"""Module 8, the local demo: the JSON API and the search page.

Everything runs on a made-up library of kettle threads, written to a temporary folder with their extraction
files (as in test_pipeline.py), so no test reads data/.
"""

import dataclasses
import json
import re
import threading
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import quote, urlparse

import pytest

from engine import web
from engine.answer import CARE_HEADING, PRICE_LABEL, PRICE_LINK_TEXT, QUOTES_HEADING
from engine.config import WEB_MAX_REQUEST_CHARS, WEB_PORT
from engine.library import DEFAULT_LIBRARY_DIR
from engine.pipeline import answer_request
from engine.prices import Price
from engine.tests.factories import write_gold
from engine.tests.test_pipeline import DESCALE, care_library, comment, kettle_thread, mention

REQUEST = "electric kettle that lasts 10+ years"


def kettle_library(tmp_path: Path, praised: tuple[str, ...] = ("Zojirushi", "Fellow Stagg", "Bonavita")) -> Path:
    """Two kettle threads: each praised kettle recommended three times across both, the Chefman warned against twice."""
    first, second, extractions = [], [], {"1kett01": [], "1kett02": []}
    for n, brand in enumerate(praised):
        product = f"{brand} kettle"
        quotes = [f"My {product} has lasted {n + 4} years and still boils perfectly.",
                  f"Had my {product} for {n + 3} years now, no problems at all.",
                  f"Our {product} is {n + 6} years old and still going strong."]
        ids = [f"k1a{n}", f"k1b{n}", f"k2a{n}"]
        first += [comment(ids[0], "1kett01", quotes[0]), comment(ids[1], "1kett01", quotes[1])]
        second.append(comment(ids[2], "1kett02", quotes[2]))
        extractions["1kett01"] += [mention(ids[0], product, quotes[0]), mention(ids[1], product, quotes[1])]
        extractions["1kett02"].append(mention(ids[2], product, quotes[2]))
    warnings = ("The Chefman kettle died after 6 months of use.", "Two Chefman kettles broke within a year of use, avoid them.")
    first.append(comment("k1warn", "1kett01", warnings[0]))
    second.append(comment("k2warn", "1kett02", warnings[1]))
    extractions["1kett01"].append(mention("k1warn", "Chefman kettle", warnings[0], "warn"))
    extractions["1kett02"].append(mention("k2warn", "Chefman kettle", warnings[1], "warn"))
    root = write_gold(tmp_path / "library", [kettle_thread("1kett01", first), kettle_thread("1kett02", second)],
                      voices=None, mentions=None)
    (root / "extracted").mkdir()
    for thread_id, mentions in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v5", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions,
        }), encoding="utf-8")
    return root


def ask(request: str, library_dir: Path) -> tuple[int, str, dict]:
    """GET /api/answer for one request: (status, content type, the JSON body)."""
    status, content_type, body = web.handle_request(f"/api/answer?q={quote(request)}", library_dir)
    return status, content_type, json.loads(body)


@pytest.fixture(autouse=True)
def fresh_cache():
    """Each test starts with no remembered answers."""
    web.clear_answer_cache()
    yield
    web.clear_answer_cache()


# --- GET /api/answer ---

def test_a_known_request_comes_back_as_three_cards_in_json(tmp_path):
    status, content_type, data = ask(REQUEST, kettle_library(tmp_path))
    assert status == 200 and content_type.startswith("application/json")
    assert data["query"]["status"] == "ok" and data["query"]["product_type"] == "electric kettle"
    assert len(data["answer"]["picks"]) == 3 and data["answer"]["message"] is None
    assert sorted(pick["name"] for pick in data["answer"]["picks"]) == ["Bonavita kettle", "Fellow Stagg kettle", "Zojirushi kettle"]
    assert sorted(data["threads_used"]) == ["1kett01", "1kett02"]


def test_the_json_has_the_documented_shape(tmp_path):
    # The contract the later website will use: change it only on purpose, and update engine/web.py's docstring.
    _, _, data = ask(REQUEST, kettle_library(tmp_path))
    assert set(data) == {"query", "answer", "threads_used", "left_out"}
    assert set(data["query"]) == {"status", "category", "product_type", "question", "message"}
    # Changed on purpose 9 Oct 2026 (decision 11, budgets): each pick has its price, and "left_out" counts the
    # products over the request's budget.
    # Changed on purpose 9 Oct 2026 (availability, Noemi's note): "left_out" also counts the products no longer sold.
    # Changed on purpose 9 Oct 2026 (product facts, decided by Claude): "left_out" also counts the products whose facts
    # don't suit the request ("not_suited").
    assert set(data["left_out"]) == {"other_type", "loose", "over_budget", "unavailable", "not_suited"}
    # Changed on purpose 11 Oct 2026 (Noemi): the tips about the kind of product are shown once, in "care_note".
    assert set(data["answer"]) == {"category", "product_type", "picks", "look_for", "skip", "message",
                                   "needs_more_threads", "quotes_dropped", "care_note"}
    # Changed on purpose 9 Oct 2026 (care tips, Noemi): each pick also has its "care" list, "How to make it last".
    # Changed on purpose 9 Oct 2026 (availability, Noemi's note): each pick also says where it is sold, "availability".
    # Changed on purpose 9 Oct 2026 (product facts, decided by Claude): each pick also has its "cautions", the facts
    # that suit the request less well ("Note: ..."); an empty list when there are none.
    # Changed on purpose 10 Oct 2026 (decided by Claude): each pick also has its "model", a brand pick's most
    # recommended model, or null.
    assert set(data["answer"]["picks"][0]) == {"rank", "product_key", "name", "reason", "support", "quotes",
                                               "downsides", "disagreement", "score", "breakdown", "price",
                                               "availability", "care", "cautions", "model", "model_price"}
    assert set(data["answer"]["picks"][0]["quotes"][0]) == {"text", "comment_id", "url", "badges"}
    assert set(data["answer"]["picks"][0]["price"]) == {"text", "amount", "currency", "shop", "url", "checked_on",
                                                        "budget_status", "budget_note"}


def test_every_card_has_at_least_two_quotes_each_linking_to_reddit(tmp_path):
    _, _, data = ask(REQUEST, kettle_library(tmp_path))
    for pick in data["answer"]["picks"]:
        assert len(pick["quotes"]) >= 2
        for shown in pick["quotes"]:
            link = urlparse(shown["url"])
            assert link.scheme == "https" and (link.hostname == "reddit.com" or link.hostname.endswith(".reddit.com"))


def test_the_skip_list_comes_through(tmp_path):
    _, _, data = ask(REQUEST, kettle_library(tmp_path))
    assert [item["name"] for item in data["answer"]["skip"]] == ["Chefman kettle"]


def with_prices(prices):
    """answer_request, with a made-up price list instead of data/prices.json."""
    def answer_with_prices(request, library_dir):
        return answer_request(request, library_dir, prices=prices, today=date(2026, 10, 9))
    return answer_with_prices


def made_up_price(product: str, amount: float, url: str = "https://shop.example/kettle") -> Price:
    return Price(product=product, category="kitchen", price=amount, currency="GBP", shop="Made-up Kitchen Shop",
                 url=url, checked_on=date(2026, 10, 9))


def test_each_card_carries_its_price_and_the_shops_own_link(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "answer_request", with_prices([made_up_price("Zojirushi kettle", 80.0)]))
    _, _, data = ask("electric kettle under £100", kettle_library(tmp_path))
    prices = {pick["name"]: pick["price"] for pick in data["answer"]["picks"]}
    assert prices["Zojirushi kettle"]["url"] == "https://shop.example/kettle"
    assert prices["Zojirushi kettle"]["budget_status"] == "within"
    assert prices["Bonavita kettle"]["url"] is None and prices["Bonavita kettle"]["budget_status"] == "unknown"


def test_products_over_the_budget_are_counted_as_left_out(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "answer_request", with_prices([made_up_price("Zojirushi kettle", 180.0)]))
    _, _, data = ask("electric kettle under £100", kettle_library(tmp_path))
    assert data["left_out"]["over_budget"] == 1
    assert "Zojirushi kettle" not in [pick["name"] for pick in data["answer"]["picks"]]


def test_too_little_evidence_comes_back_as_the_honest_message(tmp_path):
    library_dir = kettle_library(tmp_path, praised=("Zojirushi",))
    _, _, data = ask(REQUEST, library_dir)
    assert len(data["answer"]["picks"]) == 1
    assert data["answer"]["message"] == answer_request(REQUEST, library_dir).answer.message  # the answer's own words


def test_a_vague_request_comes_back_as_module_1s_question(tmp_path):
    status, _, data = ask("something nice for my mum", kettle_library(tmp_path))
    assert status == 200 and data["query"]["status"] == "clarify"
    assert data["query"]["question"] and data["answer"] is None and data["threads_used"] == []


def test_an_out_of_scope_request_comes_back_as_module_1s_polite_no(tmp_path):
    status, _, data = ask("running shoes for flat feet", kettle_library(tmp_path))
    assert status == 200 and data["query"]["status"] == "out_of_scope"
    assert data["query"]["message"] and data["answer"] is None


def test_an_unverifiable_quote_makes_the_endpoint_refuse(tmp_path, monkeypatch):
    planted = "This kettle cured my insomnia and paid my rent."

    def answer_with_a_planted_quote(request, library_dir):
        result = answer_request(request, library_dir)
        pick = result.answer.picks[0]
        pick.quotes[0] = dataclasses.replace(pick.quotes[0], text=planted)  # a quote its comment never said
        return result

    monkeypatch.setattr(web, "answer_request", answer_with_a_planted_quote)
    status, content_type, body = web.handle_request(f"/api/answer?q={quote(REQUEST)}", kettle_library(tmp_path))
    assert status == 500 and content_type.startswith("application/json")
    assert planted.encode() not in body and b"Zojirushi" not in body  # nothing from the answer is shown
    assert json.loads(body)["error"] and json.loads(body)["code"] == "quote_not_verified"


@pytest.mark.parametrize("path", ["/api/answer", "/api/answer?q=", "/api/answer?q=%20%20%20", "/api/answer?other=kettle"])
def test_an_empty_request_is_refused(tmp_path, path):
    status, content_type, body = web.handle_request(path, kettle_library(tmp_path))
    assert status == 400 and content_type.startswith("application/json") and json.loads(body)["error"]
    assert json.loads(body)["code"] == "empty_request"


def test_a_request_over_the_length_limit_is_refused(tmp_path):
    library_dir = kettle_library(tmp_path)
    at_limit = REQUEST + " " + "x" * (WEB_MAX_REQUEST_CHARS - len(REQUEST) - 1)
    assert len(at_limit) == WEB_MAX_REQUEST_CHARS == 300
    assert ask(at_limit, library_dir)[0] == 200
    status, _, data = ask(at_limit + "x", library_dir)
    assert status == 400 and data["code"] == "request_too_long"


def test_answers_are_remembered_for_the_life_of_the_process(tmp_path, monkeypatch):
    calls = []

    def counting(request, library_dir):
        calls.append(request)
        return answer_request(request, library_dir)

    monkeypatch.setattr(web, "answer_request", counting)
    library_dir = kettle_library(tmp_path)
    first = web.handle_request(f"/api/answer?q={quote(REQUEST)}", library_dir)
    again = web.handle_request(f"/api/answer?q={quote('  ' + REQUEST + ' ')}", library_dir)  # same words, extra spaces
    assert first == again and calls == [REQUEST]


def test_a_missing_library_is_an_error_not_a_crash(tmp_path):
    status, _, body = web.handle_request(f"/api/answer?q={quote(REQUEST)}", tmp_path / "no-library")
    assert status == 500 and json.loads(body)["code"] == "engine_failed"


@pytest.mark.parametrize("path", ["/nope", "/api", "/api/answer/", "/api/answers?q=kettle", "/index.html", "/../etc/passwd"])
def test_unknown_paths_are_not_found(tmp_path, path):
    status, _, body = web.handle_request(path, kettle_library(tmp_path))
    assert status == 404 and json.loads(body)["code"] == "not_found"


# --- GET /: the search page ---

def page(tmp_path: Path) -> str:
    status, content_type, body = web.handle_request("/", kettle_library(tmp_path))
    assert status == 200 and content_type.startswith("text/html")
    return body.decode("utf-8")


def test_the_page_links_and_loads_nothing_outside_this_machine_except_reddit(tmp_path):
    html = page(tmp_path)
    urls = re.findall(r"""(?:https?:)?//[^\s"'`<>)]+""", html)
    hosts = {urlparse(url if url.startswith("http") else "https:" + url).hostname for url in urls}
    assert hosts <= {"reddit.com", "www.reddit.com"}
    assert not re.search(r"<script[^>]*\ssrc=|<link\b|<iframe|<img|<object|<embed", html, re.IGNORECASE)
    styles = " ".join(re.findall(r"<style>(.*?)</style>", html, re.DOTALL))
    assert not re.search(r"@import|url\(", styles, re.IGNORECASE)  # no outside fonts or pictures


def test_the_page_never_draws_data_as_html(tmp_path):
    # Reddit text is put on the page as text only (textContent), so "<script>" in a comment is shown, never run.
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(", page(tmp_path))


def test_every_link_the_page_draws_goes_through_a_link_check(tmp_path):
    # Two kinds of link only (changed on purpose 9 Oct 2026, decision 11): a quote's comment on Reddit, and a price's
    # shop page. Each address is checked before it becomes a link; any other address is shown without one.
    html = page(tmp_path)
    links = re.findall(r"href:\s*(\w+)", html)
    assert links, "the page should draw links"
    for name in links:
        assert re.search(rf"const {name} = (redditUrl|shopUrl)\(", html), name


def test_a_shop_link_must_be_https_with_no_name_or_password(tmp_path):
    html = page(tmp_path)
    check = re.search(r"function shopUrl\(address\) \{(.*?)\n  \}", html, re.DOTALL).group(1)
    assert 'url.protocol === "https:"' in check and "http:" not in check.replace("https:", "")
    assert "url.username" in check and "url.password" in check
    assert html.count('rel: "noopener noreferrer"') == len(re.findall(r"href:", html))  # every link opens apart


def test_the_page_carries_the_price_wording(tmp_path):
    html = page(tmp_path)
    settings = json.loads(re.search(r'<script type="application/json" id="settings">(.*?)</script>', html, re.DOTALL).group(1))
    assert settings["wording"]["price_label"] == PRICE_LABEL
    assert settings["wording"]["price_link_text"] == PRICE_LINK_TEXT


def test_the_page_carries_the_answers_own_headings_and_the_example_requests(tmp_path):
    html = page(tmp_path)
    settings = json.loads(re.search(r'<script type="application/json" id="settings">(.*?)</script>', html, re.DOTALL).group(1))
    assert settings["wording"]["quotes_heading"] == QUOTES_HEADING
    assert settings["maxChars"] == WEB_MAX_REQUEST_CHARS
    assert "burr coffee grinder for pour-over under £150" in [example["text"] for example in settings["examples"]]
    assert "PROPOSED" in html  # the page's own new wording is marked for Noemi's review


# --- The server ---

def test_the_server_listens_on_this_machine_only(tmp_path):
    server = web.make_server(port=0, library_dir=kettle_library(tmp_path))
    try:
        assert server.server_address[0] == "127.0.0.1"
    finally:
        server.server_close()


def test_the_server_answers_over_http_and_only_when_addressed_to_this_machine(tmp_path):
    server = web.make_server(port=0, library_dir=kettle_library(tmp_path))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(f"{base}/api/answer?q={quote(REQUEST)}", timeout=10) as response:
            assert response.status == 200 and len(json.loads(response.read())["answer"]["picks"]) == 3
        with urllib.request.urlopen(f"{base}/", timeout=10) as response:
            assert "default-src 'none'" in response.headers["Content-Security-Policy"]
        # A page on another website that tricks the browser into calling this server (DNS rebinding) is refused.
        tricked = urllib.request.Request(f"{base}/", headers={"Host": "evil.example"})
        with pytest.raises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(tricked, timeout=10)
        assert refused.value.code == 403
    finally:
        server.shutdown()
        server.server_close()


def test_the_command_takes_a_port_and_a_library_and_nothing_else():
    assert web._options([]) == (WEB_PORT, DEFAULT_LIBRARY_DIR)
    assert web._options(["--library", "/elsewhere", "--port", "9000"]) == (9000, Path("/elsewhere"))
    assert web._options(["--port", "nine"]) is None and web._options(["--port"]) is None
    assert web._options(["--host", "0.0.0.0"]) is None  # there is no way to open it to the network


# --- Care tips: how to take care of it (Noemi, 9 Oct 2026; renamed and split on 11 Oct 2026) ---

def test_each_card_carries_its_care_tips_with_verified_reddit_quotes(tmp_path):
    _, _, data = ask(REQUEST, care_library(tmp_path))
    care = data["answer"]["picks"][0]["care"]
    # Since 11 Oct 2026 (Noemi): the card has the tips about its product; the kind's are in the answer's note.
    assert [item["tip"] for item in care] == ["Descale every 6 months."]
    assert [item["tip"] for item in data["answer"]["care_note"]] == ["Use filtered water."]
    assert care[0]["quote"]["text"] == DESCALE
    for item in care + data["answer"]["care_note"]:
        link = urlparse(item["quote"]["url"])
        assert link.scheme == "https" and link.hostname.endswith("reddit.com")


def test_a_card_with_no_care_tips_has_an_empty_list(tmp_path):
    _, _, data = ask(REQUEST, kettle_library(tmp_path))
    assert all(pick["care"] == [] for pick in data["answer"]["picks"])


def test_an_unverifiable_care_quote_makes_the_endpoint_refuse(tmp_path, monkeypatch):
    planted = "Boil vinegar in it daily and it will last a century."

    def answer_with_a_planted_care_quote(request, library_dir):
        result = answer_request(request, library_dir)
        item = result.answer.picks[0].care[0]
        result.answer.picks[0].care[0] = dataclasses.replace(item, quote=dataclasses.replace(item.quote, text=planted))
        return result

    monkeypatch.setattr(web, "answer_request", answer_with_a_planted_care_quote)
    status, _, body = web.handle_request(f"/api/answer?q={quote(REQUEST)}", care_library(tmp_path))
    assert status == 500 and json.loads(body)["code"] == "quote_not_verified"
    assert planted.encode() not in body and DESCALE.encode() not in body


def test_the_page_carries_the_care_heading_and_draws_care_tips_as_quotes(tmp_path):
    html = page(tmp_path)
    settings = json.loads(re.search(r'<script type="application/json" id="settings">(.*?)</script>', html, re.DOTALL).group(1))
    # Renamed by Noemi on 11 Oct 2026 (was "How to make it last"); the kind's tips are drawn once, as a note at the end.
    assert settings["wording"]["care_heading"] == CARE_HEADING == "How to take care of it"
    assert settings["wording"]["care_note_heading"] == "How to take care of your {product_type}"
    assert "careNote(answer)" in html
    drawing = re.search(r"function careSection\(tips\) \{(.*?)\n  \}", html, re.DOTALL).group(1)
    listing = re.search(r"function careList\(tips\) \{(.*?)\n  \}", html, re.DOTALL).group(1)
    assert "WORDING.care_heading" in drawing and "careList(tips)" in drawing
    assert "quoteBlock(item.quote)" in listing  # the same Reddit link check as every other quote
    assert "careSection(pick.care)" in html
