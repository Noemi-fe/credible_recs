"""What a visitor is told about the wait (Noemi's decision (l) of 19 Oct 2026; the review of 16 Oct, R7: "check back in
about 20 minutes" was false, since Gemini's free allowance read about one product a day): the sentence comes from the
queue's length and what the day can read, so the second request in line isn't promised what the tenth can't have.

Wording PROPOSED, like the page's other new words. Every service is a stand-in (engine/tests/fake_google.py): no test
reaches the network.
"""

import types
from datetime import timedelta

import pytest

from engine import config, on_demand
from engine.config import (
    ON_DEMAND_CALLS_PER_PRODUCT, ON_DEMAND_EACH_MINUTES, ON_DEMAND_FIRST_MINUTES, ON_DEMAND_LATE_MINUTES,
    ON_DEMAND_MONTH_SECONDS, ON_DEMAND_PRODUCT_MINUTES,
)
from engine.live_check import Bucket
from engine.on_demand import Entry, JobStarter, Queue, QueueStore, SiteReader, entry_for, wait_for
from engine.query import parse_query
from engine.tests.fake_google import FakeGoogle
from engine.tests.on_demand_fakes import NOW, Ticks

NAME = "credible-test-on-demand"
JOB = "projects/credible-picks/locations/europe-west1/jobs/credible-recs-reader"
# These tests take a reader whose free allowance reads 10 requests a day (150 calls); the one config names today
# (Gemini 3.8 Flash: 20 calls a day) is tested on its own at the end.
CALLS_A_DAY = 150
PER_DAY = CALLS_A_DAY // ON_DEMAND_CALLS_PER_PRODUCT


@pytest.fixture(autouse=True)
def a_reader_with_ten_requests_a_day(monkeypatch):
    monkeypatch.setattr(on_demand, "ON_DEMAND_GEMINI_CALLS_A_DAY", CALLS_A_DAY)


class Line:
    """A site whose queue already holds some waiting requests and some usage; asks for the teapot and says what it's told."""

    def __init__(self, tmp_path, waiting=0, calls_used=0, seconds_used=0, resting=None):
        self.google, self.ticks = FakeGoogle(), Ticks()
        self.bucket = Bucket(NAME, request=self.google, clock=lambda: 0.0, prefix=on_demand.PREFIX)
        self.site = SiteReader(self.bucket, tmp_path / "site", job=JobStarter(JOB, self.bucket, request=self.google),
                               clock=self.ticks, now=lambda: NOW)
        ahead = [Entry(key=f"kitchen/gadget {n}/", category="kitchen", product_type=f"gadget {n}",
                       subreddits=["BuyItForLife"]) for n in range(waiting)]

        def prepare(queue: Queue):
            queue.entries.extend(ahead)
            queue.usage_now(NOW).update(gemini_calls=calls_used, seconds=seconds_used)
            if resting:
                queue.rest(*resting)

        QueueStore(self.bucket).change(prepare)

    def asked(self, request="teapot for loose leaf tea", threads=0, own=0, newest=None) -> dict:
        result = types.SimpleNamespace(query=parse_query(request), threads_available=threads,
                                       own_threads_available=own, newest_own_thread=newest)
        return self.site.after_answer(result).state


def test_the_first_request_with_the_days_calls_to_spare_is_read_in_about_an_hour(tmp_path):
    # Each Gemini call took about 4 minutes on 25 Oct 2026 and a request is 15 calls and 6 minutes of Arctic Shift: 66
    # minutes of the job, and the site picks the threads up at its next ping. It was "20 minutes" before it was timed.
    state = Line(tmp_path).asked()
    assert state["check_back_minutes"] == ON_DEMAND_FIRST_MINUTES == 70
    assert state["message"] == "We haven't read Reddit about teapots yet, so we've started: check back in about an hour."


def test_each_request_ahead_adds_its_reading_while_the_days_calls_last(tmp_path):
    state = Line(tmp_path, waiting=3).asked()
    assert state["check_back_minutes"] == ON_DEMAND_FIRST_MINUTES + 3 * ON_DEMAND_EACH_MINUTES
    assert "in about" in state["message"] and state["state"] == "reading"


def test_a_place_past_what_the_days_calls_read_is_told_tomorrow_with_the_line_and_the_daily_capacity(tmp_path):
    left = 2  # products the rest of today's calls can still read
    used = CALLS_A_DAY - left * ON_DEMAND_CALLS_PER_PRODUCT
    state = Line(tmp_path, waiting=left + 1, calls_used=used).asked()
    assert state["state"] == "waiting" and state["check_back_minutes"] is None
    assert state["message"] == (
        f"We haven't read Reddit about teapots yet. It's in line: {left + 1} products are ahead of it, and our free "
        f"reading allowance covers about {PER_DAY} a day. Check back tomorrow.")


def test_one_request_ahead_is_said_in_the_singular(tmp_path):
    used = CALLS_A_DAY  # nothing left today
    state = Line(tmp_path, waiting=1, calls_used=used).asked()
    assert "1 product is ahead of it" in state["message"]


def test_the_day_with_no_calls_left_and_nobody_ahead_says_the_allowance_is_used_up(tmp_path):
    state = Line(tmp_path, waiting=0, calls_used=CALLS_A_DAY).asked()
    assert state["message"] == ("We haven't read Reddit about teapots yet. It's on our list, but our free reading "
                                "allowance is used up for now: check back tomorrow.")


def test_a_line_longer_than_a_day_reads_is_told_the_day_it_will_be_reached(tmp_path, monkeypatch):
    # A small allowance of 30 calls (2 products a day, at 15 calls a product), all used today: the places 0 and 1 are
    # read on the first day after the reset (10 October, at 8 am UTC), 2 and 3 on the next. It is 9 October at noon.
    monkeypatch.setattr(on_demand, "ON_DEMAND_GEMINI_CALLS_A_DAY", 30)
    tomorrow = Line(tmp_path / "one", waiting=1, calls_used=30).asked()
    assert tomorrow["message"].endswith("Check back tomorrow.")
    later = Line(tmp_path / "two", waiting=2, calls_used=30).asked()
    assert "2 products are ahead of it" in later["message"] and "about 2 a day" in later["message"]
    assert later["message"].endswith("Check back on 11 October.")


def test_when_the_months_time_runs_out_before_its_turn_it_says_the_first_of_next_month(tmp_path):
    product_seconds = ON_DEMAND_PRODUCT_MINUTES * 60
    state = Line(tmp_path, waiting=2, seconds_used=ON_DEMAND_MONTH_SECONDS - product_seconds).asked()  # 1 product left
    assert state["state"] == "waiting" and "on 1 November" in state["message"]


def test_a_wait_that_is_days_long_is_never_called_late(tmp_path):
    line = Line(tmp_path, waiting=1, calls_used=CALLS_A_DAY)
    line.asked()
    line.ticks.now += (ON_DEMAND_LATE_MINUTES + 1) * 60
    assert line.asked()["state"] == "waiting"


def test_a_wait_of_minutes_that_runs_late_still_says_so(tmp_path):
    line = Line(tmp_path)
    line.asked()
    line.ticks.now += (ON_DEMAND_LATE_MINUTES + 1) * 60
    assert line.asked()["state"] == "late"


def test_a_resting_queue_counts_the_place_from_when_it_starts_again(tmp_path):
    reset = on_demand.next_gemini_reset(NOW)
    state = Line(tmp_path, waiting=0, resting=(reset, "gemini")).asked()
    assert state["state"] == "waiting" and state["message"].endswith("check back tomorrow.")
    far = Line(tmp_path / "far", waiting=PER_DAY + 1, resting=(reset, "gemini")).asked()
    assert "ahead of it" in far["message"] and far["state"] == "waiting"


def test_threads_that_are_old_say_newer_ones_are_being_read(tmp_path):
    state = Line(tmp_path).asked("laptop for university", threads=14, own=8, newest=NOW - timedelta(days=3 * 365))
    assert state["read_before"] is True and state["state"] == "reading"
    assert state["message"] == ("The Reddit threads we've read about laptops are a few years old, so we've started "
                                "reading newer ones: check back in about an hour.")


def test_the_wait_is_worked_out_by_wait_for(tmp_path):
    line = Line(tmp_path, waiting=2)
    queue = line.site.store.read()[0]
    assert wait_for(0, queue, NOW) == (ON_DEMAND_FIRST_MINUTES, None)
    assert wait_for(2, queue, NOW) == (ON_DEMAND_FIRST_MINUTES + 2 * ON_DEMAND_EACH_MINUTES, None)
    minutes, until = wait_for(PER_DAY + 5, queue, NOW)
    assert minutes is None and until > NOW


def test_with_the_reader_config_names_today_the_second_request_in_line_is_told_tomorrow(tmp_path, monkeypatch):
    # Gemini 3.8 Flash's free allowance is 20 requests a day (Google's own 429 answer, 25 Oct 2026): the job's 18 calls
    # read one request of 15 calls a day, so "in about 35 minutes" for the second would be false.
    monkeypatch.setattr(on_demand, "ON_DEMAND_GEMINI_CALLS_A_DAY", config.ON_DEMAND_GEMINI_CALLS_A_DAY)
    assert config.ON_DEMAND_GEMINI_MODEL == "gemini-3.8-flash" and on_demand.products_a_day() == 1
    first = Line(tmp_path / "first").asked()
    assert first["check_back_minutes"] == ON_DEMAND_FIRST_MINUTES
    second = Line(tmp_path / "second", waiting=1).asked("stovetop kettle that whistles")
    assert second["state"] == "waiting" and second["message"].endswith("Check back tomorrow.")
    assert "1 product is ahead of it" in second["message"] and "about 1 a day" in second["message"]
