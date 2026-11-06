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


def test_without_the_lean_library_threads_are_kept_whole_and_it_says_so(tmp_path, monkeypatch):
    # Changed on purpose 14 Oct 2026 (lean-library merged): engine.slim is here now, so its absence is made explicit.
    monkeypatch.setitem(sys.modules, "engine.slim", None)  # importing it fails, as before the lean library
    google = FakeGoogle()
    queued(google, TEAPOT)
    report = run(tmp_path, google)
    assert report.whole == 3 and report.slimmed == 0 and any("engine.slim" in note for note in report.notes)
    assert not any(item.slimmed for item in the_bundle(google).threads.values())


def test_with_the_real_lean_library_threads_read_on_demand_are_slimmed(tmp_path):
    # The lean library merged (14 Oct 2026): a thread read on demand keeps only the comments answers use, checked by
    # the slimming's own guard, like any thread of the library.
    from engine.models import Thread

    google = FakeGoogle()
    queued(google, TEAPOT)
    report = run(tmp_path, google)
    assert report.slimmed + report.whole == 3 and report.slimmed >= 1
    slimmed = [Thread.model_validate_json(item.thread) for item in the_bundle(google).threads.values() if item.slimmed]
    assert slimmed and all(thread.slimmed and thread.author is None for thread in slimmed)


def test_with_the_lean_library_threads_keep_only_the_comments_answers_use(tmp_path, monkeypatch):
    # Changed on purpose, 14 Oct 2026 (lean-library merged with main's need-led reading): engine.slim also takes the
    # words a slimmed post is searched for (known_words, and the queued request's own: known_words_of).
    calls, said = [], []
    fake = types.ModuleType("engine.slim")
    fake.known_types = lambda library_dir: ("electric kettle",)
    fake.known_words = lambda library_dir: frozenset({"kettle"})
    fake.known_words_of = lambda *texts: (said.append(texts), frozenset(texts))[1]
    fake.slim_thread = lambda thread, extraction, kinds, now, words=None: (calls.append((kinds, words)), thread)[1]
    fake.differences = lambda whole, slimmed, extraction, kinds, words=None: []
    fake.thread_json = lambda thread: b'{"slimmed": "copy"}'
    monkeypatch.setitem(sys.modules, "engine.slim", fake)
    google = FakeGoogle()
    queued(google, TEAPOT)
    report = run(tmp_path, google)
    assert report.slimmed == 3 and report.whole == 0
    assert all(item.slimmed and item.thread == '{"slimmed": "copy"}' for item in the_bundle(google).threads.values())
    assert calls[0][0] == ("electric kettle", "teapot")  # the request's own type is looked for in the words dropped
    assert said[0][0] == "teapot" and "loose" in said[0]  # and its own words, as need-led reading will look for them
    assert {"kettle", "teapot", "loose"} <= calls[0][1]


def test_a_slimmed_copy_that_would_read_differently_stays_whole(tmp_path, monkeypatch):
    fake = types.ModuleType("engine.slim")
    fake.known_types = lambda library_dir: ()
    fake.known_words = lambda library_dir: frozenset()
    fake.known_words_of = lambda *texts: frozenset()
    fake.slim_thread = lambda thread, extraction, kinds, now, words=None: thread
    fake.differences = lambda whole, slimmed, extraction, kinds, words=None: ["the extraction's checks"]
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


# --- The reader's model (Noemi's decision (l) of 19 Oct 2026: a cheaper reader) ---

def test_the_job_reads_with_the_model_config_names_unless_its_settings_name_another(monkeypatch):
    from engine import config

    monkeypatch.delenv(on_demand.MODEL_VAR, raising=False)
    assert on_demand.reader_model() == config.ON_DEMAND_GEMINI_MODEL
    monkeypatch.setenv(on_demand.MODEL_VAR, "gemini-test-model")
    assert on_demand.reader_model() == "gemini-test-model"
    monkeypatch.setenv(on_demand.MODEL_VAR, "  ")
    assert on_demand.reader_model() == config.ON_DEMAND_GEMINI_MODEL  # a blank setting is no setting


def test_a_run_from_the_command_line_asks_gemini_through_that_model(monkeypatch):
    import engine.gemini_extract

    seen = {}

    class Client:
        def __init__(self, *args, **kwargs):
            seen["model"] = kwargs.get("model")

    def fake_run_job(bucket, library, archive, gemini, **kwargs):
        seen["gemini"] = gemini
        return types.SimpleNamespace(text=lambda: "report")

    monkeypatch.setenv(on_demand.BUCKET_VAR, "credible-test-on-demand")
    monkeypatch.setenv(on_demand.MODEL_VAR, "gemini-test-model")
    monkeypatch.setattr(engine.gemini_extract, "GeminiClient", Client)
    monkeypatch.setattr(on_demand, "run_job", fake_run_job)
    monkeypatch.setattr("engine.arctic_shift.ArcticShiftClient", lambda *a, **k: object())
    assert on_demand.main(["run"]) == 0
    assert seen["model"] == "gemini-test-model" and isinstance(seen["gemini"], Client)


# --- A search round cut short is tried again (4 Nov 2026, from Noemi's report about "blush") ---
# Arctic Shift timed out on about half the searches that day; a round ended by them still read what its first searches
# found (2 threads a request) and the request was closed with those. Now, when searches failed and the request has
# fewer than LIBRARY_THREADS_PER_PRODUCT threads, it stays waiting (one more try), and the next run reads the rest,
# never the bundle's again, up to LIBRARY_THREADS_PER_PRODUCT in all; after ON_DEMAND_MAX_TRIES it is closed with what
# it has.

class SearchesFail(FakeArchive):
    """The archive with only the "teapot" searches of the `answering` communities answering (r/tea's): every other
    search fails, as a busy archive's do."""

    def __init__(self, answering=("tea",), **kwargs):
        super().__init__(**kwargs)
        self.answering = answering

    def __call__(self, url, headers):
        answers = "title=teapot&" in url and any(f"subreddit={name}&" in url for name in self.answering)
        if "/posts/search" in url and not answers:
            self.requests.append(url)
            return 522, b"Cloudflare: the origin didn't answer"
        return super().__call__(url, headers)


def more_teapots(monkeypatch) -> tuple[str, ...]:
    """Four more made-up teapot threads, in r/BuyItForLife: seven in all, more than a request reads."""
    from engine.tests import on_demand_fakes

    for n in range(4, 8):
        monkeypatch.setitem(on_demand_fakes.TEAPOT_THREADS, f"1tea00{n}", ("BuyItForLife", f"Teapot number {n} worth it?", [
            (f"t{n}a", f"My Brown Betty teapot has lasted {n} years.", "Brown Betty teapot")]))
    return tuple(on_demand_fakes.TEAPOT_THREADS)


def test_a_round_cut_short_leaves_the_request_waiting_and_the_next_run_reads_the_rest(tmp_path, monkeypatch):
    from engine.config import LIBRARY_THREADS_PER_PRODUCT

    every = more_teapots(monkeypatch)
    whole = FakeGoogle()  # what one whole round reads, for comparison
    queued(whole, TEAPOT)
    (tmp_path / "whole").mkdir()
    run(tmp_path / "whole", whole, fake_archive=FakeArchive(threads=every))
    expected = sorted(the_bundle(whole).threads)
    assert 2 < len(expected) <= LIBRARY_THREADS_PER_PRODUCT  # the library's mix, at most 3 from each community here

    google = FakeGoogle()
    queued(google, TEAPOT)
    report = run(tmp_path, google, fake_archive=SearchesFail(threads=every))
    [entry] = the_queue(google).entries
    assert sorted(the_bundle(google).threads) == ["1tea001", "1tea003"]  # what r/tea's search found
    assert entry.status == "waiting" and entry.tries == 1 and entry.read_at is None  # not closed with 2
    assert report.threads_read == 2 and report.extracted == 2
    fake = FakeArchive(threads=every)
    later = run(tmp_path, google, fake_archive=fake, now=NOW + timedelta(minutes=61))
    assert sorted(the_bundle(google).threads) == expected  # the two tries read what one whole round reads
    assert later.threads_read == len(expected) - 2
    assert not any("ids=1tea001" in url or "ids=1tea003" in url for url in fake.requests)  # the bundle's: not again
    [entry] = the_queue(google).entries
    assert entry.status == "done" and entry.found == len(expected)


def test_after_its_tries_a_request_cut_short_each_time_is_closed_with_what_it_has(tmp_path, monkeypatch):
    every = more_teapots(monkeypatch)
    google = FakeGoogle()
    queued(google, TEAPOT)
    moment = NOW
    for _ in range(ON_DEMAND_MAX_TRIES):
        run(tmp_path, google, fake_archive=SearchesFail(threads=every), now=moment)
        moment += timedelta(minutes=61)
    [entry] = the_queue(google).entries
    assert entry.status == "done" and entry.found == 2 and entry.tries == ON_DEMAND_MAX_TRIES
    assert sorted(the_bundle(google).threads) == ["1tea001", "1tea003"]


def test_a_round_that_found_all_it_needs_is_closed_though_a_search_failed(tmp_path, monkeypatch):
    from engine.tests import on_demand_fakes

    # Enough teapot threads in both communities for the library's mix (at most 3 from each of the two here): the two
    # "teapot" searches that answer find all it needs, though the "tea pot" ones fail.
    for n, community in ((4, "tea"), (5, "BuyItForLife"), (6, "BuyItForLife")):
        monkeypatch.setitem(on_demand_fakes.TEAPOT_THREADS, f"1tea00{n}", (community, f"Teapot number {n} worth it?", [
            (f"t{n}a", f"My Brown Betty teapot has lasted {n} years.", "Brown Betty teapot")]))
    google = FakeGoogle()
    queued(google, TEAPOT)
    run(tmp_path, google, fake_archive=SearchesFail(answering=("tea", "BuyItForLife"),
                                                    threads=tuple(on_demand_fakes.TEAPOT_THREADS)))
    [entry] = the_queue(google).entries
    assert entry.status == "done" and entry.tries == 0


# --- Inside the old budget (4 Nov 2026, Noemi's "Keep 25 min") ---
# The told wait (about 25 minutes, 30 requests a day, 39 a month) rests on a request taking 6 minutes of Arctic Shift
# (config.ON_DEMAND_ARCHIVE_MINUTES) and 15 Gemini calls (config.ON_DEMAND_CALLS_PER_PRODUCT). Round 1's advice searches
# reach the big threads asking for recommendations, but they had been added on top of the round (about 32 searches, not
# 16), and big threads take up to 4 calls each (24 for six). So the round's searches have a budget
# (config.ON_DEMAND_SEARCH_CALLS, main's own "blush" round), the advice searches come before the title searches inside
# it, and the threads a request reads are chosen so that their extraction fits its Gemini calls.

class MakeupArchive:
    """Arctic Shift as it answers a type people post about every day: a title search matches whole words, within its
    dates, and answers only its newest `limit` posts; each thread has as many comments as its post says. Every title
    and comment is made up."""

    def __init__(self, posts: list[dict]):
        self.posts, self.requests = {p["id"]: p for p in posts}, []

    def __call__(self, url, headers):
        import re
        from datetime import UTC, datetime
        from urllib.parse import parse_qs, urlparse

        self.requests.append(url)
        path, query = urlparse(url).path, parse_qs(urlparse(url).query)
        if path.endswith("/posts/search"):
            words = set(query["title"][0].lower().split())

            def day(post):
                return datetime.fromtimestamp(post["created_utc"], UTC).date().isoformat()

            found = [p for p in self.posts.values() if p["subreddit"] == query["subreddit"][0]
                     and words <= set(re.findall(r"[a-z0-9]+", p["title"].lower()))
                     and ("after" not in query or day(p) >= query["after"][0])
                     and ("before" not in query or day(p) < query["before"][0])]
            data = sorted(found, key=lambda p: p["created_utc"], reverse=True)[:int(query["limit"][0])]
        elif path.endswith("/posts/ids"):
            data = [self.posts[tid] for tid in query["ids"][0].split(",") if tid in self.posts]
        elif path.endswith("/comments/tree"):
            post = self.posts[query["link_id"][0].removeprefix("t3_")]
            data = [{"kind": "t1", "data": {
                "id": f"{post['id']}c{n}", "parent_id": f"t3_{post['id']}", "link_id": f"t3_{post['id']}",
                "author": f"writer{n}", "body": f"A made-up comment number {n} about a blush.",
                "created_utc": post["created_utc"] + 3600, "score": 5,
                "permalink": f"/r/{post['subreddit']}/comments/{post['id']}/x/{post['id']}c{n}/", "replies": ""}}
                for n in range(post["num_comments"])]
        else:
            return 404, b"{}"
        return 200, json.dumps({"data": data}).encode()

    def searches(self) -> int:
        return sum("/posts/search" in url for url in self.requests)


def makeup_post(post_id: str, subreddit: str, title: str, comments: int, posted: str) -> dict:
    from datetime import UTC, datetime

    return {"id": post_id, "subreddit": subreddit, "title": title, "selftext": "Made up.", "author": "asker",
            "created_utc": int(datetime.fromisoformat(posted).replace(tzinfo=UTC).timestamp()), "score": 30,
            "num_comments": comments, "permalink": f"/r/{subreddit}/comments/{post_id}/x/", "link_flair_text": None}


BIG_ADVICE = {"1adv01": 205, "1adv02": 180, "1adv03": 160, "1adv04": 137}


def blush_world() -> list[dict]:
    """110 small recent "blush" posts in each makeup community (more than a search answers), four big advice threads a
    year or two old (4 Gemini calls each), and a few smaller advice threads."""
    posts = [makeup_post(f"1sw{i}{n:03d}", c, f"Blush swatch number {n}", 6, f"2026-{5 + n % 4:02d}-{1 + n % 27:02d}")
             for i, c in enumerate(("Makeup", "Sephora", "MakeupAddiction", "drugstoreMUA")) for n in range(110)]
    return posts + [
        makeup_post("1adv01", "Sephora", "Blush you'd call your all-time favorite?", 205, "2024-11-03"),
        makeup_post("1adv02", "Makeup", "Blush recommendations for a first-timer?", 180, "2024-03-09"),
        makeup_post("1adv03", "MakeupAddiction", "Which blush is your favorite for summer?", 160, "2025-02-01"),
        makeup_post("1adv04", "Sephora", "Three favorite blushes you would rebuy forever?", 137, "2025-06-14"),
        makeup_post("1adv05", "drugstoreMUA", "Budget blush recommendations?", 35, "2025-09-20"),
        makeup_post("1adv06", "Makeup", "Best blush for a beginner?", 30, "2025-04-11"),
        makeup_post("1adv07", "drugstoreMUA", "Favorite drugstore blushes?", 28, "2024-12-01"),
    ]


def test_a_blush_like_request_stays_inside_the_old_budget_and_still_reads_the_big_advice_threads(tmp_path):
    from engine.config import ON_DEMAND_CALLS_PER_PRODUCT, ON_DEMAND_FIRST_MINUTES, ON_DEMAND_SEARCH_CALLS

    google, fake_archive, fake_gemini = FakeGoogle(), MakeupArchive(blush_world()), FakeGemini()
    queued(google, "blush")
    report = run(tmp_path, google, fake_archive=fake_archive, fake_gemini=fake_gemini)
    bundle = the_bundle(google)
    assert fake_archive.searches() <= ON_DEMAND_SEARCH_CALLS == 16  # main's "blush" round
    assert fake_gemini.calls <= ON_DEMAND_CALLS_PER_PRODUCT == 15 and report.gemini_calls == fake_gemini.calls
    assert ON_DEMAND_FIRST_MINUTES == 25  # what the first in line is told, as on main
    read = set(bundle.threads)
    assert "1adv01" in read and len(read & set(BIG_ADVICE)) >= 2  # the big advice threads are reached
    assert len(bundle.extracted()) == len(read) >= 4
    [entry] = the_queue(google).entries
    assert entry.status == "done" and entry.found == len(read)


def test_a_requests_threads_are_chosen_to_fit_its_gemini_calls():
    from engine.config import ON_DEMAND_CALLS_PER_PRODUCT
    from engine.sources import rank_posts

    query = parse_query("blush")
    ranked = rank_posts(query, [p for p in blush_world() if p["num_comments"] > 6])
    chosen = on_demand.within_calls(query, ranked)
    assert sum(on_demand.estimated_calls(p) for p in chosen) <= ON_DEMAND_CALLS_PER_PRODUCT
    assert "1adv01" in {p["id"] for p in chosen} and len(chosen) <= 6
    assert len([p for p in chosen if p["id"] in BIG_ADVICE]) == 3  # a fourth big one (4 calls) would pass the 15
    # Threads read on an earlier try count: with 8 calls spent on them, the rest fits in 7.
    later = on_demand.within_calls(query, ranked, spent=8, wanted=4)
    assert sum(on_demand.estimated_calls(p) for p in later) <= 7 and len(later) <= 4
    assert on_demand.estimated_calls({"num_comments": 205}) == 4 and on_demand.estimated_calls({"num_comments": 0}) == 1
