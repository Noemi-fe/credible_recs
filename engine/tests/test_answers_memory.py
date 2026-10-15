"""The answers' memory, bounded (15 Oct 2026).

Answers keep what they work out between requests (engine/memo.py, engine/library_cache.py; latency, 12 Oct 2026), so a
second answer of a product type is quick. But they kept it for every type: with ~1,950 threads the live site ran out
of memory at 2 GiB every 20 to 40 minutes as getting ready and the keep-warm pings warmed ~480 requests, and the daily
plan job needed 3 GiB. Now:
- engine.memo.forget_answers() empties what answers worked out (every Table, the answers worked out from a list, a
  library's work for one product type) and keeps what was read (the library, the price, facts and brand-lines lists)
  and what the library worked out of itself, whatever the request (its name index, its ranges, each thread's comments
  read, each category's readable threads);
- engine.memo.TypeWindow forgets them once answers have asked about a given number of product types since the last
  time: the pre-check's plan and the site each keep at most that many types' work;
- an answer after forgetting is the same answer.

Every library, request and comment here is made up; nothing reads data/.
"""

from engine import library_cache, memo
from engine.pipeline import answer_request
from engine.tests.test_library_cache import settled
from engine.tests.test_pipeline import REQUEST, library


def test_forgetting_answers_empties_what_answers_worked_out_and_keeps_what_was_read(tmp_path):
    table = memo.Table()
    table.keep("a request", "its needs")
    listed = memo.PerList()
    things = [1, 2, 3]
    listed.of(things)["a name"] = "its entries"
    files = memo.FileMemo()
    path = tmp_path / "list.json"
    path.write_text("[1]", encoding="utf-8")
    import os
    import time
    past = time.time_ns() - 60 * 10**9
    os.utime(path, ns=(past, past))
    reads = []
    read = lambda p: reads.append(1) or p.read_text(encoding="utf-8")
    files.get(path, read)
    memo.forget_answers()
    assert len(table) == 0 and listed.of(things) == {}
    files.get(path, read)
    assert reads == [1]  # the list read stays read


def test_a_memory_registered_as_what_was_read_stays(tmp_path):
    kept = {"thread": "read"}
    memo.register(kept.clear, answers=False)
    memo.forget_answers()
    assert kept == {"thread": "read"}
    memo.forget_all()
    assert kept == {}


def test_the_kept_library_stays_with_its_own_work_and_loses_one_requests(tmp_path):
    root = settled(library(tmp_path))
    first = answer_request(REQUEST, library_dir=root)
    kept = library_cache.loaded(root / "threads")
    kinds = lambda: {key[0] for key in kept.remembered if isinstance(key, tuple)}
    assert memo.REQUEST_WORK in kept.remembered and kept.remembered[memo.REQUEST_WORK]
    before = kinds()
    memo.forget_answers()
    assert library_cache.loaded(root / "threads") is kept  # not read again
    assert not kept.remembered.get(memo.REQUEST_WORK)  # what one request's type needed
    assert kinds() - {memo.REQUEST_WORK[0]} == before - {memo.REQUEST_WORK[0]}  # the rest stays
    again = answer_request(REQUEST, library_dir=root)
    assert again.text() == first.text() and again.threads_used == first.threads_used


def test_a_type_window_forgets_once_answers_asked_about_its_size_of_types(monkeypatch):
    forgot = []
    monkeypatch.setattr(memo, "forget_answers", lambda: forgot.append(1))
    window = memo.TypeWindow(3)
    for kind in ["kettle", "kettle", "pan", "knife", "pan"]:
        window.answered(kind)
    assert forgot == []  # three types so far
    window.answered("serum")  # a fourth: the three types' work goes first
    assert forgot == [1]
    for kind in ["serum", "kettle", "pan"]:
        window.answered(kind)
    assert forgot == [1]  # serum, kettle and pan since
    window.answered("knife")
    assert forgot == [1, 1]


def test_the_site_forgets_the_answers_memory_after_so_many_types_and_answers_the_same(tmp_path, monkeypatch):
    # The site's answers (a visitor's, and getting ready's warm ones) tell the window their type before they are worked
    # out: past ANSWERS_KEPT_TYPES types, what answers worked out is forgotten, and an answer is the same as before.
    import json

    from engine import web

    root = settled(library(tmp_path))
    first = json.loads(web.answer_response(REQUEST, root)[2])
    web._answers.clear()
    forgot, real = [], memo.forget_answers
    monkeypatch.setattr(memo, "forget_answers", lambda: forgot.append(1) or real())
    monkeypatch.setattr(web, "_window", memo.TypeWindow(1))
    for request in ("frying pan", REQUEST, "chef knife"):
        web.answer_response(request, root)
    web.warm_answer("toaster", root)
    assert len(forgot) == 3  # electric kettle after frying pan, chef knife, then toaster
    web._answers.clear()
    again = json.loads(web.answer_response(REQUEST, root)[2])
    assert {k: v for k, v in again.items() if k != "timing"} == {k: v for k, v in first.items() if k != "timing"}
