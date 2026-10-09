"""Loading the gold set: files on disk, how threads connect, and how voice and mention labels match comments."""

import pytest

from engine.gold import DEFAULT_GOLD_DIR, GoldSetError, load_gold_set, load_threads, other_tag_usage
from engine.tests.factories import MENTIONS_HEADER, VOICES_HEADER, make_comment, make_thread, write_gold


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
    voices = VOICES_HEADER + (
        '1fake01,c1aaaa,high,"established member, well upvoted",\n'
        "1fake01,c2bbbb,medium,recent,\n"
        "1fake01,c3cccc,low,salesy language,\n"
    )
    mentions = MENTIONS_HEADER + (
        'c1aaaa,CeraVe Renewing SA Cleanser,skincare,recommend,long-term use,"long-term use, mentions flaws",\n'
        "c3cccc,Paula's Choice 2% BHA,skincare,recommend,no first-hand use,compares alternatives,\n"
    )
    gold = load_gold_set(write_gold(tmp_path, [make_thread()], voices, mentions))
    assert [t.id for t in gold.threads] == ["1fake01"]
    assert [v.comment_id for v in gold.voices] == ["c1aaaa", "c2bbbb", "c3cccc"]
    assert [m.product for m in gold.mentions] == ["CeraVe Renewing SA Cleanser", "Paula's Choice 2% BHA"]


def test_voice_label_without_mentions_means_no_product(tmp_path):
    # c2bbbb was read and rated, and has no rows in mentions.csv: it mentions no product.
    voices = VOICES_HEADER + "1fake01,c2bbbb,medium,recent,\n"
    gold = load_gold_set(write_gold(tmp_path, [make_thread()], voices))
    assert [v.comment_id for v in gold.voices] == ["c2bbbb"] and gold.mentions == []


def test_empty_gold_set_loads(tmp_path):
    gold = load_gold_set(write_gold(tmp_path, []))
    assert gold.threads == [] and gold.voices == [] and gold.mentions == []


def test_comment_lookup(tmp_path):
    gold = load_gold_set(write_gold(tmp_path, [make_thread()]))
    assert gold.comment("c3cccc").body.startswith("Paula's Choice")


# --- Files ---

@pytest.mark.parametrize("missing", ["voices", "mentions"])
def test_missing_label_file(tmp_path, missing):
    assert_one_problem(write_gold(tmp_path, [make_thread()], **{missing: None}), f"{missing}.csv", "missing")


def test_missing_threads_folder(tmp_path):
    (tmp_path / "voices.csv").write_text(VOICES_HEADER)
    (tmp_path / "mentions.csv").write_text(MENTIONS_HEADER)
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


# --- Voice labels against threads ---

def test_voice_for_unknown_comment(tmp_path):
    voices = VOICES_HEADER + "1fake01,c9zzzz,high,recent,\n"
    assert_one_problem(write_gold(tmp_path, [make_thread()], voices), "voices.csv line 2", "c9zzzz")


def test_voice_thread_must_match_the_comment(tmp_path):
    voices = VOICES_HEADER + "1other9,c1aaaa,high,recent,\n"
    assert_one_problem(write_gold(tmp_path, [make_thread()], voices), "voices.csv line 2", "1fake01")


def test_cannot_label_a_deleted_comment(tmp_path):
    thread = make_thread()
    thread["comments"].append(make_comment("c4dddd", body="[deleted]", status="deleted", author=None))
    voices = VOICES_HEADER + "1fake01,c4dddd,high,recent,\n"
    assert_one_problem(write_gold(tmp_path, [thread], voices), "voices.csv line 2", "deleted")


def test_one_voice_label_per_comment(tmp_path):
    voices = VOICES_HEADER + "1fake01,c1aaaa,high,recent,\n1fake01,c1aaaa,low,new account,\n"
    assert_one_problem(write_gold(tmp_path, [make_thread()], voices), "voices.csv line 3", "c1aaaa", "line 2")


def test_invalid_voice_row_reports_its_line(tmp_path):
    voices = VOICES_HEADER + "1fake01,c1aaaa,high,recent,\n1fake01,c3cccc,meh,recent,\n"
    assert_one_problem(write_gold(tmp_path, [make_thread()], voices), "voices.csv line 3", "voice")


def test_labels_of_an_unreadable_thread_add_no_extra_problems(tmp_path):
    # One typo in a thread file must not turn into a false "not in any thread" for each of its labels.
    thread = make_thread()
    del thread["comments"][0]["score"]
    voices = VOICES_HEADER + "1fake01,c1aaaa,high,recent,\n1fake01,c3cccc,low,salesy language,\n"
    mentions = MENTIONS_HEADER + "c1aaaa,CeraVe SA,skincare,recommend,long-term use,long-term use,\n"
    assert_one_problem(write_gold(tmp_path, [thread], voices, mentions), "1fake01.json", "score")


# --- Mention labels ---

VOICE_C1 = VOICES_HEADER + "1fake01,c1aaaa,high,recent,\n"


def test_mention_needs_a_voice_label_first(tmp_path):
    mentions = MENTIONS_HEADER + "c3cccc,Paula's Choice BHA,skincare,recommend,short-term use,vague,\n"
    assert_one_problem(write_gold(tmp_path, [make_thread()], VOICE_C1, mentions), "mentions.csv line 2", "c3cccc", "voices.csv")


def test_mention_for_unknown_comment(tmp_path):
    mentions = MENTIONS_HEADER + "c9zzzz,CeraVe SA,skincare,recommend,long-term use,long-term use,\n"
    assert_one_problem(write_gold(tmp_path, [make_thread()], VOICE_C1, mentions), "mentions.csv line 2", "c9zzzz")


def test_mentions_of_an_invalid_voice_row_add_no_extra_problems(tmp_path):
    voices = VOICES_HEADER + "1fake01,c1aaaa,meh,recent,\n"
    mentions = MENTIONS_HEADER + "c1aaaa,CeraVe SA,skincare,recommend,long-term use,long-term use,\n"
    assert_one_problem(write_gold(tmp_path, [make_thread()], voices, mentions), "voices.csv line 2", "voice")


def test_same_product_twice_for_one_comment(tmp_path):
    mentions = MENTIONS_HEADER + (
        "c1aaaa,CeraVe SA,skincare,recommend,long-term use,long-term use,\n"
        "c1aaaa,cerave sa ,skincare,warn,long-term use,mentions flaws,\n"
    )
    assert_one_problem(write_gold(tmp_path, [make_thread()], VOICE_C1, mentions), "mentions.csv line 3", "already", "line 2")


def test_invalid_mention_row_reports_its_line(tmp_path):
    mentions = MENTIONS_HEADER + "c1aaaa,CeraVe SA,skincare,recommend,forever,long-term use,\n"
    assert_one_problem(write_gold(tmp_path, [make_thread()], VOICE_C1, mentions), "mentions.csv line 2", "evidence")


def test_off_category_mention_loads(tmp_path):
    # End-state tree edge case: a comment that mentions a product outside the category.
    mentions = MENTIONS_HEADER + "c1aaaa,Bodum Chambord French press,other,neutral,no first-hand use,secondhand,\n"
    gold = load_gold_set(write_gold(tmp_path, [make_thread()], VOICE_C1, mentions))
    assert gold.mentions[0].category == "other"


def test_reason_that_fits_no_tag(tmp_path):
    # End-state tree edge case: "other" plus a note loads; "other" alone is reported with its line.
    voices = VOICES_HEADER + "1fake01,c1aaaa,high,other,Moderator of the subreddit\n1fake01,c3cccc,low,other,\n"
    assert_one_problem(write_gold(tmp_path, [make_thread()], voices), "voices.csv line 3", "note")


# --- How often "other" is used ---

def test_other_tag_usage_counts_each_tag_list(tmp_path):
    voices = VOICES_HEADER + (
        "1fake01,c1aaaa,high,other,Moderator of the subreddit\n"
        "1fake01,c2bbbb,medium,recent,\n"
        "1fake01,c3cccc,low,salesy language,\n"
    )
    mentions = MENTIONS_HEADER + "c1aaaa,CeraVe SA,skincare,recommend,long-term use,long-term use,\n"
    voice, evidence = other_tag_usage(load_gold_set(write_gold(tmp_path, [make_thread()], voices, mentions)))
    assert (voice.kind, voice.used, voice.total, voice.notes) == ("voice", 1, 3, ["Moderator of the subreddit"])
    assert (evidence.kind, evidence.used, evidence.total, evidence.notes) == ("evidence", 0, 1, [])


@pytest.mark.parametrize("others, total, needs_work", [(0, 0, False), (1, 10, False), (2, 10, True)])
def test_more_than_one_in_ten_others_means_the_list_needs_work(tmp_path, others, total, needs_work):
    # Brief v4: "if more than 1 in 10 labels use 'other', the list needs work". Exactly 1 in 10 is fine.
    thread = make_thread(comments=[make_comment(f"c{n:05d}") for n in range(total)])
    voices = VOICES_HEADER + "".join(
        f"1fake01,c{n:05d},high,other,note {n}\n" if n < others else f"1fake01,c{n:05d},high,recent,\n" for n in range(total)
    )
    voice, _ = other_tag_usage(load_gold_set(write_gold(tmp_path, [thread], voices)))
    assert voice.needs_work is needs_work


# --- Spreadsheet quirks ---

@pytest.mark.parametrize("file, header", [("voices", VOICES_HEADER), ("mentions", MENTIONS_HEADER)])
def test_missing_column(tmp_path, file, header):
    assert_one_problem(write_gold(tmp_path, [make_thread()], **{file: header.replace("tags,", "")}), f"{file}.csv", "tags")


@pytest.mark.parametrize("file, header", [("voices", VOICES_HEADER), ("mentions", MENTIONS_HEADER)])
def test_unknown_column(tmp_path, file, header):
    assert_one_problem(write_gold(tmp_path, [make_thread()], **{file: header.replace("note", "credibilty")}), f"{file}.csv", "credibilty")


def test_note_column_is_optional(tmp_path):
    voices = "thread_id,comment_id,voice,tags\n1fake01,c1aaaa,high,recent\n"
    assert load_gold_set(write_gold(tmp_path, [make_thread()], voices)).voices[0].note is None


def test_semicolon_csv_from_excel_in_italian(tmp_path):
    # Excel set to Italian separates columns with semicolons, so commas between tags need no quotes.
    voices = VOICES_HEADER.replace(",", ";") + "1fake01;c1aaaa;high;established member, well upvoted;\n"
    mentions = MENTIONS_HEADER.replace(",", ";") + "c1aaaa;CeraVe SA;skincare;recommend;long-term use;long-term use, mentions flaws;\n"
    gold = load_gold_set(write_gold(tmp_path, [make_thread()], voices, mentions))
    assert gold.voices[0].tags == ["established member", "well upvoted"]
    assert gold.mentions[0].tags == ["long-term use", "mentions flaws"]


def test_excel_byte_order_mark_is_ignored(tmp_path):
    write_gold(tmp_path, [make_thread()])
    (tmp_path / "voices.csv").write_text(VOICE_C1, encoding="utf-8-sig")
    assert len(load_gold_set(tmp_path).voices) == 1


def test_blank_rows_are_skipped(tmp_path):
    voices = VOICE_C1 + ",,,,\n\n"
    assert len(load_gold_set(write_gold(tmp_path, [make_thread()], voices)).voices) == 1


def test_unquoted_comma_creates_extra_values(tmp_path):
    voices = VOICES_HEADER + "1fake01,c1aaaa,high,established member, well upvoted,\n"
    assert_one_problem(write_gold(tmp_path, [make_thread()], voices), "voices.csv line 2", "quotes")


# --- Noemi's real gold set ---

def test_real_gold_set_is_valid():
    """Every file in data/gold passes validation. Skipped until the first thread is added."""
    if not any(DEFAULT_GOLD_DIR.joinpath("threads").glob("*.json")):
        pytest.skip("data/gold has no threads yet")
    load_gold_set(DEFAULT_GOLD_DIR)


# --- Threads without labels (how retrieval reads a folder of saved threads) ---

def test_threads_load_from_a_folder_with_any_name(tmp_path):
    # A saved library doesn't have to be called threads/.
    write_gold(tmp_path, [make_thread()])
    library = tmp_path / "library"
    (tmp_path / "threads").rename(library)
    assert [t.id for t in load_threads(library)] == ["1fake01"]


def test_problems_name_the_folder_they_are_in(tmp_path):
    library = tmp_path / "library"
    library.mkdir()
    (library / "1fake01.json").write_text("{not json")
    with pytest.raises(GoldSetError, match="library/1fake01.json"):
        load_threads(library)


# --- Comments with no product, and agreeing replies (Noemi, 8 Oct 2026) ---

def test_a_comment_with_product_mentions_still_needs_a_voice(tmp_path):
    voices = VOICES_HEADER + "1fake01,c1aaaa,,,\n"
    mentions = MENTIONS_HEADER + "c1aaaa,CeraVe SA,skincare,recommend,long-term use,long-term use,\n"
    assert_one_problem(write_gold(tmp_path, [make_thread()], voices, mentions), "mentions.csv line 2", "voice")


def test_read_with_no_product_needs_only_the_row(tmp_path):
    voices = VOICES_HEADER + "1fake01,c3cccc,,,\n"
    gold = load_gold_set(write_gold(tmp_path, [make_thread()], voices))
    assert gold.voices[0].voice is None


def test_only_a_reply_can_agree_with_the_comment_above(tmp_path):
    header = "thread_id,comment_id,voice,tags,note,agrees\n"
    ok = load_gold_set(write_gold(tmp_path, [make_thread()], header + "1fake01,c2bbbb,,,,yes\n"))  # c2bbbb replies to c1aaaa
    assert ok.voices[0].agrees is True
    assert_one_problem(write_gold(tmp_path / "x", [make_thread()], header + "1fake01,c1aaaa,,,,yes\n"), "c1aaaa", "reply")


def test_other_tag_usage_ignores_comments_without_a_voice(tmp_path):
    voices = VOICES_HEADER + "1fake01,c1aaaa,high,other,Moderator\n1fake01,c3cccc,,,\n"
    voice, _ = other_tag_usage(load_gold_set(write_gold(tmp_path, [make_thread()], voices)))
    assert (voice.used, voice.total) == (1, 1)


# --- Kinds of product (Noemi, 9 Oct 2026) ---

def test_a_mention_row_can_be_a_kind_of_product_rather_than_a_brand(tmp_path):
    # Advice about a kind ("a sujihiki", "chemical exfoliant") is labelled like a product, with kind = yes.
    voices = VOICES_HEADER + "1fake01,c1aaaa,high,recent,\n1fake01,c3cccc,high,recent,\n"
    mentions = ("comment_id,product,category,stance,evidence,tags,note,kind\n"
                "c1aaaa,CeraVe SA Cleanser,skincare,recommend,long-term use,long-term use,,\n"
                "c3cccc,chemical exfoliant,skincare,recommend,no first-hand use,vague,,yes\n")
    gold = load_gold_set(write_gold(tmp_path, [make_thread()], voices, mentions))
    assert [(m.product, m.kind) for m in gold.mentions] == [("CeraVe SA Cleanser", False), ("chemical exfoliant", True)]
