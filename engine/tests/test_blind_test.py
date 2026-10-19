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
    # Changed on purpose 17 Oct 2026 (the converge round, item 7): a downside is no longer cut at a word, only at the end
    # of a sentence that keeps its point (engine/tests/test_blind_test_cuts.py), so the cut quote closed here is a piece
    # of evidence, and a long downside with no sentence end is left out.
    long_quote = " ".join(f"w{i}" for i in range(100))
    shown = shown_from_ours({"picks": [pick(1, "Kettle", quotes=[quote(long_quote)])]})
    assert shown.count('"') % 2 == 0 and '…"' in shown
    shown = shown_from_ours({"picks": [pick(1, "Kettle", quotes=[], downsides=[quote(long_quote)])]})
    assert "Downside" not in shown


def test_a_quote_written_over_several_lines_is_shown_on_one():
    shown = shown_from_ours({"picks": [pick(1, "Kettle", quotes=[quote("This is my second one in 12 years,\nso "
                                                                          "not quite BIFL, but I'd buy it again.")])]})
    assert '"This is my second one in 12 years, so not quite BIFL, but I\'d buy it again."' in shown


def test_a_link_in_our_quote_becomes_a_label_as_for_every_tool():
    # FORMAT.md rule 4 ("Links become labels"), the same for all three: found in b10's OXO quote, 10 Oct 2026 (late),
    # which showed a markdown link to a shop.
    shown = shown_from_ours({"picks": [pick(1, "Acme pan", quotes=[
        quote("A cooking magazine recommends the [Acme pan](https://example.com/acme-pan)."),
        quote("See <https://example.com/review> for the test.")])]})
    assert '"A cooking magazine recommends the Acme pan (source)."' in shown
    assert '"See (source) for the test."' in shown
    assert "http" not in shown


def test_a_brand_picks_model_is_part_of_its_reason():
    # Changed on purpose 12 Oct 2026 (Noemi's wording): a brand pick is shown as the brand's line, in the blind-test
    # view too ("Victorinox chef knife line"; it was "Victorinox (their chef knives)").
    shown = shown_from_ours({"picks": [pick(1, "Victorinox chef knife line", model="Victorinox Fibrox chef knife")]})
    assert shown.startswith("**1. Victorinox chef knife line**")
    assert "Most named model: Victorinox Fibrox chef knife. Recommended by 3 credible voices" in shown


def test_our_why_is_the_picks_one_line_summary_and_its_reason_line_only_without_one():
    # Noemi's decision (m) of 19 Oct 2026: in the packets a pick's "why" is its one-line summary, what its voices say
    # of it; the reason line ("Recommended by 3 credible voices...") counts voices, as the support line rule 6 drops.
    summary = {"text": "Owners say it boils fast and still works after years of daily use.", "sources": []}
    shown = shown_from_ours({"picks": [pick(1, "Dualit Classic Kettle", summary=summary)]})
    assert shown.startswith("**1. Dualit Classic Kettle**\n\nOwners say it boils fast and still works after years of "
                            "daily use.\n\n")
    assert "Recommended by" not in shown
    assert blind_test.words_per_pick(shown)[0] <= blind_test.BLIND_TEST_WORDS_PER_PICK
    for missing in (None, {"text": "", "sources": []}):
        assert "Recommended by 3 credible voices" in shown_from_ours({"picks": [pick(1, "Kettle", summary=missing)]})
    shown = shown_from_ours({"picks": [pick(1, "Victorinox chef knife line", model="Victorinox Fibrox chef knife",
                                            summary={"text": "Cooks say it stays sharp for years.", "sources": []})]})
    assert "Most named model: Victorinox Fibrox chef knife. Cooks say it stays sharp for years." in shown
    long_summary = {"text": " ".join(f"word{i}" for i in range(120)), "sources": []}
    shown = shown_from_ours({"picks": [pick(1, "Long Kettle", summary=long_summary)]})
    assert blind_test.words_per_pick(shown) == [blind_test.BLIND_TEST_WORDS_PER_PICK]  # within FORMAT.md's 90 words


def test_a_pick_sold_second_hand_only_says_so():
    shown = shown_from_ours({"picks": [pick(1, "Griswold cast iron skillet line",  # the line's name: 12 Oct 2026
                                            availability={"text": "Sold second-hand only: eBay UK, checked 10 Oct 2026",
                                                          "second_hand": True})]})
    assert "Sold second-hand only." in shown and "eBay" not in shown


NOT_IN_UK = {"text": "Not sold in the UK, checked 15 Oct 2026", "available": False, "shop": None, "url": None,
             "checked_on": "2026-10-15", "second_hand": False}
PRESCRIPTION = "Prescription-only in the UK: ask a doctor or pharmacist."


def test_a_pick_not_sold_in_the_uk_keeps_its_note_with_the_day_it_was_checked():
    # Noemi's decision 7 of 16 Oct 2026: as a pick sold second-hand only says so (10 Oct 2026), one sold only outside the
    # UK says so in the packets too (b06's and b09's third picks would have lost it), with the day it was checked.
    shown = shown_from_ours({"picks": [pick(1, "Cuisinart CPK-17", availability=NOT_IN_UK)]})
    assert "\n\nNot sold in the UK, checked 15 Oct 2026.\n\nPrice: £45.00 at John Lewis" in shown


def test_a_prescription_only_pick_keeps_its_note():
    shown = shown_from_ours({"picks": [pick(1, "Finacea", prescription=PRESCRIPTION)]})
    assert f"\n\n{PRESCRIPTION}\n\nPrice:" in shown
    assert PRESCRIPTION not in shown_from_ours({"picks": [pick(1, "Finacea", prescription=None)]})


def test_the_notes_are_kept_whole_within_the_words_a_pick_may_have():
    long_quote = " ".join(f"word{i}" for i in range(200))
    shown = shown_from_ours({"picks": [pick(1, "Finacea", quotes=[quote(long_quote, "2 years of use")],
                                            cautions=["Note: we couldn't confirm it's fragrance-free."],
                                            availability=NOT_IN_UK, prescription=PRESCRIPTION)]})
    for note in ("Note: we couldn't confirm it's fragrance-free.", "Not sold in the UK, checked 15 Oct 2026.",
                 PRESCRIPTION):
        assert note in shown
    assert blind_test.words_per_pick(shown) == [90]  # FORMAT.md's limit: the quote is cut, never a note


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


def test_each_packet_is_also_a_plain_web_page_testers_can_open(tmp_path, monkeypatch):
    # Testers shouldn't have to read Markdown's stars: each packet is also written as a simple page, phone-friendly,
    # with every answer's text escaped (an answer can't add its own HTML).
    folder = fake_capture(tmp_path, monkeypatch)
    fill_shown(folder, text="**1. A <b>bold</b> product** & more")
    build_packets(folder, questions_file(tmp_path), [Tester("T01", "skincare")], seed=1)
    page = (folder / "packets" / "T01.html").read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>") and '<meta name="viewport"' in page
    # Changed on purpose 16 Oct 2026 (Noemi's decision 7): each question shows its code for the response form (was
    # "Question 1: ...").
    assert "<h2>Question 1 (b01): &quot;gentle exfoliant for sensitive skin under £30&quot;</h2>" in page
    assert "<h3>Answer A</h3>" in page and "<h3>Answer C</h3>" in page
    assert "<strong>1. A &lt;b&gt;bold&lt;/b&gt; product</strong> &amp; more" in page
    assert "**" not in page and "<b>bold</b>" not in page


def test_each_answer_on_a_packet_page_keeps_its_paragraphs(tmp_path, monkeypatch):
    # The website review of 16 Oct 2026: build_packets handed packet_page each answer as one line, so its three picks ran
    # together as one paragraph (the tests above use one-line answers).
    folder = fake_capture(tmp_path, monkeypatch)
    three = shown_from_ours({"picks": [pick(1, "Dualit Classic Kettle"), pick(2, "Sage Compact Kettle"),
                                       pick(3, "Bosch Styline Kettle")]})
    for tool in blind_test.TOOLS:
        for q in QUESTIONS:
            (folder / "shown" / tool / f"{q['id']}.md").write_text(three + "\n", encoding="utf-8")
    build_packets(folder, questions_file(tmp_path), [Tester("T01", "skincare")], seed=1)
    page = (folder / "packets" / "T01.html").read_text(encoding="utf-8")
    answer_a = page[page.index("<h3>Answer A</h3>"):page.index("<h3>Answer B</h3>")]
    assert answer_a.count("<p><strong>") == 3  # each pick's name opens its own paragraph
    assert "<p><strong>2. Sage Compact Kettle</strong></p>" in answer_a
    assert "<p>&quot;Mine has lasted five years and still boils fast.&quot; (five years of use)</p>" in answer_a
    assert "<p>Price: £45.00 at John Lewis</p>" in answer_a
    md = (folder / "packets" / "T01.md").read_text(encoding="utf-8")
    assert three in md  # the Markdown packet holds each answer exactly as shown


def test_a_line_break_inside_a_paragraph_is_kept_on_the_page():
    # The template puts a second piece of evidence on the line under the first: shown as a new line, not run on.
    page = blind_test.packet_page("T01", ['"First quote." (2 years of use)', '"Second quote." (1 year of use)', ""])
    assert "<p>&quot;First quote.&quot; (2 years of use)<br>&quot;Second quote.&quot; (1 year of use)</p>" in page


TEN = [{"id": f"b{n:02}", "category": "skincare" if n <= 5 else "kitchen", "text": f"made-up question {n}"}
       for n in range(1, 11)]


def test_with_testers_alternating_categories_every_question_gets_its_orders_in_turn(tmp_path):
    # The website review of 16 Oct 2026: order_for followed the tester's row in testers.csv, so with rows alternating by
    # category (as in the runbook's example) each question got 3 of the 6 orders (b01's dry run: ChatGPT first 4 times,
    # ours once, Vetted never). The orders now go round per question: its testers so far, then the next.
    from collections import Counter

    folder = tmp_path / "day"
    for tool in blind_test.TOOLS:
        (folder / "shown" / tool).mkdir(parents=True)
    fill_shown(folder, TEN)
    testers = [Tester(f"T{n:02}", "skincare" if n % 2 else "kitchen") for n in range(1, 11)]
    key = build_packets(folder, questions_file(tmp_path, TEN), testers, seed=3)
    for q in TEN:
        orders = [tuple(key[t][q["id"]][letter] for letter in "ABC") for t in key if q["id"] in key[t]]
        assert len(orders) == 5 and len(set(orders)) == 5, q["id"]  # five testers, five different orders
        firsts = Counter(order[0] for order in orders)
        assert set(firsts) == set(blind_test.TOOLS) and max(firsts.values()) <= 2, (q["id"], firsts)
    for tester in key:  # and a tester's own five questions don't repeat an order either
        orders = [tuple(letters[letter] for letter in "ABC") for letters in key[tester].values()]
        assert len(set(orders)) == len(orders) == 5, tester


def test_each_question_in_a_packet_shows_its_code_for_the_response_form(tmp_path, monkeypatch):
    # Noemi's decision 7 of 16 Oct 2026: she makes the response form (eval/blind_test/RUNBOOK.md); each response names
    # its tester and its question, so the packet says both.
    folder = fake_capture(tmp_path, monkeypatch)
    fill_shown(folder)
    build_packets(folder, questions_file(tmp_path), [Tester("T01", "skincare")], seed=1)
    packet = (folder / "packets" / "T01.md").read_text(encoding="utf-8")
    assert '## Question 1 (b01): "gentle exfoliant for sensitive skin under £30"' in packet
    assert '## Question 2 (b02): "sunscreen for oily skin"' in packet
    assert "your tester code, T01," in packet and "each question's code" in packet


def test_the_runbooks_response_form_gives_every_column_the_tally_reads(tmp_path):
    # The form's export (one row per tester and question) becomes responses.csv once its first line is these columns;
    # a column the tally doesn't read, such as the form's own Timestamp, is ignored.
    runbook = (Path(blind_test.__file__).resolve().parents[1] / "eval" / "blind_test" / "RUNBOOK.md").read_text(
        encoding="utf-8")
    assert "Timestamp,tester,question,choice,least,confidence,comment" in runbook
    for field in ("tester", "question", "choice", "least", "confidence", "comment"):
        assert f"`{field}`" in runbook, field
    path = tmp_path / "responses.csv"
    path.write_text("Timestamp,tester,question,choice,least,confidence,comment\n"
                    "20/10/2026 18:02:11,T01,b01,B,C,4,made-up reason\n", encoding="utf-8")
    (response,) = load_responses(path)
    assert (response.tester, response.question, response.choice, response.least, response.confidence) == (
        "T01", "b01", "B", "C", "4")


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


def test_tally_save_writes_the_result_into_the_metrics_file(tmp_path, monkeypatch, capsys):
    from engine import metrics
    from engine.tests.test_metrics import built

    write_key(tmp_path, KEY)
    responses = write_responses(tmp_path / "responses.csv", [("T01", "b01", "A", "C", 4, ""),
                                                             ("T02", "b02", "C", "A", 2, "")])
    path = tmp_path / "metrics.json"
    metrics.write_metrics(built(), path)
    monkeypatch.setattr(blind_test, "METRICS_FILE", path)
    assert blind_test.main(["tally", str(tmp_path), str(responses), "--save"]) == 0
    saved = json.loads(path.read_text(encoding="utf-8"))["metrics"]
    assert saved["blind_test_vs_vetted"]["out_of"] == 2 and saved["blind_test_vs_chatgpt"]["out_of"] == 2
    assert "Saved in metrics.json" in capsys.readouterr().out


# --- The command line ---

def test_command_line_explains_itself_when_used_wrongly(capsys):
    assert blind_test.main([]) == 2
    out = capsys.readouterr().out
    for command in ("capture", "shown", "packets", "tally"):
        assert f"python -m engine.blind_test {command}" in out


def test_also_worth_a_look_and_summaries_stay_out_of_the_blind_test_view():
    # Noemi's decisions of 13 Oct 2026: the blind test still shows the top 3 picks only, in FORMAT.md's template.
    data = {"picks": [pick(1, "Dualit Classic Kettle", summary={"text": "Owners say it keeps going for years.",
                                                                 "sources": []})],
            "worth_a_look": [pick(1, "Made-up Worth Kettle")], "worth_note": "2 credible voices each: less evidence.",
            "message": None}
    shown = shown_from_ours(data)
    assert "**1. Dualit Classic Kettle**" in shown
    # Changed on purpose 19 Oct 2026 (Noemi's decision (m)): a pick's one-line summary is now its why, so it is shown,
    # as the template's why line (without the page's "In short" label); it was left out until then.
    assert "**1. Dualit Classic Kettle**\n\nOwners say it keeps going for years.\n\n" in shown
    for left_out in ("Made-up Worth Kettle", "2 credible voices each", "In short"):
        assert left_out not in shown
