"""Scoring module 3 (mention extraction) against Noemi's labels: precision, recall, and whether the stance and
category agree.

Everything is built in memory: made-up threads from factories.py, labels as VoiceLabel and MentionLabel rows, and
the AI's checked extractions as CheckResults. No test reads data/.
"""

from engine.extract import CheckResult, ExtractedMention
from engine.extraction_eval import Miss, report_lines, score_extraction
from engine.gold import GoldSet
from engine.models import MentionLabel, Thread, VoiceLabel
from engine.tests.factories import make_comment, make_thread

# The made-up thread 1fake01 (factories.make_thread): c1aaaa praises the CeraVe SA Cleanser, c2bbbb replies "Same
# here", c3cccc praises Paula's Choice 2% BHA. A fourth comment is added here, which Noemi hasn't labelled.
THREAD = Thread.model_validate(make_thread(comments=make_thread()["comments"] + [
    make_comment("c4dddd", body="My Fellow Stagg kettle is great."),
]))


def other_thread(thread_id: str = "1fake02") -> Thread:
    """A second thread, with comment ids of its own."""
    return Thread.model_validate(make_thread(
        id=thread_id,
        url=f"https://www.reddit.com/r/SkincareAddiction/comments/{thread_id}/post/",
        comments=[make_comment(f"{thread_id}c1", thread_id=thread_id, body="My La Roche-Posay sunscreen is great.")],
    ))


def voice(comment_id: str, thread_id: str = "1fake01", has_products: bool = True) -> VoiceLabel:
    """Noemi's row in voices.csv: she read this comment. A comment with no product has no voice level."""
    if has_products:
        return VoiceLabel(thread_id=thread_id, comment_id=comment_id, voice="high", tags="established member")
    return VoiceLabel(thread_id=thread_id, comment_id=comment_id, tags=None)


def label(comment_id: str, product: str, stance: str = "recommend", category: str = "skincare") -> MentionLabel:
    """Noemi's row in mentions.csv: one product in one comment."""
    return MentionLabel(comment_id=comment_id, product=product, category=category, stance=stance,
                        evidence="long-term use", tags="long-term use")


def ai(comment_id: str, product: str, stance: str = "recommend", category: str = "skincare") -> ExtractedMention:
    """One mention the AI found that passed the quote checks. The quote isn't scored, so any text will do."""
    return ExtractedMention(comment_id=comment_id, product=product, category=category, stance=stance, quote="a quote")


def kept(*mentions: ExtractedMention) -> CheckResult:
    return CheckResult(kept=list(mentions))


# Noemi's labels of 1fake01: c1aaaa and c3cccc each mention one product; c2bbbb mentions none; c4dddd is unlabelled.
VOICES = [voice("c1aaaa"), voice("c2bbbb", has_products=False), voice("c3cccc")]
LABELS = [label("c1aaaa", "CeraVe SA Cleanser"), label("c3cccc", "Paula's Choice 2% BHA")]


def gold(voices=VOICES, mentions=LABELS, threads=(THREAD,)) -> GoldSet:
    return GoldSet(threads=list(threads), voices=list(voices), mentions=list(mentions))


def test_a_perfect_extraction_scores_full_marks():
    score = score_extraction(gold(), {"1fake01": kept(ai("c1aaaa", "CeraVe SA Cleanser"), ai("c3cccc", "Paula's Choice 2% BHA"))})
    assert (score.matched, score.ai_total, score.gold_total) == (2, 2, 2)
    assert score.precision == score.recall == score.stance_agreement == score.category_agreement == 1.0
    assert score.misses == []
    assert score.not_extracted == []
    assert (score.threads, score.labelled_comments) == (1, 3)


def test_a_product_the_ai_missed_lowers_recall_only():
    score = score_extraction(gold(), {"1fake01": kept(ai("c1aaaa", "CeraVe SA Cleanser"))})
    assert (score.matched, score.ai_total, score.gold_total) == (1, 1, 2)
    assert score.precision == 1.0
    assert score.recall == 0.5
    assert score.misses == [Miss("c3cccc", "missed by the AI", "Paula's Choice 2% BHA")]


def test_an_extra_ai_product_lowers_precision_only():
    checked = {"1fake01": kept(ai("c1aaaa", "CeraVe SA Cleanser"), ai("c1aaaa", "CeraVe Moisturizing Cream"),
                               ai("c3cccc", "Paula's Choice 2% BHA"))}
    score = score_extraction(gold(), checked)
    assert (score.matched, score.ai_total, score.gold_total) == (2, 3, 2)
    assert score.precision == 2 / 3
    assert score.recall == 1.0
    assert score.misses == [Miss("c1aaaa", "not in Noemi's labels", "CeraVe Moisturizing Cream")]


def test_a_product_named_differently_by_the_ai_still_matches():
    labels = [label("c1aaaa", "CeraVe SA"), label("c3cccc", "Paula's Choice 2% BHA")]
    checked = {"1fake01": kept(ai("c1aaaa", "CeraVe Renewing SA Cleanser"), ai("c3cccc", "paulas choice 2 bha"))}
    score = score_extraction(gold(mentions=labels), checked)
    assert (score.matched, score.ai_total, score.gold_total) == (2, 2, 2)
    assert score.misses == []


def test_a_different_stance_counts_as_found_but_lowers_stance_agreement():
    checked = {"1fake01": kept(ai("c1aaaa", "CeraVe SA Cleanser", stance="neutral"), ai("c3cccc", "Paula's Choice 2% BHA"))}
    score = score_extraction(gold(), checked)
    assert score.precision == score.recall == 1.0
    assert score.stance_agreement == 0.5
    assert score.category_agreement == 1.0
    assert score.misses == [Miss("c1aaaa", "stance differs: hers recommend, AI neutral", "CeraVe SA Cleanser")]


def test_a_different_category_lowers_category_agreement():
    checked = {"1fake01": kept(ai("c1aaaa", "CeraVe SA Cleanser", category="other"), ai("c3cccc", "Paula's Choice 2% BHA"))}
    score = score_extraction(gold(), checked)
    assert score.category_agreement == 0.5
    assert score.stance_agreement == 1.0


def test_comments_noemi_has_not_labelled_are_ignored():
    # c4dddd has no row in voices.csv: whatever the AI found there can't be checked, so it doesn't count.
    checked = {"1fake01": kept(ai("c1aaaa", "CeraVe SA Cleanser"), ai("c3cccc", "Paula's Choice 2% BHA"),
                               ai("c4dddd", "Fellow Stagg kettle", category="kitchen"))}
    score = score_extraction(gold(), checked)
    assert (score.matched, score.ai_total, score.gold_total) == (2, 2, 2)
    assert score.precision == 1.0
    assert score.misses == []


def test_a_product_found_in_a_comment_noemi_marked_as_having_none_lowers_precision():
    # c2bbbb has a voices row and no mention rows: Noemi read it and found no product.
    checked = {"1fake01": kept(ai("c1aaaa", "CeraVe SA Cleanser"), ai("c2bbbb", "CeraVe SA Cleanser"),
                               ai("c3cccc", "Paula's Choice 2% BHA"))}
    score = score_extraction(gold(), checked)
    assert (score.matched, score.ai_total, score.gold_total) == (2, 3, 2)
    assert score.precision == 2 / 3
    assert score.recall == 1.0
    assert score.misses == [Miss("c2bbbb", "not in Noemi's labels", "CeraVe SA Cleanser")]


def test_mentions_dropped_by_the_quote_checks_do_not_count():
    result = CheckResult(kept=[ai("c1aaaa", "CeraVe SA Cleanser"), ai("c3cccc", "Paula's Choice 2% BHA")],
                         rejected=[(ai("c3cccc", "Paula's Choice Toner"), "quote not found word for word in comment c3cccc")])
    score = score_extraction(gold(), {"1fake01": result})
    assert (score.matched, score.ai_total) == (2, 2)


def test_a_labelled_thread_not_extracted_yet_is_skipped_and_listed():
    second = other_thread()
    voices = VOICES + [voice("1fake02c1", thread_id="1fake02")]
    labels = LABELS + [label("1fake02c1", "La Roche-Posay Anthelios")]
    checked = {"1fake01": kept(ai("c1aaaa", "CeraVe SA Cleanser"), ai("c3cccc", "Paula's Choice 2% BHA"))}
    score = score_extraction(gold(voices=voices, mentions=labels, threads=(THREAD, second)), checked)
    # The second thread's label isn't a miss: the AI hasn't read that thread yet.
    assert (score.matched, score.ai_total, score.gold_total) == (2, 2, 2)
    assert score.not_extracted == ["1fake02"]
    assert (score.threads, score.labelled_comments) == (1, 3)


def test_a_thread_noemi_has_not_labelled_is_neither_scored_nor_listed():
    # Gold threads are labelled before the AI reads them (so its answers can't sway her), so an unlabelled thread
    # with no extraction is expected, not a gap; and an extraction of it has nothing to be checked against.
    second = other_thread()
    checked = {"1fake01": kept(ai("c1aaaa", "CeraVe SA Cleanser"), ai("c3cccc", "Paula's Choice 2% BHA"))}
    score = score_extraction(gold(threads=(THREAD, second)), checked)
    assert score.not_extracted == []
    assert score.threads == 1
    checked["1fake02"] = kept(ai("1fake02c1", "La Roche-Posay Anthelios"))
    score = score_extraction(gold(threads=(THREAD, second)), checked)
    assert (score.matched, score.ai_total, score.threads) == (2, 2, 1)


def test_each_label_matches_at_most_one_ai_mention():
    # The AI listed the same cleanser twice under two names: only one of them can be the product Noemi labelled.
    labels = [label("c1aaaa", "CeraVe SA Cleanser")]
    checked = {"1fake01": kept(ai("c1aaaa", "CeraVe SA Cleanser"), ai("c1aaaa", "CeraVe Renewing SA Cleanser"))}
    score = score_extraction(gold(mentions=labels), checked)
    assert (score.matched, score.ai_total, score.gold_total) == (1, 2, 1)
    assert score.precision == 0.5
    assert score.recall == 1.0
    assert score.misses == [Miss("c1aaaa", "not in Noemi's labels", "CeraVe Renewing SA Cleanser")]


def test_each_ai_mention_matches_at_most_one_label():
    labels = [label("c1aaaa", "CeraVe SA Cleanser"), label("c1aaaa", "CeraVe Renewing SA Cleanser")]
    checked = {"1fake01": kept(ai("c1aaaa", "CeraVe SA Cleanser"))}
    score = score_extraction(gold(mentions=labels), checked)
    assert (score.matched, score.ai_total, score.gold_total) == (1, 1, 2)
    assert score.recall == 0.5


def test_the_pairing_that_matches_the_most_products_is_found():
    # "CeraVe cleanser" fits both of the AI's cleansers, "CeraVe Hydrating Cleanser" only one. Pairing the first
    # label with the first fit would leave the second label unmatched; the best pairing matches both.
    labels = [label("c1aaaa", "CeraVe cleanser"), label("c1aaaa", "CeraVe Hydrating Cleanser")]
    checked = {"1fake01": kept(ai("c1aaaa", "CeraVe Hydrating Cleanser"), ai("c1aaaa", "CeraVe SA Cleanser"))}
    score = score_extraction(gold(mentions=labels), checked)
    assert (score.matched, score.ai_total, score.gold_total) == (2, 2, 2)


def test_an_exact_name_is_preferred_over_a_loose_fit():
    # Both of the AI's mentions fit the label "CeraVe SA Cleanser" loosely or exactly; the exact one is paired, so
    # its stance is the one compared.
    labels = [label("c1aaaa", "CeraVe SA Cleanser")]
    checked = {"1fake01": kept(ai("c1aaaa", "CeraVe SA", stance="warn"), ai("c1aaaa", "CeraVe SA Cleanser"))}
    score = score_extraction(gold(mentions=labels), checked)
    assert score.stance_agreement == 1.0
    assert score.misses == [Miss("c1aaaa", "not in Noemi's labels", "CeraVe SA")]


def test_ratios_with_nothing_to_divide_are_none():
    score = score_extraction(gold(voices=[voice("c2bbbb", has_products=False)], mentions=[]), {"1fake01": kept()})
    assert (score.matched, score.ai_total, score.gold_total) == (0, 0, 0)
    assert score.precision is None
    assert score.recall is None
    assert score.stance_agreement is None
    assert score.category_agreement is None


# --- The report ---

def test_the_report_reads_plainly():
    checked = {"1fake01": kept(ai("c1aaaa", "CeraVe SA Cleanser", stance="warn"), ai("c2bbbb", "CeraVe SA Cleanser"))}
    voices = VOICES + [voice("1fake02c1", thread_id="1fake02")]
    labels = LABELS + [label("1fake02c1", "La Roche-Posay Anthelios")]
    score = score_extraction(gold(voices=voices, mentions=labels, threads=(THREAD, other_thread())), checked)
    assert report_lines(score) == [
        "precision 1/2 (50%), recall 1/2 (50%), stance agreement 0/1 (0%), category agreement 1/1 (100%), "
        "over 1 thread, 3 labelled comments",
        "  c1aaaa  stance differs: hers recommend, AI warn: CeraVe SA Cleanser",
        "  c2bbbb  not in Noemi's labels: CeraVe SA Cleanser",
        "  c3cccc  missed by the AI: Paula's Choice 2% BHA",
        "not extracted yet: 1fake02",
    ]


def test_the_report_says_n_a_for_a_ratio_with_nothing_to_divide():
    score = score_extraction(gold(voices=[voice("c2bbbb", has_products=False)], mentions=[]), {"1fake01": kept()})
    assert report_lines(score) == [
        "precision 0/0 (n/a), recall 0/0 (n/a), stance agreement 0/0 (n/a), category agreement 0/0 (n/a), "
        "over 1 thread, 1 labelled comment",
    ]


def test_the_report_lists_at_most_15_misses():
    labels = [label("c1aaaa", f"Product {letter}") for letter in "ABCDEFGHIJKLMNOPQRST"]  # 20 products the AI missed
    score = score_extraction(gold(mentions=labels), {"1fake01": kept()})
    lines = report_lines(score)
    assert len(score.misses) == 20
    assert lines[1:16] == [f"  c1aaaa  missed by the AI: Product {letter}" for letter in "ABCDEFGHIJKLMNO"]
    assert lines[16] == "  ... and 5 more"
    assert len(lines) == 17
