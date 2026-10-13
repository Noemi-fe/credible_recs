"""A product-facts entry's formula (13 Oct 2026): what the product is made with (its actives) and its form, from its
maker's page, with sources and a date of its own. Every entry and link here is made up, except the check that the
committed list loads."""

import json

import pytest

from engine.product_facts import DEFAULT_PRODUCT_FACTS, ProductFactsError, load_product_facts
from engine.tests.test_product_facts import entry, write_facts

FORMULA = {"actives": ["salicylic acid", "papain"], "form": "rinse-off powder",
           "sources": ["https://facts.example/powder"], "checked_on": "2026-10-13"}


def test_an_entry_may_say_what_its_product_is_made_with(tmp_path):
    [loaded] = load_product_facts(write_facts(tmp_path, [entry(product_type="exfoliant", formula=FORMULA)]))
    assert loaded.formula.actives == ["salicylic acid", "papain"]
    assert loaded.formula.form == "rinse-off powder"
    assert str(loaded.formula.checked_on) == "2026-10-13"
    assert str(loaded.checked_on) == "2026-10-09"  # the entry's other facts keep their own date


def test_an_entry_with_a_formula_needs_no_other_fact(tmp_path):
    [loaded] = load_product_facts(write_facts(tmp_path, [entry(product_type="cleanser", facts={}, formula=FORMULA)]))
    assert loaded.facts == {}


def test_an_entry_with_neither_facts_nor_a_formula_is_refused(tmp_path):
    with pytest.raises(ProductFactsError, match="at least one fact"):
        load_product_facts(write_facts(tmp_path, [entry(facts={})]))


@pytest.mark.parametrize("change, problem", [
    ({"actives": ["salycilic acid"]}, "salycilic acid"),  # a typo would silently drop an active
    ({"form": "goo"}, "goo"),
    ({"sources": ["http://facts.example/powder"]}, "https://"),
    ({"sources": []}, "sources"),
    ({"actives": []}, "actives"),
])
def test_a_formula_that_doesnt_fit_is_refused_with_its_problem(tmp_path, change, problem):
    with pytest.raises(ProductFactsError, match=problem):
        load_product_facts(write_facts(tmp_path, [entry(product_type="exfoliant", formula=FORMULA | change)]))


def test_the_committed_list_still_loads_and_its_formulas_have_sources():
    entries = load_product_facts(DEFAULT_PRODUCT_FACTS)
    with_formula = [e for e in entries if e.formula is not None]
    assert all(e.formula.sources for e in with_formula)
    raw = json.loads(DEFAULT_PRODUCT_FACTS.read_text(encoding="utf-8"))["facts"]
    assert len(raw) == len(entries)
