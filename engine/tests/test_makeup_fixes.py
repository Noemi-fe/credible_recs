"""The makeup fix round, part 4 (5 Nov 2026, the fixer; Claude's technical calls, reported to Noemi): what the rules and
shopper reviews of parts 1 to 3 still found in the 15 makeup answers. Which quotes and tips an answer shows, how its
reason line counts a need, a product's name, and the two threads Noemi said to remove. None changes a scoring weight:
the ranking is module 6's, as before (an alias regroups names, as every alias does).

Every comment, quote and product here is made up, but for real product names in the naming tests (names only).
"""

import pytest

from engine import config
from engine.answer import _ends_asking, _no_longer_made, _undercuts, write_answer
from engine.needs import judged_needs
from engine.query import parse_query
from engine.rank import rank_products
from engine.tests.ranking_factories import bodies_for, mention, mentions, note
from engine.tests.test_round3_names import group_with, modules_four


def texts(quotes) -> list[str]:
    return [q.text for q in quotes]


def kinds_shown(answer) -> list[str]:
    return [kind for item in answer.look_for for kind in item.kind.split(" or ")]


def picks_of(answer) -> list[str]:
    return [pick.product_key for pick in answer.picks]


OILY = judged_needs(parse_query("foundation for oily skin", model=None))
PORES = judged_needs(parse_query("makeup primer for large pores", model=None))
ROSA_LUMEN = (("Rosa blush", "Rosa blush"), ("Lumen Petal Glow blush", "Lumen Petal Glow blush"))


# --- Tips ---

def test_a_tip_from_a_writer_who_hasnt_tried_it_is_never_shown_whatever_the_apostrophe():
    # The shopper review of part 3: a writer who opened with "I haven’t tried it" (a curly apostrophe) backed a tip.
    items = mentions(3, "Rosa blush", category="general") + mentions(3, "Velo blush", category="general")
    untried = note("purple blush", "t1", quote="I haven’t tried it, but a purple blush would suit pale skin.")
    answer = write_answer(rank_products(items, "general", [untried]), bodies_for(*items, untried), "blush",
                          request="blush")
    assert "purple blush" not in kinds_shown(answer)


def test_a_tip_whose_writer_tells_of_their_own_home_still_counts():
    # Found in part 4's own sweep: reading the words in small letters for the apostrophe also made a writer's tale of
    # their own smart washer, told through their wife, someone else's experience; only the apostrophes are straightened.
    items = mentions(3, "Velo kettle", category="general") + mentions(3, "Halo kettle", category="general")
    notes = [note("smart kettles", "t1", stance="warn",
                  quote="My partner laughs at me arguing with our smart kettle, it never does what I ask."),
             note("smart kettles", "t2", stance="warn",
                  quote="My husband gave up on our smart kettle, the app kept losing it.")]
    answer = write_answer(rank_products(items, "general", notes), bodies_for(*items, *notes), "electric kettle",
                          request="electric kettle")
    assert "smart kettles" in kinds_shown(answer)


@pytest.mark.parametrize("stance", ["warn", "recommend"])
def test_a_tip_that_is_the_type_asked_for_itself_is_left_out(stance):
    # "Avoid: face primer" in a makeup primer answer: one of the type's own names, against the very thing asked for.
    items = mentions(3, "Velo primer", category="general") + mentions(3, "Halo primer", category="general")
    notes = [note("face primer", "t1", stance=stance, quote="Once my skincare was sorted, a face primer felt spare."),
             note("face primer", "t2", stance=stance, quote="Honestly a face primer is optional for most people.")]
    answer = write_answer(rank_products(items, "general", notes), bodies_for(*items, *notes), "makeup primer",
                          request="makeup primer for large pores", needs=PORES)
    assert "face primer" not in kinds_shown(answer)


def test_a_one_word_makeup_tip_naming_another_makeup_type_is_left_out():
    # "Look for: spray" in a lip tint answer: a setting spray on the lips, its label cut to one word.
    items = mentions(3, "Velo water tint", category="general") + mentions(3, "Halo lip tint", category="general")
    notes = [note("spray", "t1", quote="You can make a tint last longer with a little spray over it."),
             note("spray", "t2", quote="A spray on top keeps it from moving."),
             note("drugstore", "t1", quote="Drugstore tints are every bit as good."),
             note("drugstore", "t2", quote="Honestly the drugstore ones last as long.")]
    answer = write_answer(rank_products(items, "general", notes), bodies_for(*items, *notes), "lip tint",
                          request="lip tint")
    assert "spray" not in kinds_shown(answer)
    assert "drugstore" in kinds_shown(answer)  # a one-word tip naming no makeup type is as before


# --- Quotes that undercut their product ---

@pytest.mark.parametrize("quote", [
    # The rival named only by its line, without its brand: "but True Match suits me better".
    "I have the Rosa blush in two colours but Petal Glow is better suited for me.",
    # Its writer's old favourite, since reformulated for the worse.
    "The Rosa blush used to be my daily blush. Then they reformulated it and reviews say it is not as good.",
    # Ranked second to another.
    "Love the Lumen Petal Glow blush. In second place is the Rosa blush.",
    # Its writer means to try others (the after-sweep of part 4).
    "I use the Rosa blush but reading this I want to try others.",
    "Rosa blush for now, but I want to try others.",
])
def test_these_quotes_undercut_their_product(quote):
    m = mention("Rosa blush", "t1", category="general", comment="cunder", quote=quote)
    assert _undercuts(m, ROSA_LUMEN, "blush")


@pytest.mark.parametrize("quote", [
    "I love the Rosa blush and the Petal Glow, both every day.",
    "They reformulated the Rosa blush last year and it's even better now.",
    "I used to buy cheap blushes, the Rosa blush is the one I keep.",
    "The Rosa blush is better than the Petal Glow on my skin.",
    # A short line word ("Go") is no name of its own.
    "Go for the Rosa blush, it is better than most.",
    # Others of its own maker: more of the same.
    "After the Rosa blush I want to try others from Rosa.",
])
def test_these_quotes_back_their_product(quote):
    m = mention("Rosa blush", "t1", category="general", comment="cback", quote=quote)
    named = ROSA_LUMEN + (("Lumen Go blush", "Lumen Go blush"),)
    assert not _undercuts(m, named, "blush")


def test_a_rival_line_is_read_whole_whatever_its_brands_accents():
    # "L'Oréal True Match" came out as "l'or", "al", "true", "match": its line never matched "True Match" in a quote.
    # Also, a line word that is another type's word (as "true" was) still belongs to the line.
    named = (("Rosa blush", "Rosa blush"), ("Lumérie True Glow blush", "Lumérie True Glow blush"))
    m = mention("Rosa blush", "t1", category="general", comment="caccent",
                quote="I have the Rosa blush in two colours but True Glow is better suited for me.")
    assert _undercuts(m, named, "blush")


def test_a_line_word_shared_with_the_quotes_own_product_names_no_rival():
    # "Soft" is in both names: it tells neither apart.
    m = mention("Rosa Soft blush", "t1", category="general", comment="cshared",
                quote="The Rosa Soft blush is lovely, softer is better on dry cheeks.")
    assert not _undercuts(m, (("Rosa Soft blush", "Rosa Soft blush"), ("Lumen Soft blush", "Lumen Soft blush")),
                          "blush")


# --- Quotes from the maker's side, and quotes about a product no longer made ---

def test_a_quote_from_someone_who_worked_for_the_maker_is_never_shown():
    employee = mention("Rosa lipstick", "t1", category="general", weight=3.0,
                       quote="I used to work for Rosa and the Rosa lipstick truly suits everyone.")
    items = [employee] + mentions(3, "Rosa lipstick", category="general")
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "lipstick", request="lipstick")
    assert employee.quote not in texts(answer.picks[0].quotes)
    # Even when it is all that would make up the minimum: the pick shows its other quotes only.
    alone = [employee] + mentions(2, "Rosa lipstick", category="general") + mentions(3, "Velo lipstick",
                                                                                    category="general")
    shown = write_answer(rank_products(alone, "general"), bodies_for(*alone), "lipstick", request="lipstick")
    assert all(employee.quote not in texts(pick.quotes) for pick in shown.picks)


@pytest.mark.parametrize("quote", [
    "I worked at a department store and the Rosa lipstick sold out every week.",
    "I work from home and the Rosa lipstick lasts through every call.",
    # Added after part 4's own sweep: the place the writer works is no maker ("the gym where I work stocks...").
    "The shop I work at sells the Rosa lipstick and it never lasts a week on the shelf.",
])
def test_working_elsewhere_is_no_tie_to_the_maker(quote):
    other = mention("Rosa lipstick", "t1", category="general", weight=3.0, quote=quote)
    items = [other] + mentions(3, "Rosa lipstick", category="general")
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "lipstick", request="lipstick")
    assert other.quote in texts(answer.picks[0].quotes)


def test_an_also_worth_a_look_item_whose_quotes_say_it_is_no_longer_made_is_left_out():
    gone = [mention("Orla primer", "t1", category="general", quote="Sadly the Orla primer was discontinued."),
            mention("Orla primer", "t2", category="general",
                    quote="I loved the Orla primer, but it seems to be out of production now.")]
    items = (mentions(3, "Velo primer", category="general") + mentions(3, "Halo primer", category="general")
             + mentions(3, "Kite primer", category="general") + gone
             + mentions(2, "Nimbus primer", category="general"))
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "makeup primer",
                          request="makeup primer")
    worth = [item.name for item in answer.worth_a_look]
    assert "Orla primer" not in worth
    assert "Nimbus primer" in worth


def test_an_also_worth_a_look_item_two_of_whose_voices_say_it_is_no_longer_made_is_left_out_whatever_else_is_said():
    # Two writers said the Orla primer was discontinued; a third only that she loved it. The item is no lead to follow.
    gone = [mention("Orla primer", "t1", category="general", quote="Sadly the Orla primer was discontinued."),
            mention("Orla primer", "t2", category="general",
                    quote="I loved the Orla primer, but it seems to be out of production now."),
            mention("Orla primer", "t3", category="general", quote="I was using the Orla primer too, I loved it.")]
    items = (mentions(5, "Velo primer", category="general") + mentions(5, "Halo primer", category="general")
             + mentions(5, "Kite primer", category="general") + gone
             + mentions(2, "Nimbus primer", category="general"))
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "makeup primer",
                          request="makeup primer")
    assert sorted(picks_of(answer)) == ["halo-primer", "kite-primer", "velo-primer"]
    worth = [item.name for item in answer.worth_a_look]
    assert "Orla primer" not in worth
    assert "Nimbus primer" in worth


def test_one_voice_saying_no_longer_made_leaves_the_item_with_its_other_quotes():
    one = [mention("Orla primer", "t1", category="general", quote="Sadly the Orla primer was discontinued."),
           mention("Orla primer", "t2", category="general", quote="The Orla primer keeps my makeup on all day."),
           mention("Orla primer", "t3", category="general", quote="I was using the Orla primer too, I loved it.")]
    items = (mentions(5, "Velo primer", category="general") + mentions(5, "Halo primer", category="general")
             + mentions(5, "Kite primer", category="general") + one)
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "makeup primer",
                          request="makeup primer")
    assert sorted(picks_of(answer)) == ["halo-primer", "kite-primer", "velo-primer"]
    assert "Orla primer" in [item.name for item in answer.worth_a_look]


def test_a_no_longer_made_quote_naming_another_product_is_about_that_one():
    # "X was discontinued, so I switched to Y": for Y it is a reason, not a warning.
    switched = mention("Velo primer", "t1", category="general", comment="cswitch", weight=3.0,
                       quote="The Orla primer was discontinued, so I switched to the Velo primer and love it.")
    orla = mention("Orla primer", "t1", category="general", comment="cswitch", stance="neutral",
                   quote=switched.quote)
    items = [switched, orla] + mentions(3, "Velo primer", category="general")
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "makeup primer",
                          request="makeup primer")
    assert switched.quote in texts(answer.picks[0].quotes)


def test_a_product_switched_to_after_another_was_discontinued_is_not_the_one_gone():
    # Found in part 4's own sweep: "after it was discontinued I switched to X" was read as X being gone.
    m = mention("Velo primer", "t1", category="general", comment="cafter",
                quote="After my old one was discontinued I switched to the Velo primer and it is lovely.")
    assert not _no_longer_made(m, (("Velo primer", "Velo primer"),))
    gone = mention("Velo primer", "t1", category="general", comment="cgone",
                   quote="I loved the Velo primer, but it seems to be out of production now.")
    assert _no_longer_made(gone, (("Velo primer", "Velo primer"),))


# --- A need given to another product ---

def test_a_need_sentence_that_gives_the_need_to_another_product_is_neither_shown_nor_counted():
    # The comment's pores are for "a separate primer": the pick's quote never takes that sentence in, and its reason
    # never counts the voice as one about large pores.
    giving = mention("Velo primer", "t1", category="general", comment="cgive", needs=("large", "pores"), weight=0.1,
                     quote="a light primer that isn't greasy like the Velo primer")
    items = [giving] + mentions(3, "Velo primer", category="general") + mentions(3, "Halo primer", category="general")
    bodies = bodies_for(*items)
    bodies["cgive"] = ("I have large pores myself. I use a light primer that isn't greasy like the Velo primer "
                       "then for my pores I add a separate primer that blurs them.")
    answer = write_answer(rank_products(items, "general"), bodies, "makeup primer", needs=PORES,
                          request="makeup primer for large pores")
    velo = next(pick for pick in answer.picks if pick.name == "Velo primer")
    assert all("separate primer" not in q.text for q in velo.quotes)
    assert "about large pores" not in velo.reason, velo.reason


def test_a_need_sentence_about_the_product_itself_still_counts():
    fitting = mention("Velo primer", "t1", category="general", comment="cown", needs=("large", "pores"), weight=0.1,
                      quote="I use the Velo primer every day")
    items = [fitting] + mentions(3, "Velo primer", category="general") + mentions(3, "Halo primer", category="general")
    bodies = bodies_for(*items)
    bodies["cown"] = "I use the Velo primer every day and it blurs my large pores."
    answer = write_answer(rank_products(items, "general"), bodies, "makeup primer", needs=PORES,
                          request="makeup primer for large pores")
    velo = next(pick for pick in answer.picks if pick.name == "Velo primer")
    assert velo.reason.endswith("1 of them about large pores."), velo.reason


@pytest.mark.parametrize("sentence", [
    # Found in part 4's own sweep, in sunscreen, shampoo and garlic press answers: a comparison with other products, or
    # a second bottle of this one, gives no need away.
    "I use the Velo primer every day, it looks less greasy on my large pores than the other brands do.",
    "I use the Velo primer every day, on my second bottle now and my large pores look smaller.",
    "I use the Velo primer every day, my large pores look better than with another brand I tried.",
])
def test_comparing_with_other_products_gives_no_need_away(sentence):
    fitting = mention("Velo primer", "t1", category="general", comment="ccompare", needs=("large", "pores"),
                      weight=0.1, quote="I use the Velo primer every day")
    items = [fitting] + mentions(3, "Velo primer", category="general") + mentions(3, "Halo primer", category="general")
    bodies = bodies_for(*items)
    bodies["ccompare"] = sentence
    answer = write_answer(rank_products(items, "general"), bodies, "makeup primer", needs=PORES,
                          request="makeup primer for large pores")
    velo = next(pick for pick in answer.picks if pick.name == "Velo primer")
    assert velo.reason.endswith("1 of them about large pores."), velo.reason


# --- Which quotes lead ---

def test_a_hedged_question_comes_after_a_clearer_quote():
    hedge = mention("Velo foundation", "t1", category="general", weight=3.0,
                    quote="The Velo foundation and my old one both worked well, so maybe both are my top ones?")
    clear = [mention("Velo foundation", "t2", category="general", weight=1.0,
                     quote="I've been loving the Velo foundation, the coverage looks like skin."),
             mention("Velo foundation", "t1", category="general", weight=1.0,
                     quote="The Velo foundation wears all day and never looks heavy.")]
    items = [hedge, *clear] + mentions(3, "Halo foundation", category="general")
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "foundation", request="foundation")
    velo = next(pick for pick in answer.picks if pick.name == "Velo foundation")
    assert texts(velo.quotes)[0] != hedge.quote


def test_a_question_in_brackets_at_the_end_is_no_asking():
    # Found in part 4's own sweep: a statement ending on a price asked in brackets is a statement with an aside.
    assert not _ends_asking("The Rosa boots are comfy and fairly cheap (about $40?)")
    assert _ends_asking("so maybe both are my top ones?")


def test_with_a_need_asked_a_pick_shows_a_quote_about_it_when_one_stands():
    named = [mention("Velo foundation", f"t{i % 2 + 1}", category="general", weight=2.0,
                     quote=f"The Velo foundation is lovely, number {i} of my favourites for coverage.")
             for i in range(4)]
    oily = mention("Velo foundation", "t2", category="general", weight=0.2, needs=("oily",),
                   quote="Even by the evening I still looked fresh and not oily at all.")
    items = named + [oily] + mentions(3, "Halo foundation", category="general")
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "foundation", needs=OILY,
                          request="foundation for oily skin")
    velo = next(pick for pick in answer.picks if pick.name == "Velo foundation")
    assert oily.quote in texts(velo.quotes)
    assert texts(velo.quotes)[0] == named[0].quote  # the first quote is as before
    # With no need asked, as before.
    plain = write_answer(rank_products(items, "general"), bodies_for(*items), "foundation", request="foundation")
    assert oily.quote not in texts(next(p for p in plain.picks if p.name == "Velo foundation").quotes)


def _velo_with(candidate, request, product_type="foundation", extra=()):
    named = [mention("Velo foundation", f"t{i % 2 + 1}", category="general", weight=2.0,
                     quote=f"The Velo foundation is lovely, number {i} of my favourites for coverage.")
             for i in range(4)]
    items = named + [candidate, *extra] + mentions(3, "Halo foundation", category="general")
    needs = judged_needs(parse_query(request, model=None))
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), product_type, needs=needs,
                          request=request)
    return texts(next(pick for pick in answer.picks if pick.name == "Velo foundation").quotes)


def test_the_need_quote_is_never_one_about_another_product_of_its_comment():
    # Found in part 4's own sweep (a coffee grinder pick): a writer owning three products, using another the most.
    other = mention("Kite foundation", "t2", category="general", comment="cthree", weight=0.0, stance="neutral",
                    quote="I own the Velo foundation and the Kite foundation, and mostly wear the Kite on oily days.")
    candidate = mention("Velo foundation", "t2", category="general", comment="cthree", weight=0.2, needs=("oily",),
                        quote=other.quote)
    assert candidate.quote not in _velo_with(candidate, "foundation for oily skin", extra=(other,))


def test_the_need_quote_is_never_one_whose_need_is_only_an_if():
    # Found in part 4's own sweep (a rice cooker pick): a need named only in an "if" clause about who should buy bigger.
    candidate = mention("Velo foundation", "t2", category="general", weight=0.2, needs=("oily",),
                        quote="Good value for me. If oily skin is your worry you would probably want a matte one.")
    assert candidate.quote not in _velo_with(candidate, "foundation for oily skin")


def test_the_need_quote_needs_its_writer_to_talk_about_the_need():
    # Found in part 4's own sweep: a quote whose words fit the need but whose writer, as the extraction read them,
    # never talked about it is not that quote.
    candidate = mention("Velo foundation", "t2", category="general", weight=0.2, needs=(),
                        quote="Not oily at all, I reach for it most mornings.")
    assert candidate.quote not in _velo_with(candidate, "foundation for oily skin")


@pytest.mark.parametrize("request_, needs, quote", [
    # Found in part 4's second sweep: "a few years back" is no back pain, and "dry days" no dry skin.
    ("office chair for back pain", ("back",), "Second-hand from a few years back, still holding up fine."),
    ("toner for dry skin", ("dry",), "I wear it alone on humid days and layer it on cold, dry days."),
])
def test_the_need_quote_is_never_one_whose_need_word_means_something_else(request_, needs, quote):
    named = [mention("Velo chair", f"t{i % 2 + 1}", category="general", weight=2.0,
                     quote=f"The Velo chair has lasted me {i + 2} years of daily use.") for i in range(4)]
    candidate = mention("Velo chair", "t2", category="general", weight=0.2, needs=needs, quote=quote)
    items = named + [candidate] + mentions(3, "Halo chair", category="general")
    parsed = judged_needs(parse_query(request_, model=None))
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "office chair", needs=parsed,
                          request=request_)
    assert candidate.quote not in texts(next(p for p in answer.picks if p.name == "Velo chair").quotes)


def test_no_need_quote_for_a_word_of_the_products_own_name():
    # Found in part 4's own sweep: "mechanical" of "mechanical keyboard" is no need to show a quote for.
    named = [mention("Velo keyboard", f"t{i % 2 + 1}", category="general", weight=2.0,
                     quote=f"The Velo keyboard has lasted me {i + 2} years of daily use.") for i in range(4)]
    candidate = mention("Velo keyboard", "t2", category="general", weight=0.2, needs=("mechanical",),
                        quote="The Velo keyboard is the plainest mechanical keyboard there is.")
    items = named + [candidate] + mentions(3, "Halo keyboard", category="general")
    needs = judged_needs(parse_query("mechanical keyboard", model=None))
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "keyboard", needs=needs,
                          request="mechanical keyboard")
    assert candidate.quote not in texts(next(p for p in answer.picks if p.name == "Velo keyboard").quotes)


# --- Names ---

def test_got2b_glued_brows_and_edges_is_one_product_apart_from_a_plain_got2b_hair_gel():
    groups = modules_four([("Got2B Glue Spiking Gel", 6), ("Got2b Glued Brows 38 Edges hair gel", 1),
                           ("got2b Glued Brow & Edge Gel", 1), ("Got2b hair gel", 1), ("Got2b hair gel 170g", 1),
                           ("Maybelline Super Lock Brow Glue", 5)], "brow gel")
    glued = group_with(groups, "Got2b Glued Brows 38 Edges hair gel")
    assert group_with(groups, "got2b Glued Brow & Edge Gel") is glued
    assert group_with(groups, "Got2b hair gel") is not glued
    assert group_with(groups, "Got2b hair gel 170g") is not glued


@pytest.mark.parametrize("written, shown", [
    ("Got2b Glued Brows 38 Edges hair gel", "got2b Glued Brows & Edges gel"),
    ("NARS radiant creamy concealer", "NARS Radiant Creamy concealer"),
    ("Anastasia Beverly Hills brow wiz", "Anastasia Beverly Hills Brow Wiz"),
    ("elf brow lift", "e.l.f. Brow Lift"),
    ("Dior forever concealer", "Dior Forever concealer"),
    ("NYX marshmallow primer", "NYX Marshmellow primer"),
])
def test_makeup_names_as_their_makers_write_them(written, shown):
    from engine.group_products import maker_spelling
    assert maker_spelling(written, "general") == shown


# --- Noemi's "Remove those 2 threads" (5 Nov 2026) ---

def test_the_removed_threads_are_never_read_again(tmp_path):
    from engine import bulk_import, library
    assert {"1co3r5i", "1jlzpoa"} <= set(config.REMOVED_THREADS)
    (tmp_path / "threads").mkdir()
    assert set(config.REMOVED_THREADS) <= library.not_to_read(tmp_path)
    assert set(config.REMOVED_THREADS) <= bulk_import.imported_before(tmp_path)


def test_second_place_undercuts_only_the_product_it_ranks_second():
    m = mention("Rosa blush", "t1", category="general", comment="cfirst",
                quote="The Rosa blush is my number one. In second place is the Lumen Petal Glow blush.")
    assert not _undercuts(m, ROSA_LUMEN, "blush")
