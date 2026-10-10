"""Module 7, answer writing: the top 3 picks from a fixed template, showing only quotes re-verified word for word.

The guardrail is the point of most of these tests: a planted quote that isn't in its comment, a comment
deleted since, or a quote over the word limit must never reach the answer, in any form (structured or text).
All data is made up (engine/tests/ranking_factories.py and factories.py).
"""

import dataclasses
import json
from datetime import date
from itertools import count

import pytest

from engine import answer as wording
from engine.answer import ShownQuote, answer_to_dict, comment_bodies, render_markdown, unverified_claims, write_answer
from engine.care_tips import CareTip, CareTips
from engine.config import (CARE_NOTE_TIPS, CARE_TIPS_PER_PICK, MIN_QUOTES_PER_PICK, PRICE_MAX_AGE_DAYS, QUOTE_MAX_WORDS,
                           QUOTES_PER_PICK)
from engine.models import Thread
from engine.prices import Price, PriceCheck
from engine.query import Budget
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
    # The quotes name the product: since 10 Oct 2026 one that names nothing and gives no view only makes up the
    # minimum (test_a_quote_that_neither_names_the_product_nor_gives_a_view_only_makes_up_the_minimum).
    lodge = [
        mention("Lodge Skillet", "t1", voice="medium", evidence="short-term use", quote="Medium short quote on the Lodge."),
        mention("Lodge Skillet", "t2", quote="High long quote on the Lodge."),
        mention("Lodge Skillet", "t1", voice="medium", quote="Medium long quote on the Lodge."),
        mention("Lodge Skillet", "t2", voice="low", quote="Low voice quote on the Lodge."),
        mention("Lodge Skillet", "t1", evidence="no first-hand use", quote="Hearsay quote on the Lodge."),
    ]
    answer = write_answer(rank_products(lodge, "kitchen"), bodies_for(*lodge))
    assert [q.text for q in answer.picks[0].quotes] == [
        "High long quote on the Lodge.", "Medium long quote on the Lodge.", "Medium short quote on the Lodge."
    ]


def test_each_quote_carries_its_badges_or_a_plain_fallback():
    ranking, bodies, _ = kitchen_case()
    tojiro, _, victorinox = write_answer(ranking, bodies).picks
    assert tojiro.quotes[0].badges == ("3 years of use",)
    assert victorinox.quotes[0].badges == ("medium-credibility voice", "short-term use")  # no badges were given


# --- The guardrail: every quote shown is re-verified word for word ---

def test_a_planted_fake_quote_is_dropped_and_never_shown():
    real = mentions(3, "Tojiro DP Gyuto", voice="medium")
    # The most credible, and naming its product, so it would be shown first (quotes naming the product come first
    # since 10 Oct 2026).
    fake = mention("Tojiro DP Gyuto", "t1", quote="Tojiro: " + FAKE)
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
    # Names it and gives a view, so it's tried first (10 Oct 2026).
    long_quote = "Tojiro is great " + " ".join(["word"] * QUOTE_MAX_WORDS) + " more."
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


def moisturiser_case(aha_quotes: tuple[str, ...]):
    """A moisturiser ranking with three kinds: "AHA" (its notes' quotes as given), "Squalane oil" and "Ceramides"."""
    items = mentions(3, "Acme cream", category="skincare") + mentions(3, "Bolt lotion", category="skincare")
    notes = ([note("AHA", f"t{i % 2 + 1}", quote=quote) for i, quote in enumerate(aha_quotes)]
             + [note("Squalane oil", "t1", quote="Plain old squalane oil on top."),
                note("Ceramides", "t2", quote="Anything with ceramides helped my dry patches.")])
    return rank_products(items, "skincare", notes, {}), bodies_for(*items, *notes)


def test_skincare_advice_about_another_type_of_product_is_left_out():
    # Found in b04, 10 Oct 2026: "fragrance-free moisturiser for very dry skin in winter" showed "Look for: AHA" and
    # "Look for: BHA", whose notes were about exfoliants. In skincare each type does its own job, so a kind whose name
    # and notes name another type and never the one asked for gives no advice here.
    ranking, bodies = moisturiser_case(("Try an AHA like glycolic acid for smoothness.", "Exfoliants with aha work best for me."))
    shown = [item.kind for item in write_answer(ranking, bodies, "moisturiser").look_for]
    assert "AHA" not in shown and {"Squalane oil", "Ceramides"} <= set(shown)
    assert "AHA" in [item.kind for item in write_answer(ranking, bodies, "exfoliant").look_for]  # its own type
    # A note that ties it to the type asked for keeps it: an AHA lotion is a moisturiser.
    ranking, bodies = moisturiser_case(("An AHA lotion fixed my rough dry legs.", "Try an AHA like glycolic acid for smoothness."))
    assert "AHA" in [item.kind for item in write_answer(ranking, bodies, "moisturiser").look_for]


def test_kitchen_advice_about_another_kind_of_pan_stays():
    # Another kind of pan is a real alternative: "Look for: cast iron" answers a PFAS-free non-stick pan request well.
    items = mentions(3, "Acme pan") + mentions(3, "Bolt pan")
    notes = [note("Cast iron", "t1", quote="A cast iron skillet will outlive any non-stick pan."),
             note("Cast iron", "t2", quote="Get a cast iron skillet instead.")]
    ranking = rank_products(items, "kitchen", notes, {})
    shown = [item.kind for item in write_answer(ranking, bodies_for(*items, *notes), "frying pan").look_for]
    assert shown == ["Cast iron"]


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


def test_one_comment_backing_two_kinds_is_shown_once():
    # Found on the demo, 10 Oct 2026: one sentence advising cast iron or carbon steel was the strongest note
    # for both kinds, so the same quote showed twice. A kind takes another credible note when it has one; otherwise
    # the two kinds share one line.
    shared = "After that, buy a cast iron pan or else a carbon steel one."
    both = [note("Cast iron", comment="c_both", quote=shared, weight=0.9),
            note("Carbon steel", comment="c_both", quote=shared, weight=0.8)]
    look_for = write_answer(rank_products([], "kitchen", both), bodies_for(*both)).look_for
    assert [(item.kind, item.advice) for item in look_for] == [("Cast iron or Carbon steel", wording.LOOK_FOR)]
    assert [item.quote.text for item in look_for] == [shared]

    own = note("Carbon steel", comment="c_own", quote="Carbon steel heats up fast and lasts forever.", weight=0.5)
    look_for = write_answer(rank_products([], "kitchen", both + [own]), bodies_for(*both, own)).look_for
    # Carbon steel now has more support, so it comes first, with its own note; cast iron keeps the shared one.
    assert [(item.kind, item.quote.text) for item in look_for] == [("Carbon steel", own.quote), ("Cast iron", shared)]


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
    data = [mention("A Knife", "t1", quote="A Knife: great.\nVery sharp.")] + mentions(3, "A Knife", voice="medium")
    text = render_markdown(write_answer(rank_products(data, "kitchen"), bodies_for(*data)))
    assert '"A Knife: great. Very sharp."' in text


# --- Comment bodies, read from threads ---

def test_comment_bodies_holds_only_readable_comments():
    thread = Thread.model_validate(make_thread(comments=[
        make_comment("c1aaaa", body="Still here."),
        make_comment("c2bbbb", body="[deleted]", status="deleted"),
    ]))
    assert comment_bodies([thread]) == {"c1aaaa": "Still here."}


# --- Review fixes, 9 Oct 2026 ---

def answer_with_quote(text: str, comment_id: str = "cQ1") -> wording.Answer:
    """A finished answer whose only quote is `text`, from comment `comment_id`."""
    item = wording.SkipItem("acme-kettle", "Acme kettle", "Warned against.", [ShownQuote(text, comment_id, "https://example.com/c", ())])
    return wording.Answer("kitchen", None, [], [], [item], None, True, 0)


QUOTING_REPLY = "&gt; The Acme kettle broke after a week.\nWorst purchase ever, never buy the Acme kettle.\n\nReally? Mine is fine."


def test_a_quote_from_a_quoted_block_never_passes_the_answer_check():
    # Someone else's words, quoted with ">" (the first line) or carried on by the next line of the same block.
    for text in ("The Acme kettle broke after a week.", "Worst purchase ever, never buy the Acme kettle."):
        problems = unverified_claims(answer_with_quote(text), {"cQ1": QUOTING_REPLY})
        assert len(problems) == 1 and "quoted block" in problems[0] and "cQ1" in problems[0]
    assert unverified_claims(answer_with_quote("Mine is fine."), {"cQ1": QUOTING_REPLY}) == []


def test_a_quote_from_a_quoted_block_is_never_shown():
    warnings = [mention("Acme kettle", f"t{i % 2 + 1}", stance="warn", comment=f"cQ{i}", quote="Worst purchase ever, never buy the Acme kettle.")
                for i in range(3)]
    answer = write_answer(rank_products(warnings, "kitchen"), {m.comment_id: QUOTING_REPLY for m in warnings})
    assert answer.skip == [] and answer.quotes_dropped == 3
    assert "Worst purchase" not in shown_text(answer)


def test_a_comment_written_entirely_as_a_quote_block_passes_when_no_one_else_wrote_it():
    body = "> **Best:** Hada Labo Gokujyun lotion.\nIt made my dry skin plump in a week."
    quote = "It made my dry skin plump in a week."
    assert unverified_claims(answer_with_quote(quote), {"cQ1": body}) == []
    copied = {"cQ1": body, "cQ2": f"Hada Labo Gokujyun lotion. {quote}"}
    assert "quoted block" in unverified_claims(answer_with_quote(quote), copied)[0]


def test_the_answer_check_counts_the_words_the_quote_matches():
    words = [f"word{n}" for n in range(QUOTE_MAX_WORDS + 30)]
    body = "I love the Acme kettle. " + " ".join(words)
    quote = "&#32;".join(["I", "love", "the", "Acme", "kettle."] + words)
    problems = unverified_claims(answer_with_quote(quote), {"cQ1": body})
    assert len(problems) == 1 and f"limit is {QUOTE_MAX_WORDS}" in problems[0]


def test_the_quote_shown_is_the_comments_own_text_with_entities_read():
    # The AI copies Reddit's stored text ("&amp;"); the reader should see "&", and only words the comment has.
    body = "Some context.\n\nFits 1.7 L &amp; boils in 3 minutes, love it. And one more line."
    items = [mention("Acme kettle", f"t{i % 2 + 1}", comment=f"cE{i}", quote="Fits 1.7 L &amp; boils in 3 minutes, love it.")
             for i in range(3)]
    answer = write_answer(rank_products(items, "kitchen"), {m.comment_id: body for m in items})
    shown = [q.text for q in answer.picks[0].quotes]
    assert shown and all(text == "Fits 1.7 L & boils in 3 minutes, love it." for text in shown)
    assert "&amp;" not in shown_text(answer)
    assert unverified_claims(answer, {m.comment_id: body for m in items}) == []


@pytest.mark.parametrize("body, shown", [
    ("I have sworn by **CosRX Blackhead power liquid** for years now.",
     "I have sworn by CosRX Blackhead power liquid for years now."),
    ("It is *really* gentle and ~~cheap~~ affordable, great.", "It is really gentle and cheap affordable, great."),
    ("My __favourite__ kettle, set to 80_C every day.", "My favourite kettle, set to 80_C every day."),
    # Escaped marks (Reddit's editor writes "\\*lot\\*"): shown as the word, never "\\lot\\" (b10, 10 Oct 2026, late).
    ("I cook a \\*lot\\* of eggs in my Acme pan.", "I cook a lot of eggs in my Acme pan."),
])
def test_a_quote_is_shown_without_the_writers_bold_or_italics(body, shown):
    # Found in the blind-test dry run, 10 Oct 2026: Reddit's "**" showed as stars on the web card and in the blind
    # test's plain template. The check ignores these marks, so the words shown are still the comment's own.
    items = [mention("Acme kettle", f"t{i % 2 + 1}", comment=f"cB{i}", quote=body) for i in range(3)]
    answer = write_answer(rank_products(items, "kitchen"), {m.comment_id: body for m in items})
    assert {q.text for q in answer.picks[0].quotes} == {shown}
    assert unverified_claims(answer, {m.comment_id: body for m in items}) == []


def test_quotes_that_name_the_product_are_shown_before_ones_that_dont():
    # Found reading the blind-test dry run, 10 Oct 2026: a line that only opened a list of other cleansers was shown
    # for a cleanser. Out of context, a quote that never names the product says little, so among the credible ones,
    # those naming it (its brand, a short name such as "BOJ", or a model code such as "C2") come first.
    vague = mention("Acme kettle", "t1", weight=0.9, quote="Love it, works great every single morning.")
    named = [mention("Acme kettle", "t2", weight=0.5, quote="My Acme has lasted 6 years."),
             mention("Acme kettle", "t1", weight=0.4, quote="The acme kettle still boils fast.")]
    items = [vague, *named]
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items))
    assert [q.text for q in answer.picks[0].quotes][:2] == [m.quote for m in named]
    assert vague.quote in [q.text for q in answer.picks[0].quotes]  # still shown when there's room


def test_among_equally_clear_quotes_those_about_what_was_asked_come_first():
    # Found reading the blind-test view, 10 Oct 2026 (late): "electric kettle that lasts 10+ years" showed the Fellow
    # Stagg EKG with a much-upvoted comment about a detail of its handle first, though three of its
    # writers spoke of long-term use. Among quotes as clear as each other (naming the product and giving a view), those
    # that themselves talk about what the request asks for come first (the quote, not the rest of its comment: a
    # lukewarm "fine for barrier protection" from a comment about dry skin elsewhere doesn't jump ahead).
    from engine.config import NEEDS
    from engine.needs import Need

    lasting = (Need("lasting", NEEDS["lasting"]),)
    handle = mention("Acme kettle", "t1", weight=0.9, evidence="short-term use",
                     quote="I love my Acme but the metal part on the handle is odd.")
    about_it = [mention("Acme kettle", "t2", weight=0.4, evidence="short-term use",
                        quote="My Acme has lasted 9 years, I love it."),
                mention("Acme kettle", "t1", weight=0.3, quote="Love my Acme, still going after 6 years.")]  # long use
    items = [handle, *about_it]
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items), needs=lasting)
    assert [q.text for q in answer.picks[0].quotes] == [m.quote for m in about_it] + [handle.quote]
    plain = write_answer(rank_products(items, "kitchen"), bodies_for(*items))  # nothing asked: credibility decides
    assert plain.picks[0].quotes[0].text == handle.quote


def test_a_quote_that_neither_names_the_product_nor_gives_a_view_only_makes_up_the_minimum():
    # Found reading b08, 10 Oct 2026: a one-line reply about sticking with cast iron was shown for Griswold and for
    # Wagner (the comment named them in a sentence the AI didn't quote). It says nothing about either, so such a
    # quote is shown only when the pick would otherwise have fewer than MIN_QUOTES_PER_PICK.
    empty = mention("Acme skillet", "t1", weight=0.9, quote="nah, I'll keep using my cast iron, ha.")
    full = [mention("Acme skillet", "t2", weight=0.5, quote="My Acme has lasted 6 years."),
            mention("Acme skillet", "t1", weight=0.4, quote="Love it, works great every single morning.")]
    items = [empty, *full]
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items))
    assert [q.text for q in answer.picks[0].quotes] == [m.quote for m in full]
    # With one quote that says something, the most credible empty one makes up the two; the other isn't needed.
    other_empty = mention("Acme skillet", "t2", weight=0.8, quote="Same here, honestly.")
    items = [empty, other_empty, full[0]]
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items))
    assert [q.text for q in answer.picks[0].quotes] == [full[0].quote, empty.quote]
    assert MIN_QUOTES_PER_PICK == 2


def test_a_plural_of_the_brand_names_the_product():
    from engine.answer import _names_product

    assert _names_product("We still cook on two old wagners from my aunt.", "Wagner", "kitchen")
    assert not _names_product("We still cook on two old wagons from my aunt.", "Wagner", "kitchen")


@pytest.mark.parametrize("name, quote", [
    ("Prequel's Gleanser", "Prequel gleanser is great for oily skin."),  # the name's possessive
    ("All-Clad non-stick pans", "I bought some All clad non stick pans last year."),  # a hyphen written as a space
    ("Prequel Gleanser", "Prequel's cleanser is my favourite."),  # the quote's possessive
])
def test_a_brand_written_slightly_differently_still_names_the_product(name, quote):
    from engine.answer import _names_product

    assert _names_product(quote, name, "skincare")


@pytest.mark.parametrize("quote, says_something", [
    ("nah, I'll keep using my cast iron, ha.", False),
    ("I'm on my fifth bottle of it already", True),  # points at it
    ("I've had mine for ages and only minimal wear on the burrs.", True),
    ("I like both the gel and the lotion as an everyday moisturiser.", True),  # "I like" is a view
    ("I would like a new pan for my birthday.", False),  # wanting isn't a view
])
def test_what_says_something_about_the_product(quote, says_something):
    from engine.answer import _says_something

    assert _says_something(mention("Acme skillet", quote=quote)) is says_something


def test_a_quote_naming_the_product_and_saying_what_the_writer_thinks_comes_first():
    # Found reading b09, 10 Oct 2026: a writer listing the grinders they own named the C2 but said nothing about it. Quotes that name the product and give a view or an experience come first.
    owns = mention("Timemore C2", "t1", weight=0.6, quote="I own a Baratza Encore, a Timemore C2 (in the office) and a JX.")
    views = [mention("Timemore C2", "t2", weight=0.3, quote="I've used a C2 nearly daily for pour over and it's great."),
             mention("Timemore C2", "t1", weight=0.28, quote="I'd recommend going for a C2 if you're getting a grinder.")]
    items = [owns, *views]
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items))
    assert [q.text for q in answer.picks[0].quotes][:2] == [m.quote for m in views]


@pytest.mark.parametrize("name, quote", [
    ("Sage (their electric kettles)", "My Breville is still going strong after 8 years"),
    ("Beauty of Joseon Revive Eye Serum: Ginseng + Retinal", "I've been loving the BOJ eye serum all over my face!"),
    ("Timemore C2", "The C2 is great for pour-over at home."),
])
def test_a_short_name_or_model_code_names_the_product(name, quote):
    from engine.answer import _names_product

    assert _names_product(quote, name, "skincare" if "Joseon" in name else "kitchen")
    assert not _names_product("Some others I've owned without any trouble:", name, "kitchen")


def test_among_quotes_that_dont_name_the_product_one_giving_a_view_comes_first():
    # Found reading b04, 10 Oct 2026 (night): Etude's second quote was a writer still looking for a richer cream (no
    # name, no view), ahead of a writer saying they now swear by it after years of trying others.
    plain = mention("Acme cream", "t1", weight=0.9, category="skincare",
                    quote="Haven't found a richer one, it's my main for now.")
    view = mention("Acme cream", "t2", weight=0.5, category="skincare",
                   quote="After years of trying others, I'm a convert to it.")
    named = mention("Acme cream", "t1", weight=0.3, category="skincare", quote="I love the Acme cream.")
    items = [plain, view, named]
    answer = write_answer(rank_products(items, "skincare"), bodies_for(*items))
    assert [q.text for q in answer.picks[0].quotes][:2] == [named.quote, view.quote]


def test_the_writers_own_name_for_the_product_names_it():
    # Found reading b06, 10 Oct 2026 (night): the kettle shown as "Fellow Stagg EKG" (its brand taken from a longer
    # name) had its writers' quotes saying "Stagg" read as naming nothing, so a writer's decade without a failure was
    # left out and two quotes about a detail of its handle were shown. The name the writer used names it too.
    from engine.answer import _names_product

    quote = "Bought the Stagg EKG at launch, its daily use since."
    assert not _names_product(quote, "Fellow Stagg EKG", "kitchen")  # the shown name's first word is the brand
    assert _names_product(quote, "Fellow Stagg EKG", "kitchen", written_as="my Stagg EKG")  # "my" isn't a name
    assert not _names_product("A gooseneck pours better.", "Fellow Stagg EKG", "kitchen", written_as="gooseneck kettle")
    named = mention("Fellow Stagg EKG", "t1", weight=0.4, written_as="Stagg EKG", quote=quote)
    unnamed = mention("Fellow Stagg EKG", "t2", weight=0.9, written_as="Stagg", quote="Love it, pours so nicely.")
    empty = mention("Fellow Stagg EKG", "t2", weight=0.2, written_as="Stagg", quote="Bought for my partner, who makes tea.")
    items = [named, unnamed, empty]  # three, so it's a pick; the last says nothing, so it isn't shown
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items))
    assert [q.text for q in answer.picks[0].quotes] == [named.quote, unnamed.quote]


@pytest.mark.parametrize("quote", ["Using the same one for a decade now.", "It has never failed."])
def test_time_in_use_and_failing_or_not_are_what_a_writer_went_through(quote):
    # b06, 10 Oct 2026 (night): "years" gave a view, but "a decade" and "never failed" didn't.
    from engine.answer import _gives_a_view

    assert _gives_a_view(quote)


def test_failing_to_do_something_is_not_a_view():
    # Not "failed" alone: a quote about a video reviewer leaving out a feature led a pick's downsides.
    from engine.answer import _gives_a_view

    assert not _gives_a_view("The video failed to show the timer on the cheaper model.")


def test_a_quote_saying_the_opposite_of_what_was_asked_is_shown_last():
    # Found reading b02, 10 Oct 2026: for "doesn't leave a white cast", the first pick's quote said the Etude sunscreen
    # does leave one (its writer recommends it anyway). Such a quote is shown only if nothing else is left.
    against = mention("Etude sunscreen", "t1", weight=0.9, quote="Etude's sunscreen does leave a white cast, but I like it anyway.")
    others = [mention("Etude sunscreen", "t2", weight=0.5, quote="The Etude sunscreen has no white cast at all."),
              mention("Etude sunscreen", "t1", weight=0.4, quote="Etude sunscreen doesn't leave a white cast on me.")]
    items = [against, *others]
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items), asks=("no white cast",))
    assert [q.text for q in answer.picks[0].quotes][:2] == [m.quote for m in others]
    plain = write_answer(rank_products(items, "kitchen"), bodies_for(*items))  # nothing asked: weight decides
    assert plain.picks[0].quotes[0].text == against.quote


@pytest.mark.parametrize("ask, quote, against", [
    ("no white cast", "It leaves a white cast on darker skin.", True),
    ("no white cast", "It does leave a slight white cast.", True),
    ("no white cast", "It doesn't leave a white cast.", False),
    ("no white cast", "No white cast, dries matte.", False),
    ("fragrance-free", "It smells lovely, like roses.", True),
    ("fragrance-free", "It has a strong scent.", True),
    ("fragrance-free", "It's fragrance-free and gentle.", False),
    ("fragrance-free", "No scent at all.", False),
    # Something that lasts (10 Oct 2026, b06: an Oxo pick's first quote had its kettle failing within about a
    # year): failing within days, weeks, months or up to three years is the opposite; after ten years isn't.
    ("lasting", "My kettle stopped working after about a year.", True),
    ("lasting", "Mine died within 6 months.", True),
    ("lasting", "After two years it broke.", True),
    ("lasting", "The lid cracked within the first year.", True),
    ("lasting", "It broke in 2 weeks.", True),
    ("lasting", "The handle cracked after about 10 years, they sent a new one.", False),
    ("lasting", "I've had it for 12 years and it still works.", False),
    ("lasting", "It broke in nicely after a few weeks of use.", False),  # breaking in a pan is using it, not failing
    ("lasting", "Stopped working after 13 years of daily use.", False),
    # Saying outright it won't last (b10 at 16 threads: a writer happy with their ceramic pans said they weren't BIFL).
    ("lasting", "Decent pans, though they're not buy it for life.", True),
    ("lasting", "Great pan, it just doesn't last.", True),
    ("lasting", "Non-stick coatings won't last, whatever you pay.", True),
    ("lasting", "It isn't BIFL but it's cheap.", True),
    ("lasting", "This one is BIFL, no question.", False),
    ("lasting", "Mine didn't last.", True),
    # A short life said plainly (b06 at 16 threads: a cafe owner's kettles lasting about two years each).
    ("lasting", "At our office each kettle lasts around 2 years.", True),
    ("lasting", "Mine lasted about 3 years.", True),
    ("lasting", "These pans last a few months at most.", True),
    ("lasting", "It has lasted 2 years so far and is still going strong.", False),
    ("lasting", "Mine lasted 15 years.", False),
    ("lasting", "It's lasted 3 years and counting.", False),
])
def test_what_says_the_opposite_of_a_request(ask, quote, against):
    from engine.answer import _says_the_opposite

    assert _says_the_opposite(quote, (ask,)) is against


# --- Prices and budgets (decision 11, Noemi, 9 Oct 2026) ---

CHECKED = date(2026, 10, 9)
UNDER_100 = Budget(max=100, currency="GBP")


def shop_price(product: str = "Tojiro DP Gyuto", amount: float = 120.0, currency: str = "GBP", checked_on: date = CHECKED) -> Price:
    return Price(product=product, category="kitchen", price=amount, currency=currency, shop="Made-up Knife Shop",
                 url="https://shop.example/tojiro-dp-gyuto", checked_on=checked_on)


def test_each_pick_shows_its_price_with_the_shop_and_the_date_or_says_it_is_not_checked():
    ranking, bodies, _ = kitchen_case()
    prices = {"tojiro-dp-gyuto": PriceCheck(shop_price(), "no budget")}
    tojiro, global_g2, _ = write_answer(ranking, bodies, "chef knife", prices).picks
    assert tojiro.price.text == "£120 at Made-up Knife Shop, checked 9 Oct 2026"
    assert (tojiro.price.amount, tojiro.price.currency, tojiro.price.shop) == (120.0, "GBP", "Made-up Knife Shop")
    assert tojiro.price.url == "https://shop.example/tojiro-dp-gyuto" and tojiro.price.checked_on == "2026-10-09"
    assert tojiro.price.budget_status is None and tojiro.price.budget_note is None
    assert global_g2.price.text == wording.PRICE_UNKNOWN == "Price not checked yet"
    assert global_g2.price.amount is None and global_g2.price.url is None


def test_without_any_price_list_every_pick_says_its_price_is_not_checked():
    ranking, bodies, _ = kitchen_case()
    assert {pick.price.text for pick in write_answer(ranking, bodies).picks} == {wording.PRICE_UNKNOWN}


def test_amounts_are_written_with_their_currency():
    ranking, bodies, _ = kitchen_case()
    for amount, currency, written in ((119.99, "GBP", "£119.99"), (1200.0, "EUR", "€1,200"), (85.5, "USD", "$85.50")):
        prices = {"tojiro-dp-gyuto": PriceCheck(shop_price(amount=amount, currency=currency), "no budget")}
        assert write_answer(ranking, bodies, prices=prices).picks[0].price.text.startswith(written + " at ")


@pytest.mark.parametrize("status, expected", [
    ("within", wording.BUDGET_WITHIN.format(max="£100")),
    ("unknown", wording.BUDGET_NOT_CHECKED.format(max="£100", why=wording.BUDGET_WHY_UNKNOWN)),
    ("other currency", wording.BUDGET_NOT_CHECKED.format(max="£100", why=wording.BUDGET_WHY_CURRENCY.format(currency="EUR"))),
    ("out of date", wording.BUDGET_NOT_CHECKED.format(max="£100", why=wording.BUDGET_WHY_OLD.format(days=PRICE_MAX_AGE_DAYS))),
])
def test_each_pick_says_how_its_price_compares_with_the_budget(status, expected):
    ranking, bodies, _ = kitchen_case()
    known = None if status == "unknown" else shop_price(amount=90.0, currency="EUR" if status == "other currency" else "GBP")
    pick = write_answer(ranking, bodies, prices={"tojiro-dp-gyuto": PriceCheck(known, status, UNDER_100)}).picks[0]
    assert pick.price.budget_status == status
    assert pick.price.budget_note == expected
    assert "£100" in expected


def test_a_shop_link_that_is_not_https_is_never_passed_on():
    # The price list refuses such a link when it loads; this is the second lock, in case one is ever built by hand.
    ranking, bodies, _ = kitchen_case()
    unsafe = Price.model_construct(product="Tojiro DP Gyuto", category="kitchen", price=120.0, currency="GBP",
                                   shop="Made-up Knife Shop", url="http://shop.example/tojiro", checked_on=CHECKED)
    pick = write_answer(ranking, bodies, prices={"tojiro-dp-gyuto": PriceCheck(unsafe, "no budget")}).picks[0]
    assert pick.price.url is None and pick.price.amount == 120.0


def test_the_price_turns_into_json():
    ranking, bodies, _ = kitchen_case()
    prices = {"tojiro-dp-gyuto": PriceCheck(shop_price(amount=90.0), "within", UNDER_100)}
    data = json.loads(json.dumps(answer_to_dict(write_answer(ranking, bodies, prices=prices))))
    price = data["picks"][0]["price"]
    assert set(price) == {"text", "amount", "currency", "shop", "url", "checked_on", "budget_status", "budget_note"}
    assert price["amount"] == 90.0 and price["budget_status"] == "within" and price["checked_on"] == "2026-10-09"
    assert data["picks"][1]["price"]["text"] == wording.PRICE_UNKNOWN


def test_the_markdown_shows_the_price_the_shop_link_and_the_budget_note():
    ranking, bodies, _ = kitchen_case()
    prices = {"tojiro-dp-gyuto": PriceCheck(shop_price(amount=90.0), "within", UNDER_100)}
    text = render_markdown(write_answer(ranking, bodies, prices=prices))
    assert f"**{wording.PRICE_LABEL}:** £90 at Made-up Knife Shop, checked 9 Oct 2026" in text
    assert f"[{wording.PRICE_LINK_TEXT}](https://shop.example/tojiro-dp-gyuto)" in text
    assert wording.BUDGET_WITHIN.format(max="£100") in text
    assert wording.PRICE_UNKNOWN in text  # the other picks


# --- Care tips: how to take care of it (Noemi, 9 Oct 2026; renamed and split on 11 Oct 2026) ---

_care_ids = count(1)


def care_tip(tip: str, *, is_kind: bool = False, voice: str = "high", quote: str | None = None,
             badges: tuple[str, ...] = ("well upvoted",)) -> CareTip:
    """One credible care tip, from a comment of its own, with a quote of its own unless given."""
    comment = f"cCare{next(_care_ids)}"
    return CareTip(about="chef knife" if is_kind else "Tojiro DP Gyuto", is_kind=is_kind, tip=tip,
                   quote=quote or f"My advice: {tip}, says comment {comment}.", thread_id="t1", comment_id=comment,
                   comment_url=f"https://www.reddit.com/r/test/comments/t1/comment/{comment}/", voice=voice,
                   badges=badges)


def with_care(own=(), kind=(), key="tojiro-dp-gyuto"):
    """The kitchen case, with care tips for one product: (answer, bodies)."""
    ranking, bodies, _ = kitchen_case()
    bodies = bodies | bodies_for(*own, *kind)
    answer = write_answer(ranking, bodies, "chef knife", care={key: CareTips(list(own), list(kind))})
    return answer, bodies


def test_care_heading_wording():
    # Renamed by Noemi on 11 Oct 2026 (was "How to make it last"): the section holds care of the product only.
    assert wording.CARE_HEADING == "How to take care of it"
    assert wording.CARE_NOTE_HEADING == "How to take care of your {product_type}"
    assert CARE_TIPS_PER_PICK == 2 and CARE_NOTE_TIPS == 3


def test_a_pick_shows_its_own_care_tips_and_the_answer_ends_with_the_general_ones():
    # Noemi, 11 Oct 2026: tips about the kind of product ("hone it weekly" for any chef knife) were repeated under
    # every pick. A pick now shows only the tips about itself; the kind's tips are shown once, in a note at the end.
    hand_wash, hone, dry = care_tip("hand wash only"), care_tip("hone it weekly", is_kind=True), care_tip("dry it", is_kind=True)
    answer, bodies = with_care(own=[hand_wash], kind=[hone, dry])
    tojiro, global_g2, victorinox = answer.picks
    assert [c.tip for c in tojiro.care] == ["Hand wash only."]
    assert [c.quote.text for c in tojiro.care] == [hand_wash.quote]
    assert tojiro.care[0].quote.url == hand_wash.comment_url and tojiro.care[0].quote.badges == ("well upvoted",)
    assert global_g2.care == [] and victorinox.care == []
    assert [(c.tip, c.quote.text) for c in answer.care_note] == [("Hone it weekly.", hone.quote), ("Dry it.", dry.quote)]
    assert unverified_claims(answer, bodies) == []


def test_at_most_care_tips_per_pick_and_in_the_note():
    answer, _ = with_care(own=[care_tip(f"tip number {n}") for n in range(4)],
                          kind=[care_tip(f"general tip {n}", is_kind=True) for n in range(5)])
    assert len(answer.picks[0].care) == CARE_TIPS_PER_PICK
    assert len(answer.care_note) == CARE_NOTE_TIPS


def test_the_most_credible_tip_comes_first_within_own_and_kind_tips():
    medium, high = care_tip("oil the blade", voice="medium"), care_tip("use a wooden board")
    kind_medium, kind_high = care_tip("strop it", is_kind=True, voice="medium"), care_tip("hone it", is_kind=True)
    answer, _ = with_care(own=[medium, high], kind=[kind_medium, kind_high])
    # Updated 11 Oct 2026 (Noemi): a pick shows its own tips and the note at the end shows the kind's, so the two are
    # ordered apart (on 10 Oct they were one list, where the high kind tip came before the medium own one). Within each,
    # the most credible writers' tip still comes first.
    assert [c.tip for c in answer.picks[0].care] == ["Use a wooden board.", "Oil the blade."]
    assert [c.tip for c in answer.care_note] == ["Hone it.", "Strop it."]


def test_never_two_care_tips_with_the_same_tip():
    answer, _ = with_care(own=[care_tip("descale every 6 months")],
                          kind=[care_tip("Descale it every 6 months.", is_kind=True), care_tip("use filtered water", is_kind=True)])
    assert [c.tip for c in answer.picks[0].care] == ["Descale every 6 months."]
    assert [c.tip for c in answer.care_note] == ["Use filtered water."]  # the note never repeats a pick's own tip


def test_a_care_tip_written_as_a_sentence_is_shown_as_it_is():
    answer, _ = with_care(own=[care_tip("Hand wash only!")])
    assert answer.picks[0].care[0].tip == "Hand wash only!"


def test_a_tip_that_only_repeats_its_quote_is_shown_once():
    # Found on the demo, 10 Oct 2026: "Plastic or silicone utensils only." was the tip and the whole quote, so it
    # showed twice. A tip that says nothing more than its quote is left empty: the quote alone is the tip.
    same = care_tip("plastic or silicone utensils only", quote="Plastic or silicone utensils only.")
    other = care_tip("hand wash only")
    answer, _ = with_care(own=[same, other])
    assert [c.tip for c in answer.picks[0].care] == ["", "Hand wash only."]
    text = render_markdown(answer)
    assert text.count("Plastic or silicone utensils only.") == 1
    assert '- "Plastic or silicone utensils only." (' in text and "- **Hand wash only.** " in text


def test_a_care_quote_that_fails_is_dropped_never_shown_and_the_next_tip_takes_its_place():
    fake, real = care_tip("hand wash only", quote=FAKE), care_tip("hand wash only")
    ranking, bodies, _ = kitchen_case()
    without = write_answer(ranking, bodies, "chef knife")
    bodies = bodies | bodies_for(real) | {fake.comment_id: "I just hand wash it, honestly."}
    answer = write_answer(ranking, bodies, "chef knife", care={"tojiro-dp-gyuto": CareTips([fake, real], [])})
    assert [c.quote.text for c in answer.picks[0].care] == [real.quote]
    assert FAKE not in shown_text(answer)
    assert answer.quotes_dropped == without.quotes_dropped + 1
    assert unverified_claims(answer, bodies) == []


def test_a_care_quote_whose_comment_is_gone_or_from_a_quoted_block_is_dropped():
    gone, quoted = care_tip("hand wash only"), care_tip("no dishwasher", quote="Never put it in the dishwasher.")
    ranking, bodies, _ = kitchen_case()
    bodies = bodies | {quoted.comment_id: "&gt; Never put it in the dishwasher.\n\nI do, and mine is fine."}
    answer = write_answer(ranking, bodies, care={"tojiro-dp-gyuto": CareTips([gone, quoted], [])})
    assert answer.picks[0].care == []
    assert "dishwasher" not in shown_text(answer) and gone.quote not in shown_text(answer)


def test_care_tips_never_make_a_pick_and_go_only_with_picks():
    # The Tefal knife is on the skip list: its care tips are never shown, and the picks are the same as without care.
    answer, _ = with_care(own=[care_tip("hand wash only")], kind=[care_tip("hone it weekly", is_kind=True)], key="tefal-knife")
    assert [p.name for p in answer.picks] == ["Tojiro DP Gyuto", "Global G-2", "Victorinox Fibrox"]
    assert all(p.care == [] for p in answer.picks) and "hand wash only" not in shown_text(answer).lower()
    assert answer.care_note == []  # the note gathers the shown picks' kind tips only


def test_without_care_tips_every_pick_has_none():
    ranking, bodies, _ = kitchen_case()
    answer = write_answer(ranking, bodies, "chef knife")
    assert all(p.care == [] for p in answer.picks) and answer.care_note == []
    assert wording.CARE_HEADING not in render_markdown(answer)
    assert wording.CARE_NOTE_HEADING.format(product_type="chef knife") not in render_markdown(answer)


def test_the_check_covers_care_quotes():
    answer, bodies = with_care(own=[care_tip("hand wash only")])
    real = answer.picks[0].care[0].quote
    answer.picks[0].care[0] = dataclasses.replace(answer.picks[0].care[0], quote=planted(real))
    problems = unverified_claims(answer, bodies)
    assert len(problems) == 1 and "pick 1" in problems[0] and "care tip" in problems[0]
    assert real.comment_id in problems[0] and FAKE not in problems[0]


def test_the_check_covers_the_care_note():
    answer, bodies = with_care(kind=[care_tip("hone it weekly", is_kind=True)])
    real = answer.care_note[0].quote
    answer.care_note[0] = dataclasses.replace(answer.care_note[0], quote=planted(real))
    problems = unverified_claims(answer, bodies)
    assert len(problems) == 1 and "care note" in problems[0] and FAKE not in problems[0]


def test_a_care_tip_with_no_badges_shows_the_plain_voice_level():
    answer, _ = with_care(own=[care_tip("hand wash only", voice="medium", badges=())])
    assert answer.picks[0].care[0].quote.badges == ("medium-credibility voice",)


def test_the_markdown_shows_how_to_take_care_of_it_under_the_pick():
    hand_wash = care_tip("hand wash only")
    answer, _ = with_care(own=[hand_wash])
    text = render_markdown(answer)
    assert f"**{wording.CARE_HEADING}**" in text
    assert f'- **Hand wash only.** "{hand_wash.quote}" (well upvoted · [{wording.LINK_TEXT}]({hand_wash.comment_url}))' in text
    tojiro = text.split("## 2.")[0]
    assert tojiro.index(wording.DOWNSIDES_HEADING) < tojiro.index(wording.CARE_HEADING) < tojiro.index(wording.BREAKDOWN_HEADING)
    assert text.count(wording.CARE_HEADING) == 1  # only the pick with tips has the heading


def test_the_care_tips_turn_into_json():
    answer, _ = with_care(own=[care_tip("hand wash only")], kind=[care_tip("hone it weekly", is_kind=True)])
    data = json.loads(json.dumps(answer_to_dict(answer)))
    care = data["picks"][0]["care"]
    assert set(care[0]) == {"tip", "quote"} and care[0]["tip"] == "Hand wash only."
    assert set(care[0]["quote"]) == {"text", "comment_id", "url", "badges"}
    assert data["picks"][1]["care"] == []
    assert [item["tip"] for item in data["care_note"]] == ["Hone it weekly."]


def test_the_markdown_ends_with_the_care_note():
    hone = care_tip("hone it weekly", is_kind=True)
    answer, _ = with_care(kind=[hone])
    text = render_markdown(answer)
    heading = f"## {wording.CARE_NOTE_HEADING.format(product_type='chef knife')}"
    assert heading in text and text.index(heading) > text.index(f"## {wording.SKIP_HEADING}")
    assert f'- **Hone it weekly.** "{hone.quote}"' in text
    assert f"**{wording.CARE_HEADING}**" not in text  # no pick has tips of its own
