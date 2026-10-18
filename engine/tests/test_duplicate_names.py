"""The same product twice in one answer (17 Oct 2026, the ws-names builder): the eval check over a sweep's answers
(engine/duplicate_names.py) and the short names that join the products the 16 Oct review found shown twice.

Every answer here is made up but for the real names of the review's products; the check reads no data/ but the shipped
short names and the brands module 1 knows.
"""

import json

from engine.duplicate_names import (
    BRAND_TWO_WAYS, COUNTED, LINE_AND_PRODUCT, TWO_LINES, findings, main, report,
)
from engine.match_products import known_aliases, product_words, same_product


def answer(product_type: str, category: str, picks=(), worth=(), skip=()) -> dict:
    return {"category": category, "product_type": product_type, "picks": [{"name": n} for n in picks],
            "worth_a_look": [{"name": n} for n in worth], "skip": [{"name": n} for n in skip]}


def kinds(found) -> list[tuple[str, tuple[str, str]]]:
    return [(f.kind, f.names) for f in found]


# --- The check ---

def test_a_model_written_without_its_maker_beside_it_is_one_product_twice():
    found = findings("baby carrier", answer("baby carrier", "general",
                                            picks=["Ergobaby Embrace carrier", "Embrace mesh version", "Baby Bjorn Mini"]),
                     brands=[])
    assert kinds(found) == [(COUNTED, ("Ergobaby Embrace carrier", "Embrace mesh version"))]


def test_one_combination_stone_named_two_ways_is_one_product_twice():
    found = findings("sharpener", answer("knife sharpener", "kitchen", worth=[
        "King KDS 1000/6000 combo stone", "double sided 1000/6000 King whetstone", "Shapton Pro 1500"]), brands=[])
    assert kinds(found) == [(COUNTED, ("King KDS 1000/6000 combo stone", "double sided 1000/6000 King whetstone"))]


def test_two_makers_or_two_models_are_two_products():
    found = findings("cleanser", answer("cleanser", "skincare", picks=[
        "CeraVe Hydrating Cleanser", "CeraVe Hydrating Cream-to-Foam Cleanser", "Vichy Dercos cleanser"]), brands=[])
    assert found == []
    found = findings("e-reader", answer("e-reader", "general", picks=["Kindle Paperwhite 3", "Kindle Paperwhite 4"]),
                     brands=[])
    assert found == []


def test_a_line_beside_its_own_product_and_two_lines_are_shown_not_counted():
    found = findings("mower", answer("lawn mower", "general", picks=["Greenworks lawn mower line"],
                                     worth=["Greenworks 80v"]), brands=[])
    assert kinds(found) == [(LINE_AND_PRODUCT, ("Greenworks lawn mower line", "Greenworks 80v"))]
    found = findings("toaster", answer("toaster", "kitchen", picks=["Dualit Classic toaster line"],
                                       worth=["Dualit 4-slice toaster line"]), brands=[])
    assert kinds(found) == [(TWO_LINES, ("Dualit Classic toaster line", "Dualit 4-slice toaster line"))]


def test_one_brand_written_two_ways_is_shown():
    found = findings("grinder", answer("coffee grinder", "kitchen", picks=["1Zpresso JX-Pro"], worth=["1ZPresso K Plus"]),
                     brands=[])
    assert kinds(found) == [(BRAND_TWO_WAYS, ("1Zpresso JX-Pro", "1ZPresso K Plus"))]


def test_skip_these_is_compared_with_itself_only():
    found = findings("x", answer("toaster", "kitchen", picks=["Dualit Classic toaster"], skip=["Dualit Classic"]),
                     brands=[])
    assert found == []


def test_the_report_counts_answers_showing_one_product_twice(tmp_path, capsys):
    rows = [{"request": "baby carrier", "json": {"answer": answer("baby carrier", "general",
                                                                   picks=["Ergobaby Embrace", "Embrace mesh"])}},
            {"request": "not answered", "json": {"answer": None}}]
    path = tmp_path / "sweep.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    lines, counts = report([path])
    assert counts["answers showing one product twice"] == 1 and len(lines) == 1
    assert main([str(path)]) == 0 and "one product twice" in capsys.readouterr().out


# --- The short names that join them (engine/data/product_aliases.json) ---

def test_the_ergobaby_embrace_written_any_way_is_one_product():
    aliases = known_aliases()["general"]
    for name in ("Embrace", "Embrace mesh version", "Ergo embrace", "ergo baby embrace", "Ergo Baby Embrace"):
        assert same_product(name, "Ergobaby Embrace", aliases), name


def test_a_paperwhite_is_a_kindle_paperwhite():
    aliases = known_aliases()["general"]
    assert product_words("paperwhite", aliases) == ["kindle", "paperwhite"]
    assert same_product("Paperwhite 3", "Kindle Paperwhite 3", aliases)


def test_the_weber_spirit_written_without_weber_is_the_weber_spirit():
    aliases = known_aliases()["kitchen"]
    assert product_words("Spirit II", aliases) == ["weber", "spirit", "ii"]
    assert product_words("spirit", aliases) == ["weber", "spirit"]


def test_the_king_1000_6000_written_any_way_is_one_stone():
    aliases = known_aliases()["kitchen"]
    kds = product_words("King KDS 1000/6000", aliases)
    for name in ("King 1000/6000", "king 1k/6k", "double sided 1000/6000 King", "double sided King whetstone, 1000/6000"):
        assert product_words(name, aliases)[:len(kds)] == kds, name


def test_a_barbecue_or_a_stone_named_with_its_types_other_names_is_the_name_alone():
    # config.TYPE_SYNONYMS (17 Oct 2026): "grill" and "BBQ" for a barbecue, "stone" and "combo" for a sharpener's
    # stones; the made-up mentions below are of real names.
    from engine.group_products import ProductMention, group_products, library_ranges

    def grouped(names, product_type, category="kitchen"):
        mentions = [ProductMention(f"1t{i}", f"c{i}", n, category, "recommend", product_type) for i, n in enumerate(names)]
        return group_products(mentions, product_type=product_type, ranges=library_ranges(mentions))

    groups = grouped(["Weber", "Weber BBQ", "Weber grills", "Weber gas grill", "Weber Q", "Weber Q"], "barbecue")
    weber = next(g for g in groups if "Weber BBQ" in g.names)
    assert weber.loose and set(weber.names) == {"Weber", "Weber BBQ", "Weber grills", "Weber gas grill"}
    groups = grouped(["King KDS 1000/6000", "King KDS 1000/6000 combo stone", "King 1000/6000", "Shapton Pro 1500"],
                     "knife sharpener")
    king = next(g for g in groups if "King KDS 1000/6000" in g.names)
    assert set(king.names) == {"King KDS 1000/6000", "King KDS 1000/6000 combo stone", "King 1000/6000"}
