"""Round 2 data fixes of 18 Oct 2026 (the round-2 data builder; items from the coordinator's list after round 1's
integration): each is a correction to a committed list (data/prices.json, data/product_facts.json,
data/product_pages.json) checked against what the answers need from it.

1. The price and pages lists' eye cream is named as its maker spells it ("Ole Henriksen ..."), not with the slip
   "OleHenricksen ...", so a writer's slip, shown as the maker's name, finds its £38 price and page.
2. The Kindle Keyboard (a 2010 model) is no longer sold: Amazon ended Kindle Store support for e-readers released in
   2012 or earlier on 20 May 2026.
3. PFAS, from the makers' own pages (her rule of 11 Oct 2026: a coating the maker names as PTFE is pfas_free false):
   Scanpan says its non-stick pans contain some PTFE; HexClad's current pages name its coating as a ceramic one
   (TerraBond) that it calls PTFE-free and PFAS-free; Le Creuset's toughened non-stick was recorded on 17 Oct 2026.
4. The Snakmaster sandwich maker (a 1990 infomercial product) is no longer sold new: discontinued, not "not sold in the
   UK".
5. The two blind-test picks sold out in every UK shop read (Isntree's Chestnut BHA 2% Clear Liquid, innisfree's Retinol
   Cica serum): checked again on 18 Oct 2026, still counted as sold (the price list's convention: out of stock for now is
   sold, discontinued isn't).

Most tests read the committed lists; the end-to-end ones use made-up libraries in a temporary folder (every comment
invented) with the committed lists, so they show what the lists change in an answer.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from engine.brand_lines import load_brand_lines
from engine.group_products import maker_spelling
from engine.pipeline import _spelling_lists, answer_request
from engine.prices import check_price, counts_as_sold, find_availability, find_price, load_prices
from engine.product_facts import find_brand_facts, find_facts, load_product_facts
from engine.product_pages import find_page, load_product_pages
from engine.query import Budget
from engine.tests.factories import make_comment, make_thread, write_gold
from engine.tests.test_pipeline import praise
from engine.tests.test_pipeline import write_library as write_kitchen_library

TODAY = date(2026, 10, 18)


def library(tmp_path: Path, threads: list[tuple]) -> Path:
    """A made-up library of any category: threads are (id, community, category, title, [(comment id, product, text)]),
    every comment a recommendation whose text is also its quote."""
    made, extractions = [], {}
    for tid, community, category, title, comments in threads:
        url = f"https://www.reddit.com/r/{community}/comments/{tid}/t/"
        made.append(make_thread(id=tid, community=community, category=category, title=title, body="Any advice?", url=url,
                                comments=[make_comment(cid, thread_id=tid, body=text, url=f"{url}{cid}/")
                                          for cid, _, text in comments]))
        extractions[tid] = [{"comment_id": cid, "product": product, "category": category, "stance": "recommend",
                             "quote": text} for cid, product, text in comments]
    root = write_gold(tmp_path / "library", made, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for tid, mentions in extractions.items():
        (root / "extracted" / f"{tid}.json").write_text(json.dumps({
            "thread_id": tid, "instructions_version": "extract-v5", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions}), encoding="utf-8")
    return root


def answer(request: str, root: Path):
    return answer_request(request, library_dir=root, prices=load_prices(), product_facts=load_product_facts(),
                          brand_lines=load_brand_lines(), product_pages=load_product_pages(), today=TODAY,
                          more_threads=None)


def shown(result) -> list[str]:
    return [pick.name for pick in result.answer.picks] + [item.name for item in result.answer.worth_a_look]


# --- 1. The eye cream is named as its maker spells it ---

EYE_CREAM = "Ole Henriksen banana bright + vitamin C under eye cream"
EYE_CREAM_SLIP = "OleHenricksen banana bright + vitamin C under eye cream"  # a writer's slip, and the lists' until now


def test_the_eye_creams_entries_are_named_as_its_maker_spells_it():
    prices, pages = load_prices(), load_product_pages()
    assert [p.product for p in prices if "henricksen" in p.product.lower()] == []
    assert [p.product for p in pages if "henricksen" in p.product.lower()] == []
    assert [p.product for p in prices if "banana bright" in p.product.lower()] == [EYE_CREAM]
    assert [p.product for p in pages if "banana bright" in p.product.lower()] == [EYE_CREAM]


def test_a_writers_slip_is_shown_as_the_makers_name_and_finds_its_price_and_page():
    # Changed on purpose 18 Oct 2026: engine/tests/test_names_round_two.py kept the list's slip as the shown name so
    # the £38 price was found (an answer finds a product's price and page by the name it is shown under); now the list
    # itself is right, and the writer's slip is respelled as the maker writes it.
    prices, pages = load_prices(), load_product_pages()
    makers, curated = _spelling_lists(load_brand_lines(), prices, load_product_facts(), "skincare")
    name = maker_spelling(EYE_CREAM_SLIP, "skincare", makers, curated)
    assert name == EYE_CREAM
    price = find_price(name, "skincare", prices, currency="GBP", product_type="eye cream")
    assert price is not None and (price.price, price.shop) == (38.0, "Lookfantastic")
    assert counts_as_sold(find_availability(name, "skincare", prices, product_type="eye cream")) is True
    assert check_price(price, Budget(max=35, currency="GBP"), TODAY).status == "over"  # a £35 budget leaves it out
    assert check_price(price, Budget(max=40, currency="GBP"), TODAY).status == "within"
    page = find_page([name], "skincare", "eye cream", pages)
    assert page is not None and "lookfantastic.com" in page.page


def eye_cream_library(tmp_path):
    return library(tmp_path, [
        ("1eye001", "SkincareAddiction", "skincare", "Eye cream that works?", [
            ("e1a", EYE_CREAM_SLIP, f"I use {EYE_CREAM_SLIP} every night and it has been great for 2 years."),
            ("e1b", EYE_CREAM_SLIP, f"I've repurchased {EYE_CREAM_SLIP} three times in two years."),
            ("e1c", "Clinique all about eyes", "I use Clinique all about eyes for 3 years and love it."),
            ("e1d", "Clinique all about eyes", "Clinique all about eyes has been in my routine for 5 years."),
        ]),
        ("1eye002", "SkincareAddiction", "skincare", "Best under eye cream?", [
            ("e2a", EYE_CREAM_SLIP, f"Two years with {EYE_CREAM_SLIP} and no complaints."),
            ("e2b", "Clinique all about eyes", "I've used Clinique all about eyes for 4 years and it is great."),
        ]),
    ])


def test_an_answer_shows_the_eye_cream_under_its_makers_name_with_its_price(tmp_path):
    result = answer("eye cream", eye_cream_library(tmp_path))
    picks = {pick.name: pick for pick in result.answer.picks}
    assert EYE_CREAM in picks and EYE_CREAM_SLIP not in picks
    assert picks[EYE_CREAM].price.amount == 38.0 and picks[EYE_CREAM].availability.available is True


def test_a_35_pound_budget_still_leaves_the_eye_cream_out(tmp_path):
    result = answer("eye cream under £35", eye_cream_library(tmp_path))
    assert EYE_CREAM not in shown(result) and EYE_CREAM_SLIP not in shown(result)
    assert EYE_CREAM in result.left_out_over_budget


# --- 2. The Kindle Keyboard ---

@pytest.mark.parametrize("written", ["Kindle Keyboard", "Kindle Keyboard 3G", "kindle keyboard", "Kindle keyboard",
                                     "Amazon Kindle Keyboard"])
def test_the_kindle_keyboard_is_known_to_be_no_longer_sold(written):
    entry = find_availability(written, "general", load_prices(), product_type="e-reader")
    assert entry is not None and entry.available is False and not entry.not_in_uk, written
    assert counts_as_sold(entry) is False
    assert entry.note.startswith("discontinued:") and entry.checked_on == TODAY
    assert any("amazon.com/gp/help" in source for source in entry.sources)  # Amazon's own page on old e-readers
    assert find_price(written, "general", load_prices(), product_type="e-reader") is None


@pytest.mark.parametrize("written", ["Kindle", "Kindle Paperwhite", "Kindle Paperwhite 3", "Kindle Touch", "Kindle Oasis",
                                     "kindle basic", "Kobo Clara"])
def test_the_keyboards_entry_is_not_taken_for_another_e_reader(written):
    entry = find_availability(written, "general", load_prices(), product_type="e-reader")
    assert entry is None or "Keyboard" not in entry.product, written


def test_the_kindle_keyboard_is_left_out_of_an_e_reader_answer_and_named(tmp_path):
    root = library(tmp_path, [
        ("1ereader1", "BuyItForLife", "general", "Which e-reader lasts?", [
            ("r1a", "Kindle Keyboard", "My Kindle Keyboard has lasted 12 years and still works perfectly."),
            ("r1b", "Kindle Keyboard 3G", "Our Kindle Keyboard 3G is 11 years old and still going strong."),
            ("r1c", "Kobo Clara", "My Kobo Clara has lasted 4 years and still works perfectly."),
            ("r1d", "Kobo Clara", "I've used the Kobo Clara daily for 3 years, no problems."),
        ]),
        ("1ereader2", "BuyItForLife", "general", "E-reader that lasts for years?", [
            ("r2a", "Kindle Keyboard", "I've used the Kindle Keyboard for 10 years, battery still fine."),
            ("r2b", "Kobo Clara", "The Kobo Clara has lasted 5 years without a problem."),
        ]),
    ])
    result = answer("e-reader", root)
    assert not any("Keyboard" in name for name in shown(result))
    assert any("Keyboard" in name for name in result.left_out_unavailable)


# --- 3. PFAS, from the makers' own pages ---

@pytest.mark.parametrize("written", ["Scanpan", "scanpan", "ScanPan", "Scanpans", "Scan Pan", "Scanpan frying pans",
                                     "Scanpan deep saute pans"])
def test_scanpans_non_stick_pans_contain_ptfe_by_its_makers_own_faq(written):
    # Its FAQ (scanpan.co.uk/pages/faq, read 18 Oct 2026) says its pans are free of PFOA and PFOS but do contain some
    # PTFE; before, only "Scanpan non-stick pans" and "Scanpan CTX" had the fact, so a bare "Scanpan" (writers' name for
    # the non-stick pans) was "Also worth a look" in a PFAS-free answer, unchecked.
    facts = load_product_facts()
    entry = find_facts(written, "kitchen", facts, "frying pan")
    assert entry is not None, written
    assert entry.facts.get("pfas_free") is False and entry.facts.get("non_stick") is True, written
    assert entry.checked_on == TODAY and any("scanpan.co.uk/pages/faq" in source for source in entry.sources), written
    assert find_brand_facts([written], "kitchen", facts, ("frying pan", "frying pans"), "frying pan") in (None, entry)


def test_scanpans_named_ranges_are_decided_per_model():
    facts = load_product_facts()
    haptiq = find_facts("ScanPan Haptiq", "kitchen", facts, "frying pan")  # Stratanium+, one of the FAQ's named ranges
    assert haptiq is not None and haptiq.product == "Scanpan Haptiq"
    assert haptiq.facts == {"non_stick": True, "pfas_free": False, "induction": True}
    assert any("haptiq-frying-pan" in source for source in haptiq.sources)
    ctx = find_facts("Scanpans ctx-series", "kitchen", facts, "frying pan")  # recorded 14 Oct 2026, kept
    assert ctx is not None and ctx.product == "Scanpan CTX" and ctx.facts.get("pfas_free") is False
    # The brand's own name is one entry, each named range another: a range never takes the brand's entry.
    assert find_facts("Scanpan", "kitchen", facts, "frying pan").product == "Scanpan"


@pytest.mark.parametrize("written", ["HexClad", "Hexclad", "hexclad", "Hexclad pan", "Hexclad pans", "HexClad frying pans",
                                     "hexclad frying pan", "HexClad skillet", "hexclad trio"])
def test_hexclads_pans_are_ptfe_free_by_its_makers_current_pages(written):
    # Its FAQ (hexclad.com/pages/faq, read 18 Oct 2026) names the coating of all its cookware as TerraBond, a ceramic
    # non-stick it calls PTFE-free and PFAS-free. Its earlier pans were PTFE (reviews put the switch in 2024/25,
    # unannounced), which is what most writers' pans are: the entry is the maker's present word, not a claim about
    # every pan ever sold.
    facts = load_product_facts()
    entry = find_facts(written, "kitchen", facts, "frying pan")
    assert entry is not None and entry.product == "HexClad", written
    assert entry.facts.get("pfas_free") is True and entry.facts.get("non_stick") is True, written
    assert entry.facts.get("induction") is True, written  # its FAQ lists newer induction cooktops among those it suits
    assert entry.checked_on == TODAY and any("hexclad.com/pages/faq" in source for source in entry.sources), written


def test_le_creusets_toughened_non_stick_stays_a_pfas_coating():
    # Recorded 17 Oct 2026 from Le Creuset's own pages (its pages disclose that the Toughened Non-stick PRO pans
    # contain PFAS); its site gave this round's reads an empty page, so it was not read again.
    facts = load_product_facts()
    for written in ('Le Creuset "toughened non-stick" pan', "LeCreuset non-stick", "Le Creuset non-stick pans"):
        entry = find_facts(written, "kitchen", facts, "frying pan")
        assert entry is not None and entry.facts.get("pfas_free") is False, written
        assert any("lecreuset" in source for source in entry.sources), written


def pan_library(tmp_path):
    return write_kitchen_library(tmp_path, {
        "1pan0001": ("Non-toxic non-stick pan?", "Replacing my old ones.", [
            praise("p1a", "GreenPan", 4), praise("p1b", "GreenPan", 5),
            praise("p1c", "HexClad", 3), praise("p1d", "Hexclad pans", 4),
            praise("p1e", "Scanpan", 6), praise("p1f", "scanpan", 7),
        ]),
        "1pan0002": ("Which non-stick pan lasts?", "Ten years, ideally.", [
            praise("p2a", "GreenPan", 6), praise("p2b", "HexClad", 5), praise("p2c", "ScanPan", 9),
        ]),
    }, community="BuyItForLife")


def test_a_pfas_free_answer_keeps_hexclad_confirmed_and_leaves_scanpan_out(tmp_path):
    result = answer_request("non toxic frying pan", library_dir=pan_library(tmp_path), prices=load_prices(),
                            product_facts=load_product_facts(), brand_lines=load_brand_lines(),
                            product_pages=load_product_pages(), today=TODAY, more_threads=None)
    names = shown(result)
    assert not any("Scanpan" in name for name in names)
    left_out = {item.name: item.reason for item in result.left_out_not_suited}
    assert left_out.get("Scanpan") == "it isn't PFAS-free"
    hexclad = [pick for pick in result.answer.picks if "HexClad" in pick.name]
    assert hexclad and not any("couldn't confirm" in note for note in hexclad[0].cautions)


def test_an_induction_answer_doesnt_note_hexclad_as_unconfirmed(tmp_path):
    # Its FAQ lists newer induction cooktops among those it works on; before the entry said so, HexClad came into this
    # answer (as "HexClad frying pan line") with "we couldn't confirm it works on an induction hob".
    result = answer_request("a frying pan for an induction hob", library_dir=pan_library(tmp_path), prices=load_prices(),
                            product_facts=load_product_facts(), brand_lines=load_brand_lines(),
                            product_pages=load_product_pages(), today=TODAY, more_threads=None)
    hexclad = [item for item in [*result.answer.picks, *result.answer.worth_a_look] if "HexClad" in item.name]
    assert hexclad and not any("induction" in note for note in hexclad[0].cautions)


# --- 4. The Snakmaster ---

@pytest.mark.parametrize("written", ["Snakmaster", "snakmaster", "snack master", "Snakmaster sandwich maker"])
def test_the_snakmaster_is_discontinued_not_just_missing_from_uk_shops(written):
    entry = find_availability(written, "kitchen", load_prices(), product_type="sandwich maker")
    assert entry is not None and entry.available is False, written
    assert not entry.not_in_uk, written  # "not sold in the UK" would keep it in answers with a note
    assert counts_as_sold(entry) is False and not entry.second_hand
    assert entry.note.startswith("discontinued:") and entry.checked_on == TODAY
    assert any("hunker.com" in source for source in entry.sources)


def test_a_toastie_answer_leaves_the_snakmaster_out_and_names_it(tmp_path):
    root = write_kitchen_library(tmp_path, {
        "1toast01": ("Best toastie maker?", "Our old one died.", [
            praise("t1a", "Snakmaster", 30), praise("t1b", "Snakmaster", 25), praise("t1c", "Snakmaster", 28),
        ]),
        "1toast02": ("Toasted sandwich maker that lasts?", "Looking for BIFL.", [
            praise("t2a", "Snakmaster", 31), praise("t2b", "Sage sandwich maker", 4),
        ]),
    }, community="BuyItForLife")
    result = answer("toastie maker", root)
    assert not any("Snakmaster" in name for name in shown(result))
    assert "Snakmaster" in result.left_out_unavailable


# --- 5. The two blind-test picks sold out in every UK shop read ---

@pytest.mark.parametrize("written, shop, amount, product_type, new_source", [
    ("Isntree Chestnut BHA 2% Clear Liquid", "Skinsider", 18.0, "exfoliant", "lookfantastic.com/search"),
    ("innisfree Retinol Cica Moisture Recovery Serum", "Cult Beauty", 33.0, "retinoid", "asos.com"),
])
def test_a_blind_test_pick_sold_out_for_now_still_counts_as_sold(written, shop, amount, product_type, new_source):
    # By the price list's convention an out-of-stock product is sold; only one a maker or shop says is discontinued
    # isn't. Nothing read on 18 Oct 2026 says either is, so both keep their price and stay in b01's and b03's answers.
    prices = load_prices()
    entry = find_availability(written, "skincare", prices, product_type=product_type)
    assert entry is not None and entry.available is True and counts_as_sold(entry) is True
    assert (entry.shop, entry.price, entry.checked_on) == (shop, amount, TODAY)
    price = find_price(written, "skincare", prices, currency="GBP", product_type=product_type)
    assert price is not None and (price.price, price.shop) == (amount, shop)
    assert any(new_source in source for source in entry.sources), "this round's new read is among its sources"
    assert "discontinued" not in entry.note.split(".")[0].lower()
    # One row for the day: a second row of the same day would only repeat the first.
    same_day = [p for p in prices if p.product == written and p.checked_on == TODAY]
    assert len(same_day) == 1


def test_both_picks_stay_in_the_blind_tests_answers_with_their_uk_price(tmp_path):
    root = library(tmp_path, [
        ("1exf0001", "SkincareAddiction", "skincare", "Gentle exfoliant for sensitive skin?", [
            ("x1a", "Isntree Chestnut BHA 2% Clear Liquid", "Isntree Chestnut BHA 2% Clear Liquid is gentle, 2 years in."),
            ("x1b", "Isntree Chestnut BHA 2% Clear Liquid", "I've used Isntree Chestnut BHA 2% Clear Liquid for 3 years."),
            ("x1c", "Isntree Chestnut BHA 2% Clear Liquid", "Isntree Chestnut BHA 2% Clear Liquid, my gentle favourite."),
        ]),
        ("1exf0002", "SkincareAddiction", "skincare", "Exfoliant that won't sting?", [
            ("x2a", "Isntree Chestnut BHA 2% Clear Liquid", "Isntree Chestnut BHA 2% Clear Liquid never stings, 2 years."),
            ("x2b", "Isntree Chestnut BHA 2% Clear Liquid", "Been on Isntree Chestnut BHA 2% Clear Liquid for 4 years."),
        ]),
    ])
    result = answer("gentle exfoliant for sensitive skin under £30", root)
    picks = {pick.name: pick for pick in result.answer.picks}
    pick = picks.get("Isntree Chestnut BHA 2% Clear Liquid")
    assert pick is not None and pick.price.amount == 18.0 and pick.availability.available is True
