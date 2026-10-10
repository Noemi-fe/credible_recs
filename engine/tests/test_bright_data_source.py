"""Bright Data as a full source for the library (Noemi's request, 10 Oct 2026: "not get stuck with parse and everything
else").

Until now the library's `add` found and read threads through Arctic Shift (down since 9 Oct 2026) or Parse (out of
credits), and `refresh` read through Parse only, so both were stuck while Bright Data, which works, was used by hand.
Now Bright Data can do both jobs: it finds threads with Reddit's own search inside the request's decided subreddits
(engine.bright_data.BrightDataClient.discover) and reads them (get_thread), within its free monthly records; and
`--reader auto` (the new default) tries Arctic Shift first and turns to Bright Data when Arctic Shift is down. Every
thread, client and library here is made up; nothing reaches the network.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from engine import config, library
from engine.arctic_shift import ArcticShiftError
from engine.bright_data import BrightDataError, FoundPost, ReadNotes
from engine.library import add, refresh
from engine.models import Thread
from engine.query import parse_query
from engine.sources import BrightDataSource, FallbackSource
from engine.tests.factories import make_comment, make_thread

KETTLE = "electric kettle that lasts 10+ years"
NOW = datetime(2026, 10, 11, 9, 0, tzinfo=UTC)


def found(post_id: str, title: str, comments: int = 30, subreddit: str = "BuyItForLife", years_ago: int = 1) -> FoundPost:
    return FoundPost(id=post_id, subreddit=subreddit, title=title, num_comments=comments,
                     created_at=NOW - timedelta(days=365 * years_ago),
                     url=f"https://www.reddit.com/r/{subreddit}/comments/{post_id}/")


class FakeBrightData:
    """Answers discover() from `posts` (every search gets them all, as Reddit's search would return overlapping
    results) and get_thread() with a made-up thread of `comments` comments; counts records like the real client: one
    per post found, and one for the post plus one per comment read."""

    def __init__(self, posts: list[FoundPost], used: int = 0, fail_discover: Exception | None = None):
        self.posts = posts
        self.used = used
        self.fail_discover = fail_discover
        self.searches: list[tuple[str, str]] = []
        self.read: list[str] = []
        self.last_read = ReadNotes()

    def discover(self, searches, posts_each=10):
        if self.fail_discover:
            raise self.fail_discover
        self.searches += list(searches)
        self.used += len(self.posts)
        return list(self.posts)

    def get_thread(self, url: str) -> Thread:
        post_id = url.rstrip("/").split("/")[-1]
        post = next(p for p in self.posts if p.id == post_id)
        self.read.append(post_id)
        comments = [make_comment(f"c{post_id}{i}", thread_id=post_id, body=f"My kettle lasted {i + 2} years.")
                    for i in range(3)]
        thread = make_thread(id=post_id, title=post.title, community=post.subreddit, category="kitchen",
                             url=post.url, num_comments=post.num_comments, comments=comments)
        self.used += 1 + post.num_comments
        self.last_read = ReadNotes(records=1 + post.num_comments)
        return Thread.model_validate(thread | {"read_from": "bright_data", "checked_live_at": NOW.isoformat()})

    def records_used_this_month(self) -> int:
        return self.used


KETTLE_POSTS = [
    found("1adv001", "Which electric kettle should I buy? Recommendations?", 60),
    found("1adv002", "Best kettle that lasts? Looking for BIFL advice", 45, subreddit="tea"),
    found("1adv003", "Kettle recommendations please", 30, subreddit="Coffee"),
    found("1lng001", "My kettle after 15 years of daily use", 40),
    found("1wrn001", "My kettle died after a year, avoid this brand", 25),
    found("1wrn002", "Kettle regret: the lid broke", 20, subreddit="tea"),
    found("1tiny01", "Kettle?", 2),  # too few comments to learn from
]


# --- Finding threads ---

def test_bright_data_searches_the_requests_subreddits_and_warnings():
    client = FakeBrightData(KETTLE_POSTS)
    source = BrightDataSource(client)
    ranked = source.rank_candidates(parse_query(KETTLE))
    assert client.searches[:3] == [("BuyItForLife", "kettle"), ("tea", "kettle"), ("Coffee", "kettle")]
    assert ("BuyItForLife", "kettle died") in client.searches  # warnings, in the most specialist subreddit
    # One search per subreddit for "kettle" (3, under BRIGHT_DATA_ADD_SEARCHES), then the warning searches.
    assert len(client.searches) == 3 + config.BRIGHT_DATA_ADD_WARNING_SEARCHES
    assert "1tiny01" not in [p["id"] for p in ranked]  # too few comments
    assert {"id", "subreddit", "title", "num_comments", "created_utc"} <= set(ranked[0])


def test_threads_already_saved_or_on_the_gold_list_are_never_candidates():
    source = BrightDataSource(FakeBrightData(KETTLE_POSTS), skip_ids={"1adv001", "1wrn001"})
    ids = [p["id"] for p in source.rank_candidates(parse_query(KETTLE))]
    assert "1adv001" not in ids and "1wrn001" not in ids and "1adv002" in ids


def test_it_reads_the_librarys_mix_of_kinds_through_bright_data():
    client = FakeBrightData(KETTLE_POSTS)
    threads = BrightDataSource(client).find_raw_threads(parse_query(KETTLE), limit=6, mix=config.LIBRARY_MIX)
    ids = {t.id for t in threads}
    # The long-term thread and a warning are in the mix (at most 2 threads per subreddit, as for every source).
    assert "1lng001" in ids and ids & {"1wrn001", "1wrn002"}
    assert all(t.read_from == "bright_data" for t in threads)
    assert client.read == [t.id for t in threads]


def test_reads_stop_before_the_record_budget_and_say_so():
    # Discovery costs 7 records here (one per post found); each read costs 1 for the post and 1 per comment Reddit
    # counted (31 to 61 here). A budget of 100 can't hold three reads.
    client = FakeBrightData(KETTLE_POSTS)
    source = BrightDataSource(client, max_records=100)
    threads = source.find_raw_threads(parse_query(KETTLE), limit=3, mix=None)
    assert 1 <= len(threads) < 3 and client.used <= 100
    assert source.not_read and "record" in source.notes[-1]


def test_by_default_the_budget_keeps_a_reserve_for_live_checks():
    reserve = config.BRIGHT_DATA_ADD_RECORD_RESERVE
    client = FakeBrightData(KETTLE_POSTS, used=config.BRIGHT_DATA_MONTHLY_RECORDS - reserve - 10)
    with pytest.raises(BrightDataError) as refused:
        BrightDataSource(client).find_raw_threads(parse_query(KETTLE), limit=3, mix=None)
    assert "reserve" in str(refused.value) and client.searches == []  # refused before anything was spent


def test_a_request_module_1_cant_place_spends_nothing():
    client = FakeBrightData(KETTLE_POSTS)
    assert BrightDataSource(client).find_raw_threads(parse_query("best laptop for uni"), limit=6) == []
    assert client.searches == [] and client.used == 0


# --- Never stuck: Arctic Shift first, Bright Data when it's down ---

class DownArchive:
    def rank_candidates(self, query):
        raise ArcticShiftError("Arctic Shift answered 522")

    def find_raw_threads(self, query, limit=3, mix=None, fill=True):
        raise ArcticShiftError("Arctic Shift answered 522")


class WorkingArchive:
    def __init__(self):
        self.asked = 0

    def find_raw_threads(self, query, limit=3, mix=None, fill=True):
        self.asked += 1
        return [Thread.model_validate(make_thread(id="1arc001", title="Kettle advice", community="BuyItForLife",
                                                  category="kitchen") | {"read_from": "arctic_shift"})]


def test_the_fallback_turns_to_bright_data_when_arctic_shift_is_down():
    bright = FakeBrightData(KETTLE_POSTS)
    source = FallbackSource(DownArchive(), BrightDataSource(bright))
    threads = source.find_raw_threads(parse_query(KETTLE), limit=6, mix=config.LIBRARY_MIX)
    assert threads and all(t.read_from == "bright_data" for t in threads)
    assert "Arctic Shift" in source.notes[0] and "Bright Data" in source.notes[0]


def test_the_fallback_never_spends_bright_data_records_when_arctic_shift_works():
    bright, archive = FakeBrightData(KETTLE_POSTS), WorkingArchive()
    threads = FallbackSource(archive, BrightDataSource(bright)).find_raw_threads(parse_query(KETTLE), limit=6)
    assert [t.id for t in threads] == ["1arc001"] and bright.used == 0 and bright.searches == []


def test_the_default_reader_is_auto():
    assert config.LIBRARY_READER == "auto" and "auto" in library.READERS and "bright_data" in library.READERS


# --- The library's add, through Bright Data ---

def test_add_through_bright_data_saves_new_threads_and_skips_saved_ones(tmp_path):
    saved = make_thread(id="1adv001", title="Which electric kettle should I buy?", community="BuyItForLife",
                        category="kitchen")
    (tmp_path / "threads").mkdir(parents=True)
    (tmp_path / "threads" / "1adv001.json").write_text(json.dumps(saved), encoding="utf-8")
    client = FakeBrightData(KETTLE_POSTS)
    source = library.bright_data_source(tmp_path, client)
    result = add(KETTLE, source, tmp_path, limit=3, mix=None)
    assert "1adv001" not in client.read  # already in the library: not read again, no records spent
    assert result.threads and all((tmp_path / "threads" / f"{t.id}.json").exists() for t in result.threads)


def test_add_never_reads_a_gold_thread_noemi_hasnt_labelled(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "unlabelled_gold_ids", lambda: {"1adv002"})
    client = FakeBrightData(KETTLE_POSTS)
    add(KETTLE, library.bright_data_source(tmp_path, client), tmp_path, limit=6, mix=None)
    assert "1adv002" not in client.read


def test_command_line_add_with_the_bright_data_reader(tmp_path, capsys):
    client = FakeBrightData(KETTLE_POSTS)
    status = library.main(["add", "--reader", "bright_data", "--limit", "2", KETTLE], client=_NoParse(),
                          folder=tmp_path, bright_data=client)
    out = capsys.readouterr().out
    assert status == 0 and "Saved 2 threads" in out and "Bright Data records used this month" in out


class _NoParse:
    """A Parse client that must never be used: the Bright Data reader spends no Parse credit."""

    def get_thread(self, *args):
        raise AssertionError("Parse must not be called")

    def search(self, *args):
        raise AssertionError("Parse must not be called")

    def credits_used_this_month(self):
        return 0


# --- refresh, through Bright Data ---

def saved_thread(tmp_path: Path, thread_id: str, days_old: int, read_from: str = "parse") -> None:
    comments = [make_comment(f"c{thread_id}{i}", thread_id=thread_id, body=f"My kettle lasted {i + 2} years.",
                             created_at=(NOW - timedelta(days=59)).isoformat()) for i in range(3)]
    thread = make_thread(id=thread_id, title="Kettle advice", community="BuyItForLife", category="kitchen",
                         url=f"https://www.reddit.com/r/BuyItForLife/comments/{thread_id}/", num_comments=3,
                         comments=comments, collected_at=(NOW - timedelta(days=days_old)).isoformat(),
                         created_at=(NOW - timedelta(days=60)).isoformat())
    (tmp_path / "threads").mkdir(parents=True, exist_ok=True)
    (tmp_path / "threads" / f"{thread_id}.json").write_text(json.dumps(thread | {"read_from": read_from}),
                                                            encoding="utf-8")


def test_refresh_reads_due_threads_through_bright_data_and_merges_them(tmp_path):
    saved_thread(tmp_path, "1due001", days_old=40)
    saved_thread(tmp_path, "1new001", days_old=5)
    posts = [found("1due001", "Kettle advice", 3), found("1new001", "Kettle advice", 3)]
    client = FakeBrightData(posts)
    result = refresh(folder=tmp_path, now=NOW, reader="bright_data", bright_data=client)
    assert result.refreshed == ["1due001"] and result.skipped == ["1new001"]
    assert client.read == ["1due001"] and result.records_used == 4
    stored = Thread.model_validate_json((tmp_path / "threads" / "1due001.json").read_text(encoding="utf-8"))
    assert stored.checked_live_at is not None


def test_refresh_stops_at_its_record_cap(tmp_path):
    saved_thread(tmp_path, "1due001", days_old=40)
    saved_thread(tmp_path, "1due002", days_old=41)
    posts = [found("1due001", "Kettle advice", 3), found("1due002", "Kettle advice", 3)]
    result = refresh(folder=tmp_path, now=NOW, reader="bright_data", bright_data=FakeBrightData(posts), max_records=5)
    assert len(result.refreshed) == 1 and result.capped and result.not_tried


def test_refresh_reads_through_bright_data_by_default():
    assert config.REFRESH_READER == "bright_data"


# --- Reading together (10 Oct 2026) ---

class BatchingFake(FakeBrightData):
    """A fake that can also read ahead in one go, as the real client's prefetch does."""

    def __init__(self, posts, **kwargs):
        super().__init__(posts, **kwargs)
        self.prefetched: list[list[tuple[str, int]]] = []

    def prefetch(self, threads):
        self.prefetched.append(list(threads))
        return len(threads)


def test_add_reads_its_chosen_threads_together():
    client = BatchingFake(KETTLE_POSTS)
    threads = BrightDataSource(client).find_raw_threads(parse_query(KETTLE), limit=3, mix=None)
    [asked] = client.prefetched
    assert [url for url, _ in asked] == [f"https://www.reddit.com/r/{t.community}/comments/{t.id}/" for t in threads]


def test_refresh_reads_due_threads_together_through_the_real_client(tmp_path):
    from engine.tests.test_bright_data import batch_of, make_client

    links, service = batch_of("1bat001", "1bat002", "1bat003")
    for link in links:
        post_id = link.split("/comments/")[1].split("/")[0]
        comments = [make_comment(f"c{post_id}{i}", thread_id=post_id, body=f"Comment {i} on {post_id}.",
                                 url=f"https://www.reddit.com/r/SkincareAddiction/comments/{post_id}/comment/c{post_id}{i}/",
                                 created_at=(NOW - timedelta(days=59)).isoformat()) for i in range(2)]
        thread = make_thread(id=post_id, url=link, num_comments=2, comments=comments,
                             collected_at=(NOW - timedelta(days=40)).isoformat(),
                             created_at=(NOW - timedelta(days=60)).isoformat())
        (tmp_path / "threads").mkdir(parents=True, exist_ok=True)
        (tmp_path / "threads" / f"{post_id}.json").write_text(json.dumps(thread), encoding="utf-8")
    client = make_client(tmp_path, service)
    result = refresh(folder=tmp_path, now=NOW, reader="bright_data", bright_data=client)
    assert sorted(result.refreshed) == ["1bat001", "1bat002", "1bat003"]
    assert len(service.triggered()) == 2  # one job for the posts, one for the comments: not six


# --- An outage is remembered for a while (10 Oct 2026) ---
# Each add waited about 4 minutes for Arctic Shift to fail before turning to Bright Data. After a failure, the fallback
# goes straight to Bright Data for ARCHIVE_DOWN_MINUTES, then tries Arctic Shift again.

class CountingDownArchive(DownArchive):
    def __init__(self):
        self.asked = 0

    def find_raw_threads(self, query, limit=3, mix=None, fill=True):
        self.asked += 1
        return super().find_raw_threads(query, limit, mix, fill)


def test_a_failure_is_remembered_so_the_next_add_doesnt_wait_for_arctic_shift(tmp_path):
    memo = tmp_path / "archive_down.json"
    archive = CountingDownArchive()
    clock = [NOW]
    first = FallbackSource(archive, BrightDataSource(FakeBrightData(KETTLE_POSTS)), memo=memo, clock=lambda: clock[0])
    first.find_raw_threads(parse_query(KETTLE), limit=2, mix=None)
    assert archive.asked == 1 and memo.exists()
    clock[0] = NOW + timedelta(minutes=10)
    second = FallbackSource(archive, BrightDataSource(FakeBrightData(KETTLE_POSTS)), memo=memo, clock=lambda: clock[0])
    assert second.find_raw_threads(parse_query(KETTLE), limit=2, mix=None)
    assert archive.asked == 1  # not asked again: it failed 10 minutes ago
    assert "10 minutes ago" in second.notes[0]
    clock[0] = NOW + timedelta(minutes=config.ARCHIVE_DOWN_MINUTES + 1)
    third = FallbackSource(archive, BrightDataSource(FakeBrightData(KETTLE_POSTS)), memo=memo, clock=lambda: clock[0])
    third.find_raw_threads(parse_query(KETTLE), limit=2, mix=None)
    assert archive.asked == 2  # long enough ago: tried again


def test_a_working_archive_clears_the_memory(tmp_path):
    memo = tmp_path / "archive_down.json"
    memo.write_text(json.dumps({"failed_at": (NOW - timedelta(hours=2)).isoformat()}), encoding="utf-8")
    source = FallbackSource(WorkingArchive(), BrightDataSource(FakeBrightData(KETTLE_POSTS)), memo=memo,
                            clock=lambda: NOW)
    source.find_raw_threads(parse_query(KETTLE), limit=2)
    assert not memo.exists()
