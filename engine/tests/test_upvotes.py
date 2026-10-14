"""Noemi's upvote rule (14 Oct 2026), built switched off for her to see its effect first: "let's be reasonable. if we
have few credible mentions, a highly upvoted comment (10+) counts more".

Today a product becomes a pick with 3 credible recommendations across 2 threads (Noemi's decisions 4-8 of 9 Oct 2026),
and 2 across 2 threads make "Also worth a look" (her decision 2 of 13 Oct 2026). With config.UPVOTE_COUNTS_MORE on, a
credible recommendation whose comment has at least config.UPVOTE_MIN_SCORE upvotes counts as two toward that bar, in one
of four variants (engine/rank.py):
- A: for any product (UPVOTE_ONLY_WHEN_SHORT off);
- B: only for a product short of the bar, and only as far as the bar (UPVOTE_ONLY_WHEN_SHORT on);
- C: as B, and only for a comment in the top of a big thread (UPVOTE_TOP_OF_BIG_THREAD on);
- D: as C, and a product it lifts only fills a place the picks would leave empty (UPVOTE_ONLY_TO_FILL on).
In every variant only a comment that is already a credible recommendation counts more (never a warning), one comment
counts at most twice, a pick still needs credible recommendations from 2 different threads, nothing leaves the answer,
how much an answer reads doesn't change, and the answer says so openly while its numbers stay the writers'.

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

# {variant: (UPVOTE_ONLY_WHEN_SHORT, UPVOTE_TOP_OF_BIG_THREAD, UPVOTE_ONLY_TO_FILL)}
VARIANTS = {"A": (False, False, False), "B": (True, False, False), "C": (True, True, False), "D": (True, True, True)}
BY_SCORE = ("A", "B", "C")  # the variants in which a lifted product takes its place by its score
# The top of a big thread: a comment every variant lets count twice.
TOP = {"thread_comments": 40, "share_beaten": 0.95}


def upvote_rule(monkeypatch, variant: str) -> None:
    """Turns the rule on, in one variant."""
    only_when_short, top_of_big_thread, only_to_fill = VARIANTS[variant]
    monkeypatch.setattr(config, "UPVOTE_COUNTS_MORE", True)
    monkeypatch.setattr(config, "UPVOTE_ONLY_WHEN_SHORT", only_when_short)
    monkeypatch.setattr(config, "UPVOTE_TOP_OF_BIG_THREAD", top_of_big_thread)
    monkeypatch.setattr(config, "UPVOTE_ONLY_TO_FILL", only_to_fill)


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
    assert names(result.picks) == ["Kettle K"] and result.worth_a_look == []  # a pick, so no longer an item
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
    result = rank_products([mention("Kettle K", "t1", upvotes=34, thread_comments=size, share_beaten=beaten),
                            mention("Kettle K", "t2", upvotes=2)], "kitchen")
    assert names(result.picks) == (["Kettle K"] if counts else [])
    assert names(result.worth_a_look) == ([] if counts else ["Kettle K"])


def test_variant_c_never_counts_a_comment_whose_thread_isnt_known(monkeypatch):
    upvote_rule(monkeypatch, "C")
    scored = the_product([mention("Kettle K", "t1", upvotes=34), mention("Kettle K", "t2", upvotes=2)])
    assert not scored.qualifies and scored.counted_twice == ()


THREE_PICKS = ("Kettle A", "Kettle B", "Kettle C")


def outranked() -> list:
    """Three products with 4 credible recommendations each (4.0 points), and the Kettle K with 2 from 2 threads, one of
    them with 34 upvotes at the top of a big thread (2.0 points)."""
    return ([m for name in THREE_PICKS for m in mentions(4, name)]
            + [mention("Kettle K", "t1", upvotes=34, **TOP), mention("Kettle K", "t2", upvotes=2)])


@pytest.mark.parametrize("variant", VARIANTS)
def test_a_lifted_product_outranked_by_three_picks_stays_worth_a_look(monkeypatch, variant):
    # The rule only adds: a product it lifts to the bar that doesn't make the top 3 by its score stays where it was
    # without the rule, under Also worth a look, and says nothing there about counting twice.
    upvote_rule(monkeypatch, variant)
    ranking = rank_products(outranked(), "kitchen")
    assert names(ranking.picks) == list(THREE_PICKS)
    assert product_named(ranking, "Kettle K").qualifies
    assert names(ranking.worth_a_look) == ["Kettle K"]
    answer = write_answer(ranking, bodies_for(*outranked_items(ranking)), "electric kettle")
    (item,) = answer.worth_a_look
    assert item.name == "Kettle K" and item.reason == "Recommended by 2 credible voices, 2 of them after long-term use."
    assert "twice" not in item.voices


def test_a_lifted_product_shown_as_a_pick_is_never_also_worth_a_look(monkeypatch):
    # The Kettle B has no quote that passes the check, so the answer shows the next product that meets the bar instead:
    # the Kettle K, lifted, which is then a pick only.
    upvote_rule(monkeypatch, "B")
    ranking = rank_products(outranked(), "kitchen")
    bodies = {cid: body for cid, body in bodies_for(*outranked_items(ranking)).items()
              if cid not in {m.comment_id for m in product_named(ranking, "Kettle B").mentions}}
    answer = write_answer(ranking, bodies, "electric kettle")
    assert names(answer.picks) == ["Kettle A", "Kettle C", "Kettle K"]
    assert answer.picks[2].reason.startswith("Recommended by 2 credible voices (one counted twice for its 34 upvotes)")
    assert answer.worth_a_look == []


def product_named(ranking, name: str):
    return next(p for p in ranking.products if p.name == name)


def outranked_items(ranking) -> list:
    return [m for p in ranking.products for m in p.mentions]


def lifted_and_weaker() -> list:
    """The Kettle K lifted (2.0 points), the Kettle W meeting the bar on its own with three weaker voices (1.08)."""
    return ([mention("Kettle K", "t1", upvotes=34, **TOP), mention("Kettle K", "t2", upvotes=2)]
            + mentions(3, "Kettle W", voice="medium", evidence="short-term use"))


@pytest.mark.parametrize("variant", BY_SCORE)
def test_a_lifted_product_takes_its_place_by_its_score_like_any_pick(monkeypatch, variant):
    upvote_rule(monkeypatch, variant)
    assert names(rank_products(lifted_and_weaker(), "kitchen").picks) == ["Kettle K", "Kettle W"]


def test_variant_d_puts_a_lifted_product_after_every_product_meeting_the_bar_on_its_own(monkeypatch):
    upvote_rule(monkeypatch, "D")
    assert names(rank_products(lifted_and_weaker(), "kitchen").picks) == ["Kettle W", "Kettle K"]


@pytest.mark.parametrize("variant", VARIANTS)
def test_with_three_products_meeting_the_bar_variant_d_changes_nothing(monkeypatch, variant):
    # Three products meet the bar on their own, each with three weaker voices (1.08 points), and the lifted Kettle K
    # outscores them: it takes the third place by its score in A, B and C, and in D it fills no place, so it stays an item.
    upvote_rule(monkeypatch, variant)
    data = lifted_and_weaker()[:2] + [m for name in THREE_PICKS
                                      for m in mentions(3, name, voice="medium", evidence="short-term use")]
    ranking = rank_products(data, "kitchen")
    if variant == "D":
        assert names(ranking.picks) == list(THREE_PICKS) and names(ranking.worth_a_look) == ["Kettle K"]
    else:
        assert names(ranking.picks) == ["Kettle K", "Kettle A", "Kettle B"] and ranking.worth_a_look == []


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
    ("D", ", or 2 when one of them has 10 or more upvotes and is in the top 10% of a thread of 20 or more comments"),
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
    return write_threads(tmp_path, {"1upv001": first, "1upv002": second})


def write_threads(tmp_path: Path, threads: dict[str, list[tuple]], comments_on_reddit: dict[str, int] | None = None) -> Path:
    """A made-up library of kettle threads, {thread id: [(comment id, text, score, product or None)]}: each text is also
    its product's quote. `comments_on_reddit`: a thread's comment count as Reddit gives it, which module 2 ranks by."""
    saved, extractions = [], {}
    for thread_id, rows in threads.items():
        url = f"https://www.reddit.com/r/BuyItForLife/comments/{thread_id}/kettle/"
        comments = [make_comment(cid + thread_id[-1], thread_id=thread_id, body=body, score=score,
                                 url=f"https://www.reddit.com/r/BuyItForLife/comments/{thread_id}/comment/{cid}{thread_id[-1]}/")
                    for cid, body, score, _ in rows]
        size = {"num_comments": comments_on_reddit[thread_id]} if thread_id in (comments_on_reddit or {}) else {}
        saved.append(make_thread(id=thread_id, community="BuyItForLife", category="kitchen",
                                 title="Which electric kettle lasts?", body="My kettle died again.", url=url,
                                 comments=comments, **size))
        extractions[thread_id] = [{"comment_id": cid + thread_id[-1], "product": product, "category": "kitchen",
                                   "stance": "recommend", "quote": body} for cid, body, _, product in rows if product]
    root = write_gold(tmp_path / "library", saved, voices=None, mentions=None)
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


def wider_library(tmp_path: Path) -> Path:
    """Four kettle threads. The first two (the most commented, so read first) give two picks, the Zojirushi and the Smeg
    (five writers each), and the Fellow Stagg's two writers, one with 34 upvotes at the top of its thread; the other two
    give a third pick, the Bonavita (five writers)."""
    praise = lambda cid, name, years, score=3: (cid, f"My {name} kettle has lasted {years} years and still works "
                                                     "perfectly.", score, f"{name} kettle")
    first = ([praise(f"z{n}", "Zojirushi", 4 + n) for n in range(3)] + [praise(f"m{n}", "Smeg", 4 + n) for n in range(2)]
             + [praise("s1", "Fellow Stagg", 5, 34)])
    first += [(f"f{n:02d}", FILLER, 1, None) for n in range(25 - len(first))]
    second = ([praise(f"z{n}", "Zojirushi", 4 + n) for n in range(3, 5)] + [praise(f"m{n}", "Smeg", 4 + n) for n in range(2, 5)]
              + [praise("s2", "Fellow Stagg", 7)])
    third = [praise(f"b{n}", "Bonavita", 4 + n) for n in range(3)] + [("h1", FILLER, 1, None)]
    fourth = [praise(f"b{n}", "Bonavita", 4 + n) for n in range(3, 5)]
    return write_threads(tmp_path, {"1upv001": first, "1upv002": second, "1upv003": third, "1upv004": fourth},
                         {"1upv001": 500, "1upv002": 500, "1upv003": 30, "1upv004": 30})


@pytest.mark.parametrize("variant", VARIANTS)
def test_the_rule_never_stops_an_answer_reading_more_threads(tmp_path, monkeypatch, variant):
    # Noemi, 7 Oct 2026: an answer short of picks reads more threads before giving up. Ranked with the rule, the first two
    # threads would reach three picks, the Stagg counted twice, and the wider reading would never be read. So the rule
    # never changes how much is read: which reading to keep is decided as without it, and the reading kept is ranked
    # with it. Here the wider reading's three picks all outscore the Stagg, which stays under Also worth a look.
    root = wider_library(tmp_path)
    off = answer_request(REQUEST, library_dir=root, max_threads=2, more_threads=4)
    assert off.read_more and "Bonavita kettle" in shown(off)[0] and shown(off)[1] == ["Fellow Stagg kettle"]
    upvote_rule(monkeypatch, variant)
    on = answer_request(REQUEST, library_dir=root, max_threads=2, more_threads=4)
    assert on.read_more and shown(on) == shown(off)
    assert unverified_claims(on.answer, on.bodies) == []


def test_with_the_rule_on_each_reading_reads_its_threads_once(tmp_path, monkeypatch):
    # The reading kept is ranked again with the rule, from what it has read: its threads aren't read and grouped again
    # (latency: a second reading had doubled a warm answer's time).
    from engine import pipeline

    root = wider_library(tmp_path)
    calls = []
    real = pipeline.group_products
    monkeypatch.setattr(pipeline, "group_products", lambda *args, **kwargs: calls.append(1) or real(*args, **kwargs))
    answer_request(REQUEST, library_dir=root, max_threads=2, more_threads=4)
    off = len(calls)
    upvote_rule(monkeypatch, "D")
    calls.clear()
    answer_request(REQUEST, library_dir=root, max_threads=2, more_threads=4)
    assert len(calls) == off


def test_with_the_rule_on_an_answer_it_changes_nothing_in_is_written_once(tmp_path, monkeypatch):
    # The Zojirushi meets the bar on its own and nothing else can be lifted: ranked with the rule, the reading would give
    # the same answer, so it isn't written again.
    from engine import pipeline
    from engine.tests.test_pipeline import library

    root = library(tmp_path)
    calls = []
    real = pipeline.write_answer
    monkeypatch.setattr(pipeline, "write_answer", lambda *args, **kwargs: calls.append(1) or real(*args, **kwargs))
    off = answer_request(REQUEST, library_dir=root)
    written = len(calls)
    upvote_rule(monkeypatch, "D")
    calls.clear()
    on = answer_request(REQUEST, library_dir=root)
    assert len(calls) == written and shown(on) == shown(off) and on.answer.picks[0].reason == off.answer.picks[0].reason


@pytest.mark.parametrize("variant", VARIANTS)
def test_a_comment_gone_from_reddit_lifts_nothing(tmp_path, monkeypatch, variant):
    # The Stagg's upvoted comment was deleted on Reddit since it was saved: the live check drops it, its vote no longer
    # counts, and with one credible writer left the Stagg can't be lifted.
    from engine.tests.test_pipeline import FakeLive, shown_comment_ids

    upvote_rule(monkeypatch, variant)
    result = answer_request(REQUEST, library_dir=kettle_library(tmp_path), live_checker=FakeLive(gone={"s11"}))
    assert shown(result) == (["Zojirushi kettle"], [])
    assert "s11" not in shown_comment_ids(result.answer) and result.live_dropped == {"gone": 1}
    assert unverified_claims(result.answer, result.bodies) == []


@pytest.mark.parametrize("variant", VARIANTS)
def test_with_live_checks_the_lifted_pick_is_checked_like_every_pick(tmp_path, monkeypatch, variant):
    from engine.answer import _every_quote
    from engine.tests.test_pipeline import FakeLive, shown_comment_ids

    upvote_rule(monkeypatch, variant)
    live = FakeLive()
    result = answer_request(REQUEST, library_dir=kettle_library(tmp_path), live_checker=live)
    assert shown(result) == (["Zojirushi kettle", "Fellow Stagg kettle"], [])
    assert {quote.url for _, quote in _every_quote(result.answer)} <= set(live.asked)
    assert {"s11", "s22"} <= shown_comment_ids(result.answer)


def test_the_reading_kept_is_ranked_with_the_rule(tmp_path, monkeypatch):
    # The first two threads alone (no wider reading to try): the Stagg, counted twice, fills the third place.
    upvote_rule(monkeypatch, "B")
    result = answer_request(REQUEST, library_dir=wider_library(tmp_path), max_threads=2, more_threads=None)
    assert shown(result) == (["Zojirushi kettle", "Smeg kettle", "Fellow Stagg kettle"], [])


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
    assert "never takes the place" not in text_of(html)
    upvote_rule(monkeypatch, "D")
    assert "never takes the place of one that meets this rule on its own" in text_of(get_how(tmp_path, monkeypatch))


def test_the_pages_meter_says_how_many_of_its_writers_counted_twice(tmp_path):
    html = page_text(tmp_path)
    meter = function_body(html, "function trustMeter(voices)")
    assert "voices.twice" in meter and "LABELS.meterTwice" in meter
    assert 'meterTwice: ["{n} counted twice for its upvotes", "{n} counted twice for their upvotes"]' in html
