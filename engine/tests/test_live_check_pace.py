"""Reads paced by what Reddit says is left (13 Oct 2026, the live site's latency).

Each embed page Reddit sends says how many reads its address has left in the current 10 minutes and when they come
back (x-ratelimit-remaining, x-ratelimit-reset: seconds). So reads go at once while plenty are left, spread out over
the rest of the window when few are, and wait for the window's end when none are, keeping a few for others. Until
Reddit has said (the first read, or a window that has ended), the burst and refill apply as before. A read asked not
to wait (wait=False: what "Also worth a look" and summaries ask, so they never hold up an answer) is put off instead,
uncounted and unsaved.

Every page here is a made-up stand-in for Reddit's embed page: no test touches the network.
"""

from datetime import timedelta

from engine.live_check import LiveChecker
from engine.tests.test_live_check import QUOTE, URL, Clock, page


class CountingReddit:
    """Answers each read with Reddit's rate-limit headers: `left` reads left before this one, back in `reset` s."""

    def __init__(self, clock, left: float, reset: float):
        self.clock, self.left, self.ends = clock, left, clock() + timedelta(seconds=reset)
        self.started = []

    def __call__(self, url, headers):
        self.started.append(self.clock())
        self.left -= 1
        reset = max(0.0, (self.ends - self.clock()).total_seconds())
        return 200, page(QUOTE), {"x-ratelimit-remaining": f"{self.left:.1f}", "x-ratelimit-used": "1",
                                  "x-ratelimit-reset": f"{reset:.0f}"}


def paced(tmp_path, reddit, clock, **settings):
    settings = {"min_interval": 0, "burst": 2, "refill": 4, "reserve": 10, "spread_below": 50,
                "max_wait": 600} | settings
    return LiveChecker(cache_dir=tmp_path / "cache", fetch=reddit, clock=clock, sleep=clock.sleep, **settings)


def urls(n: int) -> list[str]:
    return [URL.replace("c1aaaa", f"c{i}xxxx") for i in range(n)]


def seconds(reddit) -> list[float]:
    return [(t - reddit.started[0]).total_seconds() for t in reddit.started]


def test_reads_go_at_once_while_reddit_says_plenty_are_left(tmp_path):
    clock = Clock()
    reddit = CountingReddit(clock, left=190, reset=300)
    live = paced(tmp_path, reddit, clock)  # a burst of 2 alone would make the third read wait 4 s
    assert all(live.check(url, QUOTE).show for url in urls(6))
    assert seconds(reddit) == [0] * 6


def test_reads_spread_out_over_the_window_when_few_are_left(tmp_path):
    clock = Clock()
    reddit = CountingReddit(clock, left=41, reset=300)  # 40 left after the first read, 10 kept: 30 to spread
    live = paced(tmp_path, reddit, clock, refill=20)
    for url in urls(3):
        live.check(url, QUOTE)
    gaps = [b - a for a, b in zip(seconds(reddit), seconds(reddit)[1:])]
    assert gaps[0] == 300 / 30  # the rest of the window over what may be spent
    assert 9 < gaps[1] < 11


def test_spread_out_reads_are_never_slower_than_the_refill_pace(tmp_path):
    # 13 Oct 2026, measured live: spread over a long rest of the window, a read waited up to 20 s, slower than the one
    # every 4 s of the burst and refill, and an answer took 110 s. The refill pace is now the slowest.
    clock = Clock()
    reddit = CountingReddit(clock, left=21, reset=600)  # 10 to spread over 600 s: one a minute, so the refill's 4 s
    live = paced(tmp_path, reddit, clock)
    for url in urls(3):
        live.check(url, QUOTE)
    assert seconds(reddit) == [0, 4, 8]


def test_with_none_left_reads_wait_for_the_window_to_reset_and_then_go_at_once(tmp_path):
    clock = Clock()
    reddit = CountingReddit(clock, left=11, reset=120)  # 10 left after the first read: all kept for others
    live = paced(tmp_path, reddit, clock)
    live.check(urls(2)[0], QUOTE)
    reddit.left, reddit.ends = 200, reddit.ends + timedelta(minutes=10)  # Reddit's next window
    live.check(urls(2)[1], QUOTE)
    assert 120 <= seconds(reddit)[1] <= 122


def test_with_none_left_a_read_never_waits_longer_than_max_wait_for_the_window(tmp_path):
    # An answer must come back before Cloud Run's 5-minute timeout: a comment that would wait longer for Reddit's next
    # 10 minutes is taken as unreadable now (its quote is dropped, as for any page that can't be read), and not saved.
    clock = Clock()
    reddit = CountingReddit(clock, left=11, reset=300)
    live = paced(tmp_path, reddit, clock, max_wait=60)
    live.check(urls(2)[0], QUOTE)
    result = live.check(urls(2)[1], QUOTE)
    assert result.status == "unknown" and len(reddit.started) == 1 and clock.now == reddit.started[0]


def test_until_reddit_has_said_the_burst_and_refill_apply(tmp_path):
    clock = Clock()
    started = []

    def silent(url, headers):  # no rate-limit headers, as before 13 Oct 2026 or if Reddit stops sending them
        started.append(clock())
        return 200, page(QUOTE)

    live = paced(tmp_path, silent, clock)
    for url in urls(4):
        live.check(url, QUOTE)
    assert [(t - started[0]).total_seconds() for t in started] == [0, 0, 4, 8]


def test_an_answer_that_comes_back_late_never_raises_the_count_left(tmp_path):
    clock = Clock()
    live = paced(tmp_path, None, clock)
    live._learn({"x-ratelimit-remaining": "30", "x-ratelimit-reset": "300"}, clock())
    live._learn({"x-ratelimit-remaining": "150", "x-ratelimit-reset": "299"}, clock())  # sent earlier, came later
    assert live._window.left == 30
    clock.now += timedelta(seconds=301)
    live._learn({"x-ratelimit-remaining": "199", "x-ratelimit-reset": "599"}, clock())  # the next window
    assert live._window.left == 199


def test_a_read_asked_not_to_wait_is_put_off_unread_and_uncounted(tmp_path):
    clock = Clock()
    reddit = CountingReddit(clock, left=41, reset=300)  # after the first read, reads are spread out: 10 s apart
    live = paced(tmp_path, reddit, clock, refill=20)
    live.check(urls(3)[0], QUOTE)
    put_off = live.check(urls(3)[1], QUOTE, wait=False)
    assert put_off.status == "later" and not put_off.show
    assert len(reddit.started) == 1 and clock.now == reddit.started[0]  # not read, and nobody waited
    assert len(list((tmp_path / "cache").glob("*.json"))) == 1  # only the first read's page was saved
    live.check(urls(3)[2], QUOTE)  # a read that may wait comes next, as if the put-off one had never been asked
    assert seconds(reddit)[1] == 300 / 30


def test_a_read_asked_not_to_wait_goes_when_it_needs_no_wait(tmp_path):
    clock = Clock()
    live = paced(tmp_path, CountingReddit(clock, left=190, reset=300), clock)
    live.check(urls(2)[0], QUOTE)
    assert live.check(urls(2)[1], QUOTE, wait=False).show
    assert live.check(urls(2)[0], QUOTE, wait=False).show  # saved within 48 hours: no read needed at all


def test_a_read_asked_not_to_wait_is_put_off_once_the_burst_is_spent_and_reddit_hasnt_said(tmp_path):
    clock = Clock()

    def silent(url, headers):
        return 200, page(QUOTE)

    live = paced(tmp_path, silent, clock)
    assert [live.check(url, QUOTE, wait=False).status for url in urls(3)] == ["ok", "ok", "later"]
