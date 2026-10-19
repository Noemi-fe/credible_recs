"""Where a packet's pick is cut (17 Oct 2026, the converge round, item 7).

FORMAT.md rule 2: at most 90 words a pick, cut from the end of the reason or the evidence, at a word, marked "…". The
code cut whatever part ran over, the downside included: of 30 blind-test picks, 3 downsides were cut before their point
(one then read as praise) and 2 quotes inside the badge saying what backs them (the breadth-first review of 16 Oct 2026,
G). Now a downside is cut only at the end of a sentence, and only where what is left still warns; when no such cut fits,
the evidence is cut to make room, and when even that can't, the downside is left out rather than shown without its
point. A badge is kept whole or left out, never cut. The notes (rule 7) stay whole, as before.

All text is made up.
"""

from engine import blind_test
from engine.blind_test import shown_from_ours
from engine.tests.test_blind_test import NOT_IN_UK, PRESCRIPTION, pick, quote

PRAISE = "The kettle looked lovely on the counter and poured well for the first few months of daily use."
FAILURE = "Then the base failed twice in a year and the replacement leaked from the seam within weeks."
EXTRA = " ".join(["And here is a long story about the shop and the post office and the courier."] * 3)


def downside_of(shown: str) -> str:
    return next(line for line in shown.split("\n\n") if line.startswith("Downside:"))


def test_a_downside_too_long_to_fit_is_cut_at_the_end_of_a_sentence_that_keeps_its_point():
    shown = shown_from_ours({"picks": [pick(1, "Acme kettle", downsides=[quote(f"{PRAISE} {FAILURE} {EXTRA}")])]})
    assert downside_of(shown) == f'Downside: "{PRAISE} {FAILURE} …"'
    assert blind_test.words_per_pick(shown)[0] <= blind_test.BLIND_TEST_WORDS_PER_PICK


def test_a_downside_is_never_cut_before_its_point_the_evidence_makes_room():
    # Its point is in its last sentence, so no shorter cut keeps it: the second quote gives way instead.
    long_reason = "Recommended by 3 credible voices, 2 of them after long-term use, 3 of them about how long it lasts"
    shown = shown_from_ours({"picks": [pick(1, "Acme kettle", reason=long_reason,
                                            downsides=[quote(f"{PRAISE} {PRAISE} {FAILURE}")])]})
    assert downside_of(shown) == f'Downside: "{PRAISE} {PRAISE} {FAILURE}"'
    assert blind_test.words_per_pick(shown)[0] <= blind_test.BLIND_TEST_WORDS_PER_PICK
    assert '"Mine has lasted five years and still boils fast."' in shown


def test_a_downside_that_cant_keep_its_point_in_the_words_left_is_left_out():
    reason = " ".join(["reason"] * 70)
    shown = shown_from_ours({"picks": [pick(1, "Acme kettle", reason=reason, quotes=[],
                                            downsides=[quote(f"{PRAISE} {FAILURE}")])]})
    assert "Downside" not in shown and PRAISE not in shown


def test_a_badge_is_never_cut():
    shown = shown_from_ours({"picks": [pick(1, "Acme kettle", reason=" ".join(["reason"] * 50), quotes=[
        quote("Mine has lasted five years and still boils fast, no rust, no leaks, nothing at all to complain of here.",
              "18 points, more than 86% of this thread's comments")])]})
    assert "(18 points, more than 86% of this thread's comments)" in shown or "points" not in shown
    assert "…)" not in shown and "of…" not in shown


def test_the_notes_stay_whole_however_long_the_rest():
    long_downside = " ".join([FAILURE] * 6)
    shown = shown_from_ours({"picks": [pick(1, "Finacea", reason=" ".join(["reason"] * 40),
                                            downsides=[quote(long_downside)],
                                            cautions=["Note: we couldn't confirm it's fragrance-free."],
                                            availability=NOT_IN_UK, prescription=PRESCRIPTION)]})
    for note in ("Note: we couldn't confirm it's fragrance-free.", "Not sold in the UK, checked 15 Oct 2026.",
                 PRESCRIPTION):
        assert note in shown
    assert blind_test.words_per_pick(shown)[0] <= blind_test.BLIND_TEST_WORDS_PER_PICK


def test_a_quote_that_fits_whole_without_its_badge_is_shown_whole_without_it():
    text = "Mine has lasted five years and still boils fast."
    shown = shown_from_ours({"picks": [pick(1, "Acme kettle", reason=" ".join(["reason"] * 76),
                                            quotes=[quote(text, "18 points, more than 86% of this thread's comments")],
                                            price={"text": "Price not checked yet", "amount": None})]})
    assert f'"{text}"' in shown and "…" not in shown and "points" not in shown
