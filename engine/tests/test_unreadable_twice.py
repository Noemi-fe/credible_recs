"""A kept comment whose embed page is unreadable twice, at least 7 days apart, lapses at once (25 Oct 2026, the verify2
builder; docs/verify-bfs-2026-10-25.md, option (i): "drop after a second unreadable read", about 370 reads a day freed).

Until now a page showing no comment ("Not supported comment") proved nothing, and the comment went on holding reads (one
every config.LIBRARY_VERIFY_RETRY_DAYS, and every 40 hours when answers use it) until its 30-day deadline. All 2,031 such
comments the review found came from archive-read threads, none of 4,949 read live: they are probably gone from Reddit.
Now the second unreadable read, at least config.LIBRARY_UNREADABLE_LAPSE_DAYS after the first with no passing read between,
makes the comment lapse at the next deploy (engine.verify.apply_checks): it loses its words and mentions as an expired one
does. One unreadable read still proves nothing, so a page Reddit redesigns can never wipe the library in one go (the second
read comes a week later, and a passing read in between starts over). Made-up threads and checks only.
"""

from datetime import timedelta

from engine import config, precheck
from engine.tests.test_slim import KEPT
from engine.tests.test_verify import comment, day, extraction_of, items_of, slimmed_library, thread_of
from engine.verify import Ledger, LedgerEntry, apply_checks


def test_the_lapse_needs_two_unreadable_reads_at_least_7_days_apart():
    assert config.LIBRARY_UNREADABLE_LAPSE_DAYS == 7
    ledger = Ledger()
    ledger.record("c1", day(10), "unreadable")
    assert not ledger.lapsed("c1")  # one proves nothing
    ledger.record("c1", day(16), "unreadable")
    assert not ledger.lapsed("c1")  # twice, but only 6 days apart: the same trouble, perhaps
    ledger.record("c1", day(17), "unreadable")
    assert ledger.lapsed("c1")  # 7 days after the first
    assert ledger.get("c1").unreadable_since == day(10)


def test_a_passing_read_between_starts_the_count_again():
    ledger = Ledger()
    ledger.record("c1", day(1), "unreadable")
    ledger.record("c1", day(5), "passing")  # a page that worked
    ledger.record("c1", day(9), "unreadable")
    ledger.record("c1", day(14), "unreadable")
    assert not ledger.lapsed("c1")  # the first unreadable read since the pass was day 9: 5 days
    ledger.record("c1", day(16), "unreadable")
    assert ledger.lapsed("c1") and ledger.get("c1").unreadable_since == day(9)


def test_reads_arriving_out_of_order_count_the_same():
    ledger = Ledger()
    ledger.record("c1", day(20), "unreadable")
    ledger.record("c1", day(11), "unreadable")  # an older read taken in late
    assert ledger.lapsed("c1")
    other = Ledger()
    other.record("c2", day(12), "unreadable")
    other.record("c2", day(3), "passing")
    other.record("c2", day(20), "unreadable")
    other.record("c2", day(8), "passing")  # before the run began (day 12): it changes nothing
    assert other.lapsed("c2")
    other.record("c2", day(15), "passing")  # between its first and last read: the count starts again from day 20
    assert not other.lapsed("c2")


def test_the_pass_that_arrives_late_breaks_the_run_too():
    ledger = Ledger()
    ledger.record("c1", day(2), "unreadable")
    ledger.record("c1", day(12), "unreadable")
    assert ledger.lapsed("c1")
    ledger.record("c1", day(6), "passing")  # it was readable on day 6: day 2's read no longer counts
    assert not ledger.lapsed("c1") and ledger.get("c1").passed == day(6)


def test_any_other_read_ends_the_run():
    ledger = Ledger()
    ledger.record("c1", day(2), "unreadable")
    ledger.record("c1", day(5), "changed")
    ledger.record("c1", day(12), "unreadable")
    assert not ledger.lapsed("c1")


def test_the_record_keeps_the_run_through_the_bucket_and_merges():
    ledger = Ledger()
    ledger.record("c1", day(10), "unreadable")
    ledger.record("c1", day(14), "unreadable")
    again = Ledger.loads(ledger.dumps(day(15)))
    assert again.get("c1") == ledger.get("c1") == LedgerEntry(at=day(14), outcome="unreadable", passed=None,
                                                              unreadable_since=day(10))
    mine = Ledger()
    mine.record("c1", day(19), "unreadable")  # this machine's read of a later day
    mine.merge(again)
    assert mine.lapsed("c1") and mine.get("c1").at == day(19) and mine.get("c1").unreadable_since == day(10)
    fresh = Ledger()
    fresh.record("c1", day(30), "unreadable")
    fresh.merge(again)
    assert fresh.lapsed("c1")


def test_a_record_written_before_the_rule_counts_its_unreadable_read_as_the_first():
    old = b'{"written_at": "2026-10-24T03:00:00+00:00", "comments": {"c1": {"at": "2026-10-20T10:00:00+00:00", ' \
          b'"outcome": "unreadable", "passed": null}}}'
    ledger = Ledger.loads(old)
    assert not ledger.lapsed("c1") and ledger.get("c1").unreadable_since is None
    ledger.record("c1", ledger.get("c1").at + timedelta(days=7), "unreadable")
    assert ledger.lapsed("c1")  # the second read, a week after the one the old record held


def test_the_record_still_holds_ids_dates_and_outcomes_only():
    ledger = Ledger()
    ledger.record("c1", day(1), "unreadable")
    ledger.record("c1", day(9), "unreadable")
    import json
    entry = json.loads(ledger.dumps(day(10)))["comments"]["c1"]
    assert set(entry) == {"at", "outcome", "passed", "unreadable_since"}


# --- Applying it to the library (the next deploy) ---

def test_a_comment_unreadable_twice_loses_its_words_and_mentions_at_the_next_deploy(tmp_path):
    root = slimmed_library(tmp_path)
    ledger = Ledger()
    ledger.record("s1kept", day(3), "unreadable")
    ledger.record("s1kept", day(11), "unreadable")
    ledger.record("s12note", day(3), "unreadable")
    ledger.record("s12note", day(5), "unreadable")  # twice, but too close
    result = apply_checks(root, ledger, now=day(12))
    gone = comment(root, "s1kept")
    assert (gone.status, gone.body, gone.author, gone.verified_at) == ("not_kept", "", None, None)
    assert items_of(extraction_of(root), "s1kept") == []
    assert comment(root, "s12note").status == "ok"
    assert result.dropped == {"unreadable": 1}
    # it is still on Reddit as far as we know: like an expired comment, it leaves the thread's stub with what it named
    assert thread_of(root).whole_thread.dropped.get("s1kept") == "expired"


def test_a_passing_read_after_the_second_unreadable_one_saves_the_comment(tmp_path):
    root = slimmed_library(tmp_path)
    ledger = Ledger()
    ledger.record("s1kept", day(3), "unreadable")
    ledger.record("s1kept", day(11), "unreadable")
    ledger.record("s1kept", day(12), "passing")
    assert apply_checks(root, ledger, now=day(13)).dropped == {}
    assert comment(root, "s1kept").verified_at == day(12)


def test_the_report_counts_the_lapsed_comments(tmp_path):
    from engine.verify import report

    root = slimmed_library(tmp_path)
    ledger = Ledger()
    ledger.record("s1kept", day(3), "unreadable")
    ledger.record("s1kept", day(11), "unreadable")
    assert "unreadable twice, at least 7 days apart: 1" in report(apply_checks(root, ledger, now=day(12), dry_run=True))


# --- The plan: no more reads for it ---

def kept_of(root):
    from engine.verify import kept_comments

    return kept_comments(root)


def test_a_comment_unreadable_twice_is_not_read_again_and_is_counted_apart(tmp_path):
    root = slimmed_library(tmp_path)
    ledger = Ledger()
    ledger.record("s1kept", day(3), "unreadable")
    ledger.record("s1kept", day(11), "unreadable")
    ledger.record("s2agree", day(9), "unreadable")  # once: waits for its retry
    due = precheck.due_for_verification(kept_of(root), ledger, day(20))
    ids = {c.comment_id for c in due.chosen}
    assert "s1kept" not in ids and "s2agree" in ids  # the retry is due 10 days after day 9
    assert (due.lapsed, due.gone_already) == (1, 0)
    soon = precheck.due_for_verification(kept_of(root), ledger, day(12))
    assert "s2agree" not in {c.comment_id for c in soon.chosen} and soon.waiting_retry == 1 and soon.lapsed == 1


def test_a_run_reading_the_unreadable_page_a_second_time_lapses_it_at_once(tmp_path):
    from engine.tests.test_precheck_verify import FakeEmbed, checker_at

    root = slimmed_library(tmp_path)
    ledger = Ledger()
    ledger.record("s13care", day(2), "unreadable")
    reddit = FakeEmbed(root, unreadable={"s13care"})
    when = day(2 + config.LIBRARY_VERIFY_RETRY_DAYS, hour=6)  # the retry
    precheck.verify_kept(root, checker_at(tmp_path, reddit, when), ledger, limit=20, now=when)
    assert "s13care" in reddit.asked and ledger.lapsed("s13care")
    again = FakeEmbed(root, unreadable={"s13care"})
    later = when + timedelta(days=config.LIBRARY_VERIFY_RETRY_DAYS)
    precheck.verify_kept(root, checker_at(tmp_path, again, later, "later"), ledger, limit=20, now=later)
    assert "s13care" not in again.asked  # nothing more is spent on it


def test_the_deadline_still_drops_a_comment_whose_page_was_unreadable_once(tmp_path):
    root = slimmed_library(tmp_path)
    ledger = Ledger()
    ledger.record("s1kept", day(20), "unreadable")
    result = apply_checks(root, ledger, now=day(config.LIBRARY_VERIFY_DAYS + 1))
    assert result.dropped == {"expired": len(KEPT)}  # as before: one unreadable read proves nothing, the deadline decides


def test_the_plan_leaves_it_out_of_the_answers_and_the_report_counts_it(tmp_path, capsys, monkeypatch):
    from engine.live_check import BUNDLE_NAME  # noqa: F401  (the bucket is made up too)
    from engine.tests.fake_google import FakeGoogle
    from engine.tests.test_live_check import Clock
    from engine.tests.test_precheck_plan import BUCKET, a_checker, the_plan
    from engine.verify import LEDGER_NAME

    root = slimmed_library(tmp_path)
    google, clock = FakeGoogle(buckets=(BUCKET,)), Clock()
    clock.now = day(20)
    ledger = Ledger()
    ledger.record("s1kept", day(3), "unreadable")
    ledger.record("s1kept", day(11), "unreadable")
    google.put(BUCKET, f"live_check/{LEDGER_NAME}", ledger.dumps(day(12)))
    seen = []
    real = precheck._work_out
    monkeypatch.setattr(precheck, "_work_out", lambda *a, **k: seen.append(a[4]) or real(*a, **k))
    precheck.plan_run([], root, a_checker(tmp_path, google, clock), profiles=None)
    assert "s1kept" in seen[0]  # answers drop it, as they will after the deploy
    link = next(c.url for c in thread_of(root).comments if c.id == "s1kept")
    assert link not in the_plan(google).verify
    assert "unreadable twice, at least 7 days apart (the next deploy drops them): 1" in capsys.readouterr().out
