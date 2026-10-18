"""Need words, round two (17 Oct 2026, the ws-names builder; Claude's technical calls within Noemi's rules, reported to
her). What the 16 Oct reviews of module 1 and of ranking still listed, and the day's sweep showed in reason lines:

1. In kitchen and general requests the type's own words are no judged need: the last word of the name module 1 found
   ("freezer" in "fridge freezer", "machine" in "coffee machine", "charger" in "portable charger") and the kitchen's
   own words inside it ("coffee" in "coffee machine", "tea" in "tea kettle"). A kind the name holds stays one
   ("gaming" laptop, "noise cancelling" headphones, "cast iron" kettle, "wine" cooler).
2. Two words that make one need are named whole, as typed: config.NEED_PHRASES (more of them: dog hair, no pull, true
   wireless, raw denim, large pores, double cleansing, chapped lips...), found also inside the product's name ("noise
   cancelling headphones"), and any own words written next to each other ("small garden", "bread dough", "video
   calls"), a number before them included ("three storey house"); a need that is a verb reads as one ("drying fast",
   "staying cool", "keeping drinks cold", "slipping").
3. A skin type is a need of a kitchen or general request only when the request is about skin ("razor for sensitive
   skin"): "towels that dry fast" asks about drying, not dry skin.
4. A brand is no judged need ("cerave or similar"): it says which products, not what for.
5. A request's own word is found in its other words too: "university" in comments saying "uni" or "college", "hob" in
   "stove"; and not in words that say something else ("works under makeup" isn't removing makeup).

Every request and comment here is made up; nothing reads data/ but the shipped lists.
"""

import pytest

from engine.needs import judged_needs, needs_met, request_needs
from engine.query import parse_query


def judged(request_text: str) -> list[str]:
    """The judged needs as the reason line names them (Need.label, else the need's name)."""
    return list(dict.fromkeys(need.label or need.name for need in judged_needs(parse_query(request_text, model=None))))


def met(request_text: str, body: str) -> tuple[str, ...]:
    return needs_met(body, judged_needs(parse_query(request_text, model=None)))


# --- 1. The type's own words ---

@pytest.mark.parametrize("request_text, needs", [
    ("fridge freezer that's quiet", ["quiet"]),
    ("coffee machine", []),
    ("coffee machine with a good steam wand", ["steam wand"]),
    ("portable charger", ["portable"]),
    ("a tea kettle that whistles", ["whistling"]),
    ("wine cooler for the kitchen", ["wine"]),
    ("water filter jug", []),
    # A kind the type's names hold stays a need.
    ("best gaming laptop under 800", ["gaming"]),
    ("noise cancelling headphones", ["noise cancelling"]),
    ("true wireless earbuds for running", ["true wireless", "running"]),
    ("a cast iron kettle", ["cast iron"]),
    ("enamelled cast iron casserole", ["enamelled cast iron"]),
    ("mechanical keyboard", ["mechanical"]),
    # A word of the type's title words was no need before either: "carry on" (a suitcase's), "mesh" (a router's).
    ("carry on suitcase", []),
    ("cordless drill", ["cordless"]),
])
def test_the_types_own_words_are_no_judged_need(request_text, needs):
    assert judged(request_text) == needs


def test_they_stay_needs_for_the_threads_read_first():
    # The library's first reading still reads threads about a fridge freezer first.
    names = [need.name for need in request_needs(parse_query("fridge freezer that's quiet", model=None))]
    assert "freezer" in names


# --- 2. Two words that make one need ---

@pytest.mark.parametrize("request_text, needs", [
    ("robot vacuum that handles dog hair under £300", ["dog hair"]),
    ("a vacuum for pet hair", ["pet hair"]),
    ("no pull dog harness for a big puppy", ["no pull", "big puppy"]),
    ("raw denim jeans that fade well", ["raw denim", "fading"]),
    ("lawn mower for a small garden", ["small garden"]),
    ("tv for a small living room", ["small living room"]),
    ("stand mixer for bread dough", ["bread dough"]),
    ("niacinamide serum for large pores", ["large pores"]),
    ("double cleansing oil for beginners", ["double cleansing", "beginner"]),
    ("lip balm that actually works for chapped lips", ["chapped lips"]),
    ("lip balm that actually fixes cracked lips, less than 5 dollars", ["cracked lips"]),
    ("webcam for video calls", ["video calls"]),
    ("mesh wifi for a three storey house", ["three storey house"]),
    ("non toxic frying pan", ["non toxic"]),
    ("water bottle that keeps drinks cold", ["keeping drinks cold"]),
    ("bed sheets that stay cool", ["staying cool"]),
    ("a yoga mat that doesn't slip", ["slipping"]),
    ("dutch oven that won't chip", ["chipping"]),
    ("pram that folds small for a car boot", ["folding small", "car boot"]),
])
def test_words_that_make_one_need_are_named_whole(request_text, needs):
    assert judged(request_text) == needs


def test_a_need_named_whole_is_still_found_by_each_word():
    # As on 16 Oct 2026: comments are found by each word ("the wand is great" talks about a steam wand).
    assert met("robot vacuum that handles dog hair", "It copes with my dog's shedding.") == ("dog",)
    assert met("robot vacuum that handles dog hair", "Fine with two dogs in the house.") == ("dog",)


def test_a_skin_need_named_with_the_lips_says_so():
    needs = judged_needs(parse_query("lip balm for very dry lips", model=None))
    assert [(need.name, need.label) for need in needs] == [("dry", "dry lips")]


def test_a_word_said_twice_takes_the_label_of_where_it_is_first():
    # "travel" first names the kind of backpack, alone; "bag" is written with the second one, a number before them.
    assert judged("travel backpack for one bag travel") == ["travel", "one bag travel"]


# --- 3. Skin types only for skin ---

def test_a_skin_type_word_is_no_skin_need_outside_skin():
    assert judged("towels that dry fast") == ["drying fast"]
    assert judged("razor for sensitive skin") == ["sensitive"]


# --- 4. Brands ---

@pytest.mark.parametrize("request_text, needs", [
    ("fragrance free clenser for oily acne prone skin, cerave or similar, under 12.50",
     ["fragrance-free", "oily", "acne-prone"]),
    ("a cast iron skillet like lodge but lighter", ["lighter"]),
])
def test_a_brand_is_no_judged_need(request_text, needs):
    assert judged(request_text) == needs


# --- 5. A request's own word in other words ---

@pytest.mark.parametrize("request_text, body, need", [
    ("a laptop for university", "Perfect for uni, the battery lasts all day.", "university"),
    ("a laptop for university", "I took it through four years of college.", "university"),
    ("a laptop for uni", "It got me through university.", "uni"),
    ("noise cancelling headphones for commuting", "Great on my commute.", "commuting"),
    ("kettle for an induction hob", "Works on my gas stove too.", "hob"),
])
def test_a_request_word_is_found_in_its_other_words(request_text, body, need):
    assert need in met(request_text, body)


def test_removing_makeup_isnt_wearing_it():
    assert met("moisturiser that works under makeup", "I use it to take off my makeup at night.") == ()
    assert met("moisturiser that works under makeup", "My makeup sits on it really well.") == ("makeup",)
