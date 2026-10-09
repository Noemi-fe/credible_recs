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
- loose groups (a brand or line that fits several products, such as "Lodge" or "CeraVe") are ranked only when their
  threads make the product clear (Noemi's decision 9, 9 Oct 2026): none of their names says another type of product
  (the rule above), more than half of their mentions (config.BRAND_PICK_TITLE_SHARE) are in threads whose title
  names the requested product, and one of the brand's own products named in the threads is of that type ("Lodge
  Blacklock skillet"; config.BRAND_PICK_NEEDS_A_PRODUCT_OF_THE_TYPE). Then they are ranked under a name that says
  what they are: "Lodge (their cast iron skillets)". The others are left out: their mentions can't count for any
  one product. PIPELINE_BRAND_PICKS = False leaves them all out.
- with a budget in the request (a max and a currency), a product whose price (engine/prices.py, data/prices.json) is
  known and above the max is left out (Noemi's decision 11). A product with no known price, a price in another
  currency, or a price checked over PRICE_MAX_AGE_DAYS ago is kept, and its answer says so.
The three lists of products left out are kept on the result, so nothing is dropped silently; so are the "what to
look for" notes that name no kind (notes_without_kind, engine.group_kinds step 5), which the ranking and the answer
can't use.

Each mention carries its writer's name (lowercased), so the ranking counts one writer once per product, however
many comments or threads they praise it in (engine.rank).

Names are shown as a UK shopper knows them (decision 12): "Sage", not "Breville" (engine.group_products.uk_name).

Writers' standing (account age, karma, contributions, flair) isn't in the saved threads: Parse gives only names.
With `profiles` (engine.profiles.StoredProfiles in the command line, the web demo and the evaluation), it is filled in
from the library's profile store (kept for LIBRARY_REFRESH_DAYS, Noemi's decision of 9 Oct 2026) and Arctic Shift's
48-hour cache, never waiting on a call; `python -m engine.profiles warm data/library/threads` fills both beforehand.

Command line:
    python -m engine.pipeline "<request>"     prints the answer, from data/library
"""

import sys
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

from engine.answer import Answer, comment_bodies, render_markdown, write_answer
from engine.config import (
    BRAND_PICK_NEEDS_A_PRODUCT_OF_THE_TYPE,
    BRAND_PICK_TITLE_SHARE,
    BUDGET_DEFAULT_CURRENCY,
    PIPELINE_BRAND_PICKS,
    PIPELINE_MAX_THREADS,
)
from engine.credibility import badges, mention_weight, score_evidence, score_voice
from engine.extract import CheckResult, load_checked
from engine.group_kinds import KindMention, group_kinds, kinds_of, placements
from engine.group_products import ProductGroup, ProductMention, brand_pick_name, group_of, group_products, uk_name
from engine.library import DEFAULT_LIBRARY_DIR
from engine.match_products import known_aliases, normalize_name, same_product
from engine.models import Comment, Thread
from engine.prices import Price, PriceCheck, check_price, find_price, load_prices
from engine.profiles import ProfileStore, StoredProfiles, with_profiles
from engine.query import PRODUCT_TYPES, ParsedQuery, parse_query
from engine.rank import KindNote, RankingResult, ScoredMention, rank_products
from engine.sources import LocalSource, mentions_product


@dataclass
class PipelineResult:
    query: ParsedQuery
    threads_used: list[str] = field(default_factory=list)  # thread ids, most relevant first
    ranking: RankingResult | None = None
    answer: Answer | None = None  # None when module 1 asks a question or says no
    bodies: dict[str, str] = field(default_factory=dict)  # comment id -> text, to re-check quotes
    left_out_as_other_type: list[str] = field(default_factory=list)  # product names
    left_out_loose: list[str] = field(default_factory=list)  # brand or line names
    not_extracted: list[str] = field(default_factory=list)  # ids of threads about the product the AI hasn't read yet
    notes_without_kind: list[str] = field(default_factory=list)  # the "about" of each kept note that names no kind
    left_out_over_budget: list[str] = field(default_factory=list)  # product names, with a known price above the max

    def text(self) -> str:
        """The answer as Markdown, or module 1's question or polite no."""
        if self.answer is None:
            return self.query.question or self.query.message or "Nothing to show."
        return render_markdown(self.answer)


def answer_request(request: str, library_dir: Path = DEFAULT_LIBRARY_DIR, max_threads: int = PIPELINE_MAX_THREADS,
                   profiles=None, prices: list[Price] | None = None, today: date | None = None) -> PipelineResult:
    """Runs modules 1 to 7 on the saved library and returns everything each step decided.

    `profiles`: where writers' standing comes from (an object with user_stats and comment_flairs, such as
    engine.profiles.StoredProfiles); None leaves the writers as saved, known by name only.
    `prices`: the price list; None reads data/prices.json (engine.prices.load_prices). `today`: the day prices are
    judged on (how old they are); None is today.
    """
    query = parse_query(request)
    result = PipelineResult(query)
    if query.status != "ok":
        return result
    threads_dir = Path(library_dir) / "threads"
    every_checked = load_checked(threads_dir)
    candidates = LocalSource(threads_dir).find_threads(query, limit=sys.maxsize)  # the limit is applied below
    about_it = [t for t in candidates if _about_the_product(t, query.product_type)]
    result.not_extracted = [t.id for t in about_it if t.id not in every_checked]  # nothing to offer until read
    threads = [t for t in about_it if t.id in every_checked][:max_threads]
    checked = {t.id: every_checked[t.id] for t in threads}
    if profiles is not None:
        threads = [with_profiles(t, profiles, _commented(checked[t.id])).thread for t in threads]
    result.threads_used = [t.id for t in threads]
    result.bodies = comment_bodies(threads)

    groups = group_products(_product_mentions(checked))
    kept_groups = _groups_to_rank(groups, query, result, {t.id: t.title for t in threads})
    prices = load_prices() if prices is None else prices
    kept_groups, price_checks = _within_budget(kept_groups, query, prices, today or date.today(), result)
    kind_mentions = _kind_mentions(checked)
    kinds = group_kinds(kind_mentions, kept_groups, query.category, query.product_type or "")
    with_a_kind = kinds_of(kinds)
    result.notes_without_kind = [n.about for n in kind_mentions if n not in with_a_kind]
    scored, kind_notes = _score(threads, checked, kept_groups, kinds)
    result.ranking = rank_products(scored, query.category, kind_notes, placements(kinds))
    result.answer = write_answer(result.ranking, result.bodies, query.product_type, price_checks)
    return result


def _about_the_product(thread: Thread, product_type: str) -> bool:
    """Whether the thread's title or post names the product. Its comments don't count: they can mention it in passing."""
    return mentions_product(thread.title, product_type) or mentions_product(thread.body, product_type)


# --- Module 4: products and kinds ---

def _product_mentions(checked: dict[str, CheckResult]) -> list[ProductMention]:
    return [ProductMention(tid, m.comment_id, m.product, m.category, m.stance, m.product_type)
            for tid, res in checked.items() for m in res.kept]


def _kind_mentions(checked: dict[str, CheckResult]) -> list[KindMention]:
    return [KindMention(tid, n.comment_id, n.about, n.stance) for tid, res in checked.items() for n in res.kept_notes]


def _groups_to_rank(groups: list[ProductGroup], query: ParsedQuery, result: PipelineResult,
                    titles: dict[str, str]) -> list[ProductGroup]:
    """The product groups worth ranking for this request, each under the name to show; the others are named on the
    result. Every name is shown as a UK shopper knows it ("Sage", not "Breville": decision 12). `titles` is
    {thread id: title} for the threads read."""
    kept = []
    same_category = [g for g in groups if g.category == query.category]
    for group in same_category:  # the ranking only looks at the request's category anyway
        if group.loose:
            if _clear_brand(group, query, titles, same_category):
                kept.append(replace(group, name=brand_pick_name(uk_name(group.name), query.product_type)))
            else:
                result.left_out_loose.append(uk_name(group.name))
        elif _another_type(group, query):
            result.left_out_as_other_type.append(uk_name(group.name))
        else:
            kept.append(replace(group, name=uk_name(group.name)))
    return kept


def _clear_brand(group: ProductGroup, query: ParsedQuery, titles: dict[str, str], groups: list[ProductGroup]) -> bool:
    """Whether a brand or line name clearly means the requested product in these threads (decision 9): it names
    something, none of its names says another type of product, more than BRAND_PICK_TITLE_SHARE of its mentions are
    in threads whose title names the requested product, and (BRAND_PICK_NEEDS_A_PRODUCT_OF_THE_TYPE) one of its own
    products named in the threads is of that type. "Lodge" in "Best cast iron skillet?" threads, next to "Lodge
    Blacklock skillet", is clear. `groups` are every product group of the request's category."""
    if not PIPELINE_BRAND_PICKS or not normalize_name(group.name) or _another_type(group, query):
        return False  # a name made of filler words only ("the one") names nothing
    in_titled = sum(mentions_product(titles.get(m.thread_id, ""), query.product_type) for m in group.mentions)
    if in_titled <= BRAND_PICK_TITLE_SHARE * len(group.mentions):
        return False
    return not BRAND_PICK_NEEDS_A_PRODUCT_OF_THE_TYPE or _has_a_product_of_the_type(group, query, groups)


def _has_a_product_of_the_type(brand: ProductGroup, query: ParsedQuery, groups: list[ProductGroup]) -> bool:
    """Whether a name of the brand, or of one of its products named in these threads (a name that holds the brand's,
    such as "Griswold skillet" for "Griswold"), names the requested type of product."""
    if any(mentions_product(name, query.product_type) for name in brand.names):
        return True
    aliases = known_aliases().get(brand.category, {})
    return any(
        mentions_product(name, query.product_type) and any(same_product(own, name, aliases) for own in brand.names)
        for other in groups if other is not brand for name in other.names
    )


def _another_type(group: ProductGroup, query: ParsedQuery) -> bool:
    """Whether the product is another type of product than the one requested.

    The AI's types decide when its mentions have them (instructions v6); when none has one (older extractions),
    its names do.
    """
    types = [m.product_type for m in group.mentions if m.product_type]
    if types:
        return _another_type_by_ai(types, query.product_type)
    return _another_type_by_name(group, query)


def _another_type_by_ai(types: list[str], requested: str) -> bool:
    """Whether the type most of a product's mentions give is another type than the one requested.

    - A tie for the most mentions keeps the product in: the AI isn't sure what it is.
    - The requested type itself: kept.
    - Another of module 1's product types (engine.query.PRODUCT_TYPES): left out, even when it shares a word with
      the requested one ("stovetop kettle" for an electric kettle request).
    - A type in the AI's own words: left out, unless it names the requested type the way module 2 recognises it
      (engine.sources.mentions_product): "gooseneck kettle" names an electric kettle, "toaster" doesn't.
    """
    counts = Counter(t.strip().lower() for t in types).most_common()
    if len(counts) > 1 and counts[0][1] == counts[1][1]:
        return False
    majority = counts[0][0]
    if majority == requested:
        return False
    if majority in {p.name for p in PRODUCT_TYPES}:
        return True
    return not mentions_product(majority, requested)


def _another_type_by_name(group: ProductGroup, query: ParsedQuery) -> bool:
    """Whether the product's names say it is another type of product than the one requested, and none says it isn't."""
    names = list(group.names)
    if any(mentions_product(name, query.product_type) for name in names):
        return False
    others = [p.name for p in PRODUCT_TYPES if p.category == query.category and p.name != query.product_type]
    return any(mentions_product(name, other) for name in names for other in others)


# --- Budgets (decision 11) ---

def _within_budget(groups: list[ProductGroup], query: ParsedQuery, prices: list[Price], today: date,
                   result: PipelineResult) -> tuple[list[ProductGroup], dict[str, PriceCheck]]:
    """Each product's price, checked against the request's budget: the groups kept, and {product key: PriceCheck}.

    A known, recent price above the budget's max leaves the product out (named on the result). A brand pick has no
    single price, so it is never priced and never left out for its price.
    """
    budget = query.constraints.budget
    if budget is not None and budget.max is not None and budget.currency is None:
        # "under 100": module 1 doesn't guess a currency, but the shoppers are in the UK (Noemi, 9 Oct 2026).
        budget = budget.model_copy(update={"currency": BUDGET_DEFAULT_CURRENCY})
        query = query.model_copy(update={"constraints": query.constraints.model_copy(update={"budget": budget})})
    currency = budget.currency if budget else None
    kept, checks = [], {}
    for group in groups:
        price = None if group.loose else find_price(group.name, group.category, prices, currency)
        check = check_price(price, budget, today)
        if check.status == "over":
            result.left_out_over_budget.append(group.name)
        else:
            kept.append(group)
            checks[group.key] = check
    return kept, checks


# --- Module 5: a weight for every mention and note ---

def _score(threads: list[Thread], checked: dict[str, CheckResult], groups: list[ProductGroup], kinds) -> tuple[list[ScoredMention], list[KindNote]]:
    by_id = {t.id: t for t in threads}
    group_by_mention = group_of(groups)
    kind_groups = kinds_of(kinds)
    scored, notes = [], []
    for tid, res in checked.items():
        thread = by_id[tid]
        comments = {c.id: c for c in thread.comments}
        voices = {}
        for m in res.kept:
            group = group_by_mention.get(ProductMention(tid, m.comment_id, m.product, m.category, m.stance))
            if group is None:
                continue  # left out above: another category, another type, a loose name, or over budget
            comment = comments[m.comment_id]
            voice = voices.setdefault(m.comment_id, score_voice(comment, thread, res.kept_agreements))
            others = [o.product for o in res.kept if o.comment_id == m.comment_id and o.product != m.product]
            evidence = score_evidence(comment, m.product, m.stance, others)
            scored.append(ScoredMention(
                product_key=group.key, product_name=group.name, category=group.category, thread_id=tid,
                comment_id=m.comment_id, comment_url=str(comment.url), stance=m.stance,
                weight=mention_weight(voice, evidence, m.stance), voice=voice.level, evidence=evidence.level,
                quote=m.quote, badges=badges(voice, evidence), author=_writer(comment),
            ))
        for n in res.kept_notes:
            comment = comments[n.comment_id]
            voice = voices.setdefault(n.comment_id, score_voice(comment, thread, res.kept_agreements))
            evidence = score_evidence(comment, n.about, n.stance)
            for kind in kind_groups.get(KindMention(tid, n.comment_id, n.about, n.stance), []):
                notes.append(KindNote(
                    kind_key=kind.key, kind_name=kind.name, thread_id=tid, comment_id=n.comment_id,
                    comment_url=str(comment.url), stance=n.stance, weight=mention_weight(voice, evidence, n.stance),
                    voice=voice.level, quote=n.quote, badges=badges(voice, evidence), author=_writer(comment),
                ))
    return scored, notes


def _commented(result: CheckResult) -> set[str]:
    """The comments whose writers need a profile: those with kept product mentions or kept notes (review, 9 Oct 2026)."""
    return {m.comment_id for m in result.kept} | {n.comment_id for n in result.kept_notes}


def _writer(comment: Comment) -> str | None:
    """The writer's name, lowercased, so the ranking counts each writer once; None for a deleted account."""
    return comment.author.name.lower() if comment.author is not None else None


def cached_profiles() -> StoredProfiles:
    """Writers' standing from the library's profile store, then the Arctic Shift cache; never a call. What the command
    line, the demo and the evaluation use."""
    from engine.arctic_shift import ArcticShiftClient

    return StoredProfiles(ProfileStore(DEFAULT_LIBRARY_DIR / "profiles.json"), ArcticShiftClient())


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    result = answer_request(" ".join(argv), profiles=cached_profiles())
    print(result.text())
    if result.answer is not None:
        print(f"\n(threads used: {', '.join(result.threads_used)}; left out as another type: "
              f"{len(result.left_out_as_other_type)}; brand or line names left out: {len(result.left_out_loose)}; "
              f"threads not extracted yet: {len(result.not_extracted)}; notes naming no kind: "
              f"{len(result.notes_without_kind)}; over budget: {len(result.left_out_over_budget)})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
