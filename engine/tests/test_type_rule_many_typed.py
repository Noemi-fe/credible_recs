"""The type rule no longer drops a product whole when many of its mentions are typed as the requested type (26 Oct 2026,
the reading builder; Noemi's decision 1 of 26 Oct 2026 and the classics review of 25 Oct 2026).

A product's type was decided for the whole product by the type most of its mentions have (engine.pipeline.
_another_type_by_ai). A healing ointment is typed lip balm in the lip balm threads that mention it and moisturiser in
the moisturiser ones; with every thread read, the lip balm mentions outnumbered the rest and the product was left out
of a moisturiser answer whole. Now a product with at least config.TYPE_RULE_KEEP_MIN_MENTIONS mentions typed as the
requested type, from at least config.TYPE_RULE_KEEP_MIN_THREADS threads, is not left out whole: its mentions of
another type still count for nothing (engine.pipeline._of_another_type), so the product stands on the mentions typed as
the requested type alone. A product with fewer is left out as before: a few mistyped mentions don't bring a cleanser
into a moisturiser answer.

Every product, thread and writer here is made up.
"""

import json
from pathlib import Path

from engine import config, pipeline
from engine.answer import unverified_claims
from engine.group_products import ProductGroup, ProductMention
from engine.pipeline import answer_request
from engine.query import parse_query
from engine.tests.factories import make_comment, make_thread, write_gold

REQUEST = "best moisturiser"


def group(name: str, typed: dict[str, int], threads: int = 20, loose: bool = False,
          quote: str = "I've had it for years.") -> ProductGroup:
    """A product group whose mentions have these types ({type: how many}), spread over `threads` threads."""
    made, number = [], 0
    for product_type, count in typed.items():
        for _ in range(count):
            made.append(ProductMention(f"t{number % threads}", f"c{number}", name, "skincare", "recommend",
                                       product_type=product_type, quote=quote))
            number += 1
    return ProductGroup(key=f"skincare:{name.lower()}", name=name, category="skincare", mentions=made, loose=loose)


def test_the_values_are_a_count_of_mentions_and_of_threads():
    assert config.TYPE_RULE_KEEP_MIN_MENTIONS >= 3 and config.TYPE_RULE_KEEP_MIN_THREADS >= 2
    assert config.TYPE_RULE_KEEP_MIN_MENTIONS >= config.TYPE_RULE_KEEP_MIN_THREADS


def test_a_product_mostly_typed_as_another_type_stays_when_many_mentions_are_typed_as_the_requested_one():
    moisturiser = parse_query(REQUEST, model=None)
    many = config.TYPE_RULE_KEEP_MIN_MENTIONS
    # More mentions typed lip balm than moisturiser, but many typed moisturiser: Aquaphor's case (made-up names).
    assert not pipeline._another_type(group("Willowbark Ointment", {"lip balm": 4 * many, "moisturiser": many}),
                                      moisturiser)
    # The majority alone decided before: it still does for a product with fewer.
    assert pipeline._another_type(group("Willowbark Ointment", {"lip balm": 4 * many, "moisturiser": many - 1}),
                                  moisturiser)


def test_a_few_mistyped_mentions_bring_nothing_in():
    moisturiser = parse_query(REQUEST, model=None)
    assert pipeline._another_type(group("Hollowbrook Cleanser", {"cleanser": 40, "moisturiser": 2}), moisturiser)
    assert pipeline._another_type(group("Hollowbrook Cleanser", {"cleanser": 40}), moisturiser)


def test_the_mentions_must_come_from_enough_threads():
    moisturiser = parse_query(REQUEST, model=None)
    many, spread = config.TYPE_RULE_KEEP_MIN_MENTIONS, config.TYPE_RULE_KEEP_MIN_THREADS
    typed = {"lip balm": 4 * many, "moisturiser": many}
    # All of the moisturiser mentions come from one thread (the others' threads are many): one thread's talk isn't many.
    one_thread = group("Willowbark Ointment", {"lip balm": 4 * many}, threads=20)
    one_thread.mentions.extend(ProductMention("t99", f"x{i}", "Willowbark Ointment", "skincare", "recommend",
                                              product_type="moisturiser", quote="I've had it for years.")
                               for i in range(many))
    assert pipeline._another_type(one_thread, moisturiser)
    assert not pipeline._another_type(group("Willowbark Ointment", typed, threads=spread), moisturiser)
    assert pipeline._another_type(group("Willowbark Ointment", typed, threads=spread - 1), moisturiser)


def test_a_mention_typed_as_another_type_counts_for_nothing_whatever_its_words_say():
    # Counting the writer's words as well (the first version of this rule, 26 Oct 2026) kept a lip cream the AI called a
    # lip balm in a moisturiser answer, a glycolic toner in an exfoliant answer and an oven the AI called an air fryer
    # oven in an air fryer answer, from the library's own groups: only the AI's type says what was meant to be asked.
    moisturiser = parse_query(REQUEST, model=None)
    many = config.TYPE_RULE_KEEP_MIN_MENTIONS
    cream = group("Fernwood Lip Cream", {"lip balm": 3 * many}, quote="I use this cream as a moisturiser on my hands too.")
    assert pipeline._another_type(cream, moisturiser)
    air_fryer = parse_query("air fryer for a small kitchen", model=None)
    oven = group("Larkfield Smart Oven Air Fryer Pro", {"air fryer oven": 3 * many}, quote="The air fryer works well.")
    assert pipeline._another_type(oven, air_fryer)


def test_another_kind_of_type_in_the_ais_own_words_is_another_type_too():
    # "ointment" is the AI's own word, not one of the tool's types: still another type than a moisturiser.
    moisturiser = parse_query(REQUEST, model=None)
    many = config.TYPE_RULE_KEEP_MIN_MENTIONS
    assert not pipeline._another_type(group("Willowbark Ointment", {"ointment": 3 * many, "moisturiser": many}),
                                      moisturiser)
    assert pipeline._another_type(group("Willowbark Ointment", {"ointment": 3 * many, "moisturiser": many - 1}),
                                  moisturiser)


def test_the_requested_type_wins_where_it_is_the_majority_as_before():
    moisturiser = parse_query(REQUEST, model=None)
    assert not pipeline._another_type(group("Pebbleford Cream", {"moisturiser": 5, "lip balm": 2}), moisturiser)
    assert not pipeline._another_type(group("Pebbleford Cream", {"moisturiser": 1}), moisturiser)


def test_the_kinds_kept_out_of_a_type_stay_out_whatever_the_count():
    # Noemi's decision (g) of 19 Oct 2026: an essence is no toner. The new count never lets one in.
    toner = parse_query("hydrating toner for dehydrated skin", model=None)
    many = config.TYPE_RULE_KEEP_MIN_MENTIONS
    assert pipeline._another_type(group("COSRX Snail 96 Mucin Power Essence", {"essence": 3 * many, "toner": many}),
                                  toner)


def test_a_brand_or_line_is_judged_as_before():
    # A brand's whole line (a loose group) keeps its mentions of the requested type in _of_another_type already; the new
    # count is for one product, so the brand rules (which lines are clear brands) are not moved by it.
    moisturiser = parse_query(REQUEST, model=None)
    many = config.TYPE_RULE_KEEP_MIN_MENTIONS
    brand = group("Willowbark", {"lip balm": 4 * many, "moisturiser": many}, loose=True)
    assert pipeline._another_type(brand, moisturiser)


# --- Through the pipeline: a made-up library ---

OINTMENT = "Willowbark Ointment"
CREAM = "Pebbleford Cream"
CLEANSER = "Hollowbrook Cleanser"


def written(product: str, years: int, where: str) -> str:
    return f"I've used the {product} {where} for {years} years and it is still great."


def library(tmp_path: Path, lip_mentions: int, moisturiser_mentions: int, moisturiser_threads: int,
            cleanser_mistyped: int = 2) -> Path:
    """Moisturiser threads (and lip balm ones that mention the same ointment). Each of the cream's mentions is its own
    writer's, typed moisturiser, in a thread of its own; the ointment is typed lip balm in `lip_mentions` comments and
    moisturiser in `moisturiser_mentions`, spread over `moisturiser_threads` threads; the cleanser is typed cleanser in
    many, and moisturiser in `cleanser_mistyped`."""
    threads, extractions = [], {}
    total = max(moisturiser_threads, 6)
    for number in range(total):
        tid = f"1mz{number:03d}"
        comments, found = [], []

        def add(product, body, product_type):
            cid = f"{tid}c{len(comments)}"
            comments.append(make_comment(cid, thread_id=tid, body=body))
            found.append({"comment_id": cid, "product": product, "category": "skincare", "stance": "recommend",
                          "quote": body, "product_type": product_type})

        add(CREAM, written(CREAM, 3 + number, "on my face"), "moisturiser")
        add(CREAM, written(CREAM, 4 + number, "every winter"), "moisturiser")
        add(CLEANSER, written(CLEANSER, 3 + number, "to wash my face"), "cleanser")
        if number < moisturiser_threads:
            # the ointment's moisturiser mentions: spread evenly over the threads that carry them
            share = moisturiser_mentions // moisturiser_threads + (number < moisturiser_mentions % moisturiser_threads)
            for k in range(share):
                add(OINTMENT, written(OINTMENT, 2 + k, "as a moisturiser on my dry skin"), "moisturiser")
        for k in range(lip_mentions // total + (number < lip_mentions % total)):
            add(OINTMENT, written(OINTMENT, 2 + k, "on my lips"), "lip balm")
        if number < cleanser_mistyped:
            add(CLEANSER, written(CLEANSER, 5, "as a moisturiser on my face"), "moisturiser")
        threads.append(make_thread(id=tid, community="SkincareAddiction", category="skincare",
                                   title="Best moisturiser?", body="Any advice?",
                                   url=f"https://www.reddit.com/r/SkincareAddiction/comments/{tid}/t/",
                                   comments=comments))
        extractions[tid] = found
    root = write_gold(tmp_path / "library", threads, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for tid, found in extractions.items():
        (root / "extracted" / f"{tid}.json").write_text(json.dumps({
            "thread_id": tid, "instructions_version": "extract-v12", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": found}), encoding="utf-8")
    return root


def shown(result) -> list[str]:
    return [p.name for p in result.answer.picks]


def test_a_product_typed_lip_balm_in_most_mentions_is_a_pick_on_its_moisturiser_mentions(tmp_path):
    many, spread = config.TYPE_RULE_KEEP_MIN_MENTIONS, config.TYPE_RULE_KEEP_MIN_THREADS
    root = library(tmp_path, lip_mentions=4 * many, moisturiser_mentions=many, moisturiser_threads=max(spread, 6))
    result = answer_request(REQUEST, library_dir=root, more_threads=None)
    assert OINTMENT in shown(result)
    pick = next(p for p in result.ranking.products if p.name == OINTMENT)
    # It stands on the mentions typed as a moisturiser alone: the lip balm ones count for nothing.
    assert pick.breakdown.recommends == many
    assert OINTMENT in result.mentions_of_another_type
    assert OINTMENT not in result.left_out_as_other_type
    assert unverified_claims(result.answer, result.bodies) == []


def test_with_too_few_moisturiser_mentions_it_is_left_out_as_before(tmp_path):
    many = config.TYPE_RULE_KEEP_MIN_MENTIONS
    root = library(tmp_path, lip_mentions=4 * many, moisturiser_mentions=many - 1, moisturiser_threads=6)
    result = answer_request(REQUEST, library_dir=root, more_threads=None)
    assert OINTMENT not in shown(result)
    assert OINTMENT in result.left_out_as_other_type


def test_a_cleanser_with_a_couple_of_mistyped_mentions_is_not_a_moisturiser(tmp_path):
    root = library(tmp_path, lip_mentions=0, moisturiser_mentions=0, moisturiser_threads=6, cleanser_mistyped=2)
    result = answer_request(REQUEST, library_dir=root, more_threads=None)
    assert shown(result) == [CREAM]
    assert CLEANSER not in shown(result) and CLEANSER in result.left_out_as_other_type
