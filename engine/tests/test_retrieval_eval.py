"""Scoring module 2's ranking against hand-graded thread relevance (Noemi's grades, 7 Oct 2026):
2 fits the need, 1 useful evidence about the product type, 0 off-topic."""

import json

from engine.retrieval_eval import load_judgements, score_ordering, score_ranking, summary_lines


def write_judgements(tmp_path):
    path = tmp_path / "retrieval.json"
    path.write_text(json.dumps({"approved": True, "judgements": [
        {"question": "b01", "post": "1fits", "grade": 2, "why": "asks for exfoliant advice for sensitive skin"},
        {"question": "b01", "post": "1useful", "grade": 1, "why": "long-term use of an exfoliant, other skin type"},
        {"question": "b01", "post": "1off", "grade": 0, "why": "about something else"},
        {"question": "b01", "post": "1off2", "grade": 0, "why": "about something else"},
    ]}))
    return path


def test_grades_are_loaded(tmp_path):
    assert load_judgements(write_judgements(tmp_path))[("b01", "1useful")] == 1


def test_top_three_counts_each_grade_and_the_unjudged(tmp_path):
    judgements = load_judgements(write_judgements(tmp_path))
    scores = score_ranking({"b01": ["1fits", "1new", "1off", "1useful"]}, judgements)
    assert scores == {"b01": {2: 1, 1: 0, 0: 1, None: 1}}


def test_ordering_checks_every_useful_thread_against_every_off_topic_one(tmp_path):
    judgements = load_judgements(write_judgements(tmp_path))
    # 1fits is above both off-topic threads; 1useful is above one of them: 3 of 4 pairs in the right order.
    assert score_ordering({"b01": ["1fits", "1off", "1useful", "1off2"]}, judgements) == (3, 4)


def test_summary_reads_plainly(tmp_path):
    judgements = load_judgements(write_judgements(tmp_path))
    ranked = {"b01": ["1fits", "1useful", "1off", "1off2"]}
    lines = summary_lines(score_ranking(ranked, judgements), score_ordering(ranked, judgements))
    assert lines[0] == "top 3, fits the need (grade 2): 1/3 judged (33%); useful (grade 1 or 2): 2/3 (67%); 0 not judged yet; 1 questions"
    assert lines[1] == "ordering, useful above off-topic: 4/4 pairs (100%)"


def test_a_judged_thread_left_out_of_the_ranking_counts_as_ranked_last(tmp_path):
    # A useful thread the ranking drops is a miss; an off-topic one it drops is rightly below every useful one.
    judgements = load_judgements(write_judgements(tmp_path))
    pool = {"b01": ["1fits", "1useful", "1off", "1off2"]}
    # 1useful is dropped: it loses to 1off, and ties with the also-dropped 1off2, which counts as wrong too.
    assert score_ordering({"b01": ["1fits", "1off"]}, judgements, pool) == (2, 4)
