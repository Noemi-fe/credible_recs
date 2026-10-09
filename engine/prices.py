"""Budgets (Noemi's decision 11, 9 Oct 2026) and availability: a list of current prices, and of whether each product
is still sold, each with its shop and the day it was checked.

Reddit threads rarely give a current price, so prices come from a separate list, data/prices.json, which Claude fills
with real look-ups: for each blind-test question's shortlist, the price on a shop's own page for the product, the
shop's name and the day it was checked. Since 9 Oct 2026 (Noemi's note: "are we making sure the products we recommend
exist?") an entry can also say whether the product is still sold. Prices aren't Reddit data, so the list is committed
with the code. Its format:

    {"prices": [{"product": "Zojirushi kettle",       the product's name as the answer shows it
                 "category": "kitchen",               skincare or kitchen
                 "price": 120.0,                      what it costs there; null when only availability was checked
                 "currency": "GBP",                   GBP, EUR or USD: the currencies a request can name (the shop's
                                                      currency, even when the price is null)
                 "shop": "John Lewis",                the shop's name
                 "url": "https://...",                the product's page at that shop: https only
                 "checked_on": "2026-10-09",          the day the price (or availability) was looked up
                 "available": true}]}                 optional: true when the shop sells it (out of stock for now
                                                      still counts), false when it is no longer sold (discontinued,
                                                      or no shop checked sells it); left out when not checked

An entry must give a price, or say whether the product is available, or both. A malformed entry stops the request with
its number and the problem (PriceError), rather than being skipped.

How a product finds its price (find_price): an entry with a price, of the same category, whose name means the same
product, by module 4's rules (engine.match_products.same_product, with the category's known short names, so "Sage"
finds "Breville"). When several fit: the one with exactly the same words first, then one in the request's currency,
then the most recently checked, then the cheapest.

How a product finds whether it is sold (find_availability): among the entries that say, the same way, the one with
exactly the same words first, then the newest check; on the same day, one shop selling it is enough. The pipeline
leaves out a product whose answer is "no longer sold" (engine.pipeline, the budget step), whatever its price and
however old the check: unlike a price, a product that stopped being sold rarely comes back, and an answer should never
recommend it. A product with no availability check is kept, and its answer says so.

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

What is still to look up (`todo`): the picks of the blind-test answers with no entry yet, or whose entries still lack
a price or an availability check, so Claude can look them up on shop pages.

Command line:
    python -m engine.prices todo     the blind-test picks still to look up (names and product types only), from the
                                     answers on data/library without live checks
"""

import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, Field, StrictBool, ValidationError, model_validator

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
    """One line of the price list: what one product cost at one shop, and whether it is still sold, on the day it was
    checked."""

    product: str = Field(min_length=1)  # the name as the answer shows it
    category: Literal[THREAD_CATEGORIES]
    price: float | None = Field(gt=0)  # None ("price": null) when only its availability was checked
    currency: Literal["GBP", "EUR", "USD"]  # the currencies a request can name (engine.query.Budget)
    shop: str = Field(min_length=1)
    url: Annotated[str, AfterValidator(_shop_page)]  # the product's page at that shop
    checked_on: date
    # True: the shop sells it; False: no longer sold; None (left out of the entry): not checked. JSON true/false only.
    available: StrictBool | None = None

    @model_validator(mode="after")
    def _says_something(self) -> "Price":
        if self.price is None and self.available is None:
            raise ValueError('an entry needs a price, or "available": true or false (or both)')
        return self


@dataclass(frozen=True)
class PriceCheck:
    """What is known about one product's price for one request, and how it compares with the request's budget."""

    price: Price | None  # None when the list has no price for it
    status: PriceStatus
    budget: Budget | None = None  # the request's budget, when it has one that can be checked
    availability: Price | None = None  # the entry that says whether it is sold (find_availability); None: not checked


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

    `currency` is the request's, when it has a budget: a price in it is preferred to one in another currency. An entry
    with no price (only its availability was checked) is never a price.
    """
    aliases = known_aliases().get(category, {})
    fits = [p for p in entries_for(name, category, prices) if p.price is not None]
    if not fits:
        return None
    words = product_words(name, aliases)

    def preference(p: Price) -> tuple:
        exact = product_words(p.product, aliases) == words
        return not exact, p.currency != currency, -p.checked_on.toordinal(), p.price, p.shop.casefold()

    return min(fits, key=preference)


def find_availability(name: str, category: str, prices: Iterable[Price]) -> Price | None:
    """The entry that says whether the product called `name` is still sold, or None when no entry says.

    Among the entries that say (available true or false): the one with exactly the same words first, then the newest
    check (a product sold in January but no longer in October is no longer sold); on the same day, one that says it is
    sold, since one shop selling it is enough; then the shop's name, so the choice is always the same.
    """
    aliases = known_aliases().get(category, {})
    fits = [p for p in entries_for(name, category, prices) if p.available is not None]
    if not fits:
        return None
    words = product_words(name, aliases)

    def preference(p: Price) -> tuple:
        exact = product_words(p.product, aliases) == words
        return not exact, -p.checked_on.toordinal(), not p.available, p.shop.casefold()

    return min(fits, key=preference)


def entries_for(name: str, category: str, prices: Iterable[Price]) -> list[Price]:
    """Every entry of the same category whose name means the same product as `name`, by module 4's rules."""
    aliases = known_aliases().get(category, {})
    return [p for p in prices if p.category == category and same_product(p.product, name, aliases)]


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


# --- What is still to look up: python -m engine.prices todo ---

MISSING_WORDS = {"entry": "no entry yet", "price": "no price yet", "availability": "availability not checked yet"}


def missing(name: str, category: str, prices: Iterable[Price]) -> list[str]:
    """What the list still lacks for one product: ["entry"] when it has no entry for it; otherwise "price" when none of
    its entries has a price, and "availability" when none says whether it is sold. [] when nothing is missing."""
    entries = entries_for(name, category, prices)
    if not entries:
        return ["entry"]
    return ([] if any(p.price is not None for p in entries) else ["price"]) + (
        [] if any(p.available is not None for p in entries) else ["availability"])


@dataclass
class PickToCheck:
    name: str  # the pick's name, as the answer shows it
    missing: list[str]  # "entry", or "price" and/or "availability"


@dataclass
class QuestionToCheck:
    id: str  # the blind-test question's id, "b06"
    product_type: str | None  # module 1's product type; None when it couldn't place the question
    category: str | None
    picks: int  # how many picks its answer shows
    to_check: list[PickToCheck] = field(default_factory=list)  # in the answer's order
    brand_picks: list[str] = field(default_factory=list)  # picks that are brands (decision 9): never priced or checked


def todo(questions_path: Path | None = None, library_dir: Path | None = None, prices: list[Price] | None = None,
         profiles=None) -> list[QuestionToCheck]:
    """For each blind-test question, its picks that still need a look-up: no entry yet, or entries still missing a price
    or an availability check.

    Each question runs through engine.pipeline.answer_request on the library (`library_dir`, None: data/library) with
    the price list (`prices`, None: data/prices.json), and without live checks: no quote is read on Reddit (so it is
    fast and never touches the network), and threads still waiting for their live check count too, as in
    engine.slice_eval.threads_behind_answers. So these are the picks answers will show once every thread is checked.
    A product the list already says is no longer sold isn't a pick, so it isn't listed. A brand pick (decision 9) has no
    single product, so it is never priced or checked: it is named apart (brand_picks). `profiles`: as in
    engine.pipeline.
    """
    from engine.library import DEFAULT_LIBRARY_DIR  # imported here: the pipeline imports this module
    from engine.pipeline import answer_request
    from engine.slice_eval import DEFAULT_QUESTIONS

    prices = load_prices() if prices is None else prices
    questions = json.loads(Path(questions_path or DEFAULT_QUESTIONS).read_text(encoding="utf-8"))["questions"]
    results = []
    for question in questions:
        run = answer_request(question["text"], library_dir=library_dir or DEFAULT_LIBRARY_DIR, profiles=profiles,
                             prices=prices, live_check_required=False)
        picks = run.answer.picks if run.answer is not None else []
        result = QuestionToCheck(question["id"], run.query.product_type, run.query.category, len(picks))
        for pick in picks:
            if pick.name in run.not_priced:
                result.brand_picks.append(pick.name)
            elif lacking := missing(pick.name, run.query.category, prices):
                result.to_check.append(PickToCheck(pick.name, lacking))
        results.append(result)
    return results


def main(argv: list[str], questions_path: Path | None = None, library_dir: Path | None = None,
         prices: list[Price] | None = None) -> int:
    """`questions_path`, `library_dir` and `prices` can be swapped for made-up ones, which is how the tests run it.
    It prints names and product types only: never a quote."""
    if argv != ["todo"]:
        print(__doc__)
        return 2
    from engine.extract import ExtractionError  # imported here: the pipeline imports this module
    from engine.gold import GoldSetError
    from engine.pipeline import cached_profiles

    try:
        results = todo(questions_path, library_dir, prices, profiles=cached_profiles())
    except (PriceError, GoldSetError, ExtractionError) as e:  # a broken price list, or no library (or a broken one)
        print(e)
        return 1
    print("Blind-test picks still to look up for data/prices.json (answers from the library, without live checks):")
    for question in results:
        if not question.picks:
            print(f"  {question.id}: no picks")
            continue
        heading = f"  {question.id} {question.product_type} ({question.category})"
        if not question.to_check and not question.brand_picks:
            print(f"{heading}: every pick has a price and an availability check")
            continue
        print(heading)
        for pick in question.to_check:
            print(f"    {pick.name}: {'; '.join(MISSING_WORDS[m] for m in pick.missing)}")
        for name in question.brand_picks:
            print(f"    {name}: a brand pick, never priced or checked")
    picks = [pick for question in results for pick in question.to_check]
    no_entry = sum(pick.missing == ["entry"] for pick in picks)
    print(f"{len(picks)} pick{'' if len(picks) == 1 else 's'} to look up: {no_entry} with no entry yet, "
          f"{len(picks) - no_entry} with an entry still missing a price or an availability check.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
