"""A region choice (Noemi, 24 Oct 2026: "the tool should work for visitors anywhere, not just the UK ... country-aware
availability: ok, do it now").

The page offers UK (the default), US and Elsewhere; the API takes an optional "region" in the POST body. A region
changes only the price and availability lines: which picks are shown and their order never change (Noemi's decision
(c) of 19 Oct 2026: no country preference anywhere in ranking), and in the UK region every answer is exactly as it was.
Wording approved by Noemi, 25 Oct 2026 (it was PROPOSED; engine/answer.py). Every text and shop here is made up; no test reaches the network.
"""

import io
import json
import re
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from engine import answer as wording
from engine import config, web
from engine.answer import answer_to_dict, render_markdown, write_answer
from engine.pipeline import answer_request
from engine.prices import Price, PriceCheck, UsSale, us_sale
from engine.tests.test_answer import kitchen_case, shown_text
from engine.tests.test_web import REQUEST, kettle_library
from engine.tests.test_web_public import function_body, page_text, script_of, settings_of

TODAY = date(2026, 10, 9)
SHOP = "Made-up Kitchen Shop"
US_SHOP = "Made-up US Shop"
STAGG_AT_WALMART = "https://www.walmart.com/ip/fellow-stagg-kettle"


def listed(product: str, *, price: float | None = None, currency: str = "GBP", available: bool | None = True,
           shop: str = SHOP, url: str | None = None, not_in_uk: bool = False, sources: tuple[str, ...] = (),
           second_hand: bool = False, checked_on: date = TODAY) -> Price:
    """One line of a made-up price list."""
    url = url or f"https://shop.example/{product.lower().replace(' ', '-')}"
    return Price(product=product, category="kitchen", price=price, currency=currency, shop=shop, url=url,
                 checked_on=checked_on, available=available, not_in_uk=not_in_uk, sources=list(sources),
                 second_hand=second_hand)


def sold_in_the_us(product: str, price: float | None = None, **more) -> Price:
    """A US shop's page for a product the list says is not sold in the UK: a USD entry."""
    return listed(product, price=price, currency="USD", available=False, not_in_uk=True, shop=US_SHOP,
                  url=f"https://us-shop.example/{product.lower().replace(' ', '-')}", **more)


def not_sold_here(product: str, **more) -> Price:
    return listed(product, available=False, not_in_uk=True, **more)


# --- The regions ---

def test_the_regions_are_uk_us_and_elsewhere_and_the_default_is_the_uk():
    assert config.REGIONS == ("uk", "us", "elsewhere") and config.DEFAULT_REGION == "uk"


# --- What the price list holds about the US (engine.prices.us_sale) ---

def test_a_usd_entry_that_is_not_discontinued_is_evidence_of_a_us_sale_with_its_price():
    entry = sold_in_the_us("Fellow Stagg kettle", price=150.0)
    sold, priced = us_sale([listed("Fellow Stagg kettle", available=False, not_in_uk=True), entry])
    assert sold == UsSale(US_SHOP, entry.url, TODAY) and priced is entry
    # A USD entry with no price still says where it is sold (the entry's currency is its shop's).
    sold, priced = us_sale([sold_in_the_us("Fellow Stagg kettle")])
    assert sold is not None and sold.shop == US_SHOP and priced is None


def test_a_discontinued_product_is_not_sold_in_the_us_either():
    gone = listed("Fellow Stagg kettle", price=150.0, currency="USD", available=False, shop=US_SHOP,
                  sources=(STAGG_AT_WALMART,))  # no longer made: not_in_uk is false
    assert us_sale([gone]) == (None, None)


def test_a_known_us_shops_page_among_an_entrys_sources_is_evidence_under_the_shops_own_name():
    entry = not_sold_here("Fellow Stagg kettle", sources=(STAGG_AT_WALMART,))
    sold, priced = us_sale([entry])
    assert sold == UsSale("Walmart", STAGG_AT_WALMART, TODAY) and priced is None
    assert config.US_SHOPS["walmart.com"] == "Walmart"


def test_an_entry_with_no_us_shop_in_it_is_no_evidence():
    uk = listed("Zojirushi kettle", price=120.0, sources=("https://www.johnlewis.com/zojirushi", "https://forum.example/t"))
    assert us_sale([uk, not_sold_here("Bonavita kettle")]) == (None, None)
    assert us_sale([]) == (None, None)


def test_a_shop_is_matched_by_its_exact_address_not_by_a_subdomain_or_a_lookalike():
    # "global.danner.com" is the maker's international store; "notwalmart.com" and "walmart.com.example" are other sites.
    for page in ("https://global.danner.com/boots", "https://www.notwalmart.com/x", "https://walmart.com.example/x"):
        assert us_sale([not_sold_here("Danner boots", sources=(page,))]) == (None, None), page
    assert us_sale([not_sold_here("Danner boots", sources=("https://www.danner.com/boots",))])[0] is not None
    assert us_sale([not_sold_here("Walmart thing", sources=("https://walmart.com/x",))])[0] is not None


def test_the_newest_check_is_the_us_sale_and_the_newest_cheapest_usd_price_its_price():
    older = sold_in_the_us("Fellow Stagg kettle", price=120.0, checked_on=date(2026, 9, 1))
    newer = sold_in_the_us("Fellow Stagg kettle", price=150.0)
    cheaper = sold_in_the_us("Fellow Stagg kettle", price=140.0)
    sold, priced = us_sale([older, newer, cheaper])
    assert sold.checked_on == TODAY and priced is cheaper


# --- The wording: what each region says ---

def checks_for(**by_key) -> dict[str, PriceCheck]:
    return by_key


def knife_checks() -> dict[str, PriceCheck]:
    """Tojiro: sold and priced in the UK. Global: sold only abroad, a US shop sells it. Victorinox: sold only abroad,
    nothing known of the US."""
    tojiro = listed("Tojiro DP Gyuto", price=120.0)
    us_global = sold_in_the_us("Global G-2", price=99.0)
    sale, priced = us_sale([us_global])
    return {
        "tojiro-dp-gyuto": PriceCheck(tojiro, "no budget", availability=tojiro),
        "global-g-2": PriceCheck(None, "no budget", availability=us_global, us_sold=sale, us_price=priced),
        "victorinox-fibrox": PriceCheck(None, "no budget", availability=not_sold_here("Victorinox Fibrox")),
    }


def answers_by_region(checks=None, **more):
    ranking, bodies, _ = kitchen_case()
    checks = knife_checks() if checks is None else checks
    return {region: write_answer(ranking, bodies, "chef knife", checks, region=region, **more)
            for region in config.REGIONS}


def test_the_uk_region_is_exactly_as_it_was():
    ranking, bodies, _ = kitchen_case()
    checks = knife_checks()
    before = write_answer(ranking, bodies, "chef knife", checks)
    assert write_answer(ranking, bodies, "chef knife", checks, region="uk") == before
    tojiro, global_g2, victorinox = before.picks
    assert tojiro.price.text == "£120 at Made-up Kitchen Shop, checked 9 Oct 2026"
    assert tojiro.availability.text == "Sold at Made-up Kitchen Shop, checked 9 Oct 2026"
    assert global_g2.availability.text == "Not sold in the UK, checked 9 Oct 2026"
    assert victorinox.availability.text == "Not sold in the UK, checked 9 Oct 2026" and victorinox.price.text == ""


def test_the_wording_for_other_regions_is_proposed_and_listed_in_one_place():
    # Every new string, as PROPOSED for Noemi (DECISIONS.md, 24 Oct 2026).
    assert wording.PRICE_IN_UK == "{amount} in the UK, at {shop}, checked {date}"
    assert wording.PRICE_FROM_IN_UK == "From {amount} in the UK, at {shop}, checked {date}"
    assert wording.PRICE_IN_US == "{amount} in the US, at {shop}, checked {date}"
    assert wording.AVAILABILITY_IN_UK == "Sold in the UK at {shop}, checked {date}"
    assert wording.AVAILABILITY_IN_UK_SECOND_HAND == "Sold second-hand only in the UK: {shop}, checked {date}"
    assert wording.AVAILABILITY_IN_US == "Sold in the US at {shop}, checked {date}"
    assert wording.AVAILABILITY_US_UNKNOWN == "Availability in the US not checked yet"


def test_the_us_region_says_a_uk_price_is_in_the_uk_and_a_us_sale_is_in_the_us():
    tojiro, global_g2, victorinox = answers_by_region()["us"].picks
    assert tojiro.price.text == "£120 in the UK, at Made-up Kitchen Shop, checked 9 Oct 2026"
    assert (tojiro.price.amount, tojiro.price.currency, tojiro.price.shop) == (120.0, "GBP", SHOP)
    assert tojiro.availability.text == "Sold in the UK at Made-up Kitchen Shop, checked 9 Oct 2026"
    assert tojiro.availability.available is True
    # Sold only abroad, a US shop's page in the list: it says so, with the shop and the day, and its price is the US one.
    assert global_g2.availability.text == "Sold in the US at Made-up US Shop, checked 9 Oct 2026"
    assert (global_g2.availability.available, global_g2.availability.shop) == (True, US_SHOP)
    # The price line links to that very page, so the availability line doesn't link a second time.
    assert global_g2.price.url == "https://us-shop.example/global-g-2" and global_g2.availability.url is None
    assert global_g2.price.text == "$99 in the US, at Made-up US Shop, checked 9 Oct 2026"
    assert (global_g2.price.amount, global_g2.price.currency) == (99.0, "USD")
    # Sold only abroad, nothing known of the US: honest about it, and never "Not sold in the UK".
    assert victorinox.availability.text == wording.AVAILABILITY_US_UNKNOWN
    assert (victorinox.availability.available, victorinox.availability.shop) == (None, None)


def test_the_elsewhere_region_is_neutral_and_never_says_not_sold_in_the_uk():
    tojiro, global_g2, victorinox = answers_by_region()["elsewhere"].picks
    assert tojiro.price.text == "£120 in the UK, at Made-up Kitchen Shop, checked 9 Oct 2026"
    assert tojiro.availability.text == "Sold in the UK at Made-up Kitchen Shop, checked 9 Oct 2026"
    assert global_g2.availability.text == "Sold in the US at Made-up US Shop, checked 9 Oct 2026"
    assert victorinox.availability.text == wording.AVAILABILITY_UNKNOWN
    assert (victorinox.availability.available, victorinox.price.text) == (None, wording.PRICE_UNKNOWN)


@pytest.mark.parametrize("region", ["us", "elsewhere"])
def test_no_other_region_is_told_not_sold_in_the_uk_anywhere_in_the_answer(region):
    answer = answers_by_region()[region]
    text = shown_text(answer)
    assert "Not sold in the UK" not in text and "not sold in the UK" not in text
    assert "Not sold in the UK" in shown_text(answers_by_region()["uk"])  # the UK region still says it


def test_a_product_sold_in_both_says_the_visitors_own_side_first():
    tojiro = listed("Tojiro DP Gyuto", price=120.0)
    sale, priced = us_sale([sold_in_the_us("Tojiro DP Gyuto", price=140.0)])
    checks = {"tojiro-dp-gyuto": PriceCheck(tojiro, "no budget", availability=tojiro, us_sold=sale, us_price=priced)}
    answers = answers_by_region(checks)
    us, elsewhere = answers["us"].picks[0].availability, answers["elsewhere"].picks[0].availability
    assert us.text == ("Sold in the US at Made-up US Shop, checked 9 Oct 2026; "
                       "sold in the UK at Made-up Kitchen Shop, checked 9 Oct 2026")
    assert elsewhere.text == ("Sold in the UK at Made-up Kitchen Shop, checked 9 Oct 2026; "
                              "sold in the US at Made-up US Shop, checked 9 Oct 2026")
    # The UK price is the pipeline's price (the budget note is about it); the US price is only a fallback for it.
    assert answers["us"].picks[0].price.text == "£120 in the UK, at Made-up Kitchen Shop, checked 9 Oct 2026"


def test_second_hand_and_brand_line_prices_keep_their_meaning_in_other_regions():
    second_hand = listed("Tojiro DP Gyuto", second_hand=True, shop="eBay UK")
    from_price = listed("Global G-2", price=25.0, shop="John Lewis")
    checks = {"tojiro-dp-gyuto": PriceCheck(None, "no budget", availability=second_hand),
              "global-g-2": PriceCheck(from_price, "no budget", availability=from_price, from_price=True)}
    tojiro, global_g2, _ = answers_by_region(checks)["us"].picks
    assert tojiro.availability.text == "Sold second-hand only in the UK: eBay UK, checked 9 Oct 2026"
    assert tojiro.availability.second_hand is True
    assert global_g2.price.text == "From £25 in the UK, at John Lewis, checked 9 Oct 2026"
    assert global_g2.price.from_price is True


def test_a_product_nothing_is_known_of_says_so_in_every_region():
    for region, answer in answers_by_region({}).items():
        for pick in answer.picks:
            assert pick.availability.text == wording.AVAILABILITY_UNKNOWN, region
            assert pick.price.text == wording.PRICE_UNKNOWN, region


def test_the_budget_note_is_the_same_in_every_region():
    tojiro = listed("Tojiro DP Gyuto", price=120.0)
    from engine.query import Budget
    checks = {"tojiro-dp-gyuto": PriceCheck(tojiro, "within", Budget(max=200, currency="GBP"), availability=tojiro)}
    notes = {region: (a.picks[0].price.budget_status, a.picks[0].price.budget_note)
             for region, a in answers_by_region(checks).items()}
    assert len(set(notes.values())) == 1 and notes["uk"][0] == "within"


def test_which_picks_are_shown_and_their_order_never_change_with_the_region():
    # Noemi's decision (c) of 19 Oct 2026: no country preference anywhere in ranking; a region changes two lines only.
    answers = answers_by_region()

    def without_the_two_lines(answer):
        data = answer_to_dict(answer)
        for item in data["picks"] + data["worth_a_look"]:
            item.pop("price"), item.pop("availability")
        return data

    assert [p.name for p in answers["uk"].picks] == ["Tojiro DP Gyuto", "Global G-2", "Victorinox Fibrox"]
    for region in ("us", "elsewhere"):
        assert without_the_two_lines(answers[region]) == without_the_two_lines(answers["uk"]), region


def test_the_json_of_other_regions_has_the_same_fields_as_the_uks():
    answers = answers_by_region()
    for region in ("us", "elsewhere"):
        for here, there in zip(answers[region].picks, answers["uk"].picks):
            shown, usual = answer_to_dict(replace(answers[region], picks=[here]))["picks"][0], \
                answer_to_dict(replace(answers["uk"], picks=[there]))["picks"][0]
            assert set(shown) == set(usual)
            assert set(shown["price"]) == set(usual["price"]) and set(shown["availability"]) == set(usual["availability"])


def test_the_text_answer_is_the_uks_whatever_a_region_asks():
    ranking, bodies, _ = kitchen_case()
    checks = knife_checks()
    assert render_markdown(write_answer(ranking, bodies, "chef knife", checks, region="uk")) == render_markdown(
        write_answer(ranking, bodies, "chef knife", checks))


# --- The pipeline: the same picks, other lines ---

def kettle_prices() -> list[Price]:
    return [listed("Zojirushi kettle", price=120.0),
            not_sold_here("Fellow Stagg kettle", sources=(STAGG_AT_WALMART,)),
            not_sold_here("Bonavita kettle")]


def test_a_region_changes_the_two_lines_of_a_real_answer_and_nothing_else(tmp_path):
    library = kettle_library(tmp_path)
    results = {region: answer_request(REQUEST, library, prices=kettle_prices(), today=TODAY, region=region)
               for region in config.REGIONS}
    uk = results["uk"].answer
    assert answer_request(REQUEST, library, prices=kettle_prices(), today=TODAY).answer == uk  # no region: the UK's
    assert len(uk.picks) == 3
    for region in ("us", "elsewhere"):
        other = results[region].answer
        assert [p.name for p in other.picks] == [p.name for p in uk.picks]
        assert results[region].threads_used == results["uk"].threads_used
        assert [(p.reason, p.support, [q.text for q in p.quotes]) for p in other.picks] == [
            (p.reason, p.support, [q.text for q in p.quotes]) for p in uk.picks]
    by_name = {p.name: p.availability.text for p in results["us"].answer.picks}
    assert by_name == {"Zojirushi kettle": "Sold in the UK at Made-up Kitchen Shop, checked 9 Oct 2026",
                       "Fellow Stagg kettle": "Sold in the US at Walmart, checked 9 Oct 2026",
                       "Bonavita kettle": wording.AVAILABILITY_US_UNKNOWN}
    by_name = {p.name: p.availability.text for p in uk.picks}
    assert by_name["Fellow Stagg kettle"] == "Not sold in the UK, checked 9 Oct 2026"


def test_an_unknown_region_is_a_programming_error_not_a_quiet_default(tmp_path):
    with pytest.raises(ValueError):
        answer_request(REQUEST, kettle_library(tmp_path), prices=[], today=TODAY, region="mars")


# --- The API: "region" in the POST body ---

@pytest.fixture(autouse=True)
def fresh_cache():
    web.clear_answer_cache()
    yield
    web.clear_answer_cache()


def post(library_dir: Path, **body) -> tuple[int, str, bytes]:
    data = json.dumps({"request": REQUEST, **body}).encode("utf-8")
    return web.handle_answer("application/json", str(len(data)), io.BytesIO(data).read, library_dir)


@pytest.fixture
def priced(monkeypatch):
    """The web's pipeline run on made-up prices; every call is noted (its keywords too)."""
    calls = []

    def run(request, library_dir, **kwargs):
        calls.append(kwargs)
        return answer_request(request, library_dir, prices=kettle_prices(), today=TODAY, **kwargs)

    monkeypatch.setattr(web, "answer_request", run)
    return calls


def test_without_a_region_or_with_the_uk_the_answer_is_the_same_bytes_and_has_no_new_field(tmp_path, priced):
    library = kettle_library(tmp_path)
    plain = post(library)
    assert "region" not in json.loads(plain[2])
    web.clear_answer_cache()

    def stripped(body: bytes) -> dict:
        data = json.loads(body)
        data.pop("timing")
        return data

    assert stripped(post(library, region="uk")[2]) == stripped(plain[2])
    assert stripped(post(library, region=None)[2]) == stripped(plain[2])
    assert all(call == {} for call in priced)  # the UK is asked exactly as before: no new keyword


def test_a_region_in_the_body_changes_the_lines_and_the_answer_says_which_it_is_for(tmp_path, priced):
    library = kettle_library(tmp_path)
    uk, us = json.loads(post(library)[2]), json.loads(post(library, region="us")[2])
    elsewhere = json.loads(post(library, region="elsewhere")[2])
    assert (us["region"], elsewhere["region"]) == ("us", "elsewhere")
    assert set(us) == set(uk) | {"region"}
    names = [p["name"] for p in uk["answer"]["picks"]]
    assert [p["name"] for p in us["answer"]["picks"]] == names == [p["name"] for p in elsewhere["answer"]["picks"]]
    shown = {p["name"]: p["availability"]["text"] for p in us["answer"]["picks"]}
    assert shown["Fellow Stagg kettle"] == "Sold in the US at Walmart, checked 9 Oct 2026"
    assert "Not sold in the UK" in json.dumps(uk) and "Not sold in the UK" not in json.dumps(us)
    assert "Not sold in the UK" not in json.dumps(elsewhere)


def test_the_region_is_read_in_any_capitals_and_spaces(tmp_path, priced):
    library = kettle_library(tmp_path)
    assert json.loads(post(library, region=" US ")[2])["region"] == "us"
    assert json.loads(post(library, region="Elsewhere")[2])["region"] == "elsewhere"


@pytest.mark.parametrize("bad", ["mars", "", 5, True, ["us"], {"us": 1}])
def test_a_region_that_is_not_one_of_the_three_is_refused_in_plain_words(tmp_path, priced, bad):
    status, content_type, body = post(kettle_library(tmp_path), region=bad)
    data = json.loads(body)
    assert status == 400 and data["code"] == "bad_region" and "uk" in data["error"] and "elsewhere" in data["error"]
    assert priced == []  # nothing was worked out


def test_remembered_answers_are_kept_per_region(tmp_path, priced):
    library = kettle_library(tmp_path)
    first = post(library)
    post(library)
    assert len(priced) == 1  # asked again, the UK's answer is remembered
    us = post(library, region="us")
    assert len(priced) == 2 and priced[1] == {"region": "us"}  # another region is worked out for itself
    post(library, region="us")
    post(library, region="uk")
    assert len(priced) == 2
    elsewhere = post(library, region="elsewhere")
    assert len(priced) == 3 and priced[2] == {"region": "elsewhere"}
    assert len({first[2], us[2], elsewhere[2]}) == 3
    assert json.loads(post(library)[2])["answer"] == json.loads(first[2])["answer"]  # the UK's was never overwritten


def test_every_region_is_worked_out_again_after_the_threads_change(tmp_path, priced):
    library = kettle_library(tmp_path)
    post(library), post(library, region="us")
    web.clear_answer_cache()
    post(library), post(library, region="us")
    assert len(priced) == 4


def test_the_documented_error_for_a_bad_region_is_in_the_apis_notes():
    notes = web.__doc__
    assert "bad_region" in notes and '"region"' in notes


# --- Getting ready: the demo requests and the examples first ---

DEMO_FILE = Path(config.__file__).resolve().parent / "data" / "demo_requests.json"


def demo_requests() -> list[str]:
    return json.loads(DEMO_FILE.read_text(encoding="utf-8"))["demo"]


def test_getting_ready_warms_the_examples_and_then_the_demo_requests_before_anything_else():
    examples = [e["text"] for e in web.example_requests()]
    demo = demo_requests()
    assert examples and len(demo) == 62  # what Noemi may show at interviews (docs/bfs-2026-10-17/demo-requests.txt)
    first = list(dict.fromkeys(examples + demo))
    warmed = web.warm_requests()
    assert warmed[:len(first)] == first
    assert web.WARM_FIRST_FILES[:2] == (web.EXAMPLES_FILE, web.DEMO_FILE) and web.DEMO_FILE == DEMO_FILE


def test_the_demo_requests_warm_from_the_committed_copy_and_never_need_the_private_docs():
    # docs/ is private and never committed, so it is not in the site's image: the committed copy is what warms.
    assert "docs" not in DEMO_FILE.parts[-4:] and DEMO_FILE.is_file()
    assert web._requests_in(Path("/no/such/file.json")) == []


def test_warming_asks_for_no_more_product_types_than_the_answers_memory_keeps():
    # Memory as it is (config.ANSWERS_KEPT_TYPES): once answers have asked about more types than that, what they worked
    # out is forgotten, so a longer list would throw away the demo requests' warm work. Requests of types past the limit
    # are left to their first visitors, as the taxonomy's types are.
    from engine.pipeline import request_kind

    warmed = web.warm_requests()
    kinds = {request_kind(text) for text in warmed}
    assert len(kinds) <= config.ANSWERS_KEPT_TYPES
    assert len(warmed) == len(set(warmed))
    first = list(dict.fromkeys([e["text"] for e in web.example_requests()] + demo_requests()))
    assert {request_kind(text) for text in first} <= kinds  # none of the first ones is ever the one dropped


def test_the_warm_up_time_limit_and_the_startup_probe_are_as_they_were():
    import re as regex

    assert web.WARM_UP_ANSWERS_SECONDS == 90 and web.WARM_MORE_SECONDS == 40
    deploy = (Path(web.REPO_ROOT) / "deploy" / "cloudrun" / "deploy.sh").read_text(encoding="utf-8")
    period, threshold = (int(n) for n in regex.search(r"periodSeconds=(\d+),.*failureThreshold=(\d+)", deploy).groups())
    assert period * threshold == 240 and web.WARM_UP_ANSWERS_SECONDS * 2 < period * threshold
    assert "--memory 4Gi" in deploy


# --- The page: a small control, remembered in the browser only ---

def test_the_page_has_a_region_control_beside_the_search_box_with_the_uk_chosen_first(tmp_path):
    html = page_text(tmp_path)
    control = re.search(r'<select id="region"[^>]*>(.*?)</select>', html, re.DOTALL)
    assert control is not None
    assert re.findall(r'<option value="([a-z]+)"( selected)?', control.group(1)) == [
        ("uk", " selected"), ("us", ""), ("elsewhere", "")]
    assert html.index('id="q"') < html.index('id="region"') < html.index('id="steps-heading"')
    labels = re.search(r"const LABELS = \{(.*?)\n\};", html, re.DOTALL).group(1)
    for key in ("regionLabel", "regionUK", "regionUS", "regionElsewhere", "regionHint"):
        assert f"{key}:" in labels, key
    assert settings_of(html)["regions"] == list(config.REGIONS)


def test_the_page_sends_the_region_only_in_the_answers_own_request_and_keeps_it_in_the_browser(tmp_path):
    script = script_of(page_text(tmp_path))
    assert re.search(r"body: JSON\.stringify\(\{ request, region \}\)", script)
    assert len(re.findall(r"\bfetch\(", script)) == 2  # still only the answer and the feedback, to this site
    assert 'const REGION_KEY = "credible-recs:region";' in script
    assert re.findall(r"remember\(REGION_KEY, [^)]*\)", script) == ["remember(REGION_KEY, region)"]
    reading = function_body(script, "function currentRegion()")
    assert "recall(REGION_KEY)" in reading and "SETTINGS.regions.includes" in reading  # only a known value is believed


def test_choosing_another_region_asks_again_for_the_request_on_screen(tmp_path):
    script = script_of(page_text(tmp_path))
    changed = re.search(r'regionBox\.addEventListener\("change", \(\) => \{(.*?)\}\);', script, re.DOTALL).group(1)
    assert "remember(REGION_KEY, region)" in changed and "search(" in changed and "false" in changed


def test_the_how_page_says_the_region_stays_in_the_browser_and_travels_with_the_search(tmp_path):
    from engine.tests.test_how_page import text_of

    words = text_of(page_text(tmp_path, "/how"))
    assert "Your region." in words and "only to fit the price and availability lines" in words
    assert "never changes which products are picked" in words
