"""The Arctic Shift finder. Every test uses a fake service: no network."""

import json
from datetime import UTC, datetime, timedelta

import pytest

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
