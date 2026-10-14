"""Active ingredients (13 Oct 2026, engine/ingredients.py): which ones a request asks for, whether a product contains
one, and the form each product takes. Product names are real or made up; no test reads data/."""

import pytest

from engine.config import INGREDIENT_ACTIVES, INGREDIENTS, PRODUCT_TYPE_FORMS
from engine.ingredients import (
    blanked,
    evidence,
    find_ingredients,
    form_of,
    ingredient_type_name,
    ingredients_of_type,
    names_ingredient,
    talk_words,
    wanted_types,
)
from engine.query import PRODUCT_TYPES


def asked(text: str) -> list[str]:
    return [f.ingredient for f in find_ingredients(text)]


@pytest.mark.parametrize("text, ingredients", [
    ("salicylic acid for acne", ["salicylic acid"]),
    ("Salicylic for blackheads", ["salicylic acid"]),
    ("a bha for blackheads", ["BHA"]),
    ("beta hydroxy acid for my nose", ["BHA"]),
    ("glycolic acid toner", ["glycolic acid"]),
    ("lactic acid lotion for dry legs", ["lactic acid"]),
    ("mandelic acid serum", ["mandelic acid"]),
    ("an AHA for dull skin", ["AHA"]),
    ("azelaic acid for redness", ["azelaic acid"]),
    ("niacinamide serum for oily skin", ["niacinamide"]),
    ("vitamin c serum under £20", ["vitamin C"]),
    ("vit c for dark spots", ["vitamin C"]),
    ("benzoyl peroxide wash", ["benzoyl peroxide"]),
    ("hyaluronic acid serum", ["hyaluronic acid"]),
    ("ceramide moisturiser for my barrier", ["ceramides"]),
    ("cica cream for redness", ["centella"]),
    ("snail mucin essence", ["snail mucin"]),
    ("tretinoin for acne", ["tretinoin"]),
    ("a retinal serum", ["retinal"]),
    ("gentle retinol for beginners", ["retinoid"]),
])
def test_a_request_names_its_ingredients(text, ingredients):
    assert asked(text) == ingredients


@pytest.mark.parametrize("text", [
    "gentle exfoliant for sensitive skin under £30", "moisturiser without niacinamide", "niacinamide-free serum",
    "a sunscreen with no retinol in it", "retinol alternative for pregnancy", "cleanser, allergic to salicylic acid",
    "electric kettle that lasts 10+ years", "cerave sa cleanser",
])
def test_an_ingredient_to_avoid_or_none_at_all_asks_for_nothing(text):
    assert asked(text) == []


def test_a_narrower_ingredient_says_the_broader_one_already():
    # "BHA (salicylic acid)" asks for salicylic acid: every salicylic acid product is a BHA.
    assert asked("BHA (salicylic acid) toner") == ["salicylic acid"]
    assert asked("aha/bha toner") == ["AHA", "BHA"]  # two different acids: both asked for
    assert asked("salicylic acid and niacinamide serum") == ["salicylic acid", "niacinamide"]


def test_retinal_is_never_retinol():
    assert asked("retinal") == ["retinal"]
    assert asked("retinol") == ["retinoid"]


def test_the_rest_of_a_request_reads_without_its_ingredients():
    text = "lactic acid lotion"
    assert blanked(text, find_ingredients(text)) == " " * len("lactic acid") + " lotion"


def test_an_ingredient_led_type_is_named_after_its_ingredients_and_read_back():
    assert ingredient_type_name(["salicylic acid"]) == "salicylic acid product"
    assert ingredients_of_type("salicylic acid product") == ("salicylic acid",)
    assert ingredients_of_type("AHA and BHA product") == ("AHA", "BHA")
    assert ingredients_of_type("cleanser") == ()
    assert ingredients_of_type("air fryer product") == ()  # not an ingredient: a type the open model could name


def test_an_ingredient_led_request_may_show_every_type_that_carries_it():
    # Changed on purpose 13 Oct 2026 (Noemi's decision 2): spot treatments are a type that carries acids too.
    assert wanted_types("salicylic acid product") == ("exfoliant", "toner", "serum", "cleanser", "moisturiser",
                                                      "spot treatment")
    assert wanted_types("cleanser") == ("cleanser",)
    # Two ingredients: the types that can carry both.
    assert wanted_types("salicylic acid and vitamin C product") == ("toner", "serum", "moisturiser")


def test_threads_about_bhas_talk_about_salicylic_acid():
    assert talk_words("salicylic acid product") == (r"salicylic(?: acid)?", r"bha", r"beta[- ]hydroxy(?: acid)?")
    assert talk_words("cleanser") == ()


@pytest.mark.parametrize("name, ingredient, says", [
    ("Paula's Choice 2% BHA Skin Perfecting Liquid", "BHA", True),
    ("Paula's Choice 2% BHA Skin Perfecting Liquid", "salicylic acid", False),  # a BHA isn't proof of salicylic acid
    ("COSRX Salicylic Acid Daily Gentle Cleanser", "salicylic acid", True),
    ("COSRX Salicylic Acid Daily Gentle Cleanser", "BHA", True),
    ("The Ordinary Mandelic Acid 10% + HA", "AHA", True),
    ("The Ordinary Mandelic Acid 10% + HA", "hyaluronic acid", True),
    ("By Wishtrend Vitamin A-mazing Bakuchiol Night Cream", "retinoid", False),
    ("Medik8 Crystal Retinal 3", "retinoid", True),
    ("Medik8 Crystal Retinal 3", "retinal", True),
    ("CeraVe Resurfacing Retinol Serum", "retinal", False),
    ("Geek and Gorgeous Calm Down", "salicylic acid", False),
])
def test_a_products_own_name_may_say_it_contains_an_ingredient(name, ingredient, says):
    assert names_ingredient(name, ingredient) is says


def test_a_facts_entrys_actives_decide_before_the_name():
    # COSRX's BHA liquid is made with betaine salicylate: a BHA, but no salicylic acid.
    assert evidence("salicylic acid", "COSRX BHA Blackhead Power Liquid", ["betaine salicylate"]).contains is False
    assert evidence("BHA", "COSRX BHA Blackhead Power Liquid", ["betaine salicylate"]).contains is True
    found = evidence("salicylic acid", "Dermalogica Daily Microfoliant", ["salicylic acid", "papain"])
    assert (found.contains, found.how) == (True, "facts")
    named = evidence("salicylic acid", "Acme Salicylic Acid Serum", None)
    assert (named.contains, named.how) == (True, "name")
    assert evidence("salicylic acid", "Acme Glow Powder", None).contains is None  # not known: never a guess


@pytest.mark.parametrize("name, product_type, facts_form, form", [
    ("Dr Dennis Gross peel pads", "exfoliant", None, "pads"),
    ("Paula's Choice 2% BHA Skin Perfecting Liquid", "exfoliant", None, "leave-on liquid"),
    ("COSRX AHA/BHA Clarifying Treatment Toner", "exfoliant", None, "toner"),
    ("Skin1004 Tea-Trica BHA Cleansing Foam", "cleanser", None, "cleanser"),
    ("Some By Mi AHA, BHA, PHA 30 Days Miracle Truecica Clear Pads", "exfoliant", None, "pads"),
    ("Dermalogica Daily Microfoliant", "exfoliant", "rinse-off powder", "rinse-off powder"),
    ("Acme Glow", "exfoliant", None, "exfoliant"),
    ("Acme Glow", None, None, None),
])
def test_each_product_shows_its_form(name, product_type, facts_form, form):
    assert form_of(name, product_type, facts_form) == form


def test_the_ingredient_list_fits_module_1():
    types = {p.name for p in PRODUCT_TYPES if p.category == "skincare"}
    for key, entry in INGREDIENTS.items():
        assert set(entry["types"]) <= types, key
        assert set(entry["actives"]) <= set(INGREDIENT_ACTIVES), key
        assert set(entry.get("related", ())) <= set(INGREDIENTS), key
    assert set(PRODUCT_TYPE_FORMS) == types


def test_a_writers_description_of_what_a_product_has_isnt_its_name():
    # "Kelp Gleanser with salicylic acid": the writer's claim, not the maker's name (the maker's name, with a facts
    # entry, is read whole: CeraVe's own name holds "with Salicylic Acid").
    from engine.ingredients import own_name

    assert own_name("Kelp Gleanser with salicylic acid") == "Kelp Gleanser"
    assert own_name("Kelp toner w/ BHA") == "Kelp toner"
    assert own_name("Kelp Salicylic Acid Toner") == "Kelp Salicylic Acid Toner"
    assert evidence("salicylic acid", own_name("Kelp Gleanser with salicylic acid"), None).contains is None


# --- Forms (Noemi's decision 1 of 13 Oct 2026): leave-on forms only, unless the request names another ---

@pytest.mark.parametrize("name, product_type, form", [
    ("Acme Acne Pimple Master Patch", "pimple patch", "patch"),
    ("Acme Hydrocolloid Acne Patches", "spot treatment", "patch"),
    ("Acme Acne Spot Treatment Gel", "spot treatment", "spot treatment"),
    ("Acme Spot", "spot treatment", "spot treatment"),  # its type says the form
    ("Acme Lip Sleeping Mask", "lip balm", "sleeping mask"),
    ("Acme Rice Polish", "exfoliant", "scrub"),
    ("Acme exfoliating powder", "exfoliant", "rinse-off powder"),
    ("Acme Clay Mask", "exfoliant", "mask"),
    ("Acme AHA 30% + BHA 2% Peeling Solution", "exfoliant", "peel"),  # a peel, though its name says solution
    ("Acme Dark Spot Serum", "serum", "serum"),  # a dark spot isn't a spot treatment
])
def test_more_forms_are_read_from_names(name, product_type, form):
    assert form_of(name, product_type) == form


@pytest.mark.parametrize("form, kind", [
    ("serum", "leave-on"), ("leave-on liquid", "leave-on"), ("toner", "leave-on"), ("pads", "leave-on"),
    ("essence", "leave-on"), ("cream", "leave-on"), ("moisturiser", "leave-on"), ("spot treatment", "leave-on"),
    ("patch", "leave-on"), ("sleeping mask", "leave-on"),
    ("cleanser", "rinse-off"), ("rinse-off powder", "rinse-off"), ("mask", "rinse-off"), ("peel", "rinse-off"),
    ("scrub", "rinse-off"),
    ("exfoliant", None), (None, None),  # an exfoliant may be a leave-on liquid or a rinse-off scrub: not known
])
def test_each_form_is_leave_on_rinse_off_or_not_known(form, kind):
    from engine.ingredients import form_kind

    assert form_kind(form) == kind


def test_every_form_a_name_type_or_formula_can_give_is_known_to_be_leave_on_or_rinse_off():
    from engine.config import INGREDIENT_FORM_WORDS, INGREDIENT_FORMS
    from engine.ingredients import form_kind

    for form in set(INGREDIENT_FORMS) | {form for _, form in INGREDIENT_FORM_WORDS}:
        assert form_kind(form) is not None, form
    assert [t for t, form in PRODUCT_TYPE_FORMS.items() if form_kind(form) is None] == ["exfoliant"]


@pytest.mark.parametrize("text, forms", [
    ("salicylic acid for acne", []),
    ("salicylic acid wash for my back", ["cleanser"]),
    ("a bha liquid for my nose", ["leave-on liquid"]),
    ("salicylic acid pads", ["pads"]),
    ("glycolic acid peel at home", ["peel"]),
    ("pads with salicylic acid", ["pads"]),
    ("salicylic acid 2% liquid", ["leave-on liquid"]),
    ("salicylic acid that won't make my skin peel", []),  # "peel" here isn't the product's form
    ("salicylic acid, I'm tired of washing my face twice", []),
])
def test_a_request_names_a_form_only_next_to_its_ingredient(text, forms):
    from engine.ingredients import forms_named

    assert forms_named(text, find_ingredients(text)) == forms
