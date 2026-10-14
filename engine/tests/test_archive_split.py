"""A title search Arctic Shift times out on is asked again over shorter spans of time (13 Oct 2026, the data round).

On 13 Oct 2026 Arctic Shift timed out ("Timeout. Maybe slow down a bit") on half of the searches for "shampoo" over the
last 3 years in the big haircare subreddits, round after round, while a search over the last year answered in 14 s:
the cost is in the span searched. Three failures ended the round, so `library add` found almost nothing. Now a search
that times out is asked again as the two halves of its span, newest first (an undated one, as the archive's two
windows), at most ARCHIVE_SPLIT_DEPTH times; only a search that can't be split further counts as failed. The newer half
of a search's first timeout is asked right away, every other half at the end of the round, so a search that times out
over any span can't end the round before the other subreddits are searched. And the round ends after
ARCHIVE_SEARCH_MAX_FAILURES failures in a row, not in all: a busy service fails some searches and answers others, one
that is down fails every one.

Every test uses a fake archive and made-up data: no network.
"""

import re
from datetime import UTC, date, datetime

from engine.arctic_shift import ArcticShiftError
from engine.config import ARCHIVE_OLDER_YEARS, ARCHIVE_SEARCH_MAX_FAILURES, ARCHIVE_SPLIT_DEPTH
from engine.query import parse_query
from engine.sources import ArchiveSource, search_archive
from engine.tests.test_archive_reader import FakeArchiveClient, kettle_posts

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
KETTLE = "electric kettle that lasts 10+ years"  # kitchen; searches BuyItForLife, tea, Coffee
TIMEOUT = "Arctic Shift answered 422 to a search in r/{}: 'Timeout. Maybe slow down a bit'"
THREE_YEARS_AGO, NINE_YEARS_AGO = "2023-10-09", "2017-10-09"


def afters(failed: list[str]) -> list[str]:
    """The first day of each failed search's span, as named in `failed`."""
    return [m.group(1) for f in failed if (m := re.search(r"after (\d{4}-\d{2}-\d{2})", f))]


def span_days(after: str | None, before: str | None) -> int:
    start = date.fromisoformat(after) if after else date(2005, 6, 1)  # Reddit's start: an undated search spans it all
    end = date.fromisoformat(before) if before else NOW.date()
    return (end - start).days


class TimesOutOverLongSpans(FakeArchiveClient):
    """Times out, as Arctic Shift does when busy, on a search spanning more than `max_days` days; other errors on
    request (`other_error`). Every search asked is recorded with its dates."""

    def __init__(self, posts=(), max_days=10**6, other_error: str | None = None, fails=lambda n: False):
        super().__init__(posts)
        self.max_days = max_days
        self.other_error = other_error
        self.fails = fails  # fails(n): whether the n-th search (from 0) fails, whatever its span
        self.windows: list[tuple[str, str, str | None, str | None]] = []

    def search_posts(self, subreddit, title, limit=25, before=None, after=None):
        n = len(self.windows)
        self.windows.append((subreddit, title, after, before))
        if self.other_error:
            raise ArcticShiftError(self.other_error)
        if self.fails(n) or span_days(after, before) > self.max_days:
            self.searches.append((subreddit, title))
            raise ArcticShiftError(TIMEOUT.format(subreddit))
        return super().search_posts(subreddit, title, limit, before, after)


def search(client, failed=None, halved=None, max_free_searches=1, max_warning_searches=0, max_failures=10):
    return search_archive(client, parse_query(KETTLE), max_free_searches, max_warning_searches, posts_each=100,
                          older_than_years=ARCHIVE_OLDER_YEARS, max_failures=max_failures,
                          failed=failed if failed is not None else [], halved=halved, now=NOW)


def test_the_decided_value():
    assert ARCHIVE_SPLIT_DEPTH == 2


def test_a_search_timing_out_over_its_span_is_asked_again_in_two_halves_newest_first():
    client = TimesOutOverLongSpans(kettle_posts(), max_days=600)  # 3 years times out; a year and a half doesn't
    failed, halved = [], []
    found = search(client, failed, halved)
    middle = (date.fromisoformat(THREE_YEARS_AGO) + (NOW.date() - date.fromisoformat(THREE_YEARS_AGO)) / 2).isoformat()
    asked = client.windows
    assert asked[0] == ("BuyItForLife", "kettle", THREE_YEARS_AGO, None)  # timed out
    newer = asked.index(("BuyItForLife", "kettle", middle, None))  # the newer half: from the middle to now
    older = asked.index(("BuyItForLife", "kettle", THREE_YEARS_AGO, middle))  # then the older half
    assert 0 < newer < older
    assert {p["id"] for p in found} >= {"1a1", "1w1"}  # r/BuyItForLife's posts, found through the halves
    assert halved[0] == f'r/BuyItForLife for "kettle" (after {THREE_YEARS_AGO})'  # named as a failed one would be
    assert failed == []  # every half answered (the 6 years before 3 were halved twice), so nothing failed


def test_a_half_still_timing_out_is_halved_again_then_counts_as_failed():
    client = TimesOutOverLongSpans(kettle_posts(), max_days=200)  # even a quarter of 3 years (274 days) times out
    failed = []
    search(client, failed, max_failures=20)  # every search fails here: a limit high enough to see them all
    recent = [w for w in client.windows if w[2] and w[2] >= THREE_YEARS_AGO]
    # The 3 years, its 2 halves, and their 4 halves: halved ARCHIVE_SPLIT_DEPTH (2) times, no more.
    assert len(recent) == 1 + 2 + 4
    assert sum(after >= THREE_YEARS_AGO for after in afters(failed)) == 4  # the 4 quarters failed
    assert all(span_days(after, before) >= 270 for _, _, after, before in recent)


def test_an_error_that_isnt_a_timeout_is_not_split():
    client = TimesOutOverLongSpans(kettle_posts(), other_error="Arctic Shift answered 500 to a search in r/X: 'oops'")
    failed, halved = [], []
    search(client, failed, halved, max_failures=2)
    assert halved == [] and len(client.windows) == 2  # each asked once, then the round ended after 2 in a row
    assert len(failed) == 2


def test_an_undated_warning_search_timing_out_is_asked_again_over_the_two_windows():
    client = TimesOutOverLongSpans(kettle_posts(), max_days=4000)  # the whole history times out; 9 years doesn't
    halved = []
    search(client, halved=halved, max_free_searches=0, max_warning_searches=1)
    assert client.windows == [
        ("BuyItForLife", "kettle died", None, None),
        ("BuyItForLife", "kettle died", THREE_YEARS_AGO, None),
        ("BuyItForLife", "kettle died", NINE_YEARS_AGO, THREE_YEARS_AGO),
    ]
    assert len(halved) == 1 and '"kettle died"' in halved[0]


def test_failures_end_the_round_only_in_a_row():
    # Before 13 Oct 2026 the third failure in all ended the round. An archive that is down fails every search: the
    # first, then its newer half, then that half's newer half are 3 in a row.
    client = TimesOutOverLongSpans(kettle_posts(), fails=lambda n: True)
    failed = []
    found = search(client, failed, max_free_searches=3, max_failures=ARCHIVE_SEARCH_MAX_FAILURES)
    # The first search and its first half and quarter failed: 3 in a row end the round, before anything was found.
    assert len(client.windows) == ARCHIVE_SEARCH_MAX_FAILURES and found == []

    # A busy archive answers some searches and times out on others (here every other one, whatever its span).
    client = TimesOutOverLongSpans(kettle_posts(), fails=lambda n: n % 2 == 0)
    failed = []
    found = search(client, failed, max_free_searches=3, max_failures=ARCHIVE_SEARCH_MAX_FAILURES)
    assert len(failed) >= ARCHIVE_SEARCH_MAX_FAILURES  # more failures in all than the limit...
    assert {p["subreddit"] for p in found} == {"BuyItForLife", "tea", "Coffee"}  # ...but the round went on


def test_the_archive_source_names_the_searches_it_split_in_its_notes():
    client = TimesOutOverLongSpans(kettle_posts(), max_days=600)
    source = ArchiveSource(client)
    threads = source.find_threads(parse_query(KETTLE), limit=2)
    assert threads
    assert any("r/BuyItForLife" in note and "shorter spans" in note for note in source.notes)


def test_a_first_search_that_keeps_timing_out_does_not_end_the_round():
    # 13 Oct 2026: r/HaircareScience's "dry shampoo" search timed out over 3 years, then over its halves and quarters:
    # three timeouts in a row, before anything was found, ended the round as if Arctic Shift were down. Only the newer
    # half of a first timeout is asked right away; the other halves wait, so the subreddits that answer are searched.
    class OneSubredditTimesOut(TimesOutOverLongSpans):
        def search_posts(self, subreddit, title, limit=25, before=None, after=None):
            if subreddit == "BuyItForLife":
                self.windows.append((subreddit, title, after, before))
                raise ArcticShiftError(TIMEOUT.format(subreddit))
            return super().search_posts(subreddit, title, limit, before, after)

    client = OneSubredditTimesOut(kettle_posts())
    failed = []
    found = search(client, failed, max_free_searches=3, max_failures=ARCHIVE_SEARCH_MAX_FAILURES)
    assert {p["subreddit"] for p in found} == {"tea", "Coffee"}
    assert sum(subreddit == "BuyItForLife" for subreddit, *_ in client.windows) > 2  # its halves were asked too
