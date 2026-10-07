"""Module 2, retrieval: finds the Reddit threads, with their comments, that fit an understood request.

Every data source sits behind one interface, `Source`: give it a request from module 1, get back the most
relevant threads, best first. So a new source can plug in later (Reddit's public API closes in 2027) without
touching the rest of the engine. Two sources exist today:

- LocalSource reads thread files saved on this machine (the gold set now, a larger saved library later).
- ParseSource searches Reddit live through the Parse reddit.com API, spending as few credits as it can.

Both hand back threads without deleted or removed comments, since there's nothing in them to quote. Everything
else (link-only comments, comments in other languages) passes through untouched; later modules decide about those.
"""

import re
from functools import cache
from pathlib import Path
from typing import Protocol, runtime_checkable

from engine.gold import load_threads
from engine.models import Thread
from engine.parse_reddit import ParseRedditClient
from engine.query import PRODUCT_TYPES, ParsedQuery


@runtime_checkable
class Source(Protocol):
    def find_threads(self, query: ParsedQuery, limit: int = 3) -> list[Thread]:
        """The `limit` most relevant threads for the request, best first. Nothing unless the request's status is "ok"."""
        ...


# --- What both sources share ---

def without_unusable_comments(thread: Thread) -> Thread:
    """A copy of the thread without deleted or removed comments. The thread passed in is left as it was."""
    return thread.model_copy(update={"comments": [c for c in thread.comments if c.status not in ("deleted", "removed")]})


@cache
def _product_pattern(product_type: str) -> re.Pattern:
    """Finds any word that names the product: whole words only, in any case, singular or plural.

    The words are the product's keywords and hints from module 1. A product module 1 doesn't list (a future
    AI parser might name one) falls back to the words of its own name.
    """
    known = {p.name: p.keywords + p.hints for p in PRODUCT_TYPES}
    words = known.get(product_type.strip().lower()) or tuple(product_type.lower().split())
    alternatives = "|".join(re.escape(word) for word in words) or "(?!)"  # (?!) never matches: no words, no mentions
    return re.compile(rf"\b(?:{alternatives})s?\b", re.IGNORECASE)


def mentions_product(text: str, product_type: str) -> bool:
    return bool(_product_pattern(product_type).search(text))


def relevance(thread: Thread, product_type: str) -> float:
    """3 points if the title names the product, 1 if the post body does, plus up to 1 for comments that do (full at 5)."""
    score = 3 if mentions_product(thread.title, product_type) else 0
    score += 1 if mentions_product(thread.body, product_type) else 0
    talking = sum(mentions_product(c.body, product_type) for c in thread.comments)
    return score + min(1, talking / 5)


# --- Threads saved on this machine ---

class LocalSource:
    """Reads thread files from a folder shaped like data/gold/threads/ and picks the most relevant ones.

    The folder is read on the first request and kept in memory. Any file with a problem stops the request
    with the full list of problems (engine.gold.GoldSetError), rather than quietly leaving the thread out.
    """

    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self._threads: list[Thread] | None = None

    def find_threads(self, query: ParsedQuery, limit: int = 3) -> list[Thread]:
        if query.status != "ok" or limit < 1:
            return []
        if self._threads is None:
            self._threads = load_threads(self.folder)

        candidates = [without_unusable_comments(t) for t in self._threads if t.category == query.category]
        scored = [(relevance(t, query.product_type), t) for t in candidates]
        # Highest score first; on a tie, the thread with more comments.
        best = sorted(
            ((score, t) for score, t in scored if score > 0),
            key=lambda pair: (pair[0], pair[1].num_comments),
            reverse=True,
        )
        return [t for _, t in best[:limit]]


# --- Live from Reddit, through Parse ---

class ParseSource:
    """Searches Reddit through the Parse reddit.com API, then fetches the most promising threads.

    Credits: every call costs 2, so one request costs at most 2 × max_searches + 2 × limit credits
    (10 with the defaults: 2 searches and 3 threads), and nothing for answers still in the client's
    48-hour cache. The free plan has 200 credits a month. Errors from Parse, such as the monthly
    credits running out, are passed on, never hidden.
    """

    def __init__(self, client: ParseRedditClient | None = None, max_searches: int = 2, min_comments: int = 5):
        self.client = client if client is not None else ParseRedditClient()
        self.max_searches = max_searches
        self.min_comments = min_comments  # a thread with fewer comments has too little to learn from

    def find_threads(self, query: ParsedQuery, limit: int = 3) -> list[Thread]:
        if query.status != "ok" or limit < 1:
            return []
        wanted = {s.lower() for s in query.subreddits}
        # Search results can include posts from other subreddits (crossposts, for example).
        posts = [
            p for p in self._search(query)
            if str(p.get("subreddit", "")).lower() in wanted and (p.get("num_comments") or 0) >= self.min_comments
        ]
        # Posts whose title names the product first, then the ones with more comments.
        posts.sort(
            key=lambda p: (mentions_product(p.get("title") or "", query.product_type), p.get("num_comments") or 0),
            reverse=True,
        )
        return [without_unusable_comments(self.client.get_thread(p["subreddit"], _post_id(p))) for p in posts[:limit]]

    def _search(self, query: ParsedQuery) -> list[dict]:
        """Search results for the first `max_searches` (subreddit, search term) pairs, each post once.

        Pairs go term by term, most specific first, and for each term subreddit by subreddit, most specific first.
        """
        pairs = [(subreddit, term) for term in query.search_terms for subreddit in query.subreddits]
        posts: dict[str, dict] = {}  # post id -> post, so a post found twice is kept once
        for subreddit, term in pairs[: self.max_searches]:
            for post in self.client.search(subreddit, term).get("posts") or []:
                posts.setdefault(_post_id(post), post)
        return list(posts.values())


def _post_id(post: dict) -> str:
    # Reddit sometimes writes a post id with the "t3_" prefix it uses for posts.
    return str(post["id"]).removeprefix("t3_")
