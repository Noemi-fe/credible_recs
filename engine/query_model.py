"""Module 1's second opinion: a free open model for the requests the rules can't route (Noemi, 11 Oct 2026).

Noemi chose a free open model over a paid API: Qwen2.5 1.5B Instruct (Apache-2.0), a 1.12 GB file
(models/qwen2.5-1.5b-instruct/qwen2.5-1.5b-instruct-q4_k_m.gguf, never committed), run on this machine, or in the
Hugging Face Space, through llama.cpp (the llama-cpp-python package). No call leaves the machine and nothing is paid.

The rules stay first (engine/query.py): the model is asked only when they find no product type and no out-of-scope
word, never when they name two products. It answers in two fixed fields,

    {"category": "skincare" | "kitchen" | "haircare" | <a department of the general category> | "other" | "unclear",
     "product": "<the kind of product, in the request's words>"}

where the general category's departments (config.GENERAL_DEPARTMENTS: "home", "tech", "outdoor", "clothing", "baby",
"pets", "fitness", "tools", "beauty", "hobbies", "car") stand for the general category since 14 Oct 2026 (Noemi's
"I want recs regardless of the category"), and code checks the answer before anything is used (routed_by_model):
- "other": the polite no for what isn't a product to buy and use (a service, a place, advice, food or drink, a
  medicine, a book, a film, a game or an app, anything harmful); until 14 Oct 2026 also every product outside
  skincare, haircare and kitchen gear, as a laptop was;
- a category or a department: the product must be written in the request itself, a plural aside ("rice
  cookers"), so a vague "something nice for my mum" never becomes a "gift set", and not only inside a phrase the rules
  read as something else ("knife" in "tomato knife", "ipad" in "ipad case": 14 Oct 2026); words that name no product
  ("gadget", "stuff") or only a category, a place or an animal ("kitchen gadget", "hair products", "dog") don't count.
  A product the rules route by its name, or by a clue word in the same category, when it is written alone is routed as
  they route it; any other becomes a product type of its own, read from its category's decided subreddits ("yogurt
  maker", "curl cream"), or for the general category from its department's communities ("eyelash curler": beauty's);
- anything else, a broken answer, or a model that fails: the rules' question stands.
Budgets, skin types, sizes and the rest are always read by the rules (the brief: "AI turns the query into structured
fields; rules handle budget and units").
"""

import copy
import json
import os
import re
import threading
from collections import OrderedDict
from functools import cache
from pathlib import Path
from typing import Protocol

from engine.config import GENERAL_DEPARTMENTS, SUBREDDITS, THREAD_CATEGORIES

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = REPO_ROOT / "models" / "qwen2.5-1.5b-instruct" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
# Set to "off" to use the rules alone (the tests do, through engine/tests/conftest.py).
SWITCH = "CREDIBLE_RECS_QUERY_MODEL"

# Words that name no kind of product: a request made only of them is still vague. Category and place words count
# too (11 Oct 2026): a "kitchen gadget" or "hair products" says where or what for, not what.
NO_PRODUCT_WORDS = frozenset({
    "product", "products", "thing", "things", "stuff", "item", "items", "gift", "gifts", "present", "presents",
    "something", "gadget", "gadgets", "tool", "tools", "set", "one", "kit", "essentials", "routine",
    "kitchen", "kitchenware", "cookware", "cooking", "baking", "appliance", "appliances", "equipment", "gear",
    "accessory", "accessories", "utensil", "utensils", "skincare", "skin", "face", "beauty", "haircare", "hair", "care",
    # The general category's departments and places (14 Oct 2026): "tech stuff", "home gear", "baby things"; and
    # animals, which aren't products ("something for my dog").
    "tech", "electronics", "home", "house", "garden", "outdoor", "outdoors", "camping", "travel", "clothes",
    "clothing", "fashion", "baby", "babies", "kids", "pet", "pets", "dog", "dogs", "cat", "cats", "puppy", "kitten",
    "fitness", "gym", "sport", "sports", "hobby", "hobbies", "diy", "office", "bedroom", "bathroom", "garage",
    # A present's words (18 Oct 2026, the ws-names builder): a "stocking filler" or a "secret santa" says it is a gift,
    # not what; the gift's question stands (engine.query.GIFT_QUESTION).
    "stocking", "filler", "fillers", "stuffer", "stuffers", "secret", "santa", "christmas", "xmas", "birthday",
    "anniversary",
})
# The model's categories (14 Oct 2026): the three categories, then the general category's departments.
MODEL_CATEGORIES = ("skincare", "haircare", "kitchen") + tuple(GENERAL_DEPARTMENTS)

SYSTEM = (
    "You sort shopping requests. Answer with JSON only, as {\"category\": ..., \"product\": ...}.\n"
    "category: \"skincare\" for products put on the skin (cleansers, creams, serums, sunscreens, lotions); \"haircare\" "
    "for products put on the hair or scalp (shampoos, conditioners, hair masks, oils, curl creams, gels, sprays); "
    "\"kitchen\" for anything used to cook, bake, prepare or serve food and drink, including every kitchen appliance "
    "(pans, pots, knives, kettles, toasters, blenders, mixers, microwaves, dishwashers, fridges, coffee and tea gear); "
    "for any other product people buy and use, its department: \"home\" (furniture, bedding, cleaning, laundry, "
    "heating, lighting, smart home), \"tech\" (computers, phones, audio, TVs, cameras, gaming), \"outdoor\" (camping, "
    "hiking, cycling, travel gear and luggage), \"clothing\" (clothes, shoes, bags, watches, accessories), \"baby\" "
    "(baby and kids' gear), \"pets\" (things for pets), \"fitness\" (sport and exercise equipment), \"tools\" (tools, "
    "DIY and garden), \"beauty\" (make-up, perfume, hair dryers and straighteners, shaving, toothbrushes), "
    "\"hobbies\" (instruments, board games, crafts, stationery), \"car\" (cars and car accessories); \"other\" for "
    "anything that isn't a product to buy and use (a service, a place, advice, food or drink, a medicine, a book, film, "
    "game or app); \"unclear\" when the request doesn't say what kind of product it wants.\n"
    "product: the kind of product asked for, copied from the request in its own words, singular, without brands or "
    "describing words (\"air fryer\", \"rice cooker\", \"body lotion\"); \"\" when unclear."
)
# The 14 Oct 2026 examples: a laptop is a tech product now (it was "other"), and a service is "other".
EXAMPLES = (
    ("air fryer that lasts", {"category": "kitchen", "product": "air fryer"}),
    ("best toaster for a small kitchen", {"category": "kitchen", "product": "toaster"}),
    ("something nice for my mum", {"category": "unclear", "product": ""}),
    ("best gaming laptop under 800", {"category": "tech", "product": "laptop"}),
    ("a good plumber near me", {"category": "other", "product": ""}),
    ("body lotion for eczema", {"category": "skincare", "product": "body lotion"}),
    ("curl cream for 3a curls", {"category": "haircare", "product": "curl cream"}),
    ("eyelash curler that doesn't pinch", {"category": "beauty", "product": "eyelash curler"}),
)
SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": [*MODEL_CATEGORIES, "other", "unclear"]},
        "product": {"type": "string"},
    },
    "required": ["category", "product"],
}


class QueryModel(Protocol):
    def read(self, text: str) -> object:
        """The model's two fields for a request, as a dict (anything else is ignored)."""
        ...


class LlamaQueryModel:
    """The open model, loaded on first use (a few seconds) and kept; each request then takes a second or two. The web
    server loads it as it starts (load; latency, 12 Oct 2026), so its first visitor doesn't wait for it.

    One request at a time: the web server answers requests in parallel threads, and llama.cpp can't be used by two at
    once, so the others wait their turn (a second or two each).

    Its reading of the same words never changes (temperature 0), so each request's is kept (latency, 13 Oct 2026, the
    last READINGS_KEPT): the server gets ready by answering every product type, "serum" through the model, and a visitor
    asking one of them again doesn't wait for it."""

    READINGS_KEPT = 1_000

    def __init__(self, path: Path = DEFAULT_MODEL_PATH):
        self.path = Path(path)
        self._llm = None
        self._lock = threading.Lock()
        self._readings: OrderedDict[str, object] = OrderedDict()

    def load(self) -> None:
        """Loads the model now, if it isn't loaded yet."""
        with self._lock:
            self._loaded()

    def _loaded(self):
        if self._llm is None:
            from llama_cpp import Llama  # imported here: the rules never need it

            self._llm = Llama(model_path=str(self.path), n_ctx=1024, verbose=False)
        return self._llm

    def read(self, text: str) -> object:
        with self._lock:
            if text in self._readings:
                self._readings.move_to_end(text)
                return copy.deepcopy(self._readings[text])  # a copy: a caller changing it changes nothing kept
        messages = [{"role": "system", "content": SYSTEM}]
        for request, answer in EXAMPLES:
            messages += [{"role": "user", "content": request}, {"role": "assistant", "content": json.dumps(answer)}]
        messages.append({"role": "user", "content": text})
        with self._lock:
            out = self._loaded().create_chat_completion(messages=messages, temperature=0, max_tokens=60,
                                                        response_format={"type": "json_object", "schema": SCHEMA})
        try:
            reading = json.loads(out["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, json.JSONDecodeError):
            reading = None
        with self._lock:
            self._readings[text] = copy.deepcopy(reading)
            while len(self._readings) > self.READINGS_KEPT:
                self._readings.popitem(last=False)
        return reading


def find_default_model() -> QueryModel | None:
    """The model module 1 asks by default: the open model when its file and llama.cpp are on this machine and the
    switch isn't "off"; otherwise None, and the rules work alone. A llama.cpp that is installed but can't load (a
    missing system library raises OSError, not ImportError) counts as missing too."""
    if os.environ.get(SWITCH, "").lower() == "off" or not DEFAULT_MODEL_PATH.is_file():
        return None
    try:
        import llama_cpp  # noqa: F401
    except Exception:
        return None
    return LlamaQueryModel(DEFAULT_MODEL_PATH)


default_query_model = cache(find_default_model)  # found once per run


def routed_by_model(text: str, model: QueryModel):
    """The model's routing for a request the rules couldn't route, checked as the module docstring says; None when its
    answer can't be used (the rules' question then stands)."""
    from engine.query import OUT_OF_SCOPE_MESSAGE, Routing, classify  # here: engine.query imports this module

    try:
        answer = model.read(text)
    except Exception:  # a model that fails must never break an answer: the rules' question stands
        return None
    if not isinstance(answer, dict):
        return None
    category = answer.get("category")
    product = " ".join(re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)*", str(answer.get("product") or "").lower()))
    if category == "other":
        return Routing("out_of_scope", message=OUT_OF_SCOPE_MESSAGE)
    department = category if category in GENERAL_DEPARTMENTS else None
    category = "general" if department else category
    product = _whole_thing(product, text.lower())  # "case" in "ipad case for kids" is the iPad case
    if (category not in THREAD_CATEGORIES or not product or set(product.split()) <= NO_PRODUCT_WORDS | HOLDER_WORDS):
        return None
    if not _in_own_words(product, text.lower()):
        return None  # only the request's own words: never a product the shopper didn't name
    if _not_one_kind(product):
        return None  # "le creuset or staub", "cerave": the rules' question stands
    known = classify(product)
    if known.status == "ok" and (known.category == category or not known.clues):
        return known  # "pan" is the rules' frying pan; "kettle" the kitchen's, whatever the model said
    category, department = _placed(product, category, department)
    if department:
        return Routing("ok", "general", product, GENERAL_DEPARTMENTS[department]["communities"], department=department)
    return Routing("ok", category, product, SUBREDDITS[category])  # "curl cream" isn't the rules' moisturiser


# --- The model's product, by its own words (17 Oct 2026, the ws-names builder; Claude's technical calls, reported to
# Noemi). The 16 Oct review of module 1 found the model placing what the rules can't by its own habits: a mouse mat in
# home, a bike pump, guitar strings and a tyre pressure gauge in tools, a knife block set in tools (the kitchen's
# answers can't count general mentions), a baby food maker in home, a hair toner and sheet masks in general beauty; and
# brands ("cerave") or two products ("le creuset or staub") becoming product types of their own. ---

# Words that only say a thing holds, covers or fits on another: alone they name no product ("a sturdy case": a case for
# what?), so the request is asked about; with what they are for they do ("ipad case", engine.query.accessory_stretches).
HOLDER_WORDS = frozenset({"case", "cases", "cover", "covers", "stand", "stands", "holder", "holders", "mount", "mounts",
                          "sleeve", "sleeves", "strap", "straps", "band", "bands", "lid", "lids", "liner", "liners",
                          "attachment", "attachments", "accessory", "accessories", "part", "parts", "spares", "refill",
                          "refills"})
# Words saying two products are compared or either will do: such an answer is no one kind of product.
_TWO_PRODUCTS = re.compile(r"(?<![a-z0-9'-])(?:or|vs|versus|nor)(?![a-z0-9'-])")
# What makes, keeps or serves food and drink in a kitchen ("baby food maker", "yogurt maker", "wine rack"), after a word
# of food or drink: a kitchen product, whatever department the model chose.
KITCHEN_THING_WORDS = frozenset({
    "maker", "makers", "machine", "machines", "press", "presses", "mill", "mills", "grinder", "grinders", "cooker",
    "cookers", "steamer", "steamers", "dehydrator", "dehydrators", "slicer", "slicers", "cutter", "cutters", "mould",
    "moulds", "mold", "molds", "pan", "pans", "pot", "pots", "tin", "tins", "jar", "jars", "glass", "glasses", "rack",
    "racks", "dispenser", "dispensers", "chiller", "chillers", "cooler", "coolers", "fridge", "fridges", "frother",
    "frothers", "whisk", "whisks", "bowl", "bowls", "warmer", "warmers", "spinner", "spinners", "scoop", "scoops",
    "brewer", "brewers", "infuser", "infusers", "strainer", "strainers", "sieve", "sieves", "decanter", "decanters",
    "aerator", "aerators", "opener", "openers", "shaker", "shakers"})
FOOD_WORDS = ("food", "baby food", "yogurt", "yoghurt", "ice cream", "popcorn", "pasta", "bread", "pizza", "soda",
              "stock", "broth",  # 18 Oct 2026: a stock pot is the kitchen's, not the home's
              "juice", "smoothie", "tortilla", "rice", "egg", "eggs", "sushi", "noodle", "noodles", "dumpling",
              "candy floss", "cotton candy", "waffle", "pancake", "crepe", "jerky", "butter", "cheese", "milk",
              "oat milk", "nut milk", "tofu", "kombucha", "cold brew", "coffee", "tea", "espresso", "soup", "sauce",
              "herb", "herbs", "spice", "spices", "salad", "fruit", "vegetable", "vegetables", "veg", "meat", "fish",
              "burger", "sausage", "chocolate", "beer", "wine", "cocktail", "cocktails", "sparkling water", "chips",
              "fries", "crisps", "nuts", "cake", "cookie", "cookies", "biscuit", "biscuits")
# Something put on the hair or scalp ("hair toner", "scalp serum"): haircare, as the model's own instructions say. Hair
# tools ("hair claw clips", "hair dryer") stay the general category's (Noemi's q29, 14 Oct 2026).
HAIR_FORM_WORDS = frozenset({
    "toner", "toners", "dye", "dyes", "colour", "color", "bleach", "gloss", "glaze", "mask", "masks", "oil", "oils",
    "serum", "serums", "spray", "sprays", "gel", "gels", "mousse", "cream", "creams", "wax", "pomade", "powder",
    "treatment", "treatments", "tonic", "tonics", "rinse", "lotion", "lotions", "butter", "balm", "perm", "shampoo",
    "shampoos", "conditioner", "conditioners", "paste", "clay", "putty", "primer", "elixir", "milk", "water"})
# Something put on the skin that the model named a beauty product ("sheet mask", "hand cream"): skincare. Not when it is
# for nails, lashes, brows, a beard or make-up, or a massage or a shave.
SKIN_FORM_WORDS = frozenset({
    "mask", "masks", "lotion", "lotions", "cream", "creams", "serum", "serums", "mist", "mists", "essence", "essences",
    "toner", "toners", "cleanser", "cleansers", "moisturiser", "moisturisers", "moisturizer", "moisturizers",
    "sunscreen", "sunscreens", "exfoliator", "exfoliators", "exfoliant", "exfoliants", "scrub", "scrubs", "peel",
    "peels", "balm", "balms", "oil", "oils", "wash", "washes", "patch", "patches", "strips", "pads", "gel", "gels"})
NOT_SKIN_WORDS = frozenset({"beard", "nail", "nails", "cuticle", "lash", "lashes", "eyelash", "eyelashes", "brow",
                            "brows", "eyebrow", "eyebrows", "makeup", "make-up", "bb", "cc", "tattoo", "massage",
                            "shaving", "shave", "aftershave", "dog", "cat", "pet", "car", "leather", "wood"})


def _whole_thing(product: str, lowered: str) -> str:
    """The thing the request names when the model answered with only the word for it ("case" for "ipad case for kids"):
    the request's own name of it, a product's name with that word (engine.query.accessory_stretches); else the
    model's product as it was."""
    from engine.query import accessory_stretches  # here: engine.query imports this module

    words = product.split()
    if not words or not set(words) <= HOLDER_WORDS | _accessory_words():
        return product
    for start, end in accessory_stretches(lowered):
        stretch = " ".join(re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)*", lowered[start:end]))
        if stretch.split()[-len(words):] == words or stretch.split()[-1].rstrip("s") == words[-1].rstrip("s"):
            return stretch
    return product


@cache
def _accessory_words() -> frozenset[str]:
    """engine.query's ACCESSORY_WORDS, read once (engine.query imports this module)."""
    from engine.query import ACCESSORY_WORDS

    return frozenset(ACCESSORY_WORDS)


def _not_one_kind(product: str) -> bool:
    """Whether the model's product is no one kind of product: two compared ("le creuset or staub") or a brand alone
    ("cerave": data/brand_lines.json's brands, config.MAKER_SPELLINGS and the shipped short names' full names)."""
    return bool(_TWO_PRODUCTS.search(product)) or tuple(_plain_words(product)) in brand_names()


def _plain_words(name: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", name.lower().replace("'", "").replace("’", ""))


@cache
def brand_names() -> frozenset[tuple[str, ...]]:
    """Every brand module 1 knows, as its plain words, read once: the brand-lines list's (data/brand_lines.json),
    config.MAKER_SPELLINGS and the shipped short names' full names of up to three words."""
    import json

    from engine.config import MAKER_SPELLINGS

    names = [name for spellings in MAKER_SPELLINGS.values() for name in spellings]
    try:
        from engine.brand_lines import load_brand_lines

        names += [line.brand for line in load_brand_lines()]
    except Exception:  # no brand-lines list here: the other lists still say
        pass
    try:
        aliases = json.loads((REPO_ROOT / "engine" / "data" / "product_aliases.json").read_text(encoding="utf-8"))
        names += [entry["full"] for entries in aliases.get("products", {}).values() for entry in entries
                  if len(entry["full"].split()) <= 3]
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return frozenset(tuple(_plain_words(name)) for name in names if _plain_words(name))


def _placed(product: str, category: str, department: str | None) -> tuple[str, str | None]:
    """(category, department) of a product the model named, by its own words, else the model's:
    1. a thing made for a product goes where that product is: the product's name starts it, and its last word names no
       product of its own ("mouse mat" with the mouse in tech, "tyre pressure gauge" with the tyres in car, "knife
       block set" with the chef knife in the kitchen); never "cpu cooler", "bench grinder" or "carpet shampoo", whose
       last word is another product the model's words set aside;
    2. what makes, keeps or serves food or drink is the kitchen's ("baby food maker"; since 18 Oct 2026 also the two
       written as one word, "stockpot");
    3. what is put on the hair or scalp is haircare ("hair toner");
    4. what is put on the skin, named a beauty product, is skincare ("sheet mask")."""
    from engine.query import _find_matches  # here: engine.query imports this module

    words = product.split()
    found = _find_matches(product, strong=True)
    if found and not any(end == len(product) for _, end, _ in found):
        owner = found[0][2]
        return owner.category, owner.department
    before, last = " ".join(words[:-1]), words[-1]
    if last in KITCHEN_THING_WORDS and any(re.search(rf"(?<![a-z]){re.escape(food)}(?![a-z])", before)
                                           for food in FOOD_WORDS):
        return "kitchen", None
    if len(words) == 1 and any(last == food + thing for food in FOOD_WORDS if " " not in food
                               for thing in KITCHEN_THING_WORDS):
        return "kitchen", None  # the two written as one word ("stockpot", 18 Oct 2026)
    if {"hair", "scalp"} & set(words[:-1]) and last in HAIR_FORM_WORDS:
        return "haircare", None
    if department == "beauty" and last in SKIN_FORM_WORDS and not NOT_SKIN_WORDS & set(words[:-1]):
        return "skincare", None
    return category, department


def _in_own_words(product: str, lowered: str) -> bool:
    """Whether the request (lowercase) names the product, a plural aside, somewhere other than strictly inside a stretch
    the rules read as something else (engine.query.set_aside_stretches; 14 Oct 2026, the routing audit). Asked about
    "petty knife" or "hand blender", the model had answered "knife" and "blender", which the rules route as the chef
    knife and the blender: the very types the rules had set those look-alikes aside from. The whole stretch ("hand
    blender", "ipad case") is the request's own words."""
    from engine.query import set_aside_stretches  # here: engine.query imports this module

    found = [(m.start(), m.end()) for m in re.finditer(rf"\b{re.escape(product)}(?:s|es)?\b", lowered)]
    stretches = set_aside_stretches(lowered) if found else []
    return any(not any(s <= start and end <= e and e - s > end - start for s, e in stretches) for start, end in found)
