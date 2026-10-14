"""On-demand reading's job (Noemi's plan of 14 Oct 2026, part 3): for each request waiting in the queue it finds threads
with Arctic Shift's free title search and reads them from its archive (the library's own archive reader: no Bright Data,
no Parse), Gemini extracts them within its free allowance, the extraction's own checks run (every quote word for word),
the threads are slimmed when the lean library is there, and threads and extractions go into one bundle in the bucket.

Every service is a made-up stand-in (engine/tests/on_demand_fakes.py, fake_google.py): no test reaches the network.
"""

import json
import sys
import types
from datetime import timedelta

import pytest

from engine import on_demand
from engine.config import ON_DEMAND_GEMINI_CALLS_A_DAY, ON_DEMAND_MAX_TRIES, ON_DEMAND_MONTH_SECONDS
from engine.extract import Extraction, check_extraction
from engine.live_check import Bucket
from engine.models import Thread
from engine.on_demand import Bundle, Queue, QueueStore, entry_for, run_job
from engine.query import parse_query
from engine.tests.fake_google import FakeGoogle
from engine.tests.on_demand_fakes import MISQUOTED, NOW, TEAPOT_THREADS, FakeArchive, FakeGemini, Ticks, archive, gemini
from engine.tests.test_web import kettle_library

NAME = "credible-test-on-demand"
QUEUE, THREADS = "on_demand/queue.json", "on_demand/threads.json"
TEAPOT = "teapot for loose leaf tea"


def bucket(google) -> Bucket:
    return Bucket(NAME, request=google, clock=lambda: 0.0, prefix=on_demand.PREFIX)


def queued(google, *requests, had=0) -> None:
    """The site has queued these requests."""
    for request in requests:
        entry = entry_for(parse_query(request), had=had)
        QueueStore(bucket(google)).change(lambda queue, entry=entry: queue.add(entry) and None)


def the_library(tmp_path):
    """The site's baked library (two kettle threads), made once per test."""
    return tmp_path / "library" if (tmp_path / "library").is_dir() else kettle_library(tmp_path)


def run(tmp_path, google, fake_archive=None, fake_gemini=None, now=NOW, ticks=None):
    return run_job(bucket(google), the_library(tmp_path), archive(tmp_path, fake_archive or FakeArchive()),
                   gemini(fake_gemini or FakeGemini()), now=lambda: now, clock=ticks or Ticks(),
                   work_dir=tmp_path / "work")


def the_queue(google) -> Queue:
    return Queue.from_json(google.read(NAME, QUEUE))


def the_bundle(google) -> Bundle:
    return Bundle.from_json(google.read(NAME, THREADS))


def test_a_waiting_request_is_read_extracted_checked_and_bundled(tmp_path):
    google = FakeGoogle()
    queued(google, TEAPOT)
    report = run(tmp_path, google)
    bundle = the_bundle(google)
    assert sorted(bundle.threads) == sorted(TEAPOT_THREADS)  # found by the archive's title search, read from it
    for tid, item in bundle.threads.items():
        thread = Thread.model_validate_json(item.thread)
        assert thread.read_from == "arctic_shift" and item.product_type == "teapot"
        extraction = Extraction.model_validate_json(item.extraction)
        assert extraction.extractor == "gemini:gemini-test" and extraction.thread_id == tid
        checked = check_extraction(extraction, thread)  # the extraction workflow's own word-for-word check
        assert all(m.comment_id != MISQUOTED[0] for m in checked.kept)
    [entry] = the_queue(google).entries
    assert entry.status == "done" and entry.found == 3 and entry.read_again_after
    assert report.threads_read == 3 and report.extracted == 3 and report.quotes_dropped == 1  # the misquote
    assert report.quotes_kept == 9 and report.requests_done == ["teapot"]  # 10 mentions, the misquote dropped
    queue = the_queue(google)
    assert queue.lease_until is None and queue.usage["seconds"] > 0  # let go of, its time counted
    assert queue.usage["gemini_calls"] == 3


def test_the_report_says_counts_and_product_types_only(tmp_path):
    google = FakeGoogle()
    queued(google, TEAPOT)
    text = run(tmp_path, google).text() + json.dumps(the_queue(google).last_run)
    for _, (_, title, comments) in TEAPOT_THREADS.items():
        assert title not in text and not any(body in text for _, body, _ in comments)
    assert "teapot" in text


def test_threads_already_in_the_library_or_the_bundle_are_never_read_again(tmp_path):
    google = FakeGoogle()
    google.put(NAME, THREADS, json.dumps(Bundle({"1tea001": on_demand.Item(
        thread="{}", extraction="{}", entry="kitchen/teapot/", product_type="teapot",
        added_at=NOW.isoformat())}).as_json()).encode())
    library = the_library(tmp_path)
    (library / "threads" / "1tea002.json").write_text("{}", encoding="utf-8")  # baked into the image already
    queued(google, TEAPOT)
    fake = FakeArchive()
    run(tmp_path, google, fake_archive=fake)
    assert sorted(the_bundle(google).threads) == ["1tea001", "1tea003"]
    assert not any("ids=1tea001" in url or "ids=1tea002" in url for url in fake.requests)


def test_the_daily_limit_rests_the_queue_and_the_next_day_extracts_without_reading_again(tmp_path):
    google = FakeGoogle()
    queued(google, TEAPOT)
    report = run(tmp_path, google, fake_gemini=FakeGemini(daily_limit_after=1))
    bundle = the_bundle(google)
    assert len(bundle.threads) == 3 and len(bundle.extracted()) == 1  # read once; two wait for Gemini
    queue = the_queue(google)
    assert queue.resting_why == "gemini" and queue.find(queue.entries[0].key).status == "waiting"
    reset = on_demand.next_gemini_reset(NOW)
    assert queue.resting_until == reset.isoformat() and reset > NOW and reset.hour == 8
    assert "gemini" in report.resting
    assert run(tmp_path, google, now=NOW + timedelta(hours=1)).ran is False  # still resting: nothing asked
    fake = FakeArchive()
    tomorrow = run(tmp_path, google, fake_archive=fake, now=reset + timedelta(minutes=1))
    assert tomorrow.extracted == 2 and fake.requests == []  # the archive isn't asked again
    assert len(the_bundle(google).extracted()) == 3 and the_queue(google).entries[0].status == "done"


def test_our_own_daily_share_of_gemini_is_never_passed(tmp_path):
    google = FakeGoogle()
    queued(google, TEAPOT)
    store = QueueStore(bucket(google))
    store.change(lambda q: q.usage_now(NOW).update(gemini_calls=ON_DEMAND_GEMINI_CALLS_A_DAY - 1) and None)
    fake = FakeGemini()
    run(tmp_path, google, fake_gemini=fake)
    assert fake.calls == 1 and the_queue(google).resting_why == "gemini"


def test_the_months_time_is_never_passed(tmp_path):
    google = FakeGoogle()
    queued(google, TEAPOT)
    QueueStore(bucket(google)).change(
        lambda q: q.usage_now(NOW).update(seconds=ON_DEMAND_MONTH_SECONDS - 10) and None)
    fake = FakeArchive()
    run(tmp_path, google, fake_archive=fake)
    queue = the_queue(google)
    assert fake.requests == [] and queue.resting_why == "month"
    assert queue.resting_until == "2026-11-01T00:00:00+00:00"


def test_one_run_at_a_time(tmp_path):
    google = FakeGoogle()
    queued(google, TEAPOT)
    QueueStore(bucket(google)).change(lambda q: q.take_lease(NOW - timedelta(minutes=5)) and None)
    fake = FakeArchive()
    report = run(tmp_path, google, fake_archive=fake)
    assert not report.ran and "another run" in report.why_not and fake.requests == []
    assert the_queue(google).lease_until is not None  # the other run's lease is left alone


def test_an_archive_that_is_down_is_tried_again_later_then_set_aside_for_a_day(tmp_path):
    google = FakeGoogle()
    queued(google, TEAPOT)
    moment = NOW
    for attempt in range(ON_DEMAND_MAX_TRIES):
        run(tmp_path, google, fake_archive=FakeArchive(down=True), now=moment)
        moment += timedelta(minutes=61)
    [entry] = the_queue(google).entries
    assert entry.status == "done" and entry.found == 0 and entry.tries == ON_DEMAND_MAX_TRIES
    assert entry.due_again(moment + timedelta(days=1))


def test_a_request_whose_library_has_enough_threads_by_now_isnt_read(tmp_path):
    google = FakeGoogle()
    queued(google, TEAPOT)  # read once
    run(tmp_path, google)
    queued(google, "teapot that keeps tea hot", had=3)  # another need, asked meanwhile: 3 baked + 3 read now
    fake = FakeArchive()
    run(tmp_path, google, fake_archive=fake)
    assert fake.requests == [] and all(e.status == "done" for e in the_queue(google).entries)


def test_a_run_starts_no_new_reading_once_its_time_is_up(tmp_path, monkeypatch):
    google = FakeGoogle()
    queued(google, TEAPOT, "stovetop kettle that whistles")
    ticks = Ticks()
    real = on_demand._read_entry

    def slow_reading(*args, **kwargs):
        real(*args, **kwargs)
        ticks.now += 16 * 60  # a reading that took 16 minutes

    monkeypatch.setattr(on_demand, "_read_entry", slow_reading)
    report = run(tmp_path, google, ticks=ticks)
    assert report.requests_read == ["teapot"]  # the kettle waits for the next run
    assert [e.status for e in the_queue(google).entries] == ["done", "waiting"]


def test_without_the_lean_library_threads_are_kept_whole_and_it_says_so(tmp_path):
    google = FakeGoogle()
    queued(google, TEAPOT)
    report = run(tmp_path, google)
    assert report.whole == 3 and report.slimmed == 0 and any("engine.slim" in note for note in report.notes)
    assert not any(item.slimmed for item in the_bundle(google).threads.values())


def test_with_the_lean_library_threads_keep_only_the_comments_answers_use(tmp_path, monkeypatch):
    calls = []
    fake = types.ModuleType("engine.slim")
    fake.known_types = lambda library_dir: ("electric kettle",)
    fake.slim_thread = lambda thread, extraction, kinds, now: (calls.append(kinds), thread)[1]
    fake.differences = lambda whole, slimmed, extraction, kinds: []
    fake.thread_json = lambda thread: b'{"slimmed": "copy"}'
    monkeypatch.setitem(sys.modules, "engine.slim", fake)
    google = FakeGoogle()
    queued(google, TEAPOT)
    report = run(tmp_path, google)
    assert report.slimmed == 3 and report.whole == 0
    assert all(item.slimmed and item.thread == '{"slimmed": "copy"}' for item in the_bundle(google).threads.values())
    assert calls[0] == ("electric kettle", "teapot")  # the request's own type is looked for in the words dropped


def test_a_slimmed_copy_that_would_read_differently_stays_whole(tmp_path, monkeypatch):
    fake = types.ModuleType("engine.slim")
    fake.known_types = lambda library_dir: ()
    fake.slim_thread = lambda thread, extraction, kinds, now: thread
    fake.differences = lambda whole, slimmed, extraction, kinds: ["the extraction's checks"]
    fake.thread_json = lambda thread: pytest.fail("never written")
    monkeypatch.setitem(sys.modules, "engine.slim", fake)
    google = FakeGoogle()
    queued(google, TEAPOT)
    assert run(tmp_path, google).whole == 3


def test_the_bundle_never_loses_a_change_made_meanwhile(tmp_path):
    google = FakeGoogle()
    queued(google, TEAPOT)
    google.put(NAME, THREADS, json.dumps(Bundle({"1old001": on_demand.Item(
        thread="{}", extraction="{}", entry="kitchen/kettle/", product_type="electric kettle",
        added_at=NOW.isoformat())}).as_json()).encode())

    def a_deploy_lets_go_of_a_baked_thread():
        stored = Bundle.from_json(google.read(NAME, THREADS))
        stored.threads.pop("1old001")
        google.put(NAME, THREADS, json.dumps(stored.as_json()).encode())

    # Between the job's read of the bundle and its first write of it: its write fails (412), and it is redone over the
    # new version.
    google.before_writing[THREADS] = a_deploy_lets_go_of_a_baked_thread
    run(tmp_path, google)
    assert sorted(the_bundle(google).threads) == sorted(TEAPOT_THREADS)
    assert len(the_bundle(google).extracted()) == 3


def test_a_run_with_nothing_waiting_writes_nothing(tmp_path):
    google = FakeGoogle()
    report = run(tmp_path, google)
    assert not report.ran and "nothing waits" in report.why_not
    assert google.asked("POST") == []


def test_threads_in_the_bundle_past_the_archives_keeping_time_are_let_go(tmp_path):
    from engine.config import ARCHIVE_TEXT_KEPT_DAYS

    google = FakeGoogle()
    old = (NOW - timedelta(days=ARCHIVE_TEXT_KEPT_DAYS + 1)).isoformat()
    google.put(NAME, THREADS, json.dumps(Bundle({
        "1old001": on_demand.Item(thread="{}", extraction="{}", entry="kitchen/teapot/", product_type="teapot",
                                  added_at=old),
        "1new001": on_demand.Item(thread="{}", extraction="{}", entry="kitchen/teapot/", product_type="teapot",
                                  added_at=NOW.isoformat())}).as_json()).encode())
    queued(google, "stovetop kettle that whistles")
    run(tmp_path, google, fake_archive=FakeArchive(threads=()))
    assert "1old001" not in the_bundle(google).threads and "1new001" in the_bundle(google).threads


def test_a_waiting_thread_that_cant_be_read_is_let_go_and_the_run_goes_on(tmp_path):
    google = FakeGoogle()
    queued(google, TEAPOT)
    entry_key = the_queue(google).entries[0].key
    google.put(NAME, THREADS, json.dumps(Bundle({"1bad001": on_demand.Item(
        thread="not a thread", extraction=None, entry=entry_key, product_type="teapot",
        added_at=NOW.isoformat())}).as_json()).encode())
    report = run(tmp_path, google)
    bundle = the_bundle(google)
    assert "1bad001" not in bundle.threads and len(bundle.extracted()) == 3 and report.extracted == 3
    assert the_queue(google).entries[0].status == "done"
