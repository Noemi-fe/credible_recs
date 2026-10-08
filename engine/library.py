"""Module 2, the library: the saved Reddit threads that answers are prepared from.

There is no live AI, so answers are prepared in advance from threads saved on this machine. The library fills
itself: one command per request finds the threads and saves them, with no one picking threads by hand.

    data/library/threads/<thread id>.json   one thread each, the same shape as the gold set's thread files
    data/library/requests.jsonl             one line per `add`: when, the request, module 1's outcome, the threads saved

Three jobs:
- add: understands a request (module 1), asks a source for threads and saves them. By default the threads
  are found for free with Arctic Shift and read with Parse; Parse's own search is the backup when Arctic Shift is busy.
  Each product type gets a mix of thread kinds (Noemi, 7 Oct 2026), because each kind feeds a different later step:
  6 threads, 3 asking for advice (the picks), 1 about long-term use (the strongest evidence) and 2 warnings (the
  "skip these" list and the downsides), at most 2 from one subreddit. `--only warning` tops up one kind.
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
- Unlike the hand-checked gold set, the library is managed by these commands, so saving a thread again
  replaces the older copy.

Credits (Parse free plan: 200 a month, 2 per call):
- add costs at most 12 when Arctic Shift finds the threads (only the 6 threads are read; its searches, warning
  searches included, are free), at most 16 when it falls back to Parse's search (2 searches, then the 6 threads),
  nothing for a request module 1 can't place, and nothing for calls still in the 48-hour cache.
- add --only warning --limit 1 costs 2 (one thread read), or nothing when no warning thread is found. If Arctic
  Shift finds nothing usable at all, Parse's search is tried: 4 more, even if it finds no warning either.
- refresh costs 2 per thread due, nothing for the others. Keeping N threads costs at most 2N credits a month,
  less once they are archived (every 90 days).

Command line:
    python -m engine.library add [--only warning|advice|long_term] [--limit N] "<request>"
                                               find and save the threads for one request (6 by default, as a mix;
                                               with --only, threads of that kind only); quotes are optional
    python -m engine.library refresh           fetch again the threads that are due (30 days, archived threads 90)
    python -m engine.library coverage          saved threads per product type, and of each kind
"""

import inspect
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from engine.arctic_shift import ArcticShiftClient
from engine.config import (
    LIBRARY_ARCHIVED_REFRESH_DAYS,
    LIBRARY_MIX,
    LIBRARY_REFRESH_DAYS,
    LIBRARY_THREADS_PER_PRODUCT,
    PARSE_MONTHLY_CREDITS,
    REDDIT_ARCHIVE_DAYS,
    THREAD_CATEGORIES,
)
from engine.gold import GoldSetError, load_threads
from engine.models import Thread
from engine.parse_reddit import REPO_ROOT, ParseAPIError, ParseRedditClient
from engine.query import PRODUCT_TYPES, parse_query
from engine.sources import THREAD_KINDS, ParseSource, Source, relevance, thread_kind, without_unusable_comments

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
) -> AddResult:
    """Understands the request, saves up to `limit` threads the source finds for it, and logs the request.

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
        # The default source is built only now, so a request that can't be placed never touches Parse.
        source = source if source is not None else ParseSource(finder=ArcticShiftClient())
        result.threads = [_save(thread, folder) for thread in _find(source, query, limit, mix, only)]
    _log_request(result, folder)
    return result


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
) -> int:
    """`client`, `folder` and `finder` can be swapped for fakes, which is how the tests run the command line.

    A real run (no client given) finds threads with Arctic Shift. A test that passes its own Parse client gets
    a finder only if it passes one too, so tests never reach the network.
    """
    command = argv[0] if argv else None
    add_options = _add_options(argv[1:]) if command == "add" else None
    if command not in ("add", "refresh", "coverage") or (command == "add" and add_options is None):
        print(__doc__)
        return 2

    if client is None:
        client = ParseRedditClient()
        finder = finder or ArcticShiftClient()
    try:
        if command == "add":
            request, only, limit = add_options
            status = _print_add(add(request, ParseSource(client=client, finder=finder), folder, limit=limit, only=only))
        elif command == "refresh":
            status = _print_refresh(refresh(client, folder))
        else:
            status = _print_coverage(coverage(folder), coverage_by_kind(folder))
    except (ParseAPIError, GoldSetError) as e:
        print(e)
        status = 1
    print(f"Parse credits used this month: {client.credits_used_this_month()} of {PARSE_MONTHLY_CREDITS} (the parse.bot dashboard has the exact figure)")
    return status


def _add_options(words: list[str]) -> tuple[str, str | None, int] | None:
    """The request, --only and --limit typed after `add`, or None when they don't make sense.

    The options can come before or after the request, as `--only warning` or `--only=warning`. The request
    may be typed with or without quotes. Without --limit, 6 threads (LIBRARY_THREADS_PER_PRODUCT).
    """
    request, only, limit = [], None, LIBRARY_THREADS_PER_PRODUCT
    words = list(words)
    while words:
        word = words.pop(0)
        name, equals, value = word.partition("=")
        if name not in ("--only", "--limit"):
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
        else:
            return None
    text = " ".join(request).strip()
    return (text, only, limit) if text else None


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
