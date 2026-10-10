"""Live checks (Noemi, 9 Oct 2026): threads read from the archive are read again on Reddit through Parse, regularly,
and answers only quote threads checked live in the last 14 days.

Every test uses fakes and temporary folders with made-up data: no network, no credits, nothing written to data/.
"""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from engine import library, pipeline, slice_eval
from engine.config import (
    ARCHIVE_TEXT_KEPT_DAYS,
    ARCHIVE_TEXT_RETENTION,
    LIBRARY_READER,
    LIVE_CHECK_ALL_DAYS,
    LIVE_CHECK_CREDIT_RESERVE,
    LIVE_CHECK_REQUIRED,
    LIVE_CHECK_SHOWN_DAYS,
)
from engine.extract import load_checked
from engine.gold import load_threads
from engine.models import Thread
from engine.parse_reddit import ParseAPIError
from engine.pipeline import answer_request
from engine.slice_eval import score_questions, slice_lines, threads_behind_answers
from engine.sources import ArchiveSource
from engine.tests.factories import make_comment, make_thread, write_gold
from engine.tests.test_archive_reader import FakeArchiveClient, kettle_posts
from engine.tests.test_library import FakeParseClient
from engine.tests.test_pipeline import REQUEST
from engine.tests.test_pipeline import library as kettle_library
from engine.tests.test_slice_eval import questions_file

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)


def at(days_ago: float, now: datetime = NOW) -> str:
    return (now - timedelta(days=days_ago)).isoformat()


def thread(thread_id: str, read_from=None, collected=None, checked=None, comments=None, now=NOW, **overrides) -> dict:
    """A kettle thread in the library, with its provenance. Collected 1 day before `now` unless said otherwise."""
    fields = {
        "id": thread_id, "community": "BuyItForLife", "category": "kitchen", "title": "Which electric kettle lasts?",
        "body": "My kettle died again.", "url": f"https://www.reddit.com/r/BuyItForLife/comments/{thread_id}/kettle/",
        "collected_at": collected or at(1, now),
        "comments": comments or [
            make_comment(f"{thread_id}k1", thread_id=thread_id, body="My Zojirushi kettle has lasted 6 years."),
            make_comment(f"{thread_id}k2", thread_id=thread_id, body="Dualit for 12 years, still going."),
        ],
    }
    if read_from is not None:
        fields["read_from"] = read_from
    if checked is not None:
        fields["checked_live_at"] = checked
    return make_thread(**{**fields, **overrides})


def library_of(tmp_path: Path, *threads: dict) -> Path:
    write_gold(tmp_path, list(threads), voices=None, mentions=None)
    return tmp_path


def saved(folder: Path) -> dict[str, Thread]:
    return {t.id: t for t in load_threads(folder / "threads")}


class FakeLiveParse:
    """Stands in for ParseRedditClient during live checks: Reddit's current version of each thread, 2 credits a read."""

    def __init__(self, live=(), fail_on=(), used=0, now=NOW):
        self.live = {t.id: t for t in live}
        self.fail_on = set(fail_on)
        self.used = used  # credits already used this month
        self.now = now
        self.fetches: list[str] = []

    def get_thread(self, subreddit, post_id, limit=500, sort="top"):
        self.fetches.append(post_id)
        if post_id in self.fail_on:
            raise ParseAPIError(f"Parse answered 404 to get_post_comments: post {post_id} not found")
        self.used += 2
        if post_id in self.live:
            return self.live[post_id]
        return Thread.model_validate(thread(post_id, read_from="parse", collected=self.now.isoformat(),
                                            checked=self.now.isoformat(), now=self.now))

    def credits_used_this_month(self) -> int:
        return self.used


# --- The decided values ---

def test_the_decided_values():
    # Changed on purpose 11 Oct 2026 (Noemi asked for a Bright Data tool so the library never gets stuck): "auto" tries
    # the archive first, as decided on 9 Oct, and turns to Bright Data only when Arctic Shift fails.
    assert (LIBRARY_READER, LIVE_CHECK_SHOWN_DAYS, LIVE_CHECK_ALL_DAYS) == ("auto", 14, 30)
    assert LIVE_CHECK_REQUIRED is True and ARCHIVE_TEXT_RETENTION is True
    assert ARCHIVE_TEXT_KEPT_DAYS == LIVE_CHECK_ALL_DAYS + 7 and LIVE_CHECK_CREDIT_RESERVE == 20


# --- check-live: what is read again, in what order ---

def mixed_library(tmp_path: Path) -> Path:
    return library_of(
        tmp_path,
        thread("1shownold", collected=at(21)),  # read through Parse 21 days ago, quoted in answers: due first
        thread("1shownnew", collected=at(5)),  # quoted, but read 5 days ago: not due
        thread("1shownarch", read_from="arctic_shift", collected=at(2)),  # quoted, from the archive, never checked
        thread("1archnever", read_from="arctic_shift", collected=at(10)),  # from the archive, never checked
        thread("1archold", read_from="arctic_shift", collected=at(60), checked=at(35)),  # last checked 35 days ago
        thread("1archrecent", read_from="arctic_shift", collected=at(60), checked=at(10)),  # checked 10 days ago
        thread("1parseold", collected=at(60)),  # read through Parse long ago, not quoted: refresh's job, not this
        thread("1gold", read_from="gold", collected=at(90)),  # hand-collected: never checked here
    )


SHOWN = {"1shownold", "1shownnew", "1shownarch", "1gold", "1notinlibrary"}


def test_quoted_threads_come_first_then_archive_threads_never_checked_then_the_oldest_checks(tmp_path):
    folder = mixed_library(tmp_path)
    client = FakeLiveParse()
    result = library.check_live(client, folder, shown=SHOWN, now=NOW)
    assert client.fetches == ["1shownarch", "1shownold", "1archnever", "1archold"]
    assert result.checked == client.fetches and result.shown_checked == ["1shownarch", "1shownold"]
    assert (result.credits_used, result.credits_left) == (8, 192)
    assert result.not_tried == [] and result.failed == {} and not result.stopped


def test_without_quoted_threads_only_archive_threads_are_checked(tmp_path):
    client = FakeLiveParse()
    library.check_live(client, mixed_library(tmp_path), now=NOW)
    assert client.fetches == ["1archnever", "1shownarch", "1archold"]  # never checked first, the oldest read first


def test_a_quoted_thread_is_due_the_day_after_its_14_days(tmp_path):
    folder = library_of(tmp_path, thread("1on", collected=at(14)), thread("1past", collected=at(15)))
    client = FakeLiveParse()
    library.check_live(client, folder, shown={"1on", "1past"}, now=NOW)
    assert client.fetches == ["1past"]


def test_a_live_check_replaces_the_archive_copy_and_keeps_the_extraction(tmp_path):
    body = {"k1": "My Zojirushi kettle has lasted 6 years.", "k2": "The Chefman kettle died in 6 months.",
            "k3": "Dualit for 12 years, still going."}
    comments = [make_comment(cid, thread_id="1arch", body=text) for cid, text in body.items()]
    folder = library_of(tmp_path, thread("1arch", read_from="arctic_shift", collected=at(3), comments=comments))
    extraction = {"thread_id": "1arch", "instructions_version": "extract-v6", "extracted_at": at(2), "extractor": "claude-code",
                  "mentions": [{"comment_id": cid, "product": "a kettle", "category": "kitchen", "stance": "recommend",
                                "quote": text} for cid, text in body.items()]}
    (folder / "extracted").mkdir()
    (folder / "extracted" / "1arch.json").write_text(json.dumps(extraction), encoding="utf-8")
    before = (folder / "extracted" / "1arch.json").read_bytes()
    # On Reddit now: k2 deleted, k3 edited.
    live = Thread.model_validate(thread("1arch", read_from="parse", collected=at(0), checked=at(0), comments=[
        make_comment("k1", thread_id="1arch", body=body["k1"]),
        make_comment("k2", thread_id="1arch", body="[deleted]", author=None, status="deleted"),
        make_comment("k3", thread_id="1arch", body="Dualit for 12 years, the lid broke last week though."),
    ]))

    result = library.check_live(FakeLiveParse([live]), folder, now=NOW)

    stored = saved(folder)["1arch"]
    assert (stored.read_from, stored.checked_live_at) == ("parse", NOW)
    assert stored.comments[1].body == "[deleted]"
    assert result.checked == ["1arch"] and result.dropped_comments == 1
    assert (folder / "extracted" / "1arch.json").read_bytes() == before  # the AI's extraction is kept as it was
    checked = load_checked(folder / "threads")["1arch"]
    assert [m.comment_id for m in checked.kept] == ["k1"]  # the deleted comment and the edited quote are dropped
    assert sorted(m.comment_id for m, _ in checked.rejected) == ["k2", "k3"]


def test_a_post_gone_from_reddit_is_reported_and_kept(tmp_path):
    folder = library_of(tmp_path, thread("1arch", read_from="arctic_shift", collected=at(3)))
    live = Thread.model_validate(thread("1arch", read_from="parse", collected=at(0), checked=at(0), body="[deleted]"))
    assert library.check_live(FakeLiveParse([live]), folder, now=NOW).posts_gone == ["1arch"]


def test_nothing_due_costs_nothing(tmp_path):
    folder = library_of(tmp_path, thread("1fresh", collected=at(2)), thread("1checked", read_from="arctic_shift", checked=at(3)))
    client = FakeLiveParse(used=40)
    result = library.check_live(client, folder, shown={"1fresh"}, now=NOW)
    assert client.fetches == [] and result.checked == [] and (result.credits_used, result.credits_left) == (0, 160)


# --- check-live: credits and failures ---

def archive_library(tmp_path: Path, count: int = 5) -> Path:
    return library_of(tmp_path, *(thread(f"1a{n}", read_from="arctic_shift", collected=at(20 - n)) for n in range(count)))


def test_by_default_it_stops_at_whats_left_this_month_minus_the_reserve(tmp_path):
    client = FakeLiveParse(used=200 - 24)  # 24 left, 20 kept in reserve: 4 credits, 2 threads
    result = library.check_live(client, archive_library(tmp_path), now=NOW)
    assert result.checked == ["1a0", "1a1"] and result.not_tried == ["1a2", "1a3", "1a4"]
    assert (result.credit_cap, result.credits_used, result.credits_left) == (4, 4, 20)


def test_max_credits_sets_the_cap(tmp_path):
    result = library.check_live(FakeLiveParse(), archive_library(tmp_path), max_credits=6, now=NOW)
    assert result.checked == ["1a0", "1a1", "1a2"] and result.credits_used == 6


def test_max_credits_never_goes_past_whats_left_this_month(tmp_path):
    result = library.check_live(FakeLiveParse(used=198), archive_library(tmp_path), max_credits=50, now=NOW)
    assert result.checked == ["1a0"] and result.credits_left == 0


def test_a_failure_is_reported_and_three_in_a_row_stop_the_run(tmp_path):
    folder = archive_library(tmp_path, 6)
    before = (folder / "threads" / "1a0.json").read_bytes()
    one = library.check_live(FakeLiveParse(fail_on={"1a0"}), folder, max_credits=2, now=NOW)
    assert list(one.failed) == ["1a0"] and one.checked == ["1a1"] and not one.stopped
    assert (folder / "threads" / "1a0.json").read_bytes() == before  # left as it was

    folder = archive_library(tmp_path / "again", 6)
    three = library.check_live(FakeLiveParse(fail_on={"1a0", "1a1", "1a2"}), folder, now=NOW)
    assert three.stopped and list(three.failed) == ["1a0", "1a1", "1a2"] and three.not_tried == ["1a3", "1a4", "1a5"]


# --- Retention: archive text not checked live within 37 days is removed ---

def test_archive_text_not_checked_live_within_37_days_is_removed_but_the_thread_stays(tmp_path):
    folder = library_of(
        tmp_path,
        thread("1expired", read_from="arctic_shift", collected=at(ARCHIVE_TEXT_KEPT_DAYS + 1)),
        thread("1lastday", read_from="arctic_shift", collected=at(ARCHIVE_TEXT_KEPT_DAYS)),
        thread("1checkedlongago", read_from="arctic_shift", collected=at(90), checked=at(40)),
        thread("1parseold", collected=at(90)),  # read through Parse: its text came from Reddit itself
    )
    result = library.check_live(FakeLiveParse(), folder, max_credits=0, now=NOW)  # nothing can be checked

    assert result.text_removed == ["1checkedlongago", "1expired"]
    threads = saved(folder)  # every file still loads
    expired = threads["1expired"]
    assert expired.title == "Which electric kettle lasts?" and expired.body == ""
    assert [c.id for c in expired.comments] == ["1expiredk1", "1expiredk2"]  # ids kept, so it can be read again
    assert {(c.status, c.body, c.author) for c in expired.comments} == {("removed", "[removed]", None)}
    assert all(c.status == "ok" for c in threads["1lastday"].comments)
    assert all(c.status == "ok" for c in threads["1parseold"].comments)


def test_text_removed_once_is_not_reported_again(tmp_path):
    folder = library_of(tmp_path, thread("1expired", read_from="arctic_shift", collected=at(40)))
    assert library.check_live(FakeLiveParse(), folder, max_credits=0, now=NOW).text_removed == ["1expired"]
    assert library.check_live(FakeLiveParse(), folder, max_credits=0, now=NOW).text_removed == []


def test_a_thread_checked_in_this_run_keeps_its_text(tmp_path):
    folder = library_of(tmp_path, thread("1expired", read_from="arctic_shift", collected=at(40)))
    result = library.check_live(FakeLiveParse(), folder, now=NOW)
    assert result.checked == ["1expired"] and result.text_removed == []
    assert saved(folder)["1expired"].read_from == "parse"


def test_retention_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "ARCHIVE_TEXT_RETENTION", False)
    folder = library_of(tmp_path, thread("1expired", read_from="arctic_shift", collected=at(40)))
    assert library.check_live(FakeLiveParse(), folder, max_credits=0, now=NOW).text_removed == []
    assert all(c.status == "ok" for c in saved(folder)["1expired"].comments)


# --- check-live on the command line ---

def test_command_line_check_live_reports_what_it_did(tmp_path, capsys):
    now = datetime.now(UTC)  # the command line uses the real clock
    folder = library_of(
        tmp_path,
        thread("1quoted", collected=at(20, now), now=now),
        thread("1arch", read_from="arctic_shift", collected=at(3, now), now=now),
        thread("1expired", read_from="arctic_shift", collected=at(50, now), now=now),
    )
    client = FakeLiveParse(used=150, fail_on={"1expired"}, now=now)

    assert library.main(["check-live"], client=client, folder=folder, shown={"1quoted"}) == 1  # one failure

    out = capsys.readouterr().out
    assert "Checked live on Reddit through Parse: 2 thread(s): 1quoted, 1arch" in out
    assert "quoted in answers: 1quoted" in out
    assert "Comments gone from the live copies" in out
    assert "Credits: 4 used by this run (cap 30); 46 left this month." in out
    assert "1expired: Parse answered 404" in out
    assert "Text removed" in out and "1expired" in out
    assert out.rstrip().endswith("Parse credits used this month: 154 of 200 (the parse.bot dashboard has the exact figure)")


def test_command_line_check_live_takes_a_credit_cap(tmp_path, capsys):
    now = datetime.now(UTC)
    folder = library_of(tmp_path, *(thread(f"1a{n}", read_from="arctic_shift", collected=at(5 - n, now), now=now) for n in range(3)))
    client = FakeLiveParse(now=now)
    assert library.main(["check-live", "--max-credits", "2"], client=client, folder=folder, shown=set()) == 0
    assert client.fetches == ["1a0"]
    out = capsys.readouterr().out
    assert "Not checked this time (credit cap reached), saved copies unchanged: 1a1, 1a2" in out
    assert library.main(["check-live", "--max-credits=4"], client=FakeLiveParse(now=now), folder=folder, shown=set()) == 0


def test_command_line_check_live_finds_the_quoted_threads_from_the_blind_test(tmp_path, monkeypatch, capsys):
    asked = []
    monkeypatch.setattr(slice_eval, "threads_behind_answers", lambda **kwargs: asked.append(kwargs) or {"1quoted"})
    monkeypatch.setattr(pipeline, "cached_profiles", lambda: "profiles")
    folder = library_of(tmp_path, thread("1quoted", collected=at(20, datetime.now(UTC)), now=datetime.now(UTC)))
    client = FakeLiveParse(now=datetime.now(UTC))
    assert library.main(["check-live"], client=client, folder=folder) == 0
    assert asked == [{"library_dir": folder, "profiles": "profiles"}] and client.fetches == ["1quoted"]


@pytest.mark.parametrize("argv", [
    ["check-live", "--max-credits"], ["check-live", "--max-credits", "lots"], ["check-live", "--max-credits", "-2"],
    ["check-live", "now"], ["check-live", "--fast"],
])
def test_command_line_check_live_explains_itself_when_used_wrongly(tmp_path, capsys, argv):
    client = FakeLiveParse()
    assert library.main(argv, client=client, folder=tmp_path, shown=set()) == 2
    assert "check-live [--max-credits N]" in capsys.readouterr().out and client.fetches == []


# --- add: the archive is the default reader ---

KETTLE = "electric kettle that lasts 10+ years"


def test_add_reads_through_the_archive_by_default_and_through_parse_when_asked(tmp_path, monkeypatch):
    built = []
    # Since 11 Oct 2026 the default ("auto") also builds a Bright Data source, used only if the archive fails: a fake
    # here, so the test can never reach Bright Data (it once did, through the real cache and outage memo).
    from engine.tests.test_bright_data_source import FakeBrightData

    bright = FakeBrightData([])
    monkeypatch.setattr(library, "BrightDataClient", lambda: bright)
    monkeypatch.setattr(library, "ArcticShiftClient", lambda: "an Arctic Shift client")
    monkeypatch.setattr(library, "ArchiveSource", lambda client: built.append(("archive", client)) or FakeArchiveSourceStub())
    monkeypatch.setattr(library, "ParseSource", lambda **kwargs: built.append(("parse", kwargs["finder"])) or FakeArchiveSourceStub())
    library.add(KETTLE, folder=tmp_path)
    library.add(KETTLE, folder=tmp_path, reader="parse")
    assert built == [("archive", "an Arctic Shift client"), ("parse", "an Arctic Shift client")]
    assert bright.searches == [] and bright.read == []  # the archive answered: Bright Data never asked
    library.add("something for my face", folder=tmp_path)  # a request module 1 can't place builds nothing
    assert len(built) == 2


class FakeArchiveSourceStub:
    def find_threads(self, query, limit=3):
        return []


def test_command_line_add_reads_through_the_archive_by_default_for_free(tmp_path, capsys):
    client = FakeParseClient()
    finder = FakeArchiveClient(kettle_posts())
    assert library.main(["add", KETTLE], client=client, folder=tmp_path, finder=finder) == 0
    assert client.fetches == client.searches == []
    assert [read for read, _ in finder.reads] == ["1a1", "1a2", "1a3", "1l1", "1w1", "1w2"]
    assert all(t.read_from == "arctic_shift" for t in saved(tmp_path).values())
    out = capsys.readouterr().out
    assert "Saved 6 threads for electric kettle" in out and "check-live" in out
    assert "Parse credits used this month: 0 of 200" in out


def test_command_line_add_reader_parse_reads_through_parse(tmp_path, capsys):
    from engine.tests.test_library import kettle_client
    from engine.tests.test_library import kettle_posts as parse_kettle_posts
    from engine.tests.test_sources import FakeFinder

    client = kettle_client()
    finder = FakeFinder(parse_kettle_posts())
    assert library.main(["add", "--reader", "parse", KETTLE], client=client, folder=tmp_path, finder=finder) == 0
    assert len(client.fetches) == 6
    assert "Parse credits used this month: 12 of 200" in capsys.readouterr().out
    assert library.main(["add", KETTLE, "--reader=archive"], client=kettle_client(), folder=tmp_path / "2",
                        finder=FakeArchiveClient(kettle_posts())) == 0


@pytest.mark.parametrize("argv", [["add", "--reader", "pushshift", KETTLE], ["add", "--reader", KETTLE], ["add", KETTLE, "--reader"]])
def test_command_line_add_refuses_an_unknown_reader(tmp_path, capsys, argv):
    assert library.main(argv, client=FakeParseClient(), folder=tmp_path, finder=FakeArchiveClient()) == 2
    # Changed on purpose 11 Oct 2026: Bright Data and the automatic fallback are readers too.
    assert "--reader auto|archive|bright_data|parse" in capsys.readouterr().out


def test_an_archive_copy_never_replaces_a_copy_read_live(tmp_path):
    folder = library_of(
        tmp_path,
        thread("1a1", read_from="parse", collected=at(20), checked=at(20)),  # read on Reddit: kept
        thread("1a2", read_from="arctic_shift", collected=at(20)),  # an older archive copy: replaced
    )
    before = (folder / "threads" / "1a1.json").read_bytes()
    result = library.add(KETTLE, ArchiveSource(FakeArchiveClient(kettle_posts())), folder=folder, limit=2, mix=None)
    assert result.thread_ids == ["1a1", "1a2"] and result.kept_live == ["1a1"]
    assert (folder / "threads" / "1a1.json").read_bytes() == before
    assert [c.id for c in saved(folder)["1a2"].comments] == ["1a2c1", "1a2c2"]  # the new archive copy


def test_an_archive_read_error_is_reported_on_the_command_line(tmp_path, capsys):
    finder = FakeArchiveClient(kettle_posts(), fail_read={"1a1"})
    assert library.main(["add", KETTLE], client=FakeParseClient(), folder=tmp_path, finder=finder) == 1
    assert "Arctic Shift answered 500" in capsys.readouterr().out
    assert not (tmp_path / "threads").exists()


# --- Answers only quote threads checked live in the last 14 days ---

TODAY = date(2026, 10, 9)


def restamp(root: Path, thread_id: str, **fields) -> None:
    """Changes fields of a saved thread file (its provenance, its collected_at)."""
    path = root / "threads" / f"{thread_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update(fields)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_threads_read_through_parse_count_as_checked_live_when_collected(tmp_path):
    lib = kettle_library(tmp_path)  # collected on 6 Oct 2026, as older files: no provenance
    on_day_14 = answer_request(REQUEST, library_dir=lib, prices=[], today=date(2026, 10, 20))
    assert sorted(on_day_14.threads_used) == ["1kett01", "1kett02"] and on_day_14.waiting_live_check == []
    on_day_15 = answer_request(REQUEST, library_dir=lib, prices=[], today=date(2026, 10, 21))
    assert on_day_15.threads_used == [] and sorted(on_day_15.waiting_live_check) == ["1kett01", "1kett02"]
    assert on_day_15.answer.picks == []  # nothing quoted from them: the honest "not enough evidence" answer


def test_todays_library_stays_usable_until_14_days_after_it_was_read(tmp_path):
    lib = kettle_library(tmp_path)
    restamp(lib, "1kett01", collected_at="2026-10-07T15:18:53Z")
    restamp(lib, "1kett02", collected_at="2026-10-09T15:26:28Z")
    assert sorted(answer_request(REQUEST, library_dir=lib, prices=[], today=TODAY).threads_used) == ["1kett01", "1kett02"]
    assert answer_request(REQUEST, library_dir=lib, prices=[], today=date(2026, 10, 22)).threads_used == ["1kett02"]
    assert answer_request(REQUEST, library_dir=lib, prices=[], today=date(2026, 10, 24)).threads_used == []


def test_an_archive_thread_waits_for_its_live_check(tmp_path):
    lib = kettle_library(tmp_path)
    restamp(lib, "1kett01", read_from="arctic_shift")
    result = answer_request(REQUEST, library_dir=lib, prices=[], today=TODAY)
    assert result.threads_used == ["1kett02"] and result.waiting_live_check == ["1kett01"]
    assert all(q.comment_id.startswith("k2") for pick in result.answer.picks for q in pick.quotes)
    restamp(lib, "1kett01", read_from="arctic_shift", checked_live_at="2026-10-08T10:00:00Z")
    assert sorted(answer_request(REQUEST, library_dir=lib, prices=[], today=TODAY).threads_used) == ["1kett01", "1kett02"]


def test_a_thread_waiting_for_its_live_check_takes_no_reading_slot(tmp_path):
    lib = kettle_library(tmp_path)
    restamp(lib, "1kett01", read_from="arctic_shift")
    result = answer_request(REQUEST, library_dir=lib, max_threads=1, prices=[], today=TODAY)
    assert result.threads_used == ["1kett02"]


def test_the_requirement_can_be_switched_off_for_an_experiment(tmp_path, monkeypatch):
    lib = kettle_library(tmp_path)
    restamp(lib, "1kett01", read_from="arctic_shift")
    off = answer_request(REQUEST, library_dir=lib, prices=[], today=TODAY, live_check_required=False)
    assert sorted(off.threads_used) == ["1kett01", "1kett02"] and off.waiting_live_check == []
    monkeypatch.setattr(pipeline, "LIVE_CHECK_REQUIRED", False)
    assert sorted(answer_request(REQUEST, library_dir=lib, prices=[], today=TODAY).threads_used) == ["1kett01", "1kett02"]


def test_gold_threads_are_exempt(tmp_path, monkeypatch):
    lib = kettle_library(tmp_path)
    late = date(2027, 1, 1)
    restamp(lib, "1kett01", read_from="gold")
    assert answer_request(REQUEST, library_dir=lib, prices=[], today=late).threads_used == ["1kett01"]
    monkeypatch.setattr(pipeline, "GOLD_DIR", lib)  # the pipeline pointed at the gold set itself
    assert sorted(answer_request(REQUEST, library_dir=lib, prices=[], today=late).threads_used) == ["1kett01", "1kett02"]


def test_without_a_day_given_the_pipeline_uses_todays_date(tmp_path, monkeypatch):
    lib = kettle_library(tmp_path)
    monkeypatch.setattr(pipeline, "_today", lambda: date(2026, 12, 1))
    assert answer_request(REQUEST, library_dir=lib, prices=[]).threads_used == []


def test_the_result_names_the_threads_its_quotes_come_from(tmp_path):
    result = answer_request(REQUEST, library_dir=kettle_library(tmp_path), prices=[], today=TODAY)
    assert sorted(result.threads_quoted) == ["1kett01", "1kett02"]
    quoted = {q.comment_id[:2] for pick in result.answer.picks for q in pick.quotes + pick.downsides}
    quoted |= {q.comment_id[:2] for item in result.answer.skip for q in item.quotes}
    assert quoted == {"k1", "k2"}


# --- The blind test's quoted threads, for check-live ---

def test_the_threads_behind_the_blind_test_answers_include_those_waiting_for_a_check(tmp_path):
    lib = kettle_library(tmp_path)
    restamp(lib, "1kett01", read_from="arctic_shift")
    restamp(lib, "1kett02", collected_at="2026-01-01T00:00:00Z")
    questions = questions_file(tmp_path, [REQUEST, "best laptop for uni"])
    assert threads_behind_answers(questions, lib) == {"1kett01", "1kett02"}


def test_the_end_to_end_score_counts_threads_waiting_for_a_live_check(tmp_path):
    lib = kettle_library(tmp_path)
    restamp(lib, "1kett01", read_from="arctic_shift")
    [result] = score_questions(questions_file(tmp_path, [REQUEST]), lib)
    assert result.waiting_live_check == 1
    lines = slice_lines([result])
    assert lines[0].endswith("; threads waiting for a live check: 1")
    assert lines[1].endswith("; 1 thread waiting for a live check")


def test_an_archive_that_is_down_is_reported_on_the_command_line(tmp_path, capsys):
    finder = FakeArchiveClient(kettle_posts(), fail_search=True)
    assert library.main(["add", KETTLE], client=FakeParseClient(), folder=tmp_path, finder=finder) == 1
    out = capsys.readouterr().out
    assert "Arctic Shift answered 422" in out and "No threads found" not in out
