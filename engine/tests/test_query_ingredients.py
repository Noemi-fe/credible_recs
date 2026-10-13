"""Module 1 and active ingredients (13 Oct 2026): a request naming an ingredient keeps the type it names, or, naming
none, is ingredient-led. Requests are made up."""

import pytest

from engine.query import classify, parse_query, search_terms
from engine.sources import mentions_product


def test_an_ingredient_alone_makes_an_ingredient_led_request():
    query = parse_query("salicylic acid for acne")
    assert (query.status, query.category) == ("ok", "skincare")
    assert query.ingredient_led
    assert query.constraints.ingredients == ["salicylic acid"]
    assert query.product_type == "salicylic acid product"
    assert query.constraints.skin_types == ["acne-prone"]
    assert query.subreddits[0] == "acne"  # the condition's own subreddit first, as for any acne request


def test_an_ingredient_led_request_searches_by_the_ingredient():
    query = parse_query("salicylic acid for acne")
    assert query.search_terms == ["salicylic acid for acne-prone skin", "salicylic acid"]
    assert search_terms(query.product_type, query.constraints) == query.search_terms


def test_the_rules_alone_still_read_an_acid_as_an_exfoliant_clue():
    # classify (the product-word router) is unchanged; parse_query reads the ingredient on top of it.
    assert classify("a bha for blackheads").product_type == "exfoliant"
    query = parse_query("a bha for blackheads")
    assert query.ingredient_led and query.constraints.ingredients == ["BHA"]


@pytest.mark.parametrize("text, product_type, ingredients", [
    ("salicylic acid cleanser", "cleanser", ["salicylic acid"]),
    ("niacinamide serum for oily skin", "serum", ["niacinamide"]),
    ("vitamin c serum under £20", "serum", ["vitamin C"]),
    ("glycolic acid toner", "toner", ["glycolic acid"]),
    ("lactic acid lotion for dry legs", "moisturiser", ["lactic acid"]),  # "lotion": was a question (two products)
    ("BHA exfoliant", "exfoliant", ["BHA"]),
    ("tretinoin for acne", "retinoid", ["tretinoin"]),
    ("a retinal serum for beginners", "retinoid", ["retinal"]),
    ("ceramide moisturiser for my barrier", "moisturiser", ["ceramides"]),
])
def test_a_type_named_with_an_ingredient_stays_and_the_ingredient_is_required(text, product_type, ingredients):
    query = parse_query(text)
    assert (query.status, query.product_type, query.constraints.ingredients) == ("ok", product_type, ingredients)
    assert not query.ingredient_led


def test_vitamin_c_serum_keeps_its_budget():
    query = parse_query("vitamin c serum under £20")
    assert (query.constraints.budget.max, query.constraints.budget.currency) == (20, "GBP")


def test_retinol_is_the_retinoid_type_and_asks_for_nothing_more():
    # Noemi, 7 Oct 2026 (eval/edge_cases/query.json, q05): "retinol" maps to the generic retinoid.
    for text in ("gentle retinol for beginners", "retinol for a beginner with sensitive skin", "retinol serum"):
        query = parse_query(text)
        assert (query.product_type, query.constraints.ingredients, query.ingredient_led) == ("retinoid", [], False)


@pytest.mark.parametrize("text, ingredient", [
    ("azelaic acid for redness", "azelaic acid"),
    ("niacinamide for oily skin", "niacinamide"),
    ("vit c for dark spots", "vitamin C"),
    ("benzoyl peroxide wash", "benzoyl peroxide"),
    ("snail mucin", "snail mucin"),
    ("salicylic acid for razor bumps", "salicylic acid"),  # "razor" is out of scope, "razor bumps" aren't
])
def test_an_ingredient_named_without_a_type_is_ingredient_led(text, ingredient):
    query = parse_query(text)
    assert (query.status, query.category, query.ingredient_led, query.constraints.ingredients) == (
        "ok", "skincare", True, [ingredient])


def test_an_ingredient_to_avoid_isnt_required():
    query = parse_query("moisturiser without niacinamide")
    assert (query.product_type, query.constraints.ingredients) == ("moisturiser", [])


def test_haircare_keeps_its_type_and_its_questions():
    shampoo = parse_query("salicylic acid shampoo for dandruff")
    assert (shampoo.category, shampoo.product_type, shampoo.constraints.ingredients) == (
        "haircare", "shampoo", ["salicylic acid"])
    scalp = parse_query("salicylic acid for my scalp")  # about hair: asked about, not read as skincare
    assert (scalp.status, scalp.category) == ("clarify", "haircare")


def test_requests_without_an_ingredient_are_unchanged():
    for text, product_type in (("gentle exfoliant for sensitive skin under £30", "exfoliant"),
                               ("electric kettle that lasts 10+ years", "electric kettle")):
        query = parse_query(text)
        assert (query.product_type, query.constraints.ingredients, query.ingredient_led) == (product_type, [], False)


class NeverAsked:
    """An open model that must not be asked: an ingredient-led request is placed by the rules."""

    def read(self, text: str) -> dict:
        raise AssertionError("the open model was asked")


def test_the_open_model_isnt_asked_about_an_ingredient_led_request():
    query = parse_query("azelaic acid for redness", model=NeverAsked())
    assert query.ingredient_led


def test_threads_about_an_ingredient_led_request_name_the_ingredient_or_a_related_one():
    assert mentions_product("Best salicylic acid serum?", "salicylic acid product")
    assert mentions_product("Which BHA do you use?", "salicylic acid product")  # a BHA thread is about it too
    assert not mentions_product("Best cleanser for acne?", "salicylic acid product")
