"""The Parse reddit.com API client. Every test uses a fake service, so no test ever spends credits."""

import json
from datetime import UTC, datetime, timedelta

import pytest

from engine.gold import load_gold_set
from engine.parse_reddit import ParseAPIError, ParseRedditClient, parse_thread_url, save_to_gold
from engine.tests.factories import write_gold

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def parse_response() -> dict:
    """Shaped like the documented get_post_comments response. All content is made up."""

    def comment(cid, parent, author="test_user", body="A readable comment.", depth=0):
        return {
            "id": cid, "author": author, "body": body, "score": 12, "created_utc": 1740906000.0, "depth": depth,
            "parent_id": parent, "permalink": f"/r/SkincareAddiction/comments/1fake01/gentle_exfoliant/{cid}/",
            "is_submitter": False, "media": [],
        }

    return {
        "post": {
            "id": "1fake01", "title": "Gentle exfoliant for sensitive skin?", "author": "test_op",
            "selftext": "Looking for something under £30.", "score": 150, "upvote_ratio": 0.97, "num_comments": 42,
            "created_utc": 1740819600.0, "url": "https://www.reddit.com/r/SkincareAddiction/comments/1fake01/gentle_exfoliant/",
            "permalink": "/r/SkincareAddiction/comments/1fake01/gentle_exfoliant/", "subreddit": "SkincareAddiction",
            "link_flair_text": None, "is_self": True, "is_video": False, "thumbnail": "self", "media": [],
        },
        "comments": [
            comment("c1aaaa", "t3_1fake01", body="  I've used the CeraVe SA Cleanser for 2 years.\n\nGentle, but drying in winter. "),
            comment("c2bbbb", "t1_c1aaaa", depth=1),
            comment("c3cccc", "t3_1fake01", author="[deleted]", body="[deleted]"),
            comment("c4dddd", "t3_1fake01", author="[deleted]", body="Still readable; only the account is gone."),
            comment("c5eeee", "t3_1fake01", body="[removed]"),
        ],
        "total_comments_fetched": 5,
        "more_comments_available": 0,
    }


class FakeService:
    """Stands in for the network: records every request and answers with a canned response.

    Real successful answers come wrapped as {"status": "success", "data": ...} (seen on 7 Oct 2026);
    errors come unwrapped, e.g. {"error": "Invalid API key", "status_code": 401}.
    """

    def __init__(self, status=200, body=None, wrap=True):
        self.status = status
        self.body = body if body is not None else parse_response()
        self.wrap = wrap
        self.requests = []

    def __call__(self, url, headers):
        self.requests.append((url, headers))
        body = {"status": "success", "data": self.body} if self.wrap else self.body
        return self.status, json.dumps(body).encode()


class FakeClock:
    def __init__(self):
        self.now = NOW
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += timedelta(seconds=seconds)


def make_client(tmp_path, service=None, clock=None, api_key="test-key"):
    clock = clock or FakeClock()
    return ParseRedditClient(
        api_key=api_key, cache_dir=tmp_path / "cache", fetch=service or FakeService(), clock=clock, sleep=clock.sleep
    )


# --- Turning a response into our Thread shape ---

def test_thread_is_mapped_into_our_shape(tmp_path):
    thread = make_client(tmp_path).get_thread("SkincareAddiction", "1fake01")
    assert (thread.id, thread.community, thread.category, thread.source) == ("1fake01", "SkincareAddiction", "skincare", "reddit")
    assert thread.url == "https://www.reddit.com/r/SkincareAddiction/comments/1fake01/gentle_exfoliant/"
    assert thread.created_at == datetime(2025, 3, 1, 9, 0, tzinfo=UTC)
    assert thread.collected_at == NOW
    assert thread.author.name == "test_op"
    assert [c.id for c in thread.comments] == ["c1aaaa", "c2bbbb", "c3cccc", "c4dddd", "c5eeee"]


def test_comment_text_is_kept_exactly(tmp_path):
    thread = make_client(tmp_path).get_thread("SkincareAddiction", "1fake01")
    assert thread.comments[0].body == "  I've used the CeraVe SA Cleanser for 2 years.\n\nGentle, but drying in winter. "


def test_replies_point_to_their_parent_comment(tmp_path):
    comments = make_client(tmp_path).get_thread("SkincareAddiction", "1fake01").comments
    assert comments[0].parent_id is None  # a direct reply to the post
    assert comments[1].parent_id == "c1aaaa"


def test_comment_links_are_full_web_addresses(tmp_path):
    comment = make_client(tmp_path).get_thread("SkincareAddiction", "1fake01").comments[0]
    assert comment.url == "https://www.reddit.com/r/SkincareAddiction/comments/1fake01/gentle_exfoliant/c1aaaa/"


def test_deleted_and_removed_comments(tmp_path):
    comments = {c.id: c for c in make_client(tmp_path).get_thread("SkincareAddiction", "1fake01").comments}
    assert (comments["c3cccc"].status, comments["c3cccc"].author) == ("deleted", None)
    assert (comments["c4dddd"].status, comments["c4dddd"].author) == ("ok", None)
    assert comments["c5eeee"].status == "removed"


def test_request_sends_the_key_and_parameters(tmp_path):
    service = FakeService()
    make_client(tmp_path, service).get_thread("SkincareAddiction", "1fake01", limit=500)
    url, headers = service.requests[0]
    assert url.startswith("https://api.parse.bot/scraper/5c1e1643-5ce6-4086-9883-3886b0c0e506/get_post_comments?")
    assert "post_id=1fake01" in url and "subreddit=SkincareAddiction" in url and "limit=500" in url
    assert headers["X-API-Key"] == "test-key"


# --- Spending credits carefully ---

def test_subreddit_outside_the_decided_list_spends_nothing(tmp_path):
    service = FakeService()
    with pytest.raises(ValueError, match="AskReddit"):
        make_client(tmp_path, service).get_thread("AskReddit", "1fake01")
    assert service.requests == []


def test_missing_key_is_explained_and_spends_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("PARSE_API_KEY", raising=False)
    service = FakeService()
    client = ParseRedditClient(cache_dir=tmp_path / "cache", fetch=service, env_file=tmp_path / "missing.env")
    with pytest.raises(ParseAPIError, match="PARSE_API_KEY"):
        client.get_thread("SkincareAddiction", "1fake01")
    assert service.requests == []


def test_key_is_read_from_the_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("PARSE_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("ANTHROPIC_API_KEY=\nPARSE_API_KEY=key-from-file\n")
    service = FakeService()
    ParseRedditClient(cache_dir=tmp_path / "cache", fetch=service, env_file=env_file).get_thread("SkincareAddiction", "1fake01")
    assert service.requests[0][1]["X-API-Key"] == "key-from-file"


def test_second_request_comes_from_the_cache(tmp_path):
    service = FakeService()
    client = make_client(tmp_path, service)
    client.get_thread("SkincareAddiction", "1fake01")
    client.get_thread("SkincareAddiction", "1fake01")
    assert len(service.requests) == 1


def test_cache_expires_after_48_hours(tmp_path):
    service, clock = FakeService(), FakeClock()
    make_client(tmp_path, service, clock).get_thread("SkincareAddiction", "1fake01")
    clock.now += timedelta(hours=49)
    make_client(tmp_path, service, clock).get_thread("SkincareAddiction", "1fake01")
    assert len(service.requests) == 2


def test_old_cache_entries_are_deleted(tmp_path):
    # The deletion rule: nothing fetched is kept longer than 48 hours.
    clock = FakeClock()
    make_client(tmp_path, clock=clock).get_thread("SkincareAddiction", "1fake01")
    assert list((tmp_path / "cache" / "responses").glob("*.json"))
    clock.now += timedelta(hours=49)
    make_client(tmp_path, clock=clock)
    assert not list((tmp_path / "cache" / "responses").glob("*.json"))


def test_calls_are_spaced_to_respect_the_rate_limit(tmp_path):
    # Free plan: 5 calls a minute, so at least 12 seconds apart.
    clock = FakeClock()
    client = make_client(tmp_path, clock=clock)
    client.get_thread("SkincareAddiction", "1fake01")
    client.search("SkincareAddiction", "exfoliant")
    assert clock.slept == [12.0]


def test_every_real_call_is_logged_with_its_credits(tmp_path):
    client = make_client(tmp_path)
    client.get_thread("SkincareAddiction", "1fake01")
    client.get_thread("SkincareAddiction", "1fake01")  # cached: free
    client.search("SkincareAddiction", "exfoliant")
    assert client.credits_used_this_month() == 4


def test_monthly_budget_is_never_exceeded(tmp_path):
    service = FakeService()
    client = make_client(tmp_path, service)
    client.usage_log.parent.mkdir(parents=True, exist_ok=True)
    client.usage_log.write_text(json.dumps({"at": NOW.isoformat(), "endpoint": "search_posts", "credits": 199}) + "\n")
    with pytest.raises(ParseAPIError, match="credits"):
        client.get_thread("SkincareAddiction", "1fake01")
    assert service.requests == []


def test_service_errors_are_reported_and_not_cached(tmp_path):
    service = FakeService(status=401, body={"error": "Invalid API key", "status_code": 401}, wrap=False)
    client = make_client(tmp_path, service)
    with pytest.raises(ParseAPIError, match="401"):
        client.get_thread("SkincareAddiction", "1fake01")
    service.status, service.body, service.wrap = 200, parse_response(), True
    client.get_thread("SkincareAddiction", "1fake01")
    assert len(service.requests) == 2


def test_error_message_disguised_as_success_is_reported_and_not_cached(tmp_path):
    service = FakeService(status=200, body={"error": "upstream timeout"}, wrap=False)
    client = make_client(tmp_path, service)
    with pytest.raises(ParseAPIError, match="upstream timeout"):
        client.get_thread("SkincareAddiction", "1fake01")
    service.body, service.wrap = parse_response(), True
    client.get_thread("SkincareAddiction", "1fake01")
    assert len(service.requests) == 2


def test_wrapper_without_success_status_is_an_error(tmp_path):
    service = FakeService(status=200, body={"status": "error", "message": "subreddit unavailable"}, wrap=False)
    with pytest.raises(ParseAPIError, match="subreddit unavailable"):
        make_client(tmp_path, service).get_thread("SkincareAddiction", "1fake01")


def test_search_returns_the_service_response(tmp_path):
    service = FakeService(body={"posts": [{"id": "1fake01"}], "after": None})
    result = make_client(tmp_path, service).search("SkincareAddiction", "gentle exfoliant", limit=10)
    assert result["posts"][0]["id"] == "1fake01"
    url, _ = service.requests[0]
    assert "search_posts?" in url and "query=gentle+exfoliant" in url and "limit=10" in url


# --- Links and the gold set ---

@pytest.mark.parametrize("url", [
    "https://www.reddit.com/r/SkincareAddiction/comments/1fake01/gentle_exfoliant/",
    "https://old.reddit.com/r/SkincareAddiction/comments/1fake01/",
    "reddit.com/r/SkincareAddiction/comments/1fake01/gentle_exfoliant/c1aaaa/?context=3",
])
def test_thread_link_gives_subreddit_and_id(url):
    assert parse_thread_url(url) == ("SkincareAddiction", "1fake01")


def test_share_link_is_explained():
    with pytest.raises(ValueError, match="/comments/"):
        parse_thread_url("https://www.reddit.com/r/SkincareAddiction/s/AbCdEf123")


def test_fetched_thread_saves_into_a_valid_gold_set(tmp_path):
    gold_dir = write_gold(tmp_path / "gold", [])
    thread = make_client(tmp_path).get_thread("SkincareAddiction", "1fake01")
    path = save_to_gold(thread, gold_dir)
    assert path == gold_dir / "threads" / "1fake01.json"
    assert load_gold_set(gold_dir).comment("c1aaaa").body == thread.comments[0].body


def test_saving_never_overwrites_an_existing_thread(tmp_path):
    gold_dir = write_gold(tmp_path / "gold", [])
    thread = make_client(tmp_path).get_thread("SkincareAddiction", "1fake01")
    save_to_gold(thread, gold_dir)
    with pytest.raises(FileExistsError):
        save_to_gold(thread, gold_dir)


def test_secure_connections_have_certificates_to_check_against():
    # The python.org installer for macOS ships without them, so every HTTPS call failed before any credit was spent.
    from engine.parse_reddit import _ssl_context

    assert _ssl_context().cert_store_stats()["x509_ca"] > 0


def test_offline_client_answers_from_its_cache_and_never_spends(tmp_path):
    # Evaluation runs offline: it may reuse saved answers but must never call Parse.
    service = FakeService()
    make_client(tmp_path, service).get_thread("SkincareAddiction", "1fake01")
    offline = ParseRedditClient(api_key="test-key", cache_dir=tmp_path / "cache", fetch=service, clock=FakeClock(), offline=True)
    assert offline.get_thread("SkincareAddiction", "1fake01").id == "1fake01"
    with pytest.raises(ParseAPIError, match="offline"):
        offline.search("SkincareAddiction", "exfoliant")
    assert len(service.requests) == 1
