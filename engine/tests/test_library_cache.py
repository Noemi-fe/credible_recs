"""The library kept in memory between answers (engine/library_cache.py; latency, 12 Oct 2026).

Every answer used to read and check the whole library again (every thread file, and every quote of every extraction
matched word for word): seconds per answer. Now it is read once and kept until one of its files changes. These tests
make sure a kept library is never stale: a file added, changed or removed is read again by the next answer, a broken
file is still reported, and no answer changes what is kept.
"""

import json
import os
import time
from pathlib import Path

import pytest

from engine import library_cache
from engine.extract import load_checked
from engine.gold import GoldSetError, load_threads
from engine.pipeline import answer_request
from engine.tests.test_pipeline import REQUEST, ZOJI_1, comment, kettle_thread, library


def settled(root: Path) -> Path:
    """The library as if its files were written a minute ago: a library changed just now is read again by every answer
    until its files have been still for library_cache.RECENT_SECONDS."""
    past = time.time_ns() - 60 * 10**9
    for path in [*(root / "threads").glob("*.json"), *(root / "extracted").glob("*.json")]:
        os.utime(path, ns=(past, past))
    return root


def counting_reads(monkeypatch) -> list:
    reads = []
    real = library_cache.load_threads
    monkeypatch.setattr(library_cache, "load_threads", lambda *a, **k: reads.append(1) or real(*a, **k))
    return reads


def test_an_unchanged_library_is_read_once(tmp_path, monkeypatch):
    root = settled(library(tmp_path))
    reads = counting_reads(monkeypatch)
    first = answer_request(REQUEST, library_dir=root)
    second = answer_request(REQUEST, library_dir=root)
    assert len(reads) == 1
    assert [p.name for p in second.answer.picks] == [p.name for p in first.answer.picks]


def test_a_library_changed_just_now_is_read_again(tmp_path, monkeypatch):
    root = library(tmp_path)  # its files were written a moment ago
    reads = counting_reads(monkeypatch)
    library_cache.loaded(root / "threads")
    library_cache.loaded(root / "threads")
    assert len(reads) == 2


def test_the_kept_library_is_what_the_folder_holds(tmp_path):
    root = settled(library(tmp_path))
    kept = library_cache.loaded(root / "threads")
    assert [t.id for t in kept.threads] == [t.id for t in load_threads(root / "threads")]
    assert kept.checked == load_checked(root / "threads")
    assert kept.problems == []


def without_zojirushi(path: Path) -> None:
    extraction = json.loads(path.read_text(encoding="utf-8"))
    extraction["mentions"] = [m for m in extraction["mentions"] if "Zojirushi" not in m["product"]]
    path.write_text(json.dumps(extraction), encoding="utf-8")


def test_a_changed_extraction_is_read_again(tmp_path):
    root = settled(library(tmp_path))
    assert "Zojirushi kettle" in [p.name for p in answer_request(REQUEST, library_dir=root).answer.picks]
    without_zojirushi(root / "extracted" / "1kett01.json")
    without_zojirushi(root / "extracted" / "1kett02.json")
    assert "Zojirushi kettle" not in [p.name for p in answer_request(REQUEST, library_dir=root).answer.picks]


def griddle_instead_of_skillet(path: Path) -> None:
    """Renames one product without changing the file's size: "skillet" and "griddle" have as many letters."""
    text = path.read_text(encoding="utf-8")
    extraction = json.loads(text)
    for m in extraction["mentions"]:
        if m["product"] == "Lodge cast iron skillet":
            m["product"] = "Lodge cast iron griddle"  # the name only: its quote still says what the comment says
    changed = json.dumps(extraction)
    assert len(changed) == len(text) and changed != text
    path.write_text(changed, encoding="utf-8")


def test_a_file_rewritten_at_the_same_size_is_read_again(tmp_path):
    root = settled(library(tmp_path))
    kept = library_cache.loaded(root / "threads")
    path = root / "extracted" / "1kett01.json"
    griddle_instead_of_skillet(path)
    again = library_cache.loaded(root / "threads")
    assert again is not kept
    assert "Lodge cast iron griddle" in [m.product for m in again.checked["1kett01"].kept]


def test_a_rewrite_the_disk_dates_to_the_same_moment_is_still_read(tmp_path):
    # Some disks record times in steps of milliseconds: a file read just after it was written, then rewritten at the
    # same size within the same step, keeps its size, time and identity. The library read then isn't kept.
    root = library(tmp_path)
    path = root / "extracted" / "1kett01.json"
    written = path.stat().st_mtime_ns
    library_cache.loaded(root / "threads")
    griddle_instead_of_skillet(path)
    os.utime(path, ns=(written, written))  # the same recorded time as before the rewrite
    again = library_cache.loaded(root / "threads")
    assert "Lodge cast iron griddle" in [m.product for m in again.checked["1kett01"].kept]


def test_a_new_thread_is_read(tmp_path):
    root = settled(library(tmp_path))
    before = library_cache.loaded(root / "threads")
    thread = kettle_thread("1kett03", [comment("k3aaaa", "1kett03", ZOJI_1.replace("6 years", "7 years"))])
    (root / "threads" / "1kett03.json").write_text(json.dumps(thread), encoding="utf-8")
    after = library_cache.loaded(root / "threads")
    assert "1kett03" not in [t.id for t in before.threads]
    assert "1kett03" in [t.id for t in after.threads]


def test_a_removed_extraction_is_forgotten(tmp_path):
    root = settled(library(tmp_path))
    assert "1kett02" in library_cache.loaded(root / "threads").checked
    (root / "extracted" / "1kett02.json").unlink()
    assert "1kett02" not in library_cache.loaded(root / "threads").checked


def test_a_broken_file_is_reported_by_every_answer_that_leaves_it_out(tmp_path):
    root = library(tmp_path)
    (root / "extracted" / "1kett02.json").write_text("{not json", encoding="utf-8")
    settled(root)
    first = answer_request(REQUEST, library_dir=root)
    second = answer_request(REQUEST, library_dir=root)
    assert first.skipped_files and second.skipped_files == first.skipped_files
    assert "1kett02.json" in first.skipped_files[0]


def test_an_answer_leaves_the_kept_library_as_it_was(tmp_path):
    root = settled(library(tmp_path))
    kept = library_cache.loaded(root / "threads")
    threads = [t.model_dump() for t in kept.threads]
    checked = {tid: (list(r.kept), list(r.kept_notes), list(r.kept_agreements), list(r.kept_care))
               for tid, r in kept.checked.items()}
    copies = {tid: [m.model_dump() for m in r.kept] for tid, r in kept.checked.items()}
    answer_request(REQUEST, library_dir=root)
    answer_request(REQUEST, library_dir=root)
    assert library_cache.loaded(root / "threads") is kept
    assert [t.model_dump() for t in kept.threads] == threads
    assert {tid: (list(r.kept), list(r.kept_notes), list(r.kept_agreements), list(r.kept_care))
            for tid, r in kept.checked.items()} == checked
    assert {tid: [m.model_dump() for m in r.kept] for tid, r in kept.checked.items()} == copies


def test_two_libraries_are_kept_apart(tmp_path):
    first = settled(library(tmp_path / "one"))
    second = library(tmp_path / "two")
    (second / "extracted" / "1kett01.json").unlink()
    settled(second)
    assert "1kett01" in library_cache.loaded(first / "threads").checked
    assert "1kett01" not in library_cache.loaded(second / "threads").checked
    assert "1kett01" in library_cache.loaded(first / "threads").checked


def test_a_missing_library_still_stops_the_answer(tmp_path):
    with pytest.raises(GoldSetError):
        answer_request(REQUEST, library_dir=tmp_path / "nowhere")
