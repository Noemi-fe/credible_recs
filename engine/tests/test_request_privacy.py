"""What a visitor types never sits in an address (Noemi's decision 5 of 16 Oct 2026).

Google Cloud Run's request log keeps every request's address (with its query string), the visitor's IP address and
browser for 30 days. Until 16 Oct 2026 the page asked GET /api/answer?q=<request>, so the log held every request people
typed. Now the page sends the request in the JSON body of a POST to /api/answer, which no request log keeps, and GET
/api/answer says how to ask instead. The answer itself is unchanged.

Every request here is made up; servers listen on 127.0.0.1 and nothing reaches the network.
"""

import io
import json
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from engine import web
from engine.config import WEB_MAX_REQUEST_CHARS
from engine.tests.test_web import REQUEST, kettle_library, page, post_answer

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def fresh_cache():
    web.clear_answer_cache()
    yield
    web.clear_answer_cache()


# --- The page ---

def _script(html: str) -> str:
    return re.search(r'<script>\n/\* How this page works.*?</script>', html, re.DOTALL).group(0)


def test_the_page_sends_the_request_in_a_post_body_never_in_an_address(tmp_path):
    script = _script(page(tmp_path))
    assert "/api/answer?" not in script and "?q=" not in re.sub(r"/\*.*?\*/|//[^\n]*", "", script, flags=re.DOTALL)
    # Every call the page makes goes to a fixed address of this site, with nothing added to it.
    calls = re.findall(r"fetch\(([^,)]*)", script)
    assert sorted(set(calls)) == ['"/api/answer"', '"/api/feedback"']
    asking = re.search(r'fetch\("/api/answer", \{(.*?)\}\);', script, re.DOTALL).group(1)
    assert 'method: "POST"' in asking and '"Content-Type": "application/json"' in asking
    # Changed on purpose 25 Oct 2026 (Noemi, 24 Oct: the region choice, "never sent anywhere except with the request"): the
    # body also holds the visitor's region, one of the select's three values; the address still holds nothing. Was:
    # "body: JSON.stringify({ request })".
    assert "body: JSON.stringify({ request, region })" in asking
    assert "const region = regionBox.value;" in script


def test_the_address_bar_and_the_copied_link_keep_the_request_after_the_hash_only(tmp_path):
    # The request stays after "#q=", which browsers never send anywhere (11 Oct 2026); the copied link is that address.
    script = _script(page(tmp_path))
    code = re.sub(r"/\*.*?\*/|//[^\n]*", "", script, flags=re.DOTALL)
    for change in re.findall(r"history\.(?:pushState|replaceState)\(([^;]*)\);", code):
        assert '"#q="' in change and '"?q="' not in change, change
    assert "writeText(location.href)" in code


# --- The server ---

def test_the_answer_comes_from_a_post_with_the_request_in_its_json_body(tmp_path):
    status, content_type, body = post_answer(REQUEST, kettle_library(tmp_path))
    data = json.loads(body)
    assert status == 200 and content_type.startswith("application/json")
    # The same shape as GET /api/answer?q= gave until 16 Oct 2026.
    assert set(data) == {"query", "answer", "threads_used", "left_out", "reading", "timing"}
    assert data["query"]["product_type"] == "electric kettle" and len(data["answer"]["picks"]) == 3


def test_a_get_with_the_request_in_its_address_is_never_answered_and_says_how_to_ask(tmp_path, monkeypatch):
    def never(*args, **kwargs):
        raise AssertionError("no answer is worked out for a request sent in an address")

    monkeypatch.setattr(web, "answer_request", never)
    library = kettle_library(tmp_path)
    for path in ("/api/answer?q=kettle", "/api/answer"):
        status, content_type, body = web.handle_request(path, library)
        error = json.loads(body)
        assert status == 405 and content_type.startswith("application/json")
        assert error["code"] == "method_not_allowed"
        assert "POST /api/answer" in error["error"] and '{"request": "..."}' in error["error"]
        assert "kettle" not in error["error"]


@pytest.mark.parametrize("sent, code", [
    ([1, 2], "bad_body"), ('"kettle"', "bad_body"), ({"request": 5}, "bad_body"), ({"request": None}, "bad_body"),
    (b"{not json", "bad_json"), (b'{"request": "a", "request": "b"}', "bad_json"), (b"\xff\xfe", "bad_json"),
])
def test_a_body_that_isnt_a_request_is_refused_with_its_reason(tmp_path, sent, code):
    body = sent if isinstance(sent, bytes) else (sent if isinstance(sent, str) else json.dumps(sent)).encode()
    status, _, response = web.handle_answer("application/json", str(len(body)), io.BytesIO(body).read,
                                            kettle_library(tmp_path))
    assert status == 400 and json.loads(response)["code"] == code


def test_a_body_too_large_for_any_request_is_never_read(tmp_path):
    def never_read(size):
        raise AssertionError("the body should not have been read")

    library = kettle_library(tmp_path)
    status, _, response = web.handle_answer("application/json", str(web.ANSWER_MAX_BODY_BYTES + 1), never_read, library)
    assert status == 413 and json.loads(response)["code"] == "too_large"
    for content_type in (None, "text/plain", "application/x-www-form-urlencoded"):
        refused = web.handle_answer(content_type, "20", never_read, library)
        assert refused[0] == 415 and json.loads(refused[2])["code"] == "not_json"
    assert web.handle_answer("application/json", None, never_read, library)[0] == 411
    assert web.handle_answer("application/json", "ten", never_read, library)[0] == 400


def test_the_longest_request_fits_the_body_however_it_is_written(tmp_path):
    # JSON may write each character as a \u escape: 6 bytes, or 12 for one outside the Basic Multilingual Plane.
    longest = "kettle " + "\U0001F375" * (WEB_MAX_REQUEST_CHARS - 7)
    assert len(longest) == WEB_MAX_REQUEST_CHARS
    body = json.dumps({"request": longest}, ensure_ascii=True).encode()
    assert len(body) <= web.ANSWER_MAX_BODY_BYTES
    library = kettle_library(tmp_path)
    status, _, response = web.handle_answer("application/json", str(len(body)), io.BytesIO(body).read, library)
    assert status == 200, json.loads(response)
    longer = json.dumps({"request": longest + "x"}).encode()
    refused = web.handle_answer("application/json", str(len(longer)), io.BytesIO(longer).read, library)
    assert refused[0] == 400 and json.loads(refused[2])["code"] == "request_too_long"  # as before


# --- Over HTTP ---

def test_over_http_the_post_is_answered_and_the_get_refused_with_its_allow_header(tmp_path):
    server = web.make_server(port=0, library_dir=kettle_library(tmp_path))
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        asked = urllib.request.Request(f"{base}/api/answer", data=json.dumps({"request": REQUEST}).encode(),
                                       headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(asked, timeout=20) as response:
            assert response.status == 200 and len(json.loads(response.read())["answer"]["picks"]) == 3
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(f"{base}/api/answer?q=kettle", timeout=20)
        assert refused.value.code == 405 and refused.value.headers["Allow"] == "POST"
    finally:
        server.shutdown()
        server.server_close()


# --- What else calls the site ---

def test_the_live_latency_script_asks_with_a_post_body():
    import importlib.util

    spec = importlib.util.spec_from_file_location("live_latency", ROOT / "eval" / "live_latency.py")
    live_latency = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(live_latency)
    asked = live_latency.answer_request_for("https://example.test", "kettle that lasts")
    assert asked.full_url == "https://example.test/api/answer" and asked.get_method() == "POST"
    assert json.loads(asked.data) == {"request": "kettle that lasts"}
    assert asked.get_header("Content-type") == "application/json"
