"""Kitchen data round of 17 Oct 2026 (the ws-data-kitchen builder): the committed lists' kitchen entries this round
added or changed, checked against what the answers need from them.

1. Noemi's decision 8 of 16 Oct 2026: Circulon's and Ballarini's price-list and facts names ("Circulon pans",
   "Ballarini non-stick pans") become brand lines, so a PFAS-free frying-pan answer keeps only the pans whose facts
   confirm it: both makers' UK ranges mix ceramic pans made without PFAS with PTFE non-stick ones, and a whole brand
   can't be checked (decided 10 Oct 2026).
2. PFAS research (her rule of 11 Oct 2026: a coating its maker names as PTFE, or says contains PFAS, answers
   pfas_free: false): Le Creuset's Toughened Non-Stick is a PFAS coating by its maker's own page; Our Place makes its
   cookware without PFAS.

Most tests read the committed lists (data/); the one answering a request uses a made-up library in a temporary folder
with the committed lists, so it shows what the lists change in an answer.
"""

from datetime import date

import pytest

from engine.brand_lines import find_brand_line, load_brand_lines
from engine.pipeline import answer_request
from engine.prices import find_availability, find_price, load_prices
from engine.product_facts import NotSuited, find_brand_facts, find_facts, load_product_facts
from engine.product_pages import find_page, load_product_pages
from engine.tests.test_pipeline import praise, write_library

TODAY = date(2026, 10, 17)
PAN_WORDS = ("frying pan", "frying pans", "pan", "pans")  # the request's type words, as the pipeline passes them


# --- 1. Circulon and Ballarini are brand lines (Noemi's decision 8 of 16 Oct 2026) ---

def test_circulon_and_ballarini_have_brand_lines_entries_with_a_range_page_and_a_from_price():
    lines = load_brand_lines()
    for written, brand, site in [("Circulon", "Circulon", "circulon.uk.com"), ("Circulon pans", "Circulon", "circulon.uk.com"),
                                 ("Ballarini", "Ballarini", "zwilling.com"), ("Ballarini pans", "Ballarini", "zwilling.com")]:
        line = find_brand_line([written], "kitchen", "frying pan", lines)
        assert line is not None and line.brand == brand and line.sells, written
        assert line.range_page and site in line.range_page, written
        assert line.from_price and line.from_price_shop and line.from_price_url and line.from_price_checked_on, written


def test_their_old_product_names_are_gone_from_the_price_and_facts_lists():
    # A name in either list was treated as one product ("Circulon pans" was a pick of b10 with a PFAS note); a brand
    # line has no single price (its from price is in the brand-lines list) and no facts entry.
    prices, facts = load_prices(), load_product_facts()
    for old in ("Circulon pans", "Ballarini non-stick pans"):
        assert find_price(old, "kitchen", prices, product_type="frying pan") is None, old
        assert find_availability(old, "kitchen", prices, product_type="frying pan") is None, old
        assert find_facts(old, "kitchen", facts, "frying pan") is None, old


def test_no_facts_entry_speaks_for_either_whole_brand():
    # Both UK ranges mix ceramic pans made without PFAS (Circulon Halo; Ballarini Bologna, Ledro, Salina) with PTFE
    # non-stick ones, so neither brand's line can be confirmed PFAS-free: under a must-have it is left out, as a whole
    # brand can't be checked (decision 8: "keeps only GreenPan until more PFAS-free pans are researched").
    facts = load_product_facts()
    for names in (["Circulon", "Circulon pans", "Circulon pan"], ["Ballarini", "Ballarini pans"]):
        assert find_brand_facts(names, "kitchen", facts, PAN_WORDS, "frying pan") is None, names


def test_their_pages_are_listed_under_the_lines_names():
    pages = load_product_pages()
    for shown, site in (("Circulon frying pan line", "circulon.uk.com"), ("Ballarini frying pan line", "zwilling.com")):
        page = find_page([shown], "kitchen", "frying pan", pages)
        assert page is not None and site in page.page, shown


# --- 2. PFAS research ---

def test_le_creusets_toughened_non_stick_contains_pfas_by_its_makers_page():
    facts = load_product_facts()
    for written in ('Le Creuset "toughened non-stick" pan', "Le Creuset “toughened” non-stick", "LeCreuset non-stick"):
        entry = find_facts(written, "kitchen", facts, "frying pan")
        assert entry is not None, written
        assert entry.facts.get("pfas_free") is False and entry.facts.get("non_stick") is True, written
        assert any("lecreuset" in source for source in entry.sources), written


def test_our_places_pans_are_made_without_pfas():
    facts = load_product_facts()
    for written, product in (("Always Pan", "Our Place Always Pan"), ("OurPlace Always Pan", "Our Place Always Pan"),
                             ("titanium always pan pro", "Our Place Titanium Always Pan Pro")):
        entry = find_facts(written, "kitchen", facts, "frying pan")
        assert entry is not None and entry.product == product, written
        assert entry.facts.get("pfas_free") is True and entry.facts.get("non_stick") is True, written
        assert any("fromourplace" in source for source in entry.sources), written


# --- What the lists change in an answer ---

def pfas_library(tmp_path):
    """Two frying-pan threads in which GreenPan, Circulon, Ballarini and Le Creuset's toughened non-stick pans are each
    praised by three writers across both threads (made-up comments), as in b10's threads: writers name Circulon and
    Ballarini by brand only ("Circulon pans", "Ballarini"), never a model."""
    return write_library(tmp_path, {
        "1pfas01": ("Non-stick frying pan without PFAS?", "Replacing my old ones.", [
            praise("g1a", "GreenPan", 4), praise("g1b", "GreenPan", 5),
            praise("c1a", "Circulon pans", 6), praise("c1b", "Circulon", 7),
            praise("b1a", "Ballarini pans", 5), praise("b1b", "Ballarini", 6),
            praise("l1a", "Le Creuset toughened non-stick pan", 3), praise("l1b", "Le Creuset toughened non-stick pan", 4),
        ]),
        "1pfas02": ("Which non-stick pan lasts?", "Ten years, ideally.", [
            praise("g2a", "GreenPan", 6), praise("c2a", "Circulon pans", 8), praise("b2a", "Ballarini pans", 9),
            praise("l2a", "Le Creuset toughened non-stick pan", 5),
        ]),
    }, community="BuyItForLife")


def pfas_answer(tmp_path):
    return answer_request("non-stick frying pan without PFAS that lasts", library_dir=pfas_library(tmp_path),
                          prices=load_prices(), product_facts=load_product_facts(), brand_lines=load_brand_lines(),
                          product_pages=load_product_pages(), today=TODAY, more_threads=None)


def shown_names(result) -> list[str]:
    return [pick.name for pick in result.answer.picks] + [item.name for item in result.answer.worth_a_look]


def test_le_creusets_toughened_non_stick_leaves_a_pfas_free_answer_and_greenpan_stays(tmp_path):
    # Le Creuset's toughened non-stick was under Also worth a look in "non stick pan without teflon that lasts" (16 Oct
    # sweep): its maker's own page says it contains PFAS, so it is left out, with the reason.
    result = pfas_answer(tmp_path)
    assert result.answer.picks[0].name.startswith("GreenPan")
    assert not any("Le Creuset" in name for name in shown_names(result))
    assert NotSuited("Le Creuset toughened non-stick pan", "it isn't PFAS-free") in result.left_out_not_suited


@pytest.mark.xfail(strict=True, reason="Noemi's decision 8 needs module 4 or the pipeline too (ws-names / ws-ranking, "
                   "written down for the integrator, 17 Oct 2026): a group none of whose names names a model, whose "
                   "brand has a brand-lines entry selling the requested type, is ranked as that brand's line. Until "
                   "then module 4 keeps a brand with no model named as one product (group_products._lines_of_the_type)")
def test_circulon_and_ballarini_are_left_out_of_a_pfas_free_answer_as_whole_brands(tmp_path):
    result = pfas_answer(tmp_path)
    assert not any(word in name for name in shown_names(result) for word in ("Circulon", "Ballarini"))
    left_out = {item.name: item.reason for item in result.left_out_not_suited}
    assert left_out["Circulon frying pan line"] == left_out["Ballarini frying pan line"] == (
        "a whole brand can't be checked for PFAS or a non-stick coating")
