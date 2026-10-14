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
    # Changed on purpose 12 Oct 2026 (Noemi: show how many threads and comments each answer read): "reading".
    # Changed on purpose 13 Oct 2026 (hill-climbing the live site's latency): "timing", how long a fresh answer took.
    assert set(data) == {"query", "answer", "threads_used", "left_out", "reading", "timing"}
    # Changed on purpose 13 Oct 2026 (Noemi's testing; the UX builder): "reading" also says whether the first threads
    # gave too few picks, so more were read ("read_more"), for the page's reading strip.
    assert data["reading"] == {"threads": 2, "threads_saved": 2, "comments": 11,  # 3 kettles x 3 comments, 2 warnings
                               "read_more": False}
    # Changed on purpose 13 Oct 2026 (active ingredients, the orchestrator's decision after Noemi's live test): the
    # query also says which ingredients every product shown must contain, and whether the request is ingredient-led.
    # Changed on purpose 13 Oct 2026 (Noemi's decision 1 on forms): the query also says which forms an ingredient-led
    # request names ("salicylic acid wash": cleanser).
    assert set(data["query"]) == {"status", "category", "product_type", "question", "message", "ingredients",
                                  "ingredient_led", "forms"}
    # Changed on purpose 9 Oct 2026 (decision 11, budgets): each pick has its price, and "left_out" counts the
    # products over the request's budget.
    # Changed on purpose 9 Oct 2026 (availability, Noemi's note): "left_out" also counts the products no longer sold.
    # Changed on purpose 9 Oct 2026 (product facts, decided by Claude): "left_out" also counts the products whose facts
    # don't suit the request ("not_suited").
    # Changed on purpose 12 Oct 2026 (Noemi asked whether the footnote's numbers counted mentions or threads: they count
    # names): "left_out" also gives a few of the names left out ("other_type_names", "loose_names", at most
    # LEFT_OUT_NAMES_SHOWN each) and counts the brand or line names ranked as the brand's whole line ("ranked_as_lines").
    # Changed on purpose 13 Oct 2026 (active ingredients): "left_out" also counts the products without evidence they
    # contain the ingredient asked for ("no_ingredient").
    # Changed on purpose 13 Oct 2026 (Noemi's decision 1): "left_out" also counts the products of an ingredient-led
    # request left out for their form ("by_form"), and how many of them are rinse-off ("rinse_off").
    assert set(data["left_out"]) == {"other_type", "other_type_names", "loose", "loose_names", "ranked_as_lines",
                                     "over_budget", "unavailable", "not_suited", "no_ingredient", "by_form",
                                     "rinse_off"}
    assert isinstance(data["left_out"]["loose_names"], list) and isinstance(data["left_out"]["other_type_names"], list)
    # Changed on purpose 11 Oct 2026 (Noemi): the tips about the kind of product are shown once, in "care_note".
    # Changed on purpose 13 Oct 2026 (Noemi's decision 2): "worth_a_look", the products with two credible
    # recommendations across two threads, shown apart after the picks, and "worth_note", the words under its heading.
    # Changed on purpose 13 Oct 2026 (active ingredients): the answer's "title" as shown, the "ingredient" asked for and
    # the "ingredient_note" under the title (null for a request naming none).
    assert set(data["answer"]) == {"category", "product_type", "picks", "look_for", "skip", "message",
                                   "needs_more_threads", "quotes_dropped", "care_note", "worth_a_look", "worth_note",
                                   "ingredient", "ingredient_note", "title"}
    # Changed on purpose 9 Oct 2026 (care tips, Noemi): each pick also has its "care" list, "How to make it last".
    # Changed on purpose 9 Oct 2026 (availability, Noemi's note): each pick also says where it is sold, "availability".
    # Changed on purpose 9 Oct 2026 (product facts, decided by Claude): each pick also has its "cautions", the facts
    # that suit the request less well ("Note: ..."); an empty list when there are none.
    # Changed on purpose 10 Oct 2026 (decided by Claude): each pick also has its "model", a brand pick's most
    # recommended model, or null.
    # Changed on purpose 12 Oct 2026 (Noemi): each pick also says how many credible voices warned against it, of all,
    # "downsides_share" ("1 of 15 credible voices warned against it:"), or null when no downside is shown.
    # Changed on purpose 13 Oct 2026 (Noemi's decision 4): each pick also has its one-line "summary", {"text",
    # "sources"}, or null when it has none (or one that fails a check).
    # Changed on purpose 13 Oct 2026 (the UX builder): each pick also has its "voices", the credible voices behind it as
    # numbers (recommend, high, medium, warn, threads) for the page's credibility meter: the same writers its reason,
    # support line and share line count in words.
    # Changed on purpose 13 Oct 2026 (active ingredients): each pick also has its "form" in an ingredient-led answer
    # ("pads", "toner"), or null.
    # Changed on purpose 14 Oct 2026 (Noemi's night decision 1): each pick also has its "range", a brand line's link to
    # its maker's page for its products of the type ({"text", "url", "checked", "checked_on"}), or null; and its price
    # says whether it is a brand line's from price ("from_price").
    assert set(data["answer"]["picks"][0]) == {"rank", "product_key", "name", "reason", "support", "quotes",
                                               "downsides", "disagreement", "score", "breakdown", "price",
                                               "availability", "care", "cautions", "model", "model_price",
                                               "downsides_share", "summary", "voices", "form", "range"}
    assert set(data["answer"]["picks"][0]["quotes"][0]) == {"text", "comment_id", "url", "badges"}
    assert set(data["answer"]["picks"][0]["price"]) == {"text", "amount", "currency", "shop", "url", "checked_on",
                                                        "budget_status", "budget_note", "from_price"}


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


def test_an_answer_that_left_something_out_for_reddits_allowance_is_worked_out_again_next_time(tmp_path, monkeypatch):
    # 13 Oct 2026: "Also worth a look" and summaries never wait for Reddit's allowance; an answer that left one out for
    # that is not remembered, so the next ask (its picks' checks saved by then) can show it.
    import dataclasses

    calls = []

    def counting(request, library_dir):
        calls.append(request)
        return dataclasses.replace(answer_request(request, library_dir), live_put_off=1)

    monkeypatch.setattr(web, "answer_request", counting)
    library_dir = kettle_library(tmp_path)
    first = web.handle_request(f"/api/answer?q={quote(REQUEST)}", library_dir)
    web.handle_request(f"/api/answer?q={quote(REQUEST)}", library_dir)
    assert first[0] == 200 and calls == [REQUEST, REQUEST]
    assert json.loads(first[2])["timing"]["put_off"] == 1


def test_a_remembered_answer_is_worked_out_again_after_its_time(tmp_path, monkeypatch):
    # 12 Oct 2026 (the latency builder): answers were remembered for as long as the server ran, so their quotes were
    # checked live on Reddit once a run; the deletion rule keeps Reddit content at most 48 hours. A remembered answer
    # is kept for ANSWER_KEEP_HOURS, then worked out (and its quotes checked) again.
    calls, clock = [], [1000.0]

    def counting(request, library_dir):
        calls.append(request)
        return answer_request(request, library_dir)

    monkeypatch.setattr(web, "answer_request", counting)
    monkeypatch.setattr(web, "_clock", lambda: clock[0])
    library_dir = kettle_library(tmp_path)
    web.handle_request(f"/api/answer?q={quote(REQUEST)}", library_dir)
    clock[0] += web.ANSWER_KEEP_HOURS * 3600 - 1
    web.handle_request(f"/api/answer?q={quote(REQUEST)}", library_dir)
    assert calls == [REQUEST]
    clock[0] += 2
    web.handle_request(f"/api/answer?q={quote(REQUEST)}", library_dir)
    assert calls == [REQUEST, REQUEST]


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
    # Changed on purpose 14 Oct 2026 (Noemi's night decision 1): a third kind, a brand line's range page (the maker's
    # page for its products of the type, from data/brand_lines.json), through its own check, rangeUrl
    # (engine/tests/test_line_links.py).
    html = page(tmp_path)
    links = re.findall(r"href:\s*(\w+)", html)
    assert links, "the page should draw links"
    for name in links:
        assert re.search(rf"const {name} = (redditUrl|shopUrl|rangeUrl)\(", html), name


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



def test_the_page_says_how_many_threads_and_comments_an_answer_read():
    # Noemi, 12 Oct 2026: shown under every answer's title, not only in the small print.
    # Changed on purpose 13 Oct 2026 (Noemi's testing, through the orchestrator: "Based on 16 Reddit threads and 469
    # comments read for this answer, of 25 threads saved about exfoliant" confused her): still under every answer's
    # title, now as a strip of numbers in plain words: the threads read (the most relevant to the request), the comments
    # in them, and the threads saved about the product (engine/tests/test_web_ux.py has the strip's own test).
    page = web.search_page().decode("utf-8")
    assert "readingStrip(data.reading" in page
    for label in ('readingThreads: ["Reddit thread read", "Reddit threads read"]',
                  'readingComments: ["comment in them", "comments in them"]'):
        assert label in page, label


# --- Getting ready before the first visitor (latency, 12 Oct 2026) ---

def test_warming_up_reads_the_library_and_loads_the_open_model(tmp_path, monkeypatch):
    from engine import library_cache, query_model
    from engine.tests.test_library_cache import settled
    from engine.tests.test_pipeline import library

    root = settled(library(tmp_path))

    class FakeModel:
        loaded = False
        read_before_any_request = []

        def load(self):
            FakeModel.loaded = True

        def read(self, text):
            FakeModel.read_before_any_request.append(text)
            return {"category": "kitchen", "product": "toaster"}

    monkeypatch.setattr(query_model, "default_query_model", lambda: FakeModel())
    web.warm_up(root)
    assert FakeModel.loaded
    assert FakeModel.read_before_any_request[0] == web.PRIMING_REQUEST  # its instructions read first, ahead
    reads = []
    real = library_cache.load_threads
    monkeypatch.setattr(library_cache, "load_threads", lambda *a, **k: reads.append(1) or real(*a, **k))
    library_cache.loaded(root / "threads")
    assert reads == []  # already read, while getting ready


def test_warming_up_never_stops_the_server(tmp_path, monkeypatch, capsys):
    from engine import query_model

    def broken():
        raise RuntimeError("the model file is damaged")

    monkeypatch.setattr(query_model, "default_query_model", broken)
    monkeypatch.setattr(web, "ready", threading.Event())
    web.warm_up(tmp_path / "no-library")  # no threads/ folder, and a model that fails to load: reported, not raised
    assert "damaged" in capsys.readouterr().err
    assert web.ready.is_set()  # ready all the same: the answer that needs the model reports it


def test_the_server_says_it_is_ready_for_visitors_once_it_has_got_ready(tmp_path, monkeypatch, capsys):
    """Cloud Run sends visitors to a new server only once its /ready says so (13 Oct 2026): a server getting ready
    held the first visitors' answers up to 30 s on the live site, taking turns with them."""
    from engine import query_model

    monkeypatch.setattr(query_model, "default_query_model", lambda: None)
    monkeypatch.setattr(web, "ready", threading.Event())
    status, content_type, body = web.handle_request("/ready")
    assert status == 503 and content_type == web.JSON and json.loads(body) == {"ready": False}
    web.warm_up(tmp_path / "no-library")
    status, _, body = web.handle_request("/ready")
    assert status == 200 and json.loads(body) == {"ready": True}
    assert re.search(r"Ready for visitors: got ready in \d+\.\d s", capsys.readouterr().out)


def test_warming_up_answers_each_product_type_without_asking_reddit(tmp_path, monkeypatch):
    from engine import query_model
    from engine.tests.test_library_cache import settled
    from engine.tests.test_pipeline import library

    monkeypatch.setattr(query_model, "default_query_model", lambda: None)
    asked = []
    monkeypatch.setattr(web, "answer_request", lambda request, library_dir, **kwargs: asked.append(
        (request, kwargs | {"in_turn": web._answers_lock.locked()})))
    web.warm_up(settled(library(tmp_path)))
    assert all(kwargs["in_turn"] for _, kwargs in asked)  # one at a time with visitors' answers
    assert [request for request, _ in asked] == web.warm_requests()
    assert set(web.WARM_PRODUCT_TYPES) <= {request for request, _ in asked}  # every product type by its name too
    assert "electric kettle" in web.WARM_PRODUCT_TYPES and "shampoo" in web.WARM_PRODUCT_TYPES
    assert all("live_checker" not in kwargs and kwargs["live_check_required"] is False for _, kwargs in asked)


def test_getting_ready_answers_the_examples_then_one_request_per_product_type():
    # 14 Oct 2026 (the coordinator, from the live site: Cloud Run's one processor warmed 13 of 65 requests in getting
    # ready's 120 s): the search page's example requests first (what a visitor clicks); then one request for each type
    # not asked yet, its likeliest (the first latency request the rules place as that type, else the type's name): a
    # type's first answer reads every thread of its category for it, the biggest part of a cold answer; then the rest,
    # each once; the requests module 1 asks the open model about last (a reading of seconds that warms that very request
    # only).
    from engine.query import parse_query

    class Asked:
        def __init__(self):
            self.asked = False

        def read(self, text):
            self.asked = True
            return None

    def placed(text):
        stub = Asked()
        query = parse_query(text, model=stub)
        return (query.product_type if query.status == "ok" else None), stub.asked

    examples = [q["text"] for q in web.example_requests()]
    latency = [q["text"] for q in json.loads(web.LATENCY_FILE.read_text(encoding="utf-8"))["queries"]]
    likely = list(dict.fromkeys(examples + latency))
    warmed = web.warm_requests()
    assert sorted(warmed) == sorted(dict.fromkeys(likely + list(web.WARM_PRODUCT_TYPES)))  # each once
    assert examples and warmed[:len(examples)] == examples
    every = list(dict.fromkeys(likely + list(web.WARM_PRODUCT_TYPES)))
    where = {t: placed(t) for t in every}
    asked = {where[t][0] for t in examples}
    per_type = [next(t for t in every if where[t] == (p, False)) for p in web.WARM_PRODUCT_TYPES
                if p not in asked and any(where[t] == (p, False) for t in every)]
    assert warmed[len(examples):len(examples) + len(per_type)] == per_type
    assert "anti-dandruff shampoo" in per_type and "shampoo" not in per_type  # a type's latency request, else its name
    assert "toner" in per_type
    first = warmed[:len(examples) + len(per_type)]
    assert {where[t][0] for t in first} >= set(web.WARM_PRODUCT_TYPES) - {"serum"}  # every type the rules place alone
    asks_model = [t for t in warmed if where[t][1]]
    assert asks_model and warmed[-len(asks_model):] == asks_model  # "serum" and "something nice for my mum" last
    assert "serum" in asks_model


def test_warming_up_stops_answering_product_types_once_its_time_is_up(tmp_path, monkeypatch, capsys):
    # 13 Oct 2026: on Cloud Run a new server must say it is ready within the startup probe's 4 minutes, and the warm
    # answers alone grew past that (a deploy failed). Once WARM_UP_ANSWERS_SECONDS have passed, the remaining product
    # types are left for their first visitors and the server says it is ready.
    from engine import query_model
    from engine.tests.test_library_cache import settled
    from engine.tests.test_pipeline import library

    monkeypatch.setattr(query_model, "default_query_model", lambda: None)
    monkeypatch.setattr(web, "ready", threading.Event())
    now = [0.0]
    monkeypatch.setattr(web.time, "perf_counter", lambda: now[0])
    asked = []

    def slow(request, library_dir, **kwargs):  # every warm answer takes 40 s
        asked.append(request)
        now[0] += 40

    monkeypatch.setattr(web, "answer_request", slow)
    web.warm_up(settled(library(tmp_path)))
    assert web.ready.is_set()
    expected = -(-web.WARM_UP_ANSWERS_SECONDS // 40)  # answers started before the time was up
    assert len(asked) == expected < len(web.warm_requests())
    assert asked == web.warm_requests()[:expected]  # the likeliest first
    said = capsys.readouterr().out
    assert f"left {len(web.warm_requests()) - expected} requests for their first visitors" in said


def test_getting_ready_says_how_long_each_step_took(tmp_path, monkeypatch, capsys):
    # 14 Oct 2026 (the coordinator): on Cloud Run getting ready warmed far fewer requests than on this Mac in its 120 s;
    # each step before the warm answers now says its time in the server's window, so the slow one can be seen.
    from engine import query_model

    monkeypatch.setattr(query_model, "default_query_model", lambda: None)
    monkeypatch.setattr(web, "ready", threading.Event())
    web.warm_up(tmp_path / "no-library")
    said = capsys.readouterr().out
    for step in ("the open model", "the price list", "the facts list"):
        assert re.search(rf"Getting ready: {step} took \d+\.\d s\.", said), step


def _ready_with_requests_left(tmp_path, monkeypatch, takes: float = 40.0):
    """A server that got ready with time for 3 warm answers of `takes` seconds each, the rest left (a clock that moves
    only as answers take time); and the requests asked."""
    from engine import query_model
    from engine.tests.test_library_cache import settled
    from engine.tests.test_pipeline import library

    monkeypatch.setattr(query_model, "default_query_model", lambda: None)
    monkeypatch.setattr(web, "ready", threading.Event())
    monkeypatch.setattr(web, "_left_to_warm", [])
    now = [0.0]
    monkeypatch.setattr(web.time, "perf_counter", lambda: now[0])
    asked = []

    def slow(request, library_dir, **kwargs):
        asked.append((request, web._answers_lock.locked()))
        now[0] += takes

    monkeypatch.setattr(web, "answer_request", slow)
    root = settled(library(tmp_path))
    web.warm_up(root)
    return root, asked


def test_each_ping_after_getting_ready_warms_a_slice_of_the_requests_left(tmp_path, monkeypatch, capsys):
    # 14 Oct 2026 (the coordinator, from the live site: Cloud Run's one processor warmed 13 of 65 requests in getting
    # ready's 120 s, and a request whose threads weren't warmed took ~8 s): Cloud Run gives a server its processor only
    # while it answers someone, so a thread warming in the background would barely run. The keep-warm ping asks /ready
    # every 5 minutes: each ping warms the next requests left, for up to WARM_MORE_SECONDS, until none are left.
    root, asked = _ready_with_requests_left(tmp_path, monkeypatch)
    warm = web.warm_requests()
    done = -(-web.WARM_UP_ANSWERS_SECONDS // 40)
    assert [r for r, _ in asked] == warm[:done]
    capsys.readouterr()
    slice_ = -(-web.WARM_MORE_SECONDS // 40)  # answers started before the slice's time was up
    status, _, _ = web.handle_request("/ready", root)
    assert status == 200
    assert [r for r, _ in asked] == warm[:done + slice_]
    assert f"warmed {slice_} more, {len(warm) - done - slice_} left" in capsys.readouterr().out
    while web._left_to_warm:
        web.handle_request("/ready", root)
    assert [r for r, _ in asked] == warm  # every request warmed once, in order
    assert all(in_turn for _, in_turn in asked)  # each takes its turn with visitors' answers
    capsys.readouterr()
    web.handle_request("/ready", root)  # nothing left: the ping only says it is ready
    assert [r for r, _ in asked] == warm
    assert "warmed" not in capsys.readouterr().out


def test_a_ping_before_the_server_is_ready_warms_nothing(tmp_path, monkeypatch):
    root, asked = _ready_with_requests_left(tmp_path, monkeypatch)
    web.ready.clear()
    before = list(asked)
    assert web.handle_request("/ready", root)[0] == 503
    assert asked == before


def test_two_pings_at_once_warm_one_slice(tmp_path, monkeypatch):
    # One slice at a time: a ping arriving while another warms says it is ready at once.
    root, asked = _ready_with_requests_left(tmp_path, monkeypatch)
    before = len(asked)
    with web._warming:
        assert web.handle_request("/ready", root)[0] == 200
    assert len(asked) == before


def test_a_warmed_answer_leaves_every_answer_as_it_was(tmp_path):
    from engine import memo
    from engine.tests.test_library_cache import settled
    from engine.tests.test_pipeline import REQUEST, library

    root = settled(library(tmp_path))
    before = web.answer_json(answer_request(REQUEST, library_dir=root))
    memo.forget_all()
    web.warm_answer("electric kettle", root)
    assert web.answer_json(answer_request(REQUEST, library_dir=root)) == before



def test_a_fresh_answer_says_how_long_it_took_and_how_long_reddit_did(tmp_path, monkeypatch):
    # 13 Oct 2026: to hill-climb the live site's latency, each fresh answer says its total time, the time spent waiting
    # on live checks (overlapping checks counted once) and how many checks it made. Diagnostic only: never shown.
    status, _, data = ask(REQUEST, kettle_library(tmp_path))
    timing = data["timing"]
    assert set(timing) == {"total_s", "reddit_s", "checks", "put_off"}  # put_off: 13 Oct 2026, see below
    assert timing["total_s"] >= timing["reddit_s"] >= 0 and timing["checks"] >= 0


# --- Also worth a look and one-line summaries (Noemi's decisions 2 and 4, 13 Oct 2026) ---

def test_also_worth_a_look_comes_through_in_the_json(tmp_path):
    # The Smeg is praised twice, once in each thread: two credible voices, so "Also worth a look", never a pick.
    library_dir = kettle_library(tmp_path, praised=("Zojirushi", "Fellow Stagg", "Bonavita"))
    extra = {"1kett01": ("k1smeg", "My Smeg kettle has boiled every morning for 5 years."),
             "1kett02": ("k2smeg", "Our Smeg kettle is 7 years old and still looks new.")}
    for thread_id, (comment_id, text) in extra.items():
        thread_file = library_dir / "threads" / f"{thread_id}.json"
        thread = json.loads(thread_file.read_text(encoding="utf-8"))
        thread["comments"].append(comment(comment_id, thread_id, text))
        thread_file.write_text(json.dumps(thread), encoding="utf-8")
        extraction_file = library_dir / "extracted" / f"{thread_id}.json"
        extraction = json.loads(extraction_file.read_text(encoding="utf-8"))
        extraction["mentions"].append(mention(comment_id, "Smeg kettle", text))
        extraction_file.write_text(json.dumps(extraction), encoding="utf-8")
    _, _, data = ask(REQUEST, library_dir)
    assert [item["name"] for item in data["answer"]["worth_a_look"]] == ["Smeg kettle"]
    assert "Smeg kettle" not in [pick["name"] for pick in data["answer"]["picks"]]
    assert data["answer"]["worth_note"].startswith("2 credible voices each")
    # Changed on purpose 13 Oct 2026 (the UX builder): "voices", as for a pick (its credibility meter).
    # Changed on purpose 13 Oct 2026 (active ingredients): each item also has its "form", as picks do.
    # Changed on purpose 14 Oct 2026 (Noemi's night decision 1): each item also has its "range", as picks do.
    assert set(data["answer"]["worth_a_look"][0]) == {"product_key", "name", "reason", "quotes", "downsides",
                                                     "downsides_share", "disagreement", "score", "breakdown", "price",
                                                     "availability", "cautions", "summary", "voices", "form", "range"}


def test_the_page_draws_also_worth_a_look_and_summaries_with_the_answers_own_words(tmp_path):
    from engine.answer import SUMMARY_LABEL, SUMMARY_NOTE, WORTH_HEADING

    html = page(tmp_path)
    settings = json.loads(re.search(r'<script type="application/json" id="settings">(.*?)</script>', html, re.DOTALL).group(1))
    assert settings["wording"]["worth_heading"] == WORTH_HEADING == "Also worth a look"
    assert settings["wording"]["summary_label"] == SUMMARY_LABEL and settings["wording"]["summary_note"] == SUMMARY_NOTE
    assert "worthSection(answer)" in html and "answer.worth_note" in html
    worth = re.search(r"function worthCard\(item\) \{(.*?)\n  \}", html, re.DOTALL).group(1)
    assert "quoteList(item.quotes" in worth  # the same Reddit link check as every other quote
    assert "summaryLine(item.summary)" in worth and "summaryLine(pick.summary)" in html
    line = re.search(r"function summaryLine\(summary\) \{(.*?)\n  \}", html, re.DOTALL).group(1)
    assert "blockquote" not in line and "quote" not in line.replace("summary_note", "")  # never drawn as a quote
