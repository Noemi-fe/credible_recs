"""Fetches Reddit threads through the Parse reddit.com API (parse.bot) and turns them into our Thread shape.

Parse is a third-party scraping service, not Reddit's official API. Noemi chose it on 7 Oct 2026, after
Reddit refused API access (see CLAUDE.md). The free plan is small (200 credits a month, 2 credits a call,
5 calls a minute), so this client:

- checks the subreddit is one of the decided ones before spending anything;
- caches every response, so asking twice costs once;
- deletes cached responses after 48 hours (the deletion rule);
- spaces calls at least 12 seconds apart;
- logs every paid call and refuses to go over the monthly credits.

The key goes in .env as PARSE_API_KEY=<your key>.

Command line:
    python -m engine.parse_reddit fetch <thread link> [<thread link> ...]   save threads into data/gold/threads/
    python -m engine.parse_reddit usage                                      credits used this month
"""

import hashlib
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import certifi

from engine.config import (
    CACHE_MAX_AGE_HOURS,
    PARSE_CALLS_PER_MINUTE,
    PARSE_CREDITS_PER_CALL,
    PARSE_MONTHLY_CREDITS,
    SUBREDDITS,
)
from engine.models import Author, Comment, Thread

REPO_ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://api.parse.bot/scraper/5c1e1643-5ce6-4086-9883-3886b0c0e506/"
DEFAULT_CACHE_DIR = REPO_ROOT / ".cache" / "parse_reddit"
DEFAULT_ENV_FILE = REPO_ROOT / ".env"
DEFAULT_GOLD_DIR = REPO_ROOT / "data" / "gold"

MAX_AGE = timedelta(hours=CACHE_MAX_AGE_HOURS)
MIN_SECONDS_BETWEEN_CALLS = 60 / PARSE_CALLS_PER_MINUTE


class ParseAPIError(Exception):
    pass


def _ssl_context() -> ssl.SSLContext:
    # Python from python.org on macOS has no certificates of its own; certifi brings the standard set.
    return ssl.create_default_context(cafile=certifi.where())


def _http_get(url: str, headers: dict) -> tuple[int, bytes]:
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=60, context=_ssl_context()) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, TimeoutError) as e:
        # No answer at all (a timeout, no network): reported like any Parse failure, so callers such as the
        # library refresh count it and carry on or stop, instead of crashing. No credit is logged for it.
        raise ParseAPIError(f"couldn't reach Parse: {getattr(e, 'reason', e)}") from e


class ParseRedditClient:
    """Talks to Parse. `fetch`, `clock` and `sleep` can be swapped for fakes, which is how the tests avoid spending credits."""

    def __init__(
        self,
        api_key: str | None = None,
        cache_dir: Path = DEFAULT_CACHE_DIR,
        fetch=_http_get,
        clock=None,
        sleep=time.sleep,
        env_file: Path = DEFAULT_ENV_FILE,
        offline: bool = False,
    ):
        self._api_key = api_key
        self.offline = offline  # answer only from the cache: evaluation must never spend credits
        self._env_file = Path(env_file)
        self.cache_dir = Path(cache_dir)
        self.usage_log = self.cache_dir / "usage.jsonl"
        self._fetch = fetch
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleep = sleep
        self.purge_cache()

    def get_thread(self, subreddit: str, post_id: str, limit: int = 500, sort: str = "top") -> Thread:
        """One thread with its comments. `limit` caps top-level comments (Parse allows up to 500); replies always come too."""
        category = category_for(subreddit)
        params = {"post_id": post_id, "subreddit": subreddit, "sort": sort, "limit": limit}
        fetched_at, data = self._call("get_post_comments", params, expect="post")
        return to_thread(data, category, fetched_at)

    def search(self, subreddit: str, query: str, limit: int = 25, sort: str = "relevance", time_filter: str = "all") -> dict:
        """Parse's search results for one subreddit, as Parse returns them."""
        category_for(subreddit)
        params = {"query": query, "subreddit": subreddit, "sort": sort, "time_filter": time_filter, "limit": limit}
        return self._call("search_posts", params)[1]

    def credits_used_this_month(self) -> int:
        now = self._clock()
        return sum(
            entry["credits"]
            for entry in self._usage_entries()
            if (entry["at"].year, entry["at"].month) == (now.year, now.month)
        )

    def purge_cache(self) -> None:
        """The deletion rule: removes every cached response older than 48 hours."""
        for path in (self.cache_dir / "responses").glob("*.json"):
            try:
                fetched_at = datetime.fromisoformat(json.loads(path.read_text(encoding="utf-8"))["fetched_at"])
            except (ValueError, KeyError):
                fetched_at = None
            if fetched_at is None or self._clock() - fetched_at >= MAX_AGE:
                path.unlink()

    # --- Inside one call: cache, key, budget, rate limit, request, log ---

    def _call(self, endpoint: str, params: dict, expect: str | None = None) -> tuple[datetime, dict]:
        """`expect` names a field a good answer must contain; an answer without it is an error and isn't cached."""
        cache_file = self._cache_file(endpoint, params)
        if cache_file.exists():
            entry = json.loads(cache_file.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(entry["fetched_at"])
            if self._clock() - fetched_at < MAX_AGE:
                return fetched_at, entry["response"]

        if self.offline:
            raise ParseAPIError(f"offline: no saved answer for {endpoint} {params}; nothing was fetched")
        key = self._key()
        used = self.credits_used_this_month()
        if used + PARSE_CREDITS_PER_CALL > PARSE_MONTHLY_CREDITS:
            raise ParseAPIError(
                f"This call would go over the monthly {PARSE_MONTHLY_CREDITS} credits ({used} used); nothing was fetched."
            )
        self._wait_for_rate_limit()

        url = BASE_URL + endpoint + "?" + urllib.parse.urlencode(params)
        status, body = self._fetch(url, {"X-API-Key": key, "Accept": "application/json"})
        if status != 200:
            raise ParseAPIError(f"Parse answered {status} to {endpoint}: {body[:300].decode(errors='replace')}")

        fetched_at = self._clock()
        data = json.loads(body)
        self._log_usage(endpoint, fetched_at)
        if isinstance(data, dict) and "status" in data:  # Parse wraps good answers: {"status": "success", "data": ...}
            if data["status"] != "success" or "data" not in data:
                raise ParseAPIError(f"Parse's answer to {endpoint} was not a success: {str(data)[:300]}")
            data = data["data"]
        if expect and (not isinstance(data, dict) or expect not in data):
            raise ParseAPIError(f"Parse's answer to {endpoint} has no {expect!r}: {str(data)[:300]}")
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        entry = {"fetched_at": fetched_at.isoformat(), "endpoint": endpoint, "params": params, "response": data}
        cache_file.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        return fetched_at, data

    def _cache_file(self, endpoint: str, params: dict) -> Path:
        digest = hashlib.sha256(json.dumps([endpoint, params], sort_keys=True).encode()).hexdigest()[:32]
        return self.cache_dir / "responses" / f"{digest}.json"

    def _key(self) -> str:
        key = self._api_key or os.environ.get("PARSE_API_KEY") or _read_env_file(self._env_file).get("PARSE_API_KEY")
        if not key:
            raise ParseAPIError(
                "No Parse API key. Add a line PARSE_API_KEY=<your key> to the .env file in the project folder "
                "(create the key in your parse.bot dashboard)."
            )
        return key

    def _wait_for_rate_limit(self) -> None:
        entries = self._usage_entries()
        if entries:
            waited = (self._clock() - entries[-1]["at"]).total_seconds()
            if waited < MIN_SECONDS_BETWEEN_CALLS:
                self._sleep(MIN_SECONDS_BETWEEN_CALLS - waited)

    def _log_usage(self, endpoint: str, at: datetime) -> None:
        self.usage_log.parent.mkdir(parents=True, exist_ok=True)
        with self.usage_log.open("a", encoding="utf-8") as log:
            log.write(json.dumps({"at": at.isoformat(), "endpoint": endpoint, "credits": PARSE_CREDITS_PER_CALL}) + "\n")

    def _usage_entries(self) -> list[dict]:
        if not self.usage_log.exists():
            return []
        entries = [json.loads(line) for line in self.usage_log.read_text(encoding="utf-8").splitlines() if line.strip()]
        for entry in entries:
            entry["at"] = datetime.fromisoformat(entry["at"])
        return entries


def _read_env_file(path: Path) -> dict[str, str]:
    """Reads KEY=value lines from a .env file."""
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip().removeprefix("export ")
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip().strip("'\"")
    return values


# --- From a Parse response to our Thread shape ---

def category_for(subreddit: str) -> str:
    """The category a decided subreddit belongs to. Anything else is refused before a credit is spent."""
    name = subreddit.strip().removeprefix("r/").lower()
    for category, subs in SUBREDDITS.items():
        if name in (s.lower() for s in subs):
            return category
    decided = ", ".join(s for subs in SUBREDDITS.values() for s in subs)
    raise ValueError(f"r/{subreddit} is not one of the decided subreddits ({decided}); nothing was fetched")


def to_thread(data: dict, category: str, fetched_at: datetime) -> Thread:
    post = data["post"]
    post_id = _plain_id(post["id"])
    subreddit = post["subreddit"]
    comments = [_to_comment(c, post_id, subreddit) for c in data.get("comments", [])]
    return Thread(
        id=post_id,
        source="reddit",
        community=subreddit,
        category=category,
        title=post["title"],
        body=post.get("selftext") or "",
        author=_author(post.get("author")),
        created_at=_time(post["created_utc"]),
        score=post.get("score", 0),
        num_comments=post.get("num_comments", len(comments)),
        url=_web_url(post.get("permalink")) or f"https://www.reddit.com/r/{subreddit}/comments/{post_id}/",
        collected_at=fetched_at,
        comments=comments,
    )


def _to_comment(c: dict, post_id: str, subreddit: str) -> Comment:
    comment_id = _plain_id(c["id"])
    body = c.get("body") or ""  # kept exactly as written
    parent = c.get("parent_id")
    # Reddit marks a reply to the post with "t3_" and a reply to a comment with "t1_".
    parent_id = None if not parent or parent.startswith("t3_") or _plain_id(parent) == post_id else _plain_id(parent)
    return Comment(
        id=comment_id,
        parent_id=parent_id,
        author=_author(c.get("author")),
        body=body,
        created_at=_time(c["created_utc"]),
        score=c.get("score", 0),
        url=_web_url(c.get("permalink")) or f"https://www.reddit.com/r/{subreddit}/comments/{post_id}/comment/{comment_id}/",
        status={"[deleted]": "deleted", "[removed]": "removed"}.get(body.strip(), "ok"),
    )


def _author(name: str | None) -> Author | None:
    # Parse gives only the name: no account age, karma or flair.
    if not name or name.strip().lower() == "[deleted]":
        return None
    return Author(name=name)


def _time(value):
    return datetime.fromtimestamp(value, UTC) if isinstance(value, int | float) else value


def _web_url(permalink: str | None) -> str | None:
    if not permalink:
        return None
    return permalink if permalink.startswith("http") else "https://www.reddit.com/" + permalink.lstrip("/")


def _plain_id(value) -> str:
    return str(value).removeprefix("t1_").removeprefix("t3_")


# --- Links and the gold set ---

def parse_thread_url(url: str) -> tuple[str, str]:
    """(subreddit, thread id) from a Reddit thread or comment link."""
    if "://" not in url:
        url = "https://" + url
    parts = [p for p in urllib.parse.urlparse(url).path.split("/") if p]
    if "r" not in parts or "comments" not in parts or parts.index("comments") + 1 >= len(parts):
        raise ValueError(
            "can't find the thread in this link. Share links (.../s/...) don't contain it: open the link in a "
            "browser and copy the full address, which contains /comments/<thread id>/"
        )
    return parts[parts.index("r") + 1], parts[parts.index("comments") + 1]


def save_to_gold(thread: Thread, gold_dir: Path = DEFAULT_GOLD_DIR) -> Path:
    """Writes the thread as data/gold/threads/<id>.json. Never overwrites: the file may hold Noemi's edits."""
    path = Path(gold_dir) / "threads" / f"{thread.id}.json"
    if path.exists():
        raise FileExistsError(f"{path.name} already exists in the gold set and was not overwritten")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(thread.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


# --- Command line ---

def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("fetch", "usage"):
        print(__doc__)
        return 2
    client = ParseRedditClient()
    status = 0
    for link in argv[1:] if argv[0] == "fetch" else []:
        try:
            subreddit, post_id = parse_thread_url(link)
            if (DEFAULT_GOLD_DIR / "threads" / f"{post_id}.json").exists():
                print(f"{link}: {post_id}.json is already in the gold set; skipped, no credits spent")
                continue
            thread = client.get_thread(subreddit, post_id)
            path = save_to_gold(thread)
        except (ValueError, ParseAPIError, FileExistsError) as e:
            print(f"{link}: {e}")
            status = 1
            continue
        print(f"Saved {path.relative_to(REPO_ROOT)}: r/{thread.community}, {len(thread.comments)} comments")
    print(f"Parse credits used this month: {client.credits_used_this_month()} of {PARSE_MONTHLY_CREDITS} (the parse.bot dashboard has the exact figure)")
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
