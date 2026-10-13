"""Brand lines (Noemi's note of 12 Oct 2026, from testing the demo): a brand named on its own counts for a request only
when the brand really sells that kind of product, checked on the makers' own pages (data/brand_lines.json).

Her example: in a hair oil answer, a writer praises "the L'Oréal one". Does L'Oréal sell hair oils? If it does, the
mention counts, and with enough credible support "L'Oréal hair oil line" can be one of the top 3. If it doesn't, the
mention is about something else and is left out, with the reason. Until 12 Oct 2026 only clues from the threads decided
(engine.pipeline._clear_brand: the thread titles, and a product of the type named by the brand's writers).

Her other question: does the footnote's "brand or line names that fit several products (19)" count mentions or
threads? Neither: it counts names. The page now says so in words, with a few of the names.

Every brand, entry, source link and library here is made up (but for a few real spellings that show how names are
matched), and every library is a temporary folder: no test reads data/ except the one that checks the committed list.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from engine import pipeline, web
from engine.answer import unverified_claims
from engine.brand_lines import (
    DEFAULT_BRAND_LINES,
    BrandLine,
    BrandLinesError,
    find_brand_line,
    load_brand_lines,
    not_sold_reason,
)
from engine.pipeline import answer_request
from engine.product_facts import NotSuited
from engine.tests.factories import make_comment, make_thread, write_gold
from engine.tests.test_availability import listed
from engine.tests.test_pick_polish import TRAMONTINA, pan_library
from engine.tests.test_pipeline import praise, write_library

TODAY = date(2026, 10, 12)
SKILLET = "cast iron skillet that lasts"


def line(brand: str = "Pansmith", product_type: str = "cast iron skillet", sells: bool = True,
         category: str = "kitchen", also_called: tuple[str, ...] = (), checked_on: date = TODAY) -> BrandLine:
    """One made-up entry of the brand-lines list."""
    return BrandLine(brand=brand, also_called=list(also_called), category=category, product_type=product_type,
                     sells=sells, sources=["https://maker.example/range"], checked_on=checked_on,
                     note="Made up for a test.")


def entry(**overrides) -> dict:
    data = {"brand": "Pansmith", "category": "kitchen", "product_type": "cast iron skillet", "sells": True,
            "sources": ["https://maker.example/skillets"], "checked_on": "2026-10-12",
            "note": "The maker's own range page lists three cast iron skillets."}
    data.update(overrides)
    return data


def write_lines(tmp_path: Path, entries) -> Path:
    path = tmp_path / "brand_lines.json"
    path.write_text(json.dumps({"brand_lines": entries}), encoding="utf-8")
    return path


# --- The list ---

def test_the_committed_list_is_valid():
    assert DEFAULT_BRAND_LINES.name == "brand_lines.json" and DEFAULT_BRAND_LINES.parent.name == "data"
    raw = json.loads(DEFAULT_BRAND_LINES.read_text(encoding="utf-8"))["brand_lines"]
    loaded = load_brand_lines()
    assert len(loaded) == len(raw)
    # Every entry says where it comes from (a maker's or a big shop's page, never Reddit), when, and what was found.
    assert all(e.sources and all(s.startswith("https://") for s in e.sources) and e.checked_on and e.note
               for e in loaded)


def test_an_entry_loads_with_its_sources_date_and_note(tmp_path):
    [loaded] = load_brand_lines(write_lines(tmp_path, [entry()]))
    assert (loaded.brand, loaded.category, loaded.product_type, loaded.sells) == (
        "Pansmith", "kitchen", "cast iron skillet", True)
    assert loaded.sources == ["https://maker.example/skillets"] and loaded.checked_on == TODAY
    assert loaded.note.startswith("The maker's own range page") and loaded.also_called == []


def test_a_kind_of_product_the_open_model_names_is_a_type_too(tmp_path):
    # Module 1's open model names types of its own ("air fryer", 11 Oct 2026), so the list isn't held to module 1's.
    [loaded] = load_brand_lines(write_lines(tmp_path, [entry(brand="Fryco", product_type="air fryer")]))
    assert loaded.product_type == "air fryer"


@pytest.mark.parametrize("bad", [
    {"sells": "yes"},  # JSON true or false only
    {"sells": 1},
    {"sells": None},
    {"brand": ""},
    {"brand": "the"},  # filler words only: no brand at all
    {"category": "other"},
    {"product_type": "shampoo"},  # a haircare type in a kitchen entry
    {"product_type": "Cast Iron Skillet"},  # lowercase, as module 1 writes types
    {"product_type": ""},
    {"sources": []},  # at least one source
    {"sources": ["http://maker.example/skillets"]},  # https only
    {"sources": ["https://"]},
    {"sources": ["https://someone:secret@maker.example/skillets"]},  # a name and password in a link: never
    {"sources": ["https://maker.example/a page"]},  # spaces
    {"sources": ["https://www.reddit.com/r/castiron/comments/abc/x/"]},  # never Reddit: writers aren't makers
    {"sources": ["https://old.reddit.com/r/castiron/"]},
    {"sources": ["https://redd.it/abc"]},
    {"sources": "https://maker.example/skillets"},  # a list of links
    {"checked_on": "12 Oct 2026"},
    {"also_called": "Pan Smith"},  # a list of names
    {"also_called": [""]},
    {"price": 12.0},  # an unknown field is a typo, never ignored
])
def test_a_malformed_entry_is_refused_naming_where_it_is(tmp_path, bad):
    with pytest.raises(BrandLinesError) as refused:
        load_brand_lines(write_lines(tmp_path, [entry(), entry(**bad)]))
    assert "entry 2" in str(refused.value)


def test_a_second_entry_for_the_same_brand_and_type_is_refused(tmp_path):
    # Two entries could disagree, and which one would count? "L'Oreal" and "L'Oréal" are one brand.
    first = entry(brand="L'Oréal", category="haircare", product_type="hair oil")
    with pytest.raises(BrandLinesError) as refused:
        load_brand_lines(write_lines(tmp_path, [first, entry(brand="L'Oreal", category="haircare",
                                                            product_type="hair oil", sells=False)]))
    assert "entry 2" in str(refused.value) and "entry 1" in str(refused.value)
    # The same brand for another type is another entry.
    other = entry(brand="L'Oréal", category="haircare", product_type="shampoo")
    assert len(load_brand_lines(write_lines(tmp_path, [first, other]))) == 2


@pytest.mark.parametrize("content", ['{"lines": []}', '{"brand_lines": {}}', "[]", "{not json"])
def test_a_file_without_a_brand_lines_list_is_refused(tmp_path, content):
    path = tmp_path / "brand_lines.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(BrandLinesError):
        load_brand_lines(path)


# --- Finding a brand's entry ---

@pytest.mark.parametrize("written", ["Pansmith", "pansmith", "PANSMITH", "Pansmith's", "Pan Smith", "Pansmith skillet",
                                     "Pansmith cast iron", "Pansmith cast iron skillets", "the Pansmith one"])
def test_a_brand_name_finds_its_entry_as_writers_spell_it(written):
    # Case, spacing, a possessive and the request's own type words aside ("Pansmith skillet" in a skillet answer).
    assert find_brand_line([written], "kitchen", "cast iron skillet", [line()]) == line()


@pytest.mark.parametrize("brand, written, category, product_type", [
    ("L'Oréal", "L'Oreal", "haircare", "hair oil"),  # accents aside
    ("L'Oréal", "loreal hair oil", "haircare", "hair oil"),
    ("Head & Shoulders", "head and shoulders", "haircare", "shampoo"),  # "&" and "and"
    ("KitchenAid", "Kitchen Aid", "kitchen", "stand mixer"),  # one word or two
    ("Zojirushi", "Zojurushi", "kitchen", "rice cooker"),  # a spelling slip
])
def test_real_spellings_find_their_brand(brand, written, category, product_type):
    entry_ = line(brand, product_type, category=category)
    assert find_brand_line([written], category, product_type, [entry_]) == entry_


def test_another_name_the_brand_goes_by_finds_it_too():
    entry_ = line("Pansmith", also_called=("PS Cookware",))
    assert find_brand_line(["PS Cookware"], "kitchen", "cast iron skillet", [entry_]) == entry_


@pytest.mark.parametrize("written", [
    "Pansmith Heritage",  # a line of the brand isn't the brand: it needs an entry of its own
    "Pansmith pans",  # words that aren't the request's type
    "Potsmith",  # another name: two letters apart is no spelling slip
    "the one",  # filler words only
])
def test_other_names_find_nothing(written):
    assert find_brand_line([written], "kitchen", "cast iron skillet", [line()]) is None


def test_an_entry_speaks_only_for_its_own_type_and_category():
    entries = [line(product_type="frying pan"), line(category="haircare", product_type="shampoo")]
    assert find_brand_line(["Pansmith"], "kitchen", "cast iron skillet", entries) is None
    assert find_brand_line(["Pansmith"], "kitchen", None, [line()]) is None  # no type, nothing to check


def test_a_line_of_the_brand_has_an_entry_of_its_own():
    brand, own = line("Pansmith", sells=False), line("Pansmith Heritage", sells=True)
    assert find_brand_line(["Pansmith Heritage"], "kitchen", "cast iron skillet", [brand, own]) == own
    assert find_brand_line(["Pansmith"], "kitchen", "cast iron skillet", [brand, own]) == brand


def test_the_reason_a_brand_is_left_out_names_what_it_doesnt_sell():
    assert not_sold_reason(line(sells=False)) == "Pansmith doesn't sell cast iron skillets"
    assert not_sold_reason(line("Fryco", "air fryer", sells=False)) == "Fryco doesn't sell air fryers"


# --- The pipeline: who decides whether a brand name counts ---

def brand_library(tmp_path: Path) -> Path:
    """Skillet threads with made-up brands, each praised by a different writer in each comment.
    - "Ironworks" fits two Ironworks skillets (so its group is loose), praised in two threads whose titles name a
      skillet: its threads make the product clear, so the threads alone keep it.
    - "Pansmith" fits two Pansmith skillets, praised once in a skillet thread and twice in a thread whose title names no
      skillet: only a third of its mentions are in threads about skillets, so the threads alone leave it out.
    - "Potco" fits a stainless pan and a non-stick pan, praised three times in skillet threads: none of its products
      named here is a skillet, so the threads alone leave it out.
    - "Hearthco" fits two Hearthco skillets, praised twice, in the thread whose title names no skillet: the threads
      alone leave it out, and two recommendations in one thread are too little evidence for a pick anyway.
    - The Forgewell skillet (a specific product) is praised three times across both skillet threads.
    """
    return write_library(tmp_path, {
        "1skil01": ("Best cast iron skillet for a beginner?", "My first one.", [
            praise("i1a", "Ironworks", 20), praise("i1b", "Ironworks", 12),
            praise("i1c", "Ironworks No. 8 skillet", 3), praise("i1d", "Ironworks No. 10 skillet", 4),
            praise("p1a", "Pansmith", 5),
            praise("p1b", "Pansmith No. 8 skillet", 2), praise("p1c", "Pansmith No. 12 skillet", 2),
            praise("c1a", "Potco", 9), praise("c1b", "Potco", 8),
            praise("c1c", "Potco stainless pan", 4), praise("c1d", "Potco non-stick pan", 2),
            praise("h1c", "Hearthco No. 8 skillet", 2), praise("h1d", "Hearthco No. 10 skillet", 3),
            praise("f1a", "Forgewell skillet", 6), praise("f1b", "Forgewell skillet", 7),
        ]),
        "1skil02": ("Which cast iron skillet lasts?", "Mine cracked.", [
            praise("i2a", "Ironworks", 15), praise("c2a", "Potco", 7), praise("f2a", "Forgewell skillet", 5),
        ]),
        # Read (its post names a skillet), but its title doesn't: what it says about a brand is less clear.
        "1skil03": ("What should I cook my first steak in?", "Thinking of a cast iron skillet.", [
            praise("p3a", "Pansmith", 7), praise("p3b", "Pansmith", 8),
            praise("h3a", "Hearthco", 6), praise("h3b", "Hearthco", 7),
        ]),
    })


def run(tmp_path: Path, lines: list[BrandLine], request: str = SKILLET, prices=(), library: Path | None = None):
    return answer_request(request, library_dir=library or brand_library(tmp_path), prices=list(prices),
                          product_facts=[], brand_lines=lines, today=TODAY)


def names(result) -> list[str]:
    return [pick.name for pick in result.answer.picks]


def ranked(result) -> list[str]:
    return [product.name for product in result.ranking.products]


def qualifying(result) -> list[str]:
    return [product.name for product in result.ranking.qualifying]


def test_with_no_entry_the_threads_decide_as_before(tmp_path):
    result = run(tmp_path, [])
    assert "Ironworks cast iron skillet line" in names(result)
    assert {"Pansmith", "Potco", "Hearthco"} <= set(result.left_out_loose)
    assert not any(name.endswith(" line") and name != "Ironworks cast iron skillet line" for name in ranked(result))
    assert result.brands_not_selling == []


def test_a_brand_the_list_says_sells_the_type_counts_even_when_its_threads_dont_make_it_clear(tmp_path):
    # Noemi's example: the brand sells the kind of product asked for, so its writers' mentions count, and with enough
    # credible support its whole line is a pick.
    result = run(tmp_path, [line("Pansmith"), line("Potco")])
    assert {"Pansmith cast iron skillet line", "Potco cast iron skillet line"} <= set(qualifying(result))
    assert "Pansmith" not in result.left_out_loose and "Potco" not in result.left_out_loose
    assert unverified_claims(result.answer, result.bodies) == []


def test_a_brand_the_list_says_doesnt_sell_the_type_is_left_out_with_the_reason(tmp_path):
    # Even though its threads alone would have kept it: its writers must have meant something else of the brand's.
    result = run(tmp_path, [line("Ironworks", sells=False)])
    assert "Ironworks cast iron skillet line" not in ranked(result)
    assert "Ironworks" in result.left_out_loose
    assert result.brands_not_selling == [NotSuited("Ironworks", "Ironworks doesn't sell cast iron skillets")]


def test_an_entry_about_another_type_says_nothing_about_this_one(tmp_path):
    result = run(tmp_path, [line("Pansmith", "frying pan"), line("Ironworks", "frying pan", sells=False)])
    assert "Ironworks cast iron skillet line" in names(result)
    assert "Pansmith" in result.left_out_loose and result.brands_not_selling == []


def test_a_brand_line_still_needs_the_minimum_evidence(tmp_path):
    # 2 credible recommendations in 1 thread: ranked as the brand's line, but not a pick (3 across 2 threads needed).
    result = run(tmp_path, [line("Hearthco")])
    assert "Hearthco cast iron skillet line" in ranked(result)
    assert "Hearthco cast iron skillet line" not in names(result)


def test_a_brand_whose_mentions_say_another_type_stays_out_whatever_the_list_says(tmp_path):
    # The list says what the brand sells; the AI's type for each mention says what its writer meant. A writer who
    # praises the brand's Dutch oven in a skillet thread isn't praising a skillet.
    library = brand_library(tmp_path)
    for path in (library / "extracted").glob("*.json"):
        extraction = json.loads(path.read_text(encoding="utf-8"))
        for mention in extraction["mentions"]:
            if mention["product"] == "Pansmith":
                mention["product_type"] = "dutch oven"
        path.write_text(json.dumps(extraction), encoding="utf-8")
    result = run(tmp_path, [line("Pansmith")], library=library)
    assert "Pansmith cast iron skillet line" not in ranked(result) and "Pansmith" in result.left_out_loose


def test_brand_picks_switched_off_leave_every_brand_out_whatever_the_list_says(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "PIPELINE_BRAND_PICKS", False)
    result = run(tmp_path, [line("Pansmith"), line("Ironworks")])
    assert not any(name.endswith(" line") for name in ranked(result))


def test_whether_uk_shoppers_can_buy_it_is_still_the_price_lists_job(tmp_path):
    # The list says the brand sells skillets; a price-list entry under the brand's name says they aren't sold here.
    result = run(tmp_path, [line("Pansmith")], prices=[listed("Pansmith skillet", available=False)])
    assert "Pansmith cast iron skillet line" not in ranked(result)
    assert "Pansmith cast iron skillet line" in result.left_out_unavailable


def test_a_brand_line_is_still_left_out_under_a_hard_requirement(tmp_path):
    # Decided 10 Oct 2026: a whole brand can't be checked for PFAS or a non-stick coating, whatever it sells.
    # Changed on purpose 13 Oct 2026 (Noemi's decision 1 of 13 Oct): it is ranked again, so its credible warnings can
    # list it under Skip these, but it never qualifies as a pick.
    result = answer_request("non-stick frying pan without PFAS", library_dir=pan_library(tmp_path), prices=[],
                            product_facts=[], brand_lines=[line("Tramontina", "frying pan")], today=TODAY)
    assert TRAMONTINA not in qualifying(result) and TRAMONTINA not in names(result)
    assert result.left_out_not_suited == [NotSuited(TRAMONTINA, "a whole brand can't be checked for PFAS or a "
                                                                "non-stick coating")]


def test_a_brand_written_in_lowercase_only_is_shown_as_its_maker_writes_it(tmp_path):
    library = write_library(tmp_path, {
        "1skil01": ("Best cast iron skillet?", "My first one.", [
            praise("p1a", "pansmith", 5), praise("p1b", "pansmith", 6),
            praise("p1c", "Pansmith No. 8 skillet", 2), praise("p1d", "Pansmith No. 12 skillet", 2),
        ]),
        "1skil02": ("Which cast iron skillet lasts?", "Mine cracked.", [praise("p2a", "pansmith", 7)]),
    })
    assert names(run(tmp_path, [], library=library)) == ["pansmith cast iron skillet line"]  # the threads decide
    assert names(run(tmp_path, [line("PanSmith")], library=library)) == ["PanSmith cast iron skillet line"]


def hair_oil_library(tmp_path: Path) -> Path:
    """Noemi's example, made up: hair oil threads whose titles don't say "hair oil" (their posts do), where three
    writers praise "the L'Oreal one", which the AI writes as "L'Oreal" and types as a hair oil, next to two L'Oréal oils
    named in full (so "L'Oreal" fits two products: a loose group)."""
    texts = {"h1a": "The L'Oreal one is the only thing that tames my frizz, three years in.",
             "h1b": "Been using the L'Oreal one for two years, still my favourite.",
             "h1c": "My L'Oreal Extraordinary Oil lasted months and smells lovely.",
             "h1d": "The L'Oreal Midnight Serum works overnight for me, a year now.",
             "h2a": "The L'Oreal one has been in my routine for four years."}
    threads, extractions = [], {}
    for thread_id, title, ids in (("1hair01", "Frizz help?", ("h1a", "h1b", "h1c", "h1d")),
                                  ("1hair02", "What finally fixed your frizz?", ("h2a",))):
        threads.append(make_thread(
            id=thread_id, community="HaircareScience", category="haircare", title=title,
            body="Looking for a hair oil that works.",
            url=f"https://www.reddit.com/r/HaircareScience/comments/{thread_id}/thread/",
            comments=[make_comment(cid, thread_id=thread_id, body=texts[cid],
                                   url=f"https://www.reddit.com/r/HaircareScience/comments/{thread_id}/comment/{cid}/")
                      for cid in ids]))
        named = {"h1c": "L'Oreal Extraordinary Oil", "h1d": "L'Oreal Midnight Serum"}
        extractions[thread_id] = [{"comment_id": cid, "product": named.get(cid, "L'Oreal"), "category": "haircare",
                                   "stance": "recommend", "quote": texts[cid], "product_type": "hair oil"}
                                  for cid in ids]
    root = write_gold(tmp_path / "library", threads, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for thread_id, mentions in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v9", "extracted_at": "2026-10-12T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions}), encoding="utf-8")
    return root


def test_noemis_example_the_brand_named_alone_counts_when_it_sells_the_type(tmp_path):
    library = hair_oil_library(tmp_path)
    ask = lambda lines: answer_request("hair oil for frizz", library_dir=library, prices=[], product_facts=[],
                                       brand_lines=lines, today=TODAY)
    before = ask([])  # its threads' titles don't say hair oil, so the clues alone leave it out
    assert "L'Oreal" in before.left_out_loose and not names(before)
    sells = ask([line("L'Oréal Paris", "hair oil", category="haircare", also_called=("L'Oréal",))])
    assert "L'Oreal hair oil line" in [product.name for product in sells.ranking.products]
    assert "L'Oreal hair oil line" in qualifying(sells)  # 3 credible writers across 2 threads: enough for a pick
    doesnt = ask([line("L'Oréal Paris", "hair oil", category="haircare", also_called=("L'Oréal",), sells=False)])
    assert doesnt.brands_not_selling == [NotSuited("L'Oreal", "L'Oréal Paris doesn't sell hair oils")]


def test_the_result_names_the_brand_lines_ranked(tmp_path):
    result = run(tmp_path, [line("Pansmith"), line("Potco", sells=False)])
    assert sorted(result.ranked_as_lines) == ["Ironworks cast iron skillet line", "Pansmith cast iron skillet line"]


# --- The footnote: what its numbers count (Noemi, 12 Oct 2026) ---

def test_the_api_names_a_few_of_the_names_left_out_and_counts_names(tmp_path):
    result = run(tmp_path, [line("Pansmith")])
    left_out = web.answer_json(result)["left_out"]
    # Names (product groups), never mentions or threads: Potco and Hearthco are two names, however often written.
    assert left_out["loose"] == 2 and left_out["loose_names"] == ["Potco", "Hearthco"]
    assert left_out["ranked_as_lines"] == 2  # Ironworks and Pansmith
    assert left_out["other_type"] == len(result.left_out_as_other_type)


def test_the_api_gives_a_handful_of_names_at_most(tmp_path):
    brands = ("Ashford", "Brookline", "Copperfield", "Dunmore", "Ellwood", "Fairhaven")
    comments = [praise("t1a", "the one", 4), praise("t1b", "the one", 5)]
    for number, brand in enumerate(brands):
        comments += [praise(f"b{number}a", brand, 3), praise(f"b{number}b", f"{brand} No. 8 skillet", 2),
                     praise(f"b{number}c", f"{brand} No. 10 skillet", 2)]
    library = write_library(tmp_path, {"1skil01": ("Best cast iron skillet?", "Advice please.", comments)})
    result = run(tmp_path, [line(brand, sells=False) for brand in brands], library=library)
    left_out = web.answer_json(result)["left_out"]
    assert left_out["loose"] == 6  # "the one" names nothing: it is no brand or line name
    assert len(left_out["loose_names"]) == 3 and set(left_out["loose_names"]) <= set(brands)
    assert "the one" in result.left_out_loose  # still listed on the result: nothing is dropped silently


def test_the_page_says_its_numbers_are_names_and_how_brand_names_count():
    page = web.search_page().decode("utf-8")
    assert "fit several products ({loose})" not in page  # the old wording: a number in brackets, counting what?
    assert '"{n} brand or line names that could mean several products"' in page
    assert '"{n} products of another type"' in page
    assert "loose_names" in page and "other_type_names" in page and "ranked_as_lines" in page
    assert "ranked as a brand's whole line instead" in page


def test_the_how_page_shows_a_brand_line_and_how_brands_are_checked(tmp_path, monkeypatch):
    from engine.tests.test_how_page import get_how, text_of

    text = text_of(get_how(tmp_path, monkeypatch))
    assert '"Lodge cast iron skillet line"' in text
    assert "(their" not in text
    assert "on the maker's pages or a big shop's, that the brand sells the kind of product you asked for" in text
