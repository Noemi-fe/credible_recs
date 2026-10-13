"""The same product never shows twice in one answer (13 Oct 2026, from reading the day's answers).

b06 (an electric kettle that lasts) showed two picks for one maker's kettles: "Fellow Stagg EKG" and "Fellow kettle". No
Fellow model's name says "kettle", so "Fellow kettle" fitted no product but itself and was ranked as one. In a kettle
answer it is the brand followed by the type's word: Fellow's kettle line, which steps aside for its own model when both
are shown (engine.pipeline._fold_brand_picks). And a lip balm answer listed one brand's line twice on its skip list,
once from the brand alone and once from the brand with "balm".

Every library, product and comment here is made up; no test reads data/.
"""

from datetime import date

from engine.answer import unverified_claims
from engine.pipeline import answer_request
from engine.tests.test_pipeline import praise, write_library

TODAY = date(2026, 10, 9)
KETTLE_REQUEST = "electric kettle that lasts 10+ years"


def warn(comment_id: str, product: str, months: int) -> tuple:
    return comment_id, product, f"My {product} died after {months} months of daily use, avoid it.", "warn"


def fellow_library(tmp_path):
    """Two kettle threads: the Fellow Stagg EKG praised twice in each, "Fellow kettle" (no model) praised twice in each,
    the Fellow Corvo EKG and the brand alone once; a Zojirushi and a Bonavita kettle praised three times."""
    return write_library(tmp_path, {
        "1fel001": ("Which electric kettle lasts?", "Mine died again.", [
            praise("s1a", "Fellow Stagg EKG", 6), praise("s1b", "Fellow Stagg EKG", 5),
            praise("k1a", "Fellow kettle", 7), praise("k1b", "Fellow kettle", 8),
            praise("c1a", "Fellow Corvo EKG", 4), praise("f1a", "Fellow", 9),
            praise("z1a", "Zojirushi kettle", 6), praise("z1b", "Zojirushi kettle", 7),
            praise("b1a", "Bonavita gooseneck kettle", 5), praise("b1b", "Bonavita gooseneck kettle", 6),
        ]),
        "1fel002": ("Electric kettle that lasts 10 years?", "Tired of replacing it.", [
            praise("s2a", "Fellow Stagg EKG", 4), praise("s2b", "Fellow Stagg EKG", 7),
            praise("k2a", "Fellow kettle", 6), praise("k2b", "Fellow kettles", 5),
            praise("z2a", "Zojirushi kettle", 9), praise("b2a", "Bonavita gooseneck kettle", 4),
        ]),
    }, community="BuyItForLife")


def shown_names(answer) -> list[str]:
    return [p.name for p in answer.picks] + [w.name for w in answer.worth_a_look] + [s.name for s in answer.skip]


def test_a_brand_with_the_types_word_is_the_brands_line_not_a_second_product(tmp_path):
    result = answer_request(KETTLE_REQUEST, library_dir=fellow_library(tmp_path), prices=[], product_facts=[],
                            brand_lines=[], today=TODAY)
    fellow = [name for name in shown_names(result.answer) if name.lower().startswith("fellow")]
    assert fellow == ["Fellow Stagg EKG"], shown_names(result.answer)
    # "Fellow kettle" is the brand's line, shown as the brand's: it stepped aside for its own model.
    assert [(f.name, f.stepped_aside_for) for f in result.folded_brand_picks] == [
        ("Fellow electric kettle line", "Fellow Stagg EKG")]
    assert unverified_claims(result.answer, result.bodies) == []


def test_a_brands_line_with_and_without_the_types_word_is_listed_once(tmp_path):
    # "Chefman" fits two Chefman kettles, and so does "Chefman kettle": both were the Chefman line on the skip list.
    lib = write_library(tmp_path, {
        "1che001": ("Which electric kettle lasts?", "Mine died again.", [
            warn("w1a", "Chefman", 6), warn("w1b", "Chefman kettle", 8), warn("w1c", "Chefman kettle", 5),
            praise("g1a", "Chefman glass kettle", 1), praise("t1a", "Chefman stainless kettle", 1),
            praise("z1a", "Zojirushi kettle", 6), praise("z1b", "Zojirushi kettle", 7),
        ]),
        "1che002": ("Electric kettle that lasts 10 years?", "Tired of replacing it.", [
            warn("w2a", "Chefman", 4), warn("w2b", "Chefman kettle", 3), praise("z2a", "Zojirushi kettle", 9),
        ]),
    }, community="BuyItForLife")
    result = answer_request(KETTLE_REQUEST, library_dir=lib, prices=[], product_facts=[], brand_lines=[], today=TODAY)
    chefman = [name for name in shown_names(result.answer) if name.lower().startswith("chefman")]
    assert chefman == ["Chefman electric kettle line"], shown_names(result.answer)


def test_two_groups_shown_under_one_name_are_one_product():
    # The last guard (13 Oct 2026): whatever made two groups (a UK name, a line's name, a facts entry's name), a reader
    # can't tell two items of the same name apart, so they are ranked as one, under the first (the bigger) one's key.
    from engine.group_products import ProductGroup, ProductMention
    from engine.pipeline import _one_per_name

    def group(key, name, *comments, loose=True):
        mentions = [ProductMention("1fake01", c, name, "skincare", "warn") for c in comments]
        return ProductGroup(key, name, "skincare", mentions, loose)

    first, second = group("skincare:torriden", "Torriden lip balm line", "c1", "c2"), group(
        "skincare:torriden balm", "torriden lip balm line", "c3")
    other = group("skincare:laneige", "Laneige lip balm line", "c4")
    merged = _one_per_name([first, other, second])
    assert [(g.key, g.name, len(g.mentions)) for g in merged] == [
        ("skincare:torriden", "Torriden lip balm line", 3), ("skincare:laneige", "Laneige lip balm line", 1)]
