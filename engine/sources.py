"""Module 2, retrieval: finds the Reddit threads, with their comments, that fit an understood request.

Every data source sits behind one interface, `Source`: give it a request from module 1, get back the most
relevant threads, best first. So a new source can plug in later (Reddit's public API closes in 2027) without
touching the rest of the engine. Three sources exist today:

- LocalSource reads thread files saved on this machine (the gold set now, a larger saved library later).
- ParseSource searches Reddit live through the Parse reddit.com API, spending as few credits as it can.
- ArchiveSource finds and reads threads in Arctic Shift's archive, for free (Noemi, 9 Oct 2026). Its threads are
  marked as read from the archive, and answers wait for a live check before quoting them (engine/library.py).

All hand back threads without deleted or removed comments, since there's nothing in them to quote. Everything
else (link-only comments, comments in other languages) passes through untouched; later modules decide about those.
ParseSource and ArchiveSource can also hand back threads as fetched (find_raw_threads), which is how the library
saves them.

Candidate threads are ranked so buying advice beats popularity (rank_posts). For the library, ParseSource can also
pick a mix of thread kinds (Noemi, 7 Oct 2026): advice threads give the picks, long-term-use threads the strongest
evidence, warning threads the "skip these" list and the downsides (thread_kind, choose_mix).
"""

import json
import math
import re
from datetime import UTC, datetime
from functools import cache
from pathlib import Path
from typing import Protocol, runtime_checkable

from engine.arctic_shift import ArcticShiftClient, ArcticShiftError
from engine.bright_data import DISCOVER_POSTS_EACH, BrightDataError
from engine.config import (
    ARCHIVE_DOWN_MINUTES,
    BRIGHT_DATA_ADD_RECORD_RESERVE,
    BRIGHT_DATA_ADD_SEARCHES,
    BRIGHT_DATA_ADD_WARNING_SEARCHES,
    BRIGHT_DATA_MONTHLY_RECORDS,
    LIBRARY_MIX,
    LIBRARY_THREADS_PER_PRODUCT,
    MAX_THREADS_PER_SUBREDDIT,
    SKINCARE_RECENT_YEARS,
)
from engine.gold import load_threads
from engine.models import Thread
from engine.parse_reddit import ParseRedditClient
from engine.query import PRODUCT_TYPES, TITLE_WORDS, ParsedQuery
from engine.text import one_edit_apart


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
    """True if the text names the product, allowing one wrong letter in long names ("suncreen" for "sunscreen")."""
    if _product_pattern(product_type).search(text):
        return True
    long_names = [w for w in _product_words(product_type) if " " not in w and len(w) >= TYPO_MIN_LENGTH]
    tokens = {t.removesuffix("s") for t in re.findall(r"[a-z]+", text.lower()) if len(t) >= TYPO_MIN_LENGTH - 1}
    return any(one_edit_apart(t, w) for t in tokens for w in long_names)


# Typos are only forgiven in names this long: shorter ones have real neighbours ("cleaner" is one letter from "cleanser").
TYPO_MIN_LENGTH = 9


def _product_words(product_type: str) -> tuple[str, ...]:
    known = {p.name: p.keywords + p.hints for p in PRODUCT_TYPES}
    return known.get(product_type, tuple(product_type.lower().split()))




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

# Added to the product's title word to find threads about things going wrong: "kettle died", "moisturizer regret".
WARNING_SEARCHES = {
    "kitchen": ("died", "broke", "regret", "avoid"),
    "skincare": ("irritation", "broke me out", "regret", "avoid"),
}
# Product types that fail in their own words (11 Oct 2026): "skillet died" found only "broke in my new skillet" (its
# first use). Used before the category's words.
WARNING_SEARCHES_BY_TYPE = {
    "cast iron skillet": ("cracked", "warped", "regret", "avoid"),
    "frying pan": ("peeling", "scratched", "regret", "avoid"),
    "saucepan": ("peeling", "scratched", "regret", "avoid"),
    "chef knife": ("chipped", "broke", "regret", "avoid"),
}


def warning_words(query: ParsedQuery) -> tuple[str, ...]:
    """The words a warning search adds to the product's title word ("kettle died"): its type's own, else its category's."""
    return WARNING_SEARCHES_BY_TYPE.get(query.product_type or "") or WARNING_SEARCHES.get(query.category, ())


class ParseSource:
    """Searches Reddit through the Parse reddit.com API, then fetches the most promising threads.

    Credits: every Parse call costs 2, so one request costs at most 2 × max_searches + 2 × limit credits
    (10 with the defaults: 2 searches and 3 threads; 16 for the library's 6 threads), and nothing for answers
    still in the client's 48-hour cache. With a finder (Arctic Shift) searching is free, so only the threads
    read cost credits: 2 × limit (12 for the library's 6). The free plan has 200 credits a month. Errors from
    Parse, such as the monthly credits running out, are passed on, never hidden.
    """

    def __init__(
        self,
        client: ParseRedditClient | None = None,
        max_searches: int = 2,
        min_comments: int = 5,
        finder: ArcticShiftClient | None = None,
        max_free_searches: int = 4,
        max_warning_searches: int = 4,
    ):
        self.client = client if client is not None else ParseRedditClient()
        self.max_searches = max_searches
        # Optional free finder (Arctic Shift): searches cost nothing and only reading threads uses credits.
        self.finder = finder
        self.max_free_searches = max_free_searches
        self.max_warning_searches = max_warning_searches  # free warning searches, on top of max_free_searches
        self.min_comments = min_comments  # a thread with fewer comments has too little to learn from

    def find_threads(self, query: ParsedQuery, limit: int = 3, mix: dict | None = None, fill: bool = True) -> list[Thread]:
        return [without_unusable_comments(t) for t in self.find_raw_threads(query, limit, mix, fill)]

    def find_raw_threads(self, query: ParsedQuery, limit: int = 3, mix: dict | None = None, fill: bool = True) -> list[Thread]:
        """The same threads as find_threads, for the same credits, but as fetched: deleted and removed comments included.

        The library saves them this way, so a reply to a deleted comment still has the comment it answers.
        Without a `mix`, the `limit` best threads are fetched. With one ({"advice": 3, "long_term": 1, "warning": 2},
        say), the threads fetched are that mix of kinds (choose_mix), and `fill=False` fetches only the kinds in the
        mix: if none is found, nothing is fetched and no credit is spent on threads.
        """
        if query.status != "ok" or limit < 1:
            return []
        ranked = self.rank_candidates(query)
        chosen = ranked[:limit] if mix is None else choose_mix(query, ranked, total=limit, mix=mix, fill=fill)
        return [self.client.get_thread(p["subreddit"], _post_id(p)) for p in chosen]

    def rank_candidates(self, query: ParsedQuery) -> list[dict]:
        """Every candidate post from the searches, best first, without fetching any thread."""
        if query.status != "ok":
            return []
        if self.finder is not None:
            ranked = self._usable(query, self._search_free(query))
            if ranked:
                return ranked
        # No finder, or the free search found nothing usable: Parse's paid search.
        return self._usable(query, self._search_with_parse(query))

    def _usable(self, query: ParsedQuery, posts: list[dict]) -> list[dict]:
        return usable_posts(query, posts, self.min_comments)

    def _search_free(self, query: ParsedQuery) -> list[dict]:
        return search_archive(self.finder, query, self.max_free_searches, self.max_warning_searches)

    def _search_with_parse(self, query: ParsedQuery) -> list[dict]:
        """Search results for the first `max_searches` (subreddit, search term) pairs, each post once.

        Pairs go term by term, most specific first, and for each term subreddit by subreddit, most specific first.
        """
        pairs = [(subreddit, term) for term in query.search_terms for subreddit in query.subreddits]
        posts: dict[str, dict] = {}  # post id -> post, so a post found twice is kept once
        for subreddit, term in pairs[: self.max_searches]:
            for post in self.client.search(subreddit, term).get("posts") or []:
                posts.setdefault(_post_id(post), post)
        return list(posts.values())


def usable_posts(query: ParsedQuery, posts: list[dict], min_comments: int) -> list[dict]:
    """The posts in the request's subreddits with at least `min_comments` comments, ranked best first (rank_posts)."""
    wanted = {s.lower() for s in query.subreddits}
    # Search results can include posts from other subreddits (crossposts, for example).
    posts = [
        p for p in posts
        if str(p.get("subreddit", "")).lower() in wanted and (p.get("num_comments") or 0) >= min_comments
    ]
    return rank_posts(query, posts)


def search_archive(finder: ArcticShiftClient, query: ParsedQuery, max_free_searches: int = 4,
                   max_warning_searches: int = 4, raise_if_nothing: bool = False) -> list[dict]:
    """Arctic Shift results, in two rounds, each post once.

    1. The product's title words, term by term and subreddit by subreddit, up to `max_free_searches`.
    2. Warning searches, so threads about failures and regrets are among the candidates: the first title word
       with each of WARNING_SEARCHES ("kettle died", "kettle regret"…), in the request's most specialist
       subreddit, up to `max_warning_searches`.
    A busy or failing service ends the free search, warning searches included; results found before that are
    still used. With `raise_if_nothing`, a failure before anything was found is passed on (ArcticShiftError), so a
    service that is down isn't mistaken for a search that found nothing. Parse's paid search never runs warning
    searches: they would cost credits.
    """
    terms = finder_terms(query.product_type)
    pairs = [(subreddit, term) for term in terms for subreddit in query.subreddits][:max_free_searches]
    warnings = warning_words(query)[:max_warning_searches]
    pairs += [(query.subreddits[0], f"{terms[0]} {warning}") for warning in warnings]
    posts: dict[str, dict] = {}
    for subreddit, term in pairs:
        try:
            found = finder.search_posts(subreddit, term, limit=25)
        except ArcticShiftError:
            if raise_if_nothing and not posts:
                raise
            break
        for post in found:
            posts.setdefault(_post_id(post), post)
    return list(posts.values())


# --- From Arctic Shift's archive, for free (Noemi, 9 Oct 2026) ---

class ArchiveSource:
    """Finds threads with Arctic Shift's free search and reads them from its archive too: no Parse credit at all.

    Noemi's decision of 9 Oct 2026, instead of paying for Parse. Threads are chosen exactly as ParseSource chooses
    them with a finder (the same searches, ranking and mix of kinds); only the reading differs. If the archive's
    search finds nothing usable, nothing is read: there is no paid search to fall back on. Errors from Arctic Shift
    are passed on, never hidden: a search that fails before finding anything (the service busy or down) raises, rather
    than looking like a product with no threads; one that fails later keeps what it found, as ParseSource does.

    The archive may still hold comments people later deleted on Reddit, so every thread it reads is marked read_from
    "arctic_shift", and answers don't quote it until a live check has read it on Reddit through Parse
    (`python -m engine.library check-live`).
    """

    def __init__(
        self,
        client: ArcticShiftClient | None,
        min_comments: int = 5,
        max_free_searches: int = 4,
        max_warning_searches: int = 4,
    ):
        # The Arctic Shift client that searches and reads. It is never built here, so code that gives none (a test
        # that passes no finder) can't reach the network: with None, nothing is found or read.
        self.client = client
        self.min_comments = min_comments  # a thread with fewer comments has too little to learn from
        self.max_free_searches = max_free_searches
        self.max_warning_searches = max_warning_searches

    def find_threads(self, query: ParsedQuery, limit: int = 3, mix: dict | None = None, fill: bool = True) -> list[Thread]:
        return [without_unusable_comments(t) for t in self.find_raw_threads(query, limit, mix, fill)]

    def find_raw_threads(self, query: ParsedQuery, limit: int = 3, mix: dict | None = None, fill: bool = True) -> list[Thread]:
        """The threads as read from the archive, deleted and removed comments included (as stubs). `mix` and `fill`
        work as in ParseSource.find_raw_threads."""
        if query.status != "ok" or limit < 1:
            return []
        ranked = self.rank_candidates(query)
        chosen = ranked[:limit] if mix is None else choose_mix(query, ranked, total=limit, mix=mix, fill=fill)
        return [self.client.get_thread(_post_id(p), p["subreddit"]) for p in chosen]

    def rank_candidates(self, query: ParsedQuery) -> list[dict]:
        """Every candidate post from the archive's searches, best first, without reading any thread."""
        if query.status != "ok" or self.client is None:
            return []
        found = search_archive(self.client, query, self.max_free_searches, self.max_warning_searches, raise_if_nothing=True)
        return usable_posts(query, found, self.min_comments)


# --- Through Bright Data: Reddit's own search, and reads (Noemi's request, 11 Oct 2026) ---

class BrightDataSource:
    """Finds threads with Reddit's own search through Bright Data, inside the request's decided subreddits, and reads
    them through Bright Data too: no Parse credit and no archive, so the library can grow while Arctic Shift is down or
    Parse's credits are spent (Noemi, 11 Oct 2026: "to not get stuck with parse and everything else").

    The searches mirror the archive's (search_archive): the product's title words, subreddit by subreddit, up to
    BRIGHT_DATA_ADD_SEARCHES, then BRIGHT_DATA_ADD_WARNING_SEARCHES warning searches ("kettle died") in the most
    specialist subreddit, in one Bright Data job (engine.bright_data.BrightDataClient.discover: 1 record per post
    listed). The candidates are ranked and mixed exactly as the other sources' (usable_posts, choose_mix). Threads
    already in the library or on the gold set's unlabelled list (`skip_ids`) are never candidates, so no record is
    spent on them. Every thread read is as Reddit shows it now (read_from "bright_data"): no live check is waiting.

    Records: an add never goes past its record cap: `max_records`, or by default what's left this month minus
    BRIGHT_DATA_ADD_RECORD_RESERVE, kept for live checks. The searches are refused before they start if even they could
    go past it (BrightDataError, nothing spent); reads go in the chosen order while the most each could cost (1 for the
    post, 1 per comment Reddit counted) still fits, and the ones left are named in `not_read` and `notes`. With no
    client (a test that gives none), nothing is found or read.
    """

    def __init__(self, client, min_comments: int = 5, skip_ids: set[str] | None = None, max_records: int | None = None,
                 max_searches: int = BRIGHT_DATA_ADD_SEARCHES, max_warning_searches: int = BRIGHT_DATA_ADD_WARNING_SEARCHES,
                 posts_each: int = DISCOVER_POSTS_EACH):
        self.client = client
        self.min_comments = min_comments  # a thread with fewer comments has too little to learn from
        self.skip_ids = set(skip_ids or ())
        self.max_records = max_records
        self.max_searches = max_searches
        self.max_warning_searches = max_warning_searches
        self.posts_each = posts_each
        self.not_read: list[str] = []  # chosen threads left unread: the record cap was reached
        self.notes: list[str] = []  # what the command line should tell Noemi
        self._used_before: int | None = None
        self._cap = 0

    def find_threads(self, query: ParsedQuery, limit: int = 3, mix: dict | None = None, fill: bool = True) -> list[Thread]:
        return [without_unusable_comments(t) for t in self.find_raw_threads(query, limit, mix, fill)]

    def find_raw_threads(self, query: ParsedQuery, limit: int = 3, mix: dict | None = None, fill: bool = True) -> list[Thread]:
        """The chosen threads as Bright Data reads them, deleted and removed comments included (as stubs), within the
        record cap. `mix` and `fill` work as in ParseSource.find_raw_threads."""
        if query.status != "ok" or limit < 1 or self.client is None:
            return []
        ranked = self.rank_candidates(query)
        chosen = ranked[:limit] if mix is None else choose_mix(query, ranked, total=limit, mix=mix, fill=fill)
        planned, spent = [], self._spent()
        for n, post in enumerate(chosen):
            most = 1 + max(int(post.get("num_comments") or 0), 1)
            if spent + most > self._cap:
                self.not_read = [_post_id(p) for p in chosen[n:]]
                self.notes.append(f"Stopped before reading {len(self.not_read)} more thread"
                                  f"{'s' if len(self.not_read) != 1 else ''}: the next could take the Bright Data "
                                  f"records past this add's cap of {self._cap}.")
                break
            planned.append(post)
            spent += most
        self._read_together(planned)
        return [self.client.get_thread(post["url"]) for post in planned]

    def _read_together(self, posts: list[dict]) -> None:
        """Reads the chosen threads in batches when the client can (BrightDataClient.prefetch), so each read after it
        comes from the cache; if a batch fails, the threads are simply read one at a time."""
        if not posts or not hasattr(self.client, "prefetch"):
            return
        try:
            self.client.prefetch([(post["url"], int(post.get("num_comments") or 0)) for post in posts])
        except BrightDataError as e:
            if e.account_problem:
                raise
            self.notes.append(f"Reading the threads together failed ({e}); they were read one at a time.")

    def rank_candidates(self, query: ParsedQuery) -> list[dict]:
        """Every candidate post from the searches, best first, without reading any thread."""
        if query.status != "ok" or self.client is None:
            return []
        searches = self._searches(query)
        self._start_budget(len(searches) * self.posts_each)
        found = self.client.discover(searches, posts_each=self.posts_each)
        posts = [_as_post(p) for p in found if p.id not in self.skip_ids]
        return usable_posts(query, posts, self.min_comments)

    def _searches(self, query: ParsedQuery) -> list[tuple[str, str]]:
        terms = finder_terms(query.product_type)
        pairs = [(subreddit, term) for term in terms for subreddit in query.subreddits][:self.max_searches]
        warnings = warning_words(query)[:self.max_warning_searches]
        return pairs + [(query.subreddits[0], f"{terms[0]} {warning}") for warning in warnings]

    def _start_budget(self, searching: int) -> None:
        """Sets this add's record cap, and refuses the searches if even they could go past it."""
        used = self.client.records_used_this_month()
        left = max(0, BRIGHT_DATA_MONTHLY_RECORDS - used)
        default = max(0, left - BRIGHT_DATA_ADD_RECORD_RESERVE)
        self._cap = default if self.max_records is None else max(0, min(self.max_records, left))
        self._used_before = used
        if searching > self._cap:
            why = (f"the {BRIGHT_DATA_ADD_RECORD_RESERVE}-record reserve kept for live checks" if self.max_records is None
                   else "its cap")
            raise BrightDataError(f"Not enough Bright Data records for this add: its searches could use up to "
                                  f"{searching}, and {self._cap} are left after {why} ({used} used this month); "
                                  "nothing was spent.")

    def _spent(self) -> int:
        return self.client.records_used_this_month() - (self._used_before or 0)


def _as_post(found) -> dict:
    """A thread Bright Data's search found, in the shape the ranking reads (rank_posts, thread_kind, choose_mix)."""
    return {"id": found.id, "subreddit": found.subreddit, "title": found.title, "num_comments": found.num_comments,
            "created_utc": found.created_at.timestamp() if found.created_at else None, "url": found.url}


# --- Never stuck: one source first, another when it fails (11 Oct 2026) ---

class FallbackSource:
    """Asks the first source; when it fails with one of `fails_with` (Arctic Shift down, by default), asks the second.

    The library's default since 11 Oct 2026 (LIBRARY_READER "auto"): Arctic Shift's archive first, which searches and
    reads for free with whole reply trees, then Bright Data. The second source is never asked when the first works, so
    no Bright Data record is spent then. What happened is in `notes`, with the second source's own notes.
    """

    def __init__(self, first, second, fails_with: tuple[type[Exception], ...] = (ArcticShiftError,),
                 first_name: str = "Arctic Shift", second_name: str = "Bright Data", memo: Path | None = None,
                 clock=None):
        self.first, self.second = first, second
        self.fails_with = fails_with
        self.names = (first_name, second_name)
        self._notes: list[str] = []
        # Where a failure of the first source is remembered (ARCHIVE_DOWN_MINUTES), so the next run doesn't wait for it
        # to fail again; None remembers nothing.
        self.memo = Path(memo) if memo is not None else None
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def notes(self) -> list[str]:
        return self._notes + list(getattr(self.second, "notes", []))

    def find_threads(self, query: ParsedQuery, limit: int = 3, mix: dict | None = None, fill: bool = True) -> list[Thread]:
        return [without_unusable_comments(t) for t in self.find_raw_threads(query, limit, mix, fill)]

    def find_raw_threads(self, query: ParsedQuery, limit: int = 3, mix: dict | None = None, fill: bool = True) -> list[Thread]:
        if self._recently_down():
            return _ask(self.second, query, limit, mix, fill)
        try:
            threads = _ask(self.first, query, limit, mix, fill)
        except self.fails_with as e:
            self._fell_back(e)
            return _ask(self.second, query, limit, mix, fill)
        self._forget()
        return threads

    def rank_candidates(self, query: ParsedQuery) -> list[dict]:
        if self._recently_down():
            return self.second.rank_candidates(query)
        try:
            ranked = self.first.rank_candidates(query)
        except self.fails_with as e:
            self._fell_back(e)
            return self.second.rank_candidates(query)
        self._forget()
        return ranked

    def _fell_back(self, error: Exception) -> None:
        first, second = self.names
        self._notes.append(f"{first} couldn't be reached ({error}), so {second} found and read the threads instead.")
        if self.memo is not None:
            self.memo.parent.mkdir(parents=True, exist_ok=True)
            self.memo.write_text(json.dumps({"failed_at": self._clock().isoformat(), "error": str(error)[:300]}),
                                 encoding="utf-8")

    def _recently_down(self) -> bool:
        """Whether the first source failed less than ARCHIVE_DOWN_MINUTES ago (the memo says so): then it isn't asked."""
        if self.memo is None or not self.memo.exists():
            return False
        try:
            failed_at = datetime.fromisoformat(json.loads(self.memo.read_text(encoding="utf-8"))["failed_at"])
        except (OSError, ValueError, KeyError, TypeError):
            return False
        minutes = (self._clock() - failed_at).total_seconds() / 60
        if minutes >= ARCHIVE_DOWN_MINUTES:
            return False
        first, second = self.names
        self._notes.append(f"{first} failed {minutes:.0f} minutes ago, so {second} found and read the threads straight "
                           f"away (it is tried again after {ARCHIVE_DOWN_MINUTES} minutes).")
        return True

    def _forget(self) -> None:
        if self.memo is not None:
            self.memo.unlink(missing_ok=True)


def _ask(source, query: ParsedQuery, limit: int, mix: dict | None, fill: bool) -> list[Thread]:
    """A source's threads as fetched when it can give them (and a mix, when it can pick one), else its plain ones."""
    if hasattr(source, "find_raw_threads"):
        return source.find_raw_threads(query, limit=limit, mix=mix, fill=fill)
    return source.find_threads(query, limit=limit)


# --- Ranking candidate threads: buying advice beats popularity ---

# A thread where people ask for or compare recommendations: what the picks are built from.
_ADVICE = re.compile(
    r"\b(recommend\w*|suggest\w*|which|best|looking for|advice|help me|worth it|alternatives?|hg|holy grail"
    r"|favou?rites?|vs|versus|bifl|buy it for life|should i|request\w*)\b"
)
# A thread about living with a product for a long time: the evidence the brief values most.
_NUMBER_WORDS = r"one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen|twenty|thirty|forty|fifty"
_LONG_TERM = re.compile(
    rf"\b((\d+|{_NUMBER_WORDS})\s*(years?|yrs?)|decades?|long[- ]term|still going|review|outlast\w*|lifetime)\b"
)
# Flairs subreddits use for buying questions. A plain "Question" flair isn't one: it covers any question.
_ADVICE_FLAIRS = ("request", "product question", "advice", "recommendation")
_GONE = {"[deleted by user]", "[deleted]", "[removed]"}
# Recurring threads ("Daily recommendations…", "Weekly questions…") aren't about anyone's specific need.
# A title starting "Weekly…" counts only when it says it's such a thread: "Weekly exfoliator I could use" is a request.
_RECURRING = re.compile(
    r"^\s*(\[[^\]]*\]\s*)?(daily|weekly|monthly)\b.*\b(thread|questions?|discussion|recommendations?|help|chat)\b"
    r"|\bmegathread\b"
)
# Threads about looking after kitchen gear rather than choosing it: cleaning, seasoning, restoring, sharpening.
# "Easy to clean" is a buying need, so cleaning counts only as "cleaning" or "how I clean". Kitchen only: in
# skincare "restoring" is what a product does ("barrier restoring cream").
_CARE = re.compile(
    r"\b(cleaning|how (i|to|do you|do i|should i|we) (clean|season)|seasoning|re-?season\w*"
    r"|restor(e|ed|es|ing|ation)|sharpen\w*"
    r"|tips|recipes?|never cook|what to cook|how to use|foods? you should|sandblast\w*)\b"  # using gear rather than choosing it
)
# Shop news rather than anyone's experience: announcements, prices, sales, deals ("deal with" is something else).
# A plain "price" isn't one: budget questions use it.
_SHOP_NEWS = re.compile(r"\b(announc\w*|guess the price|price (drops?|cuts?|increases?|hikes?)|sales?|deals?(?!\s+with))\b")
# Threads with fewer comments give thin evidence. They still count, but a bigger thread on the same question wins
# (Noemi, 7 Oct 2026: don't drop small threads before there's enough to judge the request).
SMALL_THREAD = 15
_STOPWORDS = {
    "a", "an", "the", "for", "with", "without", "that", "this", "my", "me", "i", "im", "to", "of", "in", "on", "and",
    "or", "but", "is", "are", "be", "it", "its", "will", "would", "can", "could", "should", "doesnt", "dont", "wont",
    "actually", "really", "very", "good", "great", "nice", "best", "need", "want", "looking", "something", "some",
    "any", "skin", "under", "over", "less", "more", "max", "around", "about", "budget", "between", "than", "up",
    "pounds", "pound", "quid", "euros", "euro", "dollars", "bucks", "usd", "gbp", "eur",
}


def need_words(query: ParsedQuery) -> list[str]:
    """The specific part of a request, in a form titles can be matched against: "pour-over" -> "pourover"."""
    product_words = set(query.product_type.split()) | {w for t in TITLE_WORDS.get(query.product_type, ()) for w in t.split()}
    words = []
    for token in re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)*", query.text.lower()):
        word = _stem(re.sub(r"['-]", "", token))
        if word.isdigit() or word in _STOPWORDS or word in product_words or word in words:
            continue
        words.append(word)
    return words


def rank_posts(query: ParsedQuery, posts: list[dict], now: datetime | None = None) -> list[dict]:
    """Candidate posts best first.

    Left out:
    - deleted or removed posts;
    - recurring threads ("Daily…", "Weekly…", megathreads).

    Points:
    - asks for or compares recommendations, in its words or a buying flair: 3, and a question mark 0.5 more;
    - is about long-term use: 1;
    - matches the specific need: 1.5 per word, at most 2 words;
    - names the product in the title: 2;
    - the number of comments, on a slow scale (log10: 10 comments 1, 100 comments 2, 1,000 comments 3);
    - under 15 comments: minus 2;
    - in the most specialist subreddit: 0.5;
    - skincare only, posted more than 3 years (SKINCARE_RECENT_YEARS) before `now`: minus 1.5, since formulas
      change. `now` is the real clock unless a test gives one; kitchen threads can be any age;
    - shop news (announcements, "guess the price", price drops, sales, deals) and, for kitchen gear, threads about
      looking after or using it (cleaning, seasoning, restoring, sharpening, tips, recipes), unless the
      title has advice words: minus 2.
      They rank lower rather than being left out, since some still hold useful experience (Noemi, 7 Oct 2026).
    Advice earns its 3 points only when the title also names the product or the need; a request about something
    else earns 1. The product counts even with one wrong letter in a long name ("suncreen").
    So a viral post can't outrank a smaller thread that is actually buying advice, a tiny thread only wins
    when nothing bigger asks the same question, and an old skincare thread needs a clear lead to stay ahead.
    """
    needs = need_words(query)
    too_old = _years_before(now or datetime.now(UTC), SKINCARE_RECENT_YEARS)
    scored = []
    for post in posts:
        title = (post.get("title") or "").strip()
        lowered = title.lower()
        if lowered in _GONE or post.get("removed_by_category") or (post.get("selftext") or "").strip() in _GONE:
            continue
        if _RECURRING.search(lowered):
            continue
        flair = (post.get("link_flair_text") or "").lower()
        names_it = mentions_product(title, query.product_type)
        need_matches = min(2, sum(_title_has(lowered, word) for word in needs))
        if _is_advice(lowered, flair):
            # Full points only for advice about this product or this need; a request about something else
            # ("corporate gifts", flaired [Request]) earns 1.
            score = 3.0 if (names_it or need_matches) else 1.0
        else:
            score = 0.0
        score += 0.5 if "?" in title else 0.0
        score += 1.0 if _LONG_TERM.search(lowered) else 0.0
        score += 1.5 * need_matches
        score += 2.0 if names_it else 0.0
        score += math.log10(1 + (post.get("num_comments") or 0))
        score -= 2.0 if (post.get("num_comments") or 0) < SMALL_THREAD else 0.0
        score += 0.5 if query.subreddits and _subreddit(post) == query.subreddits[0].lower() else 0.0
        score -= 1.5 if query.category == "skincare" and _posted_before(post, too_old) else 0.0
        if not _ADVICE.search(lowered) and (_SHOP_NEWS.search(lowered) or (query.category == "kitchen" and _CARE.search(lowered))):
            score -= 2.0
        scored.append((score, post))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [post for _, post in scored]


def _is_advice(lowered_title: str, lowered_flair: str) -> bool:
    return bool(_ADVICE.search(lowered_title)) or any(f in lowered_flair for f in _ADVICE_FLAIRS)


def _subreddit(post: dict) -> str:
    return str(post.get("subreddit", "")).lower()


def _years_before(moment: datetime, years: int) -> datetime:
    """The same day and time, `years` calendar years earlier (28 February for a 29 February)."""
    try:
        return moment.replace(year=moment.year - years)
    except ValueError:
        return moment.replace(year=moment.year - years, day=28)


def _posted_before(post: dict, moment: datetime) -> bool:
    """Whether the post was made before `moment`. A post with no usable date isn't: an unknown age costs nothing."""
    try:
        return datetime.fromtimestamp(float(post["created_utc"]), UTC) < moment
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return False


# --- Thread kinds and the library's mix (Noemi, 7 Oct 2026) ---

# Something went wrong: what feeds the "skip these" list and the downsides. Each category has its own words:
# "peeling" is a failing pan but, in skincare, a product, and "breakouts" or "acne" alone are usually the need
# ("best cleanser for breakouts"), so neither is a skincare warning.
# "regret" only as a real regret: never "will I regret not using…", "no regrets" or "won't regret" (11 Oct 2026).
_SHARED_WARNINGS = (r"(?<!no )(?<!won't )(?<!never )(?<!don't )(?<!will i )regret\w*(?! not)(?! skipping)"
                    r"|avoid|disappoint(?:ed|ing)|worst|returned")
_WARNINGS = {
    "kitchen": re.compile(
        # "broke" only as a failure ("broke within a year", "it broke"), never "broke them down" or "broke student";
        # "broke in" only before a length of time ("broke in 6 months"), never "broke in my new pan" (its first use).
        rf"\b(?:{_SHARED_WARNINGS}|died|dead|broke (?:after|within)"
        r"|broke in (?:a|an|one|two|three|four|five|six|\d+|under|less|the first|just|only)\b"
        r"|(?:it|mine|already|just|has|have|had) broke|broken"
        r"|failed|stopped working|don['’]?t buy|never again|recall(?:s|ed)?"
        r"|only lasted|lasted only|rust(?:s|ed|ing|y)?|cracked|chipped|flaking|peeling|leaking|warp(?:ed|ing|s)?"
        r"|scratch(?:ed|es))\b"
    ),
    "skincare": re.compile(
        rf"\b(?:{_SHARED_WARNINGS}|irritat(?:ion|ed|ing)|reactions?|burn(?:s|ed|t|ing)?|rash(?:es)?|(?:broke|breaking) me out)\b"
    ),
}
_ANY_WARNING = re.compile(rf"\b(?:{_SHARED_WARNINGS})\b")  # for a category without its own words
# Long-term use, as ranking reads it, plus follow-ups: "ten years later", "Update: my pan after…".
_LONG_TERM_KIND = re.compile(_LONG_TERM.pattern + r"|\b(years later|update[sd]?)\b")
THREAD_KINDS = ("advice", "long_term", "warning")  # the kinds the library mixes; anything else is "other"


def thread_kind(post: dict, category: str, product_type: str | None = None) -> str:
    """What a thread can feed, judged from its title (and flair): "warning", "long_term", "advice" or "other".

    - warning: something went wrong ("died", "regret", "broke me out"…), with words for each category. With a
      `product_type`, the title must name that product, so "broke them down" in a recipe isn't a pan warning.
    - long_term: living with a product for a long time ("10 years", "decades", "years later", "update", "review").
    - advice: asking for or comparing recommendations, in its words or a buying flair ("Request").
    When several apply, a warning wins, then long-term use, then advice: "Mine only lasted 2 years: which kettle
    actually lasts?" is first of all a story of a kettle that failed.
    """
    title = (post.get("title") or "").lower()
    if _is_warning(title, category, product_type):
        return "warning"
    if _LONG_TERM_KIND.search(title):
        return "long_term"
    if _is_advice(title, (post.get("link_flair_text") or "").lower()):
        return "advice"
    return "other"


def _is_warning(lowered_title: str, category: str, product_type: str | None) -> bool:
    """A warning names the product (when we know which) and isn't a care project ("sandblasted it since it rusted")."""
    if not _WARNINGS.get(category, _ANY_WARNING).search(lowered_title):
        return False
    if category == "kitchen" and _CARE.search(lowered_title):
        return False
    return product_type is None or mentions_product(lowered_title, product_type)


def choose_mix(
    query: ParsedQuery,
    ranked_posts: list[dict],
    total: int = LIBRARY_THREADS_PER_PRODUCT,
    mix: dict = LIBRARY_MIX,
    per_subreddit: int | None = None,
    fill: bool = True,
) -> list[dict]:
    """Up to `total` of the ranked posts, as a mix of thread kinds, returned in rank order.

    1. Going down the ranking, each kind takes posts until it has its share of the mix (by default 3 advice,
       1 long-term use and 2 warnings out of 6). A kind missing from the mix has no share.
    2. With `fill` (the default), slots left empty go to the best posts remaining: advice, long-term or warning
       threads first, "other" threads only when none of those is left. Without it, only the shares are taken,
       which is how the library fetches warnings only.
    Throughout, at most `per_subreddit` posts come from any one subreddit, so no single community's taste dominates.
    By default that's 2 (MAX_THREADS_PER_SUBREDDIT), or more for a product with few subreddits, so it can still
    reach `total`: a product with 2 subreddits may take 3 from each.
    """
    if per_subreddit is None:
        per_subreddit = max(MAX_THREADS_PER_SUBREDDIT, math.ceil(total / max(1, len(query.subreddits))))
    kinds = [thread_kind(post, query.category, query.product_type) for post in ranked_posts]
    chosen: set[int] = set()  # positions in the ranking
    per_kind: dict[str, int] = {}
    per_sub: dict[str, int] = {}

    def has_room(i: int) -> bool:
        return len(chosen) < total and per_sub.get(_subreddit(ranked_posts[i]), 0) < per_subreddit

    def take(i: int) -> None:
        chosen.add(i)
        per_kind[kinds[i]] = per_kind.get(kinds[i], 0) + 1
        per_sub[_subreddit(ranked_posts[i])] = per_sub.get(_subreddit(ranked_posts[i]), 0) + 1

    for i, kind in enumerate(kinds):
        if per_kind.get(kind, 0) < mix.get(kind, 0) and has_room(i):
            take(i)
    if fill:
        for useful in (True, False):  # the three useful kinds first, "other" threads last
            for i, kind in enumerate(kinds):
                if i not in chosen and (kind in THREAD_KINDS) == useful and has_room(i):
                    take(i)
    return [ranked_posts[i] for i in sorted(chosen)]


def _title_has(lowered_title: str, word: str) -> bool:
    """Whole words, two-word spellings ("pour over" for "pourover") and longer forms ("lasting" for "last")."""
    tokens = [re.sub(r"['-]", "", t) for t in re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)*", lowered_title)]
    candidates = tokens + [a + b for a, b in zip(tokens, tokens[1:])]
    return any(t == word or _stem(t) == word or (len(word) >= 4 and t.startswith(word)) for t in candidates)


def _stem(word: str) -> str:
    """A light plural trim: "lasts" -> "last", "years" -> "year"; short words like "pfas" stay as they are."""
    return word[:-1] if len(word) > 4 and word.endswith("s") and not word.endswith("ss") else word


def finder_terms(product_type: str) -> list[str]:
    """What to type into a title search for this product: its usual title words, else its own name."""
    return list(TITLE_WORDS.get(product_type, (product_type,)))


def _post_id(post: dict) -> str:
    # Reddit sometimes writes a post id with the "t3_" prefix it uses for posts.
    return str(post["id"]).removeprefix("t3_")
