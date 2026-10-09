"""Commenter profiles, for module 5: fills in each writer's standing (how long they have been active, their karma,
how much they have written, their flair) from the Arctic Shift archive. Numbers and flair only, never anyone's text.

Why: Parse, our thread reader, gives only usernames, so module 5's standing signs (established member, well-regarded
account, low karma for its activity, expert flair, new account) had nothing to go on in saved threads.

What each writer (engine.models.Author) gets:
- account_created_at: the date of their first comment or post in the archive, whichever is earlier. The archive
  doesn't know when an account was created, so this is "active since": an account that only read Reddit for years
  counts from its first comment. If that date comes after a comment we can see them write in this thread, the
  archive is missing part of their history, and their age is left unknown rather than guessed.
- karma: their total karma (post karma + comment karma), as the archive counts it.
- contributions: their comments + posts in the archive, so module 5 can work out karma per contribution.
- flair: the flair on their comments in this thread. Flair belongs to one subreddit, so it comes from this thread.
Anything already known (typed by hand in the gold set, say) is kept. Deleted accounts are skipped. The post's own
writer is left as is: module 5 scores comments only.

The archive's account numbers are recalculated now and then, not live: one checked on 9 Oct 2026 was last updated
in 2025, so karma and counts can be months old, and accounts newer than the last update aren't found at all. A
writer the archive doesn't know is left as is: no sign for or against them.

Where the numbers live (Noemi, 9 Oct 2026): with the library, in data/library/profiles.json (ProfileStore), kept
for LIBRARY_REFRESH_DAYS like the library itself, then asked for again. They are public account numbers, not the
archived text the 48-hour deletion rule is about. Writers no longer in the library are dropped from it at each
`warm`, and a writer the archive no longer knows (a deleted account) is stored as unknown, so nothing about them is
kept. The thread files stay exactly as Parse gave them. Answers (engine.pipeline) read the store, then the 48-hour
cache, and never wait on Arctic Shift (StoredProfiles); `warm` fills both ahead of time.

When Arctic Shift is busy or down: the writers it can't answer for are left as they were and counted, and the rest
are still tried; after 3 failures in a row (PROFILE_FAILURES_IN_A_ROW_TO_STOP) it stops asking. A run never crashes.

Cost: free, but slow on purpose: 1 call per writer, plus 1 per 100 comments for flairs, 10 seconds apart.

Command line:
    python -m engine.profiles warm <threads folder> [--limit N]
        fills the cache for the writers of comments with kept product mentions or notes in that folder's checked
        extractions (engine.extract.load_checked), and, for the library's folder, keeps the answers in its store. It says how many calls and how long before it starts, then shows progress.
        --limit N looks up at most N writers not yet in the cache; the next run carries on from there.
"""

import math
import sys
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import json
from datetime import timedelta

from engine.arctic_shift import FLAIR_BATCH, MISSING, RETRY_PAUSE, ArcticShiftClient, ArcticShiftError
from engine.config import LIBRARY_REFRESH_DAYS, PROFILE_FAILURES_IN_A_ROW_TO_STOP
from engine.extract import ExtractionError, load_checked
from engine.gold import GoldSetError, load_threads
from engine.models import Author, Comment, Thread


# --- Asking Arctic Shift about writers ---

@dataclass
class LookUps:
    """What Arctic Shift said about each writer asked about."""

    found: dict[str, dict] = field(default_factory=dict)  # writer -> their numbers (ArcticShiftClient.user_stats)
    unknown: list[str] = field(default_factory=list)  # writers the archive doesn't know (deleted, suspended, renamed)
    failed: list[str] = field(default_factory=list)  # writers it couldn't answer for, and those not tried after it stopped
    problems: list[str] = field(default_factory=list)  # what Arctic Shift said when it failed
    stopped: bool = False  # True when it failed PROFILE_FAILURES_IN_A_ROW_TO_STOP times in a row


def look_up(client: ArcticShiftClient, names: Iterable[str], progress: Callable[[int, str], None] | None = None) -> LookUps:
    """Asks for each writer's numbers in turn; the cache answers when it can.

    A writer Arctic Shift can't answer for is noted and the next one is tried. After 3 failures in a row the trouble
    is Arctic Shift itself, so the writers left are noted as failed without asking. `progress`, if given, is told
    after each writer: their number in the list and what happened ("found", "not in the archive", "failed: ...").
    """
    result = LookUps()
    failures_in_a_row = 0
    for n, name in enumerate(names, 1):
        if result.stopped:
            result.failed.append(name)
            outcome = f"not tried: Arctic Shift failed {PROFILE_FAILURES_IN_A_ROW_TO_STOP} times in a row"
        else:
            try:
                stats = client.user_stats(name)
            except ArcticShiftError as e:
                result.failed.append(name)
                result.problems.append(str(e))
                failures_in_a_row += 1
                result.stopped = failures_in_a_row >= PROFILE_FAILURES_IN_A_ROW_TO_STOP
                outcome = f"failed: {e}"
            else:
                failures_in_a_row = 0
                if stats is None:
                    result.unknown.append(name)
                    outcome = "not in the archive"
                else:
                    result.found[name] = stats
                    outcome = "found"
        if progress:
            progress(n, outcome)
    return result


# --- Kept with the library ---

class ProfileStore:
    """Writers' numbers and comments' flairs, kept in one file next to the library for LIBRARY_REFRESH_DAYS.

    {"writers": {name in lowercase: {"stats": numbers or null, "checked_at": when}}, "flairs": {comment id:
    {"flair": text or null, "checked_at": when}}}. null stats means the archive didn't know the writer. An entry
    older than LIBRARY_REFRESH_DAYS counts as missing, so it is asked for again.
    """

    def __init__(self, path: Path, clock=None):
        self.path = Path(path)
        self._clock = clock or (lambda: datetime.now(UTC))
        data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}
        self.writers: dict[str, dict] = data.get("writers", {})
        self.flairs: dict[str, dict] = data.get("flairs", {})

    def user_stats(self, name: str):
        """The writer's numbers, None if the archive didn't know them, or MISSING if not stored or too old."""
        return self._fresh(self.writers.get(name.lower()), "stats")

    def flair(self, comment_id: str):
        """The comment's flair (None for none), or MISSING if not stored or too old."""
        return self._fresh(self.flairs.get(comment_id), "flair")

    def put_user(self, name: str, stats: dict | None) -> None:
        self.writers[name.lower()] = {"stats": stats, "checked_at": self._clock().isoformat()}

    def put_flair(self, comment_id: str, flair: str | None) -> None:
        self.flairs[comment_id] = {"flair": flair, "checked_at": self._clock().isoformat()}

    def keep_only(self, names: Iterable[str], comment_ids: Iterable[str]) -> None:
        """Drops every writer and comment that isn't in the library any more."""
        names, comment_ids = {n.lower() for n in names}, set(comment_ids)
        self.writers = {n: e for n, e in self.writers.items() if n in names}
        self.flairs = {c: e for c, e in self.flairs.items() if c in comment_ids}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps({"writers": self.writers, "flairs": self.flairs}, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.path)

    def _fresh(self, entry: dict | None, name: str):
        if entry is None:
            return MISSING
        if self._clock() - datetime.fromisoformat(entry["checked_at"]) > timedelta(days=LIBRARY_REFRESH_DAYS):
            return MISSING
        return entry[name]


class StoredProfiles:
    """Writers' standing for an answer: the library's store first, then the 48-hour cache; never a call."""

    def __init__(self, store: ProfileStore, client: ArcticShiftClient | None = None):
        self.store = store
        self.cached = CachedOnly(client) if client is not None else None

    def user_stats(self, author: str) -> dict | None:
        stats = self.store.user_stats(author)
        if stats is not MISSING:
            return stats
        return self.cached.user_stats(author) if self.cached else None

    def comment_flairs(self, comment_ids: Iterable[str]) -> dict[str, str | None]:
        ids = list(comment_ids)
        found = {cid: f for cid in ids if (f := self.store.flair(cid)) is not MISSING}
        rest = [cid for cid in ids if cid not in found]
        if rest and self.cached:
            found |= self.cached.comment_flairs(rest)
        return found


# --- At answer time: the cache only ---

class CachedOnly:
    """Arctic Shift's answers already in the 48-hour cache, and nothing else: it never makes a call.

    For answering a request quickly (engine.pipeline): a writer not looked up yet (see `warm`) simply gets no
    profile, as if the archive didn't know them, instead of making the person asking wait 10 seconds a writer.
    """

    def __init__(self, client: ArcticShiftClient):
        self.client = client

    def user_stats(self, author: str) -> dict | None:
        if self.client.uncached_users([author]):
            return None
        return self.client.user_stats(author)  # answered from the cache

    def comment_flairs(self, comment_ids: Iterable[str]) -> dict[str, str | None]:
        ids = list(comment_ids)
        missing = set(self.client.uncached_comments(ids))
        cached = [cid for cid in ids if cid not in missing]
        return self.client.comment_flairs(cached) if cached else {}


# --- Filling in one thread ---

@dataclass
class ProfileResult:
    thread: Thread  # a copy with the writers filled in; the thread passed in is left as it was
    filled: int = 0  # writers the archive knows, now filled in
    unknown: int = 0  # writers the archive doesn't know: left as they were
    failed: int = 0  # writers Arctic Shift couldn't answer for (busy or down): left as they were
    flairs: int = 0  # writers whose flair was found on their comments here
    problems: list[str] = field(default_factory=list)  # what Arctic Shift said when it failed
    stopped: bool = False  # it failed 3 times in a row, so the writers after that weren't asked about


def with_profiles(thread: Thread, client: ArcticShiftClient, comment_ids: Iterable[str] | None = None) -> ProfileResult:
    """A copy of `thread` whose writers have their standing filled in from Arctic Shift, ready for module 5.

    `comment_ids` picks whose writers to look up, such as the comments with kept product mentions; None means the
    writers of every comment. Every comment by a writer looked up gets their profile. Comment texts are never touched.
    """
    wanted = None if comment_ids is None else set(comment_ids)
    chosen = [c for c in thread.comments if c.author is not None and (wanted is None or c.id in wanted)]
    names = list(dict.fromkeys(c.author.name for c in chosen))
    result = ProfileResult(thread)
    try:
        flairs = _flairs_by_writer(chosen, client.comment_flairs(c.id for c in chosen))
    except ArcticShiftError as e:
        flairs = {}
        result.problems.append(f"flairs: {e}")
    lookups = look_up(client, names)
    first_seen = _first_seen(thread)
    filled = {name: _author_numbers(stats, first_seen[name]) for name, stats in lookups.found.items()}
    result.thread = _filled_thread(thread, filled, flairs)
    result.filled, result.unknown, result.failed = len(lookups.found), len(lookups.unknown), len(lookups.failed)
    result.flairs = len(flairs)
    result.problems += lookups.problems
    result.stopped = lookups.stopped
    return result


def _flairs_by_writer(chosen: list[Comment], flairs: dict[str, str | None]) -> dict[str, str]:
    """{writer: their flair}, from the latest of their comments here that shows one."""
    found = {}
    for comment in sorted(chosen, key=lambda c: c.created_at):
        if flairs.get(comment.id):
            found[comment.author.name] = flairs[comment.id]
    return found


def _first_seen(thread: Thread) -> dict[str, datetime]:
    """{writer: when they wrote their first comment in this thread}."""
    first: dict[str, datetime] = {}
    for comment in thread.comments:
        if comment.author is not None:
            name = comment.author.name
            first[name] = min(first.get(name, comment.created_at), comment.created_at)
    return first


def _author_numbers(stats: dict, first_seen: datetime) -> dict:
    """The Author fields that one writer's archive numbers fill in. `first_seen` is their first comment in the thread."""
    firsts = [t for t in (stats.get("earliest_comment_at"), stats.get("earliest_post_at")) if isinstance(t, int | float)]
    active_since = datetime.fromtimestamp(min(firsts), UTC) if firsts else None
    if active_since is not None and active_since > first_seen:
        active_since = None  # the archive is missing part of their history, so it can't date them
    counts = [n for n in (stats.get("num_comments"), stats.get("num_posts")) if isinstance(n, int)]
    karma = stats.get("total_karma")
    return {
        "account_created_at": active_since,
        "karma": karma if isinstance(karma, int) else None,
        "contributions": sum(counts) if counts else None,
    }


def _filled_thread(thread: Thread, numbers: dict[str, dict], flairs: dict[str, str]) -> Thread:
    """A copy of the thread with each writer's numbers and flair filled into every one of their comments."""
    comments = []
    for comment in thread.comments:
        author = comment.author
        if author is not None and (author.name in numbers or author.name in flairs):
            found = numbers.get(author.name, {}) | {"flair": flairs.get(author.name)}
            comment = comment.model_copy(update={"author": _filled_author(author, found)})
        comments.append(comment)
    return thread.model_copy(update={"comments": comments})


def _filled_author(author: Author, found: dict) -> Author:
    """The writer with each empty field filled from `found`; anything already known is kept."""
    update = {name: value for name, value in found.items() if getattr(author, name) is None and value is not None}
    return author.model_copy(update=update)


# --- Warming the cache for a folder ---

@dataclass
class WarmResult:
    writers: int = 0  # writers of comments with kept product mentions in the folder
    found: int = 0  # of those covered this run (cached ones included), the ones the archive knows
    unknown: int = 0  # the ones it doesn't know
    failed: int = 0  # the ones Arctic Shift couldn't answer for
    left_for_later: int = 0  # not looked up this run because of --limit
    stopped: bool = False


def writers_with_kept_mentions(threads_dir: Path) -> dict[str, list[str]]:
    """{writer: the ids of their comments with kept product mentions or notes}, across the folder's checked extractions.

    Notes count too (review, 9 Oct 2026): a "what to look for" note's writer needs a profile as much as a product's.
    Deleted accounts are left out. The folder's threads and extractions are only read, never changed.
    """
    checked = load_checked(threads_dir)
    writers: dict[str, list[str]] = {}
    for thread in load_threads(threads_dir):
        result = checked.get(thread.id)
        kept = {m.comment_id for m in result.kept} | {n.comment_id for n in result.kept_notes} if result else set()
        for comment in thread.comments:
            if comment.id in kept and comment.author is not None:
                writers.setdefault(comment.author.name, []).append(comment.id)
    return writers


def warm(threads_dir: Path, client: ArcticShiftClient, limit: int | None = None, say: Callable[[str], None] = print,
         store: ProfileStore | None = None) -> WarmResult:
    """Fills the 48-hour cache for the writers of comments with kept product mentions or notes in `threads_dir`.

    Says what it will cost before starting and shows progress after each writer looked up. With `limit`, at most
    that many writers not yet in the cache are looked up; the others are left for a later run. With `store` (the
    library's), writers and flairs already stored aren't asked again, the answers are kept in it, and writers no
    longer in the folder are dropped from it.
    """
    writers = writers_with_kept_mentions(threads_dir)
    stored = [name for name in writers if store is not None and store.user_stats(name) is not MISSING]
    to_ask = client.uncached_users([name for name in writers if name not in stored])
    later = to_ask[limit:] if limit is not None else []
    asking = [name for name in to_ask if name not in later]
    cached = [name for name in writers if name not in to_ask and name not in stored]
    comment_ids = [cid for name in cached + asking for cid in writers[name] if store is None or store.flair(cid) is MISSING]
    flair_calls = math.ceil(len(client.uncached_comments(comment_ids)) / FLAIR_BATCH)
    calls = len(asking) + flair_calls

    in_store = f", {len(stored)} kept with the library" if store is not None else ""
    say(f"{_plural(len(writers), 'writer')} with kept product mentions or notes in {threads_dir}; {len(cached)} already in "
        f"the 48-hour cache{in_store}.")
    say(f"Each writer costs 1 free Arctic Shift call, and their flairs 1 call per {FLAIR_BATCH} comments; calls are "
        f"{client.min_interval:.0f} s apart.")
    say(f"This run: {_plural(len(asking), 'writer')} and {_plural(flair_calls, 'flair call')}: {_plural(calls, 'call')}, "
        f"about {_duration(calls * client.min_interval)}, plus {RETRY_PAUSE:.0f} s each time Arctic Shift says it is busy.")
    if later:
        say(f"{_plural(len(later), 'more writer')} left for a later run (--limit {limit}).")

    started, calls_before = time.monotonic(), client.calls
    flairs: dict[str, str | None] = {}
    try:
        flairs = client.comment_flairs(comment_ids) if comment_ids else {}
    except ArcticShiftError as e:
        say(f"Flairs not fetched ({e}); the writers' numbers are still looked up.")
    from_cache = look_up(client, cached)
    asked = look_up(client, asking, lambda n, outcome: say(
        f"  {n}/{len(asking)} {outcome} ({_duration(time.monotonic() - started)} so far)"))
    stored_found = sum(store.user_stats(name) is not None for name in stored) if store is not None else 0
    if store is not None:
        _keep(store, [from_cache, asked], flairs, writers)

    result = WarmResult(
        writers=len(writers),
        found=stored_found + len(from_cache.found) + len(asked.found),
        unknown=len(stored) - stored_found + len(from_cache.unknown) + len(asked.unknown),
        failed=len(from_cache.failed) + len(asked.failed),
        left_for_later=len(later),
        stopped=asked.stopped,
    )
    covered = len(stored) + len(cached) + len(asking)
    say(f"Found in the archive: {result.found} of {covered} ({result.unknown} unknown to it, {result.failed} failed).")
    if result.stopped:
        say(f"Stopped asking after {PROFILE_FAILURES_IN_A_ROW_TO_STOP} failures in a row: Arctic Shift may be busy or down. Run warm again later.")
    kept = f"Kept with the library for {LIBRARY_REFRESH_DAYS} days." if store is not None else "The answers stay in the cache for 48 hours."
    say(f"Done: {_plural(client.calls - calls_before, 'Arctic Shift call')} in {_duration(time.monotonic() - started)}. {kept}")
    return result


def _keep(store: ProfileStore, lookups: list[LookUps], flairs: dict[str, str | None], writers: dict[str, list[str]]) -> None:
    """Keeps this run's answers in the library's store, and drops writers and comments no longer in the library."""
    for found in lookups:
        for name, stats in found.found.items():
            store.put_user(name, stats)
        for name in found.unknown:
            store.put_user(name, None)
    for comment_id, flair in flairs.items():
        store.put_flair(comment_id, flair)
    store.keep_only(writers, [cid for ids in writers.values() for cid in ids])
    store.save()


def _plural(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _duration(seconds: float) -> str:
    """A time in words: "40 s", "12 min", "2 h 5 min"."""
    if seconds < 60:
        return f"{seconds:.0f} s"
    minutes = round(seconds / 60)
    return f"{minutes} min" if minutes < 60 else f"{minutes // 60} h {minutes % 60} min"


# --- Command line ---

def library_store(threads_dir: Path) -> ProfileStore | None:
    """The library's store when `threads_dir` is the library's threads folder; None for any other folder (the gold
    set's is committed to git, so no writer's numbers may be kept next to it)."""
    from engine.library import DEFAULT_LIBRARY_DIR

    if Path(threads_dir).resolve() == (DEFAULT_LIBRARY_DIR / "threads").resolve():
        return ProfileStore(DEFAULT_LIBRARY_DIR / "profiles.json")
    return None


def main(argv: list[str], client: ArcticShiftClient | None = None) -> int:
    """`client` can be swapped for one with a fake service, which is how the tests run the command line."""
    options = _warm_options(argv)
    if options is None:
        print(__doc__)
        return 2
    folder, limit = options
    try:
        result = warm(folder, client or ArcticShiftClient(), limit, store=library_store(folder))
    except (ExtractionError, GoldSetError) as e:
        print(e)
        return 1
    return 1 if result.failed else 0


def _warm_options(argv: list[str]) -> tuple[Path, int | None] | None:
    """The folder and --limit typed after `warm` (as `--limit 5` or `--limit=5`), or None when they don't make sense."""
    if not argv or argv[0] != "warm":
        return None
    folders, limit, words = [], None, list(argv[1:])
    while words:
        word = words.pop(0)
        name, equals, value = word.partition("=")
        if name != "--limit":
            if word.startswith("--"):
                return None  # an option this command doesn't have
            folders.append(word)
            continue
        if not equals:
            value = words.pop(0) if words else ""
        if not value.isdigit() or int(value) < 1:
            return None
        limit = int(value)
    return (Path(folders[0]), limit) if len(folders) == 1 else None


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
