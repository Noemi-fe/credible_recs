"""Finding a product's entries in a long list without comparing its name with every entry (15 Oct 2026).

Researchers' findings grow the price list from about 160 entries to over 1,000, and the product pages list from none to
about 800; an answer looks up every product it ranks, so comparing each name with every entry would make a cold answer
seconds slower. An index of the entries' words finds the few that could be the same product, and module 4's own rule
(engine.match_products.same_product) decides among them, so what is found is exactly what comparing every entry finds.
Every name here is a real product name, or a writer's way of writing one; the entries are made up.
"""

from datetime import date

import pytest

from engine.match_products import known_aliases, same_product
from engine.name_index import NameIndex
from engine.prices import Price, entries_for
from engine.product_pages import ProductPage, find_page

NAMES = [
    "Zojirushi kettle", "Fellow Stagg EKG", "Fellow Stagg EKG Electric Pour-Over Kettle", "Breville Smart Grinder Pro",
    "KitchenAid Artisan stand mixer", "Black and Decker kettle", "Le Creuset Signature Dutch oven",
    "Lodge cast iron skillet", "1Zpresso K Plus", "Comandante C40", "Timemore C2", "Timemore C2 Max", "Baratza Encore",
    "Soon Jung 2x Barrier Intensive Cream", "CeraVe Hydrating Cleanser", "The Ordinary Niacinamide 10% + Zinc 1%",
    "Paula's Choice 2% BHA Liquid Exfoliant", "La Roche-Posay Effaclar Duo", "MBPs from late 2010-2011", "Legion Y540",
    "ASUS ROG laptop", "Dell Latitude 5300 13.3 Touchscreen", "Sony WH-1000XM4", "Bose QC45", "Wüsthof Classic chef knife",
]
ASKED = [
    "Zojurushi kettle",  # a slip
    "Sage Smart Grinder Pro",  # the UK name
    "SGP",  # a known short name
    "Kitchen Aid Artisan stand mixer",  # written apart
    "Black Decker kettle",  # without its "and"
    "Fellow Stagg", "Stagg EKG", "fellow stagg ekg", "Le Creuset Dutch oven", "Lodge", "1Z K plus", "C40",
    "Timemore C2", "Timemore C3", "soonjung 2x barrier intensive cream", "Cerave hydrating cleanser",
    "TO niacinamide", "Paula's Choice 2% BHA", "LRP Effaclar Duo", "MBPs from late 2010-2011", "Legion Y540", "ROG laptop",
    "Dell Latitude 5300", "Sony WH1000XM4", "Bose QC 45", "Wusthof Classic chef knife", "the one", "",
]


def price(product: str, category: str = "kitchen") -> Price:
    return Price(product=product, category=category, price=10.0, currency="GBP", shop="Made-up Shop",
                 url="https://shop.example/p", checked_on=date(2026, 10, 15), available=True)


@pytest.mark.parametrize("category", ["kitchen", "skincare", "general"])
def test_the_index_finds_exactly_what_comparing_every_entry_finds(category):
    entries = [price(name, category) for name in NAMES]
    aliases = known_aliases().get(category, {})
    index = NameIndex([[entry.product] for entry in entries], aliases)
    for asked in ASKED:
        every = [i for i, entry in enumerate(entries) if same_product(entry.product, asked, aliases)]
        assert [i for i in index.candidates(asked) if same_product(entries[i].product, asked, aliases)] == every, asked


def test_the_price_lists_lookups_are_unchanged_by_the_index():
    entries = [price(name) for name in NAMES] + [price(name, "skincare") for name in NAMES]
    for asked in ASKED:
        aliases = known_aliases().get("kitchen", {})
        every = [p for p in entries if p.category == "kitchen"
                 and any(same_product(known, asked, aliases) for known in [p.product, *p.also_called])]
        assert entries_for(asked, "kitchen", entries) == every, asked


def test_another_name_an_entry_goes_by_is_indexed_too():
    entries = [price("Cuisinart CPK-17P1 PerfecTemp Cordless Electric Kettle").model_copy(
        update={"also_called": ["Cuisinart CPK-17 PerfecTemp"]})]
    assert entries_for("Cuisinart CPK-17 PerfecTemp", "kitchen", entries) == entries


def test_the_pages_lookups_use_it_too():
    pages = [ProductPage(product=name, category="kitchen", page="https://shop.example/p", shop="Made-up Shop",
                         sources=["https://shop.example/p"], checked_on=date(2026, 10, 15)) for name in NAMES]
    assert find_page(["Zojurushi kettle"], "kitchen", None, pages).product == "Zojirushi kettle"
    assert find_page(["Sage Smart Grinder Pro"], "kitchen", None, pages).product == "Breville Smart Grinder Pro"
    assert find_page(["Timemore C3"], "kitchen", None, pages) is None
