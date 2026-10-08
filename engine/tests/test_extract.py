"""Module 3, mention extraction: the files the AI writes, and the checks code runs on them before anything is used.

The AI (Claude Code, following engine/prompts/extract_mentions.md) writes one extraction file per thread. These
tests write such files by hand into temporary folders, next to made-up threads from factories.py, so no test
reads or writes data/.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from engine import extract
from engine.config import MENTION_CATEGORIES, QUOTE_MAX_WORDS, STANCE_VALUE
from engine.extract import (
    CheckResult,
    ExtractedMention,
    Extraction,
    ExtractionError,
    check_extraction,
    current_instructions_version,
    extracted_dir,
    load_checked,
    overall_quote_pass_rate,
    todo,
)
from engine.models import Thread
from engine.tests.factories import make_comment, make_thread, write_gold

VERSION = "extract-v1"
# The made-up thread's comments (factories.make_thread): c1aaaa and c3cccc mention products, c2bbbb doesn't.
CERAVE_BODY = "I've used the CeraVe SA Cleanser for 2 years. Gentle, but it dries me out in winter."
CERAVE_QUOTE = "I've used the CeraVe SA Cleanser for 2 years."
PAULAS_QUOTE = "Paula's Choice 2% BHA beats every acid toner I've tried."


def mention(**overrides) -> dict:
    """One mention as the AI writes it: CeraVe, recommended in comment c1aaaa, with a quote that is really there."""
    fields = {
        "comment_id": "c1aaaa",
        "product": "CeraVe SA Cleanser",
        "category": "skincare",
        "stance": "recommend",
        "quote": CERAVE_QUOTE,
    }
    fields.update(overrides)
    return fields


def make_extraction(**overrides) -> dict:
    """A valid extraction of the made-up thread 1fake01: two mentions, both quoted word for word."""
    fields = {
        "thread_id": "1fake01",
        "instructions_version": VERSION,
        "extracted_at": "2026-10-08T10:00:00Z",
        "extractor": "claude-code",
        "mentions": [mention(), mention(comment_id="c3cccc", product="Paula's Choice 2% BHA", quote=PAULAS_QUOTE)],
    }
    fields.update(overrides)
    return fields


def other_thread(thread_id: str) -> dict:
    """Another valid thread, with comment ids of its own (a comment may belong to one thread only)."""
    return make_thread(
        id=thread_id,
        url=f"https://www.reddit.com/r/SkincareAddiction/comments/{thread_id}/post/",
        comments=[make_comment(f"{thread_id}c1", thread_id=thread_id, body="My Dualit kettle is 12 years old.")],
    )


def threads_folder(tmp_path: Path, *threads: dict) -> Path:
    """A threads/ folder holding these threads (the made-up thread 1fake01 if none are given)."""
    write_gold(tmp_path, list(threads) or [make_thread()], voices=None, mentions=None)
    return tmp_path / "threads"


def write_extraction(threads_dir: Path, extraction: dict | str, name: str | None = None) -> Path:
    """Saves an extraction where the engine looks for it. A string is written as it is, to make a broken file."""
    path = extracted_dir(threads_dir) / f"{name or extraction['thread_id']}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = extraction if isinstance(extraction, str) else json.dumps(extraction, ensure_ascii=False, indent=2)
    path.write_text(text, encoding="utf-8")
    return path


def check(extraction: dict, thread: dict | None = None) -> CheckResult:
    return check_extraction(Extraction.model_validate(extraction), Thread.model_validate(thread or make_thread()))


def reasons(result: CheckResult) -> list[str]:
    return [reason for _, reason in result.rejected]


# --- The extraction file ---

def test_an_extraction_reads_into_the_models():
    extraction = Extraction.model_validate(make_extraction())
    assert extraction.thread_id == "1fake01"
    assert extraction.extracted_at == datetime(2026, 10, 8, 10, 0, tzinfo=UTC)
    assert [m.product for m in extraction.mentions] == ["CeraVe SA Cleanser", "Paula's Choice 2% BHA"]
    assert extraction.mentions[0].stance == "recommend"


def test_an_empty_mention_list_is_valid_and_means_no_product_is_mentioned():
    assert Extraction.model_validate(make_extraction(mentions=[])).mentions == []


@pytest.mark.parametrize("field", ["thread_id", "instructions_version", "extracted_at", "extractor", "mentions"])
def test_every_extraction_field_is_required(field):
    data = make_extraction()
    del data[field]
    with pytest.raises(ValidationError):
        Extraction.model_validate(data)


@pytest.mark.parametrize("bad", [
    {"instructions_version": ""},
    {"instructions_version": "  "},
    {"extractor": ""},
    {"thread_id": "1fake01/../x"},
    {"extracted_at": "yesterday"},
    {"notes": "an unknown field"},
])
def test_an_extraction_with_a_wrong_value_or_unknown_field_is_refused(bad):
    with pytest.raises(ValidationError):
        Extraction.model_validate(make_extraction(**bad))


@pytest.mark.parametrize("bad", [
    {"category": "makeup"},
    {"stance": "love"},
    {"product": ""},
    {"product": "   "},
    {"quote": ""},
    {"quote": " \n"},
    {"comment_id": "c1 aaaa"},
    {"brand": "CeraVe"},
])
def test_a_mention_with_a_wrong_value_or_unknown_field_is_refused(bad):
    with pytest.raises(ValidationError):
        ExtractedMention.model_validate(mention(**bad))


def test_every_mention_category_and_stance_is_accepted():
    for category in MENTION_CATEGORIES:
        for stance in STANCE_VALUE:
            assert ExtractedMention.model_validate(mention(category=category, stance=stance)).stance == stance


def test_the_product_is_kept_as_written():
    assert ExtractedMention.model_validate(mention(product="cerave SA cleanser ")).product == "cerave SA cleanser "


def test_extractions_live_next_to_the_threads_folder():
    assert extracted_dir(Path("data/gold/threads")) == Path("data/gold/extracted")
    assert extracted_dir(Path("data/library/threads")) == Path("data/library/extracted")


# --- Checking one extraction against its thread ---

def test_mentions_quoted_word_for_word_are_kept():
    result = check(make_extraction())
    assert [m.comment_id for m in result.kept] == ["c1aaaa", "c3cccc"]
    assert result.rejected == []
    assert result.quote_pass_rate == 1.0


def test_a_quote_differing_only_in_formatting_is_kept():
    result = check(make_extraction(mentions=[mention(quote="  I’ve used the **CeraVe SA Cleanser**\nfor 2 years.")]))
    assert len(result.kept) == 1


def test_a_comment_not_in_the_thread_is_rejected():
    result = check(make_extraction(mentions=[mention(comment_id="c9zzzz")]))
    assert result.kept == []
    assert len(result.rejected) == 1
    assert "c9zzzz" in reasons(result)[0] and "not in thread 1fake01" in reasons(result)[0]


@pytest.mark.parametrize("status", ["deleted", "removed"])
def test_a_deleted_or_removed_comment_is_rejected_even_if_the_quote_is_there(status):
    thread = make_thread(comments=[make_comment("c1aaaa", body=CERAVE_BODY, status=status)])
    result = check(make_extraction(mentions=[mention()]), thread)
    assert result.kept == []
    assert status in reasons(result)[0] and "c1aaaa" in reasons(result)[0]


def test_a_quote_not_in_its_comment_word_for_word_is_rejected():
    result = check(make_extraction(mentions=[
        mention(quote="I've used the CeraVe SA Cleanser for 3 years."),  # one word changed
        mention(quote="I've used the CeraVe SA Cleanser for 2 years... it dries me out in winter."),  # stitched
        mention(quote="CeraVe is gentle but drying."),  # paraphrased
        mention(comment_id="c2bbbb", quote=CERAVE_QUOTE),  # real words, but from another comment
    ]))
    assert result.kept == []
    assert len(result.rejected) == 4
    assert all("not found word for word" in reason for reason in reasons(result))


def test_a_quote_over_the_word_limit_is_rejected():
    words = [f"word{n}" for n in range(QUOTE_MAX_WORDS + 10)]
    thread = make_thread(comments=[make_comment("c1aaaa", body=" ".join(words))])
    at_limit = " ".join(words[:QUOTE_MAX_WORDS])
    over = " ".join(words[:QUOTE_MAX_WORDS + 1])
    result = check(make_extraction(mentions=[mention(quote=at_limit), mention(quote=over)]), thread)
    assert [m.quote for m in result.kept] == [at_limit]
    assert len(result.rejected) == 1
    assert f"{QUOTE_MAX_WORDS + 1} words" in reasons(result)[0] and f"limit is {QUOTE_MAX_WORDS}" in reasons(result)[0]


def test_an_extraction_of_another_thread_is_rejected_whole():
    result = check(make_extraction(thread_id="1other1"))
    assert result.kept == []
    assert len(result.rejected) == 2
    assert all("1other1" in reason and "1fake01" in reason for reason in reasons(result))


def test_kept_and_rejected_mentions_keep_their_order():
    first, second, third = mention(), mention(quote="made up"), mention(comment_id="c3cccc", quote=PAULAS_QUOTE)
    result = check(make_extraction(mentions=[first, second, third]))
    # exclude_none: instructions v2 (8 Oct 2026) added an optional refers_to field, empty for these mentions.
    assert [m.model_dump(exclude_none=True) for m in result.kept] == [first, third]
    assert [m.model_dump(exclude_none=True) for m, _ in result.rejected] == [second]


def test_quote_pass_rate_is_the_share_of_mentions_kept():
    result = check(make_extraction(mentions=[
        mention(),
        mention(quote="made up"),
        mention(comment_id="c9zzzz"),
        mention(comment_id="c3cccc", quote=PAULAS_QUOTE),
    ]))
    assert result.quote_pass_rate == 0.5


def test_quote_pass_rate_is_none_without_mentions():
    assert check(make_extraction(mentions=[])).quote_pass_rate is None


def test_overall_quote_pass_rate_counts_every_mention_not_every_thread():
    all_kept = check(make_extraction())  # 2 of 2
    one_kept = check(make_extraction(mentions=[mention(), mention(quote="made up"), mention(quote="also made up")]))  # 1 of 3
    none_mentioned = check(make_extraction(mentions=[]))
    assert overall_quote_pass_rate([all_kept, one_kept, none_mentioned]) == pytest.approx(3 / 5)
    assert overall_quote_pass_rate([none_mentioned]) is None
    assert overall_quote_pass_rate([]) is None


# --- Loading a folder of extractions ---

def test_a_valid_extraction_loads_and_passes(tmp_path):
    threads_dir = threads_folder(tmp_path)
    write_extraction(threads_dir, make_extraction())
    results = load_checked(threads_dir)
    assert list(results) == ["1fake01"]
    assert [m.product for m in results["1fake01"].kept] == ["CeraVe SA Cleanser", "Paula's Choice 2% BHA"]
    assert results["1fake01"].rejected == []


def test_only_threads_with_an_extraction_are_in_the_results(tmp_path):
    threads_dir = threads_folder(tmp_path, make_thread(), other_thread("1other1"))
    assert load_checked(threads_dir) == {}  # no extracted/ folder yet
    write_extraction(threads_dir, make_extraction())
    assert list(load_checked(threads_dir)) == ["1fake01"]


def test_a_file_holding_another_threads_extraction_is_rejected_whole(tmp_path):
    threads_dir = threads_folder(tmp_path, make_thread(), other_thread("1other1"))
    write_extraction(threads_dir, make_extraction(thread_id="1other1"), name="1fake01")
    result = load_checked(threads_dir)["1fake01"]
    assert result.kept == []
    assert len(result.rejected) == 2
    assert all("1other1" in reason for reason in reasons(result))


def test_malformed_files_are_all_reported_with_their_names(tmp_path):
    threads_dir = threads_folder(tmp_path, make_thread(), other_thread("1bad001"), other_thread("1bad002"))
    write_extraction(threads_dir, make_extraction())  # fine
    write_extraction(threads_dir, '{"thread_id": "1bad001", ', name="1bad001")
    write_extraction(threads_dir, make_extraction(thread_id="1bad002", mentions=[mention(stance="love")]))
    with pytest.raises(ExtractionError) as error:
        load_checked(threads_dir)
    problems = error.value.problems
    assert len(problems) == 2
    assert problems[0].startswith("extracted/1bad001.json") and "not valid JSON" in problems[0]
    assert problems[1].startswith("extracted/1bad002.json") and "mentions.0.stance" in problems[1]
    assert "extracted/1bad001.json" in str(error.value)


def test_an_extraction_without_its_thread_is_reported(tmp_path):
    threads_dir = threads_folder(tmp_path)
    write_extraction(threads_dir, make_extraction(thread_id="1gone01", mentions=[]))
    with pytest.raises(ExtractionError) as error:
        load_checked(threads_dir)
    assert len(error.value.problems) == 1
    assert error.value.problems[0].startswith("extracted/1gone01.json") and "no thread 1gone01" in error.value.problems[0]


# --- What still needs extracting ---

def test_todo_lists_threads_with_no_extraction_or_an_outdated_one(tmp_path):
    threads_dir = threads_folder(tmp_path, *(other_thread(i) for i in ("1aaaaa", "1bbbbb", "1ccccc")))
    # 1aaaaa: never extracted
    write_extraction(threads_dir, make_extraction(thread_id="1bbbbb", instructions_version="extract-v0", mentions=[]))
    write_extraction(threads_dir, make_extraction(thread_id="1ccccc", mentions=[]))
    assert todo(threads_dir, VERSION) == ["1aaaaa", "1bbbbb"]
    assert todo(threads_dir, "extract-v0") == ["1aaaaa", "1ccccc"]


def test_todo_lists_a_thread_whose_extraction_file_is_broken(tmp_path):
    threads_dir = threads_folder(tmp_path, other_thread("1aaaaa"), other_thread("1bbbbb"))
    write_extraction(threads_dir, "not JSON", name="1aaaaa")
    write_extraction(threads_dir, make_extraction(thread_id="1bbbbb", mentions=[mention(stance="love")]))
    assert todo(threads_dir, VERSION) == ["1aaaaa", "1bbbbb"]


def test_todo_lists_every_thread_before_any_extraction(tmp_path):
    threads_dir = threads_folder(tmp_path, other_thread("1bbbbb"), other_thread("1aaaaa"))
    assert todo(threads_dir, VERSION) == ["1aaaaa", "1bbbbb"]


def test_todo_with_everything_current_is_empty(tmp_path):
    threads_dir = threads_folder(tmp_path)
    write_extraction(threads_dir, make_extraction())
    assert todo(threads_dir, VERSION) == []


def test_todo_of_a_missing_folder_is_an_error(tmp_path):
    with pytest.raises(ExtractionError, match="threads"):
        todo(tmp_path / "threads", VERSION)


# --- The instructions version ---

def test_the_instructions_version_is_the_first_line(tmp_path):
    path = tmp_path / "extract_mentions.md"
    path.write_text("Version: extract-v1\n\n# Extract product mentions\nVersion: not-this-one\n", encoding="utf-8")
    assert current_instructions_version(path) == "extract-v1"


@pytest.mark.parametrize("text", [
    "# Extract product mentions\nVersion: extract-v1\n",  # not on the first line
    "",
    "Version:\n",
    "version extract-v1\n",
])
def test_an_instruction_file_without_its_version_line_is_a_clear_error(tmp_path, text):
    path = tmp_path / "extract_mentions.md"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ExtractionError, match="Version: "):
        current_instructions_version(path)


def test_a_missing_instruction_file_is_a_clear_error(tmp_path):
    with pytest.raises(ExtractionError, match="missing"):
        current_instructions_version(tmp_path / "extract_mentions.md")


def test_the_default_instructions_are_the_extraction_prompt():
    assert extract.DEFAULT_INSTRUCTIONS == Path(extract.__file__).parent / "prompts" / "extract_mentions.md"


# --- Command line ---

def test_command_line_check_prints_each_thread_then_the_totals(tmp_path, capsys):
    threads_dir = threads_folder(tmp_path, make_thread(), other_thread("1other1"))
    write_extraction(threads_dir, make_extraction(mentions=[mention(), mention(comment_id="c9zzzz", product="Made-up Toner")]))
    write_extraction(threads_dir, make_extraction(thread_id="1other1", mentions=[]))
    assert extract.main(["check", str(threads_dir)]) == 0
    out = capsys.readouterr().out
    assert "1fake01: 1 kept, 1 rejected" in out
    assert "CeraVe SA Cleanser" in out
    assert "Made-up Toner" in out and "not in thread 1fake01" in out
    assert "1other1: no products mentioned" in out
    assert "2 mentions: 1 kept, 1 rejected" in out
    assert "Quote pass rate: 50%" in out


def test_command_line_check_exits_1_when_a_file_is_malformed(tmp_path, capsys):
    threads_dir = threads_folder(tmp_path, make_thread(), other_thread("1other1"))
    write_extraction(threads_dir, make_extraction())
    write_extraction(threads_dir, "{", name="1other1")
    assert extract.main(["check", str(threads_dir)]) == 1
    out = capsys.readouterr().out
    assert "1fake01: 2 kept, 0 rejected" in out  # the good file is still checked
    assert "extracted/1other1.json" in out and "not valid JSON" in out


def test_command_line_todo_lists_what_to_extract(tmp_path, capsys):
    instructions = tmp_path / "extract_mentions.md"
    instructions.write_text("Version: extract-v2\n", encoding="utf-8")
    threads_dir = threads_folder(tmp_path, make_thread(), other_thread("1other1"))
    write_extraction(threads_dir, make_extraction())  # made with extract-v1
    assert extract.main(["todo", str(threads_dir)], instructions=instructions) == 0
    out = capsys.readouterr().out
    assert "extract-v2" in out
    assert "1fake01" in out and "extract-v1" in out
    assert "1other1" in out


def test_command_line_todo_with_nothing_left(tmp_path, capsys):
    instructions = tmp_path / "extract_mentions.md"
    instructions.write_text("Version: extract-v1\n", encoding="utf-8")
    threads_dir = threads_folder(tmp_path)
    write_extraction(threads_dir, make_extraction())
    assert extract.main(["todo", str(threads_dir)], instructions=instructions) == 0
    assert "Nothing to extract" in capsys.readouterr().out


def test_command_line_todo_without_instructions_is_an_error(tmp_path, capsys):
    threads_dir = threads_folder(tmp_path)
    assert extract.main(["todo", str(threads_dir)], instructions=tmp_path / "missing.md") == 1
    assert "missing" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [[], ["extract"], ["check", "a", "b"]])
def test_command_line_without_a_known_command_prints_the_usage(argv, capsys):
    assert extract.main(argv) == 2
    assert "python -m engine.extract" in capsys.readouterr().out


# --- Quotes from someone else (7 Oct 2026) ---

@pytest.mark.parametrize("body", [
    "> The Zojirushi kettle died after a year.\n\nReally? Mine is fine after six.",
    "&gt; The Zojirushi kettle died after a year.\n\nReally? Mine is fine after six.",
])
def test_a_quote_from_a_quoted_block_is_someone_elses_words(body):
    # Lines starting with ">" quote another commenter; credit (and credibility) must go to the person who wrote it.
    thread = Thread.model_validate(make_thread(comments=[make_comment("c1aaaa", body=body)]))
    quoted = mention(product="Zojirushi kettle", category="kitchen", stance="warn", quote="The Zojirushi kettle died after a year.")
    own = mention(product="Zojirushi kettle", category="kitchen", stance="recommend", quote="Mine is fine after six.")
    result = check_extraction(Extraction.model_validate(make_extraction(mentions=[quoted, own])), thread)
    assert [m.quote for m in result.kept] == ["Mine is fine after six."]
    assert "quoted" in result.rejected[0][1]


# --- Instructions v2 (8 Oct 2026): replies about a product above, "what to look for" notes, agreements ---

def test_a_reply_about_the_product_above_is_marked_and_kept():
    thread = Thread.model_validate(make_thread(comments=[
        make_comment("c1aaaa", body="The Cuisinart CPK-17 is my pick."),
        make_comment("c2bbbb", parent_id="c1aaaa", body="Had this one 13 years, still going."),
    ]))
    inherited = mention(comment_id="c2bbbb", product="Cuisinart CPK-17", category="kitchen", quote="Had this one 13 years, still going.", refers_to="parent")
    result = check_extraction(Extraction.model_validate(make_extraction(mentions=[inherited])), thread)
    assert result.kept[0].refers_to == "parent"


def test_refers_to_parent_needs_a_reply():
    thread = Thread.model_validate(make_thread())
    wrong = mention(refers_to="parent")  # c1aaaa is a top-level comment
    result = check_extraction(Extraction.model_validate(make_extraction(mentions=[wrong])), thread)
    assert "reply" in result.rejected[0][1]


def test_notes_and_agreements_are_checked_like_mentions():
    thread = Thread.model_validate(make_thread(comments=[
        make_comment("c1aaaa", body="Whatever you buy, get one with no plastic touching the water."),
        make_comment("c2bbbb", parent_id="c1aaaa", body="This! Plastic-free is the way."),
    ]))
    extraction = make_extraction(
        mentions=[],
        notes=[{"comment_id": "c1aaaa", "about": "plastic-free kettle", "stance": "recommend",
                "quote": "get one with no plastic touching the water."},
               {"comment_id": "c1aaaa", "about": "glass kettle", "stance": "recommend", "quote": "glass is best"}],
        agreements=[{"comment_id": "c2bbbb", "quote": "This!"}, {"comment_id": "c1aaaa", "quote": "Whatever you buy"}],
    )
    result = check_extraction(Extraction.model_validate(extraction), thread)
    assert [n.about for n in result.kept_notes] == ["plastic-free kettle"]
    assert "word for word" in result.rejected_notes[0][1]
    assert [a.comment_id for a in result.kept_agreements] == ["c2bbbb"]
    assert "reply" in result.rejected_agreements[0][1]


def test_older_extractions_without_notes_or_agreements_still_load():
    extraction = Extraction.model_validate(make_extraction())
    assert extraction.notes == [] and extraction.agreements == []


# --- The compact reading view the extractor uses (8 Oct 2026) ---

def test_show_lists_usable_comments_compactly_with_reply_context():
    from engine.extract import render_thread

    thread = Thread.model_validate(make_thread(comments=[
        make_comment("c1aaaa", body="The Cuisinart CPK-17 is my pick.", score=40),
        make_comment("c2bbbb", parent_id="c1aaaa", body="Had this one 13 years.", score=12),
        make_comment("c3cccc", body="[deleted]", status="deleted", author=None),
    ]))
    text = render_thread(thread)
    assert "[c1aaaa]" in text and "[c2bbbb]" in text and "c3cccc" not in text
    assert "reply to c1aaaa" in text and "The Cuisinart CPK-17 is my pick." in text
    assert "Gentle exfoliant for sensitive skin?" in text  # the post's title, for context


def test_show_keeps_only_the_highest_scored_comments_in_thread_order():
    from engine.extract import render_thread, shown_comment_ids

    comments = [make_comment(f"c{n:05d}", body=f"Comment {n}", score=n) for n in range(10)]
    thread = Thread.model_validate(make_thread(comments=comments))
    assert shown_comment_ids(thread, max_comments=3) == ["c00007", "c00008", "c00009"]
    assert "3 of 10 comments" in render_thread(thread, max_comments=3)
