"""The redesigned search page (13 Oct 2026, the UX builder; Noemi: "something way nicer and advanced without sacrificing
the speed of the service"): the numbers its credibility meter and its reading strip draw, its size budget, and the
rules the new parts keep (nothing from Reddit as HTML, no score breakdown on the page, nothing typed in the page's
title, only the visitor's own requests in the browser's storage, quotes never cut).

Every text is made up. No test reaches the network.
"""

import dataclasses
import re

from engine import web
from engine.answer import DOWNSIDES_SHARE, write_answer
from engine.pipeline import answer_request
from engine.rank import rank_products
from engine.tests.ranking_factories import bodies_for, mention, mentions
from engine.tests.test_web import REQUEST, ask, kettle_library
from engine.tests.test_web_public import function_body, page_text, script_of, settings_of

# The whole search page as the public site serves it (visit counting on, its longest form), in bytes, uncompressed. The
# redesign's budget: the page is one request with everything inline, so its size is most of its loading time.
PAGE_BUDGET_BYTES = 120 * 1024


def setup_function():
    web.clear_answer_cache()


def teardown_function():
    web.clear_answer_cache()


# --- The credibility meter's numbers: "voices" in the API ---

def test_each_pick_says_its_credible_voices_as_numbers_that_match_its_words(tmp_path):
    _, _, data = ask(REQUEST, kettle_library(tmp_path))
    for pick in data["answer"]["picks"]:
        voices = pick["voices"]
        assert set(voices) == {"recommend", "high", "medium", "warn", "threads"}
        assert voices["high"] + voices["medium"] == voices["recommend"]
        assert pick["reason"].startswith(f"Recommended by {voices['recommend']} credible voices")
        assert pick["support"].endswith(f"across {voices['threads']} threads.")
        assert voices["warn"] == 0 and pick["downsides"] == [] and pick["downsides_share"] is None


def test_the_meters_warnings_are_the_share_lines_writers_with_the_brands_own_included():
    # A brand pick shows warnings about its own products under it too (the share line counts them): the meter counts the
    # same writers, so the bar and the words never give different numbers.
    praise = mentions(4, "Acme pans")
    own = [mention("Acme pans", "t1", stance="warn", voice="medium", quote=f"Acme pans chipped, writer {n}.")
           for n in range(2)]
    line = [mention("Acme Pro pan", "t2", stance="warn", voice="medium", quote="The Acme Pro pan warped.")]
    items = praise + own
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items, *line), "frying pan",
                          more_downsides={"acme-pans": line})
    pick = answer.picks[0]
    assert pick.voices == {"recommend": 4, "high": 4, "medium": 0, "warn": 3, "threads": 2}
    assert pick.downsides_share == DOWNSIDES_SHARE.format(n=3, total=3 + 4)


def test_an_also_worth_a_look_item_says_its_voices_too():
    praise = mentions(3, "Acme pan") + mentions(2, "Brio pan", voice="medium")
    answer = write_answer(rank_products(praise, "kitchen"), bodies_for(*praise), "frying pan")
    (item,) = answer.worth_a_look
    assert item.name == "Brio pan"
    assert item.voices == {"recommend": 2, "high": 0, "medium": 2, "warn": 0, "threads": 2}


# --- The reading strip: whether more threads were read ---

def test_the_reading_says_whether_the_answer_read_more_threads_than_usual(tmp_path, monkeypatch):
    # Noemi's testing, 13 Oct 2026: "Based on 16 Reddit threads ... of 25 threads saved" confused her. The strip says the
    # threads read are the most relevant ones, and, when the first ones gave too few picks, that more were read.
    _, _, data = ask(REQUEST, kettle_library(tmp_path))
    assert data["reading"]["read_more"] is False

    def wider(request, library_dir):
        return dataclasses.replace(answer_request(request, library_dir), read_more=True)

    monkeypatch.setattr(web, "answer_request", wider)
    _, _, data = ask(REQUEST, kettle_library(tmp_path / "again"))
    assert data["reading"]["read_more"] is True


# --- Size and speed ---

def test_the_page_stays_within_its_size_budget(tmp_path):
    biggest = web.Site(public=True, hosts=("demo.example",), goatcounter="credible-recs")
    assert len(web.search_page(biggest)) <= PAGE_BUDGET_BYTES
    assert len(page_text(tmp_path, "/how", biggest).encode("utf-8")) <= PAGE_BUDGET_BYTES
