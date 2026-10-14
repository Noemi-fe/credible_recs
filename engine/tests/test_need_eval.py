"""The need evaluation (14 Oct 2026, engine/need_eval.py): how many of an answer's first-reading threads are about the
request's need, by title and by title or post, and what the answer shows. The library and cases are made up."""

import json

from engine.need_eval import DEFAULT_CASES, about_the_need, need_lines, score_cases
from engine.tests.factories import make_comment, make_thread, write_gold

GREASY = "shampoo for greasy hair"


def hair_thread(thread_id: str, title: str, body: str, quote: str) -> dict:
    url = f"https://www.reddit.com/r/HaircareScience/comments/{thread_id}/post/"
    return make_thread(id=thread_id, community="HaircareScience", category="haircare", title=title, body=body, url=url,
                       comments=[make_comment(f"{thread_id}c1", thread_id=thread_id, body=quote,
                                              url=f"{url}{thread_id}c1/")])


def hair_library(tmp_path):
    threads = [
        hair_thread("1hair01", "Shampoo for greasy roots?", "Washing daily, still flat by noon.",
                    "I've used Acme Clear Shampoo for 2 years and my roots stay fresh."),
        hair_thread("1hair02", "Best shampoo you have ever used?", "My scalp gets oily fast, any ideas?",
                    "Acme Clear Shampoo has been great for me for a year."),
        hair_thread("1hair03", "Shampoo recommendations please", "Curly hair, love a good lather.",
                    "Acme Clear Shampoo is lovely, I've used it for months."),
    ]
    root = write_gold(tmp_path / "library", threads, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for thread in threads:
        comment = thread["comments"][0]
        (root / "extracted" / f"{thread['id']}.json").write_text(json.dumps({
            "thread_id": thread["id"], "instructions_version": "extract-v10", "extracted_at": "2026-10-12T10:00:00Z",
            "extractor": "claude-code", "mentions": [{
                "comment_id": comment["id"], "product": "Acme Clear Shampoo", "category": "haircare",
                "product_type": "shampoo", "stance": "recommend", "quote": comment["body"],
                "evidence": "long-term use", "evidence_tags": ["long-term use"]}],
        }), encoding="utf-8")
    return root


def cases_file(tmp_path, cases):
    path = tmp_path / "needs.json"
    path.write_text(json.dumps({"approved": False, "cases": cases}), encoding="utf-8")
    return path


def test_a_thread_is_about_the_need_by_a_judge_word_at_the_start_of_a_word():
    assert about_the_need("Shampoo for GREASY roots?", ["greas", "oily"])
    assert about_the_need("my hair gets oily", ["greas", "oily"])
    assert not about_the_need("a toily problem", ["oily"])  # inside a word
    assert not about_the_need("", ["oily"]) and not about_the_need(None, ["oily"])
    assert about_the_need("works on a glass-top stove", ["glass[- ]?top"])


def test_each_case_counts_its_first_reading_threads_about_the_need_by_title_and_by_post(tmp_path):
    path = cases_file(tmp_path, [{"id": "n01", "text": GREASY, "judge": ["greas", "oily", "oili"]}])
    [result] = score_cases(path, hair_library(tmp_path), profiles=None, live_checker=None)
    assert result.needs  # the engine reads a need in the request
    assert sorted(result.first) == ["1hair01", "1hair02", "1hair03"] and result.threads_read == 3
    assert (result.about_by_title, result.about_by_title_or_post) == (1, 2)
    lines = need_lines([result])
    assert lines[0].startswith("1 requests: first-reading threads about the need 2/3 by title or post, 1/3 by title")
    assert any("n01" in line and "about the need 2 by title or post (1 by title)" in line for line in lines)


def test_the_first_reading_is_the_first_threads_read(tmp_path):
    path = cases_file(tmp_path, [{"id": "n01", "text": GREASY, "judge": ["greas", "oily", "oili"]}])
    [result] = score_cases(path, hair_library(tmp_path), profiles=None, live_checker=None, max_threads=2)
    assert len(result.first) == 2


def test_the_committed_cases_load_and_each_has_judge_words():
    cases = json.loads(DEFAULT_CASES.read_text(encoding="utf-8"))["cases"]
    assert len(cases) >= 10 and len({c["id"] for c in cases}) == len(cases)
    texts = {c["text"] for c in cases}
    assert {"shampoo for greasy hair", "dandruff shampoo that actually works", "kettle that's quiet"} <= texts
    for case in cases:
        assert case["judge"] and all(isinstance(word, str) and word for word in case["judge"]), case["id"]
