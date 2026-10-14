"""The site reads the checks of the last 48 hours from the bucket's one bundle as it gets ready (check ahead, 13 Oct
2026; free tiers only). Since 14 Oct 2026 (the free-tier redesign, engine/read_ahead.py) it reads ahead itself when
Cloud Scheduler's keep-warm ping asks /ready (Cloud Run gives a server its processor only while it answers a request,
so a background thread waiting between requests would barely run), and writes the bundle at most hourly; it no longer
reads the bundle again each hour (engine/tests/test_read_ahead.py has the reads and the writes). No test reaches the
network.
"""

import threading

import pytest

from engine import web


class FakeLive:
    """A live checker whose bundle loads are counted (and can fail)."""

    def __init__(self, bucket=True, fails=False):
        self.bucket = object() if bucket else None
        self.fails, self.loads = fails, []

    def load_bundle(self):
        self.loads.append(1)
        if self.fails:
            raise OSError("the disk is full")
        return 3


def test_getting_ready_reads_the_pre_checks_checks_first(tmp_path, monkeypatch):
    from engine import query_model

    order = []
    live = FakeLive()
    live.load_bundle = lambda: order.append("checks") or 3
    monkeypatch.setattr(web, "live", live)
    monkeypatch.setattr(query_model, "default_query_model", lambda: order.append("model"))
    monkeypatch.setattr(web, "ready", threading.Event())
    web.warm_up(tmp_path / "no-library")
    assert order[:2] == ["checks", "model"]  # before anything slow: the first answers find them


def ping(clock_now: float) -> int:
    """Cloud Scheduler's keep-warm ping at `clock_now` (the server's clock, in seconds): /ready's status."""
    web._clock = lambda: clock_now
    return web.handle_request("/ready")[0]


class FakeAhead:
    """The site's reads ahead, whose pings and plan readings are counted (and can fail)."""

    def __init__(self, fails=False):
        self.fails, self.pings, self.plans = fails, [], []

    def on_ping(self):
        self.pings.append(1)
        if self.fails:
            raise OSError("the disk is full")

    def reload_plan_if_due(self):
        self.plans.append(1)


@pytest.fixture
def ready_site(monkeypatch):
    monkeypatch.setattr(web, "ready", threading.Event())
    web.ready.set()
    monkeypatch.setattr(web, "_clock", web._clock)
    monkeypatch.setattr(web, "read_ahead", None)


def test_without_a_bucket_nothing_is_read_and_nothing_reloads(tmp_path, monkeypatch, ready_site):
    from engine import query_model

    live = FakeLive(bucket=False)
    monkeypatch.setattr(web, "live", live)
    monkeypatch.setattr(query_model, "default_query_model", lambda: None)
    web.warm_up(tmp_path / "no-library")
    assert ping(10_000.0) == 200 and live.loads == []
    monkeypatch.setattr(web, "live", None)  # the tests' default: no live checks at all
    assert ping(20_000.0) == 200


def test_the_keep_warm_ping_reads_ahead_and_the_bundle_is_read_only_as_the_server_gets_ready(tmp_path, monkeypatch,
                                                                                              ready_site):
    # Changed on purpose, 14 Oct 2026 (the free-tier redesign): the ping read the job's bundle again at most hourly; the
    # site now reads ahead at every ping and is the bundle's writer, so it reads the bundle only as it gets ready (and
    # another writer's version just before writing over it: engine.live_check.LiveChecker.share_bundle).
    from engine import query_model

    live, ahead = FakeLive(), FakeAhead()
    monkeypatch.setattr(web, "live", live)
    monkeypatch.setattr(web, "read_ahead", ahead)
    monkeypatch.setattr(query_model, "default_query_model", lambda: None)
    web._clock = lambda: 1_000.0
    web.warm_up(tmp_path / "no-library")
    assert len(live.loads) == 1 and len(ahead.plans) == 1  # as it got ready: the checks, then the plan
    for minutes in (5, 10, 65, 125):
        assert ping(1_000.0 + 60 * minutes) == 200
    assert len(ahead.pings) == 4 and len(live.loads) == 1


def test_a_failed_reading_ahead_is_reported_and_the_ping_still_says_ready(monkeypatch, capsys, ready_site):
    ahead = FakeAhead(fails=True)
    monkeypatch.setattr(web, "live", FakeLive())
    monkeypatch.setattr(web, "read_ahead", ahead)
    assert ping(5_000.0) == 200 and len(ahead.pings) == 1
    assert "full" in capsys.readouterr().err
    assert ping(5_000.0 + 300) == 200 and len(ahead.pings) == 2  # the next ping reads ahead again


def test_a_server_still_getting_ready_reads_nothing_when_pinged(monkeypatch, ready_site):
    live, ahead = FakeLive(), FakeAhead()
    monkeypatch.setattr(web, "live", live)
    monkeypatch.setattr(web, "read_ahead", ahead)
    web.ready.clear()
    assert ping(5_000.0) == 503 and live.loads == [] and ahead.pings == []  # warm_up reads them itself
