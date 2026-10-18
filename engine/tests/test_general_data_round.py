"""General data round of 18 Oct 2026 (the ws-data-general builder): the committed lists' general entries this round
added, checked against what the general answers need from them.

Why: in the 17 Oct sweep most general answers (hiking boots, tents, strollers, running shoes, running watches...) had
few or no picks partly because writers name the brand alone ("my Merrells", "Lowa", "Garmin"): module 4 marks such a
name loose, and a loose name counts as the brand's whole line only when the brand-lines list (data/brand_lines.json,
researched on the makers' pages) says the brand sells that kind of product (Noemi, 12 Oct 2026). So the round
researched, for the brands writers name alone in these answers, whether they make the type, their range page and a UK
"From" price (Noemi's night decision 1 of 14 Oct 2026), or that they are sold abroad only (her rule of 15 Oct 2026,
evening: the best pick whatever country it is sold in, with a note).

Most tests read the committed lists (data/); the end-to-end one uses a made-up library in a temporary folder with the
committed lists, so it shows what the lists change in an answer. Every thread, comment and writer here is made up.
"""

import json
from datetime import date
from pathlib import Path

from engine.brand_lines import find_brand_line, load_brand_lines
from engine.pipeline import answer_request
from engine.prices import find_availability, find_brand_entry, find_price, load_prices
from engine.product_facts import load_product_facts
from engine.product_pages import load_product_pages
from engine.tests.factories import make_comment, make_thread, write_gold

ROUND = date(2026, 10, 18)

# (names writers use, product type, the brand as its maker writes it, from price, its shop)
LINES_SOLD_IN_THE_UK = [
    (["Patagonia"], "rain jacket", "Patagonia", 180.0, "John Lewis"),
    (["Nalgene"], "water bottle", "Nalgene", 12.99, "Heinnie Haynes"),
    (["Dyson"], "hair dryer", "Dyson", 249.99, "John Lewis"),
    (["Sonicare", "sonicare"], "electric toothbrush", "Sonicare", 39.99, "John Lewis"),
    (["DeWalt", "Dewalt"], "drill", "DeWalt", 75.0, "B&Q"),
    (["Merrell", "Merrells", "merrells"], "hiking boots", "Merrell", 120.0, "Merrell UK"),
    (["Salomon", "Solomon"], "hiking boots", "Salomon", 150.0, "John Lewis"),
    (["Lowa", "LOWA"], "hiking boots", "LOWA", 114.0, "LOWA UK"),
    (["Keen", "Keens", "KEEN"], "hiking boots", "KEEN", 110.0, "KEEN UK"),
    (["Meindl"], "hiking boots", "Meindl", 184.99, "Meindl UK"),
    (["UPPAbaby", "Uppababy"], "stroller", "UPPAbaby", 399.0, "John Lewis"),
    (["UPPAbaby Vista", "Uppababy Vista"], "stroller", "UPPAbaby Vista", 1099.99, "John Lewis"),
    (["Bugaboo"], "stroller", "Bugaboo", 435.0, "John Lewis"),
    (["Garmin"], "sports watch", "Garmin", 199.0, "John Lewis"),
    (["Hoka", "HOKA", "Hokas"], "running shoes", "HOKA", 89.99, "SportsShoes"),
    (["Saucony"], "running shoes", "Saucony", 77.99, "SportsShoes"),
    (["New Balance"], "running shoes", "New Balance", 26.99, "SportsShoes"),
    (["Brooks"], "running shoes", "Brooks", 100.0, "SportsShoes"),
    (["Asics", "ASICS", "asics"], "running shoes", "ASICS", 68.99, "SportsShoes"),
    (["BaByliss", "Babyliss"], "hair dryer", "BaByliss", 23.0, "John Lewis"),
    (["T3"], "hair dryer", "T3", 139.99, "T3 UK"),
    (["Darn Tough", "darn tough"], "socks", "Darn Tough", 20.0, "Darn Tough UK"),
    (["Manduka"], "yoga mat", "Manduka", 100.0, "Yogamatters"),
    (["Osprey"], "backpack", "Osprey", 65.0, "John Lewis"),
    (["Osprey Farpoint"], "backpack", "Osprey Farpoint", 170.0, "John Lewis"),
    (["Osprey Fairview"], "backpack", "Osprey Fairview", 170.0, "John Lewis"),
    (["Briggs & Riley", "Briggs and Riley"], "suitcase", "Briggs & Riley", 389.0, "John Lewis"),
    (["Klean Kanteen", "Klein Kanteen"], "water bottle", "Klean Kanteen", 19.64, "Alpinetrek"),
    (["COROS", "Coros"], "sports watch", "COROS", 229.0, "COROS UK"),
    (["Honda"], "lawn mower", "Honda", 425.0, "Honda UK"),
    (["Levi's", "Levis", "Levi’s"], "jeans", "Levi's", 70.0, "John Lewis"),
    (["Smartwool", "SmartWool"], "socks", "Smartwool", 21.0, "John Lewis"),
    (["Hydro Flask", "Hydroflask"], "water bottle", "Hydro Flask", 34.95, "John Lewis"),
    (["Ruffwear"], "dog harness", "Ruffwear", 21.95, "Ruffwear UK"),
]

# Brands the makers' own pages show selling the type, with no UK price readable (their prices load by script).
LINES_WITH_NO_FROM_PRICE = [(["Arc'teryx", "Arcteryx"], "rain jacket", "Arc'teryx"),
                            (["Wrangler", "Wranglers"], "jeans", "Wrangler")]


def test_brands_with_no_readable_price_still_have_their_range():
    lines = load_brand_lines()
    for names, product_type, brand in LINES_WITH_NO_FROM_PRICE:
        for name in names:
            line = find_brand_line([name], "general", product_type, lines)
            assert line is not None and line.brand == brand and line.sells and line.range_page, name
            assert line.from_price is None, name


def test_klein_alone_is_not_klean_kanteen():
    # Writers misspell Klean Kanteen "Klein Kanteen"; Klein alone is the tool maker's name, never the bottle's.
    assert find_brand_line(["Klein"], "general", "water bottle", load_brand_lines()) is None

# (the name an answer shows, product type, price or None for a range with no single price, its shop)
PRODUCTS_SOLD_IN_THE_UK = [
    ("Lowa Renegade GTX", "hiking boots", 220.0, "LOWA UK"),
    ("Fjällräven Nuuk Parka", "winter coat", 394.96, "Nordic Outdoor"),
    ("nanit cam", "baby monitor", 249.99, "John Lewis"),
    ("Darn Tough tactical socks", "socks", None, "Darn Tough UK"),
    ("Garmin Forerunner 165", "sports watch", 249.0, "John Lewis"),
    ("Garmin Forerunner 265", "sports watch", 369.99, "John Lewis"),
    ("Garmin Forerunner 570", "sports watch", 429.0, "John Lewis"),
    ("COROS PACE 3", "sports watch", None, "COROS UK"),
    # engine.maker_pages found its 71cm spinner, a checked case; writers' Platinum Elite in carry-on threads is the
    # cabin size: its 55cm spinner, out of stock for now (which still counts as sold).
    ("Travelpro Platinum Elite", "suitcase", 285.0, "Travelpro"),
    # A range ("Carhartt boot socks"): its page is one boot sock's, so no single price.
    ("Carhartt boot socks", "socks", None, "Carhartt"),
    ("Thule Chariot", "stroller", None, "Thule UK"),
    ("Ruffwear Front Range harness", "dog harness", 49.95, "Ruffwear UK"),
]


def test_a_us_only_mower_is_shown_as_sold_abroad():
    # Ryobi's 40V mowers are its US range; its UK site has no such mower.
    entry = find_availability("Ryobi 40V 20-inch push mower", "general", load_prices(), "lawn mower")
    assert entry is not None and entry.available is False and entry.not_in_uk and entry.checked_on == ROUND


def test_shown_products_have_a_uk_price_or_where_they_are_sold():
    prices = load_prices()
    for name, product_type, amount, shop in PRODUCTS_SOLD_IN_THE_UK:
        entry = find_availability(name, "general", prices, product_type)
        assert entry is not None and entry.available is True and entry.shop == shop, name
        assert entry.checked_on == ROUND, name
        price = find_price(name, "general", prices, "GBP", product_type)
        assert (price.price if price else None) == amount, name


def test_brands_writers_name_alone_have_a_brand_lines_entry_with_a_uk_from_price():
    lines = load_brand_lines()
    for names, product_type, brand, amount, shop in LINES_SOLD_IN_THE_UK:
        for name in names:
            line = find_brand_line([name], "general", product_type, lines)
            assert line is not None and line.brand == brand and line.sells, (name, product_type)
            assert line.range_page and line.range_page in line.sources, (name, product_type)
            assert (line.from_price, line.from_price_shop) == (amount, shop), (name, product_type)
            assert line.from_price_url in line.sources and line.from_price_checked_on == ROUND, (name, product_type)


def test_a_brand_line_is_only_its_own_type():
    # An entry speaks for its type alone: Garmin's sports watches say nothing of Garmin's dash cams' line (a type of
    # its own in the list), nor Merrell's hiking boots of running shoes.
    lines = load_brand_lines()
    assert find_brand_line(["Merrell"], "general", "running shoes", lines) is None
    assert find_brand_line(["Garmin"], "general", "sports watch", lines).product_type == "sports watch"
    assert find_brand_line(["Garmin"], "general", "dash cam", lines).product_type == "dash cam"


def test_the_uk_lines_have_a_price_list_entry_saying_they_are_sold_here():
    prices = load_prices()
    for names, product_type, brand, _, shop in LINES_SOLD_IN_THE_UK:
        entry = find_brand_entry(names, "general", prices, product_type.split(), product_type)
        assert entry is not None and entry.available is True and not entry.not_in_uk, (brand, product_type)


def test_danner_hiking_boots_are_a_line_sold_abroad_only():
    # Danner (US) makes hiking boots (its Mountain 600), sold from its own US store; no UK seller was found, so its line
    # stays in answers with "Not sold in the UK" (Noemi, 15 Oct 2026, evening), as its work boots did on 15 Oct.
    line = find_brand_line(["Danner"], "general", "hiking boots", load_brand_lines())
    assert line is not None and line.sells and "danner.com" in line.range_page
    entry = find_brand_entry(["Danner"], "general", load_prices(), ["hiking", "boots"], "hiking boots")
    assert entry is not None and entry.available is False and entry.not_in_uk and entry.checked_on == ROUND


# --- What the lists change in an answer ---

PRAISE = "My {brand} have done {years} years of hill walking and they are still waterproof."


def boots_library(tmp_path: Path) -> Path:
    """Two hiking-boot threads in which writers praise Merrell and Keen boots by the brand alone (three writers each,
    across both threads) and name two models of each once, whose names don't say "boots", as in the 17 Oct library's
    hiking boot threads: so each brand's name fits several products (module 4 marks it loose), and its threads alone
    don't make the product clear (no name of the brand says the type: engine.pipeline._clear_brand)."""
    def thread(thread_id: str, title: str, praised: list[tuple[str, str, int]]) -> dict:
        url = f"https://www.reddit.com/r/hiking/comments/{thread_id}/x/"
        comments = [make_comment(cid, thread_id=thread_id, body=PRAISE.format(brand=brand, years=years),
                                 url=f"https://www.reddit.com/r/hiking/comments/{thread_id}/comment/{cid}/")
                    for cid, brand, years in praised]
        return make_thread(id=thread_id, community="hiking", category="general", title=title,
                           body="Mine are worn out.", url=url, comments=comments)

    threads = {
        "1boot01": thread("1boot01", "Hiking boot recommendations?", [
            ("b1aaaa", "Merrells", 6), ("b1bbbb", "Merrells", 4), ("b1cccc", "Keens", 5), ("b1dddd", "Keens", 3),
            ("b1eeee", "Merrell Moab 3 Mid GTX", 2), ("b1ffff", "Keen Targhee IV", 2)]),
        "1boot02": thread("1boot02", "Which hiking boots last?", [
            ("b2aaaa", "Merrells", 7), ("b2bbbb", "Keens", 8), ("b2cccc", "Merrell Thermo Chill 2", 1),
            ("b2dddd", "Keen Zionic", 1)]),
    }
    root = write_gold(tmp_path / "library", list(threads.values()), voices=None, mentions=None)
    (root / "extracted").mkdir()
    for thread_id, data in threads.items():
        mentions = []
        for c in data["comments"]:
            brand = c["body"].split(" have ")[0].removeprefix("My ")
            mentions.append({"comment_id": c["id"], "product": brand, "category": "general",
                             "product_type": "hiking boots", "stance": "recommend", "evidence": "long-term use",
                             "evidence_tags": ["long-term use"], "quote": c["body"]})
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v15", "extracted_at": "2026-10-18T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions}), encoding="utf-8")
    return root


def test_boots_named_by_their_brand_alone_are_ranked_as_the_brands_lines_with_their_from_prices(tmp_path):
    result = answer_request("hiking boots", library_dir=boots_library(tmp_path), prices=load_prices(),
                            product_facts=load_product_facts(), brand_lines=load_brand_lines(),
                            product_pages=load_product_pages(), today=ROUND, more_threads=None)
    picks = {pick.name: pick for pick in result.answer.picks}
    assert {"Merrell hiking boots line", "KEEN hiking boots line"} <= set(picks), list(picks)
    assert picks["Merrell hiking boots line"].price.text == "From £120 at Merrell UK, checked 18 Oct 2026"
    assert picks["KEEN hiking boots line"].availability.text == "Sold at KEEN UK, checked 18 Oct 2026"
