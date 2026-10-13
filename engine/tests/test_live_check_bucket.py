"""The pre-check's saved checks, shared through a private Google Cloud Storage bucket (check ahead, Noemi's decision of
13 Oct 2026), as one object: free tiers only, so a few calls a day, never one a comment.

The daily pre-check runs on a machine of its own whose disk starts empty, and the site's disk is wiped whenever it
restarts. So the pre-check writes every check it holds that is under 48 hours old to the bucket as one bundle, and the
site reads that bundle into its own folder as it gets ready and then at most once an hour, only when it has changed. The
site never writes to the bucket: its own checks stay in its folder. The 48-hour rule holds for every entry, wherever it
is read from. Every call to Google here goes to a made-up stand-in: no test reaches the network.
"""

import json
from datetime import timedelta

from engine.live_check import (BUCKET_VAR, BUNDLE_NAME, METADATA_TOKEN_URL, Bucket, LiveChecker, checker_from_env,
                               embed_url)
from engine.tests.test_live_check import QUOTE, URL, Clock, FakeReddit, page

OTHER_URL = URL.replace("c1aaaa", "c2bbbb")
BUNDLE = f"live_check/{BUNDLE_NAME}"


class FakeGoogle:
    """Stands in for the Cloud Run metadata server (an access token) and the Cloud Storage JSON API (one bucket, whose
    objects have generations as Cloud Storage's do: a number that changes with every write)."""

    def __init__(self, bucket="credible-test-cache", down=False, token_status=200):
        self.bucket, self.down, self.token_status = bucket, down, token_status
        self.objects: dict[str, tuple[int, bytes]] = {}  # name -> (generation, content)
        self.calls: list[tuple[str, str, dict]] = []
        self.tokens_given = 0
        self._generation = 1000

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
        query = parse_qs(parts.query)
        if method == "GET":
            prefix = f"/storage/v1/b/{self.bucket}/o/"
            assert parts.path.startswith(prefix)
            name = unquote(parts.path[len(prefix):])
            if name not in self.objects:
                return 404, b'{"error": "not found"}'
            generation, content = self.objects[name]
            if query == {"fields": ["generation"]}:
                return 200, json.dumps({"generation": str(generation)}).encode()
            assert query["alt"] == ["media"]
            if "generation" in query and query["generation"] != [str(generation)]:
                return 404, b'{"error": "no such generation"}'
            return 200, content
        if method == "POST":
            assert parts.path == f"/upload/storage/v1/b/{self.bucket}/o" and query["uploadType"] == ["media"]
            self._generation += 1
            self.objects[query["name"][0]] = (self._generation, body)
            return 200, b"{}"
        raise AssertionError(f"unexpected call {method} {url}")

    def asked(self, method, what=""):
        return [url for m, url, _ in self.calls if m == method and url != METADATA_TOKEN_URL and what in url]

    def bundle(self) -> dict:
        return json.loads(self.objects[BUNDLE][1])


def checker(tmp_path, reddit, google, clock, folder="here"):
    bucket = Bucket(google.bucket, request=google, clock=lambda: clock.now.timestamp())
    return LiveChecker(cache_dir=tmp_path / folder, fetch=reddit, clock=clock, sleep=clock.sleep, bucket=bucket)


# --- The pre-check writes one bundle ---

def test_a_check_read_on_reddit_is_kept_on_this_machine_and_never_sent_to_the_bucket(tmp_path):
    reddit, google, clock = FakeReddit(), FakeGoogle(), Clock()
    live = checker(tmp_path, reddit, google, clock)
    assert live.check(URL, QUOTE).show and live.check(URL, "still boils perfectly").show
    assert len(list((tmp_path / "here").glob("*.json"))) == 1
    assert google.calls == []  # no call at all: a check uses this machine's folder and Reddit only


def test_the_bundle_holds_every_check_under_48_hours_old_in_one_object(tmp_path):
    reddit, google, clock = FakeReddit(), FakeGoogle(), Clock()
    live = checker(tmp_path, reddit, google, clock)
    live.check(URL, QUOTE)
    clock.now += timedelta(hours=47)
    live.check(OTHER_URL, QUOTE)
    assert live.save_bundle() == 2
    assert list(google.objects) == [BUNDLE] and len(google.asked("POST")) == 1
    clock.now += timedelta(hours=2)  # the first check is now 49 hours old
    assert live.save_bundle() == 1
    checks = google.bundle()["checks"]
    import hashlib

    assert list(checks) == [f"{hashlib.sha256(embed_url(OTHER_URL).encode()).hexdigest()[:32]}.json"]
    assert set(next(iter(checks.values()))) == {"fetched_at", "text"}  # the comment's text and when it was read only


# --- The site reads it ---

def test_a_server_with_an_empty_disk_gets_the_pre_checks_checks_from_the_bundle(tmp_path):
    reddit, google, clock = FakeReddit(), FakeGoogle(), Clock()
    job = checker(tmp_path, reddit, google, clock, folder="the job")
    job.check(URL, QUOTE)
    job.check(OTHER_URL, QUOTE)
    job.save_bundle()
    clock.now += timedelta(hours=5)
    site = checker(tmp_path, reddit, google, clock, folder="the site")
    assert site.load_bundle() == 2
    assert site.check(URL, QUOTE).show and site.check(OTHER_URL, QUOTE).show
    assert len(reddit.asked) == 2  # read on Reddit once each, by the job
    assert google.asked("POST") == [google.asked("POST")[0]]  # only the job wrote


def test_the_bundle_is_read_again_only_when_it_has_changed(tmp_path):
    reddit, google, clock = FakeReddit(), FakeGoogle(), Clock()
    job = checker(tmp_path, reddit, google, clock, folder="the job")
    job.check(URL, QUOTE)
    job.save_bundle()
    site = checker(tmp_path, reddit, google, clock, folder="the site")
    site.load_bundle()
    assert len(google.asked("GET", "alt=media")) == 1
    assert site.load_bundle() == 0  # unchanged: one small question about its generation, no download
    assert len(google.asked("GET", "alt=media")) == 1 and len(google.asked("GET", "fields=generation")) == 2
    job.check(OTHER_URL, QUOTE)
    job.save_bundle()
    assert site.load_bundle() == 1  # changed: downloaded again, and only the new check is written here
    assert len(google.asked("GET", "alt=media")) == 2


def test_a_check_in_the_bundle_older_than_48_hours_is_never_used(tmp_path):
    reddit, google, clock = FakeReddit(), FakeGoogle(), Clock()
    job = checker(tmp_path, reddit, google, clock, folder="the job")
    job.check(URL, QUOTE)
    job.save_bundle()
    clock.now += timedelta(hours=48, minutes=1)  # say the site reads a bundle written long ago
    site = checker(tmp_path, reddit, google, clock, folder="the site")
    assert site.load_bundle() == 0
    assert site.saved_check(URL, QUOTE) is None and site.checked_at(URL) is None
    assert list((tmp_path / "the site").glob("*.json")) == []
    assert site.check(URL, QUOTE).show and len(reddit.asked) == 2  # read on Reddit again


def test_the_sites_own_newer_check_is_kept_over_the_bundles(tmp_path):
    google, clock = FakeGoogle(), Clock()
    job = checker(tmp_path, FakeReddit(), google, clock, folder="the job")
    job.check(URL, QUOTE)
    job.save_bundle()
    clock.now += timedelta(hours=3)
    site = checker(tmp_path, FakeReddit(answer=(200, page("Edit: it broke last week."))), google, clock,
                   folder="the site")
    assert site.check(URL, QUOTE).status == "changed"  # the site read it again since, and it was edited
    assert site.load_bundle() == 0
    assert site.saved_check(URL, QUOTE).status == "changed"


def test_a_bundle_entry_with_a_strange_name_or_shape_is_left_out(tmp_path):
    google, clock = FakeGoogle(), Clock()
    good = checker(tmp_path, FakeReddit(), google, clock, folder="the job")
    good.check(URL, QUOTE)
    good.save_bundle()
    content = google.bundle()
    content["checks"]["../../outside.json"] = {"fetched_at": clock.now.isoformat(), "text": "x"}
    content["checks"]["0" * 32 + ".json"] = {"fetched_at": "yesterday", "text": "x"}
    google.objects[BUNDLE] = (5000, json.dumps(content).encode())
    site = checker(tmp_path, FakeReddit(), google, clock, folder="the site")
    assert site.load_bundle() == 1
    assert {p.name for p in (tmp_path / "the site").iterdir()} == {p.name for p in (tmp_path / "the job").iterdir()}
    assert not (tmp_path / "outside.json").exists()


# --- When Google can't be reached ---

def test_when_the_bucket_cant_be_reached_checks_go_on_with_this_machine_and_reddit(tmp_path, capsys):
    reddit, google, clock = FakeReddit(), FakeGoogle(down=True), Clock()
    live = checker(tmp_path, reddit, google, clock)
    assert live.load_bundle() == 0
    assert live.check(URL, QUOTE).show
    assert live.save_bundle() is None
    calls = len(google.calls)
    assert live.load_bundle() == 0
    assert len(google.calls) == calls  # left alone for a while after failing
    said = capsys.readouterr().err
    assert len(said.splitlines()) == 1 and "bucket" in said  # said once, in one line
    assert "token-" not in said  # the token is never printed


def test_the_token_comes_from_the_metadata_server_and_is_kept_until_it_expires(tmp_path):
    reddit, google, clock = FakeReddit(), FakeGoogle(), Clock()
    live = checker(tmp_path, reddit, google, clock)
    live.check(URL, QUOTE)
    live.save_bundle()
    live.load_bundle()
    assert google.tokens_given == 1
    clock.now += timedelta(hours=1)  # the token lasts an hour: a new one is asked a little before it runs out
    live.load_bundle()
    assert google.tokens_given == 2


def test_a_refused_token_leaves_the_bucket_out(tmp_path):
    reddit, google, clock = FakeReddit(), FakeGoogle(token_status=403), Clock()
    live = checker(tmp_path, reddit, google, clock)
    assert live.check(URL, QUOTE).show
    assert live.save_bundle() is None and live.load_bundle() == 0
    assert google.objects == {} and google.asked("GET") == [] and google.asked("POST") == []


def test_without_a_bucket_there_is_nothing_to_load_or_save(tmp_path):
    live = LiveChecker(cache_dir=tmp_path, fetch=FakeReddit())
    assert live.load_bundle() == 0 and live.save_bundle() is None


# --- Saved checks, whatever their source ---

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
