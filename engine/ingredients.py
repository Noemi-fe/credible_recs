"""Active ingredients (13 Oct 2026): a request that names one is answered with products that contain it.

Why: Noemi tested the live site with "salicylic acid for acne". Module 1 read "salicylic" as a clue for an exfoliant,
so the answer was an exfoliant answer: its picks included a powder and peel pads, its "Also worth a look" an AHA, and
nothing said whether any of them held the acid. She had asked for an ingredient, not for a type of product: "it should
give me like a serum, not an exfoliant". The decision (the orchestrator's, reported to her): when a request names an
active ingredient, the answer is ingredient-led. Every product it shows contains that ingredient, and the ingredient is
a hard requirement, like the product facts' requirements (engine/product_facts.py).

How it works, end to end:
1. Module 1 (engine/query.py) finds the ingredients a request names (find_ingredients), by the words of
   config.INGREDIENTS ("salicylic acid", "BHA", "niacinamide", "vitamin C"...). A request that says "no X",
   "without X", "X-free" or "instead of X" doesn't ask for X. Found ingredients go in constraints.ingredients.
   - With a product type named as well ("salicylic acid cleanser"), the type stays and the ingredient is required.
   - With none ("salicylic acid for acne"), the request is ingredient-led: its product type is the ingredient's own
     ("salicylic acid product", ingredient_type_name), and its answer may show any of the skincare types that can
     carry it (wanted_types: config.INGREDIENTS' "types", such as serums, toners, pads and cleansers).
   - The retinoid words that are the retinoid type's own name ("retinol", "retinoid") add nothing: the type already
     is the requirement (Noemi's call of 7 Oct 2026, eval/edge_cases/query.json q05).
2. Module 2 (engine/sources.py) finds threads about an ingredient-led request by the ingredient's words (and its
   related ingredients': a thread about BHAs is about salicylic acid too) in the title, the post or the comments, and
   reads first those whose comments talk about it most (talk_score).
3. The pipeline (engine/pipeline.py) keeps a product only when there is evidence it contains the ingredient
   (evidence): its product-facts entry lists it among its actives (data/product_facts.json, "actives", from the
   maker's page), or, when the entry lists no actives, the name it is shown under names it ("Paula's Choice 2% BHA"
   names a BHA). An entry whose actives don't include it says the product isn't made with it. Without evidence the
   product is left out and named, with the reason, on the result (left_out_no_ingredient): never guessed. A writer's
   comment saying a product has the ingredient isn't evidence (decided by Claude, 13 Oct 2026): writers confuse a BHA
   with salicylic acid, name several products in one sentence, and formulas change, while a wrong product is exactly
   the mistake this fixes; the products that lack evidence are listed so their facts can be looked up instead.
4. Module 7 (engine/answer.py) says what the answer holds ("Top picks: salicylic acid products") and, for an
   ingredient-led answer, each product's form (form_of: "pads", "toner", "cleanser"), so the shopper sees a toner and
   a cleanser side by side for what they are.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cache

from engine.config import (
    INGREDIENT_FORM_WORDS,
    INGREDIENT_NOT_ASKED_AFTER,
    INGREDIENT_NOT_ASKED_BEFORE,
    INGREDIENTS,
    LEAVE_ON_FORMS,
    PRODUCT_TYPE_FORMS,
    RINSE_OFF_FORMS,
)
from engine.text import one_edit_apart

# The ingredient that is the retinoid type's own name: "retinol" asks for the type, not for more (q05, 7 Oct 2026).
TYPE_OWN_INGREDIENT = {"retinoid": "retinoid"}
# How an ingredient-led request's product type is named: "salicylic acid product".
TYPE_SUFFIX = " product"
# A one-letter slip is forgiven in a name's word this long or longer (as engine.sources.TYPO_MIN_LENGTH).
TYPO_MIN_LENGTH = 9


@dataclass(frozen=True)
class Found:
    """An ingredient a request names, and where (so the rest of the request can be read without it)."""

    ingredient: str  # its key in config.INGREDIENTS: "salicylic acid"
    start: int
    end: int


# --- In a request ---

def find_ingredients(text: str) -> list[Found]:
    """The ingredients a request asks for, in the order it names them, each once; never one it asks to avoid ("no
    niacinamide", "fragrance- and alcohol-free" aside, "niacinamide-free"). When one found ingredient is a narrower
    form of another found ("BHA (salicylic acid)"), only the narrower is kept: it says the other already."""
    lowered = _plain(text)
    found: list[Found] = []
    for key, entry in INGREDIENTS.items():
        for pattern in entry["asked"]:
            for match in _whole(pattern).finditer(lowered):
                if not _not_asked(lowered, match.start(), match.end()):
                    found.append(Found(key, match.start(), match.end()))
    found = [f for f in found if not any(o.start <= f.start and f.end <= o.end and (o.end - o.start) > (f.end - f.start)
                                         for o in found)]  # "lactic" inside "lactic acid" is the same mention
    first: dict[str, Found] = {}
    for f in sorted(found, key=lambda f: f.start):
        first.setdefault(f.ingredient, f)
    keys = list(first)
    kept = [k for k in keys if not any(other != k and _narrower(other, k) for other in keys)]
    return [first[k] for k in kept]


def _narrower(narrow: str, broad: str) -> bool:
    """Whether every active that counts for `narrow` counts for `broad`, and `broad` has more: salicylic acid is a
    narrower BHA."""
    a, b = set(INGREDIENTS[narrow]["actives"]), set(INGREDIENTS[broad]["actives"])
    return a < b


def _not_asked(lowered: str, start: int, end: int) -> bool:
    """Whether the words just before or after an ingredient say the request doesn't want it: "no", "without",
    "instead of" ... just before (or with a word such as "harsh" between: "no harsh retinol"), "-free" or
    " alternative" after."""
    before = lowered[max(0, start - 40):start]
    between = r"(?:(?:harsh|strong|added|more|any|other|too much)\s+)?"
    if re.search(rf"(?:^|[^a-z0-9])(?:{'|'.join(INGREDIENT_NOT_ASKED_BEFORE)})\s+{between}$", before):
        return True
    after = lowered[end:end + 20]
    return bool(re.match(rf"(?:s)?(?:{'|'.join(INGREDIENT_NOT_ASKED_AFTER)})(?![a-z])", after))


def blanked(text: str, found: Iterable[Found]) -> str:
    """The request with the found ingredients' words blanked out (same length), so module 1 can read what else it
    names: "lactic acid lotion" is a lotion."""
    chars = list(text)
    for f in found:
        chars[f.start:f.end] = " " * (f.end - f.start)
    return "".join(chars)


def ingredient_type_name(ingredients: Iterable[str]) -> str:
    """The product type of an ingredient-led request: "salicylic acid product", "AHA and BHA product"."""
    return " and ".join(ingredients) + TYPE_SUFFIX


def ingredients_of_type(product_type: str | None) -> tuple[str, ...]:
    """The ingredients an ingredient-led product type is named after (ingredient_type_name read back), or () when it
    isn't one: "salicylic acid product" -> ("salicylic acid",)."""
    if not product_type or not product_type.endswith(TYPE_SUFFIX):
        return ()
    keys = tuple(product_type.removesuffix(TYPE_SUFFIX).split(" and "))
    return keys if all(k in INGREDIENTS for k in keys) else ()


def wanted_types(product_type: str | None, ingredients: Iterable[str] = ()) -> tuple[str, ...]:
    """The product types an answer may show: for an ingredient-led request (its type is ingredient_type_name's), every
    type that can carry all its ingredients (those that can carry any, when no type carries all), in the order of
    config.INGREDIENTS' first ingredient; otherwise the request's own type."""
    led = ingredients_of_type(product_type)
    if not led:
        return (product_type,) if product_type else ()
    lists = [INGREDIENTS[k]["types"] for k in led]
    every = [t for t in lists[0] if all(t in other for other in lists[1:])]
    return tuple(every or dict.fromkeys(t for types in lists for t in types))


def facts_types(product_type: str | None) -> tuple[str, ...]:
    """The more product types an ingredient-led answer may show, besides wanted_types', whose products count only when
    their facts entry's formula lists the ingredient (config.INGREDIENTS' "facts_types": a retinoid with benzoyl
    peroxide, such as Epiduo; the orchestrator's decision of 14 Oct 2026); () for any other type."""
    led = ingredients_of_type(product_type)
    wanted = wanted_types(product_type)
    return tuple(dict.fromkeys(t for key in led for t in INGREDIENTS[key].get("facts_types", ()) if t not in wanted))


def talk_words(product_type: str) -> tuple[str, ...]:
    """The regular expressions that show a text talks about an ingredient-led request's ingredients: their own words
    and those of their related ingredients (a thread about BHAs talks about salicylic acid). () for another type."""
    words = []
    for key in ingredients_of_type(product_type):
        for k in (key, *INGREDIENTS[key].get("related", ())):
            words += INGREDIENTS[k]["asked"]
    return tuple(dict.fromkeys(words))


def shown(ingredients: Iterable[str]) -> str:
    """The ingredients as an answer names them: "salicylic acid", "AHA and BHA"."""
    keys = list(ingredients)
    return ", ".join(keys[:-1]) + " and " + keys[-1] if len(keys) > 1 else (keys[0] if keys else "")


# --- In a product ---

@dataclass(frozen=True)
class Evidence:
    """Whether a product contains an ingredient, and how we know."""

    contains: bool | None  # True: evidence it does; False: its maker's actives don't include it; None: not known
    how: str  # "facts" (its entry's actives), "name" (the name it is shown under), or "" when not known


def evidence(ingredient: str, name: str, actives: Iterable[str] | None) -> Evidence:
    """Whether a product contains `ingredient`: its facts entry's `actives` decide when the entry lists any (from the
    maker's page); otherwise the name it is shown under, when it names the ingredient (config.INGREDIENTS' "named");
    otherwise it isn't known. Never a guess."""
    if actives is not None:
        listed = set(actives)
        return Evidence(bool(listed & set(INGREDIENTS[ingredient]["actives"])), "facts")
    if names_ingredient(name, ingredient):
        return Evidence(True, "name")
    return Evidence(None, "")


# Words that start a writer's description of what a product has, rather than its name: "Gleanser with salicylic acid".
_DESCRIPTION = re.compile(r"\s+(?:with|w/|containing|that has|which has)\s.*$|\s+w/.*$", re.IGNORECASE)


def own_name(name: str) -> str:
    """A writer's name for a product without the description some writers add ("Kelp Gleanser with salicylic acid"
    is "Kelp Gleanser"): what follows "with" is the writer's claim about the formula, not the product's name (13 Oct
    2026; found in the library: a writer's "<cleanser> with salicylic acid" for a cleanser made without it). A
    maker's own name, from a facts entry, is read whole: makers write "with" in names too."""
    return _DESCRIPTION.sub("", name).strip() or name


def names_ingredient(name: str, ingredient: str) -> bool:
    """Whether a product's name names the ingredient: "Paula's Choice 2% BHA Skin Perfecting Liquid" names a BHA, not
    salicylic acid; "COSRX Salicylic Acid Daily Gentle Cleanser" names both. A writer's one-letter slip in a long word
    is forgiven ("niacinimide"), as module 2 forgives one in a long product name (TYPO_MIN_LENGTH letters or more:
    "retinal" and "retinol" are never one another)."""
    lowered = _plain(name)
    named = INGREDIENTS[ingredient]["named"]
    if any(_whole(pattern).search(lowered) for pattern in named):
        return True
    long_words = [p for p in named if re.fullmatch(r"[a-z]+", p) and len(p) >= TYPO_MIN_LENGTH]
    return any(one_edit_apart(word, p) for word in re.findall(r"[a-z]+", lowered) for p in long_words)


def form_of(name: str, product_type: str | None, facts_form: str | None = None) -> str | None:
    """The form a product takes, as an ingredient-led answer shows it: its facts entry's form, else what its own name
    says (config.INGREDIENT_FORM_WORDS: "peel pads" are pads, "cleansing foam" a cleanser), else its product type's
    (config.PRODUCT_TYPE_FORMS); None when none says."""
    if facts_form:
        return facts_form
    lowered = _plain(name)
    for pattern, form in INGREDIENT_FORM_WORDS:
        if _form_word(pattern).search(lowered):
            return form
    return PRODUCT_TYPE_FORMS.get(product_type or "")


def form_kind(form: str | None) -> str | None:
    """Whether a form is "leave-on" (a serum, a toner, pads, a cream, a spot treatment...) or "rinse-off" (a cleanser,
    a powder, a peel, a mask, a scrub), by config.LEAVE_ON_FORMS and RINSE_OFF_FORMS (Noemi's decision 1 of 13 Oct
    2026); None when it isn't known: an "exfoliant" whose name and facts don't say may be either."""
    if form and " or " in form:  # a line's products' forms, joined ("gel or liquid"; 14 Oct 2026): all of one kind
        kinds = {form_kind(part) for part in form.split(" or ")}
        return kinds.pop() if len(kinds) == 1 else None
    if form in LEAVE_ON_FORMS:
        return "leave-on"
    if form in RINSE_OFF_FORMS:
        return "rinse-off"
    return None


def rinse_off_word(form: str) -> str:
    """The word a request names a rinse-off form by ("powder" for a rinse-off powder), for the reason a product of it is
    left out ("ask for a salicylic acid powder to see these")."""
    return RINSE_OFF_FORMS.get(form, form)


# Words that may come between an ingredient and the form a request names ("salicylic acid 2% liquid", "bha
# exfoliating pads"): numbers and percentages, and one word describing the form.
_DESCRIBING = re.compile(r"[a-z]+ing|leave-on|daily|gentle|acne|spot|pimple|clarifying")


def forms_named(text: str, found: Iterable[Found]) -> list[str]:
    """The forms a request names right next to one of its ingredients, in the order named (Noemi's decision 1 of 13 Oct
    2026): after it ("salicylic acid wash", "salicylic acid 2% liquid", "bha exfoliating pads") or before it with
    "with" ("pads with salicylic acid"). A form word elsewhere doesn't count: in "salicylic acid that won't make my
    skin peel" no peel is asked for."""
    lowered = _plain(text)
    named: list[str] = []
    for f in found:
        after = re.findall(r"[a-z0-9%.'-]+|[^\sa-z0-9%.'-]", lowered[f.end:])
        words = [w for w in after if not re.fullmatch(r"[\d.,]+%?|%", w)]  # "2% liquid" is a liquid
        form = _form_at_start(words)
        if form is None and words and _DESCRIBING.fullmatch(words[0]):
            form = _form_at_start(words[1:])  # "exfoliating pads"
        before = re.search(r"([a-z'-]+) (?:with|containing|that (?:has|have|contains?)) $", lowered[:f.start])
        if form is None and before:
            form = _form_at_start([before.group(1)])  # "pads with salicylic acid"
        if form is not None and form not in named:
            named.append(form)
    return named


def _form_at_start(words: list[str]) -> str | None:
    """The form the first one or two words name, as a whole (config.INGREDIENT_FORM_WORDS), or None."""
    for size in (2, 1):
        phrase = " ".join(words[:size])
        if len(words) >= size:
            for pattern, form in INGREDIENT_FORM_WORDS:
                if re.fullmatch(rf"(?:{pattern})", phrase):
                    return form
    return None


@cache
def _form_word(pattern: str) -> re.Pattern:
    """A form's words found as whole words in a name."""
    return re.compile(rf"(?<![a-z0-9])(?:{pattern})(?![a-z0-9])")


# --- Helpers ---

@cache
def _whole(pattern: str) -> re.Pattern:
    """A pattern found as whole words, a plural "s" allowed after it."""
    return re.compile(rf"(?<![a-z0-9])(?:{pattern})s?(?![a-z0-9])")


def _plain(text: str) -> str:
    return text.lower().replace("’", "'").replace("‘", "'")
