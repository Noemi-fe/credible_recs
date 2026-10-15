"""Module 6, ranking: turns scored mentions into ranked products, applies the minimum-evidence rule and flags disagreement.

What comes in (made by modules 4 and 5, put together by the pipeline):
- ScoredMention: one product mentioned in one comment, with module 4's product key and display name, and
  module 5's voice level (the writer), evidence level (how well they know the product) and weight;
- KindNote: one "what to look for" note about a kind of product ("get a Japanese gyuto"), with its weight;
- placements: which products belong to which kind, {kind key: [product keys]} (module 4).

How a product is scored (the brief's "Sum" rule):
    score = the sum of its mentions' weights + the kind bonus (if any)
A weight is voice value x evidence value x stance value (module 5), so a recommendation adds, a warning
subtracts and a neutral mention adds nothing. Only the request's category is ranked. One writer counts once
per product: if they mention it twice, in one comment or in several comments or threads, only their strongest
mention counts, so no one votes twice. The same goes for kinds. A writer whose account was deleted can't be
recognised, so each of their comments counts once (review fixes, 9 Oct 2026; before, it was once per comment).

A credible mention is a recommend or warn from a voice that isn't low, by someone who has used the product
(config.CREDIBLE_VOICES and CREDIBLE_EVIDENCE). Low voices and hearsay still move the score a little, but
never count toward the rules below.

Two things the pipeline settles before the ranking (9 Oct 2026), so they arrive here in the mentions:
- Needs: a mention whose comment talks about what the request asks for ("sensitive skin", "a beginner";
  engine/needs.py) carries those needs, and its weight is already multiplied by config.NEED_MATCH_BOOST (off, 1.0, for now),
  for a recommendation or a warning alike. The breakdown counts the credible mentions that fit the request's needs.
  The rules below don't change: they count credible mentions, not weights.
- Writers who contradict themselves (Noemi's rule; engine/contradictions.py): every mention by a writer who
  recommends a product and warns against it without saying what changed arrives as a low voice, so it is never
  credible.

The rules, in plain words:
- Minimum evidence: a product can be a pick only with at least 3 credible recommendations from at least 2
  different threads, and a score above zero. The kind bonus never helps a product pass this rule.
- Skip-these list: at least 2 credible warnings, and more credible warnings than credible recommendations.
  A product on it is never a pick.
- Disagreement flag: at least one credible recommendation and at least 2 credible warnings. Flagged, not hidden.
- Also worth a look (Noemi's decision 2 of 13 Oct 2026): a product with exactly 2 credible recommendations
  (config.WORTH_A_LOOK_CREDIBLE), from at least 2 different threads (WORTH_A_LOOK_MIN_THREADS), a score above zero and
  not on the skip-these list is shown apart from the picks, as less supported. It is never a pick, and, as for picks,
  the kind bonus never helps it in.
- Upvotes (Noemi, 14 Oct 2026: "if we have few credible mentions, a highly upvoted comment (10+) counts more"), only
  while config.UPVOTE_COUNTS_MORE is on (on since her decision of 14 Oct 2026, variant D): a credible recommendation
  whose comment has at least UPVOTE_MIN_SCORE upvotes counts as two toward the two rules above (counts_twice; the
  variants are config's). Only a credible recommendation: upvotes never make a comment credible, and a warning counts
  once. One comment counts at most
  twice, and the threads are still counted as threads, so the extra count never stands in for the second thread: in
  practice it lifts a product with 2 credible recommendations from 2 threads (one of them with the upvotes) to the
  picks. A writer counted once (the strongest of their mentions) is counted twice only by that mention's own comment.
  Everything else still counts writers: the score, the ties below, the skip-these list and the disagreement flag. A
  lifted product takes its place among the picks by its score, or with config.UPVOTE_ONLY_TO_FILL (variant D) only a
  place the products meeting the rule on their own leave empty (RankingResult.qualifying); one that doesn't make the
  picks stays under Also worth a look, so the rule never takes a product out of the answer.
- A comment that stands out in its thread (Noemi, 14 Oct 2026: "if a comment has a lot of upvotes compared to the size
  of the thread, i want it as a pick or worth a look"), only while config.STANDOUT_ON is on: a credible recommendation
  whose comment has at least STANDOUT_UPVOTES_PER_COMMENT upvotes for each comment of its thread, and at least
  STANDOUT_MIN_SCORE, in a thread of at least STANDOUT_MIN_THREAD_COMMENTS comments, naming at most
  STANDOUT_MAX_PRODUCTS products and talking about what the request asks for when it asks for anything besides the
  product (stands_out). A product short of the bar with such a comment, more credible recommendations than credible
  warnings, a score above zero and not on the skip-these list is Also worth a look even with that one credible voice;
  with a second credible writer (the comment counting as two, like the upvote rule's) it meets the bar even from one
  thread, while config.STANDOUT_FILLS_PICKS is on. Either way it only fills a place left empty, whatever the upvote
  rule's variant: after the products meeting the bar on their own (RankingResult.qualifying), and after the items with
  two credible recommendations across two threads (RankingResult.worth_a_look). The upvote rule comes first: a product
  it lifts is lifted as before. Everything else still counts writers.
- Products past the picks (Noemi's decision 4 of 15 Oct 2026): a product that meets the minimum-evidence rule on its
  own (not thanks to the upvote rule or a standing-out comment) but ranks below the top 3 is listed first under Also
  worth a look, best first (RankingResult.past_the_picks), labelled as meeting the bar (engine/answer.py). Until then it
  was shown nowhere, while products with two credible recommendations were shown there. The section keeps its size
  (config.WORTH_A_LOOK_SHOWN): these come first, then the items with two credible recommendations across two threads,
  then those a standing-out comment puts there. One the upvote rule or a standing-out comment lifts to the bar isn't one
  of them: it only fills places left empty, as above.
- Kind support: each kind's support is the sum of the weights of its credible notes. If the best-supported kind
  has at least 2 credible recommending notes and at least twice the support of the next kind, its products
  get a bonus (config.KIND_BONUS, shown in the score breakdown).
- Confirmed first under a must-have (Noemi's decision 1 of 15 Oct 2026): when the request asks for something a
  product's facts can settle (engine.product_facts.hard_requirements: SPF for a lip balm, PFAS-free or non-stick for a
  pan, sulfate-free for a shampoo...), the pipeline says how many of those must-haves each product's facts and name
  leave unconfirmed (`unconfirmed`), and fewer rank first, whatever the score: a lip balm whose name says SPF 25 before
  one sold with and without SPF. The rest of the order is as below. The rules above don't change, so confirmation never
  makes a pick: it orders the products that meet the bar, those listed under Also worth a look, and in each group the
  confirmed come first. Those the upvote rule or a standing-out comment lift still come after every product meeting
  the bar on its own (RankingResult.qualifying), confirmed or not: they only fill places left empty. Until then (the
  rules of 10 and 11 Oct 2026) a product we couldn't confirm kept its place, with a note; the note stays.
- Ties, decided the same way every time: higher score first (differences under one millionth are rounding
  noise, so they count as a tie), then more credible recommendations, then more threads with one, then more
  high voices recommending it, then the name in alphabetical order.
- Thin evidence: when no product meets the minimum-evidence rule, `thin_evidence` is True; when fewer than 3
  do, `needs_more_threads` is True. Either is the pipeline's signal to fetch more threads (CLAUDE.md open item).
"""

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

from engine import config  # the upvote rule's settings, read when ranking (14 Oct 2026), so they can be switched
from engine.config import (
    CREDIBLE_EVIDENCE,
    CREDIBLE_VOICES,
    DISAGREEMENT_MIN_CREDIBLE_WARNINGS,
    EVIDENCE_LEVELS,
    KIND_BONUS,
    KIND_LEAD_RATIO,
    KIND_MIN_CREDIBLE_NOTES,
    MENTION_CATEGORIES,
    MIN_CREDIBLE_MENTIONS,
    MIN_THREADS,
    PICKS_SHOWN,
    SKIP_MIN_CREDIBLE_WARNINGS,
    STANCE_VALUE,
    THREAD_CATEGORIES,
    VOICE_LEVELS,
    WORTH_A_LOOK_CREDIBLE,
    WORTH_A_LOOK_MIN_THREADS,
)

DECIMALS = 6  # scores are rounded to this many decimals, so tiny rounding noise can't break a tie


# --- What comes in ---

@dataclass(frozen=True)
class ScoredMention:
    """One product mentioned in one comment, with its credibility. Built by the pipeline from modules 3, 4 and 5."""

    product_key: str  # module 4's id for the product; every name of one product shares it
    product_name: str  # the name to show, from module 4
    category: str  # skincare, kitchen or other
    thread_id: str
    comment_id: str  # used to find the comment again and re-check the quote at answer time
    comment_url: str  # the link shown next to the quote
    stance: str  # recommend, warn or neutral
    # module 5: voice value x evidence value x stance value; negative for warn, 0 for neutral. Already multiplied by
    # config.NEED_MATCH_BOOST when the comment talks about the request's needs (`needs` below).
    weight: float
    voice: str  # module 5: high, medium or low (the writer); low for a writer who contradicts themselves
    evidence: str  # module 5: long-term use, short-term use or no first-hand use (this product)
    quote: str  # the supporting quote, checked at extraction; checked again before it is shown
    badges: tuple[str, ...] = ()  # "why this voice counts", in words: "3 years of use", "expert flair"
    author: str | None = None  # the writer's name, lowercased, so one writer counts once; None for a deleted account
    # The request's needs its comment talks about ("sensitive", "beginner", "pour-over"; engine/needs.py), in the
    # request's order; empty when it talks about none. Since 15 Oct 2026 only the needs a comment can talk about
    # (engine.needs.judged_needs): never the ingredient, size or checked requirement the request names.
    needs: tuple[str, ...] = ()
    # The product's name as this comment's writer wrote it (module 3: "my Stagg"), which names the product in a quote
    # as well as the name shown does (engine/answer.py; 10 Oct 2026). Empty when not known.
    written_as: str = ""
    # Its comment's upvotes beside its thread's (module 5, engine.credibility.thread_upvotes; 14 Oct 2026), for Noemi's
    # upvote rule (counts_twice): its score (upvotes minus downvotes), how many of its thread's comments were readable
    # when it was read (itself included), and the share of the others it scored higher than. None when not known.
    upvotes: int | None = None
    thread_comments: int | None = None
    share_beaten: float | None = None
    # For a comment that stands out in its thread (stands_out; 14 Oct 2026): how many products its comment names, this
    # one included (module 3's kept mentions), and whether the request asks for anything besides the product (its needs,
    # engine/needs.py), so that `needs` empty means the comment doesn't talk about what was asked.
    products_named: int = 1
    needs_asked: bool = False
    # Its comment's other products of another type, with the same stance (module 3's mentions and types; 15 Oct 2026),
    # as written: a quote naming one of them is about another product (engine/answer.py: "my Lodge carbon steel skillet
    # has replaced my cast iron" for a cast iron pick).
    others_of_another_type: tuple[str, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "badges", tuple(self.badges))  # a list given by the pipeline is fine too
        object.__setattr__(self, "needs", tuple(self.needs))
        object.__setattr__(self, "others_of_another_type", tuple(self.others_of_another_type))
        _check_choice("category", self.category, MENTION_CATEGORIES)
        _check_choice("voice", self.voice, VOICE_LEVELS)
        _check_choice("evidence", self.evidence, EVIDENCE_LEVELS)
        _check_stance_and_weight(self.stance, self.weight)


@dataclass(frozen=True)
class KindNote:
    """Advice about a kind of product ("get a Japanese gyuto", "avoid non-stick"), from one comment."""

    kind_key: str  # module 4's id for the kind
    kind_name: str  # the name to show: "Japanese gyuto"
    thread_id: str
    comment_id: str
    comment_url: str
    stance: str  # recommend (look for it), warn (avoid it) or neutral
    weight: float  # module 5's weight for the note; negative for warn, 0 for neutral
    voice: str  # the writer's voice level (module 5)
    quote: str
    badges: tuple[str, ...] = ()
    author: str | None = None  # the writer's name, lowercased; None for a deleted account

    def __post_init__(self):
        object.__setattr__(self, "badges", tuple(self.badges))
        _check_choice("voice", self.voice, VOICE_LEVELS)
        _check_stance_and_weight(self.stance, self.weight)


def _check_choice(what: str, value: str, allowed: tuple[str, ...]) -> None:
    if value not in allowed:
        raise ValueError(f"unknown {what} {value!r}; choose from: {', '.join(allowed)}")


def _check_stance_and_weight(stance: str, weight: float) -> None:
    """A weight's sign must match its stance: a mistake here would turn a warning into praise."""
    _check_choice("stance", stance, tuple(STANCE_VALUE))
    fits = {"recommend": weight >= 0, "warn": weight <= 0, "neutral": weight == 0}[stance]
    if not fits:
        raise ValueError(f"weight {weight} doesn't fit stance {stance!r}: recommend >= 0, warn <= 0, neutral = 0")


def is_credible(item: ScoredMention | KindNote) -> bool:
    """Whether a mention (or note) counts toward the rules: it takes a side, from a voice that isn't low, with first-hand use.

    Notes have no evidence level, so for them only the stance and the voice are checked.
    """
    if item.stance == "neutral" or item.voice not in CREDIBLE_VOICES:
        return False
    if isinstance(item, ScoredMention) and item.evidence not in CREDIBLE_EVIDENCE:
        return False
    return True


def counts_twice(mention: ScoredMention, rule: bool | None = None) -> bool:
    """Whether a mention's upvotes let it count as two credible recommendations toward the picks bar (Noemi, 14 Oct
    2026), whatever the product: the rule is on (`rule`; None follows config.UPVOTE_COUNTS_MORE), the mention is a
    credible recommendation, and its comment has at least UPVOTE_MIN_SCORE upvotes; with UPVOTE_TOP_OF_BIG_THREAD
    (variant C), its thread also had at least UPVOTE_THREAD_MIN_COMMENTS readable comments, of which it scored higher
    than UPVOTE_THREAD_SHARE_BEATEN. Which of a product's such mentions do count twice is _counted_twice's."""
    on = config.UPVOTE_COUNTS_MORE if rule is None else rule
    if not on or mention.stance != "recommend" or not is_credible(mention):
        return False
    if mention.upvotes is None or mention.upvotes < config.UPVOTE_MIN_SCORE:
        return False
    if config.UPVOTE_TOP_OF_BIG_THREAD:
        return (mention.thread_comments is not None and mention.share_beaten is not None
                and mention.thread_comments >= config.UPVOTE_THREAD_MIN_COMMENTS
                and mention.share_beaten >= config.UPVOTE_THREAD_SHARE_BEATEN)
    return True


def lifted(product: "ProductScore") -> bool:
    """Whether a product meets the minimum-evidence rule only thanks to Noemi's upvote rule: fewer credible
    recommendations than the bar, made up by some counted twice for their upvotes (14 Oct 2026)."""
    return product.qualifies and bool(product.counted_twice) and (
        product.breakdown.credible_recommends < MIN_CREDIBLE_MENTIONS)


def on_its_own(product: "ProductScore") -> bool:
    """Whether a product meets the minimum-evidence rule on its own: neither the upvote rule (lifted) nor a comment
    standing out in its thread (by_standout) is why it does. Such a product ranked below the top 3 heads Also worth a look
    (Noemi's decision 4 of 15 Oct 2026; RankingResult.past_the_picks)."""
    return product.qualifies and not lifted(product) and not product.by_standout


def stands_out(mention: ScoredMention, rule: bool | None = None) -> bool:
    """Whether a mention's comment stands out in its thread (Noemi, 14 Oct 2026: "if a comment has a lot of upvotes
    compared to the size of the thread, i want it as a pick or worth a look"): the rule is on (`rule`; None follows
    config.STANDOUT_ON), the mention is a credible recommendation, its comment has at least STANDOUT_MIN_SCORE upvotes
    and at least STANDOUT_UPVOTES_PER_COMMENT for each readable comment of its thread, a thread of at least
    STANDOUT_MIN_THREAD_COMMENTS, it names at most STANDOUT_MAX_PRODUCTS products, and, when the request asks for
    anything besides the product, it talks about that. Upvotes never make a comment credible: a low voice, one without
    first-hand use or a warning never stands out."""
    on = config.STANDOUT_ON if rule is None else rule
    if not on or mention.stance != "recommend" or not is_credible(mention):
        return False
    upvotes, comments = mention.upvotes, mention.thread_comments
    if upvotes is None or comments is None or upvotes < config.STANDOUT_MIN_SCORE:
        return False
    if comments < config.STANDOUT_MIN_THREAD_COMMENTS or mention.products_named > config.STANDOUT_MAX_PRODUCTS:
        return False
    if mention.needs_asked and not mention.needs:
        return False
    return upvotes / comments >= config.STANDOUT_UPVOTES_PER_COMMENT


def _counted_twice(credible_recommends: list[ScoredMention], rule: bool | None = None) -> tuple[ScoredMention, ...]:
    """A product's credible recommendations that count twice toward the picks bar, the most upvoted first: every one
    counts_twice allows (variant A), or with UPVOTE_ONLY_WHEN_SHORT (variants B and C) only for a product with fewer
    than MIN_CREDIBLE_MENTIONS credible recommendations, and only as many as it is short of the bar, so the rule lifts
    a product with few credible mentions and never inflates one that meets the bar on its own."""
    upvoted = sorted((m for m in credible_recommends if counts_twice(m, rule)), key=lambda m: (-m.upvotes, m.comment_id))
    if config.UPVOTE_ONLY_WHEN_SHORT:
        upvoted = upvoted[:max(0, MIN_CREDIBLE_MENTIONS - len(credible_recommends))]
    return tuple(upvoted)


# --- What comes out ---

@dataclass
class ScoreBreakdown:
    """Every number behind a product's score, for the interface's expandable breakdown."""

    mention_points: float  # the sum of the mentions' weights
    kind_bonus: float  # added when the product belongs to the leading kind, else 0
    kind: str | None  # the kind the product belongs to (the leading one if it is in it), or None
    kind_support: float | None  # that kind's support, or None
    recommends: int
    credible_recommends: int
    warnings: int
    credible_warnings: int
    neutral: int  # neutral mentions never count; shown so the numbers add up
    recommend_voices: dict[str, int]  # how many high / medium / low voices recommend it
    recommend_evidence: dict[str, int]  # and with what evidence
    warn_voices: dict[str, int]
    warn_evidence: dict[str, int]
    threads: int  # threads mentioning it at all
    credible_threads: int  # threads with at least one credible recommendation
    # Credible mentions whose comment talks about the request's needs (9 Oct 2026); each weighs NEED_MATCH_BOOST times.
    credible_recommends_fitting_need: int = 0
    credible_warnings_fitting_need: int = 0


@dataclass
class ProductScore:
    key: str
    name: str
    score: float  # mention points + kind bonus, rounded to 6 decimals: what the ranking sorts by
    breakdown: ScoreBreakdown
    mentions: tuple[ScoredMention, ...]  # the mentions counted (one per writer), for quotes and downsides
    qualifies: bool  # meets the minimum-evidence rule and can be a pick
    shortfall: str | None  # why it can't be a pick, in words; None when it qualifies
    on_skip_list: bool
    disputed: bool  # the disagreement flag
    # Shown under "Also worth a look": exactly WORTH_A_LOOK_CREDIBLE credible recommendations, from at least
    # WORTH_A_LOOK_MIN_THREADS threads, mention points above zero, not on the skip list (Noemi, 13 Oct 2026).
    worth_a_look: bool = False
    # The credible recommendations counted twice toward the picks bar for their upvotes, the most upvoted first (Noemi's
    # upvote rule, 14 Oct 2026; _counted_twice): empty while the rule is off. The bar counts the credible recommendations
    # and these once more. The answer says which and for how many upvotes (the reason, and the meter's "twice"); the
    # score breakdown doesn't hold them, so an answer's JSON is as before while the rule is off.
    counted_twice: tuple[ScoredMention, ...] = ()
    # Its credible recommendations whose comment stands out in its thread (stands_out; 14 Oct 2026), most upvoted first;
    # empty while that rule is off. `by_standout`: it is a pick or Also worth a look only thanks to them (it has fewer
    # credible recommendations than the bar, or all from one thread, and the upvote rule doesn't lift it). The answer
    # then says which comment stands out and by how much; like counted_twice, neither is in the score breakdown.
    standouts: tuple[ScoredMention, ...] = ()
    by_standout: bool = False
    # How many of the request's must-haves its facts and name leave unconfirmed (Noemi's decision 1 of 15 Oct 2026):
    # fewer rank first. 0 for a product they confirm, and for every product of a request without a must-have. Like
    # counted_twice it isn't in the score breakdown: the answer says it in the product's note ("we couldn't
    # confirm...").
    unconfirmed: int = 0

    @property
    def credible_recommendations(self) -> list[ScoredMention]:
        return [m for m in self.mentions if m.stance == "recommend" and is_credible(m)]

    @property
    def credible_warnings(self) -> list[ScoredMention]:
        return [m for m in self.mentions if m.stance == "warn" and is_credible(m)]


@dataclass
class KindSupport:
    key: str
    name: str
    support: float  # the sum of its credible notes' weights: recommendations add, warnings subtract
    credible_notes: int  # credible notes recommending it


@dataclass
class RankingResult:
    category: str
    products: list[ProductScore]  # every product in the category, best first
    kinds: list[KindSupport] = field(default_factory=list)  # best supported first
    leading_kind: KindSupport | None = None  # the kind whose products get the bonus, if one leads by far
    kind_notes: list[KindNote] = field(default_factory=list)  # one per writer and kind, for "what to look for"
    # Noemi's upvote rule with config.UPVOTE_ONLY_TO_FILL (variant D, 14 Oct 2026): the products it lifts to the bar come
    # after every product that meets it on its own, so they only fill places the picks would leave empty.
    fill_only: bool = False

    @property
    def qualifying(self) -> list[ProductScore]:
        """Every product that meets the minimum-evidence rule, best first; with `fill_only`, those the upvote rule lifted
        to it after the others, and whatever the variant, those a comment standing out in its thread lifted (14 Oct
        2026): they only fill places the others leave empty."""
        found = [p for p in self.products if p.qualifies]
        later = [p.by_standout or (self.fill_only and lifted(p)) for p in found]
        return [p for p, late in zip(found, later) if not late] + [p for p, late in zip(found, later) if late]

    @property
    def picks(self) -> list[ProductScore]:
        """The top 3 (or fewer) qualifying products."""
        return self.qualifying[:PICKS_SHOWN]

    @property
    def past_the_picks(self) -> list[ProductScore]:
        """The products that meet the minimum-evidence rule on their own (on_its_own) but rank below the top 3, best
        first: listed first under "Also worth a look", labelled as meeting the bar (Noemi's decision 4 of 15 Oct 2026).
        One lifted to the bar by the upvote rule or a standing-out comment isn't one of them, whatever its place: it
        stays the item it was without those rules."""
        picks = {p.key for p in self.picks}
        return [p for p in self.products if on_its_own(p) and p.key not in picks]

    @property
    def worth_a_look(self) -> list[ProductScore]:
        """The products for "Also worth a look", best first: first those that meet the bar on their own but rank below
        the top 3 (past_the_picks, Noemi's decision 4 of 15 Oct 2026), then those with two credible recommendations
        across two threads, so less supported than a pick (her decision 2 of 13 Oct 2026), then those a comment
        standing out in its thread puts there (14 Oct 2026). Never a pick: a product the upvote rule or a standing-out
        comment lifts to the bar (14 Oct 2026) is one of them only when its place doesn't put it among the picks, so
        the rules never take a product out of the answer. Those shown thanks to a standing-out comment come after the
        others, so they only fill places left empty there too."""
        past = self.past_the_picks
        shown = {p.key for p in self.picks} | {p.key for p in past}
        found = [p for p in self.products if p.worth_a_look and p.key not in shown]
        return past + [p for p in found if not p.by_standout] + [p for p in found if p.by_standout]

    @property
    def skip_list(self) -> list[ProductScore]:
        """Products credible voices warn against, most credible warnings first."""
        skipped = [p for p in self.products if p.on_skip_list]
        return sorted(skipped, key=lambda p: (-p.breakdown.credible_warnings, p.score, p.name.casefold(), p.key))

    @property
    def best_candidate(self) -> ProductScore | None:
        """The highest-ranked product, qualifying or not: what fell short when evidence is thin."""
        return self.products[0] if self.products else None

    @property
    def thin_evidence(self) -> bool:
        """True when no product meets the minimum-evidence rule (3 credible recommendations across 2 threads)."""
        return not self.qualifying

    @property
    def needs_more_threads(self) -> bool:
        """True when fewer than 3 products meet the rule: the signal to fetch more threads before answering."""
        return len(self.qualifying) < PICKS_SHOWN


# --- Ranking ---

def rank_products(
    mentions: Iterable[ScoredMention],
    category: str,
    kind_notes: Iterable[KindNote] = (),
    placements: Mapping[str, Iterable[str]] | None = None,
    kind_bonus: float = KIND_BONUS,
    upvote_rule: bool | None = None,
    standout_rule: bool | None = None,
    unconfirmed: Mapping[str, int] | None = None,
) -> RankingResult:
    """Ranks the products of one category, best first, by the rules at the top of this file.

    `category` is the request's category (ParsedQuery.category); mentions of other categories are left out.
    `placements` says which products belong to which kind: {kind key: [product keys]}.
    `kind_bonus` is there so different values can be tried; leave it out to use config.KIND_BONUS.
    `upvote_rule`: whether Noemi's upvote rule applies (counts_twice); None follows config.UPVOTE_COUNTS_MORE.
    `standout_rule`: whether a comment standing out in its thread lifts its product (stands_out); None follows
    config.STANDOUT_ON.
    `unconfirmed`: {product key: how many of the request's must-haves its facts leave unconfirmed} (Noemi's decision 1
    of 15 Oct 2026): fewer rank first. None, or a product not in it, is 0.
    """
    _check_choice("category", category, THREAD_CATEGORIES)
    placements = {kind: set(products) for kind, products in (placements or {}).items()}
    in_category = [m for m in mentions if m.category == category]
    votes = _one_per_comment(in_category, lambda m: m.product_key)
    notes = _one_per_comment(kind_notes, lambda n: n.kind_key)
    kinds = kind_support(notes, placements)
    leader = leading_kind(kinds)
    by_product: dict[str, list[ScoredMention]] = defaultdict(list)
    for mention in votes:
        by_product[mention.product_key].append(mention)
    products = [
        _score_product(key, product_mentions, kinds, placements, leader, kind_bonus, upvote_rule, standout_rule)
        for key, product_mentions in by_product.items()
    ]
    for product in products:
        product.unconfirmed = max(0, (unconfirmed or {}).get(product.key, 0))
    products.sort(key=_rank_order)
    on = config.UPVOTE_COUNTS_MORE if upvote_rule is None else upvote_rule
    return RankingResult(category, products, kinds, leader, notes, fill_only=on and config.UPVOTE_ONLY_TO_FILL)


def _one_per_comment(items: Iterable, key_of: Callable) -> list:
    """Keeps one item per writer and product (or kind): the one with the largest weight either way. Order is kept.

    The writer is known by name across comments and threads; a deleted account (no name) counts per comment.
    """
    best: dict[tuple, object] = {}
    for item in items:
        writer = ("writer", item.author) if item.author is not None else ("comment", item.comment_id)
        slot = (key_of(item), writer)
        if slot not in best or abs(item.weight) > abs(best[slot].weight):
            best[slot] = item
    return list(best.values())


def _score_product(
    key: str,
    mentions: list[ScoredMention],
    kinds: list[KindSupport],
    placements: dict[str, set[str]],
    leader: KindSupport | None,
    kind_bonus: float,
    upvote_rule: bool | None = None,
    standout_rule: bool | None = None,
) -> ProductScore:
    recommends = [m for m in mentions if m.stance == "recommend"]
    warnings = [m for m in mentions if m.stance == "warn"]
    credible_recommends = [m for m in recommends if is_credible(m)]
    credible_warnings = [m for m in warnings if is_credible(m)]
    points = round(sum(m.weight for m in mentions), DECIMALS)
    kind = _kind_of(key, kinds, placements, leader)
    bonus = kind_bonus if leader is not None and kind is leader else 0.0
    credible_threads = len({m.thread_id for m in credible_recommends})
    # Toward the bar, a credible recommendation counted twice for its upvotes counts two (14 Oct 2026; off: none does).
    twice = _counted_twice(credible_recommends, upvote_rule)
    counted = len(credible_recommends) + len(twice)

    on_skip_list = (
        len(credible_warnings) >= SKIP_MIN_CREDIBLE_WARNINGS and len(credible_warnings) > len(credible_recommends)
    )
    disputed = bool(credible_recommends) and len(credible_warnings) >= DISAGREEMENT_MIN_CREDIBLE_WARNINGS
    shortfall = _shortfall(counted, credible_threads, points, on_skip_list, len(twice))
    # Also worth a look counts writers: a product the upvote rule lifts keeps its place there in case its score leaves it
    # out of the picks (RankingResult.worth_a_look).
    worth_a_look = (len(credible_recommends) == WORTH_A_LOOK_CREDIBLE and credible_threads >= WORTH_A_LOOK_MIN_THREADS
                    and points > 0 and not on_skip_list)
    # A comment standing out in its thread (14 Oct 2026), for a product still short of the bar: Also worth a look, and
    # with a second credible writer the bar, the comment counting as two and standing in for the second thread. Warnings
    # still count writers: more credible recommendations than credible warnings. What the upvote rule lifts stays its.
    standouts = tuple(sorted((m for m in credible_recommends if stands_out(m, standout_rule)),
                             key=lambda m: (-m.upvotes, m.comment_id)))
    by_standout = (bool(standouts) and shortfall is not None and points > 0 and not on_skip_list
                   and len(credible_warnings) < len(credible_recommends))
    if by_standout:
        worth_a_look = True  # kept in case it isn't a pick (RankingResult.worth_a_look), as for the upvote rule's
        if (config.STANDOUT_FILLS_PICKS and len(credible_recommends) >= 2
                and len(credible_recommends) + len(standouts) >= MIN_CREDIBLE_MENTIONS):
            shortfall, twice = None, ()  # it meets the bar thanks to the comment standing out, not to counting twice
    breakdown = ScoreBreakdown(
        mention_points=points,
        kind_bonus=bonus,
        kind=kind.name if kind else None,
        kind_support=kind.support if kind else None,
        recommends=len(recommends),
        credible_recommends=len(credible_recommends),
        warnings=len(warnings),
        credible_warnings=len(credible_warnings),
        neutral=sum(m.stance == "neutral" for m in mentions),
        recommend_voices=_count(recommends, "voice", VOICE_LEVELS),
        recommend_evidence=_count(recommends, "evidence", EVIDENCE_LEVELS),
        warn_voices=_count(warnings, "voice", VOICE_LEVELS),
        warn_evidence=_count(warnings, "evidence", EVIDENCE_LEVELS),
        threads=len({m.thread_id for m in mentions}),
        credible_threads=credible_threads,
        credible_recommends_fitting_need=sum(bool(m.needs) for m in credible_recommends),
        credible_warnings_fitting_need=sum(bool(m.needs) for m in credible_warnings),
    )
    return ProductScore(
        key=key,
        name=mentions[0].product_name,  # module 4 gives every mention of a product the same display name
        score=round(points + bonus, DECIMALS),
        breakdown=breakdown,
        mentions=tuple(mentions),
        qualifies=shortfall is None,
        shortfall=shortfall,
        on_skip_list=on_skip_list,
        disputed=disputed,
        worth_a_look=worth_a_look and (shortfall is not None or bool(twice) or by_standout),
        counted_twice=twice,
        standouts=standouts,
        by_standout=by_standout,
    )


def _shortfall(credible: int, threads: int, points: float, on_skip_list: bool, twice: int = 0) -> str | None:
    """Why a product can't be a pick, in words, or None when it meets the minimum-evidence rule. `credible` counts the
    credible recommendations as the bar does, `twice` of them counted twice for their upvotes (14 Oct 2026)."""
    reasons = []
    if on_skip_list:
        reasons.append("more credible warnings than recommendations (on the skip-these list)")
    if credible < MIN_CREDIBLE_MENTIONS:
        counted = f" ({twice} counted twice for {'its' if twice == 1 else 'their'} upvotes)" if twice else ""
        reasons.append(f"{credible} of {MIN_CREDIBLE_MENTIONS} credible recommendations{counted}")
    if threads < MIN_THREADS:
        reasons.append(f"credible recommendations in {threads} of {MIN_THREADS} threads")
    if points <= 0:
        reasons.append(f"warnings outweigh its support (score {points:.2f})")
    return "; ".join(reasons) or None


def _count(mentions: list[ScoredMention], level: str, levels: tuple[str, ...]) -> dict[str, int]:
    """How many mentions have each level, with every level listed (0 when none): {"high": 2, "medium": 1, "low": 0}."""
    counts = Counter(getattr(m, level) for m in mentions)
    return {name: counts[name] for name in levels}


def _rank_order(product: ProductScore) -> tuple:
    """The sort order: best first, ties broken as described at the top of this file. Fewer must-haves left unconfirmed
    come first (Noemi's decision 1 of 15 Oct 2026; 0 for every product of a request without one)."""
    b = product.breakdown
    return (
        product.unconfirmed,
        -product.score,
        -b.credible_recommends,
        -b.credible_threads,
        -sum(m.voice == "high" for m in product.credible_recommendations),
        product.name.casefold(),
        product.key,
    )


# --- Kind support ---

def kind_support(notes: Iterable[KindNote], placements: Mapping[str, Iterable[str]] | None = None) -> list[KindSupport]:
    """Each kind's credible support, best supported first. Kinds with products placed in them but no notes have 0."""
    names: dict[str, str] = {}
    support: dict[str, float] = defaultdict(float)
    recommending: Counter = Counter()
    for note in notes:
        names.setdefault(note.kind_key, note.kind_name)
        if is_credible(note):
            support[note.kind_key] += note.weight
            recommending[note.kind_key] += note.stance == "recommend"
    for key in placements or {}:
        names.setdefault(key, key)  # no note gives it a name, so its key stands in
    kinds = [KindSupport(key, name, round(support[key], DECIMALS), recommending[key]) for key, name in names.items()]
    return sorted(kinds, key=lambda k: (-k.support, k.name.casefold(), k.key))


def leading_kind(
    kinds: list[KindSupport], ratio: float = KIND_LEAD_RATIO, min_notes: int = KIND_MIN_CREDIBLE_NOTES
) -> KindSupport | None:
    """The kind with far more credible support than any other, or None when no kind stands out.

    `kinds` must be best supported first (as kind_support returns them). The leader needs `min_notes` credible
    recommending notes, support above zero, and at least `ratio` times the next kind's support (a next kind
    with no support, or negative support, counts as 0). Two kinds level at the top means no leader.
    """
    if not kinds:
        return None
    leader = kinds[0]
    runner_up = max(kinds[1].support, 0.0) if len(kinds) > 1 else 0.0
    far_ahead = leader.support > runner_up and leader.support >= ratio * runner_up
    if leader.credible_notes >= min_notes and leader.support > 0 and far_ahead:
        return leader
    return None


def _kind_of(
    product_key: str, kinds: list[KindSupport], placements: dict[str, set[str]], leader: KindSupport | None
) -> KindSupport | None:
    """The kind a product belongs to: the leading kind if it is in it, else its best-supported kind, else None."""
    mine = [kind for kind in kinds if product_key in placements.get(kind.key, ())]
    if leader is not None and leader in mine:
        return leader
    return mine[0] if mine else None
