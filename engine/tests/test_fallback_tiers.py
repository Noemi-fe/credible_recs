"""The answers' last two tiers are read every 5 days, not every 40 hours (25 Oct 2026, the verify2 builder;
docs/verify-bfs-2026-10-25.md, option (h): about 1,260 reads a day freed).

An answer's comments come in four tiers (engine/precheck.py): shown, next in line, behind the picks (the products ranked
just behind, which take a place if a pick fails) and next after those. The last two are fallbacks a failed check brings in,
rarely shown. They are now listed by the daily plan one day in config.PLAN_FALLBACK_TIER_DAYS, each comment on its own
day, and the site reads a listed one that has no read in the last 48 hours, as it does a kept comment to verify. The rule is
unchanged: a quote is shown only with a passing check from the last 48 hours, so a fallback quote that has none is checked
at answer time, as any quote not read ahead. Made-up threads and pages: no test reaches the network.
"""

import zlib

import pytest
from collections import Counter
from datetime import datetime, timedelta

from engine import config, precheck
from engine.live_check import LiveChecker
from engine.read_ahead import plan_bytes, read_plan
from engine.tests.fake_google import FakeGoogle
from engine.tests.test_live_check import QUOTE, Clock
from engine.tests.test_precheck import REQUEST, library
from engine.tests.test_precheck_plan import BUCKET, a_checker, never_read, the_plan
from engine.tests.test_read_ahead import PLAN, link, scene  # noqa: F401  (scene is a fixture)


# --- Which comments are listed on which day ---

def test_each_fallback_comment_is_listed_one_day_in_five_on_the_same_day_each_cycle():
    ids = [f"c{n:05d}" for n in range(2_000)]
    start = datetime(2026, 10, 26, 3).date()
    cycle = [[cid for cid in ids if precheck.fallback_due(cid, start + timedelta(days=d))] for d in range(5)]
    assert Counter(cid for day in cycle for cid in day) == Counter(ids)  # every comment once in 5 days...
    assert all(300 <= len(day) <= 500 for day in cycle)  # ...about a fifth a day, whichever day
    again = [cid for cid in ids if precheck.fallback_due(cid, start + timedelta(days=5))]
    assert again == cycle[0]  # and on its day again 5 days later
    assert config.PLAN_FALLBACK_TIER_DAYS == 5


def test_a_comments_day_does_not_change_between_runs_of_the_program():
    # Python's hash() of a string changes with every run; the day comes from a fixed checksum.
    cid = "kx3a9ab"
    day = datetime(2026, 10, 26).date()
    slot = zlib.crc32(cid.encode()) % config.PLAN_FALLBACK_TIER_DAYS
    assert precheck.fallback_due(cid, day) == ((day.toordinal() - slot) % config.PLAN_FALLBACK_TIER_DAYS == 0)


# --- The plan ---

# Two more kettles with enough praise to rank behind the picks: the made-up library then has comments in every tier.
MORE = [("e1aaaa", "1kett01", "Breville kettle", "recommend", "My Breville kettle has lasted 3 years of daily use."),
        ("e1bbbb", "1kett01", "Breville kettle", "recommend", "Breville kettle for 2 years now, no trouble at all."),
        ("e2aaaa", "1kett02", "Breville kettle", "recommend", "I have used the same Breville kettle for 2 years."),
        ("f1aaaa", "1kett01", "Fellow kettle", "recommend", "My Fellow kettle has lasted 2 years of daily use."),
        ("f2aaaa", "1kett02", "Fellow kettle", "recommend", "Fellow kettle for 2 years now, no trouble at all."),
        ("f2bbbb", "1kett02", "Fellow kettle", "recommend", "I have used the same Fellow kettle for 2 years.")]


@pytest.fixture
def more_kettles(monkeypatch):
    from engine.tests import test_precheck as base

    monkeypatch.setattr(base, "COMMENTS", [*base.COMMENTS, *MORE])


def a_plan_per_day(tmp_path, days=5):
    lib, google, clock = library(tmp_path), FakeGoogle(buckets=(BUCKET,)), Clock()
    plans = []
    for _ in range(days):
        precheck.plan_run([REQUEST], lib, a_checker(tmp_path, google, clock), profiles=None)
        plans.append(the_plan(google))
        clock.now += timedelta(days=1)
    return lib, plans


def test_the_plan_lists_the_first_two_tiers_every_day_and_the_last_two_one_day_in_five(tmp_path, more_kettles):
    lib, plans = a_plan_per_day(tmp_path)
    found = precheck.comments_to_check([REQUEST], library_dir=lib,
                                       checker=LiveChecker(cache_dir=tmp_path / "empty", fetch=never_read))
    first = tuple(c.url for c in found if c.tier <= 1)
    last = [c.url for c in found if c.tier >= 2]
    assert first and last  # the made-up kettles have products behind the picks
    assert all(plan.answers == first for plan in plans)  # every day, in the old order
    assert Counter(url for plan in plans for url in plan.fallback) == Counter(last)  # each once in 5 days
    assert not {url for plan in plans for url in plan.fallback} & set(first)
    assert all(len(plan.fallback) < len(last) for plan in plans)


def test_the_plan_report_says_how_many_fallback_comments_it_lists(tmp_path, capsys, more_kettles):
    lib, google, clock = library(tmp_path), FakeGoogle(buckets=(BUCKET,)), Clock()
    precheck.plan_run([REQUEST], lib, a_checker(tmp_path, google, clock), profiles=None)
    said = capsys.readouterr().out
    plan = the_plan(google)
    assert f"{len(plan.fallback):,} listed today, each read every {config.PLAN_FALLBACK_TIER_DAYS} days" in said


def test_a_plan_keeps_its_fallback_comments_apart_and_an_older_plan_has_none():
    now = datetime(2026, 10, 26, 3)
    data = plan_bytes([link(1)], [link(2)], {}, now, [link(3)], fallback=[link(4)])
    plan = read_plan(data)
    assert (plan.answers, plan.verify, plan.edited, plan.fallback) == ((link(1),), (link(2),), (link(3),), (link(4),))
    old = b'{"written_at": "2026-10-20T03:00:00", "answers": [], "verify": [], "checks": {}}'
    assert read_plan(old).fallback == ()
    junk = read_plan(b'{"written_at": "2026-10-20T03:00:00", "answers": [], "verify": [], "fallback": 7}')
    assert junk is None


# --- The site ---

def with_fallback(scene, answers=(), fallback=(), verify=()):
    scene.google.put(BUCKET, PLAN, plan_bytes([link(n) for n in answers], [link(n) for n in verify], {},
                                              scene.clock.now, fallback=[link(n) for n in fallback]))


def test_a_fallback_comment_is_read_when_it_has_no_read_in_the_last_48_hours_and_not_again_while_it_has(scene):
    with_fallback(scene, fallback=[1])
    ahead = scene.site()
    assert ahead.on_ping().read == 1
    scene.clock.now += timedelta(hours=config.READ_AHEAD_AGAIN_HOURS + 1)
    assert ahead.on_ping().read == 0  # an answers' comment would be read again here; this one waits for its next day


def test_the_answers_comments_are_read_before_the_fallback_ones_and_those_before_the_kept_ones(scene):
    with_fallback(scene, answers=[1, 2], fallback=[3, 4], verify=[5])
    ahead = scene.site(parallel=1)
    assert ahead.on_ping().read == 5
    assert [url.split("/comment/")[1][:5] for url in scene.reddit.asked] == ["c0001", "c0002", "c0003", "c0004", "c0005"]


def test_a_fallback_comment_read_five_days_ago_has_no_check_an_answer_may_show(scene):
    # The rule is unchanged (Noemi, 13 Oct 2026): a quote needs a passing check from the last 48 hours. Reading a fallback
    # comment every 5 days leaves it without one most of the time; an answer needing it checks it then, as before.
    with_fallback(scene, fallback=[1])
    ahead = scene.site()
    ahead.on_ping()
    assert scene.live.saved_check(link(1), QUOTE).show
    scene.clock.now += timedelta(hours=config.CACHE_MAX_AGE_HOURS + 1)
    assert scene.live.saved_check(link(1), QUOTE) is None
    scene.reddit.asked.clear()
    assert scene.live.check(link(1), QUOTE).show and len(scene.reddit.asked) == 1  # read at answer time


def test_a_comment_listed_among_the_answers_and_the_fallback_ones_is_read_once(scene):
    with_fallback(scene, answers=[1], fallback=[1, 2])
    assert scene.site().on_ping().read == 2 and len(scene.reddit.asked) == 2
