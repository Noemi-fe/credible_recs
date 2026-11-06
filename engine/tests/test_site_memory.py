"""The live site's memory, bounded so 2 GiB fits again (5 Nov 2026, Noemi's "Let's do A").

The site had run at 4 GiB since 15 Oct 2026, a stopgap. Measured on 5 Nov 2026 (CLAUDE.md, DECISIONS.md): at 4 GiB it used
1.9 to 2.0 GiB in its busiest windows, with each instance's memory climbing through its life, so at 2 GiB it would run out
within hours. These tests hold each bound that brings it under 80% of 2 GiB. None changes an answer: every bound only decides what is kept in memory,
and an answer worked out again is the same answer. The first deploy of this code asks for 3 GiB (6 Nov 2026, deploy.sh), because the
worst case on Cloud Run is about 79.8% of 2 GiB and Linux is not measured. It steps down to 2 GiB once Cloud Monitoring shows room.

Every library, request and comment here is made up. Nothing reads data/.
"""

import copy
import json
import re
import sys

import pytest

from engine import library_cache
from engine.compact import SharedFieldsSet, share_fields_sets
from engine.gold import load_threads
from engine.extract import load_checked
from engine.tests.test_library_cache import settled
from engine.tests.test_pipeline import library


# --- Library objects share what they have in common (compact.py) ---

def test_the_kept_library_shares_one_fields_set_between_objects_of_a_shape(tmp_path):
    # Each pydantic object keeps a set of the names of the fields it was given: 728 bytes for a comment, 213,000 comments
    # and as many again of other objects in the live library. Objects built from the same fields can share one.
    root = settled(library(tmp_path))
    kept = library_cache.loaded(root / "threads")
    comments = [c for t in kept.threads for c in t.comments]
    assert len(comments) > 5
    shapes = {frozenset(c.model_fields_set) for c in comments}
    assert len({id(c.__pydantic_fields_set__) for c in comments}) == len(shapes)
    mentions = [m for result in kept.checked.values() for m in result.kept]
    assert mentions
    assert len({id(m.__pydantic_fields_set__) for m in mentions}) == len({frozenset(m.model_fields_set) for m in mentions})


def test_sharing_fields_sets_changes_nothing_an_object_says_about_itself(tmp_path):
    root = settled(library(tmp_path))
    kept = library_cache.loaded(root / "threads")
    fresh = load_threads(root / "threads", skip_broken=True)  # not shared: the same files, read apart
    assert [t.model_dump(exclude_unset=True) for t in kept.threads] == [t.model_dump(exclude_unset=True) for t in fresh]
    assert [t.model_dump() for t in kept.threads] == [t.model_dump() for t in fresh]
    assert kept.threads == fresh
    for a, b in zip(kept.threads, fresh):
        assert a.model_fields_set == b.model_fields_set
        assert [c.model_fields_set for c in a.comments] == [c.model_fields_set for c in b.comments]
    assert kept.checked == load_checked(root / "threads")


def test_a_shared_fields_set_cannot_be_changed_by_accident(tmp_path):
    # One object's set is every such object's: a change to it would show on all of them, so changing it is an error.
    root = settled(library(tmp_path))
    kept = library_cache.loaded(root / "threads")
    comment = kept.threads[0].comments[0]
    assert isinstance(comment.__pydantic_fields_set__, SharedFieldsSet)
    with pytest.raises(AttributeError):
        comment.__pydantic_fields_set__.add("score")
    with pytest.raises(AttributeError):
        comment.score = 3  # pydantic records the assignment in the set


def test_copies_of_a_kept_thread_get_a_set_of_their_own(tmp_path):
    # without_unusable_comments and for_request copy kept threads with model_copy(update=...), which adds the updated
    # names to the copy's set: the copy must not share the original's.
    root = settled(library(tmp_path))
    kept = library_cache.loaded(root / "threads")
    thread = kept.threads[0]
    before = set(thread.model_fields_set)
    copied = thread.model_copy(update={"comments": thread.comments[:1]})
    assert type(copied.__pydantic_fields_set__) is set
    assert copied.model_fields_set == before | {"comments"}
    assert thread.model_fields_set == before
    assert isinstance(thread.__pydantic_fields_set__, SharedFieldsSet)
    assert len(thread.comments) >= 1
    deeper = copy.deepcopy(thread)
    assert type(deeper.__pydantic_fields_set__) is set and deeper.model_fields_set == before


def test_sharing_is_done_once_and_to_every_kind_of_object(tmp_path):
    root = settled(library(tmp_path))
    threads = load_threads(root / "threads", skip_broken=True)
    checked = load_checked(root / "threads")
    share_fields_sets(threads, checked)
    share_fields_sets(threads, checked)  # again: nothing changes
    thread = threads[0]
    assert isinstance(thread.__pydantic_fields_set__, SharedFieldsSet)
    assert all(isinstance(c.__pydantic_fields_set__, SharedFieldsSet) for c in thread.comments)
    assert all(isinstance(c.author.__pydantic_fields_set__, SharedFieldsSet) for c in thread.comments if c.author)
    result = next(iter(checked.values()))
    assert all(isinstance(m.__pydantic_fields_set__, SharedFieldsSet) for m in result.kept)


# --- The library's name index leaves no table of every name behind (match_products.forget_names) ---

def _made_up_library(count: int = 300):
    import random

    from engine.group_products import ProductMention

    rng = random.Random(5)
    brands = ["Lodge", "Fellow", "Stagg", "CeraVe", "Tiger", "Zojirushi", "Our Place", "Cosrx", "Anker"]
    rest = ["", "kettle", "electric kettle", "Stagg EKG", "cast iron skillet", "skillet", "rice cooker", "SA cleanser",
            "Hydrating Cleanser", "cleanser", "moisturizing cream", "12 inch skillet", "dutch oven", "shampoo"]
    return [ProductMention(f"t{i % 30}", f"c{i}", f"{rng.choice(brands)} {rng.choice(rest)}".strip(),
                           rng.choice(["kitchen", "skincare"]), "recommend") for i in range(count)]


def _name_tables():
    from engine import match_products as mp

    return {"normalized": mp._NORMALIZED, "features": mp._FEATURES, "slips": mp._SLIP_KEYS,
            "words": mp._WORDS_NO_ALIASES, "words by list": mp._WORDS_BY_LIST}


def test_the_name_index_leaves_no_table_of_every_name_behind():
    # Measured 5 Nov 2026 with the library at 2,748 threads: making the index for a category worked out the words and
    # features of every one of its names (118,575 names), and they stayed: 290 MB that answers never need again (an
    # answer needs the few hundred names of its own request, and works those out when it asks). Pure tables: an
    # answer that asks after they are emptied works the same names out again and gets the same answer.
    from engine.group_products import library_name_index

    library = _made_up_library()
    index = library_name_index(library)
    index["kitchen"]  # a category's index is made when a grouping first asks for it
    index["skincare"]
    for name, table in _name_tables().items():
        assert len(table) == 0, name


def test_groups_are_the_same_whether_or_not_the_tables_were_emptied():
    from engine import match_products as mp
    from engine.group_products import group_products, library_name_index

    library = _made_up_library()
    index = library_name_index(library)
    kept = group_products(library, product_type="electric kettle", index=index)
    assert any(len(table) for table in _name_tables().values())  # the grouping worked its own names out
    mp.forget_names()
    assert all(len(table) == 0 for table in _name_tables().values())
    assert group_products(library, product_type="electric kettle", index=index) == kept
    assert group_products(library, product_type="electric kettle") == kept


# --- The remembered answers are kept to a size (web._answers) ---

def _answer(size: int) -> tuple[int, str, bytes]:
    return 200, "application/json", b"x" * size


def test_remembered_answers_are_kept_to_a_size_and_the_oldest_go_first():
    # Remembered answers were kept until their time was up, but never taken out of memory unless asked again: the many
    # different requests of a rush (each answer is 30 to 90 KB of JSON) only ever added to them.
    from engine import web

    answers = web.RememberedAnswers(limit_bytes=1000)
    for n in range(10):
        answers[(f"request {n}", "lib", "uk")] = (1e9, _answer(300))
    assert answers.size() <= 1000
    assert [key[0] for key in answers] == ["request 7", "request 8", "request 9"]  # the newest three of ten
    assert answers.get(("request 9", "lib", "uk")) == (1e9, _answer(300))


def test_an_answer_made_again_is_the_newest_and_its_old_size_is_forgotten():
    from engine import web

    answers = web.RememberedAnswers(limit_bytes=1000)
    answers[("a", "lib", "uk")] = (1e9, _answer(400))
    answers[("b", "lib", "uk")] = (1e9, _answer(400))
    answers[("a", "lib", "uk")] = (1e9, _answer(100))  # made again, shorter
    assert answers.size() == 500
    answers[("c", "lib", "uk")] = (1e9, _answer(650))
    assert [key[0] for key in answers] == ["a", "c"]  # "b" was the oldest once "a" was made again


def test_answers_whose_time_is_up_go_before_answers_that_can_still_be_shown(monkeypatch):
    from engine import web

    monkeypatch.setattr(web, "_clock", lambda: 100.0)
    answers = web.RememberedAnswers(limit_bytes=700)
    answers[("old but valid", "lib", "uk")] = (1e9, _answer(300))
    answers[("expired", "lib", "uk")] = (50.0, _answer(300))
    answers[("new", "lib", "uk")] = (1e9, _answer(300))
    assert [key[0] for key in answers] == ["old but valid", "new"]


def test_popping_and_clearing_keep_the_size_right():
    from engine import web

    answers = web.RememberedAnswers(limit_bytes=10_000)
    answers[("a", "lib", "uk")] = (1e9, _answer(100))
    answers[("b", "lib", "uk")] = (1e9, _answer(200))
    assert answers.pop(("a", "lib", "uk"), None) is not None and answers.size() == 200
    assert answers.pop(("nothing", "lib", "uk"), None) is None
    answers.clear()
    assert answers.size() == 0 and len(answers) == 0


def test_an_answer_too_big_for_the_size_is_still_given_and_kept_alone():
    from engine import web

    answers = web.RememberedAnswers(limit_bytes=100)
    answers[("big", "lib", "uk")] = (1e9, _answer(500))
    assert list(answers) == [("big", "lib", "uk")]


def test_the_site_gives_the_same_answer_whether_or_not_it_was_remembered(tmp_path, monkeypatch):
    # An answer let go of is worked out again, and is the same answer.
    from engine import web
    from engine.tests.test_web import REQUEST, kettle_library

    library_dir = kettle_library(tmp_path)
    web.clear_answer_cache()
    kept = web.answer_response(REQUEST, library_dir)
    assert kept[0] == 200
    one = len(kept[2])
    monkeypatch.setattr(web, "_answers", web.RememberedAnswers(limit_bytes=one + one // 2))  # room for one
    first = web.answer_response(REQUEST, library_dir)
    web.answer_response("a different kettle that boils fast", library_dir)  # takes the room: the first is let go
    assert len(web._answers) == 1 and (REQUEST, str(library_dir), "uk") not in web._answers
    again = web.answer_response(REQUEST, library_dir)
    assert (again[0], again[1]) == (first[0], first[1])
    assert json.loads(again[2])["answer"] == json.loads(first[2])["answer"]
    web.clear_answer_cache()


# --- The writers' profile store, kept small for the site (profiles.CompactProfileStore) ---

def _profiles_file(tmp_path, count: int = 300):
    """A made-up profiles.json: fresh and stale entries, writers the archive did not know (null), flairs with and without
    text, one writer with fewer numbers than the others and one entry with no date."""
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 11, 5, 12, 0, tzinfo=UTC)
    stats = {"earliest_comment_at": 1564695081, "earliest_post_at": 1573441109, "last_comment_at": 1742854247,
             "last_post_at": 1755907177, "num_comments": 27745, "num_posts": 92, "post_karma": 2406,
             "comment_karma": 199299, "total_karma": 201705}
    writers, flairs = {}, {}
    for n in range(count):
        when = (now - timedelta(days=n % 45, seconds=n, microseconds=n * 7)).isoformat()
        writers[f"writer{n}"] = {"stats": None if n % 11 == 0 else {**stats, "num_comments": n}, "checked_at": when}
        flairs[f"c{n}"] = {"flair": None if n % 3 == 0 else f"Flair {n % 7}", "checked_at": when}
    writers["fewer"] = {"stats": {"num_comments": 4, "num_posts": 2}, "checked_at": now.isoformat()}
    writers["nodate"] = {"stats": stats}
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps({"writers": writers, "flairs": flairs}), encoding="utf-8")
    return path, now


def test_the_compact_store_says_what_the_plain_store_says(tmp_path):
    from datetime import timedelta

    from engine.profiles import CompactProfileStore, ProfileStore

    path, now = _profiles_file(tmp_path)
    for later in (timedelta(0), timedelta(days=10), timedelta(days=29, hours=23), timedelta(days=31)):
        clock = lambda later=later: now + later
        plain, compact = ProfileStore(path, clock=clock), CompactProfileStore(path, clock=clock)
        names = [f"writer{n}" for n in range(300)] + ["fewer", "Writer7", "WRITER8", "nobody"]
        for name in names:
            assert compact.user_stats(name) == plain.user_stats(name), name
            assert compact.checked_at(name) == plain.checked_at(name), name
        for comment_id in [f"c{n}" for n in range(300)] + ["nothing"]:
            assert compact.flair(comment_id) == plain.flair(comment_id), comment_id
            assert compact.flair_checked_at(comment_id) == plain.flair_checked_at(comment_id), comment_id
    with pytest.raises(KeyError):  # an entry with no date fails when asked, as it always did
        CompactProfileStore(path, clock=clock).user_stats("nodate")
    with pytest.raises(KeyError):
        ProfileStore(path, clock=clock).user_stats("nodate")


def test_a_looked_up_stats_dict_is_the_callers_own(tmp_path):
    from engine.profiles import CompactProfileStore

    path, now = _profiles_file(tmp_path)
    store = CompactProfileStore(path, clock=lambda: now)
    first = store.user_stats("writer1")
    first["num_comments"] = -1
    assert store.user_stats("writer1")["num_comments"] == 1


def test_the_compact_store_cannot_be_changed(tmp_path):
    from engine.profiles import CompactProfileStore

    path, now = _profiles_file(tmp_path)
    store = CompactProfileStore(path, clock=lambda: now)
    for change in (lambda: store.put_user("a", None), lambda: store.put_flair("a", None),
                   lambda: store.keep_only([], []), store.save):
        with pytest.raises(TypeError):
            change()


def test_the_compact_store_takes_half_the_memory(tmp_path):
    # Measured 5 Nov 2026 on the library's 56,666 writers and 77,085 flairs: 69 MB as the plain store, about 20 as this.
    import gc
    import tracemalloc

    from engine.profiles import CompactProfileStore, ProfileStore

    path, now = _profiles_file(tmp_path, count=3000)
    sizes = {}
    for name, make in (("plain", ProfileStore), ("compact", CompactProfileStore)):
        gc.collect()
        tracemalloc.start()
        store = make(path, clock=lambda: now)
        gc.collect()
        sizes[name] = tracemalloc.get_traced_memory()[0]
        tracemalloc.stop()
        del store
    assert sizes["compact"] < sizes["plain"] * 0.6, sizes


def test_the_site_reads_writers_through_the_compact_store(tmp_path, monkeypatch):
    from engine import pipeline
    from engine.profiles import CompactProfileStore

    monkeypatch.setattr(pipeline, "DEFAULT_LIBRARY_DIR", tmp_path)  # no profiles.json there: an empty store
    assert isinstance(pipeline.cached_profiles().store, CompactProfileStore)


# --- Objects are shared as each thread is read, not once all are (so a library read again never holds two sizes) ---

def test_each_thread_and_extraction_is_shared_as_it_is_read(tmp_path):
    # The shared sets were handed out after the whole library was read, so a library read again (threads read on demand
    # coming in) held every thread at its full size for a while: the peak, not the end, is what the site's memory must fit.
    root = settled(library(tmp_path))
    seen_threads, seen_results = [], []
    threads = load_threads(root / "threads", skip_broken=True, each=lambda thread: seen_threads.append(thread.id))
    assert seen_threads == [t.id for t in threads] and len(threads) > 1
    from engine.extract import check_extractions

    checked, _ = check_extractions(root / "threads", threads, each=lambda result: seen_results.append(result))
    assert len(seen_results) == len(checked) > 0
    assert {id(r) for r in seen_results} == {id(r) for r in checked.values()}


def test_a_kept_library_is_shared_by_the_time_it_is_kept_and_reads_the_same(tmp_path, monkeypatch):
    root = settled(library(tmp_path))
    calls = []
    real = library_cache.share_thread
    monkeypatch.setattr(library_cache, "share_thread", lambda *a, **k: calls.append(a) or real(*a, **k))
    kept = library_cache.loaded(root / "threads")
    assert len(calls) == len(kept.threads)  # shared as each thread was read
    assert all(isinstance(c.__pydantic_fields_set__, SharedFieldsSet) for t in kept.threads for c in t.comments)
    assert kept.checked == load_checked(root / "threads")


# --- The brand rules' remembered pairs share the sets of names they are keyed by (pipeline._same_brand) ---

def _group(name: str, *written: str):
    from engine.group_products import ProductGroup, ProductMention

    return ProductGroup(f"kitchen:{name.lower()}", name, "kitchen",
                        [ProductMention("t1", f"c{n}", w, "kitchen", "recommend") for n, w in enumerate(written or (name,))])


def test_pairs_remembered_for_the_brand_rules_share_their_sets_of_names():
    # 104,768 remembered pairs were 76 MB: each key held two new sets of names, though a product's names recur in the pair
    # it makes with every brand. The answer for a pair is the same whichever set object holds the names.
    from engine import pipeline

    pipeline._SAME_BRAND.clear()
    brands = [_group("Lodge", "Lodge", "lodge cast iron"), _group("Fellow", "Fellow", "Fellow Stagg")]
    products = [_group("Lodge cast iron skillet", "Lodge cast iron skillet", "Lodge skillet"),
                _group("Fellow Stagg EKG", "Fellow Stagg EKG", "Stagg EKG"), _group("Zojirushi kettle")]
    answers = {(b.name, p.name): pipeline._same_brand(b, p) for b in brands for p in products}
    assert answers[("Lodge", "Lodge cast iron skillet")] and not answers[("Lodge", "Zojirushi kettle")]
    assert len(pipeline._SAME_BRAND) == 6
    brand_sets = [key[1] for key in pipeline._SAME_BRAND]
    product_sets = [key[3] for key in pipeline._SAME_BRAND]
    assert len({id(s) for s in product_sets}) == 3  # one set for each product, not one for each pair
    assert len({id(s) for s in brand_sets}) == 2
    again = {(b.name, p.name): pipeline._same_brand(b, p) for b in brands for p in products}
    assert again == answers and len(pipeline._SAME_BRAND) == 6
    pipeline._SAME_BRAND.clear()


# --- Smaller bounds: tables of remembered answers, the facts of recent threads, the library's names, remembered answers ---

def test_a_table_of_remembered_answers_holds_at_most_forty_thousand_by_default():
    # Each Table started again past 200,000 answers, and with 64 product types' work kept, several held 100,000 or more at
    # once (verify_quotes._FOUND 114,000 and sources._MENTIONS 180,000), about 40 to 60 MB of the live site's memory that one
    # answer never needs more than a few thousand of. Past the limit a table starts again, as it always did.
    from engine.memo import DEFAULT_TABLE_LIMIT, Table

    assert DEFAULT_TABLE_LIMIT == 40_000
    table = Table()
    assert table.limit == DEFAULT_TABLE_LIMIT
    for n in range(DEFAULT_TABLE_LIMIT + 5):
        table.keep(n, n)
    assert len(table) == 5  # started again at the limit
    assert Table(limit=7).limit == 7


def test_the_facts_of_recent_threads_hold_more_threads_than_the_biggest_answer_reads():
    # credibility._thread_facts keeps (thread, facts) for the threads asked about lately: 512 of them were 28 MB, and
    # an answer asks about its own threads, at most config.PIPELINE_POPULAR_THREADS for a popular type.
    from engine import config, credibility

    assert credibility.THREADS_REMEMBERED == 256
    assert credibility.THREADS_REMEMBERED > config.PIPELINE_POPULAR_THREADS


def test_names_of_the_librarys_index_share_their_words():
    # 118,575 names are tuples of words, each word its own string until now ("kettle" held by thousands of names).
    from engine.group_products import ProductMention, library_name_index

    mentions = [ProductMention("t1", "c1", "Lodge cast iron skillet", "kitchen", "recommend"),
                ProductMention("t2", "c2", "Lodge cast iron pan", "kitchen", "recommend"),
                ProductMention("t3", "c3", "Zojirushi cast iron kettle", "kitchen", "recommend")]
    index = library_name_index(mentions)
    names = sorted(index._names["kitchen"])
    assert len(names) == 3
    words = [w for name in names for w in name]
    assert len({id(w) for w in words if w == "cast"}) == 1 and len({id(w) for w in words if w == "iron"}) == 1
    assert sum(1 for w in words if w == "cast") == 3


def test_the_remembered_answers_size_is_twenty_four_megabytes():
    from engine import config, web

    assert config.ANSWERS_KEPT_BYTES == 24 * 1024 * 1024
    assert web._answers.limit_bytes == config.ANSWERS_KEPT_BYTES


# --- The review of 5 Nov 2026 (evening): the bundle taken in item by item, saved checks kept in memory ---
#
# The review measured two things the first round missed. Taking in an on-demand bundle parsed the whole file at once, which
# takes about 7.8 times its size for a moment (+414 MiB for the 300 largest threads), and on Cloud Run a saved check is a
# small file on a disk that is memory, a 4 KiB page each whatever its size (18,400 files from the bucket's bundle at the
# start, 44,838 after a long soak).

import hashlib
import tracemalloc
from datetime import UTC, datetime, timedelta

from engine.live_check import LiveChecker
from engine.on_demand import Bundle, Item, SiteReader, bundle_items, write_threads

TEXT_WITH_EVERYTHING = ('{"id": "t1", "title": "A \\"quoted\\" title {with} [brackets], and a colon: here", '
                        '"body": "“Curly” and emoji 😀 and a backslash \\\\ and a newline\\nand a tab\\t"}')


def an_item(n: int, extraction="{}", thread=None) -> Item:
    return Item(thread=thread if thread is not None else TEXT_WITH_EVERYTHING.replace("t1", f"t{n}"),
                extraction=extraction, entry="teapot|teapot|", product_type="teapot",
                added_at="2026-11-01T10:00:00+00:00", tries=n % 3, slimmed=bool(n % 2))


def bundle_bytes(items: dict[str, Item], **dumps) -> bytes:
    return json.dumps({"version": 1, "threads": {tid: item.as_json() for tid, item in items.items()}},
                      ensure_ascii=dumps.pop("ensure_ascii", False), **dumps).encode("utf-8")


def whole_parse(data: bytes):
    """What the site did until the review: the whole file parsed at once."""
    return sorted(Bundle.from_json(json.loads(data)).threads.items())


@pytest.mark.parametrize("style", [{}, {"separators": (",", ":")}, {"indent": 2}, {"ensure_ascii": True},
                                   {"indent": "\t", "ensure_ascii": True}])
def test_a_bundle_read_item_by_item_gives_the_items_a_whole_parse_gives(style):
    items = {f"t{n}": an_item(n, extraction=None if n == 3 else TEXT_WITH_EVERYTHING) for n in (5, 3, 9, 1, 12)}
    data = bundle_bytes(items, **style)
    assert [(tid, item) for tid, item in bundle_items(data)] == whole_parse(data)
    assert [tid for tid, _ in bundle_items(data)] == sorted(items)  # in the order write_threads always wrote them


def test_a_bundle_with_other_keys_a_threads_key_deeper_down_and_odd_items_reads_like_a_whole_parse():
    one, two = an_item(1), an_item(2)
    text = ('{"note": {"threads": {"decoy": {"thread": "x"}}, "list": [1, {"threads": 2}, "}"]}, "version": 1, '
            f'"threads": {{"b": {json.dumps(two.as_json())}, "skipped": 5, "also": [1, 2], "a": '
            f'{json.dumps(one.as_json() | {"future_field": {"nested": [1, 2]}})}, "b": {json.dumps(one.as_json())}}}, '
            '"after": {"threads": 3}}')
    data = text.encode("utf-8")
    assert [(tid, item) for tid, item in bundle_items(data)] == whole_parse(data)
    assert [tid for tid, _ in bundle_items(data)] == ["a", "b"]  # a thread named twice is its last copy, as in a parse


def test_a_bundle_with_no_threads_gives_none_whatever_it_says():
    for text in ('{"version": 1}', '{"version": 1, "threads": null}', '{"threads": {}}', '{"threads": []}',
                 '{"threads": 0}', '{"threads": {"a": 5, "b": [1], "c": "text", "d": null}}'):
        assert list(bundle_items(text.encode())) == []
        assert whole_parse(text.encode()) == []


@pytest.mark.parametrize("broken", [b"", b"not json", b"[]", b"5", b'"text"', b"null", b'{"threads": [1]}',
                                    b'{"threads": "a"}', b'{"threads": 7}', b'{"threads": {"a": {"thread": "x"',
                                    b'{"threads": {"a": {"nope": 1}}}', b'{"threads": {"a": }}', b'{"threads" {}}',
                                    b'{"threads": {"a": 1,}}', b'{"threads": {"a": 1} "b": 2}', b'{"threads": {}} junk',
                                    b'{"threads": {"a": {"thread": "x" "extraction": null}}}',
                                    b'{"threads": {"a": {"thread": "bad \\q escape", "extraction": null, "entry": "e", '
                                    b'"product_type": "p", "added_at": "x"}}}', b'\xff\xfe{"threads": {}}'])
def test_a_bundle_that_cannot_be_read_cannot_be_read_item_by_item_either(broken):
    for read in (whole_parse, lambda data: list(bundle_items(data))):
        with pytest.raises((ValueError, TypeError, AttributeError)):
            read(broken)


class OneObject:
    """A bucket that holds one object, the bundle (made-up: nothing leaves the test)."""

    name = "made-up-bucket"

    def __init__(self, data: bytes):
        self.data = data

    def lookup(self, name):
        return True, "7"

    def get(self, name, generation=None):
        return self.data


def reader_for(tmp_path, data: bytes) -> SiteReader:
    (tmp_path / "library" / "threads").mkdir(parents=True)
    return SiteReader(OneObject(data), tmp_path / "library", job=None)


def test_a_bundle_that_is_bad_in_its_last_item_writes_nothing(tmp_path):
    good = {f"t{n}": an_item(n) for n in (1, 2, 3)}
    text = bundle_bytes(good).decode()[:-2] + ', "t9": {"nope": 1}}}'
    reader = reader_for(tmp_path, text.encode())
    assert reader.load_threads() is None
    assert list((tmp_path / "library" / "threads").glob("*.json")) == [] and reader._bundle_generation is None


def test_taking_a_bundle_in_writes_what_it_always_wrote_and_remembers_when_each_was_read(tmp_path):
    items = {f"t{n}": an_item(n) for n in (4, 2, 7)} | {"t8": an_item(8, extraction=None)}
    reader = reader_for(tmp_path, bundle_bytes(items))
    assert reader.load_threads() == 3
    assert sorted(p.stem for p in (tmp_path / "library" / "threads").glob("*.json")) == ["t2", "t4", "t7"]
    assert (tmp_path / "library" / "extracted" / "t2.json").read_text(encoding="utf-8") == "{}"
    assert (tmp_path / "library" / "threads" / "t4.json").read_text(encoding="utf-8") == items["t4"].thread
    assert reader._read_on == {tid: datetime(2026, 11, 1, 10, tzinfo=UTC) for tid in ("t2", "t4", "t7")}
    assert reader._written == {tid: hashlib.sha256((items[tid].thread + "\0{}").encode()).hexdigest()
                               for tid in ("t2", "t4", "t7")}
    assert reader.load_threads() == 0  # the same version of the bundle again: nothing to do


def test_taking_in_a_bundle_never_holds_the_whole_of_it_parsed(tmp_path):
    # Parsed whole, a bundle took about 7.8 times its size for a moment (the review measured +123 MiB for a typical 16.1
    # MiB bundle and +414 MiB for the 300 largest threads, 52.8 MB). Item by item, only one item is parsed at a time, so
    # what it needs besides the file itself is a small part of the file.
    big = ("A “curly” 😀 sentence, with a comma and {braces} and \"quotes\". " * 40)[:2400]
    items = {f"t{n:03d}": an_item(n, extraction=json.dumps({"mentions": [big] * 25}, ensure_ascii=False),
                                  thread=json.dumps({"c": [big] * 25}, ensure_ascii=False)) for n in range(60)}
    data = bundle_bytes(items)
    assert len(data) > 3_000_000
    reader = reader_for(tmp_path, data)
    tracemalloc.start()
    try:
        before = tracemalloc.get_traced_memory()[0]
        tracemalloc.reset_peak()
        assert reader.load_threads() == 60
        extra = tracemalloc.get_traced_memory()[1] - before
        tracemalloc.reset_peak()
        before = tracemalloc.get_traced_memory()[0]
        parsed = Bundle.from_json(json.loads(data))
        whole = tracemalloc.get_traced_memory()[1] - before
        del parsed
    finally:
        tracemalloc.stop()
    assert whole > 3 * len(data)  # what the old way took (the test's own yardstick)
    assert extra < 0.25 * len(data)


def test_write_threads_still_takes_a_bundle_made_in_memory(tmp_path):
    folder = tmp_path / "library"
    bundle = Bundle({"t2": an_item(2), "t1": an_item(1), "t3": an_item(3, extraction=None)})
    assert write_threads(bundle, folder, written := {}) == 2
    assert sorted(written) == ["t1", "t2"] and write_threads(bundle, folder, written) == 0


def test_a_library_name_pool_is_a_local_one_and_leaves_no_word_for_ever(tmp_path):
    # sys.intern made the words of the library's names permanent from Python 3.12 (a leak bounded by the vocabulary, but a
    # leak). The index shares its words through its own pool instead, and the pool goes with the index.
    from engine import group_products

    assert "sys.intern(" not in open(group_products.__file__, encoding="utf-8").read()
    word = "zxqvbn" + "wordthatisnew"
    mentions = [group_products.ProductMention("t1", "c1", f"Lodge {word} skillet", "kitchen", "recommend"),
                group_products.ProductMention("t2", "c2", f"Lodge {word} pan", "kitchen", "recommend")]
    index = group_products.library_name_index(mentions)
    words = [w for name in index._names["kitchen"] for w in name if w == word]
    assert len(words) == 2 and words[0] is words[1]
    assert sys.intern(word) is not words[0]  # the word in the index was never interned, so it is not the interned one


# --- Saved checks kept in memory on the site ---

URL1 = "https://www.reddit.com/r/BuyItForLife/comments/1kett01/which_kettle/c1aaaa/"
SAYS = "My Zojirushi kettle has lasted 6 years and still boils perfectly."


def kept_checker(tmp_path, in_memory: bool, fetch=None):
    from engine.tests.test_live_check import Clock, FakeReddit

    clock = Clock()
    reddit = fetch if fetch is not None else FakeReddit()
    live = LiveChecker(cache_dir=tmp_path / "cache", fetch=reddit, clock=clock, sleep=clock.sleep, in_memory=in_memory)
    return live, clock, reddit


def test_a_checker_that_keeps_checks_in_memory_makes_no_files_and_reads_reddit_once(tmp_path):
    live, clock, reddit = kept_checker(tmp_path, in_memory=True)
    assert live.check(URL1, SAYS).status == "ok"
    assert live.check(URL1, SAYS).status == "ok" and len(reddit.asked) == 1
    assert live.saved_count() == 1
    assert not (tmp_path / "cache").exists()


def test_checks_kept_in_memory_answer_every_question_as_checks_kept_in_files_do(tmp_path):
    from engine.tests.test_live_check import FakeReddit, deleted_page, page

    def run(root, in_memory):
        live, clock, reddit = kept_checker(root, in_memory, FakeReddit())
        out = [live.check(URL1, SAYS).status, live.saved_check(URL1, SAYS).status, live.saved_entry(URL1),
               live.checked_at(URL1), live.last_read(URL1), live.saved_text(URL1), live.read_text(URL1)]
        other = URL1.replace("c1aaaa", "c2bbbb")
        live.keep_check(other, "kept another way", clock.now, "bright_data")
        out += [live.saved_entry(other), live.last_read(other), live.checks_made("bright_data")]
        reddit.answer = (200, page("different words"))
        clock.now += timedelta(hours=49)  # past the 48 hours: read again
        out += [live.check(URL1, SAYS).status, live.saved_entry(URL1), live.saved_entry(other), live.last_read(other)]
        gone = URL1.replace("c1aaaa", "c3cccc")
        reddit.answer = (200, deleted_page())
        out += [live.check(gone, SAYS).status, live.read_if_free(gone), live.read_if_free(URL1)]
        bundle, count = live._bundle_data()
        out += [json.loads(bundle)["checks"], count]
        return json.loads(json.dumps(out, default=str))

    assert run(tmp_path / "files", False) == run(tmp_path / "memory", True)


def test_a_bundle_from_the_bucket_is_taken_into_memory_and_the_site_writes_one_the_same_way(tmp_path):
    from engine.tests.test_live_check_bucket import FakeGoogle
    from engine.live_check import Bucket

    google = FakeGoogle()
    made = {}
    for in_memory in (False, True):
        live, clock, reddit = kept_checker(tmp_path / str(in_memory), in_memory)
        live.bucket = Bucket(google.bucket, request=google, clock=lambda: 0.0)
        entries = {f"{n:032x}.json": {"fetched_at": (clock.now - timedelta(hours=n)).isoformat(), "text": f"words {n}"}
                   for n in (1, 20, 47, 50)}
        google.objects.clear()
        google.objects["live_check/bundle.json"] = (1001, json.dumps({"checks": entries}).encode())
        assert live.load_bundle() == 3  # the 50-hour one is never taken
        assert live.saved_count() == 3
        assert live.save_bundle() == 3
        made[in_memory] = json.loads(google.objects["live_check/bundle.json"][1])["checks"]
    assert made[False] == made[True] and sorted(made[True]) == [f"{n:032x}.json" for n in (1, 20, 47)]
    assert not (tmp_path / "True" / "cache").exists()


def test_checks_older_than_48_hours_are_let_go_of_in_memory_whenever_the_bundle_is_made(tmp_path):
    # Nothing ever uses a check over 48 hours old (check, last_read and the bundle all stop at MAX_AGE), so a long-lived
    # server lets them go instead of keeping them for its whole life.
    live, clock, reddit = kept_checker(tmp_path, in_memory=True)
    for n, hours in enumerate((1, 30, 47, 49, 80)):
        live.keep_check(URL1.replace("c1aaaa", f"c{n}xxxx"), f"words {n}", clock.now - timedelta(hours=hours), "bright_data")
    live._keep("0" * 32 + ".json", b"not a check")
    assert live.saved_count() == 6
    _, count = live._bundle_data()
    assert count == 3 and live.saved_count() == 3  # the 49-hour, the 80-hour and the one that is no check
    clock.now += timedelta(hours=2)
    assert live.forget_old_checks() == 1 and live.saved_count() == 2  # the 47-hour one, now 49


def test_checks_kept_as_files_are_not_let_go_of_by_the_bundle(tmp_path):
    # The daily job's folder and Noemi's computer's: nothing there is ever deleted by the program.
    live, clock, reddit = kept_checker(tmp_path, in_memory=False)
    live.keep_check(URL1, "words", clock.now - timedelta(hours=80), "bright_data")
    live._bundle_data()
    assert len(list((tmp_path / "cache").glob("*.json"))) == 1
    assert live.forget_old_checks() == 0 and len(list((tmp_path / "cache").glob("*.json"))) == 1


def test_a_saved_check_in_memory_takes_a_fraction_of_the_page_a_file_takes_on_cloud_run(tmp_path):
    # On Cloud Run the disk is memory and a file takes whole 4 KiB pages. A check is about 300 bytes of words.
    live, clock, reddit = kept_checker(tmp_path, in_memory=True)
    words = "a comment of about three hundred characters " * 7
    tracemalloc.start()
    try:
        before = tracemalloc.get_traced_memory()[0]
        for n in range(5000):
            live.keep_check(URL1.replace("c1aaaa", f"c{n:06d}"), words[:300], clock.now, "bright_data")
        used = tracemalloc.get_traced_memory()[0] - before
    finally:
        tracemalloc.stop()
    assert live.saved_count() == 5000
    assert used / 5000 < 1024  # under a quarter of the 4,096 a file's page takes


def test_the_public_site_with_a_bucket_keeps_its_checks_in_memory_and_nothing_else_does(tmp_path):
    from engine import web
    from engine.live_check import BUCKET_VAR

    on_cloud = web.site_live_checker(True, {BUCKET_VAR: "a-bucket"})
    assert on_cloud.saved_count() == 0 and on_cloud._memory is True
    for public, environ in ((True, {}), (False, {BUCKET_VAR: "a-bucket"}), (False, {}), (True, {BUCKET_VAR: " "})):
        assert web.site_live_checker(public, environ)._memory is False  # this machine's folder, as always


def test_the_image_limits_glibcs_memory_arenas_to_two():
    # Many threads (8 answers at once, the ping's reads, the open model's) each get their own malloc arena on Linux, and
    # memory freed in one is seldom handed back. The review could not measure it on a Mac, and two arenas is the usual
    # setting for a Python server of this kind.
    from pathlib import Path

    docker = (Path(__file__).resolve().parents[2] / "deploy" / "cloudrun" / "Dockerfile").read_text(encoding="utf-8")
    assert "MALLOC_ARENA_MAX=2" in docker.split("RUN mkdir -p /home/user/app")[0]


# --- The expressions made for each product type are kept for the answers' types only ---
#
# The soak's creep was not fragmentation. The compiled expression that finds a type's names inside the names of the other
# types of its category (sources._inside_pattern) is 549 KB for each of the general category's 347 types, and a `cache`
# kept one for every type ever asked about: 31 MB after getting ready, 153 MB after a soak that touched 338 types, up to
# 196 MB for all 446. Two more were the same in kind: _covering_pattern and _covering_phrases (13 and 14 MB for all types),
# and _community_covers, which is tiny (6 Nov 2026: only 2 types have community names, about 1 KiB each, so the 268 MB first
# written here came from building it for types with no community names, which the code never does). A visitor's own words for
# a type the open model names add an entry each, so a long-lived server only ever grew. The answers' own memory keeps
# ANSWERS_KEPT_TYPES types, so these do.

@pytest.mark.parametrize("name", ["_inside_pattern", "_community_covers", "_covering_pattern", "_covering_phrases"])
def test_what_is_made_for_each_product_type_of_a_big_category_is_kept_for_the_answers_types_only(name):
    from engine import config, sources

    assert getattr(sources, name).cache_info().maxsize == config.ANSWERS_KEPT_TYPES == 64


def test_a_type_asked_after_its_expression_was_let_go_gets_the_same_expression():
    from engine import config, sources
    from engine.query import PRODUCT_TYPES

    general = [p for p in PRODUCT_TYPES if p.category == "general"][:config.ANSWERS_KEPT_TYPES + 6]
    assert len(general) == config.ANSWERS_KEPT_TYPES + 6
    makers = {"_inside_pattern": lambda p: sources._inside_pattern(p.name, p.category),
              "_covering_pattern": lambda p: sources._covering_pattern(p.name),
              "_community_covers": lambda p: sources._community_covers(p.name),
              "_covering_phrases": lambda p: sources._covering_phrases(p.name)}
    for name, make in makers.items():
        getattr(sources, name).cache_clear()
        first = {p.name: make(p) for p in general}
        assert getattr(sources, name).cache_info().currsize == config.ANSWERS_KEPT_TYPES  # the first six were let go
        re.purge()  # re's own cache of 512 expressions turns over in a few answers on the site
        for p in general[:6]:
            again = make(p)
            if hasattr(again, "pattern"):
                assert again is not first[p.name] and (again.pattern, again.flags) == (first[p.name].pattern, first[p.name].flags)
            else:
                assert again == first[p.name]  # a frozenset, or None
        last = general[-1]
        assert make(last) is first[last.name] or first[last.name] is None or not hasattr(first[last.name], "pattern")


def test_free_words_for_a_type_cannot_grow_the_expressions_for_ever():
    # A type the open model names in its own words has no entry of the taxonomy's, and each new one was a new expression.
    from engine import config, sources

    sources._inside_pattern.cache_clear()
    for n in range(config.ANSWERS_KEPT_TYPES * 3):
        sources._inside_pattern(f"made up type number {n}", "general")
    assert sources._inside_pattern.cache_info().currsize == config.ANSWERS_KEPT_TYPES
