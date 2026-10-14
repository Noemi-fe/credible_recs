"""Module 1: kitchen appliances as product types of their own (Noemi's decision 3 of 14 Oct 2026, after her and a
friend's tests of the live site: "microwave" and "oven" returned nothing, as neither was a product type).

The rules route each appliance without the open model (the tests run without it, engine/tests/conftest.py), with its
own communities, its plural, the other words people use for it, and the look-alikes that hold its word but name
something else: microwave popcorn isn't a microwave, a Dutch oven isn't an oven, oven gloves aren't an oven, an
immersion blender isn't a blender. Every request here is made up.
"""

import pytest

from engine.config import SUBREDDITS
from engine.query import PRODUCT_TYPES, TITLE_WORDS, classify, parse_query

APPLIANCES = ("microwave", "oven", "toaster oven", "air fryer", "blender", "food processor", "stand mixer",
              "hand mixer", "slow cooker", "rice cooker", "pressure cooker", "coffee maker", "french press", "toaster",
              "waffle maker", "juicer", "kitchen scale")


def routed(text: str) -> tuple:
    routing = classify(text)
    return routing.status, routing.category, routing.product_type


def test_every_appliance_is_a_kitchen_product_type():
    kitchen = {p.name for p in PRODUCT_TYPES if p.category == "kitchen"}
    assert set(APPLIANCES) <= kitchen


def test_every_product_type_is_routed_by_its_own_name():
    # The live site warms an answer for each type by its name (engine.web.WARM_PRODUCT_TYPES).
    for product in PRODUCT_TYPES:
        assert routed(product.name)[::2] == ("ok", product.name), product.name


@pytest.mark.parametrize("text, product_type", [
    ("microwave that heats evenly", "microwave"),
    ("best microwave ovens under £150", "microwave"),
    ("combination microwave for a small flat", "microwave"),
    ("oven for baking bread at home", "oven"),
    ("built-in electric oven that cleans itself", "oven"),
    ("range cooker for a big family", "oven"),
    ("wall ovens that last", "oven"),
    ("gas range under $1000", "oven"),
    ("toaster oven for a tiny flat", "toaster oven"),
    ("countertop oven that can roast a chicken", "toaster oven"),
    ("air fryer oven for a family of four", "toaster oven"),
    ("air fryer for two people", "air fryer"),
    ("airfryers that don't break", "air fryer"),
    ("blender for frozen fruit smoothies", "blender"),
    ("high-speed blenders worth the money", "blender"),
    ("food processor for pastry dough", "food processor"),
    ("stand mixer for bread dough", "stand mixer"),
    ("kitchenaid mixer alternatives", "stand mixer"),
    ("hand mixer for cake batter", "hand mixer"),
    ("electric whisk for meringues", "hand mixer"),
    ("slow cooker for stews", "slow cooker"),
    ("crockpot that lasts", "slow cooker"),
    ("crock pot for a family", "slow cooker"),
    ("rice cooker for sushi rice", "rice cooker"),
    ("pressure rice cooker", "rice cooker"),
    ("pressure cooker for dried beans", "pressure cooker"),
    ("instant pot for a beginner", "pressure cooker"),
    ("multicooker with a steam setting", "pressure cooker"),
    ("drip coffee maker with a thermal carafe", "coffee maker"),
    ("filter coffee machine for the office", "coffee maker"),
    ("coffee makers that keep it hot", "coffee maker"),
    ("french press that keeps coffee hot", "french press"),
    ("cafetiere for one person", "french press"),
    ("4 slice toaster that toasts evenly", "toaster"),
    ("toasters with wide slots", "toaster"),
    ("waffle maker for thick waffles", "waffle maker"),
    ("waffle iron that's easy to clean", "waffle maker"),
    ("cold press juicer for leafy greens", "juicer"),
    ("kitchen scales for baking", "kitchen scale"),
    ("coffee scale with a timer", "kitchen scale"),
])
def test_appliances_are_routed_by_the_rules(text, product_type):
    assert routed(text) == ("ok", "kitchen", product_type)


@pytest.mark.parametrize("text, product_type", [
    ("dutch oven for sourdough", "dutch oven"),  # its own type: a longer name wins
    ("a pan to put in the oven", "frying pan"),  # the oven is where it goes
    ("oven-safe frying pan", "frying pan"),
    ("oven safe skillet for cornbread", "cast iron skillet"),
    ("skillet that goes from stove to oven", "cast iron skillet"),
    ("dishwasher-safe chef knife", "chef knife"),  # a requirement, not a dishwasher
    ("a knife I can put in the dishwasher", "chef knife"),
    ("container I can put in the microwave", None),
    ("espresso machine for a beginner", "espresso machine"),  # a coffee machine stays an espresso machine
    ("coffee machine with a milk frother", "espresso machine"),
    ("rice cooker with a non-stick pot", "rice cooker"),  # the pot is a part of it
    ("drip coffee maker with a built-in grinder", "coffee maker"),  # so is the grinder
    ("coffee maker with grinder", "coffee maker"),
    ("dutch oven safe to 260c", "dutch oven"),  # "oven safe" starts inside the Dutch oven's name
    ("a dutch oven that's oven safe", "dutch oven"),
])
def test_an_appliance_word_that_says_where_or_what_for_isnt_the_appliance(text, product_type):
    status, _, routed_type = routed(text)
    assert routed_type == product_type
    if product_type is None:
        assert status == "clarify"


@pytest.mark.parametrize("text, not_this", [
    ("microwave popcorn without palm oil", "microwave"),
    ("microwave-safe containers for lunch", "microwave"),
    ("oven mitts that don't burn", "oven"),
    ("oven gloves for a small kitchen", "oven"),
    ("an oven thermometer that's accurate", "oven"),
    ("immersion blender for soup", "blender"),
    ("stick blender that lasts", "blender"),
    ("hand blender for baby food", "blender"),
    ("beauty blender for foundation", "blender"),
    ("toaster bags for gluten-free bread", "toaster"),
    ("air fryer liners that don't burn", "air fryer"),
])
def test_a_look_alike_holding_an_appliances_word_isnt_the_appliance(text, not_this):
    assert classify(text).product_type != not_this


@pytest.mark.parametrize("text", ["oven cleaner that actually works", "dishwasher tablets that work",
                                  "rinse aid for hard water", "a bathroom scale that's accurate"])
def test_cleaning_products_and_bathroom_scales_are_out_of_scope(text):
    assert classify(text).status == "out_of_scope"


def test_a_dishwasher_stays_out_of_scope_as_noemis_case_q30_says():
    # eval/edge_cases/query.json, q30 (her call of 7 Oct 2026: large appliances aren't kitchen gear). Her decision 3 of
    # 14 Oct 2026 brought the microwave and the oven in; the dishwasher waits for her call on q30.
    assert classify("quiet dishwasher for a small kitchen").status == "out_of_scope"
    assert routed("dishwasher-safe chef knife") == ("ok", "kitchen", "chef knife")


def test_two_appliances_get_one_question():
    routing = classify("rice cooker or instant pot?")
    assert routing.status == "clarify" and routing.several
    assert "rice cooker" in routing.question and "pressure cooker" in routing.question


@pytest.mark.parametrize("product_type, first", [
    ("microwave", "Appliances"), ("oven", "Appliances"), ("air fryer", "airfryer"),
    ("pressure cooker", "instantpot"), ("slow cooker", "slowcooking"), ("stand mixer", "Baking"),
    ("hand mixer", "Baking"), ("kitchen scale", "Baking"), ("coffee maker", "Coffee"), ("french press", "Coffee"),
    ("juicer", "juicing"), ("blender", "BuyItForLife"), ("toaster", "BuyItForLife"),
])
def test_each_appliance_is_searched_in_its_own_communities_first(product_type, first):
    query = parse_query(product_type)
    assert query.subreddits[0] == first
    assert set(query.subreddits) <= set(SUBREDDITS["kitchen"])


def test_the_new_communities_are_decided_kitchen_subreddits():
    assert {"Appliances", "airfryer", "instantpot", "slowcooking", "Baking", "juicing"} <= set(SUBREDDITS["kitchen"])
    # Searched in their own order; they come after the kitchen subreddits decided before.
    assert SUBREDDITS["kitchen"][:8] == ("BuyItForLife", "AskCulinary", "chefknives", "Cooking", "castiron", "Coffee",
                                         "espresso", "tea")


def test_appliances_are_searched_by_the_words_people_put_in_titles():
    from engine.sources import finder_terms

    assert finder_terms("air fryer") == ["air fryer", "airfryer"]
    assert finder_terms("slow cooker") == ["slow cooker", "crock pot", "crockpot"]
    assert finder_terms("pressure cooker") == ["pressure cooker", "instant pot", "multicooker"]
    assert all(TITLE_WORDS.get(name) for name in APPLIANCES)


@pytest.mark.parametrize("text, product_type", [
    ("microwve that heats evenly", "microwave"),
    ("blendr for smoothies", "blender"),
    ("best tosater for a small kitchen", None),  # two letters swapped: not one wrong letter
])
def test_one_wrong_letter_in_an_appliance_is_forgiven(text, product_type):
    assert parse_query(text).product_type == product_type


@pytest.mark.parametrize("text", ["frying pan for slow cooked stews", "pan for toasted nuts", "pan for blended sauces",
                                  "saucepan for juices and sauces"])
def test_real_words_one_letter_from_an_appliance_are_left_alone(text):
    query = parse_query(text)
    assert query.product_type in ("frying pan", "saucepan"), text


def test_the_plural_and_shown_name_of_each_appliance():
    from engine.config import PRODUCT_TYPE_PLURALS, PRODUCT_TYPE_SHOWN
    from engine.group_products import brand_pick_name

    assert PRODUCT_TYPE_PLURALS["french press"] == "French presses"
    assert PRODUCT_TYPE_PLURALS["kitchen scale"] == "kitchen scales"
    assert PRODUCT_TYPE_SHOWN["french press"] == "French press"
    assert brand_pick_name("Bodum", "french press") == "Bodum French press line"
    assert brand_pick_name("Ninja", "air fryer") == "Ninja air fryer line"
