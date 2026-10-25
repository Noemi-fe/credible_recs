"""The tech data round of 25 Oct 2026 (branch data-tech2; Claude's technical calls inside Noemi's decision (e) of
19 Oct 2026, "phone and webcam communities may be added"; reported to her).

1. Phone and webcam communities. The three phone communities Noemi's decision names (r/iphone, r/GooglePixel and
   r/samsung) and one webcam community are decided general subreddits, and the phone and webcam types search them (a
   thread is read only from a decided subreddit, and a request's subreddits must be among its category's). The webcam
   community is r/Twitch: checked on Arctic Shift on 25 Oct 2026, it exists, posts every day, and had about 25
   "which webcam" threads with 10 or more comments in 2024-2026 (r/webcam, the obvious name, is an adult-content
   community whose last post is from 2021 and is never added; r/WorkFromHome had two weak threads in the same years).
"""

import json
from pathlib import Path

from engine.config import SUBREDDITS
from engine.query import parse_query

PRODUCT_TYPES = Path(__file__).resolve().parents[1] / "data" / "product_types.json"
PHONE_COMMUNITIES = ("iphone", "GooglePixel", "samsung")
WEBCAM_COMMUNITY = "Twitch"


def type_communities(name: str) -> list[str]:
    types = json.loads(PRODUCT_TYPES.read_text(encoding="utf-8"))["types"]
    return next(t["subreddits"] for t in types if t["name"] == name)


def test_the_phone_communities_are_decided_general_subreddits():
    assert set(PHONE_COMMUNITIES) <= set(SUBREDDITS["general"])


def test_the_phone_type_searches_them_after_its_broad_communities():
    communities = type_communities("phone")
    assert set(PHONE_COMMUNITIES) <= set(communities)
    assert communities[:3] == ["PickAnAndroidForMe", "BuyItForLife", "Frugal"]  # the broad ones stay first


def test_a_phone_request_is_searched_in_them_and_stays_inside_the_decided_ones():
    query = parse_query("a phone with a good camera")
    assert query.product_type == "phone"
    assert set(PHONE_COMMUNITIES) <= set(query.subreddits)
    assert set(query.subreddits) <= set(SUBREDDITS["general"])


def test_the_webcam_community_is_a_decided_general_subreddit_and_the_webcam_type_searches_it():
    assert WEBCAM_COMMUNITY in SUBREDDITS["general"]
    communities = type_communities("webcam")
    assert WEBCAM_COMMUNITY in communities
    assert communities[:2] == ["BuyItForLife", "laptops"]  # the broad ones stay first


def test_the_adult_webcam_community_is_never_a_decided_subreddit():
    for subs in SUBREDDITS.values():
        assert "webcam" not in {s.lower() for s in subs}
    for t in json.loads(PRODUCT_TYPES.read_text(encoding="utf-8"))["types"]:
        assert "webcam" not in {s.lower() for s in t.get("subreddits", [])}


def test_a_webcam_request_is_searched_in_it_and_stays_inside_the_decided_ones():
    query = parse_query("webcam for video calls")
    assert query.product_type == "webcam"
    assert WEBCAM_COMMUNITY in query.subreddits
    assert set(query.subreddits) <= set(SUBREDDITS["general"])
