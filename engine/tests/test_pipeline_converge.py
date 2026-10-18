"""End to end, the converge round of 17 Oct 2026 (ws-ranking): a feature the request names ranks first the products a
credible voice praises for it, and the answer says so when no pick is (Noemi's decision 1 of 16 Oct 2026); a skincare
warning from the opposite need doesn't put a product under Skip these (her decision 2).

Made-up libraries written to a temporary folder (every comment invented), as engine/tests/test_pipeline.py does.
"""

import json
from pathlib import Path

from engine.answer import unverified_claims
from engine.features import FEATURE_NOT_PRAISED
from engine.pipeline import answer_request
from engine.tests.factories import make_comment, make_thread, write_gold


def comment(cid: str, tid: str, body: str, community: str) -> dict:
    return make_comment(cid, thread_id=tid, body=body,
                        url=f"https://www.reddit.com/r/{community}/comments/{tid}/comment/{cid}/")


def write_library(tmp_path: Path, threads: list[tuple[str, str, str, str, list[tuple[str, str, str, str]]]]) -> Path:
    """threads: (id, community, category, title, [(comment id, body, product, stance)])."""
    made, extractions = [], {}
    for tid, community, category, title, comments in threads:
        made.append(make_thread(id=tid, community=community, category=category, title=title, body="Any advice?",
                                url=f"https://www.reddit.com/r/{community}/comments/{tid}/t/",
                                comments=[comment(cid, tid, body, community) for cid, body, _, _ in comments]))
        extractions[tid] = [{"comment_id": cid, "product": product, "category": category, "stance": stance,
                             "quote": body} for cid, body, product, stance in comments]
    root = write_gold(tmp_path / "library", made, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for tid, mentions in extractions.items():
        (root / "extracted" / f"{tid}.json").write_text(json.dumps({
            "thread_id": tid, "instructions_version": "extract-v5", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions}), encoding="utf-8")
    return root


def kettles(tmp_path: Path, calm_praised: bool) -> Path:
    calm = ("I've had my Calm kettle for 3 years and it is so quiet in the morning." if calm_praised
            else "I've had my Calm kettle for 3 years and it boils fast.")
    return write_library(tmp_path, [
        ("1kq001", "BuyItForLife", "kitchen", "Which electric kettle lasts?", [
            ("q1a", "I've used my Brio kettle every day for 6 years, still perfect.", "Brio kettle", "recommend"),
            ("q1b", "My Brio kettle has lasted 8 years so far.", "Brio kettle", "recommend"),
            ("q1c", calm, "Calm kettle", "recommend"),
            ("q1d", "I've used the Calm kettle for 2 years, never a problem.", "Calm kettle", "recommend"),
        ]),
        ("1kq002", "BuyItForLife", "kitchen", "Electric kettle recommendations?", [
            ("q2a", "Our Brio kettle is 9 years old and still going strong.", "Brio kettle", "recommend"),
            ("q2b", "I've had the Brio kettle for 5 years, love it.", "Brio kettle", "recommend"),
            ("q2c", "Had my Calm kettle 4 years, it pours well.", "Calm kettle", "recommend"),
        ]),
    ])


def test_a_quiet_kettle_puts_first_the_one_praised_for_being_quiet(tmp_path):
    result = answer_request("a quiet electric kettle", library_dir=kettles(tmp_path, calm_praised=True))
    assert [pick.name for pick in result.answer.picks] == ["Calm kettle", "Brio kettle"]
    assert not result.answer.message or FEATURE_NOT_PRAISED.split("{")[0] not in result.answer.message
    assert unverified_claims(result.answer, result.bodies) == []


def test_without_a_feature_the_best_supported_comes_first(tmp_path):
    result = answer_request("electric kettle", library_dir=kettles(tmp_path, calm_praised=True))
    assert [pick.name for pick in result.answer.picks] == ["Brio kettle", "Calm kettle"]


def test_when_no_pick_is_praised_for_the_feature_the_answer_still_shows_them_and_says_so(tmp_path):
    result = answer_request("a quiet electric kettle", library_dir=kettles(tmp_path, calm_praised=False))
    assert [pick.name for pick in result.answer.picks] == ["Brio kettle", "Calm kettle"]
    # After the answer's own message (only two kettles meet the bar here), the note about the feature.
    assert result.answer.message.startswith("Enough credible evidence for only 2 products")
    assert result.answer.message.endswith(FEATURE_NOT_PRAISED.format(features='"quiet"', products="electric kettles"))


def moisturisers(tmp_path: Path) -> Path:
    # Acme cream: warned against in two threads, but only by writers with oily skin, in a dry-skin answer.
    return write_library(tmp_path, [
        ("1mz001", "SkincareAddiction", "skincare", "Moisturiser for dry skin?", [
            ("m1a", "I've used the Fern cream for 2 years on my dry skin, it is lovely.", "Fern cream", "recommend"),
            ("m1b", "I've had the Fern cream for a year, my dry patches are gone.", "Fern cream", "recommend"),
            ("m1c", "The Acme cream was far too heavy on my oily skin, I broke out.", "Acme cream", "warn"),
        ]),
        ("1mz002", "SkincareAddiction", "skincare", "Best moisturiser for dry winter skin?", [
            ("m2a", "I've used the Fern cream every winter for 3 years, my dry skin loves it.", "Fern cream",
             "recommend"),
            ("m2b", "I tried the Acme cream and it left my oily skin greasy all day.", "Acme cream", "warn"),
        ]),
    ])


def test_oily_skin_complaints_dont_put_a_cream_under_skip_these_in_a_dry_skin_answer(tmp_path):
    root = moisturisers(tmp_path)
    dry = answer_request("moisturiser for dry skin", library_dir=root)
    assert [item.name for item in dry.answer.skip] == []
    oily = answer_request("moisturiser for oily skin", library_dir=root)
    assert [item.name for item in oily.answer.skip] == ["Acme cream"]
