"""The daily job's plan (14 Oct 2026, the free-tier redesign: `python -m engine.precheck --plan`; engine/read_ahead.py).

The job no longer reads Reddit's embed page itself: billed for its whole run, it spent most of it waiting for Reddit's
allowance. It starts from the bundle the site shares, records in the verification record what each read of a kept
comment said, works out the comments answers would show, and leaves the site a plan: those comments likeliest first,
then the kept comments due to be verified, longest unverified first, within the day's budget; then it verifies through
Bright Data the comments the embed page can't show and adds those checks to the plan. Made-up threads and pages, made-up
Google: no test reaches the network.
"""

import json
from datetime import timedelta

import pytest

from engine import config, precheck
from engine.live_check import BUNDLE_NAME, Bucket, LiveChecker, _entry_name, embed_url
from engine.read_ahead import PLAN_NAME, read_plan
from engine.tests.fake_google import FakeGoogle
from engine.tests.test_live_check import Clock
from engine.tests.test_precheck import REQUEST, library
from engine.tests.test_precheck_bright_data import FakeBrightData, body_of, url_of
from engine.tests.test_slim import ZOJI
from engine.tests.test_verify import day, slimmed_library, thread_of
from engine.verify import LEDGER_NAME, Ledger

BUCKET = "credible-test-checks"


def never_read(url, headers):
    raise AssertionError("the plan run never reads Reddit's embed page")


def a_checker(tmp_path, google, clock, folder="job"):
    bucket = Bucket(BUCKET, request=google, clock=lambda: clock.now.timestamp())
    return LiveChecker(cache_dir=tmp_path / folder / "live_check", fetch=never_read, clock=clock, sleep=clock.sleep,
                       min_interval=0, bucket=bucket)


def site_read(google, clock, reads: dict[str, tuple[timedelta, str | None]]):
    """The bundle as the site shared it: for each comment link, how long ago it was read and what it said."""
    checks = {_entry_name(embed_url(url)): {"fetched_at": (clock.now - ago).isoformat(), "text": text}
              for url, (ago, text) in reads.items()}
    google.put(BUCKET, f"live_check/{BUNDLE_NAME}", json.dumps({"checks": checks}).encode())


def the_plan(google):
    found = google.objects.get((BUCKET, f"live_check/{PLAN_NAME}"))
    return None if found is None else read_plan(found[1])


def plan_run(tmp_path, google, clock, lib, requests=(REQUEST,), bright_data=None, **settings):
    return precheck.plan_run(list(requests), lib, a_checker(tmp_path, google, clock), profiles=None,
                             bright_data=bright_data, **settings)


# --- The answers' comments ---

def test_the_plan_lists_the_answers_comments_likeliest_first_and_the_job_reads_nothing_itself(tmp_path, capsys):
    lib, google, clock = library(tmp_path), FakeGoogle(buckets=(BUCKET,)), Clock()
    assert plan_run(tmp_path, google, clock, lib) == 0
    plan = the_plan(google)
    expected = precheck.comments_to_check([REQUEST], library_dir=lib,
                                          checker=LiveChecker(cache_dir=tmp_path / "empty", fetch=never_read))
    assert plan.answers == tuple(c.url for c in expected) and plan.verify == ()
    assert plan.written_at == clock.now
    assert not google.asked("POST", BUNDLE_NAME)  # the site writes the bundle: the job never does
    said = capsys.readouterr().out
    assert f"Plan for the site: {len(expected):,} answers' comments" in said


def test_a_comment_the_site_found_deleted_drops_out_and_the_next_in_line_is_listed(tmp_path):
    lib, google, clock = library(tmp_path), FakeGoogle(buckets=(BUCKET,)), Clock()
    plan_run(tmp_path, google, clock, lib)
    first = the_plan(google).answers[0]
    site_read(google, clock, {first: (timedelta(hours=3), "[deleted]")})
    plan_run(tmp_path, google, clock, lib)
    assert first not in the_plan(google).answers  # an answer drops it, as it would for a visitor


# --- The kept comments to verify, and the record ---

def test_the_kept_comments_due_are_listed_oldest_first_within_the_budget(tmp_path):
    root = slimmed_library(tmp_path)
    google, clock = FakeGoogle(buckets=(BUCKET,)), Clock()
    clock.now = day(10)
    ledger = Ledger()
    ledger.record("s1kept", day(5), "passing")
    google.put(BUCKET, f"live_check/{LEDGER_NAME}", ledger.dumps(day(5)))
    plan_run(tmp_path, google, clock, root, requests=(), verify_limit=3)
    links = {c.id: c.url for c in thread_of(root).comments}
    assert the_plan(google).verify == (links["s2agree"], links["s4source"], links["s5reply"])  # s1kept isn't due


def test_the_reads_the_site_shared_are_recorded_a_page_with_no_comment_too(tmp_path):
    root = slimmed_library(tmp_path)
    google, clock = FakeGoogle(buckets=(BUCKET,)), Clock()
    clock.now = day(10)
    links = {c.id: c.url for c in thread_of(root).comments}
    site_read(google, clock, {links["s1kept"]: (timedelta(hours=2), ZOJI),
                              links["s2agree"]: (timedelta(hours=30), None)})  # older than an unreadable check is used
    plan_run(tmp_path, google, clock, root, requests=())
    record = Ledger.loads(google.objects[(BUCKET, f"live_check/{LEDGER_NAME}")][1])
    assert record.get("s1kept").passed == day(10) - timedelta(hours=2)
    assert record.get("s2agree").outcome == "unreadable"  # tried again only after LIBRARY_VERIFY_RETRY_DAYS
    verify = the_plan(google).verify
    assert links["s1kept"] not in verify and links["s2agree"] not in verify and links["s4source"] in verify
    assert (tmp_path / "job" / LEDGER_NAME).is_file()  # kept on the machine that ran it too


def test_a_kept_comment_among_the_answers_is_listed_once(tmp_path):
    root = slimmed_library(tmp_path)
    google, clock = FakeGoogle(buckets=(BUCKET,)), Clock()
    clock.now = day(10)
    plan_run(tmp_path, google, clock, root, requests=("electric kettle",))
    plan = the_plan(google)
    assert plan.answers and not set(plan.answers) & set(plan.verify)


# --- Bright Data, after the plan is written ---

def test_the_plan_is_written_before_bright_data_reads_and_again_with_its_checks(tmp_path):
    lib, google, clock = library(tmp_path), FakeGoogle(buckets=(BUCKET,)), Clock()
    leader = "z1aaaa"
    site_read(google, clock, {url_of(leader): (timedelta(hours=30), None)})  # the embed page showed no comment

    class Watching(FakeBrightData):
        def prefetch(self, threads, batch=config.BRIGHT_DATA_BATCH_THREADS):
            assert the_plan(google) is not None  # the site has its plan whatever Bright Data does
            return super().prefetch(threads, batch)

    bright = Watching(clock)
    plan_run(tmp_path, google, clock, lib, bright_data=lambda: bright)
    checks = the_plan(google).checks
    assert [entry["text"] for entry in checks.values()] == [body_of(leader)]
    assert all(entry["via"] == "bright_data" for entry in checks.values())


def test_no_bright_data_read_starts_after_the_runs_minutes(tmp_path):
    lib, google, clock = library(tmp_path), FakeGoogle(buckets=(BUCKET,)), Clock()
    site_read(google, clock, {url_of("z1aaaa"): (timedelta(hours=1), None), url_of("z2aaaa"): (timedelta(hours=1), None)})

    class Slow(FakeBrightData):
        def get_thread(self, link):
            clock.now += timedelta(minutes=40)  # Bright Data takes its time
            return super().get_thread(link)

    bright = Slow(clock)
    plan_run(tmp_path, google, clock, lib, bright_data=lambda: bright, minutes=30)
    assert len(bright.read) == 1  # the second thread would start after the run's 30 minutes


def test_with_bright_data_off_the_plan_is_written_and_one_line_says_so(tmp_path, capsys):
    lib, google, clock = library(tmp_path), FakeGoogle(buckets=(BUCKET,)), Clock()
    site_read(google, clock, {url_of("z1aaaa"): (timedelta(hours=1), None)})
    plan_run(tmp_path, google, clock, lib, bright_data=None)
    assert the_plan(google) is not None
    lines = [line for line in capsys.readouterr().out.splitlines() if "Bright Data" in line]
    assert len(lines) == 1 and lines[0].startswith("Bright Data: off")


# --- Dry runs and the command ---

def test_a_dry_run_writes_nothing(tmp_path, capsys):
    root = slimmed_library(tmp_path)
    google, clock = FakeGoogle(buckets=(BUCKET,)), Clock()
    clock.now = day(10)
    plan_run(tmp_path, google, clock, root, requests=("electric kettle",), dry_run=True)
    assert not google.asked("POST")
    assert "Plan for the site (dry run)" in capsys.readouterr().out


def test_the_plan_needs_the_bucket(tmp_path, capsys):
    lib = library(tmp_path)
    checker = LiveChecker(cache_dir=tmp_path / "cache", fetch=never_read)
    assert precheck.plan_run([REQUEST], lib, checker, profiles=None, bright_data=None) == 2
    assert "bucket" in capsys.readouterr().err


def test_the_command_runs_the_plan_within_its_minutes(monkeypatch):
    given = {}
    monkeypatch.setattr(precheck, "requests_to_check", lambda: [REQUEST])
    monkeypatch.setattr(precheck.pipeline, "cached_profiles", lambda: None)
    monkeypatch.setattr(precheck, "plan_run", lambda requests, library_dir, checker, profiles, **settings:
                        given.update(settings, requests=requests) or 0)
    monkeypatch.setattr(precheck, "run", lambda *args, **kwargs: pytest.fail("the plan run reads nothing itself"))
    assert precheck.main(["--plan"]) == 0 and given["minutes"] == config.PRECHECK_PLAN_MINUTES
    assert given["requests"] == [REQUEST] and given["dry_run"] is False
    assert precheck.main(["--plan", "--minutes", "20", "--dry-run"]) == 0 and given["minutes"] == 20
    assert given["dry_run"] is True
    assert precheck.main(["--plan", "--bogus"]) == 2


def test_the_job_never_takes_more_than_a_small_share_of_the_jobs_free_tier():
    # The plan run's worst month: its task timeout (deploy.sh) every day, with on-demand reading's cap
    # (engine/tests/test_cloudrun.py does the sums from deploy.sh's own settings).
    assert config.PRECHECK_PLAN_MINUTES < 45
