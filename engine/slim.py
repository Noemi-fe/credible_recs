"""Keep only the comments answers use (Noemi, 13 Oct 2026: "Keep only comments we use").

Why. Archive text not checked live within about 37 days must go (the deletion rule, engine/library.py check-live),
and reading the whole library again on Reddit each month through Bright Data would take about 9,600 records a month
(436 threads, about 22 records a thread) against its free tier's 5,000. So the library keeps only what answers use,
and keeps that current comment by comment through Reddit's embed page, which is free (engine/verify.py).

What a slimmed thread keeps:
- its title, ids, dates, scores and links. Its post's words and writer are dropped;
- whole, every comment its extraction (the AI's reading of it) points to: each product mention, "what to look for"
  note, care tip and agreeing reply, whether its checks passed or not, and the comment a reply takes its product from
  (refers_to "parent", or "earlier": the one above that) (kept_comment_ids). Nothing else is quoted or read for its words;
- every other comment as a stub marked "not_kept": its id, what it replies to, its date, score and link, without its
  words or its writer. So the thread keeps its shape: its replies, and the scores module 5's "well upvoted" compares;
- what the scoring reads from the whole thread, worked out before the words go (engine.models.WholeThread, the field
  whole_thread): the product types its post and each dropped comment named (module 2: how relevant the thread is, and
  whether its title or post names the product; known_types), the pairs of comments with the same words under two
  writers' names (module 5's "copied text", and copies counting once), when a kept comment's writer first commented
  when that comment is dropped (engine.profiles checks their "active since" against it), and the fingerprints of the
  extraction's quotes in a quoted block whose words a dropped comment or the post had written (someone else's words);
- for each kept comment, verified_at: when Reddit last showed it saying what the library holds (initial_verified_at:
  when the thread was read on Reddit itself, through Parse or Bright Data; never, for a comment read from Arctic Shift's
  archive and not read live since). From then on each kept comment is verified one by one (engine/verify.py).

The guard. Before a slimmed copy is written it is read the way answers read it, and compared with the whole thread
(differences): the extraction's checks (every item kept or rejected alike, with its reason), every kept comment's voice
(module 5's signs, "well upvoted" and "replies agree" among them), the copies, the thread's relevance to every known
product type and whether its title or post names it, how many of its comments name it, the comments the AI read, and
each kept writer's first comment. A thread whose slimmed copy would read differently in any of these stays whole, and
is named with what differed.

What can't carry over: a product type unknown when a thread is slimmed (one the open model names later) can't be looked
for in words that are gone, so such a thread is found for it by its title and the comments it keeps only. known_types
holds every type module 1 knows, the open model's types in config.PRECHECK_MODEL_TYPES and in the library's request log,
and each active ingredient's own type: add a new type before slimming the threads about it.

Which threads: those with an extraction that loads, except gold-set threads (Noemi's: unchanged) and those already
slimmed. Running it again changes nothing. A thread not extracted yet stays whole until it is: new threads are read
whole, extracted, then slimmed.

    python -m engine.library slim [--dry-run] [--library DIR]
"""

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from engine.config import INGREDIENTS, PRECHECK_MODEL_TYPES
from engine.credibility import _groups_of, copied_comment_ids, copy_pairs, repeated_copies, score_voice
from engine.extract import (Extraction, _in_quoted_block, _read_extraction, check_extraction, extracted_dir,
                            shown_comment_ids)
from engine.gold import DEFAULT_GOLD_DIR, unlabelled_gold_ids
from engine.ingredients import ingredient_type_name
from engine.models import Thread, WholeThread, quote_fingerprint
from engine.query import PRODUCT_TYPES
from engine.sources import mentions_product, names_product, relevance, talking
from engine.verify_quotes import find_quote

PLACEHOLDERS = ("[deleted]", "[removed]")  # what Reddit shows in place of a post's or a comment's words


class SlimError(ValueError):
    """A thread that can't be slimmed with this extraction."""


@dataclass
class SlimResult:
    """What a slimming run did, in ids and counts (never anyone's words)."""

    slimmed: list[str] = field(default_factory=list)  # slimmed now (a dry run: would be)
    already: list[str] = field(default_factory=list)  # slimmed before: left as they are
    stale: list[str] = field(default_factory=list)  # of those, extracted again since: only the kept comments can count
    not_extracted: list[str] = field(default_factory=list)  # whole until they are extracted
    gold: list[str] = field(default_factory=list)  # gold-set threads: Noemi's, never slimmed
    refused: dict[str, str] = field(default_factory=dict)  # whose slimmed copy would read differently: what differed
    problems: dict[str, str] = field(default_factory=dict)  # files that couldn't be read
    comments_kept: int = 0  # in the threads slimmed now: kept whole
    comments_dropped: int = 0  # their words and writers dropped
    text_before: int = 0  # bytes of words (posts and comments) in the threads slimmed now, before and after
    text_after: int = 0
    file_before: int = 0  # bytes of their thread files, before and after
    file_after: int = 0
    dry_run: bool = False


def known_types(library_dir: Path) -> tuple[str, ...]:
    """The product types a slimmed thread's dropped words are searched for before they go: module 1's types, the open
    model's types (config.PRECHECK_MODEL_TYPES and the library's request log), and each active ingredient's own type
    ("salicylic acid product": an ingredient-led request's)."""
    found = [p.name for p in PRODUCT_TYPES] + list(PRECHECK_MODEL_TYPES) + _logged_types(Path(library_dir))
    found += [ingredient_type_name([key]) for key in INGREDIENTS]
    return tuple(dict.fromkeys(t.strip() for t in found if t and t.strip()))


def _logged_types(library_dir: Path) -> list[str]:
    """The product types of the requests the library was filled for (its request log, requests.jsonl)."""
    try:
        lines = (library_dir / "requests.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    types = []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("status") == "ok" and isinstance(entry.get("product_type"), str):
            types.append(entry["product_type"])
    return types


def gold_thread_ids(root: Path = DEFAULT_GOLD_DIR) -> set[str]:
    """Every gold-set thread, labelled or not (engine.gold): its candidates' links and its saved threads. Never slimmed:
    they are Noemi's, on her machine (her decision of 13 Oct 2026 leaves them unchanged)."""
    threads = Path(root) / "threads"
    return unlabelled_gold_ids(root) | ({p.stem for p in threads.glob("*.json")} if threads.is_dir() else set())


# --- One thread ---

def kept_comment_ids(thread: Thread, extraction: Extraction) -> set[str]:
    """The readable comments the extraction points to: every product mention, note, care tip and agreement, whether
    its checks pass or not, and the comment each reply naming its product further up takes it from (refers_to "parent":
    the comment above; "earlier": the one above that)."""
    comments = {c.id: c for c in thread.comments}
    ids = {item.comment_id for item in _items(extraction)}
    for mention in extraction.mentions:
        if mention.refers_to in ("parent", "earlier") and (source := _source_of(mention, comments)) is not None:
            ids.add(source.id)
    return {cid for cid in ids if cid in comments and comments[cid].status == "ok"}


def _items(extraction: Extraction) -> list:
    return [*extraction.mentions, *extraction.notes, *extraction.agreements, *extraction.care]


def _source_of(mention, comments: dict):
    """The comment a reply takes its product from, as engine.extract checks it (None when it isn't in the thread)."""
    comment = comments.get(mention.comment_id)
    above = comments.get(comment.parent_id) if comment is not None and comment.parent_id else None
    if mention.refers_to == "earlier" and above is not None:
        above = comments.get(above.parent_id) if above.parent_id else None
    return above


def names_in(text: str, types) -> list[str]:
    """The product types a text names (engine.sources.mentions_product), in `types`' order."""
    return [t for t in types if mentions_product(text, t)] if text.strip() else []


def initial_verified_at(thread: Thread, comment, by_id: dict) -> datetime | None:
    """When Reddit last showed a comment saying what the library holds, as the thread file tells: when the thread was
    read on Reddit itself (Thread.last_checked_live: through Parse, or Bright Data). An archive thread merged with a
    Bright Data read keeps the replies to replies from the archive (Bright Data never returns them): those, and every
    comment of an archive thread never read live, were never verified (None)."""
    last = thread.last_checked_live()
    if last is None or (thread.read_from == "arctic_shift" and _depth(comment, by_id) >= 2):
        return None
    return last


def _depth(comment, by_id: dict) -> int:
    """0 for a top-level comment, 1 for a direct reply, 2 or more for a reply to a reply."""
    depth, seen = 0, set()
    while comment.parent_id is not None and comment.parent_id in by_id and comment.id not in seen:
        seen.add(comment.id)
        comment, depth = by_id[comment.parent_id], depth + 1
    return depth


def extraction_stamp(extraction: Extraction) -> str:
    """Which extraction a thread was slimmed with: its instructions version and when it was made."""
    return f"{extraction.instructions_version} {extraction.extracted_at.isoformat()}"


def slim_thread(thread: Thread, extraction: Extraction, types, now: datetime) -> Thread:
    """The slimmed copy of a whole thread (see the module's docstring). `types`: the product types to work out from
    the words dropped (known_types). The thread passed in is left as it was."""
    if extraction.thread_id != thread.id:
        raise SlimError(f"the extraction of {extraction.thread_id} isn't of thread {thread.id}")
    if thread.slimmed:
        raise SlimError(f"thread {thread.id} is slimmed already")
    kept = kept_comment_ids(thread, extraction)
    by_id = {c.id: c for c in thread.comments}
    dropped = [c for c in thread.comments if c.status == "ok" and c.id not in kept]
    post_words = thread.body.strip() not in ("",) + PLACEHOLDERS
    facts = WholeThread(
        slimmed_at=now,
        extraction=extraction_stamp(extraction),
        post_names=names_in(thread.body, types) if post_words else [],
        comment_names={c.id: names for c in dropped if (names := names_in(c.body, types))},
        copies=_copies_reaching(thread, kept),
        first_seen=_first_seen_dropped(thread, kept),
        quoted_elsewhere=_quoted_elsewhere(thread, extraction, kept, dropped, post_words),
    )
    comments = []
    for comment in thread.comments:
        if comment.id in kept:
            comments.append(comment.model_copy(update={"verified_at": initial_verified_at(thread, comment, by_id)}))
        elif comment.status == "ok":
            comments.append(comment.model_copy(update={"status": "not_kept", "body": "", "author": None,
                                                       "verified_at": None}))
        else:
            comments.append(comment)
    slimmed = thread.model_copy(update={"body": "" if post_words else thread.body, "author": None,
                                        "comments": comments, "whole_thread": facts})
    return Thread.model_validate(slimmed.model_dump())  # checked: no words or writer left where none may be


def _copies_reaching(thread: Thread, kept: set[str]) -> list[tuple[str, str]]:
    """The pairs of copies (engine.credibility.copy_pairs) in the sets of copies that hold a kept comment."""
    pairs = copy_pairs(thread)
    reaching = set().union(*(group for group in _groups_of(pairs) if group & kept))
    return sorted(pair for pair in pairs if pair[0] in reaching)


def _first_seen_dropped(thread: Thread, kept: set[str]) -> dict[str, datetime]:
    """{writer of a kept comment: their first comment's date}, for the writers whose first comment isn't kept."""
    own: dict[str, list] = {}
    for comment in thread.comments:
        if comment.author is not None:
            own.setdefault(comment.author.name, []).append(comment)
    found = {}
    for name, comments in own.items():
        mine = [c.created_at for c in comments if c.id in kept]
        first = min(c.created_at for c in comments)
        if mine and first < min(mine):
            found[name] = first
    return found


def _quoted_elsewhere(thread: Thread, extraction: Extraction, kept: set[str], dropped: list, post_words: bool) -> list:
    """The fingerprints of the extraction's quotes that sit in a quoted block of their kept comment and are found in
    words being dropped (the post's, or another comment's): engine.extract takes those for someone else's words."""
    by_id = {c.id: c for c in thread.comments}
    texts = ([thread.body] if post_words else []) + [c.body for c in dropped]
    found = set()
    for item in _items(extraction):
        comment = by_id.get(item.comment_id)
        if comment is None or comment.id not in kept:
            continue
        span = find_quote(comment.body, item.quote)
        if span is not None and _in_quoted_block(comment.body, span) and any(
                find_quote(text, item.quote) is not None for text in texts):
            found.add(quote_fingerprint(item.quote))
    return sorted(found)


# --- The guard: read the same as the whole thread ---

def differences(whole: Thread, slimmed: Thread, extraction: Extraction, types) -> list[str]:
    """What answers would read differently in the slimmed copy than in the whole thread (empty: nothing)."""
    found = []
    before, after = check_extraction(extraction, whole), check_extraction(extraction, slimmed)
    if _checked(before) != _checked(after):
        found.append("the extraction's checks")
    old, new = {c.id: c for c in whole.comments}, {c.id: c for c in slimmed.comments}
    kept = {cid for cid, comment in new.items() if comment.status == "ok"}
    for cid in kept:
        if score_voice(new[cid], slimmed, after.kept_agreements) != score_voice(old[cid], whole,
                                                                                before.kept_agreements):
            found.append(f"comment {cid}'s voice")
    # Copies among dropped comments only change nothing: only a kept comment's flag or mentions can count.
    if ((copied_comment_ids(slimmed) & kept, repeated_copies(slimmed) & kept)
            != (copied_comment_ids(whole) & kept, repeated_copies(whole) & kept)):
        found.append("the copies")
    for product_type in types:
        if (relevance(slimmed, product_type), names_product(slimmed, product_type), talking(slimmed, product_type)) != (
                relevance(whole, product_type), names_product(whole, product_type), talking(whole, product_type)):
            found.append(f"the relevance to {product_type}")
    if len(shown_comment_ids(slimmed)) != len(shown_comment_ids(whole)):
        found.append("the comments the AI read")
    from engine.profiles import _first_seen  # here: engine.profiles reads the library's folders

    writers = {c.author.name for c in slimmed.comments if c.author is not None}
    first_old, first_new = _first_seen(whole), _first_seen(slimmed)
    if {n: first_new.get(n) for n in writers} != {n: first_old.get(n) for n in writers} or set(first_new) - writers:
        found.append("the writers' first comments")
    return found


def _checked(result) -> tuple:
    """A check of an extraction, as comparable values: every item kept, and every item rejected with its reason."""
    keyed = lambda item: item.model_dump_json()
    return tuple([keyed(i) for i in kept] for kept in (result.kept, result.kept_notes, result.kept_agreements,
                                                        result.kept_care)) + tuple(
        [(keyed(i), why) for i, why in rejected] for rejected in (result.rejected, result.rejected_notes,
                                                                  result.rejected_agreements, result.rejected_care))


# --- A whole library ---

def slim_library(folder: Path, dry_run: bool = False, now: datetime | None = None,
                 gold_ids: set[str] | None = None) -> SlimResult:
    """Slims every thread of the library that can be (see the module's docstring): extracted, not a gold-set thread
    (`gold_ids`, by default gold_thread_ids), not slimmed already, and whose slimmed copy reads as the whole one did.
    With `dry_run`, counts what it would do and writes nothing. Each file is written whole, then swapped in."""
    folder, now = Path(folder), now or datetime.now(UTC)
    threads_dir = folder / "threads"
    gold_ids = gold_thread_ids() if gold_ids is None else gold_ids
    types = known_types(folder)
    result = SlimResult(dry_run=dry_run)
    for path in sorted(threads_dir.glob("*.json")) if threads_dir.is_dir() else ():
        raw = path.read_bytes()
        try:
            thread = Thread.model_validate_json(raw)
        except ValueError:
            result.problems[path.stem] = "the thread file doesn't load"
            continue
        extraction_path = extracted_dir(threads_dir) / path.name
        if thread.slimmed:
            result.already.append(thread.id)
            extraction, problems = _read_extraction(extraction_path) if extraction_path.is_file() else (None, [])
            if extraction is not None and extraction_stamp(extraction) != thread.whole_thread.extraction:
                result.stale.append(thread.id)
            continue
        if thread.id in gold_ids or thread.read_from == "gold":
            result.gold.append(thread.id)
            continue
        if not extraction_path.is_file():
            result.not_extracted.append(thread.id)
            continue
        extraction, problems = _read_extraction(extraction_path)
        if problems:
            result.problems[thread.id] = "its extraction file is malformed (python -m engine.extract check)"
            continue
        try:
            slimmed = slim_thread(thread, extraction, types, now)
        except SlimError as error:
            result.problems[thread.id] = str(error)
            continue
        found = differences(thread, slimmed, extraction, types)
        if found:
            result.refused[thread.id] = "would read differently: " + ", ".join(found)
            continue
        data = thread_json(slimmed)
        result.slimmed.append(thread.id)
        result.comments_kept += sum(c.status == "ok" for c in slimmed.comments)
        result.comments_dropped += sum(c.status == "not_kept" for c in slimmed.comments)
        result.text_before += _words(thread)
        result.text_after += _words(slimmed)
        result.file_before += len(raw)
        result.file_after += len(data)
        if not dry_run:
            write_file(path, data)
    return result


def _words(thread: Thread) -> int:
    """Bytes of Reddit words a thread holds: its title, its post and its readable comments."""
    return len(thread.title.encode()) + len(thread.body.encode()) + sum(
        len(c.body.encode()) for c in thread.comments if c.status == "ok")


def thread_json(thread: Thread) -> bytes:
    """A slimmed thread as its file holds it: what isn't at its default is written (a stub's empty fields aren't)."""
    return (thread.model_dump_json(indent=2, exclude_defaults=True) + "\n").encode("utf-8")


def write_file(path: Path, data: bytes) -> None:
    """Writes a file whole under another name, then swaps it in: an interrupted run never leaves half a file."""
    partial = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    partial.write_bytes(data)
    partial.replace(path)


def report(result: SlimResult) -> str:
    """The run in a few lines: counts and thread ids only."""
    verb = "Would slim" if result.dry_run else "Slimmed"
    n = len(result.slimmed)
    lines = [f"{verb} {n} thread{'' if n == 1 else 's'}: {result.comments_kept:,} comments kept whole (the ones "
             f"answers use), {result.comments_dropped:,} reduced to their ids, dates, scores and replies (no words, "
             f"no writers)."]
    if n:
        lines.append(f"Words in them: {_mb(result.text_before)} -> {_mb(result.text_after)}; their files: "
                     f"{_mb(result.file_before)} -> {_mb(result.file_after)}.")
    lines.append(f"Left whole: {len(result.not_extracted)} not extracted yet, {len(result.gold)} gold-set "
                 f"thread(s). Slimmed before: {len(result.already)}.")
    if result.dry_run:
        lines[0] = lines[0].replace("Would slim", "Dry run: would slim")
        lines.append("Dry run: nothing written.")
    if result.stale:
        lines.append(f"Extracted again since they were slimmed (only their kept comments can count; read them whole "
                     f"again to use the new extraction fully): {', '.join(result.stale)}")
    for thread_id, why in result.refused.items():
        lines.append(f"  left whole, {why}: {thread_id}")
    for thread_id, why in result.problems.items():
        lines.append(f"  left whole, {why}: {thread_id}")
    return "\n".join(lines)


def _mb(size: int) -> str:
    return f"{size / 1_000_000:.2f} MB"
