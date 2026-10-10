"""Decision 11 (Noemi, 9 Oct 2026), budgets: a list of current prices, each with its shop and date.

Every price, shop and link here is made up. No test reads data/prices.json except the one that checks the committed
file is valid and starts empty.
"""

import json
import typing
from datetime import date, timedelta

import pytest

from engine import config
from engine.prices import DEFAULT_PRICES, Price, PriceError, check_price, find_price, load_prices
from engine.query import Budget

TODAY = date(2026, 10, 9)


def price(product: str = "Zojirushi kettle", amount: float = 120.0, currency: str = "GBP", category: str = "kitchen",
          shop: str = "Made-up Kitchen Shop", url: str = "https://shop.example/zojirushi-kettle",
          checked_on: date = TODAY) -> Price:
    return Price(product=product, category=category, price=amount, currency=currency, shop=shop, url=url,
                 checked_on=checked_on)


def write_prices(tmp_path, entries: list[dict]):
    path = tmp_path / "prices.json"
    path.write_text(json.dumps({"prices": entries}), encoding="utf-8")
    return path


def entry(**overrides) -> dict:
    data = {"product": "Zojirushi kettle", "category": "kitchen", "price": 120.0, "currency": "GBP",
            "shop": "Made-up Kitchen Shop", "url": "https://shop.example/zojirushi-kettle", "checked_on": "2026-10-09"}
    data.update(overrides)
    return data


# --- The file ---

def test_the_committed_price_list_is_valid():
    # Changed 9 Oct 2026: the list started empty and now holds prices checked on each shop's own page. Every entry
    # must load (load_prices refuses a bad shop link or date), link to the shop over https and be in pounds.
    assert DEFAULT_PRICES.name == "prices.json" and DEFAULT_PRICES.parent.name == "data"
    raw = json.loads(DEFAULT_PRICES.read_text(encoding="utf-8"))["prices"]
    loaded = load_prices()
    assert len(loaded) == len(raw)
    assert all(p.url.startswith("https://") and p.currency == "GBP" and p.checked_on for p in loaded)


def test_a_price_list_loads_with_its_shop_link_and_date(tmp_path):
    [loaded] = load_prices(write_prices(tmp_path, [entry()]))
    assert loaded.product == "Zojirushi kettle" and loaded.price == 120.0 and loaded.currency == "GBP"
    assert loaded.shop == "Made-up Kitchen Shop" and loaded.url == "https://shop.example/zojirushi-kettle"
    assert loaded.checked_on == TODAY


@pytest.mark.parametrize("bad", [
    {"url": "http://shop.example/kettle"},  # https only
    {"url": "HTTPS://shop.example/kettle"},  # written the one way the answer checks again
    {"url": "javascript:alert(1)"},
    {"url": "https://"},  # no shop
    {"url": "https://someone:secret@shop.example/kettle"},  # a name and password in a link: never
    {"url": "https://shop.example/a kettle"},  # spaces
    {"currency": "JPY"},  # a request can only name GBP, EUR or USD
    {"category": "other"},
    {"price": 0},
    {"price": -5},
    {"shop": ""},
    {"product": ""},
    {"checked_on": "9 Oct 2026"},
    {"colour": "red"},  # an unknown field is a typo, never ignored
])
def test_a_malformed_entry_is_refused_naming_where_it_is(tmp_path, bad):
    with pytest.raises(PriceError) as refused:
        load_prices(write_prices(tmp_path, [entry(), entry(**bad)]))
    assert "entry 2" in str(refused.value)


def test_a_file_without_a_price_list_is_refused(tmp_path):
    path = tmp_path / "prices.json"
    path.write_text(json.dumps({"price": []}), encoding="utf-8")
    with pytest.raises(PriceError):
        load_prices(path)


def test_the_currencies_are_the_ones_a_request_can_name():
    allowed = typing.get_args(Price.model_fields["currency"].annotation)
    for currency in allowed:
        Budget(max=10, currency=currency)  # every price currency can be a budget's
    assert set(allowed) == {"GBP", "EUR", "USD"}


# --- Finding a product's price ---

def test_a_product_finds_its_price_by_name_within_its_category():
    prices = [price("Zojirushi kettle"), price("Zojirushi kettle", category="skincare", amount=5.0)]
    found = find_price("zojirushi kettle", "kitchen", prices)
    assert found is not None and found.category == "kitchen" and found.price == 120.0
    assert find_price("Fellow Stagg EKG", "kitchen", prices) is None


def test_the_uk_name_finds_the_us_name_and_back():
    # Sage is Breville's UK and EU brand: the alias list makes them one product.
    prices = [price("Sage Smart Grinder Pro", amount=199.0)]
    assert find_price("Breville Smart Grinder Pro", "kitchen", prices).price == 199.0
    assert find_price("Sage Smart Grinder Pro", "kitchen", [price("Breville Smart Grinder Pro")]) is not None


def test_when_several_prices_fit_the_exact_name_then_the_currency_then_the_newest_then_the_cheapest_wins():
    longer = price("Zojirushi kettle with gooseneck spout", amount=50.0)
    euro = price(amount=90.0, currency="EUR")
    old = price(amount=80.0, checked_on=TODAY - timedelta(days=10))
    new_dear, new_cheap = price(amount=130.0), price(amount=110.0)
    assert find_price("Zojirushi kettle", "kitchen", [longer, new_dear]).price == 130.0  # exact words first
    assert find_price("Zojirushi kettle", "kitchen", [euro, old], currency="GBP").price == 80.0
    assert find_price("Zojirushi kettle", "kitchen", [old, new_dear, new_cheap]).price == 110.0


# --- Checking a price against the request's budget ---

UNDER_100 = Budget(max=100, currency="GBP")


def test_without_a_budget_there_is_nothing_to_check():
    assert check_price(price(), None, TODAY).status == "no budget"
    assert check_price(None, None, TODAY).status == "no budget"
    # Only a budget with a max and a currency can be checked: module 1 never guesses a currency.
    assert check_price(price(), Budget(max=100), TODAY).status == "no budget"
    assert check_price(price(), Budget(min=50, currency="GBP"), TODAY).status == "no budget"


def test_a_known_price_within_the_budget_is_within():
    check = check_price(price(amount=99.99), UNDER_100, TODAY)
    assert check.status == "within" and check.budget == UNDER_100
    assert check_price(price(amount=100.0), UNDER_100, TODAY).status == "within"  # at the max is within


def test_a_known_price_above_the_budget_is_over():
    assert check_price(price(amount=100.01), UNDER_100, TODAY).status == "over"


def test_an_unknown_price_or_another_currency_is_not_checked():
    assert check_price(None, UNDER_100, TODAY).status == "unknown"
    assert check_price(price(amount=500.0, currency="EUR"), UNDER_100, TODAY).status == "other currency"


def test_an_old_price_is_never_used_to_leave_a_product_out():
    limit = config.PRICE_MAX_AGE_DAYS
    just_in_time = price(amount=500.0, checked_on=TODAY - timedelta(days=limit))
    too_old = price(amount=500.0, checked_on=TODAY - timedelta(days=limit + 1))
    assert check_price(just_in_time, UNDER_100, TODAY).status == "over"
    assert check_price(too_old, UNDER_100, TODAY).status == "out of date"
    assert check_price(price(amount=50.0, checked_on=TODAY - timedelta(days=limit + 1)), UNDER_100, TODAY).status == "out of date"


# --- Other names for the same product (9 Oct 2026) ---

def test_an_entry_can_list_the_other_names_the_same_product_goes_by():
    # A shop sells "Cuisinart CPK-17P1 PerfecTemp Cordless Electric Kettle"; Reddit calls it "Cuisinart CPK-17 PerfecTemp".
    from datetime import date

    from engine.prices import Price, find_availability

    entry = Price(product="Cuisinart CPK-17P1 PerfecTemp Cordless Electric Kettle Silver", category="kitchen", price=None,
                  currency="GBP", shop="Amazon UK", url="https://www.amazon.co.uk/dp/B08CYBHW8K",
                  checked_on=date(2026, 10, 9), available=False,
                  also_called=["Cuisinart CPK-17 PerfecTemp 1.7-Liter Stainless"])
    assert find_availability("Cuisinart CPK-17 PerfecTemp 1.7-Liter Stainless", "kitchen", [entry]) == entry
    assert find_availability("Zojirushi kettle", "kitchen", [entry]) is None


# --- A researcher's note (10 Oct 2026) ---
# Researchers wrote what they found out into the shop's name ("John Lewis (OXO's Professional ceramic non-stick frying
# pans; ...)"), which then showed on cards. A note now has a field of its own, which the answer never shows.

def test_an_entry_can_carry_a_note_the_answer_never_shows(tmp_path):
    from engine.answer import shown_availability
    from engine.prices import PriceCheck

    [price] = load_prices(write_prices(tmp_path, [entry(available=True, note="the only glass kettle Sage sells here")]))
    assert price.note == "the only glass kettle Sage sells here" and price.shop == entry()["shop"]
    shown = shown_availability(PriceCheck(None, "unknown", availability=price))
    assert "glass kettle" not in shown.text and shown.shop == price.shop


def test_the_committed_price_list_keeps_notes_out_of_shop_names():
    for price in load_prices():
        assert "(" not in price.shop and len(price.shop) <= 40, price.shop


def test_a_pack_size_in_an_entry_does_not_stop_a_longer_name_finding_it():
    # b01, 10 Oct 2026 (night): the full-size entry wasn't found for a group shown with its type word at the end, so an
    # answer asking for under £30 led with a £65 product (test_match_products: a pack size is not part of the name).
    full_size = price("Dermalogica Daily Microfoliant 74g", 65.0, category="skincare")
    assert find_price("dermalogica daily microfoliant exfoliant", "skincare", [full_size], "GBP") == full_size


def test_a_name_with_a_slip_finds_its_own_price_before_a_shorter_name():
    # From the library (10 Oct 2026): the misspelled oil cleanser's price, not the foam cleanser's.
    oil = price("Beplain Mungbean Greenful Oil Cleanser", category="skincare", amount=18.0,
                checked_on=TODAY - timedelta(days=5))
    foam = price("Beplain mungbean cleanser", category="skincare", amount=12.0)
    assert find_price("Beplain mungbean greenful oil cleasner", "skincare", [foam, oil]).price == 18.0
