"""Round 3's fixer (6 Nov 2026): from the rules review, the shopper review and the summary fact-check of round 3.

- A hair product under Also worth a look (Noemi's decision 2 of 6 Nov 2026 keeps it out of the picks) is tagged as a
  hair product, never as one more product that "ranks below the top 3": it can outscore the third pick, so the note under
  the heading says why it isn't a pick instead.
- Noemi's decision 1 of 6 Nov 2026: a product note shows wherever its product is shown, Skip these included.
- On-demand reading: a removed thread in the bundle never counts as one of a request's threads read and extracted.

Every comment, quote, product and thread here is made up.
"""

from engine import config
from engine.answer import (HAIR_PRODUCT_TAG, MEETS_BAR, WORTH_NOTE_BAR_EACH, _worth_note, render_markdown,
                           write_answer)
from engine.pipeline import _ranked, answer_request
from engine.query import parse_query
from engine.tests.ranking_factories import bodies_for, mentions
from engine.tests.test_makeup_round3 import lip_balms
from engine.tests.test_product_facts import TODAY

RULE = "at least 3 credible recommendations across at least 2 threads"


def brow_gels(category: str = "general"):
    """The hair gel has the most support; four brow gels meet the bar after it, so one ranks below the picks."""
    return (mentions(6, "Zing Spiking Gel", category=category) + mentions(5, "Velo brow gel", category=category)
            + mentions(4, "Halo brow gel", category=category) + mentions(4, "Mira brow gel", category=category)
            + mentions(3, "Nova brow gel", category=category))


def brow_gel_answer():
    items = brow_gels()
    ranking = _ranked(items, parse_query("brow gel", model=None), [], [], False)
    return write_answer(ranking, bodies_for(*items), "brow gel", request="brow gel")


# --- A hair product under Also worth a look says why it isn't a pick ---

def test_a_hair_product_under_also_worth_a_look_is_tagged_as_one_and_the_note_says_why_it_isnt_a_pick():
    answer = brow_gel_answer()
    assert [pick.name for pick in answer.picks] == ["Velo brow gel", "Halo brow gel", "Mira brow gel"]
    zing, nova = answer.worth_a_look
    assert (zing.name, zing.meets_bar, zing.hair_product) == ("Zing Spiking Gel", True, True)
    assert (nova.name, nova.meets_bar, nova.hair_product) == ("Nova brow gel", True, False)
    # Not "each ranks below the top 3": the hair gel outscores the third pick.
    assert answer.worth_note == (f"Each meets the bar for a pick ({RULE}); the hair product is never a makeup pick, "
                                 "and the other ranks below the top 3.")
    text = render_markdown(answer)
    zing_part = text[text.index("### Zing Spiking Gel"):text.index("### Nova brow gel")]
    assert f"**{HAIR_PRODUCT_TAG}**" in zing_part and MEETS_BAR not in zing_part
    assert f"**{MEETS_BAR}**" in text[text.index("### Nova brow gel"):]


def test_the_note_under_also_worth_a_look_with_hair_products_in_every_shape():
    rest = "2 credible voices each: less evidence than a pick needs."
    assert _worth_note(3, bar_items=1, items=1, hair_items=1) == (
        f"It meets the bar for a pick ({RULE}), but a hair product is never a makeup pick.")
    assert _worth_note(3, bar_items=2, items=2, hair_items=2) == (
        f"Each meets the bar for a pick ({RULE}), but hair products are never makeup picks.")
    assert _worth_note(3, bar_items=3, items=3, hair_items=1) == (
        f"Each meets the bar for a pick ({RULE}); the hair product is never a makeup pick, and the others rank below "
        "the top 3.")
    assert _worth_note(3, bar_items=1, items=3, hair_items=1) == (
        f"The first meets the bar for a pick ({RULE}), but a hair product is never a makeup pick; then {rest}")
    assert _worth_note(3, bar_items=3, items=4, hair_items=2) == (
        f"The first 3 meet the bar for a pick ({RULE}); the hair products are never makeup picks, and the other ranks "
        f"below the top 3; then {rest}")
    # Without a hair product, the note is as it was.
    assert _worth_note(3, bar_items=3, items=3) == WORTH_NOTE_BAR_EACH.format(rule=RULE, picks=3)


def test_the_page_tags_a_hair_product_in_the_answers_own_words(tmp_path):
    import json
    import re
    from engine.tests.test_web import page
    html = page(tmp_path)
    settings = json.loads(re.search(r'<script type="application/json" id="settings">(.*?)</script>', html,
                                    re.DOTALL).group(1))
    assert settings["wording"]["hair_product"] == HAIR_PRODUCT_TAG == "A hair product, never a makeup pick"
    assert "WORDING.hair_product" in html


def test_outside_makeup_no_item_is_tagged_as_a_hair_product():
    items = brow_gels(category="haircare")
    ranking = _ranked(items, parse_query("hair gel", model=None), [], [], False)
    answer = write_answer(ranking, bodies_for(*items), "hair gel", request="hair gel")
    assert answer.picks[0].name == "Zing Spiking Gel"
    assert not any(item.hair_product for item in answer.worth_a_look)


# --- Noemi's decision (1): a product note shows wherever its product is shown, Skip these included ---

def test_a_skip_item_shows_its_product_note_and_no_other_caution():
    items = brow_gels() + mentions(3, "Rex brow gel", category="general", stance="warn")
    ranking = _ranked(items, parse_query("brow gel", model=None), [], [], False)
    note = "A made-up fact about the Rex gel, checked on a made-up page"
    answer = write_answer(ranking, bodies_for(*items), "brow gel", request="brow gel",
                          cautions={"rex-brow-gel": [note, "a made-up clash with the request"]},
                          product_notes={"rex-brow-gel": [note]})
    [rex] = answer.skip
    assert rex.name == "Rex brow gel" and rex.cautions == [f"Note: {note}."]
    assert f"Note: {note}." in render_markdown(answer)
    # Without a note, a Skip item shows none, whatever its other cautions.
    plain = write_answer(ranking, bodies_for(*items), "brow gel", request="brow gel",
                         cautions={"rex-brow-gel": ["a made-up clash with the request"]})
    assert plain.skip[0].cautions == []


def test_the_pipeline_shows_a_noted_products_note_under_skip_these(tmp_path, monkeypatch):
    from engine import pipeline
    from engine.product_notes import ProductNote
    note = ProductNote(names=("Ghost Lip Balm",), category="skincare", note="A made-up note about the Ghost balm",
                       sources=("https://example.com/ghost",), checked_on="2026-11-06")
    monkeypatch.setattr(pipeline, "load_product_notes", lambda: [note])
    result = answer_request("lip balm", library_dir=lip_balms(tmp_path), prices=[], product_facts=[], today=TODAY)
    [ghost] = result.answer.skip
    assert ghost.name == "Ghost Lip Balm (new formula)"
    assert ghost.cautions == ["Note: A made-up note about the Ghost balm."]


# --- On-demand reading: a removed thread in the bundle is never one of a request's threads ---

def test_a_removed_thread_in_the_bundle_never_counts_when_a_request_is_closed(monkeypatch):
    # The rules review of round 3: _finish_complete still counted a removed thread filed under the request, in its
    # "found" count and note, and waited for its extraction. Here 1tea002 stands in for a removed thread.
    from engine import on_demand
    from engine.live_check import Bucket
    from engine.on_demand import BundleStore, Item, Queue, QueueStore, RunReport, _finish_complete, entry_for
    from engine.tests.fake_google import FakeGoogle
    from engine.tests.on_demand_fakes import NOW

    monkeypatch.setattr(on_demand, "REMOVED_THREADS", ("1tea002",))
    google = FakeGoogle()
    bucket = Bucket("credible-test-on-demand", request=google, clock=lambda: 0.0, prefix=on_demand.PREFIX)
    entry = entry_for(parse_query("teapot for loose leaf tea"), had=0)
    entry.read_at = NOW.isoformat()
    QueueStore(bucket).change(lambda queue: queue.add(entry) and None)
    BundleStore(bucket).change(lambda b: b.threads.update({
        "1tea001": Item(thread="{}", extraction="{}", entry=entry.key, product_type="teapot", added_at=NOW.isoformat()),
        # The removed thread, filed under the same request and never extracted: it holds nothing up and counts for
        # nothing.
        "1tea002": Item(thread="{}", extraction=None, entry=entry.key, product_type="teapot",
                        added_at=NOW.isoformat())}))
    report = RunReport()
    assert _finish_complete(QueueStore(bucket), lambda: NOW, report)
    [done] = Queue.from_json(google.read("credible-test-on-demand", on_demand.PREFIX + "queue.json")).entries
    assert (done.status, done.found, done.note) == ("done", 1, "1 threads read and extracted")
    assert report.requests_done == ["teapot"]
    assert config.REMOVED_THREADS  # the real list is untouched
