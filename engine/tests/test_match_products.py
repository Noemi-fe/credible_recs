"""Module 4's first, rules-only version: do two names, written by different people, mean the same product?

Noemi and the AI write product names their own way ("CeraVe SA" and "CeraVe Renewing SA Cleanser"), so the
extraction scores (engine/extraction_eval.py) need this to tell a renamed product from a different one.
"""

import json

import pytest

from engine.config import MENTION_CATEGORIES
from engine.match_products import AliasError, load_aliases, make_aliases, normalize_name, product_words, same_product


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


# --- From the first gold-set scores (9 Oct 2026): the same product, written as a description ---

def test_by_and_from_are_filler():
    # "the weekly peeling solution by the ordinary" and "... from the ordinary" are the same product.
    assert normalize_name("weekly peeling solution by the ordinary") == ["weekly", "peeling", "solution", "ordinary"]
    assert same_product("the weekly peeling solution by the ordinary", "weekly peeling solution from the ordinary")


@pytest.mark.parametrize("a, b", [
    # Pairs that share most of their words but are different products, from the library (9 Oct 2026): a rule
    # merging names with most words in common was tried and dropped because of them.
    ("Round Lab Birch Juice Pads", "Round Lab birch juice cream"),
    ("Isntree Yam Root Vegan Milk Cleanser", "yam root vegan milk cream"),
    ("new Dynasty Cream by Beauty of Joseon", "old Dynasty Cream by Beauty of Joseon"),
    ("Shisheido Perfect Cleansing Oil blue bottle", "Shisheido Perfect Cleansing Oil transparent bottle"),
    ("Lodge 10 inch cast iron skillet", "Lodge 12 inch cast iron skillet"),
    ("Pharmaceris Mandelic acid 5%", "Pharmaceris Mandelic acid 10%"),
])
def test_names_sharing_most_words_can_still_be_different_products(a, b):
    assert not same_product(a, b)


# --- Module 4 proper (9 Oct 2026): edge cases from the brief, with names from the library ---

@pytest.mark.parametrize("a, b", [
    ("Timemore C2", "Timemore C2 Max"),  # a bigger model
    ("1zpresso JX", "1zpresso JX Pro"),  # the pro model
    ("Hario Skerton", "Hario Skerton Pro"),
    ("Aeropress", "Aeropress Go"),  # the travel model
    ("Porlex", "Porlex Mini"),
    ("Dynasty Cream by Beauty of Joseon", "new Dynasty Cream by Beauty of Joseon"),  # a new formula
    ("Mastercraft utility knife", "old Mastercraft utility knife"),  # an old version
])
def test_an_extra_model_or_version_word_makes_a_different_product(a, b):
    # Found inside the longer name, but the extra word names another model ("Max", "Pro") or another version of
    # the formula ("new", "old"), so the shorter name is not that product.
    assert not same_product(a, b)
    assert not same_product(b, a)


def test_a_model_word_both_names_share_does_not_split_them():
    assert same_product("Smart Grinder Pro", "Breville Smart Grinder Pro")
    assert same_product("C2 Max", "Timemore C2 Max")


@pytest.mark.parametrize("a, b", [
    ("TirTir Milk Skin Toner", "Tir Tir Milk Skin Toner"),
    ("1zpresso JMax", "1zpresso J-Max"),
    ("Allclad", "All-Clad"),
    ("Comfy Water Sunblock", "purito comfy water sun block"),  # spacing, inside a longer name
    ("Biore Watery Essence spf50", "Biore Watery Essence SPF 50"),
])
def test_a_word_written_as_one_or_split_in_two_is_the_same_word(a, b):
    assert same_product(a, b)
    assert same_product(b, a)


def test_joining_words_does_not_hide_a_real_difference():
    assert not same_product("Soon Jung cream", "SoonJung toner")
    assert not same_product("Lido 2", "Lido 3")


@pytest.mark.parametrize("a, b", [
    ("Cosrx snail cream", "Corsx snail cream"),  # two neighbouring letters swapped
    ("Le Creuset", "Le Crueset"),
    ("Lodge cast iron pan", "Lodge cast iron pans"),  # a plural, even of a short word
    ("Urbanic 070", "urbanic 070s"),
])
def test_swapped_letters_and_plurals_are_forgiven(a, b):
    assert same_product(a, b)


def test_swapped_letters_in_short_words_are_not_forgiven():
    assert not same_product("Hario V60", "Hario 6V0")


# --- Aliases: short names people use for a brand or a product, spelled out before comparing ---

ALIASES = make_aliases({"TO": "The Ordinary", "Sage": "Breville", "C2": "Timemore C2", "LRP": "La Roche-Posay"})


@pytest.mark.parametrize("a, b", [
    ("TO lactic acid", "The Ordinary Lactic Acid 10% + HA"),  # a brand's initials
    ("LRP", "La Roche Posay"),
    ("sage smart grinder pro", "Breville Smart Grinder Pro"),  # the UK and EU name of the same brand
    ("C2", "Timemore C2"),  # a model name written without its brand
])
def test_a_known_short_name_is_spelled_out_before_comparing(a, b):
    assert same_product(a, b, ALIASES)
    assert not same_product(a, b)  # without the list, words alone can't tell


def test_a_short_name_is_only_spelled_out_at_the_start_of_a_name():
    # "to" is also an everyday word: in "Cream to Foam" it is not The Ordinary.
    assert product_words("CeraVe Cream to Foam cleanser", ALIASES) == ["cerave", "cream", "to", "foam", "cleanser"]
    assert product_words("TO sunscreen", ALIASES) == ["ordinary", "sunscreen"]


def test_a_short_name_already_written_out_is_left_alone():
    # The model "C2" spelled out is "Timemore C2"; a name that already says Timemore isn't changed.
    assert product_words("Timemore C2", ALIASES) == ["timemore", "c2"]
    assert product_words("C2 Max", ALIASES) == ["timemore", "c2", "max"]


def test_the_shipped_alias_list_loads_for_every_category():
    aliases = load_aliases()
    assert set(aliases) == set(MENTION_CATEGORIES)
    assert same_product("TO niacinamide", "The Ordinary Niacinamide 10% and Zinc 1%", aliases["skincare"])


def test_an_alias_file_with_a_short_name_twice_is_refused(tmp_path):
    path = tmp_path / "aliases.json"
    path.write_text(json.dumps({"products": {"skincare": [
        {"short": "TO", "full": "The Ordinary", "seen": []},
        {"short": "to", "full": "Tatcha Overnight", "seen": []},
    ]}}))
    with pytest.raises(AliasError, match="to"):
        load_aliases(path)


def test_a_short_name_written_out_with_a_space_is_left_alone():
    # "Elta MD" is EltaMD written in two words: it must not become "eltamd md".
    aliases = make_aliases({"Elta": "EltaMD"})
    assert product_words("Elta MD UV Clear", aliases) == ["elta", "md", "uv", "clear"]
    assert same_product("Elta", "EltaMD UV Clear", aliases)


@pytest.mark.parametrize("a, b", [
    # From the library (9 Oct 2026): the shorter name is found inside the longer, but the two end in different kinds
    # of product, so they are different products.
    ("Cerave cream", "CeraVe Cream to Foam cleanser"),
    ("CeraVe moisturizer", "Cerave moisturizer cleanser"),
])
def test_names_ending_in_different_kinds_of_product_are_different_products(a, b):
    assert not same_product(a, b)
    assert not same_product(b, a)


def test_the_same_kind_of_product_at_the_end_still_matches():
    assert same_product("La Roche Posay sunscreen", "La Roche Posay 50+ face sunscreen")
    assert same_product("Lodge cast iron pan", "Lodge cast iron pans")
    assert same_product("CeraVe cleanser", "CeraVe cleanser (blue label)")  # "label" is not a kind of product


def test_a_slip_must_keep_the_first_letter():
    # From the library (9 Oct 2026): "Vario" is a Baratza grinder, not "Hario" misspelled. People rarely mistype
    # the first letter of a name, and names that differ only there are often two brands.
    assert not same_product("Hario", "Vario")
    assert same_product("Fonex", "Finex")
