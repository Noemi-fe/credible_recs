"""Module 3's reading step through Google's Gemini (Noemi, 12 Oct 2026: a quality test on her labelled threads first).

Every test uses a stand-in for Gemini: no test reaches the network (engine/tests/conftest.py blocks it).
"""

import json
from pathlib import Path

import pytest

from engine import gemini_extract
from engine.extract import check_extraction, current_instructions_version, load_checked
from engine.gemini_extract import GeminiClient, GeminiError, extract_threads
from engine.models import Thread
from engine.tests.factories import make_thread, write_gold

QUOTE = "I've used the CeraVe SA Cleanser for 2 years."  # in comment c1aaaa of the made-up thread (factories)


class FakeFetch:
    """Answers every request with one canned reply, and remembers what it was sent."""

    def __init__(self, reply: dict | str):
        self.reply = reply
        self.sent: list[dict] = []

    def __call__(self, url: str, headers: dict, body: bytes) -> dict:
        self.sent.append({"url": url, "headers": headers, "body": json.loads(body)})
        text = self.reply if isinstance(self.reply, str) else json.dumps(self.reply)
        return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def a_reply(**overrides) -> dict:
    """What Gemini writes for the made-up thread: one mention, its quote copied word for word."""
    reply = {"thread_id": "anything", "instructions_version": "old", "extracted_at": "2020-01-01T00:00:00Z",
             "extractor": "someone", "mentions": [{
                 "comment_id": "c1aaaa", "product": "CeraVe SA Cleanser", "category": "skincare",
                 "product_type": "cleanser", "stance": "recommend", "evidence": "long-term use",
                 "evidence_tags": ["long-term use"], "quote": QUOTE}]}
    reply.update(overrides)
    return reply


def folder(tmp_path: Path) -> Path:
    write_gold(tmp_path, [make_thread()], voices=None, mentions=None)
    return tmp_path / "threads"


def test_the_request_carries_the_instructions_and_the_thread_and_the_key_only_in_a_header(tmp_path):
    fetch = FakeFetch(a_reply())
    client = GeminiClient(key="test-key", model="gemini-test", fetch=fetch, sleep=lambda s: None)
    extract_threads(folder(tmp_path), tmp_path / "out", client, ids=["1fake01"])
    [sent] = fetch.sent
    assert sent["url"].endswith("/models/gemini-test:generateContent") and "test-key" not in sent["url"]
    assert sent["headers"]["x-goog-api-key"] == "test-key"
    body = sent["body"]
    assert "Finding product mentions" in body["systemInstruction"]["parts"][0]["text"]  # the extraction instructions
    user = body["contents"][0]["parts"][0]["text"]
    assert "Thread 1fake01" in user and QUOTE in user  # the reading view the AI agents read
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["temperature"] == 0


def test_the_answer_becomes_an_extraction_file_marked_as_geminis(tmp_path):
    client = GeminiClient(key="test-key", model="gemini-test", fetch=FakeFetch(a_reply()), sleep=lambda s: None)
    out = tmp_path / "out"
    report = extract_threads(folder(tmp_path), out, client, ids=["1fake01"])
    assert report.written == ["1fake01"] and report.failed == {}
    saved = json.loads((out / "extracted" / "1fake01.json").read_text(encoding="utf-8"))
    # The bookkeeping is ours, whatever the model wrote: the thread, the instructions followed, when and by what.
    assert saved["thread_id"] == "1fake01" and saved["extractor"] == "gemini:gemini-test"
    assert saved["instructions_version"] == current_instructions_version()
    checked = load_checked(out / "threads")["1fake01"]  # the same word-for-word checks as every extraction
    assert [m.product for m in checked.kept] == ["CeraVe SA Cleanser"] and checked.rejected == []


def test_a_reply_that_isnt_an_extraction_is_reported_and_nothing_is_written(tmp_path):
    for reply in ("not json at all", {"mentions": [{"comment_id": "c1aaaa"}]}):
        client = GeminiClient(key="test-key", model="gemini-test", fetch=FakeFetch(reply), sleep=lambda s: None)
        out = tmp_path / "out"
        report = extract_threads(folder(tmp_path), out, client, ids=["1fake01"])
        assert report.written == [] and "1fake01" in report.failed
        assert not (out / "extracted" / "1fake01.json").exists()


def test_an_unlabelled_gold_thread_is_never_sent(tmp_path, monkeypatch):
    # Noemi's rule (10 Oct 2026): no AI reads a gold thread before she has labelled it (anchoring).
    monkeypatch.setattr(gemini_extract, "unlabelled_gold_ids", lambda: {"1fake01"})
    fetch = FakeFetch(a_reply())
    client = GeminiClient(key="test-key", model="gemini-test", fetch=fetch, sleep=lambda s: None)
    report = extract_threads(folder(tmp_path), tmp_path / "out", client, ids=["1fake01"])
    assert fetch.sent == [] and report.written == [] and "1fake01" in report.skipped


def test_without_a_key_nothing_is_sent(tmp_path, monkeypatch):
    monkeypatch.setattr(gemini_extract, "_key_from_env_file", lambda: "")
    monkeypatch.delenv(gemini_extract.KEY_NAME, raising=False)
    with pytest.raises(GeminiError, match="GEM_API_KEY"):
        GeminiClient(fetch=lambda *a: pytest.fail("nothing may be sent")).generate("system", "user")


def test_a_busy_model_is_asked_again_after_a_pause():
    # 12 Oct 2026: the quality test met "503: This model is currently experiencing high demand" on one thread.
    answers = [GeminiError("Gemini answered 503: high demand", status=503), GeminiError("429: slow down", status=429),
               {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}]
    pauses = []

    def fetch(url, headers, body):
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    client = GeminiClient(key="test-key", fetch=fetch, sleep=pauses.append, min_interval=0)
    assert client.generate("system", "user") == "{}"
    assert len(pauses) == 2 and pauses[0] > 0 and pauses[1] > pauses[0]


def test_a_model_that_stays_busy_is_reported():
    def fetch(url, headers, body):
        raise GeminiError("Gemini answered 503: high demand", status=503)

    client = GeminiClient(key="test-key", fetch=fetch, sleep=lambda s: None, min_interval=0)
    with pytest.raises(GeminiError, match="503"):
        client.generate("system", "user")


def test_a_refusal_isnt_retried():
    calls = []

    def fetch(url, headers, body):
        calls.append(1)
        raise GeminiError("Gemini answered 400: bad request", status=400)

    with pytest.raises(GeminiError):
        GeminiClient(key="test-key", fetch=fetch, sleep=lambda s: None, min_interval=0).generate("system", "user")
    assert len(calls) == 1


def test_the_thinking_level_can_be_raised():
    fetch = FakeFetch({"mentions": []})
    GeminiClient(key="test-key", fetch=fetch, sleep=lambda s: None, thinking="high").generate("system", "user")
    assert fetch.sent[0]["body"]["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "high"}
    fetch = FakeFetch({"mentions": []})
    GeminiClient(key="test-key", fetch=fetch, sleep=lambda s: None).generate("system", "user")
    assert "thinkingConfig" not in fetch.sent[0]["body"]["generationConfig"]  # the model's own default


def test_a_long_thread_is_read_in_parts_and_the_parts_joined(tmp_path):
    # 12 Oct 2026: Gemini found 84% of Noemi's labelled products against Claude's 97%; long threads are read in parts
    # of PART_COMMENTS comments, each with the post, and the parts' extractions are joined into one.
    from engine.tests.factories import make_comment

    comments = [make_comment(f"c{i:04d}", body=f"The Brand{i} cleanser is great, used it for {i} years.") for i in range(5)]
    write_gold(tmp_path, [make_thread(comments=comments)], voices=None, mentions=None)
    sent_ids = []

    def fetch(url, headers, body):
        text = json.loads(body)["contents"][0]["parts"][0]["text"]
        ids = [c["id"] for c in comments if f"[{c['id']}]" in text]
        sent_ids.append(ids)
        mentions = [{"comment_id": cid, "product": f"Brand{int(cid[1:])} cleanser", "category": "skincare",
                     "product_type": "cleanser", "stance": "recommend", "evidence": "long-term use",
                     "evidence_tags": ["long-term use"], "quote": f"The Brand{int(cid[1:])} cleanser is great"}
                    for cid in ids]
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({"mentions": mentions})}]}}]}

    client = GeminiClient(key="test-key", model="gemini-test", fetch=fetch, sleep=lambda s: None, min_interval=0)
    report = extract_threads(tmp_path / "threads", tmp_path / "out", client, ids=["1fake01"], part_comments=2)
    assert report.written == ["1fake01"]
    assert [len(ids) for ids in sent_ids] == [2, 2, 1]  # three parts, every comment in exactly one
    saved = json.loads((tmp_path / "out" / "extracted" / "1fake01.json").read_text(encoding="utf-8"))
    assert sorted(m["comment_id"] for m in saved["mentions"]) == [c["id"] for c in comments]
