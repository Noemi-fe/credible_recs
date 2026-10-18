"""Module 5, first-hand use and whose time of use it is (the converge round of 17 Oct 2026, ws-ranking items 3 and 4).

Noemi's decision 3 of 16 Oct 2026: the AI's reading of the whole comment counts when the rules miss the writer's use,
but only where her labelled gold threads don't get worse; and the times of use the rules gave the wrong product are
fixed: a writer's older model's years counted for the one they now recommend, "just bought" read as years, another
product's or another person's years. Item 4: hearsay ("my friend swears by it") is never first-hand use, also when the
AI's own level says use while its tags say someone else's experience.

Every comment here is made up (no Reddit commenter's words); the product names are invented or generic.
"""

import pytest

from engine.credibility import NO_USE, score_evidence, with_ai_evidence
from engine.models import Comment
from engine.tests.factories import make_comment

RECENT = "2026-09-01T10:00:00Z"


def evidence_for(body: str, product: str, stance: str = "recommend", others=()):
    comment = Comment.model_validate(make_comment("c1aaaa", body=body, created_at=RECENT))
    return score_evidence(comment, product, stance, other_products=others)


def with_ai(body: str, product: str, ai_level, ai_tags=(), others=(), stance: str = "recommend"):
    return with_ai_evidence(evidence_for(body, product, stance, others), ai_level, ai_tags)


# --- Item 3: the AI's reading counts when the rules miss the writer's use ---

@pytest.mark.parametrize("body, tags", [
    # The writer speaks for themselves in words the rules don't list ("I tested", "ours", "I put"), and the AI read use.
    ("Tested the Quill Arc driver against two others and it pulled ahead every time.", ["specific details"]),
    ("Honestly the Quill Arc driver lives in our garage now, we really dislike the old one.", []),
    ("A little Quill Arc serum after washing and the ends behave, I put it on daily.", []),
])
def test_use_the_ai_reads_counts_when_the_rules_miss_it(body, tags):
    rules = evidence_for(body, "Quill Arc")
    assert rules.level == NO_USE  # the words the rules know say nothing of use
    evidence = with_ai(body, "Quill Arc", "short-term use", ["short-term use", *tags])
    assert evidence.level == "short-term use"
    assert "short-term use" in evidence.tags


def test_the_ais_long_term_reading_counts_too_without_a_time_badge_it_cant_quote():
    body = "Still rocking the Quill Arc phone from years back, the battery is tired but it is fine."
    rules = evidence_for(body, "Quill Arc")
    evidence = with_ai_evidence(rules, "long-term use", ["long-term use", "mentions flaws"])
    assert evidence.level == "long-term use"
    assert not any("of use" in badge for badge in evidence.badges)


@pytest.mark.parametrize("body", [
    "Quill Arc vitamin serum",  # a bare name in a list
    "Quill Arc is still made in the same old factory and will outlive you.",  # a claim about the brand
    "If you want something cheaper, Quill Arc is a little less expensive and has more of the active.",  # facts only
])
def test_a_bare_or_vague_mention_stays_no_use_whatever_the_ai_says(body):
    # Noemi's gold labels: a writer recommending brands in general ("X and Y have great exfoliants") hasn't shown use;
    # the AI had read such mentions as short-term use, "vague". Without a concrete tag or the writer speaking for
    # themselves in the product's own sentences, the AI's reading adds nothing.
    assert with_ai(body, "Quill Arc", "short-term use", ["short-term use", "vague"]).level == NO_USE
    assert with_ai(body, "Quill Arc", "short-term use", ["short-term use", "cheaper alternative"]).level == NO_USE


def test_an_opinion_or_a_suggestion_in_the_first_person_is_not_a_sign_of_use():
    for body in ("In my opinion the Quill Arc range is the king of audio.",
                 "I'd suggest Quill Arc, as others have, but get three of them.",
                 "I recommend Quill Arc for anyone on a budget!"):
        assert with_ai(body, "Quill Arc", "short-term use", ["short-term use"]).level == NO_USE


def test_the_ai_never_adds_use_it_reads_as_someone_elses():
    body = "Quill Arc grinders are excellent, everyone at the roastery uses one."
    assert with_ai(body, "Quill Arc", "short-term use", ["short-term use", "secondhand", "specific details"]).level == NO_USE


# --- Item 4: hearsay is never first-hand, also when the AI's level and tags clash ---

def test_a_verdict_beside_what_others_say_is_no_first_hand_use():
    # A verdict ("they're great") is use by the guide, but not when the AI reads it as someone else's experience.
    body = "The Quill Arc knives are great and very reasonable, everyone at the restaurant swears by them."
    assert evidence_for(body, "Quill Arc").level == "short-term use"  # the rules: a verdict
    evidence = with_ai(body, "Quill Arc", "short-term use", ["short-term use", "secondhand"])
    assert evidence.level == NO_USE and "secondhand" in evidence.tags


def test_what_a_test_kitchen_or_a_reviewer_says_is_hearsay():
    body = "The Quill Arc knives are great and very reasonable, the test kitchen recommends them."
    assert evidence_for(body, "Quill Arc").level == NO_USE


def test_a_time_of_the_writers_own_stays_use_when_the_ai_tags_a_second_hand_purchase():
    # The AI also tags "bought second-hand" as "secondhand": with no other person nor hearsay in the product's words,
    # the writer's own years stand.
    body = "Same here. The Quill Arc rack for 7 years, bought gently used, no rust at all."
    evidence = with_ai(body, "Quill Arc", "long-term use", ["long-term use", "secondhand"])
    assert evidence.level == "long-term use"


@pytest.mark.parametrize("body", [
    "My folks have a Quill Arc oven from the seventies that still works fine.",
    "My fiancé had a couple of Quill Arc jackets, the first one fell apart after a wash.",
    "My stepdad has had his Quill Arc boots for over 20 years.",
    "A friend of mine has had a Quill Arc shovel for years and uses it all the time.",
    "Working on the docks I have met plenty of people who have owned Quill Arc bags for 20+ years.",
])
def test_someone_elses_experience_is_no_first_hand_use_when_the_ai_says_so(body):
    evidence = with_ai(body, "Quill Arc", "long-term use", ["long-term use", "secondhand"])
    assert evidence.level == NO_USE
    assert "secondhand" in evidence.tags


@pytest.mark.parametrize("body", [
    "My folks have a Quill Arc oven from the seventies that still works fine.",
    "My fiancé had a couple of Quill Arc jackets, the first one fell apart after a wash.",
    "My stepdad has had his Quill Arc boots for over 20 years.",
    "A friend of mine has had a Quill Arc shovel for years and uses it all the time.",
    "Working on the docks I have met plenty of people who have owned Quill Arc bags for 20+ years.",
])
def test_other_peoples_use_is_no_first_hand_use_by_the_rules_alone(body):
    # The rules had read "my folks", "my fiancé", "my stepdad", "of mine" and "I have met" as the writer's own.
    assert evidence_for(body, "Quill Arc").level == NO_USE


@pytest.mark.parametrize("body", [
    "My partner and I have used the Quill Arc kettle every day for two years.",
    "My parents own the older model and I got my Quill Arc last month, it's lovely.",
    "I inherited my grandfather's Quill Arc jacket ten years ago and wear it every winter.",
])
def test_the_writers_own_use_beside_someone_elses_still_counts(body):
    evidence = with_ai(body, "Quill Arc", "short-term use", ["short-term use", "secondhand"])
    assert evidence.level != NO_USE


# --- Item 3: whose time of use it is ---

def test_a_writers_older_model_lends_its_years_to_no_other_model():
    # The laptop answer's counted-twice comment: years with an older Pro model, then an Air bought recently.
    body = ("I had a Zephyr Pro and carried it daily for nearly 10 years. Took it everywhere. "
            "Recently upgraded to a Zephyr Air and I'm happy with it.")
    evidence = evidence_for(body, "Zephyr Air")
    assert evidence.level == "short-term use"
    assert "10 years of use" not in evidence.reasons + evidence.badges
    assert evidence_for(body, "Zephyr Pro").level == "long-term use"


def test_just_bought_is_a_fresh_start_whatever_time_the_sentence_gives_something_else():
    body = 'I just bought a Kilo JX after fighting my old grinder for a couple years to grind finer. Worth twice the price.'
    evidence = evidence_for(body, "Kilo JX")
    assert evidence.level == "short-term use"
    assert not any("of use" in reason for reason in evidence.reasons)


def test_a_time_in_a_clause_about_another_product_is_not_this_ones():
    body = ("These 70 year old Brightmoor pans cook far more evenly than my 12 year old Calder. "
            "I got the Calder first and then recently got the Brightmoors.")
    brightmoor = evidence_for(body, "Brightmoor", others=("Calder",))
    assert brightmoor.level == "short-term use"
    assert "12 years of use" not in brightmoor.reasons
    assert evidence_for(body, "Calder", others=("Brightmoor",)).level == "long-term use"


def test_another_persons_years_beside_the_writers_own_are_not_the_writers():
    body = "I got the Quill Arc toaster oven last month and my parents have had theirs for 15 years."
    evidence = evidence_for(body, "Quill Arc")
    assert evidence.level == "short-term use"
    assert "15 years of use" not in evidence.reasons


def test_the_writers_own_years_beside_someone_elses_still_count():
    body = "I've cut on my Quill Arc boards for over ten years (my parents kept theirs for 50+ years)."
    evidence = evidence_for(body, "Quill Arc")
    assert evidence.level == "long-term use"
    assert "50 years of use" not in evidence.reasons


def test_a_time_said_with_the_product_it_lasted_still_counts_after_a_fresh_start():
    # Only the sentence of the fresh start loses its times: the first one's years, said apart, still count.
    body = "Just bought my second Quill Arc kettle. The first one lasted 12 years."
    assert evidence_for(body, "Quill Arc").level == "long-term use"


def test_long_use_the_ai_reads_counts_where_the_rules_see_use_but_no_time():
    body = "We use the Quill Arc kettle every morning, though the lid sticks a bit."
    rules = evidence_for(body, "Quill Arc")
    assert rules.level == "short-term use"
    evidence = with_ai_evidence(rules, "long-term use", ["long-term use", "mentions flaws"])
    assert evidence.level == "long-term use"
    assert not any("of use" in badge for badge in evidence.badges)


def test_a_time_the_rules_found_is_never_lengthened_by_the_ais_reading():
    body = "Had the Quill Arc kettle 6 months now, it is lovely."
    rules = evidence_for(body, "Quill Arc")
    assert rules.level == "short-term use"
    assert with_ai_evidence(rules, "long-term use", ["long-term use", "specific details"]).level == "short-term use"


def test_without_the_switches_the_ai_only_takes_use_away(monkeypatch):
    from engine import config
    monkeypatch.setattr(config, "AI_FIRST_HAND_COUNTS", False)
    monkeypatch.setattr(config, "AI_LONG_TERM_COUNTS", False)
    body = "Tested the Quill Arc driver against two others and it pulled ahead every time."
    assert with_ai(body, "Quill Arc", "short-term use", ["short-term use", "specific details"]).level == NO_USE
    body = "We use the Quill Arc kettle every morning, though the lid sticks a bit."
    assert with_ai(body, "Quill Arc", "long-term use", ["long-term use", "mentions flaws"]).level == "short-term use"


def test_a_short_name_of_the_same_model_is_no_sibling():
    from engine.credibility import _names_a_sibling

    assert not _names_a_sibling("my sony xm4 has lasted three years.", "Sony WH-1000XM4")
    assert _names_a_sibling("the sony wf-1000xm3 earbuds were fine.", "Sony WH-1000XM4")
    assert not _names_a_sibling("my zephyr has lasted ten years.", "Zephyr Air")  # no model said: it may be this one


@pytest.mark.parametrize("body", [
    "I bought a Quill Arc wallet for my boyfriend ten years ago and it is still going strong.",
    "Bought my sisters some Quill Arc speakers about five years ago and they're still kicking.",
    "My dad has a pair of Quill Arc headphones that I bought for him 12 years ago, they still work.",
    "I ordered my girl some Quill Arc boots and she loves them.",
])
def test_a_gifts_use_is_the_persons_it_was_for(body):
    assert evidence_for(body, "Quill Arc").level == NO_USE


def test_another_persons_years_without_a_my_are_theirs_too():
    body = "I finally got a Quill Arc toaster last month. Godmother has had one for 20+ years."
    evidence = evidence_for(body, "Quill Arc")
    assert evidence.level == "short-term use"
    assert "20 years of use" not in evidence.reasons
