"""Shown quotes checked live several comments at a time (latency, 12 Oct 2026).

Reading Reddit's embed page takes a fraction of a second a comment, and an answer shows 10 to 40 quotes: one at a time,
that was most of an answer's wait. Now the comments of one round are read together (config.LIVE_CHECK_PARALLEL at
once), and every rule stays: a quote is shown only after its comment passed, a comment that fails loses its votes and
the answer is written again, and each comment's quotes are checked exactly as before (in the answer's order, stopping
at its first failure), so no comment is read more than it was.
"""

import threading
import time
from datetime import UTC, datetime, timedelta

from engine import config, pipeline
from engine.answer import _every_quote, unverified_claims
from engine.live_check import LiveChecker, LiveResult
from engine.pipeline import answer_request
from engine.tests.test_live_check import QUOTE, URL, FakeReddit, page
from engine.tests.test_pipeline import REQUEST, library


class SlowLive:
    """A live checker that takes `pause` seconds a check and remembers how many checks ran at once."""

    def __init__(self, pause: float = 0.05, gone=()):
        self.pause, self.gone = pause, set(gone)
        self.asked: list[tuple[str, str]] = []
        self.running = self.most = 0
        self._lock = threading.Lock()

    def check(self, url, quote, wait=True):
        with self._lock:
            self.running += 1
            self.most = max(self.most, self.running)
            self.asked.append((url, quote))
        time.sleep(self.pause)
        with self._lock:
            self.running -= 1
        comment_id = url.rstrip("/").split("/")[-1]
        return LiveResult("gone", "deleted") if comment_id in self.gone else LiveResult("ok", "still there")


def test_the_comments_of_one_answer_are_checked_together(tmp_path):
    live = SlowLive()
    result = answer_request(REQUEST, library_dir=library(tmp_path), live_checker=live)
    shown = {quote.comment_id for _, quote in _every_quote(result.answer)}
    assert len(shown) >= 3
    assert live.most > 1  # several comments were being read at once
    assert live.most <= config.LIVE_CHECK_PARALLEL


def test_every_quote_shown_was_checked_and_passed(tmp_path):
    live = SlowLive(gone={"k1aaaa"})
    result = answer_request(REQUEST, library_dir=library(tmp_path), live_checker=live)
    asked = set(live.asked)
    shown = [(quote.url, quote.text) for _, quote in _every_quote(result.answer)]
    assert shown and all(pair in asked for pair in shown)
    assert "k1aaaa" not in {quote.comment_id for _, quote in _every_quote(result.answer)}
    assert result.live_dropped == {"gone": 1}
    assert unverified_claims(result.answer, result.bodies) == []


class OneAtATime:
    """The checker the tests compare with: answers like SlowLive, but never asked for two checks at once."""

    def __init__(self, gone=()):
        self.inner = SlowLive(pause=0, gone=gone)

    def check(self, url, quote, wait=True):
        return self.inner.check(url, quote)


def test_checking_together_gives_the_same_answer_and_checks_as_one_at_a_time(tmp_path, monkeypatch):
    lib = library(tmp_path)
    together = SlowLive(pause=0.01, gone={"k1aaaa", "k2cccc"})
    first = answer_request(REQUEST, library_dir=lib, live_checker=together)
    monkeypatch.setattr(pipeline, "LIVE_CHECK_PARALLEL", 1)
    alone = OneAtATime(gone={"k1aaaa", "k2cccc"})
    second = answer_request(REQUEST, library_dir=lib, live_checker=alone)
    assert pipeline.render_markdown(first.answer) == pipeline.render_markdown(second.answer)
    assert first.live_dropped == second.live_dropped
    assert sorted(together.asked) == sorted(alone.inner.asked)


def test_a_comment_that_fails_isnt_asked_about_again_for_its_other_quotes(tmp_path):
    # Its first quote failed: its other quotes would be dropped with it, so they aren't checked (as before).
    live = SlowLive(pause=0, gone={"k1aaaa", "k1bbbb", "k2aaaa", "k2bbbb"})
    answer_request(REQUEST, library_dir=library(tmp_path), live_checker=live)
    failed = [url for url, _ in live.asked if url.rstrip("/").split("/")[-1] in live.gone]
    assert len(failed) == len(set(failed))


# --- The real checker, asked from several threads at once ---

def test_the_real_checker_still_spaces_out_its_calls_when_asked_together(tmp_path):
    import json

    def reddit(url, headers):
        time.sleep(0.02)
        return 200, page(QUOTE + " Still going.")

    live = LiveChecker(cache_dir=tmp_path / "cache", fetch=reddit, min_interval=0.05)
    urls = [URL.replace("c1aaaa", f"c{n}xxxx") for n in range(5)]
    threads = [threading.Thread(target=live.check, args=(url, QUOTE)) for url in urls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    # Each saved check is dated by the moment its call was due to start: never sooner than min_interval after another.
    started = sorted(datetime.fromisoformat(json.loads(p.read_text())["fetched_at"])
                     for p in (tmp_path / "cache").glob("*.json"))
    assert len(started) == 5
    assert min(b - a for a, b in zip(started, started[1:])) >= timedelta(seconds=0.05)


def test_the_real_checker_keeps_each_comment_once_when_asked_together(tmp_path):
    reddit = FakeReddit()
    live = LiveChecker(cache_dir=tmp_path / "cache", fetch=reddit, min_interval=0)
    urls = [URL.replace("c1aaaa", f"c{n}xxxx") for n in range(6)]
    threads = [threading.Thread(target=live.check, args=(url, QUOTE)) for url in urls]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(list((tmp_path / "cache").glob("*.json"))) == 6
    assert not list((tmp_path / "cache").glob("*.tmp"))  # each saved whole, under its own name
    assert all(live.check(url, QUOTE).show for url in urls)
    assert len(reddit.asked) == 6  # the second round came from the saved pages


def test_a_saved_check_is_dated_by_its_own_call(tmp_path):
    clock_now = [datetime(2026, 10, 12, 12, tzinfo=UTC)]

    def clock():
        return clock_now[0]

    def sleep(seconds):
        clock_now[0] += timedelta(seconds=seconds)

    live = LiveChecker(cache_dir=tmp_path / "cache", fetch=FakeReddit(), clock=clock, sleep=sleep, min_interval=3)
    live.check(URL, QUOTE)
    live.check(URL.replace("c1aaaa", "c2bbbb"), QUOTE)
    import json

    dates = sorted(json.loads(p.read_text())["fetched_at"] for p in (tmp_path / "cache").glob("*.json"))
    assert dates == ["2026-10-12T12:00:00+00:00", "2026-10-12T12:00:03+00:00"]


# --- No quote is shown unchecked, however many rounds it takes (12 Oct 2026) ---

def many_writers_library(tmp_path):
    """Five kettle threads, each with three writers praising the Zojirushi kettle for years: fifteen credible quotes."""
    import json

    from engine.tests.factories import write_gold
    from engine.tests.test_pipeline import comment, kettle_thread, mention

    threads, extractions = [], {}
    for t in range(5):
        tid = f"1kett1{t}"
        bodies = [(f"z{t}{n}aaaa", f"My Zojirushi kettle has lasted {4 + t + n} years and still boils fast.")
                  for n in range(3)]
        threads.append(kettle_thread(tid, [comment(cid, tid, body) for cid, body in bodies]))
        extractions[tid] = [mention(cid, "Zojirushi kettle", body) for cid, body in bodies]
    root = write_gold(tmp_path / "library", threads, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for tid, mentions in extractions.items():
        (root / "extracted" / f"{tid}.json").write_text(json.dumps({
            "thread_id": tid, "instructions_version": "extract-v5", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions}), encoding="utf-8")
    return root


class EverythingGone:
    """Every comment it is asked about has been deleted on Reddit since it was saved."""

    def __init__(self):
        self.asked = []

    def check(self, url, quote, wait=True):
        self.asked.append((url, quote))
        return LiveResult("gone", "deleted")


def test_quotes_shown_after_several_rounds_of_deleted_comments_were_checked_too(tmp_path):
    lib = many_writers_library(tmp_path)
    assert answer_request(REQUEST, library_dir=lib).answer.picks  # without live checks: the Zojirushi is a pick
    live = EverythingGone()
    result = answer_request(REQUEST, library_dir=lib, live_checker=live)
    shown = [(quote.url, quote.text) for _, quote in _every_quote(result.answer)]
    unchecked = [pair for pair in shown if pair not in set(live.asked)]
    assert unchecked == []  # every comment is gone, so nothing may be shown
    assert result.answer.picks == []


# --- Never past Reddit's own limit (12 Oct 2026) ---

def test_reads_beyond_the_burst_wait_their_turn(tmp_path):
    # Reddit's embed pages allow about 200 reads in 10 minutes from one address (the limit its answers state): after
    # a burst, reads start one every `refill` seconds, so the limit is never reached.
    from engine.tests.test_live_check import Clock

    clock = Clock()
    started = []

    def reddit(url, headers):
        started.append(clock())
        return 200, page(QUOTE)

    live = LiveChecker(cache_dir=tmp_path / "cache", fetch=reddit, clock=clock, sleep=clock.sleep, min_interval=0,
                       burst=3, refill=4)
    for n in range(6):
        live.check(URL.replace("c1aaaa", f"c{n}xxxx"), QUOTE)
    assert [(t - started[0]).total_seconds() for t in started] == [0, 0, 0, 4, 8, 12]


def test_the_default_budget_stays_under_reddits_limit():
    # 200 reads in any 10 minutes, as Reddit's rate-limit headers said on 12 Oct 2026: the burst plus what refills in
    # 10 minutes must stay within it, with room for a few other reads from the same address.
    assert config.LIVE_CHECK_BURST + 600 / config.LIVE_CHECK_REFILL_SECONDS <= 190
