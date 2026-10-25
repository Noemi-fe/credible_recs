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
# What the page sends: never the rival or the side, which the server works out from the visit's id (25 Oct 2026).
PAIR = {"session": "k3j9x0a7q2m5p8w1", "question": "b01", "choice": "B",
        "why": "It explained what to avoid.", "language": "en", "answered_at": "2026-10-24T20:15:03.512Z"}


def sides(session, question):
    """The server's lookup (engine/pair_test.py sides_of), made up: every question is chatgpt's, with ours on side A."""
    return "chatgpt", "A"


def parse(data, **more):
    return feedback.parse_pair(data, sides=more.pop("sides", sides), now=NOW, **more)


def test_an_answer_is_kept_with_its_fields_as_its_own_kind_and_the_time_it_arrived():
    record = parse(PAIR)
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
    assert parse(without)["why"] is None
    assert parse({**PAIR, "why": "   "})["why"] is None
    assert parse({**PAIR, "why": None})["why"] is None
    assert parse({**PAIR, "why": "  spaced  "})["why"] == "spaced"


def test_the_why_may_be_three_hundred_characters_and_not_more():
    assert feedback.PAIR_MAX_WHY_CHARS == 300
    assert parse({**PAIR, "why": "長" * 300})["why"] == "長" * 300
    with pytest.raises(feedback.FeedbackError, match="300"):
        parse({**PAIR, "why": "長" * 301})


@pytest.mark.parametrize("choice", ["A", "B", "same"])
def test_every_choice_is_kept(choice):
    assert parse({**PAIR, "choice": choice})["choice"] == choice


@pytest.mark.parametrize("rival, side, language", [("chatgpt", "A", "en"), ("vetted", "B", "it")])
def test_the_rival_and_side_are_the_servers_and_the_language_the_pages(rival, side, language):
    record = parse({**PAIR, "language": language}, sides=lambda session, question: (rival, side))
    assert (record["rival"], record["ours_side"], record["language"]) == (rival, side, language)


def test_the_server_is_asked_for_the_rival_and_side_of_the_visit_and_question_sent():
    asked = []

    def lookup(session, question):
        asked.append((session, question))
        return "vetted", "B"

    parse({**PAIR, "question": "b04"}, sides=lookup)
    assert asked == [("k3j9x0a7q2m5p8w1", "b04")]


def test_an_answer_for_a_question_not_in_the_visits_deck_is_refused_with_words_saying_so():
    with pytest.raises(feedback.FeedbackError, match='"question" b01 is not one of this visit'):
        parse(PAIR, sides=lambda session, question: None)


@pytest.mark.parametrize("name, value", [("rival", "chatgpt"), ("ours_side", "A")])
def test_the_page_may_not_send_the_rival_or_the_side_it_must_not_know(name, value):
    with pytest.raises(feedback.FeedbackError, match=name):
        parse({**PAIR, name: value})


@pytest.mark.parametrize("sent, words", [
    (["not", "an", "object"], "JSON object"),
    (None, "JSON object"),
    ({**PAIR, "kind": "blind_pair"}, "kind"),  # the server sets the kind
    ({**PAIR, "ip": "203.0.113.7"}, "ip"),  # nothing about the sender is ever taken in
    ({**PAIR, "user_agent": "Firefox"}, "user_agent"),
    ({**PAIR, "category": "kitchen"}, "category"),
    ({key: value for key, value in PAIR.items() if key != "session"}, "session"),
    ({key: value for key, value in PAIR.items() if key != "question"}, "question"),
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
        parse(sent)
    assert words in str(refused.value)


@pytest.mark.parametrize("stamp, kept", [("2026-10-24T20:15:03Z", "2026-10-24T20:15:03Z"),
                                         ("2026-10-24T20:15:03.5Z", "2026-10-24T20:15:03Z"),
                                         ("2026-10-24T20:15:03.999Z", "2026-10-24T20:15:03Z")])
def test_the_pages_timestamp_is_kept_to_the_second(stamp, kept):
    assert parse({**PAIR, "answered_at": stamp})["answered_at"] == kept


# --- Reading and summing up ---

def line(**changes) -> str:
    stored = {"kind": "blind_pair", **PAIR, "rival": "chatgpt", "ours_side": "A", "received_at": "2026-10-24T20:15:04Z"}
    return json.dumps({**stored, **changes}) + "\n"


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
