"""Products' own pages and their makers' images (Noemi's decisions 2 and 3 of 15 Oct 2026, late afternoon).

From the live laptop answer ("also why none have the links to the products? or could we add a little image of the prod
with the link?"): each pick, and each "Also worth a look" item, may link to its own product page, its maker's or a big
UK shop's, and show a small image from its maker's own product page, linked to that page. Direct links only: no search
links, so a product not researched yet shows no link, as before. Links and images come from this list only, never from a
comment, and are checked again before they are shown (engine.links) and on the page.

The list, data/product_pages.json, is filled by `python -m engine.buyable import` from researchers' findings (a page is
written only for a product found on sale in the UK); pages aren't Reddit data, so the list is committed with the code.
Its format:

    {"pages": [{"product": "Apple MacBook Air 13-inch (M4)",   the product's name as the answer shows it
                "also_called": ["..."],                         optional: other names the same product goes by
                "category": "general",                          skincare, kitchen, haircare or general
                "product_type": "laptop",                       optional: the product type it is about; it then never
                                                                links a product of another type (as in the price list)
                "page": "https://www.apple.com/uk/macbook-air/",    its own page: its maker's UK page where there is
                                                                one, else a big UK shop's; never a search
                "shop": "Apple",                                the maker's or shop's plain name, as shown
                "image": "https://www.apple.com/...hero.jpg",   optional: the main image on its maker's own page
                "image_page": "https://www.apple.com/uk/...",   with an image: the maker's page it is on
                "sources": ["https://..."],                     the pages read, the page and image_page among them
                "checked_on": "2026-10-15",                     the day they were read
                "note": "..."}]}                                optional: what the researcher found; never shown

Every address is https, with no name or password, never Reddit's (engine.links.is_linkable), and the page is never a
search (engine.links.is_direct_page). A malformed entry stops the request with its number and the problem
(ProductPagesError), as the price list's do.

How a product finds its page (find_page): an entry of the same category (and type, when the entry names one) whose name
means the same product, by module 4's rules (engine.match_products.same_product, with the category's known short names),
tried with each of the product's names in turn, the name the answer shows first; among the entries one name finds,
the one with the same words (but for spelling slips) first, then the newest check.

The images' hosts are the only ones the page's security policy lets images in from (image_sources; engine/web.py).
"""

import json
import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, Field, ValidationError, model_validator

from engine.config import THREAD_CATEGORIES
from engine.links import is_direct_page, is_linkable
from engine.match_products import known_aliases, product_words, same_product, written_alike
from engine.memo import FileMemo, PerList
from engine.models import Record
from engine.name_index import NameIndex

DEFAULT_PRODUCT_PAGES = Path(__file__).resolve().parents[1] / "data" / "product_pages.json"
# A kind of product as module 1 writes it: lowercase words, joined by single spaces or hyphens ("e-reader").
_PRODUCT_TYPE = re.compile(r"[a-z0-9]+(?:[ -][a-z0-9]+)*")


class ProductPagesError(Exception):
    pass


def _address(url: str) -> str:
    if not is_linkable(url):
        raise ValueError("an address must start with https:// and have no spaces, name or password in it, and never "
                         "be Reddit's")
    return url


def _direct(url: str) -> str:
    _address(url)
    if not is_direct_page(url):
        raise ValueError("a product's page must be its own page, never a search: direct links only")
    return url


def _product_type(value: str | None) -> str | None:
    if value is not None and not _PRODUCT_TYPE.fullmatch(value):
        raise ValueError(f'the product type "{value}" must be lowercase words, as module 1 writes them ("laptop")')
    return value


class ProductPage(Record):
    """One entry of the list: a product's own page, and maybe its maker's image, as researched on one day."""

    product: str = Field(min_length=1)  # the name as the answer shows it
    also_called: list[Annotated[str, Field(min_length=1)]] = []
    category: Literal[THREAD_CATEGORIES]
    product_type: Annotated[str | None, AfterValidator(_product_type)] = None
    page: Annotated[str, AfterValidator(_direct)]
    shop: str = Field(min_length=1)  # the maker's or shop's plain name, as shown
    image: Annotated[str | None, AfterValidator(lambda url: url if url is None else _address(url))] = None
    image_page: Annotated[str | None, AfterValidator(lambda url: url if url is None else _address(url))] = None
    sources: list[Annotated[str, AfterValidator(_address)]] = Field(min_length=1)
    checked_on: date
    note: str | None = None  # what the researcher found: never shown

    @model_validator(mode="after")
    def _only_pages_read(self) -> "ProductPage":
        if self.page not in self.sources:
            raise ValueError("the page must be one of the sources, written exactly as there")
        if (self.image is None) != (self.image_page is None):
            raise ValueError("an image and the image_page it is on come together: an image is from its maker's page")
        if self.image_page is not None and self.image_page not in self.sources:
            raise ValueError("the image_page must be one of the sources, written exactly as there")
        return self


# --- The list ---

def load_product_pages(path: Path = DEFAULT_PRODUCT_PAGES) -> list[ProductPage]:
    """Every entry of the list (data/product_pages.json by default). A missing or malformed file or entry raises
    ProductPagesError naming the entry and the problem. Read once and kept while the file is unchanged (engine.memo), as
    the price list is: every caller gets the same list, which none may change."""
    return _LOADED.get(Path(path), _read)


_LOADED = FileMemo()
_FOUND = PerList()


def _read(path: Path) -> list[ProductPage]:
    try:
        entries = json.loads(Path(path).read_text(encoding="utf-8"))["pages"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        raise ProductPagesError(f"{path}: not a product pages list ({e})") from e
    if not isinstance(entries, list):
        raise ProductPagesError(f'{path}: "pages" must be a list')
    loaded = []
    for number, entry in enumerate(entries, start=1):
        try:
            loaded.append(ProductPage.model_validate(entry))
        except ValidationError as e:
            problems = "; ".join(f"{'.'.join(map(str, err['loc'])) or 'entry'}: "
                                 f"{err['msg'].removeprefix('Value error, ')}" for err in e.errors())
            raise ProductPagesError(f"{path}, entry {number}: {problems}") from e
    return loaded


# --- One product's page ---

def find_page(names: Iterable[str], category: str, product_type: str | None,
              pages: Iterable[ProductPage]) -> ProductPage | None:
    """The page of the product known by `names` (the name the answer shows first), or None when the list has none."""
    for name in dict.fromkeys(n for n in names if n):
        found = _find(name, category, product_type, pages)
        if found is not None:
            return found
    return None


def _find(name: str, category: str, product_type: str | None, pages: Iterable[ProductPage]) -> ProductPage | None:
    table = _FOUND.of(pages)
    key = (name, category, product_type)
    if table is not None and key in table:
        return table[key]
    aliases = known_aliases().get(category, {})
    fits = [p for p in _could_match(name, category, pages, aliases)
            if (p.product_type is None or product_type is None or p.product_type == product_type)
            and any(same_product(known, name, aliases) for known in [p.product, *p.also_called])]
    words = product_words(name, aliases)
    found = min(fits, key=lambda p: (not written_alike(product_words(p.product, aliases), words),
                                     -p.checked_on.toordinal(), p.product.casefold())) if fits else None
    if table is not None:
        table[key] = found
    return found


def _could_match(name: str, category: str, pages: Iterable[ProductPage], aliases) -> list[ProductPage]:
    """The category's entries that could be the same product as `name`, as the price list finds its own
    (engine.name_index; engine.prices._could_match)."""
    table = _INDEXES.of(pages)
    if table is None:
        return [p for p in pages if p.category == category]
    found = table.get(category)
    if found is None:
        of_category = [p for p in pages if p.category == category]
        found = table[category] = (of_category, NameIndex([[p.product, *p.also_called] for p in of_category], aliases))
    of_category, index = found
    return [of_category[i] for i in index.candidates(name)]


_INDEXES = PerList()


def image_sources(pages: Iterable[ProductPage]) -> tuple[str, ...]:
    """The origins ("https://images.maker.example") the list's images are on, each once, in order: the only places the
    page may load images from (engine/web.py's security policy)."""
    return tuple(sorted({f"https://{urlsplit(p.image).hostname.lower()}" for p in pages
                         if p.image is not None and is_linkable(p.image)}))
