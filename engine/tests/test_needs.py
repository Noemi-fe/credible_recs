"""What the person asked for (a request's needs) and which comments talk about it (module 6; 9 Oct 2026).

All requests and comments are made up; module 1 (engine/query.py) reads the requests.
"""

import pytest

from engine.config import NEEDS
from engine.needs import Need, needs_met, request_needs
from engine.query import MUST_HAVES, SKIN_TYPES, parse_query


def names(request: str) -> list[str]:
    return [need.name for need in request_needs(parse_query(request))]


def met(request: str, body: str, long_term_use: bool = False) -> tuple[str, ...]:
    return needs_met(body, request_needs(parse_query(request)), long_term_use)


# --- The needs a request names ---

def test_skin_types_and_words_in_other_words_are_needs_in_the_order_given():
    assert names("retinol for a beginner with sensitive skin") == ["beginner", "sensitive"]
    assert names("gentle exfoliant for sensitive skin under £30") == ["gentle", "sensitive"]


def test_a_need_typed_in_other_words_is_still_found():
    assert names("first chef's knife under £100 for a home cook") == ["beginner", "home cook"]
    assert names("sunscreen for oily skin that doesn't leave a white cast, under £20") == ["oily", "no white cast"]
    assert names("cast iron skillet for a beginner that will last decades") == ["beginner", "lasting"]


def test_how_long_it_should_last_is_a_need():
    assert names("electric kettle that lasts 10+ years") == ["lasting"]


def test_other_specific_words_are_needs_of_their_own_named_as_typed():
    assert names("burr coffee grinder for pour-over under £150") == ["pour-over"]
    assert names("non-stick frying pan without PFAS that actually lasts") == ["non-stick", "PFAS", "lasting"]
    assert names("fragrance-free moisturiser for very dry skin in winter") == ["fragrance-free", "dry", "winter"]
    assert names("gentle cleanser for acne-prone skin that won't strip my skin") == ["gentle", "acne-prone", "strip"]


def test_a_word_naming_the_kind_of_product_every_thread_discusses_is_not_a_need():
    # Every grinder in a grinder thread is a burr grinder (or not): "burr" doesn't pick out a comment.
    assert names("burr coffee grinder") == []


def test_a_plain_request_has_no_needs_and_a_question_has_none_either():
    assert names("electric kettle") == []
    assert request_needs(parse_query("something nice for my mum")) == ()


def test_every_skin_type_and_must_have_module_1_finds_has_words_to_find_it_by():
    assert set(SKIN_TYPES) <= set(NEEDS) and set(MUST_HAVES) <= set(NEEDS)


# --- Which comments talk about them ---

BEGINNER_SENSITIVE = "retinol for a beginner with sensitive skin"


def test_a_comment_talks_about_a_need_by_its_words_and_their_longer_forms():
    assert met(BEGINNER_SENSITIVE, "My skin is so reactive, but this one is fine.") == ("sensitive",)
    assert met(BEGINNER_SENSITIVE, "Great if you have sensitivity issues.") == ("sensitive",)
    assert met(BEGINNER_SENSITIVE, "I started with the 0.2% and was new to retinoids.") == ("beginner",)
    assert met(BEGINNER_SENSITIVE, "My first retinoid, perfect for sensitive skin.") == ("beginner", "sensitive")
    assert met(BEGINNER_SENSITIVE, "It cleared my skin in a month.") == ()
    assert met(BEGINNER_SENSITIVE, "We finished the first bottle in 9 months.") == ()  # "first" alone is too loose


def test_a_warning_about_the_need_talks_about_it_too():
    assert met("gentle exfoliant for sensitive skin", "Way too harsh, it burned.") == ("gentle",)


def test_a_phrase_is_found_whole_and_a_word_only_at_the_start_of_a_word():
    assert met("sunscreen that doesn't leave a white cast", "No white casts at all on me.") == ("no white cast",)
    assert met("sunscreen that doesn't leave a white cast", "It leaves my skin white, a cast-iron feel.") == ()
    assert met("fragrance-free moisturiser", "It's unscented, thankfully.") == ("fragrance-free",)
    assert met(BEGINNER_SENSITIVE, "Insensitive packaging, but works.") == ()  # "sensitiv" inside a word doesn't count


def test_quoted_blocks_are_someone_elses_words():
    assert met(BEGINNER_SENSITIVE, "> I have sensitive skin\n\nThis one works for me.") == ()


def test_a_request_word_is_found_the_way_titles_are_matched():
    assert met("burr coffee grinder for pour-over", "Great for pour over, less so for espresso.") == ("pour-over",)
    assert met("non-stick frying pan without PFAS", "This nonstick pan is PFAS-free.") == ("non-stick", "PFAS")


def test_long_term_use_talks_about_lasting():
    assert met("electric kettle that lasts 10+ years", "Mine still boils perfectly.", long_term_use=True) == ("lasting",)
    assert met("electric kettle that lasts 10+ years", "Mine still boils perfectly.") == ()
    assert met("electric kettle that lasts 10+ years", "Mine died within a year.") == ("lasting",)
    assert met(BEGINNER_SENSITIVE, "Mine is lovely.", long_term_use=True) == ()  # long use isn't this request's need


def test_a_need_of_its_own_word_finds_its_longer_forms():
    assert needs_met("This one never strips my skin.", (Need("strip", request_word="strip"),)) == ("strip",)


@pytest.mark.parametrize("body", [
    "This is the only exfoliant that doesn't cause a rash for me.",
    "It didn't irritate my skin at all.",
    "No redness or stinging, even on my cheeks.",
])
def test_a_reaction_or_its_absence_talks_about_sensitive_skin(body):
    # Found reading the blind-test view, 10 Oct 2026 (late): b01's Stratia quote about never causing a rash wasn't
    # counted as talking about sensitive skin. Picks don't change; reasons and the quotes shown get more accurate.
    assert "sensitive" in met("gentle exfoliant for sensitive skin", body)
