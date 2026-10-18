"""The site tells its reading ahead which comments its answers showed (17 Oct 2026, the converge round, item 2).

The daily plan can't know what visitors ask; the site does, for the answers it works out, so their comments are read
again first (engine.read_ahead.ReadAhead.shown) and the next visitor asking the same finds every check ready. Links
only, in memory only: the request itself never goes there. Made-up kettle threads: no test reaches the network.
"""

import json

import pytest

from engine import web
from engine.answer import quotes_to_check
from engine.pipeline import answer_request
from engine.tests.test_web import REQUEST, ask, kettle_library


class Noting:
    """A stand-in for the site's reading ahead: what it was told."""

    def __init__(self):
        self.told: list[list[str]] = []

    def shown(self, urls):
        self.told.append(list(urls))


@pytest.fixture
def noting(monkeypatch):
    found = Noting()
    monkeypatch.setattr(web, "read_ahead", found)
    web.clear_answer_cache()
    yield found
    web.clear_answer_cache()


def test_a_fresh_answer_tells_reading_ahead_every_comment_it_showed(tmp_path, noting):
    library = kettle_library(tmp_path)
    status, _, data = ask(REQUEST, library)
    assert status == 200 and data["answer"]["picks"]
    shown = [quote.url for quote in quotes_to_check(answer_request(REQUEST, library).answer)]
    assert noting.told == [shown] and all("reddit.com" in url for url in shown)
    assert all(REQUEST not in url for url in shown)  # links only: never the request


def test_a_remembered_answer_tells_it_nothing_more(tmp_path, noting):
    library = kettle_library(tmp_path)
    ask(REQUEST, library)
    ask(REQUEST, library)
    assert len(noting.told) == 1


def test_an_answer_with_nothing_to_show_tells_it_nothing(tmp_path, noting):
    status, _, data = ask("a vague thing", kettle_library(tmp_path))
    assert status == 200 and data["answer"] is None and noting.told == []
