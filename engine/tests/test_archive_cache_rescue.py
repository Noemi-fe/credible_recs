"""A round of archive searches ended by failures still uses the searches already in the 48-hour cache (13 Oct 2026, the
data round).

When Arctic Shift times out on the first searches of a round, ARCHIVE_SEARCH_MAX_FAILURES failures in a row end it, so a
service that is down isn't asked again and again. But the searches still queued may already be answered in the client's
48-hour cache (a run a few minutes earlier asked them): using those costs no call, so the round ends with what the cache
holds instead of nothing. The client answers from its cache only (ArcticShiftClient.cached_posts): never a call.

Every test uses a fake archive or a fake service and made-up data: no network.
"""

from datetime import UTC, datetime

import pytest

from engine.arctic_shift import ArcticShiftError
from engine.config import ARCHIVE_OLDER_YEARS, ARCHIVE_SEARCH_MAX_FAILURES
from engine.query import parse_query
from engine.sources import ArchiveSource, search_archive
from engine.tests.test_archive_reader import FakeArchiveClient, kettle_posts
from engine.tests.test_arctic_shift import FakeService, make_client

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)
KETTLE = "electric kettle that lasts 10+ years"  # kitchen; searches BuyItForLife, tea, Coffee
TIMEOUT = "Arctic Shift answered 422 to a search in r/{}: 'Timeout. Maybe slow down a bit'"


class CachedButBusy(FakeArchiveClient):
    """Times out on every search it is asked, but its cache already holds the answers for the subreddits in `cached`."""

    def __init__(self, posts=(), cached=("tea", "Coffee")):
        super().__init__(posts)
        self.cached = set(cached)
        self.cache_reads: list[str] = []

    def search_posts(self, subreddit, title, limit=25, before=None, after=None):
        self.searches.append((subreddit, title))
        raise ArcticShiftError(TIMEOUT.format(subreddit))

    def cached_posts(self, subreddit, title, limit=25, before=None, after=None):
        self.cache_reads.append(subreddit)
        if subreddit not in self.cached:
            return None
        return [dict(p) for p in self.posts if p["subreddit"] == subreddit]


def test_a_round_ended_by_failures_uses_the_searches_already_in_the_cache():
    client = CachedButBusy(kettle_posts())
    found = search_archive(client, parse_query(KETTLE), 3, 0, posts_each=100, older_than_years=ARCHIVE_OLDER_YEARS,
                           max_failures=ARCHIVE_SEARCH_MAX_FAILURES, failed=[], now=NOW, raise_if_nothing=True)
    assert len(client.searches) == ARCHIVE_SEARCH_MAX_FAILURES  # no more calls once the round ended
    assert {p["subreddit"] for p in found} == {"tea", "Coffee"}  # but the cache's answers are used


def test_with_nothing_in_the_cache_a_round_ended_by_failures_still_raises():
    client = CachedButBusy(kettle_posts(), cached=())
    with pytest.raises(ArcticShiftError):
        search_archive(client, parse_query(KETTLE), 3, 0, posts_each=100, older_than_years=ARCHIVE_OLDER_YEARS,
                       max_failures=ARCHIVE_SEARCH_MAX_FAILURES, failed=[], now=NOW, raise_if_nothing=True)
    assert len(client.searches) == ARCHIVE_SEARCH_MAX_FAILURES


def test_the_archive_source_finds_threads_from_the_cache_when_the_archive_is_busy():
    threads = ArchiveSource(CachedButBusy(kettle_posts())).find_threads(parse_query(KETTLE), limit=2)
    assert {t.community for t in threads} <= {"tea", "Coffee"} and threads


def test_the_client_answers_from_its_cache_only(tmp_path):
    service = FakeService()
    client = make_client(tmp_path, service)
    assert client.cached_posts("BuyItForLife", "kettle", limit=100, after="2023-10-09") is None  # nothing asked yet
    assert service.requests == []
    asked = client.search_posts("BuyItForLife", "kettle", limit=100, after="2023-10-09")
    assert client.cached_posts("BuyItForLife", "kettle", limit=100, after="2023-10-09") == asked
    assert client.cached_posts("BuyItForLife", "kettle", limit=100) is None  # another span: another search
    assert len(service.requests) == 1  # only the real search called
