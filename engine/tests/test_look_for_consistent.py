""""What to look for" never says the opposite of the request or of the picks (17 Oct 2026, the converge round, item 3).

From the breadth-first review of 16 Oct 2026 (docs/bfs-2026-10-16/answer.md, J) and the 17 Oct sweep: an electric
kettle answer said "Avoid: variable temperature kettle" under three variable-temperature kettles, and so did the
answer to "electric kettle with temperature control"; three lines against niacinamide in a niacinamide serum answer;
"Avoid: mesh networks" for mesh wifi; "Avoid: inverter microwave" above a Panasonic inverter microwave; "Look for" and
"Avoid" the same kind in one answer. Credible voices may disagree, but the section is a blueprint for the request, so a
line saying the opposite of what was asked for, of a pick, or of another kind's stronger advice is left out. Avoiding
what the request itself refuses ("Avoid: Teflon" for a pan without Teflon) agrees with it, and stays.

All text is made up (engine/tests/ranking_factories.py).
"""

from engine import answer as wording
from engine.answer import write_answer
from engine.config import NEEDS
from engine.needs import Need
from engine.rank import rank_products
from engine.tests.ranking_factories import bodies_for, mentions, note


def shown(notes, product_type, request="", needs=(), asks=(), category="kitchen", picks=None):
    items = picks if picks is not None else mentions(3, "Acme thing", category=category)
    answer = write_answer(rank_products(items, category, notes, {}), bodies_for(*items, *notes), product_type,
                          request=request, needs=tuple(needs), asks=tuple(asks))
    return [(item.advice, item.kind) for item in answer.look_for]


TEMPERATURE = Need("temperature control", NEEDS["temperature control"])


def test_an_avoid_line_about_what_the_request_asks_for_is_left_out():
    variable = note("variable temperature kettle", "t1", stance="warn", weight=-0.6,
                    quote="Every variable temperature kettle I owned broke inside a year.")
    glass = note("glass kettle", "t2", quote="A glass kettle is great, you see the scale building up.", weight=0.5)
    assert shown([variable, glass], "electric kettle", "electric kettle with temperature control",
                 needs=[TEMPERATURE]) == [(wording.LOOK_FOR, "glass kettle")]
    # Asked for nothing of the kind, the same warning stays: it says nothing against the request.
    assert (wording.AVOID, "variable temperature kettle") in shown([variable, glass], "electric kettle",
                                                                   "a quiet electric kettle")


def test_an_avoid_line_about_the_ingredient_asked_for_is_left_out():
    notes = [note("niacinamide irritation", "t1", stance="warn", weight=-0.6,
                  quote="Niacinamide irritation is common, my face went red with it."),
             note("products with niacinamide", "t2", stance="warn", weight=-0.5,
                  quote="I avoid products with niacinamide now, they all broke me out."),
             note("low-percentage niacinamide", "t1", weight=0.4,
                  quote="A low-percentage niacinamide is great, the gentler ones did more for me.")]
    assert shown(notes, "serum", "niacinamide serum for large pores", category="skincare") == [
        (wording.LOOK_FOR, "low-percentage niacinamide")]


def test_an_avoid_line_about_the_feature_the_request_names_for_its_product_is_left_out():
    # "mesh wifi": the request names a mesh system (one of the type's own names); another kind of it stays.
    notes = [note("mesh networks", "t1", stance="warn", weight=-0.6,
                  quote="Mesh networks are overkill, no reason for one in a flat."),
             note("wifi extenders", "t2", stance="warn", weight=-0.5,
                  quote="Wifi extenders are the worst fix, they halve your speed.")]
    assert shown(notes, "wifi router", "mesh wifi for a three storey house", category="general") == [
        (wording.AVOID, "wifi extenders")]


def test_avoiding_what_the_request_itself_refuses_agrees_with_it():
    teflon = note("Teflon", "t1", stance="warn", weight=-0.8,
                  quote="Teflon coatings flake within two years, I'd never buy one again.")
    non_stick = Need("non-stick", ("non-stick", "nonstick", "non stick"))
    assert shown([teflon], "frying pan", "non stick pan without teflon that lasts", needs=[non_stick],
                 asks=("PFAS-free", "non-stick")) == [(wording.AVOID, "Teflon")]


def test_a_look_for_line_about_what_the_request_refuses_is_left_out():
    teflon = note("Teflon pans", "t1", weight=0.8, quote="Teflon pans are great for eggs, cheap and easy.")
    ceramic = note("ceramic pans", "t2", weight=0.4, quote="Ceramic pans are great for eggs if you go gently.")
    assert shown([teflon, ceramic], "frying pan", "non stick pan without teflon", asks=("PFAS-free",)) == [
        (wording.LOOK_FOR, "ceramic pans")]


def test_an_avoid_line_about_a_kind_one_of_the_picks_is_is_left_out():
    picks = mentions(3, "Panasonic inverter microwave") + mentions(3, "Acme microwave")
    notes = [note("inverter microwave", "t1", stance="warn", weight=-0.7,
                  quote="An inverter microwave died on me in two years, never again."),
             note("microwave drawer", "t2", weight=0.4, quote="A microwave drawer is great in a small kitchen.")]
    assert shown(notes, "microwave", "microwave with a grill", picks=picks) == [
        (wording.LOOK_FOR, "microwave drawer")]
    # With no pick of that kind, the warning stays.
    others = mentions(3, "Acme microwave") + mentions(3, "Bolt microwave")
    assert (wording.AVOID, "inverter microwave") in shown(notes, "microwave", "microwave with a grill", picks=others)


def test_an_avoid_line_another_kinds_credible_advice_recommends_is_left_out():
    # The kettle answer: one writer warns against variable-temperature kettles, while credible voices recommend a
    # temperature-controlled one (here not even among the lines shown): the section doesn't say both.
    notes = [note("variable temperature kettle", "t1", stance="warn", weight=-1.0,
                  quote="Every variable temperature kettle I owned broke inside a year."),
             note("temperature-controlled kettle", "t2", weight=0.6,
                  quote="A temperature-controlled kettle is great for green tea."),
             note("steel kettle", "t1", weight=0.9, quote="A steel kettle is great, no plastic taste at all."),
             note("glass kettle", "t2", weight=0.8, quote="A glass kettle is great, you see the scale."),
             note("gooseneck kettle", "t1", weight=0.7, quote="A gooseneck kettle is great for pour over.")]
    assert shown(notes, "electric kettle", "electric kettle that lasts 10+ years") == [
        (wording.LOOK_FOR, "steel kettle"), (wording.LOOK_FOR, "glass kettle"), (wording.LOOK_FOR, "gooseneck kettle")]
    # Without the recommendation, the warning is the strongest advice, and it is shown first.
    assert shown(notes[:1] + notes[2:], "electric kettle", "electric kettle that lasts 10+ years")[0] == (
        wording.AVOID, "variable temperature kettle")


def test_a_look_for_line_stronger_credible_warnings_argue_against_is_left_out_and_the_stronger_stays():
    notes = [note("mineral sunscreen", "t1", weight=0.4, quote="A mineral sunscreen is great for my sensitive skin."),
             note("mineral SPFs", "t2", stance="warn", weight=-0.9,
                  quote="Mineral SPFs leave a grey film on my skin, I'd skip them."),
             note("stick sunscreens", "t1", weight=0.3, quote="Stick sunscreens are great for top ups.")]
    assert shown(notes, "sunscreen", "best sunscreen", category="skincare") == [
        (wording.AVOID, "mineral SPFs"), (wording.LOOK_FOR, "stick sunscreens")]


def test_a_recommended_kind_the_request_rules_out_argues_against_nothing():
    # "Avoid: tretinoin" for a beginner: writers who recommend tretinoin don't count against it, since a beginner's
    # answer never says "Look for: tretinoin" (its facts rule it out: the pipeline's unsuited kinds).
    items = mentions(3, "Acme serum", category="skincare")
    notes = [note("tretinoin", "t1", stance="warn", weight=-0.8, quote="Tretinoin is far too strong to start with."),
             note("tretinoin 0.025%", "t2", weight=0.9, key="tret-recommended",
                  quote="Tretinoin 0.025% is great once you are used to it.")]
    answer = write_answer(rank_products(items, "skincare", notes, {}), bodies_for(*items, *notes), "retinoid",
                          request="gentle retinol for beginners", unsuited_kinds={"tret-recommended"})
    assert [(item.advice, item.kind) for item in answer.look_for] == [(wording.AVOID, "tretinoin")]
    # Not ruled out, the recommendation outweighs the warning: neither is said (the recommendation is the product asked
    # for, so it gives no "Look for" of its own).
    answer = write_answer(rank_products(items, "skincare", notes, {}), bodies_for(*items, *notes), "retinoid",
                          request="gentle retinol for beginners")
    assert (wording.AVOID, "tretinoin") not in [(item.advice, item.kind) for item in answer.look_for]


def test_kinds_are_the_same_only_when_what_tells_one_apart_is_the_others():
    from engine.answer import _kind_own_words, _same_kind

    def same(a, b, product_type, category="kitchen"):
        return _same_kind(_kind_own_words(a, category, product_type), _kind_own_words(b, category, product_type))

    assert same("mineral SPFs", "mineral sunscreen", "sunscreen", "skincare")  # "spf" is a sunscreen's clue word
    assert same("variable temperature kettle", "temperature-controlled kettle", "electric kettle")
    assert same("gel moisturiser", "gel cream for oily skin", "moisturiser", "skincare")
    # A plural made singular its own way ("knives", "patches") is still the type's word, so it tells nothing apart.
    assert not same("Japanese style knives", "classic German knives", "paring knife")
    assert not same("large patches", "hydrocolloid patches", "spot treatment", "skincare")
    assert not same("corded hammer drill", "dedicated hammer drill", "drill")


def test_in_a_knife_answer_warnings_about_other_knives_stay_beside_advice_about_others():
    notes = [note("Japanese style knives", "t1", weight=0.3, quote="Japanese style knives are great for fine cuts."),
             note("Damascus knives", "t2", stance="warn", weight=-0.5,
                  quote="Damascus knives are mostly looks, skip the pattern and buy good steel."),
             note("classic German knives", "t1", stance="warn", weight=-0.3,
                  quote="Classic German knives are too soft for this, they dull fast.")]
    assert sorted(shown(notes, "paring knife", "best paring knife under £30")) == sorted([
        (wording.AVOID, "Damascus knives"), (wording.LOOK_FOR, "Japanese style knives"),
        (wording.AVOID, "classic German knives")])


def test_avoiding_a_needs_opposite_or_whom_it_is_for_isnt_against_the_request():
    # A need's words hold its opposite too ("harsh" for gentle, "broke" for lasting): avoiding that agrees with it. And
    # a need saying whom the product is for (a beginner, oily skin) is no word of the product asked for.
    from engine.needs import Need

    gentle, lasting = Need("gentle", NEEDS["gentle"]), Need("lasting", NEEDS["lasting"])
    harsh = note("harsh scrubs", "t1", stance="warn", weight=-0.6, quote="Harsh scrubs tear your skin, skip them.")
    assert shown([harsh], "exfoliant", "gentle exfoliant", needs=[gentle], category="skincare") == [
        (wording.AVOID, "harsh scrubs")]
    broke = note("plastic kettles that broke", "t1", stance="warn", weight=-0.6,
                 quote="Plastic kettles that broke within a year, every one of them, so skip those.")
    assert shown([broke], "electric kettle", "kettle that lasts", needs=[lasting]) == [
        (wording.AVOID, "plastic kettles that broke")]
    beginner = Need("beginner", NEEDS["beginner"])
    sets = note("beginner knife sets", "t1", stance="warn", weight=-0.6,
                quote="Beginner knife sets are a waste, buy one good knife instead.")
    assert shown([sets], "chef knife", "first chef's knife for a beginner", needs=[beginner]) == [
        (wording.AVOID, "beginner knife sets")]


def test_avoiding_a_kind_the_requests_facts_rule_out_stays_whatever_others_recommend():
    # "Avoid: tretinoin" for a beginner, whose answer the facts rules keep tretinoin out of (the pipeline's unsuited
    # kinds: the kind's own facts entry clashes hard with the request), stays beside writers recommending a tretinoin
    # cream: it agrees with the request.
    items = mentions(3, "Acme serum", category="skincare")
    notes = [note("tretinoin", "t1", stance="warn", weight=-0.8, key="tretinoin",
                  quote="Tretinoin is far too strong to start with."),
             note("tretinoin cream", "t2", weight=0.9, quote="A tretinoin cream is great once you are used to it.")]
    answer = write_answer(rank_products(items, "skincare", notes, {}), bodies_for(*items, *notes), "retinoid",
                          request="gentle retinol for beginners", unsuited_kinds={"tretinoin"})
    assert (wording.AVOID, "tretinoin") in [(item.advice, item.kind) for item in answer.look_for]
