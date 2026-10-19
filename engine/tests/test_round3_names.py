"""Round 3, names and pan facts (19 Oct 2026, the round-3 names builder; Claude's technical calls, reported to Noemi),
from the final review of 19 Oct (docs/bfs-2026-10-17/final-review.md), the answers people will see at interviews and in
the blind test.

1. The same product twice in one answer. Writers name one product by its line and by its maker ("Aeron" and "Herman
   Miller Aeron", "iPhone" and "Apple", "Sonicare" and "Philips", "ThinkPad" and "Lenovo"), and module 4 kept them as two
   groups because the bare name fits several products and so stays loose. Joined by a known short name (engine/data/
   product_aliases.json: Aeron is the Herman Miller Aeron, ThinkPad the Lenovo ThinkPad, Philips Sonicare the Sonicare
   line) or by the brand-lines list's naming (the "iPhone" entry is now "Apple iPhone", so its line is shown as
   "Apple phone line", as Apple's is, and the two are one pick): one group or one entry in the answer.
2. Garbled names shown to a tester: "Sleep on latex latex bed" (the name an extraction typed), "Basic e-reader line" and
   "Basic in matcha green" (the basic Kindle), "$30 rice cooker" (a price, no product) and Bose's "QuietComfort Pros
   (Ultras?)" (its QuietComfort Ultra Headphones). Each is shown as its maker writes it, or, when it names no product,
   not at all (module 4: a price in front of a name, or a description alone, names no product).
3. Pan facts from the makers' own pages (read 19 Oct 2026), for the blind test's PFAS-free frying pan question (b10)
   and "non stick pan without teflon that lasts": OXO's Ceramic Professional pans are ceramic and their maker says no
   PFAS (the pick's named model; OXO's older Good Grips Non-Stick Pro pans are only "PFOA-free", so its non-stick pans
   as a whole stay unconfirmed), and Caraway's ceramic non-stick frying pan is non-stick.
4. Anessa's origin, Nalgene's insulation and Berkey's being a countertop system have no fact in the vocabulary
   (config.PRODUCT_FACT_VALUES), so nothing in the lists can record them: listed for Noemi, not built.

Every comment here is made up. The end-to-end tests read the committed lists, as test_round2_data.py does.
"""

import json
from pathlib import Path

import pytest

from engine.brand_lines import load_brand_lines
from engine.group_products import ProductMention, group_products, maker_spelling
from engine.match_products import known_aliases
from engine.pipeline import _spelling_lists
from engine.prices import find_availability, find_price, load_prices
from engine.product_facts import find_brand_facts, find_facts, load_product_facts
from engine.tests.factories import make_comment, make_thread, write_gold
from engine.tests.test_round2_data import answer


def library(tmp_path: Path, product_type: str, threads: list[tuple]) -> Path:
    """A made-up library of one product type: threads are (id, category, title, [(comment id, product, text)]), all in
    r/BuyItForLife (a community decided for the kitchen and the general categories), every comment a recommendation
    whose text is also its quote, and every mention typed as the extraction types them (module 1's product type, or a
    comment's own as a fourth item: a mattress topper in a mattress thread)."""
    made, extractions = [], {}
    for tid, category, title, comments in threads:
        url = f"https://www.reddit.com/r/BuyItForLife/comments/{tid}/t/"
        made.append(make_thread(id=tid, community="BuyItForLife", category=category, title=title, body="Any advice?",
                                url=url, comments=[make_comment(c[0], thread_id=tid, body=c[2], url=f"{url}{c[0]}/")
                                                   for c in comments]))
        extractions[tid] = [{"comment_id": c[0], "product": c[1], "category": category,
                             "product_type": c[3] if len(c) > 3 else product_type, "stance": "recommend", "quote": c[2]}
                            for c in comments]
    root = write_gold(tmp_path / "library", made, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for tid, mentions in extractions.items():
        (root / "extracted" / f"{tid}.json").write_text(json.dumps({
            "thread_id": tid, "instructions_version": "extract-v5", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions}), encoding="utf-8")
    return root


def praised(cid: str, product: str, years: int = 3, product_type: str | None = None) -> tuple:
    text = f"I've had my {product} for {years} years and I would buy it again."
    return (cid, product, text, product_type) if product_type else (cid, product, text)


def modules_four(names: list[tuple[str, int]], product_type: str, category: str = "general") -> list:
    """Module 4's groups for these names, each written the stated number of times, with the shipped alias list."""
    mentions, n = [], 0
    for name, times in names:
        for _ in range(times):
            mentions.append(ProductMention(f"t{n % 3}", f"c{n}", name, category, "recommend"))
            n += 1
    return group_products(mentions, product_type=product_type)


def group_with(groups: list, name: str):
    return next(g for g in groups if name in g.names)


def shown(result) -> list[str]:
    """Every name the answer shows: its picks, its Also worth a look and its Skip these."""
    return ([pick.name for pick in result.answer.picks] + [item.name for item in result.answer.worth_a_look]
            + [item.name for item in result.answer.skip])


# --- 1. The same product twice ---

# The names the 19 Oct sweep's groups held (product names only), with the singles that made the bare name loose.
AERON = [("Aeron", 28), ("aeron", 6), ("Aeron chair", 1), ("Aeron chairs", 1), ("Herman Miller Aeron", 14),
         ("Aeron 2", 1), ("aeron remastered", 1), ("aeron size B", 1), ("Amia", 5), ("Herman Miller Mirra 2", 3)]
SONICARE = [("Sonicare", 45), ("sonicare", 31), ("Sonicares", 3), ("Phillips Sonicare", 32), ("Phillips sonicare", 8),
            ("Philips Sonicare", 6), ("Philips", 3), ("Phillips", 2), ("Sonicare 4100", 4), ("Philips Sonicare 6100", 1),
            ("Sonicare 6100", 1), ("Philips DiamondClean", 8), ("basic Sonicare", 3), ("Oral-B", 30)]
THINKPAD = [("Thinkpad", 27), ("ThinkPad", 22), ("Thinkpads", 6), ("Lenovo", 23), ("Lenovo laptop", 1),
            ("Lenovo ThinkPad", 4), ("Lenovo Thinkpad", 3), ("Thinkpad E14", 5), ("lenovo thinkpad e14 gen 7", 2),
            ("ThinkPad P series", 5), ("ThinkPad T14", 3), ("Lenovo Yoga", 3), ("MacBook Air", 8)]


@pytest.mark.parametrize("names, product_type, bare, full", [
    (AERON, "office chair", "Aeron", "Herman Miller Aeron"),
    (SONICARE, "electric toothbrush", "Sonicare", "Phillips Sonicare"),
    (THINKPAD, "laptop", "Thinkpad", "Lenovo ThinkPad"),
])
def test_a_product_named_by_its_line_and_by_its_maker_is_one_group(names, product_type, bare, full):
    groups = modules_four(names, product_type)
    assert group_with(groups, bare) is group_with(groups, full)


def test_the_aeron_with_its_sizes_and_versions_is_one_product_not_a_line():
    # "remastered", a size and a second chair are the same chair: the group stays one product, with its page and price.
    groups = modules_four(AERON, "office chair")
    aeron = group_with(groups, "Herman Miller Aeron")
    assert not aeron.loose and len(aeron.mentions) >= 50
    assert {"Aeron", "aeron remastered", "aeron size B", "Aeron 2"} <= set(aeron.names)


def test_oral_b_written_with_its_maker_is_oral_bs_line_not_a_product_of_its_own():
    # "Oral B Braun" had been a product the Oral-B line stepped aside for (the freed third place of the toothbrush answer
    # went to it, and the line's 60 voices were replaced by its 7): Braun is Oral-B's maker, not a model.
    names = [("Oral B", 28), ("oral b", 15), ("Oral-B", 14), ("OralB", 8), ("Oral B Braun", 1), ("oral b /braun", 1),
             ("oral B braun", 1), ("Braun", 2), ("Braun electric toothbrush", 1), ("Oral B IO", 2), ("Oral B Vitality", 2),
             ("Sonicare", 45), ("Philips DiamondClean", 8)]
    groups = modules_four(names, "electric toothbrush")
    assert group_with(groups, "Oral B Braun") is group_with(groups, "Oral B")
    assert group_with(groups, "Braun") is not group_with(groups, "Oral B")  # a bare Braun is Braun's razors and blenders too


def test_a_sonicare_is_still_not_the_whole_of_philips():
    # Philips is the maker of other toothbrushes too (writers' bare "Philips"): only Sonicare is written out in full.
    groups = modules_four(SONICARE, "electric toothbrush")
    assert group_with(groups, "Sonicare") is not group_with(groups, "Philips")
    assert group_with(groups, "Sonicare 4100") is not group_with(groups, "Sonicare")  # a model of the line, not the line


def test_the_short_names_stay_a_start_of_a_name_only():
    aliases = known_aliases()["general"]
    from engine.match_products import product_words

    assert product_words("Aeron chair", aliases) == ["herman", "miller", "aeron", "chair"]
    assert product_words("Herman Miller Aeron", aliases) == ["herman", "miller", "aeron"]  # already says it
    assert product_words("Lenovo ThinkPad T14", aliases) == ["lenovo", "thinkpad", "t14"]
    assert product_words("Philips Sonicare 6100", aliases) == ["sonicare", "6100"]  # Sonicare is the line's name
    # In the middle of a name they are left alone (a word of another name, not the line).
    assert product_words("Cosmic Aeron", aliases) == ["cosmic", "aeron"]
    assert product_words("basic Whirlpool", aliases) == ["basic", "whirlpool"]
    assert product_words("basic Sonicare", aliases) == ["sonicare"]  # the basic Sonicare is the line


def chairs(tmp_path):
    return library(tmp_path, "office chair", [
        ("1ch0001", "general", "Best office chair for back pain?", [
            praised("a1", "Aeron"), praised("a2", "Aeron chair"), praised("a3", "Herman Miller Aeron"),
            praised("a4", "Herman Miller Aeron"), praised("a5", "Amia"), praised("a6", "Amia"),
            praised("a7", "Steelcase Leap"), praised("a8", "Steelcase Leap")]),
        ("1ch0002", "general", "Which office chair is worth the money?", [
            praised("b1", "Aeron"), praised("b2", "aeron"), praised("b3", "Herman Miller Aeron"),
            praised("b4", "aeron remastered"), praised("b5", "Amia"), praised("b6", "Amia"),
            praised("b7", "Steelcase Leap"), praised("b8", "Steelcase Leap")]),
        ("1ch0003", "general", "Office chair for long days at a desk", [
            praised("c1", "Aeron"), praised("c2", "Herman Miller Aeron"), praised("c3", "aeron size B")]),
    ])


def test_an_office_chair_answer_shows_the_aeron_once(tmp_path):
    names = shown(answer("office chair for back pain", chairs(tmp_path)))
    assert len([n for n in names if "aeron" in n.lower()]) == 1, names
    assert not any(n == "Aeron office chair line" for n in names)


def phones(tmp_path):
    return library(tmp_path, "phone", [
        ("1ph0001", "general", "Which phone has the best camera?", [
            praised("a1", "iPhone"), praised("a2", "iPhones"), praised("a3", "iPhone"), praised("a4", "iPhone 13 mini"),
            praised("a5", "Apple"), praised("a6", "Apple iPhone"), praised("a7", "Apple iPhone 8"),
            praised("a8", "Apple iPhone 7"), praised("a9", "iPhone 16 pro"), praised("a10", "iPhone X"),
            praised("a11", "iPhone SE"), praised("a12", "Pixel"), praised("a13", "Pixel 8"),
            praised("a14", "Samsung"), praised("a15", "Samsung Galaxy S24")]),
        ("1ph0002", "general", "A phone with a good camera, what do you use?", [
            praised("b1", "iPhone"), praised("b2", "iphone"), praised("b3", "iPhone"), praised("b4", "iPhone 12 mini"),
            praised("b5", "Apple"), praised("b6", "Apple iPhone"), praised("b7", "Apple iPhone 8"),
            praised("b8", "Apple iPhone 7"), praised("b9", "iphone 16 pro"), praised("b10", "iPhone X"),
            praised("b11", "iPhone SE"), praised("b12", "Apple"), praised("b13", "Pixel"), praised("b14", "Pixel 8"),
            praised("b15", "Samsung"), praised("b16", "Samsung Galaxy S24")]),
    ])


def test_a_phone_answer_shows_apples_phones_once(tmp_path):
    names = shown(answer("a phone with a good camera", phones(tmp_path)))
    assert len([n for n in names if "iphone" in n.lower() or "apple" in n.lower()]) == 1, names
    assert "iPhone phone line" not in names


def toothbrushes(tmp_path):
    return library(tmp_path, "electric toothbrush", [
        ("1tb0001", "general", "Which electric toothbrush lasts?", [
            praised("a1", "Sonicare", 8), praised("a2", "Sonicare", 6), praised("a3", "Philips Sonicare", 7),
            praised("a4", "Phillips Sonicare", 9), praised("a5", "Philips", 5), praised("a6", "Sonicare 4100", 4),
            praised("a7", "Philips Sonicare 6100", 3), praised("a8", "Oral-B", 5), praised("a9", "Oral-B", 6),
            praised("a10", "Oral-B", 4)]),
        ("1tb0002", "general", "Electric toothbrush recommendations", [
            praised("b1", "Sonicare", 10), praised("b2", "Sonicare", 12), praised("b3", "Phillips Sonicare", 6),
            praised("b4", "Philips Sonicare", 5), praised("b5", "Philips", 7), praised("b6", "Sonicare 6100", 4),
            praised("b7", "Philips Sonicare 4100", 5), praised("b8", "Oral-B", 8), praised("b9", "Oral-B", 9),
            praised("b10", "Oral-B", 7)]),
    ])


def test_an_electric_toothbrush_answer_shows_sonicare_and_philips_once(tmp_path):
    names = shown(answer("electric toothbrush", toothbrushes(tmp_path)))
    assert len([n for n in names if "sonicare" in n.lower() or "philips" in n.lower()]) == 1, names


def laptops(tmp_path):
    return library(tmp_path, "laptop", [
        ("1lp0001", "general", "Which laptop for university?", [
            praised("a1", "ThinkPad"), praised("a2", "Thinkpad"), praised("a3", "Lenovo ThinkPad"),
            praised("a4", "Lenovo"), praised("a5", "Lenovo"), praised("a6", "ThinkPad T14"),
            praised("a7", "Lenovo ThinkPad E14 Gen 7"), praised("a8", "MacBook Air"), praised("a9", "MacBook Air"),
            praised("a10", "MacBook Air"), praised("a11", "Dell XPS 13"), praised("a12", "Dell XPS 13")]),
        ("1lp0002", "general", "A laptop for university that lasts", [
            praised("b1", "ThinkPad"), praised("b2", "Thinkpads"), praised("b3", "Lenovo thinkpad"),
            praised("b4", "Lenovo"), praised("b5", "Lenovo laptop"), praised("b6", "ThinkPad P series"),
            praised("b7", "ThinkPad T14"), praised("b8", "MacBook Air"), praised("b9", "MacBook Air"),
            praised("b10", "Dell XPS 13"), praised("b11", "Dell XPS 13"), praised("b12", "Dell XPS 15")]),
    ])


def test_a_university_laptop_answer_shows_thinkpad_and_lenovo_once(tmp_path):
    names = shown(answer("a laptop for university", laptops(tmp_path)))
    assert len([n for n in names if "thinkpad" in n.lower() or "lenovo" in n.lower()]) == 1, names


# --- 2. Garbled names ---

@pytest.fixture(scope="module")
def spelling():
    lists = (load_brand_lines(), load_prices(), load_product_facts())
    return {category: _spelling_lists(*lists, category) for category in ("general", "kitchen")}


@pytest.mark.parametrize("written, shown_as", [
    # An extraction typed "latex" twice; the maker is Sleep On Latex, and the list names its mattress so.
    ("Sleep on latex latex bed", "Sleep On Latex mattress"),
    ("sleep on latex latex bed", "Sleep On Latex mattress"),
    # Bose's QuietComfort Ultra Headphones, as one extraction typed it.
    ("Bose QuietComfort Pros (Ultras?)", "Bose QuietComfort Ultra Headphones"),
    # The basic Kindle, as writers call it ("basic", "in matcha green"): Kindle Basic, the name the brand-lines list gives
    # its line and the price list gives as one of its other names.
    ("Basic in matcha green", "Kindle Basic"),
    ("basic matcha", "Kindle Basic"),
    ("matcha basic", "Kindle Basic"),
    ("basic kindle", "Kindle Basic"),
    ("2024 Basic", "Kindle Basic"),
])
def test_a_garbled_name_is_shown_as_its_maker_writes_it(written, shown_as, spelling):
    makers, curated = spelling["general"]
    assert maker_spelling(written, "general", makers, curated) == shown_as


def test_other_basics_are_not_the_kindle(spelling):
    makers, curated = spelling["general"]
    for name in ("basic Whirlpool", "Basic Vitamix blender", "basic Powerblock kit", "basic Bosch", "basic Cuisinart"):
        assert "Kindle" not in maker_spelling(name, "general", makers, curated), name
    # The basic Sonicare is the Sonicare line, never a product named "Basic Sonicare" (its group is the line's).
    groups = modules_four(SONICARE, "electric toothbrush")
    assert group_with(groups, "basic Sonicare") is group_with(groups, "Sonicare")


def test_the_shown_garbles_find_the_price_of_the_product_they_are(spelling):
    # The mattress maker sells to the US only: no price, but the list's "not sold in the UK" is found by the shown name.
    sold = find_availability("Sleep On Latex mattress", "general", load_prices(), "mattress")
    assert sold is not None and sold.shop == "Sleep On Latex" and sold.not_in_uk
    ultra = find_price("Bose QuietComfort Ultra Headphones", "general", load_prices(), None, "headphones")
    assert ultra is not None and ultra.price == 399.95
    for name in ("Amazon Kindle (2024)", "basic in matcha green", "Kindle Basic", "Kindle Basic"):
        kindle = find_price(name, "general", load_prices(), None, "e-reader")
        assert kindle is not None and kindle.price == 134.99, name


@pytest.mark.parametrize("name, product_type", [
    ("$30 rice cooker", "rice cooker"), ("$15 rice cooker", "rice cooker"), ("£20 rice cooker", "rice cooker"),
    ("30$ rice cooker", "rice cooker"), ("$100 espresso machine", "espresso machine"), ("£20 kettle", "electric kettle"),
])
def test_a_price_in_front_of_the_types_words_names_no_product(name, product_type):
    # What a writer paid or would spend: neither a product nor a brand's line, so it is never ranked or shown.
    groups = group_products([ProductMention("t1", f"c{i}", name, "kitchen", "recommend") for i in range(3)],
                            product_type=product_type)
    assert [g.generic for g in groups] == [True]


@pytest.mark.parametrize("name, product_type", [
    # A price before a maker or a model is that maker's or model's mention (36 library names start with a price).
    ("$150 Ninja", "blender"), ("$30 DeLonghi", "blender"), ("$25 lodge", "cast iron skillet"),
    ("$15 Chinatown rice cooker", "rice cooker"), ("$40 oral b", "electric toothbrush"),
])
def test_a_price_before_a_maker_is_still_that_makers_mention(name, product_type):
    groups = group_products([ProductMention("t1", f"c{i}", name, "kitchen", "recommend") for i in range(3)],
                            product_type=product_type)
    assert groups and not any(g.generic for g in groups)


def test_a_price_name_with_no_requested_type_is_left_as_it_is():
    groups = group_products([ProductMention("t1", f"c{i}", "$30 rice cooker", "kitchen", "recommend") for i in range(3)])
    assert [g.generic for g in groups] == [False]


@pytest.mark.parametrize("name", ["Zojirushi NS-ZCC10", "Tiger JAX-T10U", "1Zpresso JX Pro", "5 Qt Dutch oven",
                                  "30 cm Tefal pan", "3-in-1 Instant Pot"])
def test_a_name_with_a_number_in_it_is_still_a_product(name):
    groups = group_products([ProductMention("t1", f"c{i}", name, "kitchen", "recommend") for i in range(3)])
    assert [g.generic for g in groups] == [False]


@pytest.mark.parametrize("name", ["basic", "Basic", "the basic one", "cheap", "the original", "older", "new", "basic new"])
def test_a_name_of_descriptions_alone_names_no_product(name):
    # A bare "basic" says which model of a brand its thread is about, not which brand (29 mentions in the e-reader
    # threads; the final review's "Basic e-reader line"): nothing to rank or show.
    groups = group_products([ProductMention("t1", f"c{i}", name, "general", "recommend") for i in range(3)],
                            product_type="e-reader")
    assert [g.generic for g in groups] == [True]


def test_a_description_alone_is_the_one_brand_name_that_holds_it_here():
    # The e-reader threads' 29 bare "basic" are "Kindle Basic" (Kindle is written alone here too): one group, not a line
    # of their own called "Basic".
    names = [("basic", 5), ("Basic", 3), ("Kindle Basic", 4), ("kindle basic", 3), ("Kindle", 9), ("Kobo", 6)]
    groups = modules_four(names, "e-reader")
    assert not [g for g in groups if g.generic]
    assert group_with(groups, "basic") is group_with(groups, "Kindle Basic")
    assert group_with(groups, "basic").names["basic"] == 5 and group_with(groups, "basic").names["Basic"] == 3


def test_a_description_alone_that_two_brands_hold_or_none_does_names_no_product():
    two = modules_four([("basic", 3), ("Kindle Basic", 3), ("Kobo Basic", 3), ("Kindle", 4), ("Kobo", 4)], "e-reader")
    assert [list(g.names) for g in two if g.generic] == [["basic"]]
    no_brand_alone = modules_four([("basic", 3), ("Kindle Basic", 3), ("Kobo", 4)], "e-reader")
    assert [list(g.names) for g in no_brand_alone if g.generic] == [["basic"]]


@pytest.mark.parametrize("name", ["basic Kindle", "basic Sonicare", "Original Sprout", "New Balance", "Little Tikes",
                                  "Good Grips OXO", "Big Green Egg", "Kindle Basic", "cheap Casio"])
def test_a_description_beside_a_brand_or_a_model_is_part_of_a_name(name):
    groups = group_products([ProductMention("t1", f"c{i}", name, "general", "recommend") for i in range(3)])
    assert [g.generic for g in groups] == [False]


def rice_cookers(tmp_path):
    return library(tmp_path, "rice cooker", [
        ("1rc0001", "kitchen", "Rice cooker for a family of four?", [
            praised("a1", "$30 rice cooker", 4), praised("a2", "$30 rice cooker", 5),
            praised("a3", "Zojirushi NS-ZCC10", 6), praised("a4", "Zojirushi NS-ZCC10", 7),
            praised("a5", "Tiger", 8), praised("a6", "Tiger rice cooker", 9), praised("a7", "Aroma", 5)]),
        ("1rc0002", "kitchen", "Which rice cooker lasts?", [
            praised("b1", "$30 rice cooker", 6), praised("b2", "Zojirushi NS-ZCC10", 8),
            praised("b3", "Tiger", 6), praised("b4", "Aroma", 4), praised("b5", "Aroma rice cooker", 6),
            praised("b6", "Aroma", 5)]),
    ])


def test_a_rice_cooker_answer_never_shows_a_price_as_a_product(tmp_path):
    result = answer("rice cooker for a family of four", rice_cookers(tmp_path))
    assert not [n for n in shown(result) if "$" in n], shown(result)
    assert "$30 rice cooker" in result.left_out_generic


def mattresses(tmp_path):
    return library(tmp_path, "mattress", [
        ("1mt0001", "general", "Mattress for a side sleeper with back pain?", [
            praised("a1", "Sleep on Latex", 5), praised("a2", "Sleep On Latex", 6),
            praised("a3", "sleep on latex latex bed", 4), praised("a4", "Purple", 3), praised("a5", "Purple", 4),
            praised("a6", "Purple mattress", 5), praised("a7", "Sleep Number bed", 6), praised("a8", "Sleep Number bed", 7),
            praised("a9", "Sleep On Latex soft topper", 2, "mattress topper"), praised("a10", "SOL", 3)]),
        ("1mt0002", "general", "Which mattress lasts?", [
            praised("b1", "Sleep on Latex", 7), praised("b2", "Sleep On Latex", 4), praised("b3", "Purple", 6),
            praised("b4", "Purple mattress", 6), praised("b5", "Sleep Number bed", 8), praised("b6", "Sleep Number bed", 9)]),
    ])


def test_a_mattress_answer_shows_sleep_on_latex_under_its_makers_name(tmp_path):
    names = shown(answer("mattress", mattresses(tmp_path)))
    assert not [n for n in names if "latex latex" in n.lower()], names
    assert any(n == "Sleep On Latex mattress" for n in names), names


def ereaders(tmp_path):
    return library(tmp_path, "e-reader", [
        ("1er0001", "general", "Which e-reader should I buy?", [
            praised("a1", "basic", 4), praised("a2", "Basic", 3), praised("a3", "Kindle Basic", 5),
            praised("a4", "kindle basic", 4), praised("a5", "basic in matcha green", 2), praised("a6", "matcha basic", 3),
            praised("a7", "Paperwhite", 5), praised("a8", "Kindle Paperwhite", 6), praised("a9", "Kobo", 4),
            praised("a12", "Kindle", 5), praised("a13", "Kindle", 7),
            praised("a10", "Kobo", 5), praised("a11", "Kobo Libra Colour", 3)]),
        ("1er0002", "general", "E-reader that is easy on the eyes", [
            praised("b1", "basic", 6), praised("b2", "Basic", 2), praised("b3", "basic kindle", 5),
            praised("b4", "Kindle Basic", 3), praised("b5", "basic matcha", 2), praised("b6", "Paperwhite", 7),
            praised("b7", "Kindle Paperwhite", 8), praised("b8", "Kobo", 4), praised("b9", "Kobo", 6),
            praised("b10", "Kobo Libra Colour", 2)]),
    ])


def test_an_e_reader_answer_shows_the_basic_kindle_once_under_a_name_that_is_not_garbled(tmp_path):
    result = answer("e-reader", ereaders(tmp_path))
    names = shown(result)
    assert "Basic e-reader line" not in names and "Basic in matcha green" not in names, names
    assert not [n for n in names if n.lower().strip() in ("basic", "basic matcha", "matcha basic")], names
    assert len([n for n in names if "kindle" in n.lower() and "paperwhite" not in n.lower()]) <= 1, names
    assert not [pick.model for pick in result.answer.picks if pick.model and "matcha" in pick.model.lower()]
    # The bare "basic" counts for the basic Kindle (it has the most credible voices here), and is no pick of its own.
    assert "Basic" not in result.left_out_generic and "basic" not in result.left_out_generic
    basic = next(pick for pick in result.answer.picks if pick.name in ("Kindle Basic", "Kindle Basic e-reader line"))
    assert basic.breakdown.credible_recommends >= 8


# --- 3. Pan facts, from the makers' own pages (read 19 Oct 2026) ---

OXO_MODEL = "OXO ceramic professional non-stick"  # the model one writer named; the group's other names are OXO's range


def test_oxos_ceramic_professional_pan_is_pfas_free_and_non_stick_by_its_makers_page():
    entry = find_facts(OXO_MODEL, "kitchen", load_product_facts(), "frying pan")
    assert entry is not None
    assert entry.facts["pfas_free"] is True and entry.facts["non_stick"] is True
    assert any("oxouk.com" in source for source in entry.sources)
    assert entry.checked_on.isoformat() == "2026-10-19"


def test_oxos_range_as_a_whole_stays_unconfirmed_since_its_older_pans_are_only_pfoa_free():
    entry = find_facts("OXO non-stick pan", "kitchen", load_product_facts(), "frying pan")
    assert entry is not None and "pfas_free" not in entry.facts
    assert entry is not find_facts(OXO_MODEL, "kitchen", load_product_facts(), "frying pan")


def test_caraways_ceramic_non_stick_frying_pan_is_non_stick_by_its_makers_page():
    facts = load_product_facts()
    entry = find_brand_facts(["Caraway", "Caraway pans", "Caraway frying pans"], "kitchen", facts,
                             ["frying", "pan", "pans"], "frying pan")
    assert entry is not None
    assert entry.facts["non_stick"] is True and entry.facts["pfas_free"] is True
    assert any("carawayhome.com" in source for source in entry.sources)
    assert entry.checked_on.isoformat() == "2026-10-19"


def pans(tmp_path):
    return library(tmp_path, "frying pan", [
        ("1pn0001", "kitchen", "Non-stick frying pan without PFAS that lasts?", [
            praised("a1", "Oxo ceramic professional non-stick", 3), praised("a2", "OXO non-stick", 4),
            praised("a3", "Oxo non stick skillet", 2), praised("a4", "OXO non-stick pan", 5),
            praised("a5", "Caraway frying pans", 3), praised("a6", "Caraway", 2), praised("a7", "caraway pans", 4),
            praised("a8", "GreenPan", 6), praised("a9", "GreenPan", 5), praised("a10", "GreenPan", 4)]),
        ("1pn0002", "kitchen", "Which non-stick pan has no PFAS and lasts?", [
            praised("b1", "oxo non stick pans", 3), praised("b2", "OXO non-stick", 4), praised("b3", "Caraway pan", 2),
            praised("b4", "Caraway", 3), praised("b5", "GreenPan", 5), praised("b6", "GreenPan", 4)]),
    ])


def test_the_blind_tests_pfas_free_pan_answer_confirms_oxo_and_caraway(tmp_path):
    result = answer("non-stick frying pan without PFAS that actually lasts", pans(tmp_path))
    picks = {pick.name: pick for pick in result.answer.picks}
    oxo = next(pick for name, pick in picks.items() if "OXO" in name)
    caraway = next(pick for name, pick in picks.items() if "Caraway" in name)
    assert oxo.name == "OXO Ceramic Professional"
    assert oxo.cautions == [] and caraway.cautions == []
    # Shown under its maker's name, it keeps its price, where it is sold and a link to its maker's page.
    assert oxo.price.text.startswith("£75 at John Lewis") and oxo.availability.text.startswith("Sold at John Lewis")
    assert oxo.link is not None and "oxouk.com" in oxo.link.url


def test_a_teflon_free_request_reads_the_same_facts(tmp_path):
    result = answer("non stick pan without teflon that lasts", pans(tmp_path))
    for pick in result.answer.picks:
        if "OXO" in pick.name or "Caraway" in pick.name:
            assert pick.cautions == [], (pick.name, pick.cautions)
