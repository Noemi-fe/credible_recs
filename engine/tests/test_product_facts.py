"""Product facts (9 Oct 2026): a few checked facts about each product, matched against what the request asks for.

"retinol for a beginner with sensitive skin" used to pick Tazorac, a strong prescription retinoid: the ranking reads
only Reddit, and comments rarely say "too strong for beginners". With a facts list (data/product_facts.json), a product
whose facts clash with the request is left out and listed (a hard rule), or kept with a caution under its pick (a soft
rule). A fact not known never counts against a product.

Every product fact, source link and library here is made up, and every library is a temporary folder: no test reads
data/ except the one that checks the committed facts list loads.
"""

import json
import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from engine import answer as wording
from engine import config, pipeline, product_facts, web
from engine.answer import answer_to_dict, render_markdown, write_answer
from engine.pipeline import answer_request
from engine.product_facts import (
    DEFAULT_PRODUCT_FACTS,
    ProductFacts,
    ProductFactsError,
    conflicts,
    facts_that_matter,
    find_facts,
    load_product_facts,
    request_asks,
)
from engine.query import MUST_HAVES, PRODUCT_TYPES, SKIN_TYPES, parse_query
from engine.tests.factories import make_comment, make_thread, write_gold
from engine.tests.test_answer import kitchen_case
from engine.tests.test_live_checks import restamp
from engine.tests.test_pipeline import FakeLive, skillet_library
from engine.tests.test_slice_eval import questions_file
from engine.tests.test_web import ask

TODAY = date(2026, 10, 9)
BEGINNER = "retinol for a beginner with sensitive skin"
RULES = config.PRODUCT_FACT_RULES


def known(product: str, product_type: str = "retinoid", category: str = "skincare", checked_on: date = TODAY,
          sources: tuple[str, ...] = ("https://facts.example/page",), **facts) -> ProductFacts:
    """One made-up entry of the facts list."""
    return ProductFacts(product=product, category=category, product_type=product_type, facts=facts,
                        sources=list(sources), checked_on=checked_on)


def entry(**overrides) -> dict:
    data = {"product": "Galderma Differin Gel", "category": "skincare", "product_type": "retinoid",
            "facts": {"strength": "gentle", "prescription_only": False},
            "sources": ["https://facts.example/differin"], "checked_on": "2026-10-09"}
    data.update(overrides)
    return data


def write_facts(tmp_path: Path, entries) -> Path:
    path = tmp_path / "product_facts.json"
    path.write_text(json.dumps({"facts": entries}), encoding="utf-8")
    return path


# --- Made-up libraries ---

def write_library(tmp_path: Path, titles: tuple[str, str], recommended: dict[str, int],
                  warned: dict[str, int] | None = None, product_type: str | None = None) -> Path:
    """Two skincare threads with these titles. Each product is recommended (or warned against) its number of times, by
    a different writer each time, alternating between the two threads; each comment's text is its quote. With
    `product_type`, every mention has that type, as extraction v6 and later give it."""
    comments: dict[str, list[dict]] = {"1skin01": [], "1skin02": []}
    mentions: dict[str, list[dict]] = {"1skin01": [], "1skin02": []}
    every = [(p, n, "recommend") for p, n in recommended.items()] + [(p, n, "warn") for p, n in (warned or {}).items()]
    for number, (product, times, stance) in enumerate(every):
        for i in range(times):
            thread_id = ("1skin01", "1skin02")[i % 2]
            comment_id = f"s{number}x{i}"
            text = (f"I've used {product} for {i + 2} years and my skin is much better for it." if stance == "recommend"
                    else f"I used {product} for {i + 2} weeks and it burned my skin, avoid it.")
            comments[thread_id].append(make_comment(comment_id, thread_id=thread_id, body=text))
            mentions[thread_id].append({"comment_id": comment_id, "product": product, "category": "skincare",
                                        "stance": stance, "quote": text}
                                       | ({"product_type": product_type} if product_type else {}))
    threads = [make_thread(id=thread_id, title=title, body="Any advice?", comments=comments[thread_id],
                           url=f"https://www.reddit.com/r/SkincareAddiction/comments/{thread_id}/thread/")
               for thread_id, title in zip(comments, titles)]
    root = write_gold(tmp_path / "library", threads, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for thread_id, found in mentions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v5", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": found,
        }), encoding="utf-8")
    return root


def retinol_library(tmp_path: Path, warned: dict[str, int] | None = None) -> Path:
    """Tazorac recommended four times (the most), three gentler retinoids three times each, across two threads."""
    titles = ("Retinol for a beginner with sensitive skin?", "Which retinol should I start with?")
    return write_library(tmp_path, titles,
                         {"Tazorac": 4, "Differin Gel": 3, "The Ordinary Retinol in Squalane": 3,
                          "CeraVe Resurfacing Retinol Serum": 3}, warned)


def moisturiser_library(tmp_path: Path) -> Path:
    """Three moisturisers, each recommended three times across two threads."""
    return write_library(tmp_path, ("Moisturiser for oily skin?", "Which moisturiser do you swear by?"),
                         {"CeraVe Moisturising Cream": 3, "Vanicream Facial Moisturiser": 3,
                          "La Roche-Posay Toleriane Double Repair": 3})


TAZORAC = known("Tazorac", strength="strong", prescription_only=True)
RICH = known("CeraVe Moisturising Cream", product_type="moisturiser", texture="rich")
RICH_CAUTION = "Note: its texture is rich, which can feel heavy on oily or acne-prone skin."


def names(picks) -> list[str]:
    return [pick.name for pick in picks]


# --- The list ---

def test_the_committed_facts_list_is_valid():
    assert DEFAULT_PRODUCT_FACTS.name == "product_facts.json" and DEFAULT_PRODUCT_FACTS.parent.name == "data"
    raw = json.loads(DEFAULT_PRODUCT_FACTS.read_text(encoding="utf-8"))["facts"]
    loaded = load_product_facts()
    assert len(loaded) == len(raw)
    assert all(e.sources and all(s.startswith("https://") for s in e.sources) and e.checked_on for e in loaded)


def test_an_entry_loads_with_its_facts_sources_and_date(tmp_path):
    [loaded] = load_product_facts(write_facts(tmp_path, [entry()]))
    assert (loaded.product, loaded.category, loaded.product_type) == ("Galderma Differin Gel", "skincare", "retinoid")
    assert loaded.facts == {"strength": "gentle", "prescription_only": False}
    assert loaded.sources == ["https://facts.example/differin"] and loaded.checked_on == TODAY


def test_a_fact_not_known_is_simply_left_out(tmp_path):
    [loaded] = load_product_facts(write_facts(tmp_path, [entry(facts={"fragrance_free": True})]))
    assert loaded.facts == {"fragrance_free": True} and "strength" not in loaded.facts


@pytest.mark.parametrize("bad", [
    {"facts": {"colour": "red"}},  # not a fact of the vocabulary
    {"facts": {"white_cast": True}},  # a sunscreen's fact, not a retinoid's
    {"facts": {"strength": "very strong"}},  # not one of its values
    {"facts": {"strength": True}},
    {"facts": {"fragrance_free": "yes"}},  # JSON true or false only
    {"facts": {"fragrance_free": 1}},
    {"facts": {"fragrance_free": None}},  # a fact not known is left out, never null
    {"facts": {}},  # an entry that says nothing
    {"facts": ["strength"]},
    {"product_type": "retinol"},  # module 1's product type names only
    {"product_type": "frying pan"},  # a kitchen type in a skincare entry
    {"category": "other"},
    {"product_type": "chef knife", "category": "kitchen", "facts": {"non_stick": False}},  # no facts for knives yet
    {"sources": []},  # at least one source
    {"sources": ["http://facts.example/differin"]},  # https only
    {"sources": ["HTTPS://facts.example/differin"]},
    {"sources": ["https://"]},
    {"sources": ["https://someone:secret@facts.example/differin"]},  # a name and password in a link: never
    {"sources": ["https://facts.example/a page"]},  # spaces
    {"sources": "https://facts.example/differin"},  # a list of links
    {"checked_on": "9 Oct 2026"},
    {"product": ""},
    {"price": 12.0},  # an unknown field is a typo, never ignored
])
def test_a_malformed_entry_is_refused_naming_where_it_is(tmp_path, bad):
    with pytest.raises(ProductFactsError) as refused:
        load_product_facts(write_facts(tmp_path, [entry(), entry(**bad)]))
    assert "entry 2" in str(refused.value)


def test_an_unknown_fact_is_refused_with_a_clear_error(tmp_path):
    with pytest.raises(ProductFactsError) as refused:
        load_product_facts(write_facts(tmp_path, [entry(facts={"fragance_free": True})]))
    message = str(refused.value)
    assert 'unknown fact "fragance_free" for a retinoid' in message
    assert "fragrance_free, prescription_only, strength" in message  # the facts a retinoid can have


def test_a_value_outside_the_vocabulary_names_the_values_it_can_take(tmp_path):
    with pytest.raises(ProductFactsError) as refused:
        load_product_facts(write_facts(tmp_path, [entry(facts={"strength": "very strong"})]))
    assert '"strength"' in str(refused.value) and "gentle, moderate, strong" in str(refused.value)


def test_a_product_type_with_no_facts_says_so(tmp_path):
    with pytest.raises(ProductFactsError) as refused:
        load_product_facts(write_facts(tmp_path, [entry(product_type="chef knife", category="kitchen",
                                                        facts={"non_stick": False})]))
    assert "chef knife" in str(refused.value) and "no facts" in str(refused.value)


@pytest.mark.parametrize("content", ['{"fact": []}', '{"facts": {}}', "[]", "{not json"])
def test_a_file_without_a_facts_list_is_refused(tmp_path, content):
    path = tmp_path / "product_facts.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ProductFactsError):
        load_product_facts(path)


# --- The vocabulary and the rules ---

def test_the_vocabulary_is_small_and_fits_module_1s_product_types():
    types = {p.name: p.category for p in PRODUCT_TYPES}
    assert set(config.PRODUCT_FACTS_BY_TYPE) <= set(types)
    for product_type, facts in config.PRODUCT_FACTS_BY_TYPE.items():
        assert facts and set(facts) <= set(config.PRODUCT_FACT_VALUES), product_type
        if types[product_type] == "skincare":
            assert {"fragrance_free", "maker_warns_sensitive"} <= set(facts), product_type
    # Only retinoids and exfoliants come in prescription versions and strengths (10 Oct 2026).
    assert config.PRODUCT_FACTS_BY_TYPE["retinoid"] == ("fragrance_free", "prescription_only", "strength",
                                                        "maker_warns_sensitive")
    assert config.PRODUCT_FACTS_BY_TYPE["exfoliant"] == config.PRODUCT_FACTS_BY_TYPE["retinoid"]
    assert [t for t, facts in config.PRODUCT_FACTS_BY_TYPE.items() if "prescription_only" in facts] == [
        "exfoliant", "retinoid"]
    assert set(config.PRODUCT_FACTS_BY_TYPE["sunscreen"]) >= {"white_cast", "finish", "filters"}
    assert config.PRODUCT_FACTS_BY_TYPE["frying pan"] == ("pfas_free", "non_stick", "induction")
    assert config.PRODUCT_FACT_VALUES["strength"] == ("gentle", "moderate", "strong")
    # Whether a product is sold is the price list's to say (data/prices.json, "available"): never kept twice.
    assert not any("sold" in fact or "avail" in fact for fact in config.PRODUCT_FACT_VALUES)


def test_every_rule_reads_a_fact_of_the_vocabulary_and_asks_for_something_a_request_can_say():
    can_ask = set(SKIN_TYPES) | set(MUST_HAVES) | set(config.NEEDS) | set(config.PRODUCT_FACT_REQUEST_WORDS)
    for name, rule in RULES.items():
        assert {"asks", "fact", "value", "hard", "reason"} <= set(rule) <= {"asks", "fact", "value", "hard",
                                                                           "reason", "confirm", "types"}, name
        assert isinstance(rule.get("confirm", True), bool), name
        assert set(rule.get("types", ())) <= {p.name for p in PRODUCT_TYPES}, name  # the types it applies to
        values = config.PRODUCT_FACT_VALUES[rule["fact"]]
        assert any(type(value) is type(rule["value"]) and value == rule["value"] for value in values), name
        assert rule["asks"] and set(rule["asks"]) <= can_ask, name
        assert isinstance(rule["hard"], bool) and rule["reason"], name
    # Changed on purpose 10 Oct 2026 (late): "light texture", the mirror of "rich texture", is a second soft rule, and
    # rules may name the product types they apply to ("types").
    assert [name for name, rule in RULES.items() if not rule["hard"]] == ["rich texture", "light texture"]


# --- Finding a product's facts ---

def test_a_product_finds_its_facts_by_name_within_its_category():
    differin = known("Galderma Differin Gel", strength="gentle")
    elsewhere = known("Differin Gel", category="kitchen", product_type="frying pan", non_stick=True)
    assert find_facts("differin gel", "skincare", [elsewhere, differin]) == differin
    assert find_facts("Tazorac", "skincare", [differin]) is None
    assert find_facts("Differin Gel", "kitchen", [differin]) is None
    assert find_facts("Differin Gel", "skincare", []) is None


def test_the_exact_name_comes_first_then_the_requested_type_then_the_newest_check():
    old_exact = known("Tazorac", strength="strong", checked_on=TODAY - timedelta(days=30))
    longer = known("Tazorac Cream", strength="moderate")
    assert find_facts("Tazorac", "skincare", [longer, old_exact]) == old_exact
    as_toner = known("Paula's Choice BHA Liquid", product_type="toner", fragrance_free=True)
    as_exfoliant = known("Paula's Choice BHA Liquid", product_type="exfoliant", strength="moderate",
                         checked_on=TODAY - timedelta(days=5))
    assert find_facts("Paula's Choice BHA Liquid", "skincare", [as_toner, as_exfoliant], "exfoliant") == as_exfoliant
    newer = known("Tazorac", strength="strong", prescription_only=True)
    assert find_facts("Tazorac", "skincare", [old_exact, newer]) == newer


def test_the_uk_name_finds_the_us_name():
    sage = known("Sage Smart Kettle", category="kitchen", product_type="electric kettle", plastic_free_inside=False)
    assert find_facts("Breville Smart Kettle", "kitchen", [sage]) == sage


# --- What a request asks for ---

@pytest.mark.parametrize("request_text, asks", [
    (BEGINNER, {"beginner", "sensitive"}),
    ("I'm new to retinol", {"beginner"}),
    ("gentle exfoliant", {"gentle"}),
    ("sunscreen for oily skin that doesn't leave a white cast", {"oily", "no white cast"}),
    ("sunscreen with no white cast", {"no white cast"}),
    ("fragrance-free moisturiser for dry skin", {"fragrance-free", "dry"}),
    ("non-stick frying pan without PFAS", {"non-stick", "PFAS-free"}),
    ("PFAS-free frying pan for induction", {"PFAS-free", "induction-compatible"}),
    ("plastic-free electric kettle", {"plastic-free"}),
    ("moisturiser for acne-prone skin", {"acne-prone"}),
])
def test_what_a_request_asks_for(request_text, asks):
    assert asks <= set(request_asks(parse_query(request_text)))


def test_a_request_doesnt_ask_for_what_it_only_mentions():
    # Module 1's must-haves are stricter than the needs' words: "a nice scent" doesn't ask for fragrance-free.
    assert "fragrance-free" not in request_asks(parse_query("moisturiser with a nice scent"))
    assert "non-stick" not in request_asks(parse_query("stainless steel frying pan, not non-stick"))
    assert "non-stick" not in request_asks(parse_query("frying pan instead of non-stick"))
    assert request_asks(parse_query("retinol")) == ()
    assert request_asks(parse_query("something nice for my mum")) == ()  # a question first, not a request yet


# --- Facts against a request ---

def test_a_strong_or_prescription_only_product_doesnt_suit_a_beginner_or_sensitive_skin():
    found = conflicts(parse_query(BEGINNER), TAZORAC)
    assert [(c.rule, c.hard) for c in found] == [("too strong", True), ("prescription only", True)]
    assert [c.reason for c in found] == [RULES["too strong"]["reason"], RULES["prescription only"]["reason"]]
    assert conflicts(parse_query(BEGINNER), known("Differin Gel", strength="gentle", prescription_only=False)) == []
    strong_acid = known("Strong Peel", product_type="exfoliant", strength="strong")
    assert [c.rule for c in conflicts(parse_query("gentle exfoliant"), strong_acid)] == ["too strong"]
    assert [c.rule for c in conflicts(parse_query("exfoliant for sensitive skin"), strong_acid)] == ["too strong"]


def test_a_strong_product_suits_a_request_that_doesnt_ask_for_gentleness():
    assert conflicts(parse_query("retinol"), TAZORAC) == []
    assert conflicts(parse_query("strongest retinol for oily skin"), TAZORAC) == []


def test_a_fact_not_known_never_counts_against_a_product():
    assert conflicts(parse_query(BEGINNER), None) == []
    assert conflicts(parse_query(BEGINNER), known("Mystery Retinol", fragrance_free=True)) == []


@pytest.mark.parametrize("request_text, facts, rule", [
    ("fragrance-free moisturiser", known("Scented Cream", product_type="moisturiser", fragrance_free=False),
     "fragrance"),
    ("sunscreen that doesn't leave a white cast", known("Mineral Sunscreen", product_type="sunscreen", white_cast=True),
     "white cast"),
    ("non-stick frying pan without PFAS",
     known("Coated Pan", category="kitchen", product_type="frying pan", pfas_free=False, non_stick=True), "PFAS"),
    ("non-stick frying pan",
     known("Carbon Steel Pan", category="kitchen", product_type="frying pan", non_stick=False), "not non-stick"),
    ("plastic-free electric kettle",
     known("Plastic Kettle", category="kitchen", product_type="electric kettle", plastic_free_inside=False), "plastic"),
    ("frying pan for induction",
     known("Aluminium Pan", category="kitchen", product_type="frying pan", induction=False), "not induction"),
])
def test_each_hard_rule_clashes_with_the_fact_it_reads(request_text, facts, rule):
    [found] = conflicts(parse_query(request_text), facts)
    assert (found.rule, found.hard, found.reason) == (rule, True, RULES[rule]["reason"])


def test_the_fact_that_suits_the_request_never_clashes():
    assert conflicts(parse_query("fragrance-free moisturiser"),
                     known("Plain Cream", product_type="moisturiser", fragrance_free=True)) == []
    ceramic = known("Ceramic Pan", category="kitchen", product_type="frying pan", pfas_free=True, non_stick=True,
                    induction=True)
    assert conflicts(parse_query("non-stick frying pan without PFAS for induction"), ceramic) == []
    steel = known("Steel Pan", category="kitchen", product_type="frying pan", non_stick=False)
    assert conflicts(parse_query("stainless steel frying pan, not non-stick"), steel) == []


def test_a_rich_moisturiser_for_oily_or_acne_prone_skin_is_only_a_caution():
    for request_text in ("moisturiser for oily skin", "moisturiser for acne-prone skin"):
        [found] = conflicts(parse_query(request_text), RICH)
        assert (found.rule, found.hard, found.reason) == ("rich texture", False, RULES["rich texture"]["reason"])
    assert conflicts(parse_query("moisturiser for dry skin"), RICH) == []
    light = known("Gel Cream", product_type="moisturiser", texture="light")
    assert conflicts(parse_query("moisturiser for oily skin"), light) == []


def test_a_light_moisturiser_for_dry_skin_is_only_a_caution():
    # Found in b04, 10 Oct 2026 (late): "fragrance-free moisturiser for very dry skin in winter" had a light gel
    # (Naturie Hatomugi Skin Conditioning Gel) as its first pick with nothing said. The mirror of "rich texture": a
    # note, never a reason to leave it out. Moisturisers only: a light cleanser suits dry skin.
    light = known("Gel Cream", product_type="moisturiser", texture="light")
    [found] = conflicts(parse_query("fragrance-free moisturiser for very dry skin in winter"), light)
    assert (found.rule, found.hard, found.reason) == ("light texture", False, RULES["light texture"]["reason"])
    assert conflicts(parse_query("moisturiser for dry skin"), RICH) == []
    gel_cleanser = known("Gel Cleanser", product_type="cleanser", texture="light")
    assert conflicts(parse_query("gentle cleanser for dry skin"), gel_cleanser) == []
    assert "texture" not in facts_that_matter(parse_query("gentle cleanser for dry skin"))
    assert "texture" in facts_that_matter(parse_query("moisturiser for dry skin"))


def test_each_rule_can_be_switched_between_leaving_out_and_a_caution(monkeypatch):
    rules = {name: dict(rule) for name, rule in RULES.items()}
    rules["too strong"]["hard"] = False
    monkeypatch.setattr(product_facts, "PRODUCT_FACT_RULES", rules)
    [found] = conflicts(parse_query("retinol for a beginner"), known("Strong Retinol", strength="strong"))
    assert found.hard is False


@pytest.mark.parametrize("request_text, facts", [
    ("gentle exfoliant for sensitive skin under £30", ["strength", "prescription_only"]),
    (BEGINNER, ["strength", "prescription_only"]),
    ("sunscreen for oily skin that doesn't leave a white cast, under £20", ["white_cast"]),  # no texture for sunscreen
    # Changed on purpose 10 Oct 2026 (late): a light moisturiser for dry skin gets a note ("light texture").
    ("fragrance-free moisturiser for very dry skin in winter", ["fragrance_free", "texture"]),
    ("gentle cleanser for acne-prone skin that won't strip my skin", ["texture"]),  # no prescription cleansers
    ("non-stick frying pan without PFAS that actually lasts", ["pfas_free", "non_stick"]),
    ("electric kettle that lasts 10+ years", []),
    ("first chef's knife under £100 for a home cook", []),  # no facts for knives yet
    ("best laptop for uni", []),
])
def test_the_facts_that_matter_for_a_request(request_text, facts):
    assert facts_that_matter(parse_query(request_text)) == facts


# --- The pipeline ---

def test_without_facts_the_strong_prescription_retinoid_is_picked_first(tmp_path):
    # The problem these facts fix: the ranking reads only Reddit.
    result = answer_request(BEGINNER, library_dir=retinol_library(tmp_path), prices=[], product_facts=[], today=TODAY)
    assert names(result.answer.picks) == ["Tazorac", "CeraVe Resurfacing Retinol Serum", "Differin Gel"]
    assert result.left_out_not_suited == []


def test_a_product_whose_facts_clash_with_the_request_is_left_out_and_listed_with_the_reason(tmp_path):
    result = answer_request(BEGINNER, library_dir=retinol_library(tmp_path), prices=[], product_facts=[TAZORAC],
                            today=TODAY)
    assert names(result.answer.picks) == ["CeraVe Resurfacing Retinol Serum", "Differin Gel",
                                          "The Ordinary Retinol in Squalane"]
    assert "Tazorac" not in [p.name for p in result.ranking.products] and "Tazorac" not in result.text()
    [left_out] = result.left_out_not_suited
    assert left_out.name == "Tazorac"
    assert left_out.reason == RULES["too strong"]["reason"] + "; " + RULES["prescription only"]["reason"]


def test_the_same_product_is_kept_when_the_request_doesnt_ask_for_gentleness(tmp_path):
    result = answer_request("best retinol", library_dir=retinol_library(tmp_path), prices=[], product_facts=[TAZORAC],
                            today=TODAY)
    assert names(result.answer.picks)[0] == "Tazorac" and result.left_out_not_suited == []


def test_a_product_with_no_facts_is_never_left_out(tmp_path):
    only_differin = [known("Differin Gel", strength="gentle", prescription_only=False)]
    result = answer_request(BEGINNER, library_dir=retinol_library(tmp_path), prices=[], product_facts=only_differin,
                            today=TODAY)
    assert names(result.answer.picks)[0] == "Tazorac" and result.left_out_not_suited == []


def test_a_soft_clash_keeps_the_product_and_shows_a_caution_under_its_pick(tmp_path):
    lib = moisturiser_library(tmp_path)
    without = answer_request("moisturiser for oily skin", library_dir=lib, prices=[], product_facts=[], today=TODAY)
    result = answer_request("moisturiser for oily skin", library_dir=lib, prices=[], product_facts=[RICH], today=TODAY)
    assert names(result.answer.picks) == names(without.answer.picks)  # a caution never changes the ranking
    assert result.left_out_not_suited == []
    picks = {pick.name: pick for pick in result.answer.picks}
    assert picks["CeraVe Moisturising Cream"].cautions == [RICH_CAUTION]
    assert all(pick.cautions == [] for name, pick in picks.items() if name != "CeraVe Moisturising Cream")
    assert RICH_CAUTION in result.text()
    dry = answer_request("moisturiser for dry skin", library_dir=lib, prices=[], product_facts=[RICH], today=TODAY)
    assert all(pick.cautions == [] for pick in dry.answer.picks)


def test_a_brand_pick_has_no_single_product_so_its_facts_are_never_looked_up(tmp_path):
    lodge = known("Lodge", category="kitchen", product_type="frying pan", induction=False)
    result = answer_request("cast iron skillet for induction that lasts", library_dir=skillet_library(tmp_path),
                            prices=[], product_facts=[lodge], today=TODAY)
    assert "Lodge (their cast iron skillets)" in names(result.answer.picks)
    assert "Lodge (their cast iron skillets)" not in [item.name for item in result.left_out_not_suited]


def test_cautions_stay_when_the_live_check_writes_the_answer_again(tmp_path):
    lib = moisturiser_library(tmp_path)
    before = answer_request("moisturiser for oily skin", library_dir=lib, prices=[], product_facts=[RICH], today=TODAY)
    vanicream = next(pick for pick in before.answer.picks if pick.name == "Vanicream Facial Moisturiser")
    live = FakeLive(gone={vanicream.quotes[0].comment_id})
    after = answer_request("moisturiser for oily skin", library_dir=lib, prices=[], product_facts=[RICH], today=TODAY,
                           live_checker=live)
    assert after.live_dropped == {"gone": 1} and "Vanicream Facial Moisturiser" not in names(after.answer.picks)
    cerave = next(pick for pick in after.answer.picks if pick.name == "CeraVe Moisturising Cream")
    assert cerave.cautions == [RICH_CAUTION]


# --- The answer ---

def test_the_caution_wording_decided_by_claude():
    assert wording.CAUTION == "Note: {reason}."


def test_a_caution_shows_on_its_pick_in_the_text_and_the_json():
    ranking, bodies, _ = kitchen_case()
    answer = write_answer(ranking, bodies, "chef knife", cautions={"tojiro-dp-gyuto": ["it is made up for this test"]})
    tojiro, global_g2, _ = answer.picks
    assert tojiro.cautions == ["Note: it is made up for this test."] and global_g2.cautions == []
    data = json.loads(json.dumps(answer_to_dict(answer)))
    assert data["picks"][0]["cautions"] == ["Note: it is made up for this test."]
    assert data["picks"][1]["cautions"] == []
    text = render_markdown(answer)
    assert "Note: it is made up for this test." in text
    assert text.index("Note: it is made up") < text.index(wording.QUOTES_HEADING)  # near the top of its pick
    assert all(pick.cautions == [] for pick in write_answer(ranking, bodies).picks)


# --- The demo page ---

@pytest.fixture
def fresh_answers():
    web.clear_answer_cache()
    yield
    web.clear_answer_cache()


def test_products_not_suited_are_counted_and_cautions_reach_the_cards(tmp_path, monkeypatch, fresh_answers):
    scented = known("Vanicream Facial Moisturiser", product_type="moisturiser", fragrance_free=False)
    monkeypatch.setattr(web, "answer_request", lambda request, library_dir: answer_request(
        request, library_dir, prices=[], product_facts=[RICH, scented], today=TODAY))
    _, _, data = ask("fragrance-free moisturiser for oily skin", moisturiser_library(tmp_path))
    assert data["left_out"]["not_suited"] == 1
    cards = {pick["name"]: pick for pick in data["answer"]["picks"]}
    assert "Vanicream Facial Moisturiser" not in cards
    # Neither entry says whether it is fragrance-free, so both get the note (10 Oct 2026), after any soft clash.
    unsure = "Note: we couldn't confirm it's fragrance-free."
    assert cards["CeraVe Moisturising Cream"]["cautions"] == [RICH_CAUTION, unsure]
    assert cards["La Roche-Posay Toleriane Double Repair"]["cautions"] == [unsure]


def test_the_page_counts_products_not_suited_and_draws_cautions_as_text():
    html = web.search_page().decode("utf-8")
    assert 'leftOutNotSuited: "Not suited to your request, so left out: {n}."' in html
    assert "data.left_out.not_suited" in html
    assert "...cautionLines(pick.cautions)," in html
    body = re.search(r"function cautionLines\(cautions\) \{(.*?)\n  \}", html, re.DOTALL).group(1)
    assert 'el("p", { class: "caution" }, text)' in body and "innerHTML" not in body


# --- What is still to look up: python -m engine.product_facts todo ---

def by_name(question) -> dict[str, tuple[bool, list[str]]]:
    return {c.name: (c.has_entry, c.missing) for c in question.to_check}


def test_todo_lists_the_candidates_still_missing_the_facts_that_matter(tmp_path):
    made_up = [known("Differin Gel", strength="gentle", prescription_only=False),  # has both: not listed
               known("CeraVe Resurfacing Retinol Serum", fragrance_free=True)]  # an entry, but neither fact
    questions = questions_file(tmp_path, [BEGINNER, "best retinol", "best laptop for uni"])
    beginner, best, laptop = product_facts.todo(questions, retinol_library(tmp_path), made_up, prices=[])
    assert (beginner.id, beginner.product_type, beginner.category) == ("b01", "retinoid", "skincare")
    assert beginner.facts_that_matter == ["strength", "prescription_only"]
    assert by_name(beginner) == {"Tazorac": (False, ["strength", "prescription_only"]),
                                 "CeraVe Resurfacing Retinol Serum": (True, ["strength", "prescription_only"]),
                                 "The Ordinary Retinol in Squalane": (False, ["strength", "prescription_only"])}
    assert [c.name for c in beginner.to_check][:2] == ["Tazorac", "CeraVe Resurfacing Retinol Serum"]  # picks first
    assert all(c.product_type == "retinoid" for c in beginner.to_check)
    assert (best.facts_that_matter, best.to_check) == ([], [])  # no rule reads a fact for this request
    assert (laptop.id, laptop.product_type, laptop.candidates, laptop.to_check) == ("b03", None, 0, [])


def test_todo_moves_on_to_the_next_candidates_once_a_product_is_left_out(tmp_path):
    [question] = product_facts.todo(questions_file(tmp_path, [BEGINNER]), retinol_library(tmp_path), [TAZORAC],
                                    prices=[])
    assert "Tazorac" not in by_name(question)
    assert set(by_name(question)) == {"CeraVe Resurfacing Retinol Serum", "Differin Gel",
                                      "The Ordinary Retinol in Squalane"}


def test_todo_looks_at_the_top_candidates_only_and_never_at_the_skip_list(tmp_path, monkeypatch):
    monkeypatch.setattr(product_facts, "PRODUCT_FACTS_TODO_CANDIDATES", 2)
    [question] = product_facts.todo(questions_file(tmp_path, [BEGINNER]), retinol_library(tmp_path), [], prices=[])
    assert list(by_name(question)) == ["Tazorac", "CeraVe Resurfacing Retinol Serum"] and question.candidates == 2
    monkeypatch.setattr(product_facts, "PRODUCT_FACTS_TODO_CANDIDATES", 5)
    lib = retinol_library(tmp_path / "2", warned={"Burning Retinoid": 3})
    [question] = product_facts.todo(questions_file(tmp_path, [BEGINNER]), lib, [], prices=[])
    assert "Burning Retinoid" not in by_name(question) and question.candidates == 4


def test_todo_names_brand_picks_apart(tmp_path):
    lib = write_library(tmp_path, ("Moisturiser for oily skin?", "Which moisturiser do you swear by?"), {
        "CeraVe": 3, "CeraVe Moisturising Cream": 1, "CeraVe Facial Moisturising Lotion": 1,
        "Vanicream Facial Moisturiser": 3, "La Roche-Posay Toleriane Double Repair": 3})
    [question] = product_facts.todo(questions_file(tmp_path, ["moisturiser for oily skin"]), lib, [], prices=[])
    assert question.brand_candidates == ["CeraVe (their moisturisers)"]
    assert "CeraVe (their moisturisers)" not in by_name(question)
    assert question.facts_that_matter == ["texture"]


def test_todo_runs_without_live_checks(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "live_checker", lambda: pytest.fail("todo must not read Reddit"))
    lib = retinol_library(tmp_path)
    restamp(lib, "1skin01", read_from="arctic_shift")  # waiting for its live check: still counted
    [question] = product_facts.todo(questions_file(tmp_path, [BEGINNER]), lib, [], prices=[])
    assert "Tazorac" in by_name(question)


def test_command_line_todo_prints_names_and_product_types_only(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pipeline, "cached_profiles", lambda: None)
    made_up = [known("Differin Gel", strength="gentle", prescription_only=False),
               known("CeraVe Resurfacing Retinol Serum", fragrance_free=True)]
    questions = questions_file(tmp_path, [BEGINNER, "best retinol", "best laptop for uni"])
    assert product_facts.main(["todo"], questions_path=questions, library_dir=retinol_library(tmp_path),
                              facts=made_up, prices=[]) == 0
    out = capsys.readouterr().out
    assert "  b01 retinoid (skincare), facts that matter: strength, prescription_only\n" in out
    assert "    Tazorac (retinoid): no entry yet\n" in out
    assert "    CeraVe Resurfacing Retinol Serum (retinoid): its entry lacks strength, prescription_only\n" in out
    assert "Differin" not in out  # nothing missing
    assert "  b02 retinoid (skincare): no rule reads a fact for this request\n" in out
    assert "  b03: no candidates\n" in out
    assert out.rstrip().endswith("3 candidates to look up: 2 with no entry yet, 1 with an entry missing a fact "
                                 "that matters.")
    assert "years" not in out and "my skin" not in out  # never a quote


def test_command_line_todo_says_when_every_candidate_has_the_facts(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pipeline, "cached_profiles", lambda: None)
    every = [known(name, strength="gentle", prescription_only=False) for name in
             ("Tazorac", "Differin Gel", "The Ordinary Retinol in Squalane", "CeraVe Resurfacing Retinol Serum")]
    assert product_facts.main(["todo"], questions_path=questions_file(tmp_path, [BEGINNER]),
                              library_dir=retinol_library(tmp_path), facts=every, prices=[]) == 0
    out = capsys.readouterr().out
    assert ("  b01 retinoid (skincare), facts that matter: strength, prescription_only: every candidate has them\n"
            in out)
    assert out.rstrip().endswith("0 candidates to look up: 0 with no entry yet, 0 with an entry missing a fact that "
                                 "matters.")


def test_command_line_todo_reports_a_broken_facts_list(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(pipeline, "cached_profiles", lambda: None)

    def broken(*args, **kwargs):
        raise ProductFactsError("data/product_facts.json, entry 3: made up for this test")

    monkeypatch.setattr(product_facts, "load_product_facts", broken)
    assert product_facts.main(["todo"], questions_path=questions_file(tmp_path, [BEGINNER]),
                              library_dir=retinol_library(tmp_path), prices=[]) == 1
    assert "entry 3: made up for this test" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [[], ["todo", "now"], ["fetch"]])
def test_command_line_todo_explains_itself_when_used_wrongly(tmp_path, capsys, argv):
    assert product_facts.main(argv, questions_path=tmp_path / "none.json", library_dir=tmp_path, facts=[],
                              prices=[]) == 2
    assert "python -m engine.product_facts todo" in capsys.readouterr().out


# --- What a maker says, and facts we couldn't confirm (decided by Claude, 10 Oct 2026) ---
# The Ordinary's Mandelic Acid is gentle by strength, but its maker's page says not to use it on sensitive skin: that
# warning is a fact of its own, which leaves the product out of a request for sensitive skin. And a pick whose facts
# can't be confirmed for a hard requirement ("OXO non-stick pan": OXO sells PTFE and ceramic pans) stays, with a note
# saying what we couldn't confirm, rather than being left out (answers would empty) or shown silently (misleading).

from engine.product_facts import NotSuited, hard_requirements, unconfirmed, unconfirmed_note  # noqa: E402
from engine.tests.test_pick_polish import pan_library  # noqa: E402

SENSITIVE = "gentle exfoliant for sensitive skin"
PAN = "non-stick frying pan without PFAS"
MANDELIC = known("Mandelic Acid Serum", product_type="exfoliant", strength="gentle", maker_warns_sensitive=True)


def test_a_makers_warning_against_sensitive_skin_is_a_fact_skincare_can_have(tmp_path):
    assert config.PRODUCT_FACT_VALUES["maker_warns_sensitive"] == (True, False)
    for product_type in ("exfoliant", "retinoid", "moisturiser", "sunscreen", "cleanser"):
        assert "maker_warns_sensitive" in config.PRODUCT_FACTS_BY_TYPE[product_type]
    assert "maker_warns_sensitive" not in config.PRODUCT_FACTS_BY_TYPE["frying pan"]
    path = write_facts(tmp_path, [entry(product="Mandelic Acid Serum", product_type="exfoliant",
                                        facts={"strength": "gentle", "maker_warns_sensitive": True})])
    [loaded] = load_product_facts(path)
    assert loaded.facts["maker_warns_sensitive"] is True


def test_a_product_its_maker_says_isnt_for_sensitive_skin_doesnt_suit_a_request_for_sensitive_skin():
    [found] = conflicts(parse_query(SENSITIVE), MANDELIC)
    assert (found.rule, found.hard) == ("maker warns sensitive", True)
    assert found.reason == RULES["maker warns sensitive"]["reason"] == "its maker says not to use it on sensitive skin"
    assert conflicts(parse_query("exfoliant for oily skin"), MANDELIC) == []
    assert conflicts(parse_query("gentle exfoliant"), MANDELIC) == []  # gentle isn't sensitive skin


def test_the_maker_warning_leaves_the_product_out_of_a_sensitive_skin_answer(tmp_path):
    lib = write_library(tmp_path, ("Gentle exfoliant for sensitive skin?", "Which exfoliant do you use?"),
                        {"Mandelic Acid Serum": 4, "Lactic Acid Toner": 3, "PHA Toner": 3, "Azelaic Acid Gel": 3})
    result = answer_request(SENSITIVE, library_dir=lib, prices=[], product_facts=[MANDELIC], today=TODAY)
    assert "Mandelic Acid Serum" not in names(result.answer.picks) and len(result.answer.picks) == 3
    assert result.left_out_not_suited == [NotSuited("Mandelic Acid Serum",
                                                    "its maker says not to use it on sensitive skin")]
    oily = answer_request("exfoliant for oily skin", library_dir=lib, prices=[], product_facts=[MANDELIC], today=TODAY)
    assert names(oily.answer.picks)[0] == "Mandelic Acid Serum"


def test_a_makers_warning_not_known_is_never_a_requirement():
    # Most makers say nothing either way, so not knowing it never leaves a brand pick out, adds a note, or asks the
    # researcher to look it up: it is recorded when a maker's page says it.
    query = parse_query("moisturiser for sensitive skin")
    assert hard_requirements(query) == [] and unconfirmed(query, None) == []
    assert "maker_warns_sensitive" not in facts_that_matter(parse_query(SENSITIVE))


def test_the_requirements_whose_facts_arent_known_are_not_confirmed():
    query = parse_query(PAN)
    assert unconfirmed(query, None) == ["PFAS", "not non-stick"]
    pan = dict(category="kitchen", product_type="frying pan")
    assert unconfirmed(query, known("Half Pan", pfas_free=True, **pan)) == ["not non-stick"]
    assert unconfirmed(query, known("Full Pan", pfas_free=True, non_stick=True, **pan)) == []
    # A fact known to clash is a reason to leave the product out, not something unconfirmed.
    assert unconfirmed(query, known("Teflon Pan", pfas_free=False, non_stick=True, **pan)) == []
    assert unconfirmed(parse_query("frying pan that lasts"), None) == []
    assert unconfirmed(parse_query(BEGINNER), known("Mid Retinol", strength="moderate", prescription_only=False)) == []
    assert unconfirmed(parse_query(BEGINNER), None) == ["too strong", "prescription only"]


def test_the_note_for_facts_not_confirmed_wording_decided_by_claude():
    assert config.UNCONFIRMED_NOTE == "we couldn't confirm {facts}"
    assert unconfirmed_note(["PFAS"]) == "we couldn't confirm it's PFAS-free"
    assert unconfirmed_note(["PFAS", "not non-stick"]) == "we couldn't confirm it's PFAS-free or that it's non-stick"
    assert unconfirmed_note(["PFAS", "not non-stick", "not induction"]) == (
        "we couldn't confirm it's PFAS-free, that it's non-stick or that it works on an induction hob")
    assert unconfirmed_note(["too strong", "prescription only"]) == (
        "we couldn't confirm it's gentle enough for beginners or sensitive skin or that it's sold without a "
        "prescription")


def test_every_requirement_has_words_for_the_note():
    required = {name for name, rule in RULES.items() if rule["hard"] and rule.get("confirm", True)}
    assert required == set(config.UNCONFIRMED_FACT_NAMES)


def test_a_pick_whose_required_facts_arent_known_keeps_its_place_with_a_note(tmp_path):
    lib = pan_library(tmp_path)
    greenpan = known("GreenPan Valencia frying pan", category="kitchen", product_type="frying pan", pfas_free=True,
                     non_stick=True)
    without = answer_request(PAN, library_dir=lib, prices=[], product_facts=[], today=TODAY)
    result = answer_request(PAN, library_dir=lib, prices=[], product_facts=[greenpan], today=TODAY)
    assert names(result.answer.picks) == names(without.answer.picks) == ["GreenPan Valencia frying pan",
                                                                         "Misen frying pan"]
    picks = {pick.name: pick for pick in result.answer.picks}
    note = "Note: we couldn't confirm it's PFAS-free or that it's non-stick."
    assert picks["GreenPan Valencia frying pan"].cautions == [] and picks["Misen frying pan"].cautions == [note]
    assert note in result.text()
    lasts = answer_request("frying pan that lasts", library_dir=lib, prices=[], product_facts=[], today=TODAY)
    assert all(pick.cautions == [] for pick in lasts.answer.picks)


def test_a_soft_clash_comes_before_the_note(tmp_path):
    lib = moisturiser_library(tmp_path)
    result = answer_request("fragrance-free moisturiser for oily skin", library_dir=lib, prices=[],
                            product_facts=[RICH], today=TODAY)
    cerave = next(pick for pick in result.answer.picks if pick.name == "CeraVe Moisturising Cream")
    assert cerave.cautions == [RICH_CAUTION, "Note: we couldn't confirm it's fragrance-free."]


# --- The name a pick is shown under (decided by Claude, 10 Oct 2026) ---
# Writers spell names as they like ("Beauty of joseon Red Bean water gel", "Biore Watery Essence spf50"). A product
# with a facts entry is shown under the entry's name, which the researcher took from the maker's own page. Price
# entries aren't used: their names carry a size or a colour ("Timemore C2 - White", "(180g)").

def test_a_pick_with_a_facts_entry_is_shown_under_the_entrys_name(tmp_path):
    lib = write_library(tmp_path, ("Retinol for a beginner with sensitive skin?", "Which retinol should I start with?"),
                        {"cerave resurfacing retinol serum": 4, "Differin Gel": 3, "inkey list retinol": 3})
    proper = [known("CeraVe Resurfacing Retinol Serum", strength="gentle", prescription_only=False)]
    result = answer_request(BEGINNER, library_dir=lib, prices=[], product_facts=proper, today=TODAY)
    assert names(result.answer.picks) == ["CeraVe Resurfacing Retinol Serum", "Differin Gel", "inkey list retinol"]
    assert [p.name for p in result.ranking.products][:1] == ["CeraVe Resurfacing Retinol Serum"]
    without = answer_request(BEGINNER, library_dir=lib, prices=[], product_facts=[], today=TODAY)
    assert names(without.answer.picks)[0] == "cerave resurfacing retinol serum"


def test_groups_that_find_the_same_facts_entry_are_one_product(tmp_path):
    # Found in b02, 10 Oct 2026: "Biore watery essence" and "Biore aqua rich" stayed apart in grouping, but both found
    # the entry "Biore UV Aqua Rich Watery Essence SPF50" and were shown under its name, one as a pick and the other
    # on the skip list. One entry is one product: their mentions are ranked together, under the biggest group's key.
    lib = write_library(tmp_path, ("Sunscreen for oily skin?", "Which sunscreen has no white cast?"),
                        {"Biore watery essence": 4, "Skin Aqua UV Super Moisture Milk": 3,
                         "Canmake Mermaid Skin Gel UV": 3},
                        warned={"Biore aqua rich": 2}, product_type="sunscreen")
    biore = known("Biore UV Aqua Rich Watery Essence SPF50", product_type="sunscreen", white_cast=False)
    without = answer_request("sunscreen for oily skin", library_dir=lib, prices=[], product_facts=[], today=TODAY)
    assert {"Biore watery essence", "Biore aqua rich"} <= {p.name for p in without.ranking.products}  # apart
    result = answer_request("sunscreen for oily skin", library_dir=lib, prices=[], product_facts=[biore], today=TODAY)
    named = [p for p in result.ranking.products if p.name == "Biore UV Aqua Rich Watery Essence SPF50"]
    assert len(named) == 1
    assert (len(named[0].credible_recommendations), len(named[0].credible_warnings)) == (4, 2)
    assert named[0].key == "skincare:biore watery essence"
    assert "Biore UV Aqua Rich Watery Essence SPF50" not in [p.name for p in result.ranking.skip_list]


def test_a_renamed_pick_keeps_its_cautions(tmp_path):
    lib = write_library(tmp_path, ("Moisturiser for oily skin?", "Which moisturiser do you swear by?"),
                        {"cerave moisturising cream": 3, "Vanicream Facial Moisturiser": 3,
                         "La Roche-Posay Toleriane Double Repair": 3})
    result = answer_request("moisturiser for oily skin", library_dir=lib, prices=[], product_facts=[RICH], today=TODAY)
    picks = {pick.name: pick for pick in result.answer.picks}
    assert picks["CeraVe Moisturising Cream"].cautions == [RICH_CAUTION]


def test_a_name_with_a_slip_comes_first_too():
    # From the library (10 Oct 2026): "Beplain mungbean greenful oil cleasner" is the oil cleanser misspelled. A shorter
    # entry ("Beplain mungbean cleanser") fits it too, but the name written alike but for a slip comes first.
    oil = known("Beplain Mungbean Greenful Oil Cleanser", product_type="cleanser", checked_on=TODAY - timedelta(days=5),
                fragrance_free=True)
    foam = known("Beplain mungbean cleanser", product_type="cleanser", fragrance_free=False)
    assert find_facts("Beplain mungbean greenful oil cleasner", "skincare", [foam, oil], "cleanser") == oil
