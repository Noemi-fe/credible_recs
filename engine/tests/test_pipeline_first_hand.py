"""A credible mention needs first-hand use (Noemi's decisions 4-8 of 9 Oct 2026), and both readers must see it.

Found reviewing the answers on 13 Oct 2026: an espresso machine was a pick on three comments that only suggested it
(an opinion phrase with "my", a list of alternatives, a "mine" that was the writer's other machine). Module 5's word rules
read those words as use; the AI, which reads the whole comment (extraction instructions v6), had written "no first-hand
use" for each. The pipeline now gives the AI's reading the last word when it says no use (engine.credibility.
with_ai_evidence), so such a product is no pick. Every comment here is made up.
"""

import json
from pathlib import Path

from engine.pipeline import answer_request
from engine.tests.factories import make_comment, make_thread, write_gold

REQUEST = "electric kettle that lasts 10+ years"

# Each suggests the Acme Glide kettle in words the rules read as use, without saying the writer used it.
SUGGESTIONS = [
    ("k1aaaa", "The Acme Glide kettle is the one to buy, in my book."),
    ("k1bbbb", "For me the Acme Glide kettle is the one to get."),
    ("k2aaaa", "You could also look at the Acme Glide kettle. Mine broke when we moved somewhere with hard water."),
]
# Three writers who use the Brightline kettle, in two threads: a pick whatever the AI says.
OWNERS = [
    ("k1cccc", "My Brightline kettle has boiled water every day for 6 years."),
    ("k2bbbb", "Had my Brightline kettle for 4 years now, no problems."),
    ("k2cccc", "Our Brightline kettle is 8 years old and still going strong."),
]


def library(tmp_path: Path, ai_evidence: str | None) -> Path:
    """Two kettle threads extracted with instructions v6: the Acme Glide suggestions, with the AI's evidence level
    `ai_evidence` (None: an older extraction, with none), and the Brightline owners (long-term use)."""
    rows = [(cid, "Acme Glide kettle", body, ai_evidence) for cid, body in SUGGESTIONS]
    rows += [(cid, "Brightline kettle", body, "long-term use") for cid, body in OWNERS]
    threads, extractions = {}, {}
    for comment_id, product, body, evidence in rows:
        thread_id = "1kett01" if comment_id.startswith("k1") else "1kett02"
        url = f"https://www.reddit.com/r/BuyItForLife/comments/{thread_id}/comment/{comment_id}/"
        threads.setdefault(thread_id, []).append(make_comment(comment_id, thread_id=thread_id, body=body, url=url))
        found = {"comment_id": comment_id, "product": product, "category": "kitchen", "stance": "recommend",
                 "quote": body, "product_type": "electric kettle"}
        if evidence is not None:
            found |= {"evidence": evidence, "evidence_tags": ["long-term use" if evidence == "long-term use" else "vague"]}
        extractions.setdefault(thread_id, []).append(found)
    root = write_gold(tmp_path / "library", [
        make_thread(id=tid, community="BuyItForLife", category="kitchen", title="Which electric kettle lasts?",
                    body="Mine died again.", url=f"https://www.reddit.com/r/BuyItForLife/comments/{tid}/post/",
                    comments=comments)
        for tid, comments in threads.items()
    ], voices=None, mentions=None)
    (root / "extracted").mkdir()
    for thread_id, mentions in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v6", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions,
        }), encoding="utf-8")
    return root


def product(result, name: str):
    return next(p for p in result.ranking.products if p.name == name)


def test_suggestions_the_ai_reads_as_untried_are_no_pick(tmp_path):
    result = answer_request(REQUEST, library_dir=library(tmp_path, "no first-hand use"))
    acme = product(result, "Acme Glide kettle")
    assert {m.evidence for m in acme.mentions} == {"no first-hand use"}
    assert acme.breakdown.credible_recommends == 0 and not acme.qualifies
    assert [pick.name for pick in result.answer.picks] == ["Brightline kettle"]


def test_the_same_words_with_use_in_the_ais_reading_still_count(tmp_path):
    # The AI never adds use, and never takes away use it saw: here it agrees with the rules.
    result = answer_request(REQUEST, library_dir=library(tmp_path, "short-term use"))
    assert product(result, "Acme Glide kettle").qualifies
    assert "Acme Glide kettle" in [pick.name for pick in result.answer.picks]


def test_an_extraction_without_the_ais_level_is_judged_by_the_rules_as_before(tmp_path):
    result = answer_request(REQUEST, library_dir=library(tmp_path, None))
    assert product(result, "Acme Glide kettle").breakdown.credible_recommends == 3
