"""Module 8, the interface (a local demo): a search page and a small JSON API, served from this machine only.

Someone types a need ("electric kettle that lasts 10+ years") into the page; the page asks the API; the API runs
modules 1 to 7 (engine.pipeline) and sends the answer back as JSON; the page draws it as cards. Nothing here
decides anything: every word of an answer comes from engine/answer.py, and every quote has passed its
word-for-word check there. Before an answer leaves the server it is checked once more (unverified_claims): if
any quote fails, the whole answer is refused (HTTP 500) and nothing from it is shown.

Local only: the server listens on 127.0.0.1, so only this computer can reach it, and it answers only requests
addressed to 127.0.0.1 or localhost (a page on another website can't reach it through a trick called DNS
rebinding). It uses Python's standard library only. The final website (Next.js, with a FastAPI service) is a
later decision; the JSON below is the contract it will use.

Routes (GET only):
    /                       the search page (engine/templates/search.html)
    /how                    the how-we-score page (engine/how_page.py): how an answer is made and scored, in plain
                            words, and the latest evaluation results, read from eval/metrics.json each time it is
                            opened (10 Oct 2026)
    /api/answer?q=<request> the answer to one request, as JSON
    anything else           404

The JSON for /api/answer (200):
    {
      "query": {"status": "ok" | "clarify" | "out_of_scope",  module 1's outcome
                "category": "skincare" | "kitchen" | null,
                "product_type": "electric kettle" | null,
                "question": "..." | null,     the one clarifying question, when status is "clarify"
                "message": "..." | null},     the polite no, when status is "out_of_scope"
      "answer": null when status isn't "ok", else engine.answer.answer_to_dict(...):
                {"category", "product_type",
                 "picks": [{"rank", "product_key", "name", "reason", "support",
                            "quotes": [{"text", "comment_id", "url", "badges": [...]}],   2 or 3, all verified
                            "downsides": [same shape as quotes], "disagreement": "..." | null,
                            "score", "breakdown": {every number behind the score (engine.rank.ScoreBreakdown)},
                            "price": {"text",                  "£120 at <shop>, checked 9 Oct 2026" or
                                                               "Price not checked yet"
                                      "amount", "currency", "shop", "checked_on",   null when not known
                                      "url",                   the shop's own page, https only, or null
                                      "budget_status",         "within" | "unknown" | "other currency" |
                                                               "out of date", or null without a budget
                                      "budget_note"},          the same in words, or null
                            "availability": {"text",           "Sold at <shop>, checked 9 Oct 2026",
                                                               "Sold second-hand only: <shop>, checked
                                                               10 Oct 2026" (10 Oct 2026), or
                                                               "Availability not checked yet" (9 Oct 2026)
                                             "available",      true, or null when not checked
                                             "second_hand",    true when no longer made and sold second-hand
                                                               only (Noemi, 10 Oct 2026), else false
                                             "shop", "checked_on",   null when not checked
                                             "url"},           the shop's own page, https only; null when not
                                                               checked or when the price line links to it
                            "care": [{"tip": "Descale every 6 months.",   "How to make it last" (9 Oct 2026):
                                      "quote": {same shape}}],            0 to 2, each quote verified
                            "cautions": ["Note: ..."],         product facts that suit the request less well
                                                               (9 Oct 2026); [] when there are none
                            "model": "Victorinox Fibrox..."}], a brand pick's most recommended model (10 Oct
                                                               2026); null for other picks
                 "look_for": [{"kind", "advice", "quote": {same shape}}],
                 "skip": [{"product_key", "name", "reason", "quotes": [...]}],
                 "message": the honest "not enough evidence" message, or null when there are 3 picks,
                 "needs_more_threads", "quotes_dropped"},
      "threads_used": ["thread id", ...],          most relevant first
      "left_out": {"other_type": n, "loose": n,    products of another type, and brand or line names, left out
                   "over_budget": n,               products whose known price is over the request's budget
                   "unavailable": n,               products the price list says are no longer sold (9 Oct 2026),
                   "not_suited": n}                and products whose checked facts clash with the request (9 Oct 2026)
    }
An error is {"error": "<plain words>", "code": "<one word for programs>"}:
    400 empty_request, request_too_long (over WEB_MAX_REQUEST_CHARS characters)
    403 wrong_host        a request not addressed to this computer
    404 not_found
    500 quote_not_verified (the answer is refused), engine_failed (details in the server's window, never sent)
The words are for whoever calls the API; the page picks its own words by code (PROPOSED, at the top of the page).

Answers take about 2 seconds, so each one is remembered for as long as the server runs: asking again is instant.
A library refresh needs a restart to show.

Command line:
    python -m engine.web [--port N] [--library DIR]    serves the page at http://127.0.0.1:8765/ (Ctrl+C stops it)
"""

import json
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from engine import answer as wording
from engine import how_page
from engine.answer import answer_to_dict, unverified_claims
from engine.config import BRAND_PICK_MODEL, WEB_MAX_REQUEST_CHARS, WEB_PORT
from engine.library import DEFAULT_LIBRARY_DIR
from engine.metrics import METRICS_FILE
from engine.parse_reddit import REPO_ROOT
from engine.pipeline import PipelineResult, answer_request

HOST = "127.0.0.1"  # this computer only. Never "0.0.0.0", which would open the server to the whole network.
PAGE_TEMPLATE = Path(__file__).resolve().parent / "templates" / "search.html"
EXAMPLES_FILE = REPO_ROOT / "eval" / "blind_test" / "questions.json"  # the 10 approved blind-test questions

HTML = "text/html; charset=utf-8"
JSON = "application/json; charset=utf-8"

# Sent with every response. The page may load and call nothing but this server: no outside scripts, styles, fonts
# or images, and no requests elsewhere. Its links still open, in a new tab: to Reddit, and to a shop's own page for a
# price or for where a product is sold (https only, from data/prices.json; decision 11 and availability, 9 Oct 2026).
HEADERS = {
    "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
                               "connect-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}

# The API's errors: a code for programs, and plain words for whoever calls the API (the page has its own wording).
EMPTY_REQUEST = ("empty_request", "Type what you're looking for: the request is empty.")
TOO_LONG = ("request_too_long", "The request is {n} characters long; the limit is {limit}.")
NOT_FOUND = ("not_found", "Nothing here. The search page is at /, how we score at /how, and answers at "
                          "/api/answer?q=<request>.")
WRONG_HOST = ("wrong_host", "This server only answers requests addressed to 127.0.0.1 or localhost.")
REFUSED = ("quote_not_verified",
           "This answer was not shown: a quote in it could not be checked word for word against its comment.")
ENGINE_FAILED = ("engine_failed", "The engine could not answer this request. The details are in the server's window.")


# Answers already worked out, by (request, library folder), kept until the server stops.
_answers: dict[tuple[str, str], tuple[int, str, bytes]] = {}
# Where writers' standing comes from (engine.pipeline's `profiles`): the command line sets the Arctic Shift cache
# (engine.profiles.CachedOnly, never a call); None, as in the tests, leaves writers known by name only.
profiles = None
# The live check of every shown quote (engine.live_check): set by the command line; None in the tests.
live = None
_answers_lock = threading.Lock()


# --- Routing: one GET request in, one response out ---

def handle_request(path_and_query: str, library_dir: Path = DEFAULT_LIBRARY_DIR) -> tuple[int, str, bytes]:
    """What the server sends back for one GET request: (status code, content type, body).

    A plain function, with no network in it, so the tests can call it directly.
    """
    parts = urlsplit(path_and_query)
    if parts.path == "/":
        return 200, HTML, search_page()
    if parts.path == "/how":
        return 200, HTML, how_page.page(METRICS_FILE).encode("utf-8")  # read now: a new evaluation run shows at once
    if parts.path == "/api/answer":
        request = parse_qs(parts.query).get("q", [""])[0]
        return answer_response(request, Path(library_dir))
    return _error(404, NOT_FOUND)


def answer_response(request: str, library_dir: Path) -> tuple[int, str, bytes]:
    """The answer to one request as JSON, remembered for next time; or an error."""
    request = request.strip()
    if not request:
        return _error(400, EMPTY_REQUEST)
    if len(request) > WEB_MAX_REQUEST_CHARS:
        return _error(400, TOO_LONG, n=len(request), limit=WEB_MAX_REQUEST_CHARS)
    key = (request, str(library_dir))
    with _answers_lock:  # one answer is worked out at a time, so the same request is never worked out twice
        if key not in _answers:
            try:
                _answers[key] = _fresh_answer(request, library_dir)
            except Exception:  # a broken library file, say: reported in the server's window, never sent
                traceback.print_exc()
                return _error(500, ENGINE_FAILED)  # not remembered: fixing the file and asking again works
        return _answers[key]


def _fresh_answer(request: str, library_dir: Path) -> tuple[int, str, bytes]:
    """Runs the pipeline, then checks every quote once more; one that fails refuses the whole answer."""
    with_profiles = {} if profiles is None else {"profiles": profiles}
    if live is not None:
        with_profiles["live_checker"] = live
    result = answer_request(request, library_dir, **with_profiles)
    if result.answer is not None:
        problems = unverified_claims(result.answer, result.bodies)
        if problems:  # the problems name comments, never the failed quote's words
            print(f"Refused the answer to {request!r}:", *problems, sep="\n  - ", file=sys.stderr)
            return _error(500, REFUSED)
    return 200, JSON, _json_bytes(answer_json(result))


def answer_json(result: PipelineResult) -> dict:
    """The pipeline's result in the shape the page (and the later website) reads: see the top of this file."""
    query = result.query
    return {
        "query": {"status": query.status, "category": query.category, "product_type": query.product_type,
                  "question": query.question, "message": query.message},
        "answer": answer_to_dict(result.answer) if result.answer is not None else None,
        "threads_used": list(result.threads_used),
        "left_out": {"other_type": len(result.left_out_as_other_type), "loose": len(result.left_out_loose),
                     "over_budget": len(result.left_out_over_budget),
                     "unavailable": len(result.left_out_unavailable),
                     "not_suited": len(result.left_out_not_suited)},
    }


def clear_answer_cache() -> None:
    """Forgets every remembered answer (the tests use it; restarting the server does the same)."""
    with _answers_lock:
        _answers.clear()


def _error(status: int, error: tuple[str, str], **details) -> tuple[int, str, bytes]:
    """An error response: {"error": its words, with any details filled in, "code": its code}."""
    code, message = error
    return status, JSON, _json_bytes({"error": message.format(**details), "code": code})


def _json_bytes(data: dict) -> bytes:
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


# --- The page ---

def search_page() -> bytes:
    """The search page: the template, with the answer's own headings and the example requests filled in."""
    settings = {"wording": answer_wording(), "examples": example_requests(), "maxChars": WEB_MAX_REQUEST_CHARS}
    template = PAGE_TEMPLATE.read_text(encoding="utf-8")
    return template.replace("{{SETTINGS}}", _script_json(settings)).encode("utf-8")


def answer_wording() -> dict[str, str]:
    """The answer's headings and fixed sentences (engine/answer.py), so the page uses exactly the same words."""
    return {
        "title": wording.TITLE,  # "Top picks: {product_type}"
        "title_any": wording.TITLE_ANY,
        "support_label": wording.SUPPORT_LABEL,
        "quotes_heading": wording.QUOTES_HEADING,
        "downsides_heading": wording.DOWNSIDES_HEADING,
        "no_downsides": wording.NO_DOWNSIDES,
        "breakdown_heading": wording.BREAKDOWN_HEADING,
        "look_for_heading": wording.LOOK_FOR_HEADING,
        "skip_heading": wording.SKIP_HEADING,
        "link_text": wording.LINK_TEXT,
        "price_label": wording.PRICE_LABEL,  # "Price"
        "price_link_text": wording.PRICE_LINK_TEXT,
        "care_heading": wording.CARE_HEADING,  # "How to make it last" (care tips, 9 Oct 2026)
        "brand_model": BRAND_PICK_MODEL,  # "Most named model: {model}" (brand picks, 10 Oct 2026)
        # The breakdown's line about the request's needs (9 Oct 2026), with {recommends} and {warnings} for the page.
        "breakdown_needs": wording.breakdown_needs_line("{recommends}", "{warnings}"),
    }


def example_requests(path: Path = EXAMPLES_FILE) -> list[dict[str, str]]:
    """The blind-test questions, offered as examples: [{"text", "category"}]. None if the file isn't there."""
    if not path.is_file():
        return []
    questions = json.loads(path.read_text(encoding="utf-8"))["questions"]
    return [{"text": q["text"], "category": q["category"]} for q in questions]


def _script_json(data: dict) -> str:
    """JSON that is safe inside a <script> block: "</script>" in a text could otherwise end the block early."""
    text = json.dumps(data, ensure_ascii=False)
    return text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


# --- The server ---

class _Handler(BaseHTTPRequestHandler):
    """Turns each GET request into a call to handle_request, and its result into an HTTP response."""

    server_version = "credible-recs-demo"

    def do_GET(self):
        if self.headers.get("Host", "") in _local_names(self.server.server_address[1]):
            status, content_type, body = handle_request(self.path, self.server.library_dir)
        else:
            status, content_type, body = _error(403, WRONG_HOST)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in HEADERS.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)


def _local_names(port: int) -> tuple[str, ...]:
    """The addresses a request to this server may carry: this computer's, never another website's."""
    return f"{HOST}:{port}", f"localhost:{port}"


def make_server(port: int = WEB_PORT, library_dir: Path = DEFAULT_LIBRARY_DIR) -> ThreadingHTTPServer:
    """A server listening on this computer only (port 0 picks any free port). Start it with serve_forever()."""
    server = ThreadingHTTPServer((HOST, port), _Handler)
    server.library_dir = Path(library_dir)
    return server


def serve(port: int = WEB_PORT, library_dir: Path = DEFAULT_LIBRARY_DIR) -> None:
    """Serves the page until Ctrl+C."""
    server = make_server(port, library_dir)
    print(f"Open http://{HOST}:{server.server_address[1]}/ in your browser (answers from {library_dir}). Ctrl+C stops it.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _options(argv: list[str]) -> tuple[int, Path] | None:
    """--port N and --library DIR, in any order; None if anything else is given."""
    port, library_dir = WEB_PORT, DEFAULT_LIBRARY_DIR
    pairs = list(zip(argv[::2], argv[1::2]))
    if len(argv) % 2 or any(name not in ("--port", "--library") for name, _ in pairs):
        return None
    for name, value in pairs:
        if name == "--port":
            if not value.isdigit():
                return None
            port = int(value)
        else:
            library_dir = Path(value)
    return port, library_dir


def main(argv: list[str]) -> int:
    options = _options(argv)
    if options is None:
        print(__doc__)
        return 2
    port, library_dir = options
    global profiles
    from engine.pipeline import cached_profiles

    profiles = cached_profiles()
    global live
    from engine.pipeline import live_checker

    live = live_checker()
    if not (library_dir / "threads").is_dir():
        print(f"Warning: no library at {library_dir} (no threads/ folder), so every answer will fail. "
              "Pass --library DIR to use another one.")
    serve(port, library_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
