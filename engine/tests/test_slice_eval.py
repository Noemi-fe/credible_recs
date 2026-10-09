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
