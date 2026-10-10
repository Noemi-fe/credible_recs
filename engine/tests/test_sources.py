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


def test_advice_first_then_the_need_then_comments():
    # Ranking changed on 7 Oct 2026 (Noemi approved): buying advice outranks size. "Kettle recommendations"
    # asks for advice, so it beats a bigger thread that only matches the need, which beats a viral one.
    client = FakeParseClient(posts=[
        post("1busy", title="What lasts forever in your kitchen?", num_comments=500),
        post("1small", title="Kettle recommendations", num_comments=20),
        post("1big", title="Electric kettle that lasts?", num_comments=80),
    ])
    found = ParseSource(client=client).find_threads(parse_query(KETTLE), limit=3)
    assert ids(found) == ["1small", "1big", "1busy"]


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


# --- ParseSource: threads as fetched, for the library ---

def test_raw_threads_come_as_fetched_with_deleted_and_removed_comments():
    fetched = Thread.model_validate(thread_with_every_kind_of_comment())
    client = FakeParseClient(posts=[post("1kettle")], threads=[fetched])
    [raw] = ParseSource(client=client).find_raw_threads(parse_query(KETTLE))
    assert raw == fetched  # nothing taken out: the library keeps deleted comments as stubs, so reply chains stay whole


def test_raw_threads_and_usable_threads_pick_the_same_threads_for_the_same_credits():
    posts = [post("1busy", title="What lasts forever?", num_comments=500), post("1big", num_comments=80), post("1small", num_comments=20)]
    raw_client, client = FakeParseClient(posts=posts), FakeParseClient(posts=posts)
    raw = ParseSource(client=raw_client).find_raw_threads(parse_query(KETTLE), limit=2)
    usable = ParseSource(client=client).find_threads(parse_query(KETTLE), limit=2)
    assert usable == [without_unusable_comments(t) for t in raw]
    assert ids(raw) == ["1big", "1small"]
    assert (raw_client.searches, raw_client.fetches) == (client.searches, client.fetches)


@pytest.mark.parametrize("text", ["something for my face", "a good laptop"])
def test_raw_threads_for_an_unclear_request_cost_nothing(text):
    client = FakeParseClient(posts=[post("1kettle")])
    assert ParseSource(client=client).find_raw_threads(parse_query(text)) == []
    assert client.searches == [] and client.fetches == []


# --- The real gold set, on Noemi's machine only ---

GOLD_THREADS = DEFAULT_GOLD_DIR / "threads"


@pytest.mark.skipif(not any(GOLD_THREADS.glob("*.json")), reason="no gold-set thread files on this machine")
def test_finds_kitchen_threads_for_a_kettle_in_the_real_gold_set():
    found = LocalSource(GOLD_THREADS).find_threads(parse_query(KETTLE))
    assert found
    assert all(t.category == "kitchen" for t in found)
    assert all(c.status == "ok" for t in found for c in t.comments)


# --- Finding threads for free with Arctic Shift, reading them with Parse ---

from engine.arctic_shift import ArcticShiftError  # noqa: E402
from engine.sources import finder_terms  # noqa: E402


class FakeFinder:
    """Stands in for ArcticShiftClient: free searches that answer with canned posts, or fail like a busy server."""

    def __init__(self, posts=(), fail=False):
        self.posts = list(posts)
        self.fail = fail
        self.searches: list[tuple[str, str]] = []

    def search_posts(self, subreddit, title, limit=25):
        self.searches.append((subreddit, title))
        if self.fail:
            raise ArcticShiftError("Arctic Shift answered 422: Timeout. Maybe slow down a bit")
        return [dict(p) for p in self.posts if p["subreddit"] == subreddit]


def test_finder_terms_are_the_short_words_people_put_in_titles():
    assert finder_terms("electric kettle") == ["kettle"]
    assert finder_terms("chef knife") == ["knife"]
    assert finder_terms("moisturiser") == ["moisturizer", "moisturiser"]  # both spellings
    assert finder_terms("espresso machine") == ["espresso machine"]
    assert finder_terms("something new") == ["something new"]  # unknown products: their own name


def test_with_a_finder_searching_costs_no_credits():
    client = FakeParseClient()
    finder = FakeFinder([post("1aaa", num_comments=90), post("1bbb", num_comments=20), post("1ccc", subreddit="tea")])
    threads = ParseSource(client=client, finder=finder).find_threads(parse_query(KETTLE), limit=2)
    assert client.searches == []  # no paid searches
    # r/BuyItForLife is the kettle's most specialist subreddit, so its smaller thread edges out r/tea's.
    assert ids(threads) == ["1aaa", "1bbb"] and client.credits == 4  # only the two threads read
    assert finder.searches[0] == ("BuyItForLife", "kettle")


def test_finder_searches_term_by_term_and_subreddit_by_subreddit_within_its_cap():
    finder = FakeFinder()
    ParseSource(client=FakeParseClient(), finder=finder, max_free_searches=5).find_threads(parse_query("moisturiser for dry skin"))
    assert finder.searches == [
        ("SkincareAddiction", "moisturizer"), ("AsianBeauty", "moisturizer"), ("30PlusSkinCare", "moisturizer"),
        ("SkincareAddictionUK", "moisturizer"), ("SkincareAddiction", "moisturiser"),
        # changed 7 Oct 2026: library mix / refresh cadence approved by Noemi. The warning searches follow,
        # under their own cap, so the 5 title-word searches above are unchanged.
        ("SkincareAddiction", "moisturizer irritation"), ("SkincareAddiction", "moisturizer broke me out"),
        ("SkincareAddiction", "moisturizer regret"), ("SkincareAddiction", "moisturizer avoid"),
    ]


def test_a_busy_finder_falls_back_to_paid_search():
    client = FakeParseClient(posts=[post("1aaa")])
    threads = ParseSource(client=client, finder=FakeFinder(fail=True)).find_threads(parse_query(KETTLE))
    assert client.searches and ids(threads) == ["1aaa"]


def test_finder_results_found_before_an_error_are_used_without_paying():
    class FailsSecond(FakeFinder):
        def search_posts(self, subreddit, title, limit=25):
            if self.searches:
                self.searches.append((subreddit, title))
                raise ArcticShiftError("Timeout. Maybe slow down a bit")
            return super().search_posts(subreddit, title, limit)

    client = FakeParseClient()
    threads = ParseSource(client=client, finder=FailsSecond([post("1aaa")])).find_threads(parse_query(KETTLE))
    assert client.searches == [] and ids(threads) == ["1aaa"]


def test_candidates_can_be_ranked_without_fetching_anything():
    client = FakeParseClient(posts=[post("1aaa", num_comments=12), post("1bbb", num_comments=90)])
    ranked = ParseSource(client=client).rank_candidates(parse_query(KETTLE))
    assert [p["id"] for p in ranked] == ["1bbb", "1aaa"]
    assert client.fetches == []


# --- Ranking candidates: buying advice beats popularity ---

from engine.sources import need_words, rank_posts  # noqa: E402


def candidate(post_id, title, num_comments=40, subreddit="BuyItForLife", flair=None, **extra):
    return {"id": post_id, "title": title, "num_comments": num_comments, "subreddit": subreddit, "link_flair_text": flair, **extra}


def test_need_words_are_the_specific_part_of_the_request():
    assert need_words(parse_query("burr coffee grinder for pour-over under £150")) == ["burr", "pourover"]
    assert need_words(parse_query("non-stick frying pan without PFAS that actually lasts")) == ["nonstick", "pfas", "last"]


def test_a_buying_advice_thread_beats_a_viral_one():
    query = parse_query("non-stick frying pan without PFAS that actually lasts")
    ranked = rank_posts(query, [
        candidate("1viral", "Caught a hot falling frying pan today, share your kitchen mistakes", 480, "Cooking"),
        candidate("1advice", "Best non-stick pan without PFAS? Mine keeps peeling", 45, "Cooking"),
    ])
    assert [p["id"] for p in ranked] == ["1advice", "1viral"]


def test_request_flair_counts_as_buying_advice():
    query = parse_query(KETTLE)
    ranked = rank_posts(query, [
        candidate("1show", "My kettle collection", 200),
        candidate("1req", "Kettle that won't die in two years", 30, flair="[Request]"),
    ])
    assert ranked[0]["id"] == "1req"


def test_the_specific_need_lifts_a_thread():
    query = parse_query("burr coffee grinder for pour-over under £150")
    ranked = rank_posts(query, [
        candidate("1generic", "Which grinder should I get?", 60, "Coffee"),
        candidate("1pour", "Which grinder for pour over?", 50, "Coffee"),
    ])
    assert ranked[0]["id"] == "1pour"


def test_comment_counts_matter_but_slowly():
    query = parse_query(KETTLE)
    ranked = rank_posts(query, [candidate("1small", "Kettle recommendations?", 20), candidate("1big", "Kettle recommendations?", 200)])
    assert ranked[0]["id"] == "1big"
    # ...but ten times the comments doesn't beat a thread that matches the need and asks for advice.
    ranked = rank_posts(query, [candidate("1viral", "My kettle", 900), candidate("1fit", "Kettle that lasts 10 years? Recommendations", 40)])
    assert ranked[0]["id"] == "1fit"


@pytest.mark.parametrize("extra", [{"title": "[deleted by user]"}, {"removed_by_category": "moderator"}, {"selftext": "[removed]"}])
def test_deleted_or_removed_posts_are_left_out(extra):
    post_ = candidate("1gone", "Kettle recommendations?", 300)
    post_.update(extra)
    assert rank_posts(parse_query(KETTLE), [post_, candidate("1ok", "Kettle?", 20)])[0]["id"] == "1ok"
    assert "1gone" not in [p["id"] for p in rank_posts(parse_query(KETTLE), [post_])]


@pytest.mark.parametrize("flair, counts", [("Question", False), ("Product Question", True), ("Buying Advice", True), ("[Request]", True)])
def test_only_buying_flairs_count_as_advice(flair, counts):
    query = parse_query("first chef's knife under £100 for a home cook")
    ranked = rank_posts(query, [
        candidate("1flair", "Why does no one make a 14 inch knife anymore", 100, "chefknives", flair=flair),
        candidate("1plain", "Knife collection", 120, "chefknives"),  # a little bigger, so only the flair can lift 1flair
    ])
    assert (ranked[0]["id"] == "1flair") == counts


@pytest.mark.parametrize("title", [
    "Daily recommendations for trustworthy, good knife stores",
    "Weekly Questions Thread",
    "[Discussion] Monthly kettle megathread",
])
def test_recurring_threads_are_left_out(title):
    # Recurring threads ("Daily…", "Weekly…") aren't about anyone's specific need.
    assert rank_posts(parse_query(KETTLE), [candidate("1recur", title, 400)]) == []


def test_small_threads_count_but_bigger_ones_on_the_same_question_win():
    # Noemi, 7 Oct 2026: don't drop small threads, but prefer threads with enough to learn from.
    query = parse_query("gentle exfoliant for sensitive skin under £30")
    ranked = rank_posts(query, [
        candidate("1small", "Best gentle exfoliant for sensitive skin?", 8, "SkincareAddiction"),  # matches 2 need words
        candidate("1big", "Best exfoliant for sensitive skin?", 60, "SkincareAddiction"),  # matches 1, but has more to learn from
        candidate("1viral", "My skincare shelf", 900, "SkincareAddiction"),
    ])
    assert [p["id"] for p in ranked] == ["1big", "1small", "1viral"]  # the small thread still beats an off-topic one


def test_free_results_that_all_fail_the_filters_fall_back_to_paid_search():
    # Arctic Shift answered, but only with tiny or recurring threads: Parse's search should still be tried.
    client = FakeParseClient(posts=[post("1good", num_comments=80)])
    finder = FakeFinder([post("1tiny", num_comments=2), post("1recur", title="Daily kettle thread", num_comments=300)])
    threads = ParseSource(client=client, finder=finder).find_threads(parse_query(KETTLE))
    assert client.searches and ids(threads) == ["1good"]


# --- The library's mix of thread kinds (Noemi, 7 Oct 2026) ---
# Advice threads give the picks, long-term-use threads the strongest evidence, warning threads the "skip these"
# list and the downsides. So each product's library is built from a mix of the three kinds.

from datetime import UTC, datetime, timedelta  # noqa: E402

from engine.sources import choose_mix, thread_kind  # noqa: E402

SKILLET = "cast iron skillet for a beginner"  # kitchen; searches castiron, BuyItForLife, Cooking
KNIFE = "first chef's knife under £100 for a home cook"  # kitchen; searches chefknives, BuyItForLife, Cooking
CLEANSER = "gentle cleanser for oily skin"  # skincare


@pytest.mark.parametrize("title, category, kind", [
    # Kitchen warnings
    ("My Fellow Stagg kettle died after 14 months", "kitchen", "warning"),
    ("Kettle is dead, lid hinge broken", "kitchen", "warning"),
    ("Thermostat failed on my Breville", "kitchen", "warning"),
    ("Kettle stopped working, never again", "kitchen", "warning"),
    ("I regret buying this kettle", "kitchen", "warning"),
    ("Don't buy the Cosori gooseneck", "kitchen", "warning"),
    ("Recall on Cuisinart kettles", "kitchen", "warning"),
    ("Mine only lasted 18 months", "kitchen", "warning"),
    ("Carbon steel pan: rust everywhere", "kitchen", "warning"),
    ("Le Creuset chipped after one use", "kitchen", "warning"),
    ("Enamel cracked on my dutch oven", "kitchen", "warning"),
    ("Coating flaking into food", "kitchen", "warning"),
    ("Non-stick pan peeling", "kitchen", "warning"),
    ("Kettle leaking from the base", "kitchen", "warning"),
    ("Disappointed with my Smeg", "kitchen", "warning"),
    ("Worst kettle I've owned", "kitchen", "warning"),
    ("Returned my third kettle this year", "kitchen", "warning"),
    # A warning wins over long-term use and advice; long-term use wins over advice.
    ("Only lasted 2 years: which kettle actually lasts?", "kitchen", "warning"),
    ("Which kettle lasts 10 years?", "kitchen", "long_term"),
    # Long-term use
    ("Dualit kettle, 12 years later", "kitchen", "long_term"),
    ("Ten years later, still my favourite pan", "kitchen", "long_term"),
    ("Update on my carbon steel pan", "kitchen", "long_term"),
    ("Long-term review of the Fellow Stagg", "kitchen", "long_term"),
    ("Still going after decades", "kitchen", "long_term"),
    # Advice, and everything else
    ("Best electric kettle?", "kitchen", "advice"),
    ("Recommendations for a gooseneck kettle", "kitchen", "advice"),
    ("My kettle collection", "kitchen", "other"),
    # Skincare warnings
    ("This moisturizer broke me out", "skincare", "warning"),
    ("Irritation from tretinoin", "skincare", "warning"),
    ("Sunscreen irritated my eyes", "skincare", "warning"),
    ("Bad reaction to a new serum", "skincare", "warning"),
    ("Does this burn for anyone else?", "skincare", "warning"),
    ("Burning after the Ordinary peel", "skincare", "warning"),
    ("Rash after switching sunscreen", "skincare", "warning"),
    ("Worst cleanser I've tried", "skincare", "warning"),
    ("Returned it after a week", "skincare", "warning"),
    # Breakouts and acne alone are usually the need, not a warning.
    ("Best cleanser for breakouts?", "skincare", "advice"),
    ("Acne cleanser routine", "skincare", "other"),
    ("Breakouts on my chin", "skincare", "other"),
    # Kitchen-only warning words mean something else in skincare: a peel is a product.
    ("Peeling solution worth it?", "skincare", "advice"),
    ("Moisturizer, 3 years later", "skincare", "long_term"),
])
def test_thread_kind_from_the_title(title, category, kind):
    assert thread_kind({"title": title}, category) == kind


def test_an_advice_flair_makes_a_thread_advice():
    assert thread_kind({"title": "Kettle that won't quit", "link_flair_text": "[Request]"}, "kitchen") == "advice"
    assert thread_kind({"title": "Kettle that won't quit", "link_flair_text": "Question"}, "kitchen") == "other"
    # A warning in the title still wins over an advice flair.
    assert thread_kind({"title": "My kettle died, what now", "link_flair_text": "Request"}, "kitchen") == "warning"


def test_a_post_without_a_title_is_other():
    assert thread_kind({"title": None}, "kitchen") == "other"
    assert thread_kind({}, "skincare") == "other"


# --- rank_posts: care, news and deals threads lose points ---

@pytest.mark.parametrize("request_text, title, subreddit", [
    (SKILLET, "How I clean my cast iron skillet", "castiron"),
    (SKILLET, "Cleaning a rusty skillet", "castiron"),
    (SKILLET, "Skillet seasoning came out sticky", "castiron"),
    (SKILLET, "Restoration of my grandmother's skillet", "castiron"),
    (KNIFE, "Sharpening my first knife on a whetstone", "chefknives"),
    (SKILLET, "Lodge announced a new skillet line", "castiron"),
    (SKILLET, "Guess the price of this vintage skillet", "castiron"),
    (KNIFE, "Knife sale this weekend", "chefknives"),
    (SKILLET, "Great deal on a Lodge skillet", "castiron"),
    (CLEANSER, "Cleanser sale at Boots", "SkincareAddiction"),
])
def test_care_news_and_deals_threads_without_advice_words_lose_points_but_stay(request_text, title, subreddit):
    # Changed 7 Oct 2026 (Noemi): they rank lower instead of being left out, since some still hold useful
    # experience (she judged a "Yeti… guess the price" thread useful). Same size and place as a plain thread
    # naming the product, they now come second.
    plain = {SKILLET: "Cast iron skillet", KNIFE: "Chef knife", CLEANSER: "Cleanser"}[request_text]
    ranked = rank_posts(parse_query(request_text), [candidate("1off", title, 400, subreddit), candidate("1plain", plain, 400, subreddit)])
    assert [p["id"] for p in ranked] == ["1plain", "1off"]


@pytest.mark.parametrize("request_text, title, subreddit", [
    (SKILLET, "Best skillet for a beginner? how to season?", "castiron"),
    (KNIFE, "Which whetstone for sharpening a first knife?", "chefknives"),
    (SKILLET, "Is this skillet deal worth it?", "castiron"),
    (KETTLE, "Electric kettle that's easy to clean", "BuyItForLife"),  # a buying need, not a cleaning thread
    ("retinol for beginners", "How to deal with retinol irritation", "SkincareAddiction"),  # "deal with" isn't a deal
    # Chosen 7 Oct 2026: the care words apply to kitchen gear only. In skincare "restoring" is what a product does.
    ("moisturiser for dry skin", "Barrier restoring moisturizer for dry skin", "SkincareAddiction"),
])
def test_threads_with_advice_words_or_a_different_meaning_stay(request_text, title, subreddit):
    assert [p["id"] for p in rank_posts(parse_query(request_text), [candidate("1ok", title, 40, subreddit)])] == ["1ok"]


# --- rank_posts: newer skincare threads are preferred ---

NOW = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
THREE_YEARS_BEFORE_NOW = datetime(2023, 10, 7, 12, 0, tzinfo=UTC)


def dated(post_id, title, num_comments, subreddit, created: datetime | None) -> dict:
    extra = {"created_utc": created.timestamp()} if created is not None else {}
    return candidate(post_id, title, num_comments, subreddit, **extra)


@pytest.mark.parametrize("old_comments, first", [
    (527, "1recent"),  # the old thread is ahead by 1.4 points on comments: the 1.5-point penalty puts it behind
    (835, "1old"),  # ahead by 1.6: still first after the penalty
])
def test_skincare_threads_older_than_three_years_lose_one_and_a_half_points(old_comments, first):
    title = "Best cleanser for oily skin?"
    ranked = rank_posts(parse_query(CLEANSER), [
        dated("1old", title, old_comments, "SkincareAddiction", NOW - timedelta(days=4 * 365)),
        dated("1recent", title, 20, "SkincareAddiction", NOW - timedelta(days=365)),
    ], now=NOW)
    assert ranked[0]["id"] == first


@pytest.mark.parametrize("created, penalised", [
    (THREE_YEARS_BEFORE_NOW, False),  # "older than 3 years" means more than 3
    (THREE_YEARS_BEFORE_NOW - timedelta(seconds=1), True),
    (None, False),  # no date: no penalty
])
def test_the_age_penalty_starts_after_exactly_three_years(created, penalised):
    title = "Best cleanser for oily skin?"
    ranked = rank_posts(parse_query(CLEANSER), [
        dated("1old", title, 527, "SkincareAddiction", created),
        dated("1recent", title, 20, "SkincareAddiction", NOW - timedelta(days=30)),
    ], now=NOW)
    assert ranked[0]["id"] == ("1recent" if penalised else "1old")


def test_kitchen_threads_have_no_age_penalty():
    ranked = rank_posts(parse_query(KETTLE), [
        dated("1old", "Best electric kettle?", 527, "BuyItForLife", NOW - timedelta(days=10 * 365)),
        dated("1recent", "Best electric kettle?", 20, "BuyItForLife", NOW - timedelta(days=30)),
    ], now=NOW)
    assert ranked[0]["id"] == "1old"


def test_without_a_given_time_the_age_penalty_uses_the_real_clock():
    real_now = datetime.now(UTC)
    ranked = rank_posts(parse_query(CLEANSER), [
        dated("1old", "Best cleanser for oily skin?", 527, "SkincareAddiction", real_now - timedelta(days=4 * 365)),
        dated("1recent", "Best cleanser for oily skin?", 20, "SkincareAddiction", real_now - timedelta(days=30)),
    ])
    assert ranked[0]["id"] == "1recent"


# --- choose_mix: a mix of kinds, no subreddit dominating ---

ADVICE, WARNING, LONG_TERM, OTHER = "Best kettle?", "My kettle died", "Kettle, 10 years later", "My kettle collection"


def mix_ids(ranked, **kwargs) -> list[str]:
    return [p["id"] for p in choose_mix(parse_query(KETTLE), ranked, **kwargs)]


def test_choose_mix_fills_each_kinds_quota_in_rank_order():
    ranked = [
        candidate("1a1", ADVICE, subreddit="BuyItForLife"),
        candidate("1a2", ADVICE, subreddit="tea"),
        candidate("1o1", OTHER, subreddit="Coffee"),
        candidate("1w1", WARNING, subreddit="BuyItForLife"),
        candidate("1a3", ADVICE, subreddit="Coffee"),
        candidate("1a4", ADVICE, subreddit="tea"),  # advice is full by now: 3
        candidate("1l1", LONG_TERM, subreddit="tea"),
        candidate("1w2", WARNING, subreddit="Coffee"),
        candidate("1w3", WARNING, subreddit="BuyItForLife"),  # warnings are full by now: 2
    ]
    # The defaults: 6 threads, 3 advice, 1 long-term, 2 warnings, at most 2 per subreddit.
    assert mix_ids(ranked) == ["1a1", "1a2", "1w1", "1a3", "1l1", "1w2"]


def test_choose_mix_takes_at_most_two_threads_from_one_subreddit():
    ranked = [
        candidate("1a1", ADVICE, subreddit="BuyItForLife"),
        candidate("1a2", ADVICE, subreddit="buyitforlife"),  # the same subreddit, whatever the capitals
        candidate("1a3", ADVICE, subreddit="BuyItForLife"),
        candidate("1a4", ADVICE, subreddit="tea"),
    ]
    assert mix_ids(ranked, total=3, mix={"advice": 3}) == ["1a1", "1a2", "1a4"]
    assert mix_ids(ranked, total=3, mix={"advice": 3}, per_subreddit=3) == ["1a1", "1a2", "1a3"]


def test_empty_slots_go_to_the_best_remaining_kinds_and_other_threads_come_last():
    ranked = [
        candidate("1o1", OTHER, subreddit="BuyItForLife"),
        candidate("1a1", ADVICE, subreddit="tea"),
        candidate("1a2", ADVICE, subreddit="Coffee"),
        candidate("1a3", ADVICE, subreddit="BuyItForLife"),
        candidate("1a4", ADVICE, subreddit="tea"),
        candidate("1l1", LONG_TERM, subreddit="Coffee"),
    ]
    # No warnings at all: the 2 warning slots go to a 4th advice thread first, then to the "other" thread.
    assert mix_ids(ranked, total=5) == ["1a1", "1a2", "1a3", "1a4", "1l1"]
    assert mix_ids(ranked, total=6) == ["1o1", "1a1", "1a2", "1a3", "1a4", "1l1"]  # returned in rank order


def test_filling_empty_slots_still_respects_the_subreddit_cap():
    ranked = [
        candidate("1a1", ADVICE, subreddit="BuyItForLife"),
        candidate("1a2", ADVICE, subreddit="BuyItForLife"),
        candidate("1w1", WARNING, subreddit="BuyItForLife"),
        candidate("1a3", ADVICE, subreddit="tea"),
    ]
    assert mix_ids(ranked, total=4, mix={"advice": 1}) == ["1a1", "1a2", "1a3"]


def test_a_kind_missing_from_the_mix_gets_no_reserved_slots():
    ranked = [
        candidate("1a1", ADVICE, subreddit="BuyItForLife"),
        candidate("1a2", ADVICE, subreddit="tea"),
        candidate("1a3", ADVICE, subreddit="Coffee"),
        candidate("1w1", WARNING, subreddit="Coffee"),
    ]
    # The warning has no slot of its own, so the third slot goes to the better-ranked advice thread.
    assert mix_ids(ranked, total=3, mix={"advice": 2}) == ["1a1", "1a2", "1a3"]


def test_without_filling_only_the_quotas_are_taken():
    ranked = [
        candidate("1a1", ADVICE, subreddit="BuyItForLife"),
        candidate("1w1", WARNING, subreddit="tea"),
        candidate("1a2", ADVICE, subreddit="Coffee"),
    ]
    assert mix_ids(ranked, total=3, mix={"warning": 3}, fill=False) == ["1w1"]
    assert mix_ids(ranked, total=3, mix={"advice": 2}, fill=False) == ["1a1", "1a2"]
    assert mix_ids(ranked, total=3, mix={"long_term": 3}, fill=False) == []


def test_choose_mix_never_goes_over_the_total():
    ranked = [candidate(f"1x{n}", title, subreddit=sub) for n, (title, sub) in enumerate([
        (ADVICE, "BuyItForLife"), (WARNING, "tea"), (ADVICE, "Coffee"), (LONG_TERM, "tea"), (WARNING, "Coffee"),
    ])]
    assert mix_ids(ranked, total=2) == ["1x0", "1x1"]
    assert mix_ids(ranked, total=0) == []
    assert mix_ids([], total=6) == []


# --- ParseSource: warning searches (free) and the mix ---

class TermFinder(FakeFinder):
    """Answers each (subreddit, search) with its own posts, so a test can tell which search found what."""

    def __init__(self, answers, fail_on=()):
        super().__init__()
        self.answers = answers
        self.fail_on = set(fail_on)  # (subreddit, search) pairs that fail like a busy server

    def search_posts(self, subreddit, title, limit=25):
        self.searches.append((subreddit, title))
        if (subreddit, title) in self.fail_on:
            raise ArcticShiftError("Arctic Shift answered 429: Too many requests")
        return [dict(p) for p in self.answers.get((subreddit, title), [])]


def test_after_the_title_word_searches_the_finder_looks_for_warnings_in_the_most_specialist_subreddit():
    finder = FakeFinder()
    ParseSource(client=FakeParseClient(), finder=finder).find_threads(parse_query(KETTLE))
    assert finder.searches == [
        ("BuyItForLife", "kettle"), ("tea", "kettle"), ("Coffee", "kettle"),
        ("BuyItForLife", "kettle died"), ("BuyItForLife", "kettle broke"),
        ("BuyItForLife", "kettle regret"), ("BuyItForLife", "kettle avoid"),
    ]


def test_warning_searches_use_the_first_finder_term():
    finder = FakeFinder()
    ParseSource(client=FakeParseClient(), finder=finder, max_free_searches=0).find_threads(parse_query(SKILLET))
    # Changed on purpose 11 Oct 2026: cast iron fails in its own words (WARNING_SEARCHES_BY_TYPE), not "died"/"broke".
    assert finder.searches == [
        ("castiron", "cast iron cracked"), ("castiron", "cast iron warped"), ("castiron", "cast iron regret"),
        ("castiron", "cast iron avoid"),
    ]


@pytest.mark.parametrize("max_free, max_warning, expected", [
    (1, 2, [("BuyItForLife", "kettle"), ("BuyItForLife", "kettle died"), ("BuyItForLife", "kettle broke")]),
    (2, 0, [("BuyItForLife", "kettle"), ("tea", "kettle")]),
])
def test_warning_searches_have_their_own_cap(max_free, max_warning, expected):
    finder = FakeFinder()
    source = ParseSource(client=FakeParseClient(), finder=finder, max_free_searches=max_free, max_warning_searches=max_warning)
    source.find_threads(parse_query(KETTLE))
    assert finder.searches == expected


def test_threads_found_by_a_warning_search_become_candidates_for_free():
    client = FakeParseClient()
    finder = TermFinder({
        ("BuyItForLife", "kettle"): [post("1adv", "Best electric kettle?")],
        ("BuyItForLife", "kettle died"): [post("1died", "My kettle died after a year"), post("1adv", "Best electric kettle?")],
    })
    ranked = ParseSource(client=client, finder=finder).rank_candidates(parse_query(KETTLE))
    assert [p["id"] for p in ranked] == ["1adv", "1died"]  # each post once
    assert client.searches == client.fetches == []


def test_a_failing_warning_search_ends_the_free_search_and_keeps_what_was_found():
    client = FakeParseClient()
    finder = TermFinder(
        {("BuyItForLife", "kettle died"): [post("1died", "My kettle died after a year")]},
        fail_on=[("BuyItForLife", "kettle broke")],
    )
    ranked = ParseSource(client=client, finder=finder).rank_candidates(parse_query(KETTLE))
    assert finder.searches[-2:] == [("BuyItForLife", "kettle died"), ("BuyItForLife", "kettle broke")]  # nothing after the error
    assert [p["id"] for p in ranked] == ["1died"] and client.searches == []


def test_a_failing_title_word_search_skips_the_warning_searches_and_parse_search_runs_none():
    client = FakeParseClient(posts=[post("1aaa")])
    finder = FakeFinder(fail=True)
    ParseSource(client=client, finder=finder).find_threads(parse_query(KETTLE))
    assert finder.searches == [("BuyItForLife", "kettle")]  # a busy service isn't asked again
    # Parse's paid search runs only the request's own search terms: warning searches would cost credits.
    assert client.searches == [("BuyItForLife", "electric kettle that lasts"), ("tea", "electric kettle that lasts")]


def mix_posts() -> list[dict]:
    return [
        post("1a", "Best electric kettle?", 300, "BuyItForLife"),
        post("1b", "Electric kettle recommendations?", 200, "tea"),
        post("1c", "Which electric kettle?", 150, "Coffee"),
        post("1w", "My electric kettle died", 20, "Coffee"),
    ]


def test_without_a_mix_the_top_threads_are_fetched_as_before():
    client = FakeParseClient(posts=mix_posts())
    assert ids(ParseSource(client=client).find_raw_threads(parse_query(KETTLE), limit=3)) == ["1a", "1b", "1c"]


def test_with_a_mix_the_threads_fetched_are_the_mix():
    client = FakeParseClient(posts=mix_posts())
    raw = ParseSource(client=client).find_raw_threads(parse_query(KETTLE), limit=3, mix={"warning": 1})
    assert ids(raw) == ["1a", "1b", "1w"]  # the warning thread has its slot; the best 2 others fill the rest
    assert client.fetches == [("BuyItForLife", "1a"), ("tea", "1b"), ("Coffee", "1w")]
    assert client.credits == 2 * 2 + 2 * 3

    usable_client = FakeParseClient(posts=mix_posts())
    usable = ParseSource(client=usable_client).find_threads(parse_query(KETTLE), limit=3, mix={"warning": 1})
    assert usable == [without_unusable_comments(t) for t in raw]


def test_with_a_mix_and_no_filling_only_that_kind_is_fetched():
    client = FakeParseClient(posts=mix_posts())
    found = ParseSource(client=client).find_threads(parse_query(KETTLE), limit=3, mix={"warning": 3}, fill=False)
    assert ids(found) == ["1w"] and client.fetches == [("Coffee", "1w")]

    client = FakeParseClient(posts=mix_posts())
    assert ParseSource(client=client).find_raw_threads(parse_query(KETTLE), limit=1, mix={"long_term": 1}, fill=False) == []
    assert client.fetches == []  # none of that kind: nothing fetched, no credits for threads


def test_products_with_few_subreddits_can_still_fill_the_mix():
    # Changed 7 Oct 2026: the cap is 2 per subreddit, but a product with only 2 subreddits (coffee grinder: Coffee,
    # espresso) may take 3 from each so it can still reach 6 threads.
    query = parse_query("burr coffee grinder for pour-over under £150")
    ranked = [candidate(f"1c{n}", "Which grinder?", 50, "Coffee") for n in range(4)] + [
        candidate(f"1e{n}", "Which grinder?", 50, "espresso") for n in range(4)]
    chosen = choose_mix(query, ranked)
    assert len(chosen) == 6
    assert sum(p["subreddit"] == "Coffee" for p in chosen) == 3


def test_products_with_three_subreddits_keep_the_cap_of_two():
    query = parse_query(KETTLE)  # BuyItForLife, tea, Coffee
    ranked = [candidate(f"1b{n}", "Kettle recommendations?", 50, "BuyItForLife") for n in range(5)] + [
        candidate("1t", "Kettle recommendations?", 50, "tea")]
    assert sum(p["subreddit"] == "BuyItForLife" for p in choose_mix(query, ranked)) == 2


# --- Ranking refinements from the graded evaluation (7 Oct 2026) ---

def ranked_ids(request_text, posts):
    return [p["id"] for p in rank_posts(parse_query(request_text), posts)]


def test_a_title_starting_with_weekly_isnt_a_recurring_thread_unless_it_says_so():
    posts = [candidate("1wk", "[Product Request] Weekly exfoliator I could use instead of my toner?", 40, "SkincareAddiction")]
    assert ranked_ids("gentle exfoliant for sensitive skin under £30", posts) == ["1wk"]
    assert ranked_ids(KETTLE, [candidate("1q", "Weekly Questions Thread", 400)]) == []


def test_request_written_in_the_title_counts_as_advice():
    knife = "first chef's knife under £100 for a home cook"
    posts = [candidate("1why", "Serious question: why does no one make a 14 inch chef knife anymore?", 114, "chefknives", flair="Question"),
             candidate("1req", "[Request] Chef knife with a similar blade style that holds an edge", 243, "BuyItForLife")]
    assert ranked_ids(knife, posts)[0] == "1req"


def test_a_request_about_something_else_earns_less_than_experience_with_the_product():
    knife = "first chef's knife under £100 for a home cook"
    posts = [candidate("1gifts", "Long-lasting corporate gifts that actually get used", 624, "BuyItForLife", flair="[Request]"),
             candidate("1cutco", "These cutco knives my parents bought 25 years ago", 602, "BuyItForLife", flair="Vintage")]
    assert ranked_ids(knife, posts)[0] == "1cutco"


@pytest.mark.parametrize("title", ["I've used this chef knife for ten years", "My chef knife after a decade", "This chef knife will outlast me"])
def test_long_term_use_in_words_counts(title):
    knife = "first chef's knife under £100 for a home cook"
    posts = [candidate("1plain", "My chef knife", 100, "BuyItForLife"), candidate("1long", title, 100, "BuyItForLife")]
    assert ranked_ids(knife, posts)[0] == "1long"


def test_kitchen_usage_tips_lose_points_like_care_threads():
    posts = [candidate("1tips", "5 foods you should never cook in a cast iron skillet", 400, "castiron"),
             candidate("1plain", "Cast iron skillet", 400, "castiron")]
    assert ranked_ids(SKILLET, posts) == ["1plain", "1tips"]


def test_a_product_name_one_letter_off_still_counts():
    from engine.sources import mentions_product

    assert mentions_product("Asian Matte Suncreen for Oily Skin", "sunscreen")
    assert mentions_product("Best moisturiser for dry skin", "moisturiser")
    assert not mentions_product("Best sunglasses for summer", "sunscreen")


# --- Warnings must be about the product (7 Oct 2026, after the first warning top-up) ---

@pytest.mark.parametrize("title, product_type, category", [
    ("I got two whole ducks, broke them down, and turned them into duck fat", "frying pan", "kitchen"),  # cooking
    ("Broke student coffee routine (or dealing with a cheap grinder)", "coffee grinder", "kitchen"),  # money
    ("I sandblasted my cast iron skillet since it rusted", "cast iron skillet", "kitchen"),  # a care project
    ("Avoid the crowds: my kitchen tour", "electric kettle", "kitchen"),  # doesn't name the product
    # "Breaking in" a pan is its first use, not a failure (found through Bright Data's search, 11 Oct 2026).
    ("Broke in my new cast iron for Sunday dinner chicken pot pie", "cast iron skillet", "kitchen"),
    ("Broke in my new (and first) cast iron skillet with some chicken. Turned out great!", "cast iron skillet", "kitchen"),
    # Regretting NOT doing something, or having no regrets, isn't a warning (11 Oct 2026).
    ("Will I regret not using retinol?", "retinoid", "skincare"),
    ("No regrets: my cast iron skillet after 10 years", "cast iron skillet", "kitchen"),
])
def test_these_are_not_warnings(title, product_type, category):
    assert thread_kind({"title": title}, category, product_type) != "warning"


@pytest.mark.parametrize("title, product_type, category", [
    ("My kettle broke within a year", "electric kettle", "kitchen"),
    ("My kettle broke in 6 months", "electric kettle", "kitchen"),
    ("I regret buying this kettle", "electric kettle", "kitchen"),
    ("My cast iron skillet warped on the induction hob", "cast iron skillet", "kitchen"),
    ("Scratched non-stick frying pan after a month", "frying pan", "kitchen"),
    ("Grinder broke in a year, avoid", "coffee grinder", "kitchen"),
    ("Cast iron skillet broke in the first week", "cast iron skillet", "kitchen"),
    ("Less than 3 years old electric kettle flaking/chipped already?", "electric kettle", "kitchen"),
    ("Non-stick pan peeling after six months", "frying pan", "kitchen"),
    ("This moisturizer gave me a rash", "moisturiser", "skincare"),
])
def test_these_are_warnings(title, product_type, category):
    assert thread_kind({"title": title}, category, product_type) == "warning"



# --- Warning searches fit the product (11 Oct 2026) ---
# "kettle died" finds failures; "skillet died" found only "broke in my new skillet" (its first use). Cast iron fails by
# cracking or warping, non-stick pans by peeling or scratching, knives by chipping.

@pytest.mark.parametrize("request_text, words", [
    ("cast iron skillet for a beginner that will last decades", ("cracked", "warped")),
    ("non-stick frying pan without PFAS that actually lasts", ("peeling", "scratched")),
    ("first chef's knife under £100 for a home cook", ("chipped", "broke")),
    ("electric kettle that lasts 10+ years", ("died", "broke")),  # the category's own words
    ("gentle cleanser for acne-prone skin that won't strip my skin", ("irritation", "broke me out")),
])
def test_warning_searches_use_the_words_each_product_fails_with(request_text, words):
    from engine.sources import warning_words

    assert warning_words(parse_query(request_text))[:2] == words
