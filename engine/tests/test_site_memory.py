"""The live site's memory, bounded so 2 GiB fits again (5 Nov 2026, Noemi's "Let's do A").

The site had run at 4 GiB since 15 Oct 2026, a stopgap. Measured on 5 Nov 2026 (CLAUDE.md, DECISIONS.md): at 4 GiB it used
1.9 to 2.0 GiB, growing about 0.03 GiB a day with the library, so at 2 GiB it would run out within hours. These tests hold
each bound that brings it under 80% of 2 GiB. None changes an answer: every bound only decides what is kept in memory,
and an answer worked out again is the same answer.

Every library, request and comment here is made up. Nothing reads data/.
"""

import copy
import json

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
