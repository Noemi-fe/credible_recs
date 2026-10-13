"""The ingredient evaluation (13 Oct 2026, engine/ingredient_eval.py): routing against the cases' expectations, and
evidence for every shown product. The library and cases are made up."""

import json

from engine.ingredient_eval import DEFAULT_CASES, ingredient_lines, score_cases
from engine.tests.test_pipeline_ingredients import acne_library


def cases_file(tmp_path, cases):
    path = tmp_path / "ingredients.json"
    path.write_text(json.dumps({"approved": False, "cases": cases}), encoding="utf-8")
    return path


def test_each_case_reports_its_routing_picks_forms_and_evidence(tmp_path):
    path = cases_file(tmp_path, [
        {"id": "i01", "text": "salicylic acid for acne",
         "expected": {"product_type": "salicylic acid product", "ingredients": ["salicylic acid"],
                      "ingredient_led": True}},
        {"id": "i02", "text": "salicylic acid cleanser",
         "expected": {"product_type": "serum", "ingredients": ["salicylic acid"], "ingredient_led": False}},
    ])
    results = score_cases(path, acne_library(tmp_path), profiles=None, live_checker=None, product_facts=[])
    first, second = results
    assert first.routing_ok and not second.routing_ok  # the second case expects the wrong type on purpose
    assert [(s.where, s.name, s.form, s.evidence) for s in first.shown] == [
        ("pick", "Acme 2% Salicylic Acid Serum", "serum", "name"),
        ("pick", "Bloom Salicylic Cleanser", "cleanser", "name"),
        ("worth", "Iris Salicylic Toner", "toner", "name"),
        ("skip", "Echo Salicylic Peel", "peel", "name")]
    assert first.evidence_holds == (4, 4)
    lines = ingredient_lines(results)
    assert lines[0] == "2 requests: routing 1/2 as expected; shown products with evidence of the ingredient 5/5"
    assert any("i02" in line and "expected serum" in line for line in lines)


def test_the_committed_cases_load_and_route_as_expected():
    from engine.query import parse_query

    cases = json.loads(DEFAULT_CASES.read_text(encoding="utf-8"))["cases"]
    assert len(cases) >= 6
    for case in cases:
        query = parse_query(case["text"])
        expected = case["expected"]
        assert (query.product_type, query.constraints.ingredients, query.ingredient_led) == (
            expected["product_type"], expected["ingredients"], expected["ingredient_led"]), case["id"]
