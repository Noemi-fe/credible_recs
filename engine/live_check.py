"""The last check before a quote is shown: is the comment still on Reddit, saying what the quote says?

Saved threads can be days or weeks old, and Arctic Shift's archive keeps comments people later deleted. So just
before an answer shows a quote, its comment is read live through Reddit's embed page (embed.reddit.com, what
Reddit's official oEmbed widget loads to show a comment on another site; approved by Noemi on 9 Oct 2026), one
comment at a time, and only for quotes about to be shown. The result:

    ok        the comment is there and the quote is found in it word for word (engine.verify_quotes.find_quote)
    gone      the comment was deleted or removed: its text reads "[deleted]" or "[removed]"
    changed   the comment is there but no longer says this: it was edited
    unknown   the page couldn't be read (an error, a timeout, or a page whose layout has changed)

Only "ok" is shown. Anything else drops the quote: strict by default, so a page Reddit redesigns makes quotes
disappear rather than show unchecked.

Being considerate, as with the other sources: calls are spaced out (LIVE_CHECK_MIN_INTERVAL seconds), and what a
comment page said is kept for 48 hours (the deletion rule), so asking again about the same comment costs nothing.
Only the comment's own text is kept, never the page around it.
"""

import hashlib
import html
import json
import re
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import certifi

from engine.config import CACHE_MAX_AGE_HOURS, LIVE_CHECK_MIN_INTERVAL
from engine.verify_quotes import find_quote

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_DIR = REPO_ROOT / ".cache" / "live_check"
USER_AGENT = "credible-recs research prototype (github.com/Noemi-fe/credible_recs)"
MAX_AGE = timedelta(hours=CACHE_MAX_AGE_HOURS)

Status = Literal["ok", "gone", "changed", "unknown"]

# The comment's text on the embed page: <div class="text-14"><div ... class="inline-block ..."> text </div></div>.
_BODY = re.compile(r'<div class="text-14">\s*<div[^>]*class="inline-block[^"]*"[^>]*>(.*?)</div>\s*</div>', re.S)
_TAG = re.compile(r"<[^>]+>")
_GONE = ("[deleted]", "[removed]")


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


def _http_get(url: str, headers: dict) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers=headers)
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urllib.request.urlopen(request, timeout=30, context=context) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


class LiveChecker:
    """`fetch`, `clock` and `sleep` can be swapped for fakes, which is how the tests avoid the network."""

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR, fetch=_http_get, clock=None, sleep=time.sleep,
                 min_interval: float = LIVE_CHECK_MIN_INTERVAL):
        self.cache_dir = Path(cache_dir)
        self._fetch = fetch
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleep = sleep
        self.min_interval = min_interval
        self._last_call: datetime | None = None

    def check(self, comment_url: str, quote: str) -> LiveResult:
        """Whether `quote` can be shown: its comment is still on Reddit and still says it, word for word."""
        body = self._comment_text(comment_url)
        if body is None:
            return LiveResult("unknown", "the comment's page couldn't be read")
        if body.strip() in _GONE:
            return LiveResult("gone", f"the comment now reads {body.strip()}")
        if find_quote(body, quote) is None:
            return LiveResult("changed", "the comment no longer says this: it was edited")
        return LiveResult("ok", "the comment still says this")

    def _comment_text(self, comment_url: str) -> str | None:
        """The comment's text as Reddit shows it now, from the 48-hour cache when it is there; None if unreadable."""
        url = embed_url(comment_url)
        cache_file = self.cache_dir / f"{hashlib.sha256(url.encode()).hexdigest()[:32]}.json"
        if cache_file.exists():
            entry = json.loads(cache_file.read_text(encoding="utf-8"))
            if self._clock() - datetime.fromisoformat(entry["fetched_at"]) < MAX_AGE:
                return entry["text"]
        try:
            status, page = self._get(url)
        except (urllib.error.URLError, TimeoutError, OSError):
            return None  # not saved: the next answer asks again
        if status != 200:
            return None
        found = _BODY.search(page.decode("utf-8", "replace"))
        if not found:
            return None  # a page with no comment on it, or a new layout: never guessed
        text = html.unescape(" ".join(_TAG.sub(" ", found.group(1)).split()))
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"fetched_at": self._last_call.isoformat(), "text": text}, ensure_ascii=False),
                              encoding="utf-8")
        return text

    def _get(self, url: str) -> tuple[int, bytes]:
        if self._last_call and (waited := (self._clock() - self._last_call).total_seconds()) < self.min_interval:
            self._sleep(self.min_interval - waited)
        self._last_call = self._clock()
        return self._fetch(url, {"User-Agent": USER_AGENT})
