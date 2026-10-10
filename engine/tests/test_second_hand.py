"""Sold second-hand only (Noemi's decision, 10 Oct 2026).

Vintage products no longer made, sold only second-hand (cast iron by Griswold and Wagner, out of production for
decades), count as available to UK shoppers, and the answer says so: "Sold second-hand only: <shop>, checked <date>".
A price-list entry says it with "second_hand": true, allowed only with "available": true. A brand pick is still never
priced and never left out for an entry under its own name, but when the list has a second-hand entry under the brand's
name ("Griswold"), the brand pick shows that line instead of "Availability not checked yet".

Every library, shop and link here is made up, and every library is a temporary folder: no test reads data/ except the
one that checks the committed price list.
"""

import json
import re
from datetime import date, timedelta

import pytest

from engine import answer as wording
from engine import prices, web
from engine.answer import answer_to_dict, render_markdown
from engine.pipeline import answer_request
from engine.prices import Price, PriceError, find_availability, load_prices
from engine.tests.test_availability import entry, listed, write_prices
from engine.tests.test_pipeline import praise, write_library
from engine.tests.test_web import ask

TODAY = date(2026, 10, 9)
REQUEST = "cast iron skillet that lasts"
GRISWOLD = "Griswold (their cast iron skillets)"
WAGNER = "Wagner 1891 skillet"
LINE = "Sold second-hand only: Made-up Vintage Dealer, checked 9 Oct 2026"


def second_hand(product: str, checked_on: date = TODAY, shop: str = "Made-up Vintage Dealer",
                url: str | None = None) -> Price:
    """A made-up entry: the product is no longer made and is sold only second-hand; no price (second-hand prices
    vary)."""
    url = url or f"https://vintage.example/{product.lower().replace(' ', '-')}"
    return Price(product=product, category="kitchen", price=None, currency="GBP", shop=shop, url=url,
                 checked_on=checked_on, available=True, second_hand=True)


def vintage_library(tmp_path):
    """Two cast iron skillet threads. "Griswold" fits two Griswold skillets (so it is a brand pick), praised across
    both threads; the Wagner 1891 skillet is one product, praised three times across both."""
    return write_library(tmp_path, {
        "1vin001": ("Best cast iron skillet for a beginner?", "My first one.", [
            praise("v1a", "Griswold", 20), praise("v1b", "Griswold", 15),
            praise("v1c", "Griswold No. 8 skillet", 3), praise("v1d", "Griswold No. 10 skillet", 4),
            praise("v1e", WAGNER, 12), praise("v1f", WAGNER, 9),
        ]),
        "1vin002": ("Which cast iron skillet lasts?", "Mine cracked.", [
            praise("v2a", "Griswold", 30), praise("v2b", WAGNER, 7),
        ]),
    })


def pick_named(result, name: str):
    return next(pick for pick in result.answer.picks if pick.name == name)


# --- The list ---

def test_an_entry_can_say_the_product_is_sold_second_hand_only(tmp_path):
    old, new = load_prices(write_prices(tmp_path, [entry(price=None, available=True, second_hand=True), entry()]))
    assert (old.price, old.available, old.second_hand) == (None, True, True)
    assert new.second_hand is False  # left out: an ordinary entry


@pytest.mark.parametrize("bad", [
    {"available": False, "second_hand": True},  # no longer sold, yet sold second-hand
    {"second_hand": True},  # a price, but availability not checked
    {"price": None, "second_hand": True},
])
def test_second_hand_without_available_true_is_refused_with_a_clear_error(tmp_path, bad):
    with pytest.raises(PriceError) as refused:
        load_prices(write_prices(tmp_path, [entry(), entry(**bad)]))
    assert "entry 2" in str(refused.value) and '"second_hand": true needs "available": true' in str(refused.value)


@pytest.mark.parametrize("unclear", ["yes", 1, None])
def test_second_hand_must_be_true_or_false(tmp_path, unclear):
    with pytest.raises(PriceError) as refused:
        load_prices(write_prices(tmp_path, [entry(available=True, second_hand=unclear)]))
    assert "entry 1" in str(refused.value) and "second_hand" in str(refused.value)


def test_the_committed_second_hand_entries_say_they_are_sold():
    assert all(p.available is True for p in load_prices() if p.second_hand)


# --- Finding whether it is sold ---

def test_a_second_hand_entry_says_the_product_is_sold():
    found = find_availability(WAGNER, "kitchen", [second_hand(WAGNER)])
    assert found.available is True and found.second_hand is True


def test_on_the_same_day_a_shop_selling_it_new_comes_before_a_second_hand_entry():
    new = listed(WAGNER, available=True, shop="Shop Z")
    assert find_availability(WAGNER, "kitchen", [second_hand(WAGNER), new]) == new
    # A newer check still decides first, as for any product.
    newer = second_hand(WAGNER, checked_on=TODAY + timedelta(days=1))
    assert find_availability(WAGNER, "kitchen", [new, newer]) == newer


# --- A specific product sold second-hand only ---

def test_a_second_hand_product_is_kept_and_its_pick_says_so(tmp_path):
    result = answer_request(REQUEST, library_dir=vintage_library(tmp_path), prices=[second_hand(WAGNER)],
                            product_facts=[], today=TODAY)
    assert WAGNER not in result.left_out_unavailable
    shown = pick_named(result, WAGNER).availability
    assert shown.text == LINE
    assert (shown.available, shown.second_hand, shown.shop, shown.url, shown.checked_on) == (
        True, True, "Made-up Vintage Dealer", "https://vintage.example/wagner-1891-skillet", "2026-10-09")
    assert pick_named(result, WAGNER).price.text == wording.PRICE_UNKNOWN


def test_a_second_hand_product_within_a_budget_is_kept_too(tmp_path):
    result = answer_request("cast iron skillet that lasts under £100", library_dir=vintage_library(tmp_path),
                            prices=[second_hand(WAGNER)], product_facts=[], today=TODAY)
    assert pick_named(result, WAGNER).availability.text == LINE
    assert result.left_out_unavailable == [] and result.left_out_over_budget == []


def test_the_second_hand_line_turns_into_markdown_and_json(tmp_path):
    result = answer_request(REQUEST, library_dir=vintage_library(tmp_path), product_facts=[], today=TODAY,
                            prices=[second_hand(WAGNER), listed("Griswold No. 8 skillet")])
    text = render_markdown(result.answer)
    assert f"{LINE} · [{wording.PRICE_LINK_TEXT}](https://vintage.example/wagner-1891-skillet)" in text
    data = json.loads(json.dumps(answer_to_dict(result.answer)))
    shown = {pick["name"]: pick["availability"] for pick in data["picks"]}
    assert shown[WAGNER] == {"text": LINE, "available": True, "second_hand": True, "shop": "Made-up Vintage Dealer",
                             "url": "https://vintage.example/wagner-1891-skillet", "checked_on": "2026-10-09"}
    assert shown[GRISWOLD]["second_hand"] is False  # a brand pick with no second-hand entry under its name


def test_the_second_hand_wording_noemis_decision():
    assert wording.AVAILABILITY_SECOND_HAND == "Sold second-hand only: {shop}, checked {date}"


# --- Brand picks ---

def test_a_brand_pick_with_a_second_hand_entry_under_its_name_shows_the_line(tmp_path):
    result = answer_request(REQUEST, library_dir=vintage_library(tmp_path), prices=[second_hand("Griswold")],
                            product_facts=[], today=TODAY)
    pick = pick_named(result, GRISWOLD)
    assert pick.availability.text == "Sold second-hand only: Made-up Vintage Dealer, checked 9 Oct 2026"
    assert pick.availability.second_hand is True and pick.availability.url == "https://vintage.example/griswold"
    assert pick.price.text == wording.PRICE_UNKNOWN  # still never priced
    assert GRISWOLD in result.not_priced and GRISWOLD not in result.left_out_unavailable


def test_a_brand_pick_is_still_never_left_out_for_an_entry_under_its_own_name(tmp_path):
    # The newest check under the brand's name says it is no longer sold: the brand pick stays, and since that entry
    # isn't second-hand, it says its availability isn't checked. One Griswold skillet is listed as sold, so the brand
    # pick isn't left out with its own products either (engine/tests/test_pick_polish.py, part 4).
    gone_since = listed("Griswold", available=False, checked_on=TODAY)
    result = answer_request(REQUEST, library_dir=vintage_library(tmp_path), product_facts=[], today=TODAY,
                            prices=[second_hand("Griswold", checked_on=TODAY - timedelta(days=5)), gone_since,
                                    listed("Griswold No. 8 skillet")])
    assert GRISWOLD not in result.left_out_unavailable
    assert pick_named(result, GRISWOLD).availability.text == wording.AVAILABILITY_UNKNOWN


@pytest.mark.parametrize("made_up", [
    lambda: [],  # nothing in the list
    lambda: [listed("Griswold", available=True)],  # sold new under its name: still never checked for that
    lambda: [second_hand("Griswold No. 8 skillet")],  # second-hand, but one of its products, not the brand's name
    lambda: [second_hand("Lodge")],  # another brand
])
def test_a_brand_pick_without_a_second_hand_entry_under_its_name_still_says_not_checked(tmp_path, made_up):
    result = answer_request(REQUEST, library_dir=vintage_library(tmp_path), prices=made_up(), product_facts=[],
                            today=TODAY)
    shown = pick_named(result, GRISWOLD).availability
    assert (shown.text, shown.available, shown.second_hand) == (wording.AVAILABILITY_UNKNOWN, None, False)
    assert GRISWOLD in result.not_priced


# --- The demo page ---

def test_the_web_card_carries_and_draws_the_second_hand_line(tmp_path, monkeypatch):
    made_up = [second_hand("Griswold"), second_hand(WAGNER, shop="Another Vintage Dealer")]
    monkeypatch.setattr(web, "answer_request", lambda request, library_dir: answer_request(
        request, library_dir, prices=made_up, product_facts=[], today=TODAY))
    _, _, data = ask(REQUEST, vintage_library(tmp_path))
    shown = {pick["name"]: pick["availability"] for pick in data["answer"]["picks"]}
    assert shown[GRISWOLD]["text"] == LINE and shown[GRISWOLD]["second_hand"] is True
    assert shown[WAGNER]["text"] == "Sold second-hand only: Another Vintage Dealer, checked 9 Oct 2026"
    assert data["left_out"]["unavailable"] == 0
    # The card draws the line's own words, with its link through the page's https check, whatever kind of line it is.
    html = web.search_page().decode("utf-8")
    body = re.search(r"function availabilityLine\(availability\) \{(.*?)\n  \}", html, re.DOTALL).group(1)
    assert "availability.text" in body and "const shop = shopUrl(availability.url);" in body


# --- What is still to look up ---

def test_a_second_hand_entry_without_a_price_is_not_asked_for_one():
    # Second-hand prices vary from one pan to the next, so a second-hand entry's price stays null on purpose.
    assert prices.missing(WAGNER, "kitchen", [second_hand(WAGNER)]) == []
    assert prices.missing(WAGNER, "kitchen", [listed(WAGNER, available=True)]) == ["price"]
