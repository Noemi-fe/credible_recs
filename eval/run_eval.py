"""Evaluation harness: runs the pipeline on the hand-checked data and reports every metric.

Built so far:
- the label report: how often the "other" reason tag is used, and the notes given with it;
- module 1 (query understanding): outcome, product type and constraints against eval/edge_cases/query.json.
Still to come, as the engine modules are built: quote verification, extraction precision and recall,
credibility agreement and cost per query.

Log every run in eval/RUNS.md.
"""

import sys

from engine.gold import GoldSetError, load_gold_set, print_other_tag_report
from engine.query import parse_query
from engine.query_eval import QueryCaseError, load_query_cases, report_lines, score_cases


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

    print("\nModules 2-7: not built yet.")
    return status


if __name__ == "__main__":
    sys.exit(main())
