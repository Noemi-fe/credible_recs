"""The library (module 2): the saved threads answers are prepared from, filled by `add` and kept honest by `refresh`.

Every test uses a fake source or a fake Parse client and a temporary folder, so no test touches the network,
spends credits or writes to data/library.
"""

import json
import re
from datetime import UTC, datetime, timedelta

import pytest

from engine import library
from engine.config import (
    LIBRARY_ARCHIVED_REFRESH_DAYS,
    LIBRARY_MIX,
    LIBRARY_REFRESH_DAYS,
    LIBRARY_THREADS_PER_PRODUCT,
    REDDIT_ARCHIVE_DAYS,
)
from engine.gold import DEFAULT_GOLD_DIR, load_threads
from engine.models import Thread
from engine.parse_reddit import ParseAPIError
from engine.query import PRODUCT_TYPES, parse_query
from engine.sources import LocalSource, ParseSource
from engine.tests.factories import make_comment, make_thread, write_gold

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
# changed 7 Oct 2026: library mix / refresh cadence approved by Noemi. Test threads are posted on 1 March 2025, so
# Reddit has archived them by NOW and they're due 90 days after saving, not 30: OLD moved from 1 August to 1 June.
OLD = "2026-06-01"  # more than 90 days before NOW: due for a refresh
RECENT = "2026-10-01"  # 6 days before NOW: not due
KETTLE = "electric kettle that lasts 10+ years"  # a clear request: an electric kettle, from BuyItForLife, tea, Coffee
OUT_OF_CREDITS = "This call would go over the monthly 200 credits (200 used); nothing was fetched."


def kettle_thread(thread_id: str, comments=("My Dualit kettle is 12 years old.",), collected_at=RECENT, **overrides) -> Thread:
    """A valid kitchen thread. `comments` are bodies, or full comment dicts when a test needs more control."""
    # Comments typed as text are dated when the thread was posted, so a test can move the posting date (created_at).
    dated = {"created_at": overrides["created_at"]} if "created_at" in overrides else {}
    fields = {
        "id": thread_id,
        "community": "BuyItForLife",
        "category": "kitchen",
        "title": "Electric kettle that lasts?",
        "body": "",
        "url": f"https://www.reddit.com/r/BuyItForLife/comments/{thread_id}/post/",
        "collected_at": collected_at,
        "num_comments": len(comments),
        "comments": [
            c if isinstance(c, dict) else make_comment(f"{thread_id}c{i}", thread_id=thread_id, body=c, **dated)
            for i, c in enumerate(comments)
        ],
    }
    return Thread.model_validate(make_thread(**{**fields, **overrides}))


def skincare_thread(thread_id: str, title: str, comments=("I love it.",)) -> Thread:
    return Thread.model_validate(make_thread(
        id=thread_id,
        title=title,
        body="",
        url=f"https://www.reddit.com/r/SkincareAddiction/comments/{thread_id}/post/",
        comments=[make_comment(f"{thread_id}c{i}", thread_id=thread_id, body=c) for i, c in enumerate(comments)],
    ))


def thread_with_every_kind_of_comment() -> Thread:
    """A kettle thread holding a deleted, a removed, a link-only and a non-English comment."""
    return kettle_thread("1kettle", comments=[
        make_comment("k1ok", thread_id="1kettle", body="My Dualit kettle is 12 years old and still fine."),
        make_comment("k2del", thread_id="1kettle", body="[deleted]", author=None, status="deleted"),
        make_comment("k3rem", thread_id="1kettle", body="[removed]", status="removed"),
        make_comment("k4link", thread_id="1kettle", body="https://www.example.com/kettle"),
        make_comment("k5it", thread_id="1kettle", body="Il mio bollitore dura da dieci anni."),
    ])


def library_with(tmp_path, *threads: Thread):
    """A library folder already holding these threads."""
    write_gold(tmp_path, [t.model_dump(mode="json") for t in threads], voices=None, mentions=None)
    return tmp_path


def log_lines(folder) -> list[dict]:
    return [json.loads(line) for line in (folder / "requests.jsonl").read_text(encoding="utf-8").splitlines()]


def saved(folder) -> dict[str, Thread]:
    return {t.id: t for t in load_threads(folder / "threads")}


def file_bytes(folder) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in (folder / "threads").iterdir()}


def refuse_to_build(*args, **kwargs):
    raise AssertionError("nothing should be built here: building the real Parse client touches the real cache")


class FakeSource:
    """Stands in for a source with only the shared interface: hands back canned threads exactly as given, recording every request."""

    def __init__(self, threads=(), error=None):
        self.threads = list(threads)
        self.error = error
        self.requests = []  # (query, limit) asked through find_threads

    def find_threads(self, query, limit=3):
        self.requests.append((query, limit))
        return self._answer(limit)

    def _answer(self, limit):
        if self.error:
            raise self.error
        return self.threads[:limit]


class FakeRawSource(FakeSource):
    """A source that can also hand back threads as fetched, like ParseSource. Records which way it was asked."""

    def __init__(self, threads=(), error=None):
        super().__init__(threads, error)
        self.raw_requests = []  # (query, limit) asked through find_raw_threads

    def find_raw_threads(self, query, limit=3):
        self.raw_requests.append((query, limit))
        return self._answer(limit)


def fetch_error(post_id: str) -> str:
    return f"Parse answered 404 to get_post_comments: post {post_id} not found"


class FakeParseClient:
    """Stands in for ParseRedditClient: answers from canned threads and posts, records every call, can fail like Parse."""

    def __init__(self, threads=(), posts=(), fail_on=()):
        self.threads = {t.id: t for t in threads}
        self.posts = list(posts)  # every search answers with these
        self.fail_on = set(fail_on)  # thread ids whose fetch raises ParseAPIError
        self.searches: list[tuple[str, str]] = []
        self.fetches: list[tuple[str, str]] = []

    def search(self, subreddit, query, limit=25, sort="relevance", time_filter="all"):
        self.searches.append((subreddit, query))
        return {"posts": [dict(p) for p in self.posts], "count": len(self.posts), "after": None}

    def get_thread(self, subreddit, post_id, limit=500, sort="top"):
        self.fetches.append((subreddit, post_id))
        if post_id in self.fail_on:
            raise ParseAPIError(fetch_error(post_id))
        return self.threads[post_id]

    def credits_used_this_month(self) -> int:
        return 2 * (len(self.searches) + len(self.fetches))


def post(post_id: str, title: str = "Electric kettle that lasts?", num_comments: int = 40, subreddit: str = "BuyItForLife") -> dict:
    """One search result, shaped like Parse's search_posts answer. Content is made up."""
    return {
        "id": post_id, "title": title, "selftext": "", "score": 25, "num_comments": num_comments,
        "created_utc": 1740819600.0, "permalink": f"/r/{subreddit}/comments/{post_id}/post/", "subreddit": subreddit,
    }


def kettle_posts() -> list[dict]:
    """Search results for a kettle over the request's 3 subreddits: 4 advice, 1 long-term, 2 warnings, 1 of no kind. Made up.

    Best first: 1a1, 1a2, 1a3, 1a4, 1l1, 1w1, 1o1, 1w2.
    """
    return [
        post("1a1", "Best electric kettle?", 300, "BuyItForLife"),
        post("1a2", "Electric kettle recommendations?", 250, "tea"),
        post("1a3", "Which electric kettle should I buy?", 200, "Coffee"),
        post("1a4", "Best gooseneck kettle?", 180, "tea"),
        post("1l1", "Dualit kettle, 12 years later", 90, "Coffee"),
        post("1w1", "My electric kettle died after a year", 60, "BuyItForLife"),
        post("1o1", "My kettle collection", 400, "BuyItForLife"),
        post("1w2", "Kettle regret: the lid broke", 30, "tea"),
    ]


def kettle_client(posts=None, **kwargs) -> "FakeParseClient":
    """A fake Parse client that can fetch every thread of `posts` (default: kettle_posts())."""
    posts = kettle_posts() if posts is None else posts
    return FakeParseClient(threads=[kettle_thread(p["id"], title=p["title"]) for p in posts], posts=posts, **kwargs)


# --- add: filling the library ---

def test_a_clear_request_saves_the_sources_threads_and_logs_the_request(tmp_path):
    source = FakeSource([kettle_thread("1a"), kettle_thread("1b")])
    result = library.add(KETTLE, source, folder=tmp_path)

    assert (result.status, result.product_type, result.thread_ids) == ("ok", "electric kettle", ["1a", "1b"])
    [(query, limit)] = source.requests
    # changed 7 Oct 2026: library mix / refresh cadence approved by Noemi (6 threads per product, was 3).
    assert query == parse_query(KETTLE) and limit == LIBRARY_THREADS_PER_PRODUCT == 6
    assert sorted(p.name for p in (tmp_path / "threads").iterdir()) == ["1a.json", "1b.json"]

    [line] = log_lines(tmp_path)
    assert set(line) == {"at", "request", "status", "product_type", "thread_ids"}
    assert (line["request"], line["status"], line["product_type"], line["thread_ids"]) == (KETTLE, "ok", "electric kettle", ["1a", "1b"])
    assert datetime.fromisoformat(line["at"]).tzinfo is not None


def test_add_asks_the_source_for_at_most_limit_threads(tmp_path):
    source = FakeSource([kettle_thread(f"1k{n}") for n in range(5)])
    assert library.add(KETTLE, source, folder=tmp_path, limit=2).thread_ids == ["1k0", "1k1"]
    assert source.requests[0][1] == 2


@pytest.mark.parametrize("text, status, answer", [
    ("something for my face", "clarify", "question"),
    ("a good laptop", "out_of_scope", "message"),
])
def test_an_unclear_or_out_of_scope_request_fetches_and_saves_no_thread(tmp_path, monkeypatch, text, status, answer):
    source = FakeRawSource([kettle_thread("1a")])
    result = library.add(text, source, folder=tmp_path)

    assert result.status == status
    assert getattr(result, answer) == getattr(parse_query(text), answer)  # the question to ask, or the polite no
    assert result.thread_ids == [] and source.requests == source.raw_requests == []
    assert not (tmp_path / "threads").exists()
    [line] = log_lines(tmp_path)  # still logged, so requests the engine couldn't place can be reviewed
    assert (line["status"], line["thread_ids"]) == (status, [])

    # With no source given, the default Parse source isn't even built, so no credit can be spent.
    monkeypatch.setattr(library, "ParseSource", refuse_to_build)
    assert library.add(text, folder=tmp_path).status == status


def test_add_asks_for_threads_as_fetched_when_the_source_can_give_them(tmp_path):
    raw = FakeRawSource([kettle_thread("1a")])
    library.add(KETTLE, raw, folder=tmp_path, limit=2)
    assert raw.raw_requests == [(parse_query(KETTLE), 2)] and raw.requests == []

    plain = FakeSource([kettle_thread("1a")])  # only the shared interface: that's what is used
    library.add(KETTLE, plain, folder=tmp_path, limit=2)
    assert plain.requests == [(parse_query(KETTLE), 2)]


def test_add_keeps_deleted_and_removed_comments_only_as_stubs_without_text(tmp_path):
    result = library.add(KETTLE, FakeRawSource([thread_with_every_kind_of_comment()]), folder=tmp_path)

    comments = {c.id: c for c in saved(tmp_path)["1kettle"].comments}
    assert list(comments) == ["k1ok", "k2del", "k3rem", "k4link", "k5it"]  # every comment, in its place
    assert (comments["k2del"].status, comments["k2del"].body, comments["k2del"].author) == ("deleted", "[deleted]", None)
    # A removed comment keeps its author on Reddit; the library's stub keeps no author either.
    assert (comments["k3rem"].status, comments["k3rem"].body, comments["k3rem"].author) == ("removed", "[removed]", None)
    # Link-only and non-English comments stay as they were: later modules decide about those.
    assert comments["k4link"].body == "https://www.example.com/kettle"
    assert comments["k5it"].body == "Il mio bollitore dura da dieci anni."
    assert result.threads[0] == saved(tmp_path)["1kettle"]


@pytest.mark.parametrize("status, placeholder", [("deleted", "[deleted]"), ("removed", "[removed]")])
def test_a_stub_that_still_carries_text_is_blanked_before_saving(tmp_path, status, placeholder):
    # We never store text Reddit shows as deleted or removed, even if a source hands some over.
    thread = kettle_thread("1kettle", comments=[
        make_comment("k1", thread_id="1kettle", body="Text the writer took back.", status=status),
    ])
    library.add(KETTLE, FakeRawSource([thread]), folder=tmp_path)

    text = (tmp_path / "threads" / "1kettle.json").read_text(encoding="utf-8")
    assert "Text the writer took back." not in text and "test_user_k1" not in text
    [stub] = saved(tmp_path)["1kettle"].comments
    assert (stub.status, stub.body, stub.author) == (status, placeholder, None)


def test_reply_chains_through_a_deleted_comment_stay_intact(tmp_path):
    # Real threads are full of these. The thread file checks accept only replies to comments in the same
    # file, which the stub keeps there; parent_id is never changed.
    thread = kettle_thread("1kettle", comments=[
        make_comment("k1del", thread_id="1kettle", body="[deleted]", author=None, status="deleted"),
        make_comment("k2reply", thread_id="1kettle", parent_id="k1del", body="Seconding the Dualit, 9 years now."),
        make_comment("k3reply", thread_id="1kettle", parent_id="k2reply", body="Same here."),
    ])
    library.add(KETTLE, FakeRawSource([thread]), folder=tmp_path)

    comments = saved(tmp_path)["1kettle"].comments
    assert [(c.id, c.parent_id) for c in comments] == [("k1del", None), ("k2reply", "k1del"), ("k3reply", "k2reply")]
    assert comments[1].body == "Seconding the Dualit, 9 years now."  # the text itself is untouched


def test_saving_a_thread_again_replaces_the_older_copy(tmp_path):
    library.add(KETTLE, FakeSource([kettle_thread("1a", comments=["An older kettle comment."])]), folder=tmp_path)
    library.add(KETTLE, FakeSource([kettle_thread("1a", comments=["A newer kettle comment."])]), folder=tmp_path)

    assert [c.body for c in saved(tmp_path)["1a"].comments] == ["A newer kettle comment."]
    assert sorted(p.name for p in (tmp_path / "threads").iterdir()) == ["1a.json"]
    assert len(log_lines(tmp_path)) == 2


def test_a_parse_error_is_passed_on_and_nothing_is_saved_or_logged(tmp_path):
    source = FakeSource(error=ParseAPIError(OUT_OF_CREDITS))
    with pytest.raises(ParseAPIError, match="credits"):
        library.add(KETTLE, source, folder=tmp_path)
    assert not (tmp_path / "threads").exists()
    assert not (tmp_path / "requests.jsonl").exists()


def test_with_the_parse_source_add_spends_at_most_16_credits(tmp_path):
    # changed 7 Oct 2026: library mix / refresh cadence approved by Noemi (6 threads, was 3: at most 16 credits, was 10).
    client = kettle_client()
    result = library.add(KETTLE, ParseSource(client=client), folder=tmp_path)

    assert result.thread_ids == ["1a1", "1a2", "1a3", "1l1", "1w1", "1w2"]  # 3 advice, 1 long-term, 2 warnings
    assert client.credits_used_this_month() == 2 * 2 + 2 * 6 == 16  # 2 paid searches and 6 threads


def test_with_the_parse_source_add_saves_threads_as_fetched(tmp_path):
    fetched = thread_with_every_kind_of_comment()
    client = FakeParseClient(threads=[fetched], posts=[post("1kettle")])
    library.add(KETTLE, ParseSource(client=client), folder=tmp_path)
    assert [c.id for c in saved(tmp_path)["1kettle"].comments] == [c.id for c in fetched.comments]


def test_saved_threads_load_back_and_are_found_by_local_source_without_the_stubs(tmp_path):
    threads = [kettle_thread("1a", comments=["A kettle comment."] * 3), kettle_thread("1b"), thread_with_every_kind_of_comment()]
    result = library.add(KETTLE, FakeRawSource(threads), folder=tmp_path)

    assert saved(tmp_path) == {t.id: t for t in result.threads}  # what add returned is exactly what was written
    found = LocalSource(tmp_path / "threads").find_threads(parse_query(KETTLE))
    assert sorted(t.id for t in found) == ["1a", "1b", "1kettle"]
    # Unusable comments are dropped when the library is read.
    assert [c.id for c in next(t for t in found if t.id == "1kettle").comments] == ["k1ok", "k4link", "k5it"]


GOLD_THREADS = DEFAULT_GOLD_DIR / "threads"


@pytest.mark.skipif(not any(GOLD_THREADS.glob("*.json")), reason="no gold-set thread files on this machine")
def test_real_gold_threads_saved_to_the_library_load_back(tmp_path):
    # Real threads have replies to deleted comments: the stubs keep those chains whole, so the files load.
    real = load_threads(GOLD_THREADS)
    library.add(KETTLE, FakeRawSource(real), folder=tmp_path, limit=len(real))
    loaded = saved(tmp_path)
    assert sorted(loaded) == sorted(t.id for t in real)
    for thread in real:
        copy = loaded[thread.id].comments
        assert [(c.id, c.parent_id, c.status) for c in copy] == [(c.id, c.parent_id, c.status) for c in thread.comments]
        assert all(c.body in ("[deleted]", "[removed]") and c.author is None for c in copy if c.status != "ok")


# --- refresh: keeping the library honest ---

def test_refresh_fetches_old_threads_again_and_skips_fresh_ones(tmp_path):
    folder = library_with(tmp_path, kettle_thread("1old", collected_at=OLD), kettle_thread("1new"))
    before = file_bytes(folder)
    client = FakeParseClient(threads=[
        kettle_thread("1old", collected_at=NOW, comments=["My Dualit kettle is 12 years old.", "A new kettle comment."]),
    ])

    result = library.refresh(client, folder, now=NOW)

    assert (result.refreshed, result.skipped, result.failed) == (["1old"], ["1new"], {})
    assert client.fetches == [("BuyItForLife", "1old")]  # the fresh thread cost nothing
    old = saved(folder)["1old"]
    assert old.collected_at == NOW and len(old.comments) == 2
    assert file_bytes(folder)["1new.json"] == before["1new.json"]


def test_refresh_turns_comments_deleted_since_the_last_copy_into_stubs_and_counts_them(tmp_path):
    first = kettle_thread("1old", collected_at=OLD, comments=["Mine lasted 12 years.", "Avoid the cheap ones.", "Dualit, every time.", "Mine broke in a year."])
    second = kettle_thread("2old", collected_at=OLD, comments=[
        "Fellow Stagg, 5 years.",
        "Same kettle here.",
        make_comment("2oldc2", thread_id="2old", body="[deleted]", author=None, status="deleted"),  # already a stub last time
    ])
    # Since then, on Reddit: in the first thread one comment was deleted, one removed (Parse still shows
    # its author) and one vanished altogether, and a new one arrived; in the second, one more was deleted.
    client = FakeParseClient(threads=[
        kettle_thread("1old", collected_at=NOW, comments=[
            make_comment("1oldc0", thread_id="1old", body="[deleted]", author=None, status="deleted"),
            make_comment("1oldc1", thread_id="1old", body="[removed]", status="removed"),
            make_comment("1oldc2", thread_id="1old", body="Dualit, every time."),
            make_comment("1oldc9", thread_id="1old", body="Just bought one."),
        ]),
        kettle_thread("2old", collected_at=NOW, comments=[
            make_comment("2oldc0", thread_id="2old", body="Fellow Stagg, 5 years."),
            make_comment("2oldc1", thread_id="2old", body="[deleted]", author=None, status="deleted"),
            make_comment("2oldc2", thread_id="2old", body="[deleted]", author=None, status="deleted"),
        ]),
    ])
    folder = library_with(tmp_path, first, second)

    result = library.refresh(client, folder, now=NOW)

    # Usable in the old copy, now a stub or missing: 3 in the first thread, 1 in the second. The old stub doesn't count.
    assert result.dropped_comments == 3 + 1
    comments = saved(folder)["1old"].comments
    assert [(c.id, c.status) for c in comments] == [("1oldc0", "deleted"), ("1oldc1", "removed"), ("1oldc2", "ok"), ("1oldc9", "ok")]
    assert comments[1].author is None
    text = (folder / "threads" / "1old.json").read_text(encoding="utf-8")
    assert "Mine lasted 12 years." not in text and "Avoid the cheap ones." not in text and "Mine broke in a year." not in text


# changed 7 Oct 2026: library mix / refresh cadence approved by Noemi. One `max_age_days` became two waits: 30 days
# (LIBRARY_REFRESH_DAYS), or 90 (LIBRARY_ARCHIVED_REFRESH_DAYS) for a thread posted more than 180 days
# (REDDIT_ARCHIVE_DAYS) before the refresh, which Reddit has archived: only deletions can still change it.
@pytest.mark.parametrize("posted, saved, due", [
    (timedelta(days=100), timedelta(days=LIBRARY_REFRESH_DAYS - 1), False),
    (timedelta(days=100), timedelta(days=LIBRARY_REFRESH_DAYS), False),  # "older than 30 days" means more than 30
    (timedelta(days=100), timedelta(days=LIBRARY_REFRESH_DAYS, minutes=1), True),
    (timedelta(days=400), timedelta(days=LIBRARY_REFRESH_DAYS, minutes=1), False),  # archived: 90 days
    (timedelta(days=400), timedelta(days=LIBRARY_ARCHIVED_REFRESH_DAYS), False),
    (timedelta(days=400), timedelta(days=LIBRARY_ARCHIVED_REFRESH_DAYS, minutes=1), True),
    # Archived means posted more than 180 days before the refresh.
    (timedelta(days=REDDIT_ARCHIVE_DAYS), timedelta(days=LIBRARY_REFRESH_DAYS, minutes=1), True),
    (timedelta(days=REDDIT_ARCHIVE_DAYS, minutes=1), timedelta(days=LIBRARY_REFRESH_DAYS, minutes=1), False),
])
def test_a_thread_is_due_30_days_after_saving_or_90_once_reddit_has_archived_it(tmp_path, posted, saved, due):
    folder = library_with(tmp_path, kettle_thread("1a", created_at=NOW - posted, collected_at=NOW - saved))
    client = FakeParseClient(threads=[kettle_thread("1a", collected_at=NOW)])

    result = library.refresh(client, folder, now=NOW)

    assert (result.refreshed, result.skipped) == ((["1a"], []) if due else ([], ["1a"]))
    assert len(client.fetches) == (1 if due else 0)


def test_saved_the_same_day_a_live_thread_is_refreshed_and_an_archived_one_waits(tmp_path):
    saved_at = NOW - timedelta(days=60)
    folder = library_with(
        tmp_path,
        kettle_thread("1live", created_at=NOW - timedelta(days=70), collected_at=saved_at),
        kettle_thread("1archived", created_at=NOW - timedelta(days=3 * 365), collected_at=saved_at),
    )
    client = FakeParseClient(threads=[kettle_thread("1live", collected_at=NOW)])

    result = library.refresh(client, folder, now=NOW)

    assert (result.refreshed, result.skipped) == (["1live"], ["1archived"])
    assert client.fetches == [("BuyItForLife", "1live")]  # the archived thread cost nothing


def test_a_thread_that_cant_be_fetched_is_reported_and_the_refresh_goes_on(tmp_path):
    # Named so that alphabetical order differs from age order: the oldest thread goes first.
    # changed 7 Oct 2026: library mix / refresh cadence approved by Noemi (dates moved 1 month back: all over 90 days).
    folder = library_with(
        tmp_path,
        kettle_thread("1c", collected_at="2026-05-01"),
        kettle_thread("1a", collected_at="2026-06-01"),
        kettle_thread("1b", collected_at="2026-07-01"),
        kettle_thread("1z", collected_at=RECENT),
    )
    before = file_bytes(folder)
    client = FakeParseClient(threads=[kettle_thread(i, collected_at=NOW) for i in ("1a", "1b", "1c")], fail_on=["1a"])

    result = library.refresh(client, folder, now=NOW)

    assert [post_id for _, post_id in client.fetches] == ["1c", "1a", "1b"]  # oldest first; one failure doesn't block the rest
    assert (result.refreshed, result.skipped) == (["1c", "1b"], ["1z"])
    assert result.failed == {"1a": fetch_error("1a")}
    assert (result.stopped, result.not_tried) == (False, [])
    after = file_bytes(folder)
    assert sorted(after) == sorted(before)  # nothing deleted, nothing left half-written
    assert after["1a.json"] == before["1a.json"] and after["1z.json"] == before["1z.json"]
    assert after["1b.json"] != before["1b.json"] and after["1c.json"] != before["1c.json"]


@pytest.mark.parametrize("fails, tried, stopped", [
    ("ok fail fail fail ok ok", 4, True),  # 3 in a row: Parse is down, the key is wrong or the credits are gone
    ("fail fail ok fail fail ok", 6, False),  # never 3 in a row: everything is tried
    ("fail fail fail", 3, True),
])
def test_three_failures_in_a_row_stop_the_refresh(tmp_path, fails, tried, stopped):
    outcomes = fails.split()
    ids = [f"1t{n}" for n in range(len(outcomes))]
    # Collected one day apart, oldest first, so the fetch order is the order above.
    # changed 7 Oct 2026: library mix / refresh cadence approved by Noemi (120 days, was 90: due for archived threads).
    folder = library_with(tmp_path, *(kettle_thread(i, collected_at=NOW - timedelta(days=120 - n)) for n, i in enumerate(ids)))
    before = file_bytes(folder)
    client = FakeParseClient(
        threads=[kettle_thread(i, collected_at=NOW) for i in ids],
        fail_on=[i for i, outcome in zip(ids, outcomes) if outcome == "fail"],
    )

    result = library.refresh(client, folder, now=NOW)

    assert [post_id for _, post_id in client.fetches] == ids[:tried]
    assert result.stopped is stopped
    assert result.not_tried == ids[tried:]
    assert sorted(result.failed) == [i for i, outcome in zip(ids[:tried], outcomes) if outcome == "fail"]
    assert result.refreshed == [i for i, outcome in zip(ids[:tried], outcomes) if outcome == "ok"]
    after = file_bytes(folder)
    assert sorted(after) == sorted(before)
    assert all(after[f"{i}.json"] == before[f"{i}.json"] for i in [*result.failed, *result.not_tried])


def test_a_thread_whose_post_was_deleted_is_kept_and_reported(tmp_path):
    folder = library_with(tmp_path, kettle_thread("1old", collected_at=OLD, body="Which kettle lasts?"))
    gone = kettle_thread("1old", collected_at=NOW, body="[deleted]", author=None)

    result = library.refresh(FakeParseClient(threads=[gone]), folder, now=NOW)

    assert result.posts_gone == ["1old"]
    assert saved(folder)["1old"].body == "[deleted]"  # the deleted post text is no longer stored, but the thread stays


def test_refresh_with_nothing_due_builds_no_client_and_spends_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "ParseRedditClient", refuse_to_build)
    folder = library_with(tmp_path, kettle_thread("1new"))
    result = library.refresh(folder=folder, now=NOW)
    assert (result.refreshed, result.skipped, result.dropped_comments, result.failed) == ([], ["1new"], 0, {})

    empty = library.refresh(folder=tmp_path / "missing", now=NOW)  # a library not created yet
    assert (empty.refreshed, empty.skipped) == ([], [])


# --- coverage: what the library can answer ---

def test_coverage_counts_saved_threads_per_product_type(tmp_path):
    folder = library_with(
        tmp_path,
        kettle_thread("1k1"),
        kettle_thread("1k2", title="Kitchen gear that lasts?", comments=["A gooseneck kettle from Fellow."]),  # only a comment names it
        kettle_thread("1knife", title="Best chef's knife under £100?", comments=["Get a Victorinox."]),
        skincare_thread("1exf", "Gentle exfoliant?"),
        skincare_thread("1water", "Does kettle limescale water hurt my skin?"),  # a kettle, but in skincare: not counted
    )

    counts = library.coverage(folder)

    assert list(counts) == [p.name for p in PRODUCT_TYPES]  # every product type, in module 1's order
    assert {name: n for name, n in counts.items() if n} == {"electric kettle": 2, "chef knife": 1, "exfoliant": 1}


def test_coverage_of_an_empty_library_is_zero_everywhere(tmp_path):
    counts = library.coverage(tmp_path / "missing")
    assert list(counts) == [p.name for p in PRODUCT_TYPES]
    assert set(counts.values()) == {0}


# --- The command line ---

def test_command_line_add_saves_and_prints_the_credits(tmp_path, capsys):
    threads = [kettle_thread(f"1p{n}") for n in range(3)]
    # changed 7 Oct 2026: library mix / refresh cadence approved by Noemi. At most 2 threads per subreddit now,
    # so the 3 threads come from the request's 3 subreddits.
    subreddits = ("BuyItForLife", "tea", "Coffee")
    client = FakeParseClient(threads=threads, posts=[post(t.id, subreddit=s) for t, s in zip(threads, subreddits)])

    # changed 9 Oct 2026: the archive became add's default reader (Noemi's decision of 9 Oct 2026); this test is
    # about reading through Parse, so it asks for --reader parse.
    assert library.main(["add", "--reader", "parse", *KETTLE.split()], client=client, folder=tmp_path) == 0  # quotes are optional

    out = capsys.readouterr().out
    assert "Saved 3 threads for electric kettle" in out
    assert all(f"{t.id}.json" in out for t in threads)
    assert out.rstrip().endswith("Parse credits used this month: 10 of 200 (the parse.bot dashboard has the exact figure)")
    assert log_lines(tmp_path)[0]["request"] == KETTLE


@pytest.mark.parametrize("text", ["something for my face", "a good laptop"])
def test_command_line_add_prints_the_question_or_the_polite_no(tmp_path, capsys, text):
    client = FakeParseClient()
    assert library.main(["add", text], client=client, folder=tmp_path) == 0
    out = capsys.readouterr().out
    query = parse_query(text)
    assert (query.question or query.message) in out
    assert "Parse credits used this month: 0 of 200" in out
    assert client.searches == client.fetches == []


def test_command_line_add_reports_a_parse_error(tmp_path, capsys):
    client = FakeParseClient(posts=[post("1a")], fail_on=["1a"])
    # changed 9 Oct 2026: the archive became add's default reader (Noemi's decision of 9 Oct 2026); this test is
    # about reading through Parse, so it asks for --reader parse.
    assert library.main(["add", "--reader", "parse", KETTLE], client=client, folder=tmp_path) == 1
    out = capsys.readouterr().out
    assert fetch_error("1a") in out and "Parse credits used this month" in out


def test_command_line_refresh(tmp_path, capsys):
    now = datetime.now(UTC)  # the command line uses the real clock
    # changed 7 Oct 2026: library mix / refresh cadence approved by Noemi (100 days, was 60: due for archived threads).
    folder = library_with(
        tmp_path,
        kettle_thread("1old", collected_at=now - timedelta(days=100), comments=["Kettle one.", "Kettle two."]),
        kettle_thread("1new", collected_at=now - timedelta(days=1)),
    )
    client = FakeParseClient(threads=[kettle_thread("1old", collected_at=now, comments=["Kettle one."])])

    assert library.main(["refresh"], client=client, folder=folder) == 0

    out = capsys.readouterr().out
    assert "Refreshed 1 thread(s): 1old" in out
    assert "Skipped 1 thread(s)" in out
    assert "Comments dropped since the last copies: 1" in out
    assert "Failures: none" in out
    assert out.rstrip().endswith("Parse credits used this month: 2 of 200 (the parse.bot dashboard has the exact figure)")


def test_command_line_refresh_reports_each_failure(tmp_path, capsys):
    now = datetime.now(UTC)
    # changed 7 Oct 2026: library mix / refresh cadence approved by Noemi (101 and 100 days, were 61 and 60).
    folder = library_with(
        tmp_path,
        kettle_thread("1bad", collected_at=now - timedelta(days=101)),
        kettle_thread("1good", collected_at=now - timedelta(days=100)),
    )
    client = FakeParseClient(threads=[kettle_thread("1good", collected_at=now)], fail_on=["1bad"])

    assert library.main(["refresh"], client=client, folder=folder) == 1

    out = capsys.readouterr().out
    assert "Refreshed 1 thread(s): 1good" in out
    assert "Failed, saved copies unchanged:" in out and f"1bad: {fetch_error('1bad')}" in out
    assert "Stopped" not in out


def test_command_line_refresh_reports_where_it_stopped(tmp_path, capsys):
    now = datetime.now(UTC)
    ids = ["1t0", "1t1", "1t2", "1t3"]
    # changed 7 Oct 2026: library mix / refresh cadence approved by Noemi (120 days, was 90: due for archived threads).
    folder = library_with(tmp_path, *(kettle_thread(i, collected_at=now - timedelta(days=120 - n)) for n, i in enumerate(ids)))

    assert library.main(["refresh"], client=FakeParseClient(fail_on=ids), folder=folder) == 1

    out = capsys.readouterr().out
    assert "Stopped after 3 failures in a row" in out
    assert "Not tried this time, saved copies unchanged: 1t3" in out


def test_command_line_coverage(tmp_path, capsys):
    folder = library_with(tmp_path, kettle_thread("1k1"))
    assert library.main(["coverage"], client=FakeParseClient(), folder=folder) == 0
    out = capsys.readouterr().out
    assert re.search(r"electric kettle\s+1\n", out) and re.search(r"sunscreen\s+0\n", out)
    assert "Parse credits used this month: 0 of 200" in out


@pytest.mark.parametrize("argv", [[], ["add"], ["fetch"]])
def test_command_line_explains_itself_when_used_wrongly(tmp_path, capsys, argv):
    client = FakeParseClient()
    assert library.main(argv, client=client, folder=tmp_path) == 2
    assert "python -m engine.library add" in capsys.readouterr().out
    assert not (tmp_path / "requests.jsonl").exists()


def test_command_line_add_finds_threads_for_free_when_given_a_finder(tmp_path, capsys):
    from engine.tests.test_sources import FakeFinder

    threads = [kettle_thread(f"1p{n}") for n in range(3)]
    client = FakeParseClient(threads=threads)
    # changed 7 Oct 2026: library mix / refresh cadence approved by Noemi. At most 2 threads per subreddit now,
    # so the 3 threads come from the request's 3 subreddits.
    finder = FakeFinder([post(t.id, subreddit=s) for t, s in zip(threads, ("BuyItForLife", "tea", "Coffee"))])
    # changed 9 Oct 2026: the archive became add's default reader (Noemi's decision of 9 Oct 2026); this test is
    # about reading through Parse, so it asks for --reader parse.
    assert library.main(["add", "--reader", "parse", KETTLE], client=client, folder=tmp_path, finder=finder) == 0
    assert client.searches == [] and len(client.fetches) == 3
    assert "Parse credits used this month: 6 of 200" in capsys.readouterr().out


# --- add: a mix of thread kinds per product type (Noemi, 7 Oct 2026) ---
# Advice threads give the picks, long-term-use threads the strongest evidence, warning threads the "skip these"
# list and the downsides.

class FakeMixSource(FakeRawSource):
    """A source that can also pick a mix of thread kinds, like ParseSource. Records what it was asked for."""

    def __init__(self, threads=(), error=None):
        super().__init__(threads, error)
        self.mix_requests = []  # (limit, mix, fill)

    def find_raw_threads(self, query, limit=3, mix=None, fill=True):
        self.mix_requests.append((limit, mix, fill))
        return self._answer(limit)


def test_add_asks_a_source_that_can_pick_a_mix_for_six_threads_in_the_librarys_mix(tmp_path):
    source = FakeMixSource([kettle_thread("1a")])
    library.add(KETTLE, source, folder=tmp_path)
    assert source.mix_requests == [(6, LIBRARY_MIX, True)]
    assert LIBRARY_MIX == {"advice": 3, "long_term": 1, "warning": 2}


def test_add_with_only_asks_for_that_kind_alone_and_no_others_in_its_place(tmp_path):
    source = FakeMixSource([kettle_thread("1w", title="My kettle died")])
    library.add(KETTLE, source, folder=tmp_path, only="warning", limit=1)
    library.add(KETTLE, source, folder=tmp_path, only="long_term")
    assert source.mix_requests == [(1, {"warning": 1}, False), (6, {"long_term": 6}, False)]


def test_add_without_a_mix_asks_for_the_best_threads(tmp_path):
    source = FakeMixSource([kettle_thread("1a")])
    library.add(KETTLE, source, folder=tmp_path, mix=None, limit=4)
    assert source.mix_requests == [(4, None, True)]


def test_with_a_source_that_cant_pick_a_mix_only_keeps_threads_of_that_kind(tmp_path):
    source = FakeSource([
        kettle_thread("1adv", title="Best electric kettle?"),
        kettle_thread("1warn", title="My kettle died after a year"),
    ])
    result = library.add(KETTLE, source, folder=tmp_path, only="warning")
    assert source.requests == [(parse_query(KETTLE), 6)]  # asked plainly
    assert result.thread_ids == ["1warn"] and sorted(saved(tmp_path)) == ["1warn"]


@pytest.mark.parametrize("only", ["pros", "warnings", ""])
def test_add_refuses_an_unknown_kind_before_doing_anything(tmp_path, only):
    source = FakeMixSource([kettle_thread("1a")])
    with pytest.raises(ValueError, match="advice, long_term, warning"):
        library.add(KETTLE, source, folder=tmp_path, only=only)
    assert source.mix_requests == [] and not (tmp_path / "requests.jsonl").exists()


def test_a_full_add_with_arctic_shift_costs_12_credits(tmp_path):
    from engine.tests.test_sources import FakeFinder

    client = kettle_client()
    result = library.add(KETTLE, ParseSource(client=client, finder=FakeFinder(kettle_posts())), folder=tmp_path)

    assert result.thread_ids == ["1a1", "1a2", "1a3", "1l1", "1w1", "1w2"]  # 3 advice, 1 long-term, 2 warnings
    assert client.searches == []  # found for free
    assert client.credits_used_this_month() == 2 * 6 == 12  # only the 6 threads read


@pytest.mark.parametrize("only, limit, expected", [
    ("warning", 1, ["1w1"]),
    ("warning", 6, ["1w1", "1w2"]),  # only 2 warnings exist: no other threads in their place
    ("long_term", 1, ["1l1"]),
    ("advice", 2, ["1a1", "1a2"]),
])
def test_add_only_one_kind_with_arctic_shift_costs_2_credits_per_thread(tmp_path, only, limit, expected):
    from engine.tests.test_sources import FakeFinder

    client = kettle_client()
    result = library.add(KETTLE, ParseSource(client=client, finder=FakeFinder(kettle_posts())), folder=tmp_path, only=only, limit=limit)

    assert result.thread_ids == expected and sorted(saved(tmp_path)) == sorted(expected)
    assert client.credits_used_this_month() == 2 * len(expected)


def test_add_only_warnings_when_there_are_none_fetches_and_saves_nothing(tmp_path):
    from engine.tests.test_sources import FakeFinder

    no_warnings = [p for p in kettle_posts() if p["id"] not in ("1w1", "1w2")]
    client = kettle_client(no_warnings)
    result = library.add(KETTLE, ParseSource(client=client, finder=FakeFinder(no_warnings)), folder=tmp_path, only="warning")

    assert (result.status, result.thread_ids) == ("ok", [])
    assert client.fetches == [] and client.credits_used_this_month() == 0
    assert not (tmp_path / "threads").exists()
    [line] = log_lines(tmp_path)  # still logged, like any request
    assert line["thread_ids"] == []


# --- coverage: what kinds of threads each product type has ---

def test_coverage_by_kind_counts_advice_long_term_and_warning_threads_per_product_type(tmp_path):
    folder = library_with(
        tmp_path,
        kettle_thread("1adv", title="Best electric kettle?"),
        kettle_thread("1adv2", title="Which kettle should I buy?"),
        kettle_thread("1long", title="Dualit kettle, 12 years later"),
        kettle_thread("1warn", title="My kettle died after a year"),
        kettle_thread("1other", title="My kettle collection"),  # counted in coverage, but of no kind
        kettle_thread("1knife", title="Best chef's knife under £100?", comments=["Get a Victorinox."]),
        skincare_thread("1burn", "This exfoliant burned my skin"),
        skincare_thread("1water", "Kettle water burned my skin?"),  # names a kettle, but in skincare: not a kettle thread
    )

    kinds = library.coverage_by_kind(folder)

    assert list(kinds) == [p.name for p in PRODUCT_TYPES]  # every product type, in module 1's order
    assert kinds["electric kettle"] == {"advice": 2, "long_term": 1, "warning": 1}
    assert kinds["chef knife"] == {"advice": 1, "long_term": 0, "warning": 0}
    assert kinds["exfoliant"] == {"advice": 0, "long_term": 0, "warning": 1}
    assert kinds["sunscreen"] == {"advice": 0, "long_term": 0, "warning": 0}
    assert library.coverage(folder)["electric kettle"] == 5


def test_coverage_by_kind_of_an_empty_library_is_zero_everywhere(tmp_path):
    kinds = library.coverage_by_kind(tmp_path / "missing")
    assert list(kinds) == [p.name for p in PRODUCT_TYPES]
    assert all(counts == {"advice": 0, "long_term": 0, "warning": 0} for counts in kinds.values())


def test_command_line_coverage_prints_the_kinds_against_the_mix(tmp_path, capsys):
    folder = library_with(
        tmp_path,
        kettle_thread("1adv", title="Best electric kettle?"),
        kettle_thread("1adv2", title="Which kettle should I buy?"),
        kettle_thread("1warn", title="My kettle died after a year"),
    )
    assert library.main(["coverage"], client=FakeParseClient(), folder=folder) == 0
    out = capsys.readouterr().out
    assert re.search(r"electric kettle\s+3\n", out)
    assert re.search(r"electric kettle\s+advice 2/3, long-term use 0/1, warning 1/2\n", out)
    assert not re.search(r"sunscreen\s+advice", out)  # only product types with saved threads


# --- The command line: add --only and --limit ---

def test_command_line_add_only_one_warning_thread_costs_2_credits(tmp_path, capsys):
    from engine.tests.test_sources import FakeFinder

    client = kettle_client()
    # changed 9 Oct 2026: the archive became add's default reader (Noemi's decision of 9 Oct 2026); this test is
    # about reading through Parse, so it asks for --reader parse.
    argv = ["add", "--reader", "parse", "--only", "warning", "--limit", "1", *KETTLE.split()]  # quotes still optional
    assert library.main(argv, client=client, folder=tmp_path, finder=FakeFinder(kettle_posts())) == 0

    out = capsys.readouterr().out
    assert "Saved 1 warning thread for electric kettle" in out and "1w1.json" in out
    assert out.rstrip().endswith("Parse credits used this month: 2 of 200 (the parse.bot dashboard has the exact figure)")
    assert log_lines(tmp_path)[0]["request"] == KETTLE


def test_command_line_add_options_can_follow_the_request_and_use_an_equals_sign(tmp_path, capsys):
    from engine.tests.test_sources import FakeFinder

    client = kettle_client()
    # changed 9 Oct 2026: the archive became add's default reader (Noemi's decision of 9 Oct 2026); this test is
    # about reading through Parse, so it asks for --reader parse.
    argv = ["add", KETTLE, "--limit=2", "--only=advice", "--reader=parse"]
    assert library.main(argv, client=client, folder=tmp_path, finder=FakeFinder(kettle_posts())) == 0
    assert "Saved 2 advice threads for electric kettle" in capsys.readouterr().out
    assert sorted(saved(tmp_path)) == ["1a1", "1a2"]


def test_command_line_add_says_when_no_thread_of_that_kind_was_found(tmp_path, capsys):
    from engine.tests.test_sources import FakeFinder

    no_warnings = [p for p in kettle_posts() if p["id"] not in ("1w1", "1w2")]
    client = kettle_client(no_warnings)
    assert library.main(["add", "--only", "warning", KETTLE], client=client, folder=tmp_path, finder=FakeFinder(no_warnings)) == 0
    out = capsys.readouterr().out
    assert "No warning threads found for electric kettle; nothing saved." in out
    assert "Parse credits used this month: 0 of 200" in out


@pytest.mark.parametrize("argv", [
    ["add", "--only", "pros", KETTLE],
    ["add", "--only", KETTLE],  # the request isn't a kind
    ["add", "--limit", "0", KETTLE],
    ["add", "--limit", "two", KETTLE],
    ["add", "--limit=", KETTLE],
    ["add", "--limit", "2"],  # no request
    ["add", KETTLE, "--only"],  # no kind
    ["add", "--fast", KETTLE],
])
def test_command_line_add_explains_itself_when_its_options_are_wrong(tmp_path, capsys, argv):
    client = FakeParseClient()
    assert library.main(argv, client=client, folder=tmp_path) == 2
    assert "--only warning|advice|long_term" in capsys.readouterr().out
    assert not (tmp_path / "requests.jsonl").exists() and client.searches == client.fetches == []
