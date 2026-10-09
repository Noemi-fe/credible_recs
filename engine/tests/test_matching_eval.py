"""Scoring module 4 against labelled same-or-different pairs of product names, and the library summary.

Pairs files are written to tmp_path; no test reads data/.
"""

import json

import pytest

from engine.extract import CheckResult, ExtractedMention
from engine.matching_eval import (
    DEFAULT_PAIRS,
    MatchingPairError,
    library_lines,
    load_pairs,
    matching_report,
    report_lines,
    score_pairs,
)
from engine.match_products import make_aliases

NO_ALIASES = {"skincare": {}, "kitchen": {}, "other": {}}


def pair(pair_id, a, b, same, category="skincare", edge_case="spelling"):
    return {"id": pair_id, "a": a, "b": b, "category": category, "same": same, "edge_case": edge_case, "note": ""}


PAIRS = [
    pair("m01", "CeraVe SA Cleanser", "cerave sa cleanser", True),
    pair("m02", "CeraVe SA Cleanser", "CeraVe Hydrating Cleanser", False, edge_case="different product"),
    pair("m03", "TO lactic acid", "The Ordinary Lactic Acid", True, edge_case="abbreviation"),
    pair("m04", "Timemore C2", "Timemore C2 Max", False, "kitchen", "model variant"),
]


def write_pairs(tmp_path, pairs=PAIRS, approved=False):
    path = tmp_path / "matching.json"
    path.write_text(json.dumps({"approved": approved, "approved_note": "draft", "pairs": pairs}))
    return path


def test_pairs_and_approval_are_loaded(tmp_path):
    loaded = load_pairs(write_pairs(tmp_path))
    assert loaded.approved is False
    assert [p.id for p in loaded.pairs] == ["m01", "m02", "m03", "m04"]


def test_a_pair_id_used_twice_is_refused(tmp_path):
    with pytest.raises(MatchingPairError, match="m01"):
        load_pairs(write_pairs(tmp_path, PAIRS + [PAIRS[0]]))


def test_a_malformed_pair_is_refused(tmp_path):
    with pytest.raises(MatchingPairError):
        load_pairs(write_pairs(tmp_path, [{"id": "m01", "a": "x", "b": "y", "same": "maybe"}]))


def test_each_pair_is_scored_with_its_categorys_short_names(tmp_path):
    pairs = load_pairs(write_pairs(tmp_path)).pairs
    without = score_pairs(pairs, NO_ALIASES)
    assert [r.right for r in without] == [True, True, False, True]  # "TO" can't be read without the list
    with_list = score_pairs(pairs, {**NO_ALIASES, "skincare": make_aliases({"TO": "The Ordinary"})})
    assert all(r.right for r in with_list)


def test_the_report_gives_the_score_against_the_target_and_lists_the_misses(tmp_path):
    loaded = load_pairs(write_pairs(tmp_path))
    lines = report_lines(loaded, score_pairs(loaded.pairs, NO_ALIASES))
    assert "DRAFT" in lines[0]
    assert "3/4 right (75%)" in lines[1] and "target 90%" in lines[1]
    assert any("abbreviation: 0/1" in line for line in lines)
    assert any("m03" in line and "TO lactic acid" in line and "said different" in line for line in lines)


def test_the_shipped_pairs_file_loads_and_is_a_draft_until_noemi_approves_it():
    loaded = load_pairs(DEFAULT_PAIRS)
    assert len(loaded.pairs) >= 50
    assert {p.category for p in loaded.pairs} <= {"skincare", "kitchen", "other"}
    assert loaded.approved or "Noemi" in loaded.approved_note


# --- The library summary ---

def checked(*names_by_thread):
    """{thread id: CheckResult} with one kept skincare mention per name."""
    return {
        f"1fake0{t}": CheckResult(kept=[
            ExtractedMention(comment_id=f"c{t}{i}", product=name, category="skincare", stance="recommend", quote="q")
            for i, name in enumerate(names)
        ])
        for t, names in enumerate(names_by_thread, start=1)
    }


def test_the_library_summary_counts_groups_and_names_the_loose_ones():
    lines = library_lines(checked(["CeraVe", "CeraVe SA Cleanser"], ["cerave sa cleanser", "CeraVe Hydrating Cleanser"]),
                          NO_ALIASES)
    assert lines[0] == "library: 4 mentions in 2 threads -> 3 product groups, 1 loose (a brand or line, not one product)"
    assert any("CeraVe SA Cleanser" in line and "2 mentions" in line for line in lines)
    assert any("loose" in line and "CeraVe" in line for line in lines[1:])


def test_the_library_summary_lists_merges_to_check():
    # A misspelling joined the group, and a much shorter name was taken to be this product: both are worth a look.
    lines = library_lines(checked(["Baratza Encore", "Barratza Encore", "Sunday Riley", "Sunday Riley Tidal Brightening Water Cream"]),
                          NO_ALIASES)
    to_check = [line for line in lines if line.strip().startswith("to check")]
    assert any("Baratza Encore" in line and "Barratza Encore" in line for line in to_check)
    assert any("Sunday Riley Tidal Brightening Water Cream" in line and "Sunday Riley," not in line for line in to_check)


def test_the_report_skips_the_library_when_there_is_none(tmp_path):
    report = matching_report(write_pairs(tmp_path), tmp_path / "no library")
    assert report.startswith("Module 4, product matching")
    assert "library: skipped" in report
