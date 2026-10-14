"""The bulk import: threads chosen from Arctic Shift's per-subreddit history files (Noemi, 14 Oct 2026).

Every test writes its own small history files, compressed as the real ones are, with made-up posts and comments, and a
library in a temporary folder. Nothing reaches the network.
"""

import json
import os
from datetime import UTC, datetime

import pytest

zstandard = pytest.importorskip("zstandard")

from engine import bulk_import, library, query  # noqa: E402
from engine.bulk_import import (  # noqa: E402
    build_thread,
    delete_raw,
    import_dump,
    raw_files,
    read_lines,
    save_new,
)
from engine.gold import load_threads  # noqa: E402
from engine.models import Thread  # noqa: E402
from engine.tests.factories import make_thread  # noqa: E402

T2021 = int(datetime(2021, 3, 1, 9, tzinfo=UTC).timestamp())
DAY = 86400
NOW = datetime(2026, 10, 14, 3, 0, tzinfo=UTC)


# --- Made-up history files ---

def post(pid, title, sub="BuyItForLife", **overrides) -> dict:
    """A post as the submissions files hold it: Reddit's own field names, with fields the library never keeps."""
    record = {
        "id": pid, "subreddit": sub, "title": title, "selftext": "Made-up post text.", "author": "test_op",
        "author_flair_text": "Not kept", "created_utc": T2021, "retrieved_on": T2021 + 30 * DAY, "score": 40,
        "num_comments": 30, "permalink": f"/r/{sub}/comments/{pid}/made_up_title/", "link_flair_text": None,
        "removed_by_category": None, "url": "https://example.com/not-kept", "over_18": False,
    }
    record.update(overrides)
    return record


def comment(cid, pid, parent=None, body="A made-up comment.", score=5, sub="BuyItForLife", **overrides) -> dict:
    """A comment as the comments files hold it: parent ids with their t1_/t3_ prefix."""
    record = {
        "id": cid, "link_id": f"t3_{pid}", "parent_id": parent or f"t3_{pid}", "body": body, "author": f"user_{cid}",
        "author_flair_text": "Not kept", "created_utc": T2021 + 3600, "score": score, "subreddit": sub,
        "retrieved_on": T2021 + 30 * DAY, "controversiality": 0,
    }
    record.update(overrides)
    return record


def write_zst(path, records, window_log=None):
    """Records as one zstandard stream of NDJSON lines, written as the real files are (no size in the frame)."""
    data = "".join(json.dumps(r) + "\n" for r in records).encode("utf-8")
    params = (zstandard.ZstdCompressionParameters.from_level(3, window_log=window_log) if window_log else None)
    compressor = zstandard.ZstdCompressor(compression_params=params) if params else zstandard.ZstdCompressor(level=3)
    with path.open("wb") as fh:
        with compressor.stream_writer(fh, closefd=False) as writer:
            writer.write(data)


def write_subreddit(folder, sub, posts, comments=()):
    folder.mkdir(parents=True, exist_ok=True)
    write_zst(folder / f"{sub}_submissions.zst", posts)
    write_zst(folder / f"{sub}_comments.zst", list(comments))


def run(files, lib, **kwargs):
    kwargs.setdefault("now", NOW)
    kwargs.setdefault("never", set())
    kwargs.setdefault("workers", 1)
    return import_dump(files, lib, **kwargs)


def chosen_ids(result, type_name):
    return {p["id"] for p in result.type_plan(type_name).chosen}


def some_comments(pid, n=3, **overrides):
    return [comment(f"{pid}c{i}", pid, score=10 - i, **overrides) for i in range(n)]


@pytest.fixture
def lib(tmp_path):
    folder = tmp_path / "library"
    (folder / "threads").mkdir(parents=True)
    return folder


# --- Reading the files ---

def test_a_file_needing_a_large_window_is_read_as_a_stream(tmp_path):
    path = tmp_path / "BuyItForLife_submissions.zst"
    write_zst(path, [post("1aaa01", "Which electric kettle lasts?")], window_log=28)
    with path.open("rb") as fh, pytest.raises(zstandard.ZstdError):  # what a default reader says about such a file
        zstandard.ZstdDecompressor().stream_reader(fh).read()
    assert [json.loads(line)["id"] for line in read_lines(path)] == ["1aaa01"]


def test_only_the_decided_subreddits_files_are_read(tmp_path, lib):
    files = tmp_path / "files"
    write_subreddit(files, "BuyItForLife", [post("1aaa01", "Which electric kettle should I buy?")],
                    some_comments("1aaa01"))
    write_subreddit(files, "cookware", [post("1bbb01", "Which electric kettle should I buy?", sub="cookware")])
    result = run(files, lib, dry_run=True)
    assert result.skipped_files == ["cookware_comments.zst", "cookware_submissions.zst"]
    assert chosen_ids(result, "electric kettle") == {"1aaa01"}


# --- Which posts can be chosen ---

GOOD = "Which electric kettle should I buy?"


@pytest.mark.parametrize("why, record", [
    ("removed by the moderators", post("1x", GOOD, removed_by_category="moderator")),
    ("deleted by its writer", post("1x", GOOD, selftext="[deleted]")),
    ("a deleted title", post("1x", "[deleted by user]")),
    ("posted before 2019", post("1x", GOOD, created_utc=T2021 - 3 * 365 * DAY, retrieved_on=T2021)),
    ("14 comments", post("1x", GOOD, num_comments=14)),
    ("a score of 4", post("1x", GOOD, score=4)),
    ("a recurring thread", post("1x", "Weekly electric kettle questions thread")),
    ("of no kind the library mixes", post("1x", "Look at my new electric kettle")),
    ("not about a product type", post("1x", "Which spatula should I buy?")),
    ("outside the type's subreddits", post("1x", GOOD, sub="Cooking")),
])
def test_a_post_that_isnt_a_good_candidate_is_never_chosen(tmp_path, lib, why, record):
    files = tmp_path / "files"
    write_subreddit(files, record["subreddit"], [record], some_comments("1x", 20))
    result = run(files, lib, dry_run=True)
    assert all(not plan.chosen for plan in result.types), why


def test_advice_long_term_and_warning_threads_about_the_type_are_chosen(tmp_path, lib):
    files = tmp_path / "files"
    posts = [post("1adv01", GOOD), post("1lt0001", "My electric kettle after 12 years"),
             post("1wrn01", "Electric kettle died after 8 months, avoid this one", link_flair_text="Review")]
    write_subreddit(files, "BuyItForLife", posts, [c for p in posts for c in some_comments(p["id"])])
    plan = run(files, lib, dry_run=True).type_plan("electric kettle")
    assert {p["id"]: p["kind"] for p in plan.chosen} == {"1adv01": "advice", "1lt0001": "long_term", "1wrn01": "warning"}
    assert plan.found == {"advice": 1, "long_term": 1, "warning": 1}


def test_a_post_whose_title_doesnt_name_the_type_isnt_chosen(tmp_path, lib):
    # answers read a thread whose post names the type, but the import keeps to threads whose title does: the ones
    # whose comments are about it
    files = tmp_path / "files"
    posts = [post("1body01", "Which one should I buy?", selftext="Thinking of an electric kettle."),
             post("1rcp001", "Favourite electric kettle recipes?")]
    write_subreddit(files, "BuyItForLife", posts, [c for p in posts for c in some_comments(p["id"])])
    assert not chosen_ids(run(files, lib, dry_run=True), "electric kettle")


@pytest.mark.parametrize("title, type_name", [
    # kitchen threads about food or using the gear, not about choosing it (14 Oct 2026, the coordinator's rule)
    ("What should I make first with my new stand mixer?", "stand mixer"),
    ("Easy weeknight meals for a slow cooker?", "slow cooker"),
    ("What's the best thing you've baked in a toaster oven?", "toaster oven"),
    ("Any tips for getting the most out of a microwave?", "microwave"),
    ("What can I add to my rice cooker to make plain rice taste better?", "rice cooker"),
    ("How do I cook fluffy rice without a rice cooker?", "rice cooker"),
    # a general megathread naming the type only in passing
    ("Besides an air fryer, what is the one kitchen gadget you'd buy again?", "air fryer"),
    ("What cooking tool was a waste of money? Mine was an electric kettle", "electric kettle"),
])
def test_food_usage_and_megathread_titles_arent_chosen(tmp_path, lib, title, type_name):
    files = tmp_path / "files"
    write_subreddit(files, "BuyItForLife", [post("1food01", title)], some_comments("1food01"))
    assert not chosen_ids(run(files, lib, dry_run=True), type_name)


@pytest.mark.parametrize("title, type_name", [
    ("Which rice cooker lasts? Any tips for buying one?", "rice cooker"),
    ("Which air fryer should I buy? Mine broke after a year", "air fryer"),
    ("What's your favourite electric kettle that has lasted?", "electric kettle"),
])
def test_buying_questions_with_tips_or_favourites_are_still_chosen(tmp_path, lib, title, type_name):
    files = tmp_path / "files"
    write_subreddit(files, "BuyItForLife", [post("1buy001", title)], some_comments("1buy001"))
    assert chosen_ids(run(files, lib, dry_run=True), type_name) == {"1buy001"}


@pytest.mark.parametrize("title, type_name", [
    ("My parents' microwave looks scorched inside - should I be concerned?", "microwave"),
    ("Is my damaged microwave still safe to use?", "microwave"),
    ("My electric kettle stopped working after a year, why?", "electric kettle"),
    ("Our dishwasher won't drain, how do I fix it?", "dishwasher"),
])
def test_a_question_about_a_fault_with_ones_own_unit_isnt_chosen(tmp_path, lib, title, type_name):
    files = tmp_path / "files"
    write_subreddit(files, "BuyItForLife", [post("1flt001", title)], some_comments("1flt001"))
    result = run(files, lib, dry_run=True)
    assert not chosen_ids(result, type_name)
    assert result.left_out.get("a question about a fault with someone's own unit") == 1


@pytest.mark.parametrize("title, type_name", [
    ("My electric kettle stopped working after a year - which one should I buy?", "electric kettle"),
    ("Our microwave died after 2 years. Recommendations for one that lasts?", "microwave"),
    ("Is a ceramic frying pan safe? Which one would you recommend?", "frying pan"),
])
def test_a_fault_or_safety_question_that_asks_what_to_buy_is_still_chosen(tmp_path, lib, title, type_name):
    files = tmp_path / "files"
    write_subreddit(files, "BuyItForLife", [post("1buy002", title)], some_comments("1buy002"))
    assert chosen_ids(run(files, lib, dry_run=True), type_name) == {"1buy002"}


def test_threads_asking_for_recommendations_are_chosen_before_other_questions(tmp_path, lib, monkeypatch):
    monkeypatch.setattr(bulk_import, "BULK_MAX_NEW_PER_TYPE", 1)
    files = tmp_path / "files"
    posts = [post("1q00001", "Should I bother with an electric kettle in a tiny flat?", num_comments=300, score=900),
             post("1r00001", "Which electric kettle would you recommend?", num_comments=20)]
    write_subreddit(files, "BuyItForLife", posts, [c for p in posts for c in some_comments(p["id"])])
    assert chosen_ids(run(files, lib, dry_run=True), "electric kettle") == {"1r00001"}


def test_a_post_named_by_a_look_alike_isnt_about_the_type(tmp_path, lib):
    files = tmp_path / "files"
    write_subreddit(files, "BuyItForLife", [post("1pot01", "Which crock pot should I buy?")], some_comments("1pot01"))
    result = run(files, lib, dry_run=True)
    assert not chosen_ids(result, "saucepan")


def test_a_post_whose_numbers_hadnt_settled_is_judged_by_its_comments_in_the_file(tmp_path, lib):
    files = tmp_path / "files"
    quick = dict(retrieved_on=T2021 + 600, num_comments=0, score=1)  # saved ten minutes after it was written
    posts = [post("1busy01", GOOD, **quick), post("1quiet1", GOOD, **quick)]
    comments = some_comments("1busy01", 16) + some_comments("1quiet1", 3)
    write_subreddit(files, "BuyItForLife", posts, comments)
    result = run(files, lib, dry_run=True)
    assert chosen_ids(result, "electric kettle") == {"1busy01"}


def test_threads_in_the_library_and_gold_threads_are_never_chosen(tmp_path, lib):
    files = tmp_path / "files"
    posts = [post("1saved1", GOOD), post("1gold01", GOOD), post("1new001", GOOD)]
    write_subreddit(files, "BuyItForLife", posts, [c for p in posts for c in some_comments(p["id"])])
    saved = make_thread(id="1saved1", community="BuyItForLife", category="kitchen", title="Kettle?",
                        url="https://www.reddit.com/r/BuyItForLife/comments/1saved1/x/", comments=[])
    (lib / "threads" / "1saved1.json").write_text(json.dumps(saved), encoding="utf-8")
    result = run(files, lib, dry_run=True, never={"1gold01"})
    assert chosen_ids(result, "electric kettle") == {"1new001"}


def test_a_thread_imported_before_and_set_aside_is_never_chosen_again(tmp_path, lib):
    # Noemi, 14 Oct 2026: off-topic imports are moved to set_aside/ or deleted, and imports.jsonl keeps their ids so they
    # are never imported again
    files = tmp_path / "files"
    posts = [post("1gone01", GOOD), post("1aside1", GOOD), post("1new001", GOOD)]
    write_subreddit(files, "BuyItForLife", posts, [c for p in posts for c in some_comments(p["id"])])
    logged = {"at": "2026-10-14T10:51:30+00:00", "thread_id": "1gone01", "set_aside": "a general megathread",
              "to": "data/library/set_aside/", "extraction_moved": False}
    (lib / "imports.jsonl").write_text(json.dumps(logged) + "\n", encoding="utf-8")
    aside = make_thread(id="1aside1", community="BuyItForLife", category="kitchen", title="Kettle?", comments=[],
                        url="https://www.reddit.com/r/BuyItForLife/comments/1aside1/x/")
    (lib / "set_aside" / "threads").mkdir(parents=True)
    (lib / "set_aside" / "threads" / "1aside1.json").write_text(json.dumps(aside), encoding="utf-8")
    result = run(files, lib, dry_run=True)
    assert chosen_ids(result, "electric kettle") == {"1new001"}
    assert result.left_out["already in the library, set aside before or in the gold set"] == 2


def test_spot_treatments_read_r_acne_and_other_skincare_types_dont(tmp_path, lib):
    files = tmp_path / "files"
    posts = [post("1spot01", "Which pimple patches actually work?", sub="acne"),
             post("1cln001", "Which cleanser should I buy?", sub="acne")]
    write_subreddit(files, "acne", posts, [c for p in posts for c in some_comments(p["id"])])
    result = run(files, lib, dry_run=True)
    assert chosen_ids(result, "spot treatment") == {"1spot01"}
    assert not chosen_ids(result, "cleanser")


# --- How many, and which first ---

def test_a_type_takes_only_the_kinds_it_is_short_of(tmp_path, lib, monkeypatch):
    monkeypatch.setattr(bulk_import, "BULK_TYPE_TARGET", 6)  # 3 advice, 1 long-term use, 2 warnings
    for n in range(3):  # the library already holds 3 advice threads about kettles
        saved = make_thread(id=f"1had{n:03}", community="BuyItForLife", category="kitchen",
                            title=f"Which electric kettle should I get, round {n}?", comments=[],
                            url=f"https://www.reddit.com/r/BuyItForLife/comments/1had{n:03}/x/")
        (lib / "threads" / f"1had{n:03}.json").write_text(json.dumps(saved), encoding="utf-8")
    files = tmp_path / "files"
    in_bifl = [post("1adv01", GOOD), post("1adv02", "Best electric kettle?"),
               post("1lt0001", "My electric kettle after 12 years"), post("1lt0002", "Electric kettle, 15 years later")]
    in_tea = [post("1wrn01", "Electric kettle died after 8 months", sub="tea"),
              post("1wrn02", "Avoid this electric kettle", sub="tea")]
    in_coffee = [post("1wrn03", "Regret buying this electric kettle", sub="Coffee")]
    for sub, posts in (("BuyItForLife", in_bifl), ("tea", in_tea), ("Coffee", in_coffee)):
        write_subreddit(files, sub, posts, [c for p in posts for c in some_comments(p["id"])])
    plan = run(files, lib, dry_run=True).type_plan("electric kettle")
    assert plan.have == {"advice": 3, "long_term": 0, "warning": 0}
    kinds = sorted(p["kind"] for p in plan.chosen)
    assert kinds == ["long_term", "warning", "warning"]


def test_no_type_takes_more_than_its_cap_in_one_run(tmp_path, lib, monkeypatch):
    monkeypatch.setattr(bulk_import, "BULK_MAX_NEW_PER_TYPE", 2)
    files = tmp_path / "files"
    posts = [post(f"1adv{n:02}", f"Which electric kettle should I buy, take {n}?", num_comments=20 + n)
             for n in range(5)]
    write_subreddit(files, "BuyItForLife", posts, [c for p in posts for c in some_comments(p["id"])])
    plan = run(files, lib, dry_run=True).type_plan("electric kettle")
    assert len(plan.chosen) == 2
    assert plan.found == {"advice": 5, "long_term": 0, "warning": 0}


def test_a_request_takes_the_threads_asking_about_its_needs(tmp_path, lib, monkeypatch):
    monkeypatch.setattr(bulk_import, "BULK_PER_REQUEST", 1)
    monkeypatch.setattr(bulk_import, "BULK_TYPE_TARGET", 0)  # no type-level choice: only the request's
    files = tmp_path / "files"
    posts = [post("1fine01", "Best conditioner for fine hair?", sub="curlyhair", num_comments=300),
             post("1curl01", "Best conditioner for curly hair?", sub="curlyhair", num_comments=20)]
    write_subreddit(files, "curlyhair", posts, [c for p in posts for c in some_comments(p["id"], sub="curlyhair")])
    result = run(files, lib, dry_run=True, requests=["conditioner for curly hair"])
    (request,) = result.requests
    assert request.product_type == "conditioner"
    assert [p["id"] for p in request.chosen] == ["1curl01"]


def test_a_general_type_takes_one_library_mix_in_a_run(tmp_path, lib):
    files = tmp_path / "files"
    posts = [post(f"1hp{n:03}", f"Which headphones should I buy, take {n}?", num_comments=20 + n) for n in range(9)]
    write_subreddit(files, "BuyItForLife", posts, [c for p in posts for c in some_comments(p["id"])])
    result = run(files, lib)
    plan = result.type_plan("headphones")
    # its 3 advice threads (no other kind is found), of which at most 2 from one community (engine.sources.choose_mix)
    assert plan.category == "general" and len(plan.chosen) == 2
    assert {t.category for t in load_threads(lib / "threads")} == {"general"}  # not r/BuyItForLife's first, kitchen


def test_a_dry_runs_choice_can_be_carried_out_later(tmp_path, lib):
    files = tmp_path / "files"
    write_subreddit(files, "BuyItForLife", [post("1adv01", GOOD)], tree_comments())
    planned = run(files, lib, dry_run=True)
    assert list((lib / "threads").iterdir()) == []
    done = bulk_import.carry_out(planned, files, lib, now=NOW, never=set(), workers=1)
    assert done.saved == ["1adv01"] and not done.dry_run
    assert (lib / "threads" / "1adv01.json").exists() and (lib / "imports.jsonl").exists()


def test_each_request_gets_its_own_threads_whatever_its_types_cap(tmp_path, lib, monkeypatch):
    monkeypatch.setattr(bulk_import, "BULK_PER_REQUEST", 1)
    monkeypatch.setattr(bulk_import, "BULK_MAX_NEW_PER_TYPE", 1)
    files = tmp_path / "files"
    posts = [post("1grs01", "Best shampoo for greasy hair?", sub="HaircareScience"),
             post("1wvy01", "Best shampoo for wavy hair?", sub="HaircareScience")]
    write_subreddit(files, "HaircareScience", posts,
                    [c for p in posts for c in some_comments(p["id"], sub="HaircareScience")])
    result = run(files, lib, dry_run=True, requests=["shampoo for greasy hair", "gentle shampoo for wavy hair"])
    assert [[p["id"] for p in plan.chosen] for plan in result.requests] == [["1grs01"], ["1wvy01"]]


def test_a_thread_about_two_types_is_chosen_once_and_counts_for_both(tmp_path, lib):
    files = tmp_path / "files"
    both = post("1both01", "Which cleanser and moisturiser should I buy?", sub="SkincareAddiction")
    write_subreddit(files, "SkincareAddiction", [both], some_comments("1both01", sub="SkincareAddiction"))
    result = run(files, lib)
    assert chosen_ids(result, "cleanser") == chosen_ids(result, "moisturiser") == {"1both01"}
    assert result.saved == ["1both01"]


def test_an_html_code_in_a_title_names_no_type(tmp_path, lib):
    # the files write "&" as "&amp;", and its letters are no guitar amp, which "amp" names
    files = tmp_path / "files"
    write_subreddit(files, "BuyItForLife", [post("1amp01", "Which saucepan &amp; lid should I buy?")],
                    some_comments("1amp01"))
    result = run(files, lib, dry_run=True)
    assert chosen_ids(result, "saucepan") == {"1amp01"}
    assert set(result.chosen["1amp01"]["about"]) == {"saucepan"}


@pytest.mark.parametrize("title, category", [
    ("Which gloves last for working in a freezer?", "general"),
    ("Which French press lasts? Mine fits in my carry on bag", "kitchen"),
    ("My freezer stopped working after a year and the fan is noisy", "kitchen"),  # module 1 reads neither: the community's
])
def test_a_thread_about_two_categories_types_takes_the_one_module_1_reads_in_its_title(tmp_path, lib, title,
                                                                                        category):
    # whichever type chose it first (the thinnest go first), a thread is saved where answers about its title read
    files = tmp_path / "files"
    write_subreddit(files, "BuyItForLife", [post("1two01", title)], some_comments("1two01"))
    result = run(files, lib)
    assert len(result.chosen["1two01"]["about"]) == 2
    (thread,) = load_threads(lib / "threads")
    assert thread.category == category


def test_product_types_are_module_1s_as_it_stands_when_the_import_runs():
    # module 1 builds its index of names when it is loaded, so a type merged in later is chosen for by the next run
    problems = []
    names = [q.product_type for q in bulk_import.type_queries(problems=problems)]
    assert names == [p.name for p in query.PRODUCT_TYPES if not any(f"{p.name!r}" in problem for problem in problems)]
    assert {"microwave", "air fryer", "electric kettle", "shampoo"} <= set(names)


def test_a_type_named_on_the_command_line_is_found_by_its_whole_name(tmp_path, lib):
    files = tmp_path / "files"
    posts = [post("1egg01", "Which egg cooker should I buy?"), post("1egg02", "Which egg should I cook first?")]
    write_subreddit(files, "BuyItForLife", posts, [c for p in posts for c in some_comments(p["id"])])
    result = run(files, lib, dry_run=True, extra_types=[("egg cooker", "kitchen")])
    assert chosen_ids(result, "egg cooker") == {"1egg01"}


# --- Building and saving the threads ---

def tree_comments(pid="1adv01"):
    return [
        comment("c1aaaa", pid, score=10),
        comment("c2bbbb", pid, score=50),
        comment("c3cccc", pid, parent="t1_c1aaaa", score=3),
        comment("c4dddd", pid, parent="t1_c3cccc", score=1),
        comment("c5eeee", pid, parent="t1_zzzzzz", body="A reply to a comment the file doesn't hold."),
        comment("c6ffff", pid, body="[deleted]", author="[deleted]", score=2),
        comment("c7gggg", pid, body="[removed]", author="someone", score=1),
        comment("c8hhhh", pid, created_utc=str(T2021 + 7200), score=4, permalink=f"/r/BuyItForLife/comments/{pid}/x/c8hhhh/"),
        comment("c9iiii", pid, body=""),
        comment("cXother", "1other1", body="A comment on another post."),
    ]


def test_a_thread_is_built_in_the_shape_of_an_archive_read():
    thread = build_thread(post("1adv01", GOOD, num_comments=3), tree_comments(), NOW)
    assert isinstance(thread, Thread)
    assert (thread.read_from, thread.checked_live_at, thread.collected_at) == ("arctic_shift", None, NOW)
    assert (thread.community, thread.category, thread.title) == ("BuyItForLife", "kitchen", GOOD)
    assert thread.url == "https://www.reddit.com/r/BuyItForLife/comments/1adv01/made_up_title/"
    # Reddit's "top" order: each comment, then its replies, best first; replies to comments not held are left out, and
    # so are comments with no text or of another post
    assert [c.id for c in thread.comments] == ["c2bbbb", "c1aaaa", "c3cccc", "c4dddd", "c8hhhh", "c6ffff", "c7gggg"]
    by_id = {c.id: c for c in thread.comments}
    assert by_id["c3cccc"].parent_id == "c1aaaa" and by_id["c1aaaa"].parent_id is None
    assert by_id["c8hhhh"].created_at == datetime.fromtimestamp(T2021 + 7200, UTC)  # written as text in the file
    assert by_id["c8hhhh"].url == "https://www.reddit.com/r/BuyItForLife/comments/1adv01/x/c8hhhh/"
    assert by_id["c1aaaa"].url == "https://www.reddit.com/r/BuyItForLife/comments/1adv01/comment/c1aaaa/"
    assert thread.num_comments == 7  # the post said 3 before its comments had come in
    # writers are names only, never their flair or anything else from the file
    assert by_id["c1aaaa"].author.model_dump() == {"name": "user_c1aaaa", "account_created_at": None, "karma": None,
                                                   "flair": None, "contributions": None}
    assert (by_id["c6ffff"].status, by_id["c6ffff"].author) == ("deleted", None)
    assert by_id["c7gggg"].status == "removed"


def test_a_run_saves_new_thread_files_the_library_reads(tmp_path, lib):
    files = tmp_path / "files"
    write_subreddit(files, "BuyItForLife", [post("1adv01", GOOD)], tree_comments())
    result = run(files, lib)
    assert result.saved == ["1adv01"]
    (thread,) = load_threads(lib / "threads")
    assert thread.id == "1adv01" and thread.read_from == "arctic_shift"
    stub = next(c for c in thread.comments if c.id == "c7gggg")
    assert (stub.body, stub.author) == ("[removed]", None)  # a removed comment is a stub, as the library keeps them
    assert not [p for p in (lib / "threads").iterdir() if not p.name.endswith(".json")]  # no temporary file left


def test_a_dry_run_writes_nothing(tmp_path, lib):
    files = tmp_path / "files"
    write_subreddit(files, "BuyItForLife", [post("1adv01", GOOD)], tree_comments())
    result = run(files, lib, dry_run=True)
    assert result.saved == [] and chosen_ids(result, "electric kettle") == {"1adv01"}
    assert list((lib / "threads").iterdir()) == []
    assert not (lib / "requests.jsonl").exists() and not (lib / "imports.jsonl").exists()


def test_an_existing_thread_file_is_never_written_over(lib):
    path = lib / "threads" / "1adv01.json"
    path.write_text("saved by someone else\n", encoding="utf-8")
    thread = build_thread(post("1adv01", GOOD), tree_comments(), NOW)
    assert save_new(thread, lib / "threads") is False
    assert path.read_text(encoding="utf-8") == "saved by someone else\n"
    assert save_new(build_thread(post("1adv02", GOOD), [], NOW), lib / "threads") is True


def test_a_gold_thread_noemi_hasnt_labelled_is_never_saved(lib):
    thread = build_thread(post("1gold01", GOOD), tree_comments("1gold01"), NOW)
    assert save_new(thread, lib / "threads", never={"1gold01"}) is False
    assert not (lib / "threads" / "1gold01.json").exists()


def test_each_run_is_logged_like_library_add_with_each_threads_provenance(tmp_path, lib):
    files = tmp_path / "files"
    write_subreddit(files, "BuyItForLife", [post("1adv01", GOOD)], tree_comments())
    run(files, lib)
    logged = [json.loads(line) for line in (lib / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
    kettle = next(line for line in logged if line["product_type"] == "electric kettle")
    assert kettle["status"] == "ok" and kettle["thread_ids"] == ["1adv01"] and kettle["via"] == "import-dump"
    assert all(line["thread_ids"] for line in logged)  # a type with nothing new isn't logged
    (provenance,) = [json.loads(line) for line in (lib / "imports.jsonl").read_text(encoding="utf-8").splitlines()]
    assert provenance["thread_id"] == "1adv01"
    assert provenance["files"] == ["BuyItForLife_submissions.zst", "BuyItForLife_comments.zst"]
    assert provenance["dump"] == bulk_import.BULK_DUMP and provenance["chosen_for"] == ["electric kettle"]
    assert provenance["kind"] == "advice"


def test_a_missing_comments_file_saves_none_of_that_subreddits_threads(tmp_path, lib):
    files = tmp_path / "files"
    files.mkdir()
    write_zst(files / "BuyItForLife_submissions.zst", [post("1adv01", GOOD)])
    result = run(files, lib)
    assert result.saved == [] and result.missing_comments == ["BuyItForLife"]


# --- The raw files ---

def test_the_raw_files_are_listed_and_deleted_and_nothing_else(tmp_path):
    root = tmp_path / "dumps"
    files = root / "reddit" / "subreddits23"
    write_subreddit(files, "BuyItForLife", [post("1adv01", GOOD)], tree_comments())
    (root / ".abc123.parts").write_bytes(b"pieces of other files")
    (root / "notes.txt").write_text("not a raw file", encoding="utf-8")
    assert sorted(p.name for p in raw_files(root)) == [".abc123.parts", "BuyItForLife_comments.zst",
                                                       "BuyItForLife_submissions.zst"]
    deleted = delete_raw(root)
    assert sorted(p.name for p in deleted) == [".abc123.parts", "BuyItForLife_comments.zst",
                                               "BuyItForLife_submissions.zst"]
    assert raw_files(root) == [] and (root / "notes.txt").exists()


def test_the_command_line_says_whether_raw_files_are_left(tmp_path, capsys):
    root = tmp_path / "dumps"
    write_subreddit(root, "BuyItForLife", [post("1adv01", GOOD)])
    assert bulk_import.main(["raw-files", str(root)]) == 1
    assert "2 raw files" in capsys.readouterr().out
    assert bulk_import.main(["delete-raw", str(root)]) == 0
    assert bulk_import.main(["raw-files", str(root)]) == 0
    assert "none left" in capsys.readouterr().out


def test_library_import_dump_runs_the_import(tmp_path, lib, capsys):
    files = tmp_path / "files"
    write_subreddit(files, "BuyItForLife", [post("1adv01", GOOD)], tree_comments())
    assert library.main(["import-dump", str(files), "--dry-run", "--workers", "1"], folder=lib) == 0
    out = capsys.readouterr().out
    assert "electric kettle" in out and "dry run: nothing saved" in out
    assert list((lib / "threads").iterdir()) == []
    assert library.main(["import-dump", str(files), "--workers", "1"], folder=lib) == 0
    assert (lib / "threads" / "1adv01.json").exists()
    assert os.path.getsize(lib / "imports.jsonl") > 0


def test_library_import_dump_refuses_options_it_doesnt_have(tmp_path, lib, capsys):
    assert library.main(["import-dump", str(tmp_path), "--fast"], folder=lib) == 2
    assert library.main(["import-dump"], folder=lib) == 2
    assert library.main(["import-dump", str(tmp_path), "--type", "air fryer"], folder=lib) == 2  # no category
