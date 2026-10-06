"""Shared test helpers: a small, valid, entirely made-up gold set that each test breaks in one way."""

import json
from pathlib import Path

LABELS_HEADER = "thread_id,comment_id,product,stance,credibility,reason\n"


def make_thread(**overrides) -> dict:
    """A valid skincare thread with three comments. Usernames and ids are fake."""
    thread = {
        "id": "1fake01",
        "source": "reddit",
        "community": "SkincareAddiction",
        "category": "skincare",
        "title": "Gentle exfoliant for sensitive skin?",
        "body": "Looking for something under £30.",
        "author": {"name": "test_op", "account_created_at": "2020-01-15", "karma": 1200, "flair": None},
        "created_at": "2025-03-01T09:00:00Z",
        "score": 150,
        "num_comments": 42,
        "url": "https://www.reddit.com/r/SkincareAddiction/comments/1fake01/gentle_exfoliant/",
        "collected_at": "2026-10-06",
        "comments": [
            make_comment("c1aaaa", body="I've used the CeraVe SA Cleanser for 2 years. Gentle, but it dries me out in winter."),
            make_comment("c2bbbb", parent_id="c1aaaa", body="Same here, 3 years and counting."),
            make_comment("c3cccc", body="Paula's Choice 2% BHA beats every acid toner I've tried."),
        ],
    }
    thread.update(overrides)
    return thread


def make_comment(comment_id: str, thread_id: str = "1fake01", **overrides) -> dict:
    comment = {
        "id": comment_id,
        "parent_id": None,
        "author": {"name": f"test_user_{comment_id}", "account_created_at": "2018-06-01", "karma": 5000, "flair": "Dry/sensitive"},
        "body": "A readable comment.",
        "created_at": "2025-03-02T10:00:00Z",
        "score": 12,
        "url": f"https://www.reddit.com/r/SkincareAddiction/comments/{thread_id}/comment/{comment_id}/",
        "status": "ok",
    }
    comment.update(overrides)
    return comment


def write_gold(root: Path, threads: list[dict], labels: str | None = LABELS_HEADER) -> Path:
    """Write threads as threads/<id>.json and labels as labels.csv. Pass labels=None to leave the CSV out."""
    (root / "threads").mkdir(parents=True, exist_ok=True)
    for thread in threads:
        (root / "threads" / f"{thread['id']}.json").write_text(json.dumps(thread, ensure_ascii=False, indent=2), encoding="utf-8")
    if labels is not None:
        (root / "labels.csv").write_text(labels, encoding="utf-8")
    return root
