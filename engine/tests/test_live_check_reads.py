"""What the live checker knows of each read, for the site's reads ahead (14 Oct 2026, the free-tier redesign;
engine/read_ahead.py).

The site now reads ahead at Cloud Scheduler's keep-warm ping and shares what it read through the bucket's bundle; the
daily job starts from that bundle and records what each read of a kept comment said (engine/verify.py). So a read that
found no comment on its page is known for 48 hours, like any read, though it is used for 20 only (an answer reads such a
page again sooner); a read ahead never waits for Reddit; the reads left in Reddit's 10 minutes can be asked; and the
site writes the bundle only over the version it last read or wrote. Every page and every Google answer here is made up:
no test reaches the network.
"""

import json
from datetime import timedelta

from engine.config import LIVE_CHECK_UNREADABLE_KEEP_HOURS
from engine.live_check import BUNDLE_NAME, Bucket, LiveChecker, _entry_name, embed_url
from engine.tests.fake_google import FakeGoogle
from engine.tests.test_live_check import QUOTE, URL, Clock, FakeReddit, page
from engine.tests.test_live_check_pace import CountingReddit

BUCKET = "credible-test-checks"
OTHER = URL.replace("c1aaaa", "c2bbbb")
NO_COMMENT = (200, b"<html>a page with no comment on it</html>")


def checker(tmp_path, reddit, clock, google=None, folder="here", **settings):
    bucket = None if google is None else Bucket(BUCKET, request=google, clock=lambda: clock.now.timestamp())
    return LiveChecker(cache_dir=tmp_path / folder, fetch=reddit, clock=clock, sleep=clock.sleep, min_interval=0,
                       bucket=bucket, **settings)


def bundle(google) -> dict:
    return google.read(BUCKET, f"live_check/{BUNDLE_NAME}")


# --- Every read is known for 48 hours ---

def test_a_read_that_found_no_comment_is_known_for_48_hours_and_used_for_20(tmp_path):
    clock = Clock()
    live = checker(tmp_path, FakeReddit(answer=NO_COMMENT), clock)
    assert live.check(URL, QUOTE).status == "unknown"
    read_at = clock.now
    clock.now += timedelta(hours=LIVE_CHECK_UNREADABLE_KEEP_HOURS + 10)
    assert live.saved_check(URL, QUOTE) is None and live.checked_at(URL) is None  # an answer reads it again
    assert live.last_read(URL) == (read_at, None, None)  # but the read is known: when, and that it found nothing
    clock.now += timedelta(hours=48 - LIVE_CHECK_UNREADABLE_KEEP_HOURS - 10, minutes=1)
    assert live.last_read(URL) is None


def test_a_read_is_known_with_its_text_and_how_it_was_made(tmp_path):
    clock = Clock()
    live = checker(tmp_path, FakeReddit(), clock)
    live.check(URL, QUOTE)
    at, text, via = live.last_read(URL)
    assert (at, via) == (clock.now, None) and QUOTE in text
    live.keep_check(OTHER, "Mine still works.", clock.now - timedelta(hours=1), "bright_data")
    assert live.last_read(OTHER) == (clock.now - timedelta(hours=1), "Mine still works.", "bright_data")
    assert live.last_read(URL.replace("c1aaaa", "c9zzzz")) is None  # never read


def test_the_bundle_carries_a_read_that_found_no_comment_for_48_hours(tmp_path):
    # Changed on purpose, 14 Oct 2026: such a read was left out of the bundle once 20 hours old. The daily job now starts
    # from the bundle the site writes, up to a day after the site's reads, and records each read of a kept comment.
    google, clock = FakeGoogle(buckets=(BUCKET,)), Clock()
    site = checker(tmp_path, FakeReddit(answer=NO_COMMENT), clock, google, folder="site")
    site.check(URL, QUOTE)
    clock.now += timedelta(hours=30)
    assert site.save_bundle() == 1
    job = checker(tmp_path, FakeReddit(), clock, google, folder="job")
    assert job.load_bundle() == 1
    assert job.last_read(URL)[1] is None and job.saved_check(URL, QUOTE) is None  # known, never used to show
    clock.now += timedelta(hours=18, minutes=1)
    assert site.save_bundle() == 0


def test_the_verification_records_text_is_this_reads_never_an_older_one(tmp_path):
    clock = Clock()
    reddit = FakeReddit(answer=NO_COMMENT)
    live = checker(tmp_path, reddit, clock)
    assert live.read_text(URL) == (clock.now, None)  # read now: the page had no comment on it
    clock.now += timedelta(hours=30)
    reddit.fail = True  # the next read fails: nothing is saved, and the older read isn't this one
    assert live.read_text(URL) is None
    reddit.fail, reddit.answer = False, (200, page(QUOTE))
    assert live.read_text(URL) == (clock.now, QUOTE)


# --- A read ahead never waits ---

def test_a_read_ahead_is_made_only_when_reddit_lets_it_go_at_once(tmp_path):
    clock = Clock()
    reddit = CountingReddit(clock, left=200, reset=600)
    live = checker(tmp_path, reddit, clock)
    assert live.read_if_free(URL) == "read" and live.read_if_free(URL) == "fresh"  # read once, then fresh
    clock.now += timedelta(seconds=1)
    assert live.read_if_free(URL, max_age=timedelta(0)) == "read"  # asked fresher than any check: read again
    reddit.left = 5  # Reddit says few are left: the next read would wait for its 10 minutes
    live.read_if_free(OTHER)
    started = clock.now
    assert live.read_if_free(URL.replace("c1aaaa", "c3cccc")) == "later" and clock.now == started  # never waited


def test_a_read_ahead_that_fails_saves_nothing(tmp_path):
    clock = Clock()
    for n, reddit in enumerate([FakeReddit(fail=True), FakeReddit(answer=(429, b"Too Many Requests"))]):
        live = checker(tmp_path, reddit, clock, folder=str(n))
        assert live.read_if_free(URL) == "failed" and live.last_read(URL) is None
    live = checker(tmp_path, FakeReddit(answer=NO_COMMENT), clock, folder="none")
    assert live.read_if_free(URL) == "read" and live.last_read(URL)[1] is None  # a page with no comment is a read


def test_the_reads_left_in_reddits_10_minutes_can_be_asked(tmp_path):
    clock = Clock()
    reddit = CountingReddit(clock, left=150, reset=300)
    live = checker(tmp_path, reddit, clock)
    assert live.spare() is None  # Reddit hasn't said yet
    live.check(URL, QUOTE)
    assert live.spare() == 149
    clock.now += timedelta(seconds=301)
    assert live.spare() is None  # its 10 minutes are over: the allowance is back, what's left unknown


# --- The site writes the bundle over the version it read ---

def test_the_site_writes_the_bundle_only_over_the_version_it_last_read_or_wrote(tmp_path):
    google, clock = FakeGoogle(buckets=(BUCKET,)), Clock()
    job = checker(tmp_path, FakeReddit(), clock, google, folder="job")
    job.check(URL, QUOTE)
    job.save_bundle()  # the bundle as the site finds it as it gets ready
    site = checker(tmp_path, FakeReddit(answer=(200, page(QUOTE + " Mine too."))), clock, google, folder="site")
    assert site.load_bundle() == 1
    clock.now += timedelta(minutes=5)
    site.check(OTHER, QUOTE)
    assert site.share_bundle() == 2 and len(bundle(google)["checks"]) == 2
    clock.now += timedelta(hours=1)
    site.check(URL.replace("c1aaaa", "c3cccc"), QUOTE)
    assert site.share_bundle() == 3  # over its own version: no download first
    assert len(google.asked("GET", "alt=media")) == 1


def test_another_writers_bundle_is_read_in_first_so_no_read_is_lost(tmp_path):
    google, clock = FakeGoogle(buckets=(BUCKET,)), Clock()
    site = checker(tmp_path, FakeReddit(), clock, google, folder="site")
    site.load_bundle()  # none yet
    site.check(URL, QUOTE)
    other = checker(tmp_path, FakeReddit(), clock, google, folder="other")  # a second server, during a deploy
    clock.now += timedelta(minutes=1)
    other.check(OTHER, QUOTE)
    assert other.share_bundle() == 1
    assert site.share_bundle() == 2  # the other's version read in first, then written over
    assert {json.loads(json.dumps(v))["fetched_at"] for v in bundle(google)["checks"].values()} == {
        (clock.now - timedelta(minutes=1)).isoformat(), clock.now.isoformat()}
    assert site.last_read(OTHER) is not None  # and the site now knows the other's read too


def test_a_bundle_the_site_cant_write_is_said_and_tried_again_later(tmp_path):
    google, clock = FakeGoogle(buckets=(BUCKET,), down=True), Clock()
    site = checker(tmp_path, FakeReddit(), clock, google)
    site.check(URL, QUOTE)
    assert site.share_bundle() is None


def test_reads_made_elsewhere_are_taken_in_when_newer_and_well_formed(tmp_path):
    clock = Clock()
    live = checker(tmp_path, FakeReddit(), clock)
    live.check(URL, QUOTE)
    name = _entry_name(embed_url(URL))
    older = {"fetched_at": (clock.now - timedelta(hours=1)).isoformat(), "text": "older"}
    newer = {"fetched_at": (clock.now + timedelta(minutes=1)).isoformat(), "text": "Mine too.", "via": "bright_data",
             "writer": "someone"}
    stale = {"fetched_at": (clock.now - timedelta(hours=49)).isoformat(), "text": "stale"}
    assert live.take_checks({name: older}) == 0  # the folder's own read is newer
    assert live.take_checks({"../outside.json": newer, _entry_name(embed_url(OTHER)): stale}) == 0
    assert live.take_checks({name: newer}) == 1
    saved = json.loads((tmp_path / "here" / name).read_text())
    assert saved == {"fetched_at": newer["fetched_at"], "text": "Mine too.", "via": "bright_data"}  # nothing else
    assert live.take_checks("not a dict") == 0
