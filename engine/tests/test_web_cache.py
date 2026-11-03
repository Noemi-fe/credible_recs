"""The search page and the How page can be kept by Firebase Hosting's CDN (3 Nov 2026, built by Claude; the launch-load
fix, DECISIONS.md): in public mode, and only for GET / and GET /how answered 200, the server says "public, max-age=60,
s-maxage=600" instead of "no-store". Everything else keeps no-store: the API, the pairwise test, /ready, every error,
and local mode entirely.

Every text is made up. No test reaches the network: servers listen on 127.0.0.1 (public mode too, pointed there instead
of every network interface), and the kettle library is a made-up one in a temporary folder.
"""

import gzip
import json
import threading
import urllib.error
import urllib.request

import pytest

from engine import web
from engine.tests.test_web import kettle_library

HOST = "demo-credible-recs.example"
PUBLIC = web.Site(public=True, hosts=(HOST,))
COUNTED = web.Site(public=True, hosts=(HOST,), goatcounter="credible-recs")
CACHEABLE = "public, max-age=60, s-maxage=600"


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    """No remembered answers between tests, feedback goes to a list (never to data/feedback), and the server has not
    "got ready", so /ready only says so (asked once ready, it would also start the site's reading ahead)."""

    class Kept:
        records: list = []

        def add(self, record):
            self.records.append(record)

    monkeypatch.setattr(web, "store", Kept())
    monkeypatch.setattr(web, "ready", threading.Event())
    web.clear_answer_cache()
    yield
    web.clear_answer_cache()


def serve(tmp_path, monkeypatch, site):
    monkeypatch.setattr(web, "PUBLIC_HOST", "127.0.0.1")  # the tests never open a port to the network
    server = web.make_server(port=0, library_dir=kettle_library(tmp_path), site=site)
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    return server


@pytest.fixture
def public_server(tmp_path, monkeypatch):
    server = serve(tmp_path, monkeypatch, PUBLIC)
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def local_server(tmp_path, monkeypatch):
    server = serve(tmp_path, monkeypatch, web.LOCAL)
    yield server
    server.shutdown()
    server.server_close()


def fetch(server, path: str, headers: dict | None = None, body=None, method: str | None = None):
    """One request: (status, the response's headers as a message, the body as sent, so gzipped if it was). A public
    server is addressed as its own site, as Firebase Hosting's request names it (the service's host)."""
    data = json.dumps(body).encode("utf-8") if isinstance(body, (dict, list)) else body
    sent = dict(headers or {})
    if data is not None:
        sent.setdefault("Content-Type", "application/json")
    if server.site.public:
        sent.setdefault("Host", HOST)
    request = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}{path}", data=data, headers=sent,
                                     method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, response.headers, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers, error.read()


def plain(headers, body: bytes) -> bytes:
    return gzip.decompress(body) if headers.get("Content-Encoding") == "gzip" else body


# --- The two pages, in public mode ---

@pytest.mark.parametrize("path", ["/", "/how", "/?utm_source=a-link-someone-shared", "/how?x=1"])
def test_the_search_page_and_the_how_page_can_be_kept_by_the_cdn_in_public_mode(public_server, path):
    status, headers, _ = fetch(public_server, path)
    assert status == 200
    assert headers.get_all("Cache-Control") == [CACHEABLE]  # one header, not two
    assert "default-src 'none'" in headers["Content-Security-Policy"]  # the rest of the security headers are unchanged
    assert headers["X-Content-Type-Options"] == "nosniff" and headers["Referrer-Policy"] == "no-referrer"


def test_the_cdn_may_keep_a_page_longer_than_a_browser_does_and_neither_for_long():
    assert web.PAGE_CACHE_CONTROL == CACHEABLE
    directives = dict(part.strip().partition("=")[::2] for part in web.PAGE_CACHE_CONTROL.split(","))
    assert "public" in directives and int(directives["max-age"]) <= int(directives["s-maxage"]) <= 600
    assert int(directives["max-age"]) <= 60


def test_a_page_with_visit_counting_is_cacheable_too(tmp_path, monkeypatch):
    server = serve(tmp_path, monkeypatch, COUNTED)
    try:
        status, headers, body = fetch(server, "/")
        assert status == 200 and headers["Cache-Control"] == CACHEABLE
        assert b"goatcounter" in plain(headers, body)  # counted in the visitor's browser, so a kept page still counts
    finally:
        server.shutdown()
        server.server_close()


# --- Everything else keeps no-store ---

@pytest.mark.parametrize("path, method, body, status", [
    ("/test", "GET", None, 503),           # the pairwise test: no cards in the made-up library, and a visit id of its own
    ("/ready", "GET", None, None),         # Cloud Run's probe (and the keep-warm ping, which does work): 503 until ready
    ("/api/answer", "GET", None, 405),
    ("/api/feedback", "GET", None, 405),
    ("/api/test-response", "GET", None, 405),
    ("/api/answer", "POST", {"request": "electric kettle that lasts 10+ years"}, 200),
    ("/api/answer", "POST", {"request": ""}, 400),
    ("/", "POST", {"x": 1}, 405),
    ("/how", "POST", {"x": 1}, 405),
    ("/how/", "GET", None, 404),           # not /how: a different path, never the page
    ("/index.html", "GET", None, 404),
    ("/nope", "GET", None, 404),
])
def test_every_other_public_response_stays_no_store(public_server, path, method, body, status):
    got, headers, _ = fetch(public_server, path, body=body, method=method)
    if status is not None:
        assert got == status, path
    assert headers.get_all("Cache-Control") == ["no-store"], (path, method)
    assert "public" not in headers["Cache-Control"]


def test_a_page_asked_for_by_the_wrong_host_is_refused_and_never_kept(public_server):
    for path in ("/", "/how"):
        status, headers, _ = fetch(public_server, path, headers={"Host": "evil.example"})
        assert status == 403 and headers.get_all("Cache-Control") == ["no-store"], path


def test_a_rate_limited_answer_is_never_kept(public_server):
    public_server.limits["answers"] = web.RateLimiter(1, 600)
    assert fetch(public_server, "/api/answer", body={"request": ""})[0] == 400  # the one allowed
    status, headers, _ = fetch(public_server, "/api/answer", body={"request": ""})
    assert status == 429 and headers.get_all("Cache-Control") == ["no-store"]


@pytest.mark.parametrize("status", [404, 500, 503, 429])
def test_a_page_that_is_not_a_200_is_never_kept(public_server, monkeypatch, status):
    # If "/" or "/how" ever failed or were closed, the failure must not be held for ten minutes.
    monkeypatch.setattr(web, "handle_request",
                        lambda path, library_dir=None, site=None: (status, web.HTML, b"<p>Not now.</p>"))
    for path in ("/", "/how"):
        got, headers, _ = fetch(public_server, path)
        assert got == status and headers.get_all("Cache-Control") == ["no-store"], path


def test_which_responses_may_be_kept_is_decided_in_one_place():
    for path in ("/", "/how"):
        assert web.cache_control(PUBLIC, path, 200) == CACHEABLE
        assert web.cache_control(COUNTED, path, 200) == CACHEABLE
        assert web.cache_control(PUBLIC, path, 404) == "no-store"
        assert web.cache_control(PUBLIC, path, 500) == "no-store"
        assert web.cache_control(web.LOCAL, path, 200) == "no-store"  # local mode: exactly as before
    for path in ("/test", "/ready", "/api/answer", "/api/feedback", "/api/test-response", "/how/", "/nope", ""):
        assert web.cache_control(PUBLIC, path, 200) == "no-store", path
    assert web.HEADERS["Cache-Control"] == "no-store"  # the default every response starts from is unchanged


# --- Local mode is exactly as before ---

@pytest.mark.parametrize("path", ["/", "/how", "/test", "/ready", "/nope", "/?q=1"])
def test_local_mode_sends_no_store_everywhere(local_server, path):
    _, headers, _ = fetch(local_server, path)
    assert headers.get_all("Cache-Control") == ["no-store"], path


def test_local_mode_sends_the_same_headers_for_the_pages_as_before():
    assert web.security_headers(web.LOCAL) == web.HEADERS


# --- The pages are the same for every visitor ---

VISITORS = [
    {},
    {"Cookie": "__session=abc123; other=1", "Authorization": "Bearer made-up"},
    {"Origin": "https://crediblepicks.com", "Referer": "https://news.example/item?id=1"},
    {"X-Forwarded-For": "203.0.113.7, 10.16.0.1", "X-Country-Code": "US", "Accept-Language": "it-IT,it;q=0.9"},
    {"User-Agent": "a-made-up-browser/1.0", "X-Forwarded-Host": "evil.example", "X-Fh-Requested-Host": "www.example"},
    {"Accept-Encoding": "gzip, deflate, br"},
    {"Accept-Encoding": "gzip"},
]


@pytest.mark.parametrize("path", ["/", "/how"])
def test_the_pages_do_not_depend_on_who_asks_or_what_they_send(public_server, path):
    # The CDN keeps one copy for everybody, so no visitor's cookie, address, country, language, browser, origin or query
    # string may change a byte of either page (decompressed: only the gzip wrapper carries a time).
    _, first_headers, first_body = fetch(public_server, path)
    first = plain(first_headers, first_body)
    assert len(first) > 10_000
    for extra in VISITORS:
        for query in ("", "?a=1", "?a=2&b=%E2%82%AC", "?q=electric+kettle", "?"):
            status, headers, body = fetch(public_server, path + query, headers=extra)
            assert status == 200 and plain(headers, body) == first, (extra, query)
            assert headers["Content-Security-Policy"] == first_headers["Content-Security-Policy"]
            assert headers["Cache-Control"] == CACHEABLE


def test_the_handler_itself_gives_the_same_bytes_for_any_query_string(tmp_path):
    for path in ("/", "/how"):
        assert web.handle_request(path, tmp_path, PUBLIC) == web.handle_request(path + "?x=1&y=%20z", tmp_path, PUBLIC)


@pytest.mark.parametrize("path", ["/", "/how", "/test", "/ready", "/nope", "/api/answer"])
def test_the_site_sets_no_cookies(public_server, path):
    # Hosting passes on only a cookie named __session and (docs) a response that sets one is not a candidate for the
    # CDN; the site sets none, so a visitor's page is never tied to them.
    _, headers, _ = fetch(public_server, path)
    assert headers.get("Set-Cookie") is None


# --- Compressed and plain copies are told apart ---

@pytest.mark.parametrize("path", ["/", "/how"])
def test_the_pages_say_their_copy_depends_on_accept_encoding_whether_or_not_it_was_gzipped(public_server, path):
    # A cache must not give a browser that can't read gzip the compressed copy, nor the other way round. The plain copy
    # (sent to a client that doesn't take gzip) used to say nothing, so a cache could have held it for everyone.
    _, zipped, zipped_body = fetch(public_server, path, headers={"Accept-Encoding": "gzip"})
    _, unzipped, unzipped_body = fetch(public_server, path)
    assert zipped["Content-Encoding"] == "gzip" and zipped["Vary"] == "Accept-Encoding"
    assert unzipped.get("Content-Encoding") is None and unzipped["Vary"] == "Accept-Encoding"
    assert gzip.decompress(zipped_body) == unzipped_body


def test_a_small_response_is_not_compressed_and_says_nothing_about_encoding(public_server):
    # Unchanged: an error is never worth compressing, so its bytes don't depend on Accept-Encoding.
    _, headers, _ = fetch(public_server, "/api/answer", headers={"Accept-Encoding": "gzip"}, body={"request": ""})
    assert headers.get("Content-Encoding") is None and headers.get("Vary") is None


# --- HEAD ---

@pytest.mark.parametrize("which", ["public_server", "local_server"])
@pytest.mark.parametrize("path", ["/", "/how", "/nope"])
def test_a_head_request_is_not_served_and_is_never_marked_cacheable(request, which, path):
    # The server answers GET and POST only (BaseHTTPRequestHandler's own 501 for anything else, with no body). It
    # stays so: a HEAD never gets the pages' public header, so it can't make the CDN keep anything.
    server = request.getfixturevalue(which)
    status, headers, body = fetch(server, path, method="HEAD")
    assert status == 501 and body == b""
    assert "public" not in (headers.get("Cache-Control") or "")
