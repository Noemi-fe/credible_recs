"""On-demand reading's queue (Noemi's plan of 14 Oct 2026, part 3): what it keeps of a request the library can't answer
yet, and how the site and the reading job share it without losing each other's changes.

Privacy (Noemi's rule of 11 Oct 2026: no access logs of visitors): an entry holds only what finding threads needs, the
product type module 1 understood, its category and subreddits, and at most a few of the request's need words; never
the request as typed, never a time it was asked or anything about who asked. Every text here is made up, and every
call to Google goes to a stand-in (engine/tests/fake_google.py): no test reaches the network.
"""

import json
from datetime import UTC, datetime, timedelta

from engine import on_demand
from engine.config import ON_DEMAND_NEED_WORDS
from engine.live_check import Bucket
from engine.on_demand import Entry, Queue, QueueStore, entry_for
from engine.query import parse_query
from engine.tests.fake_google import FakeGoogle

NAME = "credible-test-on-demand"
NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
REQUEST = "Best teapot for loose leaf tea that pours without dripping, a gift for my aunt Margot"


def store(google) -> QueueStore:
    return QueueStore(Bucket(NAME, request=google, clock=lambda: 0.0, prefix=on_demand.PREFIX))


def test_an_entry_keeps_the_product_type_and_a_few_need_words_never_the_request_as_typed():
    entry = entry_for(parse_query(REQUEST), had=0)
    assert (entry.category, entry.product_type) == ("kitchen", "teapot")
    assert entry.subreddits == ["tea", "BuyItForLife"]  # module 1's, for the archive's searches
    assert 0 < len(entry.needs) <= ON_DEMAND_NEED_WORDS and entry.needs[:2] == ["loose", "leaf"]
    saved = json.dumps(entry.as_json()).lower()
    for word in ("best", "dripping", "gift", "aunt", "margot", "pours without"):
        assert word not in saved  # the rest of the request isn't kept: filler words, the later needs, who it's for
    assert not any(name in entry.as_json() for name in ("text", "request", "asked_at", "queued_at", "address"))


def test_requests_with_the_same_product_and_needs_are_one_entry():
    one = entry_for(parse_query("teapot for loose leaf"), had=0)
    other = entry_for(parse_query("loose leaf teapot?"), had=0)
    assert one.key == other.key
    assert entry_for(parse_query("teapot that keeps tea hot"), had=0).key != one.key


def test_the_queue_reads_back_what_was_written():
    queue = Queue(entries=[entry_for(parse_query("teapot for loose leaf"), had=1)])
    queue.lease_until = (NOW + timedelta(minutes=45)).isoformat()
    again = Queue.from_json(json.loads(json.dumps(queue.as_json())))
    assert again.as_json() == queue.as_json()
    assert [e.key for e in again.waiting()] == [queue.entries[0].key]


def test_a_queue_that_isnt_there_yet_reads_as_empty():
    google = FakeGoogle()
    queue, generation = store(google).read()
    assert queue.entries == [] and generation is None


def test_the_site_and_the_job_writing_at_once_lose_nothing():
    google = FakeGoogle()
    queues = store(google)
    first = entry_for(parse_query("teapot for loose leaf"), had=0)
    queues.change(lambda queue: queue.add(first))

    def the_job_marks_it_done_meanwhile():  # another writer saves between the site's read and its write
        store(google).change(lambda queue: queue.find(first.key).finish(NOW, found=2))

    google.before_write = the_job_marks_it_done_meanwhile
    second = entry_for(parse_query("stovetop kettle that whistles"), had=0)
    assert queues.change(lambda queue: queue.add(second)) is not None
    saved = Queue.from_json(google.read(NAME, "on_demand/queue.json"))
    assert [e.key for e in saved.entries] == [first.key, second.key]
    assert saved.find(first.key).status == "done" and saved.find(second.key).status == "waiting"


def test_a_queue_that_cant_be_reached_is_said_so_and_never_overwritten():
    google = FakeGoogle(down=True)
    assert store(google).read() is None
    assert store(google).change(lambda queue: queue.add(entry_for(parse_query("teapot"), had=0))) is None


def test_one_run_holds_the_queue_at_a_time_until_its_lease_runs_out():
    queue = Queue()
    assert queue.take_lease(NOW, minutes=45)
    assert not queue.take_lease(NOW + timedelta(minutes=10), minutes=45)  # another run: it is held
    assert queue.take_lease(NOW + timedelta(minutes=46), minutes=45)  # a run that died: its lease ran out
    queue.release_lease()
    assert not queue.leased(NOW + timedelta(minutes=50))


def test_a_done_entry_is_read_again_only_after_its_wait():
    entry = Entry.waiting_for(parse_query("teapot for loose leaf"), had=0)
    entry.finish(NOW, found=3)
    assert not entry.due_again(NOW + timedelta(days=29))
    assert entry.due_again(NOW + timedelta(days=31))
    failed = Entry.waiting_for(parse_query("teapot for loose leaf"), had=0)
    failed.finish(NOW, found=0, failed=True)  # its reading failed (the archive down): tried again after a day
    assert failed.due_again(NOW + timedelta(days=1, minutes=1))
