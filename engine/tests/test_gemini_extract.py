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


# --- The free allowance's daily limit (on-demand reading, 14 Oct 2026) ---
# Gemini's free tier has a daily limit per model. A 429 that names it can't pass before the day resets, so it is never
# retried with pauses (they would only wait and fail again), and a batch stops there instead of failing every thread
# after it: on-demand reading's job is billed while it waits, and comes back tomorrow.

DAILY_429 = ('Gemini answered 429: {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [{"violations": '
             '[{"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]}]}}')
MINUTE_429 = ('Gemini answered 429: {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [{"violations": '
              '[{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]}]}}')


def test_a_429_naming_the_daily_quota_is_the_daily_limit_and_a_per_minute_one_isnt():
    from engine.gemini_extract import is_daily_limit

    assert is_daily_limit(429, DAILY_429)
    assert not is_daily_limit(429, MINUTE_429)  # waiting a minute helps: the usual pauses
    assert not is_daily_limit(503, DAILY_429)


def test_the_daily_limit_is_never_asked_again_after_a_pause():
    from engine.gemini_extract import DailyLimitReached

    calls, pauses = [], []

    def fetch(url, headers, body):
        calls.append(1)
        raise GeminiError(DAILY_429, status=429)

    client = GeminiClient(key="test-key", fetch=fetch, sleep=pauses.append, min_interval=0)
    with pytest.raises(DailyLimitReached):
        client.generate("system", "user")
    assert len(calls) == 1 and pauses == []


def test_a_batch_stops_at_the_daily_limit_and_says_which_threads_werent_sent(tmp_path):
    from engine.gemini_extract import DailyLimitReached

    from engine.tests.factories import make_comment

    threads = [make_thread(id=f"1fake0{n}", url=f"https://www.reddit.com/r/SkincareAddiction/comments/1fake0{n}/x/",
                           comments=[make_comment(f"c{n}aaaa", thread_id=f"1fake0{n}", body=f"{QUOTE} Gentle too.")])
               for n in (1, 2, 3)]
    write_gold(tmp_path, threads, voices=None, mentions=None)
    sent = []

    def fetch(url, headers, body):
        user = json.loads(body)["contents"][0]["parts"][0]["text"]
        sent.append(user.split()[1])
        if len(sent) == 2:
            raise DailyLimitReached(DAILY_429, status=429)
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(a_reply())}]}}]}

    client = GeminiClient(key="test-key", model="gemini-test", fetch=fetch, sleep=lambda s: None, min_interval=0)
    report = extract_threads(tmp_path / "threads", tmp_path / "out", client)
    assert report.written == ["1fake01"] and sent == ["1fake01", "1fake02"]  # the third is never sent
    assert report.stopped and "day" in report.stopped
    assert report.not_sent == ["1fake02", "1fake03"] and report.failed == {}
    assert not (tmp_path / "out" / "extracted" / "1fake02.json").exists()


# --- Two fields that were mixed up, and the post's id (26 Oct 2026) ---
# Gemini 3.1 Flash-Lite had read 28 threads for on-demand answers; the word-for-word check dropped 45 of their mentions.
# 20 had the evidence LEVEL "no first-hand use" written in evidence_tags, which holds reason tags (that level is not
# one); 2 had the post's own id as their comment id. The reader's instructions now say plainly what each field holds,
# and the reply's schema only lets it write the allowed values. The code does NOT repair a wrong tag (which tag fits
# depends on the comment); the check in engine/extract.py still drops it.

from engine import config  # noqa: E402
from engine.extract import ExtractedAgreement, ExtractedCareTip, ExtractedMention, ExtractedNote  # noqa: E402
from engine.gemini_extract import extraction_schema, field_rules  # noqa: E402


def sent_user_text(tmp_path) -> str:
    fetch = FakeFetch(a_reply())
    client = GeminiClient(key="test-key", model="gemini-test", fetch=fetch, sleep=lambda s: None)
    extract_threads(folder(tmp_path), tmp_path / "out", client, ids=["1fake01"])
    return fetch.sent[0]["body"]["contents"][0]["parts"][0]["text"]


def test_the_message_says_the_level_and_the_tags_are_two_fields_and_lists_the_allowed_tags(tmp_path):
    user = sent_user_text(tmp_path)
    for level in config.EVIDENCE_LEVELS:
        assert f'"{level}"' in user
    for tag in config.EVIDENCE_TAGS:
        assert f'"{tag}"' in user
    # The one level that is not also a tag is named as never a tag.
    [only_a_level] = [level for level in config.EVIDENCE_LEVELS if level not in config.EVIDENCE_TAGS]
    assert only_a_level == "no first-hand use"
    assert f'The level "{only_a_level}" is not a reason tag' in user
    assert '"evidence" holds one level' in user and '"evidence_tags" holds reason tags' in user


def test_the_message_says_the_posts_id_is_never_a_comment_id(tmp_path):
    user = sent_user_text(tmp_path)
    assert "The thread's id, 1fake01, is the post's" in user and "never write it as a comment_id" in user
    assert "a product named only in the post's own text is not a mention" in user
    assert "[c1aaaa]" in user  # the example of a comment id is a real one from this part


def test_the_rules_follow_the_configured_values_not_a_copy(monkeypatch):
    # The wording is built from config, so a changed list can't leave the instructions behind.
    thread = Thread.model_validate(make_thread())
    monkeypatch.setattr(gemini_extract, "EVIDENCE_TAGS", ("long-term use", "brand new tag"))
    rules = field_rules(thread, ["c1aaaa"])
    assert '"brand new tag"' in rules and '"vague"' not in rules and '"secondhand"' not in rules


def test_a_part_with_no_comments_still_gets_its_rules():
    rules = field_rules(Thread.model_validate(make_thread()), [])
    assert "never write it as a comment_id" in rules and "such as [" not in rules


def test_the_reply_is_asked_for_in_a_schema_that_only_allows_the_allowed_values(tmp_path):
    fetch = FakeFetch(a_reply())
    client = GeminiClient(key="test-key", model="gemini-test", fetch=fetch, sleep=lambda s: None)
    extract_threads(folder(tmp_path), tmp_path / "out", client, ids=["1fake01"])
    config_sent = fetch.sent[0]["body"]["generationConfig"]
    assert config_sent["responseMimeType"] == "application/json"
    schema = config_sent["responseJsonSchema"]
    mention = schema["properties"]["mentions"]["items"]["properties"]
    assert mention["evidence_tags"]["items"]["enum"] == list(config.EVIDENCE_TAGS)
    assert "no first-hand use" not in mention["evidence_tags"]["items"]["enum"]
    assert mention["evidence"]["enum"] == list(config.EVIDENCE_LEVELS)
    assert mention["stance"]["enum"] == list(config.STANCE_VALUE)
    assert mention["category"]["enum"] == list(config.MENTION_CATEGORIES)
    assert mention["evidence_tags"]["minItems"] == 1


def test_a_comment_id_can_only_be_one_of_the_comments_in_that_part(tmp_path):
    from engine.tests.factories import make_comment

    comments = [make_comment(f"c{i:04d}", body=f"The Brand{i} cleanser is great, used it for {i} years.")
                for i in range(3)]
    write_gold(tmp_path, [make_thread(comments=comments)], voices=None, mentions=None)
    fetch = FakeFetch({"mentions": []})
    client = GeminiClient(key="test-key", model="gemini-test", fetch=fetch, sleep=lambda s: None, min_interval=0)
    extract_threads(tmp_path / "threads", tmp_path / "out", client, ids=["1fake01"], part_comments=2)
    allowed = []
    for sent in fetch.sent:
        schema = sent["body"]["generationConfig"]["responseJsonSchema"]["properties"]
        ids = schema["mentions"]["items"]["properties"]["comment_id"]["enum"]
        for kind in ("notes", "care", "agreements"):  # every list's comment ids are limited the same way
            assert schema[kind]["items"]["properties"]["comment_id"]["enum"] == ids
        allowed.append(ids)
    assert allowed == [["c0000", "c0001"], ["c0002"]]  # the post's id (1fake01) is in none of them


def test_a_part_with_no_comments_gets_no_empty_list_of_allowed_ids():
    schema = extraction_schema([])
    assert "enum" not in schema["properties"]["mentions"]["items"]["properties"]["comment_id"]  # Gemini refuses []


def test_the_schema_has_exactly_the_fields_of_the_extraction_models():
    # A field added to a model must be added to the schema, or the reader could never write it.
    schema = extraction_schema(["c1aaaa"])["properties"]
    models = {"mentions": ExtractedMention, "notes": ExtractedNote, "care": ExtractedCareTip,
              "agreements": ExtractedAgreement}
    assert set(schema) == set(models)
    for name, model in models.items():
        item = schema[name]["items"]
        assert set(item["properties"]) == set(model.model_fields), name
        assert set(item["required"]) <= set(item["properties"]), name
        for field, rule in model.model_fields.items():
            if rule.is_required():
                assert field in item["required"], (name, field)


def test_a_wrong_tag_is_not_repaired_by_the_code_and_the_check_still_drops_it(tmp_path):
    # Which tag fits a comment that isn't first-hand depends on the comment ("secondhand", "asks about it"...): the
    # reader chooses, the code never maps the level to a tag, and engine/extract.py's check is unchanged.
    wrong = a_reply()["mentions"][0] | {"evidence": "no first-hand use", "evidence_tags": ["no first-hand use"]}
    client = GeminiClient(key="test-key", model="gemini-test", fetch=FakeFetch(a_reply(mentions=[wrong])),
                          sleep=lambda s: None)
    out = tmp_path / "out"
    assert extract_threads(folder(tmp_path), out, client, ids=["1fake01"]).written == ["1fake01"]
    saved = json.loads((out / "extracted" / "1fake01.json").read_text(encoding="utf-8"))
    assert saved["mentions"][0]["evidence_tags"] == ["no first-hand use"]  # kept as the model wrote it
    checked = load_checked(out / "threads")["1fake01"]
    assert checked.kept == [] and "unknown evidence tag" in checked.rejected[0][1]


def test_a_schema_gemini_refuses_is_dropped_and_the_reading_goes_on_without_it(capsys):
    # The schema is an extra guard: if Gemini answers 400 to it (a complex schema, a changed API), the same request
    # is asked at once without it, once for the client's life, and the word-for-word check does its job as before.
    bodies = []

    def fetch(url, headers, body):
        bodies.append(json.loads(body))
        if "responseJsonSchema" in bodies[-1]["generationConfig"]:
            raise GeminiError("Gemini answered 400: schema too complex", status=400)
        return {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}

    client = GeminiClient(key="test-key", fetch=fetch, sleep=lambda s: None, min_interval=0)
    assert client.generate("system", "user", schema={"type": "object"}) == "{}"
    assert ["responseJsonSchema" in b["generationConfig"] for b in bodies] == [True, False]
    assert client.calls == 2 and "schema too complex" in client.schema_refused
    assert "reading without the schema" in capsys.readouterr().err
    assert client.generate("system", "user", schema={"type": "object"}) == "{}"  # not tried again
    assert len(bodies) == 3 and "responseJsonSchema" not in bodies[-1]["generationConfig"]
    assert client.calls == 3


def test_a_400_without_a_schema_is_still_not_retried():
    calls = []

    def fetch(url, headers, body):
        calls.append(1)
        raise GeminiError("Gemini answered 400: bad request", status=400)

    client = GeminiClient(key="test-key", fetch=fetch, sleep=lambda s: None, min_interval=0)
    with pytest.raises(GeminiError):
        client.generate("system", "user")
    assert len(calls) == 1 and client.schema_refused is None
