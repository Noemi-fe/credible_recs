"""A line pick's "Most named model" is a real product's name (17 Oct 2026, the converge round, item 4).

Since 10 Oct 2026 a brand-line pick names the model of its brand its credible writers recommend most ("Most named
model: Victorinox Fibrox"), taken from the writers' own names for it. The 17 Oct sweep showed what that lets through:
a size ('6.5" Lodge skillets', "Cuisinart 7 cup"), a description ("corded DeWalt drill" in a cordless drill answer,
"Cosori two basket version"), a discontinued model ("2011 Macbook Air") and a shop's code ("... (B005YR0F40)", in a
blind-test packet). Now a model is named only when we know it as one product: a price or availability entry under
its own name (not the brand's), a facts entry, a researched product page, or a name the matcher knows as one product
(engine/data/product_aliases.json); never one with a shop's code, never a discontinued one. With none, the next most
recommended model that is known is named, or none.

Every library, product and price here is made up.
"""

from engine.group_products import ProductGroup, ProductMention
from engine.pipeline import _a_known_model, answer_request
from engine.prices import PriceCheck
from engine.tests.test_availability import listed
from engine.tests.test_pick_polish import KNIFE_REQUEST, TODAY, VICTORINOX
from engine.tests.test_pipeline import praise, write_library

SIZED = "Victorinox 8 inch chef knife"
FIBROX = "Victorinox Fibrox chef knife"


def knives(tmp_path):
    """"Victorinox" fits several Victorinox knives (a line pick); its 8 inch knife is praised 3 times, all in one thread
    (so never a pick of its own), its Fibrox twice; the Mac and the Tojiro are the other picks."""
    return write_library(tmp_path, {
        "1knif01": ("Best first chef knife?", "Budget about 100.", [
            praise("v1a", "Victorinox", 5), praise("v1b", "Victorinox", 6),
            praise("s1a", SIZED, 4), praise("s1b", SIZED, 5), praise("s1c", SIZED, 6),
            praise("f1a", FIBROX, 3),
            praise("m1a", "Mac Mighty chef knife", 7), praise("m1b", "Mac Mighty chef knife", 8),
            praise("t1a", "Tojiro DP gyuto", 5), praise("t1b", "Tojiro DP gyuto", 6),
        ]),
        "1knif02": ("Which chef knife lasts?", "Mine chipped.", [
            praise("v2a", "Victorinox", 9), praise("v2b", "Victorinox", 10),
            praise("f2a", FIBROX, 5),
            praise("m2a", "Mac Mighty chef knife", 4), praise("t2a", "Tojiro DP gyuto", 3),
        ]),
    }, community="chefknives")


def line_pick(result):
    return next(pick for pick in result.answer.picks if pick.name == VICTORINOX)


def test_a_size_with_no_entry_of_its_own_is_never_the_model_named(tmp_path):
    # The 8 inch knife is recommended most, but nothing says it is one product (a size the writers added); the Fibrox
    # is a name the matcher knows as one product, so it is named.
    result = answer_request(KNIFE_REQUEST, library_dir=knives(tmp_path), prices=[], product_facts=[],
                            product_pages=[], today=TODAY)
    assert line_pick(result).model == FIBROX


def test_a_model_with_an_entry_under_its_own_name_is_named(tmp_path):
    result = answer_request(KNIFE_REQUEST, library_dir=knives(tmp_path), prices=[listed(SIZED, price=45.0)],
                            product_facts=[], product_pages=[], today=TODAY)
    assert line_pick(result).model == SIZED


def test_an_entry_under_the_brands_name_says_nothing_of_one_model(tmp_path):
    # "Victorinox chef knife" is the brand and the type: it speaks for the line, never for one of its models.
    result = answer_request(KNIFE_REQUEST, library_dir=knives(tmp_path), prices=[listed("Victorinox chef knife")],
                            product_facts=[], product_pages=[], today=TODAY)
    assert line_pick(result).model == FIBROX


def brand(name="Victorinox"):
    return ProductGroup(f"kitchen:{name.lower()}", name, "kitchen", [ProductMention("t1", "c1", name, "kitchen",
                                                                                    "recommend")], True)


class Model:
    """A ranked product (its name and key), or a page (its product's name)."""

    def __init__(self, name, key=None):
        self.name, self.key, self.product = name, key or f"kitchen:{name.lower()}", name


def test_a_shops_code_or_a_discontinued_model_is_never_named():
    coded = Model("Bonavita variable temperature gooseneck (B005YR0F40)")
    entry = listed(coded.name, price=60.0)
    assert not _a_known_model(coded, brand("Bonavita"), "electric kettle",
                              {coded.key: PriceCheck(entry, "no budget", availability=entry)}, {}, {})
    gone = Model("Victorinox Swibo chef knife")
    stopped = listed(gone.name, available=False)
    assert not _a_known_model(gone, brand(), "chef knife", {gone.key: PriceCheck(None, "no budget",
                                                                                 availability=stopped)}, {}, {})


def test_a_model_sold_only_abroad_is_still_a_real_product():
    abroad = Model("Victorinox Grand Maitre chef knife")
    entry = listed(abroad.name, available=False).model_copy(update={"not_in_uk": True})
    assert _a_known_model(abroad, brand(), "chef knife", {abroad.key: PriceCheck(None, "no budget",
                                                                                 availability=entry)}, {}, {})


def test_a_facts_entry_or_a_researched_page_makes_a_model_known():
    model = Model("Victorinox Grand Maitre chef knife")
    facts = {"kitchen": [("victorinox", "grand", "maitre", "chef", "knife")]}
    assert _a_known_model(model, brand(), "chef knife", {}, facts, {})
    assert _a_known_model(model, brand(), "chef knife", {}, {}, {model.key: Model(model.name)})
    assert not _a_known_model(model, brand(), "chef knife", {}, {}, {})
    # A page under the brand's name only (its line's page, found for the model's name too) says nothing of one model.
    assert not _a_known_model(model, brand(), "chef knife", {}, {}, {model.key: Model("Victorinox chef knife line")})
