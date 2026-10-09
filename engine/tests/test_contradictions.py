"""Writers who contradict themselves (Noemi's rule, 9 Oct 2026): the same writer recommends a product and warns
against it, in two comments of the request's threads, without saying anything changed.

All data is made up: product groups built by hand (module 4's shape) and comments from engine/tests/factories.py.
"""

from engine.contradictions import contradicting_writers, says_something_changed
from engine.group_products import ProductGroup, ProductMention
from engine.models import Comment
from engine.tests.factories import make_comment


def writer(name: str | None) -> dict | None:
    return {"name": name, "account_created_at": "2018-06-01", "karma": 5000} if name else None


def comments(*rows: tuple[str, str | None, str]) -> dict[str, Comment]:
    """{comment id: Comment} from (comment id, writer's name or None for a deleted account, body)."""
    return {cid: Comment.model_validate(make_comment(cid, author=writer(name), body=body)) for cid, name, body in rows}


def group(key: str, *mentions: tuple[str, str, str], name: str | None = None) -> ProductGroup:
    """One product group from (thread id, comment id, stance) rows; every mention names the product `key`."""
    return ProductGroup(key=key, name=name or key, category="kitchen",
                        mentions=[ProductMention(tid, cid, name or key, "kitchen", stance) for tid, cid, stance in mentions])


def test_a_writer_who_recommends_and_warns_against_one_product_contradicts_themselves():
    said = comments(("c1", "Kettle_Fan", "The Zojirushi is the best kettle I've owned."),
                    ("c2", "kettle_fan", "Avoid the Zojirushi, it's a terrible kettle."))
    groups = [group("kitchen:zojirushi", ("t1", "c1", "recommend"), ("t2", "c2", "warn"))]
    assert contradicting_writers(groups, said) == {"kettle_fan"}  # names are compared lowercased


def test_two_names_of_one_product_are_the_same_product():
    # Module 4 put "Zojirushi" and "Zojirushi kettle" in one group: praising one and warning against the other is a
    # contradiction.
    said = comments(("c1", "kettle_fan", "Zojirushi, no question."), ("c2", "kettle_fan", "The Zojirushi kettle is junk."))
    zoji = ProductGroup("kitchen:zojirushi", "Zojirushi", "kitchen", [
        ProductMention("t1", "c1", "Zojirushi", "kitchen", "recommend"),
        ProductMention("t2", "c2", "Zojirushi kettle", "kitchen", "warn"),
    ])
    assert contradicting_writers([zoji], said) == {"kettle_fan"}


def test_an_update_is_honest_not_a_contradiction():
    said = comments(("c1", "kettle_fan", "The Zojirushi is the best kettle I've owned."),
                    ("c2", "kettle_fan", "Update: my Zojirushi died after 2 years, so I can't recommend it now."))
    groups = [group("kitchen:zojirushi", ("t1", "c1", "recommend"), ("t2", "c2", "warn"))]
    assert contradicting_writers(groups, said) == set()


def test_recommending_different_products_for_different_needs_is_not_a_contradiction():
    said = comments(("c1", "kettle_fan", "For tea, get the Zojirushi."),
                    ("c2", "kettle_fan", "For pour-over, skip the Zojirushi and get a Fellow Stagg."),
                    ("c3", "kettle_fan", "The Fellow Stagg is lovely."))
    groups = [group("kitchen:zojirushi", ("t1", "c1", "recommend")),
              group("kitchen:fellow stagg", ("t1", "c2", "recommend"), ("t2", "c3", "recommend"))]
    assert contradicting_writers(groups, said) == set()


def test_deleted_accounts_never_match_each_other():
    # Two deleted accounts can't be told apart, so their opposite opinions are never one writer's.
    said = comments(("c1", None, "The Zojirushi is great."), ("c2", None, "The Zojirushi is awful."))
    groups = [group("kitchen:zojirushi", ("t1", "c1", "recommend"), ("t2", "c2", "warn"))]
    assert contradicting_writers(groups, said) == set()


def test_mixed_feelings_in_one_comment_are_not_a_contradiction():
    said = comments(("c1", "kettle_fan", "The Zojirushi boils fast, but the lid is flimsy."))
    groups = [group("kitchen:zojirushi", ("t1", "c1", "recommend"), ("t1", "c1", "warn"))]
    assert contradicting_writers(groups, said) == set()


def test_neutral_mentions_never_make_a_contradiction():
    said = comments(("c1", "kettle_fan", "The Zojirushi is great."), ("c2", "kettle_fan", "Is the Zojirushi loud?"))
    groups = [group("kitchen:zojirushi", ("t1", "c1", "recommend"), ("t2", "c2", "neutral"))]
    assert contradicting_writers(groups, said) == set()


def test_a_change_said_in_any_of_their_warnings_about_it_is_enough():
    # The writer explained what changed once; a later "yeah, avoid it" continues the same story.
    said = comments(("c1", "kettle_fan", "The Zojirushi is great."),
                    ("c2", "kettle_fan", "Mine stopped heating after 3 years."),
                    ("c3", "kettle_fan", "Yeah, avoid the Zojirushi."))
    groups = [group("kitchen:zojirushi", ("t1", "c1", "recommend"), ("t2", "c2", "warn"), ("t2", "c3", "warn"))]
    assert contradicting_writers(groups, said) == set()


def test_change_words_quoted_from_someone_else_dont_count():
    said = comments(("c1", "kettle_fan", "The Zojirushi is the best kettle I've owned."),
                    ("c2", "kettle_fan", "> Mine died after 2 years\n\nThe Zojirushi is a terrible kettle anyway."))
    groups = [group("kitchen:zojirushi", ("t1", "c1", "recommend"), ("t2", "c2", "warn"))]
    assert contradicting_writers(groups, said) == {"kettle_fan"}


def test_what_counts_as_saying_something_changed():
    for text in ("It died last week.", "Mine broke.", "It stopped heating.", "The element failed.",
                 "They reformulated it.", "The new formula breaks me out.", "Something changed.", "No longer recommend.",
                 "Doesn't work anymore.", "I used to love it.", "EDIT: avoid.", "Update - it's gone.",
                 "I developed a reaction to it.", "After 6 months the lid cracked.", "after a couple of years it leaked"):
        assert says_something_changed(text), text
    for text in ("Avoid it, it's terrible.", "Way too harsh for my skin.", "The lid is flimsy.", "Not worth the money."):
        assert not says_something_changed(text), text
