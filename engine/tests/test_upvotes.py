"""Noemi's upvote rule (14 Oct 2026), built switched off for her to see its effect first: "let's be reasonable. if we
have few credible mentions, a highly upvoted comment (10+) counts more".

Today a product becomes a pick with 3 credible recommendations across 2 threads (Noemi's decisions 4-8 of 9 Oct 2026),
and 2 across 2 threads make "Also worth a look" (her decision 2 of 13 Oct 2026). With config.UPVOTE_COUNTS_MORE on, a
credible recommendation whose comment has at least config.UPVOTE_MIN_SCORE upvotes counts as two toward that bar, in one
of three variants (engine/rank.py):
- A: for any product (UPVOTE_ONLY_WHEN_SHORT off);
- B: only for a product short of the bar, and only as far as the bar (UPVOTE_ONLY_WHEN_SHORT on);
- C: as B, and only for a comment in the top of a big thread (UPVOTE_TOP_OF_BIG_THREAD on).
In every variant only a comment that is already a credible recommendation counts more (never a warning), one comment
counts at most twice, a pick still needs credible recommendations from 2 different threads, and the answer says so
openly while its numbers stay the writers'.

Every thread, comment and product here is made up; no test reads data/ or reaches the network.
"""

import json
from pathlib import Path

import pytest

from engine import config
from engine import answer as wording
from engine.answer import unverified_claims, write_answer
from engine.credibility import thread_upvotes
from engine.models import Thread
from engine.pipeline import answer_request
from engine.rank import rank_products
from engine.tests.factories import make_comment, make_thread, write_gold
from engine.tests.ranking_factories import bodies_for, mention, mentions
from engine.tests.test_how_page import get_how, text_of
from engine.tests.test_web_public import function_body, page_text

# {variant: (UPVOTE_ONLY_WHEN_SHORT, UPVOTE_TOP_OF_BIG_THREAD)}
VARIANTS = {"A": (False, False), "B": (True, False), "C": (True, True)}
# The top of a big thread: a comment every variant lets count twice.
TOP = {"thread_comments": 40, "share_beaten": 0.95}


def upvote_rule(monkeypatch, variant: str) -> None:
    """Turns the rule on, in one variant."""
    only_when_short, top_of_big_thread = VARIANTS[variant]
    monkeypatch.setattr(config, "UPVOTE_COUNTS_MORE", True)
    monkeypatch.setattr(config, "UPVOTE_ONLY_WHEN_SHORT", only_when_short)
    monkeypatch.setattr(config, "UPVOTE_TOP_OF_BIG_THREAD", top_of_big_thread)


def names(products) -> list[str]:
    return [product.name for product in products]


def the_product(data, name: str = "Kettle K"):
    return next(p for p in rank_products(data, "kitchen").products if p.name == name)


# --- Module 5: a comment's upvotes beside its thread's ---

def thread_of(scores, deleted: tuple[int, ...] = ()) -> Thread:
    comments = [make_comment(f"c{n:02d}", score=score, body=f"Made-up comment number {n}.")
                for n, score in enumerate(scores)]
    comments += [make_comment(f"d{n:02d}", score=score, status="deleted", body="[deleted]", author=None)
                 for n, score in enumerate(deleted)]
    return Thread.model_validate(make_thread(comments=comments))


def test_each_comments_upvotes_are_read_beside_its_threads():
    found = thread_upvotes(thread_of(range(20)))
    top = found["c19"]
    assert (top.score, top.thread_comments, top.share_beaten) == (19, 20, 1.0)
    assert found["c00"].share_beaten == 0.0
    assert found["c10"].share_beaten == pytest.approx(10 / 19)


def test_a_tie_beats_no_one_and_a_deleted_comment_isnt_counted():
    found = thread_upvotes(thread_of([5, 5, 1], deleted=(500,)))
    assert set(found) == {"c00", "c01", "c02"}  # a deleted comment can't count, nor be counted against
    assert found["c00"].thread_comments == 3
    assert found["c00"].share_beaten == 0.5  # it beats the 1, not the other 5


def test_a_lone_comment_beats_no_one():
    lone = thread_upvotes(thread_of([40]))["c00"]
    assert (lone.thread_comments, lone.share_beaten) == (1, 0.0)


# --- Module 6: when a credible recommendation counts twice ---

def test_off_by_default_upvotes_change_nothing():
    assert config.UPVOTE_COUNTS_MORE is False
    scored = the_product([mention("Kettle K", "t1", upvotes=500, **TOP), mention("Kettle K", "t2", upvotes=2)])
    assert not scored.qualifies and scored.worth_a_look
    assert scored.counted_twice == () and scored.breakdown.counted_twice == 0


@pytest.mark.parametrize("variant", VARIANTS)
def test_a_credible_recommendation_with_enough_upvotes_counts_as_two(monkeypatch, variant):
    upvote_rule(monkeypatch, variant)
    data = [mention("Kettle K", "t1", upvotes=config.UPVOTE_MIN_SCORE, **TOP), mention("Kettle K", "t2", upvotes=2)]
    result = rank_products(data, "kitchen")
    scored = result.products[0]
    assert names(result.picks) == ["Kettle K"] and not scored.worth_a_look
    assert scored.breakdown.credible_recommends == 2  # still two writers
    assert scored.breakdown.counted_twice == 1
    assert [m.upvotes for m in scored.counted_twice] == [config.UPVOTE_MIN_SCORE]


@pytest.mark.parametrize("variant", VARIANTS)
def test_fewer_upvotes_count_once(monkeypatch, variant):
    upvote_rule(monkeypatch, variant)
    scored = the_product([mention("Kettle K", "t1", upvotes=config.UPVOTE_MIN_SCORE - 1, **TOP),
                          mention("Kettle K", "t2", upvotes=2)])
    assert not scored.qualifies and scored.worth_a_look and scored.counted_twice == ()


@pytest.mark.parametrize("variant", VARIANTS)
def test_the_extra_count_never_replaces_the_second_thread(monkeypatch, variant):
    upvote_rule(monkeypatch, variant)
    scored = the_product([mention("Kettle K", "t1", upvotes=300, **TOP), mention("Kettle K", "t1", upvotes=200, **TOP)])
    assert not scored.qualifies and not scored.worth_a_look
    assert "credible recommendations in 1 of 2 threads" in scored.shortfall


@pytest.mark.parametrize("variant", VARIANTS)
def test_one_comment_counts_at_most_twice(monkeypatch, variant):
    upvote_rule(monkeypatch, variant)
    scored = the_product([mention("Kettle K", "t1", upvotes=5000, **TOP)])
    assert scored.breakdown.credible_recommends == 1 and scored.breakdown.counted_twice == 1
    assert not scored.qualifies and not scored.worth_a_look  # two at most, and from one thread


@pytest.mark.parametrize("variant", VARIANTS)
def test_upvotes_never_make_a_comment_credible(monkeypatch, variant):
    upvote_rule(monkeypatch, variant)
    scored = the_product([
        mention("Kettle K", "t1", upvotes=900, voice="low", **TOP),
        mention("Kettle K", "t1", upvotes=900, evidence="no first-hand use", **TOP),
        mention("Kettle K", "t1", upvotes=900, stance="neutral", **TOP),
        mention("Kettle K", "t1", upvotes=3), mention("Kettle K", "t2", upvotes=3),
    ])
    assert scored.counted_twice == () and not scored.qualifies and scored.worth_a_look


@pytest.mark.parametrize("variant", VARIANTS)
def test_warnings_never_count_twice(monkeypatch, variant):
    upvote_rule(monkeypatch, variant)
    # One credible warning with many upvotes is one warning: not enough for Skip these, nor for the mixed-opinions flag.
    praised = the_product([mention("Kettle K", "t1", stance="warn", upvotes=800, **TOP)] + mentions(3, "Kettle K"))
    assert praised.breakdown.credible_warnings == 1 and not praised.on_skip_list and not praised.disputed
    # Skip these compares writers: 3 credible warnings against 2 credible recommendations, one of them well upvoted.
    warned = [mention("Pan P", thread, stance="warn") for thread in ("t1", "t2", "t3")]
    result = rank_products(warned + [mention("Pan P", "t1", upvotes=800, **TOP), mention("Pan P", "t2")], "kitchen")
    assert names(result.skip_list) == ["Pan P"]


def test_variant_a_counts_every_well_upvoted_recommendation_of_any_product(monkeypatch):
    upvote_rule(monkeypatch, "A")
    scored = the_product([mention("Kettle K", "t1", upvotes=34), mention("Kettle K", "t2", upvotes=120),
                          mention("Kettle K", "t1", upvotes=3)])
    assert scored.qualifies  # it qualified without them
    assert [m.upvotes for m in scored.counted_twice] == [120, 34]  # the most upvoted first


@pytest.mark.parametrize("variant", ["B", "C"])
def test_b_and_c_never_inflate_a_product_that_already_qualifies(monkeypatch, variant):
    upvote_rule(monkeypatch, variant)
    scored = the_product([mention("Kettle K", "t1", upvotes=34, **TOP), mention("Kettle K", "t2", upvotes=120, **TOP),
                          mention("Kettle K", "t1", upvotes=3)])
    assert scored.qualifies and scored.counted_twice == () and scored.breakdown.counted_twice == 0


@pytest.mark.parametrize("variant", ["B", "C"])
def test_b_and_c_lift_a_product_only_as_far_as_the_bar(monkeypatch, variant):
    upvote_rule(monkeypatch, variant)
    scored = the_product([mention("Kettle K", "t1", upvotes=34, **TOP), mention("Kettle K", "t2", upvotes=120, **TOP)])
    assert scored.qualifies
    assert [m.upvotes for m in scored.counted_twice] == [120]  # one was enough: the most upvoted


@pytest.mark.parametrize("more_comments, more_beaten, counts", [
    (-1, 0.05, False),  # a thread a comment short of big enough, even for its top comment
    (0, -0.05, False),  # big enough, but the comment isn't in its top share
    (0, 0.0, True),  # both just met
    (360, 0.09, True),
])
def test_variant_c_needs_the_top_of_a_big_thread(monkeypatch, more_comments, more_beaten, counts):
    upvote_rule(monkeypatch, "C")
    size = config.UPVOTE_THREAD_MIN_COMMENTS + more_comments
    beaten = config.UPVOTE_THREAD_SHARE_BEATEN + more_beaten
    scored = the_product([mention("Kettle K", "t1", upvotes=34, thread_comments=size, share_beaten=beaten),
                          mention("Kettle K", "t2", upvotes=2)])
    assert scored.qualifies is counts and scored.worth_a_look is not counts


def test_variant_c_never_counts_a_comment_whose_thread_isnt_known(monkeypatch):
    upvote_rule(monkeypatch, "C")
    scored = the_product([mention("Kettle K", "t1", upvotes=34), mention("Kettle K", "t2", upvotes=2)])
    assert not scored.qualifies and scored.counted_twice == ()


@pytest.mark.parametrize("variant", VARIANTS)
def test_a_lifted_product_takes_its_place_by_its_score_like_any_pick(monkeypatch, variant):
    upvote_rule(monkeypatch, variant)
    data = ([mention("Kettle K", "t1", upvotes=34, **TOP), mention("Kettle K", "t2", upvotes=2)]
            + mentions(3, "Kettle W", voice="medium", evidence="short-term use"))
    assert names(rank_products(data, "kitchen").picks) == ["Kettle K", "Kettle W"]  # 2.0 points against 1.08


# --- Module 7: the answer says so, and its numbers stay the writers' ---

def answer_for(items, product_type: str = "electric kettle"):
    return write_answer(rank_products(items, "kitchen"), bodies_for(*items), product_type), bodies_for(*items)


def test_the_reason_says_which_voice_counted_twice_and_for_how_many_upvotes(monkeypatch):
    upvote_rule(monkeypatch, "B")
    answer, bodies = answer_for([mention("Kettle K", "t1", upvotes=34, **TOP), mention("Kettle K", "t2", upvotes=2)])
    (pick,) = answer.picks
    assert pick.reason == ("Recommended by 2 credible voices (one counted twice for its 34 upvotes), 2 of them after "
                           "long-term use.")
    assert pick.support == "Backed by 2 high-credibility voices, across 2 threads."
    assert pick.voices == {"recommend": 2, "high": 2, "medium": 0, "warn": 0, "threads": 2, "twice": 1}
    assert pick.breakdown.credible_recommends == 2 and pick.breakdown.counted_twice == 1
    assert unverified_claims(answer, bodies) == []


def test_two_counted_twice_are_both_named(monkeypatch):
    upvote_rule(monkeypatch, "A")
    answer, _ = answer_for([mention("Kettle K", "t1", upvotes=1203), mention("Kettle K", "t2", upvotes=34),
                            mention("Kettle K", "t1", upvotes=2)])
    pick = answer.picks[0]
    assert pick.reason.startswith("Recommended by 3 credible voices (two counted twice for their upvotes: 1,203 and 34),")
    assert pick.voices["recommend"] == 3 and pick.voices["twice"] == 2


def test_with_the_rule_off_the_words_and_numbers_are_as_before():
    answer, _ = answer_for([mention("Kettle K", "t1", upvotes=900, **TOP)] + mentions(2, "Kettle K", upvotes=500))
    pick = answer.picks[0]
    assert pick.reason == "Recommended by 3 credible voices, 3 of them after long-term use."
    assert "twice" not in pick.voices and pick.breakdown.counted_twice == 0


@pytest.mark.parametrize("variant, more", [
    ("A", ", or 2 when one of them has 10 or more upvotes"),
    ("B", ", or 2 when one of them has 10 or more upvotes"),
    ("C", ", or 2 when one of them has 10 or more upvotes and is in the top 10% of a thread of 20 or more comments"),
])
def test_the_answers_messages_give_the_rule_with_its_upvotes(monkeypatch, variant, more):
    upvote_rule(monkeypatch, variant)
    rule = "at least 3 credible recommendations across at least 2 threads" + more
    nothing, _ = answer_for(mentions(1, "Kettle K"))
    assert nothing.message == wording.NO_PICKS.format(what="any electric kettle", rule=rule)
    some, _ = answer_for(mentions(3, "Kettle K") + mentions(2, "Kettle W", upvotes=2))
    assert some.message == wording.FEWER_PICKS.format(products="1 product", rule=rule, n=1, wanted=3)
    assert some.worth_note == wording.WORTH_NOTE.format(voices="2 credible voices", rule=rule)


def test_with_the_rule_off_the_messages_are_as_before():
    nothing, _ = answer_for(mentions(1, "Kettle K"))
    assert nothing.message == wording.NO_PICKS.format(
        what="any electric kettle", rule="at least 3 credible recommendations across at least 2 threads")


# --- Through the pipeline: a made-up library ---

REQUEST = "electric kettle that lasts 10+ years"
ZOJI = "My Zojirushi kettle has lasted {years} years and still works perfectly."
STAGG = "My Fellow Stagg kettle has lasted {years} years and still works perfectly."
FILLER = "Thanks, that is a useful thing to know before buying."


def kettle_library(tmp_path: Path, big_thread: bool = True) -> Path:
    """Two kettle threads. The Zojirushi is praised three times across them (a pick), the Fellow Stagg twice, once in each
    (Also worth a look); the Stagg's first praise is its thread's top comment, with 34 upvotes. `big_thread`: that thread
    has 25 comments (else 12), the others made-up replies with a point or two."""
    first = [("z1", ZOJI.format(years=6), 3, "Zojirushi kettle"), ("z2", ZOJI.format(years=4), 4, "Zojirushi kettle"),
             ("s1", STAGG.format(years=5), 34, "Fellow Stagg kettle")]
    first += [(f"f{n:02d}", FILLER, 1 + n % 2, None) for n in range((25 if big_thread else 12) - len(first))]
    second = [("z3", ZOJI.format(years=8), 2, "Zojirushi kettle"), ("s2", STAGG.format(years=7), 3, "Fellow Stagg kettle"),
              ("g1", FILLER, 1, None)]
    threads, extractions = [], {}
    for thread_id, rows in (("1upv001", first), ("1upv002", second)):
        url = f"https://www.reddit.com/r/BuyItForLife/comments/{thread_id}/kettle/"
        comments = [make_comment(cid + thread_id[-1], thread_id=thread_id, body=body, score=score,
                                 url=f"https://www.reddit.com/r/BuyItForLife/comments/{thread_id}/comment/{cid}{thread_id[-1]}/")
                    for cid, body, score, _ in rows]
        threads.append(make_thread(id=thread_id, community="BuyItForLife", category="kitchen",
                                   title="Which electric kettle lasts?", body="My kettle died again.", url=url,
                                   comments=comments))
        extractions[thread_id] = [{"comment_id": cid + thread_id[-1], "product": product, "category": "kitchen",
                                   "stance": "recommend", "quote": body} for cid, body, _, product in rows if product]
    root = write_gold(tmp_path / "library", threads, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for thread_id, mentions_ in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v5", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions_,
        }), encoding="utf-8")
    return root


def shown(result) -> tuple[list[str], list[str]]:
    return [pick.name for pick in result.answer.picks], [item.name for item in result.answer.worth_a_look]


def test_through_the_pipeline_off_the_stagg_is_only_worth_a_look(tmp_path):
    result = answer_request(REQUEST, library_dir=kettle_library(tmp_path))
    assert shown(result) == (["Zojirushi kettle"], ["Fellow Stagg kettle"])


@pytest.mark.parametrize("variant", VARIANTS)
def test_through_the_pipeline_its_upvoted_praise_makes_the_stagg_a_pick(tmp_path, monkeypatch, variant):
    upvote_rule(monkeypatch, variant)
    result = answer_request(REQUEST, library_dir=kettle_library(tmp_path))
    assert shown(result) == (["Zojirushi kettle", "Fellow Stagg kettle"], [])
    stagg = result.answer.picks[1]
    assert stagg.reason.startswith("Recommended by 2 credible voices (one counted twice for its 34 upvotes)")
    assert stagg.voices["recommend"] == 2 and stagg.voices["twice"] == 1
    assert unverified_claims(result.answer, result.bodies) == []


def test_through_the_pipeline_variant_c_leaves_a_small_threads_top_comment_as_it_was(tmp_path, monkeypatch):
    upvote_rule(monkeypatch, "C")
    result = answer_request(REQUEST, library_dir=kettle_library(tmp_path, big_thread=False))
    assert shown(result) == (["Zojirushi kettle"], ["Fellow Stagg kettle"])
    upvote_rule(monkeypatch, "B")
    result = answer_request(REQUEST, library_dir=kettle_library(tmp_path / "again", big_thread=False))
    assert shown(result) == (["Zojirushi kettle", "Fellow Stagg kettle"], [])


# --- The how-we-score page and the search page ---

def test_the_how_page_explains_the_rule_only_when_it_is_on(tmp_path, monkeypatch):
    assert "counts as two" not in text_of(get_how(tmp_path, monkeypatch))
    upvote_rule(monkeypatch, "B")
    html = get_how(tmp_path, monkeypatch)
    words = text_of(html)
    assert "counts as two" in words and "never more" in words
    assert 'data-config="UPVOTE_MIN_SCORE"' in html and 'data-config="UPVOTE_THREAD_MIN_COMMENTS"' not in html
    upvote_rule(monkeypatch, "C")
    html = get_how(tmp_path, monkeypatch)
    assert 'data-config="UPVOTE_THREAD_MIN_COMMENTS"' in html and 'data-config="UPVOTE_THREAD_SHARE_BEATEN"' in html


def test_the_pages_meter_says_how_many_of_its_writers_counted_twice(tmp_path):
    html = page_text(tmp_path)
    meter = function_body(html, "function trustMeter(voices)")
    assert "voices.twice" in meter and "LABELS.meterTwice" in meter
    assert 'meterTwice: ["{n} counted twice for its upvotes", "{n} counted twice for their upvotes"]' in html
