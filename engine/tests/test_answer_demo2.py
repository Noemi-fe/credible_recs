"""Noemi's second demo test (12 Oct 2026, a frying pan answer), as rules:

1. a quote that gives no view ("I own one") or is garbled ("I use the gently") doesn't belong in "In their words":
   the sentences before it that state a view or advice are shown with it, or it only makes up a pick's two quotes;
2. "How to take care of it" holds care only: a repair story is left out, and two tips saying the same thing ("wooden or
   silicone utensils only", "no metal utensils") are shown once;
3. swear words are masked on display ("f**k"); the text checked word for word, and live, stays the comment's own;
4. known downsides are shown in proportion: "1 of 15 credible voices warned against it:";
5. the score breakdown is off the answer card (it stays in the API's JSON; the how page explains scoring);
6. the page never draws an answer that arrives after a newer search has started.

All text is made up (engine/tests/ranking_factories.py).
"""

import json
import re

import pytest

from engine import answer as wording
from engine.answer import answer_to_dict, masked, render_markdown, unverified_claims, write_answer
from engine.care_tips import CareTip, CareTips, is_repair, similar_tips
from engine.rank import rank_products
from engine.tests.ranking_factories import bodies_for, mention, mentions


def pan_answer(items, bodies, **kwargs):
    return write_answer(rank_products(items, "kitchen"), bodies, "frying pan", **kwargs)


# --- 1. Quotes that give a view ---

def test_a_bare_quote_takes_in_the_advice_before_it_and_a_garbled_one_only_makes_up_the_minimum():
    good = mention("Acme pan", "t1", quote="Our Acme pan has lasted ten years, love it.")
    garbled = mention("Acme pan", "t2", weight=0.9, quote="I always liked my Acme pans but I use the gently.")
    bare = mention("Acme pan", "t1", weight=0.8, quote="I own an Acme.")
    advice = "Buy a decent pan, keep the heat low and wash it by hand. I own an Acme."
    bodies = bodies_for(good, garbled) | {bare.comment_id: advice}
    quotes = [q.text for q in pan_answer([good, garbled, bare], bodies).picks[0].quotes]
    assert quotes == [good.quote, advice]
    assert unverified_claims(pan_answer([good, garbled, bare], bodies), bodies) == []
    # With nothing before the bare quote, the garbled one and then the bare one only make up the two quotes a pick needs.
    bodies = bodies_for(good, garbled, bare)
    assert [q.text for q in pan_answer([good, garbled, bare], bodies).picks[0].quotes] == [good.quote, garbled.quote]


@pytest.mark.parametrize("quote, garbled", [
    ("I always liked them but I use the gently.", True),
    ("Great pan, I use the.", True),
    ("I use the pan gently and it lasts.", False),
    ("A really lovely pan.", False),
])
def test_a_garbled_quote(quote, garbled):
    from engine.answer import _garbled

    assert _garbled(quote) is garbled


# --- 2. Care tips are care ---

def tip(text: str, comment: str, is_kind: bool = False, quote: str | None = None) -> CareTip:
    return CareTip(about="Acme pan", is_kind=is_kind, tip=text, quote=quote or f"Honestly, {text}, every time.",
                   thread_id="t1", comment_id=comment,
                   comment_url=f"https://www.reddit.com/r/test/comments/t1/comment/{comment}/", voice="high",
                   author=comment)


def care_answer(own=(), kind=()):
    items = mentions(3, "Acme pan")
    bodies = bodies_for(*items, *own, *kind)
    return pan_answer(items, bodies, care={"acme-pan": CareTips(list(own), list(kind))}), bodies


@pytest.mark.parametrize("text", ["a pot bent from a drop can be pushed back into shape", "bend the rim back",
                                  "straighten a warped base on a flat stone", "replace the thermal fuse"])
def test_a_repair_story_is_a_repair(text):
    assert is_repair(text)


def test_replacing_the_product_when_it_wears_out_is_care_not_a_repair():
    assert not is_repair("don't overheat, wash gently, replace when the coating is damaged")
    assert not is_repair("replace it once the coating flakes")


def test_repairs_are_left_out_of_how_to_take_care_of_it():
    repair = tip("a pot bent from a drop can be pushed back into shape", "cRep")
    upkeep = tip("no high heat on an empty burner", "cUp", is_kind=True)
    answer, bodies = care_answer(own=[repair], kind=[upkeep])
    assert answer.picks[0].care == []
    assert [c.tip for c in answer.care_note] == ["No high heat on an empty burner."]
    assert unverified_claims(answer, bodies) == []


def test_tips_saying_the_same_about_utensils_are_shown_once():
    assert similar_tips("wooden or silicone utensils only", "no metal utensils")
    assert similar_tips("avoid metal spatulas", "use silicone utensils only")
    assert not similar_tips("no metal utensils", "hand wash only")
    answer, _ = care_answer(own=[tip("wooden or silicone utensils only", "cW"), tip("no metal utensils", "cM")])
    assert [c.tip for c in answer.picks[0].care] == ["Wooden or silicone utensils only."]


# --- 3. Swear words, masked on display only ---

def test_swear_words_are_masked_on_display_and_the_checked_text_stays_the_comments_own():
    assert masked("I didn't want to fuck up the coating") == "I didn't want to f**k up the coating"
    assert masked("Shitty handle, fucking heavy.") == "S****y handle, f*****g heavy."
    assert masked("Scunthorpe shiitake mushrooms, a dickens of a pan") == "Scunthorpe shiitake mushrooms, a dickens of a pan"
    sweary = mention("Acme pan", "t1", quote="The Acme pan is fucking great, years on.")
    items = [sweary] + mentions(2, "Acme pan", threads=("t2", "t1"))
    bodies = bodies_for(*items)
    answer = pan_answer(items, bodies)
    # Changed on purpose, 19 Oct 2026 (round 3, the final review: a pick's first quote doesn't swear): the sweary quote
    # now comes after the clean ones (engine.answer._unfit_first), still shown and still checked as the comment's own
    # words. Was: shown first.
    assert answer.picks[0].quotes[0].text != sweary.quote
    assert sweary.quote in [q.text for q in answer.picks[0].quotes]  # what is checked, word for word and live
    assert unverified_claims(answer, bodies) == []
    text = render_markdown(answer)
    assert "f*****g great" in text and "fucking" not in text


def test_the_page_masks_swear_words_with_the_same_list():
    from engine.web import search_page

    html = search_page().decode("utf-8")
    settings = json.loads(html.split('<script type="application/json" id="settings">')[1].split("</script>")[0])
    assert settings["wording"]["masked_words"] == list(wording.MASKED_WORDS)
    assert "masked(quote.text)" in html and "masked(item.tip)" in html


# --- 4. Known downsides in proportion ---

def test_a_lone_downside_says_how_many_credible_voices_warned_out_of_all():
    praise = mentions(14, "Acme pan", threads=("t1", "t2"))
    warning = mention("Acme pan", "t1", stance="warn", voice="medium", quote="My Acme pan fell apart in months.")
    answer = pan_answer(praise + [warning], bodies_for(*praise, warning))
    pick = answer.picks[0]
    assert pick.downsides_share == "1 of 15 credible voices warned against it:"
    assert [q.text for q in pick.downsides] == [warning.quote]
    text = render_markdown(answer)
    assert text.index(wording.DOWNSIDES_HEADING) < text.index(pick.downsides_share) < text.index(warning.quote)
    assert answer_to_dict(answer)["picks"][0]["downsides_share"] == pick.downsides_share


def test_a_pick_with_no_downside_has_no_share_line():
    praise = mentions(3, "Acme pan")
    pick = pan_answer(praise, bodies_for(*praise)).picks[0]
    assert pick.downsides == [] and pick.downsides_share is None


# --- 5. The score breakdown is off the card ---

def test_the_score_breakdown_is_off_the_answer_card_but_stays_in_the_json():
    praise = mentions(3, "Acme pan")
    answer = pan_answer(praise, bodies_for(*praise))
    assert wording.BREAKDOWN_HEADING not in render_markdown(answer)
    assert answer_to_dict(answer)["picks"][0]["breakdown"]["credible_recommends"] == 3
    from engine.web import search_page

    html = search_page().decode("utf-8")
    card = re.search(r"function pickCard\(pick\) \{(.*?)\n  \}", html, re.DOTALL).group(1)
    assert "breakdown" not in card


# --- 6. A slower, older answer is never drawn ---

def test_the_page_ignores_an_answer_that_arrives_after_a_newer_search_started():
    # Noemi, 12 Oct 2026: she typed "pot" while a slow frying pan answer was loading, and got the frying pan answer.
    # The search button stayed disabled while loading, so her new search never started. Now a new search can start at
    # any time: it cancels the older request (AbortController) and an older answer is never drawn (the search number).
    from engine.web import search_page

    html = search_page().decode("utf-8")
    loading = re.search(r"function startLoading\(\) \{(.*?)\n  \}", html, re.DOTALL).group(1)
    assert "button.disabled = true" not in loading
    fetching = re.search(r"async function fetchAnswer\(request, signal\) \{(.*?)\n  \}", html, re.DOTALL).group(1)
    assert "signal" in fetching.split("fetch(")[1]
    searching = re.search(r"async function search\(text, addToHistory\) \{(.*?)\n  \}", html, re.DOTALL).group(1)
    assert "new AbortController()" in searching and ".abort()" in searching
    assert searching.index("if (mine !== latest") < searching.index("showOnly(...shown)")


def test_the_share_line_counts_as_the_mixed_opinions_line_does():
    # A brand pick also shows warnings about its own products under it: the share line and the mixed-opinions line
    # count the same writers, so the two never give different numbers.
    praise = mentions(4, "Acme pans")
    own = [mention("Acme pans", "t1", stance="warn", voice="medium", quote=f"Acme pans chipped, writer {n}.")
           for n in range(2)]
    line = [mention("Acme Pro pan", "t2", stance="warn", voice="medium", quote="The Acme Pro pan warped.")]
    items = praise + own
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items, *line), "frying pan",
                          more_downsides={"acme-pans": line})
    pick = answer.picks[0]
    assert pick.disagreement.endswith("3 credible voices.") and pick.downsides_share.startswith("3 of 7 ")
