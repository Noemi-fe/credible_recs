"""`library add` through the archive also searches titles for the request's own needs (13 Oct 2026, the data round).

Arctic Shift's title search answers the newest 100 posts of each search, so a search for "conditioner" over the last 3
years in r/curlyhair finds only the last few months of small posts, and over the 6 years before only the newest of
those: the threads that ask the request's exact question ("best conditioner for curly hair?", often years old and big)
were out of reach unless they happened to be recent. Now the archive's round also searches the product's title word
with each of the request's first ARCHIVE_NEED_WORDS need words ("conditioner curly"), in each of its subreddits, over
the whole history: few posts match both, so the search reaches back years without timing out, and those threads join
the candidates (ranked as before: a need word in the title already earns points). Parse's paid path is unchanged.

Every test uses a fake archive and made-up data: no network.
"""

from datetime import UTC, datetime

from engine.config import ARCHIVE_NEED_WORDS, SUBREDDITS
from engine.query import parse_query
from engine.sources import ArchiveSource, search_archive
from engine.tests.test_archive_reader import FakeArchiveClient, search_post


class TitleSearch(FakeArchiveClient):
    """Answers a title search with the posts whose titles hold every word searched, within its dates, newest first, and
    only the newest `cap` of them, as Arctic Shift answers the newest of its matches (100 for real)."""

    def __init__(self, posts=(), cap=1):
        super().__init__(posts)
        self.cap = cap

    def search_posts(self, subreddit, title, limit=25, before=None, after=None):
        self.searches.append((subreddit, title))
        self.asked.append({"limit": limit, "before": before, "after": after})
        words = title.lower().split()
        found = [dict(p) for p in self.posts
                 if p["subreddit"] == subreddit and all(w in p["title"].lower() for w in words)
                 and (after is None or day(p) >= after) and (before is None or day(p) < before)]
        return sorted(found, key=lambda p: p["created_utc"], reverse=True)[:self.cap]


def day(post: dict) -> str:
    return datetime.fromtimestamp(post["created_utc"], UTC).date().isoformat()


def post_on(post_id: str, title: str, comments: int, posted: str) -> dict:
    """One archive search result posted on the given day, in r/curlyhair. Content is made up."""
    return search_post(post_id, title, comments, "curlyhair") | {
        "created_utc": datetime.fromisoformat(posted).replace(tzinfo=UTC).timestamp()}


def curly_posts() -> list[dict]:
    # The newest "conditioner" titles of each window are small, unrelated posts; the thread asking the request's
    # question is years old.
    return [
        post_on("1new01", "Conditioner for my scalp?", 12, "2026-09-01"),
        post_on("1mid01", "Conditioner smells odd", 9, "2023-05-01"),
        post_on("1old01", "Best conditioner for curly hair? Need recommendations", 240, "2019-06-01"),
    ]


def test_the_decided_value():
    assert ARCHIVE_NEED_WORDS == 2


def test_the_archive_searches_the_product_word_with_the_requests_needs_over_the_whole_history():
    client = TitleSearch(curly_posts())
    search_archive(client, parse_query("conditioner for curly hair"), 16, 0, posts_each=100, older_than_years=3,
                   max_failures=3, need_searches=ARCHIVE_NEED_WORDS)
    need_searches = [(s, t, a) for (s, t), a in zip(client.searches, client.asked) if t == "conditioner curly"]
    assert {s for s, _, _ in need_searches} == set(SUBREDDITS["haircare"])  # every subreddit of the request
    assert all(a["after"] is None and a["before"] is None for _, _, a in need_searches)  # the whole history


def test_a_thread_asking_the_exact_question_is_found_and_ranked_first():
    client = TitleSearch(curly_posts())
    ranked = ArchiveSource(client).rank_candidates(parse_query("conditioner for curly hair"))
    assert [p["id"] for p in ranked][:1] == ["1old01"]


def test_without_the_need_search_that_thread_was_out_of_reach():
    client = TitleSearch(curly_posts())
    found = search_archive(client, parse_query("conditioner for curly hair"), 16, 0, posts_each=100,
                           older_than_years=3, max_failures=3)
    assert "1old01" not in {p["id"] for p in found}


def test_at_most_the_first_need_words_are_searched():
    client = TitleSearch(curly_posts())
    search_archive(client, parse_query("gentle shampoo for wavy fine oily hair"), 16, 0, posts_each=100,
                   older_than_years=3, max_failures=3, need_searches=ARCHIVE_NEED_WORDS)
    paired = {t for _, t in client.searches if " " in t}
    assert paired == {"shampoo gentle", "shampoo wavy"}


def test_a_request_with_no_needs_searches_no_more():
    client = TitleSearch(curly_posts())
    search_archive(client, parse_query("conditioner"), 16, 0, posts_each=100, older_than_years=3, max_failures=3,
                   need_searches=ARCHIVE_NEED_WORDS)
    assert all(t == "conditioner" for _, t in client.searches)


def test_without_need_words_asked_for_the_search_is_as_before():
    client = TitleSearch(curly_posts())
    search_archive(client, parse_query("conditioner for curly hair"), 16, 0, posts_each=100, older_than_years=3,
                   max_failures=3)
    assert all(t == "conditioner" for _, t in client.searches)
