"""Researchers' findings into the lists answers read (Noemi's decisions of 15 Oct 2026, late afternoon).

From the live laptop answer, whose first pick was 2010-2011 MacBook Pros with no price and no link: (1) a pick must be
on sale in the UK now; sold second-hand only counts only for things people buy vintage on purpose (her rule of 10 Oct:
Griswold and Wagner cast iron); a discontinued model is left out and named; (2) a pick may show a small image from its
maker's own product page; (3) direct links only, to the product's own page. Whether a product is sold comes from
researched data, never guessed: researchers look each product up and write what they found, one JSON object per line
(found-*.jsonl):

    {"name": "Apple MacBook Air 13-inch (M4)",   the name the answer shows
     "type": "laptop", "category": "general",    its product type and category, as the answer's
     "status": "sold_new",                       sold_new, second_hand_only, not_sold_uk, discontinued or unsure
     "product_page": "https://...",              its own page: its maker's UK page preferred, else a big UK shop's; or null
     "shop": "Apple",                            that page's shop's or maker's plain name
     "price_gbp": 999.0, "price_url": "https://...",   a price in pounds and the page it was read on; or null
     "image_url": "https://...",                 the main image on its maker's own page; or null
     "image_page": "https://...",                the maker's page it is on
     "sources": ["https://..."],                 every page read
     "checked_on": "2026-10-15", "note": "..."}  the day, and what the researcher found (never shown)

How each becomes entries (plan_finding):
- every address is checked (engine.links): https, no name or password, never Reddit's; a product page, and the page a
  price was read on, are never a search (direct links only). An address that fails is left out and reported, with the
  rest of the finding kept; a finding with no source left is refused;
- the price list (data/prices.json, engine/prices.py) says whether it is sold, as it has since 9 Oct:
    sold_new           sold there ("available": true), with its price when one was read on a page of a shop the lists
                       know by name (the product page's own shop, or one the price list names already; a price at a shop
                       the lists don't know is left for a look rather than shown under the wrong name)
    second_hand_only   for a product people buy vintage on purpose (engine.prices.bought_vintage): sold second-hand only
                       ("second_hand": true), shown "Sold second-hand only"; for anything else not sold
    not_sold_uk        not sold ("available": false): left out of answers and named
    discontinued       the same
    unsure             nothing: the product stays as it was, "Availability not checked yet"
- the product pages list (data/product_pages.json, engine/product_pages.py) gets its own page and its maker's image, for
  a product on sale only (one left out is never linked).
Names: an entry is named as the answer shows the product, so the pipeline finds it as it finds every entry of these
lists (module 4's word rules, the category's short names, the name the facts list gives it). A brand's line ("MacBook
laptop line") is recorded in the price list under its brand followed by its type ("MacBook laptop"), the form an entry
speaking for a whole line takes there (engine.prices.find_brand_entry), never with a price (a line has many products;
its "From £X" is data/brand_lines.json's), and its page under the line's own name. Every entry names the finding's
type, so it never speaks for a product of another type; an answer naming an ingredient and no type ("vitamin C
product") shows products of several types, so its findings' entries name none. A page's site is named as its link
says it ("See it at CeraVe"): researchers name in "shop" where the product is sold, which is the page's own site when
the price was read there too, and the price's shop when the page is its maker's.

Writing: new entries are added at the end of each list, in the list's own layout; an entry already there is never
added twice (importing the same findings again adds nothing) and none is ever changed or deleted. A finding that says
otherwise than an entry of the same product and day is imported and reported, for a look by hand.

Images (the coordinator, 15 Oct 2026: lazy loading doesn't help a phone opening a card with a 5 MB image): each image is
checked as it is imported, from its server's headers alone (check_image): one of at most config.IMAGE_MAX_BYTES is kept;
a bigger one gives way to a smaller size of the same image on the maker's own server, asked for the way its image server
takes a width (smaller_sizes); else it is left out, and so is one whose size can't be checked (a server refusing tools
isn't asked again as if by a browser). Why goes in the page's note. A page already imported is never checked again.

A brand line on sale (its researcher: product_page is the maker's UK range page, the price a "from" price) also goes to
the brand-lines list (data/brand_lines.json): a new entry with its range page and from price, or the line's entry given
a range page it lacks and a from price it lacks or has older; that list keeps its own layout.

Command line:
    python -m engine.buyable import <found-*.jsonl>... [--write] [--no-image-check]
        checks the findings (and each image's size, over the network) and says what they would add; --write adds it to
        data/prices.json, data/product_pages.json and data/brand_lines.json
"""

import json
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from engine.brand_lines import DEFAULT_BRAND_LINES, BrandLine, find_brand_line
from engine.config import (
    IMAGE_CHECK_TIMEOUT_SECONDS, IMAGE_MAX_BYTES, IMAGE_SMALLER_WIDTH, PRODUCT_TYPE_SHOWN, THREAD_CATEGORIES,
)
from engine.links import is_direct_page, is_linkable, is_search_page
from engine.match_products import known_aliases, product_words
from engine.prices import DEFAULT_PRICES, Price, bought_vintage
from engine.product_pages import DEFAULT_PRODUCT_PAGES, ProductPage
from engine.query import PRODUCT_TYPES

Status = Literal["sold_new", "second_hand_only", "not_sold_uk", "discontinued", "unsure"]
STATUSES = ("sold_new", "second_hand_only", "not_sold_uk", "discontinued", "unsure")
# What a not-sold entry's note starts with (never shown), so whoever checks the list sees why.
NOTE_START = {
    "not_sold_uk": "not sold to UK shoppers",
    "discontinued": "discontinued",
    "second_hand_only": "sold second-hand only, which counts only for things people buy vintage on purpose (Noemi, "
                        "15 Oct 2026)",
}


class Finding(BaseModel):
    """One researcher's finding, as written in found-*.jsonl. Fields the format doesn't have are reported."""

    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1)
    type: str = Field(min_length=1)
    category: Literal[THREAD_CATEGORIES]
    status: Status
    product_page: str | None = None
    shop: str | None = None
    price_gbp: float | None = Field(default=None, gt=0)
    price_url: str | None = None
    image_url: str | None = None
    image_page: str | None = None
    sources: list[str] = []
    checked_on: date
    note: str | None = None


@dataclass
class Plan:
    """What one finding adds: price-list entries and a product page, as the lists write them, and its problems."""

    prices: list[dict] = field(default_factory=list)
    page: dict | None = None
    problems: list[str] = field(default_factory=list)
    refused: bool = False  # nothing can be recorded: no source left
    not_vintage: bool = False  # sold second-hand only, but not bought vintage on purpose: recorded as not sold
    line_price: bool = False  # a line's price, not recorded as its own (its from price is data/brand_lines.json's)
    # For a line on sale: its brand, type, range page and from price (price, shop, page), for data/brand_lines.json.
    line: dict | None = None


@dataclass
class Report:
    """What an import found and added. Names, addresses and problems only."""

    statuses: Counter = field(default_factory=Counter)
    added_prices: int = 0
    added_pages: int = 0
    already_there: int = 0
    problems: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)
    unsure: list[str] = field(default_factory=list)
    not_vintage: list[str] = field(default_factory=list)
    lines: list[str] = field(default_factory=list)  # brand lines, recorded under their brand
    line_prices: list[str] = field(default_factory=list)  # lines whose price wasn't recorded as the line's own
    lines_updated: int = 0  # brand-lines entries added or given a range page or a newer from price
    images: dict = field(default_factory=lambda: {"kept": 0, "smaller": 0, "dropped": 0})
    images_dropped: list[str] = field(default_factory=list)  # "<product>: <why>"


# --- One finding ---

def plan_finding(finding: Finding, shops: dict[str, str] | None = None) -> Plan:
    """The entries a finding adds (see the module's docstring). `shops`: {host: shop name} of the shops the lists
    already name, for a price read at another shop than the product page's."""
    plan = Plan()
    extra = sorted(set(finding.model_extra or {}))
    if extra:
        plan.problems.append(f"fields the format doesn't have, left out: {', '.join(extra)}")
    sources = []
    for url in finding.sources:
        if is_linkable(url):
            sources.append(url)
        else:
            plan.problems.append(f"a source that can't be used (https only, no name or password, never Reddit): {url}")
    if finding.status == "unsure":
        return plan
    if not sources:
        plan.refused = True
        plan.problems.append("no source left: nothing recorded")
        return plan
    page = _checked(finding.product_page, "product_page", plan, direct=True)
    product_type = _own_type(finding.type)
    line = line_parts(finding.name, finding.type)
    line_brand = line[0] if line else None
    if line:
        product_type = line[1]
    product = f"{line_brand} {product_type}" if line_brand else finding.name
    shops = shops or {}
    shop = (finding.shop or "").strip()
    price_url = _checked(finding.price_url, "price_url", plan, direct=True) if finding.price_gbp is not None else None
    page_site, page_is_makers = _page_site(finding, page, price_url, shop, line_brand, shops)
    base = {"product": product, "category": finding.category, "product_type": product_type}
    checked = finding.checked_on.isoformat()
    if finding.status == "sold_new":
        price, price_shop = None, None
        if price_url is not None:
            price_shop = _price_site(price_url, page, shop, shops)
            if price_shop is None:
                plan.problems.append(f"price_url: a shop the lists don't name yet ({_host(price_url)}): the price "
                                     "is left for a look")
                price_url = None
            elif line_brand:
                # Sold there; but a line has many products, so no single price: its "From £X" is the brand-lines
                # list's job (its researcher: a line's price is a from price).
                plan.line_price = True
            else:
                price = finding.price_gbp
        elif finding.price_url and finding.price_gbp is None:
            plan.problems.append("price_url without price_gbp: no price recorded")
        if price_url is not None:
            entry = base | {"price": price, "currency": "GBP", "shop": price_shop, "url": price_url}
        else:
            # Sold at the shop the finding names, at a page of that shop among its pages.
            seller = shop or page_site or _host(sources[0])
            at_shop = _page_at(seller, [page, *sources], shops)
            if at_shop is None:
                plan.problems.append(f"no page of {seller} among the finding's pages: recorded as sold there with its "
                                     "product page, for a look")
            entry = base | {"price": None, "currency": "GBP", "shop": seller, "url": at_shop or page or sources[0]}
        entry |= {"checked_on": checked, "available": True}
        plan.prices.append(_with_sources(entry, sources, finding.note))
        plan.page = _page_entry(finding, page, page_site, sources, plan, product_type)
        if line_brand:
            # Its researcher: a line's product page is its range page (the maker's UK range page, or a stockist's,
            # which then names it).
            plan.line = {"brand": line_brand, "category": finding.category, "product_type": product_type,
                         "range_page": page, "range_shop": None if page is None or page_is_makers else page_site,
                         "from_price": float(finding.price_gbp) if plan.line_price else None,
                         "from_price_shop": price_shop if plan.line_price else None,
                         "from_price_url": price_url if plan.line_price else None,
                         "checked_on": checked, "sources": sources}
        return plan
    shop = shop or page_site or _shops_name(sources[0], shops) or _host(sources[0])
    if finding.status == "second_hand_only" and bought_vintage(product, finding.category):
        # A page of the shop it names ("Sold second-hand only: eBay UK"), the sources' first one otherwise.
        at_shop = _page_at(shop, [page, *sources], shops)
        entry = base | {"price": None, "currency": "GBP", "shop": shop, "url": at_shop or page or sources[0],
                        "checked_on": checked, "available": True, "second_hand": True}
        plan.prices.append(_with_sources(entry, sources, finding.note))
        return plan
    plan.not_vintage = finding.status == "second_hand_only"
    note = NOTE_START[finding.status] + (f": {finding.note}" if finding.note else "")
    entry = base | {"price": None, "currency": "GBP", "shop": shop, "url": sources[0], "checked_on": checked,
                    "available": False}
    plan.prices.append(_with_sources(entry, sources, note))
    return plan


def _page_site(finding: Finding, page: str | None, price_url: str | None, shop: str, line_brand: str | None,
               shops: dict[str, str]) -> tuple[str | None, bool]:
    """The name of the product page's site, as a link to it says ("See it at CeraVe"), and whether it is its maker's.
    Researchers name in "shop" where the product is sold: the page's own site when the price was read there too (or no
    price was read), else the price's shop, while the page is its maker's (the first findings: CeraVe's own UK pages
    with a price at a shop). So: the page with the price, or with no price, is the shop's; else the maker's name as the
    product's own name starts, when it matches the site's address ("CeraVe" at cerave.co.uk; a line's brand, "Lodge" at
    lodgecastiron.com); else the name the lists already give that site; else the site's address."""
    if page is None:
        return None, False
    host = _host(page)
    maker = _maker_of(line_brand or finding.name, host, whole=line_brand is not None)
    if price_url is not None and host == _host(price_url):
        return shop or maker or _shops_name(page, shops) or host, maker is not None
    if maker is not None and not (shop and _names_site(shop, host)):
        return maker, True  # its maker's own page; "shop" names where it is sold
    if price_url is None and shop:
        return shop, maker is not None  # the one site the finding names
    return _shops_name(page, shops) or host, maker is not None


def _price_site(price_url: str, page: str | None, shop: str, shops: dict[str, str]) -> str | None:
    """The shop a price was read at. Its researchers name it in "shop" (the coordinator, 15 Oct 2026: "shop" is the shop
    the price came from, or the product page's owner when there is no price). So: the finding's shop when the price is
    on the product page's own site; else the name the lists already give the price's site, for the same shop to be
    named alike everywhere; else the finding's shop, unless it plainly names the product page's own site while the
    price is on another (then which is meant is left for a look rather than shown under the wrong shop's name)."""
    if page is not None and _host(price_url) == _host(page):
        return shop or None
    known = _shops_name(price_url, shops)
    if known is not None:
        return known
    if not shop or (page is not None and _names_site(shop, _host(page))):
        return None
    return shop


def _page_at(shop: str, urls: list[str | None], shops: dict[str, str]) -> str | None:
    """The first of these pages that is the named shop's, by its address or the name the lists give its site."""
    return next((url for url in urls if url and (_names_site(shop, _host(url)) or _shops_name(url, shops) == shop)),
                None)


def _names_site(name: str, host: str) -> bool:
    """Whether a name spells one of a site's labels ("Wüsthof UK" at wusthof.co.uk, "ASUS" at asus.com)."""
    letters = _letters(name)
    return len(letters) >= 3 and any(len(label) >= 3 and (label.startswith(letters) or letters.startswith(label))
                                     for label in _labels(host))


def _labels(host: str) -> list[str]:
    """A site's address in words: its labels, hyphens aside ("subzero-wolf.co.uk": subzerowolf, co, uk)."""
    return [label.replace("-", "") for label in host.split(".")]


def _maker_of(name: str, host: str, whole: bool = False) -> str | None:
    """The maker's name as a product's name starts, when the site's address spells it: the longest run of the name's
    first words (up to four) whose letters are one of the address's labels, or begin it ("Lodge" at lodgecastiron.com,
    "Beauty of Joseon" at beautyofjoseon.com, "innisfree" at us.innisfree.com, "Wüsthof" at wusthof.co.uk). `whole`:
    the name is a brand already (a line's), so only all of it counts. None when nothing matches."""
    labels = [label for label in _labels(host) if len(label) >= 3]
    words = name.split()
    tried = [len(words)] if whole else range(min(4, len(words)), 0, -1)
    for k in tried:
        letters = _letters(" ".join(words[:k]))
        if len(letters) >= 3 and any(label == letters or label.startswith(letters) for label in labels):
            return " ".join(words[:k])
    return None


def _letters(text: str) -> str:
    """Lowercase letters and digits only, accents taken off and "&" spelled "and" ("Wüsthof" -> "wusthof",
    "Holland & Barrett" -> "hollandandbarrett")."""
    plain = unicodedata.normalize("NFKD", text.lower().replace("&", "and").replace("+", "and"))
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in plain if not unicodedata.combining(c)))


def line_brand_of(name: str, product_type: str) -> str | None:
    """The brand of a brand line's name as answers show it ("MacBook laptop line": "MacBook"; engine.group_products.
    brand_pick_name), or None for a product's name."""
    line = line_parts(name, product_type)
    return line[0] if line else None


def line_parts(name: str, product_type: str) -> tuple[str, str] | None:
    """A brand line's brand and its own type, from its name as answers show it, "<brand> <type> line"
    (engine.group_products.brand_pick_name): ("MacBook", "laptop"). The finding's type first, then module 1's types,
    the longest first, written as names show them ("Le Creuset Dutch oven line"), so a line in an answer naming an
    ingredient ("Paula's Choice 2% BHA exfoliant line" in "salicylic acid product") has its own. None for a product."""
    match = re.fullmatch(r"(.+?)\s+line", name.strip(), re.IGNORECASE)
    if not match:
        return None
    rest = match.group(1)
    for candidate in [product_type, *_TYPES_LONGEST_FIRST]:
        shown = PRODUCT_TYPE_SHOWN.get(candidate, candidate)
        if rest.lower().endswith(" " + shown.lower()) and len(rest) > len(shown) + 1:
            return rest[: -len(shown) - 1].strip(), candidate
    return None


def _own_type(product_type: str) -> str | None:
    """The type an entry names: the finding's, unless it is no product type but an answer's ingredient title ("vitamin
    C product": an answer naming an ingredient and no type shows products of several types, each looked up by its own
    type), when the entry names none and so speaks for any type."""
    if not _TYPE_WORDS.fullmatch(product_type) or product_type.endswith(" product"):
        return None
    return product_type


_TYPE_WORDS = re.compile(r"[a-z0-9]+(?:[ -][a-z0-9]+)*")
_TYPES_LONGEST_FIRST = sorted({p.name for p in PRODUCT_TYPES}, key=lambda name: (-len(name), name))


def _checked(url: str | None, name: str, plan: Plan, direct: bool = False) -> str | None:
    if not url:
        return None
    if not is_linkable(url):
        plan.problems.append(f"{name} can't be used (https only, no name or password, never Reddit): {url}")
        return None
    if direct and is_search_page(url):
        plan.problems.append(f"{name} is a search, never linked (direct links only): {url}")
        return None
    return url


def _page_entry(finding: Finding, page: str | None, shop: str, sources: list[str], plan: Plan,
                product_type: str | None) -> dict | None:
    """The product page entry of a product on sale: its page, and its maker's image when both addresses pass, under
    the name the answer shows and the type its price-list entry names."""
    if page is None:
        return None
    image = _checked(finding.image_url, "image_url", plan)
    image_page = _checked(finding.image_page, "image_page", plan)
    if (image is None) != (image_page is None):
        if image is not None or image_page is not None:
            plan.problems.append("image_url and image_page come together: the image is left out")
        image = image_page = None
    pages_read = list(dict.fromkeys([page, *([image_page] if image_page else []), *sources]))
    entry = {"product": finding.name, "category": finding.category, "product_type": product_type, "page": page,
             "shop": shop}
    if image is not None:
        entry |= {"image": image, "image_page": image_page}
    entry |= {"sources": pages_read, "checked_on": finding.checked_on.isoformat()}
    return entry | ({"note": finding.note} if finding.note else {})


def _with_sources(entry: dict, sources: list[str], note: str | None) -> dict:
    """The entry with every other page read (its `sources`, never shown) and the researcher's note."""
    others = [url for url in sources if url != entry["url"]]
    if others:
        entry["sources"] = list(dict.fromkeys([entry["url"], *others]))
    if note:
        entry["note"] = note
    return entry


def _host(url: str) -> str:
    return (urlsplit(url).hostname or "").lower().removeprefix("www.")


def _shops_name(url: str, shops: dict[str, str]) -> str | None:
    return shops.get(_host(url))


# --- Images: checked as they are imported (the coordinator, 15 Oct 2026) ---

@dataclass(frozen=True)
class ImageFacts:
    """What an image's server says of it, from its headers alone: its size in bytes and kind, the address it ends at
    (after redirects), or the problem in words when it wouldn't say."""

    size: int | None
    content_type: str | None
    url: str | None
    problem: str | None


@dataclass(frozen=True)
class ImageCheck:
    """An image as it is kept: `url` the image to show (the one researched, or a smaller size of it on the maker's own
    server), or None when it is left out; `reason` says why it was left out or changed, for the page's note."""

    url: str | None
    size: int | None
    reason: str | None


IMAGE_CHECKER = "credible-recs-image-check/1.0 (asks image servers for an image's size only)"


def head_image(url: str) -> ImageFacts:
    """An image's size and kind, from its server's headers: a HEAD request, else a request for its first byte only
    (whose answer gives the whole size). Never the image itself, and as the tool it is: a server that refuses tools
    isn't asked again as if by a browser. The network is used here only, as findings are imported; tests give their
    own stand-in."""
    import ssl
    import urllib.error
    import urllib.request

    import certifi

    # Python from python.org on macOS has no certificates of its own; certifi brings the standard set (as
    # engine/bright_data.py does).
    context = ssl.create_default_context(cafile=certifi.where())
    for method, headers in (("HEAD", {}), ("GET", {"Range": "bytes=0-0"})):
        request = urllib.request.Request(url, method=method, headers={"User-Agent": IMAGE_CHECKER, **headers})
        try:
            with urllib.request.urlopen(request, timeout=IMAGE_CHECK_TIMEOUT_SECONDS, context=context) as response:
                kind = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower() or None
                size = _whole_size(response.headers)
                if size is not None or method == "GET":
                    return ImageFacts(size, kind, response.geturl(), None)
        except urllib.error.HTTPError as e:
            if method == "GET" or e.code not in (400, 403, 405, 501):
                problem = "refuses automated requests" if e.code in (401, 403) else "isn't there"
                return ImageFacts(None, None, None, f"{problem} ({e.code})")
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
            return ImageFacts(None, None, None, f"couldn't be reached ({type(e).__name__})")
    return ImageFacts(None, None, None, "its size isn't given")


def _whole_size(headers) -> int | None:
    found = re.fullmatch(r"bytes \d+-\d+/(\d+)", (headers.get("Content-Range") or "").strip())
    if found:
        return int(found.group(1))
    length = (headers.get("Content-Length") or "").strip()
    return int(length) if length.isdigit() and not headers.get("Content-Range") else None


def check_image(url: str, head=head_image) -> ImageCheck:
    """An image kept as it is when its server says it is at most IMAGE_MAX_BYTES; else a smaller size of the same image
    on the maker's own server (smaller_sizes) when one is; else left out, with why. One whose server won't say, or that
    isn't an image, is left out too: never guessed."""
    facts = head(url)
    if facts.problem is not None:
        return ImageCheck(None, None, f"its size couldn't be checked: the server {facts.problem}")
    if not (facts.content_type or "").startswith("image/"):
        return ImageCheck(None, None, f"not an image ({facts.content_type or 'no kind given'})")
    if facts.size is None:
        return ImageCheck(None, None, "its size couldn't be checked: the server doesn't give it")
    shown = facts.url if facts.url and is_linkable(facts.url) else url
    if facts.size <= IMAGE_MAX_BYTES:
        return ImageCheck(shown, facts.size, None if shown == url else f"the image's address after redirects: {shown}")
    for smaller in smaller_sizes(shown):
        other = head(smaller)
        if (other.problem is None and (other.content_type or "").startswith("image/") and other.size is not None
                and other.size <= IMAGE_MAX_BYTES and _host(other.url or smaller) == _host(shown)):
            return ImageCheck(other.url or smaller, other.size, f"a smaller size of the maker's image ({_bytes(other.size)} "
                                                                 f"instead of {_bytes(facts.size)})")
    return ImageCheck(None, facts.size, f"{_bytes(facts.size)}, over {_bytes(IMAGE_MAX_BYTES)}, and no smaller size of "
                                         "it on the maker's server")


def smaller_sizes(url: str, width: int = IMAGE_SMALLER_WIDTH) -> list[str]:
    """The same image, `width` pixels wide, as its image server takes a width (Shopify's "width", Scene7's "wid",
    Salesforce Commerce's "sw", Sitecore's "mw", Cloudflare's "width=" step, imgix's, Contentful's and Sanity's "w"),
    on its own server only; a plain "width" for any other."""
    parts = urlsplit(url)
    host, path = (parts.hostname or "").lower(), parts.path
    if "/cdn-cgi/image/" in path:
        options = re.sub(r"(?<=[/,])width=\d+", f"width={width}", path) if "width=" in path else path.replace(
            "/cdn-cgi/image/", f"/cdn-cgi/image/width={width},", 1)
        return [urlunsplit(parts._replace(path=options))]
    if "/cdn/shop/" in path or host == "cdn.shopify.com":
        keys = ["width"]
    elif "/is/image/" in path:
        keys = ["wid"]
    elif "demandware.static" in url or "/dw/image/" in path:
        keys = ["sw"]
    elif "/-/media/" in path:
        keys = ["mw"]
    elif host.endswith(("imgix.net", "images.ctfassets.net", "cdn.sanity.io")):
        keys = ["w"]
    else:
        keys = ["width"]
    return [_with_query(parts, key, str(width)) for key in keys]


def _with_query(parts, key: str, value: str) -> str:
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k != key] + [(key, value)]
    return urlunsplit(parts._replace(query=urlencode(query, safe=":/,")))


def _bytes(size: int) -> str:
    """Sizes as people say them: "42 KB", "3.4 MB" (decimal, as servers and phones count them)."""
    if size >= 1_000_000:
        return f"{size / 1_000_000:.1f}".rstrip("0").rstrip(".") + " MB"
    return f"{round(size / 1000)} KB"


# --- The lists ---

def known_shops(prices: list[dict], pages: list[dict], brand_lines: list[dict] = ()) -> dict[str, str]:
    """{host: shop name} of every shop the lists already name, each host by its commonest name."""
    seen: dict[str, Counter] = {}
    pairs = [(p.get("url"), p.get("shop")) for p in prices] + [(p.get("page"), p.get("shop")) for p in pages]
    pairs += [(b.get("from_price_url"), b.get("from_price_shop")) for b in brand_lines]
    pairs += [(b.get("range_page"), b.get("range_shop")) for b in brand_lines]
    for url, shop in pairs:
        if url and shop:
            seen.setdefault(_host(url), Counter())[shop] += 1
    return {host: names.most_common(1)[0][0] for host, names in seen.items()}


def read_findings(paths: list[Path], report: Report) -> list[Finding]:
    findings = []
    for path in paths:
        for number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            where = f"{Path(path).name}:{number}"
            try:
                findings.append((where, Finding.model_validate(json.loads(line))))
            except (json.JSONDecodeError, ValidationError) as e:
                problem = str(e).splitlines()[0] if isinstance(e, json.JSONDecodeError) else "; ".join(
                    f"{'.'.join(map(str, err['loc'])) or 'line'}: {err['msg']}" for err in e.errors())
                report.problems.append(f"{where}: not a finding ({problem})")
    return findings


def import_findings(paths: list[Path], prices_path: Path | None = None, pages_path: Path | None = None,
                    write: bool = False, brand_lines_path: Path | None = None, image_head=None) -> Report:
    """Checks the findings in `paths` and adds what they say to the price list, the product pages list and, for brand
    lines on sale, the brand-lines list (only with `write`); returns what was found and added, and every problem.
    The lists are data/prices.json, data/product_pages.json and data/brand_lines.json unless given (DEFAULT_PRICES,
    DEFAULT_PRODUCT_PAGES and DEFAULT_BRAND_LINES, read when called: the tests point them at copies).
    `image_head`: how an image's size is asked of its server (head_image, which uses the network; the command line
    passes it); None checks no image."""
    prices_path = Path(prices_path or DEFAULT_PRICES)
    pages_path = Path(pages_path or DEFAULT_PRODUCT_PAGES)
    brand_lines_path = Path(brand_lines_path or DEFAULT_BRAND_LINES)
    report = Report()
    prices_data = json.loads(Path(prices_path).read_text(encoding="utf-8"))
    pages_data = json.loads(Path(pages_path).read_text(encoding="utf-8"))
    lines_file = Path(brand_lines_path).is_file()
    lines_data = json.loads(Path(brand_lines_path).read_text(encoding="utf-8")) if lines_file else {"brand_lines": []}
    prices, pages, lines = prices_data["prices"], pages_data["pages"], lines_data["brand_lines"]
    shops = known_shops(prices, pages, lines)
    seen_prices = {_price_key(p) for p in prices}
    seen_pages = {_page_key(p) for p in pages}
    for where, finding in read_findings(paths, report):
        report.statuses[finding.status] += 1
        plan = plan_finding(finding, shops)
        report.problems += [f"{where} {finding.name}: {problem}" for problem in plan.problems]
        if finding.status == "unsure":
            report.unsure.append(finding.name)
        if plan.refused:
            report.refused.append(finding.name)
        if plan.not_vintage:
            report.not_vintage.append(finding.name)
        if plan.line_price:
            report.line_prices.append(finding.name)
        if line_brand_of(finding.name, finding.type):
            report.lines.append(finding.name)
        for entry in plan.prices:
            try:
                Price.model_validate(entry)  # every entry written loads as the price list's do
            except ValidationError as e:
                report.problems.append(f"{where} {finding.name}: a price-list entry that wouldn't load, not added "
                                       f"({_problems(e)})")
                continue
            key = _price_key(entry)
            if key in seen_prices:
                report.already_there += 1
                continue
            disagreeing = [p for p in prices if _same_day_product(p, entry) and _sold(p) != _sold(entry)]
            if disagreeing:
                report.problems.append(f"{where} {finding.name}: the price list already has an entry of "
                                       f"{entry['checked_on']} that says otherwise: both kept, for a look by hand")
            prices.append(entry)
            seen_prices.add(key)
            report.added_prices += 1
        if plan.line is not None and _update_line(lines, plan.line, finding, report, where):
            report.lines_updated += 1
        if plan.page is not None:
            key = _page_key(plan.page)
            if key in seen_pages:  # already imported: its image was checked then
                report.already_there += 1
                continue
            page = _with_checked_image(plan.page, image_head, report) if image_head is not None else plan.page
            try:
                ProductPage.model_validate(page)
            except ValidationError as e:
                report.problems.append(f"{where} {finding.name}: a product page that wouldn't load, not added "
                                       f"({_problems(e)})")
                continue
            pages.append(page)
            seen_pages.add(key)
            report.added_pages += 1
    if write:
        _write(prices_path, prices_data)
        _write(pages_path, pages_data)
        if lines_file and report.lines_updated:
            _write_brand_lines(brand_lines_path, lines_data)
    return report


def _with_checked_image(page: dict, image_head, report: Report) -> dict:
    """The page entry with its image checked (check_image): kept, a smaller size of it, or left out with why, in the
    entry's note (never shown)."""
    if page.get("image") is None:
        return page
    checked = check_image(page["image"], image_head)
    page = dict(page)
    if checked.url is None:
        report.images["dropped"] += 1
        report.images_dropped.append(f"{page['product']}: {checked.reason}")
        page.pop("image", None)
        page.pop("image_page", None)
        page["note"] = "; ".join(filter(None, [page.get("note"), f"image left out: {checked.reason}"]))
        return page
    report.images["smaller" if checked.url != page["image"] else "kept"] += 1
    if checked.url != page["image"]:
        page["image"] = checked.url
        page["note"] = "; ".join(filter(None, [page.get("note"), f"image: {checked.reason}"]))
    return page


def _update_line(lines: list[dict], line: dict, finding: Finding, report: Report, where: str) -> bool:
    """A brand line on sale (its researcher: its maker's UK range page, and a "from" price) in the brand-lines list
    (engine/brand_lines.py): a new entry saying the brand sells the type, with its range page and from price; or, for
    the line's entry already there, its range page when it has none, and a from price when it has none or an older
    one. Whether the brand sells the type is never changed: an entry saying it doesn't is left for a look. True when
    the list changed."""
    aliases = known_aliases().get(line["category"], {})
    loaded = []
    for entry in lines:
        try:
            loaded.append(BrandLine.model_validate(entry))
        except ValidationError:
            loaded.append(None)
    existing = find_brand_line([line["brand"]], line["category"], line["product_type"],
                               [entry for entry in loaded if entry is not None])
    sources = lambda entry, *urls: list(dict.fromkeys([*entry.get("sources", []), *[u for u in urls if u]]))
    if existing is None:
        if line["range_page"] is None and line["from_price"] is None:
            return False
        entry = {"brand": line["brand"], "category": line["category"], "product_type": line["product_type"],
                 "sells": True, "sources": sources({}, line["range_page"], line["from_price_url"], *line["sources"]),
                 "checked_on": line["checked_on"]}
        if line["range_page"] is not None:
            entry["range_page"] = line["range_page"]
            if line["range_shop"]:
                entry["range_shop"] = line["range_shop"]
        if line["from_price"] is not None:
            entry |= {"from_price": line["from_price"], "from_price_shop": line["from_price_shop"],
                      "from_price_url": line["from_price_url"], "from_price_checked_on": line["checked_on"]}
        entry["note"] = "From the research findings of " + line["checked_on"] + (
            f": {finding.note}" if finding.note else ".") + (
            "" if line["range_page"] is not None else " No range page: the finding gives none.")
        try:
            BrandLine.model_validate(entry)
        except ValidationError as e:
            report.problems.append(f"{where} {finding.name}: a brand-lines entry that wouldn't load, not added "
                                   f"({_problems(e)})")
            return False
        lines.append(entry)
        return True
    entry = lines[loaded.index(existing)]
    if not existing.sells:
        report.problems.append(f"{where} {finding.name}: the brand-lines list says {existing.brand} doesn't sell "
                               f"{line['product_type']}s, yet it was found on sale: for a look by hand")
        return False
    changed = dict(entry)
    if existing.range_page is None and line["range_page"] is not None:
        changed |= {"range_page": line["range_page"], "sources": sources(changed, line["range_page"]),
                    "checked_on": max(existing.checked_on.isoformat(), line["checked_on"])}
        if line["range_shop"]:
            changed["range_shop"] = line["range_shop"]
    newer = existing.from_price_checked_on is None or existing.from_price_checked_on.isoformat() < line["checked_on"]
    if line["from_price"] is not None and (existing.from_price is None or newer):
        changed |= {"from_price": line["from_price"], "from_price_shop": line["from_price_shop"],
                    "from_price_url": line["from_price_url"], "from_price_checked_on": line["checked_on"],
                    "sources": sources(changed, line["from_price_url"])}
    if changed == entry:
        return False
    try:
        BrandLine.model_validate(changed)
    except ValidationError as e:
        report.problems.append(f"{where} {finding.name}: the brand-lines entry wouldn't load changed, left as it was "
                               f"({_problems(e)})")
        return False
    entry.clear()
    entry.update(_in_brand_lines_order(changed))
    return True


_BRAND_LINE_ORDER = ("brand", "also_called", "category", "product_type", "sells", "sources", "checked_on", "range_page",
                     "range_shop", "from_price", "from_price_shop", "from_price_url", "from_price_checked_on", "note")


def _in_brand_lines_order(entry: dict) -> dict:
    return {key: entry[key] for key in _BRAND_LINE_ORDER if key in entry} | {
        key: value for key, value in entry.items() if key not in _BRAND_LINE_ORDER}


def _write_brand_lines(path: Path, data: dict) -> None:
    """The brand-lines list in its own layout: as the price list's, but a list of addresses on one line."""
    text = json.dumps(data, indent=1, ensure_ascii=False)
    text = re.sub(r'\[\n\s*((?:"(?:[^"\\]|\\.)*",\n\s*)*"(?:[^"\\]|\\.)*")\n\s*\]',
                  lambda m: "[" + re.sub(r",\n\s*", ", ", m.group(1)) + "]", text)
    Path(path).write_text(text + "\n", encoding="utf-8")


def _problems(error: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, err['loc'])) or 'entry'}: {err['msg'].removeprefix('Value error, ')}"
                     for err in error.errors())


def _price_key(entry: dict) -> tuple:
    return tuple(json.dumps(entry.get(k)) for k in ("product", "category", "product_type", "price", "currency", "shop",
                                                    "url", "checked_on", "available", "second_hand"))


def _page_key(entry: dict) -> tuple:
    """A page entry's identity: its product and page on a day (its image may change as it is checked)."""
    return tuple(json.dumps(entry.get(k)) for k in ("product", "category", "product_type", "page", "shop", "checked_on"))


def _same_day_product(a: dict, b: dict) -> bool:
    return (a.get("checked_on") == b.get("checked_on") and a.get("category") == b.get("category")
            and a.get("product_type") in (None, b.get("product_type"))
            and product_words(a.get("product", "")) == product_words(b.get("product", "")))


def _sold(entry: dict) -> bool | None:
    return entry.get("available")


def _write(path: Path, data: dict) -> None:
    Path(path).write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


# --- Command line ---

def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] != "import":
        print(__doc__)
        return 2
    write = "--write" in argv
    check = "--no-image-check" not in argv
    paths = [Path(a) for a in argv[1:] if not a.startswith("--")]
    report = import_findings(paths, write=write, image_head=head_image if check else None)
    print("Findings: " + ", ".join(f"{report.statuses[s]} {s}" for s in STATUSES))
    verb = "Added" if write else "Would add (run again with --write to add them)"
    print(f"{verb}: {report.added_prices} price-list entries, {report.added_pages} product pages; "
          f"{report.already_there} already there.")
    for heading, names in (("Unsure, nothing recorded", report.unsure), ("Refused, no source left", report.refused),
                           ("Sold second-hand only but not bought vintage on purpose, recorded as not sold",
                            report.not_vintage), ("Brand lines, recorded under their brand", report.lines),
                           ("Lines' prices, recorded as their from prices in data/brand_lines.json (never as a line's "
                            "own price in the price list)", report.line_prices)):
        if names:
            print(f"{heading} ({len(names)}): {', '.join(names)}")
    if check:
        print(f"Images: {report.images['kept']} kept, {report.images['smaller']} at a smaller size of the maker's own, "
              f"{report.images['dropped']} left out (why, in each page's note):")
        for dropped in report.images_dropped:
            print(f"  {dropped}")
    if report.lines_updated:
        print(f"Brand lines: {report.lines_updated} entries added or given a range page or a newer from price.")
    if report.problems:
        print(f"Problems ({len(report.problems)}):")
        for problem in report.problems:
            print(f"  {problem}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
