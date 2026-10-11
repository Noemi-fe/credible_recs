"""Going live (Noemi, 11 Oct 2026): the feedback route, public mode, rate limits, GoatCounter, and the page's feedback
form and "First time here?" question (engine/web.py, engine/templates/search.html). Local mode's own tests are in
test_web.py, unchanged.

Every text is made up. No test reaches the network: servers listen on 127.0.0.1 (the public mode too, pointed there
instead of every network interface), and feedback goes to a fake store.
"""

import io
import json
import re
import threading
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

import pytest

from engine import feedback, pipeline, web
from engine.config import (FEEDBACK_MAX_BODY_BYTES, FEEDBACK_MAX_COMMENT_CHARS, FEEDBACK_MAX_PRODUCT_TYPE_CHARS,
                           RATE_LIMIT_ANSWERS, RATE_LIMIT_FEEDBACK, RATE_LIMIT_WINDOW_SECONDS, WEB_MAX_REQUEST_CHARS)
from engine.tests.test_web import REQUEST, kettle_library

USEFUL = {"kind": "answer_feedback", "request": "electric kettle that lasts 10+ years", "verdict": "useful",
          "comment": "Clear and quick, thanks.", "product_type": "electric kettle", "status": "ok"}
HOST = "demo-credible-recs.hf.space"
PUBLIC = web.Site(public=True, hosts=(HOST,))
COUNTED = web.Site(goatcounter="credible-recs")


class FakeStore:
    """Keeps records in a list, or refuses them all (fail=True)."""

    def __init__(self, fail: bool = False):
        self.records: list[dict] = []
        self.fail = fail

    def add(self, record: dict) -> None:
        if self.fail:
            raise feedback.StoreFull("too much waiting")
        self.records.append(record)

    def close(self) -> None:
        pass

    def describe(self) -> str:
        return "kept by the test"


@pytest.fixture(autouse=True)
def fake_store(monkeypatch):
    """Every test's feedback goes to a fake store, never to data/feedback; and no answer is remembered between tests."""
    store = FakeStore()
    monkeypatch.setattr(web, "store", store)
    web.clear_answer_cache()
    yield store
    web.clear_answer_cache()


def post(body) -> tuple[int, str, dict]:
    """POST /api/feedback's work, once the request is known to come from the site's own page."""
    data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
    status, content_type, response = web.handle_feedback("application/json", str(len(data)), io.BytesIO(data).read)
    return status, content_type, json.loads(response)


def never_read(size: int) -> bytes:
    raise AssertionError("the body should not have been read")


# --- POST /api/feedback: what is kept ---

def test_feedback_on_an_answer_is_kept_with_its_time_and_nothing_about_the_sender(fake_store):
    status, content_type, data = post(USEFUL)
    assert status == 200 and content_type.startswith("application/json") and data == {"saved": True}
    (record,) = fake_store.records
    assert set(record) == set(USEFUL) | {"received_at"}
    assert {key: value for key, value in record.items() if key != "received_at"} == USEFUL


def test_a_first_time_answer_is_kept(fake_store):
    assert post({"kind": "first_time", "answer": "no"})[0] == 200
    assert [record["answer"] for record in fake_store.records] == ["no"]


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded",
                                          "multipart/form-data; boundary=x", "", None])
def test_feedback_must_be_json(fake_store, content_type):
    # A form on another website can only send these kinds, so this alone stops it.
    status, _, body = web.handle_feedback(content_type, "20", never_read)
    assert status == 415 and json.loads(body)["code"] == "not_json" and fake_store.records == []


@pytest.mark.parametrize("content_type", ["application/json; charset=utf-8", "Application/JSON"])
def test_json_named_another_way_is_fine(fake_store, content_type):
    data = json.dumps(USEFUL).encode()
    assert web.handle_feedback(content_type, str(len(data)), io.BytesIO(data).read)[0] == 200


def test_feedback_without_its_length_is_refused(fake_store):
    status, _, body = web.handle_feedback("application/json", None, never_read)
    assert status == 411 and json.loads(body)["code"] == "length_required"


@pytest.mark.parametrize("length", ["abc", "-1", "1e3", "12 34", "9" * 40, "١٢"])
def test_a_length_that_isnt_a_plain_number_is_refused(fake_store, length):
    status, _, body = web.handle_feedback("application/json", length, never_read)
    assert status == 400 and json.loads(body)["code"] == "bad_length"


def test_feedback_over_the_size_limit_is_refused_before_it_is_read(fake_store):
    status, _, body = web.handle_feedback("application/json", str(FEEDBACK_MAX_BODY_BYTES + 1), never_read)
    assert status == 413 and json.loads(body)["code"] == "too_large"
    assert FEEDBACK_MAX_BODY_BYTES <= 16 * 1024  # "a few KB"


def test_the_longest_real_feedback_fits_the_size_limit(fake_store):
    longest = {**USEFUL, "request": "長" * WEB_MAX_REQUEST_CHARS, "comment": "長" * FEEDBACK_MAX_COMMENT_CHARS,
               "product_type": "長" * FEEDBACK_MAX_PRODUCT_TYPE_CHARS}  # every text at its limit, three bytes a letter
    data = json.dumps(longest, ensure_ascii=False).encode("utf-8")
    assert len(data) <= FEEDBACK_MAX_BODY_BYTES and post(data)[0] == 200


@pytest.mark.parametrize("body", [b"{not json", b"\xff\xfe\x00", b"",
                                  b'{"kind": "first_time", "answer": "yes", "answer": "no"}'],
                         ids=["broken", "not utf-8", "empty", "a name twice"])
def test_a_body_that_isnt_one_clean_json_value_is_refused(fake_store, body):
    status, _, data = post(body)
    assert status == 400 and data["code"] == "bad_json" and fake_store.records == []


def test_json_nested_as_deep_as_the_size_limit_allows_is_refused_without_harm(fake_store):
    depth = FEEDBACK_MAX_BODY_BYTES // 2
    status, _, data = post(b"[" * depth + b"]" * depth)
    assert status == 400 and data["code"] in ("bad_json", "bad_feedback") and fake_store.records == []


@pytest.mark.parametrize("sent", [{**USEFUL, "ip": "203.0.113.7"}, {**USEFUL, "verdict": "great"}, [USEFUL],
                                  {"kind": "first_time", "answer": "maybe"},
                                  {**USEFUL, "comment": "c" * (FEEDBACK_MAX_COMMENT_CHARS + 1)}])
def test_feedback_that_breaks_a_rule_is_refused_with_its_reason(fake_store, sent):
    status, _, data = post(sent)
    assert status == 400 and data["code"] == "bad_feedback" and data["error"]
    assert fake_store.records == []


@pytest.mark.parametrize("store", [FakeStore(fail=True), None])
def test_feedback_that_cant_be_kept_right_now_says_so(monkeypatch, store):
    monkeypatch.setattr(web, "store", store)
    status, _, data = post(USEFUL)
    assert status == 503 and data["code"] == "feedback_unavailable"


def test_a_remembered_answer_comes_back_at_once_while_a_new_one_is_worked_out(tmp_path, monkeypatch):
    # On the public site a new answer can take a minute (every quote is checked live on Reddit, a few seconds apart).
    # Answers are still worked out one at a time, but one already remembered never waits behind it.
    library_dir = kettle_library(tmp_path)
    assert web.handle_request(f"/api/answer?q={quote(REQUEST)}", library_dir)[0] == 200  # remembered
    started, release = threading.Event(), threading.Event()

    def slow(request, library_dir):
        started.set()
        release.wait(10)
        return pipeline.answer_request(request, library_dir)

    monkeypatch.setattr(web, "answer_request", slow)
    worker = threading.Thread(target=web.answer_response, args=("kettle that lasts forever", library_dir))
    worker.start()
    try:
        assert started.wait(10)
        done = []
        reader = threading.Thread(target=lambda: done.append(web.answer_response(REQUEST, library_dir)))
        reader.start()
        reader.join(2)
        assert done and done[0][0] == 200  # it didn't wait for the slow answer
    finally:
        release.set()
        worker.join(10)


def test_feedback_about_the_longest_product_type_module_1_can_give_is_kept(fake_store):
    # Module 1 can take a product type from the request's own words, so it is never longer than a request.
    assert FEEDBACK_MAX_PRODUCT_TYPE_CHARS >= WEB_MAX_REQUEST_CHARS
    assert post({**USEFUL, "product_type": "p" * WEB_MAX_REQUEST_CHARS})[0] == 200


def test_feedback_is_sent_with_post_only(tmp_path):
    status, _, body = web.handle_request("/api/feedback", tmp_path)
    assert status == 405 and json.loads(body)["code"] == "method_not_allowed"


# --- Over HTTP, on this computer (local mode) ---

def start(server):
    """Serves in the background, looking for the stop signal every 10 ms so a test ends without waiting."""
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    return server


def stop(server):
    server.shutdown()
    server.server_close()


@pytest.fixture
def local_server(tmp_path):
    server = start(web.make_server(port=0, library_dir=kettle_library(tmp_path)))
    yield server
    stop(server)


def send(server, path: str, body=None, headers: dict | None = None, method: str | None = None) -> tuple[int, dict, dict]:
    """One request to a test server: (status, response headers, JSON body)."""
    data = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
    request = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}{path}", data=data,
                                     headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, dict(response.headers), json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), json.loads(error.read())


def own_origin(server) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}"


def test_the_local_page_can_send_feedback(local_server, fake_store):
    status, _, data = send(local_server, "/api/feedback", USEFUL,
                           {"Content-Type": "application/json", "Origin": own_origin(local_server)})
    assert status == 200 and data == {"saved": True} and len(fake_store.records) == 1


def test_a_browser_that_sends_only_the_pages_address_can_send_feedback(local_server, fake_store):
    referer = f"http://localhost:{local_server.server_address[1]}/"
    status, _, _ = send(local_server, "/api/feedback", USEFUL, {"Content-Type": "application/json", "Referer": referer})
    assert status == 200 and len(fake_store.records) == 1


@pytest.mark.parametrize("headers", [{}, {"Origin": "https://evil.example"}, {"Origin": "null"},
                                     {"Referer": "https://evil.example/kettles"}, {"Origin": "http://localhost:1"},
                                     {"Origin": "https://evil.example", "Referer": "http://127.0.0.1/"}])
def test_feedback_from_another_website_or_from_nowhere_is_refused(local_server, fake_store, headers):
    status, _, data = send(local_server, "/api/feedback", USEFUL, {"Content-Type": "application/json", **headers})
    assert status == 403 and data["code"] == "cross_site" and fake_store.records == []


def test_feedback_addressed_to_another_host_is_refused(local_server, fake_store):
    headers = {"Content-Type": "application/json", "Host": "evil.example", "Origin": "http://evil.example"}
    status, _, data = send(local_server, "/api/feedback", USEFUL, headers)
    assert status == 403 and data["code"] == "wrong_host" and fake_store.records == []


@pytest.mark.parametrize("path, status, allow", [("/", 405, "GET"), ("/api/answer", 405, "GET"), ("/nope", 404, None)])
def test_a_post_anywhere_else_is_not_allowed_or_not_found(local_server, path, status, allow):
    got, headers, data = send(local_server, path, USEFUL,
                              {"Content-Type": "application/json", "Origin": own_origin(local_server)})
    assert got == status and data["code"] == ("method_not_allowed" if allow else "not_found")
    assert headers.get("Allow") == allow


def test_local_mode_has_no_rate_limit(local_server):
    local_server.limits["answers"] = web.RateLimiter(1, 600)  # even a tiny limit is never applied here
    assert [send(local_server, "/api/answer?q=")[0] for _ in range(3)] == [400, 400, 400]


def test_the_local_security_policy_is_unchanged():
    assert web.security_headers(web.LOCAL) == web.HEADERS
    assert "frame-ancestors 'none'" in web.HEADERS["Content-Security-Policy"]


# --- Public mode: the Hugging Face Space ---

def test_public_mode_listens_on_every_interface_and_local_mode_on_this_computer_only():
    assert web.listen_address(PUBLIC) == "0.0.0.0"  # the Space's proxy reaches the server from outside its container
    assert web.listen_address(web.LOCAL) == "127.0.0.1"


def test_public_mode_never_starts_without_the_hosts_it_answers_for(tmp_path):
    with pytest.raises(ValueError):
        web.make_server(port=0, library_dir=tmp_path, site=web.Site(public=True))


@pytest.fixture
def public_server(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "PUBLIC_HOST", "127.0.0.1")  # the tests never open a port to the network
    server = start(web.make_server(port=0, library_dir=kettle_library(tmp_path), site=PUBLIC))
    yield server
    stop(server)


def public_send(server, path: str, body=None, client: str = "203.0.113.7", headers: dict | None = None):
    """A request as the Space's proxy passes it on: addressed to the Space, naming the visitor's address first."""
    return send(server, path, body, {"Host": HOST, "X-Forwarded-For": f"{client}, 10.16.0.1", **(headers or {})})


@pytest.mark.parametrize("host", [HOST, HOST + ":443", HOST.upper()])
def test_public_mode_answers_requests_for_its_own_host(public_server, host):
    status, _, data = public_send(public_server, f"/api/answer?q={quote(REQUEST)}", headers={"Host": host})
    assert status == 200 and len(data["answer"]["picks"]) == 3


@pytest.mark.parametrize("host", ["evil.example", "127.0.0.1:{port}", "localhost:{port}", ""])
def test_public_mode_refuses_any_other_host(public_server, host):
    host = host.format(port=public_server.server_address[1])
    status, _, data = public_send(public_server, "/api/answer?q=kettle", headers={"Host": host})
    assert status == 403 and data["code"] == "wrong_host"
    assert "127.0.0.1" not in data["error"]  # the public site's own words


def test_a_refused_host_is_named_once_in_the_servers_window_so_the_list_can_be_fixed(public_server, capfd):
    for _ in range(3):
        public_send(public_server, "/api/answer?q=kettle", headers={"Host": "internal-proxy.example:7860"})
    said = capfd.readouterr().err
    assert said.count("internal-proxy.example:7860") == 1 and "CREDIBLE_RECS_ALLOWED_HOSTS" in said
    assert "203.0.113.7" not in said  # never who sent it


def test_public_feedback_must_come_from_the_sites_own_page(public_server, fake_store):
    headers = {"Content-Type": "application/json", "Origin": f"https://{HOST}"}
    assert public_send(public_server, "/api/feedback", USEFUL, headers=headers)[0] == 200
    headers["Origin"] = "https://evil.example"
    assert public_send(public_server, "/api/feedback", USEFUL, headers=headers)[0] == 403
    assert len(fake_store.records) == 1


def test_each_visitor_may_ask_only_so_many_answers_in_a_while(public_server):
    public_server.limits["answers"] = web.RateLimiter(2, 600)
    assert [public_send(public_server, "/api/answer?q=")[0] for _ in range(2)] == [400, 400]  # refused or not, it counts
    status, headers, data = public_send(public_server, "/api/answer?q=")
    assert status == 429 and data["code"] == "too_many_requests" and int(headers["Retry-After"]) > 0
    assert public_send(public_server, "/api/answer?q=", client="198.51.100.4")[0] == 400  # another visitor isn't held up


def test_pages_are_never_rate_limited(public_server):
    public_server.limits["answers"] = web.RateLimiter(1, 600)
    for _ in range(3):
        request = urllib.request.Request(f"http://127.0.0.1:{public_server.server_address[1]}/",
                                         headers={"Host": HOST, "X-Forwarded-For": "203.0.113.7"})
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.status == 200


def test_feedback_has_its_own_tighter_limit(public_server, fake_store):
    assert RATE_LIMIT_FEEDBACK < RATE_LIMIT_ANSWERS and RATE_LIMIT_WINDOW_SECONDS >= 60
    public_server.limits["feedback"] = web.RateLimiter(1, 600)
    headers = {"Content-Type": "application/json", "Origin": f"https://{HOST}"}
    assert public_send(public_server, "/api/feedback", USEFUL, headers=headers)[0] == 200
    status, _, data = public_send(public_server, "/api/feedback", USEFUL, headers=headers)
    assert status == 429 and data["code"] == "too_many_requests" and len(fake_store.records) == 1


def test_the_visitor_is_the_last_public_address_the_proxy_names():
    # Changed by the orchestrator at merge (11 Oct 2026): a visitor can write made-up addresses into X-Forwarded-For,
    # but only in front of the one the Space's proxy adds, so the last public address is the visitor's own; the first
    # could be changed on every request to get round the rate limit. Proxies' own private addresses are skipped.
    assert web.client_address("8.8.4.4, 10.16.0.1", "10.16.0.2") == "8.8.4.4"
    assert web.client_address("1.1.1.1, 8.8.4.4, 10.16.0.1", "10.16.0.2") == "8.8.4.4"  # the made-up 1.1.1.1 is ignored
    assert web.client_address(" 8.8.4.4 ", "10.16.0.2") == "8.8.4.4"
    assert web.client_address("2001:4860:4860::8888, 10.16.0.1", "10.16.0.2") == "2001:4860:4860::8888"
    assert web.client_address(None, "10.16.0.2") == "10.16.0.2"
    assert web.client_address("  , ", "10.16.0.2") == "10.16.0.2"
    assert len(web.client_address("x" * 5000, "10.16.0.2")) <= 100  # a made-up header can't fill memory
    assert len(web.client_address("8.8.4.4," * 5000, "10.16.0.2")) <= 100


def test_public_mode_keeps_no_log_of_addresses_or_requests(public_server, capfd):
    public_send(public_server, "/api/answer?q=kettle%20for%20my%20flat")
    captured = capfd.readouterr()
    assert "203.0.113.7" not in captured.err + captured.out and "for my flat" not in captured.err + captured.out


def test_the_public_site_can_be_shown_inside_its_page_on_huggingface(public_server):
    request = urllib.request.Request(f"http://127.0.0.1:{public_server.server_address[1]}/", headers={"Host": HOST})
    with urllib.request.urlopen(request, timeout=10) as response:
        policy = response.headers["Content-Security-Policy"]
    assert "frame-ancestors https://huggingface.co" in policy and "default-src 'none'" in policy


# --- The rate limit itself ---

def test_the_rate_limit_is_a_sliding_window_for_each_visitor():
    now = [0.0]
    limiter = web.RateLimiter(2, 60, clock=lambda: now[0])
    assert limiter.wait("a") == 0
    now[0] = 1
    assert limiter.wait("a") == 0
    assert limiter.wait("a") == 59  # its first request (at 0 s) leaves the window at 60 s
    assert limiter.wait("b") == 0  # each visitor has a window of their own
    now[0] = 30.5
    assert limiter.wait("a") == 30  # 29.5 seconds, rounded up to whole seconds
    now[0] = 60
    assert limiter.wait("a") == 0  # the first request has left the window
    assert limiter.wait("a") == 1  # the second (at 1 s) leaves it at 61 s


def test_the_rate_limit_forgets_the_visitors_seen_least_recently_beyond_its_size():
    limiter = web.RateLimiter(1, 60, clock=lambda: 0.0, max_clients=3)
    for client in "abcd":
        assert limiter.wait(client) == 0
    assert limiter.wait("d") == 60  # still remembered
    assert limiter.wait("a") == 0  # forgotten, to keep memory bounded
    assert len(limiter) == 3


# --- Starting the public site from the command line ---

def test_public_mode_refuses_to_start_without_its_hosts(monkeypatch, capsys):
    monkeypatch.delenv("CREDIBLE_RECS_ALLOWED_HOSTS", raising=False)
    monkeypatch.setattr(web, "serve", lambda *args, **kwargs: pytest.fail("the server should not start"))
    assert web.main(["--public", "--port", "7860"]) == 2
    assert "CREDIBLE_RECS_ALLOWED_HOSTS" in capsys.readouterr().err


def test_public_mode_starts_with_the_hosts_and_the_counter_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("CREDIBLE_RECS_ALLOWED_HOSTS", f"https://{HOST}/, Demo.Example ")
    monkeypatch.setenv("CREDIBLE_RECS_GOATCOUNTER", "credible-recs")
    monkeypatch.delenv("CREDIBLE_RECS_FEEDBACK_REPO", raising=False)
    for name in ("profiles", "live"):
        monkeypatch.setattr(web, name, None)  # main sets them; restored after the test
    monkeypatch.setattr(pipeline, "cached_profiles", lambda: None)
    monkeypatch.setattr(pipeline, "live_checker", lambda: None)
    started = []
    monkeypatch.setattr(web, "serve", lambda port, library_dir, site: started.append((port, site)))
    assert web.main(["--public", "--port", "7860", "--library", str(tmp_path)]) == 0
    assert started == [(7860, web.Site(public=True, hosts=(HOST, "demo.example"), goatcounter="credible-recs"))]
    assert isinstance(web.store, feedback.LocalStore)


@pytest.mark.parametrize("value, hosts", [(HOST, (HOST,)), (f" {HOST} ,demo.example", (HOST, "demo.example")),
                                          (f"https://{HOST}/", (HOST,)), (f"{HOST}:443", (HOST,)),
                                          (f"{HOST},{HOST.upper()}", (HOST,))])
def test_the_allowed_hosts_are_read_kindly(value, hosts):
    assert web.allowed_hosts(value) == hosts


@pytest.mark.parametrize("value", ["", " , ", "*", "*.hf.space", "evil example", "<script>"])
def test_allowed_hosts_that_name_no_host_stop_the_public_site(value):
    site, problems = web.site_from_env({"CREDIBLE_RECS_ALLOWED_HOSTS": value}, public=True)
    assert site is None and problems and "CREDIBLE_RECS_ALLOWED_HOSTS" in problems[0]


def test_local_mode_ignores_the_allowed_hosts_and_keeps_its_own():
    site, problems = web.site_from_env({"CREDIBLE_RECS_ALLOWED_HOSTS": HOST}, public=False)
    assert site == web.LOCAL and problems == []


def test_a_goatcounter_setting_that_isnt_a_code_leaves_counting_off_and_says_so():
    site, problems = web.site_from_env({"CREDIBLE_RECS_GOATCOUNTER": '"><script>alert(1)</script>'}, public=False)
    assert site == web.LOCAL and problems and "CREDIBLE_RECS_GOATCOUNTER" in problems[0]


# --- GoatCounter: off until Noemi gives her code ---

@pytest.mark.parametrize("value, code", [("credible-recs", "credible-recs"), ("  Credible-Recs ", "credible-recs"),
                                         ("noemi2", "noemi2")])
def test_a_goatcounter_code_is_letters_digits_and_hyphens(value, code):
    assert web.goatcounter_code(value) == code


@pytest.mark.parametrize("value", [None, "", "credible recs", "credible.recs", "credible-recs.goatcounter.com",
                                   "https://credible-recs.goatcounter.com", '"><script>', "-recs", "recs-", "a" * 64,
                                   "café"])
def test_anything_else_is_not_a_goatcounter_code(value):
    assert web.goatcounter_code(value) is None


def test_the_counter_script_is_goatcounters_standard_one():
    script = web.counter_script("credible-recs")
    assert script.startswith("<script ") and script.endswith("></script>")
    assert 'data-goatcounter="https://credible-recs.goatcounter.com/count"' in script
    assert ' async ' in script and 'src="https://gc.zgo.at/count.js"' in script  # never fetched over plain http
    # It counts inside the Space's page on huggingface.co too, which shows the site in a frame.
    assert json.loads(re.search(r"data-goatcounter-settings='([^']*)'", script).group(1)) == {"allow_frame": True}
    assert web.counter_script(None) == ""


def page_text(tmp_path: Path, path: str = "/", site: web.Site = web.LOCAL) -> str:
    """A page as the server sends it (pages read no library)."""
    status, content_type, body = web.handle_request(path, tmp_path / "no library", site)
    assert status == 200 and content_type.startswith("text/html")
    return body.decode("utf-8")


def settings_of(html: str) -> dict:
    return json.loads(re.search(r'<script type="application/json" id="settings">(.*?)</script>', html, re.DOTALL).group(1))


def test_with_goatcounter_on_both_pages_load_its_script(tmp_path):
    script = web.counter_script("credible-recs")
    html = page_text(tmp_path, "/", COUNTED)
    assert html.count(script) == 1 and settings_of(html)["counting"] is True
    # After the page's own script: the request is moved out of the address before anything is counted.
    assert html.index(script) > html.index("function track(")
    assert script in page_text(tmp_path, "/how", COUNTED)


def test_with_goatcounter_off_neither_page_counts_anything(tmp_path):
    html = page_text(tmp_path)
    assert settings_of(html)["counting"] is False
    for path in ("/", "/how"):
        assert not re.search(r"goatcounter\.com|gc\.zgo\.at", page_text(tmp_path, path))


def test_the_security_policy_lets_goatcounter_in_only_when_it_is_on():
    policy = web.security_headers(COUNTED)["Content-Security-Policy"]
    assert "script-src 'unsafe-inline' https://gc.zgo.at;" in policy
    assert "connect-src 'self' https://credible-recs.goatcounter.com;" in policy
    assert "img-src https://credible-recs.goatcounter.com;" in policy
    assert "default-src 'none'" in policy and "frame-ancestors 'none'" in policy
    assert "goatcounter" not in web.security_headers(PUBLIC)["Content-Security-Policy"]


# --- The page: "Was this useful?" under every answer ---

def script_of(html: str) -> str:
    """The page's own script (the one that draws answers)."""
    return re.search(r'<script>\n/\* How this page works(.*?)</script>', html, re.DOTALL).group(1)


def function_body(html: str, signature: str) -> str:
    found = re.search(re.escape(signature) + r" \{(.*?)\n  \}", html, re.DOTALL)
    assert found, signature
    return found.group(1)


def test_every_kind_of_answer_ends_with_the_feedback_form(tmp_path):
    draw = function_body(page_text(tmp_path), "function drawAnswer(data, request)")
    assert "feedbackForm(request, data.query)" in draw  # picks, one question first, and the polite no alike


def test_the_feedback_form_has_its_words_and_its_limit(tmp_path):
    html = page_text(tmp_path)
    for words in ('feedbackHeading: "Was this useful?"', 'feedbackUseful: "Useful"', 'feedbackNotUseful: "Not useful"',
                  "feedbackPrivacy: \"Please don't include personal details.\"", 'feedbackSend: "Send"'):
        assert words in html, words
    assert settings_of(html)["maxCommentChars"] == FEEDBACK_MAX_COMMENT_CHARS == 1000
    form = function_body(html, "function feedbackForm(request, query)")
    assert "maxlength: String(SETTINGS.maxCommentChars)" in form
    assert 'kind: "answer_feedback"' in form and "status: query.status" in form
    assert "product_type: query.product_type" in form
    assert "replaceWith(" in form  # after sending, a short thanks takes its place


def test_feedback_goes_to_this_sites_server_as_json_saying_which_site_it_comes_from(tmp_path):
    sending = function_body(page_text(tmp_path), "async function sendFeedback(record)")
    assert 'fetch("/api/feedback"' in sending and 'method: "POST"' in sending
    assert '"Content-Type": "application/json"' in sending
    # The page itself sends no Referer; this lets the browser say which site the feedback comes from (the Origin
    # header the server checks), and never the page's address.
    assert 'referrerPolicy: "strict-origin"' in sending


# --- The page: "First time here?" ---

def test_the_first_time_question_has_its_words_and_sends_only_yes_or_no(tmp_path):
    html = page_text(tmp_path)
    for words in ('firstTimeQuestion: "First time here?"', 'firstTimeYes: "Yes"',
                  "firstTimeNo: \"No, I've been before\""):
        assert words in html, words
    asking = function_body(html, "function firstTimeQuestion()")
    assert 'sendFeedback({ kind: "first_time", answer })' in asking
    assert "firstTimeQuestion();" in script_of(html)


def test_the_browsers_storage_is_only_ever_touched_inside_try_and_catch(tmp_path):
    lines = [line for line in script_of(page_text(tmp_path)).splitlines() if "localStorage" in line]
    assert lines, "the question is remembered in the browser's storage"
    for line in lines:
        assert "try {" in line and "catch" in line, line


# --- The page: events counted, never anything typed ---

EVENTS = {"search", "answer-ok", "answer-clarify", "answer-out-of-scope", "feedback-useful", "feedback-not-useful",
          "first-time-yes", "first-time-no"}


def test_only_fixed_event_names_are_counted_and_only_when_counting_is_on(tmp_path):
    script = script_of(page_text(tmp_path))
    names = re.search(r"const EVENTS = \{(.*?)\n  \};", script, re.DOTALL).group(1)
    assert set(re.findall(r'^\s*"([a-z-]+)": "[^"]+",?$', names, re.MULTILINE)) == EVENTS
    tracking = function_body(script, "function track(name)")
    assert "if (!SETTINGS.counting || !Object.hasOwn(EVENTS, name)) return;" in tracking
    assert "path: name, title: EVENTS[name], event: true" in tracking
    assert "try {" in tracking  # counting never breaks the page
    calls = re.findall(r"\btrack\(([^)]*)\)", script.replace("function track(name)", ""))
    assert calls
    for argument in calls:  # every event name written at a call is a known one; nothing typed is ever passed
        assert all(name in EVENTS for name in re.findall(r'"([a-z]+(?:-[a-z]+)+|search)"', argument)), argument
        assert not re.search(r"request|text|input|comment|value|query\.(question|message|product_type)", argument)


def test_the_request_is_kept_after_the_hash_where_nothing_sends_it(tmp_path):
    # The visit counter sends the page's address (and its "?..." part) with every event; a request after the "#" is
    # never sent anywhere. Older links with ?q= still work: the request is moved after the "#" first.
    script = script_of(page_text(tmp_path))
    assert 'history.pushState(null, "", request ? "#q=" + encodeURIComponent(request)' in script
    assert '"?q=" + encodeURIComponent' not in script
    assert 'query.delete("q")' in function_body(script, "function requestInAddress()")


def test_the_public_site_speaks_to_visitors_not_to_whoever_runs_the_server(tmp_path):
    html = page_text(tmp_path, "/", PUBLIC)
    assert settings_of(html)["public"] is True and settings_of(page_text(tmp_path))["public"] is False
    public_errors = re.search(r"errorsPublic: \{(.*?)\n  \},", html, re.DOTALL).group(1)
    assert "engine_failed" in public_errors and "offline" in public_errors
    assert "window" not in public_errors and "local server" not in public_errors
    assert 'too_many_requests: "' in html
