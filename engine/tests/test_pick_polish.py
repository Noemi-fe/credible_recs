"""Pick polish (decided by Claude, the orchestrator, 10 Oct 2026, as Noemi asked): three fixes to what a pick shows.

1. A brand pick never appears next to its own specific product. "first chef's knife under £100" showed both
   "Victorinox (their chef knives)" and "Victorinox chef's knife". When both qualify, the specific product stays and the
   brand pick steps aside (listed on the result with the product it stepped aside for); its support isn't added to
   the product's, so nothing counts twice.
2. A brand pick can't be checked against product facts (a brand has many products), so when the request has a hard
   requirement its product type can have (PFAS-free, non-stick, fragrance-free...), brand picks are left out and
   listed with the reason. "non-stick frying pan without PFAS" showed "Tramontina (their frying pans)", whose non-stick
   pans are mostly PTFE-coated.
3. Care tips most writers agree on come first: tips that say the same thing are grouped, the group with the most
   distinct credible writers is shown first, and repairs ("smooth with an angle grinder") come after looking-after
   tips ("descale with vinegar").

Every library, product and tip here is made up; no test reads data/.
"""

from datetime import date
from itertools import count

import pytest

from engine import config
from engine.answer import unverified_claims, write_answer
from engine.care_tips import CareTip, CareTips, credible_care_tips, is_repair, similar_tips, tips_by_agreement
from engine.extract import Extraction, check_extraction
from engine.group_products import ProductGroup, ProductMention
from engine.models import Thread
from engine.pipeline import FoldedBrandPick, _same_brand, answer_request
from engine.product_facts import NotSuited, hard_requirements, uncheckable_brand_reason
from engine.query import parse_query
from engine.tests.factories import make_comment, make_thread
from engine.tests.ranking_factories import bodies_for
from engine.tests.test_answer import kitchen_case
from engine.tests.test_pipeline import FakeLive, praise, skillet_library, write_library

TODAY = date(2026, 10, 9)


def names(result) -> list[str]:
    return [pick.name for pick in result.answer.picks]


# --- 1. A brand pick steps aside for its own specific product ---

def knife_library(tmp_path, fibrox: tuple[int, int] = (2, 2)):
    """Two chef knife threads. "Victorinox" fits two Victorinox knives (so it is a brand pick), praised twice in each
    thread; the Victorinox Fibrox chef knife is praised `fibrox` times in each; the Mac and the Tojiro three times."""
    first, second = fibrox
    return write_library(tmp_path, {
        "1knif01": ("Best first chef knife?", "Budget about 100.", [
            praise("v1a", "Victorinox", 5), praise("v1b", "Victorinox", 6),
            *[praise(f"f1{i}", "Victorinox Fibrox chef knife", 3 + i) for i in range(first)],
            praise("r1a", "Victorinox Rosewood chef knife", 4),
            praise("m1a", "Mac Mighty chef knife", 7), praise("m1b", "Mac Mighty chef knife", 8),
            praise("t1a", "Tojiro DP gyuto", 5), praise("t1b", "Tojiro DP gyuto", 6),
        ]),
        "1knif02": ("Which chef knife lasts?", "Mine chipped.", [
            praise("v2a", "Victorinox", 9), praise("v2b", "Victorinox", 10),
            *[praise(f"f2{i}", "Victorinox Fibrox chef knife", 5 + i) for i in range(second)],
            praise("m2a", "Mac Mighty chef knife", 4), praise("t2a", "Tojiro DP gyuto", 3),
        ]),
    }, community="chefknives")


KNIFE_REQUEST = "first chef knife for a home cook"
VICTORINOX = "Victorinox (their chef knives)"
FIBROX = "Victorinox Fibrox chef knife"


def test_a_brand_pick_steps_aside_for_its_own_specific_product_when_both_qualify(tmp_path):
    result = answer_request(KNIFE_REQUEST, library_dir=knife_library(tmp_path), prices=[], today=TODAY)
    # Before the fix: Victorinox (their chef knives), Victorinox Fibrox chef knife, Mac Mighty chef knife.
    assert names(result) == [FIBROX, "Mac Mighty chef knife", "Tojiro DP gyuto"]
    assert result.folded_brand_picks == [FoldedBrandPick(VICTORINOX, FIBROX)]
    assert VICTORINOX not in [p.name for p in result.ranking.products]
    assert unverified_claims(result.answer, result.bodies) == []


def test_the_brand_picks_support_counts_for_nothing_so_nothing_counts_twice(tmp_path):
    result = answer_request(KNIFE_REQUEST, library_dir=knife_library(tmp_path), prices=[], today=TODAY)
    fibrox = next(p for p in result.ranking.products if p.name == FIBROX)
    assert fibrox.breakdown.credible_recommends == 4  # its own four, not the brand's four on top
    pick = next(p for p in result.answer.picks if p.name == FIBROX)
    assert all(quote.comment_id.startswith("f") for quote in pick.quotes)


def test_a_brand_pick_stays_when_its_specific_product_doesnt_qualify(tmp_path):
    result = answer_request(KNIFE_REQUEST, library_dir=knife_library(tmp_path, fibrox=(2, 0)), prices=[], today=TODAY)
    assert names(result) == [VICTORINOX, "Mac Mighty chef knife", "Tojiro DP gyuto"]
    assert result.folded_brand_picks == []


def test_the_brand_pick_comes_back_when_the_live_check_drops_its_products_support(tmp_path):
    # Since 10 Oct 2026 (evening) a brand pick steps aside only for its own product when that product is shown, so this
    # starts from the library where the Fibrox is shown (4 recommendations), and the live check takes 2 of them away.
    lib = knife_library(tmp_path)
    before = answer_request(KNIFE_REQUEST, library_dir=lib, prices=[], today=TODAY)
    assert FIBROX in names(before) and VICTORINOX not in names(before)
    fibrox = next(pick for pick in before.answer.picks if pick.name == FIBROX)
    gone = {quote.comment_id for quote in fibrox.quotes[:2]}
    after = answer_request(KNIFE_REQUEST, library_dir=lib, prices=[], today=TODAY, live_checker=FakeLive(gone=gone))
    assert after.live_dropped == {"gone": 2}
    assert names(after)[0] == VICTORINOX and FIBROX not in names(after)  # 2 credible recommendations left: not enough
    assert after.folded_brand_picks == []


def group(name: str, *other_names: str, loose: bool = False, category: str = "kitchen") -> ProductGroup:
    mentions = [ProductMention("t1", f"c{i}", n, category, "recommend") for i, n in enumerate((name,) + other_names)]
    return ProductGroup(f"{category}:{name.lower()}", name, category, mentions, loose)


@pytest.mark.parametrize("brand, product", [
    (group("Victorinox", loose=True), group("Victorinox chef’s knife")),  # the brand's words start the name
    (group("Le Creuset", loose=True), group("Le Creuset Signature skillet")),
    (group("CeraVe cleanser", loose=True, category="skincare"),
     group("CeraVe Hydrating Cleanser", category="skincare")),  # module 4 says it is one of the line's products
    (group("Lodge", "lodge", loose=True), group("Blacklock skillet", "Lodge Blacklock skillet")),  # any of its names
])
def test_a_brands_own_product(brand, product):
    assert _same_brand(brand, product)


@pytest.mark.parametrize("brand, product", [
    (group("Victorinox", loose=True), group("Wusthof Classic chef knife")),
    (group("Lodge", loose=True), group("Field Company skillet")),
    (group("Mac", loose=True), group("Tojiro DP gyuto")),
])
def test_another_brands_product(brand, product):
    assert not _same_brand(brand, product)


# --- 2. Brand picks and hard requirements ---

def pan_library(tmp_path):
    """Two frying pan threads. "Tramontina" fits two Tramontina pans (a brand pick), praised four times; neither of its
    pans qualifies on its own. The GreenPan and the Misen are praised three times each."""
    return write_library(tmp_path, {
        "1pan001": ("Best non-stick frying pan?", "Mine is peeling.", [
            praise("p1a", "Tramontina", 5), praise("p1b", "Tramontina", 6),
            praise("p1c", "Tramontina Professional frying pan", 3),
            praise("p1d", "Tramontina Professional frying pan", 4),
            praise("p1e", "Tramontina tri-ply frying pan", 2),
            praise("p1f", "GreenPan Valencia frying pan", 4), praise("p1g", "GreenPan Valencia frying pan", 5),
            praise("p1h", "Misen frying pan", 4), praise("p1i", "Misen frying pan", 5),
        ]),
        "1pan002": ("Which frying pan lasts?", "Ten years, ideally.", [
            praise("p2a", "Tramontina", 8), praise("p2b", "Tramontina", 9),
            praise("p2c", "GreenPan Valencia frying pan", 6), praise("p2d", "Misen frying pan", 6),
        ]),
    }, community="BuyItForLife")


TRAMONTINA = "Tramontina (their frying pans)"


def test_a_brand_pick_is_left_out_when_the_request_has_a_hard_requirement(tmp_path):
    result = answer_request("non-stick frying pan without PFAS", library_dir=pan_library(tmp_path), prices=[],
                            product_facts=[], today=TODAY)
    assert TRAMONTINA not in names(result) and TRAMONTINA not in [p.name for p in result.ranking.products]
    assert result.left_out_not_suited == [NotSuited(TRAMONTINA, "a whole brand can't be checked for PFAS or a "
                                                                "non-stick coating")]
    assert names(result) == ["GreenPan Valencia frying pan", "Misen frying pan"]


def test_a_brand_pick_stays_when_the_request_has_no_hard_requirement(tmp_path):
    result = answer_request("frying pan that lasts", library_dir=pan_library(tmp_path), prices=[], product_facts=[],
                            today=TODAY)
    assert names(result)[0] == TRAMONTINA and result.left_out_not_suited == []


def test_a_requirement_the_product_type_cant_have_never_leaves_a_brand_out(tmp_path):
    # "for a beginner" asks for a gentle strength, but a cast iron skillet has no strength to check.
    result = answer_request("cast iron skillet for a beginner", library_dir=skillet_library(tmp_path), prices=[],
                            product_facts=[], today=TODAY)
    assert "Lodge (their cast iron skillets)" in names(result) and result.left_out_not_suited == []


@pytest.mark.parametrize("request_text, rules", [
    ("non-stick frying pan without PFAS that actually lasts", ["PFAS", "not non-stick"]),
    ("retinol for a beginner with sensitive skin", ["too strong", "prescription only"]),
    ("fragrance-free moisturiser for very dry skin", ["fragrance"]),
    ("sunscreen that doesn't leave a white cast", ["white cast"]),
    ("plastic-free electric kettle", ["plastic"]),
    ("frying pan for induction", ["not induction"]),
    ("moisturiser for oily skin", []),  # a soft rule only: a caution, never a reason to leave a product out
    ("first chef's knife under £100 for a home cook", []),  # "beginner", but a chef knife has no facts
    ("cast iron skillet for a beginner that will last decades", []),
    ("frying pan that lasts", []),
])
def test_the_hard_requirements_of_a_request(request_text, rules):
    assert hard_requirements(parse_query(request_text)) == rules


def test_the_reason_a_brand_pick_is_left_out_wording_decided_by_claude():
    assert config.BRAND_PICK_UNCHECKABLE == "a whole brand can't be checked for {requirements}"
    assert uncheckable_brand_reason(["PFAS"]) == "a whole brand can't be checked for PFAS"
    assert uncheckable_brand_reason(["too strong", "prescription only"]) == (
        "a whole brand can't be checked for strength or prescription-only formulas")
    assert uncheckable_brand_reason(["PFAS", "not non-stick", "not induction"]) == (
        "a whole brand can't be checked for PFAS, a non-stick coating or working on an induction hob")


def test_every_hard_rule_has_a_name_for_the_reason():
    hard = {name for name, rule in config.PRODUCT_FACT_RULES.items() if rule["hard"]}
    assert hard <= set(config.HARD_REQUIREMENT_NAMES)


# --- 3. Care tips most writers agree on ---

_ids = count(1)


def care(tip: str, writer: str | None, *, is_kind: bool = True, voice: str = "high",
         quote: str | None = None) -> CareTip:
    """One credible care tip from a comment of its own, written by `writer` (None: a deleted account)."""
    comment = f"cPol{next(_ids)}"
    return CareTip(about="chef knife" if is_kind else "Tojiro DP Gyuto", is_kind=is_kind, tip=tip,
                   quote=quote or f"Honestly: {tip}, from comment {comment}.", thread_id="t1", comment_id=comment,
                   comment_url=f"https://www.reddit.com/r/test/comments/t1/comment/{comment}/", voice=voice,
                   badges=("well upvoted",), author=writer)


def shown_tips(own=(), kind=(), bodies_extra=None) -> list[str]:
    ranking, bodies, _ = kitchen_case()
    bodies = bodies | bodies_for(*own, *kind) | (bodies_extra or {})
    answer = write_answer(ranking, bodies, "chef knife", care={"tojiro-dp-gyuto": CareTips(list(own), list(kind))})
    assert unverified_claims(answer, bodies) == []
    return [c.tip for c in answer.picks[0].care]


def test_the_tip_most_writers_agree_on_comes_first():
    # The one high voice's tip loses to three medium voices who say the same thing in their own words.
    tips = [care("use filtered water", "ann"),
            care("descale with vinegar", "bo", voice="medium"),
            care("Descale it with vinegar.", "cy", voice="medium"),
            care("descaling with white vinegar regularly", "di", voice="medium")]
    assert shown_tips(kind=tips) == ["Descale with vinegar.", "Use filtered water."]


def test_one_writer_counts_once_however_many_times_they_say_it():
    tips = [care("descale with vinegar", "ann"), care("descale with vinegar monthly", "ann"),
            care("descale it with vinegar", "ann"),
            care("use filtered water", "bo"), care("use filtered water only", "cy")]
    assert shown_tips(kind=tips) == ["Use filtered water.", "Descale with vinegar."]


def test_deleted_accounts_count_once_per_comment():
    tips = [care("use filtered water", "ann"), care("hand wash only", None), care("hand wash it only", None)]
    assert shown_tips(kind=tips) == ["Hand wash only.", "Use filtered water."]


def test_on_a_tie_the_higher_voice_comes_first_then_the_products_own_tip():
    own_medium, kind_high = care("oil the blade", "ann", is_kind=False, voice="medium"), care("hone it", "bo")
    assert shown_tips(own=[own_medium], kind=[kind_high]) == ["Hone it.", "Oil the blade."]
    own_high, kind_high = care("oil the blade", "ann", is_kind=False), care("hone it", "bo")
    assert shown_tips(own=[own_high], kind=[kind_high]) == ["Oil the blade.", "Hone it."]


def test_repairs_come_after_looking_after_the_product_however_many_agree():
    repairs = [care("Seal a leaking water gauge with silicone", "ann", is_kind=False),
               care("seal the leaking water gauge with silicone", "bo", is_kind=False),
               care("smooth with an angle grinder", "cy")]
    upkeep = care("descale regularly", "di", voice="medium")
    assert shown_tips(own=repairs[:2], kind=[repairs[2], upkeep]) == ["Descale regularly.",
                                                                      "Seal a leaking water gauge with silicone."]


def test_the_best_writers_tip_and_quote_are_shown_and_the_next_writers_when_it_fails():
    best = care("descale with vinegar", "ann", quote="Descale with vinegar every week, trust me.")
    next_best = care("descaling it with white vinegar", "bo", voice="medium")
    other = care("use filtered water", "cy")
    # ann's comment was edited since: her quote is no longer in it, so bo's tip and quote take its place.
    tips = shown_tips(kind=[best, next_best, other], bodies_extra={best.comment_id: "I use a descaler now."})
    assert tips == ["Descaling it with white vinegar.", "Use filtered water."]


def test_tips_are_grouped_best_supported_first_each_best_writer_first():
    a, b = care("use filtered water", "ann", voice="medium"), care("use filtered water only", "bo")
    c = care("glue the handle back", "cy")
    d = care("hand wash only", "di")
    groups = tips_by_agreement(CareTips([c], [a, d, b]))
    assert [[t.comment_id for t in g] for g in groups] == [[b.comment_id, a.comment_id], [d.comment_id], [c.comment_id]]


def test_a_tip_joins_a_group_only_when_it_says_the_same_as_the_groups_first_tip():
    # "rinse with water" is like the second tip but not the first: a group never drifts through a chain of tips
    # (on the library, chaining gathered 46 cast iron writers into one group through words like oil, water, soap).
    first, second = care("descale with vinegar", "ann"), care("descale with vinegar and rinse with water", "bo")
    third = care("rinse with water", "cy")
    groups = tips_by_agreement(CareTips([], [first, second, third]))
    assert [[t.comment_id for t in g] for g in groups] == [[first.comment_id, second.comment_id], [third.comment_id]]


@pytest.mark.parametrize("a, b", [
    ("descale every 6 months", "Descale it every 6 months."),  # the same tip (same_tip)
    ("descale with vinegar", "descaling with white vinegar regularly"),  # endings and extra words aside
    ("don't brew tea in it", "never brew tea in it"),
    ("descale every 6 months", "descale every 6 weeks"),
])
def test_tips_that_say_the_same_thing(a, b):
    assert similar_tips(a, b) and similar_tips(b, a)


@pytest.mark.parametrize("a, b", [
    ("descale every 6 months", "descale with citric acid"),  # one word in common is not enough
    ("grind at 12 for pour-over", "grind at 20 for pour-over"),  # different numbers: different advice
    ("wash it with soap", "don't wash it with soap"),  # one says the opposite
    ("don't boil water and brew tea in the same vessel", "descale by boiling white vinegar in the water"),
    ("hand wash only", "use filtered water"),
])
def test_tips_that_say_different_things(a, b):
    assert not similar_tips(a, b) and not similar_tips(b, a)


@pytest.mark.parametrize("tip", [
    "Seal a leaking water gauge with silicone", "Smooth with an angle grinder", "glue the handle back on",
    "replace the gasket", "solder the loose wire", "sand it smooth", "Grind it flat for a smooth surface",
    "fill the crack with epoxy", "repair carefully: no toxins from glues", "sanding with sandpaper takes 2+ hours",
])
def test_a_repair(tip):
    assert is_repair(tip)


@pytest.mark.parametrize("tip", [
    "descale with vinegar", "only grind with the top cap on", "run it while adjusting the grind setting",
    "brush out stuck grounds", "season it after every wash", "hand wash only",
])
def test_looking_after_the_product_is_not_a_repair(tip):
    assert not is_repair(tip)


def test_a_care_tip_knows_its_writer():
    thread = Thread.model_validate(make_thread(id="1kett01", category="kitchen", comments=[
        make_comment("k1aaaa", "1kett01", body="Descale it every 6 months and it lasts forever.")]))
    extraction = Extraction.model_validate({
        "thread_id": "1kett01", "instructions_version": "extract-v7", "extracted_at": "2026-10-09T10:00:00Z",
        "extractor": "claude-code", "mentions": [],
        "care": [{"comment_id": "k1aaaa", "about": "electric kettle", "is_kind": True, "tip": "descale every 6 months",
                  "quote": "Descale it every 6 months and it lasts forever."}]})
    [tip] = credible_care_tips([thread], {thread.id: check_extraction(extraction, thread)})
    assert tip.author == "test_user_k1aaaa"


# --- 4. A brand pick whose own products here aren't sold in the UK (decided by Claude, 10 Oct 2026) ---
# Found in the 10 Oct 2026 run: "Cuisinart (their electric kettles)" was a pick for b06, from American writers whose
# Cuisinart kettles (the CPK-17) aren't sold in the UK. When every specific product of the brand in these threads is
# known not to be sold in the UK, its writers most likely mean those, so the brand pick is left out with them.

def test_a_brand_pick_is_left_out_when_all_its_own_products_here_arent_sold_in_the_uk(tmp_path):
    from engine.tests.test_availability import listed

    gone = [listed("Tramontina Professional frying pan", available=False),
            listed("Tramontina tri-ply frying pan", available=False)]
    result = answer_request("frying pan that lasts", library_dir=pan_library(tmp_path), prices=gone, product_facts=[],
                            today=TODAY)
    assert TRAMONTINA not in names(result) and TRAMONTINA not in [p.name for p in result.ranking.products]
    assert TRAMONTINA in result.left_out_unavailable


def test_a_brand_pick_stays_when_one_of_its_products_here_is_sold_or_not_checked(tmp_path):
    from engine.tests.test_availability import listed

    library = pan_library(tmp_path)
    for prices in ([listed("Tramontina Professional frying pan", available=False),
                    listed("Tramontina tri-ply frying pan", available=True)],
                   [listed("Tramontina Professional frying pan", available=False)]):  # tri-ply: not checked
        result = answer_request("frying pan that lasts", library_dir=library, prices=prices,
                                product_facts=[], today=TODAY)
        assert names(result)[0] == TRAMONTINA and TRAMONTINA not in result.left_out_unavailable


# --- 5. Two brand picks of the same brand (decided by Claude, 10 Oct 2026) ---
# Found with 12 threads per question: "Lodge (their cast iron skillets)" and "Lodge cast iron" (a line, whose name already
# says the type) were both picks for b08. Like a brand pick next to its own product, the one ranked lower folds into the
# one ranked higher, so the same brand never takes two of the three places.

def lodge_lines_library(tmp_path):
    """"Lodge" and "Lodge cast iron" both fit the two Lodge cast iron skillets (so both are loose), each praised
    across both threads."""
    return write_library(tmp_path, {
        "1lod001": ("Best cast iron skillet for a beginner?", "My first one.", [
            praise("l1a", "Lodge", 9), praise("l1b", "Lodge", 8), praise("l1c", "Lodge", 7),
            praise("l1d", "Lodge cast iron", 6), praise("l1e", "Lodge cast iron", 5),
            praise("l1f", "Lodge cast iron Blacklock skillet", 2), praise("l1g", "Lodge cast iron Chef Collection skillet", 2),
            praise("l1h", "Smithey No. 10 skillet", 4), praise("l1i", "Smithey No. 10 skillet", 5),
        ]),
        "1lod002": ("Which cast iron skillet lasts?", "Mine cracked.", [
            praise("l2a", "Lodge", 6), praise("l2b", "Lodge cast iron", 4),
            praise("l2c", "Smithey No. 10 skillet", 3),
        ]),
    }, community="castiron")


def test_two_brand_picks_of_the_same_brand_fold_into_the_one_ranked_higher(tmp_path):
    result = answer_request("cast iron skillet that lasts", library_dir=lodge_lines_library(tmp_path), prices=[],
                            product_facts=[], today=TODAY)
    lodge = [name for name in names(result) if name.lower().startswith("lodge")]
    assert len(lodge) == 1, names(result)
    [folded] = [item for item in result.folded_brand_picks if item.name.lower().startswith("lodge")]
    assert folded.stepped_aside_for == lodge[0] and folded.name != lodge[0]


# --- 6. A brand pick steps aside only for its own product that is shown (10 Oct 2026) ---
# Found in the evening run: "Lodge (their cast iron skillets)", by far b08's strongest product, stepped aside for "lodge
# cast iron pan", which just met the minimum but ranked below the top 3, so Lodge vanished from the answer. The rule is
# there so a brand and its own product are never shown together: it applies only when that product is shown.

def lodge_far_ahead_library(tmp_path):
    """"Lodge" (fitting two Lodge skillets) praised 6 times; three other skillets 4 times each; the Lodge Blacklock
    skillet only just qualifies (3 times, both threads), behind them."""
    return write_library(tmp_path, {
        "1far001": ("Best cast iron skillet for a beginner?", "My first one.", [
            praise("f1a", "Lodge", 30), praise("f1b", "Lodge", 25), praise("f1c", "Lodge", 20),
            praise("f1d", "Smithey No. 10 skillet", 9), praise("f1e", "Smithey No. 10 skillet", 8),
            praise("f1f", "Field No. 8 skillet", 9), praise("f1g", "Field No. 8 skillet", 8),
            praise("f1h", "Finex 10 skillet", 9), praise("f1i", "Finex 10 skillet", 8),
            praise("f1j", "Lodge Blacklock skillet", 1), praise("f1k", "Lodge Blacklock skillet", 1),
            praise("f1l", "Lodge Chef Collection skillet", 1),
        ]),
        "1far002": ("Which cast iron skillet lasts?", "Mine cracked.", [
            praise("f2a", "Lodge", 15), praise("f2b", "Lodge", 12), praise("f2c", "Lodge", 10),
            praise("f2d", "Smithey No. 10 skillet", 7), praise("f2e", "Smithey No. 10 skillet", 6),
            praise("f2f", "Field No. 8 skillet", 7), praise("f2g", "Field No. 8 skillet", 6),
            praise("f2h", "Finex 10 skillet", 7), praise("f2i", "Finex 10 skillet", 6),
            praise("f2j", "Lodge Blacklock skillet", 1),
        ]),
    }, community="castiron")


def test_a_brand_pick_stays_when_its_own_product_qualifies_but_isnt_shown(tmp_path):
    result = answer_request("cast iron skillet that lasts", library_dir=lodge_far_ahead_library(tmp_path), prices=[],
                            product_facts=[], today=TODAY)
    blacklock = next(p for p in result.ranking.products if p.name == "Lodge Blacklock skillet")
    assert blacklock.qualifies and "Lodge Blacklock skillet" not in names(result)  # qualifies, but not in the top 3
    assert names(result)[0] == "Lodge (their cast iron skillets)"
    assert result.folded_brand_picks == []
