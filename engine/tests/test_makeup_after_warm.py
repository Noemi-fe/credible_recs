"""Fix 1 after the profile warm (5 Nov 2026; Claude's technical calls, reported to Noemi): what the rules review, the
shopper review and the summary fact-check of the settled makeup answers still found. Which tips and quotes an answer
shows, a product's name, a price list's availability check and the two threads Noemi said to remove. None changes a
scoring weight, a product type or the picks bar.

Every comment, quote and product here is made up, but for real product names in the naming tests (names only).
"""

import pytest

from engine import config
from engine.answer import _names_this_makeup, _stands_alone, _undercuts, write_answer
from engine.needs import judged_needs
from engine.query import parse_query
from engine.rank import rank_products
from engine.tests.ranking_factories import bodies_for, mention, mentions, note


def kinds_shown(answer) -> list[str]:
    return [kind for item in answer.look_for for kind in item.kind.split(" or ")]


def answer_with(items, notes, product_type, request=None, needs=()):
    return write_answer(rank_products(items, "general", notes), bodies_for(*items, *notes), product_type,
                        request=request or product_type, needs=needs)


def two_notes(kind: str, first: str, second: str, stance: str = "recommend") -> list:
    return [note(kind, "t1", stance=stance, quote=first), note(kind, "t2", stance=stance, quote=second)]


# --- Tips about the type asked for ---

@pytest.mark.parametrize("product_type, kind, first, second", [
    # A tool, not the product: "it's the curler, not the mascara".
    ("mascara", "eyelash curler", "An eyelash curler matters far more, honestly.",
     "Get a good eyelash curler and any formula looks fine."),
    # Another product in its place.
    ("lipstick", "lip oils", "Lip oils are a softer choice these days.", "I moved to lip oils for everyday wear."),
    ("makeup primer", "skin prep", "Good skin prep does the job for me.", "Skin prep matters more than anything."),
    # A word that says nothing of what it is about.
    ("setting powder", "mini", "A mini is enough to start with.", "The mini sizes last ages anyway."),
])
def test_a_makeup_tip_that_names_nothing_of_the_type_asked_for_is_left_out(product_type, kind, first, second):
    items = (mentions(3, f"Velo {product_type}", category="general")
             + mentions(3, f"Halo {product_type}", category="general"))
    answer = answer_with(items, two_notes(kind, first, second), product_type)
    assert kind not in kinds_shown(answer)


@pytest.mark.parametrize("product_type, kind", [
    ("makeup primer", "silicone primer"),  # the type's own last word
    ("setting spray", "hydrating spray"),
    ("mascara", "tubing mascara"),  # one of module 1's names for it
    ("concealer", "color corrector"),
])
def test_a_makeup_tip_of_a_kind_of_the_type_stays(product_type, kind):
    items = (mentions(3, f"Velo {product_type}", category="general")
             + mentions(3, f"Halo {product_type}", category="general"))
    notes = two_notes(kind, f"A {kind} works best, in my experience.", f"I always look for a {kind} now.")
    assert kind in kinds_shown(answer_with(items, notes, product_type))


@pytest.mark.parametrize("product_type, kind, first, second", [
    # A skincare product offered in the makeup's place, named before the type ("as a primer") or not at all.
    ("makeup primer", "sunscreen as a primer", "A sunscreen as a primer is all I use.",
     "Try a sunscreen as a primer, it grips makeup well."),
    ("makeup primer", "moisturizer", "A moisturizer under makeup is plenty.", "Just a moisturizer works for me."),
    # Module 1 has no type by "spf" (config.TIP_OTHER_CATEGORY_WORDS).
    ("makeup primer", "spf as a primer", "An spf as a primer is all I need.", "I just use my spf as a primer."),
    ("foundation", "tinted moisturizer for oily skin", "A tinted moisturizer for oily skin beats all of them.",
     "I use a tinted moisturizer for oily skin instead now."),
])
def test_a_makeup_tip_offering_another_categorys_product_in_its_place_is_left_out(product_type, kind, first, second):
    items = (mentions(3, f"Velo {product_type}", category="general")
             + mentions(3, f"Halo {product_type}", category="general"))
    # Changed on purpose on 5 Nov 2026 (fix 2, from the rules review): the foundation case asked a plain "foundation",
    # where fa6ee08's code already left the tip out, so it never failed; it now asks "foundation for oily skin" with
    # its need, as the settled answer did. Until then the call read: answer_with(items, two_notes(kind, first, second),
    # product_type, request="makeup primer" if product_type == "makeup primer" else product_type).
    request, needs = {"makeup primer": ("makeup primer", ()),
                      "foundation": ("foundation for oily skin",
                                     judged_needs(parse_query("foundation for oily skin", model=None)))}[product_type]
    answer = answer_with(items, two_notes(kind, first, second), product_type, request=request, needs=needs)
    assert kind not in kinds_shown(answer)


def test_names_this_makeup_reads_the_types_names_and_its_last_word():
    assert _names_this_makeup("pore primer", "makeup primer")
    assert _names_this_makeup("silicone primers", "makeup primer")
    assert _names_this_makeup("micro-mist setting spray", "setting spray")
    assert not _names_this_makeup("eyelash curler", "mascara")
    assert not _names_this_makeup("drugstore", "blush")
    assert not _names_this_makeup("hydrating or rose water", "setting spray")


def test_an_avoid_never_goes_against_the_products_of_an_also_worth_a_look_line():
    # The settled eyeliner answer: "Avoid: pencil eyeliner" beside a brand line under Also worth a look whose
    # products are pencils. The line's own name ("Ashby eyeliner line") doesn't say so; its products do.
    items = (mentions(4, "Inkwell liquid liner", category="general")
             + mentions(4, "Quill liquid liner", category="general")
             + mentions(4, "Feather liquid liner", category="general")
             + [mention("Ashby", t, category="general", key="ashby") for t in ("t1", "t2", "t1")]
             + [mention("Ashby glide pencil eyeliner", "t1", category="general", key="ashby glide-pencil")])
    warnings = two_notes("pencil eyeliner", "Avoid pencil eyeliner, it smudges by noon.",
                         "Avoid pencil eyeliner, it tugs the lid.", stance="warn")
    ranking = rank_products(items, "general", warnings)
    answer = write_answer(ranking, bodies_for(*items, *warnings), "eyeliner", request="eyeliner")
    assert [item.product_key for item in answer.worth_a_look] == ["ashby"]
    assert "pencil eyeliner" not in kinds_shown(answer)


def test_an_avoid_never_goes_against_the_brands_products_of_a_brand_and_type_line():
    # The settled eyeliner answer's real shape: the line is grouped under the brand and the type's name ("Ashby
    # eyeliner line", key "ashby eyeliner"), and the brand's pencils under the brand alone ("ashby glide pencil").
    items = (mentions(4, "Inkwell liquid liner", category="general")
             + mentions(4, "Quill liquid liner", category="general")
             + mentions(4, "Feather liquid liner", category="general")
             + [mention("Ashby eyeliner", t, category="general", key="ashby eyeliner") for t in ("t1", "t2", "t1")]
             + [mention("Ashby glide pencil eyeliner", "t1", category="general", key="ashby glide pencil")])
    warnings = two_notes("pencil eyeliner", "Avoid pencil eyeliner, it smudges by noon.",
                         "Avoid pencil eyeliner, it tugs the lid.", stance="warn")
    ranking = rank_products(items, "general", warnings)
    answer = write_answer(ranking, bodies_for(*items, *warnings), "eyeliner", request="eyeliner")
    assert [item.product_key for item in answer.worth_a_look] == ["ashby eyeliner"]
    assert "pencil eyeliner" not in kinds_shown(answer)


def test_a_brand_and_type_lines_brand_products_count_only_in_makeup_answers():
    # Outside makeup the line holds only the products grouped under its own key, as before.
    items = (mentions(4, "Inkwell kettle", category="general") + mentions(4, "Quill kettle", category="general")
             + mentions(4, "Feather kettle", category="general")
             + [mention("Ashby kettle", t, category="general", key="ashby kettle") for t in ("t1", "t2", "t1")]
             + [mention("Ashby variable temperature kettle", "t1", category="general", key="ashby variable")])
    warnings = two_notes("variable temperature kettle", "Avoid a variable temperature kettle, the board fails.",
                         "Avoid a variable temperature kettle, more to break.", stance="warn")
    ranking = rank_products(items, "general", warnings)
    answer = write_answer(ranking, bodies_for(*items, *warnings), "kettle", request="kettle")
    assert [item.product_key for item in answer.worth_a_look] == ["ashby kettle"]
    assert "variable temperature kettle" in kinds_shown(answer)


# --- Quotes ---

@pytest.mark.parametrize("quote", [
    "Someone said the Rosa blush, yes this is a favourite of mine too!",
    "Like somebody else mentioned, the Rosa blush lasts all day.",
    "As others said, the Rosa blush is lovely.",
])
def test_a_quote_answering_what_someone_else_said_leans_on_the_thread(quote):
    assert not _stands_alone(quote, names_it=True)


def test_a_quote_naming_someone_without_saying_they_said_it_still_stands():
    assert _stands_alone("Someone gave me the Rosa blush years ago and I still love it.", names_it=True)


def test_other_products_others_recommended_are_no_answer_to_another_commenter():
    # "others" is other mats here, not other commenters: the quote stands alone (the sweep's yoga mat answer).
    assert _stands_alone("The Rosa mat beats the three others recommended online that I bought.", names_it=True)


def test_a_makeup_tip_naming_the_type_beside_spf_stays():
    items = (mentions(3, "Velo makeup primer", category="general")
             + mentions(3, "Halo makeup primer", category="general"))
    notes = two_notes("spf primer", "An spf primer saves a step.", "I look for an spf primer now.")
    assert "spf primer" in kinds_shown(answer_with(items, notes, "makeup primer"))


ROSA_PETAL = (("Rosa setting spray", "Rosa setting spray"), ("Petal setting spray", "Petal setting spray"))


def test_a_quote_telling_of_buying_another_instead_undercuts_its_product():
    m = mention("Rosa setting spray", "t1", category="general",
                quote="I liked Rosa setting spray but started buying Petal setting spray because it's cheaper than "
                      "Rosa setting spray.")
    assert _undercuts(m, ROSA_PETAL, "setting spray")


def test_starting_to_use_the_product_itself_is_no_undercut():
    m = mention("Rosa setting spray", "t1", category="general",
                quote="I tried Rosa setting spray last year and started buying it in the big size.")
    assert not _undercuts(m, ROSA_PETAL, "setting spray")


# --- Names ---

@pytest.mark.parametrize("written, shown", [
    ("Smashbox’s mattifying/Photo Finish primer", ["smashbox", "mattifying", "primer"]),
    ("Stila Waterproof Stay All Day", ["stila", "stay", "all", "day", "liquid", "liner"]),
    ("Stila Stay All Day Waterproof", ["stila", "stay", "all", "day", "liquid", "liner"]),
    ("Stila Stay All Day smudge proof/water proof gel eyeliner", ["stila", "gel", "eyeliner"]),
])
def test_makeup_names_written_out_by_their_aliases(written, shown):
    from engine.match_products import known_aliases, normalize_name, spell_out
    assert spell_out(normalize_name(written), known_aliases()["general"]) == shown


def test_a_name_written_exactly_as_a_listed_short_name_is_written_out_even_when_it_already_says_the_full_name():
    from engine.match_products import make_aliases, normalize_name, spell_out
    aliases = make_aliases({"Acme’s Glow/Matte primer": "Acme Glow primer"})
    assert spell_out(normalize_name("Acme’s Glow/Matte primer"), aliases) == ["acme", "glow", "primer"]
    # The full name in other spacing only is left as it is, as before ("Leap Frog" for LeapFrog).
    spaced = make_aliases({"Acme Glow": "AcmeGlow"})
    assert spell_out(normalize_name("Acme Glow"), spaced) == ["acme", "glow"]
    # A longer name that holds every word of the full one is left as it is, as before ("Timemore C2").
    longer = normalize_name("Acme’s Glow/Matte primer refill")
    assert spell_out(longer, aliases) == longer


# --- The price list ---

def test_the_ordinary_high_adherence_primer_is_checked_as_no_longer_sold():
    from engine.prices import DEFAULT_PRICES, load_prices
    entries = [p for p in load_prices(DEFAULT_PRICES) if p.product == "The Ordinary High-Adherence Silicone Primer"]
    assert entries and all(p.available is False and p.product_type == "makeup primer" for p in entries)


# --- Noemi's "Remove those 2 threads": the bundle's own paths ---

def test_the_bundle_never_writes_a_removed_thread_into_the_library(tmp_path):
    from engine.on_demand import Bundle, Item, write_threads
    removed = config.REMOVED_THREADS[0]
    bundle = Bundle({removed: Item(thread='{"made": "up"}', extraction='{"made": "up"}', entry="general/blush/",
                                   product_type="blush", added_at="2026-11-05T00:00:00+00:00"),
                     "1kept01": Item(thread='{"made": "up"}', extraction='{"made": "up"}', entry="general/blush/",
                                     product_type="blush", added_at="2026-11-05T00:00:00+00:00")})
    (tmp_path / "threads").mkdir()
    (tmp_path / "extracted").mkdir()
    assert write_threads(bundle, tmp_path, {}) == 1
    assert (tmp_path / "threads" / "1kept01.json").exists()
    assert not (tmp_path / "threads" / f"{removed}.json").exists()
    assert not (tmp_path / "extracted" / f"{removed}.json").exists()
