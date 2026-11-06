"""The makeup fix round, part 3 (Noemi's answers of 5 Nov 2026, about 00:25).

(A) "Lip tint is filed under lipstick and brow gel under brow pencil, so those requests get the wrong products. Should I
    give them their own types?" Noemi: "Split both (Recommended)". Lip tint and brow gel are module 1 types of their
    own, and the library's tints and gels, typed lipstick and brow pencil by older extractions, are re-typed by command
    (engine/makeup_types.py).
(D) "Old skincare and haircare comments count as medium voices at most, because formulas change. Should old makeup
    comments work the same way?" Noemi: "Yes, like skincare (Recommended)". An old comment counted for a makeup request
    is a medium voice at most.
(B) "Should a top pick need at least one credible voice that fits what was asked (cream, fair skin, oily skin) before
    it's shown?" Noemi: "Yes, measure first (Recommended)". The need-fit rule is built and off
    (config.NEED_FIT_FOR_PICKS).
((C), two threads set aside, is a change to the library, not to the code.)

Every post, title, name and comment here is made up, but for a few real product lines named as products.
"""

import dataclasses
import json
import os
from pathlib import Path

import pytest

from engine import config, makeup_types, pipeline
from engine.answer import unverified_claims
from engine.config import MORE_PRODUCT_TYPES
from engine.credibility import score_voice
from engine.makeup_types import new_type, retype
from engine.pipeline import answer_request
from engine.query import parse_query
from engine.sources import finder_terms
from engine.tests.factories import make_comment, make_thread, write_gold
from engine.tests.ranking_factories import mention
from engine.tests.test_credibility import COLLECTED, account, make_case, years_before

MAKEUP_COMMUNITIES = ["Makeup", "Sephora", "MakeupAddiction", "drugstoreMUA"]


@pytest.fixture(autouse=True)
def _rules_only(monkeypatch):
    # Module 1's rules alone (the open model is off in every test already: conftest.py).
    monkeypatch.setenv("CREDIBLE_RECS_QUERY_MODEL", "off")


def _entry(name: str) -> dict:
    return next(entry for entry in MORE_PRODUCT_TYPES if entry["name"] == name)


# --- (A) The types ---

def test_lip_tint_and_brow_gel_are_makeup_types_of_their_own():
    tint, gel = _entry("lip tint"), _entry("brow gel")
    assert (tint["plural"], tint["category"], tint["department"]) == ("lip tints", "general", "beauty")
    assert (gel["plural"], gel["category"], gel["department"]) == ("brow gels", "general", "beauty")
    assert tint["subreddits"] == MAKEUP_COMMUNITIES + ["AsianBeauty"]  # as lipstick: K-beauty tints
    assert gel["subreddits"] == MAKEUP_COMMUNITIES
    assert {"lip tint", "lip stain"} <= set(tint["keywords"]) and {"brow gel", "brow soap"} <= set(gel["keywords"])
    assert {"lip tint", "brow gel"} <= set(config.REFORMULATED_TYPES)


def test_lipstick_and_brow_pencil_no_longer_hold_the_tints_and_gels():
    lipstick, pencil = _entry("lipstick"), _entry("brow pencil")
    assert not [w for w in lipstick["keywords"] + lipstick["title_words"] if "tint" in w or "stain" in w]
    assert not [w for w in pencil["keywords"] + pencil["title_words"]
                if any(gel in w for gel in ("gel", "soap", "wax", "glue"))]
    assert "lip tint" not in finder_terms("lipstick") and "brow gel" not in finder_terms("brow pencil")


@pytest.mark.parametrize("request_text, product_type", [
    ("lip tint", "lip tint"),
    ("lip tints", "lip tint"),
    ("lip stain", "lip tint"),
    ("lip tint for dry lips", "lip tint"),
    ("water tint", "lip tint"),
    ("brow gel", "brow gel"),
    ("eyebrow gel", "brow gel"),
    ("clear brow gel", "brow gel"),
    ("tinted brow gel", "brow gel"),
    ("brow soap", "brow gel"),
    ("brow wax", "brow gel"),
    ("lipstick", "lipstick"),
    ("red lipstick", "lipstick"),
    ("lip gloss", "lipstick"),
    ("brow pencil", "brow pencil"),
    ("brow pomade", "brow pencil"),
    ("tinted lip balm", "lip balm"),  # a balm with a tint stays a lip balm
    ("skin tint", "foundation"),  # a skin tint is a light foundation, not a lip tint
])
def test_each_request_finds_its_type(request_text, product_type):
    query = parse_query(request_text)
    assert (query.status, query.product_type) == ("ok", product_type), request_text


def test_a_lip_tint_request_is_searched_in_the_makeup_communities_then_asian_beauty():
    assert parse_query("lip tint").subreddits == MAKEUP_COMMUNITIES + ["AsianBeauty"]
    assert parse_query("brow gel").subreddits == MAKEUP_COMMUNITIES


# --- (A) Which mentions are re-typed ---

@pytest.mark.parametrize("typed, product, title, expected", [
    # A lipstick whose name says tint or stain, or names a tints-only line, is a lip tint...
    ("lipstick", "Acme Ink Velvet Tint", "", "lip tint"),
    ("lipstick", "Acme Hydrating Lip Stain", "", "lip tint"),
    ("lipstick", "Benetint", "", "lip tint"),
    ("lipstick", "Peripera Ink Mood Glowy", "", "lip tint"),
    ("lipstick", "Acme Juicy Lasting Tints", "Everyday lipstick?", "lip tint"),
    # ...unless it also says lipstick or crayon.
    ("lipstick", "Acme Just A Tint Lip Crayon", "", None),
    ("lipstick", "Acme Tinted Lipstick", "", None),
    ("lipstick", "Acme Ruby Matte", "", None),
    # The maker named alone, in a thread asking for lip tints: the maker's tint. Not a line's name there, nor elsewhere.
    ("lipstick", "Acme", "Which lip tint lasts all day?", "lip tint"),
    ("lipstick", "Acme", "Which lipstick lasts all day?", None),
    ("lipstick", "Acme", "Lip tint or lipstick for a beginner?", None),
    ("lipstick", "Acme Lip Monster", "Which lip tint lasts all day?", None),
    # A brow pencil whose name says gel, soap, wax, glue or a gel's line is a brow gel...
    ("brow pencil", "Acme Clear Brow Gel", "", "brow gel"),
    ("brow pencil", "Acme Brow Soap", "", "brow gel"),
    ("brow pencil", "Acme Brow Glue", "", "brow gel"),
    ("brow pencil", "Glossier Boy Brow", "", "brow gel"),
    ("brow pencil", "Acme Brow Freeze", "", "brow gel"),
    # ...a name with a pencil form never is.
    ("brow pencil", "Acme Brow Pencil", "", None),
    ("brow pencil", "Acme Brow Pomade", "", None),
    ("brow pencil", "Acme Brow Wiz", "Best brow gel?", None),
    ("brow pencil", "Acme Brow Pencil and Gel Duo", "", None),
    # In a thread asking for brow gels, a maker named alone or a hair gel is the writer's brow gel.
    ("brow pencil", "Acme", "Best brow gel for unruly brows?", "brow gel"),
    ("brow pencil", "Acme", "Best brow pencil for sparse brows?", None),
    # Only lipstick and brow pencil mentions are re-typed.
    ("lip balm", "Acme Tinted Lip Balm", "", None),
    ("mascara", "Acme Brow Gel", "", None),
    (None, "Acme Lip Stain", "", None),
])
def test_which_mentions_are_re_typed(typed, product, title, expected):
    assert new_type(typed, product, title) == expected


TINT = "I've worn the {} daily for two whole years, and it lasts through lunch."
LIPSTICK = "The {} has been my everyday lipstick for three years now."
GEL = "I've used the {} every morning for two years, my brows stay put."
PENCIL = "The {} has been my brow pencil for three years, it never smudges."


def write_library(tmp_path: Path, threads: list[tuple[str, str, str, list[tuple[str, str, str, int]]]],
                  created: str = "2025-03-02T10:00:00Z") -> Path:
    """Threads (id, community, title, [(product, typed as, comment text with {} for the name, times)]): each product
    recommended `times` times in the thread, by a different writer each time; each comment's text is its quote."""
    made, extractions = [], {}
    for thread_id, community, title, products in threads:
        comments, mentions = [], []
        for number, (product, typed, text, times) in enumerate(products):
            for i in range(times):
                comment_id = f"{thread_id[1:]}p{number}x{i}"
                body = text.format(product)
                url = f"https://www.reddit.com/r/{community}/comments/{thread_id}/c/{comment_id}/"
                comments.append(make_comment(comment_id, thread_id=thread_id, body=body, created_at=created, url=url))
                mentions.append({"comment_id": comment_id, "product": product, "category": "general",
                                 "product_type": typed, "stance": "recommend", "evidence": "long-term use",
                                 "evidence_tags": ["long-term use"], "quote": body})
        made.append(make_thread(id=thread_id, community=community, category="general", title=title,
                                body="Made-up question.", created_at=created, comments=comments,
                                url=f"https://www.reddit.com/r/{community}/comments/{thread_id}/x/"))
        extractions[thread_id] = mentions
    root = write_gold(tmp_path / "library", made, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for thread_id, mentions in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v16", "extracted_at": "2026-11-04T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions}, indent=1), encoding="utf-8")
    return root


def lip_library(tmp_path: Path) -> Path:
    """Two lip tint threads and two lipstick threads, extracted as before v17: every tint typed "lipstick"."""
    tints = [("Acme Water Tint", "lipstick", TINT, 2), ("Bolt Velvet Stain", "lipstick", TINT, 2)]
    lipsticks = [("Crest Satin Lipstick", "lipstick", LIPSTICK, 2), ("Dune Matte Lipstick", "lipstick", LIPSTICK, 2),
                 ("Acme Water Tint", "lipstick", TINT, 2)]
    return write_library(tmp_path, [
        ("1tint01", "Makeup", "Which lip tint lasts all day?", tints),
        ("1tint02", "AsianBeauty", "Lip tints that stay put?", tints),
        ("1lips01", "Makeup", "Everyday lipstick recommendations?", lipsticks),
        ("1lips02", "Sephora", "Which lipstick do you wear most?", lipsticks),
    ])


def brow_library(tmp_path: Path) -> Path:
    """Two brow gel threads and two brow pencil threads, extracted as before v17: every gel typed "brow pencil"."""
    gels = [("Acme Clear Brow Gel", "brow pencil", GEL, 2), ("Bolt", "brow pencil", GEL, 2)]
    pencils = [("Crest Micro Brow Pencil", "brow pencil", PENCIL, 2), ("Dune Brow Pencil", "brow pencil", PENCIL, 2),
               ("Acme Clear Brow Gel", "brow pencil", GEL, 2)]
    return write_library(tmp_path, [
        ("1gel01", "Makeup", "Best brow gel for unruly brows?", gels),
        ("1gel02", "Sephora", "Brow gels that hold all day?", gels),
        ("1pen01", "Makeup", "Best brow pencil for sparse brows?", pencils),
        ("1pen02", "drugstoreMUA", "Which brow pencil do you swear by?", pencils),
    ])


def picks(result) -> list[str]:
    return [pick.name for pick in result.answer.picks]


def test_before_the_re_typing_a_lipstick_answer_picks_a_tint_and_a_tint_answer_has_none(tmp_path):
    lib = lip_library(tmp_path)
    assert "Acme Water Tint" in picks(answer_request("lipstick", library_dir=lib))
    assert picks(answer_request("lip tint", library_dir=lib)) == []


def test_after_the_re_typing_lip_tint_answers_with_tints_and_lipstick_with_lipsticks(tmp_path):
    lib = lip_library(tmp_path)
    result = retype(lib, write=True)
    assert sorted({r.product for r in result.retyped}) == ["Acme Water Tint", "Bolt Velvet Stain"]
    tint = answer_request("lip tint", library_dir=lib)
    assert tint.answer.title == "Top picks: lip tint"
    assert sorted(picks(tint)) == ["Acme Water Tint", "Bolt Velvet Stain"]
    assert unverified_claims(tint.answer, tint.bodies) == []
    lipstick = answer_request("lipstick", library_dir=lib)
    assert sorted(picks(lipstick)) == ["Crest Satin Lipstick", "Dune Matte Lipstick"]


def test_after_the_re_typing_brow_gel_answers_with_gels_and_brow_pencil_with_pencils(tmp_path):
    lib = brow_library(tmp_path)
    result = retype(lib, write=True)
    assert sorted({r.product for r in result.retyped}) == ["Acme Clear Brow Gel", "Bolt"]
    gel = answer_request("brow gel", library_dir=lib)
    assert gel.answer.title == "Top picks: brow gel"
    assert sorted(picks(gel)) == ["Acme Clear Brow Gel", "Bolt"]
    pencil = answer_request("brow pencil", library_dir=lib)
    assert sorted(picks(pencil)) == ["Crest Micro Brow Pencil", "Dune Brow Pencil"]


def extraction(root: Path, thread_id: str) -> dict:
    return json.loads((root / "extracted" / f"{thread_id}.json").read_text(encoding="utf-8"))


def test_a_dry_run_lists_the_mentions_and_changes_nothing(tmp_path):
    lib = lip_library(tmp_path)
    before = {p.name: p.read_bytes() for p in (lib / "extracted").iterdir()}
    result = retype(lib)
    assert result.dry_run and len(result.retyped) == 12 and sorted(result.files_changed) == [
        "1lips01", "1lips02", "1tint01", "1tint02"]
    assert {p.name: p.read_bytes() for p in (lib / "extracted").iterdir()} == before


def test_writing_changes_only_the_product_type_and_keeps_the_version_and_date(tmp_path):
    lib = lip_library(tmp_path)
    old = extraction(lib, "1lips01")
    retype(lib, write=True)
    new = extraction(lib, "1lips01")
    assert [m["product_type"] for m in new["mentions"]] == ["lipstick"] * 4 + ["lip tint"] * 2
    for before, after in zip(old["mentions"], new["mentions"]):
        assert {k: v for k, v in before.items() if k != "product_type"} == {
            k: v for k, v in after.items() if k != "product_type"}
    assert {k: v for k, v in new.items() if k != "mentions"} == {k: v for k, v in old.items() if k != "mentions"}
    assert retype(lib, write=True).retyped == []  # done once


def test_a_file_another_process_writes_meanwhile_is_left_alone(tmp_path, monkeypatch):
    lib = lip_library(tmp_path)
    path = lib / "extracted" / "1tint01.json"
    real = makeup_types._in_place

    def written_meanwhile(text, places, data):
        if '"1tint01"' in text:
            os.utime(path, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns + 5_000_000_000))
        return real(text, places, data)

    monkeypatch.setattr(makeup_types, "_in_place", written_meanwhile)
    before = path.read_bytes()
    result = retype(lib, write=True)
    assert path.read_bytes() == before and "1tint01" not in result.files_changed
    assert {r.thread_id for r in result.left_for_later} == {"1tint01"}


def test_the_command_prints_ids_and_names_never_quotes(tmp_path, capsys):
    lib = brow_library(tmp_path)
    assert makeup_types.main(["retype", "--library", str(lib)]) == 0
    out = capsys.readouterr().out
    assert "1gel01 gel01p0x0 brow gel: Acme Clear Brow Gel" in out and "dry run" in out
    assert "brows stay put" not in out and "every morning" not in out


# --- (D) Old makeup comments are medium voices at most ---

OLD = years_before(COLLECTED + "T00:00:00Z", config.VOICE_RECENT_YEARS + 2)
RICH = account(created="2010-01-01", karma=500_000, flair="Makeup artist")


def _voice(reformulated: bool, created: str = OLD) -> str:
    comment, thread = make_case(created=created, author=RICH, score=9, others=(1, 1, 2), category="general")
    return score_voice(comment, thread, reformulated=reformulated).level


def test_an_old_comment_counted_for_a_makeup_request_is_a_medium_voice_at_most():
    assert config.OLD_SKINCARE_POST_MAX_VOICE == "medium"
    assert _voice(reformulated=True) == "medium"
    assert _voice(reformulated=False) == "high"  # the same comment for a request about anything else


def test_a_recent_makeup_comment_keeps_its_level():
    recent = years_before(COLLECTED + "T00:00:00Z", 0.2)
    assert _voice(reformulated=True, created=recent + "T10:00:00Z") == "high"


@pytest.mark.parametrize("request_text", ["blush", "lip tint", "brow gel", "lipstick", "brow pencil", "mascara",
                                          "foundation for oily skin", "setting powder", "bronzer"])
def test_every_makeup_request_counts_old_comments_as_reformulated(request_text):
    assert pipeline._reformulated(parse_query(request_text))


@pytest.mark.parametrize("request_text", ["noise cancelling headphones", "hair dryer", "makeup brush", "chef knife"])
def test_other_requests_dont(request_text):
    assert not pipeline._reformulated(parse_query(request_text))


def test_an_old_lip_tint_answer_has_no_high_voice(tmp_path):
    # Every comment of this made-up library is six years old, by writers with long, busy accounts.
    lib = lip_library(tmp_path)
    retype(lib, write=True)
    for path in (lib / "threads").iterdir():
        thread = json.loads(path.read_text(encoding="utf-8"))
        thread["created_at"] = "2020-03-01T09:00:00Z"
        for comment in thread["comments"]:
            comment.update(created_at="2020-03-02T10:00:00Z", score=40,
                           author=RICH | {"name": f"writer_{comment['id']}"})
        path.write_text(json.dumps(thread), encoding="utf-8")
    result = answer_request("lip tint", library_dir=lib)
    assert picks(result) and all(m.voice != "high" for p in result.ranking.products for m in p.mentions)


def test_the_how_page_says_old_makeup_comments_are_capped_too(tmp_path, monkeypatch):
    # A wording fix with (D): the page said "Skincare formulas change", which was already short of haircare's cap.
    from engine.tests.test_how_page import get_how, text_of

    text = text_of(get_how(tmp_path, monkeypatch))
    assert ("Skincare, haircare and makeup formulas change, so a comment about any of them older than 3 years is "
            "medium at most.") in text


# --- (B) The need-fit rule: built, off ---

def blushes(*, cream_voice: str = "medium", by_title: bool = False, needs: tuple[str, ...] = ("cream",)):
    """A popular blush whose voices say nothing about the form, and a less popular one with one credible voice about
    cream (or, `by_title`, a thread title asking for a cream blush)."""
    popular = [mention("Acme Powder Blush", thread, category="general") for thread in ("t1", "t2", "t1", "t2")]
    fitting = [mention("Bolt Rosy Blush", thread, category="general", voice="medium") for thread in ("t1", "t2", "t2")]
    fitting[0] = dataclasses.replace(fitting[0], voice=cream_voice,
                                     **({"needs_by_title": needs} if by_title else {"needs": needs}))
    return popular + fitting


def ranked(scored, request: str):
    return pipeline._ranked(scored, parse_query(request), [], [], need_led=False)


def names(products) -> list[str]:
    return [p.name for p in products]


def test_the_need_fit_rule_is_off_by_default():
    assert config.NEED_FIT_FOR_PICKS is False


def test_off_a_pick_needs_no_voice_about_the_form():
    ranking = ranked(blushes(), "cream blush")
    assert names(ranking.picks) == ["Acme Powder Blush", "Bolt Rosy Blush"]


def test_on_a_pick_without_a_voice_about_the_form_goes_to_also_worth_a_look(monkeypatch):
    monkeypatch.setattr(config, "NEED_FIT_FOR_PICKS", True)
    ranking = ranked(blushes(), "cream blush")
    assert names(ranking.picks) == ["Bolt Rosy Blush"]
    assert names(ranking.past_the_picks) == ["Acme Powder Blush"]  # first under Also worth a look, meeting the bar
    assert names(ranking.worth_a_look)[:1] == ["Acme Powder Blush"]
    acme = next(p for p in ranking.products if p.name == "Acme Powder Blush")
    assert acme.qualifies and not acme.fits_need


def test_on_a_request_without_a_need_is_unchanged(monkeypatch):
    off = names(ranked(blushes(), "blush").picks)
    monkeypatch.setattr(config, "NEED_FIT_FOR_PICKS", True)
    assert names(ranked(blushes(), "blush").picks) == off == ["Acme Powder Blush", "Bolt Rosy Blush"]


def test_on_a_low_voice_about_the_form_doesnt_fit(monkeypatch):
    monkeypatch.setattr(config, "NEED_FIT_FOR_PICKS", True)
    # Bolt keeps its bar (three medium voices counted: one more), but its only cream voice is a low one.
    scored = blushes(cream_voice="low") + [mention("Bolt Rosy Blush", "t1", category="general", voice="medium")]
    assert names(ranked(scored, "cream blush").picks) == []


def test_on_a_thread_title_asking_for_the_need_is_not_enough(monkeypatch):
    # The need rule counts a top-level answer in a thread asking for the need (Noemi's decision (d) of 19 Oct 2026); the
    # need-fit rule asks for a voice whose own words talk about it, as the reason line counts "about cream".
    monkeypatch.setattr(config, "NEED_FIT_FOR_PICKS", True)
    assert names(ranked(blushes(by_title=True), "cream blush").picks) == []


def test_on_long_term_use_fits_a_request_for_something_that_lasts(monkeypatch):
    monkeypatch.setattr(config, "NEED_FIT_FOR_PICKS", True)
    assert names(ranked(blushes(needs=("lasting",)), "blush that lasts all day").picks) == ["Bolt Rosy Blush"]


def test_on_a_feature_talked_about_without_praise_for_the_product_doesnt_fit(monkeypatch):
    monkeypatch.setattr(config, "NEED_FIT_FOR_PICKS", True)
    scored = blushes()
    scored[4] = dataclasses.replace(scored[4], needs_unpraised=("cream",))
    assert names(ranked(scored, "cream blush").picks) == []


def test_on_the_first_word_of_a_two_word_need_alone_doesnt_fit(monkeypatch):
    # "dark" alone is a skin tone, not dark circles (config.NEED_PHRASES_WHOLE, as the reason line reads it).
    monkeypatch.setattr(config, "NEED_FIT_FOR_PICKS", True)
    request = "concealer for dark circles"
    assert names(ranked(blushes(needs=("dark",)), request).picks) == []
    assert names(ranked(blushes(needs=("circles",)), request).picks) == ["Bolt Rosy Blush"]
    assert names(ranked(blushes(needs=("dark", "circles")), request).picks) == ["Bolt Rosy Blush"]
