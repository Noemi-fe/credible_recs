"""The two ranking changes of 9 Oct 2026, end to end through the pipeline (modules 1 to 7) on made-up libraries:
mentions that talk about the request's needs count more, and writers who contradict themselves count as low voices.

Every thread, writer and comment here is made up, written to a temporary folder; nothing reads data/.
"""

import json
from pathlib import Path

from engine import answer as wording
from engine.answer import answer_to_dict, unverified_claims
from engine.config import NEED_MATCH_BOOST
from engine.pipeline import answer_request
from engine.tests.factories import make_comment, make_thread, write_gold
from engine.tests.test_pipeline import REQUEST, ZOJI_1, ZOJI_2, ZOJI_3, ZOJI_4, comment, kettle_thread, mention, write_extractions

SENSITIVE_REQUEST = "retinol for sensitive skin"


def retinol_library(tmp_path: Path, rows: list[tuple[str, str, str, str]]) -> Path:
    """Two skincare threads asking for a retinol for sensitive skin. Each row is one comment: (comment id, product,
    stance, text); the text is also the quote. Comments starting with "r1" go in thread 1reti01, the others in 1reti02."""
    threads, extractions = {}, {}
    for comment_id, product, stance, body in rows:
        thread_id = "1reti01" if comment_id.startswith("r1") else "1reti02"
        threads.setdefault(thread_id, []).append(make_comment(comment_id, thread_id=thread_id, body=body))
        extractions.setdefault(thread_id, ([], []))[0].append(mention(comment_id, product, body, stance, "skincare"))
    root = write_gold(tmp_path / "library", [
        make_thread(id=tid, title="Which retinol for sensitive skin?", body="Looking for my first one.",
                    url=f"https://www.reddit.com/r/SkincareAddiction/comments/{tid}/retinol/", comments=comments)
        for tid, comments in threads.items()
    ], voices=None, mentions=None)
    write_extractions(root, extractions)
    return root


# Three equally credible recommendations of each retinol, across both threads: high voices, two years of use.
ALPHA = [("r1aaaa", "Alpha Retinol", "recommend", "I've used Alpha Retinol for 2 years, it works."),
         ("r1bbbb", "Alpha Retinol", "recommend", "Alpha Retinol every night for 2 years now."),
         ("r2aaaa", "Alpha Retinol", "recommend", "Two years on Alpha Retinol, no regrets.")]
BETA = [("r1cccc", "Beta Retinol", "recommend", "I've used Beta Retinol for 2 years, it works."),
        ("r1dddd", "Beta Retinol", "recommend", "Beta Retinol every night for 2 years now."),
        ("r2bbbb", "Beta Retinol", "recommend", "Two years on Beta Retinol, no regrets.")]
# The same as Beta's last one, but it talks about the request's need.
BETA_SENSITIVE = ("r2bbbb", "Beta Retinol", "recommend", "Two years on Beta Retinol with my sensitive skin, no regrets.")


def product(result, name):
    return next(p for p in result.ranking.products if p.name == name)


# --- Needs ---

def test_a_mention_that_talks_about_the_need_outranks_an_equally_credible_generic_one(tmp_path, monkeypatch):
    # Changed 9 Oct 2026: the boost is switched off by default (word rules made a real answer worse), so this test
    # sets it to test the mechanism itself.
    import engine.pipeline

    monkeypatch.setattr(engine.pipeline, "NEED_MATCH_BOOST", 1.5)
    generic = answer_request(SENSITIVE_REQUEST, library_dir=retinol_library(tmp_path / "a", ALPHA + BETA))
    assert [p.name for p in generic.answer.picks] == ["Alpha Retinol", "Beta Retinol"]  # a tie: by name

    fitting = answer_request(SENSITIVE_REQUEST, library_dir=retinol_library(tmp_path / "b", ALPHA + BETA[:2] + [BETA_SENSITIVE]))
    assert [p.name for p in fitting.answer.picks] == ["Beta Retinol", "Alpha Retinol"]
    beta, alpha = product(fitting, "Beta Retinol"), product(fitting, "Alpha Retinol")
    boosted = next(m for m in beta.mentions if m.comment_id == "r2bbbb")
    plain = next(m for m in alpha.mentions if m.comment_id == "r2aaaa")  # the same words, without the need
    assert boosted.needs == ("sensitive",) and plain.needs == ()
    assert boosted.weight == 1.5 * plain.weight
    assert beta.breakdown.credible_recommends_fitting_need == 1 and alpha.breakdown.credible_recommends_fitting_need == 0
    assert unverified_claims(fitting.answer, fitting.bodies) == []


def test_a_warning_that_talks_about_the_need_weighs_more(tmp_path):
    rows = ALPHA + BETA + [
        ("r2cccc", "Alpha Retinol", "warn", "I used Alpha Retinol for a month and it was way too harsh for my skin."),
        ("r2dddd", "Beta Retinol", "warn", "I used Beta Retinol for a month and it was way too harsh for my sensitive skin."),
    ]
    result = answer_request(SENSITIVE_REQUEST, library_dir=retinol_library(tmp_path, rows))
    alpha, beta = product(result, "Alpha Retinol"), product(result, "Beta Retinol")
    alpha_warning = next(m for m in alpha.mentions if m.stance == "warn")
    beta_warning = next(m for m in beta.mentions if m.stance == "warn")
    assert beta_warning.weight == NEED_MATCH_BOOST * alpha_warning.weight < 0
    assert beta.breakdown.credible_warnings_fitting_need == 1 and alpha.breakdown.credible_warnings_fitting_need == 0
    assert [p.name for p in result.answer.picks] == ["Alpha Retinol", "Beta Retinol"]


def test_the_reason_says_how_many_credible_voices_talk_about_the_need(tmp_path):
    rows = ALPHA + BETA[:1] + [
        ("r1dddd", "Beta Retinol", "recommend", "As a beginner I started with Beta Retinol 2 years ago, no irritation."),
        BETA_SENSITIVE,
    ]
    result = answer_request("retinol for a beginner with sensitive skin", library_dir=retinol_library(tmp_path, rows))
    beta = next(p for p in result.answer.picks if p.name == "Beta Retinol")
    alpha = next(p for p in result.answer.picks if p.name == "Alpha Retinol")
    assert beta.reason == "Recommended by 3 credible voices, 3 of them after long-term use, 2 of them about starting out or sensitive skin."
    assert alpha.reason == "Recommended by 3 credible voices, 3 of them after long-term use."
    text = result.text()
    assert beta.reason in text
    assert "About your request: 2 credible recommendations and 0 credible warnings talk about what you asked for" in text


def test_a_request_with_no_needs_changes_nothing(tmp_path):
    result = answer_request("retinol", library_dir=retinol_library(tmp_path, ALPHA + BETA[:2] + [BETA_SENSITIVE]))
    assert [p.name for p in result.answer.picks] == ["Alpha Retinol", "Beta Retinol"]
    assert all(not m.needs for p in result.ranking.products for m in p.mentions)
    assert "about" not in result.answer.picks[1].reason


# --- Writers who contradict themselves ---

FLIP = {"name": "Flip_Flopper", "account_created_at": "2018-06-01", "karma": 5000}


def kettle_library(tmp_path: Path, warning: str, author: dict | None = FLIP) -> Path:
    """The Zojirushi kettle praised by three writers across two threads; one of them (or a deleted account, with
    author=None) also writes `warning` about it in the second thread."""
    threads = [
        kettle_thread("1kett01", [comment("k1aaaa", "1kett01", ZOJI_1, author=author),
                                  comment("k1bbbb", "1kett01", ZOJI_2)]),
        kettle_thread("1kett02", [comment("k2aaaa", "1kett02", ZOJI_3), comment("k2bbbb", "1kett02", ZOJI_4),
                                  comment("k2cccc", "1kett02", warning, author=author)]),
    ]
    root = write_gold(tmp_path / "library", threads, voices=None, mentions=None)
    write_extractions(root, {
        "1kett01": ([mention("k1aaaa", "Zojirushi kettle", ZOJI_1), mention("k1bbbb", "Zojirushi kettle", ZOJI_2)], []),
        "1kett02": ([mention("k2aaaa", "Zojirushi kettle", ZOJI_3), mention("k2bbbb", "Zojirushi kettle", ZOJI_4),
                     mention("k2cccc", "Zojirushi kettle", warning, "warn")], []),
    })
    return root


def test_a_writer_who_contradicts_themselves_becomes_a_low_voice_and_loses_credible_status(tmp_path):
    warning = "The Zojirushi kettle is overrated, avoid it."
    trusted = answer_request(REQUEST, library_dir=kettle_library(tmp_path / "a", warning, author=None))
    assert trusted.contradicting_writers == []  # deleted accounts never match each other
    assert product(trusted, "Zojirushi kettle").breakdown.credible_recommends == 4

    result = answer_request(REQUEST, library_dir=kettle_library(tmp_path / "b", warning))
    assert result.contradicting_writers == ["flip_flopper"]
    zoji = product(result, "Zojirushi kettle")
    theirs = [m for m in zoji.mentions if m.author == "flip_flopper"]
    assert theirs and all(m.voice == "low" for m in theirs)
    assert zoji.breakdown.credible_recommends == 3  # their recommendation no longer counts towards the rule
    assert zoji.breakdown.credible_warnings == 0
    # Their other mention's weight is worked out again with the low voice value.
    assert zoji.score < product(trusted, "Zojirushi kettle").score
    # Nothing about it is shown: not their name, not the warning.
    shown = result.text() + json.dumps(answer_to_dict(result.answer))
    assert "flip_flopper" not in shown.lower() and "overrated" not in shown


def test_a_writer_who_reports_an_update_is_not_contradicting_themselves(tmp_path):
    warning = "Update: my Zojirushi kettle stopped working last month, so avoid it."
    result = answer_request(REQUEST, library_dir=kettle_library(tmp_path, warning))
    assert result.contradicting_writers == []
    zoji = product(result, "Zojirushi kettle")
    assert all(m.voice != "low" for m in zoji.mentions)
    assert zoji.breakdown.credible_recommends == 4  # their recommendation still counts


def test_contradicting_writers_are_counted_in_the_end_to_end_report(tmp_path):
    from engine.slice_eval import score_questions, slice_lines

    path = tmp_path / "questions.json"
    path.write_text(json.dumps({"questions": [{"id": "b01", "text": REQUEST}]}), encoding="utf-8")
    lines = slice_lines(score_questions(path, kettle_library(tmp_path, "The Zojirushi kettle is overrated, avoid it.")))
    assert "1 writer contradicting themselves" in lines[1]
    assert "flip_flopper" not in "\n".join(lines).lower()  # names stay internal


def test_the_wording_added_is_in_the_answers_wording_block():
    assert wording.REASON_NEEDS == ", {n} of them about {needs}"
    assert wording.NEED_LABELS["sensitive"] == "sensitive skin" and wording.NEED_LABELS["beginner"] == "starting out"


def test_the_web_page_gets_the_same_breakdown_line_with_its_numbers_left_to_fill():
    from engine.web import search_page

    html = search_page().decode("utf-8")
    line = json.loads(html.split('<script type="application/json" id="settings">')[1].split("</script>")[0])["wording"]["breakdown_needs"]
    assert line == ("About your request: {recommends} credible recommendations and {warnings} credible warnings talk "
                    f"about what you asked for (each counts {NEED_MATCH_BOOST:g} times as much)")
    assert "b.credible_recommends_fitting_need" in html  # the page shows it when some credible mention fits


# --- The reason's wording, from made-up ranked mentions (engine/tests/ranking_factories.py) ---

def test_needs_are_named_once_each_in_the_requests_order_and_unlisted_ones_as_typed():
    import dataclasses

    from engine.answer import write_answer
    from engine.rank import rank_products
    from engine.tests.ranking_factories import bodies_for, mentions

    knives = mentions(4, "Tojiro DP Gyuto", threads=("t1", "t2"))
    with_needs = [dataclasses.replace(knives[0], needs=("home cook",)),
                  dataclasses.replace(knives[1], needs=("beginner", "home cook")),
                  dataclasses.replace(knives[2], needs=("pour-over",))] + knives[3:]
    pick = write_answer(rank_products(with_needs, "kitchen"), bodies_for(*with_needs)).picks[0]
    assert pick.reason == ("Recommended by 4 credible voices, 4 of them after long-term use, "
                           "3 of them about starting out, home cooking or pour-over.")
    assert pick.breakdown.credible_recommends_fitting_need == 3


def test_the_reason_doesnt_count_long_use_twice(tmp_path):
    # "Lasts 10+ years": long-term use talks about lasting, but the reason already says "after long-term use".
    from engine.tests.test_pipeline import library

    result = answer_request(REQUEST, library_dir=library(tmp_path))
    zoji = result.answer.picks[0]
    assert zoji.reason == "Recommended by 4 credible voices, 4 of them after long-term use."
    assert zoji.breakdown.credible_recommends_fitting_need == 4  # the breakdown still counts them: they weigh more


def test_a_need_typed_as_a_verb_gets_words_that_read_well():
    # Found reading the answers, 10 Oct 2026: "won't strip my skin" read "3 of them about gentleness or strip".
    from engine import answer as wording

    assert wording.NEED_LABELS["strip"] == "not stripping the skin"
