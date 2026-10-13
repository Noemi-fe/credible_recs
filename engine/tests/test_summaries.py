"""One-line summaries (Noemi's decision 4 of 13 Oct 2026): what a pick's credible backers say, in one sentence of our
own words, written ahead of time and checked by code before it is shown.

Every comment and summary here is made up. The rules tested: the text (one sentence, at most SUMMARY_MAX_WORDS words,
no quotation marks), the comments it cites (each one of the product's credible mentions in this answer, still
readable), its numbers (each written in a cited comment; a count of people at most the comments cited) and its
downside (acknowledged when the product has credible warnings or a cited comment is one).
"""

import json
from pathlib import Path

import pytest

from engine import summaries
from engine.config import SUMMARY_MAX_WORDS
from engine.summaries import (
    Summary,
    acknowledges_downside,
    load_summaries,
    number_problems,
    shown_problems,
    text_problems,
)


def entry(text: str = "Owners of 6 years say it still boils fast, but one owner finds the lid stiff.",
          cites: tuple[str, ...] = ("c1", "c2"), **overrides) -> Summary:
    fields = dict(product="Zojirushi kettle", category="kitchen", product_type="electric kettle", text=text,
                  cites=list(cites), written_at="2026-10-13T10:00:00Z", writer="claude-code",
                  instructions_version=summaries.current_version())
    return Summary(**(fields | overrides))


BODIES = {
    "c1": "My Zojirushi kettle has lasted 6 years and still boils fast.",
    "c2": "Works fine, though the lid is stiff on my Zojirushi kettle after two years.",
    "c3": "The Zojirushi kettle died after 8 months, avoid it.",
}


# --- The text ---

def test_a_plain_sentence_passes():
    assert text_problems("Owners say it boils fast and lasts for years.") == []


def test_a_summary_over_the_word_cap_is_refused():
    long = " ".join(["word"] * (SUMMARY_MAX_WORDS + 1)) + "."
    assert any("words" in problem for problem in text_problems(long))
    assert text_problems(" ".join(["word"] * SUMMARY_MAX_WORDS) + ".") == []


@pytest.mark.parametrize("text", ['Owners call it "the best kettle".', "Owners call it “the best”.",
                                  "Owners call it ‘the best’.", "Owners call it 'the best'."])
def test_a_summary_with_quotation_marks_is_refused(text):
    # A summary is never presented as a quote.
    assert any("quotation marks" in problem for problem in text_problems(text))


def test_apostrophes_are_not_quotation_marks():
    assert text_problems("It’s the owners' favourite, and it doesn't rust.") == []


def test_a_summary_is_one_sentence():
    assert any("one sentence" in problem for problem in text_problems("Owners love it. One finds it heavy."))
    assert any("one sentence" in problem for problem in text_problems("Owners love it\nand use it daily."))
    assert text_problems("Owners love it; one finds it heavy.") == []


def test_an_empty_summary_is_refused():
    assert text_problems("   ") != []


# --- Numbers ---

def test_every_number_must_be_written_in_a_cited_comment():
    assert number_problems("Owners of 6 years say it boils fast.", ["It has lasted 6 years."], 1) == []
    problems = number_problems("Owners of 7 years say it boils fast.", ["It has lasted 6 years."], 1)
    assert problems and "7" in problems[0]


def test_a_number_may_be_written_in_digits_or_words_on_either_side():
    assert number_problems("Owners of six years say it boils fast.", ["It has lasted 6 years."], 1) == []
    assert number_problems("Owners of 6 years say it boils fast.", ["It has lasted six years."], 1) == []
    assert number_problems("It holds 1.7 litres.", ["It holds 1.7 litres."], 1) == []
    assert number_problems("It costs £1,200.", ["I paid 1200 for it."], 1) == []


def test_prices_and_percentages_are_numbers_too():
    assert number_problems("Worth it at £30.", ["Paid £35."], 1) != []
    assert number_problems("The 2% one suits beginners.", ["The 5% one stung."], 1) != []


def test_a_count_of_people_must_not_exceed_the_comments_cited():
    assert number_problems("Two owners praise its lid.", ["Great lid.", "Love the lid."], 2) == []
    problems = number_problems("Three owners praise its lid.", ["Great lid.", "Love the lid."], 2)
    assert problems and "3" in problems[0]
    assert number_problems("One owner finds it heavy.", ["Too heavy."], 1) == []


def test_one_is_a_number_only_before_a_unit_or_people():
    # "One of the best" isn't a number; "one year" and "one owner" are.
    assert number_problems("One of the best, owners say.", ["Great."], 1) == []
    assert number_problems("It broke after one year.", ["It broke after 2 years."], 1) != []


def test_numbers_in_the_products_own_name_are_not_checked():
    assert number_problems("Owners say the C2 grinds evenly.", ["It grinds evenly."], 1, "Timemore C2") == []


# --- Downsides ---

@pytest.mark.parametrize("text", ["Owners love it, but one finds it heavy.", "Loved, though the lid sticks.",
                                  "Owners praise it; one complains it rusts.", "One owner warns the coating peels."])
def test_a_contrast_or_a_drawback_acknowledges_a_downside(text):
    assert acknowledges_downside(text)


def test_praise_alone_acknowledges_no_downside():
    assert not acknowledges_downside("Owners love it and use it every day.")
    assert not acknowledges_downside("Butter slides off it.")  # whole words only


# --- Before a summary is shown ---

def test_a_summary_backed_by_credible_mentions_is_shown():
    credible = {"c1": "recommend", "c2": "recommend"}
    assert shown_problems(entry(), credible, BODIES, has_warnings=False) == []


def test_a_cited_comment_that_isnt_a_credible_mention_here_stops_it():
    problems = shown_problems(entry(cites=("c1", "c9")), {"c1": "recommend"}, BODIES, has_warnings=False)
    assert problems and "c9" in problems[0]


def test_a_cited_comment_no_longer_readable_stops_it():
    bodies = {"c1": BODIES["c1"]}  # c2 was deleted
    problems = shown_problems(entry(), {"c1": "recommend", "c2": "recommend"}, bodies, has_warnings=False)
    assert any("c2" in problem for problem in problems)


def test_a_product_with_credible_warnings_needs_a_downside_in_its_summary():
    praise = entry(text="Owners of 6 years say it still boils fast.", cites=("c1",))
    credible = {"c1": "recommend", "c3": "warn"}
    assert any("downside" in p for p in shown_problems(praise, credible, BODIES, has_warnings=True))
    assert shown_problems(praise, credible, BODIES, has_warnings=False) == []


def test_a_cited_warning_needs_a_downside_in_the_summary():
    praise = entry(text="Owners say it boils fast.", cites=("c1", "c3"))
    credible = {"c1": "recommend", "c3": "warn"}
    assert any("downside" in p for p in shown_problems(praise, credible, BODIES, has_warnings=False))
    honest = entry(text="Owners say it boils fast, but one owner warns it died within months.", cites=("c1", "c3"))
    assert shown_problems(honest, credible, BODIES, has_warnings=True) == []


def test_numbers_are_checked_against_the_cited_comments_only():
    # c3 says 8 months, but only c1 is cited.
    made_up = entry(text="Owners say it lasts 8 years.", cites=("c1",))
    assert shown_problems(made_up, {"c1": "recommend", "c3": "warn"}, BODIES, has_warnings=False) != []


# --- The file ---

def write(tmp_path: Path, data) -> Path:
    path = tmp_path / "summaries.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_the_file_loads_one_entry_per_product_key(tmp_path):
    good = entry().model_dump(mode="json")
    loaded = load_summaries(write(tmp_path, {"kitchen:zojirushi kettle": good}))
    assert list(loaded.entries) == ["kitchen:zojirushi kettle"] and loaded.problems == []
    assert loaded.entries["kitchen:zojirushi kettle"].cites == ["c1", "c2"]


def test_no_file_means_no_summaries(tmp_path):
    loaded = load_summaries(tmp_path / "summaries.json")
    assert loaded.entries == {} and loaded.problems == []


def test_a_broken_entry_is_left_out_and_named_never_the_whole_file(tmp_path):
    good = entry().model_dump(mode="json")
    broken = good | {"cites": []}
    loaded = load_summaries(write(tmp_path, {"kitchen:zojirushi kettle": good, "kitchen:other kettle": broken}))
    assert list(loaded.entries) == ["kitchen:zojirushi kettle"]
    assert len(loaded.problems) == 1 and "kitchen:other kettle" in loaded.problems[0]


def test_a_file_that_isnt_json_is_named_as_a_problem(tmp_path):
    path = tmp_path / "summaries.json"
    path.write_text("{not json", encoding="utf-8")
    loaded = load_summaries(path)
    assert loaded.entries == {} and loaded.problems


def test_a_key_must_start_with_its_entrys_category(tmp_path):
    loaded = load_summaries(write(tmp_path, {"skincare:zojirushi kettle": entry().model_dump(mode="json")}))
    assert loaded.entries == {} and "category" in loaded.problems[0]


def test_a_changed_file_is_read_again(tmp_path):
    path = write(tmp_path, {})
    assert load_summaries(path).entries == {}
    path.write_text(json.dumps({"kitchen:zojirushi kettle": entry().model_dump(mode="json")}), encoding="utf-8")
    assert list(load_summaries(path).entries) == ["kitchen:zojirushi kettle"]


def test_the_instructions_have_a_version():
    assert summaries.current_version().startswith("summarise-v")


# --- todo and check: the AI step's bookkeeping ---

from engine.tests.test_pipeline import REQUEST, library  # noqa: E402  (the made-up kettle library)

ZOJI = "kitchen:zojirushi kettle"


def requests_file(tmp_path: Path) -> Path:
    path = tmp_path / "requests.json"
    path.write_text(json.dumps({"questions": [{"id": "k01", "text": REQUEST},
                                              {"id": "k02", "text": "something nice for my mum"}]}), encoding="utf-8")
    return path


def save(library_dir: Path, entries: dict) -> None:
    (library_dir / "summaries.json").write_text(json.dumps(
        {key: value.model_dump(mode="json") for key, value in entries.items()}), encoding="utf-8")


def zoji(text: str = "Owners of 6 and 8 years say it still boils and keeps going.", cites=("k1aaaa", "k2aaaa"),
         **overrides) -> Summary:
    return entry(text=text, cites=cites, **overrides)


def test_the_requests_are_read_from_both_files_each_once(tmp_path):
    first = requests_file(tmp_path)
    second = tmp_path / "more.json"
    second.write_text(json.dumps({"queries": [{"id": "x01", "text": REQUEST}, {"id": "x02", "text": "a toaster"}]}),
                      encoding="utf-8")
    assert summaries.requests_to_answer((first, second)) == [("k01", REQUEST), ("k02", "something nice for my mum"),
                                                             ("x02", "a toaster")]


def test_todo_lists_the_picks_without_a_summary_and_writes_what_the_writer_reads(tmp_path, capsys):
    lib = library(tmp_path)
    found = summaries.todo(summaries.requests_to_answer((requests_file(tmp_path),)), lib)
    zojirushi = next(item for item in found if item.key == ZOJI)
    assert zojirushi.product == "Zojirushi kettle" and zojirushi.requests == ["k01"]
    assert zojirushi.reasons == ["k01: no summary yet"]
    assert {m["comment_id"] for m in zojirushi.credible} == {"k1aaaa", "k1bbbb", "k2aaaa", "k2bbbb"}
    first = next(m for m in zojirushi.credible if m["comment_id"] == "k1aaaa")
    assert first["stance"] == "recommend" and first["in_every_answer"] and first["body"].startswith("My Zojirushi")
    assert summaries.main(["todo"], (requests_file(tmp_path),), lib) == 0
    printed = capsys.readouterr().out
    assert ZOJI in printed and "no summary yet" in printed
    assert "lasted 6 years" not in printed  # names and reasons only, never a quote
    packet = json.loads((lib / summaries.TODO_FILE).read_text(encoding="utf-8"))
    assert packet["instructions_version"] == summaries.current_version()
    assert ZOJI in [item["key"] for item in packet["products"]]


def test_todo_leaves_out_a_product_whose_summary_is_shown(tmp_path):
    lib = library(tmp_path)
    save(lib, {ZOJI: zoji()})
    found = summaries.todo(summaries.requests_to_answer((requests_file(tmp_path),)), lib)
    assert ZOJI not in [item.key for item in found]


def test_todo_lists_a_summary_that_would_not_be_shown_with_the_reason(tmp_path):
    lib = library(tmp_path)
    save(lib, {ZOJI: zoji(text="Owners of 12 years say it still boils.")})
    found = summaries.todo(summaries.requests_to_answer((requests_file(tmp_path),)), lib)
    zojirushi = next(item for item in found if item.key == ZOJI)
    assert zojirushi.reasons == ["k01: the number 12 isn't in any comment it cites"]


def test_todo_lists_a_summary_written_under_older_instructions(tmp_path):
    lib = library(tmp_path)
    save(lib, {ZOJI: zoji(instructions_version="summarise-v0")})
    found = summaries.todo(summaries.requests_to_answer((requests_file(tmp_path),)), lib)
    assert any("older instructions" in reason for reason in next(i for i in found if i.key == ZOJI).reasons)


def test_check_passes_good_entries(tmp_path, capsys):
    lib = library(tmp_path)
    save(lib, {ZOJI: zoji()})
    assert summaries.main(["check"], (requests_file(tmp_path),), lib) == 0
    assert "1 summary checked: 1 fine" in capsys.readouterr().out


def test_check_names_every_problem_with_its_reason(tmp_path, capsys):
    lib = library(tmp_path)
    save(lib, {ZOJI: zoji(text='Owners call it "the one" after 12 years.', cites=("k1aaaa", "gone01"))})
    problems = summaries.check(lib, summaries.requests_to_answer((requests_file(tmp_path),)))[0]
    assert any("quotation marks" in p for p in problems)
    assert any("gone01" in p and "library" in p for p in problems)
    assert any("12" in p for p in problems)
    assert any(p.startswith(f"{ZOJI}: in k01:") for p in problems)  # and so it wouldn't be shown in that answer
    assert summaries.main(["check"], (requests_file(tmp_path),), lib) == 1
    assert "gone01" in capsys.readouterr().out


def test_check_names_a_broken_entry(tmp_path):
    lib = library(tmp_path)
    (lib / "summaries.json").write_text(json.dumps({ZOJI: {"product": "Zojirushi kettle"}}), encoding="utf-8")
    problems = summaries.check(lib, [])[0]
    assert problems and ZOJI in problems[0]
