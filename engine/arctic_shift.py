"""Finds Reddit threads through the Arctic Shift archive API (arctic-shift.photon-reddit.com).

Arctic Shift is a free, community-run archive of Reddit, not Reddit's official API, with no uptime guarantee.
Noemi approved it on 7 Oct 2026 for finding threads only: we keep each post's id, title, subreddit and
counts, never its text, because an archive may still hold comments people later deleted on Reddit.
The threads themselves are read live through Parse (engine/parse_reddit.py).

Being considerate with a free service (filling the library is a batch job, so speed doesn't matter): every
answer is cached for 48 hours, calls are spaced 10 seconds apart, and when the service says it is busy
("Maybe slow down a bit", "Too many requests") it gets one retry after a 30-second pause, never a loop.
"""

import hashlib
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import certifi

from engine.config import CACHE_MAX_AGE_HOURS

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://arctic-shift.photon-reddit.com/api/"
DEFAULT_CACHE_DIR = REPO_ROOT / ".cache" / "arctic_shift"
USER_AGENT = "credible-recs research prototype (github.com/Noemi-fe/credible_recs)"

MAX_AGE = timedelta(hours=CACHE_MAX_AGE_HOURS)
BUSY = (422, 429)  # the service's "slow down" answers
RETRY_PAUSE = 30.0  # seconds before the one retry
KEPT_FIELDS = ("id", "subreddit", "title", "num_comments", "score", "created_utc", "permalink", "link_flair_text", "removed_by_category")


class ArcticShiftError(Exception):
    pass


def _http_get(url: str, headers: dict) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers=headers)
    context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urllib.request.urlopen(request, timeout=60, context=context) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except urllib.error.URLError as e:
        raise ArcticShiftError(f"couldn't reach Arctic Shift: {e.reason}") from e


class ArcticShiftClient:
    """`fetch`, `clock` and `sleep` can be swapped for fakes, which is how the tests avoid the network."""

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR, fetch=_http_get, clock=None, sleep=time.sleep, min_interval: float = 10.0):
        self.cache_dir = Path(cache_dir)
        self._fetch = fetch
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleep = sleep
        self._min_interval = min_interval
        self._last_call: datetime | None = None
        self.purge_cache()

    def search_posts(self, subreddit: str, title: str, limit: int = 25) -> list[dict]:
        """Posts in one subreddit whose title matches, with only the fields needed to choose threads."""
        params = {"subreddit": subreddit, "title": title, "limit": limit}
        cache_file = self.cache_dir / f"{hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:32]}.json"
        if cache_file.exists():
            entry = json.loads(cache_file.read_text(encoding="utf-8"))
            if self._clock() - datetime.fromisoformat(entry["fetched_at"]) < MAX_AGE:
                return entry["posts"]

        url = BASE_URL + "posts/search?" + urllib.parse.urlencode(params)
        status, data, body = self._get(url)
        if status in BUSY:
            self._sleep(RETRY_PAUSE)
            status, data, body = self._get(url)
        if status != 200 or not isinstance(data, dict) or data.get("error") or not isinstance(data.get("data"), list):
            reason = data.get("error") if isinstance(data, dict) else None
            raise ArcticShiftError(f"Arctic Shift answered {status} to a search in r/{subreddit}: {reason or body[:200]!r}")

        posts = [{field: p.get(field) for field in KEPT_FIELDS} for p in data["data"]]
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({"fetched_at": self._last_call.isoformat(), "posts": posts}, ensure_ascii=False), encoding="utf-8")
        return posts

    def _get(self, url: str) -> tuple[int, object, bytes]:
        if self._last_call and (waited := (self._clock() - self._last_call).total_seconds()) < self._min_interval:
            self._sleep(self._min_interval - waited)
        status, body = self._fetch(url, {"User-Agent": USER_AGENT, "Accept": "application/json"})
        self._last_call = self._clock()
        try:
            return status, json.loads(body), body
        except ValueError:
            return status, {}, body

    def purge_cache(self) -> None:
        """Removes every cached answer older than 48 hours."""
        for path in self.cache_dir.glob("*.json"):
            try:
                fetched_at = datetime.fromisoformat(json.loads(path.read_text(encoding="utf-8"))["fetched_at"])
            except (ValueError, KeyError):
                fetched_at = None
            if fetched_at is None or self._clock() - fetched_at >= MAX_AGE:
                path.unlink()
