"""The tech data round of 25 Oct 2026 (branch data-tech2; Claude's technical calls inside Noemi's decision (e) of
19 Oct 2026, "phone and webcam communities may be added"; reported to her).

1. Phone and webcam communities. The three phone communities Noemi's decision names (r/iphone, r/GooglePixel and
   r/samsung) and one webcam community are decided general subreddits, and the phone and webcam types search them (a
   thread is read only from a decided subreddit, and a request's subreddits must be among its category's). The webcam
   community is r/Twitch: checked on Arctic Shift on 25 Oct 2026, it exists, posts every day, and had about 25
   "which webcam" threads with 10 or more comments in 2024-2026 (r/webcam, the obvious name, is an adult-content
   community whose last post is from 2021 and is never added; r/WorkFromHome had two weak threads in the same years).
2. The prices, availability and product pages of the picks the 32 new threads (webcams, 4k monitors for work, smartwatches
   for fitness, phones with a good camera) bring, researched on 25 Oct 2026 on makers' UK pages and big UK shops, under the
   names the answers show them (Noemi's rule: the best pick whatever country sells it, with a right note; a model its
   maker no longer sells is left out and named).
"""

import json
from pathlib import Path

import pytest

from engine.brand_lines import find_brand_line, load_brand_lines
from engine.config import SUBREDDITS
from engine.prices import counts_as_sold, find_availability, find_price, load_prices
from engine.product_pages import find_page, load_product_pages
from engine.query import parse_query

PRODUCT_TYPES = Path(__file__).resolve().parents[1] / "data" / "product_types.json"
PHONE_COMMUNITIES = ("iphone", "GooglePixel", "samsung")
WEBCAM_COMMUNITY = "Twitch"


def type_communities(name: str) -> list[str]:
    types = json.loads(PRODUCT_TYPES.read_text(encoding="utf-8"))["types"]
    return next(t["subreddits"] for t in types if t["name"] == name)


def test_the_phone_communities_are_decided_general_subreddits():
    assert set(PHONE_COMMUNITIES) <= set(SUBREDDITS["general"])


def test_the_phone_type_searches_them_after_its_broad_communities():
    communities = type_communities("phone")
    assert set(PHONE_COMMUNITIES) <= set(communities)
    assert communities[:3] == ["PickAnAndroidForMe", "BuyItForLife", "Frugal"]  # the broad ones stay first


def test_a_phone_request_is_searched_in_them_and_stays_inside_the_decided_ones():
    query = parse_query("a phone with a good camera")
    assert query.product_type == "phone"
    assert set(PHONE_COMMUNITIES) <= set(query.subreddits)
    assert set(query.subreddits) <= set(SUBREDDITS["general"])


def test_the_webcam_community_is_a_decided_general_subreddit_and_the_webcam_type_searches_it():
    assert WEBCAM_COMMUNITY in SUBREDDITS["general"]
    communities = type_communities("webcam")
    assert WEBCAM_COMMUNITY in communities
    assert communities[:2] == ["BuyItForLife", "laptops"]  # the broad ones stay first


def test_the_adult_webcam_community_is_never_a_decided_subreddit():
    for subs in SUBREDDITS.values():
        assert "webcam" not in {s.lower() for s in subs}
    for t in json.loads(PRODUCT_TYPES.read_text(encoding="utf-8"))["types"]:
        assert "webcam" not in {s.lower() for s in t.get("subreddits", [])}


def test_a_webcam_request_is_searched_in_it_and_stays_inside_the_decided_ones():
    query = parse_query("webcam for video calls")
    assert query.product_type == "webcam"
    assert WEBCAM_COMMUNITY in query.subreddits
    assert set(query.subreddits) <= set(SUBREDDITS["general"])


# --- 2. Prices, availability and pages (25 Oct 2026) ---

# (name as the answer shows it, product type, price in pounds, shop as shown)
PRICED = [
    ("Logitech C920", "webcam", 84.99, "Logitech UK"),
    ("Logitech Streamcam", "webcam", 139.99, "Logitech UK"),
    ("Razor Kiyo V2", "webcam", 149.99, "Razer UK"),  # a writers' misspelling finds Razer's own entry
    ("Obsbot meet 2 4K", "webcam", 128.99, "Scan"),
    ("Dell U3225QE", "monitor", 853.2, "Dell UK"),
    ("M27up", "monitor", 298.99, "Scan"),  # writers' bare model: the entry's other name
    ("Venu 4", "smartwatch", 379.0, "John Lewis"),
    ("Garmin Venu 3S", "smartwatch", 379.99, "John Lewis"),
]

# Sold in the UK now, but no pound price read on a page (name, type, shop as shown).
SOLD_WITHOUT_PRICE = [
    ("Anker C200", "webcam", "Amazon UK"),
    ("OBSBOT Tiny 2", "webcam", "OBSBOT"),
    ("obs tiny 2", "webcam", "OBSBOT"),
    ("Gigabyte M27UA", "monitor", "Amazon UK"),
    ("Huawei Watch GT 7 Pro", "smartwatch", "Amazon UK"),
]

# Models their makers no longer sell new: left out of answers and named.
NO_LONGER_SOLD = [
    ("Razer Kiyo pro", "webcam"),
    ("Elgato facecam pro", "webcam"),
    ("iPhone 16 Pro", "phone"),
    ("Galaxy S23 Ultra", "phone"),
    ("iPhone 5S", "phone"),
    ("iPhone XR", "phone"),
    ("Google Pixel 3 XL", "phone"),
    ("Pixel 2XL", "phone"),
]

# (brand as the line's name starts, product type, from price in pounds, shop as shown)
LINES = [
    ("Apple Watch", "smartwatch", 219.0, "Apple UK"),
    ("Samsung", "phone", 169.0, "John Lewis"),
]


@pytest.mark.parametrize("name, product_type, amount, shop", PRICED)
def test_a_researched_pick_finds_its_uk_price_and_is_sold(name, product_type, amount, shop):
    prices = load_prices()
    price = find_price(name, "general", prices, product_type=product_type)
    assert price is not None and (price.price, price.currency, price.shop) == (amount, "GBP", shop)
    assert counts_as_sold(find_availability(name, "general", prices, product_type=product_type)) is True
    assert find_page([name], "general", product_type, load_product_pages()) is not None


@pytest.mark.parametrize("name, product_type, shop", SOLD_WITHOUT_PRICE)
def test_a_pick_sold_in_the_uk_without_a_price_read_is_known_to_be_sold(name, product_type, shop):
    prices = load_prices()
    entry = find_availability(name, "general", prices, product_type=product_type)
    assert entry is not None and counts_as_sold(entry) is True and entry.shop == shop and not entry.not_in_uk
    assert find_price(name, "general", prices, product_type=product_type) is None  # never a price read in dollars
    assert find_page([name], "general", product_type, load_product_pages()) is not None


@pytest.mark.parametrize("name, product_type", NO_LONGER_SOLD)
def test_a_model_its_maker_no_longer_sells_is_known_to_be_gone(name, product_type):
    entry = find_availability(name, "general", load_prices(), product_type=product_type)
    assert entry is not None and entry.available is False and not entry.not_in_uk
    assert counts_as_sold(entry) is False


@pytest.mark.parametrize("name, product_type", NO_LONGER_SOLD[:5])
def test_a_model_its_maker_no_longer_sells_is_never_linked(name, product_type):
    assert find_page([name], "general", product_type, load_product_pages()) is None


@pytest.mark.parametrize("brand, product_type, amount, shop", LINES)
def test_a_researched_brand_line_finds_its_from_price(brand, product_type, amount, shop):
    line = find_brand_line([brand], "general", product_type, load_brand_lines())
    assert line is not None and line.sells
    assert (line.from_price, line.from_price_shop) == (amount, shop)
    assert line.from_price_url in line.sources and line.from_price_checked_on is not None
    assert line.range_page is not None


def test_a_pick_whose_uk_availability_conflicts_is_left_without_an_entry():
    # Two UK shops say the Innocn 32M2V and the Pixel 8a are gone or not sold, others still list them: the lists say
    # nothing about where they are sold rather than a wrong "not sold in the UK" (the page may still be linked).
    prices = load_prices()
    assert find_availability("Innocn 32M2V", "general", prices, product_type="monitor") is None
    assert find_page(["Innocn 32M2V"], "general", "monitor", load_product_pages()) is not None
