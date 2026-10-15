"""Links shown to shoppers (Noemi's decisions of 15 Oct 2026, late afternoon: direct links only).

A link on a card goes to a product's own page, its maker's or a big UK shop's, never to a search ("no search links, so
a pick not researched yet shows no link"), and every address a card shows, a page or an image, is https, carries no
name or password and is never Reddit's (the page checks them again, as rangeUrl does).
"""

import pytest

from engine.links import is_direct_page, is_linkable, is_search_page


@pytest.mark.parametrize("url", [
    "https://www.apple.com/uk/macbook-air/",
    "https://www.johnlewis.com/sony-wh-1000xm5/p6128564",
    "https://www.amazon.co.uk/dp/B0BX2L8PBT",
    "https://shop.example/products/kettle?variant=4211",  # a shop's own product page with its variant chosen
    "https://images.example/cdn/macbook-air.jpg?w=600",
])
def test_an_https_address_without_a_name_or_password_can_be_linked(url):
    assert is_linkable(url)


@pytest.mark.parametrize("url", [
    "http://www.apple.com/uk/macbook-air/",  # https only
    "https://user:secret@shop.example/kettle",  # never a name or password
    "https://shop.example/a kettle",  # no spaces
    "data:image/png;base64,iVBORw0KGgo=",  # an image written into the page is no address of a maker's
    "javascript:alert(1)",
    "//shop.example/kettle",
    "https://",
    "",
    None,
    "https://www.reddit.com/r/BuyItForLife/comments/abc/x/",  # never Reddit: writers aren't makers or shops
    "https://reddit.com/r/headphones/",
    "https://old.reddit.com/r/laptops/",
    "https://i.redd.it/picture.jpg",
    "https://preview.redd.it/picture.jpg?width=640",
    "https://external-preview.redd.it/picture.jpg",
    "https://styles.redditmedia.com/picture.png",
    "https://www.redditstatic.com/picture.png",
])
def test_anything_else_is_never_linked(url):
    assert not is_linkable(url)


@pytest.mark.parametrize("url", [
    # The searches the price list held on 15 Oct 2026, for products it says are sold or not sold.
    "https://www.ebay.co.uk/sch/i.html?_nkw=griswold+cast+iron+skillet",
    "https://www.amazon.co.uk/s?k=Cuisinart+GK-1",
    "https://www.boroughkitchen.com/search?q=fellow+kettle&type=product",
    "https://www.argos.co.uk/search/tefal-frying-pan/",
    "https://www.johnlewis.com/search?search-term=oxo",
    "https://www.boots.com/sitesearch?searchTerm=loreal+paris+elvive+hair+mask",
    "https://www.costco.co.uk/search?text=kirkland%20signature%20towel",
    "https://www.medicines.org.uk/emc/search?q=altreno",
    # And others a researcher could find.
    "https://www.google.com/search?q=macbook+air",
    "https://www.currys.co.uk/search?q=laptop",
    "https://shop.example/catalog?keyword=kettle",
])
def test_a_search_is_never_a_direct_link(url):
    assert is_search_page(url) and not is_direct_page(url)


@pytest.mark.parametrize("url", [
    "https://www.apple.com/uk/macbook-air/",
    "https://www.johnlewis.com/sony-wh-1000xm5/p6128564",
    "https://www.amazon.co.uk/dp/B0BX2L8PBT",
    "https://www.boots.com/biore-uv-aqua-rich-watery-essence-j-beauty-sunscreen-spf-50-50ml-10356353",
    "https://shop.example/products/kettle?variant=4211",
    "https://www.argos.co.uk/product/9520103",
    "https://maker.example/uk/search-and-rescue-torch",  # a product whose name holds the word, not a search step
])
def test_a_products_own_page_is_a_direct_link(url):
    assert not is_search_page(url) and is_direct_page(url)


def test_an_address_that_cant_be_linked_is_no_direct_link_whatever_its_path():
    assert not is_direct_page("http://www.apple.com/uk/macbook-air/")
    assert not is_direct_page("https://www.reddit.com/r/laptops/comments/abc/best_laptop/")
