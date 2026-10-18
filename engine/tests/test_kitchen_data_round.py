"""Kitchen data round of 17 Oct 2026 (the ws-data-kitchen builder): the committed lists' kitchen entries this round
added or changed, checked against what the answers need from them.

1. Noemi's decision 8 of 16 Oct 2026: Circulon's and Ballarini's price-list and facts names ("Circulon pans",
   "Ballarini non-stick pans") become brand lines, so a PFAS-free frying-pan answer keeps only the pans whose facts
   confirm it: both makers' UK ranges mix ceramic pans made without PFAS with PTFE non-stick ones, and a whole brand
   can't be checked (decided 10 Oct 2026).
2. PFAS research (her rule of 11 Oct 2026: a coating its maker names as PTFE, or says contains PFAS, answers
   pfas_free: false): Le Creuset's Toughened Non-Stick is a PFAS coating by its maker's own page; Our Place makes its
   cookware without PFAS.
4. The pans the brand-only-line rule's sweep surfaced (the coordinator's round-2 list, 18 Oct 2026), decided per named
   model: Made In's stainless pans aren't non-stick and its non-stick ones are PTFE (its own California disclosure);
   Cuisinart's French Classic non-stick skillets are PTFE (its own chemical disclosure); writers' Member's Mark
   non-stick pans reach the PTFE facts of Sam's Club's restaurant pans; OXO non-stick pans whose writers name no model
   keep an unknown PFAS fact.

Most tests read the committed lists (data/); the one answering a request uses a made-up library in a temporary folder
with the committed lists, so it shows what the lists change in an answer.
"""

import json
from datetime import date

from engine.brand_lines import find_brand_line, load_brand_lines
from engine.pipeline import answer_request
from engine.prices import find_availability, find_price, load_prices
from engine.product_facts import NotSuited, find_brand_facts, find_facts, load_product_facts
from engine.product_pages import find_page, load_product_pages
from engine.tests.test_pipeline import praise, write_library

TODAY = date(2026, 10, 17)
PAN_WORDS = ("frying pan", "frying pans", "pan", "pans")  # the request's type words, as the pipeline passes them


# --- 1. Circulon and Ballarini are brand lines (Noemi's decision 8 of 16 Oct 2026) ---

def test_circulon_and_ballarini_have_brand_lines_entries_with_a_range_page_and_a_from_price():
    lines = load_brand_lines()
    for written, brand, site in [("Circulon", "Circulon", "circulon.uk.com"), ("Circulon pans", "Circulon", "circulon.uk.com"),
                                 ("Ballarini", "Ballarini", "zwilling.com"), ("Ballarini pans", "Ballarini", "zwilling.com")]:
        line = find_brand_line([written], "kitchen", "frying pan", lines)
        assert line is not None and line.brand == brand and line.sells, written
        assert line.range_page and site in line.range_page, written
        assert line.from_price and line.from_price_shop and line.from_price_url and line.from_price_checked_on, written


def test_their_old_product_names_are_gone_from_the_price_and_facts_lists():
    # A name in either list was treated as one product ("Circulon pans" was a pick of b10 with a PFAS note); a brand
    # line has no single price (its from price is in the brand-lines list) and no facts entry.
    prices, facts = load_prices(), load_product_facts()
    for old in ("Circulon pans", "Ballarini non-stick pans"):
        assert find_price(old, "kitchen", prices, product_type="frying pan") is None, old
        assert find_availability(old, "kitchen", prices, product_type="frying pan") is None, old
        assert find_facts(old, "kitchen", facts, "frying pan") is None, old


def test_no_facts_entry_speaks_for_either_whole_brand():
    # Both UK ranges mix ceramic pans made without PFAS (Circulon Halo; Ballarini Bologna, Ledro, Salina) with PTFE
    # non-stick ones, so neither brand's line can be confirmed PFAS-free: under a must-have it is left out, as a whole
    # brand can't be checked (decision 8: "keeps only GreenPan until more PFAS-free pans are researched").
    facts = load_product_facts()
    for names in (["Circulon", "Circulon pans", "Circulon pan"], ["Ballarini", "Ballarini pans"]):
        assert find_brand_facts(names, "kitchen", facts, PAN_WORDS, "frying pan") is None, names


def test_their_pages_are_listed_under_the_lines_names():
    pages = load_product_pages()
    for shown, site in (("Circulon frying pan line", "circulon.uk.com"), ("Ballarini frying pan line", "zwilling.com")):
        page = find_page([shown], "kitchen", "frying pan", pages)
        assert page is not None and site in page.page, shown


# --- 2. PFAS research ---

def test_le_creusets_toughened_non_stick_contains_pfas_by_its_makers_page():
    facts = load_product_facts()
    for written in ('Le Creuset "toughened non-stick" pan', "Le Creuset “toughened” non-stick", "LeCreuset non-stick"):
        entry = find_facts(written, "kitchen", facts, "frying pan")
        assert entry is not None, written
        assert entry.facts.get("pfas_free") is False and entry.facts.get("non_stick") is True, written
        assert any("lecreuset" in source for source in entry.sources), written


def test_our_places_pans_are_made_without_pfas():
    facts = load_product_facts()
    for written, product in (("Always Pan", "Our Place Always Pan"), ("OurPlace Always Pan", "Our Place Always Pan"),
                             ("titanium always pan pro", "Our Place Titanium Always Pan Pro")):
        entry = find_facts(written, "kitchen", facts, "frying pan")
        assert entry is not None and entry.product == product, written
        assert entry.facts.get("pfas_free") is True and entry.facts.get("non_stick") is True, written
        assert any("fromourplace" in source for source in entry.sources), written


# --- What the lists change in an answer ---

def pfas_library(tmp_path):
    """Two frying-pan threads in which GreenPan, Circulon, Ballarini and Le Creuset's toughened non-stick pans are each
    praised by three writers across both threads (made-up comments), as in b10's threads: writers name Circulon and
    Ballarini by brand only ("Circulon pans", "Ballarini"), never a model."""
    return write_library(tmp_path, {
        "1pfas01": ("Non-stick frying pan without PFAS?", "Replacing my old ones.", [
            praise("g1a", "GreenPan", 4), praise("g1b", "GreenPan", 5),
            praise("c1a", "Circulon pans", 6), praise("c1b", "Circulon", 7),
            praise("b1a", "Ballarini pans", 5), praise("b1b", "Ballarini", 6),
            praise("l1a", "Le Creuset toughened non-stick pan", 3), praise("l1b", "Le Creuset toughened non-stick pan", 4),
        ]),
        "1pfas02": ("Which non-stick pan lasts?", "Ten years, ideally.", [
            praise("g2a", "GreenPan", 6), praise("c2a", "Circulon pans", 8), praise("b2a", "Ballarini pans", 9),
            praise("l2a", "Le Creuset toughened non-stick pan", 5),
        ]),
    }, community="BuyItForLife")


def pfas_answer(tmp_path):
    return answer_request("non-stick frying pan without PFAS that lasts", library_dir=pfas_library(tmp_path),
                          prices=load_prices(), product_facts=load_product_facts(), brand_lines=load_brand_lines(),
                          product_pages=load_product_pages(), today=TODAY, more_threads=None)


def shown_names(result) -> list[str]:
    return [pick.name for pick in result.answer.picks] + [item.name for item in result.answer.worth_a_look]


def test_le_creusets_toughened_non_stick_leaves_a_pfas_free_answer_and_greenpan_stays(tmp_path):
    # Le Creuset's toughened non-stick was under Also worth a look in "non stick pan without teflon that lasts" (16 Oct
    # sweep): its maker's own page says it contains PFAS, so it is left out, with the reason.
    result = pfas_answer(tmp_path)
    assert result.answer.picks[0].name.startswith("GreenPan")
    assert not any("Le Creuset" in name for name in shown_names(result))
    assert NotSuited("Le Creuset toughened non-stick pan", "it isn't PFAS-free") in result.left_out_not_suited


def test_circulon_and_ballarini_are_left_out_of_a_pfas_free_answer_as_whole_brands(tmp_path):
    # Needs the pipeline's rule too (17 Oct 2026, engine.pipeline._brand_only_lines; engine/tests/
    # test_brand_only_lines.py): module 4 keeps a brand none of whose models is named as one product.
    result = pfas_answer(tmp_path)
    assert not any(word in name for name in shown_names(result) for word in ("Circulon", "Ballarini"))
    left_out = {item.name: item.reason for item in result.left_out_not_suited}
    assert left_out["Circulon frying pan line"] == left_out["Ballarini frying pan line"] == (
        "a whole brand can't be checked for PFAS or a non-stick coating")


# --- 3. Prices and availability ---

def test_grinders_and_a_kettle_their_makers_stopped_selling_are_discontinued_not_sold_abroad():
    # They were marked "not sold in the UK" (so shown with that note); their makers no longer sell them, so answers leave
    # them out and name them, as for any discontinued model (Noemi's decision 1 of 15 Oct 2026, late afternoon).
    prices = load_prices()
    for name in ("1ZPresso K Plus", "1Zpresso K-Plus", "1zpresso X-Pro", "Timemore C2 Max", "Fellow Corvo EKG"):
        entry = find_availability(name, "kitchen", prices)
        assert entry is not None and entry.available is False and not entry.not_in_uk, name
        assert entry.note.startswith("discontinued:") and entry.checked_on == TODAY, name


def test_b09s_jx_pro_has_its_uk_shops_price():
    # A UK shop lists it, sold out for now: out of stock counts as sold (the price list's convention), with its price.
    prices = load_prices()
    price = find_price("1Zpresso JX-Pro", "kitchen", prices, currency="GBP")
    assert (price.price, price.currency, price.shop) == (140.83, "GBP", "The English Coffee Company")
    assert find_availability("1Zpresso JX-Pro", "kitchen", prices).available is True


def test_lines_picked_under_a_budget_have_a_uk_from_price():
    lines = load_brand_lines()
    for brand, product_type, amount in (("Mercer", "chef knife", 15.86), ("Le Creuset", "teapot", 65.0)):
        line = find_brand_line([brand], "kitchen", product_type, lines)
        assert line is not None and line.from_price == amount and line.from_price_checked_on == TODAY, brand


# --- 4. The pans the brand-only-line rule's sweep surfaced (the coordinator's round-2 list, 18 Oct 2026) ---

ROUND2 = date(2026, 10, 18)


def test_made_in_stainless_pans_are_uncoated_and_its_non_stick_pans_contain_ptfe():
    # Made In's California (AB 1200) disclosure lists PTFE, FEP and PFA for its non-stick pans only; its Stainless Clad
    # frying pan is 5-ply metal with no coating, so it isn't non-stick (a hard clash for a non-stick request).
    facts = load_product_facts()
    stainless = find_facts("Made In stainless pans", "kitchen", facts, "frying pan")
    assert stainless is not None and stainless.product == "Made In Stainless Clad Frying Pan"
    assert stainless.facts.get("non_stick") is False and stainless.facts.get("pfas_free") is True
    non_stick = find_facts("Made In non stick frying pan", "kitchen", facts, "frying pan")
    assert non_stick is not None and non_stick.product == "Made In Non Stick Frying Pan"
    assert non_stick.facts.get("non_stick") is True and non_stick.facts.get("pfas_free") is False
    for entry in (stainless, non_stick):
        assert entry.checked_on == ROUND2 and any("madeincookware.com" in source for source in entry.sources)
    # A writer's bare "Made In" fits both, so it names neither (name levels, 14 Oct 2026); before, it took the facts of
    # Tefal's pan "made in France".
    assert find_facts("Made In", "kitchen", facts, "frying pan") is None


def test_cuisinarts_french_classic_non_stick_skillets_contain_ptfe_by_its_makers_disclosure():
    # Cuisinart's own chemical disclosure lists PTFE, FEP and PFA for its French Classic Tri-Ply non-stick frying pans
    # (FCT22-24NS and FCT22-30HNS; FEP and PFA for FCT22-20NS), all PFAS; and for its Advantage non-stick set (55-11BK).
    facts = load_product_facts()
    for written, line in (("Cuisinart french non stick skillets", "French Classic"),
                          ("Cuisinart Advantage nonstick skillet", "Advantage")):
        entry = find_facts(written, "kitchen", facts, "frying pan")
        assert entry is not None and line in entry.product, written
        assert entry.facts.get("pfas_free") is False and entry.facts.get("non_stick") is True, written
        assert entry.checked_on == ROUND2 and any("cuisinart.com" in source for source in entry.sources), written
    # A writer's Cuisinart non-stick pan with no line named isn't either of them (Cuisinart's range has others), so its
    # warnings are never shown under the French Classic's name (a Skip these item in "a frying pan for an induction hob"
    # had been, with one entry only).
    for written in ("Cuisinart", "Cuisinart non-stick pan", "Cuisinart non sticks", "Cuisinart non stick",
                    "non-stick Cuisinart skillet", "cuisinart non stick pans"):
        assert find_facts(written, "kitchen", facts, "frying pan") is None, written


def test_writers_member_s_mark_and_sam_s_club_non_stick_pans_find_ptfe_facts_and_the_price_entry():
    # Sam's Club's own pages for the Member's Mark aluminium non-stick restaurant fry pans list PTFE, PFA and FEP.
    # Writers name them after the brand ("Members Mark commercial grade non stick pans") or the shop ("sams club
    # restaurant quality non stick pans"); each reaches facts saying so, and the price entry.
    facts, prices = load_product_facts(), load_prices()
    for written in ("Members Mark commercial grade non stick pans", "members mark from Sam’s club",
                    "sams club restaurant quality non stick pans"):
        entry = find_facts(written, "kitchen", facts, "frying pan")
        assert entry is not None and entry.facts.get("pfas_free") is False and entry.facts.get("non_stick") is True, written
        assert any("samsclub.com" in source for source in entry.sources), written
        price = find_availability(written, "kitchen", prices, "frying pan")
        assert price is not None and price.product == "Member's Mark Aluminum Nonstick Restaurant Fry Pan", written


def typed_as(library, product_type: str):
    """The made-up library's mentions typed as the extraction types them (instructions v6 on): writers' "Cuisinart
    french non stick skillets" are frying pans, though "skillet" alone names a cast iron one."""
    for path in (library / "extracted").glob("*.json"):
        extraction = json.loads(path.read_text(encoding="utf-8"))
        for mention in extraction["mentions"]:
            mention["product_type"] = product_type
        path.write_text(json.dumps(extraction), encoding="utf-8")
    return library


def round2_pans_library(tmp_path):
    """Two frying-pan threads where GreenPan and the three pans the rule's sweep surfaced are each praised by three
    writers across both threads (made-up comments), named as b10's writers name them."""
    return typed_as(write_library(tmp_path, {
        "1pfas03": ("Best non-stick pan without PFAS?", "Mine is peeling.", [
            praise("g3a", "GreenPan", 4), praise("g3b", "GreenPan", 5),
            praise("m3a", "Made In stainless pans", 6), praise("m3b", "Made In stainless pans", 7),
            praise("s3a", "Members Mark commercial grade non stick pans", 5),
            praise("s3b", "Members Mark commercial grade non stick pans", 6),
            praise("f3a", "Cuisinart french non stick skillets", 3), praise("f3b", "Cuisinart french non stick skillets", 4),
        ]),
        "1pfas04": ("Which non-stick pan lasts?", "Ten years, ideally.", [
            praise("g4a", "GreenPan", 6), praise("m4a", "Made In stainless pans", 8),
            praise("s4a", "Members Mark commercial grade non stick pans", 9),
            praise("f4a", "Cuisinart french non stick skillets", 5),
        ]),
    }, community="BuyItForLife"), "frying pan")


def test_the_three_surfaced_pans_leave_a_pfas_free_non_stick_answer_with_their_reasons(tmp_path):
    # They were under Also worth a look in the PFAS-free answers, each with "we couldn't confirm it's PFAS-free or that
    # it's non-stick" (sweep-ws-data-kitchen-rule-on-2.jsonl, 17 Oct 2026).
    result = answer_request("non-stick frying pan without PFAS that lasts", library_dir=round2_pans_library(tmp_path),
                            prices=load_prices(), product_facts=load_product_facts(), brand_lines=load_brand_lines(),
                            product_pages=load_product_pages(), today=ROUND2, more_threads=None)
    assert result.answer.picks[0].name.startswith("GreenPan")
    assert not any(word in name for name in shown_names(result) for word in ("Made In", "Members Mark", "Cuisinart"))
    left_out = {item.name: item.reason for item in result.left_out_not_suited}
    assert left_out["Made In stainless pans"] == "it isn't non-stick"
    assert left_out["Members Mark commercial grade non stick pans"] == "it isn't PFAS-free"
    assert left_out["Cuisinart french non stick skillets"] == "it isn't PFAS-free"


def test_oxo_non_stick_pans_whose_writers_name_no_model_are_never_shown_as_confirmed_pfas_free(tmp_path):
    # Decided per named model, not per brand (the coordinator's round-2 list): OXO's non-stick pans have had PTFE and
    # ceramic coatings, and writers' "OXO non-stick" names no model, so its PFAS fact stays unknown and an answer that
    # asks for PFAS-free says so. One writer naming the Ceramic Professional (made without PFAS, by OXO's California
    # disclosure) doesn't make the others' pans that model: module 4 names their group after it, so a facts entry under
    # that model's name would mark them all PFAS-free (tried on 18 Oct 2026; left for the integrator).
    library = typed_as(write_library(tmp_path, {
        "1oxo001": ("Non-stick pan that lasts, no PFAS?", "Peeling again.", [
            praise("o1a", "OXO non-stick", 3), praise("o1b", "OXO non-stick pan", 4),
            praise("o1c", "Oxo ceramic professional non-stick", 2), praise("g5a", "GreenPan", 4),
            praise("g5b", "GreenPan", 5),
        ]),
        "1oxo002": ("Which non-stick pan lasts?", "Ten years, ideally.", [
            praise("o2a", "oxo non stick pans", 5), praise("g6a", "GreenPan", 6),
        ]),
    }, community="BuyItForLife"), "frying pan")
    result = answer_request("non-stick frying pan without PFAS that lasts", library_dir=library, prices=load_prices(),
                            product_facts=load_product_facts(), brand_lines=load_brand_lines(),
                            product_pages=load_product_pages(), today=ROUND2, more_threads=None)
    shown = list(result.answer.picks) + list(result.answer.worth_a_look)
    assert not any("ceramic professional" in item.name.casefold() for item in shown)
    for item in shown:
        if "oxo" in item.name.casefold():
            assert any("couldn't confirm it's PFAS-free" in caution for caution in (item.cautions or [])), item.name


def test_chefmans_kettle_line_picked_under_a_budget_has_a_uk_from_price():
    # "1.7l kettle under £40" picks the Chefman electric kettle line, shown unpriced (the 17 Oct baseline). Amazon UK sells
    # (and ships) Chefman's 1.8 L glass kettle, its UK model (220-240 V), so the line has a from price within the budget.
    line = find_brand_line(["Chefman"], "kitchen", "electric kettle", load_brand_lines())
    assert line is not None and line.sells and line.range_page and "chefman.com" in line.range_page
    assert (line.from_price, line.from_price_shop, line.from_price_checked_on) == (20.97, "Amazon UK", ROUND2)
    assert line.from_price_url in line.sources


def test_the_new_saucepan_and_paring_picks_under_a_budget_have_uk_prices():
    # The round's saucepan and paring knife threads give "best paring knife under £30" and "2qt stainless steel
    # saucepan, dishwasher safe, up to 80 usd" their first picks, unpriced: each now has a UK price with shop and day.
    lines, prices = load_brand_lines(), load_prices()
    for names, product_type, amount, shop in ((["Victorinox"], "paring knife", 5.5, "Victorinox"),
                                              (["All-Clad", "All Clad", "all clad"], "saucepan", 113.27, "Amazon UK")):
        for name in names:
            line = find_brand_line([name], "kitchen", product_type, lines)
            assert line is not None and line.sells and line.range_page, name
            assert (line.from_price, line.from_price_shop, line.from_price_checked_on) == (amount, shop, ROUND2), name
    for written, product_type, amount, shop in (("wusthof classic paring knife", "paring knife", 82.0, "Wüsthof UK"),
                                                ("Wusthof classic Pairing knife", "paring knife", 82.0, "Wüsthof UK"),
                                                ("DeMeyere Industry 5 3.5qt conical sauteuse", "saucepan", 269.0, "Zwilling UK")):
        price = find_price(written, "kitchen", prices, currency="GBP", product_type=product_type)
        assert price is not None and (price.price, price.shop, price.checked_on) == (amount, shop, ROUND2), written
        assert find_availability(written, "kitchen", prices, product_type).available is True, written


def test_made_ins_saucepan_line_has_its_uk_range_page_and_from_price():
    # "a good saucepan" picks the Made In saucepan line (the round's saucepan threads); Made In has a UK store.
    for name in ("Made In", "MadeIn"):
        line = find_brand_line([name], "kitchen", "saucepan", load_brand_lines())
        assert line is not None and line.sells and "madeincookware.co.uk" in line.range_page, name
        assert (line.from_price, line.from_price_shop, line.from_price_checked_on) == (119.0, "Made In", ROUND2), name


def test_the_new_saucepan_and_paring_picks_link_their_makers_own_pages():
    # Item 4: product pages for the kitchen picks the round's threads add, each read for its own name (engine.buyable's
    # findings format; engine.maker_pages found neither: a writer's "Pairing" and Demeyere's pages on Zwilling's site).
    pages = load_product_pages()
    for shown, product_type, site in (("Wüsthof classic Pairing knife", "paring knife", "wusthof.co.uk"),
                                      ("DeMeyere Industry 5 3.5qt conical sauteuse", "saucepan", "zwilling.com/uk")):
        page = find_page([shown], "kitchen", product_type, pages)
        assert page is not None and site in page.page, shown


# --- 5. Lines the round's new threads make (18 Oct 2026) ---

def test_the_barista_express_line_has_a_uk_from_price_so_a_budget_under_it_leaves_the_line_out():
    # The round's bean-to-cup threads also name the Barista Express Impress, so module 4 reads writers' bare "Barista
    # Express" as Sage's Barista Express range (a line) rather than the £629.95 product: shown unpriced, it had joined
    # "espresso machine for a beginner under £500". Sage UK's own pages give the range's from price.
    lines = load_brand_lines()
    for written in ("Barista Express", "Breville Barista Express", "Sage Barista Express", "barista express espresso machine"):
        line = find_brand_line([written], "kitchen", "espresso machine", lines)
        assert line is not None and line.brand == "Sage Barista Express" and line.sells, written
        assert "sageappliances.com/en-gb" in line.range_page, written
        assert (line.from_price, line.from_price_shop, line.from_price_checked_on) == (629.95, "Sage", ROUND2), written
        assert line.from_price_url in line.sources, written
    # Sage's own entry for its other espresso machines, if one is added, isn't this line's.
    assert find_brand_line(["Sage"], "kitchen", "espresso machine", lines) is None or \
        find_brand_line(["Sage"], "kitchen", "espresso machine", lines).brand != "Sage Barista Express"


def test_writers_stagg_kettles_are_fellows_stagg_line_with_a_uk_from_price_for_electric_kettles_only():
    # The round's quiet-kettle threads name several Stagg kettles (EKG, EKG Pro), so module 4 ranks writers' bare
    # "Stagg" as a line ("Stagg electric kettle line", no entry, no price). Fellow makes them; it has no UK store, and
    # a big UK kitchen shop sells the Stagg EKG Pro with a UK plug.
    lines = load_brand_lines()
    for written in ("Stagg", "Stagg kettle", "Fellow Stagg", "Fellow Stagg electric kettle"):
        line = find_brand_line([written], "kitchen", "electric kettle", lines)
        assert line is not None and line.brand == "Fellow Stagg" and line.sells, written
        assert (line.from_price, line.from_price_shop, line.from_price_checked_on) == (145.0, "Borough Kitchen", ROUND2)
        assert line.from_price_url in line.sources
    # Fellow's other kettles aren't this line's, and a stovetop Stagg isn't an electric kettle.
    fellow = find_brand_line(["Fellow"], "kitchen", "electric kettle", lines)
    assert fellow is None or fellow.brand != "Fellow Stagg"
    assert find_brand_line(["Stagg"], "kitchen", "stovetop kettle", lines) is None


def test_fellows_kettle_line_and_the_lelit_victoria_have_uk_prices_so_budgets_under_them_leave_them_out():
    # The round's kettle and bean-to-cup threads put the Fellow electric kettle line under "1.7l kettle under £40" and
    # the Lelit Victoria under "espresso machine for a beginner under £500", both shown unpriced; neither is near its
    # budget at a UK shop.
    line = find_brand_line(["Fellow"], "kitchen", "electric kettle", load_brand_lines())
    assert line is not None and line.brand == "Fellow" and line.sells
    assert (line.from_price, line.from_price_shop, line.from_price_checked_on) == (145.0, "Borough Kitchen", ROUND2)
    prices = load_prices()
    price = find_price("Lelit Victoria", "kitchen", prices, currency="GBP", product_type="espresso machine")
    assert price is not None and (price.price, price.shop, price.checked_on) == (759.0, "Bella Barista", ROUND2)
    # Out of stock for now ("coming soon") counts as sold, as the price list's other entries do.
    assert find_availability("Lelit Victoria PL91T", "kitchen", prices, "espresso machine").available is True


def test_the_rounds_new_picks_link_their_own_pages_with_uk_prices_where_sold():
    # Item 4: product pages for the kitchen picks the round's threads add, each read for its own name (engine.buyable's
    # findings format): the Rancilio Silvia ("coffee machine"), the Pepper Cannon ("pepper grinder that doesn't
    # leak") and Mercer's 10" Millennia bread knife ("a good bread knife for sourdough").
    pages, prices = load_product_pages(), load_prices()
    for shown, product_type, site, price in (("Rancilio Silvia", "espresso machine", "bellabarista.co.uk", (589.0, "Bella Barista")),
                                             ("mannkitchen original pepper cannon pepper mill", "pepper grinder",
                                              "mannkitchen.co.uk", (175.0, "Männkitchen")),
                                             ('Mercer Culinary Millennia wavy edge wide bread knife 10"', "bread knife",
                                              "mercerculinary.com", None)):
        page = find_page([shown], "kitchen", product_type, pages)
        assert page is not None and site in page.page and page.checked_on == ROUND2, shown
        found = find_price(shown, "kitchen", prices, currency="GBP", product_type=product_type)
        if price is None:  # Mercer's own (US) page gives no UK price: no price-list entry is made
            assert found is None, shown
        else:
            assert found is not None and (found.price, found.shop, found.checked_on) == (*price, ROUND2), shown


def test_the_lines_the_rounds_threads_pick_have_range_pages_and_uk_from_prices_or_say_where_they_are_sold():
    # The round's pepper grinder, bread knife and stick blender threads pick brand lines with no entry ("Price not
    # checked yet", no range link): their makers' UK pages give each a range page and a from price, and Unicorn, sold
    # only in the US (through Amazon there), is said to be not sold in the UK.
    lines, prices = load_brand_lines(), load_prices()
    for brand, product_type, site, price, shop in (("Peugeot", "pepper grinder", "uk.peugeot-saveurs.com", 23.5, "Peugeot Saveurs"),
                                                   ("Victorinox", "bread knife", "victorinox.com/en-GB", 32.0, "Victorinox"),
                                                   ("KitchenAid", "immersion blender", "kitchenaid.co.uk", 109.0, "KitchenAid")):
        line = find_brand_line([brand], "kitchen", product_type, lines)
        assert line is not None and line.brand == brand and line.sells and site in line.range_page, brand
        assert (line.from_price, line.from_price_shop, line.from_price_checked_on) == (price, shop, ROUND2), brand
        assert line.from_price_url in line.sources, brand
    unicorn = find_availability("Unicorn pepper grinder", "kitchen", prices, "pepper grinder")
    assert unicorn is not None and unicorn.available is False and unicorn.not_in_uk and unicorn.checked_on == ROUND2


def test_the_second_reads_picks_have_uk_pages_prices_or_say_they_arent_sold_here():
    # The round's later threads (saucepans, garlic presses, meat grinders, toastie makers) pick products with no
    # entries: Le Creuset's saucepans (a line in "a good saucepan"), IKEA's KONCIS garlic press, KitchenAid's plastic
    # meat grinder attachment (its 5KSMFGA) and the Snakmaster sandwich maker, which no UK shop sells.
    lines, prices, pages = load_brand_lines(), load_prices(), load_product_pages()
    line = find_brand_line(["Le Creuset"], "kitchen", "saucepan", lines)
    assert line is not None and line.sells and "lecreuset.co.uk" in line.range_page
    assert (line.from_price, line.from_price_shop, line.from_price_checked_on) == (125.0, "Le Creuset", ROUND2)
    for shown, product_type, site, amount, shop in (("Ikea KONCIS garlic press", "garlic press", "ikea.com/gb", 4.0, "IKEA"),
                                                    ("KitchenAid plastic meat grinder attachment", "meat grinder",
                                                     "kitchenaid.co.uk", 109.0, "KitchenAid")):
        page = find_page([shown], "kitchen", product_type, pages)
        assert page is not None and site in page.page and page.checked_on == ROUND2, shown
        price = find_price(shown, "kitchen", prices, currency="GBP", product_type=product_type)
        assert price is not None and (price.price, price.shop, price.checked_on) == (amount, shop, ROUND2), shown
    snakmaster = find_availability("Snakmaster", "kitchen", prices, "sandwich maker")
    assert snakmaster is not None and snakmaster.available is False and snakmaster.not_in_uk


def test_oxos_garlic_press_line_has_a_uk_from_price():
    # "garlic press that's easy to clean" picks the OXO garlic press line; OXO has no UK store, and John Lewis sells its
    # Good Grips press with a built-in cleaner.
    line = find_brand_line(["OXO"], "kitchen", "garlic press", load_brand_lines())
    assert line is not None and line.sells and "johnlewis.com" in line.range_page
    assert (line.from_price, line.from_price_shop, line.from_price_checked_on) == (20.0, "John Lewis", ROUND2)
