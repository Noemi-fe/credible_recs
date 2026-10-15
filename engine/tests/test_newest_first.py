"""Newest threads first for fast-moving products (Noemi's decision 1 of 15 Oct 2026, late afternoon).

The live laptop answer's first pick was 2010-2011 MacBook Pros, read from old threads: laptops, phones, TVs, headphones
and the like are replaced every year or two, so an old thread's picks go out of sale as it ages. For those types
(config.FAST_MOVING_TYPES, Claude's list), module 2's first reading reads the threads newest first, a year at a time
(config.FAST_MOVING_YEARS) counted back from the newest thread about the product, each year's in module 2's graded and
need-led order. Kitchen, skincare and haircare requests read as before. Every thread here is made up.
"""

import json
from pathlib import Path

from engine import config
from engine.pipeline import answer_request
from engine.query import PRODUCT_TYPES, parse_query
from engine.sources import LocalSource
from engine.tests.factories import make_comment, make_thread, write_gold
from engine.tests.test_buyable import laptop_library


def write_threads(tmp_path: Path, threads: list[tuple]) -> Path:
    """[(thread id, title, posted, comments, category, subreddit[, post])] as a library folder of threads."""
    saved = [make_thread(id=tid, title=title, created_at=posted, num_comments=comments, category=category,
                         community=subreddit, body=(post or ["Looking for one."])[0],
                         url=f"https://www.reddit.com/r/{subreddit}/comments/{tid}/x/",
                         comments=[make_comment(f"{tid}c1", thread_id=tid, body="A readable comment.")])
             for tid, title, posted, comments, category, subreddit, *post in threads]
    return write_gold(tmp_path / "library", saved, voices=None, mentions=None) / "threads"


def read(folder: Path, request: str) -> list[str]:
    return [t.id for t in LocalSource(folder).find_threads(parse_query(request), limit=100)]


LAPTOP_THREADS = [
    # A big old advice thread, which module 2's graded order puts first, and smaller newer ones.
    ("1old001", "Best laptop to buy?", "2020-03-01T09:00:00Z", 900, "general", "BuyItForLife"),
    ("1new001", "Laptop that lasts?", "2023-09-01T09:00:00Z", 40, "general", "laptops"),
    ("1new002", "Best laptop to buy?", "2023-06-01T09:00:00Z", 300, "general", "laptops"),
    ("1mid001", "Best laptop for the money?", "2022-05-01T09:00:00Z", 500, "general", "SuggestALaptop"),
    ("1mid002", "Laptop recommendations?", "2022-03-01T09:00:00Z", 30, "general", "laptops"),
]


def test_the_fast_moving_types_are_general_products_module_1_knows():
    known = {p.name: p.category for p in PRODUCT_TYPES}
    assert config.FAST_MOVING_TYPES and all(known.get(t) == "general" for t in config.FAST_MOVING_TYPES)
    assert {"laptop", "phone", "tv", "headphones", "earbuds", "monitor", "tablet", "camera", "smartwatch",
            "gaming console", "wifi router"} <= set(config.FAST_MOVING_TYPES)


def test_a_laptop_request_reads_the_newest_threads_first_each_year_in_module_2s_order(tmp_path):
    order = read(write_threads(tmp_path, LAPTOP_THREADS), "laptop")
    # Within a year of the newest thread (Sep 2023): the 2023 ones, the bigger advice thread first; then the year
    # before it (May and March 2022), the bigger first; then the oldest, however big.
    assert order == ["1new002", "1new001", "1mid001", "1mid002", "1old001"]


def test_the_same_threads_for_a_type_that_isnt_fast_moving_keep_module_2s_graded_order(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "FAST_MOVING_TYPES", ())
    monkeypatch.setattr("engine.sources.FAST_MOVING_TYPES", ())
    order = read(write_threads(tmp_path, LAPTOP_THREADS), "laptop")
    # Module 2's graded order alone (engine.sources.post_score: advice, comments, the most specialist community first),
    # whatever their age: the newest small thread last.
    assert order == ["1mid001", "1old001", "1new002", "1mid002", "1new001"]


def test_kitchen_threads_keep_their_order_whatever_their_age(tmp_path):
    kettles = [(tid.replace("1", "2", 1), title.replace("laptop", "electric kettle"), posted, comments, "kitchen",
                "BuyItForLife") for tid, title, posted, comments, *_ in LAPTOP_THREADS]
    order = read(write_threads(tmp_path, kettles), "electric kettle")
    assert order[0] == "2old001"


def test_a_need_still_leads_within_a_year_and_another_types_thread_still_comes_last(tmp_path):
    threads = LAPTOP_THREADS + [
        ("1new003", "Laptop for programming?", "2023-02-01T09:00:00Z", 25, "general", "laptops"),
        ("1old002", "Laptop for programming that lasts?", "2019-02-01T09:00:00Z", 400, "general", "laptops"),
        ("1new004", "Best monitor to buy?", "2023-08-01T09:00:00Z", 200, "general", "monitors",
         "To go with my laptop."),
    ]
    order = read(write_threads(tmp_path, threads), "laptop for programming")
    assert order[0] == "1new003"  # the newest year's thread about programming first
    assert order.index("1new003") < order.index("1new002") < order.index("1mid001") < order.index("1old002")
    assert order[-1] == "1new004"  # titled as a monitor thread: after every laptop thread


def test_the_first_reading_of_a_laptop_answer_is_its_newest_threads(tmp_path):
    threads = {
        "1lap001": ("Best laptop to buy?", "2023-05-02T09:00:00Z", "laptops", [("l1a", "Maker Aircraft 13", 2)]),
        "1lap002": ("My laptop died", "2022-01-04T09:00:00Z", "BuyItForLife", [("l2a", "Maker Aircraft 13", 3)]),
        # Module 2's graded order puts it first (advice, long-term use): the oldest, so read last.
        "1lap003": ("Best laptop for university that lasts for years?", "2020-06-07T09:00:00Z", "SuggestALaptop",
                    [("l3a", "MBPs from late 2010-2011", 10)]),
    }
    result = answer_request("laptop", library_dir=laptop_library(tmp_path, threads), max_threads=2, more_threads=None,
                            prices=[], product_pages=[], product_facts=[], brand_lines=[])
    assert result.threads_used == ["1lap001", "1lap002"]
