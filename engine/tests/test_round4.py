"""Round 4 of the convergence (19 Oct 2026): Noemi's decisions of 19 Oct 2026 (DECISIONS.md), each built and tested here
but for (m), the blind-test packets' "why" (engine/tests/test_blind_test.py).

(b) When the first and the wider reading give as many picks, the wider one wins if more of its picks have a credible
    voice about the request's need or feature. (d) A top-level answer in a thread whose title asks for the need counts
    as talking about it, in the need rule and the feature rule; replies further down still need their own words. (g)
    Essences stay out of toner answers. (h) A travel system is a stroller pick. (i) For fast-moving tech, a comment older
    than config.FAST_MOVING_OLD_EVIDENCE_YEARS counts only for a product, or a line, known to be still sold. (j) A
    credible warning against a whole kind pushes its products down. (k) A facts entry's shown note (HexClad's earlier
    coating). (c) No country preference: a product sold only abroad counts as still sold for (i).

Every thread, writer, comment, product and link here is made up, but for HexClad's facts entry.
"""

import json
from dataclasses import replace
from datetime import date
from pathlib import Path

from engine import config, pipeline
from engine.answer import write_answer
from engine.brand_lines import BrandLine
from engine.group_products import ProductGroup, ProductMention
from engine.needs import judged_needs
from engine.pipeline import WIDER_READING_SHORTFALL, answer_request
from engine.prices import Price, PriceCheck
from engine.product_facts import ProductFacts, load_product_facts
from engine.query import parse_query
from engine.rank import rank_products
from engine.tests.factories import make_comment, make_thread, write_gold
from engine.tests.ranking_factories import bodies_for, mention, mentions, note

TODAY = date(2026, 10, 19)


def write_library(tmp_path: Path, threads) -> Path:
    """threads: (id, community, category, title, [(comment id, the comment it replies to or None, body, product,
    stance)])."""
    made, extractions = [], {}
    for tid, community, category, title, comments in threads:
        made.append(make_thread(id=tid, community=community, category=category, title=title, body="Any advice?",
                                url=f"https://www.reddit.com/r/{community}/comments/{tid}/t/",
                                comments=[make_comment(cid, thread_id=tid, parent_id=parent, body=body,
                                                       url=f"https://www.reddit.com/r/{community}/comments/{tid}/"
                                                           f"comment/{cid}/")
                                          for cid, parent, body, _, _ in comments]))
        extractions[tid] = [{"comment_id": cid, "product": product, "category": category, "stance": stance,
                             "quote": body} for cid, _, body, product, stance in comments]
    root = write_gold(tmp_path / "library", made, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for tid, found in extractions.items():
        (root / "extracted" / f"{tid}.json").write_text(json.dumps({
            "thread_id": tid, "instructions_version": "extract-v5", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": found}), encoding="utf-8")
    return root


# --- (b) Ties between the readings ---

def reading(query, *products: tuple[str, tuple[str, ...], tuple[str, ...]]) -> pipeline.PipelineResult:
    """A reading whose picks are these products, each with 3 credible recommendations over 2 threads that talk about
    these needs and praise it for these features."""
    items = [replace(m, needs=needs, features=features)
             for name, needs, features in products for m in mentions(3, name, category="general")]
    features = sorted({f for _, _, named in products for f in named})
    result = pipeline.PipelineResult(query)
    result.ranking = rank_products(items, "general", features=features)
    result.answer = write_answer(result.ranking, bodies_for(*items), query.product_type)
    return result


def test_with_as_many_picks_the_wider_reading_wins_when_more_of_its_picks_have_a_voice_about_the_need():
    # Noemi's decision (b) of 19 Oct 2026: "smartwatch for fitness" gave one pick in each reading, Huawei's watch first
    # (no voice about fitness) and Garmin's in the wider reading; the first reading had stayed.
    query = parse_query("smartwatch for fitness", model=None)
    assert [need.name for need in judged_needs(query)] == ["fitness"]
    first = reading(query, ("Halo GT watch", (), ()))
    wider = reading(query, ("Garmin Forerunner watch", ("fitness",), ()))
    assert len(first.answer.picks) == len(wider.answer.picks) == 1
    assert pipeline._wider_wins(first, wider, query)
    assert not pipeline._wider_wins(wider, first, query)
    # As many picks with such a voice: the first reading stays, the closest to the request.
    assert not pipeline._wider_wins(reading(query, ("Halo GT watch", ("fitness",), ())), wider, query)
    # More picks win as before, voiced or not; fewer never do.
    two = reading(query, ("Halo GT watch", (), ()), ("Polar Pacer watch", (), ()))
    assert pipeline._wider_wins(first, two, query)
    assert not pipeline._wider_wins(two, wider, query)


def test_a_voice_praising_a_pick_for_the_feature_asked_for_counts_too():
    query = parse_query("noise cancelling headphones", model=None)
    first = reading(query, ("Sonicwave Q2 headphones", (), ()), ("Brightline B5 headphones", (), ()))
    wider = reading(query, ("Sonicwave Q2 headphones", (), ("noise cancelling",)),
                    ("Calmtone C9 headphones", (), ()))
    assert pipeline._wider_wins(first, wider, query)


# --- (d) A top-level answer in a thread whose title asks for the need ---

def creams(tmp_path: Path) -> Path:
    # Fern cream's voices answer the posts asking for dry skin, Moss cream's reply to other answers; none says "dry".
    return write_library(tmp_path, [
        ("1dz001", "SkincareAddiction", "skincare", "Moisturiser for dry skin?", [
            ("d1a", None, "I've used the Fern cream for 2 years, it is lovely.", "Fern cream", "recommend"),
            ("d1b", None, "I've had the Fern cream for a year, my face loves it.", "Fern cream", "recommend"),
            ("d1c", "d1a", "I've used the Moss cream for 3 years, it is lovely too.", "Moss cream", "recommend"),
            ("d1d", "d1b", "Moss cream for 4 years here, never going back.", "Moss cream", "recommend"),
        ]),
        ("1dz002", "SkincareAddiction", "skincare", "Best moisturiser for dry winter skin?", [
            ("d2a", None, "I've used the Fern cream every winter for 3 years, it works.", "Fern cream", "recommend"),
            ("d2b", "d2a", "I've had the Moss cream for 2 years, love it.", "Moss cream", "recommend"),
        ]),
    ])


def test_a_top_level_answer_in_a_thread_asking_for_the_need_talks_about_it_and_a_reply_needs_its_own_words(tmp_path):
    # Noemi's decision (d) of 19 Oct 2026, for the need rule of every skincare and haircare reading.
    result = answer_request("moisturiser for dry skin", library_dir=creams(tmp_path), today=TODAY)
    assert [pick.name for pick in result.answer.picks] == ["Fern cream"]
    moss = next(p for p in result.ranking.products if p.name == "Moss cream")
    assert not moss.qualifies and moss.shortfall == WIDER_READING_SHORTFALL
    fern = next(p for p in result.ranking.products if p.name == "Fern cream")
    # For the need rule: its reason, weight and standing out go by its own words, which never say "dry".
    assert all(m.needs_by_title == ("dry",) and m.needs == () for m in fern.credible_recommendations)
    assert "about" not in result.answer.picks[0].reason


def kettles(tmp_path: Path) -> Path:
    # Brio's voices in the thread asking for a quiet kettle are replies, and none says it is quiet; Calm's answer it.
    return write_library(tmp_path, [
        ("1kz001", "BuyItForLife", "kitchen", "Which quiet electric kettle should I buy?", [
            ("k1a", None, "I've had my Calm kettle for 3 years, love it.", "Calm kettle", "recommend"),
            ("k1b", None, "My Calm kettle has lasted 4 years so far.", "Calm kettle", "recommend"),
            ("k1c", "k1a", "I've used the Brio kettle every day for 6 years, still perfect.", "Brio kettle",
             "recommend"),
            ("k1d", "k1b", "My Brio kettle has lasted 8 years so far.", "Brio kettle", "recommend"),
        ]),
        ("1kz002", "BuyItForLife", "kitchen", "Electric kettle recommendations?", [
            ("k2a", None, "Our Brio kettle is 9 years old and still going strong.", "Brio kettle", "recommend"),
            ("k2b", None, "I've had the Brio kettle for 5 years, love it.", "Brio kettle", "recommend"),
            ("k2c", None, "Had my Calm kettle 4 years, it pours well.", "Calm kettle", "recommend"),
        ]),
    ])


def test_only_a_top_level_answer_is_praised_for_the_feature_its_threads_title_asks_for(tmp_path):
    # The feature rule (Noemi's decision 1 of 16 Oct 2026) under her decision (d): until 19 Oct 2026 every comment of a
    # thread asking for the feature counted, replies too.
    result = answer_request("a quiet electric kettle", library_dir=kettles(tmp_path), today=TODAY)
    assert [pick.name for pick in result.answer.picks] == ["Calm kettle", "Brio kettle"]
    praised = {p.name: p.features_praised for p in result.ranking.products}
    assert praised == {"Calm kettle": ("quiet",), "Brio kettle": ()}


def test_a_reply_is_not_an_answer_to_the_post():
    thread = make_thread(id="1az001", comments=[make_comment("a1", "1az001"),
                                                make_comment("a2", "1az001", parent_id="a1")])
    from engine.models import Thread
    thread = Thread.model_validate(thread)
    assert [pipeline._answers_the_post(c, thread) for c in thread.comments] == [True, False]


# --- (g) Essences stay out of toner answers ---

def group(name: str, *types: str) -> ProductGroup:
    return ProductGroup(key=f"skincare:{name.lower()}", name=name, category="skincare",
                        mentions=[ProductMention("t1", f"c{i}", name, "skincare", "recommend", product_type=t)
                                  for i, t in enumerate(types or (None,))])


def test_an_essence_is_another_type_in_a_toner_answer():
    toner = parse_query("hydrating toner for dehydrated skin", model=None)
    assert toner.product_type == "toner"
    assert pipeline._another_type(group("COSRX Advanced Snail 96 Mucin Power Essence"), toner)
    assert pipeline._another_type(group("COSRX snail mucin", "essence", "essence"), toner)
    assert pipeline._another_type(group("COSRX Snail 96 Mucin Power Essence", "toner"), toner)  # its name says essence
    # A toner, whatever else its name says, stays: "Essence Toner" is a toner.
    for kept in (group("Pyunkang Yul Essence Toner"), group("Pyunkang Yul Essence Toner", "essence"),
                 group("I'm From Rice Toner"), group("Laneige Cream Skin", "toner")):
        assert not pipeline._another_type(kept, toner)
    # A request naming an essence still routes to toners, and keeps its essences.
    essence = parse_query("hydrating essence", model=None)
    assert essence.product_type == "toner"
    assert not pipeline._another_type(group("COSRX Advanced Snail 96 Mucin Power Essence"), essence)
    # Other types' answers are as before: an essence-named sunscreen is still a sunscreen (9 Oct 2026).
    sunscreen = parse_query("lightweight sunscreen for oily skin", model=None)
    assert not pipeline._another_type(group("Biore UV Aqua Rich Watery Essence"), sunscreen)


def test_inside_a_toner_brands_line_a_mention_of_its_essence_counts_for_nothing():
    toner = parse_query("hydrating toner", model=None)
    result = pipeline.PipelineResult(toner)
    line = ProductGroup(key="skincare:cosrx", name="COSRX", category="skincare", loose=True, mentions=[
        ProductMention("t1", "c1", "COSRX", "skincare", "recommend", product_type="toner"),
        ProductMention("t1", "c2", "COSRX snail essence", "skincare", "recommend", product_type="essence")])
    found = pipeline._of_another_type([line], toner, result)
    assert [m[0].comment_id for m in found] == ["c2"]


# --- (h) A travel system is a stroller pick ---

def test_a_travel_system_is_a_stroller():
    # Noemi's decision (h) of 19 Oct 2026: it already was (the 17 Oct type rules keep a bundle as the product it holds,
    # and "travel system" is one of the stroller's names); kept so by this test.
    stroller = parse_query("pram that folds small for a car boot", model=None)
    assert stroller.product_type == "stroller"
    for name in ("Graco FastAction Jogger travel system", "Evenflo pivot travel system"):
        assert not pipeline._another_type(ProductGroup(key=f"general:{name.lower()}", name=name, category="general",
                                                       mentions=[ProductMention("t1", "c1", name, "general",
                                                                                "recommend")]), stroller)
    assert not pipeline._another_type_by_ai(["travel system"], "stroller")


# --- (i) Old evidence for fast-moving tech ---

def test_an_old_comment_counts_only_for_a_product_or_line_known_to_be_still_sold():
    assert config.FAST_MOVING_OLD_EVIDENCE_YEARS == 5
    assert "tv" in config.FAST_MOVING_TYPES and "laptop" in config.FAST_MOVING_TYPES
    old = [mention("Lumen X1 laptop", f"t{i}", comment=f"old{i}", category="general") for i in range(3)]
    warning = mention("Lumen X1 laptop", "t1", comment="oldw", stance="warn", category="general")
    new = mention("Lumen X1 laptop", "t2", comment="new1", category="general")
    written = {"old0": date(2014, 5, 1), "old1": date(2019, 1, 2), "old2": date(2021, 10, 18),
               "oldw": date(2016, 3, 3), "new1": date(2024, 6, 1)}
    every = old + [warning, new]
    # Not known to be sold: its comments older than 5 years (before 19 Oct 2021) say nothing for or against it.
    kept = pipeline._set_aside_old_evidence(every, written, still_sold=set(), today=TODAY)
    assert [m.comment_id for m in kept] == ["new1"]
    # Known to be sold: every comment counts, whatever its age.
    assert pipeline._set_aside_old_evidence(every, written, still_sold={old[0].product_key}, today=TODAY) == every


def price(available, **more) -> Price:
    return Price(product="Lumen X1", category="general", price=None, currency="GBP", shop="Made-up Shop",
                 url="https://shop.example/lumen-x1", checked_on=date(2026, 10, 15), available=available, **more)


def test_still_sold_means_a_price_list_entry_counting_it_as_sold_abroad_too_or_a_brand_line_that_sells_the_type():
    # Noemi's decision (c) of 19 Oct 2026: no country preference anywhere in ranking, so a product sold only outside the
    # UK (not_in_uk) is as still sold as one sold here.
    checks = {"sold": PriceCheck(None, "unknown", availability=price(True)),
              "abroad": PriceCheck(None, "unknown", availability=price(False, not_in_uk=True)),
              "gone": PriceCheck(None, "unknown", availability=price(False)),
              "used": PriceCheck(None, "unknown", availability=price(True, second_hand=True)),
              "unchecked": PriceCheck(None, "unknown")}
    line = BrandLine(brand="Lumen", category="general", product_type="laptop", sells=True,
                     sources=["https://maker.example/laptops"], checked_on=date(2026, 10, 1))
    not_selling = line.model_copy(update={"sells": False})
    assert pipeline._known_still_sold(checks, {"line": line, "no line": not_selling}) == {"sold", "abroad", "line"}


# --- (j) A credible warning against a whole kind ---

def test_a_credible_warning_against_a_kind_ranks_its_products_below_others_with_similar_support():
    electric = mentions(3, "Zapedge electric sharpener", weight=1.2)  # 3.6 points
    stone = mentions(3, "Kuro 1000 whetstone", weight=1.0)  # 3.0 points
    placed = {"electric-sharpener": [electric[0].product_key]}
    warned = [note("electric sharpener", "t1", stance="warn"), note("electric sharpener", "t2", stance="warn")]
    before = rank_products(electric + stone, "kitchen", [], placed)
    assert [p.name for p in before.qualifying] == ["Zapedge electric sharpener", "Kuro 1000 whetstone"]
    after = rank_products(electric + stone, "kitchen", warned, placed)
    assert [p.name for p in after.qualifying] == ["Kuro 1000 whetstone", "Zapedge electric sharpener"]
    zap = after.qualifying[1]
    assert zap.breakdown.kind_bonus == -config.KIND_WARNING_PENALTY and zap.breakdown.kind == "electric sharpener"
    # Far more support still wins: the push is the size of the leading kind's bonus.
    many = mentions(6, "Zapedge electric sharpener", weight=1.2)
    assert rank_products(many + stone, "kitchen", warned, placed).qualifying[0].name == "Zapedge electric sharpener"
    # Warned off as a product is: two writers' warnings (one thread is enough), outnumbering the kind's credible
    # recommendations. One writer's warning alone, or warnings outweighed, push nothing.
    one_thread = [note("electric sharpener", "t1", stance="warn"), note("electric sharpener", "t1", stance="warn")]
    assert rank_products(electric + stone, "kitchen", one_thread, placed).qualifying[0].name == "Kuro 1000 whetstone"
    for notes in ([note("electric sharpener", "t1", stance="warn")],
                  warned + [note("electric sharpener", "t1"), note("electric sharpener", "t2")]):
        assert rank_products(electric + stone, "kitchen", notes, placed).qualifying[0].name == "Zapedge electric sharpener"
    # Only a product whose own kind (its best-supported one) is warned off: placed in a well-liked kind too, it isn't.
    both = {**placed, "guided-system": [electric[0].product_key]}
    liked = warned + [note("guided system", "t1"), note("guided system", "t2")]
    assert rank_products(electric + stone, "kitchen", liked, both).qualifying[0].name == "Zapedge electric sharpener"
    # Nor a kind the pipeline says pushes nothing (the request names it, or its warnings say only what it is bad for).
    kept = rank_products(electric + stone, "kitchen", warned, placed, kinds_not_pushed={"electric-sharpener"})
    assert kept.qualifying[0].name == "Zapedge electric sharpener"


def test_a_kind_the_request_names_or_warned_about_for_one_use_pushes_nothing():
    from engine.group_kinds import KindGroup

    kinds = [KindGroup(key="electric", name="electric knife sharpener"), KindGroup(key="oil", name="oil cleanser"),
             KindGroup(key="hyaluronic acid", name="hyaluronic acid in dry climates"),
             KindGroup(key="kitchenaid", name="KitchenAid stand mixers for bread"),
             KindGroup(key="pull through", name="pull-through sharpener")]
    sharpener = parse_query("knife sharpener for japanese knives", model=None)
    assert pipeline._kinds_not_pushed(kinds, sharpener) == {"hyaluronic acid", "kitchenaid"}
    cleanser = parse_query("double cleansing oil for beginners", model=None)
    assert {"oil", "hyaluronic acid", "kitchenaid"} <= pipeline._kinds_not_pushed(kinds, cleanser)
    assert "electric" in pipeline._kinds_not_pushed(kinds, parse_query("electric knife sharpener", model=None))


# --- (k) A facts entry's shown note ---

HEXCLAD_NOTE = "most reviews here are of its earlier PTFE-coated pans"  # wording approved by Noemi, 19 Oct 2026


def test_a_facts_entrys_shown_note_is_shown_under_its_product():
    entry = ProductFacts(product="Hexwell Hybrid Pan", category="kitchen", product_type="frying pan",
                         facts={"non_stick": True, "pfas_free": True}, sources=["https://maker.example/faq"],
                         checked_on=date(2026, 10, 18), shown_note="most reviews here are of its earlier coating")
    pan = ProductGroup(key="kitchen:hexwell hybrid pan", name="Hexwell Hybrid Pan", category="kitchen",
                       mentions=[ProductMention("t1", "c1", "Hexwell Hybrid Pan", "kitchen", "recommend")])
    for request in ("non-stick frying pan without PFAS", "frying pan"):
        query = parse_query(request, model=None)
        kept, cautions, _ = pipeline._suited_to_request([pan], query, [entry], pipeline.PipelineResult(query))
        assert [g.name for g in kept] == ["Hexwell Hybrid Pan"]
        assert cautions[pan.key] == ["most reviews here are of its earlier coating"]


def test_hexclads_facts_say_pfas_free_from_its_current_coating_with_a_note_about_the_earlier_one():
    entry = next(e for e in load_product_facts() if e.product == "HexClad")
    assert entry.facts["pfas_free"] is True
    assert entry.shown_note == HEXCLAD_NOTE


# --- Item 10: a shown quote never asks for other products or suggestions (Noemi, 19 Oct 2026) ---

def test_a_quote_asking_for_other_products_is_cut_to_the_clause_carrying_its_stance_or_not_shown():
    from engine.answer import _without_asking

    cut = _without_asking("I love the Velvra cream, but I want something richer for winter, any suggestions?",
                          "recommend", ("Velvra cream",))
    assert cut == "I love the Velvra cream"
    assert _without_asking("Had my Brio kettle for 6 years and it still works great. Bit loud though. Anyone know of a "
                           "good alternative?", "recommend", ("Brio kettle",)) == ("Had my Brio kettle for 6 years and "
                                                                                    "it still works great.")
    assert _without_asking("Mine cracked after a month, what would you recommend instead?", "warn") == (
        "Mine cracked after a month")
    # No clean clause carries the stance before the question: not shown.
    assert _without_asking("Any recommendations for a cream like Velvra but cheaper? I like it.", "recommend") is None
    # A question that suggests, or asks about something else, isn't one: the quote stays whole.
    for whole in ("Have you tried the Velvra cream? It fixed my patches.",
                  "Anyone having problems with the lid of the Brio kettle?", "I was looking for something better."):
        assert _without_asking(whole, "recommend") == whole


def test_a_pick_shows_no_such_question_and_still_has_two_verified_quotes():
    from engine.answer import unverified_claims

    asking = mention("Velvra cream", "t1", category="skincare",
                     quote="I love the Velvra cream, but I want something richer for winter, any suggestions?")
    unclean = mention("Velvra cream", "t2", category="skincare",
                      quote="Any recommendations for a cream like the Velvra cream but cheaper?")
    plain = [mention("Velvra cream", thread, category="skincare",
                     quote=f"The Velvra cream has kept my skin soft for {years} years.")
             for thread, years in (("t1", 2), ("t2", 3))]
    items = [asking, unclean, *plain]
    bodies = bodies_for(*items)
    answer = write_answer(rank_products(items, "skincare"), bodies, "moisturiser")
    texts = [quote.text for quote in answer.picks[0].quotes]
    assert "I love the Velvra cream" in texts and len(texts) >= 2
    assert not any("?" in text for text in texts)
    assert unverified_claims(answer, bodies) == []
