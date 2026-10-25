"""The pairwise test's page and route (engine/web.py, engine/templates/test.html; Noemi, 20 Oct 2026): GET /test, a short
blind test for friends, and POST /api/test-response, which keeps each answer through the feedback store.

Every text is made up (engine/tests/pair_factories.py). No test reaches the network: servers listen on 127.0.0.1 and
answers go to a fake store.
"""

import io
import json
import random
import re
import urllib.error
import urllib.request

import pytest

from engine import feedback, pair_test, web
from engine.config import FEEDBACK_MAX_BODY_BYTES, RATE_LIMIT_FEEDBACK, RATE_LIMIT_PAIRS
from engine.tests.pair_factories import QUESTION_IDS, made_up_cards, pick, write_cards
from engine.tests.test_web_public import HOST, PUBLIC, FakeStore, own_origin, send, start, stop
from engine.tests.test_web_ux import _contrast, _tokens

# What the page sends of an answer, apart from the visit's id and the question: never the rival or the side, which the
# server works out from the visit's id (25 Oct 2026, so that nothing a visitor's browser holds tells which answer is ours).
PAIR = {"choice": "B", "why": "It explained what to avoid.", "language": "en", "answered_at": "2026-10-24T20:15:03.512Z"}

# The page as the public site serves it, with the longest cards the rules allow: its size budget, in bytes, uncompressed.
# The search page's is 120 KB; this one is a few screens of text.
PAGE_BUDGET_BYTES = 44 * 1024
TEMPLATE_BUDGET_BYTES = 24 * 1024  # the page itself, styles and script, before any cards
TYPICAL_BUDGET_BYTES = 32 * 1024  # with the cards of the made-up set (three short picks each)


@pytest.fixture(autouse=True)
def fake_store(monkeypatch):
    store = FakeStore()
    monkeypatch.setattr(web, "store", store)
    return store


@pytest.fixture
def library(tmp_path):
    return write_cards(tmp_path / "library")


def get(library, path="/test", site=web.LOCAL):
    return web.handle_request(path, library, site)


def page_of(library, site=web.LOCAL) -> str:
    status, content_type, body = get(library, "/test", site)
    assert status == 200 and content_type.startswith("text/html")
    return body.decode("utf-8")


def script_of(html: str) -> str:
    return re.search(r"<script>(.*?)</script>", html, re.DOTALL).group(1)


def settings_of(html: str) -> dict:
    return json.loads(re.search(r'<script type="application/json" id="settings">(.*?)</script>', html, re.DOTALL).group(1))


def deck_of(html: str) -> list[dict]:
    return settings_of(html)["deck"]


@pytest.fixture
def visit(library):
    """A visit to the page: its id and the questions of its deck, in the order they are asked."""
    settings = settings_of(page_of(library))
    return settings["session"], [item["question"] for item in settings["deck"]]


def sent(visit, number: int = 0, **changes) -> dict:
    """The answer the page sends for the visit's `number`th comparison."""
    session, questions = visit
    return {"session": session, "question": questions[number], **PAIR, **changes}


def visit_asking(library, question: str) -> tuple[str, list[str]]:
    """A visit whose deck holds `question` (about one in two of the visits to the made-up cards' page do)."""
    for _ in range(100):
        settings = settings_of(page_of(library))
        questions = [item["question"] for item in settings["deck"]]
        if question in questions:
            return settings["session"], questions
    raise AssertionError(question)


def function_body(script: str, signature: str) -> str:
    found = re.search(re.escape(signature) + r" \{(.*?)\n  \}", script, re.DOTALL)
    assert found, signature
    return found.group(1)


def worst_cards() -> dict:
    """Every question with three picks of the longest name and the longest why (20 words, in two languages)."""
    cards = made_up_cards()
    long_why = {"en": " ".join(["resilient"] * 20), "it": " ".join(["resistente"] * 20)}
    for q in cards["questions"]:
        q["text"] = {"en": "x" * 90, "it": "y" * 90}
        for tool in q["answers"]:
            q["answers"][tool] = {"picks": [{"name": "N" * 60, "why": dict(long_why)} for _ in range(3)], "note": None}
    return cards


# --- GET /test ---

def test_the_test_page_is_a_standalone_page_with_one_fresh_deck_inside(library):
    html = page_of(library)
    deck = deck_of(html)
    assert len(deck) == 6 and len({item["question"] for item in deck}) == 6
    assert set(deck[0]) == {"question", "text", "cards"}  # never which tool the other card is, or which side is ours
    settings = settings_of(html)
    assert set(settings) == {"deck", "session", "whyMax", "closed"} and settings["closed"] is False
    assert feedback._PAIR_SESSION.fullmatch(settings["session"])  # the visit's id, made by the server


def test_every_visitor_gets_a_new_deck(library, monkeypatch):
    decks = []
    for seed in (1, 2):
        monkeypatch.setattr(web, "_deck_random", random.Random(seed))
        decks.append(deck_of(page_of(library)))
    assert decks[0] != decks[1]
    monkeypatch.setattr(web, "_deck_random", random.Random(1))
    html = page_of(library)
    assert deck_of(html) == decks[0]
    # the deck is worked out from the visit's id, as it will be again when its answers come in
    cards = pair_test.cards_in(library)
    full = pair_test.deck_for(cards, settings_of(html)["session"], web._deck_key)
    assert decks[0] == pair_test.public_deck(full)


def test_two_visits_never_share_an_id(library):
    assert len({settings_of(page_of(library))["session"] for _ in range(50)}) == 50


def test_the_page_names_no_site_and_links_nowhere(library):
    html = page_of(library)
    lowered = html.lower()
    for word in ("credible", "recs", "reddit", "href", "<a ", "http", "src=", "<img", "<iframe", "<form", "/how", "/api/answer"):
        assert word not in lowered, word
    assert "<noscript>" in lowered  # without JavaScript the page says it needs it, in both languages
    assert '<meta name="robots" content="noindex">' in html


def test_the_rest_of_the_site_never_mentions_the_test(library):
    def mentions(text: str) -> bool:  # "/test" as a route, not "/tests/" or "/test_web_ux.py" in a comment
        return bool(re.search(r"/test(?!\w)|test-response", text))

    assert not mentions(web.search_page().decode("utf-8"))
    assert not mentions(get(library, "/how")[2].decode("utf-8"))
    assert not mentions(get(library, "/nowhere")[2].decode("utf-8"))
    assert not mentions(web.NOT_FOUND[1])
    assert mentions("the page is at /test") and mentions("POST /api/test-response")  # the check itself works


def test_the_intro_is_two_sentences_in_english_and_in_italian(library):
    html = page_of(library)
    assert ("Compare two answers to a shopping question and pick the one you'd trust with your own money. "
            "It takes about 4 minutes, and it's anonymous.") in html
    assert ("Confronta due risposte a una domanda di shopping e scegli quella di cui ti fideresti per spendere i tuoi "
            "soldi. Ci vogliono circa 4 minuti ed è anonimo.") in html


def test_the_page_has_the_three_buttons_and_the_optional_why_in_both_languages(library):
    script = script_of(page_of(library))
    for words in ('same: "About the same"', 'same: "Più o meno uguali"', 'whyLabel: "Why? (optional)"',
                  'whyLabel: "Perché? (facoltativo)"', 'thanksTitle: "Thank you!"', 'thanksTitle: "Grazie!"',
                  'progress: "Question {n} of {total}"', 'progress: "Domanda {n} di {total}"'):
        assert words in script, words
    assert "maxlength" in script.lower() and "settings.whyMax" in script
    assert 'answer: "Answer {letter}"' in script and 'answer: "Risposta {letter}"' in script


def test_the_language_comes_from_the_browser_and_can_be_switched(library):
    html = page_of(library)
    script = script_of(html)
    assert "navigator.languages" in script and 'startsWith("it")' in script
    assert "aria-pressed" in script
    assert html.count("<html lang=\"en\">") == 1


def test_the_page_counts_the_comparisons_the_deck_holds_and_shows_one_a_screen(library):
    script = script_of(page_of(library))
    assert "state.deck.length" in script
    assert "function showQuestion()" in script and "function showIntro()" in script and "function showThanks()" in script


def test_a_card_shows_each_pick_by_name_and_why_or_the_note_when_there_are_no_picks(library):
    body = function_body(script_of(page_of(library)), "function cardElement(card, letter)")
    assert "pick.name" in body and "pick.why[state.language]" in body
    assert "card.note[state.language]" in body
    assert "innerHTML" not in script_of(page_of(library))  # every text goes in as text


def test_nothing_the_visitor_can_read_says_which_side_is_ours_or_who_the_rival_is(library):
    """25 Oct 2026: found by trying the page, which had carried both in its data block, and so in the page's source and
    in a tab's session storage. Now the server keeps them (the visit's id works them out, with a key only it has), so no
    word of the page's whole source, its comments and its data included, says either."""
    html = page_of(library)
    assert not re.search(r"\b(ours_side|rival|ours|chatgpt|vetted|openai)\b", html, re.IGNORECASE)
    script = script_of(html)
    assert "setAttribute(\"data-" not in script and "dataset" not in script
    assert "console." not in script


def test_a_visits_deck_is_the_same_whichever_instance_asks_for_it_and_only_the_server_can_work_it_out(library):
    cards = pair_test.cards_in(library)
    settings = settings_of(page_of(library))
    full = pair_test.deck_for(cards, settings["session"], web._deck_key)
    assert [(item["question"], item["cards"]) for item in full] == [(item["question"], item["cards"])
                                                                   for item in settings["deck"]]
    another_server = pair_test.deck_key({"CREDIBLE_RECS_TEST_KEY": "not this server's"})
    assert pair_test.deck_for(cards, settings["session"], another_server) != full


def test_the_pages_script_sends_exactly_the_fields_the_server_takes(library):
    script = script_of(page_of(library))
    body = function_body(script, "function answerRecord(item, choice, why)")
    sent = set(re.findall(r"^\s+(\w+):", body, re.MULTILINE))
    assert sent == set(feedback.PAIR_REQUIRED) | set(feedback.PAIR_OPTIONAL)
    assert not {"rival", "ours_side"} & sent  # the server works those out
    assert "settings.session" in script and "getRandomValues" not in script  # the visit's id is the server's
    assert len(re.findall(r"\bfetch\(", script)) == 1 and '"/api/test-response"' in script


def test_the_page_keeps_nothing_in_the_browser_but_its_place_for_this_visit(library):
    script = script_of(page_of(library))
    assert "localStorage" not in script and "document.cookie" not in script and "indexedDB" not in script
    assert len(re.findall(r"sessionStorage\.setItem\(", script)) == 1


def test_a_card_with_markup_in_it_cannot_break_out_of_the_page(tmp_path):
    cards = made_up_cards()
    for q in cards["questions"]:
        q["text"]["en"] = "</script><b>question</b>"
        for tool in ("ours", "chatgpt", "vetted"):
            q["answers"][tool]["picks"][:1] = [pick("</script><img src=x onerror=alert(1)>")] if q["answers"][tool]["picks"] else []
    html = page_of(write_cards(tmp_path / "library", cards))
    assert "</script><b>" not in html and "<img" not in html.lower()
    assert html.lower().count("<script") == 2  # the deck's data and the page's script
    assert deck_of(html)[0]["text"]["en"] == "</script><b>question</b>"


def test_the_test_is_closed_with_a_plain_page_when_the_cards_are_missing_or_wrong(tmp_path):
    for folder in (tmp_path / "none", write_cards(tmp_path / "wrong", {**made_up_cards(), "version": 9})):
        status, content_type, body = get(folder)
        text = body.decode("utf-8")
        assert status == 503 and content_type.startswith("text/html")
        assert "isn't open" in text and "non è ancora aperto" in text
        assert not re.search(r"credible|href|chatgpt|vetted|\bours\b|blind_test_cards", text.lower())


def test_the_page_is_sent_uncached_and_within_its_budget(library):
    server = start(web.make_server(port=0, library_dir=library))
    try:
        request = urllib.request.Request(f"{own_origin(server)}/test")
        with urllib.request.urlopen(request, timeout=10) as response:
            headers, body = dict(response.headers), response.read()
    finally:
        stop(server)
    assert headers["Cache-Control"] == "no-store" and headers["Content-Type"].startswith("text/html")
    assert "connect-src 'self'" in headers["Content-Security-Policy"]
    assert len(body) <= PAGE_BUDGET_BYTES


# --- Size and contrast ---

def test_the_page_with_the_longest_cards_stays_within_its_size_budget(tmp_path):
    library = write_cards(tmp_path / "library", worst_cards())
    biggest = web.Site(public=True, hosts=(HOST,), goatcounter="credible-recs")
    html = page_of(library, biggest)
    assert len(html.encode("utf-8")) <= PAGE_BUDGET_BYTES
    assert len(deck_of(html)) == 6
    template = web.TEST_TEMPLATE.read_text(encoding="utf-8")
    assert len(template.encode("utf-8")) <= TEMPLATE_BUDGET_BYTES


def test_the_page_with_ordinary_cards_is_smaller_still(library):
    assert len(page_of(library).encode("utf-8")) <= TYPICAL_BUDGET_BYTES


def test_the_page_loads_nothing_and_counts_nobody(library):
    html = page_of(library, web.Site(public=True, hosts=(HOST,), goatcounter="credible-recs"))
    assert "goatcounter" not in html.lower() and "gc.zgo.at" not in html


def css_of(html: str) -> str:
    return re.search(r"<style>(.*?)</style>", html, re.DOTALL).group(1)


# Every pair of text colour and the background it is drawn on, by token name.
TEXT_ON = [("text", "bg"), ("text", "surface"), ("text", "sunken"), ("muted", "bg"), ("muted", "surface"),
           ("muted", "sunken"), ("accent", "bg"), ("accent", "surface"), ("accent", "accent-soft"),
           ("on-accent", "accent"), ("bad", "bad-soft"), ("bad", "bg"), ("text", "accent-soft")]
# What shows a control or a card's edge needs 3:1 against what it sits on (WCAG 1.4.11).
EDGES_ON = [("control", "bg"), ("control", "surface"), ("accent", "bg"), ("accent", "surface")]


def test_every_text_colour_meets_wcag_aa_contrast_in_light_and_dark(library):
    css = css_of(page_of(library))
    for mode, tokens in zip(("light", "dark"), _tokens(css)):
        for colour, ground in TEXT_ON:
            ratio = _contrast(tokens[colour], tokens[ground])
            assert ratio >= 4.5, f"{mode}: {colour} on {ground} is {ratio:.2f}:1"


def test_the_edges_of_the_buttons_and_fields_meet_three_to_one_in_light_and_dark(library):
    css = css_of(page_of(library))
    for mode, tokens in zip(("light", "dark"), _tokens(css)):
        for colour, ground in EDGES_ON:
            ratio = _contrast(tokens[colour], tokens[ground])
            assert ratio >= 3.0, f"{mode}: {colour} on {ground} is {ratio:.2f}:1"


def test_the_page_follows_the_computers_light_or_dark_setting_and_reduced_motion(library):
    html = page_of(library)
    css = css_of(html)
    assert '<meta name="color-scheme" content="light dark">' in html
    assert "@media (prefers-color-scheme: dark)" in css and "color-scheme: light dark" in css
    assert "prefers-reduced-motion" in css
    assert re.search(r"body \{[^}]*background: var\(--bg\)", css)


def test_the_page_is_made_for_a_phone_first(library):
    html = page_of(library)
    css = css_of(html)
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html
    assert re.search(r"min-height: (4[4-9]|[5-9]\d)px", css)  # buttons are easy to hit with a thumb
    assert "@media (min-width" in css  # two cards side by side only where there is room


def test_the_look_is_the_sites_own_palette(library):
    search_css = re.search(r"<style>(.*?)</style>", web.PAGE_TEMPLATE.read_text(encoding="utf-8"), re.DOTALL).group(1)
    ours, theirs = _tokens(css_of(page_of(library))), _tokens(search_css)
    for mode in (0, 1):
        for name in ("bg", "surface", "sunken", "text", "muted", "accent", "accent-hover", "accent-soft", "on-accent",
                     "bad", "bad-soft"):
            assert ours[mode][name] == theirs[mode][name], (mode, name)


# --- POST /api/test-response, the answers ---

def post_pair(body, library, content_type="application/json"):
    data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
    status, kind, response = web.handle_test_response(content_type, str(len(data)), io.BytesIO(data).read, library)
    return status, kind, json.loads(response)


def test_an_answer_is_kept_as_a_blind_pair_with_the_time_and_nothing_about_the_sender(library, fake_store, visit):
    status, content_type, data = post_pair(sent(visit), library)
    assert status == 200 and content_type.startswith("application/json")
    assert data == {"saved": True}  # nothing of the answer, least of all the side, comes back
    (record,) = fake_store.records
    assert record["kind"] == "blind_pair" and record["choice"] == "B"
    assert set(record) == set(sent(visit)) | {"kind", "received_at", "rival", "ours_side"}


def test_each_answer_is_kept_with_the_rival_and_the_side_the_visits_own_cards_were_shown_on(library, fake_store):
    questions = {q["id"]: q["answers"] for q in pair_test.cards_in(library)["questions"]}
    settings = settings_of(page_of(library))
    asked = [item["question"] for item in settings["deck"]]
    for number in range(len(asked)):
        assert post_pair(sent((settings["session"], asked), number), library)[0] == 200
    assert [record["question"] for record in fake_store.records] == asked
    for record, shown in zip(fake_store.records, settings["deck"]):
        other = "B" if record["ours_side"] == "A" else "A"
        # what the visitor was shown on each side is the card of the tool the record says it was
        assert shown["cards"][record["ours_side"]] == questions[record["question"]]["ours"]
        assert shown["cards"][other] == questions[record["question"]][record["rival"]]
    assert {record["rival"] for record in fake_store.records} == {"chatgpt", "vetted"}
    assert [record["ours_side"] for record in fake_store.records].count("A") == 3


def test_an_answer_for_a_question_the_test_does_not_have_is_refused(library, fake_store, visit):
    status, _, data = post_pair(sent(visit, question="z99"), library)
    assert status == 400 and data["code"] == "bad_feedback" and "z99" in data["error"] and fake_store.records == []


def test_an_answer_for_a_question_this_visit_was_not_asked_is_refused(library, fake_store, visit):
    session, asked = visit
    not_asked = next(question for question in QUESTION_IDS if question not in asked)
    status, _, data = post_pair(sent(visit, question=not_asked), library)
    assert status == 400 and data["code"] == "bad_feedback" and not_asked in data["error"] and fake_store.records == []


def test_the_page_may_not_send_the_rival_or_the_side(library, fake_store, visit):
    for extra in ({"rival": "chatgpt"}, {"ours_side": "A"}):
        status, _, data = post_pair({**sent(visit), **extra}, library)
        assert status == 400 and data["code"] == "bad_feedback" and fake_store.records == []


def test_an_answer_from_a_visit_the_server_did_not_make_is_not_matched_to_a_deck(library, fake_store):
    status, _, data = post_pair({**PAIR, "session": "k3j9x0a7q2m5p8w1", "question": "b01"}, library)
    assert status == 400 and data["code"] == "bad_feedback" and fake_store.records == []


def test_an_answer_that_arrives_after_the_cards_changed_is_refused_not_given_the_wrong_side(library, fake_store, visit,
                                                                                             tmp_path):
    cards = made_up_cards()
    cards["questions"] = cards["questions"][:8]
    changed = write_cards(tmp_path / "changed", cards)
    status, _, data = post_pair(sent(visit), changed)
    assert status == 400 and fake_store.records == []


def test_every_question_of_the_cards_is_taken(library, fake_store):
    for question in QUESTION_IDS:
        session, questions = visit_asking(library, question)
        assert post_pair({"session": session, "question": question, **PAIR}, library)[0] == 200
    assert len(fake_store.records) == len(QUESTION_IDS)


def test_an_answer_is_refused_with_the_feedback_routes_codes_and_nothing_is_kept(library, fake_store, visit):
    assert post_pair(sent(visit), library, "text/plain")[::2] == (415, {"error": web.NOT_JSON[1], "code": "not_json"})
    assert post_pair(b"{not json", library)[0] == 400
    assert post_pair(b'{"session": "a", "session": "b"}', library)[2]["code"] == "bad_json"
    assert post_pair({**sent(visit), "ip": "203.0.113.7"}, library)[2]["code"] == "bad_feedback"
    assert post_pair({"kind": "blind_pair", **sent(visit)}, library)[2]["code"] == "bad_feedback"
    assert post_pair({**sent(visit), "why": "w" * 301}, library)[2]["code"] == "bad_feedback"
    assert post_pair({**sent(visit), "choice": "both"}, library)[2]["code"] == "bad_feedback"
    assert fake_store.records == []


def test_the_size_limit_is_the_feedbacks_and_the_body_is_not_read_beyond_it(library, fake_store):
    def never_read(size):
        raise AssertionError("the body should not have been read")

    status, _, body = web.handle_test_response("application/json", str(FEEDBACK_MAX_BODY_BYTES + 1), never_read, library)
    assert status == 413 and json.loads(body)["code"] == "too_large"
    assert web.handle_test_response("application/json", None, never_read, library)[0] == 411
    assert web.handle_test_response("application/json", "abc", never_read, library)[0] == 400


def test_the_longest_real_answer_fits_the_size_limit(library, fake_store, visit):
    longest = sent(visit, why="長" * 300)
    assert len(json.dumps(longest, ensure_ascii=False).encode("utf-8")) <= FEEDBACK_MAX_BODY_BYTES
    assert post_pair(longest, library)[0] == 200


def test_an_answer_that_cant_be_kept_right_now_says_so(library, monkeypatch, visit):
    monkeypatch.setattr(web, "store", FakeStore(fail=True))
    status, _, data = post_pair(sent(visit), library)
    assert status == 503 and data["code"] == "feedback_unavailable"
    monkeypatch.setattr(web, "store", None)
    assert post_pair(sent(visit), library)[0] == 503


def test_without_cards_no_answer_is_taken(tmp_path, fake_store, visit):
    status, _, data = post_pair(sent(visit), tmp_path / "none")
    assert status == 503 and data["code"] == "test_closed" and fake_store.records == []


def test_the_answers_go_through_the_same_store_as_other_feedback(library, tmp_path, monkeypatch, visit):
    local = feedback.LocalStore(tmp_path / "feedback.jsonl")
    monkeypatch.setattr(web, "store", local)
    assert post_pair(sent(visit), library)[0] == 200
    (record,) = feedback.read_pairs([tmp_path / "feedback.jsonl"])
    assert record["kind"] == "blind_pair" and record["session"] == visit[0]


# --- Over HTTP ---

@pytest.fixture
def local_server(library):
    server = start(web.make_server(port=0, library_dir=library))
    yield server
    stop(server)


@pytest.fixture
def public_server(library, monkeypatch):
    monkeypatch.setattr(web, "PUBLIC_HOST", "127.0.0.1")
    server = start(web.make_server(port=0, library_dir=library, site=PUBLIC))
    yield server
    stop(server)


JSON_FROM_HERE = {"Content-Type": "application/json"}


def public_send(server, path, body=None, client="203.0.113.7", headers=None):
    return send(server, path, body, {"Host": HOST, "X-Forwarded-For": f"{client}, 10.16.0.1", **(headers or {})})


def test_the_local_page_can_send_an_answer(local_server, fake_store, visit):
    status, _, data = send(local_server, "/api/test-response", sent(visit), {**JSON_FROM_HERE, "Origin": own_origin(local_server)})
    assert status == 200 and data == {"saved": True} and len(fake_store.records) == 1


@pytest.mark.parametrize("headers", [{}, {"Origin": "https://evil.example"}, {"Origin": "null"},
                                     {"Referer": "https://evil.example/test"}])
def test_an_answer_from_another_website_or_from_nowhere_is_refused(local_server, fake_store, visit, headers):
    status, _, data = send(local_server, "/api/test-response", sent(visit), {**JSON_FROM_HERE, **headers})
    assert status == 403 and data["code"] == "cross_site" and fake_store.records == []


def test_an_answer_addressed_to_another_host_is_refused(local_server, fake_store, visit):
    headers = {**JSON_FROM_HERE, "Host": "evil.example", "Origin": "http://evil.example"}
    assert send(local_server, "/api/test-response", sent(visit), headers)[0] == 403 and fake_store.records == []


def test_the_routes_take_only_their_own_method(local_server, visit):
    status, headers, data = send(local_server, "/api/test-response")
    assert status == 405 and data["code"] == "method_not_allowed" and headers["Allow"] == "POST"
    status, headers, data = send(local_server, "/test", sent(visit), {**JSON_FROM_HERE, "Origin": own_origin(local_server)})
    assert status == 405 and headers["Allow"] == "GET"


def test_the_public_site_serves_the_page_and_takes_answers_for_its_own_host_only(public_server, fake_store, visit):
    request = urllib.request.Request(f"{own_origin(public_server)}/test", headers={"Host": HOST})
    with urllib.request.urlopen(request, timeout=10) as response:
        assert response.status == 200
    headers = {**JSON_FROM_HERE, "Origin": f"https://{HOST}"}
    assert public_send(public_server, "/api/test-response", sent(visit), headers=headers)[0] == 200
    assert public_send(public_server, "/api/test-response", sent(visit), headers={**headers, "Origin": "https://evil.example"})[0] == 403
    assert public_send(public_server, "/api/test-response", sent(visit), headers={**headers, "Host": "evil.example"})[0] == 403
    (record,) = fake_store.records
    assert "203.0.113.7" not in json.dumps(record) and "10.16.0.1" not in json.dumps(record)


def test_answers_have_a_rate_limit_of_their_own_that_leaves_room_for_several_tests(public_server, fake_store, visit):
    assert RATE_LIMIT_PAIRS >= 3 * pair_test.QUESTIONS_PER_VISITOR  # friends on one network, or a retried answer
    assert RATE_LIMIT_PAIRS >= RATE_LIMIT_FEEDBACK
    public_server.limits["pairs"] = web.RateLimiter(2, 600)
    headers = {**JSON_FROM_HERE, "Origin": f"https://{HOST}"}
    assert [public_send(public_server, "/api/test-response", sent(visit), headers=headers)[0] for _ in range(2)] == [200, 200]
    status, response_headers, data = public_send(public_server, "/api/test-response", sent(visit), headers=headers)
    assert status == 429 and data["code"] == "too_many_requests" and int(response_headers["Retry-After"]) > 0
    assert public_send(public_server, "/api/test-response", sent(visit), client="198.51.100.4", headers=headers)[0] == 200
    assert len(fake_store.records) == 3


def test_the_answers_limit_and_the_feedback_limit_do_not_use_each_other_up(public_server, fake_store, visit):
    public_server.limits["feedback"] = web.RateLimiter(1, 600)
    headers = {**JSON_FROM_HERE, "Origin": f"https://{HOST}"}
    useful = {"kind": "first_time", "answer": "yes"}
    assert public_send(public_server, "/api/feedback", useful, headers=headers)[0] == 200
    assert public_send(public_server, "/api/feedback", useful, headers=headers)[0] == 429
    assert public_send(public_server, "/api/test-response", sent(visit), headers=headers)[0] == 200


def test_local_mode_has_no_rate_limit_on_answers(local_server, fake_store, visit):
    local_server.limits["pairs"] = web.RateLimiter(1, 600)
    headers = {**JSON_FROM_HERE, "Origin": own_origin(local_server)}
    assert [send(local_server, "/api/test-response", sent(visit), headers)[0] for _ in range(3)] == [200] * 3


def test_the_feedback_route_still_refuses_a_pairwise_answer(local_server, fake_store, visit):
    headers = {**JSON_FROM_HERE, "Origin": own_origin(local_server)}
    status, _, data = send(local_server, "/api/feedback", {"kind": "blind_pair", **sent(visit)}, headers)
    assert status == 400 and data["code"] == "bad_feedback" and fake_store.records == []


def test_the_page_is_never_rate_limited(public_server):
    public_server.limits["pairs"] = web.RateLimiter(1, 600)
    for _ in range(3):
        request = urllib.request.Request(f"{own_origin(public_server)}/test", headers={"Host": HOST})
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.status == 200


# --- Getting it to the live site ---

def test_the_cards_file_goes_into_the_sites_image_with_the_library(tmp_path):
    from deploy.cloudrun import make_context

    library = write_cards(tmp_path / "repo" / "data" / "library")
    out = tmp_path / "bundle"
    make_context.copy_library(library, out / "data" / "library")
    copied = out / "data" / "library" / "blind_test_cards.json"
    assert copied.is_file() and json.loads(copied.read_text(encoding="utf-8"))["version"] == 1


def test_the_cards_file_is_git_ignored_with_the_library():
    # data/library is a symlink in a worktree, which git check-ignore won't look through: read the rule itself.
    from pathlib import Path

    ignore = (Path(web.__file__).resolve().parents[1] / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/library/" in ignore  # the cards hold the rivals' answers: they are never committed


# --- Trying the page on this computer: python -m engine.pair_test serve ---

def test_the_trial_server_serves_the_page_and_keeps_answers_in_its_own_file(library, tmp_path, monkeypatch):
    monkeypatch.setattr(web, "store", None)
    trial = tmp_path / "trial.jsonl"
    server = start(pair_test.trial_server(library, trial, port=0))
    try:
        request = urllib.request.Request(f"{own_origin(server)}/test")
        with urllib.request.urlopen(request, timeout=10) as response:
            assert response.status == 200
            settings = settings_of(response.read().decode("utf-8"))
        answer = {"session": settings["session"], "question": settings["deck"][0]["question"], **PAIR}
        status, _, data = send(server, "/api/test-response", answer, {**JSON_FROM_HERE, "Origin": own_origin(server)})
        assert status == 200 and data == {"saved": True}
    finally:
        stop(server)
    (record,) = feedback.read_pairs([trial])
    assert record["session"] == settings["session"] and record["kind"] == "blind_pair"
    assert record["rival"] in feedback.PAIR_RIVALS and record["ours_side"] in feedback.PAIR_SIDES


def test_the_trial_servers_options():
    assert pair_test.trial_options([]) == (pair_test.TRIAL_PORT, pair_test.LIBRARY_DIR, pair_test.TRIAL_STORE)
    port, library, store = pair_test.trial_options(["--port", "9001", "--cards", "/some/folder", "--store", "/x/y.jsonl"])
    assert (port, str(library), str(store)) == (9001, "/some/folder", "/x/y.jsonl")
    for bad in (["--port"], ["--port", "x"], ["--nothing", "1"], ["--port", "1", "--port"]):
        assert pair_test.trial_options(bad) is None


def test_the_trial_store_is_not_the_real_feedback_file():
    assert pair_test.TRIAL_STORE != feedback.DEFAULT_FILE and pair_test.TRIAL_STORE.parent == feedback.DEFAULT_FILE.parent
