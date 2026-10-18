"""Module 1, round two (17 Oct 2026, the ws-names builder; Claude's technical calls, reported to Noemi): the routing
eval's last misses, what the 16 Oct review of module 1 still listed (docs' understanding review: U6, U8, U9), and the
questions a vague request gets.

1. The open model's product is placed by its own words, after the model: a thing made for a product goes where that
   product is (a mouse mat with the mouse, in tech; a bike pump with the bike, outdoors; guitar strings with the guitar,
   in hobbies; a tyre pressure gauge with the tyres, in car; a knife block set with the knives, in the kitchen); a maker
   of food or drink is a kitchen appliance (a baby food maker); something put on the hair is haircare (a hair toner),
   something put on the skin skincare (a sheet mask). The model had placed them by its own habits ("tools" for most).
2. A model that answers with the word of a thing made for a product ("case" for "ipad case for kids") names that thing,
   the request's own words ("ipad case"); it had been refused, and the request asked about as a baby product.
3. Two products at once ("le creuset or staub") or a brand ("cerave") is never a product type of its own: the model's
   answer is refused and the rules' question stands.
4. A kitchen mixer tap is a tap (a product of its own, in home, engine.query.LONG_TAIL_PRODUCTS), never a stand mixer
   question.
5. Skin concerns place a vague request in skincare (dark circles, blackheads, dry lips, eczema, rosacea...), so it gets
   the skincare question, not the general one; eczema is sensitive skin, as rosacea is (16 Oct 2026).
6. A plural name's plural is itself ("guitar strings", not "guitar stringses").
7. Questions: a gift asks what kind of gift, or what they like; a dog's products are a dog's (wording PROPOSED).

Every request is made up; the open model is off in tests (stand-in models only).
"""

import pytest

from engine.config import GENERAL_DEPARTMENTS, SUBREDDITS
from engine.group_products import plural
from engine.needs import request_needs
from engine.product_facts import request_asks
from engine.query import classify, parse_query


class FakeModel:
    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def read(self, text: str):
        self.asked.append(text)
        return self.answer


def placed(text: str, answer: dict) -> tuple:
    query = parse_query(text, model=FakeModel(answer))
    return query.status, query.category, query.product_type, query.department


# --- 1. The model's product placed by its own words ---

@pytest.mark.parametrize("text, answer, expected", [
    ("a mouse mat that's huge", {"category": "home", "product": "mouse mat"},
     ("ok", "general", "mouse mat", "tech")),
    ("bike pump that fits presta valves", {"category": "tools", "product": "bike pump"},
     ("ok", "general", "bike pump", "outdoor")),
    ("guitar strings for an acoustic", {"category": "tools", "product": "guitar strings"},
     ("ok", "general", "guitar strings", "hobbies")),
    ("tyre pressure gauge", {"category": "tools", "product": "tyre pressure gauge"},
     ("ok", "general", "tyre pressure gauge", "car")),
    ("knife block set under £150", {"category": "tools", "product": "knife block set"},
     ("ok", "kitchen", "knife block set", None)),
    ("baby food maker", {"category": "home", "product": "baby food maker"},
     ("ok", "kitchen", "baby food maker", None)),
    ("hair toner for brassy hair", {"category": "beauty", "product": "hair toner"},
     ("ok", "haircare", "hair toner", None)),
    ("sheet masks that are actually worth it", {"category": "beauty", "product": "sheet mask"},
     ("ok", "skincare", "sheet mask", None)),
])
def test_the_models_product_goes_where_its_own_words_say(text, answer, expected):
    assert placed(text, answer) == expected


@pytest.mark.parametrize("text, answer, expected", [
    # Its own head word is another product's ("cooler", "grinder", "shampoo"): no owner, the model's department stands.
    ("cpu cooler for a gaming pc", {"category": "tech", "product": "cpu cooler"},
     ("ok", "general", "cpu cooler", "tech")),
    ("bench grinder for sharpening chisels", {"category": "tools", "product": "bench grinder"},
     ("ok", "general", "bench grinder", "tools")),
    ("carpet shampoo for my vax", {"category": "home", "product": "carpet shampoo"},
     ("ok", "general", "carpet shampoo", "home")),
    # Nothing in its words says where: the model's department.
    ("label maker for organising the garage", {"category": "tools", "product": "label maker"},
     ("ok", "general", "label maker", "tools")),
    ("eyelash curler that doesn't pinch", {"category": "beauty", "product": "eyelash curler"},
     ("ok", "general", "eyelash curler", "beauty")),
    # A hair tool stays a general beauty product (Noemi's q29, 14 Oct 2026), and so does make-up.
    ("hair claw clips that don't snap", {"category": "beauty", "product": "hair claw clips"},
     ("ok", "general", "hair claw clips", "beauty")),
    ("lash glue that holds all day", {"category": "beauty", "product": "lash glue"},
     ("ok", "general", "lash glue", "beauty")),
])
def test_without_such_words_the_models_department_stands(text, answer, expected):
    assert placed(text, answer) == expected


def test_a_placed_kitchen_product_reads_the_kitchens_communities():
    query = parse_query("baby food maker", model=FakeModel({"category": "home", "product": "baby food maker"}))
    assert query.subreddits == list(SUBREDDITS["kitchen"])
    query = parse_query("a mouse mat that's huge", model=FakeModel({"category": "home", "product": "mouse mat"}))
    assert query.subreddits == list(GENERAL_DEPARTMENTS["tech"]["communities"])


# --- 2. The word of a thing made for a product names that thing ---

def test_a_model_answering_with_the_accessory_word_names_the_whole_thing():
    assert placed("ipad case for kids", {"category": "clothing", "product": "case"}) == (
        "ok", "general", "ipad case", "tech")


def test_the_accessory_word_alone_is_never_a_product_of_its_own():
    # No thing named for a product in the request: "case" alone stays refused (the request's question stands).
    query = parse_query("a sturdy case", model=FakeModel({"category": "tech", "product": "case"}))
    assert query.product_type != "case"


# --- 3. Two products or a brand is never a type ---

def test_two_brands_compared_are_never_one_product_type():
    query = parse_query("le creuset or staub", model=FakeModel({"category": "tools", "product": "le creuset or staub"}))
    assert query.status == "clarify" and query.product_type is None


def test_a_brand_is_never_a_product_type():
    query = parse_query("cerave or la roche posay for eczema",
                        model=FakeModel({"category": "skincare", "product": "cerave"}))
    assert query.status == "clarify" and query.product_type is None
    assert query.category == "skincare"  # eczema: the skincare question


# --- 4. A kitchen mixer tap is a tap ---

@pytest.mark.parametrize("text", ["kitchen mixer tap", "a kitchen tap that doesn't drip", "basin mixer tap",
                                  "kitchen faucet with a pull out spray"])
def test_a_tap_is_a_tap(text):
    routing = classify(text)
    assert (routing.status, routing.category, routing.product_type, routing.department) == (
        "ok", "general", "mixer tap", "home")


def test_a_kitchen_mixer_is_still_a_stand_mixer():
    assert classify("kitchen mixer for bread dough").product_type == "stand mixer"


# --- 5. Skin concerns ask the skincare question; eczema is sensitive skin ---

@pytest.mark.parametrize("text", ["something for dark circles", "something for my dry lips", "something for blackheads",
                                  "something to fade dark spots", "help with my eczema", "anything for rosacea",
                                  "what helps with redness", "something for hyperpigmentation"])
def test_a_skin_concern_asks_the_skincare_question(text):
    query = parse_query(text, model=None)
    assert (query.status, query.category) == ("clarify", "skincare")


def test_eczema_is_sensitive_skin():
    query = parse_query("moisturiser for eczema", model=None)
    assert "sensitive" in [need.name for need in request_needs(query)]
    assert "sensitive" in request_asks(query)  # the sensitive-skin rules apply, as for rosacea


def test_eczema_prone_skin_is_sensitive_and_prone_is_no_need():
    query = parse_query("cream for eczema prone skin", model=None)
    names = [need.name for need in request_needs(query)]
    assert "sensitive" in names and "prone" not in names and "eczema" not in names


def test_a_scalp_with_eczema_is_a_sensitive_scalp():
    query = parse_query("shampoo for eczema on my scalp", model=None)
    assert "sensitive scalp" in [need.name for need in request_needs(query)]


# --- 6. Plurals ---

@pytest.mark.parametrize("name, expected", [("guitar strings", "guitar strings"), ("drill bits", "drill bits"),
                                            ("baby food maker", "baby food makers"), ("hair toner", "hair toners"),
                                            ("mixer tap", "mixer taps"), ("glass", "glasses"), ("brush", "brushes"),
                                            ("camera lens", "camera lenses")])
def test_a_plural_name_is_its_own_plural(name, expected):
    assert plural(name) == expected


# --- 7. Questions (wording PROPOSED, 17 Oct 2026) ---

def test_a_gift_with_an_interest_asks_what_kind_of_gift_within_it():
    query = parse_query("a gift for my dad who likes cooking", model=None)
    assert (query.status, query.category) == ("clarify", "kitchen")
    assert "gift" in query.question.lower()
    assert "chef's knife" in query.question


def test_a_gift_without_an_interest_asks_what_they_like():
    for text in ("a gift for my mum", "christmas present for my brother", "a gift for someone who has everything"):
        query = parse_query(text, model=None)
        assert query.status == "clarify"
        assert "like" in query.question.lower(), text


def test_a_gift_in_a_department_asks_within_it():
    query = parse_query("gift for my dad who likes gadgets", model=None)
    assert (query.status, query.department) == ("clarify", "tech")
    assert "gift" in query.question.lower()


def test_a_dogs_question_names_a_dogs_products():
    query = parse_query("something for my dog", model=None)
    assert query.department == "pets" and "litter box" not in query.question
    query = parse_query("something for my cat", model=None)
    assert query.department == "pets" and "litter box" in query.question


def test_a_plain_vague_request_keeps_its_question():
    query = parse_query("something nice", model=None)
    assert query.status == "clarify" and "What kind of product" in query.question


# --- 8. Coffee and tea questions, and brands that say where (wording PROPOSED, 17 Oct 2026) ---

@pytest.mark.parametrize("text", ["present for a coffee lover", "aeropress or v60", "something for my latte habit"])
def test_a_coffee_request_with_no_product_asks_with_coffee_examples(text):
    query = parse_query(text, model=None)
    assert (query.status, query.category) == ("clarify", "kitchen")
    assert "coffee grinder" in query.question and "chef's knife" not in query.question


def test_a_tea_request_with_no_product_asks_with_tea_examples():
    query = parse_query("something for a tea lover", model=None)
    assert query.category == "kitchen" and "teapot" in query.question


def test_two_brands_compared_ask_in_their_category(monkeypatch):
    from engine import query

    monkeypatch.setattr(query, "_brand_categories", lambda: {("le", "creuset"): {"kitchen"}, ("staub",): {"kitchen"},
                                                             ("cerave",): {"skincare"}, ("global",): {"kitchen"}})
    assert (classify("le creuset or staub").status, classify("le creuset or staub").category) == ("clarify", "kitchen")
    assert classify("cerave or la roche posay").category == "skincare"
    assert classify("something with global roaming").category is None  # an everyday word is no brand here
