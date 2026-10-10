"""Module 7, answer writing: writes the top 3 picks from a fixed template, using only verified quotes.

There is no Claude API key for now (Noemi, 7 Oct 2026), so the answer is a fixed template whose slots are filled
from the ranking's data only: names, counts and quotes. Nothing is made up or paraphrased. Later, an AI step may
write the one-line reasons, but only from the verified quotes, inside this same template.

What each pick shows (the brief):
- the product name and a one-line reason it wins; when some of its credible recommendations talk about what the
  request asks for (engine/needs.py, 9 Oct 2026), the reason says how many and about what ("3 of them about sensitive
  skin");
- its credible support: how many high- and medium-credibility voices recommend it, across how many threads;
- two or three quotes, the most credible first, each with its "why this voice counts" badges and a link to the
  comment;
- known downsides: quotes from credible warnings (and the disagreement flag when there are several);
- the score breakdown, signal by signal, with how many credible mentions talk about the request's needs (each
  counts NEED_MATCH_BOOST times as much);
- its price (Noemi's decision 11, 9 Oct 2026): from the price list (engine/prices.py), with the shop, the day it was
  checked and a link to the shop's own page for it (https only); or "Price not checked yet". When the request has a
  budget, a line says how the price compares with it. Products over the budget never get here: the pipeline leaves
  them out;
- whether it is still sold (Noemi's note, 9 Oct 2026: "are we making sure the products we recommend exist?"): from the
  same list, "Sold at <shop>, checked <date>" with a link to the shop's page (https only, and only when the price line
  doesn't already link to that page), or "Availability not checked yet". Products no longer sold never get here: the
  pipeline leaves them out. A product no longer made but sold second-hand only (vintage cast iron) says "Sold
  second-hand only: <shop>, checked <date>" with the same link (Noemi's decision, 10 Oct 2026), and so does a brand
  pick whose brand's own name has such an entry ("Griswold");
- "How to make it last" (Noemi, 9 Oct 2026): up to CARE_TIPS_PER_PICK credible care tips from the threads ("descale
  every 6 months"), each with its verified quote. Since 10 Oct 2026 (decided by Claude, as Noemi asked) the advice
  most credible writers agree on comes first and repairs ("smooth with an angle grinder") last; tips that say the same
  thing are shown once, in their best writer's words (engine.care_tips.tips_by_agreement). A pick with no tip has no
  such heading.
- cautions (product facts, decided by Claude, 9 Oct 2026): when a checked fact suits the request less well by a soft
  rule (engine/product_facts.py: a rich moisturiser for oily skin), "Note: <the reason>." under the pick's price lines.
  Products whose facts clash by a hard rule never get here: the pipeline leaves them out.
Under the picks: "what to look for" (a short blueprint from credible notes about kinds of product), the
skip-these list, and an honest message when fewer than 3 products have enough evidence.

The guardrail (the brief's most important rule): every quote is checked again, word for word, against its
comment as it is now (engine.verify_quotes), right before it is shown. A comment may have been edited or deleted
since the extraction. A quote that fails, whose comment is gone, that comes from a quoted block (someone else's
words, as at extraction), or whose matched words are over QUOTE_MAX_WORDS is dropped and never shown, anywhere:
not in the text, not in the structured answer. What is shown is the comment's own text that the quote matched,
with Reddit's HTML entities read ("&amp;" as "&"). The answer never carries the ranking's raw mentions, only the
quotes that passed. Then, "no claim without a verified quote":
- a pick needs at least 2 verified quotes (MIN_QUOTES_PER_PICK); one that has fewer gives its place to the
  next qualifying product;
- a skip-these product needs at least 1 verified warning quote, or it is left out;
- a "what to look for" note is a verified quote, or nothing;
- a care tip is a verified quote, or nothing: one that fails gives its place to the next tip.
unverified_claims() runs the same checks over a finished answer, as an automated proof.

The wording users see is in the constants below, marked PROPOSED (it waits for Noemi) or decided by Claude (Noemi
asked Claude to decide wording and report it).
"""

import dataclasses
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from datetime import date

from engine.care_tips import CareTip, CareTips, tips_by_agreement
from engine.config import (
    BRAND_PICK_MODEL,
    CARE_TIPS_PER_PICK,
    DOWNSIDES_PER_PICK,
    LOOK_FOR_NOTES,
    OPPOSITE_QUOTE_PATTERNS,
    QUOTE_VIEW_WORDS,
    MIN_CREDIBLE_MENTIONS,
    MIN_QUOTES_PER_PICK,
    MIN_THREADS,
    NEED_MATCH_BOOST,
    PICKS_SHOWN,
    PRICE_MAX_AGE_DAYS,
    QUOTE_MAX_WORDS,
    QUOTES_PER_PICK,
    QUOTES_PER_SKIPPED_PRODUCT,
)
from engine.extract import _as_written, _in_quoted_block, _own_words_in_quote_format
from engine.models import Thread
from engine.needs import LASTING
from engine.prices import PriceCheck
from engine.match_products import known_aliases
from engine.rank import KindNote, ProductScore, RankingResult, ScoredMention, ScoreBreakdown, is_credible
from engine.verify_quotes import find_quote, verify_quote

# --- Wording users see: PROPOSED 9 Oct 2026, awaiting Noemi ---
TITLE = "Top picks: {product_type}"
TITLE_ANY = "Top picks"
REASON = "Recommended by {voices}{long_term}{needs}{kind}."  # {needs} added 9 Oct 2026 (REASON_NEEDS below)
REASON_LONG_TERM = ", {n} of them after long-term use"
REASON_KIND = "; credible voices favour its kind most ({kind})"
SUPPORT = "Backed by {voices}, across {threads}."
DISAGREEMENT = "Mixed opinions: also warned against by {voices}."
NO_DOWNSIDES = "No credible voice in these threads warned against it."
SKIP_REASON = "Warned against by {voices}{praised}."
SKIP_ALSO_PRAISED = ", though still recommended by {voices}"
LOOK_FOR = "Look for"  # a kind credible voices recommend
AVOID = "Avoid"  # a kind credible voices warn against
RULE = "at least {mentions} credible recommendations across at least {threads} threads"
NO_PICKS = "Not enough credible evidence to recommend {what} yet: a pick needs {rule}. We'd rather say so than guess."
FEWER_PICKS = "Enough credible evidence for only {products} ({rule}), so we show {n} instead of {wanted}."
BADGE_VOICE = "{voice}-credibility voice"  # the badge when module 5 gave no reason in words
QUOTES_HEADING = "In their words"
DOWNSIDES_HEADING = "Known downsides"
SUPPORT_LABEL = "Credible support"
BREAKDOWN_HEADING = "Score breakdown"
LOOK_FOR_HEADING = "What to look for"
SKIP_HEADING = "Skip these"
LINK_TEXT = "see the comment"
# Prices and budgets (decision 11; wording PROPOSED 9 Oct 2026, awaiting Noemi).
PRICE_LABEL = "Price"
PRICE = "{amount} at {shop}, checked {date}"
PRICE_UNKNOWN = "Price not checked yet"
PRICE_LINK_TEXT = "see it at the shop"
BUDGET_WITHIN = "Within your budget (up to {max})."
BUDGET_NOT_CHECKED = "Not checked against your budget (up to {max}): {why}."
BUDGET_WHY_UNKNOWN = "no price checked yet"
BUDGET_WHY_CURRENCY = "its price is in {currency}"
BUDGET_WHY_OLD = "its price was checked over {days} days ago, so it may have changed"
CURRENCY_SIGNS = {"GBP": "£", "EUR": "€", "USD": "$"}
# Care tips (Noemi, 9 Oct 2026; wording PROPOSED, awaiting Noemi).
CARE_HEADING = "How to make it last"
# Needs (9 Oct 2026; wording decided by Claude, as Noemi asked). The reason line says how many of the credible
# recommendations talk about what the request asks for, and about what: "Recommended by 5 credible voices, 3 of them
# about sensitive skin." It says "about", not "with sensitive skin": the rule finds comments that talk about a need,
# not writers who have it. Needs come from engine/needs.py; one not listed here is shown as the request typed it
# ("pour-over", "PFAS"). Several are listed with commas and a last "or": "2 of them about starting out or sensitive
# skin", "3 of them about starting out, home cooking or pour-over".
REASON_NEEDS = ", {n} of them about {needs}"
NEEDS_JOIN = ", "
NEEDS_JOIN_LAST = " or "
NEED_LABELS: dict[str, str] = {
    "sensitive": "sensitive skin",
    "dry": "dry skin",
    "oily": "oily skin",
    "combination": "combination skin",
    "acne-prone": "acne-prone skin",
    "normal": "normal skin",
    "mature": "mature skin",
    "fragrance-free": "fragrance",
    "non-comedogenic": "clogged pores",
    "no white cast": "white cast",
    "cruelty-free": "cruelty-free",
    "vegan": "vegan",
    "reef-safe": "reef safety",
    "plastic-free": "plastic",
    "stainless steel": "stainless steel",
    "dishwasher-safe": "the dishwasher",
    "induction-compatible": "induction",
    "temperature control": "temperature control",
    "beginner": "starting out",
    "gentle": "gentleness",
    "home cook": "home cooking",
    "lasting": "how long it lasts",
    # A request's own word that reads badly as typed ("won't strip my skin": "about gentleness or strip"); Claude,
    # 10 Oct 2026.
    "strip": "not stripping the skin",
}
# The breakdown's line about needs: only shown when some credible mention talks about them.
BREAKDOWN_NEEDS = ("About your request: {recommends} credible recommendations and {warnings} credible warnings talk "
                   "about what you asked for (each counts {boost} times as much)")
# Availability (Noemi's note, 9 Oct 2026). Wording DECIDED by Claude on 9 Oct 2026, as Noemi asked, and reported to her.
AVAILABILITY = "Sold at {shop}, checked {date}"
AVAILABILITY_UNKNOWN = "Availability not checked yet"
AVAILABILITY_GONE = "No longer sold, checked {date}"  # never shown through the pipeline, which leaves such products out
# Sold second-hand only: a product no longer made (Griswold and Wagner cast iron), sold only second-hand, on eBay UK or
# by a UK vintage dealer. Noemi's decision of 10 Oct 2026: such products count as available, and the answer says so.
AVAILABILITY_SECOND_HAND = "Sold second-hand only: {shop}, checked {date}"
# Product facts (9 Oct 2026). Wording DECIDED by Claude on 9 Oct 2026, as Noemi asked, and reported to her. A soft
# clash between a product's checked facts and the request (engine/product_facts.py) is shown under the pick as
# "Note: its texture is rich, which can feel heavy on oily or acne-prone skin." The reasons themselves are the rule
# table's (config.PRODUCT_FACT_RULES), decided by Claude the same day.
CAUTION = "Note: {reason}."


# --- The answer ---

@dataclass(frozen=True)
class ShownQuote:
    """A quote that passed the word-for-word check, ready to show."""

    text: str  # the comment's own text the quote matched, entities read ("&amp;" as "&"); verified word for word
    comment_id: str
    url: str  # the link to the comment
    badges: tuple[str, ...]  # why this voice counts: "3 years of use", "expert flair"


@dataclass(frozen=True)
class ShownPrice:
    """A pick's price as shown, from the price list (engine/prices.py). Unknown: only `text` and the budget fields."""

    text: str  # "£120 at John Lewis, checked 9 Oct 2026", or PRICE_UNKNOWN
    amount: float | None
    currency: str | None  # GBP, EUR or USD
    shop: str | None
    url: str | None  # the shop's own page for the product, from the price list: https only
    checked_on: str | None  # the day the price was looked up, as "2026-10-09"
    budget_status: str | None  # "within", "unknown", "other currency" or "out of date"; None without a budget
    budget_note: str | None  # the same in words, for the shopper; None without a budget


@dataclass(frozen=True)
class ShownAvailability:
    """Whether a pick is known to be sold, as shown, from the price list (engine/prices.py). Not checked: only text."""

    text: str  # "Sold at Boots, checked 9 Oct 2026", AVAILABILITY_SECOND_HAND's line, or AVAILABILITY_UNKNOWN
    available: bool | None  # True: a shop sells it; None: not checked; False: no longer sold (never via the pipeline)
    shop: str | None
    url: str | None  # the shop's own page, https only; None when unknown or when the price line already links to it
    checked_on: str | None  # the day it was looked up, as "2026-10-09"
    second_hand: bool = False  # True: no longer made, sold second-hand only (10 Oct 2026); then `available` is True


NOT_CHECKED = ShownAvailability(AVAILABILITY_UNKNOWN, None, None, None, None)


@dataclass(frozen=True)
class ShownCareTip:
    """A care tip as shown under a pick: the tip in a few words, and the quote that backs it (verified)."""

    tip: str  # the AI's few plain words, as a short sentence: "Descale every 6 months."; "" when the quote says just that
    quote: ShownQuote


@dataclass
class Pick:
    rank: int  # 1, 2 or 3
    product_key: str
    name: str
    reason: str  # the one-line reason it wins
    support: str  # how many credible voices back it, across how many threads
    quotes: list[ShownQuote]  # 2 or 3, the most credible first
    downsides: list[ShownQuote]  # from credible warnings; empty when there are none
    disagreement: str | None  # the disagreement flag in words, or None
    score: float
    breakdown: ScoreBreakdown  # numbers only: no quote is in it
    price: ShownPrice  # from the price list, or PRICE_UNKNOWN
    availability: ShownAvailability = NOT_CHECKED  # where it is sold, from the price list, or AVAILABILITY_UNKNOWN
    care: list[ShownCareTip] = field(default_factory=list)  # "How to make it last"; empty when there are none
    cautions: list[str] = field(default_factory=list)  # "Note: ..." from product facts (9 Oct 2026); empty when none
    # For a brand pick: the model of that brand its credible writers recommend most (10 Oct 2026); None otherwise.
    model: str | None = None
    model_price: str | None = None  # that model's checked price, as the price line words it; None when not checked


@dataclass
class SkipItem:
    product_key: str
    name: str
    reason: str
    quotes: list[ShownQuote]  # credible warnings, at least 1


@dataclass
class LookFor:
    kind: str  # "Japanese gyuto"
    advice: str  # LOOK_FOR or AVOID
    quote: ShownQuote


@dataclass
class Answer:
    category: str
    product_type: str | None  # from the request, such as "chef knife"; only used in the wording
    picks: list[Pick]
    look_for: list[LookFor]
    skip: list[SkipItem]
    message: str | None  # the honest message when fewer than 3 picks have enough evidence
    needs_more_threads: bool  # fewer than 3 picks: fetching more threads may help
    quotes_dropped: int  # quotes that failed the check at answer time (for the logs; never shown)


def answer_to_dict(answer: Answer) -> dict:
    """The answer as plain dictionaries and lists, ready to turn into JSON for the web interface."""
    return dataclasses.asdict(answer)


def comment_bodies(threads: Iterable[Thread]) -> dict[str, str]:
    """{comment id: body} for every comment still readable: deleted or removed ones are left out, so their quotes fail."""
    return {c.id: c.body for thread in threads for c in thread.comments if c.status == "ok"}


# --- Writing the answer ---

def write_answer(ranking: RankingResult, bodies: Mapping[str, str], product_type: str | None = None,
                 prices: Mapping[str, PriceCheck] | None = None, care: Mapping[str, CareTips] | None = None,
                 cautions: Mapping[str, list[str]] | None = None, models: Mapping[str, str] | None = None,
                 asks: tuple[str, ...] = (), model_prices: Mapping[str, str] | None = None) -> Answer:
    """The answer for one request, from its ranking and the current text of its comments ({comment id: body}).

    `prices` is each product's price check ({product key: engine.prices.PriceCheck}), made by the pipeline; a product
    with none shows PRICE_UNKNOWN and AVAILABILITY_UNKNOWN. `care` is each product's care tips ({product key:
    engine.care_tips.CareTips}), made by the pipeline; a product with none shows no "How to make it last". Care tips
    never change which products are picks. `cautions` is each product's soft clashes with the request ({product key:
    [reason]}, engine/product_facts.py), made by the pipeline: each is shown on its pick as CAUTION; they never change
    which products are picks either. `models` is each brand pick's most recommended model ({product key: name}),
    made by the pipeline (engine.pipeline._brand_models), shown as BRAND_PICK_MODEL, with that model's checked price
    from `model_prices` ({product key: price line}) when there is one: shown only, never a reason to leave the brand
    out. `asks` is what the request asks
    for (engine.product_facts.request_asks): a quote saying the opposite is shown last.
    """
    check = _QuoteCheck(bodies)
    models = models or {}
    prices = prices or {}
    care = care or {}
    cautions = cautions or {}
    picks: list[Pick] = []
    for product in ranking.qualifying:
        if len(picks) == PICKS_SHOWN:
            break
        ordered = _naming_first(product.credible_recommendations, asks)
        quotes = check.first([m for m in ordered if _says_something(m)], QUOTES_PER_PICK)
        if len(quotes) < MIN_QUOTES_PER_PICK:  # a quote that says nothing about it only makes up the minimum
            quotes += check.first([m for m in ordered if not _says_something(m)], MIN_QUOTES_PER_PICK - len(quotes))
        if len(quotes) >= MIN_QUOTES_PER_PICK:
            price = shown_price(prices.get(product.key))
            availability = shown_availability(prices.get(product.key), price.url)
            tips = _care_tips(care.get(product.key), check)
            notes = [CAUTION.format(reason=reason) for reason in cautions.get(product.key, [])]
            picks.append(_pick(len(picks) + 1, product, quotes, check, ranking, price, tips, availability, notes))
            picks[-1].model = models.get(product.key)
            picks[-1].model_price = (model_prices or {}).get(product.key)
    skip = [_skip_item(product, check) for product in ranking.skip_list]
    look_for = _look_for(ranking, check)
    return Answer(
        category=ranking.category,
        product_type=product_type,
        picks=picks,
        look_for=look_for,
        skip=[item for item in skip if item is not None],
        message=_message(len(picks), product_type),
        needs_more_threads=len(picks) < PICKS_SHOWN,
        quotes_dropped=check.dropped,
    )


class _QuoteCheck:
    """Checks quotes against the comments as they are now, and counts the ones dropped."""

    def __init__(self, bodies: Mapping[str, str]):
        self.bodies = bodies
        self.dropped = 0

    def first(self, items: Iterable[ScoredMention | KindNote | CareTip], limit: int) -> list[ShownQuote]:
        """The first `limit` items whose quote passes the check, as quotes to show."""
        shown: list[ShownQuote] = []
        for item in items:
            if len(shown) == limit:
                break
            if _quote_problem(item.quote, item.comment_id, self.bodies):
                self.dropped += 1
            else:
                text = _shown_text(item.quote, self.bodies[item.comment_id])
                shown.append(ShownQuote(text, item.comment_id, item.comment_url, _badges(item)))
        return shown


def _quote_problem(text: str, comment_id: str, bodies: Mapping[str, str]) -> str | None:
    """Why a quote can't be shown, in words, or None when it passes. The reason never repeats the quote.

    The same checks as at extraction (engine.extract), on the comment as it is now. A quote from a quoted block is
    someone else's words, unless the whole comment is a quoted block whose words no other comment here has (at
    answer time only the comments are at hand: the title and post were checked at extraction). The word limit
    counts the words of the comment the quote matches.
    """
    body = bodies.get(comment_id)
    if body is None:
        return f"comment {comment_id} is not available to check against (deleted, removed or missing)"
    span = find_quote(body, text)
    if span is None:
        return f"quote not found word for word in comment {comment_id}"
    if _in_quoted_block(body, span):
        elsewhere = (other for other_id, other in bodies.items() if other_id != comment_id)
        if not _own_words_in_quote_format(body, text, elsewhere):
            return f"quote from comment {comment_id} is from a quoted block: someone else's words"
    words = len(_as_written(body, span).split())
    if words > QUOTE_MAX_WORDS:
        return f"quote from comment {comment_id} has {words} words; the limit is {QUOTE_MAX_WORDS}"
    return None


def _shown_text(quote: str, body: str) -> str:
    """What the reader sees for a quote that passed: the comment's own text it matched, entities read ("&amp;" as
    "&"), so the page never shows "&#32;" or more words than were counted, and without the writer's bold or italics
    marks (_without_emphasis, 10 Oct 2026). In the rare case that text wouldn't pass the check itself (a comment
    holding an escaped entity such as "&amp;gt;"), the quote as checked is shown."""
    text = _as_written(body, find_quote(body, quote))
    text = text if verify_quote(body, text) else quote
    plain = _without_emphasis(text)
    return plain if verify_quote(body, plain) else text


# Reddit's markdown for **bold**, __bold__, ~~strikethrough~~, *italics* and _italics_: shown as plain words (10 Oct
# 2026: "**" showed as stars on cards). The quote check ignores these marks, so the words are still the comment's own.
_EMPHASIS = (re.compile(r"\*\*(.+?)\*\*"), re.compile(r"__(.+?)__"), re.compile(r"~~(.+?)~~"),
             re.compile(r"(?<![\w*])\*(?=\S)(.+?)(?<=\S)\*(?![\w*])"),
             re.compile(r"(?<![\w_])_(?=\S)(.+?)(?<=\S)_(?![\w_])"))


def _without_emphasis(text: str) -> str:
    """The text without the writer's bold, italics and strikethrough marks; an underscore inside a word stays."""
    for pattern in _EMPHASIS:
        text = pattern.sub(r"\1", text)
    return text


def _badges(item: ScoredMention | KindNote | CareTip) -> tuple[str, ...]:
    """Module 5's reasons in words; when it gave none, the plain levels ("medium-credibility voice", "short-term use")."""
    if item.badges:
        return item.badges
    plain = (BADGE_VOICE.format(voice=item.voice),)
    return plain + ((item.evidence,) if isinstance(item, ScoredMention) else ())


def _most_credible_first(items: Iterable[ScoredMention]) -> list[ScoredMention]:
    """Largest weight first; equal weights keep their order, so the result is always the same."""
    return sorted(items, key=lambda m: -abs(m.weight))


def _naming_first(items: Iterable[ScoredMention], asks: tuple[str, ...] = ()) -> list[ScoredMention]:
    """The most credible first, but the quotes that name their product and give a view before those that only name
    it, and those before the rest (10 Oct 2026: out of context, "Others I have used and not had any issues with:" says
    little, and so does "I have a Baratza Encore, Timemore C2 and a JX"), and a quote that says the opposite of what
    the request asks ("does leave a white cast") after every other (_says_the_opposite). Each is still shown when
    there's room."""
    ordered = _most_credible_first(items)

    def tier(m: ScoredMention) -> int:  # 0: names it and gives a view; 1: only names it; 2: neither
        names = _names_product(m.quote, m.product_name, m.category)
        return 0 if names and _gives_a_view(m.quote) else 1 if names else 2

    return sorted(ordered, key=lambda m: (_says_the_opposite(m.quote, asks), tier(m)))


def _says_something(m: ScoredMention) -> bool:
    """Whether a quote names its product, gives a view, or points at it ("it", "this one", "mine"). One that does none
    of these ("yea no I'm just gonna stick with my cast iron lol.", b08, 10 Oct 2026: the comment named the pans in a
    sentence the AI didn't quote) is shown only to make up a pick's MIN_QUOTES_PER_PICK."""
    text = " ".join(re.findall(r"[a-z0-9']+", m.quote.lower().replace("’", "'")))
    return (_names_product(m.quote, m.product_name, m.category) or _gives_a_view(m.quote)
            or bool(_POINTS_AT_IT.search(text)))


# Words that point at a product already named ("I wouldn't be on my 9th bottle of it", "I've had mine for 6 years").
_POINTS_AT_IT = re.compile(r"(?<![a-z0-9'])(?:it|it's|its|this|these|those|them|they|they're|mine|ones?)(?![a-z0-9'])")
# "I like it", "I really like the gel": a view. Not "I would like" (a wish), nor "like" alone ("features like a scale").
_I_LIKE = re.compile(r"\bi (?:(?:really|also|do|still|just|honestly|actually|genuinely|personally|definitely"
                     r"|absolutely|quite) )?like[sd]?\b")


def _gives_a_view(quote: str) -> bool:
    """Whether the quote says what the writer thinks or went through (config.QUOTE_VIEW_WORDS: "great", "recommend",
    "lasted"..., or "I like"), rather than only that they own it."""
    text = " ".join(re.findall(r"[a-z0-9']+", quote.lower().replace("’", "'")))
    return (any(re.search(rf"(?<![a-z0-9']){re.escape(word)}(?![a-z0-9'])", text) for word in QUOTE_VIEW_WORDS)
            or bool(_I_LIKE.search(text)))


def _says_the_opposite(quote: str, asks: Iterable[str]) -> bool:
    """Whether the quote says the opposite of one of the request's asks (config.OPPOSITE_QUOTE_PATTERNS): "it leaves a
    white cast" for "no white cast", "smells lovely" for "fragrance-free"."""
    text = " ".join(quote.lower().replace("’", "'").split())
    return any(re.search(pattern, text) for ask in asks for pattern in OPPOSITE_QUOTE_PATTERNS.get(ask, ()))


def _names_product(quote: str, name: str, category: str) -> bool:
    """Whether the quote names the product: the first word of its name (the brand), a model code in it (a word
    with a digit: "C2", "MTH-80"), or a known short or long form of its brand (engine/data/product_aliases.json:
    "BOJ" for Beauty of Joseon, "Breville" for Sage), as whole words, capitals aside. A plural or a possessive counts
    ("old wagners", "Prequel's"), and so does a hyphen written as a space or left out ("All clad" for All-Clad; b08,
    b05 and b10, 10 Oct 2026)."""
    text = " ".join(re.findall(r"[a-z0-9][a-z0-9'-]*", quote.lower().replace("’", "'")))
    name_words = [w.removesuffix("'s") for w in re.findall(r"[a-z0-9][a-z0-9'-]*", name.lower().replace("’", "'"))]
    if not name_words:
        return False
    wanted = {name_words[0]} | {w for w in name_words if any(c.isdigit() for c in w)}
    joined = " ".join(name_words)
    for short_words, full_words in known_aliases().get(category, {}).items():
        short, full = " ".join(short_words), " ".join(full_words)
        if f"{joined} ".startswith(f"{short} ") or f"{joined} ".startswith(f"{full} "):
            wanted |= {short, full}
    return any(re.search(_as_written_loosely(w), text) for w in wanted)


def _as_written_loosely(word: str) -> str:
    """A pattern for a name word (or a short name) as a whole word: its hyphens written as a space or not at all, and a
    plural or possessive ending allowed."""
    body = "[- ]?".join(re.escape(part) for part in word.split("-"))
    return rf"(?<![a-z0-9]){body}(?:'s|s'?|')?(?![a-z0-9])"


def _pick(rank: int, product: ProductScore, quotes: list[ShownQuote], check: _QuoteCheck, ranking: RankingResult,
          price: ShownPrice, care: list[ShownCareTip], availability: ShownAvailability = NOT_CHECKED,
          cautions: list[str] | None = None) -> Pick:
    warnings = product.credible_warnings
    return Pick(
        rank=rank,
        product_key=product.key,
        name=product.name,
        reason=_reason(product, ranking),
        support=_support(product),
        quotes=quotes,
        downsides=check.first(_naming_first(warnings), DOWNSIDES_PER_PICK),
        disagreement=DISAGREEMENT.format(voices=_plural(len(warnings), "credible voice")) if product.disputed else None,
        score=product.score,
        breakdown=product.breakdown,
        price=price,
        availability=availability,
        care=care,
        cautions=cautions or [],
    )


def _care_tips(tips: CareTips | None, check: _QuoteCheck) -> list[ShownCareTip]:
    """Up to CARE_TIPS_PER_PICK care tips for one pick, the ones most credible writers agree on first, repairs last
    (engine.care_tips.tips_by_agreement, 10 Oct 2026). Each tip shown stands for one group of tips that say the same
    thing, so the same advice is never shown twice: the group's best writer's tip, in their words, with their quote.
    When that quote fails the check, it is dropped and the group's next writer's tip and quote take its place."""
    if tips is None:
        return []
    shown: list[ShownCareTip] = []
    for group in tips_by_agreement(tips):
        if len(shown) == CARE_TIPS_PER_PICK:
            break
        for item in group:
            quote = check.first([item], 1)
            if quote:
                tip = _as_sentence(item.tip)
                shown.append(ShownCareTip("" if _same_words(tip, quote[0].text) else tip, quote[0]))
                break
    return shown


def _as_sentence(tip: str) -> str:
    """A tip as a short sentence: "descale every 6 months" -> "Descale every 6 months.". Only the first letter and the
    full stop change: the words stay the AI's."""
    tip = tip.strip()
    tip = tip[:1].upper() + tip[1:]
    return tip if tip.endswith((".", "!", "?")) else tip + "."


def _reason(product: ProductScore, ranking: RankingResult) -> str:
    """The one-line reason: how many credible voices, how many after long-term use, how many talk about the request's
    needs, and the kind if it leads."""
    recommendations = product.credible_recommendations
    long_term = sum(m.evidence == "long-term use" for m in recommendations)
    has_bonus = product.breakdown.kind_bonus > 0 and ranking.leading_kind is not None
    return REASON.format(
        voices=_plural(len(recommendations), "credible voice"),
        long_term=REASON_LONG_TERM.format(n=long_term) if long_term else "",
        needs=_needs_clause(recommendations, [m.needs for p in ranking.products for m in p.mentions]),
        kind=REASON_KIND.format(kind=ranking.leading_kind.name) if has_bonus else "",
    )


def _needs_clause(recommendations: list[ScoredMention], every_list: list[tuple[str, ...]]) -> str:
    """", 3 of them about sensitive skin": how many credible recommendations talk about the request's needs, and which
    needs, in the request's order; "" when none does. `every_list` holds the needs of every mention ranked: each lists
    them in the request's order, so together they show that order.

    Nothing is said twice: long-term use talks about "lasting" (engine/needs.py), and the reason already says how many
    recommendations come after long-term use, so those don't count again for "how long it lasts".
    """
    fitting = [needs for needs in map(_needs_not_said, recommendations) if needs]
    if not fitting:
        return ""
    mine = {need for needs in fitting for need in needs}
    ordered = [need for need in _in_request_order(fitting + every_list) if need in mine]
    named = list(dict.fromkeys(NEED_LABELS.get(need, need) for need in ordered))
    listed = NEEDS_JOIN.join(named[:-1]) + NEEDS_JOIN_LAST + named[-1] if len(named) > 1 else named[0]
    return REASON_NEEDS.format(n=len(fitting), needs=listed)


def _needs_not_said(mention: ScoredMention) -> tuple[str, ...]:
    """A mention's needs, less "lasting" when it comes after long-term use: the reason says that already."""
    return tuple(need for need in mention.needs if not (need == LASTING and mention.evidence == "long-term use"))


def _in_request_order(lists: list[tuple[str, ...]]) -> list[str]:
    """Every need of the lists once, in the request's order. Each list keeps that order but may skip needs (one
    mention talks about "sensitive" only, another about "beginner" and "sensitive"), so a need goes next when no other
    need left comes before it in any list. Needs no list puts in order keep the order they were first seen in."""
    left = list(dict.fromkeys(need for needs in lists for need in needs))
    before = {(a, b) for needs in lists for i, a in enumerate(needs) for b in needs[i + 1:]}
    ordered = []
    while left:
        first = next((n for n in left if not any((other, n) in before for other in left)), left[0])
        ordered.append(first)
        left.remove(first)
    return ordered


def _support(product: ProductScore) -> str:
    """How many high- and medium-credibility voices recommend it, across how many threads."""
    recommendations = product.credible_recommendations
    counts = {level: sum(m.voice == level for m in recommendations) for level in ("high", "medium")}
    voices = [_plural(n, f"{level}-credibility voice") for level, n in counts.items() if n]
    return SUPPORT.format(voices=" and ".join(voices), threads=_plural(product.breakdown.credible_threads, "thread"))


def _skip_item(product: ProductScore, check: _QuoteCheck) -> SkipItem | None:
    """A skip-these entry with its verified warnings, or None when no warning quote passes the check."""
    quotes = check.first(_naming_first(product.credible_warnings), QUOTES_PER_SKIPPED_PRODUCT)
    if not quotes:
        return None
    praised = len(product.credible_recommendations)
    reason = SKIP_REASON.format(
        voices=_plural(len(product.credible_warnings), "credible voice"),
        praised=SKIP_ALSO_PRAISED.format(voices=_plural(praised, "credible voice")) if praised else "",
    )
    return SkipItem(product.key, product.name, reason, quotes)


def _look_for(ranking: RankingResult, check: _QuoteCheck) -> list[LookFor]:
    """Up to LOOK_FOR_NOTES kinds, strongest credible advice first, each with its strongest verified note.

    A kind with positive support gets "Look for" and a recommending note; negative support gets "Avoid" and a
    warning note. A kind whose support is zero (no credible notes, or as many for as against) gives no advice. A
    comment already shown for another kind's same advice isn't shown again (10 Oct 2026): the kind takes its next
    credible note, or, with none, joins that line ("Look for: Cast iron or Carbon steel").
    """
    items: list[LookFor] = []
    item_notes: list[list[KindNote]] = []  # each item's kind's credible notes, strongest first
    for kind in sorted(ranking.kinds, key=lambda k: -abs(k.support)):  # sorted keeps ties in the ranking's order
        if len(items) == LOOK_FOR_NOTES:
            break
        if kind.support == 0:
            continue
        stance, advice = ("recommend", LOOK_FOR) if kind.support > 0 else ("warn", AVOID)
        notes = _most_credible_first([n for n in ranking.kind_notes
                                      if n.kind_key == kind.key and n.stance == stance and is_credible(n)])
        used = {item.quote.comment_id: i for i, item in enumerate(items) if item.advice == advice}
        quote = check.first([n for n in notes if n.comment_id not in used], 1)
        if not quote:
            # Only comments already shown back this kind: the kind holding one takes another note if it has one,
            # and this kind takes the shared comment; otherwise the two kinds share one line.
            for shared in check.first([n for n in notes if n.comment_id in used], len(notes)):
                holder = used[shared.comment_id]
                other = check.first([n for n in item_notes[holder] if n.comment_id not in used], 1)
                if other:
                    items[holder].quote, quote = other[0], [shared]
                    break
            else:
                shared = check.first([n for n in notes if n.comment_id in used], 1)
                if shared:
                    items[used[shared[0].comment_id]].kind += f" or {kind.name}"
                continue
        if quote:
            items.append(LookFor(kind.name, advice, quote[0]))
            item_notes.append(notes)
    return items


def _message(picks: int, product_type: str | None) -> str | None:
    """The honest message when fewer than 3 products have enough evidence, or None when there are 3."""
    if picks >= PICKS_SHOWN:
        return None
    rule = RULE.format(mentions=MIN_CREDIBLE_MENTIONS, threads=MIN_THREADS)
    if picks == 0:
        return NO_PICKS.format(what=f"any {product_type}" if product_type else "a product", rule=rule)
    return FEWER_PICKS.format(products=_plural(picks, "product"), rule=rule, n=picks, wanted=PICKS_SHOWN)


def shown_price(check: PriceCheck | None) -> ShownPrice:
    """A product's price as the shopper sees it: amount, shop and date when known, and how it meets the budget."""
    budget_status = None if check is None or check.status == "no budget" else check.status
    budget_note = _budget_note(check) if budget_status else None
    price = check.price if check is not None else None
    if price is None:
        return ShownPrice(PRICE_UNKNOWN, None, None, None, None, None, budget_status, budget_note)
    text = PRICE.format(amount=_money(price.price, price.currency), shop=price.shop, date=_day(price.checked_on))
    url = price.url if price.url.startswith("https://") else None  # the price list allows https only; checked again
    return ShownPrice(text, price.price, price.currency, price.shop, url, price.checked_on.isoformat(),
                      budget_status, budget_note)


def shown_availability(check: PriceCheck | None, price_url: str | None = None) -> ShownAvailability:
    """Whether a product is sold, as the shopper sees it: the shop and the day it was checked, when the price list says.

    The shop's link is passed on only when it is https, and only when the price line (whose link is `price_url`)
    doesn't already link to the same page. A product sold second-hand only says so (AVAILABILITY_SECOND_HAND).
    """
    sold = check.availability if check is not None else None
    if sold is None or sold.available is None:
        return NOT_CHECKED
    day = _day(sold.checked_on)
    if sold.available is False:
        return ShownAvailability(AVAILABILITY_GONE.format(date=day), False, sold.shop, None,
                                 sold.checked_on.isoformat())
    url = sold.url if sold.url.startswith("https://") and sold.url != price_url else None  # https only; checked again
    wording = AVAILABILITY_SECOND_HAND if sold.second_hand else AVAILABILITY
    return ShownAvailability(wording.format(shop=sold.shop, date=day), True, sold.shop, url,
                             sold.checked_on.isoformat(), sold.second_hand)


def _budget_note(check: PriceCheck) -> str:
    """How the price meets the budget, in words: within it, or why it wasn't checked against it."""
    most = _money(check.budget.max, check.budget.currency)
    if check.status == "within":
        return BUDGET_WITHIN.format(max=most)
    why = {
        "unknown": BUDGET_WHY_UNKNOWN,
        "other currency": BUDGET_WHY_CURRENCY.format(currency=check.price.currency if check.price else ""),
        "out of date": BUDGET_WHY_OLD.format(days=PRICE_MAX_AGE_DAYS),
    }[check.status]
    return BUDGET_NOT_CHECKED.format(max=most, why=why)


def _money(amount: float, currency: str) -> str:
    """£120, £119.99, €1,200: whole amounts without pennies."""
    number = f"{amount:,.0f}" if amount == int(amount) else f"{amount:,.2f}"
    return CURRENCY_SIGNS.get(currency, currency + " ") + number


def _day(day: date) -> str:
    """9 Oct 2026."""
    return f"{day.day} {day:%b %Y}"


def _plural(n: int, noun: str) -> str:
    """'1 thread', '3 threads'."""
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


# --- The automated check: no claim without a verified quote ---

def unverified_claims(answer: Answer, bodies: Mapping[str, str]) -> list[str]:
    """Every problem with a finished answer's quotes, in words; an empty list means every claim is backed.

    Checks that each quote shown (care tips' included) is found word for word in its comment as it is now, isn't
    from a quoted block, and matches at most QUOTE_MAX_WORDS words, that each pick has at least MIN_QUOTES_PER_PICK
    quotes, and that each skip-these product has at least one. The problems name the comment, never the failed
    quote's words.
    """
    problems = []
    for where, quote in _every_quote(answer):
        problem = _quote_problem(quote.text, quote.comment_id, bodies)
        if problem:
            problems.append(f"{where}: {problem}")
    for pick in answer.picks:
        if len(pick.quotes) < MIN_QUOTES_PER_PICK:
            problems.append(f"pick {pick.rank} ({pick.name}): {len(pick.quotes)} quote(s); a pick needs {MIN_QUOTES_PER_PICK}")
    for item in answer.skip:
        if not item.quotes:
            problems.append(f"skip-these ({item.name}): no quote backs the warning")
    return problems


def shown_quotes(answer: Answer) -> list[ShownQuote]:
    """Every quote the answer shows: its picks' quotes, downsides and care tips, "what to look for" and the skip list.
    The evaluation counts them (engine/slice_eval.py)."""
    return [quote for _, quote in _every_quote(answer)]


def _every_quote(answer: Answer) -> Iterator[tuple[str, ShownQuote]]:
    """Each quote in the answer, with where it is shown."""
    for pick in answer.picks:
        for quote in pick.quotes:
            yield f"pick {pick.rank} ({pick.name})", quote
        for quote in pick.downsides:
            yield f"pick {pick.rank} ({pick.name}) downside", quote
        for item in pick.care:
            yield f"pick {pick.rank} ({pick.name}) care tip", item.quote
    for item in answer.look_for:
        yield f"what to look for ({item.kind})", item.quote
    for item in answer.skip:
        for quote in item.quotes:
            yield f"skip-these ({item.name})", quote


# --- Rendering as text (markdown) ---

def render_markdown(answer: Answer) -> str:
    """The answer as markdown text, readable as plain text too."""
    title = TITLE.format(product_type=answer.product_type) if answer.product_type else TITLE_ANY
    lines = [f"# {title}", ""]
    if answer.message:
        lines += [answer.message, ""]
    for pick in answer.picks:
        lines += _render_pick(pick)
    if answer.look_for:
        lines += [f"## {LOOK_FOR_HEADING}", ""]
        for item in answer.look_for:
            lines.append(f"- **{item.advice}: {item.kind}.** {_render_quote_inline(item.quote)}")
        lines.append("")
    if answer.skip:
        lines += [f"## {SKIP_HEADING}", ""]
        for item in answer.skip:
            lines.append(f"- **{item.name}:** {item.reason}")
            lines += [f"  - {_render_quote_inline(quote)}" for quote in item.quotes]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_pick(pick: Pick) -> list[str]:
    lines = [f"## {pick.rank}. {pick.name}", ""]
    if pick.model:
        price = f" ({pick.model_price})" if pick.model_price else ""
        lines += [BRAND_PICK_MODEL.format(model=pick.model) + price, ""]
    lines += [pick.reason, "", f"**{SUPPORT_LABEL}:** {pick.support}", ""]
    lines += _render_price(pick.price) + _render_availability(pick.availability)
    for caution in pick.cautions:
        lines += [caution, ""]
    if pick.disagreement:
        lines += [f"**{pick.disagreement}**", ""]
    lines += [f"**{QUOTES_HEADING}**", ""]
    for quote in pick.quotes:
        lines += _render_quote_block(quote)
    lines += [f"**{DOWNSIDES_HEADING}**", ""]
    if pick.downsides:
        for quote in pick.downsides:
            lines += _render_quote_block(quote)
    else:
        lines += [NO_DOWNSIDES, ""]
    if pick.care:
        lines += [f"**{CARE_HEADING}**", ""]
        lines += [f"- **{item.tip}** {_render_quote_inline(item.quote)}" if item.tip
                  else f"- {_render_quote_inline(item.quote)}" for item in pick.care] + [""]
    lines += [f"**{BREAKDOWN_HEADING}**", ""] + _render_breakdown(pick.score, pick.breakdown) + [""]
    return lines


def _render_price(price: ShownPrice) -> list[str]:
    """The price line (with the shop's link when there is one) and the budget line, if any."""
    if price.amount is None:
        line = price.text
    else:
        link = f" · [{PRICE_LINK_TEXT}]({price.url})" if price.url else ""
        line = f"**{PRICE_LABEL}:** {price.text}{link}"
    return [line, ""] + ([price.budget_note, ""] if price.budget_note else [])


def _render_availability(availability: ShownAvailability) -> list[str]:
    """The availability line, with the shop's link when there is one."""
    link = f" · [{PRICE_LINK_TEXT}]({availability.url})" if availability.url else ""
    return [f"{availability.text}{link}", ""]


def _one_line(text: str) -> str:
    """The quote on one line: line breaks and runs of spaces become one space (formatting, not words)."""
    return " ".join(text.split())


def _render_quote_block(quote: ShownQuote) -> list[str]:
    credit = " · ".join(quote.badges + (f"[{LINK_TEXT}]({quote.url})",))
    return [f'> "{_one_line(quote.text)}"', f"> — {credit}", ""]


def _same_words(a: str, b: str) -> bool:
    """Whether two texts say the same words, capitals and punctuation aside (10 Oct 2026: a care tip that only
    repeats its quote is shown once)."""
    words = lambda text: re.findall(r"[a-z0-9]+", text.lower())
    return words(a) == words(b)


def _render_quote_inline(quote: ShownQuote) -> str:
    credit = " · ".join(quote.badges + (f"[{LINK_TEXT}]({quote.url})",))
    return f'"{_one_line(quote.text)}" ({credit})'


def _render_breakdown(score: float, b: ScoreBreakdown) -> list[str]:
    """The score breakdown as a list, signal by signal."""
    total = f"- Score {score:.2f} = {b.mention_points:.2f} from mentions"
    if b.kind_bonus:
        total += f" + {b.kind_bonus:.2f} kind bonus ({b.kind}, support {b.kind_support:.2f})"
    lines = [
        total,
        f"- Recommendations: {b.recommends}, {b.credible_recommends} credible. "
        f"Voices: {_levels(b.recommend_voices)}. Evidence: {_levels(b.recommend_evidence)}.",
        f"- Warnings: {b.warnings}, {b.credible_warnings} credible. "
        f"Voices: {_levels(b.warn_voices)}. Evidence: {_levels(b.warn_evidence)}.",
        f"- Neutral mentions: {b.neutral} (they never count)",
        f"- Threads: {b.threads}, {b.credible_threads} with a credible recommendation",
    ]
    if b.credible_recommends_fitting_need or b.credible_warnings_fitting_need:
        lines.append("- " + breakdown_needs_line(b.credible_recommends_fitting_need, b.credible_warnings_fitting_need))
    if b.kind and not b.kind_bonus:
        lines.append(f"- Kind: {b.kind} (support {b.kind_support:.2f}; no bonus: it doesn't lead by far)")
    return lines


def breakdown_needs_line(recommends: int | str, warnings: int | str) -> str:
    """The breakdown's line about the request's needs. The numbers may be given as placeholders ("{recommends}"):
    the web page fills them in."""
    return BREAKDOWN_NEEDS.format(recommends=recommends, warnings=warnings, boost=f"{NEED_MATCH_BOOST:g}")


def _levels(counts: dict[str, int]) -> str:
    """{"high": 2, "medium": 1, "low": 0} as "2 high, 1 medium, 0 low"."""
    return ", ".join(f"{n} {level}" for level, n in counts.items())
