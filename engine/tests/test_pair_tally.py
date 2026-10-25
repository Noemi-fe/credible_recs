"""The pairwise test's tally (engine/blind_test.py, `tally-pairs`; Noemi, 20 Oct 2026): per rival, how often ours was
preferred, the rival was preferred, or neither, with a 95% range, and per category too. Read from a responses file or
from the dataset's export (a folder of batch files).

Every row is made up. No test reaches the network.
"""

import json

import pytest

from engine import blind_test
from engine.tests.pair_factories import made_up_cards, write_cards

CATEGORY_OF = {"b01": "skincare", "b06": "kitchen", "r01": "other"}


def row(session: str, question: str, rival: str, ours_side: str, choice: str, why: str | None = None, **more) -> dict:
    return {"kind": "blind_pair", "session": session, "question": question, "rival": rival, "ours_side": ours_side,
            "choice": choice, "why": why, "language": "en", "answered_at": "2026-10-24T20:15:03Z",
            "received_at": "2026-10-24T20:15:04Z", **more}


# Against chatgpt: ours preferred twice (A when ours is A, B when ours is B), the rival once, one "same".
# Against vetted: ours preferred once, the rival twice.
ROWS = [
    row("s1aaaaaaaa", "b01", "chatgpt", "A", "A"),
    row("s1aaaaaaaa", "b06", "chatgpt", "B", "B", "clearer reasons"),
    row("s1aaaaaaaa", "r01", "vetted", "A", "B", "gave actual products"),
    row("s2bbbbbbbb", "b01", "chatgpt", "B", "A", "liked the first"),
    row("s2bbbbbbbb", "b06", "chatgpt", "A", "same"),
    row("s2bbbbbbbb", "r01", "vetted", "B", "B"),
    row("s3cccccccc", "b01", "vetted", "A", "B"),
]


def tally(rows=ROWS, categories=CATEGORY_OF):
    return blind_test.tally_pairs(rows, categories)


def counts(c: blind_test.PairCounts) -> tuple[int, int, int]:
    return c.ours, c.rival, c.same


def test_each_answer_is_ours_preferred_the_rival_preferred_or_the_same():
    result = tally()
    assert counts(result.by_rival["chatgpt"]) == (2, 1, 1)
    assert counts(result.by_rival["vetted"]) == (1, 2, 0)
    assert counts(result.overall) == (3, 3, 1)
    assert (result.answers, result.sessions, result.repeats, result.skipped) == (7, 3, 0, 0)


def test_the_side_ours_was_on_decides_who_was_preferred_not_the_letter():
    # The letter A chosen is ours when ours was on A, and the rival's when ours was on B.
    assert counts(tally([row("s1aaaaaaaa", "b01", "vetted", "A", "A")]).overall) == (1, 0, 0)
    assert counts(tally([row("s1aaaaaaaa", "b01", "vetted", "B", "A")]).overall) == (0, 1, 0)
    assert counts(tally([row("s1aaaaaaaa", "b01", "vetted", "B", "B")]).overall) == (1, 0, 0)
    assert counts(tally([row("s1aaaaaaaa", "b01", "vetted", "A", "B")]).overall) == (0, 1, 0)


def test_the_same_by_category_for_each_rival():
    by = tally().by_category
    assert counts(by["chatgpt"]["skincare"]) == (1, 1, 0)
    assert counts(by["chatgpt"]["kitchen"]) == (1, 0, 1)
    assert counts(by["vetted"]["other"]) == (1, 1, 0)
    assert counts(by["vetted"]["skincare"]) == (0, 1, 0)
    assert "other" not in by["chatgpt"]  # no answer, no row


def test_the_ranges_are_wilsons_95_percent_ranges():
    counts_ = blind_test.PairCounts(ours=3, rival=1, same=1)
    low, high = blind_test.wilson_range(3, 5)
    assert f"3 ({3 / 5:.0%}, 95% range {low:.0%} to {high:.0%})" in blind_test.pair_counts_text(counts_, "chatgpt")


def test_one_answer_a_question_for_a_session_and_the_last_one_counts():
    rows = [row("s1aaaaaaaa", "b01", "chatgpt", "A", "B"), row("s1aaaaaaaa", "b01", "chatgpt", "A", "A"),
            row("s1aaaaaaaa", "b06", "vetted", "A", "same")]
    result = tally(rows)
    assert counts(result.overall) == (1, 0, 1) and result.answers == 2 and result.repeats == 1


def test_the_same_question_from_two_sessions_counts_twice():
    rows = [row("s1aaaaaaaa", "b01", "chatgpt", "A", "A"), row("s2bbbbbbbb", "b01", "chatgpt", "A", "A")]
    assert tally(rows).answers == 2


def test_rows_that_are_not_pair_answers_are_skipped_and_counted():
    rows = [ROWS[0], row("s1aaaaaaaa", "b06", "bing", "A", "A"), row("s1aaaaaaaa", "b06", "vetted", "C", "A"),
            row("s1aaaaaaaa", "r01", "vetted", "A", "tie"), {"kind": "blind_pair", "session": "s9"}]
    result = tally(rows)
    assert result.answers == 1 and result.skipped == 4


def test_without_the_cards_the_categories_are_left_out_and_the_report_says_so():
    result = tally(categories=None)
    assert result.by_category == {} and counts(result.overall) == (3, 3, 1)
    assert "categories not shown" in "\n".join(blind_test.pair_tally_lines(result))


def test_a_question_the_cards_do_not_know_is_counted_in_unknown():
    result = tally([row("s1aaaaaaaa", "z99", "chatgpt", "A", "A")])
    assert counts(result.by_category["chatgpt"]["unknown"]) == (1, 0, 0)


def test_the_report_gives_each_rival_its_shares_with_ranges_and_the_categories():
    lines = "\n".join(blind_test.pair_tally_lines(tally()))
    assert "7 answers from 3 sessions" in lines
    assert "against chatgpt, 4 answers" in lines and "against vetted, 3 answers" in lines
    assert "ours preferred 2 (50%, 95% range 15% to 85%)" in lines
    assert "chatgpt preferred 1 (25%, 95% range 5% to 70%)" in lines
    assert "about the same 1 (25%, 95% range 5% to 70%)" in lines
    assert "skincare, 2 answers" in lines and "kitchen, 2 answers" in lines
    assert "both rivals together, 7 answers" in lines


def test_the_report_gives_the_share_of_the_answers_that_picked_a_side():
    lines = "\n".join(blind_test.pair_tally_lines(tally()))
    assert "when a side was picked, ours 2 of 3 (67%" in lines  # against chatgpt


def test_the_reasons_are_listed_by_what_was_preferred_without_who_gave_them():
    lines = "\n".join(blind_test.pair_tally_lines(tally()))
    assert "clearer reasons" in lines and "gave actual products" in lines and "liked the first" in lines
    assert lines.index("clearer reasons") < lines.index("gave actual products")  # ours first, then the rival
    assert "s1aaaaaaaa" not in lines and "s2bbbbbbbb" not in lines


def test_the_report_with_no_answers_says_so():
    assert blind_test.pair_tally_lines(tally([])) == ["No pairwise answers yet."]


# --- Reading the file or the dataset's export ---

def write_lines(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def test_a_responses_file_is_read_and_other_kinds_and_broken_lines_are_left_out(tmp_path):
    path = tmp_path / "feedback.jsonl"
    path.write_text(json.dumps({"kind": "first_time", "answer": "yes"}) + "\nnot json\n[1]\n"
                    + "".join(json.dumps(r) + "\n" for r in ROWS), encoding="utf-8")
    assert len(blind_test.load_pair_records(path)) == len(ROWS)


def test_the_datasets_export_is_a_folder_of_batch_files_read_in_order(tmp_path):
    export = tmp_path / "downloaded" / "noemi__feedback"
    # The later batch holds the visitor's second answer to b01: it wins, whatever order the files are listed in.
    write_lines(export / "feedback" / "2026-10-24T200000Z-aaaa1111.jsonl", [row("s1aaaaaaaa", "b01", "chatgpt", "A", "B")])
    write_lines(export / "feedback" / "2026-10-24T210000Z-bbbb2222.jsonl", [row("s1aaaaaaaa", "b01", "chatgpt", "A", "A"),
                                                                           row("s2bbbbbbbb", "b06", "vetted", "A", "A")])
    (export / "feedback" / "readme.txt").write_text("not a batch", encoding="utf-8")
    records = blind_test.load_pair_records(export)
    assert [(r["session"], r["choice"]) for r in records] == [("s1aaaaaaaa", "B"), ("s1aaaaaaaa", "A"), ("s2bbbbbbbb", "A")]
    assert counts(tally(records).overall) == (2, 0, 0)


def test_a_path_that_is_not_there_is_an_error_with_words(tmp_path):
    with pytest.raises(blind_test.BlindTestError, match="nothing.jsonl"):
        blind_test.load_pair_records(tmp_path / "nothing.jsonl")


# --- The command ---

def test_the_command_prints_the_report_for_a_file_and_the_cards(tmp_path, capsys):
    cards = made_up_cards()
    folder = write_cards(tmp_path / "library", cards)
    rows = [row("s1aaaaaaaa", "b01", "chatgpt", "A", "A"), row("s1aaaaaaaa", "b06", "vetted", "B", "A")]
    write_lines(tmp_path / "responses.jsonl", rows)
    assert blind_test.main(["tally-pairs", str(tmp_path / "responses.jsonl"), "--cards",
                            str(folder / "blind_test_cards.json")]) == 0
    out = capsys.readouterr().out
    assert "2 answers from 1 session" in out and "skincare, 1 answer" in out and "kitchen, 1 answer" in out


def test_the_command_reads_the_local_store_when_no_file_is_named(tmp_path, monkeypatch, capsys):
    from engine import feedback

    write_lines(tmp_path / "feedback.jsonl", ROWS)
    monkeypatch.setattr(feedback, "DEFAULT_FILE", tmp_path / "feedback.jsonl")
    monkeypatch.setattr(blind_test.pair_test, "cards_file", lambda: tmp_path / "no cards.json")
    assert blind_test.main(["tally-pairs"]) == 0
    out = capsys.readouterr().out
    assert "7 answers from 3 sessions" in out and "categories not shown" in out


def test_the_command_with_no_answers_or_no_file_says_so(tmp_path, capsys):
    write_lines(tmp_path / "empty.jsonl", [])
    assert blind_test.main(["tally-pairs", str(tmp_path / "empty.jsonl")]) == 0
    assert "No pairwise answers yet." in capsys.readouterr().out
    assert blind_test.main(["tally-pairs", str(tmp_path / "missing.jsonl")]) == 1
    assert "missing.jsonl" in capsys.readouterr().out


def test_the_command_with_a_bad_cards_file_says_so_and_still_reports_without_categories(tmp_path, capsys):
    write_lines(tmp_path / "responses.jsonl", ROWS)
    (tmp_path / "cards.json").write_text("{", encoding="utf-8")
    assert blind_test.main(["tally-pairs", str(tmp_path / "responses.jsonl"), "--cards", str(tmp_path / "cards.json")]) == 0
    out = capsys.readouterr().out
    assert "categories not shown" in out and "cards.json" in out


def test_the_older_commands_still_work_and_the_usage_lists_the_new_one(capsys):
    assert blind_test.main([]) == 2
    assert "tally-pairs" in capsys.readouterr().out
