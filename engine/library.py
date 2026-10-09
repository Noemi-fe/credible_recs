"""Module 2, the library: the saved Reddit threads that answers are prepared from.

There is no live AI, so answers are prepared in advance from threads saved on this machine. The library fills
itself: one command per request finds the threads and saves them, with no one picking threads by hand.

    data/library/threads/<thread id>.json   one thread each, the same shape as the gold set's thread files
    data/library/requests.jsonl             one line per `add`: when, the request, module 1's outcome, the threads saved

Four jobs:
- add: understands a request (module 1), asks a source for threads and saves them. By default (LIBRARY_READER,
  Noemi, 9 Oct 2026) the threads are found AND read for free in Arctic Shift's archive (engine.sources.ArchiveSource);
  `--reader parse` finds them with Arctic Shift and reads them through Parse, as before, with Parse's own search as
  the backup when Arctic Shift is busy. A copy read from the archive never replaces one already read on Reddit.
  Each product type gets a mix of thread kinds (Noemi, 7 Oct 2026), because each kind feeds a different later step:
  6 threads, 3 asking for advice (the picks), 1 about long-term use (the strongest evidence) and 2 warnings (the
  "skip these" list and the downsides), at most 2 from one subreddit. `--only warning` tops up one kind.
- check-live: reads again on Reddit, through Parse, the threads that need a live check (Noemi, 9 Oct 2026). An
  archive may still hold comments people later deleted on Reddit, so answers only quote threads checked live in the
  last 14 days (engine/pipeline.py). First the threads answers quote, if not checked in 14 days; then every other
  thread read from the archive, if never checked or not in 30 days. The live copy replaces the saved one, and the
  AI's extraction is kept: its checks then drop any mention whose comment was deleted or whose quote was edited.
  Archive text not checked live within 37 days is removed from the library (ids and titles stay, to read it again).
- refresh: fetches again every saved thread that is due, so comments deleted on Reddit since then lose their text
  in the library too (Noemi, 7 Oct 2026): 30 days after it was saved, or 90 for a thread posted more than 180 days
  ago, which Reddit has archived, so only deletions can still change it. It never deletes a whole thread on its
  own; it reports instead.
- coverage: how many saved threads each product type has, so the website can say "covered" or "not covered yet",
  and how many of each kind.

What is saved:
- Threads as fetched, but a deleted or removed comment only as a stub: its status, "[deleted]" or "[removed]"
  in place of its text, and no author. A stub holds nothing the writer took back, so keeping it respects the
  deletion rule, and replies to it still point to a comment in the same file, which the thread file checks
  (engine.gold) require. Stubs are dropped when the library is read: LocalSource leaves them out.
- Each thread says where it was read (read_from: "parse" or "arctic_shift") and when Reddit itself was last read
  for it (checked_live_at). Files saved before 9 Oct 2026 have neither: they were read through Parse.
- Unlike the hand-checked gold set, the library is managed by these commands, so saving a thread again
  replaces the older copy (except an archive copy over one read on Reddit, as above).

Credits (Parse free plan: 200 a month, 2 per call):
- add costs nothing with the archive reader (the default). With `--reader parse`: at most 12 when Arctic Shift finds
  the threads (only the 6 threads are read; its searches, warning searches included, are free), at most 16 when it
  falls back to Parse's search (2 searches, then the 6 threads), nothing for a request module 1 can't place, and
  nothing for calls still in the 48-hour cache.
- add --reader parse --only warning --limit 1 costs 2 (one thread read), or nothing when no warning thread is found.
  If Arctic Shift finds nothing usable at all, Parse's search is tried: 4 more, even if it finds no warning either.
- check-live costs 2 per thread read again, and stops at its credit cap: by default what's left this month minus a
  reserve of 20 (LIVE_CHECK_CREDIT_RESERVE), or `--max-credits N`.
- refresh costs 2 per thread due, nothing for the others. Keeping N threads costs at most 2N credits a month,
  less once they are archived (every 90 days).

Command line:
    python -m engine.library add [--reader archive|parse] [--only warning|advice|long_term] [--limit N] "<request>"
                                               find and save the threads for one request (6 by default, as a mix;
                                               with --only, threads of that kind only); quotes are optional
    python -m engine.library check-live [--max-credits N]
                                               read again on Reddit the threads that need a live check
    python -m engine.library refresh           fetch again the threads that are due (30 days, archived threads 90)
    python -m engine.library coverage          saved threads per product type, and of each kind
"""

import inspect
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from engine.arctic_shift import ArcticShiftClient, ArcticShiftError
from engine.config import (
    ARCHIVE_TEXT_KEPT_DAYS,
    ARCHIVE_TEXT_RETENTION,
    LIBRARY_ARCHIVED_REFRESH_DAYS,
    LIBRARY_MIX,
    LIBRARY_READER,
    LIBRARY_REFRESH_DAYS,
    LIBRARY_THREADS_PER_PRODUCT,
    LIVE_CHECK_ALL_DAYS,
    LIVE_CHECK_CREDIT_RESERVE,
    LIVE_CHECK_SHOWN_DAYS,
    PARSE_CREDITS_PER_CALL,
    PARSE_MONTHLY_CREDITS,
    REDDIT_ARCHIVE_DAYS,
    THREAD_CATEGORIES,
)
from engine.extract import ExtractionError
from engine.gold import GoldSetError, load_threads
from engine.models import Thread
from engine.parse_reddit import REPO_ROOT, ParseAPIError, ParseRedditClient
from engine.query import PRODUCT_TYPES, parse_query
from engine.sources import (
    THREAD_KINDS,
    ArchiveSource,
    ParseSource,
    Source,
    relevance,
    thread_kind,
    without_unusable_comments,
)

DEFAULT_LIBRARY_DIR = REPO_ROOT / "data" / "library"


# --- Filling the library ---

@dataclass
class AddResult:
    request: str  # exactly as typed
    status: str  # module 1's outcome: "ok", "clarify" or "out_of_scope"
    product_type: str | None = None
    threads: list[Thread] = field(default_factory=list)  # the copies saved, best first
    question: str | None = None  # what to ask the shopper, when status is "clarify"
    message: str | None = None  # the polite no, when status is "out_of_scope"
    only: str | None = None  # the one kind of thread asked for, if any: "warning", "advice" or "long_term"
    kept_live: list[str] = field(default_factory=list)  # found in the archive, but a copy read on Reddit was kept

    @property
    def thread_ids(self) -> list[str]:
        return [t.id for t in self.threads]


def add(
    request: str,
    source: Source | None = None,
    folder: Path = DEFAULT_LIBRARY_DIR,
    limit: int = LIBRARY_THREADS_PER_PRODUCT,
    mix: dict | None = LIBRARY_MIX,
    only: str | None = None,
    reader: str | None = None,
) -> AddResult:
    """Understands the request, saves up to `limit` threads the source finds for it, and logs the request.

    Without a `source`, the `reader` (None: LIBRARY_READER) decides how threads are read: "archive" finds and reads
    them in Arctic Shift's archive, for free (ArchiveSource); "parse" finds them there and reads them through Parse.
    A thread read from the archive never replaces a copy already read on Reddit (saved through Parse, or checked
    live): that copy is kept, and named on the result (kept_live).

    Which threads:
    - by default, a mix of kinds (LIBRARY_MIX: 3 advice, 1 long-term use, 2 warnings, at most 2 per subreddit),
      when the source can pick one, as ParseSource can. A source that can't is simply asked for the `limit` best.
    - `mix=None`: the `limit` best, whatever their kind.
    - `only="warning"` (or "advice", "long_term"): up to `limit` threads of that kind and nothing else in their
      place. If none is found, nothing is fetched or saved.
    A request module 1 can't place ("clarify" or "out_of_scope") fetches nothing and spends no credits; the
    result carries the question to ask or the polite no. Errors from the source, such as Parse credits
    running out, are passed on, and then nothing is saved or logged.
    """
    if only is not None and only not in THREAD_KINDS:
        raise ValueError(f"only must be one of {', '.join(THREAD_KINDS)}, not {only!r}")
    query = parse_query(request)
    result = AddResult(request, query.status, query.product_type, question=query.question, message=query.message, only=only)
    if query.status == "ok":
        # The default source is built only now, so a request that can't be placed never touches Parse or Arctic Shift.
        source = source if source is not None else _default_source(reader or LIBRARY_READER)
        for thread in _find(source, query, limit, mix, only):
            kept = _live_copy(thread, folder)
            if kept is not None:
                result.kept_live.append(kept.id)
            result.threads.append(kept or _save(thread, folder))
    _log_request(result, folder)
    return result


READERS = ("archive", "parse")


def _default_source(reader: str) -> Source:
    if reader not in READERS:
        raise ValueError(f"reader must be one of {', '.join(READERS)}, not {reader!r}")
    if reader == "archive":
        return ArchiveSource(ArcticShiftClient())
    return ParseSource(finder=ArcticShiftClient())


def _live_copy(thread: Thread, folder: Path) -> Thread | None:
    """The saved copy to keep instead of `thread`: one read on Reddit, when `thread` was read from the archive.

    A copy read on Reddit (through Parse, or checked live since) has already lost what people deleted; an archive copy
    may still hold it, and would wait for a live check before answers could quote it again. None: save `thread`.
    """
    if thread.read_from != "arctic_shift":
        return None
    path = Path(folder) / "threads" / f"{thread.id}.json"
    try:
        saved = Thread.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None  # nothing saved yet, or a broken file: the new copy replaces it
    return saved if saved.last_checked_live() is not None else None


def _find(source: Source, query, limit: int, mix: dict | None, only: str | None) -> list[Thread]:
    """Asks the source for the threads to save.

    As fetched when the source can give them (ParseSource can), so reply chains stay whole. As a mix of kinds
    when the source can pick one; with `only`, the mix is that one kind, with no other threads filling the gaps.
    A source that can't pick a mix is asked plainly, and with `only` the threads of other kinds are dropped.
    """
    find = source.find_raw_threads if hasattr(source, "find_raw_threads") else source.find_threads
    if only is not None:
        mix = {only: limit}
    if mix is not None and "mix" in inspect.signature(find).parameters:
        return find(query, limit=limit, mix=mix, **({"fill": False} if only is not None else {}))
    threads = find(query, limit=limit)
    return [t for t in threads if only is None or thread_kind({"title": t.title}, t.category, query.product_type) == only]


PLACEHOLDERS = {"deleted": "[deleted]", "removed": "[removed]"}  # what Reddit shows in place of the text


def _library_copy(thread: Thread) -> Thread:
    """The copy the library keeps: every comment as fetched, but a deleted or removed one as a stub with no text and no author.

    Reddit already shows those as "[deleted]" or "[removed]"; this makes sure, should a source ever hand over
    the text or author of one, that it isn't stored. Nothing else changes, not even which comment a reply answers.
    """
    return thread.model_copy(update={"comments": [
        c if c.status == "ok" else c.model_copy(update={"body": PLACEHOLDERS[c.status], "author": None})
        for c in thread.comments
    ]})


def _save(thread: Thread, folder: Path) -> Thread:
    """Writes the library's copy of the thread to threads/<id>.json, replacing any older copy, and returns that copy."""
    copy = _library_copy(thread)
    path = Path(folder) / "threads" / f"{copy.id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    # Written to a temporary file, then swapped in whole, so an interrupted run never leaves half a thread behind.
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(copy.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return copy


def _log_request(result: AddResult, folder: Path) -> None:
    line = {
        "at": datetime.now(UTC).isoformat(),
        "request": result.request,
        "status": result.status,
        "product_type": result.product_type,
        "thread_ids": result.thread_ids,
    }
    log = Path(folder) / "requests.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


# --- Keeping it honest ---

# This many failed fetches in a row means the trouble isn't one thread but Parse itself: down, the key
# refused, or the month's credits gone. Going on would only fail again.
FAILURES_IN_A_ROW_TO_STOP = 3


@dataclass
class RefreshResult:
    refreshed: list[str] = field(default_factory=list)  # threads fetched again and overwritten, oldest first
    skipped: list[str] = field(default_factory=list)  # threads not due yet: no call, no credits
    dropped_comments: int = 0  # comments usable in the old copies that are now stubs or missing
    posts_gone: list[str] = field(default_factory=list)  # posts now deleted or removed on Reddit: kept, for Noemi to decide
    failed: dict[str, str] = field(default_factory=dict)  # thread id -> what Parse said; those files are left as they were
    stopped: bool = False  # True when 3 fetches failed in a row and the refresh ended early
    not_tried: list[str] = field(default_factory=list)  # threads still due when it stopped, left as they were


def refresh(
    client: ParseRedditClient | None = None,
    folder: Path = DEFAULT_LIBRARY_DIR,
    now: datetime | None = None,
) -> RefreshResult:
    """Fetches again every saved thread that is due, so comments deleted on Reddit since then lose their text here too.

    When a thread is due: see is_due. Oldest first, so if credits run out the most overdue threads are already
    done. Threads not due are skipped and cost nothing. A thread Parse can't fetch is reported and its file left
    as it was; the refresh goes on with the next, so one bad thread never blocks the others month after month.
    Only 3 failures in a row stop it. No thread is ever deleted; one whose post is gone from Reddit is reported instead.
    """
    now = now or datetime.now(UTC)
    result = RefreshResult()
    due = []
    for thread in sorted(_saved_threads(folder), key=lambda t: (t.collected_at, t.id)):
        if is_due(thread, now):
            due.append(thread)
        else:
            result.skipped.append(thread.id)
    if due and client is None:
        client = ParseRedditClient()  # built only when there is something to fetch

    failures_in_a_row = 0
    for n, old in enumerate(due):
        try:
            new = _save(client.get_thread(old.community, old.id), folder)
        except ParseAPIError as e:
            result.failed[old.id] = str(e)
            failures_in_a_row += 1
            if failures_in_a_row == FAILURES_IN_A_ROW_TO_STOP:
                result.stopped = True
                result.not_tried = [t.id for t in due[n + 1:]]
                break
            continue
        failures_in_a_row = 0
        result.refreshed.append(old.id)
        usable_before = {c.id for c in old.comments if c.status == "ok"}
        usable_now = {c.id for c in new.comments if c.status == "ok"}
        result.dropped_comments += len(usable_before - usable_now)
        if new.body.strip() in PLACEHOLDERS.values():
            result.posts_gone.append(old.id)
    return result


def is_due(thread: Thread, now: datetime) -> bool:
    """Whether a saved thread should be fetched again.

    Normally after 30 days (LIBRARY_REFRESH_DAYS) since it was saved. A thread posted more than 180 days
    (REDDIT_ARCHIVE_DAYS) before `now` is archived: Reddit has locked it, so only deletions can still change
    it, and it waits 90 days (LIBRARY_ARCHIVED_REFRESH_DAYS). "More than" in both cases: exactly 30 days isn't due.
    """
    archived = now - thread.created_at > timedelta(days=REDDIT_ARCHIVE_DAYS)
    wait = LIBRARY_ARCHIVED_REFRESH_DAYS if archived else LIBRARY_REFRESH_DAYS
    return now - thread.collected_at > timedelta(days=wait)


# --- Live checks (Noemi, 9 Oct 2026) ---

def checked_live_within(thread: Thread, days: int, today: date) -> bool:
    """Whether Reddit itself was read for the thread at most `days` calendar days before `today`.

    Thread.last_checked_live says when: for a thread read through Parse, when it was read; for one read from the
    archive, its last live check, if any. Calendar days: read on 7 Oct, it is within 14 days up to and including 21 Oct.
    """
    last = thread.last_checked_live()
    return last is not None and (today - last.date()).days <= days


@dataclass
class LiveCheckResult:
    checked: list[str] = field(default_factory=list)  # threads read again on Reddit and replaced, in the order read
    shown_checked: list[str] = field(default_factory=list)  # of those, the ones answers quote from
    dropped_comments: int = 0  # comments readable in the old copies that the live ones no longer have readable
    posts_gone: list[str] = field(default_factory=list)  # posts now deleted or removed on Reddit: kept, for Noemi to decide
    failed: dict[str, str] = field(default_factory=dict)  # thread id -> what Parse said; those files are left as they were
    stopped: bool = False  # True when 3 reads failed in a row and the run ended early
    capped: bool = False  # True when the credit cap ended the run
    not_tried: list[str] = field(default_factory=list)  # threads still due when the run ended, left as they were
    credit_cap: int = 0  # the most this run could spend
    credits_used: int = 0  # by this run
    credits_left: int = 0  # this month, after the run
    text_removed: list[str] = field(default_factory=list)  # archive threads whose text was removed (retention)
    waiting: int = 0  # threads read from the archive and never checked live, after the run


def check_live(
    client: ParseRedditClient | None = None,
    folder: Path = DEFAULT_LIBRARY_DIR,
    shown: Iterable[str] = (),
    max_credits: int | None = None,
    now: datetime | None = None,
) -> LiveCheckResult:
    """Reads again on Reddit, through Parse, the saved threads that need a live check, then applies retention.

    Which threads, in this order (live_check_order):
    1. the threads answers quote (`shown`, thread ids; the command line works them out from the blind-test questions),
       when Reddit wasn't read for them in the last LIVE_CHECK_SHOWN_DAYS (14) days;
    2. every other thread read from the archive, never checked live or not in the last LIVE_CHECK_ALL_DAYS (30) days.
    Within each, threads never checked come first, then the oldest checks. Gold-set threads are never checked here.

    Each read costs 2 credits (nothing if Parse's 48-hour cache has it). The run stops before a read would take it past
    its credit cap: `max_credits`, never more than what's left this month; by default what's left minus a reserve of
    LIVE_CHECK_CREDIT_RESERVE (20). It also stops after 3 failures in a row (Parse down, the key refused, the credits
    gone); a single failure is reported and the run goes on. The live copy replaces the saved one, like refresh, and
    the AI's extraction file is kept: engine.extract's checks then drop any mention whose comment is gone or whose
    quote no longer matches (an edit). No thread is ever deleted; one whose post is gone from Reddit is reported.

    Retention, last (ARCHIVE_TEXT_RETENTION): a thread read from the archive whose last live check, or whose reading if
    it was never checked, is more than ARCHIVE_TEXT_KEPT_DAYS (37) days old loses its text (_without_text).
    """
    now = now or datetime.now(UTC)
    client = client if client is not None else ParseRedditClient()
    result = LiveCheckResult()
    due, shown_due = live_check_order(_saved_threads(folder), set(shown), now.date())
    used_before = client.credits_used_this_month()
    left = max(0, PARSE_MONTHLY_CREDITS - used_before)
    result.credit_cap = max(0, left - LIVE_CHECK_CREDIT_RESERVE) if max_credits is None else max(0, min(max_credits, left))

    failures_in_a_row = 0
    for n, old in enumerate(due):
        if client.credits_used_this_month() - used_before + PARSE_CREDITS_PER_CALL > result.credit_cap:
            result.capped = True
            result.not_tried = [t.id for t in due[n:]]
            break
        try:
            new = _save(client.get_thread(old.community, old.id), folder)
        except ParseAPIError as e:
            result.failed[old.id] = str(e)
            failures_in_a_row += 1
            if failures_in_a_row == FAILURES_IN_A_ROW_TO_STOP:
                result.stopped = True
                result.not_tried = [t.id for t in due[n + 1:]]
                break
            continue
        failures_in_a_row = 0
        result.checked.append(old.id)
        if old.id in shown_due:
            result.shown_checked.append(old.id)
        usable_before = {c.id for c in old.comments if c.status == "ok"}
        usable_now = {c.id for c in new.comments if c.status == "ok"}
        result.dropped_comments += len(usable_before - usable_now)
        if new.body.strip() in PLACEHOLDERS.values():
            result.posts_gone.append(old.id)

    result.credits_used = client.credits_used_this_month() - used_before
    result.credits_left = max(0, PARSE_MONTHLY_CREDITS - client.credits_used_this_month())
    for thread in _saved_threads(folder):
        if ARCHIVE_TEXT_RETENTION and _past_retention(thread, now.date()) and _has_text(thread):
            _save(_without_text(thread), folder)
            result.text_removed.append(thread.id)
        if thread.read_from == "arctic_shift" and thread.last_checked_live() is None:
            result.waiting += 1
    return result


def live_check_order(threads: list[Thread], shown: set[str], today: date) -> tuple[list[Thread], set[str]]:
    """The threads check-live reads, in order (see check_live), and the ids of those that answers quote."""
    def oldest_first(thread: Thread):
        last = thread.last_checked_live()
        return (last is not None, last or thread.collected_at, thread.id)  # never checked first

    quoted = [t for t in threads if t.id in shown and t.read_from != "gold"
              and not checked_live_within(t, LIVE_CHECK_SHOWN_DAYS, today)]
    quoted_ids = {t.id for t in quoted}
    archive = [t for t in threads if t.read_from == "arctic_shift" and t.id not in quoted_ids
               and not checked_live_within(t, LIVE_CHECK_ALL_DAYS, today)]
    return sorted(quoted, key=oldest_first) + sorted(archive, key=oldest_first), quoted_ids


def _past_retention(thread: Thread, today: date) -> bool:
    """Whether an archive thread has gone more than ARCHIVE_TEXT_KEPT_DAYS without a live check: counted from its last
    live check, or from the day it was read from the archive if it was never checked."""
    if thread.read_from != "arctic_shift":
        return False
    since = thread.last_checked_live() or thread.collected_at
    return (today - since.date()).days > ARCHIVE_TEXT_KEPT_DAYS


def _has_text(thread: Thread) -> bool:
    return bool(thread.body.strip()) or any(c.status == "ok" for c in thread.comments)


def _without_text(thread: Thread) -> Thread:
    """The thread with its post's text and every comment's text and author removed (retention).

    Each readable comment becomes a stub marked "removed" ("[removed]", no author), as the library keeps comments
    removed on Reddit: here it is the library that removed it, until a live check reads it again. Ids, the title,
    dates, scores and links stay, so the thread can be read again and its extraction file still fits it; the
    extraction's checks drop every mention, since no comment is readable.
    """
    return thread.model_copy(update={"body": "", "comments": [
        c if c.status != "ok" else c.model_copy(update={"body": PLACEHOLDERS["removed"], "author": None, "status": "removed"})
        for c in thread.comments
    ]})


# --- What the library can answer ---

def coverage(folder: Path = DEFAULT_LIBRARY_DIR) -> dict[str, int]:
    """For every product type module 1 knows, in its order: how many saved threads LocalSource would find relevant.

    A thread counts when it is in the product's category and names the product at least once (title, post
    or a comment), which is LocalSource's own bar.
    """
    return {name: len(threads) for name, threads in _relevant_threads(folder).items()}


def coverage_by_kind(folder: Path = DEFAULT_LIBRARY_DIR) -> dict[str, dict[str, int]]:
    """For every product type, in module 1's order: how many of the threads `coverage` counts are of each kind.

    {"advice": …, "long_term": …, "warning": …}, judged from the saved thread's title (engine.sources.thread_kind),
    so it shows which kinds a product still lacks against the library's mix. Threads of no kind aren't listed.
    """
    return {
        name: {kind: sum(thread_kind({"title": t.title}, t.category, name) == kind for t in threads) for kind in THREAD_KINDS}
        for name, threads in _relevant_threads(folder).items()
    }


def _relevant_threads(folder: Path) -> dict[str, list[Thread]]:
    """For every product type, in module 1's order, the saved threads LocalSource would find relevant to it."""
    threads = [without_unusable_comments(t) for t in _saved_threads(folder)]
    return {
        product.name: [t for t in threads if t.category == product.category and relevance(t, product.name) > 0]
        for product in PRODUCT_TYPES
    }


def _saved_threads(folder: Path) -> list[Thread]:
    """Every saved thread, checked the way LocalSource checks them. A library not created yet has none."""
    threads_dir = Path(folder) / "threads"
    return load_threads(threads_dir) if threads_dir.is_dir() else []


# --- Command line ---

def main(
    argv: list[str],
    client: ParseRedditClient | None = None,
    folder: Path = DEFAULT_LIBRARY_DIR,
    finder: ArcticShiftClient | None = None,
    shown: set[str] | None = None,
) -> int:
    """`client`, `folder`, `finder` and `shown` can be swapped for fakes, which is how the tests run the command line.

    A real run (no client given) finds and reads threads with Arctic Shift. A test that passes its own Parse client
    gets a finder only if it passes one too, so tests never reach the network. `shown`: the threads answers quote,
    for check-live; None works them out from the blind-test questions (engine.slice_eval.threads_behind_answers).
    """
    command = argv[0] if argv else None
    add_options = _add_options(argv[1:]) if command == "add" else None
    check_options = _check_live_options(argv[1:]) if command == "check-live" else None
    if (command not in ("add", "check-live", "refresh", "coverage") or (command == "add" and add_options is None)
            or (command == "check-live" and check_options is None)):
        print(__doc__)
        return 2

    if client is None:
        client = ParseRedditClient()
        finder = finder or ArcticShiftClient()
    try:
        if command == "add":
            request, only, limit, reader = add_options
            # A test that gives no finder has no archive: then the archive reader finds nothing, and never the network.
            source = ParseSource(client=client, finder=finder) if reader == "parse" else ArchiveSource(finder)
            status = _print_add(add(request, source, folder, limit=limit, only=only, reader=reader))
        elif command == "check-live":
            if shown is None:
                from engine.pipeline import cached_profiles  # imported here: the pipeline imports this module
                from engine.slice_eval import threads_behind_answers

                shown = threads_behind_answers(library_dir=folder, profiles=cached_profiles())
            (max_credits,) = check_options
            status = _print_check_live(check_live(client, folder, shown, max_credits=max_credits))
        elif command == "refresh":
            status = _print_refresh(refresh(client, folder))
        else:
            status = _print_coverage(coverage(folder), coverage_by_kind(folder))
    except (ParseAPIError, ArcticShiftError, GoldSetError, ExtractionError) as e:
        print(e)
        status = 1
    print(f"Parse credits used this month: {client.credits_used_this_month()} of {PARSE_MONTHLY_CREDITS} (the parse.bot dashboard has the exact figure)")
    return status


def _add_options(words: list[str]) -> tuple[str, str | None, int, str] | None:
    """The request, --only, --limit and --reader typed after `add`, or None when they don't make sense.

    The options can come before or after the request, as `--only warning` or `--only=warning`. The request
    may be typed with or without quotes. Without --limit, 6 threads (LIBRARY_THREADS_PER_PRODUCT); without
    --reader, LIBRARY_READER ("archive").
    """
    request, only, limit, reader = [], None, LIBRARY_THREADS_PER_PRODUCT, LIBRARY_READER
    words = list(words)
    while words:
        word = words.pop(0)
        name, equals, value = word.partition("=")
        if name not in ("--only", "--limit", "--reader"):
            if word.startswith("--"):
                return None  # an option this command doesn't have
            request.append(word)
            continue
        if not equals:
            if not words:
                return None
            value = words.pop(0)
        if name == "--only" and value in THREAD_KINDS:
            only = value
        elif name == "--limit" and value.isdigit() and int(value) >= 1:
            limit = int(value)
        elif name == "--reader" and value in READERS:
            reader = value
        else:
            return None
    text = " ".join(request).strip()
    return (text, only, limit, reader) if text else None


def _check_live_options(words: list[str]) -> tuple[int | None] | None:
    """(the --max-credits typed after `check-live`, or None for the default cap), or None when the words make no sense.

    Typed as `--max-credits 40` or `--max-credits=40`; 0 is allowed (no reads: only retention runs).
    """
    if not words:
        return (None,)
    name, equals, value = words[0].partition("=")
    if name != "--max-credits" or len(words) != (1 if equals else 2):
        return None
    value = value if equals else words[1]
    return (int(value),) if value.isdigit() else None


KIND_NAMES = {"advice": "advice", "long_term": "long-term use", "warning": "warning"}


def _print_add(result: AddResult) -> int:
    kind = f"{KIND_NAMES[result.only]} " if result.only else ""
    if result.status == "clarify":
        print(f"Not clear enough to search for; nothing fetched. Question for the shopper: {result.question}")
    elif result.status == "out_of_scope":
        print(f"Nothing fetched: {result.message}")
    elif not result.threads:
        print(f"No {kind}threads found for {result.product_type}; nothing saved.")
    else:
        count = len(result.threads)
        print(f"Saved {count} {kind}thread{'s' if count != 1 else ''} for {result.product_type}:")
        for t in result.threads:
            print(f"  {t.id}.json  r/{t.community}, {len(t.comments)} comments: {t.title}")
        if result.kept_live:
            print(f"Kept the copies already read on Reddit, not the archive's: {', '.join(result.kept_live)}")
        if any(t.read_from == "arctic_shift" for t in result.threads):
            print("Read from Arctic Shift's archive: answers quote them only after a live check "
                  "(python -m engine.library check-live).")
    return 0


def _print_refresh(result: RefreshResult) -> int:
    refreshed = f": {', '.join(result.refreshed)}" if result.refreshed else ""
    print(f"Refreshed {len(result.refreshed)} thread(s){refreshed}.")
    print(f"Comments dropped since the last copies: {result.dropped_comments}")
    print(
        f"Skipped {len(result.skipped)} thread(s) not due yet (due {LIBRARY_REFRESH_DAYS} days after saving, "
        f"{LIBRARY_ARCHIVED_REFRESH_DAYS} once Reddit has archived them): no credits spent."
    )
    if result.posts_gone:
        print(f"Post deleted or removed on Reddit, thread kept for you to decide: {', '.join(result.posts_gone)}")
    if not result.failed:
        print("Failures: none")
        return 0
    print("Failed, saved copies unchanged:")
    for thread_id, error in result.failed.items():
        print(f"  {thread_id}: {error}")
    if result.stopped:
        print(f"Stopped after {FAILURES_IN_A_ROW_TO_STOP} failures in a row: Parse may be down, the key refused or the credits gone.")
        if result.not_tried:
            print(f"Not tried this time, saved copies unchanged: {', '.join(result.not_tried)}. Run refresh again once fixed.")
    return 1


def _print_check_live(result: LiveCheckResult) -> int:
    checked = f": {', '.join(result.checked)}" if result.checked else ""
    print(f"Checked live on Reddit through Parse: {len(result.checked)} thread(s){checked}.")
    if result.shown_checked:
        print(f"  quoted in answers: {', '.join(result.shown_checked)}")
    print(f"Comments gone from the live copies (deleted, removed or no longer there): {result.dropped_comments}")
    print(f"Credits: {result.credits_used} used by this run (cap {result.credit_cap}); {result.credits_left} left this month.")
    if result.posts_gone:
        print(f"Post deleted or removed on Reddit, thread kept for you to decide: {', '.join(result.posts_gone)}")
    if result.not_tried:
        why = "credit cap reached" if result.capped else f"stopped after {FAILURES_IN_A_ROW_TO_STOP} failures in a row"
        print(f"Not checked this time ({why}), saved copies unchanged: {', '.join(result.not_tried)}")
    if result.failed:
        print("Failed, saved copies unchanged:")
        for thread_id, error in result.failed.items():
            print(f"  {thread_id}: {error}")
    else:
        print("Failures: none")
    if result.text_removed:
        print(f"Text removed (read from the archive, not checked live within {ARCHIVE_TEXT_KEPT_DAYS} days; ids and "
              f"titles kept): {', '.join(result.text_removed)}")
    print(f"Threads read from the archive still waiting for their first live check: {result.waiting}")
    return 1 if result.failed else 0


def _print_coverage(counts: dict[str, int], kinds: dict[str, dict[str, int]]) -> int:
    print("Saved threads per product type:")
    for category in THREAD_CATEGORIES:
        print(f"  {category}")
        for product in PRODUCT_TYPES:
            if product.category == category:
                print(f"    {product.name:<18} {counts[product.name]}")
    target = ", ".join(f"{KIND_NAMES[kind]} {LIBRARY_MIX.get(kind, 0)}" for kind in THREAD_KINDS)
    print(f"Threads of each kind, against the library's mix ({target}), for product types with saved threads:")
    covered = [product.name for product in PRODUCT_TYPES if counts[product.name]]
    for name in covered:
        line = ", ".join(f"{KIND_NAMES[kind]} {kinds[name][kind]}/{LIBRARY_MIX.get(kind, 0)}" for kind in THREAD_KINDS)
        print(f"    {name:<18} {line}")
    if not covered:
        print("    none yet")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
