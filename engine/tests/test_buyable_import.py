"""The importer of researchers' findings (Noemi's decisions of 15 Oct 2026, late afternoon; engine/buyable.py).

Researchers write one JSON object per product: the name the answer shows, its type and category, whether it is on sale
in the UK now (sold_new, second_hand_only, not_sold_uk, discontinued or unsure), its own page, the shop, a price, the
main image on its maker's page, their sources and the day. The importer checks every address and maps each finding
onto the lists the engine already reads: the price list (data/prices.json) for whether it is sold and its price, and
the product pages list (data/product_pages.json) for its own page and image.

The names are real names the live answers showed on 15 Oct 2026 (the laptop answer's picks and items, a kettle and a
skillet line); every page, shop, price and image is made up.
"""

import json
from datetime import date

import pytest

from engine import buyable
from engine.buyable import Finding, import_findings, plan_finding
from engine.prices import load_prices
from engine.product_pages import load_product_pages

DAY = "2026-10-15"
APPLE_PAGE = "https://maker.example/uk/macbook-air/"
APPLE_IMAGE = "https://images.maker.example/macbook-air-hero.jpg"


def finding(**changes) -> dict:
    data = {"name": "ASUS ROG laptop", "type": "laptop", "category": "general", "status": "sold_new",
            "product_page": "https://asus.example/uk/rog-laptops/", "shop": "ASUS", "price_gbp": 999.0,
            "price_url": "https://asus.example/uk/rog-laptops/", "image_url": "https://img.asus.example/rog.png",
            "image_page": "https://asus.example/uk/rog-laptops/", "sources": ["https://asus.example/uk/rog-laptops/"],
            "checked_on": DAY, "note": "Made up for a test."}
    return {key: value for key, value in (data | changes).items() if value is not ...}


def written(tmp_path, *findings) -> "Path":
    path = tmp_path / "found-test.jsonl"
    path.write_text("".join(json.dumps(f) + "\n" for f in findings), encoding="utf-8")
    return path


def lists(tmp_path, prices=(), pages=()):
    prices_path, pages_path = tmp_path / "prices.json", tmp_path / "product_pages.json"
    prices_path.write_text(json.dumps({"prices": list(prices)}, indent=1) + "\n", encoding="utf-8")
    pages_path.write_text(json.dumps({"pages": list(pages)}, indent=1) + "\n", encoding="utf-8")
    return prices_path, pages_path


def test_no_test_ever_writes_the_committed_lists(tmp_path):
    # The importer's default lists are stand-ins in tests (engine/tests/conftest.py): found on 15 Oct 2026, when a line
    # test that named no brand-lines list had changed the real data/brand_lines.json.
    from engine.brand_lines import DEFAULT_BRAND_LINES as REAL_BRAND_LINES
    from engine.prices import DEFAULT_PRICES as REAL_PRICES
    from engine.product_pages import DEFAULT_PRODUCT_PAGES as REAL_PAGES

    before = [path.read_bytes() for path in (REAL_PRICES, REAL_PAGES, REAL_BRAND_LINES)]
    line = finding(name="Victorinox chef knife line", type="chef knife", category="kitchen", shop="Victorinox",
                   product_page="https://victorinox.example/en-GB/chefs-knives", price_gbp=25.0,
                   price_url="https://victorinox.example/en-GB/chefs-knives", image_url=..., image_page=...,
                   sources=["https://victorinox.example/en-GB/chefs-knives"])
    import_findings([written(tmp_path, line)], write=True)
    assert [path.read_bytes() for path in (REAL_PRICES, REAL_PAGES, REAL_BRAND_LINES)] == before
    assert buyable.DEFAULT_BRAND_LINES != REAL_BRAND_LINES


def run(tmp_path, *findings, prices=(), pages=()):
    prices_path, pages_path = lists(tmp_path, prices, pages)
    lines_path = tmp_path / "brand_lines.json"
    lines_path.write_text('{"brand_lines": []}\n', encoding="utf-8")
    report = import_findings([written(tmp_path, *findings)], prices_path, pages_path, write=True,
                             brand_lines_path=lines_path)
    return report, load_prices(prices_path), load_product_pages(pages_path)


# --- What each status becomes ---

def test_a_product_sold_new_gets_its_price_its_page_and_its_makers_image(tmp_path):
    report, [price], [page] = run(tmp_path, finding())
    assert (price.product, price.category, price.product_type, price.price, price.currency, price.shop, price.url,
            price.available, price.second_hand, price.checked_on) == (
        "ASUS ROG laptop", "general", "laptop", 999.0, "GBP", "ASUS", "https://asus.example/uk/rog-laptops/", True,
        False, date(2026, 10, 15))
    assert (page.product, page.product_type, page.page, page.shop, page.image, page.image_page) == (
        "ASUS ROG laptop", "laptop", "https://asus.example/uk/rog-laptops/", "ASUS", "https://img.asus.example/rog.png",
        "https://asus.example/uk/rog-laptops/")
    assert report.added_prices == 1 and report.added_pages == 1 and not report.problems


def test_a_product_sold_new_without_a_price_is_still_sold_there(tmp_path):
    _, [price], [page] = run(tmp_path, finding(price_gbp=None, price_url=None))
    assert (price.price, price.available, price.url) == (None, True, "https://asus.example/uk/rog-laptops/")
    assert page.page == "https://asus.example/uk/rog-laptops/"


@pytest.mark.parametrize("status", ["discontinued", "not_sold_uk"])
def test_a_discontinued_model_or_one_not_sold_to_uk_shoppers_is_marked_not_sold(tmp_path, status):
    # The laptop answer's first pick, from old BuyItForLife threads.
    gone = finding(name="MBPs from late 2010-2011", status=status, product_page=None, shop="Apple", price_gbp=None,
                   price_url=None, image_url=None, image_page=None,
                   sources=["https://maker.example/uk/support/vintage-and-obsolete-products/"])
    report, [price], pages = run(tmp_path, gone)
    assert (price.product, price.available, price.price, price.second_hand, price.shop, price.url) == (
        "MBPs from late 2010-2011", False, None, False, "Apple",
        "https://maker.example/uk/support/vintage-and-obsolete-products/")
    assert pages == []  # never linked: it is left out of answers
    assert report.statuses[status] == 1


def test_sold_second_hand_only_counts_as_sold_only_for_what_people_buy_vintage_on_purpose(tmp_path):
    griswold = finding(name="Griswold cast iron skillet line", type="cast iron skillet", category="kitchen",
                       status="second_hand_only", product_page=None, shop="eBay UK", price_gbp=None, price_url=None,
                       image_url=None, image_page=None, sources=["https://vintage.example/griswold-skillets"])
    refurbished = finding(name="Dell Latitude 5300 13.3 Touchscreen", status="second_hand_only", product_page=None,
                          shop="eBay UK", price_gbp=None, price_url=None, image_url=None, image_page=None,
                          sources=["https://second.example/dell-latitude-5300"])
    report, prices, _ = run(tmp_path, griswold, refurbished)
    vintage, used = prices
    # Her rule of 10 Oct 2026: vintage Griswold cast iron is sold second-hand only, and counts as sold.
    assert (vintage.product, vintage.product_type, vintage.available, vintage.second_hand) == (
        "Griswold cast iron skillet", "cast iron skillet", True, True)
    # A laptop sold only used isn't bought vintage on purpose: it isn't on sale in the UK now.
    assert (used.product, used.available, used.second_hand) == ("Dell Latitude 5300 13.3 Touchscreen", False, False)
    assert report.not_vintage == ["Dell Latitude 5300 13.3 Touchscreen"]


def test_unsure_records_nothing(tmp_path):
    report, prices, pages = run(tmp_path, finding(name="Legion Y540", status="unsure"))
    assert prices == [] and pages == [] and report.unsure == ["Legion Y540"]


# --- Names: each reaches the product as the answer finds it ---

def test_a_brand_line_is_recorded_under_its_brand_as_the_price_list_speaks_for_lines(tmp_path):
    # A line's price-list entry is under its brand followed only by its type's words ("OXO kettle"), which is how the
    # pipeline finds the entry speaking for a brand line (engine.prices.find_brand_entry); its page is under the name
    # the answer shows.
    line = finding(name="MacBook laptop line", product_page=APPLE_PAGE, shop="Apple", price_gbp=None, price_url=None,
                   image_url=APPLE_IMAGE, image_page=APPLE_PAGE, sources=[APPLE_PAGE])
    _, [price], [page] = run(tmp_path, line)
    assert (price.product, price.product_type, price.available) == ("MacBook laptop", "laptop", True)
    assert (page.product, page.product_type, page.page, page.image) == (
        "MacBook laptop line", "laptop", APPLE_PAGE, APPLE_IMAGE)


@pytest.mark.parametrize("name, product_type, brand", [
    ("Sage electric kettle line", "electric kettle", "Sage electric kettle"),
    ("Le Creuset Dutch oven line", "dutch oven", "Le Creuset dutch oven"),  # the type as a name shows it
    ("Lodge cast iron skillet line", "cast iron skillet", "Lodge cast iron skillet"),
    ("Sony WH-1000XM5", "headphones", "Sony WH-1000XM5"),  # a product: its own name
    ("Fellow Stagg EKG", "electric kettle", "Fellow Stagg EKG"),
])
def test_a_price_list_entry_is_named_as_the_answer_finds_the_product(name, product_type, brand):
    category = "general" if product_type == "headphones" else "kitchen"
    plan = plan_finding(Finding.model_validate(finding(name=name, type=product_type, category=category)))
    assert plan.prices[0]["product"] == brand and plan.prices[0]["product_type"] == product_type


# --- Every address is checked ---

@pytest.mark.parametrize("field, bad", [
    ("product_page", "http://asus.example/uk/rog-laptops/"),
    ("product_page", "https://user:pw@asus.example/uk/rog-laptops/"),
    ("product_page", "https://www.reddit.com/r/laptops/comments/abc/rog/"),
    ("product_page", "https://www.amazon.co.uk/s?k=asus+rog"),  # direct links only: never a search
    ("image_url", "data:image/png;base64,iVBORw0KGgo="),
    ("image_url", "https://i.redd.it/rog.png"),
    ("image_page", "http://asus.example/uk/rog-laptops/"),
])
def test_an_address_that_fails_its_check_is_never_recorded_and_is_reported(tmp_path, field, bad):
    report, [price], pages = run(tmp_path, finding(**{field: bad}))
    assert price.available is True  # what the sources say still counts
    shown = [p for p in pages if bad in (p.page, p.image, p.image_page)]
    assert shown == [] and any(field in problem for problem in report.problems)
    if field == "product_page":
        assert pages == []  # no page, no link: as before for a product not researched
    else:
        assert pages[0].image is None  # the page without the image


def test_a_price_read_on_a_search_page_is_not_recorded(tmp_path):
    report, [price], _ = run(tmp_path, finding(price_url="https://shop.example/search?q=asus+rog"))
    assert price.price is None and price.available is True
    assert any("price_url" in problem for problem in report.problems)


def test_sources_that_fail_their_check_are_dropped_and_a_finding_with_none_left_is_refused(tmp_path):
    report, prices, pages = run(tmp_path, finding(name="Legion Y540", status="discontinued", product_page=None,
                                                  price_gbp=None, price_url=None, image_url=None, image_page=None,
                                                  sources=["https://www.reddit.com/r/laptops/comments/abc/y540/"]))
    assert prices == [] and pages == [] and report.refused == ["Legion Y540"]


@pytest.mark.parametrize("broken", [
    "{not json",
    json.dumps({"name": "Legion Y540", "status": "maybe", "type": "laptop", "category": "general",
                "sources": ["https://a.example/"], "checked_on": DAY}),
    json.dumps({"name": "", "status": "unsure", "type": "laptop", "category": "general", "sources": [],
                "checked_on": DAY}),
])
def test_a_line_that_isnt_a_finding_is_reported_with_its_file_and_line_and_the_rest_imported(tmp_path, broken):
    path = tmp_path / "found-mixed.jsonl"
    path.write_text(broken + "\n" + json.dumps(finding()) + "\n", encoding="utf-8")
    prices_path, pages_path = lists(tmp_path)
    report = import_findings([path], prices_path, pages_path, write=True)
    assert len(load_prices(prices_path)) == 1 and any("found-mixed.jsonl:1" in p for p in report.problems)


def test_a_field_the_format_doesnt_have_is_reported_never_dropped_quietly(tmp_path):
    report, _, [page] = run(tmp_path, finding(imgae_url="https://img.asus.example/other.png"))
    assert any("imgae_url" in problem for problem in report.problems)


# --- Writing the lists ---

def test_importing_twice_adds_nothing_the_second_time(tmp_path):
    prices_path, pages_path = lists(tmp_path)
    found = written(tmp_path, finding(), finding(name="Legion Y540", status="discontinued", product_page=None,
                                                 price_gbp=None, price_url=None, image_url=None, image_page=None))
    import_findings([found], prices_path, pages_path, write=True)
    again = import_findings([found], prices_path, pages_path, write=True)
    assert (again.added_prices, again.added_pages) == (0, 0) and again.already_there == 3
    assert len(load_prices(prices_path)) == 2 and len(load_product_pages(pages_path)) == 1


def test_entries_already_in_the_lists_stay_as_they_are_in_the_files_own_format(tmp_path):
    existing = {"product": "Zojirushi kettle", "category": "kitchen", "price": 120.0, "currency": "GBP",
                "shop": "Made-up Kitchen Shop", "url": "https://shop.example/zojirushi-kettle",
                "checked_on": "2026-10-09", "available": True}
    prices_path, pages_path = lists(tmp_path, prices=[existing])
    import_findings([written(tmp_path, finding())], prices_path, pages_path, write=True)
    text = prices_path.read_text(encoding="utf-8")
    data = json.loads(text)
    assert data["prices"][0] == existing and len(data["prices"]) == 2
    assert text == json.dumps(data, indent=1, ensure_ascii=False) + "\n"  # the list's own layout


def test_without_write_nothing_changes(tmp_path):
    prices_path, pages_path = lists(tmp_path)
    before = (prices_path.read_text(), pages_path.read_text())
    report = import_findings([written(tmp_path, finding())], prices_path, pages_path, write=False)
    assert report.added_prices == 1 and (prices_path.read_text(), pages_path.read_text()) == before


def test_a_finding_saying_otherwise_on_a_day_the_list_already_has_is_reported_for_a_look(tmp_path):
    sold = {"product": "Legion Y540", "category": "general", "product_type": "laptop", "price": None,
            "currency": "GBP", "shop": "Big Shop", "url": "https://shop.example/legion-y540", "checked_on": DAY,
            "available": True}
    report, prices, _ = run(tmp_path, finding(name="Legion Y540", status="discontinued", product_page=None,
                                              price_gbp=None, price_url=None, image_url=None, image_page=None,
                                              shop="Lenovo", sources=["https://lenovo.example/uk/legion-y540/"]),
                            prices=[sold])
    assert any("Legion Y540" in problem and "says otherwise" in problem for problem in report.problems)
    assert len(prices) == 2  # both kept: the importer never deletes an entry


def test_the_shop_of_a_price_read_elsewhere_is_named_as_the_price_list_names_that_shop(tmp_path):
    known = {"product": "Zojirushi kettle", "category": "kitchen", "price": 120.0, "currency": "GBP",
             "shop": "John Lewis", "url": "https://www.johnlewis.com/zojirushi/p1", "checked_on": "2026-10-09",
             "available": True}
    report, prices, _ = run(tmp_path, finding(price_url="https://www.johnlewis.com/asus-rog/p2"), prices=[known])
    assert prices[1].shop == "John Lewis" and prices[1].url == "https://www.johnlewis.com/asus-rog/p2"


def test_a_price_at_a_shop_the_lists_dont_know_yet_is_left_for_a_look(tmp_path):
    # Rather than shown under the wrong shop's name (the finding's shop is the product page's).
    report, [price], _ = run(tmp_path, finding(price_url="https://unknown-shop.example/asus-rog"))
    assert price.price is None and price.available is True
    assert any("price_url" in problem for problem in report.problems)


def test_the_command_line_reads_the_findings_and_writes_only_when_asked(tmp_path, capsys, monkeypatch):
    prices_path, pages_path = lists(tmp_path)
    monkeypatch.setattr(buyable, "DEFAULT_PRICES", prices_path)
    monkeypatch.setattr(buyable, "DEFAULT_PRODUCT_PAGES", pages_path)
    found = written(tmp_path, finding())
    monkeypatch.setattr(buyable, "head_image", fake_heads({"https://img.asus.example/rog.png": 40_000}))
    assert buyable.main(["import", str(found)]) == 0
    printed = capsys.readouterr().out
    assert load_prices(prices_path) == [] and "--write" in printed and "Images: 1 kept" in printed
    assert buyable.main(["import", str(found), "--write"]) == 0
    assert len(load_prices(prices_path)) == 1 and len(load_product_pages(pages_path)) == 1
    assert buyable.main([]) == 2


# --- Whose site a page is (real patterns of the first findings, 15 Oct 2026) ---

def test_a_page_at_the_makers_site_is_named_for_the_maker_and_the_price_for_the_shop_that_sells_it(tmp_path):
    # As the first findings wrote CeraVe's cleansers: its maker's UK page, and a price at a shop, named in "shop".
    cerave = finding(name="CeraVe Hydrating Cleanser", type="cleanser", category="skincare", shop="Lookfantastic",
                     product_page="https://www.cerave.example/skincare/cleansers/hydrating-cleanser",
                     price_gbp=12.5, price_url="https://shop-lf.example/p/cerave-hydrating-cleanser/1234/",
                     image_url="https://www.cerave.example/media/hydrating-cleanser.png",
                     image_page="https://www.cerave.example/skincare/cleansers/hydrating-cleanser",
                     sources=["https://shop-lf.example/p/cerave-hydrating-cleanser/1234/"])
    _, [price], [page] = run(tmp_path, cerave)
    assert (price.shop, price.url, price.price) == ("Lookfantastic", cerave["price_url"], 12.5)
    # Its link names the maker as the product's own name starts, since the site's address spells it.
    assert (page.shop, page.page) == ("CeraVe", cerave["product_page"])


def test_a_makers_page_at_a_site_whose_address_doesnt_spell_it_is_named_by_its_address(tmp_path):
    found = finding(name="Anessa Perfect UV Sunscreen Skincare Milk", type="sunscreen", category="skincare",
                    shop="Japan Shop", product_page="https://www.shiseido.example/anessa/perfect-uv/",
                    price_gbp=None, price_url=None, image_url=..., image_page=...,
                    sources=["https://www.shiseido.example/anessa/perfect-uv/"])
    plan = plan_finding(Finding.model_validate(found), {})
    assert plan.page["shop"] == "Japan Shop"  # no price page: the one site the finding names
    found |= {"price_gbp": 20.0, "price_url": "https://japanshop.example/p/anessa"}
    plan = plan_finding(Finding.model_validate(found), {"japanshop.example": "Japan Shop"})
    assert plan.page["shop"] == "shiseido.example" and plan.prices[0]["shop"] == "Japan Shop"


@pytest.mark.parametrize("name, page, maker", [
    ("CeraVe Hydrating Cleanser", "https://www.cerave.co.uk/skincare/cleansers/hydrating-cleanser", "CeraVe"),
    ("Beauty of Joseon Relief Sun: Rice + Niacinamide", "https://beautyofjoseon.com/products/relief-sun", "Beauty of Joseon"),
    ("innisfree Retinol Cica Moisture Recovery Serum", "https://us.innisfree.com/products/retinol-cica", "innisfree"),
    ("Lodge cast iron skillet line", "https://www.lodgecastiron.com/collections/skillets", "Lodge"),  # a line: its brand
    ("Wüsthof chef knife line", "https://wusthof.co.uk/collections/chefs-knives", "Wüsthof"),
    ("The Ordinary Niacinamide 10% + Zinc 1%", "https://theordinary.com/en-gb/niacinamide.html", "The Ordinary"),
])
def test_a_makers_site_is_named_as_the_products_own_name_starts(tmp_path, name, page, maker):
    product_type = "cast iron skillet" if "skillet" in name else "chef knife" if "knife" in name else "cleanser"
    category = "kitchen" if product_type != "cleanser" else "skincare"
    found = finding(name=name, type=product_type, category=category, shop="Big Shop", product_page=page,
                    price_gbp=10.0, price_url="https://bigshop.example/p/123", image_url=..., image_page=...,
                    sources=["https://bigshop.example/p/123"])
    plan = plan_finding(Finding.model_validate(found), {"bigshop.example": "Big Shop"})
    assert plan.page["shop"] == maker and plan.prices[0]["shop"] == "Big Shop"


def test_a_shops_own_page_with_its_price_there_is_named_as_the_finding_names_it(tmp_path):
    _, [price], [page] = run(tmp_path, finding(shop="Skin Cupid", product_page="https://skin-cupid.example/p/cream",
                                               price_url="https://skin-cupid.example/p/cream",
                                               sources=["https://skin-cupid.example/p/cream"]))
    assert price.shop == page.shop == "Skin Cupid"


def test_an_ingredient_led_answers_findings_speak_for_any_type_and_a_lines_type_is_its_own(tmp_path):
    # An answer naming an ingredient and no type ("salicylic acid for acne", typed "salicylic acid product") shows
    # products of several types; the price list looks each up by its own type, so such an entry names none.
    serum = finding(name="Mad Hippie Vitamin C Serum", type="vitamin C product", category="skincare",
                    product_page="https://madhippie.example/vitamin-c-serum", shop="Mad Hippie", price_gbp=None,
                    price_url=None, image_url=..., image_page=..., sources=["https://madhippie.example/vitamin-c-serum"])
    line = finding(name="Paula's Choice 2% BHA exfoliant line", type="salicylic acid product", category="skincare",
                   status="not_sold_uk", product_page=None, price_gbp=None, price_url=None, image_url=...,
                   image_page=..., sources=["https://paulaschoice.example/uk/"])
    report, prices, [page] = run(tmp_path, serum, line)
    assert [(p.product, p.product_type) for p in prices] == [
        ("Mad Hippie Vitamin C Serum", None), ("Paula's Choice 2% BHA exfoliant", "exfoliant")]
    assert page.product_type is None and not [p for p in report.problems if "Validation" in p]


def test_an_entry_that_wouldnt_load_is_reported_and_the_rest_imported(tmp_path, monkeypatch):
    planned = buyable.plan_finding

    def broken_for_one(found, shops=None):
        plan = planned(found, shops)
        if found.name == "Legion Y540":
            plan.prices[0]["url"] = "http://shop.example/legion"  # as if a rule above let one through
        return plan

    monkeypatch.setattr(buyable, "plan_finding", broken_for_one)
    report, prices, _ = run(tmp_path, finding(name="Legion Y540"), finding())
    assert [p.product for p in prices] == ["ASUS ROG laptop"]
    assert any("Legion Y540" in problem and "wouldn't load" in problem for problem in report.problems)


def test_a_second_hand_entry_points_at_a_page_of_the_shop_it_names_not_at_its_first_source(tmp_path):
    # As the first Griswold finding: a history page first, then the eBay UK search where it is sold.
    griswold = finding(name="Griswold cast iron skillet line", type="cast iron skillet", category="kitchen",
                       status="second_hand_only", product_page=None, shop="eBay UK", price_gbp=None, price_url=None,
                       image_url=..., image_page=...,
                       sources=["https://history.example/wiki/american-cast-iron",
                                "https://www.ebay.co.uk/sch/i.html?_nkw=griswold+cast+iron+skillet"])
    _, [price], _ = run(tmp_path, griswold)
    assert price.url == "https://www.ebay.co.uk/sch/i.html?_nkw=griswold+cast+iron+skillet"  # a search: never linked
    assert price.sources[0] == price.url and "https://history.example/wiki/american-cast-iron" in price.sources


def test_a_lines_price_is_never_recorded_as_the_lines_own(tmp_path):
    # A line has many products, so no single price: its "From £X" is the brand-lines list's (data/brand_lines.json).
    line = finding(name="Victorinox chef knife line", type="chef knife", category="kitchen", shop="Victorinox",
                   product_page="https://victorinox.example/en-GB/chefs-knives", price_gbp=25.0,
                   price_url="https://victorinox.example/en-GB/chefs-knives", image_url=..., image_page=...,
                   sources=["https://victorinox.example/en-GB/chefs-knives"])
    report, [price], [page] = run(tmp_path, line)
    assert (price.product, price.price, price.available) == ("Victorinox chef knife", None, True)
    assert report.line_prices == ["Victorinox chef knife line"]


def test_without_a_price_a_makers_page_is_still_named_for_its_maker_and_where_it_is_sold_for_the_shop(tmp_path):
    found = finding(name="CeraVe Hydrating Cleanser", type="cleanser", category="skincare", shop="Holland & Barrett",
                    product_page="https://www.cerave.example/hydrating-cleanser", price_gbp=None, price_url=None,
                    image_url=..., image_page=...,
                    sources=["https://www.cerave.example/hydrating-cleanser",
                             "https://www.hollandandbarrett.example/shop/product/cerave-hydrating-cleanser"])
    plan = plan_finding(Finding.model_validate(found), {})
    assert plan.page["shop"] == "CeraVe"
    # "Sold at Holland & Barrett" points at a page of Holland & Barrett ("&" spelled "and" in its address).
    assert plan.prices[0]["shop"] == "Holland & Barrett"
    assert plan.prices[0]["url"] == "https://www.hollandandbarrett.example/shop/product/cerave-hydrating-cleanser"


# --- Images checked as they are imported (the coordinator, 15 Oct 2026: a phone opening a card with a 5 MB image) ---

from engine.buyable import ImageFacts, check_image, smaller_sizes  # noqa: E402


def fake_heads(sizes: dict[str, object]):
    """A stand-in for asking a server for an image's headers: {url: size in bytes, or an error in words}."""
    asked = []

    def head(url):
        asked.append(url)
        found = sizes.get(url, "not found (404)")
        if isinstance(found, str):
            return ImageFacts(None, None, url, found)
        return ImageFacts(found, "image/jpeg", url, None)

    head.asked = asked
    return head


def test_an_image_under_the_limit_is_kept_as_it_is():
    checked = check_image("https://img.maker.example/a.jpg", fake_heads({"https://img.maker.example/a.jpg": 42_000}))
    assert (checked.url, checked.size, checked.reason) == ("https://img.maker.example/a.jpg", 42_000, None)


def test_a_big_image_gives_way_to_a_smaller_size_of_it_on_the_makers_own_server():
    big = "https://maker.example/cdn/shop/files/kettle.jpg?v=17"
    smaller = "https://maker.example/cdn/shop/files/kettle.jpg?v=17&width=600"
    assert smaller in smaller_sizes(big)  # Shopify's servers take a width
    checked = check_image(big, fake_heads({big: 5_400_000, smaller: 61_000}))
    assert checked.url == smaller and checked.size == 61_000 and "smaller size" in checked.reason


def test_a_big_image_with_no_smaller_size_is_dropped_and_why_is_recorded():
    big = "https://img.maker.example/toaster.png"
    checked = check_image(big, fake_heads({big: 3_400_000}))
    assert checked.url is None and "3.4 MB" in checked.reason and "no smaller size" in checked.reason


@pytest.mark.parametrize("answer, why", [
    ("refuses automated requests (403)", "couldn't be checked"),
    ("not found (404)", "couldn't be checked"),
])
def test_an_image_that_cant_be_checked_is_dropped_never_guessed(answer, why):
    checked = check_image("https://img.maker.example/shoe.jpg", fake_heads({"https://img.maker.example/shoe.jpg": answer}))
    assert checked.url is None and why in checked.reason


@pytest.mark.parametrize("url, smaller", [
    ("https://s7d1.scene7.com/is/image/maker/kettle", "https://s7d1.scene7.com/is/image/maker/kettle?wid=600"),
    ("https://www.maker.example/dw/image/v2/AAAA/on/demandware.static/k.jpg?sw=2000",
     "https://www.maker.example/dw/image/v2/AAAA/on/demandware.static/k.jpg?sw=600"),
    ("https://www.maker.example/-/media/products/k.jpg?rev=1", "https://www.maker.example/-/media/products/k.jpg?rev=1&mw=600"),
    ("https://assets.maker.example/cdn-cgi/image/width=1300,format=auto/k.png",
     "https://assets.maker.example/cdn-cgi/image/width=600,format=auto/k.png"),
])
def test_smaller_sizes_are_asked_for_the_way_each_image_server_takes_them(url, smaller):
    assert smaller in smaller_sizes(url)
    assert all(candidate.split("/")[2] == url.split("/")[2] for candidate in smaller_sizes(url))  # its own server only


def test_imported_images_are_checked_and_a_dropped_ones_reason_kept_in_the_pages_note(tmp_path):
    prices_path, pages_path = lists(tmp_path)
    found = written(tmp_path, finding())  # its image: https://img.asus.example/rog.png
    report = import_findings([found], prices_path, pages_path, write=True,
                             image_head=fake_heads({"https://img.asus.example/rog.png": 2_000_000}))
    [page] = load_product_pages(pages_path)
    assert page.image is None and "image left out" in page.note and "2 MB" in page.note
    assert report.images == {"kept": 0, "smaller": 0, "dropped": 1}
    # Imported again: nothing is asked of the network for a page already in the list, and nothing is added twice.
    head = fake_heads({})
    again = import_findings([found], prices_path, pages_path, write=True, image_head=head)
    assert head.asked == [] and again.added_pages == 0


# --- A brand line's range page and from price (its researcher: the maker's UK range page, and a "from" price) ---

def brand_lines_file(tmp_path, entries=()):
    path = tmp_path / "brand_lines.json"
    path.write_text(json.dumps({"brand_lines": list(entries)}, indent=1) + "\n", encoding="utf-8")
    return path


def test_a_lines_range_page_and_from_price_go_to_its_brand_lines_entry(tmp_path):
    from engine.brand_lines import load_brand_lines

    prices_path, pages_path = lists(tmp_path)
    lines_path = brand_lines_file(tmp_path)
    line = finding(name="Cosori air fryer line", type="air fryer", category="kitchen", shop="Argos",
                   product_page="https://cosori.example/uk/air-fryers/", price_gbp=59.99,
                   price_url="https://www.argos.example/product/123", image_url="https://cosori.example/img/af.jpg",
                   image_page="https://cosori.example/uk/air-fryers/af/", sources=["https://cosori.example/uk/air-fryers/"])
    report = import_findings([written(tmp_path, line)], prices_path, pages_path, write=True, brand_lines_path=lines_path,
                             image_head=fake_heads({"https://cosori.example/img/af.jpg": 80_000}))
    [entry] = load_brand_lines(lines_path)
    assert (entry.brand, entry.product_type, entry.sells, entry.range_page) == (
        "Cosori", "air fryer", True, "https://cosori.example/uk/air-fryers/")
    assert (entry.from_price, entry.from_price_shop, entry.from_price_url) == (
        59.99, "Argos", "https://www.argos.example/product/123")
    assert report.lines_updated == 1


def test_a_lines_existing_entry_keeps_its_range_page_and_takes_a_newer_from_price(tmp_path):
    from engine.brand_lines import load_brand_lines

    old = {"brand": "Cosori", "category": "kitchen", "product_type": "air fryer", "sells": True,
           "sources": ["https://cosori.example/uk/range-old/", "https://shop.example/old"], "checked_on": "2026-10-14",
           "range_page": "https://cosori.example/uk/range-old/", "from_price": 69.99, "from_price_shop": "Old Shop",
           "from_price_url": "https://shop.example/old", "from_price_checked_on": "2026-10-14", "note": "Made up."}
    prices_path, pages_path = lists(tmp_path)
    lines_path = brand_lines_file(tmp_path, [old])
    line = finding(name="Cosori air fryer line", type="air fryer", category="kitchen", shop="Argos",
                   product_page="https://cosori.example/uk/air-fryers/", price_gbp=59.99,
                   price_url="https://www.argos.example/product/123", image_url=..., image_page=...,
                   sources=["https://cosori.example/uk/air-fryers/"])
    import_findings([written(tmp_path, line)], prices_path, pages_path, write=True, brand_lines_path=lines_path,
                    image_head=fake_heads({}))
    [entry] = load_brand_lines(lines_path)
    assert entry.range_page == "https://cosori.example/uk/range-old/"  # a researched range page stays as it was
    assert (entry.from_price, entry.from_price_shop, entry.from_price_checked_on) == (59.99, "Argos", date(2026, 10, 15))
    assert "https://shop.example/old" in entry.sources and "https://www.argos.example/product/123" in entry.sources


def test_a_lines_range_page_at_a_stockist_names_it_and_one_without_a_page_says_so(tmp_path):
    from engine.brand_lines import load_brand_lines

    prices_path, pages_path = lists(tmp_path)
    lines_path = brand_lines_file(tmp_path)
    shun = finding(name="Shun chef knife line", type="chef knife", category="kitchen", shop="Knife Shop",
                   product_page="https://knifeshop.example/by-brand/kai-shun/", price_gbp=164.95,
                   price_url="https://knifeshop.example/kai-shun-chef/p1", image_url=..., image_page=...,
                   sources=["https://knifeshop.example/by-brand/kai-shun/"])
    cetaphil = finding(name="Cetaphil cleanser line", type="cleanser", category="skincare", shop="Boots",
                       product_page=None, price_gbp=11.49, price_url="https://www.boots.example/cetaphil-gentle/p2",
                       image_url=..., image_page=..., sources=["https://www.boots.example/cetaphil-gentle/p2"])
    import_findings([written(tmp_path, shun, cetaphil)], prices_path, pages_path, write=True,
                    brand_lines_path=lines_path, image_head=fake_heads({}))
    by_brand = {line.brand: line for line in load_brand_lines(lines_path)}
    assert (by_brand["Shun"].range_page, by_brand["Shun"].range_shop) == (
        "https://knifeshop.example/by-brand/kai-shun/", "Knife Shop")
    assert by_brand["Cetaphil"].range_page is None and "no range page" in by_brand["Cetaphil"].note.casefold()
