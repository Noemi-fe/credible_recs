"""Scores module 2's ranking against Noemi's graded judgements of thread relevance.

Grades (Noemi, 7 Oct 2026):
- 2, fits the need: buying advice or experience for this exact question;
- 1, useful evidence about the product type: long-term use, brand experience, warnings, other budgets or alternatives;
- 0, off-topic: about something else (cleaning, sizes, news) or comparing things beside the question.

Two measures:
- top 3: of the 3 threads picked for each blind-test question, how many fit the need, and how many are useful;
- ordering: for every pair of a useful thread and an off-topic thread of the same question, is the useful one
  ranked higher? This is where the off-topic examples count, even when they never reach the top 3.

The judgements live in eval/edge_cases/retrieval.json as thread ids with a short reason, never Reddit text. The
candidate threads (with their titles) stay on this machine in data/eval/retrieval_pool.json, so the same pool can
be ranked again after every change without spending credits.
"""

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_JUDGEMENTS = REPO_ROOT / "eval" / "edge_cases" / "retrieval.json"
DEFAULT_POOL = REPO_ROOT / "data" / "eval" / "retrieval_pool.json"


def load_judgements(path: Path = DEFAULT_JUDGEMENTS) -> dict[tuple[str, str], int]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {(j["question"], j["post"]): j["grade"] for j in data["judgements"]}


def score_ranking(ranked: dict[str, list[str]], judgements: dict[tuple[str, str], int]) -> dict[str, dict]:
    """For each question, how many of its top 3 have each grade (None: not judged yet)."""
    scores = {}
    for question, ids in ranked.items():
        grades = [judgements.get((question, post_id)) for post_id in ids[:3]]
        scores[question] = {grade: grades.count(grade) for grade in (2, 1, 0, None)}
    return scores


def score_ordering(
    ranked: dict[str, list[str]], judgements: dict[tuple[str, str], int], pool: dict[str, list[str]] | None = None
) -> tuple[int, int]:
    """(pairs in the right order, pairs) over every useful/off-topic pair of judged threads of a question.

    With `pool` (each question's candidate ids), a judged thread the ranking left out counts as ranked last: a
    dropped useful thread is a miss, and two dropped threads tie, which counts as wrong.
    """
    right = total = 0
    for question, ids in ranked.items():
        position = {post_id: i for i, post_id in enumerate(ids)}
        for post_id in (pool or {}).get(question, []):
            position.setdefault(post_id, len(ids))
        judged = [(p, g) for (q, p), g in judgements.items() if q == question and p in position]
        useful = [position[p] for p, g in judged if g >= 1]
        off_topic = [position[p] for p, g in judged if g == 0]
        for u in useful:
            for o in off_topic:
                total += 1
                right += u < o
    return right, total


def summary_lines(scores: dict[str, dict], ordering: tuple[int, int]) -> list[str]:
    fits = sum(s[2] for s in scores.values())
    useful = fits + sum(s[1] for s in scores.values())
    judged = useful + sum(s[0] for s in scores.values())
    unjudged = sum(s[None] for s in scores.values())
    right, total = ordering
    return [
        f"top 3, fits the need (grade 2): {fits}/{judged} judged ({_share(fits, judged)}); "
        f"useful (grade 1 or 2): {useful}/{judged} ({_share(useful, judged)}); {unjudged} not judged yet; {len(scores)} questions",
        f"ordering, useful above off-topic: {right}/{total} pairs ({_share(right, total)})",
    ]


def _share(part: int, whole: int) -> str:
    return f"{part / whole:.0%}" if whole else "n/a"
