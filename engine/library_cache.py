"""The library, kept in memory between answers (latency, 12 Oct 2026).

Every answer used to read the whole library again: every thread file (twice: once to check the extractions, once for
retrieval), and every extraction, each of its ~9,500 quotes matched word for word against its comment. That took
2 to 5 seconds per answer, though the library changes only when a builder adds or refreshes threads.

Now the library is read once and kept: its threads (as module 2 reads them) and its checked extractions (as
engine.extract.load_checked checks them), with the problems of any file left out. Before each answer, a cheap
fingerprint of the folders is taken: every .json file's name, size, modification time and identity on disk. If
anything differs from the kept library's, the library is read again from scratch, so an answer never uses a stale
library: a thread added, refreshed or removed counts from the next answer on. The fingerprint costs a few
milliseconds; reading the library, seconds.

One more care, as git takes with its own file times: a disk records modification times in steps (a few milliseconds
on some systems), so a file rewritten twice within one step, at the same size, would look unchanged. A library with a
file changed less than RECENT_SECONDS before it was read is therefore read again by the next answer, until its files
have been still for that long. A file dated further ahead of the clock than that is no change happening now
(engine.memo.changed_just_now, 14 Oct 2026: the deploy's upload dates every file of the site's image an hour ahead in
British Summer Time, and the library had been read again by every answer for the hour after each deploy).

Nothing that reads the kept library may change it (answers make copies when they need to: engine.sources.
without_unusable_comments, engine.profiles.with_profiles). engine/tests/test_library_cache.py checks that an answer
leaves it as it was.
"""

import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from engine.extract import CheckResult, check_extractions, extracted_dir
from engine.gold import load_threads
from engine.memo import REQUEST_WORK, changed_just_now, register
from engine.models import Thread

# How many libraries are kept at once (the web demo uses one; the tests make many small ones).
MAX_KEPT = 4
# A library with a file changed this recently when it was read isn't kept: see the module docstring.
RECENT_SECONDS = 2.0


@dataclass(frozen=True)
class KeptLibrary:
    """One library as read: what retrieval and the answers use."""

    threads: list[Thread]  # every thread file that loaded without a problem, in file-name order
    checked: dict[str, CheckResult]  # {thread id: its extraction, checked against it}
    problems: list[str]  # the problems of the files left out, for the answer to report
    # What retrieval works out from these threads that doesn't depend on the request (engine.sources.LocalSource): kept
    # with them, and gone with them when the library is read again.
    remembered: dict = field(default_factory=dict)


_kept: OrderedDict[str, tuple[tuple, KeptLibrary]] = OrderedDict()  # folder -> (fingerprint, library), latest last
_lock = threading.Lock()


def loaded(threads_dir: Path) -> KeptLibrary:
    """The library whose threads are in `threads_dir` (extractions next to it, in extracted/): read once and kept until
    one of its files changes. Broken files are left out and named in `problems`, as answers do (engine.extract.
    load_checked with skip_broken); a missing threads folder raises engine.gold.GoldSetError."""
    threads_dir = Path(threads_dir)
    key = str(threads_dir.resolve())
    with _lock:
        started = time.time_ns()
        now = fingerprint(threads_dir)
        found = _kept.get(key)
        if found is not None and found[0] == now:
            _kept.move_to_end(key)
            return found[1]
        if found is not None:
            # Let go first, with what it worked out (15 Oct 2026, the live site's memory): read while the old one was
            # still kept, the library was in memory twice for a while (with ~1,950 threads, about 430 MB more).
            del _kept[key]
            found[1].remembered.clear()
            found = None
        library = _read(threads_dir)
        if not _changed_just_now(now, started):
            _kept[key] = (now, library)
            _kept.move_to_end(key)
            while len(_kept) > MAX_KEPT:
                _kept.popitem(last=False)
        else:
            _kept.pop(key, None)  # a file changed just now: read again next time
        return library


def forget() -> None:
    """Drops every kept library: the next answer reads its library again."""
    with _lock:
        _kept.clear()


register(forget, answers=False)  # engine.memo.forget_all empties it too; forget_answers keeps what was read

# A kept library's `remembered` keeps what answers worked out for one request's product type under REQUEST_WORK
# (engine.memo; 15 Oct 2026; engine.sources.LocalSource: each thread's relevance to a type, its talk about an ingredient,
# whether its title names another type): forget_request_work drops it, keeping what the library worked out of itself
# whatever the request (each thread's comments read, each category's readable threads, the name index, the ranges).


def forget_request_work() -> None:
    """What every kept library worked out for requests' product types, dropped (engine.memo.forget_answers)."""
    with _lock:
        for _, library in _kept.values():
            library.remembered.pop(REQUEST_WORK, None)


register(forget_request_work)  # what answers worked out: engine.memo.forget_answers empties it


def fingerprint(threads_dir: Path) -> tuple:
    """Every .json file of the threads folder and of its extracted/ folder next to it: (name, size, modification time
    in nanoseconds, identity on disk). Taken before reading, so a file changed while the library is read makes the next
    fingerprint differ, and the library is read again."""
    return tuple(_files(folder) for folder in (Path(threads_dir), extracted_dir(threads_dir)))


def _files(folder: Path) -> tuple | None:
    try:
        with os.scandir(folder) as entries:
            found = []
            for entry in entries:
                if entry.name.endswith(".json"):
                    info = entry.stat()
                    found.append((entry.name, info.st_size, info.st_mtime_ns, info.st_ino))
    except (FileNotFoundError, NotADirectoryError):
        return None
    return tuple(sorted(found))


def _changed_just_now(fingerprint: tuple, started: int) -> bool:
    """Whether any file of a fingerprint may have been changing when reading began at `started` (nanoseconds):
    engine.memo.changed_just_now, with this module's RECENT_SECONDS."""
    return any(changed_just_now(mtime, started, RECENT_SECONDS)
               for files in fingerprint if files for _, _, mtime, _ in files)


def _read(threads_dir: Path) -> KeptLibrary:
    thread_problems: list[str] = []
    threads = load_threads(threads_dir, skip_broken=True, problems=thread_problems)
    checked, problems = check_extractions(threads_dir, threads)
    return KeptLibrary(threads, checked, thread_problems + problems)
