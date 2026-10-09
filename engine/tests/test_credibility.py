"""Module 5, credibility scoring: voice per comment, evidence per product mention, and the mention's weight.

Every comment, writer and thread here is made up (factories.py). No test reads data/. Thresholds are read from
engine/config.py rather than typed in, so Noemi can change a PROPOSED value without breaking a test.
"""

from datetime import datetime, timedelta

import pytest

from engine import config
from engine.credibility import (
    CommenterHistory, EvidenceScore, VoiceScore, badges, mention_weight, score_evidence, score_voice,
)
from engine.extract import ExtractedAgreement
from engine.models import Comment, Thread
from engine.tests.factories import make_comment, make_thread

COLLECTED = "2026-10-06"
RECENT = "2026-09-01T10:00:00Z"  # a month before the thread was collected
PLAIN = {"name": "test_writer"}  # what Parse gives: a name, no account age, karma or flair
USES_IT = "I've used the CeraVe SA Cleanser every day for a year."  # first-hand use, nothing else


def years_before(moment: str, years: float) -> str:
    when = datetime.fromisoformat(moment.replace("Z", "+00:00")) - timedelta(days=round(365.25 * years))
    return when.date().isoformat()


def account(created: str | None = None, karma: int | None = None, flair: str | None = None, name: str = "test_writer") -> dict:
    return {"name": name, "account_created_at": created, "karma": karma, "flair": flair}


def make_case(body: str = USES_IT, score: int = 2, author: dict | None = PLAIN, created: str = RECENT,
              others: tuple[int, ...] = (1, 1, 2, 2), category: str = "skincare", replies: tuple[str, ...] = ()) -> tuple[Comment, Thread]:
    """One comment (c1aaaa) in a made-up thread, plus other comments with the given scores, plus replies to it."""
    comments = [make_comment("c1aaaa", body=body, score=score, author=author, created_at=created)]
    comments += [make_comment(f"o{i}other", body="Nice thread.", score=s, created_at=created) for i, s in enumerate(others)]
    comments += [make_comment(f"r{i}reply", parent_id="c1aaaa", body=text, created_at=created) for i, text in enumerate(replies)]
    community = "SkincareAddiction" if category == "skincare" else "BuyItForLife"
    thread = Thread.model_validate(make_thread(
        category=category, community=community, created_at=created, collected_at=COLLECTED, comments=comments,
    ))
    return thread.comments[0], thread


def voice_for(agreements=(), history=None, **case) -> VoiceScore:
    comment, thread = make_case(**case)
    return score_voice(comment, thread, agreements=agreements, history=history)


# --- Voice: the guide's rubric ---

def test_an_ordinary_owner_in_a_recent_thread_is_medium():
    # One good sign (recent), no red flag: "an ordinary owner".
    voice = voice_for()
    assert voice.level == "medium"
    assert voice.tags == ("recent",)
    assert voice.red_flags == ()


def test_two_good_signs_and_no_red_flag_is_high():
    voice = voice_for(score=9, others=(1, 1, 2, 2, 3))  # well upvoted for this thread, and recent
    assert voice.level == "high"
    assert set(voice.tags) == {"well upvoted", "recent"}


def test_any_red_flag_is_low_whatever_the_good_signs():
    voice = voice_for(body=USES_IT + " Use my code GLOW20 for 20% off!", score=9, others=(1, 1, 2))
    assert voice.level == "low"
    assert "salesy language" in voice.tags
    assert "well upvoted" in voice.tags  # the good signs are still recorded, for the breakdown


def test_every_tag_is_one_of_the_voice_tags_or_other():
    voice = voice_for(body="Use my code GLOW20. " + USES_IT, score=-3, author=account(created=years_before(RECENT, 0.01)))
    assert set(voice.tags) <= set(config.VOICE_TAGS) | {config.OTHER_TAG}
    assert len(voice.reasons) == len(voice.signs)


# --- Community standing ---

def test_an_old_account_with_karma_is_an_established_member():
    voice = voice_for(author=account(created=years_before(RECENT, config.ESTABLISHED_ACCOUNT_YEARS + 1),
                                     karma=config.ESTABLISHED_MIN_KARMA))
    assert "established member" in voice.tags
    assert voice.level == "high"  # established and recent


def test_an_old_account_with_no_sign_of_activity_is_not_established():
    voice = voice_for(author=account(created=years_before(RECENT, 10), karma=None))
    assert "established member" not in voice.tags


def test_a_brand_new_account_is_a_red_flag():
    voice = voice_for(author=account(created=years_before(RECENT, (config.NEW_ACCOUNT_DAYS - 5) / 365.25), karma=50))
    assert voice.level == "low"
    assert "new account" in voice.tags


def test_account_age_is_measured_when_the_comment_was_written():
    # An account opened a week before an old comment was new then, even if it is years old today.
    voice = voice_for(created="2025-06-01T10:00:00Z", author=account(created="2025-05-25", karma=20000))
    assert "new account" in voice.tags


def test_a_genuine_expert_on_a_new_account_is_low_but_still_counts():
    # Edge case from the brief. The rubric says any red flag is low; the evidence layer still carries what they know.
    comment, thread = make_case(
        body="Dermatologist here. I've prescribed and used the CeraVe SA Cleanser for 10 years.",
        author=account(created=years_before(RECENT, 0.02), flair="Dermatologist"),
    )
    voice = score_voice(comment, thread)
    assert voice.level == "low"
    assert {"new account", "expert flair"} <= set(voice.tags)
    evidence = score_evidence(comment, "CeraVe SA Cleanser", "recommend")
    assert evidence.level == "long-term use"
    assert mention_weight(voice, evidence, "recommend") > 0


def test_a_high_karma_account_that_promotes_is_still_low():
    # Edge case from the brief: karma never buys back independence.
    voice = voice_for(body="Full disclosure: I'm the founder. " + USES_IT,
                      author=account(created=years_before(RECENT, 8), karma=250_000))
    assert voice.level == "low"
    assert "promotes one brand" in voice.tags
    assert "established member" in voice.tags


def test_expert_flair_counts_but_says_it_is_unverified():
    # Edge case from the brief: anyone can write "dermatologist" in a flair, so it is one good sign, worded as a claim.
    voice = voice_for(author=account(flair="Dermatologist"))
    assert "expert flair" in voice.tags
    assert voice.level == "high"  # expert flair and recent: two good signs
    reason = next(sign.reason for sign in voice.signs if sign.name == "expert flair")
    assert "Dermatologist" in reason and "not verified" in reason


def test_a_skin_type_flair_is_not_expert_flair():
    assert "expert flair" not in voice_for(author=account(flair="Dry/sensitive, 30s")).tags


def test_an_unverified_expert_flair_cannot_outweigh_salesy_language():
    voice = voice_for(body="DM me for a discount. " + USES_IT, author=account(flair="Dermatologist"))
    assert voice.level == "low"


def test_a_deleted_account_has_no_standing_signs_but_is_still_scored():
    voice = voice_for(author=None, score=9, others=(1, 1, 2))
    assert voice.level == "high"  # well upvoted and recent; a deleted account is not a red flag
    assert not {"established member", "new account", "expert flair"} & set(voice.tags)
    assert any("deleted" in reason for reason in voice.reasons)


def test_low_karma_for_its_activity_needs_the_commenter_history():
    history = CommenterHistory(contributions=450)
    voice = voice_for(author=account(created=years_before(RECENT, 5), karma=209), history=history)
    assert voice.level == "low"
    assert "low karma for its activity" in voice.tags
    # Without the history, a small karma alone proves nothing (a quiet reader, not a spammer).
    assert "low karma for its activity" not in voice_for(author=account(created=years_before(RECENT, 5), karma=209)).tags


def test_plenty_of_karma_per_contribution_is_a_well_regarded_account():
    history = CommenterHistory(contributions=100)
    karma = int(config.WELL_REGARDED_KARMA_PER_CONTRIBUTION * 100)
    assert "well-regarded account" in voice_for(author=account(karma=karma), history=history).tags


def test_without_the_history_karma_per_year_of_account_age_stands_in():
    years = 4
    karma = int(config.WELL_REGARDED_KARMA_PER_YEAR * years) + 1
    assert "well-regarded account" in voice_for(author=account(created=years_before(RECENT, years), karma=karma)).tags
    assert "well-regarded account" not in voice_for(author=account(created=years_before(RECENT, years), karma=karma // 10)).tags


def test_negative_karma_is_low_karma_even_without_the_history():
    assert "low karma for its activity" in voice_for(author=account(created=years_before(RECENT, 3), karma=-40)).tags


def test_the_profiles_contributions_show_low_karma_for_its_activity():
    # From Arctic Shift (engine/profiles.py): the writer's own count of comments and posts, no history needed.
    writer = account(created=years_before(RECENT, 5), karma=209) | {"contributions": 450}
    voice = voice_for(author=writer)
    assert voice.level == "low"
    assert "low karma for its activity" in voice.tags
    assert "209 karma for 450 contributions" in voice.reasons


def test_the_profiles_contributions_show_a_well_regarded_account():
    karma = int(config.WELL_REGARDED_KARMA_PER_CONTRIBUTION * 100)
    assert "well-regarded account" in voice_for(author=account(karma=karma) | {"contributions": 100}).tags


def test_once_contributions_are_known_karma_per_year_no_longer_stands_in():
    # Plenty of karma a year, but only 3 karma per contribution: between the two lines, so neither sign.
    years = 1
    karma = int(config.WELL_REGARDED_KARMA_PER_YEAR * years) * 2
    contributions = int(karma / ((config.LOW_KARMA_PER_CONTRIBUTION + config.WELL_REGARDED_KARMA_PER_CONTRIBUTION) / 2))
    writer = account(created=years_before(RECENT, years), karma=karma)
    assert "well-regarded account" in voice_for(author=writer).tags  # unknown contributions: the fallback
    tags = voice_for(author=writer | {"contributions": contributions}).tags
    assert not {"well-regarded account", "low karma for its activity"} & set(tags)


def test_the_commenter_history_can_show_an_established_member():
    history = CommenterHistory(active_in_topic=True, usually_upvoted=True)
    voice = voice_for(author=account(created=years_before(RECENT, 5)), history=history)
    assert {"established member", "well-regarded account"} <= set(voice.tags)


# --- Independence ---

@pytest.mark.parametrize("pitch", [
    "Link in bio!", "DM me and I'll send you one.", "Use code SKIN15 at checkout.",
    "Here's my affiliate link: https://example.com/p/1", "https://www.amazon.com/dp/B000123?tag=skinfan-20",
])
def test_salesy_language_and_affiliate_links_are_red_flags(pitch):
    voice = voice_for(body=f"{USES_IT} {pitch}")
    assert "salesy language" in voice.tags
    assert voice.level == "low"


def test_an_honest_user_with_a_plain_shop_link_is_not_salesy():
    # Edge case from the brief: a link to a shop, with no affiliate code in it, is just being helpful.
    voice = voice_for(body=f"{USES_IT} I got mine here: https://www.amazon.com/dp/B000123")
    assert "salesy language" not in voice.tags


def test_a_brand_rep_who_discloses_promotes_one_brand():
    voice = voice_for(body="I'm a brand ambassador for them, but honestly " + USES_IT)
    assert "promotes one brand" in voice.tags
    assert voice.level == "low"


# --- Endorsement ---

def test_well_upvoted_is_relative_to_the_thread():
    # 6 points tops a quiet thread, but is nothing in a busy one.
    assert "well upvoted" in voice_for(score=6, others=(1, 1, 2, 2, 3)).tags
    assert "well upvoted" not in voice_for(score=6, others=(40, 85, 120, 2, 300)).tags


def test_a_tiny_score_is_not_well_upvoted_even_at_the_top_of_a_tiny_thread():
    assert "well upvoted" not in voice_for(score=config.WELL_UPVOTED_MIN_SCORE - 1, others=(0, 1, 1, 1)).tags


def test_a_downvoted_comment_is_a_red_flag():
    voice = voice_for(score=-4)
    assert voice.level == "low"
    # Changed on purpose 9 Oct 2026 (Noemi's decision 13): "downvoted" is now a voice tag of its own, not "other".
    assert "downvoted" in voice.tags and config.OTHER_TAG not in voice.tags
    assert any("downvoted" in reason for reason in voice.reasons)


def test_replies_that_agree_are_a_good_sign():
    comment, thread = make_case(replies=("This! Mine lasted 10 years too.",))
    agreement = ExtractedAgreement(comment_id="r0reply", quote="This!")
    voice = score_voice(comment, thread, agreements=[agreement])
    assert voice.level == "high"  # recent, and backed up by a reply
    assert any("1 reply agrees" in reason for reason in voice.reasons)
    # An agreement with some other comment is not about this one.
    assert score_voice(comment, thread, agreements=[ExtractedAgreement(comment_id="o0other", quote="x")]).level == "medium"


def test_replies_that_agree_are_recorded_under_their_own_tag():
    # Noemi's decision 13 (9 Oct 2026): "replies agree" is a voice tag of its own, no longer "other".
    comment, thread = make_case(replies=("This! Mine lasted 10 years too.",))
    voice = score_voice(comment, thread, agreements=[ExtractedAgreement(comment_id="r0reply", quote="This!")])
    assert "replies agree" in voice.tags and config.OTHER_TAG not in voice.tags


def test_the_two_new_voice_tags_come_after_the_others():
    assert config.VOICE_TAGS[-2:] == ("replies agree", "downvoted")
    assert len(set(config.VOICE_TAGS)) == len(config.VOICE_TAGS)


# Every red flag the rules can raise, each next to good signs worth more than enough for high: the comment is
# well upvoted, written by an old account with plenty of karma (established, well regarded), and recent.
RED_FLAGS = {
    "new account": {"author": account(created=years_before(RECENT, 0.01), karma=900_000)},
    "low karma for its activity": {"author": account(created=years_before(RECENT, 8), karma=-50)},
    "salesy language": {"body": USES_IT + " Use my code GLOW20 for 20% off!"},
    "promotes one brand": {"body": "I'm the founder, full disclosure. " + USES_IT},
    "downvoted": {"score": -2},
}


@pytest.mark.parametrize("flag", sorted(RED_FLAGS))
def test_a_red_flag_makes_the_voice_low_whatever_the_good_signs(flag):
    # The guide's rule, confirmed by Noemi on 9 Oct 2026 (decision 13): a red flag means a low voice.
    case = {"score": 9, "others": (1, 1, 2, 2), "author": account(created=years_before(RECENT, 8), karma=250_000)}
    case.update(RED_FLAGS[flag])
    voice = voice_for(**case)
    assert flag in voice.tags
    assert voice.level == "low"
    assert len(voice.good_signs) >= config.VOICE_HIGH_MIN_GOOD_SIGNS  # it would be high, but for the red flag


def test_without_its_red_flag_the_same_comment_is_high():
    voice = voice_for(score=9, others=(1, 1, 2, 2), author=account(created=years_before(RECENT, 8), karma=250_000))
    assert voice.level == "high" and voice.red_flags == ()


# --- Recency ---

def test_an_old_post_is_tagged_and_not_recent():
    voice = voice_for(created=years_before(COLLECTED + "T00:00:00Z", config.VOICE_RECENT_YEARS + 1))
    assert "old post" in voice.tags
    assert "recent" not in voice.tags


def test_an_old_skincare_post_can_be_at_most_the_capped_level():
    old = years_before(COLLECTED + "T00:00:00Z", config.VOICE_RECENT_YEARS + 2)
    rich = account(created="2010-01-01", karma=500_000, flair="Dermatologist")
    skincare = voice_for(created=old, author=rich, score=9, others=(1, 1, 2))
    kitchen = voice_for(created=old, author=rich, score=9, others=(1, 1, 2), category="kitchen")
    assert skincare.level == config.OLD_SKINCARE_POST_MAX_VOICE
    assert kitchen.level == "high"


# --- The text of the comment ---

def test_no_sign_of_use_is_a_red_flag_only_when_switched_on(monkeypatch):
    # The guide lists "no sign they've used anything" as a red flag; Noemi's labels never applied it, and the evidence
    # layer already scores it, so it is a switch (VOICE_RED_FLAG_NO_USE) for her to decide.
    monkeypatch.setattr(config, "VOICE_RED_FLAG_NO_USE", True)
    voice = voice_for(body="Try the CeraVe SA Cleanser.")
    assert voice.level == "low"
    assert any("no sign" in reason for reason in voice.reasons)
    monkeypatch.setattr(config, "VOICE_RED_FLAG_NO_USE", False)
    assert voice_for(body="Try the CeraVe SA Cleanser.").level == "medium"


def test_category_vocabulary_shows_an_enthusiast():
    body = "My gyuto in aogami steel takes a scary edge on a 1000 grit whetstone, and I've used it for years."
    assert "enthusiast" in voice_for(body=body, category="kitchen").tags
    assert "enthusiast" not in voice_for(category="kitchen").tags


def test_a_deleted_comment_is_low_with_nothing_to_go_on():
    comment, thread = make_case()
    gone = comment.model_copy(update={"status": "deleted", "body": "[deleted]", "author": None})
    assert score_voice(gone, thread).level == "low"


# --- Tuning: raising one weight moves things the expected way (the brief's weight-tuning test) ---

def test_raising_one_sign_weight_lifts_a_voice_with_that_sign(monkeypatch):
    assert voice_for().level == "medium"  # only "recent"
    monkeypatch.setitem(config.VOICE_SIGN_WEIGHTS, "recent", config.VOICE_HIGH_MIN_GOOD_SIGNS)
    assert voice_for().level == "high"


# --- Evidence: proof of use ---

def evidence_for(body: str, product: str = "Lodge skillet", stance: str = "recommend", others=(), created=RECENT) -> EvidenceScore:
    comment = Comment.model_validate(make_comment("c1aaaa", body=body, created_at=created))
    return score_evidence(comment, product, stance, other_products=others)


@pytest.mark.parametrize("body", [
    "I've had my Lodge skillet for 2 years and use it daily.",
    "Lodge skillet, owned it since 2019.",
    "We've cooked on a Lodge skillet for decades.",
    "My Lodge skillet is still going strong.",
    "Bought a Lodge skillet 12 months ago, no regrets.",
    "My Lodge skillet held up through everything.",
])
def test_long_term_use(body):
    evidence = evidence_for(body)
    assert evidence.level == "long-term use"
    assert "long-term use" in evidence.tags


def test_the_badge_says_how_long():
    assert "2 years of use" in evidence_for("I've had my Lodge skillet for 2 years.").reasons
    assert any("since 2019" in reason for reason in evidence_for("Lodge skillet, owned it since 2019.").reasons)


@pytest.mark.parametrize("body", [
    "Just bought a Lodge skillet, first impressions are good.",
    "I've been using the Lodge skillet for a few weeks.",
    "Had the Lodge skillet 6 months now.",  # under a year is not long-term
    "I use a Lodge skillet.",
    "I love my Lodge skillet.",
])
def test_short_term_use(body):
    evidence = evidence_for(body)
    assert evidence.level == "short-term use"
    assert "short-term use" in evidence.tags


def test_plain_use_with_nothing_concrete_is_vague():
    assert "vague" in evidence_for("I use a Lodge skillet.").tags
    assert "vague" not in evidence_for("I use a 12 inch Lodge skillet.").tags


@pytest.mark.parametrize("body", [
    "I've heard the Lodge skillet is great.",
    "Never tried the Lodge skillet myself.",
    "I haven't used a Lodge skillet, but it looks solid.",
    "Get the Lodge skillet.",
    "Lodge skillet",
])
def test_no_first_hand_use(body):
    assert evidence_for(body).level == "no first-hand use"


def test_someone_elses_experience_is_secondhand():
    evidence = evidence_for("My sister swears by her Lodge skillet.")
    assert evidence.level == "no first-hand use"
    assert "secondhand" in evidence.tags


def test_an_age_is_not_a_duration_of_use():
    assert evidence_for("I'm 35 years old and I like the Lodge skillet.").level == "short-term use"


def test_since_a_year_counts_from_when_the_comment_was_written():
    # "since 2025" in a comment from early 2026 is months, not years.
    assert evidence_for("Had my Lodge skillet since 2025.", created="2026-02-01T10:00:00Z").level == "short-term use"


def test_each_product_gets_its_own_sentences():
    body = "I've had my Lodge skillet for 10 years. Never tried Staub, but people rave about it."
    assert evidence_for(body, "Lodge skillet", others=("Staub",)).level == "long-term use"
    staub = evidence_for(body, "Staub", stance="neutral", others=("Lodge skillet",))
    assert staub.level == "no first-hand use"


def test_a_sentence_after_the_name_still_talks_about_it():
    body = "Lodge skillet. Mine has lasted 15 years and counting."
    assert evidence_for(body).level == "long-term use"


def test_a_reply_about_the_product_above_reads_the_whole_comment():
    # "had this one 13 years": the product is named in the comment above, not in this one.
    assert evidence_for("Had this one 13 years, still perfect.").level == "long-term use"


def test_a_question_about_it_is_tagged():
    evidence = evidence_for("Is the Lodge skillet any good?", stance="neutral")
    assert evidence.level == "no first-hand use"
    assert "asks about it" in evidence.tags


# --- Evidence: honesty ---

def test_mentions_flaws():
    evidence = evidence_for("I love my Lodge skillet, but it's really heavy and the handle gets hot.")
    assert "mentions flaws" in evidence.tags


def test_compares_alternatives_counts_the_other_products_named():
    evidence = evidence_for("I've used a Lodge skillet, a Victoria and a Staub.", others=("Victoria skillet", "Staub", "Lodge"))
    assert "compares alternatives" in evidence.tags
    assert "compares 2 alternatives" in evidence.reasons  # "Lodge" is this product again, not an alternative


def test_specific_details():
    for body in ("I use the 12 inch Lodge skillet at 450°F.", "Lodge skillet was $25 and I've used it a while.",
                 "My Lodge skillet cracked down the middle."):
        assert "specific details" in evidence_for(body).tags, body


def test_a_cheaper_alternative_is_tagged():
    assert "cheaper alternative" in evidence_for("The Lodge skillet is a cheaper alternative and I use it.").tags


def test_evidence_tags_are_all_evidence_tags():
    evidence = evidence_for("I love my Lodge skillet, but it's heavy. 12 inch, $25, had it 3 years.", others=("Staub",))
    assert set(evidence.tags) <= set(config.EVIDENCE_TAGS)


# --- The mention's weight: voice x evidence x stance ---

def scores(voice_level: str, evidence_level: str, evidence_tags: tuple[str, ...] = ()) -> tuple[VoiceScore, EvidenceScore]:
    return VoiceScore(level=voice_level, signs=()), EvidenceScore(level=evidence_level, tags=evidence_tags, reasons=())


def test_the_weight_is_voice_times_evidence_times_stance():
    voice, evidence = scores("high", "long-term use")
    expected = config.VOICE_VALUE["high"] * config.EVIDENCE_VALUE["long-term use"]
    assert mention_weight(voice, evidence, "recommend") == pytest.approx(expected)
    assert mention_weight(voice, evidence, "warn") == pytest.approx(-expected)
    assert mention_weight(voice, evidence, "neutral") == 0


def test_better_voice_and_evidence_weigh_more():
    weights = [mention_weight(*scores(v, e), "recommend") for v, e in (
        ("high", "long-term use"), ("medium", "long-term use"), ("medium", "short-term use"), ("low", "no first-hand use"),
    )]
    assert weights == sorted(weights, reverse=True)
    assert weights[-1] > 0  # even the weakest mention counts a little


def test_honesty_adds_a_little_but_never_beats_the_next_evidence_level():
    plain = mention_weight(*scores("high", "short-term use"), "recommend")
    honest = mention_weight(*scores("high", "short-term use", ("mentions flaws", "compares alternatives", "specific details")), "recommend")
    long_term = mention_weight(*scores("high", "long-term use"), "recommend")
    assert plain < honest < long_term


def test_raising_the_honesty_bonus_raises_honest_mentions(monkeypatch):
    voice, evidence = scores("medium", "short-term use", ("mentions flaws",))
    before = mention_weight(voice, evidence, "recommend")
    monkeypatch.setattr(config, "EVIDENCE_HONESTY_BONUS", config.EVIDENCE_HONESTY_BONUS + 0.1)
    assert mention_weight(voice, evidence, "recommend") > before


# --- Phrases that look like a sign but aren't ---

def test_a_frequency_is_not_a_time_of_use():
    assert evidence_for("Apply the Lodge skillet oil twice a day.").level == "no first-hand use"


def test_i_have_heard_is_hearsay_not_use():
    assert evidence_for("I have heard the Lodge skillet is great.").level == "no first-hand use"


def test_sticking_with_one_product_is_not_untried():
    assert evidence_for("Had my Lodge skillet 10 years and never used anything else.").level == "long-term use"


@pytest.mark.parametrize("body", [
    "I've used my Lodge skillet a lot, no issues at all.",
    "My Lodge skillet is low maintenance and doesn't rust.",
    "My Lodge skillet is hard to beat.",
])
def test_a_denied_or_positive_flaw_word_is_not_a_flaw(body):
    assert "mentions flaws" not in evidence_for(body).tags


def test_saying_it_is_not_sponsored_is_not_salesy():
    assert "salesy language" not in voice_for(body=USES_IT + " Not sponsored, no affiliate links.").tags


# --- Found on the gold set (9 Oct 2026): general patterns, each written as made-up cases ---

@pytest.mark.parametrize("body", ["The Lodge skillet is amazing!", "Lodge skillet is very nice, and so satisfying."])
def test_a_verdict_on_the_product_itself_is_use(body):
    # The guide: "it's amazing" is use with no time given, so "X is amazing" is too.
    assert evidence_for(body).level == "short-term use"


def test_an_effect_on_the_writer_is_first_hand():
    body = "Paula's Choice BHA. I wake up with glowy skin, and it never irritates me."
    assert evidence_for(body, "Paula's Choice BHA").level == "short-term use"


def test_a_brand_alone_doesnt_claim_a_sentence_about_its_more_specific_product():
    body = "The Ordinary has great acids. I like the Ordinary weekly peeling solution."
    toner = evidence_for(body, "The Ordinary glycolic toner", others=("The Ordinary weekly peeling solution",))
    peel = evidence_for(body, "The Ordinary weekly peeling solution", others=("The Ordinary glycolic toner",))
    assert toner.level == "no first-hand use"
    assert peel.level == "short-term use"


def test_someone_elses_first_time_is_not_a_fresh_start():
    assert evidence_for("If it's his first time with good pans, get a Lodge skillet.").level == "no first-hand use"
    assert evidence_for("First time using my Lodge skillet today.").level == "short-term use"


def test_a_link_on_its_own_line_belongs_to_the_sentence_before():
    body = "My Miyabi Santoku is a workhorse. For fish I ended up getting this:\n\nhttps://example.com/opinel-fillet-knife"
    assert evidence_for(body, "Opinel fillet knife", others=("Miyabi Santoku",)).level == "short-term use"


def test_a_plain_list_of_products_is_not_a_comparison():
    # The guide: "compares alternatives" names what they used before or instead, not just several products in a row.
    listed = evidence_for("Recs: Lodge skillet, Victoria skillet, Staub.", others=("Victoria skillet", "Staub"))
    assert "compares alternatives" not in listed.tags
    for body in ("I switched from Staub to a Lodge skillet.", "My Lodge skillet beats the Staub.",
                 "I prefer the Lodge skillet over Staub."):
        assert "compares alternatives" in evidence_for(body, others=("Staub",)).tags, body


def test_a_size_in_the_products_own_name_is_not_a_detail_the_writer_adds():
    named = evidence_for("Get the Lodge skillet 12 inch.", product="Lodge skillet 12 inch")
    assert "specific details" not in named.tags
    assert "vague" in named.tags
    assert "specific details" in evidence_for("Get the Lodge skillet 12 inch, it holds 450°F.", product="Lodge skillet 12 inch").tags


# --- Badges: "why this voice counts", for the answer (module 7's ScoredMention.badges) ---

def test_badges_say_why_a_voice_counts_and_nothing_against_it():
    comment, thread = make_case(
        body="I've had my Lodge skillet for 3 years, but it's heavy.", author=account(flair="Professional Chef"),
        score=9, others=(1, 1, 2), category="kitchen",
    )
    voice = score_voice(comment, thread)
    evidence = score_evidence(comment, "Lodge skillet", "recommend")
    shown = badges(voice, evidence)
    assert '3 years of use' in shown and "mentions flaws" in shown
    assert any("Professional Chef" in badge for badge in shown)
    assert any("points" in badge for badge in shown)  # well upvoted
    assert not any(badge.startswith("written") for badge in shown)  # every comment is recent: not a reason to show


def test_weak_evidence_and_red_flags_give_no_badges():
    comment, thread = make_case(body="Use my code SAVE10. Get the Lodge skillet.", author=None, category="kitchen")
    assert badges(score_voice(comment, thread), score_evidence(comment, "Lodge skillet", "recommend")) == ()


# --- A claim about how long things last is not the writer's own use (9 Oct 2026, first end-to-end run) ---

def test_how_long_a_kind_can_last_is_not_a_time_of_use():
    # "Carbon steel ... can all last 100+ years" is a claim about the material, and gave the badge "100 years of use".
    body = "Carbon steel, cast iron and copper cookware can all last 100+ years without much issues."
    evidence = evidence_for(body, "carbon steel pan")
    assert evidence.level != "long-term use"
    assert not any("years of use" in b for b in evidence.badges)


def test_how_long_the_writers_own_one_lasted_still_counts():
    assert evidence_for("My carbon steel pan has lasted 10 years.", "carbon steel pan").level == "long-term use"
    assert evidence_for("Our Zojirushi kettle is 8 years old and still going.", "Zojirushi kettle").level == "long-term use"
