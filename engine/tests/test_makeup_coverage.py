"""Makeup coverage (4 Nov 2026, from Noemi's report: "blush" on the site said it had counted one thread, while Google's top
results for the same need were big Reddit threads in r/Makeup and r/Sephora; her ask: "let's do better threads wise").

1. The communities. r/Makeup (general makeup questions) and r/Sephora (a shoppers' community, not run by the retailer)
   are where those threads are; neither was a decided subreddit, so the archive reader refused to read them. They are
   general-category subreddits now, and r/AsianBeauty, decided for skincare already, is listed for the general category
   too, last, for foundation, concealer, mascara and lipstick (decided by Noemi, 4 Nov 2026: "Yes, plus r/AsianBeauty").
   r/MakeupRehab, a no-buy community, stays decided but no makeup type searches it.
2. The types. Bronzer was folded into blush and the setting powders into setting spray, so a "bronzer" request was
   answered with blushes; highlighters had no type. Bronzer, highlighter and setting powder are types of their own,
   blush and setting spray lose the names that were someone else's, and every makeup type's title words include its
   plural ("blushes": Arctic Shift's title search matches whole words only).
3. Makeup is reformulated as skincare and haircare are: an old makeup thread loses the ranking's old-post points, and
   since 5 Nov 2026 (Noemi: "Yes, like skincare") an old comment counted for a makeup request is a medium voice at
   most, as an old skincare or haircare comment is (engine/credibility.py; tested in test_makeup_split.py).
4. The pre-check reads the blush answers' quotes ahead, first (4 Nov 2026), without warming them: the answers' memory is
   nearly full, so they are not in engine/data/demo_requests.json.

Every post, title and comment here is made up.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from engine import config
from engine.config import MORE_PRODUCT_TYPES
from engine.parse_reddit import category_for
from engine.query import classify, parse_query
from engine.sources import finder_terms, post_score
from engine.tests.test_archive_reader import FakeArchive, archive_post, make_archive, node, raw_comment

MAKEUP_COMMUNITIES = ["Makeup", "Sephora", "MakeupAddiction", "drugstoreMUA"]
# Changed on purpose, 5 Nov 2026: lip tint and brow gel are makeup types of their own (Noemi: "Split both"), lip tint
# searched in r/AsianBeauty too, as lipstick is.
MAKEUP_TYPES = ("foundation", "concealer", "mascara", "lipstick", "lip tint", "eyeliner", "eyeshadow", "makeup primer",
                "brow pencil", "brow gel", "blush", "bronzer", "highlighter", "setting powder", "setting spray")
WITH_ASIAN_BEAUTY = ("foundation", "concealer", "mascara", "lipstick", "lip tint")


@pytest.fixture(autouse=True)
def _rules_only(monkeypatch):
    # Module 1's rules alone (the open model is off in every test already: conftest.py).
    monkeypatch.setenv("CREDIBLE_RECS_QUERY_MODEL", "off")


def _entry(name: str) -> dict:
    return next(entry for entry in MORE_PRODUCT_TYPES if entry["name"] == name)


# --- 1. The communities ---

def test_makeup_and_sephora_are_general_subreddits():
    assert category_for("Makeup") == "general" and category_for("r/Sephora") == "general"
    assert {"Makeup", "Sephora", "AsianBeauty"} <= set(config.SUBREDDITS["general"])
    assert category_for("AsianBeauty") == "skincare"  # still skincare's first: a thread read for makeup takes "general"


def test_a_sephora_thread_is_read_not_refused(tmp_path):
    post = archive_post("1seph01", subreddit="Sephora", title="Which blush lasts all day?")
    tree = [node(raw_comment("c1", "t3_1seph01", body="A made-up comment about a blush.", post_id="1seph01",
                             subreddit="Sephora"))]
    service = FakeArchive(posts={"1seph01": post}, trees={"1seph01": tree})
    thread = make_archive(tmp_path, service).get_thread("1seph01", "Sephora")
    assert (thread.id, thread.community, thread.category) == ("1seph01", "Sephora", "general")


def test_the_makeup_communities_are_decided_not_proposed():
    # Noemi, 4 Nov 2026: "Yes, plus r/AsianBeauty".
    text = (Path(config.__file__)).read_text(encoding="utf-8")
    first = text.index("# 4 Nov 2026 (Noemi's report about \"blush\"")
    note = text[first:text.index('"Makeup", "Sephora", "AsianBeauty",', first)]
    assert "PROPOSED" not in note and "Decided by Noemi, 4 Nov 2026" in note


def test_a_thread_read_in_asian_beauty_for_a_makeup_request_is_a_general_thread_the_library_accepts(tmp_path):
    from engine.gold import load_threads
    from engine.library import _save
    from engine.sources import for_request

    post = archive_post("1asb01", subreddit="AsianBeauty", title="Which cushion foundation suits oily skin?")
    tree = [node(raw_comment("c1", "t3_1asb01", body="A made-up comment about a cushion.", post_id="1asb01",
                             subreddit="AsianBeauty"))]
    service = FakeArchive(posts={"1asb01": post}, trees={"1asb01": tree})
    thread = make_archive(tmp_path, service).get_thread("1asb01", "AsianBeauty")
    assert thread.category == "skincare"  # the archive reader names it by the community alone
    kept = for_request(thread, parse_query("foundation for oily skin"))
    assert (kept.community, kept.category) == ("AsianBeauty", "general")
    _save(kept, tmp_path / "library")
    problems: list[str] = []
    [loaded] = load_threads(tmp_path / "library" / "threads", skip_broken=True, problems=problems)
    assert loaded.category == "general" and problems == []  # r/AsianBeauty is one of the general subreddits
    # A skincare request reading the same community keeps it skincare.
    assert for_request(thread, parse_query("sunscreen for oily skin")).category == "skincare"


def test_makeup_rehab_stays_decided_but_no_makeup_type_searches_it():
    assert category_for("MakeupRehab") == "general"
    assert not [name for name in MAKEUP_TYPES if "MakeupRehab" in _entry(name)["subreddits"]]


def test_every_makeup_type_searches_the_makeup_communities_first():
    for name in MAKEUP_TYPES:
        subreddits = _entry(name)["subreddits"]
        assert subreddits[:4] == MAKEUP_COMMUNITIES, name
        assert subreddits[4:] == (["AsianBeauty"] if name in WITH_ASIAN_BEAUTY else []), name


def test_a_makeup_request_is_searched_in_the_makeup_communities():
    for request in ("blush", "cream blush", "blush for fair skin"):
        query = parse_query(request)
        assert (query.status, query.product_type, query.category) == ("ok", "blush", "general"), request
        assert query.subreddits == MAKEUP_COMMUNITIES, request
    assert parse_query("foundation for oily skin").subreddits == MAKEUP_COMMUNITIES + ["AsianBeauty"]


# --- 2. The types ---

@pytest.mark.parametrize("request_text, product_type", [
    ("bronzer", "bronzer"),
    ("contour stick", "bronzer"),
    ("cream bronzer that isn't orange", "bronzer"),
    ("highlighter", "highlighter"),
    ("liquid highlighter for dry skin", "highlighter"),
    ("setting powder", "setting powder"),
    ("translucent powder", "setting powder"),
    ("setting spray", "setting spray"),
    ("blush", "blush"),
    ("cream blush", "blush"),
    ("blush for fair skin", "blush"),
    # Changed on purpose, 5 Nov 2026: a lip tint and a brow gel were a lipstick and a brow pencil until Noemi split
    # them ("Split both").
    ("lip tint", "lip tint"),
    ("brow gel", "brow gel"),
    ("lipstick", "lipstick"),
    ("brow pencil", "brow pencil"),
])
def test_each_makeup_name_finds_its_own_type(request_text, product_type):
    query = parse_query(request_text)
    assert (query.status, query.product_type) == ("ok", product_type)


def test_bronzer_is_no_longer_answered_as_blush():
    assert "bronzer" not in _entry("blush")["keywords"] and "bronzer" not in _entry("blush")["title_words"]
    assert parse_query("bronzer").product_type == "bronzer"


def test_the_setting_powders_are_no_longer_setting_sprays():
    spray = _entry("setting spray")
    assert not [k for k in spray["keywords"] + spray["title_words"] if "powder" in k]


def test_highlighter_pens_are_no_makeup():
    assert classify("highlighter pens for studying").product_type != "highlighter"
    assert classify("highlighter pen").product_type != "highlighter"


def test_primer_alone_still_asks_which_kind():
    # Paint primer is a primer too: the request is asked about, as before.
    assert parse_query("primer").status == "clarify"
    assert parse_query("makeup primer for large pores").product_type == "makeup primer"


def test_contour_alone_is_no_bronzer_where_it_means_a_shape():
    # "contour" is how a mattress or a pillow fits a body: only the makeup forms of it name a bronzer.
    assert parse_query("mattress that contours to my body").product_type == "mattress"


def test_every_makeup_types_title_words_include_its_plural():
    assert finder_terms("blush") == ["blush", "blushes"]
    plurals = {"foundation": "foundations", "concealer": "concealers", "mascara": "mascaras", "lipstick": "lipsticks",
               "eyeliner": "eyeliners", "makeup primer": "primers", "bronzer": "bronzers",
               "highlighter": "highlighters", "setting spray": "setting sprays"}
    for name, plural in plurals.items():
        assert finder_terms(name)[:2] == [finder_terms(name)[0], plural], name
    # Changed on purpose, 5 Nov 2026: lip tints and brow gels are found under their own types now (Noemi: "Split
    # both"), so lipstick's and brow pencil's searches no longer hold them.
    assert "lip tint" not in finder_terms("lipstick") and "brow gel" not in finder_terms("brow pencil")
    assert finder_terms("lip tint")[:2] == ["lip tint", "lip tints"]
    assert finder_terms("brow gel")[:2] == ["brow gel", "brow gels"]
    assert finder_terms("setting powder") == ["setting powder", "translucent powder"]


# --- 3. Makeup is reformulated ---

NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)


def _posted(year: int, title: str, subreddit: str) -> dict:
    return {"id": f"1p{year}", "title": title, "subreddit": subreddit, "num_comments": 120, "score": 50,
            "created_utc": datetime(year, 6, 1, tzinfo=UTC).timestamp(), "selftext": "Made up."}


def test_an_old_makeup_thread_loses_the_old_post_points_a_recent_one_keeps():
    blush = parse_query("blush")
    # Changed on purpose, 4 Nov 2026: the title was close to a real thread's; a made-up one tests the same.
    new, old = (post_score(blush, _posted(year, "Which blush gets the most love here?", "Sephora"), now=NOW)
                for year in (2025, 2020))
    assert new - old == pytest.approx(1.5)
    assert "blush" in config.REFORMULATED_TYPES and "general" not in config.REFORMULATED_CATEGORIES


def test_an_old_hair_dryer_thread_keeps_its_points():
    dryer = parse_query("hair dryer")
    new, old = (post_score(dryer, _posted(year, "Best hair dryer?", "Hair"), now=NOW) for year in (2025, 2020))
    assert new == old


def test_the_reformulated_types_are_the_makeup_types():
    assert set(config.REFORMULATED_TYPES) == set(MAKEUP_TYPES)
    assert all(_entry(name)["category"] == "general" for name in config.REFORMULATED_TYPES)


# --- 4. The blush answers are checked ahead ---

def test_the_blush_requests_are_checked_ahead_first_without_being_warmed():
    import json

    from engine import precheck

    blush = ("blush", "blush for fair skin", "cream blush")
    assert config.PRECHECK_FIRST_REQUESTS == blush
    listed, first = precheck.requests_to_check(), precheck.first_requests()
    assert set(blush) <= set(listed) and set(blush) <= first
    assert len(listed) <= config.PLAN_MAX_REQUESTS
    demo = json.loads(precheck.DEMO_FILE.read_text(encoding="utf-8"))
    assert not set(blush) & set(demo["demo"] + demo["interviewee"])  # not warmed: the answers' memory is nearly full
