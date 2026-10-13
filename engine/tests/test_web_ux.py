"""The redesigned search page (13 Oct 2026, the UX builder; Noemi: "something way nicer and advanced without sacrificing
the speed of the service"): the numbers its credibility meter and its reading strip draw, its size budget, and the
rules the new parts keep (nothing from Reddit as HTML, no score breakdown on the page, nothing typed in the page's
title, only the visitor's own requests in the browser's storage, quotes never cut).

Every text is made up. No test reaches the network.
"""

import dataclasses
import re

from engine import web
from engine.answer import DOWNSIDES_SHARE, write_answer
from engine.pipeline import answer_request
from engine.rank import rank_products
from engine.tests.ranking_factories import bodies_for, mention, mentions
from engine.tests.test_web import REQUEST, ask, kettle_library
from engine.tests.test_web_public import function_body, page_text, script_of, settings_of

# The whole search page as the public site serves it (visit counting on, its longest form), in bytes, uncompressed. The
# redesign's budget: the page is one request with everything inline, so its size is most of its loading time.
PAGE_BUDGET_BYTES = 120 * 1024


def setup_function():
    web.clear_answer_cache()


def teardown_function():
    web.clear_answer_cache()


# --- The credibility meter's numbers: "voices" in the API ---

def test_each_pick_says_its_credible_voices_as_numbers_that_match_its_words(tmp_path):
    _, _, data = ask(REQUEST, kettle_library(tmp_path))
    for pick in data["answer"]["picks"]:
        voices = pick["voices"]
        assert set(voices) == {"recommend", "high", "medium", "warn", "threads"}
        assert voices["high"] + voices["medium"] == voices["recommend"]
        assert pick["reason"].startswith(f"Recommended by {voices['recommend']} credible voices")
        assert pick["support"].endswith(f"across {voices['threads']} threads.")
        assert voices["warn"] == 0 and pick["downsides"] == [] and pick["downsides_share"] is None


def test_the_meters_warnings_are_the_share_lines_writers_with_the_brands_own_included():
    # A brand pick shows warnings about its own products under it too (the share line counts them): the meter counts the
    # same writers, so the bar and the words never give different numbers.
    praise = mentions(4, "Acme pans")
    own = [mention("Acme pans", "t1", stance="warn", voice="medium", quote=f"Acme pans chipped, writer {n}.")
           for n in range(2)]
    line = [mention("Acme Pro pan", "t2", stance="warn", voice="medium", quote="The Acme Pro pan warped.")]
    items = praise + own
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items, *line), "frying pan",
                          more_downsides={"acme-pans": line})
    pick = answer.picks[0]
    assert pick.voices == {"recommend": 4, "high": 4, "medium": 0, "warn": 3, "threads": 2}
    assert pick.downsides_share == DOWNSIDES_SHARE.format(n=3, total=3 + 4)


def test_an_also_worth_a_look_item_says_its_voices_too():
    praise = mentions(3, "Acme pan") + mentions(2, "Brio pan", voice="medium")
    answer = write_answer(rank_products(praise, "kitchen"), bodies_for(*praise), "frying pan")
    (item,) = answer.worth_a_look
    assert item.name == "Brio pan"
    assert item.voices == {"recommend": 2, "high": 0, "medium": 2, "warn": 0, "threads": 2}


# --- The reading strip: whether more threads were read ---

def test_the_reading_says_whether_the_answer_read_more_threads_than_usual(tmp_path, monkeypatch):
    # Noemi's testing, 13 Oct 2026: "Based on 16 Reddit threads ... of 25 threads saved" confused her. The strip says the
    # threads read are the most relevant ones, and, when the first ones gave too few picks, that more were read.
    _, _, data = ask(REQUEST, kettle_library(tmp_path))
    assert data["reading"]["read_more"] is False

    def wider(request, library_dir):
        return dataclasses.replace(answer_request(request, library_dir), read_more=True)

    monkeypatch.setattr(web, "answer_request", wider)
    _, _, data = ask(REQUEST, kettle_library(tmp_path / "again"))
    assert data["reading"]["read_more"] is True


def test_the_page_draws_the_reading_as_a_strip_of_numbers_in_plain_words(tmp_path):
    html = page_text(tmp_path)
    strip = function_body(html, "function readingStrip(reading, ingredient)")
    for field in ("reading.threads", "reading.comments", "reading.threads_saved", "reading.read_more"):
        assert field in strip, field
    assert "LABELS.readingWhy" in strip  # why not all of them: the rest are less related to the request
    assert "readingStrip(data.reading, ingredient)" in html
    assert settings_of(html)["picksShown"] == 3


# --- Size and speed ---

def test_the_page_stays_within_its_size_budget(tmp_path):
    biggest = web.Site(public=True, hosts=("demo.example",), goatcounter="credible-recs")
    assert len(web.search_page(biggest)) <= PAGE_BUDGET_BYTES
    assert len(page_text(tmp_path, "/how", biggest).encode("utf-8")) <= PAGE_BUDGET_BYTES


def test_the_page_measures_its_own_drawing_time_and_sends_it_nowhere(tmp_path):
    # The drawing time is kept in the browser's own performance timeline (User Timing), for checking the page stays
    # fast; nothing is sent anywhere.
    script = script_of(page_text(tmp_path))
    assert 'performance.measure("credible-recs:draw"' in script
    assert len(re.findall(r"\bfetch\(", script)) == 2  # the answer and the feedback, to this site's own server


# --- The rules the new parts keep ---

def test_the_page_never_draws_the_score_breakdown(tmp_path):
    # Noemi, 12 Oct 2026: the score breakdown is off the card. The meter draws "voices", the numbers the answer's own
    # sentences say in words.
    script = script_of(page_text(tmp_path))
    code = re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", script, flags=re.DOTALL))  # the comments may tell its story
    assert "breakdown" not in code
    meter = function_body(script, "function trustMeter(voices)")
    assert "voices.recommend" in meter and "voices.warn" in meter


def test_nothing_typed_ever_goes_into_the_pages_title(tmp_path):
    # GoatCounter sends the page's title with each count, so the title never holds a request or an answer.
    script = script_of(page_text(tmp_path))
    assert re.findall(r"document\.title\s*=[^=][^;]*", script) == ["document.title = LABELS.pageTitle"]


def test_the_browsers_storage_keeps_only_the_first_time_note_and_the_visitors_own_requests(tmp_path):
    script = script_of(page_text(tmp_path))
    calls = re.findall(r"\bremember\(((?:[^()]|\([^()]*\))*)\)", script.replace("function remember(key, value)", ""))
    assert calls
    for arguments in calls:
        assert re.fullmatch(r'FIRST_TIME_KEY, "[a-z]+"|RECENT_KEY, JSON\.stringify\(recent\)', arguments), arguments
    keeping = function_body(script, "function rememberSearch(request)")
    assert "recent = [request" in keeping  # the request as typed, and nothing from an answer
    assert "data." not in keeping and "answer" not in keeping


def test_recent_searches_can_be_cleared(tmp_path):
    script = script_of(page_text(tmp_path))
    assert "function forget(key) { try { localStorage.removeItem(key); } catch (error) { /* nothing kept */ } }" in script
    assert "forget(RECENT_KEY)" in function_body(script, "function clearRecent()")


def test_quotes_are_drawn_whole(tmp_path):
    # A quote is shown as the API gives it, never cut short: not in the script, not by the styles.
    html = page_text(tmp_path)
    script = script_of(html)
    assert set(re.findall(r"quote\.text[\w.(]*", script)) == {"quote.text"}
    assert "masked(quote.text)" in script
    styles = re.search(r"<style>(.*?)</style>", html, re.DOTALL).group(1)
    assert "line-clamp" not in styles and "text-overflow" not in styles


def test_the_slash_key_goes_to_the_search_box(tmp_path):
    keys = function_body(script_of(page_text(tmp_path)), "function onKey(event)")
    assert 'event.key === "/"' in keys and "input.focus()" in keys
    assert "isTyping(event.target)" in keys  # never while someone is typing in a box


def test_a_long_skip_list_shows_its_strongest_first_and_folds_the_rest_without_leaving_any_out(tmp_path):
    # 13 Oct 2026 (the orchestrator, after Noemi's decision to list brand lines under "Skip these"): b02's answer had
    # 15 items. The first 5 (the API's order, strongest first) are in view, the rest behind "Show 10 more".
    html = page_text(tmp_path)
    script = script_of(html)
    assert "const LIST_SHOWN_FIRST = 5;" in script
    skip = function_body(script, "function skipSection(items)")
    assert "foldedList(" in skip and "LIST_SHOWN_FIRST" in skip and "quoteList(item.quotes)" in skip
    folding = function_body(script, "function foldedList(listClass, entries, first)")
    assert "entries.slice(0, first)" in folding and "entries.slice(first)" in folding  # every item drawn; some hidden
    assert '"aria-expanded"' in folding
    assert 'showMore: ["Show 1 more", "Show {n} more"]' in html


def test_the_how_page_says_recent_searches_stay_in_the_browser(tmp_path):
    # The privacy section says what the browser keeps for the "recent searches" chips, and that it never leaves it.
    from engine.tests.test_how_page import text_of

    words = text_of(page_text(tmp_path, "/how"))
    assert "Your recent searches." in words and "That list is never sent to us" in words and "Clear button" in words


# --- Sent compressed (13 Oct 2026): the redesigned page is bigger, so it travels gzipped to browsers that take it ---

def fetch_raw(server, path: str, accept_encoding: str | None):
    import urllib.error
    import urllib.request

    headers = {"Accept-Encoding": accept_encoding} if accept_encoding else {}
    request = urllib.request.Request(f"http://127.0.0.1:{server.server_address[1]}{path}", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return dict(response.headers), response.read()
    except urllib.error.HTTPError as error:  # an error's headers and body all the same
        return dict(error.headers), error.read()


def test_pages_and_answers_travel_gzipped_to_browsers_that_take_it(tmp_path):
    import gzip
    import threading
    from urllib.parse import quote

    server = web.make_server(port=0, library_dir=kettle_library(tmp_path))
    threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True).start()
    try:
        for path in ("/", "/how", f"/api/answer?q={quote(REQUEST)}"):
            headers, body = fetch_raw(server, path, "gzip, deflate, br")
            assert headers["Content-Encoding"] == "gzip" and headers["Vary"] == "Accept-Encoding", path
            assert int(headers["Content-Length"]) == len(body)
            plain_headers, plain = fetch_raw(server, path, None)
            assert "Content-Encoding" not in plain_headers and gzip.decompress(body) == plain, path
            assert len(body) < len(plain) / 2, path
        headers, _ = fetch_raw(server, "/", "br;q=1, gzip;q=0")  # refused by the browser: sent as it is
        assert "Content-Encoding" not in headers
        headers, _ = fetch_raw(server, "/api/answer?q=", "gzip")  # a small error isn't worth compressing
        assert "Content-Encoding" not in headers
    finally:
        server.shutdown()
        server.server_close()


def test_only_a_browser_that_says_it_takes_gzip_gets_it():
    assert web.takes_gzip("gzip") and web.takes_gzip("deflate, gzip;q=0.5") and web.takes_gzip("*")
    assert not web.takes_gzip(None) and not web.takes_gzip("br") and not web.takes_gzip("gzip;q=0")
    assert not web.takes_gzip("gzip;q=0.000")
