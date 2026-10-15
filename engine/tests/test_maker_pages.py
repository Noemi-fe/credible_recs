"""The script finding shown products' own pages on their makers' sites (engine/maker_pages.py; Noemi, 15 Oct 2026,
evening: "can you do it automatically?"). Every site here is made up and answered by a fake: tests never reach the
network."""

import json
from datetime import date

from engine import maker_pages
from engine.buyable import import_findings
from engine.maker_pages import Response, Sites, candidates, find_product, maker_sites, model_words, read_page
from engine.product_pages import load_product_pages
from engine.prices import load_prices

DAY = date(2026, 10, 15)
ROBOTS = "User-agent: *\nDisallow: /checkout/\nSitemap: https://www.nanopuff.example/sitemap_index.xml\n"
INDEX = ("<sitemapindex><sitemap><loc>https://www.nanopuff.example/sitemap-blog.xml</loc></sitemap>"
         "<sitemap><loc>https://www.nanopuff.example/sitemap-products.xml</loc></sitemap></sitemapindex>")
PRODUCTS = ("<urlset><url><loc>https://www.nanopuff.example/blog/nano-puff-review</loc></url>"
            "<url><loc>https://www.nanopuff.example/products/mens-nano-puff-vest</loc></url>"
            "<url><loc>https://www.nanopuff.example/products/mens-nano-puff-jacket</loc></url>"
            "<url><loc>https://www.nanopuff.example/products/torrentshell-jacket</loc></url></urlset>")


def page(name: str, price="230.00", currency="GBP", availability="https://schema.org/InStock") -> str:
    product = {"@context": "https://schema.org", "@type": "Product", "name": name,
               "image": ["https://cdn.nanopuff.example/nano-puff.jpg"],
               "offers": {"@type": "Offer", "price": price, "priceCurrency": currency, "availability": availability}}
    return (f'<html><head><title>{name} | Made-up Outdoor</title><meta property="og:site_name" content="Nanopuff">'
            f'<meta property="og:image" content="//cdn.nanopuff.example/og.jpg">'
            f'<script type="application/ld+json">{json.dumps(product)}</script></head></html>')


class FakeWeb:
    """Answers from a dict of address -> (status, text); records every address asked."""

    def __init__(self, answers: dict):
        self.answers, self.asked = answers, []

    def __call__(self, url: str, max_bytes: int):
        self.asked.append(url)
        if url not in self.answers:
            return Response(404, url, b"")
        status, text = self.answers[url]
        return Response(status, url, text.encode("utf-8"))


def site(**pages) -> dict:
    answers = {"https://www.nanopuff.example/robots.txt": (200, ROBOTS),
               "https://www.nanopuff.example/sitemap_index.xml": (200, INDEX),
               "https://www.nanopuff.example/sitemap-products.xml": (200, PRODUCTS),
               "https://www.nanopuff.example/sitemap-blog.xml": (200, "<urlset></urlset>")}
    return answers | {f"https://www.nanopuff.example/products/{k.replace('_', '-')}": (200, v) for k, v in pages.items()}


def sites(web) -> Sites:
    return Sites(get=web, sleep=lambda s: None, clock=lambda: 0.0)


JACKET = {"name": "Nanopuff Nano Puff", "type": "jacket", "category": "general"}


def test_a_products_model_is_its_name_without_brand_type_and_filler():
    assert model_words("Patagonia Nano Puff", "Patagonia", "jacket") == ["nano", "puff"]
    assert model_words("vintage Osprey Exos 58 backpacks", "Osprey", "backpack") == ["exos", "58"]
    assert model_words("Hamilton Beach slow cooker", "Hamilton Beach", "slow cooker") == []  # a brand alone


def test_candidates_hold_every_model_word_type_words_first_and_never_a_blog_page():
    listed = [(url, "sitemap") for url in [
        "https://m.example/blog/nano-puff-review", "https://m.example/products/mens-nano-puff-vest",
        "https://m.example/products/mens-nano-puff-jacket", "https://m.example/collections/nano-puff",
        "https://m.example/products/torrentshell-jacket"]]
    assert [url for url, _ in candidates(listed, ["nano", "puff"], "jacket")] == [
        "https://m.example/products/mens-nano-puff-jacket", "https://m.example/products/mens-nano-puff-vest"]
    assert candidates([("https://m.example/p/nanopuff-hoody", "s")], ["nano", "puff"], "jacket")  # run together


def test_a_page_says_its_name_image_price_and_stock_through_schema_org_or_open_graph():
    facts = read_page(page("Men's Nano Puff Jacket"), "https://www.nanopuff.example/products/x")
    assert facts.names[0] == "Men's Nano Puff Jacket" and facts.site_name == "Nanopuff"
    assert (facts.price, facts.currency, facts.in_stock) == (230.0, "GBP", True)
    assert facts.image == "https://cdn.nanopuff.example/og.jpg"  # og:image first, made absolute
    graph = ('<script type="application/ld+json">{"@graph": [{"@type": "WebPage"}, {"@type": "Product", "name": "Wave+",'
             ' "image": {"url": "https://img.example/wave.png"}, "offers": [{"price": 0}, {"@type": "AggregateOffer", '
             '"lowPrice": "99.95", "priceCurrency": "gbp", "availability": "OutOfStock"}]}]}</script>')
    facts = read_page(graph, "https://m.example/p/wave")
    assert (facts.names, facts.image, facts.price, facts.currency, facts.in_stock) == (
        ["Wave+"], "https://img.example/wave.png", 99.95, "GBP", False)
    plain = read_page('<title>Henry HVR160 - Numatic</title><meta content="Henry" property="og:title">', "https://n.example/")
    assert plain.names == ["Henry", "Henry HVR160 - Numatic"] and plain.price is None


def test_a_page_in_pounds_on_its_makers_site_is_a_sold_new_finding_with_its_price():
    web = FakeWeb(site(mens_nano_puff_jacket=page("Men's Nano Puff Jacket")))
    finding = find_product(JACKET, ["www.nanopuff.example"], sites(web), {}, DAY)
    assert finding == {
        "name": "Nanopuff Nano Puff", "type": "jacket", "category": "general", "status": "sold_new",
        "product_page": "https://www.nanopuff.example/products/mens-nano-puff-jacket", "shop": "Nanopuff",
        "price_gbp": 230.0, "price_url": "https://www.nanopuff.example/products/mens-nano-puff-jacket",
        "image_url": "https://cdn.nanopuff.example/og.jpg",
        "image_page": "https://www.nanopuff.example/products/mens-nano-puff-jacket",
        "sources": ["https://www.nanopuff.example/products/mens-nano-puff-jacket",
                    "https://www.nanopuff.example/sitemap-products.xml"],
        "checked_on": "2026-10-15", "note": finding["note"]}
    assert "https://www.nanopuff.example/sitemap-blog.xml" not in web.asked[:3]  # product sitemaps first


def test_a_page_in_dollars_or_out_of_stock_gives_the_product_its_page_and_says_nothing_of_where_it_is_sold():
    for text in (page("Nano Puff Jacket", currency="USD"), page("Nano Puff Jacket", availability="SoldOut")):
        finding = find_product(JACKET, ["www.nanopuff.example"], sites(FakeWeb(site(mens_nano_puff_jacket=text))), {},
                               DAY)
        assert (finding["status"], finding["price_gbp"], finding["price_url"]) == ("unsure", None, None)
        assert finding["product_page"].endswith("/mens-nano-puff-jacket")


def test_a_page_whose_own_name_lacks_the_model_is_not_the_products():
    web = FakeWeb(site(mens_nano_puff_jacket=page("Torrentshell Jacket"), mens_nano_puff_vest=page("Gift card")))
    assert find_product(JACKET, ["www.nanopuff.example"], sites(web), {}, DAY) is None


def test_robots_txt_is_followed_and_a_site_refusing_tools_is_left_alone():
    closed = site(mens_nano_puff_jacket=page("Men's Nano Puff Jacket"))
    closed["https://www.nanopuff.example/robots.txt"] = (200, ROBOTS.replace("/checkout/", "/products/"))
    web = FakeWeb(closed)
    assert find_product(JACKET, ["www.nanopuff.example"], sites(web), {}, DAY) is None
    assert not [url for url in web.asked if "/products/" in url]
    web = FakeWeb({"https://www.nanopuff.example/robots.txt": (403, "")})
    reader = sites(web)
    assert find_product(JACKET, ["www.nanopuff.example"], reader, {}, DAY) is None
    assert web.asked == ["https://www.nanopuff.example/robots.txt"] and reader.refused == {"www.nanopuff.example"}


def test_one_site_gets_one_request_a_second():
    waits, now = [], [0.0]
    reader = Sites(get=FakeWeb(site()), sleep=lambda s: (waits.append(s), now.__setitem__(0, now[0] + s)),
                   clock=lambda: now[0])
    reader.read("https://www.nanopuff.example/a")
    reader.read("https://www.nanopuff.example/b")
    assert waits == [maker_pages.PAUSE_SECONDS, maker_pages.PAUSE_SECONDS]  # after robots.txt, then after /a


def test_known_makers_sites_come_first_uk_ones_first_else_the_brand_spelled_as_a_site():
    known = ["www.boots.com", "www.osprey.example.com", "www.osprey.example.co.uk"]
    assert [host for host, _ in maker_sites("Osprey Exos 58", ["www.osprey.com", "www.osprey.co.uk", *known])] == [
        "www.osprey.co.uk", "www.osprey.example.co.uk", "www.osprey.com"]  # UK ones first; never Boots
    assert maker_sites("vintage Numatic Henry", []) == [
        ("www.numatichenry.co.uk", "Numatic Henry"), ("www.numatichenry.com", "Numatic Henry"),
        ("www.numatic.co.uk", "Numatic"), ("www.numatic.com", "Numatic")]


def test_the_importer_takes_its_findings_as_it_takes_the_researchers(tmp_path):
    findings = [find_product(JACKET, ["www.nanopuff.example"], sites(FakeWeb(site(mens_nano_puff_jacket=text))), {},
                             DAY) for text in (page("Men's Nano Puff Jacket"), page("Nano Puff Jacket", currency="USD"))]
    findings[1]["name"] = "Nanopuff Nano Puff Vest"
    found = tmp_path / "found-auto.jsonl"
    found.write_text("".join(json.dumps(f) + "\n" for f in findings), encoding="utf-8")
    prices, pages, lines = tmp_path / "prices.json", tmp_path / "pages.json", tmp_path / "lines.json"
    prices.write_text('{"prices": []}\n'), pages.write_text('{"pages": []}\n'), lines.write_text('{"brand_lines": []}\n')
    report = import_findings([found], prices, pages, write=True, brand_lines_path=lines)
    [price] = load_prices(prices)
    assert (price.product, price.price, price.shop, price.available) == ("Nanopuff Nano Puff", 230.0, "Nanopuff", True)
    assert [(p.product, p.shop) for p in load_product_pages(pages)] == [
        ("Nanopuff Nano Puff", "Nanopuff"), ("Nanopuff Nano Puff Vest", "Nanopuff")]
    assert report.unsure == ["Nanopuff Nano Puff Vest"]


def test_another_countrys_page_a_help_site_a_category_or_a_page_that_isnt_a_product_is_never_taken():
    from engine.maker_pages import country_of
    assert [country_of(u) for u in ["https://www.camelbak.co.uk/chute", "https://at.camelbak.com/chute-mag/",
                                    "https://www.bialetti.com/au_en/venus.html", "https://www.carhartt.com/en-gb/p/x",
                                    "https://darntough.com/products/t4021", "https://us.innisfree.com/products/x"]] == [
        "uk", "abroad", "abroad", "uk", "any", "any"]
    listed = [(u, "s") for u in ["https://m.example/c/accessories/nano-puff", "https://m.example/au_en/nano-puff",
                                 "https://support.m.example/nano-puff-faq"]]
    assert candidates(listed, ["nano", "puff"], "jacket") == []
    faq = '<html><head><title>Nano Puff jacket: questions</title></head></html>'  # no schema.org Product, no og:type
    web = FakeWeb(site(mens_nano_puff_jacket=faq))
    why = []
    assert find_product(JACKET, ["www.nanopuff.example"], sites(web), {}, DAY, why) is None
    assert "not a product page" in why[0]


def test_a_shops_address_starting_with_a_common_word_isnt_the_makers_and_generic_words_may_be_left_out():
    assert maker_sites("baby merlins magic sleep suit", ["www.babylist.com"]) == [
        ("www.babymerlins.co.uk", "baby merlins"), ("www.babymerlins.com", "baby merlins"),
        ("www.baby.co.uk", "baby"), ("www.baby.com", "baby")]  # guessed, never the shop
    stridex = [("https://stridex.example/product/stridex-maximum/", "s")]
    assert candidates(stridex, ["maximum", "pads"], "exfoliant") == stridex  # "pads" left out of the address


def test_a_plural_matches_its_singular_and_a_site_without_sitemaps_in_robots_txt_is_looked_up_where_they_usually_are():
    assert candidates([("https://r.example/products/rogue-echo-bumper-plates", "s")], ["echo", "bumpers"], "weight plates")
    answers = {"https://www.nanopuff.example/robots.txt": (200, "User-agent: *\nDisallow:\n"),
               "https://www.nanopuff.example/sitemap_index.xml": (200, INDEX),
               "https://www.nanopuff.example/sitemap-products.xml": (200, PRODUCTS),
               "https://www.nanopuff.example/products/mens-nano-puff-jacket": (200, page("Nano Puff Jacket"))}
    web = FakeWeb(answers)
    assert find_product(JACKET, ["www.nanopuff.example"], sites(web), {}, DAY)["status"] == "sold_new"
    assert "https://www.nanopuff.example/wp-sitemap.xml" not in web.asked  # the first found will do


def test_a_part_another_sites_page_another_countrys_site_or_a_name_missing_a_word_isnt_the_products_page():
    from engine.maker_pages import country_of
    assert country_of("https://knirps.de/8800501001-knirps-us-050-case.html") == "abroad"
    tray = {"name": "Nanopuff Duo Crisp", "type": "air fryer", "category": "kitchen"}
    for slug, text in [("duo-crisp-dehydrating-tray", page("Duo Crisp 60 Dehydrating Tray"))]:  # a part
        web = FakeWeb(site(**{slug.replace("-", "_"): text}) | {"https://www.nanopuff.example/sitemap-products.xml": (
            200, f"<urlset><url><loc>https://www.nanopuff.example/products/{slug}</loc></url></urlset>")})
        assert find_product(tray, ["www.nanopuff.example"], sites(web), {}, DAY) is None
    cream = {"name": "Nanopuff Sun Cream", "type": "sunscreen", "category": "skincare"}
    web = FakeWeb(site(sun_serum=page("Sun Serum")) | {"https://www.nanopuff.example/sitemap-products.xml": (
        200, "<urlset><url><loc>https://www.nanopuff.example/products/sun-serum</loc></url></urlset>")})
    assert find_product(cream, ["www.nanopuff.example"], sites(web), {}, DAY) is None  # its address may skip "cream"
    elsewhere = site() | {"https://www.nanopuff.example/sitemap-products.xml": (
        200, "<urlset><url><loc>https://shop.example/products/nano-puff-jacket</loc></url></urlset>"),
        "https://shop.example/robots.txt": (200, ""), "https://shop.example/products/nano-puff-jacket": (
        200, page("Nano Puff Jacket"))}
    why = []
    assert find_product(JACKET, ["www.nanopuff.example"], sites(FakeWeb(elsewhere)), {}, DAY, why) is None
    assert "another site" in why[-1]
