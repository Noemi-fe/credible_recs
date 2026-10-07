"""Module 1, query understanding: rules that read the hard constraints straight out of a shopper's request.

The brief's plan for module 1 is "AI plus rules": the AI works out the category, the product type and the
search terms, and these rules read the numbers and units, where a rule is free, instant and never makes up a
value. Each function takes the request exactly as typed:

- parse_budget: the price limits and their currency ("under £30", "£20-40", "around $100").
- parse_size: a size, with its unit normalised ("1.7L" -> 1.7 l, '8"' -> 8 in).
- parse_spf: the sun protection factor ("spf 50+" -> 50).
- parse_min_years: how many years it should last ("lasts 10+ years" -> 10).
- parse_skin_types: skin types, in the order they were typed ("for oily, acne-prone skin").

When a phrase is ambiguous, the rules leave it out rather than guess. A missing constraint only widens the
search; a wrong one can hide the right product. In practice:

- A number is only money when a currency is written next to it ("£30", "30 quid") or a firm budget word comes
  with it ("under 30", "budget 40", "between 20 and 40", "150 or less"). Vaguer words ("around", "over", "from")
  need the currency too, because "women over 40" and "I'm around 35" are ages, not prices.
- Numbers that belong to something else (a size, an SPF, a lifespan, a weight, a percentage, a count) are
  blanked out before looking for money, so "1.7l kettle under £40" is a £40 budget, never £1.70.
- The currency is never guessed: no currency written means currency None.
- A skin type only counts in skincare phrasing: types followed by "skin" ("dry, sensitive skin"), "skin is" or
  "skin type" followed by types ("my skin is oily"), or "I'm" followed by types ("I'm sensitive and dry"). So
  "dry quickly" and "a normal kettle" give nothing. Acne words ("acne", "breakouts") count on their own, as
  they are only ever about skin; "spots" only in "for spots" or "prone to spots", because pans have hot spots.
"""

import re
from typing import NamedTuple

from engine.query import Budget, Size

# --- Shared pieces ---

# Every gap in these patterns is written so its spaces can match only one way: "\s*(?:-\s*)?", never "\s*-?\s*".
# With two optional runs of spaces side by side, a failed match retries every split of the spaces between them,
# and a long request could take minutes.

# A number as shoppers type it: "30", "29.99", "29,99" (decimal comma) or "1,200" (thousands comma).
# It must stand on its own, so the 50 in "spf50" or the 60 in "v60" is not a number here.
_NUMBER = r"(?<![\w.,])(?:\d{1,3}(?:,\d{3})+(?!\d)|\d+)(?:[.,]\d+)?(?![.,]?\d)"

_PLAIN = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "″": '"', "–": "-", "—": "-", " ": " "})


def _normalise(text: str) -> str:
    """Lowercase, with curly quotes, long dashes and non-breaking spaces typed the plain way."""
    return text.lower().translate(_PLAIN)


def _to_float(number: str) -> float:
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", number):
        return float(number.replace(",", ""))  # "1,200" is one thousand two hundred
    return float(number.replace(",", "."))  # "29,99" is how much of Europe writes 29.99


# --- Size ---

# How shoppers write each unit, by the unit we store (SIZE_UNITS).
_UNITS = {
    "fl oz": r"fl\.?\s*oz|fluid\s+ounces?",
    "ml": r"mls?|millilit(?:re|er)s?",
    "l": r"l|ltrs?|lit(?:re|er)s?",
    "qt": r"qts?|quarts?",
    "in": r"inch(?:es)?",
    "cm": r"cms?|centimet(?:re|er)s?",
    "mm": r"mms?|millimet(?:re|er)s?",
}
_SIZE = re.compile(
    # A number after a currency sign is a price, even when a quote mark follows it ('under "£30"').
    rf"(?<![£€$])(?P<value>{_NUMBER})(?:"
    rf"\s*(?:-\s*)?(?P<unit>{'|'.join(_UNITS.values())})(?![a-z])"
    # "in" and the inch sign only count stuck to the number ("12in", '8"'): a spaced "30 in" is usually the
    # word in ("under 30 in the uk"), and "2-in-1" is a kind of product, not 2 inches.
    r'|-?(?P<inch>in(?![a-z])(?!-\d)|")'
    r")"
)


def parse_size(text: str) -> Size | None:
    """The first size in the request, with its unit normalised ("1.7L" -> 1.7 l), or None."""
    for match in _SIZE.finditer(_normalise(text)):
        value = _to_float(match["value"])
        if value > 0:
            unit = "in" if match["inch"] else next(u for u, written in _UNITS.items() if re.fullmatch(written, match["unit"]))
            return Size(value=value, unit=unit)
    return None


# --- SPF ---

_SPF = re.compile(
    r"\b(?:spf|factor)\s*(?:[-:]\s*)?(?P<after>\d{1,3})(?!\d)\s*\+?"  # "SPF 50", "spf50", "spf 30+", "factor 50"
    r"|(?<![\w.,])(?P<before>\d{1,3})\s*(?:\+\s*)?spf(?![a-z])"  # "a 50 spf sunscreen"
)


def parse_spf(text: str) -> int | None:
    """The SPF asked for ("spf 50+" -> 50), or None. Values outside 1-100 are skipped: no sunscreen has them."""
    for match in _SPF.finditer(_normalise(text)):
        spf = int(match["after"] or match["before"])
        if 1 <= spf <= 100:
            return spf
    return None


# --- How many years it should last ---

_YEARS = re.compile(
    r"(?P<lead>\b(?:last|lasts|lasting|last me|for|at least|min|minimum|over|more than)\s+"
    r"(?:(?:at least|over|more than|a good|another)\s+)?)?"
    r"(?<![\w.,])(?P<value>\d{1,3})(?![\d.,]?\d)\s*(?:(?P<plus>\+)\s*)?(?:-\s*)?(?:years?|yrs?)(?![a-z])"
    r"(?!\s*(?:-\s*)?olds?(?![a-z]))"  # "for 20 year olds" is an age
    r"(?P<tail>\s*(?:\+|or more|or longer|plus))?"
)


def parse_min_years(text: str) -> int | None:
    """How many years the product should last ("lasts 10+ years" -> 10), or None.

    A number of years only counts with words that make it a lifespan: "10+ years", "10 years or more", or after
    "last", "for" or "at least". A year on its own ("a 2026 kettle") or "years" without a number gives None.
    """
    for match in _YEARS.finditer(_normalise(text)):
        years = int(match["value"])
        if years >= 1 and (match["lead"] or match["plus"] or match["tail"]):
            return years
    return None


# --- Budget ---

_CURRENCIES = {
    "GBP": r"£|gbp|pounds?|quid",
    "EUR": r"€|eur|euros?",
    "USD": r"\$|usd|dollars?|bucks?",  # "bucks": Noemi's call, 7 Oct 2026
}
_CURRENCY_BEFORE = r"[£€$]|\b(?:gbp|eur|usd)"  # only symbols and codes go before the number ("£30", "usd 30")
_CURRENCY_AFTER = rf"(?:{'|'.join(_CURRENCIES.values())})(?![a-z])"  # any of them can follow it ("30 quid")


def _amount(name: str) -> str:
    """A price: a number with an optional currency before or after it ("£30", "30 quid", "29,99€", "£1.5k")."""
    return (
        rf"(?:(?P<{name}_before>{_CURRENCY_BEFORE})\s*)?"
        rf"(?P<{name}>{_NUMBER})(?P<{name}_k>k(?![a-z]))?"
        rf"(?:\s*(?P<{name}_after>{_CURRENCY_AFTER}))?"
    )


# Firm words: a bare number after them is still a budget ("under 30", "budget 40").
_CEILING_WORDS = r"under|below|(?<!no )(?<!not )less than|cheaper than|max|maximum|up ?to|no more than|not more than|at most"
_BUDGET_WORDS = r"(?:budget|spend|spending|price|priced|costs?|costing)(?:\s+(?:is|of|at|around|about|roughly))*"
# Vague words: the number needs a written currency, or "over 40" and "around 35" (ages) would become budgets.
_FLOOR_WORDS = r"over|above|(?<!no )(?<!not )more than|at least|from|min|minimum|no less than|not less than"
_ABOUT_WORDS = r"around|about|roughly|approx|approximately|circa"

_RANGE = re.compile(
    rf"(?:\b(?P<intro>between|from|{_BUDGET_WORDS})[\s.:]*)?"
    rf"{_amount('low')}\s*(?P<sep>-|to|and)\s*{_amount('high')}"
)
_CEILING = re.compile(rf"(?:\b(?P<firm>{_CEILING_WORDS}|{_BUDGET_WORDS})|\b(?:{_ABOUT_WORDS})|~)[\s.:]*{_amount('amount')}")
# Firm words after the number ("150 or less", "40 tops"). Not "or more" or "max": "4 or more people" and
# "serves 4 max" are counts.
_CEILING_AFTER = re.compile(rf"{_amount('amount')}\s*(?P<firm>or less|or under|or below|tops|at most)(?![a-z])")
_FLOOR = re.compile(rf"\b(?:{_FLOOR_WORDS})[\s.:]*{_amount('amount')}")
_LONE_PRICE = re.compile(rf"{_amount('amount')}(?P<floor>\s*(?:\+|or more|or above|and up|and above)(?![a-z]))?")

# Numbers with these after them are weights, times, percentages or counts, never money.
_NOT_MONEY = re.compile(
    rf"{_NUMBER}(?:"
    r"\s*(?:\+\s*)?(?:-\s*)?(?:oz|ounces?|g|grams?|kg|kilos?|kilograms?|lbs?|years?|yrs?|months?|weeks?|days?|hours?|hrs?"
    r"|minutes?|mins?|percent|watts?|people|persons?|servings?|cups?|pieces?|pcs|packs?|yo|y/o)(?![a-z])"
    r"|(?:s|x|w)(?![a-z])"  # stuck to the number: "over 40s" (an age), "2x", "2000w"
    r"|\s*(?:%|°)"
    r")"
)


class _Price(NamedTuple):
    value: float
    currency: str | None


def _price(match: re.Match, name: str) -> _Price:
    value = _to_float(match[name]) * (1000 if match[f"{name}_k"] else 1)
    written = match[f"{name}_before"] or match[f"{name}_after"]
    currency = next((code for code, pattern in _CURRENCIES.items() if re.fullmatch(pattern, written)), None) if written else None
    return _Price(value, currency)


def _first_limit(pattern: re.Pattern, text: str) -> _Price | None:
    """The first price the pattern finds that is clearly money: a currency is written, or a firm word comes first."""
    for match in pattern.finditer(text):
        price = _price(match, "amount")
        if price.currency or match.groupdict().get("firm"):
            return price
    return None


def parse_budget(text: str) -> Budget | None:
    """The price limits in the request, or None.

    Tried in this order: a range ("£20-40"), then floor and ceiling words ("over £20", "under £50", "150 or less"),
    then a lone price ("£30 kettle"), which is read as a max, or as a min when it ends in "+" ("£50+").
    """
    text = _normalise(text)
    for not_money in (_SPF, _SIZE, _NOT_MONEY):
        text = not_money.sub(" _ ", text)

    for match in _RANGE.finditer(text):
        low, high = _price(match, "low"), _price(match, "high")
        currency = low.currency or high.currency
        if match["sep"] == "and" and match["intro"] != "between":
            continue  # "and" only joins two prices after "between"
        if currency or match["intro"] not in (None, "from"):
            smaller, larger = sorted((low.value, high.value))
            return Budget(min=smaller, max=larger, currency=currency)

    floor = _first_limit(_FLOOR, text)
    ceiling = _first_limit(_CEILING, text) or _first_limit(_CEILING_AFTER, text)
    if floor and ceiling and floor.value > ceiling.value:
        floor = None  # they contradict each other: keep the max, which never shows something over budget
    if floor or ceiling:
        currency = next((limit.currency for limit in (floor, ceiling) if limit and limit.currency), None)
        return Budget(min=floor and floor.value, max=ceiling and ceiling.value, currency=currency)

    for match in _LONE_PRICE.finditer(text):
        price = _price(match, "amount")
        if price.currency:
            if match["floor"]:
                return Budget(min=price.value, currency=price.currency)
            return Budget(max=price.value, currency=price.currency)
    return None


# --- Skin types ---

# How shoppers write each skin type, by the type we store (SKIN_TYPES).
_SKIN_WORDS = {
    "dry": r"dry",
    "oily": r"oily",
    "combination": r"combination|combo",
    "sensitive": r"sensitive",
    "acne-prone": r"acne[- ]?prone|acne|spot[- ]?prone|spotty|breakouts?",
    "normal": r"normal",
    "mature": r"mature",
}
_SKIN_TYPE = rf"\b(?:{'|'.join(_SKIN_WORDS.values())})\b"
_INTENSIFIER = r"(?:(?:very|super|extremely|really|quite|slightly|a bit|a little|mostly|somewhat|kinda|also)\s+)?"
# Skin types written together: "dry, sensitive", "oily and acne-prone", "normal to dry", "very dry".
_SKIN_LIST = rf"{_INTENSIFIER}{_SKIN_TYPE}(?:(?:\s*[,&/+]\s*|\s+)(?:(?:and/or|and|or|but|to)\s+)?{_INTENSIFIER}{_SKIN_TYPE})*"

_SKIN_PHRASES = (
    re.compile(rf"{_SKIN_LIST}[\s-]+skin\b"),  # "dry, sensitive skin"
    re.compile(rf"\bskin(?:\s+type(?:\s*(?:is|:))?|'s|\s*:|\s+(?:is|gets|feels|that'?s|that is|which is))\s*{_SKIN_LIST}"),  # "my skin is oily"
    re.compile(rf"\b(?:i'?m|i am)\s+{_SKIN_LIST}"),  # "I'm sensitive and dry"
)
_ACNE = re.compile(r"\b(?:acne|breakouts?|breaking out)\b|\b(?:for|prone to|get|getting)\s+spots\b")


def parse_skin_types(text: str) -> list[str]:
    """Skin types from SKIN_TYPES, in the order they appear, without repeats; only in skincare phrasing (see above)."""
    text = _normalise(text)
    found = []  # (where it appears, skin type)
    for phrase_pattern in _SKIN_PHRASES:
        for phrase in phrase_pattern.finditer(text):
            for word in re.finditer(_SKIN_TYPE, phrase[0]):
                skin_type = next(t for t, written in _SKIN_WORDS.items() if re.fullmatch(written, word[0]))
                found.append((phrase.start() + word.start(), skin_type))
    found += [(match.start(), "acne-prone") for match in _ACNE.finditer(text)]
    return list(dict.fromkeys(skin_type for _, skin_type in sorted(found)))
