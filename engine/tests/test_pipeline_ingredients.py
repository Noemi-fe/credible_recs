"""Ingredient-led answers through the pipeline (13 Oct 2026): every product an answer shows contains the ingredient
asked for, labelled with its form. Since Noemi's decision 1 of 13 Oct 2026, an ingredient-led answer shows leave-on
forms only (serums, liquids, toners, pads, creams, spot treatments...), unless the request names another form
("salicylic acid wash"); a cleanser counts when the request names it ("salicylic acid cleanser").

The library is made up: products, writers, threads and quotes. Each comment's text is also its quote, so every quote
is found word for word, and each mention has the type the AI would give it (extraction v6 and later).
"""

import json
from datetime import date
from pathlib import Path

from engine import web
from engine.answer import render_markdown, unverified_claims
from engine.pipeline import answer_request
from engine.product_facts import Formula, ProductFacts
from engine.tests.factories import make_comment, make_thread, write_gold

TODAY = date(2026, 10, 9)
REQUEST = "salicylic acid for acne"

ACME = ("Acme 2% Salicylic Acid Serum", "serum")
BLOOM = ("Bloom Salicylic Cleanser", "cleanser")
CORRA = ("Corra Glow Powder", "exfoliant")  # its name doesn't say what it is made with
DUNE = ("Dune BHA Liquid", "exfoliant")  # a BHA: its formula decides whether it is salicylic acid
FERN = ("Fern Gentle Cleanser", "cleanser")  # no acid at all
ECHO = ("Echo Salicylic Peel", "exfoliant")  # warned against; a peel is rinse-off
HAZE = ("Haze Scrub", "exfoliant")  # warned against, no acid
OPAL = ("Opal Salicylic Gel", "exfoliant")  # warned against; a gel is leave-on
GILT = ("Gilt Salicylic Acid", "exfoliant")  # its name says the acid, not its form: an exfoliant may be a scrub
KIRI = ("Kiri Salicylic Pimple Patch", "pimple patch")  # a spot treatment, leave-on
IRIS = ("Iris Salicylic Toner", "toner")  # two recommendations: Also worth a look
JADE = ("Jade Mist", "toner")  # two recommendations, no acid
GALE = ("Gale Cream", "moisturiser")  # only in a thread that never names the acid


def praise(cid: str, product: tuple[str, str], years: int = 2) -> tuple:
    text = f"I've used the {product[0]} for {years} years and my skin is much clearer for it."
    return cid, product, text, "recommend"


def warn(cid: str, product: tuple[str, str]) -> tuple:
    return cid, product, f"I used the {product[0]} for two weeks and it burned my skin, avoid it.", "warn"


def write_library(tmp_path: Path, threads: dict[str, tuple[str, list[tuple]]]) -> Path:
    """{thread id: (title, [(comment id, (product, type), text, stance)])}, every thread in r/SkincareAddiction."""
    saved, extractions = [], {}
    for thread_id, (title, rows) in threads.items():
        url = f"https://www.reddit.com/r/SkincareAddiction/comments/{thread_id}/thread/"
        comments = [make_comment(cid, thread_id=thread_id, body=text,
                                 url=f"https://www.reddit.com/r/SkincareAddiction/comments/{thread_id}/comment/{cid}/")
                    for cid, _, text, _ in rows]
        post = "Mild acne, oily skin. Which cleanser, serum or spot treatment?"
        saved.append(make_thread(id=thread_id, title=title, body=post, url=url, comments=comments,
                                 num_comments=len(comments) + 20))
        extractions[thread_id] = [{"comment_id": cid, "product": product, "category": "skincare", "stance": stance,
                                   "quote": text, "product_type": product_type}
                                  for cid, (product, product_type), text, stance in rows]
    root = write_gold(tmp_path / "library", saved, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for thread_id, mentions in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v6", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions,
        }), encoding="utf-8")
    return root


def acne_library(tmp_path: Path) -> Path:
    return write_library(tmp_path, {
        "1sali01": ("What cleared your acne?", [
            praise("a1", ACME, 2), praise("a2", ACME, 3), praise("b1", BLOOM, 2), praise("b2", BLOOM, 4),
            praise("c1", CORRA, 2), praise("c2", CORRA, 3), praise("d1", DUNE, 2), praise("d2", DUNE, 3),
            praise("f1", FERN, 2), praise("f2", FERN, 3), warn("e1", ECHO), warn("h1", HAZE),
            praise("i1", IRIS, 2), praise("j1", JADE, 2), warn("o1", OPAL), praise("g4", GILT, 2),
            praise("g5", GILT, 3), praise("k1", KIRI, 2), praise("k2", KIRI, 3),
        ]),
        "1sali02": ("Salicylic acid recommendations?", [
            praise("a3", ACME, 5), praise("b3", BLOOM, 5), praise("c3", CORRA, 5), praise("d3", DUNE, 5),
            praise("f3", FERN, 5), warn("e2", ECHO), warn("h2", HAZE), praise("i2", IRIS, 3), praise("j2", JADE, 3),
            warn("o2", OPAL), praise("g6", GILT, 4), praise("k3", KIRI, 4),
        ]),
        "1sali03": ("Best moisturiser for dry skin?", [
            praise("g1", GALE, 2), praise("g2", GALE, 3), praise("g3", GALE, 4),
        ]),
    })


def facts(product: str, product_type: str, actives: list[str], form: str | None = None) -> ProductFacts:
    return ProductFacts(product=product, category="skincare", product_type=product_type, facts={},
                        sources=["https://facts.example/page"], checked_on=TODAY,
                        formula=Formula(actives=actives, form=form, sources=["https://facts.example/formula"],
                                        checked_on=TODAY))


def ask(tmp_path: Path, request: str = REQUEST, product_facts: list[ProductFacts] = ()):
    return answer_request(request, library_dir=acne_library(tmp_path), prices=[], product_facts=list(product_facts),
                          today=TODAY)


def picks(result) -> list[tuple[str, str | None]]:
    return [(pick.name, pick.form) for pick in result.answer.picks]


def left_out(result) -> dict[str, str]:
    return {item.name: item.reason for item in result.left_out_no_ingredient}


def by_form(result) -> dict[str, str]:
    return {item.name: item.reason for item in result.left_out_by_form}


def test_an_ingredient_led_answer_shows_leave_on_products_with_the_ingredient(tmp_path):
    # Changed on purpose 13 Oct 2026 (Noemi's decision 1: leave-on forms only): the cleanser was a pick. A spot
    # treatment (decision 2) is a leave-on form like the serum.
    result = ask(tmp_path)
    assert sorted(picks(result)) == [("Acme 2% Salicylic Acid Serum", "serum"),
                                     ("Kiri Salicylic Pimple Patch", "patch")]
    assert unverified_claims(result.answer, result.bodies) == []


def test_a_rinse_off_product_with_the_ingredient_is_left_out_and_says_how_to_see_it(tmp_path):
    result = ask(tmp_path)
    assert by_form(result)["Bloom Salicylic Cleanser"] == (
        "a rinse-off cleanser: ask for a salicylic acid cleanser to see these")
    assert "Bloom Salicylic Cleanser" not in left_out(result)  # it does contain the acid
    rinse = [item for item in result.left_out_by_form if item.rinse_off]
    assert {item.name for item in rinse} == {"Bloom Salicylic Cleanser", "Echo Salicylic Peel"}


def test_a_product_whose_form_isnt_known_is_left_out(tmp_path):
    # "Gilt Salicylic Acid", typed as an exfoliant: a leave-on liquid or a rinse-off scrub? Never a guess.
    result = ask(tmp_path)
    assert by_form(result)["Gilt Salicylic Acid"] == "we couldn't confirm it's a leave-on form"
    assert not next(item for item in result.left_out_by_form if item.name == "Gilt Salicylic Acid").rinse_off


def test_a_request_naming_a_form_gets_that_form_rinse_off_or_not(tmp_path):
    wash = ask(tmp_path, "salicylic acid wash")
    assert wash.query.ingredient_led and wash.query.constraints.forms == ["cleanser"]
    assert picks(wash) == [("Bloom Salicylic Cleanser", "cleanser")]
    assert by_form(wash)["Acme 2% Salicylic Acid Serum"] == "not the form you asked for (cleanser)"


def test_a_product_with_no_evidence_of_the_ingredient_is_left_out_and_named(tmp_path):
    result = ask(tmp_path)
    reasons = left_out(result)
    assert reasons["Corra Glow Powder"] == "we couldn't confirm it contains salicylic acid"
    assert reasons["Fern Gentle Cleanser"] == "we couldn't confirm it contains salicylic acid"
    # A BHA in a name isn't proof of salicylic acid.
    assert reasons["Dune BHA Liquid"] == "we couldn't confirm it contains salicylic acid"


def test_a_formula_from_the_makers_page_is_evidence_and_gives_the_form(tmp_path):
    # Changed on purpose 13 Oct 2026 (Noemi's decision 1): a rinse-off powder shows when the request names a powder.
    powder = [facts("Corra Glow Powder", "exfoliant", ["salicylic acid", "papain"], "rinse-off powder")]
    result = ask(tmp_path, product_facts=powder)
    assert "Corra Glow Powder" not in left_out(result)  # the formula is evidence of the acid
    assert by_form(result)["Corra Glow Powder"] == "a rinse-off powder: ask for a salicylic acid powder to see these"
    asked = ask(tmp_path / "powder", "salicylic acid powder", product_facts=powder)
    assert picks(asked) == [("Corra Glow Powder", "rinse-off powder")]


def test_a_formula_without_the_ingredient_leaves_the_product_out_whatever_its_name(tmp_path):
    result = ask(tmp_path, product_facts=[facts("Dune BHA Liquid", "exfoliant", ["betaine salicylate"])])
    assert left_out(result)["Dune BHA Liquid"] == "its maker doesn't list salicylic acid among its actives"
    bha = ask(tmp_path / "bha", "a bha for blackheads",
              product_facts=[facts("Dune BHA Liquid", "exfoliant", ["betaine salicylate"])])
    assert ("Dune BHA Liquid", "leave-on liquid") in picks(bha)  # betaine salicylate is a BHA


def test_also_worth_a_look_and_the_skip_list_hold_the_ingredient_too(tmp_path):
    # Changed on purpose 13 Oct 2026 (Noemi's decision 1): the peel on the skip list is rinse-off, so a leave-on gel
    # was added to hold its place.
    result = ask(tmp_path)
    assert [(item.name, item.form) for item in result.answer.worth_a_look] == [("Iris Salicylic Toner", "toner")]
    assert [(item.name, item.form) for item in result.answer.skip] == [("Opal Salicylic Gel", "gel")]
    assert {"Jade Mist", "Haze Scrub"} <= set(left_out(result))
    assert "Echo Salicylic Peel" in by_form(result)


def test_threads_that_never_name_the_ingredient_are_not_read(tmp_path):
    result = ask(tmp_path)
    assert set(result.threads_used) == {"1sali01", "1sali02"}
    assert "Gale Cream" not in [p.name for p in result.ranking.products]


def test_the_answer_says_the_ingredient_and_each_products_form(tmp_path):
    result = ask(tmp_path)
    assert result.answer.ingredient == "salicylic acid"
    text = render_markdown(result.answer)
    assert text.startswith("# Top picks: salicylic acid products\n")
    # Changed on purpose 13 Oct 2026 (Noemi's decision 1): no cleanser now; the note says how to see rinse-off forms.
    assert "**Form:** serum" in text and "**Form:** patch" in text and "**Form:** cleanser" not in text
    assert result.answer.ingredient_note.startswith("Every product here contains salicylic acid")
    assert '"salicylic acid cleanser"' in result.answer.ingredient_note


def test_a_type_named_with_the_ingredient_keeps_its_type(tmp_path):
    result = ask(tmp_path, "salicylic acid cleanser")
    assert [pick.name for pick in result.answer.picks] == ["Bloom Salicylic Cleanser"]
    assert "Acme 2% Salicylic Acid Serum" in result.left_out_as_other_type  # a serum isn't a cleanser
    assert "Fern Gentle Cleanser" in left_out(result)  # a cleanser, but no evidence of the acid
    assert all(pick.form is None for pick in result.answer.picks)  # every pick is a cleanser: no form shown
    assert render_markdown(result.answer).startswith("# Top picks: cleanser with salicylic acid\n")


def test_a_request_without_an_ingredient_is_unchanged(tmp_path):
    result = ask(tmp_path, "cleanser for acne")
    assert [pick.name for pick in result.answer.picks] == ["Bloom Salicylic Cleanser", "Fern Gentle Cleanser"]
    assert result.left_out_no_ingredient == [] and result.answer.ingredient is None


def test_the_page_gets_the_ingredient_and_how_many_were_left_out(tmp_path):
    result = ask(tmp_path)
    data = web.answer_json(result)
    assert data["answer"]["ingredient"] == "salicylic acid"
    # Changed on purpose 13 Oct 2026 (Noemi's decision 1): leave-on forms only, and the forms left out are counted.
    assert sorted(pick["form"] for pick in data["answer"]["picks"]) == ["patch", "serum"]
    assert data["left_out"]["no_ingredient"] == len(result.left_out_no_ingredient) > 0
    assert data["left_out"]["by_form"] == len(result.left_out_by_form) == 3  # the cleanser, the peel, Gilt
    assert data["left_out"]["rinse_off"] == 2
    assert data["query"]["forms"] == []
    assert data["query"]["ingredients"] == ["salicylic acid"] and data["query"]["ingredient_led"] is True


# --- What to look for in an answer naming an ingredient ---

def test_the_ingredient_asked_for_is_no_advice_and_advice_must_be_about_it():
    from engine.tests.test_answer_sense import look_for
    from engine.tests.ranking_factories import note

    notes = [note("BHA", "t1", quote="A BHA is the one thing that cleared my pores.", weight=0.9),
             note("AHA", "t2", quote="An AHA works great for dull skin, love it.", weight=0.8),
             note("leave-on BHA", "t1", quote="A leave-on BHA works better than a salicylic wash for me.", weight=0.5),
             note("humidifier", "t2", quote="A humidifier at night is great.", weight=0.7)]
    # Ingredient-led: "BHA" is what was asked for, an AHA or a humidifier isn't advice about salicylic acid.
    assert [kind for _, kind, _ in look_for(notes, "salicylic acid product", REQUEST)] == ["leave-on BHA"]
    # A type with the ingredient: "BHA" is still what was asked for.
    kinds = [kind for _, kind, _ in look_for(notes, "cleanser", "salicylic acid cleanser")]
    assert "BHA" not in kinds


# --- A type named with an ingredient ---

LUMO = ("Lumo Glycolic Acid Toner", "exfoliant")  # the AI types acid toners as exfoliants
MIST = ("Mira Rose Toner", "toner")


def toner_library(tmp_path: Path) -> Path:
    return write_library(tmp_path, {
        "1tone01": ("Which toner do you love?", [praise("l1", LUMO, 2), praise("l2", LUMO, 3), praise("m1", MIST, 2),
                                                 praise("m2", MIST, 3)]),
        # Its title and post name glycolic acid, never a toner: read for a glycolic acid toner all the same.
        "1tone02": ("Glycolic acid: worth it?", [praise("l3", LUMO, 4), praise("m3", MIST, 4)]),
    })


def test_a_product_named_as_the_type_asked_for_counts_as_it_when_the_ingredient_is_asked_for(tmp_path):
    result = answer_request("glycolic acid toner", library_dir=toner_library(tmp_path), prices=[], product_facts=[],
                            today=TODAY)
    assert [pick.name for pick in result.answer.picks] == ["Lumo Glycolic Acid Toner"]
    assert "1tone02" in result.threads_used
    assert "Mira Rose Toner" in left_out(result)


def test_without_an_ingredient_the_ais_type_still_decides(tmp_path):
    result = answer_request("toner for dry skin", library_dir=toner_library(tmp_path / "plain"), prices=[],
                            product_facts=[], today=TODAY)
    assert "Lumo Glycolic Acid Toner" in result.left_out_as_other_type


def test_a_writers_with_the_ingredient_is_no_evidence(tmp_path):
    kelp = ("Kelp Gleanser with salicylic acid", "cleanser")
    lib = write_library(tmp_path, {
        "1kelp01": ("Salicylic acid recs?", [praise("k1", kelp, 2), praise("k2", kelp, 3)]),
        "1kelp02": ("What cleared your acne?", [praise("k3", kelp, 4)]),
    })
    result = answer_request(REQUEST, library_dir=lib, prices=[], product_facts=[], today=TODAY)
    assert result.answer.picks == []
    assert left_out(result)["Kelp Gleanser with salicylic acid"] == "we couldn't confirm it contains salicylic acid"


def test_with_an_ingredient_asked_for_advice_must_be_about_it_whatever_the_type():
    from engine.tests.test_answer_sense import look_for
    from engine.tests.ranking_factories import note

    notes = [note("tret", "t1", quote="Tret is great, it changed my skin more than anything.", weight=0.9),
             note("cream formula", "t2", quote="A cream formula is great, gels sting my skin.", weight=0.8),
             note("low-percentage niacinamide", "t1", quote="Low-percentage niacinamide is great, high ones irritate.",
                  weight=0.5)]
    # "tret" is another active, "cream formula" says nothing of niacinamide: neither is advice for a niacinamide serum.
    assert [kind for _, kind, _ in look_for(notes, "serum", "niacinamide serum for oily skin")] == [
        "low-percentage niacinamide"]
    # Without an ingredient asked for, the advice stands as before.
    assert "tret" in [kind for _, kind, _ in look_for(notes, "serum", "serum for oily skin")]


def test_a_note_leaning_on_both_in_one_is_no_advice_on_its_own():
    # Found judging the ingredient answers (13 Oct 2026): a note about a kind that holds "both in one" leans on the two
    # things the asker wanted, which the answer doesn't show.
    from engine.answer import _stands_alone

    assert not _stands_alone("Nothing puts both in one tube; a leave-on BHA is the nearest thing.", names_it=True)
    assert _stands_alone("A leave-on BHA works better than a wash for me.", names_it=True)


def test_a_spot_treatment_request_gets_spot_treatments(tmp_path):
    # Noemi's decision 2 of 13 Oct 2026: spot treatments and pimple patches are a type of their own.
    result = ask(tmp_path, "salicylic acid spot treatment")
    assert [pick.name for pick in result.answer.picks] == ["Kiri Salicylic Pimple Patch"]
    assert "Acme 2% Salicylic Acid Serum" in result.left_out_as_other_type


def test_advice_in_an_ingredient_led_answer_keeps_to_its_forms():
    # Noemi's decision 1 of 13 Oct 2026: an answer of leave-on products gives no advice to look for a rinse-off form,
    # and an answer to "salicylic acid wash" none to look for a toner.
    from engine.answer import write_answer
    from engine.rank import rank_products
    from engine.tests.ranking_factories import bodies_for, mentions, note

    notes = [note("BHA cleanser", "t1", quote="A BHA cleanser is great, it keeps my pores clear.", weight=0.9),
             note("BHA toner", "t2", quote="A BHA toner is great every other night.", weight=0.8),
             note("leave-on BHA", "t1", quote="A leave-on BHA is great, it works better than any wash.", weight=0.5)]
    items = mentions(3, "Acme thing", category="skincare")
    ranking = rank_products(items, "skincare", notes, {})

    def kinds(request: str, forms_asked=()) -> list[str]:
        answer = write_answer(ranking, bodies_for(*items, *notes), "salicylic acid product", request=request,
                              ingredient="salicylic acid", forms_asked=forms_asked)
        return [item.kind for item in answer.look_for]

    assert kinds(REQUEST) == ["BHA toner", "leave-on BHA"]
    assert kinds("salicylic acid wash", ["cleanser"]) == ["BHA cleanser", "leave-on BHA"]
