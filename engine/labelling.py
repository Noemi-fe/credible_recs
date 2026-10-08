"""Labelling: the page Noemi labels a gold-set thread on, and the import that adds her labels to the gold set.

Labelling in a spreadsheet is slow and easy to get wrong: a misspelt tag, a comment id typed wrong, a tag cell
without its quotes. So the labelling happens on a web page made for it, and one command adds the result:

    data/gold/threads/<thread id>.json     the thread to label (fetched with engine.parse_reddit)
    data/gold/labelling/<thread id>.html   its labelling page: one file that opens in any browser, offline
    labels_<thread id>.json                what the page's Export button downloads
    data/gold/voices.csv, mentions.csv     where `import` adds the labels (the format: data/gold/README.md)

The page lists the thread's comments in order, each reply under the comment it answers, with its author
(linked to their Reddit profile, to check the account's age), flair, score and date. Deleted and removed
comments are greyed out and can't be labelled. Each other comment gets:
- "No product in this comment", or one row per product mentioned: product, category, stance, evidence,
  evidence tags and a note;
- a voice level, voice tags and a note. A comment with products needs a voice level and a tag; a comment with
  no product needs neither (Noemi, 8 Oct 2026), so its voice is hidden unless she asks for it;
- for a reply, "Agrees with the comment above" ("This!", "Same, mine lasted 10 years"): evidence that the
  other writer is credible.
The levels, tags and choices come from engine/config.py. Keyboard shortcuts: j/k next/previous comment, 1/2/3
voice high/medium/low, n no product, a agrees, p add a product. Labels are saved in the browser as she goes, so
closing the tab loses nothing. Export checks every label (required fields, "other" needs a note, no product
twice in one comment), lists any problem with its comment, and only then downloads the file. Only the comments
she labelled are exported: a thread can be labelled in several sittings, or only in part.

The page holds Reddit text, so it stays on this machine (git ignores data/gold/labelling/). Nothing on it is
loaded from the internet; its only links go to Reddit itself.

The import checks every label with the gold set's own rules (engine.models.VoiceLabel and MentionLabel) and
against the thread before writing anything. It refuses a thread that already has labels, unless --replace,
which swaps that thread's rows for the file's. Rows already in the files are kept exactly as typed. After
writing, it checks the whole gold set (engine.gold) and, if anything is wrong, puts both files back as they were.

Command line:
    python -m engine.labelling page <thread id> [--open]        write the thread's labelling page (--open: open it too)
    python -m engine.labelling import <labels file> [--replace]  add an exported file's labels to the gold set
"""

import codecs
import csv
import io
import json
import re
import subprocess
import sys
import webbrowser
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from urllib.parse import quote, urlparse

from pydantic import ValidationError

from engine.config import (
    EVIDENCE_LEVELS,
    EVIDENCE_TAGS,
    MENTION_CATEGORIES,
    OTHER_TAG,
    STANCE_VALUE,
    VOICE_LEVELS,
    VOICE_TAGS,
)
from engine.gold import (
    DEFAULT_GOLD_DIR,
    MENTION_COLUMNS,
    OPTIONAL_COLUMNS,
    VOICE_COLUMNS,
    VOICE_OPTIONAL_COLUMNS,
    GoldSetError,
    _describe,
    _reddit_thread_id,
    load_gold_set,
)
from engine.gold import main as print_gold_check
from engine.models import Comment, Id, MentionLabel, Record, Thread, UtcDatetime, VoiceLabel

# The voice rule, as one switch for both the page and the import. False (Noemi, 8 Oct 2026): a comment with no
# product needs no voice label, because no metric uses it and skipping it saves time; it is still written to
# voices.csv, with the voice and tags left blank, as a comment she read. True would ask for a voice level and a
# voice tag on every comment read. A comment with products always needs both.
VOICE_REQUIRED_WITHOUT_PRODUCT = False

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = Path(__file__).resolve().parent / "templates" / "labelling.html"
GUIDE_NAME = "LABELLING_GUIDE.md"  # in data/gold; shown on the page when it exists
REDDIT = "https://www.reddit.com"
PARENT_EXCERPT_CHARS = 120  # how much of the comment a reply answers is shown above the reply


class LabellingError(Exception):
    """Why a page couldn't be made or a labels file couldn't be imported, with every problem found."""

    def __init__(self, message: str, problems: list[str] | None = None):
        self.message = message
        self.problems = problems or []
        super().__init__("\n".join([message] + [f"- {p}" for p in self.problems]))


def read_thread(thread_id: str, gold_dir: Path = DEFAULT_GOLD_DIR) -> Thread:
    """Reads data/gold/threads/<thread id>.json, or says plainly why it can't."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", thread_id):
        raise LabellingError(f"{thread_id!r} is not a thread id: it is the part after /comments/ in the thread's link.")
    folder = Path(gold_dir) / "threads"
    path = folder / f"{thread_id}.json"
    if not path.is_file():
        there = sorted(p.stem for p in folder.glob("*.json")) if folder.is_dir() else []
        listing = f"Threads there: {', '.join(there)}." if there else "There are no threads there yet."
        raise LabellingError(f"Thread {thread_id} is not in the gold set: there is no {_shown(path)}. {listing}")
    try:
        return Thread.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError as e:
        raise LabellingError(
            f"{path.name} can't be read (`python -m engine.gold` checks it too):", [_describe(err) for err in e.errors()]
        ) from None


# --- The labelling page ---

def write_page(thread_id: str, gold_dir: Path = DEFAULT_GOLD_DIR, now: datetime | None = None) -> Path:
    """Writes data/gold/labelling/<thread id>.html for one gold-set thread and returns where it is.

    Writing it again replaces the page but not the labels typed on it: those are kept by the browser.
    """
    gold_dir = Path(gold_dir)
    thread = read_thread(thread_id, gold_dir)
    guide_path = gold_dir / GUIDE_NAME
    guide = guide_path.read_text(encoding="utf-8") if guide_path.is_file() else None
    path = gold_dir / "labelling" / f"{thread.id}.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_page(thread, guide, now), encoding="utf-8")
    return path


def render_page(thread: Thread, guide: str | None = None, now: datetime | None = None) -> str:
    """The whole labelling page as one HTML file: the template in engine/templates, filled in for this thread.

    Every piece of Reddit text is escaped, so a comment containing "<script>" shows those characters and is
    never run or drawn as HTML. The page's script reads the levels, tags and comments from a settings block.
    """
    now = now or datetime.now(UTC)
    ordered = _in_thread_order(thread.comments)
    usable = [comment for comment, _ in ordered if comment.status == "ok"]
    by_id = {comment.id: comment for comment in reversed(thread.comments)}  # the first copy wins, as on Reddit
    values = {
        "PAGE_TITLE": escape(f"Label {thread.id}: {thread.title}"),
        "BAR_TITLE": escape(thread.title),
        "PROGRESS": f"0 of {len(usable)} comments labelled",
        "SHORTCUTS": _shortcuts_html(),
        "THREAD": _thread_html(thread, now),
        "GUIDE": _guide_html(guide),
        "COMMENTS": "\n".join(_comment_html(comment, depth, by_id, thread, now) for comment, depth in ordered),
        "CONFIG": _settings_json(thread, usable),
        "VOICE_REQUIRED_WITHOUT_PRODUCT": "true" if VOICE_REQUIRED_WITHOUT_PRODUCT else "false",
    }
    template = TEMPLATE.read_text(encoding="utf-8")
    # One pass, so text put in a slot is never searched for slots itself.
    return re.sub(r"\{\{([A-Z_]+)\}\}", lambda slot: values[slot.group(1)], template)


def _in_thread_order(comments: list[Comment]) -> list[tuple[Comment, int]]:
    """Every comment with its depth (0 for a direct reply to the post), each reply right after the comment it answers.

    Comments keep their order in the file among their siblings. A reply whose parent isn't in the file is shown
    as a direct reply to the post.
    """
    ids = {c.id for c in comments}
    replies: dict[str, list[Comment]] = {}
    top = []
    for comment in comments:
        if comment.parent_id in ids and comment.parent_id != comment.id:
            replies.setdefault(comment.parent_id, []).append(comment)
        else:
            top.append(comment)
    ordered: list[tuple[Comment, int]] = []
    seen: set[int] = set()
    stack = [(comment, 0) for comment in reversed(top)]
    while stack:  # a loop rather than recursion, so a very long reply chain can't hit Python's limit
        comment, depth = stack.pop()
        if id(comment) in seen:
            continue
        seen.add(id(comment))
        ordered.append((comment, depth))
        stack.extend((reply, depth + 1) for reply in reversed(replies.get(comment.id, [])))
    # Comments caught in a loop of replies (impossible on Reddit, but a hand-edited file could have one).
    ordered.extend((comment, 0) for comment in comments if id(comment) not in seen)
    return ordered


def _shortcuts_html() -> str:
    numbers = " ".join(f"<kbd>{n}</kbd>" for n in range(1, len(VOICE_LEVELS) + 1))
    shortcuts = [
        ("<kbd>j</kbd> <kbd>k</kbd>", "next / previous comment"),
        (numbers, "voice " + " / ".join(escape(level) for level in VOICE_LEVELS)),
        ("<kbd>n</kbd>", "no product"),
        ("<kbd>a</kbd>", "agrees with the comment above"),
        ("<kbd>p</kbd>", "add a product"),
        ("<kbd>Esc</kbd>", "leave a text box"),
    ]
    return "".join(f"<span>{keys} {what}</span>" for keys, what in shortcuts)


def _thread_html(thread: Thread, now: datetime) -> str:
    meta = [
        f"r/{escape(thread.community)}",
        f"posted {_date(thread.created_at)} ({_ago(thread.created_at, now)})",
        f"by {_author_html(thread.author)}",
        _count(thread.score, "point"),
        f"{_count(thread.num_comments, 'comment')} on Reddit, {len(thread.comments)} saved",
    ]
    link = _reddit_link(thread.url, "Open the thread on Reddit")
    if link:
        meta.append(link)
    body = f'\n<div class="post-body">{escape(thread.body)}</div>' if thread.body.strip() else ""
    spans = "".join(f"<span>{item}</span>" for item in meta)
    return f'<section class="thread">\n<h1>{escape(thread.title)}</h1>\n<p class="thread-meta">{spans}</p>{body}\n</section>'


def _guide_html(guide: str | None) -> str:
    if not guide or not guide.strip():
        return ""
    return f'<details class="guide"><summary>Labelling guide</summary><pre>{escape(guide)}</pre></details>'


def _comment_html(comment: Comment, depth: int, by_id: dict[str, Comment], thread: Thread, now: datetime) -> str:
    if comment.status != "ok":
        # Nothing of a deleted or removed comment is shown: not its text, author or id. It is there only so
        # the replies to it keep their place.
        return (
            f'<article class="comment gone" data-depth="{depth}" style="--depth: {depth}">'
            f"<p>[{comment.status}] This comment was {comment.status} on Reddit, so it can't be labelled.</p></article>"
        )

    author = comment.author
    meta = [_author_html(author, css="author")]
    if author and thread.author and author.name == thread.author.name:
        meta.append('<span class="op" title="The person who started the thread">OP</span>')
    if author and author.flair:
        meta.append(f'<span class="flair">{escape(author.flair)}</span>')
    meta.append(f"<span>{_count(comment.score, 'point')}</span>")
    meta.append(f'<span title="{comment.created_at:%Y-%m-%d %H:%M} UTC">{_date(comment.created_at)} · {_ago(comment.created_at, now)}</span>')
    if author and author.account_created_at:
        meta.append(f"<span>account since {author.account_created_at:%b %Y}</span>")
    if author and author.karma is not None:
        meta.append(f"<span>{author.karma:,} karma</span>")
    link = _reddit_link(comment.url, "on Reddit")
    if link:
        meta.append(link)
    meta.append('<span class="state"></span>')

    parent = by_id.get(comment.parent_id) if comment.parent_id else None
    if parent is None:
        answers = ""
    elif parent.status != "ok":
        answers = f'\n<p class="parent">↳ Replying to a comment now <span class="parent-text">[{parent.status}]</span></p>'
    else:
        who = f"u/{escape(parent.author.name)}" if parent.author else "a deleted account"
        answers = f'\n<p class="parent">↳ Replying to {who}: “<span class="parent-text">{escape(_excerpt(parent.body))}</span>”</p>'

    return (
        f'<article class="comment" id="comment-{comment.id}" data-id="{comment.id}" data-depth="{depth}" '
        f'style="--depth: {depth}" tabindex="-1">\n'
        f'<div class="meta">{"".join(meta)}</div>{answers}\n'
        f'<div class="body">{escape(comment.body)}</div>\n'
        f'<div class="controls"></div>\n'
        f"</article>"
    )


def _author_html(author, css: str = "") -> str:
    """u/name linked to the Reddit profile (where the account's age shows), or "deleted account"."""
    if author is None:
        return f'<span class="{css} deleted">deleted account</span>' if css else "a deleted account"
    url = f"{REDDIT}/user/{quote(author.name, safe='')}"
    return (
        f'<a class="{css}" href="{escape(url)}" target="_blank" rel="noopener noreferrer" '
        f'title="Their Reddit profile shows the account\'s age">u/{escape(author.name)}</a>'
    )


def _reddit_link(url: str, text: str) -> str:
    """A link that opens in a new tab, but only to Reddit: the page never links anywhere else."""
    parts = urlparse(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not (host == "reddit.com" or host.endswith(".reddit.com")):
        return ""
    return f'<a href="{escape(url)}" target="_blank" rel="noopener noreferrer">{escape(text)}</a>'


def _settings_json(thread: Thread, usable: list[Comment]) -> str:
    """What the page's script needs, as JSON that is safe inside a <script> block."""
    settings = {
        "threadId": thread.id,
        "threadCategory": thread.category,  # a new product row starts in the thread's category
        "voiceLevels": list(VOICE_LEVELS),
        "evidenceLevels": list(EVIDENCE_LEVELS),
        "voiceTags": list(VOICE_TAGS),
        "evidenceTags": list(EVIDENCE_TAGS),
        "otherTag": OTHER_TAG,
        "categories": list(MENTION_CATEGORIES),
        "stances": list(STANCE_VALUE),
        "comments": [
            {"id": c.id, "author": c.author.name if c.author else None, "reply": c.parent_id is not None} for c in usable
        ],
    }
    text = json.dumps(settings, ensure_ascii=False)
    # "</script>" in a username could otherwise end the block early.
    return text.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def _excerpt(text: str, limit: int = PARENT_EXCERPT_CHARS) -> str:
    """The start of a comment on one line: about `limit` characters, cut between words, with "…" if cut."""
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    cut = flat[:limit]
    space = cut.rfind(" ")
    if space > limit * 2 // 3:
        cut = cut[:space]
    return cut.rstrip(" ,.;:") + "…"


def _date(moment: datetime) -> str:
    return f"{moment.day} {moment:%b %Y}"


def _ago(moment: datetime, now: datetime) -> str:
    days = max((now - moment).days, 0)
    if days == 0:
        return "today"
    if days < 31:
        return f"{_count(days, 'day')} ago"
    if days < 365:
        return f"{_count(max(days // 30, 1), 'month')} ago"
    return f"{_count(days // 365, 'year')} ago"


def _count(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


# --- The labels file the page exports ---

class ExportedMention(Record):
    product: str
    category: str | None
    stance: str | None
    evidence: str | None
    evidence_tags: list[str]
    note: str | None = None


class ExportedComment(Record):
    comment_id: Id
    no_product: bool
    voice: str | None
    voice_tags: list[str]
    voice_note: str | None = None
    agrees: bool = False
    mentions: list[ExportedMention]


class LabelsFile(Record):
    """labels_<thread id>.json, as the page's Export button writes it. Values are checked later, row by row."""

    thread_id: Id
    exported_at: UtcDatetime
    comments: list[ExportedComment]


def read_labels(path: Path) -> LabelsFile:
    path = Path(path)
    if not path.is_file():
        raise LabellingError(
            f"There is no file {path}. The page's Export button saves labels_<thread id>.json, usually in your Downloads folder."
        )
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise LabellingError(f"Nothing was written: {path.name} is not valid JSON ({e}). Export it again from the labelling page.") from None
    try:
        return LabelsFile.model_validate(raw)
    except ValidationError as e:
        raise LabellingError(
            f"Nothing was written: {path.name} is not a labels file exported from the labelling page:",
            [_describe(err) for err in e.errors()],
        ) from None


def check_labels(labels: LabelsFile, thread: Thread) -> tuple[list[VoiceLabel], list[MentionLabel], list[str]]:
    """Turns the exported labels into gold-set rows, checked with the gold set's own rules.

    Returns the voice rows, the mention rows and every problem found, each naming its comment. Rows are checked
    exactly as they will be written, so what passes here is what engine.gold will read back.
    """
    comments = {c.id: c for c in reversed(thread.comments)}
    voices: list[VoiceLabel] = []
    mentions: list[MentionLabel] = []
    problems: list[str] = []
    seen: set[str] = set()

    for entry in labels.comments:
        comment = comments.get(entry.comment_id)
        if comment is None:
            problems.append(f"comment {entry.comment_id} is not in thread {thread.id}")
            continue
        who = f"comment {comment.id}" + (f" (u/{comment.author.name})" if comment.author else "")
        if comment.status != "ok":
            problems.append(f"{who} is {comment.status} on Reddit and can't be labelled")
            continue
        if comment.id in seen:
            problems.append(f"{who} appears more than once in the file; keep one entry per comment")
            continue
        seen.add(comment.id)

        if entry.no_product and entry.mentions:
            problems.append(f'{who}: says "no product" but lists {_count(len(entry.mentions), "product")}; keep one or the other')
        if not entry.no_product and not entry.mentions:
            problems.append(f'{who}: neither "no product" nor any product; tick "No product" or add the products')
        voice = _tidy(entry.voice)
        if entry.mentions and not voice:
            problems.append(f"{who}: has products, so it needs a voice level and at least one voice tag")
        elif entry.no_product and VOICE_REQUIRED_WITHOUT_PRODUCT and not voice:
            problems.append(f"{who}: needs a voice level and at least one voice tag (every comment read gets one)")
        if entry.agrees and comment.parent_id is None:
            problems.append(f"{who}: isn't a reply, so it can't agree with the comment above")

        row = {
            "thread_id": thread.id,
            "comment_id": comment.id,
            "voice": voice,
            "tags": ", ".join(entry.voice_tags),
            "note": _tidy(entry.voice_note),
            "agrees": "yes" if entry.agrees else "",
        }
        try:
            voices.append(VoiceLabel.model_validate(row))
        except ValidationError as e:
            names = {"": "voice", "voice": "voice level", "tags": "voice tags", "note": "voice note"}
            problems.extend(f"{who}: {_explain(err, names)}" for err in e.errors())

        products: dict[str, int] = {}  # product name, as compared -> its number in the comment
        for n, mention in enumerate(entry.mentions, start=1):
            name = _tidy(mention.product)
            what = f"{who}, product {n}" + (f' ("{name}")' if name else "")
            if not name:
                problems.append(f"{what}: the product name is empty; type the product as you'd name it")
                continue
            if name.casefold() in products:
                problems.append(f"{what}: listed twice in this comment (also product {products[name.casefold()]}); keep one row per product")
                continue
            products[name.casefold()] = n
            row = {
                "comment_id": comment.id,
                "product": name,
                "category": mention.category,
                "stance": mention.stance,
                "evidence": mention.evidence,
                "tags": ", ".join(mention.evidence_tags),
                "note": _tidy(mention.note),
            }
            try:
                mentions.append(MentionLabel.model_validate(row))
            except ValidationError as e:
                problems.extend(f"{what}: {_explain(err, {'tags': 'evidence tags'})}" for err in e.errors())
    return voices, mentions, problems


def _tidy(text: str | None) -> str:
    """Spaces as typed don't matter: trimmed, and runs of spaces or line breaks made one space."""
    return " ".join((text or "").split())


def _explain(error: dict, names: dict[str, str]) -> str:
    """One pydantic error as "field: message", with the field named as on the page."""
    where = ".".join(str(part) for part in error["loc"])
    where = names.get(where, where)
    message = error["msg"].removeprefix("Value error, ")
    return f"{where}: {message}" if where else message


# --- Adding labels to the gold set ---

@dataclass
class ImportResult:
    thread_id: str
    comments: int  # labelled comments in the file, each one row in voices.csv
    voices_added: int
    mentions_added: int
    voices_removed: int = 0  # with --replace: the thread's earlier rows
    mentions_removed: int = 0
    no_longer_labelled: list[str] = field(default_factory=list)  # labelled before --replace, not in the new file


def import_labels(labels_file: Path, gold_dir: Path = DEFAULT_GOLD_DIR, replace: bool = False) -> ImportResult:
    """Adds an exported labels file to voices.csv and mentions.csv, or raises LabellingError and changes nothing.

    In order: the file and every label in it are checked against the thread; the gold set must already be
    clean; the thread must have no labels yet (with `replace`, its rows are removed instead); the rows are
    added after the ones already there; then the whole gold set is checked again, and if that fails both
    files are put back exactly as they were. A label file that doesn't exist yet is created with the standard
    header, and removed again if the import fails.
    """
    gold_dir = Path(gold_dir)
    labels = read_labels(labels_file)
    thread = read_thread(labels.thread_id, gold_dir)
    voices, mentions, problems = check_labels(labels, thread)
    name = Path(labels_file).name
    if problems:
        raise LabellingError(
            f"Nothing was written: {_count(len(problems), 'problem')} in {name}. "
            "Fix them on the labelling page, export again and import the new file:",
            problems,
        )
    if not voices:
        raise LabellingError(f"Nothing was written: {name} holds no labelled comment.")

    paths = {"voices": gold_dir / "voices.csv", "mentions": gold_dir / "mentions.csv"}
    originals = {path: path.read_bytes() if path.is_file() else None for path in paths.values()}
    try:
        _create_missing(paths, originals)
        _check_gold_set_before(gold_dir)
        result = _write_rows(paths, thread, voices, mentions, replace, name)
        _check_gold_set_after(gold_dir)
    except BaseException:
        _put_back(originals)
        raise
    return result


NEW_FILE_HEADERS = {
    "voices": ",".join(VOICE_COLUMNS + VOICE_OPTIONAL_COLUMNS),
    "mentions": ",".join(MENTION_COLUMNS + OPTIONAL_COLUMNS),
}


def _create_missing(paths: dict[str, Path], originals: dict[Path, bytes | None]) -> None:
    for kind, path in paths.items():
        if originals[path] is None:
            path.write_text(NEW_FILE_HEADERS[kind] + "\n", encoding="utf-8")


def _check_gold_set_before(gold_dir: Path) -> None:
    try:
        load_gold_set(gold_dir)
    except GoldSetError as e:
        raise LabellingError(
            f"Nothing was written: the gold set already has {_count(len(e.problems), 'problem')}. "
            "Fix them first (`python -m engine.gold` lists them too):",
            e.problems,
        ) from None


def _check_gold_set_after(gold_dir: Path) -> None:
    try:
        load_gold_set(gold_dir)
    except GoldSetError as e:
        raise LabellingError(
            "Nothing was imported: the gold check failed after writing, so voices.csv and mentions.csv are back "
            "exactly as they were:",
            e.problems,
        ) from None


def _write_rows(
    paths: dict[str, Path], thread: Thread, voices: list[VoiceLabel], mentions: list[MentionLabel], replace: bool, name: str
) -> ImportResult:
    voice_file = _LabelFile.read(paths["voices"])
    mention_file = _LabelFile.read(paths["mentions"])
    comment_ids = {c.id for c in thread.comments}
    old_voices = [r for r in voice_file.rows if r.values.get("thread_id") == thread.id or r.values.get("comment_id") in comment_ids]
    old_mentions = [r for r in mention_file.rows if r.values.get("comment_id") in comment_ids]
    if (old_voices or old_mentions) and not replace:
        raise LabellingError(
            f"Nothing was written: thread {thread.id} already has labels "
            f"({_count(len(old_voices), 'row')} in voices.csv, {_count(len(old_mentions), 'row')} in mentions.csv).",
            [
                f"To swap them for the labels in {name}, run the same command again with --replace at the end.",
                "The page exports every comment labelled in that browser, so its file normally holds the earlier "
                "labels too; after replacing, any comment that is no longer labelled is named.",
            ],
        )

    _replace_file(voice_file.path, voice_file.updated(old_voices, [_voice_row(v) for v in voices]))
    _replace_file(mention_file.path, mention_file.updated(old_mentions, [_mention_row(m) for m in mentions]))
    labelled_now = {v.comment_id for v in voices}
    return ImportResult(
        thread_id=thread.id,
        comments=len(voices),
        voices_added=len(voices),
        mentions_added=len(mentions),
        voices_removed=len(old_voices),
        mentions_removed=len(old_mentions),
        no_longer_labelled=list(dict.fromkeys(
            r.values["comment_id"] for r in old_voices if r.values.get("comment_id") not in labelled_now
        )),
    )


def _voice_row(label: VoiceLabel) -> dict[str, str]:
    return {
        "thread_id": label.thread_id,
        "comment_id": label.comment_id,
        "voice": label.voice or "",
        "tags": ", ".join(label.tags),
        "note": label.note or "",
        "agrees": "yes" if label.agrees else "",
    }


def _mention_row(label: MentionLabel) -> dict[str, str]:
    return {
        "comment_id": label.comment_id,
        "product": label.product,
        "category": label.category,
        "stance": label.stance,
        "evidence": label.evidence,
        "tags": ", ".join(label.tags),
        "note": label.note or "",
    }


@dataclass
class _Row:
    text: str  # the row exactly as it is in the file, line ending included
    values: dict[str, str]  # its values by column name


@dataclass
class _LabelFile:
    """One label CSV as it is on disk, so rows can be added or removed without retyping the others."""

    path: Path
    bom: bool  # the invisible marker Excel puts at the start; kept if it was there
    delimiter: str
    newline: str
    header: str  # the header line as typed, without its line ending
    columns: list[str]  # the column names, as engine.gold reads them
    rows: list[_Row]

    @classmethod
    def read(cls, path: Path) -> "_LabelFile":
        raw = path.read_bytes()
        lines = raw.decode("utf-8-sig").splitlines(keepends=True)  # split as engine.gold splits it
        first = lines[0] if lines else ""
        header = first.rstrip("\r\n")
        # The rule engine.gold reads the file with: semicolons when the header has them and no commas (Excel in Italian).
        delimiter = ";" if ";" in header and "," not in header else ","
        columns = [c.strip() for c in next(csv.reader([header], delimiter=delimiter), [])]
        rows = []
        reader = csv.reader(lines[1:], delimiter=delimiter)
        start = 0
        for values in reader:
            # A row can span several lines when a quoted cell holds a line break.
            text = "".join(lines[1 + start:1 + reader.line_num])
            rows.append(_Row(text, {column: value.strip() for column, value in zip(columns, values)}))
            start = reader.line_num
        newline = "\r\n" if first.endswith("\r\n") else "\n"
        return cls(path, raw.startswith(codecs.BOM_UTF8), delimiter, newline, header, columns, rows)

    def updated(self, remove: list[_Row], add: list[dict[str, str]]) -> bytes:
        """The file's new content: the rows in `remove` taken out, the rest as typed, then the new rows.

        An optional column the new rows need (note, agrees) is added to the header; rows already there simply
        have it blank.
        """
        header, columns = self.header, list(self.columns)
        for column in ("note", "agrees"):
            if column not in columns and any(row.get(column) for row in add):
                header += self.delimiter + column
                columns.append(column)
        removed = {id(row) for row in remove}
        text = header + self.newline + "".join(row.text for row in self.rows if id(row) not in removed)
        if not text.endswith(("\n", "\r")):
            text += self.newline  # the last row had no line ending: the new rows must not join it
        out = io.StringIO()
        writer = csv.writer(out, delimiter=self.delimiter, lineterminator=self.newline)  # quotes cells only when needed
        for row in add:
            writer.writerow([row.get(column, "") for column in columns])
        data = (text + out.getvalue()).encode("utf-8")
        return codecs.BOM_UTF8 + data if self.bom else data


def _replace_file(path: Path, data: bytes) -> None:
    # Written to a temporary file, then swapped in whole, so an interruption never leaves half a file.
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    temporary.replace(path)


def _put_back(originals: dict[Path, bytes | None]) -> None:
    """Restores each file byte for byte, or removes it if it didn't exist before. A file never changed is left untouched."""
    for path, data in originals.items():
        if data is None:
            path.unlink(missing_ok=True)
        elif not path.is_file() or path.read_bytes() != data:
            _replace_file(path, data)


# --- Command line ---

def _open_in_browser(path: Path) -> None:
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)
    else:
        webbrowser.open(Path(path).resolve().as_uri())


def _thread_id_from(text: str) -> str:
    """The thread id, also when given as the thread's Reddit link or as its file name."""
    if text.startswith(("http://", "https://")):
        return _reddit_thread_id(text) or text
    return text.removesuffix(".json")


def main(argv: list[str], gold_dir: Path = DEFAULT_GOLD_DIR, open_page=_open_in_browser) -> int:
    """`gold_dir` and `open_page` can be swapped, which is how the tests run the command line."""
    command = argv[0] if argv else None
    options = [word for word in argv[1:] if word.startswith("--")]
    words = [word for word in argv[1:] if not word.startswith("--")]
    allowed = {"page": {"--open"}, "import": {"--replace"}}
    if command not in allowed or len(words) != 1 or not set(options) <= allowed[command]:
        print(__doc__)
        return 2

    try:
        if command == "page":
            path = write_page(_thread_id_from(words[0]), gold_dir)
        else:
            result = import_labels(Path(words[0]).expanduser(), gold_dir, replace="--replace" in options)
    except LabellingError as e:
        print(e)
        return 1

    if command == "page":
        print(f"Labelling page written: {path}")
        print("Labels are saved in that browser as you go. When done, Export downloads labels_<thread id>.json;")
        print("then run: .venv/bin/python -m engine.labelling import ~/Downloads/labels_<thread id>.json")
        if "--open" in options:
            open_page(path)
        return 0

    _print_import(result, words[0])
    return print_gold_check([str(gold_dir)])  # the same summary as `python -m engine.gold`


def _print_import(result: ImportResult, name: str) -> None:
    print(f"Imported {Path(name).name}: {_count(result.comments, 'labelled comment')} of thread {result.thread_id}.")
    print(f"  {_count(result.voices_added, 'row')} added to voices.csv, {_count(result.mentions_added, 'row')} added to mentions.csv.")
    if result.voices_removed or result.mentions_removed:
        print(
            f"  Replaced the thread's earlier labels: removed {_count(result.voices_removed, 'row')} from voices.csv "
            f"and {result.mentions_removed} from mentions.csv."
        )
    if result.no_longer_labelled:
        print(f"  Labelled before but not in this file, so no longer labelled: {', '.join(result.no_longer_labelled)}")


def _shown(path: Path) -> str:
    """A path as short as it can be: from the project folder when it's inside it."""
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
