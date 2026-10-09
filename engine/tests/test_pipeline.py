"""The thin end-to-end slice: a request typed in plain words goes through modules 1 to 7 and comes back as a top 3.

A made-up library of two kettle threads, written to a temporary folder with their extraction files, so no test
reads data/.
"""

import json
from pathlib import Path

from engine.answer import unverified_claims
from engine.pipeline import answer_request
from engine.tests.factories import make_comment, make_thread, write_gold

REQUEST = "electric kettle that lasts 10+ years"


def kettle_thread(thread_id: str, comments: list[dict]) -> dict:
    return make_thread(
        id=thread_id, community="BuyItForLife", category="kitchen", title="Which electric kettle lasts?",
        body="My kettle died again.", url=f"https://www.reddit.com/r/BuyItForLife/comments/{thread_id}/kettle/",
        comments=comments,
    )


def comment(comment_id: str, thread_id: str, body: str, **overrides) -> dict:
    url = f"https://www.reddit.com/r/BuyItForLife/comments/{thread_id}/comment/{comment_id}/"
    return make_comment(comment_id, thread_id=thread_id, body=body, url=url, **overrides)


def mention(comment_id: str, product: str, quote: str, stance: str = "recommend", category: str = "kitchen") -> dict:
    return {"comment_id": comment_id, "product": product, "category": category, "stance": stance, "quote": quote}


ZOJI_1 = "My Zojirushi kettle has lasted 6 years and still boils perfectly."
ZOJI_2 = "Had my Zojirushi kettle for 4 years now, no problems at all."
ZOJI_3 = "Our Zojirushi kettle is 8 years old and still going strong."
ZOJI_4 = "I've used the Zojirushi kettle daily for 5 years."
LODGE = "My Lodge cast iron skillet has lasted 20 years."
CHEFMAN_1 = "The Chefman kettle died after 6 months of use."
CHEFMAN_2 = "Two Chefman kettles broke within a year of use, avoid them."
HARIO_1 = "My Hario Skerton has ground beans for my kettle pour-overs for 5 years."
HARIO_2 = "I've used a Hario Skerton for 3 years, still great with a gooseneck kettle."
HARIO_3 = "Hario Skerton for 4 years, heat the kettle while you grind."


def library(tmp_path: Path) -> Path:
    """Two kettle threads: the Zojirushi praised four times across both, a skillet praised, the Chefman warned against."""
    threads = [
        kettle_thread("1kett01", [
            comment("k1aaaa", "1kett01", ZOJI_1),
            comment("k1bbbb", "1kett01", ZOJI_2),
            comment("k1cccc", "1kett01", LODGE),
            comment("k1dddd", "1kett01", CHEFMAN_1),
        ]),
        kettle_thread("1kett02", [
            comment("k2aaaa", "1kett02", ZOJI_3),
            comment("k2bbbb", "1kett02", ZOJI_4),
            comment("k2cccc", "1kett02", CHEFMAN_2),
        ]),
    ]
    # A coffee thread whose comments mention a kettle in passing: not about kettles, so never read for one.
    threads.append(make_thread(
        id="1coff01", community="Coffee", category="kitchen", title="Which hand grinder should I get?",
        body="Budget is about 100.", url="https://www.reddit.com/r/Coffee/comments/1coff01/grinder/",
        comments=[comment("c1aaaa", "1coff01", HARIO_1), comment("c1bbbb", "1coff01", HARIO_2),
                  comment("c1cccc", "1coff01", HARIO_3)],
    ))
    root = write_gold(tmp_path / "library", threads, voices=None, mentions=None)
    extractions = {
        "1kett01": [mention("k1aaaa", "Zojirushi kettle", ZOJI_1), mention("k1bbbb", "Zojirushi kettle", ZOJI_2),
                    mention("k1cccc", "Lodge cast iron skillet", LODGE), mention("k1dddd", "Chefman kettle", CHEFMAN_1, "warn")],
        "1kett02": [mention("k2aaaa", "Zojirushi kettle", ZOJI_3), mention("k2bbbb", "Zojirushi kettle", ZOJI_4),
                    mention("k2cccc", "Chefman kettle", CHEFMAN_2, "warn")],
        "1coff01": [mention("c1aaaa", "Hario Skerton", HARIO_1), mention("c1bbbb", "Hario Skerton", HARIO_2),
                    mention("c1cccc", "Hario Skerton", HARIO_3)],
    }
    (root / "extracted").mkdir()
    for thread_id, mentions in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v5", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions,
        }), encoding="utf-8")
    return root


def test_a_request_comes_back_as_picks_with_verified_quotes(tmp_path):
    result = answer_request(REQUEST, library_dir=library(tmp_path))
    assert result.query.product_type == "electric kettle"
    assert [pick.name for pick in result.answer.picks][:1] == ["Zojirushi kettle"]
    assert sorted(result.threads_used) == ["1kett01", "1kett02"]
    assert unverified_claims(result.answer, result.bodies) == []


def test_products_of_another_type_are_left_out(tmp_path):
    # A skillet praised in a kettle thread is a real product, but not an answer to a kettle request.
    result = answer_request(REQUEST, library_dir=library(tmp_path))
    names = [p.name for p in result.ranking.products]
    assert "Lodge cast iron skillet" not in names
    assert "Lodge cast iron skillet" in result.left_out_as_other_type


def test_a_product_warned_against_twice_is_never_a_pick(tmp_path):
    result = answer_request(REQUEST, library_dir=library(tmp_path))
    assert "Chefman kettle" not in [pick.name for pick in result.answer.picks]


def test_a_request_that_needs_a_question_fetches_nothing(tmp_path):
    result = answer_request("something nice for my mum", library_dir=library(tmp_path))
    assert result.query.status == "clarify" and result.answer is None and result.threads_used == []


def test_the_answer_reads_as_text(tmp_path):
    text = answer_request(REQUEST, library_dir=library(tmp_path)).text()
    assert "Zojirushi kettle" in text and ZOJI_1 in text


def test_only_threads_about_the_product_are_read(tmp_path):
    # Its title or post must name the product: a coffee thread mentioning kettles in passing isn't about kettles.
    result = answer_request(REQUEST, library_dir=library(tmp_path))
    assert "1coff01" not in result.threads_used
    assert "Hario Skerton" not in [p.name for p in result.ranking.products]
