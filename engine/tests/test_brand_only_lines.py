"""A brand named only as a brand is its brand's line (17 Oct 2026; the coordinator's technical call within Noemi's
decision 8 of 16 Oct 2026, her 12 Oct rule made consistent: brand-only names count when data/brand_lines.json says the
brand makes the requested type, and are shown as "<Brand> <type> line").

Why: writers name Circulon's and Ballarini's frying pans by brand only ("Circulon pans", "ballarini"), never a model.
Module 4 keeps such a group as one product when no model of the brand is named, so a PFAS-free answer picked "Circulon
pans" as if it were one pan (with a note that we couldn't confirm it). Decision 8 makes them brand lines, and a line
under a must-have is left out, as a whole brand can't be checked (decided 10 Oct 2026).

The rule (engine.pipeline._brand_only_lines): a product group becomes its brand's line only when all of these hold:
- the brand-lines entry its names find (engine.brand_lines.find_brand_line, as for any brand name) sells the requested
  type;
- every name of the group is that brand (or one of its other names, also_called) alone or followed only by words that
  name no model (engine.pipeline._names_a_model: the type's words and synonyms, "non-stick", descriptions);
- no facts or price entry its names find names one product (a model) of it: then the lists say which product it is.

Every brand, library, entry and comment here is made up, and every library is a temporary folder, but in the last
tests, which read the committed lists with the names writers use for b10's brands.
"""

from datetime import date

import pytest

from engine import pipeline
from engine.brand_lines import BrandLine, load_brand_lines
from engine.group_products import ProductGroup, ProductMention
from engine.pipeline import answer_request
from engine.prices import Price, load_prices
from engine.product_facts import NotSuited, ProductFacts, load_product_facts
from engine.tests.test_pipeline import praise, write_library

TODAY = date(2026, 10, 17)
LASTS = "frying pan that lasts"
PFAS_FREE = "non-stick frying pan without PFAS that lasts"
WHOLE_BRAND = "a whole brand can't be checked for PFAS or a non-stick coating"
FRYCO_LINE = "Fryco frying pan line"


def entry(brand: str = "Fryco", sells: bool = True, also_called: tuple[str, ...] = ("Bigco/Fryco",)) -> BrandLine:
    """A made-up brand-lines entry for frying pans, with a range page and a from price."""
    site = f"https://{brand.lower()}.example"
    return BrandLine(brand=brand, also_called=list(also_called), category="kitchen", product_type="frying pan",
                     sells=sells, sources=[f"{site}/pans", f"{site}/pans/small"], checked_on=TODAY,
                     range_page=f"{site}/pans", from_price=29.99, from_price_shop=brand,
                     from_price_url=f"{site}/pans/small", from_price_checked_on=TODAY, note="Made up for a test.")


def facts(product: str, **known) -> ProductFacts:
    return ProductFacts(product=product, category="kitchen", product_type="frying pan", facts=known,
                        sources=["https://facts.example/page"], checked_on=TODAY)


def pans(tmp_path):
    """Frying-pan threads. Fryco is named by brand only, three ways (with the type's words, alone, and after a co-brand
    with "non-stick"), by five writers across both threads; Potco by brand only too; Duoware once by brand and twice by
    a model, the Classic, so its brand name is that model."""
    return write_library(tmp_path, {
        "1fry001": ("Best frying pan that lasts?", "Mine is peeling.", [
            praise("f1a", "Fryco pans", 6), praise("f1b", "Fryco pans", 7),
            praise("f1c", "Bigco/Fryco non-stick pans", 4),
            praise("p1a", "Potco pans", 5), praise("p1b", "Potco", 6),
            praise("d1a", "Duoware Classic frying pan", 4),
        ]),
        "1fry002": ("Which non-stick frying pan lasts?", "Ten years, ideally.", [
            praise("f2a", "Fryco pans", 8), praise("f2b", "fryco", 5),
            praise("p2a", "Potco pans", 7),
            praise("d2a", "Duoware Classic frying pan", 6), praise("d2b", "Duoware", 3),
        ]),
    }, community="BuyItForLife")


def answer(tmp_path, request=LASTS, lines=(), prices=(), known=(), library=None):
    return answer_request(request, library_dir=library or pans(tmp_path), prices=list(prices),
                          product_facts=list(known), brand_lines=list(lines), product_pages=[], today=TODAY,
                          more_threads=None)


def picks(result) -> list[str]:
    return [pick.name for pick in result.answer.picks]


def ranked(result) -> list[str]:
    return [product.name for product in result.ranking.products]


# --- When it applies ---

def test_a_brand_named_only_as_a_brand_is_its_brands_line_when_the_list_says_the_brand_sells_the_type(tmp_path):
    result = answer(tmp_path, lines=[entry()])
    assert FRYCO_LINE in picks(result) and "Fryco pans" not in ranked(result)
    assert FRYCO_LINE in result.ranked_as_lines
    pick = next(pick for pick in result.answer.picks if pick.name == FRYCO_LINE)
    # Every way its writers named it counts for the line: five credible voices.
    assert pick.breakdown.credible_recommends == 5
    # Shown as lines are: its maker's range page and its from price, from the brand-lines entry.
    assert pick.range is not None and pick.range.url == "https://fryco.example/pans"
    assert pick.price.from_price and pick.price.text.startswith("From £29.99 at Fryco")


def test_non_stick_written_apart_names_no_model_either(tmp_path):
    # "non stick" is how many writers spell "non-stick", which names no model (config.BRAND_MODEL_GENERIC_WORDS).
    library = write_library(tmp_path, {
        "1fry001": ("Best frying pan that lasts?", "Mine is peeling.", [
            praise("f1a", "Fryco non-stick pan", 6), praise("f1b", "Fryco non-stick pan", 7)]),
        "1fry002": ("Which non-stick frying pan lasts?", "Ten years, ideally.", [
            praise("f2a", "Fryco non stick pan", 8), praise("f2b", "Fryco non stick pan", 5)]),
    }, community="BuyItForLife")
    result = answer(tmp_path, lines=[entry(also_called=("Fryco non-stick",))], library=library)
    assert picks(result) == [FRYCO_LINE]


def test_under_a_must_have_the_line_is_left_out_as_a_whole_brand(tmp_path):
    # As every brand line is (10 Oct 2026): its other pans may be coated otherwise. Potco, with no brand-lines entry,
    # stays one product, kept with a note that we couldn't confirm it (the rule changes nothing for it).
    result = answer(tmp_path, request=PFAS_FREE, lines=[entry()])
    assert FRYCO_LINE not in picks(result) and FRYCO_LINE not in [i.name for i in result.answer.worth_a_look]
    assert NotSuited(FRYCO_LINE, WHOLE_BRAND) in result.left_out_not_suited
    assert "Potco pans" in picks(result)


def test_a_facts_entry_under_the_brands_own_name_speaks_for_the_line_as_greenpans_does(tmp_path):
    # An entry under the brand's name, alone or with only the type's words, says what all its pans are (late on 10 Oct
    # 2026: GreenPan's FAQ, all its pans PFAS-free): it names no one product, so the group is still the brand's line,
    # and the entry confirms the must-haves for it.
    result = answer(tmp_path, request=PFAS_FREE, lines=[entry()],
                    known=[facts("Fryco pans", pfas_free=True, non_stick=True)])
    assert picks(result)[0] == FRYCO_LINE
    assert result.answer.picks[0].cautions == []


# --- When it doesn't ---

def test_a_brand_with_no_brand_lines_entry_stays_as_it_is(tmp_path):
    result = answer(tmp_path, lines=[])
    assert {"Fryco pans", "Potco pans"} <= set(picks(result))
    assert result.ranked_as_lines == []


def test_a_brand_whose_entry_says_it_doesnt_sell_the_type_stays_as_it_is(tmp_path):
    result = answer(tmp_path, lines=[entry(sells=False)])
    assert "Fryco pans" in picks(result) and FRYCO_LINE not in ranked(result)


def test_a_group_naming_a_model_stays_that_product_whatever_the_list_says(tmp_path):
    # "Duoware" alone joined its one product named here, the Classic: the group names a model.
    result = answer(tmp_path, lines=[entry("Duoware", also_called=())])
    assert "Duoware Classic frying pan" in picks(result) and "Duoware frying pan line" not in ranked(result)


def test_a_facts_entry_naming_one_product_of_it_keeps_the_group_that_product(tmp_path):
    # The facts list reads writers' "Fryco pans" as its one product it knows, the Everyday: so it is shown, as before.
    result = answer(tmp_path, lines=[entry()], known=[facts("Fryco Everyday Frying Pan", non_stick=True)])
    assert "Fryco Everyday Frying Pan" in picks(result) and FRYCO_LINE not in ranked(result)


def test_a_price_entry_naming_one_product_of_it_keeps_the_group_that_product(tmp_path):
    price = Price(product="Fryco Everyday Frying Pan", category="kitchen", price=35.0, currency="GBP", shop="Panshop",
                  url="https://panshop.example/fryco-everyday", checked_on=TODAY, available=True,
                  product_type="frying pan")
    result = answer(tmp_path, lines=[entry()], prices=[price])
    assert "Fryco pans" in picks(result) and FRYCO_LINE not in ranked(result)


def test_brand_picks_switched_off_leave_brand_only_names_as_they_were(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "PIPELINE_BRAND_PICKS", False)
    result = answer(tmp_path, lines=[entry()])
    assert "Fryco pans" in picks(result) and FRYCO_LINE not in ranked(result)


def test_the_rule_has_a_switch(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "BRAND_ONLY_NAMES_AS_LINES", False)
    result = answer(tmp_path, lines=[entry()])
    assert "Fryco pans" in picks(result) and FRYCO_LINE not in ranked(result)


@pytest.mark.parametrize("request_", ["salicylic acid for acne"])
def test_an_ingredient_led_request_has_no_one_type_so_nothing_is_read_as_a_line(tmp_path, request_):
    # No requested type, no brand-lines entry to read a brand-only name by: the rule never applies.
    assert pipeline._brand_only_lines([], pipeline.parse_query(request_), [entry()], [], []) == []


# --- The committed lists: the names writers use in the library's frying-pan threads ---

def group_of_names(*names: str) -> ProductGroup:
    return ProductGroup(f"kitchen:{names[0].lower()}", names[0], "kitchen",
                        [ProductMention("1thread", f"c{n}", name, "kitchen", "recommend") for n, name in enumerate(names)])


@pytest.mark.parametrize("names, brand", [
    (("Circulon pans", "Circulon pan", "circulon"), "Circulon"),
    (("Zwilling/Ballarini non-stick pans", "Ballarini pans", "ballarini"), "Ballarini"),  # its co-brand name too
    (("OXO non-stick pan", "oxo non stick pans", "OXO non-stick", "Oxo non stick skillet"), "OXO"),
])
def test_b10s_brand_only_names_read_as_their_brands_lines(names, brand):
    group = group_of_names(*names)
    query = pipeline.parse_query(PFAS_FREE)
    line = pipeline._brand_line(group, query, load_brand_lines())
    assert line is not None and line.brand == brand and line.sells
    assert pipeline._names_only_its_brand(group, line, "frying pan")
    assert not pipeline._a_listed_product(group, line, "frying pan", load_prices(), load_product_facts())


def test_a_name_holding_a_model_of_the_brand_is_no_brand_only_name():
    line = pipeline._brand_line(group_of_names("Circulon pans"), pipeline.parse_query(PFAS_FREE), load_brand_lines())
    for name in ("Circulon Halo frying pan", "Circulon 12 inch pan", "Circulon or Ballarini pans", "Anolon pans"):
        assert not pipeline._names_only_its_brand(group_of_names("Circulon pans", name), line, "frying pan"), name


def test_a_brand_the_uk_knows_by_another_name_is_read_by_either(tmp_path):
    # Writers write "Breville"; the UK knows the brand as Sage (decision 12), whose entry the list has.
    library = write_library(tmp_path, {
        "1ket001": ("Best electric kettle that lasts?", "Mine died.", [
            praise("k1a", "Breville kettle", 6), praise("k1b", "Breville kettle", 7)]),
        "1ket002": ("Which electric kettle lasts?", "Ten years, ideally.", [
            praise("k2a", "Breville kettle", 8), praise("k2b", "breville", 5)]),
    }, community="BuyItForLife")
    sage = BrandLine(brand="Sage", category="kitchen", product_type="electric kettle", sells=True,
                     sources=["https://sage.example/kettles"], checked_on=TODAY, note="Made up for a test.")
    result = answer(tmp_path, request="electric kettle that lasts", lines=[sage], library=library)
    assert picks(result) == ["Sage electric kettle line"]


def test_a_brand_whose_line_is_already_in_the_answer_keeps_its_brand_only_product_as_it_is(tmp_path):
    # "Fryco" fits two models here (the Duo and the Trio), so module 4 already made it the Fryco line; the non-stick
    # group stays as it was (as OXO's non-stick pans next to the OXO line in b10's threads), and the existing rules fold
    # them when both are shown (pipeline._the_line_itself, _fold_brand_picks). Made a second "Fryco frying pan line",
    # it would be judged apart from the first and only joined to it afterwards (_one_per_name): under a must-have, one
    # of them could be kept by a facts entry under its own names and the other left out as a whole brand.
    library = write_library(tmp_path, {
        "1fry001": ("Best frying pan that lasts?", "Mine is peeling.", [
            praise("f1a", "fryco", 6), praise("f1b", "Fryco Duo pan", 7), praise("f1c", "Fryco non-stick pan", 4),
            praise("f1d", "Fryco non stick pan", 3)]),
        "1fry002": ("Which non-stick frying pan lasts?", "Ten years, ideally.", [
            praise("f2a", "fryco", 8), praise("f2b", "Fryco Trio pan", 5), praise("f2c", "Fryco non-stick pan", 5),
            praise("f2d", "Fryco", 4)]),
    }, community="BuyItForLife")
    result = answer(tmp_path, lines=[entry(also_called=("Fryco non-stick",))], library=library)
    assert "Fryco non-stick pan" in ranked(result) and ranked(result).count(FRYCO_LINE) <= 1
    # The one line is ranked, or stepped aside for its own product shown with it (as before this rule).
    assert FRYCO_LINE in ranked(result) or [f.name for f in result.folded_brand_picks] == [FRYCO_LINE]


def test_a_co_brands_first_name_written_alone_is_read_as_the_co_brand(tmp_path):
    # Module 4 joins a brand written alone to its one product named here: writers' "Zwilling" joined "Zwilling/Ballarini
    # non-stick pans" in b10's wider reading (Ballarini belongs to Zwilling). Read so, it is Ballarini's co-brand name
    # (the entry's also_called), as module 4 already counted it for that group.
    library = write_library(tmp_path, {
        "1fry001": ("Best frying pan that lasts?", "Mine is peeling.", [
            praise("f1a", "fryco", 6), praise("f1b", "Fryco pans", 7),
            praise("f1c", "Bigco/Fryco non-stick pans", 4)]),
        "1fry002": ("Which non-stick frying pan lasts?", "Ten years, ideally.", [
            praise("f2a", "Fryco pans", 8), praise("f2b", "Bigco", 5)]),
    }, community="BuyItForLife")
    result = answer(tmp_path, lines=[entry()], library=library)
    assert picks(result) == [FRYCO_LINE] and result.answer.picks[0].breakdown.credible_recommends == 5
