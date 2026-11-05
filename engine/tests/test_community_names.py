"""Names that name a product type only in its own communities (5 Nov 2026, the makeup review of round 2).

In r/Makeup or r/drugstoreMUA a post titled "best primer?" asks for a makeup primer, but the type's names were all
longer ("makeup primer", "face primer"...), so 5 of the library's 6 face-primer threads weren't read for "makeup primer
for large pores", while an eyeshadow-primer thread was, through the name "eyeshadow primer". Elsewhere a primer is
paint's, or a beginner's guide. And "kohl", an eyeliner in the makeup communities, is mostly the shop Kohl's elsewhere:
two r/BuyItForLife threads (about sweatpants and bed sheets) were counted as eyeliner threads, through the product types
their posts' words had named before those words were dropped (slimming).

So a type may list community names (engine/data/product_types.json, "community_names"): in a thread's title they name
the type only when the thread is in one of the type's own communities, as written (a whole word, not "Kohl's" or
"Kohls") and not inside a longer name of something else ("eyeshadow primer", "lash primer"); in a post they never name
it, nor in what a slimmed post's words named (its stored post words must hold another of the type's names). Requests
(module 1) and comments read them as before; the shop's possessive ("Kohl's") is a look-alike of eyeliner's, so it names
no eyeliner anywhere. Every title and post here is made up.
"""

from datetime import UTC, datetime

import pytest

from engine.config import MORE_PRODUCT_TYPES
from engine.models import Thread
from engine.query import PRODUCT_TYPES, parse_query
from engine.sources import mentions_product, names_product, post_score, relevance
from engine.tests.factories import make_comment, make_thread


def thread(title: str, community: str, body: str = "", **overrides) -> Thread:
    return Thread.model_validate(make_thread(
        id="1fake09", community=community, category="general", title=title, body=body,
        url=f"https://www.reddit.com/r/{community}/comments/1fake09/post/",
        comments=[make_comment("c9aaaa", thread_id="1fake09", body="Mine has lasted for years.")], **overrides))


def slimmed(title: str, community: str, post_names: list[str], post_words: list[str]) -> Thread:
    return thread(title, community, author=None, whole_thread={
        "slimmed_at": "2026-10-14T21:00:00Z", "extraction": "extract-v15 2026-10-14",
        "post_names": post_names, "post_words": post_words})


def entry(name: str) -> dict:
    return next(e for e in MORE_PRODUCT_TYPES if e["name"] == name)


def test_the_two_types_and_their_community_names():
    assert entry("makeup primer")["community_names"] == ["primer", "primers"]
    assert entry("eyeliner")["community_names"] == ["kohl"]
    by_name = {p.name: p for p in PRODUCT_TYPES}
    assert by_name["makeup primer"].community_names == ("primer", "primers")
    for e in MORE_PRODUCT_TYPES:
        for name in e.get("community_names", []):
            assert name == name.lower() and name.strip() == name, (e["name"], name)


@pytest.mark.parametrize("community", ["Makeup", "Sephora", "MakeupAddiction", "drugstoreMUA"])
def test_a_title_saying_primer_names_a_makeup_primer_in_the_makeup_communities(community):
    for title in ("Which primer keeps an oily T-zone matte till lunch?", "Primers that blur pores and last all day?",
                  "Do you even need a primer?"):
        t = thread(title, community)
        assert names_product(t, "makeup primer") and relevance(t, "makeup primer") >= 3, title


def test_but_not_elsewhere():
    for community in ("BuyItForLife", "HomeImprovement", "SkincareAddiction"):
        t = thread("Best primer before painting a bathroom?", community)
        assert not names_product(t, "makeup primer") and relevance(t, "makeup primer") < 1


def test_an_eyeshadow_primer_or_a_lash_primer_is_no_makeup_primer():
    for title in ("Favourite eyeshadow primer for oily lids?", "Eyeshadow primers that stop creasing?",
                  "Is an eye primer worth it?", "Lash primer: does it do anything?"):
        assert not names_product(thread(title, "Makeup"), "makeup primer"), title
    # Nor is "eyeshadow primer" one of its names any more: what the AI typed so is another product.
    assert "eyeshadow primer" not in entry("makeup primer")["keywords"]
    assert not mentions_product("eyeshadow primer", "makeup primer")
    assert mentions_product("face primer", "makeup primer") and mentions_product("pore primer", "makeup primer")


def test_a_title_naming_both_still_names_the_makeup_primer():
    assert names_product(thread("Eyeshadow primer or a face primer first?", "Makeup"), "makeup primer")
    assert names_product(thread("Primer under foundation, eyeshadow primer on lids?", "Makeup"), "makeup primer")


def test_a_post_saying_primer_in_passing_doesnt_make_a_thread_about_it():
    # Community names count in titles only: a foundation thread whose post lists a primer isn't a primer thread.
    t = thread("Foundation that lasts through a long shift?", "Makeup", body="I use a primer, then powder.")
    assert not names_product(t, "makeup primer") and names_product(t, "foundation")


def test_a_primer_title_in_a_makeup_community_is_graded_as_naming_it():
    query = parse_query("makeup primer for large pores")
    post = {"title": "Best primer you have tried?", "num_comments": 80, "created_utc": datetime(2025, 5, 1, tzinfo=UTC).timestamp()}
    inside = post_score(query, dict(post, subreddit="Sephora"))
    outside = post_score(query, dict(post, subreddit="BuyItForLife"))
    assert inside - outside == 2.0 + 2.0  # names it (2) and asks advice about it (3, not 1)


def test_a_request_is_read_as_before():
    # Module 1 doesn't read community names: "primer" alone is no makeup primer request, "kohl" is still an eyeliner.
    assert parse_query("primer").product_type != "makeup primer"
    assert parse_query("paint primer").product_type != "makeup primer"
    assert parse_query("kohl").product_type == "eyeliner"
    assert parse_query("makeup primer for large pores").product_type == "makeup primer"


# --- kohl ---

def test_kohl_names_an_eyeliner_in_a_makeup_communitys_title():
    assert names_product(thread("Kohl for the waterline that doesn't smudge?", "Makeup"), "eyeliner")
    assert names_product(thread("Kohl or gel eyeliner?", "BuyItForLife"), "eyeliner")  # through "eyeliner"


def test_the_shop_never_does():
    for title in ("Sephora at Kohl's haul", "Sephora at Kohl’s: worth the trip?", "Kohls sale finds"):
        assert not names_product(thread(title, "Sephora"), "eyeliner"), title
    for title in ("Sweatpants from Kohl's that lasted?", "Kohl sheets after ten years"):
        assert not names_product(thread(title, "BuyItForLife"), "eyeliner"), title


def test_nor_a_post_naming_the_shop():
    t = thread("Sweatpants that last?", "BuyItForLife", body="The ones from Kohl's lasted a year.")
    assert not names_product(t, "eyeliner") and relevance(t, "eyeliner") < 1


def test_a_slimmed_post_that_named_eyeliner_only_through_kohl_no_longer_does():
    # Its words are gone; what they named was worked out with "kohl" as a name: the shop, outside makeup.
    t = slimmed("Sweatpants that last?", "BuyItForLife", ["hoodie", "eyeliner"], ["kohl", "sweatpant", "hoodie"])
    assert not names_product(t, "eyeliner") and names_product(t, "hoodie")
    t = slimmed("Sweatpants that last?", "BuyItForLife", ["eyeliner"], ["kohl", "eyeliner"])
    assert names_product(t, "eyeliner")  # its post said "eyeliner" too
    t = slimmed("Any tips for a first concert?", "Makeup", ["eyeliner"], ["liquid", "eyeliner"])
    assert names_product(t, "eyeliner")


def test_comments_read_kohl_as_before():
    # A comment saying "kohl" still names an eyeliner, wherever it is.
    assert mentions_product("A soft kohl is all I wear now.", "eyeliner")


def test_but_the_shops_possessive_names_no_eyeliner_anywhere():
    # "Kohl's" and "Kohl’s" are look-alikes of eyeliner's (engine/data/product_types.json): in a comment, a post, a
    # title or a request, the shop is no eyeliner. ("Kohls" without its apostrophe still reads as kohls in a comment.)
    for text in ("Got mine at Kohl's on sale.", "Kohl’s had them cheaper.", "kohl's"):
        assert not mentions_product(text, "eyeliner"), text
    assert mentions_product("Kohl's had a kohl liner I love.", "eyeliner")
    assert parse_query("sweatpants from kohl's that last").product_type != "eyeliner"
    assert parse_query("kohl eyeliner for the waterline").product_type == "eyeliner"


# --- The archive's mix of thread kinds (engine.sources.thread_kind) ---

def test_a_warning_titled_primer_in_a_makeup_community_is_a_makeup_primer_warning():
    from engine.sources import thread_kind
    post = {"title": "Primer regret: it pilled under everything"}
    assert thread_kind(dict(post, subreddit="Makeup"), "general", "makeup primer") == "warning"
    assert thread_kind(dict(post, subreddit="HomeImprovement"), "general", "makeup primer") != "warning"
    assert thread_kind(post, "general", "makeup primer") != "warning"  # no community given: the type's names only
    shop = {"title": "Kohl's sweatpants died after a month", "subreddit": "BuyItForLife"}
    assert thread_kind(shop, "general", "eyeliner") != "warning"
