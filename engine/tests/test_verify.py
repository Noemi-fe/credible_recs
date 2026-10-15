"""Keeping a slimmed library current, comment by comment (Noemi, 13 Oct 2026: "Keep only comments we use"; engine/
verify.py): each comment a slimmed thread keeps is verified on Reddit through its embed page, and one found deleted or
edited, or not verified within config.LIBRARY_VERIFY_DAYS, loses its words and its mentions.

Made-up threads and checks only: no test reads data/ or reaches the network.
"""

import json
from datetime import UTC, datetime, timedelta

import pytest

from engine import library, verify
from engine.config import LIBRARY_VERIFY_DAYS
from engine.extract import Extraction, check_extraction
from engine.live_check import LiveChecker, _entry_name, embed_url
from engine.models import Thread
from engine.slim import slim_library
from engine.tests.test_live_checks import FakeLiveParse
from engine.tests.test_slim import (AGREE, CARE, COPY, KEPT, NOTE, REPLY, TID, ZOJI, a_library, extraction_dict,
                                    other_thread, whole_thread_dict)
from engine.verify import Ledger, LedgerEntry, apply_checks, outcome, record_saved_checks, verification_quotes

SLIMMED = datetime(2026, 10, 13, 18, tzinfo=UTC)
READ = datetime(2026, 10, 6, tzinfo=UTC)  # when the made-up thread was read (through Parse): its comments' first check


def day(n: int, hour: int = 4) -> datetime:
    """n days after the thread was read, at 4 am."""
    return READ + timedelta(days=n, hours=hour)


def slimmed_library(tmp_path, *more_threads: dict, **thread_fields):
    root = a_library(tmp_path, [whole_thread_dict(**thread_fields), *more_threads], {TID: extraction_dict()})
    assert slim_library(root, now=SLIMMED, gold_ids=set()).slimmed == [TID]
    return root


def thread_of(root) -> Thread:
    return Thread.model_validate_json((root / "threads" / f"{TID}.json").read_text(encoding="utf-8"))


def extraction_of(root) -> Extraction:
    return Extraction.model_validate_json((root / "extracted" / f"{TID}.json").read_text(encoding="utf-8"))


def comment(root, comment_id: str):
    return next(c for c in thread_of(root).comments if c.id == comment_id)


def items_of(extraction: Extraction, comment_id: str) -> list:
    return [item for kind in (extraction.mentions, extraction.notes, extraction.agreements, extraction.care)
            for item in kind if item.comment_id == comment_id]


# --- What a read of a kept comment says ---

def test_a_comment_passes_when_every_quote_it_backs_is_still_found_word_for_word():
    quotes = ("I have had it 6 years.", "Love the lid.")
    assert outcome("I have had it 6 years. **Love** the lid. Edit: still going.", quotes) == "passing"
    assert outcome("[deleted]", quotes) == "deleted" and outcome(" [removed] ", quotes) == "removed"
    assert outcome("I have had it 6 years. The lid broke.", quotes) == "changed"  # edited: a quote is gone
    assert outcome(None, quotes) == "unreadable"  # the embed page showed no comment ("Not supported comment")
    # A comment kept only because a reply takes its product from it backs no quote: it passes while it is there.
    assert outcome("I bought the one above.", ()) == "passing" and outcome("[deleted]", ()) == "deleted"


def test_each_kept_comment_is_verified_by_the_quotes_its_items_hold(tmp_path):
    root = slimmed_library(tmp_path)
    quotes = verification_quotes(thread_of(root), extraction_of(root))
    assert set(quotes) == KEPT
    assert quotes["s1kept"] == (ZOJI,) and quotes["s2agree"] == (AGREE,) and quotes["s12note"] == (NOTE,)
    assert quotes["s5reply"] == (REPLY,) and quotes["s13care"] == (CARE,)
    assert quotes["s4source"] == ()  # it names the product its reply means: it is verified by being there
    assert quotes["s16rej"] == ()  # its one quote was never found in it: verified by being there


# --- The record of reads, which outlives the 48-hour checks ---

def test_the_ledger_keeps_each_comments_latest_read_and_its_last_pass():
    ledger = Ledger()
    ledger.record("c1", day(1), "passing")
    ledger.record("c1", day(9), "unreadable")
    ledger.record("c1", day(5), "passing")  # reads can arrive out of order
    assert ledger.get("c1") == LedgerEntry(at=day(9), outcome="unreadable", passed=day(5))
    again = Ledger.loads(ledger.dumps(day(10)))
    assert again.get("c1") == ledger.get("c1") and again.get("c2") is None
    other = Ledger()
    other.record("c1", day(12), "deleted")
    other.record("c2", day(3), "passing")
    ledger.merge(other)
    assert ledger.get("c1") == LedgerEntry(at=day(12), outcome="deleted", passed=day(5))
    assert ledger.get("c2") == LedgerEntry(at=day(3), outcome="passing", passed=day(3))


def test_a_ledger_that_cant_be_read_is_empty_and_bad_entries_are_left_out():
    assert Ledger.loads(b"not json").entries == {} and Ledger.loads(None).entries == {}
    data = json.dumps({"written_at": day(1).isoformat(), "comments": {
        "c1": {"at": day(1).isoformat(), "outcome": "passing", "passed": day(1).isoformat()},
        "c2": {"at": "yesterday", "outcome": "passing", "passed": None},
        "c3": {"at": day(1).isoformat(), "outcome": "maybe", "passed": None},
        "../c4": {"at": day(1).isoformat(), "outcome": "passing", "passed": None}}})
    assert list(Ledger.loads(data.encode()).entries) == ["c1"]


def test_the_ledger_holds_ids_dates_and_outcomes_only():
    ledger = Ledger()
    ledger.record("c1", day(1), "changed")
    entry = json.loads(ledger.dumps(day(2)))["comments"]["c1"]
    assert set(entry) == {"at", "outcome", "passed"}


# --- Applying the reads to the library ---

def test_a_passing_read_stamps_the_comment_and_changes_nothing_else(tmp_path):
    root = slimmed_library(tmp_path)
    assert comment(root, "s1kept").verified_at == READ  # read through Parse when the thread was saved
    before = (root / "extracted" / f"{TID}.json").read_bytes()
    ledger = Ledger()
    ledger.record("s1kept", day(14), "passing")
    result = apply_checks(root, ledger, now=day(15))
    assert comment(root, "s1kept").verified_at == day(14) and comment(root, "s2agree").verified_at == READ
    assert (result.stamped, result.dropped) == (1, {})
    assert (root / "extracted" / f"{TID}.json").read_bytes() == before


def test_a_comment_found_deleted_becomes_a_stub_and_loses_its_mentions(tmp_path):
    root = slimmed_library(tmp_path)
    ledger = Ledger()
    ledger.record("s1kept", day(14), "deleted")
    result = apply_checks(root, ledger, now=day(15))
    gone = comment(root, "s1kept")
    assert (gone.status, gone.body, gone.author, gone.verified_at) == ("deleted", "[deleted]", None, None)
    assert items_of(extraction_of(root), "s1kept") == []
    assert result.dropped == {"deleted": 1} and result.items_removed == 1
    assert "s1kept" not in thread_of(root).whole_thread.comment_names  # gone from Reddit: it names nothing now
    assert "alice_t" not in (root / "threads" / f"{TID}.json").read_text()  # no kept comment of hers is left


def test_a_comment_found_edited_keeps_only_its_shape_and_what_it_named(tmp_path):
    root = slimmed_library(tmp_path)
    ledger = Ledger()
    ledger.record("s7copy", day(14), "changed")
    apply_checks(root, ledger, now=day(15))
    edited = comment(root, "s7copy")
    assert (edited.status, edited.body, edited.author) == ("not_kept", "", None)
    assert items_of(extraction_of(root), "s7copy") == []
    facts = thread_of(root).whole_thread
    assert facts.comment_names["s7copy"] == ["electric kettle"]  # still there on Reddit: still counted
    assert COPY not in (root / "threads" / f"{TID}.json").read_text() + (root / "extracted" / f"{TID}.json").read_text()


def test_the_latest_read_decides_and_an_older_failure_is_ignored(tmp_path):
    root = slimmed_library(tmp_path)
    ledger = Ledger()
    ledger.record("s1kept", day(-1), "deleted")  # before the read the comment's own date comes from
    ledger.record("s12note", day(10), "deleted")
    ledger.record("s12note", day(12), "passing")  # back again (a page that failed, then worked)
    result = apply_checks(root, ledger, now=day(15))
    assert comment(root, "s1kept").status == "ok" and comment(root, "s12note").verified_at == day(12)
    assert result.dropped == {}


def test_an_unreadable_page_verifies_nothing_and_drops_nothing(tmp_path):
    # The embed page showing no comment ("Not supported comment", or a page Reddit redesigned) isn't proof of anything:
    # the comment simply isn't verified, and its words go only when the deadline passes (or Bright Data verifies it).
    root = slimmed_library(tmp_path)
    ledger = Ledger()
    ledger.record("s1kept", day(14), "unreadable")
    result = apply_checks(root, ledger, now=day(15))
    assert comment(root, "s1kept").status == "ok" and comment(root, "s1kept").verified_at == READ
    assert (result.stamped, result.dropped) == (0, {})


def test_a_kept_comment_not_verified_within_the_deadline_loses_its_words_and_mentions(tmp_path):
    assert LIBRARY_VERIFY_DAYS == 30
    root = slimmed_library(tmp_path)
    ledger = Ledger()
    ledger.record("s1kept", day(20), "passing")
    assert apply_checks(root, ledger, now=day(LIBRARY_VERIFY_DAYS, hour=20)).dropped == {}  # the 30th day: still kept
    result = apply_checks(root, Ledger(), now=day(LIBRARY_VERIFY_DAYS + 1))
    assert result.dropped == {"expired": len(KEPT) - 1}
    thread = thread_of(root)
    assert [c.id for c in thread.comments if c.status == "ok"] == ["s1kept"]  # verified on day 20
    left = extraction_of(root)
    assert [m.comment_id for m in left.mentions] == ["s1kept"] and not left.notes and not left.care
    assert check_extraction(left, thread).kept[0].comment_id == "s1kept"


def test_an_archive_comment_never_verified_counts_from_the_day_the_archive_was_read(tmp_path):
    root = slimmed_library(tmp_path, read_from="arctic_shift", collected_at="2026-10-01")
    assert comment(root, "s1kept").verified_at is None
    assert apply_checks(root, Ledger(), now=datetime(2026, 10, 31, 20, tzinfo=UTC)).dropped == {}
    assert apply_checks(root, Ledger(), now=datetime(2026, 11, 1, tzinfo=UTC)).dropped == {"expired": len(KEPT)}


def test_an_extraction_left_holding_a_dropped_comments_words_is_cleared_next_time(tmp_path):
    # Should a run stop between writing a thread and its extraction, the comment's items would be left behind: the next
    # run removes every item whose comment the thread no longer keeps whole, so no words of it stay anywhere.
    root = slimmed_library(tmp_path)
    data = json.loads((root / "threads" / f"{TID}.json").read_text(encoding="utf-8"))
    for cm in data["comments"]:
        if cm["id"] == "s12note":
            cm.update(status="not_kept", body="", author=None)
            cm.pop("verified_at", None)
    (root / "threads" / f"{TID}.json").write_text(json.dumps(data), encoding="utf-8")
    result = apply_checks(root, Ledger(), now=day(15))
    assert items_of(extraction_of(root), "s12note") == [] and result.items_removed == 1 and result.dropped == {}


def test_whole_threads_are_never_touched(tmp_path):
    root = slimmed_library(tmp_path, other_thread("1whole"))
    before = (root / "threads" / "1whole.json").read_bytes()
    ledger = Ledger()
    ledger.record("1wholea", day(14), "deleted")
    apply_checks(root, ledger, now=day(400))
    assert (root / "threads" / "1whole.json").read_bytes() == before


def test_a_dry_run_counts_and_writes_nothing(tmp_path):
    root = slimmed_library(tmp_path)
    files = {p: p.read_bytes() for p in root.rglob("*.json")}
    ledger = Ledger()
    ledger.record("s1kept", day(14), "deleted")
    result = apply_checks(root, ledger, now=day(15), dry_run=True)
    assert result.dropped == {"deleted": 1} and {p: p.read_bytes() for p in root.rglob("*.json")} == files


def test_the_checks_of_the_last_48_hours_are_read_into_the_ledger(tmp_path):
    root = slimmed_library(tmp_path)
    now = day(15)
    checker = LiveChecker(cache_dir=tmp_path / "cache", clock=lambda: now)
    thread = thread_of(root)
    urls = {c.id: c.url for c in thread.comments}

    def saved(comment_id: str, text: str | None, hours_ago: float) -> None:
        entry = {"fetched_at": (now - timedelta(hours=hours_ago)).isoformat(), "text": text}
        path = tmp_path / "cache" / _entry_name(embed_url(urls[comment_id]))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entry), encoding="utf-8")

    saved("s1kept", "Still true: " + ZOJI, 3)
    saved("s12note", "Edited: I changed my mind.", 10)
    saved("s13care", CARE, 50)  # older than 48 hours: never used
    ledger = Ledger()
    assert record_saved_checks(root, checker, ledger) == 2
    assert ledger.get("s1kept") == LedgerEntry(at=now - timedelta(hours=3), outcome="passing",
                                               passed=now - timedelta(hours=3))
    assert ledger.get("s12note").outcome == "changed" and ledger.get("s13care") is None


# --- The 14-day rule, comment by comment ---

def test_without_a_live_check_answers_use_only_kept_comments_verified_within_14_days(tmp_path):
    # Answers quote only text checked live on Reddit in the last 14 days (Noemi, 9 Oct 2026). A whole thread counts from
    # its last live check; a slimmed one, comment by comment. (With the live checker on, as on the site, every quote
    # shown is checked within 48 hours anyway, so the rule is off there, for whole and slimmed threads alike.)
    from datetime import date

    from engine.pipeline import answer_request
    from engine.tests.test_pipeline import REQUEST

    root = slimmed_library(tmp_path)
    ranked = lambda result: sorted(p.name for p in result.ranking.products)

    on_time = answer_request(REQUEST, library_dir=root, today=date(2026, 10, 20))  # verified 14 days before
    assert ranked(on_time) == ["Fellow Stagg EKG", "Zojirushi kettle"]
    assert (on_time.threads_used, on_time.waiting_live_check) == ([TID], [])
    # No kept comment verified in the last 14 days: the thread waits, as a whole thread would, and takes no slot.
    late = answer_request(REQUEST, library_dir=root, today=date(2026, 10, 21))
    assert (late.threads_used, late.waiting_live_check) == ([], [TID])
    ledger = Ledger()
    ledger.record("s1kept", day(14), "passing")
    apply_checks(root, ledger, now=day(15))
    stamped = answer_request(REQUEST, library_dir=root, today=date(2026, 10, 21))
    assert (stamped.threads_used, stamped.waiting_live_check) == ([TID], [])
    assert ranked(stamped) == ["Zojirushi kettle"]  # its reply's product came from an unverified comment


def test_a_slimmed_thread_keeping_no_comment_counts_from_its_own_live_read(tmp_path):
    # Found comparing the whole and slimmed library with the rule on: a thread whose extraction points to no comment
    # keeps none, and has nothing to verify; it takes a reading slot as long as the whole thread would.
    from datetime import date

    from engine.pipeline import answer_request
    from engine.tests.test_pipeline import REQUEST

    nothing = {**extraction_dict(), "mentions": [], "notes": [], "agreements": [], "care": []}
    root = a_library(tmp_path, [whole_thread_dict()], {TID: nothing})
    assert slim_library(root, now=SLIMMED, gold_ids=set()).slimmed == [TID]
    on_time = answer_request(REQUEST, library_dir=root, today=date(2026, 10, 20))  # read through Parse on 6 Oct
    assert (on_time.threads_used, on_time.waiting_live_check) == ([TID], [])
    late = answer_request(REQUEST, library_dir=root, today=date(2026, 10, 21))
    assert (late.threads_used, late.waiting_live_check) == ([], [TID])


# --- check-live and refresh: Bright Data and Parse are never spent on a slimmed thread ---

def test_check_live_never_reads_a_slimmed_thread_again_but_keeps_its_comments_deadline(tmp_path):
    from engine.tests.test_live_checks import thread as live_thread

    root = slimmed_library(tmp_path, live_thread("1archive", read_from="arctic_shift", collected="2026-11-05",
                                                 now=datetime(2026, 11, 6, tzinfo=UTC)),
                           read_from="arctic_shift", collected_at="2026-10-01")
    client = FakeLiveParse(now=datetime(2026, 11, 6, tzinfo=UTC))
    result = library.check_live(client, root, shown={TID, "1archive"}, now=datetime(2026, 11, 6, tzinfo=UTC))
    assert client.fetches == ["1archive"]  # the whole archive thread is checked as before; the slimmed one never
    assert result.comments_expired == len(KEPT) and result.text_removed == []
    assert result.waiting == 0  # the slimmed thread doesn't wait for a whole-thread check


def test_a_slimmed_thread_is_never_due_for_a_refresh(tmp_path):
    from engine.tests.test_library import FakeParseClient

    root = slimmed_library(tmp_path)
    client = FakeParseClient()
    result = library.refresh(client, root, now=datetime(2027, 6, 1, tzinfo=UTC), reader="parse")
    assert result.refreshed == [] and result.slimmed == [TID] and client.fetches == []


def test_an_archive_copy_never_replaces_a_slimmed_thread(tmp_path):
    from engine.tests.test_live_checks import thread as live_thread

    root = slimmed_library(tmp_path)
    archive_copy = Thread.model_validate(live_thread(TID, read_from="arctic_shift"))
    assert library._live_copy(archive_copy, root).slimmed


# --- The command line ---

def test_command_line_slim_and_apply_checks(tmp_path, capsys):
    root = a_library(tmp_path, [whole_thread_dict()], {TID: extraction_dict()})
    assert library.main(["slim", "--dry-run", "--library", str(root)], folder=tmp_path / "not this one") == 0
    out = capsys.readouterr().out
    assert "would slim 1 thread" in out and "nothing written" in out
    assert not thread_of(root).slimmed
    assert library.main(["slim"], folder=root) == 0
    assert "Slimmed 1 thread" in capsys.readouterr().out and thread_of(root).slimmed

    ledger = Ledger()
    ledger.record("s1kept", datetime.now(UTC) - timedelta(hours=1), "deleted")
    path = tmp_path / "ledger.json"
    path.write_bytes(ledger.dumps(datetime.now(UTC)))
    assert library.main(["apply-checks", "--ledger", str(path), "--checks", str(tmp_path / "no checks")],
                        folder=root) == 0
    out = capsys.readouterr().out
    assert "deleted on Reddit: 1" in out and ZOJI not in out
    assert comment(root, "s1kept").status == "deleted"


@pytest.mark.parametrize("argv", [["slim", "--what"], ["apply-checks", "--ledger"], ["apply-checks", "x"]])
def test_command_line_slim_and_apply_checks_explain_themselves_when_used_wrongly(tmp_path, capsys, argv):
    assert library.main(argv, folder=tmp_path) == 2
    assert "slim" in capsys.readouterr().out



# --- A reply whose product source lost its words (15 Oct 2026) ---

def test_a_reply_whose_source_was_found_edited_is_rejected_saying_so(tmp_path):
    # The coordinator found 5 such replies after the migration, rejected "whose words aren't kept in the library":
    # their sources had been kept, then found edited on Reddit. The reason now says what happened, so a stub left by
    # slimming isn't taken for one left by verification.
    root = slimmed_library(tmp_path)
    ledger = Ledger()
    ledger.record("s4source", day(3), "changed")  # the comment s5reply takes its product from
    apply_checks(root, ledger, now=day(3))
    reasons = {m.comment_id: why for m, why in check_extraction(extraction_of(root), thread_of(root)).rejected}
    assert "s4source" in reasons["s5reply"] and "edited on Reddit" in reasons["s5reply"]
    assert thread_of(root).whole_thread.dropped == {"s4source": "changed"}  # why its words went: no words kept


def test_a_reply_whose_source_went_unverified_too_long_is_rejected_saying_so(tmp_path):
    root = slimmed_library(tmp_path)
    ledger = Ledger()
    ledger.record("s5reply", day(LIBRARY_VERIFY_DAYS), "passing")  # the reply itself is verified; its source isn't
    apply_checks(root, ledger, now=day(LIBRARY_VERIFY_DAYS + 2))
    reasons = {m.comment_id: why for m, why in check_extraction(extraction_of(root), thread_of(root)).rejected}
    assert f"wasn't verified on Reddit within {LIBRARY_VERIFY_DAYS} days" in reasons["s5reply"]
