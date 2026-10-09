"""The thin end-to-end slice: a request typed in plain words goes through modules 1 to 7 and comes back as a top 3.

A made-up library of two kettle threads, written to a temporary folder with their extraction files, so no test
reads data/.
"""

import json
from pathlib import Path

from engine.answer import unverified_claims
from engine.pipeline import answer_request
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
    assert kept == ["Cuisinart PerfecTemp", "Zojirushi kettle"] and left_out == ["Breville"]


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
