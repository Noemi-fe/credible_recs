"""The words that show a comment talks about a need (config.NEEDS; 15 Oct 2026).

Three things found on the library's answers:
- the oily-skin need missed the words skincare writers use most for it besides "oily": sebum, sebaceous filaments,
  oiliness, oil control, mattifying. A recommendation saying a niacinamide serum helped with sebaceous pores didn't
  talk about oily skin, so under the need rule its product couldn't be a pick. Other needs missed obvious forms too
  (dehydration, flaking, broke out, blemishes, aging skin, t-zone, closed comedones, "no cast", smell, rosacea, eczema,
  "my skin reacts");
- redness counted as sensitive skin wherever it was said, so a writer who used exfoliant pads to clear bumps and
  redness on their underarms talked about sensitive skin, and that voice alone made the pads a pick for a gentle
  exfoliant for sensitive skin. Redness is a sign of sensitive skin when it is a reaction, or its absence ("no
  redness", "it caused redness"); redness a product treats is a need of its own ("azelaic acid for redness");
- a recommendation's own quote saying the product didn't help with what was asked ("it did nothing for my oily skin")
  talks about the need, but against it, like a quote saying the opposite (config.OPPOSITE_QUOTE_PATTERNS): it gives
  the product no credit for talking about the need, and is shown after the other quotes. A writer saying another
  product didn't help, before recommending this one, still talks about the need: they have it, and compared.

Every request, product and comment here is made up; nothing reads data/.
"""

import pytest

from engine.answer import unverified_claims
from engine.needs import needs_met, request_needs, said_not_to_help
from engine.pipeline import WIDER_READING_SHORTFALL, answer_request
from engine.query import parse_query
from engine.tests.test_pipeline_ingredients import write_library


def needs_of(request: str):
    return request_needs(parse_query(request, model=None))


def met(request: str, body: str) -> tuple[str, ...]:
    return needs_met(body, needs_of(request))


# --- Oily skin ---

@pytest.mark.parametrize("body", [
    "It cut my sebum right down.",
    "It keeps my sebaceous filaments in check.",
    "Great for oiliness by midday.",
    "My skin gets oilier in summer and this copes.",
    "Really good oil control all day.",
    "The oil-control version is the one to get.",
    "It controls oil without drying me out.",
    "Very mattifying, even in August.",
    "No greasiness at all, even on my nose.",
])
def test_the_words_writers_use_for_oily_skin_talk_about_it(body):
    assert met("moisturiser for oily skin", body) == ("oily",)


def test_oil_alone_still_isnt_oily_skin():
    assert met("moisturiser for oily skin", "I take my makeup off with a cleansing oil.") == ()


@pytest.mark.parametrize("request_text", ["oil control sunscreen", "sunscreen for oiliness", "moisturiser for sebum"])
def test_a_request_in_those_words_asks_for_the_oily_skin_need(request_text):
    # "oil control sunscreen" had asked for "oil" and "control", two needs found in any comment saying either word.
    assert [need.name for need in needs_of(request_text)] == ["oily"]


# --- Other needs' missing words ---

@pytest.mark.parametrize("request_text, body, need", [
    ("sunscreen for dry skin", "My skin feels much less dehydrated with it.", "dry"),
    ("sunscreen for dry skin", "No more dehydration lines by the afternoon.", "dry"),
    ("moisturiser for dry skin", "The flaking around my nose stopped.", "dry"),
    ("moisturiser for dry skin", "No more flakes on my cheeks.", "dry"),
    ("moisturiser for sensitive skin", "It's calm on my rosacea.", "sensitive"),
    ("moisturiser for sensitive skin", "My eczema patches didn't mind it.", "sensitive"),
    ("moisturiser for sensitive skin", "My skin reacts to most creams, not to this one.", "sensitive"),
    ("cleanser for acne-prone skin", "I broke out the first week, then it settled.", "acne-prone"),
    ("cleanser for acne-prone skin", "It stopped me breaking out on my chin.", "acne-prone"),
    ("cleanser for acne-prone skin", "Far fewer blemishes since I started it.", "acne-prone"),
    ("cleanser for acne-prone skin", "It keeps the zits away.", "acne-prone"),
    ("moisturiser for mature skin", "Lovely on my aging skin.", "mature"),
    ("moisturiser for combination skin", "It keeps my t-zone in check.", "combination"),
    ("non-comedogenic moisturiser", "No closed comedones from it, unlike the last one.", "non-comedogenic"),
    ("non-comedogenic moisturiser", "It says noncomedogenic on the tube.", "non-comedogenic"),
    ("sunscreen that leaves no white cast", "It leaves no cast on my deep skin tone.", "no white cast"),
    ("sunscreen that leaves no white cast", "Zero white-cast, finally.", "no white cast"),
    ("fragrance-free moisturiser", "It doesn't smell of anything.", "fragrance-free"),
])
def test_obvious_missing_words_of_other_needs(request_text, body, need):
    assert need in met(request_text, body)


@pytest.mark.parametrize("request_text, needs", [
    # Words that only comments use for a need, so a request in them keeps its own word.
    ("litter box that doesn't smell", ["smell"]),
    # Changed on purpose 16 Oct 2026 (the interview-fixes builder, the orchestrator's item): rosacea reads as sensitive
    # skin, so its rules apply ("retinol for someone with rosacea" had picked Differin Gel); was ["rosacea"].
    ("moisturiser for rosacea", ["sensitive"]),
    ("frying pan that won't react with tomatoes", ["react", "tomatoes"]),
    # Nor does a kitchen request's cast iron name the white cast.
    ("a cast iron kettle", ["cast", "iron"]),
])
def test_a_request_keeps_its_own_words_where_only_comments_have_the_needs(request_text, needs):
    assert [need.name for need in needs_of(request_text)] == needs


def test_cast_iron_is_no_cast():
    assert met("sunscreen that leaves no white cast", "I put it on before frying in a cast iron pan.") == ()


# --- Redness ---

def test_redness_a_product_treats_is_not_sensitive_skin():
    # The case found on the library: exfoliant pads a writer used on their underarms to clear bumps and redness.
    assert met("gentle exfoliant for sensitive skin", "On my legs they clear the bumps and the redness too.") == ()


@pytest.mark.parametrize("body", [
    "No redness at all, even after a month.",
    "It caused redness on my cheeks every time.",
    "Zero redness, which never happens with acids for me.",
    "I never had any redness from it.",
])
def test_redness_as_a_reaction_or_its_absence_is_still_sensitive_skin(body):
    assert met("gentle exfoliant for sensitive skin", body) == ("sensitive",)


def test_a_request_about_redness_asks_about_redness_itself():
    needs = needs_of("azelaic acid for redness")
    assert [need.name for need in needs] == ["redness"]
    assert needs_met("It took my redness right down.", needs) == ("redness",)
    assert needs_met("It never irritated my skin.", needs) == ()  # that's sensitive skin, not what was asked


# --- A recommendation saying the product didn't help with the need ---

@pytest.mark.parametrize("quote, said", [
    ("It didn't do anything for my oily skin, but it's lovely and soft.", ("oily",)),
    ("Doesn't help my oily skin much, sadly.", ("oily",)),
    ("It did nothing for my oiliness.", ("oily",)),
    ("I bought it for my oily skin, which it didn't help with, but it's a great base.", ("oily",)),
    ("No difference in how oily my skin gets.", ("oily",)),
    # It helped: nothing said against the need.
    ("It keeps my oily skin matte all day.", ()),
    ("It didn't break me out and my oily skin loves it.", ()),
    # Another product didn't help; this one is the one recommended.
    ("The Cobalt Cream did nothing for my oily skin, but this one keeps it matte.", ()),
])
def test_what_a_quote_says_its_product_didnt_help_with(quote, said):
    assert said_not_to_help(quote, needs_of("moisturiser for oily skin")) == said


ALBA = ("Alba Cream", "moisturiser")
DUNE = ("Dune Cream", "moisturiser")


def used(cid, product, years, how):
    return cid, product, f"I've used the {product[0]} for {years} years and {how}.", "recommend"


def test_a_pick_isnt_made_by_a_voice_saying_it_didnt_help_with_the_need(tmp_path):
    library = write_library(tmp_path, {
        "1oil01": ("Moisturiser recommendations?", [
            used("a1", ALBA, 2, "it didn't do anything for my oily skin, but it's lovely and soft"),
            used("a2", ALBA, 3, "it's lovely and soft"),
            used("d1", DUNE, 2, "it keeps my oily skin matte"), used("d2", DUNE, 3, "it's lovely and soft"),
        ]),
        "1oil02": ("Which moisturiser do you use?", [used("a3", ALBA, 4, "it's lovely and soft"),
                                                     used("d3", DUNE, 4, "it's lovely and soft")]),
    })
    result = answer_request("moisturiser for oily skin", library_dir=library, prices=[], product_facts=[],
                            brand_lines=[], summaries={})
    assert [pick.name for pick in result.answer.picks] == [DUNE[0]]
    alba = next(p for p in result.ranking.products if p.name == ALBA[0])
    assert alba.shortfall == WIDER_READING_SHORTFALL
    assert unverified_claims(result.answer, result.bodies) == []


def test_a_voice_saying_another_product_didnt_help_still_talks_about_the_need(tmp_path):
    library = write_library(tmp_path, {
        "1oil01": ("Moisturiser recommendations?", [
            ("d1", DUNE, "The Cobalt Cream did nothing for my oily skin, but I've used the Dune Cream for 2 years "
                         "and it's lovely and soft.", "recommend"),
            used("d2", DUNE, 3, "it's lovely and soft"),
        ]),
        "1oil02": ("Which moisturiser do you use?", [used("d3", DUNE, 4, "it's lovely and soft")]),
    })
    result = answer_request("moisturiser for oily skin", library_dir=library, prices=[], product_facts=[],
                            brand_lines=[], summaries={})
    assert [pick.name for pick in result.answer.picks] == [DUNE[0]]


def test_among_a_picks_quotes_the_one_saying_it_didnt_help_comes_last(tmp_path):
    library = write_library(tmp_path, {
        "1oil01": ("Moisturiser recommendations?", [
            used("d1", DUNE, 2, "it didn't do much for my oily skin, but it's lovely and soft"),
            used("d2", DUNE, 3, "it keeps my oily skin matte"),
        ]),
        "1oil02": ("Which moisturiser do you use?", [used("d3", DUNE, 4, "it's lovely and soft")]),
    })
    result = answer_request("moisturiser for oily skin", library_dir=library, prices=[], product_facts=[],
                            brand_lines=[], summaries={})
    pick = next(p for p in result.answer.picks if p.name == DUNE[0])
    assert [quote.comment_id for quote in pick.quotes] == ["d2", "d3", "d1"]
    assert pick.reason == "Recommended by 3 credible voices, 3 of them after long-term use, 1 of them about oily skin."
