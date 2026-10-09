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

The rules, in plain words:
- Minimum evidence: a product can be a pick only with at least 3 credible recommendations from at least 2
  different threads, and a score above zero. The kind bonus never helps a product pass this rule.
- Skip-these list: at least 2 credible warnings, and more credible warnings than credible recommendations.
  A product on it is never a pick.
- Disagreement flag: at least one credible recommendation and at least 2 credible warnings. Flagged, not hidden.
- Kind support: each kind's support is the sum of the weights of its credible notes. If the best-supported kind
  has at least 2 credible recommending notes and at least twice the support of the next kind, its products
  get a bonus (config.KIND_BONUS, shown in the score breakdown).
- Ties, decided the same way every time: higher score first (differences under one millionth are rounding
  noise, so they count as a tie), then more credible recommendations, then more threads with one, then more
  high voices recommending it, then the name in alphabetical order.
- Thin evidence: when no product meets the minimum-evidence rule, `thin_evidence` is True; when fewer than 3
  do, `needs_more_threads` is True. Either is the pipeline's signal to fetch more threads (CLAUDE.md open item).
"""

from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

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
    weight: float  # module 5: voice value x evidence value x stance value; negative for warn, 0 for neutral
    voice: str  # module 5: high, medium or low (the writer)
    evidence: str  # module 5: long-term use, short-term use or no first-hand use (this product)
    quote: str  # the supporting quote, checked at extraction; checked again before it is shown
    badges: tuple[str, ...] = ()  # "why this voice counts", in words: "3 years of use", "expert flair"
    author: str | None = None  # the writer's name, lowercased, so one writer counts once; None for a deleted account

    def __post_init__(self):
        object.__setattr__(self, "badges", tuple(self.badges))  # a list given by the pipeline is fine too
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

    @property
    def qualifying(self) -> list[ProductScore]:
        """Every product that meets the minimum-evidence rule, best first."""
        return [p for p in self.products if p.qualifies]

    @property
    def picks(self) -> list[ProductScore]:
        """The top 3 (or fewer) qualifying products."""
        return self.qualifying[:PICKS_SHOWN]

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
) -> RankingResult:
    """Ranks the products of one category, best first, by the rules at the top of this file.

    `category` is the request's category (ParsedQuery.category); mentions of other categories are left out.
    `placements` says which products belong to which kind: {kind key: [product keys]}.
    `kind_bonus` is there so different values can be tried; leave it out to use config.KIND_BONUS.
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
        _score_product(key, product_mentions, kinds, placements, leader, kind_bonus)
        for key, product_mentions in by_product.items()
    ]
    products.sort(key=_rank_order)
    return RankingResult(category, products, kinds, leader, notes)


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
) -> ProductScore:
    recommends = [m for m in mentions if m.stance == "recommend"]
    warnings = [m for m in mentions if m.stance == "warn"]
    credible_recommends = [m for m in recommends if is_credible(m)]
    credible_warnings = [m for m in warnings if is_credible(m)]
    points = round(sum(m.weight for m in mentions), DECIMALS)
    kind = _kind_of(key, kinds, placements, leader)
    bonus = kind_bonus if leader is not None and kind is leader else 0.0
    credible_threads = len({m.thread_id for m in credible_recommends})

    on_skip_list = (
        len(credible_warnings) >= SKIP_MIN_CREDIBLE_WARNINGS and len(credible_warnings) > len(credible_recommends)
    )
    disputed = bool(credible_recommends) and len(credible_warnings) >= DISAGREEMENT_MIN_CREDIBLE_WARNINGS
    shortfall = _shortfall(len(credible_recommends), credible_threads, points, on_skip_list)
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
    )


def _shortfall(credible: int, threads: int, points: float, on_skip_list: bool) -> str | None:
    """Why a product can't be a pick, in words, or None when it meets the minimum-evidence rule."""
    reasons = []
    if on_skip_list:
        reasons.append("more credible warnings than recommendations (on the skip-these list)")
    if credible < MIN_CREDIBLE_MENTIONS:
        reasons.append(f"{credible} of {MIN_CREDIBLE_MENTIONS} credible recommendations")
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
    """The sort order: best first, ties broken as described at the top of this file."""
    b = product.breakdown
    return (
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
