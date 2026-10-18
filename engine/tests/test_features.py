"""Features a request names for its product (Noemi's decision 1 of 16 Oct 2026; engine/features.py, 17 Oct 2026).

Module 1 runs on its rules here (the open model is never loaded in tests: conftest); every comment is made up.
"""

import pytest

from engine.features import feature_note, praised_for, request_features
from engine.query import parse_query


def features(request: str) -> list[str]:
    return [f.name for f in request_features(parse_query(request))]


@pytest.mark.parametrize("request_text, expected", [
    ("noise cancelling headphones", ["noise cancelling"]),
    ("noise cancelling headphones for commuting", ["noise cancelling"]),  # "for commuting" is a use, not a feature
    ("gaming laptop under £1000", ["gaming"]),
    ("automatic watch under £500", ["automatic"]),
    ("quiet kettle", ["quiet"]),
    ("a kettle that's quiet", ["quiet"]),  # the same ask, said after the noun
    ("true wireless earbuds for running", ["true wireless"]),
    ("mechanical keyboard", ["mechanical"]),
    ("cordless drill", ["cordless"]),
    ("stainless steel pan for searing", ["stainless steel"]),
])
def test_a_feature_named_before_the_product_noun(request_text, expected):
    assert features(request_text) == expected


@pytest.mark.parametrize("request_text", [
    "a laptop for university",  # a use after the noun
    "office chair for back pain",
    "coffee machine",  # "coffee" only names the product
    "portable charger",  # the product noun (a power bank) isn't written
    "first chef's knife under £100 for a home cook",  # the buyer, not the knife
    "non stick pan without teflon that lasts",  # a checked requirement: the facts settle it
    "non-stick frying pan without PFAS that actually lasts",  # the same, written with a hyphen
    "electric kettle that lasts 10+ years",  # "electric" is the type's own name
    "retinol for a beginner with sensitive skin",  # skincare keeps its own need rule
    "salicylic acid for acne",
])
def test_no_feature(request_text):
    assert features(request_text) == []


def feature(request_text: str):
    (found,) = request_features(parse_query(request_text))
    return found


@pytest.mark.parametrize("text", [
    "the noise cancelling on these is superb on the train.",
    "best anc i have had, and the battery lasts all week.",
    "noise-canceling is great for flights.",
])
def test_praise_for_a_phrase_feature(text):
    assert praised_for(feature("noise cancelling headphones"), text)


@pytest.mark.parametrize("text", [
    "they sound great but there is no noise cancelling at all.",  # denied
    "lovely studio headphones for mixing at home.",  # not said
])
def test_no_praise_for_a_phrase_feature(text):
    assert not praised_for(feature("noise cancelling headphones"), text)


def test_a_thread_asking_for_the_feature_counts_unless_the_comment_says_otherwise():
    found = feature("adjustable dumbbells")
    assert praised_for(found, "these have been great for three years.", thread_asks=True)
    assert not praised_for(found, "these have been great for three years.", thread_asks=False)
    assert not praised_for(found, "they are not adjustable, but great.", thread_asks=True)


@pytest.mark.parametrize("text, praised", [
    ("much quieter than my old one and it boils fast.", True),
    ("it is whisper quiet.", True),
    ("not loud at all, and pours well.", True),
    ("had it for six years, very noisy, but it never broke.", False),  # talks about it: against
    ("it is not quiet, but it lasts.", False),
    ("pours well and lasts.", False),
])
def test_praise_for_quiet(text, praised):
    assert praised_for(feature("quiet kettle"), text) is praised


def test_a_name_saying_the_opposite_is_never_praised():
    found = feature("cordless drill")
    text = "this one is just as good as new after 12 years. cordless can be handy, but i skip the batteries."
    assert praised_for(found, text, names=("Kilo drill",))
    assert not praised_for(found, text, names=("corded Kilo drill",))


def test_the_note_names_the_features_no_pick_is_praised_for():
    found = request_features(parse_query("noise cancelling headphones"))
    note = feature_note(found, [(), ()], "headphones")
    assert '"noise cancelling"' in note and "headphones" in note
    assert feature_note(found, [("noise cancelling",), ()], "headphones") is None
    assert feature_note(found, [], "headphones") is None  # no picks: the answer's own message says why
    one = feature_note(found, [()], "headphones", "headphones")
    assert one.startswith("No credible voice in the threads we read praised this pick for")
    assert feature_note((), [()], "headphones") is None


@pytest.mark.parametrize("text", [
    "if you want noise cancelling, get something else; these are lovely at home.",
    "i'd pick these over the noise cancelling ones any day.",
])
def test_a_condition_or_a_setting_aside_is_no_praise(text):
    assert not praised_for(feature("noise cancelling headphones"), text)


def test_skipping_the_feature_is_no_praise_either():
    assert not praised_for(feature("gaming laptop"), "skip the gaming laptops, this one just works for uni.")
    assert praised_for(feature("gaming laptop"), "great for gaming on a budget, runs everything i play.")


def test_a_material_counts_only_in_the_writers_own_words_about_the_product():
    found = feature("stainless steel pan for searing")
    assert found.material
    names = ("Brightmoor frying pan line", "Brightmoor tri-ply")
    assert praised_for(found, "my brightmoor tri-ply stainless pan sears beautifully.", names)
    assert praised_for(found, "i've had it for ten years. it's stainless steel and still looks new.", names)
    assert not praised_for(found, "go stainless steel every time. for eggs, though, a brightmoor non stick is fine.",
                           names)
    assert not praised_for(found, "i heat my stainless on medium. the brightmoor is my egg pan.", names)
    # A thread asking for a material gets answers proposing others: its ask counts for nothing.
    assert not praised_for(found, "brightmoor has been great.", names, thread_asks=True)


def test_true_wireless_is_said_as_wireless_too():
    found = feature("true wireless earbuds for running")
    assert praised_for(found, "these wireless buds stay in on long runs.")
