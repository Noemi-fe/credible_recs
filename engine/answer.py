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
- "How to take care of it" (Noemi, 9 Oct 2026; named so on 11 Oct 2026, and since then only the pick's own tips, the
  tips about its kind of product being shown once, in a note at the end): up to CARE_TIPS_PER_PICK credible care tips
  ("descale every 6 months"), each with its verified quote. Since 10 Oct 2026 (decided by Claude, as Noemi asked) the advice
  most credible writers agree on comes first and repairs ("smooth with an angle grinder") last; tips that say the same
  thing are shown once, in their best writer's words (engine.care_tips.tips_by_agreement). A pick with no tip has no
  such heading.
- cautions (product facts, decided by Claude, 9 Oct 2026): when a checked fact suits the request less well by a soft
  rule (engine/product_facts.py: a rich moisturiser for oily skin), "Note: <the reason>." under the pick's price lines.
  Products whose facts clash by a hard rule never get here: the pipeline leaves them out.
- "In short:" (Noemi's decision 4 of 13 Oct 2026, to try and judge): a one-line summary of what its credible voices
  say, in our words, written ahead of time (engine/summaries.py, data/library/summaries.json). It is shown only when
  every check passes: its text (one sentence, at most SUMMARY_MAX_WORDS words, no quotation marks), every comment it
  cites is one of the pick's credible mentions in this answer and its quote passes the word-for-word check, its numbers
  are in those comments, and it acknowledges a downside when the pick has credible warnings. It carries the verified
  quotes of the comments it cites (`sources`, not shown), so they are checked again, live too, like every quote.
- its form (13 Oct 2026), in an answer to a request that names an active ingredient but no product type ("salicylic
  acid for acne"): "Form: pads", "Form: cleanser" (engine.ingredients.form_of), since such an answer shows several
  types of product side by side. The title then says the ingredient ("Top picks: salicylic acid products"), and a note
  under it says what every product shown has in common: it contains the ingredient, by its maker's list of actives or
  its own name (INGREDIENT_NOTE_LED). A request naming a type and an ingredient gets "Top picks: cleanser with salicylic
  acid" and its own note (INGREDIENT_NOTE).
Under the picks: "Also worth a look" (Noemi's decision 2 of 13 Oct 2026): up to WORTH_A_LOOK_SHOWN products with two
credible recommendations across two threads (engine.rank), in their own section, labelled as less supported (WORTH_NOTE).
Each shows its reason line, price, cautions, one or two verified quotes that say something about it (never a bare
mention, a garbled quote or one leaning on the thread: there is no minimum to make up), and known downsides only when
credible voices warn against it; an item with no such quote gives its place to the next. They are never picks. Then
"what to look for" (a short blueprint from credible notes about kinds of product), the skip-these list, and an honest
message when fewer than 3 products have enough evidence.

Sense (Noemi's note, 12 Oct 2026: "some reccs make little sense"; measured by engine/sense_eval.py). Every quote passed
the word-for-word check, yet "retinol for a beginner" showed "Look for: retinol" with a writer's shrug for its quote,
and a pick's quote was a reply ("Yes!") whose "it" only the comment above explained. So:
- a quote that doesn't stand on its own (_standing: it never names what it is about and leans on "it", "this", "they"
  or a reply word, or is very short; or it leans on something said before it, "both of them", "for that reason") is
  shown with the sentences before it in its comment, back to the one that names what it is about, as one stretch of the
  comment's own text, within QUOTE_MAX_WORDS (_widened). A quote that still leans on the thread, or on someone or
  something the comment doesn't show ("he said", "the same experience", "as you said"), comes after every quote that
  stands: it is shown only to make up a pick's two quotes, or when a downside or a skipped product has no other;
- a quote that only mentions the product ("I have one") is never more than a pick needs;
- "What to look for" never shows the product asked for itself ("retinol" for a retinol request), nor advice named after
  another type of product (skincare and haircare: "eye creams" for a moisturiser; a type the open model named: another
  listed type, or "an immersion blender" for a blender); each line's quote names its kind and states advice about it,
  not a hedge, a wish or a question, and not the opposite of what the request asks; an "Avoid" line never quotes a
  warning about one of the answer's own picks. A kind with no such note is left out. Kinds whose name or notes name the
  product asked for come first (_look_for).

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
- a care tip is a verified quote, or nothing: one that fails gives its place to the next tip;
- an "Also worth a look" item needs at least 1 verified quote, or it is left out;
- a summary needs every quote it cites to pass, or it isn't shown, and it is never a quote itself.
unverified_claims() runs the same checks over a finished answer, as an automated proof.

The wording users see is in the constants below, marked PROPOSED (it waits for Noemi) or decided by Claude (Noemi
asked Claude to decide wording and report it).
"""

import dataclasses
import re
from collections.abc import Callable, Collection, Iterable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from datetime import date

from engine.care_tips import CareTip, CareTips, is_repair, similar_tips, tips_by_agreement
from engine.config import (
    BRAND_PICK_MODEL,
    CARE_NOTE_TIPS,
    CARE_TIPS_PER_PICK,
    DOWNSIDES_PER_PICK,
    LOOK_FOR_NOTES,
    OPPOSITE_QUOTE_PATTERNS,
    OTHER_KIND_WORDS,
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
    WORTH_A_LOOK_CREDIBLE,
    WORTH_A_LOOK_QUOTES,
    WORTH_A_LOOK_SHOWN,
)
from engine.extract import _as_written, _in_quoted_block, _own_words_in_quote_format
from engine.group_kinds import PURPOSE_WORDS, _kind_words, kind_parts
from engine.ingredients import (
    TYPE_OWN_INGREDIENT, find_ingredients, form_kind, form_of, ingredient_type_name, ingredients_of_type, talk_words,
)
from engine.models import Thread
from engine.needs import LASTING, Need, needs_met
from engine.prices import PriceCheck
from engine.credibility import GENERIC_NAME_WORDS
from engine.match_products import FILLER_WORDS, known_aliases
from engine.rank import KindNote, ProductScore, RankingResult, ScoredMention, ScoreBreakdown, is_credible
from engine.query import PRODUCT_TYPES
from engine.sources import mentions_product
from engine.summaries import Summary, shown_problems, summary_key, text_problems
from engine.text import one_edit_apart
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
# Known downsides in proportion (Noemi, 12 Oct 2026: a single warning under many long-term recommendations read as if it
# outweighed them). Shown above a pick's downsides; wording from her own example, decided by Claude.
DOWNSIDES_SHARE = "{n} of {total} credible voices warned against it:"
SUPPORT_LABEL = "Credible support"
BREAKDOWN_HEADING = "Score breakdown"  # off the answer card since 12 Oct 2026 (Noemi); kept in the JSON
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
# Care tips (Noemi, 9 Oct 2026). Renamed by Noemi on 11 Oct 2026 (was "How to make it last"): only care of the product
# itself. A pick shows the tips about itself; tips about its kind of product are shown once, in a note at the end
# (CARE_NOTE_HEADING, filled with the request's product type; CARE_NOTE_HEADING_ANY without one).
CARE_HEADING = "How to take care of it"
CARE_NOTE_HEADING = "How to take care of your {product_type}"
CARE_NOTE_HEADING_ANY = "How to take care of it"
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
# Also worth a look (Noemi's decision 2 of 13 Oct 2026; wording decided by Claude). The note under the heading says how
# much less support its products have: "2 credible voices each: less evidence than the picks above, which need at least
# 3 credible recommendations across at least 2 threads." With no picks above, WORTH_NOTE_NO_PICKS.
WORTH_HEADING = "Also worth a look"
WORTH_NOTE = "{voices} each: less evidence than the picks above, which need {rule}."
WORTH_NOTE_NO_PICKS = "{voices} each: less evidence than a pick needs ({rule})."
# One-line summaries (Noemi's decision 4 of 13 Oct 2026; wording decided by Claude): shown under a pick's name as
# "In short: <summary>", with the note saying it is ours and not a quote.
SUMMARY_LABEL = "In short:"
SUMMARY_NOTE = "Our summary of what its credible voices say, not a quote."
# Active ingredients (13 Oct 2026; wording decided by Claude). The title of an answer to a request naming an ingredient
# and no type, and of one naming both; the note under the title; the label of each product's form.
TITLE_INGREDIENT_LED = "Top picks: {ingredient} products"
TITLE_WITH_INGREDIENT = "Top picks: {product_type} with {ingredient}"
# Since Noemi's decision 1 of 13 Oct 2026 an ingredient-led answer shows leave-on forms only, or the forms the request
# names (INGREDIENT_NOTE_FORMS), and its note says how to see a cleanser.
INGREDIENT_NOTE_LED = ("Every product here contains {ingredient}: its maker's list of actives or its own name says "
                       "so. All are leave-on forms, each shown with it; for a cleanser or another rinse-off form, ask "
                       "for it by name (\"{ingredient} cleanser\").")
INGREDIENT_NOTE_FORMS = ("Every product here contains {ingredient}: its maker's list of actives or its own name says "
                         "so, and its form is the one you asked for ({forms}).")
INGREDIENT_NOTE = ("Every {product_type} here contains {ingredient}: its maker's list of actives or its own name says "
                   "so.")
FORM_LABEL = "Form"


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


@dataclass(frozen=True)
class ShownSummary:
    """A one-line summary that passed every check (engine/summaries.py): our words, never shown as a quote."""

    text: str
    # The verified quotes of the comments it cites, in its order: not shown, but checked word for word again (and live)
    # like every quote, so a summary never stands on a comment deleted or changed since.
    sources: tuple[ShownQuote, ...]


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
    care: list[ShownCareTip] = field(default_factory=list)  # "How to take care of it": the pick's own tips only
    cautions: list[str] = field(default_factory=list)  # "Note: ..." from product facts (9 Oct 2026); empty when none
    # For a brand pick: the model of that brand its credible writers recommend most (10 Oct 2026); None otherwise.
    model: str | None = None
    model_price: str | None = None  # that model's checked price, as the price line words it; None when not checked
    # How many credible voices warned against it, of all who spoke for or against it (DOWNSIDES_SHARE, 12 Oct 2026);
    # None when no downside is shown.
    downsides_share: str | None = None
    summary: ShownSummary | None = None  # "In short:" (13 Oct 2026); None when it has none, or one that fails a check
    form: str | None = None  # its form in an ingredient-led answer ("pads"; 13 Oct 2026); None otherwise
    # The credible voices behind it as numbers, for the page's credibility meter (13 Oct 2026, the UX builder; _voices):
    # {"recommend", "high", "medium", "warn", "threads"}, the writers its reason, support and share lines count.
    voices: dict[str, int] = field(default_factory=dict)


@dataclass
class WorthALook:
    """A product under "Also worth a look" (Noemi, 13 Oct 2026): less supported than a pick, shown apart."""

    product_key: str
    name: str
    reason: str  # "Recommended by 2 credible voices, 1 of them after long-term use."
    quotes: list[ShownQuote]  # 1 or 2, each saying something about it
    downsides: list[ShownQuote]  # from credible warnings; empty when there are none
    downsides_share: str | None  # "1 of 3 credible voices warned against it:", or None without downsides
    disagreement: str | None
    score: float
    breakdown: ScoreBreakdown
    price: ShownPrice
    availability: ShownAvailability = NOT_CHECKED
    cautions: list[str] = field(default_factory=list)
    summary: ShownSummary | None = None
    form: str | None = None  # as a pick's
    voices: dict[str, int] = field(default_factory=dict)  # as a pick's (13 Oct 2026, the UX builder)


@dataclass
class SkipItem:
    product_key: str
    name: str
    reason: str
    quotes: list[ShownQuote]  # credible warnings, at least 1
    form: str | None = None  # as a pick's


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
    # Care tips about the kind of product, shown once at the end (Noemi, 11 Oct 2026); empty when there are none.
    care_note: list[ShownCareTip] = field(default_factory=list)
    # "Also worth a look" (Noemi, 13 Oct 2026): best first, after the picks; and the note under its heading, or None
    # when there are none.
    worth_a_look: list[WorthALook] = field(default_factory=list)
    worth_note: str | None = None
    # The active ingredients the request names, as shown ("salicylic acid"; 13 Oct 2026), and the note under the title
    # saying every product shown contains them; None for a request naming none.
    ingredient: str | None = None
    ingredient_note: str | None = None
    title: str = ""  # the answer's title, as shown ("Top picks: salicylic acid products")


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
                 asks: tuple[str, ...] = (), model_prices: Mapping[str, str] | None = None,
                 more_downsides: Mapping[str, list[ScoredMention]] | None = None,
                 unsuited_kinds: Collection[str] = (), needs: tuple[Need, ...] = (), request: str = "",
                 summaries: Mapping[str, Summary] | None = None, worth_left_out: Collection[str] = (),
                 ingredient: str | None = None, forms: Mapping[str, str | None] | None = None,
                 forms_asked: Collection[str] = ()) -> Answer:
    """The answer for one request, from its ranking and the current text of its comments ({comment id: body}).

    `prices` is each product's price check ({product key: engine.prices.PriceCheck}), made by the pipeline; a product
    with none shows PRICE_UNKNOWN and AVAILABILITY_UNKNOWN. `care` is each product's care tips ({product key:
    engine.care_tips.CareTips}), made by the pipeline; a product with none shows no "How to take care of it". Care tips
    never change which products are picks. `cautions` is each product's soft clashes with the request ({product key:
    [reason]}, engine/product_facts.py), made by the pipeline: each is shown on its pick as CAUTION; they never change
    which products are picks either. `models` is each brand pick's most recommended model ({product key: name}),
    made by the pipeline (engine.pipeline._brand_models), shown as BRAND_PICK_MODEL, with that model's checked price
    from `model_prices` ({product key: price line}) when there is one: shown only, never a reason to leave the brand
    out. `asks` is what the request asks
    for (engine.product_facts.request_asks): a quote saying the opposite is shown last. `more_downsides` ({pick key:
    credible warnings}) are warnings about a pick's own brand or line, shown under it after its own. `unsuited_kinds`
    are the keys of kinds that give no "Look for" (engine.pipeline._unsuited_kinds). `needs` (engine.needs.request_needs):
    among equally clear quotes, those talking about them come first. `request` is the request as typed: the product it
    names ("retinol") is no advice about what to look for. `summaries` ({engine.summaries.summary_key: Summary}) are
    the one-line summaries written ahead of time: each is shown on its pick or item only when every check passes.
    `worth_left_out` are the keys of products the pipeline leaves out of "Also worth a look" (its brand rules).
    `ingredient` names the active ingredients the request asks for (13 Oct 2026; every product here contains them, the
    pipeline made sure), and `forms` is each product's form ({product key: form}) in an ingredient-led answer;
    `forms_asked` the forms an ingredient-led request names ("salicylic acid wash": cleanser), for its note.
    """
    check = _QuoteCheck(bodies)
    forms = forms or {}
    models = models or {}
    prices = prices or {}
    care = care or {}
    cautions = cautions or {}
    summaries = summaries or {}
    picks: list[Pick] = []
    for product in ranking.qualifying:
        if len(picks) == PICKS_SHOWN:
            break
        quotes = _pick_quotes(product, check, asks, needs, product_type)
        if len(quotes) >= MIN_QUOTES_PER_PICK:
            price = shown_price(prices.get(product.key))
            availability = shown_availability(prices.get(product.key), price.url)
            own = care.get(product.key)
            tips = _care_tips(CareTips(own.own, []) if own else None, check)
            notes = [CAUTION.format(reason=reason) for reason in cautions.get(product.key, [])]
            picks.append(_pick(len(picks) + 1, product, quotes, check, ranking, price, tips, availability, notes,
                               (more_downsides or {}).get(product.key, []), needs))
            picks[-1].model = models.get(product.key)
            picks[-1].model_price = (model_prices or {}).get(product.key)
            picks[-1].summary = _summary(product, _summary_of(product, summaries), check)
            picks[-1].form = forms.get(product.key)
    worth = _worth_items(ranking, check, prices, cautions, summaries, worth_left_out, asks, needs, product_type)
    for item in worth:
        item.form = forms.get(item.product_key)
    skip = [_skip_item(product, check) for product in ranking.skip_list]
    for item in skip:
        if item is not None:
            item.form = forms.get(item.product_key)
    look_for = _look_for(ranking, check, product_type, unsuited_kinds, request, asks, [pick.name for pick in picks],
                         forms_asked)
    care_note = _care_note([care.get(pick.product_key) for pick in picks], picks, check)
    return Answer(
        category=ranking.category,
        product_type=product_type,
        picks=picks,
        look_for=look_for,
        skip=[item for item in skip if item is not None],
        message=_message(len(picks), product_type),
        needs_more_threads=len(picks) < PICKS_SHOWN,
        quotes_dropped=check.dropped,
        care_note=care_note,
        worth_a_look=worth,
        worth_note=_worth_note(len(picks)) if worth else None,
        ingredient=ingredient,
        ingredient_note=_ingredient_note(product_type, ingredient, forms_asked),
        title=answer_title(product_type, ingredient),
    )


def answer_title(product_type: str | None, ingredient: str | None = None) -> str:
    """The answer's title: "Top picks: chef knife"; with an active ingredient asked for (13 Oct 2026), "Top picks:
    salicylic acid products" when the request names no type, "Top picks: cleanser with salicylic acid" when it does."""
    if ingredient and ingredients_of_type(product_type):
        return TITLE_INGREDIENT_LED.format(ingredient=ingredient)
    if ingredient and product_type:
        return TITLE_WITH_INGREDIENT.format(product_type=product_type, ingredient=ingredient)
    return TITLE.format(product_type=product_type) if product_type else TITLE_ANY


def _ingredient_note(product_type: str | None, ingredient: str | None,
                     forms_asked: Collection[str] = ()) -> str | None:
    """The note under the title of an answer to a request naming an active ingredient (13 Oct 2026), or None."""
    if not ingredient:
        return None
    if forms_asked:
        return INGREDIENT_NOTE_FORMS.format(ingredient=ingredient, forms=" or ".join(forms_asked))
    if ingredients_of_type(product_type) or not product_type:
        return INGREDIENT_NOTE_LED.format(ingredient=ingredient)
    return INGREDIENT_NOTE.format(product_type=product_type, ingredient=ingredient)


# --- Also worth a look (Noemi's decision 2 of 13 Oct 2026) ---

def _worth_items(ranking: RankingResult, check: "_QuoteCheck", prices: Mapping[str, PriceCheck],
                 cautions: Mapping[str, list[str]], summaries: Mapping[str, Summary], left_out: Collection[str],
                 asks: tuple[str, ...], needs: tuple[Need, ...], product_type: str | None) -> list[WorthALook]:
    """Up to WORTH_A_LOOK_SHOWN products with two credible recommendations across two threads (ranking.worth_a_look),
    best first, those in `left_out` aside; each with its verified quotes (_worth_quotes), or left out without one."""
    items: list[WorthALook] = []
    for product in ranking.worth_a_look:
        if len(items) == WORTH_A_LOOK_SHOWN:
            break
        if product.key in left_out:
            continue
        quotes = _worth_quotes(product, check, asks, needs, product_type)
        if not quotes:
            continue
        downsides = _warning_quotes((product.credible_warnings,), check, DOWNSIDES_PER_PICK, needs)
        price = shown_price(prices.get(product.key))
        items.append(WorthALook(
            product_key=product.key,
            name=product.name,
            reason=_reason(product, ranking),
            quotes=quotes,
            downsides=downsides,
            downsides_share=_downsides_share(product) if downsides else None,
            disagreement=(DISAGREEMENT.format(voices=_plural(len(_warned(product)), "credible voice"))
                          if product.disputed else None),
            score=product.score,
            breakdown=product.breakdown,
            price=price,
            availability=shown_availability(prices.get(product.key), price.url),
            cautions=[CAUTION.format(reason=reason) for reason in cautions.get(product.key, [])],
            summary=_summary(product, _summary_of(product, summaries), check),
            voices=_voices(product),
        ))
    return items


def _worth_quotes(product: ProductScore, check: "_QuoteCheck", asks: tuple[str, ...], needs: tuple[Need, ...],
                  product_type: str | None) -> list[ShownQuote]:
    """Up to WORTH_A_LOOK_QUOTES verified quotes for an "Also worth a look" item, in a pick's order (_pick_quotes): each
    widened to stand on its own where its comment allows. Only quotes that say something about it: with no minimum to
    make up, a bare mention, a garbled quote, one that says nothing about it, one that still leans on the thread or one
    that starts mid-sentence (_mid_sentence) is never shown."""
    mentions, leaning = _standing(product.credible_recommendations, check.bodies, _names_its_product)
    ordered = _naming_first(_with_a_view(mentions, check.bodies), asks, needs, leaning, product_type)
    good = [m for m in ordered if m.comment_id not in leaning and _says_something(m)
            and not (_bare_mention(m) or _garbled(m.quote) or _mid_sentence(m.quote, check.bodies.get(m.comment_id)))]
    return check.first(good, WORTH_A_LOOK_QUOTES)


def _mid_sentence(quote: str, body: str | None) -> bool:
    """Whether a quote starts in the middle of a sentence of its comment: in lowercase, after words that don't end a
    sentence (one opening on its verb, its subject a link left out; 13 Oct 2026). Such a quote never names what it is
    about."""
    span = find_quote(body, quote) if body else None
    if span is None or not quote[:1].islower():
        return False
    before = body[:span[0]].rstrip()
    return bool(before) and not before.endswith((".", "!", "?", "…", ":", ";"))


def _worth_note(picks: int) -> str:
    """The note under "Also worth a look": how much less support its products have than a pick."""
    voices = _plural(WORTH_A_LOOK_CREDIBLE, "credible voice")
    rule = RULE.format(mentions=MIN_CREDIBLE_MENTIONS, threads=MIN_THREADS)
    return (WORTH_NOTE if picks else WORTH_NOTE_NO_PICKS).format(voices=voices, rule=rule)


# --- One-line summaries (Noemi's decision 4 of 13 Oct 2026) ---

def _summary_of(product: ProductScore, summaries: Mapping[str, Summary]) -> Summary | None:
    """The product's summary, saved under the category and the words of the name it is shown under (summary_key)."""
    return summaries.get(summary_key(product.mentions[0].category, product.name)) if product.mentions else None


def summary_reasons(product: ProductScore, summary: Summary | None, bodies: Mapping[str, str]) -> list[str]:
    """Why a product's summary can't be shown in this answer, in words; [] when it can. The checks of
    engine.summaries.shown_problems, against the product's credible mentions here, and each cited comment's quote checked
    word for word like every quote (_quote_problem). The reasons never repeat a quote."""
    if summary is None:
        return ["no summary yet"]
    credible = {m.comment_id: m for m in [*product.credible_recommendations, *product.credible_warnings]}
    reasons = shown_problems(summary, {cid: m.stance for cid, m in credible.items()}, bodies,
                             bool(product.credible_warnings))
    for cid in dict.fromkeys(summary.cites):
        if cid in credible and cid in bodies:
            problem = _quote_problem(credible[cid].quote, cid, bodies)
            if problem:
                reasons.append(f"cited {problem}")
    return reasons


def _summary(product: ProductScore, summary: Summary | None, check: "_QuoteCheck") -> ShownSummary | None:
    """The product's summary as shown, with the verified quotes of the comments it cites; None when it has none or one
    that fails a check (summary_reasons): then it is simply not shown, and the pick stays as it is."""
    if summary is None or summary_reasons(product, summary, check.bodies):
        return None
    credible = {m.comment_id: m for m in [*product.credible_recommendations, *product.credible_warnings]}
    cites = list(dict.fromkeys(summary.cites))
    sources = check.first([credible[cid] for cid in cites], len(cites))
    return ShownSummary(summary.text, tuple(sources)) if len(sources) == len(cites) else None


def _care_note(tips: Iterable[CareTips | None], picks: list[Pick], check: "_QuoteCheck") -> list[ShownCareTip]:
    """The note at the end of the answer (Noemi, 11 Oct 2026: tips about the kind of product were repeated under every
    pick): up to CARE_NOTE_TIPS tips about the kind, gathered once from the shown picks' tips, the ones most credible
    writers agree on first, and never one that says the same as a tip already shown under a pick."""
    kind: list[CareTip] = []
    for item in tips:
        for tip in item.kind if item is not None else []:
            if not any(other.comment_id == tip.comment_id and other.tip == tip.tip for other in kind):
                kind.append(tip)
    under_picks = [shown.tip or shown.quote.text for pick in picks for shown in pick.care]
    return _care_tips(CareTips([], kind), check, CARE_NOTE_TIPS, under_picks)


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
    """The text without the writer's bold, italics and strikethrough marks; an underscore inside a word stays. Marks
    Reddit's editor escaped ("\\*lot\\*") go too, never leaving "\\lot\\" (10 Oct 2026, late)."""
    text = _ESCAPED_MARK.sub(r"\1", text)
    for pattern in _EMPHASIS:
        text = pattern.sub(r"\1", text)
    return text


_ESCAPED_MARK = re.compile(r"\\([*_~])")


def _badges(item: ScoredMention | KindNote | CareTip) -> tuple[str, ...]:
    """Module 5's reasons in words; when it gave none, the plain levels ("medium-credibility voice", "short-term use")."""
    if item.badges:
        return item.badges
    plain = (BADGE_VOICE.format(voice=item.voice),)
    return plain + ((item.evidence,) if isinstance(item, ScoredMention) else ())


def _most_credible_first(items: Iterable[ScoredMention]) -> list[ScoredMention]:
    """Largest weight first; equal weights keep their order, so the result is always the same."""
    return sorted(items, key=lambda m: -abs(m.weight))


def _naming_first(items: Iterable[ScoredMention], asks: tuple[str, ...] = (),
                  needs: tuple[Need, ...] = (), leaning: Collection[str] = (),
                  product_type: str | None = None) -> list[ScoredMention]:
    """The most credible first, but the quotes that name their product and give a view before those that only name
    it, those before the ones that only give a view, and those before the rest; within each, those whose comment talks about what the request asks for first (10 Oct 2026: out of context, a line that only opens a list of other products the
    writer has had no trouble with says little, and so does a list of the grinders someone owns), and a quote that says the opposite of what
    the request asks ("does leave a white cast") after every other (_says_the_opposite). Each is still shown when
    there's room. Since 12 Oct 2026 the quotes of `leaning` (comment ids: quotes that lean on the thread, _standing) come
    after all of these, and a quote saying the product isn't really the `product_type` asked for (that it
    isn't really a moisturiser) counts as saying the opposite of the request (_not_the_type)."""
    ordered = _most_credible_first(items)

    # 0: names it and gives a view; 1: only names it; 2: only gives a view; 3: neither (10 Oct 2026, night: b04 showed a
    # writer still looking for a richer cream before one who swears by it, neither naming it).
    def tier(m: ScoredMention) -> int:
        names, view = _names_product(m.quote, m.product_name, m.category, m.written_as), _gives_a_view(m.quote)
        return 0 if names and view else 1 if names else 2 if view else 3

    # Within a tier, quotes that themselves talk about what the request asks for come first (10 Oct 2026, late: a kettle
    # pick led with a comment about its handle, not one of its writers' years of use). The quote, not its comment.
    def about_the_ask(m: ScoredMention) -> bool:
        return bool(needs and needs_met(m.quote, needs, m.evidence == "long-term use"))

    def opposite(m: ScoredMention) -> bool:
        return _says_the_opposite(m.quote, asks) or _not_the_type(m.quote, product_type)

    return sorted(ordered, key=lambda m: (m.comment_id in leaning, opposite(m), tier(m), not about_the_ask(m)))


def _not_the_type(quote: str, product_type: str | None) -> bool:
    """Whether a quote says its product isn't (really) the type of product asked for: "not a moisturizer", "I don't feel
    like it's a 'moisturizer'" (b04, 12 Oct 2026), by the type's name or one of module 1's names for it."""
    if not product_type:
        return False
    names = {product_type, *(k for p in PRODUCT_TYPES if p.name == product_type for k in p.keywords)}
    text = _plain(quote)
    return any(re.search(rf"(?:\bnot\b|n't\b)[^.!?]{{0,30}}?\b(?:an?|real|really)\W+{re.escape(name)}s?\b", text)
               for name in names)


def _says_something(m: ScoredMention) -> bool:
    """Whether a quote names its product, gives a view, or points at it ("it", "this one", "mine"). One that does none
    of these (b08, 10 Oct 2026: a one-line reply about sticking with cast iron was shown for two vintage brands; the
    comment named them in a sentence the AI didn't quote) is shown only to make up a pick's MIN_QUOTES_PER_PICK."""
    text = " ".join(re.findall(r"[a-z0-9']+", m.quote.lower().replace("’", "'")))
    return (_names_product(m.quote, m.product_name, m.category, m.written_as) or _gives_a_view(m.quote)
            or bool(_POINTS_AT_IT.search(text)))


# Words that point at a product already named ("I'm on my fifth bottle of it", "I've had mine for years").
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


def says_the_opposite(quote: str, asks: Iterable[str]) -> bool:
    """Whether the quote says the opposite of one of the request's asks (_says_the_opposite); the pipeline uses it too."""
    return _says_the_opposite(quote, asks)


def _says_the_opposite(quote: str, asks: Iterable[str]) -> bool:
    """Whether the quote says the opposite of one of the request's asks (config.OPPOSITE_QUOTE_PATTERNS): "it leaves a
    white cast" for "no white cast", "smells lovely" for "fragrance-free"."""
    text = " ".join(quote.lower().replace("’", "'").split())
    return any(re.search(pattern, text) for ask in asks for pattern in OPPOSITE_QUOTE_PATTERNS.get(ask, ()))


def _names_product(quote: str, name: str, category: str, written_as: str = "") -> bool:
    """Whether the quote names the product: the first word of its name (the brand), a model code in it (a word
    with a digit: "C2", "MTH-80"), or a known short or long form of its brand (engine/data/product_aliases.json:
    "BOJ" for Beauty of Joseon, "Breville" for Sage), as whole words, capitals aside. A plural or a possessive counts
    ("old wagners", "Prequel's"), and so does a hyphen written as a space or left out ("All clad" for All-Clad; b08,
    b05 and b10, 10 Oct 2026). So does the first word of the writer's own name for it (`written_as`; "my" or "the"
    aside, and never a common product word such as "gooseneck"): "Stagg" for a kettle shown as "Fellow Stagg EKG"
    (b06, 10 Oct 2026, night: its writers' quotes had stopped naming it once the shown name took its brand). A name that
    is an everyday short word too (COMMON_SHORT_WORDS: "TO" for The Ordinary) names it only in capitals (12 Oct 2026)."""
    text = " ".join(re.findall(r"[a-z0-9][a-z0-9'-]*", quote.lower().replace("’", "'")))
    name_words = _name_words(name)
    if not name_words:
        return False
    # The brand is the first word that isn't a filler word: "the" never names The Ordinary (12 Oct 2026).
    first = next((w for w in name_words if w not in FILLER_WORDS), name_words[0])
    wanted = {first} | {w for w in name_words if any(c.isdigit() for c in w)}
    writers = [w for w in _name_words(written_as) if w not in FILLER_WORDS]
    if writers and writers[0] not in GENERIC_NAME_WORDS:
        wanted.add(writers[0])
    joined = " ".join(name_words)
    for short_words, full_words in known_aliases().get(category, {}).items():
        short, full = " ".join(short_words), " ".join(full_words)
        if f"{joined} ".startswith(f"{short} ") or f"{joined} ".startswith(f"{full} "):
            wanted |= {short, full}
    common = {w for w in wanted if w in COMMON_SHORT_WORDS}  # named only in capitals: "TO", never "to"
    return (any(re.search(_as_written_loosely(w), text) for w in wanted - common)
            or any(re.search(rf"(?<![A-Za-z0-9]){re.escape(w.upper())}(?![A-Za-z0-9])", quote) for w in common))


# Short words a name for a product can be that are everyday words too: "TO" (The Ordinary, as a writer or a known short
# name has it) names it only in capitals, never "having to throw it away" (12 Oct 2026).
COMMON_SHORT_WORDS = frozenset({"to", "of", "in", "on", "at", "it", "is", "as", "an", "or", "by", "be", "do", "go", "so",
                                "up", "we", "me", "no", "if", "us", "am", "a", "i"})


def _name_words(name: str) -> list[str]:
    """A name's words as _names_product compares them: lowercase, a possessive "'s" dropped."""
    return [w.removesuffix("'s") for w in re.findall(r"[a-z0-9][a-z0-9'-]*", name.lower().replace("’", "'"))]


def _as_written_loosely(word: str) -> str:
    """A pattern for a name word (or a short name) as a whole word: its hyphens written as a space or not at all, and a
    plural or possessive ending allowed."""
    body = "[- ]?".join(re.escape(part) for part in word.split("-"))
    return rf"(?<![a-z0-9]){body}(?:'s|s'?|')?(?![a-z0-9])"


# --- Quotes that stand on their own (Noemi's note, 12 Oct 2026) ---

# Things a quote can lean on that the comment around it doesn't show: another person ("he said"), what someone else went
# through ("the same experience"), what the comment it answers or the post said ("as you said", "OP's budget"). The
# writer's own sentences can't explain them, so such a quote comes after every quote that stands on its own.
_ELSEWHERE = re.compile(
    r"\b(?:he|she|him|his|her|hers)\b"
    r"|\bsame (?:reaction|experience|thing|issue|problem|results?)\b"
    r"|\bthe reasons? (?:he|she|they|you) (?:said|gave|mentioned)\b"
    r"|\bas you (?:said|say|mentioned|found|noted|described)\b"
    r"|\bwhat you(?:'re| are) (?:wanting|after|describing)\b"
    r"|\byour problem\b|(?-i:\bOP(?:'s)?\b)", re.IGNORECASE)
# Things a quote can lean on that its writer said just before it: "both of them", "either product", "for that reason",
# "that part"; since 13 Oct 2026 "both in one" (a product holding two things the asker wanted, not shown). The
# sentences before it are shown with it, when they fit (_widened).
_BEFORE = re.compile(
    r"\bboth of them\b|\bwith both\b|\bboth in one\b|\beither (?:one|product|of them|if|is|was|will|would)\b"
    r"|\b(?:for|because of) (?:that|this|those|these) reasons?\b|\bthat (?:part|type)\b|\bonce i did that\b",
    re.IGNORECASE)
# A reply's first words ("Yes!", "Same.", "I agree, this is..."), and the words that stand for something named before.
_REPLY_OPENER = re.compile(r"^\W*(?:yes|yeah|yea|yep|yup|same|agreed|i agree|seconded|seconding|ditto|exactly|this|"
                           r"lol|haha|true|\+1)\b", re.IGNORECASE)
_POINTER = re.compile(r"(?<![a-z0-9'])(?:it|it's|its|this|these|those|they|they're|them|both|either|same|mine|"
                      r"that one|this one|the one)(?![a-z0-9'])")
SHORT_QUOTE_WORDS = 5  # fewer words, naming nothing, say too little alone ("This looks very cool!")
BARE_MENTION_WORDS = 5  # "I have a ballarini": fewer words, naming the product with no view, only makes up the minimum
# Where a stretch of a comment can't be widened to: a link, a bare address, a list, a heading, a table, code or a quoted
# block. Reddit shows these differently from how they are typed, so the live check (engine/live_check.py) couldn't find
# the words, and a quoted block is someone else's words.
_UNSHOWABLE = re.compile(r"\]\(|https?://|www\.|^\s*(?:[-*+]|\d+[.)])\s|^\s*#|^\s*(?:>|&gt;)|\||`", re.MULTILINE)
_SENTENCE_END = re.compile(r"[.!?…]+[\"'”’)\]]*\s+|\n+\s*")


def _plain(text: str) -> str:
    """The text in lowercase with straight apostrophes, for the patterns above."""
    return text.lower().replace("’", "'")


def _stands_alone(quote: str, names_it: bool) -> bool:
    """Whether a quote says what it is about without the thread: it leans on nothing said elsewhere or just before it,
    and either names what it is about or reads on its own (no reply opener, no "it" or "this" standing in for a name,
    and at least SHORT_QUOTE_WORDS words)."""
    if _ELSEWHERE.search(quote) or _BEFORE.search(quote):
        return False
    return names_it or not (_leans_without_a_name(quote) or _POINTER.search(_words(quote)))


def _leans_without_a_name(quote: str) -> bool:
    """Whether a quote that never names what it is about can't be read without the thread: it opens as a reply ("Yes!",
    "Same."), opens with a word standing for something named before ("It", "This", "They"), or is under
    SHORT_QUOTE_WORDS words ("This looks very cool!"). One that only has an "it" further on ("Love it, works great")
    reads well enough under its pick's name, so it keeps its place (10 Oct 2026)."""
    words = _words(quote)
    return bool(_REPLY_OPENER.match(_plain(quote)) or _POINTER.match(words) or len(words.split()) < SHORT_QUOTE_WORDS)


def _words(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9'+]+", _plain(text)))


def _widened(quote: str, body: str | None, names: Callable[[str], bool]) -> str | None:
    """The quote with the sentences before it in its comment, back to the nearest one from which the stretch names what
    it is about, as one stretch of the comment's own text (so it is still checked word for word, and live); None when
    there is no such sentence within QUOTE_MAX_WORDS words, the stretch would take in something Reddit shows differently
    from how it is typed (_UNSHOWABLE) or something said elsewhere (_ELSEWHERE), or the comment isn't at hand."""
    span = find_quote(body, quote) if body else None
    if span is None:
        return None
    start, end = span
    starts = {0} | {m.end() for m in _SENTENCE_END.finditer(body, 0, start)}
    for begin in sorted((s for s in starts if s < start), reverse=True):
        added = body[begin:start]
        if _UNSHOWABLE.search(added) or _in_quoted_block(body, (begin, start)):
            return None
        if len(_as_written(body, (begin, end)).split()) > QUOTE_MAX_WORDS:
            return None
        text = body[begin:end]
        if names(text) and not _ELSEWHERE.search(text):
            return text
    return None


def _standing(items: Iterable, bodies: Mapping[str, str], names: Callable[[str, object], bool],
              must_name: bool = False) -> tuple[list, set[str]]:
    """Each item (a mention or a note), its quote widened to the sentences before it when it doesn't stand alone and
    they make it (_widened); and the comment ids of those that still lean on the thread. `names(text, item)` says
    whether a text names what the item is about; with `must_name` (a note under its kind), a quote that doesn't is
    widened, or else leans, whatever else it says."""
    out, leaning = [], set()
    for item in items:
        names_it = names(item.quote, item)
        if not _stands_alone(item.quote, names_it) or (must_name and not names_it):
            wider = None if _ELSEWHERE.search(item.quote) else _widened(
                item.quote, bodies.get(item.comment_id), lambda text, item=item: names(text, item))
            if wider is not None:
                item = dataclasses.replace(item, quote=wider)
            elif _ELSEWHERE.search(item.quote) or _BEFORE.search(item.quote) or (
                    not names_it and (must_name or _leans_without_a_name(item.quote))):
                leaning.add(item.comment_id)
        out.append(item)
    return out, leaning


def _names_its_product(text: str, mention: ScoredMention) -> bool:
    return _names_product(text, mention.product_name, mention.category, mention.written_as)


def _bare_mention(m: ScoredMention) -> bool:
    """A quote that names the product and says nothing more about it, in under BARE_MENTION_WORDS words ("I have a
    ballarini"): it never takes a place beyond what a pick needs (12 Oct 2026)."""
    return not _gives_a_view(m.quote) and len(m.quote.split()) < BARE_MENTION_WORDS


# A garbled quote: "the" left hanging before the end of a clause, alone or before an "-ly" word (Noemi's second demo test,
# 12 Oct 2026: a writer typed "the" for "them", as in "I wash the carefully."), or "a" or "an" before one. A writer's
# slip, not words a reader can follow.
_GARBLED = re.compile(r"(?:\bthe\b(?:\s+[a-z]+ly)?|\ban?\s+[a-z]+ly)\s*(?:[.!?,;:]|$)", re.IGNORECASE)


def _garbled(quote: str) -> bool:
    return bool(_GARBLED.search(quote.strip()))


# Advice: a sentence that opens with what to do ("Buy a decent pan, keep the heat low"), or says what one should do.
_ADVICE = re.compile(r"(?:^|[.!?]\s+)(?:just |so |also |then )?(?:get|buy|go for|try|avoid|keep|wash|don't|do not|never|"
                     r"always|look for|pick|choose|stick with|spend)\b"
                     r"|\b(?:you should|you'll want|i'd recommend|i recommend|is the way to go|worth it)\b", re.IGNORECASE)


def _gives_a_view_or_advice(text: str) -> bool:
    return _gives_a_view(text) or bool(_ADVICE.search(_plain(text)))


def _with_a_view(mentions: list[ScoredMention], bodies: Mapping[str, str]) -> list[ScoredMention]:
    """Each bare mention (_bare_mention) widened to the sentences before it in its comment that state a view or advice,
    when there are any within QUOTE_MAX_WORDS words (Noemi's second demo test, 12 Oct 2026: "prefer the comment's
    sentences that state a view or advice"); the others as they are."""
    out = []
    for m in mentions:
        if _bare_mention(m):
            wider = _widened(m.quote, bodies.get(m.comment_id),
                             lambda text, m=m: _names_its_product(text, m) and _gives_a_view_or_advice(text))
            m = dataclasses.replace(m, quote=wider) if wider is not None else m
        out.append(m)
    return out


def _pick_quotes(product: ProductScore, check: _QuoteCheck, asks: tuple[str, ...],
                 needs: tuple[Need, ...], product_type: str | None = None) -> list[ShownQuote]:
    """Up to QUOTES_PER_PICK verified quotes for a pick, in _naming_first's order, each widened to stand on its own where
    its comment allows (_standing), and a bare mention to the view or advice before it (_with_a_view). Quotes that say
    something about it come first; a bare mention or a garbled quote (_garbled), a quote that says nothing about it
    (_says_something) and, last, one that still leans on the thread only make up MIN_QUOTES_PER_PICK."""
    mentions, leaning = _standing(product.credible_recommendations, check.bodies, _names_its_product)
    ordered = _naming_first(_with_a_view(mentions, check.bodies), asks, needs, leaning, product_type)
    standing = [m for m in ordered if m.comment_id not in leaning]

    def filler(m: ScoredMention) -> bool:
        return _bare_mention(m) or _garbled(m.quote)

    quotes = check.first([m for m in standing if _says_something(m) and not filler(m)], QUOTES_PER_PICK)
    for rest in ([m for m in standing if _says_something(m) and filler(m)],
                 [m for m in standing if not _says_something(m)],
                 [m for m in ordered if m.comment_id in leaning]):
        if len(quotes) < MIN_QUOTES_PER_PICK:
            quotes += check.first(rest, MIN_QUOTES_PER_PICK - len(quotes))
    return quotes


def _warning_quotes(groups: Iterable[Iterable[ScoredMention]], check: _QuoteCheck, limit: int,
                    needs: tuple[Need, ...] = ()) -> list[ShownQuote]:
    """Up to `limit` verified warning quotes (a pick's downsides, a skipped product's quotes): each group in turn, in
    _naming_first's order, widened where that makes them stand (_standing). A quote that still leans on the thread is
    shown only when no other is: a pick's downsides are never hidden."""
    ordered, leaning = [], set()
    for group in groups:
        mentions, group_leaning = _standing(group, check.bodies, _names_its_product)
        ordered += _naming_first(mentions, needs=needs, leaning=group_leaning)
        leaning |= group_leaning
    shown = check.first([m for m in ordered if m.comment_id not in leaning], limit)
    return shown or check.first([m for m in ordered if m.comment_id in leaning], 1)


def _pick(rank: int, product: ProductScore, quotes: list[ShownQuote], check: _QuoteCheck, ranking: RankingResult,
          price: ShownPrice, care: list[ShownCareTip], availability: ShownAvailability = NOT_CHECKED,
          cautions: list[str] | None = None, more_downsides: list[ScoredMention] = (),
          needs: tuple[Need, ...] = ()) -> Pick:
    """One pick. `more_downsides`: credible warnings about the pick's own brand or line, shown after its own (the
    pipeline's _fold_brand_skips, 10 Oct 2026). `needs`: warnings that talk about them come first among equally clear
    ones ("when my bonavita broke" for a kettle that should last)."""
    warnings = product.credible_warnings
    downsides = _warning_quotes((warnings, more_downsides), check, DOWNSIDES_PER_PICK, needs)
    return Pick(
        rank=rank,
        product_key=product.key,
        name=product.name,
        reason=_reason(product, ranking),
        support=_support(product),
        quotes=quotes,
        downsides=downsides,
        disagreement=(DISAGREEMENT.format(voices=_plural(len(_warned(product, more_downsides)), "credible voice"))
                      if product.disputed else None),
        score=product.score,
        breakdown=product.breakdown,
        price=price,
        availability=availability,
        care=care,
        cautions=cautions or [],
        downsides_share=_downsides_share(product, more_downsides) if downsides else None,
        voices=_voices(product, more_downsides),
    )


def _voices(product: ProductScore, more_downsides: Iterable[ScoredMention] = ()) -> dict[str, int]:
    """The credible voices behind a pick or an "Also worth a look" item, as numbers for the page's credibility meter (13
    Oct 2026, the UX builder): its credible recommendations (as the reason counts them), of them the high and the medium
    voices (as the support line does), the writers who warned against it (_warned, as the share line and the
    mixed-opinions line do) and the threads with a credible recommendation (as the support line does). So the meter
    never disagrees with the words around it. Numbers only, like the breakdown; the score itself isn't in it."""
    recommendations = product.credible_recommendations
    return {"recommend": len(recommendations),
            "high": sum(m.voice == "high" for m in recommendations),
            "medium": sum(m.voice == "medium" for m in recommendations),
            "warn": len(_warned(product, more_downsides)),
            "threads": product.breakdown.credible_threads}


def _warned(product: ProductScore, more_downsides: Iterable[ScoredMention] = ()) -> set[str]:
    """The writers of a pick's credible warnings and of those about its own brand or line shown under it (the pipeline's
    _fold_brand_skips), each once: whom its downsides come from."""
    return {m.author or m.comment_id for m in [*product.credible_warnings, *more_downsides]}


def _downsides_share(product: ProductScore, more_downsides: Iterable[ScoredMention] = ()) -> str:
    """DOWNSIDES_SHARE for a pick: the writers its downsides come from (_warned), of those and its credible
    recommendations together (Noemi, 12 Oct 2026): "1 of 15 credible voices warned against it:" reads as what it is.
    The mixed-opinions line (DISAGREEMENT) counts the same writers, so the two never give different numbers."""
    warned = _warned(product, more_downsides)
    return DOWNSIDES_SHARE.format(n=len(warned), total=len(warned) + len(product.credible_recommendations))


def _care_tips(tips: CareTips | None, check: _QuoteCheck, limit: int = CARE_TIPS_PER_PICK,
               already: Iterable[str] = ()) -> list[ShownCareTip]:
    """Up to `limit` care tips (a pick's own, or the note's), the ones most credible writers agree on first
    (engine.care_tips.tips_by_agreement, 10 Oct 2026); repairs are left out since 12 Oct 2026 (Noemi: a repair story
    isn't advice on looking after the product, as extraction instructions v8 say). Each tip shown stands for one group
    of tips that say the same thing, so the same advice is never shown twice: the group's best writer's tip, in their
    words, with their quote.
    When that quote fails the check, it is dropped and the group's next writer's tip and quote take its place. A group
    saying the same as one of `already` (tips shown elsewhere in the answer) is left out."""
    if tips is None:
        return []
    shown: list[ShownCareTip] = []
    for group in tips_by_agreement(tips):
        if len(shown) == limit:
            break
        if is_repair(group[0].tip):  # a repair story isn't looking after the product (Noemi, 12 Oct 2026)
            continue
        if any(similar_tips(group[0].tip, tip) for tip in already):
            continue
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
    quotes = _warning_quotes((product.credible_warnings,), check, QUOTES_PER_SKIPPED_PRODUCT)
    if not quotes:
        return None
    praised = len(product.credible_recommendations)
    reason = SKIP_REASON.format(
        voices=_plural(len(product.credible_warnings), "credible voice"),
        praised=SKIP_ALSO_PRAISED.format(voices=_plural(praised, "credible voice")) if praised else "",
    )
    return SkipItem(product.key, product.name, reason, quotes)


def _look_for(ranking: RankingResult, check: _QuoteCheck, product_type: str | None = None,
              unsuited_kinds: Collection[str] = (), request: str = "", asks: tuple[str, ...] = (),
              picks: Collection[str] = (), forms_asked: Collection[str] = ()) -> list[LookFor]:
    """Up to LOOK_FOR_NOTES kinds, strongest credible advice first, each with its strongest verified note. In skincare,
    a kind whose advice is about another type of product gives none (_another_types_advice). A kind in
    `unsuited_kinds` (its facts clash hard with the request: the pipeline's _unsuited_kinds) gives no "Look for".

    A kind with positive support gets "Look for" and a recommending note; negative support gets "Avoid" and a
    warning note. A kind whose support is zero (no credible notes, or as many for as against) gives no advice. A
    comment already shown for another kind's same advice isn't shown again (10 Oct 2026): the kind takes its next
    credible note, or, with none, joins that line ("Look for: Cast iron or Carbon steel").

    Since 13 Oct 2026, when the request names active ingredients (engine/ingredients.py), a kind is advice only when
    its own name names one of them or a related one ("leave-on BHA" for salicylic acid); in an ingredient-led answer,
    only when the form its name says (if any) is one the answer may show (Noemi's decision 1: leave-on forms, or
    `forms_asked`, the forms the request names): no "Look for: BHA cleanser" above leave-on products.

    Since 12 Oct 2026 (Noemi's note: "Look for: retinol" in a retinol answer), the product asked for itself is no advice
    (_the_product_asked_for: `request` is the request as typed), and neither is another type of product named in the
    kind's own name (_another_types_advice) or, for a type the open model named, another kind of it (config.
    OTHER_KIND_WORDS: an immersion blender for a blender). A kind is shown only with a note that states advice about it
    (_advice_notes: it names the kind, widened to the sentence before that does when needed, and isn't a hedge, a wish,
    a question, the opposite of one of the request's `asks`, or, for "Avoid", a warning about one of the `picks`); with
    none, it is left out. Kinds whose name or notes name the product asked for come before those that never do.
    """
    candidates = []
    # A request naming active ingredients (13 Oct 2026): advice must be about them ("Look for: tret" or "a cream
    # formula" says nothing to someone asking for a niacinamide serum). "retinol" names the retinoid type itself, so a
    # retinol request asks for no ingredient beyond its type (engine.ingredients.TYPE_OWN_INGREDIENT).
    named = [f.ingredient for f in find_ingredients(request)
             if TYPE_OWN_INGREDIENT.get(product_type or "") != f.ingredient]
    asked = list(dict.fromkeys([*ingredients_of_type(product_type), *named]))
    for kind in ranking.kinds:  # best supported first
        if kind.support == 0 or (kind.support > 0 and kind.key in unsuited_kinds):
            continue
        if asked and not mentions_product(kind.name, ingredient_type_name(asked)):
            continue
        if ingredients_of_type(product_type) and not _form_shown(kind.name, forms_asked):
            continue
        stance, advice = ("recommend", LOOK_FOR) if kind.support > 0 else ("warn", AVOID)
        notes = _most_credible_first([n for n in ranking.kind_notes
                                      if n.kind_key == kind.key and n.stance == stance and is_credible(n)])
        if (_the_product_asked_for(kind.name, ranking.category, product_type, request)
                or _instead_of_the_product(kind.name, ranking.category, product_type, request)
                or _another_types_advice(kind.name, notes, ranking.category, product_type)):
            continue
        candidates.append((kind, advice, notes))
    # sorted keeps ties in the ranking's order
    candidates.sort(key=lambda c: (not _about_the_type(c[0].name, c[2], product_type), -abs(c[0].support)))
    items: list[LookFor] = []
    item_notes: list[list[KindNote]] = []  # each item's kind's notes that state advice, strongest first
    for kind, advice, notes in candidates:
        if len(items) == LOOK_FOR_NOTES:
            break
        notes = _advice_notes(kind.name, advice, notes, check.bodies, ranking.category, product_type, asks, picks)
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


def _form_shown(kind: str, forms_asked: Collection[str]) -> bool:
    """Whether the form a kind's own name says (engine.ingredients.form_of on its words alone) is one an ingredient-led
    answer may show: one the request names, or, when it names none, a leave-on one; a kind naming no form is fine."""
    form = form_of(kind, None)
    if form is None:
        return True
    return form in forms_asked if forms_asked else form_kind(form) == "leave-on"


def _another_types_advice(kind: str, notes: list[KindNote], category: str, product_type: str | None) -> bool:
    """Whether a skincare or haircare kind's advice is about another type of product: its name and notes name another
    type of its category (engine.sources.mentions_product) and never the one asked for. Found in b04, 10 Oct 2026: a moisturiser answer
    showed "Look for: AHA" and "Look for: BHA", whose notes were about exfoliants. A note tying it to the type asked
    for keeps it ("an AHA lotion fixed my dry legs"). Kitchen kinds always stay: another kind of pan is a real
    alternative ("Look for: cast iron" for a PFAS-free non-stick pan).

    Since 12 Oct 2026, first the kind's own name: when it names types of product of its category (_named_types), they
    decide, whatever the notes say: advice named after other types only is another type's ("Avoid: eye creams" in a
    moisturiser answer, "double cleansing" in a sunscreen one), while "retinol eye cream" names a retinoid too. The
    same holds for a type the open model named, in any category: another listed type ("coffee grinder for seeds") or
    another kind of it ("immersion blender", config.OTHER_KIND_WORDS) is no advice for it.

    For an ingredient-led request ("salicylic acid for acne", 13 Oct 2026), advice must be about its ingredient: the
    kind's own name names it (or a related one: "leave-on BHA"); "Look for: AHA" or "a humidifier" isn't, whatever its
    notes compare it with."""
    if not product_type:
        return False
    if ingredients_of_type(product_type):
        return not mentions_product(kind, product_type)
    listed = product_type in {p.name for p in PRODUCT_TYPES}
    if not listed and _another_kind_of(kind, product_type):
        return True
    if category in ("skincare", "haircare") or not listed:
        named = _named_types(kind, category)
        if named:
            return product_type not in named
    if category not in ("skincare", "haircare"):
        return False
    text = " ".join([kind] + [n.quote for n in notes])
    if mentions_product(text, product_type):
        return False
    return any(mentions_product(text, other.name) for other in PRODUCT_TYPES
               if other.category == category and other.name != product_type)


STEM_LETTERS = 6  # two words of more letters sharing their first STEM_LETTERS are one word told two ways


def _same_word(a: str, b: str) -> bool:
    """Whether two words are the same word, or two forms of one ("cleansing" and "cleanser", "moisturizer" and
    "moisturiser", "separate" and "separately"): longer than STEM_LETTERS letters and sharing their first ones. Never
    "retinal" and "retinol"."""
    return a == b or (len(a) > STEM_LETTERS and len(b) > STEM_LETTERS and a[:STEM_LETTERS] == b[:STEM_LETTERS])


def _named_types(kind: str, category: str) -> set[str]:
    """The types of product a kind's own name names (12 Oct 2026), of module 1's product types of its category, before a
    word saying what it is for ("for", "instead", "with": engine.group_kinds): by one of the type's names, the longest
    where one holds another ("dry shampoo", not "shampoo"), or by a word sharing the stem of a one-word one
    ("cleansing", a cleanser's). "retinol eye cream" names a retinoid and an eye cream; "AHA" names none."""
    words = re.findall(r"[a-z0-9][a-z0-9'-]*", _plain(kind))
    cut = next((i for i, w in enumerate(words) if w in PURPOSE_WORDS), len(words))
    text = " ".join(words[:cut])
    types = [p for p in PRODUCT_TYPES if p.category == category]
    matches = [(m.start(), m.end(), p.name) for p in types for keyword in p.keywords
               for m in re.finditer(rf"\b{re.escape(keyword)}s?\b", text)]
    named = [(s, e, name) for s, e, name in matches
             if not any(s2 <= s and e <= e2 and e2 - s2 > e - s for s2, e2, _ in matches)]
    for word in re.finditer(r"[a-z0-9]+", text):
        if not any(s <= word.start() < e for s, e, _ in named):
            named += [(word.start(), word.end(), p.name) for p in types
                      if any(_same_word(word.group(), name) for name in (p.name, *p.keywords) if " " not in name)]
    return {name for _, _, name in named}


def _another_kind_of(kind: str, product_type: str) -> bool:
    """Whether a kind is another kind of a type the open model named: its name ends with the type's name and the word
    before it says another kind (config.OTHER_KIND_WORDS: an "immersion blender" isn't a blender)."""
    words = [w.removesuffix("s") for w in re.findall(r"[a-z0-9]+", _plain(kind))]
    wanted = [w.removesuffix("s") for w in re.findall(r"[a-z0-9]+", _plain(product_type))]
    for i in range(len(words) - len(wanted) + 1):
        if words[i:i + len(wanted)] == wanted and i > 0 and words[i - 1] in OTHER_KIND_WORDS:
            return True
    return False


def _own_names(category: str, product_type: str, request: str) -> set[str]:
    """The words the request's own product goes by: its type's name, and the type's names the request uses ("retinol"
    for a retinoid), read the way kinds are (engine.group_kinds); since 13 Oct 2026 also the words of the active
    ingredients it asks for and their related ones' ("BHA" in a salicylic acid answer is what was asked for)."""
    aliases = known_aliases("kinds").get(category, {})
    own = set(_kind_words(product_type, aliases))
    asked = list(ingredients_of_type(product_type)) + [f.ingredient for f in find_ingredients(request)]
    for words in (talk_words(ingredient_type_name(asked)) if asked else ()):
        own |= set(_kind_words(" ".join(re.findall(r"[a-z0-9]+", words)), aliases))
    lowered = _plain(request)
    for p in PRODUCT_TYPES:
        if p.name == product_type:
            for keyword in p.keywords:
                if re.search(rf"\b{re.escape(keyword)}s?\b", lowered):
                    own |= set(_kind_words(keyword, aliases))
    return own


def _the_product_asked_for(kind: str, category: str, product_type: str | None, request: str = "") -> bool:
    """Whether a kind is just the product the request asks for (12 Oct 2026: "Look for: retinol" in a retinol answer,
    "Look for: kettle" in a kettle one): every word of its name is one the product goes by (_own_names), told the same
    way (_same_word)."""
    if not product_type:
        return False
    own = _own_names(category, product_type, request)
    parts = kind_parts(kind, "", known_aliases("kinds").get(category, {}), set())
    return bool(parts) and all(any(_same_word(w, o) for o in own) for part in parts for w in part)


def _instead_of_the_product(kind: str, category: str, product_type: str | None, request: str = "") -> bool:
    """Whether a kind's name sets it against the product asked for: "moisturizer instead of eye cream" in an eye cream
    answer, "grinder over machine" in an espresso machine one (12 Oct 2026). That is advice to buy something else."""
    if not product_type:
        return False
    own = _own_names(category, product_type, request)
    aliases = known_aliases("kinds").get(category, {})
    words = _kind_words(kind, aliases)
    for i, word in enumerate(words):
        after = words[i + 2:] if words[i:i + 2] in (["instead", "of"], ["rather", "than"]) else (
            words[i + 1:] if word in ("over", "not") else None)
        after = [w for w in after or [] if w not in ("a", "an", "the", "any", "one")]
        if after and all(any(_same_word(w, o) for o in own) for w in after):
            return True
    return False


# Words of a kind's name that a note needn't repeat to name it: "lactic" names "lactic acid".
GENERIC_KIND_WORDS = frozenset({"acid", "product", "type", "kind", "option", "thing", "stuff", "formula", "texture",
                                "then", "gentle", "mild", "plain"})


def _names_kind(text: str, kind: str, category: str, product_type: str | None) -> bool:
    """Whether a text names a kind: every word of its name (or of one of its parts, "cast iron or carbon steel") but
    the product type's own and GENERIC_KIND_WORDS, read the way kinds are (known short names written out, "Teflon" as
    "nonstick"), told the same way (_same_word), or two of its words written as one."""
    aliases = known_aliases("kinds").get(category, {})
    parts = [[w for w in part if w not in GENERIC_KIND_WORDS] or part
             for part in kind_parts(kind, product_type or "", aliases)]
    words = _kind_words(text, aliases)
    seen = set(words) | {a + b for a, b in zip(words, words[1:])}
    return any(part and all(any(_same_word(w, s) for s in seen) for w in part) for part in parts)


# A question, a hedge or a wish states no advice: a writer saying there's no hurry to start retinol (shown as "Look for:
# retinol"), "I want one with a steel body", "Is it worth it?" (12 Oct 2026).
_NO_ADVICE = re.compile(r"\?[\s\"')”]*$|\b(?:don't|do not|dont) think (?:you|anyone) (?:should|need|has to|have to)\b"
                        r"|\bno (?:need|rush|urgency)\b|\b(?:not|isn't|is not) (?:necessary|essential)\b"
                        r"|\btoo early to (?:say|tell)\b")
_WISH = re.compile(r"\b(?:i|we) (?:really )?(?:want|wanted|would like|'d like|wish|need) (?:a|an|one|some|something)\b")


def _advice_notes(kind: str, advice: str, notes: list[KindNote], bodies: Mapping[str, str], category: str,
                  product_type: str | None, asks: tuple[str, ...] = (), picks: Collection[str] = ()) -> list[KindNote]:
    """A kind's notes that state advice about it, as they can be shown (12 Oct 2026): each names the kind, widened to the
    sentences before it that do when it doesn't (_standing), and none leans on what the comment doesn't show, is a
    question or a hedge (_NO_ADVICE), a wish (_WISH, for "Look for"), the opposite of one of the request's `asks` (for
    "Look for"), or a warning about one of the answer's `picks` (for "Avoid", _names_a_pick)."""
    widened, leaning = _standing(notes, bodies, lambda text, note: _names_kind(text, kind, category, product_type),
                                 must_name=True)
    kept = []
    for note in widened:
        text = _plain(note.quote)
        if note.comment_id in leaning or not _names_kind(note.quote, kind, category, product_type) or (
                _NO_ADVICE.search(text)):
            continue
        if advice == LOOK_FOR and (_WISH.search(text) or _says_the_opposite(note.quote, asks)):
            continue
        if advice == AVOID and any(_names_a_pick(note.quote, pick, category) for pick in picks):
            continue
        kept.append(note)
    return kept


def _names_a_pick(text: str, pick: str, category: str) -> bool:
    """Whether a text names a pick, its first name word written with a one-letter slip too ("Greenspan" for GreenPan),
    when that word is long enough to tell (more than STEM_LETTERS letters)."""
    if _names_product(text, pick, category):
        return True
    first = (_name_words(pick) or [""])[0]
    return len(first) > STEM_LETTERS and any(one_edit_apart(word, first) for word in _name_words(text))


def _about_the_type(kind: str, notes: list[KindNote], product_type: str | None) -> bool:
    """Whether a kind's name or one of its notes names the product asked for (engine.sources.mentions_product): such
    kinds come first. Without a product type, every kind is about it."""
    return not product_type or mentions_product(" ".join([kind] + [n.quote for n in notes]), product_type)


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
    for item in answer.worth_a_look:
        if not item.quotes:
            problems.append(f"worth a look ({item.name}): no quote backs it")
    for where, shown in _summaries(answer):
        problems += [f"{where} summary: {problem}" for problem in text_problems(shown.text)]
        if not shown.sources:
            problems.append(f"{where} summary: it cites no verified quote")
        for quote in shown.sources:
            problem = _quote_problem(quote.text, quote.comment_id, bodies)
            if problem:
                problems.append(f"{where} summary: {problem}")
    return problems


def _summaries(answer: Answer) -> Iterator[tuple[str, ShownSummary]]:
    """Each summary the answer shows, with where."""
    for pick in answer.picks:
        if pick.summary is not None:
            yield f"pick {pick.rank} ({pick.name})", pick.summary
    for item in answer.worth_a_look:
        if item.summary is not None:
            yield f"worth a look ({item.name})", item.summary


def quotes_to_check(answer: Answer) -> list[ShownQuote]:
    """Every quote the live check must pass before the answer is shown: the quotes it shows (shown_quotes), then those
    its summaries cite (13 Oct 2026), so a summary never stands on a comment deleted or changed on Reddit since."""
    return shown_quotes(answer) + [quote for _, shown in _summaries(answer) for quote in shown.sources]


def needed_quotes(answer: Answer) -> list[ShownQuote]:
    """The quotes an answer can't go without (Noemi, 13 Oct 2026: the picks first): every quote it shows but those of
    "Also worth a look". Their live checks wait for Reddit's allowance when they must; the others' (that section's, and
    those the summaries cite) never do."""
    return [quote for where, quote in _every_quote(answer) if not where.startswith("worth a look")]


def without_unread(answer: Answer, comment_ids: set[str]) -> Answer:
    """The answer without what stands on these comments, which the live check put off (13 Oct 2026): an "Also worth a
    look" item quoting one (in its quotes or downsides), and a summary citing one. Nothing else changes."""
    def unread(quotes) -> bool:
        return any(quote.comment_id in comment_ids for quote in quotes)

    def summary_read(shown):
        return replace(shown, summary=None) if shown.summary is not None and unread(shown.summary.sources) else shown

    worth = [summary_read(item) for item in answer.worth_a_look if not unread((*item.quotes, *item.downsides))]
    return replace(answer, picks=[summary_read(pick) for pick in answer.picks], worth_a_look=worth,
                   worth_note=answer.worth_note if worth else None)


def shown_quotes(answer: Answer) -> list[ShownQuote]:
    """Every quote the answer shows: its picks' quotes, downsides and care tips, "Also worth a look", "what to look for"
    and the skip list.
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
    for item in answer.worth_a_look:
        for quote in item.quotes:
            yield f"worth a look ({item.name})", quote
        for quote in item.downsides:
            yield f"worth a look ({item.name}) downside", quote
    for item in answer.care_note:
        yield "care note", item.quote
    for item in answer.look_for:
        yield f"what to look for ({item.kind})", item.quote
    for item in answer.skip:
        for quote in item.quotes:
            yield f"skip-these ({item.name})", quote


# --- Rendering as text (markdown) ---

def render_markdown(answer: Answer) -> str:
    """The answer as markdown text, readable as plain text too."""
    title = answer.title or answer_title(answer.product_type, answer.ingredient)
    lines = [f"# {title}", ""]
    if answer.ingredient_note:
        lines += [answer.ingredient_note, ""]
    if answer.message:
        lines += [answer.message, ""]
    for pick in answer.picks:
        lines += _render_pick(pick)
    if answer.worth_a_look:
        lines += [f"## {WORTH_HEADING}", "", answer.worth_note or "", ""]
        for item in answer.worth_a_look:
            lines += _render_worth(item)
    if answer.look_for:
        lines += [f"## {LOOK_FOR_HEADING}", ""]
        for item in answer.look_for:
            lines.append(f"- **{item.advice}: {item.kind}.** {_render_quote_inline(item.quote)}")
        lines.append("")
    if answer.skip:
        lines += [f"## {SKIP_HEADING}", ""]
        for item in answer.skip:
            form = f" ({FORM_LABEL.lower()}: {item.form})" if item.form else ""
            lines.append(f"- **{item.name}**{form}**:** {item.reason}")
            lines += [f"  - {_render_quote_inline(quote)}" for quote in item.quotes]
        lines.append("")
    if answer.care_note:
        heading = (CARE_NOTE_HEADING.format(product_type=answer.product_type) if answer.product_type
                   else CARE_NOTE_HEADING_ANY)
        lines += [f"## {heading}", ""] + _render_care(answer.care_note)
    return "\n".join(lines).rstrip() + "\n"


def _render_form(form: str | None) -> list[str]:
    """The form line of a product in an ingredient-led answer (13 Oct 2026)."""
    return [f"**{FORM_LABEL}:** {form}", ""] if form else []


def _render_pick(pick: Pick) -> list[str]:
    lines = [f"## {pick.rank}. {pick.name}", ""] + _render_form(pick.form)
    if pick.model:
        price = f" ({pick.model_price})" if pick.model_price else ""
        lines += [BRAND_PICK_MODEL.format(model=pick.model) + price, ""]
    lines += _render_summary(pick.summary)
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
        lines += [pick.downsides_share, ""] if pick.downsides_share else []
        for quote in pick.downsides:
            lines += _render_quote_block(quote)
    else:
        lines += [NO_DOWNSIDES, ""]
    if pick.care:
        lines += [f"**{CARE_HEADING}**", ""] + _render_care(pick.care)
    # The score breakdown is off the card since 12 Oct 2026 (Noemi: too technical, and it doesn't build trust); the
    # JSON keeps it (answer_to_dict) and the how-we-score page explains the scoring.
    return lines


def _render_summary(summary: ShownSummary | None) -> list[str]:
    """"In short:" and the summary, in our words and never in quotation marks, with the note saying so."""
    return [f"**{SUMMARY_LABEL}** {summary.text} _({SUMMARY_NOTE})_", ""] if summary is not None else []


def _render_worth(item: WorthALook) -> list[str]:
    """An "Also worth a look" item: its name, summary, reason, price (when known, or with a budget), where it is sold
    (when checked), cautions, quotes and, only when credible voices warn against it, its downsides."""
    lines = [f"### {item.name}", ""] + _render_form(item.form) + _render_summary(item.summary) + [item.reason, ""]
    if item.price.amount is not None or item.price.budget_note:  # lighter than a pick: what is known, or the budget's
        lines += _render_price(item.price)
    if item.availability.available is not None:
        lines += _render_availability(item.availability)
    for caution in item.cautions:
        lines += [caution, ""]
    if item.disagreement:
        lines += [f"**{item.disagreement}**", ""]
    for quote in item.quotes:
        lines += _render_quote_block(quote)
    if item.downsides:
        lines += [f"**{DOWNSIDES_HEADING}**", ""] + ([item.downsides_share, ""] if item.downsides_share else [])
        for quote in item.downsides:
            lines += _render_quote_block(quote)
    return lines


def _render_care(items: list[ShownCareTip]) -> list[str]:
    """Care tips as a list: the tip in bold, then its quote; a tip that only repeats its quote shows the quote alone."""
    return [f"- **{masked(item.tip)}** {_render_quote_inline(item.quote)}" if item.tip
            else f"- {_render_quote_inline(item.quote)}" for item in items] + [""]


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
    return [f'> "{masked(_one_line(quote.text))}"', f"> — {credit}", ""]


def _same_words(a: str, b: str) -> bool:
    """Whether two texts say the same words, capitals and punctuation aside (10 Oct 2026: a care tip that only
    repeats its quote is shown once)."""
    words = lambda text: re.findall(r"[a-z0-9]+", text.lower())
    return words(a) == words(b)


def _render_quote_inline(quote: ShownQuote) -> str:
    credit = " · ".join(quote.badges + (f"[{LINK_TEXT}]({quote.url})",))
    return f'"{masked(_one_line(quote.text))}" ({credit})'


def breakdown_needs_line(recommends: int | str, warnings: int | str) -> str:
    """The breakdown's line about the request's needs. The numbers may be given as placeholders ("{recommends}"):
    the web page fills them in."""
    return BREAKDOWN_NEEDS.format(recommends=recommends, warnings=warnings, boost=f"{NEED_MATCH_BOOST:g}")


# --- Swear words, masked on display (Noemi, 12 Oct 2026) ---

# Whole words only, so "Scunthorpe", "shiitake" and "Dickens" stay as written. Regular expressions that read the same in
# Python and in the page's JavaScript (engine/templates/search.html masks with this same list).
MASKED_WORDS = (
    r"(?:mother)?fuck(?:s|ed|er|ers|ing|in|ery)?", r"(?:bull|horse)?shit(?:s|ty|tier|ting|ted|head|heads|show)?",
    r"cunts?", r"bitch(?:es|y|ing)?", r"(?:arse|ass)holes?", r"bastards?", r"dick(?:s|head|heads)?",
    r"piss(?:ed|ing)?", r"twats?", r"wank(?:er|ers|ing)?", r"bollocks",
)
_MASKED = re.compile(r"\b(?:" + "|".join(MASKED_WORDS) + r")\b", re.IGNORECASE)


def masked(text: str) -> str:
    """The text as shown: each swear word keeps its first and last letters, the rest starred ("f**k"). Only what is
    displayed changes: the quote checked word for word, against the saved comment and live, stays the comment's own."""
    return _MASKED.sub(lambda m: m.group()[0] + "*" * (len(m.group()) - 2) + m.group()[-1], text)
