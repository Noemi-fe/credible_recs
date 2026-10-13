"""The last check before a quote is shown: is the comment still on Reddit, saying what the quote says?

Saved threads can be days or weeks old, and Arctic Shift's archive keeps comments people later deleted. So just
before an answer shows a quote, its comment is read live through Reddit's embed page (embed.reddit.com, what
Reddit's official oEmbed widget loads to show a comment on another site; approved by Noemi on 9 Oct 2026), one
comment at a time, and only for quotes about to be shown. The result:

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
"""

import hashlib
import html
import http.client
import json
import os
import re
import ssl
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import certifi

from engine.config import (CACHE_MAX_AGE_HOURS, LIVE_CHECK_BURST, LIVE_CHECK_MIN_INTERVAL, LIVE_CHECK_REFILL_SECONDS,
                           LIVE_CHECK_RESERVE, LIVE_CHECK_SPREAD_BELOW)
from engine.verify_quotes import find_quote

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = REPO_ROOT / ".cache" / "live_check"
USER_AGENT = "credible-recs research prototype (github.com/Noemi-fe/credible_recs)"
MAX_AGE = timedelta(hours=CACHE_MAX_AGE_HOURS)

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


class LiveChecker:
    """`fetch`, `clock` and `sleep` can be swapped for fakes, which is how the tests avoid the network (a fake `fetch`
    may leave out the rate-limit headers: then the burst and refill pace every read). Safe to ask from several threads
    at once (engine.pipeline checks the comments of an answer together)."""

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR, fetch=_http_get, clock=None, sleep=time.sleep,
                 min_interval: float = LIVE_CHECK_MIN_INTERVAL, burst: int = LIVE_CHECK_BURST,
                 refill: float = LIVE_CHECK_REFILL_SECONDS, reserve: int = LIVE_CHECK_RESERVE,
                 spread_below: int = LIVE_CHECK_SPREAD_BELOW):
        self.cache_dir = Path(cache_dir)
        self._fetch = fetch
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleep = sleep
        self.min_interval = min_interval
        self.burst, self.refill = burst, refill  # reads allowed at once, and seconds for one more to be allowed
        self._last_call: datetime | None = None  # when the latest call started (or will start)
        self._allowed = float(burst)  # reads allowed at once when _last_call started
        self.reserve, self.spread_below = reserve, spread_below  # reads kept for others; fewer left spread out
        self._window: _Window | None = None  # what Reddit last said is left, until its 10 minutes end
        self._in_flight = 0  # reads started that Reddit hasn't answered yet
        self._lock = threading.Lock()

    def check(self, comment_url: str, quote: str, wait: bool = True) -> LiveResult:
        """Whether `quote` can be shown: its comment is still on Reddit and still says it, word for word. With
        wait=False a comment that isn't saved is read only if that needs no wait for Reddit's allowance, else it is
        "later"."""
        body = self._comment_text(comment_url, wait)
        if body is _PUT_OFF:
            return LiveResult("later", "not read now: it would have waited for Reddit's allowance")
        if body is None:
            return LiveResult("unknown", "the comment's page couldn't be read")
        if body.strip() in _GONE:
            return LiveResult("gone", f"the comment now reads {body.strip()}")
        if find_quote(body, quote) is None:
            return LiveResult("changed", "the comment no longer says this: it was edited")
        return LiveResult("ok", "the comment still says this")

    def _comment_text(self, comment_url: str, wait: bool = True) -> str | None:
        """The comment's text as Reddit shows it now, from the 48-hour cache when it is there; None if unreadable;
        _PUT_OFF if it isn't saved and reading it would wait (wait=False)."""
        url = embed_url(comment_url)
        cache_file = self.cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()[:32]}.json"
        if cache_file.exists():
            entry = json.loads(cache_file.read_text(encoding="utf-8"))
            if self._clock() - datetime.fromisoformat(entry["fetched_at"]) < MAX_AGE:
                return entry["text"]
        try:
            got = self._get(url, wait)
            if got is None:
                return _PUT_OFF
            status, page, fetched_at = got
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException):
            return None  # not saved: the next answer asks again (HTTPException: a page cut off halfway, 12 Oct 2026)
        if status != 200:
            return None
        found = _BODY.search(page.decode("utf-8", "replace"))
        if not found:
            return None  # a page with no comment on it, or a new layout: never guessed
        text = html.unescape(" ".join(_TAG.sub(" ", found.group(1)).split()))
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        # Written whole under another name, then renamed: a check reading it at the same moment sees all of it or none.
        partial = cache_file.with_name(f"{cache_file.stem}.{os.getpid()}.{threading.get_ident()}.tmp")
        partial.write_text(json.dumps({"fetched_at": fetched_at.isoformat(), "text": text}, ensure_ascii=False),
                           encoding="utf-8")
        partial.replace(cache_file)
        return text

    def _get(self, url: str, wait: bool = True) -> tuple[int, bytes, datetime] | None:
        """The page, and when its call started: at least min_interval after the call before it started, whichever
        thread made that one, and when Reddit's allowance allows (what Reddit last said is left; until it has said, a
        burst, then one every `refill` seconds). None, with nothing read or counted, if wait=False and it would wait."""
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
                    start = max(spaced, self._last_call + (window.ends - self._last_call) / spare)
            else:
                if self._last_call is not None:
                    allowed = min(self.burst, allowed + (spaced - self._last_call).total_seconds() / self.refill)
                if allowed < 1:  # the burst is spent: wait for the next read to be allowed
                    start = spaced + timedelta(seconds=(1 - allowed) * self.refill)
                    allowed = 1.0
                allowed -= 1
            if not wait and start > spaced:
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
