"""The tech and home picks' prices and availability (the converge round of 17 Oct 2026, ws-data-tech; CLAUDE.md's
UK-availability follow-up for general picks): each researched product or brand line, under the name the answers show
it, finds its entry in the committed lists the way answers find one (engine.prices.find_price and find_availability,
engine.brand_lines.find_brand_line), so a researched price or "Not sold in the UK" is never lost to a name that the
matcher doesn't join. Noemi's rule: the best pick whatever country it is sold in, with a note, never left out for it;
a discontinued model is left out and named.

These read data/prices.json and data/brand_lines.json, as the tests that check the committed lists load do; every
price here was read on a UK shop's or maker's page on the day its entry gives.
"""

import pytest

from engine.brand_lines import find_brand_line, load_brand_lines
from engine.prices import counts_as_sold, find_availability, find_price, load_prices

# (name as the answer shows it, product type, price in pounds, shop as shown)
PRODUCTS = [
    ("UE Boom", "bluetooth speaker", 129.99, "John Lewis"),
    ("Herman Miller Aeron", "office chair", 1219.0, "Herman Miller"),
    ("Numatic Henry", "vacuum cleaner", 129.99, "Numatic"),
    # Headphones, under writers' own names (18 Oct 2026): the entries carry them as also_called.
    ("Sennheiser HD600", "headphones", 255.0, "Thomann"),
    ("Sony Mdr-7506", "headphones", 83.0, "Thomann"),
    ("Sony xm4", "headphones", 219.99, "John Lewis"),
    ("XM5s", "headphones", 199.0, "John Lewis"),
    ("Sony XM6", "headphones", 349.0, "John Lewis"),
    ("QC Ultra", "headphones", 399.95, "Bose"),
    ("AirPod Max", "headphones", 499.0, "John Lewis"),
    ("Momentum 4s", "headphones", 199.0, "John Lewis"),
    ("Anker Soundcore Q30s", "headphones", 44.99, "soundcore"),
    ("Shokz open run", "headphones", 129.95, "John Lewis"),
    # Running and gym earbuds (18 Oct 2026), under the names writers use.
    ("Powerbeats Pro 2", "earbuds", 179.0, "John Lewis"),
    ("Soundcore x20’s", "earbuds", 89.99, "soundcore"),
    ("soundcore sport x20", "earbuds", 89.99, "soundcore"),
    ("Shokz open fit 2 plus", "earbuds", 179.0, "John Lewis"),
    ("Shokz Open Fit Air", "earbuds", 94.0, "John Lewis"),
    ("Openrun Mini", "headphones", 129.95, "John Lewis"),
    ("Sony WF-1000XM5", "earbuds", 179.99, "John Lewis"),
]

# (brand as the line's name starts, product type, from price in pounds, shop as shown)
LINES = [
    ("Kindle", "e-reader", 134.99, "John Lewis"),
    ("Paperwhite", "e-reader", 184.99, "John Lewis"),
    ("Sony", "tv", 291.90, "John Lewis"),
    ("LG", "tv", 159.0, "John Lewis"),
    ("Samsung", "tv", 249.0, "John Lewis"),
    ("JBL", "bluetooth speaker", 39.99, "John Lewis"),
    ("Bose", "bluetooth speaker", 104.99, "John Lewis"),
    ("Anker", "power bank", 24.99, "Anker"),
    ("Logitech", "mouse", 9.99, "John Lewis"),
    ("MacBook Air", "laptop", 1299.0, "John Lewis"),
    ("Eufy", "robot vacuum", 599.0, "John Lewis"),
    ("Shark", "robot vacuum", 269.99, "John Lewis"),
    ("Roomba", "robot vacuum", 229.0, "iRobot"),
    ("UniFi", "wifi router", 65.0, "Ubiquiti UK Store"),
    ("Keychron", "keyboard", 49.99, "Keychron UK"),
    ("Bose", "headphones", 189.95, "Bose"),
    # A line of a brand with an entry of its own (18 Oct 2026): "Bose QuietComfort headphones line".
    ("Bose QuietComfort", "headphones", 189.95, "Bose"),
    ("Bose Quiet Comfort", "headphones", 189.95, "Bose"),
]

# Sold in the UK, a range rather than one model, so no single price (name as the answer shows it, type, shop as shown).
SOLD = [
    ("Anker Soundcore", "bluetooth speaker", "soundcore"),
    ("Razer Death Adder", "mouse", "Razer"),
]

# Discontinued models: left out of answers and named (Noemi, 15 Oct 2026). Some had been marked "not sold in the UK"
# on 15 Oct though their own notes said they are no longer made: the newer check says so.
DISCONTINUED = [
    ("Roomba i7", "robot vacuum"),
    ("Roborock S4", "robot vacuum"),
    ("Roborock S5 MAX", "robot vacuum"),
    ("Neato D5", "robot vacuum"),
    ("Jabra elite wireless 65t", "earbuds"),
    ("Apple AirPods (1st generation)", "earbuds"),
    ("iPhone 11", "phone"),
    ("Legion Y540", "laptop"),
    ("Dell Latitude 5300 13.3 Touchscreen", "laptop"),
    ("TP-Link Deco M5", "wifi router"),
    ("QC45s", "headphones"),
    ("Bose QC35 II", "headphones"),
    ("Bose qc35", "headphones"),
    ("Bose qc25s", "headphones"),
    ("Bose 700", "headphones"),
    # Earbuds whose makers no longer sell them (18 Oct 2026): their own pages now show a successor or support only.
    ("Beats Fit Pro", "earbuds"),
    ("Samsung Galaxy Buds 2", "earbuds"),
    ("Jabra Elite 8 Active", "earbuds"),
    ("Jabra Elite Active 8", "earbuds"),
]

# Sold abroad only: they stay in answers with "Not sold in the UK" (Noemi, 15 Oct 2026, evening; 16 Oct, decision 4).
ABROAD = [
    ("Vizio TV", "tv"),
    ("Raycon Everyday Earbuds", "earbuds"),
]


@pytest.mark.parametrize("name, product_type, amount, shop", PRODUCTS)
def test_a_researched_product_finds_its_uk_price_and_is_sold(name, product_type, amount, shop):
    prices = load_prices()
    price = find_price(name, "general", prices, product_type=product_type)
    assert price is not None and (price.price, price.currency, price.shop) == (amount, "GBP", shop)
    assert counts_as_sold(find_availability(name, "general", prices, product_type=product_type)) is True


@pytest.mark.parametrize("brand, product_type, amount, shop", LINES)
def test_a_researched_brand_line_finds_its_from_price(brand, product_type, amount, shop):
    line = find_brand_line([brand], "general", product_type, load_brand_lines())
    assert line is not None and line.sells
    assert (line.from_price, line.from_price_shop) == (amount, shop)
    assert line.from_price_url in line.sources and line.from_price_checked_on is not None


@pytest.mark.parametrize("name, product_type", DISCONTINUED)
def test_a_discontinued_model_is_known_to_be_no_longer_sold(name, product_type):
    entry = find_availability(name, "general", load_prices(), product_type=product_type)
    assert entry is not None and entry.available is False and not entry.not_in_uk
    assert counts_as_sold(entry) is False


@pytest.mark.parametrize("name, product_type", ABROAD)
def test_a_product_sold_only_abroad_stays_with_its_note(name, product_type):
    entry = find_availability(name, "general", load_prices(), product_type=product_type)
    assert entry is not None and entry.available is False and entry.not_in_uk
    assert counts_as_sold(entry) is True


@pytest.mark.parametrize("name, product_type, shop", SOLD)
def test_a_researched_range_is_known_to_be_sold_where(name, product_type, shop):
    entry = find_availability(name, "general", load_prices(), product_type=product_type)
    assert entry is not None and counts_as_sold(entry) is True and entry.shop == shop and not entry.not_in_uk
