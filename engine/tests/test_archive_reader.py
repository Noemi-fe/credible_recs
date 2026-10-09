"""Reading threads from Arctic Shift's archive (Noemi, 9 Oct 2026), and where each thread was read.

Threads may now be read from the archive for free, but an archive keeps comments people later deleted on Reddit,
so every thread records where it was read (read_from) and when Reddit itself was last read for it (checked_live_at).
Every test uses a fake service and made-up data: no network.
"""

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from pydantic import ValidationError

from engine import library
from engine.arctic_shift import COLLAPSED_BATCH, MAX_COLLAPSED, ArcticShiftClient, ArcticShiftError
from engine.gold import load_threads
from engine.models import Thread
from engine.query import parse_query
from engine.sources import ArchiveSource, ParseSource, Source, choose_mix
from engine.tests.factories import make_thread
from engine.tests.test_arctic_shift import FakeClock
from engine.tests.test_parse_reddit import FakeService as FakeParseService
from engine.tests.test_parse_reddit import make_client as make_parse_client

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
POSTED = 1740819600  # 1 March 2025, 09:00 UTC
KETTLE = "electric kettle that lasts 10+ years"  # kitchen; searches BuyItForLife, tea, Coffee


# --- A made-up archive ---

def archive_post(post_id="1arch01", subreddit="BuyItForLife", **overrides) -> dict:
    """A post as Arctic Shift's posts/ids answers it, with fields we don't keep too. All content is made up."""
    post = {
        "id": post_id, "title": "Electric kettle that lasts?", "selftext": "Mine died again.", "author": "test_op",
        "created_utc": POSTED, "score": 150, "num_comments": 7, "subreddit": subreddit,
        "permalink": f"/r/{subreddit}/comments/{post_id}/electric_kettle_that_lasts/", "link_flair_text": None,
        "author_flair_text": "Not kept", "url": "https://example.com/not-kept", "upvote_ratio": 0.97,
    }
    post.update(overrides)
    return post


def raw_comment(cid, parent, body="A readable comment.", author="test_user", post_id="1arch01", subreddit="BuyItForLife"):
    """A comment as the archive answers it: Reddit's own field names, parent ids with their t1_/t3_ prefix."""
    return {
        "id": cid, "parent_id": parent, "link_id": f"t3_{post_id}", "author": author, "body": body,
        "created_utc": POSTED + 3600, "score": 12, "permalink": f"/r/{subreddit}/comments/{post_id}/x/{cid}/",
        "author_flair_text": None, "subreddit": subreddit,
    }


def node(comment: dict, replies=()) -> dict:
    """One comment in the tree, Reddit style: {"kind": "t1", "data": {..., "replies": a listing or ""}}."""
    data = dict(comment)
    data["replies"] = {"kind": "Listing", "data": {"children": list(replies)}} if replies else ""
    return {"kind": "t1", "data": data}


def more(*ids, flat=False) -> dict:
    """Collapsed comments: their ids only. Accepted in both shapes, with or without a "data" wrapper."""
    return {"kind": "more", "children": list(ids)} if flat else {"kind": "more", "data": {"count": len(ids), "children": list(ids)}}


def tree() -> list:
    """c1 (with a reply c2, which has a reply c3), a deleted c4, a removed c5, c6 by a deleted account, and two
    collapsed comments: c7 (a reply to c1) and c8 (a reply to c7)."""
    return [
        node(raw_comment("c1", "t3_1arch01", body="My Zojirushi kettle has lasted 6 years."), [
            node(raw_comment("c2", "t1_c1", body="Same, 4 years for mine."), [
                node(raw_comment("c3", "t1_c2", body="Good to know."))]),
            more("c7", flat=True),
        ]),
        node(raw_comment("c4", "t3_1arch01", body="[deleted]", author="[deleted]")),
        node(raw_comment("c5", "t3_1arch01", body="[removed]", author="someone")),
        node(raw_comment("c6", "t3_1arch01", body="Still readable; only the account is gone.", author="[deleted]")),
        more("t1_c8"),
    ]


COLLAPSED = {
    "c7": raw_comment("c7", "t1_c1", body="Dualit for 12 years here."),
    "c8": raw_comment("c8", "t1_c7", body="Which Dualit model?"),
}


class FakeArchive:
    """Stands in for the network: answers posts/ids, comments/tree and comments/ids from made-up data."""

    def __init__(self, posts=None, trees=None, collapsed=None, busy_first=False, status=200):
        self.posts = posts if posts is not None else {"1arch01": archive_post()}
        self.trees = trees if trees is not None else {"1arch01": tree()}
        self.collapsed = collapsed if collapsed is not None else dict(COLLAPSED)
        self.busy_first = busy_first
        self.status = status
        self.requests = []

    def __call__(self, url, headers):
        self.requests.append((url, headers))
        if self.busy_first and len(self.requests) == 1:
            return 422, json.dumps({"data": None, "error": "Timeout. Maybe slow down a bit"}).encode()
        if self.status != 200:
            return self.status, json.dumps({"error": "server error"}).encode()
        path, query = urlparse(url).path, parse_qs(urlparse(url).query)
        if path.endswith("/posts/ids"):
            data = [self.posts[i] for i in query["ids"][0].split(",") if i in self.posts]
        elif path.endswith("/comments/tree"):
            data = self.trees.get(query["link_id"][0].removeprefix("t3_"), [])
        elif path.endswith("/comments/ids"):
            data = [self.collapsed[i.removeprefix("t1_")] for i in query["ids"][0].split(",") if i.removeprefix("t1_") in self.collapsed]
        else:
            return 404, b"{}"
        return 200, json.dumps({"data": data}).encode()

    def paths(self) -> list[str]:
        return [urlparse(url).path.rsplit("/api/", 1)[1] for url, _ in self.requests]


def make_archive(tmp_path, service=None, clock=None) -> ArcticShiftClient:
    clock = clock or FakeClock()
    clock.now = max(clock.now, NOW)
    return ArcticShiftClient(cache_dir=tmp_path / "cache", fetch=service or FakeArchive(), clock=clock, sleep=clock.sleep)


# --- ArcticShiftClient.get_thread: one thread from the archive, in our Thread shape ---

def test_an_archive_thread_is_mapped_into_our_shape(tmp_path):
    clock = FakeClock()
    thread = make_archive(tmp_path, clock=clock).get_thread("1arch01")
    assert (thread.id, thread.community, thread.category, thread.source) == ("1arch01", "BuyItForLife", "kitchen", "reddit")
    assert (thread.title, thread.body, thread.author.name) == ("Electric kettle that lasts?", "Mine died again.", "test_op")
    assert thread.url == "https://www.reddit.com/r/BuyItForLife/comments/1arch01/electric_kettle_that_lasts/"
    assert thread.created_at == datetime(2025, 3, 1, 9, 0, tzinfo=UTC)
    assert (thread.score, thread.num_comments) == (150, 7)
    assert thread.collected_at == clock.now == NOW + timedelta(seconds=20)  # when the last of its 3 answers came


def test_an_archive_thread_is_marked_as_read_from_the_archive_never_checked_live(tmp_path):
    thread = make_archive(tmp_path).get_thread("1arch01")
    assert thread.read_from == "arctic_shift"
    assert thread.checked_live_at is None and thread.last_checked_live() is None


def test_the_tree_is_flattened_with_each_reply_pointing_to_its_parent(tmp_path):
    comments = {c.id: c for c in make_archive(tmp_path).get_thread("1arch01").comments}
    assert list(comments)[:6] == ["c1", "c2", "c3", "c4", "c5", "c6"]  # thread order: each comment, then its replies
    assert comments["c1"].parent_id is None  # a reply to the post
    assert (comments["c2"].parent_id, comments["c3"].parent_id) == ("c1", "c2")  # t1_ prefixes stripped
    assert comments["c1"].body == "My Zojirushi kettle has lasted 6 years."
    assert comments["c2"].url == "https://www.reddit.com/r/BuyItForLife/comments/1arch01/x/c2/"


def test_deleted_and_removed_comments_are_marked_as_parse_marks_them(tmp_path):
    comments = {c.id: c for c in make_archive(tmp_path).get_thread("1arch01").comments}
    assert (comments["c4"].status, comments["c4"].author) == ("deleted", None)
    assert comments["c5"].status == "removed"
    assert (comments["c6"].status, comments["c6"].author) == ("ok", None)  # only the account is gone


def test_collapsed_comments_are_fetched_by_id_in_either_shape(tmp_path):
    service = FakeArchive()
    comments = {c.id: c for c in make_archive(tmp_path, service).get_thread("1arch01").comments}
    assert (comments["c7"].parent_id, comments["c8"].parent_id) == ("c1", "c7")
    assert comments["c7"].body == "Dualit for 12 years here."
    assert service.paths() == ["posts/ids", "comments/tree", "comments/ids"]  # both collapsed comments in one call
    asked = parse_qs(urlparse(service.requests[2][0]).query)["ids"][0].split(",")
    assert sorted(asked) == ["c7", "c8"]


def test_requests_are_polite_and_well_formed(tmp_path):
    service, clock = FakeArchive(), FakeClock()
    make_archive(tmp_path, service, clock).get_thread("t3_1arch01")  # a t3_ prefix is fine too
    post_url, tree_url = service.requests[0][0], service.requests[1][0]
    assert post_url.startswith("https://arctic-shift.photon-reddit.com/api/posts/ids?")
    assert parse_qs(urlparse(post_url).query)["ids"] == ["1arch01"]
    assert tree_url.startswith("https://arctic-shift.photon-reddit.com/api/comments/tree?")
    assert parse_qs(urlparse(tree_url).query) == {
        "link_id": ["t3_1arch01"], "limit": ["9999"], "start_breadth": ["9999"], "start_depth": ["9999"],
    }
    assert all("credible-recs" in headers["User-Agent"] for _, headers in service.requests)
    assert clock.slept == [10.0, 10.0]  # three calls, 10 seconds apart


def test_collapsed_comments_are_asked_500_at_a_time_and_at_most_1000(tmp_path):
    ids = [f"m{n:04d}" for n in range(1200)]
    collapsed = {cid: raw_comment(cid, "t3_1arch01", body=f"Comment {cid}.") for cid in ids}
    service = FakeArchive(trees={"1arch01": [node(raw_comment("c1", "t3_1arch01")), more(*ids)]}, collapsed=collapsed)
    thread = make_archive(tmp_path, service).get_thread("1arch01")
    batches = [len(parse_qs(urlparse(url).query)["ids"][0].split(",")) for url, _ in service.requests[2:]]
    assert (COLLAPSED_BATCH, MAX_COLLAPSED) == (500, 1000)
    assert batches == [500, 500]
    assert len(thread.comments) == 1 + 1000  # the 200 beyond the cap are left out; num_comments still says 7


def test_a_reply_whose_comment_wasnt_read_is_left_out_so_the_thread_stays_whole(tmp_path):
    # c9 answers c8, which the archive doesn't have; c10 answers c9. Neither can point to a comment in the thread.
    collapsed = {"c9": raw_comment("c9", "t1_c8", body="Agreed."), "c10": raw_comment("c10", "t1_c9", body="Me too.")}
    service = FakeArchive(trees={"1arch01": [node(raw_comment("c1", "t3_1arch01")), more("c8", "c9", "c10")]}, collapsed=collapsed)
    thread = make_archive(tmp_path, service).get_thread("1arch01")
    assert [c.id for c in thread.comments] == ["c1"]


def test_a_comment_with_no_text_or_no_date_is_left_out(tmp_path):
    blank = raw_comment("c2", "t3_1arch01", body="   ")
    undated = raw_comment("c3", "t3_1arch01") | {"created_utc": None}
    service = FakeArchive(trees={"1arch01": [node(raw_comment("c1", "t3_1arch01")), node(blank), node(undated)]})
    assert [c.id for c in make_archive(tmp_path, service).get_thread("1arch01").comments] == ["c1"]


def test_a_thread_read_from_the_archive_saves_and_loads_like_any_library_thread(tmp_path):
    thread = make_archive(tmp_path).get_thread("1arch01")
    library._save(thread, tmp_path / "library")
    [loaded] = load_threads(tmp_path / "library" / "threads")  # the thread file checks pass
    assert loaded.read_from == "arctic_shift" and len(loaded.comments) == 8
    assert {c.id: c.body for c in loaded.comments}["c4"] == "[deleted]"


def test_the_archive_answer_is_cached_for_48_hours_then_read_again(tmp_path):
    service, clock = FakeArchive(), FakeClock()
    first = make_archive(tmp_path, service, clock).get_thread("1arch01")
    clock.now += timedelta(hours=47)
    again = make_archive(tmp_path, service, clock).get_thread("1arch01")
    assert len(service.requests) == 3 and again == first  # collected_at too: when the archive was actually read
    clock.now += timedelta(hours=2)
    client = make_archive(tmp_path, service, clock)
    assert not list((tmp_path / "cache").rglob("*.json"))  # older than 48 hours: deleted
    assert client.get_thread("1arch01").collected_at == clock.now and len(service.requests) == 6


def test_the_cache_keeps_only_the_fields_a_thread_needs(tmp_path):
    make_archive(tmp_path).get_thread("1arch01")
    cached = "".join(p.read_text(encoding="utf-8") for p in (tmp_path / "cache").rglob("*.json"))
    assert "Mine died again." in cached  # the text may be kept now, for 48 hours
    assert "Not kept" not in cached and "example.com/not-kept" not in cached


def test_a_busy_archive_gets_one_retry(tmp_path):
    clock = FakeClock()
    thread = make_archive(tmp_path, FakeArchive(busy_first=True), clock).get_thread("1arch01")
    assert thread.id == "1arch01" and 30.0 in clock.slept


def test_a_failing_archive_raises_and_caches_nothing(tmp_path):
    service = FakeArchive(status=500)
    with pytest.raises(ArcticShiftError):
        make_archive(tmp_path, service).get_thread("1arch01")
    assert len(service.requests) == 1 and not list((tmp_path / "cache").rglob("*.json"))


def test_a_post_the_archive_doesnt_have_is_an_error(tmp_path):
    service = FakeArchive(posts={})
    with pytest.raises(ArcticShiftError, match="1arch01"):
        make_archive(tmp_path, service).get_thread("1arch01")
    assert service.paths() == ["posts/ids"]


def test_a_subreddit_outside_the_decided_ones_is_refused(tmp_path):
    service = FakeArchive(posts={"1arch01": archive_post(subreddit="funny")})
    with pytest.raises(ValueError, match="r/funny"):
        make_archive(tmp_path, service).get_thread("1arch01", subreddit="funny")
    assert service.requests == []  # refused before any call when the subreddit is given
    with pytest.raises(ValueError, match="r/funny"):
        make_archive(tmp_path, service).get_thread("1arch01")
    assert service.paths() == ["posts/ids"]  # otherwise as soon as the post says where it is: its comments aren't read


# --- Where a thread was read, and when Reddit itself was last read for it ---

def test_a_thread_file_saved_before_9_october_still_loads_and_counts_as_read_through_parse():
    old = make_thread()  # no read_from, no checked_live_at
    assert "read_from" not in old and "checked_live_at" not in old
    thread = Thread.model_validate(old)
    assert (thread.read_from, thread.checked_live_at) == (None, None)
    assert thread.last_checked_live() == thread.collected_at


def test_an_archive_thread_counts_as_checked_live_only_once_it_was():
    thread = Thread.model_validate(make_thread(read_from="arctic_shift"))
    assert thread.last_checked_live() is None
    checked = Thread.model_validate(make_thread(read_from="arctic_shift", checked_live_at="2026-10-20T08:00:00Z"))
    assert checked.last_checked_live() == datetime(2026, 10, 20, 8, 0, tzinfo=UTC)


def test_an_unknown_place_of_reading_is_refused():
    with pytest.raises(ValidationError, match="read_from"):
        Thread.model_validate(make_thread(read_from="pushshift"))


def test_a_thread_read_through_parse_is_checked_live_when_fetched(tmp_path):
    thread = make_parse_client(tmp_path, FakeParseService()).get_thread("SkincareAddiction", "1fake01")
    assert thread.read_from == "parse" and thread.checked_live_at == thread.collected_at
    assert thread.last_checked_live() == thread.collected_at


# --- ArchiveSource: finding and reading through the archive, never through Parse ---

def search_post(post_id, title="Best electric kettle?", num_comments=40, subreddit="BuyItForLife") -> dict:
    """One archive search result. Content is made up."""
    return {"id": post_id, "title": title, "num_comments": num_comments, "score": 25, "subreddit": subreddit,
            "created_utc": POSTED, "permalink": f"/r/{subreddit}/comments/{post_id}/post/"}


def kettle_posts() -> list[dict]:
    """3 advice, 1 long-term and 2 warning threads over the kettle's subreddits, best first: 1a1 1a2 1a3 1l1 1w1 1w2."""
    return [
        search_post("1a1", "Best electric kettle?", 300, "BuyItForLife"),
        search_post("1a2", "Electric kettle recommendations?", 250, "tea"),
        search_post("1a3", "Which electric kettle should I buy?", 200, "Coffee"),
        search_post("1l1", "Dualit kettle, 12 years later", 90, "Coffee"),
        search_post("1w1", "My electric kettle died after a year", 60, "BuyItForLife"),
        search_post("1w2", "Kettle regret: the lid broke", 30, "tea"),
    ]


class FakeArchiveClient:
    """Stands in for ArcticShiftClient inside a source: canned searches and threads, every call recorded."""

    def __init__(self, posts=(), fail_search=False, fail_read=()):
        self.posts = list(posts)
        self.fail_search = fail_search
        self.fail_read = set(fail_read)
        self.searches: list[tuple[str, str]] = []
        self.reads: list[tuple[str, str | None]] = []

    def search_posts(self, subreddit, title, limit=25):
        self.searches.append((subreddit, title))
        if self.fail_search:
            raise ArcticShiftError("Arctic Shift answered 422: Timeout. Maybe slow down a bit")
        return [dict(p) for p in self.posts if p["subreddit"] == subreddit]

    def get_thread(self, post_id, subreddit=None):
        self.reads.append((post_id, subreddit))
        if post_id in self.fail_read:
            raise ArcticShiftError(f"Arctic Shift answered 500 to the comments of post {post_id}")
        title = next((p["title"] for p in self.posts if p["id"] == post_id), "Electric kettle that lasts?")
        return archive_thread(post_id, subreddit or "BuyItForLife", title)


def archive_thread(post_id, subreddit="BuyItForLife", title="Electric kettle that lasts?") -> Thread:
    """A thread as ArcticShiftClient.get_thread gives it: one readable comment, one deleted."""
    return Thread.model_validate(make_thread(
        id=post_id, community=subreddit, category="kitchen", title=title, body="",
        url=f"https://www.reddit.com/r/{subreddit}/comments/{post_id}/post/", read_from="arctic_shift",
        comments=[
            {"id": f"{post_id}c1", "parent_id": None, "author": {"name": "test_user"}, "body": "My Dualit kettle is 12 years old.",
             "created_at": "2025-03-02", "score": 12, "url": f"https://www.reddit.com/r/{subreddit}/comments/{post_id}/x/{post_id}c1/"},
            {"id": f"{post_id}c2", "parent_id": None, "author": None, "body": "[deleted]", "status": "deleted",
             "created_at": "2025-03-02", "score": 1, "url": f"https://www.reddit.com/r/{subreddit}/comments/{post_id}/x/{post_id}c2/"},
        ],
    ))


def test_the_archive_source_follows_the_one_interface():
    assert isinstance(ArchiveSource(FakeArchiveClient()), Source)


def test_the_archive_source_finds_and_reads_through_the_archive_only():
    client = FakeArchiveClient(kettle_posts())
    threads = ArchiveSource(client).find_threads(parse_query(KETTLE), limit=2)
    assert [t.id for t in threads] == ["1a1", "1a2"]
    assert client.searches[0] == ("BuyItForLife", "kettle")
    assert client.reads == [("1a1", "BuyItForLife"), ("1a2", "tea")]
    assert all(t.read_from == "arctic_shift" for t in threads)


def test_the_archive_source_never_builds_or_calls_parse(monkeypatch):
    from engine import parse_reddit, sources

    def refuse(*args, **kwargs):
        raise AssertionError("the archive source must never touch Parse")

    monkeypatch.setattr(sources, "ParseRedditClient", refuse)
    monkeypatch.setattr(parse_reddit.ParseRedditClient, "_call", refuse)
    ArchiveSource(FakeArchiveClient(kettle_posts())).find_raw_threads(parse_query(KETTLE), limit=6, mix={"advice": 3, "warning": 2})


def test_the_archive_source_picks_the_same_mix_as_the_parse_source_would():
    query, mix = parse_query(KETTLE), {"advice": 3, "long_term": 1, "warning": 2}
    archive = FakeArchiveClient(kettle_posts())
    threads = ArchiveSource(archive).find_raw_threads(query, limit=6, mix=mix)
    ranked = ParseSource(client=object(), finder=FakeArchiveClient(kettle_posts())).rank_candidates(query)
    assert [t.id for t in threads] == [p["id"] for p in choose_mix(query, ranked, total=6, mix=mix)]
    assert [t.id for t in threads] == ["1a1", "1a2", "1a3", "1l1", "1w1", "1w2"]


def test_find_threads_drops_deleted_comments_and_raw_threads_keep_them():
    query = parse_query(KETTLE)
    [usable] = ArchiveSource(FakeArchiveClient(kettle_posts())).find_threads(query, limit=1)
    [raw] = ArchiveSource(FakeArchiveClient(kettle_posts())).find_raw_threads(query, limit=1)
    assert [c.id for c in usable.comments] == ["1a1c1"]
    assert [c.status for c in raw.comments] == ["ok", "deleted"]


def test_with_only_one_kind_asked_for_and_none_found_nothing_is_read():
    client = FakeArchiveClient([p for p in kettle_posts() if not p["id"].startswith("1w")])
    threads = ArchiveSource(client).find_raw_threads(parse_query(KETTLE), limit=2, mix={"warning": 2}, fill=False)
    assert threads == [] and client.reads == []


@pytest.mark.parametrize("text", ["something for my face", "a good laptop"])
def test_an_unclear_request_searches_and_reads_nothing(text):
    client = FakeArchiveClient(kettle_posts())
    assert ArchiveSource(client).find_threads(parse_query(text)) == []
    assert client.searches == client.reads == []


def test_an_archive_down_from_the_first_search_is_reported_not_taken_for_no_threads():
    # There is no paid search to fall back on: saying "no threads found" would hide the outage.
    client = FakeArchiveClient(kettle_posts(), fail_search=True)
    with pytest.raises(ArcticShiftError):
        ArchiveSource(client).find_threads(parse_query(KETTLE))
    assert len(client.searches) == 1 and client.reads == []


def test_an_archive_search_failing_later_keeps_what_was_found():
    class FailsSecond(FakeArchiveClient):
        def search_posts(self, subreddit, title, limit=25):
            if self.searches:
                self.searches.append((subreddit, title))
                raise ArcticShiftError("Arctic Shift answered 422: Timeout. Maybe slow down a bit")
            return super().search_posts(subreddit, title, limit)

    client = FailsSecond(kettle_posts())
    threads = ArchiveSource(client).find_threads(parse_query(KETTLE), limit=6)
    assert [t.id for t in threads] == ["1a1", "1w1"]  # what r/BuyItForLife's search found before the failure


def test_a_failed_read_is_passed_on():
    with pytest.raises(ArcticShiftError):
        ArchiveSource(FakeArchiveClient(kettle_posts(), fail_read={"1a2"})).find_threads(parse_query(KETTLE), limit=3)


def test_without_an_arctic_shift_client_the_archive_source_finds_nothing_and_builds_none(monkeypatch):
    # So a test (or any code) that gives no client can never reach the network through it.
    from engine import sources

    monkeypatch.setattr(sources, "ArcticShiftClient", lambda *args, **kwargs: pytest.fail("no client may be built here"))
    assert ArchiveSource(None).find_raw_threads(parse_query(KETTLE), limit=6) == []
