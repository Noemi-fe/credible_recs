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


def test_a_file_another_process_writes_meanwhile_is_left_to_it(tmp_path, monkeypatch):
    # The library is shared with the extractors: a file changed between this command's read and its write is never
    # written over; its decisions are left for later.
    root = coat_library(tmp_path)
    path = root / "extracted" / f"{TID}.json"
    real = ethics.extraction_bytes

    def meanwhile(data, like=""):
        path.write_text(like.replace("claude-code", "claude-code-2"), encoding="utf-8")  # someone else's write
        later = datetime(2026, 10, 15, 3, 0).timestamp()
        os.utime(path, (later, later))
        return real(data, like=like)

    monkeypatch.setattr(ethics, "extraction_bytes", meanwhile)
    thread_before = (root / "threads" / f"{TID}.json").read_bytes()
    result = apply(root, [REMOVE_ACME], write=True)
    assert result.removed == [] and result.left_for_later == [REMOVE_ACME]
    assert "claude-code-2" in path.read_text(encoding="utf-8")
    assert (root / "threads" / f"{TID}.json").read_bytes() == thread_before


# --- Ethics-only praise (Noemi's decision 2 of 15 Oct 2026, afternoon: her ethics rule goes both ways) ---
# A recommendation resting only on a maker's ethics, eco claims, identity or origin counts for nothing, as an
# ethics-only warning does; a comment that also judges the product counts for that judgement only. All made up.

PID = "1boot01"
ORIGIN = "Buy American, get the Liberty boots: made in the USA."
STILL_WARM = "Ten years on, my Corvid coat is still warm, and it's cruelty-free too."
OWNED = "Support a woman-owned business and get the Ivy shoes."
SOFTEST = "The Pinecrest sheets are the softest I've slept on, and the brand is B Corp certified."
PLAIN = "The Brightline parka kept me warm for six winters, buy it."
ENGLAND = "Made in England, and the Wexford knife holds an edge for months."
TREATS = "Avoid Acme coats, the company treats animals badly."
LOOK_FOR = "Look for cruelty-free brands."


def praise_comment(comment_id: str, body: str) -> dict:
    return make_comment(comment_id, thread_id=PID, body=body,
                        url=f"https://www.reddit.com/r/BuyItForLife/comments/{PID}/comment/{comment_id}/")


def praise_mention(comment_id: str, product: str, stance: str, quote: str) -> dict:
    return {"comment_id": comment_id, "product": product, "category": "general", "product_type": "boots",
            "stance": stance, "evidence": "short-term use", "evidence_tags": ["short-term use"], "quote": quote}


def praise_library(tmp_path: Path) -> Path:
    bodies = {"p1origin": ORIGIN, "p2warm": STILL_WARM, "p3owned": OWNED, "p4soft": SOFTEST, "p5plain": PLAIN,
              "p6england": ENGLAND, "p7treats": TREATS, "p8look": LOOK_FOR}
    comments = [praise_comment(comment_id, body) for comment_id, body in bodies.items()]
    thread = make_thread(id=PID, community="BuyItForLife", category="general", title="Things that last?",
                         body="Looking for gear that lasts.", comments=comments, num_comments=len(comments),
                         url=f"https://www.reddit.com/r/BuyItForLife/comments/{PID}/things/")
    root = write_gold(tmp_path / "library", [thread], voices=None, mentions=None)
    (root / "extracted").mkdir()
    (root / "extracted" / f"{PID}.json").write_text(json.dumps({
        "thread_id": PID, "instructions_version": "extract-v14", "extracted_at": "2026-10-15T10:00:00Z",
        "extractor": "claude-code",
        "mentions": [praise_mention("p1origin", "Liberty boots", "recommend", ORIGIN),
                     praise_mention("p2warm", "Corvid coat", "recommend", STILL_WARM),
                     praise_mention("p3owned", "Ivy shoes", "recommend", OWNED),
                     praise_mention("p4soft", "Pinecrest sheets", "recommend", SOFTEST),
                     praise_mention("p5plain", "Brightline parka", "recommend", PLAIN),
                     praise_mention("p6england", "Wexford knife", "recommend", ENGLAND),
                     praise_mention("p7treats", "Acme coats", "warn", TREATS)],
        "notes": [{"comment_id": "p8look", "about": "cruelty-free brands", "stance": "recommend", "quote": LOOK_FOR}],
    }, indent=1), encoding="utf-8")
    result = slim.slim_library(root, now=NOW, gold_ids=set())
    assert result.slimmed == [PID], result
    return root


def test_with_stance_recommend_the_candidates_are_praise_resting_on_ethics_eco_identity_or_origin_words(tmp_path):
    root = praise_library(tmp_path)
    found = {(c.comment_id, c.kind, c.name): c for c in candidates(root, stance="recommend")}
    assert set(found) == {("p1origin", "mention", "Liberty boots"), ("p2warm", "mention", "Corvid coat"),
                          ("p3owned", "mention", "Ivy shoes"), ("p4soft", "mention", "Pinecrest sheets"),
                          ("p6england", "mention", "Wexford knife"), ("p8look", "note", "cruelty-free brands")}
    assert "origin" in found[("p1origin", "mention", "Liberty boots")].families
    assert "animal" in found[("p2warm", "mention", "Corvid coat")].families
    assert "identity" in found[("p3owned", "mention", "Ivy shoes")].families
    assert "eco" in found[("p4soft", "mention", "Pinecrest sheets")].families
    assert all(c.stance == "recommend" for c in found.values())
    # A recommendation about the product alone is never one, and the warnings stay the default's.
    assert {c.comment_id for c in candidates(root)} == {"p7treats"}
    assert all(c.stance == "warn" for c in candidates(root))


def test_the_candidates_command_lists_recommendations_by_ids_and_families_never_words(tmp_path, capsys):
    root = praise_library(tmp_path)
    assert ethics.main(["candidates", "--stance", "recommend", "--library", str(root)]) == 0
    out = capsys.readouterr().out
    assert "recommendation(s)" in out and f"{PID} p1origin mention [Liberty boots]" in out and "origin" in out
    assert "p7treats" not in out
    for words in (ORIGIN, STILL_WARM, OWNED, SOFTEST, ENGLAND, "made in the USA", "woman-owned"):
        assert words not in out, words


def test_an_ethics_only_recommendation_is_removed_and_a_mixed_one_keeps_its_judgement_of_the_product(tmp_path):
    root = praise_library(tmp_path)
    decisions = [Decision(PID, "p1origin", "mention", "Liberty boots", "remove"),
                 Decision(PID, "p3owned", "mention", "Ivy shoes", "remove"),
                 Decision(PID, "p8look", "note", "cruelty-free brands", "remove"),
                 Decision(PID, "p2warm", "mention", "Corvid coat", "requote",
                          quote="Ten years on, my Corvid coat is still warm"),
                 Decision(PID, "p6england", "mention", "Wexford knife", "requote",
                          quote="the Wexford knife holds an edge for months")]
    result = apply(root, decisions, write=True)
    assert result.refused == {} and len(result.removed) == 3 and len(result.requoted) == 2
    data = json.loads((root / "extracted" / f"{PID}.json").read_text(encoding="utf-8"))
    by_comment = {m["comment_id"]: m for m in data["mentions"]}
    assert set(by_comment) == {"p2warm", "p4soft", "p5plain", "p6england", "p7treats"} and data["notes"] == []
    assert by_comment["p2warm"]["quote"] == "Ten years on, my Corvid coat is still warm"
    assert by_comment["p2warm"]["stance"] == by_comment["p6england"]["stance"] == "recommend"
    thread = Thread.model_validate_json((root / "threads" / f"{PID}.json").read_bytes())
    stubs = {c.id for c in thread.comments if c.status == "not_kept"}
    assert {"p1origin", "p3owned", "p8look"} <= stubs and not {"p2warm", "p6england"} & stubs
    checked = check_extraction(Extraction.model_validate(data), thread)
    assert checked.rejected == [] and len(checked.kept) == 5
