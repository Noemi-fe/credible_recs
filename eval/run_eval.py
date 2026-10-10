"""Evaluation harness: runs the pipeline on the hand-checked data and reports every metric.

Built so far:
- the label report: how often the "other" reason tag is used, and the notes given with it;
- module 1 (query understanding): outcome, product type and constraints against eval/edge_cases/query.json.
- module 3 (mention extraction): precision, recall, stance and category agreement of the AI's products against
  Noemi's gold labels, and the share of quotes found word for word in their comments;
- module 4 (product matching): same-or-different name pairs against eval/edge_cases/matching.json, and how the
  library's mentions group into products;
- module 5 (credibility): voice and evidence levels from rules against Noemi's labels, with writers' profiles filled
  in as answers have them (the library's profile store; the kettle thread is held out: the fair test);
- end to end (modules 1-7): every blind-test question through the pipeline on the library: how many get a full
  top 3, how many at least one pick, and that no shown quote fails the word-for-word check;
- module 2 (retrieval): of the 3 threads picked per blind-test question, how many fit the need (grade 2) and how
  many are useful (grade 1 or 2), plus whether useful threads rank above off-topic ones, against
  eval/edge_cases/retrieval.json, re-ranking the saved candidate pool (no credits).
Still to come: the blind test's preference per rival (engine/blind_test.py tally, week 3).

The numbers (10 Oct 2026): each section's scores are kept (engine.metrics.EvalResults) as the report prints them, and
at the end the same scores are saved as numbers only in eval/metrics.json, which the how-we-score page (/how) shows.
The file is written only when every part could run, so a run without the local data (no library, no gold threads)
never replaces real numbers with empty ones. The last lines are the metric cells for this run's row in eval/RUNS.md.

Log every run in eval/RUNS.md.
"""

import json
import sys
from datetime import date
from pathlib import Path

from engine.extract import ExtractionError, load_checked, overall_quote_pass_rate
from engine.extraction_eval import report_lines as extraction_report_lines
from engine.extraction_eval import score_extraction
from engine.gold import DEFAULT_GOLD_DIR, GoldSetError, load_gold_set, print_other_tag_report
from engine.library import DEFAULT_LIBRARY_DIR
from engine.matching_eval import matching_section
from engine.pipeline import cached_profiles
from engine.credibility_eval import credibility_section
from engine.metrics import (
    METRICS_FILE,
    EvalResults,
    build_metrics,
    carry_blind_test,
    missing_parts,
    runs_cells,
    write_metrics,
)
from engine.slice_eval import slice_section
from engine.query import parse_query
from engine.query_eval import QueryCaseError, load_query_cases, report_lines, score_cases, summarize
from engine.retrieval_eval import DEFAULT_JUDGEMENTS, DEFAULT_POOL, load_judgements, score_ordering, score_ranking, summary_lines
from engine.sources import rank_posts

QUESTIONS = Path(__file__).resolve().parent / "blind_test" / "questions.json"


def main() -> int:
    status = 0
    results = EvalResults()
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
        scored = score_cases(cases.cases, parse_query)
        results.query = summarize(scored)
        print("\n".join(report_lines(cases, scored, "rules only")))

    print()
    print(_retrieval_report(results))

    print()
    print(_extraction_report(results))

    print()
    text, results.matching = matching_section()
    print(text)

    print()
    text, results.credibility = credibility_section(profiles=cached_profiles())
    print(text)

    print()
    text, results.end_to_end = slice_section()
    print(text)

    print()
    print("\n".join(_metrics_lines(results, date.today())))
    return status


def _metrics_lines(results: EvalResults, today: date, path: Path = METRICS_FILE) -> list[str]:
    """Saves eval/metrics.json when every part could run, and gives the RUNS.md cells of the same numbers."""
    metrics = carry_blind_test(build_metrics(results, today), path)  # the blind test's result isn't measured here
    missing = missing_parts(results)
    if missing:
        saved = f"Numbers: {path.name} left as it was (not measured: {', '.join(missing)})."
    else:
        write_metrics(metrics, path)
        saved = f"Numbers: saved in {path.name}, shown by the how-we-score page (/how)."
    return [saved, "For eval/RUNS.md (Module 1 | Module 2 | Quote verification | Extraction P | Extraction R | "
                   "Credibility agreement | Cost/query):", "  " + runs_cells(metrics)]


def _extraction_report(results: EvalResults) -> str:
    """Module 3: the AI's products against Noemi's labels on the gold set, and quote verification everywhere."""
    lines = ["Module 3, mention extraction"]
    try:
        gold, checked = load_gold_set(), load_checked(DEFAULT_GOLD_DIR / "threads")
        score, votes = score_extraction(gold, checked), score_extraction(gold, checked, votes_only=True)
    except (GoldSetError, ExtractionError) as e:
        lines.append(f"  gold set: {e}")
    else:
        results.extraction = votes
        lines += [f"  {line}" for line in extraction_report_lines(score, votes=votes)]
    try:
        library = load_checked(DEFAULT_LIBRARY_DIR / "threads")
    except ExtractionError as e:
        lines.append(f"  library: {e}")
    else:
        kept = sum(len(r.kept) for r in library.values())
        total = kept + sum(len(r.rejected) for r in library.values())
        results.library_quotes = (kept, total)
        rate = overall_quote_pass_rate(library.values())
        share = f"{rate:.0%}" if rate is not None else "n/a"
        lines.append(f"  quote verification (library, {len(library)} threads extracted): {kept}/{total} quotes found word for word ({share})")
    return "\n".join(lines)


def _retrieval_report(results: EvalResults) -> str:
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
    scores, ordering = score_ranking(ranked, judgements), score_ordering(ranked, judgements, pool_ids)
    results.retrieval = (scores, ordering)
    lines = summary_lines(scores, ordering)
    return f"Module 2, retrieval ({status})\n" + "\n".join(f"  {line}" for line in lines)


if __name__ == "__main__":
    sys.exit(main())
