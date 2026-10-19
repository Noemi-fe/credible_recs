"""The 48-hour rule for remembered answers (17 Oct 2026, the converge round's item 1).

A quote is shown only with a passing live check from the last 48 hours (CLAUDE.md, Noemi's decisions of 9 and 13 Oct
2026). An answer accepts checks up to 48 hours old, often made ahead of time, and was then remembered for
web.ANSWER_KEEP_HOURS (24), so a remembered answer could show a check about 72 hours old (the website review of 16 Oct
2026). Now an answer is remembered at most until its oldest shown quote's check turns 48 hours old, and never past
ANSWER_KEEP_HOURS; one with a shown quote whose check can't be found isn't remembered at all. Made-up kettle threads and
made-up embed pages: no test reaches the network.
"""

import io
import json
from datetime import timedelta

import pytest

from engine import web
from engine.answer import quotes_to_check
from engine.config import CACHE_MAX_AGE_HOURS
from engine.live_check import LiveChecker, LiveResult
from engine.pipeline import answer_request
from engine.tests.test_live_check import Clock, page
from engine.tests.test_web import REQUEST, kettle_library


class Reddit:
    """Made-up embed pages: each comment of the made-up library as it was saved."""

    def __init__(self, library_dir):
        self.bodies = {c["id"]: c["body"] for path in (library_dir / "threads").glob("*.json")
                       for c in json.loads(path.read_text(encoding="utf-8"))["comments"]}
        self.asked: list[str] = []

    def __call__(self, url, headers):
        self.asked.append(url)
        comment = url.split("/comment/")[1].split("/")[0]
        return 200, page(self.bodies[comment])


@pytest.fixture
def site(tmp_path, monkeypatch):
    """The site's two clocks moved together: its own seconds (web._clock, time.monotonic on the server) and the live
    checker's time; and the answers worked out, counted."""

    class Site:
        library = kettle_library(tmp_path)
        clock = Clock()
        seconds = [50_000.0]
        answered: list[str] = []

        def __init__(self):
            self.reddit = Reddit(self.library)
            self.live = LiveChecker(cache_dir=tmp_path / "checks", fetch=self.reddit, clock=self.clock,
                                    sleep=self.clock.sleep, min_interval=0)

        def wait(self, hours: float) -> None:
            self.clock.now += timedelta(hours=hours)
            self.seconds[0] += hours * 3600

        def ask(self) -> tuple[int, str, bytes]:
            body = json.dumps({"request": REQUEST}).encode("utf-8")
            return web.handle_answer("application/json", str(len(body)), io.BytesIO(body).read, self.library)

        def shown_links(self) -> set[str]:
            return {q.url for q in quotes_to_check(answer_request(REQUEST, self.library, live_checker=self.live).answer)}

    scene = Site()

    def counting(request, library_dir, **settings):
        scene.answered.append(request)
        return answer_request(request, library_dir, **settings)

    monkeypatch.setattr(web, "answer_request", counting)
    monkeypatch.setattr(web, "_clock", lambda: scene.seconds[0])
    monkeypatch.setattr(web, "live", scene.live)
    web.clear_answer_cache()
    yield scene
    web.clear_answer_cache()


def test_an_answer_on_checks_made_ahead_is_remembered_only_until_its_oldest_check_turns_48_hours_old(site):
    links = site.shown_links()  # every comment the answer shows, read on Reddit now (as reading ahead does)
    site.wait(30)  # 30 hours on, a visitor asks: the answer finds those checks, 30 hours old, and reads nothing
    asked = len(site.reddit.asked)
    assert site.ask()[0] == 200 and len(site.reddit.asked) == asked and links
    site.wait(48 - 30 - 0.01)
    site.ask()
    assert site.answered == [REQUEST]  # still remembered: its oldest check is just under 48 hours old
    site.wait(0.02)
    site.ask()
    assert site.answered == [REQUEST, REQUEST]  # 18 hours on, not 24: the checks it showed have run out
    assert len(site.reddit.asked) > asked  # and the new answer read its comments again


def test_an_answer_on_fresh_checks_is_still_remembered_for_a_day_at_most(site):
    site.ask()
    site.wait(web.ANSWER_KEEP_HOURS - 0.01)
    site.ask()
    assert site.answered == [REQUEST]
    site.wait(0.02)
    site.ask()
    assert site.answered == [REQUEST, REQUEST]


def test_the_oldest_of_the_shown_checks_decides(site):
    links = sorted(site.shown_links())  # all read now
    site.wait(40)
    for link in links[1:]:  # every comment read again but one, whose check is now 40 hours old
        assert site.live.read_if_free(link, max_age=timedelta(0)) == "read"
    site.ask()
    site.wait(8 - 0.01)
    site.ask()
    assert site.answered == [REQUEST]
    site.wait(0.02)
    site.ask()
    assert site.answered == [REQUEST, REQUEST]


class NoSavedCheck:
    """A checker whose checks pass but whose saved checks can't be found afterwards (a folder wiped meanwhile, say)."""

    def __init__(self, clock):
        self.clock = clock

    def check(self, url, quote, wait=True, **settings):
        return LiveResult("ok", "the comment still says this")

    def checked_at(self, url, max_age=None):
        return None

    def now(self):
        return self.clock.now


def test_an_answer_whose_shown_check_cant_be_found_isnt_remembered(site, monkeypatch):
    monkeypatch.setattr(web, "live", NoSavedCheck(site.clock))
    assert site.ask()[0] == 200
    site.ask()
    assert site.answered == [REQUEST, REQUEST]  # worked out again: nothing says how old its checks are


def test_the_rule_is_the_live_checks_48_hours():
    assert CACHE_MAX_AGE_HOURS == 48 and web.ANSWER_KEEP_HOURS < CACHE_MAX_AGE_HOURS
