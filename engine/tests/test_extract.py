"""Module 3, mention extraction: the files the AI writes, and the checks code runs on them before anything is used.

The AI (Claude Code, following engine/prompts/extract_mentions.md) writes one extraction file per thread. These
tests write such files by hand into temporary folders, next to made-up threads from factories.py, so no test
reads or writes data/.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from engine import extract
from engine.config import EVIDENCE_LEVELS, EVIDENCE_TAGS, MENTION_CATEGORIES, QUOTE_MAX_WORDS, STANCE_VALUE
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


@pytest.mark.parametrize("product_type", ["laser treatment", "Laser", "in-office procedure", "microneedling",
                                          "salon facial", "clinic treatment"])
def test_a_service_is_not_a_product_and_is_rejected(product_type):
    # Instructions v7 say a service ("laser treatments such as Clear and Brilliant, facials, salon or clinic
    # procedures: they're done to you, not bought to use") is never a product, but the AI still listed four laser
    # treatments in one thread (found 10 Oct 2026). The check enforces the instruction for every extraction.
    result = check(make_extraction(mentions=[mention(product_type=product_type), mention(product_type="exfoliant")]))
    assert len(result.kept) == 1 and result.kept[0].product_type == "exfoliant"
    assert "service" in reasons(result)[0] and product_type in reasons(result)[0]


@pytest.mark.parametrize("product_type", ["spot treatment", "acne treatment", "chemical peel", "facial cleanser",
                                          "facial oil", "eye cream", "exfoliant"])
def test_products_with_service_like_words_are_kept(product_type):
    assert len(check(make_extraction(mentions=[mention(product_type=product_type)])).kept) == 1


def test_an_extraction_of_another_thread_is_rejected_whole():
    result = check(make_extraction(thread_id="1other1"))
    assert result.kept == []
    assert len(result.rejected) == 2
    assert all("1other1" in reason and "1fake01" in reason for reason in reasons(result))


def test_kept_and_rejected_mentions_keep_their_order():
    first, second, third = mention(), mention(quote="made up"), mention(comment_id="c3cccc", quote=PAULAS_QUOTE)
    result = check(make_extraction(mentions=[first, second, third]))
    # exclude_defaults: later instructions added optional fields these mentions don't fill in (refers_to in v2;
    # product_type, evidence and evidence_tags in v6, where evidence_tags defaults to an empty list, not None).
    assert [m.model_dump(exclude_defaults=True) for m in result.kept] == [first, third]
    assert [m.model_dump(exclude_defaults=True) for m, _ in result.rejected] == [second]


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


@pytest.mark.parametrize("about", ["laser facials", "Laser", "salon facial", "microneedling"])
def test_a_note_about_a_service_is_rejected(about):
    # Found reading b04, 10 Oct 2026: a moisturiser answer said "Look for: laser facials". A service is never a product
    # (instructions v7), so it is never a kind of product either: notes about one are rejected like mentions.
    thread = Thread.model_validate(make_thread(comments=[
        make_comment("c1aaaa", body="Laser facials helped my dry skin, and so did plain squalane oil."),
    ]))
    extraction = make_extraction(mentions=[], notes=[
        {"comment_id": "c1aaaa", "about": about, "stance": "recommend", "quote": "Laser facials helped my dry skin"},
        {"comment_id": "c1aaaa", "about": "squalane oil", "stance": "recommend", "quote": "plain squalane oil"},
    ])
    result = check_extraction(Extraction.model_validate(extraction), thread)
    assert [n.about for n in result.kept_notes] == ["squalane oil"]
    assert "service" in result.rejected_notes[0][1]


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


# --- Instructions v4 (8 Oct 2026, approved by Noemi) ---

def test_a_product_named_further_up_the_chain_is_marked_earlier():
    # "How did you like it?" then "Loved it": the product is named two comments up, not in the parent.
    thread = Thread.model_validate(make_thread(comments=[
        make_comment("c1aaaa", body="I bought the Cuisinart CPK-17 last year."),
        make_comment("c2bbbb", parent_id="c1aaaa", body="How did you like it?"),
        make_comment("c3cccc", parent_id="c2bbbb", body="Still love it, boils in two minutes."),
    ]))
    earlier = mention(comment_id="c3cccc", product="Cuisinart CPK-17", category="kitchen", quote="Still love it, boils in two minutes.", refers_to="earlier")
    result = check_extraction(Extraction.model_validate(make_extraction(mentions=[earlier])), thread)
    assert result.kept[0].refers_to == "earlier"


@pytest.mark.parametrize("comment_id", ["c1aaaa", "c2bbbb"])
def test_refers_to_earlier_needs_a_reply_to_a_reply(comment_id):
    thread = Thread.model_validate(make_thread(comments=[
        make_comment("c1aaaa", body="I bought the Cuisinart CPK-17 last year."),
        make_comment("c2bbbb", parent_id="c1aaaa", body="Still love it, boils in two minutes."),
    ]))
    wrong = mention(comment_id=comment_id, product="Cuisinart CPK-17", category="kitchen",
                    quote={"c1aaaa": "I bought the Cuisinart CPK-17 last year.", "c2bbbb": "Still love it, boils in two minutes."}[comment_id],
                    refers_to="earlier")
    result = check_extraction(Extraction.model_validate(make_extraction(mentions=[wrong])), thread)
    assert "further up" in result.rejected[0][1]


WHOLE_QUOTE_BODY = "> **Best:** Hada Labo Gokujyun lotion.\n>\n> It made my dry skin plump in a week."


def test_a_comment_written_entirely_as_a_quote_block_is_the_writers_own_words():
    # Some people format their whole answer with ">". If no one else in the thread wrote those words, they're theirs.
    thread = Thread.model_validate(make_thread(comments=[make_comment("c1aaaa", body=WHOLE_QUOTE_BODY)]))
    own = mention(product="Hada Labo Gokujyun lotion", quote="It made my dry skin plump in a week.")
    result = check_extraction(Extraction.model_validate(make_extraction(mentions=[own])), thread)
    assert [m.product for m in result.kept] == ["Hada Labo Gokujyun lotion"]


@pytest.mark.parametrize("where", ["post", "another comment"])
def test_a_whole_quote_block_copying_someone_else_is_still_rejected(where):
    copied = "It made my dry skin plump in a week."
    comments = [make_comment("c1aaaa", body=WHOLE_QUOTE_BODY)]
    post = {}
    if where == "post":
        post = {"body": f"Hada Labo Gokujyun lotion: {copied} Any other ideas?"}
    else:
        comments.insert(0, make_comment("c0zzzz", body=f"Hada Labo Gokujyun lotion. {copied}"))
    thread = Thread.model_validate(make_thread(comments=comments, **post))
    result = check_extraction(Extraction.model_validate(make_extraction(mentions=[mention(product="Hada Labo Gokujyun lotion", quote=copied)])), thread)
    assert result.kept == [] and "quoted" in result.rejected[0][1]


# --- Instructions v6 (decided 9 Oct 2026): each product's type, and an evidence level with tags ---

def test_a_v6_mention_carries_its_product_type_and_evidence():
    data = mention(product_type="cleanser", evidence="long-term use", evidence_tags=["long-term use", "mentions flaws"])
    loaded = ExtractedMention.model_validate(data)
    assert loaded.product_type == "cleanser"
    assert loaded.evidence == "long-term use"
    assert loaded.evidence_tags == ["long-term use", "mentions flaws"]


def test_older_mentions_without_a_type_or_evidence_still_load():
    loaded = ExtractedMention.model_validate(mention())  # as written with instructions v1 to v5
    assert (loaded.product_type, loaded.evidence, loaded.evidence_tags) == (None, None, [])


@pytest.mark.parametrize("bad", [{"evidence": "years of use"}, {"evidence": ""}, {"product_type": ""}, {"product_type": "  "}])
def test_an_unknown_evidence_level_or_a_blank_type_is_refused(bad):
    with pytest.raises(ValidationError):
        ExtractedMention.model_validate(mention(**bad))


def test_every_evidence_level_and_tag_is_accepted():
    for level in EVIDENCE_LEVELS:
        result = check(make_extraction(mentions=[mention(evidence=level, evidence_tags=list(EVIDENCE_TAGS))]))
        assert [m.evidence for m in result.kept] == [level]


def test_a_mention_with_an_unknown_evidence_tag_is_rejected_with_the_reason():
    unknown = mention(evidence="long-term use", evidence_tags=["long-term use", "trustworthy"])
    fine = mention(comment_id="c3cccc", product="Paula's Choice 2% BHA", quote=PAULAS_QUOTE,
                   evidence="short-term use", evidence_tags=["short-term use", "compares alternatives"])
    result = check(make_extraction(mentions=[unknown, fine]))
    assert [m.comment_id for m in result.kept] == ["c3cccc"]
    assert len(result.rejected) == 1
    reason = reasons(result)[0]
    assert "unknown evidence tag" in reason and "'trustworthy'" in reason and "mentions flaws" in reason  # the allowed tags
    assert "'long-term use'" not in reason  # only the unknown tag is named as the problem


def test_other_is_not_an_evidence_tag_for_the_ai():
    # Noemi's "other" needs a note saying why; the AI has no note, so it picks from the known tags only.
    result = check(make_extraction(mentions=[mention(evidence="short-term use", evidence_tags=["other"])]))
    assert result.kept == [] and "unknown evidence tag" in reasons(result)[0]


def test_the_current_instructions_are_v7_and_todo_lists_older_extractions(tmp_path):
    # Changed on purpose 9 Oct 2026 (care tips, Noemi): the instructions moved from v6 to v7, so a v6 extraction is
    # now the older one that `todo` lists, and a v7 one is up to date. Was: v6 current, v5 listed.
    assert current_instructions_version() == "extract-v7"
    threads_dir = threads_folder(tmp_path, *(other_thread(i) for i in ("1aaaaa", "1bbbbb")))
    write_extraction(threads_dir, make_extraction(thread_id="1aaaaa", instructions_version="extract-v6", mentions=[]))
    write_extraction(threads_dir, make_extraction(thread_id="1bbbbb", instructions_version="extract-v7", mentions=[]))
    assert todo(threads_dir, current_instructions_version()) == ["1aaaaa"]


def instructions_text() -> str:
    return extract.DEFAULT_INSTRUCTIONS.read_text(encoding="utf-8")


def section(text: str, heading: str) -> str:
    """The text under a "## " heading of the instructions, up to the next one."""
    start = text.index(f"\n## {heading}")
    end = text.find("\n## ", start + 1)
    return text[start:end if end != -1 else None]


def test_the_instructions_list_every_product_type_exactly():
    from engine.query import PRODUCT_TYPES

    listed = section(instructions_text(), "Product type")
    names = listed[listed.index("Use one of these names"):listed.index("Otherwise")]
    assert re.findall(r'"([^"]+)"', names) == [p.name for p in PRODUCT_TYPES]


def test_the_instructions_define_every_evidence_level_and_tag():
    evidence = section(instructions_text(), "Evidence")
    for value in EVIDENCE_LEVELS + EVIDENCE_TAGS:
        assert f'"{value}"' in evidence or f"{value}:" in evidence, value


def test_a_long_life_ending_in_a_failure_is_in_the_stance_rules():
    # Noemi's decision 10 (9 Oct 2026), next to the "tell a friend" test.
    stance = section(instructions_text(), "Stance")
    assert "tell a friend" in stance and "died after 14 years" in stance and "mentions flaws" in stance


def test_the_output_example_is_a_valid_v7_extraction():
    # Changed on purpose 9 Oct 2026 (care tips, Noemi): the example now follows v7. Was: "extract-v6".
    example = instructions_text().split("```json", 1)[1].split("```", 1)[0]
    data = json.loads(example)
    assert data["instructions_version"] == "extract-v7"
    for item in data["mentions"]:
        loaded = ExtractedMention.model_validate(item | {"comment_id": "c1aaaa"})  # the example's ids are placeholders
        assert loaded.product_type and loaded.evidence and loaded.evidence_tags
        assert set(loaded.evidence_tags) <= set(EVIDENCE_TAGS)


# --- Review fixes, 9 Oct 2026 ---

QUOTED_PARENT = "The Acme kettle broke after a week.\nWorst purchase ever, never buy the Acme kettle."


@pytest.mark.parametrize("marker", [">", "&gt;", "> "])
def test_a_line_straight_after_a_quoted_line_is_still_quoted(marker):
    # On Reddit a line right after a ">" line, with no blank line between, belongs to the same quoted block.
    reply = f"{marker}The Acme kettle broke after a week.\nWorst purchase ever, never buy the Acme kettle.\n\nReally? Mine is fine."
    thread = Thread.model_validate(make_thread(comments=[
        make_comment("p1aaaa", body=QUOTED_PARENT), make_comment("r1bbbb", parent_id="p1aaaa", body=reply)]))
    second_line = mention(comment_id="r1bbbb", product="Acme kettle", category="kitchen", stance="warn",
                          quote="Worst purchase ever, never buy the Acme kettle.")
    own = mention(comment_id="r1bbbb", product="Acme kettle", category="kitchen", stance="recommend", quote="Mine is fine.")
    result = check_extraction(Extraction.model_validate(make_extraction(mentions=[second_line, own])), thread)
    assert [m.quote for m in result.kept] == ["Mine is fine."]
    assert "quoted" in result.rejected[0][1]


def test_a_whole_quote_block_continued_without_markers_is_still_the_writers_own_words():
    # The exception for a comment written entirely as a quoted block holds when its later lines carry no ">".
    body = "> **Best:** Hada Labo Gokujyun lotion.\nIt made my dry skin plump in a week."
    thread = Thread.model_validate(make_thread(comments=[make_comment("c1aaaa", body=body)]))
    own = mention(product="Hada Labo Gokujyun lotion", quote="It made my dry skin plump in a week.")
    result = check_extraction(Extraction.model_validate(make_extraction(mentions=[own])), thread)
    assert [m.product for m in result.kept] == ["Hada Labo Gokujyun lotion"]


@pytest.mark.parametrize("joiner", ["&#32;", "&nbsp;", "&#10;"])
def test_the_word_limit_counts_the_words_the_quote_matches(joiner):
    # A quote joined with HTML entities is one "word" as written, but matches every word of the comment.
    words = [f"word{n}" for n in range(QUOTE_MAX_WORDS + 30)]
    body = "I love the Acme kettle. " + " ".join(words)
    quote = joiner.join(["I", "love", "the", "Acme", "kettle."] + words)
    thread = Thread.model_validate(make_thread(comments=[make_comment("c1aaaa", body=body)]))
    result = check_extraction(Extraction.model_validate(make_extraction(mentions=[mention(product="Acme kettle", category="kitchen", quote=quote)])), thread)
    assert result.kept == []
    assert f"{len(words) + 5} words" in result.rejected[0][1]


@pytest.mark.parametrize("status", ["deleted", "removed"])
def test_a_reply_about_a_deleted_comment_above_is_rejected(status):
    # The product would be named only in text that is gone: it can't be checked, and the deletion rule applies.
    thread = Thread.model_validate(make_thread(comments=[
        make_comment("p1aaaa", body=f"[{status}]", status=status, author=None),
        make_comment("r1bbbb", parent_id="p1aaaa", body="Had this one 13 years, still perfect.")]))
    inherited = mention(comment_id="r1bbbb", product="Acme kettle", category="kitchen",
                        quote="Had this one 13 years, still perfect.", refers_to="parent")
    result = check_extraction(Extraction.model_validate(make_extraction(mentions=[inherited])), thread)
    assert result.kept == []
    assert status in result.rejected[0][1] and "p1aaaa" in result.rejected[0][1]


@pytest.mark.parametrize("status", ["deleted", "removed"])
def test_a_reply_about_a_deleted_comment_further_up_is_rejected(status):
    thread = Thread.model_validate(make_thread(comments=[
        make_comment("c1aaaa", body=f"[{status}]", status=status, author=None),
        make_comment("c2bbbb", parent_id="c1aaaa", body="How did you like it?"),
        make_comment("c3cccc", parent_id="c2bbbb", body="Still love it, boils in two minutes.")]))
    earlier = mention(comment_id="c3cccc", product="Cuisinart CPK-17", category="kitchen",
                      quote="Still love it, boils in two minutes.", refers_to="earlier")
    result = check_extraction(Extraction.model_validate(make_extraction(mentions=[earlier])), thread)
    assert result.kept == []
    assert status in result.rejected[0][1] and "c1aaaa" in result.rejected[0][1]


# --- Care tips: how to make it last (Noemi, 9 Oct 2026; instructions v7) ---

DESCALE_BODY = "My Zojirushi is 9 years old. Descale it every 6 months and it will outlive you."
DESCALE_QUOTE = "Descale it every 6 months and it will outlive you."


def care_tip(**overrides) -> dict:
    """One care tip as the AI writes it: about the Zojirushi kettle, in comment c1aaaa, quoted word for word."""
    fields = {"comment_id": "c1aaaa", "about": "Zojirushi kettle", "is_kind": False,
              "tip": "descale every 6 months", "quote": DESCALE_QUOTE}
    fields.update(overrides)
    return fields


def kettle_care_thread() -> Thread:
    return Thread.model_validate(make_thread(comments=[
        make_comment("c1aaaa", body=DESCALE_BODY),
        make_comment("c2bbbb", body="Never put a carbon steel knife in the dishwasher."),
        make_comment("c3cccc", body="[deleted]", status="deleted", author=None),
    ]))


def test_care_tips_are_checked_like_notes():
    # Kept only when the comment is still readable and the quote is in it word for word.
    extraction = make_extraction(mentions=[], care=[
        care_tip(),
        care_tip(comment_id="c2bbbb", about="carbon steel knife", is_kind=True, tip="no dishwasher",
                 quote="Never put a carbon steel knife in the dishwasher."),
        care_tip(comment_id="c2bbbb", about="chef knife", is_kind=True, tip="hand wash only", quote="Hand wash it only."),
        care_tip(comment_id="c3cccc", quote="[deleted]"),
        care_tip(comment_id="c9zzzz"),
    ])
    result = check_extraction(Extraction.model_validate(extraction), kettle_care_thread())
    assert [(c.about, c.is_kind, c.tip) for c in result.kept_care] == [
        ("Zojirushi kettle", False, "descale every 6 months"), ("carbon steel knife", True, "no dishwasher")]
    why = [reason for _, reason in result.rejected_care]
    assert "word for word" in why[0] and "deleted" in why[1] and "not in thread" in why[2]


def test_a_care_tip_from_a_quoted_block_or_over_the_word_limit_is_rejected():
    long_body = "Season it often: " + " ".join(f"word{n}" for n in range(QUOTE_MAX_WORDS + 5)) + "."
    thread = Thread.model_validate(make_thread(comments=[
        make_comment("c1aaaa", body=DESCALE_BODY),
        make_comment("r1bbbb", parent_id="c1aaaa", body=f"&gt;{DESCALE_QUOTE}\n\nI never descale mine."),
        make_comment("c3cccc", body=long_body),
    ]))
    extraction = make_extraction(mentions=[], care=[
        care_tip(comment_id="r1bbbb"), care_tip(comment_id="c3cccc", about="cast iron skillet", is_kind=True,
                                                tip="season it often", quote=long_body)])
    result = check_extraction(Extraction.model_validate(extraction), thread)
    assert result.kept_care == []
    assert "quoted block" in result.rejected_care[0][1] and "limit is" in result.rejected_care[1][1]


def test_a_care_tip_is_about_a_product_unless_it_says_it_is_about_a_kind():
    from engine.extract import ExtractedCareTip

    assert ExtractedCareTip.model_validate({k: v for k, v in care_tip().items() if k != "is_kind"}).is_kind is False
    assert ExtractedCareTip.model_validate(care_tip(is_kind=True)).is_kind is True


@pytest.mark.parametrize("bad", [{"about": ""}, {"tip": "  "}, {"quote": ""}, {"stance": "recommend"},
                                 {"comment_id": "c1 aaaa"}, {"is_kind": "sometimes"}])
def test_a_care_tip_with_a_wrong_or_empty_value_or_an_unknown_field_is_refused(bad):
    with pytest.raises(ValidationError):
        Extraction.model_validate(make_extraction(care=[care_tip(**bad)]))


@pytest.mark.parametrize("field", ["comment_id", "about", "tip", "quote"])
def test_every_care_tip_field_but_is_kind_is_required(field):
    tip = care_tip()
    del tip[field]
    with pytest.raises(ValidationError):
        Extraction.model_validate(make_extraction(care=[tip]))


def test_older_extractions_without_care_tips_still_load_and_check():
    # Instructions v1 to v6 had no care tips: their files have no "care" list.
    extraction = Extraction.model_validate(make_extraction(instructions_version="extract-v6"))
    assert extraction.care == []
    result = check(make_extraction(instructions_version="extract-v6"))
    assert result.kept_care == [] and result.rejected_care == []
    assert len(result.kept) == 2


def test_command_line_check_counts_care_tips_and_names_the_rejected(tmp_path, capsys):
    thread = make_thread(comments=[make_comment("c1aaaa", body=DESCALE_BODY)])
    threads_dir = threads_folder(tmp_path, thread)
    write_extraction(threads_dir, make_extraction(mentions=[], care=[care_tip(), care_tip(quote="Descale weekly.")]))
    assert extract.main(["check", str(threads_dir)]) == 0
    out = capsys.readouterr().out
    assert "care tips: 1 kept, 1 rejected" in out
    assert "c1aaaa  care tip: quote not found word for word" in out
    assert "Descale weekly." not in out  # a rejected quote is never printed


def test_the_instructions_send_care_tips_to_care_with_noemis_examples():
    care = " ".join(section(instructions_text(), "Care tips").split())
    for example in ("descale it every 6 months", "never put a carbon steel knife in the dishwasher",
                    "re-season after scrubbing", "keep it away from sunlight"):
        assert example in care, example
    for field in ('"about"', '"is_kind"', '"tip"', '"quote"', '"care"'):
        assert field in care, field
    assert "Noemi, 9 Oct 2026" in care
    notes = " ".join(section(instructions_text(), "Notes").split())
    assert "are not notes" in notes and '"care"' in notes  # no longer just skipped: they go to "care"


def test_the_output_example_has_a_valid_care_tip():
    from engine.extract import ExtractedCareTip

    example = json.loads(instructions_text().split("```json", 1)[1].split("```", 1)[0])
    assert list(example) == ["thread_id", "instructions_version", "extracted_at", "extractor", "mentions", "notes",
                             "care", "agreements"]
    tips = [ExtractedCareTip.model_validate(item | {"comment_id": "c1aaaa"}) for item in example["care"]]
    assert tips and all(isinstance(t.is_kind, bool) and t.tip and t.about for t in tips)


def test_every_rule_of_v6_is_still_in_v7():
    # Instructions v7 only adds care tips: every other rule of v6 stays word for word.
    text = instructions_text()
    for heading in ("How to read the thread", "What counts as a product mention", "Product type", "Stance",
                    "Evidence: how well this writer knows this product", "The quote",
                    "Agreements: replies that back up the comment above", "Skip", "Before you finish"):
        assert f"\n## {heading}\n" in text, heading
    for rule in ("Each product once per comment.", "A failure the writer caused themselves",
                 "Never open a link from the thread, and never quote anything from the web",
                 "Experience with a kind counts", "Only replies can agree."):
        assert rule in " ".join(text.split()), rule
