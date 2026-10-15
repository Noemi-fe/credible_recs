"""The product pages list, data/product_pages.json (Noemi's decisions 2 and 3 of 15 Oct 2026, late afternoon).

Each entry gives a product's own page (its maker's UK page, else a big UK shop's) and, optionally, the main image on its
maker's own page, researched with sources and a date. Every page and shop here is made up.
"""

import json
from datetime import date

import pytest

from engine.product_pages import (
    DEFAULT_PRODUCT_PAGES, ProductPage, ProductPagesError, find_page, image_sources, load_product_pages,
)

DAY = date(2026, 10, 15)
PAGE = "https://maker.example/uk/aircraft-laptop-13/"
IMAGE = "https://images.maker.example/aircraft-13-hero.jpg"


def entry(**changes) -> dict:
    data = {"product": "Maker Aircraft 13", "category": "general", "product_type": "laptop", "page": PAGE,
            "shop": "Maker", "image": IMAGE, "image_page": PAGE, "sources": [PAGE], "checked_on": "2026-10-15",
            "note": "Made up for a test."}
    return {key: value for key, value in (data | changes).items() if value is not ...}


def written(tmp_path, *entries) -> list[ProductPage]:
    path = tmp_path / "product_pages.json"
    path.write_text(json.dumps({"pages": list(entries)}), encoding="utf-8")
    return load_product_pages(path)


def test_an_entry_gives_the_products_own_page_and_its_makers_image(tmp_path):
    [page] = written(tmp_path, entry())
    assert (page.product, page.page, page.shop, page.image, page.image_page, page.checked_on) == (
        "Maker Aircraft 13", PAGE, "Maker", IMAGE, PAGE, DAY)


def test_an_image_is_optional(tmp_path):
    [page] = written(tmp_path, entry(image=..., image_page=...))
    assert page.image is None and page.image_page is None


@pytest.mark.parametrize("changes, problem", [
    ({"page": "http://maker.example/uk/aircraft-laptop-13/"}, "page"),  # https only
    ({"page": "https://www.reddit.com/r/laptops/comments/abc/x/"}, "page"),  # never Reddit
    ({"page": "https://www.amazon.co.uk/s?k=aircraft+13", "sources": ["https://www.amazon.co.uk/s?k=aircraft+13"]},
     "page"),  # direct links only: never a search
    ({"page": "https://me:pw@maker.example/uk/aircraft-laptop-13/"}, "page"),
    ({"image": "data:image/jpeg;base64,/9j/4AAQ"}, "image"),  # no image written into the page
    ({"image": "http://images.maker.example/a.jpg"}, "image"),
    ({"image": "https://i.redd.it/aircraft.jpg"}, "image"),  # never one of Reddit's images
    ({"image_page": ...}, "image"),  # an image says which maker's page it came from
    ({"image": ...}, "image_page"),  # and a page for an image needs the image
    ({"image_page": "https://maker.example/uk/elsewhere/"}, "image_page"),  # one of the pages read
    ({"sources": ["https://maker.example/uk/specs/"]}, "page"),  # the page itself is one of the pages read
    ({"sources": []}, "sources"),
    ({"shop": ""}, "shop"),
    ({"category": "gadgets"}, "category"),
    ({"product_type": "Laptop"}, "product_type"),  # lowercase words, as module 1 writes types
    ({"colour": "silver"}, "colour"),  # an unknown field is a typo, never dropped quietly
])
def test_a_malformed_entry_stops_the_list_with_its_number_and_problem(tmp_path, changes, problem):
    with pytest.raises(ProductPagesError) as error:
        written(tmp_path, entry(product="Another One"), entry(**changes))
    assert "entry 2" in str(error.value) and problem in str(error.value)


def test_a_missing_or_broken_file_says_so(tmp_path):
    with pytest.raises(ProductPagesError):
        load_product_pages(tmp_path / "none.json")
    (tmp_path / "broken.json").write_text("{", encoding="utf-8")
    with pytest.raises(ProductPagesError):
        load_product_pages(tmp_path / "broken.json")


def test_the_real_list_loads():
    assert all(isinstance(page, ProductPage) for page in load_product_pages(DEFAULT_PRODUCT_PAGES))


# --- Finding a product's page ---

def pages(tmp_path):
    return written(
        tmp_path,
        entry(),
        entry(product="Maker Aircraft 15", page="https://maker.example/uk/aircraft-laptop-15/",
              image="https://images.maker.example/aircraft-15.jpg", image_page="https://maker.example/uk/aircraft-laptop-15/",
              sources=["https://maker.example/uk/aircraft-laptop-15/"]),
        entry(product="Sonic Hush 5", product_type="headphones", page="https://shop.example/sonic-hush-5/p123",
              shop="Big Shop", image="https://cdn.sonic.example/hush5.png", image_page="https://sonic.example/hush-5/",
              sources=["https://shop.example/sonic-hush-5/p123", "https://sonic.example/hush-5/"],
              also_called=["Sonic WH-5"]),
    )


def test_a_product_finds_its_page_by_the_name_it_is_shown_under(tmp_path):
    found = find_page(["Maker Aircraft 13"], "general", "laptop", pages(tmp_path))
    assert found.page == PAGE and found.image == IMAGE
    assert find_page(["maker aircraft-13"], "general", "laptop", pages(tmp_path)).page == PAGE  # case and hyphens aside


def test_another_name_it_goes_by_finds_it_too(tmp_path):
    assert find_page(["Sonic WH-5"], "general", "headphones", pages(tmp_path)).shop == "Big Shop"


def test_the_first_name_given_comes_first(tmp_path):
    # The name the answer shows first, then the writers' name: each name finds its own product.
    found = find_page(["Maker Aircraft 15", "Maker Aircraft 13"], "general", "laptop", pages(tmp_path))
    assert found.product == "Maker Aircraft 15"


def test_another_product_or_type_or_category_finds_nothing(tmp_path):
    listed = pages(tmp_path)
    assert find_page(["Maker Aircraft 14"], "general", "laptop", listed) is None  # another model
    assert find_page(["Sonic Hush 5"], "general", "earbuds", listed) is None  # an entry for headphones only
    assert find_page(["Maker Aircraft 13"], "kitchen", None, listed) is None
    assert find_page([], "general", "laptop", listed) is None


def test_the_newest_check_wins_between_two_entries_for_one_product(tmp_path):
    newer = entry(page="https://maker.example/uk/aircraft-13-new/", sources=["https://maker.example/uk/aircraft-13-new/"],
                  image_page="https://maker.example/uk/aircraft-13-new/", checked_on="2026-10-20")
    assert find_page(["Maker Aircraft 13"], "general", "laptop", written(tmp_path, entry(), newer)).checked_on == date(
        2026, 10, 20)


def test_the_page_may_load_only_the_images_hosts(tmp_path):
    # The security policy lets in these hosts' images and no others (engine/web.py), https only.
    assert image_sources(pages(tmp_path)) == ("https://cdn.sonic.example", "https://images.maker.example")
    assert image_sources(written(tmp_path, entry(image=..., image_page=...))) == ()
