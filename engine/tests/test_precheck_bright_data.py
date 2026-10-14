"""Comments the embed page can't show, verified through Bright Data by the daily pre-check (Noemi, 13 Oct 2026: "Use
Bright Data").

For about 1 comment in 8, Reddit's embed page shows no comment ("Not supported comment"), so it is kept as unreadable
and never shown, and the picks it backs can fall. After its embed reads, the pre-check reads those comments' threads
through Bright Data (as Reddit shows them now), within a budget of records a run, likeliest to be shown first, and
saves a normal check for each comment it finds. One it doesn't find stays unreadable: Bright Data returns top-level
comments and their direct replies only, so missing never means deleted. The site never calls Bright Data.

Every Reddit page and every Bright Data answer here is made up: no test reaches the network.
"""

import ast
import json
from datetime import timedelta
from pathlib import Path

from engine import config, precheck
from engine.answer import _every_quote
from engine.bright_data import BrightDataError
from engine.live_check import LiveChecker, LiveResult
from engine.models import Thread
from engine.pipeline import answer_request
from engine.tests.factories import make_comment, make_thread
from engine.tests.test_live_check import Clock
from engine.tests.test_precheck import COMMENTS, REQUEST, FakeReddit, library

NOT_SUPPORTED = b"<html><body><p>Not supported comment</p></body></html>"  # the shell: no comment on the page


class EmbedPage(FakeReddit):
    """The made-up embed pages, with a shell and no comment on it for the comments in `unsupported`."""

    def __init__(self, unsupported=(), **kwargs):
        super().__init__(**kwargs)
        self.unsupported = set(unsupported)

    def __call__(self, url, headers):
        comment_id = url.split("/comment/")[1].split("/")[0]
        if comment_id in self.unsupported:
            self.asked.append(comment_id)
            return 200, NOT_SUPPORTED
        return super().__call__(url, headers)


class FakeBrightData:
    """Stands in for engine.bright_data.BrightDataClient: each thread as Reddit shows it now, from the made-up comments
    (`now` changes a comment's text: "[deleted]", an edit; `missing` leaves it out, as a reply too deep would be)."""

    def __init__(self, clock, now=None, missing=(), fails=None):
        self.clock, self.now, self.missing, self.fails = clock, dict(now or {}), set(missing), fails
        self.prefetched: list[list[tuple[str, int]]] = []
        self.read: list[str] = []
        self.records = 0

    def prefetch(self, threads, batch=config.BRIGHT_DATA_BATCH_THREADS):
        self.prefetched.append(list(threads))
        if self.fails is not None:
            raise self.fails
        return len(threads)

    def get_thread(self, link):
        if self.fails is not None:
            raise self.fails
        thread_id = link.split("/comments/")[1].split("/")[0]
        self.read.append(thread_id)
        comments = []
        for cid, tid, _, _, body in COMMENTS:
            if tid != thread_id or cid in self.missing:
                continue
            text = self.now.get(cid, body)
            status = {"[deleted]": "deleted", "[removed]": "removed"}.get(text, "ok")
            comments.append(make_comment(cid, thread_id=tid, body=text, status=status,
                                         url=f"https://www.reddit.com/r/BuyItForLife/comments/{tid}/comment/{cid}/"))
        self.records += 1 + len(comments)
        return Thread.model_validate(make_thread(
            id=thread_id, community="BuyItForLife", category="kitchen", title="Which electric kettle lasts?",
            url=f"https://www.reddit.com/r/BuyItForLife/comments/{thread_id}/kettle/", comments=comments,
            collected_at=self.clock.now.isoformat(), read_from="bright_data", checked_live_at=self.clock.now.isoformat()))

    def records_used_this_month(self):
        return self.records


def live_checker(tmp_path, reddit, clock):
    return LiveChecker(cache_dir=tmp_path / "cache", fetch=reddit, clock=clock, sleep=clock.sleep, min_interval=0)


def url_of(comment_id: str) -> str:
    thread = next(tid for cid, tid, *_ in COMMENTS if cid == comment_id)
    return f"https://www.reddit.com/r/BuyItForLife/comments/{thread}/comment/{comment_id}/"


def body_of(comment_id: str) -> str:
    return next(body for cid, *_, body in COMMENTS if cid == comment_id)


def pick_comment(lib) -> str:
    """The first pick's first quoted comment, when every check passes."""

    class AllPass:
        def check(self, url, quote, wait=True):
            return LiveResult("ok", "passes")

    return answer_request(REQUEST, library_dir=lib, live_checker=AllPass()).answer.picks[0].quotes[0].comment_id


def a_run(tmp_path, lib, reddit, bright_data, clock, dry_run=False, **budget):
    return precheck.run([REQUEST], limit=100, dry_run=dry_run, library_dir=lib,
                        checker=live_checker(tmp_path, reddit, clock), profiles=None,
                        bright_data=lambda: bright_data, **budget)


# --- What it verifies, and how ---

def test_a_comment_the_embed_page_cant_show_is_verified_through_bright_data_and_shown_again(tmp_path, capsys):
    lib = library(tmp_path)
    leader = pick_comment(lib)
    clock = Clock()
    reddit, bright_data = EmbedPage(unsupported={leader}), FakeBrightData(clock)
    a_run(tmp_path, lib, reddit, bright_data, clock)
    assert len(bright_data.prefetched) == 1 and len(bright_data.prefetched[0]) == 1  # its one thread, in one batch
    live = live_checker(tmp_path, EmbedPage(unsupported={leader}), clock)
    entry = live.saved_entry(url_of(leader))
    assert entry["text"] == body_of(leader) and entry["via"] == "bright_data"
    assert entry["fetched_at"] == clock.now.isoformat()  # when Bright Data read it
    shown = {q.comment_id for _, q in _every_quote(answer_request(REQUEST, library_dir=lib, live_checker=live).answer)}
    assert leader in shown  # an answer shows it again, without reading Reddit for it
    said = capsys.readouterr().out
    assert "Bright Data: 1 comment" in said and "1 thread read" in said and "1 passing" in said


def test_a_comment_missing_from_bright_datas_answer_stays_unverified_and_unshown(tmp_path):
    lib = library(tmp_path)
    leader = pick_comment(lib)
    clock = Clock()
    a_run(tmp_path, lib, EmbedPage(unsupported={leader}), FakeBrightData(clock, missing={leader}), clock)
    live = live_checker(tmp_path, EmbedPage(unsupported={leader}), clock)
    assert live.saved_entry(url_of(leader))["text"] is None  # still unreadable: missing isn't deleted, nor checked
    shown = {q.comment_id for _, q in _every_quote(answer_request(REQUEST, library_dir=lib, live_checker=live).answer)}
    assert leader not in shown


def test_a_comment_bright_data_finds_deleted_or_edited_is_saved_as_such(tmp_path):
    lib = library(tmp_path)
    clock = Clock()
    gone, edited = "z1aaaa", "d1aaaa"
    bright_data = FakeBrightData(clock, now={gone: "[deleted]", edited: "I gave it away, it broke."})
    a_run(tmp_path, lib, EmbedPage(unsupported={gone, edited}), bright_data, clock)
    live = live_checker(tmp_path, EmbedPage(), clock)
    assert live.saved_check(url_of(gone), body_of(gone)).status == "gone"
    assert live.saved_check(url_of(edited), body_of(edited)).status == "changed"


def test_only_the_comments_own_text_is_kept(tmp_path):
    lib = library(tmp_path)
    leader = pick_comment(lib)
    clock = Clock()
    a_run(tmp_path, lib, EmbedPage(unsupported={leader}), FakeBrightData(clock), clock)
    saved = [json.loads(p.read_text()) for p in (tmp_path / "cache").glob("*.json")]
    assert all(set(entry) <= {"fetched_at", "text", "via"} for entry in saved)
    # Of the thread Bright Data read, only the comment that needed it: never the post or the other comments.
    assert [entry["text"] for entry in saved if entry.get("via") == "bright_data"] == [body_of(leader)]


# --- Within its budget, likeliest first ---

def test_threads_are_read_likeliest_first_within_the_runs_records(tmp_path, capsys):
    lib = library(tmp_path)
    clock = Clock()
    first, second = "z1aaaa", "z2aaaa"  # in 1kett01 (10 records: the post, 9 comments) and 1kett02 (11)
    bright_data = FakeBrightData(clock)
    a_run(tmp_path, lib, EmbedPage(unsupported={first, second}), bright_data, clock, bright_data_records=12)
    assert len(bright_data.read) == 1  # only one thread fits in 12 records
    said = capsys.readouterr().out
    assert "1 left for this run's budget" in said


def test_a_comment_verified_through_bright_data_is_read_again_only_after_40_hours(tmp_path):
    lib = library(tmp_path)
    leader = pick_comment(lib)
    clock = Clock()
    reddit, bright_data = EmbedPage(unsupported={leader}), FakeBrightData(clock)
    a_run(tmp_path, lib, reddit, bright_data, clock)
    clock.now += timedelta(hours=24)  # the next day: its check is 24 hours old
    reddit.asked.clear()
    a_run(tmp_path, lib, reddit, bright_data, clock)
    assert leader not in reddit.asked and len(bright_data.read) == 1  # neither the embed page nor Bright Data again
    clock.now += timedelta(hours=config.PRECHECK_BRIGHT_DATA_FRESH_HOURS - 24 + 1)
    a_run(tmp_path, lib, reddit, bright_data, clock)
    assert len(bright_data.read) == 2 and leader not in reddit.asked  # read again through Bright Data


def test_a_bright_data_check_lasts_48_hours_and_goes_into_the_bundle(tmp_path):
    from engine.live_check import Bucket
    from engine.tests.test_live_check_bucket import FakeGoogle

    lib = library(tmp_path)
    leader = pick_comment(lib)
    clock, google = Clock(), FakeGoogle()
    checker = LiveChecker(cache_dir=tmp_path / "job", fetch=EmbedPage(unsupported={leader}), clock=clock,
                          sleep=clock.sleep, min_interval=0,
                          bucket=Bucket(google.bucket, request=google, clock=lambda: clock.now.timestamp()))
    precheck.run([REQUEST], limit=100, dry_run=False, library_dir=lib, checker=checker, profiles=None,
                 bright_data=lambda: FakeBrightData(clock))
    bundled = [entry for entry in google.bundle()["checks"].values() if entry.get("via") == "bright_data"]
    assert [entry["text"] for entry in bundled] == [body_of(leader)]
    clock.now += timedelta(hours=48, minutes=1)
    assert checker.saved_entry(url_of(leader)) is None and checker.saved_check(url_of(leader), "lasted") is None


# --- Dry runs, problems, and the site ---

def test_a_dry_run_counts_the_comments_threads_and_records_without_calling_bright_data(tmp_path, capsys):
    lib = library(tmp_path)
    clock = Clock()
    reddit = EmbedPage(unsupported={"z1aaaa", "z2aaaa", "d1aaaa"})
    a_run(tmp_path, lib, reddit, None, clock)  # reads the embed pages, so their checks are saved as unreadable
    capsys.readouterr()

    def refuse():
        raise AssertionError("a dry run never builds a Bright Data client")

    precheck.run([REQUEST], limit=100, dry_run=True, library_dir=lib, checker=live_checker(tmp_path, reddit, clock),
                 profiles=None, bright_data=refuse)
    said = capsys.readouterr().out
    assert "Bright Data (dry run): 3 comments the embed page can't show, in 2 threads" in said
    assert "would read 2 threads, about 21 records" in said


def test_an_account_problem_stops_the_bright_data_reads_and_the_run_still_finishes(tmp_path, capsys):
    lib = library(tmp_path)
    clock = Clock()
    problem = BrightDataError("No Bright Data key. Add a line BRIGHT_DATA_API_KEY=...", account_problem=True)
    status = a_run(tmp_path, lib, EmbedPage(unsupported={"z1aaaa"}), FakeBrightData(clock, fails=problem), clock)
    said = capsys.readouterr().out
    assert status == 0 and "Bright Data stopped" in said and "No Bright Data key" in said


def test_the_site_never_calls_bright_data():
    # Only the pre-check does (Noemi, 13 Oct 2026): nothing the site runs imports the Bright Data client.
    root = Path(__file__).resolve().parents[1]
    for module in ("web.py", "live_check.py", "pipeline.py", "answer.py"):
        tree = ast.parse((root / module).read_text(encoding="utf-8"))
        imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        imported |= {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
        assert "engine.bright_data" not in imported, module


def test_the_budget_keeps_a_month_well_within_bright_datas_free_records():
    # A run at most PRECHECK_BRIGHT_DATA_RECORDS records, once a day: under a quarter of the month's free records,
    # leaving the rest to the library's own reads.
    assert config.PRECHECK_BRIGHT_DATA_RECORDS * 31 <= config.BRIGHT_DATA_MONTHLY_RECORDS / 4
    assert config.PRECHECK_BRIGHT_DATA_MAX_THREADS <= config.BRIGHT_DATA_BATCH_THREADS  # one batch a run at most
    assert config.PRECHECK_FRESH_HOURS < config.PRECHECK_BRIGHT_DATA_FRESH_HOURS < config.CACHE_MAX_AGE_HOURS


def test_among_threads_of_equally_likely_comments_the_one_verifying_most_for_its_records_comes_first(tmp_path):
    lib = library(tmp_path)
    clock = Clock()
    # Both threads hold shown comments; 1kett02 (11 records) holds three needing Bright Data, 1kett01 (10) one.
    needing = {"z1aaaa", "d2aaaa", "b2aaaa", "z2aaaa"}
    bright_data = FakeBrightData(clock)
    a_run(tmp_path, lib, EmbedPage(unsupported=needing), bright_data, clock, bright_data_records=12)
    assert bright_data.read == ["1kett02"]


# --- Off when deployed without the key (14 Oct 2026, the orchestrator: a missing key never stops a deploy) ---

def test_with_the_step_off_nothing_is_read_through_bright_data_and_one_line_says_so(tmp_path, capsys):
    lib = library(tmp_path)
    clock = Clock()
    status = precheck.run([REQUEST], limit=100, dry_run=False, library_dir=lib,
                          checker=live_checker(tmp_path, EmbedPage(unsupported={"z1aaaa"}), clock), profiles=None,
                          bright_data=None)
    lines = [line for line in capsys.readouterr().out.splitlines() if "Bright Data" in line]
    assert status == 0 and len(lines) == 1 and lines[0].startswith("Bright Data: off")
    assert "1 comment the embed page can't show, in 1 thread" in lines[0]  # still counted: what waits for it
    entry = live_checker(tmp_path, EmbedPage(), clock).saved_entry(url_of("z1aaaa"))
    assert entry["text"] is None and "via" not in entry  # still unreadable, so never shown


def test_the_job_turns_the_step_off_only_when_deployed_without_the_key():
    assert precheck.bright_data_from_env({"CREDIBLE_RECS_PRECHECK_BRIGHT_DATA": "off"}) is None
    for environ in ({}, {"CREDIBLE_RECS_PRECHECK_BRIGHT_DATA": "on"}):
        assert precheck.bright_data_from_env(environ) is precheck._bright_data_client
