"""Module 1, query understanding: turns a shopper's need, typed in plain words, into a structured request.

Every request ends in one of three outcomes:
- "ok": the need is clear. We know the category, the product type, any constraints (budget, skin type,
  size, SPF, how long it should last, the active ingredients it must contain), what to search for and in which
  subreddits. A request that names an active ingredient but no product type ("salicylic acid for acne") is
  ingredient-led (13 Oct 2026, engine/ingredients.py): its product type is the ingredient's own ("salicylic acid
  product"), and its answer may show every type of skincare product that can carry it.
- "clarify": the need is too vague, or holds two needs at once. Instead of guessing, we ask one question.
- "out_of_scope": the request isn't for a product we recommend: a service, a place or advice that isn't about buying
  something; food or drink; a medicine or a supplement; a book, a film, music, a game or an app; a weapon, drugs,
  tobacco or vaping, or an adult product. We say so politely, in words that say which (14 Oct 2026: until then
  everything outside skincare, haircare and kitchen gear was out of scope; since Noemi's "I want recs regardless of
  the category", any other product people buy and use is in the general category, config.GENERAL_DEPARTMENTS).
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache
from typing import Literal

from pydantic import Field, model_validator

from engine.config import (
    CONDITION_PRODUCT_TYPES, CONDITION_SUBREDDITS, GENERAL_DEPARTMENTS, HARMFUL_KNIVES, INGREDIENTS, MORE_PRODUCT_TYPES,
    PRODUCT_FACTS_BY_TYPE, SUBREDDITS, THREAD_CATEGORIES, TYPE_ASKED_WORDS,
)
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
    # The general category's department (14 Oct 2026; config.GENERAL_DEPARTMENTS: "tech" for headphones), shown on the
    # page; None for the other categories, and for a general product whose department isn't known.
    department: str | None = None

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
        if self.department is not None:
            if self.category != "general":
                raise ValueError(f"only a general request has a department, not a {self.category} one")
            if self.department not in GENERAL_DEPARTMENTS:
                raise ValueError(f"unknown department {self.department!r} (config.GENERAL_DEPARTMENTS)")
        return self


# --- Routing: which outcome, which category, which product (rules only, no AI) ---

@dataclass(frozen=True)
class ProductType:
    name: str
    category: str
    keywords: tuple[str, ...]  # product names: "cleanser", "chef's knife"
    hints: tuple[str, ...] = ()  # weaker clues used only when no product name appears: "bha", "spf"
    subreddits: tuple[str, ...] = ()  # most specific first; empty means all of the category's subreddits
    department: str | None = None  # the general category's department (config.GENERAL_DEPARTMENTS); None otherwise


FIRST_PRODUCT_TYPES = (
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
    # kettle" had never been read for a stovetop request). A kettle for an induction hob, a stove or an Aga, and a cast
    # iron one (a tetsubin), is one too (14 Oct 2026, the routing audit: "kettle for a gas stove" was an electric
    # kettle; "X for my Y" reads as "Y X", engine.query._reversed_name, so "kettle for an aga" is an "aga kettle").
    ProductType("stovetop kettle", "kitchen", ("stovetop kettle", "stove top kettle", "stove-top kettle", "whistling kettle", "hob kettle",
                                               "tea kettle", "induction kettle", "stove kettle", "aga kettle",
                                               "cast iron kettle", "tetsubin"),
                subreddits=("BuyItForLife", "tea", "Cooking")),
    ProductType("electric kettle", "kitchen", ("electric kettle", "electric tea kettle", "kettle", "gooseneck"),
                subreddits=("BuyItForLife", "tea", "Coffee")),
    ProductType("chef knife", "kitchen", ("chef knife", "chef's knife", "chefs knife", "kitchen knife", "gyuto", "santoku", "knife", "knives"),
                subreddits=("chefknives", "BuyItForLife", "Cooking")),
    ProductType("cast iron skillet", "kitchen", ("cast iron", "cast-iron", "skillet"), subreddits=("castiron", "BuyItForLife", "Cooking")),
    # An enamelled cast iron casserole is a Dutch oven, its British name (14 Oct 2026, the routing audit). Not done, on
    # purpose: a "nonstick skillet" (American for a frying pan) is still the cast iron skillet's, since as the frying
    # pan's name it changed what frying pan and cast iron skillet answers read (eval/RUNS.md, 14 Oct 2026).
    ProductType("frying pan", "kitchen", ("frying pan", "fry pan", "non-stick pan", "nonstick pan", "stainless steel pan", "carbon steel pan"),
                ("pan",), subreddits=("BuyItForLife", "Cooking", "AskCulinary")),
    ProductType("saucepan", "kitchen", ("saucepan", "sauce pan"), ("pot",), subreddits=("BuyItForLife", "Cooking", "AskCulinary")),
    ProductType("dutch oven", "kitchen", ("dutch oven", "cocotte", "casserole dish", "cast iron casserole",
                                          "enamelled casserole", "enameled casserole", "enamel casserole",
                                          "casserole pot"),
                subreddits=("BuyItForLife", "Cooking", "AskCulinary")),
    ProductType("espresso machine", "kitchen", ("espresso machine", "espresso maker", "coffee machine"), ("espresso",),
                subreddits=("espresso", "Coffee", "BuyItForLife")),
    # A grinder sold for coffee and spices is a coffee grinder (14 Oct 2026, the routing audit): since a spice grinder
    # is a type of its own, "spice grinder" would otherwise take "coffee/spice grinder" titles from coffee grinder
    # answers.
    ProductType("coffee grinder", "kitchen", ("coffee grinder", "burr grinder", "grinder", "coffee/spice grinder",
                                              "coffee and spice grinder", "spice and coffee grinder"),
                subreddits=("Coffee", "espresso")),
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
                                            "countertop convection oven", "halogen oven"),
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
# Then the types of engine/data/product_types.json (config.MORE_PRODUCT_TYPES; 14 Oct 2026, Noemi's plan part 1): the
# general category's, each in its department, and more kitchen, skincare and haircare ones. A longer name still wins
# over a shorter one inside it: "robot vacuum" isn't a vacuum cleaner, "hiking boots" aren't boots, "dog bed" isn't a
# bed. Names are written as they are typed; hints are weaker clues, as above ("watch", "chair", "fan").
PRODUCT_TYPES = FIRST_PRODUCT_TYPES + tuple(
    ProductType(entry["name"], entry["category"], tuple(entry["keywords"]), tuple(entry.get("hints", ())),
                tuple(entry["subreddits"]), entry.get("department"))
    for entry in MORE_PRODUCT_TYPES
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
# The title words of engine/data/product_types.json's types (14 Oct 2026).
TITLE_WORDS |= {entry["name"]: tuple(entry["title_words"]) for entry in MORE_PRODUCT_TYPES}

# --- What stays out of scope (14 Oct 2026, the general category) ---
# Until 14 Oct 2026 everything outside skincare, haircare and kitchen gear was out of scope (laptops, shoes, a
# dishwasher: Noemi's approved case q30 of 7 Oct 2026). Since her "I want recs regardless of the category" any product
# people buy and use has a type: module 1's own (PRODUCT_TYPES), or one the open model names (engine/query_model.py).
# What stays out, decided by Claude and reported to Noemi, each with its own polite no (wording PROPOSED):
# 1. Weapons, drugs, tobacco and vaping, and adult products (HARMFUL), whatever else the request names: "a knife for
#    self defence" is no chef's knife request. Their look-alikes are set aside first: a glue gun, a massage gun or a
#    weed eater (a string trimmer) is a product.
# 2. Only when the request names no product: health (medicines, supplements, medical devices: advice for a pharmacist
#    or a doctor), food and drink, for people or pets (what is eaten is judged by taste and safety, not by use over
#    years), books, films, music, games and apps (taste, not use), and services, places and advice that isn't about
#    buying something ("a plumber", "a hotel in Rome", "how do I fix my posture").
# Words are matched whole, a plural "s" allowed, lowercase; a phrase in a product's own name never counts ("vitamin c
# serum" is a serum, "food processor" an appliance, "board games" a hobby's product).
HARMFUL = (
    "gun", "guns", "firearm", "rifle", "pistol", "handgun", "shotgun", "revolver", "ammo", "ammunition", "ar-15",
    "ar15", "glock", "taser", "stun gun", "pepper spray", "knuckle duster", "brass knuckles", "switchblade",
    "butterfly knife", "balisong", "flick knife", "throwing knife", "combat knife", "tactical knife", "silencer",
    "suppressor", "explosive", "grenade", "self defense", "self-defense", "self defence", "self-defence", "weapon",
    "weed", "cannabis", "marijuana", "thc", "bong", "dab rig", "dab pen", "herb grinder", "vape", "vape pen",
    "vaporizer", "vaporiser", "e-cigarette", "e-cig", "ecig", "juul", "nicotine", "cigarette", "cigar", "tobacco",
    "rolling papers", "shisha", "hookah", "kratom", "psilocybin", "magic mushrooms", "shrooms", "lsd", "cocaine",
    "mdma", "ketamine", "anabolic steroid", "sarms", "sex toy", "dildo", "vibrator", "fleshlight", "butt plug",
    *HARMFUL_KNIVES,  # the weapon-like knives, Noemi's decision of 15 Oct 2026 (engine/config.py)
)
# Products holding a harmful word, set aside before HARMFUL is looked for.
HARMFUL_LOOKALIKES = (
    "glue gun", "hot glue gun", "nail gun", "heat gun", "massage gun", "spray gun", "paint gun", "water gun",
    "nerf gun", "squirt gun", "bubble gun", "staple gun", "caulk gun", "caulking gun", "grease gun", "soldering gun",
    "foam gun", "label gun", "price gun", "temperature gun", "thermometer gun", "radar gun", "percussion gun",
    "gunmetal", "gun metal", "pistol grip", "weed eater", "weed whacker", "weed wacker", "weed killer", "weed barrier",
    "weed membrane", "weed puller", "weed burner", "cigarette lighter", "cigar box", "dry herb dehydrator",
    "nicotine patch", "nicotine patches", "nicotine gum", "nicotine replacement", "secret weapon", "tobacco vanille",
    "tobacco vanilla", "tobacco oud", "noise suppressor", "rifle paper",
    # 14 Oct 2026, the routing audit: tools and garden products refused as weapons or drugs (HARMFUL gained the
    # weapon-like knives on 15 Oct 2026, Noemi's decision: config.HARMFUL_KNIVES).
    "rivet gun", "riveting gun", "airbrush gun", "tattoo gun", "icing gun", "cookie gun", "hose gun", "grout gun",
    "sealant gun", "silicone gun", "mastic gun", "shotgun mic", "shotgun microphone", "weed control", "weed fabric",
    "weed brush", "weed sprayer", "weed suppressant", "weed suppressing",
)
HEALTH = (
    "medicine", "medication", "meds", "pills", "painkiller", "ibuprofen", "paracetamol", "acetaminophen", "aspirin",
    "antihistamine", "antidepressant", "antibiotic", "viagra", "melatonin", "vitamin", "vitamins", "multivitamin",
    "supplement", "supplements", "probiotic", "fish oil", "omega 3", "omega-3", "creatine", "protein powder",
    "pre-workout", "preworkout", "collagen supplement", "magnesium", "iron tablets", "ashwagandha", "cbd",
    "nicotine patch", "nicotine patches", "nicotine gum", "flea treatment", "wormer", "dewormer", "contraceptive",
    "condom", "hearing aid", "blood pressure monitor", "glucose monitor", "cpap", "inhaler", "contact lens",
    "contact lenses", "cold sore", "hay fever", "allergy tablets", "sleeping pills", "steroid cream",
)
FOOD_AND_DRINK = (
    "food for", "healthy food", "snack", "snacks", "coffee beans", "whole bean coffee", "ground coffee", "instant coffee", "coffee pods",
    "coffee capsules", "nespresso pods", "decaf", "wine", "beer", "whisky", "whiskey", "vodka", "gin", "rum",
    "tequila", "alcohol", "cocktail", "chocolate", "sweets", "candy", "cereal", "olive oil", "cooking oil",
    "hot sauce", "spices", "green tea", "black tea", "herbal tea", "loose leaf tea", "tea bags", "matcha", "oolong",
    "dog food", "cat food", "puppy food", "kitten food", "pet food", "dog treats", "cat treats", "baby food",
    "baby formula", "formula milk", "protein bar", "meal kit", "groceries", "recipe", "recipes",
    # 14 Oct 2026, the routing audit: kettle chips had been an electric kettle, vanilla essence a toner.
    "kettle chips", "kettle crisps", "kettle corn", "crisps", "vanilla essence", "vanilla extract", "almond extract",
)
MEDIA = (
    "books", "book for", "book about", "book on", "novel", "novels", "audiobook", "ebook", "movie", "movies",
    "film for", "film to", "films", "tv show", "tv shows", "tv series", "documentary", "podcast", "podcasts", "album",
    "albums", "song", "songs", "music for", "music to", "playlist", "video game", "video games", "game for", "games",
    "app for", "apps", "software", "website", "websites",
    "anime", "manga", "comic", "comics", "youtube channel", "streaming service", "netflix",
)
NOT_PRODUCTS = (
    # services
    "plumber", "electrician", "builder", "mechanic", "dentist", "doctor", "therapist", "counsellor", "counselor",
    "lawyer", "solicitor", "accountant", "hairdresser", "barber", "haircut", "hair salon", "nail salon", "salon", "spa",
    "tutor", "driving instructor", "driving lessons", "lessons", "online course", "insurance", "mortgage", "loan",
    "credit card", "bank", "bank account", "savings account", "pension", "broker", "investment", "investments",
    "stocks", "shares", "crypto", "bitcoin", "energy supplier", "energy provider", "broadband", "internet provider",
    "phone plan", "phone contract", "mobile plan", "sim deal", "sim only", "vpn", "gym membership", "subscription",
    "babysitter", "nanny", "childminder", "dog walker", "dog sitter", "pet sitter", "dog trainer", "personal trainer",
    "cleaning service", "removal company", "movers", "vet", "groomer", "photographer", "wedding venue",
    "car insurance", "car hire", "car rental", "pet insurance",
    # places
    "restaurant", "restaurants", "hotel", "hotels", "hostel", "airbnb", "holiday", "vacation", "flight", "flights",
    "airline", "destination", "city", "cities", "country", "countries", "neighbourhood", "neighborhood",
)
# Advice that isn't about buying something, by how the request starts, when it names no product: "how do I get rid of
# mould", "why does my back hurt". "what should I buy my mum" isn't one: it asks for a product, and is asked about.
ADVICE = re.compile(r"^\W*(?:how (?:do|can|should|would|to|much|often|long|many)|why (?:is|are|does|do|did|won'?t|"
                    r"can'?t|isn'?t)|what (?:is|are|does|causes|happens)|is it (?:normal|safe|bad|ok|okay|possible)|"
                    r"can i|should i|am i|do i)\b")

OUT_OF_SCOPE_MESSAGE = ("Sorry, I only recommend products you can buy and use, not services, places or general advice, "
                        "so I can't help with that one.")
HARMFUL_MESSAGE = "Sorry, I don't recommend weapons, drugs, tobacco or vaping products, or adult products."
HEALTH_MESSAGE = ("Sorry, I don't recommend medicines, supplements or medical devices: a pharmacist or a doctor can "
                  "help with that one.")
FOOD_MESSAGE = "Sorry, I don't recommend food or drink, for people or pets, so I can't help with that one."
MEDIA_MESSAGE = ("Sorry, I recommend products you use, not books, films, music, games or apps, so I can't help with "
                 "that one.")
# Checked in this order when the request names no product: the first that matches gives its polite no.
NOT_RECOMMENDED = ((HEALTH, HEALTH_MESSAGE), (FOOD_AND_DRINK, FOOD_MESSAGE), (MEDIA, MEDIA_MESSAGE),
                   (NOT_PRODUCTS, OUT_OF_SCOPE_MESSAGE))
# Products holding one of those words (14 Oct 2026, the routing audit: wine glasses, a baby food maker, a photo album, a
# medicine cabinet and a flight case had each been given a polite no). Such a word directly followed by a word for a
# thing made for it (THING_WORDS below: "wine rack", "baby food maker", "medicine cabinet", "games table") names that
# thing, and these phrases name products too: both are set aside before the polite nos' words are looked for, so the
# request is asked about, or placed by the open model. Never for HARMFUL: a gun case is still its polite no.
NOT_RECOMMENDED_LOOKALIKES = ("photo album", "camera film", "35mm film", "instant film", "polaroid film",
                              "film for my camera", "film for a camera", "film for my polaroid", "spa pool",
                              "lay z spa", "lay-z-spa", "inflatable spa", "hot tub")
# Kept for code that imports it (the open model's answers in engine/query_model.py): nothing stays out by holding a
# product's name any more (an air conditioner and an oven cleaner are products of the general category since 14 Oct).
OUT_OF_SCOPE_LOOKALIKES = ()

# Phrases that hold a product's word, or an out-of-scope word, but name something else (11 Oct 2026): "cream" in "ice
# cream maker" isn't a moisturiser, a "crock pot" isn't a saucepan, a "vacuum sealer" isn't a vacuum cleaner. They are
# set aside before products are looked for, so the request is asked about, or placed by the open model
# (engine.query_model), instead of being taken for the product whose word it holds.
# Since 13 Oct 2026 also the other kinds of knife: "knife" alone is a chef's knife, as people mean it in "a good knife",
# but a paring or a bread knife isn't one (b07's Tojiro line had counted a writer's paring knives). Each with its
# plural, which isn't the name and an "s".
# Since 14 Oct 2026 (the routing audit) most of these are types of their own (engine/data/product_types.json: the
# kitchen's paring, bread, steak, boning, fillet and carving knives and cutlery, the general category's pocket knives),
# and their names win as the longer ones. The rest are set aside here, so the open model places them, never the chef
# knife: a plain "utility knife" (a box cutter or a small kitchen knife), knives for other trades (putty, palette,
# drywall, linoleum), an electric knife, Japanese slicers no type lists, and the weapon-like knives HARMFUL doesn't name
# (zombie, karambit, bowie...: since 15 Oct 2026 HARMFUL refuses them first, Noemi's decision, config.HARMFUL_KNIVES).
_OTHER_KNIVES = ("paring", "bread", "steak", "utility", "boning", "fillet", "filet", "carving", "butter", "pocket",
                 "cheese", "oyster", "tomato", "petty", "grapefruit", "electric", "sushi", "sashimi", "yanagiba",
                 "putty", "palette", "drywall", "taping", "filling", "decorating", "linoleum", "lino", "zombie",
                 "karambit", "bowie", "trench", "knuckle", "gravity", "otf", "automatic", "auto", "stiletto", "boot",
                 "neck", "credit card", "hidden", "concealed", "tanto", "kukri", "fighting", "military")
# 14 Oct 2026 (kitchen appliances, Noemi's decision 3): a blender held in the hand (config.OTHER_KIND_WORDS) isn't a
# blender, and a beauty or makeup blender is a sponge. A crock pot and an Instant Pot are no longer look-alikes: they
# name a slow cooker and a pressure cooker. Since the routing audit the same day an immersion blender is a kitchen type
# of its own (its names win; the open model had put it in the general category's home department).
_OTHER_BLENDERS = ("immersion", "stick", "hand", "handheld", "hand-held", "beauty", "makeup", "make-up")
# Where an oven, a microwave or a dishwasher is only the place something goes ("a pan to put in the oven", "oven-safe",
# "dishwasher-safe"), or what goes with it ("oven gloves", "microwave popcorn", "toaster bags"). Never "for a" or "in an":
# "looking for a microwave" and "what to look for in an oven" ask for one.
_PLACES = tuple(f"{word} {the} {appliance}" for word in ("in", "into", "inside", "to", "from")
                for the in ("the", "my", "your") for appliance in ("oven", "microwave", "dishwasher"))
FIRST_LOOKALIKES = (
    "ice cream", "coffee pot", "stock pot", "stockpot", "stock-pot", "pasta pot", "sheet pan", "cake pan", "loaf pan",
    "roasting pan",
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
    # 14 Oct 2026, the routing audit: phrases holding a first type's word, or a clue word, that name something else.
    # A grinder for tools; a kettle that's food or a fish poacher; cast iron that isn't cookware; a mixer tap or shower;
    # a pan for dust, oil or gold; a pot plant; an oven for camping or a tandoor; a shampoo or conditioner for carpets,
    # fabric, leather, soil or a fish tank; a serum for lashes; a toner for hair; an essence for baking; peel-and-stick
    # tiles; a spot treatment for stains; sun and UV words that aren't sun protection; an electric carving knife and a
    # pumpkin carving one.
    "bench grinder", "die grinder", "stump grinder", "kettle chips", "kettle crisps", "kettle corn", "fish kettle",
    "cast iron radiator", "cast iron bath", "cast iron bathtub", "cast iron tub", "cast iron fireplace",
    "cast iron stove", "cast iron wood burner", "cast iron sink", "cast iron plant", "cast iron bench",
    "cast iron gate", "cast iron pipe", "mixer tap", "kitchen mixer tap", "mixer shower", "basin mixer", "bath mixer",
    "dust pan", "drain pan", "oil drain pan", "drip pan", "gold pan", "bed pan", "pot plant", "solar oven",
    "camping oven", "tandoor oven", "tandoor", "clay oven", "toy oven", "carpet shampoo", "upholstery shampoo",
    "rug shampoo", "fabric conditioner", "leather conditioner", "water conditioner", "soil conditioner",
    "wood conditioner", "lash serum", "eyelash serum", "brow serum", "eyebrow serum", "hair toner", "purple toner",
    "blue toner", "silver toner", "blonde toner", "vanilla essence", "almond essence", "peppermint essence",
    "lemon essence", "peel and stick", "peel-and-stick", "peel & stick", "stick and peel", "carpet spot treatment",
    "spot treatment for carpet", "spot treatment for carpets", "fabric spot treatment", "upholstery spot treatment",
    "laundry spot treatment", "spot treatment for clothes", "sun shade", "sun canopy", "sun visor", "uv light",
    "uv torch", "uv flashlight", "uv steriliser", "uv sterilizer", "uv sanitiser", "uv sanitizer", "uv resin",
    "uv filter", "electric carving knife", "electric carving knives", "pumpkin carving knife",
    "pumpkin carving knives",
) + tuple(f"toner for {shade} hair" for shade in ("orange", "brassy", "yellow", "blonde", "bleached", "grey", "gray",
                                                  "silver", "white", "highlighted", "dyed", "coloured", "colored")
          ) + _PLACES + tuple(f"{kind} {knife}" for kind in _OTHER_KNIVES for knife in ("knife", "knives")) + tuple(
    f"{kind} blender" for kind in _OTHER_BLENDERS)
# 14 Oct 2026 (the general category): phrases that hold a new type's word but are something else, an accessory of it or
# a service ("phone plan", "tv show", "laptop stand", "mouse mat", "life jacket", "bike pump", "guitar lessons"), kept
# with their types in engine/data/product_types.json ("lookalikes"). Set aside like the others, so the request is asked
# about, placed by the open model, or found out of scope by its own words (a phone plan is a service). And one holding
# a first type's word: a toner cartridge isn't a toner.
_GENERAL_LOOKALIKES = tuple(phrase for entry in MORE_PRODUCT_TYPES for phrase in entry.get("lookalikes", ())) + (
    "toner cartridge",
)
# A phrase that is a product's own name is no look-alike (14 Oct 2026: "pizza oven", "vacuum sealer" and "beauty blender"
# are names of the general category's types, or of the kitchen's); the longer name wins as it always has. Every phrase
# module 1 knows as a look-alike, names included, is still another product than the type whose word it holds
# (LOOKALIKE_PHRASES: advice about it is no advice for that type, engine.answer), as an immersion blender is for a
# blender, now that it is a type of its own (14 Oct 2026, the routing audit).
_KEYWORDS = frozenset(k for product in PRODUCT_TYPES for k in product.keywords)
LOOKALIKE_PHRASES = tuple(dict.fromkeys(FIRST_LOOKALIKES + _GENERAL_LOOKALIKES))
LOOKALIKES = tuple(phrase for phrase in LOOKALIKE_PHRASES
                   if phrase not in _KEYWORDS and phrase.removesuffix("s") not in _KEYWORDS)

# Sun protection for the lips is a lip balm (Noemi's decision 2 of 15 Oct 2026: lips are an exception to her 9 Oct rule
# "sun protection wins over the form"; extraction instructions v14 type such products as lip balms). A phrase asking for
# it ("lip sunscreen", "spf for my lips", "lip oil with spf", "spf lip gloss") names the lip balm type, in place of the
# sunscreen or the lip product named inside it, and the request asks for SPF, a checked requirement of lip balms
# (config.PRODUCT_FACT_REQUEST_WORDS, "SPF"). A sunscreen request that only mentions the lips ("a sunscreen that doesn't
# sting my lips") or the face and the lips stays a sunscreen's. Chosen by Claude, reported.
# The longer forms first, so a phrase holds the whole name ("spf lip gloss", not "spf lip").
_LIP_FORMS = (r"(?:lip glosses|lip (?:balm|oil|gloss|treatment|mask|tint|butter|serum|stick|care|product|protector|"
              r"protectant|moisturi[sz]er)s?|lipbalms?|lipsticks?|lipglosse?s?|chap ?sticks?|lip ?screens?|lips?)")
_SUN_WORDS = r"(?:spf\s*\d*\+?|sun ?screens?|sun ?blocks?|sun ?creams?|suncreams?|sun protection|uv protection)"
LIP_SUN_PROTECTION = re.compile(
    rf"\b{_LIP_FORMS}\s+(?:with|that has|that have|containing|w/?)\s+(?:an?\s+|some\s+|good\s+|built[- ]in\s+)?"
    rf"{_SUN_WORDS}(?![a-z])"
    rf"|\b{_SUN_WORDS}(?:\s+sticks?)?\s+(?:for|on)\s+(?:my\s+|the\s+|your\s+|our\s+)?lips\b"
    rf"|\blip\s+{_SUN_WORDS}(?![a-z])"
    rf"|\b{_SUN_WORDS}\s+{_LIP_FORMS}\b")
_LIP_BALM = next(product for product in PRODUCT_TYPES if product.name == "lip balm")


def _lip_sun_protection(lowered: str) -> list[tuple[int, int, ProductType]]:
    """(start, end, the lip balm type) of each phrase asking for sun protection for the lips (LIP_SUN_PROTECTION)."""
    return [(m.start(), m.end(), _LIP_BALM) for m in LIP_SUN_PROTECTION.finditer(lowered)]


# Words that place a vague request in a category, so the question can be more specific.
CATEGORY_HINTS = {
    "skincare": ("skin", "face", "acne", "wrinkles", "pores", "skincare", "complexion"),
    "kitchen": ("kitchen", "cooking", "cook", "coffee", "tea", "baking", "cookware"),
    "haircare": ("hair", "scalp", "curl", "curly", "frizz", "frizzy", "dandruff", "haircare"),
}
# Skin concerns a request may name without the word "skin" (17 Oct 2026, the ws-names builder, from the 16 Oct review of
# module 1: "something for dark circles", "something for my dry lips", "cerave or la roche posay for eczema" had the
# general question, with headphones and hiking boots as examples). Looked for after the three categories' words, so a
# scalp's eczema or redness still asks about haircare.
SKIN_CONCERN_HINTS = ("blackhead", "whitehead", "spots", "breakouts", "pimple", "pigmentation", "hyperpigmentation",
                      "dark circle", "lip", "lips", "eczema", "rosacea", "melasma", "redness", "dermatitis")
# The general category's departments, by their own words (config.GENERAL_DEPARTMENTS; 14 Oct 2026): "something for my
# dog" asks within pets. After the three categories above, in the departments' order.
DEPARTMENT_HINTS = {department: entry["hints"] for department, entry in GENERAL_DEPARTMENTS.items()}

EXAMPLES = {"skincare": "a cleanser, a moisturiser or a sunscreen", "kitchen": "a kettle, a chef's knife or a pan",
            "haircare": "a shampoo, a conditioner or a hair mask"}
# The question when nothing places the request (14 Oct 2026: examples from across the categories; wording approved by
# Noemi, 19 Oct 2026).
VAGUE_QUESTION = ("What kind of product are you looking for? For example a moisturiser, a kettle, headphones or "
                  "hiking boots?")
# A gift (17 Oct 2026, the ws-names builder; wording of the gift questions, in a category or department or not, approved
# by Noemi, 19 Oct 2026): a request for a present that names no product asks what
# kind of gift, in the category or department its words suggest ("a gift for my dad who likes cooking"), with examples
# answers can give whole (the blind test's chef knives, cast iron and grinders for the kitchen); one that suggests none
# asks what the person likes, whose answer ("cooking", "gadgets") is a request the question within it then follows.
GIFT_WORDS = ("gift", "present", "stocking filler", "stocking stuffer", "secret santa")
GIFT_EXAMPLES = {"kitchen": "a chef's knife, a cast iron skillet or a coffee grinder",
                 "skincare": "a moisturiser, an eye cream or a lip balm",
                 "haircare": "a hair mask, a hair oil or a leave-in conditioner"}
CATEGORY_QUESTION = "What kind of {noun} product are you after? For example {examples}?"
GIFT_CATEGORY_QUESTION = "What kind of {noun} gift are you thinking of? For example {examples}?"
GIFT_QUESTION = "What do they like? For example cooking, coffee, skincare, gadgets or the outdoors?"
# A pet's own products (17 Oct 2026, wording PROPOSED): the pets department's examples name a cat's litter box beside a
# dog's harness, so "something for my dog" had been offered a litter box.
PET_EXAMPLES = {"dog": "a dog harness, a dog bed or a crate", "cat": "a cat tree, a litter box or a cat carrier"}
PET_WORDS = {"dog": ("dog", "dogs", "puppy", "puppies"), "cat": ("cat", "cats", "kitten", "kittens")}
# Coffee and tea, in a kitchen question (17 Oct 2026, wording PROPOSED): "present for a coffee lover" or "aeropress or v60"
# had been offered a kettle, a chef's knife or a pan. Coffee makers' names place a request in the kitchen too.
COFFEE_WORDS = ("coffee", "espresso", "aeropress", "v60", "chemex", "latte", "cappuccino", "barista")
TEA_WORDS = ("tea", "matcha")
INTEREST_EXAMPLES = (
    (COFFEE_WORDS, "a coffee grinder, an espresso machine or a French press"),
    (TEA_WORDS, "an electric kettle, a teapot or a stovetop kettle"),
)


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
    department: str | None = None  # the general category's department (config.GENERAL_DEPARTMENTS)


def classify(text: str) -> Routing:
    """Decides the outcome. Ambiguity becomes a question, never a guess.

    1. Harmful items first (HARMFUL), whatever else the request names: the polite no.
    2. Look-alikes set aside (LOOKALIKES: "microwave popcorn", "phone plan").
    3. The products the request names (14 Oct 2026, with the general category's 350 types): a product named only as
       what the request's product is for, with or on ("headphones for my phone", "a pan for an induction hob", "a
       laptop with a good keyboard": _context_ranges) isn't the one asked for; of two names written together the last
       is ("laptop backpack", "cast iron dutch oven": _heads); "X for my Y" may name a product in the other order
       ("a bed for my dog" is a dog bed, "a case for my iphone" an iPhone case: _reversed_name); a name followed by
       "-free" or "-safe", or after "not", "no" or "instead of", is a requirement, not the product; a name followed
       by a word for a thing made for it names that thing ("ipad case", "guitar strings": ACCESSORY_WORDS, 14 Oct
       2026). One product is the answer; two get one question; clue words count only when no name does; a set of pots
       and pans gets the question too, frying pan or saucepan (18 Oct 2026).
    4. No product: a polite no in the words of what it is (NOT_RECOMMENDED, ADVICE; not for a thing made for what it
       names, "wine rack", nor NOT_RECOMMENDED_LOOKALIKES, "photo album"), else a product of no type of module 1's
       named in its own words (LONG_TAIL_PRODUCTS: a kitchen mixer tap, 17 Oct 2026), else a question within the
       category or department its words suggest (since 17 Oct 2026 also its skin concerns, coffee makers' names and
       the brand-lines list's brands: "something for dark circles", "aeropress or v60", "le creuset or staub"), else
       a general question; a gift's asks what kind of gift, or what they like (GIFT_*)."""
    lowered = text.lower()
    if _HARMFUL.mentioned(_phrases_pattern(HARMFUL_LOOKALIKES).sub(lambda m: " " * len(m.group(0)), lowered)):
        return Routing("out_of_scope", message=HARMFUL_MESSAGE)
    aside = _set_aside(lowered, LOOKALIKES)
    context = _context_ranges(aside)
    every_name = _find_matches(aside, strong=True)
    owners = [(s, e) for s, e, _ in every_name if _accessory_after(aside, e)]  # "ipad" in "ipad case"
    named = [m for m in every_name if (m[0], m[1]) not in owners]
    lips = _lip_sun_protection(aside)  # "lip sunscreen" is a lip balm (15 Oct 2026), not the sunscreen inside it
    if lips:
        named = sorted([m for m in named if not any(m[0] < e and s < m[1] for s, e, _ in lips)] + lips,
                       key=lambda match: match[0])
    turned = _reversed_name(aside)
    if turned is not None and not any(s <= turned[0] and turned[1] <= e and e - s > turned[1] - turned[0]
                                       for s, e, _ in named):  # "robot vacuum for pet hair" is a robot vacuum
        named = sorted([m for m in named if not (m[0] < turned[1] and turned[0] < m[1])] + [turned],
                       key=lambda match: match[0])
    # A clue word followed by a thing made for it, or inside a name that is ("sun" in "sun lounger cushions"), counts
    # no more than that name.
    clues = [m for m in _find_matches(aside, strong=False)
             if m[2] in _clues_that_fit([m[2]], aside) and not _accessory_after(aside, m[1])
             and not any(s <= m[0] and m[1] <= e for s, e in owners)]
    own_named = [m for m in named if not _in_context(m, context)]
    own_clues = [m for m in clues if not _in_context(m, context)]
    found = [product for _, _, product in _heads(own_named, aside)] if own_named else [p for _, _, p in own_clues]
    names = list(dict.fromkeys(p.name for p in found))
    # A set of pots and pans asks which (18 Oct 2026, the ws-names builder: "a good set of pans for a first flat" had
    # been answered with frying pans): the two-product question, frying pan or saucepan, since a cookware set is no type
    # of module 1's on purpose (config's note: frying pan answers read its threads) and, found by its name alone, has
    # no saved thread of its own; never in place of another product the request names.
    if set(names) <= _SET_MEMBERS and _COOKWARE_SET.search(aside):
        return Routing("clarify", question=SEVERAL_QUESTION.format(first="frying pan", second="saucepan"),
                       several=True)

    if len(names) > 1:
        return Routing("clarify", question=SEVERAL_QUESTION.format(first=names[0], second=names[1]), several=True)
    if names:
        product = next(p for p in found if p.name == names[0])
        hints = () if own_named else tuple(h for h in product.hints if _mentions_any(aside, (h,)))
        return Routing("ok", product.category, product.name, product.subreddits or SUBREDDITS[product.category],
                       clues=hints, department=product.department)
    left = _not_recommended_text(lowered)
    for words, message in NOT_RECOMMENDED:
        if _NOT_RECOMMENDED[message].mentioned(left):
            return Routing("out_of_scope", message=message)
    if ADVICE.search(lowered):
        return Routing("out_of_scope", message=OUT_OF_SCOPE_MESSAGE)
    long_tail = _long_tail_product(lowered)
    if long_tail is not None:
        return long_tail
    gift = _mentions_any(lowered, GIFT_WORDS)
    asked = GIFT_CATEGORY_QUESTION if gift else CATEGORY_QUESTION
    category = next((c for c, hints in CATEGORY_HINTS.items() if _mentions_any(lowered, hints)), None)
    if category is None and _mentions_any(lowered, SKIN_CONCERN_HINTS):
        category = "skincare"
    if category is None and _mentions_any(lowered, COFFEE_WORDS):
        category = "kitchen"
    if category is None:
        category = _brands_category(lowered)
    if category is not None:
        examples = GIFT_EXAMPLES[category] if gift else EXAMPLES[category]
        if category == "kitchen":
            examples = next((e for words, e in INTEREST_EXAMPLES if _mentions_any(lowered, words)), examples)
        return Routing("clarify", category, question=asked.format(noun=category, examples=examples))
    department = _department_hinted(lowered)
    if department is not None:
        entry = GENERAL_DEPARTMENTS[department]
        animal = next((a for a, words in PET_WORDS.items() if _mentions_any(lowered, words)), None)
        examples = PET_EXAMPLES[animal] if department == "pets" and animal else entry["examples"]
        return Routing("clarify", "general", department=department,
                       question=asked.format(noun=entry["noun"], examples=examples))
    return Routing("clarify", question=GIFT_QUESTION if gift else VAGUE_QUESTION)


# The question when a request names two products (its wording as before 18 Oct 2026).
SEVERAL_QUESTION = "I look for one thing at a time: shall I start with the {first} or the {second}?"
# A set of pots and pans (18 Oct 2026, the ws-names builder): a set of pots or pans, pots and pans, a pan set, cookware;
# the types a set is made of may be named in it ("set of frying pans"). Asked about as two products (classify).
_SET_MEMBERS = frozenset({"frying pan", "saucepan", "cast iron skillet"})
_COOKWARE_SET = re.compile(
    r"\b(?:sets?\s+of\s+(?:[a-z'-]+\s+){0,3}?(?:pots?|pans?|saucepans?|skillets?|cookware)"
    r"|(?:pots?|saucepans?)\s+(?:and|&|n|'n')\s+(?:frying\s+)?pans?|pans?\s+(?:and|&)\s+(?:pots?|saucepans?)"
    r"|(?:pots?|pans?|saucepans?|skillets?|cookware)\s+sets?|cookware)\b")


# Products of no type of module 1's that hold another type's word, placed by the rules in their own name (17 Oct 2026,
# the ws-names builder): a kitchen mixer tap is a tap, but the open model reads it as a "kitchen mixer", the stand
# mixer's own name, so the request had been asked about as a kitchen product. {the request's words for it: (the
# product's name, its category, its department)}, longest first. A product type of its own, found in threads by its
# name, as one the open model names (engine/query_model.py); not one of module 1's types, whose names the reading AI's
# instructions list.
LONG_TAIL_PRODUCTS: dict[str, tuple[str, str, str | None]] = {
    phrase: ("mixer tap", "general", "home")
    for phrase in ("kitchen mixer tap", "mixer tap", "kitchen tap", "basin mixer tap", "basin mixer", "basin tap",
                   "bath mixer tap", "bath mixer", "bath tap", "bathroom tap", "monobloc tap", "pull out tap",
                   "pull-out tap", "kitchen faucet", "bathroom faucet", "faucet")
}


def _long_tail_product(lowered: str) -> Routing | None:
    """The routing of a request (in small letters) whose product is one of LONG_TAIL_PRODUCTS, when it names no
    product of module 1's types."""
    for phrase in sorted(LONG_TAIL_PRODUCTS, key=len, reverse=True):
        if re.search(rf"\b{re.escape(phrase)}(?:s|es)?\b", lowered):
            name, category, department = LONG_TAIL_PRODUCTS[phrase]
            communities = GENERAL_DEPARTMENTS[department]["communities"] if department else SUBREDDITS[category]
            return Routing("ok", category, name, tuple(communities), department=department)
    return None


class _Words:
    """A list of words or phrases, found whole in a lowercase text with a plural "s" allowed, by one pattern."""

    def __init__(self, words: Iterable[str]):
        alternatives = "|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True))
        self.pattern = re.compile(rf"\b(?:{alternatives})s?\b" if alternatives else r"(?!)")

    def mentioned(self, lowered: str) -> bool:
        return self.pattern.search(lowered) is not None


_HARMFUL = _Words(HARMFUL)
_NOT_RECOMMENDED = {message: _Words(words) for words, message in NOT_RECOMMENDED}

# A product's name followed by a word for a thing made for it names that thing, not the product (14 Oct 2026, the
# routing audit: an "ipad case" had been an iPad, "guitar strings" a guitar, a "kettle descaler" a kettle, "drill bits"
# a drill), as a name followed by "-free" names a requirement (_REQUIREMENT_AFTER). The words: those of
# config.OTHER_TYPE_WORDS that say what holds, covers or sharpens a product (not "set", "kit" or "bundle": a set of pans
# is pans), and parts, refills and what cleans or goes with one. A model number may come between ("iphone 15 pro
# case"). A name holding such a word is still that name, the longest found as always ("phone case", "laptop bag", "tv
# stand"), and "battery life" isn't a battery. Not "light" (a stroller light enough to carry is a stroller), "handles"
# (a vacuum that handles pet hair), "replacement" (a kettle replacement is a new kettle), "screen", "set" or "kit". The
# request is then asked about, or placed by the open model in its own words ("ipad case"); never as the product whose
# name it holds (engine.query_model).
ACCESSORY_WORDS = (
    "case", "cases", "cover", "covers", "stand", "stands", "rack", "racks", "holder", "holders", "mount", "mounts",
    "strap", "straps", "band", "bands", "bag", "bags", "sleeve", "sleeves", "strings", "pedal", "pedals", "tuner",
    "tuners", "pick", "picks", "battery", "batteries", "cable", "cables", "cord", "cords", "adapter", "adapters",
    "adaptor", "adaptors", "filament", "remote", "remotes", "parts", "accessories", "accessory", "attachment",
    "attachments", "lid", "lids", "liner", "liners", "filter", "filters", "bulb", "bulbs", "blade", "blades", "bits",
    "chain", "chains", "peg", "pegs", "pole", "poles", "pump", "pumps", "seat", "seats", "saddle", "tube", "tubes",
    "mat", "mats", "cushion", "cushions", "tray", "trays", "box", "boxes", "dock", "docks", "cleaner", "cleaners",
    "descaler", "polish", "oil", "wax", "salt", "refill", "refills", "steriliser", "sterilizer", "warmer", "warmers",
    "toy", "toys", "bowl", "bowls", "jug", "jugs", "table", "tables", "cabinet", "cabinets", "opener", "openers",
    "dispenser", "dispensers", "container", "containers", "fountain", "thermometer", "shaker", "shakers", "decanter",
    "organiser", "organizer", "organisers", "organizers", "ball", "balls", "protector", "protectors", "guard",
    "guards", "sheath", "sheaths", "roll", "strip", "strips", "block", "blocks", "sharpener", "sharpeners", "gimbal",
    "cap", "caps", "net", "nets", "frame", "frames", "legs", "wheel", "wheels", "knob", "knobs", "brush", "brushes",
    "head", "heads", "spares", "repair", "scrubber", "scrubbers", "stool", "stools", "paddle", "paddles",
    # 18 Oct 2026 (the ws-names builder): a gauge or an inflator for tyres ("digital tyre gauge" had been car tyres)
    "gauge", "gauges", "inflator", "inflators",
)
_MODEL_WORD = r"(?:[a-z]*\d[a-z0-9-]*|pro|max|mini|plus|ultra|air|lite|se|xl|oled|slim|fe|gen)"
_ACCESSORY_AFTER = re.compile(rf"(?:\s+{_MODEL_WORD}){{0,3}}\s+(?:{'|'.join(map(re.escape, ACCESSORY_WORDS))})\b"
                              r"(?!\s+life\b)")


def _accessory_after(lowered: str, end: int) -> bool:
    """Whether the name ending at `end` is followed by a word for a thing made for it (ACCESSORY_WORDS)."""
    return _ACCESSORY_AFTER.match(lowered, end) is not None


# After a word of what stays out (NOT_RECOMMENDED), the words of a thing made for it: ACCESSORY_WORDS and the things
# food, drink and the rest are kept, served or shown in ("wine glasses", "a medicine cabinet", "holiday lights").
THING_WORDS = ACCESSORY_WORDS + (
    "glass", "glasses", "light", "lights", "storage", "brewing", "making", "maker", "makers", "chiller", "bucket",
    "aerator", "pourer", "stopper", "jar", "jars", "tin", "tins", "scoop", "grinder", "mill", "press", "machine",
    "fridge", "cooler", "whisk",
)
_NOT_RECOMMENDED_BEFORE_A_THING = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in sorted({w for words, _ in NOT_RECOMMENDED for w in words}, key=len,
                                                         reverse=True))
    + r")s?\b(?=\s+(?:" + "|".join(map(re.escape, THING_WORDS)) + r")\b)")


def _not_recommended_text(lowered: str) -> str:
    """The request as the polite nos' words are looked for in it: the products holding one of them
    (NOT_RECOMMENDED_LOOKALIKES), and each one followed by a word for a thing made for it ("wine rack"), blanked out."""
    blank = lambda m: " " * len(m.group(0))  # noqa: E731
    return _NOT_RECOMMENDED_BEFORE_A_THING.sub(blank, _phrases_pattern(NOT_RECOMMENDED_LOOKALIKES).sub(blank, lowered))


def plural_ending(word: str) -> str:
    """The pattern of a word's plural ending: "es" after s, x, z, ch and sh ("body washes", "french presses"), else "s"
    (14 Oct 2026; until then always "s")."""
    return "(?:es)?" if re.search(r"(?:s|x|z|ch|sh)$", word) else "s?"


def name_pattern(name: str) -> str:
    """A product's name as a pattern, with its plural ending (plural_ending), or "ies" for a "y" after a consonant
    ("potty", "potties")."""
    if re.search(r"[^aeiou]y$", name):
        return re.escape(name[:-1]) + "(?:y|ies)"
    return re.escape(name) + plural_ending(name)


def _keyword_scanner(strong: bool) -> tuple[re.Pattern, dict[str, ProductType]]:
    """One pattern finding, at every place in a text, the longest of the products' names (or clue words) that starts
    there, with its plural ending, and which product each name is."""
    index: dict[str, ProductType] = {}
    for product in PRODUCT_TYPES:
        for word in product.keywords if strong else product.hints:
            index.setdefault(word, product)
    alternatives = "|".join(name_pattern(w) for w in sorted(index, key=len, reverse=True))
    return re.compile(rf"(?=\b((?:{alternatives}))\b)"), index


_NAMES, _NAME_INDEX = _keyword_scanner(strong=True)
_CLUES, _CLUE_INDEX = _keyword_scanner(strong=False)
# A name followed by these is a requirement ("fragrance-free", "dishwasher-safe"); after these, something not wanted
# ("headphones, not earbuds", "a kettle instead of a stovetop one").
_REQUIREMENT_AFTER = re.compile(r"(?:-(?:free|safe|proof|compatible)|\s+free)\b")
_NOT_WANTED_BEFORE = re.compile(r"\b(?:not|no|without|instead of|rather than|other than|except|never)\s+(?:an?\s+|the\s+|my\s+)?$")


def _find_matches(lowered: str, strong: bool) -> list[tuple[int, int, ProductType]]:
    """(start, end, product) of the products named in the text (or found by a clue word), in order. A name inside a
    longer one doesn't count: "kettle" in "stovetop kettle". Nor does one that is a requirement or not wanted."""
    pattern, index = (_NAMES, _NAME_INDEX) if strong else (_CLUES, _CLUE_INDEX)
    matches = []
    for m in pattern.finditer(lowered):
        word = m.group(1)
        product = (index.get(word) or index.get(word[:-1]) or index.get(word[:-2])
                   or (index.get(word[:-3] + "y") if word.endswith("ies") else None))
        start, end = m.start(1), m.end(1)
        if product is None or _REQUIREMENT_AFTER.match(lowered, end) or _NOT_WANTED_BEFORE.search(lowered[:start]):
            continue
        matches.append((start, end, product))
    return [(start, end, product) for start, end, product in matches
            if not any(s <= start and end <= e and (e - s) > (end - start) for s, e, _ in matches)]


def _find_products(lowered: str, strong: bool) -> list[ProductType]:
    """The products named in the text (or found by a clue word), in order (_find_matches)."""
    return [product for _, _, product in _find_matches(lowered, strong)]


def _heads(matches: list[tuple[int, int, ProductType]], lowered: str) -> list[tuple[int, int, ProductType]]:
    """Of two products' names written together, only the last (14 Oct 2026): the first says what the second is for or
    made for, as in "laptop backpack", "tv soundbar", "cast iron dutch oven"."""
    kept = []
    for i, match in enumerate(matches):
        following = matches[i + 1] if i + 1 < len(matches) else None
        if following is not None and re.fullmatch(r"[\s-]*", lowered[match[1]:following[0]]):
            continue
        kept.append(match)
    return kept


# What a product is for, with or on (14 Oct 2026). "for", "with", "without" and "compatible with" may come straight
# before the name or before "my", "a" or "the"; "on", "in", "into", "onto", "to" and "under" only before such a word
# ("on my desk", "in the car"). Never "for" after a word that asks for the thing itself ("looking for a kettle",
# "recommendations for a laptop", "a replacement for my kettle") or before one that does ("for choosing a mattress").
_SEEKING = ("looking", "searching", "shopping", "hunting", "recommendations", "recommendation", "recs", "rec",
            "suggestions", "suggestion", "ideas", "options", "advice", "help", "tips", "market", "replacement",
            "replacements", "substitute", "alternative", "alternatives", "upgrade", "swap", "dupe", "dupes", "go",
            "opinions", "thoughts", "reviews")
_SEEKING_AFTER = ("buying", "choosing", "getting", "picking", "finding", "purchasing", "selecting", "replacing",
                  "upgrading")
# Since 16 Oct 2026 (the interview-fixes builder) also what a product is easy, gentle or kind on, or won't dull, blunt or
# damage, with or without "my" or "the": "cutting board that's easy on knives" or "won't blunt my knives" asks for a
# cutting board, not for a knife too.
_CONTEXT_MARKER = re.compile(
    r"\b(?P<word>for|with|without|compatible with|that fits|to fit|fits|fitting)\s+"
    r"(?:(?:my|our|your|his|her|their|a|an|the|this|that)\s+)?"
    r"|\b(?:on|in|into|onto|to|under|inside)\s+(?:my|our|your|his|her|their|a|an|the)\s+"
    r"|\b(?:easy|easier|gentle|gentler|kind|kinder|soft|softer|hard|harsh|rough|safe)\s+(?:on|to)\s+"
    r"(?:(?:my|our|your|his|her|their|a|an|the)\s+)?"
    r"|\b(?:won['’]?t|will not|doesn['’]?t|does not|don['’]?t|do not|never|without)\s+"
    r"(?:dull|blunt|damage|scratch|ruin|chip|wreck|destroy|hurt)(?:s|ed|ing)?\s+"
    r"(?:(?:my|our|your|his|her|their|a|an|the)\s+)?")
_CLAUSE_BREAK = re.compile(r"[,;/&.?!()]|\b(?:and|or|but|vs|versus|plus|then|also|if)\b")
CONTEXT_WORDS = 3  # a product's name may start this many words into what a product is for: "for my new sony camera"


def _context_ranges(lowered: str) -> list[tuple[int, int]]:
    """The stretches of the text that say what the product asked for is for, with or on (see _CONTEXT_MARKER)."""
    ranges = []
    for m in _CONTEXT_MARKER.finditer(lowered):
        if m.group("word") == "for":
            before = re.findall(r"[a-z']+", lowered[:m.start()])
            after = re.match(r"[a-z']+", lowered[m.end():])
            if (before and before[-1] in _SEEKING) or (after and after.group(0) in _SEEKING_AFTER):
                continue
        stop = _CLAUSE_BREAK.search(lowered, m.end())
        words = list(re.finditer(r"\S+", lowered[m.end():stop.start() if stop else len(lowered)]))[:CONTEXT_WORDS + 1]
        ranges.append((m.end(), m.end() + words[-1].end() if words else m.end()))
    return ranges


def _in_context(match: tuple[int, int, ProductType], ranges: list[tuple[int, int]]) -> bool:
    return any(start <= match[0] < end for start, end in ranges)


_REVERSED = re.compile(r"\b([a-z][a-z'-]*?)(s?)\s+for\s+(?:(?:my|our|your|his|her|their|a|an|the)\s+)?"
                       r"([a-z0-9'-]+(?:\s+[a-z0-9'-]+){0,2})")


def _reversed_name(lowered: str) -> tuple[int, int, ProductType] | None:
    """A product named in the other order, "X for my Y" for "Y X" (14 Oct 2026): "a bed for my dog" is a dog bed,
    "toys for my cat" cat toys, "a case for my iphone" an iPhone case, "shoes for running" running shoes; only when "Y X"
    is one of module 1's names. Its span is X's. The longer name wins, as everywhere in module 1 (14 Oct 2026, the
    routing audit): "knife for wood carving" is a "wood carving knife", not a kitchen "carving knife"; then each word of
    Y alone, the last first ("a lens for my sony camera" is a camera lens)."""
    for m in _REVERSED.finditer(lowered):
        thing, others = m.group(1), m.group(3).split()
        for words in [others[i:] for i in range(len(others) - 1)] + [[w] for w in reversed(others)]:
            for name in (f"{' '.join(words)} {thing}", f"{' '.join(words)} {thing}{m.group(2)}"):
                product = _NAME_INDEX.get(name) or _NAME_INDEX.get(name.removesuffix("s"))
                if product is not None:
                    return m.start(1), m.end(2), product
    return None


def _brands_category(lowered: str) -> str | None:
    """The one category of skincare, haircare and kitchen whose brands the request names, by the brand-lines list
    (data/brand_lines.json; 17 Oct 2026: "le creuset or staub" asks about kitchen products, "cerave or la roche posay"
    about skincare), but brands that are everyday words too (config.EVERYDAY_BRAND_WORDS: "global"); None otherwise."""
    from engine.config import EVERYDAY_BRAND_WORDS

    words = " " + " ".join(re.findall(r"[a-z0-9]+", lowered.replace("'", "").replace("’", ""))) + " "
    found = set()
    for brand, categories in _brand_categories().items():
        if len(brand) == 1 and (brand[0] in EVERYDAY_BRAND_WORDS or len(brand[0]) < 4):
            continue
        if f" {' '.join(brand)} " in words:
            found |= categories
    # One category only: a brand with lines in the general category too ("ikea") says nothing of which (18 Oct 2026).
    return next(iter(found)) if len(found) == 1 and found <= {"skincare", "haircare", "kitchen"} else None


@cache
def _brand_categories() -> dict[tuple[str, ...], set[str]]:
    """{a brand's plain words: the categories the brand-lines list has its lines in}, read once; and since 18 Oct 2026
    the skincare and haircare brands config.MAKER_SPELLINGS writes ("dupe for drunk elephant protini" asks about
    skincare); nothing from the list when it can't be read."""
    from engine.config import MAKER_SPELLINGS

    def plain(name: str) -> tuple[str, ...]:
        return tuple(re.findall(r"[a-z0-9]+", name.lower().replace("'", "").replace("’", "")))

    found: dict[tuple[str, ...], set[str]] = {}
    for category in ("skincare", "haircare"):
        for name in MAKER_SPELLINGS.get(category, ()):
            if plain(name):
                found.setdefault(plain(name), set()).add(category)
    try:
        from engine.brand_lines import load_brand_lines  # here: engine.brand_lines imports this module

        lines = load_brand_lines()
    except Exception:
        return found
    for line in lines:
        for name in (line.brand, *line.also_called):
            if plain(name):
                found.setdefault(plain(name), set()).add(line.category)
    return found


def _department_hinted(lowered: str) -> str | None:
    """The department whose words the request uses, by the longest of them found ("home gym" is fitness's, "home" the
    home's), the departments' order breaking a tie; None when it uses none."""
    found = [(len(hint), -i, department) for i, (department, hints) in enumerate(DEPARTMENT_HINTS.items())
             for hint in hints if _mentions_any(lowered, (hint,))]
    return max(found)[2] if found else None


def _set_aside(lowered: str, phrases: tuple[str, ...]) -> str:
    """The text with every one of these phrases blanked out (same length, so positions don't move). A phrase that starts
    inside a product's name found before it stays (14 Oct 2026): "oven safe" in "a dutch oven safe to 260c" is part of
    the Dutch oven's name, which is what the request asks for. So does one inside a product's longer name (the general
    category, 14 Oct 2026): "car wash" in "car wash soap", "nail clippers" in "dog nail clippers"."""
    for start, end in _set_aside_spans(lowered, phrases):
        lowered = lowered[:start] + " " * (end - start) + lowered[end:]
    return lowered


def _set_aside_spans(lowered: str, phrases: tuple[str, ...]) -> list[tuple[int, int]]:
    """Where _set_aside blanks the text: (start, end) of each of these phrases not inside a product's name."""
    named = [(start, end) for start, end, _ in _find_matches(lowered, strong=True)]
    return [(m.start(), m.end()) for m in _phrases_pattern(tuple(phrases)).finditer(lowered)
            if not any(start < m.start() < end or (start <= m.start() and m.end() <= end
                                                    and end - start > m.end() - m.start()) for start, end in named)]


def set_aside_stretches(lowered: str) -> list[tuple[int, int]]:
    """The stretches of a request (lowercase) that the rules read as something else than the product whose word they
    hold (14 Oct 2026, the routing audit): each look-alike they set aside ("hand blender", "tomato knife"), and each
    name followed by a word for a thing made for it, with that word ("ipad case"). The open model's answer is checked
    against them (engine.query_model): a product found only inside one, such as "knife" in "tomato knife" or "ipad" in
    "ipad case", isn't what the request names, and would bring back the very type the rules set aside."""
    return _set_aside_spans(lowered, LOOKALIKES) + accessory_stretches(lowered)


def accessory_stretches(lowered: str) -> list[tuple[int, int]]:
    """(start, end) of each product's name in a request (lowercase) followed by a word for a thing made for it, with
    that word ("ipad case", "guitar strings": ACCESSORY_WORDS): the things the request names that way."""
    aside = _set_aside(lowered, LOOKALIKES)
    stretches = []
    for start, end, _ in _find_matches(aside, strong=True) + _find_matches(aside, strong=False):
        accessory = _ACCESSORY_AFTER.match(aside, end)
        if accessory is not None:
            stretches.append((start, accessory.end()))
    return stretches


_PHRASE_PATTERNS: dict[tuple[str, ...], re.Pattern] = {}


def _phrases_pattern(phrases: tuple[str, ...]) -> re.Pattern:
    """One pattern for a list of phrases, longest first, each whole with a plural "s" allowed; made once per list."""
    if phrases not in _PHRASE_PATTERNS:
        alternatives = "|".join(re.escape(p) for p in sorted(set(phrases), key=len, reverse=True))
        _PHRASE_PATTERNS[phrases] = re.compile(rf"\b(?:{alternatives})s?\b" if alternatives else r"(?!)")
    return _PHRASE_PATTERNS[phrases]


def _clues_that_fit(found: list[ProductType], lowered: str) -> list[ProductType]:
    """Products found by a clue word alone, less the skincare ones in a request about hair (11 Oct 2026): "cream" in
    "curl cream for curly hair" is a styling product, not a moisturiser. The request is then asked about, or placed by
    the open model."""
    if not _mentions_any(lowered, CATEGORY_HINTS["haircare"]):
        return found
    return [p for p in found if p.category != "skincare"]


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


def type_asks(text: str, product_type: str | None) -> list[str]:
    """What the request's words ask for only of a product type that has the fact (config.TYPE_ASKED_WORDS; 18 Oct 2026:
    "non toxic" asks a frying pan or a saucepan for PFAS-free, and nothing of a moisturiser), in the order the request
    names them."""
    return [asked for _, asked, _ in type_asked_spans(text, product_type)]


def type_asked_spans(text: str, product_type: str | None) -> list[tuple[int, str, int]]:
    """(where it starts, what is asked, where it ends) of the first of each config.TYPE_ASKED_WORDS ask the request
    (`text`, as typed) makes of its product type."""
    found = []
    lowered = text.lower().replace("’", "'")
    for asked, entry in TYPE_ASKED_WORDS.items():
        if entry["fact"] not in PRODUCT_FACTS_BY_TYPE.get(product_type or "", ()):
            continue
        matches = [m for pattern in entry["words"] for m in re.finditer(rf"\b{pattern}\b", lowered)]
        if matches:
            first = min(matches, key=lambda m: m.start())
            found.append((first.start(), asked, first.end()))
    return sorted(found)


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
               "juicier", "microwaved",
               # 18 Oct 2026 (the ws-names builder): a stocking filler is a small present, never a "stocking filter"
               "filler", "fillers"}


# Long product nouns of the general category that people often misspell (14 Oct 2026; chosen by Claude): typos are
# corrected into these, and into the first types' words, only. The category's other words are everyday English
# ("sports", "stands", "printer" next to "pointer", "detergent" next to "deterrent") that a one-letter slip would turn
# real words into ("dark spots" into "dark sports"); they are protected from correction instead.
GENERAL_TYPO_WORDS = (
    "vacuum", "mattress", "headphones", "earbuds", "dishwasher", "dehumidifier", "humidifier", "refrigerator",
    "binoculars", "treadmill", "trampoline", "skateboard", "toothbrush", "deodorant", "mascara", "eyeliner",
    "eyeshadow", "lipstick", "sunglasses", "umbrella", "wardrobe", "suitcase", "backpack", "laptop", "keyboard",
    "smartwatch", "soundbar", "turntable", "kettlebell", "dumbbells", "barbell", "hammock", "flashlight", "headlamp",
    "chainsaw", "lawnmower", "screwdriver", "multimeter", "thermostat", "doorbell", "stroller", "pushchair", "bassinet",
    "microphone", "telescope", "wheelbarrow", "trousers", "leggings", "underwear", "pyjamas", "pajamas", "sneakers",
    "epilator", "bicycle", "helmet", "monitor", "webcam", "notebook", "foundation",
)


def _typo_vocabulary() -> tuple[frozenset[str], dict[str, tuple[str, ...]]]:
    """The words a word is never corrected from (every product name's long words), and the words typos are corrected
    into, by first letter: the first types' long words, the skin types', the active ingredients' and GENERAL_TYPO_WORDS."""
    def long_words(texts: Iterable[str]) -> set[str]:
        return {w for text in texts for w in text.split() if len(w) >= 6}

    first = {p.name for p in FIRST_PRODUCT_TYPES}
    targets = long_words(k for p in FIRST_PRODUCT_TYPES for k in p.keywords + p.hints)
    targets |= long_words(t for name, words in TITLE_WORDS.items() if name in first for t in words)
    targets |= {s for s in SKIN_TYPES if len(s) >= 6 and "-" not in s}
    # The active ingredients' words too (13 Oct 2026): "azeliac" is azelaic.
    targets |= {w for entry in INGREDIENTS.values() for pattern in entry["asked"]
                for w in re.findall(r"[a-z]+", pattern) if len(w) >= 6}
    targets |= set(GENERAL_TYPO_WORDS)
    protected = targets | long_words(k for p in PRODUCT_TYPES for k in p.keywords + p.hints)
    protected |= long_words(t for words in TITLE_WORDS.values() for t in words)
    by_letter: dict[str, list[str]] = {}
    for word in targets:
        by_letter.setdefault(word[0], []).append(word)
    return frozenset(protected), {letter: tuple(words) for letter, words in by_letter.items()}


_VOCABULARY, _VOCABULARY_BY_LETTER = _typo_vocabulary()  # made once


def _plural_of(a: str, b: str) -> bool:
    """Whether one word is the other with a plural ending: never a typo ("stand" isn't "stands" misspelt)."""
    return a in (b + "s", b + "es") or b in (a + "s", a + "es")


def correct_typos(text: str) -> str:
    """Fixes one wrong letter in a long product or skin-type word ("clenser" -> "cleanser", "sensitve" ->
    "sensitive"). Only when the word keeps its first letter (typos rarely change it: "settle" isn't "kettle"),
    the fix is unambiguous, and the word isn't a real word of its own ("cleaner")."""

    def fix(match: re.Match) -> str:
        word = match.group(0)
        lowered = word.lower()
        if len(lowered) < 5 or lowered in _VOCABULARY or lowered in _REAL_WORDS:
            return word
        candidates = {v for v in _VOCABULARY_BY_LETTER.get(lowered[0], ())
                      if one_edit_apart(lowered, v) and not _plural_of(lowered, v)}
        return candidates.pop() if len(candidates) == 1 else word

    return re.sub(r"[A-Za-z]+", fix, text)


_DEFAULT = object()  # parse_query's model: the open model when this machine has it (engine.query_model)


# Money in words (18 Oct 2026, the ws-names builder, from the 16 Oct understanding review's U9: "less than a tenner" and
# "about forty quid" gave no budget, so their answers ignored it): written in figures before the budget is read
# (engine.query_rules.parse_budget, whose rules don't change), so "a tenner" is £10, "a fiver" £5, "forty quid" 40
# quid, "a hundred bucks" 100 bucks and "a grand" or "2 grand" 1000 or 2000, with no currency written, as a bare number
# after "under" has always been read. Number words count only before quid, pounds, bucks, dollars or euros: "a forty
# pound kettlebell" is a weight.
_MONEY_UNITS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9}
_MONEY_TEENS = {"ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
                "seventeen": 17, "eighteen": 18, "nineteen": 19}
_MONEY_TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
               "ninety": 90}
_SMALL_NUMBER = (rf"(?:(?:{'|'.join(_MONEY_TENS)})(?:[\s-]+(?:{'|'.join(_MONEY_UNITS)}))?|{'|'.join(_MONEY_TEENS)}"
                 rf"|{'|'.join(_MONEY_UNITS)})")
_NUMBER_IN_WORDS = re.compile(
    rf"\b(?P<number>(?:a|{'|'.join(_MONEY_UNITS)})\s+hundred(?:\s+(?:and\s+)?{_SMALL_NUMBER})?|{_SMALL_NUMBER})"
    r"\s+(?P<unit>quid|pounds|bucks|dollars|euros)\b")
_MONEY_SLANG = re.compile(r"\b(?:a\s+)?(?P<word>tenner|fiver)\b")
_GRAND = re.compile(rf"\b(?P<number>\d{{1,2}}|a|{'|'.join(_MONEY_UNITS)}|{'|'.join(_MONEY_TEENS)})\s+grand\b")


def _number_in_words(words: str) -> int:
    """The number some number words write ("forty", "twenty five", "two hundred and fifty")."""
    before, hundred, after = words.partition("hundred")
    count = (1 if before.strip() == "a" else _MONEY_UNITS[before.strip()]) if hundred else 0
    small = sum(_MONEY_UNITS.get(word, 0) + _MONEY_TEENS.get(word, 0) + _MONEY_TENS.get(word, 0)
                for word in re.split(r"[\s-]+", (after if hundred else before).strip()))
    return count * 100 + small


def money_in_figures(text: str) -> str:
    """The request, in small letters, with money written in words written in figures (see above), for the budget
    only: "less than a tenner moisturiser" is "less than £10 moisturiser"."""
    lowered = _MONEY_SLANG.sub(lambda m: "£10" if m["word"] == "tenner" else "£5", text.lower())
    lowered = _GRAND.sub(lambda m: str(1000 * (1 if m["number"] == "a" else int(m["number"]) if m["number"].isdigit()
                                               else _MONEY_UNITS.get(m["number"], 0) + _MONEY_TEENS.get(m["number"], 0))),
                         lowered)
    return _NUMBER_IN_WORDS.sub(lambda m: f"{_number_in_words(m['number'])} {m['unit']}", lowered)


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
        other = routed_by_model(text, model)
        # A gift's question stands unless the model names a product in the request's own words (18 Oct 2026: the
        # model's "other" had made "secret santa gift under £20" a polite no; a present is something to buy).
        if other is not None and not (other.status != "ok" and _mentions_any(text.lower(), GIFT_WORDS)):
            routing = other
    elif routing.status == "ok" and routing.clues:
        routing = _second_opinion(text, routing, model)
    if routing.status == "out_of_scope":
        return ParsedQuery(text=original, status="out_of_scope", message=routing.message)
    ingredients = [f.ingredient for f in found if TYPE_OWN_INGREDIENT.get(routing.product_type or "") != f.ingredient]

    constraints = Constraints(
        budget=parse_budget(money_in_figures(text)),
        skin_types=parse_skin_types(text),
        size=parse_size(text),
        spf=parse_spf(text),
        min_years=parse_min_years(text),
        must_haves=find_must_haves(text),
        ingredients=ingredients,
        forms=forms_named(text, found) if led else [],
    )
    if routing.status == "ok":  # what the words ask only of this type ("non toxic" pans are PFAS-free; 18 Oct 2026)
        asked = [a for a in type_asks(text, routing.product_type) if a not in constraints.must_haves]
        if asked:
            constraints = constraints.model_copy(update={"must_haves": constraints.must_haves + asked})
    if routing.status == "clarify":
        # Kept so that, once the shopper answers, what they already said isn't lost.
        return ParsedQuery(text=original, status="clarify", category=routing.category, constraints=constraints,
                           question=routing.question, department=routing.department)
    return ParsedQuery(
        text=original,
        status="ok",
        category=routing.category,
        product_type=routing.product_type,
        constraints=constraints,
        search_terms=search_terms(routing.product_type, constraints),
        subreddits=_condition_subreddits(routing.subreddits, constraints.skin_types, routing.product_type),
        ingredient_led=led,
        department=routing.department,
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
