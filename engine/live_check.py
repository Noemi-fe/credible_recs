"""The last check before a quote is shown: is the comment still on Reddit, saying what the quote says?

Saved threads can be days or weeks old, and Arctic Shift's archive keeps comments people later deleted. So before
an answer shows a quote, its comment must have been read live through Reddit's embed page (embed.reddit.com, what
Reddit's official oEmbed widget loads to show a comment on another site; approved by Noemi on 9 Oct 2026) in the last
48 hours, one comment at a time, and only for quotes answers show or would show: read as the answer is written, or
since 13 Oct 2026 the day before, by the daily pre-check (below). The result:

    ok        the comment is there and the quote is found in it word for word (engine.verify_quotes.find_quote)
    gone      the comment was deleted or removed: its text reads "[deleted]" or "[removed]"
    changed   the comment is there but no longer says this: it was edited
    unknown   the page couldn't be read (an error, a timeout, or a page whose layout has changed)
    later     not read: reading it now would have meant waiting for Reddit's allowance, and the check was asked not
              to wait (13 Oct 2026: what "Also worth a look" and summaries ask, so they never hold up an answer)

Only "ok" is shown. Anything else drops the quote: strict by default, so a page Reddit redesigns makes quotes
disappear rather than show unchecked.

Being considerate, as with the other sources: calls are spaced out (each starts LIVE_CHECK_MIN_INTERVAL seconds after
the one before, even when the pipeline asks about several comments at once: latency, 12 Oct 2026), and never more than
Reddit allows: its embed pages answer about 200 reads in 10 minutes from one address (its rate-limit headers said so on
12 Oct 2026, after a test run read faster and got "429 Too Many Requests"). Since 13 Oct 2026 the pace follows what
Reddit says is left: each page it sends says how many reads the address has left in the current 10 minutes and when
they come back (x-ratelimit-remaining, x-ratelimit-reset), so reads go at once while LIVE_CHECK_SPREAD_BELOW or more
are left, spread out evenly over the rest of the 10 minutes when fewer are, and wait for the next 10 minutes when none
are, always keeping LIVE_CHECK_RESERVE for other reads from the same address. Until Reddit has said (a server's first
read, or 10 minutes that have ended), up to LIVE_CHECK_BURST reads go at once and then one every
LIVE_CHECK_REFILL_SECONDS, which can't reach the limit. What a comment page said is kept for 48 hours (the
deletion rule), so asking again about the same comment costs nothing. Only the
comment's own text is kept, never the page around it, and each is saved whole under its own name, so a check made at
the same time never reads half of one.

Checked ahead (Noemi's decision of 13 Oct 2026). A fresh answer needs 20 to 40 checks, and once Reddit's allowance is
used each one waits its turn, so a fresh answer could take a minute or two. So the quotes answers would show are also
read in advance, every day, within the same limits (engine/precheck.py, `python -m engine.precheck`): the comments of
every answer the library gives, the ones next in line for each place in them, and the products ranked just behind the
picks. The rule doesn't change: a quote is shown only when its comment passed a check made in the last 48 hours, by the
pre-check or at answer time; a failed check drops it, and an older one is read again before it is shown. The pre-check
reads again any comment last read over PRECHECK_FRESH_HOURS ago (check's `max_age`), so a check never runs out during
the next day's answers.

Where checks are kept. In this machine's folder (.cache/live_check) and, when CREDIBLE_RECS_LIVE_CACHE_BUCKET names one,
in a private Google Cloud Storage bucket (Bucket): on Google Cloud Run the server's disk is wiped whenever it sleeps,
and the daily pre-check runs on a machine of its own, so the server and the pre-check share the bucket. A check is
looked for here first, then in the bucket (and kept here when found there), and only then read on Reddit; a new one is
written to both. The 48-hour rule is the same for the bucket: an entry older than that is never used, whatever is asked,
and the bucket deletes objects 2 days old (deploy/cloudrun/DEPLOY.md). The bucket is reached with plain HTTPS calls to
Cloud Storage's JSON API, with the token Cloud Run's metadata server gives the service account; when it can't be
reached, checks go on with this folder and Reddit, and the bucket is left alone for BUCKET_REST_SECONDS.
"""

import hashlib
import html
import http.client
import json
import os
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import quote as url_quote
from urllib.parse import urlparse

import certifi

from engine.config import (CACHE_MAX_AGE_HOURS, LIVE_CHECK_BURST, LIVE_CHECK_MIN_INTERVAL, LIVE_CHECK_REFILL_SECONDS,
                           LIVE_CHECK_MAX_WAIT_SECONDS, LIVE_CHECK_RESERVE, LIVE_CHECK_SPREAD_BELOW)
from engine.verify_quotes import find_quote

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = REPO_ROOT / ".cache" / "live_check"
USER_AGENT = "credible-recs research prototype (github.com/Noemi-fe/credible_recs)"
MAX_AGE = timedelta(hours=CACHE_MAX_AGE_HOURS)

# The bucket (check ahead, 13 Oct 2026): its name, from the environment; unset, checks are kept on this machine only.
BUCKET_VAR = "CREDIBLE_RECS_LIVE_CACHE_BUCKET"
BUCKET_PREFIX = "live_check/"  # objects are named like the folder's files, under this prefix
BUCKET_TIMEOUT = 5  # seconds a call to the bucket may take: never long enough to hold up an answer for long
BUCKET_REST_SECONDS = 60  # after a failed call the bucket is left alone this long, so answers don't keep waiting on it
STORAGE_API = "https://storage.googleapis.com/storage/v1"
UPLOAD_API = "https://storage.googleapis.com/upload/storage/v1"
# Where a program on Google Cloud gets an access token for its service account (plain http: the metadata server is
# inside Google's machine, never on the internet).
METADATA_TOKEN_URL = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
TOKEN_MARGIN_SECONDS = 60  # a token is asked for again this long before it runs out

Status = Literal["ok", "gone", "changed", "unknown", "later"]
# Seconds past the end of Reddit's 10 minutes before the first read of the next (clocks differ a little), and how far
# apart two answers' ends may be and still be the same 10 minutes.
WINDOW_MARGIN_SECONDS = 1.0

# The comment's text on the embed page: <div class="text-14"><div ... class="inline-block ..."> text </div></div>.
_BODY = re.compile(r'<div class="text-14">\s*<div[^>]*class="inline-block[^"]*"[^>]*>(.*?)</div>\s*</div>', re.S)
_TAG = re.compile(r"<[^>]+>")
_GONE = ("[deleted]", "[removed]")
_PUT_OFF = object()  # _comment_text: not read, since reading it would have waited (check's wait=False)


@dataclass(frozen=True)
class LiveResult:
    status: Status
    reason: str  # in words, for the logs

    @property
    def show(self) -> bool:
        return self.status == "ok"


def embed_url(comment_url: str) -> str:
    """The embed page of a comment, from its link: .../r/<sub>/comments/<post>/<slug>/<comment>/ or .../comment/<id>/."""
    parts = [p for p in urlparse(comment_url).path.split("/") if p]
    subreddit, post, comment = parts[1], parts[3], parts[-1]
    return f"https://embed.reddit.com/r/{subreddit}/comments/{post}/comment/{comment}/?embed=true&showmedia=false"


def _http_get(url: str, headers: dict) -> tuple[int, bytes, dict[str, str]]:
    """The page's status and body, and Reddit's rate-limit headers (named in lower case)."""
    request = urllib.request.Request(url, headers=headers)
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urllib.request.urlopen(request, timeout=30, context=context) as response:
            return response.status, response.read(), _rate_limit(response.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), _rate_limit(e.headers)


def _rate_limit(headers) -> dict[str, str]:
    return {name.lower(): value for name, value in (headers or {}).items() if name.lower().startswith("x-ratelimit")}


@dataclass(frozen=True)
class _Window:
    """Reddit's current 10 minutes, as its answers said: how many reads are left, and when they come back."""

    left: float
    ends: datetime


def _http_request(method: str, url: str, headers: dict, body: bytes | None = None,
                  timeout: float = BUCKET_TIMEOUT) -> tuple[int, bytes]:
    """One call to Google (the metadata server or Cloud Storage): its status and body."""
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class Bucket:
    """The saved checks in a private Google Cloud Storage bucket, shared by the server and the daily pre-check (check
    ahead, 13 Oct 2026). Plain HTTPS calls to Cloud Storage's JSON API, with the access token Cloud Run's metadata
    server gives the service account, kept until shortly before it runs out. A problem never stops a check: it is said
    once in the server's window (never with the token), and the bucket is left alone for BUCKET_REST_SECONDS.
    `request` and `clock` (seconds) can be swapped for fakes, which is how the tests avoid the network."""

    def __init__(self, name: str, request=_http_request, clock=time.monotonic):
        self.name = name
        self._request = request
        self._clock = clock
        self._token: str | None = None
        self._token_until = 0.0
        self._resting_until = 0.0
        self.problems = 0  # how many calls failed, for reports
        self._lock = threading.Lock()

    def get(self, name: str) -> bytes | None:
        """The object's content, or None when there is none (or the bucket can't be read just now)."""
        path = url_quote(BUCKET_PREFIX + name, safe="")
        status, body = self._call("GET", f"{STORAGE_API}/b/{url_quote(self.name, safe='')}/o/{path}?alt=media")
        return body if status == 200 else None

    def put(self, name: str, data: bytes) -> bool:
        """Saves the object whole (a new version replaces the old one); whether it was saved."""
        path = url_quote(BUCKET_PREFIX + name, safe="")
        status, _ = self._call("POST", f"{UPLOAD_API}/b/{url_quote(self.name, safe='')}/o?uploadType=media&name={path}",
                               data, {"Content-Type": "application/json; charset=utf-8"})
        return status == 200

    def _call(self, method: str, url: str, body: bytes | None = None,
              headers: dict | None = None) -> tuple[int | None, bytes]:
        token = self._access_token()
        if token is None:
            return None, b""
        try:
            status, data = self._request(method, url, {"Authorization": f"Bearer {token}", **(headers or {})}, body,
                                         timeout=BUCKET_TIMEOUT)
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as error:
            self._failed(f"{type(error).__name__}")
            return None, b""
        if status == 401:
            with self._lock:
                self._token = None  # run out early: the next call asks for a new one
        if status not in (200, 404):
            self._failed(f"HTTP {status}")
        return status, data

    def _access_token(self) -> str | None:
        with self._lock:
            now = self._clock()
            if now < self._resting_until:
                return None
            if self._token is not None and now < self._token_until:
                return self._token
        try:
            status, data = self._request("GET", METADATA_TOKEN_URL, {"Metadata-Flavor": "Google"}, None,
                                         timeout=BUCKET_TIMEOUT)
            answer = json.loads(data) if status == 200 else None
            token, lasts = (answer["access_token"], float(answer["expires_in"])) if answer else (None, 0.0)
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, ValueError, KeyError,
                TypeError) as error:
            self._failed(f"no access token ({type(error).__name__})")
            return None
        if token is None:
            self._failed(f"no access token (HTTP {status})")
            return None
        with self._lock:
            self._token, self._token_until = token, self._clock() + lasts - TOKEN_MARGIN_SECONDS
        return token

    def _failed(self, why: str) -> None:
        with self._lock:
            self.problems += 1
            self._resting_until = self._clock() + BUCKET_REST_SECONDS
            first = self.problems == 1
        if first:
            print(f"The live checks' bucket {self.name} couldn't be used ({why}): checks go on with this machine's "
                  f"folder and Reddit, and the bucket is tried again every {BUCKET_REST_SECONDS} s.", file=sys.stderr,
                  flush=True)


def checker_from_env(environ=os.environ, **settings) -> "LiveChecker":
    """The live checker real answers and the pre-check use: with the bucket CREDIBLE_RECS_LIVE_CACHE_BUCKET names, or
    this machine's folder only when it is unset. `settings` go to LiveChecker (the tests give a folder)."""
    name = (environ.get(BUCKET_VAR) or "").strip()
    return LiveChecker(bucket=Bucket(name) if name else None, **settings)


class LiveChecker:
    """`fetch`, `clock` and `sleep` can be swapped for fakes, which is how the tests avoid the network (a fake `fetch`
    may leave out the rate-limit headers: then the burst and refill pace every read). Safe to ask from several threads
    at once (engine.pipeline checks the comments of an answer together). `bucket`: where checks are kept besides this
    machine's folder (Bucket), or None."""

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR, fetch=_http_get, clock=None, sleep=time.sleep,
                 min_interval: float = LIVE_CHECK_MIN_INTERVAL, burst: int = LIVE_CHECK_BURST,
                 refill: float = LIVE_CHECK_REFILL_SECONDS, reserve: int = LIVE_CHECK_RESERVE,
                 spread_below: int = LIVE_CHECK_SPREAD_BELOW, max_wait: float = LIVE_CHECK_MAX_WAIT_SECONDS,
                 bucket: Bucket | None = None):
        self.cache_dir = Path(cache_dir)
        self.bucket = bucket
        self._fetch = fetch
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleep = sleep
        self.min_interval = min_interval
        self.burst, self.refill = burst, refill  # reads allowed at once, and seconds for one more to be allowed
        self._last_call: datetime | None = None  # when the latest call started (or will start)
        self._allowed = float(burst)  # reads allowed at once when _last_call started
        self.reserve, self.spread_below = reserve, spread_below  # reads kept for others; fewer left spread out
        self.max_wait = max_wait  # seconds a read may wait for Reddit's next 10 minutes; longer, it isn't made
        self._window: _Window | None = None  # what Reddit last said is left, until its 10 minutes end
        self._in_flight = 0  # reads started that Reddit hasn't answered yet
        self._lock = threading.Lock()

    def check(self, comment_url: str, quote: str, max_age: timedelta = MAX_AGE, wait: bool = True) -> LiveResult:
        """Whether `quote` can be shown: its comment is still on Reddit and still says it, word for word. A saved check
        made within `max_age` answers (never one over 48 hours old, whatever is asked); else Reddit is read. With
        wait=False, Reddit is read only if that needs no wait for its allowance, else the check is "later"."""
        body = self._comment_text(comment_url, min(max_age, MAX_AGE), wait)
        if body is _PUT_OFF:
            return LiveResult("later", "not read now: it would have waited for Reddit's allowance")
        return _outcome(body, quote)

    def saved_check(self, comment_url: str, quote: str) -> LiveResult | None:
        """What a saved check from the last 48 hours says about `quote`, without reading Reddit; None if there is none."""
        entry = self._saved(embed_url(comment_url), MAX_AGE)
        return None if entry is None else _outcome(entry["text"], quote)

    def checked_at(self, comment_url: str, max_age: timedelta = MAX_AGE) -> datetime | None:
        """When the comment was last read on Reddit, if a saved check made within `max_age` (48 hours at most) says
        so; None otherwise. Reddit is never read for it."""
        entry = self._saved(embed_url(comment_url), min(max_age, MAX_AGE))
        return None if entry is None else datetime.fromisoformat(entry["fetched_at"])

    def _comment_text(self, comment_url: str, max_age: timedelta, wait: bool = True) -> str | None:
        """The comment's text as Reddit shows it now, from a check saved within `max_age` when there is one; None if
        unreadable; _PUT_OFF if there is none and reading it would wait (wait=False)."""
        url = embed_url(comment_url)
        saved = self._saved(url, max_age)
        if saved is not None:
            return saved["text"]
        try:
            got = self._get(url, wait)
            if got is None or got is _PUT_OFF:
                return got  # None: it would have waited longer than max_wait, so it is unreadable now (not saved)
            status, page, fetched_at = got
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
            return None  # not saved: the next answer asks again (HTTPException: a page cut off halfway, 12 Oct 2026)
        if status != 200:
            return None
        found = _BODY.search(page.decode("utf-8", "replace"))
        if not found:
            return None  # a page with no comment on it, or a new layout: never guessed
        text = html.unescape(" ".join(_TAG.sub(" ", found.group(1)).split()))
        data = json.dumps({"fetched_at": fetched_at.isoformat(), "text": text}, ensure_ascii=False).encode("utf-8")
        self._keep(_entry_name(url), data)
        if self.bucket is not None:
            self.bucket.put(_entry_name(url), data)
        return text

    def _saved(self, url: str, max_age: timedelta) -> dict | None:
        """The check of this page saved within `max_age`: from this machine's folder, else from the bucket (then kept
        in the folder too, so the next check needs no call); None when neither has one."""
        name = _entry_name(url)
        try:
            here = _entry((self.cache_dir / name).read_bytes())
        except OSError:
            here = None
        if self._within(here, max_age):
            return here
        if self.bucket is None:
            return None
        there = _entry(self.bucket.get(name))
        if not self._within(there, max_age):
            return None
        self._keep(name, json.dumps(there, ensure_ascii=False).encode("utf-8"))
        return there

    def _within(self, entry: dict | None, max_age: timedelta) -> bool:
        return entry is not None and self._clock() - datetime.fromisoformat(entry["fetched_at"]) < max_age

    def _keep(self, name: str, data: bytes) -> None:
        """Saves a check in this machine's folder, whole under another name and then renamed: a check reading it at the
        same moment sees all of it or none."""
        cache_file = self.cache_dir / name
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        partial = cache_file.with_name(f"{cache_file.stem}.{os.getpid()}.{threading.get_ident()}.tmp")
        partial.write_bytes(data)
        partial.replace(cache_file)

    def _get(self, url: str, wait: bool = True):
        """The page, and when its call started: at least min_interval after the call before it started, whichever
        thread made that one, and when Reddit's allowance allows (what Reddit last said is left, spread out no slower
        than one every `refill` seconds; until it has said, a burst, then one every `refill` seconds). Nothing is read
        or counted when it would wait and wait=False (_PUT_OFF), or when it would wait longer than max_wait for
        Reddit's next 10 minutes (None)."""
        with self._lock:
            now = self._clock()
            spaced = now if self._last_call is None else max(now,
                                                             self._last_call + timedelta(seconds=self.min_interval))
            start, window, allowed = spaced, self._window, self._allowed
            if window is not None and spaced >= window.ends:
                window, allowed = None, float(self.burst)  # Reddit's 10 minutes are over: its allowance is back
            if window is not None:
                spare = window.left - self._in_flight - self.reserve
                if spare < 1:  # nothing left to spend: the first read of Reddit's next 10 minutes
                    start = window.ends + timedelta(seconds=WINDOW_MARGIN_SECONDS)
                    window, allowed = None, float(self.burst) - 1
                elif spare < self.spread_below and self._last_call is not None:
                    gap = min((window.ends - self._last_call) / spare, timedelta(seconds=self.refill))
                    start = max(spaced, self._last_call + gap)
            else:
                if self._last_call is not None:
                    allowed = min(self.burst, allowed + (spaced - self._last_call).total_seconds() / self.refill)
                if allowed < 1:  # the burst is spent: wait for the next read to be allowed
                    start = spaced + timedelta(seconds=(1 - allowed) * self.refill)
                    allowed = 1.0
                allowed -= 1
            if not wait and start > spaced:
                return _PUT_OFF
            if (start - now).total_seconds() > self.max_wait:
                return None
            self._window, self._allowed, self._last_call = window, allowed, start
            self._in_flight += 1
        try:
            if start > now:
                self._sleep((start - now).total_seconds())
            status, page, *headers = self._fetch(url, {"User-Agent": USER_AGENT})
        finally:
            with self._lock:
                self._in_flight -= 1
        if headers:
            self._learn(headers[0], self._clock())
        return status, page, start

    def _learn(self, headers: dict[str, str], at: datetime) -> None:
        """What a page Reddit sent `at` says is left of its 10 minutes. Answers can come back out of order, so within
        the same 10 minutes the count left only ever goes down."""
        try:
            left, reset = float(headers["x-ratelimit-remaining"]), float(headers["x-ratelimit-reset"])
        except (KeyError, TypeError, ValueError):
            return
        ends = at + timedelta(seconds=reset)
        with self._lock:
            now = self._window
            if now is None or at >= now.ends or ends > now.ends + timedelta(seconds=WINDOW_MARGIN_SECONDS):
                self._window = _Window(left, ends)
            else:
                self._window = _Window(min(now.left, left), now.ends)


def _outcome(body: str | None, quote: str) -> LiveResult:
    """What the comment's text as Reddit shows it now (None: it couldn't be read) says about showing `quote`."""
    if body is None:
        return LiveResult("unknown", "the comment's page couldn't be read")
    if body.strip() in _GONE:
        return LiveResult("gone", f"the comment now reads {body.strip()}")
    if find_quote(body, quote) is None:
        return LiveResult("changed", "the comment no longer says this: it was edited")
    return LiveResult("ok", "the comment still says this")


def _entry_name(url: str) -> str:
    """The name a check of this embed page is saved under, in the folder and in the bucket."""
    return f"{hashlib.sha256(url.encode()).hexdigest()[:32]}.json"


def _entry(data: bytes | None) -> dict | None:
    """A saved check ({"fetched_at", "text"}) read from its file or object; None when there is none or it can't be
    read (it is then read on Reddit again)."""
    if data is None:
        return None
    try:
        entry = json.loads(data)
        datetime.fromisoformat(entry["fetched_at"])
    except (ValueError, KeyError, TypeError):
        return None
    return entry if isinstance(entry.get("text"), str) else None
