"""The end-to-end score: every blind-test question through the whole pipeline, counted, with no quote unchecked."""

import json

from engine.slice_eval import score_questions, slice_lines
from engine.tests.test_pipeline import REQUEST, library


def questions_file(tmp_path, texts):
    path = tmp_path / "questions.json"
    path.write_text(json.dumps({"questions": [{"id": f"b{n:02d}", "text": t} for n, t in enumerate(texts, 1)]}), encoding="utf-8")
    return path


def test_each_question_is_answered_and_counted(tmp_path):
    lib = library(tmp_path)
    results = score_questions(questions_file(tmp_path, [REQUEST, "best laptop for uni"]), lib)
    kettle, laptop = results
    assert (kettle.id, kettle.picks[:1], kettle.unverified) == ("b01", ["Zojirushi kettle"], 0)
    assert laptop.status == "out_of_scope" and laptop.picks == []


def test_the_summary_counts_full_answers_and_unverified_quotes(tmp_path):
    lines = slice_lines(score_questions(questions_file(tmp_path, [REQUEST]), library(tmp_path)))
    assert lines[0] == "1 question: 0 with 3 picks, 1 with at least 1 pick; unverified quotes shown: 0"
    assert lines[1].startswith("  b01 1 pick: Zojirushi kettle")


def test_each_question_counts_the_quotes_it_shows(tmp_path):
    from engine.answer import shown_quotes
    from engine.pipeline import answer_request

    lib = library(tmp_path)
    [result] = score_questions(questions_file(tmp_path, [REQUEST]), lib)
    shown = shown_quotes(answer_request(REQUEST, lib).answer)
    assert result.quotes_shown == len(shown) > 0


def test_the_section_gives_the_printed_text_and_the_results_it_came_from(tmp_path):
    from engine.slice_eval import slice_section

    text, results = slice_section(questions_file(tmp_path, [REQUEST]), library(tmp_path), profiles=None, live_checker=None)
    assert text.splitlines()[1].strip() == slice_lines(results)[0]
    assert [r.id for r in results] == ["b01"]
    assert slice_section(questions_file(tmp_path, [REQUEST]), tmp_path / "no library") == (
        "End to end (modules 1-7): skipped (no local library)", None)
