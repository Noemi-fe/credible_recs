"""The skincare and haircare data round of 17-18 Oct 2026 (ws-data-beauty): mature skin in the words writers use.

Writers in threads about mature skin mostly give their age as a number ("I'm 46", "46F") rather than a decade ("my
40s"), and name what ageing does (sagging, crepey skin, menopause). Those comments talk about mature skin too, so the
need rule (a pick needs a credible recommendation that talks about the request's needs) can find them. All comments
here are made up.
"""

import pytest

from engine.needs import needs_met, request_needs
from engine.query import parse_query


def met(request: str, body: str, thread: bool = False) -> tuple[str, ...]:
    return needs_met(body, request_needs(parse_query(request)), thread=thread)


@pytest.mark.parametrize("body", [
    "I'm 46 and this one has been lovely on my dry patches.",
    "I’m 52 and it sinks in overnight.",
    "46F here, combination skin, and I keep buying it.",
    "As a 58 yo with dry skin I like it a lot.",
    "I am 61 years old and it is the only one I repurchase.",
    "Turning 50 next year, this is my favourite.",
    "My 63-year-old skin drinks it up.",
    "44 yr old with combination skin and this is my favourite.",
    "At 57 yrs old I still reach for it every evening.",
])
def test_an_age_of_forty_or_more_talks_about_mature_skin(body):
    assert met("night cream for my 40s", body) == ("mature",)
    assert met("moisturiser for mature skin", body) == ("mature",)


@pytest.mark.parametrize("body", [
    "I'm 38 and it suits me.",
    "SPF 50+ PA++++ and it never pills.",
    "I wear SPF 50 for daily use and reapply.",
    "I left it on for 45 minutes and rinsed.",
    "It costs about 40 pounds for 50ml.",
])
def test_other_numbers_say_nothing_about_age(body):
    assert met("moisturiser for mature skin", body) == ()


def test_the_signs_of_ageing_talk_about_mature_skin():
    assert met("moisturiser for mature skin", "My cheeks are sagging and this firms them a little.") == ("mature",)
    assert met("moisturiser for mature skin", "It helps the crepey skin under my eyes.") == ("mature",)
    assert met("moisturiser for mature skin", "Since menopause my skin is so dry, and this helps.") == ("mature",)
    assert met("moisturiser for mature skin", "Perimenopausal skin here and it calms it.") == ("mature",)
    assert met("night cream for my 40s", "Now in my forties I need something richer.") == ("mature",)


def test_a_request_about_menopausal_or_sagging_skin_asks_about_mature_skin():
    assert "mature" in [need.name for need in request_needs(parse_query("moisturiser for menopausal skin"))]
    assert "mature" in [need.name for need in request_needs(parse_query("night cream for sagging skin"))]


def test_an_age_in_a_thread_title_names_no_need():
    # Ages count in comments only, like config.NEED_COMMENT_WORDS' other words: a title's number is too loose to rank
    # threads by (module 2's need-led first reading reads titles and posts).
    assert met("moisturiser for mature skin", "Help, 46F with dry skin", thread=True) == ()
