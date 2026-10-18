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
]

# Discontinued models: left out of answers and named (Noemi, 15 Oct 2026).
DISCONTINUED = [
    ("Roomba i7", "robot vacuum"),
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
