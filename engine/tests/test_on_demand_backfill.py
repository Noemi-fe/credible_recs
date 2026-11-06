"""Doubling on-demand reading, with backfill (Noemi, 5 Nov 2026: "You can double (do it with random products if people
don't research any), but make sure my claude usage for this week and in general stays under control"; "Let's do A").

The month's reading time doubles (config.ON_DEMAND_MONTH_SECONDS), and when no visitor waits the job may read a product
nobody asked for: one whose answer is thin, chosen in an order seeded by the day, never one read in the last
ON_DEMAND_READ_AGAIN_DAYS. Visitors always come first: their first ON_DEMAND_GUARD_FREE_SECONDS a month work exactly as
before, and backfill has room only within its share of the month, Gemini's calls and the bundle. Google's free allowance
is one pot shared with the site, so every backfill read and every visitor read past those first seconds asks the
free-tier guard first (engine/free_tier.py), which answers no whenever it can't read Cloud Monitoring.

Every text is made up; every service is a stand-in (engine/tests/on_demand_fakes.py, fake_google.py): no test reaches
the network.
"""

import json
import types
from datetime import UTC, datetime, timedelta

import pytest

from engine import config, on_demand, precheck
from engine.config import (ON_DEMAND_BACKFILL_SECONDS, ON_DEMAND_BUNDLE_MAX_THREADS, ON_DEMAND_CALLS_PER_PRODUCT,
                           ON_DEMAND_GEMINI_CALLS_A_DAY, ON_DEMAND_GUARD_FREE_SECONDS, ON_DEMAND_MONTH_SECONDS,
                           ON_DEMAND_PRODUCT_MINUTES)
from engine.free_tier import Verdict
from engine.live_check import Bucket
from engine.models import Thread
from engine.on_demand import (Entry, JobStarter, Queue, QueueStore, SiteReader, backfill_due, backfill_order,
                              backfill_stop, entry_for, run_job)
from engine.query import parse_query
from engine.tests.fake_google import FakeGoogle
from engine.tests.on_demand_fakes import NOW, FakeArchive, FakeGemini, Ticks, archive, gemini
from engine.tests.test_on_demand_job import NAME, bucket, the_bundle, the_library, the_queue
from engine.tests.test_web import kettle_library

JOB = "projects/credible-picks/locations/europe-west1/jobs/credible-recs-reader"
TEAPOT = "teapot for loose leaf tea"
KETTLE = "electric kettle that lasts"
PRODUCT_SECONDS = ON_DEMAND_PRODUCT_MINUTES * 60


class FakeGuard:
    """The free-tier guard's answer, chosen by the test; every question remembered."""

    def __init__(self, yes=True, failed=False):
        self.yes, self.failed, self.asked = yes, failed, []

    def allows(self, now, extra_seconds=PRODUCT_SECONDS, reader_seconds=0.0):
        self.asked.append({"now": now, "extra_seconds": extra_seconds, "reader_seconds": reader_seconds})
        why = "made-up: CPU 40%, memory 50%" if self.yes else (
            "Cloud Monitoring couldn't be read (made-up)" if self.failed else "made-up: memory 93% of the free part")
        return Verdict(self.yes, why, None if self.failed else 1.0, None if self.failed else 0.5, failed=self.failed)


def thin(request: str) -> Entry:
    return Entry.waiting_for(parse_query(request), had=0, backfill=True)


def made_up(product_type: str) -> Entry:
    """A thin product's candidate entry, with made-up need words."""
    return Entry(key=f"kitchen/{product_type}/", category="kitchen", product_type=product_type,
                 subreddits=["BuyItForLife"], backfill=True)


def with_candidates(queue: Queue, entries: list[Entry], day: str = "2026-10-09") -> Queue:
    queue.backfill = {"day": day, "candidates": [entry.as_json() for entry in entries]}
    return queue


def run(tmp_path, google, guard, fake_archive=None, fake_gemini=None, now=NOW, ticks=None):
    return run_job(bucket(google), the_library(tmp_path), archive(tmp_path, fake_archive or FakeArchive()),
                   gemini(fake_gemini or FakeGemini()), now=lambda: now, clock=ticks or Ticks(),
                   work_dir=tmp_path / "work", guard=guard)


def change(google, edit) -> None:
    QueueStore(bucket(google)).change(lambda queue: edit(queue) and None)


# --- The numbers ---

def test_backfill_has_at_most_half_the_month_and_never_any_of_visitors_first_seconds():
    assert ON_DEMAND_GUARD_FREE_SECONDS == 50_000  # visitors' month as it was before the doubling, without the guard
    assert ON_DEMAND_BACKFILL_SECONDS == min(ON_DEMAND_MONTH_SECONDS // 2,
                                             ON_DEMAND_MONTH_SECONDS - ON_DEMAND_GUARD_FREE_SECONDS)
    assert config.ON_DEMAND_BACKFILL_VISITOR_REQUESTS == 20 and config.ON_DEMAND_BACKFILL_BUNDLE_THREADS == 150
    assert config.ON_DEMAND_BACKFILL_BUNDLE_THREADS <= ON_DEMAND_BUNDLE_MAX_THREADS // 2


def test_the_told_monthly_capacity_follows_the_doubled_month():
    assert on_demand.products_a_month() == ON_DEMAND_MONTH_SECONDS // PRODUCT_SECONDS == 73


# --- Which product, and when ---

def test_thin_products_come_in_an_order_seeded_by_the_day():
    candidates = [made_up(f"made-up thing {n}") for n in range(10)]
    first_day, next_day = backfill_order(candidates, "2026-10-09"), backfill_order(candidates, "2026-10-10")
    assert sorted(e.key for e in first_day) == sorted(e.key for e in candidates)
    assert [e.key for e in first_day] == [e.key for e in backfill_order(list(reversed(candidates)), "2026-10-09")]
    assert [e.key for e in first_day] != [e.key for e in next_day]
    queue = with_candidates(Queue(), candidates)
    chosen = backfill_due(queue, NOW)
    assert chosen.key == first_day[0].key and chosen.backfill and chosen.status == "waiting"
    assert backfill_due(queue, NOW).key == chosen.key  # the same all day


def test_a_product_read_in_the_last_30_days_or_waiting_is_never_backfilled():
    first, second = backfill_order([made_up("made-up kettle"), made_up("made-up teapot")], "2026-10-09")
    queue = with_candidates(Queue(), [first, second])
    read = Entry(key="kitchen/" + first.product_type + "/handle", category="kitchen", product_type=first.product_type,
                 subreddits=["tea"])
    read.finish(NOW - timedelta(days=29), found=4)  # read for a visitor, other need words: the same product
    queue.entries.append(read)
    assert backfill_due(queue, NOW).product_type == second.product_type
    assert backfill_due(queue, NOW + timedelta(days=2)).product_type == first.product_type  # its 30 days are over


@pytest.mark.parametrize("state", ["visitor waiting", "backfill waiting", "queue resting", "backfill resting"])
def test_nothing_is_backfilled_while_a_visitor_or_a_backfill_waits_or_reading_rests(state):
    queue = with_candidates(Queue(), [made_up("made-up teapot")])
    if state == "visitor waiting":
        queue.add(entry_for(parse_query(KETTLE), had=0))
    elif state == "backfill waiting":
        queue.add(made_up("made-up toaster"))
    elif state == "queue resting":
        queue.rest(NOW + timedelta(hours=1), "gemini")
    else:
        queue.rest_backfill(NOW + timedelta(hours=1), "guard")
    assert backfill_due(queue, NOW) is None


def november(day: float) -> datetime:
    """`day` days into November 2026 (30 days), as Google bills it: from 08:00 UTC on 1 November. Changed on purpose 6 Nov
    2026: from midnight UTC until the month moved to Google's billing month (config.BILLING_MONTH_CUT_HOUR_UTC)."""
    return datetime(2026, 11, 1, 8, 0, tzinfo=UTC) + timedelta(days=day)


def used(backfill: float, total: float | None = None, calls: int = 0, now: datetime | None = None) -> Queue:
    queue = with_candidates(Queue(), [made_up("made-up teapot")])
    queue.usage_now(now or november(15)).update(seconds=backfill if total is None else total,
                                               backfill_seconds=backfill, gemini_calls=calls)
    return queue


def test_backfill_is_paced_evenly_through_the_month():
    # Its share of the days gone: half of November gone, half of its seconds, one request's time at a time.
    share = ON_DEMAND_BACKFILL_SECONDS * 15 / 30
    assert backfill_stop(used(share - PRODUCT_SECONDS - 1), november(15)) is None
    why, until = backfill_stop(used(share - PRODUCT_SECONDS + 100), november(15))
    assert why == "pace" and november(15) < until < november(15.1)
    assert until == november(30 * (share + 100) / ON_DEMAND_BACKFILL_SECONDS)  # when its share has grown enough
    why, _ = backfill_stop(used(0, now=november(0.01)), november(0.01))  # the first minutes of the month
    assert why == "pace"


def test_backfill_never_passes_its_half_nor_the_months_time():
    assert backfill_stop(used(ON_DEMAND_BACKFILL_SECONDS - PRODUCT_SECONDS + 1, now=november(29.9)), november(29.9))[0] == "half"
    why, until = backfill_stop(used(0, total=ON_DEMAND_MONTH_SECONDS - PRODUCT_SECONDS + 1), november(15))
    assert why == "month" and until == datetime(2026, 12, 1, 8, 0, tzinfo=UTC)  # 08:00 UTC since 6 Nov 2026 (the cut)


def test_backfill_leaves_gemini_enough_for_20_visitor_requests():
    room = ON_DEMAND_GEMINI_CALLS_A_DAY - ON_DEMAND_CALLS_PER_PRODUCT * 21  # 20 visitors' requests and its own
    assert room == 135
    assert backfill_stop(used(0, calls=room), november(15)) is None
    why, until = backfill_stop(used(0, calls=room + 1), november(15))
    assert why == "gemini" and until == on_demand.next_gemini_reset(november(15))


def test_backfill_stops_while_the_bundle_holds_150_threads_not_baked_in():
    queue = used(0)
    queue.bundle_threads = 149
    assert backfill_stop(queue, november(15)) is None
    queue.bundle_threads = 150
    assert backfill_stop(queue, november(15))[0] == "bundle"


# --- The job ---

def queue_backfill(google, request=TEAPOT) -> Entry:
    entry = thin(request)
    change(google, lambda queue: queue.add(entry))
    return entry


def test_a_backfill_read_asks_the_guard_reads_arctic_shift_checks_every_quote_and_is_logged(tmp_path):
    google, guard = FakeGoogle(), FakeGuard(yes=True)
    queue_backfill(google)
    report = run(tmp_path, google, guard)
    # Changed on purpose 6 Nov 2026 (fix round, the code and cost reviews): the guard was asked about the read alone;
    # now about the read and the rest of visitors' first 50,000 seconds (this run's start counted as theirs so far).
    assert len(guard.asked) == 1
    kept = ON_DEMAND_GUARD_FREE_SECONDS - config.ON_DEMAND_START_SECONDS
    assert guard.asked[0]["extra_seconds"] == PRODUCT_SECONDS + kept
    bundle = the_bundle(google)
    assert len(bundle.threads) == 3
    assert {Thread.model_validate_json(item.thread).read_from for item in bundle.threads.values()} == {"arctic_shift"}
    assert report.quotes_dropped == 1  # the made-up misquote: the word-for-word check runs as for visitors
    [entry] = the_queue(google).entries
    assert entry.status == "done" and entry.backfill and entry.found == 3
    assert [line["product_type"] for line in report.backfill] == ["teapot"]
    assert report.backfill[0]["gemini_calls"] == report.gemini_calls > 0
    assert "Backfill read now: teapot (" in report.text() and "Gemini calls)" in report.text()
    queue = the_queue(google)
    assert queue.last_run["backfill"] == report.backfill
    assert queue.usage["backfill_seconds"] == queue.usage["seconds"] > 0  # a backfill-only run is backfill's time
    assert queue.bundle_threads == 3


# --- Fix round, 6 Nov 2026 (the gate, the code review and the cost review) ---

def test_a_backfill_asks_the_guard_to_keep_room_for_the_rest_of_visitors_first_50000_seconds(tmp_path):
    # Visitors' first 50,000 seconds never ask the guard, so nothing could stop them later in the month: a backfill read
    # is asked about together with what is left of them, at the reader's size.
    # Backfill's seconds 9,000, not 10,000, since 6 Nov 2026: with the month from 08:00 UTC on the 1st (Google's billing
    # month) its share of 9 October at noon is about 11,065 seconds, and 10,000 and one more read would pass it.
    google, guard = FakeGoogle(), FakeGuard(yes=True)
    queue_backfill(google)
    change(google, lambda queue: queue.usage_now(NOW).update(seconds=30_000, backfill_seconds=9_000))
    run(tmp_path, google, guard)
    visitors = 30_000 - 9_000 + config.ON_DEMAND_START_SECONDS
    assert guard.asked[0]["extra_seconds"] == PRODUCT_SECONDS + ON_DEMAND_GUARD_FREE_SECONDS - visitors
    # Past their 50,000, nothing more is kept for them: they ask the guard themselves.
    google, guard = FakeGoogle(), FakeGuard(yes=True)
    queue_backfill(google)
    change(google, lambda queue: queue.usage_now(NOW).update(seconds=70_000, backfill_seconds=9_000))
    run(tmp_path, google, guard)
    assert guard.asked[0]["extra_seconds"] == PRODUCT_SECONDS


def test_a_month_with_room_for_one_read_but_not_for_visitors_rest_gets_no_backfill(tmp_path):
    # The real guard over a made-up Cloud Monitoring (9 Oct at noon: 8 days and 4 hours gone): one 21-minute read would
    # project the CPU part at 72%, but with visitors' 49,970 seconds still to come at 93%, past the 90% line. No
    # backfill. Changed on purpose 6 Nov 2026: the month starts at 08:00 UTC on the 1st (Google's billing month), where
    # it started at midnight (8.5 days gone, 71% and 92%).
    from engine.free_tier import Guard
    from engine.tests.test_free_tier import PROJECT, FakeMonitoring

    site, precheck = ("cloud_run_revision", config.CLOUD_RUN_SITE), ("cloud_run_job", config.CLOUD_RUN_PRECHECK)
    monitoring = FakeMonitoring(month={site: (16_000, 20_000, 48_000), precheck: (16_000, 16_000, 32_000)},
                                week={site: (14_000, 19_000, 42_000), precheck: (14_000, 14_000, 28_000)},
                                starts=("2026-10-01T08:00:00Z", "2026-10-02T12:00:00Z"))  # the cut (6 Nov 2026)
    guard = Guard(PROJECT, token=lambda: "token-1", request=monitoring, clock=lambda: 0.0)
    one_read = guard.allows(NOW, extra_seconds=PRODUCT_SECONDS, reader_seconds=30)
    assert one_read.yes and one_read.cpu / config.FREE_TIER_DOLLARS["cpu"] == pytest.approx(0.72, abs=0.005)
    google, fake = FakeGoogle(), FakeArchive()
    queue_backfill(google)
    report = run(tmp_path, google, guard, fake_archive=fake)
    queue = the_queue(google)
    assert fake.requests == [] and queue.entries == [] and queue.backfill_resting_why == "guard"
    assert any("49,970 of visitors' seconds kept" in note and "CPU $4.00 (93%" in note for note in report.notes)


def test_a_run_that_asks_the_guard_or_does_backfill_counts_at_least_the_minute_google_bills(tmp_path):
    # Cloud Run bills a job's run for at least a minute (https://cloud.google.com/run/pricing, read 6 Nov 2026).
    assert config.ON_DEMAND_RUN_BILLED_SECONDS == 60
    refused = FakeGoogle()
    queue_backfill(refused)
    run(tmp_path, refused, FakeGuard(yes=False))  # started only to be refused: a few seconds of work
    assert the_queue(refused).usage["seconds"] == the_queue(refused).usage["backfill_seconds"] == 60
    past = FakeGoogle()
    change(past, lambda queue: queue.add(entry_for(parse_query(TEAPOT), had=0)))
    change(past, lambda queue: queue.usage_now(NOW).update(seconds=ON_DEMAND_GUARD_FREE_SECONDS))
    run(tmp_path, past, FakeGuard(yes=False))
    assert the_queue(past).usage["seconds"] == ON_DEMAND_GUARD_FREE_SECONDS + 60
    # A visitor's run within their first 50,000 seconds counts as it always has.
    visitor = FakeGoogle()
    change(visitor, lambda queue: queue.add(entry_for(parse_query(TEAPOT), had=0)))
    run(tmp_path, visitor, FakeGuard(yes=False))
    assert the_queue(visitor).usage["seconds"] == config.ON_DEMAND_START_SECONDS  # the stand-in clock never moved


# Changed on purpose 6 Nov 2026 (the second cost review): the month's end was midnight UTC, so a rest woke while Google
# still billed October and the backlog read under visitors' fresh first 50,000 seconds, which never ask the guard. The
# month now ends at the cut, 08:00 UTC on the 1st (Google's billing month runs on US Pacific time), and so does the rest.
@pytest.mark.parametrize("when, until", [
    (NOW, NOW + timedelta(hours=config.ON_DEMAND_GUARD_REST_HOURS)),
    (datetime(2026, 11, 1, 4, 0, tzinfo=UTC), datetime(2026, 11, 1, 8, 0, tzinfo=UTC)),  # a new month starts afresh
])
def test_past_visitors_first_seconds_a_failed_reading_rests_reading_6_hours_and_never_past_the_month(tmp_path, when,
                                                                                                     until):
    # Changed on purpose 6 Nov 2026 (fix round, the cost review): an hour's rest after a failed reading started the paid
    # job every hour while a visitor waited.
    google = FakeGoogle()
    change(google, lambda queue: queue.add(entry_for(parse_query(TEAPOT), had=0)))
    change(google, lambda queue: queue.usage_now(when).update(seconds=ON_DEMAND_GUARD_FREE_SECONDS))
    run(tmp_path, google, FakeGuard(yes=False, failed=True), now=when)
    queue = the_queue(google)
    assert queue.resting_why == "guard" and queue.resting_until == until.isoformat()


def test_no_backfill_is_offered_while_its_own_limits_say_no(tmp_path):
    # The ping (and the pre-check) offer one only when backfill_stop has room: otherwise it would start the paid job
    # every hour only for the job to drop it.
    google, ticks = FakeGoogle(), Ticks()

    def paced_out(queue):
        with_candidates(queue, [made_up("made-up teapot")])
        queue.usage_now(NOW).update(seconds=20_000, backfill_seconds=20_000)  # far past its share of 8.5 days

    change(google, paced_out)
    assert backfill_stop(the_queue(google), NOW)[0] == "pace" and backfill_due(the_queue(google), NOW) is None
    a_site(tmp_path, google, ticks).on_ping()
    assert the_queue(google).waiting() == [] and google.jobs_started == []


def test_a_new_month_starts_backfills_seconds_from_nothing():
    queue = with_candidates(Queue(), [made_up("made-up teapot")])
    queue.usage.update(month="2026-09", seconds=91_000.0, backfill_seconds=ON_DEMAND_BACKFILL_SECONDS)
    assert backfill_stop(queue, NOW) is None and backfill_due(queue, NOW) is not None
    assert queue.usage_now(NOW)["backfill_seconds"] == 0.0


def test_a_request_queued_again_starts_afresh_as_whoever_asks_now():
    queue = Queue()
    entry = queue.add(thin(TEAPOT))
    entry.started_at = NOW.isoformat()
    entry.finish(NOW, found=2)
    again = queue.add(entry_for(parse_query(TEAPOT), had=2))  # a visitor, later
    assert again is entry and again.status == "waiting" and again.started_at is None and not again.backfill
    again.finish(NOW, found=1)
    assert queue.add(thin(TEAPOT)).backfill  # and backfill, later still


def test_a_backfill_never_waits_for_another_try(tmp_path, monkeypatch):
    from engine.tests.test_on_demand_job import SearchesFail, more_teapots

    down = FakeGoogle()
    queue_backfill(down)
    run(tmp_path, down, FakeGuard(yes=True), fake_archive=FakeArchive(down=True))
    [entry] = the_queue(down).entries
    assert entry.status == "done" and entry.found == 0 and entry.tries == 1  # a visitor's would wait for 2 more tries
    every = more_teapots(monkeypatch)
    cut_short = FakeGoogle()
    queue_backfill(cut_short)
    run(tmp_path, cut_short, FakeGuard(yes=True), fake_archive=SearchesFail(threads=every))
    [entry] = the_queue(cut_short).entries
    assert entry.status == "done" and entry.found == 2  # closed with what it found; a visitor's would wait


def test_a_backfill_reads_though_its_library_has_enough_threads(tmp_path):
    # Thin is fewer than 3 picks, whatever the threads: a visitor's request with this many isn't read.
    google, fake = FakeGoogle(), FakeArchive()
    change(google, lambda queue: queue.add(Entry.waiting_for(parse_query(TEAPOT), had=config.ON_DEMAND_MIN_THREADS,
                                                             backfill=True)))
    report = run(tmp_path, google, FakeGuard(yes=True), fake_archive=fake)
    assert fake.requests and report.threads_read == 3


def test_a_backfill_of_a_type_a_visitor_had_read_meanwhile_is_dropped_unread(tmp_path):
    # The code review: a visitor asking for the same product type with other need words doesn't take the backfill over;
    # the backfill was then read again right after the visitor's read. Now it is dropped, and backfill doesn't rest.
    google, guard = FakeGoogle(), FakeGuard(yes=True)
    queue_backfill(google)
    change(google, lambda queue: queue.add(entry_for(parse_query("teapot that keeps tea hot"), had=0)))
    report = run(tmp_path, google, guard)
    assert report.requests_read == ["teapot"] and guard.asked == []
    queue = the_queue(google)
    assert [e.backfill for e in queue.entries] == [False] and not queue.backfill_resting(NOW)


def test_backfills_last_read_starts_only_while_a_whole_run_still_fits_in_its_half():
    # The code review: a read counted at 21 minutes can take a run's whole 45, so backfill could pass its 42,000 and
    # leave visitors under their 50,000. Its last read now starts only while a whole run (its 50-minute lease) fits.
    longest = config.ON_DEMAND_LEASE_MINUTES * 60
    late = november(29.9)
    assert backfill_stop(used(ON_DEMAND_BACKFILL_SECONDS - longest, now=late), late) is None
    assert backfill_stop(used(ON_DEMAND_BACKFILL_SECONDS - longest + 1, now=late), late)[0] == "half"
    assert ON_DEMAND_BACKFILL_SECONDS + ON_DEMAND_GUARD_FREE_SECONDS <= ON_DEMAND_MONTH_SECONDS


def test_a_guard_rest_is_told_as_the_months_allowance():
    queue = Queue()
    queue.rest(NOW + timedelta(hours=6), "guard")
    # Changed on purpose 6 Nov 2026 (Noemi: "say up to 73"): the month is told "up to", the day still "about".
    assert on_demand.capacity_text(0, queue, NOW) == f"up to {on_demand.products_a_month()} a month"
    queue.rest(NOW + timedelta(hours=6), "gemini")
    assert on_demand.capacity_text(0, queue, NOW) == f"about {on_demand.products_a_day()} a day"


def test_no_guard_or_a_guard_that_breaks_is_a_no():
    assert not on_demand._ask(None, NOW, 0.0).yes and on_demand._ask(None, NOW, 0.0).failed

    class Broken:
        def allows(self, *args, **kwargs):
            raise RuntimeError("made-up")

    verdict = on_demand._ask(Broken(), NOW, 0.0)
    assert not verdict.yes and verdict.failed and "RuntimeError" in verdict.why


def test_the_reading_job_from_the_command_line_has_its_guard(monkeypatch):
    from engine import free_tier

    seen = {}

    def fake_run_job(bucket, library, archive, gemini, **kwargs):
        seen.update(kwargs)
        return types.SimpleNamespace(text=lambda: "report")

    monkeypatch.setenv(on_demand.BUCKET_VAR, NAME)
    monkeypatch.setenv(free_tier.PROJECT_VAR, "made-up-project")
    monkeypatch.setattr(on_demand, "run_job", fake_run_job)
    monkeypatch.setattr(on_demand, "reader_client", lambda: object())
    monkeypatch.setattr("engine.arctic_shift.ArcticShiftClient", lambda *a, **k: object())
    assert on_demand.main(["run"]) == 0
    assert isinstance(seen["guard"], free_tier.Guard) and seen["guard"].project == "made-up-project"


# Changed on purpose 6 Nov 2026 (fix round, from the cost review): backfill rested 6 hours after a no and an hour after
# a failed reading, and each time a rest ended the keep-warm ping started the paid job only for it to be refused
# again; now either rests backfill a day.
@pytest.mark.parametrize("failed, hours", [(False, config.ON_DEMAND_GUARD_BACKFILL_REST_HOURS),
                                          (True, config.ON_DEMAND_GUARD_BACKFILL_REST_HOURS)])
def test_a_guard_that_says_no_or_cant_read_stops_backfill_and_leaves_visitors_alone(tmp_path, failed, hours):
    assert config.ON_DEMAND_GUARD_BACKFILL_REST_HOURS == 24
    google, guard, fake = FakeGoogle(), FakeGuard(yes=False, failed=failed), FakeArchive()
    queue_backfill(google)
    report = run(tmp_path, google, guard, fake_archive=fake)
    assert fake.requests == [] and len(guard.asked) == 1
    queue = the_queue(google)
    assert queue.waiting() == [] and queue.entries == []  # put back: a later hour queues one again
    assert queue.backfill_resting_until == (NOW + timedelta(hours=hours)).isoformat()
    assert queue.resting_until is None  # visitors' reading doesn't rest
    assert any("guard" in note for note in report.notes)


def test_a_backfill_waits_for_a_visitor_who_comes_meanwhile(tmp_path):
    google, guard = FakeGoogle(), FakeGuard(yes=True)
    queue_backfill(google)
    change(google, lambda queue: queue.add(entry_for(parse_query(KETTLE), had=0)))
    report = run(tmp_path, google, guard)
    assert report.requests_read == ["electric kettle", "teapot"]  # queued after the backfill, read before it


def test_threads_waiting_for_gemini_go_visitors_first():
    queue = Queue()
    queue.add(thin(TEAPOT))
    visitor = entry_for(parse_query(KETTLE), had=0)
    queue.add(visitor)
    bundle = on_demand.Bundle({
        "1aaa": on_demand.Item(thread="{}", extraction=None, entry=thin(TEAPOT).key, product_type="teapot",
                               added_at=NOW.isoformat()),
        "1bbb": on_demand.Item(thread="{}", extraction=None, entry=visitor.key, product_type="electric kettle",
                               added_at=NOW.isoformat())})
    assert on_demand.waiting_for_gemini(bundle, queue) == ["1bbb", "1aaa"]


def test_visitors_first_50000_seconds_never_ask_the_guard(tmp_path):
    google, guard = FakeGoogle(), FakeGuard(yes=False)
    change(google, lambda queue: queue.add(entry_for(parse_query(TEAPOT), had=0)))
    change(google, lambda queue: queue.usage_now(NOW).update(seconds=ON_DEMAND_GUARD_FREE_SECONDS - 2_000))
    report = run(tmp_path, google, guard)
    assert guard.asked == [] and report.threads_read == 3


def test_backfills_seconds_never_count_against_visitors_first_50000(tmp_path):
    google, guard = FakeGoogle(), FakeGuard(yes=False)
    change(google, lambda queue: queue.add(entry_for(parse_query(TEAPOT), had=0)))
    change(google, lambda queue: queue.usage_now(NOW).update(seconds=60_000, backfill_seconds=20_000))
    report = run(tmp_path, google, guard)
    assert guard.asked == [] and report.threads_read == 3  # visitors' own 40,000 seconds


def test_a_visitor_read_past_the_first_50000_seconds_needs_the_guards_yes(tmp_path):
    google, guard, fake = FakeGoogle(), FakeGuard(yes=False), FakeArchive()
    change(google, lambda queue: queue.add(entry_for(parse_query(TEAPOT), had=0)))
    change(google, lambda queue: queue.usage_now(NOW).update(seconds=ON_DEMAND_GUARD_FREE_SECONDS))
    run(tmp_path, google, guard, fake_archive=fake)
    queue = the_queue(google)
    assert fake.requests == [] and queue.resting_why == "guard"
    assert queue.resting_until == (NOW + timedelta(hours=config.ON_DEMAND_GUARD_REST_HOURS)).isoformat()
    assert guard.asked[0]["reader_seconds"] >= ON_DEMAND_GUARD_FREE_SECONDS
    # Told honestly: the free allowance is used up for now.
    site = SiteReader(bucket(google), tmp_path / "site", clock=Ticks(), now=lambda: NOW)
    state = site.after_answer(types.SimpleNamespace(query=parse_query(TEAPOT), threads_available=0,
                                                    own_threads_available=0, newest_own_thread=None)).state
    assert state["message"] == ("We haven't read Reddit about teapots yet. It's on our list, but our free reading "
                                "allowance is used up for now: check back later today.")
    # The guard says yes: read.
    change(google, lambda queue: queue.rest(NOW - timedelta(seconds=1), "guard"))
    report = run(tmp_path, google, FakeGuard(yes=True))
    assert report.threads_read == 3


class SlowArchive(FakeArchive):
    """Arctic Shift taking 10 seconds a call, on the job's clock."""

    def __init__(self, ticks, **kwargs):
        super().__init__(**kwargs)
        self.ticks = ticks

    def __call__(self, url, headers):
        self.ticks.now += 10
        return super().__call__(url, headers)


class SlowGemini(FakeGemini):
    def __init__(self, ticks, **kwargs):
        super().__init__(**kwargs)
        self.ticks = ticks

    def __call__(self, url, headers, body):
        self.ticks.now += 20
        return super().__call__(url, headers, body)


def test_a_runs_time_is_split_between_visitors_and_backfill_by_what_each_took(tmp_path):
    google, guard, ticks = FakeGoogle(), FakeGuard(yes=True), Ticks()
    queue_backfill(google, KETTLE)  # nothing in the made-up archive: its searches only
    change(google, lambda queue: queue.add(entry_for(parse_query(TEAPOT), had=0)))
    report = run(tmp_path, google, guard, fake_archive=SlowArchive(ticks), fake_gemini=SlowGemini(ticks), ticks=ticks)
    queue = the_queue(google)
    assert queue.usage["seconds"] == pytest.approx(report.seconds + config.ON_DEMAND_START_SECONDS, abs=0.1)
    assert queue.usage["backfill_seconds"] == pytest.approx(report.backfill_seconds)
    assert 0 < report.backfill_seconds < report.seconds / 2  # the kettle's searches only; the teapot read and extracted
    assert report.backfill[0]["product_type"] == "electric kettle" and report.backfill[0]["gemini_calls"] == 0


def test_a_backfill_is_dropped_while_the_bundle_holds_150_threads(tmp_path):
    google, guard, fake = FakeGoogle(), FakeGuard(yes=True), FakeArchive()
    queue_backfill(google)
    items = {f"1x{n:03d}": on_demand.Item(thread="{}", extraction="{}", entry="kitchen/made-up/", product_type="made-up",
                                         added_at=NOW.isoformat()).as_json()
             for n in range(config.ON_DEMAND_BACKFILL_BUNDLE_THREADS)}
    google.put(NAME, "on_demand/threads.json", json.dumps({"version": 1, "threads": items}).encode())
    run(tmp_path, google, guard, fake_archive=fake)
    queue = the_queue(google)
    assert fake.requests == [] and guard.asked == [] and queue.backfill_resting_why == "bundle"
    assert queue.waiting() == []


# --- The site: the keep-warm ping queues it, visitors stay first ---

def a_site(tmp_path, google, ticks=None) -> SiteReader:
    site_bucket = Bucket(NAME, request=google, clock=lambda: 0.0, prefix=on_demand.PREFIX)
    return SiteReader(site_bucket, tmp_path / "site", job=JobStarter(JOB, site_bucket, request=google),
                      clock=ticks or Ticks(), now=lambda: NOW)


def test_the_keep_warm_ping_queues_a_backfill_at_most_hourly_and_starts_the_job(tmp_path):
    google, ticks = FakeGoogle(), Ticks()
    candidates = [made_up("made-up teapot"), made_up("made-up toaster")]
    change(google, lambda queue: with_candidates(queue, candidates))
    site = a_site(tmp_path, google, ticks)
    site.on_ping()
    [entry] = the_queue(google).waiting()
    assert entry.backfill and google.jobs_started == [JOB]
    change(google, lambda queue: queue.find(entry.key).finish(NOW, found=2))  # read
    ticks.now += 600
    site.on_ping()
    assert the_queue(google).waiting() == []  # not before the hour is up
    ticks.now += config.ON_DEMAND_BACKFILL_EVERY_SECONDS
    site.on_ping()
    [second] = the_queue(google).waiting()
    assert second.backfill and second.product_type != entry.product_type


def test_a_visitor_asking_about_a_product_backfill_waits_on_makes_it_theirs(tmp_path):
    google = FakeGoogle()
    queue_backfill(google)
    site = a_site(tmp_path, google)
    site.after_answer(types.SimpleNamespace(query=parse_query(TEAPOT), threads_available=0, own_threads_available=0,
                                            newest_own_thread=None))
    [entry] = the_queue(google).waiting()
    assert not entry.backfill  # a visitor's request now: read first, within visitors' month


def asked_teapot(tmp_path, google) -> dict:
    return a_site(tmp_path, google).after_answer(types.SimpleNamespace(
        query=parse_query(TEAPOT), threads_available=0, own_threads_available=0, newest_own_thread=None)).state


def test_a_backfill_read_in_progress_counts_as_one_request_ahead_in_the_told_wait(tmp_path):
    started = FakeGoogle()
    entry = queue_backfill(started, KETTLE)

    def in_progress(queue):
        queue.find(entry.key).started_at = NOW.isoformat()
        queue.take_lease(NOW - timedelta(minutes=2))

    change(started, in_progress)
    state = asked_teapot(tmp_path / "a", started)
    assert state["check_back_minutes"] == config.ON_DEMAND_FIRST_MINUTES + config.ON_DEMAND_EACH_MINUTES
    assert state["message"].endswith("check back in about 45 minutes.")
    waiting_only = FakeGoogle()
    queue_backfill(waiting_only, KETTLE)  # queued, not started: the visitor goes first
    assert asked_teapot(tmp_path / "b", waiting_only)["check_back_minutes"] == config.ON_DEMAND_FIRST_MINUTES


def test_a_full_queue_counts_visitors_only(tmp_path):
    google = FakeGoogle()
    queue_backfill(google, KETTLE)
    for n in range(config.ON_DEMAND_MAX_WAITING - 1):  # one place left for visitors, the backfill aside
        change(google, lambda queue, n=n: queue.add(Entry(key=f"kitchen/made-up visitor thing {n}/", category="kitchen",
                                                          product_type=f"made-up visitor thing {n}",
                                                          subreddits=["BuyItForLife"])))
    asked_teapot(tmp_path, google)
    assert the_queue(google).find(entry_for(parse_query(TEAPOT), had=0).key) is not None


# --- The daily pre-check lists the thin products and may queue one ---

def test_the_pre_check_lists_the_thin_answers_and_queues_one(tmp_path):
    library = kettle_library(tmp_path)
    found = precheck._work_out(["teapot for loose leaf tea", "electric kettle"], library, None, None)
    assert [(entry.product_type, entry.backfill) for entry in found.thin] == [("teapot", True)]  # 0 picks; the kettle 3
    google = FakeGoogle()
    queued = on_demand.precheck_backfill({on_demand.BUCKET_VAR: NAME}, found.thin, NOW, bucket=bucket(google))
    queue = the_queue(google)
    assert [c["product_type"] for c in queue.backfill["candidates"]] == ["teapot"]
    assert queue.backfill["day"] == "2026-10-09"
    assert queued.product_type == "teapot" and [e.key for e in queue.waiting()] == [queued.key]
    assert on_demand.precheck_backfill({}, found.thin, NOW) is None  # without the bucket, nothing


def test_the_plan_run_offers_its_thin_answers_unless_it_is_a_dry_run(tmp_path, monkeypatch):
    from engine.tests.test_precheck_plan import plan_run
    from engine.tests.test_live_check import Clock

    offered = []
    monkeypatch.setattr(precheck.on_demand, "precheck_backfill",
                        lambda environ, entries, now, bucket=None: offered.append([e.product_type for e in entries]))
    library = kettle_library(tmp_path)
    google = FakeGoogle(buckets=("credible-test-checks",))
    plan_run(tmp_path, google, Clock(), library, requests=("teapot for loose leaf tea", "electric kettle"))
    assert offered == [["teapot"]]
    plan_run(tmp_path, google, Clock(), library, requests=("teapot for loose leaf tea",), dry_run=True)
    assert offered == [["teapot"]]


def test_the_status_says_backfills_share_of_the_month():
    queue = Queue()
    queue.usage_now(NOW).update(seconds=7_200, backfill_seconds=3_600)
    text = on_demand.status_text(queue, NOW)
    assert f"This month: 2.0 h of {ON_DEMAND_MONTH_SECONDS / 3600:.1f} h (backfill 1.0 h of " in text


def test_an_older_queue_without_backfill_reads_as_visitors_requests_and_the_new_fields_are_kept():
    entry = thin(TEAPOT)
    entry.started_at = NOW.isoformat()
    queue = with_candidates(Queue(entries=[entry]), [made_up("made-up toaster")])
    queue.rest_backfill(NOW + timedelta(hours=1), "pace")
    queue.bundle_threads = 12
    again = Queue.from_json(queue.as_json())
    assert again.entries[0].backfill and again.entries[0].started_at == NOW.isoformat()
    assert (again.backfill, again.backfill_resting_why, again.bundle_threads) == (queue.backfill, "pace", 12)
    older = queue.as_json()
    for name in ("backfill", "backfill_resting_until", "backfill_resting_why", "bundle_threads"):
        del older[name]
    for data in older["entries"]:
        del data["backfill"], data["started_at"]
    old = Queue.from_json(older)
    assert not old.entries[0].backfill and old.backfill is None and old.bundle_threads == 0


def test_a_deploy_that_bakes_the_bundle_in_tells_the_queue_and_backfill_starts_again(tmp_path):
    google = FakeGoogle()
    items = {f"1y{n:03d}": on_demand.Item(thread="{}", extraction="{}", entry="kitchen/made-up/", product_type="made-up",
                                         added_at=NOW.isoformat()).as_json() for n in range(160)}
    google.put(NAME, "on_demand/threads.json", json.dumps({"version": 1, "threads": items}).encode())

    def full(queue):
        queue.bundle_threads = 160
        queue.rest_backfill(NOW + timedelta(days=1), "bundle")

    change(google, full)
    local = tmp_path / "noemis-library"
    for tid in list(items)[:150]:  # the image now holds 150 of them
        for folder in ("threads", "extracted"):
            (local / folder).mkdir(parents=True, exist_ok=True)
            (local / folder / f"{tid}.json").write_text("{}", encoding="utf-8")
    assert on_demand.forget_baked(bucket(google), local) == 150
    queue = the_queue(google)
    assert queue.bundle_threads == 10 and queue.backfill_resting_until is None and not queue.backfill_resting(NOW)


# --- Google's billing month: one cut at 08:00 UTC on the 1st (6 Nov 2026, the second cost review) ---
#
# Google's billing month runs on US Pacific time (Cloud Billing reports start a day at midnight US and Canadian Pacific
# Time), so it ends at 08:00 UTC on the 1st in winter and 07:00 in summer. The queue counted months from midnight UTC: a
# rest that woke then let the backlog read under visitors' fresh first 50,000 seconds, which never ask the guard, while
# Google still billed the old month (the reviewer's simulation: up to about 102% of the CPU part with the site at 2 GiB).
# The month now turns at one fixed cut, 08:00 UTC on the 1st, never earlier than Google's.

CUT = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)  # Google's December starts by then, summer or winter
LAST_EVENING = datetime(2026, 11, 30, 23, 0, tzinfo=UTC)


def a_visitor_waits(google, when: datetime, seconds: float, request: str = TEAPOT) -> None:
    change(google, lambda queue: queue.add(entry_for(parse_query(request), had=0)))
    change(google, lambda queue: queue.usage_now(when).update(seconds=seconds, backfill_seconds=0.0))


def test_the_queues_month_turns_at_08_00_utc_on_the_1st():
    queue = Queue()
    queue.usage_now(LAST_EVENING).update(seconds=91_000.0, backfill_seconds=30_000.0)
    before = queue.usage_now(CUT - timedelta(minutes=1))  # 07:59 UTC on the 1st: still Google's November
    assert (before["month"], before["seconds"], before["backfill_seconds"]) == ("2026-11", 91_000.0, 30_000.0)
    at = queue.usage_now(CUT)
    assert (at["month"], at["seconds"], at["backfill_seconds"]) == ("2026-12", 0.0, 0.0)


def test_a_queue_written_while_months_turned_at_midnight_utc_is_read_without_losing_its_seconds():
    # The queue in the bucket at deploy time was written by the code before this change. Mid-month its month is the
    # same either way, so nothing starts afresh. One written between midnight and 08:00 UTC on a 1st is a month ahead
    # of the billing month and keeps its seconds (they count in the month they were written for). A month that can't
    # be read starts afresh, as before.
    written = Queue(usage={"month": "2026-11", "seconds": 61_000.0, "backfill_seconds": 9_000.0,
                           "day": "2026-11-17", "gemini_calls": 120})
    read = Queue.from_json(json.loads(json.dumps(written.as_json())))
    usage = read.usage_now(datetime(2026, 11, 17, 12, 0, tzinfo=UTC))
    assert (usage["month"], usage["seconds"], usage["backfill_seconds"]) == ("2026-11", 61_000.0, 9_000.0)
    ahead = Queue(usage={"month": "2026-12", "seconds": 4_000.0, "backfill_seconds": 0.0})
    for when in (CUT - timedelta(hours=5), CUT, CUT + timedelta(days=1)):
        assert ahead.usage_now(when)["seconds"] == 4_000.0
    for unreadable in (None, "", "2026-1", "soon", 202611, {"month": 11}):
        assert Queue(usage={"month": unreadable, "seconds": 5.0}).usage_now(CUT)["seconds"] == 0.0


@pytest.mark.parametrize("left_by", ["month", "guard"])
def test_a_backlog_left_late_on_the_last_day_is_read_only_once_googles_month_has_ended(tmp_path, left_by):
    google, fake, guard = FakeGoogle(), FakeArchive(), FakeGuard(yes=False)
    a_visitor_waits(google, LAST_EVENING,
                    ON_DEMAND_MONTH_SECONDS - 10 if left_by == "month" else ON_DEMAND_GUARD_FREE_SECONDS)
    run(tmp_path, google, guard, fake_archive=fake, now=LAST_EVENING)
    queue = the_queue(google)
    assert queue.resting_why == left_by and fake.requests == []
    if left_by == "month":
        assert queue.resting_until == CUT.isoformat()
    # 00:30 UTC on the 1st: Google still bills November, so nothing is read under December's fresh seconds.
    assert not run(tmp_path, google, guard, fake_archive=fake, now=CUT - timedelta(hours=7, minutes=30)).ran
    assert fake.requests == []
    if left_by == "guard":
        # Its 6 hours end at 05:00, still November's: past visitors' first seconds the guard is asked again, and its no
        # rests reading until the cut, never past it.
        run(tmp_path, google, guard, fake_archive=fake, now=CUT - timedelta(hours=2, minutes=30))
        assert fake.requests == [] and the_queue(google).resting_until == CUT.isoformat()
    asked = len(guard.asked)
    # After 08:00 UTC it is December's: the request is read within visitors' fresh first seconds, the guard not asked.
    report = run(tmp_path, google, guard, fake_archive=fake, now=CUT + timedelta(minutes=30))
    assert report.requests_read == ["teapot"] and fake.requests and len(guard.asked) == asked
    assert the_queue(google).usage["month"] == "2026-12"


def test_backfill_is_paced_from_08_00_utc_on_the_1st():
    # In the cut's first minutes backfill has no share yet, and its share grows from the cut. A moment before the cut is
    # still November's, with November's room.
    soon = CUT + timedelta(minutes=5)
    why, until = backfill_stop(used(0, now=soon), soon)
    assert why == "pace" and until == CUT + timedelta(days=31 * PRODUCT_SECONDS / ON_DEMAND_BACKFILL_SECONDS)
    before = CUT - timedelta(minutes=5)
    assert backfill_stop(used(ON_DEMAND_BACKFILL_SECONDS // 2, now=before), before) is None


# --- Tests the second code review found missing (6 Nov 2026): correct code that no test held ---

def test_a_refused_backfill_a_visitor_took_over_meanwhile_stays_the_visitors(tmp_path):
    # The refused backfill is taken off the queue only while it is still a backfill: a visitor who asked for the same
    # product while the guard was being asked keeps their request.
    google = FakeGoogle()
    queue_backfill(google)

    class TakenOver(FakeGuard):
        def allows(self, now, extra_seconds=PRODUCT_SECONDS, reader_seconds=0.0):
            change(google, lambda queue: queue.add(entry_for(parse_query(TEAPOT), had=0)))  # a visitor asks meanwhile
            return super().allows(now, extra_seconds, reader_seconds)

    run(tmp_path, google, TakenOver(yes=False))
    queue = the_queue(google)
    [entry] = queue.entries
    assert entry.status == "waiting" and not entry.backfill and queue.backfill_resting_why == "guard"


def test_a_visitor_read_past_the_first_50000_seconds_asks_the_guard_about_one_reads_21_minutes(tmp_path):
    google, guard = FakeGoogle(), FakeGuard(yes=False)
    a_visitor_waits(google, NOW, ON_DEMAND_GUARD_FREE_SECONDS)
    run(tmp_path, google, guard)
    assert [asked["extra_seconds"] for asked in guard.asked] == [PRODUCT_SECONDS] == [1_260]


def test_only_a_backfill_begun_in_this_run_counts_in_a_visitors_told_wait():
    queue = Queue()
    entry = queue.add(thin(TEAPOT))
    entry.started_at = (NOW - timedelta(minutes=1)).isoformat()  # begun by an earlier run, cut short
    assert queue.take_lease(NOW)
    assert not on_demand.backfill_in_progress(queue, NOW + timedelta(minutes=5))
    entry.started_at = NOW.isoformat()  # begun by the run holding the queue
    assert on_demand.backfill_in_progress(queue, NOW + timedelta(minutes=5))


def test_this_runs_backfill_seconds_never_count_as_visitors(tmp_path):
    # A visitor who asks while a backfill is read: the run's seconds so far are backfill's, so the visitor's 49,530 stay
    # under their first 50,000 and they don't ask the guard (counted as theirs, it would be 50,330).
    google, ticks, guard = FakeGoogle(), Ticks(), FakeGuard(yes=True)
    queue_backfill(google)
    change(google, lambda queue: queue.usage_now(NOW).update(seconds=49_500.0, backfill_seconds=0.0))

    class Slow(FakeArchive):
        def __call__(self, url, headers):
            if not self.requests:  # the backfill's first search takes 800 s, and a visitor asks meanwhile
                ticks.now += 800
                change(google, lambda queue: queue.add(entry_for(parse_query(KETTLE), had=0)))
            return super().__call__(url, headers)

    report = run(tmp_path, google, guard, fake_archive=Slow(), ticks=ticks)
    assert report.backfill_seconds >= 800 and report.requests_read == ["teapot", "electric kettle"]
    assert len(guard.asked) == 1 and guard.asked[0]["extra_seconds"] == PRODUCT_SECONDS + 470  # the backfill's only


def test_a_backfill_queued_before_backfill_began_resting_is_dropped_unread_and_the_rest_kept(tmp_path):
    google, guard, fake = FakeGoogle(), FakeGuard(yes=True), FakeArchive()
    queue_backfill(google)
    until = NOW + timedelta(hours=3)
    change(google, lambda queue: queue.rest_backfill(until, "pace"))
    run(tmp_path, google, guard, fake_archive=fake)
    queue = the_queue(google)
    assert queue.entries == [] and guard.asked == [] and fake.requests == []
    assert (queue.backfill_resting_until, queue.backfill_resting_why) == (until.isoformat(), "pace")
