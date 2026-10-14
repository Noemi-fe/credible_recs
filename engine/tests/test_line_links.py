"""Brand lines' range links and from prices (Noemi's night decision 1, 14 Oct 2026).

Noemi asked why the knife answer ("first chef's knife under £100 for a home cook") showed no product link: its three
picks were brand lines, and a line has no single price (since 10 Oct 2026 it was never priced and never linked to a
shop), so each said "Price not checked yet". She approved two things, for display and the budget check only (how picks
are chosen doesn't change):
1. each brand-line pick, and each line under "Also worth a look", links to the maker's page for its products of that type
   (or an official UK stockist's), from data/brand_lines.json's researched sources: "Browse Victorinox's chef knives",
   with the day its sources were read;
2. a researched, sourced, dated "From £X" price: the cheapest UK price of the line's products of that type, shown as
   "From £X at <shop>, checked <date>". Under a budget below it the line is left out, as before (12 Oct 2026); within
   it, the line says "From £X, within your budget".

Every brand entry, page, shop and library here is made up (but for Victorinox, the knife library's real brand name).
"""

import json
import re
from datetime import date, timedelta

import pytest

from engine import answer as wording
from engine.answer import ShownRange, answer_to_dict, render_markdown, shown_range, unverified_claims
from engine.brand_lines import BrandLine
from engine.pipeline import answer_request
from engine.tests.test_pick_polish import KNIFE_REQUEST, VICTORINOX, knife_library
from engine.tests.test_pipeline import FakeLive, praise
from engine.tests.test_pipeline_worth import knives

TODAY = date(2026, 10, 14)
RANGE = "https://maker.example/chef-knives"
SHOP = "https://shop.example/victorinox-15cm"
UNDER_100 = KNIFE_REQUEST + " under £100"


def victorinox(**overrides) -> BrandLine:
    """A made-up entry for Victorinox's chef knives: a range page, and a from price found at a made-up shop."""
    data = dict(brand="Victorinox", category="kitchen", product_type="chef knife", sells=True, sources=[RANGE, SHOP],
                checked_on=TODAY, range_page=RANGE, from_price=25.0, from_price_shop="Made-up Cookshop",
                from_price_url=SHOP, from_price_checked_on=TODAY, note="Made up for a test.")
    return BrandLine(**(data | overrides))


def answer(tmp_path, lines, request: str = KNIFE_REQUEST, live_checker=None):
    """The knife answer whose first pick is the Victorinox line (its Fibrox praised in one thread only)."""
    return answer_request(request, library_dir=knife_library(tmp_path, fibrox=(2, 0)), prices=[], product_facts=[],
                          brand_lines=lines, today=TODAY, live_checker=live_checker)


def pick(result, name: str):
    return next(p for p in result.answer.picks if p.name == name)


# --- 1. The range link ---

def test_a_brand_line_pick_links_to_its_makers_page_for_its_type(tmp_path):
    result = answer(tmp_path, [victorinox()])
    assert [p.name for p in result.answer.picks] == [VICTORINOX, "Mac Mighty chef knife", "Tojiro DP gyuto"]
    assert pick(result, VICTORINOX).range == ShownRange(
        text="Browse Victorinox's chef knives", url=RANGE, checked="checked 14 Oct 2026", checked_on="2026-10-14")
    # A specific product has its own price line; only a line, which has many products, links to its maker's range.
    assert pick(result, "Mac Mighty chef knife").range is None and pick(result, "Tojiro DP gyuto").range is None
    assert unverified_claims(result.answer, result.bodies) == []


def test_an_official_uk_stockists_page_says_whose_it_is(tmp_path):
    result = answer(tmp_path, [victorinox(range_page=SHOP, range_shop="Made-up Cookshop")])
    assert pick(result, VICTORINOX).range.text == "Browse Victorinox's chef knives at Made-up Cookshop"
    assert pick(result, VICTORINOX).range.url == SHOP


def test_a_line_without_a_range_page_or_without_an_entry_has_no_link(tmp_path):
    assert pick(answer(tmp_path / "a", [victorinox(range_page=None)]), VICTORINOX).range is None
    # With no entry, its threads alone rank the brand as a line (decision 9): nothing was researched, so no link.
    assert pick(answer(tmp_path / "b", []), VICTORINOX).range is None


def test_the_link_is_the_entrys_own_page_checked_again_before_it_is_shown():
    # The list refuses such pages as it loads; this is the second lock, should an entry ever be built by hand.
    unsafe = lambda **changes: BrandLine.model_construct(**(victorinox().model_dump() | changes))
    assert shown_range(victorinox()).url == RANGE  # exactly as written in the list
    assert shown_range(unsafe(range_page="http://maker.example/chef-knives",
                              sources=["http://maker.example/chef-knives"])) is None  # https only
    assert shown_range(unsafe(range_page="https://maker.example/elsewhere")) is None  # one of its sources only
    reddit = "https://www.reddit.com/r/chefknives/comments/abc/x/"
    assert shown_range(unsafe(range_page=reddit, sources=[reddit])) is None  # never Reddit: writers aren't makers
    assert shown_range(victorinox(sells=False)) is None  # a brand that doesn't sell the type is never linked for it
    assert shown_range(None) is None


@pytest.mark.parametrize("brand, product_type, category, text", [
    ("Wüsthof", "chef knife", "kitchen", "Browse Wüsthof's chef knives"),  # as its maker writes it
    ("Head & Shoulders", "shampoo", "haircare", "Browse Head & Shoulders' shampoos"),
    ("Burt's Bees", "lip balm", "skincare", "Browse Burt's Bees' lip balms"),
    ("O'Keeffe's", "lip balm", "skincare", "Browse O'Keeffe's lip balms"),  # already a possessive
    ("Le Creuset", "dutch oven", "kitchen", "Browse Le Creuset's Dutch ovens"),  # the type as a name shows it
])
def test_the_link_says_whose_products_it_shows(brand, product_type, category, text):
    page = "https://maker.example/range"
    line = BrandLine(brand=brand, category=category, product_type=product_type, sells=True, sources=[page],
                     checked_on=TODAY, range_page=page)
    assert shown_range(line).text == text


# --- 2. The from price ---

def test_a_brand_line_shows_its_from_price_with_the_shop_and_the_day(tmp_path):
    result = answer(tmp_path, [victorinox()])
    line = pick(result, VICTORINOX)
    assert line.price.text == "From £25 at Made-up Cookshop, checked 14 Oct 2026"
    assert (line.price.amount, line.price.currency, line.price.shop, line.price.url, line.price.checked_on) == (
        25.0, "GBP", "Made-up Cookshop", SHOP, "2026-10-14")
    assert line.price.from_price is True and line.price.budget_status is None
    # The researcher found it on sale there that day: the line is sold, and the price line already links to the page.
    assert line.availability.text == "Sold at Made-up Cookshop, checked 14 Oct 2026"
    assert line.availability.available is True and line.availability.url is None
    mac = pick(result, "Mac Mighty chef knife")
    assert mac.price.text == wording.PRICE_UNKNOWN and mac.price.from_price is False


def test_within_the_budget_a_line_says_its_from_price_is(tmp_path):
    line = pick(answer(tmp_path, [victorinox()], UNDER_100), VICTORINOX)
    assert line.price.budget_status == "within"
    assert line.price.budget_note == "From £25, within your budget (up to £100)."


def test_a_line_whose_from_price_is_over_the_budget_is_still_left_out(tmp_path):
    result = answer(tmp_path, [victorinox(from_price=120.0)], UNDER_100)
    assert VICTORINOX not in [p.name for p in result.answer.picks]
    assert VICTORINOX in result.left_out_over_budget and VICTORINOX not in result.not_priced


def test_an_old_from_price_is_shown_with_its_day_but_never_used_to_keep_a_line(tmp_path):
    old = TODAY - timedelta(days=wording.PRICE_MAX_AGE_DAYS + 10)
    kept = pick(answer(tmp_path / "a", [victorinox(from_price_checked_on=old)], UNDER_100), VICTORINOX)
    assert kept.price.text == f"From £25 at Made-up Cookshop, checked {old.day} {old:%b %Y}"
    assert kept.price.budget_status == "out of date"
    assert kept.price.budget_note == wording.BUDGET_NOT_CHECKED.format(
        max="£100", why=wording.BUDGET_WHY_OLD.format(days=wording.PRICE_MAX_AGE_DAYS))
    # An old from price over the budget still leaves the line out (the rule of 12 Oct 2026, whatever its age).
    over = answer(tmp_path / "b", [victorinox(from_price=120.0, from_price_checked_on=old)], UNDER_100)
    assert VICTORINOX in over.left_out_over_budget


def test_a_from_price_without_where_and_when_it_was_found_is_never_shown(tmp_path):
    bare = victorinox(from_price_shop=None, from_price_url=None, from_price_checked_on=None, sources=[RANGE])
    line = pick(answer(tmp_path / "a", [bare], UNDER_100), VICTORINOX)
    assert line.price.text == wording.PRICE_UNKNOWN and line.price.from_price is False
    assert line.price.budget_status == "unknown" and line.availability.available is None
    assert line.range is not None  # its range page still shows
    over = answer(tmp_path / "b", [bare.model_copy(update={"from_price": 120.0})], UNDER_100)
    assert VICTORINOX in over.left_out_over_budget  # and it still leaves the line out under a lower budget


def test_a_specific_product_of_the_brand_never_takes_its_lines_from_price(tmp_path):
    # Its brand's cheapest product says nothing about its own price (it only leaves it out when over the budget).
    result = answer_request(KNIFE_REQUEST, library_dir=knife_library(tmp_path), prices=[], product_facts=[],
                            brand_lines=[victorinox()], today=TODAY)
    fibrox = pick(result, "Victorinox Fibrox chef knife")
    assert fibrox.price.text == wording.PRICE_UNKNOWN and fibrox.range is None


# --- Also worth a look ---

HEARTH_RANGE = "https://hearthblade.example/chef-knives"
HEARTH_SHOP = "https://shop.example/hearthblade-ember"


def hearthblade() -> BrandLine:
    return BrandLine(brand="Hearthblade", category="kitchen", product_type="chef knife", sells=True,
                     sources=[HEARTH_RANGE, HEARTH_SHOP], checked_on=TODAY, range_page=HEARTH_RANGE, from_price=59.99,
                     from_price_shop="Made-up Cookshop", from_price_url=HEARTH_SHOP, from_price_checked_on=TODAY)


def test_a_line_under_also_worth_a_look_links_and_shows_its_from_price_too(tmp_path):
    # "Hearthblade" fits two of its knives (a line); its writers praise it once in each thread: two credible
    # recommendations across two threads, so it is shown apart, after the picks.
    line = ("hearthblade",
            [praise("h1a", "Hearthblade", 5), praise("h1b", "Hearthblade Ember chef knife", 4)],
            [praise("h2a", "Hearthblade", 6), praise("h2b", "Hearthblade Tidewater chef knife", 3)])
    result = answer_request(KNIFE_REQUEST, library_dir=knives(tmp_path, line), prices=[], product_facts=[],
                            brand_lines=[hearthblade()], today=TODAY)
    item = next(i for i in result.answer.worth_a_look if i.name == "Hearthblade chef knife line")
    assert item.range == ShownRange("Browse Hearthblade's chef knives", HEARTH_RANGE, "checked 14 Oct 2026",
                                    "2026-10-14")
    assert item.price.text == "From £59.99 at Made-up Cookshop, checked 14 Oct 2026" and item.price.from_price
    assert all(i.range is None for i in result.answer.worth_a_look if i.name != "Hearthblade chef knife line")


# --- How picks are chosen doesn't change ---

def test_links_and_from_prices_change_nothing_about_which_products_are_picks(tmp_path):
    plain = answer(tmp_path / "a", [victorinox(range_page=None, from_price=None, from_price_shop=None,
                                              from_price_url=None, from_price_checked_on=None)], UNDER_100)
    linked = answer(tmp_path / "b", [victorinox()], UNDER_100)
    shown = lambda result: [(p.name, p.score, [q.comment_id for q in p.quotes]) for p in result.answer.picks]
    assert shown(linked) == shown(plain)
    assert [i.name for i in linked.answer.worth_a_look] == [i.name for i in plain.answer.worth_a_look]
    assert [i.name for i in linked.answer.skip] == [i.name for i in plain.answer.skip]


def test_the_link_and_the_from_price_stay_when_the_live_check_writes_the_answer_again(tmp_path):
    first = answer(tmp_path / "a", [victorinox()])
    mac = pick(first, "Mac Mighty chef knife")
    again = answer(tmp_path / "b", [victorinox()], live_checker=FakeLive(gone={mac.quotes[0].comment_id}))
    assert again.live_dropped == {"gone": 1}
    assert pick(again, VICTORINOX).range == pick(first, VICTORINOX).range
    assert pick(again, VICTORINOX).price.from_price is True


# --- The API and the text ---

def test_the_link_and_the_from_price_turn_into_json_and_markdown(tmp_path):
    result = answer(tmp_path, [victorinox()], UNDER_100)
    data = json.loads(json.dumps(answer_to_dict(result.answer)))
    first, second = data["picks"][0], data["picks"][1]
    assert first["range"] == {"text": "Browse Victorinox's chef knives", "url": RANGE, "checked": "checked 14 Oct 2026",
                              "checked_on": "2026-10-14"}
    assert first["price"]["from_price"] is True and first["price"]["amount"] == 25.0
    assert second["range"] is None and second["price"]["from_price"] is False
    text = render_markdown(result.answer)
    assert (f"**{wording.PRICE_LABEL}:** From £25 at Made-up Cookshop, checked 14 Oct 2026 · "
            f"[{wording.PRICE_LINK_TEXT}]({SHOP})") in text
    assert "From £25, within your budget (up to £100)." in text
    assert f"[Browse Victorinox's chef knives]({RANGE}) · checked 14 Oct 2026" in text


def test_the_wording_decided_by_claude_from_noemis_example():
    assert wording.RANGE_LINK == "Browse {brand} {products}"
    assert wording.PRICE_FROM == "From {amount} at {shop}, checked {date}"
    assert wording.BUDGET_WITHIN_FROM == "From {amount}, within your budget (up to {max})."


# --- The page (engine/templates/search.html) ---

def page_html() -> str:
    from engine import web

    return web.search_page().decode("utf-8")


def test_the_page_draws_a_lines_range_link_through_a_check_of_its_own():
    html = page_html()
    body = re.search(r"function rangeLine\(range\) \{(.*?)\n  \}", html, re.DOTALL).group(1)
    assert "const address = rangeUrl(range.url);" in body
    assert "range.text" in body and "range.checked" in body  # the answer's own words, drawn as text
    assert "rangeLine(pick.range)" in html and "rangeLine(item.range)" in html  # picks and Also worth a look


def test_a_range_link_must_be_https_with_no_name_or_password_and_never_reddits():
    check = re.search(r"function rangeUrl\(address\) \{(.*?)\n  \}", page_html(), re.DOTALL).group(1)
    assert 'url.protocol === "https:"' in check and "http:" not in check.replace("https:", "")
    assert "url.username" in check and "url.password" in check
    assert '"reddit.com"' in check and '"redd.it"' in check  # writers aren't makers: never a Reddit page


def test_the_page_says_from_wherever_it_shows_a_lines_amount_alone():
    html = page_html()
    settings = json.loads(re.search(r'<script type="application/json" id="settings">(.*?)</script>', html,
                                    re.DOTALL).group(1))
    assert settings["wording"]["price_from_amount"] == wording.PRICE_FROM_AMOUNT == "From {amount}"
    body = re.search(r"function priceAmount\(price\) \{(.*?)\n  \}", html, re.DOTALL).group(1)
    assert "price.from_price" in body and "WORDING.price_from_amount" in body


# --- The how page ---

def test_the_how_page_says_how_a_brand_line_is_linked_and_priced(tmp_path, monkeypatch):
    from engine.tests.test_how_page import get_how, text_of

    text = text_of(get_how(tmp_path, monkeypatch))
    assert "links to the maker's page for that kind of product, such as \"Browse Lodge's cast iron skillets\"" in text
    assert "its \"From\" price: the cheapest price we found for that kind of product of the brand" in text
    assert "with the shop and the day we checked" in text
    assert "A brand's line is left out when even its cheapest product of that kind is over your budget." in text
