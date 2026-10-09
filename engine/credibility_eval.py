"""Scores module 5 (credibility) against Noemi's labels of the gold set.

Two comparisons, each "the rules' level against hers":
- voice: every comment she gave a voice level (high, medium or low), scored by engine.credibility.score_voice;
- evidence: every product she labelled in those comments (long-term use, short-term use or no first-hand use),
  scored by score_evidence with her product name and stance, and her other products in the same comment as the
  alternatives it compares. Her rows with kind = yes are kinds of product, not products, so they are left out.

For each, four views:
- exact agreement: the same level;
- high-versus-low (the brief's "credibility agreement", target 80%): of her labels at either end (high or low;
  long-term or no first-hand use), how many the rules did NOT put at the opposite end. Swapping the two ends is
  the costly mistake: trusting a shill, or dismissing an expert. Also shown: how many got the very same end;
- the confusion table: her level in rows, the rules' in columns;
- the split: how many highs, mediums and lows she gave, and the rules gave. Her tags are counted against the rules'
  tags too, to show which signs each side used.

Replies that agree come from the AI's extraction of the thread (its checked agreements), as they will in use. A
thread without an extraction is scored without them.

The held-out thread: 1tfk6nm (kettle) was labelled while these rules were being written and was never used to
build or tune them, so it is the fair test. It is left out of the score unless asked for (skip_threads=()).

The report lists only counts, levels and comment ids: never comment text, never product names.

Command line: `python -m engine.credibility_eval` prints the report for data/gold, the held-out thread left out.
"""

import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from engine.config import EVIDENCE_LEVELS, VOICE_LEVELS
from engine.credibility import score_evidence, score_voice
from engine.extract import CheckResult, ExtractionError, load_checked
from engine.gold import DEFAULT_GOLD_DIR, GoldSet, GoldSetError, load_gold_set

HOLDOUT_THREADS = ("1tfk6nm",)  # the kettle thread: the fair test, never used to build the rules
MAX_DIFFERENCES_SHOWN = 15


@dataclass
class LevelAgreement:
    """Her level and the rules' level for each labelled item, and what they add up to."""

    levels: tuple[str, ...]  # best first, such as ("high", "medium", "low")
    pairs: list[tuple[str, str, str]] = field(default_factory=list)  # (comment id, her level, the rules' level)

    @property
    def total(self) -> int:
        return len(self.pairs)

    @property
    def exact(self) -> int:
        return sum(hers == rules for _, hers, rules in self.pairs)

    @property
    def extremes(self) -> int:
        """Her labels at either end: the best level or the worst."""
        return sum(hers in self._ends for _, hers, _ in self.pairs)

    @property
    def swaps(self) -> int:
        """Her labels at one end that the rules put at the other."""
        return sum(hers in self._ends and rules in self._ends and hers != rules for _, hers, rules in self.pairs)

    @property
    def not_swapped(self) -> int:
        return self.extremes - self.swaps

    @property
    def same_extreme(self) -> int:
        return sum(hers in self._ends and hers == rules for _, hers, rules in self.pairs)

    @property
    def _ends(self) -> tuple[str, str]:
        return self.levels[0], self.levels[-1]

    def confusion(self) -> Counter:
        """How many items have each (her level, the rules' level)."""
        return Counter((hers, rules) for _, hers, rules in self.pairs)

    def split(self, side: str) -> dict[str, int]:
        """How many of each level "hers" or "rules" gave, best first."""
        counts = Counter(hers if side == "hers" else rules for _, hers, rules in self.pairs)
        return {level: counts[level] for level in self.levels}


@dataclass
class TagAgreement:
    """How often each tag was used: by her, by the rules, and by both on the same item."""

    hers: Counter = field(default_factory=Counter)
    rules: Counter = field(default_factory=Counter)
    both: Counter = field(default_factory=Counter)

    def add(self, hers: Iterable[str], rules: Iterable[str]) -> None:
        hers, rules = set(hers), set(rules)
        self.hers.update(hers)
        self.rules.update(rules)
        self.both.update(hers & rules)


@dataclass
class CredibilityAgreement:
    voice: LevelAgreement = field(default_factory=lambda: LevelAgreement(VOICE_LEVELS))
    evidence: LevelAgreement = field(default_factory=lambda: LevelAgreement(EVIDENCE_LEVELS))
    voice_tags: TagAgreement = field(default_factory=TagAgreement)
    evidence_tags: TagAgreement = field(default_factory=TagAgreement)
    threads: list[str] = field(default_factory=list)  # thread ids scored
    held_out: list[str] = field(default_factory=list)  # thread ids left out on purpose
    agreements_used: int = 0  # replies that agree, from the AI's extraction of the scored threads


def score_credibility(
    gold: GoldSet, checked: dict[str, CheckResult] | None = None, skip_threads: Iterable[str] = HOLDOUT_THREADS
) -> CredibilityAgreement:
    """Compares the rules with Noemi's voice and evidence labels, thread by thread, in the gold set's order.

    `checked` holds the AI's checked extractions ({thread id: CheckResult}, as engine.extract.load_checked returns
    them), for the replies that agree. Threads in `skip_threads` are left out.
    """
    skip = set(skip_threads)
    checked = checked or {}
    voices = {v.comment_id: v for v in gold.voices if v.voice is not None}
    products: dict[str, list] = {}
    for label in gold.mentions:
        if not label.kind:
            products.setdefault(label.comment_id, []).append(label)

    score = CredibilityAgreement(held_out=sorted(skip))
    for thread in gold.threads:
        if thread.id in skip or not any(c.id in voices for c in thread.comments):
            continue
        score.threads.append(thread.id)
        agreements = checked[thread.id].kept_agreements if thread.id in checked else []
        score.agreements_used += len(agreements)
        for comment in thread.comments:
            if comment.id in voices:
                _compare_comment(score, comment, thread, voices[comment.id], products.get(comment.id, []), agreements)
    return score


def _compare_comment(score: CredibilityAgreement, comment, thread, her_voice, her_products, agreements) -> None:
    """Adds one labelled comment: its voice, then each of its products."""
    rules_voice = score_voice(comment, thread, agreements)
    score.voice.pairs.append((comment.id, her_voice.voice, rules_voice.level))
    score.voice_tags.add(her_voice.tags, rules_voice.tags)
    for label in her_products:
        others = [other.product for other in her_products if other is not label]
        rules_evidence = score_evidence(comment, label.product, label.stance, others)
        score.evidence.pairs.append((comment.id, label.evidence, rules_evidence.level))
        score.evidence_tags.add(label.tags, rules_evidence.tags)


# --- The report ---

def credibility_report(gold_dir: Path = DEFAULT_GOLD_DIR, skip_threads: Iterable[str] = HOLDOUT_THREADS) -> str:
    """Module 5's section of eval/run_eval.py: loads the gold set and its extractions, scores, and reports.

    A broken gold set is reported, not raised. Without readable extractions, voices are scored without replies
    that agree, and the report says so.
    """
    title = "Module 5, credibility (rules, no AI)"
    try:
        gold = load_gold_set(Path(gold_dir))
    except GoldSetError as e:
        return f"{title}\n  gold set: {e}"
    try:
        checked = load_checked(Path(gold_dir) / "threads")
    except (ExtractionError, GoldSetError):
        checked = {}
    return "\n".join([title] + [f"  {line}" for line in report_lines(score_credibility(gold, checked, skip_threads))])


def report_lines(score: CredibilityAgreement) -> list[str]:
    """The scores of both layers, their splits, confusion tables, tags and differences: counts, levels and ids only."""
    held_out = f"; held out (never used to build the rules): {', '.join(score.held_out)}" if score.held_out else ""
    lines = [
        f"{_count(len(score.threads), 'thread')} ({', '.join(score.threads) or 'none'}), "
        f"{_count(score.voice.total, 'labelled comment')}, {_count(score.evidence.total, 'product mention')}{held_out}",
        f"replies that agree, from the AI's extraction: {score.agreements_used}",
    ]
    lines += _layer_lines("voice", score.voice, score.voice_tags)
    lines += _layer_lines("evidence", score.evidence, score.evidence_tags)
    return lines


def _layer_lines(name: str, agreement: LevelAgreement, tags: TagAgreement) -> list[str]:
    best, worst = agreement.levels[0], agreement.levels[-1]
    lines = [
        f"{name}: {best}-versus-{worst} {_share(agreement.not_swapped, agreement.extremes)} of Noemi's {best} and "
        f"{worst} labels not swapped (target 80%); same end {_share(agreement.same_extreme, agreement.extremes)}; "
        f"exact {_share(agreement.exact, agreement.total)}",
        f"  split: Noemi {_split(agreement.split('hers'))} | rules {_split(agreement.split('rules'))}",
        "  confusion (rows Noemi, columns rules):",
    ]
    width = max(len(level) for level in agreement.levels) + 2
    lines.append("    " + " " * width + "".join(level.rjust(width) for level in agreement.levels))
    table = agreement.confusion()
    for hers in agreement.levels:
        lines.append("    " + hers.ljust(width) + "".join(str(table[(hers, rules)]).rjust(width) for rules in agreement.levels))
    used = sorted(set(tags.hers) | set(tags.rules), key=lambda tag: (-tags.hers[tag], -tags.rules[tag], tag))
    lines.append("  tags (Noemi / rules / both): " + "; ".join(f"{t} {tags.hers[t]}/{tags.rules[t]}/{tags.both[t]}" for t in used))
    lines += _difference_lines(agreement)
    return lines


def _difference_lines(agreement: LevelAgreement) -> list[str]:
    """The items where the levels differ, swaps first: comment id, her level, the rules' level."""
    ends = (agreement.levels[0], agreement.levels[-1])
    differ = [p for p in agreement.pairs if p[1] != p[2]]
    differ.sort(key=lambda p: not (p[1] in ends and p[2] in ends))  # swaps first, otherwise in thread order
    lines = []
    for comment_id, hers, rules in differ[:MAX_DIFFERENCES_SHOWN]:
        swap = "  SWAP" if hers in ends and rules in ends else ""
        lines.append(f"    {comment_id}  Noemi {hers}, rules {rules}{swap}")
    if len(differ) > MAX_DIFFERENCES_SHOWN:
        lines.append(f"    ... and {len(differ) - MAX_DIFFERENCES_SHOWN} more")
    return (["  differences:"] + lines) if lines else []


def _split(counts: dict[str, int]) -> str:
    return ", ".join(f"{level} {n}" for level, n in counts.items())


def _share(part: int, whole: int) -> str:
    """Such as "18/20 (90%)", or "0/0 (n/a)" when there is nothing to divide."""
    return f"{part}/{whole} ({part / whole:.0%})" if whole else f"{part}/{whole} (n/a)"


def _count(n: int, thing: str) -> str:
    return f"{n} {thing}{'' if n == 1 else 's'}"


if __name__ == "__main__":
    print(credibility_report())
    sys.exit(0)
