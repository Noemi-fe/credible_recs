"""On-demand reading on the site (Noemi's plan of 14 Oct 2026, part 3): a request module 1 understands, about a product
the library has too few threads about, is queued and the reading job started; the answer says so in plain words and
isn't remembered; the threads the job reads come into the site's library folder (as it gets ready, and at the
keep-warm ping), and the next ask answers with them.

Every service is a made-up stand-in (engine/tests/fake_google.py, on_demand_fakes.py): no test reaches the network.
"""

import json
import threading
from datetime import timedelta
from urllib.parse import quote

import pytest

from engine import on_demand, web
from engine.config import ARCHIVE_TEXT_KEPT_DAYS, ON_DEMAND_LATE_MINUTES, ON_DEMAND_MAX_WAITING
from engine.live_check import BUNDLE_RELOAD_SECONDS, Bucket
from engine.on_demand import Bundle, JobStarter, Queue, QueueStore, SiteReader, entry_for, run_job
from engine.query import parse_query
from engine.tests.fake_google import FakeGoogle
from engine.live_check import LiveChecker
from engine.tests.on_demand_fakes import NOW, FakeArchive, FakeEmbed, FakeGemini, Ticks, archive, body_of, gemini
from engine.tests.test_live_check import Clock
from engine.verify_quotes import find_quote
from engine.tests.test_web import REQUEST, kettle_library

NAME = "credible-test-on-demand"
JOB = "projects/credible-picks/locations/europe-west1/jobs/credible-recs-reader"
QUEUE, THREADS = "on_demand/queue.json", "on_demand/threads.json"
TEAPOT = "teapot for loose leaf tea"


class Site:
    """The site with on-demand reading on: its library (two kettle threads, enough for kettles here: min_threads=2),
    the bucket and the job's start on a stand-in, and clocks the test moves."""

    def __init__(self, tmp_path, monkeypatch, google=None):
        self.tmp_path = tmp_path
        self.library = kettle_library(tmp_path)
        self.google = google or FakeGoogle()
        self.ticks, self.now = Ticks(), NOW
        self.bucket = Bucket(NAME, request=self.google, clock=lambda: 0.0, prefix=on_demand.PREFIX)
        self.reader = SiteReader(self.bucket, self.library, job=JobStarter(JOB, self.bucket, request=self.google),
                                 clock=self.ticks, now=lambda: self.now, min_threads=2)
        monkeypatch.setattr(web, "on_demand", self.reader)

    def ask(self, request: str) -> dict:
        status, _, body = web.handle_request(f"/api/answer?q={quote(request)}", self.library)
        assert status == 200
        return json.loads(body)

    def queue(self) -> Queue:
        return Queue.from_json(self.google.read(NAME, QUEUE))

    def job_reads(self, fake_gemini=None) -> None:
        """The reading job runs once, as Cloud Run would run it, on a copy of the image's library."""
        run_job(Bucket(NAME, request=self.google, clock=lambda: 0.0, prefix=on_demand.PREFIX), self.library,
                archive(self.tmp_path, FakeArchive()), gemini(fake_gemini or FakeGemini()), now=lambda: self.now,
                clock=Ticks(), work_dir=self.tmp_path / "work")


@pytest.fixture(autouse=True)
def fresh_answers(monkeypatch):
    web.clear_answer_cache()
    monkeypatch.setattr(web, "ready", threading.Event())
    yield
    web.clear_answer_cache()


def test_a_request_the_library_hasnt_read_about_is_queued_and_the_answer_says_so(tmp_path, monkeypatch):
    site = Site(tmp_path, monkeypatch)
    data = site.ask(TEAPOT)
    assert data["query"]["product_type"] == "teapot" and data["answer"]["picks"] == []
    assert data["on_demand"] == {
        "state": "reading", "product_type": "teapot", "about": "teapots", "read_before": False,
        "check_back_minutes": 20,
        "message": "We haven't read Reddit about teapots yet, so we've started: check back in about 20 minutes."}
    [entry] = site.queue().entries
    assert entry.product_type == "teapot" and entry.status == "waiting"
    assert site.google.jobs_started == [JOB]  # started at once: no schedule to wait for


def test_the_queued_answer_isnt_remembered_and_asking_again_queues_nothing_more(tmp_path, monkeypatch):
    site = Site(tmp_path, monkeypatch)
    site.ask(TEAPOT)
    worked_out = []
    real = web.answer_request
    monkeypatch.setattr(web, "answer_request", lambda *a, **k: worked_out.append(1) or real(*a, **k))
    site.ticks.now += 120  # two minutes on: the queue is read again
    again = site.ask(TEAPOT)
    assert worked_out == [1] and again["on_demand"]["state"] == "reading"  # worked out again, not remembered
    assert len(site.google.asked("POST", "/upload/")) == 1 and len(site.queue().entries) == 1
    assert site.google.jobs_started == [JOB]  # not started again within ON_DEMAND_START_EVERY_SECONDS


def test_a_request_the_library_covers_costs_no_call(tmp_path, monkeypatch):
    site = Site(tmp_path, monkeypatch)
    data = site.ask(REQUEST)  # the kettle library's own request
    assert "on_demand" not in data and len(data["answer"]["picks"]) == 3
    assert site.google.calls == []
    for request in ("something nice for my mum", "best gaming laptop"):  # a question, a polite no
        assert "on_demand" not in site.ask(request)
    assert site.google.calls == []


def test_a_slightly_read_product_says_we_are_reading_more(tmp_path, monkeypatch):
    site = Site(tmp_path, monkeypatch)
    site.reader.min_threads = 6  # the kettle library's 2 threads are now too few
    data = site.ask(REQUEST)
    assert data["on_demand"]["read_before"] is True and len(data["answer"]["picks"]) == 3  # what it has, shown too
    assert data["on_demand"]["message"].startswith("We've read only a little on Reddit about electric kettles so far")


def test_a_second_request_waits_its_turn(tmp_path, monkeypatch):
    site = Site(tmp_path, monkeypatch)
    site.ask(TEAPOT)
    data = site.ask("stovetop kettle that whistles")
    assert data["on_demand"]["check_back_minutes"] == 35 and "in about 35 minutes" in data["on_demand"]["message"]


def test_while_reading_rests_the_answer_says_when_it_starts_again(tmp_path, monkeypatch):
    site = Site(tmp_path, monkeypatch)
    QueueStore(site.bucket).change(lambda q: q.rest(on_demand.next_gemini_reset(NOW), "gemini"))
    data = site.ask(TEAPOT)
    assert data["on_demand"]["state"] == "waiting" and data["on_demand"]["check_back_minutes"] is None
    assert data["on_demand"]["message"] == ("We haven't read Reddit about teapots yet. It's on our list, but our free "
                                            "reading allowance is used up for now: check back tomorrow.")
    assert site.google.jobs_started == []  # nothing would read it before then
    assert len(site.queue().entries) == 1  # still queued, for when it starts again


def test_a_request_waiting_far_too_long_is_said_to_take_longer_than_usual(tmp_path, monkeypatch):
    site = Site(tmp_path, monkeypatch)
    site.ask(TEAPOT)
    site.ticks.now += (ON_DEMAND_LATE_MINUTES + 1) * 60
    data = site.ask(TEAPOT)
    assert data["on_demand"]["state"] == "late" and "longer than usual" in data["on_demand"]["message"]


def test_a_full_queue_answers_with_what_the_library_has_and_asks_again_later(tmp_path, monkeypatch):
    site = Site(tmp_path, monkeypatch)
    entries = [on_demand.Entry(key=f"kitchen/gadget {n}/", category="kitchen", product_type=f"gadget {n}",
                               subreddits=["BuyItForLife"]) for n in range(ON_DEMAND_MAX_WAITING)]
    QueueStore(site.bucket).change(lambda q: q.entries.extend(entries))
    data = site.ask(TEAPOT)
    assert "on_demand" not in data and len(site.queue().entries) == ON_DEMAND_MAX_WAITING
    assert web._answers == {}  # not remembered: asked about again next time


def test_when_the_bucket_cant_be_reached_the_answer_isnt_remembered(tmp_path, monkeypatch):
    site = Site(tmp_path, monkeypatch, google=FakeGoogle(down=True))
    data = site.ask(TEAPOT)
    assert "on_demand" not in data and data["answer"]["picks"] == []
    assert web._answers == {}


def test_the_threads_the_job_read_come_in_and_the_next_ask_answers_with_them(tmp_path, monkeypatch):
    # As on the live site, every quote shown is checked on Reddit's embed page first (here a stand-in showing each
    # comment as written): archive threads count from that check, not from a live read of the whole thread.
    embed = FakeEmbed()
    clock = Clock()
    monkeypatch.setattr(web, "live", LiveChecker(cache_dir=tmp_path / "checks", fetch=embed, clock=clock,
                                                 sleep=clock.sleep))
    site = Site(tmp_path, monkeypatch)
    site.ask(TEAPOT)
    site.job_reads()
    site.ticks.now += 120
    data = site.ask(TEAPOT)
    assert "on_demand" not in data
    shown = {q["comment_id"] for p in data["answer"]["picks"] for q in p["quotes"]}
    assert shown and shown <= {url.rstrip("/").split("/")[-2] for url in embed.asked}  # each read live first
    assert sorted(p["name"] for p in data["answer"]["picks"]) == ["Brown Betty teapot", "Hario Jumping teapot"]
    # The Kinto's third recommendation was the quote Gemini got wrong: the check dropped it, so it has 2 credible
    # recommendations, shown apart under "Also worth a look".
    assert [item["name"] for item in data["answer"]["worth_a_look"]] == ["Kinto Unitea teapot"]
    assert sorted(data["threads_used"]) == ["1tea001", "1tea002", "1tea003"]
    for pick in data["answer"]["picks"]:  # every quote word for word in its comment (the server refuses any other)
        assert pick["quotes"] and all(find_quote(body_of(q["comment_id"]), q["text"]) for q in pick["quotes"])
    assert all((site.library / folder / "1tea001.json").is_file() for folder in ("threads", "extracted"))


def test_a_baked_thread_is_never_overwritten_by_the_bundle(tmp_path, monkeypatch):
    site = Site(tmp_path, monkeypatch)
    site.ask(TEAPOT)
    site.job_reads()
    baked = site.library / "threads" / "1tea001.json"
    baked.write_text('{"baked": "copy"}', encoding="utf-8")
    assert site.reader.load_threads() == 2
    assert baked.read_text(encoding="utf-8") == '{"baked": "copy"}'


def test_the_keep_warm_ping_looks_for_new_threads_at_each_ping_while_a_request_waits_else_hourly(tmp_path,
                                                                                                monkeypatch):
    site = Site(tmp_path, monkeypatch)
    web.ready.set()
    site.ask(TEAPOT)
    looked = lambda: len(site.google.asked("GET", "threads.json?fields=generation"))  # noqa: E731
    before = looked()
    site.ticks.now += 300
    assert web.handle_request("/ready", site.library)[0] == 200 and looked() == before + 1
    site.job_reads()
    site.ticks.now += 300
    web.handle_request("/ready", site.library)  # the reading is done: the threads come in now
    assert (site.library / "threads" / "1tea003.json").is_file()
    after = looked()
    site.ticks.now += 300
    web.handle_request("/ready", site.library)
    assert looked() == after  # nothing waits: no more than hourly
    site.ticks.now += BUNDLE_RELOAD_SECONDS
    web.handle_request("/ready", site.library)
    assert looked() == after + 1


def test_the_ping_starts_the_job_again_when_a_start_failed(tmp_path, monkeypatch):
    site = Site(tmp_path, monkeypatch)
    web.ready.set()
    site.google.job_status = 403  # the account may not start it (yet)
    site.ask(TEAPOT)
    assert site.google.jobs_started == []
    site.google.job_status = 200
    site.ticks.now += 60
    web.handle_request("/ready", site.library)
    assert site.google.jobs_started == []  # within ON_DEMAND_START_EVERY_SECONDS of the last try
    site.ticks.now += 300
    web.handle_request("/ready", site.library)
    assert site.google.jobs_started == [JOB]
    QueueStore(site.bucket).change(lambda q: q.take_lease(NOW) and None)  # a run holds the queue now
    site.ticks.now += 600
    web.handle_request("/ready", site.library)
    assert site.google.jobs_started == [JOB]  # never a second run at once


def test_getting_ready_takes_in_the_threads_read_on_demand_before_reading_the_library(tmp_path, monkeypatch):
    from engine import library_cache, query_model

    site = Site(tmp_path, monkeypatch)
    site.ask(TEAPOT)
    site.job_reads()
    order = []
    real_loaded = library_cache.loaded
    monkeypatch.setattr(library_cache, "loaded", lambda d: order.append(
        ("library", (site.library / "threads" / "1tea001.json").is_file())) or real_loaded(d))
    monkeypatch.setattr(query_model, "default_query_model", lambda: None)
    monkeypatch.setattr(web, "WARM_PRODUCT_TYPES", ())
    web.warm_up(site.library)
    assert order and order[0] == ("library", True)


def test_threads_never_checked_live_go_from_the_folder_after_the_archive_keeping_time(tmp_path, monkeypatch):
    site = Site(tmp_path, monkeypatch)
    web.ready.set()
    site.ask(TEAPOT)
    site.job_reads()
    site.reader.load_threads()
    assert (site.library / "threads" / "1tea002.json").is_file()
    site.now = NOW + timedelta(days=ARCHIVE_TEXT_KEPT_DAYS + 1)
    site.ticks.now += BUNDLE_RELOAD_SECONDS
    web.handle_request("/ready", site.library)
    assert not (site.library / "threads" / "1tea002.json").exists()
    assert not (site.library / "extracted" / "1tea002.json").exists()


def test_without_its_job_the_site_queues_nothing(tmp_path):
    assert on_demand.site_reader_from_env({on_demand.BUCKET_VAR: NAME}, tmp_path) is None
    assert on_demand.site_reader_from_env({}, tmp_path) is None
    reader = on_demand.site_reader_from_env({on_demand.BUCKET_VAR: NAME, on_demand.JOB_VAR: JOB}, tmp_path)
    assert reader is not None and reader.job.job_name == JOB
    with pytest.raises(ValueError):
        on_demand.site_reader_from_env({on_demand.BUCKET_VAR: NAME, on_demand.JOB_VAR: "credible-recs-reader"},
                                       tmp_path)


def test_a_request_queued_again_a_month_later_isnt_late_for_its_first_reading(tmp_path, monkeypatch):
    clock = Clock()
    monkeypatch.setattr(web, "live", LiveChecker(cache_dir=tmp_path / "checks", fetch=FakeEmbed(), clock=clock,
                                                 sleep=clock.sleep))
    site = Site(tmp_path, monkeypatch)
    site.ask(TEAPOT)
    site.job_reads()  # read: done, with 3 threads; their library is still under the bar here
    site.reader.load_threads()
    site.reader.min_threads = 6
    site.ticks.now += 31 * 24 * 3600
    site.now = NOW + timedelta(days=31)  # its wait is over: queued again
    data = site.ask(TEAPOT)
    assert data["on_demand"]["state"] == "reading" and data["on_demand"]["read_before"] is True
