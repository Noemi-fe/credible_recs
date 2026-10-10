"""Reads Reddit threads through Bright Data's ready-made Reddit datasets and turns them into our Thread shape.

Bright Data (brightdata.com) is a third-party scraping service, not Reddit's official API. Noemi opened a free-tier
account on 9 Oct 2026: 5,000 records a month, and no charge beyond it (jobs simply stop working). One record is one
post, or one top-level comment with all its replies nested inside it.

Reading one thread takes two jobs on Bright Data's side. Each is started, then its progress is asked every 10 seconds
until it is ready (about a minute for a small thread), then its records are downloaded:
1. the post (1 record): its title, text, writer, score and comment count;
2. its comments (one record per top-level comment, replies inside).
If the post can't be read, the thread's title is taken from its link (the link's words: lower case, maybe cut short),
its text is left empty and its writer unknown, and the command line says so.

What a real read showed (9 Oct 2026, one 8-comment library thread compared with its Parse copy): the 7 comments that
arrived matched Parse's word for word, with the same ids, parents, writers, dates and scores; but replies to replies
(two levels down) don't arrive at all. So a comment missing from a Bright Data read is not evidence that it was
deleted, and the thread's num_comments (Reddit's count) can be higher than the comments kept.

Like the other sources, this client:
- checks the subreddit is one of the decided ones before spending anything;
- caches every answer, so asking twice costs once, and deletes it after 48 hours (the deletion rule);
- logs every record delivered, and refuses to start a job that could go past the month's records;
- picks up a job that took too long the next time the same thread is asked for, instead of paying for a new one;
- turns every problem (a refused key, no records left, a failed or slow job, an unreadable answer, no network) into a
  BrightDataError, so a caller can report it and carry on.

The key goes in .env as BRIGHT_DATA_API_KEY=<your key>. It is only ever sent to Bright Data, in the request's
Authorization header: never printed, logged or cached.

Finding threads (discovery, 10 Oct 2026, while Arctic Shift's archive was down): the same posts dataset can also run
Reddit's own search and return the posts it finds. A search is a subreddit and some words ("SkincareAddiction",
"gentle cleanser"); it is sent as Reddit's search syntax "subreddit:SkincareAddiction gentle cleanser", so the results
stay within that subreddit, most relevant first, from any year. Several searches go in one job. Each post found costs
one record, like any post (so 4 searches of 10 posts cost 40), and the answer holds the whole post, its text and its
first comments included: only what's needed to choose a thread is kept (its id, subreddit, title, comment count and
date), never its text, comments or writers. A post from a subreddit that wasn't asked for is left out (paid for all
the same). A thread chosen from the list is then read with `fetch` as usual.

Command line:
    python -m engine.bright_data fetch <thread link> [<thread link> ...] [--to <folder>]   save threads as JSON files
    python -m engine.bright_data discover [--posts N] <subreddit> "<words>" [<subreddit> "<words>" ...]
                                                   list the threads Reddit's search finds in each subreddit (N each,
                                                   10 by default): ids, titles and comment counts only
    python -m engine.bright_data usage                                                   records used this month
Without --to, threads are saved in a scratch folder outside the project (DEFAULT_THREADS_DIR), never in data/.
"""

import hashlib
import http.client
import json
import os
import re
import ssl
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import certifi

from engine.config import (
    BRIGHT_DATA_COMMENTS_DATASET,
    BRIGHT_DATA_MAX_WAIT_SECONDS,
    BRIGHT_DATA_MONTHLY_RECORDS,
    BRIGHT_DATA_POLL_SECONDS,
    BRIGHT_DATA_POSTS_DATASET,
    BRIGHT_DATA_RECORDS_IF_UNKNOWN,
    CACHE_MAX_AGE_HOURS,
    SUBREDDITS,
)
from engine.gold import unlabelled_gold_ids
from engine.models import Author, Comment, Thread
from engine.parse_reddit import _read_env_file, category_for, parse_thread_url

REPO_ROOT = Path(__file__).resolve().parents[1]
API_URL = "https://api.brightdata.com/datasets/v3/"
DEFAULT_CACHE_DIR = REPO_ROOT / ".cache" / "bright_data"
# Where `fetch` saves threads unless told otherwise: a scratch folder outside the project, so a trial read never
# lands in the library or the gold set (those are filled by their own commands).
DEFAULT_THREADS_DIR = Path(tempfile.gettempdir()) / "credible-recs-bright-data"
# The library's threads folder: a gold-set thread Noemi hasn't labelled yet is never read into it (10 Oct 2026).
LIBRARY_THREADS_DIR = Path(__file__).resolve().parents[1] / "data" / "library" / "threads" / "threads"

MAX_AGE = timedelta(hours=CACHE_MAX_AGE_HOURS)
BUSY_PAUSE = 30.0  # seconds before the one retry when Bright Data says "too many requests" (429)
JOB_NAMES = {BRIGHT_DATA_POSTS_DATASET: "post", BRIGHT_DATA_COMMENTS_DATASET: "comments"}
DISCOVERY_JOB = "discovery"  # a search job on the posts dataset (see "Finding threads" above)
DISCOVER_POSTS_EACH = 10  # posts asked for per search by default: 10 records each
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]+$")
# A comment or reply is recognised by these fields, at whatever depth Bright Data nests it.
_COMMENT_FIELDS = frozenset({"comment_id", "comment", "reply_id", "reply"})
# Words in a refusal that mean the account has run out of records, not that this one request went wrong.
_OUT_OF_RECORDS = ("quota", "balance", "insufficient", "credit")
READ_MORE = " Read more"  # the label of Reddit's button, which Bright Data adds at the end of a post's text


@dataclass(frozen=True)
class FoundPost:
    """A thread a discovery search found: what's needed to choose it, never its text, comments or writer."""

    id: str
    subreddit: str  # as config.SUBREDDITS spells it
    title: str
    num_comments: int  # Reddit's count
    created_at: datetime | None
    url: str  # the thread's own link, ready for `fetch`


class BrightDataError(Exception):
    """Anything that stopped a thread being read.

    `account_problem` is True when the trouble is the account, not this thread (a refused key, no records left this
    month): every other thread would fail the same way, so a caller reading many threads should stop asking.
    """

    def __init__(self, message: str, account_problem: bool = False):
        super().__init__(message)
        self.account_problem = account_problem


@dataclass
class ReadNotes:
    """What happened while reading the last thread, for the command line to report (counts only, never text)."""

    records: int = 0  # records Bright Data delivered for it (0 when it all came from the cache)
    left_out: int = 0  # comments kept out: no id to link or quote them by, or no readable date (their replies too)
    post_read: bool = True  # False: the post couldn't be read, so the title comes from the link (see post_note)
    post_note: str = ""


def default_env_file(repo_root: Path = REPO_ROOT) -> Path:
    """The .env file the key is read from: the project's own, or, in a git worktree that has none, the main copy's.

    A worktree is a second copy of the project that parallel builders work in. Its ".git" is a one-line file,
    "gitdir: <main copy>/.git/worktrees/<name>", which says where the main copy (and its .env) is.
    """
    own = Path(repo_root) / ".env"
    pointer_file = Path(repo_root) / ".git"
    if own.is_file() or not pointer_file.is_file():
        return own
    pointer = pointer_file.read_text(encoding="utf-8").strip()
    gitdir = Path(pointer.removeprefix("gitdir:").strip())
    if pointer.startswith("gitdir:") and gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":
        return gitdir.parent.parent.parent / ".env"
    return own


def _http(method: str, url: str, headers: dict, data: bytes | None = None) -> tuple[int, bytes]:
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    # Python from python.org on macOS has no certificates of its own; certifi brings the standard set.
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urllib.request.urlopen(request, timeout=60, context=context) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as e:
        # No answer at all (a timeout, no network): reported like any Bright Data failure, never a crash.
        raise BrightDataError(f"couldn't reach Bright Data: {getattr(e, 'reason', e)}") from e


class BrightDataClient:
    """Talks to Bright Data. `fetch`, `clock` and `sleep` can be swapped for fakes, which is how the tests avoid
    the network and the waiting."""

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        fetch=_http,
        clock=None,
        sleep=time.sleep,
        env_file: Path | None = None,
        offline: bool = False,
    ):
        self._api_key = api_key
        self.offline = offline  # answer only from the cache: never start a job
        self._env_file = Path(env_file) if env_file else default_env_file()
        self.cache_dir = Path(cache_dir)
        self.usage_log = self.cache_dir / "usage.jsonl"
        self._fetch = fetch
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleep = sleep
        self.last_read = ReadNotes()
        self.purge_cache()

    def get_thread(self, post_url: str) -> Thread:
        """One thread with all its comments, from a link to it (or to one of its comments)."""
        subreddit, post_id = parse_thread_url(post_url)
        category = category_for(subreddit)  # refuses other subreddits before anything is spent
        community = _decided_name(subreddit)
        link = _post_link(post_url, community, post_id)
        self.last_read = notes = ReadNotes()

        try:
            post = _the_post(self._records(BRIGHT_DATA_POSTS_DATASET, link, community, post_id, most_records=1)[1], post_id)
        except BrightDataError as e:
            if e.account_problem:
                raise
            post = None
            notes.post_read = False
            notes.post_note = f"the post couldn't be read ({e}), so its title comes from the link and its text is left empty"

        # Every comments record is a top-level comment, so a thread can't cost more records than it has comments.
        reported = _int(post.get("num_comments"), None) if post else None
        most = max(reported, 1) if reported is not None else BRIGHT_DATA_RECORDS_IF_UNKNOWN
        fetched_at, records = self._records(BRIGHT_DATA_COMMENTS_DATASET, link, community, post_id, most_records=most)
        comments, notes.left_out, errors = flatten_comments(records, community, post_id)
        if not comments and reported != 0:
            # Never hand back an empty thread for one that has comments: a refresh would think they were all deleted.
            if errors:
                raise BrightDataError(f"Bright Data couldn't read the comments of {link}: {errors[0]}")
            said = f", but the post has {reported}" if reported else ""
            raise BrightDataError(f"Bright Data returned no comments for {link}{said}; nothing was saved")
        return to_thread(post, comments, records, link, community, category, fetched_at)

    def discover(self, searches: list[tuple[str, str]], posts_each: int = DISCOVER_POSTS_EACH) -> list[FoundPost]:
        """The threads Reddit's search finds for each (subreddit, words) search, `posts_each` per search, in one job.

        Every subreddit must be a decided one, checked before anything is spent. The job can cost up to
        posts_each records per search, and is refused if that could go past the month's records. Posts from other
        subreddits, error records and a post found twice are left out. The list is cached for 48 hours, like every
        answer (ids, titles, counts and dates only), and a job that took too long is picked up the next time the same
        searches are asked for.
        """
        if not searches:
            raise ValueError("give at least one search: a subreddit and the words to look for")
        if isinstance(posts_each, bool) or not isinstance(posts_each, int) or posts_each < 1:
            raise ValueError(f"posts_each must be a whole number of posts, 1 or more (not {posts_each!r})")
        asked = []
        for subreddit, words in searches:
            category_for(subreddit)  # refuses other subreddits before anything is spent
            if not isinstance(words, str) or not words.strip():
                raise ValueError(f"the search in r/{subreddit} has no words to look for")
            asked.append((_decided_name(subreddit), " ".join(words.split())))
        inputs = [
            {"keyword": f"subreddit:{name} {words}", "date": "All time", "num_of_posts": posts_each, "sort_by": "Relevance"}
            for name, words in asked
        ]

        digest = hashlib.sha256(json.dumps([DISCOVERY_JOB, BRIGHT_DATA_POSTS_DATASET, inputs]).encode()).hexdigest()[:32]
        cache_file = self.cache_dir / "responses" / f"{digest}.json"
        entry = self._cached(cache_file)
        if entry and "found" in entry:
            return [_found_from_json(item) for item in entry["found"]]
        if self.offline:
            raise BrightDataError("offline: no saved answer for these searches; nothing was fetched")
        key = self._key()
        snapshot_id = entry["snapshot_id"] if entry else None  # a job that took too long last time
        if snapshot_id is None:
            self._check_budget(posts_each * len(inputs), DISCOVERY_JOB)
            snapshot_id = self._trigger(
                BRIGHT_DATA_POSTS_DATASET, inputs, key, DISCOVERY_JOB, {"type": "discover_new", "discover_by": "keyword"}
            )
            self._save(cache_file, {"started_at": self._clock().isoformat(), "job": DISCOVERY_JOB, "snapshot_id": snapshot_id})
        records = self._wait_and_download(snapshot_id, key, DISCOVERY_JOB, cache_file)
        self._log(DISCOVERY_JOB, snapshot_id, len(records), "ready")  # every record delivered is paid for
        found = found_posts(records, [name for name, _ in asked])
        self._save(cache_file, {
            "fetched_at": self._clock().isoformat(), "job": DISCOVERY_JOB, "snapshot_id": snapshot_id,
            "found": [_found_to_json(post) for post in found],
        })
        return found

    def records_used_this_month(self) -> int:
        """Records delivered this calendar month, from this client's log (Bright Data's dashboard has the exact figure)."""
        now = self._clock()
        return sum(
            entry["records"] for entry in self._usage_entries() if (entry["at"].year, entry["at"].month) == (now.year, now.month)
        )

    def purge_cache(self) -> None:
        """The deletion rule: removes every cached answer (and every note of a job still running) older than 48 hours."""
        for path in (self.cache_dir / "responses").glob("*.json"):
            try:
                entry = json.loads(path.read_text(encoding="utf-8"))
                saved_at = datetime.fromisoformat(entry.get("fetched_at") or entry["started_at"])
            except (ValueError, KeyError, TypeError, AttributeError):
                saved_at = None
            if saved_at is None or self._clock() - saved_at >= MAX_AGE:
                path.unlink()

    # --- One dataset for one thread: cache, budget, start, wait, download, log ---

    def _records(self, dataset: str, link: str, community: str, post_id: str, most_records: int) -> tuple[datetime, list]:
        """Bright Data's records of one dataset for one thread, and when they were downloaded.

        They come from the cache when it has them; otherwise from a job, which is started (unless one started earlier
        is still waiting to be picked up), waited for and downloaded. `most_records` is the most the job could cost.
        """
        name = JOB_NAMES[dataset]
        cache_file = self._cache_file(dataset, community, post_id)
        entry = self._cached(cache_file)
        if entry and "records" in entry:
            return datetime.fromisoformat(entry["fetched_at"]), entry["records"]
        if self.offline:
            raise BrightDataError(f"offline: no saved {name} answer for {link}; nothing was fetched")
        key = self._key()
        snapshot_id = entry["snapshot_id"] if entry else None  # a job that took too long last time
        if snapshot_id is None:
            self._check_budget(most_records, name)
            snapshot_id = self._start(dataset, link, key)
            self._save(cache_file, {"started_at": self._clock().isoformat(), "job": name, "snapshot_id": snapshot_id})
        records = self._wait_and_download(snapshot_id, key, name, cache_file)
        fetched_at = self._clock()
        self._log(name, snapshot_id, len(records), "ready")
        self.last_read.records += len(records)
        self._save(cache_file, {"fetched_at": fetched_at.isoformat(), "job": name, "snapshot_id": snapshot_id, "records": records})
        return fetched_at, records

    def _check_budget(self, most_records: int, name: str) -> None:
        used = self.records_used_this_month()
        if used + most_records > BRIGHT_DATA_MONTHLY_RECORDS:
            raise BrightDataError(
                f"This {name} job could use up to {most_records} records, which would go past the monthly "
                f"{BRIGHT_DATA_MONTHLY_RECORDS} ({used} used); nothing was fetched.",
                account_problem=used + 1 > BRIGHT_DATA_MONTHLY_RECORDS,  # no records left at all: every thread would fail
            )

    def _start(self, dataset: str, link: str, key: str) -> str:
        """Starts a job about one thread and returns its snapshot id (Bright Data's name for the job)."""
        return self._trigger(dataset, [{"url": link}], key, JOB_NAMES[dataset])

    def _trigger(self, dataset: str, inputs: list[dict], key: str, name: str, extra: dict | None = None) -> str:
        """Starts a job on one dataset with these inputs and returns its snapshot id. `extra` adds to the request's
        parameters (a discovery job says which kind of search it is)."""
        params = {"dataset_id": dataset, "include_errors": "true", **(extra or {})}
        url = API_URL + "trigger?" + urllib.parse.urlencode(params)
        status, data, text = self._ask("POST", url, key, f"starting the {name} job", json.dumps(inputs).encode())
        snapshot_id = data.get("snapshot_id") if status == 200 and isinstance(data, dict) else None
        if not isinstance(snapshot_id, str) or not _SAFE_ID.match(snapshot_id):
            raise BrightDataError(f"Bright Data answered {status} to starting the {name} job, with no job to wait for: {text}")
        return snapshot_id

    def _wait_and_download(self, snapshot_id: str, key: str, name: str, cache_file: Path) -> list:
        """Asks the job's progress every poll interval until it is ready, then downloads its records."""
        deadline = self._clock() + timedelta(seconds=BRIGHT_DATA_MAX_WAIT_SECONDS)
        while True:
            self._sleep(BRIGHT_DATA_POLL_SECONDS)
            progress = self._progress(snapshot_id, key)
            if progress.get("status") == "ready":
                break
            if progress.get("status") == "failed":
                cache_file.unlink(missing_ok=True)  # a failed job is never picked up again
                self._log(name, snapshot_id, 0, "failed")
                reason = progress.get("error") or progress.get("message") or "no reason given"
                raise BrightDataError(f"Bright Data's {name} job {snapshot_id} failed: {str(reason)[:300]}")
            if self._clock() >= deadline:
                raise self._too_slow(name, snapshot_id)

        # A ready job's file can still be "building" for a moment (202): it is asked for again until the same limit.
        deadline = self._clock() + timedelta(seconds=BRIGHT_DATA_MAX_WAIT_SECONDS)
        while True:
            what = f"the download of {name} job {snapshot_id}"
            status, data, text = self._ask("GET", f"{API_URL}snapshot/{snapshot_id}?format=json", key, what)
            if status == 200 and isinstance(data, list):
                return data
            if status != 202:
                raise BrightDataError(f"Bright Data answered {status} to {what}, not a list of records: {text}")
            if self._clock() >= deadline:
                raise self._too_slow(name, snapshot_id)
            self._sleep(BRIGHT_DATA_POLL_SECONDS)

    def _too_slow(self, name: str, snapshot_id: str) -> BrightDataError:
        # Nothing was delivered yet, so no record is logged; the job stays noted in the cache to be picked up.
        self._log(name, snapshot_id, 0, "too slow")
        return BrightDataError(
            f"Bright Data's {name} job {snapshot_id} took longer than {BRIGHT_DATA_MAX_WAIT_SECONDS} seconds; asking "
            f"again for this thread within 48 hours picks the job up instead of paying for a new one"
        )

    def _progress(self, snapshot_id: str, key: str) -> dict:
        """The job's progress ({"status": "running"}, "ready", "failed"...). A check that gets no clear answer returns {}:
        the job carries on at Bright Data, so it is simply asked again at the next poll. A job Bright Data doesn't know
        (404) counts as failed, so it is never waited for again."""
        try:
            status, data, text = self._ask("GET", f"{API_URL}progress/{snapshot_id}", key, f"the progress of job {snapshot_id}")
        except BrightDataError as e:
            if e.account_problem:
                raise
            return {}
        if status == 404:
            return {"status": "failed", "error": f"Bright Data doesn't know this job ({text})"}
        return data if status == 200 and isinstance(data, dict) else {}

    def _ask(self, method: str, url: str, key: str, what: str, body: bytes | None = None) -> tuple[int, object, str]:
        """One request: (status, the answer read as JSON or None, the answer's start as text for messages).

        Refusals that are about the account (a bad key, no records left) raise straight away. When Bright Data says it
        is busy (429), there is one retry after a pause, never a loop.
        """
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"}
        status, raw = self._fetch(method, url, headers, body)
        if status == 429:
            self._sleep(BUSY_PAUSE)
            status, raw = self._fetch(method, url, headers, body)
        text = raw[:300].decode(errors="replace").replace(key, "<key>")  # an answer must never leak the key into a log
        if status in (401, 403):
            raise BrightDataError(
                f"Bright Data refused the key ({status}) on {what}: {text}. Check the line BRIGHT_DATA_API_KEY=<your key> "
                "in the .env file (the key is in the Bright Data dashboard, under account settings).",
                account_problem=True,
            )
        if status == 402 or status == 429 or (status >= 400 and any(word in text.lower() for word in _OUT_OF_RECORDS)):
            raise BrightDataError(
                f"Bright Data refused {what} ({status}): {text}. The account may be out of its monthly records (quota) "
                "or too busy; nothing more was asked.",
                account_problem=True,
            )
        try:
            data = json.loads(raw)
        except ValueError:
            data = None
        return status, data, text

    def _key(self) -> str:
        key = self._api_key or os.environ.get("BRIGHT_DATA_API_KEY") or _read_env_file(self._env_file).get("BRIGHT_DATA_API_KEY")
        if not key:
            raise BrightDataError(
                "No Bright Data key. Add a line BRIGHT_DATA_API_KEY=<your key> to the .env file in the project folder "
                "(the key is in the Bright Data dashboard, under account settings).",
                account_problem=True,
            )
        return key

    # --- Cache and usage log ---

    def _cache_file(self, dataset: str, community: str, post_id: str) -> Path:
        digest = hashlib.sha256(json.dumps([dataset, community.lower(), post_id]).encode()).hexdigest()[:32]
        return self.cache_dir / "responses" / f"{digest}.json"

    def _cached(self, cache_file: Path) -> dict | None:
        """What the cache holds for one thread and dataset, if it is younger than 48 hours: its records, or a job
        still to be picked up."""
        if not cache_file.exists():
            return None
        entry = json.loads(cache_file.read_text(encoding="utf-8"))
        saved_at = datetime.fromisoformat(entry.get("fetched_at") or entry["started_at"])
        return entry if self._clock() - saved_at < MAX_AGE else None

    def _save(self, cache_file: Path, entry: dict) -> None:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")

    def _log(self, name: str, snapshot_id: str, records: int, outcome: str) -> None:
        self.usage_log.parent.mkdir(parents=True, exist_ok=True)
        entry = {"at": self._clock().isoformat(), "dataset": name, "snapshot_id": snapshot_id, "records": records, "outcome": outcome}
        with self.usage_log.open("a", encoding="utf-8") as log:
            log.write(json.dumps(entry) + "\n")

    def _usage_entries(self) -> list[dict]:
        if not self.usage_log.exists():
            return []
        entries = [json.loads(line) for line in self.usage_log.read_text(encoding="utf-8").splitlines() if line.strip()]
        for entry in entries:
            entry["at"] = datetime.fromisoformat(entry["at"])
        return entries


# --- From Bright Data's records to our Thread shape ---

def flatten_comments(records: list, community: str, post_id: str) -> tuple[list[Comment], int, list[str]]:
    """Bright Data's comment records as our flat list of comments, in thread order (each comment, then its replies).

    Each record is a top-level comment with its replies nested inside it, at any depth: a top-level comment gets no
    parent (it answers the post), and a reply gets the id of the comment it is nested in. A comment or reply with no id
    (it couldn't be linked to or quoted) or no readable date is kept out together with its own replies, whose parent
    would be missing: they are counted. A comment given twice is kept once.

    Returns the comments, how many were kept out, and the messages of any error records (Bright Data's way of saying
    one page couldn't be read).
    """
    found: list[tuple[dict, str, str | None, datetime]] = []  # (item, its id, its parent's id, its date)
    seen: set[str] = set()
    errors: list[str] = []
    left_out = 0

    def visit(item: dict, parent_id: str | None) -> None:
        nonlocal left_out
        comment_id = _plain_id(item.get("comment_id") or item.get("reply_id"))
        created_at = _date(item.get("date_posted") or item.get("date_of_reply"))
        if comment_id is None or created_at is None:
            left_out += _count(item)
            return
        if comment_id not in seen:
            seen.add(comment_id)
            found.append((item, comment_id, parent_id, created_at))
        for reply in _nested(item):
            visit(reply, comment_id)

    for record in records:
        if not isinstance(record, dict):
            continue
        if not _COMMENT_FIELDS & record.keys():
            if record.get("error") or record.get("error_code"):
                errors.append(str(record.get("error") or record.get("error_code"))[:300])
            continue
        visit(record, None)

    comments = []
    for item, comment_id, parent_id, created_at in found:
        if parent_id is None:
            # A record Bright Data marks as answering another comment of this thread keeps that comment as its parent.
            # Anything else (no parent, the post itself, the comment's own id) means it answers the post.
            said = _plain_id(item.get("parent_comment_id"))
            parent_id = said if said in seen and said != comment_id else None
        comments.append(_to_comment(item, comment_id, parent_id, created_at, community, post_id))
    return comments, left_out, errors


def found_posts(records: list, subreddits: list[str]) -> list[FoundPost]:
    """The posts a discovery job returned, as FoundPost: only those from the subreddits asked for (Reddit may spell
    them in another case), each once, in the order found. Error records and posts with no id or title are skipped."""
    wanted = {name.lower(): name for name in subreddits}
    found: list[FoundPost] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        post_id = _plain_id(record.get("post_id"))
        title, community = record.get("title"), record.get("community_name")
        if post_id is None or not isinstance(title, str) or not title.strip() or not isinstance(community, str):
            continue
        name = wanted.get(community.strip().removeprefix("r/").lower())
        if name is None or post_id in seen:
            continue
        seen.add(post_id)
        found.append(FoundPost(
            id=post_id, subreddit=name, title=title.strip(), num_comments=_int(record.get("num_comments")),
            created_at=_date(record.get("date_posted")), url=f"https://www.reddit.com/r/{name}/comments/{post_id}/",
        ))
    return found


def _found_to_json(post: FoundPost) -> dict:
    return {**post.__dict__, "created_at": post.created_at.isoformat() if post.created_at else None}


def _found_from_json(item: dict) -> FoundPost:
    return FoundPost(**{**item, "created_at": datetime.fromisoformat(item["created_at"]) if item["created_at"] else None})


def to_thread(post: dict | None, comments: list[Comment], records: list, link: str, community: str, category: str,
              collected_at: datetime) -> Thread:
    """The Thread, from the post's record (None when it couldn't be read) and the comments already flattened.

    `collected_at` is when the comments were downloaded (for the deletion rule and for recency).
    Without the post, the title comes from the link's words, the text is empty, the writer unknown, the score 0,
    the comment count is the comments read, and the date is the earliest comment's (the post can't be later).
    """
    post_id = parse_thread_url(link)[1]
    earliest = min((c.created_at for c in comments), default=None)
    if post is None:
        title = _title_from_link(link) or next(
            (t for r in records if isinstance(r, dict) and (t := _title_from_link(r.get("post_url")))), f"Reddit thread {post_id}"
        )
        body, author, score, num_comments, created_at, url = "", None, 0, len(comments), earliest, link
    else:
        title = post["title"]
        # Kept exactly as written, except the label of Reddit's "Read more" button that Bright Data adds at the end
        # (seen on 9 Oct 2026; its "description_markdown" is HTML-escaped and padded, so it isn't used).
        text = post.get("description") if isinstance(post.get("description"), str) else ""
        body = text.removesuffix(READ_MORE)
        author = _author(post.get("user_posted"))
        score = _int(post.get("num_upvotes"))
        num_comments = max(_int(post.get("num_comments"), len(comments)), 0)
        created_at = _date(post.get("date_posted")) or earliest
        own_url = post.get("url")
        url = own_url if isinstance(own_url, str) and _is_web_url(own_url) and f"/comments/{post_id}" in own_url else link
    if created_at is None:
        raise BrightDataError(f"Bright Data's answer for {link} has no date for the post or any comment")
    return Thread(
        id=post_id,
        source="reddit",
        community=community,
        category=category,
        title=title,
        body=body,
        author=author,
        created_at=created_at,
        score=score,
        num_comments=num_comments,
        url=url,
        collected_at=collected_at,
        comments=comments,
        read_from="bright_data",  # Reddit as it is now: checked live when read
        checked_live_at=collected_at,
    )


def _to_comment(item: dict, comment_id: str, parent_id: str | None, created_at: datetime, community: str, post_id: str) -> Comment:
    text = item.get("comment") if item.get("comment") is not None else item.get("reply")
    body = text if isinstance(text, str) else ""  # kept exactly as written
    # "[deleted]" and "[removed]" are what Reddit shows in place of a deleted or removed comment. A comment with no
    # text at all (only an image, or nothing Bright Data could read) is kept, so its replies keep their parent, but it
    # is marked deleted: there is nothing in it to quote.
    status = {"[deleted]": "deleted", "[removed]": "removed"}.get(body.strip(), "ok") if body.strip() else "deleted"
    own_url = item.get("url")
    # The live check reads the comment named at the end of the link, so a link that doesn't end with this comment's id
    # (a reply has none; its "user_url" is the writer's profile) is replaced by one built from the ids.
    if isinstance(own_url, str) and _is_web_url(own_url) and _last_part(own_url) == comment_id:
        url = own_url
    else:
        url = f"https://www.reddit.com/r/{community}/comments/{post_id}/comment/{comment_id}/"
    return Comment(
        id=comment_id,
        parent_id=parent_id,
        author=_author(item.get("user_posted") or item.get("user_replying")),
        body=body,
        created_at=created_at,
        score=_int(item.get("num_upvotes")),
        url=url,
        status=status,
    )


def _the_post(records: list, post_id: str) -> dict:
    """The post's record among Bright Data's answer about it; an answer without one (an error record) is an error."""
    for record in records:
        if isinstance(record, dict) and isinstance(record.get("title"), str) and record["title"].strip():
            if _plain_id(record.get("post_id")) in (None, post_id):
                return record
    errors = [str(r.get("error") or r.get("error_code")) for r in records if isinstance(r, dict) and (r.get("error") or r.get("error_code"))]
    raise BrightDataError(f"Bright Data's answer about the post has no title: {errors[0][:300] if errors else 'an empty answer'}")


def _nested(item: dict) -> list[dict]:
    """The replies held inside a comment or reply, under whatever field Bright Data puts them ("replies" so far).
    Lists of other things (a reply's images) are not replies: a reply is recognised by its id or text fields."""
    replies = []
    for value in item.values():
        if isinstance(value, list):
            replies += [v for v in value if isinstance(v, dict) and _COMMENT_FIELDS & v.keys()]
    return replies


def _count(item: dict) -> int:
    """This comment and every reply nested inside it."""
    return 1 + sum(_count(reply) for reply in _nested(item))


def _author(name) -> Author | None:
    # Bright Data gives only the name: no account age, karma or flair (engine/profiles.py can add those).
    if not isinstance(name, str) or not name.strip() or name.strip().lower() in ("[deleted]", "u/[deleted]"):
        return None
    return Author(name=name.strip().removeprefix("/").removeprefix("u/"))


def _date(value) -> datetime | None:
    """A date as Bright Data writes it ("2025-03-01T10:00:00.000Z"), in UTC and to the second, as Reddit's own dates
    are (Bright Data adds milliseconds to a post's date); None when there is none to read."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return datetime.fromtimestamp(int(value), UTC)
    if not isinstance(value, str):
        return None
    try:
        moment = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    moment = moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)
    return moment.replace(microsecond=0)


def _int(value, default: int | None = 0) -> int | None:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _plain_id(value) -> str | None:
    """A Reddit id without its type prefix ("t1_" for comments, "t3_" for posts); None when there is no usable id."""
    if value is None or isinstance(value, bool):
        return None
    plain = str(value).strip().removeprefix("t1_").removeprefix("t3_")
    return plain if _SAFE_ID.match(plain) else None


def _is_web_url(value: str) -> bool:
    return bool(re.match(r"^https?://\S+$", value))


def _last_part(url: str) -> str:
    parts = [p for p in urllib.parse.urlparse(url).path.split("/") if p]
    return parts[-1] if parts else ""


def _decided_name(subreddit: str) -> str:
    """The subreddit as config.SUBREDDITS spells it ("skincareaddiction" -> "SkincareAddiction")."""
    name = subreddit.strip().removeprefix("r/").lower()
    return next(s for subs in SUBREDDITS.values() for s in subs if s.lower() == name)


def _post_link(url: str, community: str, post_id: str) -> str:
    """The thread's own web address, from any link to it: www.reddit.com, its title words if the link had them, no
    comment id or extra parameters. This is what Bright Data is asked to read."""
    parts = [p for p in urllib.parse.urlparse(url if "://" in url else "https://" + url).path.split("/") if p]
    after = parts[parts.index("comments") + 2:] if "comments" in parts else []
    slug = after[0] if after and after[0] != "comment" and re.match(r"^\w+$", after[0]) else None
    return f"https://www.reddit.com/r/{community}/comments/{post_id}/" + (f"{slug}/" if slug else "")


def _title_from_link(url) -> str | None:
    """The title words a thread's link carries ("gentle_exfoliant_for" -> "gentle exfoliant for"), if it has them."""
    if not isinstance(url, str) or "/comments/" not in url:
        return None
    parts = [p for p in urllib.parse.urlparse(url).path.split("/") if p]
    after = parts[parts.index("comments") + 2:] if "comments" in parts else []
    if not after or after[0] == "comment" or not re.match(r"^\w+$", after[0]):
        return None
    return " ".join(after[0].replace("_", " ").split()) or None


def save_thread(thread: Thread, folder: Path) -> Path:
    """Writes the thread as <folder>/<id>.json, in the same shape as the gold set's and the library's thread files.
    Never overwrites a file already there."""
    path = Path(folder) / f"{thread.id}.json"
    if path.exists():
        raise FileExistsError(f"{path} already exists and was not overwritten")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(thread.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


# --- Command line ---

def main(argv: list[str], client: BrightDataClient | None = None) -> int:
    """`client` can be swapped for one with a fake service, which is how the tests run the command line.
    It prints counts only: never a comment's text or a writer's name (`discover` prints thread titles too)."""
    if argv and argv[0] == "discover":
        return _discover_command(argv[1:], client)
    if not argv or argv[0] not in ("fetch", "usage"):
        print(__doc__)
        return 2
    links, folder, words = [], DEFAULT_THREADS_DIR, list(argv[1:])
    while words:
        word = words.pop(0)
        if word == "--to" and words:
            folder = Path(words.pop(0))
        elif word.startswith("--to="):
            folder = Path(word.removeprefix("--to="))
        elif word.startswith("-") or argv[0] == "usage":
            print(__doc__)
            return 2
        else:
            links.append(word)
    if argv[0] == "fetch" and not links:
        print(__doc__)
        return 2

    client = client or BrightDataClient()
    status = 0
    into_library = Path(folder).resolve() == LIBRARY_THREADS_DIR.resolve()
    gold = unlabelled_gold_ids() if into_library else set()
    for link in links:
        try:
            post_id = parse_thread_url(link)[1]
            if post_id in gold:
                print(f"{link}: {post_id} is a gold-set thread Noemi hasn't labelled yet (data/gold/CANDIDATES.md); "
                      "never read into the library, no records spent")
                status = 1
                continue
            if (folder / f"{post_id}.json").exists():
                print(f"{link}: {post_id}.json is already in {folder}; skipped, no records spent")
                continue
            thread = client.get_thread(link)
            path = save_thread(thread, folder)
        except (ValueError, BrightDataError, FileExistsError) as e:
            print(f"{link}: {e}")
            status = 1
            if isinstance(e, BrightDataError) and e.account_problem:
                break  # every other thread would fail the same way
            continue
        notes = client.last_read
        print(f"Saved {path}: r/{thread.community}, {len(thread.comments)} comments ({notes.records} records used)")
        if thread.num_comments > len(thread.comments):
            print(
                f"  Reddit counts {thread.num_comments} comments; {len(thread.comments)} arrived (Bright Data leaves out "
                "replies to replies, and Reddit's count can include removed comments)"
            )
        if notes.left_out:
            print(f"  {notes.left_out} comments kept out: no id to link them by, or no readable date")
        if not notes.post_read:
            print(f"  Note: {notes.post_note}")
    print(
        f"Bright Data records used this month: {client.records_used_this_month()} of {BRIGHT_DATA_MONTHLY_RECORDS} "
        "(as logged by this tool; the Bright Data dashboard has the exact figure)"
    )
    return status


def _discover_command(words: list[str], client: BrightDataClient | None) -> int:
    """`discover [--posts N] <subreddit> "<words>" ...`: one job for all the searches, then one line per thread found."""
    words, posts_each = list(words), DISCOVER_POSTS_EACH
    rest = []
    while words:
        word = words.pop(0)
        if word == "--posts" and words:
            word = "--posts=" + words.pop(0)
        if word.startswith("--posts="):
            number = word.removeprefix("--posts=")
            if not number.isdigit() or int(number) < 1:
                print(__doc__)
                return 2
            posts_each = int(number)
        elif word.startswith("-"):
            print(__doc__)
            return 2
        else:
            rest.append(word)
    if not rest or len(rest) % 2:
        print(__doc__)
        return 2

    client = client or BrightDataClient()
    searches = list(zip(rest[::2], rest[1::2]))
    before = client.records_used_this_month()
    try:
        found = client.discover(searches, posts_each=posts_each)
    except (ValueError, BrightDataError) as e:
        print(e)
        return 1
    print(f"Found {len(found)} threads ({client.records_used_this_month() - before} records used):")
    for post in found:
        day = post.created_at.date().isoformat() if post.created_at else "date unknown"
        print(f"  {post.id}  r/{post.subreddit}  {post.num_comments} comments  {day}  {post.title}  {post.url}")
    print(
        f"Bright Data records used this month: {client.records_used_this_month()} of {BRIGHT_DATA_MONTHLY_RECORDS} "
        "(as logged by this tool; the Bright Data dashboard has the exact figure)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
