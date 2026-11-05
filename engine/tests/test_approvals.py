"""What Noemi approved on 25 Oct 2026 ("yes to all recommendations"), tests first.

1. On-demand reading comes back on, read by Gemini 3.1 Flash-Lite: the model, a daily cap of 450 calls (a margin under
   Google's free 500), pacing under the free 15 a minute, a wait message whose capacity sum stays honest (the month's job
   time, not only Gemini's calls, limits the reading), and the deploy switch on unless a deploy says "off".
2. Two ways of looking like a paid or coordinated writer that the voice rubric's rules cover but the detection missed,
   found among the comments the tech data round's extraction helpers flagged: an Amazon product behind a lookalike
   redirect ("dp-" and an Amazon product code on some other site), and a sign-off naming the brand the writer works at.
3. The wordings she approved are no longer marked PROPOSED.

Every text, writer, site and link here is made up.
"""

import re
import types
from datetime import UTC, datetime
from pathlib import Path

import pytest

from engine import config, on_demand
from engine.credibility import score_voice
from engine.gemini_extract import GeminiClient
from engine.live_check import Bucket
from engine.models import Thread
from engine.on_demand import Entry, JobStarter, Queue, QueueStore, SiteReader, run_job
from engine.query import parse_query
from engine.tests.factories import make_comment, make_thread
from engine.tests.fake_google import FakeGoogle
from engine.tests.on_demand_fakes import MISQUOTED, NOW, TEAPOT_THREADS, FakeArchive, FakeGemini, Ticks, archive
from engine.tests.test_web import kettle_library

REPO = Path(__file__).resolve().parents[2]
NAME = "credible-test-on-demand"
JOB = "projects/credible-picks/locations/europe-west1/jobs/credible-recs-reader"


# --- 1. The reader: Gemini 3.1 Flash-Lite, within its free allowance ---

def test_the_reader_is_flash_lite_within_its_free_allowance():
    # Google's own limits for it on 25 Oct 2026 (eval/RUNS.md): 500 requests a day, 15 a minute. 450 a day leaves a
    # margin (a thread's retries count as calls, and the cap is checked before a thread, not inside it); the pace is
    # under the minute's limit.
    assert config.ON_DEMAND_GEMINI_MODEL == "gemini-3.1-flash-lite"
    assert config.ON_DEMAND_GEMINI_CALLS_A_DAY == 450 < 500
    assert config.ON_DEMAND_GEMINI_CALLS_A_MINUTE < 15


def test_the_job_asks_flash_lite_at_a_pace_under_fifteen_a_minute(monkeypatch):
    monkeypatch.delenv(on_demand.MODEL_VAR, raising=False)
    client = on_demand.reader_client()
    assert client.model == "gemini-3.1-flash-lite" == on_demand.reader_model()
    assert 60 / client.min_interval <= config.ON_DEMAND_GEMINI_CALLS_A_MINUTE < 15


def test_a_run_of_calls_never_goes_faster_than_the_pace(monkeypatch):
    # The client waits between calls: made up, the clock is the pauses it asks for.
    from engine import gemini_extract

    # No time passes between calls but the pauses it sleeps (the client reads only gemini_extract's own clock).
    monkeypatch.setattr(gemini_extract, "time", types.SimpleNamespace(monotonic=lambda: 1000.0))
    pauses = []
    client = GeminiClient(key="made-up", model="gemini-3.1-flash-lite", fetch=lambda *a: {
        "candidates": [{"content": {"parts": [{"text": "{}"}]}}]}, sleep=pauses.append,
                          min_interval=on_demand.reader_client().min_interval)
    for _ in range(5):
        client.generate("system", "user")
    assert len(pauses) == 4 and all(p >= 60 / config.ON_DEMAND_GEMINI_CALLS_A_MINUTE - 1e-9 for p in pauses)


def test_the_days_cap_is_450_calls_and_the_next_thread_waits_for_tomorrow(tmp_path):
    google = FakeGoogle()
    bucket = Bucket(NAME, request=google, clock=lambda: 0.0, prefix=on_demand.PREFIX)
    entry = on_demand.entry_for(parse_query("teapot for loose leaf tea"), had=0)
    store = QueueStore(bucket)
    store.change(lambda q: q.add(entry) and None)
    store.change(lambda q: q.usage_now(NOW).update(gemini_calls=449) and None)  # one call left today
    fake = FakeGemini()
    library = kettle_library(tmp_path)
    gem = GeminiClient(key="made-up", model=on_demand.reader_model(), fetch=fake, sleep=lambda s: None, min_interval=0)
    report = run_job(bucket, library, archive(tmp_path, FakeArchive()), gem, now=lambda: NOW, clock=Ticks(),
                     work_dir=tmp_path / "work")
    queue = Queue.from_json(google.read(NAME, "on_demand/queue.json"))
    # Each teapot thread is one call: the one call left today reads one thread, and the next finds 450 of 450 used.
    assert fake.calls == 1 == report.gemini_calls and queue.usage["gemini_calls"] == 450
    assert queue.resting_why == "gemini" and queue.resting_until == on_demand.next_gemini_reset(NOW).isoformat()


def test_the_reader_flash_lite_is_checked_word_for_word_like_every_reader(tmp_path):
    google = FakeGoogle()
    bucket = Bucket(NAME, request=google, clock=lambda: 0.0, prefix=on_demand.PREFIX)
    QueueStore(bucket).change(lambda q: q.add(on_demand.entry_for(parse_query("teapot for loose leaf tea"), had=0)) and None)
    gem = GeminiClient(key="made-up", model=on_demand.reader_model(), fetch=FakeGemini(), sleep=lambda s: None,
                       min_interval=0)
    report = run_job(bucket, kettle_library(tmp_path), archive(tmp_path, FakeArchive()), gem, now=lambda: NOW,
                     clock=Ticks(), work_dir=tmp_path / "work")
    from engine.extract import Extraction, check_extraction

    bundle = on_demand.Bundle.from_json(google.read(NAME, "on_demand/threads.json"))
    assert report.quotes_dropped == 1 and report.extracted == len(TEAPOT_THREADS)
    for tid, item in bundle.threads.items():
        extraction = Extraction.model_validate_json(item.extraction)
        assert extraction.extractor == "gemini:gemini-3.1-flash-lite"
        kept = check_extraction(extraction, Thread.model_validate_json(item.thread)).kept
        assert all(m.comment_id != MISQUOTED[0] for m in kept)  # the misquote never reaches an answer


# --- the visitor's wait, with the new reader's numbers ---

class Line:
    """A site whose queue already holds some waiting requests and some usage; asks for the teapot and says what it's told."""

    def __init__(self, tmp_path, waiting=0, calls_used=0, seconds_used=0):
        self.google = FakeGoogle()
        self.bucket = Bucket(NAME, request=self.google, clock=lambda: 0.0, prefix=on_demand.PREFIX)
        self.site = SiteReader(self.bucket, tmp_path / "site", job=JobStarter(JOB, self.bucket, request=self.google),
                               clock=Ticks(), now=lambda: NOW)
        ahead = [Entry(key=f"kitchen/gadget {n}/", category="kitchen", product_type=f"gadget {n}",
                       subreddits=["BuyItForLife"]) for n in range(waiting)]

        def prepare(queue: Queue):
            queue.entries.extend(ahead)
            queue.usage_now(NOW).update(gemini_calls=calls_used, seconds=seconds_used)

        QueueStore(self.bucket).change(prepare)

    def asked(self, request="teapot for loose leaf tea") -> dict:
        result = types.SimpleNamespace(query=parse_query(request), threads_available=0, own_threads_available=0,
                                       newest_own_thread=None)
        return self.site.after_answer(result).state


def test_a_request_takes_about_21_minutes_of_the_job_with_the_fast_reader():
    # A Flash-Lite call took 10 to 25 seconds on 25 Oct 2026; a safe minute a call, 15 calls and 6 minutes of Arctic
    # Shift's paced reads: 21 minutes, the first one's wait 4 minutes more (the site's next ping).
    assert config.ON_DEMAND_CALL_MINUTES == 1 and config.ON_DEMAND_PRODUCT_MINUTES == 21
    assert (config.ON_DEMAND_FIRST_MINUTES, config.ON_DEMAND_EACH_MINUTES) == (25, 21)


def test_the_first_request_is_told_about_25_minutes(tmp_path):
    state = Line(tmp_path).asked()
    assert state["check_back_minutes"] == 25
    assert state["message"] == "We haven't read Reddit about teapots yet, so we've started: check back in about 25 minutes."


def test_the_days_capacity_in_the_wait_message_is_the_calls_over_a_requests_calls():
    assert on_demand.products_a_day() == 450 // config.ON_DEMAND_CALLS_PER_PRODUCT == 30


def test_in_line_past_the_days_calls_the_message_says_30_a_day(tmp_path):
    used = config.ON_DEMAND_GEMINI_CALLS_A_DAY  # nothing left today, plenty of the month's time
    state = Line(tmp_path, waiting=2, calls_used=used).asked()
    assert state["message"] == (
        "We haven't read Reddit about teapots yet. It's in line: 2 products are ahead of it, and our free reading "
        "allowance covers about 30 a day. Check back tomorrow.")


def test_when_the_months_time_is_what_runs_out_the_capacity_is_told_by_the_month_not_the_day(tmp_path):
    # 50,000 seconds of job time a month read 39 requests of 21 minutes: it is the month's time, not Gemini's 450
    # calls, that limits the reading, so "about 30 a day" next to "check back on 1 November" would not be true.
    assert on_demand.products_a_month() == config.ON_DEMAND_MONTH_SECONDS // (21 * 60) == 39
    left = config.ON_DEMAND_MONTH_SECONDS - 21 * 60  # one request's time left this month
    state = Line(tmp_path, waiting=3, seconds_used=left).asked()
    assert state["message"] == (
        "We haven't read Reddit about teapots yet. It's in line: 3 products are ahead of it, and our free reading "
        "allowance covers about 39 a month. Check back on 1 November.")
    assert "a day" not in state["message"]


def test_the_month_out_and_nobody_ahead_keeps_the_used_up_message(tmp_path):
    state = Line(tmp_path, waiting=0, seconds_used=config.ON_DEMAND_MONTH_SECONDS).asked()
    assert state["message"] == ("We haven't read Reddit about teapots yet. It's on our list, but our free reading "
                                "allowance is used up for now: check back on 1 November.")


# --- the deploy switch ---

def switch_state(tmp_path, switch):
    """on_demand.sh's on_demand_secret on its own (as deploy.sh runs it) with the key there, CREDIBLE_RECS_ON_DEMAND
    set to `switch` (None: not set): what ON_DEMAND became."""
    import os
    import subprocess

    gcloud = tmp_path / "gcloud"
    gcloud.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    gcloud.chmod(0o755)
    env = {"PATH": os.environ["PATH"], "GCLOUD": str(gcloud)}
    if switch is not None:
        env["CREDIBLE_RECS_ON_DEMAND"] = switch
    shell = (f'set -eu\nPROJECT=made-up\nREGION=europe-west1\n. "{REPO / "deploy/cloudrun/on_demand.sh"}"\n'
             'on_demand_secret\necho "$ON_DEMAND"\n')
    done = subprocess.run(["sh", "-c", shell], capture_output=True, text=True, check=True, env=env)
    return done.stdout.strip(), done.stderr


@pytest.mark.parametrize("switch", [None, "", "on"])
def test_on_demand_reading_is_on_for_a_deploy_unless_it_says_off(tmp_path, switch):
    state, said = switch_state(tmp_path, switch)
    assert state == "on" and said == ""


# --- 2. Voice rubric: paid promotion behind a redirect, and a brand worker's sign-off ---

def voice_of(body: str, name: str = "made_up_writer"):
    author = {"name": name, "account_created_at": "2015-01-01", "karma": 50_000, "flair": None}
    comments = [make_comment("c1aaaa", body=body, author=author, score=40, created_at="2026-09-01T10:00:00Z")]
    comments += [make_comment(f"o{i}other", body="Nice thread.", score=1, created_at="2026-09-01T10:00:00Z")
                 for i in range(4)]
    thread = Thread.model_validate(make_thread(category="general", community="BuyItForLife", comments=comments,
                                               created_at="2026-09-01T10:00:00Z", collected_at="2026-10-06"))
    return score_voice(thread.comments[0], thread)


def red_flags(voice) -> dict[str, int]:
    return {sign.name: sign.red_flags for sign in voice.signs if sign.kind == "red flag"}


@pytest.mark.parametrize("link", [
    "https://made-up-reviews.example/dp-B0ABCDEFGH",  # an Amazon product code behind a site that isn't Amazon
    "https://deals-for-nobody.example/dp-B0ABCDEFGHOP",  # the code with letters added
    "https://Another-Made-Up.example/dp-b0abcdefgh?ref=x",  # any capitals, a query
])
def test_an_amazon_product_behind_a_lookalike_redirect_is_paid_promotion(link):
    # The 25 Oct 2026 round's four near-identical plugs (found by the extraction helpers) linked such pages: the same
    # shape as the redirects round 2 listed by host (ra-sl.com), under other names.
    voice = voice_of(f"For that I'd get the [Made-up Watch X]({link}), it is cheap and good.")
    assert red_flags(voice) == {"salesy language": config.PAID_PROMOTION_RED_FLAGS}
    assert voice.level == "low"


@pytest.mark.parametrize("link", [
    "https://www.amazon.com/dp/B0ABCDEFGH",  # a shopper's plain product link
    "https://www.amazon.co.uk/dp/B0ABCDEFGH?ref=cm_sw_r_cp",
    "https://made-up-reviews.example/dp-notes-on-things",  # "dp-" but no product code
    "https://made-up-reviews.example/adp-B0ABCDEFGH",  # not the segment "dp-"
    "https://made-up-reviews.example/guides/watch-reviews",
])
def test_other_links_are_no_promotion(link):
    assert red_flags(voice_of(f"I bought [this one]({link}) and love it.")) == {}


def test_the_redirect_is_one_paid_promotion_flag_not_two():
    both = ("See [it](https://made-up-reviews.example/dp-B0ABCDEFGH) or [that]"
            "(https://deals-for-nobody.example/dp-B0ZZZZZZZZ).")
    assert red_flags(voice_of(both)) == {"salesy language": config.PAID_PROMOTION_RED_FLAGS}


@pytest.mark.parametrize("closing", [
    "- Dana at Northwind",
    "\\- Dana at Northwind Telecom",  # markdown-escaped, as writers paste it
    "— Dana Fry at Northwind",
    "~ Dana from the Northwind team",
    "- Dana from Northwind Support",
])
def test_a_sign_off_naming_the_brand_the_writer_works_at_promotes_one_brand(closing):
    body = f"Honestly the Made-up Watch X is the best for everyday use.\n\n{closing}"
    voice = voice_of(body, name="Northwind_uk")
    assert red_flags(voice) == {"promotes one brand": 1}
    assert voice.level == "medium"  # one red flag caps the voice at medium (Noemi, 9 Oct 2026)


@pytest.mark.parametrize("body", [
    "I met Dana at Northwind Park last week and she loves hers.",  # not a closing line
    "The Made-up Watch X is good.\n\n- Dana from Ohio",  # a place, not a brand's team
    "The Made-up Watch X is good.\n\n- Dana at home",  # not a brand
    "The Made-up Watch X is good.\n\n- thanks at last",  # no capitals: not a name and a brand
    "The Made-up Watch X is good.\n\n- Dana at Northwind, and then more words follow here",  # a sentence
    "- Dana at Northwind sells these\n- Sam at Southwind sells those\n\nI'd go with the Made-up Watch X.",  # a list
])
def test_an_ordinary_line_naming_a_name_and_a_place_is_no_sign_off(body):
    assert red_flags(voice_of(body)) == {}


def test_a_sign_off_and_saying_so_in_words_are_still_one_flag():
    body = "I work for the company that makes it, and it is great.\n\n- Dana at Northwind"
    assert red_flags(voice_of(body)) == {"promotes one brand": 1}


# --- 3. The wordings she approved are no longer PROPOSED ---

def block(path: str, start: str, end: str) -> str:
    text = (REPO / path).read_text(encoding="utf-8")
    first = text.index(start)
    return text[first:text.index(end, first)]


APPROVED = "approved by Noemi, 25 Oct 2026"


@pytest.mark.parametrize("path, start, end", [
    # The region lines: "{amount} in the UK, at ...", "... in the US ...", "Sold in the UK at ...", "Sold in the US at ..." and
    # "Availability in the US not checked yet". Two others ("From ...", second-hand) were not on her list: still PROPOSED.
    ("engine/answer.py", "# A region other than the UK (Noemi, 24 Oct 2026", "# Two more lines of the region work"),
    # The control: "Shopping from" and its hint.
    ("engine/templates/search.html", "// Region (24 Oct 2026", "examplesHeading:"),
    # The on-demand wait message.
    ("engine/on_demand.py", "# --- Wording visitors see", "def _now()"),
])
def test_the_approved_wordings_say_so_and_are_not_proposed(path, start, end):
    text = block(path, start, end)
    assert "PROPOSED" not in text and APPROVED in text, path


def test_the_region_lines_she_did_not_list_stay_proposed():
    text = block("engine/answer.py", "# Two more lines of the region work", "# Products' own pages and their makers' images")
    assert "PROPOSED" in text and "PRICE_FROM_IN_UK" in text and "AVAILABILITY_IN_UK_SECOND_HAND" in text
