"""The evaluation's numbers in one file, eval/metrics.json: written by eval/run_eval.py, shown by the how-we-score page.

eval/run_eval.py scores every module and prints a report. The same scores (the very objects the report is printed
from) are turned into numbers here (build_metrics) and saved as eval/metrics.json. The how-we-score page
(engine/how_page.py, at /how) reads that file each time it is opened, so a new evaluation run shows on the page with no
restart and no copying by hand. run_eval also prints the same numbers as cells for eval/RUNS.md (runs_cells), so the
log, the file and the page all show one run's numbers.

Numbers only. The file is committed, so the page can be published later, and it must never hold Reddit text: no
quotes, no comment text, no usernames, no comment or thread ids, no product names, no question texts. That is why it
is built field by field from the scores' counts (each turned into a plain int or float), never by copying an object.

Shape:
    {
      "measured_on": "2026-10-10",
      "metrics": {<name>: {"value":  the share (0 to 1), or dollars for cost_per_question_usd; null = not measured,
                           "target": the brief's target, or null when it sets none,
                           "count", "out_of":  the share as counts ("45 of 47"), or null,
                           "threads":  how many hand-labelled threads it was measured on, or null}},
                 the names in METRIC_KEYS, always all of them, in that order
      "end_to_end": {"questions", "with_all_picks", "with_a_pick", "picks_wanted", "quotes_shown",
                     "unverified_quotes_shown", "threads_waiting_live_check"}, or null when there was no library
    }
Every target is "at least", except cost per question, which must be under its target (LOWER_IS_BETTER).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from engine import config
from engine.models import Record

if TYPE_CHECKING:
    from engine.credibility_eval import CredibilityAgreement
    from engine.extraction_eval import ExtractionScore
    from engine.matching_eval import PairResult
    from engine.query_eval import Summary
    from engine.slice_eval import QuestionResult

METRICS_FILE = Path(__file__).resolve().parents[1] / "eval" / "metrics.json"

# The brief's metric table first (quote verification to cost), then the other checks the evaluation runs.
HEADLINE_KEYS = (
    "quote_verification",  # end to end: the share of shown quotes found word for word in their comments
    "extraction_precision",  # module 3, votes (recommend or warn): of the AI's products, the share Noemi labelled
    "extraction_recall",  # module 3, votes: of Noemi's products, the share the AI found
    "voice_agreement",  # module 5: of her high and low voices, the share the rules didn't put at the other end
    "evidence_agreement",  # module 5: the same for long-term use and no first-hand use
    "blind_test_vs_vetted",  # the blind test (week 3): the share of choices that picked our answer over Vetted's
    "blind_test_vs_chatgpt",  # ... and over ChatGPT's
    "cost_per_question_usd",  # logged API spend divided by the questions answered
)
OTHER_KEYS = (
    "ai_quotes_found",  # module 3: of the quotes the AI copied into the library, the share found word for word
    "request_outcome",  # module 1: the right outcome (answer, ask a question, out of scope) and category
    "request_product",  # module 1: the right product type
    "request_details",  # module 1: every detail right (budget, skin types, size, SPF, years)
    "threads_fit",  # module 2: of the top 3 threads per question, the share that fit the need
    "threads_useful",  # module 2: ... the share that are useful evidence
    "thread_order",  # module 2: pairs of a useful and an off-topic thread with the useful one ranked higher
    "name_matching",  # module 4: same-or-different pairs of product names judged right
)
METRIC_KEYS = HEADLINE_KEYS + OTHER_KEYS
LOWER_IS_BETTER = frozenset({"cost_per_question_usd"})
ENTRY_FIELDS = ("value", "target", "count", "out_of", "threads")

# What answering one question costs in paid API calls. There is no API key (Noemi, 7 Oct 2026): the AI steps run
# beforehand, in batches, through Claude Code under her plan, and answering reads saved files. The live check reads
# Reddit's embed page, which is free. So the logged API spend is $0; the day a paid call is added, it is logged and
# passed to EvalResults.api_spend_usd.
API_SPEND_PER_RUN_USD = 0.0


class MetricsError(Exception):
    """eval/metrics.json exists but can't be read: not JSON, or not the shape above."""


@dataclass
class EvalResults:
    """What one evaluation run measured, as the evaluation modules score it; None for a part that couldn't run (its
    local data is missing). eval/run_eval.py prints its report from these and builds eval/metrics.json from them."""

    query: Summary | None = None  # module 1 (engine.query_eval.summarize)
    retrieval: tuple[dict, tuple[int, int]] | None = None  # module 2: (score_ranking's scores, score_ordering's pairs)
    extraction: ExtractionScore | None = None  # module 3 on the gold set, votes only (the main score)
    library_quotes: tuple[int, int] | None = None  # module 3 on the library: (quotes found word for word, quotes)
    matching: list[PairResult] | None = None  # module 4's labelled pairs
    credibility: CredibilityAgreement | None = None  # module 5
    end_to_end: list[QuestionResult] | None = None  # every blind-test question through modules 1 to 7
    api_spend_usd: float = API_SPEND_PER_RUN_USD


def missing_parts(results: EvalResults) -> list[str]:
    """The parts of a run that couldn't be measured, in words; [] for a complete run.

    eval/run_eval.py writes eval/metrics.json only for a complete run, so a run without the local data (a builder's
    worktree has no library or gold threads) never replaces the real numbers with empty ones.
    """
    parts = [("module 1", results.query), ("module 2", results.retrieval), ("module 3 (gold set)", results.extraction),
             ("module 3 (library)", results.library_quotes), ("module 4", results.matching),
             ("module 5", results.credibility), ("end to end", results.end_to_end)]
    return [name for name, measured in parts if measured is None]


# --- Building the numbers ---

def build_metrics(results: EvalResults, measured_on: date) -> dict:
    """eval/metrics.json's content for one run: numbers only, from the scores' counts."""
    from engine.retrieval_eval import top3_counts

    m = {key: _entry(None, None) for key in METRIC_KEYS}
    m["blind_test_vs_vetted"] = _entry(None, None, config.BLIND_TEST_TARGET)
    m["blind_test_vs_chatgpt"] = _entry(None, None, config.BLIND_TEST_TARGET)
    m["quote_verification"] = _entry(None, None, config.QUOTE_VERIFICATION_TARGET)
    m["extraction_precision"] = _entry(None, None, config.EXTRACTION_PRECISION_TARGET)
    m["extraction_recall"] = _entry(None, None, config.EXTRACTION_RECALL_TARGET)
    m["voice_agreement"] = _entry(None, None, config.CREDIBILITY_AGREEMENT_TARGET)
    m["evidence_agreement"] = _entry(None, None, config.CREDIBILITY_AGREEMENT_TARGET)
    m["name_matching"] = _entry(None, None, config.MATCHING_TARGET)
    m["cost_per_question_usd"] = _entry(None, None, config.COST_PER_QUESTION_TARGET_USD)

    if results.query is not None:
        m["request_outcome"] = _entry(*results.query.outcome)
        m["request_product"] = _entry(*results.query.product)
        m["request_details"] = _entry(*results.query.constraints)
    if results.retrieval is not None:
        scores, ordering = results.retrieval
        fits, useful, judged, _ = top3_counts(scores)
        m["threads_fit"] = _entry(fits, judged)
        m["threads_useful"] = _entry(useful, judged)
        m["thread_order"] = _entry(*ordering)
    if results.extraction is not None:
        votes = results.extraction
        m["extraction_precision"] = _entry(votes.matched, votes.ai_total, config.EXTRACTION_PRECISION_TARGET, votes.threads)
        m["extraction_recall"] = _entry(votes.matched, votes.gold_total, config.EXTRACTION_RECALL_TARGET, votes.threads)
    if results.library_quotes is not None:
        m["ai_quotes_found"] = _entry(*results.library_quotes)
    if results.matching is not None:
        m["name_matching"] = _entry(sum(r.right for r in results.matching), len(results.matching), config.MATCHING_TARGET)
    if results.credibility is not None:
        score, threads = results.credibility, len(results.credibility.threads)
        m["voice_agreement"] = _entry(score.voice.not_swapped, score.voice.extremes, config.CREDIBILITY_AGREEMENT_TARGET,
                                      threads)
        m["evidence_agreement"] = _entry(score.evidence.not_swapped, score.evidence.extremes,
                                         config.CREDIBILITY_AGREEMENT_TARGET, threads)

    end_to_end = None
    if results.end_to_end is not None:
        questions = results.end_to_end
        shown = sum(int(q.quotes_shown) for q in questions)
        unverified = sum(int(q.unverified) for q in questions)
        # Each problem unverified_claims finds counts against one shown quote, so the share can only be too low.
        m["quote_verification"] = _entry(max(shown - unverified, 0), shown, config.QUOTE_VERIFICATION_TARGET)
        if questions:
            m["cost_per_question_usd"]["value"] = float(results.api_spend_usd) / len(questions)
        end_to_end = {
            "questions": len(questions),
            "with_all_picks": sum(len(q.picks) >= config.PICKS_SHOWN for q in questions),
            "with_a_pick": sum(bool(q.picks) for q in questions),
            "picks_wanted": int(config.PICKS_SHOWN),
            "quotes_shown": shown,
            "unverified_quotes_shown": unverified,
            "threads_waiting_live_check": sum(int(q.waiting_live_check) for q in questions),
        }
    return {"measured_on": measured_on.isoformat(), "metrics": m, "end_to_end": end_to_end}


def _entry(count: int | None, out_of: int | None, target: float | None = None, threads: int | None = None) -> dict:
    """One metric: its share (null when there is nothing to divide), target, counts and threads, as plain numbers."""
    count = None if count is None else int(count)
    out_of = None if out_of is None else int(out_of)
    value = count / out_of if count is not None and out_of else None
    return {"value": value, "target": None if target is None else float(target), "count": count, "out_of": out_of,
            "threads": None if threads is None else int(threads)}


# --- Writing and reading the file ---

class MetricEntry(Record):
    value: float | None = None
    target: float | None = None
    count: int | None = None
    out_of: int | None = None
    threads: int | None = None


class EndToEnd(Record):
    questions: int
    with_all_picks: int
    with_a_pick: int
    picks_wanted: int
    quotes_shown: int
    unverified_quotes_shown: int
    threads_waiting_live_check: int = 0


class MetricsFile(Record):
    measured_on: date
    metrics: dict[str, MetricEntry]
    end_to_end: EndToEnd | None = None


def write_metrics(metrics: dict, path: Path = METRICS_FILE) -> None:
    """Saves one run's numbers, checked against the shape first."""
    MetricsFile.model_validate(metrics)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")


def load_metrics(path: Path = METRICS_FILE) -> MetricsFile | None:
    """The latest run's numbers; None when there is no file yet. Raises MetricsError for a file that can't be read."""
    path = Path(path)
    if not path.is_file():
        return None
    try:
        return MetricsFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, ValidationError) as e:  # unreadable, not JSON, or not the shape
        raise MetricsError(f"{path}: {e}") from e


# --- The blind test's result (10 Oct 2026) ---

BLIND_TEST_KEYS = {"vetted": "blind_test_vs_vetted", "chatgpt": "blind_test_vs_chatgpt"}


def save_blind_test(against: dict[str, tuple[int, int]], path: Path = METRICS_FILE) -> None:
    """Writes the blind test's result into the metrics file: for each rival, (rankings with ours above it,
    rankings), from engine.blind_test.tally. Everything else in the file stays as it is. Raises MetricsError when
    there is no file yet: run eval/run_eval.py first."""
    current = load_metrics(path)
    if current is None:
        raise MetricsError(f"{path}: no metrics file yet; run eval/run_eval.py first")
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for rival, (wins, total) in against.items():
        data["metrics"][BLIND_TEST_KEYS[rival]] = _entry(wins, total, config.BLIND_TEST_TARGET)
    write_metrics(data, path)


def carry_blind_test(metrics: dict, path: Path = METRICS_FILE) -> dict:
    """The new run's numbers, with the blind test's result carried over from the file (an evaluation run doesn't
    measure it, so it must not wipe it). Unchanged when there is no file or no result in it."""
    try:
        current = load_metrics(path)
    except MetricsError:
        return metrics
    if current is None:
        return metrics
    old = json.loads(Path(path).read_text(encoding="utf-8"))["metrics"]
    carried = {key: old[key] for key in BLIND_TEST_KEYS.values() if old.get(key, {}).get("value") is not None}
    if not carried:
        return metrics
    return {**metrics, "metrics": {**metrics["metrics"], **carried}}


# --- The same numbers for eval/RUNS.md ---

def runs_cells(metrics: dict) -> str:
    """The metric cells of an eval/RUNS.md row, in the table's column order: Module 1 | Module 2 | Quote verification |
    Extraction P | Extraction R | Credibility agreement | Cost/query. "n/a" for what wasn't measured."""
    m = {key: MetricEntry.model_validate(entry) for key, entry in metrics["metrics"].items()}
    e2e = metrics.get("end_to_end")

    def part(key: str) -> str | None:
        entry = m.get(key)
        return f"{entry.count}/{entry.out_of}" if entry is not None and entry.count is not None else None

    def share(key: str) -> str | None:
        entry = m.get(key)
        return f"{part(key)} ({entry.value:.0%})" if part(key) and entry.value is not None else part(key)

    module_1 = [part(k) for k in ("request_outcome", "request_product", "request_details")]
    module_2 = (f"fits {part('threads_fit')}, useful {part('threads_useful')}; ordering {share('thread_order')}"
                if part("threads_fit") and part("thread_order") else None)
    quotes = []
    if part("ai_quotes_found"):
        quotes.append(f"library {part('ai_quotes_found')}")
    if e2e is not None and part("quote_verification"):
        quotes.append(f"shown {part('quote_verification')}, unverified shown {e2e['unverified_quotes_shown']}")
    voice, evidence = share("voice_agreement"), share("evidence_agreement")
    credibility = (f"voice high-vs-low {voice}, evidence long-vs-none {evidence}" if voice and evidence else None)
    cost = m.get("cost_per_question_usd")
    cells = [
        " · ".join(module_1) if all(module_1) else None,
        module_2,
        "; ".join(quotes) or None,
        f"votes {share('extraction_precision')}" if share("extraction_precision") else None,
        f"votes {share('extraction_recall')}" if share("extraction_recall") else None,
        credibility,
        f"${cost.value:.2f}" if cost is not None and cost.value is not None else None,
    ]
    return " | ".join(cell or "n/a" for cell in cells)
