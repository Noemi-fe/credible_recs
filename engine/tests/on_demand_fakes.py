"""Made-up stand-ins for on-demand reading's tests (14 Oct 2026): Arctic Shift's archive with three teapot threads,
Gemini extracting them, and Reddit's embed page showing their comments. Every text is invented; nothing reaches the
network.
"""

import json
import re
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

from engine.arctic_shift import ArcticShiftClient
from engine.gemini_extract import DailyLimitReached, GeminiClient

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)  # the tests' today (engine/tests/conftest.py), at noon UTC
POSTED = 1740819600  # 1 March 2025, 09:00 UTC

# Three teapot threads: each of three teapots recommended after years of use in every thread, one teapot warned
# against; one quote Gemini gets wrong on purpose (the word-for-word check drops it).
TEAPOT_THREADS = {
    "1tea001": ("tea", "Which teapot lasts for years?", [
        ("t1a", "My Brown Betty teapot has lasted 12 years and still pours perfectly.", "Brown Betty teapot"),
        ("t1b", "I've used a Hario Jumping teapot daily for 5 years, no problems at all.", "Hario Jumping teapot"),
        ("t1c", "Our Kinto Unitea teapot is 4 years old and still going strong.", "Kinto Unitea teapot"),
        ("t1d", "Mostly I just drink coffee these days, honestly.", None),
    ]),
    "1tea002": ("BuyItForLife", "Teapot recommendations? Mine cracked again", [
        ("t2a", "Had my Brown Betty teapot for 8 years now, it never chipped.", "Brown Betty teapot"),
        ("t2b", "My Hario Jumping teapot has been in daily use for 6 years.", "Hario Jumping teapot"),
        ("t2c", "Kinto Unitea teapot, 3 years of daily use and it still looks new.", "Kinto Unitea teapot"),
        ("t2d", "The Clunkware teapot cracked within 6 months, avoid it.", "Clunkware teapot"),
    ]),
    "1tea003": ("tea", "Best teapot for loose leaf?", [
        ("t3a", "Brown Betty teapot for 7 years, the best loose leaf brewer I've owned.", "Brown Betty teapot"),
        ("t3b", "Hario Jumping teapot for 4 years, the infuser is great for loose leaf.", "Hario Jumping teapot"),
        ("t3c", "Kinto Unitea teapot for 5 years, perfect for one person.", "Kinto Unitea teapot"),
    ]),
}
MISQUOTED = ("t1c", "Our Kinto teapot is four years old")  # not in its comment word for word: dropped by the check


def comment_url(thread_id: str, comment_id: str) -> str:
    subreddit = TEAPOT_THREADS[thread_id][0]
    return f"https://www.reddit.com/r/{subreddit}/comments/{thread_id}/x/{comment_id}/"


def body_of(comment_id: str) -> str:
    return next(body for _, (_, _, comments) in TEAPOT_THREADS.items() for cid, body, _ in comments if cid == comment_id)


class FakeArchive:
    """Answers Arctic Shift's posts/search, posts/ids and comments/tree from TEAPOT_THREADS (`threads` picks which)."""

    def __init__(self, threads=tuple(TEAPOT_THREADS), down=False):
        self.threads, self.down, self.requests = list(threads), down, []

    def __call__(self, url, headers):
        self.requests.append(url)
        if self.down:
            return 522, b"Cloudflare: the origin didn't answer"
        path, query = urlparse(url).path, parse_qs(urlparse(url).query)
        if path.endswith("/posts/search"):
            words = query["title"][0].lower().split()
            data = [self._post(tid) for tid in self.threads if TEAPOT_THREADS[tid][0] == query["subreddit"][0]
                    and all(word in TEAPOT_THREADS[tid][1].lower() for word in words) and "before" not in query]
        elif path.endswith("/posts/ids"):
            data = [self._post(tid) for tid in query["ids"][0].split(",") if tid in TEAPOT_THREADS]
        elif path.endswith("/comments/tree"):
            data = self._tree(query["link_id"][0].removeprefix("t3_"))
        else:
            return 404, b"{}"
        return 200, json.dumps({"data": data}).encode()

    def _post(self, thread_id: str) -> dict:
        subreddit, title, comments = TEAPOT_THREADS[thread_id]
        return {"id": thread_id, "subreddit": subreddit, "title": title, "selftext": "Looking for a sturdy one.",
                "author": "tea_asker", "created_utc": POSTED, "score": 40, "num_comments": 10 + len(comments),
                "permalink": f"/r/{subreddit}/comments/{thread_id}/x/", "link_flair_text": None}

    def _tree(self, thread_id: str) -> list:
        subreddit, _, comments = TEAPOT_THREADS[thread_id]
        return [{"kind": "t1", "data": {
            "id": cid, "parent_id": f"t3_{thread_id}", "link_id": f"t3_{thread_id}", "author": f"writer_{cid}",
            "body": body, "created_utc": POSTED + 3600, "score": 25,
            "permalink": f"/r/{subreddit}/comments/{thread_id}/x/{cid}/", "replies": ""}}
            for cid, body, _ in comments]

    def searches(self) -> int:
        return sum("/posts/search" in url for url in self.requests)


def archive(tmp_path, fake: FakeArchive) -> ArcticShiftClient:
    return ArcticShiftClient(cache_dir=tmp_path / "arctic_shift", fetch=fake, clock=lambda: NOW, sleep=lambda s: None,
                             min_interval=0)


class FakeGemini:
    """Writes each comment's mention, quoting it word for word (but for MISQUOTED); `daily_limit_after` calls, then
    answers as Gemini does when the day's free allowance is used up."""

    def __init__(self, daily_limit_after: int | None = None):
        self.daily_limit_after, self.calls = daily_limit_after, 0

    def __call__(self, url, headers, body):
        self.calls += 1
        if self.daily_limit_after is not None and self.calls > self.daily_limit_after:
            raise DailyLimitReached("Gemini answered 429: the free allowance for the day is used up", status=429)
        text = json.loads(body)["contents"][0]["parts"][0]["text"]
        mentions = []
        for cid in re.findall(r"^\[([a-z0-9]+)\] score", text, re.M):
            product = next((p for _, (_, _, cs) in TEAPOT_THREADS.items() for c, _, p in cs if c == cid), None)
            if product is None:
                continue
            quote = MISQUOTED[1] if cid == MISQUOTED[0] else body_of(cid)
            stance = "warn" if "avoid" in body_of(cid) else "recommend"
            mentions.append({"comment_id": cid, "product": product, "category": "kitchen", "product_type": "teapot",
                             "stance": stance, "evidence": "long-term use", "evidence_tags": ["long-term use"],
                             "quote": quote})
        return {"candidates": [{"content": {"parts": [{"text": json.dumps({"mentions": mentions})}]}}]}


def gemini(fake: FakeGemini) -> GeminiClient:
    return GeminiClient(key="test-key", model="gemini-test", fetch=fake, sleep=lambda s: None, min_interval=0)


class FakeEmbed:
    """Reddit's embed page for the teapot comments, each showing its comment as written."""

    def __init__(self):
        self.asked = []

    def __call__(self, url, headers):
        self.asked.append(url)
        cid = urlparse(url).path.rstrip("/").split("/")[-1]
        try:
            body = body_of(cid)
        except StopIteration:
            return 404, b"not found"
        return 200, (f'<html><div class="text-14"><div class="inline-block max-w-full w-full"><p>{body}</p></div>'
                     f'</div></html>').encode()


class Ticks:
    """A monotonic clock (seconds) that moves only when a test moves it."""

    def __init__(self, start: float = 1_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now
