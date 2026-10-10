"""Care tips, "how to make it last" (Noemi, 9 Oct 2026): which credible tips go with which products.

A product tip goes with the product it names; a kind tip goes with the kinds it is about, and so with their
products; a tip about the requested kind of product itself goes with every product. Low voices are left out.
All data is made up.
"""

import pytest

from engine import care_tips
from engine.care_tips import CareTip, attach_care_tips, credible_care_tips, same_tip
from engine.extract import Extraction, check_extraction
from engine.group_kinds import KindGroup
from engine.group_products import ProductGroup, ProductMention
from engine.models import Thread
from engine.tests.factories import make_comment, make_thread


def product(name: str, *other_names: str, loose: bool = False, shown: str | None = None) -> ProductGroup:
    """A kitchen product group whose mentions are written under these names."""
    mentions = [ProductMention("t1", f"c{i}{name[:3].lower()}", n, "kitchen", "recommend")
                for i, n in enumerate((name,) + other_names)]
    return ProductGroup(f"kitchen:{name.lower()}", shown or name, "kitchen", mentions, loose)


def tip(about: str, is_kind: bool = False, text: str = "descale every 6 months", comment: str = "cT1",
        voice: str = "high") -> CareTip:
    return CareTip(about=about, is_kind=is_kind, tip=text, quote=f"A tip from comment {comment}.", thread_id="t1",
                   comment_id=comment, comment_url=f"https://www.reddit.com/r/test/comments/t1/comment/{comment}/",
                   voice=voice, badges=("well upvoted",))


ZOJIRUSHI = product("Zojirushi kettle", "Zojirushi")
STAGG = product("Fellow Stagg kettle")


def attach(tips, products, kinds=(), product_type="electric kettle"):
    return attach_care_tips(tips, list(products), list(kinds), "kitchen", product_type)


# --- Product tips ---

def test_a_product_tip_goes_with_the_product_it_names():
    care = attach([tip("zojirushi")], [ZOJIRUSHI, STAGG])
    assert [t.about for t in care[ZOJIRUSHI.key].own] == ["zojirushi"]
    assert care[ZOJIRUSHI.key].kind == []
    assert STAGG.key not in care


def test_a_product_tip_naming_no_ranked_product_goes_nowhere():
    assert attach([tip("Chefman kettle"), tip("electric kettle")], [ZOJIRUSHI, STAGG]) == {}


def test_a_brand_that_fits_two_products_goes_with_neither():
    blacklock, chef = product("Lodge Blacklock skillet"), product("Lodge Chef Collection skillet")
    assert attach([tip("Lodge", text="season it")], [blacklock, chef], product_type="cast iron skillet") == {}


def test_a_name_written_the_same_way_wins_then_a_specific_product_over_a_brand():
    brand = product("Lodge", loose=True, shown="Lodge (their cast iron skillets)")
    blacklock, chef = product("Lodge Blacklock skillet"), product("Lodge Chef Collection skillet")
    care = attach([tip("Lodge", text="season it", comment="cT1"), tip("Lodge Blacklock", text="dry it", comment="cT2")],
                  [brand, blacklock, chef], product_type="cast iron skillet")
    assert [t.tip for t in care[brand.key].own] == ["season it"]
    assert [t.tip for t in care[blacklock.key].own] == ["dry it"]
    assert chef.key not in care


# --- Kind tips ---

def test_a_tip_about_the_requested_kind_of_product_goes_with_every_product():
    care = attach([tip("electric kettle", is_kind=True), tip("kettles", is_kind=True, comment="cT2")], [ZOJIRUSHI, STAGG])
    for group in (ZOJIRUSHI, STAGG):
        assert care[group.key].own == [] and [t.comment_id for t in care[group.key].kind] == ["cT1", "cT2"]


def knife_kinds():
    misono, victorinox = product("Misono carbon steel gyuto"), product("Victorinox stainless steel")
    kinds = [KindGroup("carbon steel", "carbon steel", product_keys=[misono.key], broader=["steel"]),
             KindGroup("steel", "steel knife", product_keys=[misono.key, victorinox.key]),
             KindGroup("gyuto", "gyuto", product_keys=[misono.key])]
    return misono, victorinox, kinds


def test_a_kind_tip_goes_with_the_products_placed_in_the_kind_it_is_about():
    misono, victorinox, kinds = knife_kinds()
    care = attach([tip("gyuto", is_kind=True, text="hone it weekly")], [misono, victorinox], kinds, "chef knife")
    assert [t.tip for t in care[misono.key].kind] == ["hone it weekly"]
    assert victorinox.key not in care


def test_a_kind_tip_goes_only_with_the_narrowest_kinds_it_is_about():
    # "carbon steel knife" is about carbon steel and about steel; a carbon steel tip isn't for every steel knife.
    misono, victorinox, kinds = knife_kinds()
    care = attach([tip("carbon steel knife", is_kind=True, text="dry it straight away")], [misono, victorinox], kinds,
                  "chef knife")
    assert [t.tip for t in care[misono.key].kind] == ["dry it straight away"]
    assert victorinox.key not in care


def test_a_kind_tip_about_another_kind_goes_nowhere():
    misono, victorinox, kinds = knife_kinds()
    assert attach([tip("cast iron skillet", is_kind=True, text="season it")], [misono, victorinox], kinds,
                  "chef knife") == {}


def test_a_kind_tip_in_two_of_a_products_kinds_goes_with_it_once():
    misono, victorinox, kinds = knife_kinds()
    care = attach([tip("carbon steel gyuto", is_kind=True, text="oil the blade")], [misono, victorinox], kinds,
                  "chef knife")
    assert [t.tip for t in care[misono.key].kind] == ["oil the blade"]


def test_tips_keep_their_order_and_own_and_kind_tips_stay_apart():
    tips = [tip("electric kettle", is_kind=True, comment="cT1"), tip("Zojirushi kettle", comment="cT2"),
            tip("kettle", is_kind=True, comment="cT3"), tip("zojirushi", comment="cT4")]
    care = attach(tips, [ZOJIRUSHI, STAGG])
    assert [t.comment_id for t in care[ZOJIRUSHI.key].own] == ["cT2", "cT4"]
    assert [t.comment_id for t in care[ZOJIRUSHI.key].kind] == ["cT1", "cT3"]
    assert [t.comment_id for t in care[STAGG.key].kind] == ["cT1", "cT3"]


# --- Credible tips only ---

def care_thread() -> Thread:
    return Thread.model_validate(make_thread(id="1kett01", category="kitchen", comments=[
        make_comment("k1aaaa", "1kett01", body="Descale it every 6 months and it lasts forever."),
        make_comment("k1bbbb", "1kett01", body="Use my code KETTLE10! Descale it every month with our powder."),
    ]))


def test_only_tips_from_voices_that_are_not_low_are_kept_with_the_voice_and_its_badges():
    thread = care_thread()
    extraction = Extraction.model_validate({
        "thread_id": "1kett01", "instructions_version": "extract-v7", "extracted_at": "2026-10-09T10:00:00Z",
        "extractor": "claude-code", "mentions": [],
        "care": [{"comment_id": "k1aaaa", "about": "electric kettle", "is_kind": True, "tip": "descale every 6 months",
                  "quote": "Descale it every 6 months and it lasts forever."},
                 {"comment_id": "k1bbbb", "about": "electric kettle", "is_kind": True, "tip": "descale monthly",
                  "quote": "Descale it every month with our powder."}],
    })
    tips = credible_care_tips([thread], {thread.id: check_extraction(extraction, thread)})
    assert [t.comment_id for t in tips] == ["k1aaaa"]  # paid promotion makes the second voice low
    first = tips[0]
    assert first.voice in ("high", "medium") and first.thread_id == "1kett01" and first.is_kind
    assert first.comment_url == "https://www.reddit.com/r/SkincareAddiction/comments/1kett01/comment/k1aaaa/"
    assert isinstance(first.badges, tuple)


def test_copied_text_is_looked_for_once_per_thread(monkeypatch):
    # Module 5's "copied text" red flag (Noemi's decision 3, 11 Oct 2026) compares a whole thread: it is worked out once
    # per thread, however many of its tips are scored.
    looked_at = []
    real = care_tips.copied_comment_ids
    monkeypatch.setattr(care_tips, "copied_comment_ids", lambda thread: looked_at.append(thread.id) or real(thread))
    thread = care_thread()
    extraction = Extraction.model_validate({
        "thread_id": "1kett01", "instructions_version": "extract-v7", "extracted_at": "2026-10-09T10:00:00Z",
        "extractor": "claude-code", "mentions": [],
        "care": [{"comment_id": "k1aaaa", "about": "electric kettle", "is_kind": True, "tip": "descale every 6 months",
                  "quote": "Descale it every 6 months and it lasts forever."},
                 {"comment_id": "k1bbbb", "about": "electric kettle", "is_kind": True, "tip": "descale monthly",
                  "quote": "Descale it every month with our powder."}],
    })
    credible_care_tips([thread], {thread.id: check_extraction(extraction, thread)})
    assert looked_at == ["1kett01"]


def test_an_extraction_without_care_tips_gives_none():
    thread = care_thread()
    extraction = Extraction.model_validate({
        "thread_id": "1kett01", "instructions_version": "extract-v6", "extracted_at": "2026-10-09T10:00:00Z",
        "extractor": "claude-code", "mentions": []})
    assert credible_care_tips([thread], {thread.id: check_extraction(extraction, thread)}) == []


# --- The same tip ---

@pytest.mark.parametrize("a, b", [
    ("descale every 6 months", "Descale every 6 months."),
    ("descale it every 6 months", "descale every 6 months"),
    ("dry your knife straight away", "dry the knife straight away"),
])
def test_tips_in_the_same_words_are_the_same_tip(a, b):
    assert same_tip(a, b)


@pytest.mark.parametrize("a, b", [("descale every 6 months", "descale every month"), ("no dishwasher", "hand wash")])
def test_different_words_are_different_tips(a, b):
    assert not same_tip(a, b)
