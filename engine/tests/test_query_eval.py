"""Scoring module 1 against the hand-checked request set."""

import json

import pytest

from engine.query import ParsedQuery
from engine.query_eval import QueryCaseError, load_query_cases, score_cases, summarize


def case(case_id, text, status, category=None, product_type=None, constraints=None):
    return {
        "id": case_id,
        "text": text,
        "expected": {"status": status, "category": category, "product_type": product_type, "constraints": constraints or {}},
        "notes": "",
    }


CASES = [
    case("q01", "gentle exfoliant for sensitive skin under £30", "ok", "skincare", "exfoliant",
         {"budget": {"max": 30, "currency": "GBP"}, "skin_types": ["sensitive"], "must_haves": ["gentle"]}),
    case("q02", "something nice for my mum", "clarify"),
    case("q03", "best laptop", "out_of_scope"),
]


def write_cases(tmp_path, cases=CASES, approved=False):
    path = tmp_path / "query.json"
    path.write_text(json.dumps({"approved": approved, "approved_note": "draft", "cases": cases}))
    return path


def fake_parser(answers: dict):
    def parse(text):
        return ParsedQuery.model_validate({"text": text, **answers[text]})
    return parse


PERFECT = {
    "gentle exfoliant for sensitive skin under £30": {
        "status": "ok", "category": "skincare", "product_type": "chemical exfoliant",
        "constraints": {"budget": {"max": 30, "currency": "GBP"}, "skin_types": ["sensitive"]},
        "search_terms": ["exfoliant"], "subreddits": ["SkincareAddiction"],
    },
    "something nice for my mum": {"status": "clarify", "category": "skincare", "question": "What kind of product?"},
    "best laptop": {"status": "out_of_scope", "message": "Sorry."},
}


def test_loads_cases_and_approval(tmp_path):
    loaded = load_query_cases(write_cases(tmp_path))
    assert loaded.approved is False
    assert [c.id for c in loaded.cases] == ["q01", "q02", "q03"]


def test_duplicate_ids_are_refused(tmp_path):
    with pytest.raises(QueryCaseError, match="q01"):
        load_query_cases(write_cases(tmp_path, CASES + [CASES[0]]))


def test_a_correct_parser_scores_full_marks(tmp_path):
    # Product types match loosely ("chemical exfoliant" counts as "exfoliant"); must-haves are free text and not scored;
    # a clarify outcome only has to be a clarify, whatever category hint it carries.
    results = score_cases(load_query_cases(write_cases(tmp_path)).cases, fake_parser(PERFECT))
    assert all(r.outcome_ok for r in results)
    summary = summarize(results)
    assert (summary.outcome, summary.product, summary.constraints) == ((3, 3), (1, 1), (1, 1))


def test_each_kind_of_miss_is_counted_and_explained(tmp_path):
    wrong = dict(PERFECT)
    wrong["gentle exfoliant for sensitive skin under £30"] = {
        **PERFECT["gentle exfoliant for sensitive skin under £30"],
        "product_type": "cleanser",
        "constraints": {"budget": {"max": 30}, "skin_types": ["sensitive"]},  # currency missed
    }
    wrong["best laptop"] = {"status": "clarify", "question": "What kind of product?"}
    results = score_cases(load_query_cases(write_cases(tmp_path)).cases, fake_parser(wrong))
    summary = summarize(results)
    assert (summary.outcome, summary.product, summary.constraints) == ((2, 3), (0, 1), (0, 1))
    misses = {r.case.id: r.problems for r in results if r.problems}
    assert any("budget" in p for p in misses["q01"]) and any("product" in p for p in misses["q01"])
    assert any("out_of_scope" in p for p in misses["q03"])
