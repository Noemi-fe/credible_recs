"""The blind test's tooling (brief: "Blind test protocol"; built 10 Oct 2026 for week 3, 20-26 Oct).

Three steps, each a command: capture our answers on the day the rivals' answers are captured, build each tester's
packet with the three answers shuffled and named only A, B and C (the key kept apart), and tally the testers'
choices into a preference rate per rival. Every answer, tester and response here is made up, and every folder is a
temporary one.
"""

import csv
import json
from datetime import date
from pathlib import Path

import pytest

from engine import blind_test
from engine.blind_test import (
    BlindTestError,
    Tester,
    assign_questions,
    build_packets,
    capture,
    load_responses,
    load_testers,
    order_for,
    shown_from_ours,
    tally,
    tally_lines,
    write_shown_ours,
)

DAY = date(2026, 10, 20)
QUESTIONS = [
    {"id": "b01", "category": "skincare", "text": "gentle exfoliant for sensitive skin under £30"},
    {"id": "b02", "category": "skincare", "text": "sunscreen for oily skin"},
    {"id": "b06", "category": "kitchen", "text": "electric kettle that lasts 10+ years"},
    {"id": "b07", "category": "kitchen", "text": "first chef's knife under £100"},
]


def questions_file(tmp_path: Path, questions=QUESTIONS) -> Path:
    path = tmp_path / "questions.json"
    path.write_text(json.dumps({"questions": questions}), encoding="utf-8")
    return path


class FakeRun:
    def __init__(self, request: str):
        self.request = request
        self.answer = object()

    def text(self) -> str:
        return f"# Top picks for {self.request}\n\n1. Something good\n"


def fake_capture(tmp_path: Path, monkeypatch) -> Path:
    asked = []

    def answer(request, **kwargs):
        asked.append(request)
        return FakeRun(request)

    monkeypatch.setattr(blind_test, "answer_request", answer)
    monkeypatch.setattr(blind_test, "answer_to_dict", lambda answer: {"picks": ["Something good"]})
    folder = capture(questions_file(tmp_path), tmp_path / "answers", DAY)
    assert asked == [q["text"] for q in QUESTIONS]
    return folder


MARK = {"ours": "alpha", "vetted": "bravo", "chatgpt": "charlie"}  # a tool's name in an answer would give it away


def fill_shown(folder: Path, questions=QUESTIONS, text: str = "1. A product, because reasons.") -> None:
    for tool in blind_test.TOOLS:
        for q in questions:
            (folder / "shown" / tool / f"{q['id']}.md").write_text(f"{text} ({MARK[tool]} {q['id']})",
                                                                   encoding="utf-8")


# --- 1. Capture ---

def test_capture_saves_our_answers_and_empty_files_for_the_rivals(tmp_path, monkeypatch):
    folder = fake_capture(tmp_path, monkeypatch)
    assert folder == tmp_path / "answers" / "2026-10-20"
    for q in QUESTIONS:
        ours = (folder / "raw" / "ours" / f"{q['id']}.md").read_text(encoding="utf-8")
        assert ours.startswith(f"# Top picks for {q['text']}")
        assert json.loads((folder / "raw" / "ours" / f"{q['id']}.json").read_text(encoding="utf-8")) == {
            "picks": ["Something good"]}
        for rival in ("vetted", "chatgpt"):
            assert (folder / "raw" / rival / f"{q['id']}.md").read_text(encoding="utf-8") == ""
        for tool in blind_test.TOOLS:
            assert (folder / "shown" / tool / f"{q['id']}.md").read_text(encoding="utf-8") == ""
    assert (folder / "screenshots").is_dir()
    about = json.loads((folder / "capture.json").read_text(encoding="utf-8"))
    assert about["captured_on"] == "2026-10-20" and [q["id"] for q in about["questions"]] == ["b01", "b02", "b06",
                                                                                               "b07"]
    assert about["questions"][0]["text"] == QUESTIONS[0]["text"]  # the exact wording to give the rivals


def test_capture_never_overwrites_a_rivals_answer_already_pasted(tmp_path, monkeypatch):
    folder = fake_capture(tmp_path, monkeypatch)
    (folder / "raw" / "vetted" / "b01.md").write_text("Vetted's answer, pasted by hand", encoding="utf-8")
    capture(questions_file(tmp_path), tmp_path / "answers", DAY)
    assert (folder / "raw" / "vetted" / "b01.md").read_text(encoding="utf-8") == "Vetted's answer, pasted by hand"


def test_the_answers_folder_is_never_committed():
    # Our answers quote Reddit, and the rivals' answers and the testers' names aren't ours to publish.
    ignored = (Path(__file__).resolve().parents[2] / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "eval/blind_test/answers/" in ignored


# --- 1b. The answer testers see (Noemi's decision, 10 Oct 2026: eval/blind_test/FORMAT.md) ---

def quote(text: str, *badges: str) -> dict:
    return {"text": text, "comment_id": "c1aaaa", "url": "https://www.reddit.com/r/x/comments/1a/comment/c1aaaa",
            "badges": list(badges)}


def pick(rank: int, name: str, **overrides) -> dict:
    data = {"rank": rank, "product_key": f"kitchen:{name.lower()}", "name": name,
            "reason": "Recommended by 3 credible voices, 2 of them after long-term use",
            "support": "Backed by 1 high-credibility voice and 2 medium-credibility voices, across 2 threads",
            "quotes": [quote("Mine has lasted five years and still boils fast.", "account 9 years old", "five years of use"),
                       quote("Three years in, no rust at all.", "3 years of use"),
                       quote("A third quote that is never shown.", "short-term use")],
            "downsides": [], "breakdown": {"score": 2.5}, "score": 2.5,
            "price": {"text": "£45.00 at John Lewis, checked 10 Oct 2026", "amount": 45.0},
            "availability": {"text": "Sold at John Lewis, checked 10 Oct 2026"},
            "care": [{"tip": "Descale monthly.", "quote": quote("Descale it monthly.")}], "cautions": []}
    data.update(overrides)
    return data


def test_our_answer_is_shown_in_the_template_without_the_score_care_tips_or_support_line():
    shown = shown_from_ours({"picks": [pick(1, "Dualit Classic Kettle"), pick(2, "Sage Compact Kettle")],
                             "message": None})
    assert shown.startswith("**1. Dualit Classic Kettle**\n\nRecommended by 3 credible voices, 2 of them after "
                            "long-term use.")
    assert '"Mine has lasted five years and still boils fast." (five years of use)' in shown  # the evidence badge
    assert '"Three years in, no rust at all." (3 years of use)' in shown
    assert "A third quote" not in shown  # two pieces of evidence at most
    assert "Price: £45.00 at John Lewis" in shown and "checked" not in shown
    for dropped in ("Backed by", "Descale", "score", "Sold at", "reddit.com", "account 9 years old"):
        assert dropped not in shown
    assert "**2. Sage Compact Kettle**" in shown


def test_downsides_and_cautions_are_kept_and_an_unknown_price_is_left_out():
    shown = shown_from_ours({"picks": [pick(1, "OXO pan", downsides=[quote("The coating peeled after a year.")],
                                            cautions=["Note: we couldn't confirm it's PFAS-free."],
                                            price={"text": "Price not checked yet", "amount": None})]})
    assert 'Downside: "The coating peeled after a year."' in shown
    assert "Note: we couldn't confirm it's PFAS-free." in shown
    assert "Price" not in shown


def test_a_long_pick_is_cut_at_a_word_to_the_same_length_for_everyone():
    long_quote = " ".join(f"word{i}" for i in range(200))
    shown = shown_from_ours({"picks": [pick(1, "Long Kettle", quotes=[quote(long_quote, "five years of use")])]})
    assert blind_test.words_per_pick(shown) == [blind_test.BLIND_TEST_WORDS_PER_PICK]
    assert "…" in shown and "word0 word1" in shown  # cut from the end, so what's left is still word for word


def test_a_quote_shows_what_backs_it_or_nothing():
    shown = shown_from_ours({"picks": [pick(1, "Kettle", quotes=[
        quote("Upvoted and short.", "mentions flaws", "18 points, more than 86% of this thread's comments"),
        quote("No badge worth showing.", "mentions flaws")])]})
    assert '"Upvoted and short." (18 points, more than 86% of this thread\'s comments)' in shown
    assert '"No badge worth showing."\n' in shown + "\n" and "mentions flaws" not in shown


def test_a_part_that_would_be_cut_too_short_is_left_out_and_a_cut_quote_is_closed():
    reason = " ".join(["reason"] * 80)  # leaves 5 words, after the price line's 5
    shown = shown_from_ours({"picks": [pick(1, "Kettle", reason=reason)]})
    assert '"Mine has lasted' not in shown  # 5 words left: under MIN_CUT_WORDS, so the quote isn't cut to nothing
    long_downside = " ".join(f"w{i}" for i in range(100))
    shown = shown_from_ours({"picks": [pick(1, "Kettle", quotes=[], downsides=[quote(long_downside)])]})
    assert shown.count('"') % 2 == 0 and '…"' in shown


def test_a_quote_written_over_several_lines_is_shown_on_one():
    shown = shown_from_ours({"picks": [pick(1, "Kettle", quotes=[quote("I am on my second one in 13 years,\nSo not "
                                                                          "BIFL, but I bought it again.")])]})
    assert '"I am on my second one in 13 years, So not BIFL, but I bought it again."' in shown


def test_a_brand_picks_model_is_part_of_its_reason():
    shown = shown_from_ours({"picks": [pick(1, "Victorinox (their chef knives)", model="Victorinox Fibrox chef knife")]})
    assert "Most named model: Victorinox Fibrox chef knife. Recommended by 3 credible voices" in shown


def test_with_no_picks_our_answer_says_so_in_its_own_words():
    assert shown_from_ours({"picks": [], "message": "Not enough credible evidence to recommend a kettle yet."}) == (
        "Not enough credible evidence to recommend a kettle yet.")
    assert shown_from_ours(None) == "No answer."


def test_the_shown_command_writes_our_answers_and_leaves_the_rivals_alone(tmp_path, monkeypatch):
    folder = fake_capture(tmp_path, monkeypatch)
    for q in QUESTIONS:
        (folder / "raw" / "ours" / f"{q['id']}.json").write_text(json.dumps({"picks": [pick(1, "Dualit")]}),
                                                                encoding="utf-8")
    (folder / "shown" / "vetted" / "b01.md").write_text("**1. Something**\n\nIts reason.", encoding="utf-8")
    assert write_shown_ours(folder) == len(QUESTIONS)
    assert (folder / "shown" / "ours" / "b01.md").read_text(encoding="utf-8").startswith("**1. Dualit**")
    assert (folder / "shown" / "vetted" / "b01.md").read_text(encoding="utf-8") == "**1. Something**\n\nIts reason."


# --- 2. Packets ---

def test_testers_load_with_their_category(tmp_path):
    path = tmp_path / "testers.csv"
    path.write_text("tester,category\nT01,skincare\nT02,kitchen\nT03,any\n", encoding="utf-8")
    assert load_testers(path) == [Tester("T01", "skincare"), Tester("T02", "kitchen"), Tester("T03", "any")]


@pytest.mark.parametrize("content, problem", [
    ("tester,category\nT01,cooking\n", "line 2"),
    ("tester,category\nT01,skincare\nT01,kitchen\n", "T01"),
    ("name,category\nT01,skincare\n", "tester,category"),
    ("tester,category\n", "no testers"),
])
def test_a_broken_testers_file_is_refused_with_the_problem(tmp_path, content, problem):
    path = tmp_path / "testers.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(BlindTestError) as refused:
        load_testers(path)
    assert problem in str(refused.value)


def test_each_tester_gets_the_questions_of_their_category():
    testers = [Tester("T01", "skincare"), Tester("T02", "kitchen")]
    assert assign_questions(testers, QUESTIONS, per_tester=5) == {"T01": ["b01", "b02"], "T02": ["b06", "b07"]}


def test_a_tester_for_any_category_gets_the_questions_seen_least_so_far():
    testers = [Tester("T01", "skincare"), Tester("T02", "any"), Tester("T03", "any")]
    assigned = assign_questions(testers, QUESTIONS, per_tester=2)
    assert assigned["T01"] == ["b01", "b02"]
    assert assigned["T02"] == ["b06", "b07"]  # nobody has these yet
    assert assigned["T03"] == ["b01", "b02"]  # every question has one tester now: the file's order decides


def test_the_order_of_the_answers_is_balanced_across_testers():
    # Each of the six orders of the three tools comes up once in six testers, so no tool sits first more often.
    orders = [order_for(i, 0, seed=7) for i in range(6)]
    assert sorted(orders) == sorted(set(orders)) and len(set(orders)) == 6
    for position in range(3):
        assert {order[position] for order in orders} == set(blind_test.TOOLS)
    assert order_for(0, 0, seed=7) == order_for(0, 0, seed=7)  # the same seed gives the same packets


def test_packets_show_the_answers_as_a_b_and_c_and_the_key_says_which_is_which(tmp_path, monkeypatch):
    folder = fake_capture(tmp_path, monkeypatch)
    fill_shown(folder)
    testers = [Tester("T01", "skincare"), Tester("T02", "kitchen")]
    key = build_packets(folder, questions_file(tmp_path), testers, seed=1)
    packet = (folder / "packets" / "T01.md").read_text(encoding="utf-8")
    assert "gentle exfoliant for sensitive skin under £30" in packet and "electric kettle" not in packet
    assert "Which would you trust with your own money?" in packet and "1 to 5" in packet
    assert "And which would you trust least?" in packet  # every response ranks all three (10 Oct 2026)
    for letter in "ABC":
        assert f"### Answer {letter}" in packet
    first = packet.index("### Answer A")
    for letter, tool in key["T01"]["b01"].items():
        start = packet.index(f"### Answer {letter}", first)
        assert f"({MARK[tool]} b01)" in packet[start:start + 200]
    saved = json.loads((folder / "key.json").read_text(encoding="utf-8"))
    assert saved == key and set(saved["T02"]) == {"b06", "b07"}
    assert sorted(saved["T01"]["b01"].values()) == sorted(blind_test.TOOLS)


def test_packets_are_refused_while_an_answer_to_show_is_missing(tmp_path, monkeypatch):
    folder = fake_capture(tmp_path, monkeypatch)
    fill_shown(folder)
    (folder / "shown" / "chatgpt" / "b02.md").write_text("  \n", encoding="utf-8")
    with pytest.raises(BlindTestError) as refused:
        build_packets(folder, questions_file(tmp_path), [Tester("T01", "skincare")], seed=1)
    assert "shown/chatgpt/b02.md" in str(refused.value)
    assert not (folder / "packets").exists()


@pytest.mark.parametrize("giveaway", ["As ChatGPT, I suggest", "Vetted recommends", "credible recs picks",
                                      "OpenAI", "Generated by Claude"])
def test_packets_are_refused_when_an_answer_names_a_tool(tmp_path, monkeypatch, giveaway):
    # The brief's edge case: testers recognising a tool. Its name is the plainest giveaway.
    folder = fake_capture(tmp_path, monkeypatch)
    fill_shown(folder)
    (folder / "shown" / "vetted" / "b01.md").write_text(f"{giveaway} this exfoliant.", encoding="utf-8")
    with pytest.raises(BlindTestError) as refused:
        build_packets(folder, questions_file(tmp_path), [Tester("T01", "skincare")], seed=1)
    assert "shown/vetted/b01.md" in str(refused.value)


def test_packets_are_refused_when_a_pick_is_longer_than_the_others_may_be(tmp_path, monkeypatch):
    folder = fake_capture(tmp_path, monkeypatch)
    fill_shown(folder)
    too_long = " ".join(["word"] * (blind_test.BLIND_TEST_WORDS_PER_PICK + 1))
    (folder / "shown" / "chatgpt" / "b01.md").write_text(f"**1. A pan**\n\n{too_long}\n\n**2. B pan**\n\nShort.",
                                                          encoding="utf-8")
    with pytest.raises(BlindTestError) as refused:
        build_packets(folder, questions_file(tmp_path), [Tester("T01", "skincare")], seed=1)
    assert "shown/chatgpt/b01.md" in str(refused.value) and "pick 1" in str(refused.value)


# --- 3. Tally ---

def write_key(folder: Path, key: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "key.json").write_text(json.dumps(key), encoding="utf-8")


def write_responses(path: Path, rows: list[tuple]) -> Path:
    """Rows of (tester, question, choice, least, confidence, comment)."""
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["tester", "question", "choice", "least", "confidence", "comment"])
        writer.writerows(rows)
    return path


KEY = {
    "T01": {"b01": {"A": "ours", "B": "vetted", "C": "chatgpt"}, "b02": {"A": "chatgpt", "B": "ours", "C": "vetted"}},
    "T02": {"b01": {"A": "vetted", "B": "chatgpt", "C": "ours"}, "b02": {"A": "ours", "B": "chatgpt", "C": "vetted"}},
}


def test_the_tally_counts_how_often_ours_was_trusted_more_than_each_rival(tmp_path):
    # Each response ranks the three: its choice first, the least trusted last, the other in the middle. So each one
    # says whether ours was trusted more than Vetted's, and more than ChatGPT's (Noemi's decision, 10 Oct 2026).
    write_key(tmp_path, KEY)
    responses = write_responses(tmp_path / "responses.csv", [
        ("T01", "b01", "A", "C", 4, "real people who used it for years"),  # ours > vetted > chatgpt
        ("T01", "b02", "A", "C", 3, "clear list"),  # chatgpt > ours > vetted
        ("T02", "b01", "C", "A", 5, "the quotes"),  # ours > chatgpt > vetted
        ("T02", "b02", "C", "A", 2, ""),  # vetted > chatgpt > ours
    ])
    result = tally(tmp_path, load_responses(responses))
    assert result.choices == {"ours": 2, "vetted": 1, "chatgpt": 1}
    assert result.least == {"ours": 1, "vetted": 2, "chatgpt": 1}
    # Ours above vetted in 3 of 4 rankings; above chatgpt in 2 of 4.
    assert result.against["vetted"] == (3, 4) and result.against["chatgpt"] == (2, 4)
    assert result.confidence["ours"] == 4.5
    assert result.comments["ours"] == ["real people who used it for years", "the quotes"]
    lines = "\n".join(tally_lines(result))
    assert "against vetted: ours trusted more in 3 of 4 (75%)" in lines and "target 60%: met" in lines
    assert "against chatgpt: ours trusted more in 2 of 4 (50%)" in lines and "target 60%: not met" in lines
    assert "first choice: ours 2 of 4 (50%)" in lines


def test_a_response_the_key_doesnt_know_is_refused(tmp_path):
    write_key(tmp_path, KEY)
    for row, problem in [(("T09", "b01", "A", "B", 4, ""), "T09"), (("T01", "b07", "A", "B", 4, ""), "b07"),
                         (("T01", "b01", "D", "B", 4, ""), "choice"), (("T01", "b01", "A", "D", 4, ""), "least"),
                         (("T01", "b01", "A", "A", 4, ""), "least"), (("T01", "b01", "A", "B", 6, ""), "confidence")]:
        responses = write_responses(tmp_path / "responses.csv", [row])
        with pytest.raises(BlindTestError) as refused:
            tally(tmp_path, load_responses(responses))
        assert problem in str(refused.value) and "line 2" in str(refused.value)


def test_a_tester_answering_the_same_question_twice_is_refused(tmp_path):
    write_key(tmp_path, KEY)
    responses = write_responses(tmp_path / "responses.csv", [("T01", "b01", "A", "B", 4, ""),
                                                             ("T01", "b01", "B", "A", 3, "")])
    with pytest.raises(BlindTestError) as refused:
        tally(tmp_path, load_responses(responses))
    assert "line 3" in str(refused.value)


def test_with_few_choices_the_tally_gives_a_range_not_just_a_rate(tmp_path):
    # 50 rankings is a small sample: the report gives the 95% range (Wilson) so 62% isn't read as a sure win.
    write_key(tmp_path, KEY)
    responses = write_responses(tmp_path / "responses.csv", [("T01", "b01", "A", "C", 4, ""),
                                                             ("T02", "b02", "C", "A", 2, "")])
    lines = "\n".join(tally_lines(tally(tmp_path, load_responses(responses))))
    assert "95% range" in lines


def test_responses_without_the_least_trusted_column_are_refused(tmp_path):
    path = tmp_path / "responses.csv"
    path.write_text("tester,question,choice,confidence,comment\nT01,b01,A,4,\n", encoding="utf-8")
    with pytest.raises(BlindTestError) as refused:
        load_responses(path)
    assert "least" in str(refused.value)


# --- The command line ---

def test_command_line_explains_itself_when_used_wrongly(capsys):
    assert blind_test.main([]) == 2
    out = capsys.readouterr().out
    for command in ("capture", "shown", "packets", "tally"):
        assert f"python -m engine.blind_test {command}" in out
