"""Retrieval (module 2): finding the threads for an understood request, from saved files or live through Parse.

Every test uses saved test files or a fake Parse client, so no test ever touches the network or spends credits.
"""

import pytest

from engine.gold import DEFAULT_GOLD_DIR, GoldSetError
from engine.models import Thread
from engine.parse_reddit import ParseAPIError
from engine.query import parse_query
from engine.sources import LocalSource, ParseSource, Source, relevance, without_unusable_comments
from engine.tests.factories import make_comment, make_thread, write_gold

KETTLE = "electric kettle that lasts 10+ years"  # kitchen; searches BuyItForLife, tea, Coffee


def kitchen_thread(thread_id: str, title: str, body: str = "", comments=(), num_comments=None, community="BuyItForLife") -> dict:
    """A valid kitchen thread. `comments` are bodies, or full comment dicts when a test needs more control."""
    return make_thread(
        id=thread_id,
        community=community,
        category="kitchen",
        title=title,
        body=body,
        url=f"https://www.reddit.com/r/{community}/comments/{thread_id}/post/",
        num_comments=len(comments) if num_comments is None else num_comments,
        comments=[
            c if isinstance(c, dict) else make_comment(f"{thread_id}c{i}", thread_id=thread_id, body=c)
            for i, c in enumerate(comments)
        ],
    )


def local_source(tmp_path, threads: list[dict]) -> LocalSource:
    return LocalSource(write_gold(tmp_path, threads) / "threads")


def ids(threads: list[Thread]) -> list[str]:
    return [t.id for t in threads]


# --- The shared interface ---

def thread_with_every_kind_of_comment() -> dict:
    """A kettle thread holding a deleted, a removed, a link-only and a non-English comment."""
    return kitchen_thread(
        "1kettle",
        "Electric kettle that lasts?",
        comments=[
            make_comment("k1ok", thread_id="1kettle", body="My Dualit kettle is 12 years old and still fine."),
            make_comment("k2del", thread_id="1kettle", body="[deleted]", author=None, status="deleted"),
            make_comment("k3rem", thread_id="1kettle", body="[removed]", status="removed"),
            make_comment("k4link", thread_id="1kettle", body="https://www.example.com/kettle"),
            make_comment("k5it", thread_id="1kettle", body="Il mio bollitore dura da dieci anni."),
        ],
        num_comments=60,
    )


class FakeParseClient:
    """Stands in for ParseRedditClient: answers from canned posts and threads, and records every call."""

    def __init__(self, posts=(), threads=(), fail_on=None):
        self.posts = list(posts)  # every search answers with these
        self.threads = {t.id: t for t in threads}
        self.fail_on = fail_on  # "search" or "get_thread": that call raises, like Parse does when credits run out
        self.searches: list[tuple[str, str]] = []
        self.fetches: list[tuple[str, str]] = []

    def search(self, subreddit, query, limit=25, sort="relevance", time_filter="all"):
        self.searches.append((subreddit, query))
        if self.fail_on == "search":
            raise ParseAPIError("This call would go over the monthly 200 credits (200 used); nothing was fetched.")
        return {"posts": [dict(p) for p in self.posts], "count": len(self.posts), "after": None}

    def get_thread(self, subreddit, post_id, limit=500, sort="top"):
        self.fetches.append((subreddit, post_id))
        if self.fail_on == "get_thread":
            raise ParseAPIError("Parse answered 500 to get_post_comments")
        if post_id in self.threads:
            return self.threads[post_id]
        return Thread.model_validate(kitchen_thread(post_id, f"Thread {post_id}", community=subreddit))

    @property
    def credits(self) -> int:
        return 2 * (len(self.searches) + len(self.fetches))


def post(post_id: str, title: str = "Electric kettle that lasts?", num_comments: int = 40, subreddit: str = "BuyItForLife") -> dict:
    """One search result, shaped like Parse's search_posts answer. Content is made up."""
    return {
        "id": post_id, "title": title, "selftext": "", "score": 25, "num_comments": num_comments,
        "created_utc": 1740819600.0, "permalink": f"/r/{subreddit}/comments/{post_id}/post/", "subreddit": subreddit,
    }


def test_both_sources_follow_the_one_interface(tmp_path):
    assert isinstance(local_source(tmp_path, []), Source)
    assert isinstance(ParseSource(client=FakeParseClient()), Source)


def test_same_request_gives_the_same_result_from_both_sources(tmp_path):
    saved = thread_with_every_kind_of_comment()
    local = local_source(tmp_path, [saved]).find_threads(parse_query(KETTLE))

    live_thread = Thread.model_validate(saved)
    client = FakeParseClient(posts=[post("1kettle", num_comments=60)], threads=[live_thread])
    live = ParseSource(client=client).find_threads(parse_query(KETTLE))

    assert all(type(t) is Thread for t in local + live)
    assert ids(local) == ids(live) == ["1kettle"]
    assert local == live  # same fields, same values, same comments dropped


@pytest.mark.parametrize("text", ["something for my face", "a good laptop"])
def test_unclear_or_out_of_scope_request_finds_nothing_and_does_nothing(tmp_path, text):
    query = parse_query(text)
    assert query.status != "ok"
    # The folder doesn't exist, so reading it would raise: an empty answer proves nothing was read.
    assert LocalSource(tmp_path / "missing" / "threads").find_threads(query) == []
    client = FakeParseClient(posts=[post("1kettle")])
    assert ParseSource(client=client).find_threads(query) == []
    assert client.searches == [] and client.fetches == []


# --- Deleted and removed comments ---

def test_deleted_and_removed_comments_are_left_out_of_a_copy():
    thread = Thread.model_validate(thread_with_every_kind_of_comment())
    cleaned = without_unusable_comments(thread)
    assert [c.id for c in cleaned.comments] == ["k1ok", "k4link", "k5it"]
    assert len(thread.comments) == 5  # the thread passed in is left as it was
    assert cleaned.num_comments == thread.num_comments == 60  # the count Reddit reported stays


def test_local_source_drops_deleted_and_removed_but_keeps_link_only_and_non_english(tmp_path):
    source = local_source(tmp_path, [thread_with_every_kind_of_comment()])
    for _ in range(2):  # asking twice gives the same answer: the loaded thread isn't changed by the first answer
        [found] = source.find_threads(parse_query(KETTLE))
        assert [c.id for c in found.comments] == ["k1ok", "k4link", "k5it"]
    bodies = {c.id: c.body for c in found.comments}
    assert bodies["k4link"] == "https://www.example.com/kettle"
    assert bodies["k5it"] == "Il mio bollitore dura da dieci anni."


def test_parse_source_drops_deleted_and_removed_without_changing_the_fetched_thread():
    fetched = Thread.model_validate(thread_with_every_kind_of_comment())
    client = FakeParseClient(posts=[post("1kettle")], threads=[fetched])
    [found] = ParseSource(client=client).find_threads(parse_query(KETTLE))
    assert [c.id for c in found.comments] == ["k1ok", "k4link", "k5it"]
    assert len(fetched.comments) == 5


# --- LocalSource: relevance ---

def test_picks_the_kettle_thread_over_a_knife_thread(tmp_path):
    source = local_source(tmp_path, [
        kitchen_thread("1knife", "Best chef's knife under £100?", comments=["Get a Victorinox."] * 3, community="chefknives"),
        kitchen_thread("1kettle", "All steel electric kettle that lasts for years?", comments=["Mine is a Dualit."]),
    ])
    # The knife thread never mentions a kettle, so it scores zero and isn't returned at all.
    assert ids(source.find_threads(parse_query(KETTLE))) == ["1kettle"]


def test_ignores_threads_of_the_other_category(tmp_path):
    skincare = make_thread(title="Does kettle limescale water hurt my skin?", body="My kettle leaves white flakes.")
    source = local_source(tmp_path, [skincare, kitchen_thread("1kettle", "Kettle advice")])
    assert ids(source.find_threads(parse_query(KETTLE))) == ["1kettle"]


def test_respects_the_limit_and_returns_the_best_first(tmp_path):
    threads = [kitchen_thread(f"1k{n}", "Which kettle?", comments=["A kettle comment."] * n) for n in range(5)]
    source = local_source(tmp_path, threads)
    assert ids(source.find_threads(parse_query(KETTLE), limit=2)) == ["1k4", "1k3"]
    assert ids(source.find_threads(parse_query(KETTLE), limit=1)) == ["1k4"]


def test_title_outweighs_body_and_comments(tmp_path):
    source = local_source(tmp_path, [
        kitchen_thread("1body", "Something that lasts?", body="Thinking of an electric kettle.",
                       comments=["The kettle from Dualit."] * 8, num_comments=900),
        kitchen_thread("1title", "Electric kettle recommendations", comments=["No idea."]),
    ])
    assert ids(source.find_threads(parse_query(KETTLE))) == ["1title", "1body"]


def test_relevance_points():
    def score(**fields):
        thread = Thread.model_validate(kitchen_thread("1x", **{"title": "Help", **fields}))
        return relevance(thread, "electric kettle")

    assert score() == 0
    assert score(title="My KETTLE died") == 3  # any case
    assert score(body="Looking at kettles.") == 1  # plural counts
    assert score(comments=["kettle"] * 2 + ["toaster"] * 3) == pytest.approx(0.4)  # 2 of the 5 needed for the full point
    assert score(comments=["kettle"] * 12) == 1  # comments add at most 1
    assert score(title="Gooseneck or not?", body="kettle", comments=["kettle"] * 5) == 5


def test_mentions_are_whole_words():
    thread = Thread.model_validate(kitchen_thread("1x", "Kettlebell workout gear", body="A kettledrum.", comments=["kettlecorn"]))
    assert relevance(thread, "electric kettle") == 0
    pan = Thread.model_validate(kitchen_thread("1y", "Japanese panini press", comments=["A pantry staple."]))
    assert relevance(pan, "frying pan") == 0


def test_an_unknown_product_type_falls_back_to_the_words_of_its_name():
    # A future AI parser might name a product module 1 doesn't list.
    thread = Thread.model_validate(kitchen_thread("1x", "Best rice cooker?", body="Rice every day."))
    assert relevance(thread, "rice cooker") == 4
    assert relevance(thread, "Air Fryer") == 0


def test_ties_go_to_the_thread_with_more_comments(tmp_path):
    # Named so that file order alone would put the quiet thread first.
    source = local_source(tmp_path, [
        kitchen_thread("1aquiet", "Kettle?", num_comments=12),
        kitchen_thread("1zbusy", "Kettle?", num_comments=300),
    ])
    assert ids(source.find_threads(parse_query(KETTLE))) == ["1zbusy", "1aquiet"]


def test_a_thread_with_600_comments_works(tmp_path):
    comments = [f"Kettle number {n} still works." for n in range(600)]
    source = local_source(tmp_path, [kitchen_thread("1big", "Electric kettle that lasts?", comments=comments)])
    [found] = source.find_threads(parse_query(KETTLE))
    assert len(found.comments) == 600
    assert relevance(found, "electric kettle") == 4


def test_a_broken_thread_file_is_reported(tmp_path):
    broken = kitchen_thread("1kettle", "Kettle?", community="AskReddit")  # not a decided subreddit
    with pytest.raises(GoldSetError) as excinfo:
        local_source(tmp_path, [broken]).find_threads(parse_query(KETTLE))
    assert "r/AskReddit" in str(excinfo.value)


def test_reads_exactly_the_folder_it_is_given(tmp_path):
    # Any folder name works (a saved library needn't be called threads/), and it's never
    # quietly swapped for a threads/ folder next to it.
    write_gold(tmp_path, [kitchen_thread("1kettle", "Kettle?")])
    (tmp_path / "library").mkdir()
    assert LocalSource(tmp_path / "library").find_threads(parse_query(KETTLE)) == []
    assert [t.id for t in LocalSource(tmp_path / "threads").find_threads(parse_query(KETTLE))] == ["1kettle"]


def test_a_missing_folder_is_reported(tmp_path):
    with pytest.raises(GoldSetError, match="library"):
        LocalSource(tmp_path / "library").find_threads(parse_query(KETTLE))


# --- ParseSource: careful with credits ---

def test_searches_terms_in_order_then_subreddits_in_order_up_to_max_searches():
    query = parse_query(KETTLE)
    client = FakeParseClient()
    ParseSource(client=client, max_searches=4).find_threads(query)
    assert client.searches == [
        ("BuyItForLife", "electric kettle that lasts"),
        ("tea", "electric kettle that lasts"),
        ("Coffee", "electric kettle that lasts"),
        ("BuyItForLife", "electric kettle"),
    ]


@pytest.mark.parametrize("max_searches", [0, 1, 2, 3])
def test_never_more_than_max_searches(max_searches):
    client = FakeParseClient(posts=[post("1a")])
    ParseSource(client=client, max_searches=max_searches).find_threads(parse_query(KETTLE))
    assert len(client.searches) == max_searches


def test_a_post_found_twice_is_fetched_once():
    client = FakeParseClient(posts=[post("1a"), post("t3_1a"), post("1b")])  # every search returns the same posts
    found = ParseSource(client=client).find_threads(parse_query(KETTLE))
    assert len(client.searches) == 2
    assert client.fetches == [("BuyItForLife", "1a"), ("BuyItForLife", "1b")]
    assert ids(found) == ["1a", "1b"]


def test_posts_from_other_subreddits_or_with_too_few_comments_are_dropped():
    client = FakeParseClient(posts=[
        post("1other", subreddit="AskReddit"),
        post("1cooking", subreddit="Cooking"),  # a kitchen subreddit, but not one this request searches
        post("1quiet", num_comments=4),
        post("1edge", num_comments=5),
        post("1lower", subreddit="buyitforlife"),  # names match whatever the capitals
    ])
    ParseSource(client=client, min_comments=5).find_threads(parse_query(KETTLE))
    assert [post_id for _, post_id in client.fetches] == ["1lower", "1edge"]  # 40 comments, then 5


def test_title_mentions_first_then_more_comments():
    client = FakeParseClient(posts=[
        post("1busy", title="What lasts forever in your kitchen?", num_comments=500),
        post("1small", title="Kettle recommendations", num_comments=20),
        post("1big", title="Electric kettle that lasts?", num_comments=80),
    ])
    found = ParseSource(client=client).find_threads(parse_query(KETTLE), limit=3)
    assert ids(found) == ["1big", "1small", "1busy"]


def test_fetches_at_most_limit_threads_and_stays_within_the_credit_cap():
    client = FakeParseClient(posts=[post(f"1p{n}") for n in range(10)])
    found = ParseSource(client=client).find_threads(parse_query(KETTLE))
    assert len(found) == len(client.fetches) == 3
    assert client.credits <= 2 * 2 + 2 * 3 == 10

    client = FakeParseClient(posts=[post(f"1p{n}") for n in range(10)])
    ParseSource(client=client, max_searches=1).find_threads(parse_query(KETTLE), limit=1)
    assert client.credits == 4


@pytest.mark.parametrize("fail_on", ["search", "get_thread"])
def test_parse_errors_are_passed_on(fail_on):
    client = FakeParseClient(posts=[post("1a")], fail_on=fail_on)
    with pytest.raises(ParseAPIError):
        ParseSource(client=client).find_threads(parse_query(KETTLE))


# --- The real gold set, on Noemi's machine only ---

GOLD_THREADS = DEFAULT_GOLD_DIR / "threads"


@pytest.mark.skipif(not any(GOLD_THREADS.glob("*.json")), reason="no gold-set thread files on this machine")
def test_finds_kitchen_threads_for_a_kettle_in_the_real_gold_set():
    found = LocalSource(GOLD_THREADS).find_threads(parse_query(KETTLE))
    assert found
    assert all(t.category == "kitchen" for t in found)
    assert all(c.status == "ok" for t in found for c in t.comments)
