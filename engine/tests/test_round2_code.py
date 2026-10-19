"""Round 2 of the convergence, the code builder (18 Oct 2026; docs/bfs-2026-10-17/round2-additions.md and the
orchestrator's list): what round 1's answers showed wrong, each fixed where a rule of Noemi's supports it.

- "What to look for" shows only tips about the product asked for: in a general answer, a note from a thread whose
  products the AI typed mostly as another type ("a dog bed thread read for a washing machine") is another type's tip,
  unless the tip's own name names the type asked for (engine.pipeline._threads_about_another_type,
  engine.answer._look_for).
- Names: a brand-lines entry found through one of its other names shows its maker's name when that name is its short
  form or the line without its maker ("WM" is Western Mountaineering's line, "Stagg" Fellow Stagg's); no shown name is
  a bare number ("965" is the Garmin Forerunner 965 of the price list; engine.pipeline._groups_to_rank).
- Module 1: "bean to cup" is one need, which US writers call "super automatic" (config.NEEDS).
- The voice rubric's red flags: Amazon's associate short links, redirect and referral links are affiliate or referral
  links (paid promotion), and a writer linking their own site, or a review outfit's account linking its write-up of
  products it tested, promotes one brand (engine.credibility).
- The daily plan job works out its requests type by type and forgets what answers worked out between product types
  (engine.precheck._work_out, config.PLAN_ANSWERS_KEPT_TYPES).

Every thread, writer, comment and link here is made up.
"""

from datetime import date

import pytest

from engine import config, pipeline
from engine.answer import write_answer
from engine.brand_lines import BrandLine
from engine.credibility import score_voice
from engine.extract import CheckResult, ExtractedMention
from engine.group_products import ProductGroup, ProductMention
from engine.models import Thread
from engine.needs import needs_met, request_needs
from engine.features import request_features
from engine.query import parse_query
from engine.rank import rank_products
from engine.tests.factories import make_comment, make_thread
from engine.tests.ranking_factories import bodies_for, mentions, note

TODAY = date(2026, 10, 18)


# --- "What to look for": only tips about the type asked for ---

def towel_ranking():
    """A towel answer: three towels, a tip about a kind of towel from a towel thread (t1), and two tips from a yoga mat
    thread (t9): one about a kind of mat, one about a kind of towel."""
    items = (mentions(3, "Fluffco bath towel", category="general")
             + mentions(3, "Dryco towel", category="general"))
    notes = [note("waffle weave towel", "t1", quote="A waffle weave towel dries in an hour on the rail."),
             note("waffle weave towel", "t2", quote="Waffle weave towels dry fastest for me."),
             note("cork mat", "t9", quote="A cork mat stays grippy when you sweat."),
             note("cork mat", "t9", quote="Cork mats are the best I have owned."),
             note("mat towels", "t9", quote="Mat towels on top of the mat stop the slipping.")]
    return rank_products(items, "general", notes, {}), bodies_for(*items, *notes)


def test_a_tip_from_a_thread_about_another_type_is_left_out_of_a_general_answer():
    # Found in round 1's sweep (18 Oct 2026): "towels that dry fast" read a yoga mat thread (its title names "mat
    # towels") and showed "Look for: cork mat"; a washing machine answer read a dog bed thread and showed a dog bed tip.
    ranking, bodies = towel_ranking()
    shown = [item.kind for item in write_answer(ranking, bodies, "towel", other_types_threads={"t9"}).look_for]
    assert "cork mat" not in shown
    assert "waffle weave towel" in shown  # its thread is about towels
    assert "mat towels" in shown  # its own name names the type asked for, whatever its thread is about
    # Without the pipeline's word on which threads are about another type, nothing changes.
    assert "cork mat" in [item.kind for item in write_answer(ranking, bodies, "towel").look_for]


def extraction(*types: str | None) -> CheckResult:
    """A checked extraction whose kept mentions the AI typed as given (None: no type)."""
    return CheckResult(kept=[ExtractedMention(comment_id=f"m{i}", product=f"Product {i}", category="general",
                                              stance="recommend", quote=f"Product {i} is good.", product_type=t)
                             for i, t in enumerate(types)])


def thread(thread_id: str, title: str) -> Thread:
    return Thread.model_validate(make_thread(id=thread_id, title=title, category="general", community="BuyItForLife",
                                             comments=[make_comment(f"c{thread_id}", thread_id)]))


def test_a_thread_is_about_another_type_when_few_of_its_products_are_of_the_type_asked_for():
    query = parse_query("washing machine that lasts 10+ years", model=None)
    checked = {
        "w1": extraction("washing machine", "washing machine", "laundry detergent"),  # about washing machines
        "d1": extraction("dog bed", "dog bed", "dog bed", "dog bed", "laundry detergent"),  # a dog bed thread
        # A quarter of its products are washing machines (config.LOOK_FOR_TYPE_SHARE): about them too.
        "m1": extraction("washing machine", "tumble dryer", "tumble dryer", "tumble dryer"),
        "n1": extraction(),  # no products: its title decides
        "n2": extraction(None),
    }
    threads = [thread("w1", "Which washing machine lasts?"), thread("d1", "Advice on choosing my dog bed"),
               thread("m1", "Washer and dryer for a small flat"), thread("n1", "Best dog bed for an old dog?"),
               thread("n2", "Washing machine advice")]
    assert pipeline._threads_about_another_type(checked, threads, query) == {"d1", "n1"}


def test_kitchen_skincare_and_haircare_answers_keep_their_own_rules_for_another_types_advice():
    # Kitchen keeps another kind of cookware as an alternative (10 Oct 2026: "Look for: cast iron" for a non-stick pan,
    # and "Avoid: non-stick pans" in a cast iron skillet answer, whose notes come from frying pan threads); skincare and
    # haircare have their own rule (engine.answer._another_types_advice).
    checked = {"d1": extraction("frying pan", "frying pan", "frying pan")}
    threads = [thread("d1", "Best frying pan?")]
    for request in ("cast iron skillet for a beginner", "moisturiser for dry skin", "shampoo for curly hair"):
        assert pipeline._threads_about_another_type(checked, threads, parse_query(request, model=None)) == set()


# --- Names ---

def line_entry(brand: str, also_called: tuple[str, ...], product_type: str, category: str = "general") -> BrandLine:
    site = "https://maker.example"
    return BrandLine(brand=brand, also_called=list(also_called), category=category, product_type=product_type,
                     sells=True, sources=[f"{site}/range"], checked_on=TODAY, note="Made up for a test.")


def group(name: str, *names: str, category: str = "general", loose: bool = False,
          product_type: str | None = None) -> ProductGroup:
    written = names or (name,)
    return ProductGroup(key=f"{category}:{name.lower()}", name=name, category=category, loose=loose,
                        mentions=[ProductMention("t1", f"c{i}{name}", w, category, "recommend", product_type, f"{w} is good.")
                                  for i, w in enumerate(written)])


def shown(groups, request: str, lines=(), listed=()) -> tuple[list[str], pipeline.PipelineResult]:
    query = parse_query(request, model=None)
    result = pipeline.PipelineResult(query)
    kept = pipeline._groups_to_rank(groups, query, result, {"t1": request}, list(lines), listed=tuple(listed))
    return [g.name for g in pipeline._one_per_name(kept)], result


def test_a_brands_short_form_shows_its_makers_name_and_joins_its_line():
    # Round 1's sleeping bag answer listed "WM sleeping bag line" as a pick and "Western Mountaineering sleeping bag
    # line" under Also worth a look: the brand-lines entry for sleeping bags says WM is Western Mountaineering.
    lines = [line_entry("Western Mountaineering", ("WM",), "sleeping bag")]
    names, _ = shown([group("WM", "WM", "WM", loose=True),
                      group("Western Mountaineering", loose=True)], "sleeping bag", lines)
    assert names == ["Western Mountaineering sleeping bag line"]


def test_a_line_written_without_its_maker_shows_its_makers_name():
    # Writers' bare "Stagg" showed as "Stagg electric kettle line"; the entry is Fellow Stagg's.
    lines = [line_entry("Fellow Stagg", ("Stagg",), "electric kettle", "kitchen")]
    names, _ = shown([group("Stagg", "Stagg", "Stagg", category="kitchen", loose=True)], "a kettle that's quiet", lines)
    assert names == ["Fellow Stagg electric kettle line"]


def test_a_brand_written_without_the_rest_of_its_makers_name_keeps_its_writers_name():
    # "Field" is how writers name Field Company: their name for the brand itself, which a UK shopper knows too.
    lines = [line_entry("Field Company", ("Field",), "cast iron skillet", "kitchen")]
    names, _ = shown([group("Field", "Field", "Field", category="kitchen", loose=True)], "cast iron skillet", lines)
    assert names == ["Field cast iron skillet line"]


def test_a_bare_number_shows_the_full_name_of_the_listed_product_of_the_type():
    # Round 1's running watch answer showed a pick named "965".
    listed = ("Garmin Forerunner 965", "965", "Garmin Forerunner 265")
    names, _ = shown([group("965", "965", "965", "Forerunner 965", product_type="sports watch")], "running watch",
                     listed=listed)
    assert names == ["Garmin Forerunner 965"]


def test_a_bare_number_takes_the_listed_model_up_to_its_number():
    # "502" for the G502 mouse the price list writes "G502 wireless": the model, not a wireless one in particular.
    names, _ = shown([group("502", "502", "502's", product_type="mouse")], "ergonomic mouse", listed=("G502 wireless",))
    assert names == ["G502"]


def test_a_product_whose_listed_name_starts_with_its_number_shows_that_whole_name():
    names, _ = shown([group("4711", "4711", "4711", product_type="perfume")], "a perfume that lasts all day",
                     listed=("4711 Original Eau de Cologne",))
    assert names == ["4711 Original Eau de Cologne"]


def test_a_bare_number_takes_its_own_writers_fuller_name_when_no_list_has_it():
    names, _ = shown([group("742", "742", "742", "Zoomer 742", product_type="sports watch")], "running watch")
    assert names == ["Zoomer 742"]


def test_a_bare_number_nothing_names_in_full_is_left_out_as_naming_no_one_product():
    names, result = shown([group("742", "742", "742", product_type="sports watch"),
                           group("Garmin Forerunner 265", product_type="sports watch")], "running watch",
                          listed=("Garmin Forerunner 265", "Garmin Forerunner 742", "Suunto 742"))
    assert names == ["Garmin Forerunner 265"]  # two makers' 742s: the lists can't say which
    assert "742" in result.left_out_generic


# --- Module 1: bean to cup is what US writers call super automatic ---

def test_bean_to_cup_is_one_need_that_super_automatic_comments_talk_about():
    for request in ("bean to cup coffee machine", "bean-to-cup coffee machine", "super automatic espresso machine"):
        needs = request_needs(parse_query(request, model=None))
        assert [n.name for n in needs if n.request_word is None] == ["bean-to-cup"], request
    needs = request_needs(parse_query("bean to cup coffee machine", model=None))
    asked = tuple(n for n in needs if n.name == "bean-to-cup")
    for said in ("My super automatic grinds and brews at the push of a button.",
                 "A superautomatic is the easy choice.", "Our bean-to-cup machine still works."):
        assert needs_met(said, asked), said
    assert not needs_met("A manual lever machine with a separate grinder.", asked)


def test_bean_to_cup_named_before_the_machine_is_a_feature_it_ranks_by():
    # Noemi's decision 1 of 16 Oct 2026: a feature named before the product noun ranks first the products a credible
    # voice praises for it.
    features = request_features(parse_query("bean to cup coffee machine", model=None))
    assert [f.name for f in features] == ["bean to cup"]


# --- The voice rubric's red flags ---

def voice_of(body: str, name: str = "test_writer"):
    author = {"name": name, "account_created_at": "2015-01-01", "karma": 50_000, "flair": None}
    comments = [make_comment("c1aaaa", body=body, author=author, score=40, created_at="2026-09-01T10:00:00Z")]
    comments += [make_comment(f"o{i}other", body="Nice thread.", score=1, created_at="2026-09-01T10:00:00Z")
                 for i in range(4)]
    thread = Thread.model_validate(make_thread(category="kitchen", community="BuyItForLife", comments=comments,
                                               created_at="2026-09-01T10:00:00Z", collected_at="2026-10-06"))
    return score_voice(thread.comments[0], thread)


def red_flags(voice) -> dict[str, int]:
    return {sign.name: sign.red_flags for sign in voice.signs if sign.kind == "red flag"}


@pytest.mark.parametrize("link", [
    "https://amzn.to/3Abc123",  # an Amazon associate's short link
    "https://d1abcdefgh.cloudfront.net/?q=PARER0001",  # a redirect hiding the shop behind a product code
    "https://ra-sl.com/dp-B0ABCDEFGH",  # a redirect to an Amazon product
    "https://hiarthur.com/?share=1234abcd-0000-4000-8000-1234567890ab",  # a deals app's referral link
])
def test_affiliate_redirect_and_referral_links_are_paid_promotion(link):
    voice = voice_of(f"The [Parero paring knife]({link}) is great, I use it daily.")
    assert red_flags(voice) == {"salesy language": config.PAID_PROMOTION_RED_FLAGS}
    assert voice.level == "low"


@pytest.mark.parametrize("link", ["https://a.co/d/abc1234", "https://amzn.eu/d/abc1234",
                                  "https://www.amazon.co.uk/dp/B0ABCDEFGH?ref=cm_sw_r_cp"])
def test_a_shoppers_own_share_link_is_no_promotion(link):
    assert red_flags(voice_of(f"I bought [this one]({link}) and love it.")) == {}


def test_a_writer_linking_their_own_shop_promotes_one_brand():
    voice = voice_of("Buy a hand forged knife: https://www.fernforges.example/chef-knife", name="Fern_Forges")
    assert red_flags(voice) == {"promotes one brand": 1}
    assert red_flags(voice_of("Mine is from https://www.fernforges.example/chef-knife", name="kettle_fan_99")) == {}


def test_a_review_outfits_account_linking_its_write_up_of_products_it_tested_promotes_one_brand():
    body = "I finally tested 6 garlic presses side by side. Full breakdown: https://pages.example/garlic-presses"
    assert red_flags(voice_of(body, name="KitchenGearTested")) == {"promotes one brand": 1}
    # An ordinary writer whose name happens to end so, saying nothing of testing, links nothing: no flag.
    assert red_flags(voice_of("I use Eufy, it is good.", name="Honest_Dad_Reviews")) == {}
    # A tester without a review outfit's name: no flag either.
    assert red_flags(voice_of(body, name="garlic_lover")) == {}


# --- The daily plan job's memory ---

def test_the_plan_job_works_type_by_type_and_forgets_the_answers_memory_between_types(monkeypatch):
    from engine import memo, precheck

    order, forgot = [], []
    kinds = {"kettle a": "kettle", "pan a": "pan", "kettle b": "kettle", "knife a": "knife", "pan b": "pan"}
    monkeypatch.setattr(pipeline, "request_kind", lambda request: kinds[request])
    monkeypatch.setattr(memo, "forget_answers", lambda: forgot.append(len(order)))

    def answering(request, **_):
        order.append(request)
        return pipeline.PipelineResult(parse_query("electric kettle", model=None))  # no answer: nothing to check

    monkeypatch.setattr(pipeline, "answer_request", answering)
    precheck._work_out(list(kinds), library_dir=None, checker=None, profiles=None)
    assert order == ["kettle a", "kettle b", "pan a", "pan b", "knife a"]  # each type's requests together, in order
    assert forgot == [2, 4]  # before the pans and before the knife: one type's work kept at a time
    assert config.PLAN_ANSWERS_KEPT_TYPES == 1
