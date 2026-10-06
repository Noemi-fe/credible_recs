"""Loads and checks the hand-collected gold set in data/gold.

    data/gold/threads/<thread id>.json   one thread with its comments (shape: engine.models.Thread)
    data/gold/labels.csv                 Noemi's labels, one row per product mention (shape: engine.models.Label)

The loader never stops at the first mistake: it collects every problem, names the file and the
line or field, and raises them together, so a labelling session ends with one complete to-do list.

Run `python -m engine.gold` to check the gold set and print a summary.
"""

import csv
import json
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from pydantic import ValidationError

from engine.models import SUBREDDITS, Comment, Label, Thread

DEFAULT_GOLD_DIR = Path(__file__).resolve().parents[1] / "data" / "gold"

LABEL_COLUMNS = ("thread_id", "comment_id", "product", "stance", "credibility", "reason")
OPTIONAL_LABEL_COLUMNS = ("notes",)


class GoldSetError(Exception):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(f"{len(problems)} problem(s) in the gold set:\n" + "\n".join(f"- {p}" for p in problems))


@dataclass
class GoldSet:
    threads: list[Thread]
    labels: list[Label]

    def comment(self, comment_id: str) -> Comment:
        for thread in self.threads:
            for comment in thread.comments:
                if comment.id == comment_id:
                    return comment
        raise KeyError(comment_id)


def load_gold_set(root: Path = DEFAULT_GOLD_DIR) -> GoldSet:
    root = Path(root)
    problems: list[str] = []
    threads, unreadable = _load_threads(root, problems)
    labels = _load_labels(root, threads, unreadable, problems)
    if problems:
        raise GoldSetError(problems)
    return GoldSet(threads=threads, labels=labels)


# --- Threads ---

def _load_threads(root: Path, problems: list[str]) -> tuple[list[Thread], set[str]]:
    """Returns the threads that loaded, plus the ids of thread files that couldn't be read."""
    folder = root / "threads"
    if not folder.is_dir():
        problems.append("threads/ folder is missing")
        return [], set()

    threads: list[Thread] = []
    unreadable: set[str] = set()
    seen_comments: dict[str, str] = {}  # comment id -> thread id, to catch the same comment pasted into two threads
    for path in sorted(folder.glob("*.json")):
        where = f"threads/{path.name}"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            problems.append(f"{where}: not valid JSON (line {e.lineno}, column {e.colno}): {e.msg}")
            unreadable.add(path.stem)
            continue
        try:
            thread = Thread.model_validate(raw)
        except ValidationError as e:
            problems.extend(f"{where}: {_field(err['loc'])}{err['msg']}" for err in e.errors())
            unreadable.add(path.stem)
            if isinstance(raw, dict) and isinstance(raw.get("id"), str):
                unreadable.add(raw["id"])
            continue

        thread_problems = _check_thread(thread, path.stem)
        for comment in thread.comments:
            other = seen_comments.setdefault(comment.id, thread.id)
            if other != thread.id:
                thread_problems.append(f"comment {comment.id} also appears in thread {other}")
        problems.extend(f"{where}: {p}" for p in thread_problems)
        threads.append(thread)
    return threads, unreadable


def _check_thread(thread: Thread, file_stem: str) -> list[str]:
    """Checks that the parts of one thread fit together. Each returned string is one problem."""
    problems = []
    if file_stem != thread.id:
        problems.append(f"file name should match the thread id {thread.id!r}: rename it to {thread.id}.json")

    if thread.source == "reddit":
        allowed = SUBREDDITS[thread.category]
        if thread.community.lower() not in (s.lower() for s in allowed):
            problems.append(
                f"r/{thread.community} is not one of the {thread.category} subreddits ({', '.join(allowed)})"
            )
        if _reddit_thread_id(thread.url) != thread.id:
            problems.append(f"url does not point to thread {thread.id}: {thread.url}")

    id_counts = Counter(c.id for c in thread.comments)
    for dup in sorted(i for i, n in id_counts.items() if n > 1):
        problems.append(f"comment {dup} appears more than once")

    for comment in thread.comments:
        who = f"comment {comment.id}"
        if comment.parent_id is not None and comment.parent_id not in id_counts:
            problems.append(f"{who} replies to {comment.parent_id}, which is not in this thread")
        if thread.source == "reddit":
            url_thread = _reddit_thread_id(comment.url)
            if url_thread is None:
                problems.append(f"{who}: url is not a Reddit comment link: {comment.url}")
            elif url_thread != thread.id:
                problems.append(f"{who}: url points to thread {url_thread}, not {thread.id}: {comment.url}")
            elif comment.id not in _path_parts(comment.url):
                problems.append(f"{who}: url does not point to comment {comment.id}: {comment.url}")
        if _day(comment.created_at) < _day(thread.created_at):
            problems.append(
                f"{who}: created_at {_day(comment.created_at)} is before the thread was posted ({_day(thread.created_at)})"
            )

    dated = [("thread created_at", thread.created_at)]
    dated += [(f"comment {c.id}: created_at", c.created_at) for c in thread.comments]
    authors = [("thread author", thread.author)] + [(f"comment {c.id} author", c.author) for c in thread.comments]
    dated += [(f"{who} account_created_at", a.account_created_at) for who, a in authors if a and a.account_created_at]
    for what, when in dated:
        if _day(when) > _day(thread.collected_at):
            problems.append(f"{what} {_day(when)} is after collected_at {_day(thread.collected_at)}")
    return problems


def _path_parts(url: str) -> list[str]:
    return [part for part in urlparse(url).path.split("/") if part]


def _reddit_thread_id(url: str) -> str | None:
    """Reddit links look like /r/<subreddit>/comments/<thread id>/..."""
    parts = _path_parts(url)
    if "comments" in parts and parts.index("comments") + 1 < len(parts):
        return parts[parts.index("comments") + 1]
    return None


def _day(moment: datetime):
    # Compare calendar days, not times, because hand-typed dates often have no time.
    return moment.date()


def _field(loc: tuple) -> str:
    return ".".join(str(part) for part in loc) + ": " if loc else ""


# --- Labels ---

def _load_labels(root: Path, threads: list[Thread], unreadable: set[str], problems: list[str]) -> list[Label]:
    path = root / "labels.csv"
    if not path.is_file():
        problems.append(f"labels.csv is missing; create it with the header row: {','.join(LABEL_COLUMNS)}")
        return []

    # utf-8-sig drops the invisible marker Excel puts at the start of a file.
    text = path.read_text(encoding="utf-8-sig")
    header = text.splitlines()[0] if text else ""
    # Excel set to Italian saves CSVs with semicolons.
    delimiter = ";" if ";" in header and "," not in header else ","
    reader = csv.DictReader(text.splitlines(keepends=True), delimiter=delimiter)

    columns = [c.strip() for c in (reader.fieldnames or [])]
    missing = [c for c in LABEL_COLUMNS if c not in columns]
    unknown = [c for c in columns if c not in LABEL_COLUMNS + OPTIONAL_LABEL_COLUMNS]
    if missing:
        problems.append(f"labels.csv is missing column(s): {', '.join(missing)}")
    if unknown:
        problems.append(f"labels.csv has unknown column(s): {', '.join(unknown)}")
    if missing or unknown:
        return []
    reader.fieldnames = columns

    comments = {c.id: (t.id, c) for t in threads for c in t.comments}
    labels: list[Label] = []
    credibility_seen: dict[str, tuple[str, int]] = {}  # comment id -> (credibility, line)
    products_seen: dict[tuple[str, str], int] = {}  # (comment id, product) -> line
    with_products: set[str] = set()  # comment ids that have at least one product row
    no_product_seen: dict[str, int] = {}  # comment id -> line of its "no product" row

    for row in reader:
        line = reader.line_num
        where = f"labels.csv line {line}"
        if None in row:
            problems.append(f"{where}: more values than columns; put text that contains commas inside double quotes")
            continue
        if not any((v or "").strip() for v in row.values()):
            continue
        try:
            label = Label.model_validate(row)
        except ValidationError as e:
            problems.extend(f"{where}: {_field(err['loc'])}{err['msg']}" for err in e.errors())
            continue

        found = comments.get(label.comment_id)
        if found is None and label.thread_id in unreadable:
            continue  # the thread file's own problem is already reported; fix that first
        if found is None:
            problems.append(f"{where}: comment {label.comment_id} is not in any thread")
            continue
        thread_id, comment = found
        if thread_id != label.thread_id:
            problems.append(f"{where}: comment {label.comment_id} belongs to thread {thread_id}, not {label.thread_id}")
            continue
        if comment.status != "ok":
            problems.append(f"{where}: comment {label.comment_id} is {comment.status} and can't be labelled")
            continue

        if label.credibility:
            earlier = credibility_seen.setdefault(label.comment_id, (label.credibility, line))
            if earlier[0] != label.credibility:
                problems.append(
                    f"{where}: comment {label.comment_id} was rated {earlier[0]} on line {earlier[1]}; "
                    "credibility describes the comment, so use one rating for all its rows"
                )
        if label.product:
            key = (label.comment_id, label.product.casefold())
            if key in products_seen:
                problems.append(f"{where}: comment {label.comment_id} already has a label for {label.product!r} (line {products_seen[key]})")
            elif label.comment_id in no_product_seen:
                problems.append(f"{where}: comment {label.comment_id} already has a 'no product' row (line {no_product_seen[label.comment_id]})")
            products_seen.setdefault(key, line)
            with_products.add(label.comment_id)
        else:
            if label.comment_id in with_products:
                problems.append(f"{where}: comment {label.comment_id} has product rows, so it can't also have a 'no product' row")
            no_product_seen.setdefault(label.comment_id, line)
        labels.append(label)
    return labels


# --- Command line ---

def main(argv: list[str]) -> int:
    root = Path(argv[0]) if argv else DEFAULT_GOLD_DIR
    try:
        gold = load_gold_set(root)
    except GoldSetError as e:
        print(e)
        return 1
    by_category = {c: sum(t.category == c for t in gold.threads) for c in SUBREDDITS}
    n_comments = sum(len(t.comments) for t in gold.threads)
    labelled = {label.comment_id for label in gold.labels}
    mentions = sum(1 for label in gold.labels if label.product)
    print(
        f"Gold set OK: {len(gold.threads)} threads "
        f"({', '.join(f'{n} {c}' for c, n in by_category.items())}), {n_comments} comments, "
        f"{len(labelled)} labelled comments, {mentions} product mentions."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
