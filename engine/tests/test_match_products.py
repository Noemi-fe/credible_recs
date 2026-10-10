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


def test_a_size_in_inches_reads_the_same_with_or_without_the_unit():
    # Found reading b07, 10 Oct 2026 (late): 'Wusthof Classic 8" Chef Knife', '8" Wusthof chefs knife' and 'Wusthof classic
    # 8 inch' were apart (the word "inch" read as a word of the name), so no Wusthof model had two recommendations.
    assert normalize_name('Wusthof classic 8 inch') == normalize_name('Wusthof classic 8"') == ["wusthof", "classic", "8"]
    assert same_product('Wusthof Classic 8" Chef Knife', "Wusthof classic 8 inch")
    assert same_product('8" Wusthof chefs knife', "Wusthoff chefs knife 8 inches")
    assert not same_product("Lodge 10 inch skillet", 'Lodge 12" skillet')  # sizes still tell products apart
    assert "inch" in normalize_name("an inch of water")  # only after a number


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


# --- A brand written with and without its possessive "'s" (9 Oct 2026, gold scores with instructions v6) ---

def test_a_brand_alone_matches_its_possessive_form():
    # "FAB" (the AI) and "FAB's exfoliating pads" (Noemi) are the same product: the apostrophe is dropped, leaving "fabs".
    assert same_product("FAB", "FAB's exfoliating pads")
    assert not same_product("FAB", "Fable exfoliating pads")  # a longer word is another brand


def test_a_model_code_with_an_s_is_another_model():
    # "Q2" and "Q2S" are two grinders: the possessive rule is for brand words made of letters only.
    assert not same_product("Q2", "q2s")


# --- Splits found in the blind-test answers (10 Oct 2026): one product written several ways ---

@pytest.mark.parametrize("a, b", [
    ("House of Hurr Weightless Sunscreen", "House of Hur weightless sunscreen"),  # a letter doubled, in a short word
    ("Comandante C40", "Commandante C40"),
    ("Bioderma AKN Matt", "Bioderma AKN Mat"),
])
def test_a_doubled_letter_is_a_slip_even_in_a_short_word(a, b):
    assert same_product(a, b)


def test_a_doubled_digit_is_not_a_slip():
    # Model numbers differ by a digit: "Lido 2" and "Lido 22" would be two models.
    assert not same_product("Lido 2", "Lido 22")
    assert not same_product("Hario V60", "Hario V600")


@pytest.mark.parametrize("a, b", [
    ("Le Creseut", "Le Creuset"),  # letters moved further than one place
    ("Victoronix Fibrox", "Victorinox Fibrox"),
])
def test_letters_moved_within_three_neighbouring_places_are_a_slip(a, b):
    assert same_product(a, b)


def test_the_same_letters_moved_far_apart_are_not_a_slip():
    assert not same_product("Ginsu knife", "Gusin knife")  # the letters of positions 2 to 5 all moved


@pytest.mark.parametrize("a, b", [
    ("Commandante", "Comandante C40"),  # a misspelled brand alone
    ("Zojurushi", "Zojirushi kettle"),
    ("Kikumasamune Sake cream", "Kikumasamume Sake Skin Care Cream"),  # a slip and extra words together
    ("Beauty of Josen Green Plum cleanser", "Beauty of Joseon Green Plum Refreshing Cleanser"),
    ("The Ordinary's Advanced Retinoid", "The Ordinary Advanced Retinoid 2%"),  # a possessive "s"
])
def test_a_shorter_name_found_inside_a_longer_one_with_a_slip_is_the_same_product(a, b):
    assert same_product(a, b)
    assert same_product(b, a)


@pytest.mark.parametrize("a, b", [
    ("Timemore C2", "Timemore C2 Max"),  # the extra model word still makes another model
    ("Pyukang Yul Essence Toner", "Pyunkang Yul Nutrition Cream"),  # a misspelled brand, another product
    ("Dr Ceracle cream", "Dr Ceuracle kombucha essence"),
    ("Zojurushi kettle", "Zojirushi rice cooker"),
])
def test_a_slip_does_not_make_different_products_the_same(a, b):
    assert not same_product(a, b)


def test_non_before_a_model_word_says_which_model_it_is_not():
    # "1zpresso JX (non pro)" is the plain JX: "non pro" says it isn't the Pro.
    assert normalize_name("1zpresso JX (non-pro)") == ["1zpresso", "jx"]
    assert same_product("1zpresso JX (non pro)", "1zpresso JX")
    assert not same_product("1zpresso JX (non pro)", "1zpresso JX Pro")
    # Before any other word, "non" is part of the name: a non-foaming cleanser is not a foaming one.
    assert normalize_name("Aveeno non foaming cleanser") == ["aveeno", "non", "foaming", "cleanser"]


@pytest.mark.parametrize("a, b", [
    ("Black and Decker kettle", "Black & Decker kettle"),  # "&" is dropped as punctuation, so "and" is too
    ("Geek and Gorgeous Zero Feel SPF", "Geek & Gorgeous Zero Feel SPF 50"),
    ("Mary and May idebenone cream", "Mary & May Idebenone cream"),
])
def test_and_written_out_is_the_same_as_an_ampersand(a, b):
    assert same_product(a, b)
    assert same_product(b, a)


def test_and_still_separates_when_both_names_have_it():
    assert not same_product("Griswold and Wagner", "Lodge and Wagner")


# --- Short names written with a possessive, a slip, or one inside another (10 Oct 2026) ---

def test_a_short_name_with_a_possessive_is_spelled_out():
    aliases = make_aliases({"TO": "The Ordinary", "BoJ": "Beauty of Joseon"})
    assert product_words("TO's mandelic acid", aliases) == ["ordinary", "mandelic", "acid"]
    assert product_words("BoJ's Revive Eye Serum", aliases) == ["beauty", "of", "joseon", "revive", "eye", "serum"]
    # Without an apostrophe, an "s" after a model code is another model: the Q2S is not the Q2.
    assert product_words("Q2S", make_aliases({"Q2": "1Zpresso Q2"})) == ["q2s"]
    assert product_words("tos", aliases) == ["tos"]


def test_a_short_name_written_with_a_slip_is_spelled_out():
    aliases = make_aliases({"House of Hur weightless sunscreen": "House of Hur Weightless Sun Fluid"})
    assert product_words("House of Hurr Weightless Sunscreen", aliases) == ["house", "of", "hur", "weightless", "sun", "fluid"]


def test_a_spelled_out_name_can_hold_another_short_name():
    # "BoJ retinal eye cream": BoJ is Beauty of Joseon, and Beauty of Joseon's retinal eye cream is its Revive Eye
    # Serum (its only retinal eye product).
    aliases = make_aliases({"BOJ": "Beauty of Joseon",
                            "Beauty of Joseon retinal eye cream": "Beauty of Joseon Revive Eye Serum"})
    assert product_words("BoJ retinal eye cream", aliases) == ["beauty", "of", "joseon", "revive", "eye", "serum"]


@pytest.mark.parametrize("category, a, b", [
    ("kitchen", "Hario Mini-Slim (MSS-1)", "Hario slim"),  # the Slim is the Mini-Slim
    ("kitchen", "Virtuoso", "Baratza Virtuoso"),
    ("kitchen", "Fibrox", "Victorinox Fibrox"),
    ("kitchen", "Field Company", "Field"),
    ("skincare", "Kikumasamume Sake Skin Care Cream", "Kiku Sake cream"),
    ("skincare", "BoJ retinal eye cream", "Beauty of Joseon Revive Eye Serum: Retinal + Ginseng"),
    ("skincare", "BoJ's Revive Eye Serum", "Beauty of Joseon Revive Eye Serum: Retinal + Ginseng"),
    ("skincare", "House of Hurr Weightless Sunscreen", "House of Hur Weightless Sun Fluid"),
    ("skincare", "Etude soon jung cleansers", "Etude House Soon Jung foam cleanser"),
    ("skincare", "DDG peel pads", "Dr Dennis Gross peel pads"),
    ("skincare", "PC's BHA", "Paula's Choice 2% BHA Skin Perfecting Liquid"),
])
def test_the_shipped_short_names_found_in_the_blind_test_answers(category, a, b):
    assert same_product(a, b, load_aliases()[category])


def test_the_shipped_short_names_keep_other_models_apart():
    kitchen = load_aliases()["kitchen"]
    assert not same_product("Baratza Virtuoso Plus", "Virtuoso", kitchen)
    assert not same_product("Hario Slim Pro", "Hario Mini-Slim (MSS-1)", kitchen)
    skincare = load_aliases()["skincare"]
    assert not same_product("BoJ retinal eye cream", "Beauty of Joseon Dynasty Cream", skincare)


def test_retinal_and_retinol_are_never_a_slip():
    # From the library merges (10 Oct 2026): one letter apart, but two different retinoids.
    assert not same_product("Medik8 retinal", "Medik8 retinol")
    assert not same_product("Cera Ve retinal", "CeraVe resurfacing retinol serum")


def test_a_slip_in_the_first_word_of_a_shorter_name_is_only_forgiven_at_the_start_of_the_longer():
    # From the library merges (10 Oct 2026): "treitnoin .05" (tretinoin in general) isn't Obagi's tretinoin. The first
    # word of a name is most often its brand, so a slip in it is only forgiven where the longer name starts.
    assert not same_product("treitnoin .05", "Obagi 0.05% tretinoin cream")
    assert same_product("treitnoin .05", "tretinoin 0.05% cream")
    assert same_product("speedy oil cleaner", "Kose Speedy oil cleanser")  # a slip in a later word is forgiven


def test_refurbished_is_filler():
    # A refurbished unit is the same product (from the library: "Baratza Virtuoso+ (refurbished)", "refurbished Virtuoso").
    assert normalize_name("refurbished Virtuoso") == ["virtuoso"]
    assert same_product("refurbished Virtuoso", "Baratza Virtuoso", load_aliases()["kitchen"])


def test_a_short_name_already_written_out_with_a_slip_is_left_alone():
    # "Ettude Houde" is Etude House misspelled, not Etude followed by a word "houde".
    aliases = make_aliases({"Etude": "Etude House"})
    assert product_words("Ettude Houde", aliases) == ["ettude", "houde"]
    assert same_product("Ettude Houde", "Etude House", aliases)
