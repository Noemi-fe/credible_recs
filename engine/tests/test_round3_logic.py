"""Round 3 of the convergence, the logic builder (19 Oct 2026; docs/bfs-2026-10-17/final-review.md, the last review of
the answers before the interviews and the blind test): each problem fixed within Noemi's decided rules.

1. Her feature rule (decision 1 of 16 Oct 2026) holds: a thread asks for a feature by its title, never by a post's
   passing words (a uni laptop thread whose post says its writer games on a desktop); and in a feature answer a voice
   counts as talking about the feature only when it praises its product for it, so the reason never counts voices
   "about stainless steel" beside the note saying none praised a pick for it.
2. A voice saying the opposite of a feature or need never counts as talking about it (config.OPPOSITE_QUOTE_PATTERNS:
   open-ear headphones for noise cancelling; a bottle that isn't insulated for keeping drinks cold), nor a product
   whose own name says the opposite (config.FEATURE_OPPOSITE_NAMES: an "Open" design for noise cancelling).

Every thread, writer, comment and link here is made up.
"""

import pytest

from engine import config, pipeline
from engine.features import praised_for, request_features, thread_asks_for
from engine.answer import write_answer
from engine.models import Thread
from engine.rank import rank_products
from engine.needs import judged_needs
from engine.query import parse_query
from engine.tests.factories import make_comment, make_thread
from engine.tests.ranking_factories import bodies_for, mention, mentions, note


def general_thread(title: str, body: str = "") -> Thread:
    return Thread.model_validate(make_thread(id="1fake9", title=title, body=body, category="general",
                                             community="BuyItForLife", comments=[make_comment("c9aaaa", "1fake9")]))


def feature(request: str):
    found = request_features(parse_query(request, model=None))
    assert len(found) == 1
    return found[0]


# --- 1. Her feature rule ---

def test_a_thread_asks_for_a_feature_by_its_title_never_by_its_posts_passing_words():
    # Found in the final review (19 Oct 2026): "gaming laptop under £1000" showed Apple's laptop line first, praised for
    # gaming by a uni laptop thread whose post said its writer games on a desktop; no writer talked about gaming.
    gaming = feature("gaming laptop under £1000")
    assert not thread_asks_for(general_thread("MacBook or ThinkPad for a uni student?",
                                              "I do my gaming on a desktop PC at home, so this is for lectures."), gaming)
    assert thread_asks_for(general_thread("Best gaming laptop under 1000?"), gaming)
    assert thread_asks_for(general_thread("Laptop for gaming and uni?"), gaming)


def test_in_a_feature_answer_only_a_voice_praising_its_product_for_it_talks_about_the_feature():
    # Found in the final review: "stainless steel pan for searing" said no pick was praised for stainless steel, yet its
    # reasons counted voices "about stainless steel": they praised stainless pans in general, then named a non-stick one.
    query = parse_query("stainless steel pan for searing", model=None)
    needs, features = judged_needs(query), request_features(query)
    body = "Stainless steel is what you want for searing. For eggs, though, a Brightmoor non-stick is handy."
    assert "stainless steel" not in pipeline._needs_talked_about(
        "For eggs, though, a Brightmoor non-stick is handy.", body, needs, (), features=features, praised=())
    assert "stainless steel" in pipeline._needs_talked_about(
        "Stainless steel is what you want.", body, needs, (), features=features, praised=("stainless steel",))
    # A warning keeps what it talks about: its words about the feature are what it warns of.
    assert "stainless steel" in pipeline._needs_talked_about(
        "My stainless steel pan warped.", body, needs, (), stance="warn", features=features, praised=())
    # Its other needs are untouched.
    assert "searing" in pipeline._needs_talked_about(
        "Great for searing.", "Great for searing steaks.", needs, (), features=features, praised=())


# --- 2. A voice saying the opposite ---

def test_an_open_ear_design_is_never_praised_for_noise_cancelling_even_in_a_thread_asking_for_it():
    noise = feature("noise cancelling headphones")
    # The writer's own words say the opposite: open ear, bone conduction, hearing the traffic.
    for text in ("for walks i prefer an open ear design like these.",
                 "these bone conduction ones are great on runs.",
                 "you can hear the traffic around you, which i like on my bike."):
        assert not praised_for(noise, text, ("Sonicwave Run",), thread_asks=True)
    # Nor a product whose own name says it is an open design, whatever its writer says.
    assert not praised_for(noise, "they block out the bus noise nicely.", ("Sonicwave OpenRun 2",))
    assert not praised_for(noise, "great on flights.", ("Sonicwave Open Fit",), thread_asks=True)
    # Praise as before for the rest.
    assert praised_for(noise, "the noise cancelling on these is superb.", ("Sonicwave QC9",))
    assert praised_for(noise, "great on flights.", ("Sonicwave QC9",), thread_asks=True)


def test_a_recommendation_saying_its_bottle_isnt_insulated_doesnt_talk_about_keeping_drinks_cold():
    query = parse_query("water bottle that keeps drinks cold", model=None)
    needs = judged_needs(query)
    body = "It isn't insulated, so it won't keep your drinks cold, but it is indestructible."
    own = body.lower()
    assert "cold" not in pipeline._needs_talked_about("It is indestructible.", body, needs, (), own_text=own)
    # Without the opposite said, the need counts as before.
    plain = "It keeps my drinks cold all day."
    assert "cold" in pipeline._needs_talked_about(plain, plain, needs, (), own_text=plain.lower())
    # A warning keeps it: not keeping drinks cold is what it warns of.
    assert "cold" in pipeline._needs_talked_about("It won't keep drinks cold.", body, needs, (), stance="warn",
                                                  own_text=own)


def test_the_opposite_patterns_are_config_values_as_for_the_other_asks():
    assert config.OPPOSITE_QUOTE_PATTERNS["noise cancelling"]
    assert config.OPPOSITE_QUOTE_PATTERNS["cold"]
    assert "open" in config.FEATURE_OPPOSITE_NAMES["noise cancelling"]


# --- 3. No tip, Look for, Avoid or Skip these entry says the opposite of a pick, its model or the requested form ---

def kinds_shown(answer) -> list[str]:
    return [kind for item in answer.look_for for kind in item.kind.split(" or ")]


def test_an_avoid_naming_a_picks_own_kind_in_the_types_words_is_left_out():
    # Found in the final review: the oil-cleanser answers said "Avoid: oil cleanser" and "Avoid: balm" above an oil
    # cleanser and a cleansing balm pick. Both kinds are named in the type's own words (a cleansing oil and a cleansing
    # balm are cleansers), which the 17 Oct check of a pick's kind didn't read.
    items = (mentions(3, "Glowmist Speedy oil cleanser", category="skincare")
             + mentions(3, "Fernleaf Clean cleansing balm", category="skincare")
             + mentions(3, "Dewdrop Gel Cleanser", category="skincare"))
    notes = [note("oil cleanser", "t1", stance="warn", quote="Oil cleansers broke me out every single time."),
             note("oil cleanser", "t2", stance="warn", quote="Every oil cleanser I tried broke me out."),
             note("balm", "t1", stance="warn", quote="A balm always left a film on my skin."),
             note("balm", "t2", stance="warn", quote="Each balm I used left a film."),
             note("micellar water", "t1", quote="Micellar water is a gentle first cleanse."),
             note("micellar water", "t2", quote="Micellar water works well as a first cleanse.")]
    ranking = rank_products(items, "skincare", notes, {})
    answer = write_answer(ranking, bodies_for(*items, *notes), "cleanser", request="cleanser for oily skin")
    assert {pick.name for pick in answer.picks} == {"Glowmist Speedy oil cleanser", "Fernleaf Clean cleansing balm",
                                                    "Dewdrop Gel Cleanser"}
    shown = kinds_shown(answer)
    assert "oil cleanser" not in shown and "balm" not in shown
    assert "micellar water" in shown
    # Without such a pick, the warning stays.
    others = mentions(3, "Dewdrop Gel Cleanser", category="skincare") + mentions(3, "Mossy Foam", category="skincare")
    ranking = rank_products(others, "skincare", notes, {})
    assert "oil cleanser" in kinds_shown(write_answer(ranking, bodies_for(*others, *notes), "cleanser",
                                                      request="cleanser for oily skin"))


def test_a_look_for_is_left_out_when_the_same_kinds_avoid_agrees_with_what_the_request_asks_to_be_without():
    # Found in the final review: both white-cast sunscreen answers said to look for mineral sunscreen and to avoid
    # mineral SPFs, whose warnings are about their white cast. Avoiding it agrees with the request; looking for it doesn't.
    items = mentions(3, "Sunmoss Watery Gel", category="skincare") + mentions(3, "Ricepaper Sun", category="skincare")
    notes = [note("mineral sunscreen", "t1", quote="A mineral sunscreen never stings my eyelids."),
             note("mineral sunscreen", "t2", quote="I like a mineral sunscreen on sensitive days."),
             note("mineral sunscreen", "t3", quote="Mineral sunscreen never stings me."),
             note("mineral SPFs", "t1", stance="warn", quote="Mineral SPFs leave a white cast on me."),
             note("mineral SPFs", "t2", stance="warn", quote="Every mineral SPF gave me a white cast.")]
    ranking = rank_products(items, "skincare", notes, {})
    shown = kinds_shown(write_answer(ranking, bodies_for(*items, *notes), "sunscreen", asks=("no white cast",),
                                     request="sunscreen that doesn't leave a white cast"))
    assert "mineral SPFs" in shown
    assert "mineral sunscreen" not in shown
    # Without that ask, the stronger advice keeps its line as before.
    shown = kinds_shown(write_answer(ranking, bodies_for(*items, *notes), "sunscreen", request="sunscreen"))
    assert "mineral sunscreen" in shown


def test_a_look_for_naming_the_opposite_of_the_requested_form_is_left_out():
    # "Look for: corded drill" in a cordless drill answer: a corded drill is no cordless one (config.
    # FEATURE_OPPOSITE_NAMES, her decision 1 of 16 Oct 2026's list).
    items = mentions(3, "Boltco drill", category="general") + mentions(3, "Torqueline drill", category="general")
    notes = [note("corded drill", "t1", quote="A corded drill will outlast any battery one."),
             note("corded drill", "t2", quote="Get a corded drill if you can."),
             note("impact driver", "t1", quote="An impact driver drives screws far better than a drill."),
             note("impact driver", "t2", quote="I use my impact driver more than my drill.")]
    ranking = rank_products(items, "general", notes, {})
    shown = kinds_shown(write_answer(ranking, bodies_for(*items, *notes), "drill", request="cordless drill"))
    assert "corded drill" not in shown
    shown = kinds_shown(write_answer(ranking, bodies_for(*items, *notes), "drill", request="drill"))
    assert "corded drill" in shown


def skipped(n_warn: int, product: str, **kwargs):
    return (mentions(n_warn, product, stance="warn", evidence="short-term use", **kwargs)
            + mentions(1, product, **kwargs))


def test_skip_these_never_names_a_shown_picks_model_or_an_item_shown_above():
    # Found in the final review: running shoes skipped "Adrenaline" while showing the Brooks line with its Adrenaline as
    # the most named model; the mouse answer listed the G502 under Skip these and the G502 wireless under Also worth a
    # look.
    items = (mentions(4, "Strideco running shoes line", category="general")
             + mentions(3, "Featherfoot running shoes", category="general")
             + mentions(3, "Archway running shoes", category="general")
             + mentions(2, "Glidex G502 wireless", category="general")
             + skipped(3, "Adrenaline", category="general")
             + skipped(3, "G502", category="general")
             + skipped(3, "Clunker 9", category="general"))
    ranking = rank_products(items, "general", [], {})
    key = ranking.products[0].key
    answer = write_answer(ranking, bodies_for(*items), "running shoes",
                          models={key: "Strideco Adrenaline GTS"}, request="running shoes")
    assert answer.picks[0].model == "Strideco Adrenaline GTS"
    assert "Glidex G502 wireless" in [item.name for item in answer.worth_a_look]
    assert [item.name for item in answer.skip] == ["Clunker 9"]


# --- 4. Tips about another appliance, another use, DIY electrics or batteries ---

def test_a_kitchen_tip_naming_another_appliance_is_left_out_and_cookware_alternatives_stay():
    # Found in the final review: a pressure cooker in the dutch oven answers, a food processor in the blender ones, rice
    # cookers in the saucepan ones. Round 2 left another type's tips out of general answers; kitchen kept its exception
    # (another kind of cookware is a real alternative: "Look for: cast iron" for a saucepan), and keeps it here.
    items = mentions(3, "Ironhearth Dutch oven", category="kitchen") + mentions(3, "Bluecast Dutch oven",
                                                                              category="kitchen")
    notes = [note("pressure cooker", "t1", quote="A pressure cooker does beans in half the time."),
             note("pressure cooker", "t2", quote="Our pressure cooker gets far more use than anything."),
             note("cheap rice cookers", "t1", quote="A cheap rice cooker has worked for years."),
             note("cheap rice cookers", "t2", quote="Cheap rice cookers are all you need."),
             note("cast iron", "t1", quote="Plain cast iron is tougher than enamel."),
             note("cast iron", "t2", quote="Bare cast iron lasts for generations.")]
    ranking = rank_products(items, "kitchen", notes, {})
    shown = kinds_shown(write_answer(ranking, bodies_for(*items, *notes), "dutch oven", request="dutch oven"))
    assert "pressure cooker" not in shown and "cheap rice cookers" not in shown
    assert "cast iron" in shown


def test_a_general_tip_naming_another_appliance_or_another_use_is_left_out():
    # Found in the final review: a heat pump water heater in the dehumidifier answers; a Windows laptop for accounting
    # in the gaming and university laptop answers.
    items = mentions(3, "Dampex dehumidifier", category="general") + mentions(3, "Dryroom dehumidifier",
                                                                              category="general")
    notes = [note("a hybrid heat pump water heater", "t1", quote="Our hybrid heat pump water heater dries the basement too."),
             note("a hybrid heat pump water heater", "t2", quote="A hybrid heat pump water heater pulls water from the air."),
             note("crawl space dehumidifier", "t1", quote="A crawl space dehumidifier works in any room."),
             note("crawl space dehumidifier", "t2", quote="Crawl space dehumidifiers are built to last.")]
    ranking = rank_products(items, "general", notes, {})
    shown = kinds_shown(write_answer(ranking, bodies_for(*items, *notes), "dehumidifier", request="dehumidifier"))
    assert "a hybrid heat pump water heater" not in shown
    assert "crawl space dehumidifier" in shown

    laptops = mentions(3, "Keystone laptop line", category="general") + mentions(3, "Northpad laptop",
                                                                                 category="general")
    notes = [note("Windows laptop for accounting", "t1", quote="Most accounting software wants a Windows laptop."),
             note("Windows laptop for accounting", "t2", quote="For accounting you want a Windows laptop."),
             note("16GB RAM", "t1", quote="16GB RAM keeps it quick for years."),
             note("16GB RAM", "t2", quote="16GB RAM is the minimum now."),
             note("OLED laptop for better colours", "t1", quote="An OLED laptop for better colours is worth the money."),
             note("OLED laptop for better colours", "t2", quote="Get an OLED laptop for better colours.")]
    ranking = rank_products(laptops, "general", notes, {})
    shown = kinds_shown(write_answer(ranking, bodies_for(*laptops, *notes), "laptop", request="gaming laptop"))
    assert "Windows laptop for accounting" not in shown
    assert "16GB RAM" in shown
    assert "OLED laptop for better colours" in shown  # what it is good for, not someone else's use
    shown = kinds_shown(write_answer(ranking, bodies_for(*laptops, *notes), "laptop",
                                     request="laptop for accounting"))
    assert "Windows laptop for accounting" in shown


@pytest.mark.parametrize("tip, left_out", [
    ("Rewire the old plug first.", True),
    ("Make sure the metal body is properly grounded.", True),
    ("Use a GFCI socket for it.", True),
    ("Chill the batteries before charging them.", True),
    ("Keep it off the charger when you're not using it.", True),
    ("Keep the battery around 70% when stored.", True),
    ("Descale it monthly with citric acid.", False),
    ("Brush the old grounds out of the burrs.", False),  # coffee grounds, not an earth wire
    ("Rinse the filter weekly.", False),
])
def test_diy_electrical_and_battery_care_tips_are_left_out(tip, left_out):
    from engine.care_tips import is_left_out
    assert is_left_out(tip) is left_out


# --- 5. A pick's first quote names the exact product, doesn't open negatively and doesn't swear ---

def first_quotes(product: str, quotes: list[tuple[str, str]], category: str = "general") -> list[str]:
    """The quotes shown for a pick whose credible recommendations say these (quote, the writer's own name for it), the
    most credible first (each a little less weighty than the one before), beside a second product."""
    items = [mention(product, f"t{i % 2 + 1}", quote=text, written_as=written, category=category,
                     weight=3.0 - i * 0.1) for i, (text, written) in enumerate(quotes)]
    others = mentions(3, "Other Brand Thing", category=category, weight=0.5)
    ranking = rank_products(items + others, category, [], {})
    answer = write_answer(ranking, bodies_for(*items, *others), None, request="anything")
    pick = next(p for p in answer.picks if p.name == product)
    return [quote.text for quote in pick.quotes]


def test_a_quote_that_swears_comes_after_a_clean_one():
    shown = first_quotes("Boomco Clip", [("The Boomco Clip is fucking indestructible, three years of camping trips.",
                                          "Boomco Clip"),
                                         ("My Boomco Clip has survived three summers at the beach.", "Boomco Clip"),
                                         ("The Boomco Clip is loud for its size and never died.", "Boomco Clip")])
    assert "fucking" not in shown[0]


def test_a_quote_opening_negatively_comes_after_one_that_doesnt():
    shown = first_quotes("Panmaster saucepan line", [
        ("Ignore everyone pushing Panmaster here, lovely pans but you can barely buy them now.", "Panmaster"),
        ("Can't recommend my Panmaster now that the line is discontinued, though it served me well.", "Panmaster"),
        ("My Panmaster saucepans have cooked daily for twelve years without a mark.", "Panmaster")], "kitchen")
    assert shown[0].startswith("My Panmaster saucepans")


def test_a_quote_about_a_sibling_product_or_naming_it_as_a_yardstick_comes_after_one_about_the_product():
    # Found in the final review: a Cetaphil cleanser pick's first quote praised another Cetaphil cleanser; an office
    # chair pick's praised another chair as comfortable as it.
    shown = first_quotes("Dermalux Gentle Skin Cleanser", [
        ("Love the Dermalux Clear Acne Wash, it keeps my chin calm.", "Dermalux Clear Acne Wash"),
        ("I've used the Dermalux Gentle Skin Cleanser for two years and my skin is calm.",
         "Dermalux Gentle Skin Cleanser"),
        ("The Dermalux gentle cleanser never stings.", "Dermalux gentle cleanser")], "skincare")
    assert shown[0].startswith("I've used the Dermalux Gentle")
    shown = first_quotes("Seatwell Aeron", [
        ("Honestly these feel every bit as comfy as the Seatwell Aeron I sat on for years.", "Seatwell Aeron"),
        ("My Seatwell Aeron is ten years old and still perfect for my back.", "Seatwell Aeron"),
        ("The Seatwell Aeron fixed my back pain within a month.", "Seatwell Aeron")])
    assert shown[0].startswith("My Seatwell Aeron")


# --- 6. No "Price not checked yet" beside "Not sold in the UK" ---

def test_a_product_not_sold_in_the_uk_shows_no_price_not_checked_line():
    from datetime import date

    from engine.answer import PRICE_UNKNOWN
    from engine.prices import Price, PriceCheck

    items = mentions(3, "Prairie skillet", category="kitchen") + mentions(3, "Moorland skillet", category="kitchen")
    ranking = rank_products(items, "kitchen", [], {})
    abroad = Price(product="Prairie skillet", category="kitchen", price=None, currency="GBP", shop="Made-up US Shop",
                   url="https://shop.example/prairie", checked_on=date(2026, 10, 18), available=False, not_in_uk=True)
    key = next(p.key for p in ranking.products if p.name == "Prairie skillet")
    answer = write_answer(ranking, bodies_for(*items), "frying pan",
                          prices={key: PriceCheck(price=None, status="no budget", availability=abroad)})
    picks = {pick.name: pick for pick in answer.picks}
    assert picks["Prairie skillet"].availability.text.startswith("Not sold in the UK")
    assert picks["Prairie skillet"].price.text == ""
    assert picks["Moorland skillet"].price.text == PRICE_UNKNOWN  # not checked at all: said as before


def test_the_page_shows_no_empty_price_line_and_says_not_sold_at_a_glance():
    from engine.web import search_page

    html = search_page().decode("utf-8")
    assert "if (!price.text && !price.budget_note) return [];" in html
    assert 'glanceNotSold: "Not sold in the UK"' in html


# --- 7. The demo, interviewee and blind-test requests are checked ahead first ---

def test_the_plan_works_out_the_demo_and_interviewee_requests_beside_the_blind_test_ones(tmp_path):
    import json

    from engine import precheck

    questions = tmp_path / "questions.json"
    questions.write_text(json.dumps({"questions": [{"text": "blind one"}, {"text": "blind two"}]}), encoding="utf-8")
    demo = tmp_path / "demo.json"
    demo.write_text(json.dumps({"demo": ["demo one", "blind two"], "interviewee": ["asked one", "demo one"]}),
                    encoding="utf-8")
    latency = tmp_path / "latency.json"
    latency.write_text(json.dumps({"queries": [{"text": "latency one"}]}), encoding="utf-8")
    found = precheck.requests_to_check(questions, latency, tmp_path, tmp_path / "none.json", demo)
    # In the plan's list (each once; their place there doesn't decide what is read first: Candidate.first does).
    assert found[:3] == ["blind one", "blind two", "latency one"] and found[-2:] == ["demo one", "asked one"]
    assert precheck.first_requests(questions, demo) == {"blind one", "blind two", "demo one", "asked one"}


def test_their_shown_and_next_in_line_quotes_are_read_before_any_other_requests():
    from engine.precheck import Candidate, merged

    def candidate(url: str, tier: int, request: int, first: bool) -> Candidate:
        return Candidate(url, url, (f"quote of {url}",), tier, 0, request, 0, first)

    found = merged([candidate("other-shown", 0, 0, False), candidate("demo-next", 1, 5, True),
                    candidate("demo-shown", 0, 4, True), candidate("demo-behind", 2, 4, True),
                    candidate("other-next", 1, 0, False)])
    assert [c.url for c in found] == ["demo-shown", "demo-next", "other-shown", "other-next", "demo-behind"]


def test_the_shipped_list_holds_the_demo_and_interviewee_requests_and_the_plan_stays_inside_its_bound():
    import json

    from engine import precheck

    data = json.loads(precheck.DEMO_FILE.read_text(encoding="utf-8"))
    assert "gaming laptop under £1000" in data["demo"] and "stainless steel pan for searing" in data["interviewee"]
    requests = precheck.requests_to_check()
    assert set(data["demo"]) | set(data["interviewee"]) <= set(requests)
    # The plan's working out grows with its requests (486 took about 5 minutes on Noemi's computer, the model off; 18
    # Oct 2026): a bound well inside the job's task timeout, which the free-tier sums count (test_cloudrun.py).
    assert len(requests) <= config.PLAN_MAX_REQUESTS
