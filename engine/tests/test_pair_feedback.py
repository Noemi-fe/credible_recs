"""One answer of the pairwise test, kept like any feedback (engine/feedback.py parse_pair; Noemi, 20 Oct 2026): checked
as strictly as the other feedback, kept with the time it arrived and nothing about the sender, as its own kind
("blind_pair").

Every text is made up. No test reaches the network.
"""

import json
from datetime import UTC, datetime

import pytest

from engine import feedback

NOW = datetime(2026, 10, 24, 20, 15, 4, tzinfo=UTC)
PAIR = {"session": "k3j9x0a7q2m5p8w1", "question": "b01", "rival": "chatgpt", "ours_side": "A", "choice": "B",
        "why": "It explained what to avoid.", "language": "en", "answered_at": "2026-10-24T20:15:03.512Z"}


def test_an_answer_is_kept_with_its_fields_as_its_own_kind_and_the_time_it_arrived():
    record = feedback.parse_pair(PAIR, now=NOW)
    assert record == {"kind": "blind_pair", "session": "k3j9x0a7q2m5p8w1", "question": "b01", "rival": "chatgpt",
                      "ours_side": "A", "choice": "B", "why": "It explained what to avoid.", "language": "en",
                      "answered_at": "2026-10-24T20:15:03Z", "received_at": "2026-10-24T20:15:04Z"}


def test_the_kinds_of_the_other_feedback_are_unchanged_and_pairs_are_not_sent_there():
    assert feedback.KINDS == ("answer_feedback", "first_time")
    assert feedback.PAIR_KIND == "blind_pair"
    with pytest.raises(feedback.FeedbackError, match='"kind"'):
        feedback.parse_record({"kind": "blind_pair", **PAIR}, now=NOW)


def test_the_why_may_be_left_out_or_blank():
    without = {key: value for key, value in PAIR.items() if key != "why"}
    assert feedback.parse_pair(without, now=NOW)["why"] is None
    assert feedback.parse_pair({**PAIR, "why": "   "}, now=NOW)["why"] is None
    assert feedback.parse_pair({**PAIR, "why": None}, now=NOW)["why"] is None
    assert feedback.parse_pair({**PAIR, "why": "  spaced  "}, now=NOW)["why"] == "spaced"


def test_the_why_may_be_three_hundred_characters_and_not_more():
    assert feedback.PAIR_MAX_WHY_CHARS == 300
    assert feedback.parse_pair({**PAIR, "why": "長" * 300}, now=NOW)["why"] == "長" * 300
    with pytest.raises(feedback.FeedbackError, match="300"):
        feedback.parse_pair({**PAIR, "why": "長" * 301}, now=NOW)


@pytest.mark.parametrize("choice", ["A", "B", "same"])
def test_every_choice_is_kept(choice):
    assert feedback.parse_pair({**PAIR, "choice": choice}, now=NOW)["choice"] == choice


@pytest.mark.parametrize("rival, side, language", [("chatgpt", "A", "en"), ("vetted", "B", "it")])
def test_each_rival_side_and_language_is_kept(rival, side, language):
    record = feedback.parse_pair({**PAIR, "rival": rival, "ours_side": side, "language": language}, now=NOW)
    assert (record["rival"], record["ours_side"], record["language"]) == (rival, side, language)


@pytest.mark.parametrize("sent, words", [
    (["not", "an", "object"], "JSON object"),
    (None, "JSON object"),
    ({**PAIR, "kind": "blind_pair"}, "kind"),  # the server sets the kind
    ({**PAIR, "ip": "203.0.113.7"}, "ip"),  # nothing about the sender is ever taken in
    ({**PAIR, "user_agent": "Firefox"}, "user_agent"),
    ({**PAIR, "category": "kitchen"}, "category"),
    ({key: value for key, value in PAIR.items() if key != "session"}, "session"),
    ({key: value for key, value in PAIR.items() if key != "question"}, "question"),
    ({key: value for key, value in PAIR.items() if key != "rival"}, "rival"),
    ({key: value for key, value in PAIR.items() if key != "ours_side"}, "ours_side"),
    ({key: value for key, value in PAIR.items() if key != "choice"}, "choice"),
    ({key: value for key, value in PAIR.items() if key != "language"}, "language"),
    ({key: value for key, value in PAIR.items() if key != "answered_at"}, "answered_at"),
    ({**PAIR, "session": "short"}, '"session"'),
    ({**PAIR, "session": "a" * 65}, '"session"'),
    ({**PAIR, "session": "has spaces in it"}, '"session"'),
    ({**PAIR, "session": 12345678}, '"session"'),
    ({**PAIR, "question": "B 01!"}, '"question"'),
    ({**PAIR, "question": ""}, '"question"'),
    ({**PAIR, "question": 1}, '"question"'),
    ({**PAIR, "rival": "ours"}, '"rival"'),
    ({**PAIR, "rival": "bing"}, '"rival"'),
    ({**PAIR, "ours_side": "C"}, '"ours_side"'),
    ({**PAIR, "ours_side": "a"}, '"ours_side"'),
    ({**PAIR, "choice": "tie"}, '"choice"'),
    ({**PAIR, "choice": "b"}, '"choice"'),
    ({**PAIR, "choice": True}, '"choice"'),
    ({**PAIR, "why": ["a", "list"]}, '"why"'),
    ({**PAIR, "language": "fr"}, '"language"'),
    ({**PAIR, "answered_at": "yesterday"}, '"answered_at"'),
    ({**PAIR, "answered_at": "2026-13-45T25:61:61Z"}, '"answered_at"'),
    ({**PAIR, "answered_at": "2026-10-24T20:15:03+02:00"}, '"answered_at"'),
    ({**PAIR, "answered_at": 1761336903}, '"answered_at"'),
])
def test_an_answer_that_breaks_a_rule_is_refused_with_words_saying_why(sent, words):
    with pytest.raises(feedback.FeedbackError) as refused:
        feedback.parse_pair(sent, now=NOW)
    assert words in str(refused.value)


@pytest.mark.parametrize("stamp, kept", [("2026-10-24T20:15:03Z", "2026-10-24T20:15:03Z"),
                                         ("2026-10-24T20:15:03.5Z", "2026-10-24T20:15:03Z"),
                                         ("2026-10-24T20:15:03.999Z", "2026-10-24T20:15:03Z")])
def test_the_pages_timestamp_is_kept_to_the_second(stamp, kept):
    assert feedback.parse_pair({**PAIR, "answered_at": stamp}, now=NOW)["answered_at"] == kept


# --- Reading and summing up ---

def line(**changes) -> str:
    return json.dumps({"kind": "blind_pair", **PAIR, "received_at": "2026-10-24T20:15:04Z", **changes}) + "\n"


def test_reading_the_local_file_takes_in_pairs_and_the_other_kinds(tmp_path):
    path = tmp_path / "feedback.jsonl"
    path.write_text(line() + json.dumps({"kind": "first_time", "answer": "yes"}) + "\nnot json\n" + line(), encoding="utf-8")
    assert [r["kind"] for r in feedback.read_records([path])] == ["blind_pair", "first_time", "blind_pair"]


def test_reading_only_the_pairs_skips_everything_else(tmp_path):
    path = tmp_path / "feedback.jsonl"
    path.write_text(line() + json.dumps({"kind": "first_time", "answer": "yes"}) + "\n[1]\n" + line(session="otherone12345"),
                    encoding="utf-8")
    assert [r["session"] for r in feedback.read_pairs([path])] == ["k3j9x0a7q2m5p8w1", "otherone12345"]


def test_the_summary_counts_the_pairwise_answers_and_the_sessions_and_says_where_to_read_more():
    records = [json.loads(line()), json.loads(line(question="b04")), json.loads(line(session="otherone12345"))]
    text = feedback.summary(records)
    assert "Pairwise test: 3 answers from 2 sessions" in text and "tally-pairs" in text
    assert "Was this useful?" not in text  # no ratings among them: no line of zeros


def test_the_summary_keeps_its_other_lines_when_pairs_are_among_the_records():
    records = [{"kind": "first_time", "answer": "no", "received_at": "2026-10-12T10:30:00Z"}, json.loads(line())]
    text = feedback.summary(records)
    assert "First time here? 1 answered: 0 yes, 1 no" in text and "Pairwise test: 1 answer from 1 session" in text
