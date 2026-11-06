"""What an answer shows (5 Nov 2026, the makeup fix round, part 2; Claude's technical calls, reported to Noemi): which
quotes, tips and notes it shows and how its reason line names a need, from the shopper review of 4-5 Nov 2026. None of
these may change which products are picks or their order. Every comment, name and product here is made up."""

import dataclasses
import json

import pytest

from engine import config
from engine.answer import _about_a_shade, _undercuts, write_answer
from engine.needs import Need, judged_needs
from engine.pipeline import _note_products
from engine.product_notes import ProductNote, ProductNotesError, load_product_notes, notes_for
from engine.query import parse_query
from engine.rank import rank_products
from engine.tests.ranking_factories import bodies_for, mention, mentions, note


def texts(quotes) -> list[str]:
    return [q.text for q in quotes]


def kinds_shown(answer) -> list[str]:
    return [kind for item in answer.look_for for kind in item.kind.split(" or ")]


def picks_of(answer) -> list[str]:
    return [pick.product_key for pick in answer.picks]


FAIR = judged_needs(parse_query("blush for fair skin", model=None))
DARK_CIRCLES = judged_needs(parse_query("concealer for dark circles", model=None))


# --- 4. The reason line names a need as the visitor asked it ---

@pytest.mark.parametrize("request_text, label", [
    ("blush for fair skin", "fair skin"),
    ("a bed for my old dog", "old dog"),
    ("conditioner for dry damaged hair", "damaged hair"),
    ("very fair skin foundation", "fair skin"),
])
def test_a_word_named_alone_is_named_with_what_it_describes(request_text, label):
    labels = [need.label or need.name for need in judged_needs(parse_query(request_text, model=None))]
    assert label in labels, labels


def test_the_reason_says_about_fair_skin_not_about_fair():
    items = (mentions(3, "Rosa blush", category="general")
             + [mention("Rosa blush", "t1", category="general", needs=("fair",),
                        quote="The Rosa blush is soft and easy to blend.")])
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "blush", needs=FAIR,
                          request="blush for fair skin")
    assert answer.picks[0].reason.endswith("1 of them about fair skin."), answer.picks[0].reason


def test_a_word_of_two_that_make_one_need_counts_only_with_the_word_naming_it():
    # "dark" alone (a writer with dark skin) talks about no dark circles; "circles" alone does.
    items = (mentions(2, "Velo concealer", category="general")
             + [mention("Velo concealer", "t1", category="general", needs=("dark", "circles")),
                mention("Velo concealer", "t2", category="general", needs=("circles",)),
                mention("Velo concealer", "t1", category="general", needs=("dark",))])
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "concealer", needs=DARK_CIRCLES,
                          request="concealer for dark circles")
    assert answer.picks[0].reason.endswith("2 of them about dark circles."), answer.picks[0].reason


def test_a_first_word_that_says_the_need_alone_still_counts():
    # Only a first word that says something else alone (config.NEED_PHRASES_WHOLE: "dark" is a skin tone or a shade)
    # needs the second: "my lower back" is about back pain (5 Nov 2026, the second sweep: 47 non-makeup reasons
    # counted fewer voices when every phrase was read whole).
    back_pain = judged_needs(parse_query("office chair for back pain", model=None))
    items = (mentions(2, "Velo chair", category="general")
             + [mention("Velo chair", "t1", category="general", needs=("back",)),
                mention("Velo chair", "t2", category="general", needs=("back", "pain"))])
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "office chair", needs=back_pain,
                          request="office chair for back pain")
    assert answer.picks[0].reason.endswith("2 of them about back pain."), answer.picks[0].reason


# --- 1. Quotes for a need ---

def test_a_quote_whose_comment_talks_about_the_need_takes_in_the_sentence_that_does():
    fitting = mention("Rosa blush", "t1", category="general", needs=("fair",), weight=0.1,
                      quote="I own the Rosa blush and it blends in seconds.")
    items = mentions(3, "Rosa blush", category="general") + [fitting]
    bodies = bodies_for(*items)
    bodies[fitting.comment_id] = "I own the Rosa blush and it blends in seconds. It looks lovely on my fair skin."
    answer = write_answer(rank_products(items, "general"), bodies, "blush", needs=FAIR, request="blush for fair skin")
    first = answer.picks[0].quotes[0]
    assert first.comment_id == fitting.comment_id
    assert first.text == "I own the Rosa blush and it blends in seconds. It looks lovely on my fair skin."


def test_the_need_is_never_taken_from_a_sentence_about_another_product():
    # The comment's fair-skin sentence comes before, in a comment naming another blush: its "this one" may be that one.
    fitting = mention("Rosa blush", "t1", category="general", needs=("fair",), comment="cfair1", weight=0.1,
                      quote="I have also used the Rosa blush with good results.")
    other = mention("Lumen blush", "t2", category="general", comment="cfair1", quote="I wear the Lumen blush daily.")
    items = mentions(3, "Rosa blush", category="general") + [fitting, other]
    bodies = bodies_for(*items)
    bodies["cfair1"] = ("I wear the Lumen blush daily. I have fair skin and only wear this one. "
                        "I have also used the Rosa blush with good results.")
    answer = write_answer(rank_products(items, "general"), bodies, "blush", needs=FAIR, request="blush for fair skin")
    shown = {q.comment_id: q.text for pick in answer.picks for q in pick.quotes}
    assert shown.get("cfair1") in (None, "I have also used the Rosa blush with good results.")


@pytest.mark.parametrize("body, widened", [
    ("I have fair skin and most blushes look harsh. I love the Rosa blush and wear it daily.", True),
    # The sentence about the need isn't the writer's own, or a paragraph starts between (5 Nov 2026: the sweep's
    # widened quotes took in "<another chair> isn't the best for back pain" and a paragraph about something else).
    ("Fair skin is hard to shop for. Everyone says so. I love the Rosa blush and wear it daily.", False),
    ("I have fair skin.\n\nI love the Rosa blush and wear it daily.", False),
    # Its "it" is another product, or a new line starts between (5 Nov 2026, the second sweep).
    ("I tried it for a month on my fair skin and broke out. I love the Rosa blush and wear it daily.", False),
    ("I have fair skin.\nI love the Rosa blush and wear it daily.", False),
])
def test_a_sentence_before_is_taken_in_only_when_it_is_the_writers_own(body, widened):
    fitting = mention("Rosa blush", "t1", category="general", needs=("fair",), comment="cbefore", weight=0.1,
                      quote="I love the Rosa blush and wear it daily.")
    items = mentions(3, "Rosa blush", category="general") + [fitting]
    bodies = bodies_for(*items)
    bodies["cbefore"] = body
    answer = write_answer(rank_products(items, "general"), bodies, "blush", needs=FAIR, request="blush for fair skin")
    shown = {q.comment_id: q.text for pick in answer.picks for q in pick.quotes}
    if widened:
        assert shown["cbefore"] == body
    else:
        assert shown.get("cbefore") in (None, "I love the Rosa blush and wear it daily.")


def test_a_turn_after_the_quote_is_never_taken_in():
    # 5 Nov 2026: a quote under a non-slip mat took in a later "but" clause saying it began to slip after years.
    fitting = mention("Rosa blush", "t1", category="general", needs=("fair",), comment="cturn", weight=0.1,
                      quote="I wore the Rosa blush for years, it lasts all day")
    items = mentions(3, "Rosa blush", category="general") + [fitting]
    bodies = bodies_for(*items)
    bodies["cturn"] = "I wore the Rosa blush for years, it lasts all day, but on my fair skin it went patchy."
    answer = write_answer(rank_products(items, "general"), bodies, "blush", needs=FAIR, request="blush for fair skin")
    for q in answer.picks[0].quotes:
        assert "patchy" not in q.text


def test_a_new_line_after_the_quote_is_never_taken_in():
    # 5 Nov 2026, the second sweep: a conditioner's quote took in the next lines of the writer's routine.
    fitting = mention("Rosa blush", "t1", category="general", needs=("fair",), comment="cline", weight=0.1,
                      quote="I love the Rosa blush, it blends in seconds.")
    items = mentions(3, "Rosa blush", category="general") + [fitting]
    bodies = bodies_for(*items)
    bodies["cline"] = "I love the Rosa blush, it blends in seconds.\nCheeks - lovely on fair skin."
    answer = write_answer(rank_products(items, "general"), bodies, "blush", needs=FAIR, request="blush for fair skin")
    for q in answer.picks[0].quotes:
        assert "Cheeks" not in q.text


@pytest.mark.parametrize("after", [
    "For a cheaper pick I like the velvo stick, lovely on fair skin.",
    "The velvo stick is good too, lovely on fair skin.",
])
def test_a_sentence_praising_something_else_is_never_taken_in(after):
    # 5 Nov 2026, the third sweep: a vacuum's quote took in a sentence praising another vacuum, one the extraction
    # hadn't listed for that comment.
    fitting = mention("Rosa blush", "t1", category="general", needs=("fair",), comment="celse", weight=0.1,
                      quote="I love the Rosa blush, it blends in seconds.")
    items = mentions(3, "Rosa blush", category="general") + [fitting]
    bodies = bodies_for(*items)
    bodies["celse"] = "I love the Rosa blush, it blends in seconds. " + after
    answer = write_answer(rank_products(items, "general"), bodies, "blush", needs=FAIR, request="blush for fair skin")
    for q in answer.picks[0].quotes:
        assert "velvo" not in q.text


def test_a_question_after_the_quote_is_never_taken_in():
    fitting = mention("Rosa blush", "t1", category="general", needs=("fair",), weight=0.1,
                      quote="The Rosa blush is pretty but fiddly to apply.")
    items = mentions(3, "Rosa blush", category="general") + [fitting]
    bodies = bodies_for(*items)
    bodies[fitting.comment_id] = "The Rosa blush is pretty but fiddly to apply. Any tips for fair skin?"
    answer = write_answer(rank_products(items, "general"), bodies, "blush", needs=FAIR, request="blush for fair skin")
    for q in answer.picks[0].quotes:
        assert "?" not in q.text


def test_with_a_need_asked_a_shade_quote_only_makes_up_the_minimum():
    shade = mention("Rosa blush", "t1", category="general", weight=2.0,
                    quote="The Rosa blush is my go-to in the warm shade, as I have olive skin.")
    items = [shade] + mentions(3, "Rosa blush", category="general")
    bodies = bodies_for(*items)
    asked = write_answer(rank_products(items, "general"), bodies, "blush", needs=FAIR, request="blush for fair skin")
    assert shade.quote not in texts(asked.picks[0].quotes)
    plain = write_answer(rank_products(items, "general"), bodies, "blush", request="blush")
    assert shade.quote in texts(plain.picks[0].quotes)  # no need asked: as before
    # "I own it in three shades" says how much its writer likes it, not which shade to buy; and outside makeup no quote is
    # read for shades.
    assert _about_a_shade(shade, FAIR, "blush")
    assert not _about_a_shade(dataclasses.replace(shade, quote="The Rosa blush comes with me daily, I own four shades."),
                              FAIR, "blush")
    assert not _about_a_shade(shade, FAIR, "kettle")
    assert not _about_a_shade(dataclasses.replace(shade, quote="The Rosa blush shade I bought is lovely on fair skin."),
                              FAIR, "blush")


# --- 2. Quotes that undercut the pick ---

UNDERCUTTING = [
    ("I like the Rosa blush, but the Lumen blush is better suited to me.", "rival above"),
    ("The Lumen blush is far better than the Rosa blush.", "rival above"),
    ("I prefer the Lumen blush over the Rosa blush.", "rival above"),
    ("The Rosa blush was my go-to for years before I found the Lumen blush.", "switching away"),
    ("The Rosa blush is great, but I'd rather pick up a drugstore one.", "going elsewhere"),
    ("Step 2: cheeks - Rosa blush, Lumen blush and a setting mist.", "a routine"),
    ("The old Rosa blush was the best, before they reformulated it.", "an old version"),
    ("Original Rosa blush, I still keep my old pan of it.", "an old version"),
    ("I'm a Rosa blush convert for the colour, but nothing beats the Lumen blush for wear.", "rival above"),
    ("I like the Rosa blush for the price but, cost aside, I prefer the Lumen blush.", "rival above"),
    ("The Rosa blush and the Lumen blush both last, and the Lumen blush is significantly better than the Rosa blush.",
     "rival above"),
]


@pytest.mark.parametrize("quote, why", UNDERCUTTING)
def test_a_quote_undercutting_its_pick_is_never_shown_when_others_are(quote, why):
    bad = mention("Rosa blush", "t1", category="general", comment="cbad", weight=3.0, quote=quote)
    rival = mention("Lumen blush", "t1", category="general", comment="cbad", quote=quote)
    items = [bad, rival] + mentions(3, "Rosa blush", category="general")
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "blush", request="blush")
    rosa = next(pick for pick in answer.picks if pick.name == "Rosa blush")
    assert quote not in texts(rosa.quotes), why


@pytest.mark.parametrize("quote", [
    "I prefer to use the Rosa blush with a dense brush.",
    "I tried every brand before I found the Rosa blush.",
    "The Rosa blush is pricey, but I would buy it again.",
    "My old Rosa blush ran out, so I bought it again.",
    "I like the Lumen blush, but the Rosa blush is better on me.",
    # A rival ranked below it, after "than", "over" or "to", and a rival said not to be better (5 Nov 2026: the sweep's
    # first reading of these took the rival for the one favoured).
    "I've worn the Rosa blush for a year, and it's far nicer to wear than the Lumen blush was.",
    "What's even better than the Lumen blush is the Rosa blush.",
    "The Rosa blush is lovely and I much prefer it over the Lumen blush.",
    "I find the Rosa blush far superior to the Lumen blush.",
    "Rosa blush, full stop. I've tried the lot, and no, the Lumen blush is not better.",
    "The Rosa blush is soft. It blends better, not as patchy as the Lumen blush.",
    "I came to the Rosa blush from an old version of my compact, and it suits me well.",
])
def test_a_quote_backing_its_pick_is_no_undercut(quote):
    m = mention("Rosa blush", "t1", category="general", comment="cgood", quote=quote)
    assert not _undercuts(m, (("Rosa blush", "Rosa blush"), ("Lumen blush", "Lumen blush")), "blush")


def test_the_old_one_is_an_old_formula_in_makeup_only():
    # In makeup "the old X" is the formula before a change; of a kettle it is most often the writer's long-lived one.
    kettle = mention("Kestrel kettle", "t1", category="general", comment="cold",
                     quote="I've had the old Kestrel kettle with the dial for 15 years and it's still great.")
    blush = mention("Rosa blush", "t1", category="general", comment="cold2",
                    quote="I loved the old Rosa blush with the mirror, it was the best.")
    assert not _undercuts(kettle, (("Kestrel kettle", "Kestrel kettle"), ("Brio kettle", "Brio kettle")), "kettle")
    assert _undercuts(blush, (("Rosa blush", "Rosa blush"), ("Lumen blush", "Lumen blush")), "blush")


def test_an_undercutting_quote_still_makes_up_a_picks_minimum_so_the_picks_stay():
    bad = mention("Rosa blush", "t1", category="general", comment="cbad2",
                  quote="I like the Rosa blush, but the Lumen blush is better suited to me.")
    rival = mention("Lumen blush", "t1", category="general", comment="cbad2", quote=bad.quote)
    good = mention("Rosa blush", "t2", category="general", quote="The Rosa blush lasts all day on me.")
    third = mention("Rosa blush", "t1", category="general", quote="Rosa blush, every single day, for years.")
    items = [bad, rival, good, third] + mentions(3, "Velo blush", category="general")
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "blush", request="blush")
    rosa = next(pick for pick in answer.picks if pick.name == "Rosa blush")
    assert bad.quote not in texts(rosa.quotes)
    # With its third comment deleted, the undercutting quote is the only other one left: shown last, the pick stays.
    bodies = bodies_for(*items)
    bodies[third.comment_id] = "[deleted]"
    shown = write_answer(rank_products(items, "general"), bodies, "blush", request="blush")
    assert picks_of(shown) == picks_of(answer)
    assert texts(next(p for p in shown.picks if p.name == "Rosa blush").quotes) == [good.quote, bad.quote]


def test_skip_these_never_shows_a_quote_that_leans_on_another_comment():
    leaning = mention("Gritto pen eyeliner", "t1", stance="warn", category="general",
                      quote="My own went the same way, exactly the same experience here.")
    warnings = [leaning, mention("Gritto pen eyeliner", "t2", stance="warn", category="general",
                                 quote="Exactly the same experience, sadly.")]
    items = warnings + mentions(3, "Inkwell liner", category="general")
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "eyeliner", request="eyeliner")
    assert "Gritto pen eyeliner" not in [item.name for item in answer.skip]
    # A pick's downsides are never hidden: a leaning warning about a pick is still shown.
    downside = mention("Inkwell liner", "t1", stance="warn", category="general",
                       quote="It went the same way for me as for the person above, it smudged.")
    items = [downside] + mentions(4, "Inkwell liner", category="general")
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "eyeliner", request="eyeliner")
    assert texts(answer.picks[0].downsides) == [downside.quote]


# --- 3. Tips ---

def blush_picks() -> list:
    return mentions(3, "Rosa blush", category="general") + mentions(3, "Velo blush", category="general")


def test_a_tip_from_a_writer_who_hasnt_tried_it_is_never_shown():
    items = blush_picks()
    untried = note("purple blush", "t1", quote="I haven't tried it, but a purple blush would suit pale skin.")
    tried = note("purple blush", "t2", quote="A purple blush is what I wear every day on pale skin.")
    answer = write_answer(rank_products(items, "general", [untried, tried]), bodies_for(*items, untried, tried),
                          "blush", request="blush")
    [line] = [item for item in answer.look_for if item.kind == "purple blush"]
    assert line.quote.text == tried.quote
    alone = write_answer(rank_products(items, "general", [untried]), bodies_for(*items, untried), "blush",
                         request="blush")
    assert "purple blush" not in kinds_shown(alone)


def test_a_makeup_avoid_line_needs_two_writers():
    items = mentions(3, "Inkwell liquid liner", category="general") + mentions(3, "Quill liquid liner",
                                                                               category="general")
    one = [note("gel eyeliner", "t1", stance="warn", quote="Avoid gel eyeliner, it just doesn't work for me.")]
    two = one + [note("gel eyeliner", "t2", stance="warn", quote="Avoid gel eyeliner, the pot dries out fast.")]
    alone = write_answer(rank_products(items, "general", one), bodies_for(*items, *one), "eyeliner",
                         request="eyeliner")
    assert "gel eyeliner" not in kinds_shown(alone)
    both = write_answer(rank_products(items, "general", two), bodies_for(*items, *two), "eyeliner",
                        request="eyeliner")
    assert "gel eyeliner" in kinds_shown(both)
    # Outside makeup one credible warning still gives an "Avoid", as before.
    pans = mentions(3, "Velo pan", category="kitchen") + mentions(3, "Steelpot pan", category="kitchen")
    warning = [note("ceramic pans", "t1", stance="warn", quote="Avoid ceramic pans, mine lost the coating in a month.")]
    answer = write_answer(rank_products(pans, "kitchen", warning), bodies_for(*pans, *warning), "frying pan",
                          request="frying pan")
    assert "ceramic pans" in kinds_shown(answer)


def test_an_avoid_line_never_goes_against_an_also_worth_a_look_item():
    items = (mentions(3, "Inkwell liquid liner", category="general") + mentions(3, "Quill liquid liner",
                                                                                category="general")
             + mentions(3, "Feather liquid liner", category="general")
             + mentions(2, "Ashby pencil eyeliner", category="general"))
    warnings = [note("pencil eyeliner", "t1", stance="warn", quote="Avoid pencil eyeliner, it smudges by noon."),
                note("pencil eyeliner", "t2", stance="warn", quote="Avoid pencil eyeliner, it tugs the lid.")]
    answer = write_answer(rank_products(items, "general", warnings), bodies_for(*items, *warnings), "eyeliner",
                          request="eyeliner")
    assert "Ashby pencil eyeliner" in [item.name for item in answer.worth_a_look]
    assert "pencil eyeliner" not in kinds_shown(answer)


def test_a_makeup_tip_named_after_another_makeup_type_is_left_out():
    items = blush_picks()
    notes = [note("bronzer", "t1", quote="A bronzer from the drugstore is as good as any."),
             note("bronzer", "t2", quote="Get a bronzer, they are cheap and good."),
             note("bronzer worn as blush", "t1", quote="Try bronzer worn as blush on a lazy day."),
             note("bronzer worn as blush", "t2", quote="Bronzer worn as blush looks natural.")]
    answer = write_answer(rank_products(items, "general", notes), bodies_for(*items, *notes), "blush",
                          request="blush")
    assert "bronzer" not in kinds_shown(answer)
    assert "bronzer worn as blush" in kinds_shown(answer)


def test_a_makeup_tip_for_something_not_made_for_the_face_is_left_out():
    items = (mentions(3, "Mistral setting spray", category="general")
             + mentions(3, "Halo setting spray", category="general"))
    notes = [note("hairspray as a setting spray", "t1", quote="Hairspray as a setting spray works, try it."),
             note("hairspray as a setting spray", "t2", quote="Use hairspray as a setting spray in a pinch."),
             note("hydrating setting spray", "t1", quote="A hydrating setting spray is kinder to dry skin."),
             note("hydrating setting spray", "t2", quote="Go for a hydrating setting spray in winter.")]
    answer = write_answer(rank_products(items, "general", notes), bodies_for(*items, *notes), "setting spray",
                          request="setting spray")
    assert "hairspray as a setting spray" not in kinds_shown(answer)
    assert "hydrating setting spray" in kinds_shown(answer)
    powders = mentions(3, "Veil setting powder", category="general") + mentions(3, "Dune setting powder",
                                                                               category="general")
    baby = [note("baby powder as a setting powder", "t1", quote="Baby powder as a setting powder costs pennies."),
            note("baby powder as a setting powder", "t2", quote="Try baby powder as a setting powder.")]
    answer = write_answer(rank_products(powders, "general", baby), bodies_for(*powders, *baby), "setting powder",
                          request="setting powder")
    assert "baby powder as a setting powder" not in kinds_shown(answer)


def test_a_makeup_tip_backed_by_a_health_scare_is_left_out():
    items = mentions(3, "Veil setting powder", category="general") + mentions(3, "Dune setting powder",
                                                                             category="general")
    notes = [note("talc setting powder", "t1", stance="warn", quote="Avoid talc setting powder."),
             note("talc setting powder", "t2", stance="warn", quote="Avoid talc setting powder, honestly.")]
    bodies = bodies_for(*items, *notes)
    bodies[notes[0].comment_id] = "Avoid talc setting powder. It can hold asbestos."
    bodies[notes[1].comment_id] = "Avoid talc setting powder, honestly. Asbestos is a worry."
    answer = write_answer(rank_products(items, "general", notes), bodies, "setting powder", request="setting powder")
    assert "talc setting powder" not in kinds_shown(answer)


def test_a_makeup_tip_of_the_opposite_form_is_left_out_of_a_cream_request():
    items = blush_picks()
    notes = [note("pressed blush in satin", "t1", quote="A pressed blush in satin is easy for beginners."),
             note("pressed blush in satin", "t2", quote="Pick a pressed blush in satin, never glitter.")]
    cream = write_answer(rank_products(items, "general", notes), bodies_for(*items, *notes), "blush",
                         request="cream blush")
    assert "pressed blush in satin" not in kinds_shown(cream)
    plain = write_answer(rank_products(items, "general", notes), bodies_for(*items, *notes), "blush",
                         request="blush")
    assert "pressed blush in satin" in kinds_shown(plain)


def test_a_tip_whose_label_was_cut_short_is_left_out():
    items = mentions(3, "Kettle One", category="kitchen") + mentions(3, "Steelpot kettle", category="kitchen")
    notes = [note("travel size of", "t1", quote="Get the travel size of whichever you pick."),
             note("travel size of", "t2", quote="Buy the travel size of it first.")]
    answer = write_answer(rank_products(items, "kitchen", notes), bodies_for(*items, *notes), "kettle",
                          request="kettle")
    assert "travel size of" not in kinds_shown(answer)


# --- 5 and 6. Notes beside a product's quotes ---

NOTES = [ProductNote(names=("Rosa blush line",), category="general", note="Rosa reformulated its blushes in 2024",
                     sources=("https://example.com/rosa",), checked_on="2026-11-05"),
         ProductNote(names=("Spiky gel",), category="general", note="A hair styling gel some writers use on brows",
                     sources=("threads",), threads=("1abcde",), checked_on="2026-11-05")]


def test_a_products_note_is_found_by_every_word_of_one_of_its_names():
    assert notes_for("Rosa blush line", "general", NOTES) == ["Rosa reformulated its blushes in 2024"]
    assert notes_for("Rosa Liquid blush line", "general", NOTES) == ["Rosa reformulated its blushes in 2024"]
    assert notes_for("Rosa lipstick line", "general", NOTES) == []
    assert notes_for("Bolt Spiky Gel Extra", "general", NOTES) == ["A hair styling gel some writers use on brows"]
    assert notes_for("Bolt Spiky Gel Extra", "haircare", NOTES) == []


def test_a_note_is_shown_under_its_pick_and_changes_no_pick():
    items = mentions(3, "Rosa blush line", category="general") + mentions(3, "Velo blush", category="general")
    ranking = rank_products(items, "general")
    before = write_answer(ranking, bodies_for(*items), "blush", request="blush")

    @dataclasses.dataclass
    class Group:
        key: str
        name: str

    cautions: dict[str, list[str]] = {}
    _note_products([Group(p.key, p.name) for p in ranking.products], cautions, "general", NOTES)
    after = write_answer(ranking, bodies_for(*items), "blush", request="blush", cautions=cautions)
    assert picks_of(after) == picks_of(before)
    rosa = next(pick for pick in after.picks if pick.name == "Rosa blush line")
    assert rosa.cautions == ["Note: Rosa reformulated its blushes in 2024."]


def test_the_notes_list_is_checked(tmp_path):
    good = {"names": ["Rosa blush"], "category": "general", "note": "A fact", "sources": ["https://example.com/a"],
            "checked_on": "2026-11-05"}
    path = tmp_path / "notes.json"
    path.write_text(json.dumps({"product_notes": [good]}))
    assert [n.note for n in load_product_notes(path)] == ["A fact"]
    for broken in ({**good, "note": "A fact."}, {**good, "sources": ["http://example.com"]},
                   {**good, "sources": ["threads"]}, {**good, "checked_on": "5 Nov"}):
        path.write_text(json.dumps({"product_notes": [broken]}))
        with pytest.raises(ProductNotesError):
            load_product_notes(path)
    assert load_product_notes(tmp_path / "missing.json") == []


def test_the_committed_notes_list_loads_and_says_no_more_than_its_sources():
    notes = load_product_notes()
    assert notes, "data/product_notes.json"
    for entry in notes:
        assert entry.category in config.THREAD_CATEGORIES
        assert all(source == "threads" or source.startswith("https://") for source in entry.sources)
