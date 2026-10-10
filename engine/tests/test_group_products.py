"""Module 4, grouping: every mention of one product, across threads, gathered under one name.

Names are made up or copied from the library's product names (names only, never comment text).
"""

import random

from engine import config
from engine.extract import CheckResult, ExtractedMention
from engine.group_products import (
    ProductMention, brand_pick_name, group_of, group_products, mentions_from_checked, uk_name,
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
    assert brand_pick_name("Lodge", "cast iron skillet") == "Lodge (their cast iron skillets)"
    assert brand_pick_name("Zojirushi", "electric kettle") == "Zojirushi (their electric kettles)"
    assert brand_pick_name("Victorinox", "chef knife") == "Victorinox (their chef knives)"
    assert brand_pick_name("Paula's Choice", "exfoliant") == "Paula's Choice (their exfoliants)"


def test_every_product_type_has_a_plural():
    assert set(config.PRODUCT_TYPE_PLURALS) == {p.name for p in PRODUCT_TYPES}
    assert config.PRODUCT_TYPE_PLURALS["chef knife"] == "chef knives"
    assert config.PRODUCT_TYPE_PLURALS["dutch oven"] == "Dutch ovens"
    for name, plural in config.PRODUCT_TYPE_PLURALS.items():
        assert plural.lower() != name.lower() and plural.endswith("s"), name


def test_a_brand_pick_name_that_already_says_the_type_has_no_bracket():
    # Noemi, 9 Oct 2026: "CeraVe cleanser (their cleansers)" reads oddly; the name already says what it is.
    assert brand_pick_name("CeraVe cleanser", "cleanser") == "CeraVe cleanser"
    assert brand_pick_name("Lodge", "cast iron skillet") == "Lodge (their cast iron skillets)"


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
