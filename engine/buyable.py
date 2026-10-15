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

Command line:
    python -m engine.buyable import <found-*.jsonl>... [--write]   checks the findings and says what they would add;
                                                                   --write adds it to data/prices.json and
                                                                   data/product_pages.json
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
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from engine.brand_lines import DEFAULT_BRAND_LINES
from engine.config import PRODUCT_TYPE_SHOWN, THREAD_CATEGORIES
from engine.links import is_direct_page, is_linkable, is_search_page
from engine.match_products import product_words
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
            price_shop = _price_site(price_url, page, shop, page_is_makers, shops)
            if price_shop is None:
                plan.problems.append(f"price_url: a shop the lists don't name yet ({_host(price_url)}): the price "
                                     "is left for a look")
                price_url = None
            elif line_brand:
                # Sold there; but a line has many products, so no single price: its "From £X" is the brand-lines
                # list's job.
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


def _price_site(price_url: str, page: str | None, shop: str, page_is_makers: bool, shops: dict[str, str]) -> str | None:
    """The shop a price was read at: the finding's shop when the price is on the product page's own site, or when the
    product page is its maker's (then "shop" names where it is sold); else the name the lists already give that site;
    None when they give none (the price is then left for a look rather than shown under the wrong shop's name)."""
    if page is not None and _host(price_url) == _host(page):
        return shop or None
    known = _shops_name(price_url, shops)
    if known is not None:
        return known
    return shop if page_is_makers and shop and not _names_site(shop, _host(page)) else None


def _page_at(shop: str, urls: list[str | None], shops: dict[str, str]) -> str | None:
    """The first of these pages that is the named shop's, by its address or the name the lists give its site."""
    return next((url for url in urls if url and (_names_site(shop, _host(url)) or _shops_name(url, shops) == shop)),
                None)


def _names_site(name: str, host: str) -> bool:
    """Whether a name spells one of a site's labels ("Wüsthof UK" at wusthof.co.uk, "ASUS" at asus.com)."""
    letters = _letters(name)
    return len(letters) >= 3 and any(len(label) >= 3 and (label.startswith(letters) or letters.startswith(label))
                                     for label in host.split("."))


def _maker_of(name: str, host: str, whole: bool = False) -> str | None:
    """The maker's name as a product's name starts, when the site's address spells it: the longest run of the name's
    first words (up to four) whose letters are one of the address's labels, or begin it ("Lodge" at lodgecastiron.com,
    "Beauty of Joseon" at beautyofjoseon.com, "innisfree" at us.innisfree.com, "Wüsthof" at wusthof.co.uk). `whole`:
    the name is a brand already (a line's), so only all of it counts. None when nothing matches."""
    labels = [label for label in host.split(".") if len(label) >= 3]
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
    plain = unicodedata.normalize("NFKD", text.lower().replace("&", "and"))
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


def import_findings(paths: list[Path], prices_path: Path = DEFAULT_PRICES, pages_path: Path = DEFAULT_PRODUCT_PAGES,
                    write: bool = False, brand_lines_path: Path = DEFAULT_BRAND_LINES) -> Report:
    """Checks the findings in `paths` and adds what they say to the price list and the product pages list (only with
    `write`); returns what was found and added, and every problem."""
    report = Report()
    prices_data = json.loads(Path(prices_path).read_text(encoding="utf-8"))
    pages_data = json.loads(Path(pages_path).read_text(encoding="utf-8"))
    lines_data = (json.loads(Path(brand_lines_path).read_text(encoding="utf-8"))["brand_lines"]
                  if Path(brand_lines_path).is_file() else [])
    prices, pages = prices_data["prices"], pages_data["pages"]
    shops = known_shops(prices, pages, lines_data)
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
        if plan.page is not None:
            try:
                ProductPage.model_validate(plan.page)
            except ValidationError as e:
                report.problems.append(f"{where} {finding.name}: a product page that wouldn't load, not added "
                                       f"({_problems(e)})")
                continue
            key = _page_key(plan.page)
            if key in seen_pages:
                report.already_there += 1
            else:
                pages.append(plan.page)
                seen_pages.add(key)
                report.added_pages += 1
    if write:
        _write(prices_path, prices_data)
        _write(pages_path, pages_data)
    return report


def _problems(error: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, err['loc'])) or 'entry'}: {err['msg'].removeprefix('Value error, ')}"
                     for err in error.errors())


def _price_key(entry: dict) -> tuple:
    return tuple(json.dumps(entry.get(k)) for k in ("product", "category", "product_type", "price", "currency", "shop",
                                                    "url", "checked_on", "available", "second_hand"))


def _page_key(entry: dict) -> tuple:
    return tuple(json.dumps(entry.get(k)) for k in ("product", "category", "product_type", "page", "shop", "image",
                                                    "image_page", "checked_on"))


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
    paths = [Path(a) for a in argv[1:] if a != "--write"]
    report = import_findings(paths, DEFAULT_PRICES, DEFAULT_PRODUCT_PAGES, write=write)
    print("Findings: " + ", ".join(f"{report.statuses[s]} {s}" for s in STATUSES))
    verb = "Added" if write else "Would add (run again with --write to add them)"
    print(f"{verb}: {report.added_prices} price-list entries, {report.added_pages} product pages; "
          f"{report.already_there} already there.")
    for heading, names in (("Unsure, nothing recorded", report.unsure), ("Refused, no source left", report.refused),
                           ("Sold second-hand only but not bought vintage on purpose, recorded as not sold",
                            report.not_vintage), ("Brand lines, recorded under their brand", report.lines),
                           ("Lines' prices not recorded as the line's own (a line's from price is data/brand_lines.json's)",
                            report.line_prices)):
        if names:
            print(f"{heading} ({len(names)}): {', '.join(names)}")
    if report.problems:
        print(f"Problems ({len(report.problems)}):")
        for problem in report.problems:
            print(f"  {problem}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
