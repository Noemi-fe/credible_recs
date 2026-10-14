"""The general category's routing evaluation (engine/routing_eval.py, 14 Oct 2026). Made-up cases, stand-in parsers."""

import json

import pytest

from engine.query import ParsedQuery
from engine.routing_eval import DEFAULT_CASES, load_cases, report_lines, routing_section, score, summary

CASES = [
    {"id": "g1", "text": "headphones for the gym",
     "expected": {"status": "ok", "category": "general", "product_type": "headphones", "department": "tech"}},
    {"id": "g2", "text": "a good plumber", "expected": {"status": "out_of_scope"}},
    {"id": "g3", "text": "label maker", "expected": {"status": "ok", "category": "general", "product_type": "label maker"}},
]


def parser(answers: dict):
    def parse(text: str) -> ParsedQuery:
        fields = answers[text]
        if fields["status"] == "ok":
            fields = {"search_terms": [fields["product_type"]], "subreddits": ["BuyItForLife"]} | fields
        return ParsedQuery(text=text, **fields)
    return parse


def test_every_field_is_scored_and_a_miss_says_why():
    results = score(CASES, parser({
        "headphones for the gym": {"status": "ok", "category": "general", "product_type": "headphones",
                                   "department": "home"},
        "a good plumber": {"status": "out_of_scope", "message": "Sorry."},
        "label maker": {"status": "clarify", "question": "What kind?"},
    }))
    assert summary(results) == {"outcome": (2, 3), "product": (1, 2), "department": (0, 1), "all": (1, 3)}
    first, _, third = results
    assert first.problems == ["department: expected 'tech', got 'home'"]
    assert third.problems[0] == "outcome: expected ok (general), got clarify"


def test_the_report_says_whether_noemi_has_checked_the_cases():
    results = score(CASES[:1], parser({"headphones for the gym": {
        "status": "ok", "category": "general", "product_type": "headphones", "department": "tech"}}))
    lines = report_lines({"approved": False}, results, "rules only")
    assert "DRAFT: not yet approved by Noemi" in lines[0] and lines[-1].endswith("1/1 (100%)")


def test_repeated_case_ids_are_refused(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"approved": False, "cases": CASES + CASES[:1]}), encoding="utf-8")
    with pytest.raises(ValueError, match="g1"):
        load_cases(path)


def test_the_shipped_cases_are_made_up_requests_across_the_departments():
    from engine.config import GENERAL_DEPARTMENTS

    data = load_cases(DEFAULT_CASES)
    cases = data["cases"]
    assert len(cases) >= 60 and data["approved"] is False
    departments = {c["expected"].get("department") for c in cases}
    assert set(GENERAL_DEPARTMENTS) <= departments
    assert {c["expected"]["status"] for c in cases} == {"ok", "clarify", "out_of_scope"}


def test_the_rules_alone_place_the_cases_no_open_model_is_needed_for():
    # The long tail (cases noted so) is the open model's; every other clear case the rules route themselves.
    data = load_cases(DEFAULT_CASES)
    results = score(data["cases"], lambda text: __import__("engine.query", fromlist=["parse_query"]).parse_query(
        text, model=None))
    missed = [r.id for r in results if r.problems and "Long tail" not in next(
        c["notes"] for c in data["cases"] if c["id"] == r.id)]
    assert missed == []


def test_the_section_runs_with_the_rules_alone_when_no_model_is_here():
    text = routing_section()
    assert "rules only" in text and "rules, then the open model" not in text  # tests never load the model
