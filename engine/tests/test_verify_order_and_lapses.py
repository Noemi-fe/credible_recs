"""When deadlines tie, kept comments are verified by use; and the plan job's report projects the lapses (25 Oct 2026, the
verify2 builder; docs/verify-bfs-2026-10-25.md, option (b), the review's "priority by use, a tie-break only").

A kept comment must pass a read within 30 calendar days (config.LIBRARY_VERIFY_DAYS). Until now the plan listed the kept
comments oldest first, down to the minute, then by thread: 22,836 of the 78,000 are due on 13 Nov alone, so on a shortfall
the comments that lapsed were whichever sat last in thread order. Now the deadline is the calendar day, and within one
deadline day the comments answers use come first: the answers' own comments (read by the site anyway, first), then those
that back a product an answer shows (a credible mention first), then those that back a product ranked just behind, then the
rest. An earlier deadline still always comes first. The report says how many comments the day's budget leaves to lapse.
Made-up comments and threads only.
"""

from datetime import UTC, datetime, timedelta

import pytest

from engine import config, precheck
from engine.tests.test_precheck import REQUEST, library
from engine.verify import KeptComment, Ledger

NOW = datetime(2026, 10, 26, 3, tzinfo=UTC)


def a_comment(cid: str, verified_days_ago: int | None, thread="t1", order=0, hour=12) -> KeptComment:
    """A kept comment last verified `verified_days_ago` days before NOW (at `hour`), or never verified (read at archive time
    40 days ago)."""
    when = None if verified_days_ago is None else (NOW - timedelta(days=verified_days_ago)).replace(hour=hour)
    return KeptComment(thread, cid, f"https://www.reddit.com/r/x/comments/{thread}/t/{cid}/", (), when,
                       NOW - timedelta(days=40), order)


def chosen(kept, **settings):
    return [c.comment_id for c in precheck.due_for_verification(kept, Ledger(), NOW, **settings).chosen]


# --- The order ---

def test_without_any_use_the_order_is_the_old_one_oldest_first_then_thread_and_place():
    kept = [a_comment("b", 20, thread="t2"), a_comment("a", 20, thread="t1", order=3), a_comment("c", 25, thread="t9"),
            a_comment("d", 20, thread="t1", order=1)]
    assert chosen(kept) == ["c", "d", "a", "b"]


def test_within_one_deadline_day_the_comments_answers_use_come_first():
    kept = [a_comment("unused", 20, thread="t1", hour=3),   # the same calendar day, an earlier hour and thread
            a_comment("behind", 20, thread="t2", hour=9),
            a_comment("shown", 20, thread="t3", hour=15),
            a_comment("other", 20, thread="t0", hour=1)]
    use = {"shown": 1, "behind": 2}
    assert chosen(kept, use=use) == ["shown", "behind", "other", "unused"]  # rest in the old order


def test_an_earlier_deadline_day_comes_first_whatever_the_use():
    kept = [a_comment("used_late", 20, thread="t1"), a_comment("unused_early", 21, thread="t2")]
    assert chosen(kept, use={"used_late": 1}) == ["unused_early", "used_late"]


def test_the_answers_own_comments_are_left_to_the_site_and_never_cost_the_budget():
    kept = [a_comment("quoted", 25), a_comment("backs_a_pick", 24), a_comment("nothing", 23)]
    assert chosen(kept, exclude={"quoted"}, limit=1, use={"backs_a_pick": 1}) == ["backs_a_pick"]


# --- The plan passes it on ---

def test_the_plan_works_out_each_comments_use_from_the_answers_it_writes(tmp_path):
    lib = library(tmp_path)
    from engine.live_check import LiveChecker

    checker = LiveChecker(cache_dir=tmp_path / "empty", fetch=lambda url, headers: (500, b""))
    found = precheck._work_out([REQUEST], lib, checker, None)
    quoted = {c.comment_id for c in found.candidates}
    assert quoted and all(found.use[cid] == 0 for cid in quoted)  # an answer's own comment: first of all
    assert set(found.use) >= quoted


def test_a_comment_backing_a_shown_product_without_being_quoted_comes_before_one_backing_nothing(tmp_path, monkeypatch):
    # Zojirushi is a pick; "z9zzzz" is a mention of it that takes no side worth quoting (never used it): it isn't an
    # answer's comment, but it backs a product the answer shows.
    from engine.tests import test_precheck as base

    extra = ("z9zzzz", "1kett01", "Zojirushi kettle", "recommend", "I think a Zojirushi kettle is fine, so I have read.")
    monkeypatch.setattr(base, "COMMENTS", [*base.COMMENTS, extra])
    lib = base.library(tmp_path)
    from engine.live_check import LiveChecker

    checker = LiveChecker(cache_dir=tmp_path / "empty", fetch=lambda url, headers: (500, b""))
    found = precheck._work_out([REQUEST], lib, checker, None)
    quoted = {c.comment_id for c in found.candidates}
    assert "z9zzzz" not in quoted and found.use["z9zzzz"] == 2  # a mention (not a credible one) of a shown product
    assert found.use.get("nobody", 3) == 3


def test_the_plan_gives_the_use_to_the_choice_of_kept_comments(tmp_path, monkeypatch):
    from engine.tests.fake_google import FakeGoogle
    from engine.tests.test_live_check import Clock
    from engine.tests.test_precheck_plan import BUCKET, a_checker

    seen = []
    real = precheck.due_for_verification
    monkeypatch.setattr(precheck, "due_for_verification", lambda *a, **k: seen.append(k.get("use")) or real(*a, **k))
    lib, google, clock = library(tmp_path), FakeGoogle(buckets=(BUCKET,)), Clock()
    # a slimmed library is needed for a kept comment; here none, so only the call's arguments are looked at
    monkeypatch.setattr(precheck, "kept_comments", lambda folder: [a_comment("k1", 10)])
    precheck.plan_run([REQUEST], lib, a_checker(tmp_path, google, clock), profiles=None)
    assert seen and seen[0] and 0 in seen[0].values()  # the answers' own comments are level 0


# --- The projection ---

def project(kept, per_day, **more):
    return precheck.projected_lapses(kept, Ledger(), NOW, per_day, **more)


def test_nothing_lapses_when_the_budget_reads_everything_due_in_time():
    kept = [a_comment(f"c{n}", 29) for n in range(10)]  # due tomorrow: today and tomorrow to read them
    projection = project(kept, per_day=5)
    assert (projection.lapses, projection.first_day) == (0, None)


def test_what_the_budget_cannot_read_by_its_deadline_lapses_the_day_after():
    kept = [a_comment(f"c{n}", 29) for n in range(10)]  # last day without a pass: tomorrow, 27 Oct
    projection = project(kept, per_day=4)  # 4 today, 4 tomorrow
    assert projection.lapses == 2
    assert projection.first_day == datetime(2026, 10, 28).date() and projection.busiest == 10
    assert projection.busiest_day == datetime(2026, 10, 27).date()


def test_the_oldest_deadline_is_read_first_so_later_ones_are_the_ones_that_lapse():
    early = [a_comment(f"e{n}", 29) for n in range(4)]
    late = [a_comment(f"l{n}", 25) for n in range(10)]  # five more days
    assert project(early + late, per_day=3).lapses == 0  # 14 reads in 6 days at 3 a day (the four early ones first)
    assert project(early + late, per_day=2).lapses == 2  # 12 reads in 6 days for 14 comments; the late ones are the two


def test_a_comment_verified_a_few_days_ago_isnt_due_until_a_week_after_its_read():
    fresh = [a_comment(f"f{n}", 3) for n in range(6)]  # read 3 days ago: due again from 4 days on, deadline in 27 days
    assert project(fresh, per_day=1).lapses == 0
    crowd = [a_comment(f"x{n}", 29) for n in range(3)]
    assert project(fresh + crowd, per_day=2).lapses == 0  # the three due tomorrow go first; the fresh ones can wait


def test_the_answers_own_comments_are_left_out_for_the_site_reads_them_anyway():
    kept = [a_comment(f"c{n}", 29) for n in range(10)]
    assert project(kept, per_day=4, exclude={"c0", "c1"}).lapses == 0


def test_lapses_say_how_many_back_products_answers_show():
    kept = [a_comment("shown", 29, thread="t9"), *[a_comment(f"c{n}", 29, thread="t1") for n in range(5)]]
    assert project(kept, per_day=3, use={"shown": 1}).lapses == 0  # 6 due tomorrow, 6 reads in the two days
    projection = project(kept, per_day=2, use={"shown": 1})  # 4 reads: the used comment is read first (thread t9 last)
    assert (projection.lapses, projection.lapses_used) == (2, 0)
    unused = project(kept, per_day=2)  # without use the thread order decides: "shown" is last and lapses
    assert (unused.lapses, unused.lapses_used) == (2, 0)  # (nothing known of its use: counted with the others)


def test_unreadable_pages_are_counted_apart_and_never_in_the_lapses():
    kept = [a_comment("u1", 29), a_comment("u2", 29), a_comment("ok", 29)]
    ledger = Ledger()
    ledger.record("u1", NOW - timedelta(days=9), "unreadable")
    ledger.record("u1", NOW - timedelta(days=1), "unreadable")  # twice, a week apart: lapsed
    ledger.record("u2", NOW - timedelta(days=3), "unreadable")  # once: waiting for its second read
    projection = precheck.projected_lapses(kept, ledger, NOW, 1)
    assert (projection.lapses, projection.unreadable_lapsed, projection.unreadable_waiting) == (0, 1, 1)


def test_the_projection_runs_over_a_whole_library_quickly():
    import time

    kept = [a_comment(f"c{n}", n % 31, thread=f"t{n % 977}", order=n) for n in range(80_000)]
    started = time.perf_counter()
    projection = project(kept, per_day=config.LIBRARY_VERIFY_READS)
    assert time.perf_counter() - started < 10 and projection.busiest > 0


def test_the_report_has_a_projected_lapses_line_with_counts_only(tmp_path, capsys):
    from engine.tests.fake_google import FakeGoogle
    from engine.tests.test_live_check import Clock
    from engine.tests.test_precheck_plan import BUCKET, a_checker
    from engine.tests.test_verify import day, slimmed_library

    root = slimmed_library(tmp_path)
    google, clock = FakeGoogle(buckets=(BUCKET,)), Clock()
    clock.now = day(10)
    precheck.plan_run([], root, a_checker(tmp_path, google, clock), profiles=None, verify_limit=3)
    said = capsys.readouterr().out
    assert "Projected lapses at 3 reads a day (oldest deadline first, ties by use): none would lapse" in said
    kept = [a_comment(f"c{n}", 29) for n in range(10)]
    line = precheck.projection_report(project(kept, per_day=4), 4)
    assert line.startswith("Projected lapses at 4 reads a day (oldest deadline first, ties by use): 2 readable kept "
                           f"comments would pass their {config.LIBRARY_VERIFY_DAYS} days unread, the first lapsing on "
                           "28 Oct")
    assert "10 due on 27 Oct" in line and "Unreadable pages: 0 lapsed" in line
    assert precheck.projection_report(project(kept, per_day=40), 40).count("none would lapse") == 1
