"""Module 1, query understanding: turns a shopper's need, typed in plain words, into a structured request.

Every request ends in one of three outcomes:
- "ok": the need is clear. We know the category, the product type, any constraints (budget, skin type,
  size, SPF, how long it should last, the active ingredients it must contain), what to search for and in which
  subreddits. A request that names an active ingredient but no product type ("salicylic acid for acne") is
  ingredient-led (13 Oct 2026, engine/ingredients.py): its product type is the ingredient's own ("salicylic acid
  product"), and its answer may show every type of skincare product that can carry it.
- "clarify": the need is too vague, or holds two needs at once. Instead of guessing, we ask one question.
- "out_of_scope": the product isn't skincare, haircare or kitchen gear. We say so politely.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from engine.config import CONDITION_PRODUCT_TYPES, CONDITION_SUBREDDITS, INGREDIENTS, SUBREDDITS, THREAD_CATEGORIES
from engine.ingredients import (
    TYPE_OWN_INGREDIENT, blanked, find_ingredients, forms_named, ingredient_type_name, ingredients_of_type,
)
from engine.ingredients import shown as shown_ingredients
from engine.models import Record
from engine.text import one_edit_apart

SKIN_TYPES = ("dry", "oily", "combination", "sensitive", "acne-prone", "normal", "mature")
SIZE_UNITS = ("ml", "l", "fl oz", "qt", "in", "cm", "mm")


class Budget(Record):
    min: float | None = Field(default=None, ge=0)
    max: float | None = Field(default=None, ge=0)
    currency: Literal["GBP", "EUR", "USD"] | None = None  # None when the shopper didn't say: never guessed

    @model_validator(mode="after")
    def _has_a_sensible_limit(self) -> "Budget":
        if self.min is None and self.max is None:
            raise ValueError("a budget needs a min, a max or both")
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError(f"budget min {self.min} is above max {self.max}")
        return self


class Size(Record):
    value: float = Field(gt=0)
    unit: Literal[SIZE_UNITS]


class Constraints(Record):
    budget: Budget | None = None
    skin_types: list[Literal[SKIN_TYPES]] = []
    size: Size | None = None
    spf: int | None = Field(default=None, ge=1, le=100)
    min_years: int | None = Field(default=None, ge=1)  # "a kettle that lasts 10+ years"
    must_haves: list[str] = []  # free text, e.g. "fragrance-free", "plastic-free"
    # The active ingredients every product shown must contain (13 Oct 2026; keys of config.INGREDIENTS), such as
    # "salicylic acid". Noemi's call of 7 Oct 2026 (q04) kept a named ingredient apart from the product type; it is
    # kept in this list of its own since 13 Oct 2026, a hard requirement checked against facts and names
    # (engine/pipeline.py).
    ingredients: list[str] = []
    # The forms an ingredient-led request names next to its ingredient ("salicylic acid wash": cleanser; Noemi's
    # decision 1 of 13 Oct 2026, engine.ingredients.forms_named): its answer shows those forms only. Empty for any
    # other request: an ingredient-led one naming none shows leave-on forms only, a typed one its type.
    forms: list[str] = []

    @model_validator(mode="after")
    def _known_ingredients(self) -> "Constraints":
        unknown = [i for i in self.ingredients if i not in INGREDIENTS]
        if unknown:
            raise ValueError(f"unknown ingredients: {', '.join(unknown)} (config.INGREDIENTS)")
        return self


class ParsedQuery(Record):
    text: str  # the request exactly as typed
    status: Literal["ok", "clarify", "out_of_scope"]
    category: Literal[THREAD_CATEGORIES] | None = None
    product_type: str | None = None  # e.g. "exfoliant", "electric kettle"
    constraints: Constraints = Constraints()
    search_terms: list[str] = []
    subreddits: list[str] = []
    question: str | None = None  # the one clarifying question, when status is "clarify"
    message: str | None = None  # the polite no, when status is "out_of_scope"
    # True when the request names active ingredients and no product type (13 Oct 2026): product_type is then the
    # ingredients' own (engine.ingredients.ingredient_type_name), and its answer may show any type that carries them.
    ingredient_led: bool = False

    @model_validator(mode="after")
    def _fits_its_outcome(self) -> "ParsedQuery":
        if self.status == "ok":
            missing = [f for f in ("category", "product_type", "search_terms", "subreddits") if not getattr(self, f)]
            if missing:
                raise ValueError(f"a clear request needs: {', '.join(missing)}")
            outside = [s for s in self.subreddits if s not in SUBREDDITS[self.category]]
            if outside:
                raise ValueError(f"subreddits {', '.join(outside)} are not {self.category} subreddits")
        elif self.status == "clarify" and not self.question:
            raise ValueError("a clarify outcome needs the question to ask")
        elif self.status == "out_of_scope":
            if not self.message:
                raise ValueError("an out-of-scope outcome needs a polite message")
            if self.category:
                raise ValueError("an out-of-scope request has no category")
        return self


# --- Routing: which outcome, which category, which product (rules only, no AI) ---

@dataclass(frozen=True)
class ProductType:
    name: str
    category: str
    keywords: tuple[str, ...]  # product names: "cleanser", "chef's knife"
    hints: tuple[str, ...] = ()  # weaker clues used only when no product name appears: "bha", "spf"
    subreddits: tuple[str, ...] = ()  # most specific first; empty means all of the category's subreddits


PRODUCT_TYPES = (
    ProductType("exfoliant", "skincare", ("exfoliant", "exfoliator", "exfoliating", "exfoliate", "peeling solution", "peel"),
                ("aha", "bha", "pha", "salicylic", "glycolic", "lactic acid", "mandelic")),
    ProductType("cleanser", "skincare", ("cleanser", "face wash", "facial wash", "cleansing oil", "cleansing balm", "micellar",
                                         "makeup remover", "make-up remover")),
    ProductType("moisturiser", "skincare", ("moisturiser", "moisturizer", "moisturising cream", "moisturizing cream", "face cream", "night cream", "day cream"),
                ("lotion", "cream")),
    ProductType("sunscreen", "skincare", ("sunscreen", "sun screen", "suncream", "sun cream", "sunblock"), ("spf", "uv", "sun")),
    ProductType("retinoid", "skincare", ("retinol", "retinoid", "retinal", "tretinoin", "adapalene")),
    ProductType("serum", "skincare", ("vitamin c serum", "niacinamide serum"), ("serum", "vitamin c", "niacinamide")),
    ProductType("toner", "skincare", ("toner", "essence")),
    ProductType("eye cream", "skincare", ("eye cream", "under eye", "under-eye", "eye serum")),
    ProductType("lip balm", "skincare", ("lip balm", "lip mask", "chapstick")),
    # Noemi's decision 2 of 13 Oct 2026: spot treatments, pimple and acne patches (hydrocolloid ones too) are a type of
    # their own, a leave-on form an ingredient-led answer may show. A plain hydrocolloid bandage or plaster, and a
    # "dark spot" product (for marks, not spots), aren't one (LOOKALIKES below).
    # Words match with a plural "s" ("pimple stickers"); a patch's plural is written out ("pimple patches").
    ProductType("spot treatment", "skincare",
                ("spot treatment", "spot gel", "spot cream", "pimple sticker", "acne sticker", "zit sticker",
                 "spot sticker", "pimple dot", "acne dot")
                + tuple(f"{kind} {patch}" for kind in ("pimple", "acne", "spot", "zit", "blemish", "hydrocolloid")
                        for patch in ("patch", "patches")),
                ("hydrocolloid",)),
    # "tea kettle" is people's usual name for a stovetop one, unless it says electric (12 Oct 2026: threads titled "tea
    # kettle" had never been read for a stovetop request).
    ProductType("stovetop kettle", "kitchen", ("stovetop kettle", "stove top kettle", "stove-top kettle", "whistling kettle", "hob kettle",
                                               "tea kettle"),
                subreddits=("BuyItForLife", "tea", "Cooking")),
    ProductType("electric kettle", "kitchen", ("electric kettle", "electric tea kettle", "kettle", "gooseneck"),
                subreddits=("BuyItForLife", "tea", "Coffee")),
    ProductType("chef knife", "kitchen", ("chef knife", "chef's knife", "chefs knife", "kitchen knife", "gyuto", "santoku", "knife", "knives"),
                subreddits=("chefknives", "BuyItForLife", "Cooking")),
    ProductType("cast iron skillet", "kitchen", ("cast iron", "cast-iron", "skillet"), subreddits=("castiron", "BuyItForLife", "Cooking")),
    ProductType("frying pan", "kitchen", ("frying pan", "fry pan", "non-stick pan", "nonstick pan", "stainless steel pan", "carbon steel pan"),
                ("pan",), subreddits=("BuyItForLife", "Cooking", "AskCulinary")),
    ProductType("saucepan", "kitchen", ("saucepan", "sauce pan"), ("pot",), subreddits=("BuyItForLife", "Cooking", "AskCulinary")),
    ProductType("dutch oven", "kitchen", ("dutch oven", "cocotte", "casserole dish"), subreddits=("BuyItForLife", "Cooking", "AskCulinary")),
    ProductType("espresso machine", "kitchen", ("espresso machine", "espresso maker", "coffee machine"), ("espresso",),
                subreddits=("espresso", "Coffee", "BuyItForLife")),
    ProductType("coffee grinder", "kitchen", ("coffee grinder", "burr grinder", "grinder"), subreddits=("Coffee", "espresso")),
    ProductType("teapot", "kitchen", ("teapot", "tea pot"), subreddits=("tea", "BuyItForLife")),
    # Haircare (Noemi, 11 Oct 2026). A longer name wins over a shorter one inside it: "dry shampoo" isn't a shampoo,
    # and a "deep conditioner" is a hair mask.
    ProductType("shampoo", "haircare", ("shampoo", "co-wash", "cowash")),
    ProductType("dry shampoo", "haircare", ("dry shampoo",)),
    ProductType("conditioner", "haircare", ("conditioner",)),
    ProductType("leave-in conditioner", "haircare", ("leave-in conditioner", "leave in conditioner", "leave-in")),
    ProductType("hair mask", "haircare", ("hair mask", "hair masque", "deep conditioner", "deep conditioning mask")),
    ProductType("hair oil", "haircare", ("hair oil", "scalp oil", "hair serum")),
    # Kitchen appliances (Noemi's decision 3 of 14 Oct 2026, after her and a friend's tests of the live site: "microwave"
    # and "oven" returned nothing). The types, their words and their communities were chosen by Claude, reported to her.
    # Seven were the open model's types until then (config.PRECHECK_MODEL_TYPES): the rules now route them without it.
    # A longer name wins, as above: a "toaster oven" isn't a toaster nor an oven, a "rice cooker" isn't a pressure
    # cooker, a "microwave oven" is a microwave. An air fryer oven is a countertop oven, so a toaster oven (the AI had
    # typed 160 mentions so); an Instant Pot or a multicooker is a pressure cooker, a crock pot a slow cooker, a
    # cafetiere a French press, a drip or filter coffee machine a coffee maker (a plain "coffee machine" stays an espresso
    # machine). A range, a gas or electric cooker is only a clue to an oven: "a skillet for my gas range" is a skillet.
    ProductType("microwave", "kitchen", ("microwave", "microwave oven", "combination microwave", "combi microwave",
                                         "microwave air fryer", "air fryer microwave"),
                subreddits=("Appliances", "BuyItForLife", "Cooking")),
    ProductType("oven", "kitchen", ("oven", "wall oven", "built-in oven", "built in oven", "double oven", "single oven",
                                    "range cooker", "range oven", "freestanding cooker", "electric oven", "gas oven",
                                    "fan oven", "steam oven", "convection oven"),
                ("gas range", "electric range", "induction range", "dual fuel range", "gas cooker", "electric cooker"),
                subreddits=("Appliances", "BuyItForLife", "Cooking", "Baking")),
    ProductType("toaster oven", "kitchen", ("toaster oven", "countertop oven", "counter top oven", "benchtop oven",
                                            "mini oven", "air fryer oven", "air fry oven", "air-fryer oven",
                                            "air fryer toaster oven", "toaster oven air fryer", "convection toaster oven",
                                            "countertop convection oven"),
                subreddits=("BuyItForLife", "Appliances", "Cooking")),
    ProductType("air fryer", "kitchen", ("air fryer", "air-fryer", "airfryer"),
                subreddits=("airfryer", "BuyItForLife", "Cooking")),
    ProductType("blender", "kitchen", ("blender", "countertop blender", "high-speed blender", "high speed blender",
                                       "personal blender", "bullet blender", "smoothie blender", "smoothie maker"),
                subreddits=("BuyItForLife", "Cooking", "AskCulinary")),
    ProductType("food processor", "kitchen", ("food processor", "food-processor", "mini chopper", "food chopper"),
                subreddits=("BuyItForLife", "Cooking", "AskCulinary")),
    ProductType("stand mixer", "kitchen", ("stand mixer", "stand-mixer", "standmixer", "kitchen mixer", "bowl-lift mixer",
                                           "bowl lift mixer", "tilt-head mixer", "tilt head mixer", "planetary mixer",
                                           "kitchenaid mixer", "kitchen aid mixer", "dough mixer"),
                subreddits=("Baking", "BuyItForLife", "Cooking")),
    ProductType("hand mixer", "kitchen", ("hand mixer", "handheld mixer", "hand-held mixer", "electric whisk"),
                subreddits=("Baking", "BuyItForLife", "Cooking")),
    ProductType("slow cooker", "kitchen", ("slow cooker", "slow-cooker", "crock pot", "crock-pot", "crockpot"),
                subreddits=("slowcooking", "BuyItForLife", "Cooking")),
    ProductType("rice cooker", "kitchen", ("rice cooker", "rice-cooker", "ricecooker", "rice maker"),
                subreddits=("BuyItForLife", "Cooking", "AskCulinary")),
    ProductType("pressure cooker", "kitchen", ("pressure cooker", "pressure-cooker", "multicooker", "multi-cooker",
                                               "multi cooker", "instant pot", "instant-pot", "instantpot", "instapot"),
                subreddits=("instantpot", "BuyItForLife", "Cooking")),
    ProductType("coffee maker", "kitchen", ("coffee maker", "coffeemaker", "coffee-maker", "drip coffee machine",
                                            "filter coffee machine", "drip machine", "drip brewer", "batch brewer",
                                            "coffee brewer"),
                subreddits=("Coffee", "BuyItForLife")),
    ProductType("french press", "kitchen", ("french press", "cafetiere", "cafetière", "coffee press", "press pot"),
                subreddits=("Coffee", "BuyItForLife")),
    ProductType("toaster", "kitchen", ("toaster",), subreddits=("BuyItForLife", "Appliances", "Cooking")),
    ProductType("waffle maker", "kitchen", ("waffle maker", "waffle iron", "waffle machine"),
                subreddits=("BuyItForLife", "Cooking", "Baking")),
    ProductType("juicer", "kitchen", ("juicer", "juice extractor", "juicing machine", "citrus press"),
                subreddits=("juicing", "BuyItForLife", "Cooking")),
    ProductType("kitchen scale", "kitchen", ("kitchen scale", "food scale", "baking scale", "coffee scale",
                                             "cooking scale", "digital scale", "weighing scale"),
                subreddits=("Baking", "Coffee", "BuyItForLife", "Cooking")),
)

# The short words people put in Reddit post titles for each product, used to find threads.
# A product not listed is searched by its own name.
TITLE_WORDS = {
    "exfoliant": ("exfoliant",),
    "cleanser": ("cleanser",),
    "moisturiser": ("moisturizer", "moisturiser"),
    "sunscreen": ("sunscreen",),
    "retinoid": ("retinol", "tretinoin"),
    "serum": ("serum",),
    "toner": ("toner",),
    "spot treatment": ("spot treatment", "pimple patch", "acne patch"),
    "stovetop kettle": ("kettle",),
    "electric kettle": ("kettle",),
    "chef knife": ("knife",),
    "cast iron skillet": ("cast iron", "skillet"),
    "frying pan": ("pan",),
    "coffee grinder": ("grinder",),
    "teapot": ("teapot", "tea pot"),
    "shampoo": ("shampoo",),
    "conditioner": ("conditioner",),
    "leave-in conditioner": ("leave-in", "leave in"),
    "hair mask": ("hair mask", "deep conditioner"),
    # Kitchen appliances (14 Oct 2026).
    "microwave": ("microwave",),
    "oven": ("oven", "range cooker"),
    "toaster oven": ("toaster oven", "countertop oven"),
    "air fryer": ("air fryer", "airfryer"),
    "blender": ("blender",),
    "food processor": ("food processor",),
    "stand mixer": ("stand mixer", "mixer"),
    "hand mixer": ("hand mixer",),
    "slow cooker": ("slow cooker", "crock pot", "crockpot"),
    "rice cooker": ("rice cooker",),
    "pressure cooker": ("pressure cooker", "instant pot", "multicooker"),
    "coffee maker": ("coffee maker", "drip"),
    "french press": ("french press",),
    "toaster": ("toaster",),
    "waffle maker": ("waffle maker", "waffle iron"),
    "juicer": ("juicer",),
    "kitchen scale": ("scale",),
}

# Things people shop for that this version doesn't cover. "-free" and "-safe" forms are requirements, not products.
# Shampoo and conditioner moved into haircare on 11 Oct 2026; hair tools stay out. A bathroom scale isn't a kitchen
# scale (14 Oct 2026). The dishwasher stays out, as Noemi's approved module 1 case q30 says (her call of 7 Oct 2026:
# large appliances aren't kitchen gear), although her decision 3 of 14 Oct 2026 brought the microwave and the oven in:
# whether it comes in too is her call (eval/RUNS.md, 14 Oct 2026).
OUT_OF_SCOPE = (
    "laptop", "phone", "headphones", "earbuds", "tv", "monitor", "camera", "shoes", "trainers", "sneakers", "boots", "jacket",
    "mattress", "pillow", "vacuum", "hair dryer", "hairdryer", "straightener", "curling iron", "curling wand", "makeup",
    "make-up", "foundation", "mascara", "lipstick", "perfume", "fragrance", "dishwasher", "washing machine", "fridge", "car",
    "bike", "chair", "desk", "watch", "toothbrush", "razor", "bathroom scale",
)
# Out of scope although they hold a product's name: an air conditioner isn't a hair conditioner, and cleaning products
# aren't the appliance they clean (14 Oct 2026; the extraction instructions put them under "other" too).
OUT_OF_SCOPE_LOOKALIKES = ("air conditioner", "air conditioning", "oven cleaner", "microwave cleaner",
                           "dishwasher tablet", "dishwasher pod", "dishwasher detergent", "dishwasher salt",
                           "dishwasher cleaner", "rinse aid")

# Phrases that hold a product's word, or an out-of-scope word, but name something else (11 Oct 2026): "cream" in "ice
# cream maker" isn't a moisturiser, a "crock pot" isn't a saucepan, a "vacuum sealer" isn't a vacuum cleaner. They are
# set aside before products are looked for, so the request is asked about, or placed by the open model
# (engine.query_model), instead of being taken for the product whose word it holds.
# Since 13 Oct 2026 also the other kinds of knife: "knife" alone is a chef's knife, as people mean it in "a good knife",
# but a paring or a bread knife isn't one (b07's Tojiro line had counted a writer's paring knives). Each with its
# plural, which isn't the name and an "s".
_OTHER_KNIVES = ("paring", "bread", "steak", "utility", "boning", "fillet", "filet", "carving", "butter", "pocket",
                 "cheese", "oyster", "tomato", "petty")
# 14 Oct 2026 (kitchen appliances, Noemi's decision 3): a blender held in the hand (config.OTHER_KIND_WORDS) isn't a
# blender, and a beauty or makeup blender is a sponge. A crock pot and an Instant Pot are no longer look-alikes: they
# name a slow cooker and a pressure cooker.
_OTHER_BLENDERS = ("immersion", "stick", "hand", "handheld", "hand-held", "beauty", "makeup", "make-up")
# Where an oven, a microwave or a dishwasher is only the place something goes ("a pan to put in the oven", "oven-safe",
# "dishwasher-safe"), or what goes with it ("oven gloves", "microwave popcorn", "toaster bags"). Never "for a" or "in an":
# "looking for a microwave" and "what to look for in an oven" ask for one.
_PLACES = tuple(f"{word} {the} {appliance}" for word in ("in", "into", "inside", "to", "from")
                for the in ("the", "my", "your") for appliance in ("oven", "microwave", "dishwasher"))
LOOKALIKES = (
    "ice cream", "coffee pot", "sheet pan", "cake pan", "loaf pan", "roasting pan",
    "baking pan", "muffin pan", "bundt pan", "pie pan", "tart pan", "sun hat", "sun lounger", "vacuum sealer",
    "vacuum flask", "vacuum-insulated", "vacuum insulated",
    # 13 Oct 2026: razor bumps and razor burn are skin, not a razor ("salicylic acid for razor bumps").
    "razor bump", "razor burn",
    # 13 Oct 2026 (spot treatments a type): a plain hydrocolloid bandage, plaster or dressing isn't a pimple patch, nor
    # a blister plaster; a dark spot, an age spot or a sun spot is a mark on the skin, not a spot to treat.
    "hydrocolloid bandage", "hydrocolloid plaster", "hydrocolloid dressing", "blister plaster", "blister patch",
    "dark spot", "age spot", "sun spot",
    # 14 Oct 2026: what goes in, with or on an appliance isn't the appliance; a pizza oven or a toy oven isn't a kitchen
    # oven.
    "out of the oven", "stove to oven", "stovetop to oven", "hob to oven", "oven to table", "oven-to-table",
    "oven safe", "oven-safe", "ovensafe", "oven proof", "oven-proof", "oven mitt", "oven glove", "oven thermometer",
    "oven liner", "oven tray", "oven rack", "oven dish", "oven light", "oven bag", "oven chip", "oven temperature",
    "oven temp", "pizza oven", "easy bake oven",
    "microwave safe", "microwave-safe", "microwave popcorn", "microwave rice", "microwave meal", "microwave dinner",
    "microwave cover", "microwave plate", "microwave bowl", "microwave container",
    "dishwasher safe", "dishwasher-safe", "dishwasher proof", "dishwasher-proof", "through the dishwasher",
    "toaster bag", "toaster pastry", "toaster pastries", "toaster strudel", "toaster waffle",
    "air fryer liner", "air fryer paper", "air fryer recipe", "slow cooker liner", "slow cooker recipe",
    "blender bottle", "blender sponge", "blender brush", "cooker hood",
    # A coffee maker or an espresso machine with a grinder built in is still the machine.
    "built-in grinder", "built in grinder", "integrated grinder", "with a grinder", "with grinder",
) + _PLACES + tuple(f"{kind} {knife}" for kind in _OTHER_KNIVES for knife in ("knife", "knives")) + tuple(
    f"{kind} blender" for kind in _OTHER_BLENDERS)

# Words that place a vague request in a category, so the question can be more specific.
CATEGORY_HINTS = {
    "skincare": ("skin", "face", "acne", "wrinkles", "pores", "skincare", "complexion"),
    "kitchen": ("kitchen", "cooking", "cook", "coffee", "tea", "baking", "cookware"),
    "haircare": ("hair", "scalp", "curl", "curly", "frizz", "frizzy", "dandruff", "haircare"),
}

EXAMPLES = {"skincare": "a cleanser, a moisturiser or a sunscreen", "kitchen": "a kettle, a chef's knife or a pan",
            "haircare": "a shampoo, a conditioner or a hair mask"}


@dataclass(frozen=True)
class Routing:
    status: str
    category: str | None = None
    product_type: str | None = None
    subreddits: tuple[str, ...] = ()
    question: str | None = None
    message: str | None = None
    several: bool = False  # a question because the request names two products: the open model is never asked
    clues: tuple[str, ...] = ()  # the clue words that alone placed the product ("pot"), when no product name did


OUT_OF_SCOPE_MESSAGE = "Sorry, I only cover skincare, haircare and kitchen gear for now, so I can't recommend that one."


def classify(text: str) -> Routing:
    """Decides the outcome. Ambiguity becomes a question, never a guess."""
    lowered = text.lower()
    if _mentions_any(lowered, OUT_OF_SCOPE_LOOKALIKES):
        return Routing("out_of_scope", message=OUT_OF_SCOPE_MESSAGE)
    lowered = _set_aside(lowered, LOOKALIKES)
    named = _find_products(lowered, strong=True)
    found = named or _clues_that_fit(_find_products(lowered, strong=False), lowered)
    names = list(dict.fromkeys(p.name for p in found))

    if len(names) > 1:
        return Routing("clarify", question=f"I look for one thing at a time: shall I start with the {names[0]} or the {names[1]}?",
                       several=True)
    if names:
        product = next(p for p in found if p.name == names[0])
        clues = () if named else tuple(h for h in product.hints if _mentions_any(lowered, (h,)))
        return Routing("ok", product.category, product.name, product.subreddits or SUBREDDITS[product.category],
                       clues=clues)
    if _mentions_any(lowered, OUT_OF_SCOPE, skip_requirements=True):
        return Routing("out_of_scope", message=OUT_OF_SCOPE_MESSAGE)
    for category, hints in CATEGORY_HINTS.items():
        if _mentions_any(lowered, hints):
            return Routing("clarify", category, question=f"What kind of {category} product are you after? For example {EXAMPLES[category]}?")
    return Routing("clarify", question="What kind of product are you looking for? For example a cleanser, a shampoo, a kettle or a chef's knife?")


def _set_aside(lowered: str, phrases: tuple[str, ...]) -> str:
    """The text with every one of these phrases blanked out (same length, so positions don't move). A phrase that starts
    inside a product's name found before it stays (14 Oct 2026): "oven safe" in "a dutch oven safe to 260c" is part of
    the Dutch oven's name, which is what the request asks for."""
    named = [(m.start(), m.end()) for product in PRODUCT_TYPES for keyword in product.keywords
             for m in re.finditer(rf"\b{re.escape(keyword)}s?\b", lowered)]

    def blank(m: re.Match) -> str:
        inside = any(start < m.start() < end for start, end in named)
        return m.group(0) if inside else " " * len(m.group(0))

    for phrase in phrases:
        lowered = re.sub(rf"\b{re.escape(phrase)}s?\b", blank, lowered)
    return lowered


def _clues_that_fit(found: list[ProductType], lowered: str) -> list[ProductType]:
    """Products found by a clue word alone, less the skincare ones in a request about hair (11 Oct 2026): "cream" in
    "curl cream for curly hair" is a styling product, not a moisturiser. The request is then asked about, or placed by
    the open model."""
    if not _mentions_any(lowered, CATEGORY_HINTS["haircare"]):
        return found
    return [p for p in found if p.category != "skincare"]


def _find_products(lowered: str, strong: bool) -> list[ProductType]:
    """Products named in the text. A phrase inside a longer match doesn't count: "kettle" in "stovetop kettle"."""
    matches = []  # (start, end, product)
    for product in PRODUCT_TYPES:
        for keyword in product.keywords if strong else product.hints:
            for m in re.finditer(rf"\b{re.escape(keyword)}s?\b", lowered):
                matches.append((m.start(), m.end(), product))
    kept = [
        (start, end, product) for start, end, product in matches
        if not any(s <= start and end <= e and (e - s) > (end - start) for s, e, _ in matches)
    ]
    return [product for _, _, product in sorted(kept, key=lambda match: match[0])]


def _mentions_any(lowered: str, words: tuple[str, ...], skip_requirements: bool = False) -> bool:
    for word in words:
        for m in re.finditer(rf"\b{re.escape(word)}s?\b", lowered):
            if skip_requirements and re.match(r"[- ]?(free|safe)\b", lowered[m.end():]):
                continue
            return True
    return False


# --- Requirements and search terms ---

# Stated requirements, written the way shoppers type them, mapped to one short name each.
MUST_HAVES = {
    "fragrance-free": (r"fragrance[- ]free", r"unscented", r"(no|without) (added )?fragrance", r"perfume[- ]free"),
    "non-comedogenic": (r"non[- ]?comedogenic", r"(won't|doesn't|does not|will not) clog pores"),
    "no white cast": (r"(no|without a?) white cast",),
    "cruelty-free": (r"cruelty[- ]free",),
    "vegan": (r"vegan",),
    "reef-safe": (r"reef[- ]safe",),
    "plastic-free": (r"plastic[- ]free", r"(no|without) plastic"),
    "stainless steel": (r"stainless( steel)?",),
    "dishwasher-safe": (r"dishwasher[- ]safe",),
    "induction-compatible": (r"induction",),
    "temperature control": (r"(variable )?temp(erature)? control", r"variable temperature"),
}


def find_must_haves(text: str) -> list[str]:
    """Requirements in the order they appear, each named once."""
    lowered = text.lower()
    found = []  # (position, name)
    for name, patterns in MUST_HAVES.items():
        positions = [m.start() for pattern in patterns for m in re.finditer(rf"\b{pattern}\b", lowered)]
        if positions:
            found.append((min(positions), name))
    return [name for _, name in sorted(found)]


def search_terms(product_type: str, constraints: Constraints) -> list[str]:
    """What to search for, most specific first. Each search costs credits, so at most three. An ingredient-led request
    is searched by its ingredients' names ("salicylic acid"), a typed one with an ingredient by both ("salicylic acid
    cleanser") first (13 Oct 2026)."""
    led = ingredients_of_type(product_type)
    if led:
        product_type = shown_ingredients(led)
    terms = []
    if constraints.ingredients and not led:
        terms.append(f"{shown_ingredients(constraints.ingredients)} {product_type}")
    if constraints.skin_types:
        terms.append(f"{product_type} for {' '.join(constraints.skin_types)} skin")
    if constraints.must_haves:
        terms.append(f"{constraints.must_haves[0]} {product_type}")
    if constraints.min_years:
        terms.append(f"{product_type} that lasts")
    terms.append(product_type)
    return terms[:2] + terms[-1:] if len(terms) > 3 else terms


# --- The whole of module 1 ---

# Real words one letter away from a product or skin-type word: never "corrected" into it. Since 14 Oct 2026 (kitchen
# appliances) also "cooked" and "cooler" ("cooker"), "toasted" ("toaster"), "blended" and "bender" ("blender"), "juices",
# "juiced" and "juicier" ("juicer"), "microwaved" ("microwave").
_REAL_WORDS = {"cleaner", "cleaners", "cooked", "cooler", "coolers", "toasted", "blended", "bender", "juices", "juiced",
               "juicier", "microwaved"}


def correct_typos(text: str) -> str:
    """Fixes one wrong letter in a long product or skin-type word ("clenser" -> "cleanser", "sensitve" ->
    "sensitive"). Only when the word keeps its first letter (typos rarely change it: "settle" isn't "kettle"),
    the fix is unambiguous, and the word isn't a real word of its own ("cleaner")."""
    vocabulary = {w for p in PRODUCT_TYPES for k in p.keywords + p.hints for w in k.split() if len(w) >= 6}
    vocabulary |= {w for words in TITLE_WORDS.values() for t in words for w in t.split() if len(w) >= 6}
    vocabulary |= {s for s in SKIN_TYPES if len(s) >= 6 and "-" not in s}
    # The active ingredients' words too (13 Oct 2026): "azeliac" is azelaic.
    vocabulary |= {w for entry in INGREDIENTS.values() for pattern in entry["asked"]
                   for w in re.findall(r"[a-z]+", pattern) if len(w) >= 6}

    def fix(match: re.Match) -> str:
        word = match.group(0)
        lowered = word.lower()
        if len(lowered) < 5 or lowered in vocabulary or lowered in _REAL_WORDS:
            return word
        candidates = {v for v in vocabulary if v[0] == lowered[0] and one_edit_apart(lowered, v)}
        return candidates.pop() if len(candidates) == 1 else word

    return re.sub(r"[A-Za-z]+", fix, text)


_DEFAULT = object()  # parse_query's model: the open model when this machine has it (engine.query_model)


def parse_query(text: str, model=_DEFAULT) -> ParsedQuery:
    """Turns a request typed in plain words into an understood request: rules first, at no cost; when they find no
    product type, a free open model's second opinion, checked by code (engine.query_model; Noemi, 11 Oct 2026).
    `model`: the model to ask (None: the rules alone); by default the one engine.query_model finds on this machine."""
    # Imported here because query_rules builds on this file's shapes (Budget, Size).
    from engine.query_model import default_query_model, routed_by_model
    from engine.query_rules import parse_budget, parse_min_years, parse_size, parse_skin_types, parse_spf

    original, text = text, correct_typos(text)
    found = find_ingredients(text)
    routing, led = _with_ingredients(text, classify(text), found)
    model = default_query_model() if model is _DEFAULT else model
    if led or model is None:
        pass  # an ingredient-led request is placed by the rules: the open model is never asked about it
    elif routing.status == "clarify" and not routing.several:
        routing = routed_by_model(text, model) or routing
    elif routing.status == "ok" and routing.clues:
        routing = _second_opinion(text, routing, model)
    if routing.status == "out_of_scope":
        return ParsedQuery(text=original, status="out_of_scope", message=routing.message)
    ingredients = [f.ingredient for f in found if TYPE_OWN_INGREDIENT.get(routing.product_type or "") != f.ingredient]

    constraints = Constraints(
        budget=parse_budget(text),
        skin_types=parse_skin_types(text),
        size=parse_size(text),
        spf=parse_spf(text),
        min_years=parse_min_years(text),
        must_haves=find_must_haves(text),
        ingredients=ingredients,
        forms=forms_named(text, found) if led else [],
    )
    if routing.status == "clarify":
        # Kept so that, once the shopper answers, what they already said isn't lost.
        return ParsedQuery(text=original, status="clarify", category=routing.category, constraints=constraints, question=routing.question)
    return ParsedQuery(
        text=original,
        status="ok",
        category=routing.category,
        product_type=routing.product_type,
        constraints=constraints,
        search_terms=search_terms(routing.product_type, constraints),
        subreddits=_condition_subreddits(routing.subreddits, constraints.skin_types, routing.product_type),
        ingredient_led=led,
    )


def _with_ingredients(text: str, routing: Routing, found: list) -> tuple[Routing, bool]:
    """The routing of a request that names active ingredients (13 Oct 2026), and whether it is ingredient-led.

    A product type named by its own name ("salicylic acid cleanser", "vitamin c serum", "retinol") stays. When the
    type came only from clue words, or none was found, the rest of the request is read without the ingredients' words
    (engine.ingredients.blanked): a product it names stays ("lactic acid lotion" is a moisturiser, though "lactic acid"
    alone is an exfoliant's clue), something out of scope stays out ("makeup with niacinamide"), a question about
    another category stays a question ("salicylic acid for my scalp"); otherwise the ingredients alone are what is asked
    for, and the request is ingredient-led, in skincare ("salicylic acid for acne")."""
    if not found or (routing.status == "ok" and not routing.clues):
        return routing, False
    rest = classify(blanked(text, found))
    if rest.status in ("ok", "out_of_scope") or rest.several or rest.category not in (None, "skincare"):
        return rest, False
    keys = [f.ingredient for f in found]
    return Routing("ok", "skincare", ingredient_type_name(keys), SUBREDDITS["skincare"]), True


def _second_opinion(text: str, routing: Routing, model) -> Routing:
    """For a request the rules placed by a clue word alone ("pot"): the open model's reading when it names another
    product, in the request's own words and without that clue word ("rice cooker with a non-stick pot" is a rice
    cooker, the pot a part of it; 11 Oct 2026). Otherwise, or when the model is unsure, the rules' routing stands."""
    from engine.query_model import routed_by_model

    other = routed_by_model(text, model)
    if other is None or other.status != "ok" or other.product_type == routing.product_type:
        return routing
    if any(_mentions_any(other.product_type, (clue,)) for clue in routing.clues):
        return routing  # "stainless pot" is the rules' saucepan
    return other


def _condition_subreddits(subreddits: Iterable[str], skin_types: Iterable[str],
                          product_type: str | None = None) -> list[str]:
    """The request's subreddits, with a skin condition's own subreddit (config.CONDITION_SUBREDDITS: r/acne) first when
    the request is about that condition, or for a product made for it (config.CONDITION_PRODUCT_TYPES: spot
    treatments, 13 Oct 2026), and left out otherwise."""
    general = [s for s in subreddits if s not in CONDITION_SUBREDDITS]
    own = [s for s in subreddits if CONDITION_SUBREDDITS.get(s) in set(skin_types)
           or product_type in CONDITION_PRODUCT_TYPES.get(s, ())]
    return own + general
