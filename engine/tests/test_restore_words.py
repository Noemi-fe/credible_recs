"""Putting back words verification dropped by mistake (15 Oct 2026; engine.verify.restore_words, `python -m
engine.library restore-words`).

After the migration, of 65 kept comments verification had dropped as edited, 7 were not edited at all: the embed page's
formatting (bold, italics, a superscript) had kept their quotes from being found word for word, since fixed
(engine/tests/test_live_check_formatting.py). Their words are in the backup made before slimming, kept a week. A comment
is given its words back only when Reddit's embed page, read again now, passes the check: its words and writer from the
backup, its items back in the extraction file (checked as before slimming), and today's read as its verification, so the
next deploy's apply-checks keeps it. One Reddit shows edited stays as it is. Made-up threads and pages: no network.
"""

import io
import shutil
import tarfile
from datetime import timedelta

from engine.extract import check_extraction
from engine.live_check import LiveChecker
from engine.tests.test_live_check import Clock, page
from engine.tests.test_slim import AGREE, TID, ZOJI, a_library, extraction_dict, whole_thread_dict
from engine.tests.test_verify import SLIMMED, comment, day, extraction_of, items_of, thread_of
from engine.slim import slim_library
from engine.verify import Ledger, apply_checks, restore_words


class Embed:
    """Reddit's embed page for one made-up comment: `html` its text as the page shows it."""

    def __init__(self, html):
        self.html, self.asked = html, []

    def __call__(self, url, headers):
        self.asked.append(url)
        return 200, page(self.html)


def a_dropped_library(tmp_path):
    """A slimmed library whose s1kept was found "edited" by a check misreading formatting, and its backup."""
    root = a_library(tmp_path, [whole_thread_dict()], {TID: extraction_dict()})
    backup = tmp_path / "backup" / "library"
    shutil.copytree(root, backup)  # the whole library, as it was before slimming
    assert slim_library(root, now=SLIMMED, gold_ids=set()).slimmed == [TID]
    ledger = Ledger()
    ledger.record("s1kept", day(8), "changed")
    apply_checks(root, ledger, now=day(8))
    assert comment(root, "s1kept").status == "not_kept" and not items_of(extraction_of(root), "s1kept")
    return root, backup, ledger


def checker(tmp_path, html, clock):
    return LiveChecker(cache_dir=tmp_path / "checks", fetch=Embed(html), clock=clock, sleep=clock.sleep, min_interval=0)


def test_a_comment_reddit_still_shows_word_for_word_gets_its_words_and_items_back(tmp_path):
    root, backup, ledger = a_dropped_library(tmp_path)
    clock = Clock()
    clock.now = day(9)
    restored = restore_words(root, backup, [(TID, "s1kept")], checker(tmp_path, ZOJI.replace("Zojirushi", "<strong>"
                                                                                               "Zojirushi</strong>"),
                                                                       clock))
    assert [(r.thread_id, r.comment_id, r.outcome, r.items) for r in restored] == [(TID, "s1kept", "passing", 1)]
    kept = comment(root, "s1kept")
    assert (kept.status, kept.body, kept.author.name, kept.verified_at) == ("ok", ZOJI, "alice_t", day(9))
    assert "s1kept" not in thread_of(root).whole_thread.comment_names
    check = check_extraction(extraction_of(root), thread_of(root))
    assert any(m.comment_id == "s1kept" for m in check.kept)
    assert any(a.comment_id == "s2agree" for a in check.kept_agreements)  # its reply's agreement had stayed
    apply_checks(root, ledger, now=day(10))  # the next deploy, with the record's older "changed"
    assert comment(root, "s1kept").status == "ok"


def test_a_comment_reddit_shows_edited_stays_as_it_is(tmp_path):
    root, backup, _ = a_dropped_library(tmp_path)
    before = {p: p.read_bytes() for p in root.rglob("*.json")}
    clock = Clock()
    clock.now = day(9)
    restored = restore_words(root, backup, [(TID, "s1kept")], checker(tmp_path, "Edit: it broke, avoid.", clock))
    assert [(r.outcome, r.items) for r in restored] == [("changed", 0)]
    assert {p: p.read_bytes() for p in root.rglob("*.json")} == before


def test_a_dry_run_writes_nothing(tmp_path):
    root, backup, _ = a_dropped_library(tmp_path)
    before = {p: p.read_bytes() for p in root.rglob("*.json")}
    clock = Clock()
    clock.now = day(9)
    restored = restore_words(root, backup, [(TID, "s1kept")], checker(tmp_path, ZOJI, clock), dry_run=True)
    assert [(r.outcome, r.items) for r in restored] == [("passing", 1)]
    assert {p: p.read_bytes() for p in root.rglob("*.json")} == before


def test_only_a_comment_slimming_kept_and_verification_dropped_is_put_back(tmp_path):
    root, backup, _ = a_dropped_library(tmp_path)
    clock = Clock()
    clock.now = day(9)
    asked = checker(tmp_path, AGREE, clock)
    # s3drop was never kept (no item points to it), s2agree is kept now, nothing is called x9none.
    restored = restore_words(root, backup, [(TID, "s3drop"), (TID, "s2agree"), (TID, "x9none")], asked)
    assert [r.outcome for r in restored] == ["not dropped by verification"] * 3
    assert asked._fetch.asked == []  # nothing was read for them


def test_the_backup_can_be_the_archive_itself(tmp_path):
    root, backup, _ = a_dropped_library(tmp_path)
    archive = tmp_path / "library-before-slim.tgz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(backup, arcname="library")
    clock = Clock()
    clock.now = day(9)
    restored = restore_words(root, archive, [(TID, "s1kept")], checker(tmp_path, ZOJI, clock))
    assert restored[0].outcome == "passing" and comment(root, "s1kept").status == "ok"


def test_the_command_gives_ids_and_outcomes_only(tmp_path, monkeypatch, capsys):
    from engine import library, live_check

    root, backup, _ = a_dropped_library(tmp_path)
    clock = Clock()
    clock.now = day(9)
    monkeypatch.setattr(live_check, "DEFAULT_CACHE_DIR", tmp_path / "checks")
    monkeypatch.setattr(live_check, "_http_get", lambda url, headers: (200, page(ZOJI), {}))
    real = live_check.LiveChecker
    monkeypatch.setattr(live_check, "LiveChecker", lambda **kw: real(fetch=lambda u, h: (200, page(ZOJI)), clock=clock,
                                                                  sleep=clock.sleep, min_interval=0, **kw))
    assert library.main(["restore-words", "--backup", str(backup), "--library", str(root), "--dry-run",
                         f"{TID}:s1kept"]) == 0
    said = capsys.readouterr().out
    assert f"{TID}:s1kept: Reddit shows it word for word" in said and "would get its words back, and 1 item(s)" in said
    assert ZOJI not in said and comment(root, "s1kept").status == "not_kept"  # a dry run: nothing written
    assert library.main(["restore-words", "--library", str(root), f"{TID}:s1kept"]) == 2  # no backup named
