"""Feedback from the people who try the demo, kept anonymously (Noemi, 11 Oct 2026: going live).

Two kinds of record come in through POST /api/feedback (engine/web.py), sent by the search page:

    {"kind": "answer_feedback",                     "Was this useful?", under an answer
     "request": "electric kettle that lasts",       the request the answer was for (at most WEB_MAX_REQUEST_CHARS)
     "verdict": "useful" | "not useful",
     "comment": "..." | null,                       optional, at most FEEDBACK_MAX_COMMENT_CHARS characters
     "product_type": "electric kettle" | null,      module 1's product type, when it found one
     "status": "ok" | "clarify" | "out_of_scope"}   the kind of answer: picks, one question first, or a polite no
    {"kind": "first_time", "answer": "yes" | "no"}  "First time here?", to count new and returning visitors

A third kind comes in through POST /api/test-response, sent by the pairwise test's page (/test; engine/pair_test.py, Noemi,
20 Oct 2026), one record per answer, checked by parse_pair:

    {"session": "<28 letters and digits>",          the id the server gave this visit (not tied to anyone)
     "question": "b01",                             the test question's id
     "choice": "A" | "B" | "same",                  the visitor's answer: the side trusted more, or about the same
     "why": "..." | null,                           optional, at most PAIR_MAX_WHY_CHARS characters
     "language": "en" | "it",
     "answered_at": "2026-10-24T20:15:03.512Z"}     the page's clock, UTC

The page never knows which tool the other answer is, or which side ours is on (25 Oct 2026: nothing a visitor's browser
holds may say, so it is never in the page or in what the page sends). The server works both out from the visit's id
(engine/pair_test.py sides_of, passed in as `sides`) and keeps them in the record:

     "rival": "chatgpt" | "vetted",                 the tool ours was set against
     "ours_side": "A" | "B",                        the side ours was shown on

A page that sends either is refused. It is kept as the kind "blind_pair" (the server sets the kind; a body that names one
is refused), with the time it arrived, in the same store; `python -m engine.blind_test tally-pairs` counts them.

parse_record checks each one strictly: an unknown kind or field, a missing field, a value of the wrong type or a text
over its limit is refused, with plain words saying why, and nothing is kept. What is kept is those fields and the time
the record arrived (UTC, "received_at"), and nothing else: no IP address, no browser details, no cookie, no name. The
page asks people not to put personal details in a comment.

Where records go (store_from_env):
- LocalStore, the default: one JSON line per record, appended to data/feedback/feedback.jsonl (git-ignored, so it stays
  on this machine).
- HubStore, on the Hugging Face Space, when both CREDIBLE_RECS_FEEDBACK_REPO (Noemi's private dataset, "owner/name")
  and HF_TOKEN are set. Records wait in memory and go up together, at most every FEEDBACK_UPLOAD_EVERY_SECONDS, each
  batch as a new file in the dataset's feedback/ folder: a click never makes a commit of its own, and no upload ever
  overwrites an earlier one (the Space's disk is wiped at every restart, so one growing file would be). Just before
  each upload the dataset is checked to be private: a public one gets nothing. When the server stops, what is waiting
  goes up first. huggingface_hub is needed for this store only (pip install -e ".[deploy]"); the local demo works
  without it.

Reading it all:
    python -m engine.feedback                      sums up the local file
    python -m engine.feedback --repo OWNER/NAME    downloads the Space's batches from the dataset first (with HF_TOKEN,
                                                   from the environment or .env), into data/feedback/downloaded/
"""

import json
import os
import re
import secrets
import sys
import threading
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from engine.config import (FEEDBACK_MAX_COMMENT_CHARS, FEEDBACK_MAX_PENDING, FEEDBACK_MAX_PRODUCT_TYPE_CHARS,
                           FEEDBACK_UPLOAD_EVERY_SECONDS, PAIR_TEST_MAX_WHY_CHARS, WEB_MAX_REQUEST_CHARS)
from engine.parse_reddit import DEFAULT_ENV_FILE as ENV_FILE
from engine.parse_reddit import _read_env_file

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FILE = REPO_ROOT / "data" / "feedback" / "feedback.jsonl"
DOWNLOAD_DIR = REPO_ROOT / "data" / "feedback" / "downloaded"  # the Space's batches, once read here (git-ignored too)
REPO_VAR = "CREDIBLE_RECS_FEEDBACK_REPO"  # the private dataset feedback goes to, "owner/name" (a Space variable)
TOKEN_VAR = "HF_TOKEN"  # the Hugging Face token (a Space secret; on this machine, in .env)
REPO_FOLDER = "feedback"  # the dataset's folder the batches go into

KINDS = ("answer_feedback", "first_time")
VERDICTS = ("useful", "not useful")
STATUSES = ("ok", "clarify", "out_of_scope")  # module 1's outcomes (engine.query.ParsedQuery.status); a test checks
FIRST_TIME_ANSWERS = ("yes", "no")
# The pairwise test's answers (20 Oct 2026): their own kind, which only POST /api/test-response takes.
PAIR_KIND = "blind_pair"
STORED_KINDS = KINDS + (PAIR_KIND,)  # what the store holds and reading takes in
PAIR_RIVALS = ("chatgpt", "vetted")
PAIR_SIDES = ("A", "B")
PAIR_CHOICES = ("A", "B", "same")
PAIR_LANGUAGES = ("en", "it")
PAIR_MAX_WHY_CHARS = PAIR_TEST_MAX_WHY_CHARS
PAIR_REQUIRED = ("session", "question", "choice", "language", "answered_at")  # what the page sends
PAIR_OPTIONAL = ("why",)
_PAIR_SESSION = re.compile(r"[A-Za-z0-9_-]{8,64}")
_PAIR_QUESTION = re.compile(r"[A-Za-z0-9_-]{1,16}")
_PAIR_TIME = re.compile(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.\d{1,6})?Z")
# The kinds of answer, in words, for the summary.
STATUS_WORDS = {"ok": "answers with picks", "clarify": "a question first", "out_of_scope": "a polite no"}


class FeedbackError(ValueError):
    """A record that can't be kept. Its words say why, for whoever calls the API."""


class StoreFull(RuntimeError):
    """Too much feedback is waiting to be uploaded (the uploads keep failing): new feedback is refused, not kept."""


# --- Checking a record ---

def parse_record(data: object, now: datetime | None = None) -> dict:
    """The record to keep, from the JSON a page sent: its fields, checked, and the time it arrived (UTC, to the second).
    Raises FeedbackError when anything is off; nothing is kept then."""
    if not isinstance(data, dict):
        raise FeedbackError("Send one JSON object.")
    if data.get("kind") == "answer_feedback":
        _only(data, required=("kind", "request", "verdict", "status"), optional=("comment", "product_type"))
        record = {"kind": "answer_feedback",
                  "request": _text(data, "request", WEB_MAX_REQUEST_CHARS, required=True),
                  "verdict": _one_of(data, "verdict", VERDICTS),
                  "comment": _text(data, "comment", FEEDBACK_MAX_COMMENT_CHARS),
                  "product_type": _text(data, "product_type", FEEDBACK_MAX_PRODUCT_TYPE_CHARS),
                  "status": _one_of(data, "status", STATUSES)}
    elif data.get("kind") == "first_time":
        _only(data, required=("kind", "answer"), optional=())
        record = {"kind": "first_time", "answer": _one_of(data, "answer", FIRST_TIME_ANSWERS)}
    else:
        raise FeedbackError(f'"kind" must be one of: {_listed(KINDS)}.')
    record["received_at"] = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return record


def parse_pair(data: object, sides, now: datetime | None = None) -> dict:
    """The record to keep for one answer of the pairwise test: its fields, checked, as the kind "blind_pair", and the
    time it arrived. The page's own clock is kept to the second (UTC). `sides(session, question)` gives the rival and
    ours' side for that visit's question as ("chatgpt" | "vetted", "A" | "B"), or None when the visit was never asked
    that question (the answer is then refused). Raises FeedbackError when anything is off."""
    if not isinstance(data, dict):
        raise FeedbackError("Send one JSON object.")
    _only(data, required=PAIR_REQUIRED, optional=PAIR_OPTIONAL)
    session = _matching(data, "session", _PAIR_SESSION, "8 to 64 letters, digits, - or _")
    question = _matching(data, "question", _PAIR_QUESTION, "1 to 16 letters, digits, - or _")
    checked = {"choice": _one_of(data, "choice", PAIR_CHOICES), "why": _text(data, "why", PAIR_MAX_WHY_CHARS),
               "language": _one_of(data, "language", PAIR_LANGUAGES), "answered_at": _page_time(data)}
    found = sides(session, question)  # last: working out a deck is only done for an answer that is otherwise fine
    if found is None:
        raise FeedbackError(f'"question" {question} is not one of this visit\'s questions.')
    rival, ours_side = found
    assert rival in PAIR_RIVALS and ours_side in PAIR_SIDES, found  # the server's own lookup: a bug, not bad input
    record = {"kind": PAIR_KIND, "session": session, "question": question, "rival": rival, "ours_side": ours_side,
              **checked}
    record["received_at"] = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return record


def _matching(data: dict, name: str, pattern: re.Pattern, words: str) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise FeedbackError(f'"{name}" must be {words}.')
    return value


def _page_time(data: dict) -> str:
    """The page's timestamp (UTC, ending in Z, optional fractions of a second) as a time to the second."""
    value = data.get("answered_at")
    found = _PAIR_TIME.fullmatch(value) if isinstance(value, str) else None
    try:
        if found is None:
            raise ValueError
        datetime.strptime(found.group(1), "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        raise FeedbackError('"answered_at" must be a UTC time such as 2026-10-24T20:15:03Z.') from None
    return found.group(1) + "Z"


def _only(data: dict, required: tuple[str, ...], optional: tuple[str, ...]) -> None:
    """Refuses a field this kind of record doesn't have (anything about the sender included), or a missing one."""
    unknown = sorted(set(data) - set(required) - set(optional))
    if unknown:
        raise FeedbackError(f"Unknown field{'s' if len(unknown) > 1 else ''}: {', '.join(unknown)}. This kind of "
                            f"feedback has only {_listed(required + optional)}.")
    missing = [name for name in required if name not in data]
    if missing:
        raise FeedbackError(f"Missing: {_listed(missing)}.")


def _text(data: dict, name: str, limit: int, required: bool = False) -> str | None:
    """A text field without the spaces around it; None when an optional one is left out or blank."""
    value = data.get(name)
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise FeedbackError(f'"{name}" must be text.')
    value = value.strip()
    if not value:
        if required:
            raise FeedbackError(f'"{name}" is empty.')
        return None
    if len(value) > limit:
        raise FeedbackError(f'"{name}" is {len(value)} characters long; the limit is {limit}.')
    return value


def _one_of(data: dict, name: str, allowed: tuple[str, ...]) -> str:
    value = data.get(name)
    if not isinstance(value, str) or value not in allowed:
        raise FeedbackError(f'"{name}" must be one of: {_listed(allowed)}.')
    return value


def _listed(names) -> str:
    return ", ".join(f'"{name}"' for name in names)


# --- Where records go ---

class LocalStore:
    """Feedback on this machine: each record appended as one JSON line to data/feedback/feedback.jsonl."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else DEFAULT_FILE
        self._lock = threading.Lock()

    def add(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self._lock:  # one record at a time, so two lines never mix
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as file:
                file.write(line)

    def close(self) -> None:
        """Nothing waits here: each record is written as it arrives."""

    def describe(self) -> str:
        return f"kept on this machine, in {self.path}"


class HubStore:
    """Feedback on the Space: records wait in memory and go up in batches to a private Hugging Face dataset.

    `api` is a huggingface_hub.HfApi (the tests give a fake). A background thread uploads every `every_seconds`;
    start=False leaves it to flush() and close(), as the tests do. `log` gets one line per problem, never a record's
    words.
    """

    def __init__(self, api, repo_id: str, every_seconds: float = FEEDBACK_UPLOAD_EVERY_SECONDS, start: bool = True,
                 log=None):
        self.api = api
        self.repo_id = repo_id
        self.every_seconds = every_seconds
        self._log = log or (lambda line: print(line, file=sys.stderr, flush=True))
        self._waiting: list[dict] = []
        self._lock = threading.Lock()  # guards the list of records waiting
        self._uploading = threading.Lock()  # one upload at a time, so no record goes up twice
        self._stop = threading.Event()
        self._thread = None
        if start:
            self._thread = threading.Thread(target=self._upload_regularly, name="feedback-uploads", daemon=True)
            self._thread.start()

    def add(self, record: dict) -> None:
        with self._lock:
            if len(self._waiting) >= FEEDBACK_MAX_PENDING:
                raise StoreFull(f"{len(self._waiting)} records are already waiting to be uploaded")
            self._waiting.append(record)

    def flush(self) -> int:
        """Uploads every record waiting, as one new file; returns how many went up. On any problem (a public dataset,
        no connection, a refused token) nothing goes up: the records keep waiting for the next try, and the problem is
        logged."""
        with self._uploading:
            with self._lock:
                batch = list(self._waiting)
            if not batch:
                return 0
            try:
                if not self.api.repo_info(self.repo_id, repo_type="dataset").private:
                    self._log(f"Feedback not uploaded: the dataset {self.repo_id} is public, and feedback only ever goes "
                              f"to a private one. Make it private (its Settings page); the {len(batch)} records waiting "
                              "go up at the next try.")
                    return 0
                content = "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in batch).encode("utf-8")
                self.api.upload_file(path_or_fileobj=content, path_in_repo=_batch_name(), repo_id=self.repo_id,
                                     repo_type="dataset",
                                     commit_message=f"Feedback: {len(batch)} record{'s' if len(batch) != 1 else ''}")
            except Exception as error:  # no connection, a refused token, ...: nothing is lost, the next try sends them
                self._log(f"Feedback upload to {self.repo_id} failed ({type(error).__name__}: {str(error)[:200]}); "
                          f"{len(batch)} records wait for the next try.")
                return 0
            with self._lock:
                del self._waiting[:len(batch)]  # only those uploaded: records that arrived meanwhile keep waiting
            return len(batch)

    def close(self) -> None:
        """Stops the regular uploads and sends what is waiting (the server calls this as it stops)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=60)
        self.flush()

    def describe(self) -> str:
        return f"uploaded to the private dataset {self.repo_id} every {self.every_seconds / 60:g} minutes"

    def _upload_regularly(self) -> None:
        while not self._stop.wait(self.every_seconds):
            self.flush()


def _batch_name() -> str:
    """A new file for each batch: the time it went up, and a random part so two batches never share a name."""
    return f"{REPO_FOLDER}/{datetime.now(UTC):%Y-%m-%dT%H%M%SZ}-{secrets.token_hex(4)}.jsonl"


def store_from_env(environ=None, make_api=None, start: bool = True):
    """Where feedback goes: Noemi's private dataset when CREDIBLE_RECS_FEEDBACK_REPO and HF_TOKEN are both set (on the
    Space), else this machine's file. `make_api(token)` builds the Hugging Face client (the tests give a fake)."""
    environ = os.environ if environ is None else environ
    repo_id = environ.get(REPO_VAR, "").strip()
    token = environ.get(TOKEN_VAR, "").strip()
    if not (repo_id and token):
        return LocalStore()
    return HubStore((make_api or hub_api)(token), repo_id, start=start)


def hub_api(token: str):
    """huggingface_hub's client, with `token`; a clear error when the package isn't installed."""
    try:
        from huggingface_hub import HfApi
    except ImportError as error:
        raise RuntimeError("Feedback is set to go to a Hugging Face dataset (CREDIBLE_RECS_FEEDBACK_REPO), but the "
                           'huggingface_hub package isn\'t installed: run pip install -e ".[deploy]".') from error
    return HfApi(token=token)


# --- Reading the feedback ---

def read_records(paths) -> list[dict]:
    """Every record in these JSON-lines files. A line that isn't a record (broken, empty, or something else) is skipped."""
    records = []
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict) and record.get("kind") in STORED_KINDS:
                records.append(record)
    return records


def read_pairs(paths) -> list[dict]:
    """The pairwise test's records (kind "blind_pair") in these JSON-lines files, in file order; anything else is left out."""
    return [record for record in read_records(paths) if record.get("kind") == PAIR_KIND]


def summary(records: list[dict]) -> str:
    """The feedback in plain words: how many found answers useful (by kind of answer), the answers to "First time
    here?", and every comment, newest first, with the request it was about."""
    if not records:
        return "No feedback yet."
    rated = [r for r in records if r.get("kind") == "answer_feedback"]
    firsts = [r for r in records if r.get("kind") == "first_time"]
    pairs = [r for r in records if r.get("kind") == PAIR_KIND]
    pair_line = (f"Pairwise test: {_count(len(pairs), 'answer')} from "
                 f"{_count(len({r.get('session') for r in pairs}), 'session')} (python -m engine.blind_test tally-pairs "
                 "counts them).")
    if pairs and not (rated or firsts):
        return pair_line
    verdicts = Counter(r.get("verdict") for r in rated)
    answers = Counter(r.get("answer") for r in firsts)
    lines = [f"Was this useful? {_count(len(rated), 'answer')} rated: {verdicts['useful']} useful, "
             f"{verdicts['not useful']} not useful."]
    for status, words in STATUS_WORDS.items():
        some = [r for r in rated if r.get("status") == status]
        if some:
            lines.append(f"  {words}: {len(some)} rated, {sum(r.get('verdict') == 'useful' for r in some)} useful")
    lines.append(f"First time here? {len(firsts)} answered: {answers['yes']} yes, {answers['no']} no.")
    if pairs:
        lines.append(pair_line)
    comments = sorted((r for r in rated if r.get("comment")), key=lambda r: str(r.get("received_at", "")), reverse=True)
    if comments:
        lines += ["", "Comments, newest first:"]
        for r in comments:
            about = str(r.get("request", "")) + (f" ({r['product_type']})" if r.get("product_type") else "")
            when = str(r.get("received_at", ""))[:16].replace("T", " ")
            lines.append(f'  {when}  {r.get("verdict")}, about "{about}": {r["comment"]}')
    return "\n".join(lines)


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else "s")


def _snapshot_download(**kwargs):
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        raise SystemExit('Reading the Space\'s feedback needs huggingface_hub: run pip install -e ".[deploy]".')
    return snapshot_download(**kwargs)


def main(argv: list[str], download=None) -> int:
    if not argv:
        if not DEFAULT_FILE.is_file():
            print(f"No feedback yet: {DEFAULT_FILE} doesn't exist.")
            return 0
        print(summary(read_records([DEFAULT_FILE])))
        return 0
    if len(argv) != 2 or argv[0] != "--repo" or argv[1].count("/") != 1:
        print(__doc__)
        return 2
    repo_id = argv[1]
    token = os.environ.get(TOKEN_VAR) or _read_env_file(ENV_FILE).get(TOKEN_VAR)
    if not token:
        print(f"No HF_TOKEN: put the line HF_TOKEN=<your Hugging Face token> in {ENV_FILE} "
              "(deploy/huggingface/DEPLOY.md explains which token).")
        return 2
    folder = DOWNLOAD_DIR / repo_id.replace("/", "__")
    try:
        (download or _snapshot_download)(repo_id=repo_id, repo_type="dataset", token=token, local_dir=str(folder),
                                         allow_patterns=[f"{REPO_FOLDER}/*.jsonl"])
    except Exception as error:  # no access, no connection: said plainly, nothing else to do
        print(f"Couldn't download the feedback from {repo_id}: {error}")
        return 1
    files = sorted((folder / REPO_FOLDER).glob("*.jsonl"))
    print(f"{_count(len(files), 'batch file')} from {repo_id}, saved in {folder}.\n")
    print(summary(read_records(files)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
