"""Evaluation harness: runs the whole pipeline on the gold set and reports every metric.

Built so far: the label report, i.e. how often the "other" reason tag is used and the notes given with it.
Still to come, as the engine modules are built: quote verification, extraction precision and recall,
credibility agreement and cost per query.
"""

import sys

from engine.gold import GoldSetError, load_gold_set, print_other_tag_report


def main() -> int:
    try:
        gold = load_gold_set()
    except GoldSetError as e:
        print(e)
        return 1
    print("Labels")
    print_other_tag_report(gold)
    print("\nPipeline metrics: not built yet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
