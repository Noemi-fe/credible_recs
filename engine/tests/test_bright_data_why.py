"""Why a thread couldn't be read through Bright Data (14 Oct 2026, the coordinator: the daily plan's Bright Data step
failed on the same two threads at every run, and its report didn't say why).

A BrightDataError now says what Bright Data said of the job (its status: "ready", "failed", "running"...) and its error
(the error record's code and message, short), and whether the post is gone: Reddit shows it removed or deleted, or
Bright Data says its page is no longer there. Then its comments can be taken as unverifiable without spending records
on them again (engine/precheck.py). Never a comment's words: they aren't in an error. Every answer here comes from a
made-up service: no test reaches the network.
"""

import pytest

from engine.bright_data import BrightDataError
from engine.config import BRIGHT_DATA_COMMENTS_DATASET as COMMENTS
from engine.config import BRIGHT_DATA_MAX_WAIT_SECONDS
from engine.tests.test_bright_data import POST_URL, FakeBrightData, FakeClock, comment_record, make_client, post_records


def failure(tmp_path, service, clock=None) -> BrightDataError:
    with pytest.raises(BrightDataError) as caught:
        make_client(tmp_path, service, clock).get_thread(POST_URL)
    assert not caught.value.account_problem  # this thread only: the next one may be read
    return caught.value


def test_an_error_record_for_the_comments_gives_the_jobs_status_and_bright_datas_error(tmp_path):
    error = failure(tmp_path, FakeBrightData(comments=[{"error": "Page not reachable", "error_code": "dead_page",
                                                        "input": {"url": POST_URL}}]))
    assert (error.status, error.error) == ("ready", "dead_page: Page not reachable")
    assert error.post_gone  # Bright Data's code for a page that is no longer there


@pytest.mark.parametrize("text", ["[removed]", "[deleted]"])
def test_no_comments_for_a_post_reddit_shows_removed_or_deleted_means_it_is_gone(tmp_path, text):
    post = post_records()
    post[0]["description"] = text
    error = failure(tmp_path, FakeBrightData(comments=[], post=post))
    assert (error.status, error.error, error.post_gone) == ("ready", "no comments", True)


def test_no_comments_for_a_post_that_is_still_there_is_a_failure_not_a_gone_post(tmp_path):
    error = failure(tmp_path, FakeBrightData(comments=[]))
    assert (error.status, error.error, error.post_gone) == ("ready", "no comments", False)


@pytest.mark.parametrize("said, gone", [("Post was removed by moderators", True), ("Post not found", True),
                                        ("Crawl blocked, try later", False)])
def test_what_the_error_says_tells_a_gone_post_from_a_failed_read(tmp_path, said, gone):
    error = failure(tmp_path, FakeBrightData(comments=[{"error": said, "input": {"url": POST_URL}}]))
    assert error.error == said and error.post_gone is gone


def test_a_failed_job_gives_failed_and_bright_datas_reason(tmp_path):
    service = FakeBrightData(answers={("progress", COMMENTS): (200, {"status": "failed", "error": "Crawl failed"})})
    error = failure(tmp_path, service)
    assert (error.status, error.error, error.post_gone) == ("failed", "Crawl failed", False)


def test_a_job_that_takes_too_long_is_still_running(tmp_path):
    error = failure(tmp_path, FakeBrightData(progress={COMMENTS: ["running"]}), FakeClock())
    assert error.status == "running" and str(BRIGHT_DATA_MAX_WAIT_SECONDS) in error.error and not error.post_gone


def test_an_answer_bright_data_wont_give_says_its_http_status(tmp_path):
    error = failure(tmp_path, FakeBrightData(answers={("snapshot", COMMENTS): (500, {"error": "internal"})}))
    assert error.status == "HTTP 500" and not error.post_gone


def test_the_error_is_short_and_on_one_line(tmp_path):
    long = "Something went wrong\n" + "x" * 500
    error = failure(tmp_path, FakeBrightData(comments=[{"error": long, "error_code": "crawl_failed",
                                                        "input": {"url": POST_URL}}]))
    assert len(error.error) <= 100 and "\n" not in error.error and error.error.startswith("crawl_failed: ")


def test_a_comment_record_with_words_but_no_id_gives_an_error_without_them(tmp_path):
    # A record Bright Data couldn't give an id is left out (it can't be linked or quoted): its words never reach the
    # error, which says only that no comments came.
    words = "My made-up kettle lasted nine years and still pours well."
    error = failure(tmp_path, FakeBrightData(comments=[comment_record(None, text=words)]))
    assert words not in str(error) and words not in error.error


def test_a_post_bright_data_says_is_not_found_and_no_comments_means_it_is_gone(tmp_path):
    error = failure(tmp_path, FakeBrightData(comments=[], post=[{"error": "Post not found", "error_code": "dead_page",
                                                                 "input": {"url": POST_URL}}]))
    assert error.post_gone and error.status == "ready"
    assert error.error == "no comments; the post: dead_page: Post not found"
