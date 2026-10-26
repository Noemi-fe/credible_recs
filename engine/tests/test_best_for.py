"""The "best for" label of a pick (26 Oct 2026, the bestfor builder; Noemi's decision 3, third part).

A label is worked out from our own evidence only: what a pick's credible voices write about (the topics of
config.BEST_FOR_TOPICS, found in their words about the product), how many of them wrote after long-term use, and its
checked price against the other picks'. At most one a pick, never the same on two picks, only when clearly supported
(at least config.BEST_FOR_MIN_VOICES voices, more than any other pick has, a real share of the pick's own voices) and
never more than the voices say. All text is made up (engine/tests/ranking_factories.py).
"""

import re
from dataclasses import replace
from datetime import date, timedelta

import pytest

from engine import answer as wording
from engine import best_for, config
from engine.answer import ShownPrice, answer_to_dict, render_markdown, unverified_claims, write_answer
from engine.prices import Price, PriceCheck
from engine.rank import rank_products
from engine.tests.ranking_factories import bodies_for, mention

TODAY = date(2026, 10, 26)
SHORT = "short-term use"
LONG = "long-term use"


def label_text(topic: str) -> str:
    return config.BEST_FOR_LABEL.format(topic=config.BEST_FOR_TOPICS[topic]["phrase"])


def voices(product: str, n: int, about: tuple[str, ...] = (), with_topic: int = 0, evidence: str = SHORT,
           first_thread: int = 1):
    """n credible recommendations of one product over two threads; the first `with_topic` talk about `about`."""
    items = []
    for i in range(n):
        thread = f"t{first_thread + i % 2}"
        item = mention(product, thread, evidence=evidence, category="skincare")
        items.append(replace(item, topics=about if i < with_topic else ()))
    return items


def case(**products):
    """{name: (voices, with_topic[, topic][, evidence])} -> (items, ranking); the topic defaults to sensitive skin."""
    items = []
    for name, spec in products.items():
        n, with_topic, *rest = spec
        topic = rest[0] if rest else "sensitive skin"
        evidence = rest[1] if len(rest) > 1 else SHORT
        items += voices(name.replace("_", " "), n, (topic,), with_topic, evidence)
    return items, rank_products(items, "skincare")


def written(items, ranking, **kwargs):
    return write_answer(ranking, bodies_for(*items), "moisturiser", **kwargs)


# --- Which topics a writer's words talk about ---

def test_every_topic_is_named_in_its_own_words_and_says_no_more_than_they_do():
    # "Best for eczema" isn't allowed unless the voices talk about eczema: the label names a thing its own words hold.
    for key, topic in config.BEST_FOR_TOPICS.items():
        assert topic["words"] and topic["phrase"] and topic["categories"]
        assert set(topic["categories"]) <= set(config.THREAD_CATEGORIES)
        assert best_for.topics_in(topic["words"][0], topic["categories"][0]) == (key,) or key in best_for.topics_in(
            topic["words"][0], topic["categories"][0]), key
        # Every word of the phrase that names something is one the topic's own words hold ("dandruff control" says more
        # than "dandruff" does): the label says what the voices say.
        for named in (w for w in re.split(r"[\s-]+", topic["phrase"]) if w not in best_for.PHRASE_FILLER):
            assert any(named[:4] in word.replace("-", " ") for word in topic["words"]), (key, named)


@pytest.mark.parametrize("text, topic", [
    ("i have sensitive skin and this never stung", "sensitive skin"),
    ("my skin is very sensitive and it was fine", "sensitive skin"),
    ("it doesn't sting my sensitive skin", "sensitive skin"),  # the negation is of the sting, not of the praise
    ("never irritated my sensitive skin", "sensitive skin"),
    ("works on my dry skin through winter", "dry skin"),
    ("great for oily skin, no shine by noon", "oily skin"),
])
def test_a_topic_is_found_when_the_writer_says_it(text, topic):
    assert topic in best_for.topics_in(text, "skincare")


@pytest.mark.parametrize("text", [
    "not for sensitive skin, avoid it",  # the writer says the opposite
    "it isn't good on dry skin",
    "this stings my sensitive skin",  # a complaint in the same clause
    "doesn't work for sensitive skin",
    "my sensitive teeth hate cold drinks",  # another thing that is sensitive
    "i have drysskin",  # inside another word
    "",
])
def test_a_topic_is_not_found_when_the_words_say_otherwise_or_are_another_thing(text):
    assert best_for.topics_in(text, "skincare") == ()


def test_a_topic_belongs_to_its_categories_only():
    assert "sensitive skin" in best_for.topics_in("good for sensitive skin", "skincare")
    assert "sensitive skin" not in best_for.topics_in("good for sensitive skin", "kitchen")
    assert "quiet" in best_for.topics_in("so quiet i forget it is on", "kitchen")
    assert "quiet" not in best_for.topics_in("so quiet i forget it is on", "skincare")
    assert "quiet" in best_for.topics_in("so quiet i forget it is on", "general")


def test_a_clause_that_complains_does_not_count():
    assert "comfort" not in best_for.topics_in("comfortable and poor quality overall", "general")
    assert "comfort" not in best_for.topics_in("not comfortable after an hour", "general")
    assert "comfort" in best_for.topics_in("comfortable even after an hour", "general")
    # A complaint in another clause of the sentence does not spoil it.
    assert "comfort" in best_for.topics_in("poor battery, but comfortable even after an hour", "general")


def test_the_words_of_the_products_own_name_are_not_the_writers_praise():
    # "Bose QuietComfort" written "quiet comfort", and a "Gentle Cleanser" by its name: neither is praise.
    assert best_for.topics_in("my bose quiet comfort headphones are 5 years old", "general", ("Bose QuietComfort",)) == ()
    assert "quiet" in best_for.topics_in("my bose quiet comfort headphones are 5 years old", "general")  # without the name
    assert best_for.topics_in("i love the acme gentle cleanser", "skincare", ("Acme Gentle Cleanser",)) == ()
    assert "gentle" in best_for.topics_in("i love the acme cleanser, so gentle", "skincare", ("Acme Gentle Cleanser",))
    assert "quiet" in best_for.topics_in("the acme kettle is quiet", "kitchen", ("Acme kettle",))


def test_praise_of_customer_service_and_warranty_needs_the_praise_not_the_bare_word():
    assert "customer service" in best_for.topics_in("great customer service when the lid cracked", "general")
    assert best_for.topics_in("i called customer service and waited", "general") == ()
    assert "warranty" in best_for.topics_in("they replaced it under warranty, no questions", "general")
    assert best_for.topics_in("it is out of warranty now", "general") == ()


# --- A topic label: clearly supported, and more than the other picks have ---

def test_the_pick_with_most_voices_about_a_topic_gets_the_label_with_its_numbers():
    items, ranking = case(Acme_cream=(6, 4), Bolt_cream=(4, 1), Cove_cream=(3, 0))
    acme, bolt, cove = written(items, ranking).picks
    assert acme.best_for.text == label_text("sensitive skin") == "Most praised for sensitive skin"
    assert acme.best_for.kind == "topic"
    assert "4 of its 6 credible voices" in acme.best_for.basis and "sensitive skin" in acme.best_for.basis
    assert "1 and 0" in acme.best_for.basis  # what the other picks have
    assert bolt.best_for is None and cove.best_for is None


def test_one_voice_is_not_enough():
    items, ranking = case(Acme_cream=(6, 1), Bolt_cream=(4, 0), Cove_cream=(3, 0))
    assert config.BEST_FOR_MIN_VOICES >= 2
    assert [p.best_for for p in written(items, ranking).picks] == [None, None, None]


def test_a_tie_gives_the_label_to_nobody():
    items, ranking = case(Acme_cream=(6, 3), Bolt_cream=(5, 3), Cove_cream=(3, 0))
    assert [p.best_for for p in written(items, ranking).picks] == [None, None, None]


def test_the_leader_needs_a_real_share_of_its_own_voices():
    # 2 of 40 voices talk about it: more than the others' 0, but not what its voices are about.
    items, ranking = case(Acme_cream=(40, 2), Bolt_cream=(4, 0), Cove_cream=(3, 0))
    assert config.BEST_FOR_MIN_SHARE > 2 / 40
    assert [p.best_for for p in written(items, ranking).picks] == [None, None, None]


def test_a_small_pick_can_lead_on_its_share_of_a_bigger_leader_s_count_only_by_having_more_voices():
    # "Most praised" is a count of voices: the pick with fewer voices does not take it from one with more.
    items, ranking = case(Acme_cream=(8, 4), Bolt_cream=(4, 3), Cove_cream=(3, 0))
    acme, bolt, _ = written(items, ranking).picks
    assert acme.best_for is not None and bolt.best_for is None


def test_a_pick_never_gets_two_labels_and_two_picks_never_get_the_same_one():
    items = (voices("Acme cream", 6, ("sensitive skin", "dry skin"), 5) + voices("Bolt cream", 6, ("dry skin",), 3)
             + voices("Cove cream", 5, ("sensitive skin",), 2))
    answer = written(items, rank_products(items, "skincare"))
    labels = [p.best_for.text for p in answer.picks if p.best_for]
    assert len(labels) == len(set(labels))
    assert all(isinstance(p.best_for.text, str) for p in answer.picks if p.best_for)
    assert len(answer.picks) == 3


def test_a_topic_the_request_asks_about_is_no_label():
    items, ranking = case(Acme_cream=(6, 4), Bolt_cream=(4, 1), Cove_cream=(3, 0))
    from engine.needs import Need
    asked = written(items, ranking, request="a moisturiser for sensitive skin", needs=(Need("sensitive"),))
    assert [p.best_for for p in asked.picks] == [None, None, None]
    typed = written(items, ranking, request="moisturiser for sensitive skin")  # by its words, with no needs given
    assert [p.best_for for p in typed.picks] == [None, None, None]


def test_a_single_pick_has_nothing_to_be_best_against():
    items, ranking = case(Acme_cream=(6, 5))
    answer = written(items, ranking)
    assert len(answer.picks) == 1 and answer.picks[0].best_for is None


def test_a_label_is_one_of_the_topics_of_the_category_it_was_found_in():
    items, ranking = case(Acme_cream=(6, 4), Bolt_cream=(4, 1), Cove_cream=(3, 0))
    label = written(items, ranking).picks[0].best_for
    assert label.text.removeprefix("Most praised for ") in {t["phrase"] for t in config.BEST_FOR_TOPICS.values()}


# --- Long-term use ---

def test_the_pick_with_most_voices_after_long_term_use_gets_that_label():
    items = (voices("Acme cream", 6, (), 0, LONG) + voices("Bolt cream", 4, (), 0, SHORT)
             + voices("Cove cream", 3, (), 0, SHORT))
    acme, bolt, cove = written(items, rank_products(items, "skincare")).picks
    assert acme.best_for.text == config.BEST_FOR_LONG_TERM_LABEL
    assert acme.best_for.kind == "long-term use"
    assert "6 of its 6 credible voices" in acme.best_for.basis
    assert bolt.best_for is None and cove.best_for is None


def test_long_term_use_needs_the_minimum_and_a_lead_like_any_other_label():
    one = voices("Acme cream", 6, (), 0, SHORT)
    one[0] = replace(one[0], evidence=LONG)
    items = one + voices("Bolt cream", 4, (), 0, SHORT) + voices("Cove cream", 3, (), 0, SHORT)
    assert [p.best_for for p in written(items, rank_products(items, "skincare")).picks] == [None, None, None]
    tied = voices("Acme cream", 5, (), 0, LONG) + voices("Bolt cream", 5, (), 0, LONG) + voices("Cove cream", 3, (), 0, SHORT)
    assert [p.best_for for p in written(tied, rank_products(tied, "skincare")).picks] == [None, None, None]


def test_long_term_use_is_no_label_when_another_pick_has_a_clearly_better_share():
    # Acme has the most voices after long-term use (8), but Bolt's 5 are all of its voices: Acme is only the bigger pick.
    acme = voices("Acme cream", 10, (), 0, SHORT)
    acme = [replace(m, evidence=LONG) if i < 8 else m for i, m in enumerate(acme)]
    items = acme + voices("Bolt cream", 5, (), 0, LONG) + voices("Cove cream", 3, (), 0, SHORT)
    assert [p.best_for for p in written(items, rank_products(items, "skincare")).picks] == [None, None, None]
    # With its share ahead by the set margin, the same count is a label.
    ahead = voices("Acme cream", 10, (), 0, LONG) + voices("Bolt cream", 5, (), 0, SHORT) + voices("Cove cream", 3, (), 0, SHORT)
    first = written(ahead, rank_products(ahead, "skincare")).picks[0]
    assert first.best_for.kind == "long-term use" and config.BEST_FOR_LONG_TERM_SHARE_LEAD < 1


def test_a_topic_comes_before_long_term_use_and_price_for_the_same_pick():
    items = (voices("Acme cream", 6, ("sensitive skin",), 4, LONG) + voices("Bolt cream", 4, (), 0, SHORT)
             + voices("Cove cream", 3, (), 0, SHORT))
    answer = written(items, rank_products(items, "skincare"))
    assert answer.picks[0].best_for.kind == "topic"


# --- Price: checked, in the shopper's region, against every other pick's ---

def shop_price(product: str, amount: float, currency: str = "GBP", checked_on: date = TODAY - timedelta(days=3)) -> Price:
    return Price(product=product, category="skincare", price=amount, currency=currency, shop="Made-up Shop",
                 url="https://shop.example/" + product.lower().replace(" ", "-"), checked_on=checked_on)


def priced(items, amounts, currency="GBP", **kwargs):
    ranking = rank_products(items, "skincare")
    checks = {}
    for key, amount in amounts.items():
        if amount is not None:
            checks[key] = PriceCheck(shop_price(key.replace("-", " "), amount, currency, **kwargs), "no budget")
    return ranking, checks


def three_unlabelled():
    return (voices("Acme cream", 5, (), 0, SHORT) + voices("Bolt cream", 4, (), 0, SHORT)
            + voices("Cove cream", 3, (), 0, SHORT))


def test_the_clearly_cheapest_pick_gets_the_price_label_from_checked_prices():
    items = three_unlabelled()
    ranking, checks = priced(items, {"acme-cream": 25.0, "bolt-cream": 12.0, "cove-cream": 30.0})
    answer = written(items, ranking, prices=checks, today=TODAY)
    labelled = [p for p in answer.picks if p.best_for]
    assert [p.name for p in labelled] == ["Bolt cream"]
    assert labelled[0].best_for.text == config.BEST_FOR_PRICE_LABEL and labelled[0].best_for.kind == "price"
    assert "£12" in labelled[0].best_for.basis and "£25" in labelled[0].best_for.basis


def test_a_price_label_needs_every_pick_to_have_a_checked_price():
    items = three_unlabelled()
    ranking, checks = priced(items, {"acme-cream": 25.0, "bolt-cream": 12.0, "cove-cream": None})
    assert all(p.best_for is None for p in written(items, ranking, prices=checks, today=TODAY).picks)


def test_a_price_label_needs_a_clear_gap():
    items = three_unlabelled()
    ranking, checks = priced(items, {"acme-cream": 12.5, "bolt-cream": 12.0, "cove-cream": 30.0})
    assert 12.0 > 12.5 * (1 - config.BEST_FOR_PRICE_GAP)  # the premise: £12 is less than the set gap below £12.50
    answer = written(items, ranking, prices=checks, today=TODAY)
    assert all(p.best_for is None for p in answer.picks)


def test_a_price_label_needs_prices_checked_recently():
    items = three_unlabelled()
    old = TODAY - timedelta(days=config.PRICE_MAX_AGE_DAYS + 1)
    ranking, checks = priced(items, {"acme-cream": 25.0, "bolt-cream": 12.0, "cove-cream": 30.0}, checked_on=old)
    assert all(p.best_for is None for p in written(items, ranking, prices=checks, today=TODAY).picks)


def test_a_brand_lines_from_price_is_no_price_to_compare():
    items = three_unlabelled()
    ranking, checks = priced(items, {"acme-cream": 25.0, "bolt-cream": 12.0, "cove-cream": 30.0})
    checks["bolt-cream"] = PriceCheck(checks["bolt-cream"].price, "no budget", from_price=True)
    assert all(p.best_for is None for p in written(items, ranking, prices=checks, today=TODAY).picks)


def test_the_prices_must_be_in_one_currency_the_shoppers_region_uses():
    items = three_unlabelled()
    ranking, checks = priced(items, {"acme-cream": 25.0, "bolt-cream": 12.0, "cove-cream": 30.0}, currency="USD")
    uk = written(items, ranking, prices=checks, today=TODAY, region="uk")
    assert all(p.best_for is None for p in uk.picks)  # dollars are not a UK shopper's prices
    us = written(items, ranking, prices=checks, today=TODAY, region="us")
    assert [p.name for p in us.picks if p.best_for] == ["Bolt cream"]
    elsewhere = written(items, ranking, prices=checks, today=TODAY, region="elsewhere")
    assert all(p.best_for is None for p in elsewhere.picks)  # no region of its own: no price label


def test_a_us_shopper_is_not_labelled_from_the_uk_pounds():
    items = three_unlabelled()
    ranking, checks = priced(items, {"acme-cream": 25.0, "bolt-cream": 12.0, "cove-cream": 30.0})
    assert all(p.best_for is None for p in written(items, ranking, prices=checks, today=TODAY, region="us").picks)


def test_the_label_is_in_the_json_and_the_text_and_no_quote_changes():
    items, ranking = case(Acme_cream=(6, 4), Bolt_cream=(4, 1), Cove_cream=(3, 0))
    answer = written(items, ranking)
    data = answer_to_dict(answer)
    assert data["picks"][0]["best_for"] == {"text": "Most praised for sensitive skin", "basis": answer.picks[0].best_for.basis,
                                            "kind": "topic"}
    assert data["picks"][1]["best_for"] is None
    assert "Most praised for sensitive skin" in render_markdown(answer)
    assert unverified_claims(answer, bodies_for(*items)) == []


def test_the_label_comes_from_the_evidence_alone_so_the_same_ranking_gives_the_same_labels():
    items, ranking = case(Acme_cream=(6, 4), Bolt_cream=(4, 1), Cove_cream=(3, 0))
    first = [p.best_for for p in written(items, ranking).picks]
    second = [p.best_for for p in written(list(reversed(items)), rank_products(list(reversed(items)), "skincare")).picks]
    assert first == second


def test_the_wording_is_decided_in_config_and_marked():
    source = (config.__file__ and open(config.__file__, encoding="utf-8").read())
    section = source[source.index("# --- Build round 26 Oct 2026: bestfor ---"):]
    assert "(26 Oct 2026, the bestfor builder; approved in principle by Noemi, wording Claude's)" in section


# --- Through the pipeline: the topics are noted for credible recommendations, from the writer's own words ---

def quiet_kettle_library(tmp_path):
    """Two kettle threads (made-up words): the Zojirushi's writers say it is quiet, the others' say nothing of it, and one
    Zojirushi writer says it is loud (a clause that complains does not count)."""
    import json

    from engine.tests.factories import write_gold
    from engine.tests.test_pipeline import comment, kettle_thread, mention as extracted

    spoken = {"Zojirushi": ["Mine is so quiet that I forget it is on, and I have used it for {n} years.",
                            "Quiet and quick, I have used mine for {n} years.",
                            "Mine is very loud, but it has boiled right for {n} years.",
                            "Mine boils right and has done for {n} years."],
              "Bonavita": ["Mine boils right and has done for {n} years."] * 3,
              "Cove": ["The Cove is fine, and has done well for {n} years."] * 3}
    first, second, extractions = [], [], {"1kett01": [], "1kett02": []}
    for brand, sentences in spoken.items():
        product = f"{brand} kettle"
        for i, sentence in enumerate(sentences):
            thread = "1kett01" if i % 2 == 0 else "1kett02"
            cid = f"{brand[:3].lower()}{i}"
            text = f"{product}: " + sentence.format(n=i + 3)
            (first if thread == "1kett01" else second).append(comment(cid, thread, text))
            extractions[thread].append(extracted(cid, product, text))
    root = write_gold(tmp_path / "library", [kettle_thread("1kett01", first), kettle_thread("1kett02", second)],
                      voices=None, mentions=None)
    (root / "extracted").mkdir()
    for thread_id, found in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v5", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": found}), encoding="utf-8")
    return root


def test_the_pipeline_notes_topics_of_credible_recommendations_only(tmp_path):
    from engine.pipeline import answer_request

    result = answer_request("electric kettle", quiet_kettle_library(tmp_path), today=date(2026, 10, 9))
    credible = {m.comment_id: m for p in result.ranking.products for m in p.mentions}
    quiet = [m for m in credible.values() if "quiet" in m.topics]
    assert {m.product_name for m in quiet} == {"Zojirushi kettle"} and len(quiet) == 2
    assert all(m.stance == "recommend" and m.voice != "low" for m in quiet)
    assert credible["zoj2"].topics == ()  # "very loud": a clause that complains (and "quiet" is not said)
    assert all(m.topics == () for m in credible.values() if m.product_name != "Zojirushi kettle")
    zojirushi = next(p for p in result.answer.picks if p.name == "Zojirushi kettle")
    assert zojirushi.best_for and zojirushi.best_for.text == "Most praised for being quiet"
    assert all(p.best_for is None for p in result.answer.picks if p is not zojirushi)
