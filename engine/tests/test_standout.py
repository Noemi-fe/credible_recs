"""A comment that stands out in its thread (Noemi, 14 Oct 2026, after switching on variant D): "if a comment has a lot
of upvotes compared to the size of the thread, i want it as a pick or worth a look".

The breadth-first pass's choice (eval/RUNS.md, 14 Oct 2026): a credible recommendation stands out when its comment has
at least config.STANDOUT_UPVOTES_PER_COMMENT upvotes for each readable comment of its thread, at least
STANDOUT_MIN_SCORE upvotes, in a thread of at least STANDOUT_MIN_THREAD_COMMENTS comments, names at most
STANDOUT_MAX_PRODUCTS products, and talks about what the request asks for when it asks for anything besides the product.
Its product is then shown under Also worth a look even with that one credible voice, and, with a second credible writer
even from the same thread, it can fill a place the picks would leave empty, never one a product meeting the bar holds.
Upvotes never make a comment credible, warnings still count people, the upvote rule (variant D) comes first, how much
an answer reads never changes, and the answer says why such a product is shown. An answer it changes nothing in is the
same as with it off.

Every thread, comment and product here is made up; no test reads data/ or reaches the network.
"""

import json
from pathlib import Path

import pytest

from engine import config
from engine.answer import answer_to_dict, unverified_claims, write_answer
from engine.pipeline import answer_request
from engine.rank import rank_products, stands_out
from engine.tests.factories import make_comment, make_thread, write_gold
from engine.tests.ranking_factories import bodies_for, mention, mentions
from engine.tests.test_how_page import get_how, text_of
from engine.tests.test_upvotes import FILLER, shown, wider_library
from engine.tests.test_upvotes import REQUEST as KETTLE_REQUEST


def standout(product: str = "Pan P", thread: str = "t1", score: int = 74, comments: int = 69, products: int = 1,
             **kwargs):
    """A credible recommendation (a high voice after long-term use) whose comment has `score` upvotes in a thread of
    `comments` readable comments, among the top of it, and names `products` products: by default one that stands out."""
    return mention(product, thread, upvotes=score, thread_comments=comments, share_beaten=0.97,
                   products_named=products, **kwargs)


def names(products) -> list[str]:
    return [p.name for p in products]


def the(result, name: str = "Pan P"):
    return next(p for p in result.products if p.name == name)


# --- Module 6: what stands out ---

def test_the_rule_is_on_as_noemi_asked():
    assert config.STANDOUT_ON is True and config.STANDOUT_FILLS_PICKS is True
    assert (config.STANDOUT_UPVOTES_PER_COMMENT, config.STANDOUT_MIN_SCORE, config.STANDOUT_MIN_THREAD_COMMENTS,
            config.STANDOUT_MAX_PRODUCTS) == (0.75, 25, 20, 5)


def test_a_comment_with_enough_upvotes_for_its_threads_size_stands_out():
    assert stands_out(standout())
    least = config.STANDOUT_UPVOTES_PER_COMMENT
    assert stands_out(standout(score=round(least * 100), comments=100))
    assert not stands_out(standout(score=round(least * 100) - 1, comments=100))
    assert stands_out(standout(score=config.STANDOUT_MIN_SCORE, comments=config.STANDOUT_MIN_THREAD_COMMENTS))


@pytest.mark.parametrize("what, item", [
    ("too few upvotes", lambda: standout(score=config.STANDOUT_MIN_SCORE - 1, comments=20)),
    ("too small a thread", lambda: standout(score=60, comments=config.STANDOUT_MIN_THREAD_COMMENTS - 1)),
    ("too many products named", lambda: standout(products=config.STANDOUT_MAX_PRODUCTS + 1)),
    ("a low voice", lambda: standout(voice="low")),
    ("no first-hand use", lambda: standout(evidence="no first-hand use")),
    ("a warning", lambda: standout(stance="warn")),
    ("not about what was asked", lambda: standout(needs_asked=True)),
    ("its upvotes not known", lambda: mention("Pan P", "t1")),
])
def test_what_never_stands_out(what, item):
    assert not stands_out(item())


def test_talking_about_what_was_asked_or_nothing_asked_is_fine():
    assert stands_out(standout(needs_asked=True, needs=("lasting",)))
    assert stands_out(standout(products=config.STANDOUT_MAX_PRODUCTS))


def test_off_nothing_stands_out(monkeypatch):
    assert not stands_out(standout(), rule=False)  # the pipeline's ranking without the upvote rules
    monkeypatch.setattr(config, "STANDOUT_ON", False)
    assert not stands_out(standout())
    result = rank_products([standout()] + mentions(3, "Pan A"), "kitchen")
    assert result.worth_a_look == [] and the(result).standouts == () and not the(result).by_standout


# --- Module 6: what it earns ---

def test_a_standing_out_comment_alone_puts_its_product_under_also_worth_a_look():
    alone = standout()
    result = rank_products([alone] + mentions(3, "Pan A") + mentions(3, "Pan B"), "kitchen")
    assert names(result.picks) == ["Pan A", "Pan B"] and names(result.worth_a_look) == ["Pan P"]
    product = the(result)
    assert not product.qualifies and product.by_standout and product.standouts == (alone,)


def test_with_a_second_credible_writer_from_the_same_thread_it_fills_an_empty_pick():
    result = rank_products([standout(), mention("Pan P", "t1")] + mentions(3, "Pan A"), "kitchen")
    assert names(result.picks) == ["Pan A", "Pan P"] and result.worth_a_look == []
    assert the(result).qualifies and the(result).by_standout and the(result).counted_twice == ()


def test_with_the_picks_part_off_a_pick_still_needs_two_threads(monkeypatch):
    # Noemi's night rule of 14 Oct 2026 for the upvote rule ("a pick still needs credible recommendations across 2
    # threads"), kept when STANDOUT_FILLS_PICKS is off: the comment standing out earns Also worth a look only.
    monkeypatch.setattr(config, "STANDOUT_FILLS_PICKS", False)
    result = rank_products([standout(), mention("Pan P", "t1")] + mentions(3, "Pan A"), "kitchen")
    assert names(result.picks) == ["Pan A"] and names(result.worth_a_look) == ["Pan P"]
    shown_, _ = answer([standout(), mention("Pan P", "t1")] + mentions(3, "Pan A"))
    assert "stands out" not in shown_.message and shown_.worth_note.startswith("2 credible voices each, or one comment")


def test_it_fills_a_place_only_after_every_product_meeting_the_bar(monkeypatch):
    # Even when the upvote rule takes its places by score (variants A to C): a pick from one thread comes last.
    monkeypatch.setattr(config, "UPVOTE_ONLY_TO_FILL", False)
    strong = [standout(score=900, comments=60, weight=5.0), mention("Pan P", "t1", weight=5.0)]
    result = rank_products(strong + mentions(3, "Pan A") + mentions(3, "Pan B"), "kitchen")
    assert names(result.picks) == ["Pan A", "Pan B", "Pan P"]


def test_it_never_takes_a_pick_place_that_a_product_meeting_the_bar_holds():
    items = [standout(), mention("Pan P", "t1")] + [m for n in "ABC" for m in mentions(3, f"Pan {n}")]
    result = rank_products(items, "kitchen")
    assert names(result.picks) == ["Pan A", "Pan B", "Pan C"]
    assert names(result.worth_a_look) == ["Pan P"]  # it stays where it can be seen


def test_under_also_worth_a_look_too_it_only_fills_a_place_left_empty():
    # Like the upvote rule's lifts among the picks (variant D): it never takes the place of an item with two credible
    # writers across two threads, even outscoring them (here, one high voice after years of use against two medium ones
    # after a week). With a place left, it takes it.
    strong = standout(weight=1.0)
    plain = [m for n in "XYZ" for m in mentions(2, f"Pan {n}", voice="medium", evidence="short-term use")]
    full = rank_products([strong] + plain + mentions(3, "Pan A"), "kitchen")
    assert names(full.worth_a_look) == ["Pan X", "Pan Y", "Pan Z", "Pan P"]  # 3 are shown (WORTH_A_LOOK_SHOWN)
    room = rank_products([strong] + plain[:4] + mentions(3, "Pan A"), "kitchen")
    assert names(room.worth_a_look) == ["Pan X", "Pan Y", "Pan P"]


def test_one_writer_is_never_a_pick_however_many_upvotes():
    result = rank_products([standout(score=900, comments=60)], "kitchen")
    assert result.picks == [] and names(result.worth_a_look) == ["Pan P"]  # a pick shows two quotes: two writers


def test_warnings_still_count_people():
    warned = rank_products([standout(), mention("Pan P", "t2", stance="warn")], "kitchen")
    assert warned.worth_a_look == [] and not the(warned).by_standout  # one credible warning against its one voice
    skipped = rank_products([standout()] + [mention("Pan P", t, stance="warn") for t in ("t2", "t3")], "kitchen")
    assert names(skipped.skip_list) == ["Pan P"] and skipped.worth_a_look == []
    two = rank_products([standout(), mention("Pan P", "t1"), mention("Pan P", "t2", stance="warn")], "kitchen")
    assert names(two.picks) == ["Pan P"] and the(two).disputed is False  # two voices, one warning: shown, warning too


def test_the_upvote_rule_comes_first(monkeypatch):
    # Two credible writers from two threads, one of them standing out: variant D counts that one twice, and the product
    # meets the bar as it did before; the standing out changes nothing. With D off, the standing out lifts it instead.
    items = [standout(), mention("Pan P", "t2")]
    by_d = the(rank_products(items, "kitchen"))
    assert by_d.qualifies and by_d.counted_twice == (items[0],) and not by_d.by_standout
    monkeypatch.setattr(config, "UPVOTE_COUNTS_MORE", False)
    by_standout = the(rank_products(items, "kitchen"))
    assert by_standout.qualifies and by_standout.by_standout and by_standout.counted_twice == ()


def test_a_product_meeting_the_bar_on_its_own_is_left_as_it_is():
    product = the(rank_products([standout()] + mentions(2, "Pan P"), "kitchen"))
    assert product.qualifies and not product.by_standout and product.standouts  # nothing to lift: as before


# --- Module 7: the answer says why ---

def answer(items, product_type: str = "frying pan"):
    bodies = bodies_for(*items)
    return write_answer(rank_products(items, "kitchen"), bodies, product_type), bodies


def test_the_item_says_its_comment_stands_out_and_by_how_much():
    shown_, bodies = answer([standout()] + mentions(3, "Pan A"))
    (item,) = shown_.worth_a_look
    assert item.reason == ("Recommended by 1 credible voice (its comment has 74 upvotes in a 69-comment thread), "
                           "1 of them after long-term use.")
    assert item.voices == {"recommend": 1, "high": 1, "medium": 0, "warn": 0, "threads": 1}
    assert shown_.worth_note == (
        "2 credible voices each, or one comment that stands out in its thread: less evidence than the picks above, "
        "which need at least 3 credible recommendations across at least 2 threads, or 2 when one of them has 10 or "
        "more upvotes and is in the top 10% of a thread of 20 or more comments.")
    assert unverified_claims(shown_, bodies) == []


def test_a_pick_it_fills_says_so_and_the_rule_says_how():
    shown_, bodies = answer([standout(score=1203, comments=1500), mention("Pan P", "t1")] + mentions(3, "Pan A"))
    pick = shown_.picks[1]
    assert pick.reason.startswith("Recommended by 2 credible voices (one comment has 1,203 upvotes in a 1,500-comment "
                                  "thread)")
    assert "twice" not in pick.voices
    assert shown_.message == (
        "Enough credible evidence for only 2 products (at least 3 credible recommendations across at least 2 threads, "
        "or 2 when one of them has 10 or more upvotes and is in the top 10% of a thread of 20 or more comments, or 2, "
        "even from one thread, when one of them stands out in its thread), so we show 2 instead of 3.")
    assert unverified_claims(shown_, bodies) == []


def test_an_answer_it_changes_nothing_in_is_as_with_it_off(monkeypatch):
    # A standing-out comment of a product that meets the bar on its own, and items that don't stand out.
    items = [standout()] + mentions(2, "Pan P") + mentions(2, "Pan W") + [mention("Pan Q", "t1", upvotes=20,
                                                                                  thread_comments=200)]
    on = answer_to_dict(answer(items)[0])
    monkeypatch.setattr(config, "STANDOUT_ON", False)
    assert answer_to_dict(answer(items)[0]) == on


def test_off_the_answer_is_as_before(monkeypatch):
    monkeypatch.setattr(config, "STANDOUT_ON", False)
    shown_ = answer_to_dict(answer([standout()] + mentions(3, "Pan A") + mentions(2, "Pan W"))[0])
    assert [w["name"] for w in shown_["worth_a_look"]] == ["Pan W"]
    assert shown_["worth_note"].startswith("2 credible voices each: less evidence")


def test_the_how_page_explains_it_only_when_it_is_on(tmp_path, monkeypatch):
    html = get_how(tmp_path, monkeypatch)
    words = text_of(html)
    assert "stands out in its thread" in words and "Also worth a look" in words
    for setting in ("STANDOUT_MIN_SCORE", "STANDOUT_UPVOTES_PER_COMMENT", "STANDOUT_MIN_THREAD_COMMENTS",
                    "STANDOUT_MAX_PRODUCTS"):
        assert f'data-config="{setting}"' in html
    assert "75% as many upvotes as its thread has comments" in words
    picks = "even from the same thread, a place the picks would otherwise leave empty"
    assert picks in words
    monkeypatch.setattr(config, "STANDOUT_FILLS_PICKS", False)
    words = text_of(get_how(tmp_path, monkeypatch))
    assert "stands out in its thread" in words and picks not in words
    monkeypatch.setattr(config, "STANDOUT_ON", False)
    assert "stands out in its thread" not in text_of(get_how(tmp_path, monkeypatch))


# --- Through the pipeline: a made-up library ---

KETTLE = "My {name} kettle has lasted {years} years and still works perfectly."
BODUM = KETTLE.format(name="Bodum", years=5)


def kettle_library(tmp_path: Path, score: int = 40, others_named: int = 0, bodum: str = BODUM) -> Path:
    """Two kettle threads. The Zojirushi is praised by three writers across both (a pick); the Bodum by one writer only,
    whose comment says `bodum`, has `score` upvotes in a 25-comment thread (the others a point or two) and warns
    against `others_named` other kettles too."""
    zoji = lambda cid, years, points: (cid, KETTLE.format(name="Zojirushi", years=years), points,
                                       [("Zojirushi kettle", None, "recommend")])
    others = [(f"Kettle {n}", f"The Kettle {n} broke within a year.", "warn") for n in range(others_named)]
    first = [zoji("z1", 4, 3), zoji("z2", 6, 2),
             ("b1", " ".join([bodum] + [quote for _, quote, _ in others]), score, [("Bodum kettle", bodum, "recommend")]
              + others)]
    first += [(f"f{n:02d}", FILLER, 1 + n % 2, []) for n in range(25 - len(first))]
    second = [zoji("z3", 8, 2), ("g1", FILLER, 1, [])]
    return _library(tmp_path, {"1sto001": first, "1sto002": second})


def _library(tmp_path: Path, threads: dict[str, list[tuple]]) -> Path:
    """A made-up library of kettle threads, {thread id: [(comment id, text, score, [(product, quote or None for the
    whole text, stance)])]}, as engine.tests.test_upvotes.write_threads writes one, with any number of products to a
    comment."""
    saved, extractions = [], {}
    for thread_id, rows in threads.items():
        base = f"https://www.reddit.com/r/BuyItForLife/comments/{thread_id}"
        comments = [make_comment(cid + thread_id[-1], thread_id=thread_id, body=body, score=score,
                                 url=f"{base}/comment/{cid}{thread_id[-1]}/")
                    for cid, body, score, _ in rows]
        saved.append(make_thread(id=thread_id, community="BuyItForLife", category="kitchen",
                                 title="Which electric kettle lasts?", body="My kettle died again.",
                                 url=f"{base}/kettle/", comments=comments))
        extractions[thread_id] = [{"comment_id": cid + thread_id[-1], "product": product, "category": "kitchen",
                                   "stance": stance, "quote": quote or body}
                                  for cid, body, _, products in rows for product, quote, stance in products]
    root = write_gold(tmp_path / "library", saved, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for thread_id, found in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v5", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": found,
        }), encoding="utf-8")
    return root


def test_through_the_pipeline_its_one_standing_out_comment_shows_the_bodum(tmp_path):
    result = answer_request(KETTLE_REQUEST, library_dir=kettle_library(tmp_path))
    assert shown(result) == (["Zojirushi kettle"], ["Bodum kettle"])
    assert result.answer.worth_a_look[0].reason.startswith(
        "Recommended by 1 credible voice (its comment has 40 upvotes in a 25-comment thread)")
    assert unverified_claims(result.answer, result.bodies) == []


def test_through_the_pipeline_off_or_too_few_upvotes_it_isnt_shown(tmp_path, monkeypatch):
    assert shown(answer_request(KETTLE_REQUEST, library_dir=kettle_library(tmp_path / "few", score=15)))[1] == []
    monkeypatch.setattr(config, "STANDOUT_ON", False)
    assert shown(answer_request(KETTLE_REQUEST, library_dir=kettle_library(tmp_path / "off")))[1] == []


def test_through_the_pipeline_a_comment_naming_many_products_lifts_none(tmp_path):
    most = config.STANDOUT_MAX_PRODUCTS
    named_most = kettle_library(tmp_path / "most", others_named=most - 1)
    assert shown(answer_request(KETTLE_REQUEST, library_dir=named_most))[1] == ["Bodum kettle"]
    named_more = kettle_library(tmp_path / "more", others_named=most)
    assert shown(answer_request(KETTLE_REQUEST, library_dir=named_more))[1] == []


def test_through_the_pipeline_it_must_talk_about_what_was_asked(tmp_path):
    root = kettle_library(tmp_path, bodum="I bought a Bodum kettle last month and it boils water really fast.")
    assert shown(answer_request(KETTLE_REQUEST, library_dir=root))[1] == []  # nothing about lasting
    assert shown(answer_request("electric kettle", library_dir=root))[1] == ["Bodum kettle"]  # nothing else asked


def test_the_rule_never_stops_an_answer_reading_more_threads(tmp_path, monkeypatch):
    # The first two kettle threads give two picks, and the Fellow Stagg's two writers, one of them standing out at the
    # top of a 25-comment thread: ranked with the rule, those threads would reach three picks and the wider reading,
    # whose picks talk about what was asked, would never be read. So which reading to keep is decided without it.
    monkeypatch.setattr(config, "UPVOTE_COUNTS_MORE", False)  # the standing out alone
    root = wider_library(tmp_path)
    on = answer_request(KETTLE_REQUEST, library_dir=root, max_threads=2, more_threads=4)
    assert on.read_more and "Bonavita kettle" in shown(on)[0] and shown(on)[1] == ["Fellow Stagg kettle"]
    first_only = answer_request(KETTLE_REQUEST, library_dir=root, max_threads=2, more_threads=None)
    assert shown(first_only) == (["Zojirushi kettle", "Smeg kettle", "Fellow Stagg kettle"], [])
    assert first_only.answer.picks[2].reason.startswith(
        "Recommended by 2 credible voices (one comment has 34 upvotes in a 25-comment thread)")
    assert unverified_claims(on.answer, on.bodies) == []
    assert unverified_claims(first_only.answer, first_only.bodies) == []
