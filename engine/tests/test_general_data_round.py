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
    (["Merrell", "Merrells", "merrells"], "hiking boots", "Merrell", 58.0, "Merrell UK"),
    # 18 Oct 2026, the same day: hiking shoes are of the type too (its keywords), so Salomon's and KEEN's from prices are
    # their cheapest hiking shoes (£110, £75), no longer their cheapest boots (£150, £110); Merrell's likewise (£58, was £120).
    (["Salomon", "Solomon"], "hiking boots", "Salomon", 110.0, "John Lewis"),
    (["Lowa", "LOWA"], "hiking boots", "LOWA", 114.0, "LOWA UK"),
    (["Keen", "Keens", "KEEN"], "hiking boots", "KEEN", 75.0, "KEEN UK"),
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
    # Lines of a brand that writers name as one product, though they come in several versions and heights.
    (["Salomon X Ultra", "Salomon X-Ultra"], "hiking boots", "Salomon X Ultra", 140.0, "John Lewis"),
    (["Salomon Quest"], "hiking boots", "Salomon Quest", 170.0, "John Lewis"),
    (["Scarpa", "SCARPA"], "hiking boots", "Scarpa", 110.0, "SCARPA UK"),
]

# Brands the makers' own pages show selling the type, with no UK price readable (their prices load by script).
# 18 Oct 2026, later the same day: Arc'teryx's UK pages now show prices, so its line has a from price (the Beta Jacket,
# £350) and moved to LINES_SOLD_IN_THE_UK_2 below; it was here because none could be read in the morning.
LINES_WITH_NO_FROM_PRICE = [(["Wrangler", "Wranglers"], "jeans", "Wrangler")]


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
    assert picks["Merrell hiking boots line"].price.text == "From £58 at Merrell UK, checked 18 Oct 2026"
    assert picks["KEEN hiking boots line"].availability.text == "Sold at KEEN UK, checked 18 Oct 2026"


# --- Names shown (18 Oct 2026, the round's second half) ---

def test_astra_blades_are_shown_as_astra_not_as_the_running_shoe_brand_altra():
    """Writers' "astras" are Astra razor blades. The brand-lines list's "Altra" (running shoes) was the only known
    spelling of a brand one letter away, so maker_spelling showed the razor answer's pick as "Altra razor line". Astra's
    own spelling (config, the general builder's section) comes first; Altra's own names are still Altra's."""
    from engine.group_products import maker_spelling

    makers = tuple(sorted({line.brand for line in load_brand_lines() if line.category == "general"}))
    assert maker_spelling("Astra", "general", makers, ()) == "Astra"
    assert maker_spelling("astras", "general", makers, ()) == "Astra"
    assert maker_spelling("Altra", "general", makers, ()) == "Altra"
    assert maker_spelling("altras", "general", makers, ()) == "Altra"


# --- The round's second half (18 Oct 2026): the lines and products the new threads' answers show ---
# Researched on the makers' pages and UK shops on 18 Oct (docs' findings, imported with engine.buyable): from prices of
# full-size products; a specialist shop where no big UK shop sells the type (shaving: The English Shaving Company).
LINES_SOLD_IN_THE_UK_2 = [
    (["Arc'teryx", "Arcteryx"], "rain jacket", "Arc'teryx", 350.0, "Arc'teryx UK"),
    # The cheapest regular price read (a John Lewis clearance in one size, ending the next day, was left aside).
    (["Columbia"], "rain jacket", "Columbia", 135.0, "Ellis Brigham"),
    (["Yeti", "YETI"], "water bottle", "Yeti", 32.0, "Yeti UK"),
    (["Merkur"], "razor", "Merkur", 29.0, "The English Shaving Company"),
    # Blades count as razors in the taxonomy ("razor blades" is a razor keyword): writers' "astras".
    (["Astra", "astras"], "razor", "Astra", 2.5, "The English Shaving Company"),
    (["Milwaukee"], "drill", "Milwaukee", 149.99, "Toolstation"),
    (["EGO", "Ego"], "lawn mower", "Ego", 489.0, "EGO Power+ UK"),
    (["PowerBlock", "Powerblocks"], "dumbbells", "PowerBlock", 199.0, "PowerBlock UK"),
    (["Bowflex"], "dumbbells", "bowflex", 239.99, "Bowflex UK"),
    (["Chicco"], "stroller", "Chicco", 99.9, "Chicco UK"),
    (["Canada Goose"], "winter coat", "Canada Goose", 1050.0, "Canada Goose UK"),
]

PRODUCTS_SOLD_IN_THE_UK_2 = [
    ("Wrangler 13MWZ", "jeans", 58.0, "Zalando"),
    ("Unbranded", "jeans", 83.4, "Jeanstore"),
    ("Gillette Silver Blue", "razor", 2.1, "The English Shaving Company"),
    ("Rockwell 6C", "razor", 55.0, "The English Shaving Company"),
    ("mild Henson al 13", "razor", 81.6, "Henson Shaving UK"),
    ("Makita 18v hammer drill combo", "drill", 179.99, "Toolstation"),
    ("Crispi Summit GTX", "hiking boots", 280.0, "ArdMoor"),
    ("Big Agnes Tiger Wall UL 3 person", "tent", 467.95, "Absolute Snow"),
    ("cybex rotating car seat", "car seat", 214.16, "John Lewis"),
    ("Owlet sock", "baby monitor", 299.99, "Owlet UK"),
]

# Sold only abroad (Noemi, 15 Oct 2026, evening: shown with "Not sold in the UK"). Graco's UK Turn2Me seats are other
# seats under the name; writers' Turn2Me is the US 3-in-1.
SOLD_ABROAD_ONLY_2 = [("Graco Turn2Me", "car seat"), ("Baby Jogger City Turn", "car seat"), ("Hello Baby", "baby monitor"),
                      ("laifen swift", "hair dryer"), ("Dearborn Denim", "jeans"), ("durston x mid 2p", "tent"),
                      ("Takeya originals 32 oz insulated water bottle with spout lid", "water bottle")]


def test_the_second_halfs_lines_have_a_uk_from_price():
    lines = load_brand_lines()
    for names, product_type, brand, amount, shop in LINES_SOLD_IN_THE_UK_2:
        for name in names:
            line = find_brand_line([name], "general", product_type, lines)
            assert line is not None and line.brand == brand and line.sells, (name, product_type)
            assert line.range_page and line.range_page in line.sources, (name, product_type)
            assert (line.from_price, line.from_price_shop) == (amount, shop), (name, product_type)
            assert line.from_price_url in line.sources and line.from_price_checked_on == ROUND, (name, product_type)


def test_the_second_halfs_products_have_a_uk_price():
    prices = load_prices()
    for name, product_type, amount, shop in PRODUCTS_SOLD_IN_THE_UK_2:
        entry = find_availability(name, "general", prices, product_type)
        assert entry is not None and entry.available is True and entry.shop == shop, name
        assert entry.checked_on == ROUND, name
        price = find_price(name, "general", prices, "GBP", product_type)
        assert (price.price if price else None) == amount, name


def test_the_second_halfs_products_sold_abroad_only_say_so():
    prices = load_prices()
    for name, product_type in SOLD_ABROAD_ONLY_2:
        entry = find_availability(name, "general", prices, product_type)
        assert entry is not None and entry.available is False and entry.not_in_uk, name
        assert entry.checked_on == ROUND, name


def test_lululemon_is_shown_as_its_maker_writes_it():
    """Writers' "lulu lemon mats" became a pick of "yoga mat" with the new yoga threads. lululemon writes its name in small
    letters, a style maker_spelling takes only from config (the brand-lines list writes some brands in small letters
    that aren't their makers' style), so config's spelling joins the writers' two words into the maker's one."""
    from engine.group_products import maker_spelling

    makers = tuple(sorted({line.brand for line in load_brand_lines() if line.category == "general"}))
    assert maker_spelling("lulu lemon mats", "general", makers, ()) == "lululemon mats"
    assert maker_spelling("Lululemon", "general", makers, ()) == "lululemon"


# The picks and items the round's 150 new threads brought (research of 18 Oct 2026, later in the day). Brands writers
# name alone or by a line's name became lines with their UK range pages and from prices; the cheapest regular price
# was recorded where the cheapest was one size or colour on clearance (Carhartt's), a cordless kit for a drill line
# asked for as cordless (Bosch), and a UK store's tax-inclusive price over a maker's tax-exclusive one (GORUCK).
LINES_SOLD_IN_THE_UK_3 = [
    (["Travelpro"], "suitcase", "Travelpro", 149.0, "Travelpro UK"),
    (["Away"], "suitcase", "Away", 198.0, "Away"),
    (["Samsonite"], "suitcase", "Samsonite", 145.0, "Samsonite UK"),
    (["timberland pro", "Timberland PRO"], "work boots", "Timberland PRO", 89.99, "ITS"),
    (["SecrID", "Secrid"], "wallet", "Secrid", 34.95, "Secrid"),
    (["Carhartt"], "winter coat", "Carhartt", 120.39, "Workwear Gurus"),
    (["Carhartt"], "jeans", "Carhartt", 64.99, "Charlie's"),
    (["Patagonia"], "winter coat", "Patagonia", 175.0, "Zalando"),
    (["Outdoor Research"], "rain jacket", "Outdoor Research", 99.95, "Outdoor Action"),
    (["North Face"], "rain jacket", "North Face", 119.99, "John Lewis"),
    (["GHD"], "hair straightener", "GHD", 149.0, "John Lewis"),
    (["Perfect Fit"], "dog harness", "Perfect Fit", 35.7, "PerfectFit"),
    (["Ruffwear Front Range"], "dog harness", "Ruffwear Front Range", 49.95, "Ruffwear UK"),
    (["Easy Walk"], "dog harness", "Easy Walk", 14.99, "PetSafe UK"),
    (["jade", "Jade"], "yoga mat", "Jade", 60.0, "JadeYoga UK"),
    (["Liforme"], "yoga mat", "Liforme", 125.0, "Liforme"),
    (["Bosch"], "drill", "Bosch", 87.11, "Bosch DIY UK"),
    (["Western Mountaineering", "WM"], "sleeping bag", "Western Mountaineering", 439.99, "Ultralight Outdoor Gear"),
    (["Enlightened Equipment", "EE"], "sleeping bag", "Enlightened Equipment", 219.99, "Ultralight Outdoor Gear"),
    (["Big Agnes Copper Spur", "Copper Spur"], "tent", "Big Agnes Copper Spur", 522.45, "Absolute Snow"),
    (["MSR Hubba Hubba", "Hubba Hubba"], "tent", "MSR Hubba Hubba", 447.95, "Cotswold Outdoor"),
    (["Nemo Dragonfly"], "tent", "Nemo Dragonfly", 455.95, "Absolute Snow"),
    (["Bugaboo Donkey"], "stroller", "Bugaboo Donkey", 972.0, "Bugaboo UK"),
    (["Silver Cross"], "stroller", "Silver Cross", 195.0, "Silver Cross"),
    (["Thule"], "stroller", "Thule", 314.99, "Thule UK"),
    (["Nanit"], "baby monitor", "Nanit", 179.99, "Nanit UK"),
    (["Owlet sock"], "baby monitor", "Owlet sock", 299.99, "Owlet UK"),
]

PRODUCTS_SOLD_IN_THE_UK_3 = [
    ("Ruffwear Web Master", "dog harness", 84.95, "Ruffwear UK"),
    ("Dyson Supersonic Hair Dryer", "hair dryer", 249.99, "John Lewis"),
    ("NEMO Dagger OSMO 2P", "tent", 474.95, "Absolute Snow"),
    ("Go Ruck GR2", "backpack", 375.0, "GORUCK UK"),
    ("GoRuck GR1 backpack", "backpack", 395.0, "GORUCK UK"),
    ("Canada Goose mid length down parka", "winter coat", 1095.0, "Canada Goose UK"),
    ("Pelican Air 1535", "suitcase", 308.54, "Peli UK"),
    ("Ridge Wallet", "wallet", 65.0, "Ridge UK"),
    ("Hanwag Berglers", "hiking boots", 296.0, "Zalando"),
    ("Loreal Steampod hair straightener", "hair straightener", 320.29, "Sally Beauty"),
    # Sold in the UK by marketplace sellers only, at over twice the maker's US price: no price recorded.
    ("Blue-9 Balance Harness", "dog harness", None, "Amazon UK"),
]

SOLD_ABROAD_ONLY_3 = [("Graco Extend2Fit", "car seat"), ("Nuna Rava", "car seat"), ("Cybex Callisto", "car seat"),
                      ("Evenflo pivot travel system", "stroller"), ("2 Hounds no pull harness", "dog harness"),
                      ('BaByliss nano titanium 1" flat iron', "hair straightener")]

# Lines sold abroad only: a price-list entry under the brand and type saying so, and a brand-lines entry with the maker's
# range page abroad, so a brand writers name alone can still be shown, with "Not sold in the UK".
LINES_SOLD_ABROAD_3 = [(["Red Wing"], "work boots"), (["Durston X-Mid", "X-Mid"], "tent"), (["Tarptent"], "tent"),
                       (["Cumulus"], "sleeping bag"), (["K9 Ballistics"], "dog bed"), (["Tortuga"], "backpack"),
                       (["BOB"], "stroller")]


def test_the_new_threads_lines_have_a_uk_from_price():
    lines = load_brand_lines()
    for names, product_type, brand, amount, shop in LINES_SOLD_IN_THE_UK_3:
        for name in names:
            line = find_brand_line([name], "general", product_type, lines)
            assert line is not None and line.brand == brand and line.sells, (name, product_type)
            assert line.range_page and line.range_page in line.sources, (name, product_type)
            assert (line.from_price, line.from_price_shop) == (amount, shop), (name, product_type)
            assert line.from_price_url in line.sources and line.from_price_checked_on == ROUND, (name, product_type)


def test_the_new_threads_products_have_a_uk_price():
    prices = load_prices()
    for name, product_type, amount, shop in PRODUCTS_SOLD_IN_THE_UK_3:
        entry = find_availability(name, "general", prices, product_type)
        assert entry is not None and entry.available is True and entry.shop == shop, name
        assert entry.checked_on == ROUND, name
        price = find_price(name, "general", prices, "GBP", product_type)
        assert (price.price if price else None) == amount, name


def test_the_new_threads_products_and_lines_sold_abroad_say_so():
    prices, lines = load_prices(), load_brand_lines()
    for name, product_type in SOLD_ABROAD_ONLY_3:
        entry = find_availability(name, "general", prices, product_type)
        assert entry is not None and entry.available is False and entry.not_in_uk, name
    for names, product_type in LINES_SOLD_ABROAD_3:
        line = find_brand_line(names, "general", product_type, lines)
        assert line is not None and line.sells and line.range_page in line.sources, names
        entry = find_brand_entry(names, "general", prices, product_type.split(), product_type)
        assert entry is not None and entry.available is False and entry.not_in_uk, names


def test_brooklinen_is_not_shown_as_the_running_shoe_brand_brooks():
    """The skip list of "bed sheets that stay cool" showed writers' "Brook Linen" as "Brooks Linen" once Brooks (running
    shoes) joined the brand-lines list this round: one more slip between two makers' names, fixed as Astra's was."""
    from engine.group_products import maker_spelling

    makers = tuple(sorted({line.brand for line in load_brand_lines() if line.category == "general"}))
    assert maker_spelling("Brook Linen", "general", makers, ()) == "Brooklinen"
    assert maker_spelling("Brooks", "general", makers, ()) == "Brooks"


# --- The finishing round (18 Oct 2026, afternoon): prices for the picks that still had none, and the sleeping bag lines ---
# The last builder to work on the round read the picks the answers still showed with "Price not checked yet" or
# "Availability not checked yet" and researched each on UK pages (docs' findings, imported with engine.buyable). A line's
# from price is the cheapest product read on a page: Bellroy's is its £39 Mag Wallet (Bellroy EU's own listing on Amazon UK,
# the £25 listing of another edition having a hidden buy-box price), Oral-B's a sale price at an online pharmacy (the
# big shops refused to be read), Kirkland's the smallest bed at Costco UK, Big Agnes's the two-person Blacktail.
LINES_SOLD_IN_THE_UK_4 = [
    (["Bellroy"], "wallet", "Bellroy", 39.0, "Amazon UK"),
    (["UPPAbaby Cruz"], "stroller", "UPPAbaby Cruz", 749.99, "John Lewis"),
    (["Oral-B", "Oral B", "Oral-b"], "electric toothbrush", "Oral-B", 21.0, "LloydsPharmacy"),
    (["Kirkland"], "dog bed", "Kirkland", 27.99, "Costco UK"),
    (["Big Agnes"], "tent", "Big Agnes", 224.95, "Absolute Snow"),
]

PRODUCTS_SOLD_IN_THE_UK_4 = [
    ("Rockwell 6S", "razor", 92.0, "Rockwell Razors UK"),
    ("Osprey Daylite Expandable 26+6", "backpack", 78.26, "Alpinetrek"),
    # Garmin's Forerunner 965 is still sold new by Garmin UK (under its "Previous Models"); writers just say "965".
    ("Garmin Forerunner 965", "sports watch", 499.99, "Garmin UK"),
    ("965", "sports watch", 499.99, "Garmin UK"),
    # The UK sells the Boondock as the Ultralight safety boot (ITS, authorised stockist); the classic US 6-inch Boondock
    # writers name was not found on UK pages, so the entry's note says it is the UK version.
    ("Timberland PRO Boondock", "work boots", 169.99, "ITS"),
]


def test_the_finishing_rounds_lines_have_a_uk_from_price():
    lines, prices = load_brand_lines(), load_prices()
    for names, product_type, brand, amount, shop in LINES_SOLD_IN_THE_UK_4:
        for name in names:
            line = find_brand_line([name], "general", product_type, lines)
            assert line is not None and line.brand == brand and line.sells, (name, product_type)
            assert line.range_page and line.range_page in line.sources, (name, product_type)
            assert (line.from_price, line.from_price_shop) == (amount, shop), (name, product_type)
            assert line.from_price_url in line.sources and line.from_price_checked_on == ROUND, (name, product_type)
        entry = find_brand_entry(names, "general", prices, product_type.split(), product_type)
        assert entry is not None and entry.available is True and not entry.not_in_uk, (brand, product_type)


def test_the_finishing_rounds_products_have_a_uk_price():
    prices = load_prices()
    for name, product_type, amount, shop in PRODUCTS_SOLD_IN_THE_UK_4:
        entry = find_availability(name, "general", prices, product_type)
        assert entry is not None and entry.available is True and entry.shop == shop, name
        assert entry.checked_on == ROUND, name
        price = find_price(name, "general", prices, "GBP", product_type)
        assert (price.price if price else None) == amount, name


def test_feathered_friends_is_a_sleeping_bag_line_sold_abroad_only():
    """Writers name Feathered Friends ("FF") for its down sleeping bags; it sells from its own US store and no UK seller
    was found, so its line is shown with "Not sold in the UK" (Noemi, 15 Oct 2026, evening)."""
    lines, prices = load_brand_lines(), load_prices()
    for name in ("Feathered Friends", "FF"):
        line = find_brand_line([name], "general", "sleeping bag", lines)
        assert line is not None and line.brand == "Feathered Friends" and line.sells, name
        assert "featheredfriends.com" in line.range_page and line.range_page in line.sources, name
        assert line.from_price is None, name
    entry = find_brand_entry(["Feathered Friends"], "general", prices, ["sleeping", "bag"], "sleeping bag")
    assert entry is not None and entry.available is False and entry.not_in_uk and entry.checked_on == ROUND


BAG_PRAISE = "My {brand} bag has kept me warm below freezing for {years} winters, and it still lofts like new."


def sleeping_bags_library(tmp_path: Path) -> Path:
    """Two sleeping bag threads in which five writers praise Feathered Friends, three by the initials "FF" and two by the
    full name, and one writer each names a model (a Lark YF, a Flicker): one brand written two ways, whose name fits
    several products (module 4 marks it loose), so the brand's line should be one pick, whichever way a writer wrote it."""
    def thread(thread_id: str, title: str, praised: list[tuple[str, str, int]]) -> dict:
        url = f"https://www.reddit.com/r/Ultralight/comments/{thread_id}/x/"
        comments = [make_comment(cid, thread_id=thread_id, body=BAG_PRAISE.format(brand=brand, years=years),
                                 url=f"https://www.reddit.com/r/Ultralight/comments/{thread_id}/comment/{cid}/")
                    for cid, brand, years in praised]
        return make_thread(id=thread_id, community="Ultralight", category="general", title=title,
                           body="Mine is worn out.", url=url, comments=comments)

    threads = {
        "1bag001": thread("1bag001", "Winter sleeping bag advice", [
            ("g1aaaa", "FF", 5), ("g1bbbb", "Feathered Friends", 3), ("g1cccc", "FF", 4),
            ("g1dddd", "Feathered Friends Lark YF", 2)]),
        "1bag002": thread("1bag002", "Which sleeping bag lasts?", [
            ("g2aaaa", "Feathered Friends", 6), ("g2bbbb", "FF", 2), ("g2cccc", "FF Flicker 20 degree", 1)]),
    }
    root = write_gold(tmp_path / "library", list(threads.values()), voices=None, mentions=None)
    (root / "extracted").mkdir()
    for thread_id, data in threads.items():
        mentions = []
        for c in data["comments"]:
            brand = c["body"].split(" bag has ")[0].removeprefix("My ")
            mentions.append({"comment_id": c["id"], "product": brand, "category": "general",
                             "product_type": "sleeping bag", "stance": "recommend", "evidence": "long-term use",
                             "evidence_tags": ["long-term use"], "quote": c["body"]})
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v15", "extracted_at": "2026-10-18T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions}), encoding="utf-8")
    return root


def test_feathered_friends_written_two_ways_is_one_line_shown_as_not_sold_in_the_uk(tmp_path):
    result = answer_request("sleeping bag", library_dir=sleeping_bags_library(tmp_path), prices=load_prices(),
                            product_facts=load_product_facts(), brand_lines=load_brand_lines(),
                            product_pages=load_product_pages(), today=ROUND, more_threads=None)
    # One pick, whichever way the writers wrote the brand (shown as the brand, or as its line when module 4 finds the
    # name doesn't say the type), not sold in the UK, with the maker's range page.
    assert len(result.answer.picks) == 1, [pick.name for pick in result.answer.picks]
    pick = result.answer.picks[0]
    assert pick.name.startswith("Feathered Friends"), pick.name
    assert pick.availability.text == "Not sold in the UK, checked 18 Oct 2026"
    page = pick.range or pick.link
    assert page is not None and "featheredfriends.com" in page.url
