"""Skincare's need rule in every reading (Noemi's decision 3 of 15 Oct 2026).

Her decision 4 of 14 Oct 2026 (option B) made haircare's readings follow the wider reading's need rule: a pick, or an
"Also worth a look" item, needs a credible recommendation that talks about the request's needs, in every reading, not
only in the wider one. Since 15 Oct 2026 skincare's readings follow it too (config.NEED_RULE_IN_EVERY_READING). The case
that prompted it: "a bha for blackheads" showed a microdart patch none of whose credible comments talk about
blackheads. Kitchen and the general category keep the rule to the wider reading, as before.

The rule judges a pick by the needs a comment can talk about (engine.needs.judged_needs, Claude's call within her rule):
not the words that say what the product is or holds, which no comment's words can settle: an active ingredient the
request names, asked for ("vitamin c serum": the ingredient rule checks it against the maker's list) or asked to leave
out ("moisturiser without niacinamide"), or a size ("15ml", "1.7 fl oz"). Judged by those words too, on the frozen
library, "need an eye cream 15ml max £35" lost all its picks, "vitamin c serum under £20" a vitamin C serum whose
credible writers call it by its name only, and "moisturiser without niacinamide" got creams whose writers say they hold
it.

Every product, comment and library here is made up; nothing reads data/.
"""

import dataclasses

import pytest

from engine import config, pipeline
from engine.answer import unverified_claims
from engine.needs import judged_needs, request_needs
from engine.pipeline import answer_request
from engine.query import parse_query
from engine.tests.ranking_factories import mention
from engine.tests.test_needs_and_contradictions import ALPHA, BETA, BETA_SENSITIVE, retinol_library
from engine.tests.test_pipeline_ingredients import write_library as skincare_library


def made_up(product: str, threads=("t1", "t2", "t1"), needs_in_first: tuple[str, ...] = (), category="skincare"):
    """Three credible recommendations of `product` across two threads; the first talks about `needs_in_first`."""
    found = [mention(product, thread, category=category) for thread in threads]
    found[0] = dataclasses.replace(found[0], needs=needs_in_first)
    return found


def names(products) -> list[str]:
    return [p.name for p in products]


# --- The rule, in skincare's first reading ---

def test_a_skincare_pick_needs_a_credible_recommendation_about_the_requests_needs_in_the_first_reading():
    query = parse_query("gentle exfoliant for sensitive skin")
    plain, fitting = made_up("Made-up Exfoliant"), made_up("Other Exfoliant", needs_in_first=("sensitive",))
    ranking = pipeline._ranked(plain + fitting, query, [], [], need_led=False)
    assert names(ranking.picks) == ["Other Exfoliant"]
    left_out = next(p for p in ranking.products if p.name == "Made-up Exfoliant")
    assert not left_out.qualifies and left_out.shortfall == pipeline.WIDER_READING_SHORTFALL


def test_so_does_an_also_worth_a_look_item():
    query = parse_query("moisturiser for oily skin")
    plain = made_up("Made-up Cream", threads=("t1", "t2"))
    fitting = made_up("Other Cream", threads=("t1", "t2"), needs_in_first=("oily",))
    ranking = pipeline._ranked(plain + fitting, query, [], [], need_led=False)
    assert names(ranking.worth_a_look) == ["Other Cream"]


def test_the_case_that_prompted_it_a_patch_no_credible_comment_says_is_for_blackheads():
    # "a bha for blackheads" is ingredient-led: its products are of every type that can carry a BHA. A microdart patch
    # with salicylic acid qualifies on the bar, but no credible writer of it talks about blackheads.
    query = parse_query("a bha for blackheads")
    assert query.category == "skincare" and query.ingredient_led
    assert [need.name for need in request_needs(query)] == ["blackheads"]
    patch = made_up("Made-up Salicylic Microdart Patch")
    liquid = made_up("Made-up BHA Liquid", needs_in_first=("blackheads",))
    ranking = pipeline._ranked(patch + liquid, query, [], [], need_led=False)
    assert names(ranking.picks) == ["Made-up BHA Liquid"]
    assert "Made-up Salicylic Microdart Patch" not in names(ranking.worth_a_look)


def test_a_skincare_request_with_no_needs_is_unchanged():
    query = parse_query("moisturiser")
    assert request_needs(query) == ()
    ranking = pipeline._ranked(made_up("Made-up Cream") + made_up("Other Cream"), query, [], [], need_led=False)
    assert set(names(ranking.picks)) == {"Made-up Cream", "Other Cream"}


@pytest.mark.parametrize("request_text, category", [("frying pan that lasts", "kitchen"),
                                                    ("quiet hair dryer", "general")])
def test_kitchen_and_general_first_readings_are_unchanged(request_text, category):
    query = parse_query(request_text)
    assert query.category == category and judged_needs(query)
    mentions = made_up("Made-up Thing", category=category) + made_up("Other Thing", category=category)
    first = pipeline._ranked(mentions, query, [], [], need_led=False)
    assert set(names(first.picks)) == {"Made-up Thing", "Other Thing"}
    # The wider reading's rule is theirs as before: there, neither talks about what was asked.
    assert pipeline._ranked(mentions, query, [], [], need_led=True).picks == []



# --- What the rule judges a pick by ---

@pytest.mark.parametrize("request_text, judged", [
    ("gentle exfoliant for sensitive skin", ["gentle", "sensitive"]),
    # The ingredient a typed request asks for says which product it is; the ingredient rule checks it.
    ("vitamin c serum", []),
    ("vitamin c serum under £20", []),
    ("salicylic acid spot treatment", []),
    ("niacinamide serum for oily skin", ["oily"]),
    # Nor one it asks to leave out: whether a cream holds it is the maker's list's to say, and writers say either way.
    ("moisturiser without niacinamide", []),
    ("niacinamide-free moisturiser for dry skin", ["dry"]),
    # A size says which bottle, not what it should do.
    ("need an eye cream 15ml max £35", []),
    # Changed on purpose 16 Oct 2026 (the interview-fixes builder): "daily" is filler, found in nearly any comment ("I
    # use it daily"); was ["daily", "spf30", "dry"].
    ("daily moisturizer w spf30+ for dry skin, 1.7 fl oz, $25 or less", ["spf30", "dry"]),
    # Nor a single letter: "w/o" says "without", and "w" or "o" names nothing a comment could talk about.
    ("toner w/o alcohol for combination/normal skin", ["alcohol", "combination", "normal"]),
    ("1.7l kettle under £40", []),
    # Changed on purpose 16 Oct 2026 (the interview-fixes builder): "non stick" is one need (config.NEED_PHRASES) and
    # "pfas free" asks about PFAS, as "pfas-free" does; was ["non", "stick", "pfas", "free"].
    ("28cm frying pan, non stick but pfas free, £30-60", ["non stick", "pfas"]),
    ("10 inch cast iron skillet that lasts", ["lasting"]),
])
def test_the_rule_judges_the_needs_a_comment_can_talk_about(request_text, judged):
    assert [need.name for need in judged_needs(parse_query(request_text))] == judged


def test_with_only_the_ingredient_asked_for_the_rule_doesnt_apply():
    query = parse_query("vitamin c serum")
    assert [need.name for need in request_needs(query)] == ["vitamin", "c"]  # its needs, as before
    named = made_up("Made-up C Serum")  # its credible writers call it by its name, never "vitamin c"
    ranking = pipeline._ranked(named + made_up("Other C Serum", needs_in_first=("vitamin",)), query, [], [],
                               need_led=False)
    assert set(names(ranking.picks)) == {"Made-up C Serum", "Other C Serum"}


def test_a_recommendation_about_the_ingredient_alone_doesnt_answer_the_need():
    query = parse_query("niacinamide serum for oily skin")
    about_the_ingredient = made_up("Made-up Serum", needs_in_first=("niacinamide",))
    about_oily_skin = made_up("Other Serum", needs_in_first=("oily",))
    ranking = pipeline._ranked(about_the_ingredient + about_oily_skin, query, [], [], need_led=False)
    assert names(ranking.picks) == ["Other Serum"]


def test_a_size_alone_leaves_the_answer_as_before():
    query = parse_query("need an eye cream 15ml max £35")
    assert [need.name for need in request_needs(query)] == ["15ml"]
    ranking = pipeline._ranked(made_up("Made-up Eye Cream") + made_up("Other Eye Cream"), query, [], [],
                               need_led=False)
    assert set(names(ranking.picks)) == {"Made-up Eye Cream", "Other Eye Cream"}


# --- Through the pipeline ---

def test_a_retinol_whose_credible_writers_never_talk_about_sensitive_skin_isnt_a_pick(tmp_path):
    result = answer_request("retinol for sensitive skin",
                            library_dir=retinol_library(tmp_path, ALPHA + BETA[:2] + [BETA_SENSITIVE]))
    assert [pick.name for pick in result.answer.picks] == ["Beta Retinol"]
    alpha = next(p for p in result.ranking.products if p.name == "Alpha Retinol")
    assert alpha.shortfall == pipeline.WIDER_READING_SHORTFALL
    assert "Alpha Retinol" not in [item.name for item in result.answer.worth_a_look]
    assert unverified_claims(result.answer, result.bodies) == []


def test_without_the_need_in_the_request_both_retinols_are_picks(tmp_path):
    result = answer_request("retinol", library_dir=retinol_library(tmp_path, ALPHA + BETA[:2] + [BETA_SENSITIVE]))
    assert [pick.name for pick in result.answer.picks] == ["Alpha Retinol", "Beta Retinol"]


PATCH = ("Nova Salicylic Microdart Patch", "pimple patch")
LIQUID = ("Wren BHA Liquid", "exfoliant")


def test_through_the_pipeline_the_patch_gives_way_to_the_liquid_whose_writer_talks_about_blackheads(tmp_path):
    praise = lambda cid, product, years: (cid, product, f"I've used the {product[0]} for {years} years, my skin is "
                                                        "smoother.", "recommend")
    about = ("w3", LIQUID, f"I've used the {LIQUID[0]} for 4 years and it cleared my blackheads.", "recommend")
    lib = skincare_library(tmp_path, {
        "1bha01": ("Which BHA do you use?", [praise("p1", PATCH, 2), praise("p2", PATCH, 3),
                                              praise("w1", LIQUID, 2), praise("w2", LIQUID, 3)]),
        "1bha02": ("BHA recommendations?", [praise("p3", PATCH, 4), about]),
    })
    result = answer_request("a bha for blackheads", library_dir=lib, prices=[], product_facts=[])
    assert [pick.name for pick in result.answer.picks] == [LIQUID[0]]
    assert PATCH[0] not in [item.name for item in result.answer.worth_a_look]
    patch = next(p for p in result.ranking.products if p.name == PATCH[0])
    assert patch.breakdown.credible_recommends == 3 and patch.shortfall == pipeline.WIDER_READING_SHORTFALL


# --- The how page ---

def test_the_how_page_says_a_pick_must_talk_about_what_you_asked_for_and_where(tmp_path, monkeypatch):
    from engine.tests.test_how_page import get_how, text_of

    words = text_of(get_how(tmp_path, monkeypatch))
    assert ("When you ask for more than the product, such as a skin type, a concern or a must-have, at least one of "
            "those credible recommendations must also talk about it: in every answer for haircare and skincare, and "
            "for anything else when we read more threads than usual.") in words
    assert "An ingredient or a size you name isn't counted here" in words
    monkeypatch.setattr(config, "NEED_RULE_IN_EVERY_READING", ("haircare",))
    assert "in every answer for haircare, and for anything else" in text_of(get_how(tmp_path, monkeypatch))
    monkeypatch.setattr(config, "NEED_RULE_IN_EVERY_READING", ())
    assert ("at least one of those credible recommendations must also talk about it when we read more threads than "
            "usual.") in text_of(get_how(tmp_path, monkeypatch))


# --- A need its checked requirement settles isn't judged by comments (15 Oct 2026) ---

@pytest.mark.parametrize("request_text, settled", [
    ("lip balm with spf", "spf"),  # Noemi's decision 2: the lip balm's facts or its name say whether it has SPF
    ("sulfate-free shampoo for curly hair", "sulfate"),  # the shampoo's facts say whether it is sulfate-free
])
def test_a_need_a_checked_requirement_settles_is_not_judged_by_comments(request_text, settled):
    # As for an active ingredient: the facts check settles it (engine/product_facts.py), and nobody's praise has to say
    # it as well. It stays a need for the threads read first (since 15 Oct 2026 the reason's "about ..." goes by the
    # judged needs: engine/tests/test_reason_needs.py).
    query = parse_query(request_text, model=None)
    assert settled in {need.name for need in request_needs(query)}
    assert settled not in {need.name for need in judged_needs(query)}


def test_the_requests_other_needs_are_still_judged():
    query = parse_query("sulfate-free shampoo for curly hair", model=None)
    assert "curly" in {need.name for need in judged_needs(query)}
    query = parse_query("lip balm for very dry lips", model=None)
    assert "dry" in {need.name for need in judged_needs(query)}
