"""Scores module 4 (product matching) against labelled pairs of names, and sums up its groups in the library.

The pairs: eval/edge_cases/matching.json holds pairs of product names copied from the library (names only, never
comment text), each labelled the same product or not, and tagged with the brief's edge case it tests (sizes and
variants, old and new formula, short names, US and EU names, brand or line alone, spelling and spacing...).
A pair is right when engine.match_products.same_product, with the category's known short names, says what the
label says. The brief's target is at least 90% right (MATCHING_TARGET in engine/config.py).

What "the same product" means in a label: the two names can name one product. A brand or product line alone
counts as the same as its products ("Comandante" and "Comandante C40"), as same_product treats it; grouping
(engine/group_products.py) keeps such a name apart when it fits more than one product. An unmarked name next to
"new" or "old" counts as different: the old formula's reviews must not count for the new one.

The library summary (library_lines), from the AI's checked extractions: how many product groups, the biggest,
the loose ones (a brand or line that fits several products), and the merges worth a look: a name joined through
a spelling slip or a known short name (it neither holds nor is held by the shown name), or a much shorter name
taken to be this product (under half the shown name's words: "Lodge 12" in a "Lodge 12 carbon steel fry pan").

Command line:
    python -m engine.matching_eval            the pairs score and a short library summary
    python -m engine.matching_eval library    the library summary in full
"""

import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from engine.config import MATCHING_TARGET, MENTION_CATEGORIES
from engine.extract import CheckResult, ExtractionError, load_checked
from engine.group_products import ProductGroup, group_products, mentions_from_checked
from engine.match_products import Aliases, join_split_words, known_aliases, normalize_name, same_product
from engine.models import Record

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAIRS = REPO_ROOT / "eval" / "edge_cases" / "matching.json"
DEFAULT_LIBRARY_DIR = REPO_ROOT / "data" / "library"
BIGGEST_SHOWN = 10
TO_CHECK_SHOWN = 15


class MatchingPairError(Exception):
    pass


class MatchingPair(Record):
    id: str
    a: str
    b: str
    category: Literal[MENTION_CATEGORIES]
    same: bool  # Noemi's label: do the two names name the same product?
    edge_case: str  # which edge case of the brief it tests
    note: str = ""


class MatchingPairFile(Record):
    approved: bool  # True once Noemi has checked every label
    approved_note: str = ""
    pairs: list[MatchingPair]


def load_pairs(path: Path = DEFAULT_PAIRS) -> MatchingPairFile:
    try:
        data = MatchingPairFile.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, ValueError, ValidationError) as e:  # missing, bad JSON, or a pair that doesn't fit the shape
        raise MatchingPairError(f"{path}: {e}") from e
    repeated = sorted(pair_id for pair_id, n in Counter(p.id for p in data.pairs).items() if n > 1)
    if repeated:
        raise MatchingPairError(f"{path}: pair ids used more than once: {', '.join(repeated)}")
    return data


@dataclass
class PairResult:
    pair: MatchingPair
    said_same: bool  # what the matcher said

    @property
    def right(self) -> bool:
        return self.said_same == self.pair.same


def score_pairs(pairs: list[MatchingPair], aliases: dict[str, Aliases] | None = None) -> list[PairResult]:
    """What the matcher says of each pair, with the pair's category's known short names (the shipped list by default)."""
    aliases = known_aliases() if aliases is None else aliases
    return [PairResult(p, same_product(p.a, p.b, aliases.get(p.category, {}))) for p in pairs]


def report_lines(pairs_file: MatchingPairFile, results: list[PairResult]) -> list[str]:
    """The score against the target, the score per edge case, then every miss."""
    status = "approved by Noemi" if pairs_file.approved else "DRAFT: not yet approved by Noemi"
    right = sum(r.right for r in results)
    met = "met" if results and right / len(results) >= MATCHING_TARGET else "not met"
    lines = [
        f"Module 4, product matching, {len(results)} labelled pairs ({status})",
        f"  same or different: {right}/{len(results)} right ({_percent(right, len(results))}); target {MATCHING_TARGET:.0%}, {met}",
    ]
    by_case: dict[str, list[PairResult]] = defaultdict(list)
    for r in results:
        by_case[r.pair.edge_case].append(r)
    lines.append("  by edge case: " + ", ".join(
        f"{case}: {sum(r.right for r in rs)}/{len(rs)}" for case, rs in sorted(by_case.items())))
    misses = [r for r in results if not r.right]
    if misses:
        lines.append("  misses:")
        for r in misses:
            said = "same" if r.said_same else "different"
            lines.append(f"    {r.pair.id} {r.pair.a!r} / {r.pair.b!r}: labelled {'same' if r.pair.same else 'different'}, "
                         f"said {said} ({r.pair.edge_case})")
    return lines


# --- The library summary ---

def library_lines(checked: dict[str, CheckResult], aliases: dict[str, Aliases] | None = None,
                  full: bool = False) -> list[str]:
    """Product groups made from every kept mention of the checked extractions. `full` lists every loose group."""
    groups = group_products(mentions_from_checked(checked), aliases)
    mentions = sum(len(g.mentions) for g in groups)
    loose = [g for g in groups if g.loose]
    lines = [f"library: {_count(mentions, 'mention')} in {_count(len(checked), 'thread')} -> "
             f"{_count(len(groups), 'product group')}, {len(loose)} loose (a brand or line, not one product)"]
    lines.append("  biggest: " + "; ".join(_described(g) for g in groups[:BIGGEST_SHOWN]))
    shown_loose = loose if full else loose[:BIGGEST_SHOWN]
    if shown_loose:
        lines.append("  loose: " + "; ".join(_described(g) for g in shown_loose))
    to_check = [(g, names) for g in groups if (names := merges_to_check(g))]
    for g, names in to_check if full else to_check[:TO_CHECK_SHOWN]:
        lines.append(f"  to check: {g.name} <- {', '.join(names)}")
    if not full and len(to_check) > TO_CHECK_SHOWN:
        lines.append(f"  ... and {len(to_check) - TO_CHECK_SHOWN} more groups to check")
    return lines


def merges_to_check(group: ProductGroup) -> list[str]:
    """The names of a group worth a look: joined through a spelling slip or a known short name, or much shorter
    than the shown name. Compared on their own words, with no short name written out."""
    shown = normalize_name(group.name)
    flagged = []
    for name in sorted(group.names):
        words = normalize_name(name)
        if not words:
            continue
        a = set(join_split_words(words, shown))
        b = set(join_split_words(shown, list(a)))
        if not (a <= b or b <= a) or (a < b and 2 * len(a) < len(b)):
            flagged.append(name)
    return flagged


def _described(group: ProductGroup) -> str:
    return f"{group.name} ({_count(len(group.mentions), 'mention')})"


# --- For eval/run_eval.py ---

def matching_section(pairs_path: Path = DEFAULT_PAIRS, library_dir: Path = DEFAULT_LIBRARY_DIR,
                     ) -> tuple[str, list[PairResult] | None]:
    """Module 4's lines for the evaluation harness: the pairs score, then the library summary if there is one. Returns
    the printed text and the pairs' results it was printed from (None when the pairs can't be read), which also go
    into eval/metrics.json (engine/metrics.py)."""
    results = None
    try:
        pairs_file = load_pairs(pairs_path)
    except MatchingPairError as e:
        lines = ["Module 4, product matching", f"  pairs: {e}"]
    else:
        results = score_pairs(pairs_file.pairs)
        lines = report_lines(pairs_file, results)
    threads_dir = Path(library_dir) / "threads"
    if not threads_dir.is_dir():
        lines.append(f"  library: skipped (no library at {threads_dir})")
        return "\n".join(lines), results
    try:
        checked = load_checked(threads_dir)
    except ExtractionError as e:
        lines.append(f"  library: {e}")
    else:
        lines += [f"  {line}" for line in library_lines(checked)[:2]]
    return "\n".join(lines), results


def matching_report(pairs_path: Path = DEFAULT_PAIRS, library_dir: Path = DEFAULT_LIBRARY_DIR) -> str:
    """Module 4's lines for the evaluation harness, as text only."""
    return matching_section(pairs_path, library_dir)[0]


def _percent(part: int, whole: int) -> str:
    return f"{part / whole:.0%}" if whole else "n/a"


def _count(n: int, thing: str) -> str:
    return f"{n} {thing}{'' if n == 1 else 's'}"


def main(argv: list[str]) -> int:
    if argv == ["library"]:
        threads_dir = DEFAULT_LIBRARY_DIR / "threads"
        if not threads_dir.is_dir():
            print(f"No library at {threads_dir}.")
            return 1
        print("\n".join(library_lines(load_checked(threads_dir), full=True)))
        return 0
    if argv:
        print(__doc__)
        return 2
    print(matching_report())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
