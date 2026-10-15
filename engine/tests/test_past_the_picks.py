"""Products past the top 3 (Noemi's decision 4 of 15 Oct 2026).

A product that meets the picks bar but ranks below the top 3 is listed first under "Also worth a look", labelled as
meeting the bar. Until then such a product was shown nowhere, while products with two credible voices were shown there
(on the frozen library of 14 Oct, Byoma's Jelly Cleanser and CeraVe's Skin Renewing Vitamin C serum, for example).
Also worth a look keeps its size (config.WORTH_A_LOOK_SHOWN), these products first, best first; after them the products
with two credible voices across two threads, then those a comment standing out in its thread puts there. A product that
meets the bar only thanks to the upvote rule or a standing-out comment isn't one of them: those only fill places left
empty, as before. Through every layer: the ranking (engine/rank.py), the answer (engine/answer.py), the API
(engine/web.py), the page (engine/templates/search.html) and the how page.

Every product, comment and library here is made up; nothing reads data/ or reaches the network.
"""

import json

import pytest

from engine import answer as wording
from engine import config, web
from engine.answer import answer_to_dict, render_markdown, unverified_claims, write_answer
from engine.config import WORTH_A_LOOK_QUOTES, WORTH_A_LOOK_SHOWN
from engine.pipeline import answer_request
from engine.rank import rank_products
from engine.tests.ranking_factories import bodies_for, mention, mentions
from engine.tests.test_web import REQUEST, ask, kettle_library
from engine.tests.test_web_public import function_body, page_text, script_of, settings_of

TOP = {"thread_comments": 40, "share_beaten": 0.95}  # the top of a big thread, as engine/tests/test_upvotes.py has it


def names(products) -> list[str]:
    return [p.name for p in products]


def knives(bar: int = 2, voices: int = 2, more: list | None = None) -> list:
    """Three picks (4 credible voices each, highest scores), `bar` more knives meeting the bar with 3 medium voices each
    (lower scores, best first: Knife D, E...), and `voices` knives with two credible voices across two threads."""
    items = [m for name in ("Knife A", "Knife B", "Knife C") for m in mentions(4, name)]
    for n in range(bar):
        items += mentions(3, f"Knife {'DEFGHI'[n]}", voice="medium", weight=0.6 - n / 100)
    for n in range(voices):
        items += mentions(2, f"Duo {'VWXYZ'[n]}", voice="medium", weight=0.3 - n / 100)
    return items + (more or [])


def answer_of(items, product_type: str = "chef knife", **kwargs):
    ranking = rank_products(items, "kitchen")
    return ranking, write_answer(ranking, bodies_for(*items), product_type, **kwargs)


# --- Module 6: the ranking ---

def test_a_product_meeting_the_bar_below_the_top_3_comes_first_under_also_worth_a_look():
    ranking = rank_products(knives(), "kitchen")
    assert names(ranking.picks) == ["Knife A", "Knife B", "Knife C"]
    assert names(ranking.past_the_picks) == ["Knife D", "Knife E"]
    assert names(ranking.worth_a_look) == ["Knife D", "Knife E", "Duo V", "Duo W"]
    knife_d = next(p for p in ranking.products if p.name == "Knife D")
    assert knife_d.qualifies and not knife_d.worth_a_look  # it meets the bar: no less supported than a pick


def test_with_three_picks_or_fewer_there_is_none():
    ranking = rank_products(knives(bar=0), "kitchen")
    assert ranking.past_the_picks == [] and names(ranking.worth_a_look) == ["Duo V", "Duo W"]
    two = rank_products([m for name in ("Knife A", "Knife B") for m in mentions(4, name)], "kitchen")
    assert names(two.picks) == ["Knife A", "Knife B"] and two.past_the_picks == []


def test_one_lifted_by_its_upvotes_only_fills_a_place_and_stays_a_two_voice_item(monkeypatch):
    # Variant D (Noemi, 14 Oct 2026): a product the upvote rule lifts to the bar only takes a place the picks leave
    # empty. Past the top 3 it is what it was without the rule, an item with two credible voices, never labelled as
    # meeting the bar.
    monkeypatch.setattr(config, "STANDOUT_ON", False)
    lifted = [mention("Duo L", "t1", upvotes=34, **TOP), mention("Duo L", "t2", upvotes=2)]
    ranking = rank_products(knives(bar=1, voices=0, more=lifted), "kitchen", upvote_rule=True)
    duo_l = next(p for p in ranking.products if p.name == "Duo L")
    assert duo_l.qualifies and duo_l.counted_twice  # it meets the bar with the upvote rule's count
    assert names(ranking.past_the_picks) == ["Knife D"]
    assert names(ranking.worth_a_look) == ["Knife D", "Duo L"]


def test_one_a_standing_out_comment_lifts_comes_after_the_rest():
    pan = [mention("Duo P", "t1", upvotes=74, thread_comments=69, share_beaten=0.97),
           mention("Duo P", "t1")]
    ranking = rank_products(knives(bar=1, voices=1, more=pan), "kitchen", standout_rule=True)
    assert next(p for p in ranking.products if p.name == "Duo P").by_standout
    assert names(ranking.past_the_picks) == ["Knife D"]
    assert names(ranking.worth_a_look) == ["Knife D", "Duo V", "Duo P"]


# --- Module 7: the answer ---

def test_they_come_first_labelled_as_meeting_the_bar_within_the_size_limit():
    _, answer = answer_of(knives())
    assert names(answer.picks) == ["Knife A", "Knife B", "Knife C"]
    assert names(answer.worth_a_look) == ["Knife D", "Knife E", "Duo V"]  # 3 in all: WORTH_A_LOOK_SHOWN
    assert len(answer.worth_a_look) == WORTH_A_LOOK_SHOWN
    assert [item.meets_bar for item in answer.worth_a_look] == [True, True, False]
    knife_d = answer.worth_a_look[0]
    assert knife_d.reason == "Recommended by 3 credible voices, 3 of them after long-term use."
    assert knife_d.voices == {"recommend": 3, "high": 0, "medium": 3, "warn": 0, "threads": 2}
    assert 1 <= len(knife_d.quotes) <= WORTH_A_LOOK_QUOTES


def test_with_more_meeting_the_bar_than_places_only_they_are_shown():
    _, answer = answer_of(knives(bar=4))
    assert names(answer.worth_a_look) == ["Knife D", "Knife E", "Knife F"]
    assert all(item.meets_bar for item in answer.worth_a_look)


def test_without_them_the_section_is_as_before(monkeypatch):
    monkeypatch.setattr(config, "UPVOTE_COUNTS_MORE", False)  # the plain bar's words, as test_answer_worth.py has them
    _, answer = answer_of(knives(bar=0))
    assert [item.meets_bar for item in answer.worth_a_look] == [False, False]
    assert answer.worth_note == ("2 credible voices each: less evidence than the picks above, which need at least 3 "
                                 "credible recommendations across at least 2 threads.")


def test_the_note_under_the_heading_says_which_meet_the_bar(monkeypatch):
    monkeypatch.setattr(config, "UPVOTE_COUNTS_MORE", False)
    bar = "at least 3 credible recommendations across at least 2 threads"
    assert answer_of(knives())[1].worth_note == (
        f"The first 2 meet the bar for a pick ({bar}) but rank below the top 3; then 2 credible voices each: less "
        "evidence than a pick needs.")
    assert answer_of(knives(bar=1))[1].worth_note == (
        f"The first meets the bar for a pick ({bar}) but ranks below the top 3; then 2 credible voices each: less "
        "evidence than a pick needs.")
    assert answer_of(knives(bar=3))[1].worth_note == (
        f"Each meets the bar for a pick ({bar}) but ranks below the top 3.")
    assert answer_of(knives(bar=1, voices=0))[1].worth_note == (
        f"It meets the bar for a pick ({bar}) but ranks below the top 3.")


def test_the_bar_is_said_plainly_even_with_the_upvote_rule_on():
    # The items labelled meet the bar on their own: the note gives that bar, not the upvote rule's other way to it.
    assert config.UPVOTE_COUNTS_MORE
    note = answer_of(knives(bar=3))[1].worth_note
    assert note == "Each meets the bar for a pick (at least 3 credible recommendations across at least 2 threads) " \
                   "but ranks below the top 3."


def test_with_an_item_a_standing_out_comment_puts_there_the_note_says_that_too(monkeypatch):
    monkeypatch.setattr(config, "UPVOTE_COUNTS_MORE", False)
    items = knives(bar=1, voices=0, more=[mention("Duo P", "t1", upvotes=74, thread_comments=69, share_beaten=0.97)])
    answer = write_answer(rank_products(items, "kitchen", standout_rule=True), bodies_for(*items), "chef knife")
    assert names(answer.worth_a_look) == ["Knife D", "Duo P"]
    assert answer.worth_note == (
        "The first meets the bar for a pick (at least 3 credible recommendations across at least 2 threads) but ranks "
        "below the top 3; then 2 credible voices each, or one comment that stands out in its thread: less evidence "
        "than a pick needs.")


def test_the_text_answer_labels_each_and_the_json_says_so():
    items = knives()
    _, answer = answer_of(items)
    text = render_markdown(answer)
    worth = text[text.index(f"## {wording.WORTH_HEADING}"):]
    knife_d, rest = worth.split("### Knife D", 1)[1].split("### Knife E", 1)
    assert f"**{wording.MEETS_BAR}**" in knife_d and f"**{wording.MEETS_BAR}**" in rest.split("### Duo V")[0]
    assert wording.MEETS_BAR not in worth.split("### Duo V", 1)[1]
    data = json.loads(json.dumps(answer_to_dict(answer)))
    assert [item["meets_bar"] for item in data["worth_a_look"]] == [True, True, False]
    assert unverified_claims(answer, bodies_for(*items)) == []


def test_when_the_live_check_puts_one_off_the_note_still_counts_right(monkeypatch):
    # The picks first (Noemi, 13 Oct 2026): an Also worth a look item whose comment can't be read without waiting is left
    # out of that answer (engine.answer.without_unread). The note is worked out again from what is left.
    from engine.answer import without_unread

    monkeypatch.setattr(config, "UPVOTE_COUNTS_MORE", False)
    _, answer = answer_of(knives())
    knife_e = answer.worth_a_look[1]
    assert knife_e.name == "Knife E" and answer.worth_note.startswith("The first 2 meet the bar")
    later = without_unread(answer, {quote.comment_id for quote in knife_e.quotes})
    assert names(later.worth_a_look) == ["Knife D", "Duo V"]
    assert later.worth_note.startswith("The first meets the bar for a pick")
    alone = without_unread(answer, {q.comment_id for item in answer.worth_a_look[1:] for q in item.quotes})
    assert alone.worth_note.startswith("It meets the bar for a pick")


def test_the_wording_decided_by_claude():
    assert wording.MEETS_BAR == "Meets the bar for a pick"


def test_a_product_that_cant_be_a_pick_for_want_of_quotes_gives_its_place_as_before():
    # Knife B's quotes all fail the check: Knife D is a pick in its place, Knife E heads Also worth a look.
    items = knives()
    bodies = bodies_for(*items)
    for m in items:
        if m.product_name == "Knife B":
            bodies[m.comment_id] = "This comment says something else now."
    answer = write_answer(rank_products(items, "kitchen"), bodies, "chef knife")
    assert names(answer.picks) == ["Knife A", "Knife C", "Knife D"]
    assert names(answer.worth_a_look) == ["Knife E", "Duo V", "Duo W"]
    assert [item.meets_bar for item in answer.worth_a_look] == [True, False, False]


# --- The pipeline ---

def test_through_the_pipeline_a_fourth_kettle_meeting_the_bar_heads_also_worth_a_look(tmp_path):
    library = kettle_library(tmp_path, praised=("Zojirushi", "Fellow Stagg", "Bonavita", "Dualit", "Sage"))
    result = answer_request(REQUEST, library_dir=library)
    assert len(result.answer.picks) == 3
    shown = [pick.name for pick in result.answer.picks]
    items = result.answer.worth_a_look
    assert len(items) == 2 and all(item.meets_bar for item in items)
    assert {item.name for item in items} | set(shown) == {f"{brand} kettle" for brand in (
        "Zojirushi", "Fellow Stagg", "Bonavita", "Dualit", "Sage")}
    assert unverified_claims(result.answer, result.bodies) == []


# --- The API and the page ---

def test_the_api_says_which_items_meet_the_bar(tmp_path):
    library = kettle_library(tmp_path, praised=("Zojirushi", "Fellow Stagg", "Bonavita", "Dualit"))
    status, _, data = ask(REQUEST, library)
    assert status == 200
    (item,) = data["answer"]["worth_a_look"]
    assert item["meets_bar"] is True
    assert data["answer"]["worth_note"].startswith("It meets the bar for a pick")
    assert "meets_bar" in web.__doc__


def test_the_page_tags_such_a_row_in_the_answers_words(tmp_path):
    html = page_text(tmp_path)
    assert settings_of(html)["wording"]["meets_bar"] == wording.MEETS_BAR
    script = script_of(html)
    worth = function_body(script, "function worthCard(item)")
    shown, _ = worth.split("return row(", 1)  # what the row shows before it is opened
    assert "barTag(item.meets_bar)" in shown
    tag = function_body(script, "function barTag(meets)")
    assert "WORDING.meets_bar" in tag and 'class: "tag bar"' in tag and "innerHTML" not in tag


def test_its_tag_is_drawn_in_the_accent_colours_whose_contrast_is_checked(tmp_path):
    css = page_text(tmp_path).split("<style>", 1)[1].split("</style>", 1)[0]
    assert ".tag.bar { background: var(--accent-soft); color: var(--accent); }" in css


# --- The how page ---

def test_the_how_page_says_where_they_are_listed(tmp_path, monkeypatch):
    from engine.tests.test_how_page import get_how, text_of

    words = text_of(get_how(tmp_path, monkeypatch))
    assert (f"A product that meets the bar but ranks below the top 3 is listed there first, marked “{wording.MEETS_BAR}”, "
            "within those 3 places.") in words
