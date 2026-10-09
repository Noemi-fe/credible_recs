"""The labelling tool: the page Noemi labels a thread on, and the import that adds its labels to the gold set.

Every test works in a temporary folder with made-up threads from factories.py, so no test reads or writes data/.
"""

import json
import re
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from urllib.parse import urlparse

import pytest

from engine import labelling
from engine.config import (
    EVIDENCE_LEVELS,
    EVIDENCE_TAGS,
    MENTION_CATEGORIES,
    OTHER_TAG,
    STANCE_VALUE,
    VOICE_LEVELS,
    VOICE_TAGS,
)
from engine.gold import GoldSetError, load_gold_set
from engine.labelling import LabellingError, import_labels, write_page
from engine.tests.factories import MENTIONS_HEADER, VOICES_HEADER, make_comment, make_thread, write_gold

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


# --- Helpers for the page ---

def page_for(gold_dir: Path, thread: dict | None = None, guide: str | None = None) -> str:
    """Writes the labelling page for one thread (the made-up 1fake01 by default) and returns its HTML."""
    thread = thread or make_thread()
    write_gold(gold_dir, [thread])
    if guide is not None:
        (gold_dir / "LABELLING_GUIDE.md").write_text(guide, encoding="utf-8")
    return write_page(thread["id"], gold_dir=gold_dir, now=NOW).read_text(encoding="utf-8")


def page_config(html: str) -> dict:
    """The settings the page's script reads: levels, tags, choices and the comments to label."""
    found = re.search(r'<script type="application/json" id="config">(.*?)</script>', html, re.S)
    assert found, "the page has no settings block"
    return json.loads(found.group(1))


def card(html: str, comment_id: str) -> str:
    """The HTML of one comment's card."""
    start = html.index(f'data-id="{comment_id}"')
    return html[start:html.index("</article>", start)]


def thread_with_gone_comments() -> dict:
    """The made-up thread plus a deleted comment, a removed one, and a reply to the deleted one."""
    thread = make_thread()
    thread["comments"] += [
        make_comment("c4dddd", body="[deleted]", status="deleted", author=None),
        make_comment("c5eeee", body="[removed]", status="removed"),
        make_comment("c6ffff", parent_id="c4dddd", body="Answering a comment that is gone now."),
    ]
    return thread


# --- The page: what it shows ---

def test_the_page_is_written_to_the_labelling_folder(tmp_path):
    write_gold(tmp_path, [make_thread()])
    path = write_page("1fake01", gold_dir=tmp_path, now=NOW)
    assert path == tmp_path / "labelling" / "1fake01.html"
    assert path.read_text(encoding="utf-8").startswith("<!doctype html>")


def test_every_usable_comment_can_be_labelled_and_no_deleted_or_removed_one(tmp_path):
    html = page_for(tmp_path, thread_with_gone_comments())
    for comment_id in ("c1aaaa", "c2bbbb", "c3cccc", "c6ffff"):
        assert f'data-id="{comment_id}"' in html
    for comment_id in ("c4dddd", "c5eeee"):
        assert comment_id not in html  # not even a link: nothing of theirs is on the page
    assert [c["id"] for c in page_config(html)["comments"]] == ["c1aaaa", "c2bbbb", "c3cccc", "c6ffff"]


def test_deleted_and_removed_comments_are_shown_greyed_out_without_text_or_author(tmp_path):
    thread = thread_with_gone_comments()
    thread["comments"][4]["body"] = "Text a source should never have kept"
    html = page_for(tmp_path, thread)
    assert html.count('<article class="comment gone"') == 2
    assert "Text a source should never have kept" not in html
    assert "test_user_c5eeee" not in html


def test_comment_text_is_shown_as_text_never_as_html(tmp_path):
    thread = make_thread(title="Is <i>this</i> safe?")
    thread["comments"][0]["body"] = '<script>alert("hi")</script> & <b>bold</b>\nsecond line'
    html = page_for(tmp_path, thread)
    assert "<script>alert" not in html and "<b>bold" not in html and "<i>this" not in html
    assert escape('<script>alert("hi")</script> & <b>bold</b>\nsecond line') in card(html, "c1aaaa")
    assert escape("Is <i>this</i> safe?") in html


def test_line_breaks_in_a_comment_are_kept(tmp_path):
    thread = make_thread()
    thread["comments"][0]["body"] = "First paragraph.\n\nSecond paragraph."
    assert "First paragraph.\n\nSecond paragraph." in card(page_for(tmp_path, thread), "c1aaaa")


def test_levels_tags_and_choices_come_from_config(tmp_path, monkeypatch):
    monkeypatch.setattr(labelling, "VOICE_TAGS", VOICE_TAGS + ("made-up voice tag",))
    monkeypatch.setattr(labelling, "EVIDENCE_TAGS", EVIDENCE_TAGS + ("made-up evidence tag",))
    config = page_config(page_for(tmp_path))
    assert config["voiceLevels"] == list(VOICE_LEVELS)
    assert config["evidenceLevels"] == list(EVIDENCE_LEVELS)
    assert config["voiceTags"] == list(VOICE_TAGS) + ["made-up voice tag"]
    assert config["evidenceTags"] == list(EVIDENCE_TAGS) + ["made-up evidence tag"]
    assert config["otherTag"] == OTHER_TAG
    assert config["categories"] == list(MENTION_CATEGORIES)
    assert config["stances"] == list(STANCE_VALUE)


def test_a_new_product_starts_in_the_threads_category(tmp_path):
    thread = make_thread(
        id="1kitch1",
        community="BuyItForLife",
        category="kitchen",
        url="https://www.reddit.com/r/BuyItForLife/comments/1kitch1/kettle/",
        comments=[make_comment("k1aaaa", thread_id="1kitch1", url="https://www.reddit.com/r/BuyItForLife/comments/1kitch1/comment/k1aaaa/")],
    )
    config = page_config(page_for(tmp_path, thread))
    assert (config["threadId"], config["threadCategory"]) == ("1kitch1", "kitchen")


def test_a_comment_with_no_product_needs_no_voice_label():
    # Noemi, 8 Oct 2026: no metric uses the voice of a comment with no product, and skipping it saves time.
    assert labelling.VOICE_REQUIRED_WITHOUT_PRODUCT is False


@pytest.mark.parametrize("required, written", [(True, "true"), (False, "false")])
def test_the_page_follows_the_same_voice_rule_switch_as_the_import(tmp_path, monkeypatch, required, written):
    monkeypatch.setattr(labelling, "VOICE_REQUIRED_WITHOUT_PRODUCT", required)
    assert f"const VOICE_REQUIRED_WITHOUT_PRODUCT = {written};" in page_for(tmp_path)


def test_only_replies_can_be_marked_as_agreeing_with_the_comment_above(tmp_path):
    config = page_config(page_for(tmp_path))
    assert {c["id"]: c["reply"] for c in config["comments"]} == {"c1aaaa": False, "c2bbbb": True, "c3cccc": False}


def test_the_only_web_links_are_to_reddit(tmp_path):
    html = page_for(tmp_path, guide="Read the README first.")
    urls = re.findall(r"https?://[^\s\"'<>]+", html)
    assert "https://www.reddit.com/r/SkincareAddiction/comments/1fake01/gentle_exfoliant/" in urls
    assert "https://www.reddit.com/user/test_user_c1aaaa" in urls
    hosts = {urlparse(url).hostname for url in urls}
    assert all(host == "reddit.com" or host.endswith(".reddit.com") for host in hosts), hosts
    # Nothing is loaded from anywhere: no scripts, images, stylesheets or fonts from a link.
    assert " src=" not in html and "url(" not in html and "@import" not in html and "<link" not in html


def test_the_header_names_the_thread_and_counts_the_comments_to_label(tmp_path):
    html = page_for(tmp_path, thread_with_gone_comments())
    assert "Gentle exfoliant for sensitive skin?" in html
    assert "r/SkincareAddiction" in html
    assert "1 Mar 2025" in html
    assert 'href="https://www.reddit.com/r/SkincareAddiction/comments/1fake01/gentle_exfoliant/"' in html
    assert "0 of 4 comments labelled" in html  # the deleted and removed ones don't count


def test_the_header_lists_the_keyboard_shortcuts(tmp_path):
    html = page_for(tmp_path)
    for key in ("j", "k", "1", "2", "3", "n", "a", "p"):
        assert f"<kbd>{key}</kbd>" in html


def test_each_comment_shows_its_author_flair_score_and_date(tmp_path):
    shown = card(page_for(tmp_path), "c1aaaa")
    assert 'href="https://www.reddit.com/user/test_user_c1aaaa"' in shown
    assert "u/test_user_c1aaaa" in shown
    assert "Dry/sensitive" in shown
    assert "12 points" in shown
    assert "2 Mar 2025" in shown and "1 year ago" in shown
    assert "account since Jun 2018" in shown and "5,000 karma" in shown
    assert 'href="https://www.reddit.com/r/SkincareAddiction/comments/1fake01/comment/c1aaaa/"' in shown


def test_a_deleted_account_is_named_as_such_with_no_profile_link(tmp_path):
    thread = make_thread()
    thread["comments"][2]["author"] = None
    shown = card(page_for(tmp_path, thread), "c3cccc")
    assert "deleted account" in shown and "/user/" not in shown


def test_replies_sit_under_their_parent_in_thread_order(tmp_path):
    # The reply is listed last in the file but belongs right after the comment it answers.
    thread = make_thread()
    reply = thread["comments"].pop(1)
    thread["comments"].append(reply)
    html = page_for(tmp_path, thread)
    assert html.index('data-id="c1aaaa"') < html.index('data-id="c2bbbb"') < html.index('data-id="c3cccc"')
    assert 'data-depth="1"' in card(html, "c2bbbb") and 'data-depth="0"' in card(html, "c3cccc")


def test_a_reply_shows_the_start_of_the_comment_it_answers(tmp_path):
    shown = card(page_for(tmp_path), "c2bbbb")
    assert "u/test_user_c1aaaa" in shown
    assert escape("I've used the CeraVe SA Cleanser for 2 years.") in shown


def test_a_long_parent_is_cut_to_about_120_characters(tmp_path):
    thread = make_thread()
    thread["comments"][0]["body"] = "word " * 100
    shown = card(page_for(tmp_path, thread), "c2bbbb")
    excerpt = re.search(r'class="parent-text">(.*?)<', shown, re.S).group(1)
    assert excerpt.endswith("…") and 100 <= len(excerpt) <= 122


def test_a_reply_to_a_deleted_comment_says_so(tmp_path):
    assert "[deleted]" in card(page_for(tmp_path, thread_with_gone_comments()), "c6ffff")


def test_the_guide_is_shown_as_plain_text_when_it_exists(tmp_path):
    html = page_for(tmp_path, guide="# Guide\nTick <other> only when nothing fits.")
    assert "<details" in html and escape("Tick <other> only when nothing fits.") in html


def test_no_guide_panel_without_the_guide_file(tmp_path):
    assert "<details" not in page_for(tmp_path)


# --- The page from the command line ---

def test_command_line_page_prints_where_it_wrote_the_page(tmp_path, capsys):
    write_gold(tmp_path, [make_thread()])
    opened = []
    assert labelling.main(["page", "1fake01"], gold_dir=tmp_path, open_page=opened.append) == 0
    assert str(tmp_path / "labelling" / "1fake01.html") in capsys.readouterr().out
    assert opened == []


def test_command_line_page_opens_it_with_open(tmp_path):
    write_gold(tmp_path, [make_thread()])
    opened = []
    assert labelling.main(["page", "--open", "1fake01"], gold_dir=tmp_path, open_page=opened.append) == 0
    assert opened == [tmp_path / "labelling" / "1fake01.html"]


def test_command_line_page_accepts_a_reddit_link(tmp_path):
    write_gold(tmp_path, [make_thread()])
    link = "https://www.reddit.com/r/SkincareAddiction/comments/1fake01/gentle_exfoliant/"
    assert labelling.main(["page", link], gold_dir=tmp_path, open_page=lambda path: None) == 0
    assert (tmp_path / "labelling" / "1fake01.html").is_file()


def test_command_line_page_for_a_thread_not_in_the_gold_set(tmp_path, capsys):
    write_gold(tmp_path, [make_thread()])
    assert labelling.main(["page", "1zzzzz"], gold_dir=tmp_path) == 1
    out = capsys.readouterr().out
    assert "1zzzzz" in out and "1fake01" in out  # it says which threads there are
    assert not (tmp_path / "labelling").exists()


# --- Helpers for the import ---

def product(name="CeraVe SA Cleanser", category="skincare", stance="recommend", evidence="long-term use",
            tags=("long-term use",), note="", kind=False) -> dict:
    """One product row as the page exports it. kind=True: a kind of product, not a brand (9 Oct 2026)."""
    return {"product": name, "category": category, "stance": stance, "evidence": evidence,
            "evidence_tags": list(tags), "note": note, "kind": kind}


def labelled(comment_id, voice="high", voice_tags=("established member",), voice_note="", mentions=(), no_product=None,
             agrees=False) -> dict:
    """One labelled comment as the page exports it. With no products it is a "no product" comment."""
    return {"comment_id": comment_id, "no_product": not mentions if no_product is None else no_product,
            "voice": voice, "voice_tags": list(voice_tags), "voice_note": voice_note, "agrees": agrees,
            "mentions": list(mentions)}


def exported(*comments, thread_id="1fake01") -> dict:
    return {"thread_id": thread_id, "exported_at": "2026-10-08T10:00:00.000Z", "comments": list(comments)}


def write_labels(folder: Path, labels: dict | str, name: str = "labels_1fake01.json") -> Path:
    path = folder / name
    path.write_text(labels if isinstance(labels, str) else json.dumps(labels), encoding="utf-8")
    return path


def other_thread(thread_id: str = "1fake02") -> dict:
    """A second valid thread, with comment ids of its own."""
    return make_thread(
        id=thread_id,
        url=f"https://www.reddit.com/r/SkincareAddiction/comments/{thread_id}/post/",
        comments=[make_comment(f"{thread_id}c1", thread_id=thread_id, body="My Dualit kettle is 12 years old.")],
    )


# Labels already in the gold set, for the second thread only.
OTHER_VOICES = VOICES_HEADER + '1fake02,1fake02c1,high,"established member, well upvoted",\n'
OTHER_MENTIONS = MENTIONS_HEADER + "1fake02c1,Dualit kettle,kitchen,recommend,long-term use,long-term use,\n"


def gold_folder(tmp_path: Path, voices: str = OTHER_VOICES, mentions: str = OTHER_MENTIONS) -> Path:
    """A gold set with the made-up thread 1fake01 (not labelled yet) and 1fake02 (labelled)."""
    return write_gold(tmp_path / "gold", [make_thread(), other_thread()], voices, mentions)


def label_files(gold: Path) -> tuple[bytes, bytes]:
    return (gold / "voices.csv").read_bytes(), (gold / "mentions.csv").read_bytes()


TWO_COMMENTS = exported(
    labelled(
        "c1aaaa",
        voice_tags=["established member", "well upvoted"],
        mentions=[product(tags=["long-term use", "mentions flaws"], note="Dries her out in winter, says so")],
    ),
    labelled(
        "c3cccc",
        voice="low",
        voice_tags=["other"],
        voice_note="Works for the brand",
        mentions=[product("Paula's Choice 2% BHA, liquid", evidence="no first-hand use", tags=["compares alternatives"])],
    ),
)


# --- Import: what it writes ---

def test_a_valid_export_adds_its_rows_after_the_existing_ones(tmp_path):
    gold = gold_folder(tmp_path)
    result = import_labels(write_labels(tmp_path, TWO_COMMENTS), gold_dir=gold)
    assert (gold / "voices.csv").read_text(encoding="utf-8") == OTHER_VOICES + (
        '1fake01,c1aaaa,high,"established member, well upvoted",\n'
        "1fake01,c3cccc,low,other,Works for the brand\n"
    )
    assert (gold / "mentions.csv").read_text(encoding="utf-8") == OTHER_MENTIONS + (
        'c1aaaa,CeraVe SA Cleanser,skincare,recommend,long-term use,"long-term use, mentions flaws","Dries her out in winter, says so"\n'
        "c3cccc,\"Paula's Choice 2% BHA, liquid\",skincare,recommend,no first-hand use,compares alternatives,\n"
    )
    assert (result.voices_added, result.mentions_added) == (2, 2)
    gold_set = load_gold_set(gold)
    assert [v.comment_id for v in gold_set.voices] == ["1fake02c1", "c1aaaa", "c3cccc"]
    assert gold_set.mentions[2].product == "Paula's Choice 2% BHA, liquid"


def test_a_no_product_comment_adds_a_voice_row_and_no_mention_rows(tmp_path):
    gold = gold_folder(tmp_path)
    import_labels(write_labels(tmp_path, exported(labelled("c2bbbb", voice="medium", voice_tags=["recent"]))), gold_dir=gold)
    assert (gold / "voices.csv").read_text(encoding="utf-8") == OTHER_VOICES + "1fake01,c2bbbb,medium,recent,\n"
    assert (gold / "mentions.csv").read_text(encoding="utf-8") == OTHER_MENTIONS
    assert load_gold_set(gold).mentions[0].comment_id == "1fake02c1"


def test_a_no_product_comment_without_a_voice_is_a_row_with_blank_voice_and_tags(tmp_path):
    gold = gold_folder(tmp_path)
    import_labels(write_labels(tmp_path, exported(labelled("c3cccc", voice=None, voice_tags=[]))), gold_dir=gold)
    assert (gold / "voices.csv").read_text(encoding="utf-8") == OTHER_VOICES + "1fake01,c3cccc,,,\n"
    assert load_gold_set(gold).voices[1].voice is None


def test_a_reply_that_agrees_with_the_comment_above_gets_the_agrees_column(tmp_path):
    # voices.csv has no "agrees" column yet: it is added, and the rows already there stay as they are (blank).
    gold = gold_folder(tmp_path)
    labels = exported(labelled("c2bbbb", voice=None, voice_tags=[], agrees=True),  # c2bbbb replies to c1aaaa
                      labelled("c1aaaa", mentions=[product()]))
    import_labels(write_labels(tmp_path, labels), gold_dir=gold)
    assert (gold / "voices.csv").read_text(encoding="utf-8") == (
        "thread_id,comment_id,voice,tags,note,agrees\n"
        '1fake02,1fake02c1,high,"established member, well upvoted",\n'
        "1fake01,c2bbbb,,,,yes\n"
        "1fake01,c1aaaa,high,established member,,\n"
    )
    voices = load_gold_set(gold).voices
    assert [(v.comment_id, v.agrees) for v in voices] == [("1fake02c1", False), ("c2bbbb", True), ("c1aaaa", False)]


def test_the_agrees_column_is_left_out_when_no_reply_agrees(tmp_path):
    gold = gold_folder(tmp_path)
    import_labels(write_labels(tmp_path, exported(labelled("c2bbbb", voice=None, voice_tags=[]))), gold_dir=gold)
    assert (gold / "voices.csv").read_text(encoding="utf-8").startswith(VOICES_HEADER)


def test_an_agrees_column_already_there_is_filled_in(tmp_path):
    voices = "thread_id,comment_id,voice,tags,note,agrees\n1fake02,1fake02c1,high,recent,,\n"
    gold = gold_folder(tmp_path, voices=voices)
    labels = exported(labelled("c3cccc", voice="low", voice_tags=["salesy language"]), labelled("c2bbbb", voice=None, voice_tags=[], agrees=True))
    import_labels(write_labels(tmp_path, labels), gold_dir=gold)
    assert (gold / "voices.csv").read_text(encoding="utf-8") == voices + "1fake01,c3cccc,low,salesy language,,\n1fake01,c2bbbb,,,,yes\n"


def test_missing_label_files_are_created_with_the_standard_headers(tmp_path):
    gold = write_gold(tmp_path / "gold", [make_thread()], voices=None, mentions=None)
    import_labels(write_labels(tmp_path, TWO_COMMENTS), gold_dir=gold)
    assert (gold / "voices.csv").read_text(encoding="utf-8").startswith("thread_id,comment_id,voice,tags,note,agrees\n1fake01,c1aaaa,high,")
    assert (gold / "mentions.csv").read_text(encoding="utf-8").startswith("comment_id,product,category,stance,evidence,tags,note\nc1aaaa,")
    assert len(load_gold_set(gold).voices) == 2


def test_a_refused_import_leaves_no_new_label_file_behind(tmp_path):
    gold = write_gold(tmp_path / "gold", [make_thread()], voices=None, mentions=None)
    (gold / "threads" / "1fake02.json").write_text("{not json", encoding="utf-8")  # the gold set has a problem elsewhere
    with pytest.raises(LabellingError, match="1fake02.json"):
        import_labels(write_labels(tmp_path, TWO_COMMENTS), gold_dir=gold)
    assert not (gold / "voices.csv").exists() and not (gold / "mentions.csv").exists()


def test_values_are_tidied_the_way_the_gold_set_reads_them(tmp_path):
    gold = gold_folder(tmp_path)
    labels = exported(labelled("c1aaaa", voice="High", voice_tags=["Well  Upvoted"], voice_note="  two   spaces ",
                               mentions=[product(name="  CeraVe   SA ", category="Skincare")]))
    import_labels(write_labels(tmp_path, labels), gold_dir=gold)
    assert (gold / "voices.csv").read_text(encoding="utf-8").endswith("1fake01,c1aaaa,high,well upvoted,two spaces\n")
    assert (gold / "mentions.csv").read_text(encoding="utf-8").endswith("c1aaaa,CeraVe SA,skincare,recommend,long-term use,long-term use,\n")


def test_an_empty_file_with_no_labelled_comment_is_refused(tmp_path):
    gold = gold_folder(tmp_path)
    with pytest.raises(LabellingError, match="no labelled comment"):
        import_labels(write_labels(tmp_path, exported()), gold_dir=gold)


# --- Import: the same thread twice ---

def test_a_second_import_of_the_same_thread_is_refused(tmp_path):
    gold = gold_folder(tmp_path)
    labels = write_labels(tmp_path, TWO_COMMENTS)
    import_labels(labels, gold_dir=gold)
    after_first = label_files(gold)
    with pytest.raises(LabellingError) as refused:
        import_labels(labels, gold_dir=gold)
    assert "already has labels" in str(refused.value) and "--replace" in str(refused.value)
    assert label_files(gold) == after_first


def test_a_thread_labelled_by_hand_counts_as_already_labelled(tmp_path):
    gold = gold_folder(tmp_path, voices=OTHER_VOICES + "1fake01,c2bbbb,medium,recent,\n")
    with pytest.raises(LabellingError, match="already has labels"):
        import_labels(write_labels(tmp_path, TWO_COMMENTS), gold_dir=gold)


def test_replace_swaps_the_threads_rows_and_keeps_the_others(tmp_path):
    gold = gold_folder(tmp_path)
    import_labels(write_labels(tmp_path, TWO_COMMENTS), gold_dir=gold)
    newer = exported(labelled("c2bbbb", voice="medium", voice_tags=["recent"]),
                     labelled("c3cccc", voice="low", voice_tags=["salesy language"], mentions=[product("Paula's Choice 2% BHA")]))
    result = import_labels(write_labels(tmp_path, newer, "newer.json"), gold_dir=gold, replace=True)
    assert (gold / "voices.csv").read_text(encoding="utf-8") == OTHER_VOICES + (
        "1fake01,c2bbbb,medium,recent,\n"
        "1fake01,c3cccc,low,salesy language,\n"
    )
    assert (gold / "mentions.csv").read_text(encoding="utf-8") == OTHER_MENTIONS + (
        "c3cccc,Paula's Choice 2% BHA,skincare,recommend,long-term use,long-term use,\n"
    )
    assert (result.voices_removed, result.mentions_removed) == (2, 2)
    assert result.no_longer_labelled == ["c1aaaa"]  # labelled before, missing from the newer file
    assert len(load_gold_set(gold).voices) == 3


def test_replace_on_a_thread_with_no_labels_yet_just_adds(tmp_path):
    gold = gold_folder(tmp_path)
    result = import_labels(write_labels(tmp_path, TWO_COMMENTS), gold_dir=gold, replace=True)
    assert (result.voices_added, result.voices_removed) == (2, 0)


# --- Import: refused labels ---

@pytest.mark.parametrize("comment, fragments", [
    (labelled("c1aaaa", voice_tags=["famous"]), ["c1aaaa", "famous"]),
    (labelled("c1aaaa", mentions=[product(tags=["loved it"])]), ["c1aaaa", "loved it"]),
    (labelled("c1aaaa", voice_tags=["other"]), ["c1aaaa", "other", "note"]),
    (labelled("c1aaaa", mentions=[product(tags=["other"])]), ["c1aaaa", "CeraVe SA Cleanser", "other", "note"]),
    (labelled("c9zzzz"), ["c9zzzz", "not in thread 1fake01"]),
    (labelled("c4dddd"), ["c4dddd", "deleted"]),
    (labelled("c1aaaa", voice=None, mentions=[product()]), ["c1aaaa", "voice"]),
    (labelled("c1aaaa", voice=None, voice_tags=[], mentions=[product()]), ["c1aaaa", "products", "voice level"]),
    (labelled("c1aaaa", voice_tags=[]), ["c1aaaa", "tag"]),
    (labelled("c3cccc", voice=None, voice_tags=["recent"]), ["c3cccc", "voice"]),
    (labelled("c1aaaa", agrees=True), ["c1aaaa", "reply"]),
    (labelled("c1aaaa", mentions=[product(), product(name="cerave sa cleanser ", stance="warn")]), ["c1aaaa", "twice"]),
    (labelled("c1aaaa", mentions=[product(name="  ")]), ["c1aaaa", "name"]),
    (labelled("c1aaaa", mentions=[product(stance="love")]), ["c1aaaa", "stance"]),
    (labelled("c1aaaa", mentions=[product()], no_product=True), ["c1aaaa", "no product"]),
    (labelled("c1aaaa", no_product=False), ["c1aaaa", "no product"]),
], ids=["unknown voice tag", "unknown evidence tag", "voice other without note", "evidence other without note",
        "comment not in thread", "deleted comment", "tags but no voice level", "products but no voice",
        "voice level but no tag", "no product, tags but no voice", "agrees but not a reply", "same product twice",
        "no product name", "unknown stance", "no product but products", "neither"])
def test_an_invalid_label_is_refused_with_its_reason_and_nothing_is_written(tmp_path, comment, fragments):
    thread = make_thread()
    thread["comments"].append(make_comment("c4dddd", body="[deleted]", status="deleted", author=None))
    gold = write_gold(tmp_path / "gold", [thread, other_thread()], OTHER_VOICES, OTHER_MENTIONS)
    before = label_files(gold)
    # One good comment beside the bad one: a single problem still stops the whole file.
    labels = exported(labelled("c2bbbb", voice="medium", voice_tags=["recent"]), comment)
    with pytest.raises(LabellingError) as refused:
        import_labels(write_labels(tmp_path, labels), gold_dir=gold)
    message = str(refused.value)
    assert "Nothing was written" in message
    for fragment in fragments:
        assert fragment in message
    assert label_files(gold) == before


def test_every_problem_in_the_file_is_listed_at_once(tmp_path):
    gold = gold_folder(tmp_path)
    labels = exported(labelled("c1aaaa", voice_tags=["famous"]), labelled("c9zzzz"))
    with pytest.raises(LabellingError) as refused:
        import_labels(write_labels(tmp_path, labels), gold_dir=gold)
    assert len(refused.value.problems) == 2


def test_the_same_comment_twice_in_one_file_is_refused(tmp_path):
    gold = gold_folder(tmp_path)
    labels = exported(labelled("c2bbbb"), labelled("c2bbbb", voice="low"))
    with pytest.raises(LabellingError, match="c2bbbb.*more than once"):
        import_labels(write_labels(tmp_path, labels), gold_dir=gold)


@pytest.mark.parametrize("text, fragment", [
    ("{not json", "not valid JSON"),
    (json.dumps({"thread_id": "1fake01", "exported_at": "2026-10-08T10:00:00Z"}), "comments"),
    (json.dumps(exported(labelled("c1aaaa"), thread_id="1zzzzz")), "1zzzzz"),
])
def test_a_file_that_isnt_a_labels_export_is_refused(tmp_path, text, fragment):
    gold = gold_folder(tmp_path)
    before = label_files(gold)
    with pytest.raises(LabellingError, match=fragment):
        import_labels(write_labels(tmp_path, text), gold_dir=gold)
    assert label_files(gold) == before


def test_a_missing_labels_file_is_refused(tmp_path):
    with pytest.raises(LabellingError, match="no file"):
        import_labels(tmp_path / "labels_1fake01.json", gold_dir=gold_folder(tmp_path))


# --- Import: the voice rule switch ---

def test_a_no_product_comment_may_still_have_a_voice(tmp_path):
    gold = gold_folder(tmp_path)
    import_labels(write_labels(tmp_path, exported(labelled("c2bbbb", voice="medium", voice_tags=["recent"]))), gold_dir=gold)
    assert load_gold_set(gold).voices[1].voice == "medium"


def test_with_the_voice_rule_on_a_no_product_comment_needs_a_voice(tmp_path, monkeypatch):
    monkeypatch.setattr(labelling, "VOICE_REQUIRED_WITHOUT_PRODUCT", True)
    gold = gold_folder(tmp_path)
    before = label_files(gold)
    with pytest.raises(LabellingError, match="c2bbbb.*voice level"):
        import_labels(write_labels(tmp_path, exported(labelled("c2bbbb", voice=None, voice_tags=[]))), gold_dir=gold)
    assert label_files(gold) == before


# --- Import: keeping the gold set safe ---

def test_a_gold_check_failure_after_writing_puts_the_files_back(tmp_path, monkeypatch):
    gold = gold_folder(tmp_path)
    before = label_files(gold)
    real_check = labelling.load_gold_set

    def check_that_fails_once_written(root):
        if "c1aaaa" in (Path(root) / "voices.csv").read_text(encoding="utf-8"):
            raise GoldSetError(["made-up problem found after writing"])
        return real_check(root)

    monkeypatch.setattr(labelling, "load_gold_set", check_that_fails_once_written)
    with pytest.raises(LabellingError) as refused:
        import_labels(write_labels(tmp_path, TWO_COMMENTS), gold_dir=gold)
    assert "made-up problem found after writing" in str(refused.value)
    assert "back exactly as they were" in str(refused.value)
    assert label_files(gold) == before


def test_a_gold_set_that_already_has_problems_is_left_alone(tmp_path):
    gold = gold_folder(tmp_path, voices=OTHER_VOICES + "1fake02,1fake02c1,meh,recent,\n")
    before = label_files(gold)
    with pytest.raises(LabellingError) as refused:
        import_labels(write_labels(tmp_path, TWO_COMMENTS), gold_dir=gold)
    assert "already has" in str(refused.value) and "voices.csv line 3" in str(refused.value)
    assert label_files(gold) == before


def test_rows_typed_by_hand_are_kept_exactly_as_typed(tmp_path):
    # Extra quotes, a blank line and Windows line endings: kept byte for byte, new rows follow the file's line ending.
    voices = '"thread_id","comment_id","voice","tags","note"\r\n"1fake02","1fake02c1","high","recent",""\r\n\r\n'
    gold = gold_folder(tmp_path, voices=voices)
    import_labels(write_labels(tmp_path, exported(labelled("c2bbbb", voice="medium", voice_tags=["recent"]))), gold_dir=gold)
    assert (gold / "voices.csv").read_bytes() == (voices + "1fake01,c2bbbb,medium,recent,\r\n").encode()
    assert len(load_gold_set(gold).voices) == 2


def test_a_last_row_without_a_line_ending_is_not_joined_to_the_new_row(tmp_path):
    gold = gold_folder(tmp_path, voices=OTHER_VOICES.rstrip("\n"))
    import_labels(write_labels(tmp_path, exported(labelled("c2bbbb", voice="medium", voice_tags=["recent"]))), gold_dir=gold)
    assert (gold / "voices.csv").read_text(encoding="utf-8") == OTHER_VOICES + "1fake01,c2bbbb,medium,recent,\n"


def test_a_semicolon_file_from_excel_in_italian_stays_semicolon(tmp_path):
    voices = VOICES_HEADER.replace(",", ";") + "1fake02;1fake02c1;high;established member, well upvoted;\n"
    mentions = MENTIONS_HEADER.replace(",", ";") + "1fake02c1;Dualit kettle;kitchen;recommend;long-term use;long-term use;\n"
    gold = gold_folder(tmp_path, voices, mentions)
    import_labels(write_labels(tmp_path, TWO_COMMENTS), gold_dir=gold)
    assert (gold / "voices.csv").read_text(encoding="utf-8") == voices + (
        "1fake01;c1aaaa;high;established member, well upvoted;\n"
        "1fake01;c3cccc;low;other;Works for the brand\n"
    )
    gold_set = load_gold_set(gold)
    assert gold_set.mentions[1].tags == ["long-term use", "mentions flaws"]
    assert gold_set.mentions[2].product == "Paula's Choice 2% BHA, liquid"


def test_an_excel_byte_order_mark_is_kept(tmp_path):
    gold = gold_folder(tmp_path)
    (gold / "voices.csv").write_text(OTHER_VOICES, encoding="utf-8-sig")
    import_labels(write_labels(tmp_path, exported(labelled("c2bbbb", voice="medium", voice_tags=["recent"]))), gold_dir=gold)
    assert (gold / "voices.csv").read_text(encoding="utf-8-sig") == OTHER_VOICES + "1fake01,c2bbbb,medium,recent,\n"
    assert (gold / "voices.csv").read_bytes().startswith(b"\xef\xbb\xbf")


def test_a_note_column_is_added_only_when_a_note_needs_it(tmp_path):
    no_note_column = "thread_id,comment_id,voice,tags\n1fake02,1fake02c1,high,recent\n"
    gold = gold_folder(tmp_path, voices=no_note_column)
    import_labels(write_labels(tmp_path, exported(labelled("c2bbbb", voice="medium", voice_tags=["recent"]))), gold_dir=gold)
    assert (gold / "voices.csv").read_text(encoding="utf-8") == no_note_column + "1fake01,c2bbbb,medium,recent\n"

    gold = gold_folder(tmp_path / "second", voices=no_note_column)
    labels = exported(labelled("c2bbbb", voice="medium", voice_tags=["other"], voice_note="Moderator"))
    import_labels(write_labels(tmp_path, labels), gold_dir=gold)
    assert (gold / "voices.csv").read_text(encoding="utf-8") == (
        "thread_id,comment_id,voice,tags,note\n1fake02,1fake02c1,high,recent\n1fake01,c2bbbb,medium,other,Moderator\n"
    )
    assert load_gold_set(gold).voices[1].note == "Moderator"


# --- Import from the command line ---

def test_command_line_import_prints_what_it_added_and_the_gold_summary(tmp_path, capsys):
    gold = gold_folder(tmp_path)
    assert labelling.main(["import", str(write_labels(tmp_path, TWO_COMMENTS))], gold_dir=gold) == 0
    out = capsys.readouterr().out
    assert "2 rows added to voices.csv" in out and "2 rows added to mentions.csv" in out
    assert "Gold set OK" in out and '"other" used in 1 of 3' in out


def test_command_line_import_twice_needs_replace(tmp_path, capsys):
    gold = gold_folder(tmp_path)
    labels = str(write_labels(tmp_path, TWO_COMMENTS))
    assert labelling.main(["import", labels], gold_dir=gold) == 0
    assert labelling.main(["import", labels], gold_dir=gold) == 1
    assert "--replace" in capsys.readouterr().out
    assert labelling.main(["import", "--replace", labels], gold_dir=gold) == 0
    out = capsys.readouterr().out
    assert "removed 2 rows from voices.csv and 2 from mentions.csv" in out
    assert "Gold set OK" in out


def test_command_line_import_names_the_comments_no_longer_labelled_after_replace(tmp_path, capsys):
    gold = gold_folder(tmp_path)
    labelling.main(["import", str(write_labels(tmp_path, TWO_COMMENTS))], gold_dir=gold)
    fewer = write_labels(tmp_path, exported(TWO_COMMENTS["comments"][0]), "fewer.json")
    assert labelling.main(["import", str(fewer), "--replace"], gold_dir=gold) == 0
    assert "c3cccc" in capsys.readouterr().out


def test_command_line_import_of_an_invalid_file_lists_the_problems(tmp_path, capsys):
    gold = gold_folder(tmp_path)
    labels = write_labels(tmp_path, exported(labelled("c1aaaa", voice_tags=["famous"])))
    assert labelling.main(["import", str(labels)], gold_dir=gold) == 1
    out = capsys.readouterr().out
    assert "c1aaaa" in out and "famous" in out


@pytest.mark.parametrize("argv", [[], ["label"], ["page"], ["import"], ["page", "a", "b"], ["import", "x.json", "--force"]])
def test_command_line_without_a_known_command_prints_the_usage(argv, capsys):
    assert labelling.main(argv) == 2
    assert "python -m engine.labelling" in capsys.readouterr().out


# --- Kinds of product, and pages that start from the gold labels (9 Oct 2026) ---

def test_a_product_row_can_be_marked_as_a_kind_not_a_brand(tmp_path):
    assert "kind, not a brand" in page_for(tmp_path)


def test_a_kind_of_product_is_imported_with_the_kind_column(tmp_path):
    gold = gold_folder(tmp_path)
    labels = exported(labelled("c3cccc", mentions=[product("chemical exfoliant", evidence="no first-hand use", tags=["vague"], kind=True)]))
    import_labels(write_labels(tmp_path, labels), gold_dir=gold)
    text = (gold / "mentions.csv").read_text(encoding="utf-8")
    assert text.startswith(MENTIONS_HEADER.rstrip("\n") + ",kind\n")
    assert text.endswith("c3cccc,chemical exfoliant,skincare,recommend,no first-hand use,vague,,yes\n")
    assert load_gold_set(gold).mentions[-1].kind is True


def test_an_export_from_before_kinds_still_imports(tmp_path):
    gold = gold_folder(tmp_path)
    old = product()
    del old["kind"]
    import_labels(write_labels(tmp_path, exported(labelled("c1aaaa", mentions=[old]))), gold_dir=gold)
    assert load_gold_set(gold).mentions[-1].kind is False
    assert (gold / "mentions.csv").read_text(encoding="utf-8").startswith(MENTIONS_HEADER)


def test_a_labelled_threads_page_starts_from_its_gold_labels(tmp_path):
    # So a thread can be opened again to add to its labels, and exporting it never brings back older ones.
    gold = gold_folder(tmp_path)  # 1fake02 is labelled, 1fake01 isn't
    config = page_config(write_page("1fake02", gold_dir=gold, now=NOW).read_text(encoding="utf-8"))
    start = config["goldLabels"]["1fake02c1"]
    assert (start["voice"], start["voice_tags"], start["no_product"]) == ("high", ["established member", "well upvoted"], False)
    assert start["mentions"] == [{"product": "Dualit kettle", "category": "kitchen", "stance": "recommend", "evidence": "long-term use",
                                  "evidence_tags": ["long-term use"], "note": "", "kind": False}]
    assert config["goldVersion"]


def test_an_unlabelled_threads_page_starts_empty(tmp_path):
    config = page_config(write_page("1fake01", gold_dir=gold_folder(tmp_path), now=NOW).read_text(encoding="utf-8"))
    assert (config["goldLabels"], config["goldVersion"]) == ({}, "")


def test_the_gold_version_changes_when_the_labels_change(tmp_path):
    # The browser keeps what was typed under this version: new gold labels mean a fresh start from them.
    first = page_config(write_page("1fake02", gold_dir=gold_folder(tmp_path), now=NOW).read_text(encoding="utf-8"))
    changed = OTHER_MENTIONS.replace("recommend", "warn")
    second = page_config(write_page("1fake02", gold_dir=gold_folder(tmp_path / "b", mentions=changed), now=NOW).read_text(encoding="utf-8"))
    assert first["goldVersion"] != second["goldVersion"]
