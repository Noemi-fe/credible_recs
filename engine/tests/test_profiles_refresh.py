"""Refreshing the stored writers' profiles in chunks, the writers of quoted comments first and the stalest first (25 Oct 2026,
the verify2 builder; docs/verify-bfs-2026-10-25.md: 13,283 of the 14,328 stored writers pass their 30 days on 9 to 16 Nov).

An expired profile is not dropped and not kept: the store answers MISSING, so module 5 sees the writer as if the archive
didn't know them, with no standing for or against them. On the 278-request sweep that changed 77 of 219 answers' picks and
the high-credibility voices behind the picks fell from 2,501 to 699 (docs/verify2-2026-10-25/), so the store is refreshed
before 9 Nov: `python -m engine.profiles warm <threads> --limit 300 [--quoted FILE]`, over and over until nothing is left.
Every writer, number and thread here is made up (test_profiles.py's factories): no test reads data/ or reaches the network.
"""

import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from engine import config, profiles
from engine.extract import extracted_dir
from engine.profiles import ProfileStore, StoredProfiles, quoted_comment_ids, warm
from engine.tests.factories import make_comment, make_thread, write_gold
from engine.tests.test_arctic_shift import FakeClock
from engine.tests.test_profiles import (KEPT, NEWBIE_KEPT, FakeArchive, library_folder, make_client, mention, numbers,
                                        plain, store_at)


def say(lines=None):
    return (lines.append if lines is not None else (lambda line: None))


def many_writers(tmp_path, count: int):
    """A threads folder with `count` writers, each with one comment (c<i>aaaa) holding a kept mention, and the archive
    that knows them all."""
    comments = [make_comment(f"c{i}aaaa", author=plain(f"writer{i}"),
                             body=f"I've used the CeraVe SA Cleanser for {i} years.") for i in range(1, count + 1)]
    write_gold(tmp_path, [make_thread(author=plain("test_op"), comments=comments)], voices=None, mentions=None)
    threads_dir = tmp_path / "threads"
    mentions = [mention(f"c{i}aaaa", f"I've used the CeraVe SA Cleanser for {i} years.") for i in range(1, count + 1)]
    extraction = {"thread_id": "1fake01", "instructions_version": "extract-v1", "extracted_at": "2026-10-08T10:00:00Z",
                  "extractor": "claude-code", "mentions": mentions}
    extracted_dir(threads_dir).mkdir()
    (extracted_dir(threads_dir) / "1fake01.json").write_text(json.dumps(extraction), encoding="utf-8")
    archive = FakeArchive(writers={f"writer{i}": numbers() for i in range(1, count + 1)},
                          flairs={f"c{i}aaaa": None for i in range(1, count + 1)})
    return threads_dir, archive


# --- Which writers first ---

def test_the_writers_of_quoted_comments_are_asked_first(tmp_path):
    threads_dir = library_folder(tmp_path, [KEPT, NEWBIE_KEPT])
    archive = FakeArchive()
    warm(threads_dir, make_client(tmp_path, archive), say=say(), quoted={"c2bbbb"})
    assert archive.writers_asked == ["test_newbie", "test_derm"]  # the thread's own order is the other way round


def stored_days_ago(store, clock, **ages):
    """Puts each writer in the store as if looked up that many days before now (clock.now is left as it was)."""
    now = clock.now
    for name, days in ages.items():
        clock.now = now - timedelta(days=days)
        store.put_user(name, numbers())
    clock.now = now


def test_stored_writers_go_stalest_first_and_those_never_asked_before_come_last(tmp_path):
    # An expired entry is what the cliff of 9 to 16 Nov is made of: answers keep their standing signs only while it is
    # looked up again in time. A writer never looked up is neutral already, so it loses nothing by waiting.
    threads_dir, archive = many_writers(tmp_path, 4)
    clock = FakeClock()
    store = store_at(tmp_path, clock)
    stored_days_ago(store, clock, writer1=5, writer2=config.LIBRARY_REFRESH_DAYS + 5, writer3=config.LIBRARY_REFRESH_DAYS + 15)
    assert store.user_stats("writer1") is not profiles.MISSING  # 5 days old: fresh, not asked at all
    warm(threads_dir, make_client(tmp_path, archive), say=say(), store=store)
    assert archive.writers_asked == ["writer3", "writer2", "writer4"]  # the oldest first, the never asked last


def test_a_writer_looked_up_before_the_refresh_time_is_asked_again_though_it_has_not_expired(tmp_path):
    threads_dir, archive = many_writers(tmp_path, 3)
    clock = FakeClock()
    store = store_at(tmp_path, clock)
    stored_days_ago(store, clock, writer1=20, writer2=10, writer3=2)  # none expired (30 days)
    when = clock.now - timedelta(days=5)
    warm(threads_dir, make_client(tmp_path, archive), say=say(), store=store, refresh_before=when)
    assert archive.writers_asked == ["writer1", "writer2"]  # looked up before the refresh time; writer3 is newer
    again = FakeArchive(writers=archive.writers, flairs=archive.flairs)
    warm(threads_dir, make_client(tmp_path / "other", again), say=say(), store=store, refresh_before=when)
    assert again.writers_asked == []  # what the refresh found is newer than its time: a run finishes


def test_quoted_writers_come_before_stale_ones_and_each_group_goes_stalest_first(tmp_path):
    threads_dir, archive = many_writers(tmp_path, 4)
    clock = FakeClock()
    store = store_at(tmp_path, clock)
    stored_days_ago(store, clock, writer1=40, writer2=41, writer3=42, writer4=43)  # all expired
    warm(threads_dir, make_client(tmp_path, archive), say=say(), store=store, quoted={"c1aaaa", "c2aaaa"})
    assert archive.writers_asked == ["writer2", "writer1", "writer4", "writer3"]


def test_without_a_store_or_a_quoted_list_the_order_is_as_before(tmp_path):
    threads_dir, archive = many_writers(tmp_path, 3)
    warm(threads_dir, make_client(tmp_path, archive), say=say())
    assert archive.writers_asked == ["writer1", "writer2", "writer3"]


# --- Chunks that carry on where the last stopped ---

def test_a_chunk_of_n_writers_leaves_the_rest_and_the_next_run_carries_on_with_none_asked_twice(tmp_path):
    threads_dir, archive = many_writers(tmp_path, 5)
    client = make_client(tmp_path, archive)
    clock = FakeClock()
    lines = []
    for expected_left in (3, 1, 0):
        store = ProfileStore(tmp_path / "profiles.json", clock=clock)
        result = warm(threads_dir, client, limit=2, say=say(lines), store=store)
        assert result.left_for_later == expected_left
    assert sorted(archive.writers_asked) == [f"writer{i}" for i in range(1, 6)] and len(set(archive.writers_asked)) == 5
    assert all(ProfileStore(tmp_path / "profiles.json", clock=clock).user_stats(f"writer{i}") is not profiles.MISSING
               for i in range(1, 6))


def test_a_run_stopped_half_way_has_kept_what_it_found_so_far(tmp_path, monkeypatch):
    threads_dir, archive = many_writers(tmp_path, 5)
    monkeypatch.setattr(profiles, "SAVE_EVERY", 2)

    class Killed(Exception):
        pass

    real = archive.__call__

    def dies_at_the_fifth(url, headers):
        if "users/search" in url and len(archive.writers_asked) >= 4:  # the fifth look-up never gets an answer
            raise Killed
        return real(url, headers)

    client = make_client(tmp_path, archive)
    client._fetch = dies_at_the_fifth
    with pytest.raises(Killed):
        warm(threads_dir, client, say=say(), store=store_at(tmp_path))
    kept = ProfileStore(tmp_path / "profiles.json", clock=FakeClock())
    found = [f"writer{i}" for i in range(1, 6) if kept.user_stats(f"writer{i}") is not profiles.MISSING]
    assert found == ["writer1", "writer2", "writer3", "writer4"]  # saved every 2: the fourth made the second save


def test_a_chunk_looks_up_the_flairs_of_its_own_writers_only(tmp_path):
    threads_dir, archive = many_writers(tmp_path, 5)
    warm(threads_dir, make_client(tmp_path, archive), limit=2, say=say(), store=store_at(tmp_path))
    assert sorted(archive.comments_asked) == ["c1aaaa", "c2aaaa"]


def test_without_a_limit_every_writers_flairs_are_looked_up_as_before(tmp_path):
    threads_dir, archive = many_writers(tmp_path, 3)
    warm(threads_dir, make_client(tmp_path, archive), say=say(), store=store_at(tmp_path))
    assert sorted(archive.comments_asked) == ["c1aaaa", "c2aaaa", "c3aaaa"]


# --- The store when two runs share it ---

def test_saving_keeps_what_another_run_saved_meanwhile(tmp_path):
    clock = FakeClock()
    first, second = (ProfileStore(tmp_path / "profiles.json", clock=clock) for _ in range(2))
    first.put_user("alpha", numbers())
    first.save()
    second.put_user("beta", numbers())
    second.save()  # it never saw alpha
    both = ProfileStore(tmp_path / "profiles.json", clock=clock)
    assert both.user_stats("alpha") is not profiles.MISSING and both.user_stats("beta") is not profiles.MISSING


def test_the_newer_look_up_wins_when_both_runs_asked_about_the_same_writer(tmp_path):
    clock = FakeClock()
    first, second = (ProfileStore(tmp_path / "profiles.json", clock=clock) for _ in range(2))
    clock.now += timedelta(days=1)
    first.put_user("alpha", numbers(karma=100))
    clock.now += timedelta(days=1)
    second.put_user("alpha", numbers(karma=900))
    second.save()
    first.save()  # saved last, but looked up earlier
    assert ProfileStore(tmp_path / "profiles.json", clock=clock).user_stats("alpha")["total_karma"] == 900


def test_a_writer_dropped_from_the_library_stays_dropped(tmp_path):
    clock = FakeClock()
    store = ProfileStore(tmp_path / "profiles.json", clock=clock)
    store.put_user("alpha", numbers())
    store.put_user("beta", numbers())
    store.put_flair("c1aaaa", "Chef")
    store.save()
    mine = ProfileStore(tmp_path / "profiles.json", clock=clock)
    mine.keep_only(["beta"], [])
    mine.save()
    again = ProfileStore(tmp_path / "profiles.json", clock=clock)
    assert again.user_stats("alpha") is profiles.MISSING and again.user_stats("beta") is not profiles.MISSING
    assert again.flair("c1aaaa") is profiles.MISSING


# --- The command ---

def test_quoted_comment_ids_come_from_links_and_bare_ids():
    text = ("https://www.reddit.com/r/AsianBeauty/comments/1mq4ewt/whats_the_best_exfoliant/n8ob1cm/\n"
            "\n  l5xwgi7  \nhttps://www.reddit.com/r/x/comments/1abc/title/abc123x\n# a comment line\n")
    assert quoted_comment_ids(text) == {"n8ob1cm", "l5xwgi7", "abc123x"}


def test_the_command_takes_a_quoted_list_and_asks_those_writers_first(tmp_path, capsys):
    threads_dir = library_folder(tmp_path, [KEPT, NEWBIE_KEPT])
    listing = tmp_path / "quoted.txt"
    listing.write_text("c2bbbb\n", encoding="utf-8")
    archive = FakeArchive()
    assert profiles.main(["warm", str(threads_dir), "--quoted", str(listing)], client=make_client(tmp_path, archive)) == 0
    assert archive.writers_asked == ["test_newbie", "test_derm"]
    assert "Asked first: 1 writer of quoted comments" in capsys.readouterr().out


def test_a_refresh_looks_up_the_flairs_of_the_writers_it_asks_again_too(tmp_path):
    threads_dir, archive = many_writers(tmp_path, 3)
    clock = FakeClock()
    store = store_at(tmp_path, clock)
    stored_days_ago(store, clock, writer1=20, writer2=2, writer3=20)
    now = clock.now
    for days, cid in ((20, "c1aaaa"), (2, "c2aaaa"), (20, "c3aaaa")):
        clock.now = now - timedelta(days=days)
        store.put_flair(cid, None)
    clock.now = now
    warm(threads_dir, make_client(tmp_path, archive), say=say(), store=store, refresh_before=now - timedelta(days=5))
    assert archive.writers_asked == ["writer1", "writer3"] and sorted(archive.comments_asked) == ["c1aaaa", "c3aaaa"]
    assert store.flair_checked_at("c1aaaa") == now and store.flair_checked_at("c2aaaa") == now - timedelta(days=2)


def test_the_command_takes_a_refresh_time(tmp_path):
    assert profiles._warm_options(["warm", "x", "--refresh-before", "2026-10-25"]) == (
        Path("x"), None, None, datetime(2026, 10, 25, tzinfo=UTC))
    assert profiles._warm_options(["warm", "x", "--refresh-before=2026-10-25T05:30:00Z", "--limit", "3"]) == (
        Path("x"), 3, None, datetime(2026, 10, 25, 5, 30, tzinfo=UTC))


@pytest.mark.parametrize("argv", [["warm", "x", "--refresh-before"], ["warm", "x", "--refresh-before", "soon"]])
def test_the_command_explains_itself_when_the_refresh_time_is_typed_wrong(argv, capsys, tmp_path):
    assert profiles.main(argv, client=make_client(tmp_path, FakeArchive())) == 2
    assert "--refresh-before" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [["warm", "x", "--quoted"], ["warm", "x", "--quoted", "a", "b"]])
def test_the_command_explains_itself_when_the_quoted_list_is_typed_wrong(argv, capsys, tmp_path):
    assert profiles.main(argv, client=make_client(tmp_path, FakeArchive())) == 2
    assert "--quoted" in capsys.readouterr().out


def test_the_command_says_a_quoted_list_it_cant_read(tmp_path, capsys):
    threads_dir = library_folder(tmp_path, [KEPT])
    assert profiles.main(["warm", str(threads_dir), "--quoted", str(tmp_path / "nowhere.txt")],
                         client=make_client(tmp_path, FakeArchive())) == 1
    assert "nowhere.txt" in capsys.readouterr().out


def test_the_sweep_lists_the_comments_its_answers_quote_as_ids_only(tmp_path):
    spec = importlib.util.spec_from_file_location("sweep_tool", Path(__file__).resolve().parents[2] / "eval" / "sweep.py")
    sweep = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sweep)
    out = tmp_path / "sweep.jsonl"
    answer = {"answer": {"picks": [{"quotes": [{"text": "made-up words", "comment_id": "n8ob1cm"}],
                                    "downsides": [{"text": "more made-up words", "comment_id": "l5xwgi7"}]}],
                         "worth_a_look": [{"quotes": [{"text": "x", "comment_id": "n8ob1cm"}]}]}}
    out.write_text(json.dumps({"request": "r", "source": "s", "seconds": 1, "json": answer}) + "\n", encoding="utf-8")
    listing = tmp_path / "quoted.txt"
    sweep.quoted(out, listing)
    assert listing.read_text(encoding="utf-8").split() == ["l5xwgi7", "n8ob1cm"]
