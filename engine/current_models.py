"""The current model of a tech product whose reviewed model a newer one has replaced (Noemi's decision 3 of 26 Oct 2026,
second part: "the current tech models named where an owner-reviewed line continues").

Why: laptops, phones, headphones and the like are replaced every year or two (config.FAST_MOVING_TYPES), and writers
review the model they own. An answer can rightly pick the Sony XM4 because its owners praise it; a shopper should also
be told that the XM6 has replaced it. So a pick, or an "Also worth a look" item, of a fast-moving type whose reviewed
model a newer one of the same line has replaced shows "Current model: Sony WH-1000XM6 (2025)", with the page it was read
on and the day (engine/answer.py, ShownCurrentModel). Nothing is shown when the reviewed model is current, when it is
a model we know nothing of, or when we couldn't check: a missing line is never a claim.

The list, data/current_models.json, is filled by looking each product up on its maker's own page (a big UK shop's page
when the maker's refuses automated reads: a page that refuses is never got around, and the entry is left out when no
shop's page says it either), only for the tech products the sweep's answers show. Pages aren't Reddit data, so the list
is committed with the code. Its format (the same as the other lists' in spirit: engine/brand_lines.py):

    {"current_models": [{"product_type": "headphones",     the kind of product, as module 1 writes it ("e-reader")
                         "category": "general",             always general: tech
                         "replaced": ["Sony XM4", ...],     the names an answer shows (a pick's or item's name, or the
                                                            model that titles it) for models the current one replaced,
                                                            as shown: matched word for word (case, punctuation and the
                                                            known short names aside), never by a likeness, since "XM4"
                                                            and "XM5" are one letter apart
                         "line": ["Kindle Paperwhite e-reader line"],
                                                            optional: the names an answer shows for the line itself,
                                                            whose writers reviewed whichever model was current when they
                                                            wrote; it counts as a replaced model only when more than
                                                            half of its credible voices wrote before the current model
                                                            came out (`released`), so before the day or month the page
                                                            gives, or before the year starts when it gives a year only
                         "current": "Sony WH-1000XM6",      the current model as its page names it, with its generation
                                                            or year when the page gives one: shown as written
                         "released": "2025-05",             when the page says it came out: YYYY, YYYY-MM or YYYY-MM-DD;
                                                            needed with "line", optional otherwise
                         "shop": "Sony",                    the maker's, or the big UK shop's, plain name, as shown:
                                                            "Sony page"
                         "maker": true,                     true: the maker's own page; false: a big UK shop's, because
                                                            the maker's page refused automated reads or lists nothing
                         "page": "https://...",             the page the current model was read on: https, never
                                                            Reddit's, never a search page
                         "checked_on": "2026-10-26",        the day it was read
                         "note": "..."}]}                   what the researcher found, for whoever checks the list:
                                                            never shown in an answer

A malformed entry, or a second entry naming a product already named by one for the same product type (two entries could
disagree), stops the request with the entry's number and the problem (CurrentModelsError), as the other lists do.
"""

import json
import re
from collections.abc import Iterable
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, StrictBool, ValidationError, model_validator

from engine.config import THREAD_CATEGORIES
from engine.links import is_direct_page, is_linkable
from engine.match_products import known_aliases, product_words
from engine.memo import FileMemo
from engine.models import Record

DEFAULT_CURRENT_MODELS = Path(__file__).resolve().parents[1] / "data" / "current_models.json"
_PRODUCT_TYPE = re.compile(r"[a-z0-9]+(?:[ -][a-z0-9]+)*")
_RELEASED = re.compile(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?")


class CurrentModelsError(Exception):
    pass


def _page(url: str) -> str:
    if not is_linkable(url):
        raise ValueError("a page must start with https:// and have no spaces, name or password in it, and never be "
                         "Reddit's")
    if not is_direct_page(url):
        raise ValueError("a page must be the model's own page or its maker's range page, never a search page")
    return url


def _released(value: str) -> str:
    """YYYY, YYYY-MM or YYYY-MM-DD, a real day."""
    found = _RELEASED.fullmatch(value)
    if found is None:
        raise ValueError('"released" must be YYYY, YYYY-MM or YYYY-MM-DD')
    year, month, day = (int(part) if part else None for part in found.groups())
    try:
        date(year, month or 1, day or 1)
    except ValueError as e:
        raise ValueError(f'"released" {value}: {e}') from e
    return value


class CurrentModel(Record):
    """One entry of the list: the current model of a line whose older models answers may show, as read on one page on one
    day."""

    product_type: str
    category: Literal[THREAD_CATEGORIES]
    replaced: list[Annotated[str, Field(min_length=1)]] = []
    line: list[Annotated[str, Field(min_length=1)]] = []
    current: str = Field(min_length=1)
    released: Annotated[str, AfterValidator(_released)] | None = None
    shop: str = Field(min_length=1)
    maker: StrictBool
    page: Annotated[str, AfterValidator(_page)]
    checked_on: date
    note: str | None = None

    @model_validator(mode="after")
    def _names_something(self) -> "CurrentModel":
        if not _PRODUCT_TYPE.fullmatch(self.product_type):
            raise ValueError(f'the product type "{self.product_type}" must be lowercase words, as module 1 writes them '
                             '("e-reader")')
        if self.category != "general":
            raise ValueError("current models are for tech, which is the general category")
        if not (self.replaced or self.line):
            raise ValueError('an entry names the models it replaced ("replaced"), or the line itself ("line")')
        if self.line and self.released is None:
            raise ValueError('a line is a replaced model only for writers from before the current model came out: '
                             '"line" needs "released"')
        current = tuple(product_words(self.current, known_aliases().get(self.category, {})))
        for name in self.replaced:
            if _words(name, self.category) == current:
                raise ValueError(f'"{name}" is the current model itself, not one it replaced')
        return self


def _words(name: str, category: str) -> tuple[str, ...]:
    return tuple(product_words(name, known_aliases().get(category, {})))


def released_from(entry: CurrentModel) -> date | None:
    """The first day the current model could have come out, from what its page says: the day, the month's first day, or
    the year's. A comment written before it was written about an older model. None without a `released`."""
    if entry.released is None:
        return None
    year, month, day = (int(part) if part else None for part in _RELEASED.fullmatch(entry.released).groups())
    return date(year, month or 1, day or 1)


# --- The list ---

def load_current_models(path: Path = DEFAULT_CURRENT_MODELS) -> list[CurrentModel]:
    """Every entry of the list (data/current_models.json by default). A missing or malformed file or entry, or two
    entries naming one product of one type, raises CurrentModelsError naming the entry and the problem. Read once and
    kept while the file is unchanged (engine.memo), as the other lists are: every caller gets the same list, which none
    may change."""
    return _LOADED.get(Path(path), _read)


_LOADED = FileMemo()


def _read(path: Path) -> list[CurrentModel]:
    try:
        entries = json.loads(Path(path).read_text(encoding="utf-8"))["current_models"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        raise CurrentModelsError(f"{path}: not a current models list ({e})") from e
    if not isinstance(entries, list):
        raise CurrentModelsError(f'{path}: "current_models" must be a list')
    loaded: list[CurrentModel] = []
    seen: dict[tuple, int] = {}  # (product type, the name's words) -> the entry's number
    for number, entry in enumerate(entries, start=1):
        try:
            model = CurrentModel.model_validate(entry)
        except ValidationError as e:
            problems = "; ".join(f"{'.'.join(map(str, err['loc'])) or 'entry'}: "
                                 f"{err['msg'].removeprefix('Value error, ')}" for err in e.errors())
            raise CurrentModelsError(f"{path}, entry {number}: {problems}") from e
        for name in [*model.replaced, *model.line]:
            key = (model.product_type, _words(name, model.category))
            if key in seen:
                raise CurrentModelsError(f'{path}, entry {number}: "{name}" ({model.product_type}) is named by entry '
                                         f"{seen[key]} already: keep one")
            seen[key] = number
        loaded.append(model)
    return loaded


# --- Finding a product's entry ---

def find_current_model(names: Iterable[str], category: str, product_type: str | None,
                       entries: Iterable[CurrentModel]) -> tuple[CurrentModel, str] | None:
    """(the entry, "replaced" or "line") for a product shown under one of `names`, or None. A name fits when its words
    (module 4's, with the category's known short names: case, punctuation and an "and" aside) are exactly an entry's name
    for the same product type: never a likeness, since one letter tells two models apart. The newest check first
    when several fit."""
    if not product_type:
        return None
    shown = {_words(name, category) for name in names} - {()}
    found = []
    for entry in entries:
        if entry.category != category or entry.product_type != product_type:
            continue
        for kind, listed in (("replaced", entry.replaced), ("line", entry.line)):
            if any(_words(name, category) in shown for name in listed):
                found.append((entry, kind))
                break
    if not found:
        return None
    return max(found, key=lambda hit: hit[0].checked_on)
