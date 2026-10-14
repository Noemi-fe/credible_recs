"""On-demand reading (Noemi's plan of 14 Oct 2026, part 3, after "I want recs regardless of the category"): a request
about a product the library hasn't read about yet is queued, the site says so honestly, and a Cloud Run job finds and
reads its threads, so the next ask gets an answer.

How it works, in four parts:

1. The site queues (SiteReader.after_answer). When module 1 understands a request but the library holds fewer than
   ON_DEMAND_MIN_THREADS extracted threads about its product, the site adds an entry to the queue, one small object in
   the private bucket CREDIBLE_RECS_ON_DEMAND_BUCKET (on_demand/queue.json), and starts the reading job at once (Cloud
   Run's jobs:run, with its service account's token). The answer says so in plain words ("We haven't read Reddit about
   teapots yet, so we've started: check back in about 20 minutes."), and isn't remembered: the next ask works it out
   again. An entry holds only what finding threads needs (Noemi's rule of 11 Oct 2026: no access logs of visitors): the
   product type module 1 understood, its category and subreddits, and at most ON_DEMAND_NEED_WORDS of the request's need
   words (engine.sources.need_words: its own words less the product's name, filler words and numbers); never the
   request as typed, never when it was asked (the job's own times say when it read), nothing about who asked. Requests
   with the same product and need words are one entry. The site and the job both write the queue, each only over the version it read (Bucket.put_if), so
   neither loses the other's change.
2. The job reads (run_job: `python -m engine.on_demand run`, the Cloud Run job credible-recs-reader). It holds the
   queue while it runs (a lease, so two runs never read the same request), and for each waiting request finds threads
   with Arctic Shift's free title search and reads them from its archive (engine.sources.ArchiveSource, the library's
   own archive reader, at its own polite pace: no Bright Data, no Parse), the library's mix of thread kinds, threads
   already saved left out. Gemini extracts each, one at a time, within its free allowance (engine/gemini_extract.py;
   at most ON_DEMAND_GEMINI_CALLS_A_DAY calls a day, and none more that day after its daily 429), and the extraction's
   own checks run: every quote word for word against its comment (engine.extract.check_extraction; a quote that fails
   is never used). Then, when engine.slim is there (the lean library, Noemi's "Keep only comments we use"), the thread
   keeps only the comments answers use, as long as it reads the same; without it, it is kept whole. Each thread and its
   extraction go into one bundle object (on_demand/threads.json), saved after every thread, so a run cut short loses
   nothing; the queue says a request is done only once its threads are in the bundle.
3. The site answers with them (SiteReader.load_threads): as it gets ready, and at the keep-warm ping (every 5 minutes
   while a request it knows of waits, at most hourly otherwise), it asks the bundle's version (one small read) and
   downloads it only when it changed, writing the new threads into its library folder next to the baked ones (a baked
   thread is never overwritten). Answers read them like any other, and every quote shown is checked live on Reddit. A
   thread taken from the bundle goes from the folder ARCHIVE_TEXT_KEPT_DAYS after the job read it from the archive,
   as archive text not read live does in the library, and the bundle lets go of it then too. The daily pre-check
   loads them too, and checks ahead the answers about every product read on demand (precheck_types).
4. A deploy bakes them in (pull, forget_baked: `python -m engine.library pull-bucket` and `forget-baked`, run by
   deploy/cloudrun/deploy.sh): before the image is built, the bundle's threads come into data/library on Noemi's
   computer (a thread already there stays as it is), and once the site is deployed the bundle lets go of every thread
   the image now holds.

Free tiers only (the sums are in deploy/cloudrun/DEPLOY.md): no scheduler of its own (the site starts the job, and the
keep-warm ping starts it again when a start failed), the job's runs at most ON_DEMAND_MONTH_SECONDS a month, Gemini's
free allowance only, two small objects in the bucket.

    python -m engine.on_demand run       the reading job (on Google Cloud: CREDIBLE_RECS_ON_DEMAND_BUCKET, GEM_API_KEY)
    python -m engine.on_demand status    the queue, in counts and product types (on Noemi's computer, through gcloud)
"""

import hashlib
import importlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import http.client
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path

from engine.config import (
    ARCHIVE_TEXT_KEPT_DAYS,
    GEMINI_RESET_HOUR_UTC,
    LIBRARY_MIX,
    LIBRARY_THREADS_PER_PRODUCT,
    ON_DEMAND_BUNDLE_MAX_THREADS,
    ON_DEMAND_EACH_MINUTES,
    ON_DEMAND_EXTRACT_TRIES,
    ON_DEMAND_FIRST_MINUTES,
    ON_DEMAND_GEMINI_CALLS_A_DAY,
    ON_DEMAND_LATE_MINUTES,
    ON_DEMAND_LEASE_MINUTES,
    ON_DEMAND_MAX_DONE,
    ON_DEMAND_MAX_TRIES,
    ON_DEMAND_MAX_WAITING,
    ON_DEMAND_MIN_THREADS,
    ON_DEMAND_MONTH_SECONDS,
    ON_DEMAND_NEED_WORDS,
    ON_DEMAND_NEW_READING_SECONDS,
    ON_DEMAND_QUEUE_FRESH_SECONDS,
    ON_DEMAND_READ_AGAIN_DAYS,
    ON_DEMAND_RETRY_DAYS,
    ON_DEMAND_RETRY_MINUTES,
    ON_DEMAND_START_EVERY_SECONDS,
    ON_DEMAND_START_SECONDS,
)
from engine.live_check import BUCKET_TIMEOUT, BUNDLE_RELOAD_SECONDS, Bucket, _http_request
from engine.query import ParsedQuery
from engine.sources import need_words

BUCKET_VAR = "CREDIBLE_RECS_ON_DEMAND_BUCKET"  # the private bucket of the queue and the bundle
JOB_VAR = "CREDIBLE_RECS_ON_DEMAND_JOB"  # projects/<project>/locations/<region>/jobs/<job>: the site starts it
DEFAULT_BUCKET = "credible-picks-on-demand"  # its name in Noemi's project (deploy/cloudrun/deploy.sh)
PREFIX = "on_demand/"  # the bucket's objects are under this prefix
QUEUE_NAME = "queue.json"
THREADS_NAME = "threads.json"
RUN_API = "https://run.googleapis.com/v2/"
_JOB_NAME = re.compile(r"projects/[a-z][a-z0-9-]{4,28}[a-z0-9]/locations/[a-z0-9-]+"
                       r"/jobs/[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?")
CHANGE_TRIES = 5  # a write over a version another writer moved on is redone from a fresh read this many times at most

# --- Wording visitors see (decided by Claude, 14 Oct 2026; PROPOSED, like the page's other new words) ---
# The answer says what is happening in the page's own style; {about} is the product type's plural ("teapots").
READING_NEW = "We haven't read Reddit about {about} yet, so we've started: check back {when}."
READING_MORE = ("We've read only a little on Reddit about {about} so far, so we've started reading more: check back "
                "{when}.")
WAITING_NEW = ("We haven't read Reddit about {about} yet. It's on our list, but our free reading allowance is used up "
               "for now: check back {when}.")
WAITING_MORE = ("We've read only a little on Reddit about {about} so far. Reading more is on our list, but our free "
                "reading allowance is used up for now: check back {when}.")
LATE = "We're reading Reddit about {about}, but it's taking longer than usual: please check back later."
IN_MINUTES = "in about {n} minutes"
IN_AN_HOUR = "in about an hour"
IN_HOURS = "in about {n} hours"
BACK_TODAY = "later today"
BACK_TOMORROW = "tomorrow"
BACK_ON = "on {date}"


def _now() -> datetime:
    return datetime.now(UTC)


def _time(text: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(text) if text else None
    except (TypeError, ValueError):
        return None


# --- The queue: one small object, written by the site and the job ---

def key_of(category: str, product_type: str, needs: list[str]) -> str:
    """One entry per product and need words, in any order: "kitchen/teapot/leaf+loose"."""
    return f"{category}/{product_type}/{'+'.join(sorted(needs))}"


@dataclass
class Entry:
    """One request the library can't answer yet, as the queue keeps it: what finding its threads needs, and how its
    reading went. Never the request as typed, never when it was asked (see the module's docstring)."""

    key: str
    category: str
    product_type: str
    subreddits: list[str]
    needs: list[str] = field(default_factory=list)  # at most ON_DEMAND_NEED_WORDS of its need words
    ingredient_led: bool = False  # an ingredient-led request ("salicylic acid product"): module 2 reads it so
    had: int = 0  # the extracted threads the library had about it when it was queued
    status: str = "waiting"  # "waiting", or "done" once its threads are read and extracted
    tries: int = 0  # readings that failed (Arctic Shift couldn't be reached), by the job
    tried_at: str | None = None  # when the job last tried and failed (UTC)
    read_at: str | None = None  # when the job read its threads from the archive (UTC): they wait for Gemini then
    done_at: str | None = None  # when it was done (UTC)
    read_again_after: str | None = None  # when it may be queued again, if its library is still thin then
    found: int = 0  # threads its reading added to the bundle
    note: str | None = None  # the job's last word on it, in a few words (counts only)

    @classmethod
    def waiting_for(cls, query: ParsedQuery, had: int) -> "Entry":
        """The entry for an understood request (module 1's ParsedQuery), whose library has `had` extracted threads."""
        needs = need_words(query)[:ON_DEMAND_NEED_WORDS]
        return cls(key=key_of(query.category, query.product_type, needs), category=query.category,
                   product_type=query.product_type, subreddits=list(query.subreddits), needs=needs,
                   ingredient_led=query.ingredient_led, had=had)

    def query(self) -> ParsedQuery:
        """The request as module 2 reads it, made again from the entry: its product type, category and subreddits, and
        its need words as its text (raises ValueError when they no longer fit module 1's decided values)."""
        return ParsedQuery(text=" ".join([self.product_type, *self.needs]), status="ok", category=self.category,
                           product_type=self.product_type, search_terms=[self.product_type],
                           subreddits=list(self.subreddits), ingredient_led=self.ingredient_led)

    def finish(self, now: datetime, found: int, failed: bool = False, note: str | None = None) -> None:
        """Done: read again after ON_DEMAND_READ_AGAIN_DAYS if its library is still thin then, or after
        ON_DEMAND_RETRY_DAYS when its reading failed."""
        wait = timedelta(days=ON_DEMAND_RETRY_DAYS if failed else ON_DEMAND_READ_AGAIN_DAYS)
        self.status, self.done_at, self.found = "done", now.isoformat(), found
        self.read_again_after, self.note = (now + wait).isoformat(), note

    def due_again(self, now: datetime) -> bool:
        """Whether a done entry may be queued again (its library still thin)."""
        after = _time(self.read_again_after)
        return self.status == "done" and (after is None or now >= after)

    def wait_again(self, had: int) -> None:
        """Queued again, from the start."""
        self.status, self.had, self.tries, self.tried_at, self.read_at, self.note = "waiting", had, 0, None, None, None

    def tried_lately(self, now: datetime) -> bool:
        """Whether its last failed try was under ON_DEMAND_RETRY_MINUTES ago: the next run tries others first."""
        tried = _time(self.tried_at)
        return tried is not None and now - tried < timedelta(minutes=ON_DEMAND_RETRY_MINUTES)

    def as_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> "Entry":
        known = {f.name for f in fields(cls)}
        return cls(**{name: value for name, value in data.items() if name in known})


entry_for = Entry.waiting_for


@dataclass
class Queue:
    """The queue object: its entries in the order they were queued, and the job's state."""

    entries: list[Entry] = field(default_factory=list)
    lease_until: str | None = None  # a run holds the queue until then (UTC)
    resting_until: str | None = None  # no reading until then: Gemini's daily allowance, or the month's time, used up
    resting_why: str | None = None  # "gemini", "month" or "full" (the bundle waits for a deploy)
    # {"month": "2026-10", "seconds": the job's runs this month, "day": Gemini's day, "gemini_calls": its calls that
    # day}
    usage: dict = field(default_factory=dict)
    last_run: dict | None = None  # the last run's report, in counts

    def find(self, key: str) -> Entry | None:
        return next((entry for entry in self.entries if entry.key == key), None)

    def waiting(self) -> list[Entry]:
        return [entry for entry in self.entries if entry.status == "waiting"]

    def add(self, entry: Entry) -> Entry:
        """Queues `entry`, or queues again a done entry of the same request (to the end of the line); the queue's
        entry. One already waiting stays as it is."""
        found = self.find(entry.key)
        if found is None:
            self.entries.append(entry)
            done = [e for e in self.entries if e.status == "done"]
            for old in sorted(done, key=lambda e: e.done_at or "")[:max(0, len(done) - ON_DEMAND_MAX_DONE)]:
                self.entries.remove(old)
            return entry
        if found.status == "done":
            found.wait_again(entry.had)
            self.entries.remove(found)
            self.entries.append(found)
        return found

    def leased(self, now: datetime) -> bool:
        until = _time(self.lease_until)
        return until is not None and now < until

    def take_lease(self, now: datetime, minutes: int = ON_DEMAND_LEASE_MINUTES) -> bool:
        """Holds the queue for one run, unless another run holds it; whether it was taken."""
        if self.leased(now):
            return False
        self.lease_until = (now + timedelta(minutes=minutes)).isoformat()
        return True

    def release_lease(self) -> None:
        self.lease_until = None

    def resting(self, now: datetime) -> bool:
        until = _time(self.resting_until)
        return until is not None and now < until

    def rest(self, until: datetime, why: str) -> None:
        self.resting_until, self.resting_why = until.isoformat(), why

    def usage_now(self, now: datetime) -> dict:
        """This month's and Gemini's day's usage (a new month or day starts from nothing)."""
        month, day = now.strftime("%Y-%m"), gemini_day(now).isoformat()
        if self.usage.get("month") != month:
            self.usage.update(month=month, seconds=0.0)
        if self.usage.get("day") != day:
            self.usage.update(day=day, gemini_calls=0)
        return self.usage

    def as_json(self) -> dict:
        return {"version": 1, "entries": [entry.as_json() for entry in self.entries], "lease_until": self.lease_until,
                "resting_until": self.resting_until, "resting_why": self.resting_why, "usage": self.usage,
                "last_run": self.last_run}

    @classmethod
    def from_json(cls, data: dict) -> "Queue":
        return cls(entries=[Entry.from_json(e) for e in data.get("entries") or [] if isinstance(e, dict)],
                   lease_until=data.get("lease_until"), resting_until=data.get("resting_until"),
                   resting_why=data.get("resting_why"), usage=dict(data.get("usage") or {}),
                   last_run=data.get("last_run"))


def gemini_day(now: datetime):
    """Gemini's day (its free allowance resets at midnight Pacific time; GEMINI_RESET_HOUR_UTC is never before it)."""
    return (now - timedelta(hours=GEMINI_RESET_HOUR_UTC)).date()


def next_gemini_reset(now: datetime) -> datetime:
    """When Gemini's free allowance is surely back: the next GEMINI_RESET_HOUR_UTC o'clock UTC."""
    reset = now.replace(hour=GEMINI_RESET_HOUR_UTC, minute=0, second=0, microsecond=0)
    return reset if reset > now else reset + timedelta(days=1)


def next_month(now: datetime) -> datetime:
    first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return (first + timedelta(days=32)).replace(day=1)


# --- The bundle: the threads read on demand, with their extractions ---

@dataclass
class Item:
    """One thread read on demand, as the bundle holds it: its file's text as the library saves it (slimmed or whole),
    and its extraction file's text, None while it waits for Gemini."""

    thread: str
    extraction: str | None
    entry: str  # the key of the request it was read for
    product_type: str
    added_at: str  # when it was read from the archive (UTC)
    tries: int = 0  # extractions that failed (not for the daily limit)
    slimmed: bool = False

    def as_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict) -> "Item":
        known = {f.name for f in fields(cls)}
        return cls(**{name: value for name, value in data.items() if name in known})


@dataclass
class Bundle:
    threads: dict[str, Item] = field(default_factory=dict)  # thread id -> its item

    def extracted(self, product_type: str | None = None) -> list[str]:
        return [tid for tid, item in self.threads.items() if item.extraction is not None
                and (product_type is None or item.product_type == product_type)]

    def as_json(self) -> dict:
        return {"version": 1, "threads": {tid: item.as_json() for tid, item in self.threads.items()}}

    @classmethod
    def from_json(cls, data: dict) -> "Bundle":
        return cls(threads={str(tid): Item.from_json(item) for tid, item in (data.get("threads") or {}).items()
                            if isinstance(item, dict)})


class _Stored:
    """One JSON object in the bucket, read with its version and written only over that version."""

    name = ""
    shape = None  # the class: Queue or Bundle

    def __init__(self, bucket: Bucket):
        self.bucket = bucket

    def read(self):
        """(the object, its generation: None when there is none yet, and it reads as empty), or None when the bucket
        can't be read just now."""
        reached, generation = self.bucket.lookup(self.name)
        if not reached:
            return None
        if generation is None:
            return self.shape(), None
        data = self.bucket.get(self.name, generation)
        if data is None:
            return None  # can't be read just now, or written again meanwhile: tried again later
        try:
            return self.shape.from_json(json.loads(data)), generation
        except (ValueError, TypeError, AttributeError) as error:
            print(f"The bucket's {self.name} couldn't be read ({type(error).__name__}): it is started again empty.",
                  file=sys.stderr, flush=True)
            return self.shape(), generation

    def change(self, edit: Callable):
        """Reads the object, lets `edit` change it, and writes it over the version read; when another writer saved it
        first, again from a fresh read (CHANGE_TRIES times at most). `edit` returning False leaves it unwritten. The
        object as written (or as read, when left unwritten); None when the bucket couldn't be reached."""
        for _ in range(CHANGE_TRIES):
            found = self.read()
            if found is None:
                return None
            thing, generation = found
            if edit(thing) is False:
                return thing
            saved = self.bucket.put_if(self.name, json.dumps(thing.as_json(), ensure_ascii=False).encode("utf-8"),
                                       generation)
            if saved is None:
                return None
            if saved != Bucket.CHANGED:
                return thing
        return None


class QueueStore(_Stored):
    name, shape = QUEUE_NAME, Queue


class BundleStore(_Stored):
    name, shape = THREADS_NAME, Bundle


# --- Starting the job (the site, and the keep-warm ping) ---

class JobStarter:
    """Starts the reading job through Cloud Run's Admin API (jobs:run), with the service account's token (the bucket's:
    the site and the job run as the same account, which may start it). A start that fails is said once in the server's
    window; the keep-warm ping tries again."""

    def __init__(self, job_name: str, bucket: Bucket, request=_http_request):
        if not _JOB_NAME.fullmatch(job_name or ""):
            raise ValueError(f"{JOB_VAR} must be projects/<project>/locations/<region>/jobs/<job>, not {job_name!r}")
        self.job_name, self.bucket, self._request = job_name, bucket, request
        self.started = 0
        self.problems = 0

    def start(self) -> bool:
        token = self.bucket.access_token()
        status = None
        if token is not None:
            try:
                status, _ = self._request("POST", f"{RUN_API}{self.job_name}:run",
                                          {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                                          b"{}", timeout=BUCKET_TIMEOUT)
            except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
                status = None
        if status == 200:
            self.started += 1
            return True
        self.problems += 1
        if self.problems == 1:
            print(f"The reading job couldn't be started ({'no answer' if status is None else f'HTTP {status}'}): the "
                  "keep-warm ping tries again.", file=sys.stderr, flush=True)
        return False


# --- The site's side ---

@dataclass(frozen=True)
class Outcome:
    """What on-demand reading adds to one answer."""

    state: dict | None = None  # the API's "on_demand" (engine/web.py), or None
    remember: bool = True  # whether the answer may be remembered (engine.web.ANSWER_KEEP_HOURS)
    again: bool = False  # new threads have just come in: work the answer out again


class SiteReader:
    """The site's side of on-demand reading (see the module's docstring): queues what the library can't answer yet,
    starts the job, and writes the threads it reads into the site's library folder. `clock` (seconds) and `now` can be
    swapped for fakes; `min_threads`, the thin library's bar."""

    def __init__(self, bucket: Bucket, library_dir: Path, job: JobStarter | None = None, clock=time.monotonic,
                 now=_now, min_threads: int = ON_DEMAND_MIN_THREADS):
        self.bucket = bucket
        self.store, self.bundles = QueueStore(bucket), BundleStore(bucket)
        self.library_dir = Path(library_dir)
        self.job, self._clock, self._now, self.min_threads = job, clock, now, min_threads
        self._queue: Queue | None = None  # the queue as last read or written here
        self._queue_at: float | None = None
        self._bundle_generation: str | None = None  # the bundle's version last written into the folder
        self._bundle_at: float | None = None
        self._written: dict[str, str] = {}  # thread id -> the fingerprint of the files written here from the bundle
        self._read_on: dict[str, datetime] = {}  # thread id -> when the job read it from the archive (the bundle's)
        self._first_seen: dict[str, float] = {}  # entry key -> when this server first saw it waiting (memory only)
        self._last_start: float | None = None
        self._lock = threading.RLock()

    # --- Answers ---

    def after_answer(self, result) -> Outcome:
        """What on-demand reading adds to an answer (engine.pipeline's PipelineResult). A request module 1 didn't
        understand, or whose library isn't thin, costs nothing: no call at all."""
        query = result.query
        if query.status != "ok" or not query.product_type or result.threads_available >= self.min_threads:
            return Outcome()
        entry = Entry.waiting_for(query, had=result.threads_available)
        now = self._now()
        with self._lock:
            queue = self._read_queue(ON_DEMAND_QUEUE_FRESH_SECONDS)
            if queue is None:
                return Outcome(remember=False)  # the bucket can't be read just now: asked again next time
            found = queue.find(entry.key)
            if found is not None and found.status == "done" and not found.due_again(now):
                if not found.found:
                    return Outcome()  # read already, and Reddit's archive had nothing new: what the library has
                written = self.load_threads()
                if written is None:
                    return Outcome(remember=False)
                return Outcome(remember=False, again=True) if written else Outcome()
            if found is None or found.status == "done":
                if len(queue.waiting()) >= ON_DEMAND_MAX_WAITING:
                    return Outcome(remember=False)  # a full queue: what the library has, asked about again later
                queue = self.store.change(lambda q: q.add(entry) and None)
                if queue is None:
                    return Outcome(remember=False)
                self._queue, self._queue_at = queue, self._clock()
                self._first_seen[entry.key] = self._clock()  # queued (again) now: its wait starts now
            self._first_seen.setdefault(entry.key, self._clock())
            self._start_if_due(queue, now)
            return Outcome(self._state(queue, entry.key, now), remember=False)

    def _state(self, queue: Queue, key: str, now: datetime) -> dict:
        """The API's "on_demand" for a waiting entry: where it stands, and the sentence the page shows."""
        entry = queue.find(key)
        from engine.group_products import plural  # here: grouping is a module answers load anyway

        about = plural(entry.product_type)
        more = entry.had > 0
        state = {"state": "reading", "product_type": entry.product_type, "about": about, "read_before": more,
                 "check_back_minutes": None}
        if queue.resting(now):
            when = back_when(_time(queue.resting_until), now)
            return state | {"state": "waiting", "message": (WAITING_MORE if more else WAITING_NEW).format(
                about=about, when=when)}
        if self._clock() - self._first_seen.get(key, self._clock()) > ON_DEMAND_LATE_MINUTES * 60:
            return state | {"state": "late", "message": LATE.format(about=about)}
        ahead = [e.key for e in queue.waiting()].index(key) if key in [e.key for e in queue.waiting()] else 0
        minutes = ON_DEMAND_FIRST_MINUTES + ON_DEMAND_EACH_MINUTES * ahead
        return state | {"check_back_minutes": minutes, "message": (READING_MORE if more else READING_NEW).format(
            about=about, when=check_back_in(minutes))}

    # --- Getting ready and the keep-warm ping ---

    def warm_up(self) -> int | None:
        """As the server gets ready: what waits (the queue), and the threads read on demand into the folder."""
        with self._lock:
            self._read_queue(0)
        return self.load_threads()

    def on_ping(self) -> int:
        """At the keep-warm ping: while a request this server knows of waits, the queue read again, the job started
        when it should be running and isn't, and the bundle's version asked; otherwise the bundle's version at most
        hourly (BUNDLE_RELOAD_SECONDS). How many threads were written into the folder or taken out of it (the caller
        forgets its remembered answers when there were any)."""
        with self._lock:
            waiting = self._queue is not None and bool(self._queue.waiting())
            due = self._bundle_at is None or self._clock() - self._bundle_at >= BUNDLE_RELOAD_SECONDS
            if not (waiting or due):
                return 0
            if waiting:
                queue = self._read_queue(0)
                if queue is not None:
                    self._start_if_due(queue, self._now())
            return self.load_threads() or 0

    def _read_queue(self, fresh_within: float) -> Queue | None:
        if self._queue is not None and self._queue_at is not None and self._clock() - self._queue_at < fresh_within:
            return self._queue
        found = self.store.read()
        if found is None:
            return None
        self._queue, self._queue_at = found[0], self._clock()
        waiting = {e.key for e in self._queue.waiting()}
        self._first_seen = {key: at for key, at in self._first_seen.items() if key in waiting}
        for key in waiting:
            self._first_seen.setdefault(key, self._clock())
        return self._queue

    def _start_if_due(self, queue: Queue, now: datetime) -> None:
        if self.job is None or not queue.waiting() or queue.leased(now) or queue.resting(now):
            return
        if self._last_start is not None and self._clock() - self._last_start < ON_DEMAND_START_EVERY_SECONDS:
            return
        self._last_start = self._clock()
        self.job.start()

    # --- The threads read on demand, into the library folder ---

    def load_threads(self) -> int | None:
        """The bundle's threads, into the library folder: only when the bundle changed since it was last written here
        (one small question about its version first), only threads with their extraction, never over a baked thread,
        and only those whose files changed. Then the folder's threads taken from the bundle are let go
        ARCHIVE_TEXT_KEPT_DAYS after the job read them. How many threads were written or let go; None when the bucket
        can't be read just now."""
        with self._lock:
            self._bundle_at = self._clock()
            reached, generation = self.bucket.lookup(THREADS_NAME)
            if not reached:
                return None
            changed = 0
            if generation is not None and generation != self._bundle_generation:
                data = self.bucket.get(THREADS_NAME, generation)
                if data is None:
                    return None
                try:
                    bundle = Bundle.from_json(json.loads(data))
                except (ValueError, TypeError, AttributeError):
                    return None
                changed += write_threads(bundle, self.library_dir, self._written)
                for tid in self._written:
                    if tid in bundle.threads and _time(bundle.threads[tid].added_at) is not None:
                        self._read_on[tid] = _time(bundle.threads[tid].added_at)
                self._bundle_generation = generation
            return changed + self._let_go_of_old()

    def _let_go_of_old(self) -> int:
        """Lets go of the threads taken from the bundle that the job read from the archive more than
        ARCHIVE_TEXT_KEPT_DAYS ago (none of them is ever read live as a whole thread: their quotes are checked one by
        one before they are shown); how many."""
        gone = 0
        for tid in list(self._written):
            read_on = self._read_on.get(tid)
            if read_on is not None and (self._now() - read_on).days > ARCHIVE_TEXT_KEPT_DAYS:
                for folder in ("extracted", "threads"):
                    (self.library_dir / folder / f"{tid}.json").unlink(missing_ok=True)
                del self._written[tid], self._read_on[tid]
                gone += 1
        return gone

    def product_types(self) -> list[str]:
        """Every product type in the queue, waiting or read (the daily pre-check checks their answers ahead)."""
        with self._lock:
            queue = self._read_queue(0)
        return list(dict.fromkeys(e.product_type for e in queue.entries)) if queue is not None else []


def check_back_in(minutes: int) -> str:
    """"in about 20 minutes", "in about an hour", "in about 2 hours"."""
    if minutes < 55:
        return IN_MINUTES.format(n=max(5, 5 * round(minutes / 5)))
    hours = round(minutes / 60)
    return IN_AN_HOUR if hours <= 1 else IN_HOURS.format(n=hours)


def back_when(until: datetime | None, now: datetime) -> str:
    """When reading starts again, in words: "later today", "tomorrow", "on 1 November"."""
    if until is None or until.date() <= now.date():
        return BACK_TODAY
    if until.date() == now.date() + timedelta(days=1):
        return BACK_TOMORROW
    return BACK_ON.format(date=f"{until.day} {until.strftime('%B')}")


def write_threads(bundle: Bundle, library_dir: Path, written: dict[str, str]) -> int:
    """Writes the bundle's extracted threads into a library folder: threads/<id>.json first, then extracted/<id>.json,
    each whole under another name and then swapped in. A thread the folder already holds that wasn't written from the
    bundle (`written`: id -> fingerprint, kept by the caller) is a baked thread: never overwritten. How many were
    written."""
    count = 0
    for tid, item in sorted(bundle.threads.items()):
        if item.extraction is None or not re.fullmatch(r"[A-Za-z0-9]+", tid):
            continue
        thread_path = Path(library_dir) / "threads" / f"{tid}.json"
        if thread_path.exists() and tid not in written:
            continue  # baked into the image (or saved on Noemi's computer): that copy stays
        print_ = _fingerprint(item)
        if written.get(tid) == print_:
            continue
        _write_file(thread_path, item.thread)
        _write_file(Path(library_dir) / "extracted" / f"{tid}.json", item.extraction)
        written[tid] = print_
        count += 1
    return count


def _fingerprint(item: Item) -> str:
    return hashlib.sha256((item.thread + "\0" + (item.extraction or "")).encode("utf-8")).hexdigest()


def _write_file(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    partial.write_text(text, encoding="utf-8")
    partial.replace(path)


def _past_keeping(item: Item, now: datetime) -> bool:
    """Whether a thread the job read from the archive was read more than ARCHIVE_TEXT_KEPT_DAYS ago (the library's
    keeping time for archive text not read live: engine.library). A thread whose date can't be read counts as past."""
    read_on = _time(item.added_at)
    return read_on is None or (now - read_on).days > ARCHIVE_TEXT_KEPT_DAYS


def site_reader_from_env(environ, library_dir: Path) -> SiteReader | None:
    """The site's on-demand reading, when both its bucket (CREDIBLE_RECS_ON_DEMAND_BUCKET) and its job
    (CREDIBLE_RECS_ON_DEMAND_JOB) are set: without the job nothing would read what is queued, so nothing is queued."""
    name, job = (environ.get(BUCKET_VAR) or "").strip(), (environ.get(JOB_VAR) or "").strip()
    if not name:
        return None
    if not job:
        print(f"On-demand reading is off: {BUCKET_VAR} is set but {JOB_VAR} isn't, and nothing would read what is "
              "queued.", file=sys.stderr, flush=True)
        return None
    bucket = Bucket(name, prefix=PREFIX)
    return SiteReader(bucket, library_dir, job=JobStarter(job, bucket))


def precheck_types(environ, library_dir: Path, bucket: Bucket | None = None) -> list[str]:
    """For the daily pre-check, with CREDIBLE_RECS_ON_DEMAND_BUCKET set: the threads read on demand written into its
    library folder, and the product types of the queue (its answers about them are checked ahead). [] without it.
    `bucket` can be a fake (the tests)."""
    name = (environ.get(BUCKET_VAR) or "").strip()
    if not name:
        return []
    reader = SiteReader(bucket or Bucket(name, prefix=PREFIX), library_dir)
    if reader.load_threads() is None:
        print(f"The threads read on demand couldn't be read from {name}: checked ahead without them.",
              file=sys.stderr, flush=True)
    return reader.product_types()


# --- The job ---

@dataclass
class RunReport:
    """One run of the reading job, in counts and product types (never a comment's words)."""

    ran: bool = False  # False: another run held the queue, the queue rests, or the bucket couldn't be reached
    why_not: str | None = None
    requests_read: list[str] = field(default_factory=list)  # product types whose threads were read now
    requests_done: list[str] = field(default_factory=list)  # product types done now
    threads_read: int = 0
    extracted: int = 0
    quotes_kept: int = 0  # mentions whose quote passed the word-for-word check
    quotes_dropped: int = 0  # and those that didn't (never used)
    slimmed: int = 0
    whole: int = 0
    failures: int = 0  # threads or searches that failed (the archive, or Gemini for a thread)
    gemini_calls: int = 0
    resting: str | None = None  # why the queue rests now, if it does
    notes: list[str] = field(default_factory=list)
    seconds: float = 0.0

    def summary(self) -> dict:
        return {"requests_read": len(self.requests_read), "requests_done": len(self.requests_done),
                "threads_read": self.threads_read, "extracted": self.extracted, "quotes_kept": self.quotes_kept,
                "quotes_dropped": self.quotes_dropped, "slimmed": self.slimmed, "whole": self.whole,
                "failures": self.failures, "gemini_calls": self.gemini_calls, "seconds": round(self.seconds),
                "resting": self.resting}

    def text(self) -> str:
        if not self.ran:
            return f"Nothing read: {self.why_not}."
        lines = [f"Requests read now: {len(self.requests_read)} ({', '.join(self.requests_read) or 'none'}); done: "
                 f"{len(self.requests_done)} ({', '.join(self.requests_done) or 'none'}).",
                 f"Threads read from the archive: {self.threads_read}; extracted by Gemini: {self.extracted} "
                 f"({self.gemini_calls} calls); quotes kept by the word-for-word check: {self.quotes_kept}, dropped: "
                 f"{self.quotes_dropped}.",
                 f"Kept only the comments answers use: {self.slimmed}; kept whole: {self.whole}.",
                 f"Failures: {self.failures}. Time: {self.seconds / 60:.1f} min."]
        if self.resting:
            lines.append(f"Resting: {self.resting}.")
        return "\n".join(lines + self.notes)


def run_job(bucket: Bucket, library_dir: Path, archive, gemini, now=_now, clock=time.monotonic,
            work_dir: Path | None = None, new_reading_seconds: float = ON_DEMAND_NEW_READING_SECONDS) -> RunReport:
    """One run of the reading job (see the module's docstring): holds the queue, extracts the threads waiting for
    Gemini, reads the next waiting request's threads from the archive, and so on, until nothing waits, the queue rests
    (Gemini's day, the month's time) or the run's time for new readings is up; then lets go of the queue and adds its
    time to the month's. `archive`: an engine.arctic_shift.ArcticShiftClient; `gemini`: an
    engine.gemini_extract.GeminiClient; `now` (datetimes) and `clock` (seconds) can be fakes."""
    report = RunReport()
    started = clock()
    queues, bundles = QueueStore(bucket), BundleStore(bucket)
    took: dict = {}

    def take(queue: Queue):
        if not queue.waiting():
            took["why"] = "nothing waits"
            return False
        if queue.resting(now()):
            took["why"] = f"the queue rests until {queue.resting_until} ({queue.resting_why})"
            return False
        if not queue.take_lease(now()):
            took["why"] = "another run holds the queue"
            return False
        took["ok"] = True

    if queues.change(take) is None:
        report.why_not = "the bucket couldn't be reached"
        return report
    if not took.get("ok"):
        report.why_not = took["why"]
        return report
    report.ran = True
    work = Path(work_dir) if work_dir is not None else Path(tempfile.mkdtemp(prefix="on-demand-"))
    try:
        _let_go_of_old_threads(bundles, now(), report)
        _read_until_done(queues, bundles, Path(library_dir), archive, gemini, now, clock, started, work, report,
                         new_reading_seconds)
    except Exception as error:  # reported, and the queue let go of all the same: the next run starts afresh
        report.failures += 1
        report.notes.append(f"The run stopped on an error ({type(error).__name__}).")
        print(f"The reading job stopped on an error ({type(error).__name__}: {error}).", file=sys.stderr, flush=True)
    finally:
        report.seconds = clock() - started

        def release(queue: Queue):
            queue.release_lease()
            usage = queue.usage_now(now())
            usage["seconds"] = round(float(usage.get("seconds", 0.0)) + report.seconds + ON_DEMAND_START_SECONDS, 1)
            queue.last_run = report.summary() | {"at": now().isoformat()}

        if queues.change(release) is None:
            report.notes.append("The queue couldn't be let go of: its lease runs out by itself.")
        if work_dir is None:
            shutil.rmtree(work, ignore_errors=True)
    return report


def _read_until_done(queues: QueueStore, bundles: BundleStore, library_dir: Path, archive, gemini, now, clock,
                     started: float, work: Path, report: RunReport, new_reading_seconds: float) -> None:
    while True:
        found_queue, found_bundle = queues.read(), bundles.read()
        if found_queue is None or found_bundle is None:
            report.notes.append("The bucket couldn't be read: the rest waits for the next run.")
            return
        queue, bundle = found_queue[0], found_bundle[0]
        moment = now()
        if queue.resting(moment):
            report.resting = f"until {queue.resting_until} ({queue.resting_why})"
            return
        usage = queue.usage_now(moment)
        if float(usage.get("seconds", 0.0)) + (clock() - started) + ON_DEMAND_START_SECONDS >= ON_DEMAND_MONTH_SECONDS:
            _rest(queues, next_month(moment), "month", report)
            return
        waiting_items = [tid for tid, item in bundle.threads.items() if item.extraction is None]
        if waiting_items:
            if not _extract_one(waiting_items[0], bundle, queues, bundles, library_dir, gemini, now, work, report):
                return
            _finish_complete(queues, now, report)  # a request whose threads are all in is done at once
            continue
        if _finish_complete(queues, now, report):
            continue
        if clock() - started >= new_reading_seconds:
            report.notes.append("This run's time for new readings is up: the rest waits for the next run.")
            return
        entry = next((e for e in queue.waiting() if e.read_at is None and not e.tried_lately(moment)), None)
        if entry is None:
            return
        if len(bundle.threads) >= ON_DEMAND_BUNDLE_MAX_THREADS:
            _rest(queues, moment + timedelta(days=1), "full", report)
            report.notes.append(f"The bundle holds {len(bundle.threads)} threads not baked in yet: a deploy takes them "
                                "in (python -m engine.library pull-bucket).")
            return
        _read_entry(entry, queue, bundle, queues, bundles, library_dir, archive, now, work, report)


def _let_go_of_old_threads(bundles: BundleStore, now: datetime, report: RunReport) -> None:
    """The bundle lets go of the threads read from the archive more than ARCHIVE_TEXT_KEPT_DAYS ago (a deploy has
    usually baked them in long before)."""
    gone: list[str] = []

    def drop(bundle: Bundle):
        gone[:] = [tid for tid, item in bundle.threads.items() if _past_keeping(item, now)]
        for tid in gone:
            del bundle.threads[tid]
        if not gone:
            return False

    bundles.change(drop)
    if gone:
        report.notes.append(f"Let go of {len(gone)} thread(s) read from the archive over {ARCHIVE_TEXT_KEPT_DAYS} days "
                            "ago.")


def _change_entry(queues: QueueStore, key: str, change: Callable[[Entry], object]) -> None:
    """Changes one entry of the queue, read afresh; nothing when it is gone."""
    def edit(queue: Queue):
        entry = queue.find(key)
        if entry is None:
            return False
        change(entry)

    queues.change(edit)


def _rest(queues: QueueStore, until: datetime, why: str, report: RunReport) -> None:
    queues.change(lambda queue: queue.rest(until, why))
    report.resting = f"until {until.isoformat()} ({why})"


def _finish_complete(queues: QueueStore, now, report: RunReport) -> bool:
    """Marks done every waiting request whose threads were read and are all in the bundle with their extraction (a
    thread let go after failing counts for nothing); whether any was."""
    bundle_found = BundleStore(queues.bucket).read()
    if bundle_found is None:
        return False
    bundle = bundle_found[0]
    done: list[str] = []

    def finish(queue: Queue):
        done.clear()
        for entry in queue.waiting():
            if entry.read_at is None:
                continue
            mine = [tid for tid, item in bundle.threads.items() if item.entry == entry.key]
            if all(bundle.threads[tid].extraction is not None for tid in mine):
                entry.finish(now(), found=len(mine), note=f"{len(mine)} threads read and extracted")
                done.append(entry.product_type)
        if not done:
            return False

    queues.change(finish)
    report.requests_done += done
    return bool(done)


def _read_entry(entry: Entry, queue: Queue, bundle: Bundle, queues: QueueStore, bundles: BundleStore,
                library_dir: Path, archive, now, work: Path, report: RunReport) -> None:
    """Finds and reads one waiting request's threads from the archive, into the bundle (waiting for Gemini), then
    marks it read in the queue (or done, when the library has enough threads about it already or none were found)."""
    from engine.arctic_shift import ArcticShiftError
    from engine.gold import GoldThreadError, unlabelled_gold_ids
    from engine.library import _save
    from engine.sources import ArchiveSource, choose_mix, for_request

    moment = now()
    key = entry.key
    try:
        query = entry.query()
    except ValueError:
        _change_entry(queues, key, lambda e: e.finish(moment, found=0, failed=True, note="no longer fits module 1"))
        return
    if entry.had + len(bundle.extracted(entry.product_type)) >= ON_DEMAND_MIN_THREADS:
        _change_entry(queues, key, lambda e: e.finish(moment, found=0, note="enough threads about it already"))
        report.requests_done.append(entry.product_type)
        return
    source = ArchiveSource(archive)
    try:
        ranked = source.rank_candidates(query)
    except ArcticShiftError:
        report.failures += 1

        def failed(mine: Entry):
            mine.tries, mine.tried_at = mine.tries + 1, moment.isoformat()
            if mine.tries >= ON_DEMAND_MAX_TRIES:
                mine.finish(moment, found=0, failed=True, note="the archive couldn't be searched")

        _change_entry(queues, key, failed)
        report.notes.append(f"Arctic Shift couldn't be searched for {entry.product_type}: tried again later.")
        return
    saved = {path.stem for path in (library_dir / "threads").glob("*.json")}
    skip = saved | set(bundle.threads) | unlabelled_gold_ids()
    fresh = [post for post in ranked if str(post["id"]).removeprefix("t3_") not in skip]
    chosen = choose_mix(query, fresh, total=LIBRARY_THREADS_PER_PRODUCT, mix=LIBRARY_MIX)
    read: dict[str, Item] = {}
    for post in chosen:
        post_id = str(post["id"]).removeprefix("t3_")
        try:
            thread = _save(for_request(archive.get_thread(post_id, post["subreddit"]), query), work)
        except (ArcticShiftError, ValueError, GoldThreadError):
            report.failures += 1
            continue
        text = (work / "threads" / f"{thread.id}.json").read_text(encoding="utf-8")
        read[thread.id] = Item(thread=text, extraction=None, entry=key, product_type=entry.product_type,
                               added_at=moment.isoformat())
    if read:
        if bundles.change(lambda b: b.threads.update(read)) is None:
            report.notes.append("The bundle couldn't be written: these threads are read again next time.")
            return
    report.threads_read += len(read)
    report.requests_read.append(entry.product_type)

    def mark(mine: Entry):
        mine.read_at = moment.isoformat()
        if not read:
            mine.finish(moment, found=0, note="no new threads in the archive")

    _change_entry(queues, key, mark)
    if not read:
        report.requests_done.append(entry.product_type)


def _extract_one(tid: str, bundle: Bundle, queues: QueueStore, bundles: BundleStore, library_dir: Path, gemini, now,
                 work: Path, report: RunReport) -> bool:
    """Extracts one thread waiting in the bundle, within Gemini's free allowance: checked word for word, slimmed when
    the lean library is here, and saved into the bundle. Whether the run goes on (False: Gemini rests for the day)."""
    from engine.extract import Extraction, check_extraction, shown_comment_ids
    from engine.gemini_extract import PART_COMMENTS, extract_threads
    from engine.models import Thread

    item = bundle.threads[tid]
    try:
        thread = Thread.model_validate_json(item.thread)
    except ValueError:  # a thread file that doesn't load can never be extracted: let go, and the run goes on
        bundles.change(lambda b: b.threads.pop(tid, None) and None)
        report.failures += 1
        report.notes.append("A thread waiting for Gemini couldn't be read: let go.")
        return True
    parts = max(1, math.ceil(len(shown_comment_ids(thread)) / PART_COMMENTS))
    queue_found = queues.read()
    if queue_found is None:
        return False
    usage = queue_found[0].usage_now(now())
    if int(usage.get("gemini_calls", 0)) + parts > ON_DEMAND_GEMINI_CALLS_A_DAY:
        _rest(queues, next_gemini_reset(now()), "gemini", report)
        report.notes.append(f"Today's {ON_DEMAND_GEMINI_CALLS_A_DAY} Gemini calls are used: the rest wait for "
                            "tomorrow.")
        return False
    for folder in ("threads", "extracted"):
        shutil.rmtree(work / folder, ignore_errors=True)
    _write_file(work / "threads" / f"{tid}.json", item.thread)
    before = gemini.calls
    result = extract_threads(work / "threads", work, gemini, ids=[tid])
    calls = gemini.calls - before
    report.gemini_calls += calls

    def count(queue: Queue):
        usage = queue.usage_now(now())
        usage["gemini_calls"] = int(usage.get("gemini_calls", 0)) + calls

    queues.change(count)
    if result.stopped:
        _rest(queues, next_gemini_reset(now()), "gemini", report)
        report.notes.append("Gemini's free allowance for the day is used up: the rest wait for tomorrow.")
        return False
    if tid in result.written:
        extraction_text = (work / "extracted" / f"{tid}.json").read_text(encoding="utf-8")
        extraction = Extraction.model_validate_json(extraction_text)
        checked = check_extraction(extraction, thread)
        report.quotes_kept += len(checked.kept)
        report.quotes_dropped += len(checked.rejected)
        report.extracted += 1
        needs = [word for word in item.entry.rsplit("/", 1)[-1].split("+") if word]  # its request's (key_of)
        slim_text, why = slimmed(thread, extraction, item.product_type, library_dir, now(), needs)
        if slim_text is None:
            report.whole += 1
            if why and why not in report.notes:
                report.notes.append(why)
        else:
            report.slimmed += 1

        def save(b: Bundle):
            mine = b.threads.get(tid)
            if mine is None:
                return False
            mine.extraction = extraction_text
            if slim_text is not None:
                mine.thread, mine.slimmed = slim_text, True

        bundles.change(save)
        return True
    report.failures += 1

    def failed(b: Bundle):
        mine = b.threads.get(tid)
        if mine is None:
            return False
        mine.tries += 1
        if mine.tries >= ON_DEMAND_EXTRACT_TRIES:
            del b.threads[tid]

    bundles.change(failed)
    return True


def slimmed(thread, extraction, product_type: str, library_dir: Path, now: datetime,
            needs: list[str] = ()) -> tuple[str | None, str | None]:
    """The thread file's text with only the comments answers use (Noemi, 13 Oct 2026: "Keep only comments we use"),
    through engine.slim (branch lean-library) when it is here and the slimmed copy reads the same as the whole one
    (its own guard, engine.slim.differences); else (None, why): the thread is kept whole. Its post is searched for the
    words the engine knows and the queued request's own (`needs`), as need-led reading will look for them."""
    try:
        slim = importlib.import_module("engine.slim")
    except ImportError:
        return None, "engine.slim isn't here yet (branch lean-library): threads are kept whole."
    try:
        types = tuple(dict.fromkeys((*slim.known_types(library_dir), product_type)))
        words = slim.known_words(library_dir) | slim.known_words_of(product_type, *needs)
        copy = slim.slim_thread(thread, extraction, types, now, words)
        if slim.differences(thread, copy, extraction, types, words):
            return None, "A thread would read differently slimmed: kept whole."
        return slim.thread_json(copy).decode("utf-8"), None
    except Exception as error:  # a thread the slimming refuses stays whole, as engine.slim leaves such threads
        return None, f"A thread couldn't be slimmed ({type(error).__name__}): kept whole."


# --- Baking them in: Noemi's computer, at each deploy ---

@dataclass
class PullReport:
    pulled: list[str] = field(default_factory=list)  # thread ids written into the library now
    kept_local: list[str] = field(default_factory=list)  # already in the library: that copy stays
    waiting: int = 0  # still waiting for Gemini: not pulled
    types: list[str] = field(default_factory=list)  # product types of the threads pulled


def pull(bucket: Bucket, library_dir: Path, now=_now) -> PullReport | None:
    """The bundle's extracted threads into a library folder (data/library on Noemi's computer), before a deploy builds
    the image: a thread the folder already holds stays as it is (a copy read live, or extracted by Claude, is the one
    to keep). Each product type pulled is added to the library's request log (requests.jsonl, without a request's words:
    the product type and the threads), so the daily pre-check and the slimming know it. None when the bucket can't be
    read."""
    found = BundleStore(bucket).read()
    if found is None:
        return None
    bundle = found[0]
    report = PullReport()
    by_type: dict[str, list[str]] = {}
    for tid, item in sorted(bundle.threads.items()):
        if item.extraction is None:
            report.waiting += 1
            continue
        if (Path(library_dir) / "threads" / f"{tid}.json").exists():
            report.kept_local.append(tid)
            continue
        write_threads(Bundle({tid: item}), library_dir, {})
        report.pulled.append(tid)
        by_type.setdefault(item.product_type, []).append(tid)
    report.types = list(by_type)
    if by_type:
        log = Path(library_dir) / "requests.jsonl"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as f:
            for product_type, ids in by_type.items():
                f.write(json.dumps({"at": now().isoformat(), "request": None, "via": "on-demand", "status": "ok",
                                    "product_type": product_type, "thread_ids": ids}, ensure_ascii=False) + "\n")
    return report


def forget_baked(bucket: Bucket, library_dir: Path) -> int | None:
    """Once a deploy has built the image from data/library: the bundle lets go of every thread the library holds with
    its extraction (the image has it now). Written only over the version read, so a thread the job adds meanwhile is
    never lost. How many it let go of; None when the bucket couldn't be reached."""
    gone: list[str] = []

    def drop(bundle: Bundle):
        gone.clear()
        for tid in list(bundle.threads):
            here = all((Path(library_dir) / folder / f"{tid}.json").exists() for folder in ("threads", "extracted"))
            if here and bundle.threads[tid].extraction is not None:
                del bundle.threads[tid]
                gone.append(tid)
        if not gone:
            return False

    return None if BundleStore(bucket).change(drop) is None else len(gone)


def gcloud_token() -> tuple[str, float]:
    """An access token from gcloud, as signed in on Noemi's computer (`gcloud auth login`), for an hour at most. Never
    printed. Raises OSError when gcloud can't give one."""
    try:
        done = subprocess.run([os.environ.get("GCLOUD") or "gcloud", "auth", "print-access-token"], capture_output=True,
                              text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as error:
        raise OSError(f"gcloud couldn't be run ({type(error).__name__})") from None
    token = done.stdout.strip()
    if done.returncode != 0 or not token:
        raise OSError("gcloud gave no access token: sign in with `gcloud auth login`")
    return token, 3000.0


def pull_command(command: str, argv: list[str], library_dir: Path, bucket: Bucket | None = None) -> int:
    """`python -m engine.library pull-bucket | forget-baked [--bucket NAME]` (deploy/cloudrun/deploy.sh runs both: the
    first before building the image, the second once the site is deployed)."""
    name = (os.environ.get(BUCKET_VAR) or "").strip() or DEFAULT_BUCKET
    if argv[:1] == ["--bucket"] and len(argv) == 2:
        name = argv[1]
    elif argv:
        print(f"python -m engine.library {command} [--bucket NAME]   (the bucket: {DEFAULT_BUCKET} by default)")
        return 2
    bucket = bucket or Bucket(name, prefix=PREFIX, token=gcloud_token)
    if command == "pull-bucket":
        report = pull(bucket, library_dir)
        if report is None:
            print(f"The bucket {name} couldn't be read: nothing pulled (the site still loads its threads from it).")
            return 1
        print(f"Pulled {len(report.pulled)} thread(s) read on demand into {library_dir}"
              f"{' (' + ', '.join(report.types) + ')' if report.types else ''}; already here, kept as they are: "
              f"{len(report.kept_local)}; still waiting for Gemini: {report.waiting}.")
        return 0
    gone = forget_baked(bucket, library_dir)
    if gone is None:
        print(f"The bucket {name} couldn't be written: its threads stay there until the next deploy.")
        return 1
    print(f"The bucket {name} let go of {gone} thread(s) the image now holds.")
    return 0


# --- Command line ---

def status_text(queue: Queue, now: datetime) -> str:
    """The queue in a few lines: counts and product types, never a request's words beyond its need words."""
    waiting = queue.waiting()
    done = [e for e in queue.entries if e.status == "done"]
    lines = [f"Waiting: {len(waiting)} ({', '.join(e.product_type for e in waiting) or 'none'}).",
             f"Read: {len(done)} ({', '.join(f'{e.product_type} ({e.found})' for e in done[-10:]) or 'none'}"
             f"{', ...' if len(done) > 10 else ''})."]
    if queue.resting(now):
        lines.append(f"Resting until {queue.resting_until} ({queue.resting_why}).")
    if queue.leased(now):
        lines.append(f"A run holds the queue until {queue.lease_until}.")
    usage = queue.usage_now(now)
    hours = float(usage.get("seconds", 0)) / 3600
    lines.append(f"This month: {hours:.1f} h of {ON_DEMAND_MONTH_SECONDS / 3600:.1f} h; Gemini today: "
                 f"{usage.get('gemini_calls', 0)} of {ON_DEMAND_GEMINI_CALLS_A_DAY} calls.")
    if queue.last_run:
        lines.append(f"Last run: {queue.last_run}.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    if argv == ["run"]:
        name = (os.environ.get(BUCKET_VAR) or "").strip()
        if not name:
            print(f"Set {BUCKET_VAR} to the bucket of the queue and the bundle.")
            return 2
        from engine.arctic_shift import ArcticShiftClient
        from engine.gemini_extract import GeminiClient
        from engine.library import DEFAULT_LIBRARY_DIR

        report = run_job(Bucket(name, prefix=PREFIX), DEFAULT_LIBRARY_DIR, ArcticShiftClient(), GeminiClient())
        print(report.text())
        return 0
    if argv[:1] == ["status"] and len(argv) in (1, 3):
        name = argv[2] if len(argv) == 3 and argv[1] == "--bucket" else (os.environ.get(BUCKET_VAR) or DEFAULT_BUCKET)
        found = QueueStore(Bucket(name, prefix=PREFIX, token=gcloud_token)).read()
        if found is None:
            print(f"The bucket {name} couldn't be read.")
            return 1
        print(status_text(found[0], _now()))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
