"""Evaluation harness: runs the pipeline on the hand-checked data and reports every metric.

Built so far:
- the label report: how often the "other" reason tag is used, and the notes given with it;
- module 1 (query understanding): outcome, product type and constraints against eval/edge_cases/query.json.
- module 3 (mention extraction): precision, recall, stance and category agreement of the AI's products against
  Noemi's gold labels, and the share of quotes found word for word in their comments;
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

from engine.extract import ExtractionError, load_checked, overall_quote_pass_rate
from engine.extraction_eval import report_lines as extraction_report_lines
from engine.extraction_eval import score_extraction
from engine.gold import DEFAULT_GOLD_DIR, GoldSetError, load_gold_set, print_other_tag_report
from engine.library import DEFAULT_LIBRARY_DIR
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

    print()
    print(_extraction_report())

    print("\nModules 4-7: not built yet.")
    return status


def _extraction_report() -> str:
    """Module 3: the AI's products against Noemi's labels on the gold set, and quote verification everywhere."""
    lines = ["Module 3, mention extraction"]
    try:
        gold, checked = load_gold_set(), load_checked(DEFAULT_GOLD_DIR / "threads")
        score, votes = score_extraction(gold, checked), score_extraction(gold, checked, votes_only=True)
    except (GoldSetError, ExtractionError) as e:
        lines.append(f"  gold set: {e}")
    else:
        lines += [f"  {line}" for line in extraction_report_lines(score, votes=votes)]
    try:
        library = load_checked(DEFAULT_LIBRARY_DIR / "threads")
    except ExtractionError as e:
        lines.append(f"  library: {e}")
    else:
        kept = sum(len(r.kept) for r in library.values())
        total = kept + sum(len(r.rejected) for r in library.values())
        rate = overall_quote_pass_rate(library.values())
        share = f"{rate:.0%}" if rate is not None else "n/a"
        lines.append(f"  quote verification (library, {len(library)} threads extracted): {kept}/{total} quotes found word for word ({share})")
    return "\n".join(lines)


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
