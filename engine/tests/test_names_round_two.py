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
    # Changed on purpose 18 Oct 2026 (the ws-names builder): writers' "G502" is the G502 family (Hero, Lightspeed, X),
    # and written out as "Logitech G502" it became a line that left the mouse answer; the short name is gone, and the
    # price list's own name is shown. Was: "Logitech G502 wireless".
    ("G502 wireless", "general", "G502 wireless"),
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
    # Changed on purpose 18 Oct 2026 (the ws-names builder): the short name had split "vintage Toastmaster toaster" from
    # its 1B14 (the price list's name says "vintage": a toaster bought vintage on purpose). Was: "Toastmaster 1B14
    # toaster".
    ("vintage Toastmaster 1B14 toaster", "kitchen", "Vintage Toastmaster 1B14 toaster"),
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
    # Changed on purpose 18 Oct 2026 (the ws-names builder): the short name had made the brand's sunscreen line a
    # product; config.MAKER_SPELLINGS writes the brand instead. Was: "Haruharu Wonder sunscreen".
    ("haru haru sunscreen", "skincare", "Haruharu sunscreen"),
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


# --- Round three (18 Oct 2026, the ws-names builder): every library name spelled with the 17 Oct rules ---

@pytest.mark.parametrize("name, category, shown", [
    # Brands a letter apart are two brands, never a slip of one another (engine.match_products.NOT_SLIPS).
    ("Graco Turn2Me", "general", "Graco Turn2Me"),
    ("graco 4ever", "general", "Graco 4ever"),
    ("Babylist bottle box", "general", "Babylist bottle box"),
    ("Molly Mutt canvas covers", "general", "Molly Mutt canvas covers"),
    ("Milly Moon", "general", "Milly Moon"),
    # A beginning written as its maker writes it keeps the name's own words after it: "Series", "ONE+", "The" and a
    # model number are no filler.
    ("Bosch Series 4 GSN36VWFPG", "kitchen", "Bosch Series 4 GSN36VWFPG"),
    ("Ryobi ONE+ 18V Cordless 3-Tool Combo Kit", "general", "Ryobi ONE+ 18V Cordless 3-Tool Combo Kit"),
    ("Cosrx The 6 Peptide", "skincare", "COSRX The 6 Peptide"),  # COSRX as the brand-lines list writes it, below
    ("Huepar 9011G", "general", "Huepar 9011G"),
    ("Klein line laser", "general", "Klein line laser"),
    # A short name of a longer beginning still wins, every word said: the BaBylissPRO, Spyderco's Sharpmaker.
    ("Spyderco sharpmaker", "kitchen", "Spyderco Sharpmaker"),
    ("KitchenAid Pro Line 7-quart", "kitchen", "KitchenAid Professional 7-quart"),
    # Where and how it was bought is no part of a name.
    ("Vitamix from Costco", "kitchen", "Vitamix"),
    ("KitchenAid Pro 6-quart (Costco)", "kitchen", "KitchenAid Professional 6-quart"),
    ("Danby from Costco", "general", "Danby"),
    ("Hisense from Sam's Club", "general", "Hisense"),
    ("KitchenAid stand mixer (refurbished)", "kitchen", "KitchenAid stand mixer"),
    # A maker's letters and a model code's in capitals.
    ("lg fridge", "kitchen", "LG fridge"),
    ("ghd platinum", "general", "GHD platinum"),
    ("h&m jeans", "general", "H&M jeans"),
    ("hd600", "general", "HD600"),
    ("mr coffee", "kitchen", "Mr coffee"),
    # Makers who write their brand in small letters, or capitals of their own.
    ("Innisfree Jeju Orchid Eye Cream", "skincare", "Innisfree Jeju Orchid Eye Cream"),  # writers' capitals stay
    ("elf holy hydration eye cream", "skincare", "e.l.f. holy hydration eye cream"),
    ("iunik centella calming gel cream", "skincare", "iUNIK centella calming gel cream"),
    ("got2b Glued Blasting Freeze Spray", "haircare", "got2b Glued Blasting Freeze Spray"),
    ("Ogx coconut miracle oil", "haircare", "OGX coconut miracle oil"),
    ("darn tough socks", "general", "Darn Tough socks"),
    ("Redwing Iron Ranger", "general", "Red Wing Iron Ranger"),
    # Writers' fragments with a plain product behind them (the short names).
    ("wave", "general", "Leatherman Wave"),
    ("squeeze", "general", "Sawyer Squeeze"),
    ("la creuset pot", "kitchen", "Le Creuset pot"),
    ("bjorn older model", "general", "BabyBjörn Bouncer"),
])
def test_round_three_names_are_shown_as_their_makers_write_them(name, category, shown):
    assert maker_spelling(name, category, more=("COSRX",) if category == "skincare" else ()) == shown


def test_the_price_and_facts_lists_name_comes_before_a_short_names_full_name():
    # The UK's "CeraVe Hydrating Cleanser" (the price and facts lists; 10 Oct 2026) over the short name's full name.
    curated = ("CeraVe Hydrating Cleanser",)
    assert maker_spelling("CeraVe Hydrating Facial Cleanser", "skincare", whole=curated) == "CeraVe Hydrating Cleanser"


def test_a_facts_lists_small_letters_keep_a_writers_small_letters():
    curated = ("innisfree Retinol Cica Moisture Recovery Serum",)
    assert maker_spelling("innisfree Lip Sleeping Mask", "skincare", whole=curated) == "innisfree Lip Sleeping Mask"


def test_a_lists_small_letters_keep_a_name_in_them():
    # A first word a list writes in small letters is the maker's style, never capitalised as a last resort.
    assert maker_spelling("beplain mung bean cleanser", "skincare", whole=("beplain Mung Bean pH-Balanced Cleansing Foam",)) == (
        "beplain mung bean cleanser")


def test_a_lists_name_keeps_its_letters_so_its_price_is_found():
    # An answer finds a product's price, availability, page and image by the name it is shown under, so a list's name
    # written with a slip is shown as the list writes it ("OleHenricksen ...", the price list's: respelled, the eye
    # cream lost its £38 price and a £35 budget no longer left it out); the list is the place to correct it. Capitals
    # alone may still change, and a writer's own name is still respelled (the round-two list above).
    curated = ("OleHenricksen banana bright + vitamin C under eye cream", "CeraVe Hydrating Cleanser",
               "1ZPresso K Plus")
    assert maker_spelling("OleHenricksen banana bright + vitamin C under eye cream", "skincare", whole=curated) == (
        "OleHenricksen banana bright + vitamin C under eye cream")
    assert maker_spelling("CeraVe Hydrating Facial Cleanser", "skincare", whole=curated) == "CeraVe Hydrating Cleanser"
    assert maker_spelling("1zpresso k plus", "kitchen", whole=curated) == "1Zpresso K Plus"


@pytest.mark.parametrize("name, category, more, shown", [
    # "brand" right after a maker's name, before the rest of the name, is filler (main's rules had left it out; the
    # 18 Oct order of beginnings had kept it): the product's own words stay.
    ("crock pot brand pressure cooker", "kitchen", ("Crock-Pot",), "Crock-Pot pressure cooker"),
    ("Keen brand boots", "general", ("Keens",), "Keens boots"),
    ("Weber brand grill", "kitchen", (), "Weber grill"),
    # At the end it says the maker is meant, as a brand pick's shown name already leaves it (unchanged here).
    ("Kirkland brand", "general", (), "Kirkland brand"),
])
def test_brand_after_a_makers_name_is_filler(name, category, more, shown):
    assert maker_spelling(name, category, more) == shown
