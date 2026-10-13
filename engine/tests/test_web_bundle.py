"""The site reads the daily pre-check's checks from the bucket's one bundle (check ahead, 13 Oct 2026; free tiers only):
as it gets ready, then at most once an hour. It never writes to the bucket. No test reaches the network.
"""

import threading

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


def test_without_a_bucket_nothing_is_read_and_nothing_reloads(tmp_path, monkeypatch):
    from engine import query_model

    live = FakeLive(bucket=False)
    monkeypatch.setattr(web, "live", live)
    monkeypatch.setattr(query_model, "default_query_model", lambda: None)
    monkeypatch.setattr(web, "ready", threading.Event())
    web.warm_up(tmp_path / "no-library")
    assert live.loads == [] and web.start_reloading_checks() is None
    monkeypatch.setattr(web, "live", None)  # the tests' default: no live checks at all
    assert web.start_reloading_checks() is None


def test_the_checks_are_read_again_every_hour_and_a_failure_never_stops_it(monkeypatch, capsys):
    live = FakeLive(fails=True)
    monkeypatch.setattr(web, "live", live)
    slept = []
    web.reload_checks(rounds=3, sleep=slept.append)
    assert slept == [BUNDLE_RELOAD_SECONDS] * 3 and len(live.loads) == 3
    assert "full" in capsys.readouterr().err


def test_the_hourly_reading_runs_in_the_background(monkeypatch):
    live = FakeLive()
    monkeypatch.setattr(web, "live", live)
    started = []
    monkeypatch.setattr(web, "reload_checks", lambda: started.append(threading.current_thread().name))
    thread = web.start_reloading_checks()
    thread.join(timeout=5)
    assert started == [thread.name] and thread.daemon
