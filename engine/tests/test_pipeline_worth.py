"""The pipeline's part in two additions of 13 Oct 2026 (Noemi's decisions 2 and 4).

"Also worth a look" keeps the picks' filters (they are applied before the ranking) and the brand rules: an item of the
brand of a brand-line pick is left out (the pick speaks for its brand's products), a brand line steps aside for its own
product, and an item whose brand is on the skip list is left out. One-line summaries are read from the library's
summaries.json, and the comments they cite are checked live like every shown quote.

Every library, product and summary here is made up; no test reads data/.
"""

import dataclasses
import json
from datetime import date

from engine import pipeline
from engine.answer import quotes_to_check, unverified_claims
from engine.pipeline import answer_request
from engine.query import parse_query
from engine.summaries import current_version
from engine.tests.ranking_factories import mention
from engine.tests.test_pick_polish import KNIFE_REQUEST, VICTORINOX, knife_library
from engine.tests.test_pipeline import REQUEST, FakeLive, library, praise, write_library

TODAY = date(2026, 10, 9)


def worth(result) -> list[str]:
    return [item.name for item in result.answer.worth_a_look]


def picks(result) -> list[str]:
    return [pick.name for pick in result.answer.picks]


def knives(tmp_path, *more: tuple[str, list, list]):
    """Two chef knife threads: the Mac and the Tojiro praised three times each (picks), the Misono twice, once in each."""
    first = [praise("m1a", "Mac Mighty chef knife", 7), praise("m1b", "Mac Mighty chef knife", 8),
             praise("t1a", "Tojiro DP gyuto", 5), praise("t1b", "Tojiro DP gyuto", 6),
             praise("u1a", "Misono UX10 gyuto", 4)]
    second = [praise("m2a", "Mac Mighty chef knife", 4), praise("t2a", "Tojiro DP gyuto", 3),
              praise("u2a", "Misono UX10 gyuto", 6)]
    for _, in_first, in_second in more:
        first += in_first
        second += in_second
    return write_library(tmp_path, {
        "1knif01": ("Best first chef knife?", "Budget about 100.", first),
        "1knif02": ("Which chef knife lasts?", "Mine chipped.", second),
    }, community="chefknives")


def test_also_worth_a_look_comes_through_the_pipeline(tmp_path):
    result = answer_request(KNIFE_REQUEST, library_dir=knives(tmp_path), prices=[], today=TODAY)
    assert picks(result) == ["Mac Mighty chef knife", "Tojiro DP gyuto"]
    assert worth(result) == ["Misono UX10 gyuto"]
    assert unverified_claims(result.answer, result.bodies) == []


def test_an_item_of_a_brand_line_pick_is_left_out(tmp_path):
    # The Victorinox line is a pick, and it speaks for the Fibrox (praised twice): listing the Fibrox apart would say
    # the same brand twice, once as less supported.
    result = answer_request(KNIFE_REQUEST, library_dir=knife_library(tmp_path, fibrox=(1, 1)), prices=[], today=TODAY)
    assert VICTORINOX in picks(result)
    assert "Victorinox Fibrox chef knife" in [p.name for p in result.ranking.worth_a_look]
    assert "Victorinox Fibrox chef knife" not in worth(result)


def test_a_brand_line_steps_aside_for_its_own_product_among_the_items(tmp_path):
    shun = ("shun",
            [praise("s1a", "Shun", 5), praise("s1b", "Shun Classic chef knife", 4),
             praise("s1c", "Shun Premier chef knife", 2)],
            [praise("s2a", "Shun", 6), praise("s2b", "Shun Classic chef knife", 3)])
    result = answer_request(KNIFE_REQUEST, library_dir=knives(tmp_path, shun), prices=[], today=TODAY)
    ranked = [p.name for p in result.ranking.worth_a_look]
    assert "Shun chef knife line" in ranked and "Shun Classic chef knife" in ranked
    assert "Shun Classic chef knife" in worth(result) and "Shun chef knife line" not in worth(result)


def test_an_item_whose_brand_is_on_the_skip_list_is_left_out(tmp_path):
    warn = lambda cid, product: (cid, product, f"My {product} chipped within a month, avoid it.", "warn")
    global_knives = ("global",
                     [warn("g1a", "Global"), warn("g1b", "Global"), praise("g1c", "Global G-2 chef knife", 4),
                      warn("g1d", "Global G-48 chef knife")],
                     [warn("g2a", "Global"), praise("g2b", "Global G-2 chef knife", 5)])
    result = answer_request(KNIFE_REQUEST, library_dir=knives(tmp_path, global_knives), prices=[], today=TODAY)
    assert "Global chef knife line" in [item.name for item in result.answer.skip]
    assert "Global G-2 chef knife" in [p.name for p in result.ranking.worth_a_look]
    assert "Global G-2 chef knife" not in worth(result)
    assert worth(result) == ["Misono UX10 gyuto"]


def test_in_a_wider_reading_an_item_needs_a_recommendation_about_the_requests_needs():
    # As for picks (11 Oct 2026): reading more threads had given every shampoo request the same popular products.
    query = parse_query("gentle exfoliant for sensitive skin")
    plain = [mention("Made-up Exfoliant", thread, category="skincare") for thread in ("t1", "t2")]
    fitting = [mention("Other Exfoliant", "t1", category="skincare"),
               mention("Other Exfoliant", "t2", category="skincare")]
    fitting[0] = dataclasses.replace(fitting[0], needs=("sensitive",))
    ranking = pipeline._ranked(plain + fitting, query, [], [], need_led=True)
    assert [p.name for p in ranking.worth_a_look] == ["Other Exfoliant"]
    assert {p.name for p in pipeline._ranked(plain + fitting, query, [], [], need_led=False).worth_a_look} == {
        "Made-up Exfoliant", "Other Exfoliant"}


# --- One-line summaries, read from the library ---

ZOJI = "kitchen:zojirushi kettle"


def write_summaries(library_dir, cites, text="Owners of 6 and 8 years say it still boils and keeps going.") -> None:
    (library_dir / "summaries.json").write_text(json.dumps({ZOJI: {
        "product": "Zojirushi kettle", "category": "kitchen", "product_type": "electric kettle", "text": text,
        "cites": list(cites), "written_at": "2026-10-13T10:00:00Z", "writer": "claude-code",
        "instructions_version": current_version()}}), encoding="utf-8")


def test_a_summary_in_the_library_is_shown_on_its_pick(tmp_path):
    lib = library(tmp_path)
    write_summaries(lib, ["k1aaaa", "k2aaaa"])
    result = answer_request(REQUEST, library_dir=lib)
    pick = result.answer.picks[0]
    assert pick.name == "Zojirushi kettle"
    assert pick.summary.text == "Owners of 6 and 8 years say it still boils and keeps going."
    assert [q.comment_id for q in pick.summary.sources] == ["k1aaaa", "k2aaaa"]
    assert unverified_claims(result.answer, result.bodies) == []


def test_no_summaries_file_means_no_summaries(tmp_path):
    result = answer_request(REQUEST, library_dir=library(tmp_path))
    assert result.answer.picks[0].summary is None


def test_a_broken_summaries_file_never_stops_an_answer(tmp_path):
    lib = library(tmp_path)
    (lib / "summaries.json").write_text("{not json", encoding="utf-8")
    result = answer_request(REQUEST, library_dir=lib)
    assert result.answer.picks[0].summary is None and result.answer.picks
    assert any("summaries.json" in problem for problem in result.skipped_files)


def test_a_summary_whose_number_no_cited_comment_gives_isnt_shown(tmp_path):
    lib = library(tmp_path)
    write_summaries(lib, ["k1aaaa", "k2aaaa"], text="Owners of 12 years say it still boils.")
    assert answer_request(REQUEST, library_dir=lib).answer.picks[0].summary is None


def test_the_comments_a_summary_cites_are_checked_live(tmp_path):
    lib = library(tmp_path)
    before = answer_request(REQUEST, library_dir=lib)
    shown = {q.comment_id for q in before.answer.picks[0].quotes}
    zoji = next(p for p in before.ranking.products if p.name == "Zojirushi kettle")
    unshown = next(m.comment_id for m in zoji.credible_recommendations if m.comment_id not in shown)
    write_summaries(lib, [unshown], text="Owners say it keeps going.")
    live = FakeLive()
    checked = answer_request(REQUEST, library_dir=lib, live_checker=live)
    assert checked.answer.picks[0].summary is not None
    assert any(url.rstrip("/").endswith(unshown) for url in live.asked)  # checked though its quote isn't shown
    assert {q.comment_id for q in quotes_to_check(checked.answer)} >= {unshown}
    gone = answer_request(REQUEST, library_dir=lib, live_checker=FakeLive(gone={unshown}))
    assert gone.answer.picks[0].summary is None  # deleted on Reddit since: it backs nothing now
    assert gone.live_dropped == {"gone": 1}
    assert unverified_claims(gone.answer, gone.bodies) == []


def test_summaries_can_be_given_instead_of_read(tmp_path):
    from engine.summaries import Summary

    entry = Summary(product="Zojirushi kettle", category="kitchen", product_type="electric kettle",
                    text="Owners of 6 years say it still boils.", cites=["k1aaaa"],
                    written_at="2026-10-13T10:00:00Z", writer="claude-code", instructions_version=current_version())
    result = answer_request(REQUEST, library_dir=library(tmp_path), summaries={ZOJI: entry})
    assert result.answer.picks[0].summary.text == "Owners of 6 years say it still boils."


def test_a_size_before_a_name_is_left_aside_but_never_a_brands_own_digits():
    assert pipeline._without_leading_size('10" Lodge cast iron') == "Lodge cast iron"
    assert pipeline._without_leading_size("12-inch Lodge") == "Lodge"
    assert pipeline._without_leading_size("1Zpresso JX") == "1Zpresso JX"
