"""Checking ahead (Noemi's decision of 13 Oct 2026): the comments answers would show are read live on Reddit in advance,
every day, within Reddit's limits, so a visitor's fresh answer finds its quotes already checked.

Why. Before an answer shows a quote, its comment is read live through Reddit's embed page (engine/live_check.py). A
fresh answer needs 20 to 40 such reads, and Reddit's embed pages allow about 200 reads in 10 minutes from one address:
once that allowance is used, each read waits its turn (one every 4 s), and a fresh answer took a minute or two. The
rule doesn't change: a quote is shown only with a passing live check from the last 48 hours. What changes is when the
check is made: mostly ahead of time, so answers find it saved.

Who reads (14 Oct 2026, the free-tier redesign). On Google Cloud the daily job no longer reads the embed page itself: a
Cloud Run job is billed for its whole run, and two thirds of its run went on waiting for Reddit's allowance. With
--plan (deploy.sh runs it so) it works out what to read and leaves the site a plan in the bucket (plan_run): the
comments below, likeliest first, then the slimmed library's kept comments due to be verified, and its checks through
Bright Data; the site, billed only while it answers, reads them a few at each keep-warm ping (engine/read_ahead.py) and
shares what it read through the bucket's bundle, which the next run starts from. Without --plan (on Noemi's computer,
say) a run reads them itself, as below.

What is read, worked out without reading Reddit (comments_to_check):
1. the requests (requests_to_check): the search page's example requests (the blind-test questions), the latency eval's
   requests, then every product type the library answers, by its name: module 1's own types, and the open model's
   types the library holds threads about (its request log, and config.PRECHECK_MODEL_TYPES where the log isn't kept);
2. each request's answer, as the live site writes it (engine.pipeline.answer_request, with writers' standing from the
   library), every quote taken as passing except where a saved check already says a comment was deleted or edited: then
   that comment drops out and what replaces it is shown, as for a visitor. Every quote the live check must pass counts
   (engine.answer.quotes_to_check): a pick's quotes, its downsides and care tips, "Also worth a look" with its
   downsides, the care note, "What to look for" and "Avoid", the skip list, and the comments the one-line summaries
   cite;
3. what would be shown if checks failed: the answer written again (module 7's own write_answer, with what the pipeline
   gave it) without each comment it shows, one at a time, so that place's next in line shows (a pick's next quote, the
   next downside, care tip or note); with its picks set aside, so the products ranked just behind them show; and
   without every comment of those two, for the places' next in line after that (a pick left with too few quotes gives
   its place to the next product, as it would).
Each comment gets a tier (0: shown; 1: next in line; 2: behind the picks; 3: next after that), and they are read in
that order, a pick's own quotes before the rest of each tier, then by request, then by place in the answer: the
likeliest to be shown first. A comment in several answers or places is read once, at its likeliest.

How it is read (check_ahead): through the live site's own checker (engine.live_check.checker_from_env: the same pace,
the same 48-hour cache; but a read waits for Reddit's next 10 minutes however long that is, config.
PRECHECK_MAX_WAIT_SECONDS, since nobody waits on it), one comment at a time, until the run's budget is spent: its reads
(--limit, default config.PRECHECK_MAX_READS) or its time (--minutes from the run's start, default
config.PRECHECK_MAX_RUN_MINUTES: no read starts after it, so the job's bill stays inside the free tier; 14 Oct 2026). On Google Cloud the checks are shared with the site through the bucket, as
one object (engine.live_check.LiveChecker.load_bundle and save_bundle): read as a run starts, written midway and at the
end. A comment read less than config.PRECHECK_FRESH_HOURS ago is skipped; an older one is read again, so the next
day's answers never find its check expired. A run stops when Reddit stops answering (config.PRECHECK_STOP_AFTER_UNKNOWN
unreadable pages in a row). The report gives counts and times only, never a comment's words.

Comments the embed page can't show (Noemi, 13 Oct 2026: "Use Bright Data"). For about 1 comment in 8 the embed page
holds no comment ("Not supported comment", likely comments with photos): it is kept as unreadable and never shown. After
the embed reads, the comments needed here whose check is that kind are verified through Bright Data instead
(verify_through_bright_data): their threads are read as Reddit shows them now (engine/bright_data.py, its pacing and
monthly records), the likeliest to be shown first, in one batch of at most config.PRECHECK_BRIGHT_DATA_MAX_THREADS
threads and config.PRECHECK_BRIGHT_DATA_RECORDS records a run (estimated from the library's copy of each thread: its
post and its top-level comments). Each comment found gets a normal check, its own text as Reddit shows it now, saved
when Bright Data read it (via "bright_data"), used like any other (found word for word, gone, changed) for 48 hours, and
shared in the bundle. One its answer doesn't hold stays unreadable: Bright Data returns top-level comments and their
direct replies only, so missing never means deleted. Such a check isn't read again on the embed page, and through Bright
Data only after config.PRECHECK_BRIGHT_DATA_FRESH_HOURS. The site itself never calls Bright Data. With
CREDIBLE_RECS_PRECHECK_BRIGHT_DATA=off (deploy.sh sets it when the key's secret, bright-data-key, isn't there; 14 Oct
2026) the step is off: nothing is read through Bright Data, and the report says so in one line. A thread Bright Data
couldn't read is remembered (BrightDataMemory: in the bucket beside the plan, since each run on Google Cloud starts with
an empty disk; on a computer, next to its checks) with Bright Data's status and error, which the report gives for each,
and left for config.PRECHECK_BRIGHT_DATA_SKIP_DAYS so the records go to the next threads; one whose post is gone holds
comments that can't be verified that way: taken as unverifiable for config.PRECHECK_BRIGHT_DATA_GONE_DAYS, they cost no
record again and drop out of the answers worked out here, as they do for a visitor (14 Oct 2026, the coordinator: the
same two threads had failed at every run).

Keeping a slimmed library verified (Noemi, 13 Oct 2026: "Keep only comments we use"; engine/slim.py, engine/verify.py).
After those reads, the comments the library's slimmed threads keep are verified one by one on the same embed page
(verify_kept): first, what today's checks already say about them is recorded (the comments just read, the bundle's);
then the kept comments verified longest ago are read, oldest first (a comment never verified counts from the day its
thread was read), within a budget of their own (--verify N, default config.LIBRARY_VERIFY_READS), each one at most
every config.LIBRARY_VERIFY_AGAIN_DAYS; a comment found deleted or edited isn't read again (the next deploy drops it),
and a page with no comment on it is tried again after config.LIBRARY_VERIFY_RETRY_DAYS. Every read goes into the
verification record (engine.verify.Ledger: when, and what it said; ids, dates and outcomes only, never any words): on
this machine (.cache/verified.json) and, with a bucket, next to the bundle (live_check/verified.json). The library
itself is never changed here: it is baked into the site's image, so `python -m engine.library apply-checks` applies the
record before each deploy (deploy/cloudrun/deploy.sh).

    python -m engine.precheck [--limit N] [--minutes M] [--verify N] [--dry-run]
    python -m engine.precheck --plan [--minutes M] [--verify N] [--dry-run]

--plan (the daily job on Google Cloud, with CREDIBLE_RECS_LIVE_CACHE_BUCKET): the plan for the site, read nothing on the
embed page; --minutes is then when the Bright Data step starts nothing more (config.PRECHECK_PLAN_MINUTES), and --verify
how many kept comments the plan asks the site to read (config.LIBRARY_VERIFY_READS).

--dry-run works out the comments and says how many would be read and how many are fresh, reading nothing on Reddit,
and how many comments and threads would be read through Bright Data, and about how many records that would use.
On Google Cloud a Cloud Run job runs it once a day (deploy/cloudrun/DEPLOY.md).

The products read on demand (14 Oct 2026; engine/on_demand.py): with CREDIBLE_RECS_ON_DEMAND_BUCKET set, the command
first takes the threads read on demand into its library folder, and checks ahead the answers about every product type
in on-demand reading's queue, after the requests above.
"""

import dataclasses
import inspect
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from engine import memo, on_demand, pipeline
from engine.answer import Answer, ShownQuote, quotes_to_check
from engine.config import (ANSWERS_KEPT_TYPES, BRIGHT_DATA_BATCH_THREADS, LIBRARY_VERIFY_AGAIN_DAYS, LIBRARY_VERIFY_DAYS,
                           LIBRARY_VERIFY_READS, LIBRARY_VERIFY_RETRY_DAYS, PICKS_SHOWN,
                           PRECHECK_BRIGHT_DATA_FRESH_HOURS, PRECHECK_BRIGHT_DATA_GONE_DAYS,
                           PRECHECK_BRIGHT_DATA_MAX_THREADS, PRECHECK_BRIGHT_DATA_SKIP_DAYS,
                           PRECHECK_BRIGHT_DATA_RECORDS, PRECHECK_FRESH_HOURS, PRECHECK_MAX_READS,
                           PRECHECK_MAX_RUN_MINUTES, PRECHECK_MAX_WAIT_SECONDS, PRECHECK_MODEL_TYPES,
                           PRECHECK_PLAN_MINUTES, PRECHECK_STOP_AFTER_UNKNOWN)
from engine.library import DEFAULT_LIBRARY_DIR
from engine.live_check import LiveResult, checker_from_env
from engine.parse_reddit import REPO_ROOT, parse_thread_url
from engine.query import PRODUCT_TYPES
from engine.read_ahead import PLAN_NAME, plan_bytes
from engine.verify import FAILED, LEDGER_NAME, KeptComment, Ledger, kept_comments, outcome, record_saved_checks

QUESTIONS_FILE = REPO_ROOT / "eval" / "blind_test" / "questions.json"  # the search page's example requests
LATENCY_FILE = REPO_ROOT / "eval" / "edge_cases" / "latency_queries.json"
INGREDIENTS_FILE = REPO_ROOT / "eval" / "edge_cases" / "ingredients.json"  # the ingredient eval's requests (13 Oct 2026)
TIERS = ("shown", "next in line", "behind the picks", "next after those")  # each tier in words, for the report
SET_ASIDE = "set aside by the pre-check, to see what is ranked behind it"  # never shown: these answers are thrown away
PROGRESS_EVERY = 100  # reads between progress lines on stderr


@dataclass(frozen=True)
class Candidate:
    """A comment to read ahead: its link, its id, every quote of it an answer could show, and how likely it is to be
    shown (tier, then section: 0 for a pick's own quotes, 1 for the rest; then the request's place in the list and the
    quote's place in its answer)."""

    url: str
    comment_id: str
    quotes: tuple[str, ...]
    tier: int
    section: int
    request: int
    place: int

    @property
    def order(self) -> tuple[int, int, int, int]:
        return self.tier, self.section, self.request, self.place


@dataclass
class Reading:
    """What one run read, in counts."""

    read: int = 0  # comments read on Reddit now
    passing: int = 0  # still there, every quote found word for word
    gone: int = 0  # deleted or removed
    changed: int = 0  # edited: a quote no longer found
    unknown: int = 0  # the page couldn't be read
    fresh: int = 0  # skipped: read less than PRECHECK_FRESH_HOURS ago
    via_bright_data: int = 0  # skipped: verified through Bright Data (its embed page shows no comment)
    would_read: int = 0  # a dry run: what would have been read
    not_reached: int = 0  # left for lack of reads or time in this run's budget
    out_of_time: float | None = None  # the run's minutes, when they ran out before its reads
    stopped: bool = False  # stopped early: Reddit stopped answering
    seconds: float = 0.0


@dataclass
class _Found:
    """The comments worked out for the requests, with counts for the report."""

    candidates: list[Candidate] = field(default_factory=list)
    answered: int = 0
    failed: int = 0  # requests the pipeline couldn't answer (each named on stderr)


# --- Which requests ---

def requests_to_check(questions: Path = QUESTIONS_FILE, latency: Path = LATENCY_FILE,
                      library_dir: Path = DEFAULT_LIBRARY_DIR, ingredients: Path = INGREDIENTS_FILE) -> list[str]:
    """The requests whose answers are checked ahead, likeliest first, each once: the search page's example requests
    (the blind-test questions), the latency eval's requests, module 1's product types, the open model's types in the
    library's request log, config.PRECHECK_MODEL_TYPES, then the ingredient eval's requests (13 Oct 2026: ingredient-led
    answers read skincare threads of every type). A missing file adds nothing."""
    found = [q["text"] for q in _read_json(questions).get("questions", [])]
    found += [q["text"] for q in _read_json(latency).get("queries", [])]
    found += [p.name for p in PRODUCT_TYPES]
    found += _logged_types(Path(library_dir) / "requests.jsonl")
    found += list(PRECHECK_MODEL_TYPES)
    found += [q["text"] for q in _read_json(ingredients).get("cases", [])]
    return list(dict.fromkeys(text.strip() for text in found if text and text.strip()))


def _read_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _logged_types(log: Path) -> list[str]:
    """The product types of the requests the library was filled for (`library add`'s log), as module 1 placed them."""
    try:
        lines = Path(log).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    types = []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("status") == "ok" and isinstance(entry.get("product_type"), str):
            types.append(entry["product_type"])
    return types


# --- Which comments ---

class _AsIfChecked:
    """The checker answers get while the pre-check works out what they show: a comment with a saved check is answered
    by it (one deleted or edited drops out, as it would for a visitor); one without is taken as passing, since it is
    about to be read, and so is one whose embed page showed no comment, since it is about to be verified through
    Bright Data. But not one of `unverifiable` (comment ids: a post Bright Data found gone held them, and their embed
    page showed no comment; BrightDataMemory): it can't be verified, so it drops out as it does for a visitor, and what
    shows instead is read ahead. Reddit is never read here."""

    def __init__(self, live, unverifiable=frozenset()):
        self.live, self.unverifiable = live, frozenset(unverifiable)

    def check(self, url: str, quote: str, wait: bool = True) -> LiveResult:
        saved = self.live.saved_check(url, quote)
        if saved is not None and saved.status != "unknown":
            return saved
        if [part for part in url.split("/") if part][-1] in self.unverifiable:
            return LiveResult("unknown", "its post is gone and its embed page shows no comment: it can't be verified")
        return LiveResult("ok", "not checked yet: taken as passing for now")


@contextmanager
def _answers_kept():
    """While open, each answer the pipeline writes is kept with what it was written from (engine.answer.write_answer's
    arguments), so it can be written again as it would be if checks failed. The pipeline itself is unchanged, and the
    pre-check runs as a process of its own, never inside the site, so no visitor's answer passes through here."""
    written: list[tuple[dict, Answer]] = []
    original = pipeline.write_answer
    signature = inspect.signature(original)

    def keeping(*args, **kwargs):
        answer = original(*args, **kwargs)
        written.append((dict(signature.bind(*args, **kwargs).arguments), answer))
        return answer

    pipeline.write_answer = keeping
    try:
        yield written, original
    finally:
        pipeline.write_answer = original


def comments_to_check(requests: list[str], library_dir: Path = DEFAULT_LIBRARY_DIR, checker=None,
                      profiles=None) -> list[Candidate]:
    """The comments the requests' answers show or hold next in line, likeliest to be shown first (see the module's
    docstring). `checker`: the live checker whose saved checks count (engine.live_check.LiveChecker); it never reads
    Reddit here. `profiles`: writers' standing, as engine.pipeline takes it."""
    return _work_out(requests, library_dir, checker, profiles).candidates


def _work_out(requests: list[str], library_dir: Path, checker, profiles, unverifiable=frozenset()) -> _Found:
    """The comments of every request's answer, and those next in line (comments_to_check). What answers work out is
    forgotten once they have asked about more than ANSWERS_KEPT_TYPES product types since it last was (engine.memo.
    TypeWindow, 15 Oct 2026: kept for every type, it had made the plan job's memory grow with the types, 2.25 GB for 486
    requests over ~1,950 threads): the library stays read, and the answers are the same."""
    found = _Found()
    as_if = _AsIfChecked(checker, unverifiable)
    every: list[Candidate] = []
    window = memo.TypeWindow(ANSWERS_KEPT_TYPES)
    with _answers_kept() as (written, write_answer):
        for number, request in enumerate(requests):
            written.clear()
            window.answered(pipeline.request_kind(request))
            try:
                result = pipeline.answer_request(request, library_dir=library_dir, profiles=profiles,
                                                 live_checker=as_if)
            except Exception as error:  # a broken library file, say: the other requests are still checked ahead
                found.failed += 1
                print(f"  {request!r} couldn't be answered ({type(error).__name__}: {error}): left out of this run.",
                      file=sys.stderr, flush=True)
                continue
            if result.answer is None:
                continue
            found.answered += 1
            arguments = next(args for args, answer in reversed(written) if answer is result.answer)
            for tier, answers in enumerate(_written_again(arguments, result.answer, write_answer)):
                every += [Candidate(quote.url, quote.comment_id, (quote.text,), tier, section, number, place)
                          for answer in answers for place, (section, quote) in enumerate(shown_quotes(answer))]
    found.candidates = merged(every)
    return found


def _written_again(arguments: dict, answer: Answer, write_answer) -> list[list[Answer]]:
    """The answer, then written again as it would be if checks failed, by tier: [the answer], [the answer without each
    comment it shows, one at a time: each place's next in line], [the answer with its picks set aside: the products
    ranked behind them], [the answer without every comment of the first two: the next in line after those]."""
    bodies = arguments["bodies"]
    shown = _comment_ids(answer)
    one_less = [write_answer(**{**arguments, "bodies": _without(bodies, {cid})}) for cid in sorted(shown)]
    picks = {pick.product_key for pick in answer.picks[:PICKS_SHOWN]}
    ranking = arguments["ranking"]
    set_aside = dataclasses.replace(ranking, products=[
        dataclasses.replace(p, qualifies=False, shortfall=SET_ASIDE) if p.key in picks else p
        for p in ranking.products])
    behind = write_answer(**{**arguments, "ranking": set_aside})
    next_in_line = set().union(*(_comment_ids(a) for a in one_less)) if one_less else set()
    after_those = write_answer(**{**arguments, "bodies": _without(bodies, shown | next_in_line)})
    return [[answer], one_less, [behind], [after_those]]


def _without(bodies, comment_ids: set[str]) -> dict[str, str]:
    """The comments' texts less these: their quotes fail module 7's check, as a comment dropped by a live check does."""
    return {cid: body for cid, body in bodies.items() if cid not in comment_ids}


def _comment_ids(answer: Answer) -> set[str]:
    return {quote.comment_id for _, quote in shown_quotes(answer)}


def shown_quotes(answer: Answer) -> list[tuple[int, ShownQuote]]:
    """Every quote the live check must pass before the answer is shown (engine.answer.quotes_to_check: the quotes it
    shows, "Also worth a look" and its downsides among them, then the quotes its one-line summaries cite), in its own
    order (the picks first), each with its section: 0 for a pick's own quotes ("In their words"), 1 for the rest."""
    own = {id(quote) for pick in answer.picks for quote in pick.quotes}
    return [(0 if id(quote) in own else 1, quote) for quote in quotes_to_check(answer)]


def merged(candidates: list[Candidate]) -> list[Candidate]:
    """One candidate per comment, at its likeliest order, holding every quote of it (each once, likeliest first);
    sorted likeliest first."""
    by_url: dict[str, list[Candidate]] = {}
    for candidate in sorted(candidates, key=lambda c: c.order):
        by_url.setdefault(candidate.url, []).append(candidate)
    out = []
    for same in by_url.values():
        quotes = tuple(dict.fromkeys(q for c in same for q in c.quotes))
        out.append(dataclasses.replace(same[0], quotes=quotes))
    return sorted(out, key=lambda c: c.order)


# --- Reading them ---

def check_ahead(candidates: list[Candidate], checker, limit: int = PRECHECK_MAX_READS, dry_run: bool = False,
                stop_after_unknown: int = PRECHECK_STOP_AFTER_UNKNOWN,
                fresh: timedelta = timedelta(hours=PRECHECK_FRESH_HOURS), midway=None,
                started: datetime | None = None, minutes: float | None = None) -> Reading:
    """Reads the candidates on Reddit in order through `checker` (engine.live_check.LiveChecker), skipping those read
    within `fresh`, until `limit` reads are made or, with `minutes`, until that long after `started` (the checker's
    clock; by default now), when no more reads start. `dry_run`: nothing is read; counts what would be. `midway`:
    called once when half the reads are made or half the time is spent, whichever comes first (the run saves its checks
    then too, so a run cut short still leaves them)."""
    run = Reading()
    began = time.perf_counter()
    now = getattr(checker, "now", None) or (lambda: datetime.now(UTC))
    started = started or now()
    until = halfway = None
    if minutes is not None:
        until, halfway = started + timedelta(minutes=minutes), started + timedelta(minutes=minutes / 2)
    unknown_in_a_row = 0
    for candidate in candidates:
        if not run.stopped and run.out_of_time is None and until is not None and not dry_run and now() >= until:
            run.out_of_time = minutes
        if run.stopped or run.out_of_time is not None or run.read + run.would_read >= limit:
            run.not_reached += 1
            continue
        entry = checker.saved_entry(candidate.url)
        if entry is not None and entry.get("via") == "bright_data":  # its embed page shows no comment: never read there
            run.via_bright_data += 1
            continue
        if checker.checked_at(candidate.url, max_age=fresh) is not None:
            run.fresh += 1
            continue
        if dry_run:
            run.would_read += 1
            continue
        status = _read(candidate, checker, fresh)
        run.read += 1
        setattr(run, status, getattr(run, status) + 1)
        unknown_in_a_row = unknown_in_a_row + 1 if status == "unknown" else 0
        if unknown_in_a_row >= stop_after_unknown:
            run.stopped = True
        if midway is not None and (run.read == max(limit // 2, 1) or halfway is not None and now() >= halfway):
            midway()
            midway = None
        if run.read % PROGRESS_EVERY == 0:
            print(f"  read {run.read:,} of up to {limit:,} ({(time.perf_counter() - began) / 60:.1f} min)",
                  file=sys.stderr, flush=True)
    run.seconds = time.perf_counter() - began
    return run


def _read(candidate: Candidate, checker, fresh: timedelta) -> str:
    """One comment read on Reddit (once: its other quotes are checked against what was read), as one word: "passing"
    when every quote is still found, else "gone", "changed" or "unknown"."""
    for quote in candidate.quotes:
        outcome = checker.check(candidate.url, quote, max_age=fresh)
        if not outcome.show:
            return outcome.status
    return "passing"


# --- Comments the embed page can't show, through Bright Data ---

@dataclass
class BrightDataReading:
    """What a run verified through Bright Data, in counts."""

    needed: int = 0  # comments whose embed page shows no comment (or whose Bright Data check is due again)
    threads: int = 0  # the threads they are in
    read: int = 0  # threads read through Bright Data now (a dry run: would be)
    records: int = 0  # records Bright Data delivered (a dry run: the estimate)
    passing: int = 0
    gone: int = 0
    changed: int = 0
    absent: int = 0  # not in Bright Data's answer: still unverified, never shown
    not_reached: int = 0  # threads left for this run's budget (or whose size isn't known)
    failed: int = 0  # threads Bright Data couldn't read
    problem: str | None = None  # an account problem (no key, no records left) that stopped the reads
    dry_run: bool = False
    off: bool = False  # the step is off (deployed without the key): nothing read through Bright Data
    failures: list = field(default_factory=list)  # a Failure for each thread that couldn't be read now
    skipped: int = 0  # threads left: Bright Data couldn't read them in the last PRECHECK_BRIGHT_DATA_SKIP_DAYS
    skipped_gone: int = 0  # threads left: Bright Data found their post gone (BrightDataMemory)
    batch_problem: str | None = None  # why the batch couldn't be read (its status and error), when it couldn't


@dataclass(frozen=True)
class Failure:
    """Why one thread couldn't be read through Bright Data, in its words: never a comment's."""

    post_id: str
    status: str | None  # what Bright Data said of the job or answer ("ready", "failed", "running", "HTTP 500")
    error: str | None  # its error, short ("dead_page: Page not reachable")
    gone: bool  # the post itself is gone: its comments can't be verified that way
    comments: int  # the comments it was asked for


# --- What the Bright Data step remembers between runs (14 Oct 2026) ---

BRIGHT_DATA_MEMORY_NAME = "bright_data.json"  # in the bucket under live_check/, beside the plan; on a computer, .cache/


@dataclass(frozen=True)
class Trouble:
    """A thread Bright Data couldn't read: when, its status and error, whether the post is gone, and then the comments
    that needed it (unverifiable while the entry lasts)."""

    at: datetime
    gone: bool
    status: str | None
    error: str | None
    comments: tuple[str, ...] = ()


class BrightDataMemory:
    """The threads Bright Data couldn't read lately (see config.PRECHECK_BRIGHT_DATA_SKIP_DAYS): kept by the daily job
    in the bucket beside the plan, since each of its runs starts with an empty disk; ids, dates and Bright Data's own
    words only, a few dozen entries, each gone once its days are over."""

    def __init__(self, entries: dict[str, Trouble] | None = None):
        self.entries: dict[str, Trouble] = dict(entries or {})
        self.held = bool(self.entries)  # it held entries when it was read: written again even if they all went

    def lasts(self, trouble: Trouble) -> timedelta:
        return timedelta(days=PRECHECK_BRIGHT_DATA_GONE_DAYS if trouble.gone else PRECHECK_BRIGHT_DATA_SKIP_DAYS)

    def skipping(self, post_id: str, now: datetime) -> Trouble | None:
        """The thread's trouble while it lasts: then it isn't asked for."""
        trouble = self.entries.get(post_id)
        return trouble if trouble is not None and now - trouble.at < self.lasts(trouble) else None

    def unverifiable(self, now: datetime) -> frozenset[str]:
        """The comments of posts found gone, while their entries last."""
        return frozenset(cid for post_id, trouble in self.entries.items() if trouble.gone
                         and self.skipping(post_id, now) for cid in trouble.comments)

    def record(self, post_id: str, now: datetime, error, comments=()) -> None:
        """A thread Bright Data couldn't read now (`error`: an engine.bright_data.BrightDataError)."""
        self.entries[post_id] = Trouble(now, bool(getattr(error, "post_gone", False)), _brief(getattr(error, "status", None)),
                                        _brief(getattr(error, "error", None)), tuple(dict.fromkeys(comments)))

    def add_comments(self, post_id: str, comments) -> None:
        """More comments of a post already found gone, as unverifiable as the others."""
        trouble = self.entries[post_id]
        self.entries[post_id] = dataclasses.replace(trouble, comments=tuple(dict.fromkeys((*trouble.comments, *comments))))

    def prune(self, now: datetime) -> None:
        self.entries = {post_id: t for post_id, t in self.entries.items() if self.skipping(post_id, now)}

    def dumps(self, now: datetime) -> bytes:
        threads = {post_id: {"at": t.at.isoformat(), "gone": t.gone, "status": t.status, "error": t.error,
                             **({"comments": list(t.comments)} if t.comments else {})}
                   for post_id, t in sorted(self.entries.items())}
        return json.dumps({"written_at": now.isoformat(), "threads": threads}, ensure_ascii=False).encode("utf-8")

    @classmethod
    def loads(cls, data) -> "BrightDataMemory":
        """As dumps wrote it; one that can't be read is empty, and an entry that can't be read is left out."""
        try:
            threads = json.loads(data)["threads"]
        except (TypeError, ValueError, KeyError):
            return cls()
        entries = {}
        for post_id, raw in threads.items() if isinstance(threads, dict) else ():
            try:
                comments = tuple(c for c in raw.get("comments", ()) if isinstance(c, str) and _ID.match(c))
                if _ID.match(post_id):
                    entries[post_id] = Trouble(datetime.fromisoformat(raw["at"]), bool(raw.get("gone")),
                                               _brief(raw.get("status")), _brief(raw.get("error")), comments)
            except (TypeError, ValueError, KeyError, AttributeError):
                continue
        return cls(entries)


_ID = re.compile(r"^[A-Za-z0-9_-]{1,20}$")  # a post's or a comment's id, as the memory keeps them


def _brief(text) -> str | None:
    """Bright Data's words, on one line and short (100 characters), as the memory keeps them."""
    if text is None:
        return None
    flat = " ".join(str(text).split())
    return flat[:100]


def load_bright_data_memory(checker) -> BrightDataMemory:
    """The memory from the bucket (the daily job), else from beside this machine's checks (.cache/)."""
    bucket = getattr(checker, "bucket", None)
    if bucket is not None:
        return BrightDataMemory.loads(bucket.get(BRIGHT_DATA_MEMORY_NAME))
    try:
        return BrightDataMemory.loads((Path(checker.cache_dir).parent / BRIGHT_DATA_MEMORY_NAME).read_bytes())
    except OSError:
        return BrightDataMemory()


def save_bright_data_memory(checker, memory: BrightDataMemory, now: datetime) -> None:
    """The memory written back, its entries over their days left out: to the bucket every run that has any (so the
    bucket's 2-day rule never removes it while the job runs), else beside this machine's checks."""
    memory.prune(now)
    if not memory.entries and not memory.held:
        return
    bucket = getattr(checker, "bucket", None)
    if bucket is not None:
        bucket.put(BRIGHT_DATA_MEMORY_NAME, memory.dumps(now))
    else:
        local = Path(checker.cache_dir).parent / BRIGHT_DATA_MEMORY_NAME
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(memory.dumps(now))


def needing_bright_data(candidates: list[Candidate], checker,
                        fresh: timedelta = timedelta(hours=PRECHECK_BRIGHT_DATA_FRESH_HOURS)) -> list[Candidate]:
    """The candidates whose latest read of the last 48 hours (engine.live_check.LiveChecker.last_read: the site's
    reads ahead are up to a day old when the daily job runs) found no comment on the embed page, or that were verified
    through Bright Data more than `fresh` ago, likeliest to be shown first."""
    needed = []
    now = checker.now()
    for candidate in candidates:
        last = checker.last_read(candidate.url)
        if last is None:
            continue
        at, text, via = last
        if text is None and via is None or via == "bright_data" and now - at >= fresh:
            needed.append(candidate)
    return needed


def verify_through_bright_data(candidates: list[Candidate], checker, client_factory, library_dir: Path,
                               max_records: int = PRECHECK_BRIGHT_DATA_RECORDS,
                               max_threads: int = PRECHECK_BRIGHT_DATA_MAX_THREADS,
                               dry_run: bool = False, until: datetime | None = None,
                               memory: BrightDataMemory | None = None, remember=None) -> BrightDataReading:
    """Reads the threads of the comments needing_bright_data, the most useful first (_value_order), through Bright Data
    (`client_factory()`, an engine.bright_data.BrightDataClient, built only when there is something to read), within
    `max_records` (each thread's cost estimated from the library's copy: its post and its top-level comments) and
    `max_threads` a run, in one batch; and saves a check for each comment its answer holds (checker.keep_check).
    With no `client_factory` (None: the step is off, bright_data_from_env) it only counts the comments waiting. With
    `until` (the checker's clock), nothing is asked of Bright Data after it: the plan run's minutes. With `memory`
    (BrightDataMemory), a thread Bright Data couldn't read lately is left, so the records go to the next ones, and one
    that can't be read now is remembered with Bright Data's status and error (`remember()` is called after each, so a
    run cut short keeps them)."""
    reading = BrightDataReading(dry_run=dry_run, off=client_factory is None)
    needed = needing_bright_data(candidates, checker)
    by_thread: dict[str, list[Candidate]] = {}
    for candidate in needed:
        by_thread.setdefault(parse_thread_url(candidate.url)[1], []).append(candidate)
    reading.needed, reading.threads = len(needed), len(by_thread)
    if reading.off:
        return reading
    costs = {post_id: _records_estimate(Path(library_dir), post_id) for post_id in by_thread}
    now = checker.now()
    chosen, spent = [], 0
    for post_id in sorted(by_thread, key=lambda t: _value_order(by_thread[t], costs[t])):
        comments, cost = by_thread[post_id], costs[post_id]
        trouble = memory.skipping(post_id, now) if memory is not None else None
        if trouble is not None:  # failed lately, or its post is gone: the records go to the next threads
            if trouble.gone:
                reading.skipped_gone += 1
                memory.add_comments(post_id, [c.comment_id for c in comments])
            else:
                reading.skipped += 1
            continue
        if cost is None or len(chosen) >= min(max_threads, BRIGHT_DATA_BATCH_THREADS) or spent + cost > max_records:
            reading.not_reached += 1
            continue
        chosen.append((post_id, comments, cost))
        spent += cost
    if dry_run or not chosen:
        reading.read, reading.records = (len(chosen), spent) if dry_run else (0, 0)
        return reading
    if until is not None and checker.now() >= until:
        reading.not_reached += len(chosen)
        return reading
    from engine.bright_data import BrightDataError

    client = client_factory()
    if client is None:
        reading.problem = "no Bright Data client"
        return reading
    before = client.records_used_this_month()
    try:
        client.prefetch([(comments[0].url, max(cost - 1, 1)) for _, comments, cost in chosen])
    except BrightDataError as error:
        if error.account_problem:
            reading.problem = str(error)
            return reading
        # Not the account: each thread is asked on its own below.
        reading.batch_problem = f"{error.status or 'no answer'}: {error.error or 'no reason given'}"
    for number, (post_id, comments, _) in enumerate(chosen):
        if until is not None and checker.now() >= until:
            reading.not_reached += len(chosen) - number
            break
        try:
            thread = client.get_thread(comments[0].url)
        except BrightDataError as error:
            if error.account_problem:
                reading.problem = str(error)
                break
            reading.failed += 1
            reading.failures.append(Failure(post_id, error.status, error.error, error.post_gone, len(comments)))
            if memory is not None:
                memory.record(post_id, now, error, [c.comment_id for c in comments])
                if remember is not None:
                    remember()
            continue
        reading.read += 1
        found = {comment.id: comment for comment in thread.comments}
        for candidate in comments:
            comment = found.get(candidate.comment_id)
            if comment is None:
                reading.absent += 1  # Bright Data returns top-level comments and direct replies only: not deleted
                continue
            checker.keep_check(candidate.url, comment.body, thread.collected_at, "bright_data")
            outcomes = [checker.saved_check(candidate.url, quote) for quote in candidate.quotes]
            status = next((o.status for o in outcomes if not o.show), "passing")  # "gone" or "changed" when not
            setattr(reading, status, getattr(reading, status) + 1)
    reading.records = client.records_used_this_month() - before
    return reading


def _value_order(comments: list[Candidate], cost: int | None) -> tuple:
    """Which threads are read first: those whose comments are likeliest to be shown (the best tier, a pick's own quotes
    first), then those that verify the most comments for their records, then by their likeliest comment."""
    return (min(c.tier for c in comments), min(c.section for c in comments),
            (cost if cost is not None else float("inf")) / len(comments), min(c.order for c in comments))


def _records_estimate(library_dir: Path, post_id: str) -> int | None:
    """What reading a thread through Bright Data should cost, from the library's copy of it: a record for its post and
    one for each top-level comment; None when the library doesn't hold it."""
    try:
        thread = json.loads((library_dir / "threads" / f"{post_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return 1 + sum(1 for comment in thread.get("comments", []) if not comment.get("parent_id"))


def bright_data_report(reading: BrightDataReading) -> str:
    """The Bright Data reads in a line or two: counts only."""
    head = (f"{_n(reading.needed, 'comment')} the embed page can't show, in {_n(reading.threads, 'thread')}")
    if reading.off:
        return (f"Bright Data: off (deployed without its key, the secret bright-data-key: deploy/cloudrun/DEPLOY.md); "
                f"{head}, not verified that way.")
    if reading.dry_run:
        return (f"Bright Data (dry run): {head}; would read {_n(reading.read, 'thread')}, about "
                f"{_n(reading.records, 'record')} (at most {PRECHECK_BRIGHT_DATA_RECORDS} a run); "
                f"{reading.not_reached} left for this run's budget.")
    line = (f"Bright Data: {head}; {_n(reading.read, 'thread')} read ({_n(reading.records, 'record')}): "
            f"{reading.passing} passing, {reading.gone} gone, {reading.changed} changed, {reading.absent} not in its "
            f"answer (still unverified); {reading.not_reached} left for this run's budget"
            + (f"; {reading.failed} couldn't be read" if reading.failed else "") + ".")
    if reading.batch_problem:
        line += f"\nThe batch couldn't be read ({reading.batch_problem}): each thread was asked on its own."
    if reading.failures:
        whys = []
        for failure in reading.failures:
            why = f"{failure.status or 'no answer'}: {failure.error or 'no reason given'}"
            then = (f"its post is gone: its {_n(failure.comments, 'comment')} can't be verified that way, not asked "
                    f"again for {PRECHECK_BRIGHT_DATA_GONE_DAYS} days" if failure.gone else
                    f"asked again in {PRECHECK_BRIGHT_DATA_SKIP_DAYS} days")
            whys.append(f"{failure.post_id} ({why}; {then})")
        line += "\nCouldn't be read: " + "; ".join(whys) + "."
    if reading.skipped or reading.skipped_gone:
        line += (f"\nLeft for now: {_n(reading.skipped, 'thread')} Bright Data couldn't read in the last "
                 f"{PRECHECK_BRIGHT_DATA_SKIP_DAYS} days, {_n(reading.skipped_gone, 'thread')} whose post is gone.")
    if reading.problem:
        line += f"\nBright Data stopped: {reading.problem}"
    return line


def _n(count: int, word: str) -> str:
    return f"{count:,} {word}{'' if count == 1 else 's'}"


def _bright_data_client():
    """The real Bright Data client (key BRIGHT_DATA_API_KEY, from the environment or .env), built the way the library
    builds it, so the tests' guard against real clients (engine/tests/conftest.py) covers it too."""
    from engine import library

    return library.BrightDataClient()


def bright_data_from_env(environ=os.environ):
    """What builds the run's Bright Data client: None (the step is off) when CREDIBLE_RECS_PRECHECK_BRIGHT_DATA is "off",
    as deploy.sh deploys the job when the key's secret isn't there (14 Oct 2026: a missing key never stops a deploy)."""
    return None if environ.get("CREDIBLE_RECS_PRECHECK_BRIGHT_DATA", "").strip().lower() == "off" else _bright_data_client


# --- Keeping a slimmed library verified (13 Oct 2026) ---

@dataclass
class VerifyReading:
    """What a run did for the comments slimmed threads keep, in counts (never their words)."""

    kept: int = 0  # comments the library's slimmed threads keep
    recorded: int = 0  # whose check of the last 48 hours (made today, or in the bundle) was recorded without a read
    due: int = 0  # not verified within LIBRARY_VERIFY_AGAIN_DAYS, so to read
    read: int = 0  # read on Reddit now
    passing: int = 0
    deleted: int = 0
    removed: int = 0
    changed: int = 0
    unreadable: int = 0  # the page showed no comment: tried again after LIBRARY_VERIFY_RETRY_DAYS
    unknown: int = 0  # couldn't be read now (an error, Reddit refusing): left for the next run
    gone_already: int = 0  # found deleted or edited before: not read again, the next deploy drops them
    waiting_retry: int = 0  # unreadable less than LIBRARY_VERIFY_RETRY_DAYS ago
    not_reached: int = 0  # due, but left for lack of reads in this run's budget
    would_read: int = 0  # a dry run: what would have been read
    stopped: bool = False  # Reddit stopped answering
    out_of_time: bool = False  # the run's minutes ran out first (no read starts after them)
    dry_run: bool = False
    never_verified: int = 0  # after the run: kept comments no read has passed yet
    oldest_days: int | None = None  # after the run: days since the oldest kept comment was verified (or read)
    expiring: int = 0  # after the run: would go past LIBRARY_VERIFY_DAYS within a week unless read meanwhile


def verify_kept(library_dir: Path, checker, ledger: Ledger, limit: int = LIBRARY_VERIFY_READS,
                now: datetime | None = None, dry_run: bool = False, kept: list[KeptComment] | None = None,
                again: timedelta = timedelta(days=LIBRARY_VERIFY_AGAIN_DAYS),
                retry: timedelta = timedelta(days=LIBRARY_VERIFY_RETRY_DAYS),
                stop_after_unknown: int = PRECHECK_STOP_AFTER_UNKNOWN, until: datetime | None = None) -> VerifyReading:
    """Verifies the kept comments of the library's slimmed threads (see the module's docstring), recording every read
    in `ledger` (engine.verify.Ledger). `checker`: engine.live_check.LiveChecker. The library isn't changed. With
    `until` (the checker's clock), no read starts after it: the run's minutes (PRECHECK_MAX_RUN_MINUTES)."""
    clock = getattr(checker, "now", None) or (lambda: datetime.now(UTC))
    now = now or datetime.now(UTC)
    kept = kept_comments(library_dir) if kept is None else kept
    reading = VerifyReading(kept=len(kept), dry_run=dry_run)
    reading.recorded = record_saved_checks(library_dir, checker, ledger, kept)  # what today's checks say: no read
    due = due_for_verification(kept, ledger, now, again=again, retry=retry)
    reading.due, reading.gone_already, reading.waiting_retry = due.due, due.gone_already, due.waiting_retry
    unknown_in_a_row = 0
    for comment in due.chosen:
        if not dry_run and until is not None and not reading.out_of_time and clock() >= until:
            reading.out_of_time = True
        if reading.stopped or reading.out_of_time or reading.read + reading.would_read >= limit:
            reading.not_reached += 1
            continue
        if dry_run:
            reading.would_read += 1
            continue
        got = checker.read_text(comment.url)
        reading.read += 1
        if got is None:
            reading.unknown += 1
            unknown_in_a_row += 1
        else:
            status = outcome(got[1], comment.quotes)
            ledger.record(comment.comment_id, got[0], status)
            setattr(reading, status, getattr(reading, status) + 1)
            unknown_in_a_row = unknown_in_a_row + 1 if status == "unreadable" else 0
        if unknown_in_a_row >= stop_after_unknown:
            reading.stopped = True
    _after_the_run(kept, ledger, now, reading)
    return reading


@dataclass
class Due:
    """The kept comments due to be verified, longest unverified first (chosen: within the limit), and those not."""

    chosen: list[KeptComment] = field(default_factory=list)
    due: int = 0  # due, chosen or not
    not_reached: int = 0  # due, beyond the limit
    gone_already: int = 0  # found deleted or edited before: not read again, the next deploy drops them
    waiting_retry: int = 0  # unreadable less than LIBRARY_VERIFY_RETRY_DAYS ago


def due_for_verification(kept: list[KeptComment], ledger: Ledger, now: datetime, limit: int | None = None,
                         exclude=frozenset(), again: timedelta = timedelta(days=LIBRARY_VERIFY_AGAIN_DAYS),
                         retry: timedelta = timedelta(days=LIBRARY_VERIFY_RETRY_DAYS)) -> Due:
    """The kept comments not verified within `again` (a comment never verified counts from the day its thread was
    read), longest unverified first, then by thread and place in it; at most `limit` chosen. Left out: those in
    `exclude` (comment ids: the answers' own comments, read anyway), those found deleted or edited since their last
    pass, and those whose page showed no comment less than `retry` ago."""
    result, due = Due(), []
    for comment in kept:
        if comment.comment_id in exclude:
            continue
        entry, last = ledger.get(comment.comment_id), _last_verified(comment, ledger)
        if entry is not None and entry.outcome in FAILED and (last is None or entry.at > last):
            result.gone_already += 1
        elif entry is not None and entry.outcome == "unreadable" and (last is None or entry.at > last) and (
                now - entry.at < retry):
            result.waiting_retry += 1
        elif last is None or now - last >= again:
            due.append(((last or comment.collected_at), comment.thread_id, comment.order, comment))
    due.sort(key=lambda item: item[:3])
    ordered = [item[3] for item in due]
    result.due, result.chosen = len(ordered), ordered if limit is None else ordered[:limit]
    result.not_reached = result.due - len(result.chosen)
    return result


def _last_verified(comment: KeptComment, ledger: Ledger) -> datetime | None:
    """A kept comment's last passing read: its thread file's, or the record's when newer."""
    entry = ledger.get(comment.comment_id)
    found = [d for d in (comment.verified_at, entry.passed if entry is not None else None) if d is not None]
    return max(found) if found else None


def _after_the_run(kept: list[KeptComment], ledger: Ledger, now: datetime, reading: VerifyReading) -> None:
    """How verified the kept comments are once the run is over: never verified, the oldest, and those about to go."""
    ages = []
    for comment in kept:
        last = _last_verified(comment, ledger)
        reading.never_verified += last is None
        days = (now.date() - (last or comment.collected_at).date()).days
        ages.append(days)
        reading.expiring += LIBRARY_VERIFY_DAYS - 7 < days <= LIBRARY_VERIFY_DAYS
    reading.oldest_days = max(ages) if ages else None


def verify_step(library_dir: Path, checker, dry_run: bool, limit: int = LIBRARY_VERIFY_READS,
                now: datetime | None = None, until: datetime | None = None) -> VerifyReading:
    """The run's second part: the verification record read (this machine's, next to the checks, and the bucket's),
    the kept comments verified (verify_kept), and the record written back (not on a dry run). Nothing is read or
    written, the bucket not even asked, when the library has no slimmed thread."""
    now = now or datetime.now(UTC)
    kept = kept_comments(library_dir)
    if not kept:
        return VerifyReading(dry_run=dry_run)
    local = Path(checker.cache_dir).parent / LEDGER_NAME
    ledger = Ledger.load(local)
    bucket = getattr(checker, "bucket", None)
    if bucket is not None:
        ledger.merge(Ledger.loads(bucket.get(LEDGER_NAME)))
    reading = verify_kept(library_dir, checker, ledger, limit, now, dry_run, kept, until=until)
    if not dry_run:
        ledger.keep_only({comment.comment_id for comment in kept})
        ledger.save(local, now)
        if bucket is not None:
            bucket.put(LEDGER_NAME, ledger.dumps(now))
    return reading


def verify_report(reading: VerifyReading) -> str:
    """The kept comments' part of the run in a few lines: counts only."""
    if reading.dry_run:
        done = f"would read {reading.would_read:,} now"
    else:
        done = (f"read {reading.read:,} now ({reading.passing:,} passing, {reading.deleted + reading.removed:,} "
                f"deleted, {reading.changed:,} edited, {reading.unreadable:,} unreadable, {reading.unknown:,} couldn't "
                "be read now)")
    lines = [f"Kept comments of slimmed threads: {reading.kept:,} kept comments, each to be verified on Reddit within "
             f"{LIBRARY_VERIFY_DAYS} days. From today's checks: {reading.recorded:,}; due: {reading.due:,}; {done}; "
             f"left for the next runs: {reading.not_reached:,}.",
             f"Found deleted or edited before (the next deploy drops them): {reading.gone_already:,}; unreadable, "
             f"tried again after {LIBRARY_VERIFY_RETRY_DAYS} days: {reading.waiting_retry:,}. After this run: "
             f"{reading.never_verified:,} never verified, the oldest verified {reading.oldest_days} days ago, "
             f"{reading.expiring:,} due to go within a week unless read."]
    if reading.stopped:
        lines.append(f"Stopped early: {PRECHECK_STOP_AFTER_UNKNOWN} pages in a row couldn't be read.")
    if reading.out_of_time:
        lines.append("Stopped at the run's minutes: the rest wait for the next run.")
    return "\n".join(lines)


# --- The report and the command ---

def report(candidates: list[Candidate], run: Reading, requests: int, answered: int, seconds_working: float,
           seconds_reading: float, failed: int = 0) -> str:
    """The run in a few lines: counts and times only, never a comment's words."""
    by_tier = [sum(1 for c in candidates if c.tier == tier) for tier in range(len(TIERS))]
    tiers = ", ".join(f"{n:,} {words}" for n, words in zip(by_tier, TIERS))
    failures = f", {failed} failed (named above)" if failed else ""
    lines = [f"Requests: {requests} ({answered} answered{failures}). Comments their answers show or hold next in line: "
             f"{len(candidates):,} ({tiers})."]
    if run.would_read or not run.read:
        lines.append(f"Would read on Reddit: {run.would_read:,}." if run.would_read else "Read on Reddit now: none.")
    if run.read:
        lines.append(f"Read on Reddit now: {run.read:,} ({run.passing:,} passing, {run.gone:,} gone, {run.changed:,} "
                     f"changed, {run.unknown:,} unreadable).")
    via = f"; verified through Bright Data, never read on the embed page: {run.via_bright_data:,}" if (
        run.via_bright_data) else ""
    budget = "budget" if run.out_of_time is None else f"{run.out_of_time:g} minutes"
    lines.append(f"Skipped, read within {PRECHECK_FRESH_HOURS} hours: {run.fresh:,}{via}. Not reached within this "
                 f"run's {budget}: {run.not_reached:,}.")
    if run.stopped:
        lines.append(f"Stopped early: {PRECHECK_STOP_AFTER_UNKNOWN} pages in a row couldn't be read (Reddit is "
                     "refusing reads); the rest wait for the next run.")
    lines.append(f"Time: {_duration(seconds_working)} working out the answers, {_duration(seconds_reading)} reading, "
                 f"{_duration(seconds_working + seconds_reading)} in all.")
    return "\n".join(lines)


def _duration(seconds: float) -> str:
    return f"{seconds:.0f} s" if seconds < 120 else f"{seconds / 60:.1f} min"


def options(argv: list[str]) -> tuple[int, int, bool] | None:
    """(--limit N, --minutes M, --dry-run) from the command line; None when anything else is given."""
    limit, minutes, dry_run, rest = PRECHECK_MAX_READS, PRECHECK_MAX_RUN_MINUTES, False, list(argv)
    while rest:
        arg = rest.pop(0)
        if arg == "--dry-run":
            dry_run = True
        elif arg == "--limit" and rest and rest[0].isdigit():
            limit = int(rest.pop(0))
        elif arg == "--minutes" and rest and rest[0].isdigit() and int(rest[0]) > 0:
            minutes = int(rest.pop(0))
        else:
            return None
    return limit, minutes, dry_run


def run(requests: list[str], limit: int, dry_run: bool, library_dir: Path, checker, profiles,
        minutes: float | None = None, verify_limit: int = LIBRARY_VERIFY_READS,
        bright_data=_bright_data_client, bright_data_records: int = PRECHECK_BRIGHT_DATA_RECORDS,
        bright_data_threads: int = PRECHECK_BRIGHT_DATA_MAX_THREADS) -> int:
    """Works out the comments, reads them on the embed page, then those it can't show through Bright Data
    (`bright_data`: builds the client, only when there is something to read; None: that step is off), and prints the
    report. With a bucket (the daily job on Google Cloud), it starts from the bundle of checks the last run left
    (engine.live_check.LiveChecker.load_bundle), so what is still fresh isn't read again, and leaves a new one, midway
    and at the end (save_bundle): one object, a few calls a run. With `minutes`, no read starts that long after the run
    started. Then the kept comments of slimmed threads are verified, within `verify_limit` reads (verify_step), and the
    verification record written (one more object, when the library has slimmed threads)."""
    started = time.perf_counter()
    began = (getattr(checker, "now", None) or (lambda: datetime.now(UTC)))()
    bucket = getattr(checker, "bucket", None)
    loaded = checker.load_bundle() if bucket is not None else 0
    memory = load_bright_data_memory(checker)
    found = _work_out(requests, library_dir, checker, profiles, memory.unverifiable(began))
    working = time.perf_counter() - started
    print(f"Worked out {len(found.candidates):,} comments from {len(requests)} requests in {_duration(working)}; "
          f"{'counting' if dry_run else 'reading'} up to {limit:,}"
          f"{'' if minutes is None or dry_run else f' within {minutes:g} minutes of the start'}.", file=sys.stderr,
          flush=True)
    save = None if bucket is None or dry_run else checker.save_bundle
    reading = check_ahead(found.candidates, checker, limit=limit, dry_run=dry_run, midway=save, started=began,
                          minutes=minutes)
    remember = None if dry_run else lambda: save_bright_data_memory(checker, memory, checker.now())
    through = verify_through_bright_data(found.candidates, checker, bright_data, library_dir,
                                         max_records=bright_data_records, max_threads=bright_data_threads,
                                         dry_run=dry_run, memory=memory, remember=remember)
    if remember is not None and not through.off:
        remember()
    print(report(found.candidates, reading, len(requests), found.answered, working, reading.seconds, found.failed))
    print(bright_data_report(through))
    until = None if minutes is None else began + timedelta(minutes=minutes)  # the same minutes as the reads above
    verified = verify_step(library_dir, checker, dry_run, verify_limit, until=until)
    if verified.kept:
        print(verify_report(verified))
    if bucket is not None:
        saved = None if save is None else save()
        written = ("not written: a dry run" if save is None else f"{saved:,} written to it at the end" if saved
                   is not None else "the bundle couldn't be written: the site keeps yesterday's until the next run")
        print(f"Checks shared through the bucket {bucket.name}: {loaded:,} from the bucket's bundle at the start; "
              f"{written}.")
        if bucket.problems:
            print(f"The bucket failed {bucket.problems} time(s) (said above).")
    return 0


# --- The daily plan for the site (14 Oct 2026, the free-tier redesign; engine/read_ahead.py) ---

def plan_run(requests: list[str], library_dir: Path, checker, profiles, dry_run: bool = False,
             minutes: float | None = None, verify_limit: int = LIBRARY_VERIFY_READS, bright_data=_bright_data_client,
             bright_data_records: int = PRECHECK_BRIGHT_DATA_RECORDS,
             bright_data_threads: int = PRECHECK_BRIGHT_DATA_MAX_THREADS) -> int:
    """The daily job since 14 Oct 2026: it works out what the site reads ahead, and reads nothing on the embed page
    itself (see engine/read_ahead.py). With the bucket only (`checker`'s): it starts from the bundle the site shares,
    takes into the verification record what each read of the last 48 hours said about a kept comment (a page with no
    comment included), works out the comments answers would show, chooses the kept comments due (verify_limit, less the
    answers' own), and writes the record and the plan; then it verifies through Bright Data the comments the embed page
    can't show, starting nothing `minutes` after it started, and writes the plan again with those checks. A dry run
    writes nothing. 2 without a bucket."""
    bucket = getattr(checker, "bucket", None)
    if bucket is None:
        print("The plan is for the site, through the live checks' bucket: set CREDIBLE_RECS_LIVE_CACHE_BUCKET.",
              file=sys.stderr)
        return 2
    started = time.perf_counter()
    now = checker.now()
    loaded = checker.load_bundle()
    kept = kept_comments(library_dir)
    local = Path(checker.cache_dir).parent / LEDGER_NAME
    ledger = Ledger()
    if kept:
        ledger = Ledger.load(local)
        ledger.merge(Ledger.loads(bucket.get(LEDGER_NAME)))
    recorded = record_saved_checks(library_dir, checker, ledger, kept) if kept else 0
    memory = load_bright_data_memory(checker)  # what Bright Data couldn't read lately (each run's disk starts empty)
    found = _work_out(requests, library_dir, checker, profiles, memory.unverifiable(now))
    due = due_for_verification(kept, ledger, now, verify_limit, exclude={c.comment_id for c in found.candidates})
    answers, verify = [c.url for c in found.candidates], [c.url for c in due.chosen]
    written = None
    if not dry_run:
        if kept:
            ledger.keep_only({comment.comment_id for comment in kept})
            ledger.save(local, now)
            bucket.put(LEDGER_NAME, ledger.dumps(now))
        written = bucket.put(PLAN_NAME, plan_bytes(answers, verify, checker.checks_made("bright_data"), now))
    after = VerifyReading()
    _after_the_run(kept, ledger, now, after)
    print(plan_report(found, len(requests), kept, due, loaded, recorded, after, time.perf_counter() - started, dry_run,
                      written))
    until = None if minutes is None else now + timedelta(minutes=minutes)
    remember = None if dry_run else lambda: save_bright_data_memory(checker, memory, now)
    through = verify_through_bright_data(found.candidates, checker, bright_data, library_dir,
                                         max_records=bright_data_records, max_threads=bright_data_threads,
                                         dry_run=dry_run, until=until, memory=memory, remember=remember)
    if remember is not None and not through.off:
        remember()  # every run: so the bucket's 2-day rule never removes it while the job runs daily
    print(bright_data_report(through))
    if not dry_run and through.read:
        bucket.put(PLAN_NAME, plan_bytes(answers, verify, checker.checks_made("bright_data"), now))
    if bucket.problems:
        print(f"The bucket failed {bucket.problems} time(s) (said above).")
    return 0


def plan_report(found: _Found, requests: int, kept: list[KeptComment], due: Due, loaded: int, recorded: int,
                after: VerifyReading, seconds: float, dry_run: bool, written: bool | None) -> str:
    """The plan in a few lines: counts and times only, never a comment's words."""
    by_tier = [sum(1 for c in found.candidates if c.tier == tier) for tier in range(len(TIERS))]
    tiers = ", ".join(f"{n:,} {words}" for n, words in zip(by_tier, TIERS))
    failures = f", {found.failed} failed (named above)" if found.failed else ""
    head = "Plan for the site (dry run)" if dry_run else "Plan for the site"
    lines = [f"{head}: {len(found.candidates):,} answers' comments ({tiers}) from {requests} requests "
             f"({found.answered} answered{failures}), worked out in {_duration(seconds)}; then {len(due.chosen):,} kept "
             f"comments to verify, of {due.due:,} due."]
    if kept:
        lines.append(f"Kept comments of slimmed threads: {len(kept):,}, each to be verified on Reddit within "
                     f"{LIBRARY_VERIFY_DAYS} days. The site's reads of the last 48 hours: {loaded:,} taken from the "
                     f"bucket's bundle, {recorded:,} of kept comments recorded. Found deleted or edited before (the next "
                     f"deploy drops them): {due.gone_already:,}; unreadable, tried again after "
                     f"{LIBRARY_VERIFY_RETRY_DAYS} days: {due.waiting_retry:,}. Now {after.never_verified:,} never "
                     f"verified, the oldest verified {after.oldest_days} days ago, {after.expiring:,} due to go within a "
                     "week unless read.")
    if dry_run:
        lines.append("Nothing written: a dry run.")
    elif not written:
        lines.append("The plan couldn't be written: the site reads yesterday's until the next run.")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    argv, verify = _verify_option(argv)
    plan = "--plan" in argv
    argv = [arg for arg in argv if arg != "--plan"]
    parsed = options(argv) if verify is not None else None
    if parsed is None:
        print(__doc__)
        return 2
    limit, minutes, dry_run = parsed
    requests = requests_to_check()
    # The products read on demand (14 Oct 2026; engine/on_demand.py): their threads into the library folder first, then
    # their answers checked ahead like the others, after them.
    read_on_demand = on_demand.precheck_types(os.environ, DEFAULT_LIBRARY_DIR)
    requests += [t for t in dict.fromkeys(read_on_demand) if t not in requests]
    if plan:  # the daily job since 14 Oct 2026: the site reads ahead (engine/read_ahead.py)
        minutes = minutes if "--minutes" in argv else PRECHECK_PLAN_MINUTES
        return plan_run(requests, DEFAULT_LIBRARY_DIR, checker_from_env(), pipeline.cached_profiles(),
                        dry_run=dry_run, minutes=minutes, bright_data=bright_data_from_env(), **verify)
    return run(requests, limit, dry_run, DEFAULT_LIBRARY_DIR, checker_from_env(max_wait=PRECHECK_MAX_WAIT_SECONDS),
               pipeline.cached_profiles(), minutes=minutes, bright_data=bright_data_from_env(), **verify)


def _verify_option(argv: list[str]) -> tuple[list[str], dict | None]:
    """The arguments without `--verify N`, and {"verify_limit": N} for run ({} when not typed: its default,
    LIBRARY_VERIFY_READS); None when N isn't a number."""
    rest = list(argv)
    if "--verify" not in rest:
        return rest, {}
    at = rest.index("--verify")
    if at + 1 >= len(rest) or not rest[at + 1].isdigit():
        return rest, None
    verify_limit = int(rest[at + 1])
    del rest[at:at + 2]
    return rest, {"verify_limit": verify_limit}


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
