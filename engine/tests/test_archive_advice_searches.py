"""The archive's round also searches the product's title words with advice words (4 Nov 2026, from Noemi's report about
"blush").

Arctic Shift's title search answers the newest 100 posts of each search, and matches whole words without stemming. For
a type people post about every day ("blush" in r/Sephora), round 1's newest 100 of the last 3 years are the last few
weeks of small posts, and a request with no need words ("blush") had no need searches to reach further back: the big
threads asking for recommendations, a year or two old, stayed out of reach. So the round also searches the type's
first two title words with each advice word (ARCHIVE_ADVICE_WORDS: "blush favorite", "blushes favorite", "blush
recommendations"...), subreddit by subreddit, over the whole history (few posts match both, so such a search doesn't
time out), at most ARCHIVE_ADVICE_SEARCHES of them. A post such a search alone finds joins the candidates only when its
title reads as a question for advice: "favorite" is also how people show off a look. Ranking is unchanged. Parse's paid
path never runs them.

Every post and title here is made up.
"""

import re
from datetime import UTC, datetime

import pytest

from engine import query as module_1
from engine.arctic_shift import ArcticShiftError
from engine.config import ARCHIVE_ADVICE_SEARCHES, ARCHIVE_ADVICE_WORDS, ARCHIVE_NEED_WORDS, ARCHIVE_SEARCH_MAX_FAILURES
from engine.query import parse_query
from engine.sources import ArchiveSource, ParseSource, search_archive
from engine.tests.test_archive_reader import FakeArchiveClient
from engine.tests.test_sources import FakeParseClient

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


class TitleSearch(FakeArchiveClient):
    """Answers a title search as Arctic Shift does: the posts whose titles hold every word searched as a whole word (no
    stemming: "blush" isn't in "blushes"), within its dates, newest first, and only the newest `cap` of them."""

    def __init__(self, posts=(), cap=1):
        super().__init__(posts)
        self.cap = cap

    def search_posts(self, subreddit, title, limit=25, before=None, after=None):
        self.searches.append((subreddit, title))
        self.asked.append({"limit": limit, "before": before, "after": after})
        words = set(title.lower().split())
        found = [dict(p) for p in self.posts
                 if p["subreddit"] == subreddit and words <= set(re.findall(r"[a-z0-9]+", p["title"].lower()))
                 and (after is None or day(p) >= after) and (before is None or day(p) < before)]
        return sorted(found, key=lambda p: p["created_utc"], reverse=True)[:self.cap]


def day(post: dict) -> str:
    return datetime.fromtimestamp(post["created_utc"], UTC).date().isoformat()


def post_on(post_id: str, title: str, comments: int, posted: str, subreddit: str = "Sephora", flair=None) -> dict:
    return {"id": post_id, "title": title, "num_comments": comments, "score": 20, "subreddit": subreddit,
            "created_utc": datetime.fromisoformat(posted).replace(tzinfo=UTC).timestamp(),
            "permalink": f"/r/{subreddit}/comments/{post_id}/post/", "link_flair_text": flair}


def blush_posts() -> list[dict]:
    # The newest "blush" and "blushes" titles of each window are small posts; the big questions are a year or two old.
    return [
        post_on("1new01", "Blush swatches from my haul", 12, "2026-09-01"),
        post_on("1new02", "Blushes I finished this year", 20, "2026-08-01"),
        post_on("1mid01", "Blush that survived a long shift", 9, "2022-05-01"),
        post_on("1mid02", "Blushes from the drugstore", 6, "2022-04-01"),
        # Changed on purpose, 4 Nov 2026 (the round-1 review): these two had been near copies of two real r/Sephora
        # titles, with their real comment counts and dates; invented ones test the same (a question with "blush" and
        # "favorite" as whole words, not starting as a question does; one with only the plural "blushes").
        post_on("1old01", "Blush you'd call your all-time favorite?", 205, "2024-11-03"),
        post_on("1top01", "Three favorite blushes you would rebuy forever?", 137, "2025-06-14"),
    ]


def ids(posts) -> set[str]:
    return {p["id"] for p in posts}


def advice_terms(client) -> list[str]:
    return [t for _, t in client.searches if t.split()[-1] in ARCHIVE_ADVICE_WORDS]


def test_the_decided_values():
    # "recommendations" before "best", so a type with a plural reaches all three words' kinds of question within the
    # cap (a request for blush searched 4 communities: 8 "favorite" searches, then 4 "recommendations").
    assert ARCHIVE_ADVICE_WORDS == ("favorite", "recommendations", "best") and ARCHIVE_ADVICE_SEARCHES == 12


def test_without_advice_searches_the_big_old_question_was_out_of_reach():
    found = search_archive(TitleSearch(blush_posts()), parse_query("blush"), 16, 0, posts_each=100, older_than_years=3,
                           max_failures=3, now=NOW)
    assert not ids(found) & {"1old01", "1top01"}


def test_with_advice_searches_it_is_a_candidate_and_ranks_first():
    client = TitleSearch(blush_posts())
    found = search_archive(client, parse_query("blush"), 16, 0, posts_each=100, older_than_years=3, max_failures=3,
                           now=NOW, advice_searches=ARCHIVE_ADVICE_SEARCHES)
    assert {"1old01", "1top01"} <= ids(found)
    ranked = ArchiveSource(TitleSearch(blush_posts())).rank_candidates(parse_query("blush"))
    assert [p["id"] for p in ranked][:2] == ["1old01", "1top01"]


def test_a_title_with_the_plural_only_is_found_through_the_plural(monkeypatch):
    found = search_archive(TitleSearch(blush_posts()), parse_query("blush"), 16, 0, posts_each=100, older_than_years=3,
                           max_failures=3, now=NOW, advice_searches=ARCHIVE_ADVICE_SEARCHES)
    assert "1top01" in ids(found)
    monkeypatch.setitem(module_1.TITLE_WORDS, "blush", ("blush",))  # no plural among the title words
    found = search_archive(TitleSearch(blush_posts()), parse_query("blush"), 16, 0, posts_each=100, older_than_years=3,
                           max_failures=3, now=NOW, advice_searches=ARCHIVE_ADVICE_SEARCHES)
    assert "1top01" not in ids(found) and "1old01" in ids(found)


def test_advice_searches_pair_the_first_two_title_words_with_each_advice_word_over_the_whole_history():
    client = TitleSearch(blush_posts())
    query = parse_query("blush")
    search_archive(client, query, 16, 0, posts_each=100, older_than_years=3, max_failures=3, now=NOW,
                   advice_searches=ARCHIVE_ADVICE_SEARCHES)
    asked = [(s, t, a) for (s, t), a in zip(client.searches, client.asked) if t.split()[-1] in ARCHIVE_ADVICE_WORDS]
    assert len(asked) == ARCHIVE_ADVICE_SEARCHES  # 2 words x 3 advice words x 4 communities, capped
    assert all(a["after"] is None and a["before"] is None for _, _, a in asked)
    pairs = {(s, t) for s, t, _ in asked}
    for subreddit in query.subreddits:
        assert {(subreddit, "blush favorite"), (subreddit, "blushes favorite"),
                (subreddit, "blush recommendations")} <= pairs


def test_the_advice_searches_are_bounded_for_any_type():
    for request in ("blush", "lipstick", "foundation for oily skin", "conditioner for curly hair", KETTLE):
        client = TitleSearch(blush_posts())
        search_archive(client, parse_query(request), 16, 4, posts_each=100, older_than_years=3, max_failures=3,
                       now=NOW, need_searches=ARCHIVE_NEED_WORDS, advice_searches=ARCHIVE_ADVICE_SEARCHES)
        assert 0 < len(advice_terms(client)) <= ARCHIVE_ADVICE_SEARCHES, request


KETTLE = "electric kettle that lasts 10+ years"


def test_a_request_with_needs_still_runs_its_need_searches_first_then_advice_then_warnings():
    client = TitleSearch(blush_posts())
    search_archive(client, parse_query("cream blush that lasts"), 16, 4, posts_each=100, older_than_years=3,
                   max_failures=3, now=NOW, need_searches=ARCHIVE_NEED_WORDS, advice_searches=ARCHIVE_ADVICE_SEARCHES)
    terms = [t for _, t in client.searches]
    assert "blush cream" in terms and "blush last" in terms and "blush favorite" in terms
    last_need = max(i for i, t in enumerate(terms) if t in ("blush cream", "blush last"))
    first_advice = min(i for i, t in enumerate(terms) if t.split()[-1] in ARCHIVE_ADVICE_WORDS)
    last_advice = max(i for i, t in enumerate(terms) if t.split()[-1] in ARCHIVE_ADVICE_WORDS)
    first_warning = min(i for i, t in enumerate(terms) if t in ("blush regret", "blush avoid", "blush broke me out",
                                                                  "blush irritation", "blush died"))
    assert last_need < first_advice and last_advice < first_warning


def test_without_advice_searches_asked_for_the_round_is_as_before():
    client = TitleSearch(blush_posts())
    search_archive(client, parse_query("blush"), 16, 0, posts_each=100, older_than_years=3, max_failures=3, now=NOW)
    assert advice_terms(client) == []


def test_the_archive_reader_runs_them():
    client = TitleSearch(blush_posts())
    ArchiveSource(client).rank_candidates(parse_query("blush"))
    assert len(advice_terms(client)) == ARCHIVE_ADVICE_SEARCHES


def test_parse_never_runs_them_neither_its_finder_nor_its_paid_search():
    finder, paid = TitleSearch(blush_posts()), FakeParseClient()
    ParseSource(client=paid, finder=finder, max_free_searches=16).find_threads(parse_query("blush"))
    assert advice_terms(finder) == [] and advice_terms(paid) == []
    paid = FakeParseClient()
    ParseSource(client=paid).find_threads(parse_query("blush"))
    assert paid.searches and advice_terms(paid) == []


# --- A post only an advice search found must read as a question for advice ---

def lipstick_posts() -> list[dict]:
    return [
        post_on("1lip01", "Lipstick swatches in daylight", 30, "2026-10-20", "Makeup"),
        post_on("1look01", "Wearing my favorite red lipstick today", 40, "2026-10-01", "Makeup"),
        post_on("1lip02", "Any favorite lipstick for dry lips", 60, "2025-03-01", "Sephora"),
        post_on("1lip03", "My favorite lipstick dilemma", 45, "2024-06-01", "MakeupAddiction", flair="Product Question"),
        post_on("1lip04", "Lipstick haul", 10, "2026-10-21", "Sephora"),
        post_on("1lip05", "Lipstick haul part two", 10, "2026-10-21", "MakeupAddiction"),
    ]


def test_a_post_an_advice_search_alone_found_joins_only_when_it_asks_for_advice():
    found = ids(search_archive(TitleSearch(lipstick_posts()), parse_query("lipstick"), 16, 0, posts_each=100,
                               older_than_years=3, max_failures=3, now=NOW, advice_searches=ARCHIVE_ADVICE_SEARCHES))
    assert "1look01" not in found  # a look shown, not a question
    assert "1lip02" in found  # starts as a question does
    assert "1lip03" in found  # its flair asks


def test_a_question_mark_is_enough():
    found = ids(search_archive(TitleSearch(blush_posts()), parse_query("blush"), 16, 0, posts_each=100,
                               older_than_years=3, max_failures=3, now=NOW, advice_searches=ARCHIVE_ADVICE_SEARCHES))
    assert "1old01" in found


def test_a_post_a_title_search_found_too_is_kept_whatever_its_title():
    posts = [post_on("1look01", "Wearing my favorite red lipstick today", 40, "2026-10-01", "Makeup")]
    found = ids(search_archive(TitleSearch(posts), parse_query("lipstick"), 16, 0, posts_each=100, older_than_years=3,
                               max_failures=3, now=NOW, advice_searches=ARCHIVE_ADVICE_SEARCHES))
    assert found == {"1look01"}  # the round's newest "lipstick" post: found as before


# --- A busy archive still gets the narrow searches (4 Nov 2026, the branch's dry run) ---
# On the day, Arctic Shift timed out on the broad "blush" searches of the last 3 years in the busy communities: three
# failures in a row ended the round in its first part, and the advice searches, queued after it, were never asked,
# though narrow searches like them answered in seconds. So when failures end a round in which some searches did answer
# (busy, not down), the need and advice searches still queued are asked anyway, once each, until as many of them fail in
# a row. A round in which nothing answered (the archive down) ends as before, with no more calls.

TIMEOUT = "Arctic Shift answered 422 to a search in r/{}: 'Timeout. Maybe slow down a bit'"


class BusyArchive(TitleSearch):
    """Answers its first `answers` searches, then times out on every search bounded by dates (the broad ones) and, with
    `narrow_fail`, on the undated ones too."""

    def __init__(self, posts=(), answers=1, narrow_fail=False):
        super().__init__(posts)
        self.answers, self.narrow_fail = answers, narrow_fail

    def search_posts(self, subreddit, title, limit=25, before=None, after=None):
        if len(self.searches) >= self.answers and (after is not None or before is not None or self.narrow_fail):
            self.searches.append((subreddit, title))
            self.asked.append({"limit": limit, "before": before, "after": after})
            raise ArcticShiftError(TIMEOUT.format(subreddit))
        return super().search_posts(subreddit, title, limit, before, after)


def test_a_round_ended_by_a_busy_archive_still_asks_its_advice_searches():
    client, failed = BusyArchive(blush_posts()), []
    found = search_archive(client, parse_query("blush"), 16, 4, posts_each=100, older_than_years=3, max_failures=3,
                           now=NOW, failed=failed, raise_if_nothing=True, advice_searches=ARCHIVE_ADVICE_SEARCHES)
    assert {"1old01", "1top01"} <= ids(found) and failed  # found, and the round still says it was cut short
    assert len(advice_terms(client)) == ARCHIVE_ADVICE_SEARCHES
    assert not [t for _, t in client.searches if t.endswith(("regret", "avoid", "died", "broke"))]  # not the warnings


def test_the_need_searches_too():
    client = BusyArchive(blush_posts())
    search_archive(client, parse_query("cream blush that lasts"), 16, 4, posts_each=100, older_than_years=3,
                   max_failures=3, now=NOW, failed=[], need_searches=ARCHIVE_NEED_WORDS,
                   advice_searches=ARCHIVE_ADVICE_SEARCHES)
    terms = [t for _, t in client.searches]
    assert "blush cream" in terms and "blush last" in terms


def test_when_the_narrow_searches_fail_too_they_stop_after_as_many_in_a_row():
    client = BusyArchive(blush_posts(), narrow_fail=True)
    search_archive(client, parse_query("blush"), 16, 4, posts_each=100, older_than_years=3, max_failures=3, now=NOW,
                   failed=[], advice_searches=ARCHIVE_ADVICE_SEARCHES)
    assert len(advice_terms(client)) == 3


def test_an_archive_that_answered_nothing_isnt_asked_again():
    client = BusyArchive(blush_posts(), answers=0, narrow_fail=True)
    with pytest.raises(ArcticShiftError):
        ArchiveSource(client).rank_candidates(parse_query("blush"))
    assert len(client.searches) == ARCHIVE_SEARCH_MAX_FAILURES  # as before: a service that is down ends the round


# --- On demand: inside the old budget (4 Nov 2026, Noemi's "Keep 25 min") ---
# Round 1 added up to 12 advice searches on top of the round's title, need and warning searches: a "blush" request asked
# about 32 searches where main asked 16, and the wait visitors are told would have gone from about 25 minutes to about
# 45. Noemi kept the 25 minutes. So on-demand reading's round has a budget, config.ON_DEMAND_SEARCH_CALLS (main's own
# "blush" round: 12 title searches and 4 warning searches), and every call counts against it, halves of a search that
# timed out and the busy archive's second chances included; a search the 48-hour cache holds costs nothing. Inside it,
# one title search goes first, to see whether the type's word is common: when it answers its full 100, the newest posts
# are only the last weeks, so the need and advice searches (whole history) come next, then the warning searches, and the
# other title searches only fill what is left; when it answers fewer, the title searches find every post (the advice
# searches could only find some of the same), so the round keeps main's order: titles, needs and warnings, the title
# searches cut so main's need and warning searches fit, and the advice searches only in what is left (5 Nov 2026, below).
# `library add` has no budget.

def saturated_blush_posts() -> list[dict]:
    """More recent small "blush" posts in each makeup community than a search answers (its newest 100), and the big
    advice threads a year or two old; every title made up."""
    communities = ("Makeup", "Sephora", "MakeupAddiction", "drugstoreMUA")
    posts = [post_on(f"1sw{i}{n:03d}", f"Blush swatch number {n}", 8, f"2026-{7 + n % 4:02d}-{1 + n % 27:02d}",
                     community)
             for i, community in enumerate(communities) for n in range(110)]
    return posts + [
        post_on("1old01", "Blush you'd call your all-time favorite?", 205, "2024-11-03", "Sephora"),
        post_on("1top01", "Three favorite blushes you would rebuy forever?", 137, "2025-06-14", "Sephora"),
        post_on("1rec01", "Blush recommendations for a first-timer?", 180, "2024-03-09", "Makeup"),
    ]


def budgeted(client, request: str = "blush", calls: int | None = None, **kwargs) -> list[dict]:
    from engine.config import ON_DEMAND_SEARCH_CALLS

    return search_archive(client, parse_query(request), 16, 4, posts_each=100, older_than_years=3, max_failures=3,
                          now=NOW, need_searches=ARCHIVE_NEED_WORDS, advice_searches=ARCHIVE_ADVICE_SEARCHES,
                          max_calls=ON_DEMAND_SEARCH_CALLS if calls is None else calls, **kwargs)


def kind(term: str) -> str:
    last = term.split()[-1]
    if last in ARCHIVE_ADVICE_WORDS:
        return "advice"
    if last in ("died", "broke", "regret", "avoid"):
        return "warning"
    return "title" if term in ("blush", "blushes") else "need"


def test_the_on_demand_budget_is_mains_blush_round():
    from engine import config

    # Main's "blush" round on 4 Nov 2026: 2 title words in 3 communities, both date windows (12), and 4 warnings.
    assert config.ON_DEMAND_SEARCH_CALLS == 16
    assert (config.ON_DEMAND_ARCHIVE_MINUTES, config.ON_DEMAND_CALLS_PER_PRODUCT) == (6, 15)  # as on main


def test_a_blush_like_round_asks_the_advice_searches_before_the_title_searches_and_stays_inside_the_budget():
    client = TitleSearch(saturated_blush_posts(), cap=100)
    found = budgeted(client)
    kinds = [kind(t) for _, t in client.searches]
    assert len(client.searches) == 16  # the whole budget, not one call more
    assert client.searches[0] == ("Makeup", "blush") and client.asked[0]["after"] is not None  # the one title search
    assert kinds[1:] == ["advice"] * 11 + ["warning"] * 4  # then the advice searches, the warnings kept
    assert {"1old01", "1top01", "1rec01"} <= ids(found)  # the big old advice threads are reached
    ranked = ArchiveSource(TitleSearch(saturated_blush_posts(), cap=100), max_calls=16).rank_candidates(
        parse_query("blush"))
    assert {p["id"] for p in ranked[:3]} == {"1old01", "1top01", "1rec01"}


def test_with_need_words_the_need_searches_come_first_then_the_advice_ones():
    client = TitleSearch(saturated_blush_posts(), cap=100)
    budgeted(client, "blush for fair skin")
    kinds = [kind(t) for _, t in client.searches]
    assert len(kinds) == 16 and kinds[0] == "title"
    first_advice = kinds.index("advice")
    assert set(kinds[1:first_advice]) == {"need"} and kinds[-4:] == ["warning"] * 4
    assert "title" not in kinds[1:]


def test_a_word_the_title_searches_cover_whole_keeps_mains_order():
    # Few posts: the first title search answers fewer than 100, so title searches find every post with the word and
    # come first, as on main; the budget still holds.
    # Changed on purpose, 5 Nov 2026 (the rules review of round 2): this test expected 16 title searches and no warning
    # search, which was the flaw: main asks its 4 warning searches for every type, so the title searches are now cut to
    # leave them room (12 title searches and 4 warnings, main's own "blush" round), as the tests below check for words
    # that aren't makeup.
    posts = [dict(p, subreddit="Makeup") for p in blush_posts()]
    client = TitleSearch(posts, cap=100)
    found = budgeted(client)
    assert [kind(t) for _, t in client.searches] == ["title"] * 12 + ["warning"] * 4  # the budget, warnings kept
    # The big ones are found through the title searches; the 4 cut are the plural's over the older years (an old small
    # post holding only "blushes" is the price of the warnings).
    assert {"1old01", "1top01"} <= ids(found) and ids(found) == ids(posts) - {"1mid02"}


# --- A rare word (5 Nov 2026, the rules review of round 2) ---
# For a word few posts hold, the first title search answers fewer than 100 posts. The round had then asked the title,
# need and advice searches before the warning ones until the budget ran out, so most types lost main's 4 warning
# searches (in a replay over every type's name, warning searches fell from 1,776 to 486) and many lost their need
# searches. Now the need and warning searches main asks keep their place, the title searches are cut to leave them
# room, and the advice searches only fill what is left. Every post here is made up.

class FiveEach(FakeArchiveClient):
    """Answers every search with 5 made-up posts of its own: far fewer than 100, so any word reads as a rare one."""

    def search_posts(self, subreddit, title, limit=25, before=None, after=None):
        self.searches.append((subreddit, title))
        self.asked.append({"limit": limit, "before": before, "after": after})
        n = len(self.searches)
        return [post_on(f"1rr{n:03d}{i}", f"Made-up {title} question {i}?", 12, "2025-05-01", subreddit)
                for i in range(5)]


def kinds_of(request: str, client) -> list[str]:
    from engine.sources import finder_terms, warning_words

    query = parse_query(request)
    terms = finder_terms(query.product_type)
    warnings = {f"{terms[0]} {word}" for word in warning_words(query)}

    def one(term: str) -> str:
        if term in terms:
            return "title"
        if term in warnings:
            return "warning"
        if term.split()[-1] in ARCHIVE_ADVICE_WORDS and " ".join(term.split()[:-1]) in terms[:2]:
            return "advice"
        return "need"
    return [one(t) for _, t in client.searches]


def mains_round(request: str) -> list[tuple[str, str]]:
    """The searches main asks for a request (no budget, no advice searches): its title, need and warning searches."""
    client = FiveEach()
    search_archive(client, parse_query(request), 16, 4, posts_each=100, older_than_years=3, max_failures=3, now=NOW,
                   need_searches=ARCHIVE_NEED_WORDS)
    return client.searches


@pytest.mark.parametrize("request_text", ["teapot", "conditioner for curly hair", "robot vacuum for pet hair",
                                          "chef knife for beginners"])
def test_a_rare_word_keeps_mains_need_and_warning_searches(request_text):
    main, client = mains_round(request_text), FiveEach()
    budgeted(client, request_text)
    kinds, main_kinds = kinds_of(request_text, client), kinds_of(request_text, FakeSearches(main))
    assert len(client.searches) <= 16
    for wanted in ("need", "warning"):
        asked = [s for s, k in zip(client.searches, kinds) if k == wanted]
        assert asked == [s for s, k in zip(main, main_kinds) if k == wanted]  # every one main asks, in its order
    assert main_kinds.count("warning") == 4


def test_a_rare_word_like_teapot_asks_mains_round_then_advice_only_fills_what_is_left():
    client = FiveEach()
    budgeted(client, "teapot")
    kinds = kinds_of("teapot", client)
    # Main's teapot round is 8 title searches and 4 warnings: all of it, then 4 advice searches, the rest of the budget.
    assert kinds == ["title"] * 8 + ["warning"] * 4 + ["advice"] * 4
    assert client.searches[:12] == mains_round("teapot")


def test_with_more_need_searches_than_room_the_warnings_still_keep_their_place():
    client = FiveEach()
    budgeted(client, "conditioner for curly hair")
    kinds = kinds_of("conditioner for curly hair", client)
    assert kinds[0] == "title" and kinds.count("warning") == 4 and kinds.count("need") == 7
    assert len(kinds) == 16 and "advice" not in kinds  # main's 25 searches don't fit: the title searches give way
    client = FiveEach()
    budgeted(client, "conditioner for curly hair", calls=8)
    kinds = kinds_of("conditioner for curly hair", client)
    assert kinds == ["title"] + ["need"] * 3 + ["warning"] * 4  # a tight budget: the warnings first, then the needs


class FakeSearches:
    """Holds a list of searches, for kinds_of."""

    def __init__(self, searches):
        self.searches = list(searches)


def test_every_call_counts_halves_and_second_chances_included():
    # The title searches time out (each halved before it fails), three in a row end the round, and the busy archive's
    # second chances (the advice searches, once each) stop when the budget does.
    posts = [dict(p, subreddit="Makeup") for p in blush_posts()]
    client, failed = BusyArchive(posts, answers=1), []
    budgeted(client, calls=10, failed=failed)
    assert len(client.searches) == 10 and failed


def test_a_busy_archive_cannot_take_the_round_past_its_budget():
    client = BusyArchive(saturated_blush_posts(), answers=1, narrow_fail=True)
    budgeted(client, failed=[])
    assert len(client.searches) <= 16


class CachedSearches(TitleSearch):
    """A client whose 48-hour cache already holds some searches (a request tried again after a round cut short)."""

    def __init__(self, posts, held):
        super().__init__(posts, cap=100)
        self.held = set(held)

    def cached_posts(self, subreddit, title, limit=25, before=None, after=None):
        if (subreddit, title) not in self.held:
            return None
        words = set(title.lower().split())
        found = [dict(p) for p in self.posts if p["subreddit"] == subreddit
                 and words <= set(re.findall(r"[a-z0-9]+", p["title"].lower()))
                 and (after is None or day(p) >= after) and (before is None or day(p) < before)]
        return sorted(found, key=lambda p: p["created_utc"], reverse=True)[:self.cap]


def test_a_search_the_cache_holds_costs_no_call():
    held = {(community, f"{word} {advice}") for community in ("Makeup", "Sephora", "MakeupAddiction", "drugstoreMUA")
            for word in ("blush", "blushes") for advice in ("favorite",)}
    client = CachedSearches(saturated_blush_posts(), held)
    found = budgeted(client)
    assert len(client.searches) == 16 and not set(client.searches) & held  # 16 calls, none of them the cached 8
    assert {"1old01", "1top01", "1rec01"} <= ids(found)


def test_library_add_has_no_budget():
    client = TitleSearch(saturated_blush_posts(), cap=100)
    ArchiveSource(client).rank_candidates(parse_query("blush"))
    assert len(client.searches) > 16 and len(advice_terms(client)) == ARCHIVE_ADVICE_SEARCHES
