"""Module 7's small part of the converge round of 17 Oct 2026 (ws-ranking): Skip these shows the warnings that count,
at most config.SKIP_SHOWN items (Noemi's decision 2 of 16 Oct 2026), and a pick's downsides count only its own
warnings, those about its brand's line as a whole shown apart (item 5; the wording PROPOSED).

All text is made up (engine/tests/ranking_factories.py).
"""

from dataclasses import replace

from engine import answer as wording
from engine import config
from engine.answer import render_markdown, unverified_claims, write_answer
from engine.rank import rank_products
from engine.tests.ranking_factories import bodies_for, mention, mentions


def warning(product, thread, n, opposite=False):
    return replace(mention(product, thread, stance="warn", voice="medium",
                           quote=f"The {product} broke on me, writer {n} in {thread}."), opposite_need=opposite)


# --- Skip these (Noemi's decision 2 of 16 Oct 2026) ---

def test_skip_these_shows_at_most_the_set_number_of_items():
    items = [warning(f"Pan {chr(65 + i)}", t, i) for i in range(8) for t in ("t1", "t2")]
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items), "frying pan")
    assert len(answer.skip) == config.SKIP_SHOWN


def test_a_skipped_products_reason_and_quotes_are_the_warnings_that_count():
    counted = [warning("Pan A", "t1", 1), warning("Pan A", "t2", 2)]
    opposite = warning("Pan A", "t3", 3, opposite=True)
    items = counted + [opposite]
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items), "frying pan")
    (item,) = answer.skip
    assert item.reason.startswith("Warned against by 2 credible voices")
    assert opposite.quote not in [q.text for q in item.quotes]


# --- A pick's downsides: its own, and its brand's line's apart (item 5) ---

def brand_case():
    praise = mentions(4, "Acme Glide pan")
    own = [mention("Acme Glide pan", "t1", stance="warn", voice="medium", quote="The Glide warped on me after a year.")]
    line = [mention("Acme frying pan line", t, stance="warn", voice="medium", quote=f"Acme pans flaked, writer {t}.")
            for t in ("t1", "t2", "t3")]
    items = praise + own
    ranking = rank_products(items, "kitchen")
    return ranking, items, own, line


def test_the_share_line_counts_the_picks_own_warnings_and_names_the_brands_apart():
    ranking, items, own, line = brand_case()
    answer = write_answer(ranking, bodies_for(*items, *line), "frying pan",
                          brand_downsides={"acme-glide-pan": ("Acme frying pan line", line)})
    pick = answer.picks[0]
    assert pick.downsides_share == wording.DOWNSIDES_SHARE_BRAND.format(
        n=1, total=1 + 4, more=3, line="Acme frying pan line")
    assert [q.text for q in pick.downsides][0] == own[0].quote  # its own first, then the line's
    assert {q.text for q in pick.downsides[1:]} <= {m.quote for m in line}
    assert pick.voices["warn"] == 1  # the meter counts its own warnings
    assert unverified_claims(answer, bodies_for(*items, *line)) == []
    assert pick.downsides_share in render_markdown(answer)


def test_with_no_warning_of_its_own_the_line_says_so():
    praise = mentions(4, "Acme Glide pan")
    line = [mention("Acme frying pan line", t, stance="warn", voice="medium", quote=f"Acme pans flaked, writer {t}.")
            for t in ("t1", "t2")]
    answer = write_answer(rank_products(praise, "kitchen"), bodies_for(*praise, *line), "frying pan",
                          brand_downsides={"acme-glide-pan": ("Acme frying pan line", line)})
    pick = answer.picks[0]
    assert pick.downsides_share == wording.DOWNSIDES_BRAND_ONLY.format(more=2, line="Acme frying pan line")
    assert pick.disagreement is None  # no credible voice warned against the pick itself


def test_a_brand_line_picks_own_products_warnings_stay_its_own():
    # The other way round (10 Oct 2026, night): a brand line pick speaks for its specific products, so their warnings
    # are its own and the share line counts them, as before.
    praise = mentions(4, "Acme pans")
    own = [mention("Acme pans", "t1", stance="warn", voice="medium", quote=f"Acme pans chipped, writer {n}.")
           for n in range(2)]
    product = [mention("Acme Pro pan", "t2", stance="warn", voice="medium", quote="The Acme Pro pan warped.")]
    items = praise + own
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items, *product), "frying pan",
                          more_downsides={"acme-pans": product})
    assert answer.picks[0].downsides_share.startswith("3 of 7 ")
