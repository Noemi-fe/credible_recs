"""Module 4's first, rules-only version: do two names, written by different people, mean the same product?

Noemi and the AI write product names their own way ("CeraVe SA" and "CeraVe Renewing SA Cleanser"), so the
extraction scores (engine/extraction_eval.py) need this to tell a renamed product from a different one.
"""

import pytest

from engine.match_products import normalize_name, same_product


# --- normalize_name ---

def test_names_become_lowercase_words_without_punctuation():
    # The apostrophe joins its word ("paulas"); other punctuation, like "%", separates words.
    assert normalize_name("Paula's Choice 2% BHA") == ["paulas", "choice", "2", "bha"]


def test_html_codes_become_their_characters_before_punctuation_is_dropped():
    # Reddit stores "&" as "&amp;": without turning it back, "amp" would look like a word of the name.
    assert normalize_name("Black &amp; Decker") == ["black", "decker"]


def test_a_leading_the_a_or_my_is_dropped():
    assert normalize_name("The Zojirushi") == ["zojirushi"]
    assert normalize_name("a Lodge skillet") == ["lodge", "skillet"]
    assert normalize_name("my Victorinox") == ["victorinox"]


def test_filler_words_that_are_not_part_of_a_name_are_dropped():
    assert normalize_name("the Victorinox one") == ["victorinox"]
    assert normalize_name("Le Creuset brand") == ["le", "creuset"]
    assert normalize_name("CeraVe and their SA cleanser") == ["cerave", "and", "sa", "cleanser"]


def test_an_a_inside_a_name_is_kept():
    # "Vitamin A" is a name, not filler: dropping the "a" would make it match "Vitamin C serum".
    assert normalize_name("Vitamin A serum") == ["vitamin", "a", "serum"]


def test_accents_are_dropped():
    assert normalize_name("Avène Cicalfate") == ["avene", "cicalfate"]


# --- same_product: the same product ---

@pytest.mark.parametrize("a, b", [
    ("Paula's Choice 2% BHA", "paulas choice 2 bha"),  # case and punctuation
    ("The Ordinary Niacinamide", "Ordinary Niacinamide"),  # a leading "the"
    ("Black &amp; Decker", "Black & Decker"),  # an HTML code
    ("Avène Cicalfate", "Avene Cicalfate"),  # an accent
    ("my Zojirushi one", "Zojirushi"),  # filler words
])
def test_names_that_are_equal_after_normalizing_are_the_same_product(a, b):
    assert same_product(a, b)


@pytest.mark.parametrize("a, b", [
    ("CeraVe SA", "CeraVe Renewing SA Cleanser"),
    ("SA cleanser", "CeraVe Renewing SA Cleanser"),  # two words or more need not start the longer name
    ("Zojirushi", "Zojirushi kettle"),  # one word: a brand that starts the longer name
])
def test_a_shorter_name_found_inside_a_longer_one_is_the_same_product(a, b):
    assert same_product(a, b)
    assert same_product(b, a)  # the order the names are given in doesn't matter


@pytest.mark.parametrize("a, b", [
    ("Zojirushi", "Zojurushi"),
    ("Zojirushi kettle", "Zojurushi kettle"),
    ("Victorinox Fibrox", "Victornox Fibrox"),  # a letter missing
    ("CeraVe SA cleanser", "CeraVe SA cleansers"),  # a plural is one letter away too
])
def test_one_letter_typos_in_long_words_are_forgiven(a, b):
    assert same_product(a, b)


# --- same_product: different products ---

@pytest.mark.parametrize("a, b", [
    ("CeraVe Hydrating Cleanser", "CeraVe SA Cleanser"),  # same brand, different products
    ("Paula's Choice 2% BHA", "Paula's Choice 2% AHA"),  # same brand, one short word apart
    ("Hario V60", "Hario V61"),  # typos aren't forgiven in short words: model names differ by one letter
    ("Zojirushi kettle", "Fellow kettle"),  # different brands, same product type
    ("Victorinox Fibrox", "Mercer Millennia"),  # nothing in common
])
def test_different_products_are_told_apart(a, b):
    assert not same_product(a, b)
    assert not same_product(b, a)


def test_a_single_word_that_does_not_start_the_longer_name_is_not_enough():
    # "kettle" alone names a kind of product, not this one.
    assert not same_product("kettle", "Zojirushi kettle")
    assert not same_product("cleanser", "CeraVe SA Cleanser")


def test_a_lone_number_is_not_a_brand():
    assert not same_product("10", "10 inch Lodge skillet")


def test_names_made_only_of_filler_words_match_nothing():
    assert not same_product("the one", "my one")
    assert not same_product("the one", "Zojirushi")
