"""One-line summaries for what a sweep shows (17 Oct 2026, the converge round, item 8).

Summaries were written on 13 Oct 2026 for the products of the pre-check's requests; the sweeps of 16 and 17 Oct show
far more (interviewee and demo requests, the general category), and most of their picks and "Also worth a look" items
have no summary. For the final phase (once picks settle) the tooling lists every pick and item a sweep (eval/sweep.py)
shows without a summary, from the sweep's file alone (`missing`), and prepares the writer's reading for exactly those
(`todo --sweep`: the sweep's requests answered again, only what their answers show). No summary is written here.

The kettle library is made up (engine/tests/test_pipeline.py); so is every sweep line.
"""

import json
from pathlib import Path

from engine import summaries
from engine.pipeline import answer_request
from engine.tests.test_pipeline import REQUEST, library
from engine.tests.test_summaries import ZOJI, save, zoji
from engine.web import answer_json


def sweep_line(request: str, answer: dict | None) -> str:
    return json.dumps({"request": request, "source": "test", "seconds": 0.1,
                       "json": {"query": {}, "answer": answer}}, ensure_ascii=False)


def made_up_sweep(tmp_path: Path) -> Path:
    path = tmp_path / "sweep.jsonl"
    path.write_text("\n".join([
        sweep_line("kettle that lasts", {"category": "kitchen", "picks": [
            {"name": "Zojirushi kettle", "summary": None}, {"name": "Fellow Stagg EKG", "summary": {"text": "Ours."}}],
            "worth_a_look": [{"name": "Smeg kettle", "summary": None}]}),
        sweep_line("quiet kettle", {"category": "kitchen", "picks": [{"name": "Zojirushi kettle", "summary": None}],
                                    "worth_a_look": []}),
        sweep_line("a vague thing", None),
    ]) + "\n", encoding="utf-8")
    return path


def test_every_pick_and_item_a_sweep_shows_without_a_summary_is_listed_once(tmp_path):
    lib = library(tmp_path)
    found = summaries.missing_in_sweep(made_up_sweep(tmp_path), lib)
    assert [item["key"] for item in found] == [ZOJI, "kitchen:smeg kettle"]
    zojirushi = found[0]
    assert zojirushi["shown_as"] == ["pick"] and zojirushi["requests"] == ["kettle that lasts", "quiet kettle"]
    assert zojirushi["reasons"] == ["kettle that lasts: no summary yet", "quiet kettle: no summary yet"]
    assert found[1]["shown_as"] == ["worth a look"]


def test_a_summary_saved_but_not_shown_in_an_answer_says_so(tmp_path):
    lib = library(tmp_path)
    save(lib, {ZOJI: zoji()})
    zojirushi = next(item for item in summaries.missing_in_sweep(made_up_sweep(tmp_path), lib) if item["key"] == ZOJI)
    assert zojirushi["reasons"][0] == "kettle that lasts: its summary isn't shown in this answer (todo says why)"


def test_todo_over_a_sweeps_requests_lists_only_what_their_answers_show(tmp_path):
    lib = library(tmp_path)
    shown = {pick.name for pick in answer_request(REQUEST, library_dir=lib).answer.picks}
    found = summaries.todo([(REQUEST, REQUEST)], lib, shown_only=True)
    assert {item.product for item in found} <= shown and "Zojirushi kettle" in {item.product for item in found}
    every = summaries.todo([(REQUEST, REQUEST)], lib)  # as before: every product that qualifies, shown or not
    assert {item.product for item in found} <= {item.product for item in every}


def test_the_commands_print_names_and_reasons_only_and_todo_writes_the_writers_reading(tmp_path, capsys):
    lib = library(tmp_path)
    sweep = tmp_path / "sweep.jsonl"
    sweep.write_text(sweep_line(REQUEST, answer_json(answer_request(REQUEST, library_dir=lib))["answer"]) + "\n",
                     encoding="utf-8")
    assert summaries.main(["missing", str(sweep)], library_dir=lib) == 0
    printed = capsys.readouterr().out
    assert ZOJI in printed and "no summary yet" in printed and "lasted 6 years" not in printed
    assert summaries.main(["todo", "--sweep", str(sweep)], library_dir=lib) == 0
    packet = json.loads((lib / summaries.TODO_FILE).read_text(encoding="utf-8"))
    assert ZOJI in [item["key"] for item in packet["products"]]
    assert "lasted 6 years" not in capsys.readouterr().out
