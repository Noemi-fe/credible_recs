"""Module 1's routing audit (14 Oct 2026, the routing-audit builder; Noemi: recommendations "regardless of the category").

A wrong route gives a confident wrong answer, worse than an honest "we haven't read about this yet". A breadth-first
pass over about 1,000 realistic requests (each type's head noun with the modifiers that make it another product, and
phrasings people type) found the rules routing by a single word: a hunting knife or a Stanley knife was the kitchen's
chef knife, a pepper grinder a coffee grinder, kettle chips an electric kettle, a carpet shampoo a hair shampoo, an
iPad case an iPad, wine glasses a polite no about food. With the open model on, kitchen gadgets and kitchen knives
landed in the general category (a bread maker in "home", a paring knife in "tools"), where answers can't count the
mentions the reading AI types as kitchen gear; and a model that dropped a word ("knife" for "petty knife", "blender" for
"hand blender") brought back the very type the rules had set aside. Every request here is made up; the open model is off
in tests (stand-in models only).
"""

import pytest

from engine.config import GENERAL_DEPARTMENTS, SUBREDDITS
from engine.query import FOOD_MESSAGE, HARMFUL_MESSAGE, HEALTH_MESSAGE, MEDIA_MESSAGE, classify, parse_query


def routed(text: str) -> tuple:
    routing = classify(text)
    return routing.status, routing.category, routing.product_type


class FakeModel:
    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def read(self, text: str):
        self.asked.append(text)
        return self.answer


# --- Knives: "knife" alone is the kitchen's chef knife; other kinds are their own types ---

@pytest.mark.parametrize("text", ["chef's knife under £100", "a good kitchen knife for a beginner cook",
                                  "gyuto 240mm recommendations", "santoku knife for a small kitchen",
                                  "a good knife for chopping onions", "kitchen knives that stay sharp",
                                  "first chef's knife under £100 for a home cook"])
def test_a_knife_for_cooking_is_still_a_chef_knife(text):
    assert routed(text) == ("ok", "kitchen", "chef knife")


@pytest.mark.parametrize("text, product_type", [
    ("best paring knife under £30", "paring knife"),
    ("petty knife 150mm", "paring knife"),
    ("kitchen utility knife", "paring knife"),
    ("a good bread knife for sourdough", "bread knife"),
    ("serrated knife for tomatoes and bread", "bread knife"),
    ("meat cleaver for chopping bones", "cleaver"),
    ("chinese cleaver for vegetables", "cleaver"),
    ("chinese chef knife", "cleaver"),
    ("steak knives that don't need sharpening", "steak knife"),
    ("steak knife set of 6", "steak knife"),
    ("boning knife for butchering chickens", "boning knife"),
    ("flexible fillet knife", "fillet knife"),
    ("carving knife for the sunday roast", "carving knife"),
    ("slicing knife for brisket", "carving knife"),
    ("nakiri for vegetables", "nakiri"),
])
def test_a_kitchen_knife_of_another_kind_is_a_kitchen_type_of_its_own(text, product_type):
    # Kitchen knives, read from the kitchen's knife communities first (r/chefknives), never the general category's
    # tools (where the open model had put a paring knife, a bread knife and a cleaver).
    query = parse_query(text)
    assert (query.status, query.category, query.product_type, query.department) == ("ok", "kitchen", product_type,
                                                                                     None)
    assert query.subreddits[0] in ("chefknives", "BuyItForLife")


@pytest.mark.parametrize("text, product_type, department", [
    ("folding knife for camping", "pocket knife", "outdoor"),
    ("best pocket knife under £50", "pocket knife", "outdoor"),
    ("swiss army knife that's legal in the uk", "pocket knife", "outdoor"),
    ("edc knife under 100", "pocket knife", "outdoor"),
    ("pen knife for my keyring", "pocket knife", "outdoor"),
    ("multitool knife", "pocket knife", "outdoor"),
    ("spyderco knife", "pocket knife", "outdoor"),
    ("a small knife for my keychain", "pocket knife", "outdoor"),
    ("hunting knife for deer", "outdoor knife", "outdoor"),
    ("survival knife", "outdoor knife", "outdoor"),
    ("bushcraft knife for carving wood", "outdoor knife", "outdoor"),
    ("fixed blade knife for bushcraft", "outdoor knife", "outdoor"),
    ("dive knife for scuba", "outdoor knife", "outdoor"),
    ("mora knife", "outdoor knife", "outdoor"),
    ("a knife for camping", "outdoor knife", "outdoor"),
    ("a knife for my fishing tackle box", "outdoor knife", "outdoor"),
    ("whittling knife for beginners", "whittling knife", "hobbies"),
    ("wood carving knife", "whittling knife", "hobbies"),
    ("knife for wood carving", "whittling knife", "hobbies"),
    ("a knife for whittling", "whittling knife", "hobbies"),
    ("x-acto knife", "craft knife", "hobbies"),
    ("hobby knife for models", "craft knife", "hobbies"),
    ("stanley knife", "box cutter", "tools"),
    ("box cutter", "box cutter", "tools"),
    ("carpet knife", "box cutter", "tools"),
])
def test_a_knife_that_isnt_for_the_kitchen_is_never_a_chef_knife(text, product_type, department):
    query = parse_query(text)
    assert (query.status, query.category, query.product_type, query.department) == ("ok", "general", product_type,
                                                                                     department)
    assert set(query.subreddits) <= set(SUBREDDITS["general"])


@pytest.mark.parametrize("text", ["putty knife", "palette knife for oil painting", "electric carving knife",
                                  "tomato knife", "oyster knife for shucking", "sushi knife", "pumpkin carving knife",
                                  "utility knife for cutting drywall", "kitchen utility knife"])
def test_a_knife_no_type_lists_is_set_aside_not_taken_for_a_chef_knife(text):
    # The rules ask (the open model places it), never the chef knife whose word it holds. A plain "utility knife" is a
    # box cutter or a small kitchen knife: the open model reads which (a kitchen utility knife is a paring knife).
    assert routed(text)[2] != "chef knife"


def test_two_knife_names_are_left_out_on_purpose():
    # Like cookware sets (config.MORE_PRODUCT_TYPES), a knife set isn't a type of its own: its name made two knife set
    # threads another product's, which the chef knife answer of the blind test reads (b07). It stays a chef knife
    # request. And the general category's box cutter isn't named "utility knife": the reading AI types a kitchen's
    # small knife so too, and the type's category would have taken those mentions out of the kitchen's answers.
    from engine.query import PRODUCT_TYPES

    names = {p.name for p in PRODUCT_TYPES}
    assert "knife set" not in names and "utility knife" not in names and "box cutter" in names


@pytest.mark.parametrize("text", ["tactical knife", "throwing knife", "butterfly knife", "a knife for self defence",
                                  "combat knife", "switchblade", "flick knife"])
def test_a_weapon_the_list_names_is_still_the_polite_no(text):
    assert (classify(text).status, classify(text).message) == ("out_of_scope", HARMFUL_MESSAGE)


@pytest.mark.parametrize("text", ["zombie knife", "karambit knife", "bowie knife", "trench knife", "knuckle knife",
                                  "gravity knife", "otf knife", "automatic knife", "stiletto knife", "boot knife",
                                  "neck knife", "credit card knife", "hidden knife"])
def test_a_weapon_like_knife_the_list_doesnt_name_is_never_a_chef_knife(text):
    # Whether these join the polite no (engine.query.HARMFUL) is Noemi's call (config.PROPOSED_HARMFUL); until then the
    # rules set them aside, so no answer recommends chef knives for them.
    routing = classify(text)
    assert routing.product_type is None and routing.message != HARMFUL_MESSAGE


# --- Grinders ---

@pytest.mark.parametrize("text", ["burr grinder for espresso", "hand grinder for pour over", "manual coffee grinder",
                                  "a grinder for espresso under 200", "best grinder for filter coffee"])
def test_a_grinder_for_coffee_is_still_a_coffee_grinder(text):
    assert routed(text) == ("ok", "kitchen", "coffee grinder")


@pytest.mark.parametrize("text, product_type", [
    ("pepper grinder that doesn't leak", "pepper grinder"),
    ("salt and pepper grinder set", "pepper grinder"),
    ("pepper mill", "pepper grinder"),
    ("spice grinder for whole spices", "spice grinder"),
    ("meat grinder for burgers", "meat grinder"),
    ("meat mincer", "meat grinder"),
])
def test_a_kitchen_grinder_for_something_else_is_its_own_type(text, product_type):
    assert routed(text) == ("ok", "kitchen", product_type)


def test_a_grinder_for_coffee_and_spices_is_a_coffee_grinder_in_requests_and_titles():
    # A blade grinder sold for both is still a coffee grinder: "spice grinder" inside "coffee/spice grinder" doesn't
    # take a coffee grinder thread away from coffee grinder answers (the blind test's b09 reads one so titled).
    from engine.sources import mentions_product

    assert routed("coffee and spice grinder") == ("ok", "kitchen", "coffee grinder")
    assert mentions_product("My cheap coffee/spice grinder is still going", "coffee grinder")
    assert not mentions_product("Which spice grinder for whole cumin?", "coffee grinder")
    assert not mentions_product("Meat grinder or food processor for mince?", "coffee grinder")


@pytest.mark.parametrize("text", ["bench grinder for sharpening tools", "die grinder", "stump grinder"])
def test_a_tool_grinder_is_never_a_coffee_grinder(text):
    assert routed(text)[2] not in ("coffee grinder", "pepper grinder", "spice grinder", "meat grinder")


def test_a_nail_grinder_for_a_dog_is_a_pet_tool():
    assert routed("nail grinder for my dog") == ("ok", "general", "pet nail clippers")


# --- Kettles ---

@pytest.mark.parametrize("text", ["cast iron kettle", "japanese cast iron kettle", "induction kettle",
                                  "kettle for an aga", "kettle for a gas stove", "best kettle for induction hob"])
def test_a_kettle_for_the_hob_is_a_stovetop_kettle(text):
    assert routed(text) == ("ok", "kitchen", "stovetop kettle")


def test_a_camping_kettle_is_camping_cookware():
    assert classify("camping kettle").product_type == "camping cookware"
    assert classify("kettle for backpacking").product_type != "electric kettle"
    assert parse_query("camping kettle").department == "outdoor"


@pytest.mark.parametrize("text", ["kettle chips", "best kettle chips flavour", "kettle corn"])
def test_kettle_chips_are_food_not_a_kettle(text):
    assert (classify(text).status, classify(text).message) == ("out_of_scope", FOOD_MESSAGE)


def test_a_kettle_that_isnt_one_is_set_aside():
    assert routed("popcorn kettle") == ("ok", "kitchen", "popcorn maker")
    assert routed("fish kettle for salmon")[2] not in ("electric kettle", "stovetop kettle")
    assert routed("electric kettle that lasts 10+ years") == ("ok", "kitchen", "electric kettle")


# --- Irons, mixers, scales ---

@pytest.mark.parametrize("text, not_this", [
    ("tire iron", "car tyres"), ("tyre iron for my car", "car tyres"), ("tyre pressure monitor", "car tyres"),
    ("cast iron radiator", "cast iron skillet"), ("cast iron bath", "cast iron skillet"),
    ("kitchen mixer tap", "stand mixer"), ("mixer tap for the kitchen", "stand mixer"), ("mixer shower", "stand mixer"),
])
def test_a_word_of_a_product_inside_another_things_name_isnt_that_product(text, not_this):
    assert routed(text)[2] != not_this


def test_an_enamelled_cast_iron_casserole_is_a_dutch_oven():
    assert routed("enameled cast iron casserole") == ("ok", "kitchen", "dutch oven")
    assert routed("cast iron casserole dish") == ("ok", "kitchen", "dutch oven")


def test_a_cast_iron_pan_is_still_a_skillet():
    assert routed("cast iron skillet that lasts") == ("ok", "kitchen", "cast iron skillet")
    assert routed("cast iron teapot")[2] == "teapot" and routed("cast iron wok")[2] == "wok"


# --- Pans, pots and bakeware ---

@pytest.mark.parametrize("text", ["dust pan and brush", "oil drain pan for my car", "gold pan for panning"])
def test_a_pan_that_isnt_for_cooking_isnt_a_frying_pan(text):
    assert routed(text)[2] != "frying pan"


@pytest.mark.parametrize("text, product_type", [
    ("sheet pan for roasting", "baking tray"), ("baking tray that doesn't warp", "baking tray"),
    ("pizza pan", "baking tray"), ("roasting tin with a rack", "baking tray"),
    ("springform pan for cheesecake", "cake tin"), ("9x13 pan", "cake tin"), ("loaf tin", "cake tin"),
    ("muffin tin", "cake tin"), ("brownie pan", "cake tin"),
])
def test_bakeware_is_its_own_kitchen_type(text, product_type):
    assert routed(text) == ("ok", "kitchen", product_type)


@pytest.mark.parametrize("text", ["pot plant for a dark room", "pot rack for the kitchen", "pot holder", "pot scrubber"])
def test_a_pot_that_isnt_for_cooking_isnt_a_saucepan(text):
    assert routed(text)[2] != "saucepan"


def test_a_pot_for_cooking_is_still_a_saucepan():
    assert routed("a big pot for pasta") == ("ok", "kitchen", "saucepan")


# --- Kitchen gadgets: the kitchen's, so their answers count the kitchen's mentions ---

@pytest.mark.parametrize("text, product_type", [
    ("bread maker that lasts", "bread maker"), ("ice cream maker", "ice cream maker"),
    ("toastie maker", "sandwich maker"), ("sandwich toaster", "sandwich maker"), ("panini press", "sandwich maker"),
    ("george foreman grill", "electric grill"), ("electric grill for indoors", "electric grill"),
    ("pasta machine", "pasta maker"), ("sodastream", "soda maker"), ("countertop ice maker", "ice maker"),
    ("popcorn maker", "popcorn maker"), ("sous vide for steak", "sous vide cooker"),
    ("vacuum sealer for sous vide", "vacuum sealer"), ("immersion blender for soup", "immersion blender"),
    ("hand blender", "immersion blender"), ("deep fat fryer", "deep fryer"), ("food dehydrator", "food dehydrator"),
    ("food dryer for jerky", "food dehydrator"), ("mandoline slicer", "mandoline"),
    ("meat thermometer", "meat thermometer"), ("candy thermometer", "meat thermometer"),
    ("garlic press", "garlic press"), ("salad spinner", "salad spinner"), ("salad dryer", "salad spinner"),
    ("can opener that lasts", "can opener"), ("vegetable peeler", "peeler"), ("cheese grater", "grater"),
    ("mixing bowls", "mixing bowl"), ("glass food storage containers", "food storage container"),
    ("cutlery set", "cutlery"), ("butter knives", "cutlery"), ("dinnerware set", "dinnerware"),
    ("wine glasses that don't break", "wine glass"), ("cocktail shaker", "cocktail shaker"),
    ("corkscrew", "wine opener"), ("kitchen scissors", "kitchen scissors"),
])
def test_a_kitchen_gadget_is_a_kitchen_type(text, product_type):
    query = parse_query(text)
    assert (query.status, query.category, query.product_type) == ("ok", "kitchen", product_type)
    assert set(query.subreddits) <= set(SUBREDDITS["kitchen"])


@pytest.mark.parametrize("text", ["shoe dryer", "hand dryer", "glove dryer for skiing", "dish dryer"])
def test_a_dryer_for_something_else_isnt_a_tumble_dryer(text):
    assert routed(text)[2] != "tumble dryer"


def test_a_dish_drying_rack_isnt_a_clothes_airer():
    assert routed("dish drying rack")[2] != "clothes airer"
    assert routed("clothes drying rack") == ("ok", "general", "clothes airer")


@pytest.mark.parametrize("text", ["pool vacuum", "vacuum storage bags", "vacuum pump for wine"])
def test_a_vacuum_that_isnt_a_cleaner_isnt_a_vacuum_cleaner(text):
    assert routed(text)[2] != "vacuum cleaner"


@pytest.mark.parametrize("text", ["solar oven for camping", "camping oven", "tandoor oven for the garden"])
def test_an_oven_that_isnt_the_kitchens_isnt_an_oven(text):
    assert routed(text)[2] != "oven"


def test_a_halogen_oven_is_a_countertop_oven():
    assert routed("halogen oven") == ("ok", "kitchen", "toaster oven")


def test_freezer_bags_arent_a_freezer():
    assert routed("freezer bags")[2] != "freezer"


# --- A product's name followed by a word for something made for it names that thing ---

@pytest.mark.parametrize("text, not_this", [
    ("ipad case for kids", "tablet"), ("ipad stand", "tablet"), ("airpods case", "earbuds"), ("kindle case", "e-reader"),
    ("switch case for travel", "gaming console"), ("guitar case", "guitar"), ("guitar strings", "guitar"),
    ("guitar pedal", "guitar"), ("guitar tuner", "guitar"), ("camera battery", "camera"),
    ("drone batteries", "drone"), ("3d printer filament", "3d printer"), ("phone gimbal", "phone"),
    ("tent pegs", "tent"), ("bike chain", "bicycle"), ("drill bits for concrete", "drill"), ("lens cap", "camera lens"),
    ("dishwasher salt", "dishwasher"), ("washing machine cleaner", "washing machine"),
    ("coffee machine descaler", "espresso machine"), ("kettle descaler", "electric kettle"),
    ("hoover bags", "vacuum cleaner"), ("makeup brush cleaner", "makeup brush"), ("sewing machine oil", "sewing machine"),
    ("baby bottle steriliser", "baby bottle"), ("chair mat for carpet", "office chair"),
    ("iphone 15 pro case", "phone"), ("galaxy s24 case", "phone"), ("kayak paddle", "kayak"),
    # A clue word inside a name set aside so counts no more than the name: "sun" in "sun lounger cushions".
    ("sun lounger cushions", "sunscreen"), ("pot rack for the kitchen", "saucepan"),
])
def test_a_products_name_followed_by_a_thing_made_for_it_isnt_the_product(text, not_this):
    assert routed(text)[2] != not_this


@pytest.mark.parametrize("text, product_type", [
    ("phone case", "phone case"), ("laptop bag for work", "laptop bag"), ("tv stand", "tv stand"),
    ("a case for my iphone 15", "phone case"), ("a mouse toy for my cat", "cat toy"),
    ("best laptop battery life under 800", "laptop"), ("phone with good battery life", "phone"),
    ("sleeping bag for summer camping", "sleeping bag"), ("dog bed for a big dog", "dog bed"),
])
def test_a_name_holding_such_a_word_and_battery_life_are_still_the_product(text, product_type):
    assert routed(text)[2] == product_type


# --- Single words that caught other products ---

@pytest.mark.parametrize("text, not_this", [
    ("carpet shampoo", "shampoo"), ("upholstery shampoo", "shampoo"),
    ("fabric conditioner that smells nice", "conditioner"), ("leather conditioner for boots", "conditioner"),
    ("water conditioner for my fish tank", "conditioner"), ("lash serum", "serum"),
    ("hair toner for brassy hair", "toner"), ("purple toner for blonde hair", "toner"), ("vanilla essence", "toner"),
    ("peel and stick wallpaper", "exfoliant"), ("peel and stick tiles for the kitchen", "exfoliant"),
    ("spot treatment for carpet stains", "spot treatment"),
    ("sun shade for the garden", "sunscreen"), ("uv light for curing resin", "sunscreen"),
    ("raised garden bed", "bed frame"), ("bed bug spray", "bed frame"), ("camp bed", "bed frame"),
    ("shower chair", "office chair"), ("bean bag chair", "office chair"), ("deck chair", "office chair"),
    ("capsule wardrobe basics", "wardrobe"), ("pc case fans", "fan"), ("cpu cooler", "cooler"),
    ("air cooler for a bedroom", "cooler"), ("patio heater", "space heater"),
    ("blow torch for creme brulee", "flashlight"), ("kitchen torch", "flashlight"),
    ("co2 monitor for my flat", "monitor"), ("projector screen", "projector"),
    ("star projector for a kids room", "projector"), ("radio controlled car", "radio"),
    ("a router for woodworking", "wifi router"), ("trim router", "wifi router"), ("car amp", "guitar amp"),
    ("computer glasses", "desktop computer"), ("desktop organiser", "desktop computer"), ("lab coat", "winter coat"),
    ("wet suit for open water swimming", "suit"), ("ski suit", "suit"), ("grow tent for plants", "tent"),
    ("dirt bike for a teenager", "bicycle"), ("quad bike", "bicycle"), ("camping mattress", "mattress"),
    ("dog mattress", "mattress"), ("pillow case", "pillow"),
])
def test_a_single_word_no_longer_catches_another_product(text, not_this):
    assert routed(text)[2] != not_this


@pytest.mark.parametrize("text, product_type", [
    ("wine cooler", "fridge"), ("musical keyboard for a child", "digital piano"), ("tv box", "streaming device"),
    ("swim suit for holiday", "swimwear"), ("camping mattress", "air mattress"), ("dog mattress", "dog bed"),
    ("pillow top mattress", "mattress"), ("pillow case", "bed sheets"), ("rocking chair for the nursery", "armchair"),
    ("dryer brush", "hot air brush"), ("alcohol stove for hiking", "camping stove"), ("dog food bowl", "pet bowl"),
])
def test_a_name_people_use_finds_its_type(text, product_type):
    assert routed(text)[2] == product_type


# --- Polite nos: products holding a word of what stays out aren't refused; what stays out still is ---

@pytest.mark.parametrize("text", ["baby food maker", "cat food storage container", "formula milk maker", "wine rack",
                                  "olive oil dispenser", "cereal dispenser", "snack containers for kids",
                                  "chocolate fountain", "photo album", "film for my camera", "medicine cabinet",
                                  "medicine ball for slams", "flight case for my guitar", "lay z spa hot tub",
                                  "holiday lights for the house", "games table"])
def test_a_product_holding_a_word_of_what_stays_out_isnt_refused(text):
    assert classify(text).status != "out_of_scope"


@pytest.mark.parametrize("text, message", [
    ("best coffee beans for espresso", FOOD_MESSAGE), ("a whisky under £50", FOOD_MESSAGE),
    ("best dog food for a puppy", FOOD_MESSAGE), ("vitamin d supplement for winter", HEALTH_MESSAGE),
    ("best books about stoicism", MEDIA_MESSAGE), ("best wine for a dinner party", FOOD_MESSAGE),
])
def test_what_stays_out_still_gets_its_polite_no(text, message):
    assert (classify(text).status, classify(text).message) == ("out_of_scope", message)


@pytest.mark.parametrize("text", ["airbrush gun", "tattoo gun", "rivet gun", "icing gun", "cookie gun", "hose gun",
                                  "grout gun", "shotgun mic for my camera", "weed control fabric",
                                  "weed brush for the patio"])
def test_a_tool_holding_a_harmful_word_isnt_refused(text):
    assert classify(text).message != HARMFUL_MESSAGE


@pytest.mark.parametrize("text", ["best gun for home defense", "weed grinder that lasts", "a good bong",
                                  "pepper spray for running", "best vape for beginners"])
def test_harmful_items_are_still_refused(text):
    assert classify(text).message == HARMFUL_MESSAGE


# --- The open model's answer: never a word the rules set aside ---

def test_a_word_the_model_takes_from_a_set_aside_name_isnt_used():
    # Asked about "tomato knife", the model may answer "knife": that word is the chef knife's, but the request named
    # a tomato knife, which the rules set aside. The rules' question stands rather than chef knives.
    for text, answer in (("tomato knife", {"category": "kitchen", "product": "knife"}),
                         ("oyster knife for shucking", {"category": "tools", "product": "knife"}),
                         ("ipad case for kids", {"category": "tech", "product": "ipad"}),
                         ("guitar strings", {"category": "hobbies", "product": "guitar"})):
        query = parse_query(text, model=FakeModel(answer))
        assert query.product_type not in ("chef knife", "tablet", "guitar"), text
        assert query.status == "clarify", text


def test_the_whole_set_aside_name_from_the_model_is_used():
    query = parse_query("ipad case for kids", model=FakeModel({"category": "tech", "product": "ipad case"}))
    assert (query.status, query.category, query.product_type, query.department) == ("ok", "general", "ipad case",
                                                                                     "tech")
    assert query.subreddits == list(GENERAL_DEPARTMENTS["tech"]["communities"])
    query = parse_query("tomato knife", model=FakeModel({"category": "kitchen", "product": "tomato knife"}))
    assert (query.status, query.category, query.product_type) == ("ok", "kitchen", "tomato knife")


def test_the_model_is_still_asked_about_what_the_rules_set_aside():
    model = FakeModel({"category": "hobbies", "product": "guitar pedal"})
    query = parse_query("guitar pedal for a beginner", model=model)
    assert model.asked == ["guitar pedal for a beginner"]
    assert (query.category, query.product_type, query.department) == ("general", "guitar pedal", "hobbies")
