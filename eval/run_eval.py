"""Evaluation harness: runs the pipeline on the hand-checked data and reports every metric.

Built so far:
- the label report: how often the "other" reason tag is used, and the notes given with it;
- module 1 (query understanding): outcome, product type and constraints against eval/edge_cases/query.json.
- module 2 (retrieval): of the 3 threads picked per blind-test question, how many fit the need (grade 2) and how
  many are useful (grade 1 or 2), plus whether useful threads rank above off-topic ones, against
  eval/edge_cases/retrieval.json, re-ranking the saved candidate pool (no credits).
Still to come, as the engine modules are built: quote verification, extraction precision and recall,
credibility agreement and cost per query.

Log every run in eval/RUNS.md.
"""

import json
import sys
from pathlib import Path

from engine.gold import GoldSetError, load_gold_set, print_other_tag_report
from engine.query import parse_query
from engine.query_eval import QueryCaseError, load_query_cases, report_lines, score_cases
from engine.retrieval_eval import DEFAULT_JUDGEMENTS, DEFAULT_POOL, load_judgements, score_ordering, score_ranking, summary_lines
from engine.sources import rank_posts

QUESTIONS = Path(__file__).resolve().parent / "blind_test" / "questions.json"


def main() -> int:
    status = 0
    try:
        gold = load_gold_set()
    except GoldSetError as e:
        print(e)
        status = 1
    else:
        print("Labels")
        print_other_tag_report(gold)

    print()
    try:
        cases = load_query_cases()
    except QueryCaseError as e:
        print(e)
        status = 1
    else:
        print("\n".join(report_lines(cases, score_cases(cases.cases, parse_query), "rules only")))

    print()
    print(_retrieval_report())

    print("\nModules 3-7: not built yet.")
    return status


def _retrieval_report() -> str:
    """Module 2: ranks the saved candidate pool again (no credits) and checks the top 3 against the judgements."""
    if not DEFAULT_POOL.exists():
        return "Module 2, retrieval: skipped (no local candidate pool at data/eval/retrieval_pool.json)"
    pool = json.loads(DEFAULT_POOL.read_text(encoding="utf-8"))
    texts = {q["id"]: q["text"] for q in json.loads(QUESTIONS.read_text(encoding="utf-8"))["questions"]}
    ranked = {qid: [p["id"] for p in rank_posts(parse_query(texts[qid]), posts)] for qid, posts in pool.items()}
    approved = json.loads(DEFAULT_JUDGEMENTS.read_text(encoding="utf-8"))["approved"]
    status = "approved by Noemi" if approved else "DRAFT judgements: not yet approved by Noemi"
    judgements = load_judgements()
    pool_ids = {qid: [p["id"] for p in posts] for qid, posts in pool.items()}
    lines = summary_lines(score_ranking(ranked, judgements), score_ordering(ranked, judgements, pool_ids))
    return f"Module 2, retrieval ({status})\n" + "\n".join(f"  {line}" for line in lines)


if __name__ == "__main__":
    sys.exit(main())
