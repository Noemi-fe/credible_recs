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
from engine.needs import judged_needs, needs_met, request_needs
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
    # Changed on purpose 16 Oct 2026 (the interview-fixes builder): "fixes" is filler and "lips" the product's own word
    # (a lip balm's), as the reviews of that day found in reason lines ("about fixes, cracked or lips"); was
    # ["fixes", "cracked", "lips"].
    ("lip balm that fixes cracked lips, less than 5 dollars", ["cracked"]),
    ("a kettle under 40 pounds", []),
])
def test_only_real_needs_are_needs(request_text, needs):
    assert [n.name for n in request_needs(parse_query(request_text, model=None))] == needs


def test_a_budgets_word_is_no_need_word_for_the_threads_either():
    assert "buck" not in need_words(parse_query("cast iron skillet under 50 bucks", model=None))
    assert "dollar" not in need_words(parse_query("lip balm for cracked lips under 5 dollars", model=None))


# --- Need words that say something (16 Oct 2026, the interview-fixes builder) ---
# The breadth-first reviews of 16 Oct found reason lines saying "about someone", "about night or cream", "about steam,
# wand or at", "about non or stick", "about makes or brown": filler words, the product's own names and two-word needs
# split in two. Requests below are the interviewees' kind; every comment is made up.

def judged(request_text: str) -> list[str]:
    """The judged needs as the reason line names them: a word of two that make one need by both (Need.label)."""
    return list(dict.fromkeys(need.label or need.name for need in judged_needs(parse_query(request_text, model=None))))


@pytest.mark.parametrize("request_text, needs", [
    # Filler is no need.
    ("retinol for someone with rosacea", ["sensitive"]),
    ("vitamin c serum that doesn't oxidise quickly", ["oxidise"]),
    ("espresso machine w a proper steam wand, willing to spend at least €400", ["steam wand"]),
    # Changed on purpose 17 Oct 2026 (the ws-names builder, need words round two): two words that make one need are
    # named whole with a word that is no need on its own too (config.NEED_PHRASES: "dog hair"). Was: ["dog"].
    ("robot vacuum that handles dog hair under £300", ["dog hair"]),
    ("enameled dutch oven 5.5 quart, from 100 to 200 euro", ["enameled"]),
    # Changed on purpose 17 Oct 2026 (the ws-names builder): "cracked lips" is named whole, its "lips" the product's
    # word (config.NEED_PHRASES). Was: ["cracked"].
    ("lip balm that actually fixes cracked lips, less than 5 dollars", ["cracked lips"]),
    ("cutting board that's easy on knives", ["knives"]),
    ("knife sharpener for japanese knives", ["japanese"]),  # the type's own word, in the plural
    # In skincare and haircare the product's own names and clue words are no needs: a night cream's "night" and
    # "cream", a sunscreen's "spf", a cleansing oil's "cleansing" and "oil", a wash's "wash".
    ("night cream for my 40s", ["mature"]),
    ("spf for sensitive skin with no white cast", ["sensitive", "no white cast"]),
    # Changed on purpose 17 Oct 2026 (the ws-names builder): "double cleansing" is named whole (config.NEED_PHRASES).
    # Was: ["double", "beginner"].
    ("double cleansing oil for beginners", ["double cleansing", "beginner"]),
    ("pimple patches for acne", ["acne-prone"]),
    ("salicylic acid wash", []),
    # In kitchen and general requests a kind the type's names hold stays a need: it is what they ask ("gaming").
    ("best gaming laptop under 800", ["gaming"]),
    # Changed on purpose 17 Oct 2026 (the ws-names builder, the orchestrator's item: kitchen and general reason lines
    # never name the type's own words): the last word of the type's name the request uses is the product's ("about
    # freezer" in a fridge freezer answer). Was: ["freezer", "quiet"].
    ("fridge freezer that's quiet", ["quiet"]),
    # Two words that make one need are named whole, as typed; "kitchen" alone is no need.
    ("eye cream for dark circles", ["dark circles"]),
    ("burr grinder for pour over, 150 or less, im in the uk", ["pour over"]),
    ("rice cooker that makes good brown rice", ["brown rice"]),
    ("blender for smoothies with frozen fruit", ["smoothies", "frozen fruit"]),
    ("a mattress for back pain", ["back pain"]),
    ("running shoes for flat feet", ["flat feet"]),
    ("air fryer for a small kitchen", ["small kitchen"]),
    # Changed on purpose 17 Oct 2026 (the ws-names builder): "cooler" is the last word of the fridge's name "wine cooler",
    # the product's; "wine", the kind, stays. Was: ["wine", "cooler"].
    ("wine cooler for the kitchen", ["wine"]),
    ("28cm frying pan, non stick but pfas free, £30-60", ["non stick", "pfas"]),
    # Written as one word, as before.
    ("burr coffee grinder for pour-over under £150", ["pour-over"]),
    ("non-stick frying pan without PFAS that actually lasts", ["non-stick", "PFAS", "lasting"]),
])
def test_only_words_that_say_what_is_asked_are_judged_needs(request_text, needs):
    assert judged(request_text) == needs


def test_two_words_that_make_one_need_are_named_whole_and_found_by_their_words():
    needs = judged_needs(parse_query("eye cream for dark circles", model=None))
    assert [(need.name, need.label) for need in needs] == [("dark", "dark circles"), ("circles", "dark circles")]
    assert needs_met("It made my dark circles much lighter.", needs) == ("dark", "circles")  # as before


def test_the_reason_names_two_words_that_make_one_need_whole(tmp_path):
    vela = ("Vela Eye Cream", "eye cream")
    library = write_library(tmp_path, {
        "1eye01": ("Eye cream for dark circles?", [used("v1", vela, 2, "my dark circles are much lighter"),
                                                  used("v2", vela, 3, "the circles under my eyes faded")]),
        "1eye02": ("Which eye cream do you use?", [used("v3", vela, 4, "it helped my dark circles")]),
    })
    result = answer("eye cream for dark circles", library)
    [pick] = result.answer.picks
    assert pick.reason.endswith("3 of them about dark circles."), pick.reason
    assert unverified_claims(result.answer, result.bodies) == []


@pytest.mark.parametrize("request_text, body", [
    ("vitamin c serum that doesn't oxidise quickly", "Mine oxidized within a month."),
    ("vitamin c serum that doesn't oxidise quickly", "No oxidation after three months in the fridge."),
    ("vitamin c serum that doesn't oxidise quickly", "It started oxidising in the bottle."),
    ("vitamin c serum that doesn't oxidize quickly", "It had oxidised by the time I opened it."),
    ("earbuds with noise cancelling for the gym", "The noise canceling works brilliantly on the train."),
    ("kettle in a nice colour", "It comes in a great color."),
    ("enamelled dutch oven", "The enameled one is lovely to cook in."),
])
def test_british_and_us_spellings_meet(request_text, body):
    needs = judged_needs(parse_query(request_text, model=None))
    assert needs_met(body, needs), (request_text, body)


def test_rosacea_reads_as_sensitive_skin_and_its_rules_apply():
    from engine.product_facts import request_asks

    query = parse_query("retinol for someone with rosacea", model=None)
    assert "sensitive" in request_asks(query)
    assert needs_met("My rosacea flared for a week.", judged_needs(query)) == ("sensitive",)
