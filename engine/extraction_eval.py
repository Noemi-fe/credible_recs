"""Scores module 3 (mention extraction) against Noemi's labels of the gold set.

Four numbers, each "right out of total":
- precision: of the products the AI found, how many Noemi labelled too (the brief's target: at least 90%);
- recall: of the products Noemi labelled, how many the AI found (target: at least 80%);
- stance agreement: of the products both found, how many have the same stance (recommend, warn or neutral);
- category agreement: likewise for the category (skincare, kitchen or other).
The main score counts votes only (Noemi, 9 Oct 2026): recommend and warn, the mentions that change a product's
score. Neutral mentions add nothing to a score, so they are reported in a second line, with every mention.

Kinds of product (her rows with kind = yes, such as "sujihiki") aren't products: they are looked for among the
AI's notes in the same comment, by the same name comparison, and reported as how many of her kinds were found.
Only recall: she adds kind rows from 9 Oct 2026, so threads labelled before then may hold kinds she didn't label.

What counts:
- Only comments Noemi labelled: those with a row in voices.csv. Her rows in mentions.csv are the truth for them,
  and a voices row with no mention rows means "no product here", so anything the AI found there lowers precision.
  What the AI found in comments she hasn't read can't be checked, so it is left out.
- Only the AI's mentions that passed the quote checks (engine.extract.check_extraction): the rest are already
  dropped and never used.
- A thread Noemi labelled but the AI hasn't extracted yet is skipped and listed as not extracted, so its labels
  don't count as misses. A thread she hasn't labelled is neither scored nor listed: gold threads are labelled
  before the AI reads them, so its answers can't sway her labels.

Pairing her products with the AI's, comment by comment: names are compared with
engine.match_products.same_product, so "CeraVe SA" and "CeraVe Renewing SA Cleanser" are one product. Each of her
products is paired with at most one of the AI's, and the other way round, so the AI listing a product twice under
two names counts once. Among the possible pairings the one with the most pairs is taken, and exact names are tried
first, so a loose fit doesn't take the place of an exact one.

The misses are listed for reading: the comment id, what went wrong and the product name, never a quote or any
comment text.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import NamedTuple

from engine.extract import CheckResult, ExtractedMention, ExtractedNote
from engine.gold import GoldSet
from engine.match_products import normalize_name, same_product
from engine.models import MentionLabel

MAX_MISSES_SHOWN = 15

MISSED = "missed by the AI"
NOT_LABELLED = "not in Noemi's labels"


class Miss(NamedTuple):
    """One thing to look at: a product the AI missed, one it found that Noemi didn't, or a stance they read differently."""

    comment_id: str
    kind: str  # MISSED, NOT_LABELLED, or "stance differs: hers recommend, AI warn"
    product: str  # her name for it, or the AI's when she has none


@dataclass
class ExtractionScore:
    matched: int = 0  # pairs of her product and the AI's naming the same product
    ai_total: int = 0  # the AI's mentions in the comments she labelled
    gold_total: int = 0  # her mentions in the comments the AI read
    same_stance: int = 0  # matched pairs with the same stance
    same_category: int = 0  # matched pairs with the same category
    threads: int = 0  # threads scored: labelled by her and extracted by the AI
    labelled_comments: int = 0  # comments she labelled in those threads, with or without a product
    misses: list[Miss] = field(default_factory=list)
    not_extracted: list[str] = field(default_factory=list)  # thread ids she labelled that the AI hasn't read yet
    kinds_found: int = 0  # her kinds of product found among the AI's notes in the same comment
    kinds_total: int = 0  # her kinds of product in the comments the AI read

    @property
    def precision(self) -> float | None:
        return _ratio(self.matched, self.ai_total)

    @property
    def recall(self) -> float | None:
        return _ratio(self.matched, self.gold_total)

    @property
    def stance_agreement(self) -> float | None:
        return _ratio(self.same_stance, self.matched)

    @property
    def category_agreement(self) -> float | None:
        return _ratio(self.same_category, self.matched)


def score_extraction(gold: GoldSet, checked: dict[str, CheckResult], votes_only: bool = False) -> ExtractionScore:
    """Compares the AI's checked extractions ({thread id: CheckResult}, as engine.extract.load_checked returns them)
    with Noemi's labels, in the gold set's thread and comment order. `votes_only` leaves neutral mentions out of
    the products on both sides."""
    labelled: dict[str, set[str]] = defaultdict(set)  # thread id -> the comment ids she labelled
    for voice in gold.voices:
        labelled[voice.thread_id].add(voice.comment_id)
    hers: dict[str, list[MentionLabel]] = defaultdict(list)
    her_kinds: dict[str, list[MentionLabel]] = defaultdict(list)
    for label in gold.mentions:
        if label.kind:
            her_kinds[label.comment_id].append(label)
        elif not (votes_only and label.stance == "neutral"):
            hers[label.comment_id].append(label)

    score = ExtractionScore()
    for thread in gold.threads:
        if not labelled[thread.id]:
            continue  # not labelled yet: nothing to check the AI against
        if thread.id not in checked:
            score.not_extracted.append(thread.id)
            continue
        score.threads += 1
        theirs: dict[str, list[ExtractedMention]] = defaultdict(list)
        for mention in checked[thread.id].kept:
            if not (votes_only and mention.stance == "neutral"):
                theirs[mention.comment_id].append(mention)
        notes: dict[str, list[ExtractedNote]] = defaultdict(list)
        for note in checked[thread.id].kept_notes:
            notes[note.comment_id].append(note)
        for comment in thread.comments:
            if comment.id in labelled[thread.id]:
                score.labelled_comments += 1
                _score_comment(score, comment.id, hers[comment.id], theirs[comment.id])
                score.kinds_total += len(her_kinds[comment.id])
                score.kinds_found += len(_pair_names([k.product for k in her_kinds[comment.id]], [n.about for n in notes[comment.id]]))
    return score


def _score_comment(score: ExtractionScore, comment_id: str, hers: list[MentionLabel], theirs: list[ExtractedMention]) -> None:
    """Adds one labelled comment's counts and misses to the score."""
    pairs = _pair_up(hers, theirs)
    score.gold_total += len(hers)
    score.ai_total += len(theirs)
    score.matched += len(pairs)
    for h, t in pairs:
        score.same_category += hers[h].category == theirs[t].category
        if hers[h].stance == theirs[t].stance:
            score.same_stance += 1
        else:
            kind = f"stance differs: hers {hers[h].stance}, AI {theirs[t].stance}"
            score.misses.append(Miss(comment_id, kind, hers[h].product))
    paired_hers = {h for h, _ in pairs}
    paired_theirs = {t for _, t in pairs}
    score.misses += [Miss(comment_id, MISSED, label.product) for h, label in enumerate(hers) if h not in paired_hers]
    score.misses += [Miss(comment_id, NOT_LABELLED, m.product) for t, m in enumerate(theirs) if t not in paired_theirs]


def _pair_up(hers: list[MentionLabel], theirs: list[ExtractedMention]) -> list[tuple[int, int]]:
    """Pairs her mentions with the AI's (as list positions) so that as many as possible are paired, each at most once.

    Her mentions are placed one at a time. When the only AI mention that fits one is already taken, the mention
    that took it is moved to another AI mention that fits it, if there is one free (or one that can be freed the
    same way). This finds the most pairs possible, where taking the first fit could leave a mention unpaired.
    """
    return _pair_names([label.product for label in hers], [mention.product for mention in theirs])


def _pair_names(hers: list[str], theirs: list[str]) -> list[tuple[int, int]]:
    """_pair_up on plain names, also used to pair her kinds of product with the AI's notes."""
    fits = []  # for each of her names, the AI names meaning the same product: exact names first
    for name in hers:
        candidates = [t for t, other in enumerate(theirs) if same_product(name, other)]
        candidates.sort(key=lambda t: normalize_name(theirs[t]) != normalize_name(name))
        fits.append(candidates)

    partner: dict[int, int] = {}  # AI mention -> her mention it is paired with

    def place(h: int, tried: set[int]) -> bool:
        for t in fits[h]:
            if t in tried:
                continue
            tried.add(t)
            if t not in partner or place(partner[t], tried):
                partner[t] = h
                return True
        return False

    for h in range(len(hers)):
        place(h, set())
    return sorted((h, t) for t, h in partner.items())


# --- The report ---

def report_lines(score: ExtractionScore, votes: ExtractionScore | None = None) -> list[str]:
    """The scores, then up to MAX_MISSES_SHOWN misses, then the labelled threads not extracted yet.

    With `votes` (the same scoring with votes_only=True), the first line is the votes score, then every mention,
    then the kinds of product.
    """
    every = (
        f"precision {_share(score.matched, score.ai_total)}, recall {_share(score.matched, score.gold_total)}, "
        f"stance agreement {_share(score.same_stance, score.matched)}, "
        f"category agreement {_share(score.same_category, score.matched)}, "
        f"over {_count(score.threads, 'thread')}, {_count(score.labelled_comments, 'labelled comment')}"
    )
    if votes is None:
        lines = [every]
    else:
        lines = [
            f"votes (recommend or warn): precision {_share(votes.matched, votes.ai_total)}, "
            f"recall {_share(votes.matched, votes.gold_total)}",
            f"every mention, neutral included: {every}",
            f"kinds of product: {_share(score.kinds_found, score.kinds_total, 'of Noemi\'s kinds')} found among the AI's notes",
        ]
    lines += [f"  {miss.comment_id}  {miss.kind}: {miss.product}" for miss in score.misses[:MAX_MISSES_SHOWN]]
    if len(score.misses) > MAX_MISSES_SHOWN:
        lines.append(f"  ... and {len(score.misses) - MAX_MISSES_SHOWN} more")
    if score.not_extracted:
        lines.append(f"not extracted yet: {', '.join(score.not_extracted)}")
    return lines


def _ratio(part: int, whole: int) -> float | None:
    return part / whole if whole else None


def _share(part: int, whole: int, of: str = "") -> str:
    """Such as "18/20 (90%)", or "0/0 (n/a)" when there is nothing to divide; `of` goes before the brackets."""
    middle = f" {of}" if of else ""
    return f"{part}/{whole}{middle} ({part / whole:.0%})" if whole else f"{part}/{whole}{middle} (n/a)"


def _count(n: int, thing: str) -> str:
    return f"{n} {thing}{'' if n == 1 else 's'}"
