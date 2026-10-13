"""The site reads the daily pre-check's checks from the bucket's one bundle (check ahead, 13 Oct 2026; free tiers only):
as it gets ready, then at most once an hour, when Cloud Scheduler's keep-warm ping asks /ready (Cloud Run gives a
server its processor only while it answers a request, so a background thread waiting an hour would barely run). It
never writes to the bucket. No test reaches the network.
"""

import threading

import pytest

from engine import web
from engine.live_check import BUNDLE_RELOAD_SECONDS


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


@pytest.fixture
def ready_site(monkeypatch):
    monkeypatch.setattr(web, "ready", threading.Event())
    web.ready.set()
    monkeypatch.setattr(web, "_clock", web._clock)
    monkeypatch.setattr(web, "_checks_read_at", None)


def test_without_a_bucket_nothing_is_read_and_nothing_reloads(tmp_path, monkeypatch, ready_site):
    from engine import query_model

    live = FakeLive(bucket=False)
    monkeypatch.setattr(web, "live", live)
    monkeypatch.setattr(query_model, "default_query_model", lambda: None)
    web.warm_up(tmp_path / "no-library")
    assert ping(10_000.0) == 200 and live.loads == []
    monkeypatch.setattr(web, "live", None)  # the tests' default: no live checks at all
    assert ping(20_000.0) == 200


def test_the_keep_warm_ping_reads_the_checks_again_at_most_once_an_hour(tmp_path, monkeypatch, ready_site):
    from engine import query_model

    live = FakeLive()
    monkeypatch.setattr(web, "live", live)
    monkeypatch.setattr(query_model, "default_query_model", lambda: None)
    web._clock = lambda: 1_000.0
    web.warm_up(tmp_path / "no-library")
    assert len(live.loads) == 1  # as it got ready
    assert ping(1_000.0 + 300) == 200 and len(live.loads) == 1  # 5 minutes on: not due
    assert ping(1_000.0 + BUNDLE_RELOAD_SECONDS) == 200 and len(live.loads) == 2
    assert ping(1_000.0 + BUNDLE_RELOAD_SECONDS + 300) == 200 and len(live.loads) == 2


def test_a_failed_reading_is_reported_and_the_ping_still_says_ready(monkeypatch, capsys, ready_site):
    live = FakeLive(fails=True)
    monkeypatch.setattr(web, "live", live)
    assert ping(5_000.0) == 200 and len(live.loads) == 1
    assert "full" in capsys.readouterr().err
    assert ping(5_000.0 + 60) == 200 and len(live.loads) == 1  # tried again in an hour, not at every ping


def test_a_server_still_getting_ready_reads_nothing_when_pinged(monkeypatch, ready_site):
    live = FakeLive()
    monkeypatch.setattr(web, "live", live)
    web.ready.clear()
    assert ping(5_000.0) == 503 and live.loads == []  # warm_up reads them itself
