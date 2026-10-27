"""Reading wider for popular product types (26 Oct 2026, the reading builder; Noemi's decision 1 of 26 Oct 2026, after
comparing our answers with ChatGPT's and Vetted's: "okay to all four recommendations").

An answer read its 16 most relevant threads, and read up to 48 only when they gave fewer than 3 picks. For a type the
library holds many more threads about (b04's moisturisers: 165), the 16 were a small sample. Now a type with at least
config.POPULAR_TYPE_MIN_THREADS usable threads about it is read wider (answer_request's `popular_threads`) even when the
first reading has 3 picks: every thread that talks about what the request asks for (every thread when it asks for nothing
besides the product), up to the cap; and every thread there is, up to the cap, when the first reading is short of picks.
Reading all of them for a request with needs gave a type's most recommended products to every request for it (the
library's six cleanser requests had the same top 3), so the evidence read is the evidence about the need. The wider
reading is shown when it has more picks, or as many picks with as many of them with a voice about the request's need and
not fewer such voices behind them (_wider_wins). `more_threads=None` still reads nothing more. `read_more` still means
"the first threads gave too few picks" (the page says so); `read_wider` says the reading shown is the popular type's.

Every thread, comment and product here is made up.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from engine import config, pipeline
from engine.answer import unverified_claims, write_answer
from engine.pipeline import answer_request
from engine.query import parse_query
from engine.rank import rank_products
from engine.tests.factories import make_thread
from engine.tests.ranking_factories import bodies_for, mentions
from engine.tests.test_round4 import reading
from engine.tests.test_upvotes import FILLER, REQUEST, STAGG, ZOJI, shown, write_threads

REAL_MIN_THREADS = config.POPULAR_TYPE_MIN_THREADS  # as decided: the fixture below sets a smaller one for made-up libraries
SMEG = "My Smeg kettle has lasted {years} years and still works perfectly."
BONAVITA = "My Bonavita kettle has lasted {years} years and still works perfectly."


@pytest.fixture(autouse=True)
def _popular_from_six_threads(monkeypatch):
    # The real threshold is for a library of hundreds of threads; these have eight.
    monkeypatch.setattr(config, "POPULAR_TYPE_MIN_THREADS", 6)


def popular_library(tmp_path: Path, threads: int = 8) -> Path:
    """Eight kettle threads. The two biggest (read first) give three picks, the Zojirushi, the Smeg and the Bonavita, with
    three credible voices each across them; the other six, smaller, praise the Fellow Stagg in each and the Zojirushi
    in each, the Bonavita in two: read in full, the Fellow Stagg is a pick (six voices) and the Smeg, with its three,
    is left out."""
    praise = lambda cid, text, years, product: (cid, text.format(years=years), 3, product)
    first = [praise("z1", ZOJI, 6, "Zojirushi kettle"), praise("z2", ZOJI, 4, "Zojirushi kettle"),
             praise("s1", SMEG, 5, "Smeg kettle"), praise("s2", SMEG, 4, "Smeg kettle"),
             praise("b1", BONAVITA, 7, "Bonavita kettle"), ("f1", FILLER, 1, None)]
    second = [praise("z3", ZOJI, 8, "Zojirushi kettle"), praise("s3", SMEG, 6, "Smeg kettle"),
              praise("b2", BONAVITA, 5, "Bonavita kettle"), praise("b3", BONAVITA, 6, "Bonavita kettle"),
              ("f2", FILLER, 1, None)]
    rest = {}
    for n in range(threads - 2):
        rows = [praise("z", ZOJI, 3 + n, "Zojirushi kettle"), praise("g", STAGG, 4 + n, "Fellow Stagg kettle")]
        if n < 2:
            rows.append(praise("b", BONAVITA, 3 + n, "Bonavita kettle"))
        rest[f"1pop{n + 3:03d}"] = rows
    sizes = {"1pop001": 500, "1pop002": 400, **{tid: 100 - n for n, tid in enumerate(rest)}}
    return write_threads(tmp_path, {"1pop001": first, "1pop002": second, **rest}, sizes)


def test_the_values_are_as_decided():
    assert config.PIPELINE_POPULAR_THREADS > config.PIPELINE_MORE_THREADS >= 48
    assert 16 < REAL_MIN_THREADS <= config.PIPELINE_POPULAR_THREADS
    assert config.PIPELINE_MAX_THREADS == 16  # the first reading is as it was


def test_a_popular_type_is_read_wider_though_the_first_reading_has_three_picks(tmp_path):
    root = popular_library(tmp_path)
    first = answer_request(REQUEST, library_dir=root, max_threads=2, more_threads=None)
    assert sorted(shown(first)[0]) == ["Bonavita kettle", "Smeg kettle", "Zojirushi kettle"] and not first.read_wider
    wider = answer_request(REQUEST, library_dir=root, max_threads=2, more_threads=4, popular_threads=8)
    assert wider.read_wider and not wider.read_more  # the page's "too few picks" note is for the other reason
    assert len(wider.threads_used) == 8
    assert "Fellow Stagg kettle" in shown(wider)[0] and "Smeg kettle" not in shown(wider)[0]
    assert shown(wider)[0][0] == "Zojirushi kettle"  # nine voices, in all eight threads
    assert unverified_claims(wider.answer, wider.bodies) == []


def test_a_type_with_fewer_threads_than_the_threshold_is_read_as_before(tmp_path, monkeypatch):
    root = popular_library(tmp_path)
    monkeypatch.setattr(config, "POPULAR_TYPE_MIN_THREADS", 9)  # the library holds 8
    result = answer_request(REQUEST, library_dir=root, max_threads=2, more_threads=4, popular_threads=8)
    assert not result.read_wider and not result.read_more and len(result.threads_used) == 2
    assert sorted(shown(result)[0]) == ["Bonavita kettle", "Smeg kettle", "Zojirushi kettle"]


def test_the_threshold_counts_the_threads_available_not_the_ones_read(tmp_path, monkeypatch):
    root = popular_library(tmp_path)
    monkeypatch.setattr(config, "POPULAR_TYPE_MIN_THREADS", 8)
    result = answer_request(REQUEST, library_dir=root, max_threads=2, more_threads=4, popular_threads=8)
    assert result.threads_available == 8 and result.read_wider


def test_more_threads_none_never_reads_more_even_for_a_popular_type(tmp_path):
    # Every test and every tool that asks for the first reading alone passes more_threads=None.
    result = answer_request(REQUEST, library_dir=popular_library(tmp_path), max_threads=2, more_threads=None,
                            popular_threads=8)
    assert not result.read_wider and not result.read_more and len(result.threads_used) == 2


def test_no_popular_width_keeps_the_old_reading_for_a_popular_type(tmp_path):
    result = answer_request(REQUEST, library_dir=popular_library(tmp_path), max_threads=2, more_threads=4,
                            popular_threads=None)
    assert not result.read_wider and not result.read_more and len(result.threads_used) == 2


def test_the_width_is_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "POPULAR_TYPE_MIN_THREADS", 4)
    result = answer_request(REQUEST, library_dir=popular_library(tmp_path), max_threads=2, more_threads=4,
                            popular_threads=5)
    assert result.read_wider and len(result.threads_used) == 5


def test_a_popular_type_short_of_picks_reads_as_wide_as_a_popular_one_not_the_few_picks_width(tmp_path):
    # Two threads give two picks (the Zojirushi and the Smeg, three voices each); the few-picks width is 3 threads, a
    # popular type's is all 8: the wider reading is the popular one, and is a "too few picks" one too.
    root = popular_library(tmp_path)
    result = answer_request(REQUEST, library_dir=root, max_threads=1, more_threads=3, popular_threads=8)
    assert len(result.threads_used) == 8 and result.read_more
    assert "Fellow Stagg kettle" in shown(result)[0]


def test_a_type_short_of_picks_but_not_popular_reads_the_few_picks_width(tmp_path, monkeypatch):
    root = popular_library(tmp_path)
    monkeypatch.setattr(config, "POPULAR_TYPE_MIN_THREADS", 9)
    result = answer_request(REQUEST, library_dir=root, max_threads=1, more_threads=3, popular_threads=8)
    assert len(result.threads_used) <= 3 and not result.read_wider


def retitle(root: Path, thread_ids: list[str], title: str) -> None:
    """Gives these threads another title, which asks for nothing (and the post, which says nothing of the need)."""
    for thread_id in thread_ids:
        path = root / "threads" / f"{thread_id}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["title"], data["body"] = title, "Any advice before I buy?"
        path.write_text(json.dumps(data), encoding="utf-8")


def test_a_request_with_needs_reads_the_threads_about_them_not_all_of_them(tmp_path, monkeypatch):
    # "Which electric kettle lasts?" talks about the request's need (lasting); "Electric kettle recommendations?" doesn't.
    # Four of the eight threads do: the first two (read first) and two of the six that praise the Fellow Stagg.
    monkeypatch.setattr(config, "POPULAR_TYPE_MIN_THREADS", 4)
    root = popular_library(tmp_path)
    retitle(root, [f"1pop{n:03d}" for n in range(5, 9)], "Electric kettle recommendations?")
    result = answer_request(REQUEST, library_dir=root, max_threads=2, more_threads=3, popular_threads=8)
    assert result.threads_available == 8 and result.threads_about_needs == 4
    assert result.read_wider and len(result.threads_used) == 4
    assert set(result.threads_used) == {f"1pop{n:03d}" for n in range(1, 5)}
    # The Fellow Stagg, praised in all six of the later threads, has only two voices in the two that are about the need.
    assert "Fellow Stagg kettle" not in shown(result)[0]
    assert unverified_claims(result.answer, result.bodies) == []


def test_a_request_that_asks_for_nothing_besides_the_product_reads_every_thread(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "POPULAR_TYPE_MIN_THREADS", 4)
    root = popular_library(tmp_path)
    retitle(root, [f"1pop{n:03d}" for n in range(5, 9)], "Electric kettle recommendations?")
    result = answer_request("electric kettle", library_dir=root, max_threads=2, more_threads=3, popular_threads=8)
    assert result.threads_about_needs is None
    assert result.read_wider and len(result.threads_used) == 8
    assert "Fellow Stagg kettle" in shown(result)[0]


def test_a_popular_type_short_of_picks_reads_at_least_the_few_picks_width(tmp_path, monkeypatch):
    # One thread gives one pick, the few-picks width is 6 threads and four threads are about the need: it reads 6.
    monkeypatch.setattr(config, "POPULAR_TYPE_MIN_THREADS", 4)
    root = popular_library(tmp_path)
    retitle(root, [f"1pop{n:03d}" for n in range(5, 9)], "Electric kettle recommendations?")
    result = answer_request(REQUEST, library_dir=root, max_threads=1, more_threads=6, popular_threads=8)
    assert result.read_more and result.read_wider and len(result.threads_used) == 6


def test_the_flags_survive_the_reading_ranked_with_the_upvote_rules(tmp_path, monkeypatch):
    # The reading kept is ranked again with Noemi's upvote rules when they change its ranking (a copy of the result):
    # the copy says what the reading was too.
    calls = []
    monkeypatch.setattr(pipeline, "_upvotes_change_nothing", lambda *args, **kwargs: calls.append(1) or False)
    wider = answer_request(REQUEST, library_dir=popular_library(tmp_path), max_threads=2, more_threads=4,
                           popular_threads=8)
    assert calls and wider.read_wider and not wider.read_more and len(wider.threads_used) == 8
    short = answer_request(REQUEST, library_dir=popular_library(tmp_path / "again"), max_threads=1, more_threads=3,
                           popular_threads=8)
    assert short.read_wider and short.read_more


def first_reading(picks: int, available: int, used: int = 16, answered: bool = True, about_needs: int | None = None):
    """What _wider_width looks at in a first reading."""
    from types import SimpleNamespace
    return SimpleNamespace(answer=SimpleNamespace(picks=[None] * picks) if answered else None,
                           threads_available=available, threads_used=[None] * used, threads_about_needs=about_needs)


def test_how_wide_the_wider_reading_reads(monkeypatch):
    monkeypatch.setattr(config, "POPULAR_TYPE_MIN_THREADS", 24)
    width = pipeline._wider_width
    # A popular type reads the threads about the need, or every thread when nothing is asked for besides the product (or an
    # ingredient is named), up to its cap...
    assert width(first_reading(3, 165, about_needs=40), 16, 48, 200) == (40, True)
    assert width(first_reading(3, 165, about_needs=300), 16, 48, 200) == (200, True)
    assert width(first_reading(3, 165, about_needs=None), 16, 48, 200) == (165, True)
    assert width(first_reading(3, 300, about_needs=None), 16, 48, 200) == (200, True)
    # ... with enough picks only a reading of at least POPULAR_TYPE_MIN_THREADS: a few more than the first reading's is
    # no wider one.
    assert width(first_reading(3, 165, about_needs=23), 16, 48, 200) == (None, False)
    assert width(first_reading(3, 165, about_needs=0), 16, 48, 200) == (None, False)
    assert width(first_reading(3, 165, about_needs=24), 16, 48, 200) == (24, True)
    # Short of picks it reads at least the few-picks width, as every type did.
    assert width(first_reading(1, 165, about_needs=40), 16, 48, 200) == (48, True)
    assert width(first_reading(1, 165, about_needs=90), 16, 48, 200) == (90, True)
    assert width(first_reading(0, 165, about_needs=5), 16, 48, 200) == (48, True)
    assert width(first_reading(1, 165, about_needs=None), 16, 48, 200) == (165, True)
    assert width(first_reading(1, 165), 16, 48, 30) == (48, True)
    assert width(first_reading(1, 24), 16, 48, 200) == (48, True)  # more than there are: it reads them all
    # Switched off, a request with needs reads every thread too (the reading of the classics review of 25 Oct 2026).
    monkeypatch.setattr(config, "POPULAR_READS_ONLY_THREADS_ABOUT_THE_NEED", False)
    assert width(first_reading(3, 165, about_needs=40), 16, 48, 200) == (165, True)
    assert width(first_reading(1, 165, about_needs=40), 16, 48, 200) == (165, True)
    monkeypatch.setattr(config, "POPULAR_READS_ONLY_THREADS_ABOUT_THE_NEED", True)
    # Any other type reads the few-picks width when short of picks, and nothing more with enough.
    assert width(first_reading(1, 23), 16, 48, 200) == (48, False)
    assert width(first_reading(3, 23), 16, 48, 200) == (None, False)
    # A width not beyond the first reading's is no reading.
    assert width(first_reading(3, 165, about_needs=60), 60, 48, 200) == (None, False)
    # Nothing more to read, no answer, or no wider reading asked for: nothing.
    assert width(first_reading(3, 16), 16, 48, 200) == (None, False)
    assert width(first_reading(1, 16), 16, 48, 200) == (None, False)
    assert width(first_reading(3, 165, answered=False), 16, 48, 200) == (None, False)
    assert width(first_reading(3, 165), 16, None, 200) == (None, False)
    assert width(first_reading(3, 165), 16, 48, None) == (None, False)
    assert width(first_reading(1, 165), 16, 48, None) == (48, False)


def test_which_threads_talk_about_the_requests_needs():
    from engine.models import Thread

    def thread(title: str, body: str = "") -> Thread:
        return Thread.model_validate(make_thread(id="1t", title=title, body=body, comments=[]))

    quiet = parse_query("a quiet electric kettle", model=None)
    threads = [thread("Which quiet electric kettle should I buy?"), thread("Electric kettle recommendations?"),
               thread("Electric kettle help", "I need one that is really quiet."), thread("Best kettle for tea?")]
    assert pipeline._threads_about_needs(threads * 10, quiet) == 20  # the first and third kinds, ten times each
    assert pipeline._threads_about_needs(threads, quiet) is None  # fewer than POPULAR_TYPE_MIN_THREADS: never asked
    # A request that asks for nothing besides the product has no need to read by: every thread is about it.
    plain = parse_query("electric kettle", model=None)
    assert pipeline._threads_about_needs(threads * 10, plain) is None
    # A thread titled as another type of product talks about none of them.
    other = [thread("Quiet toaster recommendations?")] * 30
    assert pipeline._threads_about_needs(other, quiet) == 0


# --- The live check reads only the reading that is shown ---

def asked_comments(live) -> set[str]:
    return {url.rstrip("/").split("/")[-1] for url in live.asked}


def spy_on_live_checks(monkeypatch) -> list[int]:
    """The number of threads read by each reading that gets its quotes checked against Reddit, in turn."""
    calls = []
    real = pipeline._check_live

    def spy(result, *args, **kwargs):
        calls.append(len(result.threads_used))
        return real(result, *args, **kwargs)

    monkeypatch.setattr(pipeline, "_check_live", spy)
    return calls


def test_with_a_live_checker_only_the_reading_shown_is_checked_against_reddit(tmp_path, monkeypatch):
    # The first reading's quotes would be checked (an embed read each, from Reddit's allowance of about 200 in 10 minutes)
    # and then not shown: 36 popular answers of the sweep would have had 9 such reads each.
    from engine.tests.test_pipeline import FakeLive

    calls, live = spy_on_live_checks(monkeypatch), FakeLive()
    result = answer_request(REQUEST, library_dir=popular_library(tmp_path), max_threads=2, more_threads=4,
                            popular_threads=8, live_checker=live)
    assert result.read_wider and len(result.threads_used) == 8
    assert live.asked and set(calls) == {8}  # no check of the 2-thread reading's answer
    assert asked_comments(live) <= shown_ids(result)  # every comment asked about is one the answer shows
    assert unverified_claims(result.answer, result.bodies) == []


def shown_ids(result) -> set[str]:
    from engine.answer import _every_quote

    return {quote.comment_id for _, quote in _every_quote(result.answer)}


def test_when_the_first_reading_is_kept_it_is_checked_after_all(tmp_path, monkeypatch):
    from engine.tests.test_pipeline import FakeLive

    monkeypatch.setattr(pipeline, "_wider_wins", lambda *args, **kwargs: False)
    calls = spy_on_live_checks(monkeypatch)
    live = FakeLive(gone={"s11"})  # a Smeg comment, deleted on Reddit since it was saved
    result = answer_request(REQUEST, library_dir=popular_library(tmp_path), max_threads=2, more_threads=4,
                            popular_threads=8, live_checker=live)
    assert not result.read_wider and not result.read_more  # the first reading is the one shown
    assert calls[-1] == 2  # and its quotes were checked after all
    assert "s11" in asked_comments(live) and "s11" not in shown_ids(result)  # checked, found gone, never shown
    assert "Smeg kettle" not in shown(result)[0]  # with two voices left it is no pick
    assert unverified_claims(result.answer, result.bodies) == []


def test_a_type_that_is_not_popular_is_checked_reading_by_reading_as_before(tmp_path, monkeypatch):
    from engine.tests.test_pipeline import FakeLive

    monkeypatch.setattr(config, "POPULAR_TYPE_MIN_THREADS", 9)  # the library holds 8
    calls, live = spy_on_live_checks(monkeypatch), FakeLive()
    result = answer_request(REQUEST, library_dir=popular_library(tmp_path), max_threads=2, more_threads=3,
                            popular_threads=8, live_checker=live)
    assert not result.read_wider and len(result.threads_used) == 2
    assert calls == [2]  # one reading, checked once
    # Short of picks it reads wider and checks both readings, as every type did.
    calls.clear()
    short = answer_request(REQUEST, library_dir=popular_library(tmp_path / "short"), max_threads=1, more_threads=3,
                           popular_threads=8, live_checker=FakeLive())
    assert short.read_more and calls == [1, 3]


def test_the_usable_thread_count_before_reading_is_the_one_reading_gives(tmp_path):
    from engine.tests.test_pipeline import FakeLive

    root = popular_library(tmp_path)
    query = parse_query(REQUEST, model=None)
    counted = pipeline._usable_thread_count(query, root, None, None, FakeLive())
    assert counted == answer_request(REQUEST, library_dir=root, more_threads=None, live_checker=FakeLive()
                                     ).threads_available == 8
    assert pipeline._usable_thread_count(parse_query("something nice for my mum", model=None), root, None, None,
                                         FakeLive()) == 0


# --- Which reading is shown ---

def two_readings(query, first, wider):
    return reading(query, *first), reading(query, *wider)


def fitting(query, name: str, voices: int, fitting_voices: int):
    """A reading with one pick: `voices` credible recommendations of it, `fitting_voices` of them talking about the need."""
    items = [replace(m, needs=("fitness",) if n < fitting_voices else (), features=())
             for n, m in enumerate(mentions(voices, name, category="general"))]
    result = pipeline.PipelineResult(query)
    result.ranking = rank_products(items, "general")
    result.answer = write_answer(result.ranking, bodies_for(*items), query.product_type)
    return result


def test_as_many_picks_the_popular_types_wider_reading_wins_unless_fewer_of_its_picks_have_a_voice():
    query = parse_query("smartwatch for fitness", model=None)
    first, wider = two_readings(query, [("Halo GT watch", ("fitness",), ())], [("Garmin Forerunner watch", ("fitness",), ())])
    # Same picks, same voices: the first reading stays for a type that isn't popular (as before). Changed on purpose 26
    # Oct 2026 (the orchestrator, at the merge): for a popular type it stays too, since the wider reading brings no more
    # voices about the need (it had won: "shampoo for curly hair that isn't drying" read 57 threads, not 16, for the same
    # 8 voices about the need behind twice the voices, and put an anti-dandruff shampoo second).
    assert not pipeline._wider_wins(first, wider, query)
    assert not pipeline._wider_wins(first, wider, query, popular=True)
    # Fewer of the wider reading's picks with a voice about the need: the first reading stays either way.
    voiceless = reading(query, ("Garmin Forerunner watch", (), ()))
    assert not pipeline._wider_wins(first, voiceless, query, popular=True)
    # More voices win either way.
    assert pipeline._wider_wins(reading(query, ("Halo GT watch", (), ())), wider, query)


def test_a_popular_types_wider_reading_with_fewer_voices_about_the_need_does_not_win():
    # More evidence of popularity is not more evidence of fit: 90 credible voices, 5 about the need, against 22, 8.
    query = parse_query("smartwatch for fitness", model=None)
    first, wider = fitting(query, "Halo GT watch", 22, 8), fitting(query, "Garmin Forerunner watch", 90, 5)
    assert pipeline._voiced_picks(first, query) == pipeline._voiced_picks(wider, query) == 1
    assert (pipeline._need_voices(first), pipeline._need_voices(wider)) == (8, 5)
    assert not pipeline._wider_wins(first, wider, query, popular=True)
    # More voices about the need, at a share not much below the first reading's, and it wins; nothing is asked of a
    # request that asks for nothing. Changed on purpose 26 Oct 2026 (the orchestrator, at the merge): as many voices
    # about the need (8 and 8) had won; more evidence of popularity with no more evidence of fit now keeps the first.
    assert not pipeline._wider_wins(first, fitting(query, "Garmin Forerunner watch", 90, 8), query, popular=True)
    assert pipeline._wider_wins(first, fitting(query, "Garmin Forerunner watch", 90, 30), query, popular=True)
    plain = parse_query("smartwatch", model=None)
    assert pipeline._wider_wins(fitting(plain, "Halo GT watch", 22, 0), fitting(plain, "Garmin Forerunner watch", 90, 0),
                                plain, popular=True)


def test_fewer_picks_never_win_and_more_picks_always_do():
    query = parse_query("smartwatch for fitness", model=None)
    one = reading(query, ("Halo GT watch", ("fitness",), ()))
    two = reading(query, ("Halo GT watch", (), ()), ("Polar Pacer watch", (), ()))
    for popular in (False, True):
        assert pipeline._wider_wins(one, two, query, popular=popular)
        assert not pipeline._wider_wins(two, one, query, popular=popular)



def test_a_popular_types_wider_reading_must_add_voices_about_the_need_at_a_share_close_to_the_first_readings():
    # 26 Oct 2026 (the orchestrator, at the merge): reading three times the threads should bring more evidence of fit,
    # not only of popularity. On the library: b04's moisturiser went from 11 of 32 voices about the need to 17 of 53 (shown
    # wider); the curly-hair shampoo from 8 of 17 to 8 of 33, and the fine oily hair one from 11 of 18 to 11 of 33 (both
    # now keep their first reading).
    query = parse_query("smartwatch for fitness", model=None)
    first = fitting(query, "Halo GT watch", 32, 11)
    assert pipeline._wider_wins(first, fitting(query, "Garmin Forerunner watch", 53, 17), query, popular=True)
    assert not pipeline._wider_wins(fitting(query, "Halo GT watch", 17, 8), fitting(query, "Garmin Forerunner watch", 33, 8),
                                    query, popular=True)
    # More voices about the need, but a far smaller share of them: still popularity, not fit.
    assert not pipeline._wider_wins(fitting(query, "Halo GT watch", 17, 8), fitting(query, "Garmin Forerunner watch", 60, 9),
                                    query, popular=True)
    # The share it must keep is a setting.
    assert 0 < config.POPULAR_WIDER_NEED_SHARE_KEPT <= 1
