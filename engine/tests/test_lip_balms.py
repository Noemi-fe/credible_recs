"""SPF lip balms (Noemi's decision 2 of 15 Oct 2026): lips are an exception to her 9 Oct rule "sun protection wins over
the form". A product for the lips with SPF is a lip balm, and "with SPF" is a checked requirement of a lip balm
request, as PFAS-free is of a pan's: the product's name says SPF, or its facts entry (from the maker's page) does; a
pick whose facts can't confirm it keeps a note (and since Noemi's decision 1 of 15 Oct 2026 ranks after those confirmed:
engine/tests/test_confirmed_first.py); a whole brand can't be checked, so its line is left out.

Before this, extraction instructions v6 to v13 typed anything with SPF as a sunscreen, so "lip balm with spf" showed
lip balms without SPF and the library's SPF lip balms were counted as sunscreens. engine/lip_balms.py re-types them.

Every product, name, source link and library here is made up, and every library is a temporary folder.
"""

import json
import os
from datetime import datetime
from pathlib import Path

import pytest

from engine import config, lip_balms
from engine.lip_balms import is_lip_product, retype
from engine.pipeline import answer_request
from engine.product_facts import (
    NotSuited,
    conflicts,
    facts_that_matter,
    find_facts,
    hard_requirements,
    name_facts,
    request_asks,
    uncheckable_brand_reason,
    unconfirmed,
    unconfirmed_note,
)
from engine.query import parse_query
from engine.tests.factories import make_comment, make_thread, write_gold
from engine.tests.test_product_facts import TODAY, known, names, write_library

SPF_REQUEST = "lip balm with spf"
RULES = config.PRODUCT_FACT_RULES


def lip(product: str, **facts):
    return known(product, product_type="lip balm", **facts)


# --- The fact, the rule and the words a request asks for it with ---

def test_a_lip_balm_can_say_whether_it_has_spf_and_a_sunscreen_has_no_such_fact():
    assert config.PRODUCT_FACT_VALUES["spf"] == (True, False)
    assert "spf" in config.PRODUCT_FACTS_BY_TYPE["lip balm"]
    for product_type in ("sunscreen", "moisturiser", "serum"):  # their SPF is what they are, or not asked for
        assert "spf" not in config.PRODUCT_FACTS_BY_TYPE[product_type], product_type
    assert RULES["no SPF"] == {"asks": ("SPF",), "fact": "spf", "value": False, "hard": True,
                               "reason": "it has no SPF"}


@pytest.mark.parametrize("text", [SPF_REQUEST, "spf lip balm", "SPF lip balm for dry lips", "lip balm with SPF 30",
                                  "lip balm spf30", "lip balm with sunscreen", "sunscreen lip balm",
                                  "lip balm with sun protection", "tinted lip balm with spf", "chapstick with spf"])
def test_a_lip_balm_request_naming_spf_asks_for_it(text):
    assert "SPF" in request_asks(parse_query(text)), text


@pytest.mark.parametrize("text", ["lip balm", "lip balm for very dry lips", "lip balm without spf",
                                  "lip balm with no spf", "lip balm without an spf", "spf-free lip balm",
                                  "lip mask for cracked lips"])
def test_a_lip_balm_request_not_naming_spf_or_refusing_it_doesnt_ask_for_it(text):
    assert "SPF" not in request_asks(parse_query(text)), text


def test_with_spf_is_a_hard_requirement_of_lip_balms_only():
    assert hard_requirements(parse_query(SPF_REQUEST)) == ["no SPF"]
    assert facts_that_matter(parse_query(SPF_REQUEST)) == ["spf"]
    # Every sunscreen has SPF, and a moisturiser's isn't checked: their requests ask for nothing to confirm.
    for text in ("spf 50 sunscreen", "sunscreen for oily skin", "daily moisturizer w spf30+ for dry skin"):
        assert hard_requirements(parse_query(text)) == [], text
        assert "spf" not in facts_that_matter(parse_query(text)), text
    assert hard_requirements(parse_query("lip balm for very dry lips")) == []


def test_a_lip_balm_without_spf_doesnt_suit_a_request_for_one():
    [found] = conflicts(parse_query(SPF_REQUEST), lip("Plain Lip Butter", spf=False))
    assert (found.rule, found.hard, found.reason) == ("no SPF", True, "it has no SPF")
    assert conflicts(parse_query(SPF_REQUEST), lip("Sunny Lip Balm", spf=True)) == []
    assert conflicts(parse_query("lip balm for very dry lips"), lip("Plain Lip Butter", spf=False)) == []


def test_the_words_for_spf_in_notes_and_reasons_wording_proposed():
    assert unconfirmed_note(["no SPF"]) == "we couldn't confirm it has SPF"
    assert uncheckable_brand_reason(["no SPF"]) == "a whole brand can't be checked for SPF"


# --- The name says it ---

@pytest.mark.parametrize("name", ["Acme Lip Balm SPF 30", "Acme lip balm spf30", "Acme SPF lip balm",
                                  "Acme lip balm with SPF", "Acme chapstick with sunscreen", "Acme UV lip 50+",
                                  "Acme Lip Screen SPF 50", "Acme Melty Lip SPF25 PA++"])
def test_a_lip_balms_name_can_say_it_has_spf(name):
    assert name_facts(name, "lip balm") == {"spf": True}, name


@pytest.mark.parametrize("name", ["Acme Lip Balm", "Acme Lip Balm (no SPF)", "Acme lip balm without spf",
                                  "Acme SPF-free lip balm", "Sun Valley Lip Butter", "Acme Lip Sleeping Mask"])
def test_a_name_that_doesnt_say_spf_or_says_it_has_none_states_nothing(name):
    assert name_facts(name, "lip balm") == {}, name


def test_only_a_type_that_can_have_the_fact_takes_it_from_its_name():
    assert name_facts("Acme Sun Fluid SPF 50", "sunscreen") == {}
    assert name_facts("Acme Day Cream SPF 30", "moisturiser") == {}
    assert name_facts("Acme Lip Balm SPF 30", None) == {}


def test_a_name_that_says_spf_confirms_it_without_an_entry():
    query = parse_query(SPF_REQUEST)
    assert unconfirmed(query, None) == ["no SPF"]
    assert unconfirmed(query, None, names=("Acme Lip Balm SPF 30",)) == []
    assert unconfirmed(query, None, names=("Acme Lip Balm",)) == ["no SPF"]
    assert unconfirmed(query, lip("Acme Lip Balm", fragrance_free=True), names=("Acme Lip Balm",)) == ["no SPF"]
    assert unconfirmed(query, lip("Acme Lip Balm", spf=True), names=("Acme Lip Balm",)) == []
    # A fact known to clash is a reason to leave the product out, not something unconfirmed.
    assert unconfirmed(query, lip("Plain Lip Butter", spf=False), names=("Plain Lip Butter",)) == []


def test_a_name_that_says_spf_never_takes_the_entry_of_a_version_without_it():
    # A maker may sell a lip balm with and without SPF under one name ("Lip Repair", "Lip Repair + Protect SPF 30"),
    # and module 4 reads a writer's "Lip Repair SPF" as either: the words of the name decide between them.
    plain, protect = lip("Acme Lip Repair", spf=False), lip("Acme Lip Repair + Protect SPF 30", spf=True)
    assert find_facts("Acme Lip Repair SPF", "skincare", [plain, protect], "lip balm") == protect
    assert find_facts("Acme Lip Repair SPF", "skincare", [plain], "lip balm") is None
    assert find_facts("Acme Lip Repair", "skincare", [plain, protect], "lip balm") == plain


# --- In an answer ---

def lip_library(tmp_path: Path) -> Path:
    return write_library(tmp_path, ("Lip balm with SPF for summer?", "Which lip balm do you swear by?"),
                         {"Plain Lip Butter": 5, "Acme Lip Balm SPF 30": 4, "Mystery Overnight Lip Balm": 3,
                          "Glow Tinted Balm": 3}, product_type="lip balm")


FACTS = [lip("Plain Lip Butter", spf=False), lip("Glow Tinted Balm", spf=True)]


def test_a_lip_balm_with_spf_request_shows_lip_balms_with_spf_first_and_notes_the_unconfirmed(tmp_path):
    lib = lip_library(tmp_path)
    result = answer_request(SPF_REQUEST, library_dir=lib, prices=[], product_facts=FACTS, today=TODAY)
    picks = {pick.name: pick for pick in result.answer.picks}
    assert set(picks) == {"Acme Lip Balm SPF 30", "Mystery Overnight Lip Balm", "Glow Tinted Balm"}
    assert names(result.answer.picks)[0] == "Acme Lip Balm SPF 30"
    assert result.left_out_not_suited == [NotSuited("Plain Lip Butter", "it has no SPF")]
    assert picks["Acme Lip Balm SPF 30"].cautions == [] and picks["Glow Tinted Balm"].cautions == []
    assert picks["Mystery Overnight Lip Balm"].cautions == ["Note: we couldn't confirm it has SPF."]


def test_a_lip_balm_request_not_asking_for_spf_is_as_before(tmp_path, skincare_need_rule_set_aside):
    # The need rule set aside (15 Oct 2026, merging Noemi's decisions 2 and 3): this test is about SPF, and its made-up
    # comments don't talk about very dry lips, which skincare's need rule asks of a pick in every reading since then.
    lib = lip_library(tmp_path)
    without = answer_request("lip balm for very dry lips", library_dir=lib, prices=[], product_facts=[], today=TODAY)
    result = answer_request("lip balm for very dry lips", library_dir=lib, prices=[], product_facts=FACTS, today=TODAY)
    assert names(result.answer.picks) == names(without.answer.picks)
    assert names(result.answer.picks)[0] == "Plain Lip Butter"
    assert all(pick.cautions == [] for pick in result.answer.picks) and result.left_out_not_suited == []


# --- Module 1: sun protection for the lips is a lip balm ---

@pytest.mark.parametrize("text", ["lip sunscreen", "sunscreen for lips", "sunscreen for my lips", "spf for lips",
                                  "lip spf", "a lip sunblock", "lip oil with spf", "lip gloss with SPF 30",
                                  "spf lip gloss", "lip treatment with sunscreen", "sunscreen stick for lips",
                                  SPF_REQUEST, "tinted lip balm with spf"])
def test_sun_protection_for_the_lips_is_a_lip_balm_request_with_the_spf_requirement(text):
    query = parse_query(text)
    assert (query.status, query.category, query.product_type) == ("ok", "skincare", "lip balm"), text
    assert hard_requirements(query) == ["no SPF"], text


@pytest.mark.parametrize("text", ["sunscreen", "sunscreen for oily skin", "spf 50 sunscreen for my face",
                                  "sunscreen that doesn't sting my lips or eyes", "sunscreen stick",
                                  "mineral sunscreen spf 30 for sensitive skin"])
def test_a_sunscreen_request_stays_a_sunscreen_request(text):
    query = parse_query(text)
    assert (query.status, query.product_type) == ("ok", "sunscreen"), text


def test_a_lip_balm_and_a_sunscreen_are_still_two_products():
    assert parse_query("a lip balm and a sunscreen").status == "clarify"
    assert parse_query("lip spf and a face sunscreen").status == "clarify"


# --- Re-typing the library's lip products typed sunscreen (engine/lip_balms.py) ---

@pytest.mark.parametrize("name", ["Acme Melty Cream Lip SPF 25", "Acme Intense Therapy Lip Balm",
                                  "Acme chapsticks with sunscreen", "Acme Lipscreen SPF 50", "Acme SPF lip glosses",
                                  "Acme UV lip 50+ PA++++", "Acme lip protect stick", "Acme lipbalm",
                                  "Blistex Deep Renewal", "Rohto Mentholatum Deep Moist SPF", "Acme lips SPF"])
def test_a_lip_product_is_known_by_its_name(name):
    assert is_lip_product(name), name


@pytest.mark.parametrize("name", ["Acme Matte Sun Stick", "Acme Invisible Sun Stick SPF 50", "Acme Play Lotion",
                                  "La Roche-Posay Lipikar Baume", "Philip Kingsley sunscreen", "Acme Kids Stick SPF 40",
                                  "Acme Eclipse Sun Gel", "Acme Tinted Face Fluid"])
def test_a_sunscreen_for_the_face_or_body_is_no_lip_product(name):
    assert not is_lip_product(name), name


def lip_mention(comment_id: str, product: str, product_type: str, quote: str) -> dict:
    return {"comment_id": comment_id, "product": product, "category": "skincare", "product_type": product_type,
            "stance": "recommend", "evidence": "short-term use", "evidence_tags": ["short-term use"], "quote": quote}


BALM = "The Acme Melty Lip SPF 25 is the only balm I reapply happily."
STICK = "The Acme Sun Stick SPF 50 goes on clear over makeup."
SLEEP = "The Acme Lip Sleeping Mask keeps my lips soft overnight."


def retype_library(tmp_path: Path) -> Path:
    comments = [make_comment("l1balm", thread_id="1lips01", body=BALM),
                make_comment("l2stick", thread_id="1lips01", body=STICK),
                make_comment("l3sleep", thread_id="1lips01", body=SLEEP)]
    thread = make_thread(id="1lips01", title="Lip balm with SPF?", comments=comments,
                         url="https://www.reddit.com/r/SkincareAddiction/comments/1lips01/lip_balm/")
    root = write_gold(tmp_path / "library", [thread], voices=None, mentions=None)
    (root / "extracted").mkdir()
    (root / "extracted" / "1lips01.json").write_text(json.dumps({
        "thread_id": "1lips01", "instructions_version": "extract-v13", "extracted_at": "2026-10-14T10:00:00Z",
        "extractor": "claude-code",
        "mentions": [lip_mention("l1balm", "Acme Melty Lip SPF 25", "sunscreen", "the only balm I reapply happily"),
                     lip_mention("l2stick", "Acme Sun Stick SPF 50", "sunscreen", "goes on clear over makeup"),
                     lip_mention("l3sleep", "Acme Lip Sleeping Mask", "lip balm", "keeps my lips soft overnight")],
    }, indent=1), encoding="utf-8")
    return root


def extraction_of(root: Path) -> dict:
    return json.loads((root / "extracted" / "1lips01.json").read_text(encoding="utf-8"))


def test_a_dry_run_lists_the_lip_products_typed_sunscreen_and_changes_nothing(tmp_path):
    root = retype_library(tmp_path)
    before = (root / "extracted" / "1lips01.json").read_bytes()
    result = retype(root)
    assert [(r.thread_id, r.comment_id, r.product) for r in result.retyped] == [
        ("1lips01", "l1balm", "Acme Melty Lip SPF 25")]
    assert result.dry_run and (root / "extracted" / "1lips01.json").read_bytes() == before


def test_writing_retypes_only_the_lip_products_and_keeps_everything_else(tmp_path):
    root = retype_library(tmp_path)
    old = extraction_of(root)
    result = retype(root, write=True)
    new = extraction_of(root)
    assert [m["product_type"] for m in new["mentions"]] == ["lip balm", "sunscreen", "lip balm"]
    assert result.files_changed == ["1lips01"]
    for before, after in zip(old["mentions"], new["mentions"]):
        assert {k: v for k, v in before.items() if k != "product_type"} == {
            k: v for k, v in after.items() if k != "product_type"}
    # Its version and date stay: what it was extracted with is unchanged (a slimmed thread's stamp still matches).
    assert {k: new[k] for k in ("thread_id", "instructions_version", "extracted_at", "extractor")} == {
        k: old[k] for k in ("thread_id", "instructions_version", "extracted_at", "extractor")}
    assert retype(root, write=True).retyped == []  # done once


def test_a_file_changed_since_the_cutoff_is_listed_and_left_alone(tmp_path):
    # 15 Oct 2026: three extractors were still writing v13 files; theirs are re-typed once their lists finish.
    root = retype_library(tmp_path)
    path = root / "extracted" / "1lips01.json"
    late = datetime(2026, 10, 15, 0, 30).timestamp()
    os.utime(path, (late, late))
    before = path.read_bytes()
    result = retype(root, write=True, before=datetime(2026, 10, 15, 0, 0))
    assert result.retyped == [] and [(r.comment_id, r.product) for r in result.left_for_later] == [
        ("l1balm", "Acme Melty Lip SPF 25")]
    assert path.read_bytes() == before


def test_the_command_prints_ids_and_names_never_quotes(tmp_path, capsys):
    root = retype_library(tmp_path)
    assert lip_balms.main(["retype", "--library", str(root)]) == 0
    out = capsys.readouterr().out
    assert "1lips01 l1balm Acme Melty Lip SPF 25" in out and "dry run" in out.lower()
    assert "reapply happily" not in out and "over makeup" not in out


def test_a_hand_laid_out_file_keeps_its_layout(tmp_path):
    # Some library files were written with one mention a line: only the re-typed mention's type value changes.
    root = retype_library(tmp_path)
    path = root / "extracted" / "1lips01.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    head = {k: v for k, v in data.items() if k != "mentions"}
    lines = ",\n".join("    " + json.dumps(m, ensure_ascii=False) for m in data["mentions"])
    text = json.dumps(head, indent=2)[:-2] + ',\n  "mentions": [\n' + lines + "\n  ]\n}\n"
    path.write_text(text, encoding="utf-8")
    retype(root, write=True)
    expected = text.replace('"product": "Acme Melty Lip SPF 25", "category": "skincare", "product_type": "sunscreen"',
                            '"product": "Acme Melty Lip SPF 25", "category": "skincare", "product_type": "lip balm"')
    assert expected != text and path.read_text(encoding="utf-8") == expected


@pytest.mark.parametrize("text", ["lip sunscreen", "sunscreen for my lips", "spf for lips", "lip oil with spf",
                                  "spf lip gloss", "chapstick with sunscreen", "spf lip balm", "lip balm with SPF 30"])
def test_every_way_of_asking_for_sun_protection_for_the_lips_asks_what_lip_balm_with_spf_does(text):
    # The words naming the product ("sunscreen", "lips", "lip oil") are no needs of their own (the 11 Oct 2026 rule:
    # the product's own name is never a need); the request asks for a lip balm with SPF, so every such request reads
    # the threads "lip balm with spf" reads first.
    from engine.needs import request_needs

    assert [need.name.lower() for need in request_needs(parse_query(text))] == ["spf"], text  # named as typed
    assert [need.name for need in request_needs(parse_query(SPF_REQUEST))] == ["spf"]
    assert [need.name for need in request_needs(parse_query("tinted lip balm with spf"))] == ["tinted", "spf"]


def test_a_file_another_process_writes_meanwhile_is_left_to_it(tmp_path, monkeypatch):
    # The library is shared with the extractors: a file changed between this command's read and its write is never
    # written over, only listed.
    root = retype_library(tmp_path)
    path = root / "extracted" / "1lips01.json"
    real = lip_balms.extraction_bytes

    def meanwhile(data, like=""):
        path.write_text(like.replace("claude-code", "claude-code-2"), encoding="utf-8")  # someone else's write
        later = datetime(2026, 10, 15, 3, 0).timestamp()
        os.utime(path, (later, later))
        return real(data, like=like)

    monkeypatch.setattr(lip_balms, "extraction_bytes", meanwhile)
    monkeypatch.setattr(lip_balms, "_in_place", lambda *args: None)
    result = retype(root, write=True)
    assert result.retyped == [] and [r.comment_id for r in result.left_for_later] == ["l1balm"]
    assert "claude-code-2" in path.read_text(encoding="utf-8")
