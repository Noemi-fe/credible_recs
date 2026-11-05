"""Makeup names and groups (5 Nov 2026, the makeup review of round 2; Claude's technical calls, reported to Noemi).

A beauty-literate reader found one product in two groups and names written wrong in the 15 makeup answers:
- Charlotte Tilbury's setting spray was recommended under its name and skipped under "CT", each with the same warnings.
  CT is Charlotte Tilbury (engine/data/product_aliases.json), at the start of a name only.
- Essence's mascara is the Lash Princess, though writers often write "Princess Lash".
- Stila's liquid liner, written "Stila liquid eyeliner" or "Stila All Day Waterproof Liquid Eyeliner", is its Stay All
  Day Liquid Liner, so a warning written under one name reaches the pick shown under the other.
- The Maybelline Super Stay Skin Tint, written with "24", "24h" or "VitC", had made the Super Stay a loose line shown
  as "Maybelline Super Stay foundation line"; the Skin Tint is one product, apart from the Super Stay foundation.
- Brands as their makers write them (config.MAKER_SPELLINGS): NARS, NYX, MAC's lines (a bare "Mac" in the general
  category is mostly Apple's), ONE/SIZE and its On 'Til Dawn, Estée Lauder, L'Oréal, got2b, e.l.f.

Product names only, as the library writes them; nothing reads data/ but the shipped lists.
"""

import pytest

from engine.group_products import ProductMention, brand_pick_name, group_products, maker_spelling
from engine.match_products import known_aliases, product_words, same_product
from engine.summaries import summary_key
from engine.tests.test_round3_names import group_with, modules_four


# --- One product, one group ---

CHARLOTTE = [("Charlotte Tilbury", 18), ("CT", 14), ("Charlotte Tilbury setting spray", 6), ("Charlotte tilbury", 5),
             ("CT setting spray", 2), ("CT Setting Spray", 1), ("Charlotte Tillbury setting spray", 1),
             ("Urban Decay All Nighter", 12), ("One Size setting spray", 9), ("Milani Make It Last", 8)]


def test_ct_is_charlotte_tilbury_one_setting_spray_group():
    groups = modules_four(CHARLOTTE, "setting spray")
    charlotte = group_with(groups, "Charlotte Tilbury")
    assert {"CT", "CT setting spray", "CT Setting Spray"} <= set(charlotte.names)
    assert len(charlotte.mentions) == 47
    for other in ("Urban Decay All Nighter", "One Size setting spray", "Milani Make It Last"):
        assert group_with(groups, other) is not charlotte, other


def test_a_comment_warning_about_ct_and_charlotte_tilbury_is_in_one_group():
    # One comment naming the spray both ways: both mentions land in the one group, so the ranking counts its writer once
    # (one voice per writer, engine.rank), where two groups had each counted the warning.
    mentions = [ProductMention("t1", "c1", "CT setting spray", "general", "warn"),
                ProductMention("t1", "c1", "Charlotte Tilbury setting spray", "general", "warn"),
                ProductMention("t2", "c2", "Charlotte Tilbury", "general", "recommend"),
                ProductMention("t2", "c3", "Urban Decay All Nighter", "general", "recommend")]
    groups = group_products(mentions, product_type="setting spray")
    charlotte = group_with(groups, "Charlotte Tilbury")
    assert {m.comment_id for m in charlotte.mentions} == {"c1", "c2"}
    assert group_with(groups, "CT setting spray") is charlotte


def test_ct_is_a_short_name_at_the_start_of_a_general_name_only():
    general = known_aliases()["general"]
    assert product_words("CT", general) == ["charlotte", "tilbury"]
    assert product_words("CT matte spray", general) == ["charlotte", "tilbury", "matte", "spray"]
    assert product_words("Original CT", general) == ["original", "ct"]
    # Each category has its own short names: a skincare name is read as before.
    assert product_words("CT Magic Cream", known_aliases()["skincare"]) == ["ct", "magic", "cream"]


ESSENCE = [("Essence Princess Lash", 11), ("Essence Lash Princess", 7), ("Lash Princess", 3),
           ("essence princess lash", 3), ("Lash Princess from Essence", 1), ("Essence lash princess", 1),
           ("Essence Lash without limits tubing", 5), ("Maybelline Sky High", 10), ("Thrive", 9)]


def test_essences_lash_princess_is_one_product_however_it_is_written():
    groups = modules_four(ESSENCE, "mascara")
    princess = group_with(groups, "Essence Lash Princess")
    assert {"Essence Princess Lash", "Lash Princess", "essence princess lash"} <= set(princess.names)
    assert group_with(groups, "Essence Lash without limits tubing") is not princess
    assert maker_spelling("Essence Princess Lash", "general") == "Essence Lash Princess"
    assert maker_spelling("Lash Princess", "general") == "Essence Lash Princess"


STILA = [("Stila All Day Waterproof Liquid Eyeliner", 6), ("Stila liquid eyeliner", 3), ("Stila liquid liner", 2),
         ("Stila Stay All Day Liquid Liner", 2), ("Stila Stay All Day liquid liner", 2),
         ("Stila Stay All Day liquid eyeliner", 1), ("Stila waterproof Stay All Day liquid", 1),
         ("Stila eyeliner", 11), ("Stila Smudge Stick", 1), ("NYX Epic Ink", 14), ("KVD Tattoo Liner", 6)]


def test_stilas_liquid_liners_are_its_stay_all_day_liquid_liner():
    groups = modules_four(STILA, "eyeliner")
    liner = group_with(groups, "Stila Stay All Day Liquid Liner")
    assert {"Stila All Day Waterproof Liquid Eyeliner", "Stila liquid eyeliner", "Stila liquid liner",
            "Stila Stay All Day liquid eyeliner", "Stila waterproof Stay All Day liquid"} <= set(liner.names)
    # Its other eyeliners, and the brand written alone, stay apart.
    for other in ("Stila eyeliner", "Stila Smudge Stick", "NYX Epic Ink", "KVD Tattoo Liner"):
        assert group_with(groups, other) is not liner, other
    assert maker_spelling("Stila liquid eyeliner", "general") == "Stila Stay All Day Liquid Liner"


SUPER_STAY = [("Maybelline Super Stay Skin Tint", 13), ("Maybelline Superstay Skin Tint", 7),
              ("Maybelline super stay skin tint", 2), ("Maybelline SuperStay VitC skin tint", 1),
              ("Maybeline Super Stay 24h skin tint", 1), ("Maybelline superstay tint", 1),
              ("Maybelline SuperStay 24 Skin Tint", 1), ("Maybelline Super Stay", 1), ("Maybelline SuperStay", 1),
              ("Maybelline Lumi Matte", 7), ("Maybelline Super Stay Lumi Matte", 2), ("Estee Lauder Double Wear", 20)]


def test_the_super_stay_skin_tint_is_one_product_apart_from_the_super_stay_foundation():
    groups = modules_four(SUPER_STAY, "foundation")
    tint = group_with(groups, "Maybelline Super Stay Skin Tint")
    assert not tint.loose  # a product, not a line named "Maybelline Super Stay foundation line"
    assert {"Maybelline SuperStay VitC skin tint", "Maybeline Super Stay 24h skin tint", "Maybelline superstay tint",
            "Maybelline SuperStay 24 Skin Tint"} <= set(tint.names)
    assert "Maybelline Super Stay" not in tint.names and "Maybelline SuperStay" not in tint.names
    assert group_with(groups, "Maybelline Lumi Matte") is not tint
    assert not same_product("Maybelline Super Stay Skin Tint", "Maybelline Super Stay foundation",
                            known_aliases()["general"])


# --- Names as their makers write them ---

@pytest.mark.parametrize("written, shown", [
    ("Nars Orgasm", "NARS Orgasm"),
    ("nars radiant creamy concealer", "NARS radiant creamy concealer"),
    ("NARS Light Reflecting foundation", "NARS Light Reflecting foundation"),
    ("Nyx marshmallow primer", "NYX marshmallow primer"),
    ("Mac Fix + Stay Over", "MAC Fix+ Stay Over"),
    ("Mac Fix+", "MAC Fix+"),
    ("Mac Fix Plus", "MAC Fix+"),
    ("Mac face and body", "MAC Face and Body"),
    ("One size on til dawn", "ONE/SIZE On 'Til Dawn"),
    ("One Size setting spray", "ONE/SIZE setting spray"),
    ("Estee Lauder Double Wear", "Estée Lauder Double Wear"),
    ("L’Oreal True Match", "L'Oréal True Match"),
    ("Got2B Glue Spiking Gel", "got2b Glue Spiking Gel"),
    ("Elf brow lift", "e.l.f. brow lift"),
    ("ELF setting spray", "e.l.f. setting spray"),
])
def test_makeup_brands_are_shown_as_their_makers_write_them(written, shown):
    assert maker_spelling(written, "general") == shown


@pytest.mark.parametrize("name", ["Mac", "Macs", "Mac Neo", "MacBook Air", "Mack Weldon", "Mach 5",
                                  "Patrick Ta One/size On ‘Til Dawn setting spray"])
def test_apples_mac_and_other_names_are_left_as_they_were(name):
    assert maker_spelling(name, "general") == name


def test_the_on_til_dawn_line_is_named_as_its_maker_writes_it():
    assert brand_pick_name(maker_spelling("One size on til dawn", "general"), "setting spray") == (
        "ONE/SIZE On 'Til Dawn setting spray line")


@pytest.mark.parametrize("written", ["Nars Orgasm", "Mac Fix + Stay Over", "One size on til dawn", "Got2B Glue",
                                     "Estee Lauder Double Wear", "L’Oreal True Match",
                                     "Nyx Epic Wear liquid eyeliner"])
def test_a_brand_written_otherwise_keeps_its_saved_summary(written):
    # A product's summary is saved under the words of its shown name (engine.summaries.summary_key): these spellings
    # change capitals and marks only. e.l.f.'s letters are words of their own, so its two summaries wait for the next
    # summarising batch. (A short name written out, "Nyx Epic Ink" as the NYX Epic Ink Liner, is another name: below.)
    assert summary_key("general", maker_spelling(written, "general")) == summary_key("general", written)


# --- More of the same kind, from a look through the 15 makeup answers' ranked products (5 Nov 2026) ---
# Brands written as writers shorten them split one product or line into two groups, each with only part of its voices
# and warnings: "VB eyeliner" beside the third eyeliner pick, "T28" and "ND" beside the first and third concealer picks,
# "Huda" beside "Huda Beauty" (the third setting powder pick), "Thrive" beside "Thrive Causemetics" (the first mascara
# pick), "ABH" and "Anastasia" beside "Anastasia Beverly Hills", "NYX Epic Ink" beside the NYX Epic Ink Liner (the
# second eyeliner pick), and "Got2be" beside got2b. Counts made up; product names only.

def test_vb_is_victoria_beckham():
    groups = modules_four([("Victoria Beckham eyeliner", 20), ("VB eyeliner", 8), ("VB liners", 2),
                           ("Stila eyeliner", 10), ("NYX Epic Ink liner", 12)], "eyeliner")
    beckham = group_with(groups, "Victoria Beckham eyeliner")
    assert "VB eyeliner" in beckham.names
    assert group_with(groups, "Stila eyeliner") is not beckham
    assert maker_spelling("VB eyeliner", "general") == "Victoria Beckham eyeliner"


def test_t28_is_tower_28_and_nd_and_denona_are_natasha_denona():
    groups = modules_four([("Tower 28 concealer", 30), ("Tower 28", 10), ("T28", 9), ("t28", 1),
                           ("Natasha Denona concealer", 10), ("Natasha Denona", 5), ("ND", 17), ("ND concealer", 1),
                           ("Denona", 5), ("Kosas concealer", 20), ("Kosas", 6)], "concealer")
    assert group_with(groups, "T28") is group_with(groups, "Tower 28")
    assert group_with(groups, "ND") is group_with(groups, "Natasha Denona")
    assert group_with(groups, "Denona") is group_with(groups, "Natasha Denona")
    assert group_with(groups, "Kosas") is not group_with(groups, "Tower 28")
    assert maker_spelling("T28", "general") == "Tower 28" and maker_spelling("ND", "general") == "Natasha Denona"



def test_but_a_cameras_nd_filter_stays_an_nd_filter():
    # "ND" is a short name of the general category, which cameras share: a neutral-density filter keeps its name.
    general = known_aliases()["general"]
    for name in ("ND filter", "ND filters", "nd filter for video"):
        assert "denona" not in product_words(name, general), name
    assert product_words("ND concealer", general) == product_words("Natasha Denona concealer", general)

def test_huda_is_huda_beauty():
    groups = modules_four([("Huda Beauty", 10), ("Huda", 17), ("Huda loose powder", 4), ("Huda Beauty loose powder", 2),
                           ("Hourglass Veil", 10), ("Hourglass", 8)], "setting powder")
    assert group_with(groups, "Huda") is group_with(groups, "Huda Beauty")
    assert group_with(groups, "Huda loose powder") is group_with(groups, "Huda Beauty loose powder")
    assert maker_spelling("Huda loose powder", "general") == "Huda Beauty loose powder"


def test_thrive_is_thrive_causemetics():
    groups = modules_four([("Thrive", 33), ("Thrive Causemetics", 8), ("Thrive Causmetics", 4), ("Thrive Cosmetics", 1),
                           ("thrive", 5), ("Essence Lash Princess", 7), ("Maybelline Sky High", 9)], "mascara")
    thrive = group_with(groups, "Thrive")
    assert {"Thrive Causemetics", "Thrive Causmetics", "Thrive Cosmetics", "thrive"} <= set(thrive.names)
    assert group_with(groups, "Essence Lash Princess") is not thrive
    assert maker_spelling("Thrive mascara", "general") == "Thrive Causemetics mascara"
    assert maker_spelling("Thrive Cosmetics", "general") == "Thrive Causemetics"


def test_abh_and_anastasia_are_anastasia_beverly_hills():
    groups = modules_four([("ABH brow wiz", 4), ("Anastasia Beverly Hills brow wiz", 4), ("Anastasia Brow Wiz", 2),
                           ("Anastasia", 16), ("ABH", 3), ("Anastasia Beverly Hills", 1), ("Anastasia BH", 1),
                           ("ABH Dipbrow", 4), ("Benefit Precisely My Brow", 5)], "brow pencil")
    wiz = group_with(groups, "Anastasia Beverly Hills brow wiz")
    assert {"ABH brow wiz", "Anastasia Brow Wiz"} <= set(wiz.names)
    brand = group_with(groups, "Anastasia")
    assert {"ABH", "Anastasia Beverly Hills", "Anastasia BH"} <= set(brand.names)
    assert group_with(groups, "ABH Dipbrow") not in (wiz, brand)
    assert maker_spelling("ABH Dipbrow", "general") == "Anastasia Beverly Hills Dipbrow"


def test_nyx_epic_ink_is_the_epic_ink_liner_and_epic_wear_stays_apart():
    groups = modules_four([("NYX Epic Ink liner", 25), ("NYX Epic Ink", 4), ("Nyx Epic Ink", 3),
                           ("NYX Epic Ink Eyeliner", 1), ("NYX epic ink eyeliner", 1), ("NYX Epic Wear liquid eyeliner", 9),
                           ("NYX epic inky stick cream gel liner", 1), ("Stila eyeliner", 6)], "eyeliner")
    ink = group_with(groups, "NYX Epic Ink liner")
    assert {"NYX Epic Ink", "Nyx Epic Ink", "NYX Epic Ink Eyeliner", "NYX epic ink eyeliner"} <= set(ink.names)
    assert not ink.loose
    for other in ("NYX Epic Wear liquid eyeliner", "NYX epic inky stick cream gel liner"):
        assert group_with(groups, other) is not ink, other


def test_got2be_is_got2b():
    general = known_aliases()["general"]
    assert product_words("Got2be glue", general) == product_words("got2b glue", general)
    assert maker_spelling("Got2be glue travel size", "general") == "got2b glue travel size"


@pytest.mark.parametrize("written, shown", [
    ("Lancome Lash Idole", "Lancôme Lash Idole"),
    ("Ysl touche eclat blur primer", "YSL touche eclat blur primer"),
])
def test_more_makeup_brands_are_shown_as_their_makers_write_them(written, shown):
    assert maker_spelling(written, "general") == shown
    assert summary_key("general", shown) == summary_key("general", written)  # capitals and accents only


@pytest.mark.parametrize("name", ["ND", "T28", "VB", "ABH", "Huda", "Thrive", "Anastasia"])
def test_the_short_names_are_the_general_categorys_only(name):
    # A skincare or haircare name starting so is read as before.
    for category in ("skincare", "haircare", "kitchen"):
        assert product_words(f"{name} cream", known_aliases()[category]) == product_words(f"{name} cream")
