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
    """`day` days into November 2026 (30 days)."""
    return datetime(2026, 11, 1, tzinfo=UTC) + timedelta(days=day)


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
    assert why == "month" and until == datetime(2026, 12, 1, tzinfo=UTC)


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
    assert len(guard.asked) == 1 and guard.asked[0]["extra_seconds"] == PRODUCT_SECONDS
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


@pytest.mark.parametrize("failed, hours", [(False, config.ON_DEMAND_GUARD_REST_HOURS),
                                          (True, config.ON_DEMAND_GUARD_FAILED_MINUTES / 60)])
def test_a_guard_that_says_no_or_cant_read_stops_backfill_and_leaves_visitors_alone(tmp_path, failed, hours):
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
