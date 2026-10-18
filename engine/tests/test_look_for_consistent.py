""""What to look for" never says the opposite of the request or of the picks (17 Oct 2026, the converge round, item 3).

From the breadth-first review of 16 Oct 2026 (docs/bfs-2026-10-16/answer.md, J) and the 17 Oct sweep: an electric
kettle answer said "Avoid: variable temperature kettle" under three variable-temperature kettles, and so did the
answer to "electric kettle with temperature control"; three lines against niacinamide in a niacinamide serum answer;
"Avoid: mesh networks" for mesh wifi; "Avoid: inverter microwave" above a Panasonic inverter microwave; "Look for" and
"Avoid" the same kind in one answer. Credible voices may disagree, but the section is a blueprint for the request, so a
line saying the opposite of what was asked for, of a pick, or of another kind's stronger advice is left out. Avoiding
what the request itself refuses ("Avoid: Teflon" for a pan without Teflon) agrees with it, and stays.

18 Oct 2026, from reading the whole sweep: counting other kinds' advice as the same kind's took out good lines ("Avoid:
pull-through sharpener" for a knife sharpener's credible praise, "Avoid: ice maker" beside "Look for: fridge without an
ice maker", "Avoid: non-stick pans" in a cast iron answer), and the lines that came in for them were weaker (a no-name
copy from a marketplace, in a kettle answer). Now another kind counts only when it is the same thing, or one of it
("heavy wool coat" for "wool coats in rain"), never a wider one nor its opposite, and only as much credible advice the
other way outweighs a line; the kettle answers are told by their picks, a line pick by its products' names; and a line
left out leaves its place empty.

All text is made up (engine/tests/ranking_factories.py).
"""

from engine import answer as wording
from engine.answer import write_answer
from engine.config import NEEDS
from engine.needs import Need
from engine.rank import rank_products
from engine.tests.ranking_factories import bodies_for, mention, mentions, note


def shown(notes, product_type, request="", needs=(), asks=(), category="kitchen", picks=None):
    items = picks if picks is not None else mentions(3, "Acme thing", category=category)
    answer = write_answer(rank_products(items, category, notes, {}), bodies_for(*items, *notes), product_type,
                          request=request, needs=tuple(needs), asks=tuple(asks))
    return [(item.advice, item.kind) for item in answer.look_for]


TEMPERATURE = Need("temperature control", NEEDS["temperature control"])


def test_an_avoid_line_about_what_the_request_asks_for_is_left_out():
    variable = note("variable temperature kettle", "t1", stance="warn", weight=-0.6,
                    quote="Every variable temperature kettle I owned broke inside a year.")
    glass = note("glass kettle", "t2", quote="A glass kettle is great, you see the scale building up.", weight=0.5)
    assert shown([variable, glass], "electric kettle", "electric kettle with temperature control",
                 needs=[TEMPERATURE]) == [(wording.LOOK_FOR, "glass kettle")]
    # Asked for nothing of the kind, the same warning stays: it says nothing against the request.
    assert (wording.AVOID, "variable temperature kettle") in shown([variable, glass], "electric kettle",
                                                                   "a quiet electric kettle")


def test_an_avoid_line_about_the_ingredient_asked_for_is_left_out():
    notes = [note("niacinamide irritation", "t1", stance="warn", weight=-0.6,
                  quote="Niacinamide irritation is common, my face went red with it."),
             note("products with niacinamide", "t2", stance="warn", weight=-0.5,
                  quote="I avoid products with niacinamide now, they all broke me out."),
             note("low-percentage niacinamide", "t1", weight=0.4,
                  quote="A low-percentage niacinamide is great, the gentler ones did more for me.")]
    assert shown(notes, "serum", "niacinamide serum for large pores", category="skincare") == [
        (wording.LOOK_FOR, "low-percentage niacinamide")]


def test_an_avoid_line_about_the_feature_the_request_names_for_its_product_is_left_out():
    # "mesh wifi": the request names a mesh system (one of the type's own names); another kind of it stays.
    notes = [note("mesh networks", "t1", stance="warn", weight=-0.6,
                  quote="Mesh networks are overkill, no reason for one in a flat."),
             note("wifi extenders", "t2", stance="warn", weight=-0.5,
                  quote="Wifi extenders are the worst fix, they halve your speed.")]
    assert shown(notes, "wifi router", "mesh wifi for a three storey house", category="general") == [
        (wording.AVOID, "wifi extenders")]


def test_avoiding_what_the_request_itself_refuses_agrees_with_it():
    teflon = note("Teflon", "t1", stance="warn", weight=-0.8,
                  quote="Teflon coatings flake within two years, I'd never buy one again.")
    non_stick = Need("non-stick", ("non-stick", "nonstick", "non stick"))
    assert shown([teflon], "frying pan", "non stick pan without teflon that lasts", needs=[non_stick],
                 asks=("PFAS-free", "non-stick")) == [(wording.AVOID, "Teflon")]


def test_a_look_for_line_about_what_the_request_refuses_is_left_out():
    teflon = note("Teflon pans", "t1", weight=0.8, quote="Teflon pans are great for eggs, cheap and easy.")
    ceramic = note("ceramic pans", "t2", weight=0.4, quote="Ceramic pans are great for eggs if you go gently.")
    assert shown([teflon, ceramic], "frying pan", "non stick pan without teflon", asks=("PFAS-free",)) == [
        (wording.LOOK_FOR, "ceramic pans")]


def test_an_avoid_line_about_a_kind_one_of_the_picks_is_is_left_out():
    picks = mentions(3, "Panasonic inverter microwave") + mentions(3, "Acme microwave")
    notes = [note("inverter microwave", "t1", stance="warn", weight=-0.7,
                  quote="An inverter microwave died on me in two years, never again."),
             note("microwave drawer", "t2", weight=0.4, quote="A microwave drawer is great in a small kitchen.")]
    assert shown(notes, "microwave", "microwave with a grill", picks=picks) == [
        (wording.LOOK_FOR, "microwave drawer")]
    # With no pick of that kind, the warning stays.
    others = mentions(3, "Acme microwave") + mentions(3, "Bolt microwave")
    assert (wording.AVOID, "inverter microwave") in shown(notes, "microwave", "microwave with a grill", picks=others)


def test_an_avoid_line_another_kinds_credible_advice_recommends_is_left_out():
    # One writer warns against variable-temperature kettles, while credible voices recommend the same thing under
    # another name, more strongly: the section doesn't say both.
    # Changed on 18 Oct 2026 (deliberately, the converge round): the recommendation was "temperature-controlled kettle"
    # at 0.6, a kind that never says "variable", which no longer counts as the same one (the sweep's false matches); the
    # kettle answers are told by their picks now. And the warning's place stays empty (no fourth line comes in).
    notes = [note("variable temperature kettle", "t1", stance="warn", weight=-1.0,
                  quote="Every variable temperature kettle I owned broke inside a year."),
             note("variable temp kettles", "t2", weight=1.2, quote="Variable temp kettles are great for green tea."),
             note("steel kettle", "t1", weight=0.9, quote="A steel kettle is great, no plastic taste at all."),
             note("glass kettle", "t2", weight=0.8, quote="A glass kettle is great, you see the scale."),
             note("gooseneck kettle", "t1", weight=0.7, quote="A gooseneck kettle is great for pour over.")]
    assert shown(notes, "electric kettle", "electric kettle that lasts 10+ years") == [
        (wording.LOOK_FOR, "variable temp kettles"), (wording.LOOK_FOR, "steel kettle")]
    # Without the recommendation, the warning is the strongest advice, and it is shown first.
    assert shown(notes[:1] + notes[2:], "electric kettle", "electric kettle that lasts 10+ years")[0] == (
        wording.AVOID, "variable temperature kettle")


def test_a_look_for_line_stronger_credible_warnings_argue_against_is_left_out_and_the_stronger_stays():
    notes = [note("mineral sunscreen", "t1", weight=0.4, quote="A mineral sunscreen is great for my sensitive skin."),
             note("mineral SPFs", "t2", stance="warn", weight=-0.9,
                  quote="Mineral SPFs leave a grey film on my skin, I'd skip them."),
             note("stick sunscreens", "t1", weight=0.3, quote="Stick sunscreens are great for top ups.")]
    assert shown(notes, "sunscreen", "best sunscreen", category="skincare") == [
        (wording.AVOID, "mineral SPFs"), (wording.LOOK_FOR, "stick sunscreens")]


def test_a_recommended_kind_the_request_rules_out_argues_against_nothing():
    # "Avoid: tretinoin" for a beginner: writers who recommend tretinoin don't count against it, since a beginner's
    # answer never says "Look for: tretinoin" (its facts rule it out: the pipeline's unsuited kinds).
    items = mentions(3, "Acme serum", category="skincare")
    notes = [note("tretinoin", "t1", stance="warn", weight=-0.8, quote="Tretinoin is far too strong to start with."),
             note("tretinoin 0.025%", "t2", weight=0.9, key="tret-recommended",
                  quote="Tretinoin 0.025% is great once you are used to it.")]
    answer = write_answer(rank_products(items, "skincare", notes, {}), bodies_for(*items, *notes), "retinoid",
                          request="gentle retinol for beginners", unsuited_kinds={"tret-recommended"})
    assert [(item.advice, item.kind) for item in answer.look_for] == [(wording.AVOID, "tretinoin")]
    # Not ruled out, the recommendation outweighs the warning: neither is said (the recommendation is the product asked
    # for, so it gives no "Look for" of its own).
    answer = write_answer(rank_products(items, "skincare", notes, {}), bodies_for(*items, *notes), "retinoid",
                          request="gentle retinol for beginners")
    assert (wording.AVOID, "tretinoin") not in [(item.advice, item.kind) for item in answer.look_for]


def test_kinds_are_the_same_only_when_what_tells_one_apart_is_the_others():
    # Changed on 18 Oct 2026 (deliberately): a kind's advice counts for another's only when it is about that one
    # (_about_the_same): "temperature-controlled kettle" never says "variable", so it no longer counts for "variable
    # temperature kettle"; "adjustable temperature" says the same as "variable temperature".
    from engine.answer import _about_the_same

    def same(a, b, product_type, category="kitchen"):
        return _about_the_same(a, b, category, product_type)

    assert same("mineral SPFs", "mineral sunscreen", "sunscreen", "skincare")  # "spf" is a sunscreen's clue word
    assert not same("variable temperature kettle", "temperature-controlled kettle", "electric kettle")
    assert same("variable temperature kettle", "adjustable temp kettle", "electric kettle")
    assert same("gel moisturiser", "gel cream for oily skin", "moisturiser", "skincare")
    # A plural made singular its own way ("knives", "patches") is still the type's word, so it tells nothing apart.
    assert not same("Japanese style knives", "classic German knives", "paring knife")
    assert not same("large patches", "hydrocolloid patches", "spot treatment", "skincare")
    assert not same("corded hammer drill", "dedicated hammer drill", "drill")


def test_in_a_knife_answer_warnings_about_other_knives_stay_beside_advice_about_others():
    notes = [note("Japanese style knives", "t1", weight=0.3, quote="Japanese style knives are great for fine cuts."),
             note("Damascus knives", "t2", stance="warn", weight=-0.5,
                  quote="Damascus knives are mostly looks, skip the pattern and buy good steel."),
             note("classic German knives", "t1", stance="warn", weight=-0.3,
                  quote="Classic German knives are too soft for this, they dull fast.")]
    assert sorted(shown(notes, "paring knife", "best paring knife under £30")) == sorted([
        (wording.AVOID, "Damascus knives"), (wording.LOOK_FOR, "Japanese style knives"),
        (wording.AVOID, "classic German knives")])


def test_avoiding_a_needs_opposite_or_whom_it_is_for_isnt_against_the_request():
    # A need's words hold its opposite too ("harsh" for gentle, "broke" for lasting): avoiding that agrees with it. And
    # a need saying whom the product is for (a beginner, oily skin) is no word of the product asked for.
    from engine.needs import Need

    gentle, lasting = Need("gentle", NEEDS["gentle"]), Need("lasting", NEEDS["lasting"])
    harsh = note("harsh scrubs", "t1", stance="warn", weight=-0.6, quote="Harsh scrubs tear your skin, skip them.")
    assert shown([harsh], "exfoliant", "gentle exfoliant", needs=[gentle], category="skincare") == [
        (wording.AVOID, "harsh scrubs")]
    broke = note("plastic kettles that broke", "t1", stance="warn", weight=-0.6,
                 quote="Plastic kettles that broke within a year, every one of them, so skip those.")
    assert shown([broke], "electric kettle", "kettle that lasts", needs=[lasting]) == [
        (wording.AVOID, "plastic kettles that broke")]
    beginner = Need("beginner", NEEDS["beginner"])
    sets = note("beginner knife sets", "t1", stance="warn", weight=-0.6,
                quote="Beginner knife sets are a waste, buy one good knife instead.")
    assert shown([sets], "chef knife", "first chef's knife for a beginner", needs=[beginner]) == [
        (wording.AVOID, "beginner knife sets")]


def test_avoiding_a_kind_the_requests_facts_rule_out_stays_whatever_others_recommend():
    # "Avoid: tretinoin" for a beginner, whose answer the facts rules keep tretinoin out of (the pipeline's unsuited
    # kinds: the kind's own facts entry clashes hard with the request), stays beside writers recommending a tretinoin
    # cream: it agrees with the request.
    items = mentions(3, "Acme serum", category="skincare")
    notes = [note("tretinoin", "t1", stance="warn", weight=-0.8, key="tretinoin",
                  quote="Tretinoin is far too strong to start with."),
             note("tretinoin cream", "t2", weight=0.9, quote="A tretinoin cream is great once you are used to it.")]
    answer = write_answer(rank_products(items, "skincare", notes, {}), bodies_for(*items, *notes), "retinoid",
                          request="gentle retinol for beginners", unsuited_kinds={"tretinoin"})
    assert (wording.AVOID, "tretinoin") in [(item.advice, item.kind) for item in answer.look_for]


def test_the_same_kinds_recommendations_count_together_against_a_warning():
    # One warning against variable temperature kettles (-1.6), and credible recommendations of the same thing under
    # three other names, each weaker, together as strong: the warning is left out. "temp" is "temperature" written
    # short, "adjustable" the same as "variable".
    # Changed on 18 Oct 2026 (deliberately): the names were "temperature-controlled kettle" (no longer the same kind:
    # it never says "variable") and "variable temp"; and since then only as much support the other way outweighs a line
    # (it was half as much).
    notes = [note("variable temperature kettle", "t1", stance="warn", weight=-1.6,
                  quote="Every variable temperature kettle I owned broke inside a year."),
             note("adjustable temperature kettle", "t2", weight=0.6,
                  quote="An adjustable temperature kettle is great for green tea."),
             note("variable temp", "t1", weight=0.5, quote="Variable temp is great for tea, get a kettle with it."),
             note("variable temperature kettles", "t2", weight=0.5,
                  quote="Variable temperature kettles are great, mine is on year six."),
             note("steel kettle", "t2", weight=0.4, quote="A steel kettle is great, no plastic taste at all.")]
    assert (wording.AVOID, "variable temperature kettle") not in shown(notes, "electric kettle",
                                                                       "electric kettle that lasts 10+ years")
    # Two of them, together weaker than it, don't outweigh it.
    assert (wording.AVOID, "variable temperature kettle") in shown([notes[0], notes[1], notes[2], notes[4]],
                                                                   "electric kettle",
                                                                   "electric kettle that lasts 10+ years")


def test_a_kind_named_after_a_prescription_only_active_gives_a_beginner_no_look_for_even_misspelt():
    # b03 ("retinol for a beginner with sensitive skin", a blind-test question) showed "Look for: adalpalene": a
    # writer's slip for adapalene, prescription-only in the UK (Differin), which the facts rules keep out of the answer.
    # A kind named after an active ingredient (a one-letter slip in a long word forgiven) gives no "Look for" when every
    # product of the facts list holding it clashes hard with the request; a kind of another active stays.
    from datetime import date

    from engine.pipeline import _unsuited_kinds
    from engine.product_facts import ProductFacts
    from engine.query import parse_query
    from engine.rank import KindSupport

    facts = [ProductFacts(product="Differin Gel (adapalene 0.1%)", category="skincare", product_type="retinoid",
                          facts={"prescription_only": True, "strength": "strong"},
                          sources=["https://www.example-pharmacy.co.uk/differin"], checked_on=date(2026, 10, 14)),
             ProductFacts(product="Acme Gentle Retinol Serum", category="skincare", product_type="retinoid",
                          facts={"prescription_only": False, "strength": "gentle"},
                          sources=["https://www.example-maker.co.uk/serum"], checked_on=date(2026, 10, 14))]
    kinds = [KindSupport("adalpalene", "adalpalene", 0.6, 1), KindSupport("encapsulated retinol",
                                                                         "encapsulated retinol", 0.4, 1)]
    beginner = parse_query("retinol for a beginner with sensitive skin")
    assert _unsuited_kinds(kinds, beginner, facts) == {"adalpalene"}
    assert _unsuited_kinds(kinds, parse_query("retinol for acne scars"), facts) == set()


def test_a_picks_writers_names_tell_its_kind_too():
    # b06 after the variable-temperature line left: "Avoid: gooseneck" under the Fellow Stagg EKG, which its writers
    # call their Stagg gooseneck. The names a pick's writers give it say what kind it is, as its shown name does.
    picks = (mentions(3, "Fellow Stagg EKG", written_as="Stagg gooseneck kettle")
             + mentions(3, "Acme kettle", written_as="Acme kettle"))
    notes = [note("gooseneck", "t1", stance="warn", weight=-0.7,
                  quote="A gooseneck is useless unless you brew pour over, skip it."),
             note("glass kettle", "t2", weight=0.4, quote="A glass kettle is great, you see the scale building up.")]
    assert shown(notes, "electric kettle", "electric kettle that lasts 10+ years", picks=picks) == [
        (wording.LOOK_FOR, "glass kettle")]


def test_a_wider_kinds_advice_never_counts_against_a_narrower_ones():
    # From the 18 Oct sweep: praise for a knife sharpener says nothing for a pull-through one, nor praise for a coating
    # for a non-stick one.
    notes = [note("pull-through sharpener", "t1", stance="warn", weight=-2.0,
                  quote="A pull-through sharpener chews up the edge, skip it."),
             note("knife sharpener", "t2", weight=1.3, quote="A knife sharpener is great, mine keeps every edge keen."),
             note("sharpening", "t1", weight=0.3, quote="Sharpening is great once you learn it, takes minutes.")]
    assert (wording.AVOID, "pull-through sharpener") in shown(notes, "chef knife", "best chef knife under £100")
    notes = [note("non-stick coating", "t1", stance="warn", weight=-1.2,
                  quote="The non-stick coating flaked off the basket in a year."),
             note("coating", "t2", weight=1.0, quote="A ceramic coating is great, still like new.")]
    assert (wording.AVOID, "non-stick coating") in shown(notes, "air fryer", "air fryer that lasts")


def test_a_kind_said_without_something_is_its_opposite_never_the_same_kind():
    # "fridge without an ice maker" and "ice maker" agree (a quiet fridge has no ice maker): both stay.
    notes = [note("fridge without an ice maker", "t1", weight=1.2,
                  quote="A fridge without an ice maker is great, ours is silent."),
             note("ice maker", "t2", stance="warn", weight=-1.2, quote="The ice maker is the loud part, skip it.")]
    assert sorted(shown(notes, "fridge", "fridge freezer that's quiet", category="general")) == sorted([
        (wording.LOOK_FOR, "fridge without an ice maker"), (wording.AVOID, "ice maker")])
    notes = [note("silicone-free", "t1", weight=0.6, quote="Silicone-free is great, my curls are lighter."),
             note("heavy silicone use", "t2", stance="warn", weight=-0.6,
                  quote="Heavy silicone use built up on my hair, skip it."),
             note("silicone products", "t1", stance="warn", weight=-0.3,
                  quote="Silicone products weighed my hair down, skip them.")]
    assert (wording.LOOK_FOR, "silicone-free") in shown(notes, "conditioner", "conditioner for dry damaged hair",
                                                        category="haircare")


def test_a_narrower_kind_counts_only_when_it_is_one_of_the_same_thing():
    # Its further words say which of them it is ("heavy wool coat" is a wool coat); "merino hiking socks" are no
    # hiking boots, "cleansing brushes" no BHA cleanser.
    notes = [note("wool coats in rain", "t1", stance="warn", weight=-0.3,
                  quote="Wool coats in rain soak through and smell, skip them."),
             note("heavy wool coat", "t2", weight=0.55, quote="A heavy wool coat is great, warm to minus ten.")]
    assert (wording.AVOID, "wool coats in rain") not in shown(notes, "winter coat", "winter coat", category="general")
    notes = [note("hiking boots", "t1", stance="warn", weight=-0.5,
                  quote="Hiking boots look wrong with a suit, skip them."),
             note("merino hiking socks", "t2", weight=0.9, quote="Merino hiking socks are great, no blisters.")]
    assert (wording.AVOID, "hiking boots") in shown(notes, "boots", "chelsea boots that can be resoled",
                                                    category="general")
    # "salicylic acid wash" names a rinse-off form, so a cleanser is advice there (module 1's forms).
    items = mentions(3, "Acme wash", category="skincare")
    notes = [note("BHA cleanser", "t1", weight=0.3, quote="A BHA cleanser is great, my pores are clearer."),
             note("cleansing brushes", "t2", stance="warn", weight=-0.5,
                  quote="Cleansing brushes scratched my face, skip them.")]
    answer = write_answer(rank_products(items, "skincare", notes, {}), bodies_for(*items, *notes),
                          "salicylic acid product", request="salicylic acid wash", forms_asked=("cleanser",))
    assert (wording.LOOK_FOR, "BHA cleanser") in [(item.advice, item.kind) for item in answer.look_for]


def test_only_as_much_credible_advice_the_other_way_outweighs_a_line():
    # A cast iron answer: a strong warning against non-stick pans stays beside weaker praise for two kinds of them.
    notes = [note("non-stick pans", "t1", stance="warn", weight=-10.0,
                  quote="Non-stick pans wear out in a couple of years, skip them."),
             note("light nonstick pan", "t2", weight=3.0, quote="A light nonstick pan is great for eggs."),
             note("hard-anodized nonstick pan", "t1", weight=3.0, quote="A hard-anodized nonstick pan is great.")]
    assert (wording.AVOID, "non-stick pans") in shown(notes, "cast iron skillet", "cast iron skillet for a beginner")
    stronger = notes + [note("restaurant nonstick pan", "t2", weight=4.5,
                             quote="A restaurant nonstick pan is great, cheap and tough.")]
    assert (wording.AVOID, "non-stick pans") not in shown(stronger, "cast iron skillet",
                                                          "cast iron skillet for a beginner")


def line_pick(model, stance="recommend"):
    """A brand-level pick ("Bonavita", ranked as a line), one of its products ranked beside it (one mention: never a
    pick of its own), and two more picks."""
    weight = -1.0 if stance == "warn" else None
    return (mentions(3, "Bonavita", key="kitchen:bonavita")
            + [mention(model, "t1", key="kitchen:" + model.lower(), written_as=model, stance=stance, weight=weight)]
            + mentions(3, "Acme kettle", key="kitchen:acme kettle")
            + mentions(3, "Bolt kettle", key="kitchen:bolt kettle"))


def test_a_line_picks_products_say_which_kinds_of_the_type_it_holds():
    # b06: "Avoid: variable temperature kettle" under the Bonavita kettle line, whose writers' most named product is its
    # variable temperature gooseneck; and the quiet kettle answers, under the OXO line's adjustable temperature kettle.
    variable = note("variable temperature kettle", "t1", stance="warn", weight=-1.6,
                    quote="Every variable temperature kettle I owned broke inside a year.")
    glass = note("glass kettle", "t2", weight=0.4, quote="A glass kettle is great, you see the scale building up.")
    for model in ("Bonavita variable temperature gooseneck", "Bonavita adjustable temp kettle"):
        assert shown([variable, glass], "electric kettle", "electric kettle that lasts 10+ years",
                     picks=line_pick(model)) == [(wording.LOOK_FOR, "glass kettle")], model
    # A product of the line its credible writers only warn against isn't what the pick recommends: warning against its
    # kind agrees with them.
    assert (wording.AVOID, "variable temperature kettle") in shown(
        [variable, glass], "electric kettle", "electric kettle that lasts 10+ years",
        picks=line_pick("Bonavita variable temperature gooseneck", stance="warn"))
    # Its products tell only kinds of the type asked for: a set of knives under a knife line says nothing of knife sets.
    sets = note("knife sets", "t1", stance="warn", weight=-0.8, quote="Knife sets are a waste, buy one good knife.")
    knives = (mentions(3, "Victorinox", key="kitchen:victorinox")
              + [mention("Victorinox knife set", "t1", key="kitchen:victorinox knife set")]
              + mentions(3, "Acme chef knife", key="kitchen:acme chef knife")
              + mentions(3, "Bolt chef knife", key="kitchen:bolt chef knife"))
    assert (wording.AVOID, "knife sets") in shown([sets], "chef knife", "best chef knife under £100", picks=knives)


def test_a_line_left_out_for_saying_the_opposite_leaves_its_place_empty():
    # The lines after the first three are weaker advice; one never comes in for a line left out.
    picks = mentions(3, "Panasonic inverter microwave") + mentions(3, "Acme microwave")
    notes = [note("inverter microwave", "t1", stance="warn", weight=-0.9,
                  quote="An inverter microwave died on me in two years, never again."),
             note("microwave drawer", "t2", weight=0.6, quote="A microwave drawer is great in a small kitchen."),
             note("solo microwave", "t1", weight=0.5, quote="A solo microwave is great, nothing to break."),
             note("countertop convection oven", "t2", weight=0.4, quote="A countertop convection oven is great.")]
    assert shown(notes, "microwave", "microwave with a grill", picks=picks) == [
        (wording.LOOK_FOR, "microwave drawer"), (wording.LOOK_FOR, "solo microwave")]


def test_looking_for_a_kind_free_of_what_the_request_refuses_agrees_with_it():
    free = note("PFAS-free pans", "t1", weight=0.8, quote="PFAS-free pans are great now, ceramic ones last.")
    assert shown([free], "frying pan", "non stick pan without teflon", asks=("PFAS-free",)) == [
        (wording.LOOK_FOR, "PFAS-free pans")]
    against = note("PFAS-free pans", "t1", stance="warn", weight=-0.8,
                   quote="PFAS-free pans lose their slickness in months, skip them.")
    assert shown([against], "frying pan", "non stick pan without teflon", asks=("PFAS-free",)) == []
