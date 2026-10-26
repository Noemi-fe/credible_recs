"""Classics (25 Oct 2026, the classics builder; Claude's technical calls, reported to Noemi), from the review in
docs/classics-review-2026-10-25.md: why mainstream classics missed our top 3 in the blind test's and the demo's answers.
Only the review's technical fixes, none of Noemi's rules (the picks bar, the weights, the voice rubric, the reading
window):

1. Facts from the makers' pages, with sources and the day read. Vanicream says on its own pages that all its products are
   free of fragrance (a brand entry, so the brand's moisturiser line can be checked for the must-have, as GreenPan's can
   for PFAS); CeraVe's Moisturizing Cream page says "fragrance-free"; La Roche-Posay's own pages answered only with a
   bot check, so Lipikar AP+M is recorded from two UK stockists' pages (as Cicaplast's entry is) and says so; Misen's
   Carbon Nonstick pan: PFAS only (whether an uncoated pan is "non-stick" is Noemi's call, DECISIONS.md).
2. Names that split one product into two to four groups, pooled with known short names (engine/data/product_aliases.json):
   Steelcase's Leap V2 (its commonest spelling was dropped as ambiguous), Dualit's Classic kettle, Vanicream's tub
   cream, La Roche-Posay's Lipikar balm AP+M, Misen's Carbon Nonstick pan and Lodge's Blacklock collection. Each test
   also shows the product's neighbours staying apart: no two different products may join.

Every comment here is made up; the names are the products' (the library's real spellings, with their counts made up).
"""

from datetime import date

import pytest

from engine import pipeline
from engine.group_products import ProductGroup, ProductMention, group_products
from engine.match_products import known_aliases, product_words
from engine.product_facts import find_brand_facts, find_facts, load_product_facts
from engine.query import parse_query
from engine.tests.test_round2_data import answer as answer_with_lists
from engine.tests.test_round2_data import library as any_library
from engine.tests.test_round3_names import chairs, group_with, library, modules_four, praised, shown

TODAY = date(2026, 10, 25)
FF_REQUEST = "fragrance-free moisturiser for very dry skin in winter"


# --- 1. Facts from the makers' pages ---

def test_vanicreams_own_pages_say_all_its_products_are_fragrance_free_so_its_moisturiser_line_can_be_checked():
    entry = find_brand_facts(["Vanicream", "vanicream"], "skincare", load_product_facts(), ["moisturiser", "moisturisers"],
                             "moisturiser")
    assert entry is not None and entry.facts == {"fragrance_free": True}
    assert entry.checked_on == TODAY and all(source.startswith("https://www.vanicream.com/") for source in entry.sources)
    assert "https://www.vanicream.com/body-products/all-body-products" in entry.sources  # "All Vanicream products are ..."


def test_vanicreams_brand_entry_speaks_for_moisturisers_only_and_for_no_other_brand():
    facts = load_product_facts()
    assert find_brand_facts(["Vanicream"], "skincare", facts, ["cleanser", "cleansers"], "cleanser") is None
    for brand in ("CeraVe", "Cetaphil", "La Roche-Posay", "Aveeno"):
        assert find_brand_facts([brand], "skincare", facts, ["moisturiser", "moisturisers"], "moisturiser") is None, brand


def test_vanicreams_line_passes_the_fragrance_free_must_have_and_cerave_s_still_cannot_be_checked():
    query = parse_query(FF_REQUEST, model=None)
    vanicream = ProductGroup("skincare:vanicream", "Vanicream", "skincare",
                             [ProductMention("t1", "c1", "Vanicream", "skincare", "recommend")], loose=True)
    cerave = ProductGroup("skincare:cerave", "CeraVe", "skincare",
                          [ProductMention("t1", "c2", "CeraVe", "skincare", "recommend")], loose=True)
    result = pipeline.PipelineResult(query)
    kept, _, found = pipeline._suited_to_request([vanicream, cerave], query, load_product_facts(), result)
    assert [g.name for g in kept if g.key == "skincare:vanicream"] == ["Vanicream moisturiser line"]
    assert "skincare:vanicream" not in result.skip_only and "skincare:vanicream" in found
    assert "skincare:cerave" in result.skip_only  # a whole brand can't be checked, still


@pytest.mark.parametrize("written", ["CeraVe Moisturizing Cream", "Cerave moisturizing cream", "CeraVe moisturizing cream"])
def test_cerave_moisturizing_cream_is_fragrance_free_by_its_makers_page(written):
    entry = find_facts(written, "skincare", load_product_facts(), "moisturiser")
    assert entry is not None and entry.product == "CeraVe Moisturizing Cream" and entry.facts == {"fragrance_free": True}
    assert entry.sources == ["https://www.cerave.com/skincare/moisturizers/moisturizing-cream"]
    assert entry.checked_on == TODAY


def test_cerave_s_other_moisturisers_do_not_find_the_moisturizing_creams_entry():
    facts = load_product_facts()
    # (A "CeraVe Baby Moisturizing Cream" does find it: module 4's long-standing rule reads one extra word as the same
    # product, and CeraVe's own page says its baby cream is free of fragrance too.)
    for other in ("CeraVe Daily Moisturizing Lotion", "CeraVe PM Facial Moisturizing Lotion", "CeraVe Healing Ointment",
                  "CeraVe Skin Renewing Night Cream"):
        found = find_facts(other, "skincare", facts, "moisturiser")
        assert found is None or found.product != "CeraVe Moisturizing Cream", other


def test_cerave_s_moisturizing_cream_written_with_its_tub_is_that_cream_but_a_bare_cerave_or_cream_is_not():
    # The tub spellings had stood as a skip of their own (two answers listed "CeraVe moisturizing cream in the blue tub");
    # the entry makes them the cream. A bare "CeraVe", "CeraVe cream" or "CeraVe in the tub" fits its night cream too.
    facts = load_product_facts()
    for written in ("CeraVe moisturizing cream in the tub", "CeraVe moisturizing cream in the blue tub"):
        assert find_facts(written, "skincare", facts, "moisturiser").product == "CeraVe Moisturizing Cream", written
    for written in ("CeraVe", "CeraVe cream", "Cerave cream", "CeraVe in the tub", "CeraVe moisturizer"):
        assert find_facts(written, "skincare", facts, "moisturiser") is None, written


@pytest.mark.parametrize("written", ["La Roche-Posay Lipikar Balm AP+M", "LRP lipikar baume AP+", "La Roche-Posay Lipikar Balm AP+ M",
                                     "LRP triple repair moisturizer"])
def test_lipikar_ap_m_is_fragrance_free_by_two_uk_stockists_pages(written):
    group = group_with(modules_four([(written, 2), ("La Roche-Posay Lipikar Balm AP+M", 1)], "moisturiser", "skincare"),
                       written)
    entry = find_facts(group.name, "skincare", load_product_facts(), "moisturiser")
    assert entry is not None and entry.product == "La Roche-Posay Lipikar Balm AP+M"
    assert entry.facts == {"fragrance_free": True} and entry.checked_on == TODAY
    assert len(entry.sources) == 2 and all("12382711" in source for source in entry.sources)
    assert not any("laroche-posay" in source for source in entry.sources)  # its own pages answered with a bot check


def test_lipikars_lotion_and_cicaplast_do_not_find_the_balms_entry():
    facts = load_product_facts()
    for other in ("La Roche-Posay Lipikar AP+ lotion", "La Roche-Posay Cicaplast Baume B5+"):
        found = find_facts(other, "skincare", facts, "moisturiser")
        assert found is None or found.product != "La Roche-Posay Lipikar Balm AP+M", other


def test_misen_carbon_nonstick_is_pfas_free_by_its_makers_page_and_says_nothing_of_non_stick():
    entry = find_facts("Misen Carbon Nonstick", "kitchen", load_product_facts(), "frying pan")
    assert entry is not None and entry.facts == {"pfas_free": True}  # "non_stick" is Noemi's call (DECISIONS.md)
    assert entry.checked_on == TODAY and all(source.startswith("https://misen.com/") for source in entry.sources)


# --- 2. Names that split one product ---

# The spellings the library holds for the Leap V2 (product names only; the counts are made up).
LEAP = [("Steelcase Leap V2", 8), ("Leap", 9), ("leap", 6), ("Leap V2", 6), ("leap v2", 6), ("Leap v2", 5), ("leap V2", 1),
        ("leapv2", 1), ("leap v2 uph", 1), ("Steel case Leap V2", 1), ("steel case leap v2", 1),
        ("used Steelcase Leap V2", 1), ("Steelcase leap V2", 2)]
OTHER_CHAIRS = [("Herman Miller Aeron", 14), ("Aeron", 20), ("Amia", 5), ("Steelcase Gesture", 8), ("Steelcase", 6),
                ("Steelcase Series 1", 1), ("Herman Miller Mirra 2", 3), ("older steelcase leap", 1)]


def test_every_spelling_of_the_leap_v2_is_one_product_named_in_full():
    groups = modules_four(LEAP + OTHER_CHAIRS, "office chair")
    leap = group_with(groups, "Steelcase Leap V2")
    assert not leap.loose and leap.name == "Steelcase Leap V2"
    for spelling, _ in LEAP:
        assert spelling in leap.names, spelling
    assert len(leap.mentions) == sum(times for _, times in LEAP)


def test_the_leap_never_joins_another_chair_nor_the_steelcase_line():
    groups = modules_four(LEAP + OTHER_CHAIRS, "office chair")
    leap = group_with(groups, "Steelcase Leap V2")
    for other in ("Herman Miller Aeron", "Amia", "Steelcase Gesture", "Steelcase Series 1", "Herman Miller Mirra 2"):
        assert group_with(groups, other) is not leap, other
    steelcase = group_with(groups, "Steelcase")
    assert steelcase is not leap and steelcase.loose  # a bare Steelcase is the brand's line
    # "Older Leap" may be the first Leap, not the V2: left alone.
    assert group_with(groups, "older steelcase leap") is not leap


def test_leap_frog_is_not_a_leap_chair():
    names = LEAP + OTHER_CHAIRS + [("leap frog", 1), ("LeapFrog non-wifi baby monitor", 1)]
    groups = modules_four(names, "office chair")
    assert group_with(groups, "leap frog") is not group_with(groups, "Leap")
    assert "leap frog" not in group_with(groups, "Steelcase Leap V2").names
    # The guard: "Leap Frog" is written out as the toy maker's one word, which two words already say, so it is left
    # as it is and never becomes "steelcase leap v2 frog".
    assert product_words("leap frog", known_aliases()["general"]) == ["leap", "frog"]


def test_the_short_name_leap_is_a_start_of_a_name_only():
    aliases = known_aliases()["general"]
    assert product_words("Leap", aliases) == ["steelcase", "leap", "v2"]
    assert product_words("Leap V2", aliases) == ["steelcase", "leap", "v2"]  # not "... v2 v2"
    assert product_words("Steelcase Leap V2", aliases) == ["steelcase", "leap", "v2"]
    assert product_words("Cosmic Leap", aliases) == ["cosmic", "leap"]


@pytest.mark.parametrize("sibling", ["Leap V1", "Leap Plus", "Steelcase Leap Plus", "Steelcase Leap V1"])
def test_other_steelcase_leap_models_never_join_the_leap_v2(sibling):
    # A short name matches the start of a name, so "Leap" would have written "Leap V1" out as "Steelcase Leap V2 V1".
    groups = modules_four(LEAP + OTHER_CHAIRS + [(sibling, 2)], "office chair")
    assert group_with(groups, sibling) is not group_with(groups, "Steelcase Leap V2")


DUALIT_KETTLE = [("Dualit classic kettle", 7), ("Dualit", 7), ("dualit", 1), ("Dualit kettle", 2), ("Dualit kettles", 1),
                 ("Dualit (big full size)", 1), ("Fellow Stagg EKG", 5), ("Cuisinart CPK-17 PerfecTemp", 6)]


def test_the_dualit_classic_kettle_and_its_brand_name_written_alone_are_one_product():
    groups = modules_four(DUALIT_KETTLE, "electric kettle", "kitchen")
    dualit = group_with(groups, "Dualit classic kettle")
    assert not dualit.loose and len(dualit.mentions) == 19
    assert {"Dualit", "dualit", "Dualit kettle", "Dualit kettles", "Dualit (big full size)"} <= set(dualit.names)
    assert group_with(groups, "Fellow Stagg EKG") is not dualit
    assert group_with(groups, "Cuisinart CPK-17 PerfecTemp") is not dualit


def test_when_the_threads_name_another_dualit_kettle_the_bare_brand_stays_its_line():
    # Two Dualit kettles named: a bare "Dualit" can't be told to mean the Classic, so nothing joins it.
    groups = modules_four(DUALIT_KETTLE + [("Dualit Design Series kettle", 2)], "electric kettle", "kitchen")
    design = group_with(groups, "Dualit Design Series kettle")
    classic = group_with(groups, "Dualit classic kettle")
    assert design is not classic
    assert not classic.loose and "Dualit" not in classic.names and "dualit" not in classic.names
    assert group_with(groups, "Dualit").loose


def typed(names: list[tuple[str, str, int]], product_type: str, category: str = "kitchen") -> list:
    """Module 4's groups for these (name, the type the AI gave it, times written), in a request for `product_type`."""
    mentions, n = [], 0
    for name, given_type, times in names:
        for _ in range(times):
            mentions.append(ProductMention(f"t{n % 3}", f"c{n}", name, category, "recommend", given_type))
            n += 1
    return group_products(mentions, product_type=product_type)


def test_the_classic_kettle_is_not_the_classic_toaster():
    # As the extraction types them: the toaster mentions are a toaster's, whatever the request.
    names = [("Dualit Classic Kettle", "electric kettle", 3), ("Dualit kettle", "electric kettle", 1),
             ("Dualit Classic toaster", "toaster", 3), ("Dualit toaster", "toaster", 2)]
    kettles = typed(names, "electric kettle")
    assert group_with(kettles, "Dualit kettle") is group_with(kettles, "Dualit Classic Kettle")
    assert "Dualit Classic toaster" not in group_with(kettles, "Dualit Classic Kettle").names
    toasters = typed(names + [("Dualit Architect toaster", "toaster", 1)], "toaster")
    assert "Dualit kettle" not in group_with(toasters, "Dualit Classic toaster").names
    assert group_with(toasters, "Dualit Architect toaster") is not group_with(toasters, "Dualit Classic toaster")


# The spellings of the Lipikar balm (product names only), and the neighbours that are other products.
LIPIKAR = [("La Roche-Posay Lipikar Balm AP+ M", 5), ("La Roche-Posay Lipikar Balm AP+", 2), ("LRP lipikar baume AP+", 1),
           ("LRP Lipikar Baume", 1), ("LRP Lipikar AP+M", 1), ("LRP lipikar ap+m", 1), ("La Roche Posay Lipikar Balm", 1),
           ("LRP lipikar balm", 1), ("La Roche-Posay Lipikar AP+M Triple Repair Moisturizer", 1),
           ("LRP triple repair moisturizer", 1), ("Laroche Posay Triple Repair", 1), ("La Roche Posay lipikar face and body", 3),
           ("La Roche Posay AP+M Triple Repair Body Moisturizing Cream", 1)]
LIPIKAR_NEIGHBOURS = [("La Roche-Posay Lipikar AP+ lotion", 1), ("La Roche Posay Lipikar Eczema Soothing Relief Cream", 1),
                      ("La Roche Posay Cicaplast Baume", 2), ("La Roche-Posay Toleriane Double Repair Face Moisturizer", 3),
                      ("CeraVe Moisturizing Cream", 4), ("La Roche Posay", 2)]


def test_every_spelling_of_the_lipikar_balm_is_one_product_named_in_full():
    groups = modules_four(LIPIKAR + LIPIKAR_NEIGHBOURS, "moisturiser", "skincare")
    balm = group_with(groups, "La Roche-Posay Lipikar Balm AP+ M")
    assert not balm.loose
    for spelling, _ in LIPIKAR:
        assert spelling in balm.names, spelling
    assert len(balm.mentions) == sum(times for _, times in LIPIKAR)


def test_the_lipikar_balm_never_joins_another_la_roche_posay_product():
    groups = modules_four(LIPIKAR + LIPIKAR_NEIGHBOURS, "moisturiser", "skincare")
    balm = group_with(groups, "La Roche-Posay Lipikar Balm AP+ M")
    for other, _ in LIPIKAR_NEIGHBOURS:
        assert group_with(groups, other) is not balm, other


@pytest.mark.parametrize("sibling", ["LRP Lipikar Baume Light", "Lipikar Baume Light AP+M", "La Roche-Posay Lipikar Balm Light",
                                     "La Roche-Posay Lipikar Baume Light AP+M"])
def test_the_lighter_lipikar_balm_never_joins_the_original(sibling):
    groups = modules_four(LIPIKAR + LIPIKAR_NEIGHBOURS + [(sibling, 2)], "moisturiser", "skincare")
    assert group_with(groups, sibling) is not group_with(groups, "La Roche-Posay Lipikar Balm AP+ M")


VANICREAM = [("Vanicream in the tub", 1), ("Vanicream (in the tub)", 2), ("vanicream in the tub", 2), ("Vanicream tub", 1),
             ("tub vanicream", 1), ("Vanicream in the big tub", 1), ("vanicream in the tub with the blue lid", 1),
             ("Vanicream Moisturizing Cream", 3), ("Vanicream Moisturizing Skin Cream", 2), ("vanicream moisturizing cream", 2)]
VANICREAM_NEIGHBOURS = [("Vanicream", 9), ("Vanicream lotion", 2), ("Vanicream Moisturizing Lotion", 1),
                        ("Vanicream daily facial moisturizer", 3), ("Vanicream Enhanced Moisturizer", 1),
                        ("Vanicream hydrocortisone cream", 1), ("Vanicream Gentle Cleanser", 1), ("CeraVe in the tub", 2),
                        ("Cetaphil in the tub", 2)]


def test_vanicream_s_tub_cream_written_six_ways_is_one_product():
    groups = modules_four(VANICREAM + VANICREAM_NEIGHBOURS, "moisturiser", "skincare")
    cream = group_with(groups, "Vanicream Moisturizing Cream")
    assert not cream.loose
    for spelling, _ in VANICREAM:
        assert spelling in cream.names, spelling
    assert len(cream.mentions) == sum(times for _, times in VANICREAM)


def test_vanicream_s_tub_cream_never_joins_its_lotion_its_other_moisturisers_nor_another_brands_tub():
    groups = modules_four(VANICREAM + VANICREAM_NEIGHBOURS, "moisturiser", "skincare")
    cream = group_with(groups, "Vanicream Moisturizing Cream")
    for other, _ in VANICREAM_NEIGHBOURS:
        assert group_with(groups, other) is not cream, other
    assert group_with(groups, "Vanicream").loose  # the bare brand is the brand's line
    assert group_with(groups, "CeraVe in the tub") is not group_with(groups, "Cetaphil in the tub")


MISEN = [("Misen Carbon Nonstick", 5), ("Misen carbon nonstick", 1), ("Misen nitrogenated carbon steel pan", 1),
         ("Nitrited Misen", 1), ("Misen nonstick pan", 1), ("Misen non stick", 1)]
MISEN_NEIGHBOURS = [("Misen", 6), ("Misen saucier", 2), ("Misen stainless set", 1), ("Misen All-Purpose pan", 1),
                    ("Misen carbon steel", 1), ("Misen 8” carbon steel pan", 1), ("All-Clad D3", 3)]


def test_misen_s_carbon_nonstick_pan_written_four_ways_is_one_product():
    groups = modules_four(MISEN + MISEN_NEIGHBOURS, "frying pan", "kitchen")
    pan = group_with(groups, "Misen Carbon Nonstick")
    assert not pan.loose
    for spelling, _ in MISEN:
        assert spelling in pan.names, spelling


def test_misen_s_carbon_nonstick_pan_never_joins_its_other_pans_or_the_brand():
    groups = modules_four(MISEN + MISEN_NEIGHBOURS, "frying pan", "kitchen")
    pan = group_with(groups, "Misen Carbon Nonstick")
    for other in ("Misen saucier", "Misen stainless set", "Misen All-Purpose pan", "All-Clad D3"):
        assert group_with(groups, other) is not pan, other
    assert group_with(groups, "Misen").loose and group_with(groups, "Misen") is not pan


BLACKLOCK = [("Lodge Blacklock", 1), ("lodge blacklock collection", 1), ("Lodge Blacklock 10\"", 1), ("Blacklock 12\" skillet", 1)]


def test_lodge_s_blacklock_collection_is_named_with_its_maker_and_its_sizes_stay_apart():
    groups = modules_four(BLACKLOCK + [("Lodge cast iron skillet", 8), ("Lodge", 6)], "cast iron skillet", "kitchen")
    collection = group_with(groups, "Lodge Blacklock")
    assert group_with(groups, "lodge blacklock collection") is collection
    ten, twelve = group_with(groups, "Lodge Blacklock 10\""), group_with(groups, "Blacklock 12\" skillet")
    assert ten is not twelve and ten is not collection and twelve is not collection  # two sizes are two products
    assert "Lodge" not in collection.names
    assert product_words("Blacklock 12\" skillet", known_aliases()["kitchen"])[:2] == ["lodge", "blacklock"]


# --- End to end: the committed lists, a made-up library ---

def test_a_chair_answer_shows_the_leap_v2_once_under_its_full_name(tmp_path):
    root = library(tmp_path, "office chair", [
        ("1ch0001", "general", "Best office chair for back pain?", [
            praised("a1", "Leap"), praised("a2", "Leap V2"), praised("a3", "Steelcase Leap V2"), praised("a4", "leap v2"),
            praised("a5", "Aeron"), praised("a6", "Herman Miller Aeron"), praised("a7", "Amia"), praised("a8", "Amia")]),
        ("1ch0002", "general", "Which office chair is worth the money?", [
            praised("b1", "Leap"), praised("b2", "Leap v2"), praised("b3", "leap v2 uph"), praised("b4", "Steelcase Leap V2"),
            praised("b5", "Aeron"), praised("b6", "Herman Miller Aeron"), praised("b7", "Amia"), praised("b8", "Amia")]),
    ])
    names = shown(answer_with_lists("office chair for back pain", root))
    assert [n for n in names if "leap" in n.lower()] == ["Steelcase Leap V2"], names


def test_a_kettle_answer_shows_the_dualit_classic_kettle_once_and_no_dualit_line(tmp_path):
    root = library(tmp_path, "electric kettle", [
        ("1ke0001", "kitchen", "Electric kettle that lasts 10+ years?", [
            praised("a1", "Dualit", 12), praised("a2", "Dualit kettle", 10), praised("a3", "Dualit classic kettle", 15),
            praised("a4", "Fellow Stagg EKG", 5), praised("a5", "Fellow Stagg EKG", 6), praised("a6", "Fellow Stagg EKG", 4)]),
        ("1ke0002", "kitchen", "A kettle that will last decades", [
            praised("b1", "Dualit", 14), praised("b2", "Dualit kettles", 11), praised("b3", "Dualit classic kettle", 13),
            praised("b4", "Fellow Stagg EKG", 5), praised("b5", "Fellow Stagg EKG", 7), praised("b6", "Fellow Stagg EKG", 3)]),
    ])
    names = shown(answer_with_lists("electric kettle that lasts 10+ years", root))
    assert [n for n in names if "dualit" in n.lower()] == ["Dualit Classic Kettle"], names


def moisturiser_threads(tmp_path, with_range: bool):
    """Three threads. `with_range`: Vanicream's lotion and daily facial moisturizer are named too, so a bare "Vanicream" fits
    more than one of its products; without them it fits the cream alone."""
    def comment(cid, product, years=3):
        return (cid, product, f"I've used {product} for {years} years and I would buy it again.")

    range_ = [comment("r1", "Vanicream lotion"), comment("r2", "Vanicream daily facial moisturizer")] if with_range else []
    return any_library(tmp_path, [
        ("1mo0001", "SkincareAddiction", "skincare", "Fragrance-free moisturiser for very dry skin?", [
            comment("a1", "Vanicream"), comment("a2", "Vanicream"), comment("a3", "Vanicream in the tub"),
            comment("a4", "Vanicream Moisturizing Skin Cream"), comment("a5", "CeraVe"), comment("a6", "CeraVe"),
            comment("a7", "La Roche-Posay Lipikar Balm AP+"), comment("a8", "LRP lipikar baume AP+")] + range_),
        ("1mo0002", "SkincareAddiction", "skincare", "Best fragrance-free moisturiser for winter", [
            comment("b1", "Vanicream"), comment("b2", "Vanicream"), comment("b3", "vanicream in the tub"),
            comment("b4", "Vanicream Moisturizing Cream"), comment("b5", "CeraVe"), comment("b6", "CeraVe"),
            comment("b7", "La Roche Posay Lipikar Balm"), comment("b8", "LRP Lipikar AP+M"),
            comment("b9", "CeraVe Moisturizing Cream"), comment("b10", "CeraVe Moisturizing Cream")]),
        ("1mo0003", "SkincareAddiction", "skincare", "Rich fragrance-free cream for dry winter skin", [
            comment("c1", "Vanicream"), comment("c2", "Vanicream"), comment("c3", "Vanicream tub"),
            comment("c4", "CeraVe Moisturizing Cream"), comment("c5", "CeraVe"), comment("c6", "CeraVe"),
            comment("c7", "La Roche-Posay Lipikar AP+M Triple Repair Moisturizer")]),
    ])


def test_a_fragrance_free_moisturiser_answer_shows_vanicreams_tub_cream_once_and_lipikar_once(tmp_path):
    # Only the cream is named: a bare "Vanicream" is that cream, and the tub is too. Its facts entry confirms the must-have.
    result = answer_with_lists(FF_REQUEST, moisturiser_threads(tmp_path, with_range=False))
    names = shown(result)
    assert [n for n in names if "vanicream" in n.lower()] == ["Vanicream Moisturizing Cream"], names
    assert "Vanicream Moisturizing Cream" in [pick.name for pick in result.answer.picks]
    assert [n for n in names if "lipikar" in n.lower()] == ["La Roche-Posay Lipikar Balm AP+M"], names
    # Their facts confirm the must-have: no "we couldn't confirm" for Lipikar, nor for CeraVe's Moisturizing Cream.
    assert not [key for key in result.unconfirmed if "lipikar" in key or "cerave moisturizing cream" in key]


def test_with_vanicreams_range_named_its_brand_line_is_checked_by_the_makers_word_and_can_be_a_pick(tmp_path):
    result = answer_with_lists(FF_REQUEST, moisturiser_threads(tmp_path, with_range=True))
    picks = [pick.name for pick in result.answer.picks]
    assert "Vanicream moisturiser line" in picks, shown(result)
    assert not [n for n in shown(result) if "tub" in n.lower()]  # the tub cream is part of the line, not a second item
    # A bare CeraVe next to its Moisturizing Cream and nothing else: that cream. The line itself is never listed twice.
    assert len([n for n in shown(result) if "cerave" in n.lower() and "moisturizing cream" in n.lower()]) <= 1
