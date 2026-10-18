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
    # Changed on purpose 18 Oct 2026 (the ws-names builder): "portable charger" is another name of the power bank, not a
    # kind of it (config.TYPE_OTHER_NAMES), so "portable" is the product's own word. Was: ["portable"].
    ("portable charger", []),
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
    # Changed on purpose 18 Oct 2026 (the ws-names builder): for a frying pan "non toxic" asks for PFAS-free (Claude's
    # call of 18 Oct 2026; engine/tests/test_non_toxic_pfas.py), named "PFAS-free". A yoga mat's is the
    # need of two words this case is about. Was: ("non toxic frying pan", ["non toxic"]).
    ("non toxic yoga mat", ["non toxic"]),
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
    # Changed on purpose 18 Oct 2026 (the ws-names builder): an induction hob is the induction need, named once (config
    # NEEDS["induction-compatible"]), and a gas stove says nothing of it; a gas hob's hob is found in "stove" as before.
    # Was: ("kettle for an induction hob", "Works on my gas stove too.", "hob").
    ("kettle for a gas hob", "Works on my stove top too.", "hob"),
])
def test_a_request_word_is_found_in_its_other_words(request_text, body, need):
    assert need in met(request_text, body)


def test_removing_makeup_isnt_wearing_it():
    assert met("moisturiser that works under makeup", "I use it to take off my makeup at night.") == ()
    assert met("moisturiser that works under makeup", "My makeup sits on it really well.") == ("makeup",)


# --- 6. Round three (18 Oct 2026, the ws-names builder): from every sweep request's reason words ---

@pytest.mark.parametrize("request_text, needs", [
    # A name that is another name of the type, not a kind of it: its words are the product's ("portable charger" is a
    # power bank; config.TYPE_OTHER_NAMES). A kind stays a need, as before.
    ("portable charger", []),
    ("portable charger for travel", ["travel"]),
    ("battery pack for camping", ["camping"]),
    ("wine cooler for the kitchen", ["wine"]),
    # A one-word name of the type that is a kind is what it asks: a gyuto is a Japanese chef knife (as on 16 Oct; a
    # laptop's "macbook" and an e-reader's "kindle" are title words of their types, left out of needs as before).
    ("210mm gyuto for a beginner, around $100", ["gyuto", "beginner"]),
    # A brand written as what the product is for is a need: a case for an iPhone is about the iPhone.
    ("headphones for my iphone", ["iphone"]),
    ("a case for my iphone 15", ["iphone"]),
    ("charger for my macbook", ["macbook"]),
    # "that'll" and "yrs" are no needs ("20+ yrs" is how long it lasts).
    ("10 inch cast iron skilet that'll last 20+ yrs, under 50 bucks", ["lasting"]),
    # An induction hob is the induction need, named once.
    ("a frying pan for an induction hob", ["induction-compatible"]),
    ("kettle for an induction hob", ["induction-compatible"]),
])
def test_round_three_judged_needs(request_text, needs):
    judged_names = list(dict.fromkeys(need.name if need.request_word is None else (need.label or need.name)
                                      for need in judged_needs(parse_query(request_text, model=None))))
    assert judged_names == needs


def test_a_brand_naming_which_products_is_still_no_need():
    assert "cerave" not in judged("cerave or similar cleanser for oily skin")
    assert "lodge" not in judged("a cast iron skillet like lodge but lighter")
