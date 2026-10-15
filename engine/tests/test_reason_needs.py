"""What an answer says about the request's needs: only the needs a comment can talk about (15 Oct 2026).

The need rule judges a pick by the needs a comment can talk about (engine.needs.judged_needs): not a word of an active
ingredient the request names, a size, a single letter, or, in skincare and haircare, a word of a checked requirement.
Until 15 Oct 2026 the reason line still listed every need of the request, so a vitamin C serum's reason said "3 of them
about vitamin or c": the serum's own name, which every writer of it says. Now the reason, the breakdown's count of
recommendations about the request and which quotes count as talking about it all go by the same needs as the rule.
Two words that were never needs leave the reason too: the second word of a need's name written with a space ("prone" of
"acne prone", "free" of "fragrance free"), and a budget's own word ("50 bucks", "5 dollars").

Every product, comment and library here is made up; nothing reads data/.
"""

import pytest

from engine.answer import unverified_claims
from engine.needs import judged_needs, request_needs
from engine.pipeline import answer_request
from engine.query import parse_query
from engine.sources import need_words
from engine.tests.test_pipeline_ingredients import write_library

WREN = ("Wren Niacinamide Serum", "serum")
FENN = ("Fenn Niacinamide Serum", "serum")
VEGA = ("Vega Vitamin C Serum", "serum")


def used(cid: str, product: tuple[str, str], years: int, how: str = "my skin is much calmer for it") -> tuple:
    """A credible recommendation: long use, in the writer's own words. Naming the product names its ingredient."""
    return cid, product, f"I've used the {product[0]} for {years} years and {how}.", "recommend"


OILY = "it keeps my oily skin matte until the evening"


def niacinamide_library(tmp_path):
    return write_library(tmp_path, {
        "1nia01": ("Niacinamide serum recommendations?", [used("w1", WREN, 2), used("w2", WREN, 3, OILY),
                                                         used("f1", FENN, 2, OILY)]),
        "1nia02": ("Which niacinamide serum do you use?", [used("w3", WREN, 4), used("f2", FENN, 3)]),
    })


def answer(request: str, library):
    return answer_request(request, library_dir=library, prices=[], product_facts=[], brand_lines=[], summaries={})


def test_the_reason_names_the_need_not_the_ingredient_asked_for(tmp_path):
    result = answer("niacinamide serum for oily skin", niacinamide_library(tmp_path))
    pick = next(p for p in result.answer.picks if p.name == WREN[0])
    # Every recommendation names the serum, so every one "talked about" niacinamide: "3 of them about niacinamide or
    # oily skin". One talks about oily skin.
    assert pick.reason == "Recommended by 3 credible voices, 3 of them after long-term use, 1 of them about oily skin."
    item = next(w for w in result.answer.worth_a_look if w.name == FENN[0])
    assert item.reason == "Recommended by 2 credible voices, 2 of them after long-term use, 1 of them about oily skin."
    assert unverified_claims(result.answer, result.bodies) == []


def test_the_breakdown_counts_the_recommendations_about_the_need_only(tmp_path):
    result = answer("niacinamide serum for oily skin", niacinamide_library(tmp_path))
    wren = next(p for p in result.ranking.products if p.name == WREN[0])
    assert wren.breakdown.credible_recommends_fitting_need == 1
    assert [m.needs for m in sorted(wren.mentions, key=lambda m: m.comment_id)] == [(), ("oily",), ()]


def test_among_equally_clear_quotes_the_one_about_the_need_comes_first(tmp_path):
    # Each quote names the serum and gives a view, from equally credible writers: the one that talks about oily skin
    # leads, not the first written (which only names the serum, and with it the ingredient).
    result = answer("niacinamide serum for oily skin", niacinamide_library(tmp_path))
    pick = next(p for p in result.answer.picks if p.name == WREN[0])
    assert pick.quotes[0].comment_id == "w2"


def test_with_only_the_ingredient_asked_for_the_reason_names_no_need(tmp_path):
    library = write_library(tmp_path, {
        "1vit01": ("Vitamin C serum recommendations?", [used("v1", VEGA, 2), used("v2", VEGA, 3)]),
        "1vit02": ("Which vitamin C serum?", [used("v3", VEGA, 4)]),
    })
    query = parse_query("vitamin c serum", model=None)
    assert [n.name for n in request_needs(query)] == ["vitamin", "c"] and judged_needs(query) == ()
    result = answer("vitamin c serum", library)
    pick = next(p for p in result.answer.picks if p.name == VEGA[0])
    assert pick.reason == "Recommended by 3 credible voices, 3 of them after long-term use."  # never "about vitamin or c"
    vega = next(p for p in result.ranking.products if p.name == VEGA[0])
    assert vega.breakdown.credible_recommends_fitting_need == 0


def test_the_reason_names_the_needs_in_the_requests_order_even_when_no_comment_talks_about_both(tmp_path):
    # Each recommendation talks about one need; the first written about the second one asked for. The request asks
    # about combination skin first, so the reason does too.
    library = write_library(tmp_path, {
        "1com01": ("Serum recommendations?", [used("w1", WREN, 2, "it stopped my breakouts"),
                                              used("w2", WREN, 3, "it suits my combination skin")]),
        "1com02": ("Which serum do you use?", [used("w3", WREN, 4)]),
    })
    result = answer("serum for combination skin with breakouts", library)
    pick = next(p for p in result.answer.picks if p.name == WREN[0])
    assert pick.reason == ("Recommended by 3 credible voices, 3 of them after long-term use, 2 of them about "
                           "combination skin or acne-prone skin.")


@pytest.mark.parametrize("request_text, needs", [
    # A need's name written with a space is that need, every word of it: "prone" alone names nothing.
    ("cleanser for acne prone skin", ["acne-prone"]),
    ("fragrance free moisturiser", ["fragrance-free"]),
    ("reef safe sunscreen", ["reef-safe"]),
    ("dishwasher safe frying pan", ["dishwasher-safe"]),
    ("non comedogenic moisturiser", ["non-comedogenic"]),
    ("stainless steel kettle", ["stainless steel"]),
    # Written with its hyphen, as before.
    ("cleanser for acne-prone skin", ["acne-prone"]),
    # A budget's words are no needs, whatever its currency.
    ("cast iron skillet under 50 bucks", []),
    ("lip balm that fixes cracked lips, less than 5 dollars", ["fixes", "cracked", "lips"]),
    ("a kettle under 40 pounds", []),
])
def test_only_real_needs_are_needs(request_text, needs):
    assert [n.name for n in request_needs(parse_query(request_text, model=None))] == needs


def test_a_budgets_word_is_no_need_word_for_the_threads_either():
    assert "buck" not in need_words(parse_query("cast iron skillet under 50 bucks", model=None))
    assert "dollar" not in need_words(parse_query("lip balm for cracked lips under 5 dollars", model=None))
