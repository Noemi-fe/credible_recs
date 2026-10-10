"""The thin end-to-end slice: a request typed in plain words goes through modules 1 to 7 and comes back as a top 3.

A made-up library of two kettle threads, written to a temporary folder with their extraction files, so no test
reads data/.
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from engine import answer as answer_wording
from engine import pipeline
from engine.answer import unverified_claims
from engine.config import PRICE_MAX_AGE_DAYS
from engine.pipeline import _another_type_by_ai, answer_request
from engine.prices import Price
from engine.tests.factories import make_comment, make_thread, write_gold

REQUEST = "electric kettle that lasts 10+ years"


def kettle_thread(thread_id: str, comments: list[dict]) -> dict:
    return make_thread(
        id=thread_id, community="BuyItForLife", category="kitchen", title="Which electric kettle lasts?",
        body="My kettle died again.", url=f"https://www.reddit.com/r/BuyItForLife/comments/{thread_id}/kettle/",
        comments=comments,
    )


def comment(comment_id: str, thread_id: str, body: str, **overrides) -> dict:
    url = f"https://www.reddit.com/r/BuyItForLife/comments/{thread_id}/comment/{comment_id}/"
    return make_comment(comment_id, thread_id=thread_id, body=body, url=url, **overrides)


def mention(comment_id: str, product: str, quote: str, stance: str = "recommend", category: str = "kitchen") -> dict:
    return {"comment_id": comment_id, "product": product, "category": category, "stance": stance, "quote": quote}


ZOJI_1 = "My Zojirushi kettle has lasted 6 years and still boils perfectly."
ZOJI_2 = "Had my Zojirushi kettle for 4 years now, no problems at all."
ZOJI_3 = "Our Zojirushi kettle is 8 years old and still going strong."
ZOJI_4 = "I've used the Zojirushi kettle daily for 5 years."
LODGE = "My Lodge cast iron skillet has lasted 20 years."
CHEFMAN_1 = "The Chefman kettle died after 6 months of use."
CHEFMAN_2 = "Two Chefman kettles broke within a year of use, avoid them."
HARIO_1 = "My Hario Skerton has ground beans for my kettle pour-overs for 5 years."
HARIO_2 = "I've used a Hario Skerton for 3 years, still great with a gooseneck kettle."
HARIO_3 = "Hario Skerton for 4 years, heat the kettle while you grind."


def library(tmp_path: Path) -> Path:
    """Two kettle threads: the Zojirushi praised four times across both, a skillet praised, the Chefman warned against."""
    threads = [
        kettle_thread("1kett01", [
            comment("k1aaaa", "1kett01", ZOJI_1),
            comment("k1bbbb", "1kett01", ZOJI_2),
            comment("k1cccc", "1kett01", LODGE),
            comment("k1dddd", "1kett01", CHEFMAN_1),
        ]),
        kettle_thread("1kett02", [
            comment("k2aaaa", "1kett02", ZOJI_3),
            comment("k2bbbb", "1kett02", ZOJI_4),
            comment("k2cccc", "1kett02", CHEFMAN_2),
        ]),
    ]
    # A coffee thread whose comments mention a kettle in passing: not about kettles, so never read for one.
    threads.append(make_thread(
        id="1coff01", community="Coffee", category="kitchen", title="Which hand grinder should I get?",
        body="Budget is about 100.", url="https://www.reddit.com/r/Coffee/comments/1coff01/grinder/",
        comments=[comment("c1aaaa", "1coff01", HARIO_1), comment("c1bbbb", "1coff01", HARIO_2),
                  comment("c1cccc", "1coff01", HARIO_3)],
    ))
    root = write_gold(tmp_path / "library", threads, voices=None, mentions=None)
    extractions = {
        "1kett01": [mention("k1aaaa", "Zojirushi kettle", ZOJI_1), mention("k1bbbb", "Zojirushi kettle", ZOJI_2),
                    mention("k1cccc", "Lodge cast iron skillet", LODGE), mention("k1dddd", "Chefman kettle", CHEFMAN_1, "warn")],
        "1kett02": [mention("k2aaaa", "Zojirushi kettle", ZOJI_3), mention("k2bbbb", "Zojirushi kettle", ZOJI_4),
                    mention("k2cccc", "Chefman kettle", CHEFMAN_2, "warn")],
        "1coff01": [mention("c1aaaa", "Hario Skerton", HARIO_1), mention("c1bbbb", "Hario Skerton", HARIO_2),
                    mention("c1cccc", "Hario Skerton", HARIO_3)],
    }
    (root / "extracted").mkdir()
    for thread_id, mentions in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v5", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions,
        }), encoding="utf-8")
    return root


def test_a_request_comes_back_as_picks_with_verified_quotes(tmp_path):
    result = answer_request(REQUEST, library_dir=library(tmp_path))
    assert result.query.product_type == "electric kettle"
    assert [pick.name for pick in result.answer.picks][:1] == ["Zojirushi kettle"]
    assert sorted(result.threads_used) == ["1kett01", "1kett02"]
    assert unverified_claims(result.answer, result.bodies) == []


def test_products_of_another_type_are_left_out(tmp_path):
    # A skillet praised in a kettle thread is a real product, but not an answer to a kettle request.
    result = answer_request(REQUEST, library_dir=library(tmp_path))
    names = [p.name for p in result.ranking.products]
    assert "Lodge cast iron skillet" not in names
    assert "Lodge cast iron skillet" in result.left_out_as_other_type


def test_a_product_warned_against_twice_is_never_a_pick(tmp_path):
    result = answer_request(REQUEST, library_dir=library(tmp_path))
    assert "Chefman kettle" not in [pick.name for pick in result.answer.picks]


def test_a_request_that_needs_a_question_fetches_nothing(tmp_path):
    result = answer_request("something nice for my mum", library_dir=library(tmp_path))
    assert result.query.status == "clarify" and result.answer is None and result.threads_used == []


def test_the_answer_reads_as_text(tmp_path):
    text = answer_request(REQUEST, library_dir=library(tmp_path)).text()
    assert "Zojirushi kettle" in text and ZOJI_1 in text


def test_only_threads_about_the_product_are_read(tmp_path):
    # Its title or post must name the product: a coffee thread mentioning kettles in passing isn't about kettles.
    result = answer_request(REQUEST, library_dir=library(tmp_path))
    assert "1coff01" not in result.threads_used
    assert "Hario Skerton" not in [p.name for p in result.ranking.products]


def test_copied_text_is_looked_for_once_per_thread_read(tmp_path, monkeypatch):
    # Module 5's "copied text" red flag (Noemi's decision 3, 11 Oct 2026) compares a whole thread, which can have
    # hundreds of comments: it is worked out once per thread, not once per comment scored.
    looked_at = []
    real = pipeline.copied_comment_ids
    monkeypatch.setattr(pipeline, "copied_comment_ids", lambda thread: looked_at.append(thread.id) or real(thread))
    result = answer_request(REQUEST, library_dir=library(tmp_path))
    assert sorted(looked_at) == sorted(result.threads_used) == ["1kett01", "1kett02"]


class FakeProfiles:
    """Profiles as the cache would give them: every writer an old, active, well-regarded account."""

    def user_stats(self, author):
        return {"num_comments": 2000, "num_posts": 20, "total_karma": 30000, "earliest_comment_at": 1400000000}

    def comment_flairs(self, comment_ids):
        return {}


def plain_writers_library(tmp_path: Path) -> Path:
    """The kettle library, with writers known only by name, as Parse saves them."""
    root = library(tmp_path)
    for path in (root / "threads").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for c in data["comments"]:
            c["author"] = {"name": c["author"]["name"]}
        path.write_text(json.dumps(data), encoding="utf-8")
    return root


def test_profiles_from_the_cache_raise_the_writers_standing(tmp_path):
    lib = plain_writers_library(tmp_path)
    without = answer_request(REQUEST, library_dir=lib)
    with_profiles = answer_request(REQUEST, library_dir=lib, profiles=FakeProfiles())
    zoji = lambda result: next(p for p in result.ranking.products if p.name == "Zojirushi kettle")
    assert zoji(without).breakdown.recommend_voices["high"] < zoji(with_profiles).breakdown.recommend_voices["high"]


# --- Instructions v6 (9 Oct 2026): the AI writes each product's type, and the type decides ---

def typed_library(tmp_path: Path, title: str, rows: list[tuple[str, str, str | None, str]]) -> Path:
    """A made-up library extracted with instructions v6. Each row is one comment recommending one product:
    (comment id, product, the type the AI gave it or None, the comment's text, which is also the quote).
    Comments starting with "k1" go in thread 1kett01, the others in 1kett02; both threads are titled `title`."""
    threads, extractions = {}, {}
    for comment_id, product, product_type, body in rows:
        thread_id = "1kett01" if comment_id.startswith("k1") else "1kett02"
        threads.setdefault(thread_id, []).append(comment(comment_id, thread_id, body))
        typed = mention(comment_id, product, body) | ({"product_type": product_type} if product_type else {})
        extractions.setdefault(thread_id, []).append(typed)
    root = write_gold(tmp_path / "library", [
        make_thread(id=tid, community="BuyItForLife", category="kitchen", title=title, body="Mine died again.",
                    url=f"https://www.reddit.com/r/BuyItForLife/comments/{tid}/post/", comments=comments)
        for tid, comments in threads.items()
    ], voices=None, mentions=None)
    (root / "extracted").mkdir()
    for thread_id, mentions in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v6", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions,
        }), encoding="utf-8")
    return root


KETTLE_TITLE = "Which electric kettle lasts?"


def kept_and_left_out(result) -> tuple[list[str], list[str]]:
    return sorted(p.name for p in result.ranking.products), sorted(result.left_out_as_other_type)


def test_a_product_the_ai_types_as_another_known_type_is_left_out_whatever_its_name(tmp_path):
    # "Le Creuset" says nothing about its type, so the name rule would keep it; the AI says it's a stovetop kettle.
    lib = typed_library(tmp_path, KETTLE_TITLE, [
        ("k1aaaa", "Zojirushi kettle", "electric kettle", ZOJI_1),
        ("k1bbbb", "Le Creuset", "stovetop kettle", "My Le Creuset has whistled on the hob for 12 years."),
        ("k2aaaa", "Zojirushi kettle", "electric kettle", ZOJI_3),
    ])
    kept, left_out = kept_and_left_out(answer_request(REQUEST, library_dir=lib))
    assert kept == ["Zojirushi kettle"] and left_out == ["Le Creuset"]


def test_a_type_in_plain_words_is_left_out_unless_it_names_the_requested_type(tmp_path):
    lib = typed_library(tmp_path, KETTLE_TITLE, [
        ("k1aaaa", "Zojirushi kettle", "electric kettle", ZOJI_1),
        ("k1bbbb", "Breville", "toaster", "My Breville has made toast every morning for 9 years."),
        ("k1cccc", "Cuisinart PerfecTemp", "gooseneck kettle", "The Cuisinart PerfecTemp has been great for 3 years."),
    ])
    kept, left_out = kept_and_left_out(answer_request(REQUEST, library_dir=lib))
    # Changed 9 Oct 2026 when decision 12 was merged: Breville is shown by its UK name, Sage, in the left-out list too.
    assert kept == ["Cuisinart PerfecTemp", "Zojirushi kettle"] and left_out == ["Sage"]


def test_a_set_block_or_sharpener_of_the_requested_type_is_another_type(tmp_path):
    # Found in the 10 Oct 2026 evaluation run: "Henckels knife block" (the AI's type: "knife set") was a pick for "first
    # chef's knife", because "knife set" names a knife. A set, a block, a sharpener or a stand of knives isn't a chef
    # knife (config.OTHER_TYPE_WORDS); a type that only describes the knife still names it.
    lib = typed_library(tmp_path, "Best first chef's knife?", [
        ("k1aaaa", "Victorinox Fibrox", "chef knife", "My Victorinox Fibrox has been my daily knife for 6 years."),
        ("k1bbbb", "Henckels knife block", "knife set", "The Henckels knife block has served us for 10 years."),
        ("k1cccc", "Work Sharp", "knife sharpener", "The Work Sharp has kept my knives sharp for 5 years."),
        ("k1dddd", "Wusthof stand", "knife block", "Our Wusthof stand still looks new after 8 years."),
        ("k2aaaa", "Mercer Millennia", "chef's knife", "The Mercer Millennia has been great for 4 years."),
    ])
    kept, left_out = kept_and_left_out(answer_request("first chef's knife", library_dir=lib))
    assert kept == ["Mercer Millennia", "Victorinox Fibrox"]
    assert left_out == ["Henckels knife block", "Work Sharp", "Wusthof stand"]


def test_a_set_mention_never_lends_its_votes_to_the_brands_knives(tmp_path):
    # The 10 Oct 2026 run, again: "Henckels knive block" (knife set) was grouped with the writers' other Henckels
    # mentions (chef knives), and most of the group's mentions were chef knives, so the knife block's recommendations
    # counted for a chef knife. Each mention typed as a set, a block or a sharpener is left out before grouping.
    lib = typed_library(tmp_path, "Best first chef's knife?", [
        ("k1aaaa", "Henckels", "chef knife", "My Henckels chef's knife has lasted 12 years."),
        ("k1bbbb", "Henckels knife block", "knife set", "The Henckels knife block has served us for 10 years."),
        ("k2aaaa", "Henckels", "chef knife", "Henckels, 6 years of daily use and still sharp."),
        ("k2bbbb", "Henckels", "chef knife", "I have used a Henckels chef's knife for 9 years."),
        ("k2cccc", "Henckels knife block", "knife set", "Our Henckels knife block is 20 years old."),
    ])
    result = answer_request("first chef's knife", library_dir=lib)
    [henckels] = [p for p in result.ranking.products if "Henckels" in p.name]
    assert sorted(m.comment_id for m in henckels.mentions) == ["k1aaaa", "k2aaaa", "k2bbbb"]
    assert "Henckels knife block" in result.left_out_as_other_type


def test_a_pick_known_by_another_name_outside_the_uk_says_so(tmp_path):
    # Found reading the answers, 10 Oct 2026: "Sage (their electric kettles)" was backed by quotes that all say
    # "Breville" (decision 12 shows the UK name). A note under the pick says why.
    lib = typed_library(tmp_path, KETTLE_TITLE, [
        ("k1aaaa", "Breville kettle", "electric kettle", "My Breville kettle has lasted 8 years."),
        ("k1bbbb", "Breville kettle", "electric kettle", "The Breville kettle, 6 years and still perfect."),
        ("k2aaaa", "Breville kettle", "electric kettle", "Breville kettle here, 5 years of daily use."),
        ("k2bbbb", "Zojirushi kettle", "electric kettle", ZOJI_3),
    ])
    result = answer_request(REQUEST, library_dir=lib)
    sage = next(pick for pick in result.answer.picks if pick.name == "Sage kettle")
    assert sage.cautions == ["Note: sold as Breville outside the UK, so writers often call it Breville."]
    zoji = [pick for pick in result.answer.picks if pick.name != "Sage kettle"]
    assert all(pick.cautions == [] for pick in zoji)


@pytest.mark.parametrize("product_type, requested, other", [
    ("knife set", "chef knife", True),
    ("knife sets", "chef knife", True),
    ("knife block", "chef knife", True),
    ("knife sharpener", "chef knife", True),
    ("magnetic knife strip", "chef knife", True),
    ("frying pan set", "frying pan", True),
    ("frying pan lid", "frying pan", True),
    ("skincare set", "moisturiser", True),
    ("gooseneck kettle", "electric kettle", False),
    ("chef's knife", "chef knife", False),
])
def test_the_words_that_make_a_type_another_one(product_type, requested, other):
    assert _another_type_by_ai([product_type], requested) is other


def test_the_type_most_of_a_products_mentions_give_decides_and_a_tie_keeps_it(tmp_path):
    lib = typed_library(tmp_path, KETTLE_TITLE, [
        ("k1aaaa", "Bodum Bistro", "electric kettle", "The Bodum Bistro has lasted 5 years."),
        ("k1bbbb", "Bodum Bistro", "electric kettle", "Bodum Bistro, 4 years and counting."),
        ("k2aaaa", "Bodum Bistro", "teapot", "I love my Bodum Bistro."),
        ("k1cccc", "Hamilton Beach", "toaster", "Hamilton Beach toasts evenly after 6 years."),
        ("k1dddd", "Hamilton Beach", "toaster", "My Hamilton Beach still toasts well."),
        ("k2bbbb", "Hamilton Beach", "electric kettle", "Hamilton Beach boils fast."),
        ("k1eeee", "Fellow Stagg", "electric kettle", "The Fellow Stagg is lovely to pour from."),
        ("k2cccc", "Fellow Stagg", "stovetop kettle", "Fellow Stagg on the hob for 2 years."),
    ])
    kept, left_out = kept_and_left_out(answer_request(REQUEST, library_dir=lib))
    assert kept == ["Bodum Bistro", "Fellow Stagg"] and left_out == ["Hamilton Beach"]


def test_the_ais_type_keeps_a_product_whose_name_suggests_another_type(tmp_path):
    # The name rule reads "skillet" as a cast iron skillet; the AI knows a carbon steel skillet is a frying pan.
    lib = typed_library(tmp_path, "Best frying pan that lasts?", [
        ("k1aaaa", "Lodge carbon steel skillet", "frying pan", "My Lodge carbon steel skillet has lasted 7 years."),
        ("k2aaaa", "Lodge carbon steel skillet", "frying pan", "Lodge carbon steel skillet, 3 years, no complaints."),
    ])
    kept, left_out = kept_and_left_out(answer_request("a frying pan that lasts", library_dir=lib))
    assert kept == ["Lodge carbon steel skillet"] and left_out == []


def test_without_a_type_the_name_rule_still_decides(tmp_path):
    # Older extractions (v1 to v5) have no types: a name that says it's another type is still left out.
    lib = typed_library(tmp_path, KETTLE_TITLE, [
        ("k1aaaa", "Zojirushi kettle", "electric kettle", ZOJI_1),
        ("k1bbbb", "Lodge cast iron skillet", None, LODGE),
        ("k1cccc", "Le Creuset", None, "My Le Creuset has whistled on the hob for 12 years."),
    ])
    kept, left_out = kept_and_left_out(answer_request(REQUEST, library_dir=lib))
    assert kept == ["Le Creuset", "Zojirushi kettle"] and left_out == ["Lodge cast iron skillet"]


# --- Review fixes, 9 Oct 2026 ---

def write_extractions(root: Path, extractions: dict[str, tuple[list[dict], list[dict]]]) -> None:
    """One extraction file per thread: {thread id: (mentions, notes)}."""
    (root / "extracted").mkdir(exist_ok=True)
    for thread_id, (mentions, notes) in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v5", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions, "notes": notes,
        }), encoding="utf-8")


def test_a_thread_whose_comments_alone_name_the_product_is_not_read(tmp_path):
    # Five comments naming a kettle in passing used to give a grinder thread enough relevance to be read.
    in_passing = [HARIO_1, HARIO_2, HARIO_3, "Hario Skerton for 2 years, with my gooseneck kettle.",
                  "Hario Skerton every morning for 3 years; boil the kettle first."]
    threads = [make_thread(id=tid, community="Coffee", category="kitchen", title="Which hand grinder should I get?",
                           body="Budget is about 100.", url=f"https://www.reddit.com/r/Coffee/comments/{tid}/grinder/",
                           comments=[comment(f"{tid[-2:]}{x}aaaa", tid, b) for x, b in zip("abcde", in_passing)])
               for tid in ("1coff01", "1coff02")]
    root = write_gold(tmp_path / "library", threads, voices=None, mentions=None)
    write_extractions(root, {t["id"]: ([mention(c["id"], "Hario Skerton", c["body"]) for c in t["comments"]], [])
                             for t in threads})
    result = answer_request(REQUEST, library_dir=root)
    assert result.threads_used == []
    assert result.answer.picks == []


def test_one_writer_counts_once_across_comments_and_threads(tmp_path):
    same = {"name": "One_Person", "account_created_at": "2018-06-01", "karma": 5000}
    threads = [kettle_thread("1kett01", [comment("k1aaaa", "1kett01", ZOJI_1, author=same),
                                         comment("k1bbbb", "1kett01", ZOJI_2, author=same)]),
               kettle_thread("1kett02", [comment("k2aaaa", "1kett02", ZOJI_3, author={**same, "name": "one_person"})])]
    root = write_gold(tmp_path / "library", threads, voices=None, mentions=None)
    write_extractions(root, {
        "1kett01": ([mention("k1aaaa", "Zojirushi kettle", ZOJI_1), mention("k1bbbb", "Zojirushi kettle", ZOJI_2)], []),
        "1kett02": ([mention("k2aaaa", "Zojirushi kettle", ZOJI_3)], []),
    })
    result = answer_request(REQUEST, library_dir=root)
    zoji = next(p for p in result.ranking.products if p.name == "Zojirushi kettle")
    assert zoji.breakdown.credible_recommends == 1 and len(zoji.mentions) == 1
    assert result.answer.picks == []


def test_threads_not_yet_extracted_dont_take_the_reading_slots_and_are_listed(tmp_path):
    from engine.config import PIPELINE_MAX_THREADS

    root = library(tmp_path)
    waiting = []
    for i in range(PIPELINE_MAX_THREADS):  # more relevant (more comments), but the AI hasn't read them yet
        thread = kettle_thread(f"1new{i:02d}", [comment(f"n{i}a{j}aaa", f"1new{i:02d}", "Any kettle advice?") for j in range(5)])
        thread["num_comments"] = 500
        waiting.append(thread["id"])
        write_gold(root, [thread], voices=None, mentions=None)
    result = answer_request(REQUEST, library_dir=root)
    assert sorted(result.threads_used) == ["1kett01", "1kett02"]
    assert [p.name for p in result.answer.picks][:1] == ["Zojirushi kettle"]
    assert sorted(result.not_extracted) == waiting
    assert "1coff01" not in result.not_extracted  # extracted, but not about kettles


def test_the_reading_limit_counts_only_threads_read(tmp_path):
    result = answer_request(REQUEST, library_dir=library(tmp_path), max_threads=1)
    assert len(result.threads_used) == 1


def test_notes_naming_no_kind_are_listed_not_dropped_silently(tmp_path):
    # "kettle with auto shut-off" is, in a kettle request, about no kind at all (group_kinds, step 5).
    shut_off = "I've had a kettle for 10 years: get one with an auto shut-off."
    threads = [kettle_thread("1kett01", [comment("k1aaaa", "1kett01", ZOJI_1), comment("k1nnnn", "1kett01", shut_off)]),
               kettle_thread("1kett02", [comment("k2aaaa", "1kett02", ZOJI_3)])]
    root = write_gold(tmp_path / "library", threads, voices=None, mentions=None)
    write_extractions(root, {
        "1kett01": ([mention("k1aaaa", "Zojirushi kettle", ZOJI_1)],
                    [{"comment_id": "k1nnnn", "about": "kettle with auto shut-off", "stance": "recommend",
                      "quote": "get one with an auto shut-off."}]),
        "1kett02": ([mention("k2aaaa", "Zojirushi kettle", ZOJI_3)], []),
    })
    result = answer_request(REQUEST, library_dir=root)
    assert result.ranking.kind_notes == []
    assert result.notes_without_kind == ["kettle with auto shut-off"]


class RecordingProfiles(FakeProfiles):
    def __init__(self):
        self.asked = []

    def user_stats(self, author):
        self.asked.append(author)
        return super().user_stats(author)


def test_writers_of_notes_get_profiles_too(tmp_path):
    # Review finding 7: a "what to look for" note's writer needs a profile as much as a product's.
    lib = library(tmp_path)
    path = lib / "extracted" / "1kett01.json"
    extraction = json.loads(path.read_text(encoding="utf-8"))
    extraction["notes"] = [{"comment_id": "k1cccc", "about": "metal kettle", "stance": "recommend", "quote": LODGE}]
    extraction["mentions"] = [m for m in extraction["mentions"] if m["comment_id"] != "k1cccc"]
    path.write_text(json.dumps(extraction), encoding="utf-8")
    profiles = RecordingProfiles()
    answer_request(REQUEST, library_dir=lib, profiles=profiles)
    assert "test_user_k1cccc" in profiles.asked

# --- Decisions of 9 Oct 2026: brand-only picks (9), budgets (11) and the UK name (12) ---

TODAY = date(2026, 10, 9)


def write_library(tmp_path: Path, threads: dict[str, tuple[str, str, list[tuple]]], community: str = "castiron") -> Path:
    """A made-up library: {thread id: (title, post, [(comment id, product, text, stance)])}.

    Each comment's text is also its quote, so every quote is found word for word.
    """
    saved, extractions = [], {}
    for thread_id, (title, body, comments) in threads.items():
        url = f"https://www.reddit.com/r/{community}/comments/{thread_id}/thread/"
        saved.append(make_thread(id=thread_id, community=community, category="kitchen", title=title, body=body, url=url,
                                 comments=[comment(cid, thread_id, text) for cid, _, text, _ in comments]))
        extractions[thread_id] = [mention(cid, product, text, stance) for cid, product, text, stance in comments]
    root = write_gold(tmp_path / "library", saved, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for thread_id, mentions in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v5", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions,
        }), encoding="utf-8")
    return root


def praise(comment_id: str, product: str, years: int) -> tuple:
    return comment_id, product, f"My {product} has lasted {years} years and still works perfectly.", "recommend"


def skillet_library(tmp_path: Path) -> Path:
    """Skillet threads. "Lodge" and "Smithey" are brand names that fit two skillets each (so grouping marks them
    loose); "All-Clad" fits two pans, neither a skillet; "the one" names nothing; "Le Creuset dutch oven" is a line
    of another type of product."""
    return write_library(tmp_path, {
        "1skil01": ("Best cast iron skillet for a beginner?", "My first one.", [
            praise("s1a", "Lodge", 20), praise("s1b", "Lodge", 12),
            praise("s1c", "Lodge Blacklock skillet", 3), praise("s1d", "Lodge Chef Collection skillet", 4),
            praise("s1e", "Smithey", 5), praise("s1f", "Smithey", 6),
            praise("s1g", "Smithey No. 10 skillet", 2), praise("s1h", "Smithey No. 12 skillet", 2),
            praise("s1i", "the one", 30), praise("s1j", "the one", 25),
            praise("s1k", "Le Creuset dutch oven", 10), praise("s1l", "Le Creuset dutch oven", 11),
            praise("s1m", "Le Creuset 5.5 qt dutch oven", 3), praise("s1n", "Le Creuset 7 qt dutch oven", 3),
            praise("s1o", "All-Clad", 9), praise("s1p", "All-Clad", 8),
            praise("s1q", "All-Clad stainless", 4), praise("s1r", "All-Clad non-stick", 2),
        ]),
        "1skil02": ("Which cast iron skillet lasts?", "Mine cracked.", [
            praise("s2a", "Lodge", 15), praise("s2b", "the one", 40), praise("s2c", "Le Creuset dutch oven", 9),
            praise("s2d", "All-Clad", 7),
        ]),
        # Read (its post names a skillet), but its title doesn't: what it says about a brand is less clear.
        "1skil03": ("What should I cook my first steak in?", "Thinking of a cast iron skillet.", [
            praise("s3a", "Smithey", 7), praise("s3b", "Smithey", 8),
        ]),
    })


def test_a_brand_whose_threads_make_the_product_clear_is_a_pick_named_as_a_brand(tmp_path):
    result = answer_request("cast iron skillet that lasts", library_dir=skillet_library(tmp_path), prices=[], today=TODAY)
    assert "Lodge (their cast iron skillets)" in [pick.name for pick in result.answer.picks]
    assert "Lodge" not in result.left_out_loose
    assert unverified_claims(result.answer, result.bodies) == []


def test_a_brand_mentioned_mostly_in_threads_about_something_else_stays_out(tmp_path):
    # Smithey: 4 credible recommendations across 2 threads, but only half of them in threads whose title names a
    # skillet. More than half is needed.
    result = answer_request("cast iron skillet that lasts", library_dir=skillet_library(tmp_path), prices=[], today=TODAY)
    assert "Smithey" in result.left_out_loose
    assert not any("Smithey" in p.name and "their" in p.name for p in result.ranking.products)


def test_a_line_of_another_type_or_a_name_that_names_nothing_stays_out(tmp_path):
    result = answer_request("cast iron skillet that lasts", library_dir=skillet_library(tmp_path), prices=[], today=TODAY)
    assert {"Le Creuset dutch oven", "the one"} <= set(result.left_out_loose)
    assert not any("their" in p.name and p.name != "Lodge (their cast iron skillets)" for p in result.ranking.products)


def test_a_brand_none_of_whose_products_here_is_of_the_type_stays_out(tmp_path, monkeypatch):
    # Found in the library on 9 Oct 2026: All-Clad, praised in cast iron threads for its stainless and non-stick
    # pans, would be shown as "All-Clad (their cast iron skillets)". At least one of the brand's own products named
    # in the threads must be of the requested type ("Lodge Blacklock skillet").
    lib = skillet_library(tmp_path)
    result = answer_request("cast iron skillet that lasts", library_dir=lib, prices=[], today=TODAY)
    assert "All-Clad" in result.left_out_loose
    monkeypatch.setattr(pipeline, "BRAND_PICK_NEEDS_A_PRODUCT_OF_THE_TYPE", False)
    loose_rule_only = answer_request("cast iron skillet that lasts", library_dir=lib, prices=[], today=TODAY)
    assert "All-Clad (their cast iron skillets)" in [pick.name for pick in loose_rule_only.answer.picks]


def test_brand_picks_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "PIPELINE_BRAND_PICKS", False)
    result = answer_request("cast iron skillet that lasts", library_dir=skillet_library(tmp_path), prices=[], today=TODAY)
    assert "Lodge" in result.left_out_loose
    assert not any("their" in p.name for p in result.ranking.products)


def made_up_price(product: str, amount: float, checked_on: date = TODAY, currency: str = "GBP") -> Price:
    return Price(product=product, category="kitchen", price=amount, currency=currency, shop="Made-up Kitchen Shop",
                 url="https://shop.example/" + product.lower().replace(" ", "-"), checked_on=checked_on)


def test_a_product_over_the_budget_is_left_out_and_listed(tmp_path):
    result = answer_request("electric kettle under £100", library_dir=library(tmp_path),
                            prices=[made_up_price("Zojirushi kettle", 120.0)], today=TODAY)
    assert result.left_out_over_budget == ["Zojirushi kettle"]
    assert "Zojirushi kettle" not in [p.name for p in result.ranking.products]
    assert "Zojirushi" not in result.text()


def test_a_product_within_the_budget_shows_its_price_shop_and_date(tmp_path):
    result = answer_request("electric kettle under £100", library_dir=library(tmp_path),
                            prices=[made_up_price("Zojirushi kettle", 80.0)], today=TODAY)
    pick = result.answer.picks[0]
    assert pick.name == "Zojirushi kettle" and result.left_out_over_budget == []
    assert pick.price.amount == 80.0 and pick.price.shop == "Made-up Kitchen Shop"
    assert pick.price.url == "https://shop.example/zojirushi-kettle" and pick.price.checked_on == "2026-10-09"
    assert pick.price.budget_status == "within"


def test_a_product_with_no_known_price_is_kept_and_marked(tmp_path):
    result = answer_request("electric kettle under £100", library_dir=library(tmp_path), prices=[], today=TODAY)
    pick = result.answer.picks[0]
    assert pick.name == "Zojirushi kettle"
    assert pick.price.amount is None and pick.price.text == answer_wording.PRICE_UNKNOWN
    assert pick.price.budget_status == "unknown" and pick.price.budget_note


def test_an_old_price_is_shown_but_never_leaves_a_product_out(tmp_path):
    old = TODAY - timedelta(days=PRICE_MAX_AGE_DAYS + 1)
    result = answer_request("electric kettle under £100", library_dir=library(tmp_path),
                            prices=[made_up_price("Zojirushi kettle", 120.0, checked_on=old)], today=TODAY)
    pick = result.answer.picks[0]
    assert pick.name == "Zojirushi kettle" and result.left_out_over_budget == []
    assert pick.price.amount == 120.0 and pick.price.checked_on == old.isoformat()
    assert pick.price.budget_status == "out of date"


def test_a_price_in_another_currency_is_kept_and_marked(tmp_path):
    result = answer_request("electric kettle under £100", library_dir=library(tmp_path),
                            prices=[made_up_price("Zojirushi kettle", 500.0, currency="EUR")], today=TODAY)
    assert result.answer.picks[0].price.budget_status == "other currency"


def test_without_a_budget_a_known_price_is_still_shown(tmp_path):
    result = answer_request(REQUEST, library_dir=library(tmp_path), prices=[made_up_price("Zojirushi kettle", 120.0)],
                            today=TODAY)
    pick = result.answer.picks[0]
    assert pick.price.amount == 120.0 and pick.price.budget_status is None and pick.price.budget_note is None


def test_a_brand_pick_has_no_single_price_so_a_budget_never_leaves_it_out(tmp_path):
    result = answer_request("cast iron skillet under £50", library_dir=skillet_library(tmp_path),
                            prices=[made_up_price("Lodge", 500.0)], today=TODAY)
    lodge = next(pick for pick in result.answer.picks if pick.name == "Lodge (their cast iron skillets)")
    assert lodge.price.amount is None and lodge.price.budget_status == "unknown"


def test_the_uk_name_sage_is_shown_rather_than_breville(tmp_path):
    lib = write_library(tmp_path, {
        "1kett01": ("Which electric kettle lasts?", "Mine died.", [praise("k1a", "Breville IQ kettle", 6),
                                                                    praise("k1b", "Breville IQ kettle", 7)]),
        "1kett02": ("Electric kettle advice", "Need a new one.", [praise("k2a", "Sage IQ kettle", 5)]),
    }, community="BuyItForLife")
    result = answer_request("electric kettle under £100", library_dir=lib, prices=[made_up_price("Sage IQ kettle", 90.0)],
                            today=TODAY)
    assert [pick.name for pick in result.answer.picks] == ["Sage IQ kettle"]
    assert result.answer.picks[0].price.budget_status == "within"
    assert "## 1. Sage IQ kettle" in result.text()  # the quotes keep their own words: they are never changed


# --- Noemi's answers of 9 Oct 2026: a budget with no currency is in pounds ---

def test_a_budget_with_no_currency_is_in_pounds(tmp_path):
    result = answer_request("electric kettle under 100", library_dir=library(tmp_path),
                            prices=[made_up_price("Zojirushi kettle", 120.0)], today=TODAY)
    assert result.query.constraints.budget.currency is None  # module 1 doesn't guess; the budget check assumes £
    assert result.left_out_over_budget == ["Zojirushi kettle"]


def test_a_sunscreen_named_as_an_essence_stays_a_sunscreen():
    # Noemi, 9 Oct 2026: "UV" and "sun" say sunscreen, so "essence" (a toner word) doesn't leave it out.
    from engine.pipeline import _another_type_by_name
    from engine.group_products import ProductGroup, ProductMention
    from engine.query import parse_query

    query = parse_query("lightweight sunscreen for oily skin")
    for name in ("Biore UV Aqua Rich Watery Essence", "Missha All Around Safe Block Essence Sun"):
        group = ProductGroup(key=f"skincare:{name.lower()}", name=name, category="skincare",
                             mentions=[ProductMention("t1", "c1", name, "skincare", "recommend")])
        assert not _another_type_by_name(group, query)


# --- Care tips: how to make it last (Noemi, 9 Oct 2026; instructions v7) ---

DESCALE = "Descale it every 6 months and it will outlive you."
FILTERED = "Whatever kettle you get, use filtered water so it scales less."
PROMO = "Descale it monthly with our powder, use my code KETTLE10."
SEASON = "Re-season your cast iron after every scrub."


def care(comment_id: str, about: str, tip: str, quote: str, is_kind: bool = False) -> dict:
    return {"comment_id": comment_id, "about": about, "is_kind": is_kind, "tip": tip, "quote": quote}


def care_library(tmp_path: Path) -> Path:
    """The Zojirushi praised four times across two kettle threads (extracted with v7), with care tips: one about the
    Zojirushi, one about electric kettles, one from a paid promoter, and one about another kind of product."""
    threads = [
        kettle_thread("1kett01", [comment("k1aaaa", "1kett01", ZOJI_1), comment("k1bbbb", "1kett01", ZOJI_2),
                                  comment("k1cccc", "1kett01", f"My Zojirushi is 9 years old. {DESCALE}"),
                                  comment("k1dddd", "1kett01", SEASON)]),
        kettle_thread("1kett02", [comment("k2aaaa", "1kett02", ZOJI_3), comment("k2bbbb", "1kett02", ZOJI_4),
                                  comment("k2cccc", "1kett02", FILTERED), comment("k2dddd", "1kett02", PROMO)]),
    ]
    root = write_gold(tmp_path / "library", threads, voices=None, mentions=None)
    extractions = {
        "1kett01": ([mention("k1aaaa", "Zojirushi kettle", ZOJI_1), mention("k1bbbb", "Zojirushi kettle", ZOJI_2)],
                    [care("k1cccc", "Zojirushi", "descale every 6 months", DESCALE),
                     care("k1dddd", "cast iron", "re-season after scrubbing", SEASON, is_kind=True)]),
        "1kett02": ([mention("k2aaaa", "Zojirushi kettle", ZOJI_3), mention("k2bbbb", "Zojirushi kettle", ZOJI_4)],
                    [care("k2cccc", "electric kettle", "use filtered water", FILTERED, is_kind=True),
                     care("k2dddd", "electric kettle", "descale monthly", PROMO, is_kind=True)]),
    }
    (root / "extracted").mkdir()
    for thread_id, (mentions, tips) in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v7", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions, "care": tips,
        }), encoding="utf-8")
    return root


def test_each_pick_shows_how_to_take_care_of_it_from_credible_care_tips(tmp_path):
    result = answer_request(REQUEST, library_dir=care_library(tmp_path), prices=[], today=TODAY)
    zojirushi = result.answer.picks[0]
    assert zojirushi.name == "Zojirushi kettle"
    # Since 11 Oct 2026 (Noemi): the pick shows the tips about itself, and the tips about any electric kettle are in
    # one note at the end of the answer, not under every pick.
    assert [(c.tip, c.quote.text) for c in zojirushi.care] == [("Descale every 6 months.", DESCALE)]
    assert [(c.tip, c.quote.text) for c in result.answer.care_note] == [("Use filtered water.", FILTERED)]
    assert zojirushi.care[0].quote.url == "https://www.reddit.com/r/BuyItForLife/comments/1kett01/comment/k1cccc/"
    text = result.text()
    assert answer_wording.CARE_HEADING in text and DESCALE in text and FILTERED in text
    assert PROMO not in text and SEASON not in text  # a low voice, and a tip about another kind of product
    assert unverified_claims(result.answer, result.bodies) == []


def test_care_tips_change_nothing_in_the_ranking(tmp_path):
    lib = care_library(tmp_path)
    with_tips = answer_request(REQUEST, library_dir=lib, prices=[], today=TODAY)
    for path in (lib / "extracted").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        del data["care"]
        path.write_text(json.dumps(data), encoding="utf-8")
    without = answer_request(REQUEST, library_dir=lib, prices=[], today=TODAY)
    assert [(p.name, p.score) for p in with_tips.ranking.products] == [(p.name, p.score) for p in without.ranking.products]
    assert all(pick.care == [] for pick in without.answer.picks)


def test_an_older_extraction_without_care_tips_changes_nothing(tmp_path):
    result = answer_request(REQUEST, library_dir=library(tmp_path), prices=[], today=TODAY)
    assert result.answer.picks and all(pick.care == [] for pick in result.answer.picks)
    assert answer_wording.CARE_HEADING not in result.text()


def test_writers_of_care_tips_get_profiles_too(tmp_path):
    # Like notes (review finding 7): a care tip's voice needs its writer's standing as much as a product's.
    profiles = RecordingProfiles()
    answer_request(REQUEST, library_dir=care_library(tmp_path), profiles=profiles, prices=[], today=TODAY)
    assert "test_user_k2cccc" in profiles.asked


# --- The live check of every shown quote (Noemi, 9 Oct 2026: Reddit's embed page) ---

class FakeLive:
    """Stands in for engine.live_check.LiveChecker: the comments in `gone` were deleted on Reddit since we saved them."""

    def __init__(self, gone=()):
        self.gone, self.asked = set(gone), []

    def check(self, url, quote):
        from engine.live_check import LiveResult

        self.asked.append(url)
        comment_id = url.rstrip("/").split("/")[-1]
        return LiveResult("gone", "deleted") if comment_id in self.gone else LiveResult("ok", "still there")


def shown_comment_ids(answer):
    from engine.answer import _every_quote

    return {quote.comment_id for _, quote in _every_quote(answer)}


def test_every_shown_quote_is_checked_live_and_a_deleted_one_never_shows(tmp_path):
    lib = library(tmp_path)
    before = answer_request(REQUEST, library_dir=lib)
    assert "k1aaaa" in shown_comment_ids(before.answer)
    live = FakeLive(gone={"k1aaaa"})
    after = answer_request(REQUEST, library_dir=lib, live_checker=live)
    assert "k1aaaa" not in shown_comment_ids(after.answer)
    assert live.asked  # the shown quotes were checked
    assert after.live_dropped == {"gone": 1}
    assert unverified_claims(after.answer, after.bodies) == []


def test_with_the_live_check_threads_are_not_held_back_for_their_age(tmp_path):
    # Each shown quote is checked against Reddit itself, so a thread's last full re-read doesn't matter for showing it.
    from datetime import date

    lib = library(tmp_path)
    late = date(2026, 12, 1)  # long after the made-up threads were saved
    assert answer_request(REQUEST, library_dir=lib, today=late).answer.picks == []
    assert answer_request(REQUEST, library_dir=lib, today=late, live_checker=FakeLive()).answer.picks
