"""Which quote comes first, within Noemi's rule 4 of 15 Oct 2026 (17 Oct 2026, the converge round, item 6).

Her rule: a quote shown must be the most significant and coherent part of its comment for the stance it backs. A
pick's first quote is the one a tester reads; from the breadth-first review of 16 Oct 2026 (D) and the 17 Oct sweep,
some first quotes opened by agreeing with another writer ("Agreed; ...", "Seconded.", "Yeah ..."), named another
product first (a moisturiser pick's quote mostly about CeraVe) or told someone else's experience ("my sister swears by
it"). Each such quote now comes after a clearer one of the same stance; with none, it is still shown. The words shown
never change, only their order.

All text is made up (engine/tests/ranking_factories.py).
"""

from engine.answer import write_answer
from engine.rank import rank_products
from engine.tests.ranking_factories import bodies_for, mention, mentions


def first_quotes(items, product_type="electric kettle", category="kitchen", bodies=None):
    answer = write_answer(rank_products(items, category), bodies_for(*items) | (bodies or {}), product_type)
    return answer, [q.text for q in answer.picks[0].quotes]


CLEAR = "My Acme kettle has boiled twice a day for nine years without a fault."


def test_a_quote_opening_by_agreeing_with_another_writer_comes_after_a_clearer_one():
    for opener in ("Agreed; my Acme kettle has been great for years, no complaints at all.",
                   "Seconded. The Acme kettle is the one I'd buy again, it has lasted ages.",
                   "Yeah my Acme kettle is still going strong after six years of use.",
                   "I second the Acme kettle, mine has been flawless for five years."):
        agreeing = mention("Acme kettle", "t1", quote=opener, weight=2.0)
        clear = mention("Acme kettle", "t2", quote=CLEAR, weight=1.0)
        other = mention("Acme kettle", "t1", quote="Our Acme kettle is the best we've owned, years on.", weight=0.9)
        _, shown = first_quotes([agreeing, clear, other])
        assert shown[0] == CLEAR and opener in shown, opener


def test_a_quote_naming_another_product_first_comes_after_a_clearer_one():
    other_first = mention("Acme kettle", "t1", weight=2.0,
                          quote="The Bolt kettle died twice on me, so I got the Acme kettle and it has been great.")
    clear = mention("Acme kettle", "t2", quote=CLEAR, weight=1.0)
    rest = mention("Acme kettle", "t1", quote="Our Acme kettle is the best we've owned, years on.", weight=0.9)
    bolt = mention("Bolt kettle", "t1", comment=other_first.comment_id, stance="warn",
                   quote="The Bolt kettle died twice on me")
    _, shown = first_quotes([other_first, clear, rest, bolt], bodies={other_first.comment_id: other_first.quote})
    assert shown[0] == CLEAR and other_first.quote in shown


def test_someone_elses_experience_comes_after_the_writers_own():
    hearsay = mention("Acme kettle", "t1", weight=2.0, quote="My sister swears by the Acme kettle, apparently it never fails.")
    clear = mention("Acme kettle", "t2", quote=CLEAR, weight=1.0)
    rest = mention("Acme kettle", "t1", quote="Our Acme kettle is the best we've owned, years on.", weight=0.9)
    _, shown = first_quotes([hearsay, clear, rest])
    assert shown[0] == CLEAR and hearsay.quote in shown


def test_with_no_clearer_quote_the_weak_one_still_leads_and_its_words_never_change():
    agreeing = mention("Acme kettle", "t1", weight=2.0, quote="Agreed, the Acme kettle has been great for years.")
    also = mention("Acme kettle", "t2", weight=1.0, quote="Seconded, my Acme kettle is going strong after five years.")
    third = mention("Acme kettle", "t1", weight=0.9, quote="Yep, the Acme kettle lasted me a decade and counting.")
    _, shown = first_quotes([agreeing, also, third])
    assert shown == [agreeing.quote, also.quote, third.quote]


def test_a_downside_opening_by_agreeing_comes_after_a_clearer_warning():
    praise = mentions(3, "Acme kettle", threads=("t1", "t2"))
    agreeing = mention("Acme kettle", "t1", stance="warn", weight=-0.6,
                       quote="Agreed, the Acme kettle's lid cracked on me within a year.")
    clear = mention("Acme kettle", "t2", stance="warn", weight=-0.3,
                    quote="The Acme kettle's switch failed after fourteen months of daily use.")
    answer, _ = first_quotes(praise + [agreeing, clear])
    assert [q.text for q in answer.picks[0].downsides][0] == clear.quote


def test_a_weak_opening_never_puts_a_quote_after_one_that_says_less():
    # Only a clearer quote saying as much goes first: one that never names the product ("it's held up") stays behind a
    # reply's that does, and so does one that says less about what the request asks.
    agreeing = mention("Acme kettle", "t1", weight=2.0,
                       quote="Yeah, my Acme kettle has lasted six years of daily boiling without a fault.")
    vague = mention("Acme kettle", "t2", weight=1.0, quote="I can say it's held up, it's been over four years now.")
    rest = mention("Acme kettle", "t1", weight=0.9, quote="Our Acme kettle is the best we've owned, years on.")
    _, shown = first_quotes([agreeing, vague, rest])
    assert shown[0] == agreeing.quote


def test_what_counts_as_opening_by_agreeing():
    from engine.answer import _opens_by_agreeing

    for opener in ("Agreed; it works.", "Seconded.", "Second the Acme kettle.", "Third for the Acme!", "+1 for Acme",
                   "Yeah my Acme is great", "Another vote for the Acme.", "I also use the Acme.", "This! Mine lasted."):
        assert _opens_by_agreeing(opener), opener
    for clear in ("Secondly, the Acme lasts.", "Third time I've bought the Acme.", "This kettle is great.",
                  "Yes-man products aside, the Acme is great.", "My Acme kettle lasted nine years."):
        assert not _opens_by_agreeing(clear), clear
