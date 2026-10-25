"""The pairwise test's cards and decks (engine/pair_test.py; Noemi, 20 Oct 2026): the cards file is read and checked, and
each visitor gets a deck of 6 comparisons, spread across the categories, each ours against one rival, both rivals seen,
ours on a random side.

Every text is made up (engine/tests/pair_factories.py). No test reaches the network.
"""

import copy
import json
import random
from collections import Counter

import pytest

from engine import pair_test
from engine.tests.pair_factories import CATEGORIES, QUESTION_IDS, made_up_cards, pick, question_of, write_cards


def cards_with(change) -> dict:
    cards = made_up_cards()
    change(cards)
    return cards


def load(cards: dict, tmp_path):
    return pair_test.load_cards(write_cards(tmp_path, cards) / "blind_test_cards.json")


# --- Reading the cards file ---

def test_the_cards_file_is_read_whole(tmp_path):
    cards = load(made_up_cards(), tmp_path)
    assert [q["id"] for q in cards["questions"]] == QUESTION_IDS
    assert question_of(cards, "b04")["answers"]["vetted"]["note"] == pair_test.NO_RECOMMENDATION
    assert pair_test.NO_RECOMMENDATION == {"en": "No recommendation given.", "it": "Nessun consiglio dato."}


def test_a_missing_file_says_where_it_should_be(tmp_path):
    with pytest.raises(pair_test.CardsError, match="blind_test_cards.json"):
        pair_test.load_cards(tmp_path / "blind_test_cards.json")


@pytest.mark.parametrize("text", ["", "not json", "[]", '{"version": 1}', '{"version": 2, "questions": []}'])
def test_a_file_that_is_not_the_cards_is_refused(tmp_path, text):
    (tmp_path / "blind_test_cards.json").write_text(text, encoding="utf-8")
    with pytest.raises(pair_test.CardsError):
        pair_test.load_cards(tmp_path / "blind_test_cards.json")


def test_the_cards_default_to_the_librarys_file():
    assert pair_test.cards_file().name == "blind_test_cards.json"
    assert pair_test.cards_file().parent.name == "library"


# Each rule the cards file keeps, and the words that say which question and answer broke it.
def _three_picks_more(cards):
    question_of(cards, "b06")["answers"]["chatgpt"]["picks"].append(pick("A fourth one"))


def _long_why(cards):
    question_of(cards, "b07")["answers"]["ours"]["picks"][0]["why"]["en"] = " ".join(["word"] * 21)


def _long_why_italian(cards):
    question_of(cards, "b07")["answers"]["ours"]["picks"][1]["why"]["it"] = " ".join(["parola"] * 21)


def _no_picks_without_the_note(cards):
    question_of(cards, "b08")["answers"]["vetted"].update(picks=[], note=None)


def _picks_with_a_note(cards):
    question_of(cards, "b08")["answers"]["ours"]["note"] = dict(pair_test.NO_RECOMMENDATION)


def _another_note(cards):
    question_of(cards, "b04")["answers"]["vetted"]["note"] = {"en": "Nothing here.", "it": "Niente."}


def _no_italian_question(cards):
    del question_of(cards, "r01")["text"]["it"]


def _empty_name(cards):
    question_of(cards, "r02")["answers"]["ours"]["picks"][0]["name"] = "  "


def _missing_tool(cards):
    del question_of(cards, "r03")["answers"]["vetted"]


def _extra_tool(cards):
    question_of(cards, "r03")["answers"]["bing"] = {"picks": [], "note": dict(pair_test.NO_RECOMMENDATION)}


def _unknown_category(cards):
    question_of(cards, "r04")["category"] = "pets"


def _same_id_twice(cards):
    cards["questions"][1]["id"] = cards["questions"][0]["id"]


def _bad_id(cards):
    question_of(cards, "r05")["id"] = "R 05!"


def _extra_pick_field(cards):
    question_of(cards, "r05")["answers"]["ours"]["picks"][0]["price"] = "12"


@pytest.mark.parametrize("change, where", [
    (_three_picks_more, "b06"), (_long_why, "b07"), (_long_why_italian, "b07"), (_no_picks_without_the_note, "b08"),
    (_picks_with_a_note, "b08"), (_another_note, "b04"), (_no_italian_question, "r01"), (_empty_name, "r02"),
    (_missing_tool, "r03"), (_extra_tool, "r03"), (_unknown_category, "r04"), (_bad_id, "R 05"),
    (_extra_pick_field, "r05")])
def test_cards_that_break_a_rule_are_refused_naming_the_question(tmp_path, change, where):
    with pytest.raises(pair_test.CardsError, match=where):
        load(cards_with(change), tmp_path)


def test_a_question_twice_is_refused(tmp_path):
    with pytest.raises(pair_test.CardsError, match="twice"):
        load(cards_with(_same_id_twice), tmp_path)


def test_a_why_of_exactly_twenty_words_and_three_picks_are_fine(tmp_path):
    def exact(cards):
        question_of(cards, "b07")["answers"]["ours"]["picks"][0]["why"] = {"en": " ".join(["word"] * 20),
                                                                           "it": " ".join(["parola"] * 20)}
    load(cards_with(exact), tmp_path)


# What a card must never carry, whichever tool's answer it is in: tool names, links, prices, shops, availability.
@pytest.mark.parametrize("words", [
    "As ChatGPT would say, this one is solid.", "Recommended by OpenAI's model.", "Vetted ranks it first.",
    "Made by credible recs voices.", "See https://example.com/kettle for more.", "Read more at www.example.com now.",
    "Around £25 in most shops.", "About $30 at the moment.", "Costs 20 euros.", "A fair price for what you get.",
    "Cheap at 15 GBP.", "Sold on Amazon all year.", "Often in stock at Argos.", "Sold out in most places.",
    "Not sold in the UK.", "Currently out of stock.", "Discontinued last year.", "Free delivery over a minimum.",
    "Ships from Sephora.", "Try the Superdrug own brand."])
def test_a_card_that_names_a_tool_a_link_a_price_a_shop_or_availability_is_refused(tmp_path, words):
    def leak(cards):
        question_of(cards, "b09")["answers"]["chatgpt"]["picks"][1]["why"]["en"] = words
    with pytest.raises(pair_test.CardsError, match="b09"):
        load(cards_with(leak), tmp_path)


def test_a_product_name_may_not_carry_a_price_or_a_tool_name_either(tmp_path):
    def leak(cards):
        question_of(cards, "b09")["answers"]["ours"]["picks"][0]["name"] = "Kettle (£30)"
    with pytest.raises(pair_test.CardsError, match="b09"):
        load(cards_with(leak), tmp_path)


@pytest.mark.parametrize("words", ["Boots stay waterproof for years.", "A target heart rate monitor.",
                                   "Lasts a decade of daily use.", "Gentle enough for sensitive skin."])
def test_ordinary_words_that_only_look_like_shops_are_fine(tmp_path, words):
    def fine(cards):
        question_of(cards, "b09")["answers"]["ours"]["picks"][1]["why"]["en"] = words
    load(cards_with(fine), tmp_path)


def test_the_problems_of_a_cards_file_are_all_listed_together(tmp_path):
    def two(cards):
        _long_why(cards)
        _unknown_category(cards)
    problems = pair_test.problems(cards_with(two))
    assert len(problems) == 2 and "b07" in problems[0] + problems[1] and "r04" in problems[0] + problems[1]
    assert pair_test.problems(made_up_cards()) == []


def test_loading_is_remembered_until_the_file_changes(tmp_path):
    folder = write_cards(tmp_path)
    first = pair_test.cards_in(folder)
    assert pair_test.cards_in(folder) is first
    changed = made_up_cards()
    changed["questions"] = changed["questions"][:8]
    path = folder / "blind_test_cards.json"
    path.write_text(json.dumps(changed), encoding="utf-8")
    assert len(pair_test.cards_in(folder)["questions"]) == 8


def test_cards_in_a_library_without_them_are_none(tmp_path):
    assert pair_test.cards_in(tmp_path) is None


def test_cards_in_a_library_with_a_broken_file_are_none_and_the_reason_is_kept(tmp_path):
    (tmp_path / "blind_test_cards.json").write_text("{", encoding="utf-8")
    assert pair_test.cards_in(tmp_path) is None
    assert pair_test.why_closed(tmp_path)


# --- The deck each visitor gets ---

def deck_of(seed: int, cards: dict | None = None) -> list[dict]:
    return pair_test.build_deck(cards or made_up_cards(), random.Random(seed))


def categories_of(deck: list[dict]) -> Counter:
    by_id = {q: category for category, ids in CATEGORIES.items() for q in ids}
    return Counter(by_id[item["question"]] for item in deck)


def test_a_deck_is_six_different_questions_two_from_each_category():
    for seed in range(300):
        deck = deck_of(seed)
        assert len(deck) == pair_test.QUESTIONS_PER_VISITOR == 6
        assert len({item["question"] for item in deck}) == 6
        assert categories_of(deck) == {"skincare": 2, "kitchen": 2, "other": 2}


def test_a_deck_spreads_across_categories_as_evenly_as_the_set_allows():
    # One skincare and one kitchen question only: they are both asked, and the rest are the others', not 3-2-1.
    cards = made_up_cards()
    cards["questions"] = ([question_of(cards, "b01"), question_of(cards, "b06")]
                          + [question_of(cards, q) for q in CATEGORIES["other"]])
    for seed in range(50):
        assert categories_of(deck_of(seed, cards)) == {"skincare": 1, "kitchen": 1, "other": 4}
    # Two categories only, five questions each: 3 and 3.
    cards = made_up_cards()
    cards["questions"] = [question_of(cards, q) for q in CATEGORIES["kitchen"] + CATEGORIES["other"]]
    for seed in range(50):
        assert sorted(categories_of(deck_of(seed, cards)).values()) == [3, 3]


def test_a_set_of_fewer_than_six_questions_gives_a_shorter_deck():
    cards = made_up_cards()
    cards["questions"] = cards["questions"][:4]
    assert len(deck_of(1, cards)) == 4


def test_each_visitor_sees_both_rivals_three_comparisons_each():
    for seed in range(300):
        assert Counter(item["rival"] for item in deck_of(seed)) == {"chatgpt": 3, "vetted": 3}


def test_ours_is_on_either_side_three_times_each():
    for seed in range(300):
        assert Counter(item["ours_side"] for item in deck_of(seed)) == {"A": 3, "B": 3}


def test_every_question_and_every_order_can_come_up():
    seen_first, asked = Counter(), Counter()
    for seed in range(1200):
        deck = deck_of(seed)
        seen_first[deck[0]["question"]] += 1
        asked.update(item["question"] for item in deck)
    assert set(asked) == set(QUESTION_IDS)
    assert set(seen_first) == set(QUESTION_IDS)  # the first screen isn't always the same
    # The two skincare questions are asked of everybody; each of the five kitchen ones of about two in five visitors.
    assert asked["b01"] == asked["b04"] == 1200
    assert all(380 <= asked[q] <= 580 for q in CATEGORIES["kitchen"] + CATEGORIES["other"]), asked


def test_both_rivals_and_both_sides_come_up_for_every_question():
    seen = Counter()
    for seed in range(800):
        for item in deck_of(seed):
            seen[(item["question"], item["rival"], item["ours_side"])] += 1
    assert len(seen) == len(QUESTION_IDS) * 2 * 2


def test_the_same_seed_gives_the_same_deck_and_another_seed_another():
    assert deck_of(7) == deck_of(7)
    assert deck_of(7) != deck_of(8)


def test_each_comparison_puts_ours_and_the_rival_on_their_sides_and_nothing_else():
    cards = made_up_cards()
    for item in deck_of(3, cards):
        question = question_of(cards, item["question"])
        rival_side = "B" if item["ours_side"] == "A" else "A"
        assert item["text"] == question["text"]
        assert item["cards"][item["ours_side"]] == question["answers"]["ours"]
        assert item["cards"][rival_side] == question["answers"][item["rival"]]
        assert set(item) == {"question", "text", "rival", "ours_side", "cards"}
        assert set(item["cards"]) == {"A", "B"}


def test_building_a_deck_changes_nothing_in_the_cards():
    cards = made_up_cards()
    before = copy.deepcopy(cards)
    deck_of(5, cards)
    assert cards == before


def test_a_deck_is_refused_when_there_are_no_questions():
    with pytest.raises(pair_test.CardsError):
        pair_test.build_deck({"version": 1, "questions": []}, random.Random(1))


# --- python -m engine.pair_test check ---

def test_the_check_command_says_the_cards_follow_the_rules_or_lists_what_breaks_them(tmp_path, capsys):
    good = write_cards(tmp_path / "good") / "blind_test_cards.json"
    assert pair_test.main(["check", str(good)]) == 0
    assert "12 questions (skincare 2, kitchen 5, other 5)" in capsys.readouterr().out
    bad = write_cards(tmp_path / "bad", cards_with(_long_why)) / "blind_test_cards.json"
    assert pair_test.main(["check", str(bad)]) == 1
    assert "b07" in capsys.readouterr().out
    assert pair_test.main(["check", str(tmp_path / "missing.json")]) == 1
    assert pair_test.main([]) == 2
