"""Ethics-only warnings (Noemi's decision 5 of 15 Oct 2026): a warning that rests only on a maker's ethics (animal
welfare, labour practices, politics, a boycott) and says nothing about the product itself counts for nothing; a
comment that also judges the product counts for that judgement only.

Extraction instructions v14 say so for new extractions. For the library's older ones, engine/ethics.py lists keyword
candidates (ids and keyword families only, never anyone's words), a person judges each from its quote and comment,
and the decisions are applied: an ethics-only item is removed, a mixed one keeps its judgement of the product with
its own quote. A slimmed thread keeps whole only the comments answers use (Noemi's "Keep only comments we use", 13 Oct
2026), so a comment left with nothing to use keeps only its shape, as one not verified in time does.

Every comment, product and library here is made up, and every library is a temporary folder.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from engine import ethics, slim
from engine.ethics import Decision, apply, candidates
from engine.extract import Extraction, check_extraction
from engine.models import Thread
from engine.tests.factories import make_comment, make_thread, write_gold

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
TID = "1coat01"

ANIMALS = "I stopped buying Acme winter coats after reading about how the company treats animals."
WARM = "The Brightline parka kept me warm for six winters, buy it."
MIXED = "Avoid the Zenith jacket, the zip broke in a month, and the owner's politics are awful anyway."
SAME = "Same, they won't get a penny from me."
KIND = "My Corvid coat is cruelty-free and has lasted ten years."
NOTE = "Avoid brands that test on animals."
BROKE = "The Ridge coat's seams split in the first winter."
TURN = "The Halo coat is the warmest I've owned, but I quit buying from them over the founder's views."


def comment(comment_id: str, body: str, **overrides) -> dict:
    return make_comment(comment_id, thread_id=TID, body=body,
                        url=f"https://www.reddit.com/r/BuyItForLife/comments/{TID}/comment/{comment_id}/", **overrides)


def mention(comment_id: str, product: str, stance: str, quote: str, **more) -> dict:
    return {"comment_id": comment_id, "product": product, "category": "general", "product_type": "winter coat",
            "stance": stance, "evidence": "short-term use", "evidence_tags": ["short-term use"], "quote": quote, **more}


def coat_library(tmp_path: Path, slimmed: bool = True) -> Path:
    comments = [comment("e1animals", ANIMALS), comment("e2warm", WARM), comment("e3mixed", MIXED),
                comment("e4same", SAME, parent_id="e1animals"), comment("e5kind", KIND), comment("e6note", NOTE),
                comment("e7broke", BROKE), comment("e8turn", TURN)]
    thread = make_thread(id=TID, community="BuyItForLife", category="general", title="Winter coat that lasts?",
                         body="Mine fell apart after two winters.", comments=comments, num_comments=len(comments),
                         url=f"https://www.reddit.com/r/BuyItForLife/comments/{TID}/winter_coat/")
    root = write_gold(tmp_path / "library", [thread], voices=None, mentions=None)
    (root / "extracted").mkdir()
    (root / "extracted" / f"{TID}.json").write_text(json.dumps({
        "thread_id": TID, "instructions_version": "extract-v13", "extracted_at": "2026-10-14T10:00:00Z",
        "extractor": "claude-code",
        "mentions": [mention("e1animals", "Acme winter coats", "warn", ANIMALS),
                     mention("e2warm", "Brightline parka", "recommend", WARM),
                     mention("e3mixed", "Zenith jacket", "warn", MIXED),
                     mention("e5kind", "Corvid coat", "recommend", KIND),
                     mention("e7broke", "Ridge coat", "warn", BROKE),
                     mention("e8turn", "Halo coat", "warn", TURN)],
        "notes": [{"comment_id": "e6note", "about": "brands that test on animals", "stance": "warn", "quote": NOTE}],
    }, indent=1), encoding="utf-8")
    if slimmed:
        result = slim.slim_library(root, now=NOW, gold_ids=set())
        assert result.slimmed == [TID], result
    return root


def thread_of(root: Path) -> Thread:
    return Thread.model_validate_json((root / "threads" / f"{TID}.json").read_bytes())


def extraction_of(root: Path) -> dict:
    return json.loads((root / "extracted" / f"{TID}.json").read_text(encoding="utf-8"))


REMOVE_ACME = Decision(TID, "e1animals", "mention", "Acme winter coats", "remove")
REMOVE_NOTE = Decision(TID, "e6note", "note", "brands that test on animals", "remove")
REQUOTE_ZENITH = Decision(TID, "e3mixed", "mention", "Zenith jacket", "requote",
                          quote="Avoid the Zenith jacket, the zip broke in a month")


# --- Candidates: warnings whose quote or comment holds an ethics word ---

def test_the_candidates_are_warnings_with_ethics_words_in_their_quote_or_comment(tmp_path):
    root = coat_library(tmp_path)
    found = {(c.comment_id, c.kind, c.name): c for c in candidates(root)}
    assert set(found) == {("e1animals", "mention", "Acme winter coats"), ("e3mixed", "mention", "Zenith jacket"),
                          ("e6note", "note", "brands that test on animals"), ("e8turn", "mention", "Halo coat")}
    assert found[("e1animals", "mention", "Acme winter coats")].families == ("animal",)
    assert found[("e3mixed", "mention", "Zenith jacket")].families == ("politics",)
    assert all(c.in_quote and not c.newer for c in found.values())
    # A recommendation is never one (the rule is about warnings), nor a warning about the product itself.
    assert not any(c.comment_id in ("e2warm", "e5kind", "e7broke") for c in found.values())


def test_a_candidate_in_a_file_changed_since_a_time_is_marked_newer(tmp_path):
    root = coat_library(tmp_path, slimmed=False)
    path = root / "extracted" / f"{TID}.json"
    late = datetime(2026, 10, 15, 0, 30).timestamp()
    os.utime(path, (late, late))
    assert all(c.newer for c in candidates(root, since=datetime(2026, 10, 15, 0, 0)))
    assert not any(c.newer for c in candidates(root, since=datetime(2026, 10, 15, 1, 0)))


def test_the_candidates_command_prints_ids_and_keyword_families_never_words(tmp_path, capsys):
    root = coat_library(tmp_path)
    assert ethics.main(["candidates", "--library", str(root)]) == 0
    out = capsys.readouterr().out
    assert f"{TID} e1animals mention" in out and "animal" in out
    for words in (ANIMALS, MIXED, NOTE, "treats animals", "politics are awful"):
        assert words not in out, words


# --- Applying the decisions ---

def test_an_ethics_only_warning_is_removed_and_its_comment_keeps_only_its_shape(tmp_path):
    root = coat_library(tmp_path)
    old = extraction_of(root)
    result = apply(root, [REMOVE_ACME, REMOVE_NOTE], write=True)
    assert result.removed == [REMOVE_ACME, REMOVE_NOTE] and result.refused == {}
    new = extraction_of(root)
    assert [m["comment_id"] for m in new["mentions"]] == ["e2warm", "e3mixed", "e5kind", "e7broke", "e8turn"]
    assert new["notes"] == []
    assert [m for m in new["mentions"]] == [m for m in old["mentions"] if m["comment_id"] != "e1animals"]
    assert {k: new[k] for k in ("instructions_version", "extracted_at")} == {
        k: old[k] for k in ("instructions_version", "extracted_at")}
    thread = thread_of(root)
    by_id = {c.id: c for c in thread.comments}
    for gone in ("e1animals", "e6note"):  # nothing of theirs is used any more
        assert (by_id[gone].status, by_id[gone].body, by_id[gone].author) == ("not_kept", "", None), gone
    assert "winter coat" in thread.whole_thread.comment_names["e1animals"]  # module 2 still counts what it named
    assert sorted(result.stubbed) == [(TID, "e1animals"), (TID, "e6note")]
    for kept in ("e2warm", "e3mixed", "e5kind", "e7broke", "e8turn"):
        assert by_id[kept].status == "ok" and by_id[kept].body, kept
    checked = check_extraction(Extraction.model_validate(new), thread)
    assert checked.rejected == [] and len(checked.kept) == 5


def test_a_mixed_warning_keeps_its_judgement_of_the_product_with_its_own_quote(tmp_path):
    root = coat_library(tmp_path)
    result = apply(root, [REQUOTE_ZENITH], write=True)
    assert result.requoted == [REQUOTE_ZENITH] and result.stubbed == []
    zenith = next(m for m in extraction_of(root)["mentions"] if m["comment_id"] == "e3mixed")
    assert zenith["quote"] == "Avoid the Zenith jacket, the zip broke in a month" and zenith["stance"] == "warn"
    checked = check_extraction(Extraction.model_validate(extraction_of(root)), thread_of(root))
    assert any(m.comment_id == "e3mixed" for m in checked.kept) and checked.rejected == []


def test_a_judgement_of_the_product_can_turn_the_stance(tmp_path):
    # "The warmest I've owned, but I quit buying from them over the founder's views": the warning rests on the maker's
    # ethics alone, so what counts is the judgement left, a recommendation.
    root = coat_library(tmp_path)
    turned = Decision(TID, "e8turn", "mention", "Halo coat", "requote", quote="The Halo coat is the warmest I've owned",
                      stance="recommend", evidence="short-term use", evidence_tags=("short-term use",))
    result = apply(root, [turned], write=True)
    assert result.requoted == [turned] and result.refused == {}
    halo = next(m for m in extraction_of(root)["mentions"] if m["comment_id"] == "e8turn")
    assert (halo["quote"], halo["stance"], halo["evidence"], halo["evidence_tags"]) == (
        "The Halo coat is the warmest I've owned", "recommend", "short-term use", ["short-term use"])
    checked = check_extraction(Extraction.model_validate(extraction_of(root)), thread_of(root))
    assert any(m.comment_id == "e8turn" and m.stance == "recommend" for m in checked.kept)


@pytest.mark.parametrize("decision, why", [
    (Decision(TID, "e3mixed", "mention", "Zenith jacket", "requote", quote="the zip broke on day one"),
     "isn't word for word"),
    (Decision(TID, "e9none", "mention", "Nobody coat", "remove"), "no such item"),
    (Decision(TID, "e3mixed", "mention", "Zenith jacket", "requote"), "a requote needs its quote"),
])
def test_a_decision_that_cant_be_applied_is_refused_and_nothing_is_written(tmp_path, decision, why):
    root = coat_library(tmp_path)
    before = (root / "extracted" / f"{TID}.json").read_bytes(), (root / "threads" / f"{TID}.json").read_bytes()
    result = apply(root, [REMOVE_ACME, decision], write=True)
    assert why in " ".join(result.refused.values()), result.refused
    assert ((root / "extracted" / f"{TID}.json").read_bytes(), (root / "threads" / f"{TID}.json").read_bytes()) == before


def test_a_dry_run_says_what_it_would_do_and_writes_nothing(tmp_path):
    root = coat_library(tmp_path)
    before = (root / "extracted" / f"{TID}.json").read_bytes(), (root / "threads" / f"{TID}.json").read_bytes()
    result = apply(root, [REMOVE_ACME, REQUOTE_ZENITH])
    assert result.dry_run and result.removed == [REMOVE_ACME] and result.requoted == [REQUOTE_ZENITH]
    assert result.stubbed == [(TID, "e1animals")]
    assert ((root / "extracted" / f"{TID}.json").read_bytes(), (root / "threads" / f"{TID}.json").read_bytes()) == before


def test_a_whole_thread_only_loses_the_item(tmp_path):
    # A thread not slimmed yet keeps every comment whole until slimming, which then keeps only those still used.
    root = coat_library(tmp_path, slimmed=False)
    thread_before = (root / "threads" / f"{TID}.json").read_bytes()
    result = apply(root, [REMOVE_ACME], write=True)
    assert result.removed == [REMOVE_ACME] and result.stubbed == []
    assert (root / "threads" / f"{TID}.json").read_bytes() == thread_before
    assert "e1animals" not in {m["comment_id"] for m in extraction_of(root)["mentions"]}


def test_a_file_changed_since_the_cutoff_is_left_alone_and_listed(tmp_path):
    # 15 Oct 2026: three extractors, already told the rule, were publishing new files; theirs wait for their lists.
    root = coat_library(tmp_path)
    path = root / "extracted" / f"{TID}.json"
    late = datetime(2026, 10, 15, 0, 30).timestamp()
    os.utime(path, (late, late))
    before = path.read_bytes()
    result = apply(root, [REMOVE_ACME], write=True, before=datetime(2026, 10, 15, 0, 0))
    assert result.removed == [] and result.left_for_later == [REMOVE_ACME]
    assert path.read_bytes() == before


def test_decisions_load_from_a_file_of_ids_and_names(tmp_path):
    path = tmp_path / "decisions.json"
    path.write_text(json.dumps([
        {"thread_id": TID, "comment_id": "e1animals", "kind": "mention", "name": "Acme winter coats",
         "action": "remove"},
        {"thread_id": TID, "comment_id": "e3mixed", "kind": "mention", "name": "Zenith jacket", "action": "requote",
         "quote": "Avoid the Zenith jacket, the zip broke in a month"}]), encoding="utf-8")
    assert ethics.load_decisions(path) == [REMOVE_ACME, REQUOTE_ZENITH]
