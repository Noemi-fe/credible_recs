"""The Arctic Shift finder. Every test uses a fake service: no network."""

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from engine import arctic_shift
from engine.arctic_shift import ArcticShiftClient, ArcticShiftError

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def post(post_id, title="Electric kettle that lasts?", num_comments=40, subreddit="BuyItForLife"):
    return {
        "id": post_id, "title": title, "num_comments": num_comments, "score": 30, "subreddit": subreddit,
        "created_utc": 1779008488, "permalink": f"/r/{subreddit}/comments/{post_id}/x/",
        "selftext": "The post's own text, which we must never keep.", "author": "someone", "author_flair_text": None,
    }


class FakeService:
    def __init__(self, status=200, body=None):
        self.status = status
        self.body = body if body is not None else {"data": [post("1aaa111"), post("1bbb222", title="Kettle advice", num_comments=12)]}
        self.requests = []

    def __call__(self, url, headers):
        self.requests.append((url, headers))
        return self.status, json.dumps(self.body).encode()


class FakeClock:
    def __init__(self):
        self.now = NOW
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += timedelta(seconds=seconds)


def make_client(tmp_path, service=None, clock=None):
    clock = clock or FakeClock()
    return ArcticShiftClient(cache_dir=tmp_path / "cache", fetch=service or FakeService(), clock=clock, sleep=clock.sleep)


def test_search_returns_only_what_finding_needs(tmp_path):
    posts = make_client(tmp_path).search_posts("BuyItForLife", "kettle")
    assert [p["id"] for p in posts] == ["1aaa111", "1bbb222"]
    assert set(posts[0]) == {
        "id", "subreddit", "title", "num_comments", "score", "created_utc", "permalink", "link_flair_text", "removed_by_category",
    }  # flair ("[Request]") and removal status are labels on the post, not anyone's text


def test_text_is_never_kept_even_in_the_cache(tmp_path):
    # An archive may still hold text people later deleted on Reddit, so none of it is stored.
    make_client(tmp_path).search_posts("BuyItForLife", "kettle")
    cached = "".join(p.read_text() for p in (tmp_path / "cache").rglob("*.json"))
    assert "never keep" not in cached and "someone" not in cached


def test_request_is_polite_and_well_formed(tmp_path):
    service = FakeService()
    make_client(tmp_path, service).search_posts("BuyItForLife", "electric kettle", limit=10)
    url, headers = service.requests[0]
    assert url.startswith("https://arctic-shift.photon-reddit.com/api/posts/search?")
    assert "subreddit=BuyItForLife" in url and "title=electric+kettle" in url and "limit=10" in url
    assert "credible-recs" in headers["User-Agent"]


def test_second_search_comes_from_the_cache(tmp_path):
    service = FakeService()
    client = make_client(tmp_path, service)
    client.search_posts("BuyItForLife", "kettle")
    client.search_posts("BuyItForLife", "kettle")
    assert len(service.requests) == 1


def test_cache_expires_and_is_deleted_after_48_hours(tmp_path):
    service, clock = FakeService(), FakeClock()
    make_client(tmp_path, service, clock).search_posts("BuyItForLife", "kettle")
    clock.now += timedelta(hours=49)
    client = make_client(tmp_path, service, clock)
    assert not list((tmp_path / "cache").rglob("*.json"))
    client.search_posts("BuyItForLife", "kettle")
    assert len(service.requests) == 2


def test_calls_are_spaced_out(tmp_path):
    # Filling the library is a batch job, so it can afford to be gentle: 10 seconds between calls.
    clock = FakeClock()
    client = make_client(tmp_path, clock=clock)
    client.search_posts("BuyItForLife", "kettle")
    client.search_posts("tea", "kettle")
    assert clock.slept == [10.0]


@pytest.mark.parametrize("status, body, attempts", [
    (422, {"data": None, "error": "Timeout. Maybe slow down a bit"}, 2),  # busy: one retry after a pause
    (429, {"error": "Too many requests"}, 2),
    (500, {"error": "server error"}, 1),  # broken: no retry
    (200, {"data": None, "error": "Timeout. Maybe slow down a bit"}, 1),
])
def test_errors_are_reported_without_a_retry_loop_and_not_cached(tmp_path, status, body, attempts):
    service = FakeService(status=status, body=body)
    client = make_client(tmp_path, service)
    with pytest.raises(ArcticShiftError):
        client.search_posts("BuyItForLife", "kettle")
    assert len(service.requests) == attempts
    assert not list((tmp_path / "cache").rglob("*.json"))


def test_a_busy_service_gets_one_retry_after_a_pause(tmp_path):
    class BusyOnce(FakeService):
        def __call__(self, url, headers):
            self.requests.append((url, headers))
            if len(self.requests) == 1:
                return 422, json.dumps({"data": None, "error": "Timeout. Maybe slow down a bit"}).encode()
            return 200, json.dumps(self.body).encode()

    clock = FakeClock()
    posts = make_client(tmp_path, BusyOnce(), clock).search_posts("BuyItForLife", "kettle")
    assert len(posts) == 2 and 30.0 in clock.slept


# --- Commenter profiles: one account's numbers, and the flair on comments ---

def user(name="test_writer", **meta):
    """One account as Arctic Shift's users/search answers it. All numbers are made up."""
    numbers = {
        "earliest_comment_at": 1500000000, "earliest_post_at": 1520000000, "last_comment_at": 1790000000,
        "last_post_at": 1780000000, "num_comments": 900, "num_posts": 100, "post_karma": 2000,
        "comment_karma": 8000, "total_karma": 10000,
        "subreddits": ["SkincareAddiction"], "bio": "Some words the account wrote about itself.",
    }
    numbers.update(meta)
    return {"author": name, "id": "t2_fake", "_meta": numbers}


def test_user_stats_keeps_only_the_numbers(tmp_path):
    service = FakeService(body={"data": [user()]})
    stats = make_client(tmp_path, service).user_stats("test_writer")
    assert stats == {
        "earliest_comment_at": 1500000000, "earliest_post_at": 1520000000, "last_comment_at": 1790000000,
        "last_post_at": 1780000000, "num_comments": 900, "num_posts": 100, "post_karma": 2000,
        "comment_karma": 8000, "total_karma": 10000,
    }
    cached = "".join(p.read_text() for p in (tmp_path / "cache").rglob("*.json"))
    assert "Some words" not in cached and "SkincareAddiction" not in cached and "t2_fake" not in cached


def test_user_stats_request_is_well_formed(tmp_path):
    service = FakeService(body={"data": [user()]})
    make_client(tmp_path, service).user_stats("test_writer")
    url, headers = service.requests[0]
    assert url.startswith("https://arctic-shift.photon-reddit.com/api/users/search?")
    assert "author=test_writer" in url and "limit=1" in url
    assert "credible-recs" in headers["User-Agent"]


@pytest.mark.parametrize("body", [
    {"data": []},  # the archive doesn't know the account (deleted, suspended, never active)
    {"data": [user("test_writer_2")]},  # a different account, whose name only starts the same
    {"data": [{"author": "test_writer", "id": "t2_fake"}]},  # no numbers at all
])
def test_an_account_the_archive_doesnt_know_is_none(tmp_path, body):
    assert make_client(tmp_path, FakeService(body=body)).user_stats("test_writer") is None


def test_the_name_is_matched_whatever_its_capitals(tmp_path):
    # Reddit names ignore capitals: "Test_Writer" and "test_writer" are one account.
    service = FakeService(body={"data": [user("Test_Writer")]})
    assert make_client(tmp_path, service).user_stats("test_writer")["total_karma"] == 10000


def test_user_stats_come_from_the_cache_the_second_time_even_when_unknown(tmp_path):
    known, unknown = FakeService(body={"data": [user()]}), FakeService(body={"data": []})
    for n, service in enumerate((known, unknown)):
        client = make_client(tmp_path / str(n), service)
        client.user_stats("test_writer")
        client.user_stats("test_writer")
        assert len(service.requests) == 1


def test_user_stats_expire_after_48_hours(tmp_path):
    service, clock = FakeService(body={"data": [user()]}), FakeClock()
    make_client(tmp_path, service, clock).user_stats("test_writer")
    clock.now += timedelta(hours=49)
    make_client(tmp_path, service, clock).user_stats("test_writer")
    assert len(service.requests) == 2


@pytest.mark.parametrize("status, body, attempts", [
    (422, {"data": None, "error": "Timeout. Maybe slow down a bit"}, 2),
    (429, {"error": "Too many requests"}, 2),
    (500, {"error": "server error"}, 1),
])
def test_user_stats_errors_get_one_retry_at_most_and_are_not_cached(tmp_path, status, body, attempts):
    service = FakeService(status=status, body=body)
    with pytest.raises(ArcticShiftError):
        make_client(tmp_path, service).user_stats("test_writer")
    assert len(service.requests) == attempts
    assert not list((tmp_path / "cache").rglob("*.json"))


def flair_service(flairs: dict):
    """A fake comments/ids endpoint: answers with the flair of each asked-for comment it knows."""
    class Flairs(FakeService):
        def __call__(self, url, headers):
            self.requests.append((url, headers))
            asked = parse_qs(urlparse(url).query)["ids"][0].split(",")
            found = [{"id": cid, "author": "someone", "author_flair_text": flairs[cid], "body": "Their words."}
                     for cid in asked if cid in flairs]
            return 200, json.dumps({"data": found}).encode()
    return Flairs()


def test_comment_flairs_asks_for_the_flair_and_never_the_text(tmp_path):
    service = flair_service({"c1aaaa": "Dermatologist", "c2bbbb": None})
    flairs = make_client(tmp_path, service).comment_flairs(["c1aaaa", "c2bbbb"])
    assert flairs == {"c1aaaa": "Dermatologist", "c2bbbb": None}
    url = service.requests[0][0]
    assert url.startswith("https://arctic-shift.photon-reddit.com/api/comments/ids?")
    query = parse_qs(urlparse(url).query)
    assert query["ids"] == ["c1aaaa,c2bbbb"]
    assert "body" not in query["fields"][0].split(",")
    cached = "".join(p.read_text() for p in (tmp_path / "cache").rglob("*.json"))
    assert "Their words" not in cached and "someone" not in cached


def test_an_empty_flair_or_a_comment_the_archive_lacks_is_no_flair(tmp_path):
    service = flair_service({"c1aaaa": "  "})
    assert make_client(tmp_path, service).comment_flairs(["c1aaaa", "c9zzzz"]) == {"c1aaaa": None, "c9zzzz": None}


def test_comment_flairs_are_asked_100_at_a_time_and_spaced_out(tmp_path):
    ids = [f"c{n:05d}" for n in range(250)]
    service, clock = flair_service({cid: "Home cook" for cid in ids}), FakeClock()
    flairs = make_client(tmp_path, service, clock).comment_flairs(ids)
    assert len(flairs) == 250 and set(flairs.values()) == {"Home cook"}
    assert [len(parse_qs(urlparse(url).query)["ids"][0].split(",")) for url, _ in service.requests] == [100, 100, 50]
    assert clock.slept == [10.0, 10.0]


def test_each_comments_flair_is_cached_on_its_own(tmp_path):
    # So a later question about some of the same comments, in any grouping, costs nothing.
    service = flair_service({"c1aaaa": "Chef", "c2bbbb": None, "c3cccc": "Barista"})
    client = make_client(tmp_path, service)
    client.comment_flairs(["c1aaaa", "c2bbbb", "c3cccc"])
    assert client.comment_flairs(["c3cccc", "c1aaaa"]) == {"c3cccc": "Barista", "c1aaaa": "Chef"}
    assert len(service.requests) == 1


def test_the_cache_says_what_is_still_to_ask(tmp_path):
    client = make_client(tmp_path, FakeService(body={"data": [user()]}))
    client.user_stats("test_writer")
    assert client.uncached_users(["test_writer", "Test_Writer", "other_writer", "other_writer"]) == ["other_writer"]
    client = make_client(tmp_path, flair_service({"c1aaaa": "Chef"}))
    client.comment_flairs(["c1aaaa"])
    assert client.uncached_comments(["c1aaaa", "c2bbbb", "c2bbbb"]) == ["c2bbbb"]


def test_calls_are_counted(tmp_path):
    client = make_client(tmp_path, FakeService(body={"data": [user()]}))
    client.user_stats("test_writer")
    client.user_stats("test_writer")  # from the cache: no call
    assert client.calls == 1


def test_no_answer_at_all_is_an_arctic_shift_error(monkeypatch):
    # A timeout or no network is reported like any failure, so callers can carry on instead of crashing.
    def times_out(*args, **kwargs):
        raise TimeoutError("timed out")
    monkeypatch.setattr(arctic_shift.urllib.request, "urlopen", times_out)
    with pytest.raises(ArcticShiftError):
        arctic_shift._http_get("https://arctic-shift.photon-reddit.com/api/users/search?author=x", {})
