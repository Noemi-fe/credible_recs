"""Product facts (decided by Claude, 9 Oct 2026, as Noemi asked): a few checked facts about each product, so a pick
suits what the request asks for.

Why: the ranking reads only what Reddit says, so it ignored what a request asks for. "retinol for a beginner with
sensitive skin" picked Tazorac, a strong prescription retinoid. Word rules on comments made it worse (engine/needs.py:
comments rarely say "too strong for beginners"). What was missing is product knowledge: a few facts about each product,
looked up online with a source, and matched against the request.

The list, data/product_facts.json, is filled with real look-ups (by Claude or a researcher): for each product, a few
facts from a small vocabulary, the pages they come from and the day they were checked. Facts aren't Reddit data, so the
list is committed with the code. Its format:

    {"facts": [{"product": "Galderma Differin Gel",    the product's full name, brand first
                "category": "skincare",                 skincare or kitchen
                "product_type": "retinoid",             one of module 1's product types (engine.query.PRODUCT_TYPES)
                "facts": {"strength": "gentle",         facts from the vocabulary below, at least one; a fact that
                          "prescription_only": false},  isn't known is left out (never null)
                "sources": ["https://..."],             the pages the facts come from: at least one, https only
                "checked_on": "2026-10-09"}]}           the day they were looked up

The vocabulary (engine/config.py, "Product facts"): PRODUCT_FACT_VALUES lists every fact and the values it can take,
PRODUCT_FACTS_BY_TYPE which facts each product type can have. In short:
    every skincare product  fragrance_free: true/false, prescription_only: true/false
    retinoid, exfoliant     strength: "gentle" | "moderate" | "strong"
    sunscreen               white_cast: true/false, finish: "matte" | "natural" | "dewy",
                            filters: "mineral" | "chemical" | "hybrid"
    moisturiser, cleanser   texture: "light" | "rich"
    kettles                 plastic_free_inside: true/false
    frying pan, saucepan    pfas_free: true/false, non_stick: true/false, induction: true/false
Whether a product is still sold isn't a fact here: the price list says it (engine/prices.py), so it isn't kept twice.
A malformed entry, an unknown fact (a typo such as "fragance_free" would otherwise silently drop the fact) or a value
outside the vocabulary stops the request with the entry's number and the problem (ProductFactsError).

How a product finds its facts (find_facts), as a product finds its price (engine.prices): an entry of the same
category whose name means the same product, by module 4's rules (engine.match_products.same_product, with the
category's known short names, so "Sage" finds "Breville"). When several fit: the one with the same words (but for
spelling slips, 10 Oct 2026) first, then one of the requested product type, then the most recently checked. A brand
pick ("Lodge (their cast iron skillets)") is no single product, so its facts are never looked up. So when the request has a hard requirement its
product type can have (hard_requirements: "non-stick frying pan without PFAS"), brand picks are left out and listed with
the reason uncheckable_brand_reason gives ("a whole brand can't be checked for PFAS or a non-stick coating"; decided by
Claude, 10 Oct 2026, as Noemi asked): a brand's other pans may well be PTFE-coated. A requirement its type can't have
("first chef's knife" asks for a beginner's strength, but a chef knife has no strength) leaves brand picks in.

How facts meet a request (conflicts). The rules are config.PRODUCT_FACT_RULES, one table: when the request asks for one
of a rule's "asks", a product whose fact has the rule's value doesn't suit it. What a request asks for (request_asks):
    - module 1's skin types and must-haves ("sensitive", "fragrance-free", "plastic-free", "induction-compatible");
    - the needs engine/needs.py finds by their words, apart from must-haves ("new to retinol" asks for "beginner",
      "gentle"). Must-haves come from module 1 only, whose patterns are stricter: "a nice scent" doesn't ask for
      fragrance-free, though "scent" is one of the need's words for comments;
    - config.PRODUCT_FACT_REQUEST_WORDS: "doesn't leave a white cast" asks for no white cast, "without PFAS" for
      PFAS-free, "non-stick" for non-stick (but not "not non-stick").
Each rule is hard or soft (its "hard" switch in config): a hard clash leaves the product out, listed on the pipeline's
result with the reason (left_out_not_suited); a soft one keeps it and shows the reason under its pick as a caution
("Note: ..."; engine/answer.py). Today one rule is soft: a rich moisturiser or cleanser for oily or acne-prone skin.
A fact that isn't known never counts against a product: a product with no entry, or whose entry doesn't say, is kept.

What is still to look up (todo): for each blind-test question, its top candidates (its picks, then the products that
qualify or nearly qualify, in the ranking's order: PRODUCT_FACTS_TODO_CANDIDATES of them) that have no entry yet, or
whose entry lacks a fact that matters for that question (a fact a rule reads for what the question asks). So the facts
that change answers are looked up first.

Command line:
    python -m engine.product_facts todo     the blind-test candidates still to look up (names and product types only),
                                            from the answers on data/library without live checks
"""

import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import AfterValidator, Field, StrictBool, ValidationError, model_validator

from engine.config import (
    BRAND_PICK_UNCHECKABLE,
    HARD_REQUIREMENT_NAMES,
    NEEDS,
    PRODUCT_FACT_REQUEST_WORDS,
    PRODUCT_FACT_RULES,
    PRODUCT_FACT_VALUES,
    PRODUCT_FACTS_BY_TYPE,
    PRODUCT_FACTS_TODO_CANDIDATES,
    UNCONFIRMED_FACT_NAMES,
    UNCONFIRMED_NOTE,
    THREAD_CATEGORIES,
)
from engine.match_products import known_aliases, product_words, same_product, written_alike
from engine.models import Record
from engine.needs import request_needs
from engine.query import MUST_HAVES, PRODUCT_TYPES, ParsedQuery

DEFAULT_PRODUCT_FACTS = Path(__file__).resolve().parents[1] / "data" / "product_facts.json"


class ProductFactsError(Exception):
    pass


def _source_page(url: str) -> str:
    """A source page: starting "https://", with a web address, and no spaces, name or password in it."""
    parts = urlsplit(url)
    unsafe = parts.username or parts.password or any(c.isspace() for c in url)
    if not url.startswith("https://") or not parts.hostname or unsafe:
        raise ValueError("a source link must start with https:// and have no spaces, name or password in it")
    return url


class ProductFacts(Record):
    """One entry of the facts list: what is known about one product, where it comes from and when it was checked."""

    product: str = Field(min_length=1)  # the product's full name, brand first
    category: Literal[THREAD_CATEGORIES]
    product_type: str  # one of module 1's product types: "retinoid", "frying pan"
    facts: dict[str, StrictBool | str]  # {fact: value}, from the vocabulary; a fact not known is left out
    sources: list[Annotated[str, AfterValidator(_source_page)]] = Field(min_length=1)
    checked_on: date

    @model_validator(mode="after")
    def _fits_the_vocabulary(self) -> "ProductFacts":
        product_type = next((p for p in PRODUCT_TYPES if p.name == self.product_type), None)
        if product_type is None:
            types = ", ".join(p.name for p in PRODUCT_TYPES)
            raise ValueError(f'unknown product type "{self.product_type}": it must be one of {types}')
        if product_type.category != self.category:
            raise ValueError(f"a {self.product_type} is a {product_type.category} product, not {self.category}")
        allowed = PRODUCT_FACTS_BY_TYPE.get(self.product_type, ())
        if not allowed:
            raise ValueError(f"no facts are kept for a {self.product_type} yet (config.PRODUCT_FACTS_BY_TYPE)")
        if not self.facts:
            raise ValueError("an entry needs at least one fact")
        for fact, value in self.facts.items():
            if fact not in allowed:
                raise ValueError(f'unknown fact "{fact}" for a {self.product_type}: the facts a {self.product_type} '
                                 f"can have are {', '.join(allowed)}")
            values = PRODUCT_FACT_VALUES[fact]
            if not any(type(value) is type(v) and value == v for v in values):  # true is never "true", nor 1
                shown = ", ".join(json.dumps(v) if isinstance(v, bool) else v for v in values)
                raise ValueError(f'"{fact}" can be {shown}, not {json.dumps(value)}')
        return self


@dataclass(frozen=True)
class Conflict:
    """One way a product's facts don't suit a request."""

    rule: str  # the rule's name in config.PRODUCT_FACT_RULES: "too strong"
    reason: str  # in words, for the shopper: "it is a strong formula, too strong for beginners or sensitive skin"
    hard: bool  # True: the product is left out; False: it is kept, with the reason as a caution under its pick


@dataclass(frozen=True)
class NotSuited:
    """A product left out because its facts clash with the request (the pipeline's left_out_not_suited)."""

    name: str  # the product's name, as the answer would have shown it
    reason: str  # every hard clash's reason, joined with "; "


# --- The list ---

def load_product_facts(path: Path = DEFAULT_PRODUCT_FACTS) -> list[ProductFacts]:
    """Every entry of the facts list (data/product_facts.json by default). A malformed file or entry raises
    ProductFactsError, naming the entry and the problem."""
    try:
        entries = json.loads(Path(path).read_text(encoding="utf-8"))["facts"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        raise ProductFactsError(f"{path}: not a product facts list ({e})") from e
    if not isinstance(entries, list):
        raise ProductFactsError(f'{path}: "facts" must be a list')
    loaded = []
    for number, entry in enumerate(entries, start=1):
        try:
            loaded.append(ProductFacts.model_validate(entry))
        except ValidationError as e:
            problems = "; ".join(f"{'.'.join(map(str, err['loc'])) or 'entry'}: {_plain(err['msg'])}"
                                 for err in e.errors())
            raise ProductFactsError(f"{path}, entry {number}: {problems}") from e
    return loaded


def _plain(message: str) -> str:
    """Pydantic's message without its "Value error, " label."""
    return message.removeprefix("Value error, ")


# --- One product's facts ---

def find_facts(name: str, category: str, entries: Iterable[ProductFacts],
               product_type: str | None = None) -> ProductFacts | None:
    """The facts entry of the product called `name`, or None when the list has none.

    Among the entries of the same category whose name means the same product (module 4's rules): the one with the
    same words (but for spelling slips: engine.match_products.written_alike) first, then one of `product_type` (the
    request's), then the newest check, then the name, so the choice is always the same. Entries are never merged: two names may be two versions of a product.
    """
    aliases = known_aliases().get(category, {})
    fits = [e for e in entries if e.category == category and same_product(e.product, name, aliases)]
    if not fits:
        return None
    words = product_words(name, aliases)

    def preference(e: ProductFacts) -> tuple:
        exact = written_alike(product_words(e.product, aliases), words)  # the same name, but for slips
        return not exact, e.product_type != product_type, -e.checked_on.toordinal(), e.product.casefold()

    return min(fits, key=preference)


# --- Facts against a request ---

def request_asks(query: ParsedQuery) -> tuple[str, ...]:
    """What the request asks for that a fact can meet, each named once: module 1's skin types and must-haves, the needs
    engine/needs.py finds that aren't must-haves ("beginner", "gentle"), and config.PRODUCT_FACT_REQUEST_WORDS
    ("PFAS-free", "non-stick", "no white cast"). Nothing for a request module 1 didn't understand (a question or a
    polite no)."""
    if query.status != "ok":
        return ()
    asks = list(query.constraints.skin_types) + list(query.constraints.must_haves)
    asks += [need.name for need in request_needs(query) if need.name in NEEDS and need.name not in MUST_HAVES]
    text = query.text.lower().replace("’", "'")
    asks += [ask for ask, patterns in PRODUCT_FACT_REQUEST_WORDS.items()
             if any(re.search(rf"\b{pattern}", text) for pattern in patterns)]
    return tuple(dict.fromkeys(asks))


def conflicts(query: ParsedQuery, facts: ProductFacts | None) -> list[Conflict]:
    """Every way a product's facts don't suit the request, in the rule table's order; [] when they all suit it, or when
    nothing is known (`facts` None). A rule counts when the request asks for one of its "asks" and the product's fact
    has the rule's value; a fact the entry doesn't give never counts."""
    if facts is None:
        return []
    asks = set(request_asks(query))
    found = []
    for name, rule in PRODUCT_FACT_RULES.items():
        if asks & set(rule["asks"]) and _has(facts, rule["fact"], rule["value"]):
            found.append(Conflict(name, rule["reason"], rule["hard"]))
    return found


def _has(facts: ProductFacts, fact: str, value) -> bool:
    """Whether the entry gives `fact` exactly this value (true is never 1, and a fact not given is never false)."""
    if fact not in facts.facts:
        return False
    known = facts.facts[fact]
    return type(known) is type(value) and known == value


def facts_that_matter(query: ParsedQuery) -> list[str]:
    """The facts a rule reads for what this request asks, among those its product type can have, in the rule table's
    order: what to look up first for it. [] when no rule applies. A rule marked "confirm": False (a maker's warning,
    recorded only when a maker's page says it) is never asked for."""
    asks = set(request_asks(query))
    allowed = PRODUCT_FACTS_BY_TYPE.get(query.product_type or "", ())
    matter = [rule["fact"] for rule in PRODUCT_FACT_RULES.values()
              if asks & set(rule["asks"]) and rule["fact"] in allowed and rule.get("confirm", True)]
    return list(dict.fromkeys(matter))


def hard_requirements(query: ParsedQuery) -> list[str]:
    """The hard rules (config.PRODUCT_FACT_RULES, "hard": True) this request asks for, in the rule table's order: the
    request asks for one of the rule's "asks", and the rule's fact is one its product type can have
    (config.PRODUCT_FACTS_BY_TYPE). [] when none applies: "first chef's knife" asks for a beginner's strength, but a
    chef knife has no strength to check. A rule marked "confirm": False (a maker's warning) is never a requirement. A
    brand pick can't be checked for any of them (engine/pipeline.py)."""
    asks = set(request_asks(query))
    allowed = PRODUCT_FACTS_BY_TYPE.get(query.product_type or "", ())
    return [name for name, rule in PRODUCT_FACT_RULES.items()
            if rule["hard"] and rule.get("confirm", True) and asks & set(rule["asks"]) and rule["fact"] in allowed]


def unconfirmed(query: ParsedQuery, facts: ProductFacts | None) -> list[str]:
    """The hard requirements of this request (hard_requirements) whose fact the product's entry doesn't give, in the
    rule table's order: what we couldn't confirm about it (10 Oct 2026). All of them when nothing is known (`facts`
    None); a fact known to clash is a reason to leave the product out (conflicts), not something unconfirmed."""
    requirements = hard_requirements(query)
    known = facts.facts if facts is not None else {}
    return [name for name in requirements if PRODUCT_FACT_RULES[name]["fact"] not in known]


def unconfirmed_note(rules: list[str]) -> str:
    """The note under a pick whose facts couldn't confirm these requirements, in words for the shopper (config.
    UNCONFIRMED_NOTE and UNCONFIRMED_FACT_NAMES): "we couldn't confirm it's PFAS-free or that it's non-stick"."""
    named = [UNCONFIRMED_FACT_NAMES[rule] for rule in rules]
    named = named[:1] + [f"that {words}" for words in named[1:]]
    listed = ", ".join(named[:-1]) + " or " + named[-1] if len(named) > 1 else named[0]
    return UNCONFIRMED_NOTE.format(facts=listed)


def uncheckable_brand_reason(rules: list[str]) -> str:
    """Why a brand pick is left out of a request with these hard rules, in words for the shopper (config.
    BRAND_PICK_UNCHECKABLE and HARD_REQUIREMENT_NAMES): "a whole brand can't be checked for PFAS or a non-stick
    coating"."""
    named = [HARD_REQUIREMENT_NAMES.get(rule, rule) for rule in rules]
    listed = ", ".join(named[:-1]) + " or " + named[-1] if len(named) > 1 else named[0]
    return BRAND_PICK_UNCHECKABLE.format(requirements=listed)


# --- What is still to look up: python -m engine.product_facts todo ---

@dataclass
class CandidateToCheck:
    name: str  # the product's name, as the answer shows it
    product_type: str  # the type its entry should give: the question's
    has_entry: bool  # False: no entry yet
    missing: list[str]  # the facts that matter for the question that it doesn't give yet


@dataclass
class QuestionFactsToCheck:
    id: str  # the blind-test question's id, "b03"
    product_type: str | None  # module 1's product type; None when it couldn't place the question
    category: str | None
    facts_that_matter: list[str]  # facts_that_matter(): [] when no rule reads a fact for this question
    candidates: int  # how many candidates were looked at
    to_check: list[CandidateToCheck] = field(default_factory=list)  # picks first, then the ranking's order
    brand_candidates: list[str] = field(default_factory=list)  # brand picks (decision 9): no single product to look up


def candidates(run, limit: int | None = None) -> list[str]:
    """The names of a pipeline result's top candidates: its picks, in the answer's order, then the products that
    qualify or nearly qualify (at least one credible recommendation, a score above zero, not on the skip list), in the
    ranking's order; `limit` of them at most (None: PRODUCT_FACTS_TODO_CANDIDATES)."""
    limit = PRODUCT_FACTS_TODO_CANDIDATES if limit is None else limit
    if run.answer is None or run.ranking is None:
        return []
    names = [pick.name for pick in run.answer.picks]
    for product in run.ranking.products:
        if product.name in names or product.on_skip_list or product.score <= 0:
            continue
        if product.qualifies or product.credible_recommendations:
            names.append(product.name)
    return names[:limit]


def todo(questions_path: Path | None = None, library_dir: Path | None = None,
         facts: list[ProductFacts] | None = None, profiles=None, prices=None) -> list[QuestionFactsToCheck]:
    """For each blind-test question, its top candidates still lacking a fact that matters for it.

    Each question runs through engine.pipeline.answer_request on the library (`library_dir`, None: data/library) with
    the facts list (`facts`, None: data/product_facts.json) and the price list (`prices`, None: data/prices.json), and
    without live checks: no quote is read on Reddit (so it is fast and never touches the network), and threads still
    waiting for their live check count too, as in engine.prices.todo. A product the facts already leave out isn't a
    candidate, so the next one moves up. A question for which no rule reads a fact lists nothing: no fact would change
    its answer. Brand picks have no single product, so they are named apart. `profiles`: as in engine.pipeline.
    """
    from engine.library import DEFAULT_LIBRARY_DIR  # imported here: the pipeline imports this module
    from engine.pipeline import answer_request
    from engine.slice_eval import DEFAULT_QUESTIONS

    facts = load_product_facts() if facts is None else facts
    questions = json.loads(Path(questions_path or DEFAULT_QUESTIONS).read_text(encoding="utf-8"))["questions"]
    results = []
    for question in questions:
        run = answer_request(question["text"], library_dir=library_dir or DEFAULT_LIBRARY_DIR, profiles=profiles,
                             prices=prices, product_facts=facts, live_check_required=False)
        query = run.query
        matter = facts_that_matter(query)
        names = candidates(run)
        result = QuestionFactsToCheck(question["id"], query.product_type, query.category, matter, len(names))
        for name in names if matter else []:
            if name in run.not_priced:  # a brand pick: named in not_priced by the pipeline
                result.brand_candidates.append(name)
                continue
            entry = find_facts(name, query.category, facts, query.product_type)
            lacking = [fact for fact in matter if entry is None or fact not in entry.facts]
            if lacking:
                result.to_check.append(CandidateToCheck(name, query.product_type, entry is not None, lacking))
        results.append(result)
    return results


def main(argv: list[str], questions_path: Path | None = None, library_dir: Path | None = None,
         facts: list[ProductFacts] | None = None, prices=None) -> int:
    """`questions_path`, `library_dir`, `facts` and `prices` can be swapped for made-up ones, which is how the tests
    run it. It prints names and product types only: never a quote."""
    if argv != ["todo"]:
        print(__doc__)
        return 2
    from engine.extract import ExtractionError  # imported here: the pipeline imports this module
    from engine.gold import GoldSetError
    from engine.pipeline import cached_profiles
    from engine.prices import PriceError

    try:
        results = todo(questions_path, library_dir, facts, profiles=cached_profiles(), prices=prices)
    except (ProductFactsError, PriceError, GoldSetError, ExtractionError) as e:  # a broken list, or no library
        print(e)
        return 1
    print("Blind-test candidates still to look up for data/product_facts.json (answers from the library, without "
          "live checks):")
    for question in results:
        if not question.candidates:
            print(f"  {question.id}: no candidates")
            continue
        heading = f"  {question.id} {question.product_type} ({question.category})"
        if not question.facts_that_matter:
            print(f"{heading}: no rule reads a fact for this request")
            continue
        heading += f", facts that matter: {', '.join(question.facts_that_matter)}"
        if not question.to_check and not question.brand_candidates:
            print(f"{heading}: every candidate has them")
            continue
        print(heading)
        for candidate in question.to_check:
            lacks = f"its entry lacks {', '.join(candidate.missing)}" if candidate.has_entry else "no entry yet"
            print(f"    {candidate.name} ({candidate.product_type}): {lacks}")
        for name in question.brand_candidates:
            print(f"    {name}: a brand pick, no single product to look up")
    found = [candidate for question in results for candidate in question.to_check]
    no_entry = sum(not candidate.has_entry for candidate in found)
    print(f"{len(found)} candidate{'' if len(found) == 1 else 's'} to look up: {no_entry} with no entry yet, "
          f"{len(found) - no_entry} with an entry missing a fact that matters.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
