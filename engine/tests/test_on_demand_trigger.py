"""When on-demand reading starts (Noemi's decision (l) of 19 Oct 2026: it comes back on with a cheaper reader; the
breadth-first review of 16 Oct 2026, docs/bfs-2026-10-16/reading.md, R1 and R2): the bar of 6 threads counts only the
threads about the type, never threads titled as another type (a moisturiser had 51 of 102, a saucepan 30 of 50), and a
fast-moving type (laptops, headphones) whose threads are all old is read again for newer ones, since a 2019 laptop is
no recommendation.

Every text is made up; every service is a stand-in (engine/tests/fake_google.py, on_demand_fakes.py): no test reaches
the network.
"""

import json
import types
from datetime import timedelta

from engine import config, on_demand
from engine.config import FAST_MOVING_TYPES, ON_DEMAND_MIN_THREADS, ON_DEMAND_OLD_YEARS
from engine.live_check import Bucket
from engine.on_demand import Entry, JobStarter, Queue, QueueStore, SiteReader, entry_for, run_job
from engine.pipeline import answer_request
from engine.query import parse_query
from engine.tests.factories import make_thread, write_gold
from engine.tests.fake_google import FakeGoogle
from engine.tests.on_demand_fakes import NOW, FakeArchive, FakeGemini, Ticks, archive, gemini
from engine.tests.test_on_demand_job import the_library
from engine.tests.test_pipeline import REQUEST, comment, mention

NAME = "credible-test-on-demand"
JOB = "projects/credible-picks/locations/europe-west1/jobs/credible-recs-reader"
QUEUE = "on_demand/queue.json"
YEAR = timedelta(days=365)


def mixed_library(tmp_path, kettles: int, toasters: int):
    """`kettles` threads about kettles and `toasters` threads titled as toasters whose posts also name a kettle (so they
    are read for a kettle request, last), each with one extracted mention."""
    threads, extractions = [], {}
    for kind, count, title, body, posted in (
            ("kett", kettles, "Which electric kettle lasts?", "My kettle died again.", "2026-03-01T09:00:00Z"),
            ("toas", toasters, "Which toaster is worth buying?", "My kettle died too.", "2026-04-01T09:00:00Z")):
        for n in range(count):
            tid, cid = f"1{kind}{n:02d}", f"c{kind}{n:02d}"
            text = f"My Zojirushi kettle has lasted {n + 4} years and still boils perfectly."
            threads.append(make_thread(
                id=tid, community="BuyItForLife", category="kitchen", title=title, body=body,
                url=f"https://www.reddit.com/r/BuyItForLife/comments/{tid}/x/", created_at=posted,
                comments=[comment(cid, tid, text, created_at=posted)]))
            extractions[tid] = [mention(cid, "Zojirushi kettle", text)]
    root = write_gold(tmp_path / "library", threads, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for tid, mentions in extractions.items():
        (root / "extracted" / f"{tid}.json").write_text(json.dumps({
            "thread_id": tid, "instructions_version": "extract-v5", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions}), encoding="utf-8")
    return root


# --- What an answer counts ---

def test_an_answer_counts_the_threads_about_the_type_apart_from_those_titled_as_another(tmp_path):
    result = answer_request(REQUEST, library_dir=mixed_library(tmp_path, kettles=2, toasters=3))
    assert result.threads_available == 5  # module 2 reads the toaster threads too, last: their posts name a kettle
    assert result.own_threads_available == 2  # only these are about kettles
    assert result.newest_own_thread is not None and result.newest_own_thread.year == 2026


def test_a_library_with_no_thread_about_the_type_counts_none(tmp_path):
    result = answer_request(REQUEST, library_dir=mixed_library(tmp_path, kettles=0, toasters=3))
    assert result.own_threads_available == 0 and result.newest_own_thread is None


# --- The site's bar ---

def reader(tmp_path, google=None) -> SiteReader:
    google = google or FakeGoogle()
    bucket = Bucket(NAME, request=google, clock=lambda: 0.0, prefix=on_demand.PREFIX)
    return SiteReader(bucket, tmp_path / "site", job=JobStarter(JOB, bucket, request=google), clock=Ticks(),
                      now=lambda: NOW)


def answered(request: str, threads: int, own: int, newest=None):
    """What the pipeline hands the site: module 1's reading of `request` and the counts of the answer."""
    return types.SimpleNamespace(query=parse_query(request), threads_available=threads, own_threads_available=own,
                                 newest_own_thread=newest)


def queue_of(site: SiteReader) -> Queue:
    return site.store.read()[0]


def test_threads_titled_as_another_type_dont_lift_a_product_over_the_bar(tmp_path):
    # R2: nine threads were read for teapots, but six of them are titled as other products (a kettle, a pot): three
    # teapot threads is a thin library.
    site = reader(tmp_path)
    outcome = site.after_answer(answered("teapot for loose leaf tea", threads=9, own=3))
    assert outcome.state is not None and outcome.state["state"] == "reading" and outcome.remember is False
    [entry] = queue_of(site).waiting()
    assert (entry.product_type, entry.had, entry.refresh) == ("teapot", 3, False)


def test_enough_threads_about_the_type_cost_no_call(tmp_path):
    google = FakeGoogle()
    site = reader(tmp_path, google)
    outcome = site.after_answer(answered("teapot for loose leaf tea", threads=9, own=ON_DEMAND_MIN_THREADS))
    assert outcome == on_demand.Outcome() and not google.calls


def test_a_fast_moving_type_whose_threads_are_old_is_read_again_for_newer_ones(tmp_path):
    # R1: every laptop thread of the library is from 2023 or older; "newest first" had nothing new to read.
    assert "laptop" in FAST_MOVING_TYPES
    site = reader(tmp_path)
    old = NOW - (ON_DEMAND_OLD_YEARS + 1) * YEAR
    outcome = site.after_answer(answered("laptop for university", threads=14, own=8, newest=old))
    assert outcome.state is not None and outcome.state["state"] == "reading"
    assert outcome.state["about"] == "laptops" and outcome.state["read_before"] is True
    [entry] = queue_of(site).waiting()
    assert (entry.product_type, entry.had, entry.refresh) == ("laptop", 8, True)


def test_a_fast_moving_type_with_a_recent_thread_is_left_alone(tmp_path):
    google = FakeGoogle()
    site = reader(tmp_path, google)
    recent = NOW - (ON_DEMAND_OLD_YEARS - 1) * YEAR
    assert site.after_answer(answered("laptop for university", threads=14, own=8, newest=recent)) == on_demand.Outcome()
    assert not google.calls


def test_a_type_that_isnt_fast_moving_is_never_read_again_for_being_old(tmp_path):
    google = FakeGoogle()
    site = reader(tmp_path, google)
    assert "teapot" not in FAST_MOVING_TYPES
    outcome = site.after_answer(answered("teapot for loose leaf tea", threads=9, own=8, newest=NOW - 6 * YEAR))
    assert outcome == on_demand.Outcome() and not google.calls


def test_the_age_that_calls_a_fast_moving_types_threads_old_comes_before_the_evidence_rule():
    # PROPOSED (the review's "over 2 years old"): older than this a fast-moving type is read again, well before
    # config.FAST_MOVING_OLD_EVIDENCE_YEARS stops old comments counting for or against a product.
    assert ON_DEMAND_OLD_YEARS == 2 and ON_DEMAND_OLD_YEARS < config.FAST_MOVING_OLD_EVIDENCE_YEARS


# --- The job ---

def queue_entry(google, request: str, had: int, refresh: bool) -> None:
    entry = entry_for(parse_query(request), had=had, refresh=refresh)
    QueueStore(Bucket(NAME, request=google, clock=lambda: 0.0, prefix=on_demand.PREFIX)).change(
        lambda queue: queue.add(entry) and None)


def run(tmp_path, google, fake_archive):
    return run_job(Bucket(NAME, request=google, clock=lambda: 0.0, prefix=on_demand.PREFIX), the_library(tmp_path),
                   archive(tmp_path, fake_archive), gemini(FakeGemini()), now=lambda: NOW, clock=Ticks(),
                   work_dir=tmp_path / "work")


class OldArchive(FakeArchive):
    """An archive whose threads were all posted in March 2023: nothing newer to read."""

    def _post(self, thread_id):
        return super()._post(thread_id) | {"created_utc": 1_678_000_000}


def test_a_request_to_read_again_is_read_although_its_library_has_enough_threads(tmp_path):
    google = FakeGoogle()
    queue_entry(google, "teapot for loose leaf tea", had=ON_DEMAND_MIN_THREADS + 2, refresh=True)
    fake = FakeArchive()  # its threads were posted in 2025: newer than the two years
    report = run(tmp_path, google, fake)
    assert fake.searches() > 0 and report.threads_read == 3


def test_a_request_to_read_again_reads_only_threads_newer_than_the_ones_called_old(tmp_path):
    google = FakeGoogle()
    queue_entry(google, "teapot for loose leaf tea", had=ON_DEMAND_MIN_THREADS + 2, refresh=True)
    report = run(tmp_path, google, OldArchive())
    assert report.threads_read == 0 and report.gemini_calls == 0
    [entry] = Queue.from_json(google.read(NAME, QUEUE)).entries
    assert entry.status == "done" and entry.found == 0


def test_an_ordinary_request_with_enough_threads_is_still_not_read(tmp_path):
    google = FakeGoogle()
    queue_entry(google, "teapot for loose leaf tea", had=ON_DEMAND_MIN_THREADS + 2, refresh=False)
    fake = FakeArchive()
    run(tmp_path, google, fake)
    assert fake.requests == []


def test_the_field_is_saved_and_an_older_queue_without_it_reads_as_a_thin_librarys():
    entry = entry_for(parse_query("laptop for university"), had=8, refresh=True)
    assert Entry.from_json(entry.as_json()).refresh is True
    without = entry.as_json()
    del without["refresh"]
    assert Entry.from_json(without).refresh is False
