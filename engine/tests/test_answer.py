"""Module 7, answer writing: the top 3 picks from a fixed template, showing only quotes re-verified word for word.

The guardrail is the point of most of these tests: a planted quote that isn't in its comment, a comment
deleted since, or a quote over the word limit must never reach the answer, in any form (structured or text).
All data is made up (engine/tests/ranking_factories.py and factories.py).
"""

import json

from engine import answer as wording
from engine.answer import ShownQuote, answer_to_dict, comment_bodies, render_markdown, unverified_claims, write_answer
from engine.config import MIN_QUOTES_PER_PICK, QUOTE_MAX_WORDS, QUOTES_PER_PICK
from engine.models import Thread
from engine.rank import rank_products
from engine.tests.factories import make_comment, make_thread
from engine.tests.ranking_factories import bodies_for, mention, mentions, note

FAKE = "Best knife ever made, I would never use anything else."


def kitchen_case():
    """Three qualifying knives, one warned against, and kind notes. Returns (ranking, bodies, every item)."""
    items = (
        mentions(4, "Tojiro DP Gyuto", threads=("t1", "t2", "t3"))
        + mentions(3, "Global G-2", voice="medium")
        + [mention("Global G-2", "t2", stance="warn", voice="medium", quote="The handle gets slippery when wet.")]
        + [mention("Global G-2", "t3", stance="warn", voice="low", evidence="no first-hand use", quote="Looks cheap, never tried it.")]
        + mentions(3, "Victorinox Fibrox", voice="medium", evidence="short-term use", badges=())
        + mentions(2, "Tefal Knife", stance="warn")
    )
    notes = [note("Japanese gyuto", "t1"), note("Japanese gyuto", "t2"), note("Serrated knife", "t3", stance="warn")]
    ranking = rank_products(items, "kitchen", notes, {"japanese-gyuto": ["tojiro-dp-gyuto"]}, kind_bonus=1.0)
    return ranking, bodies_for(*items, *notes), items + notes


def shown_text(answer) -> str:
    """Everything a user or the web interface could see: the text rendering and the JSON."""
    return render_markdown(answer) + json.dumps(answer_to_dict(answer))


# --- The picks ---

def test_three_picks_each_with_two_or_three_verified_linked_quotes():
    ranking, bodies, _ = kitchen_case()
    answer = write_answer(ranking, bodies, "chef knife")
    assert [p.name for p in answer.picks] == ["Tojiro DP Gyuto", "Global G-2", "Victorinox Fibrox"]
    assert [p.rank for p in answer.picks] == [1, 2, 3]
    for pick in answer.picks:
        assert MIN_QUOTES_PER_PICK <= len(pick.quotes) <= QUOTES_PER_PICK
        assert all(q.url.startswith("https://") and q.text in bodies[q.comment_id] for q in pick.quotes)
    assert answer.message is None and not answer.needs_more_threads
    assert unverified_claims(answer, bodies) == []


def test_the_reason_and_support_lines_come_from_the_data():
    ranking, bodies, _ = kitchen_case()
    tojiro, _, victorinox = write_answer(ranking, bodies).picks
    assert "4 credible voices" in tojiro.reason and "4 of them after long-term use" in tojiro.reason
    assert "Japanese gyuto" in tojiro.reason  # it got the kind bonus
    assert tojiro.support == "Backed by 4 high-credibility voices, across 3 threads."
    assert "long-term" not in victorinox.reason and "gyuto" not in victorinox.reason
    assert victorinox.support == "Backed by 3 medium-credibility voices, across 2 threads."


def test_quotes_come_from_credible_recommendations_most_credible_first():
    lodge = [
        mention("Lodge Skillet", "t1", voice="medium", evidence="short-term use", quote="Medium short quote here."),
        mention("Lodge Skillet", "t2", quote="High long quote here."),
        mention("Lodge Skillet", "t1", voice="medium", quote="Medium long quote here."),
        mention("Lodge Skillet", "t2", voice="low", quote="Low voice quote here."),
        mention("Lodge Skillet", "t1", evidence="no first-hand use", quote="Hearsay quote here."),
    ]
    answer = write_answer(rank_products(lodge, "kitchen"), bodies_for(*lodge))
    assert [q.text for q in answer.picks[0].quotes] == [
        "High long quote here.", "Medium long quote here.", "Medium short quote here."
    ]


def test_each_quote_carries_its_badges_or_a_plain_fallback():
    ranking, bodies, _ = kitchen_case()
    tojiro, _, victorinox = write_answer(ranking, bodies).picks
    assert tojiro.quotes[0].badges == ("3 years of use",)
    assert victorinox.quotes[0].badges == ("medium-credibility voice", "short-term use")  # no badges were given


# --- The guardrail: every quote shown is re-verified word for word ---

def test_a_planted_fake_quote_is_dropped_and_never_shown():
    real = mentions(3, "Tojiro DP Gyuto", voice="medium")
    fake = mention("Tojiro DP Gyuto", "t1", quote=FAKE)  # the most credible, so it would be shown first
    bodies = bodies_for(*real) | {fake.comment_id: "Decent knife. I'd buy it again."}
    answer = write_answer(rank_products(real + [fake], "kitchen"), bodies)
    assert answer.picks[0].name == "Tojiro DP Gyuto"
    assert FAKE not in shown_text(answer)
    assert answer.quotes_dropped == 1
    assert unverified_claims(answer, bodies) == []


def test_a_quote_whose_comment_is_gone_is_dropped():
    data = mentions(4, "Tojiro DP Gyuto")
    bodies = bodies_for(*data)
    del bodies[data[0].comment_id]  # deleted on Reddit since the extraction
    answer = write_answer(rank_products(data, "kitchen"), bodies)
    assert data[0].quote not in shown_text(answer)
    assert answer.quotes_dropped == 1


def test_a_quote_over_the_word_limit_is_dropped():
    long_quote = " ".join(["word"] * QUOTE_MAX_WORDS) + " more."
    data = [mention("Tojiro DP Gyuto", "t1", quote=long_quote)] + mentions(3, "Tojiro DP Gyuto", voice="medium")
    answer = write_answer(rank_products(data, "kitchen"), bodies_for(*data))
    assert long_quote not in shown_text(answer)
    assert answer.quotes_dropped == 1


def test_a_pick_without_two_verified_quotes_gives_its_place_to_the_next():
    first = mentions(5, "A Knife")
    others = mentions(3, "B Knife") + mentions(3, "C Knife", voice="medium") + mentions(3, "D Knife", voice="low") + mentions(
        3, "E Knife", voice="medium", evidence="short-term use"
    )
    bodies = bodies_for(*first[:1], *others)  # 4 of A's 5 comments were deleted since
    answer = write_answer(rank_products(first + others, "kitchen"), bodies)
    assert [p.name for p in answer.picks] == ["B Knife", "C Knife", "E Knife"]
    assert [p.rank for p in answer.picks] == [1, 2, 3]
    assert "A Knife" not in render_markdown(answer)
    assert unverified_claims(answer, bodies) == []


def test_the_check_catches_a_quote_planted_in_a_finished_answer():
    ranking, bodies, _ = kitchen_case()
    answer = write_answer(ranking, bodies)
    real = answer.picks[0].quotes[0]
    answer.picks[0].quotes[0] = ShownQuote(FAKE, real.comment_id, real.url, real.badges)
    problems = unverified_claims(answer, bodies)
    assert len(problems) == 1
    assert "pick 1" in problems[0] and real.comment_id in problems[0]
    assert FAKE not in problems[0]  # a failed quote is never repeated, even in a report


def test_the_check_catches_missing_comments_long_quotes_and_thin_picks():
    ranking, bodies, _ = kitchen_case()
    answer = write_answer(ranking, bodies)
    gone = answer.picks[0].quotes[0].comment_id
    answer.picks[1].quotes = answer.picks[1].quotes[:1]
    long_quote = " ".join(["word"] * (QUOTE_MAX_WORDS + 1))
    answer.picks[2].quotes[0] = ShownQuote(long_quote, "cLONG", "https://example.com/cLONG", ())
    problems = unverified_claims(answer, {**{k: v for k, v in bodies.items() if k != gone}, "cLONG": long_quote})
    assert len(problems) == 3
    assert any(gone in p and "not available" in p for p in problems)
    assert any("pick 2" in p and f"needs {MIN_QUOTES_PER_PICK}" in p for p in problems)
    assert any("pick 3" in p and f"limit is {QUOTE_MAX_WORDS}" in p for p in problems)


def test_the_check_covers_downsides_skip_these_and_what_to_look_for():
    ranking, bodies, _ = kitchen_case()
    answer = write_answer(ranking, bodies)
    for section in (answer.picks[1].downsides, answer.skip[0].quotes, [answer.look_for[0]]):
        assert section, "the case should fill every section"
    answer.picks[1].downsides[0] = planted(answer.picks[1].downsides[0])
    answer.skip[0].quotes[0] = planted(answer.skip[0].quotes[0])
    answer.look_for[0].quote = planted(answer.look_for[0].quote)
    assert len(unverified_claims(answer, bodies)) == 3


def planted(quote: ShownQuote) -> ShownQuote:
    """The same quote, its words swapped for made-up ones."""
    return ShownQuote(FAKE, quote.comment_id, quote.url, quote.badges)


# --- Downsides, disagreement and the skip-these list ---

def test_downsides_come_from_credible_warnings_only():
    ranking, bodies, _ = kitchen_case()
    _, global_g2, victorinox = write_answer(ranking, bodies).picks
    assert [q.text for q in global_g2.downsides] == ["The handle gets slippery when wet."]
    assert victorinox.downsides == []
    assert wording.NO_DOWNSIDES in render_markdown(write_answer(ranking, bodies))


def test_a_disputed_pick_says_so():
    data = mentions(4, "Lodge Skillet") + mentions(2, "Lodge Skillet", stance="warn", voice="medium")
    pick = write_answer(rank_products(data, "kitchen"), bodies_for(*data)).picks[0]
    assert "Mixed opinions" in pick.disagreement and "2 credible voices" in pick.disagreement
    assert len(pick.downsides) == 2


def test_an_undisputed_pick_has_no_disagreement_line():
    ranking, bodies, _ = kitchen_case()
    assert write_answer(ranking, bodies).picks[0].disagreement is None


def test_the_skip_list_shows_warned_against_products_with_verified_quotes():
    ranking, bodies, _ = kitchen_case()
    answer = write_answer(ranking, bodies)
    assert [item.name for item in answer.skip] == ["Tefal Knife"]
    assert answer.skip[0].reason == "Warned against by 2 credible voices."
    assert len(answer.skip[0].quotes) == 2


def test_a_skipped_product_that_some_still_praise_says_so():
    data = mentions(1, "Cuisinart Pan") + mentions(3, "Cuisinart Pan", stance="warn")
    item = write_answer(rank_products(data, "kitchen"), bodies_for(*data)).skip[0]
    assert item.reason == "Warned against by 3 credible voices, though still recommended by 1 credible voice."


def test_praised_products_never_reach_the_skip_list():
    data = mentions(5, "Lodge Skillet") + mentions(3, "Staub Pan") + mentions(3, "Staub Pan", stance="warn")
    assert write_answer(rank_products(data, "kitchen"), bodies_for(*data)).skip == []


def test_a_skipped_product_with_no_verified_quote_is_left_out():
    data = mentions(2, "Tefal Knife", stance="warn")
    answer = write_answer(rank_products(data, "kitchen"), {})
    assert answer.skip == []
    assert "Tefal" not in render_markdown(answer)


# --- What to look for: the blueprint from credible kind notes ---

def test_what_to_look_for_comes_from_credible_kind_notes():
    ranking, bodies, _ = kitchen_case()
    look_for = write_answer(ranking, bodies).look_for
    assert [(item.kind, item.advice) for item in look_for] == [
        ("Japanese gyuto", wording.LOOK_FOR), ("Serrated knife", wording.AVOID)
    ]


def test_low_voices_and_balanced_kinds_give_no_advice():
    notes = (
        [note("Plastic handle", voice="low") for _ in range(3)]
        + [note("Carbon steel"), note("Carbon steel", stance="warn")]  # balanced: no clear advice
        + [note("Japanese gyuto")]
    )
    ranking = rank_products(mentions(3, "Tojiro DP Gyuto"), "kitchen", notes)
    look_for = write_answer(ranking, bodies_for(*notes)).look_for
    assert [item.kind for item in look_for] == ["Japanese gyuto"]


def test_at_most_three_kinds_strongest_advice_first():
    notes = [note(kind, weight=w) for kind, w in (("A kind", 0.2), ("B kind", 0.9), ("C kind", 0.5), ("D kind", 0.7))]
    look_for = write_answer(rank_products([], "kitchen", notes), bodies_for(*notes)).look_for
    assert [item.kind for item in look_for] == ["B kind", "D kind", "C kind"]


def test_a_kind_note_that_fails_verification_gives_way_to_the_next():
    fake, real = note("Japanese gyuto", quote=FAKE), note("Japanese gyuto", weight=0.5)
    bodies = bodies_for(real) | {fake.comment_id: "Something else entirely."}
    answer = write_answer(rank_products([], "kitchen", [fake, real]), bodies)
    assert [item.quote.text for item in answer.look_for] == [real.quote]
    assert FAKE not in shown_text(answer)


# --- The honest message when evidence is thin ---

def test_no_qualifying_product_gets_an_honest_message_and_no_picks():
    data = mentions(5, "Tojiro DP Gyuto", threads=("t1",))
    answer = write_answer(rank_products(data, "kitchen"), bodies_for(*data), "chef knife")
    assert answer.picks == []
    assert "any chef knife" in answer.message and "3 credible recommendations" in answer.message
    assert answer.needs_more_threads
    assert answer.message in render_markdown(answer)


def test_fewer_than_three_picks_says_how_many_and_why():
    data = mentions(3, "A Knife") + mentions(3, "B Knife") + mentions(2, "C Knife")
    answer = write_answer(rank_products(data, "kitchen"), bodies_for(*data))
    assert len(answer.picks) == 2
    assert "only 2 products" in answer.message and "instead of 3" in answer.message
    assert answer.needs_more_threads


def test_one_pick_is_singular():
    data = mentions(3, "A Knife")
    answer = write_answer(rank_products(data, "kitchen"), bodies_for(*data))
    assert "only 1 product " in answer.message


def test_picks_lost_to_failed_quotes_count_in_the_message():
    data = mentions(3, "A Knife") + mentions(3, "B Knife") + mentions(3, "C Knife")
    answer = write_answer(rank_products(data, "kitchen"), bodies_for(*data[:6]))  # C's comments are gone
    assert len(answer.picks) == 2 and "only 2 products" in answer.message


# --- Output: structured for the web, and as text ---

def test_the_answer_turns_into_json():
    ranking, bodies, _ = kitchen_case()
    data = json.loads(json.dumps(answer_to_dict(write_answer(ranking, bodies, "chef knife"))))
    assert data["product_type"] == "chef knife"
    first = data["picks"][0]
    assert first["name"] == "Tojiro DP Gyuto"
    assert first["breakdown"]["kind_bonus"] > 0
    assert set(first["quotes"][0]) == {"text", "comment_id", "url", "badges"}


def test_the_answer_holds_no_quote_except_the_verified_ones():
    # The structured answer must not carry the raw mentions (which hold unchecked quotes) along with it.
    ranking, bodies, items = kitchen_case()
    answer = write_answer(ranking, bodies)
    shown = {q["text"] for q in _all_quotes(answer_to_dict(answer))}
    assert all(item.quote not in json.dumps(answer_to_dict(answer)) for item in items if item.quote not in shown)


def _all_quotes(data):
    for pick in data["picks"]:
        yield from pick["quotes"] + pick["downsides"]
    for item in data["skip"]:
        yield from item["quotes"]
    for item in data["look_for"]:
        yield item["quote"]


def test_the_markdown_shows_names_quotes_badges_links_and_the_breakdown():
    ranking, bodies, _ = kitchen_case()
    answer = write_answer(ranking, bodies, "chef knife")
    text = render_markdown(answer)
    tojiro = answer.picks[0]
    for expected in (
        "chef knife", "## 1. Tojiro DP Gyuto", tojiro.reason, tojiro.support, tojiro.quotes[0].text,
        "3 years of use", tojiro.quotes[0].url, wording.BREAKDOWN_HEADING, "kind bonus",
        wording.LOOK_FOR_HEADING, wording.SKIP_HEADING, "Tefal Knife", "The handle gets slippery when wet.",
    ):
        assert expected in text, expected
    assert "Looks cheap, never tried it." not in text  # a low voice's warning is not a known downside


def test_quotes_written_over_several_lines_render_on_one():
    data = [mention("A Knife", "t1", quote="Sharp.\nVery sharp.")] + mentions(3, "A Knife", voice="medium")
    text = render_markdown(write_answer(rank_products(data, "kitchen"), bodies_for(*data)))
    assert '"Sharp. Very sharp."' in text


# --- Comment bodies, read from threads ---

def test_comment_bodies_holds_only_readable_comments():
    thread = Thread.model_validate(make_thread(comments=[
        make_comment("c1aaaa", body="Still here."),
        make_comment("c2bbbb", body="[deleted]", status="deleted"),
    ]))
    assert comment_bodies([thread]) == {"c1aaaa": "Still here."}
