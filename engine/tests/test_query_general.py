"""Module 1 and the general category (14 Oct 2026, Noemi: "I want recs regardless of the category"; her plan's part 1).

Any product people buy and use gets a product type: module 1's own (engine/data/product_types.json, about 350 types in
departments) or one the open model names. What stays out gets a polite no in its own words: services, places and
advice that isn't about buying; food and drink; medicines and supplements; books, films, music, games and apps; and
weapons, drugs, tobacco and vaping, and adult products. Every request here is made up, and the rules alone route them
(the open model is off in tests).
"""

import json
import re

import pytest

from engine import config
from engine.config import GENERAL_DEPARTMENTS, MORE_PRODUCT_TYPES, PRODUCT_TYPE_PLURALS, SUBREDDITS
from engine.query import (
    FOOD_MESSAGE, HARMFUL_MESSAGE, HEALTH_MESSAGE, LOOKALIKES, MEDIA_MESSAGE, OUT_OF_SCOPE_MESSAGE, PRODUCT_TYPES,
    TITLE_WORDS, ParsedQuery, classify, correct_typos, parse_query,
)


def routed(text: str) -> tuple:
    routing = classify(text)
    return routing.status, routing.category, routing.product_type, routing.department


# --- The orchestrator's examples, and products across the departments ---

@pytest.mark.parametrize("text, category, product_type, department", [
    ("microwave that heats evenly", "kitchen", "microwave", None),
    ("hiking boots for wide feet", "general", "hiking boots", "outdoor"),
    ("robot vacuum for pet hair", "general", "robot vacuum", "home"),
    ("noise cancelling headphones under £200", "general", "headphones", "tech"),
    ("quiet dishwasher for a small kitchen", "kitchen", "dishwasher", None),
    ("dog harness for a puppy that pulls", "general", "dog harness", "pets"),
    ("baby carrier for a newborn", "general", "baby carrier", "baby"),
    ("best laptop for uni under 800", "general", "laptop", "tech"),
    ("hair dryer that wont fry my curls under £100", "general", "hair dryer", "beauty"),
    ("mattress for side sleepers", "general", "mattress", "home"),
    ("cordless drill for a first flat", "general", "drill", "tools"),
    ("adjustable dumbbells for a home gym", "general", "dumbbells", "fitness"),
    ("selvedge jeans that last", "general", "jeans", "clothing"),
    ("a dash cam with a rear camera", "general", "dash cam", "car"),
    ("fountain pen for a beginner", "general", "fountain pen", "hobbies"),
    ("air conditioner for a small flat", "general", "air conditioner", "home"),
    ("oven cleaner that actually works", "general", "oven cleaner", "home"),
    ("best barbecue under £300", "kitchen", "barbecue", None),
    ("hair gel that doesn't flake", "haircare", "hair gel", None),
])
def test_products_outside_the_first_three_categories_get_a_product_type(text, category, product_type, department):
    assert routed(text) == ("ok", category, product_type, department)


def test_the_general_category_is_one_engine_category_with_departments():
    # One category, so a robot vacuum or a rain jacket never falls between two (config.THREAD_CATEGORIES); the
    # department is what the page shows and what a type the open model names is searched by.
    assert config.THREAD_CATEGORIES == ("skincare", "kitchen", "haircare", "general")
    assert "general" in config.MENTION_CATEGORIES and "other" in config.MENTION_CATEGORIES
    assert set(GENERAL_DEPARTMENTS) == {"home", "tech", "outdoor", "clothing", "baby", "pets", "fitness", "tools",
                                        "beauty", "hobbies", "car"}
    for department, entry in GENERAL_DEPARTMENTS.items():
        assert entry["label"] and entry["noun"] and entry["examples"] and entry["hints"], department
        assert set(entry["communities"]) <= set(SUBREDDITS["general"]), department


def test_a_parsed_general_request_carries_its_department():
    query = parse_query("noise cancelling headphones under £200")
    assert (query.status, query.category, query.department) == ("ok", "general", "tech")
    assert query.subreddits[0] == "headphones" and query.constraints.budget.max == 200
    assert parse_query("electric kettle that lasts 10+ years").department is None


def test_only_a_general_request_has_a_department():
    with pytest.raises(ValueError):
        ParsedQuery(text="kettle", status="ok", category="kitchen", product_type="electric kettle",
                    search_terms=["kettle"], subreddits=["BuyItForLife"], department="home")
    with pytest.raises(ValueError):
        ParsedQuery(text="x", status="ok", category="general", product_type="widget", search_terms=["widget"],
                    subreddits=["BuyItForLife"], department="garden")


# --- The taxonomy as data (engine/data/product_types.json) ---

def test_the_taxonomy_holds_about_300_types_across_departments():
    general = [t for t in MORE_PRODUCT_TYPES if t["category"] == "general"]
    assert len(MORE_PRODUCT_TYPES) >= 300 and len(general) >= 280
    by_department = {d: sum(t["department"] == d for t in general) for d in GENERAL_DEPARTMENTS}
    assert all(n >= 10 for n in by_department.values()), by_department
    assert {t["category"] for t in MORE_PRODUCT_TYPES} == {"general", "kitchen", "haircare"}
    # Left out on purpose (config.MORE_PRODUCT_TYPES): their names covered words the first types' answers read, or
    # (curl cream, 14 Oct 2026, found merging main) a first type's advice names them: the open model still places them.
    assert not ({"body wash", "body lotion", "hand cream", "cookware set", "curl cream"}
                & {t["name"] for t in MORE_PRODUCT_TYPES})
    assert routed("curl cream for 3a curls")[0] == "clarify"  # the rules' question; the open model places it, as before


def test_every_type_of_the_taxonomy_is_well_formed():
    names = [p.name for p in PRODUCT_TYPES]
    assert len(names) == len(set(names))
    for entry in MORE_PRODUCT_TYPES:
        assert entry["name"] == entry["name"].lower() and entry["name"] in entry["keywords"], entry["name"]
        assert entry["plural"] and PRODUCT_TYPE_PLURALS[entry["name"]] == entry["plural"], entry["name"]
        assert entry["title_words"] and TITLE_WORDS[entry["name"]] == tuple(entry["title_words"]), entry["name"]
        assert entry["subreddits"] and set(entry["subreddits"]) <= set(SUBREDDITS[entry["category"]]), entry["name"]
        assert (entry.get("department") in GENERAL_DEPARTMENTS) == (entry["category"] == "general"), entry["name"]
        for word in entry["keywords"] + entry.get("hints", []) + entry["title_words"]:
            assert word == word.lower() and word.strip() == word, (entry["name"], word)


def test_no_two_types_share_a_name():
    seen = {}
    for product in PRODUCT_TYPES:
        for keyword in product.keywords:
            assert seen.setdefault(keyword, product.name) == product.name, keyword


def test_each_type_is_found_by_its_own_name_and_plural():
    # So `library add "<type>"`, the pre-check and the warm-up, which ask for each type by its name, find it.
    for entry in MORE_PRODUCT_TYPES:
        for text in (entry["name"], entry["plural"], f"best {entry['name']} that lasts"):
            assert classify(text).product_type == entry["name"], text


def test_each_name_of_a_general_type_finds_that_type():
    for entry in MORE_PRODUCT_TYPES:
        for keyword in entry["keywords"]:
            assert classify(f"recommendations for a {keyword}").product_type == entry["name"], keyword


def test_a_types_look_alikes_hold_its_words_and_are_set_aside():
    # Kept with their types as data (part 2 chooses threads with them too): each holds one of its type's words.
    for entry in MORE_PRODUCT_TYPES:
        words = entry["keywords"] + entry.get("hints", [])
        for phrase in entry.get("lookalikes", []):
            assert any(re.search(rf"\b{re.escape(w.removesuffix('s'))}s?\b", phrase) for w in words), (entry["name"],
                                                                                                        phrase)
            assert phrase in LOOKALIKES, phrase
    assert sum(len(entry.get("lookalikes", [])) for entry in MORE_PRODUCT_TYPES) >= 100


def test_a_look_alike_is_never_a_products_own_name():
    # Set aside before products are looked for, a look-alike that is a name would hide its own product.
    names = {k for product in PRODUCT_TYPES for k in product.keywords}
    assert not [phrase for phrase in LOOKALIKES if phrase in names]


def test_the_communities_of_noemis_plan_are_general_subreddits():
    planned = ("BuyItForLife", "headphones", "BudgetAudiophile", "MechanicalKeyboards", "SuggestALaptop", "laptops",
               "Monitors", "HomeImprovement", "homeowners", "VacuumCleaners", "Mattress", "smarthome", "homeautomation",
               "Tools", "HomeDecorating", "Frugal", "Ultralight", "CampingGear", "onebag", "HerOneBag", "bicycling",
               "malefashionadvice", "femalefashionadvice", "frugalmalefashion", "goodyearwelt", "Boots",
               "RunningShoeGeeks", "homegym", "NewParents", "beyondthebump", "dogs", "Watches")
    assert SUBREDDITS["general"][:len(planned)] == planned
    used = {s for t in MORE_PRODUCT_TYPES if t["category"] == "general" for s in t["subreddits"]}
    assert set(planned) <= used  # each is some type's community
    assert len(set(SUBREDDITS["general"])) == len(SUBREDDITS["general"])


def test_each_type_is_searched_in_its_specialist_communities_first():
    assert parse_query("mechanical keyboard").subreddits[0] == "MechanicalKeyboards"
    assert parse_query("laptop for video editing").subreddits[:2] == ["SuggestALaptop", "laptops"]
    assert parse_query("running shoes for flat feet").subreddits[0] == "RunningShoeGeeks"
    assert parse_query("stroller that folds small").subreddits[0] == "NewParents"
    assert parse_query("dive watch under £500").subreddits[0] == "Watches"
    assert parse_query("tent for wild camping").subreddits[0] == "CampingGear"


# --- Context: what the product is for, with or on ---

@pytest.mark.parametrize("text, product_type", [
    ("headphones for my phone", "headphones"),
    ("a monitor for my macbook", "monitor"),
    ("a lamp on my desk", "lamp"),
    ("a frying pan for an induction hob", "frying pan"),
    ("saucepan that works on an induction hob", "saucepan"),
    ("a laptop with a good keyboard", "laptop"),
    ("phone with a good camera", "phone"),
    ("coffee machine with a milk frother", "espresso machine"),
    ("burr grinder for pour over", "coffee grinder"),
    ("looking for a kettle", "electric kettle"),  # "looking for" asks for the kettle itself
    ("recommendations for a laptop", "laptop"),
    ("tips for choosing a mattress", "mattress"),
])
def test_a_product_named_as_what_the_request_is_for_isnt_the_product_asked_for(text, product_type):
    assert classify(text).product_type == product_type


# 16 Oct 2026 (the interview-fixes builder): what a product is easy, gentle or kind on, or won't dull or blunt, is what
# it is for: "cutting board that's easy on knives" (an interviewee request) had asked "the cutting board or the chef
# knife?"; "easy on my knives" already worked.
@pytest.mark.parametrize("text", [
    "cutting board that's easy on knives",
    "cutting board that's easy on my knives",
    "cutting board gentle on knives",
    "cutting board kind to knives",
    "cutting board that is kind to my knives",
    "cutting board that won't dull my knife",
    "chopping board that won't blunt my knives",
    "cutting board that doesn't dull knives",
    "cutting board safe for knives",
    "cutting board that's soft on knife edges",
])
def test_what_a_product_is_easy_on_or_wont_dull_is_what_it_is_for(text):
    query = parse_query(text)
    assert (query.status, query.product_type) == ("ok", "cutting board"), query.question


@pytest.mark.parametrize("text, product_type", [
    ("a bed for my dog", "dog bed"),
    ("toys for my cat", "cat toy"),
    ("a case for my iphone 15", "phone case"),
    ("charger for my laptop", "charger"),
    ("a lens for my sony camera", "camera lens"),
    ("mount for my tv", "tv mount"),
    ("shoes for running", "running shoes"),
    ("boots for hiking", "hiking boots"),
    ("a harness for my puppy", "dog harness"),
    ("lights for my bike", "bike light"),
])
def test_a_product_named_the_other_way_round_is_found(text, product_type):
    assert classify(text).product_type == product_type


def test_a_request_only_about_something_for_a_product_is_asked_about():
    # "a stand for my phone": a stand, not a phone; the rules don't know the stand, so they ask (the open model reads it).
    for text in ("a stand for my phone", "something for my laptop", "a cover for my sofa"):
        routing = classify(text)
        assert routing.status == "clarify" and not routing.several, text


@pytest.mark.parametrize("text, product_type", [
    ("laptop backpack for commuting", "backpack"),
    ("tv soundbar under £200", "soundbar"),
    ("cast iron dutch oven that lasts", "dutch oven"),
    ("bike helmet with mips", "bike helmet"),
])
def test_of_two_names_written_together_the_last_is_the_product(text, product_type):
    assert classify(text).product_type == product_type


def test_a_name_that_is_a_requirement_or_not_wanted_isnt_the_product():
    assert classify("fragrance-free moisturiser").product_type == "moisturiser"
    assert classify("fragrance free cleanser").product_type == "cleanser"
    assert classify("dishwasher-safe chef knife").product_type == "chef knife"
    assert classify("dutch oven safe to 260c").product_type == "dutch oven"
    assert classify("earbuds, not headphones").product_type == "earbuds"
    assert classify("a laptop instead of a tablet").product_type == "laptop"


def test_two_products_still_get_one_question():
    routing = classify("headphones or earbuds for the gym?")
    assert routing.status == "clarify" and routing.several
    assert classify("a kettle and a good chef knife").several


@pytest.mark.parametrize("text, not_this", [
    ("phone plan with lots of data", "phone"),
    ("tv show like succession", "tv"),
    ("laptop stand for my desk", "laptop"),
    ("a mouse mat that's big", "mouse"),
    ("life jacket for kayaking", "jacket"),
    ("bike pump that's compact", "bicycle"),
    ("nail clippers that last", "beard trimmer"),
    ("mattress protector that's waterproof", "mattress"),
    ("eyelash curler", "curling iron"),
])
def test_a_look_alike_of_a_general_type_isnt_that_type(text, not_this):
    assert classify(text).product_type != not_this


# --- What stays out, each with its own polite no ---

@pytest.mark.parametrize("text", ["a good plumber near me", "best hotel in rome", "cheap flights to lisbon",
                                  "best credit card for travel", "a vpn that's fast", "how do I get rid of mould",
                                  "why does my back hurt when I wake up"])
def test_services_places_and_advice_get_the_polite_no(text):
    routing = classify(text)
    assert (routing.status, routing.message, routing.category) == ("out_of_scope", OUT_OF_SCOPE_MESSAGE, None)


@pytest.mark.parametrize("text, message", [
    ("best coffee beans for espresso", FOOD_MESSAGE),
    ("best dog food for a puppy", FOOD_MESSAGE),
    ("a whisky under £50", FOOD_MESSAGE),
    ("vitamin d supplement for winter", HEALTH_MESSAGE),
    ("best painkiller for headaches", HEALTH_MESSAGE),
    ("protein powder that mixes well", HEALTH_MESSAGE),
    ("best books about stoicism", MEDIA_MESSAGE),
    ("a film to watch tonight", MEDIA_MESSAGE),
    ("best games for my ps5", MEDIA_MESSAGE),
])
def test_food_health_and_media_get_their_own_polite_no(text, message):
    routing = classify(text)
    assert (routing.status, routing.message) == ("out_of_scope", message)


@pytest.mark.parametrize("text", ["best gun for home defense", "a knife for self defence", "pepper spray for running",
                                  "best vape for beginners", "weed grinder that lasts", "a good bong"])
def test_harmful_items_are_refused_whatever_else_the_request_names(text):
    assert (classify(text).status, classify(text).message) == ("out_of_scope", HARMFUL_MESSAGE)


@pytest.mark.parametrize("text", ["my secret weapon for frizz is a silk pillowcase", "a tobacco vanille dupe",
                                  "a noise suppressor pedal for my guitar", "rifle paper co notebook"])
def test_a_harmful_word_in_an_everyday_phrase_isnt_refused(text):
    assert classify(text).message != HARMFUL_MESSAGE


@pytest.mark.parametrize("text, product_type", [
    ("glue gun for crafts", "glue gun"),
    ("massage gun for sore legs", "massage gun"),
    ("weed eater that starts first time", "string trimmer"),
    ("nicotine patches to quit", None),  # health, not harmful
])
def test_a_products_name_holding_a_harmful_word_isnt_refused_as_harmful(text, product_type):
    routing = classify(text)
    assert routing.message != HARMFUL_MESSAGE
    assert routing.product_type == product_type


def test_a_product_named_with_a_health_or_food_word_is_still_the_product():
    assert classify("vitamin c serum for dull skin").product_type == "serum"
    assert classify("food processor for hummus").product_type == "food processor"
    assert classify("board games for two players").product_type == "board game"


# --- Questions within a department ---

@pytest.mark.parametrize("text, department", [
    ("something for my dog", "pets"),
    ("a gift for a new baby", "baby"),
    ("stuff for my home gym", "fitness"),
    ("something for camping", "outdoor"),
])
def test_a_vague_request_with_a_departments_words_asks_within_it(text, department):
    # Changed on purpose 17 Oct 2026 (the ws-names builder): a dog's question names a dog's products
    # (engine.query.PET_EXAMPLES), not the pets department's, which offered a dog a litter box.
    from engine.query import PET_EXAMPLES

    routing = classify(text)
    assert (routing.status, routing.category, routing.department) == ("clarify", "general", department)
    examples = PET_EXAMPLES["dog"] if "dog" in text else GENERAL_DEPARTMENTS[department]["examples"]
    assert examples in routing.question


def test_a_vague_request_still_gets_a_question_not_a_no():
    # Noemi's approved q23 and q24 stay questions.
    assert classify("something nice for my mum").status == "clarify"
    assert classify("need something for my skin its been really dry lately").category == "skincare"
    assert classify("gift for my boyfriend").status == "clarify"


# --- Typos ---

def test_a_typo_in_a_long_general_product_name_is_forgiven():
    assert parse_query("vaccum for pet hair").product_type == "vacuum cleaner"
    assert parse_query("headphnes for the gym").product_type == "headphones"
    assert parse_query("best matress for back pain").product_type == "mattress"


@pytest.mark.parametrize("text", ["vit c for dark spots", "stand mixer for bread", "laser pointer for my cat",
                                  "pest deterrent for the garden", "a screen protector"])
def test_everyday_words_are_never_corrected_into_a_general_name(text):
    # "spots" isn't "sports" misspelt, "stand" isn't "stands", "pointer" isn't "printer", "deterrent" isn't "detergent".
    assert correct_typos(text) == text


def test_the_extraction_instructions_name_the_general_category():
    from engine.extract import DEFAULT_INSTRUCTIONS

    text = " ".join(DEFAULT_INSTRUCTIONS.read_text(encoding="utf-8").split())
    assert '"general"' in text and re.search(r"Category: \"skincare\", \"kitchen\", \"haircare\", \"general\" or \"other\"", text)


def test_the_taxonomy_file_is_valid_json_with_its_explanation():
    data = json.loads(config.PRODUCT_TYPES_FILE.read_text(encoding="utf-8"))
    assert "about" in data and len(data["types"]) == len(MORE_PRODUCT_TYPES)


# --- The open model's long tail (stand-in models only: tests never load the real one) ---

class FakeModel:
    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def read(self, text: str):
        self.asked.append(text)
        return self.answer


def test_a_product_no_type_lists_is_placed_in_the_department_the_model_names():
    model = FakeModel({"category": "beauty", "product": "eyelash curler"})
    query = parse_query("eyelash curler that doesn't pinch", model=model)
    assert (query.status, query.category, query.product_type, query.department) == (
        "ok", "general", "eyelash curler", "beauty")
    assert query.subreddits == list(GENERAL_DEPARTMENTS["beauty"]["communities"])
    assert model.asked == ["eyelash curler that doesn't pinch"]


def test_a_product_the_rules_know_by_name_is_routed_as_the_rules_route_it_whatever_the_department():
    # The model asked about "a stand for my kettle" may answer "kettle" in "home": it is the kitchen's electric kettle.
    query = parse_query("a stand for my kettle", model=FakeModel({"category": "home", "product": "kettle"}))
    assert (query.category, query.product_type) == ("kitchen", "electric kettle")


def test_the_models_other_is_the_polite_no_and_its_unknown_departments_are_ignored():
    assert parse_query("a fun weekend in york", model=FakeModel({"category": "other", "product": ""})).message \
        == OUT_OF_SCOPE_MESSAGE
    assert parse_query("best label maker", model=FakeModel({"category": "garden", "product": "label maker"})).status \
        == "clarify"


def test_an_animal_or_a_department_word_is_no_product():
    for text, answer in (("something for my dog", {"category": "pets", "product": "dog"}),
                         ("tech stuff for a student", {"category": "tech", "product": "tech stuff"})):
        assert parse_query(text, model=FakeModel(answer)).product_type is None, text


def test_the_models_categories_are_the_three_and_the_departments():
    from engine.query_model import MODEL_CATEGORIES, SCHEMA

    assert MODEL_CATEGORIES == ("skincare", "haircare", "kitchen", *GENERAL_DEPARTMENTS)
    assert SCHEMA["properties"]["category"]["enum"] == [*MODEL_CATEGORIES, "other", "unclear"]
