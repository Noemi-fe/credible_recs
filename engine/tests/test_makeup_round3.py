"""Round 3 after the profile warm (6 Nov 2026): Noemi's two decisions of that day and the round's technical calls.

Noemi's decisions ("yes to all three", 6 Nov 2026, in chat):
- (2) a hair product (a hair gel, a spiking gel, a hairspray, a hair glue and the like, known by what its names say it
  is) is never a pick in a face-makeup answer; it may still be listed under Also worth a look, with its product note
  (Claude's call), and nothing changes outside face makeup;
- (3) the warnings filed under a "(new formula)" item are about the product sold today: they fold into the product they
  are about, where the unchanged scoring weighs them and the answer shows them as its downsides.

And Claude's technical calls from the third reviews: the bare swear word the page didn't mask, and the on-demand
reading's last two ways for a removed thread to take a place in its request's round.

Every comment, quote, product and thread here is made up.
"""

import pytest

from engine import config
from engine.answer import masked, write_answer
from engine.pipeline import _ranked, answer_request
from engine.query import parse_query
from engine.rank import rank_products
from engine.tests.ranking_factories import bodies_for, mention, mentions
from engine.tests.test_product_facts import TODAY, write_library


def names(items) -> list[str]:
    return [item.name for item in items]


# --- Noemi's decision (2): a hair product is never a pick in a face-makeup answer ---

def brow_gels(hair_product: str = "Zing Spiking Gel", category: str = "general") -> list:
    """The hair product has the most support; three brow gels meet the bar after it."""
    return (mentions(6, hair_product, category=category) + mentions(5, "Velo brow gel", category=category)
            + mentions(4, "Halo brow gel", category=category) + mentions(3, "Mira brow gel", category=category))


def test_a_hair_gel_is_never_a_pick_in_a_brow_gel_answer_and_heads_also_worth_a_look():
    ranking = _ranked(brow_gels(), parse_query("brow gel", model=None), [], [], False)
    assert names(ranking.picks) == ["Velo brow gel", "Halo brow gel", "Mira brow gel"]
    assert names(ranking.past_the_picks) == ["Zing Spiking Gel"]  # it meets the bar: first under Also worth a look
    zing = next(p for p in ranking.products if p.name == "Zing Spiking Gel")
    assert zing.qualifies and zing.score == max(p.score for p in ranking.products)  # its score is as it was
    # Outside face makeup nothing changes: in a hair gel answer the same gel is the first pick.
    hair = _ranked(brow_gels(category="haircare"), parse_query("hair gel", model=None), [], [], False)
    assert names(hair.picks)[0] == "Zing Spiking Gel"


@pytest.mark.parametrize("request_, hair_product", [
    ("eyebrow gel", "Zing hair gel"),
    ("brow gel", "Zing Ultra Hold Styling Gel"),
    ("setting spray", "Zing Freeze Hairspray"),
    ("setting spray", "Zing hair spray"),
    ("mascara", "Zing Hair Glue"),
])
def test_what_its_names_say_it_is_makes_it_a_hair_product(request_, hair_product):
    query = parse_query(request_, model=None)
    kind = query.product_type
    items = (mentions(6, hair_product, category="general") + mentions(5, f"Velo {kind}", category="general")
             + mentions(4, f"Halo {kind}", category="general") + mentions(3, f"Mira {kind}", category="general"))
    assert hair_product not in names(_ranked(items, query, [], [], False).picks)


def test_a_hair_product_known_by_another_of_its_names_is_still_one():
    # Writers name it by its maker alone, or call it a brow gel, as much as by what it is: one name saying hair gel is
    # enough. A brow glue or a brow soap is a brow gel, not a hair product.
    items = ([mention("Zing glue", "t1", category="general", written_as="Zing glue") for _ in range(4)]
             + [mention("Zing glue", "t2", category="general", written_as="Zing hair gel") for _ in range(2)]
             + mentions(5, "Velo brow glue", category="general") + mentions(4, "Halo brow soap", category="general")
             + mentions(3, "Mira brow gel", category="general"))
    ranking = _ranked(items, parse_query("brow gel", model=None), [], [], False)
    assert names(ranking.picks) == ["Velo brow glue", "Halo brow soap", "Mira brow gel"]


def test_the_hair_gel_under_also_worth_a_look_keeps_its_product_note():
    items = brow_gels()
    ranking = _ranked(items, parse_query("brow gel", model=None), [], [], False)
    note = "A hair styling gel, which some writers use to hold their brows"
    answer = write_answer(ranking, bodies_for(*items), "brow gel", request="brow gel",
                          cautions={"zing-spiking-gel": [note]})
    assert "Zing Spiking Gel" not in names(answer.picks)
    first = answer.worth_a_look[0]
    assert (first.name, first.meets_bar) == ("Zing Spiking Gel", True)
    assert first.cautions == [f"Note: {note}."]


# --- Noemi's decision (3): a "(new formula)" item folds into the product it is about ---

@pytest.mark.parametrize("name, base", [
    ("Velvet Lip Balm (new formula)", "Velvet Lip Balm"),
    ("Velvet Lip Balm (New Formula)", "Velvet Lip Balm"),
    ("Velvet lip balm new formula", "Velvet lip balm"),
    ("Velvet new formula lip balm", "Velvet lip balm"),
    ("new formulation of Velvet", "Velvet"),
    ("Velvet Lip Balm new formulas", "Velvet Lip Balm"),
    ("Velvet Lip Balm (reformulated)", "Velvet Lip Balm"),
    ("reformulated Velvet Lip Balm", "Velvet Lip Balm"),
    ("Velvet Lip Balm (post-reformulation)", "Velvet Lip Balm"),
    # Not the product sold today, or not a formula: left as they are.
    ("Velvet Lip Balm (old formula)", None),
    ("Velvet Lip Balm (original formula)", None),
    ("Velvet Lip Balm pre reformulation version", None),
    ("Velvet Lip Balm (new)", None),
    ("Velvet Lip Balm", None),
])
def test_which_names_say_new_formula(name, base):
    from engine.pipeline import new_formula_base
    assert new_formula_base(name) == base


def lip_balms(tmp_path):
    """The Velvet balm has the most praise, three warnings filed under its new formula and praise for its old one; the
    Ghost balm's new formula is warned against with no Ghost balm of today's in the answer."""
    return write_library(tmp_path, ("Which lip balm do you swear by?", "Best lip balm for winter?"),
                         {"Velvet Lip Balm": 5, "Plain Lip Butter": 4, "Acme Lip Balm": 4,
                          "Velvet Lip Balm (old formula)": 3},
                         {"Velvet Lip Balm (new formula)": 3, "Ghost Lip Balm (new formula)": 3},
                         product_type="lip balm")


def test_a_new_formulas_warnings_fold_into_the_product_sold_today(tmp_path):
    result = answer_request("lip balm", library_dir=lip_balms(tmp_path), prices=[], product_facts=[], today=TODAY)
    velvet = next(p for p in result.ranking.products if p.name.startswith("Velvet") and "formula" not in p.name)
    assert len(velvet.credible_warnings) == 3  # the new formula's warnings are its own now
    assert all("(new formula)" in m.quote for m in velvet.credible_warnings)
    # The unchanged scoring weighs them: it drops below the two balms it led.
    assert names(result.answer.picks)[:2] == ["Acme Lip Balm", "Plain Lip Butter"]
    shown = next(item for item in [*result.answer.picks, *result.answer.worth_a_look] if item.name == velvet.name)
    assert len(shown.downsides) >= 1 and shown.downsides_share.startswith("3 of 8 credible voices")
    # No Skip item for the new formula of a product the answer has; one without its product today stays apart.
    assert names(result.answer.skip) == ["Ghost Lip Balm (new formula)"]
    # The old formula is another product: never folded in.
    assert any(p.name == "Velvet Lip Balm (old formula)" for p in result.ranking.products)


def test_folding_drops_only_a_renamed_mention_its_writer_already_made_and_nothing_else():
    # The round's own sweep: the fold had also merged a comment's repeated mention of another product (two quotes of one
    # brand in one comment), so that brand's line changed in an answer the fold had nothing to do with.
    from engine.extract import CheckResult, ExtractedMention
    from engine.group_products import ProductMention, group_products
    from engine.pipeline import _new_formulas_folded

    def said(comment, product, stance, quote):
        return ExtractedMention(comment_id=comment, product=product, category="general", stance=stance, quote=quote)
    kept = [said("c1", "Acme Lip Balm", "recommend", "Acme first"),
            said("c1", "Acme Lip Balm", "recommend", "Acme again"),
            said("c2", "Velvet Lip Balm", "warn", "Velvet today"),
            said("c2", "Velvet Lip Balm (new formula)", "warn", "Velvet new"),
            said("c3", "Velvet Lip Balm (new formula)", "warn", "Velvet new too"),
            said("c4", "Velvet Lip Balm", "recommend", "Velvet loved")]
    checked = {"t1": CheckResult(kept=kept)}
    mentions = [ProductMention("t1", m.comment_id, m.product, "general", m.stance, m.product_type, m.quote)
                for m in kept]
    new_checked, new_mentions = _new_formulas_folded(
        checked, mentions, lambda found: group_products(found, product_type="lip balm"))
    assert [(m.comment_id, m.product) for m in new_checked["t1"].kept] == [
        ("c1", "Acme Lip Balm"), ("c1", "Acme Lip Balm"), ("c2", "Velvet Lip Balm"), ("c3", "Velvet Lip Balm"),
        ("c4", "Velvet Lip Balm")]
    assert [(m.comment_id, m.product) for m in new_mentions] == [
        ("c1", "Acme Lip Balm"), ("c1", "Acme Lip Balm"), ("c2", "Velvet Lip Balm"), ("c3", "Velvet Lip Balm"),
        ("c4", "Velvet Lip Balm")]


# --- The swear word the page didn't mask (the rules review: a brow gel pick led with it) ---

def test_the_bare_word_is_masked_and_never_leads_but_words_holding_it_are_untouched():
    assert masked("The Rosa brow gel kicks every other gel's ass.") == "The Rosa brow gel kicks every other gel's a*s."
    assert masked("Kick-ass hold, as for the arse of it.") == "Kick-a*s hold, as for the a**e of it."
    for word in ("class", "pass", "assess", "bass", "mass", "Assam", "assume", "badass"):
        assert masked(f"A {word} of a gel.") == f"A {word} of a gel."
    swear = mention("Rosa brow gel", "t1", category="general", weight=3.0,
                    quote="The Rosa brow gel kicks every other gel's ass.")
    clear = mention("Rosa brow gel", "t2", category="general", weight=0.5,
                    quote="The Rosa brow gel holds my brows in place from morning to night.")
    items = [swear, clear, mention("Rosa brow gel", "t1", category="general", weight=0.5)]
    items += mentions(3, "Halo brow gel", category="general")
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "brow gel", request="brow gel")
    rosa = next(pick for pick in answer.picks if pick.name == "Rosa brow gel")
    assert rosa.quotes[0].comment_id != swear.comment_id and clear.comment_id in [q.comment_id for q in rosa.quotes]


# --- Noemi's "Remove those 2 threads": on-demand reading's count of a request's threads ---

def test_a_removed_thread_in_the_bundle_never_counts_towards_a_requests_threads(tmp_path, monkeypatch):
    # The rules review of fix 2: a removed thread already extracted in the bundle still counted towards "enough threads
    # about it already", so a request one thread short was closed unread. Here 1tea002 stands in for a removed thread.
    from engine import on_demand
    from engine.live_check import Bucket
    from engine.on_demand import Bundle, BundleStore, Item, Queue, QueueStore, entry_for, run_job
    from engine.tests.fake_google import FakeGoogle
    from engine.tests.on_demand_fakes import NOW, FakeArchive, FakeGemini, Ticks, archive, gemini
    from engine.tests.test_web import kettle_library

    monkeypatch.setattr(on_demand, "REMOVED_THREADS", ("1tea002",))
    google = FakeGoogle()
    bucket = Bucket("credible-test-on-demand", request=google, clock=lambda: 0.0, prefix=on_demand.PREFIX)
    entry = entry_for(parse_query("teapot for loose leaf tea"), had=config.ON_DEMAND_MIN_THREADS - 1)
    BundleStore(bucket).change(lambda b: b.threads.update({"1tea002": Item(
        thread="{}", extraction="{}", entry="another/entry/", product_type="teapot", added_at=NOW.isoformat())}))
    QueueStore(bucket).change(lambda queue: queue.add(entry) and None)
    run_job(bucket, kettle_library(tmp_path), archive(tmp_path, FakeArchive()), gemini(FakeGemini()), now=lambda: NOW,
            clock=Ticks(), work_dir=tmp_path / "work")
    bundle = Bundle.from_json(google.read("credible-test-on-demand", on_demand.PREFIX + "threads.json"))
    [waited] = Queue.from_json(google.read("credible-test-on-demand", on_demand.PREFIX + "queue.json")).entries
    assert waited.note != "enough threads about it already"
    assert set(bundle.threads) - {"1tea002"}  # it was read
