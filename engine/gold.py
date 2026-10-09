"""Loads and checks the hand-collected gold set in data/gold.

    data/gold/threads/<thread id>.json   one thread with its comments (shape: engine.models.Thread)
    data/gold/voices.csv                 one row per comment read: how credible the writer is (engine.models.VoiceLabel)
    data/gold/mentions.csv               one row per product mentioned: stance and evidence (engine.models.MentionLabel)

The loader never stops at the first mistake: it collects every problem, names the file and the
line or field, and raises them together, so a labelling session ends with one complete to-do list.

Run `python -m engine.gold` to check the gold set and print a summary, including how often the
"other" reason tag is used.
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

from engine.config import OTHER_TAG, OTHER_TAG_LIMIT, SUBREDDITS, THREAD_CATEGORIES
from engine.models import Comment, MentionLabel, Thread, VoiceLabel

DEFAULT_GOLD_DIR = Path(__file__).resolve().parents[1] / "data" / "gold"

VOICE_COLUMNS = ("thread_id", "comment_id", "voice", "tags")
MENTION_COLUMNS = ("comment_id", "product", "category", "stance", "evidence", "tags")
OPTIONAL_COLUMNS = ("note",)
VOICE_OPTIONAL_COLUMNS = ("note", "agrees")  # agrees: a reply agreeing with the comment above (8 Oct 2026)
MENTION_OPTIONAL_COLUMNS = ("note", "kind")  # kind: a kind of product, not a brand (9 Oct 2026)


class GoldSetError(Exception):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(f"{len(problems)} problem(s) in the gold set:\n" + "\n".join(f"- {p}" for p in problems))


@dataclass
class GoldSet:
    threads: list[Thread]
    voices: list[VoiceLabel]
    mentions: list[MentionLabel]

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
    voices, skipped = _load_voices(root, threads, unreadable, problems)
    mentions = _load_mentions(root, threads, voices, skipped, problems)
    if problems:
        raise GoldSetError(problems)
    return GoldSet(threads=threads, voices=voices, mentions=mentions)


def load_threads(folder: Path) -> list[Thread]:
    """Loads and checks the thread files in a folder, without the label files. Retrieval reads threads this way."""
    problems: list[str] = []
    threads, _ = _load_thread_folder(Path(folder), problems)
    if problems:
        raise GoldSetError(problems)
    return threads


# --- Threads ---

def _load_threads(root: Path, problems: list[str]) -> tuple[list[Thread], set[str]]:
    return _load_thread_folder(root / "threads", problems)


def _load_thread_folder(folder: Path, problems: list[str]) -> tuple[list[Thread], set[str]]:
    """Returns the threads that loaded, plus the ids of thread files that couldn't be read."""
    if not folder.is_dir():
        problems.append(f"{folder.name}/ folder is missing")
        return [], set()

    threads: list[Thread] = []
    unreadable: set[str] = set()
    seen_comments: dict[str, str] = {}  # comment id -> thread id, to catch the same comment pasted into two threads
    for path in sorted(folder.glob("*.json")):
        where = f"{folder.name}/{path.name}"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            problems.append(f"{where}: not valid JSON (line {e.lineno}, column {e.colno}): {e.msg}")
            unreadable.add(path.stem)
            continue
        try:
            thread = Thread.model_validate(raw)
        except ValidationError as e:
            problems.extend(f"{where}: {_describe(err)}" for err in e.errors())
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


def _describe(error: dict) -> str:
    """One pydantic error as "field.path: message"."""
    field = ".".join(str(part) for part in error["loc"])
    message = error["msg"].removeprefix("Value error, ")
    return f"{field}: {message}" if field else message


# --- Labels ---

def _read_csv(
    root: Path, name: str, columns: tuple[str, ...], problems: list[str], optional: tuple[str, ...] = OPTIONAL_COLUMNS
) -> list[tuple[int, dict]]:
    """Returns (line number, row) for every non-blank row, or nothing if the file or its header is wrong."""
    path = root / name
    if not path.is_file():
        problems.append(f"{name} is missing; create it with the header row: {','.join(columns + optional)}")
        return []

    # utf-8-sig drops the invisible marker Excel puts at the start of a file.
    text = path.read_text(encoding="utf-8-sig")
    header = text.splitlines()[0] if text else ""
    # Excel set to Italian saves CSVs with semicolons.
    delimiter = ";" if ";" in header and "," not in header else ","
    reader = csv.DictReader(text.splitlines(keepends=True), delimiter=delimiter)

    found = [c.strip() for c in (reader.fieldnames or [])]
    missing = [c for c in columns if c not in found]
    unknown = [c for c in found if c not in columns + optional]
    if missing:
        problems.append(f"{name} is missing column(s): {', '.join(missing)}")
    if unknown:
        problems.append(f"{name} has unknown column(s): {', '.join(unknown)}")
    if missing or unknown:
        return []
    reader.fieldnames = found

    rows = []
    for row in reader:
        if None in row:
            problems.append(
                f"{name} line {reader.line_num}: more values than columns; "
                "put text that contains commas inside double quotes"
            )
        elif any((v or "").strip() for v in row.values()):
            rows.append((reader.line_num, row))
    return rows


def _load_voices(
    root: Path, threads: list[Thread], unreadable: set[str], problems: list[str]
) -> tuple[list[VoiceLabel], set[str]]:
    """Returns the valid voice labels, plus the ids of comments whose voice row was skipped.

    Mentions of a skipped comment are not reported again: the voice row's own problem comes first.
    """
    comments = {c.id: (t.id, c) for t in threads for c in t.comments}
    voices: list[VoiceLabel] = []
    skipped: set[str] = set()
    first_line: dict[str, int] = {}  # comment id -> line of its voice row

    for line, row in _read_csv(root, "voices.csv", VOICE_COLUMNS, problems, VOICE_OPTIONAL_COLUMNS):
        where = f"voices.csv line {line}"
        try:
            label = VoiceLabel.model_validate(row)
        except ValidationError as e:
            problems.extend(f"{where}: {_describe(err)}" for err in e.errors())
            skipped.add((row.get("comment_id") or "").strip())
            continue

        found = comments.get(label.comment_id)
        if found is None:
            if label.thread_id not in unreadable:  # otherwise the thread file's own problem is already reported
                problems.append(f"{where}: comment {label.comment_id} is not in any thread")
            skipped.add(label.comment_id)
            continue
        thread_id, comment = found
        if thread_id != label.thread_id:
            problems.append(f"{where}: comment {label.comment_id} belongs to thread {thread_id}, not {label.thread_id}")
            skipped.add(label.comment_id)
            continue
        if comment.status != "ok":
            problems.append(f"{where}: comment {label.comment_id} is {comment.status} and can't be labelled")
            skipped.add(label.comment_id)
            continue
        if label.agrees and comment.parent_id is None:
            problems.append(f"{where}: comment {label.comment_id} isn't a reply, so it can't agree with the comment above")
        if label.comment_id in first_line:
            problems.append(
                f"{where}: comment {label.comment_id} already has a voice label (line {first_line[label.comment_id]}); one per comment"
            )
            continue
        first_line[label.comment_id] = line
        voices.append(label)
    return voices, skipped


def _load_mentions(
    root: Path, threads: list[Thread], voices: list[VoiceLabel], skipped: set[str], problems: list[str]
) -> list[MentionLabel]:
    comment_ids = {c.id for t in threads for c in t.comments}
    voice_of = {v.comment_id: v.voice for v in voices}
    mentions: list[MentionLabel] = []
    seen: dict[tuple[str, str], int] = {}  # (comment id, product) -> line

    for line, row in _read_csv(root, "mentions.csv", MENTION_COLUMNS, problems, MENTION_OPTIONAL_COLUMNS):
        where = f"mentions.csv line {line}"
        try:
            label = MentionLabel.model_validate(row)
        except ValidationError as e:
            problems.extend(f"{where}: {_describe(err)}" for err in e.errors())
            continue

        if label.comment_id in skipped:
            continue  # its voice row's problem is already reported
        if label.comment_id not in comment_ids:
            problems.append(f"{where}: comment {label.comment_id} is not in any thread")
            continue
        if label.comment_id not in voice_of:
            problems.append(f"{where}: comment {label.comment_id} has no voice label; add its row to voices.csv first")
            continue
        if voice_of[label.comment_id] is None:
            problems.append(f"{where}: comment {label.comment_id} has product mentions, so it needs a voice level and tags in voices.csv")
            continue
        key = (label.comment_id, label.product.casefold())
        if key in seen:
            problems.append(f"{where}: comment {label.comment_id} already has a label for {label.product!r} (line {seen[key]})")
            continue
        seen[key] = line
        mentions.append(label)
    return mentions


# --- How often "other" is used ---

@dataclass
class OtherTagUsage:
    """How many labels of one kind fall back on the "other" tag, and the notes they give."""

    kind: str  # "voice" or "evidence"
    used: int
    total: int
    notes: list[str]

    @property
    def rate(self) -> float:
        return self.used / self.total if self.total else 0.0

    @property
    def needs_work(self) -> bool:
        return self.rate > OTHER_TAG_LIMIT

    def __str__(self) -> str:
        line = f'{self.kind} tags: "{OTHER_TAG}" used in {self.used} of {self.total} labels ({self.rate:.0%})'
        if self.needs_work:
            line += f"; more than {OTHER_TAG_LIMIT:.0%}, so the {self.kind} tag list needs work"
        return line


def other_tag_usage(gold: GoldSet) -> tuple[OtherTagUsage, OtherTagUsage]:
    usages = []
    voiced = [v for v in gold.voices if v.voice is not None]  # a comment with no product has no voice to count
    for kind, labels in (("voice", voiced), ("evidence", gold.mentions)):
        with_other = [label for label in labels if OTHER_TAG in label.tags]
        usages.append(OtherTagUsage(kind, len(with_other), len(labels), [label.note for label in with_other]))
    return tuple(usages)


def print_other_tag_report(gold: GoldSet) -> None:
    for usage in other_tag_usage(gold):
        print(usage)
        for note in usage.notes:
            print(f"  - {note}")


# --- Command line ---

def main(argv: list[str]) -> int:
    root = Path(argv[0]) if argv else DEFAULT_GOLD_DIR
    try:
        gold = load_gold_set(root)
    except GoldSetError as e:
        print(e)
        return 1
    by_category = {c: sum(t.category == c for t in gold.threads) for c in THREAD_CATEGORIES}
    n_comments = sum(len(t.comments) for t in gold.threads)
    print(
        f"Gold set OK: {len(gold.threads)} threads "
        f"({', '.join(f'{n} {c}' for c, n in by_category.items())}), {n_comments} comments, "
        f"{len(gold.voices)} labelled comments, {len(gold.mentions)} product mentions."
    )
    print_other_tag_report(gold)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
