"""Checking ahead (Noemi's decision of 13 Oct 2026): the comments answers would show are read live in advance, daily,
within Reddit's limits, so a visitor's fresh answer finds them already checked.

A made-up library of two kettle threads, Reddit's embed page made up too: no test reaches the network.
"""

import json
from datetime import timedelta

import pytest

from engine import config, precheck
from engine.answer import _every_quote
from engine.live_check import LiveChecker, LiveResult
from engine.pipeline import answer_request
from engine.precheck import Candidate, check_ahead, comments_to_check, requests_to_check
from engine.tests.factories import write_gold
from engine.tests.test_live_check import Clock, deleted_page, page
from engine.tests.test_pipeline import REQUEST, comment, kettle_thread, mention

# Made-up comments: (comment id, thread, product, stance, text). Four kettles with enough credible praise to be picks,
# so one is ranked behind the three picks; one praised twice, for "Also worth a look"; and one kettle warned against
# twice, for the skip list.
COMMENTS = [
    ("z1aaaa", "1kett01", "Zojirushi kettle", "recommend", "My Zojirushi kettle has lasted 9 years and still boils fast."),
    ("z1bbbb", "1kett01", "Zojirushi kettle", "recommend", "Our Zojirushi kettle is 8 years old and works every day."),
    ("z1cccc", "1kett01", "Zojirushi kettle", "recommend", "Had a Zojirushi kettle for 7 years, never a problem."),
    ("z2aaaa", "1kett02", "Zojirushi kettle", "recommend", "The Zojirushi kettle I bought 6 years ago is still perfect."),
    ("z2bbbb", "1kett02", "Zojirushi kettle", "recommend", "I have used the same Zojirushi kettle for 5 years."),
    ("d1aaaa", "1kett01", "Dualit kettle", "recommend", "My Dualit kettle has lasted 12 years and counting."),
    ("d1bbbb", "1kett01", "Dualit kettle", "recommend", "Dualit kettle for 10 years now, still going strong."),
    ("d2aaaa", "1kett02", "Dualit kettle", "recommend", "We have had our Dualit kettle for 11 years, no faults."),
    ("d2bbbb", "1kett02", "Dualit kettle", "recommend", "Our Dualit kettle has worked daily for 9 years."),
    ("b1aaaa", "1kett01", "Bonavita kettle", "recommend", "My Bonavita kettle has lasted 6 years so far."),
    ("b2aaaa", "1kett02", "Bonavita kettle", "recommend", "Bonavita kettle, 5 years of daily use, still fine."),
    ("b2bbbb", "1kett02", "Bonavita kettle", "recommend", "Had my Bonavita kettle 4 years and it still heats fast."),
    ("s1aaaa", "1kett01", "Cosori kettle", "recommend", "My Cosori kettle has lasted 4 years with daily use."),
    ("s2aaaa", "1kett02", "Cosori kettle", "recommend", "Cosori kettle for 3 years, it still works well."),
    ("s2bbbb", "1kett02", "Cosori kettle", "recommend", "I have had the Cosori kettle 3 years, no issues yet."),
    ("r1aaaa", "1kett01", "Russell Hobbs kettle", "recommend", "My Russell Hobbs kettle has lasted 5 years so far."),
    ("r2aaaa", "1kett02", "Russell Hobbs kettle", "recommend", "Russell Hobbs kettle, 4 years of daily use, still good."),
    ("c1aaaa", "1kett01", "Chefman kettle", "warn", "The Chefman kettle died after 6 months of use."),
    ("c2aaaa", "1kett02", "Chefman kettle", "warn", "Two Chefman kettles broke within a year of use, avoid them."),
]
LETTERS = {"Zojirushi kettle": "z", "Dualit kettle": "d", "Bonavita kettle": "b", "Cosori kettle": "s"}


def library(tmp_path):
    threads = {tid: [] for tid in ("1kett01", "1kett02")}
    extractions = {tid: [] for tid in threads}
    for cid, tid, product, stance, body in COMMENTS:
        threads[tid].append(comment(cid, tid, body))
        extractions[tid].append(mention(cid, product, body, stance))
    root = write_gold(tmp_path / "library", [kettle_thread(tid, comments) for tid, comments in threads.items()],
                      voices=None, mentions=None)
    (root / "extracted").mkdir()
    for tid, mentions in extractions.items():
        (root / "extracted" / f"{tid}.json").write_text(json.dumps({
            "thread_id": tid, "instructions_version": "extract-v5", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions}), encoding="utf-8")
    return root


class FakeReddit:
    """Reddit's embed page for the made-up comments: each comment as saved, or deleted when named in `gone`."""

    def __init__(self, gone=(), unreadable=()):
        self.gone, self.unreadable = set(gone), set(unreadable)
        self.bodies = {cid: body for cid, _, _, _, body in COMMENTS}
        self.asked: list[str] = []

    def __call__(self, url, headers):
        comment_id = url.split("/comment/")[1].split("/")[0]
        self.asked.append(comment_id)
        if comment_id in self.unreadable:
            return 503, b"busy"
        if comment_id in self.gone:
            return 200, deleted_page()
        return 200, page(self.bodies[comment_id])


def live_checker(tmp_path, reddit, clock=None):
    clock = clock or Clock()
    return LiveChecker(cache_dir=tmp_path / "cache", fetch=reddit, clock=clock, sleep=clock.sleep, min_interval=0)


class AllPass:
    def check(self, url, quote, wait=True):
        return LiveResult("ok", "passes")


def shown_ids(answer) -> set[str]:
    return {quote.comment_id for _, quote in _every_quote(answer)}


# --- Which comments, in what order ---

def test_the_comments_an_answer_shows_come_first_then_those_next_in_line(tmp_path):
    lib = library(tmp_path)
    shown = shown_ids(answer_request(REQUEST, library_dir=lib, live_checker=AllPass()).answer)
    found = comments_to_check([REQUEST], library_dir=lib, checker=live_checker(tmp_path, FakeReddit()))
    assert {c.comment_id for c in found if c.tier == 0} == shown
    assert [c.order for c in found] == sorted(c.order for c in found)  # likeliest to be shown first
    assert found[0].tier == 0 and found[0].section == 0  # a pick's own quote leads
    # A pick praised by more writers than it quotes has its next quote in line checked ahead too (tier 1), so a quote
    # dropped by a check is replaced by one already checked.
    answer = answer_request(REQUEST, library_dir=lib, live_checker=AllPass()).answer
    next_in_line = {c.comment_id for c in found if c.tier == 1}
    for pick in answer.picks:
        praise = {cid for cid, _, product, stance, _ in COMMENTS if product == pick.name and stance == "recommend"}
        if len(praise) > len(pick.quotes):
            assert praise & next_in_line, pick.name
    assert {"c1aaaa", "c2aaaa"} <= {c.comment_id for c in found}  # the skip list's warnings are shown too


def test_the_products_behind_the_picks_are_checked_ahead(tmp_path):
    lib = library(tmp_path)
    answer = answer_request(REQUEST, library_dir=lib, live_checker=AllPass()).answer
    picks = {pick.name for pick in answer.picks}
    assert len(picks) == 3
    (behind,) = set(LETTERS) - picks
    letter = LETTERS[behind]
    found = comments_to_check([REQUEST], library_dir=lib, checker=live_checker(tmp_path, FakeReddit()))
    assert {c.comment_id for c in found if c.comment_id[0] == letter} == {cid for cid, *_ in COMMENTS
                                                                          if cid[0] == letter}
    assert all(c.tier > 0 for c in found if c.comment_id[0] == letter)


def test_also_worth_a_look_and_the_comments_a_summary_cites_are_checked_ahead(tmp_path):
    # Every quote the live check must pass before an answer is shown (engine.answer.quotes_to_check), since 13 Oct 2026
    # also "Also worth a look" and the comments a one-line summary cites, though the summary shows no quote.
    lib = library(tmp_path)
    plain = answer_request(REQUEST, library_dir=lib, live_checker=AllPass()).answer
    zojirushi = next(pick for pick in plain.picks if pick.name == "Zojirushi kettle")
    praise = [cid for cid, _, product, stance, _ in COMMENTS if product == "Zojirushi kettle" and stance == "recommend"]
    unquoted = [cid for cid in praise if cid not in {q.comment_id for q in zojirushi.quotes}]
    from engine.summaries import current_version

    (lib / "summaries.json").write_text(json.dumps({"kitchen:zojirushi kettle": {
        "product": "Zojirushi kettle", "category": "kitchen", "product_type": "electric kettle",
        "text": "Owners say it keeps boiling well for years.", "cites": unquoted[-1:],
        "written_at": "2026-10-13T10:00:00Z", "writer": "claude-code", "instructions_version": current_version()}}),
        encoding="utf-8")
    answer = answer_request(REQUEST, library_dir=lib, live_checker=AllPass()).answer
    assert [q.comment_id for q in next(p for p in answer.picks if p.name == "Zojirushi kettle").summary.sources] == \
        unquoted[-1:]
    assert [item.name for item in answer.worth_a_look] == ["Russell Hobbs kettle"]
    found = comments_to_check([REQUEST], library_dir=lib, checker=live_checker(tmp_path, FakeReddit()))
    shown = {c.comment_id for c in found if c.tier == 0}
    assert {"r1aaaa", "r2aaaa"} <= shown and unquoted[-1] in shown


def test_working_out_the_comments_never_reads_reddit(tmp_path):
    reddit = FakeReddit()
    comments_to_check([REQUEST, "something nice for my mum"], library_dir=library(tmp_path),
                      checker=live_checker(tmp_path, reddit))
    assert reddit.asked == []


def test_a_comment_known_to_be_deleted_leaves_its_place_to_the_next_in_line(tmp_path):
    # As in a visitor's answer: the saved check drops it, and what replaces it is what the answer shows.
    lib = library(tmp_path)
    first = comments_to_check([REQUEST], library_dir=lib, checker=live_checker(tmp_path, FakeReddit()))
    leader = first[0].comment_id
    live = live_checker(tmp_path, FakeReddit(gone={leader}))
    live.check(first[0].url, first[0].quotes[0])  # the saved check now says it was deleted
    again = comments_to_check([REQUEST], library_dir=lib, checker=live)
    assert leader not in {c.comment_id for c in again if c.tier == 0}
    expected = shown_ids(answer_request(REQUEST, library_dir=lib, live_checker=live).answer)
    assert {c.comment_id for c in again if c.tier == 0} == expected


def test_a_comment_shown_in_two_places_is_one_candidate_with_both_quotes_at_its_likeliest():
    merged = precheck.merged([
        Candidate("https://r/1/a", "a", ("first words",), tier=1, section=1, request=0, place=4),
        Candidate("https://r/1/b", "b", ("other",), tier=0, section=0, request=0, place=0),
        Candidate("https://r/1/a", "a", ("second words",), tier=0, section=1, request=1, place=2),
        Candidate("https://r/1/a", "a", ("first words",), tier=0, section=0, request=2, place=1),
    ])
    assert [c.comment_id for c in merged] == ["b", "a"]
    assert merged[1].quotes == ("first words", "second words") and merged[1].order == (0, 0, 2, 1)


def test_requests_without_an_answer_add_nothing(tmp_path):
    found = comments_to_check(["something nice for my mum", "best gaming laptop under 800"],
                              library_dir=library(tmp_path), checker=live_checker(tmp_path, FakeReddit()))
    assert found == []


# --- Which requests ---

def test_the_requests_checked_ahead_likeliest_first_each_once(tmp_path):
    questions = tmp_path / "questions.json"
    questions.write_text(json.dumps({"questions": [{"id": "b01", "text": "electric kettle that lasts 10+ years"}]}))
    latency = tmp_path / "latency.json"
    latency.write_text(json.dumps({"queries": [{"id": "b01", "text": "electric kettle that lasts 10+ years"},
                                               {"id": "l03", "text": "air fryer that lasts"}]}))
    lib = tmp_path / "library"
    lib.mkdir()
    (lib / "requests.jsonl").write_text("\n".join(json.dumps(line) for line in [
        {"request": "a yogurt maker", "status": "ok", "product_type": "yogurt maker"},
        {"request": "kettle", "status": "ok", "product_type": "electric kettle"},  # module 1's own: listed already
        {"request": "something", "status": "clarify", "product_type": None},
    ]) + "\n")
    found = requests_to_check(questions, latency, lib)
    from engine.query import PRODUCT_TYPES

    own = [p.name for p in PRODUCT_TYPES]
    assert found[:2] == ["electric kettle that lasts 10+ years", "air fryer that lasts"]  # the page's examples first
    assert found[2:2 + len(own)] == own
    # Changed on purpose 14 Oct 2026: the log's example was a waffle maker, module 1's own type since then; then an ice
    # cream maker, module 1's own type since the routing audit the same day.
    assert found[2 + len(own)] == "yogurt maker"
    assert set(config.PRECHECK_MODEL_TYPES) <= set(found)
    assert len(found) == len(set(found))


def test_the_ingredient_requests_are_checked_ahead_too(tmp_path):
    # 13 Oct 2026: ingredient-led answers (engine/ingredients.py) read skincare threads of every type, and none of their
    # requests was on the list, so their quotes were all read at answer time: the ingredient eval's requests come last.
    ingredients = tmp_path / "ingredients.json"
    ingredients.write_text(json.dumps({"cases": [{"id": "i01", "text": "salicylic acid for acne"},
                                                 {"id": "i02", "text": "air fryer"}]}))  # listed already: once
    found = requests_to_check(tmp_path / "none.json", tmp_path / "none.json", tmp_path / "no library", ingredients)
    assert found[-1] == "salicylic acid for acne" and found.count("air fryer") == 1


def test_without_the_request_log_the_listed_model_types_are_still_checked(tmp_path):
    found = requests_to_check(tmp_path / "none.json", tmp_path / "none.json", tmp_path / "no library")
    assert "air fryer" in found and "electric kettle" in found


# --- Reading them ---

def candidates(tmp_path):
    return comments_to_check([REQUEST], library_dir=library(tmp_path), checker=live_checker(tmp_path, FakeReddit()))


def test_each_comment_is_read_once_in_order_within_the_runs_budget(tmp_path):
    found = candidates(tmp_path)
    reddit = FakeReddit()
    run = check_ahead(found, live_checker(tmp_path, reddit), limit=5)
    assert reddit.asked == [c.comment_id for c in found[:5]]
    assert (run.read, run.passing, run.not_reached) == (5, 5, len(found) - 5)


def test_comments_checked_within_a_day_are_skipped_older_ones_read_again(tmp_path):
    found = candidates(tmp_path)
    clock = Clock()
    reddit = FakeReddit()
    live = live_checker(tmp_path, reddit, clock)
    check_ahead(found[:4], live, limit=100)
    clock.now += timedelta(hours=config.PRECHECK_FRESH_HOURS - 1)
    check_ahead(found[4:6], live, limit=100)
    clock.now += timedelta(hours=2)  # the first four are now older than PRECHECK_FRESH_HOURS, the next two aren't
    reddit.asked.clear()
    run = check_ahead(found[:6], live, limit=100)
    assert reddit.asked == [c.comment_id for c in found[:4]]
    assert (run.read, run.fresh) == (4, 2)


def test_deleted_edited_and_unreadable_comments_are_counted(tmp_path):
    found = candidates(tmp_path)
    reddit = FakeReddit(gone={found[0].comment_id}, unreadable={found[1].comment_id})
    reddit.bodies[found[2].comment_id] = "Edit: I gave it away, it broke."
    run = check_ahead(found, live_checker(tmp_path, reddit), limit=100)
    assert (run.gone, run.unknown, run.changed) == (1, 1, 1)
    assert run.passing == len(found) - 3 and run.read == len(found)


def test_a_comment_with_several_quotes_is_read_once(tmp_path):
    reddit = FakeReddit()
    url = "https://www.reddit.com/r/BuyItForLife/comments/1kett01/comment/z1aaaa/"
    candidate = Candidate(url, "z1aaaa", ("lasted 9 years", "still boils fast"), tier=0, section=0, request=0, place=0)
    run = check_ahead([candidate], live_checker(tmp_path, reddit), limit=10)
    assert reddit.asked == ["z1aaaa"] and run.passing == 1


def test_a_dry_run_reads_nothing_and_says_what_it_would_read(tmp_path):
    found = candidates(tmp_path)
    reddit = FakeReddit()
    live = live_checker(tmp_path, reddit)
    check_ahead(found[:2], live, limit=100)
    reddit.asked.clear()
    run = check_ahead(found, live, limit=100, dry_run=True)
    assert reddit.asked == []
    assert (run.read, run.fresh, run.would_read) == (0, 2, len(found) - 2)


def test_the_run_stops_when_reddit_stops_answering(tmp_path):
    found = candidates(tmp_path)
    reddit = FakeReddit(unreadable={c.comment_id for c in found})
    run = check_ahead(found, live_checker(tmp_path, reddit), limit=100, stop_after_unknown=3)
    assert len(reddit.asked) == 3 and run.stopped and run.not_reached == len(found) - 3


def test_reads_keep_to_reddits_pace(tmp_path):
    clock = Clock()
    found = candidates(tmp_path)
    live = LiveChecker(cache_dir=tmp_path / "cache", fetch=FakeReddit(), clock=clock, sleep=clock.sleep,
                       min_interval=0, burst=2, refill=4)
    started = clock.now
    check_ahead(found[:5], live, limit=100)
    assert clock.now - started >= timedelta(seconds=3 * 4)  # after a burst of 2, one read every 4 s


# --- The report and the command ---

def test_the_report_gives_the_counts_and_never_a_comments_words(tmp_path):
    found = candidates(tmp_path)
    run = check_ahead(found, live_checker(tmp_path, FakeReddit(gone={found[0].comment_id})), limit=100)
    text = precheck.report(found, run, requests=1, answered=1, seconds_working=1.5, seconds_reading=620.0)
    assert f"next in line: {len(found)} (" in text and "1 gone" in text and "passing" in text
    assert "2 s working out" in text and "10.3 min reading" in text and "10.4 min in all" in text
    assert not any(body in text for *_, body in COMMENTS)
    assert not any(word in text for word in ("Zojirushi", "Dualit"))


@pytest.mark.parametrize("argv, expected", [
    ([], (config.PRECHECK_MAX_READS, config.PRECHECK_MAX_RUN_MINUTES, False)),
    (["--limit", "40"], (40, config.PRECHECK_MAX_RUN_MINUTES, False)),
    (["--dry-run", "--limit", "7"], (7, config.PRECHECK_MAX_RUN_MINUTES, True)),
    (["--minutes", "30", "--limit", "7"], (7, 30, False)),
])
def test_the_command_takes_a_limit_a_time_and_a_dry_run(argv, expected):
    assert precheck.options(argv) == expected


@pytest.mark.parametrize("argv", [["--limit"], ["--limit", "many"], ["--limit", "-3"], ["--minutes"],
                                  ["--minutes", "0"], ["--fast"], ["kettle"]])
def test_the_command_refuses_anything_else(argv, capsys):
    assert precheck.main(argv) == 2
    assert "python -m engine.precheck" in capsys.readouterr().out


def test_the_command_waits_for_reddits_next_10_minutes_rather_than_give_up(monkeypatch):
    # 13 Oct 2026: a visitor's read never waits more than LIVE_CHECK_MAX_WAIT_SECONDS for Reddit's next 10 minutes; the
    # pre-check has nobody waiting on it and reads until its budget is spent, so it waits as long as a window lasts.
    given = {}
    monkeypatch.setattr(precheck, "requests_to_check", lambda: [REQUEST])
    monkeypatch.setattr(precheck.pipeline, "cached_profiles", lambda: None)
    monkeypatch.setattr(precheck, "run", lambda requests, limit, dry_run, library_dir, checker, profiles, **times:
                        given.setdefault("checker", checker) and 0)
    assert precheck.main(["--dry-run"]) == 0
    assert given["checker"].max_wait > 600 > config.LIVE_CHECK_MAX_WAIT_SECONDS


def test_a_whole_run_from_the_command(tmp_path, capsys):
    reddit = FakeReddit()
    status = precheck.run([REQUEST], limit=100, dry_run=False, library_dir=library(tmp_path),
                          checker=live_checker(tmp_path, reddit), profiles=None)
    assert status == 0 and reddit.asked
    said = capsys.readouterr().out
    assert "Read on Reddit now" in said


# --- The values ---

def test_a_check_skipped_as_fresh_lasts_until_the_next_days_run_has_read_everything():
    # Skipped when under PRECHECK_FRESH_HOURS old; the next run, a day later, reads it again within PRECHECK_MAX_READS
    # reads at the live check's pace, before the 48 hours of the deletion rule run out.
    longest_run_hours = config.PRECHECK_MAX_READS * config.LIVE_CHECK_REFILL_SECONDS / 3600
    assert config.PRECHECK_FRESH_HOURS + 24 + longest_run_hours < config.CACHE_MAX_AGE_HOURS
    # And within its time (14 Oct 2026): no read starts after PRECHECK_MAX_RUN_MINUTES, and the last may wait for
    # Reddit's next 10 minutes.
    longest_run_hours = (config.PRECHECK_MAX_RUN_MINUTES * 60 + config.PRECHECK_MAX_WAIT_SECONDS) / 3600
    assert config.PRECHECK_FRESH_HOURS + 24 + longest_run_hours < config.CACHE_MAX_AGE_HOURS
    assert config.PRECHECK_FRESH_HOURS >= 12  # "fresh for most of a day": not read twice a day


def test_a_request_whose_answer_fails_is_reported_and_the_others_still_worked_out(tmp_path, monkeypatch, capsys):
    from engine import pipeline

    real = pipeline.answer_request

    def failing(request, **kwargs):
        if request == "a broken request":
            raise ValueError("a library file that doesn't load")
        return real(request, **kwargs)

    monkeypatch.setattr(pipeline, "answer_request", failing)
    found = comments_to_check(["a broken request", REQUEST], library_dir=library(tmp_path),
                              checker=live_checker(tmp_path, FakeReddit()))
    assert found and all(c.request == 1 for c in found)
    said = capsys.readouterr().err
    assert "ValueError" in said and "a broken request" in said  # our own request list: named, to find the problem


# --- Sharing the checks through the bucket, as one bundle (free tiers only, 13 Oct 2026) ---

def bucketed(tmp_path, folder, reddit, google, clock=None):
    from engine.live_check import Bucket

    clock = clock or Clock()
    return LiveChecker(cache_dir=tmp_path / folder, fetch=reddit, clock=clock, sleep=clock.sleep, min_interval=0,
                       bucket=Bucket(google.bucket, request=google, clock=lambda: clock.now.timestamp()))


def test_a_run_starts_from_yesterdays_bundle_and_leaves_one_bundle_behind(tmp_path, capsys):
    from engine.tests.test_live_check_bucket import FakeGoogle

    google, clock, lib = FakeGoogle(), Clock(), library(tmp_path)
    first = FakeReddit()
    precheck.run([REQUEST], limit=100, dry_run=False, library_dir=lib,
                 checker=bucketed(tmp_path, "monday", first, google, clock), profiles=None)
    assert first.asked and len(google.asked("POST")) <= 2  # a bundle mid-run at most, and one at the end
    held = len(google.bundle()["checks"])
    assert held == len(set(first.asked))
    clock.now += timedelta(hours=2)  # the next run, on a new machine whose folder starts empty
    second = FakeReddit()
    precheck.run([REQUEST], limit=100, dry_run=False, library_dir=lib,
                 checker=bucketed(tmp_path, "tuesday", second, google, clock), profiles=None)
    assert second.asked == []  # every check came from the bundle, and is fresh
    said = capsys.readouterr().out
    assert f"{held} from the bucket's bundle" in said and f"{held} written to it" in said


def test_a_dry_run_reads_the_bundle_but_never_writes_it(tmp_path):
    from engine.tests.test_live_check_bucket import FakeGoogle

    google = FakeGoogle()
    precheck.run([REQUEST], limit=100, dry_run=True, library_dir=library(tmp_path),
                 checker=bucketed(tmp_path, "here", FakeReddit(), google), profiles=None)
    assert google.asked("POST") == [] and google.asked("GET", "fields=generation")


def test_the_checks_are_saved_once_midway_through_a_run(tmp_path):
    found = candidates(tmp_path)
    saved = []
    check_ahead(found, live_checker(tmp_path, FakeReddit()), limit=8, midway=lambda: saved.append(1))
    assert saved == [1]
    saved.clear()
    check_ahead(found[:2], live_checker(tmp_path, FakeReddit()), limit=8, midway=lambda: saved.append(1))
    assert saved == []  # fewer reads than half the budget: the end of the run saves them


class SlowReddit(FakeReddit):
    """FakeReddit whose every read takes a minute of the clock's time."""

    def __init__(self, clock):
        super().__init__()
        self.clock = clock

    def __call__(self, url, headers):
        self.clock.sleep(60)
        return super().__call__(url, headers)


def test_a_run_starts_no_read_once_its_time_is_spent(tmp_path):
    # 14 Oct 2026: a run is bounded by time as well as by reads, so the job's bill stays inside Cloud Run's free tier
    # however fast Reddit lets it read (a run that hit its 1,100 reads in 46 minutes had left 459 comments unread).
    found = candidates(tmp_path)
    clock = Clock()
    reddit = SlowReddit(clock)
    started = clock()
    run = check_ahead(found, live_checker(tmp_path, reddit, clock), limit=100, started=started, minutes=2.5)
    assert len(reddit.asked) == 3  # started at 0, 1 and 2 minutes; at 3 the 2.5 minutes are spent
    assert (run.read, run.not_reached, run.out_of_time) == (3, len(found) - 3, 2.5)
    assert "Not reached within this run's 2.5 minutes" in precheck.report(found, run, 1, 1, 0, run.seconds)


def test_the_time_counts_from_the_runs_start_working_out_included(tmp_path):
    found = candidates(tmp_path)
    clock = Clock()
    started = clock()
    clock.sleep(120)  # two minutes working out the answers
    run = check_ahead(found, live_checker(tmp_path, SlowReddit(clock), clock), limit=100, started=started, minutes=3)
    assert run.read == 1


def test_the_checks_are_saved_once_midway_through_a_runs_time(tmp_path):
    found = candidates(tmp_path)
    clock = Clock()
    started, saved = clock(), []
    check_ahead(found, live_checker(tmp_path, SlowReddit(clock), clock), limit=100, started=started, minutes=4,
                midway=lambda: saved.append(clock()))
    assert saved == [started + timedelta(minutes=2)]  # half the time spent, long before half of 100 reads


def test_reads_the_whole_list_when_neither_the_reads_nor_the_time_run_out(tmp_path):
    found = candidates(tmp_path)
    clock = Clock()
    run = check_ahead(found, live_checker(tmp_path, FakeReddit(), clock), limit=100, started=clock(), minutes=60)
    assert (run.read, run.not_reached, run.out_of_time) == (len(found), 0, None)
    assert "Not reached within this run's budget: 0." in precheck.report(found, run, 1, 1, 0, run.seconds)
