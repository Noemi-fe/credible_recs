"""The live checks' cache in a private Google Cloud Storage bucket (check ahead, Noemi's decision of 13 Oct 2026).

On Google Cloud Run a server's disk is wiped whenever it sleeps, so what Reddit's embed page said about a comment is
also kept in a bucket the server and the daily pre-check share: read from this machine's folder first, then the bucket,
and only then from Reddit; written to both. The 48-hour rule holds for the bucket too. Every call to Google here goes
to a made-up stand-in: no test reaches the network.
"""

import json
from datetime import timedelta

from engine.live_check import (BUCKET_VAR, METADATA_TOKEN_URL, Bucket, LiveChecker, checker_from_env, embed_url)
from engine.tests.test_live_check import QUOTE, URL, Clock, FakeReddit, page

OTHER_URL = URL.replace("c1aaaa", "c2bbbb")


class FakeGoogle:
    """Stands in for the Cloud Run metadata server (an access token) and the Cloud Storage JSON API (one bucket)."""

    def __init__(self, bucket="credible-test-cache", down=False, token_status=200):
        self.bucket, self.down, self.token_status = bucket, down, token_status
        self.objects: dict[str, bytes] = {}
        self.calls: list[tuple[str, str, dict]] = []
        self.tokens_given = 0

    def __call__(self, method, url, headers, body=None, timeout=None):
        self.calls.append((method, url, dict(headers)))
        if self.down:
            raise TimeoutError("timed out")
        if url == METADATA_TOKEN_URL:
            assert headers.get("Metadata-Flavor") == "Google"
            self.tokens_given += 1
            return self.token_status, json.dumps({"access_token": f"token-{self.tokens_given}", "expires_in": 3599,
                                                  "token_type": "Bearer"}).encode()
        assert headers.get("Authorization", "").startswith("Bearer token-")
        from urllib.parse import parse_qs, unquote, urlsplit

        parts = urlsplit(url)
        if method == "GET":
            prefix = f"/storage/v1/b/{self.bucket}/o/"
            assert parts.path.startswith(prefix) and parse_qs(parts.query) == {"alt": ["media"]}
            name = unquote(parts.path[len(prefix):])
            return (200, self.objects[name]) if name in self.objects else (404, b'{"error": "not found"}')
        if method == "POST":
            assert parts.path == f"/upload/storage/v1/b/{self.bucket}/o"
            query = parse_qs(parts.query)
            assert query["uploadType"] == ["media"]
            self.objects[query["name"][0]] = body
            return 200, b"{}"
        raise AssertionError(f"unexpected call {method} {url}")

    def asked(self, method):
        return [url for m, url, _ in self.calls if m == method and url != METADATA_TOKEN_URL]


def checker(tmp_path, reddit, google, clock, folder="here"):
    bucket = Bucket(google.bucket, request=google, clock=lambda: clock.now.timestamp())
    return LiveChecker(cache_dir=tmp_path / folder, fetch=reddit, clock=clock, sleep=clock.sleep, bucket=bucket)


def test_a_check_read_on_reddit_is_kept_on_this_machine_and_in_the_bucket(tmp_path):
    reddit, google, clock = FakeReddit(), FakeGoogle(), Clock()
    assert checker(tmp_path, reddit, google, clock).check(URL, QUOTE).show
    local = list((tmp_path / "here").glob("*.json"))
    assert len(local) == 1 and list(google.objects) == [f"live_check/{local[0].name}"]
    assert json.loads(google.objects[f"live_check/{local[0].name}"]) == json.loads(local[0].read_text())


def test_a_server_waking_with_an_empty_disk_finds_the_check_in_the_bucket_and_keeps_it(tmp_path):
    reddit, google, clock = FakeReddit(), FakeGoogle(), Clock()
    checker(tmp_path, reddit, google, clock, folder="before the sleep").check(URL, QUOTE)
    woken = checker(tmp_path, reddit, google, clock, folder="after the sleep")
    clock.now += timedelta(hours=5)
    assert woken.check(URL, QUOTE).show
    assert len(reddit.asked) == 1  # Reddit was read once, before the sleep
    assert len(list((tmp_path / "after the sleep").glob("*.json"))) == 1  # kept on this machine's disk too
    gets = len(google.asked("GET"))
    woken.check(URL, "still boils perfectly")
    assert len(google.asked("GET")) == gets  # the next check of the comment needs no call at all


def test_a_check_in_the_bucket_older_than_48_hours_is_never_used(tmp_path):
    reddit, google, clock = FakeReddit(), FakeGoogle(), Clock()
    checker(tmp_path, reddit, google, clock, folder="first").check(URL, QUOTE)
    clock.now += timedelta(hours=48, minutes=1)
    later = checker(tmp_path, reddit, google, clock, folder="second")
    assert later.saved_check(URL, QUOTE) is None and later.checked_at(URL) is None
    assert later.check(URL, QUOTE).show
    assert len(reddit.asked) == 2  # read on Reddit again
    (name,) = google.objects
    assert json.loads(google.objects[name])["fetched_at"] == clock.now.isoformat()  # the bucket holds the new one


def test_reading_the_bucket_never_waits_for_reddits_budget(tmp_path):
    reddit, google, clock = FakeReddit(), FakeGoogle(), Clock()
    urls = [URL.replace("c1aaaa", f"c{n}xxxx") for n in range(5)]
    first = checker(tmp_path, reddit, google, clock, folder="first")
    for url in urls:
        first.check(url, QUOTE)
    woken = LiveChecker(cache_dir=tmp_path / "woken", fetch=reddit, clock=clock, sleep=clock.sleep, burst=1,
                        refill=4, bucket=Bucket(google.bucket, request=google, clock=lambda: clock.now.timestamp()))
    started = clock.now
    assert all(woken.check(url, QUOTE).show for url in urls)
    assert clock.now == started and len(reddit.asked) == 5  # no wait, and no read of Reddit


def test_the_token_comes_from_the_metadata_server_and_is_kept_until_it_expires(tmp_path):
    reddit, google, clock = FakeReddit(), FakeGoogle(), Clock()
    live = checker(tmp_path, reddit, google, clock)
    live.check(URL, QUOTE)
    live.check(OTHER_URL, QUOTE)
    assert google.tokens_given == 1
    clock.now += timedelta(hours=1)  # the token lasts an hour: a new one is asked a little before it runs out
    live.check(URL.replace("c1aaaa", "c3cccc"), QUOTE)
    assert google.tokens_given == 2


def test_when_the_bucket_cant_be_reached_checks_go_on_with_this_machine_and_reddit(tmp_path, capsys):
    reddit, google, clock = FakeReddit(), FakeGoogle(down=True), Clock()
    live = checker(tmp_path, reddit, google, clock)
    assert live.check(URL, QUOTE).show
    assert live.check(OTHER_URL, QUOTE).show
    assert len(reddit.asked) == 2 and len(list((tmp_path / "here").glob("*.json"))) == 2
    calls = len(google.calls)
    live.check(URL.replace("c1aaaa", "c3cccc"), QUOTE)
    assert len(google.calls) == calls  # left alone for a while after failing, so answers don't wait on it
    said = capsys.readouterr().err
    assert len(said.splitlines()) == 1 and "bucket" in said  # said once, in one line
    assert "token-" not in said  # the token is never printed


def test_a_refused_token_leaves_the_bucket_out(tmp_path):
    reddit, google, clock = FakeReddit(), FakeGoogle(token_status=403), Clock()
    live = checker(tmp_path, reddit, google, clock)
    assert live.check(URL, QUOTE).show
    assert google.objects == {} and google.asked("GET") == [] and google.asked("POST") == []


def test_a_fresher_check_can_be_asked_for_and_is_read_again_when_older(tmp_path):
    # The daily pre-check reads again a comment checked more than PRECHECK_FRESH_HOURS ago, though answers could still
    # use that check: so the next day's answers never find it expired.
    reddit, clock = FakeReddit(), Clock()
    live = LiveChecker(cache_dir=tmp_path / "cache", fetch=reddit, clock=clock, sleep=clock.sleep)
    live.check(URL, QUOTE)
    clock.now += timedelta(hours=21)
    assert live.checked_at(URL) is not None and live.checked_at(URL, max_age=timedelta(hours=20)) is None
    live.check(URL, QUOTE, max_age=timedelta(hours=20))
    assert len(reddit.asked) == 2
    assert live.checked_at(URL, max_age=timedelta(hours=20)) == clock.now


def test_a_saved_check_never_lasts_beyond_48_hours_whatever_is_asked(tmp_path):
    reddit, clock = FakeReddit(), Clock()
    live = LiveChecker(cache_dir=tmp_path / "cache", fetch=reddit, clock=clock, sleep=clock.sleep)
    live.check(URL, QUOTE)
    clock.now += timedelta(hours=49)
    assert live.checked_at(URL, max_age=timedelta(days=30)) is None
    live.check(URL, QUOTE, max_age=timedelta(days=30))
    assert len(reddit.asked) == 2


def test_a_saved_check_answers_without_reading_reddit(tmp_path):
    reddit, clock = FakeReddit(answer=(200, page("Edit: it died last week, avoid."))), Clock()
    live = LiveChecker(cache_dir=tmp_path / "cache", fetch=reddit, clock=clock, sleep=clock.sleep)
    assert live.saved_check(URL, QUOTE) is None and reddit.asked == []
    live.check(URL, QUOTE)
    assert live.saved_check(URL, QUOTE).status == "changed"
    assert len(reddit.asked) == 1


def test_objects_are_named_after_the_comments_page_as_the_files_are(tmp_path):
    reddit, google, clock = FakeReddit(), FakeGoogle(), Clock()
    checker(tmp_path, reddit, google, clock).check(URL, QUOTE)
    import hashlib

    name = hashlib.sha256(embed_url(URL).encode()).hexdigest()[:32]
    assert list(google.objects) == [f"live_check/{name}.json"]


def test_the_bucket_is_used_only_when_its_name_is_set(tmp_path):
    assert checker_from_env({}, cache_dir=tmp_path).bucket is None
    assert checker_from_env({BUCKET_VAR: "  "}, cache_dir=tmp_path).bucket is None
    live = checker_from_env({BUCKET_VAR: "credible-test-cache"}, cache_dir=tmp_path)
    assert live.bucket is not None and live.bucket.name == "credible-test-cache"


def test_real_answers_use_the_bucket_when_it_is_named(monkeypatch):
    # What the web server and the command line build (engine.pipeline.live_checker): the same checker as the pre-check.
    from engine import pipeline

    monkeypatch.setenv(BUCKET_VAR, "credible-test-cache")
    assert pipeline.live_checker().bucket.name == "credible-test-cache"
    monkeypatch.delenv(BUCKET_VAR)
    assert pipeline.live_checker().bucket is None
