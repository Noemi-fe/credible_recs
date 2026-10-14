"""Threads Bright Data can't read (14 Oct 2026, the coordinator: both of the day's plan runs failed on the same two
threads and read no other, since each run on Google Cloud starts with an empty disk and chose the same threads again).

The daily job now remembers, in the bucket beside the plan (live_check/bright_data.json), the threads Bright Data
couldn't read lately: when, Bright Data's status and error, and whether the post itself is gone. A thread that failed is
left for config.PRECHECK_BRIGHT_DATA_SKIP_DAYS, so the run's records go to the next threads; one whose post is gone
(removed, deleted, its page no longer there) holds comments that can't be verified that way, so they are taken as
unverifiable for config.PRECHECK_BRIGHT_DATA_GONE_DAYS without a record spent on them again, and the plan shows what
answers show instead. The report says why each thread couldn't be read, in Bright Data's words, never a comment's.
Made-up threads, pages and Google: no test reaches the network.
"""

import json
from datetime import timedelta

from engine import config, precheck
from engine.bright_data import BrightDataError
from engine.live_check import BUNDLE_NAME, Bucket, LiveChecker, _entry_name, embed_url
from engine.read_ahead import PLAN_NAME, read_plan
from engine.tests.fake_google import FakeGoogle
from engine.tests.test_live_check import Clock
from engine.tests.test_precheck import COMMENTS, REQUEST, library
from engine.tests.test_precheck_bright_data import EmbedPage, FakeBrightData, live_checker, url_of

BUCKET = "credible-test-checks"
MEMORY = f"live_check/{precheck.BRIGHT_DATA_MEMORY_NAME}"


def failed(error="crawl_failed: Crawl failed, try later"):
    return BrightDataError("Bright Data's comments job failed", status="failed", error=error)


def gone(error="dead_page: Page not reachable"):
    return BrightDataError("Bright Data couldn't read the comments", status="ready", error=error, post_gone=True)


def unreadable_bundle(google, clock, comment_ids, hours_ago=2):
    """The bundle as the site shared it: these comments' embed pages showed no comment, `hours_ago`."""
    checks = {_entry_name(embed_url(url_of(cid))): {"fetched_at": (clock.now - timedelta(hours=hours_ago)).isoformat(),
                                                   "text": None} for cid in comment_ids}
    google.put(BUCKET, f"live_check/{BUNDLE_NAME}", json.dumps({"checks": checks}).encode())


def a_plan_run(tmp_path, google, clock, lib, bright, folder, **settings):
    """One daily run on Google Cloud: a machine whose disk starts empty (`folder`), the bucket shared."""
    def never_read(url, headers):
        raise AssertionError("the plan run never reads the embed page")

    checker = LiveChecker(cache_dir=tmp_path / folder / "live_check", fetch=never_read, clock=clock, sleep=clock.sleep,
                          min_interval=0, bucket=Bucket(BUCKET, request=google, clock=lambda: clock.now.timestamp()))
    return precheck.plan_run([REQUEST], lib, checker, profiles=None, bright_data=lambda: bright, **settings)


def the_memory(google) -> dict:
    found = google.objects.get((BUCKET, MEMORY))
    return {} if found is None else json.loads(found[1])["threads"]


# --- Why ---

def test_why_each_thread_couldnt_be_read_is_reported_in_bright_datas_words(tmp_path, capsys):
    lib, clock = library(tmp_path), Clock()
    bright = FakeBrightData(clock, fails_for={"1kett01": failed(), "1kett02": gone()})
    precheck.run([REQUEST], limit=100, dry_run=False, library_dir=lib,
                 checker=live_checker(tmp_path, EmbedPage(unsupported={"z1aaaa", "z2aaaa"}), clock), profiles=None,
                 bright_data=lambda: bright)
    said = capsys.readouterr().out
    assert "2 couldn't be read" in said
    assert "1kett01 (failed: crawl_failed: Crawl failed, try later; asked again in 7 days)" in said
    assert "1kett02 (ready: dead_page: Page not reachable; its post is gone:" in said
    assert not any(body in said for *_, body in COMMENTS)  # never a comment's words


def test_a_batch_bright_data_couldnt_read_is_reported_and_each_thread_asked_on_its_own(tmp_path, capsys):
    lib, clock = library(tmp_path), Clock()
    bright = FakeBrightData(clock, batch_fails=BrightDataError("the batch failed", status="failed",
                                                               error="Crawl failed"))
    precheck.run([REQUEST], limit=100, dry_run=False, library_dir=lib,
                 checker=live_checker(tmp_path, EmbedPage(unsupported={"z1aaaa"}), clock), profiles=None,
                 bright_data=lambda: bright)
    said = capsys.readouterr().out
    assert "The batch couldn't be read (failed: Crawl failed): each thread was asked on its own." in said
    assert bright.read == ["1kett01"]


# --- Remembered across runs, in the bucket ---

def test_a_thread_that_failed_is_left_for_a_week_so_the_budget_moves_on(tmp_path):
    lib, google, clock = library(tmp_path), FakeGoogle(buckets=(BUCKET,)), Clock()
    unreadable_bundle(google, clock, ["z1aaaa", "z2aaaa"])  # in 1kett01 (10 records) and 1kett02 (11)
    probe = FakeBrightData(clock)
    a_plan_run(tmp_path, google, clock, lib, probe, "probe", bright_data_records=12, dry_run=True)
    a_plan_run(tmp_path, google, clock, lib, probe, "probe", bright_data_records=12)
    (chosen,) = probe.asked  # the one thread 12 records reach
    other = ({"1kett01", "1kett02"} - {chosen}).pop()
    bright = FakeBrightData(clock, fails_for={chosen: failed()})
    for name in ("live_check/" + PLAN_NAME, MEMORY):
        google.objects.pop((BUCKET, name), None)
    unreadable_bundle(google, clock, ["z1aaaa", "z2aaaa"])  # the probe's reads gone too: the scene as it was
    a_plan_run(tmp_path, google, clock, lib, bright, "day 1", bright_data_records=12)
    assert bright.asked == [chosen] and set(the_memory(google)) == {chosen}
    clock.now += timedelta(days=1)
    unreadable_bundle(google, clock, ["z1aaaa", "z2aaaa"])
    a_plan_run(tmp_path, google, clock, lib, bright, "day 2", bright_data_records=12)  # an empty disk again
    assert bright.asked == [chosen, other]  # the budget went to the next thread
    clock.now += timedelta(days=config.PRECHECK_BRIGHT_DATA_SKIP_DAYS)
    unreadable_bundle(google, clock, ["z1aaaa", "z2aaaa"])
    a_plan_run(tmp_path, google, clock, lib, bright, "a week on", bright_data_records=12)
    assert bright.asked[-1] == chosen  # asked again a week after it failed


def test_a_run_on_this_computer_remembers_them_next_to_its_checks(tmp_path):
    lib, clock = library(tmp_path), Clock()
    reddit = EmbedPage(unsupported={"z1aaaa", "z2aaaa"})
    bright = FakeBrightData(clock, fails_for={"1kett01": failed(), "1kett02": failed()})
    for _ in range(2):
        precheck.run([REQUEST], limit=100, dry_run=False, library_dir=lib, checker=live_checker(tmp_path, reddit, clock),
                     profiles=None, bright_data=lambda: bright)
        clock.now += timedelta(hours=30)
    assert sorted(bright.asked) == ["1kett01", "1kett02"]  # each asked once: the second run left them
    assert (tmp_path / precheck.BRIGHT_DATA_MEMORY_NAME).is_file()


# --- A post that is gone ---

def test_a_gone_posts_comments_are_unverifiable_and_cost_no_records_again(tmp_path):
    lib, google, clock = library(tmp_path), FakeGoogle(buckets=(BUCKET,)), Clock()
    unreadable_bundle(google, clock, ["z1aaaa"])
    bright = FakeBrightData(clock, fails_for={"1kett01": gone()})
    a_plan_run(tmp_path, google, clock, lib, bright, "day 1")
    remembered = the_memory(google)["1kett01"]
    assert remembered["gone"] and remembered["comments"] == ["z1aaaa"]
    assert url_of("z1aaaa") in read_plan(google.objects[(BUCKET, f"live_check/{PLAN_NAME}")][1]).answers
    clock.now += timedelta(days=1)
    unreadable_bundle(google, clock, ["z1aaaa"])
    records = bright.records
    a_plan_run(tmp_path, google, clock, lib, bright, "day 2")
    assert bright.asked == ["1kett01"] and bright.records == records  # not asked again: no record spent
    plan = read_plan(google.objects[(BUCKET, f"live_check/{PLAN_NAME}")][1])
    assert url_of("z1aaaa") not in plan.answers  # it can't be shown, so the plan reads what answers show instead
    clock.now += timedelta(days=config.PRECHECK_BRIGHT_DATA_GONE_DAYS)
    unreadable_bundle(google, clock, ["z1aaaa"])
    a_plan_run(tmp_path, google, clock, lib, bright, "a month on")
    assert bright.asked == ["1kett01", "1kett01"]  # forgotten after its days: asked once more


def test_a_readable_comment_of_a_gone_post_is_still_shown(tmp_path):
    # Only the comments that needed Bright Data are unverifiable: another comment of the thread is read on the embed
    # page as before, and shown when it passes.
    lib, google, clock = library(tmp_path), FakeGoogle(buckets=(BUCKET,)), Clock()
    unreadable_bundle(google, clock, ["z1aaaa"])
    a_plan_run(tmp_path, google, clock, lib, FakeBrightData(clock, fails_for={"1kett01": gone()}), "day 1")
    plan = read_plan(google.objects[(BUCKET, f"live_check/{PLAN_NAME}")][1])
    others = [cid for cid, tid, *_ in COMMENTS if tid == "1kett01" and cid != "z1aaaa"]
    assert any(url_of(cid) in plan.answers for cid in others)


# --- Small, and only what it needs ---

def test_the_memory_holds_ids_dates_and_bright_datas_words_only_and_stays_small(tmp_path):
    clock = Clock()
    memory = precheck.BrightDataMemory()
    for n in range(100):
        memory.record(f"1t{n:05d}", clock.now, failed("x" * 400) if n % 2 else gone(), comments=("c1aaaa", "c2bbbb"))
    data = memory.dumps(clock.now)
    assert len(data) < 25_000
    entries = json.loads(data)["threads"]
    assert all(set(entry) <= {"at", "gone", "status", "error", "comments"} for entry in entries.values())
    assert all(len(entry["error"]) <= 100 for entry in entries.values())
    memory.prune(clock.now + timedelta(days=config.PRECHECK_BRIGHT_DATA_SKIP_DAYS))
    assert len(memory.entries) == 50 and all(entry.gone for entry in memory.entries.values())  # the failures go first
    memory.prune(clock.now + timedelta(days=config.PRECHECK_BRIGHT_DATA_GONE_DAYS))
    assert memory.entries == {}
    assert precheck.BrightDataMemory.loads(b"not json").entries == {}
    assert precheck.BrightDataMemory.loads(json.dumps({"threads": {"../x": {"at": "now"}}})).entries == {}


def test_a_dry_run_and_a_run_with_the_step_off_write_nothing_of_it(tmp_path):
    lib, google, clock = library(tmp_path), FakeGoogle(buckets=(BUCKET,)), Clock()
    unreadable_bundle(google, clock, ["z1aaaa"])
    a_plan_run(tmp_path, google, clock, lib, FakeBrightData(clock, fails_for={"1kett01": failed()}), "dry",
               dry_run=True)
    assert (BUCKET, MEMORY) not in google.objects


def test_the_records_stay_within_their_sums_and_a_failure_costs_nothing_more_for_days():
    # A run reads at most PRECHECK_BRIGHT_DATA_RECORDS records, every day of a 31-day month: under a fifth of Bright
    # Data's free 5,000 (engine/tests/test_cloudrun.py has the jobs' free-tier sums). A thread that failed waits a week;
    # a gone post's comments wait as long as a kept comment may go unverified.
    assert 31 * config.PRECHECK_BRIGHT_DATA_RECORDS <= config.BRIGHT_DATA_MONTHLY_RECORDS / 5
    assert config.PRECHECK_BRIGHT_DATA_SKIP_DAYS >= 7
    assert config.PRECHECK_BRIGHT_DATA_GONE_DAYS >= config.LIBRARY_VERIFY_DAYS
