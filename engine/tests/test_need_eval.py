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


# --- Every need, and the opposite (14 Oct 2026, the need-quality builder) ---
# A request with several needs ("shampoo for curly hair that isn't drying") is best read from threads about all of them,
# and never from threads asking for the opposite ("Best clarifying shampoo?"), nor answered with a product named as
# the opposite (a clarifying or detox shampoo). Each case may judge each need apart ("judge_each") and list the
# opposite's words ("opposite"), matched like judge words.

def test_a_case_counts_threads_about_every_need_and_threads_and_picks_named_as_the_opposite(tmp_path):
    root = hair_library(tmp_path)
    path = cases_file(tmp_path, [{
        "id": "n11", "text": "shampoo for curly hair that isn't drying", "judge": ["curl", "dry"],
        "judge_each": {"curly": ["curl"], "drying": ["dry", "moistur"]}, "opposite": ["clear", "clarif"]}])
    [result] = score_cases(path, root, profiles=None, live_checker=None)
    # 1hair03's post is about curls only; no thread is about curls and drying; none is titled as the opposite.
    assert result.about_every_need == 0 and result.titled_opposite == 0
    # What the answer shows named with an opposite word ("Clear" here) is counted.
    assert result.named_opposite == sum("Clear" in name for name in result.picks + result.worth)
    lines = need_lines([result])
    assert "about every need 0/" in lines[0] and "titled as the opposite 0" in lines[0]


def test_a_case_without_each_need_judged_counts_none_for_every_need():
    from engine.need_eval import CaseResult

    plain = CaseResult("n01", GREASY, first=["a", "b"])
    assert plain.about_every_need == 0 and plain.titled_opposite == 0 and plain.named_opposite == 0
    assert "about every need" not in need_lines([plain])[0]


def test_a_slimmed_threads_post_is_judged_by_title_only_and_the_report_says_how_many(tmp_path):
    # 13 Oct 2026 (Noemi: "Keep only comments we use"): a slimmed thread keeps its title but not its post's words, and
    # the judge words are the eval's own, so its post can't be judged: the report says how many were judged by title.
    from engine.slim import slim_library

    root = hair_library(tmp_path)
    assert len(slim_library(root, gold_ids=set()).slimmed) == 3
    path = cases_file(tmp_path, [{"id": "n01", "text": GREASY, "judge": ["greas", "oily", "oili"]}])
    [result] = score_cases(path, root, profiles=None, live_checker=None)
    assert sorted(result.first) == ["1hair01", "1hair02", "1hair03"]  # need-led as before: the noted need words
    assert result.slimmed == 3 and (result.about_by_title, result.about_by_title_or_post) == (1, 1)
    assert "(3 slimmed: their posts' words are gone, judged by title only)" in need_lines([result])[0]
