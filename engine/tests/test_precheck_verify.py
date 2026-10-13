"""The daily pre-check keeps a slimmed library verified (Noemi, 13 Oct 2026: "Keep only comments we use"): after the
comments answers would show, it reads on Reddit's embed page the kept comments verified longest ago, within a budget of
its own (config.LIBRARY_VERIFY_READS), and records each read (when, and what it said: no words) in the verification
record, which the next deploy applies to the library (engine.verify.apply_checks).

A made-up slimmed thread and a made-up embed page: no test reads data/ or reaches the network.
"""

import json
from datetime import timedelta

import pytest

from engine import config, precheck
from engine.live_check import Bucket, LiveChecker, _entry_name, embed_url
from engine.precheck import verify_kept
from engine.tests.test_live_check import Clock, deleted_page, page
from engine.tests.test_live_check_bucket import FakeGoogle
from engine.tests.test_slim import KEPT, ZOJI
from engine.tests.test_verify import READ, day, slimmed_library, thread_of
from engine.verify import LEDGER_NAME, Ledger

ORDER = ["s1kept", "s2agree", "s4source", "s5reply", "s7copy", "s10quoted", "s12note", "s13care", "s16rej"]


class FakeEmbed:
    """Reddit's embed page for the kept comments: each as saved, unless deleted, edited or a page with no comment."""

    def __init__(self, root, gone=(), edited=(), unreadable=(), busy=()):
        self.bodies = {c.id: c.body for c in thread_of(root).comments if c.status == "ok"}
        self.gone, self.edited, self.unreadable, self.busy = set(gone), set(edited), set(unreadable), set(busy)
        self.asked: list[str] = []

    def __call__(self, url, headers):
        comment_id = url.split("/comment/")[1].split("/")[0]
        self.asked.append(comment_id)
        if comment_id in self.busy:
            return 503, b"busy"
        if comment_id in self.unreadable:
            return 200, b"<html>Not supported comment</html>"
        if comment_id in self.gone:
            return 200, deleted_page()
        if comment_id in self.edited:
            return 200, page("Edit: I changed my mind about all of this.")
        return 200, page(self.bodies[comment_id])


def checker_at(tmp_path, reddit, when, folder="cache", bucket=None):
    clock = Clock()
    clock.now = when
    return LiveChecker(cache_dir=tmp_path / folder, fetch=reddit, clock=clock, sleep=clock.sleep, min_interval=0,
                       bucket=bucket)


def test_the_kept_comments_verified_longest_ago_are_read_first_within_the_budget(tmp_path):
    root = slimmed_library(tmp_path)  # every kept comment verified when the thread was read (READ)
    ledger = Ledger()
    ledger.record("s1kept", day(5), "passing")
    ledger.record("s12note", day(6), "passing")
    reddit = FakeEmbed(root)
    reading = verify_kept(root, checker_at(tmp_path, reddit, day(10)), ledger, limit=3, now=day(10))
    assert reddit.asked == ["s2agree", "s4source", "s5reply"]  # the oldest, in thread order
    # The two verified within LIBRARY_VERIFY_AGAIN_DAYS aren't due; 4 of the 7 due are left for the next run.
    assert (reading.kept, reading.read, reading.passing, reading.not_reached) == (9, 3, 3, 4)
    assert all(ledger.get(cid).passed == day(10) and ledger.get(cid).outcome == "passing" for cid in reddit.asked)
    next_day = FakeEmbed(root)
    verify_kept(root, checker_at(tmp_path, next_day, day(11), "next"), ledger, limit=9, now=day(11))
    assert next_day.asked == ["s7copy", "s10quoted", "s13care", "s16rej"]  # those read yesterday aren't due again


def test_a_comment_checked_today_by_the_pre_check_is_recorded_without_a_read(tmp_path):
    root = slimmed_library(tmp_path)
    reddit = FakeEmbed(root)
    checker = checker_at(tmp_path, reddit, day(10))
    url = next(c.url for c in thread_of(root).comments if c.id == "s1kept")
    path = tmp_path / "cache" / _entry_name(embed_url(url))
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"fetched_at": (day(10) - timedelta(hours=2)).isoformat(), "text": ZOJI}))
    ledger = Ledger()
    reading = verify_kept(root, checker, ledger, limit=20, now=day(10))
    assert "s1kept" not in reddit.asked and reading.recorded == 1 and reading.read == len(KEPT) - 1
    assert ledger.get("s1kept").passed == day(10) - timedelta(hours=2)


def test_deleted_edited_and_unreadable_comments_are_recorded_and_the_library_is_left_as_it_is(tmp_path):
    root = slimmed_library(tmp_path)
    before = {p: p.read_bytes() for p in root.rglob("*.json")}
    reddit = FakeEmbed(root, gone={"s1kept"}, edited={"s12note"}, unreadable={"s13care"})
    ledger = Ledger()
    reading = verify_kept(root, checker_at(tmp_path, reddit, day(10)), ledger, limit=20, now=day(10))
    assert (reading.removed, reading.changed, reading.unreadable, reading.passing) == (1, 1, 1, 6)
    # The made-up page of a gone comment reads "[removed]", as Reddit's embed page shows a comment removed.
    assert ledger.get("s1kept").outcome == "removed" and ledger.get("s12note").outcome == "changed"
    assert ledger.get("s13care").outcome == "unreadable" and ledger.get("s13care").passed is None
    assert {p: p.read_bytes() for p in root.rglob("*.json")} == before  # the next deploy applies them


def test_a_comment_found_gone_is_not_read_again_and_an_unreadable_one_only_after_some_days(tmp_path):
    root = slimmed_library(tmp_path)
    ledger = Ledger()
    ledger.record("s1kept", day(8), "deleted")
    ledger.record("s2agree", day(8), "unreadable")
    reddit = FakeEmbed(root)
    reading = verify_kept(root, checker_at(tmp_path, reddit, day(10)), ledger, limit=20, now=day(10))
    assert "s1kept" not in reddit.asked and "s2agree" not in reddit.asked
    assert (reading.gone_already, reading.waiting_retry) == (1, 1)
    later = day(8 + config.LIBRARY_VERIFY_RETRY_DAYS, hour=6)
    reddit = FakeEmbed(root)
    verify_kept(root, checker_at(tmp_path, reddit, later, "later"), ledger, limit=20, now=later)
    assert "s2agree" in reddit.asked and "s1kept" not in reddit.asked


def test_a_page_that_cant_be_read_now_is_left_for_the_next_run_and_reddit_refusing_stops_it(tmp_path):
    root = slimmed_library(tmp_path)
    ledger = Ledger()
    reddit = FakeEmbed(root, busy=set(ORDER))
    reading = verify_kept(root, checker_at(tmp_path, reddit, day(10)), ledger, limit=20, now=day(10),
                          stop_after_unknown=3)
    assert reading.read == 3 and reading.unknown == 3 and reading.stopped and ledger.entries == {}


def test_a_dry_run_reads_nothing_and_says_how_many_it_would(tmp_path):
    root = slimmed_library(tmp_path)
    reddit = FakeEmbed(root)
    ledger = Ledger()
    reading = verify_kept(root, checker_at(tmp_path, reddit, day(10)), ledger, limit=5, now=day(10), dry_run=True)
    assert reddit.asked == [] and (reading.would_read, reading.not_reached) == (5, 4) and ledger.entries == {}


def test_the_report_counts_and_never_shows_a_comments_words(tmp_path):
    root = slimmed_library(tmp_path)
    reading = verify_kept(root, checker_at(tmp_path, FakeEmbed(root, gone={"s1kept"}), day(10)), Ledger(), limit=20,
                          now=day(10))
    said = precheck.verify_report(reading)
    assert "9 kept comments" in said and "1 deleted" in said and ZOJI not in said
    assert f"within {config.LIBRARY_VERIFY_DAYS} days" in said


def test_the_record_is_shared_through_the_bucket_and_starts_the_next_run(tmp_path, capsys):
    root = slimmed_library(tmp_path)
    google = FakeGoogle()
    bucket = lambda clock: Bucket(google.bucket, request=google, clock=lambda: clock.now.timestamp())
    first = FakeEmbed(root)
    checker = checker_at(tmp_path, first, day(10), "monday/cache")
    checker.bucket = bucket(checker._clock)
    precheck.run([], limit=0, dry_run=False, library_dir=root, checker=checker, profiles=None, verify_limit=20)
    assert sorted(first.asked) == sorted(ORDER)
    record = json.loads(google.objects["live_check/" + LEDGER_NAME][1])
    assert set(record["comments"]) == KEPT and "Kept comments" in capsys.readouterr().out
    # Four days on, on a new machine (its own folder, with no record of its own): the bundle's checks are too old to
    # use, the bucket's record isn't.
    second = FakeEmbed(root)
    checker = checker_at(tmp_path, second, day(14), "friday/cache")
    checker.bucket = bucket(checker._clock)
    precheck.run([], limit=0, dry_run=False, library_dir=root, checker=checker, profiles=None, verify_limit=20)
    assert second.asked == []  # every kept comment was verified four days ago: none is due yet


def test_a_library_with_nothing_slimmed_writes_no_record(tmp_path):
    from engine.tests.test_precheck import library

    google = FakeGoogle()
    def no_reads(url, headers):
        raise AssertionError("nothing to verify: Reddit isn't read")

    checker = checker_at(tmp_path, no_reads, day(10))
    checker.bucket = Bucket(google.bucket, request=google, clock=lambda: 0.0)
    reading = precheck.verify_step(library(tmp_path), checker, dry_run=False, limit=20)
    assert reading.kept == 0 and google.calls == []  # the bucket isn't even asked


@pytest.mark.parametrize("argv, expected", [
    (["--dry-run"], (["--dry-run"], {})),
    (["--verify", "2000", "--limit", "0"], (["--limit", "0"], {"verify_limit": 2000})),
    (["--verify"], (["--verify"], None)),
    (["--verify", "many"], (["--verify", "many"], None)),
])
def test_the_command_takes_a_verification_budget(argv, expected):
    assert precheck._verify_option(argv) == expected


def test_the_command_refuses_a_verification_budget_that_isnt_a_number(capsys):
    assert precheck.main(["--verify", "lots"]) == 2
    assert "--verify N" in capsys.readouterr().out


# --- The values ---

def test_the_daily_budget_verifies_a_library_of_10000_kept_comments_well_within_the_deadline():
    # Sized on 13 Oct 2026's slimmed library (about 10,200 kept comments, about 1,150 of them read every day as the
    # comments answers show): the rest are read at least every LIBRARY_VERIFY_DAYS minus a week of margin.
    rest = 10_200 - 1_150
    assert rest / config.LIBRARY_VERIFY_READS <= config.LIBRARY_VERIFY_DAYS - 7
    assert config.LIBRARY_VERIFY_RETRY_DAYS * 2 < config.LIBRARY_VERIFY_DAYS  # an unreadable page gets two more tries


def test_the_whole_run_fits_in_the_jobs_time_at_the_slowest_pace():
    import re
    from pathlib import Path

    script = (Path(precheck.REPO_ROOT) / "deploy" / "cloudrun" / "deploy.sh").read_text(encoding="utf-8")
    hours = int(re.search(r"--task-timeout (\d+)h", script).group(1))
    reads = config.PRECHECK_MAX_READS + config.LIBRARY_VERIFY_READS - config.LIVE_CHECK_BURST
    assert reads * config.LIVE_CHECK_REFILL_SECONDS + 30 * 60 < hours * 3600
