"""Finding and re-quoting the library's incoherent quotes (Noemi's decision 4 of 15 Oct 2026; engine/quote_coherence.py).

Candidates are found by code: a recommendation whose quote reads as a failure or a complaint, a warning whose quote reads
as praise (engine.answer.reads_against_its_stance), and a quote about another product of its comment (another type, the
same stance). Only ids, names and what was found are printed, never anyone's words. A person reads each candidate's
comment and, where a better word-for-word span of it carries the stance and names or points at the product, decides a
requote; the decisions are applied as engine/ethics.py applies its own, checked as an extraction is.

Every comment, product and library here is made up, and every library is a temporary folder.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from engine import quote_coherence, slim
from engine.ethics import Decision
from engine.extract import Extraction, check_extraction
from engine.models import Thread
from engine.quote_coherence import apply, candidates
from engine.tests.factories import make_comment, make_thread, write_gold

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
TID = "1tele01"

LONG_LIFE = ("My current Acme TV is holding up great at three years old. Our previous Acme we had for 14 years and "
             "then the backlight gave out.")
WARM = "I loved the Zeta kettle for a while. Then the lid hinge snapped and the base started leaking."
BOTH = "I'm happy with my Corvo cast iron, but my Corvo carbon steel skillet has replaced it for nearly everything."
FINE = "My Brightline TV has been great for six years."
TURNS = "The Delta kettle's handle broke after ten years, but they sent me a new one for free."
ASKS = "Is the Omega TV any good?"


def comment(comment_id: str, body: str) -> dict:
    return make_comment(comment_id, thread_id=TID, body=body,
                        url=f"https://www.reddit.com/r/BuyItForLife/comments/{TID}/comment/{comment_id}/")


def mention(comment_id: str, product: str, product_type: str, stance: str, quote: str, evidence: str = "long-term use",
            tags: tuple[str, ...] = ("long-term use",)) -> dict:
    return {"comment_id": comment_id, "product": product, "category": "general", "product_type": product_type,
            "stance": stance, "evidence": evidence, "evidence_tags": list(tags), "quote": quote}


def library(tmp_path: Path) -> Path:
    bodies = {"q1life": LONG_LIFE, "q2warm": WARM, "q3both": BOTH, "q4fine": FINE, "q5turns": TURNS, "q6asks": ASKS}
    comments = [comment(comment_id, body) for comment_id, body in bodies.items()]
    thread = make_thread(id=TID, community="BuyItForLife", category="general", title="Things that last?",
                         body="Looking for things that last.", comments=comments, num_comments=len(comments),
                         url=f"https://www.reddit.com/r/BuyItForLife/comments/{TID}/things/")
    root = write_gold(tmp_path / "library", [thread], voices=None, mentions=None)
    (root / "extracted").mkdir()
    (root / "extracted" / f"{TID}.json").write_text(json.dumps({
        "thread_id": TID, "instructions_version": "extract-v14", "extracted_at": "2026-10-15T10:00:00Z",
        "extractor": "claude-code",
        "mentions": [
            mention("q1life", "Acme", "tv", "recommend", "Our previous Acme we had for 14 years and then the backlight "
                                                          "gave out.", tags=("long-term use", "mentions flaws")),
            mention("q2warm", "Zeta kettle", "electric kettle", "warn", "I loved the Zeta kettle for a while.",
                    evidence="short-term use", tags=("short-term use",)),
            mention("q3both", "Corvo cast iron", "cast iron skillet", "recommend", BOTH),
            mention("q3both", "Corvo carbon steel skillet", "frying pan", "recommend",
                    "my Corvo carbon steel skillet has replaced it for nearly everything."),
            mention("q4fine", "Brightline TV", "tv", "recommend", FINE),
            mention("q5turns", "Delta kettle", "electric kettle", "recommend", TURNS),
            mention("q6asks", "Omega TV", "tv", "neutral", ASKS, evidence="no first-hand use", tags=("asks about it",)),
        ],
    }, indent=1), encoding="utf-8")
    result = slim.slim_library(root, now=NOW, gold_ids=set())
    assert result.slimmed == [TID], result
    return root


def extraction_of(root: Path) -> dict:
    return json.loads((root / "extracted" / f"{TID}.json").read_text(encoding="utf-8"))


def thread_of(root: Path) -> Thread:
    return Thread.model_validate_json((root / "threads" / f"{TID}.json").read_bytes())


# --- Candidates ---

def test_the_candidates_are_quotes_that_read_against_their_stance_or_are_about_another_product(tmp_path):
    root = library(tmp_path)
    found = {(c.comment_id, c.name): c for c in candidates(root)}
    assert set(found) == {("q1life", "Acme"), ("q2warm", "Zeta kettle"), ("q3both", "Corvo cast iron")}
    assert found[("q1life", "Acme")].reads == "failure" and found[("q1life", "Acme")].stance == "recommend"
    assert found[("q2warm", "Zeta kettle")].reads == "praise" and found[("q2warm", "Zeta kettle")].stance == "warn"
    assert found[("q3both", "Corvo cast iron")].reads == "another product"
    # A coherent quote, one whose words turn back to its stance, and a neutral mention are never candidates; nor is the
    # other product itself, whose quote is about it.
    assert not {"q4fine", "q5turns", "q6asks"} & {c.comment_id for c in found.values()}
    assert ("q3both", "Corvo carbon steel skillet") not in found


def test_the_candidates_command_prints_ids_names_and_what_was_found_never_words(tmp_path, capsys):
    root = library(tmp_path)
    assert quote_coherence.main(["candidates", "--library", str(root)]) == 0
    out = capsys.readouterr().out
    assert f"{TID} q1life recommend [Acme] reads=failure" in out and "3 quote(s)" in out
    for words in (LONG_LIFE, WARM, BOTH, "backlight gave out", "loved the Zeta"):
        assert words not in out, words


# --- Re-quoting ---

def test_a_long_life_failure_is_requoted_for_its_long_life_and_keeps_its_stance(tmp_path):
    root = library(tmp_path)
    decisions = [Decision(TID, "q1life", "mention", "Acme", "requote",
                          quote="My current Acme TV is holding up great at three years old."),
                 Decision(TID, "q2warm", "mention", "Zeta kettle", "requote",
                          quote="the lid hinge snapped and the base started leaking"),
                 Decision(TID, "q3both", "mention", "Corvo cast iron", "requote",
                          quote="I'm happy with my Corvo cast iron")]
    result = apply(root, decisions, write=True)
    assert result.refused == {} and len(result.requoted) == 3 and result.stubbed == []
    by_comment = {(m["comment_id"], m["product"]): m for m in extraction_of(root)["mentions"]}
    acme = by_comment[("q1life", "Acme")]
    assert acme["quote"] == "My current Acme TV is holding up great at three years old."
    assert (acme["stance"], acme["evidence"], acme["evidence_tags"]) == ("recommend", "long-term use",
                                                                         ["long-term use", "mentions flaws"])
    assert by_comment[("q2warm", "Zeta kettle")]["stance"] == "warn"
    checked = check_extraction(Extraction.model_validate(extraction_of(root)), thread_of(root))
    assert checked.rejected == []
    assert {(c.comment_id, c.name) for c in candidates(root)} == set()  # nothing incoherent left


def test_a_requote_that_isnt_word_for_word_is_refused_and_nothing_is_written(tmp_path):
    root = library(tmp_path)
    before = (root / "extracted" / f"{TID}.json").read_bytes()
    result = apply(root, [Decision(TID, "q1life", "mention", "Acme", "requote",
                                   quote="My Acme TV has held up for three years.")], write=True)
    assert "isn't word for word" in " ".join(result.refused.values())
    assert (root / "extracted" / f"{TID}.json").read_bytes() == before


def test_a_requote_over_fifty_words_is_refused(tmp_path):
    root = library(tmp_path)
    long_quote = " ".join(["word"] * 51)
    result = apply(root, [Decision(TID, "q4fine", "mention", "Brightline TV", "requote", quote=long_quote)])
    assert result.refused
