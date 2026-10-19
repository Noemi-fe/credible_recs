"""The reason line's needs, as a shopper reads them (17 Oct 2026, the converge round, item 5).

The reason says how many credible recommendations talk about what the request asks for ("3 of them about sensitive
skin"). From the 17 Oct sweep: "non stick pan without teflon that lasts" said "4 of them about non stick or teflon", a
must-have asked for in other words and the product's own name; "fridge freezer that's quiet" said "about freezer",
"cordless drill for diy" "about cordless or diy". Now a must-have the request asks for is named as one ("about
PFAS-free"), and in kitchen and general answers the words of the product's own name the request uses (its type's
names: "non stick pan", "fridge freezer", "cordless drill") are never named, nor counted. Skincare and haircare
requests already leave them out of their needs (engine.needs.judged_needs). Which words are needs stays module 1's.

All text is made up (engine/tests/ranking_factories.py).
"""

from engine.answer import write_answer
from engine.needs import judged_needs
from engine.product_facts import request_asks
from engine.query import parse_query
from engine.rank import rank_products
from engine.tests.ranking_factories import bodies_for, mentions


def reason(request: str, needs_talked_about: tuple[str, ...]) -> str:
    """The first pick's reason for `request`, its three credible recommendations each talking about those needs."""
    query = parse_query(request)
    items = mentions(3, "Acme thing", category=query.category, needs=needs_talked_about)
    answer = write_answer(rank_products(items, query.category), bodies_for(*items), query.product_type,
                          asks=request_asks(query), needs=judged_needs(query), request=query.text)
    return answer.picks[0].reason


def test_a_must_have_asked_for_in_other_words_is_named_as_the_must_have():
    said = reason("non stick pan without teflon that lasts", ("non", "stick", "teflon"))
    assert "teflon" not in said.lower() and "non stick" not in said
    # Changed on 18 Oct 2026 (deliberately; it said "about PFAS-free" alone, "non stick" being the product's own name):
    # the request asks for a non-stick pan (a must-have, checked against the facts) though its words are the product's
    # name too, so it is named as the must-have, as "non-stick frying pan without PFAS" is just below.
    assert said.endswith("3 of them about non-stick or PFAS-free.")
    said = reason("non-stick frying pan without PFAS that actually lasts", ("non-stick", "PFAS"))
    assert said.endswith("3 of them about non-stick or PFAS-free.")
    said = reason("28cm frying pan, non stick but pfas free, £30-60", ("non", "stick", "pfas"))
    assert said.endswith("3 of them about non-stick or PFAS-free.")


def test_kitchen_and_general_reasons_never_name_the_products_own_words():
    assert reason("fridge freezer that's quiet", ("freezer", "quiet")).endswith("3 of them about noise.")
    assert reason("cordless drill for diy", ("cordless", "diy")).endswith("3 of them about diy.")
    # Only the product's own words: nothing is said when they are all the comments talk about.
    assert "about" not in reason("cordless drill for diy", ("cordless",))


def test_skincare_reasons_are_as_before():
    said = reason("fragrance-free moisturiser for very dry skin in winter", ("fragrance-free", "dry", "winter"))
    assert said.endswith("3 of them about fragrance, dry skin or winter.")
