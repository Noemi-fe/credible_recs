"""Names a tester would find odd, round two (17 Oct 2026, the ws-names builder; Claude's technical calls, reported to
Noemi), from the day's sweep after the 16 Oct fixes: names still starting in small letters ("laifen swift", "nanit cam",
"other box defender"), a writer's possessive ("Grado's headphones line"), filler kept in a name ("used Kenmore Elite
dishwasher", "vintage Sunbeam Radiant Control toaster", "Kenwood Chef (vintage)", "Grid Linen towel from Outlier"),
writers' fragments and nicknames ("other box defender" for the OtterBox Defender, "melly" for Melanzana's Micro Grid
Hoodie, "s2s" for Sea to Summit, "SE846" for Shure's) and marks in a name ('Le Creuset "toughened non-stick" pan').

- Brands as their makers write them (config.MAKER_SPELLINGS, more of them): a writer's possessive or plural of the
  brand is the brand ("Grado's" is Grado's line).
- Short names (engine/data/product_aliases.json) where the threads make the product plain; the name shown is the short
  name's full name when the writers' name is just that (engine.group_products.maker_spelling).
- As a last resort a name starts with a capital, unless its maker writes it in small letters ("innisfree", config) or
  its first word has capitals of its own ("iPhone").
- Double quotation marks are no part of a name.

Every name here is a real product's, as the review found it; nothing reads data/ but the shipped lists.
"""

import pytest

from engine.group_products import maker_spelling
from engine.match_products import known_aliases, same_product


@pytest.mark.parametrize("name, category, shown", [
    ("laifen swift", "general", "Laifen Swift"),
    ("nanit cam", "general", "Nanit cam"),
    ("momcozy wrap", "general", "Momcozy wrap"),
    ("other box defender", "general", "OtterBox Defender"),
    ("Otter box", "general", "OtterBox"),
    ("Grado's headphones", "general", "Grado headphones"),
    ("Smartwool’s thicker hiking socks", "general", "Smartwool thicker hiking socks"),
    ("Oral B electric toothbrush", "general", "Oral-B electric toothbrush"),
    ("s2s fleece liner", "general", "Sea to Summit fleece liner"),
    ("SE846", "general", "Shure SE846"),
    ("G502 wireless", "general", "Logitech G502 wireless"),
    ("melly", "general", "Melanzana Micro Grid Hoodie"),
    ("Baby bjorn mini", "general", "BabyBjörn mini"),
    ("Ergo Baby Omni Air 360", "general", "Ergobaby Omni Air 360"),
    ("Grid Linen towel from Outlier", "general", "Outlier Grid Linen Towel"),
    ("babyliss nano titanium 1\" flat iron", "general", "BaBylissPRO Nano Titanium 1\" flat iron"),
    ("durston x mid 2p", "general", "Durston X-Mid 2p"),
    ("dogbed4less waterproof memory foam beds", "general", "Dogbed4less waterproof memory foam beds"),
    ("used Kenmore Elite dishwasher", "kitchen", "Kenmore Elite dishwasher"),
    ("Kenmoore fridge", "kitchen", "Kenmore fridge"),
    ("vintage Sunbeam Radiant Control toaster", "kitchen", "Sunbeam Radiant Control toaster"),
    ("vintage Toastmaster 1B14 toaster", "kitchen", "Toastmaster 1B14 toaster"),
    ("Kenwood Chef (vintage)", "kitchen", "Kenwood Chef"),
    ("full-size Hario Skerton", "kitchen", "Hario Skerton"),
    ("chef's choice electric knife sharpener", "kitchen", "Chef'sChoice electric knife sharpener"),
    ("ChefsChoice Trizor XV", "kitchen", "Chef'sChoice Trizor XV"),
    ("our place pan", "kitchen", "Our Place pan"),
    ("finex 12”", "kitchen", "Finex 12-inch skillet"),
    ("All clad saucepan", "kitchen", "All-Clad saucepan"),
    ("Amazon basics Dutch oven", "kitchen", "Amazon Basics Dutch oven"),
    ("Big Green egg", "kitchen", "Big Green Egg"),
    ("Henkels chef knife", "kitchen", "Henckels chef knife"),
    ("Spyderco sharpmaker", "kitchen", "Spyderco Sharpmaker"),
    ("Shapton pro 1500", "kitchen", "Shapton Pro 1500"),
    ("Lido 3", "kitchen", "Orphan Espresso Lido 3"),
    ("Le Creuset \"toughened non-stick\" pan", "kitchen", "Le Creuset toughened non-stick pan"),
    ("Paula’s choice 20% niacinamide", "skincare", "Paula's Choice 20% niacinamide"),
    ("vanicream moisturiser", "skincare", "Vanicream moisturiser"),
    ("sun bum sunscreen", "skincare", "Sun Bum sunscreen"),
    ("skinfood aloe watery sun water gel", "skincare", "SKINFOOD aloe watery sun water gel"),
    ("neutrogena stubborn marks retinol serum", "skincare", "Neutrogena stubborn marks retinol serum"),
    ("Inkey List caffeine eye cream", "skincare", "The INKEY List caffeine eye cream"),
    ("OleHenricksen banana bright + vitamin C under eye cream", "skincare",
     "Ole Henriksen banana bright + vitamin C under eye cream"),
    ("Estée Lauder's Advanced Night Repair", "skincare", "Estée Lauder Advanced Night Repair"),
    ("haru haru sunscreen", "skincare", "Haruharu Wonder sunscreen"),
    ("native conditioner", "haircare", "Native conditioner"),
    ("viori rice water shampoo bar", "haircare", "Viori rice water shampoo bar"),
    ("Kevyn Murphy angel shampoo", "haircare", "KEVIN.MURPHY angel shampoo"),
    ("HairStory Rich New Wash", "haircare", "Hairstory New Wash Rich"),
    ("Giovanni Tea Tree Triple Threat", "haircare", "Giovanni Tea Tree Triple Treat"),
])
def test_a_name_is_shown_as_its_maker_writes_it(name, category, shown):
    assert maker_spelling(name, category) == shown


@pytest.mark.parametrize("name, category, more", [
    # Its maker's small letters, as the brand-lines list writes them (answers pass its brands).
    ("innisfree Retinol Cica Moisture Recovery Serum", "skincare", ("innisfree",)),
    ("iPhone 11", "general", ()),  # capitals of its own
])
def test_a_maker_who_writes_it_in_small_letters_keeps_them(name, category, more):
    assert maker_spelling(name, category, more) == name


def test_a_name_in_small_letters_starts_with_a_capital_as_a_last_resort():
    assert maker_spelling("zyvo lunchbox", "general") == "Zyvo lunchbox"


@pytest.mark.parametrize("a, b, category", [
    ("other box defender", "OtterBox Defender", "general"),
    ("melly", "Melanzana Micro Grid Hoodie", "general"),
    ("vintage Sunbeam Radiant Control toaster", "Sunbeam Radiant Control toaster", "kitchen"),
    ("Kenwood Chef (vintage)", "Kenwood Chef", "kitchen"),
    ("Kenmoore", "Kenmore", "kitchen"),
    ("Lido 3", "Orphan Espresso Lido 3", "kitchen"),
    ("Giovanni Tea Tree Triple Threat", "Giovanni tea tree triple treat", "haircare"),
])
def test_the_short_names_join_the_writers_names_to_their_product(a, b, category):
    assert same_product(a, b, known_aliases()[category])
