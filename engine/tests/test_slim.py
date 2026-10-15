"""Keep only the comments answers use (Noemi, 13 Oct 2026: "Keep only comments we use"; engine/slim.py).

A slimmed thread keeps its title and the comments its extraction points to, whole; every other comment keeps its id,
what it replies to, its date, score and link, but not its words or its writer. What the scoring reads from the whole
thread is worked out first and kept with it, so every answer reads the slimmed thread as it read the whole one.

Every thread, writer and comment here is made up: no test reads data/ or reaches the network.
"""

import json
from datetime import UTC, datetime

import pytest

from engine import profiles, slim
from engine.credibility import copied_comment_ids, repeated_copies, score_voice
from engine.extract import Extraction, check_extraction, shown_comment_ids
from engine.models import Comment, Thread, quote_fingerprint
from engine.pipeline import _about_the_product, answer_request
from engine.slim import SlimError, kept_comment_ids, known_types, slim_library, slim_thread
from engine.sources import relevance, talking
from engine.tests.factories import make_comment, make_thread, write_gold

NOW = datetime(2026, 10, 13, 18, 0, tzinfo=UTC)
TID = "1slim01"

ZOJI = "My Zojirushi kettle has lasted 6 years and still boils perfectly."
AGREE = "Same here, mine is 5 years old and still fine."
SOURCE = "I bought the Fellow Stagg EKG last spring."
REPLY = "Had that one for 3 years now, still great."
# 27 words: a run of 20 (config.COPIED_TEXT_MIN_WORDS) under two writers' names is "copied text".
COPY = ("Honestly the best kettle money can buy is the Dualit Classic because mine has lasted twelve years without a "
        "single problem and it still looks new today")
CHEFMAN = "The Chefman kettle broke within a year of daily use, avoid it."
NOTE = "Get a gooseneck kettle if you make pour-over."
CARE = "Descale your kettle every 3 months with citric acid."
SMEG = "I think the Smeg one looks nice."


def c(comment_id: str, writer: str | None, body: str, score: int, **overrides) -> dict:
    author = None if writer is None else {"name": writer, "account_created_at": "2018-06-01", "karma": 5000,
                                          "flair": None}
    url = f"https://www.reddit.com/r/BuyItForLife/comments/{TID}/comment/{comment_id}/"
    return make_comment(comment_id, thread_id=TID, author=author, body=body, score=score, url=url, **overrides)


def whole_thread_dict(**overrides) -> dict:
    """A kettle thread whose title names nothing and whose post names an electric kettle, with comments of every kind:
    kept for a mention, an agreement, a note, a care tip, a rejected mention; a reply taking its product from the
    comment above; a copy of a dropped comment's words; a writer whose first comment is dropped; a quoted block whose
    words a dropped comment wrote; scores that make the first comment well upvoted only counting the dropped ones."""
    comments = [
        c("s8first", "alice_t", "Following, I need one too.", 1, created_at="2025-03-01T12:00:00Z"),
        c("s1kept", "alice_t", ZOJI, 8),
        c("s2agree", "bob_t", AGREE, 9, parent_id="s1kept"),
        c("s3drop", "carol_t", "Does a stovetop kettle work on induction? Asking for my mum.", 1),
        c("s4source", "dave_t", SOURCE, 12),
        c("s5reply", "erin_t", REPLY, 6, parent_id="s4source"),
        c("s6copied", "frank_t", COPY, 2, created_at="2025-03-02T08:00:00Z"),
        c("s7copy", "gina_t", COPY, 2, created_at="2025-03-02T11:00:00Z"),
        c("s9gone", None, "[deleted]", 1, status="deleted"),
        c("s10quoted", "hank_t", "&gt; " + CHEFMAN, 4),
        c("s11drop", "ivan_t", CHEFMAN, 3),
        c("s12note", "jack_t", NOTE, 15),
        c("s13care", "kim_t", CARE, 10),
        c("s14drop", "leo_t", "This thread made me buy a Bonavita gooseneck.", 1),
        c("s16rej", "rita_t", SMEG, 2),
    ] + [c(f"s{n}extra", f"quiet{n}_t", "Thanks for asking this.", 0) for n in range(20, 24)] + [
        c("s24extra", "quiet24_t", "Try a BHA once a week, it helps.", 0)]
    fields = dict(id=TID, community="BuyItForLife", category="kitchen", title="Which one would you buy again?",
                  body="My electric kettle died again after two years.", score=80, num_comments=len(comments),
                  url=f"https://www.reddit.com/r/BuyItForLife/comments/{TID}/which_one/", collected_at="2026-10-06",
                  comments=comments)
    return make_thread(**{**fields, **overrides})


def extraction_dict() -> dict:
    mention = lambda cid, product, quote, stance="recommend", **more: {
        "comment_id": cid, "product": product, "category": "kitchen", "stance": stance, "quote": quote,
        "product_type": "electric kettle", **more}
    return {
        "thread_id": TID, "instructions_version": "extract-v9", "extracted_at": "2026-10-12T10:00:00Z",
        "extractor": "claude-code",
        "mentions": [
            mention("s1kept", "Zojirushi kettle", ZOJI, evidence="long-term use", evidence_tags=["long-term use"]),
            mention("s5reply", "Fellow Stagg EKG", REPLY, refers_to="parent"),
            mention("s7copy", "Dualit Classic kettle", "the best kettle money can buy is the Dualit Classic"),
            mention("s10quoted", "Chefman kettle", CHEFMAN, "warn"),  # someone else's words: rejected
            mention("s16rej", "Smeg kettle", "the Smeg kettle looks nice"),  # not word for word: rejected
        ],
        "notes": [{"comment_id": "s12note", "about": "gooseneck kettle", "stance": "recommend", "quote": NOTE}],
        "agreements": [{"comment_id": "s2agree", "quote": AGREE}],
        "care": [{"comment_id": "s13care", "about": "electric kettle", "is_kind": True, "tip": "descale every 3 months",
                  "quote": CARE}],
    }


KEPT = {"s1kept", "s2agree", "s4source", "s5reply", "s7copy", "s10quoted", "s12note", "s13care", "s16rej"}


@pytest.fixture
def whole() -> Thread:
    return Thread.model_validate(whole_thread_dict())


@pytest.fixture
def extraction() -> Extraction:
    return Extraction.model_validate(extraction_dict())


@pytest.fixture
def types(tmp_path) -> tuple[str, ...]:
    return known_types(tmp_path)


@pytest.fixture
def slimmed(whole, extraction, types) -> Thread:
    return slim_thread(whole, extraction, types, NOW)


def by_id(thread: Thread) -> dict[str, Comment]:
    return {comment.id: comment for comment in thread.comments}


# --- What is kept, and what goes ---

def test_the_comments_the_extraction_points_to_are_kept_with_the_one_a_reply_takes_its_product_from(whole, extraction):
    # Mentions, notes, care tips and agreements, whether their checks pass or not, and the comment above a reply that
    # names its product only there (refers_to "parent").
    assert kept_comment_ids(whole, extraction) == KEPT


def test_a_source_with_no_item_of_its_own_is_kept_through_a_parent_and_through_an_earlier_chain(extraction, types):
    # 15 Oct 2026 (the coordinator, after the migration: replies whose product source had become a stub). Slimming was
    # not the cause (verification dropped those sources since, found edited on Reddit: engine/tests/test_verify.py), and
    # this pins it: the comment a reply takes its product from is kept whole, with no item of its own, for "parent" and
    # for "earlier" (the reply's parent's parent), and so is each comment it takes it from in turn.
    thread = whole_thread_dict()
    thread["comments"] += [c("s30top", "olga_t", "The Bodum one, every morning for six years.", 5),
                           c("s31mid", "pete_t", "Same here.", 2, parent_id="s30top"),
                           c("s32low", "quin_t", "Mine is nine years old now.", 3, parent_id="s31mid")]
    more = extraction_dict()
    more["mentions"] += [{"comment_id": "s32low", "product": "Bodum kettle", "category": "kitchen",
                          "stance": "recommend", "quote": "Mine is nine years old now.",
                          "product_type": "electric kettle", "refers_to": "earlier"},
                         {"comment_id": "s31mid", "product": "Bodum kettle", "category": "kitchen",
                          "stance": "recommend", "quote": "Same here.", "product_type": "electric kettle",
                          "refers_to": "parent"}]
    whole, extraction = Thread.model_validate(thread), Extraction.model_validate(more)
    kept = kept_comment_ids(whole, extraction)
    assert {"s30top", "s31mid", "s32low"} <= kept  # s30top has no item: kept as both replies' source
    slimmed = slim_thread(whole, extraction, types, NOW)
    assert by_id(slimmed)["s30top"].status == "ok"
    reasons = {m.comment_id: why for m, why in check_extraction(extraction, slimmed).rejected}
    assert "s32low" not in reasons and "s31mid" not in reasons


def test_every_other_comment_keeps_its_shape_but_not_its_words_or_writer(whole, slimmed):
    before, after = by_id(whole), by_id(slimmed)
    assert list(after) == list(before)  # every comment, in the same order
    for cid, comment in after.items():
        old = before[cid]
        assert (comment.parent_id, comment.created_at, comment.score, comment.url) == (
            old.parent_id, old.created_at, old.score, old.url)
        if cid in KEPT:
            assert (comment.status, comment.body, comment.author) == ("ok", old.body, old.author)
        elif old.status == "ok":
            assert (comment.status, comment.body, comment.author) == ("not_kept", "", None)
        else:
            assert comment == old  # a deleted comment's stub stays as it was


def test_the_title_stays_and_the_posts_words_and_writer_go(whole, slimmed):
    assert slimmed.title == whole.title and (slimmed.score, slimmed.url, slimmed.created_at) == (
        whole.score, whole.url, whole.created_at)
    assert (slimmed.body, slimmed.author) == ("", None)
    assert slimmed.slimmed and not whole.slimmed


def test_a_post_reddit_shows_as_removed_keeps_saying_so(extraction, types):
    gone = Thread.model_validate(whole_thread_dict(body="[removed]"))
    assert slim_thread(gone, extraction, types, NOW).body == "[removed]"  # module 2 leaves such a post out


def test_the_whole_threads_facts_hold_no_words(slimmed):
    facts = slimmed.whole_thread
    assert facts.post_names == ["electric kettle"]
    assert facts.comment_names == {"s3drop": ["stovetop kettle"], "s6copied": ["electric kettle"],
                                   "s11drop": ["electric kettle"], "s14drop": ["electric kettle"],
                                   "s24extra": ["exfoliant", "salicylic acid product", "BHA product"]}
    assert [tuple(sorted(pair)) for pair in facts.copies] == [("s6copied", "s7copy")]
    assert facts.first_seen == {"alice_t": datetime(2025, 3, 1, 12, tzinfo=UTC)}
    assert facts.quoted_elsewhere == [quote_fingerprint(CHEFMAN)]
    assert facts.extraction == "extract-v9 2026-10-12T10:00:00+00:00" and facts.slimmed_at == NOW
    words = json.dumps(facts.model_dump(mode="json"))
    for text in (COPY, CHEFMAN, "Following", "induction", "Bonavita"):
        assert text not in words


def test_a_comment_whose_words_arent_kept_can_hold_no_words_or_writer():
    stub = make_comment("x1", status="not_kept", body="", author=None)
    assert Comment.model_validate(stub).status == "not_kept"
    with pytest.raises(ValueError, match="no words and no writer"):
        Comment.model_validate({**stub, "body": "some words"})
    with pytest.raises(ValueError, match="no words and no writer"):
        Comment.model_validate({**stub, "author": {"name": "someone"}})
    with pytest.raises(ValueError, match="verified_at"):
        Comment.model_validate({**stub, "verified_at": "2026-10-13T00:00:00Z"})


def test_a_slimmed_thread_can_hold_no_post_words_or_post_writer(slimmed):
    data = slimmed.model_dump(mode="json")
    with pytest.raises(ValueError, match="title, not its post"):
        Thread.model_validate({**data, "body": "the post's words"})
    with pytest.raises(ValueError, match="post writer"):
        Thread.model_validate({**data, "author": {"name": "someone"}})


# --- Read the same as the whole thread ---

def kept_items(result) -> tuple:
    return ([(m.comment_id, m.product) for m in result.kept], [(n.comment_id, n.about) for n in result.kept_notes],
            [a.comment_id for a in result.kept_agreements], [t.comment_id for t in result.kept_care])


def test_the_extractions_checks_keep_and_reject_the_same_items(whole, extraction, slimmed):
    before, after = check_extraction(extraction, whole), check_extraction(extraction, slimmed)
    assert kept_items(after) == kept_items(before)
    assert [m.comment_id for m, _ in after.rejected] == [m.comment_id for m, _ in before.rejected] == [
        "s10quoted", "s16rej"]
    # The quoted block's words were written by a comment whose words aren't kept: still someone else's words.
    assert dict((m.comment_id, why) for m, why in after.rejected)["s10quoted"] == dict(
        (m.comment_id, why) for m, why in before.rejected)["s10quoted"]


def test_every_kept_comments_voice_is_the_same(whole, extraction, slimmed):
    before, after = check_extraction(extraction, whole), check_extraction(extraction, slimmed)
    old, new = by_id(whole), by_id(slimmed)
    for cid in sorted(KEPT):
        assert score_voice(new[cid], slimmed, after.kept_agreements) == score_voice(old[cid], whole,
                                                                                   before.kept_agreements), cid
    # Well upvoted only because the dropped comments' scores still count; a reply agrees; copied text.
    assert "well upvoted" in score_voice(new["s1kept"], slimmed, after.kept_agreements).tags
    assert "replies agree" in score_voice(new["s1kept"], slimmed, after.kept_agreements).tags
    assert "copied text" in score_voice(new["s7copy"], slimmed, after.kept_agreements).tags


def test_copies_count_once_as_before(whole, slimmed):
    assert copied_comment_ids(slimmed) == copied_comment_ids(whole) == {"s6copied", "s7copy"}
    assert repeated_copies(slimmed) == repeated_copies(whole) == {"s7copy"}  # the later copy's mention is left out


def test_copies_among_comments_not_kept_are_left_out_and_change_nothing(tmp_path):
    # Found slimming the library (13 Oct 2026): an account posting the same text again and again, with no product in it.
    # Those copies touch no kept comment, so they can't change any voice or any mention: nothing of them is kept.
    spam = ("Join our giveaway this week and tell all your friends about it because the winner gets a whole year of "
            "free coffee delivered")
    comments = whole_thread_dict()["comments"] + [c("s40spam", "bot_one_t", spam, 0), c("s41spam", "bot_two_t", spam, 0)]
    root = a_library(tmp_path, [whole_thread_dict(comments=comments)], {TID: extraction_dict()})
    assert slim_library(root, now=NOW, gold_ids=set()).slimmed == [TID]
    saved = Thread.model_validate_json((root / "threads" / f"{TID}.json").read_text())
    assert [tuple(pair) for pair in saved.whole_thread.copies] == [("s6copied", "s7copy")]


def test_a_copy_whose_kept_comment_is_later_deleted_counts_no_more(slimmed):
    deleted = slimmed.model_copy(update={"comments": [
        cm.model_copy(update={"status": "deleted", "body": "[deleted]", "author": None}) if cm.id == "s7copy" else cm
        for cm in slimmed.comments]})
    assert copied_comment_ids(deleted) == set()


def test_the_thread_is_found_for_every_known_product_type_as_before(whole, slimmed, types):
    assert "salicylic acid product" in types and "electric kettle" in types and "air fryer" in types
    for product_type in types + ("salicylic acid and niacinamide product",):
        assert relevance(slimmed, product_type) == relevance(whole, product_type), product_type
        assert talking(slimmed, product_type) == talking(whole, product_type), product_type
        assert _about_the_product(slimmed, product_type) == _about_the_product(whole, product_type), product_type
    assert _about_the_product(slimmed, "electric kettle")  # its post named it, its title doesn't
    # A request naming two ingredients counts a comment naming either, as the words themselves would.
    assert talking(slimmed, "salicylic acid and niacinamide product") == 1


# --- Need-led reading (main, 14 Oct 2026: a thread whose title or post talks about the request's needs is read first) ---

def test_the_needs_a_slimmed_threads_post_talked_about_are_known_as_before(extraction, types):
    from engine.needs import every_config_need, thread_needs

    body = "My electric kettle died after two years. I want a quiet one: the old one was so loud, and not plastic."
    whole = Thread.model_validate(whole_thread_dict(body=body))
    slimmed = slim_thread(whole, extraction, types, NOW)
    needs = every_config_need()
    assert slimmed.body == "" and thread_needs(slimmed, needs) == thread_needs(whole, needs)
    assert {"lasting", "quiet", "plastic-free"} <= set(thread_needs(slimmed, needs))
    # What is noted is config's own need words the post held, never the post's words.
    assert set(slimmed.whole_thread.post_need_words) <= {word for need in needs for word in need.words}
    assert "electric" not in slimmed.whole_thread.post_need_words


def test_hair_types_written_together_in_a_slimmed_post_still_name_their_needs(extraction, types):
    from engine.needs import every_config_need, thread_needs

    whole = Thread.model_validate(whole_thread_dict(body="Any kettle for someone with fine, oily hair? Joking."))
    slimmed = slim_thread(whole, extraction, types, NOW)
    assert "fine hair" in thread_needs(whole, every_config_need())
    assert thread_needs(slimmed, every_config_need()) == thread_needs(whole, every_config_need())


def test_a_requests_own_words_are_found_in_a_slimmed_post_when_they_are_words_the_engine_knows(extraction, types):
    # A word of the request ("pour-over") is no need of config's, and any word can be one: a slimmed post keeps, of its
    # words, only which of the words the engine knows it held (engine.slim.known_words: the words of every request the
    # daily plan works out, and the product types', ingredients' and needs' own). Another is found by the title only.
    from engine.needs import Need, thread_needs

    pour_over, zeppelin = (Need("pour-over", request_word="pourover"),), (Need("zeppelin", request_word="zeppelin"),)
    posted = Thread.model_validate(whole_thread_dict(body="I make pour-over every morning, zeppelin mug in hand."))
    slimmed = slim_thread(posted, extraction, types, NOW, words=frozenset({"pourover", "mug"}))
    assert thread_needs(posted, pour_over) == thread_needs(slimmed, pour_over) == ("pour-over",)
    assert thread_needs(posted, zeppelin) == ("zeppelin",) and thread_needs(slimmed, zeppelin) == ()
    assert slimmed.whole_thread.post_words == ["mug", "pourover"]  # the engine's words, never the post's own
    titled = Thread.model_validate(whole_thread_dict(title="Zeppelin kettle?", body="I make pour-over."))
    assert thread_needs(slim_thread(titled, extraction, types, NOW, words=frozenset()), zeppelin) == ("zeppelin",)


def test_the_words_the_engine_knows_hold_the_checked_requests_and_its_own(tmp_path):
    words = slim.known_words(tmp_path)
    assert {"pourover", "pfas", "nonstick"} <= words  # the search page's example requests (b09, b10)
    assert {"kettle", "salicylic", "smoothie", "sensitiv"} <= words  # product types, ingredients, title and need words
    assert all(word.isalnum() and word == word.lower() for word in words)  # as need_words gives a request's words


def test_a_posts_known_words_are_found_as_need_led_reading_finds_a_requests_word():
    from engine.needs import post_request_words
    from engine.credibility import _own_words
    from engine.sources import _title_has

    posts = ["I make Pour-Over every morning; anti-frizz serum, sulfate-free shampoo.", "&gt; quoted pfas line\nmine: ok",
             "Non-stick pans: the Tefal one is non stick, the best pour over kit", ""]
    words = sorted(slim.known_words(None))
    for body in posts:
        found = post_request_words(body, words)
        assert found == [word for word in words if _title_has(_own_words(body), word)], body


def test_a_thread_whose_slimmed_copy_would_lose_its_posts_needs_is_left_whole(tmp_path, monkeypatch):
    root = a_library(tmp_path, [whole_thread_dict(body="My electric kettle died after two years.")],
                     {TID: extraction_dict()})
    monkeypatch.setattr(slim, "post_need_words", lambda body: [])  # the needs its post talked about "forgotten"
    result = slim_library(root, now=NOW, gold_ids=set())
    assert result.slimmed == [] and "the needs" in result.refused[TID]


def test_the_bulk_importer_counts_a_slimmed_thread_its_post_named_the_type_in(extraction, types):
    from engine.bulk_import import _have

    whole = Thread.model_validate(whole_thread_dict(title="Which one should I buy?"))  # its post names the kettle
    slimmed = slim_thread(whole, extraction, types, NOW)
    assert _have([slimmed], "electric kettle", "kitchen") == _have([whole], "electric kettle", "kitchen")
    assert sum(_have([slimmed], "electric kettle", "kitchen").values()) == 1


def test_the_product_types_looked_for_include_the_ones_the_library_was_filled_for(tmp_path):
    (tmp_path / "requests.jsonl").write_text(json.dumps({"status": "ok", "product_type": "sourdough proofer"}) + "\n"
                                             + json.dumps({"status": "clarify", "product_type": None}) + "\n",
                                             encoding="utf-8")
    assert "sourdough proofer" in known_types(tmp_path) and "sourdough proofer" not in known_types(tmp_path / "elsewhere")


def test_the_comments_the_ai_read_are_counted_as_before(whole, slimmed):
    assert len(shown_comment_ids(slimmed)) == len(shown_comment_ids(whole))


def test_writers_first_comments_in_the_thread_are_as_before(whole, slimmed):
    before, after = profiles._first_seen(whole), profiles._first_seen(slimmed)
    writers = {cm.author.name for cm in slimmed.comments if cm.author is not None}
    assert {name: after[name] for name in writers} == {name: before[name] for name in writers}
    assert set(after) == writers  # dropped writers' names aren't kept anywhere


# --- When each kept comment was last verified on Reddit ---

def stamped(extraction: dict | None = None, **thread_fields) -> dict[str, datetime | None]:
    thread = Thread.model_validate(whole_thread_dict(**thread_fields))
    out = slim_thread(thread, Extraction.model_validate(extraction or extraction_dict()), (), NOW)
    return {cm.id: cm.verified_at for cm in out.comments if cm.status == "ok"}


def test_a_thread_read_on_reddit_verifies_its_kept_comments_when_it_was_read():
    read = datetime(2026, 10, 6, tzinfo=UTC)
    assert set(stamped().values()) == {read}  # read through Parse (no provenance: older files)
    assert set(stamped(read_from="bright_data", collected_at="2026-10-10T08:00:00Z").values()) == {
        datetime(2026, 10, 10, 8, tzinfo=UTC)}


def test_an_archive_thread_is_verified_only_where_a_live_read_covered_it():
    assert set(stamped(read_from="arctic_shift").values()) == {None}  # never checked live
    # Checked live through Bright Data, which returns top-level comments and their direct replies only: a reply to a
    # reply kept from the archive was never read live.
    seconding = "Seconding the Zojirushi kettle here."
    data = extraction_dict()
    data["agreements"].append({"comment_id": "s30deep", "quote": seconding})
    deep = stamped(data, read_from="arctic_shift", checked_live_at="2026-10-11T09:00:00Z",
                   comments=whole_thread_dict()["comments"] + [c("s30deep", "una_t", seconding, 3, parent_id="s2agree")])
    assert deep["s1kept"] == deep["s2agree"] == datetime(2026, 10, 11, 9, tzinfo=UTC)
    assert deep["s30deep"] is None  # a reply to a reply: kept from the archive, never read live


# --- A whole library ---

def a_library(tmp_path, threads: list[dict], extractions: dict[str, dict]):
    root = write_gold(tmp_path / "library", threads, voices=None, mentions=None)
    (root / "extracted").mkdir(exist_ok=True)
    for thread_id, data in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps(data), encoding="utf-8")
    return root


def other_thread(thread_id: str) -> dict:
    return make_thread(id=thread_id, community="BuyItForLife", category="kitchen", title="Which kettle lasts?",
                       body="", url=f"https://www.reddit.com/r/BuyItForLife/comments/{thread_id}/kettle/",
                       comments=[make_comment(f"{thread_id}a", thread_id=thread_id, body="My Dualit is 12 years old.")])


def test_slimming_a_library_leaves_threads_not_extracted_yet_and_gold_threads_whole(tmp_path):
    root = a_library(tmp_path, [whole_thread_dict(), other_thread("1waits"), other_thread("1goldie")],
                     {TID: extraction_dict(), "1goldie": {**extraction_dict(), "thread_id": "1goldie", "mentions": [],
                                                         "notes": [], "agreements": [], "care": []}})
    result = slim_library(root, now=NOW, gold_ids={"1goldie"})
    assert (result.slimmed, result.not_extracted, result.gold) == ([TID], ["1waits"], ["1goldie"])
    saved = {t.id: t for t in (Thread.model_validate_json(p.read_text()) for p in (root / "threads").glob("*.json"))}
    assert saved[TID].slimmed and not saved["1waits"].slimmed and not saved["1goldie"].slimmed
    assert result.comments_kept == len(KEPT) and result.comments_dropped == 10
    assert result.text_after < result.text_before


def test_slimming_again_changes_nothing(tmp_path):
    root = a_library(tmp_path, [whole_thread_dict()], {TID: extraction_dict()})
    slim_library(root, now=NOW, gold_ids=set())
    first = (root / "threads" / f"{TID}.json").read_bytes()
    again = slim_library(root, now=datetime(2026, 10, 20, tzinfo=UTC), gold_ids=set())
    assert (again.slimmed, again.already) == ([], [TID])
    assert (root / "threads" / f"{TID}.json").read_bytes() == first


def test_a_dry_run_counts_and_writes_nothing(tmp_path):
    root = a_library(tmp_path, [whole_thread_dict()], {TID: extraction_dict()})
    before = (root / "threads" / f"{TID}.json").read_bytes()
    result = slim_library(root, now=NOW, gold_ids=set(), dry_run=True)
    assert result.slimmed == [TID] and result.comments_kept == len(KEPT)
    assert (root / "threads" / f"{TID}.json").read_bytes() == before


def test_a_thread_whose_slimmed_copy_would_read_differently_is_left_whole_and_named(tmp_path, monkeypatch):
    # The guard: before writing, each slimmed copy is read the way answers read it and compared with the whole thread.
    # Here the product types its dropped comments named are "forgotten", so the thread would be found differently.
    root = a_library(tmp_path, [whole_thread_dict()], {TID: extraction_dict()})
    monkeypatch.setattr(slim, "names_in", lambda text, types: [])
    result = slim_library(root, now=NOW, gold_ids=set())
    assert result.slimmed == [] and list(result.refused) == [TID]
    assert "relevance" in result.refused[TID]
    assert not Thread.model_validate_json((root / "threads" / f"{TID}.json").read_text()).slimmed


def test_a_thread_with_a_malformed_extraction_is_left_whole(tmp_path):
    root = a_library(tmp_path, [whole_thread_dict()], {})
    (root / "extracted" / f"{TID}.json").write_text("{not json", encoding="utf-8")
    result = slim_library(root, now=NOW, gold_ids=set())
    assert result.slimmed == [] and TID in result.problems


def test_slimming_never_makes_up_text_a_thread_did_not_have(whole, extraction, types):
    with pytest.raises(SlimError, match="extraction of"):
        slim_thread(whole, extraction.model_copy(update={"thread_id": "1another"}), types, NOW)


# --- The AI never reads a slimmed thread: most of its words are gone ---

def test_a_slimmed_thread_is_never_given_to_the_ai_to_extract_again(tmp_path):
    from engine import extract
    from engine.gemini_extract import GeminiClient, extract_threads
    from engine.tests.test_gemini_extract import FakeFetch, a_reply

    old = {**extraction_dict(), "instructions_version": "extract-v1"}  # older instructions: due again if it were whole
    root = a_library(tmp_path, [whole_thread_dict(), other_thread("1waits")], {TID: old})
    slim_library(root, now=NOW, gold_ids=set())
    assert extract.todo(root / "threads", "extract-v9") == ["1waits"]  # the slimmed one is read whole again first
    slimmed = Thread.model_validate_json((root / "threads" / f"{TID}.json").read_text())
    with pytest.raises(extract.ExtractionError, match="slimmed"):
        extract.render_thread(slimmed)
    fetch = FakeFetch(a_reply())
    report = extract_threads(root / "threads", tmp_path / "out", GeminiClient(key="test-key", fetch=fetch,
                                                                             sleep=lambda s: None), ids=[TID])
    assert report.skipped == [TID] and fetch.sent == []


# --- Answers ---

def kettle_library(tmp_path, name: str):
    """The pre-check's made-up kettle library, with comments no extraction points to and posts with words."""
    from engine.tests.test_precheck import library

    root = library(tmp_path / name)
    for path in (root / "threads").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        tid = data["id"]
        data["body"] = "Every kettle I buy dies, which electric kettle lasts?"
        data["comments"] += [
            make_comment(f"{tid}n{i}", thread_id=tid, body=text, score=score,
                         url=f"https://www.reddit.com/r/BuyItForLife/comments/{tid}/comment/{tid}n{i}/")
            for i, (text, score) in enumerate([("Following this thread for ideas.", 30),
                                               ("Mine is a cheap stovetop kettle, no complaints.", 1),
                                               ("Bought a gooseneck kettle after reading this.", 0)])]
        path.write_text(json.dumps(data), encoding="utf-8")
    return root


def test_an_answer_on_the_slimmed_library_is_the_same_as_on_the_whole_one(tmp_path):
    from engine.tests.test_pipeline import REQUEST
    from engine.web import answer_json

    whole_lib, slim_lib = kettle_library(tmp_path, "whole"), kettle_library(tmp_path, "slim")
    result = slim_library(slim_lib, now=NOW, gold_ids=set())
    assert sorted(result.slimmed) == ["1kett01", "1kett02"] and result.comments_dropped == 6
    before = answer_request(REQUEST, library_dir=whole_lib, live_check_required=False)
    after = answer_request(REQUEST, library_dir=slim_lib, live_check_required=False)
    assert answer_json(after) == answer_json(before) and after.text() == before.text()
    assert after.comments_read == before.comments_read and after.answer.picks
