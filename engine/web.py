"""Module 8, the interface: a search page and a small JSON API, served from this machine only, or since 11 Oct 2026 from
Noemi's Hugging Face Space (public mode).

Someone types a need ("electric kettle that lasts 10+ years") into the page; the page asks the API; the API runs
modules 1 to 7 (engine.pipeline) and sends the answer back as JSON; the page draws it as cards. Nothing here
decides anything: every word of an answer comes from engine/answer.py, and every quote has passed its
word-for-word check there. Before an answer leaves the server it is checked once more (unverified_claims): if
any quote fails, the whole answer is refused (HTTP 500) and nothing from it is shown.

Local only (the default): the server listens on 127.0.0.1, so only this computer can reach it, and it answers only
requests addressed to 127.0.0.1 or localhost (a page on another website can't reach it through a trick called DNS
rebinding). It uses Python's standard library only. The final website (Next.js, with a FastAPI service) is a
later decision; the JSON below is the contract it will use.

Public mode (`--public`, for the Hugging Face Space; Noemi's decision of 11 Oct 2026, deploy/huggingface/DEPLOY.md):
- the server listens on every network interface (0.0.0.0), since the Space's proxy reaches it from outside its
  container, and answers only requests addressed to a host named in CREDIBLE_RECS_ALLOWED_HOSTS (comma-separated,
  such as "noemi-credible-recs.hf.space"). Without that list it refuses to start.
- each visitor may ask for RATE_LIMIT_ANSWERS answers and send RATE_LIMIT_FEEDBACK pieces of feedback in any
  RATE_LIMIT_WINDOW_SECONDS (engine/config.py); more gets 429 and a polite "please wait". A visitor is told apart by
  the last public address in X-Forwarded-For, the one the Space's proxy adds (client_address), held in memory only:
  never stored, never logged. It is a courtesy against casual floods, not a wall.
- it keeps no access log (no addresses, no requests), its pages may be shown inside the Space's own page on
  huggingface.co (a frame), and its error messages speak to visitors rather than to whoever runs the server.
Local mode is exactly as before: none of this applies to it.

Visit counts (11 Oct 2026, either mode): when CREDIBLE_RECS_GOATCOUNTER holds Noemi's GoatCounter site code (letters,
digits and hyphens only), both pages load GoatCounter's standard script, which sets no cookies, and the search page
counts a few events by fixed names (listed in the page). Unset, nothing is loaded and nothing is counted.

Routes:
    GET  /                       the search page (engine/templates/search.html)
    GET  /how                    the how-we-score page (engine/how_page.py): how an answer is made and scored, in plain
                                 words, and the latest evaluation results, read from eval/metrics.json each time it is
                                 opened (10 Oct 2026); and what is collected about visitors (11 Oct 2026)
    GET  /api/answer?q=<request> the answer to one request, as JSON
    POST /api/feedback           "Was this useful?" or "First time here?" (engine/feedback.py; 11 Oct 2026)
    anything else                404; a known route asked the wrong way, 405

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
                            "care": [{"tip": "Descale every 6 months.",   "How to take care of it" (9 Oct 2026,
                                      "quote": {same shape}}],            renamed 11 Oct): the pick's own tips, 0 to 2,
                                                               each quote verified
                            "cautions": ["Note: ..."],         product facts that suit the request less well
                                                               (9 Oct 2026); [] when there are none
                            "model": "Victorinox Fibrox...",   a brand pick's most recommended model (10 Oct
                                                               2026); null for other picks
                            "model_price": "£41.50 at ...",    that model's checked price line, or null
                            "downsides_share": "1 of 15 ...",  how many credible voices warned against it (12 Oct
                                                               2026), or null when no downside is shown
                            "summary": {"text": "...",         "In short:" (Noemi's decision 4, 13 Oct 2026): one
                                        "sources": [quotes]}   sentence in our words, never a quote, shown only when
                                                               every check passes (engine/summaries.py); "sources"
                                                               are the verified quotes of the comments it sums up
                                                               (not shown; checked word for word and live like every
                                                               quote); null when the pick has none
                            "voices": {"recommend": n,         the credible voices behind it, as numbers for the page's
                                       "high": n, "medium": n, credibility meter (13 Oct 2026): its credible
                                       "warn": n,              recommendations, of them the high and medium voices, the
                                       "threads": n}           writers who warned (as the share line counts them) and
                                                               the threads with a credible recommendation
                           }],
                 "look_for": [{"kind", "advice", "quote": {same shape}}],
                 "skip": [{"product_key", "name", "reason", "quotes": [...]}],
                 "care_note": [{"tip", "quote"}],   care tips about the kind of product, shown once at the end
                                                    (Noemi, 11 Oct 2026); [] when there are none
                 "worth_a_look": [{"product_key", "name", "reason", "quotes", "downsides", "downsides_share",
                                   "disagreement", "score", "breakdown", "price", "availability", "cautions",
                                   "summary", "voices"}],
                                  "Also worth a look" (Noemi's decision 2, 13 Oct 2026): up to 3 products with 2
                                  credible recommendations across at least 2 threads, best first, shown apart after the
                                  picks and never among them; the same shapes as a pick's fields, with 1 or 2 quotes,
                                  and downsides only when credible voices warn against it; [] when there are none
                 "worth_note": "2 credible voices each: ...",   the words under its heading, or null without items
                 "message": the honest "not enough evidence" message, or null when there are 3 picks,
                 "needs_more_threads", "quotes_dropped"},
      "threads_used": ["thread id", ...],          most relevant first
      "left_out": {"other_type": n,                products of another type, left out,
                   "other_type_names": [...],      and up to LEFT_OUT_NAMES_SHOWN of their names (12 Oct 2026);
                   "loose": n,                     brand or line names that fit several products, left out (a name of
                                                   filler words only, such as "the one", names nothing: since 12 Oct
                                                   2026 it isn't counted),
                   "loose_names": [...],           and up to LEFT_OUT_NAMES_SHOWN of them, most mentioned first;
                   "ranked_as_lines": n,           the brand or line names ranked as the brand's whole line instead
                                                   ("Lodge cast iron skillet line"; 12 Oct 2026). Every count here is
                                                   of names (products), never of mentions or threads,
                   "over_budget": n,               products whose known price is over the request's budget
                   "unavailable": n,               products the price list says are no longer sold (9 Oct 2026),
                   "not_suited": n},               and products whose checked facts clash with the request (9 Oct 2026)
      "timing": {"total_s": s, "reddit_s": s,      diagnostic, never shown (13 Oct 2026): how long the answer took to
                 "checks": n,                      work out, how long it waited on live checks, how many it made,
                 "put_off": n},                    and the comments put off rather than wait (what they back is left out)
      "reading": {"threads": n,                    how much the answer read (Noemi, 12 Oct 2026): the threads used
                                                   (the most relevant to the request),
                  "threads_saved": n,              the extracted threads saved about the product,
                  "comments": n,                   the comments the AI read in the threads used,
                  "read_more": bool}               and whether the first threads gave too few picks, so more were read
                                                   (13 Oct 2026, for the page's reading strip)
    }

POST /api/feedback takes one JSON object (Content-Type: application/json, at most FEEDBACK_MAX_BODY_BYTES) in one of
the two shapes engine/feedback.py describes, and answers {"saved": true}. It is taken only from this site's own page:
the Origin header the browser adds (or, when it sends none, its Referer) must name this server's host.

An error is {"error": "<plain words>", "code": "<one word for programs>"}:
    400 empty_request, request_too_long (over WEB_MAX_REQUEST_CHARS characters); bad_length, bad_json, bad_feedback
    403 wrong_host        a request not addressed to this server
        cross_site        feedback not sent from this site's own page
    404 not_found
    405 method_not_allowed (with an Allow header)
    411 length_required, 413 too_large, 415 not_json   (feedback)
    429 too_many_requests (public mode only, with a Retry-After header in seconds)
    500 quote_not_verified (the answer is refused), engine_failed (details in the server's window, never sent)
    503 feedback_unavailable (the feedback couldn't be kept just now)
The words are for whoever calls the API; the page picks its own words by code (PROPOSED, at the top of the page).

Answers take about 2 seconds, so each one is remembered for as long as the server runs: asking again is instant.
A library refresh needs a restart to show.

Getting ready (latency, 12 Oct 2026): as it starts, the server reads the library, the price and facts lists, loads
the open model, and works out (and throws away) one answer per product type without live checks, so what answers keep
between requests is ready (warm_up). All in the background: the page is there at once, and the first visitor doesn't
wait for any of it. On the live site (CREDIBLE_RECS_LIVE_CACHE_BUCKET set) it first reads the daily pre-check's checks
from the bucket's one bundle into its folder, and again at most once an hour, only when the bundle has changed, when
Cloud Scheduler's keep-warm ping asks /ready (reload_checks_if_due; 13 Oct 2026: Cloud Run gives a server its
processor only while it answers a request). It never writes to the bucket: its own checks stay in its folder.

Command line:
    python -m engine.web [--port N] [--library DIR]    serves the page at http://127.0.0.1:8765/ (Ctrl+C stops it)
    python -m engine.web --public --port 7860           the public site (deploy/huggingface/start.sh runs it)
Feedback goes to data/feedback/feedback.jsonl, or to Noemi's private dataset when CREDIBLE_RECS_FEEDBACK_REPO and
HF_TOKEN are set (engine/feedback.py).
"""

import gzip
import html
import ipaddress
import json
import math
import os
import re
import signal
import sys
import threading
import time
import traceback
from collections import OrderedDict, deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from engine import answer as wording
from engine import feedback, how_page
from engine.answer import answer_to_dict, unverified_claims
from engine.config import (BRAND_PICK_MODEL, FEEDBACK_MAX_BODY_BYTES, FEEDBACK_MAX_COMMENT_CHARS, LEFT_OUT_NAMES_SHOWN,
                           PICKS_SHOWN, RATE_LIMIT_ANSWERS, RATE_LIMIT_FEEDBACK, RATE_LIMIT_WINDOW_SECONDS, WEB_MAX_REQUEST_CHARS,
                           WEB_PORT)
from engine.library import DEFAULT_LIBRARY_DIR
from engine.live_check import BUNDLE_RELOAD_SECONDS
from engine.metrics import METRICS_FILE
from engine.parse_reddit import REPO_ROOT
from engine.pipeline import PipelineResult, answer_request
from engine.query import PRODUCT_TYPES

HOST = "127.0.0.1"  # this computer only. Never "0.0.0.0", which would open the server to the whole network.
PUBLIC_HOST = "0.0.0.0"  # public mode only: every network interface, so the Space's proxy can reach the server
PAGE_TEMPLATE = Path(__file__).resolve().parent / "templates" / "search.html"
EXAMPLES_FILE = REPO_ROOT / "eval" / "blind_test" / "questions.json"  # the 10 approved blind-test questions
ALLOWED_HOSTS_VAR = "CREDIBLE_RECS_ALLOWED_HOSTS"  # public mode: the host names the site answers for
GOATCOUNTER_VAR = "CREDIBLE_RECS_GOATCOUNTER"  # Noemi's GoatCounter site code; unset, visits aren't counted
GOATCOUNTER_SCRIPT = "https://gc.zgo.at"  # where GoatCounter's script comes from
HUGGING_FACE = "https://huggingface.co"  # the Space's page there shows the public site in a frame
MAX_TRACKED_CLIENTS = 10_000  # the rate limit remembers at most this many visitors (the least recent are forgotten)
MAX_HOSTS_NAMED = 20  # public mode names at most this many refused hosts in its window, so scanners can't flood it

HTML = "text/html; charset=utf-8"
JSON = "application/json; charset=utf-8"
# Pages and answers are sent gzipped to browsers that say they take it (13 Oct 2026, with the redesigned page: 93 KB
# becomes 27 KB on the way); smaller bodies, such as errors, as they are.
GZIP_MIN_BYTES = 1024

# Sent with every response. The page may load and call nothing but this server: no outside scripts, styles, fonts
# or images, and no requests elsewhere. Its links still open, in a new tab: to Reddit, and to a shop's own page for a
# price or for where a product is sold (https only, from data/prices.json; decision 11 and availability, 9 Oct 2026).
# Exactly what local mode sends; security_headers adds GoatCounter when visits are counted, and the Space's page.
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
# Added 11 Oct 2026 (going live).
WRONG_HOST_PUBLIC = ("wrong_host", "This server only answers requests addressed to its own website.")
WRONG_METHOD = ("method_not_allowed", "This address takes {allowed} requests only.")
CROSS_SITE = ("cross_site", "Feedback is taken only from this website's own page.")
NOT_JSON = ("not_json", "Send the feedback as JSON, with the header Content-Type: application/json.")
NO_LENGTH = ("length_required", "Say how long the feedback is, with a Content-Length header.")
BAD_LENGTH = ("bad_length", "The Content-Length header isn't a plain number.")
TOO_LARGE = ("too_large", "Feedback is limited to {limit} bytes.")
BAD_JSON = ("bad_json", "The feedback isn't one valid JSON value (or a name in it appears twice).")
BAD_FEEDBACK = ("bad_feedback", "{reason}")
FEEDBACK_UNAVAILABLE = ("feedback_unavailable", "Feedback can't be kept just now. Please try again later.")
TOO_MANY = ("too_many_requests", "Too many requests in a short time. Please try again in {seconds} seconds.")

FEEDBACK_PATH = "/api/feedback"
READY_PATH = "/ready"  # whether the server has got ready (warm_up): Cloud Run's startup probe asks it
METHODS = {"/": "GET", "/how": "GET", "/api/answer": "GET", READY_PATH: "GET",
           FEEDBACK_PATH: "POST"}  # each route and how it is asked


@dataclass(frozen=True)
class Site:
    """How the server runs. Local (the default): this computer only, as before. Public (the Hugging Face Space): every
    network interface, requests for `hosts` only, rate limits, no access log. `goatcounter`: Noemi's GoatCounter site
    code when visits are counted, else None (either mode)."""

    public: bool = False
    hosts: tuple[str, ...] = ()
    goatcounter: str | None = None


LOCAL = Site()


# Answers already worked out, by (request, library folder), kept until the server stops.
_answers: dict[tuple[str, str], tuple[float, tuple[int, str, bytes]]] = {}  # key -> (when worked out, the answer)
# How long a remembered answer is kept before it is worked out again, its quotes checked live once more (12 Oct 2026):
# well within the 48 hours Reddit content may be kept, and short enough that a comment deleted today leaves the
# answers by tomorrow. Chosen by Claude, reported to Noemi.
ANSWER_KEEP_HOURS = 24
_clock = time.monotonic
# Where writers' standing comes from (engine.pipeline's `profiles`): the command line sets the Arctic Shift cache
# (engine.profiles.CachedOnly, never a call); None, as in the tests, leaves writers known by name only.
profiles = None
# The live check of every shown quote (engine.live_check): set by the command line; None in the tests.
live = None
# Where feedback goes (engine.feedback, 11 Oct 2026): set by the command line; None in the tests, which give their own.
store = None
_answers_lock = threading.Lock()
# Set once the server has got ready (warm_up). Until then /ready says 503, and Cloud Run sends visitors to the server
# only when it says 200 (13 Oct 2026, the live site's latency): a new server getting ready took turns with its first
# visitors' answers and held them up to 30 s, with the processor Cloud Run gives a server only while it answers
# someone. While it starts, Cloud Run gives it the processor in full, and keeps visitors on the server before it.
ready = threading.Event()
# When the pre-check's bundle was last read (warm_up, then reload_checks_if_due), by _clock; None: not yet.
_checks_read_at: float | None = None
_checks_lock = threading.Lock()


# --- Routing: one GET request in, one response out ---

def handle_request(path_and_query: str, library_dir: Path = DEFAULT_LIBRARY_DIR,
                   site: Site = LOCAL) -> tuple[int, str, bytes]:
    """What the server sends back for one GET request: (status code, content type, body).

    A plain function, with no network in it, so the tests can call it directly.
    """
    parts = urlsplit(path_and_query)
    if parts.path == "/":
        return 200, HTML, search_page(site)
    if parts.path == "/how":  # read now: a new evaluation run shows at once
        page = how_page.page(METRICS_FILE, counter=counter_script(site.goatcounter), public=site.public)
        return 200, HTML, page.encode("utf-8")
    if parts.path == "/api/answer":
        request = parse_qs(parts.query).get("q", [""])[0]
        return answer_response(request, Path(library_dir), quiet=site.public)
    if parts.path == READY_PATH:
        if ready.is_set():
            reload_checks_if_due()
        return (200 if ready.is_set() else 503), JSON, json.dumps({"ready": ready.is_set()}).encode("utf-8")
    if parts.path in METHODS:  # a route that takes another method: feedback is sent, never fetched
        return _error(405, WRONG_METHOD, allowed=METHODS[parts.path])
    return _error(404, NOT_FOUND)


def answer_response(request: str, library_dir: Path, quiet: bool = False) -> tuple[int, str, bytes]:
    """The answer to one request as JSON, remembered for next time; or an error. `quiet` (the public site): nothing
    about the request goes to the server's window, not even in a report of a failure."""
    request = request.strip()
    if not request:
        return _error(400, EMPTY_REQUEST)
    if len(request) > WEB_MAX_REQUEST_CHARS:
        return _error(400, TOO_LONG, n=len(request), limit=WEB_MAX_REQUEST_CHARS)
    key = (request, str(library_dir))
    remembered = _answers.get(key)  # read without waiting (11 Oct 2026): a slow new answer never holds up a known one
    if remembered is not None and _clock() - remembered[0] < ANSWER_KEEP_HOURS * 3600:
        return remembered[1]
    with _answers_lock:  # one answer is worked out at a time, so the same request is never worked out twice
        remembered = _answers.get(key)
        if remembered is None or _clock() - remembered[0] >= ANSWER_KEEP_HOURS * 3600:
            try:
                response, whole = _fresh_answer(request, library_dir, quiet)
            except Exception:  # a broken library file, say: reported in the server's window, never sent
                _report_failure(quiet)
                return _error(500, ENGINE_FAILED)  # not remembered: fixing the file and asking again works
            if not whole:  # something was left out for Reddit's allowance (13 Oct 2026): worked out again next time
                _answers.pop(key, None)
                return response
            _answers[key] = (_clock(), response)
        return _answers[key][1]


class _TimedChecker:
    """The live checker, timed for one answer (13 Oct 2026, hill-climbing the live site's latency): how many checks it
    made and how long the answer waited on them, overlapping checks counted once."""

    def __init__(self, checker):
        self._checker = checker
        self._spans: list[tuple[float, float]] = []
        self._lock = threading.Lock()

    def check(self, *args, **kwargs):
        started = time.perf_counter()
        try:
            return self._checker.check(*args, **kwargs)
        finally:
            with self._lock:
                self._spans.append((started, time.perf_counter()))

    def __getattr__(self, name):  # anything else the pipeline asks the checker goes to the real one
        return getattr(self._checker, name)

    @property
    def checks(self) -> int:
        return len(self._spans)

    def waited(self) -> float:
        """Seconds during which at least one check was running."""
        total, end = 0.0, None
        for start, stop in sorted(self._spans):
            if end is None or start > end:
                total += stop - start
                end = stop
            elif stop > end:
                total += stop - end
                end = stop
        return total


def _fresh_answer(request: str, library_dir: Path, quiet: bool = False) -> tuple[tuple[int, str, bytes], bool]:
    """Runs the pipeline, then checks every quote once more; one that fails refuses the whole answer. Also whether the
    answer is whole: nothing in it was left out because its live check would have waited (13 Oct 2026)."""
    with_profiles = {} if profiles is None else {"profiles": profiles}
    timed = _TimedChecker(live) if live is not None else None
    if timed is not None:
        with_profiles["live_checker"] = timed
    started = time.perf_counter()
    result = answer_request(request, library_dir, **with_profiles)
    timing = {"total_s": round(time.perf_counter() - started, 2), "reddit_s": round(timed.waited(), 2) if timed else 0.0,
              "checks": timed.checks if timed else 0, "put_off": result.live_put_off}
    if result.skipped_files:  # a broken library file was left out of the answer (11 Oct 2026): say so where it runs
        print(f"Library files left out ({len(result.skipped_files)} problem(s)); first: {result.skipped_files[0]}",
              file=sys.stderr)
    if result.answer is not None:
        problems = unverified_claims(result.answer, result.bodies)
        if problems:  # the problems name comments, never the failed quote's words
            asked = "a request" if quiet else repr(request)
            print(f"Refused the answer to {asked}:", *problems, sep="\n  - ", file=sys.stderr)
            return _error(500, REFUSED), True
    return (200, JSON, _json_bytes(answer_json(result) | {"timing": timing})), result.live_put_off == 0


def _report_failure(quiet: bool) -> None:
    """An engine failure, in the server's window: the whole traceback locally; on the public site only where it happened
    and what kind of error it was, since an error's own message can quote the request."""
    if not quiet:
        traceback.print_exc()
        return
    kind, _, trace = sys.exc_info()
    frames = traceback.extract_tb(trace) if trace else []
    where = f" at {Path(frames[-1].filename).name}:{frames[-1].lineno}" if frames else ""
    print(f"The engine failed on a request ({kind.__name__ if kind else 'unknown error'}{where}).", file=sys.stderr)


def answer_json(result: PipelineResult) -> dict:
    """The pipeline's result in the shape the page (and the later website) reads: see the top of this file."""
    query = result.query
    brand_names = result.brand_or_line_names_left_out
    return {
        "query": {"status": query.status, "category": query.category, "product_type": query.product_type,
                  "question": query.question, "message": query.message},
        "answer": answer_to_dict(result.answer) if result.answer is not None else None,
        "threads_used": list(result.threads_used),
        # Names, a few of them for the page's footnote to give as examples (Noemi asked what its numbers count, 12 Oct
        # 2026): products of another type, brand or line names left out, and brand or line names ranked as lines.
        "left_out": {"other_type": len(result.left_out_as_other_type),
                     "other_type_names": result.left_out_as_other_type[:LEFT_OUT_NAMES_SHOWN],
                     "loose": len(brand_names), "loose_names": brand_names[:LEFT_OUT_NAMES_SHOWN],
                     "ranked_as_lines": len(result.ranked_as_lines),
                     "over_budget": len(result.left_out_over_budget),
                     "unavailable": len(result.left_out_unavailable),
                     "not_suited": len(result.left_out_not_suited)},
        # How much the answer read (Noemi, 12 Oct 2026): the threads used, the extracted threads saved about the product,
        # and the comments the AI read in the threads used; and since 13 Oct 2026 (Noemi's testing: the page's line
        # about it confused her) whether the first threads gave too few picks, so more were read.
        "reading": {"threads": len(result.threads_used), "threads_saved": result.threads_available,
                    "comments": result.comments_read, "read_more": result.read_more},
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


# --- Feedback: one POST request in, one response out (11 Oct 2026) ---

def handle_feedback(content_type: str | None, content_length: str | None, read) -> tuple[int, str, bytes]:
    """POST /api/feedback, once the request is known to come from this site's own page: the record, checked
    (engine.feedback.parse_record) and kept in `store`; or an error. `read(n)` reads the body, and is called only once
    the body is known to be JSON of a sensible size, so an oversized one is never read.

    Only JSON is taken: a form on another website can send nothing else without the browser first asking this server
    for leave, which it never gives.
    """
    if (content_type or "").split(";")[0].strip().lower() != "application/json":
        return _error(415, NOT_JSON)
    if content_length is None:
        return _error(411, NO_LENGTH)
    if not re.fullmatch(r"[0-9]{1,9}", content_length.strip()):
        return _error(400, BAD_LENGTH)
    size = int(content_length)
    if size > FEEDBACK_MAX_BODY_BYTES:
        return _error(413, TOO_LARGE, limit=FEEDBACK_MAX_BODY_BYTES)
    try:
        data = json.loads(read(size).decode("utf-8"), object_pairs_hook=_no_repeated_names)
    except (ValueError, RecursionError):  # not UTF-8, not JSON, a name given twice, or nested too deep to read
        return _error(400, BAD_JSON)
    try:
        record = feedback.parse_record(data)
    except feedback.FeedbackError as error:
        return _error(400, BAD_FEEDBACK, reason=str(error))
    if store is None:
        return _error(503, FEEDBACK_UNAVAILABLE)
    try:
        store.add(record)
    except Exception as error:  # too much waiting to be uploaded, or a full disk: the record's words are never logged
        print(f"Feedback not kept ({type(error).__name__}).", file=sys.stderr)
        return _error(503, FEEDBACK_UNAVAILABLE)
    return 200, JSON, _json_bytes({"saved": True})


def _no_repeated_names(pairs: list[tuple[str, object]]) -> dict:
    """A JSON object as a dict, refusing one that gives the same name twice (which of the two would count?)."""
    names = [name for name, _ in pairs]
    if len(set(names)) != len(names):
        raise ValueError("a name appears twice")
    return dict(pairs)


def from_this_site(origin: str | None, referer: str | None, accepts) -> bool:
    """Whether a POST comes from this site's own page: the Origin header the browser adds (or, when it sends none, the
    Referer) names a host this server takes requests for (`accepts(host)`, the same test as for the Host header). A page
    on another website can't make a browser send ours; a request that names no page at all is refused too."""
    source = origin if origin is not None else referer
    if not source or source == "null":
        return False
    return accepts(urlsplit(source).netloc)


# --- Public mode: hosts, visitors and rate limits (11 Oct 2026) ---

_HOST_NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*")


def host_name(value: str) -> str:
    """The host name in a Host header or in an address: lowercased, without its port or a final dot."""
    value = value.strip().lower()
    if value.startswith("["):  # an IPv6 address, "[::1]:7860"
        return value.split("]")[0] + "]"
    if value.count(":") == 1:
        value = value.split(":")[0]
    return value.rstrip(".")


def allowed_hosts(value: str) -> tuple[str, ...]:
    """The host names in CREDIBLE_RECS_ALLOWED_HOSTS, read kindly: lowercased, without a port, and taken from a whole
    address if one is pasted in ("https://noemi-credible-recs.hf.space/"). Raises ValueError for an entry that names no
    host, such as "*" or "*.hf.space": every host must be named."""
    hosts = []
    for entry in value.split(","):
        entry = entry.strip()
        if not entry:
            continue
        name = host_name(urlsplit(entry).netloc if "//" in entry else entry)
        if not _HOST_NAME.fullmatch(name):
            raise ValueError(f"{entry!r} isn't a host name (such as noemi-credible-recs.hf.space).")
        hosts.append(name)
    return tuple(dict.fromkeys(hosts))


def client_address(forwarded_for: str | None, socket_address: str) -> str:
    """Who a request comes from, for the rate limit only (public mode): the last public address in X-Forwarded-For,
    the one the Space's proxy adds (a visitor can write made-up addresses into the header, but only in front of it, so
    the first one could change on every request and get round the limit); proxies' own private addresses are skipped.
    With no public address, the first entry, else the connection's own address. Cut to 100 characters, so a made-up
    header can't fill memory. Held in memory only: never stored, never logged."""
    entries = [entry.strip()[:100] for entry in (forwarded_for or "")[:2000].split(",")]
    for entry in reversed(entries):
        try:
            if ipaddress.ip_address(entry).is_global:
                return entry
        except ValueError:
            continue
    return next((entry for entry in entries if entry), "") or socket_address


class RateLimiter:
    """At most `limit` requests from each visitor in any `window` seconds (a sliding window). Kept in memory only, and
    only for the `max_clients` visitors seen most recently, so a flood of made-up addresses can't fill memory."""

    def __init__(self, limit: int, window: float, clock=time.monotonic, max_clients: int = MAX_TRACKED_CLIENTS):
        self.limit = limit
        self.window = window
        self._clock = clock
        self._max_clients = max_clients
        self._seen: OrderedDict[str, deque[float]] = OrderedDict()  # visitor: their requests' times, least recent first
        self._lock = threading.Lock()

    def wait(self, client: str) -> int:
        """0 when this request may go ahead (it is counted); otherwise the whole seconds until it may (it isn't)."""
        now = self._clock()
        with self._lock:
            times = self._seen.get(client)
            if times is None:
                times = self._seen[client] = deque()
                if len(self._seen) > self._max_clients:
                    self._seen.popitem(last=False)  # forget the visitor seen least recently
            else:
                self._seen.move_to_end(client)
            while times and now - times[0] >= self.window:
                times.popleft()
            if len(times) >= self.limit:
                return max(1, math.ceil(self.window - (now - times[0])))
            times.append(now)
            return 0

    def __len__(self) -> int:
        return len(self._seen)


def site_from_env(environ, public: bool) -> tuple[Site | None, list[str]]:
    """The site the command line asks for, from the environment, and any problems in plain words. A public site with no
    usable CREDIBLE_RECS_ALLOWED_HOSTS is None: it must not start. A CREDIBLE_RECS_GOATCOUNTER that isn't a code leaves
    visit counting off, with a warning (the site is more use running than not)."""
    problems = []
    hosts: tuple[str, ...] = ()
    if public:
        try:
            hosts = allowed_hosts(environ.get(ALLOWED_HOSTS_VAR, ""))
        except ValueError as error:
            problems.append(f"Not starting: {ALLOWED_HOSTS_VAR} has {error}")
        if not hosts and not problems:
            problems.append(f"Not starting: the public site needs {ALLOWED_HOSTS_VAR}, the host names it answers for, "
                            "comma-separated (such as noemi-credible-recs.hf.space).")
    setting = environ.get(GOATCOUNTER_VAR, "")
    code = goatcounter_code(setting)
    if setting.strip() and code is None:
        problems.append(f"{GOATCOUNTER_VAR} isn't a GoatCounter code (letters, digits and hyphens only, such as "
                        "credible-recs), so visits aren't counted.")
    if public and not hosts:
        return None, problems
    return Site(public=public, hosts=hosts, goatcounter=code), problems


# --- Visit counts: GoatCounter (11 Oct 2026) ---

_GOATCOUNTER_CODE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


def goatcounter_code(value: str | None) -> str | None:
    """Noemi's GoatCounter site code ("credible-recs" counts at credible-recs.goatcounter.com), if `value` is one:
    letters, digits and hyphens only. It goes into the page's script address, so nothing else may get in. None when
    unset or not a code."""
    code = (value or "").strip().lower()
    return code if _GOATCOUNTER_CODE.fullmatch(code) else None


def counter_script(code: str | None) -> str:
    """GoatCounter's standard script for the site `code`, or "" when visits aren't counted. Two small changes to the
    snippet GoatCounter suggests: the script's address says https (GoatCounter's own "//gc.zgo.at/count.js" would be
    fetched over plain http on an http page, which the security policy refuses), and its one setting, allow_frame, lets
    it count visits made through the Space's page on huggingface.co, which shows the site in a frame (GoatCounter skips
    framed pages otherwise)."""
    code = goatcounter_code(code)
    if code is None:
        return ""
    return (f'<script data-goatcounter="https://{html.escape(code)}.goatcounter.com/count" '
            f"""data-goatcounter-settings='{{"allow_frame": true}}' async src="{GOATCOUNTER_SCRIPT}/count.js"></script>""")


def security_headers(site: Site = LOCAL) -> dict[str, str]:
    """The headers sent with every response: exactly HEADERS in local mode without visit counts. Counting lets in
    GoatCounter's script and its counting address, and nothing else; the public site may also be shown inside the
    Space's page on huggingface.co."""
    if not site.public and site.goatcounter is None:
        return dict(HEADERS)
    scripts, connections, images = "'unsafe-inline'", "'self'", ""
    if site.goatcounter is not None:
        counter = f"https://{site.goatcounter}.goatcounter.com"
        scripts += f" {GOATCOUNTER_SCRIPT}"
        connections += f" {counter}"
        images = f"img-src {counter}; "  # GoatCounter's fallback when a browser won't send its count another way
    frames = HUGGING_FACE if site.public else "'none'"
    policy = (f"default-src 'none'; script-src {scripts}; style-src 'unsafe-inline'; {images}connect-src {connections}; "
              f"form-action 'self'; base-uri 'none'; frame-ancestors {frames}")
    return {**HEADERS, "Content-Security-Policy": policy}


# --- The page ---

def search_page(site: Site = LOCAL) -> bytes:
    """The search page: the template, with the answer's own headings, the example requests, the length limits and the
    site's settings filled in, and GoatCounter's script when visits are counted."""
    settings = {"wording": answer_wording(), "examples": example_requests(), "maxChars": WEB_MAX_REQUEST_CHARS,
                "maxCommentChars": FEEDBACK_MAX_COMMENT_CHARS, "counting": site.goatcounter is not None,
                "public": site.public,
                "picksShown": PICKS_SHOWN}  # the reading strip's "why not all?" (13 Oct 2026)
    template = PAGE_TEMPLATE.read_text(encoding="utf-8")
    page = template.replace("{{COUNTER}}", counter_script(site.goatcounter))  # first: the settings could hold any text
    return page.replace("{{SETTINGS}}", _script_json(settings)).encode("utf-8")


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
        # The two kinds of advice under it (13 Oct 2026, the redesign marks each with its own sign): "Look for", "Avoid".
        "look_for_advice": wording.LOOK_FOR,
        "avoid_advice": wording.AVOID,
        "skip_heading": wording.SKIP_HEADING,
        "link_text": wording.LINK_TEXT,
        "price_label": wording.PRICE_LABEL,  # "Price"
        "price_link_text": wording.PRICE_LINK_TEXT,
        "care_heading": wording.CARE_HEADING,  # "How to take care of it" (care tips; renamed by Noemi on 11 Oct 2026)
        # The note at the end with the tips about the kind of product (Noemi, 11 Oct 2026), and its wording without one.
        "care_note_heading": wording.CARE_NOTE_HEADING,
        "care_note_heading_any": wording.CARE_NOTE_HEADING_ANY,
        "brand_model": BRAND_PICK_MODEL,  # "Most named model: {model}" (brand picks, 10 Oct 2026)
        # The breakdown's line about the request's needs (9 Oct 2026), with {recommends} and {warnings} for the page.
        "breakdown_needs": wording.breakdown_needs_line("{recommends}", "{warnings}"),
        # Swear words the page masks on display (Noemi, 12 Oct 2026): the same list as the text answer's.
        "masked_words": list(wording.MASKED_WORDS),
        # "Also worth a look" (Noemi, 13 Oct 2026); the note under it comes with each answer ("worth_note").
        "worth_heading": wording.WORTH_HEADING,
        # One-line summaries (Noemi, 13 Oct 2026): "In short:" and the note saying it is ours, not a quote.
        "summary_label": wording.SUMMARY_LABEL,
        "summary_note": wording.SUMMARY_NOTE,
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
    """Turns each request into a call to handle_request (GET) or handle_feedback (POST), and its result into an HTTP
    response. This is local mode; _PublicHandler changes what the public site needs."""

    server_version = "credible-recs-demo"
    _wrong_host = WRONG_HOST

    def do_GET(self):
        path = urlsplit(self.path).path
        if path != READY_PATH and not self._addressed_here():  # Cloud Run's probe names no site: it learns only this
            return self._send(*_error(403, self._wrong_host))
        if path == "/api/answer" and self._held_back("answers"):
            return
        self._send(*handle_request(self.path, self.server.library_dir, self.server.site), path=path)

    def do_POST(self):
        path = urlsplit(self.path).path
        if not self._addressed_here():
            return self._send(*_error(403, self._wrong_host))
        if path != FEEDBACK_PATH:
            refused = _error(405, WRONG_METHOD, allowed=METHODS[path]) if path in METHODS else _error(404, NOT_FOUND)
            return self._send(*refused, path=path)
        if not from_this_site(self.headers.get("Origin"), self.headers.get("Referer"), self._accepts):
            return self._send(*_error(403, CROSS_SITE))
        if self._held_back("feedback"):
            return
        self._send(*handle_feedback(self.headers.get("Content-Type"), self.headers.get("Content-Length"),
                                    self.rfile.read))

    def _addressed_here(self) -> bool:
        return self._accepts(self.headers.get("Host", ""))

    def _accepts(self, host: str) -> bool:
        """Whether a request for `host` is for this server: here, this computer's own addresses, exactly as written."""
        return host in _local_names(self.server.server_address[1])

    def _held_back(self, limit: str) -> bool:
        """Whether a rate limit stops this request, which has then been answered (429). Never in local mode."""
        return False

    def _send(self, status: int, content_type: str, body: bytes, path: str | None = None,
              extra: dict[str, str] | None = None) -> None:
        if len(body) >= GZIP_MIN_BYTES and takes_gzip(self.headers.get("Accept-Encoding")):
            body = gzip.compress(body, compresslevel=6)
            extra = {**(extra or {}), "Content-Encoding": "gzip", "Vary": "Accept-Encoding"}
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in security_headers(self.server.site).items():
            self.send_header(name, value)
        if status == 405 and path in METHODS:
            self.send_header("Allow", METHODS[path])
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)


class _PublicHandler(_Handler):
    """The public site's differences: its own host names, rate limits, no access log, and no waiting forever on a
    visitor's connection that has gone quiet."""

    timeout = 30  # seconds a connection may stay silent in the middle of a request before it is closed
    _wrong_host = WRONG_HOST_PUBLIC

    def _addressed_here(self) -> bool:
        host = self.headers.get("Host", "")
        if self._accepts(host):
            return True
        self._name_refused_host(host[:100])
        return False

    def _accepts(self, host: str) -> bool:
        return host_name(host) in self.server.site.hosts

    def _name_refused_host(self, host: str) -> None:
        """Names a refused host once in the server's window (never who sent the request): if Hugging Face's proxy
        addresses the site in a way nobody expected, the Space's logs say what to add to the list."""
        named = self.server.refused_hosts
        with self.server.refused_lock:
            if host in named or len(named) >= MAX_HOSTS_NAMED:
                return
            named.add(host)
        print(f"Refused a request addressed to {host!r}. If that is this site's own address, add it to "
              f"{ALLOWED_HOSTS_VAR}.", file=sys.stderr, flush=True)

    def _held_back(self, limit: str) -> bool:
        visitor = client_address(self.headers.get("X-Forwarded-For"), self.client_address[0])
        seconds = self.server.limits[limit].wait(visitor)
        if seconds:
            self._send(*_error(429, TOO_MANY, seconds=seconds), extra={"Retry-After": str(seconds)})
        return bool(seconds)

    def log_message(self, format, *args):
        """No access log on the public site: no visitors' addresses, no requests (Noemi, 11 Oct 2026)."""


def takes_gzip(accept_encoding: str | None) -> bool:
    """Whether a browser's Accept-Encoding header takes gzip ("gzip", "*", "gzip;q=0.8"), and not with q=0."""
    for entry in (accept_encoding or "").lower().split(","):
        name, _, params = entry.strip().partition(";")
        if name.strip() not in ("gzip", "*"):
            continue
        quality = params.strip().removeprefix("q=").strip() if params.strip().startswith("q=") else "1"
        try:
            return float(quality) > 0
        except ValueError:
            return False
    return False


def _local_names(port: int) -> tuple[str, ...]:
    """The addresses a request to this server may carry: this computer's, never another website's."""
    return f"{HOST}:{port}", f"localhost:{port}"


def listen_address(site: Site) -> str:
    """Where the server listens: this computer only, or every network interface for the public site."""
    return PUBLIC_HOST if site.public else HOST


def make_server(port: int = WEB_PORT, library_dir: Path = DEFAULT_LIBRARY_DIR, site: Site = LOCAL) -> ThreadingHTTPServer:
    """A server for `site` (port 0 picks any free port): on this computer only, unless the site is public. Start it with
    serve_forever()."""
    if site.public and not site.hosts:
        raise ValueError(f"a public site needs the host names it answers for ({ALLOWED_HOSTS_VAR})")
    server = ThreadingHTTPServer((listen_address(site), port), _PublicHandler if site.public else _Handler)
    server.library_dir = Path(library_dir)
    server.site = site
    server.limits = {"answers": RateLimiter(RATE_LIMIT_ANSWERS, RATE_LIMIT_WINDOW_SECONDS),
                     "feedback": RateLimiter(RATE_LIMIT_FEEDBACK, RATE_LIMIT_WINDOW_SECONDS)}
    server.refused_hosts, server.refused_lock = set(), threading.Lock()  # public mode: refused hosts already named
    return server


PRIMING_REQUEST = "best toaster for a small kitchen"  # one of the open model's own examples (engine.query_model)


def warm_up(library_dir: Path = DEFAULT_LIBRARY_DIR) -> None:
    """Everything answers keep in memory, made ready before the first request needs it (latency, 12 Oct 2026): the
    library read and checked (engine.library_cache), the price and facts lists, and the open model loaded (a few
    seconds each). A problem is reported in the server's window and never stops it: the answer that needs the missing
    piece reports it as before. On the live site, first of all, the daily pre-check's checks (engine/precheck.py), read
    from the bucket's bundle into this server's folder (engine.live_check.LiveChecker.load_bundle; 13 Oct 2026)."""
    from engine.library_cache import loaded
    from engine.prices import load_prices
    from engine.product_facts import load_product_facts
    from engine.query_model import default_query_model

    def load_model():
        model = default_query_model()
        if model is not None and hasattr(model, "load"):
            model.load()
            # One reading of an example request, so the model has read its instructions (which every request repeats)
            # and the first visitor's request reads only its own words: seconds the first time, then a second or two.
            model.read(PRIMING_REQUEST)

    started = time.perf_counter()
    threads = Path(library_dir) / "threads"
    steps = [("the open model", load_model), ("the price list", load_prices), ("the facts list", load_product_facts)]
    if live is not None and getattr(live, "bucket", None) is not None:  # first, and quick: the first answers find them
        steps.insert(0, ("the pre-check's checks", _read_checks))
    if threads.is_dir():
        steps.insert(0, ("the library", lambda: loaded(threads)))
        steps += [(f"the answers' memory for {name}", lambda name=name: warm_answer(name, library_dir))
                  for name in WARM_PRODUCT_TYPES]
    for name, step in steps:
        try:
            step()
        except Exception as error:  # reported where the server runs; answers report it again when they need it
            print(f"Getting ready: {name} couldn't be loaded ({type(error).__name__}: {error}).", file=sys.stderr,
                  flush=True)
    ready.set()
    print(f"Ready for visitors: got ready in {time.perf_counter() - started:.1f} s.", flush=True)


def _read_checks() -> None:
    """The pre-check's bundle read into this server's folder (engine.live_check.LiveChecker.load_bundle), and when."""
    global _checks_read_at
    _checks_read_at = _clock()
    live.load_bundle()


def reload_checks_if_due() -> None:
    """On the live site (a live checker with a bucket), the pre-check's bundle read again when the last reading is
    BUNDLE_RELOAD_SECONDS old: one small question about its version, and a download only when the daily run has written
    a new one. /ready asks, so Cloud Scheduler's keep-warm ping every 5 minutes drives it, while Cloud Run gives the
    server its processor (13 Oct 2026: a background thread waiting an hour between requests would barely run). One
    reading at a time; a problem is reported, tried again an hour later, and never stops the ping."""
    if live is None or getattr(live, "bucket", None) is None:
        return
    if _checks_read_at is not None and _clock() - _checks_read_at < BUNDLE_RELOAD_SECONDS:
        return
    if not _checks_lock.acquire(blocking=False):
        return  # another request is reading it now
    try:
        _read_checks()
    except Exception as error:  # reported where the server runs; checks go on with what the folder holds
        print(f"The pre-check's checks couldn't be read again ({type(error).__name__}: {error}).", file=sys.stderr,
              flush=True)
    finally:
        _checks_lock.release()


def warm_answer(product_type: str, library_dir: Path) -> None:
    """One answer about a product type, worked out and thrown away while the server gets ready (latency, 12 Oct
    2026), so what answers keep between requests is ready for the first visitors: retrieval's reading of each thread,
    what each comment's words show, the name matching, the price and facts lookups (engine.memo). Nothing is shown and
    Reddit is never asked: no live check, and every thread read as answers checked live read them
    (live_check_required=False). The answers themselves are never kept. It takes its turn with visitors' answers
    (_answers_lock), so a visitor arriving meanwhile waits for one of these at most, rather than sharing the processor
    with all of them."""
    with _answers_lock:
        answer_request(product_type, library_dir, profiles=profiles, live_check_required=False)


# The product types answered while getting ready: module 1's own (engine.query.PRODUCT_TYPES). The rules route each by
# its name (only "serum", placed by a clue word, also gets the open model's view, as any request would).
WARM_PRODUCT_TYPES = tuple(p.name for p in PRODUCT_TYPES)


def serve(port: int = WEB_PORT, library_dir: Path = DEFAULT_LIBRARY_DIR, site: Site = LOCAL) -> None:
    """Serves the page until Ctrl+C (on the Space, until it is stopped); then hands over any feedback still waiting.
    The server gets ready for answers in the background as it starts (warm_up)."""
    server = make_server(port, library_dir, site)
    threading.Thread(target=warm_up, args=(library_dir,), name="warm-up", daemon=True).start()
    if site.public:
        signal.signal(signal.SIGTERM, _stop)  # how a Space stops its container: wind down as for Ctrl+C
        print(f"Serving the public site for {', '.join(site.hosts)} on port {server.server_address[1]} (answers from "
              f"{library_dir}).", flush=True)
    else:
        print(f"Open http://{HOST}:{server.server_address[1]}/ in your browser (answers from {library_dir}). Ctrl+C stops it.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        if store is not None:
            store.close()


def _stop(signum, frame):
    raise KeyboardInterrupt


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
    global profiles, live, store
    public = "--public" in argv
    options = _options([arg for arg in argv if arg != "--public"])
    if options is None:
        print(__doc__)
        return 2
    port, library_dir = options
    site, problems = site_from_env(os.environ, public)
    for problem in problems:
        print(problem, file=sys.stderr, flush=True)
    if site is None:
        return 2
    try:
        store = feedback.store_from_env()
    except RuntimeError as error:  # feedback set to go to the dataset, without huggingface_hub installed
        print(error, file=sys.stderr)
        return 2
    if public:
        kept = "" if isinstance(store, feedback.HubStore) else (
            " A Space's disk is wiped at every restart: set CREDIBLE_RECS_FEEDBACK_REPO and HF_TOKEN to keep it.")
        print(f"Feedback is {store.describe()}.{kept}", flush=True)
        print(f"Visit counts: {'GoatCounter, ' + site.goatcounter if site.goatcounter else 'off'}.", flush=True)
    from engine.pipeline import cached_profiles

    profiles = cached_profiles()
    from engine.pipeline import live_checker

    live = live_checker()
    if not (library_dir / "threads").is_dir():
        print(f"Warning: no library at {library_dir} (no threads/ folder), so every answer will fail. "
              "Pass --library DIR to use another one.")
    serve(port, library_dir, site)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
