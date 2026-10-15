"""Quotes coherent with the stance they back (Noemi's decision 4 of 15 Oct 2026): a quote shown must be the most
significant and coherent part of its comment for the stance it backs. A recommendation is quoted where the comment
recommends (praise, how long it lasted, how it held up), a warning where it warns. Her example: a TV pick's first quote
told of the 14 years the writer's last TV of that brand lasted before its picture went out, while the same comment
says their current one is holding up well.

Module 7 orders a product's quotes so (engine.answer._naming_first): among them, those whose own words carry the stance
they back come first, and a quote whose words read against it (a recommendation's quote telling of a failure or a
complaint, a warning's quote praising) comes after every other, before only those saying the opposite of the request
and those leaning on the thread. It orders quotes; it never changes their words.

Every comment, product and quote here is made up (engine/tests/ranking_factories.py).
"""

import pytest

from engine.answer import carries_its_stance, reads_against_its_stance, write_answer
from engine.rank import rank_products
from engine.tests.ranking_factories import bodies_for, mention


def texts(quotes) -> list[str]:
    return [q.text for q in quotes]


# --- Noemi's example, made up: a recommendation quoted for a failure after a long life ---

def test_a_recommendation_quoted_for_its_failure_comes_after_the_quotes_that_recommend():
    failure = mention("Acme TV", "t1", weight=0.9, category="general", quote="Our last Acme TV lasted us 14 years and then the backlight gave out.")
    holding_up = mention("Acme TV", "t2", weight=0.5, category="general", quote="My Acme TV is holding up well at 3 years old.")
    praise = mention("Acme TV", "t1", weight=0.4, category="general", quote="The Acme TV has a great picture for the price.")
    items = [failure, holding_up, praise]
    answer = write_answer(rank_products(items, "general"), bodies_for(*items))
    assert texts(answer.picks[0].quotes) == [holding_up.quote, praise.quote, failure.quote]  # still shown: there's room


def test_a_failure_after_a_long_life_is_still_shown_when_it_is_all_there_is():
    # Never hidden: the order changes, not what can be shown.
    failures = [mention("Acme kettle", "t1", weight=0.9, quote="My Acme kettle died after 14 years."),
                mention("Acme kettle", "t2", weight=0.8, quote="My Acme stopped working after 11 years of daily use.")]
    praise = mention("Acme kettle", "t1", weight=0.3, quote="Love my Acme kettle, it boils fast.")
    items = [*failures, praise]
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items))
    assert texts(answer.picks[0].quotes) == [praise.quote] + [m.quote for m in failures]


def test_a_failure_with_praise_in_its_own_words_keeps_its_place():
    # "Mine died after 12 years and I bought the same one again": the writer's own words still recommend it.
    rebought = mention("Acme kettle", "t1", weight=0.9, quote="My Acme kettle died after 12 years and I bought the same one again.")
    plain = mention("Acme kettle", "t2", weight=0.5, quote="The Acme kettle sits on my counter.")
    other = mention("Acme kettle", "t1", weight=0.4, quote="I have had the Acme kettle for 3 years, love it.")
    items = [rebought, plain, other]
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items))
    assert texts(answer.picks[0].quotes)[0] == rebought.quote


# --- Warnings: quoted where they warn ---

def test_a_downside_quoted_for_praise_comes_after_the_ones_that_warn():
    picks = [mention("Acme kettle", f"t{i % 2 + 1}", weight=0.9 - i / 10, quote=f"The Acme kettle is great, take {i}.")
             for i in range(3)]
    praising = mention("Acme kettle", "t1", stance="warn", weight=-0.9, quote="I loved my Acme kettle at first.")
    warning = mention("Acme kettle", "t2", stance="warn", weight=-0.5, quote="The Acme kettle's lid cracked within a month.")
    items = [*picks, praising, warning]
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items))
    assert texts(answer.picks[0].downsides) == [warning.quote, praising.quote]


def test_a_warning_that_says_what_went_wrong_comes_before_one_that_only_names_it():
    # Saying what went wrong is the warning's own view, as praise is a recommendation's.
    names_it = mention("Zeta pan", "t1", stance="warn", weight=-0.9, quote="I own the Zeta pan and the older model too.")
    went_wrong = mention("Zeta pan", "t2", stance="warn", weight=-0.5, quote="The Zeta pan warped on the first use.")
    items = [names_it, went_wrong]
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items))
    assert [s.name for s in answer.skip] == ["Zeta pan"]
    assert texts(answer.skip[0].quotes) == [went_wrong.quote, names_it.quote]


# --- The rules that were there stay ---

def test_saying_the_opposite_of_the_request_still_comes_last():
    # For "a kettle that lasts": a failure within a year says the opposite of the request (the 10 Oct 2026 rule), a
    # failure after 12 years reads against the recommendation; both go after the quote that recommends, the opposite last.
    opposite = mention("Acme kettle", "t1", weight=0.9, quote="My Acme stopped working after about a year.")
    against = mention("Acme kettle", "t2", weight=0.8, quote="My Acme kettle died after 12 years.")
    coherent = mention("Acme kettle", "t1", weight=0.3, quote="My Acme kettle is still going strong after 9 years.")
    items = [opposite, against, coherent]
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items), asks=("lasting",))
    assert texts(answer.picks[0].quotes) == [coherent.quote, against.quote, opposite.quote]


def test_naming_the_product_still_comes_before_carrying_the_stance():
    named = mention("Acme kettle", "t1", weight=0.5, quote="My Acme has lasted 6 years.")
    unnamed = mention("Acme kettle", "t2", weight=0.9, quote="Love it, works great every single morning.")
    other = mention("Acme kettle", "t1", weight=0.4, quote="The acme kettle still boils fast.")
    items = [named, unnamed, other]
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items))
    assert texts(answer.picks[0].quotes) == [named.quote, other.quote, unnamed.quote]


def test_an_also_worth_a_look_item_is_quoted_where_it_recommends():
    pick = [mention("Tojiro DP Gyuto", f"t{i % 2 + 1}", weight=1.0) for i in range(3)]
    failure = mention("Misono UX10", "t1", weight=0.9, quote="My Misono UX10 lasted 15 years before the handle cracked.")
    praise = mention("Misono UX10", "t2", weight=0.5, quote="The Misono UX10 is the best knife I have owned.")
    items = [*pick, failure, praise]
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items), "chef knife")
    assert [w.name for w in answer.worth_a_look] == ["Misono UX10"]
    assert texts(answer.worth_a_look[0].quotes) == [praise.quote, failure.quote]


def test_the_words_of_a_quote_never_change():
    failure = mention("Acme TV", "t1", weight=0.9, category="general", quote="Our last Acme TV lasted us 14 years and then the backlight gave out.")
    others = [mention("Acme TV", "t2", weight=0.5, category="general"),
              mention("Acme TV", "t1", weight=0.4, category="general")]
    items = [failure, *others]
    bodies = bodies_for(*items)
    answer = write_answer(rank_products(items, "general"), bodies)
    assert sorted(texts(answer.picks[0].quotes)) == sorted(m.quote for m in items)


# --- The most informative for the request first (the coordinator's trial comparison, 15 Oct 2026) ---
# Testers see a pick's first quotes: among its coherent quotes, those that say why (the request's needs, any need, how
# long, a view with something behind it) come before a bare like ("I love the Acme cleanser").

def test_quotes_that_say_why_come_before_a_bare_like():
    bare = mention("Acme cleanser", "t1", weight=0.55, category="skincare", quote="I love the Acme cleanser.")
    which_need = mention("Acme cleanser", "t2", weight=0.5, category="skincare",
                         quote="The Acme cleanser has been amazing for my dry, sensitive skin.")
    loyal = mention("Acme cleanser", "t1", weight=0.5, category="skincare",
                    quote="I've tried a few others but always go back to the Acme cleanser.")
    items = [bare, which_need, loyal]
    answer = write_answer(rank_products(items, "skincare"), bodies_for(*items))
    assert texts(answer.picks[0].quotes) == [which_need.quote, loyal.quote, bare.quote]


def test_a_quote_about_the_requests_needs_still_comes_first():
    from engine.config import NEEDS
    from engine.needs import Need

    acne = (Need("acne-prone", NEEDS["acne-prone"]),)
    bare = mention("Acme foam", "t1", weight=0.55, category="skincare", quote="Oddly, I really like the Acme foam.")
    what_it_did = mention("Acme foam", "t2", weight=0.3, category="skincare",
                          quote="The Acme foam leaves my skin soft and has repaired my damaged barrier.")
    about_acne = mention("Acme foam", "t1", weight=0.5, category="skincare",
                         quote="The Acme foam works for me with little to no breakouts.")
    items = [bare, what_it_did, about_acne]
    answer = write_answer(rank_products(items, "skincare"), bodies_for(*items), needs=acne)
    assert texts(answer.picks[0].quotes) == [about_acne.quote, what_it_did.quote, bare.quote]


@pytest.mark.parametrize("product, quote, bare", [
    ("Acme cleanser", "I love the Acme cleanser.", True),
    ("Acme Cream-to-Foam Cleanser", "Oddly, I really like the Acme Cream to Foam cleanser.", True),
    ("Acme cleanser", "The best I've tried is from Acme!!!", True),
    ("Acme cleanser", "I love it for my dry skin.", False),  # which need
    ("Acme kettle", "I love my Acme, it pours so nicely and feels well built.", False),  # a view with substance
    ("Acme kettle", "I love my Acme, had it for 12 years.", False),  # how long
    ("Acme knife", "Acme brand for most things.", False),  # no like at all: not a bare like, if not much either
])
def test_what_a_bare_like_is(product, quote, bare):
    from engine.answer import _bare_like

    assert _bare_like(mention(product, category="skincare", quote=quote)) is bare


def test_a_quote_about_another_product_of_its_comment_comes_last_and_only_makes_up_the_minimum():
    # b08 (the coordinator's trial, 15 Oct 2026): the Lodge line's first quote praised the writer's Lodge carbon steel
    # skillet, which had replaced their cast iron: module 3 had the same comment recommend the carbon steel skillet,
    # typed as a frying pan. Made up here.
    other = mention("Acme cast iron", "t1", weight=1.1, others_of_another_type=("Acme carbon steel skillet",),
                    quote="I'm happy with my Acme cast iron, but my Acme carbon steel skillet has replaced it for nearly "
                          "everything.")
    good = [mention("Acme cast iron", "t2", weight=1.0, quote="I've had my Acme for almost 20 years."),
            mention("Acme cast iron", "t1", weight=0.5, quote="My Acme is 10 years old and still gets daily use.")]
    items = [other, *good]
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items))
    assert texts(answer.picks[0].quotes) == [m.quote for m in good]  # not shown: the pick has better ones
    gone = mention("Acme cast iron", "t2", weight=0.4, quote="My Acme still cooks the best steak.")
    items = [other, good[0], gone]
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(other, good[0]))  # its comment is gone
    assert texts(answer.picks[0].quotes) == [good[0].quote, other.quote]  # it makes up the minimum of two, last


def test_naming_another_type_of_product_in_passing_isnt_enough():
    # The other product's own words must be there: "steel" alone in a cast iron quote isn't the carbon steel skillet.
    passing = mention("Acme cast iron", "t1", weight=1.1, others_of_another_type=("Matfer Bourgeat carbon steel pan",),
                      quote="My Acme cast iron has outlasted every stainless steel pan I owned.")
    others = [mention("Acme cast iron", "t2", weight=1.0), mention("Acme cast iron", "t1", weight=0.5)]
    items = [passing, *others]
    answer = write_answer(rank_products(items, "kitchen"), bodies_for(*items))
    assert texts(answer.picks[0].quotes)[0] == passing.quote


def test_the_pipeline_records_a_comments_other_products_of_another_type():
    from engine.extract import ExtractedMention
    from engine.pipeline import _others_of_another_type

    def extracted(product: str, product_type: str | None, stance: str = "recommend", comment_id: str = "c1"):
        return ExtractedMention(comment_id=comment_id, product=product, category="kitchen", stance=stance,
                                quote="Some quote.", product_type=product_type)

    cast_iron = extracted("Acme cast iron", "cast iron skillet")
    kept = [cast_iron, extracted("Acme carbon steel skillet", "frying pan"), extracted("Zeta skillet", "skillet"),
            extracted("Old nonstick pan", "frying pan", stance="warn"), extracted("Beta wok", "wok", comment_id="c2"),
            extracted("Gamma pan", None)]
    # Another type, the same stance, the same comment; a skillet is a cast iron skillet's own kind; a type not given
    # tells nothing.
    assert _others_of_another_type(cast_iron, kept) == ("Acme carbon steel skillet",)


# --- What reads against a quote's stance (all made up) ---

@pytest.mark.parametrize("stance, quote, carries, against", [
    # A recommendation: praise, how it held up, an endorsement carry it; a failure or a complaint reads against it.
    ("recommend", "Our last Acme TV lasted us 14 years and then the backlight gave out.", False, True),
    ("recommend", "My Acme TV is still going strong at 3 years old.", True, False),
    ("recommend", "My Panasonic died after 14 years.", False, True),
    ("recommend", "I had my Panasonic for 14 years.", False, False),  # how long alone: neither (the view words see it)
    ("recommend", "Had it for 15 years before the thermostat failed.", False, True),
    ("recommend", "I returned it once for a dent, the new one is fine.", False, True),
    ("recommend", "The worst part is cleaning it.", False, True),
    ("recommend", "When mine broke, they replaced it free.", False, True),
    ("recommend", "Love it, though the handle cracked after 5 years.", True, False),  # praise in its own words
    ("recommend", "It still works after the lid broke.", True, False),
    ("recommend", "After 9 years it finally died, so I bought the same one.", True, False),
    ("recommend", "The handle broke after 10 years but they sent a new one.", False, False),  # it turns after
    # What didn't go wrong is how it held up.
    ("recommend", "It never broke, not once in ten years.", True, False),
    ("recommend", "Twelve years in and no peeling at all.", True, False),
    ("recommend", "They're not cheap but they don't break.", True, False),
    ("recommend", "It didn't chip, crack or warp in 20 years.", True, False),
    ("recommend", "Not a single one has died in 8 years.", True, False),
    ("recommend", "Never had a single issue.", True, False),
    ("recommend", "Zero regrets, use it daily.", True, False),
    ("recommend", "You won't be disappointed.", True, False),
    ("recommend", "I don't think you'd be disappointed.", True, False),
    ("recommend", "I will never buy another wallet again.", True, False),
    ("recommend", "Cannot recommend it enough, honestly.", True, False),
    ("recommend", "I'll never get rid of it.", True, False),
    ("recommend", "Avoid the Cuisinart, get the Zojirushi.", True, False),
    ("recommend", "Why not just get the Acme drill?", True, False),
    ("recommend", "Nothing better than an Acme bar.", True, False),
    ("recommend", "Cannot recommend my Acme pack highly enough.", True, False),
    ("recommend", "We have barely ever had leaks with these.", True, False),
    ("recommend", "We switched to the Acme and never looked back.", True, False),
    ("recommend", "It worked fine for me.", True, False),
    ("recommend", "They got so comfortable once they broke in.", True, False),  # breaking in, at the end too
    # Words that look like a failure and aren't one.
    ("recommend", "It broke in nicely after a few weeks.", False, False),  # breaking in a pan is using it
    ("recommend", "Best balm for cracked lips I've found.", True, False),
    ("recommend", "Freshly cracked pepper every morning, love it.", True, False),
    ("recommend", "My grandma died and left me her Griswold.", False, False),
    ("recommend", "I was broke in college and it still works.", True, False),
    ("recommend", "It won't break the bank.", True, False),
    ("recommend", "I went out and bought a second one.", True, False),
    ("recommend", "I returned to it after trying others.", False, False),
    ("recommend", "If it ever breaks, they replace it for free.", False, False),  # it hasn't
    ("recommend", "It breaks everything down so well.", False, False),
    ("recommend", "Mine is dead quiet and boils fast.", False, False),
    ("recommend", "It went out of stock everywhere.", False, False),
    ("recommend", "It cleared my breakouts in a week.", False, False),
    ("recommend", "It calmed my irritated skin.", False, False),
    ("recommend", "My only regret is not buying it sooner.", False, False),
    # A warning: what went wrong, advice against, praise taken back carry it; praise alone reads against it.
    ("warn", "I loved my Acme kettle at first.", False, True),
    ("warn", "Works great!", False, True),
    ("warn", "Looks great on the counter.", False, True),
    ("warn", "The Acme kettle's lid cracked within a month.", True, False),
    ("warn", "Avoid the Acme kettle, it leaks.", True, False),
    ("warn", "It was great for six months, then the coating peeled.", True, False),
    ("warn", "No issues at first, then it died.", True, False),
    ("warn", "Great pan, terrible customer service.", True, False),
    ("warn", "Not great, honestly.", True, False),
    ("warn", "Not Ring, it's junk.", True, False),
    ("warn", "Le Creuset isn't worth it to me.", True, False),
    ("warn", "I wouldn't recommend it to anyone.", True, False),
    ("warn", "I'd never buy it again.", True, False),
    ("warn", "It broke me out in days.", True, False),
    ("warn", "I hate how flimsy it is.", True, False),
    ("warn", "I wish my blender held up this well.", True, False),
    ("warn", "Initially it was fine but eventually, I dont know, it just stopped working?", True, False),
    ("warn", "It was great the first day, but ever since it rides up.", False, False),  # it turns after the praise
    # A neutral mention has no stance to carry.
    ("neutral", "Is the Acme kettle any good?", False, False),
])
def test_what_carries_a_quotes_stance_and_what_reads_against_it(stance, quote, carries, against):
    assert carries_its_stance(quote, stance) is carries
    assert reads_against_its_stance(quote, stance) is against


def test_a_product_named_with_praise_words_isnt_praise():
    # "Perfect Gel", "Great Barrier Relief": the product's own name (two or more of its words together) says nothing.
    quote = "The Perfect Gel did nothing for my face."
    assert reads_against_its_stance(quote, "warn") is False
    assert carries_its_stance(quote, "warn", ("Hada Labo Perfect Gel",)) is True
    assert reads_against_its_stance("Switched to the Perfect Gel and it's kinda meh.", "warn", ("Perfect Gel",)) is False
    assert reads_against_its_stance("It's perfect.", "warn", ("Perfect Gel",)) is True  # one word alone is the writer's
