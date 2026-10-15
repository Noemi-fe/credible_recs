"""The prescription-only note (Noemi's decision 5 of 14 Oct 2026).

A product whose checked facts say it is prescription-only shows a plain note wherever it is shown, on a pick, under
"Also worth a look" and under "Skip these", in the answer, its text and the page, all in the same words. The fact can be
set on any skincare product type (since 10 Oct 2026 it had been retinoids' and exfoliants' only, which left Duac, a
clindamycin and benzoyl peroxide gel, with no way to say it). Today's rule stays: such a product is left out of a request
for a beginner, a gentle product or sensitive skin. Only for retinoids and exfoliants is not knowing it a requirement
("we couldn't confirm it's sold without a prescription"): for every other type it is recorded when an official source
says so, and never asked for, so a cleanser or a moisturiser answer gets no new note and keeps its brand lines.

Every product, fact, source and library here is made up, but for the one test that checks the committed facts list.
"""

import json
import re
from datetime import date
from urllib.parse import urlsplit

import pytest

from engine import answer as wording
from engine import config, web
from engine.answer import answer_to_dict, render_markdown, unverified_claims
from engine.pipeline import answer_request
from engine.product_facts import (
    DEFAULT_PRODUCT_FACTS,
    Formula,
    ProductFacts,
    ProductFactsError,
    conflicts,
    facts_that_matter,
    hard_requirements,
    load_product_facts,
    unconfirmed,
)
from engine.query import PRODUCT_TYPES, parse_query
from engine.tests.test_pipeline import FakeLive
from engine.tests.test_pipeline_ingredients import ACME, IRIS, KIRI, OPAL, acne_library
from engine.tests.test_product_facts import entry, write_facts

TODAY = date(2026, 10, 9)
NOTE = "Prescription-only in the UK: ask a doctor or pharmacist."
REQUEST = "salicylic acid for acne"


def facts(product: str, product_type: str, prescription_only: bool, form: str | None = None) -> ProductFacts:
    """A made-up entry: the product's prescription status and its formula (it contains salicylic acid)."""
    return ProductFacts(product=product, category="skincare", product_type=product_type,
                        facts={"prescription_only": prescription_only}, sources=["https://facts.example/label"],
                        checked_on=TODAY, formula=Formula(actives=["salicylic acid"], form=form,
                                                          sources=["https://facts.example/formula"],
                                                          checked_on=TODAY))


# The acne library's pick (a spot treatment), its "Also worth a look" item (a toner) and its skip (an exfoliant) are
# prescription-only here; its other pick (a serum) isn't.
def prescribed() -> list[ProductFacts]:
    return [facts(KIRI[0], "spot treatment", True, "patch"), facts(IRIS[0], "toner", True),
            facts(OPAL[0], "exfoliant", True, "gel"), facts(ACME[0], "serum", False)]


def ask(tmp_path, request: str = REQUEST, product_facts=None, live_checker=None):
    product_facts = prescribed() if product_facts is None else product_facts
    return answer_request(request, library_dir=acne_library(tmp_path), prices=[], product_facts=list(product_facts),
                          today=TODAY, live_checker=live_checker)


def notes(answer) -> dict[str, str | None]:
    """Every product the answer shows, with its prescription note (None without one)."""
    items = [*answer.picks, *answer.worth_a_look, *answer.skip]
    return {item.name: item.prescription for item in items}


# --- The fact, on any skincare product ---

@pytest.mark.parametrize("product_type", [p.name for p in PRODUCT_TYPES if p.category == "skincare"])
def test_the_fact_can_be_set_on_every_skincare_product_type(tmp_path, product_type):
    path = write_facts(tmp_path, [entry(product="Made-up Prescription Gel", product_type=product_type,
                                        facts={"prescription_only": True})])
    [loaded] = load_product_facts(path)
    assert loaded.facts == {"prescription_only": True}


def test_but_not_on_a_product_of_another_category(tmp_path):
    path = write_facts(tmp_path, [entry(product="Made-up Pan", category="kitchen", product_type="frying pan",
                                        facts={"prescription_only": True})])
    with pytest.raises(ProductFactsError, match='unknown fact "prescription_only" for a frying pan'):
        load_product_facts(path)


def test_not_knowing_it_is_a_requirement_for_retinoids_and_exfoliants_only():
    beginner = parse_query("retinol for a beginner with sensitive skin")
    assert "prescription only" in hard_requirements(beginner) and "prescription_only" in facts_that_matter(beginner)
    assert "prescription only" in hard_requirements(parse_query("gentle exfoliant for sensitive skin"))
    for text in ("gentle cleanser for acne-prone skin that won't strip my skin", "moisturiser for sensitive skin",
                 "gentle sunscreen for sensitive skin"):
        query = parse_query(text)
        assert "prescription only" not in hard_requirements(query), text
        assert "prescription_only" not in facts_that_matter(query), text
        assert "prescription only" not in unconfirmed(query, None), text  # no "we couldn't confirm" note
    led = parse_query("azelaic acid for sensitive skin")  # an ingredient-led request: each product's own type counts
    assert hard_requirements(led, "moisturiser") == [] and "prescription only" in hard_requirements(led, "exfoliant")


def test_a_prescription_only_product_of_any_type_still_never_suits_a_gentle_or_sensitive_request():
    cream = ProductFacts(product="Made-up Azelaic Cream", category="skincare", product_type="moisturiser",
                         facts={"prescription_only": True}, sources=["https://facts.example/label"], checked_on=TODAY)
    for text in ("moisturiser for sensitive skin", "gentle moisturiser"):
        [found] = conflicts(parse_query(text), cream)
        assert (found.rule, found.hard) == ("prescription only", True), text
    assert conflicts(parse_query("moisturiser for oily skin"), cream) == []


# --- The note, wherever the product is shown ---

def test_the_note_shows_on_a_pick_an_item_and_a_skip_of_any_type(tmp_path, skincare_need_rule_set_aside):
    result = ask(tmp_path)
    assert [pick.name for pick in result.answer.picks] == [ACME[0], KIRI[0]]
    assert notes(result.answer) == {ACME[0]: None, KIRI[0]: NOTE, IRIS[0]: NOTE, OPAL[0]: NOTE}
    assert [item.name for item in result.answer.worth_a_look] == [IRIS[0]]
    assert [item.name for item in result.answer.skip] == [OPAL[0]]
    assert unverified_claims(result.answer, result.bodies) == []


def test_the_note_changes_nothing_about_which_products_are_shown(tmp_path):
    prescribed = ask(tmp_path / "a")
    unknown = ask(tmp_path / "b", product_facts=[facts(name, product_type, False, form) for name, product_type, form in
                                                 ((KIRI[0], "spot treatment", "patch"), (IRIS[0], "toner", None),
                                                  (OPAL[0], "exfoliant", "gel"), (ACME[0], "serum", None))])
    assert list(notes(prescribed.answer)) == list(notes(unknown.answer))
    assert set(notes(unknown.answer).values()) == {None}


def test_a_request_for_sensitive_skin_still_leaves_them_out(tmp_path):
    result = ask(tmp_path, "salicylic acid for sensitive skin")
    reason = config.PRODUCT_FACT_RULES["prescription only"]["reason"]
    left_out = {item.name: item.reason for item in result.left_out_not_suited}
    assert {name: left_out.get(name) for name in (KIRI[0], IRIS[0], OPAL[0])} == {
        KIRI[0]: reason, IRIS[0]: reason, OPAL[0]: reason}
    assert NOTE not in notes(result.answer).values()


def test_the_note_stays_when_the_live_check_writes_the_answer_again(tmp_path, skincare_need_rule_set_aside):
    result = ask(tmp_path, live_checker=FakeLive(gone={"a1"}))  # one of the serum's quotes, read again and gone
    assert result.live_dropped == {"gone": 1}
    assert notes(result.answer)[KIRI[0]] == NOTE and notes(result.answer)[IRIS[0]] == NOTE
    assert notes(result.answer)[ACME[0]] is None


def test_the_note_turns_into_json_and_markdown(tmp_path, skincare_need_rule_set_aside):
    result = ask(tmp_path)
    data = json.loads(json.dumps(answer_to_dict(result.answer)))
    assert [pick["prescription"] for pick in data["picks"]] == [None, NOTE]
    assert data["worth_a_look"][0]["prescription"] == NOTE and data["skip"][0]["prescription"] == NOTE
    text = render_markdown(result.answer)
    kiri = text.split(f"## 2. {KIRI[0]}")[1].split("**In their words**")[0]
    assert NOTE in kiri
    assert NOTE in text.split(f"### {IRIS[0]}")[1].split(f"## {wording.SKIP_HEADING}")[0]
    assert f"  - {NOTE}" in text.split(f"- **{OPAL[0]}**")[1]
    assert NOTE not in text.split(f"## 1. {ACME[0]}")[1].split(f"## 2. {KIRI[0]}")[0]


def test_the_wording_decided_by_claude():
    assert wording.PRESCRIPTION_NOTE == NOTE  # the coordinator's example, as a sentence like the answer's notes
    assert wording.PRESCRIPTION_TAG == "Prescription-only"  # the tag on a row under the picks, before it is opened


# --- The page (engine/templates/search.html) ---

def page_html() -> str:
    return web.search_page().decode("utf-8")


def function(html: str, name: str) -> str:
    return re.search(rf"function {name}\((.*?)\n  \}}", html, re.DOTALL).group(1)


def test_the_page_draws_the_answers_own_note_wherever_it_shows_a_product():
    html = page_html()
    line = function(html, "prescriptionLine")
    assert "innerHTML" not in line and 'class: "caution prescription"' in line  # the answer's words, as text
    assert "prescriptionLine(pick.prescription)" in function(html, "pickCard")
    assert "prescriptionLine(item.prescription)" in function(html, "worthCard")
    assert "prescriptionLine(item.prescription)" in function(html, "skipSection")


def test_a_row_says_so_before_it_is_opened_in_the_answers_words():
    html = page_html()
    settings = json.loads(re.search(r'<script type="application/json" id="settings">(.*?)</script>', html,
                                    re.DOTALL).group(1))
    assert settings["wording"]["prescription_tag"] == wording.PRESCRIPTION_TAG
    tag = function(html, "prescriptionTag")
    assert "WORDING.prescription_tag" in tag and "innerHTML" not in tag
    assert "prescriptionTag(item.prescription)" in function(html, "worthCard")
    assert "prescriptionTag(item.prescription)" in function(html, "skipSection")
    assert "prescriptionTag(pick.prescription)" in function(html, "glanceTable")  # "At a glance", above the cards


# --- The how page ---

def test_the_how_page_says_a_prescription_only_product_says_so(tmp_path, monkeypatch):
    from engine.tests.test_how_page import get_how, text_of

    text = text_of(get_how(tmp_path, monkeypatch))
    assert f'A product sold in the UK only on a prescription says so wherever we show it: "{NOTE}"' in text


# --- The committed facts list ---

OFFICIAL = ("medicines.org.uk", "mhra.gov.uk", "nhs.uk", "nhsbsa.nhs.uk", "dailymed.nlm.nih.gov")


def test_every_prescription_only_entry_has_an_official_source():
    entries = [e for e in load_product_facts(DEFAULT_PRODUCT_FACTS) if e.facts.get("prescription_only") is True]
    assert entries
    for e in entries:
        hosts = [urlsplit(source).hostname or "" for source in e.sources]
        assert any(host == official or host.endswith("." + official) for host in hosts for official in OFFICIAL), (
            e.product)
