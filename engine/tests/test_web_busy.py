"""A busy site (3 Nov 2026, the pre-launch load fix for the Show HN of about 10 Nov).

Fresh answers are worked out one at a time (engine.web._answers_lock). Firebase Hosting in front of Cloud Run cuts any
request at 60 s, and the per-visitor rate limit does nothing against many visitors at once. So, on the public site only:

- an answer that is not remembered and would have to queue is refused at once (503, code "busy", with Retry-After) when
  BUSY_MAX_WAITING visitors already wait for their turn, or when its turn doesn't come within BUSY_MAX_QUEUE_SECONDS;
  a remembered answer is never refused, and warming (which also takes turns) is never refused either;
- no answer is waited on past ANSWER_DEADLINE_SECONDS after the request arrived, queue time included: once it is up, no
  Reddit read is waited for. A quote that needed a read not made is never shown unchecked. "Also worth a look" and the
  summaries are left out (the answer isn't remembered); an answer whose picks can't be checked in time is "busy".

Local mode is exactly as before. Every library, page and clock here is made up: no test reaches the network.
"""

import contextlib
import io
import json
import re
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest

from engine import pipeline, web
from engine.answer import needed_quotes
from engine.live_check import LiveChecker
from engine.pipeline import answer_request
from engine.tests.test_live_check import Clock, page
from engine.tests.test_pipeline import comment, mention
from engine.tests.test_web import REQUEST, kettle_library, post_answer
from engine.tests.test_web_public import PUBLIC, public_send, start, stop

ASKED = {"Content-Type": "application/json"}


@pytest.fixture(autouse=True)
def nobody_waiting(monkeypatch):
    """Each test starts with no remembered answers and nobody queued."""
    web.clear_answer_cache()
    monkeypatch.setattr(web, "_visitors_waiting", 0)
    yield
    assert not web._answers_lock.locked(), "a test left the answers' turn taken"
    web.clear_answer_cache()


@contextlib.contextmanager
def holding_the_turn():
    """The answers' lock taken, as an answer being worked out takes it."""
    web._answers_lock.acquire()
    try:
        yield
    finally:
        web._answers_lock.release()


def ask(request: str, library_dir: Path, **settings) -> tuple[int, str, bytes]:
    """A visitor on the public site (guarded: the cap and the deadline apply)."""
    return web.answer_response(request, library_dir, quiet=True, guarded=True, **settings)


def code_of(response: tuple[int, str, bytes]) -> str:
    return json.loads(response[2])["code"]


def wait_until(condition, seconds: float = 10.0) -> None:
    end = time.monotonic() + seconds
    while not condition():
        assert time.monotonic() < end, "waited too long for the test's own condition"
        time.sleep(0.005)


# --- The values and what they rest on ---

def test_the_values_fit_inside_hostings_sixty_seconds():
    # Hosting cuts a request at 60 s (deploy/cloudrun/DEPLOY.md). A visitor refused for waiting too long is refused
    # before the deadline, and what is left of it holds the slowest fresh answer measured through Hosting (21 s,
    # 2 Nov 2026), so a visitor who waited the most can still be answered in time.
    assert 0 < web.BUSY_MAX_QUEUE_SECONDS < web.ANSWER_DEADLINE_SECONDS < 60
    assert web.ANSWER_DEADLINE_SECONDS - web.BUSY_MAX_QUEUE_SECONDS >= 21
    assert web.BUSY_RETRY_AFTER_SECONDS >= 1


def test_the_queue_leaves_cloud_runs_other_places_free():
    # Cloud Run lets deploy.sh's --concurrency requests in at once: the answer being worked out and the visitors queued
    # behind it must leave places for the pages, the keep-warm ping (/ready) and remembered answers.
    script = (Path(__file__).resolve().parents[2] / "deploy" / "cloudrun" / "deploy.sh").read_text(encoding="utf-8")
    places = int(re.search(r"--concurrency (\d+)", script).group(1))
    assert 1 + web.BUSY_MAX_WAITING + 3 <= places


# --- The cap: how many may wait, and for how long ---

def test_a_remembered_answer_is_served_while_the_queue_is_full(tmp_path, monkeypatch):
    library_dir = kettle_library(tmp_path)
    first = ask(REQUEST, library_dir)  # worked out and remembered
    assert first[0] == 200
    monkeypatch.setattr(web, "_visitors_waiting", web.BUSY_MAX_WAITING)
    with holding_the_turn():
        assert ask(REQUEST, library_dir) == first  # no waiting, no refusal


def test_a_new_answer_is_refused_at_once_when_the_queue_is_full(tmp_path, monkeypatch):
    library_dir = kettle_library(tmp_path)
    monkeypatch.setattr(web, "_visitors_waiting", web.BUSY_MAX_WAITING)
    with holding_the_turn():
        started = time.monotonic()
        response = ask(REQUEST, library_dir)
        took = time.monotonic() - started
    assert took < 1 and response[:2] == (503, web.JSON) and code_of(response) == "busy"
    assert json.loads(response[2])["error"]  # plain words for whoever calls the API
    assert web._visitors_waiting == web.BUSY_MAX_WAITING  # a refused visitor was never counted as waiting
    assert not web._answers  # and nothing was worked out or remembered


def test_one_place_short_of_full_a_visitor_still_joins_the_queue(tmp_path, monkeypatch):
    library_dir = kettle_library(tmp_path)
    monkeypatch.setattr(web, "_visitors_waiting", web.BUSY_MAX_WAITING - 1)
    done = []
    with holding_the_turn():
        visitor = threading.Thread(target=lambda: done.append(ask(REQUEST, library_dir)))
        visitor.start()
        wait_until(lambda: web._visitors_waiting == web.BUSY_MAX_WAITING)  # in the queue now: it is full
        assert not done
    visitor.join(20)
    assert done[0][0] == 200 and web._visitors_waiting == web.BUSY_MAX_WAITING - 1  # its turn came; no longer counted


def test_the_queue_holds_so_many_and_refuses_the_next_while_they_all_get_their_answers(tmp_path, monkeypatch):
    library_dir = kettle_library(tmp_path)
    started, release = threading.Event(), threading.Event()

    def slow(request, library_dir, **settings):
        started.set()
        release.wait(30)
        return answer_request(REQUEST, library_dir)

    monkeypatch.setattr(web, "answer_request", slow)
    results = []
    visitors = [threading.Thread(target=lambda n=n: results.append(ask(f"kettle number {n}", library_dir)))
                for n in range(1 + web.BUSY_MAX_WAITING)]
    visitors[0].start()
    assert started.wait(10)  # one answer under way
    for visitor in visitors[1:]:
        visitor.start()
    wait_until(lambda: web._visitors_waiting == web.BUSY_MAX_WAITING)  # and the queue behind it full
    refused = ask("one kettle too many", library_dir)
    assert refused[0] == 503 and code_of(refused) == "busy"
    release.set()
    for visitor in visitors:
        visitor.join(30)
    assert [r[0] for r in results] == [200] * (1 + web.BUSY_MAX_WAITING)  # nobody in the queue was turned away
    assert web._visitors_waiting == 0


def test_a_visitor_who_cannot_take_their_turn_in_time_is_refused(tmp_path, monkeypatch):
    library_dir = kettle_library(tmp_path)
    monkeypatch.setattr(web, "BUSY_MAX_QUEUE_SECONDS", 0.2)
    with holding_the_turn():
        started = time.monotonic()
        response = ask(REQUEST, library_dir)
        took = time.monotonic() - started
    assert response[0] == 503 and code_of(response) == "busy"
    assert 0.15 <= took < 5  # it waited its time, no more
    assert web._visitors_waiting == 0  # no longer counted as waiting
    assert not web._answers


def test_a_visitor_whose_time_ran_out_gets_the_answer_remembered_meanwhile(tmp_path, monkeypatch):
    # The same request, worked out for someone else while this visitor waited: it is theirs too, not "busy".
    library_dir = kettle_library(tmp_path)
    monkeypatch.setattr(web, "BUSY_MAX_QUEUE_SECONDS", 0.5)
    made = (200, web.JSON, b'{"made": "up"}')
    key = (REQUEST, str(library_dir), web.DEFAULT_REGION)
    with holding_the_turn():
        timer = threading.Timer(0.1, lambda: web._answers.__setitem__(key, (web._clock() + 1000, made)))
        timer.start()
        got = ask(REQUEST, library_dir)
        timer.join()
    assert got == made


def test_a_refused_visitor_over_http_is_told_when_to_try_again(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "PUBLIC_HOST", "127.0.0.1")  # the tests never open a port to the network
    server = start(web.make_server(port=0, library_dir=kettle_library(tmp_path), site=PUBLIC))
    try:
        monkeypatch.setattr(web, "_visitors_waiting", web.BUSY_MAX_WAITING)
        with holding_the_turn():
            status, headers, data = public_send(server, "/api/answer", {"request": REQUEST}, headers=ASKED)
    finally:
        stop(server)
    assert status == 503 and data["code"] == "busy"
    assert headers["Retry-After"] == str(web.BUSY_RETRY_AFTER_SECONDS)


def test_the_public_site_is_guarded_and_local_mode_never_is(tmp_path, monkeypatch):
    library_dir = kettle_library(tmp_path)
    monkeypatch.setattr(web, "_visitors_waiting", web.BUSY_MAX_WAITING)
    with holding_the_turn():
        assert post_answer(REQUEST, library_dir, PUBLIC)[0] == 503
    # Local mode (one visitor, no Hosting in front, nothing to cut at 60 s) waits for its turn as it always did.
    assert post_answer(REQUEST, library_dir, web.LOCAL)[0] == 200


# --- Warming takes its turns as before ---

def test_warming_is_never_refused_even_when_the_queue_is_full(tmp_path, monkeypatch):
    asked = []
    monkeypatch.setattr(web, "answer_request", lambda request, library_dir, **settings: asked.append(request))
    monkeypatch.setattr(web, "_visitors_waiting", web.BUSY_MAX_WAITING)
    web.warm_answer("electric kettle", tmp_path)
    assert asked == ["electric kettle"]
    assert web._visitors_waiting == web.BUSY_MAX_WAITING  # warming isn't a visitor in the queue


def test_a_warm_answer_waits_for_its_turn_however_long_it_takes(tmp_path, monkeypatch):
    # A warm answer refused for waiting would leave its request cold for its first visitor: only visitors have a limit.
    asked = []
    monkeypatch.setattr(web, "answer_request", lambda request, library_dir, **settings: asked.append(request))
    monkeypatch.setattr(web, "BUSY_MAX_QUEUE_SECONDS", 0.05)
    web._answers_lock.acquire()
    timer = threading.Timer(0.3, web._answers_lock.release)
    timer.start()
    web.warm_answer("electric kettle", tmp_path)
    timer.join()
    assert asked == ["electric kettle"]


def test_a_visitor_waiting_in_the_queue_still_holds_warming_back(tmp_path, monkeypatch):
    library_dir = kettle_library(tmp_path)
    warmed = []
    monkeypatch.setattr(web, "_left_to_warm", ["a warm request"])
    monkeypatch.setattr(web, "_left_in", [library_dir])
    monkeypatch.setattr(web, "warm_answer", lambda request, library_dir: warmed.append(request))
    done = []
    with holding_the_turn():
        visitor = threading.Thread(target=lambda: done.append(ask(REQUEST, library_dir)))
        visitor.start()
        wait_until(lambda: web._visitors_waiting == 1)
        web.warm_more()
        assert warmed == [] and web._left_to_warm == ["a warm request"]  # it gave way to the visitor
    visitor.join(20)
    assert done[0][0] == 200
    web.warm_more()  # nobody waiting now
    assert warmed == ["a warm request"]


# --- The deadline ---

def add_smeg(library_dir: Path) -> None:
    """The Smeg is praised once in each thread: two credible voices, so "Also worth a look", never a pick."""
    extra = {"1kett01": ("k1smeg", "My Smeg kettle has boiled every morning for 5 years."),
             "1kett02": ("k2smeg", "Our Smeg kettle is 7 years old and still looks new.")}
    for thread_id, (comment_id, text) in extra.items():
        thread_file = library_dir / "threads" / f"{thread_id}.json"
        thread = json.loads(thread_file.read_text(encoding="utf-8"))
        thread["comments"].append(comment(comment_id, thread_id, text))
        thread_file.write_text(json.dumps(thread), encoding="utf-8")
        extraction_file = library_dir / "extracted" / f"{thread_id}.json"
        extraction = json.loads(extraction_file.read_text(encoding="utf-8"))
        extraction["mentions"].append(mention(comment_id, "Smeg kettle", text))
        extraction_file.write_text(json.dumps(extraction), encoding="utf-8")


class Scene:
    """The site with a made-up Reddit and a made-up clock that moves only when something takes time: the engine
    (`engine_takes` seconds a fresh answer), a read of Reddit (`read_takes`), or a read waiting for its turn."""

    def __init__(self, tmp_path, monkeypatch, smeg: bool = False, engine_takes: float = 0.0, read_takes: float = 0.0,
                 parallel: int = 1, **checker):
        self.library = kettle_library(tmp_path)
        if smeg:
            add_smeg(self.library)
        self.clock, self.engine_takes, self.read_takes = Clock(), engine_takes, read_takes
        self.began = self.clock.now
        self.bodies = {c["id"]: c["body"] for path in (self.library / "threads").glob("*.json")
                       for c in json.loads(path.read_text(encoding="utf-8"))["comments"]}
        self.read, self.answered = [], []
        self.live = LiveChecker(cache_dir=tmp_path / "checks", fetch=self.reddit, clock=self.clock,
                                sleep=self.clock.sleep, min_interval=0, **checker)
        monkeypatch.setattr(web, "_clock", self.seconds)
        monkeypatch.setattr(web, "live", self.live)
        monkeypatch.setattr(web, "answer_request", self.engine)
        # One read at a time unless asked: the made-up clock moves as reads wait, which threads would add up.
        monkeypatch.setattr(pipeline, "LIVE_CHECK_PARALLEL", parallel)

    def seconds(self) -> float:
        return (self.clock.now - self.began).total_seconds()

    def reddit(self, url, headers):
        comment_id = url.split("/comment/")[1].split("/")[0]
        self.read.append(comment_id)
        self.clock.now += timedelta(seconds=self.read_takes)
        return 200, page(self.bodies[comment_id])

    def engine(self, request, library_dir, **settings):
        self.answered.append(request)
        self.clock.now += timedelta(seconds=self.engine_takes)
        return answer_request(request, library_dir, **settings)

    def check_ahead(self, quotes) -> None:
        """Their comments read on Reddit now, as the pre-check and reading ahead do; the reads aren't counted."""
        for quote in quotes:
            assert self.live.check(quote.url, quote.text).show
        self.read.clear()

    def ask(self, site: web.Site = PUBLIC) -> tuple[int, str, bytes]:
        body = json.dumps({"request": REQUEST}).encode()
        return web.handle_answer("application/json", str(len(body)), io.BytesIO(body).read, self.library, site)

    def saved_checks(self) -> int:
        return len(list(self.live.cache_dir.glob("*.json")))


def shown_links(data: dict) -> set[str]:
    """Every link the JSON answer shows a quote with (the picks', their downsides and care tips, the rest)."""
    found = set()

    def walk(value):
        if isinstance(value, dict):
            if "comment_id" in value and "url" in value and "text" in value:
                found.add(value["url"])
            for inner in value.values():
                walk(inner)
        elif isinstance(value, list):
            for inner in value:
                walk(inner)

    walk(data["answer"])
    return found


def test_past_the_deadline_what_was_checked_ahead_is_shown_and_the_rest_is_left_out(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch, smeg=True)
    scene.check_ahead(needed_quotes(answer_request(REQUEST, scene.library).answer))  # the picks' comments, not the Smeg's
    scene.engine_takes = 46.0  # the engine alone used up the time
    response = scene.ask(PUBLIC)
    data = json.loads(response[2])
    assert response[0] == 200 and len(data["answer"]["picks"]) == 3
    assert data["answer"]["worth_a_look"] == []  # left out: the checks it needed were not made in time
    assert not {"k1smeg", "k2smeg"} & set(scene.read)  # and Reddit was not asked for them
    assert data["timing"]["put_off"] >= 1
    # Never an unchecked quote: every quote shown has a passing check from the last 48 hours.
    links = shown_links(data)
    assert links and all(scene.live.checked_at(link) is not None for link in links)


def test_the_same_answer_without_a_deadline_shows_also_worth_a_look(tmp_path, monkeypatch):
    # The control for the test above: local mode has no deadline, so the Smeg's checks are made and it is shown.
    scene = Scene(tmp_path, monkeypatch, smeg=True)
    scene.check_ahead(needed_quotes(answer_request(REQUEST, scene.library).answer))
    scene.engine_takes = 46.0
    data = json.loads(scene.ask(web.LOCAL)[2])
    assert [item["name"] for item in data["answer"]["worth_a_look"]] == ["Smeg kettle"]
    assert {"k1smeg", "k2smeg"} <= set(scene.read)


def test_an_answer_cut_short_of_its_extras_is_not_remembered(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch, smeg=True)
    scene.check_ahead(needed_quotes(answer_request(REQUEST, scene.library).answer))
    scene.engine_takes = 46.0
    assert scene.ask(PUBLIC)[0] == 200
    assert scene.ask(PUBLIC)[0] == 200
    assert scene.answered == [REQUEST, REQUEST]  # worked out again the second time: not remembered


def test_past_the_deadline_an_answer_whose_picks_were_not_checked_is_busy_and_reads_nothing(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    scene.engine_takes = 46.0  # nothing checked ahead, and the engine alone used up the time
    response = scene.ask(PUBLIC)
    assert response[:2] == (503, web.JSON) and code_of(response) == "busy"
    assert scene.read == []  # no read was started after the deadline
    assert not web._answers and not web._answers_lock.locked() and web._visitors_waiting == 0


def test_picks_checks_cut_short_while_several_are_read_at_once_are_busy_too(tmp_path, monkeypatch):
    # The live site reads LIVE_CHECK_PARALLEL comments at once: the refusal crosses its threads, and none is left behind.
    scene = Scene(tmp_path, monkeypatch, parallel=8, engine_takes=46.0)
    response = scene.ask(PUBLIC)
    assert response[0] == 503 and code_of(response) == "busy" and scene.read == []
    assert not web._answers and not web._answers_lock.locked() and web._visitors_waiting == 0


def test_the_deadline_falling_in_the_middle_of_the_checks_stops_them_there(tmp_path, monkeypatch):
    # Reddit lets one read through every 10 s (burst 1, refill 10): reads at 0, 10, 20, 30 and 40 s fit in the 45 s
    # deadline, the one at 50 s does not. The answer needs more than five (nine quotes, nine comments).
    scene = Scene(tmp_path, monkeypatch, burst=1, refill=10)
    response = scene.ask(PUBLIC)
    assert response[0] == 503 and code_of(response) == "busy"
    assert len(scene.read) == 5
    assert scene.saved_checks() == 5  # what was read is kept: the visitor's next try finds it checked
    assert not web._answers


def test_without_a_deadline_the_same_slow_reddit_gives_the_whole_answer(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch, burst=1, refill=10)
    response = scene.ask(web.LOCAL)  # local mode: it waits as it always did
    data = json.loads(response[2])
    assert response[0] == 200 and len(data["answer"]["picks"]) == 3 and len(scene.read) >= 9


def test_time_queued_counts_toward_the_deadline(tmp_path, monkeypatch):
    # Arrived 40 s ago (it waited for its turn): 5 s are left, enough for the first read, not for the 10 s wait for the next.
    scene = Scene(tmp_path, monkeypatch, burst=1, refill=10)
    response = web.answer_response(REQUEST, scene.library, quiet=True, guarded=True, arrived=web._clock() - 40)
    assert response[0] == 503 and code_of(response) == "busy"
    assert len(scene.read) == 1


def test_the_request_is_timed_from_the_moment_it_arrived(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "_clock", lambda: 123.0)
    seen = []
    monkeypatch.setattr(web, "answer_response", lambda *args, **settings: seen.append(settings) or (200, web.JSON, b"{}"))
    body = json.dumps({"request": REQUEST}).encode()
    web.handle_answer("application/json", str(len(body)), io.BytesIO(body).read, tmp_path, PUBLIC)
    assert seen[0]["arrived"] == 123.0 and seen[0]["guarded"] is True
    web.handle_answer("application/json", str(len(body)), io.BytesIO(body).read, tmp_path, web.LOCAL)
    assert seen[1]["guarded"] is False


def test_an_answer_checked_in_time_is_whole_and_remembered_as_before(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch, smeg=True)
    first = scene.ask(PUBLIC)
    data = json.loads(first[2])
    assert first[0] == 200 and [item["name"] for item in data["answer"]["worth_a_look"]] == ["Smeg kettle"]
    scene.ask(PUBLIC)
    assert scene.answered == [REQUEST]  # remembered: nothing was cut short


def test_local_mode_has_neither_the_cap_nor_the_deadline(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch, smeg=True, engine_takes=200.0)
    monkeypatch.setattr(web, "_visitors_waiting", 99)
    response = scene.ask(web.LOCAL)
    data = json.loads(response[2])
    assert response[0] == 200 and [item["name"] for item in data["answer"]["worth_a_look"]] == ["Smeg kettle"]


# --- The page ---

def test_the_page_has_words_for_a_busy_site_and_says_who_proposed_them():
    html = web.search_page(PUBLIC).decode("utf-8")
    lines = html.splitlines()
    at = next(n for n, line in enumerate(lines) if re.match(r"\s*busy: \"", line))
    wording = re.match(r"\s*busy: \"(.*?)\"", lines[at]).group(1)
    nearby = " ".join(lines[max(0, at - 3):at + 1])
    assert "3 Nov 2026" in nearby and "Noemi" in nearby and "PROPOSED" in nearby.upper()
    assert "—" not in nearby and "–" not in wording  # no dashes in the page's voice
    assert not re.search(r"\bnot\b.*\bbut\b", wording, re.I)  # and no "not this but that"
    assert "try again" in wording.lower()
    errors = re.search(r"\n  errors: \{(.*?)\n  \},", html, re.DOTALL).group(1)
    assert "busy:" in errors  # with the other errors: the public page uses them too
