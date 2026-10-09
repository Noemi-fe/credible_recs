"""Module 6, ranking: from scored mentions to ranked products, with the minimum-evidence rule and flags.

All data is made up (engine/tests/ranking_factories.py). Weights follow its simple scale: high voice and
long-term use make 1.0, medium voice and short-term use 0.36, and so on; warnings are negative.
"""

import pytest

from engine import config
from engine.rank import KindNote, ScoredMention, is_credible, rank_products
from engine.tests.ranking_factories import mention, mentions, note


def names(products) -> list[str]:
    return [product.name for product in products]


def product(result, name: str):
    return next(p for p in result.products if p.name == name)


# --- The score and the known winner ---

def test_synthetic_threads_with_a_known_winner_rank_it_first():
    data = (
        mentions(4, "Tojiro DP Gyuto", threads=("t1", "t2", "t3"))  # 4 high voices, long-term use: 4.0
        + mentions(3, "Victorinox Fibrox", voice="medium", evidence="short-term use")  # 3 x 0.36 = 1.08
        + mentions(3, "Global G-2", threads=("t2", "t3"), voice="medium")  # 3 x 0.6 = 1.8
        + [mention("Global G-2", "t3", stance="warn", voice="medium")]  # -0.6, so 1.2
        + mentions(8, "Wusthof Classic", voice="low", evidence="short-term use")  # many, but none credible
    )
    result = rank_products(data, "kitchen")
    assert names(result.picks) == ["Tojiro DP Gyuto", "Global G-2", "Victorinox Fibrox"]
    assert not product(result, "Wusthof Classic").qualifies


def test_the_score_is_the_sum_of_the_mention_weights():
    data = mentions(3, "Lodge Skillet") + [mention("Lodge Skillet", "t2", stance="warn", voice="medium", evidence="short-term use")]
    scored = rank_products(data, "kitchen").products[0]
    assert scored.score == pytest.approx(3.0 - 0.36)
    assert scored.breakdown.mention_points == pytest.approx(3.0 - 0.36)


def test_only_the_query_category_is_ranked():
    data = (
        mentions(3, "CeraVe SA Cleanser", category="skincare")
        + mentions(5, "Lodge Skillet", category="kitchen")
        + mentions(5, "A Phone Case", category="other")
    )
    result = rank_products(data, "skincare")
    assert names(result.products) == ["CeraVe SA Cleanser"]


def test_an_unknown_category_is_refused():
    with pytest.raises(ValueError, match="category"):
        rank_products(mentions(3, "Lodge Skillet"), "other")


def test_more_than_three_qualifying_products_give_three_picks_best_first():
    data = mentions(6, "A Pan") + mentions(5, "B Pan") + mentions(4, "C Pan") + mentions(3, "D Pan")
    result = rank_products(data, "kitchen")
    assert names(result.picks) == ["A Pan", "B Pan", "C Pan"]
    assert names(result.qualifying) == ["A Pan", "B Pan", "C Pan", "D Pan"]


# --- What counts as a credible mention ---

def test_a_credible_mention_is_a_vote_by_a_voice_that_is_not_low_from_first_hand_use():
    assert is_credible(mention("X", voice="high", evidence="long-term use"))
    assert is_credible(mention("X", voice="medium", evidence="short-term use"))
    assert is_credible(mention("X", stance="warn", voice="medium", evidence="short-term use"))
    assert not is_credible(mention("X", voice="low", evidence="long-term use"))
    assert not is_credible(mention("X", voice="high", evidence="no first-hand use"))
    assert not is_credible(mention("X", stance="neutral", voice="high", evidence="long-term use"))


# --- The minimum-evidence rule: 3 credible recommendations across 2 threads ---

def test_two_credible_recommendations_are_not_enough():
    data = mentions(2, "Lodge Skillet") + mentions(10, "Lodge Skillet", voice="low")
    scored = rank_products(data, "kitchen").products[0]
    assert not scored.qualifies
    assert "2 of 3 credible recommendations" in scored.shortfall


def test_neutral_mentions_never_count_toward_the_rule():
    data = mentions(2, "Lodge Skillet") + mentions(5, "Lodge Skillet", stance="neutral")
    scored = rank_products(data, "kitchen").products[0]
    assert not scored.qualifies
    assert scored.score == pytest.approx(2.0)
    assert scored.breakdown.neutral == 5


def test_all_mentions_in_one_thread_fail_the_two_thread_rule():
    result = rank_products(mentions(6, "Lodge Skillet", threads=("t1",)), "kitchen")
    scored = result.products[0]
    assert not scored.qualifies
    assert "1 of 2 threads" in scored.shortfall
    assert result.picks == []


def test_low_voices_still_add_to_the_score_but_not_to_the_rule():
    data = mentions(3, "Lodge Skillet") + mentions(2, "Lodge Skillet", voice="low")
    scored = rank_products(data, "kitchen").products[0]
    assert scored.qualifies
    assert scored.score == pytest.approx(3.0 + 2 * 0.2)
    assert scored.breakdown.credible_recommends == 3


def test_one_comment_counts_once_per_product():
    same_comment = [
        mention("Lodge Skillet", comment="cX", evidence="long-term use"),
        mention("Lodge Skillet", comment="cX", evidence="short-term use"),
        mention("Lodge Skillet", comment="cX", evidence="no first-hand use"),
    ]
    scored = rank_products(same_comment + mentions(2, "Lodge Skillet"), "kitchen").products[0]
    assert scored.breakdown.credible_recommends == 3  # cX once, plus the 2 others
    assert scored.score == pytest.approx(3.0)  # cX's strongest mention (1.0) is the one kept
    assert not rank_products(same_comment, "kitchen").products[0].qualifies


def test_a_pick_needs_a_positive_score():
    # 3 credible but modest recommendations, buried under many warnings from low voices.
    data = mentions(3, "Tefal Pan", voice="medium", evidence="short-term use") + mentions(
        6, "Tefal Pan", stance="warn", voice="low", evidence="short-term use", weight=-0.2
    )
    scored = rank_products(data, "kitchen").products[0]
    assert scored.score < 0
    assert not scored.qualifies
    assert "warnings outweigh" in scored.shortfall


# --- One very credible voice versus many average ones ---

def test_one_very_credible_voice_alone_is_never_enough():
    data = [mention("Shun Classic", "t1")] + mentions(5, "Victorinox Fibrox", voice="medium", evidence="short-term use")
    result = rank_products(data, "kitchen")
    assert names(result.picks) == ["Victorinox Fibrox"]
    assert "1 of 3 credible recommendations" in product(result, "Shun Classic").shortfall


def test_one_very_credible_voice_can_outweigh_many_average_ones_once_the_rule_is_met():
    shun = [mention("Shun Classic", "t1")] + mentions(2, "Shun Classic", voice="medium", evidence="short-term use")  # 1.72
    victorinox = mentions(4, "Victorinox Fibrox", voice="medium", evidence="short-term use")  # 1.44
    result = rank_products(shun + victorinox, "kitchen")
    assert names(result.picks) == ["Shun Classic", "Victorinox Fibrox"]


# --- Ties: decided the same way every time ---

def test_equal_scores_go_to_more_credible_recommendations():
    fewer = mentions(3, "Alpha Pan", weight=1.0)
    more = mentions(4, "Beta Pan", weight=0.75)
    result = rank_products(fewer + more, "kitchen")
    assert product(result, "Alpha Pan").score == product(result, "Beta Pan").score
    assert names(result.picks) == ["Beta Pan", "Alpha Pan"]


def test_then_to_more_threads():
    two_threads = mentions(3, "Alpha Pan", threads=("t1", "t2"))
    three_threads = mentions(3, "Beta Pan", threads=("t1", "t2", "t3"))
    assert names(rank_products(two_threads + three_threads, "kitchen").picks) == ["Beta Pan", "Alpha Pan"]


def test_then_to_more_high_voices():
    all_high = mentions(3, "Alpha Pan", weight=0.6)
    all_medium = mentions(3, "Beta Pan", voice="medium", weight=0.6)
    assert names(rank_products(all_medium + all_high, "kitchen").picks) == ["Alpha Pan", "Beta Pan"]


def test_a_full_tie_is_broken_by_name_whatever_the_input_order():
    zebra, alpha = mentions(3, "Zebra Pan"), mentions(3, "alpha Pan")
    assert names(rank_products(zebra + alpha, "kitchen").picks) == ["alpha Pan", "Zebra Pan"]
    assert names(rank_products(alpha + zebra, "kitchen").picks) == ["alpha Pan", "Zebra Pan"]


def test_tiny_rounding_differences_count_as_a_tie():
    # In computer arithmetic 0.1 x 3 is 0.30000000000000004, so three of them add up to 0.9000000000000001,
    # while three times 0.3 adds up to 0.8999999999999999. Both are really 0.9.
    beta = mentions(3, "Beta Pan", weight=0.1 * 3)
    alpha = mentions(3, "Alpha Pan", weight=0.3)
    result = rank_products(beta + alpha, "kitchen")
    assert product(result, "Alpha Pan").score == product(result, "Beta Pan").score
    assert names(result.picks) == ["Alpha Pan", "Beta Pan"]


# --- Mixed opinions, the disagreement flag and the skip-these list ---

def test_praised_and_warned_is_flagged_not_hidden():
    data = mentions(4, "Lodge Skillet") + mentions(2, "Lodge Skillet", stance="warn", voice="medium")
    result = rank_products(data, "kitchen")
    scored = result.products[0]
    assert scored.qualifies and scored.disputed
    assert names(result.picks) == ["Lodge Skillet"]
    assert result.skip_list == []


def test_more_credible_warnings_than_praise_goes_to_the_skip_list_not_the_picks():
    data = (
        mentions(3, "Cuisinart Pan")
        + mentions(4, "Cuisinart Pan", stance="warn", threads=("t1", "t2", "t3"))
    )
    result = rank_products(data, "kitchen")
    scored = result.products[0]
    assert scored.on_skip_list and scored.disputed
    assert not scored.qualifies
    assert result.picks == []
    assert names(result.skip_list) == ["Cuisinart Pan"]


def test_planted_warned_against_products_appear_on_the_skip_list():
    data = mentions(2, "Tefal Pan", stance="warn") + mentions(3, "Ikea Pan", stance="warn", voice="medium")
    result = rank_products(data, "kitchen")
    assert names(result.skip_list) == ["Ikea Pan", "Tefal Pan"]  # most credible warnings first
    assert not any(p.disputed for p in result.skip_list)  # no one credible praises them


def test_the_skip_list_needs_two_credible_warnings():
    data = [mention("Tefal Pan", stance="warn")] + mentions(5, "Tefal Pan", stance="warn", voice="low")
    assert rank_products(data, "kitchen").skip_list == []


def test_praised_products_never_appear_on_the_skip_list():
    praised = mentions(5, "Lodge Skillet")
    equally_praised_and_warned = mentions(3, "Staub Pan") + mentions(3, "Staub Pan", stance="warn")
    result = rank_products(praised + equally_praised_and_warned, "kitchen")
    assert result.skip_list == []
    assert product(result, "Staub Pan").disputed
    assert not product(result, "Lodge Skillet").disputed


def test_one_credible_warning_is_not_yet_a_disagreement():
    data = mentions(4, "Lodge Skillet") + [mention("Lodge Skillet", stance="warn")] + mentions(
        3, "Lodge Skillet", stance="warn", voice="low"
    )
    assert not rank_products(data, "kitchen").products[0].disputed


# --- Thin evidence: the signal to fetch more threads ---

def test_fewer_than_three_qualifying_products():
    data = mentions(4, "A Pan") + mentions(3, "B Pan") + mentions(2, "C Pan")
    result = rank_products(data, "kitchen")
    assert names(result.picks) == ["A Pan", "B Pan"]
    assert result.needs_more_threads
    assert not result.thin_evidence


def test_no_qualifying_product_is_thin_evidence():
    data = mentions(5, "A Pan", threads=("t1",)) + mentions(2, "B Pan")
    result = rank_products(data, "kitchen")
    assert result.picks == []
    assert result.thin_evidence and result.needs_more_threads
    assert result.best_candidate.name == "A Pan"
    assert "1 of 2 threads" in result.best_candidate.shortfall


def test_enough_evidence_needs_no_more_threads():
    data = mentions(3, "A Pan") + mentions(3, "B Pan") + mentions(3, "C Pan")
    result = rank_products(data, "kitchen")
    assert not result.needs_more_threads and not result.thin_evidence


def test_no_mentions_at_all_is_thin_evidence():
    result = rank_products([], "kitchen")
    assert result.thin_evidence and result.best_candidate is None


# --- The score breakdown, signal by signal ---

def test_the_breakdown_counts_every_signal():
    data = [
        mention("Lodge Skillet", "t1"),
        mention("Lodge Skillet", "t2"),
        mention("Lodge Skillet", "t3", voice="medium", evidence="short-term use"),
        mention("Lodge Skillet", "t1", voice="low", evidence="short-term use"),
        mention("Lodge Skillet", "t2", stance="warn", voice="medium"),
        mention("Lodge Skillet", "t3", stance="warn", voice="low", evidence="no first-hand use"),
        mention("Lodge Skillet", "t1", stance="neutral", evidence="short-term use"),
    ]
    b = rank_products(data, "kitchen").products[0].breakdown
    assert (b.recommends, b.credible_recommends, b.warnings, b.credible_warnings, b.neutral) == (4, 3, 2, 1, 1)
    assert b.recommend_voices == {"high": 2, "medium": 1, "low": 1}
    assert b.recommend_evidence == {"long-term use": 2, "short-term use": 2, "no first-hand use": 0}
    assert b.warn_voices == {"high": 0, "medium": 1, "low": 1}
    assert b.warn_evidence == {"long-term use": 1, "short-term use": 0, "no first-hand use": 1}
    assert (b.threads, b.credible_threads) == (3, 3)
    assert b.mention_points == pytest.approx(1 + 1 + 0.36 + 0.12 - 0.6 - 0.04)
    assert (b.kind_bonus, b.kind, b.kind_support) == (0.0, None, None)


# --- Kind support: products of a far better supported kind move up ---

KNIVES = mentions(3, "Tojiro Gyuto", voice="medium") + mentions(3, "Wusthof Chef", weight=0.7)  # 1.8 and 2.1
PLACEMENTS = {"japanese-gyuto": ["tojiro-gyuto"], "german-chef-knife": ["wusthof-chef"]}


def test_a_far_better_supported_kind_moves_its_products_up():
    notes = mentions_of_kind("Japanese gyuto", 3) + mentions_of_kind("German chef knife", 1)
    result = rank_products(KNIVES, "kitchen", notes, PLACEMENTS, kind_bonus=1.0)
    assert names(result.picks) == ["Tojiro Gyuto", "Wusthof Chef"]
    assert result.leading_kind.name == "Japanese gyuto"
    b = product(result, "Tojiro Gyuto").breakdown
    assert (b.kind, b.kind_support, b.kind_bonus) == ("Japanese gyuto", 3.0, 1.0)
    assert product(result, "Tojiro Gyuto").score == pytest.approx(1.8 + 1.0)
    assert product(result, "Wusthof Chef").breakdown.kind_bonus == 0.0
    assert product(result, "Wusthof Chef").breakdown.kind == "German chef knife"


def test_no_bonus_when_the_lead_is_not_far():
    notes = mentions_of_kind("Japanese gyuto", 3) + mentions_of_kind("German chef knife", 2)  # 3.0 is not twice 2.0
    result = rank_products(KNIVES, "kitchen", notes, PLACEMENTS, kind_bonus=1.0)
    assert result.leading_kind is None
    assert names(result.picks) == ["Wusthof Chef", "Tojiro Gyuto"]


def test_one_credible_note_cannot_make_a_kind_lead():
    result = rank_products(KNIVES, "kitchen", mentions_of_kind("Japanese gyuto", 1), PLACEMENTS, kind_bonus=1.0)
    assert result.leading_kind is None


def test_kind_notes_from_low_voices_do_not_count():
    notes = mentions_of_kind("Japanese gyuto", 1) + mentions_of_kind("Japanese gyuto", 4, voice="low")
    result = rank_products(KNIVES, "kitchen", notes, PLACEMENTS, kind_bonus=1.0)
    assert result.leading_kind is None
    assert result.kinds[0].credible_notes == 1


def test_warnings_about_a_kind_lower_its_support():
    notes = mentions_of_kind("Japanese gyuto", 3) + mentions_of_kind("Japanese gyuto", 2, stance="warn") + mentions_of_kind(
        "German chef knife", 1
    )
    result = rank_products(KNIVES, "kitchen", notes, PLACEMENTS, kind_bonus=1.0)
    gyuto = next(k for k in result.kinds if k.name == "Japanese gyuto")
    assert gyuto.support == pytest.approx(1.0)
    assert result.leading_kind is None  # 1.0 against 1.0


def test_the_bonus_is_configurable_and_zero_turns_it_off():
    notes = mentions_of_kind("Japanese gyuto", 3)
    result = rank_products(KNIVES, "kitchen", notes, PLACEMENTS, kind_bonus=0.0)
    assert names(result.picks) == ["Wusthof Chef", "Tojiro Gyuto"]
    default = rank_products(KNIVES, "kitchen", notes, PLACEMENTS)
    assert product(default, "Tojiro Gyuto").breakdown.kind_bonus == config.KIND_BONUS


def test_the_bonus_never_lets_a_product_skip_the_minimum_evidence_rule():
    data = mentions(2, "Tojiro Gyuto")
    result = rank_products(data, "kitchen", mentions_of_kind("Japanese gyuto", 3), PLACEMENTS, kind_bonus=100.0)
    assert result.picks == []


def test_a_product_in_two_kinds_gets_the_bonus_once():
    placements = {"japanese-gyuto": ["tojiro-gyuto"], "carbon-steel-knife": ["tojiro-gyuto"]}
    notes = mentions_of_kind("Japanese gyuto", 3) + mentions_of_kind("Carbon steel knife", 1)
    result = rank_products(KNIVES, "kitchen", notes, placements, kind_bonus=1.0)
    assert product(result, "Tojiro Gyuto").breakdown.kind_bonus == 1.0


def test_one_comment_counts_once_per_kind():
    notes = [note("Japanese gyuto", comment="cK"), note("Japanese gyuto", comment="cK"), note("Japanese gyuto", comment="cK")]
    result = rank_products(KNIVES, "kitchen", notes, PLACEMENTS, kind_bonus=1.0)
    assert result.kinds[0].credible_notes == 1
    assert result.leading_kind is None


def mentions_of_kind(kind: str, n: int, **kwargs) -> list[KindNote]:
    return [note(kind, f"t{i % 2 + 1}", **kwargs) for i in range(n)]


# --- Input checks: mistakes in the glue fail loudly ---

def test_a_weight_must_match_its_stance():
    with pytest.raises(ValueError, match="weight"):
        mention("X", stance="recommend", weight=-1.0)
    with pytest.raises(ValueError, match="weight"):
        mention("X", stance="warn", weight=0.5)
    with pytest.raises(ValueError, match="weight"):
        mention("X", stance="neutral", weight=0.5)


def test_unknown_levels_are_refused():
    with pytest.raises(ValueError, match="voice"):
        mention("X", voice="very high", weight=1.0)
    with pytest.raises(ValueError, match="evidence"):
        mention("X", evidence="forever", weight=1.0)
    with pytest.raises(ValueError, match="stance"):
        mention("X", stance="love", weight=1.0)


def test_badges_given_as_a_list_are_kept_as_a_tuple():
    m = ScoredMention(
        product_key="x", product_name="X", category="kitchen", thread_id="t1", comment_id="c1",
        comment_url="https://example.com/c1", stance="recommend", weight=1.0, voice="high",
        evidence="long-term use", quote="q", badges=["3 years of use"],
    )
    assert m.badges == ("3 years of use",)
