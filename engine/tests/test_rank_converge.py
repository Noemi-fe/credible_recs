"""Module 6, the converge round of 17 Oct 2026 (ws-ranking): features asked for rank first (item 1), Skip these needs two
threads and leaves out the opposite need's complaints (item 2), and the PROPOSED order by credible support (item 6).

Every mention here is made up (engine/tests/ranking_factories.py).
"""

from dataclasses import replace

from engine import config
from engine.rank import rank_products
from engine.tests import ranking_factories


def mention(product, thread="t1", *, features=(), opposite_need=False, **kwargs):
    """ranking_factories' mention, with the features its comment praises the product for and whether it is a warning
    from the opposite need (17 Oct 2026)."""
    return replace(ranking_factories.mention(product, thread, **kwargs), features=features, opposite_need=opposite_need)


def mentions(n, product, threads=("t1", "t2"), **kwargs):
    return [mention(product, threads[i % len(threads)], **kwargs) for i in range(n)]


def names(products):
    return [p.name for p in products]


# --- Item 1: a feature named before the product noun ranks first the products praised for it ---

def test_a_product_praised_for_the_feature_ranks_first_whatever_its_score():
    plain = mentions(6, "Acme Studio")  # more support, nobody praises its noise cancelling
    praised = mentions(3, "Brio Quiet") + [mention("Brio Quiet", "t2", features=("noise cancelling",))]
    ranking = rank_products(plain + praised, "kitchen", features=("noise cancelling",))
    assert names(ranking.picks) == ["Brio Quiet", "Acme Studio"]
    assert ranking.products[0].features_praised == ("noise cancelling",)
    assert ranking.products[1].features_praised == ()


def test_without_a_feature_asked_the_order_is_the_scores():
    plain = mentions(6, "Acme Studio")
    praised = mentions(3, "Brio Quiet") + [mention("Brio Quiet", "t2", features=("noise cancelling",))]
    assert names(rank_products(plain + praised, "kitchen").picks) == ["Acme Studio", "Brio Quiet"]


def test_only_a_credible_recommendation_praises_a_product_for_the_feature():
    plain = mentions(6, "Acme Studio")
    hearsay = mentions(3, "Brio Quiet") + [mention("Brio Quiet", "t2", evidence="no first-hand use",
                                                   features=("noise cancelling",))]
    warned = mentions(3, "Cole One") + [mention("Cole One", "t1", stance="warn", features=("noise cancelling",))]
    ranking = rank_products(plain + hearsay + warned, "kitchen", features=("noise cancelling",))
    assert names(ranking.picks)[0] == "Acme Studio"
    assert all(p.features_praised == () for p in ranking.products)


def test_more_features_praised_rank_before_fewer():
    one = mentions(5, "Acme") + [mention("Acme", "t1", features=("quiet",))]
    two = mentions(3, "Brio") + [mention("Brio", "t2", features=("quiet", "compact"))]
    none = mentions(9, "Cole")
    ranking = rank_products(one + two + none, "kitchen", features=("quiet", "compact"))
    assert names(ranking.picks) == ["Brio", "Acme", "Cole"]


def test_the_feature_never_makes_a_pick_of_a_product_short_of_the_bar():
    plain = mentions(4, "Acme")
    short = [mention("Brio", "t1", features=("quiet",)), mention("Brio", "t2", features=("quiet",))]
    ranking = rank_products(plain + short, "kitchen", features=("quiet",))
    assert names(ranking.picks) == ["Acme"]
    assert names(ranking.worth_a_look) == ["Brio"]


def test_a_must_have_left_unconfirmed_still_ranks_after_the_confirmed_whatever_the_feature():
    confirmed = mentions(4, "Acme")
    praised = mentions(4, "Brio", features=("quiet",))
    ranking = rank_products(confirmed + praised, "kitchen", features=("quiet",), unconfirmed={"brio": 1})
    assert names(ranking.picks) == ["Acme", "Brio"]


# --- Item 2: Skip these needs credible warnings from two threads, the opposite need's aside ---

def test_skip_these_needs_credible_warnings_from_two_threads():
    one_thread = mentions(3, "Acme", threads=("t1",), stance="warn")
    two_threads = mentions(2, "Brio", threads=("t1", "t2"), stance="warn")
    ranking = rank_products(one_thread + two_threads + mentions(3, "Cole"), "kitchen")
    assert names(ranking.skip_list) == ["Brio"]
    acme = next(p for p in ranking.products if p.name == "Acme")
    assert not acme.on_skip_list and acme.breakdown.credible_warnings == 3  # still counted, still never a pick
    assert not acme.qualifies


def test_a_warning_from_the_opposite_need_doesnt_count_toward_skip_these():
    # A dry-skin answer: two of three warnings are oily-skin complaints.
    warnings = [mention("Acme cream", "t1", stance="warn", opposite_need=True),
                mention("Acme cream", "t2", stance="warn", opposite_need=True),
                mention("Acme cream", "t3", stance="warn")]
    ranking = rank_products(warnings, "kitchen")
    assert ranking.skip_list == []
    assert ranking.products[0].skip_warnings == [warnings[2]]


def test_the_warnings_that_count_must_outnumber_the_recommendations():
    warnings = [mention("Acme", t, stance="warn") for t in ("t1", "t2")] + [
        mention("Acme", "t3", stance="warn", opposite_need=True)]
    praise = mentions(2, "Acme")
    assert rank_products(warnings + praise, "kitchen").skip_list == []
    assert names(rank_products(warnings + praise[:1], "kitchen").skip_list) == ["Acme"]


def test_skip_these_lists_the_most_counted_warnings_first():
    a = [mention("Acme", t, stance="warn") for t in ("t1", "t2")]
    b = [mention("Brio", t, stance="warn") for t in ("t1", "t2", "t3")] + [
        mention("Brio", "t4", stance="warn", opposite_need=True) for _ in range(3)]
    c = [mention("Cole", t, stance="warn") for t in ("t1", "t2", "t3", "t1")]
    ranking = rank_products(a + b + c, "kitchen")
    assert names(ranking.skip_list) == ["Cole", "Brio", "Acme"]


# --- Item 6 (PROPOSED, off): the order by credible support, every mention's points breaking ties ---

def test_by_default_the_score_orders_the_picks_hearsay_included(monkeypatch):
    monkeypatch.setattr(config, "RANK_BY_CREDIBLE_POINTS", False)
    few = mentions(3, "Acme", voice="medium", evidence="short-term use") + [
        mention("Acme", "t1", evidence="no first-hand use") for _ in range(9)]
    many = mentions(5, "Brio", voice="medium", evidence="short-term use")
    assert names(rank_products(few + many, "kitchen").picks) == ["Acme", "Brio"]


def test_with_the_proposed_order_credible_support_comes_first(monkeypatch):
    monkeypatch.setattr(config, "RANK_BY_CREDIBLE_POINTS", True)
    few = mentions(3, "Acme", voice="medium", evidence="short-term use") + [
        mention("Acme", "t1", evidence="no first-hand use") for _ in range(9)]
    many = mentions(5, "Brio", voice="medium", evidence="short-term use")
    ranking = rank_products(few + many, "kitchen")
    assert names(ranking.picks) == ["Brio", "Acme"]
    assert ranking.products[0].credible_points > ranking.products[1].credible_points


def test_a_product_warned_off_in_one_thread_is_still_never_a_pick():
    # Skip these lists only warnings from two threads, but more credible warnings than recommendations still keep a
    # product from the picks and Also worth a look (the skip rule of 9 Oct 2026), wherever they come from.
    praise = mentions(3, "Acme")
    warnings = [mention("Acme", "t1", stance="warn") for _ in range(4)]
    ranking = rank_products(praise + warnings + mentions(3, "Brio"), "kitchen")
    acme = next(p for p in ranking.products if p.name == "Acme")
    assert not acme.on_skip_list and not acme.qualifies and not acme.worth_a_look
    assert acme.shortfall.startswith("more credible warnings than recommendations")
    assert names(ranking.picks) == ["Brio"]
