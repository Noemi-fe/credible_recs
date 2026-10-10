"""Scoring module 5 (credibility) against Noemi's labels: voice levels per comment, evidence levels per product.

Everything is made up: threads from factories.py, labels as VoiceLabel and MentionLabel rows. No test reads data/.
"""

from engine import credibility_eval
from engine.credibility_eval import (
    LevelAgreement,
    credibility_report,
    report_lines,
    score_credibility,
)
from engine.extract import CheckResult, ExtractedAgreement, ExtractedMention
from engine.gold import GoldSet
from engine.models import MentionLabel, Thread, VoiceLabel
from engine.profiles import ProfileStore, StoredProfiles
from engine.tests.factories import MENTIONS_HEADER, VOICES_HEADER, make_comment, make_thread, write_gold

# The made-up thread 1fake01 (factories.make_thread). Its writers have old accounts with 5,000 karma, and wrote in
# 2025 (recent when it was collected in 2026), so the rules call c1aaaa and c3cccc high: established and recent.
#   c1aaaa: two years of the CeraVe SA Cleanser, dries out in winter -> long-term use, mentions flaws
#   c2bbbb: "Same here", no product -> no voice level
#   c3cccc: Paula's Choice 2% BHA beats every acid toner "I've tried" -> short-term use (the 2% is its name, not a detail)
THREAD = Thread.model_validate(make_thread())


def other_thread(thread_id: str = "1fake02") -> Thread:
    return Thread.model_validate(make_thread(
        id=thread_id,
        url=f"https://www.reddit.com/r/SkincareAddiction/comments/{thread_id}/post/",
        comments=[make_comment(f"{thread_id}c1", thread_id=thread_id, body="I've used the La Roche-Posay sunscreen for years.")],
    ))


def voice(comment_id: str, level: str | None, tags: str | None, thread_id: str = "1fake01") -> VoiceLabel:
    return VoiceLabel(thread_id=thread_id, comment_id=comment_id, voice=level, tags=tags)


def mention(comment_id: str, product: str, evidence: str, tags: str, kind: bool = False) -> MentionLabel:
    return MentionLabel(comment_id=comment_id, product=product, category="skincare", stance="recommend",
                        evidence=evidence, tags=tags, kind=kind)


VOICES = [
    voice("c1aaaa", "high", "established member, recent"),
    voice("c2bbbb", None, None),  # no product: no voice to compare
    voice("c3cccc", "low", "salesy language"),  # the rules say high: a swap
]
MENTIONS = [
    mention("c1aaaa", "CeraVe SA Cleanser", "long-term use", "long-term use, mentions flaws"),
    mention("c3cccc", "Paula's Choice 2% BHA", "short-term use", "short-term use, specific details"),
    mention("c3cccc", "chemical exfoliant", "no first-hand use", "vague", kind=True),  # a kind of product: skipped
]


def gold(voices=VOICES, mentions=MENTIONS, threads=(THREAD,)) -> GoldSet:
    return GoldSet(threads=list(threads), voices=list(voices), mentions=list(mentions))


# --- Counting agreement ---

def test_exact_agreement_swaps_and_extremes():
    agreement = LevelAgreement(("high", "medium", "low"), [
        ("c1", "high", "low"),  # swap
        ("c2", "low", "high"),  # swap
        ("c3", "high", "medium"),  # her extreme, not matched, not swapped
        ("c4", "medium", "low"),  # not an extreme of hers
        ("c5", "low", "low"),  # exact
    ])
    assert agreement.total == 5
    assert agreement.exact == 1
    assert agreement.extremes == 4  # her high and low labels
    assert agreement.swaps == 2
    assert agreement.not_swapped == 2
    assert agreement.same_extreme == 1


def test_the_confusion_table_and_the_split():
    agreement = LevelAgreement(("high", "medium", "low"), [("c1", "high", "medium"), ("c2", "high", "medium"), ("c3", "low", "low")])
    assert agreement.confusion()[("high", "medium")] == 2
    assert agreement.confusion()[("low", "low")] == 1
    assert agreement.confusion()[("medium", "high")] == 0
    assert agreement.split("hers") == {"high": 2, "medium": 0, "low": 1}
    assert agreement.split("rules") == {"high": 0, "medium": 2, "low": 1}


# --- Scoring the gold set ---

def test_voice_is_compared_on_comments_with_a_voice_level():
    score = score_credibility(gold())
    assert score.voice.pairs == [("c1aaaa", "high", "high"), ("c3cccc", "low", "high")]
    assert (score.voice.exact, score.voice.swaps) == (1, 1)


def test_copied_text_is_looked_for_once_per_thread(monkeypatch):
    # Module 5's "copied text" red flag (Noemi's decision 3, 11 Oct 2026) compares a whole thread: it is worked out once
    # per thread scored, not once per labelled comment (this thread has two).
    looked_at = []
    real = credibility_eval.copied_comment_ids
    monkeypatch.setattr(credibility_eval, "copied_comment_ids", lambda thread: looked_at.append(thread.id) or real(thread))
    score_credibility(gold())
    assert looked_at == ["1fake01"]


def test_evidence_is_compared_on_products_not_kinds():
    score = score_credibility(gold())
    assert score.evidence.pairs == [("c1aaaa", "long-term use", "long-term use"), ("c3cccc", "short-term use", "short-term use")]


def test_tags_are_counted_for_her_the_rules_and_both():
    score = score_credibility(gold())
    assert score.voice_tags.hers["recent"] == 1
    assert score.voice_tags.rules["recent"] == 2
    assert score.voice_tags.both["recent"] == 1
    assert score.evidence_tags.both["mentions flaws"] == 1
    assert score.evidence_tags.both["short-term use"] == 1
    assert score.evidence_tags.hers["specific details"] == 1 and score.evidence_tags.rules["specific details"] == 0


def test_a_held_out_thread_is_never_scored():
    second = other_thread()
    voices = VOICES + [voice("1fake02c1", "high", "recent", thread_id="1fake02")]
    mentions = MENTIONS + [mention("1fake02c1", "La Roche-Posay sunscreen", "long-term use", "long-term use")]
    score = score_credibility(gold(voices, mentions, (THREAD, second)), skip_threads=("1fake02",))
    assert "1fake02c1" not in {comment_id for comment_id, _, _ in score.voice.pairs + score.evidence.pairs}
    assert score.threads == ["1fake01"]
    assert score.held_out == ["1fake02"]


def test_replies_that_agree_come_from_the_extraction():
    # c2bbbb agrees with c1aaaa. With it, c1aaaa has three good signs instead of two: still high, now with the reason.
    checked = {"1fake01": CheckResult(kept_agreements=[ExtractedAgreement(comment_id="c2bbbb", quote="Same here")])}
    score = score_credibility(gold(), checked)
    # Changed on purpose 9 Oct 2026 (Noemi's decision 13): recorded under its own tag, no longer "other".
    assert score.voice_tags.rules["replies agree"] == 1 and score.voice_tags.rules["other"] == 0
    assert score.agreements_used == 1


# --- The report ---

def test_the_report_shows_counts_levels_and_ids_never_comment_text():
    text = "\n".join(report_lines(score_credibility(gold())))
    assert "c3cccc" in text  # the swap is listed
    assert "1/2" in text  # voice: one of her two extremes not swapped, one of two exact
    for comment in THREAD.comments:
        for sentence in comment.body.split(". "):
            assert sentence.strip(".") not in text
    assert "Paula" not in text and "CeraVe" not in text  # no product names either


def test_credibility_report_reads_a_gold_folder(tmp_path):
    voices = VOICES_HEADER + "1fake01,c1aaaa,high,\"established member, recent\",\n1fake01,c2bbbb,,,\n"
    mentions = MENTIONS_HEADER + "c1aaaa,CeraVe SA Cleanser,skincare,recommend,long-term use,long-term use,\n"
    write_gold(tmp_path, [make_thread()], voices, mentions)
    report = credibility_report(tmp_path)
    assert report.startswith("Module 5")
    assert "1/1" in report


def test_credibility_report_says_what_is_wrong_with_a_broken_gold_set(tmp_path):
    write_gold(tmp_path, [make_thread()], voices="thread_id,comment_id\n")
    report = credibility_report(tmp_path)
    assert report.startswith("Module 5")
    assert "voices.csv" in report


# --- The AI's own evidence level (instructions v6, 9 Oct 2026) against hers, next to the rules' ---

def ai(comment_id: str, product: str, evidence: str | None = None) -> ExtractedMention:
    """One of the AI's kept mentions; with `evidence`, as instructions v6 write it. The quote isn't scored here."""
    tags = [evidence] if evidence in ("long-term use", "short-term use") else ["vague"] if evidence else []
    return ExtractedMention(comment_id=comment_id, product=product, category="skincare", stance="recommend",
                            quote="a quote", evidence=evidence, evidence_tags=tags)


def test_the_ais_evidence_is_compared_with_hers_on_the_products_both_found():
    # Her labels: CeraVe long-term use, Paula's short-term use. The AI names CeraVe differently and swaps it to none.
    checked = {"1fake01": CheckResult(kept=[ai("c1aaaa", "CeraVe Renewing SA Cleanser", "no first-hand use"),
                                            ai("c3cccc", "Paula's Choice 2% BHA", "short-term use"),
                                            ai("c3cccc", "The Ordinary AHA", "short-term use")])}  # not hers: unpaired
    score = score_credibility(gold(), checked)
    assert score.ai_evidence.pairs == [("c1aaaa", "long-term use", "no first-hand use"), ("c3cccc", "short-term use", "short-term use")]
    assert (score.ai_evidence.exact, score.ai_evidence.swaps) == (1, 1)
    # The rules on the very same products, so the two compare on equal terms.
    assert score.rules_on_ai_matched.pairs == [("c1aaaa", "long-term use", "long-term use"), ("c3cccc", "short-term use", "short-term use")]


def test_ai_mentions_without_evidence_are_not_compared():
    # Extractions made before instructions v6 have no evidence level.
    checked = {"1fake01": CheckResult(kept=[ai("c1aaaa", "CeraVe SA Cleanser"), ai("c3cccc", "Paula's Choice 2% BHA")])}
    score = score_credibility(gold(), checked)
    assert score.ai_evidence.total == 0 and score.rules_on_ai_matched.total == 0


def test_a_held_out_thread_counts_for_the_ai_only():
    # The kettle thread is the fair test of v6 (Noemi's decision 2): the AI is scored there, the rules still aren't.
    second = other_thread()
    voices = VOICES + [voice("1fake02c1", "high", "recent", thread_id="1fake02")]
    mentions = MENTIONS + [mention("1fake02c1", "La Roche-Posay sunscreen", "long-term use", "long-term use")]
    checked = {"1fake02": CheckResult(kept=[ai("1fake02c1", "La Roche-Posay sunscreen", "long-term use")])}
    score = score_credibility(gold(voices, mentions, (THREAD, second)), checked, skip_threads=("1fake02",))
    assert score.ai_evidence_held_out.pairs == [("1fake02c1", "long-term use", "long-term use")]
    assert score.ai_evidence.total == 0
    assert "1fake02c1" not in {comment_id for comment_id, _, _ in score.evidence.pairs + score.rules_on_ai_matched.pairs}


def test_the_report_says_when_there_are_no_v6_extractions_yet():
    lines = report_lines(score_credibility(gold()))
    rules_line = next(i for i, line in enumerate(lines) if line.startswith("evidence:"))
    assert "no v6 extractions yet" in lines[rules_line + 1]


def test_the_report_puts_the_ais_evidence_line_under_the_rules_line():
    checked = {"1fake01": CheckResult(kept=[ai("c1aaaa", "CeraVe SA Cleanser", "no first-hand use"),
                                            ai("c3cccc", "Paula's Choice 2% BHA", "short-term use")])}
    lines = report_lines(score_credibility(gold(), checked))
    rules_line = next(i for i, line in enumerate(lines) if line.startswith("evidence:"))
    ai_line = lines[rules_line + 1]
    # Of her two labels only CeraVe's is at an end (long-term use): the AI swapped it to no first-hand use.
    assert "AI" in ai_line and "exact 1/2 (50%)" in ai_line and "swaps 1 of 1" in ai_line  # the AI
    assert "rules on the same 2: exact 2/2 (100%)" in ai_line and "swaps 0 of 1" in ai_line  # the rules, same two
    assert "Paula" not in "\n".join(lines) and "CeraVe" not in "\n".join(lines)  # still no product names


def test_the_report_shows_the_ai_on_a_held_out_thread_without_the_rules():
    second = other_thread()
    voices = VOICES + [voice("1fake02c1", "high", "recent", thread_id="1fake02")]
    mentions = MENTIONS + [mention("1fake02c1", "La Roche-Posay sunscreen", "long-term use", "long-term use")]
    checked = {"1fake02": CheckResult(kept=[ai("1fake02c1", "La Roche-Posay sunscreen", "short-term use")])}
    lines = report_lines(score_credibility(gold(voices, mentions, (THREAD, second)), checked, skip_threads=("1fake02",)))
    held_out = [line for line in lines if "held-out" in line and "AI" in line]
    assert len(held_out) == 1 and "exact 0/1 (0%)" in held_out[0] and "rules on the same" not in held_out[0]


# --- Writers' profiles from the cache (9 Oct 2026): does profile data close the voice gap? ---

class LongStanding:
    """Profiles as Arctic Shift would give them: every writer active since 2014, with plenty of karma per contribution."""

    def user_stats(self, author):
        return {"num_comments": 2000, "num_posts": 20, "total_karma": 30000, "earliest_comment_at": 1400000000}

    def comment_flairs(self, comment_ids):
        return {}


def test_profiles_fill_in_plain_writers_before_the_rules_judge_them():
    # Parse saves writers by name only, so the rules can't see standing; with profiles they can.
    plain = Thread.model_validate(make_thread(comments=[
        make_comment(c["id"], body=c["body"], parent_id=c["parent_id"], author={"name": f"writer_{c['id']}"})
        for c in make_thread()["comments"]]))
    level = lambda score, cid: next(rules for c, _, rules in score.voice.pairs if c == cid)
    assert level(score_credibility(gold(threads=(plain,))), "c1aaaa") == "medium"  # only "recent" to go on
    assert level(score_credibility(gold(threads=(plain,)), profiles=LongStanding()), "c1aaaa") == "high"


# --- The report judges writers with their profiles, as answers do (10 Oct 2026) ---
# Gold threads are saved by name only, so without profiles the rules could never call anyone "established member" or
# "well-regarded account", while answers (engine.pipeline) fill writers in from the library's profile store first.

def plain_thread() -> dict:
    """make_thread's thread with every writer known by name only, as Parse saves them."""
    thread = make_thread()
    thread["comments"] = [c | {"author": {"name": f"writer_{c['id']}"}} for c in thread["comments"]]
    return thread


PLAIN_VOICES = VOICES_HEADER + '1fake01,c1aaaa,high,"established member, well-regarded account",\n1fake01,c2bbbb,,,\n'


def test_the_report_judges_writers_with_their_profiles_when_given_them(tmp_path):
    write_gold(tmp_path, [plain_thread()], PLAIN_VOICES)
    assert "exact 0/1 (0%)" in credibility_report(tmp_path)  # medium: only "recent" to go on
    report = credibility_report(tmp_path, profiles=LongStanding())
    assert "exact 1/1 (100%)" in report
    assert "established member 1/1/1" in report and "well-regarded account 1/1/1" in report


def test_the_report_says_how_many_labelled_writers_had_a_profile(tmp_path):
    write_gold(tmp_path, [plain_thread()], PLAIN_VOICES)
    assert "writers' profiles: not looked up" in credibility_report(tmp_path)
    assert "writers' profiles: 1 of 1 labelled writer found" in credibility_report(tmp_path, profiles=LongStanding())


def test_the_report_still_works_when_the_library_has_no_profile_store(tmp_path):
    write_gold(tmp_path / "gold", [plain_thread()], PLAIN_VOICES)
    no_store = StoredProfiles(ProfileStore(tmp_path / "library" / "profiles.json"))  # no such file
    report = credibility_report(tmp_path / "gold", profiles=no_store)
    assert "exact 0/1 (0%)" in report
    assert "writers' profiles: 0 of 1 labelled writer found" in report


def test_writers_are_counted_once_per_thread_and_deleted_accounts_are_not_writers():
    thread = make_thread(comments=[
        make_comment("c1aaaa", author={"name": "same_writer"}, body="I've used the CeraVe SA Cleanser for 2 years."),
        make_comment("c3cccc", author={"name": "same_writer"}, body="Paula's Choice 2% BHA is great."),
        make_comment("c4dddd", author=None, body="The Ordinary AHA is fine."),
    ])
    voices = [voice("c1aaaa", "high", "recent"), voice("c3cccc", "medium", "recent"), voice("c4dddd", "medium", "recent")]
    score = score_credibility(gold(voices, [], (Thread.model_validate(thread),)), profiles=LongStanding())
    assert (score.writers, score.writers_profiled) == (1, 1)


def test_the_section_gives_the_printed_text_and_the_score_it_came_from(tmp_path):
    from engine.credibility_eval import credibility_section

    voices = VOICES_HEADER + "1fake01,c1aaaa,high,\"established member, recent\",\n1fake01,c2bbbb,,,\n"
    mentions = MENTIONS_HEADER + "c1aaaa,CeraVe SA Cleanser,skincare,recommend,long-term use,long-term use,\n"
    write_gold(tmp_path, [make_thread()], voices, mentions)
    text, score = credibility_section(tmp_path)
    assert text == credibility_report(tmp_path)
    assert (score.voice.not_swapped, score.voice.extremes) == (1, 1)
    assert "(target 80%)" in text


def test_the_section_gives_no_score_for_a_broken_gold_set(tmp_path):
    from engine.credibility_eval import credibility_section

    write_gold(tmp_path, [make_thread()], voices="thread_id,comment_id\n")
    text, score = credibility_section(tmp_path)
    assert score is None and "voices.csv" in text
