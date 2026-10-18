"""The thin end-to-end slice: one request, typed in plain words, through modules 1 to 7 to a top 3.

    request ──1 query──> category, product type ──2 retrieval──> the library's most relevant threads
            ──3 extraction──> their checked mentions and notes (saved files; quotes already verified once)
            ──4 matching──> products and kinds ──5 credibility──> a weight per mention
            ──6 ranking──> scores, minimum-evidence rule, skip list ──7 answer──> picks with quotes re-verified

Every step is a module of its own; this file only passes each one's output to the next. Four filters sit here:
- only threads about the product are read: its title or post must name it (engine.sources.mentions_product).
  Comments don't count, however many name it: a coffee thread whose comments mention kettles in passing isn't
  about kettles, and its grinders would otherwise be ranked for a kettle request (review fixes, 9 Oct 2026: five
  such comments used to be enough). Of those, only threads the AI has already read (extracted) can be used, and
  the reading limit (max_threads) counts only those: threads still waiting for the AI are listed on the result
  (not_extracted) instead of taking a slot and then being dropped;
- products of another type are left out: a skillet praised in a kettle thread is a real product, but not an answer
  to a kettle request. From extraction instructions v6 the AI writes each product's type, and the type most of
  its mentions give decides. Older extractions have no type: then a product counts as another type when one of
  its names says so ("Lodge cast iron skillet") and none names the requested type, and a name that says nothing
  ("Zojirushi") stays in.
- loose groups (a brand or line that fits several products, such as "Lodge" or "CeraVe") are ranked, as the brand's
  whole line, only when it is clear they mean the requested product (Noemi's decision 9, 9 Oct 2026). They must name
  something, and none of their names (nor most of the AI's types for their mentions) may say another type of product
  (the rule above). Then, since 12 Oct 2026 (Noemi: "are we making sure that the brand mentioned doesn't sell the
  product we're looking for?"), the brand-lines list decides when it has an entry for the brand and the requested type
  (engine/brand_lines.py, data/brand_lines.json, checked on the makers' own pages): ranked when the brand sells that
  kind of product, left out when it doesn't, with the reason (brands_not_selling: "Batiste doesn't sell shampoos").
  With no entry, their threads decide, as before: more than half of their mentions (config.BRAND_PICK_TITLE_SHARE) are
  in threads whose title names the requested product, and one of the brand's own products named in the threads is of
  that type ("Lodge Blacklock skillet"; config.BRAND_PICK_NEEDS_A_PRODUCT_OF_THE_TYPE). A group ranked is shown under a
  name that says what it is, the brand's line of the requested type: "Lodge cast iron skillet line" (Noemi's wording,
  12 Oct 2026), named on the result (ranked_as_lines). The others are left out: their mentions can't count for any one
  product. PIPELINE_BRAND_PICKS = False leaves them all out. A brand pick never appears next to its own specific
  product (decided by Claude, 10 Oct 2026, as Noemi asked): when both qualify ("Victorinox chef knife line" and
  "Victorinox chef's knife"), the specific product stays and the brand pick steps aside, out of the ranking, so its
  support counts for nothing rather than twice. It is listed on the result with the product it stepped aside for
  (folded_brand_picks). Its own products are those whose name starts with the brand's words, or that module 4 says
  are one of its products (engine.match_products.same_product: "CeraVe cleanser" and "CeraVe Hydrating Cleanser").
  Since 17 Oct 2026 (within Noemi's decision 8 of 16 Oct 2026) a product group named only by its brand ("Circulon
  pans", "circulon": module 4 keeps a brand none of whose models is named as one product) is that brand's line too,
  when its brand-lines entry says the brand sells the requested type and no facts or price entry names one product of
  it (_brand_only_lines): under a must-have it is then left out as a whole brand, as every line is.
- with a budget in the request (a max and a currency), a product whose price (engine/prices.py, data/prices.json) is
  known and above the max is left out (Noemi's decision 11). A product with no known price, a price in another
  currency, or a price checked over PRICE_MAX_AGE_DAYS ago is kept, and its answer says so.
- a product the price list says is no longer sold ("available": false; engine.prices.find_availability) is left out,
  budget or not (Noemi's note of 9 Oct 2026: "are we making sure the products we recommend exist?"). A product with no
  availability check is kept, and its answer says so. A product no longer made but sold second-hand only ("second_hand":
  true: vintage Griswold and Wagner cast iron) counts as sold, and its answer says "Sold second-hand only" (Noemi's
  decision, 10 Oct 2026). Brand picks are never priced or checked (named in not_priced), except that a brand pick
  shows the second-hand line when the newest entry under the brand's own name ("Griswold") says so. Since Noemi's night
  decision 1 of 14 Oct 2026, a line whose brand-lines entry gives a from price with where and when it was found has
  that as its price (the cheapest UK price of its products of the type), which also says it is sold there; and the
  answer links each line to its entry's range page (the maker's page for its products of the type). Since Noemi's
  decisions of 15 Oct 2026 (late afternoon: a pick must be on sale in the UK now), sold second-hand only counts only
  for things people buy vintage on purpose (engine.prices.counts_as_sold): anything else so sold is left out and
  named, as a discontinued model is; and an entry under the name the answer shows a product under counts as one under
  its writers' name (_sold_under_shown_name), since researchers record what answers show (engine/buyable.py).
- each product's own page and its maker's image (Noemi's decisions 2 and 3 of 15 Oct 2026, engine/product_pages.py,
  data/product_pages.json), found by the name it is shown under, then its writers' name (_pages): the answer links it
  and shows the image; nothing is linked for a product not researched, and nothing here changes which products are
  shown.
- product facts (decided by Claude, 9 Oct 2026; engine/product_facts.py, data/product_facts.json): right after the
  budget step, a product whose checked facts clash with what the request asks for is left out by a hard rule ("retinol
  for a beginner with sensitive skin" leaves out a strong, prescription-only retinoid) and listed with the reason
  (left_out_not_suited), or kept by a soft rule with the reason shown under its pick as a caution ("Note: ..."). A fact
  that isn't known never leaves a product out. Brand picks have no single product, so their facts are never looked up:
  when the request has a hard requirement its product type can have ("non-stick frying pan without PFAS"; engine.
  product_facts.hard_requirements), brand picks are left out too, listed with the reason "a whole brand can't be
  checked for PFAS or a non-stick coating" (decided by Claude, 10 Oct 2026, as Noemi asked), whatever the brand-lines
  list says it sells. Since Noemi's decision 1 of 13 Oct 2026 such a line is still ranked, never as a pick nor "Also
  worth a look", so its credible warnings can list it under Skip these (skip_only). A product whose facts can't
  confirm a hard requirement is kept with a note ("we couldn't confirm it's PFAS-free"), and since Noemi's decision 1
  of 15 Oct 2026 it ranks after the products whose facts or name confirm it (unconfirmed; engine.rank): until then it
  kept its place.
- only threads checked live on Reddit in the last LIVE_CHECK_SHOWN_DAYS (14) days are quoted (Noemi, 9 Oct 2026): a
  thread read from Arctic Shift's archive may still hold comments people deleted on Reddit since, so it counts from
  the day a live check read it on Reddit (checked_live_at); a thread read through Parse counts from the day it was
  read (collected_at; older files have no provenance and were all read through Parse). Days are calendar days on
  `today`: a thread read on 7 Oct is quoted up to and including 21 Oct. Threads waiting for a live check are listed
  on the result (waiting_live_check) and, like threads not extracted yet, take no reading slot.
  `python -m engine.library check-live` reads them again. Gold-set threads (read_from "gold", or the pipeline pointed
  at data/gold) are exempt. LIVE_CHECK_REQUIRED = False turns the rule off, for an experiment only.
- active ingredients (13 Oct 2026; engine/ingredients.py): when the request names one ("salicylic acid for acne",
  "salicylic acid cleanser"), right after the facts step a product is kept only with evidence it contains it: its facts
  entry's formula lists it among its actives (from the maker's page), or, with no formula, the name it is shown under
  names it. A formula without it, or no evidence at all, leaves the product out, named with the reason
  (left_out_no_ingredient), and so does a brand pick: a whole brand can't be checked for an ingredient. An
  ingredient-led request (one naming no product type) reads the skincare threads that name the ingredient, whatever
  their type, and keeps the products of every type that can carry it (engine.ingredients.wanted_types): a serum, a
  toner and a cleanser compete, each shown with its form. Each product's own type is the one its mentions give, and it
  is what its price and facts are looked up by. Since Noemi's decision 1 of 13 Oct 2026, such a request shows leave-on
  forms only (a serum, a liquid, a toner, pads, a cream, a spot treatment...), or the forms it names ("salicylic acid
  wash"): a rinse-off product, or one whose form isn't known, is left out with the reason and counted
  (left_out_by_form); a cleanser shows when the request names it ("salicylic acid cleanser", a type of its own).
The lists of products left out are kept on the result, so nothing is dropped silently; so are the "what to
look for" notes that name no kind (notes_without_kind, engine.group_kinds step 5), which the ranking and the answer
can't use. threads_quoted names the threads the answer's quotes come from: the ones whose live checks matter most.

Each mention carries its writer's name (lowercased), so the ranking counts one writer once per product, however
many comments or threads they praise it in (engine.rank). Since 14 Oct 2026 it also carries its comment's upvotes beside
its thread's (engine.credibility.thread_upvotes), for Noemi's upvote rule, which is off (engine.rank.counts_twice).

Two ranking changes of 9 Oct 2026 are worked out here, in _score, before module 6 ranks:
- needs: a mention whose comment talks about what the request asks for (engine/needs.py: "sensitive skin", "a
  beginner", "pour-over") weighs NEED_MATCH_BOOST times (off, 1.0, for now) as much, a recommendation or a warning alike.
  Since 15 Oct 2026 what a mention talks about is judged by the needs a comment can talk about (engine.needs.
  judged_needs), the need rule's: not a word of an active ingredient the request names, a size, a single letter or, in
  skincare and haircare, a checked requirement's word. So everything the answer says or shows about them goes by the
  rule's needs: the reason's "2 of them about ...", the breakdown's counts, the quotes about them shown first, and
  whether a comment standing out in its thread talks about what was asked. Every writer of a vitamin C serum names it,
  so its reason had said "3 of them about vitamin or c". The threads read first still go by every need (engine.sources);
- writers who contradict themselves (Noemi's rule; engine/contradictions.py): a writer who recommends a product and
  warns against it in another comment of the threads read, without saying what changed, counts as a low voice in
  every mention and note they make, so none of it is credible. They are named on the result (contradicting_writers)
  for reports, which count them; nothing about them is shown to users.

Names are shown as a UK shopper knows them (decision 12): "Sage", not "Breville" (engine.group_products.uk_name).

The same product never shows twice in one answer (13 Oct 2026, from reading the day's answers: b06 had "Fellow Stagg
EKG" and "Fellow kettle" as two picks, a lip balm answer one brand's line twice on its skip list). Module 4 groups the
request's mentions for its product type (engine.group_products, "In one request": "Fellow kettle" is Fellow's kettle
line, which steps aside for its own model as brand picks do), and as the last guard, groups shown under the same name
are joined before the ranking (_one_per_name).

"Also worth a look" (Noemi's decision 2 of 13 Oct 2026): products with two credible recommendations across two threads
(engine.rank), shown apart after the picks. The filters above apply to them as to picks, since they come before the
ranking, and so does the wider reading's rule (a credible recommendation about the request's needs). The brand rules
too (_worth_left_out): an item of the brand of a brand-line pick shown is left out, since the pick speaks for its
brand's products ("Lodge dutch oven" under the pick "Lodge Dutch oven line"); a brand line whose own product is a pick
is left out; among the items, a brand line steps aside for its own product, as picks do; and an item whose brand or line
is on the skip list is left out, so an answer never lists a product apart while telling you to skip its brand.

One-line summaries (Noemi's decision 4 of 13 Oct 2026): read from the library's summaries.json (engine/summaries.py),
written ahead of time; the answer shows one only when every check passes, and with the live checker on, the quotes of
the comments it cites are checked on Reddit with every shown quote (engine.answer.quotes_to_check).

Care tips, "How to take care of it" (Noemi, 9 Oct 2026; renamed 11 Oct 2026): the credible care tips of the threads
read (extraction instructions v7, narrowed in v8 to care of the product itself) go with the products they are about
(engine/care_tips.py). The answer shows a pick's own tips under it, and the tips about its kind of product once, in a
note at the end (Noemi, 11 Oct 2026). They never change the ranking. Older extractions have none, so their answers
don't change.

Writers' standing (account age, karma, contributions, flair) isn't in the saved threads: Parse gives only names.
With `profiles` (engine.profiles.StoredProfiles in the command line, the web demo and the evaluation), it is filled in
from the library's profile store (kept for LIBRARY_REFRESH_DAYS, Noemi's decision of 9 Oct 2026) and Arctic Shift's
48-hour cache, never waiting on a call; `python -m engine.profiles warm data/library/threads` fills both beforehand.

Command line:
    python -m engine.pipeline "<request>"     prints the answer, from data/library
"""

import re
import sys
from collections import Counter
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from datetime import date
from functools import cache
from pathlib import Path

from engine import config  # the upvote rule's switch, read for each request (14 Oct 2026)
from engine.answer import (
    NO_THREADS, Answer, _every_quote, comment_bodies, flattened_comments, needed_quotes, quotes_to_check,
    render_markdown, says_the_opposite, shown_availability, shown_price, without_unread, write_answer,
)
from engine.brand_lines import BrandLine, find_brand_line, from_price_entry, load_brand_lines, not_sold_reason
from engine.care_tips import CareTips, attach_care_tips, credible_care_tips
from engine.config import (
    BRAND_MODEL_GENERIC_WORDS,
    BRAND_MODEL_MIN_CREDIBLE,
    BRAND_ONLY_NAMES_AS_LINES,
    BRAND_PICK_NEEDS_A_PRODUCT_OF_THE_TYPE,
    BRAND_PICK_TITLE_SHARE,
    BUDGET_DEFAULT_CURRENCY,
    INGREDIENT_BRAND_UNCHECKABLE,
    INGREDIENT_FORM_NOT_CONFIRMED,
    INGREDIENT_FORM_UNKNOWN,
    INGREDIENT_NOT_CONFIRMED,
    INGREDIENT_NOT_FORM_ASKED,
    INGREDIENT_NOT_LISTED,
    INGREDIENT_RINSE_OFF,
    LIVE_CHECK_PARALLEL,
    LIVE_CHECK_REQUIRED,
    LIVE_CHECK_SHOWN_DAYS,
    NEED_MATCH_BOOST,
    NEED_RULE_IN_EVERY_READING,
    OTHER_NAME_NOTE,
    OTHER_KIND_WORDS,
    OTHER_TYPE_WORDS,
    PIPELINE_BRAND_PICKS,
    PICKS_SHOWN,
    PIPELINE_MAX_THREADS,
    PIPELINE_MORE_THREADS,
    TYPE_SYNONYMS,
    UK_BRAND_NAMES,
    WORTH_A_LOOK_SHOWN,
)
from engine.contradictions import contradicting_writers
from engine.credibility import (
    VoiceScore, badges, copied_comment_ids, copy_groups, mention_weight, repeated_copies, score_evidence, score_voice,
    thread_upvotes, with_ai_evidence,
)
from engine.extract import CheckResult, shown_comment_ids
from engine.group_kinds import KindMention, group_kinds, kinds_of, placements
from engine.group_products import (
    LibraryRanges, ProductGroup, ProductMention, brand_pick_name, group_of, group_products, library_name_index,
    library_ranges, maker_spelling, plural, uk_name,
)
from engine.gold import DEFAULT_GOLD_DIR
from engine.ingredients import evidence as ingredient_evidence
from engine.ingredients import (
    facts_types, form_kind, form_of, ingredient_type_name, own_name, rinse_off_word, wanted_types,
)
from engine.ingredients import shown as shown_ingredients
from engine.library import DEFAULT_LIBRARY_DIR, checked_live_within
from engine.library_cache import loaded as loaded_library
from engine.match_products import (
    LINE_WORDS, known_aliases, normalize_name, plain_words, product_words, same_product, written_alike,
)
from engine.memo import Table
from engine.models import Comment, Thread
from engine.needs import Need, judged_needs, needs_met, said_not_to_help
from engine.prices import (
    Price,
    PriceCheck,
    check_price,
    counts_as_sold,
    find_availability,
    find_brand_entry,
    find_price,
    load_prices,
)
from engine.product_pages import ProductPage, find_page, load_product_pages
from engine.product_facts import (
    NotSuited,
    ProductFacts,
    conflicts,
    find_brand_facts,
    find_facts,
    hard_requirements,
    unconfirmed,
    unconfirmed_note,
    load_product_facts,
    request_asks,
    uncheckable_brand_reason,
)
from engine.profiles import ProfileStore, StoredProfiles, with_profiles
from engine.query import _OTHER_KNIVES as OTHER_KNIVES, PRODUCT_TYPES, ParsedQuery, parse_query
from engine.rank import KindNote, RankingResult, ScoredMention, rank_products
from engine.sources import LocalSource, mentions_product, names_product
from engine.summaries import SUMMARIES_FILE, Summary, load_summaries


@dataclass(frozen=True)
class LeftOutByForm:
    """A product with the ingredient asked for, left out of an ingredient-led answer for its form (Noemi's decision 1 of
    13 Oct 2026): rinse-off, not known to be leave-on, or not the form the request names."""

    name: str  # as the answer would have shown it
    reason: str  # in words for the shopper: "a rinse-off cleanser: ask for a salicylic acid cleanser to see these"
    form: str | None  # its form (engine.ingredients.form_of), or None when not known
    rinse_off: bool  # True when its form is rinse-off (the page's footnote says how to see those)


@dataclass(frozen=True)
class FoldedBrandPick:
    """A brand pick that stepped aside for a specific product of its own brand that also qualifies, or for a brand pick
    of the same brand ranked higher (10 Oct 2026)."""

    name: str  # the brand pick's name: "Victorinox chef knife line"
    stepped_aside_for: str  # the product it stepped aside for: "Victorinox chef's knife"


@dataclass
class PipelineResult:
    query: ParsedQuery
    threads_used: list[str] = field(default_factory=list)  # thread ids, most relevant first
    ranking: RankingResult | None = None
    answer: Answer | None = None  # None when module 1 asks a question or says no
    bodies: dict[str, str] = field(default_factory=dict)  # comment id -> text, to re-check quotes
    left_out_as_other_type: list[str] = field(default_factory=list)  # product names
    # The names of single mentions about another type of product, left out of a product of the requested type (13 Oct
    # 2026; _of_another_type): the product itself stays in, so it isn't in left_out_as_other_type.
    mentions_of_another_type: list[str] = field(default_factory=list)
    left_out_loose: list[str] = field(default_factory=list)  # brand or line names (and names that name nothing)
    # Names that name no one product (15 Oct 2026; engine.group_products: a kind written without a maker, "SA cleanser",
    # or two models at once, "JBL Flip 4, 5, or 6"): never ranked, nor counted among the brand or line names.
    left_out_generic: list[str] = field(default_factory=list)
    # Brand or line names left out because the brand-lines list says their brand doesn't sell the requested type of
    # product, with that reason (12 Oct 2026); they are in left_out_loose too.
    brands_not_selling: list[NotSuited] = field(default_factory=list)
    # The brand or line names ranked as the brand's whole line ("Lodge cast iron skillet line"), as shown (12 Oct 2026).
    ranked_as_lines: list[str] = field(default_factory=list)
    not_extracted: list[str] = field(default_factory=list)  # ids of threads about the product the AI hasn't read yet
    notes_without_kind: list[str] = field(default_factory=list)  # the "about" of each kept note that names no kind
    left_out_over_budget: list[str] = field(default_factory=list)  # product names, with a known price above the max
    left_out_unavailable: list[str] = field(default_factory=list)  # product names the price list says aren't sold now
    not_priced: list[str] = field(default_factory=list)  # brand or line names ranked (decision 9): never priced
    # Products whose facts clash with the request by a hard rule (engine/product_facts.py, 9 Oct 2026): name and reason.
    # Since 10 Oct 2026 also brand picks, when the request has a hard requirement: a whole brand can't be checked.
    left_out_not_suited: list[NotSuited] = field(default_factory=list)
    # The brand lines among them kept in the ranking for Skip these only, {product key: reason} (Noemi's decision 1 of
    # 13 Oct 2026: never a pick, but listed under Skip these when their credible warnings put them there).
    skip_only: dict[str, str] = field(default_factory=dict)
    # {product key: how many of the request's must-haves (engine.product_facts.hard_requirements) its facts and the
    # names it is shown under can't confirm}, for the products noted "we couldn't confirm ..." (Noemi's decision 1 of 15
    # Oct 2026): they rank after those confirmed, fewer first (engine.rank). Empty for a request without a must-have.
    unconfirmed: dict[str, int] = field(default_factory=dict)
    # Products left out of a request naming an active ingredient (13 Oct 2026): no evidence they contain it, a formula
    # without it, or a brand pick (a whole brand can't be checked); name and reason.
    left_out_no_ingredient: list[NotSuited] = field(default_factory=list)
    # The lines kept in an answer naming an active ingredient because every product of them named in the threads has a
    # facts entry confirming it (14 Oct 2026, the orchestrator's call): {line's key: those entries' names}, and the
    # forms its products take, joined ("gel or liquid"), {line's key: form}.
    lines_confirmed: dict[str, list[str]] = field(default_factory=dict)
    line_forms: dict[str, str] = field(default_factory=dict)
    # The keys of the lines in such an answer whose products named are all one product the facts list knows: each is
    # that product (14 Oct 2026; "Finacea", its "Gel 15%" and its "(15% azelaic acid)").
    lines_as_one_product: set[str] = field(default_factory=set)
    # Products with the ingredient left out of an ingredient-led answer for their form (Noemi's decision 1, 13 Oct
    # 2026): rinse-off, form not known, or not the form the request names.
    left_out_by_form: list[LeftOutByForm] = field(default_factory=list)
    # Brand picks that stepped aside for a specific product of their brand that also qualifies (10 Oct 2026).
    folded_brand_picks: list[FoldedBrandPick] = field(default_factory=list)
    # Brands or lines on the skip list that a shown pick belongs to: not listed as skips; their warnings are shown under
    # that pick's Known downsides instead (10 Oct 2026).
    folded_skips: list[FoldedBrandPick] = field(default_factory=list)
    live_dropped: dict[str, int] = field(default_factory=dict)  # comments dropped by the live check, by reason
    # Comments the live check put off rather than wait for Reddit's allowance (13 Oct 2026): what stands on them ("Also
    # worth a look", a summary) is left out of this answer, and the web page doesn't remember it.
    live_put_off: int = 0
    # Ids of extracted threads about the product not checked live on Reddit in the last LIVE_CHECK_SHOWN_DAYS: not
    # used until `python -m engine.library check-live` reads them again (Noemi, 9 Oct 2026).
    waiting_live_check: list[str] = field(default_factory=list)
    threads_quoted: list[str] = field(default_factory=list)  # ids of the threads the answer's quotes come from
    # Writers (lowercased names) who recommend a product and warn against it without saying what changed: their every
    # mention counts as a low voice (Noemi's rule, 9 Oct 2026). For reports only, as a count: never shown to users.
    contradicting_writers: list[str] = field(default_factory=list)
    threads_available: int = 0  # extracted threads about the product that could be read (threads_used is the first ones)
    # The comments the AI read in the threads used (its reading view: the readable comments, up to EXTRACT_MAX_COMMENTS
    # a thread), shown with every answer (Noemi, 12 Oct 2026).
    comments_read: int = 0
    # Problems of library files left out of this answer (a thread or extraction file that doesn't load or check):
    # reported, never quietly dropped (11 Oct 2026).
    skipped_files: list[str] = field(default_factory=list)
    read_more: bool = False  # the first threads gave too few picks, so more were read (answer_request, 11 Oct 2026)
    # The same reading ranked with Noemi's upvote rule (14 Oct 2026), when asked for (_answer's upvotes_too): what
    # answer_request returns for the reading it keeps. None otherwise, and when the rule changes nothing in its ranking
    # (the answer is this one).
    with_upvotes: "PipelineResult | None" = field(default=None, repr=False, compare=False)

    def text(self) -> str:
        """The answer as Markdown, or module 1's question or polite no."""
        if self.answer is None:
            return self.query.question or self.query.message or "Nothing to show."
        return render_markdown(self.answer)

    @property
    def brand_or_line_names_left_out(self) -> list[str]:
        """The brand or line names left out (left_out_loose), most mentioned first, without the names made of filler
        words only ("the one"): those name nothing, so they aren't brand or line names (12 Oct 2026, for the page's
        footnote)."""
        return [name for name in self.left_out_loose if normalize_name(name)]


# The pipeline sees only the gold set's threads when pointed at this folder (or one inside it): they are exempt from
# live checks.
GOLD_DIR = DEFAULT_GOLD_DIR


def _today() -> date:
    """Today's date, the day prices and live checks are judged on when no `today` is given. The tests set it to a fixed
    day (engine/tests/conftest.py), since their made-up threads are dated October 2026."""
    return date.today()


def answer_request(request: str, library_dir: Path = DEFAULT_LIBRARY_DIR, max_threads: int = PIPELINE_MAX_THREADS,
                   profiles=None, prices: list[Price] | None = None, today: date | None = None,
                   live_check_required: bool | None = None, live_checker=None,
                   product_facts: list[ProductFacts] | None = None,
                   more_threads: int | None = PIPELINE_MORE_THREADS,
                   brand_lines: list[BrandLine] | None = None,
                   summaries: Mapping[str, Summary] | None = None,
                   product_pages: list[ProductPage] | None = None) -> PipelineResult:
    """Runs modules 1 to 7 on the saved library and returns everything each step decided.

    The answer reads the `max_threads` most relevant threads first. When they give fewer than PICKS_SHOWN picks and the
    library holds more threads about the product, it reads up to `more_threads` before giving up (Noemi, 7 Oct 2026:
    "fetch more threads automatically before giving up"; built 11 Oct 2026), and keeps that wider answer only if it has
    more picks: the first threads are the ones closest to the request's needs. In the wider reading a pick also needs a
    credible recommendation that talks about what the request asks for, when it asks for something besides the product
    (its needs, engine/needs.py): reading 48 shampoo threads had given every shampoo request the same popular picks. For
    haircare it needs one in the first reading too (config.NEED_RULE_IN_EVERY_READING; Noemi's decision 4 of 14 Oct
    2026). `more_threads=None` never reads more. `brand_lines`: the brand-lines list (engine/brand_lines.py); None reads
    data/brand_lines.json. `summaries`: the one-line summaries ({engine.summaries.summary_key: Summary}); None reads the
    library's summaries.json (none when there is no such file). `product_pages`: the products' own pages and makers'
    images (engine/product_pages.py, 15 Oct 2026); None reads data/product_pages.json.

    Noemi's upvote rule (14 Oct 2026; off unless config.UPVOTE_COUNTS_MORE) never changes how much is read: ranked with
    it, a first reading short of picks could reach three with products it lifts and never read on, where the wider
    reading's picks talk about what was asked (on the library: Nizoral and Head & Shoulders for a dandruff shampoo). So
    which reading to keep is decided as with the rule off, and the reading kept is then ranked with it, from what it has
    read (_answer's upvotes_too: its threads aren't read again). The same goes for a comment standing out in its thread
    (14 Oct 2026; config.STANDOUT_ON): the upvote rules, together.
    """
    query = parse_query(request)
    upvotes = config.UPVOTE_COUNTS_MORE or config.STANDOUT_ON
    reading = dict(library_dir=library_dir, profiles=profiles, prices=prices, today=today,
                   live_check_required=live_check_required, live_checker=live_checker, product_facts=product_facts,
                   brand_lines=brand_lines, summaries=summaries, upvotes_too=upvotes, product_pages=product_pages)
    result = _answer(query, max_threads=max_threads, **reading)
    if not (more_threads is None or more_threads <= max_threads or result.answer is None
            or len(result.answer.picks) >= PICKS_SHOWN or result.threads_available <= len(result.threads_used)):
        wider = _answer(query, max_threads=more_threads, need_led=True, **reading)
        if len(wider.answer.picks) > len(result.answer.picks):
            wider.read_more = True
            result = wider
    if upvotes and result.with_upvotes is not None:
        result.with_upvotes.read_more = result.read_more
        result = result.with_upvotes
    return result


def request_kind(request: str) -> tuple:
    """What an answer to `request` works out is kept under, for the answers' memory (engine.memo.TypeWindow, 15 Oct
    2026): its product type as module 1 reads it, with its category and whether it is ingredient-led; a request module 1
    doesn't place has one of its own (its status), since it works nothing out."""
    query = parse_query(request)
    if query.status != "ok":
        return (query.status,)
    return query.category, query.product_type, query.ingredient_led


def _answer(query: ParsedQuery, library_dir: Path, max_threads: int, profiles, prices: list[Price] | None,
            today: date | None, live_check_required: bool | None, live_checker,
            product_facts: list[ProductFacts] | None, need_led: bool = False,
            brand_lines: list[BrandLine] | None = None,
            summaries: Mapping[str, Summary] | None = None, upvotes_too: bool = False,
            product_pages: list[ProductPage] | None = None) -> PipelineResult:
    """One reading of the library for an understood request, with at most `max_threads` threads (answer_request).
    `need_led`: the wider reading's rule, a pick needs a credible recommendation that talks about the request's needs.
    `upvotes_too`: the reading is also ranked with Noemi's upvote rules (engine.rank.counts_twice, stands_out, as config
    sets them), from what it has read
    and the comments its live checks dropped, into result.with_upvotes (14 Oct 2026); the result itself is ranked
    without it, so answer_request can decide which reading to keep as with the rule off.

    `profiles`: where writers' standing comes from (an object with user_stats and comment_flairs, such as
    engine.profiles.StoredProfiles); None leaves the writers as saved, known by name only.
    `prices`: the price list; None reads data/prices.json (engine.prices.load_prices). `today`: the day prices are
    judged on (how old they are), and live checks (how long ago Reddit was read); None is today.
    `product_facts`: the facts list (engine/product_facts.py); None reads data/product_facts.json.
    `brand_lines`: the brand-lines list (engine/brand_lines.py); None reads data/brand_lines.json.
    `summaries`: the one-line summaries; None reads the library's summaries.json, whose broken entries are left out and
    named in skipped_files.
    `product_pages`: the products' own pages and makers' images (engine/product_pages.py); None reads
    data/product_pages.json.
    `live_check_required`: None follows LIVE_CHECK_REQUIRED (on). False uses every thread whatever its last live
    check: only to see what answers would quote once every thread is checked (engine.slice_eval.threads_behind_answers).
    `live_checker` (engine.live_check.LiveChecker): every quote about to be shown is checked against the comment on
    Reddit itself; a comment deleted, removed or edited since we saved it is dropped, its votes no longer count, and
    the answer is written again without it, until every quote it shows has passed. With it, a thread's age no longer
    holds it back (live_check_required defaults to off), since what is shown is checked live anyway.
    """
    result = PipelineResult(query)
    if query.status != "ok":
        return result
    today = today or _today()
    threads_dir = Path(library_dir) / "threads"
    # Read once and kept in memory until one of its files changes (engine.library_cache; latency, 12 Oct 2026). A broken
    # file is left out and named, never quietly: one had stopped every answer (11 Oct 2026).
    library = loaded_library(threads_dir)
    result.skipped_files.extend(library.problems)
    every_checked = library.checked
    candidates = LocalSource(threads_dir, skip_broken=True, threads=library.threads,
                             remembered=library.remembered).find_threads(query, limit=sys.maxsize)  # limit: below
    about_it = [t for t in candidates if _about_the_request(t, query)]
    result.not_extracted = [t.id for t in about_it if t.id not in every_checked]  # nothing to offer until read
    if live_check_required is None:
        live_check_required = LIVE_CHECK_REQUIRED and live_checker is None
    required = live_check_required
    exempt = not required or _in_gold_set(threads_dir)
    extracted = [t for t in about_it if t.id in every_checked]
    result.waiting_live_check = [t.id for t in extracted if not (exempt or _checked_live_recently(t, today))]
    usable = [t for t in extracted if t.id not in result.waiting_live_check]
    result.threads_available = len(usable)
    threads = usable[:max_threads]
    checked = {t.id: every_checked[t.id] for t in threads}
    if not exempt:  # the same rule, comment by comment, in slimmed threads (13 Oct 2026)
        checked = {t.id: _recently_verified(checked[t.id], t, today) if t.slimmed else checked[t.id] for t in threads}
    if profiles is not None:
        threads = [with_profiles(t, profiles, _commented(checked[t.id])).thread for t in threads]
    result.threads_used = [t.id for t in threads]
    result.comments_read = sum(len(shown_comment_ids(t)) for t in threads)  # what the AI read in them (12 Oct 2026)
    result.bodies = comment_bodies(threads)

    mentions = _not_sets(_product_mentions(checked), result, query.product_type)
    # Grouped for this request's type (13 Oct 2026): "Fellow kettle" in a kettle answer is Fellow's kettle line. An
    # ingredient-led request has no one type: its products are grouped as the library's are.
    grouping_type = None if query.ingredient_led else query.product_type
    index = _name_index(library)  # the library's pairs of names that could match, worked out once (13 Oct 2026)
    product_facts = load_product_facts() if product_facts is None else product_facts
    known = _known_products(product_facts)  # names the facts list knows as one product each (14 Oct 2026)
    brand_ranges = _library_ranges(library)  # what the whole library names of each brand's products (14 Oct 2026)
    groups = group_products(mentions, product_type=grouping_type, index=index, known=known, ranges=brand_ranges)
    of_another_type = _of_another_type(groups, query, result)
    if of_another_type:  # grouped again without them, so they neither count for nor name a product (13 Oct 2026)
        groups = group_products([m for m in mentions if _typed(m) not in of_another_type], product_type=grouping_type,
                                index=index, known=known, ranges=brand_ranges)
    brand_lines = load_brand_lines() if brand_lines is None else brand_lines
    prices = load_prices() if prices is None else prices
    # The price and facts lists write their products as their makers do: a name in their words is shown so (15 Oct 2026).
    makers, curated = _spelling_lists(brand_lines, prices, product_facts, query.category)
    kept_groups = _groups_to_rank(groups, query, result, {t.id: t.title for t in threads}, brand_lines, curated, makers)
    # A product named only by its brand is that brand's line when the brand-lines list says the brand sells the type
    # (17 Oct 2026, within Noemi's decision 8 of 16 Oct 2026: writers' "Circulon pans" is the Circulon frying pan line).
    kept_groups = _brand_only_lines(kept_groups, query, brand_lines, prices, product_facts)
    lines = {g.key for g in kept_groups if g.loose}  # the brand or line names kept as the brand's whole line
    # Their brand-lines entries, whose range pages the answer links to (Noemi's night decision 1, 14 Oct 2026).
    ranges = {g.key: line for g in kept_groups if g.loose and (line := _brand_line(g, query, brand_lines)) is not None}
    types = {g.key: _own_type(g, query) for g in kept_groups}  # each product's own type (13 Oct 2026)
    kept_groups, price_checks = _within_budget(kept_groups, query, prices, today, result, brand_lines, types)
    named_before = {g.key: g.name for g in kept_groups if not g.loose}  # the names the price list was asked about
    kept_groups, cautions, formulas = _suited_to_request(kept_groups, query, product_facts, result, types)
    kept_groups = _sold_under_shown_name(kept_groups, named_before, query, prices, price_checks, result, types, today)
    lines -= result.lines_as_one_product  # lines whose products are one known product are that product (14 Oct 2026)
    kept_groups = _one_per_name(kept_groups)  # the names are final here: one item per name (13 Oct 2026)
    result.ranked_as_lines = [g.name for g in kept_groups if g.key in lines]
    _note_other_names(kept_groups, cautions)
    # What the answer says beyond the ranking, as write_answer's keywords: about the request's active ingredients (13 Oct
    # 2026), which products its facts say are prescription-only in the UK (Noemi's decision 5 of 14 Oct 2026), which
    # comments' words are Reddit's embed page's text (found edited, they kept Reddit's current text: Noemi's decision 3
    # of 15 Oct 2026), whose quotes are never widened, and each product's own page and its maker's image (Noemi's
    # decisions of 15 Oct 2026, late afternoon).
    product_pages = load_product_pages() if product_pages is None else product_pages
    wording = {**_ingredient_wording(query, kept_groups, types, formulas, result.line_forms),
               "prescription": _prescription_only(kept_groups, formulas), "flattened": flattened_comments(threads),
               "pages": _pages(kept_groups, named_before, query, product_pages, types)}
    kind_mentions = _kind_mentions(checked)
    kinds = group_kinds(kind_mentions, kept_groups, query.category, query.product_type or "")
    with_a_kind = kinds_of(kinds)
    result.notes_without_kind = [n.about for n in kind_mentions if n not in with_a_kind]
    result.contradicting_writers = sorted(contradicting_writers(groups, {c.id: c for t in threads for c in t.comments}))
    # What a comment talks about of the request is judged by the needs a comment can talk about (15 Oct 2026): the need
    # rule's, so the reason, the breakdown and the quotes shown first say no more than the rule judges.
    scored, kind_notes = _score(threads, checked, kept_groups, kinds, judged_needs(query),
                                set(result.contradicting_writers), request_asks(query))
    if summaries is None:
        loaded = load_summaries(Path(library_dir) / SUMMARIES_FILE)
        summaries = loaded.entries
        result.skipped_files.extend(loaded.problems)

    def rank_and_write(result: PipelineResult, scored: list[ScoredMention], kind_notes: list[KindNote],
                       upvote_rule: bool) -> PipelineResult:
        """Modules 6 and 7 for this reading: the ranking, the answer, and the live checks of what it shows."""
        result.ranking, more_downsides = _fold_brand_skips(
            _fold_brand_picks(_ranked(scored, query, kind_notes, kinds, need_led, result.skip_only, upvote_rule,
                                      result.unconfirmed),
                              kept_groups, result, query.product_type),
            kept_groups, result)
        unsuited_kinds = _unsuited_kinds(result.ranking.kinds, query, product_facts)
        folded = {item.name for item in result.folded_brand_picks}
        care = _care_tips(threads, checked, [g for g in kept_groups if g.name not in folded], kinds, query)
        models, model_prices = _brand_models(result.ranking, kept_groups, query.product_type, price_checks)
        result.answer = write_answer(result.ranking, result.bodies, query.product_type, price_checks, care, cautions,
                                     models, request_asks(query), model_prices, more_downsides, unsuited_kinds,
                                     judged_needs(query), query.text, summaries,
                                     _worth_left_out(result.ranking, kept_groups), **wording, ranges=ranges)
        if live_checker is not None:
            _check_live(result, live_checker, scored, kind_notes, kinds, query, price_checks, care, cautions,
                        kept_groups, unsuited_kinds, need_led, summaries, wording, ranges, upvote_rule=upvote_rule)
        thread_of = {c.id: t.id for t in threads for c in t.comments}
        quoted = {thread_of.get(quote.comment_id) for _, quote in _every_quote(result.answer)}
        result.threads_quoted = [tid for tid in result.threads_used if tid in quoted]
        if not (result.answer.picks or result.threads_used or result.waiting_live_check or result.not_extracted):
            # Nothing saved is about it (14 Oct 2026): say that, not that the evidence fell short. Changed in place, so
            # the answer stays the one module 7 wrote (the pre-check finds it by itself, engine/precheck.py).
            result.answer.message = NO_THREADS.format(products=plural(query.product_type))
        return result

    readable = set(result.bodies)
    rank_and_write(result, scored, kind_notes, upvote_rule=False)
    if upvotes_too:
        # The same reading, ranked with Noemi's upvote rule (14 Oct 2026). The comments its live checks dropped (gone,
        # changed or unreadable on Reddit) stay dropped, so their votes and notes count for nothing here either; anything
        # new it shows is checked live as usual (the checker remembers the rest). When the rule changes nothing in the
        # ranking, the answer is the same: it isn't written again.
        dropped = readable - set(result.bodies)
        scored = [m for m in scored if m.comment_id not in dropped]
        kind_notes = [n for n in kind_notes if n.comment_id not in dropped]
        if not _upvotes_change_nothing(scored, query, kind_notes, kinds, need_led, result.skip_only,
                                       result.unconfirmed):
            again = replace(result, live_dropped=dict(result.live_dropped), live_put_off=0)
            result.with_upvotes = rank_and_write(again, scored, kind_notes, upvote_rule=True)
    return result


def _upvotes_change_nothing(scored, query: ParsedQuery, kind_notes, kinds, need_led: bool,
                            skip_only: Mapping[str, str], unconfirmed: Mapping[str, int] | None = None) -> bool:
    """Whether Noemi's upvote rules (14 Oct 2026: counting twice, and a comment standing out in its thread) leave a
    reading's ranking as it is: every product meets the bar, is an Also worth a look item or neither, as without them,
    none that meets it has a voice counted twice, and none is shown thanks to a comment standing out (which its reason
    would say). The rest of a ranking doesn't depend on the rules, so its answer would be the same."""
    def marks(ranking: RankingResult) -> list[tuple]:
        return [(p.key, p.qualifies, p.worth_a_look, p.qualifies and bool(p.counted_twice),
                 p.by_standout and (p.qualifies or p.worth_a_look)) for p in ranking.products]

    return (marks(_ranked(scored, query, kind_notes, kinds, need_led, skip_only, False, unconfirmed))
            == marks(_ranked(scored, query, kind_notes, kinds, need_led, skip_only, True, unconfirmed)))


# Why a product found only in a wider reading isn't a pick (answer_request, 11 Oct 2026), nor, since 14 Oct 2026, one in
# any reading of a category of config.NEED_RULE_IN_EVERY_READING (haircare; skincare too since 15 Oct 2026).
WIDER_READING_SHORTFALL = "no credible recommendation talks about what you asked for"


def _ranked(scored, query: ParsedQuery, kind_notes, kinds, need_led: bool,
            skip_only: Mapping[str, str] | None = None, upvote_rule: bool = False,
            unconfirmed: Mapping[str, int] | None = None) -> RankingResult:
    """Module 6's ranking. In a wider reading (`need_led`) of a request that asks for something besides the product, a
    product with no credible recommendation talking about it can't be a pick (answer_request), nor "Also worth a look"
    (13 Oct 2026); in every reading for a category of config.NEED_RULE_IN_EVERY_READING (haircare: Noemi's decision 4 of
    14 Oct 2026; skincare: her decision 3 of 15 Oct 2026). What it asks for besides the product are its needs that a
    comment can talk about (engine.needs.judged_needs, 15 Oct 2026): not an active ingredient it names, nor a size.
    `skip_only`: {product key: reason} of the brand lines a hard requirement keeps from being picks (a whole brand can't
    be checked): never a pick nor "Also worth a look", but listed under Skip these when their credible warnings put them
    there (Noemi's decision 1 of 13 Oct 2026). `upvote_rule`: with Noemi's upvote rules (14 Oct 2026), as config sets
    them: counting twice (config.UPVOTE_COUNTS_MORE) and a comment standing out (config.STANDOUT_ON). `unconfirmed`:
    {product key: how many of the request's must-haves its facts can't confirm} (PipelineResult.unconfirmed): those
    products rank after the confirmed ones (Noemi's decision 1 of 15 Oct 2026; engine.rank)."""
    ranking = rank_products(scored, query.category, kind_notes, placements(kinds),
                            upvote_rule=upvote_rule and config.UPVOTE_COUNTS_MORE,
                            standout_rule=upvote_rule and config.STANDOUT_ON, unconfirmed=unconfirmed)
    judged = {need.name for need in judged_needs(query)}
    if (need_led or query.category in NEED_RULE_IN_EVERY_READING) and judged:
        ranking.products = [replace(p, qualifies=False, shortfall=WIDER_READING_SHORTFALL, worth_a_look=False)
                            if (p.qualifies or p.worth_a_look) and not _talks_about(p, judged)
                            else p for p in ranking.products]
    if skip_only:
        ranking.products = [replace(p, qualifies=False, worth_a_look=False, shortfall=skip_only[p.key])
                            if p.key in skip_only and (p.qualifies or p.worth_a_look) else p for p in ranking.products]
    return ranking


def _talks_about(product, needs: set[str]) -> bool:
    """Whether one of a product's credible recommendations talks about one of these needs (their names: the need rule's,
    engine.needs.judged_needs)."""
    return any(needs.intersection(m.needs) for m in product.credible_recommendations)


def _check_live(result: PipelineResult, live_checker, scored, kind_notes, kinds, query, price_checks, care,
                cautions=None, groups: list[ProductGroup] = (), unsuited_kinds: frozenset[str] = frozenset(),
                need_led: bool = False, summaries: Mapping[str, Summary] | None = None,
                wording: Mapping | None = None, ranges: Mapping[str, BrandLine] | None = None,
                upvote_rule: bool = False) -> None:
    """Checks every quote about to be shown against Reddit itself; drops the comments that fail and answers again.
    Since 13 Oct 2026 the quotes a shown summary cites are checked too (engine.answer.quotes_to_check): a summary never
    stands on a comment deleted or changed since.

    A comment that fails (gone, changed or unreadable) loses its votes too: the ranking is redone without it, so a
    deleted opinion never decides a pick. Each comment is asked about once (the checker also keeps its answer for
    48 hours). Stops when every shown quote has passed: until 12 Oct 2026 it stopped after 3 rounds (LIVE_CHECK_ROUNDS),
    and an answer written after a third round of drops was shown with its new quotes unchecked. Each round drops at
    least one comment, so it always ends. result.live_dropped counts the comments dropped by reason. Brand picks step
    aside for their own products again on the new ranking (`groups` are the product groups ranked): one whose product
    no longer qualifies comes back.

    The picks first (Noemi, 13 Oct 2026): a comment quoted only by "Also worth a look" or a summary (none of the
    needed_quotes) is read only if that needs no wait for Reddit's allowance (the checker's wait=False). Put off, it
    keeps its votes (it hasn't failed), and what stands on it is left out of the answer (without_unread);
    result.live_put_off counts them.
    """
    failed: set[str] = set()
    while True:
        new, put_off = set(), set()
        quotes = [quote for quote in quotes_to_check(result.answer) if quote.comment_id not in failed]
        may_wait = {quote.comment_id for quote in needed_quotes(result.answer)}
        outcomes = _checked_together(live_checker, quotes, may_wait)
        for quote in quotes:  # in the answer's order: a comment's first quote that fails says why it was dropped
            if quote.comment_id in new or quote.comment_id in put_off:
                continue
            outcome = outcomes[(quote.url, quote.text)]
            if outcome.status == "later":
                put_off.add(quote.comment_id)
            elif not outcome.show:
                new.add(quote.comment_id)
                result.live_dropped[outcome.status] = result.live_dropped.get(outcome.status, 0) + 1
        if not new:
            if put_off:
                standing_out = {p.key for p in result.ranking.products if p.by_standout}
                result.answer = without_unread(result.answer, put_off, standing_out)
                result.live_put_off = len(put_off)
            return
        failed |= new
        result.bodies = {cid: body for cid, body in result.bodies.items() if cid not in failed}
        ranking = _ranked([m for m in scored if m.comment_id not in failed], query,
                          [n for n in kind_notes if n.comment_id not in failed], kinds, need_led, result.skip_only,
                          upvote_rule, result.unconfirmed)
        result.ranking, more_downsides = _fold_brand_skips(
            _fold_brand_picks(ranking, groups, result, query.product_type), groups, result)
        models, model_prices = _brand_models(result.ranking, groups, query.product_type, price_checks)
        result.answer = write_answer(result.ranking, result.bodies, query.product_type, price_checks, care, cautions,
                                     models, request_asks(query), model_prices, more_downsides, unsuited_kinds,
                                     judged_needs(query), query.text, summaries,
                                     _worth_left_out(result.ranking, groups), **(wording or {}), ranges=ranges)


def _checked_together(live_checker, quotes, may_wait: set[str] | None = None) -> dict[tuple[str, str], object]:
    """The live check of each quote, {(link, text): engine.live_check.LiveResult}, with LIVE_CHECK_PARALLEL comments
    read at once (latency, 12 Oct 2026: one at a time, the checks were most of an answer's wait). Each comment's quotes
    are checked one after another, in the answer's order, up to its first that fails: the very checks made when every
    quote was checked in turn, so no comment is read more than before, and none of its later quotes, which the failure
    drops anyway. A comment not in `may_wait` (when given) is checked with wait=False, after those that may wait."""
    by_comment: dict[str, list] = {}
    for quote in quotes:
        by_comment.setdefault(quote.comment_id, []).append(quote)
    if may_wait is not None:  # the picks' comments first, so the reads free now go to them
        by_comment = dict(sorted(by_comment.items(), key=lambda item: item[0] not in may_wait))

    def check_comment(own: list) -> dict[tuple[str, str], object]:
        found = {}
        waits = may_wait is None or own[0].comment_id in may_wait
        for quote in own:
            key = (quote.url, quote.text)
            if key not in found:
                found[key] = (live_checker.check(quote.url, quote.text) if waits
                              else live_checker.check(quote.url, quote.text, wait=False))
                if not found[key].show:
                    break
        return found

    if LIVE_CHECK_PARALLEL <= 1 or len(by_comment) <= 1:
        found = [check_comment(own) for own in by_comment.values()]
    else:
        with ThreadPoolExecutor(max_workers=min(LIVE_CHECK_PARALLEL, len(by_comment))) as pool:
            found = list(pool.map(check_comment, by_comment.values()))
    return {key: outcome for each in found for key, outcome in each.items()}


def _checked_live_recently(thread: Thread, today: date) -> bool:
    """Whether an answer may quote the thread: Reddit itself was read for it in the last LIVE_CHECK_SHOWN_DAYS days, or
    it is a gold-set thread. A slimmed thread's kept comments are verified one by one: it may be quoted when one of them
    was verified in that time, and then only those (_recently_verified); with none, it waits as a whole thread would.
    One that keeps no comment at all has nothing to verify: its own last live read counts, as for a whole thread."""
    kept = [c for c in thread.comments if c.status == "ok"] if thread.slimmed else []
    if kept:
        return any(c.verified_at is not None and (today - c.verified_at.date()).days <= LIVE_CHECK_SHOWN_DAYS
                   for c in kept)
    return thread.read_from == "gold" or checked_live_within(thread, LIVE_CHECK_SHOWN_DAYS, today)


def _recently_verified(checked: CheckResult, thread: Thread, today: date) -> CheckResult:
    """A slimmed thread's checked extraction with only what rests on comments verified on Reddit in the last
    LIVE_CHECK_SHOWN_DAYS days (Comment.verified_at, calendar days as for threads): the 14-day rule, comment by comment
    (13 Oct 2026). A reply that takes its product from the comment above needs that comment verified too."""
    comments = {c.id: c for c in thread.comments}

    def verified(comment_id: str | None) -> bool:
        comment = comments.get(comment_id)
        return (comment is not None and comment.verified_at is not None
                and (today - comment.verified_at.date()).days <= LIVE_CHECK_SHOWN_DAYS)

    def usable(item) -> bool:
        if not verified(item.comment_id):
            return False
        if getattr(item, "refers_to", None) in ("parent", "earlier"):
            above = comments.get(comments[item.comment_id].parent_id)
            if item.refers_to == "earlier" and above is not None:
                above = comments.get(above.parent_id)
            return above is not None and verified(above.id)
        return True

    return replace(checked, kept=[m for m in checked.kept if usable(m)],
                   kept_notes=[n for n in checked.kept_notes if usable(n)],
                   kept_agreements=[a for a in checked.kept_agreements if usable(a)],
                   kept_care=[c for c in checked.kept_care if usable(c)])


def _in_gold_set(threads_dir: Path) -> bool:
    """Whether the folder is the gold set's (or inside it): hand-collected threads, exempt from live checks."""
    return Path(threads_dir).resolve().is_relative_to(Path(GOLD_DIR).resolve())


def _about_the_product(thread: Thread, product_type: str) -> bool:
    """Whether the thread's title or post names the product. Its comments don't count: they can mention it in passing.
    A slimmed thread's post is read by what its words named (engine.sources.names_product, 13 Oct 2026)."""
    return names_product(thread, product_type)


def _about_the_request(thread: Thread, query: ParsedQuery) -> bool:
    """Whether the thread is about what the request asks for (13 Oct 2026): its title or post names the product
    (_about_the_product), or, for a request naming active ingredients, one of them ("Glycolic acid: worth it?" for a
    glycolic acid toner). An ingredient-led request reads every thread module 2 found naming its ingredient anywhere,
    comments included: its products may be of any type, so no title names them all."""
    if query.ingredient_led:
        return True
    if _about_the_product(thread, query.product_type):
        return True
    ingredients = query.constraints.ingredients
    return bool(ingredients) and _about_the_product(thread, ingredient_type_name(ingredients))


# --- Module 4: products and kinds ---

def _known_products(product_facts: list[ProductFacts]) -> dict[str, list[tuple[str, ...]]]:
    """{category: the words of each facts entry's name that is one product's} (name levels, 14 Oct 2026): grouping never
    makes such a name a line (engine.group_products), whatever descriptions writers add to it ("... SPF50+ PA++++"), and
    never joins two of them. An entry under a brand's name, alone or with only its type's words and words that never
    name a model ("GreenPan", "Darto pans"), speaks for the brand's line (find_brand_facts): it isn't one. Worked out once
    per facts list."""
    found = _KNOWN.get(id(product_facts))
    if found is not None and found[0] is product_facts:
        return found[1]
    aliases = known_aliases()
    known: dict[str, list[tuple[str, ...]]] = {}
    for entry in product_facts:
        if _named_as_a_line(entry.product):
            continue  # "Medik8 Crystal Retinal line" (its six strengths): the line, never one product (15 Oct 2026)
        words = tuple(product_words(entry.product, aliases.get(entry.category, {})))
        brand = ProductGroup(f"{entry.category}:{words[:1]}", entry.product.split()[0], entry.category,
                             [ProductMention("facts", "facts", entry.product.split()[0], entry.category, "neutral")])
        if len(words) > 1 and _names_a_model(entry.product, brand, entry.product_type):
            known.setdefault(entry.category, []).append(words)
    _KNOWN.clear()
    _KNOWN[id(product_facts)] = (product_facts, known)
    return known


_KNOWN: dict[int, tuple[list, dict]] = {}  # id(facts list) -> (the list, _known_products' answer for it)


def _named_as_a_line(name: str) -> bool:
    """Whether a name ends in a word naming a line ("Medik8 Crystal Retinal line", "... series": engine.match_products.
    LINE_WORDS, which the words of a name leave out at its end since 15 Oct 2026)."""
    words = plain_words(name)
    return len(words) > 1 and words[-1] in LINE_WORDS


def _name_index(library) -> dict:
    """The pairs of names that could match among all the library's mentions (engine.group_products.library_name_index),
    worked out on the library's first answer and kept with it (engine.library_cache: gone when it is read again)."""
    found = library.remembered.get(_NAME_INDEX)
    if found is None:
        found = library.remembered[_NAME_INDEX] = library_name_index(_product_mentions(library.checked))
    return found


_NAME_INDEX = ("name index",)  # where the library keeps it (engine.library_cache.KeptLibrary.remembered)


def _library_ranges(library) -> LibraryRanges:
    """What the whole library names of each brand's products, by type (engine.group_products.LibraryRanges; name
    levels, 14 Oct 2026), worked out on the library's first answer and kept with it, as the name index is."""
    found = library.remembered.get(_RANGES)
    if found is None:
        found = library.remembered[_RANGES] = library_ranges(_product_mentions(library.checked))
    return found


_RANGES = ("library ranges",)  # where the library keeps them (engine.library_cache.KeptLibrary.remembered)


def _product_mentions(checked: dict[str, CheckResult]) -> list[ProductMention]:
    return [ProductMention(tid, m.comment_id, m.product, _category_of(m), m.stance, m.product_type, m.quote)
            for tid, res in checked.items() for m in res.kept]


_TYPE_CATEGORY = {p.name: p.category for p in PRODUCT_TYPES}
_TYPE_NAMES = frozenset(_TYPE_CATEGORY)  # module 1's types, once (14 Oct 2026: 394 of them to build a set of each time)


def _category_of(mention) -> str:
    """The category a mention counts in (14 Oct 2026, the general category): module 1's for a product type it lists,
    whatever the AI called it ("water bottle" is the general category's, even when the AI called it kitchen gear;
    "dishwasher" the kitchen's, even when an older extraction said "other"), else the AI's own."""
    return _TYPE_CATEGORY.get((mention.product_type or "").strip().lower(), mention.category)


def _not_sets(mentions: list[ProductMention], result: PipelineResult,
              requested: str | None = None) -> list[ProductMention]:
    """The mentions that aren't of a set, a block or a sharpener (config.OTHER_TYPE_WORDS, in the type the AI gave
    the mention): those are left out before grouping and named on the result, so a "Henckels knife block" never lends
    its votes to the writers' other Henckels mentions (10 Oct 2026). Any other type is decided for the whole product
    by most of its mentions (_another_type). `requested`: the request's product type (_names_a_set)."""
    kept = []
    for mention in mentions:
        if mention.product_type and _names_a_set(mention.product_type, requested):
            if uk_name(mention.product) not in result.left_out_as_other_type:
                result.left_out_as_other_type.append(uk_name(mention.product))
        else:
            kept.append(mention)
    return kept


def _names_a_set(product_type: str, requested: str | None = None) -> bool:
    """Whether a type in the AI's words names something that holds, sharpens, covers or bundles a product ("knife
    set", "knife blocks"), not the product: the word that says what it is, singular or plural, is in
    config.OTHER_TYPE_WORDS. That word is the last one ("knife stand"), or the one before "of" ("set of knives"):
    a "stand mixer" is a mixer (11 Oct 2026, when its every mention had been dropped).

    A type ending with a name of one of module 1's types whose own name ends with that word is that product (14 Oct
    2026, the general category: "sleeping bag", "down sleeping bag", "tool set", "tv stand"): with no request, or in a
    request for it (`requested`, the request's product type). In any other request it is left out as a set is, as
    before the taxonomy made it a type of its own: a "knife sharpener" in a chef knife request."""
    words = product_type.strip().lower().split()
    if not words:
        return False
    head = words[words.index("of") - 1] if "of" in words[1:] else words[-1]
    if head not in OTHER_TYPE_WORDS and head.removesuffix("s") not in OTHER_TYPE_WORDS:
        return False
    named = _ends_with_a_type(product_type)
    if named is None or named.name.split()[-1].removesuffix("s") != head.removesuffix("s"):
        return True
    return requested is not None and named.name != requested


@cache
def _ends_with_a_type(product_type: str):
    """The module 1 type that a type in the AI's words ends with one of the names of (the longest such name, the first
    type's when two are as long), or None: "down sleeping bag" ends with the sleeping bag's name, "frying pan set" with
    the cookware set's ("pan set"), "gooseneck kettle" with the electric kettle's ("kettle"). 14 Oct 2026. Only the
    names whose last word is the type's are looked at (_TYPE_ENDINGS): a name it ends with ends with that word."""
    text = " " + " ".join(product_type.strip().lower().split())
    best = None
    for size, form, product in _TYPE_ENDINGS.get(text.rsplit(" ", 1)[-1], ()):
        if text.endswith(" " + form) and (best is None or size > best[0]):
            best = (size, product)
    return best[1] if best else None


def _type_endings() -> dict[str, list[tuple[int, str, object]]]:
    """Each last word of module 1's names, with their plural "s" or "es" too -> (the name's length, that form, its
    type), in the types' and names' own order."""
    endings: dict[str, list[tuple[int, str, object]]] = {}
    for product in PRODUCT_TYPES:
        for keyword in product.keywords:
            for form in (keyword, keyword + "s", keyword + "es"):
                endings.setdefault(form.rsplit(" ", 1)[-1], []).append((len(keyword), form, product))
    return endings


_TYPE_ENDINGS = _type_endings()


def _of_another_type(groups: list[ProductGroup], query: ParsedQuery, result: PipelineResult) -> set[tuple]:
    """The mentions about another type of product inside the products of the requested type (13 Oct 2026), each told
    apart by its type (_typed), and named on the result (mentions_of_another_type).

    Which products are of the requested type is decided first, as before, by most of their mentions (_another_type).
    Inside those, a mention the AI typed as another type counts for nothing when its own words don't say it is the
    requested type either (_mention_of_another_type): a review of the answers had found a brand named alone in a
    sentence about moisturisers counting for the brand's scrub in an exfoliant answer, a writer's bare "Panasonic"
    kettle joining a hot water dispenser (which then stood for a kettle), and a chef knife line counting a writer's
    paring knives. The pipeline groups the other mentions again without them, so they neither count for nor lend their
    names to a product of the requested type. Done once: a regrouping that brings a new mention of another type into a
    product leaves it there (none did on the 20 sense-eval requests, 13 Oct 2026)."""
    found = set()
    wanted = _wanted_types(query)
    for group in groups:
        # A brand or line (a loose group) keeps its mentions of the requested type whatever most of its mentions are (name
        # levels, 14 Oct 2026): a brand named mostly for its Dutch ovens still has a skillet line, its other mentions
        # leave it, and a product of another type is left out whole, as before.
        if group.category != query.category or (_another_type(group, query) and not group.loose):
            continue  # left out whole, or never ranked
        for mention in group.mentions:
            if all(_mention_of_another_type(mention, w) for w in wanted):
                found.add(_typed(mention))
                if uk_name(mention.product) not in result.mentions_of_another_type:
                    result.mentions_of_another_type.append(uk_name(mention.product))
    return found


def _typed(mention: ProductMention) -> tuple:
    """A mention told apart by its type and quote too: the AI lists a brand named for its shampoo and its conditioner
    in one comment as two mentions, equal but for their types, and only the one of another type is left out."""
    return mention, mention.product_type, mention.quote


def _mention_of_another_type(mention: ProductMention, requested: str) -> bool:
    """Whether one mention is about another type of product than the one requested: the AI typed it as another type
    (_another_type_by_ai, on its type alone) and its name and quote don't name the requested type, leaving aside the
    AI's type itself and the word it ends with ("knife" in a paring knife, "air fryer" in an "air fryer oven"). The
    AI's types are noisy at the edges, so the writer's own words win when they say it is the requested type: a "COSRX
    AHA/BHA toner" the AI typed as a toner is an exfoliant still ("AHA" names one)."""
    product_type = (mention.product_type or "").strip().lower()
    if not product_type or not _another_type_by_ai([product_type], requested):
        return False
    words = f"{mention.product} {mention.quote}"
    # The AI's type is left out with the words of the requested type written just before it, which belong to the other
    # type's own name (name levels, 14 Oct 2026): "cast iron" in "cast iron dutch oven" names no skillet. b08's Lodge
    # line had counted a writer's Lodge Dutch ovens so.
    words = re.sub(rf"(?<!\w)(?:(?:{_requested_words(requested)})[\s-]+)*{re.escape(product_type)}(?:s|es)?(?!\w)", " ",
                   words, flags=re.IGNORECASE)
    return not mentions_product(words, requested, leave_aside=_word_left_aside(product_type, requested))


def _word_left_aside(product_type: str, requested: str) -> str:
    """The word that doesn't name the requested type on its own in a mention the AI typed as `product_type`: the last
    word of the AI's type ("knife" of a paring knife); and "knife" for a chef knife when the AI's type is another kind
    of knife named without the word (16 Oct 2026, the interview-fixes builder: "knife" alone is a chef's knife, as
    people mean it in "a good knife", but "Kiwi knives" the AI typed as a nakiri is the nakiri, and b07's Kiwi line had
    taken a second thread from such mentions; other kinds of knife are look-alikes of chef knives since 13 Oct 2026). A
    fuller name of the requested type ("chef's knife") still says it is one."""
    words = product_type.split()
    if requested == "chef knife" and "knife" not in words and any(word in _KNIFE_KINDS for word in words):
        return "knife"
    return words[-1]


# Kinds of knife that are no chef's knife, as the AI names them without the word "knife": Japanese and other kitchen
# knives (16 Oct 2026), with module 1's other knives (engine.query: paring, bread, steak...). Not the gyuto and santoku,
# which are chef knives, nor the bunka and kiritsuke, all-purpose knives writers recommend as one.
_KNIFE_KINDS = frozenset(OTHER_KNIVES) | {"nakiri", "usuba", "deba", "petty", "sujihiki", "honesuki", "cleaver",
                                          "yanagiba", "takohiki", "mukimono"}


@cache
def _requested_words(requested: str) -> str:
    """The names of a requested type (module 1's keywords and its own name) as one alternation of a regular expression,
    longest first: what may be written as part of another type's name before it ("cast iron dutch oven")."""
    product = next((p for p in PRODUCT_TYPES if p.name == requested), None)
    names = {requested, *(product.keywords if product else ())}
    return "|".join(re.escape(name) for name in sorted(names, key=lambda n: (-len(n), n)))


def _kind_mentions(checked: dict[str, CheckResult]) -> list[KindMention]:
    return [KindMention(tid, n.comment_id, n.about, n.stance) for tid, res in checked.items() for n in res.kept_notes]


def _spelling_lists(brand_lines: list[BrandLine], prices: list[Price], product_facts: list[ProductFacts],
                    category: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """(the brand-lines list's brands, the price and facts lists' products' names) of a category, for
    engine.group_products.maker_spelling: worked out once per three lists and kept with them, so answers pass it the
    same lists (it remembers its names by them; latency, 15 Oct 2026)."""
    key = (id(brand_lines), id(prices), id(product_facts), category)
    found = _SPELLING_LISTS.get(key)
    if found is None or found[0] is not brand_lines or found[1] is not prices or found[2] is not product_facts:
        if len(_SPELLING_LISTS) >= 16:
            _SPELLING_LISTS.clear()
        makers = tuple(sorted({line.brand for line in brand_lines if line.category == category}))
        curated = tuple(sorted({p.product for p in prices if p.category == category}
                               | {f.product for f in product_facts if f.category == category}))
        found = _SPELLING_LISTS[key] = (brand_lines, prices, product_facts, makers, curated)
    return found[3], found[4]


_SPELLING_LISTS: dict[tuple, tuple] = {}  # (the lists' ids, category) -> (the lists, the brands, the names)


def _groups_to_rank(groups: list[ProductGroup], query: ParsedQuery, result: PipelineResult,
                    titles: dict[str, str], brand_lines: list[BrandLine] = (),
                    curated: tuple[str, ...] = (), makers: tuple[str, ...] | None = None) -> list[ProductGroup]:
    """The product groups worth ranking for this request, each under the name to show; the others are named on the
    result. Every name is shown as a UK shopper knows it ("Sage", not "Breville": decision 12). `titles` is
    {thread id: title} for the threads read; `brand_lines` the brand-lines list (engine/brand_lines.py)."""
    kept = []
    same_category = [g for g in groups if g.category == query.category]
    typed: dict = {}  # once worked out, the names of these groups that name the requested type (_typed_names)
    # Each name with its brand written as its maker writes it (15 Oct 2026: "Philips Avent", not writers' "Phillips
    # Avent"; engine.group_products.maker_spelling), the brand-lines list's brands among the known spellings.
    # `curated`: the price and facts lists' products' names, as their makers write them; `makers`: the brand-lines
    # list's brands (_spelling_lists), worked out here when not given.
    if makers is None:
        makers = tuple(sorted({line.brand for line in brand_lines if line.category == query.category}))
    same_category = [replace(g, name=maker_spelling(g.name, g.category, makers, curated)) for g in same_category]
    for group in same_category:  # the ranking only looks at the request's category anyway
        if group.generic:  # it names no one product (15 Oct 2026): neither a product nor a brand's line
            result.left_out_generic.append(uk_name(group.name))
        elif group.loose:
            line = _brand_line(group, query, brand_lines)
            if _clear_brand(group, query, titles, same_category, line, typed):
                # An ingredient-led request has no one type: the line is named by its own ("Paula's Choice 2% BHA
                # exfoliant line"), not by the ingredient's (14 Oct 2026).
                named_as = (_own_type(group, query) if query.ingredient_led else None) or query.product_type
                kept.append(replace(group, name=_line_name(group, line, named_as,
                                                           bool(query.constraints.ingredients))))
            else:
                result.left_out_loose.append(uk_name(group.name))
                if line is not None and not line.sells:
                    result.brands_not_selling.append(NotSuited(uk_name(group.name), not_sold_reason(line)))
        elif _another_type(group, query):
            result.left_out_as_other_type.append(uk_name(group.name))
        else:
            kept.append(replace(group, name=uk_name(group.name)))
    return kept


def _brand_line(group: ProductGroup, query: ParsedQuery, brand_lines: list[BrandLine]) -> BrandLine | None:
    """The brand-lines entry for a brand or line name in this request (engine.brand_lines.find_brand_line, by the names
    writers used for it and their UK names), or None."""
    names = set(group.names) | {uk_name(name) for name in group.names}
    return find_brand_line(names, group.category, query.product_type, brand_lines)


def _line_name(group: ProductGroup, line: BrandLine | None, product_type: str, keep_ingredients: bool = False) -> str:
    """The name a brand or line ranked as the brand's line is shown under (engine.group_products.brand_pick_name):
    "Lodge cast iron skillet line". The brand as its writers spelled it, as a UK shopper knows it; but a name its
    writers wrote all in lowercase ("head and shoulders") is shown as its maker writes it when the brand-lines list
    has an entry for it ("Head & Shoulders shampoo line"; 12 Oct 2026)."""
    brand = uk_name(group.name)
    if line is not None and brand == brand.lower():
        brand = uk_name(line.brand)
    return brand_pick_name(brand, product_type, keep_ingredients)


def _brand_only_lines(groups: list[ProductGroup], query: ParsedQuery, brand_lines: list[BrandLine],
                      prices: list[Price], product_facts: list[ProductFacts]) -> list[ProductGroup]:
    """The groups, with each product named only by its brand ranked as that brand's line (17 Oct 2026; the
    coordinator's technical call within Noemi's decision 8 of 16 Oct 2026, her 12 Oct 2026 rule on brand-only names
    made consistent: they count when the brand-lines list says the brand makes the requested type, and are shown as
    "<Brand> <type> line").

    Writers name Circulon's and Ballarini's frying pans by brand only ("Circulon pans", "ballarini"), never a model, and
    module 4 keeps a brand none of whose models is named as one product: a PFAS-free answer had picked "Circulon pans"
    as if it were one pan, with a note that we couldn't confirm it. Such a group is its brand's line ("Circulon frying
    pan line"), shown with its range page and from price, and under a must-have left out as a whole brand, as every
    line is (10 Oct 2026), when all of these hold:
    - the brand-lines entry its names find (_brand_line, as for any brand's name) says the brand sells the type;
    - every name of it is that brand, or another name the entry gives it (also_called), alone or followed only by words
      that name no model (_names_only_its_brand): "Circulon pans", "circulon", "Zwilling/Ballarini non-stick pans";
    - no facts or price entry its names find names one product of it (_a_listed_product): then the lists say which
      product it is ("our place pan" is the Always Pan);
    - the brand's line isn't among these groups already (as "OXO" is, next to OXO's non-stick pans, in b10's threads):
      then the existing rules fold the two when both are shown (_the_line_itself), where a second line of the same
      name would be judged apart from the first and only joined to it afterwards (_one_per_name).
    Never for an ingredient-led request (no one type), nor with brand picks or this rule switched off
    (PIPELINE_BRAND_PICKS, config.BRAND_ONLY_NAMES_AS_LINES)."""
    if not (BRAND_ONLY_NAMES_AS_LINES and PIPELINE_BRAND_PICKS) or query.ingredient_led or not query.product_type:
        return groups
    # The brand-lines entries of the lines already here: a brand's line found among the groups is never made twice.
    lines_here = {id(line) for g in groups if g.loose and (line := _brand_line(g, query, brand_lines)) is not None}
    found = []
    for group in groups:
        line = None if group.loose or group.generic else _brand_line(group, query, brand_lines)
        if (line is not None and line.sells and id(line) not in lines_here
                and _names_only_its_brand(group, line, query.product_type)
                and not _a_listed_product(group, line, query.product_type, prices, product_facts)):
            group = replace(group, name=brand_pick_name(uk_name(line.brand), query.product_type), loose=True,
                            bases=tuple(dict.fromkeys((*group.bases, line.brand, *line.also_called))))
        found.append(group)
    return found


def _names_only_its_brand(group: ProductGroup, line: BrandLine, product_type: str) -> bool:
    """Whether every name of a group is the brand-lines entry's brand, or another name the entry gives it, alone or
    followed only by words that name no model (_names_a_model: the type's words and synonyms, "non-stick", descriptions
    such as "cheap"), with no number and no "or" (two products). Writers' "non stick" is read as "non-stick", a brand
    the UK knows by another name as the UK knows it (decision 12: "Breville" is Sage), and the first words of a
    co-brand name the entry gives, written alone, as that name ("Zwilling" in the group of "Zwilling/Ballarini
    non-stick pans", which module 4 joined it to)."""
    brand = _brand_of(line)
    aliases = known_aliases().get(group.category, {})
    # The maker's name before the brand in a co-brand name the entry gives, written alone ("Zwilling" for
    # "Zwilling/Ballarini"): module 4 joins a brand written alone to its one product named here, so in such a group it
    # is the co-brand name's.
    own = product_words(line.brand, aliases)
    co_brands = [words[:-len(own)] for other in line.also_called
                 if len(words := product_words(other, aliases)) > len(own) and written_alike(words[-len(own):], own)]
    named = False
    for name in group.names:
        if not (words := product_words(name, aliases)):
            continue  # filler words only: it names nothing
        if any(written_alike(words, first) for first in co_brands):
            continue
        if "or" in plain_words(name) or not any(
                find_brand_line([written], group.category, product_type, [line], of_a_product=True) is not None
                for written in (name, uk_name(name))):
            return False
        if _names_a_model(_NON_STICK.sub("non-stick", uk_name(name)), brand, product_type):
            return False  # "Breville kettle" is read as the UK knows it, "Sage kettle", as the entry's brand is
        named = True
    return named


_NON_STICK = re.compile(r"\bnon\s+stick", re.IGNORECASE)  # "non stick", as writers often spell "non-stick"


def _a_listed_product(group: ProductGroup, line: BrandLine, product_type: str, prices: list[Price],
                      product_facts: list[ProductFacts]) -> bool:
    """Whether a facts or price entry that a group's names find names one product of its brand, a model ("Our Place
    Always Pan" for "our place pan"), rather than the brand's whole range ("GreenPan", "OXO non-stick pan")."""
    brand = _brand_of(line)
    for name in group.names:
        entries = (find_facts(name, group.category, product_facts, product_type),
                   find_price(name, group.category, prices, None, product_type),
                   find_availability(name, group.category, prices, product_type))
        if any(entry is not None and _names_a_model(uk_name(entry.product), brand, product_type) for entry in entries):
            return True
    return False


def _brand_of(line: BrandLine) -> ProductGroup:
    """A brand-lines entry's brand as a group of its names (the brand and also_called), for _names_a_model."""
    return ProductGroup(f"{line.category}:{line.brand}", line.brand, line.category,
                        [ProductMention("brand_lines", "brand_lines", name, line.category, "neutral")
                         for name in (line.brand, *line.also_called)])


def _clear_brand(group: ProductGroup, query: ParsedQuery, titles: dict[str, str], groups: list[ProductGroup],
                 line: BrandLine | None = None, typed: dict | None = None) -> bool:
    """Whether a brand or line name clearly means the requested product (decision 9), so it is ranked as the brand's
    whole line. It must name something, and none of its names, nor most of the AI's types for its mentions, may say
    another type of product. Then the brand-lines entry for it decides, when there is one (`line`, 12 Oct 2026): yes
    when the brand sells the requested type, no when it doesn't. With none, its threads decide: more than
    BRAND_PICK_TITLE_SHARE of its mentions are in threads whose title names the requested product, and
    (BRAND_PICK_NEEDS_A_PRODUCT_OF_THE_TYPE) one of its own products named in the threads is of that type. "Lodge" in
    "Best cast iron skillet?" threads, next to "Lodge Blacklock skillet", is clear. `groups` are every product group of
    the request's category. `typed`: where _has_a_product_of_the_type keeps the groups' names that name the type, the
    first time it needs them, for the other brands of the same groups (latency, 13 Oct 2026)."""
    if not PIPELINE_BRAND_PICKS or not normalize_name(group.name) or _another_type(group, query):
        return False  # a name made of filler words only ("the one") names nothing
    if line is not None:
        return line.sells  # checked on the maker's own pages: better than any clue in the threads
    in_titled = sum(mentions_product(titles.get(m.thread_id, ""), query.product_type) for m in group.mentions)
    if in_titled <= BRAND_PICK_TITLE_SHARE * len(group.mentions):
        return False
    return not BRAND_PICK_NEEDS_A_PRODUCT_OF_THE_TYPE or _has_a_product_of_the_type(group, query, groups, typed)


def _has_a_product_of_the_type(brand: ProductGroup, query: ParsedQuery, groups: list[ProductGroup],
                               typed: dict | None = None) -> bool:
    """Whether a name of the brand, or of one of its products named in these threads (a name that holds the brand's,
    such as "Griswold skillet" for "Griswold"), names the requested type of product. The groups' names that name the
    type are listed once for every brand of the same groups (kept in `typed`, a dict, when given: _typed_names)."""
    own_names = list(brand.names)
    if any(mentions_product(name, query.product_type) for name in own_names):
        return True
    aliases = known_aliases().get(brand.category, {})
    typed = {} if typed is None else typed
    if "names" not in typed:
        typed["names"] = _typed_names(groups, query.product_type)
    return any(any(same_product(own, name, aliases) for own in own_names)
               for other, name in typed["names"] if other is not brand)


def _typed_names(groups: list[ProductGroup], product_type: str) -> list[tuple[ProductGroup, str]]:
    """Each group with each of its names that names the product type (engine.sources.mentions_product), in order."""
    return [(group, name) for group in groups for name in group.names if mentions_product(name, product_type)]


def _another_type(group: ProductGroup, query: ParsedQuery) -> bool:
    """Whether the product is another type of product than the one requested (for an ingredient-led request, than
    every type that can carry its ingredient: engine.ingredients.wanted_types, 13 Oct 2026).

    The AI's types decide when its mentions have them (instructions v6); when none has one (older extractions),
    its names do.
    """
    types = [m.product_type for m in group.mentions if m.product_type]
    wanted = _wanted_types(query)
    if _named_as_asked_with_its_ingredient(group, query, types):
        return False
    if types:
        return all(_another_type_by_ai(types, w) for w in wanted)
    return all(_another_type_by_name(group, query, w) for w in wanted)


def _wanted_types(query: ParsedQuery) -> tuple[str, ...]:
    """The product types an answer may show (engine.ingredients.wanted_types), and for an ingredient-led request those
    whose products count only with a facts entry confirming the ingredient (engine.ingredients.facts_types: a retinoid
    with benzoyl peroxide; 14 Oct 2026)."""
    return wanted_types(query.product_type) + facts_types(query.product_type)


def _named_as_asked_with_its_ingredient(group: ProductGroup, query: ParsedQuery, types: list[str]) -> bool:
    """For a request naming a type and an active ingredient ("glycolic acid toner"; 13 Oct 2026): whether one of the
    product's names names the requested type while the AI typed it as another type that can carry the ingredient. The
    AI types acid toners and pads as exfoliants; a "Glycolic Acid Toner" is the toner asked for."""
    ingredients = query.constraints.ingredients
    if not ingredients or query.ingredient_led or not types:
        return False
    carrying = set(wanted_types(ingredient_type_name(ingredients)))
    majority = Counter(t.strip().lower() for t in types).most_common(1)[0][0]
    return (query.product_type in carrying and majority in carrying
            and any(mentions_product(name, query.product_type) for name in group.names))


def _own_type(group: ProductGroup, query: ParsedQuery) -> str | None:
    """The product's own type (13 Oct 2026): the request's, or for an ingredient-led request the first of its wanted
    types the product is of, by the AI's types (most of its mentions) or, without them, its names; None when none
    says (a brand or line name). Its price and facts are looked up by it, and its form shown from it."""
    if not query.ingredient_led:
        return query.product_type
    wanted = _wanted_types(query)  # a type only facts can confirm comes last (engine.ingredients.facts_types)
    types = [m.product_type for m in group.mentions if m.product_type]
    if types:
        majority = Counter(t.strip().lower() for t in types).most_common(1)[0][0]
        return next((w for w in wanted if not _another_type_by_ai([majority], w)),
                    next((w for w in wanted if not _another_type_by_ai(types, w)), None))
    return next((w for w in wanted if any(mentions_product(name, w) for name in group.names)), None)


def _another_type_by_ai(types: list[str], requested: str) -> bool:
    """Whether the type most of a product's mentions give is another type than the one requested.

    - A tie for the most mentions keeps the product in: the AI isn't sure what it is. But only when one of the tied
      types is the requested one (13 Oct 2026): a tie between a hair mask and a leave-in treatment is sure it isn't a
      conditioner.
    - The requested type itself: kept.
    - Another of module 1's product types (engine.query.PRODUCT_TYPES): left out, even when it shares a word with
      the requested one ("stovetop kettle" for an electric kettle request).
    - A type in the AI's own words: left out, unless it names the requested type the way module 2 recognises it
      (engine.sources.mentions_product): "gooseneck kettle" names an electric kettle, "toaster" doesn't. A set, a
      block or a sharpener of it (config.OTHER_TYPE_WORDS) doesn't: "knife set" isn't a chef knife (10 Oct 2026).
    """
    counts = Counter(t.strip().lower() for t in types).most_common()
    if len(counts) > 1 and counts[0][1] == counts[1][1]:
        return all(_another_type_by_ai([t], requested) for t, n in counts if n == counts[0][1])
    majority = counts[0][0]
    if majority == requested:
        return False
    if majority in _TYPE_NAMES:
        return True
    if _names_a_set(majority, requested):
        return True
    named = _ends_with_a_type(majority)  # 14 Oct 2026: a "frying pan set" is the cookware set's, not a frying pan
    if named is not None and named.name != requested:
        return True
    if requested not in _TYPE_NAMES:
        return not _same_kind(majority, requested)
    return not mentions_product(majority, requested)


def _same_kind(product_type: str, requested: str) -> bool:
    """For a type the open model named (11 Oct 2026, from the appliance builder's findings): the AI's type is the
    requested one when it ends with its name ("basket air fryer" is an air fryer; "toaster oven" isn't a toaster), and
    the word just before doesn't make it another kind (config.OTHER_KIND_WORDS: an "immersion blender" isn't a
    blender)."""
    def singular(word: str) -> str:
        return word.removesuffix("es") if word.endswith(("ches", "shes", "sses", "xes")) else word.removesuffix("s")

    words = [singular(w) for w in product_type.strip().lower().split()]
    wanted = [singular(w) for w in requested.strip().lower().split()]
    if not wanted or words[-len(wanted):] != wanted:
        return False
    before = words[:-len(wanted)]
    return not (before and before[-1] in OTHER_KIND_WORDS)


def _another_type_by_name(group: ProductGroup, query: ParsedQuery, requested: str | None = None) -> bool:
    """Whether the product's names say it is another type of product than the one requested (`requested`, by default
    the request's), and none says it isn't."""
    requested = requested or query.product_type
    names = list(group.names)
    if any(mentions_product(name, requested) for name in names):
        return False
    others = [p.name for p in PRODUCT_TYPES if p.category == query.category and p.name != requested]
    return any(mentions_product(name, other) for name in names for other in others)


# --- Budgets (decision 11) ---

def _within_budget(groups: list[ProductGroup], query: ParsedQuery, prices: list[Price], today: date,
                   result: PipelineResult, brand_lines: list[BrandLine] = (),
                   types: Mapping[str, str | None] | None = None) -> tuple[list[ProductGroup], dict[str, PriceCheck]]:
    """Each product's price, checked against the request's budget, and whether it is still sold: the groups kept, and
    {product key: PriceCheck}.

    A product the price list says is no longer sold is left out first, whatever its price (named on the result as
    unavailable); one it says is sold carries that entry (PriceCheck.availability), for the answer's "Sold at" line.
    A product sold second-hand only counts as sold (Noemi's decision, 10 Oct 2026): it is kept, and its entry gives the
    answer's "Sold second-hand only" line. A known, recent price above the budget's max leaves the product out (named
    on the result). A brand pick has no single price, so it is never priced or checked for availability itself (named
    in not_priced), and an entry under its own name never leaves it out; but when every specific product of its brand
    among these groups is known not to be sold, its writers most likely mean those, so it is left out with them (10 Oct
    2026: "Cuisinart (their electric kettles)", from American writers' CPK-17s). When the newest entry under the
    brand's own name says it is sold second-hand only (engine.prices.find_brand_second_hand: "Griswold"), the brand
    pick carries that entry, so its answer shows the second-hand line instead of "Availability not checked yet". Late on
    10 Oct 2026: when the newest entry under the brand's name, alone or followed only by the product type's words
    ("OXO kettle"), says it isn't sold, the brand pick is left out (OXO's kettles are 120 V models: one OXO kettle with
    no type word in its name had kept "Oxo (their electric kettles)" in b06). Since 14 Oct 2026 (Noemi's night
    decision 1) a brand line's from price, from its brand-lines entry with where and when it was found
    (engine.brand_lines.from_price_entry), is its price, checked against the budget like any (PriceCheck.from_price),
    and says where it is sold unless a second-hand entry does; it is still named in not_priced (never priced from the
    price list), unless it is over the budget.

    `types`: each product's own type ({product key: type}, _own_type), which its price entries are looked up by; by
    default the request's (13 Oct 2026: an ingredient-led request has products of several types).
    """
    type_of = lambda g: (types or {}).get(g.key, query.product_type)
    budget = _budget(query)
    currency = budget.currency if budget else None
    product_type = query.product_type
    # Sold to UK shoppers now (engine.prices.counts_as_sold; Noemi, 15 Oct 2026): sold second-hand only counts only for
    # things people buy vintage on purpose.
    entries = {id(g): find_availability(g.name, g.category, prices, type_of(g)) for g in groups if not g.loose}
    not_sold = [g for g in groups if not g.loose and counts_as_sold(entries[id(g)]) is False]
    kept, checks = [], {}
    type_words = _type_words(query.product_type)
    sold_here = [g for g in groups if not g.loose and counts_as_sold(entries[id(g)]) is True]
    in_the_uk = [g for g in sold_here if entries[id(g)].available]  # not a product sold only abroad
    for group in groups:
        from_price = None
        if group.loose:
            # An entry under the brand ("Griswold", "OXO kettle"): second-hand only is shown; not sold leaves the brand
            # pick out, unless one of its own products here is known to be sold, which proves the brand is.
            sold = find_brand_entry(set(group.names) | {uk_name(n) for n in group.names}, group.category, prices,
                                    type_words, query.product_type)
            unsold_brand = (counts_as_sold(sold) is False
                            and not any(_same_brand(group, g, as_written=True) for g in sold_here))
            if unsold_brand or _only_unsold_products(group, groups, not_sold):
                result.left_out_unavailable.append(group.name)
                continue
            result.not_priced.append(group.name)
            # Shown only when second-hand and bought vintage on purpose (15 Oct 2026): another brand sold second-hand
            # only that one of its own products here proves is sold says nothing shown. Since 16 Oct 2026 (the
            # interview-fixes builder) also when it says the brand isn't sold in the UK (not_in_uk, Noemi's rule of 15
            # Oct 2026, evening: b07's Kiwi and b08's Field lines had shown "Availability not checked yet"), unless one
            # of its own products here is known to be sold in the UK, which proves the brand is.
            abroad = (sold is not None and sold.not_in_uk
                      and not any(_same_brand(group, g, as_written=True) for g in in_the_uk))
            sold = sold if sold is not None and (abroad or sold.second_hand and counts_as_sold(sold)) else None
            # Its from price (Noemi's night decision 1, 14 Oct 2026): the brand-lines entry's cheapest UK price of the
            # brand's products of the type, with where and when it was found, which also says the line is sold there
            # (so it wins over an entry saying the brand isn't sold in the UK).
            from_price = from_price_entry(find_brand_line(set(group.names) | {uk_name(n) for n in group.names},
                                                          group.category, type_of(group), brand_lines), group.name)
            sold = from_price if abroad and from_price is not None else sold or from_price
        else:
            sold = entries[id(group)]
        if counts_as_sold(sold) is False:
            result.left_out_unavailable.append(group.name)
            continue
        price = from_price if group.loose else find_price(group.name, group.category, prices, currency, type_of(group))
        check = replace(check_price(price, budget, today), from_price=from_price is not None)
        if check.status == "over":
            result.left_out_over_budget.append(group.name)
            if group.loose:  # a line whose cheapest product is over the budget: not ranked after all
                result.not_priced.remove(group.name)
        else:
            kept.append(group)
            checks[group.key] = replace(check, availability=sold)
    # A brand line under a budget (12 Oct 2026: b09, "under £150", had picked the Comandante coffee grinder line, whose
    # cheapest grinder costs more): when its brand-lines entry gives a "from" price (the brand's cheapest UK product of
    # this type) above the budget, even its cheapest product is over, so it is left out as over budget. No from price,
    # or one within the budget, keeps it (b07's Wüsthof sells cheaper knives than the Classic its writers name). So is
    # a product of that brand with no price of its own (13 Oct 2026: "Comandante with Red Clix" in b09's Also worth a
    # look): it costs at least its brand's cheapest. Since 14 Oct 2026 a from price with where and when it was found is
    # the line's own price above, so this catches the rest: one recorded without them, or checked over
    # PRICE_MAX_AGE_DAYS ago (never used to keep a line, whatever its age, as on 12 Oct).
    over_from = budget is not None and budget.max is not None and budget.currency == "GBP"
    for group in [g for g in kept if over_from and (g.loose or checks[g.key].status == "unknown")]:
        line = find_brand_line(set(group.names) | {uk_name(n) for n in group.names}, group.category, type_of(group),
                               brand_lines, of_a_product=not group.loose)
        if line is not None and line.from_price is not None and line.from_price > budget.max:
            kept.remove(group)
            checks.pop(group.key, None)
            if group.name in result.not_priced:
                result.not_priced.remove(group.name)
            result.left_out_over_budget.append(group.name)
    return kept, checks


def _sold_under_shown_name(groups: list[ProductGroup], named_before: Mapping[str, str], query: ParsedQuery,
                           prices: list[Price], checks: dict[str, PriceCheck], result: PipelineResult,
                           types: Mapping[str, str | None] | None = None,
                           today: date | None = None) -> list[ProductGroup]:
    """The products still sold under the name the answer shows them under (15 Oct 2026, the facts researcher), with
    what the price list says under that name.

    _within_budget asks the price list about each product under its writers' name, and only then may the facts step
    show it under its facts entry's name (_suited_to_request). When the writers' name found no entry saying whether it
    is sold, the entry the shown name finds decides: one saying it isn't sold leaves it out as unavailable, as if writers
    had called it that. Found in "retinoid": writers' "Tazorac .05%" (with "Tazorac") found the facts entry "Tazorac
    (tazarotene) cream and gel" by its other name, but the price list's entry saying it isn't sold in the UK fits only
    the shown name, not the writers' with its strength. Since 15 Oct 2026 (researchers record findings under the names
    answers show: engine/buyable.py) the same goes for an entry saying it is sold, which the answer then shows, and for
    a price: one found under the shown name only is its price, checked against the budget like any (over it, the
    product is left out). A product its writers' name found sold or priced, and one nothing is known of, are kept as
    they were; a brand line is never asked about here (its own check is under its brand)."""
    kept = []
    budget = _budget(query)
    for group in groups:
        before = named_before.get(group.key)
        check = checks.get(group.key)
        product_type = (types or {}).get(group.key, query.product_type)
        if before is not None and before != group.name and (check is None or check.availability is None):
            sold = find_availability(group.name, group.category, prices, product_type)
            if counts_as_sold(sold) is False:
                result.left_out_unavailable.append(group.name)
                checks.pop(group.key, None)
                continue
            if sold is not None and check is not None:
                check = checks[group.key] = replace(check, availability=sold)
        if before is not None and before != group.name and check is not None and check.price is None:
            price = find_price(group.name, group.category, prices, budget.currency if budget else None, product_type)
            if price is not None:
                priced = replace(check_price(price, budget, today or _today()), availability=check.availability)
                if priced.status == "over":
                    result.left_out_over_budget.append(group.name)
                    checks.pop(group.key, None)
                    continue
                checks[group.key] = priced
        kept.append(group)
    return kept


def _budget(query: ParsedQuery):
    """The request's budget as prices are checked against it: "under 100" has no currency, and module 1 doesn't guess
    one, but the shoppers are in the UK (Noemi, 9 Oct 2026), so it is in BUDGET_DEFAULT_CURRENCY."""
    budget = query.constraints.budget
    if budget is not None and budget.max is not None and budget.currency is None:
        budget = budget.model_copy(update={"currency": BUDGET_DEFAULT_CURRENCY})
    return budget


def _pages(groups: list[ProductGroup], named_before: Mapping[str, str], query: ParsedQuery,
           pages: list[ProductPage], types: Mapping[str, str | None] | None = None) -> dict[str, ProductPage]:
    """Each product's own page and its maker's image ({product key: entry of data/product_pages.json}; Noemi's decisions
    of 15 Oct 2026, late afternoon), found by the name the answer shows it under, then by its writers' name
    (engine.product_pages.find_page); a brand line by its line's name. Products with none aren't in it: a product not
    researched shows no link."""
    found = {}
    for group in groups:
        names = [group.name, named_before.get(group.key)]
        page = find_page(names, group.category, (types or {}).get(group.key, query.product_type), pages)
        if page is not None:
            found[group.key] = page
    return found


def _type_words(product_type: str | None) -> tuple[str, ...]:
    """The words of a product type and its plural ("electric kettle", "electric kettles"): the only words an entry
    under a brand may add to speak for the brand's products of that type (engine.prices.find_brand_entry)."""
    if not product_type:
        return ()
    return (product_type, plural(product_type))


def _only_unsold_products(brand: ProductGroup, groups: list[ProductGroup], not_sold: list[ProductGroup]) -> bool:
    """Whether the brand pick's own specific products among `groups` (_same_brand) are all in `not_sold`, and there
    is at least one. A product not checked yet counts as maybe sold. The few unsold products are looked at first
    (13 Oct 2026, the live site's engine time: comparing every brand with every product took 0.6 s an answer, almost
    always to find no unsold product of the brand); the same answer, for `not_sold` drawn from `groups`."""
    if not any(_same_brand(brand, g, as_written=True) for g in not_sold if not g.loose):
        return False
    unsold = {id(g) for g in not_sold}
    return not any(id(g) not in unsold and not g.loose and _same_brand(brand, g, as_written=True) for g in groups)


# --- Product facts (decided by Claude, 9 Oct 2026) ---

def _suited_to_request(groups: list[ProductGroup], query: ParsedQuery, product_facts: list[ProductFacts],
                       result: PipelineResult, types: Mapping[str, str | None] | None = None
                       ) -> tuple[list[ProductGroup], dict[str, list[str]], dict[str, ProductFacts]]:
    """The groups whose known facts suit the request, each kept product's cautions ({product key: [reason]}), and the
    facts entry each kept product found ({product key: entry}).

    A product with a hard clash (engine.product_facts.conflicts) is left out and named on the result with every hard
    reason; one with only soft clashes is kept, and their reasons go under its pick. A product with no facts entry, or
    whose entry doesn't give the facts a rule reads, is kept as it is. A brand pick has no single product, so it is
    never looked up: when the request has a hard requirement its product type can have (engine.product_facts.
    hard_requirements), it is left out of the picks and named on the result, since a whole brand can't be checked (10
    Oct 2026), but kept for Skip these only (result.skip_only; Noemi's decision 1 of 13 Oct 2026: listed there when its
    credible warnings put it there); otherwise it is kept. A kept product whose facts don't say whether it meets a hard requirement gets a note after its
    soft reasons: "we couldn't confirm it's PFAS-free" (engine.product_facts.unconfirmed, 10 Oct 2026), unless the names
    it is shown under say so (15 Oct 2026: a lip balm named "... SPF 25" has SPF; engine.product_facts.name_facts), and
    since Noemi's decision 1 of 15 Oct 2026 ranks after the products confirmed (how many it can't confirm goes in
    result.unconfirmed, which every ranking of the answer is given: engine.rank). A kept product
    with a facts entry is shown under the entry's name, taken from the maker's page, rather than as writers spelled it
    (10 Oct 2026); its key stays, so its price check and cautions still find it. An entry under a brand's own name
    speaks for the brand's whole line, so its pick is shown as that line: "GreenPan frying pan line" (12 Oct 2026).
    Groups that find the same entry are one product: the later (smaller) ones join the first, so their mentions are
    ranked together under its key (b02, 10 Oct 2026: "Biore watery essence" was a pick and "Biore aqua rich" a skip,
    both shown under one entry's name).

    Active ingredients (13 Oct 2026): when the request names some (constraints.ingredients), a product is kept only
    with evidence it contains each (engine.ingredients.evidence: its entry's formula, else the name it is shown under);
    otherwise it is left out, named in left_out_no_ingredient with the reason, and so is a brand pick. `types` gives
    each product's own type (_own_type): its entry is looked up by it, then, for an ingredient-led request, by its name
    alone, and the hard requirements are those its type can have.
    """
    requirements = hard_requirements(query)
    ingredients = query.constraints.ingredients
    kept, cautions, found_facts = [], {}, {}
    by_entry: dict[tuple[str, str], int] = {}  # a facts entry (name, category) -> where its product is in `kept`
    type_words = _type_words(query.product_type)
    for group in groups:
        own_type = (types or {}).get(group.key, query.product_type)
        if query.ingredient_led:
            requirements = hard_requirements(query, own_type)
        one_product = None  # the facts entry a line's products all find: the line is that one product
        if group.loose and ingredients:
            # A brand has many products: it can't be checked for an ingredient (13 Oct 2026), unless every product of it
            # named in the threads has a facts entry confirming the ingredient, so its versions don't differ in it (14
            # Oct 2026, the orchestrator's call): "Paula's Choice 2% BHA", its liquid and its gel.
            confirmed = _line_confirmed(group, groups, query, product_facts, types)
            if confirmed is None:
                reason = INGREDIENT_BRAND_UNCHECKABLE.format(ingredient=shown_ingredients(ingredients))
                result.left_out_no_ingredient.append(NotSuited(group.name, reason))
                continue
            entries, form = confirmed
            if len({entry.product for entry in entries}) == 1:
                # Its products are one product the facts list knows ("Finacea": its "Gel 15%" and its "(15% azelaic
                # acid)"): the line is that product, ranked with it as groups finding one entry are.
                one_product = entries[0]
                group = replace(group, loose=False)
                result.lines_as_one_product.add(group.key)
            else:
                result.lines_confirmed[group.key] = list(dict.fromkeys(entry.product for entry in entries))
                if form is not None:
                    result.line_forms[group.key] = form
                kept.append(group)
                continue
        if one_product is not None:
            facts = one_product
        elif group.loose:
            # A facts entry under the brand's own name speaks for the brand pick (late on 10 Oct 2026: GreenPan's FAQ
            # says all its pans are PFAS-free); without one, a whole brand can't be checked.
            facts = find_brand_facts(set(group.names) | {uk_name(n) for n in group.names}, group.category,
                                     product_facts, type_words, query.product_type)
            if facts is None:
                if requirements:
                    # Never a pick, but ranked, so its credible warnings can list it under Skip these (Noemi's decision
                    # 1 of 13 Oct 2026; it was left out of the ranking altogether).
                    reason = uncheckable_brand_reason(requirements)
                    result.left_out_not_suited.append(NotSuited(group.name, reason))
                    result.skip_only[group.key] = reason
                kept.append(group)
                continue
        else:
            facts = _facts_of(group, product_facts, own_type, query.ingredient_led)
        found = conflicts(query, facts)
        hard = [c.reason for c in found if c.hard]
        if hard:
            result.left_out_not_suited.append(NotSuited(group.name, "; ".join(hard)))
            continue
        if query.ingredient_led and own_type in facts_types(query.product_type) and (
                facts is None or facts.formula is None):
            # Only its facts can confirm it (a retinoid in a benzoyl peroxide answer; 14 Oct 2026), never its name.
            result.left_out_no_ingredient.append(NotSuited(
                facts.product if facts is not None else group.name,
                INGREDIENT_NOT_CONFIRMED.format(ingredient=shown_ingredients(ingredients))))
            continue
        missing_ingredient = _without_ingredient(group, facts, ingredients)
        if missing_ingredient:
            result.left_out_no_ingredient.append(NotSuited(facts.product if facts is not None else group.name,
                                                           missing_ingredient))
            continue
        if query.ingredient_led:
            shown_name = facts.product if facts is not None else group.name
            form = form_of(shown_name, own_type, _formula_form(facts))
            unsuited = _form_left_out(shown_name, form, query)
            if unsuited is not None:
                result.left_out_by_form.append(unsuited)
                continue
        entry = (facts.product, facts.category) if facts is not None else None
        if entry in by_entry:
            first = kept[by_entry[entry]]
            kept[by_entry[entry]] = replace(first, mentions=first.mentions + group.mentions)
            continue
        if entry is not None:
            by_entry[entry] = len(kept)
        if facts is None:
            kept.append(group)
        else:  # a brand pick whose entry is under its brand's name is still the brand's line (12 Oct 2026)
            # As the UK knows it (15 Oct 2026: the facts list names Aquaphor's ointment as its American maker does).
            shown_as = uk_name(facts.product)
            name = brand_pick_name(shown_as, query.product_type) if group.loose else shown_as
            kept.append(replace(group, name=name, loose=False))
            found_facts[group.key] = facts
        soft = [c.reason for c in found if not c.hard]
        # The names it is shown under can confirm a requirement too (15 Oct 2026: a lip balm named "... SPF 25").
        shown = (group.name,) + ((facts.product,) if facts is not None else ())
        missing = unconfirmed(query, facts, own_type if query.ingredient_led else None, names=shown)
        if missing:
            soft.append(unconfirmed_note(missing))
            result.unconfirmed[group.key] = len(missing)  # ranked after the confirmed (Noemi, 15 Oct 2026)
        if soft:
            cautions[group.key] = soft
    return kept, cautions, found_facts


def _facts_of(group: ProductGroup, product_facts: list[ProductFacts], own_type: str | None,
              ingredient_led: bool = False) -> ProductFacts | None:
    """A product's facts entry (engine.product_facts.find_facts): by the name it is shown under, of its own type (for an
    ingredient-led request, of any type when none of its own is found); when that name fits two products the list knows
    apart, by its other names, if they all point at one entry (name levels, 14 Oct 2026: a group of Paula's Choice's
    2% BHA liquid, shown as writers' "Paula's Choice 2% BHA", is the liquid, though that name fits its gel too)."""
    def lookup(name: str) -> ProductFacts | None:
        found = find_facts(name, group.category, product_facts, own_type)
        if found is None and ingredient_led:
            found = find_facts(name, group.category, product_facts)
        return found

    facts = lookup(group.name)
    if facts is None:
        named = {entry.product: entry for name in group.names if (entry := lookup(name)) is not None}
        if len(named) == 1:
            facts = next(iter(named.values()))
    return facts


def _line_confirmed(line: ProductGroup, groups: list[ProductGroup], query: ParsedQuery,
                    product_facts: list[ProductFacts], types: Mapping[str, str | None] | None
                    ) -> tuple[list[ProductFacts], str | None] | None:
    """For a line (a loose group) in an answer naming active ingredients (14 Oct 2026, the orchestrator's call): when
    every product of it named in the threads (the other groups of its brand or line, as the fold finds them:
    _same_brand_sized) has a facts entry whose formula confirms each ingredient, and for an ingredient-led request a
    form it may show, those entries and the forms they take, joined ("gel or liquid": engine.ingredients.form_kind reads
    each); otherwise None, and the line is left out as before (its versions may differ, or nothing is known of them).
    A line with fewer than two of its products named here can't be told not to differ: one version says nothing of the
    others ("Paula's Choice" in salicylic acid cleanser threads, a line there since the library names several of its
    cleansers, while the one named in those threads has the acid)."""
    ingredients = query.constraints.ingredients
    products = [g for g in groups if g is not line and not g.loose and _same_brand_sized(line, g)]
    if len(products) < 2:
        return None
    entries, forms = [], []
    for product in products:
        own_type = (types or {}).get(product.key, query.product_type)
        facts = _facts_of(product, product_facts, own_type, query.ingredient_led)
        if facts is None or facts.formula is None or _without_ingredient(product, facts, ingredients):
            return None
        if query.ingredient_led:
            form = form_of(facts.product, own_type, _formula_form(facts))
            if _form_left_out(facts.product, form, query) is not None:
                return None
            forms.append(form)
        entries.append(facts)
    shown = " or ".join(sorted(set(forms))) if forms else None
    return entries, shown


def _without_ingredient(group: ProductGroup, facts: ProductFacts | None, ingredients: list[str]) -> str | None:
    """Why a product is left out of a request for these active ingredients (13 Oct 2026), or None when there is
    evidence it contains each (engine.ingredients.evidence): its entry's formula decides when it has one ("its maker
    doesn't list salicylic acid among its actives"), otherwise the name it is shown under, the entry's or its group's
    (without a writer's "with ..."); with neither, "we couldn't confirm it contains salicylic acid". Never a guess."""
    # The maker's name when the product has a facts entry; otherwise the writers' name, without a writer's own
    # description of what it has ("<cleanser> with salicylic acid": engine.ingredients.own_name).
    name = facts.product if facts is not None else own_name(uk_name(group.name))
    actives = facts.formula.actives if facts is not None and facts.formula is not None else None
    for ingredient in ingredients:
        found = ingredient_evidence(ingredient, name, actives)
        if found.contains is False:
            return INGREDIENT_NOT_LISTED.format(ingredient=ingredient)
        if found.contains is None:
            return INGREDIENT_NOT_CONFIRMED.format(ingredient=ingredient)
    return None


def _prescription_only(groups: list[ProductGroup], found_facts: Mapping[str, ProductFacts]) -> frozenset[str]:
    """The keys of the products whose facts entry says they are prescription-only in the UK (Noemi's decision 5 of 14
    Oct 2026): the answer says so wherever it shows them (engine.answer.PRESCRIPTION_NOTE)."""
    return frozenset(g.key for g in groups
                     if g.key in found_facts and found_facts[g.key].facts.get("prescription_only") is True)


def _formula_form(facts: ProductFacts | None) -> str | None:
    """The form a facts entry's formula gives (from the maker's page), or None."""
    return facts.formula.form if facts is not None and facts.formula is not None else None


def _form_left_out(name: str, form: str | None, query: ParsedQuery) -> LeftOutByForm | None:
    """Why a product with the ingredient is left out of an ingredient-led answer for its form, or None when its form
    suits it (Noemi's decision 1 of 13 Oct 2026): the request names forms ("salicylic acid wash") and it isn't one of
    them; or it names none and the product is rinse-off ("a rinse-off cleanser: ask for a salicylic acid cleanser to see
    these"), or its form isn't known to be leave-on (an exfoliant whose name and facts don't say: never a guess)."""
    asked = query.constraints.forms
    kind = form_kind(form)
    if asked:
        if form in asked:
            return None
        listed = " or ".join(asked)
        reason = (INGREDIENT_FORM_NOT_CONFIRMED if kind is None else INGREDIENT_NOT_FORM_ASKED).format(forms=listed)
    elif kind == "leave-on":
        return None
    elif kind == "rinse-off":
        reason = INGREDIENT_RINSE_OFF.format(noun=rinse_off_word(form),
                                             ingredient=shown_ingredients(query.constraints.ingredients))
    else:
        reason = INGREDIENT_FORM_UNKNOWN
    return LeftOutByForm(name, reason, form if kind is not None else None, kind == "rinse-off")


def _ingredient_wording(query: ParsedQuery, groups: list[ProductGroup], types: Mapping[str, str | None],
                        found_facts: Mapping[str, ProductFacts], line_forms: Mapping[str, str] | None = None) -> dict:
    """What the answer says about a request's active ingredients (13 Oct 2026), as write_answer's keywords: the
    ingredients' names, the forms an ingredient-led request names, and for an ingredient-led request each product's
    form ({product key: form}, engine.ingredients.form_of), from its entry's formula, its name or its own type. {} for
    a request naming none."""
    if not query.constraints.ingredients:
        return {}
    forms = {}
    if query.ingredient_led:
        for group in groups:
            forms[group.key] = (line_forms or {}).get(group.key) or form_of(
                group.name, types.get(group.key), _formula_form(found_facts.get(group.key)))
    return {"ingredient": shown_ingredients(query.constraints.ingredients), "forms": forms,
            "forms_asked": list(query.constraints.forms)}


def _one_per_name(groups: list[ProductGroup]) -> list[ProductGroup]:
    """The groups, with those shown under the same name (its words, case and punctuation aside) joined into the first,
    the bigger: a reader can't tell two items of one name apart, so they are one product, ranked once with every mention
    (13 Oct 2026, the last guard of "the same product never twice": a lip balm answer had listed "Torriden lip balm line"
    and "torriden lip balm line" on its skip list, two lines of one brand, before module 4 made them one). The first's
    key, name and price check stand for both."""
    kept: list[ProductGroup] = []
    by_name: dict[tuple[str, ...], int] = {}
    for group in groups:
        words = tuple(normalize_name(group.name))
        if words and words in by_name:
            first = kept[by_name[words]]
            kept[by_name[words]] = replace(first, mentions=first.mentions + group.mentions)
            continue
        if words:
            by_name[words] = len(kept)
        kept.append(group)
    return kept


def _unsuited_kinds(kinds, query: ParsedQuery, product_facts: list[ProductFacts]) -> set[str]:
    """The keys of the kinds whose own facts entry clashes hard with the request: they give no "Look for" (decided by
    Claude late on 10 Oct 2026; b03 said "Look for: tret" to a beginner with sensitive skin, though the rules leave
    tretinoin products out of that answer). A kind takes an entry's facts only when the entry has the kind's very name
    (short names allowed: "tret" is Tretinoin), never one that only shares words with it ("salicylic acid" and "COSRX
    Salicylic Acid Daily Gentle Cleanser"). "Avoid" advice about such a kind stays."""
    aliases = known_aliases().get(query.category, {})
    unsuited = set()
    for kind in kinds:
        words = product_words(kind.name, aliases)
        own = [f for f in product_facts if f.category == query.category and product_words(f.product, aliases) == words]
        if words and any(c.hard for f in own for c in conflicts(query, f)):
            unsuited.add(kind.key)
    return unsuited


def _note_other_names(groups: list[ProductGroup], cautions: dict[str, list[str]]) -> None:
    """Adds a note to each product shown by its UK name whose writers used another one (UK_BRAND_NAMES: a "Sage"
    pick whose quotes say "Breville"), so the quotes make sense (10 Oct 2026). One note per UK name, under the first of
    its other names in UK_BRAND_NAMES (the maker's own spelling), however many of its spellings writers used (15 Oct
    2026: TEMPUR, which writers call Tempur-Pedic four ways)."""
    canonical: dict[str, str] = {}
    for brand, uk_brand in UK_BRAND_NAMES.items():
        canonical.setdefault(uk_brand, brand)
    for group in groups:
        noted: set[str] = set()
        noted_brands: list[str] = []  # a brand inside one noted already ("Aquaphor" in "Aquaphor Healing Ointment") isn't
        for brand, uk_brand in UK_BRAND_NAMES.items():
            if uk_brand in noted or any(brand.casefold() in other.casefold() for other in noted_brands):
                continue
            if uk_brand.lower() in group.name.lower() and any(
                    re.search(rf"(?<!\w){re.escape(brand)}(?!\w)", name, re.IGNORECASE) for name in group.names):
                cautions.setdefault(group.key, []).append(OTHER_NAME_NOTE.format(brand=canonical[uk_brand]))
                noted.add(uk_brand)
                noted_brands.append(brand)


# --- A brand pick steps aside for its own product (decided by Claude, 10 Oct 2026) ---

def _fold_brand_picks(ranking: RankingResult, groups: list[ProductGroup], result: PipelineResult,
                      product_type: str | None = None) -> RankingResult:
    """The ranking without the brand picks shown next to a specific product of their own brand ("Victorinox chef knife
    line" next to "Victorinox chef's knife"): the specific product stays, the brand pick leaves the ranking, so its
    support counts for nothing rather than twice. Two brand picks of the same brand shown together fold the same way:
    the one ranked lower into the one ranked higher. Each is named on the result with the product it stepped aside for
    (folded_brand_picks, worked out afresh each time). `groups` are the product groups ranked; `product_type` the
    request's.

    Only what is shown counts (10 Oct 2026, evening): a brand pick steps aside only when its own product is among the
    PICKS_SHOWN qualifying products shown with it, not for one that qualifies further down ("Lodge" had stepped aside
    for a Lodge pan ranked below the top 3, and vanished). After each fold the next product moves up, so it is checked
    again until nothing changes.

    Name levels (14 Oct 2026): a "product" none of whose names says more than the brand and the type ("lodge cast iron
    pan" next to the Lodge line; _the_line_itself) is the line written another way, not one of its products. The line
    never steps aside for it; the two fold as two lines of one brand do, the one ranked lower into the other (b08 had
    lost its Lodge pick so). A line written with its size first ('12" Lodge cast iron skillet line') is its brand's line
    too, as Also worth a look already read it (_same_brand_sized; b08's follow-up: it had been a pick next to the
    product '10.25" Lodge')."""
    by_key = {g.key: g for g in groups}
    qualifying = [(p, by_key[p.key]) for p in ranking.qualifying if p.key in by_key]
    folded, keys = [], set()
    while True:
        shown = [(p, g) for p, g in qualifying if p.key not in keys][:PICKS_SHOWN]
        step = None
        for position, (product, group) in enumerate(shown):
            if group.loose:  # a size written first is no brand ('12" Lodge' is Lodge's): _same_brand_sized
                own = next((p for p, g in shown if not g.loose and _same_brand_sized(group, g)
                            and not _the_line_itself(g, group, product_type)), None)
                own = own or next((p for p, g in shown[:position]
                                   if (g.loose and _lines_of_one_brand(g, group))
                                   or _the_line_itself(g, group, product_type)), None)
            else:  # the line written another way, shown below the line: it folds into it
                own = next((p for p, g in shown[:position] if g.loose and _the_line_itself(group, g, product_type)),
                           None)
            if own is not None:
                step = (product, own)
                break
        if step is None:
            break
        folded.append(FoldedBrandPick(step[0].name, step[1].name))
        keys.add(step[0].key)
    result.folded_brand_picks = folded
    return replace(ranking, products=[p for p in ranking.products if p.key not in keys]) if keys else ranking


def _lines_of_one_brand(a: ProductGroup, b: ProductGroup) -> bool:
    """Whether two lines (loose groups) are one brand's, so the one ranked lower folds into the other: one's name holds
    the other's brand (_same_brand_sized), and their names start with it (a size first aside). Not one read inside the
    other's name after another brand (name levels' follow-up, 14 Oct 2026): writers' "Rival Crock-Pot" is Rival's line,
    and the Crock-Pot line, a brand of its own sold new in the UK, had folded into it."""
    if not (_same_brand_sized(a, b) or _same_brand_sized(b, a)):
        return False
    aliases = known_aliases().get(a.category, {})

    def firsts(group: ProductGroup) -> set[str]:
        return {words[0] for name in group.names
                if (words := product_words(_without_leading_size(uk_name(name)), aliases))}

    return any(written_alike([x], [y]) for x in firsts(a) for y in firsts(b))


def _the_line_itself(product: ProductGroup, line: ProductGroup, product_type: str | None) -> bool:
    """Whether a specific product's group is a brand line written another way (name levels, 14 Oct 2026): it is of the
    line's brand (_same_brand) and none of its names says more than the brand, the type and words that never name a
    model (_names_a_model): "lodge cast iron pan" for the Lodge line in a cast iron skillet answer, but not "Lodge
    Blacklock skillet"."""
    return (not product.loose and line.loose and _same_brand(line, product)
            and not any(_names_a_model(name, line, product_type) for name in product.names))


def _fold_brand_skips(ranking: RankingResult, groups: list[ProductGroup],
                      result: PipelineResult) -> tuple[RankingResult, dict[str, list[ScoredMention]]]:
    """The ranking without the brands or lines on the skip list that a shown pick belongs to, and their credible
    warnings by that pick's key, to show under its Known downsides after its own (decided by Claude, 10 Oct 2026).

    Found reading the answers: b08 showed the pick "Lodge (their cast iron skillets)" and the skip "Lodge pans (their
    cast iron skillets)", b06 the pick "Fellow Stagg EKG" and the skip "Fellow Stagg (their electric kettles)": listing
    the brand as a skip says to skip the pick. Its warnings are about the pick's own brand or line, so they go with the
    pick and none is hidden. Only a brand or line steps aside (a loose group, _same_brand either way round, among the
    PICKS_SHOWN qualifying products as _fold_brand_picks leaves them): a specific product on the skip list stays, even
    of a picked brand ("Dualit Architect kettle" next to the pick "Dualit Classic kettle"), since skipping it is real
    advice. Each is named on the result (folded_skips, worked out afresh each time).

    Also (10 Oct 2026, night: b09's "Hario Mini (their coffee grinders)", while a credible warning about the Hario Mini
    Mill, one of its own grinders, was shown nowhere): a shown brand or line pick speaks for its specific products, so
    the credible warnings about those that are neither shown as picks nor on the skip list go under its downsides too,
    after its own."""
    by_key = {g.key: g for g in groups}
    shown = [(p, by_key[p.key]) for p in ranking.qualifying if p.key in by_key][:PICKS_SHOWN]
    more: dict[str, list[ScoredMention]] = {}
    folded, keys = [], set()
    for skipped in ranking.skip_list:
        group = by_key.get(skipped.key)
        if group is None or not group.loose:
            continue
        pick = next((p for p, g in shown if _same_brand(group, g) or _same_brand(g, group)), None)
        if pick is not None:
            more.setdefault(pick.key, []).extend(skipped.credible_warnings)
            folded.append(FoldedBrandPick(skipped.name, pick.name))
            keys.add(skipped.key)
    elsewhere = {p.key for p, _ in shown} | {s.key for s in ranking.skip_list}
    for pick, brand in shown:
        if not brand.loose:
            continue
        for product in ranking.products:
            group = by_key.get(product.key)
            if group is not None and not group.loose and product.key not in elsewhere and _same_brand(brand, group):
                more.setdefault(pick.key, []).extend(product.credible_warnings)
    result.folded_skips = folded
    ranking = replace(ranking, products=[p for p in ranking.products if p.key not in keys]) if keys else ranking
    return ranking, more


# --- Also worth a look: the brand rules (Noemi's decision 2 of 13 Oct 2026; rules decided by Claude) ---

def _worth_left_out(ranking: RankingResult, groups: list[ProductGroup]) -> set[str]:
    """The keys of the "Also worth a look" products (ranking.worth_a_look) the answer leaves out, by the brand rules
    (found in the 13 Oct 2026 answers: "Lodge dutch oven" next to the pick "Lodge Dutch oven line", "Shun chef knife
    line" next to "Shun Chef's knife"):
    - an item of the same brand as a brand-line pick shown (the PICKS_SHOWN qualifying products, as for picks): the
      pick speaks for its brand's products (_fold_brand_skips). An item whose name starts with a size ('10" Lodge') is
      of that brand too (_same_brand_sized);
    - a brand line whose own product, or another line of its brand, is a pick shown;
    - a brand line among the WORTH_A_LOOK_SHOWN items shown with its own product, or after a line of the same brand:
      it steps aside, as brand picks do (_fold_brand_picks); checked again after each step, until nothing changes;
    - an item whose brand or line is on the skip list: an answer never lists a product apart while telling you to skip
      its brand. A specific product skipped stays skipped, and doesn't stop its brand's other products."""
    by_key = {g.key: g for g in groups}
    shown_picks = [by_key[p.key] for p in ranking.qualifying[:PICKS_SHOWN] if p.key in by_key]
    skipped_lines = [by_key[p.key] for p in ranking.skip_list if p.key in by_key and by_key[p.key].loose]
    left_out, items = set(), []
    for product in ranking.worth_a_look:
        group = by_key.get(product.key)
        if group is None:
            continue
        if (any(_one_brand(pick, group) for pick in shown_picks)
                or any(_same_brand_sized(line, group) for line in skipped_lines)):
            left_out.add(product.key)
        else:
            items.append(group)
    while True:
        shown = [g for g in items if g.key not in left_out][:WORTH_A_LOOK_SHOWN]
        step = next((g.key for i, g in enumerate(shown) if g.loose and any(
            (not other.loose and _same_brand_sized(g, other))
            or (other.loose and j < i and (_same_brand_sized(other, g) or _same_brand_sized(g, other)))
            for j, other in enumerate(shown) if other is not g)), None)
        if step is None:
            return left_out
        left_out.add(step)


def _one_brand(pick: ProductGroup, item: ProductGroup) -> bool:
    """Whether an item can't be listed apart from a pick of its brand: the pick is a brand line and the item one of its
    brand's products or lines, or the item is a brand line and the pick one of its products or lines. Two specific
    products of one brand are alternatives ("Timemore C2" and "Timemore Slim"): both may be shown."""
    return (pick.loose and _same_brand_sized(pick, item)) or (item.loose and _same_brand_sized(item, pick))


def _same_brand_sized(brand: ProductGroup, product: ProductGroup) -> bool:
    """_same_brand, and the same with a size or a number before the names left aside ('10" Lodge', '8" Wusthof
    Classic'): sizes come first in some writers' names, never as the brand."""
    if _same_brand(brand, product):
        return True
    unsized = lambda g: replace(g, mentions=[replace(m, product=_without_leading_size(m.product)) for m in g.mentions])
    return _same_brand(unsized(brand), unsized(product))


# A size or a number at a name's start, followed by its unit or a space (never "1Zpresso").
_LEADING_SIZE = re.compile(r"^\s*\d+(?:[.,]\d+)?"
                           r"(?:\s*(?:\"|”|''|-?\s*(?:inch|inches|in|cm|qt|quart|l|litre|liter)\b)\s*|\s+)", re.IGNORECASE)


def _without_leading_size(name: str) -> str:
    """A name without a size or a number at its start: '10" Lodge cast iron' -> 'Lodge cast iron'."""
    rest = _LEADING_SIZE.sub("", name, count=1)
    return rest or name


def _brand_models(ranking: RankingResult, groups: list[ProductGroup], product_type: str | None,
                  price_checks: Mapping[str, PriceCheck] | None = None) -> tuple[dict[str, str], dict[str, str]]:
    """({brand pick's key: the name of its brand's model its credible writers recommend most}, {brand pick's key: that
    model's checked price, as the price line words it}) (10 Oct 2026). A model is a specific product of the brand
    still in the ranking (_same_brand), with at least BRAND_MODEL_MIN_CREDIBLE credible recommendations, whose name
    says more than the brand and the product type (_names_a_model). The most credible recommendations win, then the
    higher score. A brand pick with none is left out; a model with no price checked has no price, but one a shop is
    known to sell says where ("sold at The English Coffee Company, checked 10 Oct 2026")."""
    models, prices = {}, {}
    for brand_key, model in _brand_model_products(ranking, groups, product_type).items():
        models[brand_key] = model.name
        check = (price_checks or {}).get(model.key)
        if check is not None and check.price is not None and check.price.price is not None:
            prices[brand_key] = shown_price(check).text
        elif (sold := shown_availability(check)).available is True:
            # No one price fits the name, but a shop sells it (10 Oct 2026, late: "Bonavita gooseneck").
            prices[brand_key] = sold.text[:1].lower() + sold.text[1:]
    return models, prices


def _brand_model_products(ranking: RankingResult, groups: list[ProductGroup],
                          product_type: str | None) -> dict[str, "ProductScore"]:
    """{brand pick's key: the ranked product that is its brand's most recommended model} (see _brand_models)."""
    by_key = {g.key: g for g in groups}
    found = {}
    # The specific products with enough credible recommendations to be a brand's model, worked out once for every brand.
    models = [(p, g) for p in ranking.products if (g := by_key.get(p.key)) is not None and not g.loose
              and len(p.credible_recommendations) >= BRAND_MODEL_MIN_CREDIBLE]
    for brand in ranking.products:
        brand_group = by_key.get(brand.key)
        if brand_group is None or not brand_group.loose:
            continue
        candidates = [p for p, g in models
                      if _same_brand(brand_group, g) and _names_a_model(p.name, brand_group, product_type)]
        if candidates:
            found[brand.key] = max(candidates, key=lambda p: (len(p.credible_recommendations), p.score))
    return found


def _names_a_model(name: str, brand: ProductGroup, product_type: str | None) -> bool:
    """Whether a product's name says more than its brand and its type ("Victorinox Fibrox chef knife": yes;
    "Lodge cast iron pan": no): a word left after taking out the brand's words, the product type's and
    config.BRAND_MODEL_GENERIC_WORDS, or a number."""
    words = re.findall(r"[a-z0-9][a-z0-9'-]*", name.lower())
    if "or" in words:  # "restored griswold or wagner": two products, not one model
        return False
    if any(any(c.isdigit() for c in w) for w in words):
        return True
    brand_words = {w for n in list(brand.names) + [uk_name(n) for n in brand.names]
                   for w in re.findall(r"[a-z0-9][a-z0-9'-]*", n.lower())}
    # The type's plural too (14 Oct 2026): "Ruffwear harnesses" names no model of a dog harness. And the type's synonyms
    # (config.TYPE_SYNONYMS, name levels, 14 Oct 2026): "Zipzit patches" names no model of a spot treatment.
    generic = set(BRAND_MODEL_GENERIC_WORDS) | set((product_type or "").lower().split())
    generic |= set(plural(product_type).lower().split()) if product_type else set()
    generic |= {w for phrase in TYPE_SYNONYMS.get(product_type or "", ()) for form in (phrase, plural(phrase))
                for w in form.lower().split()}
    return any(w not in brand_words and w not in generic and w.rstrip("s") not in generic for w in words)


def _same_brand(brand: ProductGroup, product: ProductGroup, as_written: bool = False) -> bool:
    """Whether a specific product is one of a brand pick's own products: a name of the brand (as written, or as the UK
    knows it) is the first word or words of one of the product's names ("Victorinox" and "Victorinox chef's knife"), or
    module 4 says the two names mean the same product (engine.match_products.same_product: "CeraVe cleanser" and
    "CeraVe Hydrating Cleanser"). It depends on the two groups' names alone, so each pair of groups is worked out once
    (latency, 13 Oct 2026: an answer asks it of the same pairs from every brand rule).

    A line's names without the requested type's words count as its brand's names too (ProductGroup.bases, 15 Oct
    2026): "LL Bean sheets", always written so, is LL Bean's line in a bed sheets answer, so "LL Bean Percale Pima
    Cotton" is one of its products (it had been a pick while the line was listed under Skip these). `as_written`: by
    the names as written only, for the rules on what is sold (_within_budget): a line its writers name thirty times
    isn't taken for its one unsold model there."""
    bases = () if as_written else brand.bases
    key = (brand.category, frozenset(brand.names), bases, frozenset(product.names), product.name)
    found = _SAME_BRAND.get(key)
    if found is None:
        found = _SAME_BRAND.keep(key, _same_brand_of(brand, product, bases))
    return found


_SAME_BRAND = Table()  # (category, a brand's names, its bases, a product's names, its name) -> _same_brand's answer


def _same_brand_of(brand: ProductGroup, product: ProductGroup, bases: tuple[str, ...] = ()) -> bool:
    aliases = known_aliases().get(brand.category, {})
    brand_names = set(brand.names) | {uk_name(name) for name in brand.names} | set(bases)
    product_names = set(product.names) | {product.name}
    for name in brand_names:
        words = normalize_name(name)
        if words and any(normalize_name(other)[:len(words)] == words or same_product(name, other, aliases)
                         for other in product_names):
            return True
    return False


# --- Module 5: a weight for every mention and note ---

def _score(threads: list[Thread], checked: dict[str, CheckResult], groups: list[ProductGroup], kinds,
           needs: tuple[Need, ...] = (),
           contradicting: set[str] = frozenset(), asks: tuple[str, ...] = ()) -> tuple[list[ScoredMention], list[KindNote]]:
    """A weight for every product mention and kind note of the threads read (module 5), ready for the ranking.

    `needs` are the request's needs a comment can talk about (engine.needs.judged_needs, since 15 Oct 2026; every need
    of engine.needs.request_needs before): a product mention whose comment talks about one of them weighs
    NEED_MATCH_BOOST times as much, and they are the needs the mention carries (ScoredMention.needs). `contradicting`
    are the writers who contradict themselves (engine.contradictions): every mention and note of theirs counts as a low
    voice.
    """
    by_id = {t.id: t for t in threads}
    group_by_mention = group_of(groups)
    kind_groups = kinds_of(kinds)
    scored, notes = [], []
    for tid, res in checked.items():
        thread = by_id[tid]
        comments = {c.id: c for c in thread.comments}
        groups = copy_groups(thread)  # once per thread: it reads the whole thread
        # Copies count once (Noemi, 11 Oct 2026): the later copies' mentions and notes are left out.
        copied, repeats = copied_comment_ids(thread, groups), repeated_copies(thread, groups)
        upvotes = thread_upvotes(thread)  # each comment's beside the thread's, for the upvote rule (14 Oct 2026)
        named = _products_named(res)  # for a comment standing out in its thread (14 Oct 2026)
        voices = {}

        def voice_of(comment: Comment) -> VoiceScore:
            if comment.id not in voices:
                voice = score_voice(comment, thread, res.kept_agreements, copied=copied)
                voices[comment.id] = _as_low(voice) if _writer(comment) in contradicting else voice
            return voices[comment.id]

        for m in res.kept:
            if m.comment_id in repeats:
                continue
            group = group_by_mention.get(ProductMention(tid, m.comment_id, m.product, _category_of(m), m.stance))
            if group is None:
                continue  # left out above: another category, another type, a loose name, or over budget
            comment = comments[m.comment_id]
            voice = voice_of(comment)
            others = [o.product for o in res.kept if o.comment_id == m.comment_id and o.product != m.product]
            # First-hand use needs the AI's reading to agree when it says no use (13 Oct 2026; with_ai_evidence).
            evidence = with_ai_evidence(score_evidence(comment, m.product, m.stance, others), m.evidence,
                                        m.evidence_tags)
            met = _needs_talked_about(m.quote, comment.body, needs, asks, evidence.level == "long-term use", m.stance)
            weight = mention_weight(voice, evidence, m.stance) * (NEED_MATCH_BOOST if met else 1)
            standing = upvotes.get(m.comment_id)
            scored.append(ScoredMention(
                product_key=group.key, product_name=group.name, category=group.category, thread_id=tid,
                comment_id=m.comment_id, comment_url=str(comment.url), stance=m.stance,
                weight=weight, voice=voice.level, evidence=evidence.level,
                quote=m.quote, badges=badges(voice, evidence), author=_writer(comment), needs=met,
                written_as=m.product,
                upvotes=standing.score if standing else None,
                thread_comments=standing.thread_comments if standing else None,
                share_beaten=standing.share_beaten if standing else None,
                products_named=named[m.comment_id], needs_asked=bool(needs),
                others_of_another_type=_others_of_another_type(m, res.kept),
            ))
        for n in res.kept_notes:
            if n.comment_id in repeats:
                continue
            comment = comments[n.comment_id]
            voice = voice_of(comment)
            evidence = score_evidence(comment, n.about, n.stance)
            for kind in kind_groups.get(KindMention(tid, n.comment_id, n.about, n.stance), []):
                notes.append(KindNote(
                    kind_key=kind.key, kind_name=kind.name, thread_id=tid, comment_id=n.comment_id,
                    comment_url=str(comment.url), stance=n.stance, weight=mention_weight(voice, evidence, n.stance),
                    voice=voice.level, quote=n.quote, badges=badges(voice, evidence), author=_writer(comment),
                ))
    return scored, notes


def _others_of_another_type(mention, kept) -> tuple[str, ...]:
    """The names of a mention's comment's other products of another type with the same stance, as module 3 wrote them
    (15 Oct 2026, the coordinator's trial: a cast iron pick's quote praised the writer's carbon steel skillet, typed as a
    frying pan, which had replaced their cast iron). Types are module 3's: another when neither is the other's own kind
    (_same_kind: a "skillet" is a cast iron skillet's); a mention with no type tells nothing."""
    own = (mention.product_type or "").strip().lower()
    if not own:
        return ()
    found = []
    for other in kept:
        theirs = (other.product_type or "").strip().lower()
        if (other.comment_id != mention.comment_id or other.product == mention.product or other.stance != mention.stance
                or not theirs or _same_kind(theirs, own) or _same_kind(own, theirs)):
            continue
        found.append(other.product)
    return tuple(dict.fromkeys(found))


def _products_named(res: CheckResult) -> dict[str, int]:
    """{comment id: how many products it names}, from a thread's kept mentions (module 3), each product once whatever
    its spelling's capitals and punctuation (engine.match_products.normalize_name): one that names many shares its
    upvotes among them, so it never stands out for any (engine.rank.stands_out; 14 Oct 2026)."""
    names: dict[str, set[tuple[str, ...]]] = {}
    for m in res.kept:
        names.setdefault(m.comment_id, set()).add(tuple(normalize_name(m.product)))
    return {cid: len(found) for cid, found in names.items()}


def _needs_talked_about(quote: str, body: str, needs: tuple[Need, ...], asks: tuple[str, ...],
                        long_term_use: bool = False, stance: str = "recommend") -> tuple[str, ...]:
    """The request's needs a comment talks about (engine.needs.needs_met), for NEED_MATCH_BOOST; none when the
    mention's quote says the opposite of what the request asks (engine.answer.says_the_opposite: "it will give you a
    white cast" for a no-white-cast request; b02, 11 Oct 2026). Such a comment talks about the need, but against the
    request. So does a recommendation whose quote says its product didn't help with a need (engine.needs.
    said_not_to_help, 15 Oct 2026: "it did nothing for my oily skin"): that need isn't among those it talks about. A
    warning's not helping is what it warns about, so it keeps them."""
    if says_the_opposite(quote, asks):
        return ()
    met = needs_met(body, needs, long_term_use)
    if stance != "recommend" or not met:
        return met
    against = said_not_to_help(quote, needs)
    return tuple(need for need in met if need not in against)


def _as_low(voice: VoiceScore) -> VoiceScore:
    """The voice of a writer who contradicts themselves: low, whatever its signs (Noemi's rule, 9 Oct 2026). The signs
    are kept, so nothing else about the writer changes."""
    return replace(voice, level="low")


def _commented(result: CheckResult) -> set[str]:
    """The comments whose writers need a profile: those with kept product mentions, notes (review, 9 Oct 2026) or
    care tips (9 Oct 2026)."""
    return ({m.comment_id for m in result.kept} | {n.comment_id for n in result.kept_notes}
            | {c.comment_id for c in result.kept_care})


# --- Care tips: how to take care of it (Noemi, 9 Oct 2026; renamed 11 Oct 2026) ---

def _care_tips(threads: list[Thread], checked: dict[str, CheckResult], groups: list[ProductGroup], kinds,
               query: ParsedQuery) -> dict[str, CareTips]:
    """The credible care tips of the threads read, for the products ranked: {product key: CareTips}
    (engine/care_tips.py). An extraction made before instructions v7 has no care tips, so nothing changes for it."""
    tips = credible_care_tips(threads, checked)
    return attach_care_tips(tips, groups, kinds, query.category, query.product_type or "")


def _writer(comment: Comment) -> str | None:
    """The writer's name, lowercased, so the ranking counts each writer once; None for a deleted account."""
    return comment.author.name.lower() if comment.author is not None else None


def live_checker():
    """The live check of shown quotes through Reddit's embed page (engine/live_check.py), for real answers: checks are
    kept in this machine's folder, and in the bucket CREDIBLE_RECS_LIVE_CACHE_BUCKET names when it is set (the live
    site, which shares it with the daily pre-check, engine/precheck.py; 13 Oct 2026)."""
    from engine.live_check import checker_from_env

    return checker_from_env()


def cached_profiles() -> StoredProfiles:
    """Writers' standing from the library's profile store, then the Arctic Shift cache; never a call. What the command
    line, the demo and the evaluation use."""
    from engine.arctic_shift import ArcticShiftClient

    return StoredProfiles(ProfileStore(DEFAULT_LIBRARY_DIR / "profiles.json"), ArcticShiftClient())


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    result = answer_request(" ".join(argv), profiles=cached_profiles(), live_checker=live_checker())
    print(result.text())
    if result.answer is not None:
        if result.skipped_files:
            print(f"\n(left out of this answer: {len(result.skipped_files)} problem(s) in library files, first: "
                  f"{result.skipped_files[0]}; run `python -m engine.extract check` for the list)")
        if result.read_more:
            print(f"\n(the first {PIPELINE_MAX_THREADS} threads gave too few picks, so {len(result.threads_used)} were read)")
        print(f"\n(read for this answer: {len(result.threads_used)} threads, of {result.threads_available} saved about it, "
              f"and {result.comments_read:,} comments)")
        print(f"\n(threads used: {', '.join(result.threads_used)}; left out as another type: "
              f"{len(result.left_out_as_other_type)}; brand or line names left out: "
              f"{len(result.brand_or_line_names_left_out)}; ranked as a brand's line: {len(result.ranked_as_lines)}; "
              f"threads not extracted yet: {len(result.not_extracted)}; threads waiting for a live check: "
              f"{len(result.waiting_live_check)}; notes naming no kind: "
              f"{len(result.notes_without_kind)}; over budget: {len(result.left_out_over_budget)}; no longer sold: "
              f"{len(result.left_out_unavailable)}; not suited to the request: {len(result.left_out_not_suited)})")
        for item in result.left_out_not_suited:
            print(f"  not suited: {item.name} ({item.reason})")
        for item in result.brands_not_selling:
            print(f"  left out: {item.name} ({item.reason})")
        for item in result.folded_brand_picks:
            print(f"  brand pick stepped aside: {item.name} (for {item.stepped_aside_for})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
