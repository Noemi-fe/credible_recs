"""Files dated ahead of the clock (14 Oct 2026, the live site's slow getting ready).

The deploy's upload stores each file's time as the local time of the computer it runs on (in two-second steps), and the
build reads it as UTC: in British Summer Time every file in the site's image is dated an hour ahead of when it was
written. A file "changed" in the future looked changed just now, so the kept library and the price, facts and brand-lines
lists were never kept for the hour after a deploy, and every answer read the whole library again (about 10 s on Cloud
Run). A time more than RECENT_SECONDS ahead of the clock can't be a change happening now, so it no longer counts as
one; a file dated a moment ahead still does, and a file rewritten later is still read again.
"""

import os
import time

from engine import library_cache, memo
from engine.pipeline import answer_request
from engine.prices import load_prices
from engine.tests.test_library_cache import counting_reads, griddle_instead_of_skillet
from engine.tests.test_pipeline import REQUEST, library
from engine.tests.test_prices import entry, write_prices

HOUR = 3600 * 10**9


def dated(paths, ahead_ns: int):
    """Each file dated `ahead_ns` nanoseconds after now (as the deploy's upload dated the site's files)."""
    stamp = time.time_ns() + ahead_ns
    for path in paths:
        os.utime(path, ns=(stamp, stamp))


def library_files(root):
    return [*(root / "threads").glob("*.json"), *(root / "extracted").glob("*.json")]


def test_a_library_dated_an_hour_ahead_is_read_once(tmp_path, monkeypatch):
    root = library(tmp_path)
    dated(library_files(root), HOUR)
    reads = counting_reads(monkeypatch)
    first = answer_request(REQUEST, library_dir=root)
    second = answer_request(REQUEST, library_dir=root)
    assert len(reads) == 1
    assert [p.name for p in second.answer.picks] == [p.name for p in first.answer.picks]


def test_a_library_dated_ahead_still_sees_a_rewrite(tmp_path):
    root = library(tmp_path)
    dated(library_files(root), HOUR)
    kept = library_cache.loaded(root / "threads")
    griddle_instead_of_skillet(root / "extracted" / "1kett01.json")  # the same size, dated now by the disk
    again = library_cache.loaded(root / "threads")
    assert again is not kept
    assert "Lodge cast iron griddle" in [m.product for m in again.checked["1kett01"].kept]


def test_a_library_dated_a_moment_ahead_counts_as_changed_just_now(tmp_path, monkeypatch):
    # A disk or a writer's clock a little ahead (within RECENT_SECONDS) may still be writing: read again, as before.
    root = library(tmp_path)
    dated(library_files(root), int(library_cache.RECENT_SECONDS * 10**9 / 2))
    reads = counting_reads(monkeypatch)
    library_cache.loaded(root / "threads")
    library_cache.loaded(root / "threads")
    assert len(reads) == 2


def test_a_price_list_dated_an_hour_ahead_is_read_once(tmp_path):
    path = write_prices(tmp_path, [entry()])
    dated([path], HOUR)
    first = load_prices(path)
    assert load_prices(path) is first


def test_a_price_list_dated_ahead_still_sees_a_change(tmp_path):
    path = write_prices(tmp_path, [entry(price=120.0)])
    dated([path], HOUR)
    assert [p.price for p in load_prices(path)] == [120.0]
    write_prices(tmp_path, [entry(price=99.0)])
    assert [p.price for p in load_prices(path)] == [99.0]


def test_a_price_list_dated_a_moment_ahead_is_read_again(tmp_path):
    path = write_prices(tmp_path, [entry()])
    dated([path], int(memo.RECENT_SECONDS * 10**9 / 2))
    first = load_prices(path)
    assert load_prices(path) is not first
