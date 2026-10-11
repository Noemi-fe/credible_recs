"""Feedback from visitors, kept anonymously (engine/feedback.py; Noemi, 11 Oct 2026: going live).

Every text here is made up. No test reaches the network: the Hugging Face store gets a fake API, and the reader a fake
download.
"""

import json
import sys
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import get_args

import pytest

from engine import feedback
from engine.config import (FEEDBACK_MAX_COMMENT_CHARS, FEEDBACK_MAX_PRODUCT_TYPE_CHARS, FEEDBACK_UPLOAD_EVERY_SECONDS,
                           WEB_MAX_REQUEST_CHARS)
from engine.query import ParsedQuery

NOW = datetime(2026, 10, 11, 18, 40, 5, tzinfo=UTC)
USEFUL = {"kind": "answer_feedback", "request": "electric kettle that lasts 10+ years", "verdict": "useful",
          "comment": "Clear and quick, thanks.", "product_type": "electric kettle", "status": "ok"}
FIRST_TIME = {"kind": "first_time", "answer": "yes"}


# --- What is kept: exactly the fields sent, and the time ---

def test_feedback_on_an_answer_keeps_its_fields_and_the_time_and_nothing_else():
    assert feedback.parse_record(USEFUL, now=NOW) == {**USEFUL, "received_at": "2026-10-11T18:40:05Z"}


def test_a_first_time_answer_keeps_only_the_yes_or_no_and_the_time():
    assert feedback.parse_record(FIRST_TIME, now=NOW) == {"kind": "first_time", "answer": "yes",
                                                          "received_at": "2026-10-11T18:40:05Z"}
    assert feedback.parse_record({"kind": "first_time", "answer": "no"}, now=NOW)["answer"] == "no"


@pytest.mark.parametrize("comment, product_type", [(None, None), ("", ""), ("   ", "  ")])
def test_the_comment_and_the_product_type_may_be_left_out(comment, product_type):
    sent = {**USEFUL, "comment": comment, "product_type": product_type, "status": "clarify"}
    record = feedback.parse_record(sent, now=NOW)
    assert record["comment"] is None and record["product_type"] is None
    without = {key: value for key, value in USEFUL.items() if key not in ("comment", "product_type")}
    record = feedback.parse_record(without, now=NOW)
    assert record["comment"] is None and record["product_type"] is None


def test_texts_are_kept_without_the_spaces_around_them():
    record = feedback.parse_record({**USEFUL, "request": "  rice cooker  ", "comment": "\n Too slow. \n"}, now=NOW)
    assert record["request"] == "rice cooker" and record["comment"] == "Too slow."


def test_texts_may_be_as_long_as_their_limits():
    sent = {**USEFUL, "request": "k" * WEB_MAX_REQUEST_CHARS, "comment": "é" * FEEDBACK_MAX_COMMENT_CHARS,
            "product_type": "p" * FEEDBACK_MAX_PRODUCT_TYPE_CHARS}
    assert feedback.parse_record(sent, now=NOW)["comment"] == "é" * FEEDBACK_MAX_COMMENT_CHARS
    assert FEEDBACK_MAX_COMMENT_CHARS == 1000  # what the page's comment box says


def test_the_kinds_of_answer_are_module_1s_outcomes():
    assert feedback.STATUSES == get_args(ParsedQuery.model_fields["status"].annotation)
    for status in feedback.STATUSES:
        assert feedback.parse_record({**USEFUL, "status": status}, now=NOW)["status"] == status


def test_the_time_is_utc_and_taken_when_the_record_arrives():
    before = datetime.now(UTC).replace(microsecond=0)
    stamp = feedback.parse_record(FIRST_TIME)["received_at"]
    assert stamp.endswith("Z")
    assert datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC) >= before


# --- What is refused: anything off, with plain words saying why ---

@pytest.mark.parametrize("sent, words", [
    (["not", "an", "object"], "JSON object"),
    ("useful", "JSON object"),
    (None, "JSON object"),
    ({**USEFUL, "kind": "rating"}, '"kind"'),
    ({key: value for key, value in USEFUL.items() if key != "kind"}, '"kind"'),
    ({**USEFUL, "ip": "203.0.113.7"}, "ip"),  # an unknown field: nothing about the sender is ever taken in
    ({**USEFUL, "user_agent": "Firefox"}, "user_agent"),
    ({**FIRST_TIME, "request": "kettle"}, "request"),
    ({key: value for key, value in USEFUL.items() if key != "request"}, "request"),
    ({key: value for key, value in USEFUL.items() if key != "verdict"}, "verdict"),
    ({key: value for key, value in USEFUL.items() if key != "status"}, "status"),
    ({"kind": "first_time"}, "answer"),
    ({**USEFUL, "request": 5}, '"request"'),
    ({**USEFUL, "request": None}, '"request"'),
    ({**USEFUL, "request": "   "}, '"request"'),
    ({**USEFUL, "comment": ["a", "list"]}, '"comment"'),
    ({**USEFUL, "product_type": {"a": 1}}, '"product_type"'),
    ({**USEFUL, "verdict": True}, '"verdict"'),
    ({**USEFUL, "verdict": "great"}, '"verdict"'),
    ({**USEFUL, "status": "error"}, '"status"'),
    ({**FIRST_TIME, "answer": "maybe"}, '"answer"'),
    ({**FIRST_TIME, "answer": 1}, '"answer"'),
    ({**USEFUL, "request": "k" * (WEB_MAX_REQUEST_CHARS + 1)}, str(WEB_MAX_REQUEST_CHARS)),
    ({**USEFUL, "comment": "c" * (FEEDBACK_MAX_COMMENT_CHARS + 1)}, "1000"),
    ({**USEFUL, "product_type": "p" * (FEEDBACK_MAX_PRODUCT_TYPE_CHARS + 1)}, str(FEEDBACK_MAX_PRODUCT_TYPE_CHARS)),
])
def test_a_record_that_breaks_a_rule_is_refused_with_words_saying_why(sent, words):
    with pytest.raises(feedback.FeedbackError) as refused:
        feedback.parse_record(sent, now=NOW)
    assert words in str(refused.value)


# --- The local store: one JSON line per record, on this machine ---

def test_the_local_store_appends_one_json_line_per_record(tmp_path):
    store = feedback.LocalStore(tmp_path / "feedback" / "feedback.jsonl")
    first = feedback.parse_record({**USEFUL, "comment": "Très utile, merci."}, now=NOW)
    second = feedback.parse_record(FIRST_TIME, now=NOW)
    store.add(first)
    store.add(second)
    lines = (tmp_path / "feedback" / "feedback.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [first, second]
    assert "Très utile" in lines[0]  # written as it was typed, not escaped
    store.close()  # nothing to do, and no error


def test_the_local_store_keeps_every_record_whole_when_many_arrive_at_once(tmp_path):
    store = feedback.LocalStore(tmp_path / "feedback.jsonl")
    record = feedback.parse_record({**USEFUL, "comment": "x" * 900}, now=NOW)
    writers = [threading.Thread(target=lambda: [store.add(record) for _ in range(20)]) for _ in range(10)]
    for writer in writers:
        writer.start()
    for writer in writers:
        writer.join()
    lines = (tmp_path / "feedback.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 200 and all(json.loads(line) == record for line in lines)


def test_the_local_stores_file_is_in_the_git_ignored_feedback_folder():
    assert feedback.DEFAULT_FILE == feedback.REPO_ROOT / "data" / "feedback" / "feedback.jsonl"
    ignored = (feedback.REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/feedback/" in ignored


# --- The Hugging Face store: batches uploaded to a private dataset ---

class FakeHub:
    """Stands in for huggingface_hub.HfApi: records each upload; never reaches the network."""

    def __init__(self, private: bool = True, fail: bool = False):
        self.private = private
        self.fail = fail
        self.uploads: list[dict] = []
        self.during_upload = None  # called in the middle of an upload, to add a record meanwhile

    def repo_info(self, repo_id, repo_type=None, **kwargs):
        assert repo_type == "dataset"
        return SimpleNamespace(id=repo_id, private=self.private)

    def upload_file(self, *, path_or_fileobj, path_in_repo, repo_id, repo_type=None, commit_message=None, **kwargs):
        if self.during_upload:
            self.during_upload()
        if self.fail:
            raise ConnectionError("the Hub could not be reached")
        self.uploads.append({"content": path_or_fileobj, "path": path_in_repo, "repo_id": repo_id,
                             "repo_type": repo_type, "message": commit_message})

    def records(self, upload: dict) -> list[dict]:
        return [json.loads(line) for line in upload["content"].decode("utf-8").splitlines()]


def hub_store(hub: FakeHub, **kwargs) -> feedback.HubStore:
    logged = []
    store = feedback.HubStore(hub, "noemi-test/credible-recs-feedback", start=False, log=logged.append, **kwargs)
    store.logged = logged
    return store


def test_the_hub_store_uploads_nothing_until_it_flushes_then_one_file_for_the_whole_batch():
    hub = FakeHub()
    store = hub_store(hub)
    records = [feedback.parse_record(USEFUL, now=NOW), feedback.parse_record(FIRST_TIME, now=NOW)]
    for record in records:
        store.add(record)
    assert hub.uploads == []  # a click never makes a commit of its own
    assert store.flush() == 2
    (upload,) = hub.uploads
    assert upload["repo_id"] == "noemi-test/credible-recs-feedback" and upload["repo_type"] == "dataset"
    assert upload["path"].startswith("feedback/") and upload["path"].endswith(".jsonl")
    assert hub.records(upload) == records
    assert store.flush() == 0 and len(hub.uploads) == 1  # nothing waiting: nothing uploaded


def test_each_batch_is_a_new_file_so_no_upload_overwrites_an_earlier_one():
    hub = FakeHub()
    store = hub_store(hub)
    for _ in range(3):
        store.add(feedback.parse_record(FIRST_TIME, now=NOW))
        store.flush()
    paths = [upload["path"] for upload in hub.uploads]
    assert len(paths) == 3 and len(set(paths)) == 3


def test_nothing_is_ever_uploaded_to_a_public_dataset():
    hub = FakeHub(private=False)
    store = hub_store(hub)
    store.add(feedback.parse_record(USEFUL, now=NOW))
    assert store.flush() == 0 and hub.uploads == []
    assert any("public" in line for line in store.logged)
    hub.private = True  # made private: the waiting records go up at the next try
    assert store.flush() == 1


def test_a_failed_upload_keeps_the_records_for_the_next_try_and_logs_no_feedback_text():
    hub = FakeHub(fail=True)
    store = hub_store(hub)
    store.add(feedback.parse_record(USEFUL, now=NOW))
    assert store.flush() == 0 and hub.uploads == []
    assert store.logged and not any(USEFUL["comment"] in line or USEFUL["request"] in line for line in store.logged)
    hub.fail = False
    assert store.flush() == 1 and hub.records(hub.uploads[0])[0]["comment"] == USEFUL["comment"]


def test_records_added_during_an_upload_wait_for_the_next_one():
    hub = FakeHub()
    store = hub_store(hub)
    store.add(feedback.parse_record(USEFUL, now=NOW))
    hub.during_upload = lambda: store.add(feedback.parse_record(FIRST_TIME, now=NOW))
    assert store.flush() == 1
    hub.during_upload = None
    assert store.flush() == 1 and hub.records(hub.uploads[1])[0]["kind"] == "first_time"


def test_too_much_feedback_waiting_is_refused_rather_than_filling_memory(monkeypatch):
    monkeypatch.setattr(feedback, "FEEDBACK_MAX_PENDING", 2)
    store = hub_store(FakeHub(fail=True))
    store.add(feedback.parse_record(FIRST_TIME, now=NOW))
    store.add(feedback.parse_record(FIRST_TIME, now=NOW))
    with pytest.raises(feedback.StoreFull):
        store.add(feedback.parse_record(FIRST_TIME, now=NOW))


def test_closing_the_store_uploads_what_is_waiting():
    hub = FakeHub()
    store = hub_store(hub)
    store.add(feedback.parse_record(USEFUL, now=NOW))
    store.close()
    assert len(hub.uploads) == 1


def test_the_background_thread_uploads_on_its_own():
    hub = FakeHub()
    store = feedback.HubStore(hub, "noemi-test/credible-recs-feedback", every_seconds=0.02, log=lambda line: None)
    try:
        store.add(feedback.parse_record(USEFUL, now=NOW))
        deadline = time.monotonic() + 5
        while not hub.uploads and time.monotonic() < deadline:
            time.sleep(0.01)
        assert len(hub.uploads) == 1
    finally:
        store.close()


def test_uploads_happen_every_few_minutes_by_default():
    assert FEEDBACK_UPLOAD_EVERY_SECONDS >= 300  # Hugging Face advises at least 5 minutes between scheduled commits
    store = hub_store(FakeHub())
    assert store.every_seconds == FEEDBACK_UPLOAD_EVERY_SECONDS
    assert "noemi-test/credible-recs-feedback" in store.describe() and "private" in store.describe()


# --- Which store: the Hugging Face one only when both its settings are there ---

@pytest.mark.parametrize("environ", [{}, {"HF_TOKEN": "hf_made_up"},
                                     {"CREDIBLE_RECS_FEEDBACK_REPO": "noemi-test/credible-recs-feedback"},
                                     {"HF_TOKEN": "  ", "CREDIBLE_RECS_FEEDBACK_REPO": "noemi-test/feedback"}])
def test_without_both_settings_feedback_stays_on_this_machine(environ):
    def no_api(token):
        raise AssertionError("no Hugging Face client should be built")

    store = feedback.store_from_env(environ, make_api=no_api)
    assert isinstance(store, feedback.LocalStore) and store.path == feedback.DEFAULT_FILE


def test_with_both_settings_feedback_goes_to_the_dataset():
    tokens = []

    def make_api(token):
        tokens.append(token)
        return FakeHub()

    environ = {"HF_TOKEN": "hf_made_up", "CREDIBLE_RECS_FEEDBACK_REPO": " noemi-test/credible-recs-feedback "}
    store = feedback.store_from_env(environ, make_api=make_api, start=False)
    assert isinstance(store, feedback.HubStore) and store.repo_id == "noemi-test/credible-recs-feedback"
    assert tokens == ["hf_made_up"]


def test_the_dataset_store_without_huggingface_hub_says_how_to_install_it(monkeypatch):
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)  # as on a machine without the [deploy] extra
    environ = {"HF_TOKEN": "hf_made_up", "CREDIBLE_RECS_FEEDBACK_REPO": "noemi-test/credible-recs-feedback"}
    with pytest.raises(RuntimeError) as refused:
        feedback.store_from_env(environ, start=False)
    assert ".[deploy]" in str(refused.value)


def test_the_local_demo_needs_no_huggingface_hub(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)
    store = feedback.store_from_env({})
    assert isinstance(store, feedback.LocalStore)


# --- Reading the feedback: python -m engine.feedback ---

def made_up_records() -> list[dict]:
    return [
        {**USEFUL, "comment": None, "received_at": "2026-10-12T09:00:00Z"},
        {**USEFUL, "verdict": "not useful", "comment": "Wanted cheaper ones.", "request": "kettle under £30",
         "received_at": "2026-10-12T10:00:00Z"},
        {**USEFUL, "status": "clarify", "product_type": None, "request": "something for my dad",
         "comment": "The question helped.", "received_at": "2026-10-12T11:00:00Z"},
        {"kind": "first_time", "answer": "yes", "received_at": "2026-10-12T09:00:00Z"},
        {"kind": "first_time", "answer": "yes", "received_at": "2026-10-12T09:30:00Z"},
        {"kind": "first_time", "answer": "no", "received_at": "2026-10-12T10:30:00Z"},
    ]


def test_the_summary_counts_ratings_and_first_visits_and_lists_comments_newest_first():
    text = feedback.summary(made_up_records())
    assert "Was this useful? 3 answers rated: 2 useful, 1 not useful" in text
    assert "First time here? 3 answered: 2 yes, 1 no" in text
    assert text.index("The question helped.") < text.index("Wanted cheaper ones.")  # newest first
    assert "kettle under £30" in text and "something for my dad" in text


def test_the_summary_of_nothing_says_so():
    assert "No feedback yet" in feedback.summary([])


def test_reading_skips_lines_that_are_not_records(tmp_path):
    path = tmp_path / "feedback.jsonl"
    path.write_text(json.dumps(made_up_records()[0]) + "\nnot json\n\n[1, 2]\n" + json.dumps(FIRST_TIME) + "\n",
                    encoding="utf-8")
    assert len(feedback.read_records([path])) == 2


def test_the_command_sums_up_the_local_file(tmp_path, monkeypatch, capsys):
    path = tmp_path / "feedback.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in made_up_records()), encoding="utf-8")
    monkeypatch.setattr(feedback, "DEFAULT_FILE", path)
    assert feedback.main([]) == 0
    assert "2 useful, 1 not useful" in capsys.readouterr().out


def test_the_command_with_no_file_yet_says_so(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(feedback, "DEFAULT_FILE", tmp_path / "nothing.jsonl")
    assert feedback.main([]) == 0
    assert "No feedback yet" in capsys.readouterr().out


def test_the_command_downloads_the_spaces_batches_with_the_token_then_sums_them_up(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HF_TOKEN", "hf_made_up")
    monkeypatch.setattr(feedback, "DOWNLOAD_DIR", tmp_path / "downloaded")
    calls = []

    def fake_download(**kwargs):
        calls.append(kwargs)
        folder = Path(kwargs["local_dir"]) / "feedback"
        folder.mkdir(parents=True)
        (folder / "2026-10-12T110000Z-1a2b3c4d.jsonl").write_text(
            "".join(json.dumps(record) + "\n" for record in made_up_records()), encoding="utf-8")
        return str(kwargs["local_dir"])

    assert feedback.main(["--repo", "noemi-test/credible-recs-feedback"], download=fake_download) == 0
    (call,) = calls
    assert call["repo_id"] == "noemi-test/credible-recs-feedback" and call["repo_type"] == "dataset"
    assert call["token"] == "hf_made_up" and call["allow_patterns"] == ["feedback/*.jsonl"]
    assert "2 useful, 1 not useful" in capsys.readouterr().out


def test_the_command_without_a_token_says_where_to_put_it(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    monkeypatch.setattr(feedback, "ENV_FILE", tmp_path / "no.env")

    def no_download(**kwargs):
        raise AssertionError("nothing should be downloaded without a token")

    assert feedback.main(["--repo", "noemi-test/credible-recs-feedback"], download=no_download) == 2
    assert "HF_TOKEN" in capsys.readouterr().out
