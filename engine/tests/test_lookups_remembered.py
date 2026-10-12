"""Price and facts lookups, remembered while the lists don't change (latency, 12 Oct 2026).

Each answer looked every product up in the price list and the facts list by comparing its name with every entry's
(module 4's rules): about 50,000 comparisons, 2 to 4 seconds an answer. The lists change only when a researcher adds
entries, so now each list is read once and kept while its file is unchanged, and each product's entries are worked out
once per list. These tests make sure nothing remembered is ever stale or mixed up.
"""

import json
import os
import time

from engine import memo
from engine.prices import Price, entries_for, find_availability, find_price, load_prices
from engine.product_facts import ProductFacts, find_facts, load_product_facts
from engine.tests.test_prices import entry, price, write_prices


def settled(path):
    """The file as if written a minute ago: a file changed just now is read again until it has been still a while."""
    past = time.time_ns() - 60 * 10**9
    os.utime(path, ns=(past, past))
    return path


def test_an_unchanged_price_list_is_read_once(tmp_path, monkeypatch):
    path = settled(write_prices(tmp_path, [entry()]))
    first = load_prices(path)
    assert load_prices(path) is first


def test_a_price_list_changed_since_is_read_again(tmp_path):
    path = settled(write_prices(tmp_path, [entry()]))
    assert [p.price for p in load_prices(path)] == [120.0]
    write_prices(tmp_path, [entry(price=99.0)])
    assert [p.price for p in load_prices(path)] == [99.0]


def test_a_price_list_rewritten_at_the_same_size_and_moment_is_read_again(tmp_path):
    # A disk that records times in steps: written, read at once, rewritten within the same step at the same size.
    path = write_prices(tmp_path, [entry(price=120.0)])
    written = path.stat().st_mtime_ns
    assert [p.price for p in load_prices(path)] == [120.0]
    write_prices(tmp_path, [entry(price=130.0)])
    os.utime(path, ns=(written, written))
    assert [p.price for p in load_prices(path)] == [130.0]


def test_a_lookup_asked_again_gives_the_same_answer_and_a_list_of_its_own(tmp_path):
    prices = [price("Zojirushi kettle", 120.0), price("Fellow Stagg EKG kettle", 150.0)]
    first = entries_for("Zojirushi kettle", "kitchen", prices)
    first.append("changed by the caller")
    again = entries_for("Zojirushi kettle", "kitchen", prices)
    assert [p.product for p in again] == ["Zojirushi kettle"]
    assert find_price("Zojirushi kettle", "kitchen", prices).price == 120.0


def test_two_price_lists_never_answer_for_each_other():
    cheap = [price("Zojirushi kettle", 80.0)]
    dear = [price("Zojirushi kettle", 180.0)]
    assert find_price("Zojirushi kettle", "kitchen", cheap).price == 80.0
    assert find_price("Zojirushi kettle", "kitchen", dear).price == 180.0
    assert find_price("Zojirushi kettle", "kitchen", cheap).price == 80.0


def test_a_lookup_is_worked_out_once_per_list(monkeypatch):
    from engine import prices as prices_module

    calls = []
    real = prices_module.same_product
    monkeypatch.setattr(prices_module, "same_product", lambda *a: calls.append(1) or real(*a))
    prices = [price("Zojirushi kettle", 120.0), price("Dualit kettle", 60.0)]
    for _ in range(3):
        find_availability("Zojirushi kettle", "kitchen", prices)
        find_price("Zojirushi kettle", "kitchen", prices)
    assert len(calls) == 2  # one comparison per entry, once


def test_many_lists_are_each_answered_rightly():
    lists = [[price("Zojirushi kettle", float(n + 1))] for n in range(30)]
    for n, prices in enumerate(lists):
        assert find_price("Zojirushi kettle", "kitchen", prices).price == n + 1
    for n, prices in enumerate(lists):
        assert find_price("Zojirushi kettle", "kitchen", prices).price == n + 1


def test_a_list_given_as_a_one_off_iterable_is_still_answered(tmp_path):
    prices = [price("Zojirushi kettle", 120.0)]
    assert find_price("Zojirushi kettle", "kitchen", iter(prices)).price == 120.0
    assert find_price("Zojirushi kettle", "kitchen", (p for p in prices)).price == 120.0


# --- Facts ---

def facts(product: str, **values) -> ProductFacts:
    return ProductFacts.model_validate({"product": product, "category": "kitchen", "product_type": "frying pan",
                                        "sources": ["https://maker.example/page"], "checked_on": "2026-10-10",
                                        "facts": values})


def write_facts(tmp_path, entries: list[ProductFacts]):
    path = tmp_path / "product_facts.json"
    path.write_text(json.dumps({"facts": [e.model_dump(mode="json", exclude_none=True) for e in entries]}),
                    encoding="utf-8")
    return path


def test_an_unchanged_facts_list_is_read_once_and_a_changed_one_again(tmp_path):
    path = settled(write_facts(tmp_path, [facts("GreenPan Valencia Pro", pfas_free=True)]))
    first = load_product_facts(path)
    assert load_product_facts(path) is first
    write_facts(tmp_path, [facts("GreenPan Valencia Pro", pfas_free=False)])
    assert load_product_facts(path)[0].facts["pfas_free"] is False


def test_facts_lookups_never_mix_two_lists():
    yes = [facts("GreenPan Valencia Pro", pfas_free=True)]
    no = [facts("GreenPan Valencia Pro", pfas_free=False)]
    assert find_facts("GreenPan Valencia Pro", "kitchen", yes).facts["pfas_free"] is True
    assert find_facts("GreenPan Valencia Pro", "kitchen", no).facts["pfas_free"] is False
    assert find_facts("GreenPan Valencia Pro", "kitchen", yes, "frying pan").facts["pfas_free"] is True
    assert find_facts("GreenPan Valencia Pro", "kitchen", yes, "saucepan") is None


def test_the_memo_tells_lists_apart_by_identity_not_by_content():
    table = memo.PerList()
    a, b = [1, 2], [1, 2]
    table.of(a)["x"] = "a's"
    assert table.of(b).get("x") is None
    assert table.of(a)["x"] == "a's"
