"""A "best for" label per pick (26 Oct 2026, the bestfor builder; Noemi's decision 3 of 26 Oct 2026, third part).

ChatGPT labels its picks ("best for sensitive skin", "best budget"). Ours are worked out from our own evidence only: no AI
writes anything per request, and no label says more than the pick's credible voices say.

Three kinds, in the order a pick's own label is chosen when it qualifies for more than one (at most one a pick):
1. A topic its credible voices write about (config.BEST_FOR_TOPICS: sensitive skin, being quiet, battery life...). The
   pipeline notes, for each credible recommendation, which topics the writer's own words about the product hold
   (topics_in, ScoredMention.topics: the sentences about this product only, not the clauses about another product or
   person, not the words of the product's own name, and not a clause that complains or negates: "not for sensitive
   skin"). Where several topics qualify, the one with the biggest lead over the other picks.
2. Its checked price against the other picks': only when every pick has a price checked in the shopper's region and
   currency in the last config.PRICE_MAX_AGE_DAYS days (never a brand line's "from" price) and the cheapest is clearly
   below the next. A price label is never from what voices say about price: only from checked prices.
3. Long-term use: how many of its credible voices wrote after long-term use, an evidence the ranking already weighs (the
   reason line says how many); a label only when it has the most of them and clearly the biggest share.
What a request asks for is never a label, and the kinds of engine/group_kinds.py are not one: a kind is what a pick is
(its category of product, shown in the reason and under "What to look for"), not what it is best for.

A label is shown only when the evidence clearly supports it: there are at least config.BEST_FOR_MIN_PICKS picks (a lone pick
has nothing to be best against); at least config.BEST_FOR_MIN_VOICES of the pick's credible voices; more of them than any
other pick has (a tie gives the label to nobody); and a real share of the pick's own credible voices
(config.BEST_FOR_MIN_SHARE; for long-term use config.BEST_FOR_LONG_TERM_MIN_SHARE). Because a label needs more voices than
every other pick has, two picks of an answer never share one; a last check also keeps the same text off two picks. A
topic the request asked for is never a label (every pick fits what was asked, so naming it would suggest the others
don't). The label's `basis` says the numbers behind it, so a reader can check it against the reason line.

Wording and numbers: config.py's section "Build round 26 Oct 2026: bestfor".
"""

import re
from collections import Counter
from collections.abc import Callable, Collection, Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from functools import cache, lru_cache
from typing import TYPE_CHECKING

from engine import config
from engine.rank import ProductScore

if TYPE_CHECKING:  # engine.answer imports this module
    from engine.answer import ShownPrice

# Words of a label's phrase that name nothing (config.BEST_FOR_PHRASE_FILLER), for the test that a phrase is said in the
# topic's own words.
PHRASE_FILLER = frozenset(config.BEST_FOR_PHRASE_FILLER)

KIND_TOPIC, KIND_LONG_TERM, KIND_PRICE = "topic", "long-term use", "price"
_ORDER = (KIND_TOPIC, KIND_PRICE, KIND_LONG_TERM)  # which of a pick's labels it keeps when it qualifies for several


@dataclass(frozen=True)
class Label:
    """A pick's label and what it rests on, as shown."""

    text: str  # "Most praised for sensitive skin"
    basis: str  # "4 of its 6 credible voices write about sensitive skin; the other picks have 1 and 0."
    kind: str  # "topic", "long-term use" or "price"


# --- Which topics a writer's words talk about ---

def topics_in(text: str, category: str | None, names: Iterable[str] = ()) -> tuple[str, ...]:
    """The keys of config.BEST_FOR_TOPICS (those that can be found in `category`) that `text` talks about: a topic's word
    said as a whole word (or its plural), outside a clause that complains or negates it. `text` is a writer's own words
    about one product (engine.credibility.product_text). A category the topics don't list (the old "other") is the
    general one. `names` are the product's names (as shown, as the writer was read): a run of two or more of their words
    in a row is the product's name, however it is spaced ("Bose QuietComfort" written "quiet comfort"), so the words of the
    name are not the writer's own praise ("Cetaphil Gentle Cleanser" is not "gentle")."""
    if not text:
        return ()
    lowered = _without_names(text.lower().replace("’", "'"), tuple(names))
    return tuple(key for key, words in _words_of(category or "general").items()
                 if any(_said(lowered, word) for word in words))


_TOKEN = re.compile(r"[a-z0-9]+")


@lru_cache(maxsize=4096)  # bounded: names are as many as the library's products, each entry is a few short tuples
def _name_runs(names: tuple[str, ...]) -> dict[int, frozenset[tuple[str, ...]]]:
    """The runs of two or more consecutive words of the names, by length: a name's words are split where its capitals
    say ("QuietComfort" is "quiet" and "comfort")."""
    runs: dict[int, set[tuple[str, ...]]] = {}
    for name in names:
        words = _TOKEN.findall(re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name or "").lower())
        for i in range(len(words)):
            for j in range(i + 2, len(words) + 1):
                runs.setdefault(j - i, set()).add(tuple(words[i:j]))
    return {size: frozenset(found) for size, found in runs.items()}


def _without_names(text: str, names: tuple[str, ...]) -> str:
    """`text` with every run of two or more consecutive words of a name blanked out (the longest runs first), however the
    writer spaced them: the product's name is not the writer's praise."""
    runs = _name_runs(names)
    if not runs:
        return text
    found = [(m.start(), m.end(), m.group(0)) for m in _TOKEN.finditer(text)]
    letters = list(text)
    for size in sorted(runs, reverse=True):
        for i in range(len(found) - size + 1):
            if tuple(token for _, _, token in found[i:i + size]) in runs[size]:
                for k in range(found[i][0], found[i + size - 1][1]):
                    letters[k] = " "
    return "".join(letters)


@cache
def _words_of(category: str) -> dict[str, tuple[str, ...]]:
    category = category if category in config.THREAD_CATEGORIES else "general"
    return {key: topic["words"] for key, topic in config.BEST_FOR_TOPICS.items() if category in topic["categories"]}


@cache
def _pattern(word: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])" + re.escape(word.lower()) + r"(?:s|es)?(?![a-z0-9])")


_CLAUSE_END = re.compile(r"[.!?;:\n]|(?<![a-z0-9'])(?:but|though|although|however|yet|whereas|because)(?![a-z0-9'])")
_WORD = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)*")


def _said(text: str, word: str) -> bool:
    """Whether `word` is said somewhere in `text`, not negated just before it, not turned against the product just after
    it ("my dry skin, so it wasn't thick enough") and not in a clause that complains."""
    if word not in text:  # the quick check first: most words are nowhere in a comment (latency: it is most of the time)
        return False
    for match in _pattern(word).finditer(text):
        before = _WORD.findall(_CLAUSE_END.split(text[:match.start()])[-1])
        after = _WORD.findall(_CLAUSE_END.split(text[match.end():])[0])
        if _negated(before[-config.NEGATION_REACH:]) or _turned_against(after) or _complains(before + after):
            continue
        return True
    return False


def _turned_against(words_after: list[str]) -> bool:
    """Whether a negation comes soon after a topic's word in its clause without negating a complaint: "it wasn't thick
    enough" does, "it does not react" doesn't (config.BEST_FOR_NEGATABLE)."""
    for i, word in enumerate(words_after[:config.BEST_FOR_AFTER_REACH]):
        if word in _NEGATIONS:
            return not any(next_word in _NEGATABLE for next_word in words_after[i + 1:i + 3])
    return False


def _negated(words_before: list[str]) -> bool:
    """Whether the words just before a topic's word negate it: a negation among them, unless a complaint comes after the
    last one, which is what the negation negates ("doesn't sting my sensitive skin" praises it)."""
    last = max((i for i, word in enumerate(words_before) if word in _NEGATIONS), default=None)
    return last is not None and not any(word in _COMPLAINTS for word in words_before[last + 1:])


def _complains(words: list[str]) -> bool:
    """Whether a clause holds a complaint that isn't itself negated ("poor", but not "never stung")."""
    return any(word in _COMPLAINTS and not _negated(words[max(0, i - config.NEGATION_REACH):i])
               for i, word in enumerate(words))


_NEGATIONS = frozenset(config.BEST_FOR_NEGATIONS)
_COMPLAINTS = frozenset(config.BEST_FOR_COMPLAINTS)
_NEGATABLE = frozenset(config.BEST_FOR_NEGATABLE)


# --- The labels of an answer's picks ---

def label_picks(products: Sequence[ProductScore], prices: Sequence["ShownPrice"], needs: Collection = (),
                asks: Collection[str] = (), request: str = "", region: str = config.DEFAULT_REGION,
                today: date | None = None, money: Callable[[float, str], str] | None = None) -> list[Label | None]:
    """A label (or None) for each of the answer's picks, in order. `products` are the picks' scores, `prices` the prices
    as shown (engine.answer.ShownPrice, same order). `needs` (the request's judged needs), `asks` (what the request asks
    for, engine.product_facts.request_asks) and `request` (as typed) say which topics the request asked for. `region`
    and `today` decide which prices count (config.BEST_FOR_PRICE_CURRENCY, config.PRICE_MAX_AGE_DAYS)."""
    nothing: list[Label | None] = [None] * len(products)
    if len(products) < config.BEST_FOR_MIN_PICKS:
        return nothing
    candidates: list[dict[str, Label]] = [{} for _ in products]
    for index, label in _topic_labels(products, _asked(needs, asks, request)).items():
        candidates[index][KIND_TOPIC] = label
    for index, label in _long_term_labels(products).items():
        candidates[index][KIND_LONG_TERM] = label
    for index, label in _price_labels(prices, region, today or date.today(), money or _plain_money).items():
        candidates[index][KIND_PRICE] = label
    found = nothing
    used: set[str] = set()
    for index, options in enumerate(candidates):
        for kind in _ORDER:
            if kind in options and options[kind].text not in used:
                found[index] = options[kind]
                used.add(options[kind].text)
                break
    return found


def _plain_money(amount: float, currency: str) -> str:
    return f"{amount:,.0f}" if amount == int(amount) else f"{amount:,.2f}"


def _asked(needs: Collection, asks: Collection[str], request: str) -> frozenset[str]:
    """The topics the request asks for: one whose names (config.BEST_FOR_TOPICS "needs") are among the request's needs or
    asks, or whose words the request says."""
    names = {getattr(need, "name", need) for need in needs} | set(asks)
    typed = (request or "").lower().replace("’", "'")
    return frozenset(key for key, topic in config.BEST_FOR_TOPICS.items()
                     if names.intersection(topic["needs"]) or any(word in typed and _pattern(word).search(typed) for word in topic["words"]))


def _topic_labels(products: Sequence[ProductScore], asked: frozenset[str]) -> dict[int, Label]:
    """The clearest topic label of each pick that has one: a bigger lead over the best other pick first, then a bigger share
    of its own voices; the first topic of config.BEST_FOR_TOPICS wins a tie."""
    voices = [product.credible_recommendations for product in products]
    counts = [Counter(topic for m in recommendations for topic in set(m.topics)) for recommendations in voices]
    best: dict[int, tuple[tuple[int, float], Label]] = {}
    for key, topic in config.BEST_FOR_TOPICS.items():
        if key in asked:
            continue
        led = _leader([c[key] for c in counts], [len(v) for v in voices], config.BEST_FOR_MIN_SHARE)
        if led is None:
            continue
        index, n, others = led
        strength = (n - max(others), n / len(voices[index]))
        label = Label(config.BEST_FOR_LABEL.format(topic=topic["phrase"]),
                      config.BEST_FOR_BASIS_TOPIC.format(n=n, voices=len(voices[index]), topic=topic["phrase"],
                                                         picks=_other_picks(others), others=_numbers(others)),
                      KIND_TOPIC)
        if index not in best or strength > best[index][0]:
            best[index] = (strength, label)
    return {index: label for index, (_, label) in best.items()}


def _long_term_labels(products: Sequence[ProductScore]) -> dict[int, Label]:
    voices = [product.credible_recommendations for product in products]
    totals = [len(v) for v in voices]
    longs = [sum(m.evidence == "long-term use" for m in v) for v in voices]
    led = _leader(longs, totals, config.BEST_FOR_LONG_TERM_MIN_SHARE)
    if led is None:
        return {}
    index, n, others = led
    share = n / totals[index]
    # Also clearly ahead on share: with a pick whose voices nearly all wrote after years of use beside it, the pick with the
    # most voices would always lead.
    if any(share < other / total + config.BEST_FOR_LONG_TERM_SHARE_LEAD
           for i, (other, total) in enumerate(zip(longs, totals)) if i != index and total):
        return {}
    return {index: Label(config.BEST_FOR_LONG_TERM_LABEL,
                         config.BEST_FOR_BASIS_LONG_TERM.format(n=n, voices=totals[index],
                                                                picks=_other_picks(others), others=_numbers(others)),
                         KIND_LONG_TERM)}


def _leader(counts: list[int], voices: list[int], min_share: float) -> tuple[int, int, list[int]] | None:
    """(the pick with the most, its count, the others' counts) when one pick clearly leads: at least BEST_FOR_MIN_VOICES,
    more than every other pick by at least BEST_FOR_MIN_LEAD, and at least `min_share` of its own voices; else None."""
    top = max(counts)
    if counts.count(top) != 1 or top < config.BEST_FOR_MIN_VOICES:
        return None
    index = counts.index(top)
    others = [n for i, n in enumerate(counts) if i != index]
    if top < min_share * voices[index] or top - max(others) < config.BEST_FOR_MIN_LEAD:
        return None
    return index, top, others


def _price_labels(prices: Sequence["ShownPrice"], region: str, today: date, money: Callable[[float, str], str]
                  ) -> dict[int, Label]:
    """The label of the pick whose checked price is clearly the lowest: every pick needs a price in the region's currency
    (config.BEST_FOR_PRICE_CURRENCY), checked in the last config.PRICE_MAX_AGE_DAYS days, and not a brand line's "from"
    price; the cheapest must be at least config.BEST_FOR_PRICE_GAP below the next."""
    currency = config.BEST_FOR_PRICE_CURRENCY.get(region)
    if currency is None or not all(_usable(price, currency, today) for price in prices):
        return {}
    amounts = [price.amount for price in prices]
    cheapest = min(amounts)
    others = sorted(a for i, a in enumerate(amounts) if i != amounts.index(cheapest))
    if amounts.count(cheapest) != 1 or cheapest > others[0] * (1 - config.BEST_FOR_PRICE_GAP):
        return {}
    index = amounts.index(cheapest)
    sign = lambda amount: money(amount, currency)
    basis = config.BEST_FOR_BASIS_PRICE.format(
        amount=sign(cheapest), days=config.PRICE_MAX_AGE_DAYS, picks=_other_picks(others, costs=True),
        others=" and ".join(sign(a) for a in _in_pick_order(amounts, index)))
    return {index: Label(config.BEST_FOR_PRICE_LABEL, basis, KIND_PRICE)}


def _in_pick_order(amounts: list[float], index: int) -> list[float]:
    return [a for i, a in enumerate(amounts) if i != index]


def _usable(price: "ShownPrice", currency: str, today: date) -> bool:
    """A price a label may compare: an amount in the region's currency, a product's own (not a line's "from" price), checked
    within config.PRICE_MAX_AGE_DAYS."""
    if price.amount is None or price.currency != currency or price.from_price or not price.checked_on:
        return False
    try:
        age = (today - date.fromisoformat(price.checked_on)).days
    except ValueError:
        return False
    return age <= config.PRICE_MAX_AGE_DAYS


def _other_picks(others: list, costs: bool = False) -> str:
    """"pick has" / "picks have" (or "cost") for the other picks of the basis."""
    if costs:
        return config.BEST_FOR_OTHER_PICK_COSTS if len(others) == 1 else config.BEST_FOR_OTHER_PICKS_COST
    return config.BEST_FOR_OTHER_PICK if len(others) == 1 else config.BEST_FOR_OTHER_PICKS


def _numbers(others: list[int]) -> str:
    """The other picks' counts in rank order: "1", "1 and 0", "2, 1 and 0"."""
    words = [str(n) for n in others]
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1]
