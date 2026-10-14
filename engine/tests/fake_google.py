"""A made-up stand-in for the Google services on-demand reading talks to (14 Oct 2026), so no test reaches the network:
Cloud Run's metadata server (an access token), Cloud Storage's JSON API (buckets whose objects have generations, a
number that changes with every write, and writes that can ask for a generation first: ifGenerationMatch), and the
Cloud Run Admin API's call that starts a job (jobs:run). Every call is remembered, for the tests to count.
"""

import json
from urllib.parse import parse_qs, unquote, urlsplit

from engine.live_check import METADATA_TOKEN_URL

RUN_API = "https://run.googleapis.com/v2/"


class FakeGoogle:
    def __init__(self, buckets=("credible-test-on-demand",), down=False):
        self.buckets = set(buckets)
        self.down = down  # every call times out, as when Google can't be reached
        self.objects: dict[tuple[str, str], tuple[int, bytes]] = {}  # (bucket, name) -> (generation, content)
        self.calls: list[tuple[str, str]] = []
        self.jobs_started: list[str] = []
        self.job_status = 200  # what starting a job answers (403: the account may not start it)
        self.before_write = None  # called before the next write is applied: a test makes another writer win the race
        self.before_writing: dict[str, object] = {}  # the same, before the next write of one object (by its name)
        self._generation = 1000

    def __call__(self, method, url, headers, body=None, timeout=None):
        self.calls.append((method, url))
        if self.down:
            raise TimeoutError("timed out")
        if url == METADATA_TOKEN_URL:
            assert headers.get("Metadata-Flavor") == "Google"
            return 200, json.dumps({"access_token": "token-1", "expires_in": 3599, "token_type": "Bearer"}).encode()
        assert headers.get("Authorization", "").startswith("Bearer "), "every call to Google carries the token"
        if url.startswith(RUN_API):
            assert method == "POST" and url.endswith(":run")
            if self.job_status == 200:
                self.jobs_started.append(url[len(RUN_API):-len(":run")])
            return self.job_status, b"{}"
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        if method == "GET":
            assert parts.path.startswith("/storage/v1/b/")
            bucket, _, name = parts.path[len("/storage/v1/b/"):].partition("/o/")
            if bucket not in self.buckets:
                return 404, b'{"error": "no such bucket"}'
            found = self.objects.get((bucket, unquote(name)))
            if found is None:
                return 404, b'{"error": "not found"}'
            generation, content = found
            if query == {"fields": ["generation"]}:
                return 200, json.dumps({"generation": str(generation)}).encode()
            assert query["alt"] == ["media"]
            if "generation" in query and query["generation"] != [str(generation)]:
                return 404, b'{"error": "no such generation"}'
            return 200, content
        if method == "POST":
            assert parts.path.startswith("/upload/storage/v1/b/") and query["uploadType"] == ["media"]
            bucket = parts.path[len("/upload/storage/v1/b/"):].removesuffix("/o")
            if bucket not in self.buckets:
                return 404, b'{"error": "no such bucket"}'
            name = query["name"][0]
            if self.before_write is not None:
                hook, self.before_write = self.before_write, None
                hook()
            if name in self.before_writing:
                self.before_writing.pop(name)()
            if "ifGenerationMatch" in query:
                wanted = query["ifGenerationMatch"][0]
                now = str(self.objects[(bucket, name)][0]) if (bucket, name) in self.objects else "0"
                if wanted != now:
                    return 412, b'{"error": "conditionNotMet"}'
            self._generation += 1
            self.objects[(bucket, name)] = (self._generation, body)
            return 200, json.dumps({"name": name, "generation": str(self._generation)}).encode()
        raise AssertionError(f"unexpected call {method} {url}")

    # --- For the tests ---

    def put(self, bucket: str, name: str, content: bytes) -> None:
        """An object written by someone else (another program, or a test setting the scene)."""
        self._generation += 1
        self.objects[(bucket, name)] = (self._generation, content)

    def read(self, bucket: str, name: str):
        """An object's content as JSON, or None when there is none."""
        found = self.objects.get((bucket, name))
        return None if found is None else json.loads(found[1])

    def asked(self, method: str, what: str = "") -> list[str]:
        return [url for m, url in self.calls if m == method and url != METADATA_TOKEN_URL and what in url]
