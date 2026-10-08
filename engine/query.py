"""Module 1, query understanding: turns a shopper's need, typed in plain words, into a structured request.

Every request ends in one of three outcomes:
- "ok": the need is clear. We know the category, the product type, any constraints (budget, skin type,
  size, SPF, how long it should last), what to search for and in which subreddits.
- "clarify": the need is too vague, or holds two needs at once. Instead of guessing, we ask one question.
- "out_of_scope": the product isn't skincare or kitchen gear. We say so politely.
"""

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import Field, model_validator

from engine.config import SUBREDDITS, THREAD_CATEGORIES
from engine.models import Record

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
    ProductType("cleanser", "skincare", ("cleanser", "face wash", "facial wash", "cleansing oil", "cleansing balm", "micellar")),
    ProductType("moisturiser", "skincare", ("moisturiser", "moisturizer", "moisturising cream", "moisturizing cream", "face cream", "night cream", "day cream"),
                ("lotion", "cream")),
    ProductType("sunscreen", "skincare", ("sunscreen", "sun screen", "suncream", "sun cream", "sunblock"), ("spf",)),
    ProductType("retinoid", "skincare", ("retinol", "retinoid", "retinal", "tretinoin", "adapalene")),
    ProductType("serum", "skincare", ("vitamin c serum", "niacinamide serum"), ("serum", "vitamin c", "niacinamide")),
    ProductType("toner", "skincare", ("toner", "essence")),
    ProductType("eye cream", "skincare", ("eye cream", "under eye", "under-eye", "eye serum")),
    ProductType("lip balm", "skincare", ("lip balm", "lip mask", "chapstick")),
    ProductType("stovetop kettle", "kitchen", ("stovetop kettle", "stove top kettle", "stove-top kettle", "whistling kettle", "hob kettle"),
                subreddits=("BuyItForLife", "tea", "Cooking")),
    ProductType("electric kettle", "kitchen", ("electric kettle", "kettle", "gooseneck"), subreddits=("BuyItForLife", "tea", "Coffee")),
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
    "stovetop kettle": ("kettle",),
    "electric kettle": ("kettle",),
    "chef knife": ("knife",),
    "cast iron skillet": ("cast iron", "skillet"),
    "frying pan": ("pan",),
    "coffee grinder": ("grinder",),
    "teapot": ("teapot",),
}

# Things people shop for that this version doesn't cover. "-free" and "-safe" forms are requirements, not products.
OUT_OF_SCOPE = (
    "laptop", "phone", "headphones", "earbuds", "tv", "monitor", "camera", "shoes", "trainers", "sneakers", "boots", "jacket",
    "mattress", "pillow", "vacuum", "hair dryer", "hairdryer", "straightener", "shampoo", "conditioner", "makeup", "make-up",
    "foundation", "mascara", "lipstick", "perfume", "fragrance", "dishwasher", "washing machine", "fridge", "car", "bike",
    "chair", "desk", "watch", "toothbrush", "razor",
)

# Words that place a vague request in a category, so the question can be more specific.
CATEGORY_HINTS = {
    "skincare": ("skin", "face", "acne", "wrinkles", "pores", "skincare", "complexion"),
    "kitchen": ("kitchen", "cooking", "cook", "coffee", "tea", "baking", "cookware"),
}

EXAMPLES = {"skincare": "a cleanser, a moisturiser or a sunscreen", "kitchen": "a kettle, a chef's knife or a pan"}


@dataclass(frozen=True)
class Routing:
    status: str
    category: str | None = None
    product_type: str | None = None
    subreddits: tuple[str, ...] = ()
    question: str | None = None
    message: str | None = None


def classify(text: str) -> Routing:
    """Decides the outcome. Ambiguity becomes a question, never a guess."""
    lowered = text.lower()
    found = _find_products(lowered, strong=True) or _find_products(lowered, strong=False)
    names = list(dict.fromkeys(p.name for p in found))

    if len(names) > 1:
        return Routing("clarify", question=f"I look for one thing at a time: shall I start with the {names[0]} or the {names[1]}?")
    if names:
        product = next(p for p in found if p.name == names[0])
        return Routing("ok", product.category, product.name, product.subreddits or SUBREDDITS[product.category])
    if _mentions_any(lowered, OUT_OF_SCOPE, skip_requirements=True):
        return Routing(
            "out_of_scope",
            message="Sorry, I only cover skincare and kitchen gear for now, so I can't recommend that one.",
        )
    for category, hints in CATEGORY_HINTS.items():
        if _mentions_any(lowered, hints):
            return Routing("clarify", category, question=f"What kind of {category} product are you after? For example {EXAMPLES[category]}?")
    return Routing("clarify", question="What kind of product are you looking for? For example a cleanser, a sunscreen, a kettle or a chef's knife?")


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
    """What to search for, most specific first. Each search costs credits, so at most three."""
    terms = []
    if constraints.skin_types:
        terms.append(f"{product_type} for {' '.join(constraints.skin_types)} skin")
    if constraints.must_haves:
        terms.append(f"{constraints.must_haves[0]} {product_type}")
    if constraints.min_years:
        terms.append(f"{product_type} that lasts")
    terms.append(product_type)
    return terms[:2] + terms[-1:] if len(terms) > 3 else terms


# --- The whole of module 1 ---

def parse_query(text: str) -> ParsedQuery:
    """Turns a request typed in plain words into an understood request, using rules only (no AI, no cost)."""
    # Imported here because query_rules builds on this file's shapes (Budget, Size).
    from engine.query_rules import parse_budget, parse_min_years, parse_size, parse_skin_types, parse_spf

    routing = classify(text)
    if routing.status == "out_of_scope":
        return ParsedQuery(text=text, status="out_of_scope", message=routing.message)

    constraints = Constraints(
        budget=parse_budget(text),
        skin_types=parse_skin_types(text),
        size=parse_size(text),
        spf=parse_spf(text),
        min_years=parse_min_years(text),
        must_haves=find_must_haves(text),
    )
    if routing.status == "clarify":
        # Kept so that, once the shopper answers, what they already said isn't lost.
        return ParsedQuery(text=text, status="clarify", category=routing.category, constraints=constraints, question=routing.question)
    return ParsedQuery(
        text=text,
        status="ok",
        category=routing.category,
        product_type=routing.product_type,
        constraints=constraints,
        search_terms=search_terms(routing.product_type, constraints),
        subreddits=list(routing.subreddits),
    )
