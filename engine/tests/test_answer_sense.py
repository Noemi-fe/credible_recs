"""Answers that make sense (Noemi's note, 12 Oct 2026): every quote says what it is about, and every "What to look for"
line is advice about a kind of the product asked for.

From testing the demo: "retinol for a beginner with sensitive skin" showed "Look for: retinol" (the product asked for,
with a writer's shrug for its quote), "Look for: retinol eye cream" with a quote whose "it" was never named, and a pick
quote that was a reply ("Yes!") whose "it" only the comment above explained. Every quote passed the word-for-word check;
what failed was sense. engine/sense_eval.py measures it; these tests hold the rules that fix it.

All text is made up (engine/tests/ranking_factories.py).
"""

from engine import answer as wording
from engine.answer import says_the_opposite, unverified_claims, write_answer
from engine.config import QUOTE_MAX_WORDS
from engine.rank import rank_products
from engine.tests.ranking_factories import bodies_for, mention, mentions, note


def answer_for(items, bodies, product_type=None, **kwargs):
    return write_answer(rank_products(items, kwargs.pop("category", "kitchen"), kwargs.pop("notes", ()), {}), bodies,
                        product_type, **kwargs)


# --- Quotes that stand on their own ---

def test_a_quote_leaning_on_the_sentence_before_it_is_shown_with_that_sentence():
    # The writer names the kettle, then says what it did in the next sentence: "It" alone would leave the reader asking
    # what. The two sentences are one stretch of the comment, so the quote is still its own words, word for word.
    leaning = mention("Acme kettle", "t1", quote="It has boiled water twice a day for nine years.")
    others = mentions(2, "Acme kettle", threads=("t1", "t2"), voice="medium")
    bodies = bodies_for(*others) | {leaning.comment_id: "Went with the Acme kettle after my last one died. "
                                                        "It has boiled water twice a day for nine years. No regrets."}
    answer = answer_for([leaning] + others, bodies, "electric kettle")
    shown = [q.text for q in answer.picks[0].quotes]
    assert ("Went with the Acme kettle after my last one died. It has boiled water twice a day for nine years."
            in shown)
    assert unverified_claims(answer, bodies) == []


def test_the_sentences_before_are_taken_in_only_up_to_the_word_limit():
    # The comment names the kettle too far before the quote: the stretch would be over QUOTE_MAX_WORDS words, so the
    # quote isn't widened. It leans on what came before, so the quotes that name the kettle are shown instead.
    filler = " ".join(["Some long story about my kitchen."] * (QUOTE_MAX_WORDS // 5))
    leaning = mention("Acme kettle", "t1", quote="It has boiled water twice a day for nine years.")
    others = mentions(2, "Acme kettle", threads=("t1", "t2"), voice="medium")
    bodies = bodies_for(*others) | {leaning.comment_id: f"The Acme kettle. {filler} {leaning.quote}"}
    answer = answer_for([leaning] + others, bodies, "electric kettle")
    assert [q.text for q in answer.picks[0].quotes] == [m.quote for m in others]


def test_a_quote_is_never_widened_across_a_link_a_list_or_a_quoted_block():
    # Reddit shows a link, a list or a quoted block differently from how it is typed, so the live check couldn't find
    # a stretch that takes one in, and a quoted block is someone else's words.
    leaning = mention("Acme kettle", "t1", quote="It has boiled water twice a day for nine years.")
    others = mentions(2, "Acme kettle", threads=("t1", "t2"), voice="medium")
    for before in ("I bought the [Acme kettle](https://example.com/acme) last year. ",
                   "- the Acme kettle\n- a scale\n\n",
                   "&gt; Is the Acme kettle any good?\n\n"):
        bodies = bodies_for(*others) | {leaning.comment_id: before + leaning.quote}
        answer = answer_for([leaning] + others, bodies, "electric kettle")
        assert all("Acme kettle" not in q.text or q.comment_id != leaning.comment_id for q in answer.picks[0].quotes)
        assert unverified_claims(answer, bodies) == []


def test_a_reply_that_never_names_its_product_gives_way_to_quotes_that_do():
    # The most credible quote is a reply: "Yes!" and an "it" that only the comment above explains. The pick shows the
    # quotes that name the kettle instead; the reply is shown only to make up a pick's two quotes.
    reply = mention("Acme kettle", "t1", quote="Yes! Big change since I began using it.", weight=2.0)
    naming = mentions(3, "Acme kettle", threads=("t1", "t2"), voice="medium")
    bodies = bodies_for(*naming) | {reply.comment_id: reply.quote}
    answer = answer_for([reply] + naming, bodies, "electric kettle")
    assert reply.quote not in [q.text for q in answer.picks[0].quotes]
    assert len(answer.picks[0].quotes) == 3

    few = [reply] + naming[:1] + [mention("Acme kettle", "t2", voice="medium", quote="Still going strong.")]
    answer = answer_for(few, bodies | bodies_for(*few[1:]), "electric kettle")
    assert [q.text for q in answer.picks[0].quotes][0] == naming[0].quote
    assert len(answer.picks[0].quotes) == 2  # the two that don't name it make up the minimum, the reply last


def test_a_quote_leaning_on_someone_or_something_not_shown_gives_way_even_when_it_names_its_product():
    for quote in ("He told me to get the Acme kettle and it broke anyway, so mixed feelings.",
                  "Acme kettle? Same experience here, sadly.",
                  "I liked the Acme kettle for that reason, it pours well."):
        leaning = mention("Acme kettle", "t1", quote=quote, weight=2.0)
        naming = mentions(3, "Acme kettle", threads=("t1", "t2"), voice="medium")
        answer = answer_for([leaning] + naming, bodies_for(leaning, *naming), "electric kettle")
        assert quote not in [q.text for q in answer.picks[0].quotes], quote


def test_a_bare_mention_is_never_more_than_a_pick_needs():
    # "I own an Acme." names it but says nothing about it: it never takes the third place.
    bare = mention("Acme kettle", "t1", quote="I own an Acme.")
    naming = mentions(2, "Acme kettle", threads=("t1", "t2"), voice="medium")
    answer = answer_for(naming + [bare], bodies_for(bare, *naming), "electric kettle")
    assert [q.text for q in answer.picks[0].quotes] == [m.quote for m in naming]


def test_a_downside_or_skip_quote_that_leans_on_the_thread_comes_after_one_that_stands():
    praise = mentions(3, "Acme kettle", threads=("t1", "t2"))
    leaning = mention("Acme kettle", "t1", stance="warn", quote="Same thing happened to mine.", weight=-2.0)
    standing = mention("Acme kettle", "t2", stance="warn", voice="medium", quote="The Acme kettle's lid cracked.")
    answer = answer_for(praise + [leaning, standing], bodies_for(*praise, leaning, standing), "electric kettle")
    assert [q.text for q in answer.picks[0].downsides][0] == standing.quote
    # With no standing warning, the leaning one is still shown: a pick's downsides are never hidden.
    answer = answer_for(praise + [leaning], bodies_for(*praise, leaning), "electric kettle")
    assert [q.text for q in answer.picks[0].downsides] == [leaning.quote]

    skipped = [mention("Bolt kettle", "t1", stance="warn", quote="Yeah I agree, mine went in the bin.", weight=-2.0),
               mention("Bolt kettle", "t2", stance="warn", quote="The Bolt kettle leaked within a month.")]
    answer = answer_for(praise + skipped, bodies_for(*praise, *skipped), "electric kettle")
    assert [q.text for q in answer.skip[0].quotes] == [skipped[1].quote]


# --- What to look for: advice about a kind of the product asked for ---

def look_for(notes, product_type, request="", asks=(), category="skincare", picks=()):
    items = list(picks) or mentions(3, "Acme thing", category=category)
    answer = write_answer(rank_products(items, category, notes, {}), bodies_for(*items, *notes), product_type,
                          request=request, asks=asks)
    return [(item.advice, item.kind, item.quote.text) for item in answer.look_for]


def test_the_product_asked_for_is_no_advice_about_what_to_look_for():
    notes = [note("retinol", "t1", quote="Retinol is worth it once your skin is used to it.", weight=0.9),
             note("Retinoids", "t2", quote="Retinoids changed my skin more than any other step.", weight=0.8),
             note("retinal", "t1", quote="Retinal worked better than retinol for my sensitive skin.", weight=0.5)]
    assert [kind for _, kind, _ in look_for(notes, "retinoid", "retinol for a beginner with sensitive skin")] == [
        "retinal"]
    kettles = [note("Kettle", "t1", quote="Any kettle with a steel body is great.", weight=0.9),
               note("Steel body", "t2", quote="A steel body is what I'd get, it lasts.", weight=0.5)]
    assert [kind for _, kind, _ in look_for(kettles, "electric kettle", "electric kettle that lasts", category="kitchen")
            ] == ["Steel body"]


def test_a_note_must_name_its_kind_or_the_kind_takes_another_note_or_is_left_out():
    vague = note("Glass kettle", "t1", quote="It changed my mornings.", weight=0.9)
    naming = note("Glass kettle", "t2", quote="A glass kettle lets you see the scale, love it.", weight=0.5)
    assert look_for([vague, naming], "electric kettle", category="kitchen") == [
        (wording.LOOK_FOR, "Glass kettle", naming.quote)]
    assert look_for([vague], "electric kettle", category="kitchen") == []


def test_a_note_is_shown_with_the_sentence_before_it_that_names_its_kind():
    leaning = note("Blade grinder", "t1", stance="warn", quote="And it was useless, honestly.")
    items = mentions(3, "Acme grinder")
    bodies = bodies_for(*items) | {leaning.comment_id: "Before my burr grinder I owned a blade one, the cheap blade grinder. "
                                                       "And it was useless, honestly. Never again."}
    answer = write_answer(rank_products(items, "kitchen", [leaning], {}), bodies, "coffee grinder")
    assert [(item.advice, item.quote.text) for item in answer.look_for] == [
        (wording.AVOID, "Before my burr grinder I owned a blade one, the cheap blade grinder. And it was useless, honestly.")]
    assert unverified_claims(answer, bodies) == []


def test_a_hedge_a_wish_or_a_question_is_no_advice():
    for quote in ("I don't think you need a glass kettle, but they look nice.",
                  "I want a glass kettle for my new flat one day.",
                  "Is a glass kettle worth it for hard water?"):
        assert look_for([note("Glass kettle", "t1", quote=quote)], "electric kettle", category="kitchen") == [], quote


def test_skincare_and_haircare_advice_named_after_another_type_of_product_is_left_out():
    # Found on 12 Oct 2026: "Avoid: eye creams" in a moisturiser answer, "Look for: double cleansing" in a sunscreen one,
    # "Avoid: dry shampoo" in a shampoo one. The kind's own name says what types of product it is about (module 1's names
    # for them, or a word sharing their stem): advice named after other types only is no advice for this one, whatever
    # its notes say. "retinol eye cream" names a retinoid too, so a retinol answer may show it.
    eye = note("eye creams", "t1", stance="warn", quote="Eye creams are a gimmick, I never saw a difference with one.")
    assert look_for([eye], "moisturiser") == []
    double = note("double cleansing", "t1", quote="Double cleansing on sunscreen days is great for my skin.")
    assert look_for([double], "sunscreen") == []
    assert [kind for _, kind, _ in look_for([double], "cleanser")] == ["double cleansing"]
    retinol_eye = note("retinol eye cream", "t1", quote="A retinol eye cream made a big difference to my lines.")
    assert [kind for _, kind, _ in look_for([retinol_eye], "retinoid")] == ["retinol eye cream"]
    assert look_for([retinol_eye], "moisturiser") == []
    dry = note("dry shampoo", "t1", stance="warn", quote="Dry shampoo is a pain to wash out, skip it.")
    assert look_for([dry], "shampoo", category="haircare") == []


def test_a_note_saying_the_opposite_of_the_request_gives_way_to_one_that_doesnt():
    opposite = note("mineral sunscreen", "t1", quote="Mineral sunscreen is great for oily skin, but there's a slight "
                                                     "white cast.", weight=0.9)
    fine = note("mineral sunscreen", "t2", quote="Tinted mineral sunscreen works great for me.", weight=0.5)
    assert look_for([opposite, fine], "sunscreen", asks=("no white cast",)) == [
        (wording.LOOK_FOR, "mineral sunscreen", fine.quote)]
    assert look_for([opposite], "sunscreen", asks=("no white cast",)) == []
    assert says_the_opposite("The catch: there's some white cast.", ["no white cast"])
    assert not says_the_opposite("There's no white cast on me.", ["no white cast"])


def test_advice_naming_the_product_asked_for_comes_before_advice_that_never_does():
    # A strongly backed kind whose notes never name the product asked for ("humidifier" in a retinol answer) comes after
    # the kinds that do, whatever its support.
    notes = [note("humidifier", "t1", quote="A humidifier at night is great.", weight=0.9),
             note("humidifier", "t2", quote="My humidifier helped a lot.", weight=0.9),
             note("retinal", "t1", quote="Retinal is gentler than most retinol for me, love it.", weight=0.5),
             note("encapsulated retinol", "t2", quote="Encapsulated retinol is a good gentle start.", weight=0.4),
             note("bakuchiol", "t1", quote="Bakuchiol worked great before my retinol.", weight=0.3)]
    assert [kind for _, kind, _ in look_for(notes, "retinoid", "retinol for a beginner")] == [
        "retinal", "encapsulated retinol", "bakuchiol"]


def test_for_a_type_the_open_model_named_another_kind_of_it_is_no_advice():
    # config.OTHER_KIND_WORDS: an immersion blender isn't a blender (11 Oct 2026, for products); the same for advice.
    notes = [note("immersion blender", "t1", quote="An immersion blender is worth it for soups."),
             note("stick blender", "t2", quote="A stick blender is great for small jobs."),
             note("glass jar", "t1", quote="A glass jar blender is great, no stains.", weight=0.3)]
    assert [kind for _, kind, _ in look_for(notes, "blender", "blender for smoothies", category="kitchen")] == [
        "glass jar"]


def test_an_avoid_line_never_quotes_a_warning_about_one_of_the_picks():
    picks = mentions(3, "GreenPan", category="kitchen")
    about_a_pick = note("Teflon", "t1", stance="warn", quote="Greenpans and similar nonstick pans wear out fast.",
                        weight=-0.9)
    other = note("Teflon", "t2", stance="warn", quote="Nonstick coatings like Teflon never last, avoid them.",
                 weight=-0.5)
    assert look_for([about_a_pick, other], "frying pan", category="kitchen", picks=picks) == [
        (wording.AVOID, "Teflon", other.quote)]
    # A one-letter slip in the pick's name is still the pick ("Greenspan").
    slip = note("Teflon", "t1", stance="warn", quote="Greenspan and other nonstick pans wear out fast.", weight=-0.9)
    assert look_for([slip, other], "frying pan", category="kitchen", picks=picks) == [
        (wording.AVOID, "Teflon", other.quote)]


# --- Refinements found judging the first run (12 Oct 2026) ---

def test_a_quote_reasoning_from_the_original_posters_budget_leans_on_the_thread():
    from engine.answer import _stands_alone

    assert not _stands_alone("At twice OP's budget, the Acme is probably best.", names_it=True)
    assert not _stands_alone("Having cooked with both, the Acme felt no different.", names_it=True)
    assert _stands_alone("Both the Acme and the Bolt are great, years on.", names_it=True)
    assert _stands_alone("I chop onions with my Acme every day and it's great.", names_it=True)  # not "OP"


def test_a_kind_named_as_something_instead_of_the_product_asked_for_is_no_advice_for_it():
    # "Look for: moisturizer instead of eye cream" in an eye cream answer, "Look for: grinder over machine" in an
    # espresso machine one: advice to buy something else.
    notes = [note("facial cream instead of eye cream", "t1", quote="A facial cream instead of eye cream works fine."),
             note("caffeine eye cream", "t2", quote="A caffeine eye cream helped my dark circles a lot.", weight=0.5)]
    assert [kind for _, kind, _ in look_for(notes, "eye cream", "eye cream for dark circles")] == ["caffeine eye cream"]
    grinder = [note("grinder over machine", "t1", quote="Spend on a grinder over the machine, it matters more."),
               note("used espresso machines", "t2", quote="Buy used espresso machines, they last.", weight=0.5)]
    assert [kind for _, kind, _ in look_for(grinder, "espresso machine", "espresso machine for a beginner",
                                            category="kitchen")] == ["used espresso machines"]


def test_a_mild_word_of_a_kinds_name_needn_t_be_repeated_to_name_it():
    notes = [note("gentle retinol eye cream", "t1", quote="Pick a low strength retinol eye cream, it's great.")]
    assert [kind for _, kind, _ in look_for(notes, "eye cream")] == ["gentle retinol eye cream"]


def test_a_writers_short_name_that_is_a_common_word_doesnt_name_the_product():
    # "TO" (The Ordinary, as a writer wrote it) isn't named by "had to bin it".
    from engine.answer import _names_product

    assert not _names_product("I had to bin it at last.", "The Ordinary sunscreen", "skincare",
                              written_as="TO sunscreen")
    # Nor is a name's leading "The" its brand: "the" in a quote doesn't name The Ordinary.
    assert not _names_product("It gave me the worst cast.", "The Ordinary sunscreen", "skincare")
    assert _names_product("The ordinary one was fine.", "The Ordinary sunscreen", "skincare")
    assert _names_product("TO sunscreen gave me a white cast.", "The Ordinary sunscreen", "skincare",
                          written_as="TO sunscreen")


def test_a_quote_saying_the_pick_isnt_really_the_type_asked_for_comes_last():
    # b04: a moisturiser pick's quote said the cream was fine but not really a moisturiser: it doesn't speak for it as one.
    not_one = mention("Acme cream", "t1", category="skincare", weight=2.0,
                      quote="The Acme cream is fine, but honestly it's not a real moisturizer.")
    others = mentions(3, "Acme cream", category="skincare", voice="medium")
    answer = write_answer(rank_products([not_one] + others, "skincare"), bodies_for(not_one, *others), "moisturiser")
    assert not_one.quote not in [q.text for q in answer.picks[0].quotes]


def test_advice_to_buy_the_cheapest_and_replace_it_says_the_opposite_of_lasting():
    assert says_the_opposite("Get the cheapest and replace it once it breaks.", ["lasting"])
    assert not says_the_opposite("Replace the jar when it wears and the motor goes on for years.", ["lasting"])


def test_a_note_that_never_names_its_kind_is_widened_whatever_else_it_says():
    # b09: a note listing burrs and a dial to look for names no hand grinder (the kind) and leans on no "it", but the
    # sentence before it does name one: the two are shown together.
    advice = note("Hand grinder", "t1", quote="Look for metal burrs and a stepped dial.")
    items = mentions(3, "Acme grinder")
    bodies = bodies_for(*items) | {advice.comment_id: "Some cheap hand grinders are fine these days. "
                                                      "Look for metal burrs and a stepped dial."}
    answer = write_answer(rank_products(items, "kitchen", [advice], {}), bodies, "coffee grinder")
    assert [item.quote.text for item in answer.look_for] == [
        "Some cheap hand grinders are fine these days. Look for metal burrs and a stepped dial."]


def test_advice_about_a_look_alike_of_the_product_asked_for_is_no_advice_for_it():
    # 14 Oct 2026 (kitchen appliances, Noemi's decision 3): a blender became one of module 1's own types, and an
    # immersion or stick blender stays no advice for it, as when it was the open model's type: module 1 sets those
    # aside as look-alikes of a blender. So is a look-alike of any type: a bread or paring knife (13 Oct 2026, other
    # kinds of knife) in a chef's knife answer, a sheet pan in a frying pan one. A kind that only shares a word with one
    # stays ("Look for: Santoku", "Look for: cast iron").
    notes = [note("immersion blender", "t1", quote="An immersion blender is worth it for soups."),
             note("stick blender", "t2", quote="A stick blender is great for small jobs."),
             note("glass jar", "t1", quote="A glass jar blender is great, no stains.", weight=0.3)]
    assert [kind for _, kind, _ in look_for(notes, "blender", "blender for smoothies", category="kitchen")] == [
        "glass jar"]
    knives = [note("bread knife", "t1", quote="Get a serrated bread knife alongside it, it's great."),
              note("paring knife", "t2", quote="A cheap paring knife is great for small jobs."),
              note("Santoku", "t1", quote="A Santoku is a great first chef's knife.", weight=0.4)]
    assert [kind for _, kind, _ in look_for(knives, "chef knife", "first chef's knife", category="kitchen")] == [
        "Santoku"]
    pans = [note("sheet pan", "t1", quote="A sheet pan is great for roasting veg."),
            note("cast iron", "t2", quote="Cast iron is great and lasts forever.", weight=0.4)]
    assert [kind for _, kind, _ in look_for(pans, "frying pan", "a frying pan", category="kitchen")] == ["cast iron"]
