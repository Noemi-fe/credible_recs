"""The rest of the engine with the general category (14 Oct 2026, Noemi's plan part 1: "same credibility rules,
verified quotes and live checks for all"). Credibility is about the writer and their use, never the category, so the
same rules rank headphones as kettles; these tests check what had assumed three categories: which threads a request
reads and their category, which mentions count for it, sets that are products of their own, the warning and specialist
words, the honest answer when nothing has been read yet, and on-demand reading. Every thread, comment and name of a
writer here is made up.
"""

import json
from pathlib import Path

from engine import config
from engine.answer import unverified_claims
from engine.credibility import CATEGORY_TERMS, GENERIC_NAME_WORDS, score_voice
from engine.group_products import ProductMention
from engine.models import Thread
from engine.pipeline import PipelineResult, _names_a_set, _not_sets, answer_request
from engine.query import parse_query
from engine.sources import ArchiveSource, for_request, thread_kind, warning_words
from engine.tests.factories import make_comment, make_thread, write_gold
from engine.tests.test_archive_reader import FakeArchiveClient, search_post

HEADPHONES = "noise cancelling headphones that last"
SONY_1 = "My Sony WH-1000XM4 headphones have lasted 3 years of daily commuting."
SONY_2 = "Had the Sony WH-1000XM4 for 2 years, the noise cancelling is still great."
SONY_3 = "I've worn my Sony WH-1000XM4 on every flight for 4 years."
SONY_4 = "Two years in, my Sony WH-1000XM4 still holds a charge for days."
BOSE_1 = "The Bose QC45 headband cracked after 5 months, avoid them."
BOSE_2 = "My Bose QC45 broke within a year, the hinge snapped."
ZOJI = "My Zojirushi kettle has lasted 6 years."


def comment(comment_id: str, thread_id: str, body: str, subreddit: str = "headphones") -> dict:
    return make_comment(comment_id, thread_id=thread_id, body=body,
                        url=f"https://www.reddit.com/r/{subreddit}/comments/{thread_id}/comment/{comment_id}/")


def headphone_thread(thread_id: str, subreddit: str, comments: list[dict], title="Best noise cancelling headphones?"):
    return make_thread(id=thread_id, community=subreddit, category="general", title=title,
                       body="Mine broke again.", url=f"https://www.reddit.com/r/{subreddit}/comments/{thread_id}/x/",
                       comments=comments)


def mention(comment_id: str, product: str, quote: str, stance: str = "recommend", category: str = "general",
            product_type: str = "headphones") -> dict:
    return {"comment_id": comment_id, "product": product, "category": category, "product_type": product_type,
            "stance": stance, "evidence": "long-term use", "evidence_tags": ["long-term use"], "quote": quote}


def general_library(tmp_path: Path, version: str = "extract-v12") -> Path:
    """Two headphone threads (r/headphones and the shared r/BuyItForLife): the Sony praised four times across both,
    the Bose warned against twice, a kettle praised in passing."""
    threads = [
        headphone_thread("1head01", "headphones", [
            comment("h1aaaa", "1head01", SONY_1), comment("h1bbbb", "1head01", SONY_2),
            comment("h1cccc", "1head01", BOSE_1), comment("h1dddd", "1head01", ZOJI)]),
        headphone_thread("1head02", "BuyItForLife", [
            comment("h2aaaa", "1head02", SONY_3, "BuyItForLife"), comment("h2bbbb", "1head02", SONY_4, "BuyItForLife"),
            comment("h2cccc", "1head02", BOSE_2, "BuyItForLife")], title="Headphones that last?"),
    ]
    root = write_gold(tmp_path / "library", threads, voices=None, mentions=None)
    extractions = {
        "1head01": [mention("h1aaaa", "Sony WH-1000XM4", SONY_1), mention("h1bbbb", "Sony WH-1000XM4", SONY_2),
                    mention("h1cccc", "Bose QC45", BOSE_1, "warn"),
                    mention("h1dddd", "Zojirushi kettle", ZOJI, category="kitchen", product_type="electric kettle")],
        "1head02": [mention("h2aaaa", "Sony WH-1000XM4", SONY_3), mention("h2bbbb", "Sony WH-1000XM4", SONY_4),
                    mention("h2cccc", "Bose QC45", BOSE_2, "warn")],
    }
    (root / "extracted").mkdir()
    for thread_id, mentions in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": version, "extracted_at": "2026-10-14T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions,
        }), encoding="utf-8")
    return root


# --- End to end ---

def test_a_general_request_comes_back_as_picks_with_verified_quotes(tmp_path):
    result = answer_request(HEADPHONES, library_dir=general_library(tmp_path))
    assert (result.query.category, result.query.department) == ("general", "tech")
    assert sorted(result.threads_used) == ["1head01", "1head02"]
    assert [pick.name for pick in result.answer.picks][:1] == ["Sony WH-1000XM4"]
    assert "Bose QC45" not in [pick.name for pick in result.answer.picks]
    assert unverified_claims(result.answer, result.bodies) == []
    assert "Zojirushi kettle" not in [p.name for p in result.ranking.products]  # another category's product


def test_a_general_request_with_no_threads_yet_says_so_honestly(tmp_path):
    result = answer_request("robot vacuum for pet hair", library_dir=general_library(tmp_path))
    assert result.query.status == "ok" and result.threads_available == 0 and result.answer.picks == []
    assert result.answer.message == "We haven't read any Reddit threads about robot vacuums yet, so there's nothing " \
                                    "to recommend from. We'd rather say so than guess."


def test_a_mention_typed_as_one_of_module_1s_types_counts_in_that_types_category(tmp_path):
    # The AI may call a water bottle kitchen gear; module 1 says it's the general category's (14 Oct 2026).
    threads = [headphone_thread(f"1bott0{n}", "BuyItForLife",
                                [comment(f"b{n}{c}aaaa", f"1bott0{n}", f"My Hydro Flask water bottle has lasted {n + c} years.",
                                         "BuyItForLife") for c in (1, 2)], title="Water bottle that lasts?")
               for n in (1, 2)]
    root = write_gold(tmp_path / "library", threads, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for thread in threads:
        mentions = [mention(c["id"], "Hydro Flask water bottle", c["body"], category="kitchen",
                            product_type="water bottle") for c in thread["comments"]]
        (root / "extracted" / f"{thread['id']}.json").write_text(json.dumps({
            "thread_id": thread["id"], "instructions_version": "extract-v12", "extracted_at": "2026-10-14T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions}), encoding="utf-8")
    result = answer_request("water bottle that lasts", library_dir=root)
    assert [p.name for p in result.answer.picks] == ["Hydro Flask water bottle"]


# --- Which threads, and their category ---

def test_a_thread_from_a_community_two_categories_share_takes_the_requests_category():
    # r/BuyItForLife is the kitchen's and the general category's: a thread read for headphones is a general thread.
    posts = [search_post("1bifl01", "Headphones that last?", 120, "BuyItForLife"),
             search_post("1head01", "Best noise cancelling headphones?", 300, "headphones")]
    client = FakeArchiveClient(posts)
    threads = ArchiveSource(client).find_raw_threads(parse_query(HEADPHONES), limit=2)
    assert {t.id: t.category for t in threads} == {"1head01": "general", "1bifl01": "general"}
    kettle = parse_query("electric kettle that lasts 10+ years")
    assert for_request(threads[0].model_copy(update={"category": "kitchen"}), kettle).category == "kitchen"


def test_a_thread_keeps_its_category_when_its_community_isnt_the_requests():
    thread = Thread.model_validate(make_thread(category="skincare", community="acne",
                                               url="https://www.reddit.com/r/acne/comments/1fake01/x/"))
    assert for_request(thread, parse_query(HEADPHONES)).category == "skincare"


def test_a_general_threads_warnings_are_failures_in_plain_words():
    query = parse_query(HEADPHONES)
    assert thread_kind({"title": "My headphones broke after 6 months"}, "general", "headphones") == "warning"
    assert thread_kind({"title": "Headphones died within a year, regret buying"}, "general", "headphones") == "warning"
    assert thread_kind({"title": "Best headphones for the gym?"}, "general", "headphones") == "advice"
    assert warning_words(query) == ("died", "broke", "regret", "avoid")


# --- Sets of a product are products when they are a type of their own ---

def test_a_type_whose_name_ends_with_a_set_word_is_a_product_not_a_set():
    for product_type in ("sleeping bag", "down sleeping bag", "punching bag", "tool set", "phone case", "tv stand",
                         "squat rack", "duvet cover", "drum kit"):
        assert not _names_a_set(product_type), product_type
    for product_type in ("knife set", "knife block", "lego set", "bike rack"):
        assert _names_a_set(product_type), product_type


def test_a_type_with_a_set_word_is_spared_only_in_its_own_request():
    # 14 Oct 2026 (found merging main, comparing every answer's JSON): in a chef knife request a "knife sharpener"
    # mention is left out before grouping, as before the taxonomy made the knife sharpener a type of its own; kept,
    # its "Rada sharpener" had made "Rada" a brand of two products, and the knife answer counted one brand line more.
    assert _names_a_set("knife sharpener", "chef knife")
    assert _names_a_set("sleeping bag", "tent")
    assert not _names_a_set("knife sharpener", "knife sharpener")
    assert not _names_a_set("down sleeping bag", "sleeping bag")
    result = PipelineResult(parse_query("first chef's knife under £100 for a home cook"))
    mentions = [ProductMention("t1", "c1", "Rada Knives", "kitchen", "recommend", "chef knife"),
                ProductMention("t1", "c1", "Rada sharpener", "kitchen", "recommend", "knife sharpener")]
    assert [m.product for m in _not_sets(mentions, result, "chef knife")] == ["Rada Knives"]
    assert result.left_out_as_other_type == ["Rada sharpener"]


# --- Credibility: the same rules, the general category's specialist words ---

def test_the_general_category_has_specialist_words_for_enthusiasts():
    assert {"soundstage", "goodyear welt", "base weight", "keycaps"} <= set(CATEGORY_TERMS["general"])
    thread = Thread.model_validate(headphone_thread("1head09", "headphones", [comment(
        "h9aaaa", "1head09", "The soundstage is wide, the planar drivers are fast and the dac pairs well.")]))
    voice = score_voice(thread.comments[0], thread)
    assert any(sign.name == "enthusiast" for sign in voice.signs)


def test_a_general_types_own_word_doesnt_pick_out_one_product():
    # "headphones" in "Sony headphones" says what it is, not which one (module 5's sentences per product).
    assert {"headphones", "earbuds", "vacuum", "mattress", "boots", "backpack"} <= GENERIC_NAME_WORDS


def test_the_general_categorys_extractions_need_v12():
    assert set(config.EXTRACT_STILL_CURRENT["extract-v12"]["extract-v11"]) == {"skincare", "kitchen", "haircare"}


def test_a_thread_read_again_through_parse_keeps_the_category_it_was_saved_in(tmp_path):
    from engine import library
    from engine.tests.test_library import NOW, OLD, FakeParseClient, kettle_thread, library_with, saved

    folder = library_with(tmp_path, kettle_thread("1old", collected_at=OLD, category="general",
                                                  title="Headphones that last?"))
    client = FakeParseClient(threads=[kettle_thread("1old", collected_at=NOW, title="Headphones that last?")])  # kitchen
    library.refresh(client, folder, now=NOW)
    assert saved(folder)["1old"].category == "general"


# --- On-demand reading of a general product ---

def test_a_general_request_is_queued_with_its_category_and_communities():
    from engine.on_demand import entry_for

    entry = entry_for(parse_query("robot vacuum for pet hair"), had=0)
    assert (entry.category, entry.product_type) == ("general", "robot vacuum")
    assert entry.subreddits[0] == "VacuumCleaners" and entry.needs == ["pet"]  # "hair" is a filler word of requests
    query = entry.query()  # the job reads it back as module 2 does
    assert (query.category, query.product_type, query.subreddits) == ("general", "robot vacuum", entry.subreddits)


def test_a_product_the_open_model_named_is_queued_with_its_departments_communities():
    from engine.on_demand import entry_for
    from engine.tests.test_query_general import FakeModel

    query = parse_query("eyelash curler that doesn't pinch", model=FakeModel({"category": "beauty",
                                                                               "product": "eyelash curler"}))
    entry = entry_for(query, had=0)
    assert entry.subreddits == list(config.GENERAL_DEPARTMENTS["beauty"]["communities"])
    assert entry.query().product_type == "eyelash curler"


# --- What the page shows: the department above the answer ---

def test_the_api_says_a_general_requests_department(tmp_path):
    from engine.tests.test_web import ask

    status, _, data = ask(HEADPHONES, general_library(tmp_path))
    assert status == 200 and (data["query"]["category"], data["query"]["department"]) == ("general", "tech")
    assert data["answer"]["picks"][0]["name"] == "Sony WH-1000XM4"
    _, _, kettle = ask("electric kettle that lasts 10+ years", general_library(tmp_path / "other"))
    assert kettle["query"]["department"] is None


def test_the_page_names_every_category_and_department_as_config_does():
    import re

    from engine.web import PAGE_TEMPLATE

    page = PAGE_TEMPLATE.read_text(encoding="utf-8")
    departments = re.search(r"departments: \{(.*?)\}", page).group(1)
    for key, entry in config.GENERAL_DEPARTMENTS.items():
        assert f'{key}: "{entry["label"]}"' in departments, key
    assert re.search(r'categories: \{[^}]*general: "', page)
    assert "answerHead(title, query" in page and "LABELS.departments[query.department]" in page


def test_the_page_no_longer_says_it_covers_three_categories_only():
    from engine.web import PAGE_TEMPLATE

    page = PAGE_TEMPLATE.read_text(encoding="utf-8")
    assert "Three picks for skincare, haircare and kitchen gear" not in page
    assert "outside skincare and kitchen" not in page


def test_the_how_page_says_what_module_1_turns_away():
    from engine.how_page import METRIC_WORDING

    words = METRIC_WORDING["request_outcome"][1]
    assert "outside skincare, haircare and kitchen gear" not in words and "a product we recommend" in words


def test_on_demand_reading_keeps_a_general_requests_threads_in_the_general_category(tmp_path, monkeypatch):
    # The job reads from the archive, whose reader names a thread's category by its community: r/BuyItForLife's is the
    # kitchen's first. A thread read there for headphones must be a general thread, or answers would never read it.
    from engine.tests import on_demand_fakes
    from engine.tests.test_on_demand_job import queued, run, the_bundle
    from engine.tests.fake_google import FakeGoogle

    monkeypatch.setattr(on_demand_fakes, "TEAPOT_THREADS", {
        "1head07": ("BuyItForLife", "Which headphones last for years?", [
            ("h7a", "My Sennheiser headphones have lasted 9 years.", "Sennheiser HD 600")]),
        "1head08": ("headphones", "Headphones that survive daily commuting?", [
            ("h8a", "Sony headphones, 4 years of daily commuting so far.", "Sony WH-1000XM4")]),
    })
    google = FakeGoogle()
    queued(google, "headphones that last")
    run(tmp_path, google, fake_archive=on_demand_fakes.FakeArchive(threads=("1head07", "1head08")))
    bundle = the_bundle(google)
    assert sorted(bundle.threads) == ["1head07", "1head08"]
    assert {Thread.model_validate_json(item.thread).category for item in bundle.threads.values()} == {"general"}


def test_a_brand_name_with_a_general_types_plural_names_no_model():
    # "Most named model: Ruffwear harnesses" would name no model at all (14 Oct 2026: a type's plural is generic too).
    from engine.pipeline import _names_a_model
    from engine.tests.test_pick_polish import group

    assert not _names_a_model("Ruffwear harnesses", group("Ruffwear", loose=True), "dog harness")
    assert _names_a_model("Ruffwear Front Range harness", group("Ruffwear", loose=True), "dog harness")


def test_the_type_a_name_ends_with_is_found_as_a_full_search_finds_it():
    # 14 Oct 2026 (merging main): with the taxonomy, looking through every name of every type for each of the AI's types
    # took a second of getting ready; the names are now looked up by their last word, the same type found.
    from engine.pipeline import _ends_with_a_type
    from engine.query import PRODUCT_TYPES

    def full_search(product_type):
        text = " " + " ".join(product_type.strip().lower().split())
        best = None
        for product in PRODUCT_TYPES:
            for keyword in product.keywords:
                if any(text.endswith(" " + form) for form in (keyword, keyword + "s", keyword + "es")):
                    if best is None or len(keyword) > best[0]:
                        best = (len(keyword), product)
        return best[1] if best else None

    names = [k for p in PRODUCT_TYPES for k in p.keywords][::60]  # every 60th name: the full search is slow
    types = names + [n + "s" for n in names] + [n + "es" for n in names] + [f"down {n}" for n in names]
    types += ["frying pan set", "gooseneck kettle", "  Down   Sleeping  Bag ", "", "pan set", "set", "notatype"]
    for product_type in types:
        assert _ends_with_a_type(product_type) == full_search(product_type), product_type


def test_names_grouped_by_first_letter_with_their_plural_endings_find_what_they_found_one_by_one():
    # 14 Oct 2026 (merging main's names grouped by first letter, engine.sources._alternation): every module 1 name with
    # its plural ending (engine.query.name_pattern: "brushes", "potties"), grouped, matches where and as the names one
    # after another did.
    import re

    from engine.query import PRODUCT_TYPES, name_pattern
    from engine.sources import _alternation

    names = [k for p in PRODUCT_TYPES for k in p.keywords + p.hints]
    grouped = re.compile(rf"\b(?:{_alternation(names, name_pattern)})\b", re.IGNORECASE)
    one_by_one = re.compile(rf"\b(?:{'|'.join(name_pattern(n) for n in names)})\b", re.IGNORECASE)
    for text in ("Two dish brushes and a travel potty, then potties for the twins.",
                 "My Kettles broke; the french presses lasted. A hair dryer, three Hair Dryers.",
                 "Robot vacuums vs a stick vacuum: e-readers, 3D printers and a TV-stand.",
                 "nothing to see here", "Boxes of glasses, watches and benches."):
        assert ([m.span() for m in grouped.finditer(text)] == [m.span() for m in one_by_one.finditer(text)]), text
