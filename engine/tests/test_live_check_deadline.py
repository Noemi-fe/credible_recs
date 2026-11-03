"""A read that may wait only so long (3 Nov 2026, the pre-launch load fix for the Show HN of about 10 Nov).

Firebase Hosting in front of the site cuts any request at 60 s, and a live check used to wait up to
LIVE_CHECK_MAX_WAIT_SECONDS (60 s) for Reddit's allowance, so a visitor could wait past the cut. The checker can now be
told how long a read may wait (wait_at_most, the time the answer has left): a read that would wait longer is put off
unread and uncounted, exactly as a read asked not to wait is ("later"). A saved check from the last 48 hours needs no
read at all, so it answers whatever time is left. Asked nothing, the checker behaves as before.

Every page here is a made-up stand-in for Reddit's embed page: no test touches the network.
"""

from engine.tests.test_live_check import QUOTE, Clock
from engine.tests.test_live_check_pace import CountingReddit, paced, seconds, urls


def test_a_read_that_would_wait_longer_than_it_may_is_put_off_unread_and_uncounted(tmp_path):
    clock = Clock()
    reddit = CountingReddit(clock, left=41, reset=300)  # after the first read, reads are spread out: 10 s apart
    live = paced(tmp_path, reddit, clock, refill=20)
    first, second = urls(2)
    live.check(first, QUOTE)
    late = live.check(second, QUOTE, wait_at_most=5)
    assert late.status == "later" and not late.show
    assert len(reddit.started) == 1 and clock.now == reddit.started[0]  # not read, and nobody waited
    assert len(list((tmp_path / "cache").glob("*.json"))) == 1  # only the first read's page was saved
    in_time = live.check(second, QUOTE, wait_at_most=30)  # the same read fits in 30 s: made after its 10 s wait
    assert in_time.show and seconds(reddit)[1] == 10


def test_a_put_off_read_leaves_the_pace_as_if_it_had_never_been_asked(tmp_path):
    clock = Clock()
    reddit = CountingReddit(clock, left=41, reset=300)
    live = paced(tmp_path, reddit, clock, refill=20)
    first, second, third = urls(3)
    live.check(first, QUOTE)
    live.check(second, QUOTE, wait_at_most=1)  # put off
    live.check(third, QUOTE)  # the next read still comes 10 s after the first, not 20
    assert seconds(reddit) == [0, 10]


def test_a_saved_check_answers_whatever_time_is_left(tmp_path):
    clock = Clock()
    reddit = CountingReddit(clock, left=41, reset=300)
    live = paced(tmp_path, reddit, clock, refill=20)
    (url,) = urls(1)
    live.check(url, QUOTE)
    again = live.check(url, QUOTE, wait_at_most=0)
    assert again.show and len(reddit.started) == 1  # read from the saved check, no second read


def test_a_read_that_needs_no_wait_goes_even_with_no_time_to_wait(tmp_path):
    clock = Clock()
    live = paced(tmp_path, CountingReddit(clock, left=190, reset=300), clock)
    assert all(live.check(url, QUOTE, wait_at_most=0).show for url in urls(3))


def test_the_time_left_decides_before_the_checkers_own_limit(tmp_path):
    # A read that would wait 5 minutes for Reddit's next 10 minutes is taken as unreadable ("unknown", its quote dropped)
    # when only the checker's own limit applies. With the answer's time left given, it is simply not made now.
    clock = Clock()
    reddit = CountingReddit(clock, left=11, reset=300)  # after the first read, nothing is left to spend
    live = paced(tmp_path, reddit, clock, max_wait=60)
    first, second, third = urls(3)
    live.check(first, QUOTE)
    assert live.check(second, QUOTE).status == "unknown"  # as before: waits over 60 s
    assert live.check(third, QUOTE, wait_at_most=30).status == "later"
    assert len(reddit.started) == 1
