"""Confirmed first under a must-have (Noemi's decision 1 of 15 Oct 2026).

When a request asks for a must-have, a hard requirement a product's facts can settle (engine.product_facts.
hard_requirements: SPF for a lip balm, PFAS-free or non-stick for a pan, sulfate-free for a shampoo, fragrance-free,
gentle enough for a beginner...), a product whose facts or own name confirm it ranks above one they can't confirm.
Until then a pick we couldn't confirm kept its place, with a note (the rules of 10 and 11 Oct 2026), so "lip balm with
spf" showed lip balms sold with and without SPF ahead of one whose own name says SPF 25. The note stays; the order
changes, in each part of the answer:
- module 6 (engine/rank.py) is told how many of the request's must-haves each product's facts leave unconfirmed and
  ranks fewer first, then as before (score, credible recommendations, threads...). So the picks, the products meeting
  the bar below the top 3 (which head Also worth a look) and the items with two credible voices each put the confirmed
  first. Confirmation never makes a pick: a product short of the bar stays short of it, and one that meets the bar only
  thanks to the upvote rules still only fills a place left empty;
- the pipeline (engine/pipeline.py) counts what it couldn't confirm where it writes the note, and ranks with the
  counts every time it ranks (again after a live check drops a comment, and with the upvote rules).

Every product, comment and library here is made up; nothing reads data/ or reaches the network.
"""

from engine.pipeline import answer_request
from engine.rank import rank_products
from engine.tests.ranking_factories import mention, mentions
from engine.tests.test_lip_balms import SPF_REQUEST, lip
from engine.tests.test_pipeline import FakeLive, praise
from engine.tests.test_pipeline import write_library as kitchen_library
from engine.tests.test_product_facts import PAN, TODAY, known, names, write_library

TOP = {"thread_comments": 40, "share_beaten": 0.95}  # the top of a big thread, as engine/tests/test_upvotes.py has it


# --- Module 6: the ranking ---

def test_a_product_whose_facts_confirm_the_must_have_ranks_above_one_they_cant_confirm():
    items = mentions(5, "Mystery Balm", category="skincare") + mentions(3, "Sure Balm", category="skincare")
    before = rank_products(items, "skincare")
    assert names(before.picks) == ["Mystery Balm", "Sure Balm"]  # by score, as before
    ranking = rank_products(items, "skincare", unconfirmed={"mystery-balm": 1})
    assert names(ranking.products) == names(ranking.picks) == ["Sure Balm", "Mystery Balm"]
    mystery = next(p for p in ranking.products if p.name == "Mystery Balm")
    assert mystery.unconfirmed == 1 and mystery.qualifies  # still a pick, after the confirmed one
    assert next(p for p in ranking.products if p.name == "Sure Balm").unconfirmed == 0


def test_without_a_must_have_the_ranking_is_as_before():
    items = mentions(5, "Mystery Balm", category="skincare") + mentions(3, "Sure Balm", category="skincare")
    for unconfirmed in (None, {}, {"mystery-balm": 0}):
        assert names(rank_products(items, "skincare", unconfirmed=unconfirmed).products) == ["Mystery Balm",
                                                                                            "Sure Balm"]


def test_confirmation_never_makes_a_pick():
    # The confirmed product has two credible voices: less supported than a pick, it stays under Also worth a look while
    # the product we couldn't confirm, meeting the bar, is the pick.
    items = mentions(4, "Mystery Balm", category="skincare") + mentions(2, "Sure Duo", category="skincare")
    ranking = rank_products(items, "skincare", unconfirmed={"mystery-balm": 1})
    assert names(ranking.products) == ["Sure Duo", "Mystery Balm"]
    assert names(ranking.picks) == ["Mystery Balm"] and names(ranking.worth_a_look) == ["Sure Duo"]


def test_fewer_must_haves_left_unconfirmed_rank_first():
    # "non-stick frying pan without PFAS": a pan confirmed non-stick but not PFAS-free comes after one confirmed both
    # ways and before one confirmed neither way, whatever their scores.
    items = mentions(6, "Neither Pan") + mentions(5, "Half Pan") + mentions(3, "Full Pan")
    ranking = rank_products(items, "kitchen", unconfirmed={"neither-pan": 2, "half-pan": 1})
    assert names(ranking.picks) == ["Full Pan", "Half Pan", "Neither Pan"]


def test_past_the_picks_and_two_voice_items_put_the_confirmed_first_each_in_their_place():
    # Four products meet the bar: the confirmed three are the picks, and the best supported one, unconfirmed, heads
    # Also worth a look as meeting the bar. Among the items with two credible voices, the confirmed one comes first.
    # Each part keeps its place: a product meeting the bar is never put after a two-voice item.
    items = (mentions(6, "Knife U") + mentions(4, "Knife A") + mentions(4, "Knife B") + mentions(4, "Knife C")
             + mentions(2, "Duo V", voice="medium") + mentions(2, "Duo W", voice="medium", weight=0.2))
    ranking = rank_products(items, "kitchen", unconfirmed={"knife-u": 1, "duo-v": 1})
    assert names(ranking.picks) == ["Knife A", "Knife B", "Knife C"]
    assert names(ranking.past_the_picks) == ["Knife U"]
    assert names(ranking.worth_a_look) == ["Knife U", "Duo W", "Duo V"]


def test_a_product_the_upvote_rule_lifts_still_only_fills_a_place_left_empty():
    # Variant D (Noemi's decision 3 of 14 Oct 2026): a product lifted to the bar by an upvoted comment comes after every
    # product meeting it on its own, confirmed or not.
    lifted = [mention("Lifted Pan", "t1", upvotes=40, **TOP), mention("Lifted Pan", "t2")]
    items = mentions(3, "Own Pan") + mentions(3, "Noted Pan", weight=2.0) + lifted
    ranking = rank_products(items, "kitchen", upvote_rule=True, unconfirmed={"noted-pan": 1})
    assert names(ranking.qualifying) == ["Own Pan", "Noted Pan", "Lifted Pan"]


# --- In answers: the pipeline counts what it couldn't confirm and ranks with it ---

def lip_library(tmp_path):
    """Lip balm threads: the two best supported balms can't be confirmed to have SPF; one is confirmed by its name
    ("... SPF 30"), one by its facts entry; one has no SPF at all."""
    return write_library(tmp_path, ("Lip balm with SPF for summer?", "Which lip balm do you swear by?"),
                         {"Mystery Overnight Lip Balm": 6, "Velvet Lip Balm": 5, "Plain Lip Butter": 5,
                          "Acme Lip Balm SPF 30": 3, "Glow Tinted Balm": 3}, product_type="lip balm")


FACTS = [lip("Plain Lip Butter", spf=False), lip("Glow Tinted Balm", spf=True)]
NOTE = "Note: we couldn't confirm it has SPF."


def key_of(result, name: str) -> str:
    return next(p.key for p in result.ranking.products if p.name == name)


def test_lip_balms_confirmed_to_have_spf_come_first_and_the_others_follow_with_their_note(tmp_path):
    result = answer_request(SPF_REQUEST, library_dir=lip_library(tmp_path), prices=[], product_facts=FACTS,
                            today=TODAY)
    assert names(result.answer.picks) == ["Acme Lip Balm SPF 30", "Glow Tinted Balm", "Mystery Overnight Lip Balm"]
    picks = {pick.name: pick for pick in result.answer.picks}
    assert picks["Acme Lip Balm SPF 30"].cautions == [] and picks["Glow Tinted Balm"].cautions == []
    assert picks["Mystery Overnight Lip Balm"].cautions == [NOTE]
    # The other balm we couldn't confirm meets the bar too: it heads Also worth a look, with its note.
    [item] = result.answer.worth_a_look
    assert (item.name, item.meets_bar, item.cautions) == ("Velvet Lip Balm", True, [NOTE])
    assert result.unconfirmed == {key_of(result, "Mystery Overnight Lip Balm"): 1, key_of(result, "Velvet Lip Balm"): 1}
    assert "Plain Lip Butter" not in names(result.ranking.products)  # no SPF: left out, as before


def test_a_lip_balm_request_without_the_must_have_ranks_as_before(tmp_path, skincare_need_rule_set_aside):
    result = answer_request("lip balm for very dry lips", library_dir=lip_library(tmp_path), prices=[],
                            product_facts=FACTS, today=TODAY)
    assert names(result.answer.picks) == ["Mystery Overnight Lip Balm", "Plain Lip Butter", "Velvet Lip Balm"]
    assert result.unconfirmed == {} and all(pick.cautions == [] for pick in result.answer.picks)


def test_the_order_holds_when_the_live_check_drops_a_comment_and_the_answer_is_ranked_again(tmp_path):
    lib = lip_library(tmp_path)
    before = answer_request(SPF_REQUEST, library_dir=lib, prices=[], product_facts=FACTS, today=TODAY)
    # One of the confirmed Acme balm's comments was deleted on Reddit: with two credible voices left it falls short of
    # the bar, and the answer is ranked again. The confirmed Glow balm still comes first.
    acme = next(p for p in before.ranking.products if p.name == "Acme Lip Balm SPF 30")
    gone = next(m.comment_id for m in acme.mentions if m.thread_id == "1skin01")
    result = answer_request(SPF_REQUEST, library_dir=lib, prices=[], product_facts=FACTS, today=TODAY,
                            live_checker=FakeLive(gone={gone}))
    assert result.live_dropped == {"gone": 1}
    assert names(result.answer.picks) == ["Glow Tinted Balm", "Mystery Overnight Lip Balm", "Velvet Lip Balm"]
    assert [item.name for item in result.answer.worth_a_look] == ["Acme Lip Balm SPF 30"]


def pans(tmp_path):
    """Frying pan threads: the best supported pan can't be confirmed PFAS-free or non-stick, the next is confirmed
    non-stick only, the least supported both ways."""
    return kitchen_library(tmp_path, {
        "1pan101": ("Best non-stick frying pan without PFAS?", "Mine is peeling.", [
            praise("m1a", "Misen frying pan", 4), praise("m1b", "Misen frying pan", 5),
            praise("m1c", "Misen frying pan", 6), praise("c1a", "Corra frying pan", 4),
            praise("c1b", "Corra frying pan", 5), praise("c1c", "Corra frying pan", 3),
            praise("g1a", "GreenPan Valencia frying pan", 4), praise("g1b", "GreenPan Valencia frying pan", 5)]),
        "1pan102": ("Which frying pan lasts?", "Ten years, ideally.", [
            praise("m2a", "Misen frying pan", 7), praise("m2b", "Misen frying pan", 8),
            praise("m2c", "Misen frying pan", 9), praise("c2a", "Corra frying pan", 6),
            praise("c2b", "Corra frying pan", 7), praise("g2a", "GreenPan Valencia frying pan", 6)]),
    }, community="BuyItForLife")


def pan(product: str, **facts):
    return known(product, category="kitchen", product_type="frying pan", **facts)


def test_a_pan_confirmed_pfas_free_and_non_stick_comes_first_then_the_one_confirmed_half_way(tmp_path):
    lib = pans(tmp_path)
    without = answer_request(PAN, library_dir=lib, prices=[], product_facts=[], today=TODAY)
    assert names(without.answer.picks) == ["Misen frying pan", "Corra frying pan", "GreenPan Valencia frying pan"]
    facts = [pan("GreenPan Valencia frying pan", pfas_free=True, non_stick=True),
             pan("Corra frying pan", non_stick=True)]
    result = answer_request(PAN, library_dir=lib, prices=[], product_facts=facts, today=TODAY)
    assert names(result.answer.picks) == ["GreenPan Valencia frying pan", "Corra frying pan", "Misen frying pan"]
    notes = {pick.name: pick.cautions for pick in result.answer.picks}
    assert notes == {"GreenPan Valencia frying pan": [],
                     "Corra frying pan": ["Note: we couldn't confirm it's PFAS-free."],
                     "Misen frying pan": ["Note: we couldn't confirm it's PFAS-free or that it's non-stick."]}
    # A request without the must-haves ranks the same pans by their support alone.
    lasts = answer_request("frying pan that lasts", library_dir=lib, prices=[], product_facts=facts, today=TODAY)
    assert names(lasts.answer.picks) == names(without.answer.picks) and lasts.unconfirmed == {}
