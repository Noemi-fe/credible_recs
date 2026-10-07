"""Module 1: the rules that read budget, size, SPF, lifespan and skin types straight out of a request."""

import pytest

from engine.query import Budget, Constraints, Size
from engine.query_rules import parse_budget, parse_min_years, parse_size, parse_skin_types, parse_spf

# --- Budget: limit words ---


@pytest.mark.parametrize(
    "text, expected",
    [
        ("cleanser under £30", Budget(max=30, currency="GBP")),
        ("kettle below 40 euros", Budget(max=40, currency="EUR")),
        ("serum for less than $25", Budget(max=25, currency="USD")),
        ("max 25 quid", Budget(max=25, currency="GBP")),
        ("up to €60", Budget(max=60, currency="EUR")),
        ("no more than 50 pounds", Budget(max=50, currency="GBP")),
    ],
)
def test_ceiling_words_set_a_max(text, expected):
    assert parse_budget(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("chef knife over £100", Budget(min=100, currency="GBP")),
        ("above 80 euros", Budget(min=80, currency="EUR")),
        ("more than $50", Budget(min=50, currency="USD")),
        ("at least 40 quid", Budget(min=40, currency="GBP")),
        ("from €30", Budget(min=30, currency="EUR")),
        ("no less than £20", Budget(min=20, currency="GBP")),  # not read as "less than"
    ],
)
def test_floor_words_set_a_min(text, expected):
    assert parse_budget(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("£20-£40", Budget(min=20, max=40, currency="GBP")),
        ("20-40 euros", Budget(min=20, max=40, currency="EUR")),
        ("$20 to $40", Budget(min=20, max=40, currency="USD")),
        ("between £20 and £40", Budget(min=20, max=40, currency="GBP")),
        ("from €20 to €40", Budget(min=20, max=40, currency="EUR")),
        ("between 20 and 40", Budget(min=20, max=40)),
        ("budget 20-40", Budget(min=20, max=40)),
    ],
)
def test_ranges_set_a_min_and_a_max(text, expected):
    assert parse_budget(text) == expected


def test_floor_and_ceiling_in_one_request():
    assert parse_budget("over £20 but under £50") == Budget(min=20, max=50, currency="GBP")


@pytest.mark.parametrize(
    "text, expected",
    [
        ("around £30", Budget(max=30, currency="GBP")),
        ("about 30 euros", Budget(max=30, currency="EUR")),
        ("~$30", Budget(max=30, currency="USD")),
    ],
)
def test_around_a_price_is_a_max(text, expected):
    assert parse_budget(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("£30 kettle", Budget(max=30, currency="GBP")),
        ("a 30 quid kettle", Budget(max=30, currency="GBP")),
        ("25€ cleanser", Budget(max=25, currency="EUR")),
    ],
)
def test_a_lone_price_is_a_max(text, expected):
    assert parse_budget(text) == expected


@pytest.mark.parametrize("text", ["£50+ chef knife", "a chef knife for £50 or more"])
def test_a_lone_price_with_a_plus_is_a_min(text):
    assert parse_budget(text) == Budget(min=50, currency="GBP")


# --- Budget: how prices are written ---


@pytest.mark.parametrize(
    "text, currency",
    [
        ("under £30", "GBP"),
        ("under 30£", "GBP"),
        ("under 30 gbp", "GBP"),
        ("under 30 pound", "GBP"),
        ("under 30 pounds", "GBP"),
        ("under 30 quid", "GBP"),
        ("under €30", "EUR"),
        ("under 30€", "EUR"),
        ("under 30 eur", "EUR"),
        ("under 30 euro", "EUR"),
        ("under 30 euros", "EUR"),
        ("under $30", "USD"),
        ("under 30$", "USD"),
        ("under usd 30", "USD"),
        ("under 30 dollars", "USD"),
        ("under 30 bucks", "USD"),  # Noemi, 7 Oct 2026: "bucks" means US dollars
    ],
)
def test_currency_written_before_or_after_the_number(text, currency):
    assert parse_budget(text) == Budget(max=30, currency=currency)


@pytest.mark.parametrize(
    "text, expected",
    [
        ("under £29.99", Budget(max=29.99, currency="GBP")),
        ("29,99€ cleanser", Budget(max=29.99, currency="EUR")),  # the European decimal comma
        ("under £1,200", Budget(max=1200, currency="GBP")),  # a thousands comma
        ("espresso machine under £1.5k", Budget(max=1500, currency="GBP")),
    ],
)
def test_decimals_thousands_and_k(text, expected):
    assert parse_budget(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("cleanser under 30", Budget(max=30)),
        ("budget 40", Budget(max=40)),
        ("max 25", Budget(max=25)),
        ("my budget is around 40", Budget(max=40)),
    ],
)
def test_bare_number_after_a_budget_word_has_no_currency(text, expected):
    assert parse_budget(text) == expected  # currency None: never guessed


@pytest.mark.parametrize(
    "text, expected",
    [
        ("burr grinder for pour over, 150 or less, im in the uk", Budget(max=150)),
        ("toaster, 40 tops", Budget(max=40)),
        ("£30 or less", Budget(max=30, currency="GBP")),
    ],
)
def test_ceiling_words_after_the_number(text, expected):
    assert parse_budget(text) == expected


@pytest.mark.parametrize("text", ["rice cooker for 4 or more people", "serves 4 max"])
def test_counts_before_or_more_and_max_are_not_a_budget(text):
    assert parse_budget(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "1.7l kettle",
        "50ml moisturiser",
        "10 inch skillet",
        "210mm gyuto",
        "5.5 qt dutch oven",
        "spf 50 sunscreen",
        "kettle that lasts 10+ years",
        "a pan to use for 5 years",
        "rice cooker for 2 people",
        "kettle 30",
        "skillet under 10 inch",
        "sunscreen at least spf 30",
        "pan under 2kg",
        "serum with at least 10% niacinamide",
        "kettle that holds up to 8 cups",
        "best kettle 2026",
        "gentle exfoliant for sensitive skin",
        "",
    ],
)
def test_other_numbers_are_not_a_budget(text):
    assert parse_budget(text) is None


@pytest.mark.parametrize(
    "text",
    [
        "moisturiser for women over 40",  # an age
        "I'm around 35 with dry skin",  # an age
        "best kettle from 2019",  # a year
    ],
)
def test_vague_budget_words_need_a_written_currency(text):
    assert parse_budget(text) is None


@pytest.mark.parametrize("text", ["UNDER £30", "Under 30 GBP", "under 30 quid!!"])
def test_budget_ignores_case_and_punctuation(text):
    assert parse_budget(text) == Budget(max=30, currency="GBP")


# --- Size ---


@pytest.mark.parametrize(
    "text, expected",
    [
        ("1.7L kettle", Size(value=1.7, unit="l")),
        ("1.7 litre kettle", Size(value=1.7, unit="l")),
        ("2 liters", Size(value=2, unit="l")),
        ("1,7l kettle", Size(value=1.7, unit="l")),
        ("50 ml", Size(value=50, unit="ml")),
        ("50ML moisturiser", Size(value=50, unit="ml")),
        ("50 millilitres", Size(value=50, unit="ml")),
        ("1.7 fl oz", Size(value=1.7, unit="fl oz")),
        ("1.7fl. oz cream", Size(value=1.7, unit="fl oz")),
        ("5.5 qt dutch oven", Size(value=5.5, unit="qt")),
        ("7 quart stock pot", Size(value=7, unit="qt")),
        ("10 inch skillet", Size(value=10, unit="in")),
        ("10-inch skillet", Size(value=10, unit="in")),
        ("10 inches", Size(value=10, unit="in")),
        ('8" chef knife', Size(value=8, unit="in")),
        ("12in pan", Size(value=12, unit="in")),
        ("20cm frying pan", Size(value=20, unit="cm")),
        ("210mm gyuto", Size(value=210, unit="mm")),
    ],
)
def test_size_with_its_unit_normalised(text, expected):
    assert parse_size(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "gentle exfoliant",
        "2-in-1 cleanser",  # a product type, not 2 inches
        "kettle under 30 in the uk",  # the word "in", not inches
        "spf 50 sunscreen",
        "kettle under £30",
        "a 5 lb skillet",  # a weight
        "",
    ],
)
def test_no_size(text):
    assert parse_size(text) is None


# --- SPF ---


@pytest.mark.parametrize(
    "text, expected",
    [
        ("SPF 50", 50),
        ("spf50 moisturiser", 50),
        ("spf 30+", 30),
        ("factor 50", 50),
        ("SPF-30 moisturiser", 30),
        ("a 50 spf sunscreen", 50),
    ],
)
def test_spf(text, expected):
    assert parse_spf(text) == expected


@pytest.mark.parametrize("text", ["sunscreen for my face", "spf 500", ""])  # no sunscreen has SPF 500
def test_no_spf(text):
    assert parse_spf(text) is None


# --- How many years it should last ---


@pytest.mark.parametrize(
    "text, expected",
    [
        ("kettle that lasts 10+ years", 10),
        ("10 years or more", 10),
        ("a pan that will last at least 5 years", 5),
        ("a knife for 20 years", 20),
        ("toaster that lasts 15 yrs", 15),
    ],
)
def test_min_years(text, expected):
    assert parse_min_years(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "best kettle 2026",  # a year, not a lifespan
        "a kettle that lasts years",  # no number
        "cleanser for 20 year olds",  # an age
        "",
    ],
)
def test_no_min_years(text):
    assert parse_min_years(text) is None


# --- Skin types ---


@pytest.mark.parametrize(
    "text, expected",
    [
        ("dry skin", ["dry"]),
        ("cleanser for sensitive skin", ["sensitive"]),
        ("for oily, acne-prone skin", ["oily", "acne-prone"]),
        ("acne prone skin", ["acne-prone"]),
        ("combo skin", ["combination"]),
        ("normal to dry skin", ["normal", "dry"]),
        ("mature skin", ["mature"]),
        ("very dry skin", ["dry"]),
        ("DRY SKIN", ["dry"]),
        ("my skin is oily and acne prone", ["oily", "acne-prone"]),
        ("skin type: combination", ["combination"]),
        ("I'm sensitive and dry", ["sensitive", "dry"]),
        ("im oily", ["oily"]),
        ("serum for breakouts", ["acne-prone"]),
        ("something for acne", ["acne-prone"]),
        ("cream for spots", ["acne-prone"]),
    ],
)
def test_skin_types(text, expected):
    assert parse_skin_types(text) == expected


def test_skin_types_keep_their_order_without_repeats():
    assert parse_skin_types("sensitive skin, also oily skin") == ["sensitive", "oily"]
    assert parse_skin_types("dry skin, really dry skin, acne-prone skin and acne scars") == ["dry", "acne-prone"]


@pytest.mark.parametrize(
    "text",
    [
        "towel that will dry quickly",
        "a normal kettle",
        "pan with no hot spots",
        "cleanser that won't dry out my skin",  # an effect to avoid, not the shopper's skin type
        "combination steam oven",
        "",
    ],
)
def test_skin_words_outside_skincare_phrasing_are_ignored(text):
    assert parse_skin_types(text) == []


# --- Mixed requests ---


@pytest.mark.parametrize(
    "text, budget, size, spf, min_years, skin_types",
    [
        ("1.7l kettle under £40", Budget(max=40, currency="GBP"), Size(value=1.7, unit="l"), None, None, []),
        ("spf 50 sunscreen below 20 euros", Budget(max=20, currency="EUR"), None, 50, None, []),
        ("chef knife 210mm around $100", Budget(max=100, currency="USD"), Size(value=210, unit="mm"), None, None, []),
        ("kettle that lasts 10+ years for under 50 quid", Budget(max=50, currency="GBP"), None, None, 10, []),
        ("moisturiser for dry, sensitive skin", None, None, None, None, ["dry", "sensitive"]),
    ],
)
def test_mixed_requests_read_every_constraint(text, budget, size, spf, min_years, skin_types):
    assert parse_budget(text) == budget
    assert parse_size(text) == size
    assert parse_spf(text) == spf
    assert parse_min_years(text) == min_years
    assert parse_skin_types(text) == skin_types
    # What the rules return fits the request's constraints as they are.
    Constraints(budget=budget, size=size, spf=spf, min_years=min_years, skin_types=skin_types)
