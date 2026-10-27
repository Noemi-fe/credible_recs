"""The current model of a tech product whose reviewed model a newer one has replaced (26 Oct 2026, the names builder;
Noemi approved it in principle on 26 Oct 2026, decision 3, second part: "the current tech models named").

A pick, or an "Also worth a look" item, of a fast-moving type (config.FAST_MOVING_TYPES) whose reviewed model a newer
one of the same line has replaced shows "Current model: <model>", with the page it was read on and the day. The list is
data/current_models.json (engine/current_models.py); a model is matched by its shown name word for word, never by a
likeness; a line (not one model) counts only when most of its credible voices wrote before the current model came out.
Nothing is shown for a model that is current, a model the list doesn't know, or a type that isn't fast-moving.

Every product, page, shop and comment here is made up.
"""

import json
from datetime import date

import pytest

from engine import config
from engine.answer import answer_to_dict, render_markdown, unverified_claims
from engine.current_models import (
    CurrentModel, CurrentModelsError, find_current_model, load_current_models, released_from,
)
from engine.pipeline import answer_request
from engine.tests.test_buyable import AIR, DELL, LEGION, ROG, laptop_library
from engine.tests.test_pick_polish import FIBROX, KNIFE_REQUEST, VICTORINOX, knife_library

TODAY = date(2026, 10, 9)
PAGE = "https://maker.example/uk/aircraft"


def entry(**overrides) -> dict:
    data = {"product_type": "laptop", "category": "general", "replaced": [AIR], "current": "Maker Aircraft 14 (2026)",
            "shop": "Maker", "maker": True, "page": PAGE, "checked_on": "2026-10-26", "note": "Made up for a test."}
    return data | overrides


def write_list(tmp_path, entries):
    path = tmp_path / "current_models.json"
    path.write_text(json.dumps({"current_models": entries}), encoding="utf-8")
    return path


def listed(**overrides) -> CurrentModel:
    return CurrentModel.model_validate(entry(**overrides))


# --- The list ---

def test_a_good_entry_loads(tmp_path):
    [loaded] = load_current_models(write_list(tmp_path, [entry(released="2026-03")]))
    assert loaded.current == "Maker Aircraft 14 (2026)" and loaded.maker is True
    assert released_from(loaded) == date(2026, 3, 1)


@pytest.mark.parametrize("released, first", [("2024", date(2024, 1, 1)), ("2024-10", date(2024, 10, 1)),
                                             ("2024-10-16", date(2024, 10, 16)), (None, None)])
def test_a_release_is_read_as_the_first_day_it_could_be(released, first):
    assert released_from(listed(released=released)) == first


@pytest.mark.parametrize("bad, why", [
    ({"page": "http://maker.example/aircraft"}, "https"),
    ({"page": "https://www.reddit.com/r/laptops/comments/1abc/x/"}, "Reddit"),
    ({"page": "https://shop.example/search?q=aircraft"}, "search"),
    ({"page": "https://user:pass@maker.example/aircraft"}, "https"),
    ({"replaced": []}, "names the models"),
    ({"line": ["Maker Aircraft line"]}, "needs"),  # a line needs the day its current model came out
    ({"released": "2026-13"}, "released"),
    ({"released": "last spring"}, "released"),
    ({"current": AIR}, "current model itself"),
    ({"category": "kitchen"}, "tech"),
    ({"product_type": "Laptop"}, "lowercase"),
    ({"maker": "yes"}, "maker"),
    ({"checked_on": "yesterday"}, "checked_on"),
    ({"verdict": "better"}, "verdict"),  # unknown fields are errors
])
def test_a_malformed_entry_stops_the_list_with_its_number_and_the_problem(tmp_path, bad, why):
    with pytest.raises(CurrentModelsError) as e:
        load_current_models(write_list(tmp_path, [entry(), entry(**bad)]))
    assert "entry 2" in str(e.value) and why in str(e.value)


def test_two_entries_naming_one_product_of_one_type_are_refused(tmp_path):
    with pytest.raises(CurrentModelsError, match="entry 1 already"):
        load_current_models(write_list(tmp_path, [entry(), entry(current="Maker Aircraft 15")]))
    # The same name for another product type is another product.
    assert len(load_current_models(write_list(tmp_path, [entry(), entry(product_type="tablet")]))) == 2


def test_a_missing_or_broken_file_is_refused(tmp_path):
    with pytest.raises(CurrentModelsError):
        load_current_models(tmp_path / "nothing.json")
    (tmp_path / "bad.json").write_text("{", encoding="utf-8")
    with pytest.raises(CurrentModelsError):
        load_current_models(tmp_path / "bad.json")


def test_the_committed_list_loads_and_every_entry_is_read_from_a_page():
    entries = load_current_models()
    assert all(e.page.startswith("https://") and e.checked_on <= date.today() for e in entries)
    assert all(e.category == "general" and e.product_type in config.FAST_MOVING_TYPES for e in entries)


# --- Finding a product's entry ---

def test_a_replaced_model_is_found_by_its_shown_name_word_for_word():
    entries = [listed(replaced=["Sony WH-1000XM4"], current="Sony WH-1000XM6", product_type="headphones")]
    for name in ("Sony WH-1000XM4", "sony wh-1000xm4", "Sony  WH-1000XM4"):
        assert find_current_model([name], "general", "headphones", entries) == (entries[0], "replaced")


@pytest.mark.parametrize("name, type_", [
    ("Sony WH-1000XM5", "headphones"),  # one letter from the listed model, and another model
    ("Sony WH-1000XM4 Wireless Headset", "headphones"),  # more than the name: not the same product
    ("Sony WH-1000XM6", "headphones"),  # the current model itself
    ("Sony WH-1000XM4", "earbuds"),  # another product type
])
def test_a_likeness_is_never_a_match(name, type_):
    entries = [listed(replaced=["Sony WH-1000XM4"], current="Sony WH-1000XM6", product_type="headphones")]
    assert find_current_model([name], "general", type_, entries) is None


def test_any_of_a_products_shown_names_may_find_it_and_the_newest_check_wins():
    old = listed(replaced=["Old Name"], checked_on="2026-10-20")
    new = listed(replaced=["Maker Aircraft 13 Pro"], current="Maker Aircraft 15", checked_on="2026-10-26")
    assert find_current_model(["Maker Aircraft 13 Pro", "Old Name"], "general", "laptop", [old, new]) == (new, "replaced")
    assert find_current_model([], "general", "laptop", [old]) is None
    assert find_current_model(["Old Name"], "general", None, [old]) is None


# --- The answer ---

def threads_of(first: str = AIR) -> dict:
    """The default laptop threads' two best-praised laptops, an `first` praised three times in two threads (a pick)."""
    return {
        "1lap001": ("Best laptop to buy?", "2023-05-02T09:00:00Z", "laptops", [
            ("l1a", first, 4), ("l1b", LEGION, 4), ("l1c", ROG, 3), ("l1d", DELL, 4), ("l1e", "Maker Skyline 15", 2)]),
        "1lap002": ("Which laptop lasts?", "2022-01-04T09:00:00Z", "BuyItForLife", [
            ("l2a", first, 3), ("l2b", LEGION, 3), ("l2c", ROG, 4), ("l2d", DELL, 3), ("l2e", "Maker Skyline 15", 3)]),
        "1lap003": ("Laptop that lasts for university?", "2022-06-07T09:00:00Z", "SuggestALaptop", [
            ("l3a", first, 5), ("l3b", LEGION, 2), ("l3c", ROG, 2)]),
    }


def laptops(tmp_path, entries, **kwargs):
    return answer_request("laptop", library_dir=laptop_library(tmp_path, threads_of()), prices=[], product_pages=[],
                          product_facts=[], brand_lines=[], today=TODAY, current_models=entries, **kwargs)


def shown_items(result):
    return {item.name: item for item in [*result.answer.picks, *result.answer.worth_a_look]}


def test_a_pick_whose_reviewed_model_was_replaced_shows_the_current_model_its_page_and_the_day(tmp_path):
    result = laptops(tmp_path, [listed()])
    pick = shown_items(result)[AIR]
    assert pick.current_model is not None
    assert pick.current_model.text == "Current model: Maker Aircraft 14 (2026)"
    assert (pick.current_model.link_text, pick.current_model.url) == ("Maker page", PAGE)
    assert (pick.current_model.checked, pick.current_model.checked_on) == ("checked 26 Oct 2026", "2026-10-26")
    assert unverified_claims(result.answer, result.bodies) == []


def test_no_other_product_shows_one(tmp_path):
    result = laptops(tmp_path, [listed()])
    assert [name for name, item in shown_items(result).items() if item.current_model] == [AIR]


def test_the_text_and_the_json_say_it_too(tmp_path):
    result = laptops(tmp_path, [listed()])
    text = render_markdown(result.answer)
    assert "Current model: Maker Aircraft 14 (2026)" in text and f"[Maker page]({PAGE}) · checked 26 Oct 2026" in text
    data = answer_to_dict(result.answer)
    shown = [p["current_model"] for p in data["picks"] + data["worth_a_look"] if p["current_model"]]
    assert shown == [{"text": "Current model: Maker Aircraft 14 (2026)", "model": "Maker Aircraft 14 (2026)",
                      "link_text": "Maker page", "url": PAGE, "shop": "Maker", "checked": "checked 26 Oct 2026",
                      "checked_on": "2026-10-26"}]


def test_an_also_worth_a_look_item_shows_it_too(tmp_path):
    result = laptops(tmp_path, [listed(replaced=["Maker Skyline 15"], current="Maker Skyline 16")])
    items = {item.name: item for item in result.answer.worth_a_look}
    assert items["Maker Skyline 15"].current_model.text == "Current model: Maker Skyline 16"


def test_nothing_is_shown_for_a_current_model_or_one_we_could_not_check(tmp_path):
    assert all(item.current_model is None for item in shown_items(laptops(tmp_path / "a", [])).values())
    elsewhere = [listed(replaced=["Maker Cirrus 14"])]  # a model that is not shown
    assert all(item.current_model is None for item in shown_items(laptops(tmp_path / "b", elsewhere)).values())
    already = [listed(replaced=["Maker Aircraft 12"], current=AIR)]  # the shown model is the current one
    assert all(item.current_model is None for item in shown_items(laptops(tmp_path / "c", already)).values())


def test_a_type_that_is_not_fast_moving_never_shows_one(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FAST_MOVING_TYPES", tuple(t for t in config.FAST_MOVING_TYPES if t != "laptop"))
    monkeypatch.setattr("engine.sources.FAST_MOVING_TYPES", config.FAST_MOVING_TYPES)
    assert all(item.current_model is None for item in shown_items(laptops(tmp_path, [listed()])).values())


def test_the_answer_reads_the_committed_list_when_none_is_given(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr("engine.pipeline.load_current_models", lambda: seen.append("read") or [listed()])
    result = answer_request("laptop", library_dir=laptop_library(tmp_path, threads_of()), prices=[], product_pages=[],
                            product_facts=[], brand_lines=[], today=TODAY)
    assert seen and shown_items(result)[AIR].current_model is not None


# --- A line, and a model that titles a line ---

def fast_knives(monkeypatch):
    """Chef knives made fast-moving, so the Victorinox line and its Fibrox answer like tech (the library is made up)."""
    monkeypatch.setattr(config, "FAST_MOVING_TYPES", (*config.FAST_MOVING_TYPES, "chef knife"))


def knives(tmp_path, entries):
    return answer_request(KNIFE_REQUEST, library_dir=knife_library(tmp_path, fibrox=(1, 1)), prices=[], today=TODAY,
                          product_facts=[], product_pages=[], brand_lines=[], current_models=entries)


def knife(**overrides):
    """An entry for the made-up fast-moving knives; the list only allows tech, so its category is changed after it loads."""
    made = listed(**({"product_type": "chef knife", "replaced": [], "current": "Victorinox Fibrox Pro"} | overrides))
    return made.model_copy(update={"category": "kitchen"})


def test_a_model_that_titles_a_line_is_matched_by_its_title_not_the_lines_name(tmp_path, monkeypatch):
    fast_knives(monkeypatch)
    result = knives(tmp_path, [knife(replaced=[FIBROX])])
    pick = result.answer.picks[0]
    assert pick.name == FIBROX and pick.current_model.text == "Current model: Victorinox Fibrox Pro"
    # The line's own name no longer finds it: the title says which model the voices named.
    assert knives(tmp_path / "b", [knife(line=[VICTORINOX], released="2020")]).answer.picks[0].current_model is None


def test_a_line_shows_it_only_when_most_of_its_credible_voices_wrote_before_the_current_model(tmp_path, monkeypatch):
    fast_knives(monkeypatch)
    monkeypatch.setattr(config, "BRAND_MODEL_TITLES_ON", False)  # the line keeps its name, so its name finds the entry
    after = knives(tmp_path / "a", [knife(line=[VICTORINOX], released="2025-06")])
    assert after.answer.picks[0].name == VICTORINOX and after.answer.picks[0].current_model is not None
    # The voices wrote on 2 Mar 2025 (the made-up threads'): a model out in March 2025 or later may be the one they own.
    for released in ("2025-03", "2025", "2024-12-31"):
        again = knives(tmp_path / released, [knife(line=[VICTORINOX], released=released)])
        assert again.answer.picks[0].current_model is None, released


def test_the_most_named_model_of_a_line_pick_is_matched_too(tmp_path, monkeypatch):
    # No model clearly leads here (the titles are off): the line pick shows "Most named model: <Fibrox>", and the Fibrox
    # is a model a newer one replaced, so its current model is shown too.
    fast_knives(monkeypatch)
    monkeypatch.setattr(config, "BRAND_MODEL_TITLES_ON", False)
    pick = knives(tmp_path, [knife(replaced=[FIBROX])]).answer.picks[0]
    assert pick.name == VICTORINOX and pick.model == FIBROX
    assert pick.current_model.text == "Current model: Victorinox Fibrox Pro"
