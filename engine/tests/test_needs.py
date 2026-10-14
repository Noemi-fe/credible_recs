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


def test_the_products_own_name_is_not_a_need():
    # "dry shampoo" names a product, not dry skin (11 Oct 2026, from the shampoo builder's findings).
    assert names("dry shampoo that doesn't leave a white cast") == ["no white cast"]
    assert "dry" in names("moisturiser for dry skin")


# --- Haircare needs, and kitchen needs in other words (14 Oct 2026: need-led thread choice) ---
# From Noemi's and a friend's tests of the live site: "shampoo for greasy hair" asked about a need the engine read as
# oily skin, through one word of it ("greasy"), so threads about an oily scalp didn't count; and "fine", "flat", "wavy" or
# "frizzy" were words of the request found only as typed. A haircare request's needs are its own (config.HAIR_NEEDS),
# in place of the skin types': "shiny" hair isn't greasy, a "flaky" scalp is dandruff, not dry hair.

@pytest.mark.parametrize("request_text, expected", [
    ("shampoo for greasy hair", ["oily hair"]),
    ("shampoo for an oily scalp", ["oily hair"]),
    ("dandruff shampoo that actually works", ["dandruff"]),  # "works" says how well, not what for
    ("anti-dandruff shampoo for a flaky scalp", ["dandruff"]),
    ("shampoo for an itchy scalp", ["itchy scalp"]),
    ("gentle shampoo for wavy hair", ["gentle", "wavy"]),
    ("shampoo for fine flat hair", ["fine hair"]),
    ("shampoo for thin fine hair", ["fine hair"]),
    ("conditioner for frizzy curly hair", ["frizzy", "curly"]),
    ("conditioner for dry hair", ["dry hair"]),
    ("conditioner for dry, damaged hair", ["dry hair", "damaged"]),
    ("shampoo for colour-treated hair", ["colour-treated"]),
    ("shampoo for dyed hair", ["colour-treated"]),
    ("shampoo for a sensitive scalp", ["sensitive scalp"]),
])
def test_haircare_needs_are_named_in_the_words_people_use(request_text, expected):
    assert names(request_text) == expected


def test_the_skin_types_are_not_haircare_needs_and_skincare_keeps_them():
    assert "oily" not in names("shampoo for greasy hair")
    assert names("moisturiser for greasy skin") == ["oily"]
    assert names("sunscreen for dry skin") == ["dry"]


def test_a_comment_talks_about_a_haircare_need_in_its_own_words():
    assert met("shampoo for greasy hair", "My roots get oily by lunchtime, this fixed it.") == ("oily hair",)
    assert met("shampoo for greasy hair", "Way less grease between washes.") == ("oily hair",)
    assert met("shampoo for greasy hair", "It left my hair so shiny and soft.") == ()  # shiny hair isn't greasy
    assert met("dandruff shampoo", "The flakes were gone in a week.") == ("dandruff",)
    assert met("conditioner for dry hair", "My ends felt like straw before this one.") == ("dry hair",)
    assert met("conditioner for dry hair", "I love the strawberry scent.") == ()  # straw only as straw-like hair
    assert met("shampoo for fine flat hair", "It never weighs my hair down.") == ("fine hair",)
    assert met("shampoo for fine flat hair", "Gives me volume at the roots.") == ("fine hair",)
    assert met("shampoo for fine flat hair", "It works fine for me.") == ()  # "fine" alone says how it works
    assert met("conditioner for frizzy curly hair", "No frizz and my curls clump.") == ("frizzy", "curly")
    assert met("gentle shampoo for wavy hair", "Great for my 2b waves.") == ("wavy",)
    assert met("shampoo for dyed hair", "Kept my bleached blonde bright.") == ("colour-treated",)


def test_needs_in_other_words_for_kitchen_requests():
    assert names("kettle that's quiet") == ["quiet"]
    assert met("kettle that's quiet", "It's so loud when it boils.") == ("quiet",)
    assert met("kettle that's quiet", "It boils fast.") == ()
    assert names("cast iron skillet for a glass top stove") == ["glass top stove"]
    assert met("cast iron skillet for a glass top stove", "Fine on my ceramic hob, just lift it.") == ("glass top stove",)
    assert met("cast iron skillet for a glass top stove", "Works on a glass-top, never slide it.") == ("glass top stove",)
    assert met("cast iron skillet for a glass top stove", "Glass lids are handy.") == ()  # glass alone isn't the stove


# --- What a request asks a product not to do, and hair types written together (14 Oct 2026, the need-quality builder) ---
# Found on the library: "shampoo for curly hair that isn't drying" read "isn't" as a need of its own and "drying" as a
# word found as typed (in comments about air-drying too), and nothing knew it asked for a shampoo that isn't drying;
# "shampoo for fine oily hair" read "fine" as a word of its own, so a comment saying a shampoo works fine talked about it.

@pytest.mark.parametrize("request_text, expected", [
    ("shampoo for curly hair that isn't drying", ["curly", "not drying"]),
    ("shampoo that is not drying", ["not drying"]),
    ("a non-drying shampoo for my curls", ["not drying", "curly"]),
    ("shampoo that won't dry out my hair", ["not drying"]),
    ("shampoo that doesn't leave my hair dry", ["not drying"]),
    ("cleanser that doesn't dry my skin out", ["not drying"]),
    ("cleanser that isn't drying", ["not drying"]),
    ("shampoo for dry hair that isn't drying", ["dry hair", "not drying"]),
])
def test_drying_after_a_negation_asks_for_a_product_that_isnt_drying(request_text, expected):
    assert names(request_text) == expected


@pytest.mark.parametrize("request_text, expected", [
    ("moisturiser that isn't greasy", ["oily"]),  # greasiness either way round: the oily need's words
    ("kettle that isn't loud", ["quiet"]),
    ("sunscreen with no white cast", ["no white cast"]),
    ("cleanser for sensitive skin that doesn't strip", ["sensitive", "strip"]),
    ("conditioner that is never heavy", ["heavy"]),
])
def test_a_negation_is_never_a_need_of_its_own(request_text, expected):
    assert names(request_text) == expected


def test_drying_without_a_negation_is_still_dry_skin_or_hair():
    assert names("moisturiser for dry skin") == ["dry"]
    assert names("conditioner for dry hair") == ["dry hair"]
    assert names("conditioner for dry frizzy hair") == ["dry hair", "frizzy"]


@pytest.mark.parametrize("request_text, expected", [
    ("shampoo for fine oily hair", ["fine hair", "oily hair"]),
    ("shampoo for fine, oily hair", ["fine hair", "oily hair"]),
    ("shampoo for thin greasy hair", ["fine hair", "oily hair"]),
    ("conditioner for dry fine hair", ["dry hair", "fine hair"]),
    ("shampoo for oily fine curly hair", ["oily hair", "fine hair", "curly"]),
    ("shampoo for very fine and slightly oily hair", ["fine hair", "oily hair"]),
])
def test_hair_types_written_together_each_name_their_need(request_text, expected):
    assert names(request_text) == expected


def test_a_comment_or_title_names_hair_types_written_together_too():
    assert met("shampoo for fine oily hair", "My fine, oily hair loves this one.") == ("fine hair", "oily hair")
    assert met("shampoo for fine oily hair", "Holy grail for thin/greasy hair?") == ("fine hair", "oily hair")
    assert met("shampoo for fine oily hair", "It works fine on my oily roots.") == ("oily hair",)  # fine says how


def test_a_comment_talks_about_drying_when_it_says_how_drying_a_product_is():
    request = "shampoo for curly hair that isn't drying"
    assert met(request, "Not drying at all, even on my curls.") == ("curly", "not drying")
    assert met(request, "Way too drying for me.") == ("not drying",)
    assert met(request, "It dried out my ends in a week.") == ("not drying",)
    assert met(request, "I let it air dry overnight.") == ()  # drying hair isn't a drying product
    assert met(request, "Blow drying takes forever.") == ()


def test_a_request_word_named_like_a_skin_type_is_not_asked_for_as_one():
    # "dry" typed in a haircare request ("a dry scalp") is a word of its own there, never the skin type dry, which only
    # the skincare needs' rules ask about (engine.product_facts.request_asks: a light moisturiser's note).
    from engine.product_facts import request_asks

    assert "dry" not in request_asks(parse_query("shampoo for a dry scalp"))
    assert "not drying" in request_asks(parse_query("shampoo for curly hair that isn't drying"))


# --- Worked out once (latency, 13 Oct 2026) ---

def test_a_comment_asked_again_about_the_same_needs_is_read_once(monkeypatch):
    from engine import needs as needs_module

    needs = request_needs(parse_query("gentle exfoliant for sensitive skin under £30"))
    body = "Gentle enough for my sensitive skin, and I've used it for a year."
    reads = []
    real = needs_module._own_words
    monkeypatch.setattr(needs_module, "_own_words", lambda text: reads.append(1) or real(text))
    first = needs_met(body, needs)
    assert needs_met(body, needs) == first == ("gentle", "sensitive")
    assert len(reads) == 1
    assert needs_met(body, needs, long_term_use=True) == first  # another question: read again
    assert needs_met(body, needs[:1]) == ("gentle",)


def test_two_requests_written_alike_keep_their_own_needs():
    plain = parse_query("retinol for a beginner")
    with_skin = plain.model_copy(update={"constraints": plain.constraints.model_copy(update={"skin_types": ["sensitive"]})})
    assert [n.name for n in request_needs(plain)] == ["beginner"]
    assert [n.name for n in request_needs(with_skin)] == ["beginner", "sensitive"]
    assert [n.name for n in request_needs(plain)] == ["beginner"]
