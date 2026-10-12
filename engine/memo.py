"""Remembering what was worked out from a data file or a list, while it doesn't change (latency, 12 Oct 2026).

Answers read the same price list and facts list and look the same products up in them, request after request; the
lists change only when a researcher adds entries. Two small tools let each be worked out once:

- `FileMemo`: a file's contents as read (a list of entries, say), kept until the file changes. A file counts as
  changed when its size, modification time or identity on disk differs, or when it had changed less than
  RECENT_SECONDS before it was read: disks record times in steps of a few milliseconds, so a file rewritten twice in
  one step at the same size would otherwise look unchanged (git takes the same care with its own file times).
- `PerList`: answers worked out from one list, kept for as long as that very list is the one asked about. A list is
  known by its identity, not its contents, and kept with its answers, so a list made later can't be mistaken for it.
  The lists asked about are never changed once made; answers are worked out again for any other kind of collection.
- `Table`: the answers of a function that depends only on what it is given (a comment's text, say), by what it was
  given; it starts again empty past `limit` answers, so a long-running server never grows past it.

Every memory here, and the others like it (engine.library_cache, engine.match_products), registers a way to empty it:
`forget_all` empties them all, so each test starts from nothing (engine/tests/conftest.py).
"""

import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from pathlib import Path

RECENT_SECONDS = 2.0  # a file changed this recently when read is read again next time

_forgetters: list[Callable[[], None]] = []


def register(forget: Callable[[], None]) -> None:
    """Adds a way to empty one memory to what forget_all empties."""
    _forgetters.append(forget)


def forget_all() -> None:
    """Empties every memory of worked-out answers: the next answers work everything out again."""
    for forget in _forgetters:
        forget()


class Table(dict):
    """Remembered answers by key, emptied past `limit` of them (see the module docstring)."""

    def __init__(self, limit: int = 200_000):
        super().__init__()
        self.limit = limit
        register(self.clear)

    def keep(self, key, value):
        """Remembers `value` for `key` and hands it back."""
        if len(self) >= self.limit:
            self.clear()
        self[key] = value
        return value


def file_fingerprint(path: Path) -> tuple | None:
    """(size, modification time in nanoseconds, identity on disk), or None when there is no such file."""
    try:
        info = os.stat(path)
    except OSError:
        return None
    return info.st_size, info.st_mtime_ns, info.st_ino


class FileMemo:
    """What `read(path)` gave for each file, kept until the file changes (see the module docstring)."""

    def __init__(self, keep: int = 8):
        self._kept: OrderedDict[str, tuple[tuple, object]] = OrderedDict()
        self._keep = keep
        self._lock = threading.Lock()
        register(self.forget)

    def get(self, path: Path, read: Callable[[Path], object]) -> object:
        key = str(Path(path).resolve())
        started = time.time_ns()
        now = file_fingerprint(path)
        with self._lock:
            found = self._kept.get(key)
            if now is not None and found is not None and found[0] == now:
                self._kept.move_to_end(key)
                return found[1]
        value = read(path)  # raises as reading always did: a missing or broken file is never kept
        with self._lock:
            if now is not None and now[1] < started - RECENT_SECONDS * 1e9:
                self._kept[key] = (now, value)
                self._kept.move_to_end(key)
                while len(self._kept) > self._keep:
                    self._kept.popitem(last=False)
            else:
                self._kept.pop(key, None)
        return value

    def forget(self) -> None:
        with self._lock:
            self._kept.clear()


class PerList:
    """A table of answers for each list asked about (see the module docstring); at most `keep` lists at once."""

    def __init__(self, keep: int = 8):
        self._tables: OrderedDict[int, tuple[object, int, dict]] = OrderedDict()
        self._keep = keep
        self._lock = threading.Lock()
        register(self.forget)

    def forget(self) -> None:
        with self._lock:
            self._tables.clear()

    def of(self, items) -> dict | None:
        """The answers kept for `items`, a list or tuple (a new, empty table the first time); None for anything else,
        whose answers aren't kept (an iterator can be read only once)."""
        if not isinstance(items, (list, tuple)):
            return None
        with self._lock:
            found = self._tables.get(id(items))
            if found is not None and found[0] is items and found[1] == len(items):
                self._tables.move_to_end(id(items))
                return found[2]
            table: dict = {}
            self._tables[id(items)] = (items, len(items), table)
            self._tables.move_to_end(id(items))
            while len(self._tables) > self._keep:
                self._tables.popitem(last=False)
            return table
