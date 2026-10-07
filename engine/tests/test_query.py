"""Module 1: the shape of an understood request, and the rules-only parser."""

import pytest
from pydantic import ValidationError

from engine.query import Budget, Constraints, ParsedQuery, Size


def ok_query(**overrides) -> dict:
    query = {
        "text": "gentle exfoliant for sensitive skin under £30",
        "status": "ok",
        "category": "skincare",
        "product_type": "exfoliant",
        "constraints": {"budget": {"max": 30, "currency": "GBP"}, "skin_types": ["sensitive"]},
        "search_terms": ["gentle exfoliant sensitive skin"],
        "subreddits": ["SkincareAddiction", "SkincareAddictionUK"],
    }
    query.update(overrides)
    return query


# --- The shape ---

def test_clear_request_parses():
    query = ParsedQuery.model_validate(ok_query())
    assert query.constraints.budget == Budget(max=30, currency="GBP")
    assert query.question is None and query.message is None


@pytest.mark.parametrize("missing", ["category", "product_type", "search_terms", "subreddits"])
def test_clear_request_needs_everything_the_search_uses(missing):
    blank = None if missing in ("category", "product_type") else []
    with pytest.raises(ValidationError, match=missing):
        ParsedQuery.model_validate(ok_query(**{missing: blank}))


def test_subreddits_must_belong_to_the_category():
    with pytest.raises(ValidationError, match="BuyItForLife"):
        ParsedQuery.model_validate(ok_query(subreddits=["SkincareAddiction", "BuyItForLife"]))


def test_clarify_needs_a_question():
    with pytest.raises(ValidationError, match="question"):
        ParsedQuery.model_validate({"text": "something nice for my mum", "status": "clarify"})
    query = ParsedQuery.model_validate(
        {"text": "something nice for my mum", "status": "clarify", "question": "What kind of product are you looking for?"}
    )
    assert query.category is None


def test_out_of_scope_needs_a_polite_message_and_no_category():
    with pytest.raises(ValidationError, match="message"):
        ParsedQuery.model_validate({"text": "best laptop", "status": "out_of_scope"})
    with pytest.raises(ValidationError, match="category"):
        ParsedQuery.model_validate(
            {"text": "best laptop", "status": "out_of_scope", "category": "kitchen", "message": "Sorry, only skincare and kitchen gear."}
        )


def test_budget_needs_a_limit_and_a_sensible_range():
    with pytest.raises(ValidationError):
        Budget(currency="GBP")
    with pytest.raises(ValidationError):
        Budget(min=50, max=20)
    assert Budget(min=20, max=50).currency is None  # no currency given: don't guess one


def test_size_and_other_constraints():
    constraints = Constraints(size=Size(value=1.7, unit="l"), spf=50, min_years=10, skin_types=["dry", "sensitive"])
    assert constraints.size.unit == "l"
    with pytest.raises(ValidationError):
        Size(value=1.7, unit="litres")  # units are normalised before they get here
    with pytest.raises(ValidationError):
        Constraints(skin_types=["purple"])


# --- Routing: clear, ask a question, or out of scope (rules only, no AI) ---

from engine.query import classify  # noqa: E402


@pytest.mark.parametrize("text, category, product_type", [
    ("gentle exfoliant for sensitive skin under £30", "skincare", "exfoliant"),
    ("electric kettle that lasts 10+ years", "kitchen", "electric kettle"),
    ("Best MOISTURIZER for dry skin??", "skincare", "moisturiser"),
    ("whistling stovetop kettle", "kitchen", "stovetop kettle"),
    ("first chef's knife, 210mm gyuto maybe", "kitchen", "chef knife"),
    ("retinol serum for beginners", "skincare", "retinoid"),
    ("a bha for blackheads", "skincare", "exfoliant"),
    ("tea pot that doesn't drip", "kitchen", "teapot"),
])
def test_clear_requests_find_their_category_and_product(text, category, product_type):
    routing = classify(text)
    assert (routing.status, routing.category, routing.product_type) == ("ok", category, product_type)


def test_subreddits_suit_the_product():
    assert classify("chef knife under £100").subreddits[0] == "chefknives"
    assert classify("cast iron skillet").subreddits[0] == "castiron"
    assert set(classify("sunscreen spf 50").subreddits) == {"SkincareAddiction", "AsianBeauty", "30PlusSkinCare", "SkincareAddictionUK"}


def test_vague_request_gets_one_question_instead_of_a_guess():
    routing = classify("something nice for my mum")
    assert routing.status == "clarify"
    assert routing.question.endswith("?")


def test_vague_request_with_a_category_hint_asks_within_that_category():
    routing = classify("something for my dry skin")
    assert (routing.status, routing.category) == ("clarify", "skincare")
    assert "skincare" in routing.question


def test_two_needs_get_one_question():
    routing = classify("a kettle and a good chef knife")
    assert routing.status == "clarify"
    assert "kettle" in routing.question and "chef knife" in routing.question


def test_out_of_scope_gets_a_polite_no():
    routing = classify("best laptop for uni")
    assert routing.status == "out_of_scope" and routing.category is None
    assert "skincare and kitchen" in routing.message


def test_requirements_that_mention_other_products_are_not_out_of_scope():
    # "fragrance-free" and "dishwasher-safe" are requirements, not a perfume or a dishwasher.
    assert classify("fragrance-free moisturiser").status == "ok"
    assert classify("dishwasher-safe chef knife").status == "ok"
    assert classify("dishwasher that's quiet").status == "out_of_scope"


# --- Requirements and search terms ---

from engine.query import find_must_haves, search_terms  # noqa: E402


@pytest.mark.parametrize("text, expected", [
    ("unscented moisturiser for sensitive skin", ["fragrance-free"]),
    ("Fragrance free, non comedogenic sunscreen with no white cast", ["fragrance-free", "non-comedogenic", "no white cast"]),
    ("kettle with no plastic inside, stainless steel", ["plastic-free", "stainless steel"]),
    ("dishwasher safe chef knife", ["dishwasher-safe"]),
    ("a kettle", []),
])
def test_requirements_are_spotted(text, expected):
    assert find_must_haves(text) == expected


def test_search_terms_go_from_specific_to_general():
    constraints = Constraints(skin_types=["sensitive"], must_haves=["fragrance-free"])
    assert search_terms("moisturiser", constraints) == [
        "moisturiser for sensitive skin", "fragrance-free moisturiser", "moisturiser",
    ]
    assert search_terms("electric kettle", Constraints(min_years=10)) == ["electric kettle that lasts", "electric kettle"]
    assert search_terms("teapot", Constraints()) == ["teapot"]


# --- The whole of module 1: text in, understood request out ---

from engine.query import parse_query  # noqa: E402


def test_brief_example_end_to_end():
    query = parse_query("gentle exfoliant for sensitive skin under £30")
    assert (query.status, query.category, query.product_type) == ("ok", "skincare", "exfoliant")
    assert query.constraints.budget == Budget(max=30, currency="GBP")
    assert query.constraints.skin_types == ["sensitive"]
    assert query.search_terms == ["exfoliant for sensitive skin", "exfoliant"]
    assert "SkincareAddiction" in query.subreddits


def test_size_and_price_in_one_request_stay_apart():
    query = parse_query("1.7l kettle under £40")
    assert query.constraints.size == Size(value=1.7, unit="l")
    assert query.constraints.budget == Budget(max=40, currency="GBP")
    assert query.subreddits[0] == "BuyItForLife"


def test_question_keeps_what_was_already_said():
    # When the shopper answers, the budget they gave is still known.
    query = parse_query("kitchen stuff for my first flat, budget £200")
    assert query.status == "clarify" and query.question
    assert query.constraints.budget == Budget(max=200, currency="GBP")


def test_out_of_scope_carries_nothing_else():
    query = parse_query("best laptop for uni under £800")
    assert query.status == "out_of_scope" and query.message
    assert query.constraints == Constraints() and query.search_terms == [] and query.subreddits == []
