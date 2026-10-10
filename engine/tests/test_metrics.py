"""eval/metrics.json: the evaluation's numbers, written by eval/run_eval.py and shown by the how-we-score page.

Everything here is made up: scores built as the evaluation modules build them, full of long names and question texts,
so the tests can check that none of that text ever reaches the file. No test reads data/ or calls a network, except
the last one, which checks the committed eval/metrics.json against eval/RUNS.md when the file exists.
"""

import json
import re
from datetime import date

import pytest

from engine import config, metrics
from engine.credibility_eval import CredibilityAgreement
from engine.extraction_eval import MISSED, NOT_LABELLED, ExtractionScore, Miss
from engine.matching_eval import MatchingPair, PairResult
from engine.query_eval import Summary
from engine.slice_eval import QuestionResult

LONG_QUESTION = "gentle chemical exfoliant for sensitive skin that won't sting or peel, under thirty pounds please"
LONG_PRODUCT = "Paula's Choice Skin Perfecting 2% BHA Liquid Exfoliant, the big bottle with the pump top"
COMMENT_ID = "lq3x9zk"


def extraction() -> ExtractionScore:
    """The votes score of module 3: 45 of the AI's 47 votes are hers, and all 45 of hers were found."""
    return ExtractionScore(matched=45, ai_total=47, gold_total=45, same_stance=45, same_category=45, threads=3,
                           labelled_comments=96, misses=[Miss(COMMENT_ID, NOT_LABELLED, LONG_PRODUCT),
                                                         Miss("lq3x9zz", MISSED, LONG_PRODUCT)])


def credibility() -> CredibilityAgreement:
    """Module 5: 3 of her 4 voice extremes not swapped, 2 of her 2 evidence extremes."""
    score = CredibilityAgreement(threads=["1vumd3s", "1ur9shv"], held_out=["1tfk6nm"])
    score.voice.pairs += [("c1", "high", "high"), ("c2", "high", "medium"), ("c3", "low", "high"),
                          ("c4", "low", "low"), ("c5", "medium", "medium")]
    score.evidence.pairs += [("c1", "long-term use", "long-term use"), ("c4", "no first-hand use", "short-term use")]
    return score


def matching() -> list[PairResult]:
    """Module 4: 3 of 4 pairs right."""
    def pair(n, same, said):
        made = MatchingPair(id=f"m{n:02d}", a=LONG_PRODUCT, b=LONG_PRODUCT + " mini", category="skincare", same=same,
                            edge_case="sizes and variants", note="a note that must never be copied")
        return PairResult(made, said)
    return [pair(1, True, True), pair(2, False, False), pair(3, False, False), pair(4, False, True)]


def end_to_end() -> list[QuestionResult]:
    """Three blind-test questions: one full answer, one with one pick, one with none; 14 quotes shown, all verified."""
    return [
        QuestionResult("b01", LONG_QUESTION, "ok", picks=[LONG_PRODUCT, "Zojirushi kettle", "Fellow Stagg EKG"],
                       threads=8, quotes_shown=11, waiting_live_check=1),
        QuestionResult("b02", "retinol for a beginner with sensitive skin", "ok", picks=[LONG_PRODUCT], threads=5,
                       quotes_shown=3),
        QuestionResult("b03", "PFAS-free non-stick frying pan", "ok", threads=4),
    ]


def every_part() -> metrics.EvalResults:
    return metrics.EvalResults(
        query=Summary(outcome=(30, 30), product=(22, 22), constraints=(21, 22)),
        retrieval=({"b01": {2: 2, 1: 1, 0: 0, None: 0}, "b02": {2: 1, 1: 1, 0: 1, None: 0}}, (75, 79)),
        extraction=extraction(),
        library_quotes=(2838, 2838),
        matching=matching(),
        credibility=credibility(),
        end_to_end=end_to_end(),
    )


def built() -> dict:
    return metrics.build_metrics(every_part(), date(2026, 10, 10))


# --- What the file holds ---

def test_each_metric_comes_from_the_evaluations_own_scores():
    m = built()["metrics"]
    assert (m["extraction_precision"]["count"], m["extraction_precision"]["out_of"]) == (45, 47)
    assert m["extraction_precision"]["value"] == pytest.approx(45 / 47)
    assert (m["extraction_recall"]["count"], m["extraction_recall"]["out_of"]) == (45, 45)
    assert m["extraction_precision"]["threads"] == 3
    # High-versus-low: of her 4 highs and lows, only c3 (her low, the rules' high) was swapped.
    assert (m["voice_agreement"]["count"], m["voice_agreement"]["out_of"], m["voice_agreement"]["threads"]) == (3, 4, 2)
    assert (m["evidence_agreement"]["count"], m["evidence_agreement"]["out_of"]) == (2, 2)
    assert (m["name_matching"]["count"], m["name_matching"]["out_of"]) == (3, 4)
    assert (m["ai_quotes_found"]["count"], m["ai_quotes_found"]["out_of"]) == (2838, 2838)
    assert (m["request_outcome"]["count"], m["request_details"]["count"], m["request_details"]["out_of"]) == (30, 21, 22)
    assert (m["threads_fit"]["count"], m["threads_useful"]["count"], m["threads_fit"]["out_of"]) == (3, 5, 6)
    assert (m["thread_order"]["count"], m["thread_order"]["out_of"]) == (75, 79)
    # Every shown quote passed: 14 shown, 0 unverified.
    assert (m["quote_verification"]["count"], m["quote_verification"]["out_of"], m["quote_verification"]["value"]) == (14, 14, 1.0)


def test_the_end_to_end_counts_are_kept():
    assert built()["end_to_end"] == {"questions": 3, "with_all_picks": 1, "with_a_pick": 2, "picks_wanted": config.PICKS_SHOWN,
                                     "quotes_shown": 14, "unverified_quotes_shown": 0, "threads_waiting_live_check": 1}


def test_an_unverified_quote_lowers_quote_verification():
    parts = every_part()
    parts.end_to_end[1].unverified = 1
    m = metrics.build_metrics(parts, date(2026, 10, 10))
    assert (m["metrics"]["quote_verification"]["count"], m["metrics"]["quote_verification"]["out_of"]) == (13, 14)
    assert m["end_to_end"]["unverified_quotes_shown"] == 1


def test_each_target_is_the_briefs():
    m = built()["metrics"]
    assert m["quote_verification"]["target"] == config.QUOTE_VERIFICATION_TARGET == 1.0
    assert m["extraction_precision"]["target"] == config.EXTRACTION_PRECISION_TARGET == 0.90
    assert m["extraction_recall"]["target"] == config.EXTRACTION_RECALL_TARGET == 0.80
    assert m["voice_agreement"]["target"] == m["evidence_agreement"]["target"] == config.CREDIBILITY_AGREEMENT_TARGET == 0.80
    assert m["blind_test_vs_vetted"]["target"] == m["blind_test_vs_chatgpt"]["target"] == config.BLIND_TEST_TARGET == 0.6
    assert m["cost_per_question_usd"]["target"] == config.COST_PER_QUESTION_TARGET_USD == 0.05
    assert m["name_matching"]["target"] == config.MATCHING_TARGET
    assert m["request_outcome"]["target"] is None and m["thread_order"]["target"] is None  # no target in the brief


def test_the_blind_test_is_not_measured_yet():
    m = built()["metrics"]
    for rival in ("blind_test_vs_vetted", "blind_test_vs_chatgpt"):
        assert m[rival]["value"] is None and m[rival]["count"] is None


def test_cost_per_question_is_the_logged_spend_divided_by_the_questions():
    parts = every_part()
    assert metrics.build_metrics(parts, date(2026, 10, 10))["metrics"]["cost_per_question_usd"]["value"] == 0.0
    parts.api_spend_usd = 0.06
    assert metrics.build_metrics(parts, date(2026, 10, 10))["metrics"]["cost_per_question_usd"]["value"] == pytest.approx(0.02)


def test_every_metric_and_count_is_in_the_file_in_a_fixed_order():
    data = built()
    assert list(data) == ["measured_on", "metrics", "end_to_end"]
    assert data["measured_on"] == "2026-10-10"
    assert tuple(data["metrics"]) == metrics.METRIC_KEYS
    for entry in data["metrics"].values():
        assert list(entry) == ["value", "target", "count", "out_of", "threads"]


def test_a_part_that_could_not_run_is_left_empty_not_guessed():
    data = metrics.build_metrics(metrics.EvalResults(), date(2026, 10, 10))
    assert all(entry["value"] is None for key, entry in data["metrics"].items())
    assert data["end_to_end"] is None


def test_nothing_to_divide_is_left_empty():
    parts = every_part()
    parts.extraction = ExtractionScore()  # no labelled thread extracted yet: 0 of 0
    m = metrics.build_metrics(parts, date(2026, 10, 10))["metrics"]
    assert m["extraction_precision"]["value"] is None and m["extraction_precision"]["out_of"] == 0


# --- Numbers only: never Reddit text, names or quotes ---

def _leaves(value, path=()):
    if isinstance(value, dict):
        for key, inner in value.items():
            yield from _leaves(inner, path + (key,))
    else:
        yield path, value


def test_the_file_holds_numbers_only_never_text_from_reddit_or_the_labels():
    data = built()
    text = json.dumps(data)
    for words in (LONG_QUESTION, LONG_PRODUCT, COMMENT_ID, "Zojirushi", "a note that must never be copied", "1vumd3s",
                  "b01", "c3"):
        assert words not in text
    allowed_keys = ({"measured_on", "metrics", "end_to_end"} | set(metrics.METRIC_KEYS)
                    | {"value", "target", "count", "out_of", "threads"} | set(data["end_to_end"]))
    for path, value in _leaves(data):
        assert set(path) <= allowed_keys, path
        if path == ("measured_on",):
            assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
        else:
            assert value is None or (isinstance(value, (int, float)) and not isinstance(value, bool)), (path, value)


def test_the_file_is_written_and_read_back(tmp_path):
    path = tmp_path / "eval" / "metrics.json"
    metrics.write_metrics(built(), path)
    assert json.loads(path.read_text(encoding="utf-8")) == built()
    loaded = metrics.load_metrics(path)
    assert loaded.measured_on == date(2026, 10, 10)
    assert loaded.metrics["extraction_precision"].count == 45 and loaded.end_to_end.quotes_shown == 14


def test_a_missing_file_reads_as_none_and_a_broken_one_as_an_error(tmp_path):
    assert metrics.load_metrics(tmp_path / "metrics.json") is None
    for broken in ("{not json", json.dumps({"measured_on": "<b>yesterday</b>", "metrics": {}}),
                   json.dumps({"measured_on": "2026-10-10", "metrics": {"extraction_precision": {"value": "high"}}}),
                   json.dumps(["2026-10-10"])):
        (tmp_path / "metrics.json").write_text(broken, encoding="utf-8")
        with pytest.raises(metrics.MetricsError):
            metrics.load_metrics(tmp_path / "metrics.json")


def test_a_partial_run_names_the_parts_it_could_not_measure():
    # Run where the local data is missing (a builder's worktree has no library), the evaluation must not overwrite
    # the real numbers with empty ones: eval/run_eval.py writes the file only when nothing is missing.
    assert metrics.missing_parts(every_part()) == []
    parts = every_part()
    parts.end_to_end = None
    parts.extraction = None
    assert metrics.missing_parts(parts) == ["module 3 (gold set)", "end to end"]


def run_eval_module():
    """eval/run_eval.py, loaded as a module (it isn't in a package) without running it: nothing is evaluated."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_eval", metrics.METRICS_FILE.parent / "run_eval.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_run_eval_saves_a_complete_run_and_prints_its_runs_md_cells(tmp_path):
    path = tmp_path / "metrics.json"
    lines = run_eval_module()._metrics_lines(every_part(), date(2026, 10, 10), path)
    assert metrics.load_metrics(path).metrics["extraction_precision"].count == 45
    assert lines[-1].strip() == metrics.runs_cells(built())


def test_run_eval_never_overwrites_the_numbers_with_a_partial_run(tmp_path):
    path = tmp_path / "metrics.json"
    path.write_text("the real numbers", encoding="utf-8")
    parts = every_part()
    parts.end_to_end = None  # no library on this machine
    lines = run_eval_module()._metrics_lines(parts, date(2026, 10, 10), path)
    assert path.read_text(encoding="utf-8") == "the real numbers"
    assert "end to end" in lines[0]


# --- The same numbers for eval/RUNS.md ---

def test_the_runs_md_cells_carry_the_same_numbers_in_the_tables_column_order():
    cells = metrics.runs_cells(built())
    assert cells.split(" | ") == [
        "30/30 · 22/22 · 21/22",
        "fits 3/6, useful 5/6; ordering 75/79 (95%)",
        "library 2838/2838; shown 14/14, unverified shown 0",
        "votes 45/47 (96%)",
        "votes 45/45 (100%)",
        "voice high-vs-low 3/4 (75%), evidence long-vs-none 2/2 (100%)",
        "$0.00",
    ]


def test_runs_md_cells_say_n_a_for_what_was_not_measured():
    cells = metrics.runs_cells(metrics.build_metrics(metrics.EvalResults(), date(2026, 10, 10))).split(" | ")
    assert cells[:5] == ["n/a", "n/a", "n/a", "n/a", "n/a"]


def test_the_committed_metrics_have_their_run_logged_in_runs_md():
    # The brief: "Numbers on the page match eval/RUNS.md". The page reads eval/metrics.json; every run is logged in
    # eval/RUNS.md (a working rule), so a committed metrics file must have a RUNS.md entry on its date.
    loaded = metrics.load_metrics(metrics.METRICS_FILE)
    if loaded is None:
        pytest.skip("no eval/metrics.json yet: run eval/run_eval.py to make it")
    day = f"{loaded.measured_on.day} {loaded.measured_on:%b %Y}"
    runs = (metrics.METRICS_FILE.parent / "RUNS.md").read_text(encoding="utf-8")
    assert re.search(rf"^\| {day} \|", runs, re.MULTILINE), f"eval/RUNS.md has no row dated {day}"
