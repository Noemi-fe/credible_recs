"""The general category's backpacks and its home types' communities (15 Oct 2026, the general-quality builder; Claude's
calls, reported to Noemi).

1. A plain backpack (everyday, travel, laptop, school) is the "backpack" type, daypacks included; a hiking backpack
   stays its own type, a hiking daypack with it; "laptop backpack" is a backpack, as the routing audit placed it (g50).
2. Furniture, lamps and bedding are searched in the communities where people ask what to buy first (r/furniture,
   r/Lighting, r/Bedding, r/BuyItForLife), r/HomeDecorating, whose threads are mostly decorating talk, last. Each was
   checked on Arctic Shift on 15 Oct 2026: it exists and had 25 new posts in the last two days.

Module 1 runs on its rules here (the open model is off in tests).
"""

from engine.config import SUBREDDITS
from engine.query import parse_query
from engine.sources import finder_terms


def routed(text: str) -> tuple[str | None, str | None]:
    query = parse_query(text)
    return query.product_type, query.department


# --- 1. Backpacks ---

def test_a_daypack_is_a_backpack_and_a_hiking_daypack_a_hiking_backpack():
    assert routed("daypack") == ("backpack", "clothing")
    assert routed("packable daypack for travel") == ("backpack", "clothing")
    assert routed("day pack for the city") == ("backpack", "clothing")
    assert routed("hiking daypack") == ("hiking backpack", "outdoor")
    assert routed("daypack for hiking") == ("hiking backpack", "outdoor")
    assert routed("hiking backpack") == ("hiking backpack", "outdoor")


def test_everyday_travel_and_laptop_backpacks_are_backpacks():
    for text in ("backpack", "travel backpack for one bag travel", "laptop backpack for commuting", "rucksack",
                 "school bag"):
        assert routed(text) == ("backpack", "clothing"), text


def test_a_backpack_sprayer_is_no_backpack():
    assert parse_query("backpack sprayer").product_type != "backpack"


def test_backpacks_are_searched_in_onebag_and_backpacks_first():
    assert parse_query("travel backpack").subreddits[:2] == ["onebag", "backpacks"]
    assert "backpacks" in SUBREDDITS["general"]
    assert {"daypack", "backpack"} <= set(finder_terms("backpack"))


# --- 2. Home types' communities ---

def test_furniture_lamps_and_bedding_are_searched_where_people_ask_what_to_buy_first():
    assert parse_query("sofa that lasts").subreddits[0] == "furniture"
    assert parse_query("armchair").subreddits[0] == "furniture"
    assert parse_query("dining table").subreddits[0] == "furniture"
    assert parse_query("lamp for reading").subreddits[0] == "Lighting"
    assert parse_query("bed sheets").subreddits[:2] == ["BuyItForLife", "Bedding"]
    assert parse_query("curtains").subreddits[0] == "BuyItForLife"
    for text in ("sofa", "armchair", "lamp", "curtains", "dining table", "bed sheets", "bookshelf", "bed frame",
                 "chest of drawers", "wardrobe", "tv stand", "duvet", "duvet cover"):
        subreddits = parse_query(text).subreddits
        assert subreddits[-1] == "HomeDecorating", text  # decorating talk: searched last
        assert set(subreddits) <= set(SUBREDDITS["general"]), text


def test_the_new_communities_are_decided_general_subreddits():
    assert {"furniture", "Lighting", "Bedding", "backpacks"} <= set(SUBREDDITS["general"])


# --- 3. A type named in the plural is no need of its own request (found reading the general answers) ---

def test_a_types_plural_name_is_no_need():
    # "Recommended by 3 credible voices, 1 of them about headphones." had been the reason line of headphone picks: the
    # request's "headphones", trimmed to "headphone", wasn't taken for the product's own word.
    from engine.sources import need_words

    assert need_words(parse_query("headphones")) == []
    assert need_words(parse_query("bed sheets")) == []
    assert need_words(parse_query("running shoes for flat feet")) == ["flat", "feet"]
    assert need_words(parse_query("dishwasher tablets that don't leave residue")) == ["leave", "residue"]
