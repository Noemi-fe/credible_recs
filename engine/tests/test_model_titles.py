"""A brand-line pick is titled by the model its credible writers clearly name most (26 Oct 2026, the names builder;
Noemi approved it in principle on 26 Oct 2026, decision 3, first part: "model names instead of lines").

ChatGPT titles its picks by model ("Victorinox Fibrox 20 cm", "MacBook Air M4"); ours was "Victorinox chef knife line"
with "Most named model: ..." under it. Now, when one model of the line clearly leads the models its credible writers
name, the pick is titled by that model, and the line stays as honest context: how many credible voices are about the
model and how many about the line in general. Only what is shown changes: the pick is still the line's, so its score,
its support, its reason and its place in the ranking are the line's. Clearly leads: at least BRAND_MODEL_TITLE_MIN_CREDIBLE
credible recommendations, at least BRAND_MODEL_TITLE_LEAD_RATIO times as many as any other model of the line, and at
least BRAND_MODEL_TITLE_MIN_SHARE of all the credible recommendations that name one of the line's models. Never a
model that is discontinued, sold only abroad while another model of the line is sold here, not known as one product,
named with a size first, or less suited to the request than the line. No clear lead: the line's name and "Most named
model", as before.

Every library, product, price and comment here is made up.
"""

from datetime import date

import pytest

from engine import config
from engine.answer import answer_to_dict, render_markdown, unverified_claims
from engine.brand_lines import BrandLine
from engine.pipeline import _one_model, answer_request
from engine.product_pages import ProductPage
from engine.tests.test_availability import listed
from engine.tests.test_pick_polish import FIBROX, KNIFE_REQUEST, TODAY, VICTORINOX, knife_library
from engine.tests.test_pipeline import praise, write_library

ROSEWOOD = "Victorinox Rosewood chef knife"
SIZED = "Victorinox 8 inch chef knife"


def lead(tmp_path, **kwargs):
    """Victorinox is the line (4 credible voices, two threads); the Fibrox has 2 (one a thread) and the Rosewood 1: the
    Fibrox is 2 of the 3 credible recommendations that name one of the line's models."""
    return answer_request(KNIFE_REQUEST, library_dir=knife_library(tmp_path, fibrox=(1, 1)), today=TODAY,
                          **{"prices": [], "product_facts": [], "product_pages": [], **kwargs})


def line_library(tmp_path, fibrox: int, rosewood: int, sized: int = 0, one_thread: tuple[str, ...] = ()):
    """The line's 4 credible voices, and the numbers of voices given for each of its models: spread over the two threads,
    or, for the models named in `one_thread`, all in the first (so a model with three or more voices is no pick of its
    own, which would put the line aside for it)."""
    def named(name, count, prefix):
        if name in one_thread:
            return [[praise(f"{prefix}0{i}", name, 3 + i) for i in range(count)], []]
        return [[praise(f"{prefix}{t}{i}", name, 3 + i) for i in range((count + 1 - t) // 2)] for t in (0, 1)]

    fibroxes, rosewoods, sizeds = named(FIBROX, fibrox, "f"), named(ROSEWOOD, rosewood, "r"), named(SIZED, sized, "s")
    return write_library(tmp_path, {
        "1knif01": ("Best first chef knife?", "Budget about 100.", [
            praise("v1a", "Victorinox", 5), praise("v1b", "Victorinox", 6),
            *fibroxes[0], *rosewoods[0], *sizeds[0],
            praise("m1a", "Mac Mighty chef knife", 7), praise("m1b", "Mac Mighty chef knife", 8),
            praise("t1a", "Tojiro DP gyuto", 5), praise("t1b", "Tojiro DP gyuto", 6),
        ]),
        "1knif02": ("Which chef knife lasts?", "Mine chipped.", [
            praise("v2a", "Victorinox", 9), praise("v2b", "Victorinox", 10),
            *fibroxes[1], *rosewoods[1], *sizeds[1],
            praise("m2a", "Mac Mighty chef knife", 4), praise("t2a", "Tojiro DP gyuto", 3),
        ]),
    }, community="chefknives")


def line_pick(result):
    return next(pick for pick in result.answer.picks if pick.product_key == "kitchen:victorinox")


# --- The title ---

def test_a_model_that_clearly_leads_its_line_titles_the_pick(tmp_path):
    result = lead(tmp_path)
    pick = result.answer.picks[0]
    assert pick.name == FIBROX and pick.product_key == "kitchen:victorinox"
    assert pick.line == VICTORINOX
    assert pick.model is None and pick.model_price is None  # the title is the model: no second "Most named model"


def test_the_line_stays_the_ranking_only_what_is_shown_changes(tmp_path, monkeypatch):
    titled = lead(tmp_path / "a").answer.picks[0]
    monkeypatch.setattr(config, "BRAND_MODEL_TITLES_ON", False)
    line = lead(tmp_path / "b").answer.picks[0]
    assert line.name == VICTORINOX and line.model == FIBROX and line.line is None
    for field in ("rank", "product_key", "score", "support", "reason", "voices", "disagreement", "breakdown"):
        assert getattr(titled, field) == getattr(line, field), field


def test_the_note_says_how_many_voices_are_about_the_model_and_how_many_about_the_line(tmp_path):
    pick = lead(tmp_path).answer.picks[0]
    assert pick.voices["recommend"] == 4
    assert pick.line_note == config.BRAND_MODEL_TITLE_NOTE.format(line=VICTORINOX, model_voices=2, line_voices=4)
    assert pick.line_note == ("The model named most in the Victorinox chef knife line. Credible voices: 2 about this "
                              "model, 4 about the line in general. The counts below are the line's.")


def test_one_voice_about_the_line_reads_as_well_as_many():
    # Numbers, not "1 credible voices": the note reads the same for any count.
    assert "1 about the line in general" in config.BRAND_MODEL_TITLE_NOTE.format(line="X line", model_voices=3,
                                                                                line_voices=1)


def test_the_text_and_the_json_say_the_same(tmp_path):
    result = lead(tmp_path)
    pick = result.answer.picks[0]
    text = render_markdown(result.answer)
    assert f"## 1. {FIBROX}" in text and pick.line_note in text
    assert "Most named model" not in text
    data = answer_to_dict(result.answer)["picks"][0]
    assert (data["name"], data["line"], data["line_note"], data["model"]) == (FIBROX, VICTORINOX, pick.line_note, None)


def test_a_pick_without_a_leading_model_is_the_line_as_before(tmp_path):
    # Mac and Tojiro are specific products: they have no line and no note.
    result = lead(tmp_path)
    for pick in result.answer.picks[1:]:
        assert pick.line is None and pick.line_note is None


# --- Clearly leads ---

def test_two_models_with_as_many_voices_name_no_leader_and_the_line_keeps_its_name(tmp_path):
    result = answer_request(KNIFE_REQUEST, library_dir=line_library(tmp_path, fibrox=2, rosewood=2),
                            prices=[listed(ROSEWOOD)], product_facts=[], product_pages=[], today=TODAY)
    pick = line_pick(result)
    assert pick.name == VICTORINOX and pick.line is None and pick.line_note is None
    assert pick.model in (FIBROX, ROSEWOOD)  # "Most named model", as before


def test_a_model_needs_twice_the_voices_of_any_other_model(tmp_path):
    # Fibrox 3 of 5 against the Rosewood's 2: the most named, by one voice: not a clear lead, so the old line stays.
    only = (FIBROX,)  # all in one thread: no pick of its own, so the line stays a pick
    result = answer_request(KNIFE_REQUEST, library_dir=line_library(tmp_path, fibrox=3, rosewood=2, one_thread=only),
                            prices=[], product_facts=[], product_pages=[], today=TODAY)
    pick = line_pick(result)
    assert pick.name == VICTORINOX and pick.line_note is None and pick.model == FIBROX
    # Twice the next model's voices is clear.
    again = answer_request(KNIFE_REQUEST, library_dir=line_library(tmp_path / "b", fibrox=4, rosewood=2,
                                                                   one_thread=only),
                           prices=[], product_facts=[], product_pages=[], today=TODAY)
    assert line_pick(again).name == FIBROX


def test_a_model_needs_a_share_of_the_models_voices_too(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "BRAND_MODEL_TITLE_MIN_SHARE", 0.9)  # the Fibrox has 2 of the 3
    pick = lead(tmp_path).answer.picks[0]
    assert pick.name == VICTORINOX and pick.line_note is None and pick.model == FIBROX


def test_a_leader_needs_enough_credible_voices(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "BRAND_MODEL_TITLE_MIN_CREDIBLE", 3)  # the Fibrox has 2
    pick = lead(tmp_path).answer.picks[0]
    assert pick.name == VICTORINOX and pick.line_note is None and pick.model == FIBROX


def test_a_leader_we_do_not_know_as_one_product_titles_nothing(tmp_path):
    # The sized knife has the most voices (4 of 6, twice the Fibrox's) but nothing says it is one product (a size writers
    # added); the Fibrox, known, is the "Most named model" as before. The title is never a name we can't stand behind.
    result = answer_request(KNIFE_REQUEST, library_dir=line_library(tmp_path, fibrox=2, rosewood=0, sized=4, one_thread=(SIZED,)),
                            prices=[], product_facts=[], product_pages=[], today=TODAY)
    pick = line_pick(result)
    assert pick.name == VICTORINOX and pick.line_note is None and pick.model == FIBROX


def test_a_discontinued_leader_titles_nothing(tmp_path):
    gone = listed(FIBROX, available=False)
    result = answer_request(KNIFE_REQUEST, library_dir=knife_library(tmp_path, fibrox=(1, 1)), prices=[gone],
                            product_facts=[], product_pages=[], today=TODAY)
    assert FIBROX not in [p.name for p in result.answer.picks]  # a product no longer made is left out altogether


def test_a_leader_sold_only_abroad_titles_nothing_when_another_model_is_sold_here(tmp_path):
    abroad = listed(FIBROX, available=False).model_copy(update={"not_in_uk": True})
    here = listed(ROSEWOOD, available=True)
    result = answer_request(KNIFE_REQUEST, library_dir=knife_library(tmp_path, fibrox=(1, 1)), prices=[abroad, here],
                            product_facts=[], product_pages=[], today=TODAY)
    pick = line_pick(result)
    assert pick.name == VICTORINOX and pick.line_note is None


def test_a_leader_sold_only_abroad_still_titles_when_no_other_model_is_sold_here(tmp_path):
    abroad = listed(FIBROX, available=False).model_copy(update={"not_in_uk": True})
    result = answer_request(KNIFE_REQUEST, library_dir=knife_library(tmp_path, fibrox=(1, 1)), prices=[abroad],
                            product_facts=[], product_pages=[], today=TODAY)
    pick = result.answer.picks[0]
    assert pick.name == FIBROX and pick.availability.available is False
    assert pick.availability.text == "Not sold in the UK, checked 9 Oct 2026"  # said honestly beside the title


@pytest.mark.parametrize("name, one", [
    ("Victorinox Fibrox chef knife", True), ("Lenovo Legion 5a Gen 10", True), ("Brooks Adrenaline/Glycerine GTS", False),
    ("Sony WH-1000XM4 and XM5", False), ("Bose QuietComfort Pros (Ultras?)", False), ("Mac Mighty & Chef", False),
    ("Kobo Libra, Clara", False), ("Roborock S7 or S8", False),
])
def test_a_name_that_gives_two_models_is_no_title(name, one):
    assert _one_model(name) is one


@pytest.mark.parametrize("name, titles", [
    ('8" wusthof classic', False), ("8 inch Victorinox Fibrox", False), ("10in Field skillet", False),
    ("Wusthof Classic 8 inch", True), ("Lodge Blacklock 10 inch skillet", True),
])
def test_a_name_with_a_size_first_is_no_title(name, titles):
    from engine.pipeline import _without_leading_size

    assert (_without_leading_size(name) == name) is titles


@pytest.mark.parametrize("name, request_text, another", [
    ("Tramontina Professional Nonstick", "stainless steel pan for searing", True),  # the 26 Oct baseline's case
    ("Tramontina Professional Non-Stick", "stainless steel pan for searing", True),
    ("Lodge Chef Collection carbon steel", "stainless steel pan for searing", True),
    ("Tramontina Gourmet Tri-Ply Clad stainless steel", "stainless steel pan for searing", False),  # the material asked
    ("Tramontina Professional Nonstick", "nonstick frying pan", False),  # non-stick is no material asked for here
    ("Tramontina Professional Nonstick", "frying pan", False),  # a request naming no material
    ("Lodge Blacklock skillet", "cast iron skillet", False),
    ("Lodge enamel skillet", "cast iron skillet", False),  # a type's own material ("cast iron skillet") is no feature
])
def test_a_model_that_says_another_material_than_the_one_asked_for_is_no_title(name, request_text, another):
    from engine.features import request_features
    from engine.pipeline import _names_another_material
    from engine.query import parse_query

    assert _names_another_material(name, request_features(parse_query(request_text))) is another


def test_a_model_less_suited_to_the_request_than_its_line_is_no_title():
    # Found in the 26 Oct baseline: "stainless steel pan for searing" put the Tramontina line first because its voices
    # praise stainless steel, while its most named model, a non-stick pan, ranks below it for lacking that.
    from types import SimpleNamespace as Score

    from engine.pipeline import WIDER_READING_SHORTFALL, _suits_the_request

    def made(**changes):
        return Score(**({"on_skip_list": False, "shortfall": None, "unconfirmed": 0, "features_praised": ()} | changes))

    line = made(features_praised=("stainless steel",))
    assert _suits_the_request(made(features_praised=("stainless steel",)), line)
    assert not _suits_the_request(made(), line)  # the line's voices praise what the request asks, the model's don't
    assert _suits_the_request(made(), made())  # a request naming no feature: nothing sets them apart
    assert not _suits_the_request(made(unconfirmed=1), made())  # a must-have its facts can't confirm
    assert not _suits_the_request(made(on_skip_list=True), made())
    assert not _suits_the_request(made(shortfall=WIDER_READING_SHORTFALL), made())
    assert not _suits_the_request(made(shortfall="more credible warnings than recommendations"), made())
    # Only the bar's counts: a model that is short of the picks bar is what a line is for.
    assert _suits_the_request(made(shortfall="1 of 3 credible recommendations"), made())


# --- What is shown with the model ---

def test_the_models_own_price_and_availability_are_shown_when_it_has_them(tmp_path):
    own = listed(FIBROX, available=True, price=41.5, shop="Victorinox UK")
    result = lead(tmp_path, prices=[own])
    pick = result.answer.picks[0]
    assert pick.price.text == "£41.50 at Victorinox UK, checked 9 Oct 2026"
    assert pick.availability.text == "Sold at Victorinox UK, checked 9 Oct 2026"
    assert pick.model_price is None  # said once, as the pick's own price


def test_a_model_with_no_price_of_its_own_keeps_the_lines_from_price(tmp_path):
    line = BrandLine(brand="Victorinox", category="kitchen", product_type="chef knife", sells=True,
                     sources=["https://maker.example/knives", "https://shop.example/knife"], checked_on=TODAY,
                     range_page="https://maker.example/knives", from_price=25.0, from_price_shop="Made-up Cookshop",
                     from_price_url="https://shop.example/knife", from_price_checked_on=TODAY, note="Made up.")
    pick = lead(tmp_path, brand_lines=[line]).answer.picks[0]
    assert pick.name == FIBROX
    assert pick.price.text == "From £25 at Made-up Cookshop, checked 9 Oct 2026" and pick.price.from_price
    assert pick.range is not None and pick.range.url == "https://maker.example/knives"  # no page of the model's own


def test_quotes_about_the_model_come_first(tmp_path):
    result = lead(tmp_path)
    pick = result.answer.picks[0]
    assert [q.comment_id[0] for q in pick.quotes[:2]] == ["f", "f"]  # the Fibrox's two voices
    assert len(pick.quotes) == config.QUOTES_PER_PICK
    assert len({q.comment_id for q in pick.quotes}) == len(pick.quotes)
    assert any(q.comment_id.startswith("v") for q in pick.quotes[2:])  # then the line's own
    assert unverified_claims(result.answer, result.bodies) == []


def test_a_models_own_page_and_image_replace_the_lines(tmp_path):
    page = ProductPage(product=FIBROX, category="kitchen", product_type="chef knife",
                       page="https://maker.example/fibrox", shop="Made-up Maker", image="https://maker.example/f.jpg",
                       image_page="https://maker.example/fibrox", sources=["https://maker.example/fibrox"],
                       checked_on=date(2026, 10, 9))
    line = BrandLine(brand="Victorinox", category="kitchen", product_type="chef knife", sells=True,
                     sources=["https://maker.example/knives"], checked_on=TODAY, range_page="https://maker.example/knives",
                     note="Made up.")
    pick = lead(tmp_path, product_pages=[page], brand_lines=[line]).answer.picks[0]
    assert pick.link is not None and pick.link.url == "https://maker.example/fibrox"
    assert pick.image is not None and pick.image.url == "https://maker.example/f.jpg" and FIBROX in pick.image.alt
    assert pick.range is None  # the model's own page stands where the line's range page did


def test_also_worth_a_look_items_are_never_titled_by_a_model(tmp_path):
    result = lead(tmp_path)
    assert all(item.name != FIBROX for item in result.answer.worth_a_look)
    assert not any(hasattr(item, "line_note") and item.line_note for item in result.answer.worth_a_look)


def test_the_skip_list_never_repeats_the_title(tmp_path):
    result = lead(tmp_path)
    assert FIBROX not in [item.name for item in result.answer.skip]


def test_the_wording_is_marked_as_the_builders(tmp_path):
    import inspect

    source = inspect.getsource(config)
    assert "(26 Oct 2026, the names builder; approved in principle by Noemi, wording Claude's)" in source


def test_a_testers_card_keeps_the_note_whole_under_the_title(tmp_path):
    from engine.blind_test import BLIND_TEST_WORDS_PER_PICK, shown_from_ours

    result = lead(tmp_path)
    card = shown_from_ours(answer_to_dict(result.answer)).split("\n\n**2. ")[0]
    pick = result.answer.picks[0]
    # Without its last sentence: the counts it points to are on the page, not on the card.
    assert card.startswith(f"**1. {FIBROX}**\n\n{pick.line_note.removesuffix(' ' + config.BRAND_MODEL_TITLE_WHOSE)}\n\n")
    assert "counts below" not in card
    assert "Most named model" not in card
    assert len(card.split()) <= BLIND_TEST_WORDS_PER_PICK + len(f"**1. {FIBROX}**".split())


def test_a_titled_pick_has_no_one_line_summary_since_it_sums_up_the_lines_voices(tmp_path, monkeypatch):
    from engine import summaries
    from engine.summaries import Summary, summary_key

    line = Summary(product=VICTORINOX, category="kitchen", product_type="chef knife", cites=["v1a", "v2a"],
                   text="Owners say it has lasted for years.", written_at="2026-10-26T10:00:00Z", writer="claude-code",
                   instructions_version=summaries.current_version())
    kept = {summary_key("kitchen", VICTORINOX): line}
    monkeypatch.setattr(config, "BRAND_MODEL_TITLES_ON", False)
    assert lead(tmp_path / "a", summaries=kept).answer.picks[0].summary is not None  # the line's, as any pick's
    monkeypatch.setattr(config, "BRAND_MODEL_TITLES_ON", True)
    titled = lead(tmp_path / "b", summaries=kept).answer.picks[0]
    assert titled.name == FIBROX and titled.summary is None  # "In short" would read as about the model
