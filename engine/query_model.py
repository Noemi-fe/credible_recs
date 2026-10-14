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
    if category not in THREAD_CATEGORIES or not product or set(product.split()) <= NO_PRODUCT_WORDS:
        return None
    if not _in_own_words(product, text.lower()):
        return None  # only the request's own words: never a product the shopper didn't name
    known = classify(product)
    if known.status == "ok" and (known.category == category or not known.clues):
        return known  # "pan" is the rules' frying pan; "kettle" the kitchen's, whatever the model said
    if department:
        return Routing("ok", "general", product, GENERAL_DEPARTMENTS[department]["communities"], department=department)
    return Routing("ok", category, product, SUBREDDITS[category])  # "curl cream" isn't the rules' moisturiser


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
