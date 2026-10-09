"""The monthly live check through Bright Data (9 Oct 2026): free, instead of Parse, whose credits are nearly used up.

Bright Data returns a thread as Reddit shows it now, but only its top-level comments and their direct replies, never
replies to replies. So its copy is merged into the stored one (library.merge_bright_data_read) instead of replacing it.

Every test uses fakes and temporary folders with made-up data: no network, no records, no credits, nothing in data/.
"""

import json
from datetime import UTC, datetime

import pytest

from engine import library
from engine.bright_data import BrightDataError, ReadNotes
from engine.config import (
    ARCHIVE_TEXT_KEPT_DAYS,
    BRIGHT_DATA_MONTHLY_RECORDS,
    LIVE_CHECK_READER,
    LIVE_CHECK_RECORD_RESERVE,
)
from engine.extract import load_checked
from engine.models import Thread
from engine.parse_reddit import parse_thread_url
from engine.tests.factories import make_comment
from engine.tests.test_library import refuse_to_build
from engine.tests.test_live_checks import SHOWN, NOW, FakeLiveParse, at, library_of, mixed_library, saved, thread


def depth(comment, by_id) -> int:
    """0 for a top-level comment, 1 for a direct reply, 2 or more for a reply to a reply."""
    n = 0
    while comment.parent_id is not None:
        comment, n = by_id[comment.parent_id], n + 1
    return n


class FakeBrightData:
    """Stands in for BrightDataClient: Reddit as it is now (`live`, whole threads), seen the way Bright Data sees it,
    without replies to replies. A read costs 1 record for the post and 1 per top-level comment."""

    def __init__(self, live=(), fail_on=(), used=0, now=NOW, post_unread=(), refuse_account=False):
        self.live = {t.id: t for t in live}
        self.fail_on = set(fail_on)
        self.used = used  # records already used this month
        self.now = now
        self.post_unread = set(post_unread)  # threads whose post can't be read
        self.refuse_account = refuse_account
        self.reads: list[str] = []
        self.last_read = ReadNotes()

    def get_thread(self, post_url: str) -> Thread:
        post_id = parse_thread_url(post_url)[1]
        self.reads.append(post_id)
        if self.refuse_account:
            raise BrightDataError("Bright Data refused the key (401) on starting the post job", account_problem=True)
        if post_id in self.fail_on:
            raise BrightDataError(f"Bright Data's comments job for {post_id} failed: no reason given")
        now = self.live.get(post_id) or Thread.model_validate(
            thread(post_id, read_from="bright_data", collected=self.now.isoformat(), checked=self.now.isoformat(),
                   now=self.now, num_comments=2))
        by_id = {c.id: c for c in now.comments}
        seen = [c for c in now.comments if depth(c, by_id) <= 1]  # never a reply to a reply
        update = {"comments": seen, "read_from": "bright_data", "collected_at": self.now, "checked_live_at": self.now}
        if post_id in self.post_unread:  # the title from the link's words, no text, no writer
            update |= {"title": "kettle", "body": "", "author": None}
        top_level = sum(c.parent_id is None for c in seen)
        self.used += 1 + top_level
        self.last_read = ReadNotes(records=1 + top_level, post_read=post_id not in self.post_unread)
        return now.model_copy(update=update)

    def records_used_this_month(self) -> int:
        return self.used


def reply(comment_id: str, parent_id: str, body: str, thread_id: str = "1arch", **overrides) -> dict:
    return make_comment(comment_id, thread_id=thread_id, parent_id=parent_id, body=body, **overrides)


def top(comment_id: str, body: str, thread_id: str = "1arch", **overrides) -> dict:
    return make_comment(comment_id, thread_id=thread_id, body=body, **overrides)


STORED = {
    "t1": "My Zojirushi kettle has lasted 6 years.",
    "r1": "Mine too, 8 years now.",
    "rr1": "Same, a Zojirushi for 10 years.",
    "t2": "The Chefman kettle died in 6 months.",
    "r2": "Mine died too.",
    "rr2": "Chefman support never answered.",
    "t3": "Dualit for 12 years, still going.",
}
PARENTS = {"r1": "t1", "rr1": "r1", "r2": "t2", "rr2": "r2"}


def stored_thread(collected: str | None = None, now: datetime = NOW) -> dict:
    """An archive thread: two top-level comments with a reply and a reply to it each, and a third top-level comment."""
    comments = [make_comment(cid, thread_id="1arch", parent_id=PARENTS.get(cid), body=text) for cid, text in STORED.items()]
    return thread("1arch", read_from="arctic_shift", collected=collected or at(3, now), comments=comments,
                  num_comments=7, now=now)


def reddit_now() -> Thread:
    """1arch on Reddit today: t1 edited, r1 deleted, t2 gone with its replies, t3 removed, a new comment t4."""
    return Thread.model_validate(thread("1arch", read_from="bright_data", collected=NOW.isoformat(), num_comments=8, comments=[
        top("t1", "My Zojirushi kettle has lasted 6 years. Edit: 7 now."),
        reply("r1", "t1", "[deleted]", author=None, status="deleted"),
        reply("rr1", "r1", "Same, a Zojirushi for 10 years."),
        top("t3", "[removed]", author=None, status="removed"),
        top("t4", "Bought a Fellow Stagg last week."),
    ]))


def write_extraction(folder, thread_id: str, quotes: dict[str, str]) -> bytes:
    extraction = {"thread_id": thread_id, "instructions_version": "extract-v6", "extracted_at": at(2), "extractor": "claude-code",
                  "mentions": [{"comment_id": cid, "product": "Zojirushi kettle", "category": "kitchen", "stance": "recommend",
                                "quote": text} for cid, text in quotes.items()]}
    (folder / "extracted").mkdir(exist_ok=True)
    path = folder / "extracted" / f"{thread_id}.json"
    path.write_text(json.dumps(extraction), encoding="utf-8")
    return path.read_bytes()


# --- The decided values ---

def test_the_values():
    assert LIVE_CHECK_READER == "bright_data"  # decided 9 Oct 2026: free, while Parse's credits are nearly used up
    assert LIVE_CHECK_RECORD_RESERVE == 300  # chosen by Claude: records kept back for backup reads


# --- The merge: what a Bright Data read changes in the stored thread ---

def test_returned_comments_replace_the_stored_ones_missing_ones_count_as_deleted_and_replies_to_replies_stay(tmp_path):
    folder = library_of(tmp_path, stored_thread())
    result = library.check_live(folder=folder, now=NOW, bright_data=FakeBrightData([reddit_now()]))

    stored = saved(folder)["1arch"]  # the file still loads: every reply's parent is still in it
    by_id = {c.id: c for c in stored.comments}
    assert [c.id for c in stored.comments] == ["t1", "r1", "rr1", "t2", "r2", "rr2", "t3", "t4"]
    assert by_id["t1"].body == "My Zojirushi kettle has lasted 6 years. Edit: 7 now."  # as Reddit shows it now
    assert (by_id["r1"].status, by_id["r1"].body, by_id["r1"].author) == ("deleted", "[deleted]", None)
    assert (by_id["t3"].status, by_id["t3"].body, by_id["t3"].author) == ("removed", "[removed]", None)
    # Not returned, but a top-level comment and a direct reply: Bright Data would have returned them. Treated as deleted.
    for gone in ("t2", "r2"):
        assert (by_id[gone].status, by_id[gone].body, by_id[gone].author) == ("deleted", "[deleted]", None)
    # Replies to replies are never returned: no evidence either way, so they stay exactly as they were.
    for kept in ("rr1", "rr2"):
        assert (by_id[kept].status, by_id[kept].body) == ("ok", STORED[kept]) and by_id[kept].author is not None
    assert by_id["t4"].body == "Bought a Fellow Stagg last week."  # written since: added
    assert result.reader == "bright_data" and result.checked == ["1arch"]
    assert result.dropped_comments == 4  # r1, t2, r2 and t3 are no longer readable
    assert result.replies_kept == 2


def test_a_thread_still_holding_unchecked_replies_keeps_where_it_was_read_and_is_marked_checked(tmp_path):
    folder = library_of(tmp_path, stored_thread())
    library.check_live(folder=folder, now=NOW, bright_data=FakeBrightData([reddit_now()]))
    stored = saved(folder)["1arch"]
    # Its replies to replies came from the archive and were never read live: it stays an archive thread, so it is still
    # checked monthly and still under retention; but it counts as checked live now.
    assert stored.read_from == "arctic_shift"
    assert stored.checked_live_at == NOW and stored.collected_at == NOW and stored.last_checked_live() == NOW
    assert stored.num_comments == 8  # Reddit's count, from the post Bright Data read


def test_a_thread_whose_every_comment_was_returned_counts_as_read_through_bright_data(tmp_path):
    folder = library_of(tmp_path, thread("1arch", read_from="arctic_shift", collected=at(3), num_comments=2))
    result = library.check_live(folder=folder, now=NOW, bright_data=FakeBrightData())
    stored = saved(folder)["1arch"]
    assert (stored.read_from, stored.checked_live_at) == ("bright_data", NOW)
    assert result.replies_kept == 0 and result.dropped_comments == 0


def test_replies_to_replies_already_gone_leave_nothing_unchecked(tmp_path):
    comments = [top("t1", "My Zojirushi kettle has lasted 6 years."), reply("r1", "t1", "Mine too."),
                reply("rr1", "r1", "[deleted]", author=None, status="deleted")]
    folder = library_of(tmp_path, thread("1arch", read_from="arctic_shift", collected=at(3), comments=comments))
    live = Thread.model_validate(thread("1arch", collected=NOW.isoformat(), comments=comments))
    result = library.check_live(folder=folder, now=NOW, bright_data=FakeBrightData([live]))
    assert saved(folder)["1arch"].read_from == "bright_data" and result.replies_kept == 0


def test_the_merge_on_its_own():
    stored = Thread.model_validate(stored_thread())
    fresh = FakeBrightData([reddit_now()]).get_thread(stored.url)
    merged, kept = library.merge_bright_data_read(stored, fresh)
    assert kept == 2 and merged.read_from == "arctic_shift" and merged.checked_live_at == NOW
    assert [c.id for c in merged.comments if c.status == "ok"] == ["t1", "rr1", "rr2", "t4"]
    assert merged.title == fresh.title and merged.id == stored.id and merged.community == stored.community


def test_when_the_post_cant_be_read_the_stored_post_is_kept(tmp_path):
    folder = library_of(tmp_path, thread("1arch", read_from="arctic_shift", collected=at(3), num_comments=2,
                                         title="Which electric kettle lasts 10 years?", body="Mine died again."))
    result = library.check_live(folder=folder, now=NOW, bright_data=FakeBrightData(post_unread={"1arch"}))
    stored = saved(folder)["1arch"]
    assert (stored.title, stored.body) == ("Which electric kettle lasts 10 years?", "Mine died again.")
    assert stored.author is not None and stored.read_from == "arctic_shift"  # the post wasn't read live
    assert stored.checked_live_at == NOW and result.posts_gone == []


def test_a_post_gone_from_reddit_is_reported_and_kept(tmp_path):
    folder = library_of(tmp_path, thread("1arch", read_from="arctic_shift", collected=at(3), num_comments=2))
    live = Thread.model_validate(thread("1arch", collected=NOW.isoformat(), body="[deleted]", num_comments=2))
    result = library.check_live(folder=folder, now=NOW, bright_data=FakeBrightData([live]))
    assert result.posts_gone == ["1arch"] and "1arch" in saved(folder)


def test_the_extraction_is_kept_and_its_checks_drop_only_the_gone_comments(tmp_path):
    folder = library_of(tmp_path, stored_thread())
    before = write_extraction(folder, "1arch", {cid: STORED[cid] for cid in ("t1", "rr1", "t2", "rr2")})
    library.check_live(folder=folder, now=NOW, bright_data=FakeBrightData([reddit_now()]))
    assert (folder / "extracted" / "1arch.json").read_bytes() == before
    checked = load_checked(folder / "threads")["1arch"]
    assert [m.comment_id for m in checked.kept] == ["t1", "rr1", "rr2"]  # t1's quote is still in its edited text
    assert [m.comment_id for m, _ in checked.rejected] == ["t2"]


# --- Which threads, in what order ---

def test_bright_data_reads_the_same_threads_in_the_same_order_as_parse(tmp_path):
    client = FakeBrightData()
    result = library.check_live(folder=mixed_library(tmp_path), shown=SHOWN, now=NOW, bright_data=client)
    assert client.reads == ["1shownarch", "1shownold", "1archnever", "1archold"]
    assert result.checked == client.reads and result.shown_checked == ["1shownarch", "1shownold"]


def test_threads_read_through_bright_data_are_read_again_monthly(tmp_path):
    folder = library_of(
        tmp_path,
        thread("1bdold", read_from="bright_data", collected=at(31), checked=at(31), num_comments=2),
        thread("1bdnew", read_from="bright_data", collected=at(10), checked=at(10), num_comments=2),
    )
    client = FakeBrightData()
    library.check_live(folder=folder, now=NOW, bright_data=client)
    assert client.reads == ["1bdold"]


# --- Records and failures ---

def small_archive(tmp_path, count: int = 5):
    """Archive threads of 2 comments each: a Bright Data read costs at most 3 records (the post, 2 comments)."""
    return library_of(tmp_path, *(thread(f"1a{n}", read_from="arctic_shift", collected=at(20 - n), num_comments=2)
                                  for n in range(count)))


def test_by_default_it_stops_at_the_records_left_this_month_minus_the_reserve(tmp_path):
    client = FakeBrightData(used=BRIGHT_DATA_MONTHLY_RECORDS - LIVE_CHECK_RECORD_RESERVE - 10)  # 10 records to spend
    result = library.check_live(folder=small_archive(tmp_path), now=NOW, bright_data=client)
    assert result.checked == ["1a0", "1a1", "1a2"] and result.not_tried == ["1a3", "1a4"] and result.capped
    assert (result.record_cap, result.records_used, result.records_left) == (10, 9, LIVE_CHECK_RECORD_RESERVE + 1)
    assert (result.credits_used, result.credit_cap) == (0, 0)  # no Parse credits


def test_max_records_sets_the_cap_but_never_past_whats_left(tmp_path):
    result = library.check_live(folder=small_archive(tmp_path), now=NOW, bright_data=FakeBrightData(), max_records=6)
    assert result.checked == ["1a0", "1a1"] and result.record_cap == 6
    nearly_out = FakeBrightData(used=BRIGHT_DATA_MONTHLY_RECORDS - 4)
    result = library.check_live(folder=small_archive(tmp_path / "2"), now=NOW, bright_data=nearly_out, max_records=50)
    assert result.checked == ["1a0"] and result.record_cap == 4 and result.records_left == 1


def test_a_read_is_not_started_when_the_threads_comments_could_take_it_past_the_cap(tmp_path):
    # One record per top-level comment: a thread Reddit counted 42 comments for could cost up to 43.
    folder = library_of(tmp_path, thread("1big", read_from="arctic_shift", collected=at(20), num_comments=42))
    client = FakeBrightData()
    result = library.check_live(folder=folder, now=NOW, bright_data=client, max_records=40)
    assert client.reads == [] and result.not_tried == ["1big"] and result.capped


def test_a_failure_is_reported_three_in_a_row_stop_the_run_and_an_account_problem_stops_it_at_once(tmp_path):
    folder = small_archive(tmp_path, 6)
    before = (folder / "threads" / "1a0.json").read_bytes()
    one = library.check_live(folder=folder, now=NOW, bright_data=FakeBrightData(fail_on={"1a0"}), max_records=3)
    assert list(one.failed) == ["1a0"] and one.checked == ["1a1"] and not one.stopped
    assert (folder / "threads" / "1a0.json").read_bytes() == before  # left as it was

    three = library.check_live(folder=small_archive(tmp_path / "2", 6), now=NOW,
                               bright_data=FakeBrightData(fail_on={"1a0", "1a1", "1a2"}))
    assert three.stopped and list(three.failed) == ["1a0", "1a1", "1a2"] and three.not_tried == ["1a3", "1a4", "1a5"]
    assert not three.account_problem

    refused = FakeBrightData(refuse_account=True)
    account = library.check_live(folder=small_archive(tmp_path / "3", 6), now=NOW, bright_data=refused)
    assert refused.reads == ["1a0"] and account.stopped and account.account_problem
    assert account.not_tried == ["1a1", "1a2", "1a3", "1a4", "1a5"]


def test_retention_still_runs_after_a_bright_data_run(tmp_path):
    folder = library_of(tmp_path, thread("1expired", read_from="arctic_shift", collected=at(ARCHIVE_TEXT_KEPT_DAYS + 1)))
    result = library.check_live(folder=folder, now=NOW, bright_data=FakeBrightData(), max_records=0)
    assert result.text_removed == ["1expired"] and result.checked == []


# --- Which reader ---

def test_bright_data_is_the_default_reader_and_parse_is_never_built_for_it(tmp_path, monkeypatch):
    client = FakeBrightData()
    monkeypatch.setattr(library, "BrightDataClient", lambda: client)
    monkeypatch.setattr(library, "ParseRedditClient", refuse_to_build)
    result = library.check_live(folder=small_archive(tmp_path, 1), now=NOW)
    assert result.reader == "bright_data" and client.reads == ["1a0"]


def test_parse_reads_when_asked_and_when_only_a_parse_client_is_given(tmp_path, monkeypatch):
    parse = FakeLiveParse()
    monkeypatch.setattr(library, "ParseRedditClient", lambda: parse)
    monkeypatch.setattr(library, "BrightDataClient", refuse_to_build)
    asked = library.check_live(folder=small_archive(tmp_path, 1), now=NOW, reader="parse")
    assert asked.reader == "parse" and parse.fetches == ["1a0"] and asked.credits_used == 2
    given = FakeLiveParse()
    alone = library.check_live(given, small_archive(tmp_path / "2", 1), now=NOW)  # as callers did before 9 Oct 2026
    assert alone.reader == "parse" and given.fetches == ["1a0"]
    both = library.check_live(FakeLiveParse(), small_archive(tmp_path / "3", 1), now=NOW, bright_data=FakeBrightData())
    assert both.reader == "bright_data"


def test_an_unknown_reader_is_refused(tmp_path):
    with pytest.raises(ValueError):
        library.check_live(folder=tmp_path, now=NOW, reader="pushshift", bright_data=FakeBrightData())


# --- On the command line ---

def test_command_line_check_live_reads_through_bright_data_by_default(tmp_path, capsys):
    now = datetime.now(UTC)  # the command line uses the real clock
    folder = library_of(tmp_path, stored_thread(collected=at(3, now), now=now))
    parse = FakeLiveParse(now=now)
    client = FakeBrightData([reddit_now()], used=100, now=now)  # it reads at the real time too

    assert library.main(["check-live"], client=parse, folder=folder, shown=set(), bright_data=client) == 0

    out = capsys.readouterr().out
    assert parse.fetches == [] and client.reads == ["1arch"]
    assert "Checked live on Reddit through Bright Data: 1 thread(s): 1arch." in out
    assert "Comments gone from the live copies (deleted, removed or no longer there): 4" in out
    assert "Replies to replies kept as they were (Bright Data never returns them, so they aren't taken as deleted): 2" in out
    assert "Bright Data records: 4 used by this run (cap 4600); 4896 left this month." in out
    assert out.rstrip().endswith("Parse credits used this month: 0 of 200 (the parse.bot dashboard has the exact figure)")


def test_command_line_check_live_reads_through_parse_when_asked(tmp_path, capsys):
    now = datetime.now(UTC)
    folder = library_of(tmp_path, thread("1arch", read_from="arctic_shift", collected=at(3, now), now=now))
    parse, client = FakeLiveParse(now=now), FakeBrightData(now=now)
    assert library.main(["check-live", "--reader", "parse", "--max-credits", "2"], client=parse, folder=folder,
                        shown=set(), bright_data=client) == 0
    assert parse.fetches == ["1arch"] and client.reads == []
    assert "Checked live on Reddit through Parse: 1 thread(s): 1arch." in capsys.readouterr().out


def test_command_line_check_live_takes_a_record_cap(tmp_path, capsys):
    now = datetime.now(UTC)
    folder = library_of(tmp_path, *(thread(f"1a{n}", read_from="arctic_shift", collected=at(5 - n, now), now=now,
                                           num_comments=2) for n in range(3)))
    client = FakeBrightData(now=now)
    assert library.main(["check-live", "--max-records", "3"], client=FakeLiveParse(now=now), folder=folder, shown=set(),
                        bright_data=client) == 0
    assert client.reads == ["1a0"]
    assert "Not checked this time (record cap reached), saved copies unchanged: 1a1, 1a2" in capsys.readouterr().out
    assert library.main(["check-live", "--reader=bright_data", "--max-records=0"], client=FakeLiveParse(now=now),
                        folder=folder, shown=set(), bright_data=FakeBrightData(now=now)) == 0


def test_command_line_check_live_says_when_bright_data_refused_the_account(tmp_path, capsys):
    now = datetime.now(UTC)
    folder = library_of(tmp_path, *(thread(f"1a{n}", read_from="arctic_shift", collected=at(5 - n, now), now=now,
                                           num_comments=2) for n in range(2)))
    client = FakeBrightData(now=now, refuse_account=True)
    assert library.main(["check-live"], client=FakeLiveParse(now=now), folder=folder, shown=set(), bright_data=client) == 1
    out = capsys.readouterr().out
    assert "1a0: Bright Data refused the key (401)" in out
    assert "Not checked this time (Bright Data refused the account: its key, or no records left), saved copies unchanged: 1a1" in out


def test_a_real_run_builds_the_bright_data_client_for_check_live(tmp_path, monkeypatch, capsys):
    client = FakeBrightData()
    monkeypatch.setattr(library, "BrightDataClient", lambda: client)
    monkeypatch.setattr(library, "ParseRedditClient", lambda: FakeLiveParse())
    monkeypatch.setattr(library, "ArcticShiftClient", lambda: "an Arctic Shift client")
    folder = library_of(tmp_path, thread("1arch", read_from="arctic_shift", collected=at(3, datetime.now(UTC)),
                                         now=datetime.now(UTC), num_comments=2))
    assert library.main(["check-live"], folder=folder, shown=set()) == 0
    assert client.reads == ["1arch"] and "through Bright Data" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [
    ["check-live", "--reader", "pushshift"], ["check-live", "--reader"], ["check-live", "--max-records", "lots"],
    ["check-live", "--reader", "parse", "--max-records", "5"],  # Parse spends credits, not records
    ["check-live", "--reader", "bright_data", "--max-credits", "5"],  # Bright Data spends records, not credits
    ["check-live", "--max-credits", "5"],  # the default reader is Bright Data
    ["check-live", "--max-records", "5", "--max-records", "6"],
])
def test_command_line_check_live_explains_its_reader_options_when_used_wrongly(tmp_path, capsys, argv):
    parse, client = FakeLiveParse(), FakeBrightData()
    assert library.main(argv, client=parse, folder=tmp_path, shown=set(), bright_data=client) == 2
    out = capsys.readouterr().out
    assert "check-live [--max-credits N] [--max-records N] [--reader bright_data|parse]" in out
    assert parse.fetches == [] and client.reads == []
