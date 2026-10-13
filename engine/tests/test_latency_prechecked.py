"""The latency eval's --prechecked mode (check ahead, 13 Oct 2026): how many of the quotes fresh answers show were
already checked by the daily pre-check, read from its saved checks only. No test reaches the network.
"""

import importlib.util
from pathlib import Path

import pytest

from engine.live_check import LiveChecker
from engine.pipeline import answer_request
from engine.tests.test_live_check import QUOTE, URL, FakeReddit, page
from engine.tests.test_precheck import REQUEST, library

LATENCY = Path(__file__).resolve().parents[2] / "eval" / "latency.py"


@pytest.fixture(scope="module")
def latency():
    spec = importlib.util.spec_from_file_location("latency_eval", LATENCY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_comment_the_pre_check_saved_is_answered_by_its_check(tmp_path, latency):
    LiveChecker(cache_dir=tmp_path, fetch=FakeReddit(answer=(200, page("Edit: it broke.")))).check(URL, QUOTE)
    checker = latency.PrecheckedChecker(tmp_path, pause=0)
    assert checker.check(URL, QUOTE).status == "changed"  # what Reddit said, as the site's checker would answer
    assert checker.reads_needed == set()


def test_a_comment_not_pre_checked_counts_as_a_read_still_needed_and_passes(tmp_path, latency):
    checker = latency.PrecheckedChecker(tmp_path, pause=0)
    assert checker.check(URL, QUOTE).show
    assert checker.reads_needed == {URL} and (URL, QUOTE) in checker.passed
    checker.new_request()
    assert checker.reads_needed == set() and checker.passed == set()


def test_coverage_counts_the_shown_quotes_whose_comment_was_pre_checked(tmp_path, latency):
    lib = library(tmp_path)
    checker = latency.PrecheckedChecker(tmp_path / "cache", pause=0)
    result = answer_request(REQUEST, library_dir=lib, live_checker=checker)
    shown, prechecked = latency.coverage(result, checker)
    assert shown > 0 and prechecked == 0  # nothing saved yet
    first = next(q for q in result.answer.picks[0].quotes)
    LiveChecker(cache_dir=tmp_path / "cache", fetch=FakeReddit(answer=(200, page(first.text)))).check(first.url,
                                                                                                     first.text)
    checker = latency.PrecheckedChecker(tmp_path / "cache", pause=0)
    result = answer_request(REQUEST, library_dir=lib, live_checker=checker)
    again, prechecked = latency.coverage(result, checker)
    assert again == shown and 1 <= prechecked < shown
    assert first.url not in checker.reads_needed
