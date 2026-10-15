"""Module 4, grouping: every mention of one product, across threads, gathered under one name.

Names are made up or copied from the library's product names (names only, never comment text).
"""

import random

from engine import config
from engine.extract import CheckResult, ExtractedMention
from engine.group_products import (
    ProductMention, brand_pick_name, group_of, group_products, mentions_from_checked, plural, uk_name,
)
from engine.match_products import load_aliases, make_aliases
from engine.query import PRODUCT_TYPES

NO_ALIASES = {"skincare": {}, "kitchen": {}, "other": {}}


def mention(product: str, thread_id: str = "1fake01", comment_id: str = "c1aaaa", category: str = "skincare",
            stance: str = "recommend") -> ProductMention:
    return ProductMention(thread_id=thread_id, comment_id=comment_id, product=product, category=category, stance=stance)


def kitchen(product: str, comment_id: str = "c1aaaa", thread_id: str = "1fake01") -> ProductMention:
    return mention(product, thread_id, comment_id, category="kitchen")


def group(mentions, aliases=NO_ALIASES):
    return group_products(mentions, aliases)


def names_by_group(groups) -> list[set[str]]:
    return sorted((sorted({m.product for m in g.mentions}) for g in groups), key=lambda names: names[0])


# --- One product, several names ---

def test_one_product_named_three_ways_in_two_threads_is_one_group():
    groups = group([
        mention("CeraVe SA Cleanser", "1fake01"),
        mention("cerave sa cleanser", "1fake02"),
        mention("CeraVe Renewing SA Cleanser", "1fake02", "c2bbbb"),
    ])
    assert len(groups) == 1
    assert groups[0].category == "skincare"
    assert len(groups[0].mentions) == 3
    assert not groups[0].loose


def test_different_products_are_different_groups():
    groups = group([mention("CeraVe SA Cleanser"), mention("CeraVe Hydrating Cleanser"), mention("Paula's Choice 2% BHA")])
    assert len(groups) == 3


def test_every_mention_lands_in_exactly_one_group():
    mentions = [mention(name, comment_id=f"c{i}") for i, name in enumerate(
        ["CeraVe", "CeraVe SA Cleanser", "CeraVe Hydrating Cleanser", "cerave", "the one", "Vaseline"])]
    groups = group(mentions)
    grouped = [m for g in groups for m in g.mentions]
    assert sorted(grouped, key=repr) == sorted(mentions, key=repr)


def test_the_same_name_in_two_categories_is_two_groups():
    groups = group([kitchen("IKEA"), mention("IKEA", category="other")])
    assert sorted(g.category for g in groups) == ["kitchen", "other"]


# --- Brands and loose names never join two products (same_product is not transitive) ---

def test_a_brand_alone_does_not_join_two_products_of_that_brand():
    # "CeraVe" matches both cleansers, which don't match each other: it stays a group of its own, flagged loose.
    groups = group([mention("CeraVe"), mention("CeraVe SA Cleanser"), mention("CeraVe Hydrating Cleanser"), mention("cerave")])
    assert names_by_group(groups) == [["CeraVe", "cerave"], ["CeraVe Hydrating Cleanser"], ["CeraVe SA Cleanser"]]
    loose = [g for g in groups if g.loose]
    assert [g.name for g in loose] == ["CeraVe"]


def test_a_brand_alone_joins_the_only_product_of_that_brand_around():
    groups = group([kitchen("Lodge"), kitchen("Lodge 12 inch skillet")])
    assert len(groups) == 1
    assert not groups[0].loose


def test_a_loose_name_does_not_join_two_products_it_fits():
    # "CeraVe cleanser" fits both cleansers: it can't count for either.
    groups = group([mention("CeraVe cleanser"), mention("CeraVe SA Cleanser"), mention("CeraVe Hydrating Cleanser")])
    assert len(groups) == 3
    assert [g.name for g in groups if g.loose] == ["CeraVe cleanser"]


def test_a_name_without_a_size_does_not_join_two_sizes():
    groups = group([kitchen("Lodge skillet"), kitchen("Lodge 10 inch skillet"), kitchen("Lodge 12 inch skillet")])
    assert names_by_group(groups) == [["Lodge 10 inch skillet"], ["Lodge 12 inch skillet"], ["Lodge skillet"]]


def test_a_brand_alone_does_not_chain_through_a_looser_name():
    # Lodge fits a combo cooker and two skillets; "Lodge cast iron" fits both skillets. Neither joins anything.
    groups = group([kitchen(n) for n in ("Lodge", "Lodge combo cooker", "Lodge cast iron", "Lodge cast iron skillet 10 inch",
                                          "Lodge cast iron skillet 12 inch")])
    assert len(groups) == 5
    assert sorted(g.name for g in groups if g.loose) == ["Lodge", "Lodge cast iron"]


def test_model_and_formula_variants_stay_apart():
    groups = group([kitchen("Timemore C2"), kitchen("Timemore C2 Max"), mention("Beauty of Joseon Dynasty Cream"),
                    mention("new Dynasty Cream by Beauty of Joseon"), mention("old Dynasty Cream by Beauty of Joseon")])
    assert len(groups) == 5


def test_a_name_made_only_of_filler_words_is_a_loose_group_of_its_own():
    groups = group([mention("the one"), mention("CeraVe SA Cleanser")])
    assert len(groups) == 2
    assert [g.name for g in groups if g.loose] == ["the one"]


# --- Known short names ---

def test_known_short_names_join_their_full_names():
    aliases = {**NO_ALIASES, "skincare": make_aliases({"TO": "The Ordinary"}), "kitchen": make_aliases({"Sage": "Breville"})}
    groups = group([mention("TO lactic acid"), mention("The Ordinary Lactic Acid"), kitchen("sage smart grinder pro"),
                    kitchen("Breville Smart Grinder Pro")], aliases)
    assert sorted(g.name for g in groups) == ["Breville Smart Grinder Pro", "The Ordinary Lactic Acid"]


def test_the_shipped_alias_list_is_used_by_default():
    groups = group_products([mention("LRP sunscreen"), mention("La Roche-Posay sunscreen")])
    assert len(groups) == 1


def test_short_names_only_apply_within_their_category():
    aliases = {**NO_ALIASES, "skincare": make_aliases({"TO": "The Ordinary"})}
    groups = group([kitchen("TO lactic acid"), kitchen("The Ordinary Lactic Acid")], aliases)
    assert len(groups) == 2


# --- The name shown, and the key ---

def test_the_name_shown_is_the_one_written_most_often():
    groups = group([kitchen("Differin", comment_id=f"c{i}") for i in range(3)] + [kitchen("Differin gel")])
    assert groups[0].name == "Differin"


def test_on_a_tie_the_more_complete_name_is_shown():
    groups = group([mention("CeraVe SA cleanser"), mention("CeraVe Renewing SA Cleanser")])
    assert groups[0].name == "CeraVe Renewing SA Cleanser"


def test_a_more_complete_name_written_at_least_half_as_often_is_shown():
    # The brand alone is written twice, the product once: the product's name says more.
    groups = group([mention("Sunday Riley"), mention("Sunday Riley", comment_id="c2"), mention("Sunday Riley water cream")])
    assert groups[0].name == "Sunday Riley water cream"
    # A description written once doesn't beat a name written ten times.
    groups = group([kitchen("Timemore C2", comment_id=f"c{i}") for i in range(10)] + [kitchen("Timemore C2 with titanium coated burrs")])
    assert groups[0].name == "Timemore C2"


def test_the_brand_goes_first_when_some_name_gives_it():
    # "JX Pro" is written most often, but "1Zpresso JX Pro" says whose it is.
    groups = group([kitchen("JX Pro", comment_id=f"c{i}") for i in range(3)] + [kitchen("1Zpresso JX Pro")])
    assert groups[0].name == "1Zpresso JX Pro"


def _stagg(*more):
    """The kettle answer's case (10 Oct 2026): "Stagg" written most often, the brand only in a longer name."""
    return group([kitchen("Stagg", comment_id=f"c{i}") for i in range(4)]
                 + [kitchen("Stagg EKG", comment_id="c5"), kitchen("Fellow Stagg EKG", comment_id="c6")]
                 + [kitchen(name, comment_id=f"d{i}") for i, name in enumerate(more)])


def test_the_brand_goes_first_when_only_a_longer_name_gives_it():
    # No name is "Stagg" with only words before it, but "Fellow Stagg EKG" puts "Fellow" before it, and "Fellow" is
    # written on its own elsewhere (a brand): shown "Fellow Stagg", not a bare "Stagg" a shopper can't place.
    groups = _stagg("Fellow", "Fellow Corvo EKG")
    stagg = next(g for g in groups if "Stagg" in g.names)
    assert (stagg.name, stagg.key, stagg.loose) == ("Fellow Stagg", "kitchen:fellow stagg", False)
    assert sorted(stagg.names) == ["Fellow Stagg EKG", "Stagg", "Stagg EKG"]  # the name changes, the group doesn't


def test_words_before_the_name_count_as_a_brand_only_when_written_on_their_own():
    # Nobody writes "Fellow" alone here, so nothing says it's a brand rather than a describing word.
    assert next(g for g in _stagg() if "Stagg" in g.names).name == "Stagg"
    # A size before the name: '12"' is never a product of its own.
    groups = group([kitchen("De Buyer", comment_id=f"c{i}") for i in range(3)]
                   + [kitchen('12" De Buyer carbon steel crepe pan', comment_id="c4")])
    assert groups[0].name == "De Buyer"


def test_a_brand_put_first_never_takes_another_groups_name():
    # "Fellow Stagg" is written too, and fits two products, so it is a loose group of its own. The "Stagg" group then
    # shows its own name that starts with the brand, so no two groups share a name or a key.
    groups = _stagg("Fellow", "Fellow Corvo EKG", "Fellow Stagg", "Fellow Stagg electric kettle")
    stagg = next(g for g in groups if "Stagg" in g.names)
    assert stagg.name == "Fellow Stagg EKG"
    assert len({g.key for g in groups}) == len(groups)
    assert len({g.name.lower() for g in groups}) == len(groups)


def test_the_spelling_shown_is_the_most_common_and_a_short_name_is_shown_written_out():
    aliases = {**NO_ALIASES, "skincare": make_aliases({"TO": "The Ordinary"})}
    groups = group([mention("TO lactic acid"), mention("TO lactic acid", comment_id="c2"), mention("The Ordinary lactic acid"),
                    mention("lodge", category="kitchen"), mention("Lodge", category="kitchen"),
                    mention("Lodge", category="kitchen", comment_id="c2")], aliases)
    assert sorted(g.name for g in groups) == ["Lodge", "The Ordinary lactic acid"]


def test_keys_name_the_category_and_the_product():
    groups = group([mention("CeraVe SA Cleanser"), kitchen("Lodge")])
    assert sorted(g.key for g in groups) == ["kitchen:lodge", "skincare:cerave sa cleanser"]


def test_grouping_does_not_depend_on_the_order_of_the_mentions():
    mentions = [mention(n, comment_id=f"c{i}") for i, n in enumerate(
        ["CeraVe", "CeraVe SA Cleanser", "cerave sa cleanser", "CeraVe Hydrating Cleanser", "CeraVe cleanser", "Vaseline",
         "vaseline", "CeraVe Renewing SA Cleanser"])]
    expected = [(g.key, g.name, g.loose, sorted(g.mentions, key=repr)) for g in group(mentions)]
    for seed in range(5):
        shuffled = mentions[:]
        random.Random(seed).shuffle(shuffled)
        assert [(g.key, g.name, g.loose, sorted(g.mentions, key=repr)) for g in group(shuffled)] == expected


def test_groups_come_biggest_first():
    groups = group([mention("Vaseline"), mention("CeraVe SA Cleanser"), mention("CeraVe SA Cleanser", comment_id="c2")])
    assert [len(g.mentions) for g in groups] == [2, 1]


def test_a_group_counts_its_stances():
    groups = group([mention("Vaseline"), mention("Vaseline", comment_id="c2", stance="warn"), mention("vaseline", comment_id="c3")])
    assert groups[0].stances == {"recommend": 2, "warn": 1}


# --- From the checked extractions ---

def test_mentions_come_from_the_kept_mentions_of_every_thread():
    kept = ExtractedMention(comment_id="c1aaaa", product="CeraVe SA Cleanser", category="skincare", stance="recommend", quote="q")
    dropped = ExtractedMention(comment_id="c9zzzz", product="Fake", category="skincare", stance="warn", quote="q")
    checked = {"1fake01": CheckResult(kept=[kept], rejected=[(dropped, "quote not found")])}
    assert mentions_from_checked(checked) == [
        ProductMention(thread_id="1fake01", comment_id="c1aaaa", product="CeraVe SA Cleanser", category="skincare", stance="recommend")
    ]


def test_a_misspelling_does_not_let_a_name_join_two_products():
    # From the library (9 Oct 2026): "lodge pan" fits a Lodge carbon steel pan, and its plural "Lodge pans" fits the
    # Lodge cast iron pans. Spellings of one name are judged together, so "lodge pan" is loose and joins neither.
    groups = group([kitchen("lodge pan"), kitchen("Lodge pans"), kitchen("lodge 12 inch carbon steel fry pan"),
                    kitchen("Lodge cast iron pans")])
    assert names_by_group(groups) == [["Lodge cast iron pans"], ["Lodge pans", "lodge pan"], ["lodge 12 inch carbon steel fry pan"]]
    assert [g.name for g in groups if g.loose] == ["lodge pan"]



# --- For the pipeline: each mention's product key and shown name (engine.rank.ScoredMention) ---

def test_each_mention_can_be_looked_up_to_its_group():
    mentions = [mention("CeraVe SA Cleanser"), mention("cerave sa cleanser", "1fake02"), mention("Vaseline", comment_id="c2")]
    groups = group(mentions)
    lookup = group_of(groups)
    assert set(lookup) == set(mentions)
    assert lookup[mentions[1]].key == "skincare:cerave sa cleanser"
    assert lookup[mentions[1]].name == "CeraVe SA Cleanser"
    assert lookup[mentions[2]].name == "Vaseline"


# --- Instructions v6 (9 Oct 2026): the AI's product type rides along with each mention ---

def test_a_mention_carries_the_ais_product_type_from_the_checked_extractions():
    typed = ExtractedMention(comment_id="c1aaaa", product="CeraVe SA Cleanser", category="skincare", stance="recommend",
                             quote="q", product_type="cleanser")
    untyped = ExtractedMention(comment_id="c2bbbb", product="Vaseline", category="skincare", stance="recommend", quote="q")
    mentions = mentions_from_checked({"1fake01": CheckResult(kept=[typed, untyped])})
    assert [m.product_type for m in mentions] == ["cleanser", None]


def test_the_product_type_does_not_change_which_mention_is_which():
    # The pipeline looks mentions up by thread, comment, name, category and stance; the type is extra information.
    typed = ProductMention("1fake01", "c1aaaa", "CeraVe SA Cleanser", "skincare", "recommend", product_type="cleanser")
    plain = mention("CeraVe SA Cleanser")
    assert typed == plain and hash(typed) == hash(plain)
    assert group_of(group([typed]))[plain].name == "CeraVe SA Cleanser"
    assert group([typed])[0].mentions[0].product_type == "cleanser"

# --- The name shown to the shopper (decisions 9 and 12, Noemi, 9 Oct 2026) ---

def test_the_uk_name_sage_is_shown_rather_than_breville():
    # Sage is Breville's UK and EU brand. Grouping keeps its own name; the shown name uses the UK brand.
    assert uk_name("Breville Smart Grinder Pro") == "Sage Smart Grinder Pro"
    assert uk_name("breville bambino") == "Sage bambino"
    assert uk_name("my Breville's kettle") == "my Sage's kettle"
    assert uk_name("Zojirushi kettle") == "Zojirushi kettle"
    assert uk_name("Brevilleish Kettle") == "Brevilleish Kettle"  # whole words only


def test_the_uk_names_come_from_the_config():
    assert config.UK_BRAND_NAMES == {"Breville": "Sage"}
    assert uk_name("Fellow Stagg", {"Fellow": "Made-up UK Brand"}) == "Made-up UK Brand Stagg"


def test_a_brand_pick_says_which_products_it_means():
    # Changed on purpose 12 Oct 2026 (Noemi's wording, from testing the demo: "L'Oreal hair oil serum line"): a brand
    # pick is the brand's line of the requested type, "<Brand> <product type> line"; it was "Lodge (their cast iron
    # skillets)".
    assert brand_pick_name("Lodge", "cast iron skillet") == "Lodge cast iron skillet line"
    assert brand_pick_name("Zojirushi", "electric kettle") == "Zojirushi electric kettle line"
    assert brand_pick_name("Victorinox", "chef knife") == "Victorinox chef knife line"
    assert brand_pick_name("Paula's Choice", "exfoliant") == "Paula's Choice exfoliant line"
    assert brand_pick_name("Nizoral", "shampoo") == "Nizoral shampoo line"
    assert brand_pick_name("Le Creuset", "dutch oven") == "Le Creuset Dutch oven line"  # as a name writes the type


def test_a_product_type_the_open_model_names_gets_a_plural_too():
    # Types module 1 doesn't list (the open model's, 11 Oct 2026) follow English's usual rules.
    # Changed on purpose 14 Oct 2026 (kitchen appliances, Noemi's decision 3): the air fryer, the French press and the
    # rice cooker are module 1's own types now, with their plurals in config.PRODUCT_TYPE_PLURALS ("French presses");
    # a garlic press, a sandwich press and a bread maker take their places here.
    for product_type, plural_ in [("bread maker", "bread makers"), ("dish brush", "dish brushes"), ("zester", "zesters"),
                                  ("garlic press", "garlic presses"), ("wok", "woks"),
                                  ("sandwich press", "sandwich presses")]:
        assert plural(product_type) == plural_
    # Changed on purpose 12 Oct 2026 (Noemi's wording): a brand pick names the type itself, "<Brand> <type> line",
    # so the plural is no longer part of its name (it was "Ninja (their air fryers)").
    assert brand_pick_name("Ninja", "air fryer") == "Ninja air fryer line"
    assert brand_pick_name("Zojirushi", "rice cooker") == "Zojirushi rice cooker line"


def test_every_product_type_has_a_plural():
    assert set(config.PRODUCT_TYPE_PLURALS) == {p.name for p in PRODUCT_TYPES}
    assert config.PRODUCT_TYPE_PLURALS["chef knife"] == "chef knives"
    assert config.PRODUCT_TYPE_PLURALS["dutch oven"] == "Dutch ovens"
    # Changed on purpose 14 Oct 2026 (the general category): a type named in the plural ("headphones", "jeans") or as a
    # mass noun ("underwear", "garden furniture") is its own plural (engine/data/product_types.json); every other type's
    # plural differs from its name and ends in "s", as module 1's first types' all do.
    plural_names = {entry["name"] for entry in config.MORE_PRODUCT_TYPES if entry["plural"] == entry["name"]}
    assert {"headphones", "jeans", "underwear", "garden furniture"} <= plural_names
    irregular = {"mouse": "computer mice"}  # read as "We haven't read Reddit about computer mice yet"
    for name, plural in config.PRODUCT_TYPE_PLURALS.items():
        if name in irregular:
            assert plural == irregular[name]
        elif name not in plural_names:
            assert plural.lower() != name.lower() and plural.endswith("s"), name


def test_a_brand_pick_name_that_already_says_the_type_has_no_bracket():
    # Noemi, 9 Oct 2026: "CeraVe cleanser (their cleansers)" reads oddly; the name already says what it is.
    # Changed on purpose 12 Oct 2026 (Noemi's wording): the same holds for "<Brand> <type> line", never "CeraVe cleanser
    # cleanser line".
    # Changed on purpose 13 Oct 2026 (Noemi's decision 3 of 13 Oct, replacing the 9 Oct rule): every brand line is shown
    # as "<Brand> <type> line", also when its name already holds the type; the type is said once.
    assert brand_pick_name("CeraVe cleanser", "cleanser") == "CeraVe cleanser line"
    assert brand_pick_name("Lodge cast iron", "cast iron skillet") == "Lodge cast iron skillet line"
    assert brand_pick_name("Lodge", "cast iron skillet") == "Lodge cast iron skillet line"
    assert brand_pick_name("Davines conditioner", "conditioner") == "Davines conditioner line"
    assert brand_pick_name("Ninja electric kettle", "electric kettle") == "Ninja electric kettle line"
    assert brand_pick_name("Sage kettle", "electric kettle") == "Sage electric kettle line"
    assert brand_pick_name("Herbal Essences shampoos", "shampoo") == "Herbal Essences shampoo line"
    assert brand_pick_name("Lodge cast iron pan", "cast iron skillet") == "Lodge cast iron skillet line"
    assert brand_pick_name("Cuisinart stainless kettle", "electric kettle") == "Cuisinart stainless electric kettle line"
    # Only the ending that says the type gives way: a line's own words stay.
    assert brand_pick_name("Aussie Miracle Curls shampoo", "shampoo") == "Aussie Miracle Curls shampoo line"
    assert brand_pick_name("Haden brand electric kettle", "electric kettle") == "Haden electric kettle line"


def test_a_brand_pick_name_never_says_part_of_its_type_twice():
    # Found measuring 27 answers on 12 Oct 2026: a line name ending in part of the type (or a plural or slip of it) would
    # say it twice once the type is added ("Zojirushi cooker rice cooker line"). Those last words give way to the type.
    assert brand_pick_name("Zojirushi cooker", "rice cooker") == "Zojirushi rice cooker line"
    assert brand_pick_name("KitchenAid processor", "food processor") == "KitchenAid food processor line"
    assert brand_pick_name("Torriden Ceramide Lip", "lip balm") == "Torriden Ceramide lip balm line"
    assert brand_pick_name("8 inch Victorinox chefs", "chef knife") == "8 inch Victorinox chef knife line"
    assert brand_pick_name("Ouai shanpoo", "shampoo") == "Ouai shampoo line"  # a writer's slip for "shampoo"
    # Changed on purpose 13 Oct 2026 (Noemi's decision 3 of 13 Oct): "pans" says the type, so it gives way to it; it was
    # shown as it is, "Lodge pans".
    assert brand_pick_name("Lodge pans", "frying pan") == "Lodge frying pan line"
    # Other last words stay.
    assert brand_pick_name("Hario Mini", "coffee grinder") == "Hario Mini coffee grinder line"
    assert brand_pick_name("Lodge pans", "cast iron skillet") == "Lodge pans cast iron skillet line"


# --- A loose name that is one product's name but for the word "skin" (10 Oct 2026) ---

def test_a_loose_name_joins_the_product_it_names_but_for_the_word_skin():
    # From the library: "Cetaphil gentle cleanser" fits the Gentle Skin Cleanser and the Gentle Foaming Cleanser, but
    # it is the first one's name without "skin", which says nothing about which product it is.
    groups = group([mention("cetaphil gentle cleanser"), mention("Cetaphil gentle cleanser", "1fake02"),
                    mention("Cetaphil Gentle Skin Cleanser", "1fake03"), mention("Cetaphil gentle foaming cleanser", "1fake04")])
    assert names_by_group(groups) == [["Cetaphil Gentle Skin Cleanser", "Cetaphil gentle cleanser", "cetaphil gentle cleanser"],
                                      ["Cetaphil gentle foaming cleanser"]]
    assert not any(g.loose for g in groups)


def test_skin_never_joins_two_products():
    # Without the loose name, the two cleansers stay apart, and "skin" doesn't bring a third product into either.
    groups = group([mention("Cetaphil Gentle Skin Cleanser"), mention("Cetaphil gentle foaming cleanser", "1fake02")])
    assert len(groups) == 2
    groups = group([mention("CeraVe cleanser"), mention("CeraVe SA cleanser", "1fake02"),
                    mention("CeraVe Hydrating Cleanser", "1fake03")])
    assert [g.name for g in groups if g.loose] == ["CeraVe cleanser"]  # no name equals it but for "skin"


def test_a_brand_written_with_its_full_name_joins_the_brand():
    # From the library: "Field Company" is the brand Field (shipped short names), which makes skillets in several
    # sizes, so both are the brand, not one of its skillets.
    groups = group([kitchen("Field 10in"), kitchen("Field 8in", "c2"), kitchen("Field", "c3"), kitchen("Field Company", "c4")],
                   load_aliases())
    assert names_by_group(groups) == [["Field", "Field Company"], ["Field 10in"], ["Field 8in"]]
    assert [g.name for g in groups if g.loose] == ["Field"]


def test_the_name_shown_is_one_written_as_the_product_is_known():
    # From the library merges (10 Oct 2026): a name written out through a short name or a slip ("House of Hurr
    # Weightless Sunscreen") is not shown when a name says the product's words as they are.
    aliases = {"skincare": make_aliases({"House of Hur weightless sunscreen": "House of Hur Weightless Sun Fluid"})}
    groups = group([mention("House of Hurr Weightless Sunscreen"), mention("House of Hurr Weightless Sunscreen", "1fake02"),
                    mention("House of Hur Weightless Sun Fluid", "1fake03")], aliases)
    assert [g.name for g in groups] == ["House of Hur Weightless Sun Fluid"]
    # As before, the full name rather than a short one: "The Ordinary", not "TO".
    groups = group([mention("TO"), mention("TO", "1fake02"), mention("The Ordinary", "1fake03")],
                   {"skincare": make_aliases({"TO": "The Ordinary"})})
    assert [g.name for g in groups] == ["The Ordinary"]


def test_a_loose_name_that_fits_another_loose_name_stays_loose():
    # From the library merges (10 Oct 2026): "MM" fits "MM Factory pan", itself loose (a 9 mm and a 12 mm pan), and
    # an MM Factory lid. It fits more than one product, so it joins none, even though only the lid is specific.
    groups = group([kitchen("MM"), kitchen("MM Factory extra thick lid", "c2"), kitchen("MM Factory pan", "c3"),
                    kitchen("9 mm MM Factory pan", "c4"), kitchen("12 mm MM Factory pan", "c5")])
    assert ["MM"] in names_by_group(groups)
    assert sorted(g.name for g in groups if g.loose) == ["MM", "MM Factory pan"]


# --- A name without its brand, of one word and a kind of product (13 Oct 2026) ---

def haircare(product: str, comment_id: str = "c1aaaa", thread_id: str = "1fake01") -> ProductMention:
    return mention(product, thread_id, comment_id, category="haircare")


def test_a_flavour_and_a_kind_never_join_another_makers_product():
    # Found reading the shampoo answers: one maker's chai shampoo, named without its brand, had joined another maker's
    # coconut milk and chai spice shampoo. Two brands are never one product.
    groups = group([haircare("Chai shampoo"), haircare("Hair Food coconut milk and chai spice shampoo", "c2")])
    assert names_by_group(groups) == [["Chai shampoo"], ["Hair Food coconut milk and chai spice shampoo"]]


def test_a_brand_and_a_kind_join_a_product_whose_name_holds_the_brand_later():
    # "Ballarini" is written alone as a name: a brand, so "Ballarini pans" is its product in a co-branded name.
    groups = group([kitchen("Ballarini pans"), kitchen("ballarini", "c2"), kitchen("Zwilling/Ballarini non-stick pans", "c3")])
    assert names_by_group(groups) == [["Ballarini pans", "Zwilling/Ballarini non-stick pans", "ballarini"]]


# --- A brand followed by the requested type's words is the brand's line of that type (13 Oct 2026) ---

def kettles(*names):
    return [kitchen(name, comment_id=f"c{i}") for i, name in enumerate(names)]


def test_a_brand_and_the_requested_type_fits_every_model_of_the_brand():
    # Found reading the kettle answer (b06): "Fellow kettle" was a product of its own, a pick next to "Fellow Stagg EKG",
    # because no Fellow model's name says "kettle". In a kettle answer it names Fellow's kettles, so it fits the Stagg EKG
    # and the Corvo EKG: Fellow's kettle line, one line with "Fellow" written alone.
    mentions = kettles("Fellow kettle", "Fellow kettles", "Fellow", "Fellow Stagg EKG", "Fellow Corvo EKG")
    groups = group_products(mentions, NO_ALIASES, product_type="electric kettle")
    assert names_by_group(groups) == [["Fellow", "Fellow kettle", "Fellow kettles"], ["Fellow Corvo EKG"], ["Fellow Stagg EKG"]]
    line = next(g for g in groups if "Fellow" in g.names)
    assert line.loose and line.name == "Fellow"  # shown as the brand, so the answer names it "Fellow ... line"


def test_a_models_name_with_the_type_joins_that_model():
    # "Fellow Stag kettle" (a slip) is the Stagg with the type's word: it fits the Stagg EKG alone, so it joins it.
    mentions = kettles("Fellow Stag kettle", "Fellow kettle", "Fellow", "Fellow Stagg EKG", "Fellow Corvo EKG")
    groups = group_products(mentions, NO_ALIASES, product_type="electric kettle")
    assert ["Fellow Stag kettle", "Fellow Stagg EKG"] in names_by_group(groups)
    assert ["Fellow", "Fellow kettle"] in names_by_group(groups)


def test_two_lines_of_one_brand_with_and_without_the_type_are_one_line():
    # Found in the lip balm answer (s06): "Torriden" and "Torriden balm" both fit two Torriden lip balms, and both were
    # listed as "Torriden lip balm line" on the skip list.
    mentions = [mention(n, comment_id=f"c{i}") for i, n in enumerate(
        ["Torriden", "torriden", "Torriden balm", "Torriden yellow lip balm", "Torriden ceramide solid-in lip balm",
         "Torriden dive in serum"])]
    groups = group_products(mentions, NO_ALIASES, product_type="lip balm")
    line = [g for g in groups if g.loose]
    assert [sorted(g.names) for g in line] == [["Torriden", "Torriden balm", "torriden"]]
    assert len(groups) == 4


def test_the_requested_types_words_never_join_a_shampoo_to_its_conditioner():
    # "Suave Naturals ocean breeze shampoo" is one product in a shampoo answer: dropping the type's word never makes it
    # the line's conditioner, nor the line itself.
    mentions = [haircare(n, f"c{i}") for i, n in enumerate(
        ["Suave Naturals ocean breeze", "Suave Naturals ocean breeze shampoo", "Suave Naturals ocean breeze conditioner"])]
    for product_type in ("shampoo", None):
        groups = group_products(mentions, NO_ALIASES, product_type=product_type)
        assert names_by_group(groups) == [["Suave Naturals ocean breeze"], ["Suave Naturals ocean breeze conditioner"],
                                          ["Suave Naturals ocean breeze shampoo"]]
        assert [g.name for g in groups if g.loose] == ["Suave Naturals ocean breeze"]


def test_a_brand_and_the_type_joins_a_line_name_that_says_no_type():
    # Found in the conditioner answer (s08): "Suave Coconut conditioner" is the "Suave Naturals Coconut" conditioner, whose
    # name says no type: in a conditioner answer they are one product.
    mentions = [haircare(n, f"c{i}") for i, n in enumerate(["Suave Coconut conditioner", "Suave Naturals Coconut"])]
    assert len(group_products(mentions, NO_ALIASES, product_type="conditioner")) == 1
    assert len(group_products(mentions, NO_ALIASES, product_type="shampoo")) == 2  # its words aren't the shampoo's
    assert len(group_products(mentions, NO_ALIASES)) == 2  # with no request, as before


def test_without_a_requested_type_a_brand_and_a_type_is_grouped_as_before():
    mentions = kettles("Fellow kettle", "Fellow kettles", "Fellow", "Fellow Stagg EKG", "Fellow Corvo EKG")
    assert ["Fellow kettle", "Fellow kettles"] in names_by_group(group_products(mentions, NO_ALIASES))


def test_a_brands_line_is_shown_as_the_brand_not_with_the_types_words():
    # Found in the cast iron answer (b08) once "Lodge cast iron" joined the Lodge line: its other spelling, "cast iron
    # Lodge", has words before the brand, and was shown as if they were a brand ("cast iron Lodge cast iron skillet").
    mentions = [kitchen(n, comment_id=f"c{i}") for i, n in enumerate(
        ["Lodge", "Lodge", "Lodge", "Lodge cast iron", "cast iron Lodge", "Lodge cast iron skillet 10 inch",
         "Lodge cast iron skillet 12 inch"])]
    groups = group_products(mentions, NO_ALIASES, product_type="cast iron skillet")
    line = next(g for g in groups if g.loose)
    assert sorted(line.names) == ["Lodge", "Lodge cast iron", "cast iron Lodge"]
    assert (line.name, line.key) == ("Lodge", "kitchen:lodge")


def typed(product: str, product_type: str, comment_id: str = "c1aaaa", category: str = "skincare") -> ProductMention:
    return ProductMention("1fake01", comment_id, product, category, "recommend", product_type=product_type)


def test_a_brand_and_the_type_fits_only_the_brands_products_of_that_type():
    # Found in the sunscreen answer (b02): "TO sunscreen" had fitted The Ordinary's lactic acid and niacinamide, whose
    # names say no kind of product: the AI's type says they aren't sunscreens.
    mentions = [typed("TO sunscreen", "sunscreen", "c1"), typed("TO sunscreen", "sunscreen", "c2"),
                typed("The Ordinary Lactic Acid 10% + HA", "exfoliant", "c3"),
                typed("The Ordinary Niacinamide 10% and Zinc 1%", "serum", "c4")]
    aliases = {"skincare": make_aliases({"TO": "The Ordinary"})}
    groups = group_products(mentions, aliases, product_type="sunscreen")
    # Changed on purpose 14 Oct 2026 (name levels, engine/tests/test_name_levels.py): "TO sunscreen" is The Ordinary
    # with only the type's word, so it is The Ordinary's sunscreen line (loose); it was a product of its own. What this
    # test guards stays: it fits neither the lactic acid nor the niacinamide, which stay products of their own.
    assert len(groups) == 3
    assert [sorted(g.names) for g in groups if g.loose] == [["TO sunscreen"]]
    assert not any(g.loose for g in groups if "TO sunscreen" not in g.names)


def test_a_brand_and_the_types_plural_fits_the_brands_models_of_that_type():
    # Found in the chef knife answer (b07): "Shun knives" fitted only "Shun 7"" (a size) and so joined it, though it
    # names Shun's knives: it fits the Shun Classic chef knife too, whose name ends in the type's own word. So it is the
    # Shun line, as is "Shun Chef's knife" (the brand and the type's words: Shun makes many chef's knives).
    mentions = [typed(n, "chef knife", f"c{i}", "kitchen") for i, n in enumerate(
        ["Shun", "Shun knives", "Shun knives", 'Shun 7"', "Shun Chef's knife", "Shun Classic chef knife"])]
    groups = group_products(mentions, NO_ALIASES, product_type="chef knife")
    line = next(g for g in groups if "Shun" in g.names)
    assert line.loose and sorted(line.names) == ["Shun", "Shun Chef's knife", "Shun knives"]
    assert names_by_group(groups) == [["Shun", "Shun Chef's knife", "Shun knives"], ["Shun 7\""], ["Shun Classic chef knife"]]


def test_a_brand_and_the_type_written_two_ways_is_one_name_not_two_products():
    # Found in the sunscreen answer (b02): "TO sunscreen" fitted "TO sunscreens" (its own plural) and a TO sun care line,
    # so it read as fitting two products and left the skip list as a line.
    mentions = [typed("TO sunscreen", "sunscreen", "c1"), typed("TO sunscreens", "sunscreen", "c2"),
                typed("The Ordinary sunscreen", "sunscreen", "c3"), typed("The Ordinary suncare", "sunscreen", "c4")]
    groups = group_products(mentions, {"skincare": make_aliases({"TO": "The Ordinary"})}, product_type="sunscreen")
    assert len(groups) == 1 and not groups[0].loose


def test_a_brand_written_alone_and_with_the_type_is_a_line_even_with_one_model_named():
    # Found in the rice cooker answer (s04): "Tiger" (written 15 times) and "Tiger rice cooker" name Tiger's rice cookers.
    # With one Tiger model named, the brand had joined that model, and the pick was shown as a bare "Tiger". Writers who
    # name a brand both alone and with the type speak of its line: it stays the line, and the model a product of its own.
    mentions = [typed(n, "rice cooker", f"c{i}", "kitchen") for i, n in enumerate(
        ["Tiger", "Tiger", "tiger", "Tiger rice cooker", "Tiger 1 button"])]
    groups = group_products(mentions, NO_ALIASES, product_type="rice cooker")
    assert names_by_group(groups) == [["Tiger", "Tiger rice cooker", "tiger"], ["Tiger 1 button"]]
    assert [g.name for g in groups if g.loose] == ["Tiger"]
    # Without the name with the type, the brand alone joins its only model, as before (a brand alone fits its one
    # product).
    groups = group_products([m for m in mentions if m.product != "Tiger rice cooker"], NO_ALIASES, product_type="rice cooker")
    assert len(groups) == 1 and not groups[0].loose


def test_the_ais_type_says_which_of_a_brands_products_are_of_the_type():
    # A cream and a lotion the AI typed as moisturisers are moisturisers, whatever their last words: "Cetaphil moisturizer"
    # fits both, so it is Cetaphil's moisturiser line in a moisturiser request.
    mentions = [typed("Cetaphil moisturizer", "moisturiser", "c1"), typed("Cetaphil Moisturising Cream", "moisturiser", "c2"),
                typed("Cetaphil Daily Hydrating Lotion", "moisturiser", "c3"), typed("Cetaphil cleanser", "cleanser", "c4")]
    groups = group_products(mentions, NO_ALIASES, product_type="moisturiser")
    assert [g.name for g in groups if g.loose] == ["Cetaphil moisturizer"]
    assert len(groups) == 4


def test_a_product_is_shown_by_its_own_name_not_its_brand_with_the_type():
    # Found in the eye cream answer (s10): "Lancome eye creams" fitted one Lancôme product here, the Génifique, and joined
    # it; the item was shown as "Lancome eye creams", a line's name, though its other name says which product it is.
    mentions = [typed("Lancôme genefique", "eye cream", "c1"), typed("Lancôme genefique", "eye cream", "c2"),
                typed("Lancome eye creams", "eye cream", "c3")]
    groups = group_products(mentions, NO_ALIASES, product_type="eye cream")
    assert [(g.name, g.loose) for g in groups] == [("Lancôme genefique", False)]


def test_a_brand_pick_name_leaves_out_a_trailing_one():
    # Found in the cleanser answer (b05): the AI wrote "the Aveeno one" as "aveeno one" ("one" is filler: the name is the
    # brand), and the line was shown as "aveeno one cleanser line".
    assert brand_pick_name("aveeno one", "cleanser") == "aveeno cleanser line"
    assert brand_pick_name("Victorinox ones", "chef knife") == "Victorinox chef knife line"
    assert brand_pick_name("One", "cleanser") == "One cleanser line"  # a name that is only "one" keeps it


def test_a_line_name_without_its_brand_and_with_the_type_is_its_product_not_a_line():
    # Found in the dandruff answer (s02): "T-Gel" and "T Gel shampoo" are Neutrogena's T/Gel written without the brand.
    # "Neutrogena T-Gel" adds the brand before the name, not a model after it, so it isn't a model of a "T-Gel" line:
    # all of them are the one shampoo.
    mentions = [typed(n, "shampoo", f"c{i}", "haircare") for i, n in enumerate(
        ["T-Gel", "T-Gel", "T Gel shampoo", "neutrogena t-gel", "Neutrogena T/Gel shampoo"])]
    groups = group_products(mentions, NO_ALIASES, product_type="shampoo")
    assert len(groups) == 1 and not groups[0].loose


def test_a_brand_and_the_type_fitting_one_of_several_models_joins_none():
    # Found in the frying pan answer (b10): "our place pan" fitted only the titanium cookware, because the brand alone
    # never fits a model with a model word ("Pro"), and so joined it, though its writer's pan was ceramic (the Always
    # Pan). Our Place has several products named here: its name with the type fits one of them only by chance.
    mentions = [typed(n, "frying pan", f"c{i}", "kitchen") for i, n in enumerate(
        ["our place pan", "Our Place titanium cookware", "Our Place titanium cookware", "Our Place Titanium Always Pan Pro"])]
    groups = group_products(mentions, NO_ALIASES, product_type="frying pan")
    assert names_by_group(groups) == [["Our Place Titanium Always Pan Pro"], ["Our Place titanium cookware"], ["our place pan"]]
    # A name of one product with the type's words still joins it: "Suave Coconut conditioner" (test above).


def test_a_products_most_written_name_stays_shown_though_it_ends_like_the_type():
    # Found in the eye cream answer (s10): "Clinique all about eyes" (its "eyes" reads as the type's word) was shown as
    # "Clinique All About Eyes Rich", the name of one writer's variant, once names with the type gave way.
    mentions = [typed(n, "eye cream", f"c{i}") for i, n in enumerate(
        ["Clinique all about eyes", "Clinique all about eyes", "Clinique All About Eyes", "Clinique All About Eyes Rich"])]
    groups = group_products(mentions, NO_ALIASES, product_type="eye cream")
    assert [g.name.lower() for g in groups] == ["clinique all about eyes"]


# --- One index of a library's names, for every request's grouping (latency, 13 Oct 2026) ---

from engine.group_products import library_name_index  # noqa: E402


def test_grouping_with_the_librarys_name_index_gives_the_same_groups():
    # Made-up names of brands, lines, models, types and slips: a request's mentions (any of the library's, and a part
    # of them, as grouping again without another type's mentions does) grouped with and without the index, for the
    # product types module 1 knows, none, and one the open model named (its bases aren't in the index: worked out).
    rng = random.Random(13)
    brands = ["Lodge", "lodge", "Fellow", "Stagg", "CeraVe", "Cerave", "Tiger", "Zojirushi", "Zojurushi", "Our Place"]
    rest = ["", "kettle", "kettles", "electric kettle", "Stagg EKG", "cast iron skillet", "skillet", "pan", "pans",
            "rice cooker", "SA cleanser", "Hydrating Cleanser", "cleanser", "moisturizing cream", "cream", "10 inch",
            "12 inch skillet", "Corvo EKG", "titanium cookware", "Always Pan Pro", "dutch oven", "shampoo"]
    library = []
    for i in range(400):
        name = f"{rng.choice(brands)} {rng.choice(rest)}".strip()
        category = rng.choice(["kitchen", "skincare"])
        library.append(ProductMention(f"t{i % 30}", f"c{i}", name, category, rng.choice(["recommend", "warn"]),
                                      rng.choice([None, "electric kettle", "cast iron skillet", "cleanser"])))
    index = library_name_index(library)
    for product_type in [None, "electric kettle", "cast iron skillet", "rice cooker", "cleanser", "moisturiser",
                         "air fryer"]:
        for mentions in (library, library[:150], library[100:330]):
            assert (group_products(mentions, product_type=product_type, index=index)
                    == group_products(mentions, product_type=product_type)), product_type


def test_a_categorys_index_holds_the_first_types_bases_and_its_own_taxonomy_types_only():
    # 14 Oct 2026 (merging main): with the taxonomy's 351 types, every name's base in every type made getting ready's
    # name index seven times slower. A category's index holds its names' bases in module 1's first 43 types (any
    # request's, as before) and in the taxonomy's types of that category only; a request of another category's taxonomy
    # type works these names' pairs out itself, as for a type the open model named: the same groups either way.
    library = [typed("Work Sharp knife sharpener", "knife sharpener", "c1", "kitchen"),
               typed("Work Sharp", "knife sharpener", "c2", "kitchen"), typed("Bose headphones", None, "c3", "kitchen"),
               typed("Sony WH-1000XM5 headphones", "headphones", "c4", "general"),
               typed("Sony", "headphones", "c5", "general")]
    index = library_name_index(library)
    assert ("work", "sharp") in index["kitchen"].candidates  # its base as a knife sharpener, a kitchen taxonomy type
    assert ("bose",) not in index["kitchen"].candidates  # its base as headphones, a general type: not worked out here
    assert ("sony", "wh", "1000xm5") in index["general"].candidates
    for product_type in ("knife sharpener", "headphones", "electric kettle", None):
        assert (group_products(library, product_type=product_type, index=index)
                == group_products(library, product_type=product_type)), product_type


def test_the_index_asks_each_name_only_the_types_that_can_give_it_a_base(monkeypatch):
    # 15 Oct 2026 (getting ready on the live site took 199 s of its probe's 240): with ~1,950 threads the index was most
    # of a cold first answer, every general name's base worked out in each of ~385 types. A name has a base in a type
    # only when its last word is one of the type's words, as written or with a spelling slip, or a synonym of the type
    # ends it: so only those types are asked, and the index holds exactly what asking every type gives.
    from engine import group_products as grouping
    from engine.query import FIRST_PRODUCT_TYPES

    names = ["Fellow Stagg EKG kettle", "Fellow kettel", "Lodge cast iron pan", "Zojirushi", "Sony WH-1000XM5 headphones",
             "Sony headphone", "Bose QC45", "Work Sharp knife sharpener", "Our Place Always Pan", "CeraVe cleanser",
             "Anker charger", "Anker chargers", "Patagonia jacket", "Hoka running shoes", "Osprey backpack"]
    library = [typed(name, None, f"c{i}", category) for i, name in enumerate(names) for category in ("general", "kitchen")]
    calls = []
    real = grouping._without_type_words
    monkeypatch.setattr(grouping, "_without_type_words", lambda *args: calls.append(1) or real(*args))
    index = library_name_index(library)
    index["general"], index["kitchen"]  # each category's made when first asked for (the test below)
    types = [(grouping._type_words(p.name), grouping._type_phrases(p.name)) for p in PRODUCT_TYPES
             if p in FIRST_PRODUCT_TYPES or p.category == "general"]
    asked = len(calls)
    from engine.match_products import known_aliases, product_words

    every = {tuple(product_words(n, known_aliases().get("general", {}))) for n in names}
    every |= {base for words in set(every) for type_words, phrases in types
              if (base := real(words, type_words, phrases))}
    assert set(index["general"].candidates) == every
    assert asked < len(names) * len(types) / 4  # each name asks a few types, not all of them (2 categories: < 1/2)


def test_a_categorys_index_is_made_when_an_answer_of_it_first_needs_it(monkeypatch):
    # 15 Oct 2026 (getting ready on the live site took 199 s of its probe's 240): the library's index was made for every
    # category on the first answer, whatever it asked, and the general category's (~22,000 names and bases with ~1,950
    # threads) was two thirds of it. Now each category's is made the first time a grouping of its names needs it, and
    # kept: a category's first answer makes its own, and the groups are the same.
    from engine import group_products as grouping

    made = []
    real = grouping.NameIndex.__init__
    monkeypatch.setattr(grouping.NameIndex, "__init__", lambda self, names: made.append(1) or real(self, names))
    kettles = [kitchen("Fellow Stagg EKG", "c1"), kitchen("Fellow kettle", "c2"), kitchen("Fellow", "c3")]
    headphones = [typed("Sony WH-1000XM5 headphones", "headphones", "c4", "general"),
                  typed("Sony", "headphones", "c5", "general")]
    index = library_name_index(kettles + headphones)
    assert made == [] and sorted(index) == ["general", "kitchen"] and "general" in index and made == []
    assert index.get("haircare") is None and "haircare" not in index
    groups = group_products(kettles, product_type="electric kettle", index=index)
    assert len(made) == 1  # the kitchen's only
    assert groups == group_products(kettles, product_type="electric kettle")
    assert group_products(kettles, product_type="electric kettle", index=index) == groups and len(made) == 1
    general = index["general"]
    assert len(made) == 2 and index["general"] is general
    assert group_products(headphones, product_type="headphones", index=index) == group_products(
        headphones, product_type="headphones")


def _many_names(seed: int = 7, count: int = 2500) -> list[tuple[str, ...]]:
    """Made-up names sharing brands, words and slips, so that many pairs are candidates."""
    rng = random.Random(seed)
    brands = ["sony", "sonos", "sage", "shark", "smeg", "salter", "tefal", "tower", "lodge", "lodgee", "cerave", "cera",
              "zojirushi", "zojurushi", "fellow", "fellows", "bosch", "breville", "oxo", "ninja", "ninjas"]
    words = ["kettle", "kettles", "pan", "pans", "cream", "cleanser", "pro", "max", "mini", "plus", "2", "22", "x", "xl",
             "blender", "mixer", "stand", "air", "fryer", "steel", "cast", "iron", "and", "co", "classic", "one"]
    return sorted({(rng.choice(brands),) + tuple(rng.choice(words) for _ in range(rng.randint(0, 3)))
                   for _ in range(count)})


def test_the_index_keeps_its_pairs_in_a_small_part_of_the_memory_of_sets():
    # 15 Oct 2026: with ~1,950 threads the library's index held 3.6 million candidate links and 3.55 million open pairs
    # as sets of names: about 470 MB kept, and building it went a gigabyte above the library (the live site ran out of
    # memory at 2 GiB). It keeps each name's candidates as an array of numbers, with a byte for whether the quick look
    # leaves the pair that way round, and builds them without keeping every word's names at once.
    import tracemalloc

    from engine.group_products import NameIndex
    from engine.match_products import match_candidates_and_open

    names = _many_names()
    tracemalloc.start()
    plain = match_candidates_and_open(names)
    as_sets = tracemalloc.get_traced_memory()[0]
    tracemalloc.stop()
    links = sum(map(len, plain[0].values()))
    del plain
    tracemalloc.start()
    index = NameIndex(names)
    kept, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert links > 40_000 and len(index.candidates) == len(names)
    assert kept < as_sets / 4, (kept, as_sets)


def test_the_indexs_pairs_among_a_requests_names_are_the_pairs_worked_out_for_them():
    from engine.group_products import NameIndex
    from engine.match_products import _cannot_match, match_candidates_and_open

    names = _many_names(count=800)
    index = NameIndex(names)
    every, _ = match_candidates_and_open(names)
    rng = random.Random(3)
    for part in (names, rng.sample(names, 200), rng.sample(names, 40)):
        among = set(part)
        candidates, open_pairs = index.among(part)
        assert candidates == {name: every[name] & among for name in part}
        asked = {(a, b) for a in part for b in candidates[a]}
        assert {pair for pair in asked if pair in open_pairs} == {(a, b) for a, b in asked if not _cannot_match(a, b)}
    assert index.among(part + [("not", "in", "the", "library")]) is None


def test_a_request_of_a_known_type_takes_its_pairs_from_the_index(monkeypatch):
    from engine import group_products as grouping

    library = [kitchen("Fellow Stagg EKG", "c1"), kitchen("Fellow kettle", "c2"), kitchen("Fellow", "c3"),
               kitchen("Lodge cast iron skillet", "c4"), kitchen("Lodge", "c5")]
    index = library_name_index(library)
    worked_out = []
    real = grouping.match_candidates_and_open
    monkeypatch.setattr(grouping, "match_candidates_and_open", lambda names: worked_out.append(1) or real(names))
    with_index = group_products(library, product_type="electric kettle", index=index)
    assert worked_out == []  # every name and base was in the index
    assert with_index == group_products(library, product_type="electric kettle")
    assert worked_out == [1]


# --- Whether a name adds words at the start of another, worked out once per pair (latency, 14 Oct 2026) ---

def test_whether_a_name_adds_words_at_the_start_of_another_is_worked_out_once_per_pair(monkeypatch):
    # Choosing each group's shown name asks it of every name of the group against the main one, and every answer
    # grouping the same names asks again (38,204 times for 32 answers after getting ready).
    from engine import group_products

    joined = []
    joining = group_products.join_split_words
    monkeypatch.setattr(group_products, "join_split_words", lambda words, other: joined.append(1) or joining(words, other))
    pairs = [(("fellow", "stagg", "ekg"), ("stagg", "ekg")), (("1zpresso", "jx", "pro"), ("jx", "pro")),
             (("jx", "pro"), ("jx", "pro")), (("tir", "tir", "milk"), ("tirtir", "milk")), (("a", "b", "c"), ("c",))]
    first = [group_products._adds_words_at_start(longer, name) for longer, name in pairs]
    assert first == [True, True, False, False, True]
    asked = len(joined)
    assert [group_products._adds_words_at_start(longer, name) for longer, name in pairs] == first
    assert len(joined) == asked  # each pair worked out once
