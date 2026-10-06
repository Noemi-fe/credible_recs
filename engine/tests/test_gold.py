"""Loading the gold set: files on disk, how threads connect, and how labels match comments."""

import pytest

from engine.gold import DEFAULT_GOLD_DIR, GoldSetError, load_gold_set
from engine.tests.factories import LABELS_HEADER, make_comment, make_thread, write_gold


def problems_for(root) -> list[str]:
    with pytest.raises(GoldSetError) as excinfo:
        load_gold_set(root)
    return excinfo.value.problems


def assert_one_problem(root, *fragments: str):
    problems = problems_for(root)
    assert len(problems) == 1, problems
    for fragment in fragments:
        assert fragment in problems[0], problems[0]


# --- Happy path ---

def test_loads_threads_and_labels(tmp_path):
    labels = LABELS_HEADER + (
        "1fake01,c1aaaa,CeraVe Renewing SA Cleanser,recommend,high,2 years of use and names a downside\n"
        "1fake01,c2bbbb,,,,\n"
        "1fake01,c3cccc,Paula's Choice 2% BHA,recommend,medium,compares alternatives but no duration\n"
    )
    gold = load_gold_set(write_gold(tmp_path, [make_thread()], labels))
    assert [t.id for t in gold.threads] == ["1fake01"]
    assert len(gold.labels) == 3
    assert gold.labels[1].product is None


def test_empty_gold_set_loads(tmp_path):
    gold = load_gold_set(write_gold(tmp_path, []))
    assert gold.threads == [] and gold.labels == []


def test_comment_lookup(tmp_path):
    gold = load_gold_set(write_gold(tmp_path, [make_thread()]))
    assert gold.comment("c3cccc").body.startswith("Paula's Choice")


# --- Files ---

def test_missing_labels_file(tmp_path):
    assert_one_problem(write_gold(tmp_path, [make_thread()], labels=None), "labels.csv", "missing")


def test_missing_threads_folder(tmp_path):
    (tmp_path / "labels.csv").write_text(LABELS_HEADER)
    assert_one_problem(tmp_path, "threads", "missing")


def test_broken_json_reports_file_and_line(tmp_path):
    write_gold(tmp_path, [])
    (tmp_path / "threads" / "1fake01.json").write_text('{\n  "id": "1fake01",\n  "title": "oops"\n  "score": 3\n}')
    assert_one_problem(tmp_path, "1fake01.json", "line 4")


def test_schema_error_reports_file_and_field(tmp_path):
    thread = make_thread()
    del thread["comments"][2]["score"]
    assert_one_problem(write_gold(tmp_path, [thread]), "1fake01.json", "comments.2.score")


def test_file_name_must_match_thread_id(tmp_path):
    write_gold(tmp_path, [make_thread()])
    (tmp_path / "threads" / "1fake01.json").rename(tmp_path / "threads" / "other.json")
    assert_one_problem(tmp_path, "other.json", "1fake01")


def test_reports_every_problem_at_once(tmp_path):
    bad_a = make_thread(community="BuyItForLife")
    bad_b = make_thread(id="1fake02", url="https://www.reddit.com/r/SkincareAddiction/comments/1fake02/x/", comments=[])
    bad_b["category"] = "gadgets"
    assert len(problems_for(write_gold(tmp_path, [bad_a, bad_b]))) == 2


# --- How a thread hangs together ---

def test_subreddit_must_belong_to_the_category(tmp_path):
    assert_one_problem(write_gold(tmp_path, [make_thread(community="BuyItForLife")]), "BuyItForLife", "skincare")


def test_subreddit_check_ignores_case_and_r_prefix(tmp_path):
    gold = load_gold_set(write_gold(tmp_path, [make_thread(community="r/skincareaddiction")]))
    assert gold.threads[0].community == "skincareaddiction"


def test_duplicate_comment_ids_in_a_thread(tmp_path):
    thread = make_thread()
    thread["comments"].append(make_comment("c1aaaa", body="Pasted twice by mistake."))
    assert_one_problem(write_gold(tmp_path, [thread]), "c1aaaa", "more than once")


def test_reply_must_point_to_a_comment_in_the_thread(tmp_path):
    thread = make_thread()
    thread["comments"][1]["parent_id"] = "c9zzzz"
    assert_one_problem(write_gold(tmp_path, [thread]), "c2bbbb", "c9zzzz")


def test_thread_url_must_point_to_the_thread(tmp_path):
    thread = make_thread(url="https://www.reddit.com/r/SkincareAddiction/comments/1other9/x/")
    assert_one_problem(write_gold(tmp_path, [thread]), "url", "1fake01")


def test_comment_url_must_point_to_that_comment(tmp_path):
    # The most likely copy-paste slip: the link of the comment above.
    thread = make_thread()
    thread["comments"][2]["url"] = thread["comments"][1]["url"]
    assert_one_problem(write_gold(tmp_path, [thread]), "c3cccc", "url")


def test_comment_url_must_point_to_this_thread(tmp_path):
    thread = make_thread()
    thread["comments"][0]["url"] = "https://www.reddit.com/r/SkincareAddiction/comments/1other9/comment/c1aaaa/"
    assert_one_problem(write_gold(tmp_path, [thread]), "c1aaaa", "1fake01")


def test_old_style_reddit_comment_url_is_accepted(tmp_path):
    thread = make_thread()
    thread["comments"][0]["url"] = "https://old.reddit.com/r/SkincareAddiction/comments/1fake01/gentle_exfoliant/c1aaaa/?context=3"
    assert load_gold_set(write_gold(tmp_path, [thread]))


def test_nothing_can_be_dated_after_collection(tmp_path):
    thread = make_thread()
    thread["comments"][0]["created_at"] = "2062-03-02"  # typo for 2026
    assert_one_problem(write_gold(tmp_path, [thread]), "c1aaaa", "after")


def test_comment_cannot_predate_its_thread(tmp_path):
    thread = make_thread()
    thread["comments"][0]["created_at"] = "2024-03-02"
    assert_one_problem(write_gold(tmp_path, [thread]), "c1aaaa", "before")


def test_comment_on_the_same_day_as_thread_is_fine_even_without_a_time(tmp_path):
    thread = make_thread(created_at="2025-03-01T21:00:00Z")
    thread["comments"][0]["created_at"] = "2025-03-01"  # midnight if read literally
    assert load_gold_set(write_gold(tmp_path, [thread]))


def test_comment_ids_are_unique_across_threads(tmp_path):
    other = make_thread(
        id="1fake02",
        url="https://www.reddit.com/r/SkincareAddiction/comments/1fake02/x/",
        comments=[make_comment("c1aaaa", thread_id="1fake02")],
    )
    assert_one_problem(write_gold(tmp_path, [make_thread(), other]), "c1aaaa", "1fake01", "1fake02")


# --- Edge cases from the End-state tree (Data and sources) ---

def test_deleted_and_removed_comments_load(tmp_path):
    thread = make_thread()
    thread["comments"].append(make_comment("c4dddd", body="[deleted]", status="deleted", author=None))
    thread["comments"].append(make_comment("c5eeee", body="[removed]", status="removed"))
    gold = load_gold_set(write_gold(tmp_path, [thread]))
    assert {c.status for c in gold.threads[0].comments} == {"ok", "deleted", "removed"}


def test_link_only_and_non_english_comments_load(tmp_path):
    thread = make_thread()
    thread["comments"].append(make_comment("c4dddd", body="https://www.example.com/product/123"))
    thread["comments"].append(make_comment("c5eeee", body="Lo uso da due anni, delicatissimo sulla pelle sensibile."))
    assert len(load_gold_set(write_gold(tmp_path, [thread])).threads[0].comments) == 5


def test_large_thread_loads(tmp_path):
    comments = [make_comment(f"c{n:05d}") for n in range(600)]
    gold = load_gold_set(write_gold(tmp_path, [make_thread(num_comments=812, comments=comments)]))
    assert len(gold.threads[0].comments) == 600


def test_kitchen_thread_loads(tmp_path):
    thread = make_thread(
        id="1kitch1",
        community="BuyItForLife",
        category="kitchen",
        url="https://www.reddit.com/r/BuyItForLife/comments/1kitch1/kettle/",
        comments=[make_comment("k1aaaa", thread_id="1kitch1", url="https://www.reddit.com/r/BuyItForLife/comments/1kitch1/comment/k1aaaa/")],
    )
    assert load_gold_set(write_gold(tmp_path, [thread])).threads[0].category == "kitchen"


# --- Labels against threads ---

def test_label_for_unknown_comment(tmp_path):
    labels = LABELS_HEADER + "1fake01,c9zzzz,CeraVe SA,recommend,high,2 years\n"
    assert_one_problem(write_gold(tmp_path, [make_thread()], labels), "line 2", "c9zzzz")


def test_label_thread_must_match_the_comment(tmp_path):
    labels = LABELS_HEADER + "1other9,c1aaaa,CeraVe SA,recommend,high,2 years\n"
    assert_one_problem(write_gold(tmp_path, [make_thread()], labels), "line 2", "1fake01")


def test_cannot_label_a_deleted_comment(tmp_path):
    thread = make_thread()
    thread["comments"].append(make_comment("c4dddd", body="[deleted]", status="deleted", author=None))
    labels = LABELS_HEADER + "1fake01,c4dddd,CeraVe SA,recommend,high,2 years\n"
    assert_one_problem(write_gold(tmp_path, [thread], labels), "line 2", "deleted")


def test_one_credibility_per_comment(tmp_path):
    labels = LABELS_HEADER + (
        "1fake01,c1aaaa,CeraVe SA,recommend,high,2 years\n"
        "1fake01,c1aaaa,Paula's Choice BHA,warn,low,2 years\n"
    )
    assert_one_problem(write_gold(tmp_path, [make_thread()], labels), "line 3", "c1aaaa", "high")


def test_same_product_twice_for_one_comment(tmp_path):
    labels = LABELS_HEADER + (
        "1fake01,c1aaaa,CeraVe SA,recommend,high,2 years\n"
        "1fake01,c1aaaa,cerave sa ,warn,high,2 years\n"
    )
    assert_one_problem(write_gold(tmp_path, [make_thread()], labels), "line 3", "already")


def test_no_product_row_cannot_sit_beside_product_rows(tmp_path):
    labels = LABELS_HEADER + (
        "1fake01,c1aaaa,CeraVe SA,recommend,high,2 years\n"
        "1fake01,c1aaaa,,,,\n"
    )
    assert_one_problem(write_gold(tmp_path, [make_thread()], labels), "line 3", "no product")


def test_labels_of_an_unreadable_thread_add_no_extra_problems(tmp_path):
    # One typo in a thread file must not turn into a false "not in any thread" for each of its labels.
    thread = make_thread()
    del thread["comments"][0]["score"]
    labels = LABELS_HEADER + (
        "1fake01,c1aaaa,CeraVe SA,recommend,high,2 years\n"
        "1fake01,c3cccc,Paula's Choice BHA,recommend,medium,compares 3\n"
    )
    assert_one_problem(write_gold(tmp_path, [thread], labels), "1fake01.json", "score")


def test_invalid_label_row_reports_its_line(tmp_path):
    labels = LABELS_HEADER + (
        "1fake01,c1aaaa,CeraVe SA,recommend,high,2 years\n"
        "1fake01,c3cccc,Paula's Choice BHA,meh,high,compares 3\n"
    )
    assert_one_problem(write_gold(tmp_path, [make_thread()], labels), "line 3", "stance")


# --- Spreadsheet quirks ---

def test_missing_column(tmp_path):
    labels = "thread_id,comment_id,product,stance,reason\n"
    assert_one_problem(write_gold(tmp_path, [make_thread()], labels), "credibility")


def test_unknown_column(tmp_path):
    labels = "thread_id,comment_id,product,stance,credibility,reason,credibilty\n"
    assert_one_problem(write_gold(tmp_path, [make_thread()], labels), "credibilty")


def test_optional_notes_column(tmp_path):
    labels = "thread_id,comment_id,product,stance,credibility,reason,notes\n1fake01,c1aaaa,CeraVe SA,recommend,high,2 years,check formula year\n"
    assert load_gold_set(write_gold(tmp_path, [make_thread()], labels)).labels[0].notes == "check formula year"


def test_semicolon_csv_from_excel_in_italian(tmp_path):
    labels = LABELS_HEADER.replace(",", ";") + "1fake01;c1aaaa;CeraVe SA;recommend;high;2 years, names a downside\n"
    gold = load_gold_set(write_gold(tmp_path, [make_thread()], labels))
    assert gold.labels[0].reason == "2 years, names a downside"


def test_excel_byte_order_mark_is_ignored(tmp_path):
    write_gold(tmp_path, [make_thread()])
    (tmp_path / "labels.csv").write_text(LABELS_HEADER + "1fake01,c1aaaa,CeraVe SA,recommend,high,2 years\n", encoding="utf-8-sig")
    assert len(load_gold_set(tmp_path).labels) == 1


def test_blank_rows_are_skipped(tmp_path):
    labels = LABELS_HEADER + "1fake01,c1aaaa,CeraVe SA,recommend,high,2 years\n,,,,,\n\n"
    assert len(load_gold_set(write_gold(tmp_path, [make_thread()], labels)).labels) == 1


def test_unquoted_comma_creates_extra_values(tmp_path):
    labels = LABELS_HEADER + "1fake01,c1aaaa,CeraVe SA,recommend,high,2 years, names a downside\n"
    assert_one_problem(write_gold(tmp_path, [make_thread()], labels), "line 2", "quotes")


# --- Noemi's real gold set ---

def test_real_gold_set_is_valid():
    """Every file in data/gold passes validation. Skipped until the first thread is added."""
    if not any(DEFAULT_GOLD_DIR.joinpath("threads").glob("*.json")):
        pytest.skip("data/gold has no threads yet")
    load_gold_set(DEFAULT_GOLD_DIR)
