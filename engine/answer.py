"""Module 7, answer writing: writes the top 3 picks from a fixed template, using only verified quotes.

There is no Claude API key for now (Noemi, 7 Oct 2026), so the answer is a fixed template whose slots are filled
from the ranking's data only: names, counts and quotes. Nothing is made up or paraphrased. Later, an AI step may
write the one-line reasons, but only from the verified quotes, inside this same template.

What each pick shows (the brief):
- the product name and a one-line reason it wins; when some of its credible recommendations talk about what the
  request asks for (engine/needs.py, 9 Oct 2026), the reason says how many and about what ("3 of them about sensitive
  skin"), by the needs a comment can talk about (engine.needs.judged_needs, since 15 Oct 2026: never the ingredient,
  size or checked requirement the request names, so a vitamin C serum's reason no longer says "about vitamin or c");
  and with Noemi's upvote rule on (14 Oct 2026; off: config.UPVOTE_COUNTS_MORE), which of its credible voices
  counted twice toward the picks bar and for how many upvotes ("(one counted twice for its 34 upvotes)"), while every
  number of voices stays the number of writers (the meter's "voices" says how many counted twice) and the answer's
  messages give the bar with its upvotes ("..., or 2 when one of them has 10 or more upvotes"); and when a comment
  standing out in its thread is why it is shown (14 Oct 2026; config.STANDOUT_ON), which comment and by how much
  ("(one comment has 205 upvotes in a 270-comment thread)"), the same for an "Also worth a look" item;
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
- for a brand-line pick (Noemi's night decision 1, 14 Oct 2026; the knife answer's three lines showed no link at all):
  its from price, researched in data/brand_lines.json, the cheapest UK price of its products of the type, "From £25 at
  John Lewis, checked 14 Oct 2026", with the shop's link; within a budget, "From £25, within your budget (up to £100)."
  (a line whose from price is over the budget never gets here); and since the researcher found it on sale there, "Sold
  at John Lewis, checked 14 Oct 2026". Then a link to its maker's page for its products of the type, or an official UK
  stockist's: "Browse Victorinox chef knives", "checked 14 Oct 2026" (shown_range). Both come from the brand-lines
  list, never from a comment, and change nothing about which products are picks. A line under "Also worth a look" shows
  them too;
- its own page and its maker's image (Noemi's decisions 2 and 3 of 15 Oct 2026, late afternoon: "could we add a little
  image of the prod with the link?"; direct links only): when researched (data/product_pages.json), a direct link to
  its own page, its maker's or a big UK shop's, "See it at Apple", "checked 15 Oct 2026" (shown_link; only when no line
  above links to that page already, nor a range link to the line's), and a small image from its maker's own page,
  linked to that page, its text the product's name (shown_image). No link ever goes to a search, here or in the price
  and availability lines (engine.links.is_direct_page): "Sold second-hand only: eBay UK" had linked to an eBay search,
  and now has no link. An "Also worth a look" item shows them too. The text answer carries the link, never the image;
- "How to take care of it" (Noemi, 9 Oct 2026; named so on 11 Oct 2026, and since then only the pick's own tips, the
  tips about its kind of product being shown once, in a note at the end): up to CARE_TIPS_PER_PICK credible care tips
  ("descale every 6 months"), each with its verified quote. Since 10 Oct 2026 (decided by Claude, as Noemi asked) the advice
  most credible writers agree on comes first and repairs ("smooth with an angle grinder") last; tips that say the same
  thing are shown once, in their best writer's words (engine.care_tips.tips_by_agreement). A pick with no tip has no
  such heading.
- cautions (product facts, decided by Claude, 9 Oct 2026): when a checked fact suits the request less well by a soft
  rule (engine/product_facts.py: a rich moisturiser for oily skin), "Note: <the reason>." under the pick's price lines.
  Products whose facts clash by a hard rule never get here: the pipeline leaves them out. One whose facts can't confirm
  a must-have says so ("Note: we couldn't confirm it has SPF.") and, since Noemi's decision 1 of 15 Oct 2026, comes
  after the products whose facts confirm it, in the picks and under Also worth a look alike (engine/rank.py).
- prescription-only (Noemi's decision 5 of 14 Oct 2026): a product whose checked facts say it is sold in the UK only on
  a prescription says so under its price lines, PRESCRIPTION_NOTE, and so does such an "Also worth a look" item or
  skipped product. (A request for a beginner, a gentle product or sensitive skin never gets such a product.)
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
Since her decision 4 of 15 Oct 2026, the products that meet the picks bar on their own but rank below the top 3 come
first there (engine.rank.RankingResult.past_the_picks), each labelled as meeting the bar (MEETS_BAR; WorthALook.meets_bar),
with a pick's reason line, and the note says how many meet it (WORTH_NOTE_BAR...). The section keeps its size.
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
from functools import cache, lru_cache

from engine import config  # the upvote rule's settings, read as the answer is written (14 Oct 2026)
from engine.brand_lines import BrandLine, is_source_page
from engine.care_tips import CareTip, CareTips, is_repair, similar_tips, tips_by_agreement
from engine.config import (
    BRAND_PICK_MODEL,
    CARE_NOTE_TIPS,
    CARE_TIPS_PER_PICK,
    DOWNSIDES_PER_PICK,
    LOOK_FOR_NOTES,
    OPPOSITE_NEGATED_IN_SENTENCE,
    OPPOSITE_NEGATION_WINDOW,
    OPPOSITE_QUOTE_PATTERNS,
    HAIR_NEEDS,
    INGREDIENTS,
    NEEDS,
    OTHER_KIND_WORDS,
    QUOTE_ADVICE_AGAINST_PATTERNS,
    QUOTE_FAILURE_PATTERNS,
    QUOTE_PRAISE_PATTERNS,
    QUOTE_STANCE_NEGATION_WINDOW,
    QUOTE_STANCE_PEOPLE_WORDS,
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
    TYPE_SYNONYMS,
    WORTH_A_LOOK_CREDIBLE,
    WORTH_A_LOOK_QUOTES,
    WORTH_A_LOOK_SHOWN,
)
from engine.extract import _as_written, _in_quoted_block, _own_words_in_quote_format
from engine.group_kinds import PURPOSE_WORDS, _kind_words, kind_parts
from engine.group_products import plural
from engine.ingredients import (
    TYPE_OWN_INGREDIENT, find_ingredients, form_kind, form_of, ingredient_type_name, ingredients_of_type, talk_words,
)
from engine.links import is_direct_page, is_linkable, is_search_page
from engine.models import Thread
from engine.product_pages import ProductPage
from engine.needs import LASTING, Need, needs_met, said_not_to_help
from engine.sources import _stem as _need_stem
from engine.prices import PriceCheck
from engine.credibility import _SECONDHAND_REASON, _proof_of_use, GENERIC_NAME_WORDS
from engine.match_products import FILLER_WORDS, known_aliases
from engine.memo import Table
from engine.rank import KindNote, KindSupport, ProductScore, RankingResult, ScoredMention, ScoreBreakdown, is_credible
from engine.query import LOOKALIKE_PHRASES, PRODUCT_TYPES, SKIN_TYPES
from engine.sources import mentions_product
from engine.summaries import Summary, shown_problems, summary_key, text_problems
from engine.text import one_edit_apart
from engine.verify_quotes import find_quote, verify_quote

# --- Wording users see: PROPOSED 9 Oct 2026, awaiting Noemi ---
TITLE = "Top picks: {product_type}"
TITLE_ANY = "Top picks"
# {needs} added 9 Oct 2026 (REASON_NEEDS below), {upvotes} 14 Oct 2026 (REASON_UPVOTES below)
REASON = "Recommended by {voices}{upvotes}{long_term}{needs}{kind}."
REASON_LONG_TERM = ", {n} of them after long-term use"
REASON_KIND = "; credible voices favour its kind most ({kind})"
# Noemi's upvote rule (14 Oct 2026; off unless config.UPVOTE_COUNTS_MORE; wording decided by Claude, from the
# orchestrator's example): the reason says which of its credible voices counted twice toward the picks bar, and for how
# many upvotes, right after the number of voices, which stays the number of writers: "Recommended by 2 credible voices
# (one counted twice for its 34 upvotes), 2 of them after long-term use." Several: "(two counted twice for their upvotes:
# 1,203 and 34)". The rule as the answer's messages give it (RULE): "..., or 2 when one of them has 10 or more upvotes",
# with variant C's thread "and is in the top 10% of a thread of 20 or more comments".
REASON_UPVOTES_ONE = " (one counted twice for its {upvotes} upvotes)"
REASON_UPVOTES = " ({n} counted twice for their upvotes: {upvotes})"
RULE_UPVOTES = ", or {fewer} when one of them has {score} or more upvotes"
RULE_UPVOTES_THREAD = " and is in the top {top} of a thread of {comments} or more comments"
# A comment that stands out in its thread (Noemi, 14 Oct 2026, after switching on variant D; off unless
# config.STANDOUT_ON; wording decided by Claude, from the orchestrator's example): a product shown only thanks to it
# says which comment, and by how much, right after its number of voices, which stays the number of writers:
# "Recommended by 1 credible voice (its comment has 74 upvotes in a 69-comment thread)"; with more writers, "(one
# comment has ...)".
# The note under Also worth a look is WORTH_NOTE_STANDOUT when such an item is shown, and the rule in the answer's
# messages adds RULE_STANDOUT when such a pick is: in an answer it changes nothing in, every word stays as it was.
REASON_STANDOUT_ONE = " (its comment has {upvotes} upvotes in a {comments}-comment thread)"
REASON_STANDOUT = " (one comment has {upvotes} upvotes in a {comments}-comment thread)"
RULE_STANDOUT = ", or {fewer}, even from one thread, when one of them stands out in its thread"
NUMBER_WORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
SUPPORT = "Backed by {voices}, across {threads}."
DISAGREEMENT = "Mixed opinions: also warned against by {voices}."
NO_DOWNSIDES = "No credible voice in these threads warned against it."
SKIP_REASON = "Warned against by {voices}{praised}."
SKIP_ALSO_PRAISED = ", though still recommended by {voices}"
LOOK_FOR = "Look for"  # a kind credible voices recommend
AVOID = "Avoid"  # a kind credible voices warn against
RULE = "at least {mentions} credible recommendations across at least {threads} threads"
NO_PICKS = "Not enough credible evidence to recommend {what} yet: a pick needs {rule}. We'd rather say so than guess."
# When no saved thread is about the product at all (14 Oct 2026, the general category: most of its types have none yet;
# wording decided by Claude, PROPOSED). On the live site on-demand reading then says it has started reading.
NO_THREADS = ("We haven't read any Reddit threads about {products} yet, so there's nothing to recommend from. We'd "
              "rather say so than guess.")
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
# Brand lines (Noemi's night decision 1, 14 Oct 2026; wording decided by Claude from her example, reported to her). A
# line has many products, so no single price: it shows its from price, the cheapest UK price of its products of the
# type (data/brand_lines.json), and a link to its maker's page for them (or an official UK stockist's), with the day
# its sources were read: "Browse Victorinox chef knives", "checked 14 Oct 2026". Her example said "Victorinox's"; the
# brand stays as its maker writes it, since some entries are a line of a brand and read badly as a possessive
# ("Instant Vortex Plus' air fryers"), and a stockist's page says whose it is ("... at <shop>").
PRICE_FROM = "From {amount} at {shop}, checked {date}"
PRICE_FROM_AMOUNT = "From {amount}"  # the amount alone, as the page's "At a glance" and an item's row show it
BUDGET_WITHIN_FROM = "From {amount}, within your budget (up to {max})."
RANGE_LINK = "Browse {brand} {products}"
RANGE_LINK_AT = "Browse {brand} {products} at {shop}"  # an official UK stockist's page
RANGE_CHECKED = "checked {date}"
# Care tips (Noemi, 9 Oct 2026). Renamed by Noemi on 11 Oct 2026 (was "How to make it last"): only care of the product
# itself. A pick shows the tips about itself; tips about its kind of product are shown once, in a note at the end
# (CARE_NOTE_HEADING, filled with the request's product type; CARE_NOTE_HEADING_ANY without one).
CARE_HEADING = "How to take care of it"
CARE_NOTE_HEADING = "How to take care of your {product_type}"
CARE_NOTE_HEADING_ANY = "How to take care of it"
# Needs (9 Oct 2026; wording decided by Claude, as Noemi asked). The reason line says how many of the credible
# recommendations talk about what the request asks for, and about what: "Recommended by 5 credible voices, 3 of them
# about sensitive skin." It says "about", not "with sensitive skin": the rule finds comments that talk about a need,
# not writers who have it. Needs come from engine/needs.py, the ones a comment can talk about (judged_needs, since 15
# Oct 2026: "3 of them about vitamin or c" named a vitamin C serum's own ingredient); one not listed here is shown as the
# request typed it ("pour-over", "PFAS"). Several are listed with commas and a last "or": "2 of them about starting out
# or sensitive skin", "3 of them about starting out, home cooking or pour-over".
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
    # 10 Oct 2026. A need of its own since 14 Oct 2026, for hair too (NEED_LABELS_BY_CATEGORY below).
    "strip": "not stripping the skin",
    # Haircare needs (config.HAIR_NEEDS) and kitchen needs in other words, 14 Oct 2026 (Claude). "oily hair", "dry
    # hair", "dandruff" and "fine hair" read well as they are.
    "frizzy": "frizz",
    "curly": "curly hair",
    "wavy": "wavy hair",
    "colour-treated": "colour-treated hair",
    "itchy scalp": "an itchy scalp",
    "sensitive scalp": "a sensitive scalp",
    "quiet": "noise",
    "glass top stove": "glass-top stoves",
    "not drying": "drying",  # "a shampoo that isn't drying" (14 Oct 2026, Claude), as "no white cast" is "white cast"
}
# A need whose words differ by category (14 Oct 2026, Claude): "a shampoo that doesn't strip my hair".
NEED_LABELS_BY_CATEGORY: dict[str, dict[str, str]] = {"haircare": {"strip": "not stripping the hair"}}
# The breakdown's line about needs: only shown when some credible mention talks about them.
BREAKDOWN_NEEDS = ("About your request: {recommends} credible recommendations and {warnings} credible warnings talk "
                   "about what you asked for (each counts {boost} times as much)")
# Availability (Noemi's note, 9 Oct 2026). Wording DECIDED by Claude on 9 Oct 2026, as Noemi asked, and reported to her.
AVAILABILITY = "Sold at {shop}, checked {date}"
AVAILABILITY_UNKNOWN = "Availability not checked yet"
AVAILABILITY_GONE = "No longer sold, checked {date}"  # never shown through the pipeline, which leaves such products out
# A product not sold to UK shoppers but not discontinued (sold abroad, mostly in the US), shown with this note (Noemi,
# 15 Oct 2026, evening). Wording PROPOSED.
AVAILABILITY_NOT_IN_UK = "Not sold in the UK, checked {date}"
# Sold second-hand only: a product no longer made (Griswold and Wagner cast iron), sold only second-hand, on eBay UK or
# by a UK vintage dealer. Noemi's decision of 10 Oct 2026: such products count as available, and the answer says so.
AVAILABILITY_SECOND_HAND = "Sold second-hand only: {shop}, checked {date}"
# Products' own pages and their makers' images (Noemi's decisions 2 and 3 of 15 Oct 2026, late afternoon; wording
# decided by Claude, PROPOSED): a direct link to the product's own page, its maker's or a big UK shop's, with the day it
# was read ("See it at Apple", "checked 15 Oct 2026"); and a small image from its maker's own page, linked to that
# page, whose text for anyone who can't see it is the product's name. A price or availability line already linking to
# the same page, or a line's range link, is its link: no second one. Shoppers' links never go to a search.
PRODUCT_LINK = "See it at {shop}"
PRODUCT_LINK_CHECKED = "checked {date}"
IMAGE_ALT = "{name}"
# Product facts (9 Oct 2026). Wording DECIDED by Claude on 9 Oct 2026, as Noemi asked, and reported to her. A soft
# clash between a product's checked facts and the request (engine/product_facts.py) is shown under the pick as
# "Note: its texture is rich, which can feel heavy on oily or acne-prone skin." The reasons themselves are the rule
# table's (config.PRODUCT_FACT_RULES), decided by Claude the same day.
CAUTION = "Note: {reason}."
# Prescription-only products (Noemi's decision 5 of 14 Oct 2026; wording decided by Claude from the coordinator's
# example, in the answer's way of saying a fact and what to do). A product whose checked facts say it is sold in the UK
# only on a prescription (data/product_facts.json, "prescription_only") says so wherever it is shown: a pick and an "Also
# worth a look" item under their price lines, a "Skip these" item under its reason; on the page a row under the picks,
# and a pick's row "At a glance", also carry the tag. Such a product is still never offered for a beginner, a gentle
# product or sensitive skin (config.PRODUCT_FACT_RULES, "prescription only"): the note is for every other answer.
PRESCRIPTION_NOTE = "Prescription-only in the UK: ask a doctor or pharmacist."
PRESCRIPTION_TAG = "Prescription-only"
# Also worth a look (Noemi's decision 2 of 13 Oct 2026; wording decided by Claude). The note under the heading says how
# much less support its products have: "2 credible voices each: less evidence than the picks above, which need at least
# 3 credible recommendations across at least 2 threads." With no picks above, WORTH_NOTE_NO_PICKS.
WORTH_HEADING = "Also worth a look"
WORTH_NOTE = "{voices} each: less evidence than the picks above, which need {rule}."
WORTH_NOTE_NO_PICKS = "{voices} each: less evidence than a pick needs ({rule})."
# With an item shown thanks to a comment standing out in its thread (14 Oct 2026; see REASON_STANDOUT above).
WORTH_NOTE_STANDOUT = ("{voices} each, or one comment that stands out in its thread: less evidence than the picks "
                       "above, which need {rule}.")
WORTH_NOTE_STANDOUT_NO_PICKS = ("{voices} each, or one comment that stands out in its thread: less evidence than a "
                                "pick needs ({rule}).")
# Products past the picks (Noemi's decision 4 of 15 Oct 2026; wording decided by Claude, PROPOSED): a product that meets
# the picks bar on its own but ranks below the top 3 comes first under Also worth a look, labelled MEETS_BAR (its row's
# tag on the page, a line under its name in the text). The note under the heading says it first: WORTH_NOTE_BAR_ONE when
# it is the only item, WORTH_NOTE_BAR_EACH when every item is one, else WORTH_NOTE_BAR_FIRST(_ONE) and the others after
# "then" (WORTH_NOTE_BAR_REST, or WORTH_NOTE_BAR_REST_STANDOUT with an item a standing-out comment puts there). {rule} is
# the bar they meet on their own (RULE: never the upvote rule's other way to it).
MEETS_BAR = "Meets the bar for a pick"
WORTH_NOTE_BAR_ONE = "It meets the bar for a pick ({rule}) but ranks below the top {picks}."
WORTH_NOTE_BAR_EACH = "Each meets the bar for a pick ({rule}) but ranks below the top {picks}."
WORTH_NOTE_BAR_FIRST_ONE = "The first meets the bar for a pick ({rule}) but ranks below the top {picks}; then {rest}"
WORTH_NOTE_BAR_FIRST = "The first {n} meet the bar for a pick ({rule}) but rank below the top {picks}; then {rest}"
WORTH_NOTE_BAR_REST = "{voices} each: less evidence than a pick needs."
WORTH_NOTE_BAR_REST_STANDOUT = ("{voices} each, or one comment that stands out in its thread: less evidence than a "
                                "pick needs.")
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
    # True when it is a brand line's from price (14 Oct 2026): the cheapest UK price of its products of the type,
    # "From £25 at John Lewis, checked 14 Oct 2026"; False for a product's own price, or none.
    from_price: bool = False


@dataclass(frozen=True)
class ShownRange:
    """A brand line's link to its maker's page for its products of the type, or an official UK stockist's, as shown
    (Noemi's night decision 1, 14 Oct 2026): from data/brand_lines.json, never from a comment."""

    text: str  # "Browse Victorinox chef knives" (RANGE_LINK), or "... at <shop>" for a stockist's page
    url: str  # the entry's range page, exactly as the list writes it: https only, one of its sources, never Reddit
    checked: str  # "checked 14 Oct 2026": the day the entry's sources were read
    checked_on: str  # the same day, as "2026-10-14"


@dataclass(frozen=True)
class ShownLink:
    """A product's direct link to its own page, its maker's or a big UK shop's, as shown (Noemi's decision 3 of 15 Oct
    2026, late afternoon): from data/product_pages.json, never from a comment, never a search."""

    text: str  # "See it at Apple" (PRODUCT_LINK)
    url: str  # its own page, exactly as the list writes it: https only, never Reddit's, never a search
    shop: str  # the maker's or shop's plain name
    checked: str  # "checked 15 Oct 2026": the day its page was read
    checked_on: str  # the same day, as "2026-10-15"


@dataclass(frozen=True)
class ShownImage:
    """A small image of the product from its maker's own product page, linked to that page (Noemi's decision 2 of 15 Oct
    2026, late afternoon). The page loads it only when its card is on screen and sends no referrer."""

    url: str  # the image's address on the maker's site: https only, never Reddit's
    alt: str  # its text for anyone who can't see it: the product's name as shown (IMAGE_ALT)
    page: str  # the maker's page it is on, which it links to


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
    # For a brand-line pick: the link to its maker's page for its products of the type (14 Oct 2026); None otherwise,
    # and for a line whose entry has no range page.
    range: ShownRange | None = None
    # PRESCRIPTION_NOTE when its checked facts say it is prescription-only in the UK (14 Oct 2026); None otherwise.
    prescription: str | None = None
    # Its own page and its maker's image, when researched (Noemi's decisions of 15 Oct 2026, late afternoon): the link
    # only when no price or availability line links to that page already, nor a range link to the line's; else None.
    link: ShownLink | None = None
    image: ShownImage | None = None


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
    range: ShownRange | None = None  # as a pick's (14 Oct 2026): a brand line's link to its maker's page
    prescription: str | None = None  # as a pick's (14 Oct 2026)
    # True when it meets the picks bar on its own but ranks below the top 3 (Noemi's decision 4 of 15 Oct 2026): shown
    # first, labelled MEETS_BAR, with a pick's reason line. False for an item less supported than a pick.
    meets_bar: bool = False
    link: ShownLink | None = None  # as a pick's (15 Oct 2026)
    image: ShownImage | None = None


@dataclass
class SkipItem:
    product_key: str
    name: str
    reason: str
    quotes: list[ShownQuote]  # credible warnings, at least 1
    form: str | None = None  # as a pick's
    prescription: str | None = None  # as a pick's (14 Oct 2026)


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


def flattened_comments(threads: Iterable[Thread]) -> frozenset[str]:
    """The ids of the readable comments whose words are Reddit's embed page's text (Comment.edited "embed": found
    edited, they kept Reddit's current text; Noemi's decision 3 of 15 Oct 2026): its formatting read as plain words, so
    a quoted block, a list or a heading can't be told from the writer's own sentences, and their quotes are never
    widened."""
    return frozenset(c.id for thread in threads for c in thread.comments if c.status == "ok" and c.edited == "embed")


# --- Writing the answer ---

def write_answer(ranking: RankingResult, bodies: Mapping[str, str], product_type: str | None = None,
                 prices: Mapping[str, PriceCheck] | None = None, care: Mapping[str, CareTips] | None = None,
                 cautions: Mapping[str, list[str]] | None = None, models: Mapping[str, str] | None = None,
                 asks: tuple[str, ...] = (), model_prices: Mapping[str, str] | None = None,
                 more_downsides: Mapping[str, list[ScoredMention]] | None = None,
                 unsuited_kinds: Collection[str] = (), needs: tuple[Need, ...] = (), request: str = "",
                 summaries: Mapping[str, Summary] | None = None, worth_left_out: Collection[str] = (),
                 ingredient: str | None = None, forms: Mapping[str, str | None] | None = None,
                 forms_asked: Collection[str] = (), ranges: Mapping[str, BrandLine] | None = None,
                 prescription: Collection[str] = (), flattened: Collection[str] = (),
                 pages: Mapping[str, ProductPage] | None = None) -> Answer:
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
    are the keys of kinds that give no "Look for" (engine.pipeline._unsuited_kinds). `needs` (the needs a comment can
    talk about, engine.needs.judged_needs, since 15 Oct 2026): among equally clear quotes, those talking about them come
    first. `request` is the request as typed: the product it
    names ("retinol") is no advice about what to look for. `summaries` ({engine.summaries.summary_key: Summary}) are
    the one-line summaries written ahead of time: each is shown on its pick or item only when every check passes.
    `worth_left_out` are the keys of products the pipeline leaves out of "Also worth a look" (its brand rules).
    `ingredient` names the active ingredients the request asks for (13 Oct 2026; every product here contains them, the
    pipeline made sure), and `forms` is each product's form ({product key: form}) in an ingredient-led answer;
    `forms_asked` the forms an ingredient-led request names ("salicylic acid wash": cleanser), for its note.
    `ranges` ({product key: brand-lines entry}, 14 Oct 2026) are the entries of the products ranked as a brand's line:
    each such pick and "Also worth a look" item links to its entry's range page (shown_range). A line's from price
    comes in `prices`, like any price (PriceCheck.from_price). `prescription` (14 Oct 2026, Noemi's decision 5) are the
    keys of the products whose checked facts say they are prescription-only in the UK: each such pick, item and skipped
    product says so (PRESCRIPTION_NOTE). It never changes which products are shown. `flattened` (15 Oct 2026) are the
    comments whose words are Reddit's embed page's text (flattened_comments): their quotes are shown as they are, never
    widened to the sentences before them. `pages` ({product key: entry of data/product_pages.json}, 15 Oct 2026) are the
    researched pages of the products: each such pick and item links to its own page (shown_link) and shows its maker's
    image (shown_image). They never change which products are shown.
    """
    check = _QuoteCheck(bodies, flattened)
    check.named_in = _named_in(ranking)
    pages = pages or {}
    ranges = ranges or {}
    forms = forms or {}
    models = models or {}
    prices = prices or {}
    care = care or {}
    cautions = cautions or {}
    summaries = summaries or {}
    picks: list[Pick] = []
    said = _said_needs(needs, product_type, request, asks, ranking.category)  # how the reason names them (17 Oct 2026)
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
                               (more_downsides or {}).get(product.key, []), needs, said))
            picks[-1].model = models.get(product.key)
            picks[-1].model_price = (model_prices or {}).get(product.key)
            picks[-1].summary = _summary(product, _summary_of(product, summaries), check)
            picks[-1].form = forms.get(product.key)
            picks[-1].range = shown_range(ranges.get(product.key))
            picks[-1].prescription = _prescription(product.key, prescription)
            _with_page(picks[-1], pages.get(product.key))
    # A product the upvote rule lifted (14 Oct 2026) may be an item and a pick shown: then it is a pick only.
    shown_picks = {pick.product_key for pick in picks}
    worth = _worth_items(ranking, check, prices, cautions, summaries, set(worth_left_out) | shown_picks, asks, needs,
                         product_type, said)
    for item in worth:
        item.form = forms.get(item.product_key)
        item.range = shown_range(ranges.get(item.product_key))
        item.prescription = _prescription(item.product_key, prescription)
        _with_page(item, pages.get(item.product_key))
    skip = [_skip_item(product, check) for product in ranking.skip_list]
    for item in skip:
        if item is not None:
            item.form = forms.get(item.product_key)
            item.prescription = _prescription(item.product_key, prescription)
    look_for = _look_for(ranking, check, product_type, unsuited_kinds, request, asks, [pick.name for pick in picks],
                         forms_asked, needs, _picks_names(ranking, picks),
                         _Once(lambda: _lines_products(ranking, picks, product_type)))
    care_note = _care_note([care.get(pick.product_key) for pick in picks], picks, check)
    # Shown thanks to a comment standing out in its thread (14 Oct 2026): the messages and the note say how.
    standing_out = {p.key for p in ranking.products if p.by_standout}
    standout_pick = any(pick.product_key in standing_out for pick in picks)
    standout_item = any(item.product_key in standing_out for item in worth)
    bar_items = sum(item.meets_bar for item in worth)  # past the picks, shown first (Noemi's decision 4, 15 Oct 2026)
    return Answer(
        category=ranking.category,
        product_type=product_type,
        picks=picks,
        look_for=look_for,
        skip=[item for item in skip if item is not None],
        message=_message(len(picks), product_type, standout_pick),
        needs_more_threads=len(picks) < PICKS_SHOWN,
        quotes_dropped=check.dropped,
        care_note=care_note,
        worth_a_look=worth,
        worth_note=_worth_note(len(picks), standout_item, standout_pick, bar_items, len(worth)) if worth else None,
        ingredient=ingredient,
        ingredient_note=_ingredient_note(product_type, ingredient, forms_asked),
        title=answer_title(product_type, ingredient),
    )


def _prescription(key: str, prescription: Collection[str]) -> str | None:
    """PRESCRIPTION_NOTE for a product whose checked facts say it is prescription-only in the UK, else None."""
    return PRESCRIPTION_NOTE if key in prescription else None


def _with_page(shown: "Pick | WorthALook", page: ProductPage | None) -> None:
    """A pick's or item's own page and its maker's image (15 Oct 2026), from its entry in data/product_pages.json: the
    link only when no line of it links to that page already (its price, where it is sold) and it has no range link."""
    already = {shown.price.url, shown.availability.url}
    shown.link = shown_link(page) if shown.range is None else None
    if shown.link is not None and shown.link.url in already:
        shown.link = None
    shown.image = shown_image(page, shown.name)


def shown_link(page: ProductPage | None) -> ShownLink | None:
    """A product's direct link to its own page: "See it at Apple", with the day its page was read. None without an
    entry, and for a page that isn't one of the entry's sources or isn't a direct page (https, never Reddit's, never a
    search: engine.links.is_direct_page), checked again here as the list does when it loads."""
    if page is None or page.page not in page.sources or not is_direct_page(page.page):
        return None
    return ShownLink(PRODUCT_LINK.format(shop=page.shop), page.page, page.shop,
                     PRODUCT_LINK_CHECKED.format(date=_day(page.checked_on)), page.checked_on.isoformat())


def shown_image(page: ProductPage | None, name: str) -> ShownImage | None:
    """A product's image from its maker's own page, linked to that page, its text the product's name. None without an
    entry or an image, and for addresses that fail their checks (https, never Reddit's; the maker's page one of the
    entry's sources)."""
    if page is None or page.image is None or page.image_page is None or page.image_page not in page.sources:
        return None
    if not (is_linkable(page.image) and is_linkable(page.image_page)):
        return None
    return ShownImage(page.image, IMAGE_ALT.format(name=name), page.image_page)


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
                 asks: tuple[str, ...], needs: tuple[Need, ...], product_type: str | None,
                 said: "_SaidNeeds | None" = None) -> list[WorthALook]:
    """Up to WORTH_A_LOOK_SHOWN products of ranking.worth_a_look, in its order, those in `left_out` aside: first those
    that meet the picks bar on their own but rank below the top 3 (Noemi's decision 4 of 15 Oct 2026), each labelled so
    (meets_bar) and with a pick's reason line and voices; then those with two credible recommendations across two
    threads, best first; then those shown thanks to a comment standing out in its thread (14 Oct 2026). Each with its
    verified quotes (_worth_quotes), or left out without one."""
    items: list[WorthALook] = []
    past = {p.key for p in ranking.past_the_picks}
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
        meets_bar = product.key in past
        items.append(WorthALook(
            product_key=product.key,
            name=product.name,
            # A product the upvote rule lifted to the bar but its score left out of the picks (14 Oct 2026) is shown
            # here as it would be without the rule: the upvotes changed nothing for it, so nothing is said of them. One
            # shown here thanks to a comment standing out in its thread says so (_reason). One meeting the bar on its
            # own has a pick's reason, as a pick would say it.
            reason=_reason(product, ranking, upvotes=meets_bar, order=tuple(need.name for need in needs),
                           shown=(said or _said_needs(needs)).labels, hidden=(said or _said_needs(needs)).hidden),
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
            voices=_voices(product, twice=meets_bar),
            meets_bar=meets_bar,
        ))
    return items


def _worth_quotes(product: ProductScore, check: "_QuoteCheck", asks: tuple[str, ...], needs: tuple[Need, ...],
                  product_type: str | None) -> list[ShownQuote]:
    """Up to WORTH_A_LOOK_QUOTES verified quotes for an "Also worth a look" item, in a pick's order (_pick_quotes): each
    widened to stand on its own where its comment allows. Only quotes that say something about it: with no minimum to
    make up, a bare mention, a garbled quote, one that says nothing about it, one that still leans on the thread or one
    that starts mid-sentence (_mid_sentence) is never shown."""
    mentions, leaning = _standing(product.credible_recommendations, check.widen, _names_its_product)
    ordered = _naming_first(_with_a_view(mentions, check.widen), asks, needs, leaning, product_type, check.named_in)
    good = [m for m in ordered if m.comment_id not in leaning and _says_something(m)
            and not (_bare_mention(m) or _garbled(m.quote) or _mid_sentence(m.quote, check.bodies.get(m.comment_id)))]
    # A quote about another product of its comment (15 Oct 2026) only when the item has no other.
    return (check.first([m for m in good if not _about_another_product(m)], WORTH_A_LOOK_QUOTES)
            or check.first([m for m in good if _about_another_product(m)], 1))


def _mid_sentence(quote: str, body: str | None) -> bool:
    """Whether a quote starts in the middle of a sentence of its comment: in lowercase, after words that don't end a
    sentence (one opening on its verb, its subject a link left out; 13 Oct 2026). Such a quote never names what it is
    about."""
    span = find_quote(body, quote) if body else None
    if span is None or not quote[:1].islower():
        return False
    before = body[:span[0]].rstrip()
    return bool(before) and not before.endswith((".", "!", "?", "…", ":", ";"))


def _worth_note(picks: int, standout_item: bool = False, standout_pick: bool = False, bar_items: int = 0,
                items: int = 0) -> str:
    """The note under "Also worth a look": how much less support its products have than a pick; with an item shown
    thanks to a comment standing out in its thread (`standout_item`, 14 Oct 2026), that it can be one such comment, and
    with such a pick (`standout_pick`) the rule says how it meets the bar. With `bar_items` of its `items` meeting the
    bar on their own but ranked below the top 3 (Noemi's decision 4 of 15 Oct 2026), shown first, it says that first,
    and the bar they meet (WORTH_NOTE_BAR...)."""
    voices = _plural(WORTH_A_LOOK_CREDIBLE, "credible voice")
    if bar_items:
        bar = dict(rule=RULE.format(mentions=MIN_CREDIBLE_MENTIONS, threads=MIN_THREADS), picks=PICKS_SHOWN)
        if bar_items == items:
            return (WORTH_NOTE_BAR_ONE if items == 1 else WORTH_NOTE_BAR_EACH).format(**bar)
        rest = (WORTH_NOTE_BAR_REST_STANDOUT if standout_item else WORTH_NOTE_BAR_REST).format(voices=voices)
        if bar_items == 1:
            return WORTH_NOTE_BAR_FIRST_ONE.format(rest=rest, **bar)
        return WORTH_NOTE_BAR_FIRST.format(n=bar_items, rest=rest, **bar)
    if standout_item:
        wording = WORTH_NOTE_STANDOUT if picks else WORTH_NOTE_STANDOUT_NO_PICKS
    else:
        wording = WORTH_NOTE if picks else WORTH_NOTE_NO_PICKS
    return wording.format(voices=voices, rule=_rule(standout_pick))


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

    def __init__(self, bodies: Mapping[str, str], flattened: Collection[str] = ()):
        self.bodies = bodies
        # The comments whose quotes may be widened to the sentences before them (_standing, _with_a_view): all but those
        # whose words are Reddit's embed page's text (`flattened`: an edited comment's, Noemi's decision 3 of 15 Oct
        # 2026), where a quoted block of someone else's words, a list or a heading reads like the writer's own
        # sentences.
        self.widen = {cid: body for cid, body in bodies.items() if cid not in flattened} if flattened else bodies
        self.dropped = 0
        # {comment id: the names (as shown, and as written) of every product it names}, for quote order (17 Oct 2026:
        # _names_another_first); set by write_answer from the ranking.
        self.named_in: Mapping[str, tuple[tuple[str, str], ...]] = {}

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
                  product_type: str | None = None,
                  named_in: Mapping[str, tuple[tuple[str, str], ...]] | None = None) -> list[ScoredMention]:
    """The most credible first, but the quotes that name their product and give a view before those that only name
    it, those before the ones that only give a view, and those before the rest; within each, those whose comment talks about what the request asks for first (10 Oct 2026: out of context, a line that only opens a list of other products the
    writer has had no trouble with says little, and so does a list of the grinders someone owns), and a quote that says the opposite of what
    the request asks ("does leave a white cast"), or a recommendation's quote saying its product didn't help with a
    need ("it did nothing for my oily skin", 15 Oct 2026), after every other (_says_the_opposite). Each is still shown when
    there's room. Since 12 Oct 2026 the quotes of `leaning` (comment ids: quotes that lean on the thread, _standing) come
    after all of these, and a quote saying the product isn't really the `product_type` asked for (that it
    isn't really a moisturiser) counts as saying the opposite of the request (_not_the_type).

    Since 15 Oct 2026 (Noemi's decision 4: a quote must be the most coherent part of its comment for the stance it backs)
    a quote whose own words carry its stance gives a view (carries_its_stance: "never had a single issue" for a
    recommendation, "the lid cracked within a month" for a warning), and one whose words read against it
    (reads_against_its_stance: a recommendation's quote telling only of a failure, even after a long life; a warning's
    only praising) comes after every other quote, before only those saying the opposite of the request and those leaning
    on the thread. The order changes, never a quote's words. So does a quote about another product of its comment
    (_about_another_product: the writer's carbon steel skillet in a cast iron pick).

    Then the most informative for the request first (15 Oct 2026, the coordinator's trial comparison with ChatGPT and
    Vetted: testers see a pick's first quotes): within each tier, a quote talking about what the request asks for, then
    one saying why otherwise (_says_why: which need, how long, a view with something behind it), then the rest, and a
    bare like last ("I love the X": _bare_like), which doesn't count as a view.

    Since 17 Oct 2026 (the converge round, within her rule 4) a quote that opens by agreeing with another writer
    (_opens_by_agreeing: "Agreed; ...", "Seconded.", "Yeah ..."), names another product of its comment before its own
    (_names_another_first, from `named_in`: {comment id: the names of the products it names}) or tells someone else's
    experience (_hearsay: "my sister swears by it", "apparently") comes after a clearer quote of its tier that says as
    much for the request (informative): last of its kind, never after a quote that names less or says less."""
    ordered = _most_credible_first(items)

    # 0: names it and gives a view; 1: only names it; 2: only gives a view; 3: neither (10 Oct 2026, night: b04 showed a
    # writer still looking for a richer cream before one who swears by it, neither naming it).
    def tier(m: ScoredMention) -> int:
        names = _names_product(m.quote, m.product_name, m.category, m.written_as)
        view = (_gives_a_view(m.quote) or carries_its_stance(m.quote, m.stance, _its_names(m))) and not _bare_like(m)
        return 0 if names and view else 1 if names else 2 if view else 3

    # Within a tier, quotes that themselves talk about what the request asks for come first (10 Oct 2026, late: a kettle
    # pick led with a comment about its handle, not one of its writers' years of use). The quote, not its comment. Then
    # (15 Oct 2026) those that say why otherwise, the rest, and bare likes last.
    def informative(m: ScoredMention) -> int:
        if needs and needs_met(m.quote, needs, m.evidence == "long-term use"):
            return 0
        return 1 if _says_why(m) else 3 if _bare_like(m) else 2

    # A recommendation whose quote says its product didn't help with one of the needs ("it did nothing for my oily
    # skin") talks about it against the request too (engine.needs.said_not_to_help, 15 Oct 2026); a warning's doesn't.
    def opposite(m: ScoredMention) -> bool:
        return (_says_the_opposite(m.quote, asks) or _not_the_type(m.quote, product_type)
                or (m.stance == "recommend" and bool(said_not_to_help(m.quote, needs))))

    def against(m: ScoredMention) -> bool:
        return reads_against_its_stance(m.quote, m.stance, _its_names(m)) or _about_another_product(m)

    def unclear(m: ScoredMention) -> bool:
        return (_opens_by_agreeing(m.quote) or _hearsay(m.quote)
                or _names_another_first(m, (named_in or {}).get(m.comment_id, ())))

    return sorted(ordered, key=lambda m: (m.comment_id in leaning, opposite(m), against(m), tier(m), informative(m),
                                          unclear(m)))


# A reply's opening agreement with another writer (17 Oct 2026, the converge round): "Agreed; ...", "Seconded.", "Yeah
# my ...", "I second the ...", "+1", "Same here", "This!", "Came here to say", "Can confirm", "I also use ...". It leans on
# a comment the reader doesn't see, so a clearer quote of the same stance comes first (_naming_first).
_AGREEING = re.compile(
    r"^\W*(?:yes|yeah|yea|yep|yup|agreed|agree|i agree|totally agree|completely agree|fully agree|100% agree"
    r"|seconded|seconding|second(?:ing)? this|i second|i'd second|second|thirded|thirding|third for|\+1|same(?: here)?"
    r"|ditto|exactly"
    r"|this(?=\s*[.!,]|\s*$)|came here to (?:say|post|recommend|suggest)|was (?:going|about) to (?:say|post|suggest)"
    r"|can confirm|i can confirm|me too|i also|also (?:a fan|love|recommend|vote|use|team)|another (?:vote|fan|one) for"
    r"|(?:big |huge )?(?:\+1|vote) for)(?![\w'-])", re.IGNORECASE)


def _opens_by_agreeing(quote: str) -> bool:
    """Whether a quote opens by agreeing with another writer (_AGREEING)."""
    return bool(_AGREEING.match(_plain(quote)))


def _hearsay(quote: str) -> bool:
    """Whether a quote tells someone else's experience or what the writer heard, not their own use, by module 5's
    reading of first-hand use (engine.credibility: "my sister swears by it", "apparently it never fails", "I've heard")."""
    level, reasons = _proof_of_use(_plain(quote), None)
    return level == "no first-hand use" and bool(set(reasons) & HEARSAY_REASONS)


# Module 5's reasons for someone else's experience and for hearsay (engine.credibility._proof_of_use).
HEARSAY_REASONS = frozenset({_SECONDHAND_REASON, "heard about it, not used"})


def _names_another_first(m: ScoredMention, named: Iterable[tuple[str, str]]) -> bool:
    """Whether a quote names another product of its comment before its own (named: the names, as shown and as written,
    of every product its comment names): that product's own word (the first word of its name its product's names don't
    hold, a brand, as names_another_product finds it) comes first, or it alone is named."""
    text = " ".join(_split_words(m.quote))
    own_at = _first_at(text, {w for name in _its_names(m) for w in _split_words(name) if w not in FILLER_WORDS
                              and w not in GENERIC_NAME_WORDS})
    own = {word for name in _its_names(m) for word in _split_words(name)}
    for name, written in named:
        if name == m.product_name:
            continue
        for other in (name, written):
            distinct = [w for w in dict.fromkeys(_split_words(other)) if w not in own and w not in FILLER_WORDS
                        and w != "and"]
            brand = next((w for w in distinct if w not in GENERIC_NAME_WORDS), None)
            other_at = _first_at(text, {brand}) if brand else None
            if other_at is not None and (own_at is None or other_at < own_at):
                return True
    return False


def _first_at(text: str, words: Collection[str]) -> int | None:
    """Where the first of these words is in a text of words (_split_words joined by spaces), or None."""
    found = [m.start() for word in words if word for m in [re.search(rf"(?<![a-z0-9']){re.escape(word)}(?![a-z0-9'])",
                                                                      text)] if m]
    return min(found) if found else None


def _picks_names(ranking: RankingResult, picks: Iterable["Pick"]) -> list[str]:
    """Every name the picks go by: each one's shown name and the names its writers give it (ScoredMention.written_as:
    "Stagg gooseneck kettle" for the Fellow Stagg EKG), which say what kind of product it is as its name does (17 Oct
    2026: What to look for never warns against a pick's own kind)."""
    by_key = {p.key: p for p in ranking.products}
    names: list[str] = []
    for pick in picks:
        names.append(pick.name)
        product = by_key.get(pick.product_key)
        names += [m.written_as for m in (product.mentions if product else ()) if m.written_as]
    return list(dict.fromkeys(names))


class _Once:
    """What a function gives, worked out the first time it is asked for (latency, 18 Oct 2026)."""

    def __init__(self, work):
        self._work, self._done, self._value = work, False, None

    def __call__(self):
        if not self._done:
            self._value, self._done = self._work(), True
        return self._value


def _lines_products(ranking: RankingResult, picks: Iterable["Pick"], product_type: str | None) -> list[str]:
    """The names of the products ranked under each pick's own name, as shown and as their writers give them, of the
    type asked for (18 Oct 2026): a brand or line pick holds them ("Bonavita variable temperature gooseneck" under the
    Bonavita kettle line, "OXO adjustable temp kettle" under OXO's), so they say which kinds of the type it is. Only
    those its credible writers recommend, which are what the pick stands for (a model they only warn against isn't);
    never one whose name names another type ("Lodge enameled cast iron Dutch oven" under the Lodge skillet line)."""
    names: list[str] = []
    for pick in picks:
        under = pick.product_key + " "
        for product in ranking.products:
            if (product.key.startswith(under) and product.credible_recommendations
                    and not (_named_types(product.name, ranking.category) - {product_type})):
                names += [product.name, *(m.written_as for m in product.mentions if m.written_as)]
    return list(dict.fromkeys(names))


def _named_in(ranking: RankingResult) -> dict[str, tuple[tuple[str, str], ...]]:
    """{comment id: the names, as shown and as written, of every product of the ranking it names} (17 Oct 2026)."""
    found: dict[str, dict[tuple[str, str], None]] = {}
    for product in ranking.products:
        for m in product.mentions:
            found.setdefault(m.comment_id, {})[(m.product_name, m.written_as)] = None
    return {cid: tuple(names) for cid, names in found.items()}


def _not_the_type(quote: str, product_type: str | None) -> bool:
    """Whether a quote says its product isn't (really) the type of product asked for: "not a moisturizer", "I don't feel
    like it's a 'moisturizer'" (b04, 12 Oct 2026), by the type's name or one of module 1's names for it."""
    if not product_type:
        return False
    key = (quote, product_type)
    found = _NOT_THE_TYPE.get(key)
    if found is None:
        names = {product_type, *(k for p in PRODUCT_TYPES if p.name == product_type for k in p.keywords)}
        text = _plain(quote)
        found = _NOT_THE_TYPE.keep(key, any(
            re.search(rf"(?:\bnot\b|n't\b)[^.!?]{{0,30}}?\b(?:an?|real|really)\W+{re.escape(name)}s?\b", text)
            for name in names))
    return found


def _says_something(m: ScoredMention) -> bool:
    """Whether a quote names its product, gives a view, or points at it ("it", "this one", "mine"). One that does none
    of these (b08, 10 Oct 2026: a one-line reply about sticking with cast iron was shown for two vintage brands; the
    comment named them in a sentence the AI didn't quote) is shown only to make up a pick's MIN_QUOTES_PER_PICK. Since
    15 Oct 2026 words carrying its stance say something too ("no issues after two winters": carries_its_stance)."""
    text = " ".join(re.findall(r"[a-z0-9']+", m.quote.lower().replace("’", "'")))
    return (_names_product(m.quote, m.product_name, m.category, m.written_as) or _gives_a_view(m.quote)
            or bool(_POINTS_AT_IT.search(text)) or carries_its_stance(m.quote, m.stance, _its_names(m)))


# Words that point at a product already named ("I'm on my fifth bottle of it", "I've had mine for years").
_POINTS_AT_IT = re.compile(r"(?<![a-z0-9'])(?:it|it's|its|this|these|those|them|they|they're|mine|ones?)(?![a-z0-9'])")
# "I like it", "I really like the gel": a view. Not "I would like" (a wish), nor "like" alone ("features like a scale").
_I_LIKE = re.compile(r"\bi (?:(?:really|also|do|still|just|honestly|actually|genuinely|personally|definitely"
                     r"|absolutely|quite) )?like[sd]?\b")


def _gives_a_view(quote: str) -> bool:
    """Whether the quote says what the writer thinks or went through (config.QUOTE_VIEW_WORDS: "great", "recommend",
    "lasted"..., or "I like"), rather than only that they own it."""
    found = _GIVES_A_VIEW.get(quote)
    if found is None:
        text = " ".join(re.findall(r"[a-z0-9']+", quote.lower().replace("’", "'")))
        found = _GIVES_A_VIEW.keep(quote, any(re.search(rf"(?<![a-z0-9']){re.escape(word)}(?![a-z0-9'])", text)
                                              for word in QUOTE_VIEW_WORDS) or bool(_I_LIKE.search(text)))
    return found


# What a quote shows, worked out once per quote (latency, 13 Oct 2026: an answer asks the same of each quote over and
# over, as it orders, widens and picks them): each depends on the words it is given alone.
_GIVES_A_VIEW = Table()  # quote -> _gives_a_view
_NAMES_PRODUCT = Table()  # (quote, name, category, writer's name) -> _names_product
_SAYS_THE_OPPOSITE = Table()  # (quote, asks) -> _says_the_opposite
_NOT_THE_TYPE = Table()  # (quote, product type) -> _not_the_type


def says_the_opposite(quote: str, asks: Iterable[str]) -> bool:
    """Whether the quote says the opposite of one of the request's asks (_says_the_opposite); the pipeline uses it too."""
    return _says_the_opposite(quote, asks)


def _says_the_opposite(quote: str, asks: Iterable[str]) -> bool:
    """Whether the quote says the opposite of one of the request's asks (config.OPPOSITE_QUOTE_PATTERNS): "it leaves a
    white cast" for "no white cast", "smells lovely" for "fragrance-free", "way too drying" for "not drying" (14 Oct
    2026). For the asks of config.OPPOSITE_NEGATED_IN_SENTENCE, a match with a negation just before it in its sentence
    doesn't count (_negated_before: "none of the three ever stripped my face")."""
    asks = tuple(asks)
    key = (quote, asks)
    found = _SAYS_THE_OPPOSITE.get(key)
    if found is None:
        text = " ".join(quote.lower().replace("’", "'").split())
        found = _SAYS_THE_OPPOSITE.keep(key, any(_opposite_in(text, pattern, ask in OPPOSITE_NEGATED_IN_SENTENCE)
                                                 for ask in asks for pattern in OPPOSITE_QUOTE_PATTERNS.get(ask, ())))
    return found


def _opposite_in(text: str, pattern: str, unless_negated: bool) -> bool:
    """Whether `pattern` is found in the quote's `text`, and, `unless_negated`, once with no negation just before it."""
    if not unless_negated:
        return re.search(pattern, text) is not None
    return any(not _negated_before(text, match.start()) for match in re.finditer(pattern, text))


# A word that negates what follows it: "not", "no", "none", "neither", "without", "less", any "...n't" ("doesn't",
# "wasn't") and the same written without an apostrophe ("doesnt", "wasnt").
_NEGATION_WORD = re.compile(r"(?:not|no|non|none|never|neither|nor|without|less|hardly|cannot|\w+n't"
                            r"|(?:is|are|was|were|does|do|did|has|have|had|would|could|should|wo|ca)nt)")
# Where a sentence's part ends for a negation: a full stop, a question or exclamation mark, a semicolon, or "but",
# "though", "although", "however", "because" ("not a daily one for me, but it strips my hair", "I wouldn't reach for it
# each morning because it strips my skin").
_CLAUSE_END = re.compile(r"[.!?;]|\b(?:but|though|although|however|because)\b")


def _negated_before(text: str, at: int) -> bool:
    """Whether a negation is among the config.OPPOSITE_NEGATION_WINDOW words just before `at` in its sentence's part:
    "neither has ever dried my hair out", "it doesn't burn, smell or strip the skin" (14 Oct 2026)."""
    part = _CLAUSE_END.split(text[:at])[-1]
    words = [word.strip(",/()\"'*-:") for word in part.split()][-OPPOSITE_NEGATION_WINDOW:]
    return any(_NEGATION_WORD.fullmatch(word) for word in words)


# --- Quotes coherent with their stance (Noemi's decision 4 of 15 Oct 2026) ---

def carries_its_stance(quote: str, stance: str, names: Iterable[str] = ()) -> bool:
    """Whether the quote's own words carry the stance it backs: a recommendation's praise, how it held up or an
    endorsement ("still going strong", "never had a single issue", "get the X"), a warning's failure, complaint or
    advice against ("the lid cracked", "not worth it", "avoid it"). `names`: the product's names, whose words together
    say nothing ("Perfect Gel" is no praise). See config.QUOTE_FAILURE_PATTERNS."""
    words = _stance_words(quote, tuple(names))
    return words.positive if stance == "recommend" else words.negative if stance == "warn" else False


def reads_against_its_stance(quote: str, stance: str, names: Iterable[str] = ()) -> bool:
    """Whether the quote's own words read against the stance it backs: a recommendation's quote telling only of a
    failure or a complaint ("we had it 14 years and then the backlight gave out"), a warning's quote only praising ("I
    loved it at first"). Not when the words turn after them ("the handle broke, but they sent a new one"; "great the
    first day, but since then it rides up"): the quote ends on its stance."""
    words = _stance_words(quote, tuple(names))
    if stance == "recommend":
        return words.negative and not words.positive and not words.turns_after_negative
    if stance == "warn":
        return words.positive and not words.negative and not words.turns_after_positive
    return False


@dataclass(frozen=True)
class _StanceWords:
    """What a quote's words tell, read once: something gone wrong or advice against it (negative: a failure, a
    complaint, praise taken back), praise or how it held up (positive: praise, a failure taken back), and whether the
    quote turns ("but", "until", "then"...) after the last of each."""

    negative: bool
    positive: bool
    turns_after_negative: bool
    turns_after_positive: bool


# Each family as one pattern, read in one pass (latency: one pass per pattern took about 0.6 ms a quote).
_FAILURES = re.compile("|".join(f"(?:{pattern})" for pattern in QUOTE_FAILURE_PATTERNS))
_ADVICE_AGAINST = re.compile("|".join(f"(?:{pattern})" for pattern in QUOTE_ADVICE_AGAINST_PATTERNS))
_PRAISE = re.compile("|".join(f"(?:{pattern})" for pattern in QUOTE_PRAISE_PATTERNS))
# A negation word, as _NEGATION_WORD, with "zero", "nobody", "nothing", "barely" ("zero regrets", "barely ever had
# leaks", "nothing has broken"), and never "not" after "why" ("why not just get the X?"). "Less" takes back praise only
# ("less durable"), "minimal" a failure only ("minimal pilling").
_STANCE_NEGATION = re.compile(r"(?:not|no|non|none|never|neither|nor|without|hardly|barely|rarely|seldom|cannot|zero"
                              r"|nobody|nothing|\w+n't"
                              r"|(?:is|are|was|were|does|do|did|has|have|had|would|could|should|wo|ca)nt)")
_PRAISE_ONLY_NEGATION = frozenset({"less"})
_FAILURE_ONLY_NEGATION = frozenset({"minimal"})
# Where a part of a sentence ends for a negation (config.QUOTE_STANCE_NEGATION_WINDOW): as _CLAUSE_END, and "until",
# "then", or a comma before a new subject ("Not Ring, it's junk").
_STANCE_PART_END = re.compile(r"[.!?;]|\b(?:but|though|although|however|because|until|till|then)\b"
                              r"|,\s+(?=(?:it|it's|its|they|they're|i|i'm|i've|we|we're|you|you're|this|that|which"
                              r"|so)\b)")
_STANCE_LIST = re.compile(r"or|nor|and")
# Words that don't use up the negation's window: "barely ever had leaks", "never even once broke", "never had any
# rust", "not at all disappointed", "didn't seem very comfortable", "not nearly as durable", and "that" after "all"
# ("isn't all that bad").
_NOT_COUNTED = frozenset({"ever", "even", "once", "really", "actually", "honestly", "truly", "yet", "still", "so",
                          "far", "any", "single", "all", "as", "nearly", "very", "at", "too", "quite", "much"})
_A_WISH = re.compile(r"\b(?:wish|wished|if only|hopefully|hoping)\b")  # "I wish mine held up this well": no praise
_WANTED_TO = re.compile(r"\b(?:wanted|wanting|want|hoped|hoping) to\s+(?:really\s+)?$")  # "I so wanted to love it"
# Praise that is other people's, not the writer's: "most people love it", "everyone swears by it", "I've heard great
# things".
_OTHERS_PRAISE = re.compile(r"\b(?:people|everyone|everybody|folks|others|reviewers|saw|seen|heard)"
                            r"(?:\s+(?:all|really|just|always|seem to|seems to|tend to))?\s+$")
# A complaint word said of the state that sends the writer to the product, not of the product: "when my lips get really
# bad, I use it". A word among this many before it in its part of the sentence makes it so.
_COMPLAINT_WORD = re.compile(r"bad|terrible|awful|horrible|horrendous|dreadful|worst")
_A_CONDITION = re.compile(r"when|whenever|if")
_CONDITION_WORDS = 5
_STANCE_TURN = re.compile(r"\b(?:but|however|though|although|until|till|then|except|unfortunately|sadly|yet|before)\b")
# A failure that may come, not one that came: a present-tense one after "if", "when", "once"... ("if it ever breaks").
_PRESENT_FAILURE = re.compile(r"(?:dies|breaks|fails|quits|leaks|cracks|rusts|warps|chips|gives out|goes out"
                              r"|stops working|wears out|falls apart|craps out)\b")
_MAYBE_LATER = re.compile(r"if|when|whenever|once|unless|until|before|eventually")
_PEOPLE_WORDS = frozenset(QUOTE_STANCE_PEOPLE_WORDS)
_STANCE_WORDS = Table()  # (quote, names) -> _StanceWords


def _stance_words(quote: str, names: tuple[str, ...]) -> _StanceWords:
    key = (quote, names)
    found = _STANCE_WORDS.get(key)
    if found is None:
        found = _STANCE_WORDS.keep(key, _stance_words_of(_without_names(" ".join(_plain(quote).split()), names)))
    return found


def _stance_words_of(text: str) -> _StanceWords:
    negative = positive = False
    last_negative = last_positive = -1
    for pattern, praise in ((_FAILURES, False), (_ADVICE_AGAINST, None), (_PRAISE, True)):
        for match in pattern.finditer(text):
            if _someones_death(text, match) or _may_come(text, match):
                continue
            if praise is True and _OTHERS_PRAISE.search(text, 0, match.start()):
                continue
            if praise is False and _a_condition(text, match):
                continue
            # "So far so good" is said whole: an earlier "without" doesn't take it back.
            negated = (not match.group(0).startswith("so far")
                       and _stance_negated(text, match.start(), praise is True))
            if praise is None and negated:  # advice against taken back says nothing either way
                continue
            if (praise is None) or (praise is negated):  # a failure or advice against, or praise taken back
                negative, last_negative = True, max(last_negative, match.end())
            else:  # praise, or a failure taken back: how it held up
                positive, last_positive = True, max(last_positive, match.end())
    return _StanceWords(negative, positive, _turns_after(text, last_negative), _turns_after(text, last_positive))


def _stance_negated(text: str, at: int, praise: bool) -> bool:
    """Whether a negation is among the config.QUOTE_STANCE_NEGATION_WINDOW words just before `at` in its part of the
    sentence (twice as many when "or", "nor" or "and" are among them); for praise, also a wish anywhere before it in
    that part."""
    part = _STANCE_PART_END.split(text[:at])[-1]
    if praise and (_A_WISH.search(part) or _WANTED_TO.search(part)):
        return True
    raw = [w.strip(",/()\"'*-:") for w in part.split()]
    words = [word for i, word in enumerate(raw)
             if word not in _NOT_COUNTED and not (word == "that" and i > 0 and raw[i - 1] == "all")]
    size = QUOTE_STANCE_NEGATION_WINDOW
    if words and _STANCE_LIST.fullmatch(words[-1]):  # the list's last item: "didn't chip, crack or warp"
        size *= 2
    start, near = max(len(words) - size, 0), len(words) - QUOTE_STANCE_NEGATION_WINDOW
    only = _PRAISE_ONLY_NEGATION if praise else _FAILURE_ONLY_NEGATION
    # "Nothing" reaches only the window itself, never across a list; "more or less" is "about".
    return any((_STANCE_NEGATION.fullmatch(word) or word in only) and not (word == "nothing" and i < near)
               and not (word == "not" and i > 0 and words[i - 1] == "why")
               and not (word == "less" and i > 0 and words[i - 1] == "or")
               for i, word in enumerate(words[start:], start))


def _a_condition(text: str, match: re.Match) -> bool:
    """Whether a complaint word tells of the state that sends the writer to the product ("when my lips get really bad,
    I use it"), not of the product."""
    if not _COMPLAINT_WORD.fullmatch(match.group(0)):
        return False
    part = _STANCE_PART_END.split(text[:match.start()])[-1]
    before = [word.strip(",/()\"'*-:") for word in part.split()][-_CONDITION_WORDS:]
    return any(_A_CONDITION.fullmatch(word) for word in before)


def _someones_death(text: str, match: re.Match) -> bool:
    """Whether "died" or "dies" tells of a person's or a pet's death ("my grandma died and left me her pans")."""
    if match.group(0) not in ("died", "dies", "dying"):
        return False
    before = [word.strip(",/()\"'*-:").removesuffix("'s") for word in text[:match.start()].split()][-2:]
    return any(word in _PEOPLE_WORDS for word in before)


def _may_come(text: str, match: re.Match) -> bool:
    """Whether a failure is one that may come ("if it ever breaks", "when it finally gives out"), not one that came."""
    if not _PRESENT_FAILURE.search(match.group(0)):
        return False
    before = [word.strip(",/()\"'*-:") for word in text[:match.start()].split()][-3:]
    return any(_MAYBE_LATER.fullmatch(word) for word in before)


def _turns_after(text: str, at: int) -> bool:
    return at >= 0 and _STANCE_TURN.search(text, at) is not None


def _without_names(text: str, names: tuple[str, ...]) -> str:
    """The text with each run of two or more words of the product's names put as "it": the name says nothing of the
    product ("the Perfect Gel did nothing for me" is no praise). One word of a name alone is the writer's own ("it's
    perfect")."""
    words = {word.removesuffix("'s") for name in names for word in _NAME_TOKEN.findall(_plain(name))}
    if not words:
        return text
    spans, run = [], []
    for token in _NAME_TOKEN.finditer(text):
        if token.group().removesuffix("'s") in words and (
                not run or _NAME_JOIN.fullmatch(text[run[-1].end():token.start()])):
            run.append(token)
            continue
        if len(run) >= 2:
            spans.append((run[0].start(), run[-1].end()))
        run = [token] if token.group().removesuffix("'s") in words else []
    if len(run) >= 2:
        spans.append((run[0].start(), run[-1].end()))
    for start, end in reversed(spans):
        text = text[:start] + "it" + text[end:]
    return text


_NAME_TOKEN = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
_NAME_JOIN = re.compile(r"[\s-]*")


def _its_names(m: ScoredMention) -> tuple[str, ...]:
    """The product's names a quote may hold: the name it is shown under, and its writer's own."""
    return tuple(name for name in (m.product_name, m.written_as) if name)


# --- The most informative for the request first (15 Oct 2026, the coordinator's trial comparison) ---

def _about_another_product(m: ScoredMention) -> bool:
    """Whether the quote is about another product of its comment: one of the comment's other products of another type,
    with the same stance (module 3's: ScoredMention.others_of_another_type), named in it (names_another_product)."""
    return names_another_product(m.quote, _its_names(m), m.others_of_another_type)


def names_another_product(quote: str, names: Iterable[str], others: Iterable[str]) -> bool:
    """Whether the quote names one of `others` (products of another type, as their writer wrote them) by the words of
    its name that the product's own `names` don't have: its first one that isn't a generic product word (its brand:
    "Matfer"), or, when it has none (the same brand), all of them ("carbon steel" for a writer's "Lodge carbon steel
    skillet" in a "Lodge cast iron" quote; never "steel pan" for a Matfer carbon steel pan)."""
    own = {word for name in names for word in _split_words(name)}
    words = set(_split_words(quote))
    for other in others:
        distinct = [w for w in dict.fromkeys(_split_words(other)) if w not in own and w not in FILLER_WORDS
                    and w != "and"]
        brand = next((w for w in distinct if w not in GENERIC_NAME_WORDS), None)
        if (brand in words) if brand is not None else (bool(distinct) and all(w in words for w in distinct)):
            return True
    return False


def _says_why(m: ScoredMention) -> bool:
    """Whether the quote says why, beyond liking it: which need it suits, in the words of any need (config.NEEDS and
    HAIR_NEEDS: "my dry, sensitive skin", "no breakouts"), how long the writer has had it ("for 12 years", "since 2015",
    a grandmother's pan), or a view with something behind it: at least WHY_WORDS words besides its names, small words
    and likes ("it pours so nicely and feels well built")."""
    found = _SAYS_WHY.get((m.quote, m.stance, _its_names(m)))
    if found is None:
        text = " ".join(_plain(m.quote).split())
        found = _names_a_need(text) or bool(_HOW_LONG.search(text))
        if not found and (_gives_a_view(m.quote) or carries_its_stance(m.quote, m.stance, _its_names(m))):
            found = len(_content_words(m.quote, _its_names(m))) >= WHY_WORDS
        _SAYS_WHY.keep((m.quote, m.stance, _its_names(m)), found)
    return found


def _bare_like(m: ScoredMention) -> bool:
    """Whether the quote only likes the product ("I love the Acme cleanser", "Oddly, I really like the Cream to Foam",
    "The best I've tried is from Acme!!!"): a like, and no word besides its names, small words and likes. One word can
    be the reason ("great, very sharp")."""
    text = " ".join(_plain(m.quote).split())
    return bool(_A_LIKE.search(text)) and not _content_words(m.quote, _its_names(m))


def _content_words(quote: str, names: tuple[str, ...]) -> list[str]:
    """The quote's words besides the product's names, small words (_SMALL_WORDS) and likes (_LIKE_WORDS)."""
    own = {word for name in names for word in _split_words(name)}
    return [word for word in _split_words(quote) if word not in own and word not in _SMALL_WORDS
            and word not in _LIKE_WORDS]


def _split_words(text: str) -> list[str]:
    """A text's words, lowercase, split at hyphens too ("Cream-to-Foam"), a possessive "'s" dropped."""
    return [word.removesuffix("'s") for word in _NAME_TOKEN.findall(_plain(text))]


WHY_WORDS = 3  # a view with at least this many words besides names, small words and likes says why (15 Oct 2026)
# Any need's words, as engine.needs finds them: a word at a word's start ("sensitiv" in "sensitivity"), a phrase whole.
_NEED_WORDS = frozenset(w.lower() for words in (*NEEDS.values(), *HAIR_NEEDS.values()) for w in words
                        if re.fullmatch(r"[a-z0-9]+", w.lower()))
_NEED_PHRASES = tuple((w.lower(), re.compile(rf"(?<![a-z0-9]){re.escape(w.lower())}s?(?![a-z0-9])"))
                      for words in (*NEEDS.values(), *HAIR_NEEDS.values()) for w in words
                      if not re.fullmatch(r"[a-z0-9]+", w.lower()))
_NEED_WORD_LENGTHS = sorted({len(w) for w in _NEED_WORDS})


def _names_a_need(text: str) -> bool:
    """Whether a lowercase text holds any need's words (config.NEEDS, HAIR_NEEDS), as engine.needs finds them."""
    for token in re.findall(r"[a-z0-9]+", text):
        if any(token[:n] in _NEED_WORDS for n in _NEED_WORD_LENGTHS if n <= len(token)):
            return True
    return any(phrase in text and pattern.search(text) for phrase, pattern in _NEED_PHRASES)
_HOW_LONG = re.compile(
    r"\b(?:\d+|a|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty"
    r"|a few|a couple(?: of)?|several|many)\+? (?:years?|yrs?|months?|decades?|winters?|summers?)\b|\bdecades?\b"
    r"|\bsince (?:19|20)\d\d\b|\b(?:in|from|back in) (?:19|20)\d\d\b|\bfor (?:years|ages|decades|a long time)\b"
    r"|\b(?:great[- ])?grand(?:mother|father|ma|pa|parents?)(?:'s)?\b|\binherited\b|\bheirloom\b"
    r"|\b(?:handed|passed) down\b")
_A_LIKE = re.compile(r"\b(?:lov(?:e|ed|es|ing)|lik(?:e|ed|es)|best|favou?rite|fave|great|amazing|awesome|obsessed|hg"
                     r"|holy grail)\b")
_SMALL_WORDS = frozenset({
    "i", "i'm", "i've", "i'd", "i'll", "im", "ive", "me", "my", "mine", "we", "our", "us", "you", "your", "it", "it's",
    "its", "this", "that", "these", "those", "they", "them", "their", "the", "a", "an", "and", "or", "so", "to", "of",
    "in", "on", "at", "for", "from", "by", "with", "is", "are", "was", "were", "be", "been", "am", "has", "have", "had",
    "do", "does", "did", "just", "really", "very", "too", "also", "still", "absolutely", "totally", "honestly", "oddly",
    "personally", "definitely", "seriously", "literally", "pretty", "quite", "much", "lol", "omg", "one", "ones",
    "brand", "stuff", "product", "thing", "things", "all", "now", "here", "there", "what", "which", "who", "s",
    "but", "not", "no", "nor", "if", "as", "than", "then", "when", "while", "because", "about", "more", "less", "can",
    "could", "would", "will", "should", "may", "might", "must", "how", "why", "where", "any", "some", "every", "each",
    "other", "others", "another", "same", "such", "out", "up", "down", "over", "again", "ever", "yet", "both", "either",
    "way", "lot", "bit", "kind", "sort", "t", "don", "isn", "wasn", "didn", "doesn",
    # Having or trying it says nothing more ("The best I've tried").
    "tried", "try", "trying", "used", "use", "using", "own", "owned", "got", "get", "bought", "buy", "found", "find",
    "picked", "go", "went", "ve", "ll", "d", "m"})
_LIKE_WORDS = frozenset({
    "love", "loved", "loves", "loving", "like", "liked", "likes", "great", "best", "amazing", "awesome", "good",
    "favourite", "favorite", "fave", "fan", "big", "huge", "hg", "holy", "grail", "nice", "lovely", "fantastic",
    "excellent", "perfect", "recommend", "recommended", "obsessed", "loveeee", "loove"})
_SAYS_WHY = Table()  # (quote, stance, names) -> _says_why


def _names_product(quote: str, name: str, category: str, written_as: str = "") -> bool:
    """Whether the quote names the product: the first word of its name (the brand), a model code in it (a word
    with a digit: "C2", "MTH-80"), or a known short or long form of its brand (engine/data/product_aliases.json:
    "BOJ" for Beauty of Joseon, "Breville" for Sage), as whole words, capitals aside. A plural or a possessive counts
    ("old wagners", "Prequel's"), and so does a hyphen written as a space or left out ("All clad" for All-Clad; b08,
    b05 and b10, 10 Oct 2026). So does the first word of the writer's own name for it (`written_as`; "my" or "the"
    aside, and never a common product word such as "gooseneck"): "Stagg" for a kettle shown as "Fellow Stagg EKG"
    (b06, 10 Oct 2026, night: its writers' quotes had stopped naming it once the shown name took its brand). A name that
    is an everyday short word too (COMMON_SHORT_WORDS: "TO" for The Ordinary) names it only in capitals (12 Oct 2026)."""
    key = (quote, name, category, written_as)
    found = _NAMES_PRODUCT.get(key)
    if found is None:
        found = _NAMES_PRODUCT.keep(key, _names_product_of(quote, name, category, written_as))
    return found


def _names_product_of(quote: str, name: str, category: str, written_as: str) -> bool:
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
    mentions, leaning = _standing(product.credible_recommendations, check.widen, _names_its_product)
    ordered = _naming_first(_with_a_view(mentions, check.widen), asks, needs, leaning, product_type, check.named_in)
    standing = [m for m in ordered if m.comment_id not in leaning]

    def filler(m: ScoredMention) -> bool:  # since 15 Oct 2026 also a quote about another product of its comment
        return _bare_mention(m) or _garbled(m.quote) or _about_another_product(m)

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
        mentions, group_leaning = _standing(group, check.widen, _names_its_product)
        ordered += _naming_first(mentions, needs=needs, leaning=group_leaning, named_in=check.named_in)
        leaning |= group_leaning
    shown = check.first([m for m in ordered if m.comment_id not in leaning], limit)
    return shown or check.first([m for m in ordered if m.comment_id in leaning], 1)


def _pick(rank: int, product: ProductScore, quotes: list[ShownQuote], check: _QuoteCheck, ranking: RankingResult,
          price: ShownPrice, care: list[ShownCareTip], availability: ShownAvailability = NOT_CHECKED,
          cautions: list[str] | None = None, more_downsides: list[ScoredMention] = (),
          needs: tuple[Need, ...] = (), said: "_SaidNeeds | None" = None) -> Pick:
    """One pick. `more_downsides`: credible warnings about the pick's own brand or line, shown after its own (the
    pipeline's _fold_brand_skips, 10 Oct 2026). `needs`: warnings that talk about them come first among equally clear
    ones ("when my bonavita broke" for a kettle that should last). `said`: how its reason names them (_said_needs)."""
    warnings = product.credible_warnings
    downsides = _warning_quotes((warnings, more_downsides), check, DOWNSIDES_PER_PICK, needs)
    said = said or _said_needs(needs)
    return Pick(
        rank=rank,
        product_key=product.key,
        name=product.name,
        reason=_reason(product, ranking, order=tuple(need.name for need in needs), shown=said.labels,
                       hidden=said.hidden),
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


def _voices(product: ProductScore, more_downsides: Iterable[ScoredMention] = (), twice: bool = True) -> dict[str, int]:
    """The credible voices behind a pick or an "Also worth a look" item, as numbers for the page's credibility meter (13
    Oct 2026, the UX builder): its credible recommendations (as the reason counts them), of them the high and the medium
    voices (as the support line does), the writers who warned against it (_warned, as the share line and the
    mixed-opinions line do) and the threads with a credible recommendation (as the support line does). So the meter
    never disagrees with the words around it. Numbers only, like the breakdown; the score itself isn't in it.

    With Noemi's upvote rule (14 Oct 2026) the numbers stay the writers', and "twice" says how many of them counted
    twice toward the picks bar for their upvotes, as the reason does: only when some did (and `twice`, a pick's), so
    nothing changes while the rule is off."""
    recommendations = product.credible_recommendations
    voices = {"recommend": len(recommendations),
              "high": sum(m.voice == "high" for m in recommendations),
              "medium": sum(m.voice == "medium" for m in recommendations),
              "warn": len(_warned(product, more_downsides)),
              "threads": product.breakdown.credible_threads}
    if twice and product.counted_twice:
        voices["twice"] = len(product.counted_twice)
    return voices


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


def _need_labels(needs: Iterable[Need]) -> dict[str, str]:
    """{a need's name: how the answer names it}, for needs named otherwise than by their name: two words that make one
    need, named whole (engine.needs.Need.label, 16 Oct 2026: "about dark circles", not "about dark or circles")."""
    return {need.name: need.label for need in needs if need.label}


@dataclass(frozen=True)
class _SaidNeeds:
    """How a reason line names the request's needs (17 Oct 2026): {need name: words} for those named otherwise than by
    their name, and the needs it never names nor counts."""

    labels: Mapping[str, str]
    hidden: frozenset[str] = frozenset()


# The must-haves a request can ask for in other words (17 Oct 2026, the converge round), by their names as
# engine.product_facts.request_asks gives them, and the words naming them as need words are written (no spaces,
# hyphens or apostrophes): a need found by one of these words, when the request asks for the must-have, is named by it
# ("about PFAS-free", not "about teflon"). Decided by Claude.
MUST_HAVE_WORDS: dict[str, tuple[str, ...]] = {
    "PFAS-free": ("pfas", "teflon", "ptfe", "pfoa", "forever"),
    "non-stick": ("nonstick",),
    "sulfate-free": ("sulfate", "sulphate"),
    "SPF": ("spf",),
}


def _said_needs(needs: Iterable[Need], product_type: str | None = None, request: str = "",
                asks: Iterable[str] = (), category: str | None = None) -> _SaidNeeds:
    """How the reason names the request's needs (_need_labels), and since 17 Oct 2026 (the converge round): a need that
    is a must-have the request asks for in other words, by the must-have (MUST_HAVE_WORDS: "teflon" and "PFAS" as
    "PFAS-free", "non stick" as "non-stick"), named once; and in kitchen and general answers, never a need that is a word
    of the product's own name in the request (_own_name_words: "non stick" of "non stick pan", "freezer" of "fridge
    freezer", "cordless" of "cordless drill"). Skincare and haircare requests already have no such need
    (engine.needs.judged_needs). Which words are needs is module 1's; this is only how they are said."""
    labels = _need_labels(needs)
    hidden: set[str] = set()
    asked = set(asks)
    own = _own_name_words(product_type, request) if category in ("kitchen", "general") else frozenset()
    for need in needs:
        written = re.sub(r"[\s'-]", "", (need.label or need.request_word or need.name).lower())
        must = next((must_have for must_have, words in MUST_HAVE_WORDS.items()
                     if must_have in asked and any(written.startswith(word) for word in words)), None)
        if must is not None:
            # A must-have is named as one even when the product's name holds it (18 Oct 2026): "non stick pan without
            # teflon" asks for a non-stick pan as "non-stick frying pan without PFAS" does, and is said the same way.
            labels[need.name] = must
        elif need.request_word is not None and need.request_word in own:
            hidden.add(need.name)
    return _SaidNeeds(labels, frozenset(hidden))


@lru_cache(maxsize=4096)  # one per request as typed: bounded, since visitors' requests are any words (17 Oct 2026)
def _own_name_words(product_type: str | None, request: str) -> frozenset[str]:
    """The words of the product's own names the request uses (module 1's names and clue words for its type,
    config.TYPE_SYNONYMS), as need words are written (engine.sources: no hyphens or apostrophes, a plural trimmed): "non"
    and "stick" of "non stick pan" (a frying pan's "non-stick pan", written with a space or a hyphen), "freezer" of "fridge
    freezer"."""
    product = next((p for p in PRODUCT_TYPES if p.name == product_type), None)
    names = list(product.keywords + product.hints) if product else []
    names += list(TYPE_SYNONYMS.get(product_type or "", ()))
    lowered = _plain(request)
    words: set[str] = set()
    for name in names:
        pattern = r"[\s-]*".join(re.escape(part) for part in re.split(r"[\s-]+", name.lower()) if part)
        for match in re.finditer(rf"(?<![a-z0-9]){pattern}(?:s|es)?(?![a-z0-9])", lowered):
            words |= {_need_stem(re.sub(r"['-]", "", token))
                      for token in re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)*", match.group(0))}
    return frozenset(words)


def _reason(product: ProductScore, ranking: RankingResult, upvotes: bool = True, order: tuple[str, ...] = (),
            shown: Mapping[str, str] | None = None, hidden: Collection[str] = ()) -> str:
    """The one-line reason: how many credible voices, which counted twice for their upvotes (a pick's, `upvotes`) or
    which comment stands out in its thread when that is why it is shown (14 Oct 2026), how many after long-term use,
    how many talk about the request's needs (named in `order`, the request's own, when given; never one of `hidden`,
    17 Oct 2026), and the kind if it leads."""
    recommendations = product.credible_recommendations
    long_term = sum(m.evidence == "long-term use" for m in recommendations)
    has_bonus = product.breakdown.kind_bonus > 0 and ranking.leading_kind is not None
    if product.by_standout:
        clause = _standout_clause(product)
    else:
        clause = _upvotes_clause(product.counted_twice) if upvotes else ""
    return REASON.format(
        voices=_plural(len(recommendations), "credible voice"),
        upvotes=clause,
        long_term=REASON_LONG_TERM.format(n=long_term) if long_term else "",
        needs=_needs_clause(recommendations, [m.needs for p in ranking.products for m in p.mentions], ranking.category,
                            order, shown, hidden),
        kind=REASON_KIND.format(kind=ranking.leading_kind.name) if has_bonus else "",
    )


def _upvotes_clause(counted_twice: tuple[ScoredMention, ...]) -> str:
    """" (one counted twice for its 34 upvotes)": which of a product's credible voices counted twice toward the picks bar
    for their upvotes (Noemi's upvote rule, 14 Oct 2026), most upvoted first; "" when none did (always, while it is off)."""
    if not counted_twice:
        return ""
    counts = [f"{m.upvotes:,}" for m in counted_twice]
    if len(counts) == 1:
        return REASON_UPVOTES_ONE.format(upvotes=counts[0])
    n = NUMBER_WORDS[len(counts)] if len(counts) < len(NUMBER_WORDS) else str(len(counts))
    return REASON_UPVOTES.format(n=n, upvotes=NEEDS_JOIN.join(counts[:-1]) + " and " + counts[-1])


def _standout_clause(product: ProductScore) -> str:
    """" (its comment has 74 upvotes in a 69-comment thread)": the most upvoted of a product's comments standing out in
    their threads (14 Oct 2026), its upvotes and its thread's readable comments; "(one comment has ...)" with more
    credible writers."""
    top = product.standouts[0]
    wording = REASON_STANDOUT_ONE if len(product.credible_recommendations) == 1 else REASON_STANDOUT
    return wording.format(upvotes=f"{top.upvotes:,}", comments=f"{top.thread_comments:,}")


def _rule(standout_pick: bool = False) -> str:
    """The picks bar in words, for the answer's messages (RULE): with the upvote rule on (14 Oct 2026), also how a
    product with one credible recommendation fewer meets it; with a pick shown thanks to a comment standing out in its
    thread (`standout_pick`, 14 Oct 2026), how that one did."""
    rule = RULE.format(mentions=MIN_CREDIBLE_MENTIONS, threads=MIN_THREADS)
    if config.UPVOTE_COUNTS_MORE:
        rule += RULE_UPVOTES.format(fewer=MIN_CREDIBLE_MENTIONS - 1, score=f"{config.UPVOTE_MIN_SCORE:,}")
        if config.UPVOTE_TOP_OF_BIG_THREAD:
            rule += RULE_UPVOTES_THREAD.format(top=f"{1 - config.UPVOTE_THREAD_SHARE_BEATEN:.0%}",
                                               comments=f"{config.UPVOTE_THREAD_MIN_COMMENTS:,}")
    if standout_pick:
        rule += RULE_STANDOUT.format(fewer=MIN_CREDIBLE_MENTIONS - 1)
    return rule


def _needs_clause(recommendations: list[ScoredMention], every_list: list[tuple[str, ...]],
                  category: str | None = None, order: tuple[str, ...] = (), shown: Mapping[str, str] | None = None,
                  hidden: Collection[str] = ()) -> str:
    """", 3 of them about sensitive skin": how many credible recommendations talk about the request's needs, and which
    needs, in the request's order; "" when none does. `order` is the request's needs in its own order (write_answer's
    `needs`): since 15 Oct 2026 the needs are named in it, since the mentions alone can't always show it (each lists its
    needs in the request's order, but when none talks about two of them, which comes first was a guess: "about acne-prone
    skin or combination skin" for a request asking about combination skin first). Without it, `every_list`, the needs of
    every mention ranked, shows that order as well as it can.

    Nothing is said twice: long-term use talks about "lasting" (engine/needs.py), and the reason already says how many
    recommendations come after long-term use, so those don't count again for "how long it lasts".
    """
    fitting = [kept for needs in map(_needs_not_said, recommendations)
               if (kept := tuple(need for need in needs if need not in hidden))]
    if not fitting:
        return ""
    mine = {need for needs in fitting for need in needs}
    ordered = [need for need in order if need in mine]
    ordered += [need for need in _in_request_order(fitting + every_list) if need in mine and need not in ordered]
    labels = NEED_LABELS | NEED_LABELS_BY_CATEGORY.get(category or "", {}) | dict(shown or {})
    named = list(dict.fromkeys(labels.get(need, need) for need in ordered))
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
              picks: Collection[str] = (), forms_asked: Collection[str] = (),
              needs: tuple[Need, ...] = (), picks_names: Collection[str] | None = None,
              lines_products: Collection[str] | Callable[[], Collection[str]] = ()) -> list[LookFor]:
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

    Since 17 Oct 2026 (the converge round) the section never says the opposite of the request or of the picks
    (_contradicts): no "Avoid" for what the request asks for (an active ingredient it names, one of its `needs`, or a
    feature of the product it names, "mesh" in "mesh wifi"), for a kind one of the `picks` is by its own name ("Avoid:
    inverter microwave" above a Panasonic inverter microwave; "Avoid: variable temperature kettle" above a kettle line
    whose products are variable temperature ones), or for a kind the same kind's credible advice, under its other names,
    recommends as strongly ("Avoid: mineral SPFs" beside "Look for: mineral sunscreen"); no "Look for" for what the
    request refuses ("Teflon pans" for a pan without Teflon), or that stronger credible warnings in the same answer
    argue against. Avoiding what the request refuses ("Avoid: Teflon") agrees with it, and stays.

    Since 18 Oct 2026 (the whole sweep read): `picks_names` are the picks' names and their writers' (_picks_names),
    `lines_products` the names of the products ranked under them (_lines_products), which tell only kinds of the type
    asked for ("variable temperature kettle" under the Bonavita line's variable temperature gooseneck); another kind's
    advice counts as this one's only when it is about the same thing (_about_the_same); and a line left out for saying
    the opposite leaves its place empty: the advice after the first lines is weaker, and none comes in for it.
    """
    candidates = []
    asked_words, refused = _asked_and_refused(ranking.category, product_type, request, needs, asks)
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
        # A kind saying the opposite (_contradicts) still takes its place, left empty at the end (18 Oct 2026).
        candidates.append((kind, advice, notes))
    # sorted keeps ties in the ranking's order
    candidates.sort(key=lambda c: (not _about_the_type(c[0].name, c[2], product_type), -abs(c[0].support)))
    names = picks if picks_names is None else picks_names
    opposite: dict[str, bool] = {}  # worked out only for the kinds the section reaches (latency, 18 Oct 2026)

    def says_the_opposite(kind: KindSupport) -> bool:
        if kind.key not in opposite:
            opposite[kind.key] = _contradicts(kind, ranking, product_type, asked_words, refused, names,
                                              unsuited_kinds, lines_products)
        return opposite[kind.key]

    items: list[LookFor] = []
    item_notes: list[list[KindNote]] = []  # each item's kind's notes that state advice, strongest first
    item_kinds: list[list[KindSupport]] = []  # each item's kinds: its own, then those sharing its line
    for kind, advice, notes in candidates:
        if len(items) == LOOK_FOR_NOTES:
            break
        notes = _advice_notes(kind.name, advice, notes, check.widen, ranking.category, product_type, asks, picks)
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
                    item_kinds[used[shared[0].comment_id]].append(kind)
                continue
        if quote:
            items.append(LookFor(kind.name, advice, quote[0]))
            item_notes.append(notes)
            item_kinds.append([kind])
    shown = []
    for item, kinds in zip(items, item_kinds):
        # A line saying the opposite is left out; a kind sharing its line keeps it (the comment backs it too).
        kept = [kind.name for kind in kinds if not says_the_opposite(kind)]
        if kept:
            item.kind = " or ".join(kept)
            shown.append(item)
    return shown


def _form_shown(kind: str, forms_asked: Collection[str]) -> bool:
    """Whether the form a kind's own name says (engine.ingredients.form_of on its words alone) is one an ingredient-led
    answer may show: one the request names, or, when it names none, a leave-on one; a kind naming no form is fine."""
    form = form_of(kind, None)
    if form is None:
        return True
    return form in forms_asked if forms_asked else form_kind(form) == "leave-on"


# What a request's must-have refuses, in the words a kind's name says it with (17 Oct 2026, the converge round): avoiding
# it agrees with the request ("Avoid: Teflon" for a pan without Teflon), looking for it goes against it. By the must-have's
# name, as engine.product_facts.request_asks and config.NEEDS give it. Decided by Claude.
REFUSED_THINGS: dict[str, tuple[str, ...]] = {
    "PFAS-free": ("pfas", "teflon", "ptfe", "pfoa", "forever chemical"),
    "fragrance-free": ("fragrance", "fragranced", "scented", "perfume"),
    "no white cast": ("white cast",),
    "plastic-free": ("plastic",),
    "sulfate-free": ("sulfate", "sulphate", "sls"),
    "non-comedogenic": ("comedogenic", "pore clogging", "pore-clogging", "clogging"),
    "not drying": ("drying", "stripping"),
    "strip": ("stripping", "harsh"),
    "cruelty-free": ("cruelty", "tested on animals"),
}
# How much credible support the kinds recommending what an "Avoid" line warns against need, together, against that
# warning, to keep the line out: half of it on 17 Oct 2026, as much since 18 Oct (half took out a strong warning against
# non-stick pans in a cast iron answer for weaker praise of two kinds of them). Stronger warnings than its support,
# together, keep a "Look for" out. Decided by Claude.
AVOID_OUTWEIGHED_SHARE = 1.0


def _asked_and_refused(category: str, product_type: str | None, request: str, needs: Iterable[Need],
                       asks: Iterable[str]) -> tuple[frozenset[str], tuple[str, ...]]:
    """(the words of what the request asks for, as kinds are read (_written): the active ingredients it names and their
    related ones', its needs' words and the feature words of the product it names (_feature_words), less any word of
    what it refuses; the phrases of what it refuses, REFUSED_THINGS of its asks and needs) (17 Oct 2026)."""
    refused = tuple(dict.fromkeys(thing for ask in [*asks, *(need.name for need in needs)]
                                  for thing in REFUSED_THINGS.get(ask, ())))
    named = [f.ingredient for f in find_ingredients(request) if TYPE_OWN_INGREDIENT.get(product_type or "") != f.ingredient]
    words: set[str] = set()
    for ingredient in dict.fromkeys([*ingredients_of_type(product_type), *named]):
        for name in (ingredient, *INGREDIENTS.get(ingredient, {}).get("related", ())):
            words |= set(_written(name, category))
    for need in needs:
        if need.name in REFUSED_THINGS:
            continue
        if need.request_word:  # a word of the request as typed: "mineral", "storey"
            words |= set(_written(need.request_word, category))
        elif need.name not in PERSON_NEEDS:
            # A need of config.NEEDS by its name's first word, a long one only: "temperature" of "temperature control",
            # "curly", "stainless". Never its other words: they hold its opposite too ("harsh" for gentle, "broke" for
            # lasting, "greasy" for oily), which an "Avoid" line agrees with.
            words |= {w for w in _written(need.name, category)[:1] if len(w) >= 5}
    words |= _feature_words(category, product_type, request)
    words = {w for w in words if len(w) > 2 and w not in GENERIC_KIND_WORDS}
    return frozenset(w for w in words if not _says_any(w, refused)), refused


# Needs that say whom the product is for rather than what it is (17 Oct 2026): an "Avoid" line naming one ("beginner
# knife sets", "oily sunscreens") isn't against a request asking for it.
PERSON_NEEDS = frozenset(SKIN_TYPES) | {"beginner", "home cook"}
# Words that tell no kind apart, when kinds are compared (17 Oct 2026).
_NO_KIND_WORDS = frozenset({"a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "by", "for", "from", "with",
                            "into", "but", "you", "can", "has", "once", "then", "not", "no", "one", "it", "its"})


# Short forms writers use for a kind's word (17 Oct 2026): "variable temp" is variable temperature; and one word for
# another saying the same (18 Oct 2026): an "adjustable temperature" kettle is a variable temperature one.
_SHORT_FORMS = {"temp": "temperature", "temps": "temperature", "adjustable": "variable"}


def _one_form(word: str) -> str:
    """A kind word as one form, so a plural group_kinds made singular its own way meets its singular: "knive" (of
    "knives") is "knife", "patche" "patch", "batterie" "battery", "glasse" "glass"; and a short form as its word
    (_SHORT_FORMS: "temp")."""
    if word in _SHORT_FORMS:
        return _SHORT_FORMS[word]
    if len(word) > 4:
        for ending, base in (("ive", "ife"), ("che", "ch"), ("she", "sh"), ("sse", "ss"), ("xe", "x"), ("ie", "y")):
            if word.endswith(ending):
                return word[:-len(ending)] + base
    return word


def _written(text: str, category: str) -> list[str]:
    """A text's words as kinds are read (engine.group_kinds: hyphens joined, plurals dropped, known names written out),
    each in one form (_one_form)."""
    return [_one_form(w) for w in _kind_words(text, known_aliases("kinds").get(category, {}))]


def _feature_words(category: str, product_type: str | None, request: str) -> set[str]:
    """The words of the product's own names the request uses beyond the type's own name and clue words (17 Oct 2026):
    "mesh" in "mesh wifi" (a wifi router), "oil" in "double cleansing oil" (a cleanser), "automatic" in "automatic
    watch"; also two of them written as one ("carryon"). What the request names its product by is what it asks for."""
    product = next((p for p in PRODUCT_TYPES if p.name == product_type), None)
    if product is None:
        return set()
    own = _type_words(category, product_type)
    lowered = _plain(request)
    found: set[str] = set()
    for keyword in product.keywords:
        if re.search(rf"(?<![a-z0-9]){re.escape(keyword.lower())}s?(?![a-z0-9])", lowered):
            words = [w for w in _written(keyword, category) if not any(_same_word(w, o) for o in own)]
            found |= set(words) | {a + b for a, b in zip(words, words[1:])}
    return found


@cache
def _type_words(category: str, product_type: str) -> frozenset[str]:
    """The words a kind of the type needn't hold to be of it: the type's own name, its clue words (module 1's hints:
    "spf" for a sunscreen, "cream" for a moisturiser), config.TYPE_SYNONYMS, and the last word of each of its names of
    two words or more ("grill" of a barbecue's "gas grill", "luggage" of a suitcase's "carry-on luggage"; a one-word
    name is a kind of its own: "santoku", "tretinoin"), read as kinds are (_written)."""
    words = set(_written(product_type, category))
    for p in PRODUCT_TYPES:
        if p.name == product_type:
            for hint in p.hints:
                words |= set(_written(hint, category))
            for keyword in p.keywords:
                written = _written(keyword, category)
                words |= set(written[-1:]) if len(written) > 1 else set()
    for synonym in TYPE_SYNONYMS.get(product_type, ()):
        words |= set(_written(synonym, category))
    return frozenset(words)


def _kind_own_words(kind: str, category: str, product_type: str | None) -> frozenset[str]:
    """What tells a kind apart, as kinds are read (17 Oct 2026): the words of its parts (kind_parts: before a word
    saying what it is for, the type's words out), each in one form, less the type's clue words, synonyms and names'
    last words (_type_words), GENERIC_KIND_WORDS and words that tell nothing apart. "variable temperature kettle":
    variable, temperature; "mineral SPFs": mineral; "Teflon": nonstick (its known name written out). Worked out once
    per kind, category and type (latency, 18 Oct 2026: an answer compares every kind with every other)."""
    key = (kind, category, product_type)
    found = _KIND_OWN_WORDS.get(key)
    if found is None:
        aliases = known_aliases("kinds").get(category, {})
        own = _type_words(category, product_type) if product_type else frozenset()
        found = _KIND_OWN_WORDS.keep(key, frozenset(
            w for part in kind_parts(kind, product_type or "", aliases) for w in map(_one_form, part)
            if w not in GENERIC_KIND_WORDS and w not in _NO_KIND_WORDS and not any(_same_word(w, o) for o in own)))
    return found


_KIND_OWN_WORDS = Table()  # (kind, category, product type) -> _kind_own_words
_ABOUT_THE_SAME = Table()  # (kind, other, category, product type) -> _about_the_same


def _says_any(text: str, phrases: Iterable[str]) -> bool:
    """Whether a text (any case) holds one of the phrases, each at the start of a word ("sulfate" in "sulfates")."""
    lowered = _plain(text)
    return any(re.search(rf"(?<![a-z0-9]){re.escape(phrase)}", lowered) for phrase in phrases)


def _shares_a_word(a: Iterable[str], b: Iterable[str]) -> bool:
    return any(_same_word(x, y) for x in a for y in b)


def _contradicts(kind: KindSupport, ranking: RankingResult, product_type: str | None, asked: frozenset[str],
                 refused: tuple[str, ...], picks: Collection[str], unsuited_kinds: Collection[str] = (),
                 lines_products: Collection[str] | Callable[[], Collection[str]] = ()) -> bool:
    """Whether a kind's advice would say the opposite of the request, of a pick, or of as strong credible advice about
    the same kind in this answer (_look_for, 17 Oct 2026). An "Avoid" naming what the request refuses agrees with it,
    and so does one about a kind the request's facts rule out (`unsuited_kinds`: tretinoin for a beginner, by its
    facts entry), whatever others recommend; such a kind argues against nothing either. A kind said without what the
    request refuses ("PFAS-free pans", 18 Oct 2026) is the other way round: looking for it agrees with the request.

    The picks are what `picks` names (their names and their writers'); for a kind of the type asked for ("variable
    temperature kettle"), also the products ranked under them (`lines_products`, _lines_products, 18 Oct 2026)."""
    category = ranking.category
    words = _kind_own_words(kind.name, category, product_type)
    others = [other for other in ranking.kinds if other.key != kind.key and other.key not in unsuited_kinds]
    refuses = _says_any(kind.name, refused) and not _negated(kind.name, category)
    against_refusal = _says_any(kind.name, refused) and _negated(kind.name, category)
    if kind.support < 0:
        if refuses or kind.key in unsuited_kinds:
            return False
        if against_refusal:
            return True
        # Every word of its name, not only what tells it apart: "products with niacinamide" names the ingredient asked
        # for after its "with", and a serum's clue words hold the actives.
        named = [w for w in _written(kind.name, category) if w not in GENERIC_KIND_WORDS]
        if _shares_a_word(set(named) | {a + b for a, b in zip(named, named[1:])}, asked):
            return True
        lines = (lines_products() if callable(lines_products) else lines_products) if (
            _of_the_type(kind.name, category, product_type)) else ()
        names = [*picks, *lines]
        if words and any(all(any(_same_word(w, n) for n in _written(name, category)) for w in words) for name in names):
            return True
        # The same kind's recommendations under other names count together (module 4 kept them apart).
        return sum(other.support for other in others if other.support > 0
                   and _about_the_same(kind.name, other.name, category, product_type)) >= (
            AVOID_OUTWEIGHED_SHARE * -kind.support)
    if refuses:
        return True
    return -sum(other.support for other in others if other.support < 0
                and _about_the_same(kind.name, other.name, category, product_type)) > kind.support


# Words saying a kind is without something (18 Oct 2026): "fridge without an ice maker", "garage no ice maker",
# "silicone-free" (one word, as kinds are read) are the opposite of an ice maker and of silicones, never the same kind.
# "non" only before another word than "stick": a non-stick pan has its coating.
_NEGATIONS = frozenset({"without", "no", "free", "zero", "not", "never"})


def _negated(kind: str, category: str) -> bool:
    """Whether a kind's name says it is without something (_NEGATIONS, a word ending in "free", or "non" before a word
    other than "stick")."""
    key = (kind, category)
    found = _NEGATED.get(key)
    if found is None:
        words = _written(kind, category)
        found = _NEGATED.keep(key, any(w in _NEGATIONS or (len(w) > 4 and w.endswith("free"))
                                       or (w == "non" and words[i + 1:i + 2] != ["stick"])
                                       for i, w in enumerate(words)))
    return found


_NEGATED = Table()  # (kind, category) -> _negated
_HEADS = Table()  # (kind, category) -> _head


def _head(kind: str, category: str) -> str | None:
    """What a kind is: the last word of its name before a word saying what it is for, as kinds are read ("coat" of "wool
    coats in rain", "sharpener" of "pull-through sharpener", "iem" of "IEMs with detachable cables")."""
    key = (kind, category)
    if key not in _HEADS:
        words = _written(kind, category)
        cut = next((i for i, w in enumerate(words) if w in PURPOSE_WORDS), len(words))
        words = [w for w in words[:cut] if w not in _NO_KIND_WORDS and w not in GENERIC_KIND_WORDS
                 and not any(ch.isdigit() for ch in w)]
        _HEADS.keep(key, words[-1] if words else None)
    return _HEADS[key]


def _of_the_type(kind: str, category: str, product_type: str | None) -> bool:
    """Whether a kind is a kind of the type asked for by its name's last word ("variable temperature kettle", "inverter
    microwave"; never "knife sets" in a chef knife answer)."""
    head = _head(kind, category)
    return bool(product_type and head and any(_same_word(head, w) for w in _type_words(category, product_type)))


def _about_the_same(kind: str, other: str, category: str, product_type: str | None) -> bool:
    """Whether another kind's advice is about this kind, so that their credible support counts together (_contradicts;
    18 Oct 2026, from the whole sweep): every word telling this one apart is one of the other's (_kind_own_words, told
    the same way: _same_word); the other's further words, if any, only say which one of it it is, keeping what it is
    (_head: "heavy wool coat" for "wool coats in rain", "micro-encapsulated tretinoin" for "tretinoin"; never "merino
    hiking socks" for "hiking boots", "cleansing brushes" for "BHA cleanser"); and neither is without what the other is
    (_negated: "fridge without an ice maker" agrees with avoiding an ice maker). A wider kind never counts for a narrower
    one: a knife sharpener's praise says nothing for a pull-through one, nor a temperature-controlled kettle's (it never
    says "variable") for a variable temperature one."""
    key = (kind, other, category, product_type)
    found = _ABOUT_THE_SAME.get(key)
    if found is None:
        found = _ABOUT_THE_SAME.keep(key, _about_the_same_of(kind, other, category, product_type))
    return found


def _about_the_same_of(kind: str, other: str, category: str, product_type: str | None) -> bool:
    words = _kind_own_words(kind, category, product_type)
    other_words = _kind_own_words(other, category, product_type)
    if not words or not other_words or not all(any(_same_word(w, o) for o in other_words) for w in words):
        return False
    if _negated(kind, category) != _negated(other, category):
        return False
    if all(any(_same_word(o, w) for w in words) for o in other_words):
        return True  # one kind under two names: "mineral SPFs" and "mineral sunscreen", "variable temp"
    head, other_head = _head(kind, category), _head(other, category)
    if head is None or other_head is None:
        return False
    return _same_word(head, other_head) or (_of_the_type(kind, category, product_type)
                                            and _of_the_type(other, category, product_type))


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
    if listed and _a_lookalike_of(kind, product_type):
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
    ("cleansing", a cleanser's). "retinol eye cream" names a retinoid and an eye cream; "AHA" names none. Worked out
    once per kind and category (latency, 13 Oct 2026); a new set each time."""
    key = (kind, category)
    found = _NAMED_TYPES.get(key)
    if found is None:
        found = _NAMED_TYPES.keep(key, frozenset(_named_types_of(kind, category)))
    return set(found)


def _named_types_of(kind: str, category: str) -> set[str]:
    words = re.findall(r"[a-z0-9][a-z0-9'-]*", _plain(kind))
    cut = next((i for i, w in enumerate(words) if w in PURPOSE_WORDS), len(words))
    text = " ".join(words[:cut])
    matches = [(m.start(), m.end(), name) for pattern, name in _type_name_patterns(category)
               for m in pattern.finditer(text)]
    named = [(s, e, name) for s, e, name in matches
             if not any(s2 <= s and e <= e2 and e2 - s2 > e - s for s2, e2, _ in matches)]
    for word in re.finditer(r"[a-z0-9]+", text):
        if not any(s <= word.start() < e for s, e, _ in named):
            named += [(word.start(), word.end(), name) for name, one_word in _one_word_type_names(category)
                      if any(_same_word(word.group(), other) for other in one_word)]
    return {name for _, _, name in named}


@cache
def _type_name_patterns(category: str) -> tuple[tuple[re.Pattern, str], ...]:
    """Each name of module 1's product types of a category, as the pattern _named_types_of finds it with, and its type,
    compiled once (latency, 18 Oct 2026: the general category's ~1,700 names were compiled again for every new name)."""
    return tuple((re.compile(rf"\b{re.escape(keyword)}s?\b"), p.name) for p in PRODUCT_TYPES if p.category == category
                 for keyword in p.keywords)


@cache
def _one_word_type_names(category: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """(type, its one-word names) of each of module 1's product types of a category (_named_types_of)."""
    return tuple((p.name, tuple(name for name in (p.name, *p.keywords) if " " not in name))
                 for p in PRODUCT_TYPES if p.category == category)


def _a_lookalike_of(kind: str, product_type: str) -> bool:
    """Whether a kind's name holds one of module 1's look-alikes of a listed type (engine.query.LOOKALIKE_PHRASES): a
    phrase holding one of the type's own words that names something else (14 Oct 2026). An "immersion blender" in a
    blender answer, a "bread knife" in a chef's knife one (the other kinds of knife, 13 Oct 2026), a "sheet pan" in a
    frying pan one: advice about another product, as an immersion blender was for a blender when it was the open model's
    type."""
    pattern = _lookalikes_of(product_type)
    return pattern is not None and bool(pattern.search(_plain(kind)))


@cache
def _lookalikes_of(product_type: str) -> re.Pattern | None:
    """Module 1's look-alikes holding one of the type's own words (its names and clue words), as one pattern. Every
    phrase module 1 knows as one (engine.query.LOOKALIKE_PHRASES), also those that are other types' names now (14 Oct
    2026, the routing audit: an immersion blender, a bread knife, a sheet pan), never one of the type's own names."""
    own = {k for p in PRODUCT_TYPES if p.name == product_type for k in p.keywords}
    words = {w for p in PRODUCT_TYPES if p.name == product_type for w in p.keywords + p.hints}
    phrases = [phrase for phrase in LOOKALIKE_PHRASES if phrase not in own and phrase.removesuffix("s") not in own
               and any(re.search(rf"\b{re.escape(w)}s?\b", phrase) for w in words)]
    if not phrases:
        return None
    return re.compile(rf"\b(?:{'|'.join(re.escape(phrase) for phrase in phrases)})s?\b")


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
    ingredients it asks for and their related ones' ("BHA" in a salicylic acid answer is what was asked for). Worked out
    once per request (latency, 13 Oct 2026: it was worked out again for every kind); a new set each time."""
    key = (category, product_type, request)
    found = _OWN_NAMES.get(key)
    if found is None:
        found = _OWN_NAMES.keep(key, frozenset(_own_names_of(category, product_type, request)))
    return set(found)


_OWN_NAMES = Table(limit=10_000)  # (category, product type, request) -> the words its own product goes by
_NAMED_TYPES = Table()  # (kind, category) -> the product types its name names


def _own_names_of(category: str, product_type: str, request: str) -> set[str]:
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


def _message(picks: int, product_type: str | None, standout_pick: bool = False) -> str | None:
    """The honest message when fewer than 3 products have enough evidence, or None when there are 3. With a pick shown
    thanks to a comment standing out in its thread (14 Oct 2026), the rule says how that one met the bar."""
    if picks >= PICKS_SHOWN:
        return None
    rule = _rule(standout_pick)
    if picks == 0:
        return NO_PICKS.format(what=f"any {product_type}" if product_type else "a product", rule=rule)
    return FEWER_PICKS.format(products=_plural(picks, "product"), rule=rule, n=picks, wanted=PICKS_SHOWN)


def shown_price(check: PriceCheck | None) -> ShownPrice:
    """A product's price as the shopper sees it: amount, shop and date when known, and how it meets the budget. A brand
    line's from price (14 Oct 2026) says so: "From £25 at John Lewis, checked 14 Oct 2026"."""
    budget_status = None if check is None or check.status == "no budget" else check.status
    budget_note = _budget_note(check) if budget_status else None
    price = check.price if check is not None else None
    if price is None:
        return ShownPrice(PRICE_UNKNOWN, None, None, None, None, None, budget_status, budget_note)
    wording = PRICE_FROM if check.from_price else PRICE
    text = wording.format(amount=_money(price.price, price.currency), shop=price.shop, date=_day(price.checked_on))
    # The price list allows https only; checked again, and never a search (direct links only, 15 Oct 2026).
    url = price.url if is_direct_page(price.url) else None
    return ShownPrice(text, price.price, price.currency, price.shop, url, price.checked_on.isoformat(),
                      budget_status, budget_note, check.from_price)


def shown_range(line: BrandLine | None) -> ShownRange | None:
    """A brand line's link to its entry's range page (Noemi's night decision 1, 14 Oct 2026): "Browse Victorinox chef
    knives" (the brand as its maker writes it, the type as a name shows it), with the day its sources were read; "...
    at <shop>" when the page is an official UK stockist's. None when
    there is no entry, it says the brand doesn't sell the type, or it has no range page. The page is shown exactly as
    the list writes it, and only when it is still one of the entry's sources and a page the list allows (https, never
    Reddit: engine.brand_lines.is_source_page), checked again here as the shop links are."""
    if line is None or not line.sells or line.range_page is None:
        return None
    if line.range_page not in line.sources or not is_source_page(line.range_page) or is_search_page(line.range_page):
        return None
    brand, products = line.brand, plural(line.product_type)
    text = (RANGE_LINK_AT.format(brand=brand, products=products, shop=line.range_shop) if line.range_shop
            else RANGE_LINK.format(brand=brand, products=products))
    return ShownRange(text, line.range_page, RANGE_CHECKED.format(date=_day(line.checked_on)),
                      line.checked_on.isoformat())



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
        wording = AVAILABILITY_NOT_IN_UK if getattr(sold, "not_in_uk", False) else AVAILABILITY_GONE
        return ShownAvailability(wording.format(date=day), False, sold.shop, None, sold.checked_on.isoformat())
    # https only, checked again, and never a search (direct links only, 15 Oct 2026: "Sold second-hand only: eBay UK"
    # had linked to an eBay search).
    url = sold.url if is_direct_page(sold.url) and sold.url != price_url else None
    wording = AVAILABILITY_SECOND_HAND if sold.second_hand else AVAILABILITY
    return ShownAvailability(wording.format(shop=sold.shop, date=day), True, sold.shop, url,
                             sold.checked_on.isoformat(), sold.second_hand)


def _budget_note(check: PriceCheck) -> str:
    """How the price meets the budget, in words: within it, or why it wasn't checked against it."""
    most = _money(check.budget.max, check.budget.currency)
    if check.status == "within" and check.from_price:  # a brand line's cheapest product of the type (14 Oct 2026)
        return BUDGET_WITHIN_FROM.format(amount=_money(check.price.price, check.price.currency), max=most)
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


def without_unread(answer: Answer, comment_ids: set[str], standing_out: Collection[str] = ()) -> Answer:
    """The answer without what stands on these comments, which the live check put off (13 Oct 2026): an "Also worth a
    look" item quoting one (in its quotes or downsides), and a summary citing one. Nothing else changes but the note
    under Also worth a look, worked out again when an item leaves it (15 Oct 2026: it counts the items meeting the picks
    bar), with `standing_out` the keys of the products shown thanks to a comment standing out in its thread."""
    def unread(quotes) -> bool:
        return any(quote.comment_id in comment_ids for quote in quotes)

    def summary_read(shown):
        return replace(shown, summary=None) if shown.summary is not None and unread(shown.summary.sources) else shown

    worth = [summary_read(item) for item in answer.worth_a_look if not unread((*item.quotes, *item.downsides))]
    note = answer.worth_note
    if len(worth) < len(answer.worth_a_look):
        note = _worth_note(len(answer.picks), any(item.product_key in standing_out for item in worth),
                           any(pick.product_key in standing_out for pick in answer.picks),
                           sum(item.meets_bar for item in worth), len(worth))
    return replace(answer, picks=[summary_read(pick) for pick in answer.picks], worth_a_look=worth,
                   worth_note=note if worth else None)


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
            lines += [f"  - {item.prescription}"] if item.prescription else []
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
    lines += _render_price(pick.price) + _render_availability(pick.availability) + _render_range(pick.range)
    lines += _render_link(pick.link)
    lines += [pick.prescription, ""] if pick.prescription else []
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
    """An "Also worth a look" item: its name, MEETS_BAR when it meets the picks bar (15 Oct 2026), summary, reason,
    price (when known, or with a budget), where it is sold (when checked), cautions, quotes and, only when credible voices
    warn against it, its downsides."""
    lines = [f"### {item.name}", ""] + ([f"**{MEETS_BAR}**", ""] if item.meets_bar else [])
    lines += _render_form(item.form) + _render_summary(item.summary) + [item.reason, ""]
    if item.price.amount is not None or item.price.budget_note:  # lighter than a pick: what is known, or the budget's
        lines += _render_price(item.price)
    if item.availability.available is not None:
        lines += _render_availability(item.availability)
    lines += _render_range(item.range) + _render_link(item.link)
    lines += [item.prescription, ""] if item.prescription else []
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


def _render_range(range_: ShownRange | None) -> list[str]:
    """A brand line's link to its maker's page for the type, and the day it was checked (14 Oct 2026); nothing for
    any other product."""
    return [f"[{range_.text}]({range_.url}) · {range_.checked}", ""] if range_ is not None else []


def _render_link(link: ShownLink | None) -> list[str]:
    """A product's direct link to its own page, and the day it was read (15 Oct 2026); nothing without one. The text
    answer carries no images."""
    return [f"[{link.text}]({link.url}) · {link.checked}", ""] if link is not None else []


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
