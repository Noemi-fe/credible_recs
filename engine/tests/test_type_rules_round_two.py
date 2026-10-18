"""Type rules a decided rule covers, round two (17 Oct 2026, the ws-names builder; Claude's technical calls within the
decided rule of 10 Oct 2026, reported to Noemi): what holds, covers, sharpens or refills a product never counts for the
product itself (config.OTHER_TYPE_WORDS).

- A razor blade is no razor: the AI's "razor blade" mentions are left out of a razor answer like a set's (the word
  "blade" joins config.OTHER_TYPE_WORDS), and so is a product every writer names as blades ("Derby blades"), whatever
  type the AI gave it: the day's two razor answers had it as their second pick. Module 1 no longer reads "razor blades"
  as a razor request.
- A stock pot is no saucepan, though "pot" is a saucepan's clue word (engine.query's look-alikes).

Every library, product and writer here is made up but for the review's real names.
"""

from engine.config import OTHER_TYPE_WORDS
from engine.group_products import ProductMention, group_products, library_ranges
from engine.query import classify
from engine.sources import mentions_product


def mentions(names_types, category="general"):
    return [ProductMention(f"1t{i % 3}", f"c{i}", name, category, "recommend", product_type)
            for i, (name, product_type) in enumerate(names_types)]


def grouped(names_types, product_type, category="general"):
    ms = mentions(names_types, category)
    return group_products(ms, product_type=product_type, ranges=library_ranges(ms))


def ai_types(group) -> set[str]:
    return {m.product_type for m in group.mentions}


def test_a_blade_is_a_word_for_what_goes_with_a_product():
    assert "blade" in OTHER_TYPE_WORDS


def test_a_product_its_writers_name_as_blades_is_blades_in_a_razor_answer():
    groups = grouped([("Derby blades", "razor"), ("Derby blades", "razor"), ("Derby blades", "razor blade"),
                      ("Merkur 34C", "razor"), ("Merkur 34C", "razor")], "razor")
    derby = next(g for g in groups if "Derby blades" in g.names)
    assert ai_types(derby) == {"razor blade"}
    merkur = next(g for g in groups if "Merkur 34C" in g.names)
    assert ai_types(merkur) == {"razor"}


def test_a_name_with_the_word_after_with_is_still_the_product():
    groups = grouped([("Hydro Flask with straw lid", "water bottle"), ("Hydro Flask with straw lid", "water bottle")],
                     "water bottle", "general")
    assert ai_types(groups[0]) == {"water bottle"}


def test_a_word_of_the_types_own_names_is_never_another_thing():
    # A case in a phone case answer, a sharpener in a knife sharpener answer, a set where the type's names say set.
    for name, product_type in (("OtterBox Defender case", "phone case"), ("Work Sharp sharpener", "knife sharpener"),
                               ("Bowflex dumbbell set", "dumbbells"), ("Kenwood stand", "stand mixer")):
        groups = grouped([(name, product_type), (name, product_type)], product_type,
                         "kitchen" if product_type in ("knife sharpener", "stand mixer") else "general")
        assert ai_types(groups[0]) == {product_type}, name


def test_a_kit_or_a_bundle_is_left_to_the_ais_type():
    # A console bundle is a console: only the AI's own type decides these (config.OTHER_TYPE_WORDS, as before).
    groups = grouped([("Nintendo Switch OLED bundle", "gaming console")] * 2, "gaming console")
    assert ai_types(groups[0]) == {"gaming console"}


def test_without_a_requested_type_nothing_is_retyped():
    ms = mentions([("Derby blades", "razor"), ("Derby blades", "razor")])
    assert ai_types(group_products(ms)[0]) == {"razor"}


def test_razor_blades_are_no_razor_request():
    assert classify("razor blades for a safety razor").product_type != "razor"
    assert classify("safety razor for a beginner").product_type == "razor"


def test_a_stock_pot_is_no_saucepan():
    assert not mentions_product("Vollrath stock pot", "saucepan")
    assert not mentions_product("a 12 quart stockpot", "saucepan")
    assert mentions_product("a heavy pot for sauces", "saucepan")
    assert classify("stock pot for making broth").product_type != "saucepan"
