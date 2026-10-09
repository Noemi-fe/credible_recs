"""Finds Reddit threads, and looks up commenters' numbers, through the Arctic Shift archive API
(arctic-shift.photon-reddit.com).

Arctic Shift is a free, community-run archive of Reddit, not Reddit's official API, with no uptime guarantee.
Noemi approved it on 7 Oct 2026 for finding threads and metadata only: we keep each post's id, title, subreddit
and counts, never its text, because an archive may still hold comments people later deleted on Reddit.
The threads themselves are read live through Parse (engine/parse_reddit.py).

Three questions it answers:
- search_posts: posts in one subreddit whose title matches (to find threads);
- user_stats: one account's numbers: when it was first and last active in the archive, how many comments and
  posts it wrote, its karma (for module 5's standing signs, through engine/profiles.py);
- comment_flairs: the flair shown next to the writer's name on given comments ("Dermatologist", "Home cook"):
  a short label people give themselves, not something they wrote, so it may be kept. Never the comment's text.

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
from collections.abc import Iterable
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
# One account's numbers kept from users/search (its "_meta"); the times are unix seconds. Nothing else is kept.
USER_FIELDS = (
    "earliest_comment_at", "earliest_post_at", "last_comment_at", "last_post_at",
    "num_comments", "num_posts", "post_karma", "comment_karma", "total_karma",
)
FLAIR_BATCH = 100  # comments/ids takes at most this many comment ids per call
MISSING = object()  # "nothing fresh in the cache": None can't say it, since None is a real answer (an unknown account)


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
    except (urllib.error.URLError, TimeoutError) as e:
        # No answer at all (a timeout, no network): reported like any failure, so callers can carry on.
        raise ArcticShiftError(f"couldn't reach Arctic Shift: {getattr(e, 'reason', e)}") from e


class ArcticShiftClient:
    """`fetch`, `clock` and `sleep` can be swapped for fakes, which is how the tests avoid the network."""

    def __init__(self, cache_dir: Path = DEFAULT_CACHE_DIR, fetch=_http_get, clock=None, sleep=time.sleep, min_interval: float = 10.0):
        self.cache_dir = Path(cache_dir)
        self._fetch = fetch
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleep = sleep
        self.min_interval = min_interval  # seconds between calls
        self.calls = 0  # calls made to Arctic Shift by this client (answers from the cache don't count)
        self._last_call: datetime | None = None
        self.purge_cache()

    def search_posts(self, subreddit: str, title: str, limit: int = 25) -> list[dict]:
        """Posts in one subreddit whose title matches, with only the fields needed to choose threads."""
        params = {"subreddit": subreddit, "title": title, "limit": limit}
        cached = self._cached(params, "posts")
        if cached is not MISSING:
            return cached
        found = self._ask(BASE_URL + "posts/search?" + urllib.parse.urlencode(params), f"a search in r/{subreddit}")
        posts = [{field: p.get(field) for field in KEPT_FIELDS} for p in found]
        self._save(params, "posts", posts)
        return posts

    def user_stats(self, author: str) -> dict | None:
        """One account's numbers in the archive (USER_FIELDS), or None when the archive doesn't know the account.

        "earliest_comment_at" and "earliest_post_at" are its first comment and post in the archive: the archive
        doesn't know when an account was created, so they only approximate its age ("active since"). None covers
        a deleted, suspended or renamed account, one never active, and an answer about a different account
        (the search may match a longer name that starts the same way).
        """
        key = {"user": author.lower()}  # Reddit names ignore capitals
        cached = self._cached(key, "user")
        if cached is not MISSING:
            return cached
        url = BASE_URL + "users/search?" + urllib.parse.urlencode({"author": author, "limit": 1})
        found = self._ask(url, f"a look-up of u/{author}")
        match = next((u for u in found if isinstance(u, dict) and str(u.get("author", "")).lower() == author.lower()), None)
        numbers = match.get("_meta") if match else None
        stats = {field: numbers.get(field) for field in USER_FIELDS} if isinstance(numbers, dict) else None
        self._save(key, "user", stats)
        return stats

    def comment_flairs(self, comment_ids: Iterable[str]) -> dict[str, str | None]:
        """{comment id: the flair next to its writer's name, or None} for each comment, asked FLAIR_BATCH at a time.

        Only each comment's id and flair are asked for, never its text. A comment the archive doesn't have counts
        as no flair. Each comment's flair is cached on its own, so asking again about any of them costs nothing.
        """
        ids = list(dict.fromkeys(comment_ids))
        flairs = {cid: self._cached({"comment_flair": cid}, "flair") for cid in ids}
        missing = [cid for cid in ids if flairs[cid] is MISSING]
        for start in range(0, len(missing), FLAIR_BATCH):
            batch = missing[start:start + FLAIR_BATCH]
            url = BASE_URL + "comments/ids?" + urllib.parse.urlencode({"ids": ",".join(batch), "fields": "id,author_flair_text"})
            found = {str(c.get("id", "")).removeprefix("t1_"): c.get("author_flair_text")
                     for c in self._ask(url, f"a look-up of {len(batch)} comments") if isinstance(c, dict)}
            for cid in batch:
                flair = found.get(cid)
                flairs[cid] = (flair.strip() or None) if isinstance(flair, str) else None
                self._save({"comment_flair": cid}, "flair", flairs[cid])
        return flairs

    def uncached_users(self, authors: Iterable[str]) -> list[str]:
        """The accounts user_stats would have to ask Arctic Shift about (no fresh answer in the cache), each once."""
        names: dict[str, str] = {}
        for author in authors:
            names.setdefault(author.lower(), author)  # one per account, as Reddit names ignore capitals
        return [name for name in names.values() if self._cached({"user": name.lower()}, "user") is MISSING]

    def uncached_comments(self, comment_ids: Iterable[str]) -> list[str]:
        """The comments comment_flairs would have to ask Arctic Shift about, each once."""
        return [cid for cid in dict.fromkeys(comment_ids) if self._cached({"comment_flair": cid}, "flair") is MISSING]

    # --- Inside one call: cache, spacing, one retry when busy ---

    def _ask(self, url: str, what: str) -> list:
        """The list Arctic Shift answers to `url`. When it says it is busy, one retry after a pause; any problem raises."""
        status, data, body = self._get(url)
        if status in BUSY:
            self._sleep(RETRY_PAUSE)
            status, data, body = self._get(url)
        if status != 200 or not isinstance(data, dict) or data.get("error") or not isinstance(data.get("data"), list):
            reason = data.get("error") if isinstance(data, dict) else None
            raise ArcticShiftError(f"Arctic Shift answered {status} to {what}: {reason or body[:200]!r}")
        return data["data"]

    def _get(self, url: str) -> tuple[int, object, bytes]:
        if self._last_call and (waited := (self._clock() - self._last_call).total_seconds()) < self.min_interval:
            self._sleep(self.min_interval - waited)
        self.calls += 1
        status, body = self._fetch(url, {"User-Agent": USER_AGENT, "Accept": "application/json"})
        self._last_call = self._clock()
        try:
            return status, json.loads(body), body
        except ValueError:
            return status, {}, body

    def _cache_file(self, key: dict) -> Path:
        return self.cache_dir / f"{hashlib.sha256(json.dumps(key, sort_keys=True).encode()).hexdigest()[:32]}.json"

    def _cached(self, key: dict, name: str):
        """The answer saved under `key` if it is younger than 48 hours, otherwise MISSING."""
        cache_file = self._cache_file(key)
        if cache_file.exists():
            entry = json.loads(cache_file.read_text(encoding="utf-8"))
            if self._clock() - datetime.fromisoformat(entry["fetched_at"]) < MAX_AGE:
                return entry[name]
        return MISSING

    def _save(self, key: dict, name: str, value) -> None:
        """Keeps one answer for 48 hours, stamped with the time of the call that fetched it."""
        cache_file = self._cache_file(key)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        entry = {"fetched_at": self._last_call.isoformat(), name: value}
        cache_file.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")

    def purge_cache(self) -> None:
        """Removes every cached answer older than 48 hours."""
        for path in self.cache_dir.glob("*.json"):
            try:
                fetched_at = datetime.fromisoformat(json.loads(path.read_text(encoding="utf-8"))["fetched_at"])
            except (ValueError, KeyError):
                fetched_at = None
            if fetched_at is None or self._clock() - fetched_at >= MAX_AGE:
                path.unlink()
