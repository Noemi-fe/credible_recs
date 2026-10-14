"""The private bucket's client (engine.live_check.Bucket), as on-demand reading needs it (14 Oct 2026): objects under a
folder of their own, writes that never lose another writer's change (Cloud Storage's ifGenerationMatch: the site adds
requests to the queue while the reading job marks them done), and an access token from gcloud on Noemi's computer,
where there is no Cloud Run metadata server. Every call goes to a made-up stand-in: no test reaches the network.
"""

from engine.live_check import BUCKET_PREFIX, Bucket
from engine.tests.fake_google import FakeGoogle

NAME = "credible-test-on-demand"


def bucket(google, **settings) -> Bucket:
    return Bucket(NAME, request=google, clock=lambda: 0.0, **settings)


def test_a_bucket_keeps_its_objects_in_its_own_folder():
    google = FakeGoogle()
    assert bucket(google, prefix="on_demand/").put("queue.json", b"{}")
    assert (NAME, "on_demand/queue.json") in google.objects
    assert bucket(google).put("bundle.json", b"{}")  # the live checks' folder stays the default
    assert (NAME, BUCKET_PREFIX + "bundle.json") in google.objects


def test_a_write_that_asks_for_a_generation_saves_only_over_that_version():
    google = FakeGoogle()
    store = bucket(google, prefix="on_demand/")
    first = store.put_if("queue.json", b'{"n": 1}', None)  # None: only if there is no such object yet
    assert first is not None and first != Bucket.CHANGED and store.generation("queue.json") == first
    assert store.put_if("queue.json", b'{"n": 2}', None) == Bucket.CHANGED  # it exists now: not saved
    second = store.put_if("queue.json", b'{"n": 2}', first)
    assert second not in (None, Bucket.CHANGED, first)
    assert store.put_if("queue.json", b'{"n": 3}', first) == Bucket.CHANGED  # another writer saved since
    assert google.read(NAME, "on_demand/queue.json") == {"n": 2}
    assert store.problems == 0  # a version that moved on is an answer, not a failure: the bucket isn't rested


def test_a_write_that_fails_says_so_and_the_bucket_is_rested():
    google = FakeGoogle(down=True)
    store = bucket(google, prefix="on_demand/")
    assert store.put_if("queue.json", b"{}", None) is None
    assert store.problems == 1


def test_on_noemis_computer_the_token_comes_from_gcloud_not_the_metadata_server():
    google = FakeGoogle()
    asked = []

    def from_gcloud():
        asked.append(1)
        return "token-from-gcloud", 3000.0

    store = bucket(google, prefix="on_demand/", token=from_gcloud)
    assert store.put("queue.json", b"{}") and store.get("queue.json") == b"{}"
    assert len(asked) == 1  # kept until shortly before it runs out
    assert not [url for _, url in google.calls if "metadata" in url]


def test_the_same_token_serves_other_calls_to_google():
    google = FakeGoogle()
    store = bucket(google)
    assert store.access_token() == "token-1" and store.access_token() == "token-1"
    assert len([url for _, url in google.calls if "metadata" in url]) == 1
