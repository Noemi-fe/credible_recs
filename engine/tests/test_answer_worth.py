"""Module 7, two additions of 13 Oct 2026 (Noemi's decisions 2 and 4):

- "Also worth a look": up to WORTH_A_LOOK_SHOWN products with two credible recommendations across two threads, shown
  apart after the picks, labelled as less supported, each with one or two verified quotes; never a pick.
- One-line summaries: a pick's (or item's) summary from data/library/summaries.json, shown as "In short:" only when
  every check passes, with the verified quotes of the comments it cites.

All data is made up (engine/tests/ranking_factories.py).
"""

import dataclasses
import json
from datetime import date

from engine import answer as wording
from engine import config
from engine.answer import answer_to_dict, quotes_to_check, render_markdown, shown_quotes, unverified_claims, write_answer
from engine.config import WORTH_A_LOOK_QUOTES, WORTH_A_LOOK_SHOWN
from engine.prices import Price, PriceCheck
from engine.rank import rank_products
from engine.summaries import Summary, current_version
from engine.tests.ranking_factories import bodies_for, mention, mentions


def case(extra=()):
    """One pick (the Tojiro), four products with two credible recommendations across two threads (scores 2.0, 1.2, 0.72
    and 0.6, in that order), and `extra`."""
    items = (
        mentions(3, "Tojiro DP Gyuto")
        + mentions(2, "Misono UX10", quote=None)
        + mentions(2, "Sakai Takayuki", voice="medium")
        + mentions(2, "Masamoto VG", voice="medium", evidence="short-term use")
        + mentions(2, "Mac Pro", voice="medium", evidence="short-term use", weight=0.3, badges=())
        + list(extra)
    )
    return rank_products(items, "kitchen"), bodies_for(*items), items


def names(items) -> list[str]:
    return [item.name for item in items]


# --- Also worth a look ---

def test_also_worth_a_look_comes_after_the_picks_and_never_among_them():
    ranking, bodies, _ = case()
    answer = write_answer(ranking, bodies, "chef knife")
    assert names(answer.picks) == ["Tojiro DP Gyuto"]
    assert names(answer.worth_a_look) == ["Misono UX10", "Sakai Takayuki", "Masamoto VG"]  # ranked, at most 3
    assert len(answer.worth_a_look) == WORTH_A_LOOK_SHOWN
    for item in answer.worth_a_look:
        assert 1 <= len(item.quotes) <= WORTH_A_LOOK_QUOTES
        assert all(q.text in bodies[q.comment_id] for q in item.quotes)
    assert unverified_claims(answer, bodies) == []


def test_its_note_says_plainly_that_it_is_less_supported(monkeypatch):
    # The upvote rule is on since 14 Oct 2026 and adds its own clause to the bar; this test is about the plain bar.
    monkeypatch.setattr(config, "UPVOTE_COUNTS_MORE", False)
    ranking, bodies, _ = case()
    answer = write_answer(ranking, bodies, "chef knife")
    assert answer.worth_note == ("2 credible voices each: less evidence than the picks above, which need at least 3 "
                                 "credible recommendations across at least 2 threads.")
    assert answer.worth_a_look[0].reason == "Recommended by 2 credible voices, 2 of them after long-term use."


def test_with_no_picks_the_note_doesnt_point_at_picks_above(monkeypatch):
    # The upvote rule is on since 14 Oct 2026 and adds its own clause to the bar; this test is about the plain bar.
    monkeypatch.setattr(config, "UPVOTE_COUNTS_MORE", False)
    ranking, bodies, _ = case()
    ranking.products = [p for p in ranking.products if p.name != "Tojiro DP Gyuto"]
    answer = write_answer(ranking, bodies, "chef knife")
    assert answer.picks == [] and answer.message  # the honest message stays
    assert answer.worth_note == ("2 credible voices each: less evidence than a pick needs (at least 3 credible "
                                 "recommendations across at least 2 threads).")


def test_no_items_no_note():
    ranking, bodies, _ = case()
    ranking.products = [p for p in ranking.products if not p.worth_a_look]
    answer = write_answer(ranking, bodies, "chef knife")
    assert answer.worth_a_look == [] and answer.worth_note is None
    assert wording.WORTH_HEADING not in render_markdown(answer)


def test_an_item_whose_quotes_all_fail_gives_its_place_to_the_next():
    ranking, bodies, items = case()
    for m in items:
        if m.product_name == "Misono UX10":
            bodies[m.comment_id] = "This comment was edited since and says something else now."
    answer = write_answer(ranking, bodies, "chef knife")
    assert names(answer.worth_a_look) == ["Sakai Takayuki", "Masamoto VG", "Mac Pro"]


def test_an_item_shows_only_quotes_that_say_something():
    # Unlike a pick, an item has no minimum of two to make up: a bare mention or a garbled quote is never shown.
    bare = [mention("Wusthof Ikon", t, quote="I have a Wusthof.") for t in ("t1", "t2")]
    ranking, bodies, _ = case(bare)
    answer = write_answer(ranking, bodies, "chef knife")
    assert "Wusthof Ikon" not in names(answer.worth_a_look)


def test_items_named_by_the_pipeline_are_left_out():
    ranking, bodies, _ = case()
    answer = write_answer(ranking, bodies, "chef knife", worth_left_out={"misono-ux10"})
    assert names(answer.worth_a_look) == ["Sakai Takayuki", "Masamoto VG", "Mac Pro"]


def test_an_item_shows_downsides_only_when_credible_voices_warn():
    warning = mention("Sakai Takayuki", "t1", stance="warn", voice="medium", evidence="short-term use",
                      quote="The Sakai Takayuki chipped in its first month.")
    ranking, bodies, _ = case([warning])
    answer = write_answer(ranking, bodies, "chef knife")
    by_name = {item.name: item for item in answer.worth_a_look}
    assert [q.text for q in by_name["Sakai Takayuki"].downsides] == ["The Sakai Takayuki chipped in its first month."]
    assert by_name["Sakai Takayuki"].downsides_share == "1 of 3 credible voices warned against it:"
    assert by_name["Misono UX10"].downsides == [] and by_name["Misono UX10"].downsides_share is None
    text = render_markdown(answer)
    assert "chipped in its first month" in text
    assert text.count(wording.DOWNSIDES_HEADING) == 1 + 1  # the pick's, and the warned item's only


def test_an_item_carries_its_price_and_cautions():
    price = Price(product="Misono UX10", category="kitchen", price=150.0, currency="GBP", shop="Made-up Knife Shop",
                  url="https://shop.example/misono", checked_on=date(2026, 10, 9))
    ranking, bodies, _ = case()
    answer = write_answer(ranking, bodies, "chef knife", prices={"misono-ux10": PriceCheck(price, "no budget")},
                          cautions={"misono-ux10": ["we couldn't confirm it's dishwasher-safe"]})
    item = answer.worth_a_look[0]
    assert item.price.text == "£150 at Made-up Knife Shop, checked 9 Oct 2026"
    assert item.cautions == ["Note: we couldn't confirm it's dishwasher-safe."]


def test_items_are_in_the_json_and_the_text():
    ranking, bodies, _ = case()
    answer = write_answer(ranking, bodies, "chef knife")
    data = answer_to_dict(answer)
    assert [item["name"] for item in data["worth_a_look"]] == ["Misono UX10", "Sakai Takayuki", "Masamoto VG"]
    # Changed on purpose 13 Oct 2026 (the UX builder): "voices", the credible voices behind it as numbers, for the
    # page's credibility meter (engine/tests/test_web_ux.py).
    # Changed on purpose 13 Oct 2026 (active ingredients): each item also has its "form" in an ingredient-led answer.
    # Changed on purpose 14 Oct 2026 (Noemi's night decision 1): each item also has its "range", a brand line's link to
    # its maker's page for the type, or null (engine/tests/test_line_links.py).
    # Changed on purpose 14 Oct 2026 (Noemi's decision 5): each item also has its "prescription" note, or null
    # (engine/tests/test_prescription_note.py).
    # Changed on purpose 15 Oct 2026 (Noemi's decision 4): each item also says whether it meets the picks bar but ranks
    # below the top 3 ("meets_bar"; engine/tests/test_past_the_picks.py).
    # Changed on purpose 15 Oct 2026 (Noemi's decisions 2 and 3 of the late afternoon): each item also has its "link" to
    # its own page and its maker's "image", or null (engine/tests/test_buyable.py).
    assert set(data["worth_a_look"][0]) == {"product_key", "name", "reason", "quotes", "downsides", "downsides_share",
                                           "disagreement", "score", "breakdown", "price", "availability", "cautions",
                                           "summary", "voices", "form", "range", "prescription", "meets_bar", "link",
                                           "image"}
    text = render_markdown(answer)
    assert f"## {wording.WORTH_HEADING}" in text and answer.worth_note in text
    assert text.index("Tojiro DP Gyuto") < text.index(wording.WORTH_HEADING) < text.index("Misono UX10")


def test_their_quotes_are_checked_like_every_quote():
    ranking, bodies, _ = case()
    answer = write_answer(ranking, bodies, "chef knife")
    assert {q.comment_id for item in answer.worth_a_look for q in item.quotes} <= {q.comment_id for q in shown_quotes(answer)}
    planted = dataclasses.replace(answer.worth_a_look[0].quotes[0], text="Words this comment never said at all.")
    answer.worth_a_look[0].quotes[0] = planted
    assert any("worth a look" in problem for problem in unverified_claims(answer, bodies))
    answer.worth_a_look[1].quotes.clear()
    assert any("no quote" in problem for problem in unverified_claims(answer, bodies))


# --- One-line summaries ---

TOJIRO = "kitchen:tojiro dp gyuto"  # a summary's key: the category and the words of the name shown (summary_key)


def summary(cites, text="Owners of many years say it holds an edge well.", **overrides) -> Summary:
    return Summary(**(dict(product="Tojiro DP Gyuto", category="kitchen", product_type="chef knife", text=text,
                           cites=list(cites), written_at="2026-10-13T10:00:00Z", writer="claude-code",
                           instructions_version=current_version()) | overrides))


def tojiro(ranking):
    return next(p for p in ranking.products if p.name == "Tojiro DP Gyuto")


def test_a_valid_summary_is_shown_with_the_quotes_it_cites():
    ranking, bodies, _ = case()
    cites = [m.comment_id for m in tojiro(ranking).credible_recommendations[:2]]
    answer = write_answer(ranking, bodies, "chef knife", summaries={TOJIRO: summary(cites)})
    shown = answer.picks[0].summary
    assert shown.text == "Owners of many years say it holds an edge well."
    assert [q.comment_id for q in shown.sources] == cites
    assert all(q.text in bodies[q.comment_id] for q in shown.sources)
    assert answer_to_dict(answer)["picks"][0]["summary"]["text"] == shown.text
    text = render_markdown(answer)
    assert f"{wording.SUMMARY_LABEL}** {shown.text}" in text and wording.SUMMARY_NOTE in text
    assert f'"{shown.text}"' not in text  # never in quotation marks
    assert unverified_claims(answer, bodies) == []


def test_a_pick_without_a_summary_shows_none():
    ranking, bodies, _ = case()
    answer = write_answer(ranking, bodies, "chef knife")
    assert answer.picks[0].summary is None
    assert wording.SUMMARY_LABEL not in render_markdown(answer)


def test_a_summary_citing_a_comment_that_isnt_a_credible_mention_here_isnt_shown():
    ranking, bodies, _ = case()
    cites = [tojiro(ranking).credible_recommendations[0].comment_id, "c-somewhere-else"]
    answer = write_answer(ranking, bodies, "chef knife", summaries={TOJIRO: summary(cites)})
    assert answer.picks[0].summary is None and answer.picks[0].name == "Tojiro DP Gyuto"


def test_a_summary_whose_cited_quote_fails_the_check_isnt_shown():
    ranking, bodies, _ = case()
    cited = tojiro(ranking).credible_recommendations[2]
    bodies[cited.comment_id] = "Edited since: this comment now says something else entirely."
    answer = write_answer(ranking, bodies, "chef knife", summaries={TOJIRO: summary([cited.comment_id])})
    assert answer.picks[0].summary is None


def test_a_summary_must_acknowledge_the_picks_credible_warnings():
    warning = mention("Tojiro DP Gyuto", "t1", stance="warn", voice="medium", quote="The Tojiro handle cracked.")
    ranking, bodies, _ = case([warning])
    cites = [m.comment_id for m in tojiro(ranking).credible_recommendations[:2]]
    praise = write_answer(ranking, bodies, "chef knife", summaries={TOJIRO: summary(cites)})
    assert praise.picks[0].summary is None
    honest = summary(cites + [warning.comment_id], text="Owners of many years praise its edge, but one owner's handle "
                                                         "cracked.")
    answer = write_answer(ranking, bodies, "chef knife", summaries={TOJIRO: honest})
    assert answer.picks[0].summary.text == honest.text


def test_an_item_can_have_a_summary_too():
    ranking, bodies, _ = case()
    misono = next(p for p in ranking.products if p.name == "Misono UX10")
    entry = summary([m.comment_id for m in misono.credible_recommendations], product="Misono UX10",
                    text="Two owners with long use recommend it.")
    answer = write_answer(ranking, bodies, "chef knife", summaries={"kitchen:misono ux10": entry})
    assert answer.worth_a_look[0].summary.text == "Two owners with long use recommend it."


def test_the_live_check_covers_the_quotes_a_summary_cites():
    ranking, bodies, _ = case()
    cites = [m.comment_id for m in tojiro(ranking).credible_recommendations]
    answer = write_answer(ranking, bodies, "chef knife", summaries={TOJIRO: summary(cites)})
    checked = {(q.url, q.text) for q in quotes_to_check(answer)}
    assert {(q.url, q.text) for q in answer.picks[0].summary.sources} <= checked
    assert {(q.url, q.text) for q in shown_quotes(answer)} <= checked


def test_a_shown_summary_is_checked_once_more_with_every_quote():
    ranking, bodies, _ = case()
    cites = [m.comment_id for m in tojiro(ranking).credible_recommendations[:2]]
    answer = write_answer(ranking, bodies, "chef knife", summaries={TOJIRO: summary(cites)})
    pick = answer.picks[0]
    pick.summary = dataclasses.replace(pick.summary, text='Owners call it "the best".')
    assert any("quotation marks" in problem for problem in unverified_claims(answer, bodies))
    pick.summary = dataclasses.replace(pick.summary, text="Owners like it.", sources=(
        dataclasses.replace(pick.summary.sources[0], text="Words this comment never said at all."),))
    assert any("summary" in problem for problem in unverified_claims(answer, bodies))


def test_the_json_of_a_pick_has_its_summary_or_null():
    ranking, bodies, _ = case()
    data = json.loads(json.dumps(answer_to_dict(write_answer(ranking, bodies, "chef knife"))))
    assert data["picks"][0]["summary"] is None


def test_an_items_unknown_price_and_availability_arent_spelled_out_but_a_budget_note_is():
    # Lighter than a pick's card: "Price not checked yet" under every item was noise (13 Oct 2026). With a budget, the
    # note saying it wasn't checked against it stays: that matters to the shopper.
    from engine.query import Budget

    ranking, bodies, _ = case()
    plain = render_markdown(write_answer(ranking, bodies, "chef knife"))
    worth_part = plain[plain.index(wording.WORTH_HEADING):]
    assert wording.PRICE_UNKNOWN not in worth_part and wording.AVAILABILITY_UNKNOWN not in worth_part
    budget = Budget(max=100, currency="GBP")
    checks = {"misono-ux10": PriceCheck(None, "unknown", budget)}
    with_budget = render_markdown(write_answer(ranking, bodies, "chef knife", prices=checks))
    assert "Not checked against your budget (up to £100): no price checked yet." in with_budget[
        with_budget.index(wording.WORTH_HEADING):]


def test_an_item_never_shows_a_quote_that_starts_mid_sentence():
    # Found judging the 13 Oct 2026 answers: a quote opened on its verb, its subject (a link) left out.
    cut = [mention("Mauviel M150", t, quote="is what I cook with every day, a great pan.") for t in ("t1", "t2")]
    ranking, bodies, _ = case(cut)
    for m in cut:
        bodies[m.comment_id] = "[This Mauviel](https://shop.example/pan) is what I cook with every day, a great pan."
    assert "Mauviel M150" not in names(write_answer(ranking, bodies, "chef knife").worth_a_look)
    whole = [mention("Mauviel M150", t, quote="My Mauviel is what I cook with every day, a great pan.") for t in ("t1", "t2")]
    ranking, bodies, _ = case(whole)
    assert "Mauviel M150" in names(write_answer(ranking, bodies, "chef knife").worth_a_look)
