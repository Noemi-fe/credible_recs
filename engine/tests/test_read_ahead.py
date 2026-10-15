"""Reading ahead on the site (14 Oct 2026, the free-tier redesign; engine/read_ahead.py).

The daily job now only works out what to read (the plan: the comments answers would show, likeliest first, then the
slimmed library's kept comments due to be verified, and its checks through Bright Data) and leaves it in the bucket.
The site, billed only while it answers, reads a few of them at each keep-warm ping: never waiting on Reddit, never using
the reads visitors' answers need, an answer's comment again before its check runs out, and it shares what it read
through the bucket's bundle at most once an hour. Every Reddit page and every Google answer here is made up: no test
reaches the network.
"""

import threading
from datetime import timedelta

import pytest

from engine import config
from engine.live_check import BUNDLE_NAME, Bucket, LiveChecker, _entry_name, embed_url
from engine.read_ahead import PLAN_NAME, ReadAhead, plan_bytes, read_plan
from engine.tests.fake_google import FakeGoogle
from engine.tests.test_live_check import QUOTE, Clock, page

BUCKET = "credible-test-checks"
PLAN = f"live_check/{PLAN_NAME}"


def link(n: int) -> str:
    return f"https://www.reddit.com/r/BuyItForLife/comments/1kett01/which_kettle/c{n:04d}x/"


class Reddit:
    """Made-up embed pages with Reddit's rate-limit headers: `left` reads before each one, back `reset` s after the
    first; `empty`: comments whose page shows no comment."""

    def __init__(self, clock, left=190.0, reset=600.0, empty=()):
        self.clock, self.left, self.ends, self.empty = clock, left, clock() + timedelta(seconds=reset), set(empty)
        self.asked: list[str] = []
        self._lock = threading.Lock()

    def __call__(self, url, headers):
        with self._lock:
            self.asked.append(url)
            self.left -= 1
            left = self.left
        reset = max(0.0, (self.ends - self.clock()).total_seconds())
        comment = url.split("/comment/")[1].split("/")[0]
        body = b"<html>no comment here</html>" if comment in self.empty else page(QUOTE)
        return 200, body, {"x-ratelimit-remaining": f"{left:.1f}", "x-ratelimit-reset": f"{reset:.0f}"}

    def read(self, n: int) -> bool:
        return embed_url(link(n)) in self.asked


class Ticks:
    """The site's own seconds (time.monotonic in the server), moved by the tests; `step` added at every look."""

    def __init__(self, step: float = 0.0):
        self.now, self.step = 10_000.0, step

    def __call__(self) -> float:
        self.now += self.step
        return self.now


@pytest.fixture
def scene(tmp_path):
    class Scene:
        google, clock, ticks = FakeGoogle(buckets=(BUCKET,)), Clock(), Ticks()

        def site(self, reddit=None, folder="site", **settings):
            self.reddit = reddit or Reddit(self.clock)
            bucket = Bucket(BUCKET, request=self.google, clock=lambda: self.clock.now.timestamp())
            self.live = LiveChecker(cache_dir=tmp_path / folder, fetch=self.reddit, clock=self.clock,
                                    sleep=self.clock.sleep, min_interval=0, bucket=bucket)
            self.ahead = ReadAhead(self.live, clock=self.ticks, **settings)
            return self.ahead

        def plan(self, answers=(), verify=(), checks=None):
            self.google.put(BUCKET, PLAN, plan_bytes([link(n) for n in answers], [link(n) for n in verify],
                                                     checks or {}, self.clock.now))

        def bundle(self):
            return self.google.read(BUCKET, f"live_check/{BUNDLE_NAME}")

    return Scene()


# --- What is read, and in what order ---

def test_the_plans_comments_with_no_read_are_read_in_its_order_answers_first(scene):
    scene.plan(answers=[1, 2, 3], verify=[4, 5])
    ahead = scene.site(parallel=1)  # one at a time, so the order shows (at once, each batch in the plan's order)
    reading = ahead.on_ping()
    assert reading.read == 5 and reading.due == 5
    assert [url.split("/comment/")[1][:5] for url in scene.reddit.asked] == ["c0001", "c0002", "c0003", "c0004",
                                                                              "c0005"]
    assert scene.live.saved_check(link(1), QUOTE).show  # an answer finds it checked


def test_reads_go_a_few_at_once_each_batch_in_the_plans_order(scene):
    scene.plan(answers=range(1, 10))
    ahead = scene.site(parallel=4)
    assert ahead.on_ping().read == 9
    batches = [sorted(scene.reddit.asked[i:i + 4]) for i in (0, 4)]
    assert batches == [sorted(embed_url(link(n)) for n in range(1, 5)), sorted(embed_url(link(n)) for n in range(5, 9))]


def test_an_answers_comment_is_read_again_once_its_read_is_40_hours_old_so_its_check_never_runs_out(scene):
    scene.plan(answers=[1])
    ahead = scene.site()
    ahead.on_ping()
    scene.clock.now += timedelta(hours=config.READ_AHEAD_AGAIN_HOURS) - timedelta(minutes=1)
    assert ahead.on_ping().read == 0
    scene.clock.now += timedelta(minutes=2)
    assert ahead.on_ping().read == 1 and len(scene.reddit.asked) == 2
    assert config.READ_AHEAD_AGAIN_HOURS * 3600 + 3 * 3600 < config.CACHE_MAX_AGE_HOURS * 3600  # hours to spare


def test_a_comment_to_verify_is_read_once_while_its_read_is_under_48_hours_old(scene):
    scene.plan(verify=[4])
    ahead = scene.site()
    assert ahead.on_ping().read == 1
    scene.clock.now += timedelta(hours=47)
    assert ahead.on_ping().read == 0  # the job records it and lists it again only when due (engine/verify.py)
    scene.clock.now += timedelta(hours=2)
    assert ahead.on_ping().read == 1


def test_a_comment_also_among_the_answers_is_read_once(scene):
    scene.plan(answers=[1], verify=[1, 2])
    assert scene.site().on_ping().read == 2 and len(scene.reddit.asked) == 2


def test_a_page_with_no_comment_on_it_is_read_again_only_with_the_others(scene):
    scene.plan(answers=[1])
    ahead = scene.site(Reddit(scene.clock, empty={"c0001x"}))
    assert ahead.on_ping().read == 1
    scene.clock.now += timedelta(hours=config.LIVE_CHECK_UNREADABLE_KEEP_HOURS + 1)  # no longer used by answers...
    assert ahead.on_ping().read == 0  # ...but read again only 40 hours after: the daily job sends it to Bright Data


def test_a_comment_verified_through_bright_data_is_left_to_the_job(scene):
    name = _entry_name(embed_url(link(1)))
    seen = (scene.clock.now - timedelta(hours=1)).isoformat()
    scene.plan(answers=[1, 2], checks={name: {"fetched_at": seen, "text": QUOTE, "via": "bright_data"}})
    ahead = scene.site()
    assert ahead.on_ping().read == 1 and not scene.reddit.read(1) and scene.reddit.read(2)
    assert scene.live.saved_check(link(1), QUOTE).show  # the job's check, taken in from the plan
    scene.clock.now += timedelta(hours=44)
    ahead.on_ping()
    assert not scene.reddit.read(1)  # never read on the embed page while it lasts


def test_a_comment_a_visitors_answer_read_meanwhile_isnt_read_again(scene):
    scene.plan(answers=[1, 2])
    ahead = scene.site()
    ahead.on_ping()
    scene.clock.now += timedelta(hours=49)  # say the pings stopped a while: the checks ran out
    assert scene.live.check(link(1), QUOTE).show  # a visitor's answer reads it again on Reddit
    reading = ahead.on_ping()
    assert (reading.fresh, reading.read) == (1, 1) and scene.reddit.asked.count(embed_url(link(1))) == 2


def test_without_a_plan_nothing_is_read(scene):
    ahead = scene.site()
    reading = ahead.on_ping()
    assert reading.read == 0 and scene.reddit.asked == []


# --- Within its limits ---

def test_at_most_its_reads_a_ping(scene):
    scene.plan(answers=range(1, 60))
    ahead = scene.site()
    assert ahead.on_ping().read == config.READ_AHEAD_PER_PING and len(scene.reddit.asked) == config.READ_AHEAD_PER_PING
    scene.reddit.left = 190  # the next 10 minutes
    scene.ticks.now += 300
    assert ahead.on_ping().read == 59 - config.READ_AHEAD_PER_PING


def test_no_read_starts_after_its_seconds(scene):
    scene.plan(answers=range(1, 30))
    scene.ticks.step = 1.0  # each look at the clock a second later
    # Changed on purpose 15 Oct 2026: 4 at once named here, as the setting was then (it is 8 since: 29 comments would
    # all be read within its 5 looks at the clock, and the test would no longer test its seconds).
    reading = scene.site(parallel=4).on_ping()
    assert 0 < reading.read < 29 and reading.left == 29 - reading.read


def test_the_reads_visitors_answers_need_are_kept(scene):
    scene.plan(answers=range(1, 30))
    reddit = Reddit(scene.clock, left=config.READ_AHEAD_KEEP + 6)
    reading = scene.site(reddit).on_ping()
    assert reading.kept_for_visitors and reading.read < 29
    assert reddit.left >= config.READ_AHEAD_KEEP - config.READ_AHEAD_PARALLEL  # at most one batch past it


def test_a_read_ahead_never_waits_for_reddit(scene):
    scene.plan(answers=range(1, 10))
    reddit = Reddit(scene.clock, left=3)  # nothing to spare: the next read would wait for Reddit's next 10 minutes
    ahead = scene.site(reddit, keep=0, parallel=1)
    started = scene.clock.now
    reading = ahead.on_ping()
    assert scene.clock.now == started and reading.read < 9 and reading.put_off


def test_when_reddit_doesnt_answer_a_ping_stops_after_one_batch(scene):
    scene.plan(answers=range(1, 30))

    def down(url, headers):
        scene.reddit.asked.append(url)
        raise TimeoutError("timed out")

    ahead = scene.site()
    scene.live._fetch = down
    reading = ahead.on_ping()
    assert reading.reddit_failing and reading.failed == config.READ_AHEAD_PARALLEL and reading.read == 0
    assert len(scene.reddit.asked) == config.READ_AHEAD_PARALLEL and scene.live.last_read(link(1)) is None


def test_a_ping_arriving_while_another_reads_does_nothing(scene):
    scene.plan(answers=[1])
    ahead = scene.site()
    with ahead._lock:
        assert ahead.on_ping() is None
    assert scene.reddit.asked == []


# --- The plan and the bundle ---

def test_the_plan_is_asked_for_at_most_once_an_hour_and_downloaded_only_when_it_changed(scene):
    scene.plan(answers=[1])
    ahead = scene.site()
    ahead.on_ping()
    assert len(scene.google.asked("GET", "plan.json?alt=media")) == 1
    scene.ticks.now += 300
    ahead.on_ping()
    assert len(scene.google.asked("GET", "plan.json?fields=generation")) == 1  # 5 minutes on: not asked
    scene.ticks.now += config.PLAN_RELOAD_SECONDS
    ahead.on_ping()
    assert len(scene.google.asked("GET", "plan.json?fields=generation")) == 2
    assert len(scene.google.asked("GET", "plan.json?alt=media")) == 1  # unchanged: not downloaded again
    scene.plan(answers=[1, 2])
    scene.ticks.now += config.PLAN_RELOAD_SECONDS
    assert ahead.on_ping().read == 1 and scene.reddit.read(2)


def test_what_was_read_is_written_to_the_bundle_at_most_once_an_hour(scene):
    scene.plan(answers=[1, 2])
    ahead = scene.site()
    assert ahead.on_ping().shared == 2 and len(scene.bundle()["checks"]) == 2
    scene.clock.now += timedelta(hours=config.READ_AHEAD_AGAIN_HOURS)
    scene.ticks.now += 300
    reading = ahead.on_ping()
    assert reading.read == 2 and reading.shared is None  # read again, but the bundle was written 5 minutes ago
    scene.ticks.now += config.BUNDLE_SHARE_SECONDS
    assert ahead.on_ping().shared == 2  # an hour on: written, with the new reads
    scene.ticks.now += config.BUNDLE_SHARE_SECONDS
    assert ahead.on_ping().shared is None  # nothing new: not written
    assert len(scene.google.asked("POST")) == 2


def test_a_server_that_restarts_starts_from_what_it_shared(scene, tmp_path):
    scene.plan(answers=[1, 2])
    scene.site().on_ping()
    reddit = Reddit(scene.clock)
    again = scene.site(reddit, folder="the new server")
    scene.live.load_bundle()  # as it gets ready
    assert again.on_ping().read == 0 and reddit.asked == []  # nothing read twice


def test_another_writers_bundle_is_read_in_before_the_site_writes(scene):
    scene.plan(answers=[1])
    ahead = scene.site()
    other = LiveChecker(cache_dir=scene.live.cache_dir.parent / "other", fetch=Reddit(scene.clock), clock=scene.clock,
                        sleep=scene.clock.sleep, min_interval=0,
                        bucket=Bucket(BUCKET, request=scene.google, clock=lambda: scene.clock.now.timestamp()))
    other.check(link(9), QUOTE)
    other.save_bundle()  # written after the site last read it (here: never)
    assert ahead.on_ping().shared == 2
    assert {_entry_name(embed_url(link(n))) for n in (1, 9)} == set(scene.bundle()["checks"])


def test_when_the_bucket_cant_be_reached_the_site_still_reads_and_the_ping_says_ready(scene, capsys):
    scene.plan(answers=[1])
    ahead = scene.site()
    ahead.on_ping()
    scene.google.down = True
    scene.plan(answers=[1, 2])  # never seen: the bucket is down
    scene.ticks.now += config.PLAN_RELOAD_SECONDS
    scene.clock.now += timedelta(hours=41)
    reading = ahead.on_ping()
    assert reading.read == 1 and reading.shared is None  # the plan it has is read; the bundle waits
    assert "token-" not in capsys.readouterr().err


# --- The plan's shape ---

def test_the_plan_holds_links_and_checks_only_and_a_broken_one_is_ignored(scene):
    data = plan_bytes([link(1)], [link(2)], {}, scene.clock.now)
    plan = read_plan(data)
    assert (plan.answers, plan.verify, plan.checks) == ((link(1),), (link(2),), {})
    assert plan.written_at == scene.clock.now
    for broken in (b"", b"[]", b'{"answers": "x"}', b"not json", None):
        assert read_plan(broken) is None
    odd = read_plan(b'{"written_at": "2026-10-14T04:00:00+00:00", "answers": ["https://example.com/x", 3], '
                    b'"verify": [], "checks": {}}')
    assert odd.answers == ()  # only Reddit comment links are kept


def test_two_pings_in_reddits_10_minutes_leave_visitors_their_share():
    # Reddit's embed pages answer about 200 reads in 10 minutes from one address, and the keep-warm ping comes twice in
    # that time: reading ahead takes at most 2 x READ_AHEAD_PER_PING and stops while fewer than READ_AHEAD_KEEP are left.
    # (Its cost: engine/tests/test_cloudrun.py.)
    assert config.READ_AHEAD_PER_PING * 2 + config.READ_AHEAD_KEEP <= 200
    assert config.READ_AHEAD_KEEP >= 40 * 3  # three fresh answers' worth (an answer reads 10 to 40 comments)


def test_a_day_of_pings_reads_what_falls_due_with_room_to_spare():
    # 15 Oct 2026 (the coordinator): the live site read 20 a ping, 4 at once in its 5 seconds (each batch about a second
    # on Reddit's side: 5 batches), so 5,760 a day, while about 7,650 fell due: the plan's 7,752 answers' comments each
    # every READ_AHEAD_AGAIN_HOURS, and LIBRARY_VERIFY_READS kept comments a day. Now as many at once as an answer reads
    # (LIVE_CHECK_PARALLEL): READ_AHEAD_PER_PING a ping, within Reddit's share (the test above) and the ping's seconds
    # (its cost: engine/tests/test_cloudrun.py), covering what falls due with a third to spare.
    from math import ceil

    pings_a_day, batch_seconds, plan_answers = 24 * 12, 1.0, 7_752  # the live site's numbers, 15 Oct 2026
    per_ping = min(config.READ_AHEAD_PER_PING,
                   config.READ_AHEAD_PARALLEL * ceil(config.READ_AHEAD_SECONDS / batch_seconds))
    due_a_day = plan_answers * 24 / config.READ_AHEAD_AGAIN_HOURS + config.LIBRARY_VERIFY_READS
    assert per_ping == config.READ_AHEAD_PER_PING == 40
    assert per_ping * pings_a_day >= 1.33 * due_a_day  # 11,520 a day against 7,651
    assert config.READ_AHEAD_PARALLEL <= config.LIVE_CHECK_PARALLEL  # no more at once than an answer reads
