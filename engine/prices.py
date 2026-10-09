"""Budgets (Noemi's decision 11, 9 Oct 2026): a list of current prices, each with its shop and the day it was checked.

Reddit threads rarely give a current price, so prices come from a separate list, data/prices.json, which Claude fills
with real look-ups: for each blind-test question's shortlist, the price on a shop's own page for the product, the
shop's name and the day it was checked. Prices aren't Reddit data, so the list is committed with the code. Its format:

    {"prices": [{"product": "Zojirushi kettle",       the product's name as the answer shows it
                 "category": "kitchen",               skincare or kitchen
                 "price": 120.0,                      what it costs there
                 "currency": "GBP",                   GBP, EUR or USD: the currencies a request can name
                 "shop": "John Lewis",                the shop's name
                 "url": "https://...",                the product's page at that shop: https only
                 "checked_on": "2026-10-09"}]}        the day the price was looked up

A malformed entry stops the request with its number and the problem (PriceError), rather than being skipped.

How a product finds its price (find_price): an entry of the same category whose name means the same product, by
module 4's rules (engine.match_products.same_product, with the category's known short names, so "Sage" finds
"Breville"). When several fit: the one with exactly the same words first, then one in the request's currency, then
the most recently checked, then the cheapest.

How a price meets the request's budget (check_price). Only a budget with a max and a currency is checked: module 1
never guesses a currency, and nothing converts one currency into another.
    within          a known price, in the budget's currency, checked within PRICE_MAX_AGE_DAYS, at or under the max
    over            the same, but above the max: the pipeline leaves the product out and lists it
    unknown         no price in the list: kept, and the answer says the price isn't checked yet
    other currency  the price is in another currency: kept, and the answer says it wasn't compared
    out of date     checked more than PRICE_MAX_AGE_DAYS ago: still shown with its date, but never used to leave a
                    product out, since it may have changed (PROPOSED)
    no budget       the request has no budget that can be checked
A budget's min is never used to leave a product out: a product cheaper than the shopper expected is still an answer.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, Field, ValidationError

from engine.config import PRICE_MAX_AGE_DAYS, THREAD_CATEGORIES
from engine.match_products import known_aliases, product_words, same_product
from engine.models import Record
from engine.query import Budget

DEFAULT_PRICES = Path(__file__).resolve().parents[1] / "data" / "prices.json"

PriceStatus = Literal["within", "over", "unknown", "other currency", "out of date", "no budget"]


class PriceError(Exception):
    pass


def _shop_page(url: str) -> str:
    """A shop's page: starting "https://", with a web address, and no spaces, name or password in it."""
    parts = urlsplit(url)
    unsafe = parts.username or parts.password or any(c.isspace() for c in url)
    if not url.startswith("https://") or not parts.hostname or unsafe:
        raise ValueError("a shop link must start with https:// and have no spaces, name or password in it")
    return url


class Price(Record):
    """One line of the price list: what one product cost at one shop, on the day it was checked."""

    product: str = Field(min_length=1)  # the name as the answer shows it
    category: Literal[THREAD_CATEGORIES]
    price: float = Field(gt=0)
    currency: Literal["GBP", "EUR", "USD"]  # the currencies a request can name (engine.query.Budget)
    shop: str = Field(min_length=1)
    url: Annotated[str, AfterValidator(_shop_page)]  # the product's page at that shop
    checked_on: date


@dataclass(frozen=True)
class PriceCheck:
    """What is known about one product's price for one request, and how it compares with the request's budget."""

    price: Price | None  # None when the list has no price for it
    status: PriceStatus
    budget: Budget | None = None  # the request's budget, when it has one that can be checked


# --- The list ---

def load_prices(path: Path = DEFAULT_PRICES) -> list[Price]:
    """Every price in the list (data/prices.json by default). A malformed file or entry raises PriceError."""
    try:
        entries = json.loads(Path(path).read_text(encoding="utf-8"))["prices"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        raise PriceError(f"{path}: not a price list ({e})") from e
    if not isinstance(entries, list):
        raise PriceError(f"{path}: \"prices\" must be a list")
    prices = []
    for number, entry in enumerate(entries, start=1):
        try:
            prices.append(Price.model_validate(entry))
        except ValidationError as e:
            problems = "; ".join(f"{'.'.join(map(str, err['loc'])) or 'entry'}: {err['msg']}" for err in e.errors())
            raise PriceError(f"{path}, entry {number}: {problems}") from e
    return prices


# --- One product's price ---

def find_price(name: str, category: str, prices: Iterable[Price], currency: str | None = None) -> Price | None:
    """The price of the product called `name`, or None when the list has none.

    `currency` is the request's, when it has a budget: a price in it is preferred to one in another currency.
    """
    aliases = known_aliases().get(category, {})
    fits = [p for p in prices if p.category == category and same_product(p.product, name, aliases)]
    if not fits:
        return None
    words = product_words(name, aliases)

    def preference(p: Price) -> tuple:
        exact = product_words(p.product, aliases) == words
        return not exact, p.currency != currency, -p.checked_on.toordinal(), p.price, p.shop.casefold()

    return min(fits, key=preference)


def check_price(price: Price | None, budget: Budget | None, today: date) -> PriceCheck:
    """How a product's price (None when unknown) compares with the request's budget, on `today`."""
    if budget is None or budget.max is None or budget.currency is None:
        return PriceCheck(price, "no budget")
    if price is None:
        status = "unknown"
    elif price.currency != budget.currency:
        status = "other currency"
    elif (today - price.checked_on).days > PRICE_MAX_AGE_DAYS:
        status = "out of date"
    elif price.price > budget.max:
        status = "over"
    else:
        status = "within"
    return PriceCheck(price, status, budget)
