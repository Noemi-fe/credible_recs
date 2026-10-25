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


# --- A visit: its deck follows from its id, so the page never needs to know the rival or the side (25 Oct 2026) ---

KEY = pair_test.deck_key({"CREDIBLE_RECS_TEST_KEY": "a made-up key for the tests"})
OTHER_KEY = pair_test.deck_key({"CREDIBLE_RECS_TEST_KEY": "another made-up key"})


def visit_of(seed: int, cards: dict | None = None) -> str:
    return pair_test.new_visit(cards or made_up_cards(), random.Random(seed))


def test_a_visits_id_is_one_the_answers_route_takes_and_it_ends_with_the_cards_fingerprint():
    from engine import feedback

    cards = made_up_cards()
    visit = visit_of(1, cards)
    assert feedback._PAIR_SESSION.fullmatch(visit) and len(visit) == 28
    assert visit.endswith(pair_test.fingerprint(cards))
    assert visit_of(1, cards) == visit and visit_of(2, cards) != visit  # random ids, from the generator given


def test_the_fingerprint_follows_the_questions_and_their_categories_and_order_not_the_words():
    cards = made_up_cards()
    words_changed = copy.deepcopy(cards)
    words_changed["questions"][0]["answers"]["ours"]["picks"][0]["name"] = "Another made-up name"
    assert pair_test.fingerprint(words_changed) == pair_test.fingerprint(cards)
    fewer = copy.deepcopy(cards)
    fewer["questions"].pop()
    assert pair_test.fingerprint(fewer) != pair_test.fingerprint(cards)
    reordered = copy.deepcopy(cards)
    reordered["questions"].reverse()
    assert pair_test.fingerprint(reordered) != pair_test.fingerprint(cards)
    recategorised = copy.deepcopy(cards)
    recategorised["questions"][0]["category"] = "other"
    assert pair_test.fingerprint(recategorised) != pair_test.fingerprint(cards)


def test_a_visits_deck_is_worked_out_from_its_id_and_the_servers_key_the_same_each_time():
    cards = made_up_cards()
    visit = visit_of(5, cards)
    deck = pair_test.deck_for(cards, visit, KEY)
    assert deck == pair_test.deck_for(cards, visit, KEY)  # asked for again when its answers come in: the same deck
    assert len(deck) == 6 and Counter(item["rival"] for item in deck) == {"chatgpt": 3, "vetted": 3}
    assert Counter(item["ours_side"] for item in deck) == {"A": 3, "B": 3}
    assert pair_test.deck_for(cards, visit_of(6, cards), KEY) != deck
    assert pair_test.deck_for(cards, visit, OTHER_KEY) != deck  # nobody without the key can work a deck out


def test_the_rival_and_side_of_each_question_asked_can_be_found_again_from_the_id_alone():
    cards = made_up_cards()
    for seed in range(40):
        visit = visit_of(seed, cards)
        deck = pair_test.deck_for(cards, visit, KEY)
        for item in deck:
            assert pair_test.sides_of(cards, visit, item["question"], KEY) == (item["rival"], item["ours_side"])
        asked = {item["question"] for item in deck}
        for question in set(QUESTION_IDS) - asked:
            assert pair_test.sides_of(cards, visit, question, KEY) is None  # not in this visit's deck: not its answer
        assert pair_test.sides_of(cards, visit, "z99", KEY) is None


def test_an_id_made_for_other_cards_is_not_matched_to_a_deck():
    cards = made_up_cards()
    visit = visit_of(3, cards)
    changed = copy.deepcopy(cards)
    changed["questions"] = changed["questions"][:8]  # cards replaced while a visitor was part way through
    question = pair_test.deck_for(cards, visit, KEY)[0]["question"]
    assert pair_test.sides_of(changed, visit, question, KEY) is None
    assert pair_test.sides_of(cards, visit, question, KEY) is not None


def test_an_id_that_is_not_one_the_server_made_gives_some_deck_but_never_an_error():
    cards = made_up_cards()
    assert pair_test.sides_of(cards, "k3j9x0a7q2m5p8w1", "b01", KEY) is None  # too short to carry a fingerprint
    forged = "f" * 24 + pair_test.fingerprint(cards)
    deck = pair_test.deck_for(cards, forged, KEY)
    assert pair_test.sides_of(cards, forged, deck[0]["question"], KEY) == (deck[0]["rival"], deck[0]["ours_side"])


def test_the_public_deck_is_what_the_page_gets_and_it_holds_neither_the_rival_nor_the_side():
    cards = made_up_cards()
    deck = deck_of(4, cards)
    public = pair_test.public_deck(deck)
    assert [set(item) for item in public] == [{"question", "text", "cards"}] * 6
    assert [item["cards"] for item in public] == [item["cards"] for item in deck]
    assert "rival" in deck[0] and "ours_side" in deck[0]  # the deck itself is not changed
    assert not any(word in json.dumps(public) for word in ("rival", "ours_side", "chatgpt", "vetted"))


def test_the_key_comes_from_the_sites_own_secret_so_every_instance_has_the_same():
    token = {"HF_TOKEN": "a-made-up-token"}
    assert pair_test.deck_key(token) == pair_test.deck_key(token) != pair_test.deck_key({"HF_TOKEN": "another-token"})
    assert b"a-made-up-token" not in pair_test.deck_key(token)  # a key worked out from the token, not the token
    assert pair_test.deck_key({**token, "CREDIBLE_RECS_TEST_KEY": "own"}) == pair_test.deck_key(
        {"CREDIBLE_RECS_TEST_KEY": "own"})  # its own setting comes first
    assert pair_test.deck_key({"HF_TOKEN": "  "}) != pair_test.deck_key({"HF_TOKEN": "  "})  # none set: a fresh key each
    assert pair_test.deck_key({}) != pair_test.deck_key({})


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
