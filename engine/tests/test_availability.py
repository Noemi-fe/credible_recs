"""Availability (Noemi's note, 9 Oct 2026: "are we making sure the products we recommend exist?").

The price list (data/prices.json) can also say whether a product is still sold ("available": true or false), with or
without a price. A product no longer sold is left out of the ranking and listed; every pick says where it is sold, or
that this isn't checked yet. `python -m engine.prices todo` lists the blind-test picks still to look up.

Every price, shop and link here is made up, and every library is a temporary folder: no test reads data/ except the
one that checks the committed price list still loads.
"""

import json
import re
from datetime import date, timedelta

import pytest

from engine import answer as wording
from engine import pipeline, prices, web
from engine.answer import answer_to_dict, render_markdown, write_answer
from engine.config import PRICE_MAX_AGE_DAYS
from engine.pipeline import answer_request
from engine.prices import Price, PriceCheck, PriceError, find_availability, find_price, load_prices
from engine.query import Budget
from engine.tests.test_answer import kitchen_case
from engine.tests.test_live_checks import restamp
from engine.tests.test_pipeline import REQUEST, skillet_library
from engine.tests.test_pipeline import library as zojirushi_library
from engine.tests.test_slice_eval import questions_file
from engine.tests.test_web import ask
from engine.tests.test_web import kettle_library as three_kettles

TODAY = date(2026, 10, 9)


def entry(**overrides) -> dict:
    data = {"product": "Zojirushi kettle", "category": "kitchen", "price": 120.0, "currency": "GBP",
            "shop": "Made-up Kitchen Shop", "url": "https://shop.example/zojirushi-kettle", "checked_on": "2026-10-09"}
    data.update(overrides)
    return data


def write_prices(tmp_path, entries: list[dict]):
    path = tmp_path / "prices.json"
    path.write_text(json.dumps({"prices": entries}), encoding="utf-8")
    return path


def listed(product: str = "Zojirushi kettle", available: bool | None = True, price: float | None = None,
           checked_on: date = TODAY, shop: str = "Made-up Kitchen Shop", url: str | None = None,
           category: str = "kitchen") -> Price:
    """One line of a made-up price list: by default, the product is sold and its price wasn't looked at."""
    url = url or f"https://shop.example/{product.lower().replace(' ', '-')}"
    return Price(product=product, category=category, price=price, currency="GBP", shop=shop, url=url,
                 checked_on=checked_on, available=available)


# --- The list ---

def test_an_entry_can_say_whether_the_product_is_sold_with_or_without_a_price(tmp_path):
    only, both = load_prices(write_prices(tmp_path, [entry(price=None, available=True), entry(available=False)]))
    assert (only.price, only.available) == (None, True)
    assert (both.price, both.available) == (120.0, False)


def test_an_entry_without_available_says_nothing_about_it(tmp_path):
    [loaded] = load_prices(write_prices(tmp_path, [entry()]))
    assert loaded.available is None


@pytest.mark.parametrize("bad", [
    {"price": None},  # neither a price nor an availability check: nothing was looked up
    {"price": None, "available": None},
    {"available": "yes"},  # true or false only
    {"available": 1},
])
def test_an_entry_that_checked_nothing_or_says_available_unclearly_is_refused(tmp_path, bad):
    with pytest.raises(PriceError) as refused:
        load_prices(write_prices(tmp_path, [entry(), entry(**bad)]))
    assert "entry 2" in str(refused.value)


def test_the_committed_list_still_loads():
    assert all(p.price is not None or p.available is not None for p in load_prices())


# --- Finding a product's price and its availability ---

def test_a_price_comes_only_from_an_entry_that_has_one():
    newer_without = listed(checked_on=TODAY)
    older_with = listed(price=120.0, available=None, checked_on=TODAY - timedelta(days=3))
    assert find_price("Zojirushi kettle", "kitchen", [newer_without, older_with]) == older_with
    assert find_price("Zojirushi kettle", "kitchen", [newer_without]) is None


def test_availability_comes_from_the_newest_check():
    sold_long_ago = listed(available=True, checked_on=TODAY - timedelta(days=60))
    gone_now = listed(available=False, checked_on=TODAY)
    assert find_availability("Zojirushi kettle", "kitchen", [sold_long_ago, gone_now]) == gone_now
    sold_again = listed(available=True, checked_on=TODAY + timedelta(days=1), shop="Another Shop")
    assert find_availability("Zojirushi kettle", "kitchen", [gone_now, sold_again]) == sold_again


def test_on_the_same_day_one_shop_selling_it_is_enough():
    gone_here = listed(available=False, shop="Shop A", url="https://a.example/kettle")
    sold_there = listed(available=True, shop="Shop B", url="https://b.example/kettle")
    assert find_availability("Zojirushi kettle", "kitchen", [gone_here, sold_there]) == sold_there


def test_the_exact_name_comes_first():
    variant_gone = listed("Zojirushi kettle with gooseneck spout", available=False)
    exact_sold = listed(available=True, checked_on=TODAY - timedelta(days=5))
    assert find_availability("Zojirushi kettle", "kitchen", [variant_gone, exact_sold]) == exact_sold


def test_without_an_availability_check_nothing_is_known():
    assert find_availability("Zojirushi kettle", "kitchen", [listed(price=120.0, available=None)]) is None
    assert find_availability("Fellow Stagg kettle", "kitchen", [listed(available=True)]) is None
    assert find_availability("Zojirushi kettle", "kitchen", [listed(available=True, category="skincare")]) is None


# --- The pipeline: a product no longer sold is left out ---

def test_a_product_no_longer_sold_is_left_out_of_the_ranking_and_listed(tmp_path):
    result = answer_request(REQUEST, library_dir=zojirushi_library(tmp_path), prices=[listed(available=False)], today=TODAY)
    assert result.left_out_unavailable == ["Zojirushi kettle"]
    assert "Zojirushi kettle" not in [p.name for p in result.ranking.products]
    assert "Zojirushi kettle" not in [p.name for p in result.answer.picks]


def test_no_longer_sold_is_listed_as_such_whatever_its_price(tmp_path):
    lib = zojirushi_library(tmp_path)
    for amount in (80.0, 180.0):  # within the budget, and over it
        result = answer_request("electric kettle under £100", library_dir=lib, today=TODAY,
                                prices=[listed(available=False, price=amount)])
        assert result.left_out_unavailable == ["Zojirushi kettle"] and result.left_out_over_budget == []


def test_an_old_no_longer_sold_check_still_leaves_the_product_out(tmp_path):
    # Unlike an old price, which may have changed: a product that stopped being sold rarely comes back.
    long_ago = TODAY - timedelta(days=PRICE_MAX_AGE_DAYS + 30)
    result = answer_request(REQUEST, library_dir=zojirushi_library(tmp_path), today=TODAY,
                            prices=[listed(available=False, checked_on=long_ago)])
    assert result.left_out_unavailable == ["Zojirushi kettle"]


def test_a_product_sold_says_where_and_when_and_its_price_works_as_before(tmp_path):
    lib = zojirushi_library(tmp_path)
    pick = answer_request(REQUEST, library_dir=lib, prices=[listed(available=True)], today=TODAY).answer.picks[0]
    assert pick.name == "Zojirushi kettle" and pick.price.text == wording.PRICE_UNKNOWN
    assert pick.availability.text == "Sold at Made-up Kitchen Shop, checked 9 Oct 2026"
    assert pick.availability.available is True and pick.availability.url == "https://shop.example/zojirushi-kettle"

    within = answer_request("electric kettle under £100", library_dir=lib, today=TODAY,
                            prices=[listed(available=True, price=80.0)])
    pick = within.answer.picks[0]
    assert pick.price.budget_status == "within" and pick.price.url == "https://shop.example/zojirushi-kettle"
    assert pick.availability.text == "Sold at Made-up Kitchen Shop, checked 9 Oct 2026"
    assert pick.availability.url is None  # the price line already links to the same page
    over = answer_request("electric kettle under £100", library_dir=lib, today=TODAY,
                          prices=[listed(available=True, price=180.0)])
    assert over.left_out_over_budget == ["Zojirushi kettle"] and over.left_out_unavailable == []


def test_a_product_with_no_availability_check_says_so(tmp_path):
    result = answer_request(REQUEST, library_dir=zojirushi_library(tmp_path), today=TODAY,
                            prices=[listed(available=None, price=120.0)])
    pick = result.answer.picks[0]
    assert pick.availability.text == wording.AVAILABILITY_UNKNOWN and pick.availability.available is None
    assert pick.price.amount == 120.0 and result.left_out_unavailable == []


def test_a_brand_pick_is_never_checked_for_availability(tmp_path):
    # Since 10 Oct 2026 a brand pick is left out when every one of its own specific products here isn't sold
    # (engine/tests/test_pick_polish.py, part 4), and the "Lodge" entry below also fits both Lodge skillets. So one of them
    # is listed as sold. Changed on purpose late on 10 Oct 2026: an entry under the brand's own name that says it isn't
    # sold now leaves the brand pick out (OXO's 120 V kettles), but not while one of its own products here is known to
    # be sold, as here: that proves the brand is.
    result = answer_request("cast iron skillet that lasts", library_dir=skillet_library(tmp_path), today=TODAY,
                            prices=[listed("Lodge", available=False), listed("Lodge Blacklock skillet")])
    assert "Lodge (their cast iron skillets)" in [pick.name for pick in result.answer.picks]
    assert "Lodge (their cast iron skillets)" in result.not_priced
    assert "Lodge (their cast iron skillets)" not in result.left_out_unavailable


# --- The answer ---

def knife(available: bool | None = True, price: float | None = None, url: str = "https://shop.example/tojiro-dp-gyuto",
          shop: str = "Made-up Knife Shop") -> Price:
    return Price(product="Tojiro DP Gyuto", category="kitchen", price=price, currency="GBP", shop=shop, url=url,
                 checked_on=TODAY, available=available)


def test_the_availability_wording_decided_by_claude():
    assert wording.AVAILABILITY == "Sold at {shop}, checked {date}"
    assert wording.AVAILABILITY_UNKNOWN == "Availability not checked yet"
    assert wording.AVAILABILITY_GONE == "No longer sold, checked {date}"


def test_each_pick_says_where_it_is_sold_or_that_its_availability_is_not_checked():
    ranking, bodies, _ = kitchen_case()
    checks = {"tojiro-dp-gyuto": PriceCheck(None, "no budget", availability=knife())}
    tojiro, global_g2, _ = write_answer(ranking, bodies, "chef knife", checks).picks
    shown = tojiro.availability
    assert shown.text == "Sold at Made-up Knife Shop, checked 9 Oct 2026"
    assert (shown.available, shown.shop, shown.url, shown.checked_on) == (
        True, "Made-up Knife Shop", "https://shop.example/tojiro-dp-gyuto", "2026-10-09")
    assert tojiro.price.text == wording.PRICE_UNKNOWN
    unknown = global_g2.availability
    assert (unknown.text, unknown.available, unknown.shop, unknown.url, unknown.checked_on) == (
        wording.AVAILABILITY_UNKNOWN, None, None, None, None)
    assert {pick.availability.text for pick in write_answer(ranking, bodies).picks} == {wording.AVAILABILITY_UNKNOWN}


def test_the_availability_line_links_to_the_shop_unless_the_price_line_already_does():
    ranking, bodies, _ = kitchen_case()
    same = knife(price=120.0)
    tojiro = write_answer(ranking, bodies, prices={"tojiro-dp-gyuto": PriceCheck(same, "no budget", availability=same)}).picks[0]
    assert tojiro.price.url == "https://shop.example/tojiro-dp-gyuto" and tojiro.availability.url is None
    elsewhere = knife(shop="Another Knife Shop", url="https://another.example/tojiro")
    tojiro = write_answer(ranking, bodies, prices={"tojiro-dp-gyuto": PriceCheck(same, "no budget", availability=elsewhere)}).picks[0]
    assert tojiro.availability.url == "https://another.example/tojiro"
    assert tojiro.availability.text == "Sold at Another Knife Shop, checked 9 Oct 2026"


def test_a_shop_link_that_is_not_https_is_never_passed_on():
    ranking, bodies, _ = kitchen_case()
    unsafe = Price.model_construct(product="Tojiro DP Gyuto", category="kitchen", price=None, currency="GBP",
                                   shop="Made-up Knife Shop", url="http://shop.example/tojiro", checked_on=TODAY,
                                   available=True)
    pick = write_answer(ranking, bodies, prices={"tojiro-dp-gyuto": PriceCheck(None, "no budget", availability=unsafe)}).picks[0]
    assert pick.availability.url is None and pick.availability.available is True


def test_a_product_known_to_be_no_longer_sold_is_never_said_to_be_unchecked():
    # The pipeline leaves such a product out; this is the second lock, should one ever reach the answer.
    ranking, bodies, _ = kitchen_case()
    gone = knife(available=False)
    pick = write_answer(ranking, bodies, prices={"tojiro-dp-gyuto": PriceCheck(None, "no budget", availability=gone)}).picks[0]
    assert pick.availability.text == "No longer sold, checked 9 Oct 2026"
    assert pick.availability.available is False and pick.availability.url is None


def test_the_availability_turns_into_json_and_markdown():
    ranking, bodies, _ = kitchen_case()
    checks = {"tojiro-dp-gyuto": PriceCheck(None, "within", Budget(max=100, currency="GBP"), availability=knife())}
    answer = write_answer(ranking, bodies, prices=checks)
    data = json.loads(json.dumps(answer_to_dict(answer)))
    assert set(data["picks"][0]["availability"]) == {"text", "available", "shop", "url", "checked_on", "second_hand"}
    assert data["picks"][0]["availability"]["available"] is True
    assert data["picks"][1]["availability"]["text"] == wording.AVAILABILITY_UNKNOWN
    text = render_markdown(answer)
    assert ("Sold at Made-up Knife Shop, checked 9 Oct 2026 · "
            f"[{wording.PRICE_LINK_TEXT}](https://shop.example/tojiro-dp-gyuto)") in text
    assert wording.AVAILABILITY_UNKNOWN in text


# --- The demo page ---

@pytest.fixture
def fresh_answers():
    web.clear_answer_cache()
    yield
    web.clear_answer_cache()


def test_each_card_carries_its_availability_and_products_no_longer_sold_are_counted(tmp_path, monkeypatch, fresh_answers):
    made_up = [listed("Zojirushi kettle", available=True), listed("Bonavita kettle", available=False)]
    monkeypatch.setattr(web, "answer_request",
                        lambda request, library_dir: answer_request(request, library_dir, prices=made_up, today=TODAY))
    _, _, data = ask(REQUEST, three_kettles(tmp_path))
    shown = {pick["name"]: pick["availability"] for pick in data["answer"]["picks"]}
    assert set(shown) == {"Zojirushi kettle", "Fellow Stagg kettle"}
    assert shown["Zojirushi kettle"]["text"] == "Sold at Made-up Kitchen Shop, checked 9 Oct 2026"
    assert shown["Zojirushi kettle"]["url"] == "https://shop.example/zojirushi-kettle"
    assert shown["Fellow Stagg kettle"] == {"text": wording.AVAILABILITY_UNKNOWN, "available": None, "shop": None,
                                            "url": None, "checked_on": None, "second_hand": False}
    assert data["left_out"]["unavailable"] == 1


def test_the_page_draws_the_availability_line_as_text_with_its_link_checked():
    html = web.search_page().decode("utf-8")
    assert "...priceLines(pick.price), availabilityLine(pick.availability)," in html
    body = re.search(r"function availabilityLine\(availability\) \{(.*?)\n  \}", html, re.DOTALL).group(1)
    assert "const shop = shopUrl(availability.url);" in body and "availability.text" in body
    assert 'leftOutUnavailable: "No longer sold, so left out: {n}."' in html
    assert "data.left_out.unavailable" in html


# --- What is still to look up: python -m engine.prices todo ---

def by_name(question) -> dict[str, list[str]]:
    return {pick.name: pick.missing for pick in question.to_check}


def test_todo_lists_each_blind_test_pick_still_missing_an_entry_a_price_or_an_availability_check(tmp_path):
    made_up = [listed("Zojirushi kettle", available=True, price=80.0),  # nothing missing
               listed("Fellow Stagg kettle", available=None, price=150.0)]  # its availability
    questions = questions_file(tmp_path, [REQUEST, "best laptop for uni"])
    kettle, laptop = prices.todo(questions, three_kettles(tmp_path), made_up)
    assert (kettle.id, kettle.product_type, kettle.category, kettle.picks) == ("b01", "electric kettle", "kitchen", 3)
    assert by_name(kettle) == {"Fellow Stagg kettle": ["availability"], "Bonavita kettle": ["entry"]}
    assert (laptop.id, laptop.picks, laptop.to_check) == ("b02", 0, [])

    only_sold = [listed("Bonavita kettle", available=True)]
    [kettle] = prices.todo(questions_file(tmp_path, [REQUEST]), three_kettles(tmp_path / "2"), only_sold)
    assert by_name(kettle)["Bonavita kettle"] == ["price"]
    assert by_name(kettle)["Zojirushi kettle"] == ["entry"]


def test_todo_skips_products_no_longer_sold_and_brand_picks(tmp_path):
    gone = [listed("Bonavita kettle", available=False)]
    [kettle] = prices.todo(questions_file(tmp_path, [REQUEST]), three_kettles(tmp_path), gone)
    assert "Bonavita kettle" not in by_name(kettle) and kettle.picks == 2  # no longer sold: not a pick
    [skillet] = prices.todo(questions_file(tmp_path, ["cast iron skillet that lasts"]), skillet_library(tmp_path / "2"), [])
    assert "Lodge (their cast iron skillets)" not in by_name(skillet)  # a brand pick is never priced
    assert "Lodge (their cast iron skillets)" in skillet.brand_picks


def test_todo_runs_without_live_checks(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "live_checker", lambda: pytest.fail("todo must not read Reddit"))
    lib = three_kettles(tmp_path)
    restamp(lib, "1kett01", read_from="arctic_shift")  # waiting for its live check: still counted
    [kettle] = prices.todo(questions_file(tmp_path, [REQUEST]), lib, [])
    assert kettle.picks == 3 and set(by_name(kettle)) == {"Zojirushi kettle", "Fellow Stagg kettle", "Bonavita kettle"}


def test_command_line_todo_prints_names_and_product_types_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pipeline, "cached_profiles", lambda: None)
    made_up = [listed("Zojirushi kettle", available=True, price=80.0), listed("Fellow Stagg kettle", available=None, price=150.0)]
    questions = questions_file(tmp_path, [REQUEST, "best laptop for uni", "cast iron skillet that lasts"])
    lib = three_kettles(tmp_path)
    for path in (skillet_library(tmp_path / "skillets") / "threads").iterdir():  # one library with both
        (lib / "threads" / path.name).write_bytes(path.read_bytes())
        extraction = path.parent.parent / "extracted" / path.name
        (lib / "extracted" / path.name).write_bytes(extraction.read_bytes())
    assert prices.main(["todo"], questions_path=questions, library_dir=lib, prices=made_up) == 0
    out = capsys.readouterr().out
    assert "  b01 electric kettle (kitchen)\n" in out
    assert "    Fellow Stagg kettle: availability not checked yet\n" in out
    assert "    Bonavita kettle: no entry yet\n" in out
    assert "Zojirushi kettle" not in out  # nothing missing
    assert "  b02: no picks\n" in out
    assert "  b03 cast iron skillet (kitchen)\n" in out
    assert "    Lodge (their cast iron skillets): a brand pick, never priced or checked\n" in out
    assert out.rstrip().endswith("2 picks to look up: 1 with no entry yet, 1 with an entry still missing a price or "
                                 "an availability check.")
    assert "lasted" not in out and "years" not in out  # never a quote


def test_todo_also_lists_the_products_next_in_line_after_the_picks(tmp_path, monkeypatch, capsys):
    # Found on 10 Oct 2026: pricing a pick over budget let the next, unpriced product in (b09: the Comandante C40,
    # then the Baratza Sette 270, both over £150). So the products right behind the picks are looked up too.
    from engine.tests.test_product_facts import retinol_library

    questions = questions_file(tmp_path, ["best retinol"])
    [retinol] = prices.todo(questions, retinol_library(tmp_path), [])
    shown = set(by_name(retinol))
    assert retinol.picks == 3 and len(shown) == 3
    assert [item.name for item in retinol.next_in_line] == [
        name for name in ("Differin Gel", "The Ordinary Retinol in Squalane", "CeraVe Resurfacing Retinol Serum")
        if name not in shown]
    assert retinol.next_in_line[0].missing == ["entry"]
    monkeypatch.setattr(pipeline, "cached_profiles", lambda: None)
    assert prices.main(["todo"], questions_path=questions, library_dir=tmp_path / "library", prices=[]) == 0
    assert f"    next in line: {retinol.next_in_line[0].name}: no entry yet\n" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [[], ["todo", "now"], ["fetch"]])
def test_command_line_todo_explains_itself_when_used_wrongly(tmp_path, capsys, argv):
    assert prices.main(argv, questions_path=tmp_path / "none.json", library_dir=tmp_path, prices=[]) == 2
    assert "python -m engine.prices todo" in capsys.readouterr().out
