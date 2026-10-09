"""Checking a quote against the live comment on Reddit, through Reddit's embed page, just before it is shown.

Every page here is a small made-up stand-in for Reddit's embed page: no test touches the network.
"""

from datetime import UTC, datetime, timedelta

from engine.live_check import LiveChecker, embed_url

URL = "https://www.reddit.com/r/BuyItForLife/comments/1kett01/which_kettle/c1aaaa/"
QUOTE = "My Zojirushi kettle has lasted 6 years and still boils perfectly."


def page(body: str, author: str = "kettle_fan") -> bytes:
    """A minimal embed page: the writer's name and the comment's text, as Reddit's embed page lays them out."""
    return (f'<html><a href="https://www.reddit.com/user/{author}/?utm_source=embedv2">{author}</a>'
            f'<div class="text-14"><div class="inline-block max-w-full w-full"><p>{body}</p></div></div></html>').encode()


def deleted_page() -> bytes:
    return (b'<html><span class="font-bold" data-testid="user-name">[deleted]</span>'
            b'<div class="text-14"><div class="inline-block max-w-full w-full"><p>[removed]</p></div></div></html>')


class FakeReddit:
    def __init__(self, answer=(200, page(QUOTE + " Best purchase ever.")), fail=False):
        self.answer, self.fail, self.asked = answer, fail, []

    def __call__(self, url, headers):
        self.asked.append(url)
        if self.fail:
            raise TimeoutError("timed out")
        return self.answer


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 9, 12, tzinfo=UTC)

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += timedelta(seconds=seconds)


def checker(tmp_path, reddit, clock=None):
    clock = clock or Clock()
    return LiveChecker(cache_dir=tmp_path / "cache", fetch=reddit, clock=clock, sleep=clock.sleep)


def test_the_embed_page_of_a_comment():
    assert embed_url(URL) == "https://embed.reddit.com/r/BuyItForLife/comments/1kett01/comment/c1aaaa/?embed=true&showmedia=false"


def test_a_live_comment_with_the_quote_is_shown(tmp_path):
    result = checker(tmp_path, FakeReddit()).check(URL, QUOTE)
    assert (result.status, result.show) == ("ok", True)


def test_a_deleted_or_removed_comment_is_never_shown(tmp_path):
    result = checker(tmp_path, FakeReddit(answer=(200, deleted_page()))).check(URL, QUOTE)
    assert (result.status, result.show) == ("gone", False)


def test_an_edited_comment_that_no_longer_has_the_quote_is_not_shown(tmp_path):
    result = checker(tmp_path, FakeReddit(answer=(200, page("Edit: it died last week, avoid.")))).check(URL, QUOTE)
    assert (result.status, result.show) == ("changed", False)


def test_when_reddit_cant_be_read_the_quote_is_not_shown(tmp_path):
    assert checker(tmp_path, FakeReddit(fail=True)).check(URL, QUOTE).status == "unknown"
    assert checker(tmp_path, FakeReddit(answer=(404, b"not found"))).check(URL, QUOTE).show is False
    assert checker(tmp_path, FakeReddit(answer=(200, b"<html>a page with no comment on it</html>"))).check(URL, QUOTE).show is False


def test_html_codes_in_the_page_are_read_as_characters(tmp_path):
    quote = "Black & Decker kettle, 5 years and counting."
    result = checker(tmp_path, FakeReddit(answer=(200, page("Black &amp; Decker kettle, 5 years and counting.")))).check(URL, quote)
    assert result.show


def test_each_comment_is_read_once_within_48_hours_then_again(tmp_path):
    reddit, clock = FakeReddit(), Clock()
    live = checker(tmp_path, reddit, clock)
    live.check(URL, QUOTE)
    live.check(URL, "still boils perfectly")  # another quote from the same comment: the saved page answers
    assert len(reddit.asked) == 1
    clock.now += timedelta(hours=49)
    live.check(URL, QUOTE)
    assert len(reddit.asked) == 2


def test_calls_are_spaced_out(tmp_path):
    clock = Clock()
    live = checker(tmp_path, FakeReddit(), clock)
    live.check(URL, QUOTE)
    live.check(URL.replace("c1aaaa", "c2bbbb"), QUOTE)
    assert clock.now - datetime(2026, 10, 9, 12, tzinfo=UTC) >= timedelta(seconds=live.min_interval)


def test_only_the_comments_status_and_text_are_saved_never_the_page(tmp_path):
    checker(tmp_path, FakeReddit()).check(URL, QUOTE)
    saved = "".join(p.read_text() for p in (tmp_path / "cache").glob("*.json"))
    assert "utm_source" not in saved and "<div" not in saved
