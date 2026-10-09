"""Commenter profiles: each writer's standing filled in from Arctic Shift. Every test uses a fake archive: no network.

Every writer, number, flair and thread here is made up (factories.py). No test reads data/.
"""

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest

from engine import config, profiles
from engine.arctic_shift import ArcticShiftClient
from engine.credibility import score_voice
from engine.extract import extracted_dir
from engine.models import Thread
from engine.profiles import warm, with_profiles
from engine.tests.factories import make_comment, make_thread, write_gold
from engine.tests.test_arctic_shift import FakeClock


def unix(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


def numbers(first_comment="2016-01-01", first_post="2017-06-01", karma=10_000, comments=900, posts=100) -> dict:
    """One writer's numbers as users/search answers them (its "_meta")."""
    return {
        "earliest_comment_at": unix(first_comment) if first_comment else None,
        "earliest_post_at": unix(first_post) if first_post else None,
        "last_comment_at": unix("2026-09-01"), "last_post_at": unix("2026-08-01"),
        "num_comments": comments, "num_posts": posts, "post_karma": karma // 5, "comment_karma": karma - karma // 5,
        "total_karma": karma,
    }


WRITERS = {
    "test_derm": numbers(),  # 10 years active, 10 karma per contribution
    "test_newbie": numbers(first_comment="2025-02-20", first_post=None, karma=12, comments=30, posts=0),
}
FLAIRS = {"c1aaaa": "Dermatologist", "c3cccc": "Dermatologist", "c2bbbb": None}


class FakeArchive:
    """A fake Arctic Shift: users/search answers from `writers`, comments/ids from `flairs`.

    `failing` lists the writers whose look-up fails; "*" fails them all, "flairs" fails the flair look-ups.
    """

    def __init__(self, writers=None, flairs=None, failing=()):
        self.writers = WRITERS if writers is None else writers
        self.flairs = FLAIRS if flairs is None else flairs
        self.failing = set(failing)
        self.requests = []

    def __call__(self, url, headers):
        self.requests.append(url)
        path, query = urlparse(url).path, parse_qs(urlparse(url).query)
        if path.endswith("users/search"):
            name = query["author"][0]
            if name in self.failing or "*" in self.failing:
                return 500, json.dumps({"error": "server error"}).encode()
            found = [{"author": name, "id": "t2_fake", "_meta": self.writers[name]}] if name in self.writers else []
            return 200, json.dumps({"data": found}).encode()
        if path.endswith("comments/ids"):
            if "flairs" in self.failing:
                return 500, json.dumps({"error": "server error"}).encode()
            asked = query["ids"][0].split(",")
            found = [{"id": cid, "author_flair_text": self.flairs[cid]} for cid in asked if cid in self.flairs]
            return 200, json.dumps({"data": found}).encode()
        raise AssertionError(f"unexpected call: {url}")

    @property
    def writers_asked(self) -> list[str]:
        return [parse_qs(urlparse(url).query)["author"][0] for url in self.requests if "users/search" in url]

    @property
    def comments_asked(self) -> list[str]:
        return [cid for url in self.requests if "comments/ids" in url for cid in parse_qs(urlparse(url).query)["ids"][0].split(",")]


def plain(name: str) -> dict:
    return {"name": name}  # what Parse gives: a name, nothing else


def parse_thread(**overrides) -> dict:
    """A thread as saved from Parse: writers with names only. test_derm writes two comments; one comment is deleted."""
    comments = [
        make_comment("c1aaaa", author=plain("test_derm"), body="I've used the CeraVe SA Cleanser for 2 years. Gentle, but it dries me out in winter."),
        make_comment("c2bbbb", parent_id="c1aaaa", author=plain("test_newbie"), body="Same here, 3 years and counting."),
        make_comment("c3cccc", author=plain("test_derm"), body="Paula's Choice 2% BHA beats every acid toner I've tried.",
                     created_at="2025-03-05T10:00:00Z"),
        make_comment("c4dddd", author=None, body="[deleted]", status="deleted"),
    ]
    return make_thread(author=plain("test_op"), comments=comments) | overrides


def make_client(tmp_path, archive):
    clock = FakeClock()
    return ArcticShiftClient(cache_dir=tmp_path / "cache", fetch=archive, clock=clock, sleep=clock.sleep)


def fill(tmp_path, archive=None, thread=None, **options):
    archive = archive or FakeArchive()
    thread = Thread.model_validate(thread or parse_thread())
    return with_profiles(thread, make_client(tmp_path, archive), **options), archive


def writer(result, comment_id):
    return next(c.author for c in result.thread.comments if c.id == comment_id)


# --- Filling in one thread ---

def test_writers_get_active_since_karma_contributions_and_flair(tmp_path):
    result, _ = fill(tmp_path)
    derm = writer(result, "c1aaaa")
    assert derm.account_created_at == datetime(2016, 1, 1, tzinfo=UTC)  # the earlier of first comment and first post
    assert derm.karma == 10_000  # total karma
    assert derm.contributions == 1000  # comments + posts
    assert derm.flair == "Dermatologist"  # from this thread's comments
    assert writer(result, "c3cccc") == derm  # every comment by the same writer
    newbie = writer(result, "c2bbbb")
    assert (newbie.account_created_at, newbie.karma, newbie.contributions, newbie.flair) == (
        datetime(2025, 2, 20, tzinfo=UTC), 12, 30, None)
    assert (result.filled, result.unknown, result.failed, result.flairs) == (2, 0, 0, 1)


def test_a_first_post_before_the_first_comment_sets_active_since(tmp_path):
    archive = FakeArchive(writers={"test_derm": numbers(first_comment="2019-01-01", first_post="2014-05-01")})
    result, _ = fill(tmp_path, archive)
    assert writer(result, "c1aaaa").account_created_at == datetime(2014, 5, 1, tzinfo=UTC)


def test_the_thread_passed_in_and_every_comment_text_stay_as_they_were(tmp_path):
    thread = Thread.model_validate(parse_thread())
    before = thread.model_dump()
    result = with_profiles(thread, make_client(tmp_path, FakeArchive()))
    assert thread.model_dump() == before
    assert [c.body for c in result.thread.comments] == [c.body for c in thread.comments]
    assert result.thread.author == thread.author  # the post's writer: module 5 scores comments only


def test_deleted_accounts_are_skipped_and_each_writer_is_asked_once(tmp_path):
    result, archive = fill(tmp_path)
    assert archive.writers_asked == ["test_derm", "test_newbie"]
    assert writer(result, "c4dddd") is None


def test_a_writer_the_archive_doesnt_know_is_left_as_is(tmp_path):
    result, _ = fill(tmp_path, FakeArchive(writers={"test_derm": numbers()}))
    assert writer(result, "c2bbbb").model_dump() == plain("test_newbie") | {
        "account_created_at": None, "karma": None, "flair": None, "contributions": None}
    assert (result.filled, result.unknown) == (1, 1)


def test_a_failed_look_up_leaves_that_writer_as_is_and_carries_on(tmp_path):
    result, _ = fill(tmp_path, FakeArchive(failing={"test_derm"}))
    derm = writer(result, "c1aaaa")
    assert (derm.account_created_at, derm.karma, derm.contributions) == (None, None, None)
    assert derm.flair == "Dermatologist"  # flairs come from another call, which worked
    assert writer(result, "c2bbbb").karma == 12
    assert (result.filled, result.failed, result.stopped) == (1, 1, False)
    assert "500" in result.problems[0]


def test_failures_in_a_row_stop_the_look_ups_without_crashing(tmp_path):
    names = [f"test_writer_{n}" for n in range(6)]
    comments = [make_comment(f"c{n}xxxx", author=plain(name), body="I like it.") for n, name in enumerate(names)]
    result, archive = fill(tmp_path, FakeArchive(failing={"*"}), thread=parse_thread(comments=comments))
    assert len(archive.writers_asked) == config.PROFILE_FAILURES_IN_A_ROW_TO_STOP  # a 500 gets no retry
    assert result.failed == 6 and result.filled == 0 and result.stopped
    assert all(c.author.karma is None for c in result.thread.comments)


def test_when_flairs_fail_the_numbers_are_still_filled(tmp_path):
    result, _ = fill(tmp_path, FakeArchive(failing={"flairs"}))
    assert writer(result, "c1aaaa").karma == 10_000 and writer(result, "c1aaaa").flair is None
    assert result.flairs == 0 and result.problems


def test_an_archive_that_starts_after_a_comment_seen_here_leaves_the_age_unknown(tmp_path):
    # The archive is missing part of this writer's history, so their first activity in it says nothing about their age.
    archive = FakeArchive(writers={"test_derm": numbers(first_comment="2025-03-04", first_post=None)})
    derm = writer(fill(tmp_path, archive)[0], "c1aaaa")  # c1aaaa was written on 2 March 2025
    assert derm.account_created_at is None
    assert derm.karma == 10_000


def test_what_is_already_known_is_kept(tmp_path):
    comments = [make_comment("c1aaaa", author={"name": "test_derm", "karma": 7, "flair": "Esthetician"}, body="Nice.")]
    derm = writer(fill(tmp_path, thread=parse_thread(comments=comments))[0], "c1aaaa")
    assert (derm.karma, derm.flair, derm.contributions) == (7, "Esthetician", 1000)


def test_comment_ids_choose_whose_writers_are_looked_up(tmp_path):
    result, archive = fill(tmp_path, comment_ids=(cid for cid in ["c3cccc"]))  # any list of ids, even a one-off
    assert archive.writers_asked == ["test_derm"]
    assert archive.comments_asked == ["c3cccc"]
    assert writer(result, "c1aaaa").karma == 10_000  # the same writer's other comment is filled too
    assert writer(result, "c2bbbb").karma is None


def test_the_next_answer_comes_from_the_cache(tmp_path):
    archive = FakeArchive()
    client = make_client(tmp_path, archive)
    thread = Thread.model_validate(parse_thread())
    first = with_profiles(thread, client)
    calls = len(archive.requests)
    again = with_profiles(thread, client)
    assert len(archive.requests) == calls
    assert again.thread == first.thread


def test_profiles_let_module_5s_standing_signs_fire(tmp_path):
    thread = Thread.model_validate(parse_thread())
    before = score_voice(thread.comments[0], thread)
    assert not {"established member", "well-regarded account", "expert flair"} & set(before.tags)

    filled = fill(tmp_path)[0].thread
    derm = score_voice(filled.comments[0], filled)
    assert {"established member", "well-regarded account", "expert flair"} <= set(derm.tags)
    newbie = score_voice(filled.comments[1], filled)  # active for 10 days when it wrote this, 0.4 karma a contribution
    assert {"new account", "low karma for its activity"} <= set(newbie.tags)
    assert newbie.level == "low"


# --- Warming the cache for a folder ---

def mention(comment_id: str, quote: str) -> dict:
    return {"comment_id": comment_id, "product": "CeraVe SA Cleanser", "category": "skincare", "stance": "recommend", "quote": quote}


def library_folder(tmp_path, mentions: list[dict]):
    """A threads/ folder holding the Parse thread, with an extraction next to it (data/<set>/extracted/)."""
    write_gold(tmp_path, [parse_thread()], voices=None, mentions=None)
    threads_dir = tmp_path / "threads"
    extraction = {"thread_id": "1fake01", "instructions_version": "extract-v1", "extracted_at": "2026-10-08T10:00:00Z",
                  "extractor": "claude-code", "mentions": mentions}
    extracted_dir(threads_dir).mkdir()
    (extracted_dir(threads_dir) / "1fake01.json").write_text(json.dumps(extraction), encoding="utf-8")
    return threads_dir


KEPT = mention("c1aaaa", "I've used the CeraVe SA Cleanser for 2 years.")
NEWBIE_KEPT = mention("c2bbbb", "Same here, 3 years and counting.")
REJECTED = mention("c2bbbb", "A quote that isn't in the comment.")  # dropped by the check, so its writer isn't looked up


def test_warm_looks_up_only_the_writers_of_kept_mentions(tmp_path):
    archive = FakeArchive()
    lines = []
    result = warm(library_folder(tmp_path, [KEPT, REJECTED]), make_client(tmp_path, archive), say=lines.append)
    assert archive.writers_asked == ["test_derm"]
    assert archive.comments_asked == ["c1aaaa"]
    assert (result.writers, result.found, result.unknown, result.failed) == (1, 1, 0, 0)
    out = "\n".join(lines)
    assert "1 writer" in out and "10 s" in out and "2 calls" in out
    assert "Found in the archive: 1 of 1" in out


def test_warm_changes_no_file_in_the_folder(tmp_path):
    threads_dir = library_folder(tmp_path, [KEPT, NEWBIE_KEPT])
    files = {p: p.read_bytes() for p in tmp_path.rglob("*.json") if "cache" not in p.parts}
    warm(threads_dir, make_client(tmp_path, FakeArchive()), say=lambda line: None)
    assert {p: p.read_bytes() for p in tmp_path.rglob("*.json") if "cache" not in p.parts} == files


def test_warm_limit_looks_up_at_most_n_new_writers(tmp_path):
    threads_dir = library_folder(tmp_path, [KEPT, NEWBIE_KEPT])
    archive = FakeArchive()
    client = make_client(tmp_path, archive)
    lines = []
    first = warm(threads_dir, client, limit=1, say=lines.append)
    assert archive.writers_asked == ["test_derm"]
    assert first.left_for_later == 1 and "1 more writer" in "\n".join(lines)
    second = warm(threads_dir, client, limit=1, say=lines.append)  # the next run picks up where this one stopped
    assert archive.writers_asked == ["test_derm", "test_newbie"]
    assert (second.found, second.left_for_later) == (2, 0)


def test_warm_again_costs_nothing(tmp_path):
    threads_dir = library_folder(tmp_path, [KEPT])
    archive = FakeArchive()
    client = make_client(tmp_path, archive)
    warm(threads_dir, client, say=lambda line: None)
    calls = len(archive.requests)
    lines = []
    result = warm(threads_dir, client, say=lines.append)
    assert len(archive.requests) == calls
    assert result.found == 1
    assert "1 already in the 48-hour cache" in "\n".join(lines)


def test_warm_reports_failures_and_carries_on(tmp_path):
    lines = []
    result = warm(library_folder(tmp_path, [KEPT, NEWBIE_KEPT]), make_client(tmp_path, FakeArchive(failing={"test_derm"})),
                  say=lines.append)
    assert (result.found, result.failed) == (1, 1)
    assert "failed" in "\n".join(lines)


def test_command_line_warm(tmp_path, capsys):
    threads_dir = library_folder(tmp_path, [KEPT])
    assert profiles.main(["warm", str(threads_dir), "--limit", "5"], client=make_client(tmp_path, FakeArchive())) == 0
    assert "Found in the archive: 1 of 1" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [[], ["warm"], ["cool", "x"], ["warm", "x", "--limit"], ["warm", "x", "--limit", "0"],
                                  ["warm", "x", "--limit", "many"], ["warm", "x", "y"], ["warm", "x", "--fast"]])
def test_command_line_explains_itself_when_typed_wrong(argv, capsys, tmp_path):
    assert profiles.main(argv, client=make_client(tmp_path, FakeArchive())) == 2
    assert "warm" in capsys.readouterr().out


def test_command_line_reports_a_missing_folder(tmp_path, capsys):
    assert profiles.main(["warm", str(tmp_path / "nowhere")], client=make_client(tmp_path, FakeArchive())) == 1
    assert "missing" in capsys.readouterr().out


# --- At answer time: only what is already in the cache (9 Oct 2026) ---

class CountingClient:
    """A stand-in client: one writer and one comment are cached; every call that would reach Arctic Shift is counted."""

    def __init__(self):
        self.calls = 0

    def uncached_users(self, authors):
        return [a for a in authors if a != "cached_writer"]

    def uncached_comments(self, comment_ids):
        return [c for c in comment_ids if c != "c1aaaa"]

    def user_stats(self, author):
        if author != "cached_writer":
            self.calls += 1
        return {"num_comments": 900, "num_posts": 10, "total_karma": 9000, "earliest_comment_at": 1500000000}

    def comment_flairs(self, comment_ids):
        ids = list(comment_ids)
        self.calls += sum(c != "c1aaaa" for c in ids)
        return {c: "Chef" for c in ids}


def test_cached_only_never_asks_arctic_shift():
    from engine.profiles import CachedOnly

    client = CountingClient()
    cached = CachedOnly(client)
    assert cached.user_stats("cached_writer")["num_comments"] == 900
    assert cached.user_stats("someone_else") is None  # not warmed yet: no profile, no call
    assert cached.comment_flairs(["c1aaaa", "c2bbbb"]) == {"c1aaaa": "Chef"}
    assert client.calls == 0


# --- Kept with the library (Noemi, 9 Oct 2026: refreshed monthly, not only 48 hours) ---

from engine.profiles import ProfileStore, StoredProfiles  # noqa: E402


def store_at(tmp_path, clock=None):
    return ProfileStore(tmp_path / "profiles.json", clock=clock or FakeClock())


def test_the_store_keeps_numbers_flairs_and_unknown_writers(tmp_path):
    store = store_at(tmp_path)
    store.put_user("Test_Derm", WRITERS["test_derm"])
    store.put_user("gone_writer", None)  # not in the archive: remembered, so it isn't asked again for a month
    store.put_flair("c1aaaa", "Dermatologist")
    store.save()
    again = store_at(tmp_path)
    assert again.user_stats("test_derm") == WRITERS["test_derm"]  # names ignore capitals, as on Reddit
    assert again.user_stats("gone_writer") is None
    assert again.user_stats("never_seen") is profiles.MISSING
    assert again.flair("c1aaaa") == "Dermatologist"


def test_entries_older_than_the_library_refresh_are_missing(tmp_path):
    clock = FakeClock()
    store = store_at(tmp_path, clock)
    store.put_user("test_derm", WRITERS["test_derm"])
    clock.now += timedelta(days=config.LIBRARY_REFRESH_DAYS + 1)
    assert store.user_stats("test_derm") is profiles.MISSING


def test_warm_with_a_store_keeps_the_answers_and_asks_nothing_next_time(tmp_path):
    threads_dir = library_folder(tmp_path, [KEPT, NEWBIE_KEPT])
    store = store_at(tmp_path)
    warm(threads_dir, make_client(tmp_path, FakeArchive(writers={"test_derm": numbers()})), say=lambda line: None, store=store)
    assert store.user_stats("test_derm")["num_comments"] == 900 and store.user_stats("test_newbie") is None
    assert (tmp_path / "profiles.json").exists()
    archive = FakeArchive()
    fresh_cache = ArcticShiftClient(cache_dir=tmp_path / "other_cache", fetch=archive, clock=FakeClock(), sleep=lambda s: None)
    warm(threads_dir, fresh_cache, say=lambda line: None, store=store_at(tmp_path))
    assert archive.requests == []  # everything was in the store


def test_warm_with_a_store_drops_writers_no_longer_in_the_library(tmp_path):
    store = store_at(tmp_path)
    store.put_user("left_the_library", WRITERS["test_derm"])
    store.save()
    warm(library_folder(tmp_path, [KEPT]), make_client(tmp_path, FakeArchive()), say=lambda line: None, store=store_at(tmp_path))
    assert store_at(tmp_path).user_stats("left_the_library") is profiles.MISSING


def test_stored_profiles_answer_without_calls_then_fall_back_to_the_cache(tmp_path):
    store = store_at(tmp_path)
    store.put_user("test_derm", WRITERS["test_derm"])
    store.put_flair("c1aaaa", "Dermatologist")
    client = CountingClient()
    stored = StoredProfiles(store, client)
    assert stored.user_stats("test_derm") == WRITERS["test_derm"]
    assert stored.user_stats("cached_writer")["num_comments"] == 900  # not stored, but in the cache
    assert stored.user_stats("someone_else") is None
    assert stored.comment_flairs(["c1aaaa", "c2bbbb"]) == {"c1aaaa": "Dermatologist"}
    assert client.calls == 0


def test_writers_of_what_to_look_for_notes_are_looked_up_too(tmp_path):
    # Review finding 7: a note's writer was never looked up, so their notes kept a voice no profile could lower.
    threads_dir = library_folder(tmp_path, [])
    extraction = json.loads((extracted_dir(threads_dir) / "1fake01.json").read_text())
    extraction["notes"] = [{"comment_id": "c2bbbb", "about": "fragrance-free cleanser", "stance": "recommend",
                            "quote": "Same here, 3 years and counting."}]
    (extracted_dir(threads_dir) / "1fake01.json").write_text(json.dumps(extraction))
    assert profiles.writers_with_kept_mentions(threads_dir) == {"test_newbie": ["c2bbbb"]}
