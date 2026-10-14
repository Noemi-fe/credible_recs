"""Name levels (decided by Claude, 14 Oct 2026, as the orchestrator asked; reported to Noemi): module 4 and the ranking
treat a brand, a line and a specific product the same way in every answer.

Found when the library grew from 590 to about 1,100 extracted threads: b08 ("cast iron skillet for a beginner that will
last decades") lost its Lodge pick because a writer's "lodge cast iron pan" (the brand and the type's words) was taken
for a specific Lodge product, and the Lodge line stepped aside for it. The rules below, each with made-up products:

1. A name made of a brand and only the requested type's words or their synonyms ("Ferrow cast iron pan" in a cast iron
   skillet answer, "Kestrel kettle" in a kettle answer, "Zipzit patches" for a spot treatment) is the brand's line,
   never a specific product: grouping makes it the line, and a brand line never steps aside for it.
2. A product of another type never makes a name fit two products, and a name never joins one: "Aveline" in an
   exfoliant answer is the Aveline Soft Peel even when its Glow Serum is named too.
3. A brand's mentions the AI typed as another type of product never count for the requested type, even when their
   quote says a word of it inside the other type's own name ("cast iron dutch oven"), and they never decide a brand
   line's type: its mentions of the requested type still count, as that line.
4. A model's other versions ("ESP", "Forte") are other products, and a name the facts list knows as one product is
   never a line, whatever descriptions writers add to it; two products the facts list knows apart are never joined.

Every library, product, writer and quote here is made up; no test reads data/.
"""

import json
from datetime import date
from pathlib import Path

from engine import pipeline
from engine.answer import PRESCRIPTION_NOTE, unverified_claims
from engine.group_products import ProductGroup, ProductMention, group_products
from engine.match_products import same_product
from engine.pipeline import FoldedBrandPick, answer_request
from engine.product_facts import Formula, ProductFacts
from engine.rank import rank_products
from engine.tests.factories import make_comment, make_thread, write_gold
from engine.tests.ranking_factories import mentions as scored

TODAY = date(2026, 10, 9)
NO_ALIASES = {"skincare": {}, "kitchen": {}, "haircare": {}, "general": {}, "other": {}}


def typed(product: str, product_type: str | None, comment_id: str, category: str = "kitchen",
          thread_id: str = "1fake01") -> ProductMention:
    return ProductMention(thread_id, comment_id, product, category, "recommend", product_type=product_type)


def names_by_group(groups) -> list[list[str]]:
    return sorted((sorted({m.product for m in g.mentions}) for g in groups), key=lambda names: names[0])


def loose_names(groups) -> list[list[str]]:
    return sorted(sorted({m.product for m in g.mentions}) for g in groups if g.loose)


# --- 1. A brand and the type's words or synonyms is the brand's line ---

def test_a_brand_and_a_synonym_of_the_type_is_the_brands_line():
    # The b08 case: writers call a cast iron skillet a "cast iron pan". "Ferrow cast iron pan" says no more than Ferrow in
    # a cast iron skillet answer, so it is Ferrow's line with "Ferrow" written alone, not a product of its own.
    mentions = [typed(n, "cast iron skillet", f"c{i}") for i, n in enumerate(
        ["Ferrow", "Ferrow", "Ferrow cast iron pan", "Ferrow cast iron pan", "Ferrow cast iron frying pans",
         "Ferrow No. 8 skillet", "Ferrow No. 10 skillet"])]
    groups = group_products(mentions, NO_ALIASES, product_type="cast iron skillet")
    assert loose_names(groups) == [["Ferrow", "Ferrow cast iron frying pans", "Ferrow cast iron pan"]]
    assert ["Ferrow No. 8 skillet"] in names_by_group(groups) and ["Ferrow No. 10 skillet"] in names_by_group(groups)


def test_a_brand_and_the_types_words_is_a_line_when_the_brand_starts_two_products_here():
    # "Marlow pan", with "Marlow" never written alone, names Marlow's pans: the brand starts two products' names here.
    # Only a brand of one word: "Cetaphil gentle cleanser" next to two Cetaphil Gentle cleansers is the Gentle Skin
    # Cleanser by the 10 Oct rule (UNTELLING_WORDS), and "CeraVe SA cleanser" may be the SA range's one cleanser.
    mentions = [typed(n, "frying pan", f"c{i}") for i, n in enumerate(
        ["Marlow pan", "Marlow Titan cookware", "Marlow Titan cookware", "Marlow Titan Always Pan Pro"])]
    groups = group_products(mentions, NO_ALIASES, product_type="frying pan")
    assert loose_names(groups) == [["Marlow pan"]]
    assert names_by_group(groups) == [["Marlow Titan Always Pan Pro"], ["Marlow Titan cookware"], ["Marlow pan"]]


def test_a_brand_and_the_types_patches_is_its_line_in_an_ingredient_led_answer():
    # An ingredient-led request has no one type to group by ("salicylic acid for acne"): the type the AI gave the name
    # tells which words say no more than its brand. "Zipzit patches" had joined Zipzit's Dart Kit, though Zipzit makes
    # other patches.
    mentions = [typed(n, t, f"c{i}", "skincare") for i, (n, t) in enumerate([
        ("Zipzit", "spot treatment"), ("Zipzit patches", "spot treatment"), ("Zipzit patches", "pimple patch"),
        ("Zipzit Dart Kit Microdart Patches", "spot treatment"), ("Zipzit Dart Kit Microdart Patches", "spot treatment")])]
    groups = group_products(mentions, NO_ALIASES)
    dart = next(g for g in groups if "Zipzit Dart Kit Microdart Patches" in g.names)
    assert set(dart.names) == {"Zipzit Dart Kit Microdart Patches"} and not dart.loose
    assert ["Zipzit", "Zipzit patches"] in loose_names(groups)


def test_a_line_never_steps_aside_for_its_brand_written_with_the_types_words():
    # Grouping makes such a name the line; should a name still reach the ranking as a product of its own (here built by
    # hand), the brand line doesn't step aside for it: they are one line, so the one ranked lower folds into the other.
    def made_up_group(name: str, loose: bool) -> ProductGroup:
        return ProductGroup(f"kitchen:{name.lower()}", name, "kitchen",
                            [ProductMention("t1", f"c-{name}", name, "kitchen", "recommend")], loose)

    line, plain, other = made_up_group("Ferrow", True), made_up_group("Ferrow cast iron pan", False), \
        made_up_group("Smithson No. 10 skillet", False)
    ranking = rank_products(scored(6, "Ferrow cast iron skillet line", key=line.key)
                            + scored(4, "Smithson No. 10 skillet", key=other.key)
                            + scored(3, "Ferrow cast iron pan", key=plain.key), "kitchen")
    result = pipeline.PipelineResult(query=None)
    folded = pipeline._fold_brand_picks(ranking, [line, plain, other], result, "cast iron skillet")
    assert [p.name for p in folded.qualifying] == ["Ferrow cast iron skillet line", "Smithson No. 10 skillet"]
    assert result.folded_brand_picks == [FoldedBrandPick("Ferrow cast iron pan", "Ferrow cast iron skillet line")]


# --- 2. Products of another type never decide what a name fits ---

def test_a_product_of_another_type_never_makes_a_brand_fit_two_products():
    # The b01 case: "Stratia" (an exfoliant) joined the Soft Touch AHA until the brand's serum was named in the same
    # threads; it then fitted two products and its vote counted for neither.
    mentions = [typed(n, t, f"c{i}", "skincare") for i, (n, t) in enumerate([
        ("Aveline", "exfoliant"), ("Aveline", "exfoliant"), ("Aveline Soft Peel", "exfoliant"),
        ("Aveline Soft Peel", "exfoliant"), ("Aveline Glow Serum", "serum")])]
    groups = group_products(mentions, NO_ALIASES, product_type="exfoliant")
    assert names_by_group(groups) == [["Aveline", "Aveline Soft Peel"], ["Aveline Glow Serum"]]
    assert not any(g.loose for g in groups)


# --- 3. A brand's mentions of another type never count for the requested type ---

def write_library(tmp_path: Path, threads: dict[str, tuple[str, list[tuple]]]) -> Path:
    """{thread id: (title, [(comment id, product, the AI's type, text, stance)])}, in r/castiron; each comment's text is
    also its quote."""
    saved, extractions = [], {}
    for thread_id, (title, rows) in threads.items():
        url = f"https://www.reddit.com/r/castiron/comments/{thread_id}/thread/"
        comments = [make_comment(cid, thread_id=thread_id, body=text,
                                 url=f"https://www.reddit.com/r/castiron/comments/{thread_id}/comment/{cid}/")
                    for cid, _, _, text, _ in rows]
        saved.append(make_thread(id=thread_id, community="castiron", category="kitchen", title=title,
                                 body="My first one.", url=url, comments=comments))
        extractions[thread_id] = [{"comment_id": cid, "product": product, "category": "kitchen", "stance": stance,
                                   "quote": text, "product_type": product_type}
                                  for cid, product, product_type, text, stance in rows]
    root = write_gold(tmp_path / "library", saved, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for thread_id, mentions in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v6", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions,
        }), encoding="utf-8")
    return root


def skillet(cid: str, product: str, years: int) -> tuple:
    text = f"I have cooked on my {product} for {years} years, the best skillet I own."
    return cid, product, "cast iron skillet", text, "recommend"


def oven(cid: str, product: str, years: int) -> tuple:
    text = f"My {product} enameled cast iron dutch oven has lasted {years} years of stews."
    return cid, product, "dutch oven", text, "recommend"


def corbel_library(tmp_path: Path) -> Path:
    """Two skillet threads. Corbel is praised four times for its Dutch ovens (quotes saying "cast iron dutch oven") and
    three times for its skillets, across both threads; the Smithson and the Pellam skillets three times each."""
    return write_library(tmp_path, {
        "1corb01": ("Best cast iron skillet for a beginner?", [
            oven("o1", "Corbel", 12), oven("o2", "Corbel", 9), skillet("s1", "Corbel", 15), skillet("s2", "Corbel", 8),
            skillet("m1", "Smithson No. 10", 6), skillet("m2", "Smithson No. 10", 7),
            skillet("p1", "Pellam 12 inch", 5), skillet("p2", "Pellam 12 inch", 4),
            skillet("n1", "Corbel No. 8 skillet", 3),
        ]),
        "1corb02": ("Which cast iron skillet lasts?", [
            oven("o3", "Corbel", 11), oven("o4", "Corbel", 10), skillet("s3", "Corbel", 20),
            skillet("m3", "Smithson No. 10", 9), skillet("p3", "Pellam 12 inch", 8), skillet("n2", "Corbel No. 10 skillet", 2),
        ]),
    })


def test_a_brands_dutch_oven_mentions_never_count_in_a_skillet_answer(tmp_path):
    result = answer_request("cast iron skillet that lasts", library_dir=corbel_library(tmp_path), prices=[],
                            product_facts=[], today=TODAY)
    line = next(p for p in result.ranking.products if p.name == "Corbel cast iron skillet line")
    assert sorted(m.comment_id for m in line.mentions) == ["s1", "s2", "s3"]
    assert "Corbel" in result.mentions_of_another_type
    assert unverified_claims(result.answer, result.bodies) == []


def test_a_brand_mostly_named_for_another_type_keeps_its_mentions_of_the_requested_type(tmp_path):
    # Four Dutch oven mentions to three skillet ones: the brand's name no longer takes the type most of its mentions give,
    # so its skillet mentions still count, as its skillet line (Le Creuset's skillets had vanished from b08 so).
    result = answer_request("cast iron skillet that lasts", library_dir=corbel_library(tmp_path), prices=[],
                            product_facts=[], today=TODAY)
    assert "Corbel" not in result.left_out_as_other_type
    assert "Corbel cast iron skillet line" in [pick.name for pick in result.answer.picks]


def test_a_requested_types_word_inside_another_types_name_doesnt_name_it():
    # "cast iron" in "cast iron dutch oven" is the Dutch oven's word: it doesn't make a Dutch oven mention a skillet one.
    corbel = ProductMention("t1", "c1", "Corbel", "kitchen", "recommend", product_type="dutch oven",
                            quote="My Corbel enameled cast iron dutch oven has lasted years.")
    assert pipeline._mention_of_another_type(corbel, "cast iron skillet")
    # The writer's own words still win when they name the requested type apart (13 Oct 2026).
    said = ProductMention("t1", "c2", "Corbel", "kitchen", "recommend", product_type="dutch oven",
                          quote="My Corbel cast iron skillet sits next to the dutch oven.")
    assert not pipeline._mention_of_another_type(said, "cast iron skillet")


# --- 4. Models' versions, and what the facts list knows ---

def test_a_models_esp_and_forte_versions_are_other_products():
    assert not same_product("Baratza Encore", "Baratza Encore ESP")
    assert not same_product("Epiduo", "Epiduo Forte")
    assert same_product("Baratza Encore", "Baratza Encore with M2 burr")


def test_a_name_the_facts_list_knows_as_one_product_is_never_a_line():
    # The b02 case: writers added a bottle's colours and the SPF rating to the full name of one sunscreen, and the full
    # name then fitted "two products", so it was shown as a line.
    names = ["Solenne Perfect UV Milk", "Solenne Perfect UV Milk", "Solenne Perfect UV Milk",
             "Solenne Perfect UV Milk SPF50+ PA++++", "Solenne Perfect UV Milk gold bottle with blue cap"]
    mentions = [typed(n, "sunscreen", f"c{i}", "skincare") for i, n in enumerate(names)]
    known = {"skincare": [("solenne", "perfect", "uv", "milk")]}
    groups = group_products(mentions, NO_ALIASES, product_type="sunscreen", known=known)
    assert len(groups) == 1 and not groups[0].loose
    assert any(g.loose for g in group_products(mentions, NO_ALIASES, product_type="sunscreen"))  # without it, a line


def test_two_products_the_facts_list_knows_apart_are_never_joined():
    mentions = [typed(n, "serum", f"c{i}", "skincare") for i, n in enumerate(
        ["Kelso Centella Ampoule", "Kelso Centella Ampoule", "Kelso Centella Tone Brightening Ampoule"])]
    known = {"skincare": [("kelso", "centella", "ampoule"), ("kelso", "centella", "tone", "brightening", "ampoule")]}
    assert len(group_products(mentions, NO_ALIASES, product_type="serum", known=known)) == 2
    assert len(group_products(mentions, NO_ALIASES, product_type="serum")) == 1  # without the list, one product


def test_the_facts_lists_own_names_of_products_are_known_but_a_brands_entry_is_not():
    entries = [ProductFacts(product=name, category=category, product_type=product_type, facts=facts,
                            sources=["https://facts.example/page"], checked_on=TODAY)
               for name, category, product_type, facts in [
                   ("Solenne Perfect UV Milk", "skincare", "sunscreen", {"fragrance_free": False}),
                   ("Glenpan", "kitchen", "frying pan", {"pfas_free": True}),
                   ("Darrow pans", "kitchen", "frying pan", {"pfas_free": False}),
                   ("Darrow Titan 28cm frying pan", "kitchen", "frying pan", {"pfas_free": True})]]
    known = pipeline._known_products(entries)
    assert known["skincare"] == [("solenne", "perfect", "uv", "milk")]
    assert known["kitchen"] == [("darrow", "titan", "28cm", "frying", "pan")]


# --- Side item: a retinoid whose facts confirm benzoyl peroxide counts for a benzoyl peroxide request ---

def bpo_library(tmp_path: Path) -> Path:
    def rows(thread: str) -> list[tuple]:
        text = "I used the {} for {} months and my acne cleared up for good."
        return [(f"{thread}{p[:2]}{i}", p, t, text.format(p, 4 + i), "recommend")
                for p, t in (("Duolexa gel", "retinoid"), ("Retinolux serum", "retinoid"), ("Pyrox 5% gel", "spot treatment"))
                for i in range(2)]
    saved, extractions = [], {}
    for thread_id, title in (("1bpo001", "Benzoyl peroxide for acne?"), ("1bpo002", "What cleared your acne?")):
        thread_rows = rows(thread_id[-1])
        url = f"https://www.reddit.com/r/acne/comments/{thread_id}/thread/"
        comments = [make_comment(cid, thread_id=thread_id, body=text,
                                 url=f"https://www.reddit.com/r/acne/comments/{thread_id}/comment/{cid}/")
                    for cid, _, _, text, _ in thread_rows]
        saved.append(make_thread(id=thread_id, community="acne", title=title, body="Benzoyl peroxide or adapalene?",
                                 url=url, comments=comments))
        extractions[thread_id] = [{"comment_id": cid, "product": p, "category": "skincare", "stance": s, "quote": text,
                                   "product_type": t} for cid, p, t, text, s in thread_rows]
    root = write_gold(tmp_path / "library", saved, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for thread_id, mentions in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v6", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions}), encoding="utf-8")
    return root


def bpo_facts() -> list[ProductFacts]:
    def entry(product: str, product_type: str, actives: list[str], prescription: bool) -> ProductFacts:
        return ProductFacts(product=product, category="skincare", product_type=product_type,
                            facts={"prescription_only": prescription}, sources=["https://facts.example/page"],
                            checked_on=TODAY, formula=Formula(actives=actives, form="gel",
                                                              sources=["https://facts.example/formula"],
                                                              checked_on=TODAY))
    return [entry("Duolexa gel", "retinoid", ["adapalene", "benzoyl peroxide"], True),
            entry("Retinolux serum", "retinoid", ["retinol"], False),
            entry("Pyrox 5% gel", "spot treatment", ["benzoyl peroxide"], False)]


def test_a_retinoid_whose_facts_confirm_benzoyl_peroxide_counts_for_a_benzoyl_peroxide_request(tmp_path):
    lib = bpo_library(tmp_path)
    result = answer_request("benzoyl peroxide for acne", library_dir=lib, prices=[], product_facts=bpo_facts(),
                            today=TODAY)
    picks = {pick.name: pick for pick in result.answer.picks}
    assert set(picks) == {"Duolexa gel", "Pyrox 5% gel"}
    assert picks["Duolexa gel"].prescription == PRESCRIPTION_NOTE
    # A retinoid whose formula lacks benzoyl peroxide stays out, said why.
    assert {item.name: item.reason for item in result.left_out_no_ingredient}["Retinolux serum"] == (
        "its maker doesn't list benzoyl peroxide among its actives")
    # Prescription-only, so out of a request for sensitive skin, as the rules say (Noemi's decision 5 of 14 Oct 2026).
    gentle = answer_request("benzoyl peroxide for sensitive skin", library_dir=lib, prices=[],
                            product_facts=bpo_facts(), today=TODAY)
    assert "Duolexa gel" not in [pick.name for pick in gentle.answer.picks]


def test_a_lines_name_with_the_type_is_still_its_one_product_by_the_untelling_rule():
    # Found by the name-levels sweep: "cetaphil gentle" starts two Cetaphil Gentle cleansers, but it is no brand: its name
    # with the type stays the Gentle Skin Cleanser (10 Oct 2026, UNTELLING_WORDS), as before.
    mentions = [typed(n, "cleanser", f"c{i}", "skincare") for i, n in enumerate(
        ["cetaphil gentle cleanser", "Cetaphil Gentle Skin Cleanser", "Cetaphil Gentle Skin Cleanser",
         "Cetaphil Gentle Foaming Cleanser"])]
    groups = group_products(mentions, NO_ALIASES, product_type="cleanser")
    assert ["Cetaphil Gentle Skin Cleanser", "cetaphil gentle cleanser"] in names_by_group(groups)
    assert not any(g.loose for g in groups)


def test_a_brand_fitting_only_products_of_other_types_is_still_its_line():
    # Found by the name-levels sweep: "Nizoral" next to two Nizoral products of other types was its line before, and must
    # stay one, not become a product of its own because the others aren't shampoos.
    mentions = [typed(n, t, f"c{i}", "haircare") for i, (n, t) in enumerate([
        ("Nizoral", "shampoo"), ("Nizoral", "shampoo"), ("Nizoral Scalp Serum", "hair oil"),
        ("Nizoral Daily Conditioner", "conditioner")])]
    groups = group_products(mentions, NO_ALIASES, product_type="shampoo")
    assert ["Nizoral"] in loose_names(groups) and len(groups) == 3


def test_a_brand_and_the_types_words_with_its_products_of_other_types_is_its_line():
    # "Nizoral" and "Nizoral shampoo", with no other Nizoral shampoo named but a Nizoral conditioner: a brand with a range,
    # so its line, as it was before products of other types were set apart. With no other product of the brand named at
    # all, the brand and its name with the type are still one product, as a brand alone joins its one product.
    mentions = [typed(n, t, f"c{i}", "haircare") for i, (n, t) in enumerate([
        ("Nizoral", "shampoo"), ("Nizoral", "shampoo"), ("Nizoral shampoo", "shampoo"),
        ("Nizoral conditioner", "conditioner")])]
    groups = group_products(mentions, NO_ALIASES, product_type="shampoo")
    assert ["Nizoral", "Nizoral shampoo"] in loose_names(groups)
    alone = [m for m in mentions if m.product != "Nizoral conditioner"]
    groups = group_products(alone, NO_ALIASES, product_type="shampoo")
    assert len(groups) == 1 and not groups[0].loose


def test_a_name_the_facts_list_knows_still_fits_other_products_named_otherwise():
    # Found by the name-levels sweep: "Kelso bean cleanser", a facts entry, next to three other Kelso bean products named
    # in other words, had joined all of them (an oil cleanser, a foam and a balm) once it could never be a line: only
    # names that add words after its own are it.
    mentions = [typed(n, "cleanser", f"c{i}", "skincare") for i, n in enumerate(
        ["Kelso bean cleanser", "Kelso bean cleanser", "Kelso bean greenful oil cleanser", "Kelso low ph bean cleanser",
         "Kelso bean pore cleansing milk balm"])]
    known = {"skincare": [("kelso", "bean", "cleanser")]}
    groups = group_products(mentions, NO_ALIASES, product_type="cleanser", known=known)
    assert ["Kelso bean cleanser"] in loose_names(groups) and len(groups) == 4


# --- The same rule in the first reading's thread choice (engine.sources.titled_as_another_type) ---

def test_a_title_naming_the_requested_types_word_inside_another_types_name_is_titled_as_that_type():
    # Found in b08: a thread titled about a cast iron enamel Dutch oven took a need-led first-reading place in the cast
    # iron skillet answer ("cast iron" is a skillet's word), pushing out a skillet recommendation thread.
    from engine.query import parse_query
    from engine.sources import titled_as_another_type

    skillet = parse_query("cast iron skillet for a beginner that will last decades")
    assert titled_as_another_type("Cast iron enamel dutch oven with a 3 year warranty. Worth it?", skillet)
    assert titled_as_another_type("Is this cast iron dutch oven a good price?", skillet)
    assert not titled_as_another_type("Cast iron skillet or dutch oven for a first pan?", skillet)
    assert not titled_as_another_type("Cast iron vs enamel dutch oven for searing?", skillet)
    assert not titled_as_another_type("Best cast iron skillet for a beginner?", skillet)


def test_instant_pots_short_names_are_its_name():
    # Found by the name-levels sweep: "IP" and "instapot" were picks of their own next to the Instant Pot line.
    from engine.match_products import known_aliases

    kitchen = known_aliases()["kitchen"]
    assert same_product("IP Duo", "Instant Pot Duo", kitchen)
    assert same_product("instapot", "Instant Pot", kitchen)


def test_a_brand_alone_joined_to_its_one_product_is_shown_by_the_products_name():
    # Found by the name-levels sweep: a serum answer showed "Skinceuticals" as a pick: the brand alone, written most
    # often, had joined its one serum named here, the C E Ferulic, and the group was shown under the brand's name.
    mentions = [typed(n, "serum", f"c{i}", "skincare") for i, n in enumerate(
        ["Solvane", "Solvane", "Solvane", "Solvane", "Solvane C E Ferulic", "Solvane C E Ferulic", "Solvane CE Ferulic"])]
    groups = group_products(mentions, NO_ALIASES, product_type="serum")
    assert [(g.name, g.loose) for g in groups] == [("Solvane C E Ferulic", False)]
