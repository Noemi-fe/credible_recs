"""Buyable picks, makers' images and direct links (Noemi's decisions of 15 Oct 2026, late afternoon).

From the live laptop answer, whose first pick was "MBPs from late 2010-2011", read from old BuyItForLife threads, with
"Price not checked yet" and no link: "what's the point of recommending it if i can't buy it? also why none have the links
to the products? or could we add a little image of the prod with the link?"
1. A pick must be on sale in the UK now: a discontinued model, or one not sold to UK shoppers, is left out and named;
   sold second-hand only counts only for things people buy vintage on purpose (her rule of 10 Oct: Griswold, Wagner).
   Availability comes from researched data, never guessed: a product nothing is known of stays, as before.
2. A pick, and an "Also worth a look" item, may show a small image from its maker's own product page, linked to that
   page, and a direct link to its own page (its maker's, or a big UK shop's).
3. No search links: a search is never linked, and a product not researched yet shows no link.

The library is made up, but its products carry the real names the live laptop answer showed on 15 Oct 2026; every
page, shop, image and price is made up.
"""

import json
import re
from datetime import date
from pathlib import Path

import pytest

from engine import answer as wording
from engine import config, web
from engine.answer import ShownImage, ShownLink, answer_to_dict, render_markdown, unverified_claims
from engine.buyable import import_findings
from engine.pipeline import answer_request
from engine.prices import Price, counts_as_sold, load_prices
from engine.product_pages import ProductPage, load_product_pages
from engine.tests.factories import make_comment, make_thread, write_gold
from engine.tests.test_second_hand import second_hand, vintage_library
from engine.tests.test_second_hand import REQUEST as SKILLET_REQUEST
from engine.tests.test_second_hand import GRISWOLD, WAGNER

TODAY = date(2026, 10, 9)
DAY = date(2026, 10, 8)
# The live laptop answer's picks and items, 15 Oct 2026.
MBP = "MBPs from late 2010-2011"
LEGION = "Legion Y540"
ROG = "ASUS ROG laptop"
DELL = "Dell Latitude 5300 13.3 Touchscreen"
AIR = "Maker Aircraft 13"  # a made-up laptop still sold
ROG_PAGE = "https://asus.example/uk/rog-laptops/"
ROG_IMAGE = "https://img.asus.example/rog-hero.png"


def comment(comment_id: str, thread_id: str, body: str, subreddit: str) -> dict:
    return make_comment(comment_id, thread_id=thread_id, body=body,
                        url=f"https://www.reddit.com/r/{subreddit}/comments/{thread_id}/comment/{comment_id}/")


def said(product: str, years: int) -> str:
    return f"My {product} has lasted {years} years and still works perfectly."


def laptop_library(tmp_path: Path, threads: dict | None = None) -> Path:
    """Laptop threads: {thread id: (title, posted, subreddit, [(comment id, product, years)])}. By default three, where
    the 2010-2011 MacBook Pros, the Legion Y540 and the ASUS ROG laptop are praised three times across two threads
    (picks), and the Dell Latitude and the Aircraft 13 twice (Also worth a look)."""
    threads = threads or {
        "1lap001": ("Best laptop to buy?", "2023-05-02T09:00:00Z", "laptops", [
            ("l1a", MBP, 12), ("l1b", LEGION, 4), ("l1c", ROG, 3), ("l1d", DELL, 4), ("l1e", AIR, 2)]),
        "1lap002": ("Which laptop lasts?", "2022-01-04T09:00:00Z", "BuyItForLife", [
            ("l2a", MBP, 11), ("l2b", LEGION, 3), ("l2c", ROG, 4), ("l2d", DELL, 3), ("l2e", AIR, 3)]),
        "1lap003": ("Laptop that lasts for university?", "2020-06-07T09:00:00Z", "SuggestALaptop", [
            ("l3a", MBP, 10), ("l3b", LEGION, 2), ("l3c", ROG, 2)]),
    }
    saved, extractions = [], {}
    for thread_id, (title, posted, subreddit, said_in) in threads.items():
        saved.append(make_thread(
            id=thread_id, community=subreddit, category="general", title=title, body="My old one died.",
            created_at=posted, url=f"https://www.reddit.com/r/{subreddit}/comments/{thread_id}/x/",
            comments=[comment(cid, thread_id, said(product, years), subreddit) for cid, product, years in said_in]))
        extractions[thread_id] = [
            {"comment_id": cid, "product": product, "category": "general", "product_type": "laptop",
             "stance": "recommend", "evidence": "long-term use", "evidence_tags": ["long-term use"],
             "quote": said(product, years)} for cid, product, years in said_in]
    root = write_gold(tmp_path / "library", saved, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for thread_id, mentions in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v12", "extracted_at": "2026-10-08T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions}), encoding="utf-8")
    return root


def entry(product: str, available: bool | None = True, price: float | None = None, second_hand: bool = False,
          url: str | None = None, shop: str = "Big Shop", checked_on: date = DAY, product_type: str | None = "laptop",
          category: str = "general") -> Price:
    return Price(product=product, category=category, product_type=product_type, price=price, currency="GBP",
                 shop=shop, url=url or f"https://shop.example/{product.lower().replace(' ', '-')}",
                 checked_on=checked_on, available=available, second_hand=second_hand)


def page(product: str, image: bool = True, url: str = ROG_PAGE, shop: str = "ASUS", product_type: str | None = "laptop",
         image_page: str | None = None, category: str = "general") -> ProductPage:
    image_page = image_page or url
    return ProductPage(product=product, category=category, product_type=product_type, page=url, shop=shop,
                       image=ROG_IMAGE if image else None, image_page=image_page if image else None,
                       sources=list(dict.fromkeys([url, image_page])), checked_on=DAY)


def laptops(tmp_path, prices=(), pages=(), request: str = "laptop", **kwargs):
    return answer_request(request, library_dir=laptop_library(tmp_path), prices=list(prices),
                          product_pages=list(pages), product_facts=[], brand_lines=[], today=TODAY, **kwargs)


def names(result) -> tuple[list[str], list[str]]:
    return [p.name for p in result.answer.picks], [w.name for w in result.answer.worth_a_look]


def shown(result, name: str):
    return next(p for p in result.answer.picks + result.answer.worth_a_look if p.name == name)


# --- 1. Buyable ---

def test_with_nothing_researched_the_laptop_answer_is_as_before(tmp_path):
    result = laptops(tmp_path)
    picks, items = names(result)
    assert sorted(picks) == sorted([MBP, LEGION, ROG]) and sorted(items) == sorted([DELL, AIR])
    assert result.left_out_unavailable == []
    assert shown(result, MBP).availability.text == wording.AVAILABILITY_UNKNOWN  # never guessed
    assert shown(result, MBP).link is None and shown(result, MBP).image is None


def test_a_discontinued_model_is_left_out_and_named(tmp_path):
    result = laptops(tmp_path, prices=[entry(MBP, available=False), entry(LEGION, available=False)])
    picks, items = names(result)
    assert MBP not in picks + items and LEGION not in picks + items
    assert sorted(result.left_out_unavailable) == sorted([MBP, LEGION])
    # The next products take their places: what is on sale moves up.
    assert ROG in picks and DELL in picks + items and AIR in picks + items
    assert unverified_claims(result.answer, result.bodies) == []


def test_a_laptop_sold_only_used_isnt_on_sale_now_but_vintage_cast_iron_is():
    used = entry(DELL, second_hand=True)
    assert counts_as_sold(used) is False  # a used 2019 laptop isn't bought vintage on purpose
    assert counts_as_sold(second_hand(WAGNER)) is True and counts_as_sold(second_hand("Griswold")) is True
    assert counts_as_sold(entry(AIR)) is True and counts_as_sold(entry(AIR, available=False)) is False
    assert counts_as_sold(entry(AIR, available=None, price=999.0)) is None and counts_as_sold(None) is None


def test_her_rule_of_10_october_names_griswold_and_wagner():
    assert {"Griswold", "Wagner"} <= set(config.SECOND_HAND_VINTAGE["kitchen"])


def test_a_product_sold_second_hand_only_that_isnt_vintage_is_left_out_and_named(tmp_path):
    result = laptops(tmp_path, prices=[entry(DELL, second_hand=True)])
    assert DELL not in sum(names(result), []) and result.left_out_unavailable == [DELL]


def test_vintage_cast_iron_sold_second_hand_only_still_counts_as_sold(tmp_path):
    result = answer_request(SKILLET_REQUEST, library_dir=vintage_library(tmp_path), product_facts=[], today=TODAY,
                            prices=[second_hand(WAGNER), second_hand("Griswold")])
    assert {GRISWOLD, WAGNER} <= {p.name for p in result.answer.picks}
    assert shown(result, WAGNER).availability.second_hand is True and result.left_out_unavailable == []


def test_a_brand_sold_second_hand_only_that_isnt_bought_vintage_on_purpose_leaves_its_line_out(tmp_path, monkeypatch):
    # As Rival's American crock pots: their entry says sold second-hand only, which counts only for vintage on purpose.
    monkeypatch.setattr("engine.prices.SECOND_HAND_VINTAGE", {"kitchen": ("Wagner",)})
    result = answer_request(SKILLET_REQUEST, library_dir=vintage_library(tmp_path), product_facts=[], today=TODAY,
                            prices=[second_hand("Griswold")])
    assert GRISWOLD not in {p.name for p in result.answer.picks} and GRISWOLD in result.left_out_unavailable


def test_the_answer_names_what_it_left_out_as_not_on_sale(tmp_path, monkeypatch):
    made_up = [entry(MBP, available=False), entry(LEGION, available=False)]
    monkeypatch.setattr(web, "answer_request", lambda request, library_dir: answer_request(
        request, library_dir, prices=made_up, product_pages=[], product_facts=[], brand_lines=[], today=TODAY))
    data = web.answer_json(web.answer_request("laptop", laptop_library(tmp_path)))
    assert data["left_out"]["unavailable"] == 2
    assert sorted(data["left_out"]["unavailable_names"]) == sorted([MBP, LEGION])


# --- 2. Its own page and its maker's image ---

def test_a_pick_on_sale_links_to_its_own_page_and_shows_its_makers_image(tmp_path):
    result = laptops(tmp_path, prices=[entry(ROG, shop="ASUS", url=ROG_PAGE)], pages=[page(ROG)])
    rog = shown(result, ROG)
    assert rog.image == ShownImage(url=ROG_IMAGE, alt=ROG, page=ROG_PAGE)
    # Its price-list entry already links to the same page ("Sold at ASUS ... see it at the shop"): no second link.
    assert rog.availability.url == ROG_PAGE and rog.link is None


def test_a_page_the_price_lines_dont_link_to_gets_its_own_link_with_the_day_it_was_checked(tmp_path):
    result = laptops(tmp_path, pages=[page(ROG)])
    rog = shown(result, ROG)
    assert rog.link == ShownLink(text="See it at ASUS", url=ROG_PAGE, shop="ASUS", checked="checked 8 Oct 2026",
                                 checked_on="2026-10-08")
    assert rog.availability.text == wording.AVAILABILITY_UNKNOWN  # a page alone never says it is sold
    text = render_markdown(result.answer)
    assert f"[See it at ASUS]({ROG_PAGE}) · checked 8 Oct 2026" in text
    assert ROG_IMAGE not in text  # the text answer carries no images


def test_an_also_worth_a_look_item_shows_them_too(tmp_path):
    air = page(AIR, url="https://maker.example/uk/aircraft-13/", shop="Maker")
    result = laptops(tmp_path, pages=[air])
    item = shown(result, AIR)
    assert item in result.answer.worth_a_look
    assert item.link.url == "https://maker.example/uk/aircraft-13/" and item.image.page == air.image_page


def test_the_image_links_to_the_makers_page_it_came_from_and_the_link_to_the_products_own_page(tmp_path):
    shop_page = page(ROG, url="https://bigshop.example/asus-rog-14/p77", shop="Big Shop", image_page=ROG_PAGE)
    rog = shown(laptops(tmp_path, pages=[shop_page]), ROG)
    assert rog.link.url == "https://bigshop.example/asus-rog-14/p77" and rog.link.text == "See it at Big Shop"
    assert rog.image.page == ROG_PAGE


def test_a_product_not_researched_shows_no_link_and_no_image(tmp_path):
    result = laptops(tmp_path, pages=[page(ROG)])
    assert all(p.link is None and p.image is None for p in result.answer.picks + result.answer.worth_a_look
               if p.name != ROG)


def test_a_page_for_another_type_of_product_is_never_shown(tmp_path):
    assert shown(laptops(tmp_path, pages=[page(ROG, product_type="monitor")]), ROG).link is None


def test_a_left_out_product_is_never_linked(tmp_path):
    result = laptops(tmp_path, prices=[entry(MBP, available=False)], pages=[page(MBP)])
    assert MBP not in sum(names(result), [])


def test_the_page_and_the_image_reach_the_json(tmp_path):
    data = json.loads(json.dumps(answer_to_dict(laptops(tmp_path, pages=[page(ROG)]).answer)))
    rog = next(p for p in data["picks"] if p["name"] == ROG)
    assert rog["image"] == {"url": ROG_IMAGE, "alt": ROG, "page": ROG_PAGE}
    assert rog["link"] == {"text": "See it at ASUS", "url": ROG_PAGE, "shop": "ASUS", "checked": "checked 8 Oct 2026",
                           "checked_on": "2026-10-08"}
    other = next(p for p in data["picks"] if p["name"] != ROG)
    assert other["image"] is None and other["link"] is None


def test_an_address_that_fails_its_check_is_never_shown_even_if_an_entry_was_built_by_hand(tmp_path):
    # The list refuses such entries as it loads; this is the second lock, as for range pages.
    unsafe = ProductPage.model_construct(**(page(ROG).model_dump() | {
        "page": "https://www.amazon.co.uk/s?k=asus+rog", "image": "http://img.asus.example/rog.png"}))
    rog = shown(laptops(tmp_path, pages=[unsafe]), ROG)
    assert rog.link is None and rog.image is None


# --- 3. No search links ---

def test_a_search_is_never_linked_its_words_stay(tmp_path):
    search = "https://www.ebay.co.uk/sch/i.html?_nkw=wagner+cast+iron+skillet"
    result = answer_request(SKILLET_REQUEST, library_dir=vintage_library(tmp_path), product_facts=[], today=TODAY,
                            prices=[second_hand(WAGNER, shop="eBay UK", url=search)])
    sold = shown(result, WAGNER).availability
    assert sold.text == "Sold second-hand only: eBay UK, checked 9 Oct 2026" and sold.url is None
    assert search not in render_markdown(result.answer)
    priced = laptops(tmp_path / "b", prices=[entry(ROG, price=999.0, url="https://shop.example/search?q=asus+rog")])
    assert shown(priced, ROG).price.text == "£999 at Big Shop, checked 8 Oct 2026" and shown(priced, ROG).price.url is None


# --- How an imported finding reaches a card ---

def test_imported_findings_reach_the_cards_of_the_answer_that_showed_them(tmp_path):
    findings = [
        {"name": MBP, "type": "laptop", "category": "general", "status": "discontinued", "product_page": None,
         "shop": "Apple", "price_gbp": None, "price_url": None, "image_url": None, "image_page": None,
         "sources": ["https://maker.example/uk/support/obsolete/"], "checked_on": "2026-10-08", "note": "Made up."},
        {"name": LEGION, "type": "laptop", "category": "general", "status": "discontinued", "product_page": None,
         "shop": "Lenovo", "price_gbp": None, "price_url": None, "image_url": None, "image_page": None,
         "sources": ["https://lenovo.example/uk/legion-y540/"], "checked_on": "2026-10-08", "note": "Made up."},
        {"name": DELL, "type": "laptop", "category": "general", "status": "second_hand_only", "product_page": None,
         "shop": "eBay UK", "price_gbp": None, "price_url": None, "image_url": None, "image_page": None,
         "sources": ["https://used.example/dell-latitude-5300"], "checked_on": "2026-10-08", "note": "Made up."},
        {"name": ROG, "type": "laptop", "category": "general", "status": "sold_new", "product_page": ROG_PAGE,
         "shop": "ASUS", "price_gbp": 1299.0, "price_url": ROG_PAGE, "image_url": ROG_IMAGE, "image_page": ROG_PAGE,
         "sources": [ROG_PAGE], "checked_on": "2026-10-08", "note": "Made up."},
        {"name": AIR, "type": "laptop", "category": "general", "status": "unsure", "product_page": None,
         "shop": None, "price_gbp": None, "price_url": None, "image_url": None, "image_page": None,
         "sources": [], "checked_on": "2026-10-08", "note": "Made up."},
    ]
    found = tmp_path / "found-laptops.jsonl"
    found.write_text("".join(json.dumps(f) + "\n" for f in findings), encoding="utf-8")
    prices_path, pages_path = tmp_path / "prices.json", tmp_path / "product_pages.json"
    prices_path.write_text('{"prices": []}\n', encoding="utf-8")
    pages_path.write_text('{"pages": []}\n', encoding="utf-8")
    import_findings([found], prices_path, pages_path, write=True)
    result = laptops(tmp_path, prices=load_prices(prices_path), pages=load_product_pages(pages_path))
    picks, items = names(result)
    assert sorted(result.left_out_unavailable) == sorted([MBP, LEGION, DELL])
    rog = shown(result, ROG)
    assert rog.price.text == "£1,299 at ASUS, checked 8 Oct 2026" and rog.price.url == ROG_PAGE
    assert rog.image.url == ROG_IMAGE and rog.link is None  # the price line links to its page already
    air = shown(result, AIR)  # unsure: as before
    assert air.availability.text == wording.AVAILABILITY_UNKNOWN and air.link is None
    assert unverified_claims(result.answer, result.bodies) == []


# --- The page ---

def page_html() -> str:
    return web.search_page().decode("utf-8")


def function_body(html: str, name: str) -> str:
    return re.search(rf"function {name}\([^)]*\) \{{(.*?)\n  \}}", html, re.DOTALL).group(1)


def test_each_card_shows_its_image_by_its_name_and_its_link_with_the_other_lines():
    html = page_html()
    pick_card, worth_card = function_body(html, "pickCard"), function_body(html, "worthCard")
    assert "productImage(pick.image)" in pick_card and "pageLine(pick.link)" in pick_card
    assert "productImage(item.image)" in worth_card and "pageLine(item.link)" in worth_card


def test_an_image_loads_only_when_on_screen_sends_no_referrer_has_its_text_and_links_to_its_page():
    body = function_body(page_html(), "productImage")
    assert "const src = rangeUrl(image.url);" in body and "const page = rangeUrl(image.page);" in body
    picture = re.search(r'el\("img", \{(.*?)\}\)', body, re.DOTALL).group(1)
    assert 'loading: "lazy"' in picture and 'referrerpolicy: "no-referrer"' in picture and "alt: image.alt" in picture
    # Set before the address, so the browser waits before fetching it.
    assert picture.index('loading: "lazy"') < picture.index("src")
    link = re.search(r'el\("a", \{(.*?)\}', body, re.DOTALL).group(1)
    assert "href: page" in link and 'rel: "noopener noreferrer"' in link and 'referrerpolicy: "no-referrer"' in link
    assert 'addEventListener("error"' in body  # one that can't load goes away


def test_a_products_link_goes_through_the_same_check_as_a_range_link():
    body = function_body(page_html(), "pageLine")
    assert "const address = rangeUrl(page.url);" in body and "page.text" in body and "page.checked" in body


def test_the_page_names_what_it_left_out_as_not_on_sale():
    html = page_html()
    assert 'leftOutUnavailable: "Not on sale in the UK now, so left out: {n}{names}."' in html
    assert "data.left_out.unavailable_names" in html


def test_the_security_policy_lets_in_only_the_makers_images_over_https(monkeypatch):
    listed = [page(ROG), page(AIR, url="https://maker.example/uk/aircraft-13/", shop="Maker")]
    listed[1] = listed[1].model_copy(update={"image": "https://cdn.maker.example/a13.jpg"})
    monkeypatch.setattr(web, "load_product_pages", lambda *args, **kwargs: listed)
    local = web.security_headers(web.LOCAL)["Content-Security-Policy"]
    assert "img-src https://cdn.maker.example https://img.asus.example;" in local
    # The rest of the policy as tight as before: local mode's own, with the images only.
    assert local.replace("img-src https://cdn.maker.example https://img.asus.example; ", "") == (
        web.HEADERS["Content-Security-Policy"])
    assert not re.search(r"data:|blob:|\bhttps:(?!//)|\*", local)  # no other scheme, no whole-web https:, no wildcard
    counted = web.security_headers(web.Site(public=True, hosts=("demo.example",), goatcounter="credible-recs"))
    assert ("img-src https://credible-recs.goatcounter.com https://cdn.maker.example https://img.asus.example;"
            in counted["Content-Security-Policy"])


def test_without_makers_images_the_policy_is_as_before(monkeypatch):
    monkeypatch.setattr(web, "load_product_pages", lambda *args, **kwargs: [page(ROG, image=False)])
    assert web.security_headers(web.LOCAL) == web.HEADERS
    assert "img-src" not in web.HEADERS["Content-Security-Policy"]


# --- The how page ---

def how_page() -> str:
    from engine import how_page as how

    return how.page()


def test_the_how_page_says_images_load_from_the_makers_site_which_sees_the_address_but_never_the_search():
    privacy = how_page().split('id="privacy"')[1]
    assert "Product images." in privacy and "from the maker's site" in privacy
    assert "the maker sees your IP address" in privacy and "never what you searched for" in privacy
    assert "no referrer" in privacy


def test_the_how_page_says_what_isnt_on_sale_is_left_out_and_named_and_links_are_direct():
    html = how_page()
    assert "Not on sale in the UK now." in html and "discontinued model, it's left out and named" in html
    assert "vintage on purpose, such as Griswold and Wagner cast iron" in html
    assert "“See it at John Lewis”" in html and "We never link to a search" in html


def test_only_pages_carry_the_makers_image_hosts_the_apis_json_loads_no_image(monkeypatch):
    monkeypatch.setattr(web, "load_product_pages", lambda *args, **kwargs: [page(ROG)])
    assert "img-src https://img.asus.example;" in web.security_headers(web.LOCAL)["Content-Security-Policy"]
    assert web.security_headers(web.LOCAL, page=False) == web.HEADERS


def test_the_server_sends_the_image_hosts_with_its_pages_only(tmp_path, monkeypatch):
    import threading
    import urllib.error
    import urllib.request

    monkeypatch.setattr(web, "load_product_pages", lambda *args, **kwargs: [page(ROG)])
    server = web.make_server(port=0, library_dir=tmp_path / "library")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base}/", timeout=10) as response:
            assert "img-src https://img.asus.example;" in response.headers["Content-Security-Policy"]
        with pytest.raises(urllib.error.HTTPError) as empty:  # an empty request: the API's JSON error
            urllib.request.urlopen(f"{base}/api/answer?q=", timeout=10)
        assert empty.value.headers["Content-Type"].startswith("application/json")
        assert empty.value.headers["Content-Security-Policy"] == web.HEADERS["Content-Security-Policy"]
    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.parametrize("name, category, vintage", [
    ("Griswold cast iron skillet", "kitchen", True),  # her rule of 10 Oct 2026
    ("Wagner 1891 skillet", "kitchen", True),
    ("Hobart-era KitchenAid stand mixer", "kitchen", True),  # bought vintage on purpose; UK 240 V ones exist
    ("IBM Model M", "general", True),  # a collectors' keyboard, bought used on purpose; works here with an adapter
    ("vintage Sunbeam Radiant Control toaster", "kitchen", False),  # bought vintage in the US, 110-120 V
    ("Rival crock pot", "kitchen", False),  # American 120 V crock pots
    ("Dell Latitude 5300 13.3 Touchscreen", "general", False),  # a used laptop is just old
    ("Griswold cast iron skillet", "general", False),  # each category's own list
])
def test_what_people_buy_vintage_on_purpose_and_can_use_here(name, category, vintage):
    from engine.prices import bought_vintage

    assert bought_vintage(name, category) is vintage
