"""The ingredient evaluation (13 Oct 2026, engine/ingredient_eval.py): routing against the cases' expectations, and
evidence for every shown product. The library and cases are made up."""

import json

from engine.ingredient_eval import DEFAULT_CASES, ingredient_lines, score_cases
from engine.tests.test_pipeline_ingredients import acne_library


def cases_file(tmp_path, cases):
    path = tmp_path / "ingredients.json"
    path.write_text(json.dumps({"approved": False, "cases": cases}), encoding="utf-8")
    return path


def test_each_case_reports_its_routing_picks_forms_and_evidence(tmp_path, skincare_need_rule_set_aside):
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
    # Changed on purpose 13 Oct 2026 (Noemi's decisions 1 and 2): an ingredient-led answer shows leave-on forms only,
    # spot treatments among them, and the evaluation checks each shown product's form too.
    assert [(s.where, s.name, s.form, s.evidence, s.form_ok) for s in first.shown] == [
        ("pick", "Acme 2% Salicylic Acid Serum", "serum", "name", True),
        ("pick", "Kiri Salicylic Pimple Patch", "patch", "name", True),
        ("worth", "Iris Salicylic Toner", "toner", "name", True),
        ("skip", "Opal Salicylic Gel", "gel", "name", True)]
    assert first.evidence_holds == (4, 4) and first.form_holds == (4, 4)
    assert first.left_out_by_form == 3 and first.rinse_off == 2
    assert [s.form_ok for s in second.shown] == [None]  # a typed request: its type says the form
    lines = ingredient_lines(results)
    assert lines[0] == ("2 requests: routing 1/2 as expected; shown products with evidence of the ingredient 5/5; "
                        "ingredient-led products in a leave-on form or the form asked for 4/4")
    assert any("i02" in line and "expected serum" in line for line in lines)


def test_the_committed_cases_load_and_route_as_expected():
    from engine.query import parse_query

    cases = json.loads(DEFAULT_CASES.read_text(encoding="utf-8"))["cases"]
    assert len(cases) >= 6
    for case in cases:
        query = parse_query(case["text"])
        expected = case["expected"]
        assert (query.product_type, query.constraints.ingredients, query.ingredient_led, query.constraints.forms) == (
            expected["product_type"], expected["ingredients"], expected["ingredient_led"],
            expected.get("forms", [])), case["id"]


def test_a_line_kept_for_its_products_facts_has_their_evidence(tmp_path, skincare_need_rule_set_aside):
    # A line stays in an ingredient answer only when every product of it named has a facts entry confirming the
    # ingredient (14 Oct 2026): its own name may not say the ingredient, so the evaluation checks those entries again.
    from engine.tests.test_pipeline_ingredients import facts, wren_library

    path = cases_file(tmp_path, [
        {"id": "i01", "text": "salicylic acid for acne",
         "expected": {"product_type": "salicylic acid product", "ingredients": ["salicylic acid"],
                      "ingredient_led": True}}])
    both = [facts("Wren 2% BHA Liquid", "exfoliant", ["salicylic acid"]),
            facts("Wren 2% BHA Gel", "exfoliant", ["salicylic acid"])]
    (result,) = score_cases(path, wren_library(tmp_path), profiles=None, live_checker=None, product_facts=both)
    assert ("pick", "Wren 2% BHA exfoliant line", "gel or leave-on liquid", "facts", True) in [
        (s.where, s.name, s.form, s.evidence, s.form_ok) for s in result.shown]
