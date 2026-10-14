"""Brand lines (Noemi's note of 12 Oct 2026, from testing the demo): which brands sell which kinds of product, checked
on the makers' own pages, so a brand named on its own counts for a request only when the brand really sells that kind
of product.

Why: writers often name only a brand ("the L'Oréal one is amazing"). Such a name fits several products, so module 4
marks its group loose (engine/group_products.py) and its mentions can't count for any one product. Since decision 9
(9 Oct 2026) a brand or line name can still be ranked, as the brand's whole line ("Lodge cast iron skillet line"), when
its threads make the product clear (engine/pipeline.py: most of its mentions are in threads whose title names the
product, and one of the brand's own products named there is of that type). Those are clues from the threads. Noemi
asked for a check against the real world: does the brand actually sell that kind of product? If it does, the mention
counts, and if enough credible writers back it, the brand's line can be one of the top 3.

The list, data/brand_lines.json, is filled with real look-ups (by Claude or a researcher): the makers' own pages first
(their UK pages before others), or a big shop's pages, never Reddit. A fact a page doesn't give stays unrecorded. Brand
lines aren't Reddit data, so the list is committed with the code. Its format:

    {"brand_lines": [{"brand": "Nizoral",                the brand, or a line of it, as its maker writes it
                      "also_called": ["..."],             optional: other names writers use for it
                      "category": "haircare",             skincare, kitchen or haircare
                      "product_type": "shampoo",          the kind of product, in lowercase: one of module 1's product
                                                          types, or a type its open model names ("air fryer")
                      "sells": true,                      true: the brand sells that kind of product (anywhere:
                                                          whether UK shoppers can buy it is the price list's job,
                                                          data/prices.json); false: it doesn't, going by its whole
                                                          range on its own pages
                      "sources": ["https://..."],         the pages that say so: at least one, https only, never Reddit
                      "checked_on": "2026-10-12",         the day they were read
                      "range_page": "https://...",        optional (14 Oct 2026): the page answers link to, the maker's
                                                          page for its products of this type (its UK page where there
                                                          is one), or an official UK stockist's; one of the sources,
                                                          written exactly as there
                      "range_shop": "...",                optional, only with range_page: the stockist's name, as shown,
                                                          when the page isn't the maker's own
                      "from_price": 199.0,                optional: the cheapest UK price in pounds of the brand's
                                                          products of this type; under a budget below it the brand's
                                                          line is left out as over budget (12 Oct 2026)
                      "from_price_shop": "John Lewis",    with from_price, all three or none (14 Oct 2026): the shop's
                      "from_price_url": "https://...",    (or maker's) name as shown, the page the price was read on
                      "from_price_checked_on": "...",     (one of the sources) and the day; answers show the from price
                                                          only with them: "From £45 at John Lewis, checked 14 Oct 2026"
                      "note": "..."}]}                    what the researcher found, for whoever checks the list; never
                                                          shown in an answer
A malformed entry, or a second entry for the same brand, category and product type (two entries could disagree), stops
the request with the entry's number and the problem (BrandLinesError).

Range pages and from prices (Noemi's night decision 1, 14 Oct 2026, after asking why the knife answer showed no product
link: its three picks were brand lines, which have no single price): a brand-line pick, and a line under "Also worth a
look", links to its entry's range page ("Browse Victorinox's chef knives", engine/answer.py), and shows its from price
with the shop and the day. Both are for display and the budget check only: how picks are chosen doesn't change. The
link is the entry's own address, never one from a comment; it is checked again before it is shown (https, one of the
entry's sources) and on the page (rangeUrl in engine/templates/search.html).

How a brand or line name finds its entry (find_brand_line): an entry of the request's category and product type whose
brand, or one of its also_called names, is the name's words, alone or followed only by the product type's own words
("Nizoral" and "Nizoral shampoo" in a shampoo answer), with module 4's word rules: case, accents, punctuation and
spacing aside, and small spelling slips forgiven ("L'Oreal" is L'Oréal, "head and shoulders" is Head & Shoulders,
"Kitchen Aid" is KitchenAid, "Zojurushi" is Zojirushi). A line of the brand isn't the brand: "L'Oréal Elvive" needs an
entry of its own.

How the pipeline uses it (engine/pipeline.py, the brand-pick step), for a loose group in a request for type T:
- an entry saying its brand sells T: the group is ranked as the brand's line, even when its threads alone don't make
  the product clear; its mentions count, and the usual minimum-evidence rule decides whether it is a pick;
- an entry saying its brand doesn't sell T: the group is left out, even when its threads alone would have kept it, and
  listed with the reason (not_sold_reason: "Batiste doesn't sell shampoos": its whole range is dry shampoos);
- no entry: its threads decide, as before.
Whatever the list says, a name made of filler words only ("the one") names nothing, a group whose mentions the AI typed
as another kind of product is left out (the list says what the brand sells, the AI's type what its writer meant), brand
lines are never picks when the request has a hard requirement (decided 10 Oct 2026: a whole brand can't be checked;
since Noemi's decision 1 of 13 Oct 2026 they may still be listed under Skip these, when their credible warnings put them
there), and the price list still says whether UK shoppers can buy them.
"""

import json
import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, Field, StrictBool, StrictFloat, ValidationError, model_validator

from engine.config import BRAND_LINE_NOT_SOLD, THREAD_CATEGORIES
from engine.group_products import plural
from engine.match_products import comparable, known_aliases, product_words, written_alike
from engine.models import Record
from engine.prices import Price
from engine.query import PRODUCT_TYPES

DEFAULT_BRAND_LINES = Path(__file__).resolve().parents[1] / "data" / "brand_lines.json"

# Pages that can never be a source: Reddit is what the list checks, not where its facts come from.
_REDDIT_HOSTS = ("reddit.com", "redd.it")
# A kind of product as module 1 writes it: lowercase words, joined by single spaces or hyphens ("leave-in conditioner").
_PRODUCT_TYPE = re.compile(r"[a-z]+(?:[ -][a-z]+)*")


class BrandLinesError(Exception):
    pass


def _source_page(url: str) -> str:
    """A source page: starting "https://", with a web address, no spaces, name or password in it, and not Reddit's."""
    parts = urlsplit(url)
    unsafe = parts.username or parts.password or any(c.isspace() for c in url)
    if not url.startswith("https://") or not parts.hostname or unsafe:
        raise ValueError("a source link must start with https:// and have no spaces, name or password in it")
    if any(parts.hostname == host or parts.hostname.endswith("." + host) for host in _REDDIT_HOSTS):
        raise ValueError("a source must be a maker's or a shop's page, never Reddit's")
    return url


class BrandLine(Record):
    """One entry of the brand-lines list: whether a brand sells one kind of product, where that comes from and when it
    was checked."""

    brand: str = Field(min_length=1)  # the brand (or a line of it) as its maker writes it
    also_called: list[Annotated[str, Field(min_length=1)]] = []  # other names writers use for it
    category: Literal[THREAD_CATEGORIES]
    product_type: str  # the kind of product, in lowercase: module 1's type or one its open model names
    sells: StrictBool  # true: the brand sells that kind of product; false: it doesn't. JSON true/false only.
    sources: list[Annotated[str, AfterValidator(_source_page)]] = Field(min_length=1)
    checked_on: date
    # The page answers link to (14 Oct 2026): the maker's page for its products of this type, or an official UK
    # stockist's (then range_shop names it). One of the sources, exactly as written there. Optional.
    range_page: str | None = None
    range_shop: str | None = Field(default=None, min_length=1)
    # The cheapest UK price, in pounds, of the brand's products of this type (12 Oct 2026): under a budget below it the
    # brand's line is left out as over budget. From a UK shop's or the maker's UK page among the sources. Optional.
    from_price: StrictFloat | None = Field(default=None, gt=0)
    # Where and when it was found (14 Oct 2026): the shop's name as shown, the page (one of the sources) and the day.
    # All three with a from price, or none; answers show a from price only with them.
    from_price_shop: str | None = Field(default=None, min_length=1)
    from_price_url: str | None = None
    from_price_checked_on: date | None = None
    note: str | None = None  # what the researcher found, for whoever checks the list: never shown in an answer

    @model_validator(mode="after")
    def _names_a_brand_and_a_kind_of_product(self) -> "BrandLine":
        if not product_words(self.brand):
            raise ValueError(f'"{self.brand}" names no brand: its words are all filler words')
        if not _PRODUCT_TYPE.fullmatch(self.product_type):
            raise ValueError(f'the product type "{self.product_type}" must be lowercase words, as module 1 writes '
                             'them ("cast iron skillet", "air fryer")')
        known = next((p for p in PRODUCT_TYPES if p.name == self.product_type), None)
        if known is not None and known.category != self.category:
            raise ValueError(f"a {self.product_type} is a {known.category} product, not {self.category}")
        return self

    @model_validator(mode="after")
    def _links_only_to_pages_read(self) -> "BrandLine":
        if self.range_page is not None and self.range_page not in self.sources:
            raise ValueError("the range page must be one of the sources, written exactly as there")
        if self.range_shop is not None and self.range_page is None:
            raise ValueError("a range shop names whose range page it is: it needs the range page")
        found = (self.from_price_shop, self.from_price_url, self.from_price_checked_on)
        if any(part is not None for part in found):
            if self.from_price is None or any(part is None for part in found):
                raise ValueError("a from price's shop, page and day come together, with the from price")
            if self.from_price_url not in self.sources:
                raise ValueError("the page a from price was read on must be one of the sources")
        return self


# --- The list ---

def load_brand_lines(path: Path = DEFAULT_BRAND_LINES) -> list[BrandLine]:
    """Every entry of the brand-lines list (data/brand_lines.json by default). A malformed file or entry, or a second
    entry for the same brand, category and product type, raises BrandLinesError naming the entry and the problem."""
    try:
        entries = json.loads(Path(path).read_text(encoding="utf-8"))["brand_lines"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        raise BrandLinesError(f"{path}: not a brand-lines list ({e})") from e
    if not isinstance(entries, list):
        raise BrandLinesError(f'{path}: "brand_lines" must be a list')
    loaded: list[BrandLine] = []
    seen: dict[tuple, int] = {}  # (the brand's words, category, product type) -> the entry's number
    for number, entry in enumerate(entries, start=1):
        try:
            line = BrandLine.model_validate(entry)
        except ValidationError as e:
            problems = "; ".join(f"{'.'.join(map(str, err['loc'])) or 'entry'}: {_plain(err['msg'])}"
                                 for err in e.errors())
            raise BrandLinesError(f"{path}, entry {number}: {problems}") from e
        aliases = known_aliases().get(line.category, {})
        key = (tuple(product_words(line.brand, aliases)), line.category, line.product_type)
        if key in seen:
            raise BrandLinesError(f"{path}, entry {number}: {line.brand} ({line.category}, {line.product_type}) has an "
                                  f"entry already, entry {seen[key]}: keep one")
        seen[key] = number
        loaded.append(line)
    return loaded


def _plain(message: str) -> str:
    """Pydantic's message without its "Value error, " label."""
    return message.removeprefix("Value error, ")


# --- One brand's entry ---

def find_brand_line(names: Iterable[str], category: str, product_type: str | None,
                    lines: Iterable[BrandLine], of_a_product: bool = False) -> BrandLine | None:
    """The entry for a brand or line name in a request for `product_type`, or None when the list has none.

    `names` are the names writers used for it (a loose group's names, and their UK names). An entry fits when its brand,
    or one of its also_called names, is one of those names' words (module 4's word rules, with the category's known
    short names: case, accents, spacing and an "and" aside, spelling slips forgiven), alone or followed only by the
    product type's own words ("Nizoral shampoo" for a shampoo request). When several fit: the one whose brand has the
    most words (a line with an entry of its own before its brand), then the newest check, then the brand's name.
    `of_a_product` (13 Oct 2026): the entry of the brand a specific product's names start with, whatever words follow
    ("Comandante with Red Clix"), for its from price.
    """
    if not product_type:
        return None
    aliases = known_aliases().get(category, {})
    type_words = {word for words in (product_type, plural(product_type)) for word in product_words(words, aliases)}
    written = [words for words in {tuple(product_words(name, aliases)) for name in names} if words]

    def fits(line: BrandLine) -> bool:
        for brand in [line.brand, *line.also_called]:
            for words in written:
                name, brand_words = comparable(list(words), product_words(brand, aliases))
                if (brand_words and written_alike(name[:len(brand_words)], brand_words)
                        and (of_a_product or set(name[len(brand_words):]) <= type_words)):
                    return True
        return False

    found = [line for line in lines if line.category == category and line.product_type == product_type and fits(line)]
    if not found:
        return None
    return min(found, key=lambda line: (-len(product_words(line.brand, aliases)), -line.checked_on.toordinal(),
                                        line.brand.casefold()))


def not_sold_reason(line: BrandLine) -> str:
    """Why a brand or line name is left out when the list says its brand doesn't sell the kind of product asked for,
    in words (config.BRAND_LINE_NOT_SOLD): "Batiste doesn't sell shampoos"."""
    return BRAND_LINE_NOT_SOLD.format(brand=line.brand, products=plural(line.product_type))


# --- Range pages and from prices (Noemi's night decision 1, 14 Oct 2026) ---

def is_source_page(url: str) -> bool:
    """Whether a page may be a source of the list, and so be linked to: https, with a web address, no spaces, name or
    password in it, and never Reddit's (_source_page). Answers check a range page with it again before showing it."""
    try:
        _source_page(url)
    except ValueError:
        return False
    return True


def from_price_entry(line: BrandLine | None, name: str) -> Price | None:
    """A brand line's from price as a price-list entry under the line's name, for the budget check and its price line:
    the cheapest UK price of the brand's products of the type, the shop and the page it was read on, the day, and that
    the shop sells it (the researcher found it on sale there). None without an entry that sells the type, a from price,
    or where and when it was found: such a from price is never shown, and only leaves the line out under a budget
    below it (engine.pipeline._within_budget)."""
    if line is None or not line.sells or line.from_price is None or line.from_price_shop is None:
        return None
    return Price(product=name, category=line.category, price=line.from_price, currency="GBP", shop=line.from_price_shop,
                 url=line.from_price_url, checked_on=line.from_price_checked_on, available=True,
                 product_type=line.product_type)
