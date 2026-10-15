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
                "category": "skincare" | "kitchen" | "haircare" | "general" | null,
                "product_type": "electric kettle" | null,
                "question": "..." | null,     the one clarifying question, when status is "clarify"
                "message": "..." | null,      the polite no, when status is "out_of_scope"
                "ingredients": [...],         the active ingredients every product shown contains (13 Oct 2026)
                "ingredient_led": bool,       true when the request names ingredients and no product type
                "forms": [...],               the forms an ingredient-led request names ("salicylic acid wash":
                                              ["cleanser"]); [] for any other request (Noemi, 13 Oct 2026)
                "department": "tech" | null}, the general category's department (config.GENERAL_DEPARTMENTS, 14 Oct
                                              2026), which the page shows above the answer; null for the others
      "answer": null when status isn't "ok", else engine.answer.answer_to_dict(...):
                {"category", "product_type",
                 "picks": [{"rank", "product_key", "name", "reason", "support",
                            "quotes": [{"text", "comment_id", "url", "badges": [...]}],   2 or 3, all verified
                            "downsides": [same shape as quotes], "disagreement": "..." | null,
                            "score", "breakdown": {every number behind the score (engine.rank.ScoreBreakdown)},
                            "price": {"text",                  "£120 at <shop>, checked 9 Oct 2026" or
                                                               "Price not checked yet"; for a brand line, its
                                                               from price: "From £25 at <shop>, checked 14 Oct
                                                               2026"
                                      "amount", "currency", "shop", "checked_on",   null when not known
                                      "url",                   the shop's own page, https only, or null
                                      "budget_status",         "within" | "unknown" | "other currency" |
                                                               "out of date", or null without a budget
                                      "budget_note",           the same in words, or null ("From £25, within
                                                               your budget (up to £100)." for a line)
                                      "from_price"},           true when the amount is a brand line's from price
                                                               (Noemi's night decision 1, 14 Oct 2026): the
                                                               cheapest UK price of its products of the type,
                                                               researched in data/brand_lines.json; else false
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
                                       "threads": n,           writers who warned (as the share line counts them) and
                                       "twice": n}             the threads with a credible recommendation; "twice" only
                                                               with Noemi's upvote rule on (14 Oct 2026; off), when
                                                               some of those writers counted twice toward the picks bar
                                                               for their upvotes (the reason says which)
                            "prescription": "Prescription-only in the UK: ask a doctor or pharmacist." | null,
                                                               on a product whose checked facts say it is sold in the UK
                                                               only on a prescription (Noemi's decision 5, 14 Oct 2026);
                                                               "worth_a_look" and "skip" items have it too
                            "range": {"text",                  a brand line's link to its maker's page for its products
                                      "url",                   of the type, or an official UK stockist's (Noemi's night
                                      "checked",               decision 1, 14 Oct 2026): "Browse Victorinox chef
                                      "checked_on"}            knives", the entry's range page exactly as
                                                               data/brand_lines.json writes it (https only, one of its
                                                               sources, never Reddit's, never from a comment), and
                                                               "checked 14 Oct 2026" / "2026-10-14", the day its sources
                                                               were read; null for any other pick, and for a line whose
                                                               entry has no range page
                           }],
                 "look_for": [{"kind", "advice", "quote": {same shape}}],
                 "skip": [{"product_key", "name", "reason", "quotes": [...], "prescription"}],
                 "care_note": [{"tip", "quote"}],   care tips about the kind of product, shown once at the end
                                                    (Noemi, 11 Oct 2026); [] when there are none
                 "worth_a_look": [{"product_key", "name", "reason", "quotes", "downsides", "downsides_share",
                                   "disagreement", "score", "breakdown", "price", "availability", "cautions",
                                   "summary", "voices", "range", "prescription", "meets_bar"}],
                                  "Also worth a look" (Noemi's decision 2, 13 Oct 2026): up to 3 products, shown apart
                                  after the picks and never among them: first those that meet the picks bar but rank
                                  below the top 3, best first ("meets_bar": true, her decision 4 of 15 Oct 2026; the
                                  page tags them with the wording's "meets_bar"), then those with 2 credible
                                  recommendations across at least 2 threads, best first ("meets_bar": false); the same
                                  shapes as a pick's fields, with 1 or 2 quotes, and downsides only when credible voices
                                  warn against it; [] when there are none
                 "worth_note": "2 credible voices each: ...",   the words under its heading, or null without items
                 "message": the honest "not enough evidence" message, or null when there are 3 picks,
                 "needs_more_threads", "quotes_dropped",
                 "title": "Top picks: ...",    the answer's title, as shown (13 Oct 2026)
                 "ingredient": "salicylic acid" | null,   the active ingredients asked for, as shown (13 Oct 2026),
                 "ingredient_note": "..." | null,         and the note under the title saying every product has them;
                 each pick, "worth_a_look" item and "skip" item also has "form": "pads" | null, its form in an
                 ingredient-led answer},
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
                   "not_suited": n,                products whose checked facts clash with the request (9 Oct 2026),
                   "no_ingredient": n,             products without evidence they contain the active ingredients
                                                   asked for, or whose maker's actives don't (13 Oct 2026),
                   "by_form": n,                   products with them left out of an ingredient-led answer for their
                                                   form: rinse-off, not known to be leave-on, or not the form asked
                                                   for (Noemi's decision 1, 13 Oct 2026),
                   "rinse_off": n},                and how many of those are rinse-off
      "timing": {"total_s": s, "reddit_s": s,      diagnostic, never shown (13 Oct 2026): how long the answer took to
                 "checks": n,                      work out, how long it waited on live checks, how many it made,
                 "put_off": n},                    and the comments put off rather than wait (what they back is left out)
      "reading": {"threads": n,                    how much the answer read (Noemi, 12 Oct 2026): the threads used
                                                   (the most relevant to the request),
                  "threads_saved": n,              the extracted threads saved about the product,
                  "comments": n,                   the comments the AI read in the threads used,
                  "read_more": bool}               and whether the first threads gave too few picks, so more were read
                                                   (13 Oct 2026, for the page's reading strip)
      "on_demand": {"state": "reading" | "waiting" | "late",   only on the live site with on-demand reading
                    "product_type": "teapot",                  (engine/on_demand.py, 14 Oct 2026), for a request about a
                    "about": "teapots",                        product the library has too few threads about, now queued
                    "read_before": bool,                       for reading: whether it is being read, waits for the free
                    "check_back_minutes": n | null,            allowance, or is late; its type and plural; whether some
                    "message": "We haven't read Reddit ..."}   threads were read before; when to check back (reading
                                                               only); and the sentence the page shows. Such an answer
                                                               isn't remembered. Absent for every other answer.
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
wait for any of it. On the live site (CREDIBLE_RECS_LIVE_CACHE_BUCKET set) it first reads the checks of the last 48
hours from the bucket's one bundle into its folder, and the daily plan of what to read ahead. Since 14 Oct 2026 (the
free-tier redesign; engine/read_ahead.py) the site reads ahead itself, a few comments each time Cloud Scheduler's
keep-warm ping asks /ready (Cloud Run gives a server its processor only while it answers a request), and writes what
it read to the bundle at most once an hour (read_ahead_on_ping).

On-demand reading (Noemi's plan of 14 Oct 2026, part 3; engine/on_demand.py): on the live site, with its own bucket and
job (CREDIBLE_RECS_ON_DEMAND_BUCKET, CREDIBLE_RECS_ON_DEMAND_JOB), a request whose product the library has too few
threads about is queued and the reading job started; the answer says so ("on_demand" above) and isn't remembered. The
threads it reads are taken into the library folder first of all as the server gets ready, then at the keep-warm ping
(every ping while a request it queued waits, at most hourly otherwise; reload_on_demand_if_due), and answers use them
like any other, every quote shown checked live. This server writes the queue (only over the version it read), never
the threads.

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
from engine.config import (ANSWERS_KEPT_TYPES, BRAND_PICK_MODEL, FEEDBACK_MAX_BODY_BYTES, FEEDBACK_MAX_COMMENT_CHARS,
                           LEFT_OUT_NAMES_SHOWN,
                           PICKS_SHOWN, RATE_LIMIT_ANSWERS, RATE_LIMIT_FEEDBACK, RATE_LIMIT_WINDOW_SECONDS, WEB_MAX_REQUEST_CHARS,
                           WEB_PORT)
from engine.library import DEFAULT_LIBRARY_DIR
from engine.metrics import METRICS_FILE
from engine.parse_reddit import REPO_ROOT
from engine import memo
from engine.pipeline import PipelineResult, answer_request, request_kind
from engine.query import FIRST_PRODUCT_TYPES, PRODUCT_TYPES

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
# What answers worked out is kept for at most ANSWERS_KEPT_TYPES product types (15 Oct 2026; engine.memo.TypeWindow):
# every answer worked out here, a visitor's or a warm one, says its type first. With ~1,950 threads the live site had
# run out of memory at 2 GiB, every type's work kept as it warmed ~480 requests.
_window = memo.TypeWindow(ANSWERS_KEPT_TYPES)
_clock = time.monotonic
# Where writers' standing comes from (engine.pipeline's `profiles`): the command line sets the Arctic Shift cache
# (engine.profiles.CachedOnly, never a call); None, as in the tests, leaves writers known by name only.
profiles = None
# The live check of every shown quote (engine.live_check): set by the command line; None in the tests.
live = None
# On-demand reading (Noemi's plan of 14 Oct 2026, part 3; engine/on_demand.py): set by the command line when the live
# site has its bucket and job (CREDIBLE_RECS_ON_DEMAND_BUCKET, CREDIBLE_RECS_ON_DEMAND_JOB); None otherwise and in the
# tests, which give their own.
on_demand = None
# Where feedback goes (engine.feedback, 11 Oct 2026): set by the command line; None in the tests, which give their own.
store = None
_answers_lock = threading.Lock()
# Visitors waiting for _answers_lock (14 Oct 2026, measured live just after a deploy: a visitor's answer queued 31 s
# behind a warming slice, because Python's lock isn't fair and the slice took it back for its next request before the
# visitor's thread woke). A slice of warming (warm_more) starts no answer while one is waiting.
_visitors_waiting = 0
_visitors_lock = threading.Lock()


def _visitor_waits(change: int) -> None:
    global _visitors_waiting
    with _visitors_lock:
        _visitors_waiting += change
# Set once the server has got ready (warm_up). Until then /ready says 503, and Cloud Run sends visitors to the server
# only when it says 200 (13 Oct 2026, the live site's latency): a new server getting ready took turns with its first
# visitors' answers and held them up to 30 s, with the processor Cloud Run gives a server only while it answers
# someone. While it starts, Cloud Run gives it the processor in full, and keeps visitors on the server before it.
ready = threading.Event()
# The site's reads ahead (engine/read_ahead.py, 14 Oct 2026): set by the command line when the live checker has the
# bucket; None otherwise and in the tests, which give their own.
read_ahead = None


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
        page = how_page.page(METRICS_FILE, counter=counter_script(site.goatcounter), public=site.public,
                             on_demand=on_demand is not None)
        return 200, HTML, page.encode("utf-8")
    if parts.path == "/api/answer":
        request = parse_qs(parts.query).get("q", [""])[0]
        return answer_response(request, Path(library_dir), quiet=site.public)
    if parts.path == READY_PATH:
        if ready.is_set():
            read_ahead_on_ping()
            reload_on_demand_if_due()
            warm_more()  # the requests getting ready had no time for, a slice per keep-warm ping (14 Oct 2026)
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
    _visitor_waits(+1)
    with _answers_lock:  # one answer is worked out at a time, so the same request is never worked out twice
        _visitor_waits(-1)
        remembered = _answers.get(key)
        if remembered is None or _clock() - remembered[0] >= ANSWER_KEEP_HOURS * 3600:
            try:
                _window.answered(request_kind(request))
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
    answer is whole: nothing in it was left out because its live check would have waited (13 Oct 2026), and since 14
    Oct 2026 it isn't an answer on-demand reading is about to change (engine/on_demand.py: a request queued for
    reading, or one whose queue couldn't be read): such an answer is worked out again next time."""
    with_profiles = {} if profiles is None else {"profiles": profiles}
    timed = _TimedChecker(live) if live is not None else None
    if timed is not None:
        with_profiles["live_checker"] = timed
    started = time.perf_counter()
    result = answer_request(request, library_dir, **with_profiles)
    reading = on_demand.after_answer(result) if on_demand is not None else None
    if reading is not None and reading.again:  # threads read on demand have just come in: answered with them
        _answers.clear()  # (the lock is held here) every remembered answer is worked out again with them too
        result = answer_request(request, library_dir, **with_profiles)
        reading = on_demand.after_answer(result)
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
    extra = {"on_demand": reading.state} if reading is not None and reading.state is not None else {}
    whole = result.live_put_off == 0 and (reading is None or reading.remember)
    return (200, JSON, _json_bytes(answer_json(result) | {"timing": timing} | extra)), whole


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
                  "question": query.question, "message": query.message,
                  "ingredients": list(query.constraints.ingredients), "ingredient_led": query.ingredient_led,
                  "forms": list(query.constraints.forms), "department": query.department},
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
                     "not_suited": len(result.left_out_not_suited),
                     "no_ingredient": len(result.left_out_no_ingredient),
                     "by_form": len(result.left_out_by_form),
                     "rinse_off": sum(item.rinse_off for item in result.left_out_by_form)},
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
        # The tag of an item there that meets the picks bar but ranks below the top 3 (Noemi's decision 4, 15 Oct 2026).
        "meets_bar": wording.MEETS_BAR,
        # One-line summaries (Noemi, 13 Oct 2026): "In short:" and the note saying it is ours, not a quote.
        "summary_label": wording.SUMMARY_LABEL,
        "summary_note": wording.SUMMARY_NOTE,
        # Active ingredients (13 Oct 2026): the label of each product's form in an ingredient-led answer.
        "form_label": wording.FORM_LABEL,
        # Brand lines (14 Oct 2026): a line's from price as an amount alone ("From £25"), in "At a glance" and its row.
        "price_from_amount": wording.PRICE_FROM_AMOUNT,
        # Prescription-only products (Noemi's decision 5, 14 Oct 2026): the tag on a row under the picks before it is
        # opened, and on a pick's row "At a glance"; the note itself comes with each product ("prescription").
        "prescription_tag": wording.PRESCRIPTION_TAG,
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
    piece reports it as before. On the live site, first of all, the checks of the last 48 hours, read from the bucket's
    bundle into this server's folder (engine.live_check.LiveChecker.load_bundle; 13 Oct 2026), and the daily plan of
    what to read ahead (engine/read_ahead.py; 14 Oct 2026)."""
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
    if on_demand is not None:  # first of all (14 Oct 2026): the library is then read once, with them
        steps.insert(0, ("the threads read on demand", on_demand.warm_up))
    for name, step in steps:
        step_started = time.perf_counter()
        _step(name, step)
        # Each step's time, in the server's window (14 Oct 2026: on Cloud Run getting ready warmed far fewer requests
        # than on this Mac in its time; this shows which step takes it).
        print(f"Getting ready: {name} took {time.perf_counter() - step_started:.1f} s.", flush=True)
    left = []
    for request in warm_requests() if threads.is_dir() else ():
        if time.perf_counter() - started >= WARM_UP_ANSWERS_SECONDS:
            left.append(request)  # warmed later, a slice per keep-warm ping (warm_more), or by its first visitor
            continue
        _step(f"{WARM_ANSWER_STEP} {request}", lambda request=request: warm_answer(request, library_dir))
    if left:
        print(f"Getting ready: left {len(left)} requests for their first visitors (time up after "
              f"{WARM_UP_ANSWERS_SECONDS} s).", flush=True)
    with _warming:
        _left_to_warm[:] = left
        _left_in[:] = [library_dir]
    ready.set()
    print(f"Ready for visitors: got ready in {time.perf_counter() - started:.1f} s.", flush=True)


def _step(name: str, step) -> None:
    """One step of getting ready; a problem is reported where the server runs, and never stops it: answers report it
    again when they need it."""
    try:
        step()
    except Exception as error:
        print(f"Getting ready: {name} couldn't be loaded ({type(error).__name__}: {error}).", file=sys.stderr,
              flush=True)


def warm_more() -> None:
    """The next of the requests getting ready had no time for (warm_up), warmed while the keep-warm ping asks /ready
    (14 Oct 2026, the coordinator's request: on Cloud Run's one processor getting ready warmed 13 of 65 requests in its
    time, and a request whose threads weren't warmed took ~8 s; Cloud Run gives a server its processor only while it
    answers someone, so a thread warming in the background would barely run). Each ping warms the next ones for up to
    WARM_MORE_SECONDS (an answer begun then ends), each taking its turn with visitors' answers as getting ready's do
    (warm_answer), until none are left; one slice at a time (a ping arriving meanwhile only says it is ready). A slice
    starts no answer while a visitor is waiting for their turn (_visitors_waiting): the next ping carries on."""
    if not _left_to_warm or not _warming.acquire(blocking=False):
        return
    try:
        started, warmed, gave_way = time.perf_counter(), 0, False
        while _left_to_warm and time.perf_counter() - started < WARM_MORE_SECONDS:
            if _visitors_waiting:
                gave_way = True
                break
            request = _left_to_warm.pop(0)
            _step(f"{WARM_ANSWER_STEP} {request}", lambda: warm_answer(request, _left_in[0]))
            warmed += 1
        way = "; a visitor's answer came first" if gave_way else ""
        print(f"Getting ready: warmed {warmed} more, {len(_left_to_warm)} left{way}.", flush=True)
    finally:
        _warming.release()


def _read_checks() -> None:
    """The bucket's bundle read into this server's folder (engine.live_check.LiveChecker.load_bundle), then the daily
    plan of what to read ahead, with its checks through Bright Data (engine.read_ahead.ReadAhead.reload_plan_if_due)."""
    live.load_bundle()
    if read_ahead is not None:
        read_ahead.reload_plan_if_due()


def read_ahead_on_ping() -> None:
    """On the live site (a live checker with the bucket), Cloud Scheduler's keep-warm ping reads ahead (engine/
    read_ahead.py, 14 Oct 2026): a new plan when due (asked at most hourly), the comments due read within the ping's
    limits, and what was read written to the bundle at most hourly. Since then the site no longer reads the bundle again
    each hour: it writes it, and reads another writer's version only before writing over it. A problem is reported and
    never stops the ping."""
    if read_ahead is None:
        return
    try:
        read_ahead.on_ping()
    except Exception as error:  # reported where the server runs; answers go on reading what they need
        print(f"Reading ahead failed ({type(error).__name__}: {error}).", file=sys.stderr, flush=True)


def reload_on_demand_if_due() -> None:
    """On the live site with on-demand reading (engine/on_demand.py, 14 Oct 2026), at Cloud Scheduler's keep-warm ping:
    the threads read on demand looked for (at every ping while a request this server queued waits, at most hourly
    otherwise; one small question about the bundle's version, a download only when it changed) and the reading job
    started again when it should run and doesn't. When threads come in or go, every remembered answer is forgotten,
    without waiting for an answer being worked out (a dict emptied at once). A problem is reported and never stops
    the ping."""
    if on_demand is None:
        return
    try:
        if on_demand.on_ping():
            _answers.clear()
    except Exception as error:  # reported where the server runs; answers go on with the library they have
        print(f"The threads read on demand couldn't be looked for ({type(error).__name__}: {error}).",
              file=sys.stderr, flush=True)


def warm_answer(request: str, library_dir: Path) -> None:
    """One answer to a request (warm_requests), worked out and thrown away while the server gets ready (latency, 12
    Oct 2026), so what answers keep between requests is ready for the first visitors: retrieval's reading of each
    thread, what each comment's words show, the name matching, the price and facts lookups (engine.memo). Nothing is
    shown and Reddit is never asked: no live check, and every thread read as answers checked live read them
    (live_check_required=False). The answers themselves are never kept. It takes its turn with visitors' answers
    (_answers_lock), so a visitor arriving meanwhile waits for one of these at most, rather than sharing the processor
    with all of them."""
    with _answers_lock:
        _window.answered(request_kind(request))
        answer_request(request, library_dir, profiles=profiles, live_check_required=False)


def warm_requests() -> list[str]:
    """The requests answered while getting ready (14 Oct 2026, the coordinator's requests after the live site's getting
    ready reached 7, then 13, of its requests in its time), each once, in the order that takes the most cold work away
    soonest (measured on this Mac: eval/LATENCY.md):

    - the search page's example requests (the first of WARM_FIRST_FILES): what a visitor clicks, word for word;
    - then one request for each product type not asked yet (WARM_PRODUCT_TYPES' order), its likeliest: the first of the
      latency requests that module 1's rules place as that type, else the type's own name. A type's first answer reads
      every thread of its category for it, the biggest part of a cold answer, which every later request of that type
      then finds done, however it is worded;
    - then the rest of the latency requests and the types' names: the threads their needs lead to;
    - then the requests module 1 asks the open model about ("serum", "something nice for my mum"): a reading of
      seconds, which warms that very request only.
    Not the taxonomy's types by their names (WARM_TAXONOMY_TYPES), warmed last from 14 Oct 2026 until 15 Oct 2026 (the
    coordinator: warm only what pays): they have almost no threads yet, so their answers warm little, the latency set's
    general request already does the general category's own work (its readable threads, each thread's comments read),
    and the answers' memory keeps ANSWERS_KEPT_TYPES types' work (_window), fewer than their 398: warming them had
    filled the memory (the live site ran out of it at 2 GiB). Each is worked out for its first visitor.
    What getting ready has no time for (WARM_UP_ANSWERS_SECONDS) is warmed a slice per keep-warm ping (warm_more)."""
    examples = _requests_in(WARM_FIRST_FILES[0]) if WARM_FIRST_FILES else []
    likely = [text for path in WARM_FIRST_FILES for text in _requests_in(path)]
    every = list(dict.fromkeys(likely + list(WARM_PRODUCT_TYPES)))
    placed = {text: _placed_by_rules(text) for text in every}
    per_type = [text for product_type in WARM_PRODUCT_TYPES
                if (text := next((t for t in every if placed[t] == (product_type, False)), None)) is not None]
    lead = list(dict.fromkeys(examples + per_type))
    rest = [text for text in every if text not in lead]
    return lead + [t for t in rest if not placed[t][1]] + [t for t in rest if placed[t][1]]


def _placed_by_rules(text: str) -> tuple[str | None, bool]:
    """The product type module 1 places a request as (None for a question or a polite no), and whether it would ask the
    open model about it: module 1 run with a stand-in that only notes being asked, so its rules alone decide."""
    from engine.query import parse_query

    class _Noting:
        asked = False

        def read(self, text: str):
            self.asked = True
            return None

    noting = _Noting()
    query = parse_query(text, model=noting)
    return (query.product_type if query.status == "ok" else None), noting.asked


def _requests_in(path: Path) -> list[str]:
    """The requests of a file of requests: the blind-test questions ("questions") or the latency requests ("queries");
    none when there is no such file."""
    if not Path(path).is_file():
        return []
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [item["text"] for item in data.get("questions", data.get("queries", []))]


# The requests answered first while getting ready (warm_requests): the search page's examples, then the latency
# requests (each type's likeliest first).
LATENCY_FILE = REPO_ROOT / "eval" / "edge_cases" / "latency_queries.json"
WARM_FIRST_FILES = (EXAMPLES_FILE, LATENCY_FILE)
# Then the product types: module 1's own first 43 (engine.query.FIRST_PRODUCT_TYPES). The rules route each by its name
# (only "serum", placed by a clue word, also gets the open model's view, as any request would).
WARM_PRODUCT_TYPES = tuple(p.name for p in FIRST_PRODUCT_TYPES)
# And after every other request, the 351 types of the taxonomy (engine/data/product_types.json, 14 Oct 2026; the
# general category's, and a few kitchen and haircare ones), each by its name: the rules route each so.
WARM_TAXONOMY_TYPES = tuple(p.name for p in PRODUCT_TYPES[len(FIRST_PRODUCT_TYPES):])
WARM_ANSWER_STEP = "the answers' memory for"
# Getting ready starts no more warm answers once this many seconds have passed (13 Oct 2026): Cloud Run's startup probe
# waits 4 minutes for /ready (deploy/cloudrun/deploy.sh), and the warm answers alone had grown past that, so a deploy
# failed (the server before it kept serving). The requests left are warmed later, a slice per keep-warm ping
# (warm_more), unless a visitor asks one first. 90 since 15 Oct 2026: counted from the start of getting ready (the
# library's reading included), the answer under way when the time is up still ends, and with the library grown to
# ~1,950 threads a server got ready in 168.5 s with 120; 90 keeps the probe's 4 minutes far off, and the pings (which
# give way to visitors) warm the rest.
WARM_UP_ANSWERS_SECONDS = 90
# How long each keep-warm ping warms the requests left (warm_more, 14 Oct 2026): well inside the ping's attempt deadline
# (180 s, deploy/cloudrun/deploy.sh), and short enough that a visitor waits at most one warm answer behind it.
WARM_MORE_SECONDS = 40
# The requests left (warm_more) and the library they are answered from, kept by warm_up; one slice at a time.
_left_to_warm: list[str] = []
_left_in: list[Path] = []
_warming = threading.Lock()


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
    global profiles, live, store, on_demand, read_ahead
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
    if getattr(live, "bucket", None) is not None:  # the live site: it reads ahead (engine/read_ahead.py)
        from engine.read_ahead import ReadAhead

        read_ahead = ReadAhead(live)
    from engine.on_demand import site_reader_from_env

    try:
        on_demand = site_reader_from_env(os.environ, library_dir)
    except ValueError as error:  # a job name that isn't one: the site runs without on-demand reading
        print(f"On-demand reading is off: {error}", file=sys.stderr, flush=True)
    if on_demand is not None:
        print(f"On-demand reading: on (queue and threads in {on_demand.bucket.name}).", flush=True)
    if not (library_dir / "threads").is_dir():
        print(f"Warning: no library at {library_dir} (no threads/ folder), so every answer will fail. "
              "Pass --library DIR to use another one.")
    serve(port, library_dir, site)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
