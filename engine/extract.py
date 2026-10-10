"""Module 3, mention extraction: lists the products each comment mentions, with a stance and a supporting quote.

There is no Claude API key (Noemi, 7 Oct 2026), so the AI half runs outside Python: Claude Code reads a thread
file, follows the instructions in engine/prompts/extract_mentions.md and writes one extraction file per thread.
This module is the bookkeeping and the guardrail around that:

    data/<set>/threads/<thread id>.json     a thread (engine.models.Thread), from the gold set or the library
    data/<set>/extracted/<thread id>.json   what the AI found in it (Extraction, below); git ignores these folders

An extraction file looks like this. An empty "mentions" list means the thread mentions no product.

    {
      "thread_id": "1fake01",
      "instructions_version": "extract-v1",
      "extracted_at": "2026-10-08T10:00:00Z",
      "extractor": "claude-code",
      "mentions": [
        {"comment_id": "c1aaaa", "product": "CeraVe SA Cleanser", "category": "skincare",
         "stance": "recommend", "quote": "I've used the CeraVe SA Cleanser for 2 years."}
      ]
    }

From instructions v6 (decided 9 Oct 2026) each mention also says what type of product it is ("product_type":
"cleanser") and how well the writer knows it ("evidence": "long-term use", with "evidence_tags" saying why).
Older extractions have neither and still load.

From instructions v7 (Noemi, 9 Oct 2026) an extraction also lists care tips ("care"): advice on looking after a
product or a kind of product so it lasts or works well ("descale it every 6 months"), shown under the picks as "How
to make it last" (engine/care_tips.py). Older extractions have no "care" list and still load.

The guardrail (the brief's rule): every quote must exist word for word in its comment, checked by code, not by
the AI, and a quote that fails is dropped. check_extraction keeps a mention only if its comment is in the thread
and still readable (not deleted or removed), its quote is found word for word (engine.verify_quotes), and the
quote is at most 50 words (QUOTE_MAX_WORDS), and its evidence tags, if any, are known ones (config.EVIDENCE_TAGS).
Every other mention is set aside with the reason, never used. Notes, agreements and care tips are checked the
same way (their comment and their quote).
The share kept is the quote pass rate, which shows how often the AI quotes faithfully.

The instructions version: the instruction file starts with a line such as "Version: extract-v1", and each
extraction records the version it followed. When the instructions change, the version changes too, and `todo`
lists the threads extracted with older instructions, so they are done again.

Command line:
    python -m engine.extract todo [threads folder]    the threads still to extract under the current instructions
                                                      (data/library/threads by default)
    python -m engine.extract check [threads folder]   for every extraction: the mentions kept, and the ones rejected
                                                      with the reason; then totals and the quote pass rate.
                                                      Exits 1 if any extraction file is malformed.
"""

import html
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Annotated, Literal

from pydantic import AfterValidator, ValidationError

from engine.config import (
    EVIDENCE_LEVELS,
    EVIDENCE_TAGS,
    EXTRACT_MAX_COMMENTS,
    MENTION_CATEGORIES,
    QUOTE_MAX_WORDS,
    STANCE_VALUE,
)
from engine.gold import DEFAULT_GOLD_DIR, GoldSetError, _describe, load_threads, unlabelled_gold_ids
from engine.models import Id, Record, Thread, UtcDatetime
from engine.verify_quotes import find_quote

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INSTRUCTIONS = REPO_ROOT / "engine" / "prompts" / "extract_mentions.md"
DEFAULT_THREADS_DIR = REPO_ROOT / "data" / "library" / "threads"

_VERSION_LINE = re.compile(r"Version:\s*(\S+)\s*")


class ExtractionError(Exception):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(f"{len(problems)} problem(s) with the extractions:\n" + "\n".join(f"- {p}" for p in problems))


# --- The extraction file ---

def _not_blank(text: str) -> str:
    if not text.strip():
        raise ValueError("must not be empty")
    return text


Text = Annotated[str, AfterValidator(_not_blank)]  # some text, not just spaces; kept exactly as written


class ExtractedMention(Record):
    """One product mentioned in one comment, as the AI wrote it down. Nothing here is trusted until checked."""

    comment_id: Id
    product: Text  # as written in the comment; matching names to products is module 4's job
    category: Literal[MENTION_CATEGORIES]
    stance: Literal[tuple(STANCE_VALUE)]
    quote: Text  # meant to be copied word for word from the comment; check_extraction makes sure
    # A reply about a product named in the comment above ("had this one 13 years") or in the post ("the one you
    # listed") names it from there (instructions v2, 8 Oct 2026). "earlier" when it is named further up the same
    # reply chain ("how did you like it?" then "loved it"; instructions v4). None when the comment names it itself.
    refers_to: Literal["parent", "post", "earlier"] | None = None
    # From instructions v6 (decided 9 Oct 2026); None or empty in older extractions.
    # The type of the product itself, not the thread's ("CeraVe SA Cleanser" in an exfoliant thread is "cleanser"):
    # a product type name from module 1 (engine.query.PRODUCT_TYPES) when one fits, else a short type in plain
    # words ("toaster"). The pipeline uses it to leave out products of another type.
    product_type: Text | None = None
    # How well this writer knows this product, in Noemi's levels (long-term use, short-term use, no first-hand use),
    # and the tags that explain it. Only known tags (config.EVIDENCE_TAGS): check_extraction drops a mention with
    # any other, rather than refusing the whole file.
    evidence: Literal[EVIDENCE_LEVELS] | None = None
    evidence_tags: list[str] = []


class ExtractedNote(Record):
    """Advice about a kind of product, not a specific one ("get one with no plastic touching the water").

    Not a product mention: it becomes a "what to look for" note under the picks (Noemi, 8 Oct 2026).
    """

    comment_id: Id
    about: Text  # the kind of product or the feature, such as "plastic-free kettle"
    stance: Literal[tuple(STANCE_VALUE)]
    quote: Text


class ExtractedCareTip(Record):
    """Advice on looking after, using or maintaining a product or a kind of product, so it lasts or works well
    ("descale it every 6 months", "never put a carbon steel knife in the dishwasher"). Instructions v7.

    Not a product mention and not a note (notes are about choosing what to buy): it is shown under a pick as "How to
    make it last" (Noemi, 9 Oct 2026). Nothing here is trusted until checked, like the rest of the file.
    """

    comment_id: Id
    about: Text  # the product as the comment names it ("Zojirushi kettle"), or the kind ("cast iron skillet")
    is_kind: bool = False  # True when the tip is about a kind of product, False when about one specific product
    tip: Text  # the tip in a few plain words, saying only what the quote says: "descale every 6 months"
    quote: Text


class ExtractedAgreement(Record):
    """A reply agreeing with the comment above ("This!"): evidence that the other writer is credible."""

    comment_id: Id
    quote: Text


class Extraction(Record):
    """One extraction file: every product mentioned in one thread, plus its notes and agreements."""

    thread_id: Id
    instructions_version: Text  # the "Version:" line of the instructions followed, such as "extract-v1"
    extracted_at: UtcDatetime
    extractor: Text  # who extracted, such as "claude-code"
    mentions: list[ExtractedMention]  # empty means the thread mentions no product
    notes: list[ExtractedNote] = []  # from instructions v2; older extractions have none
    agreements: list[ExtractedAgreement] = []
    care: list[ExtractedCareTip] = []  # from instructions v7 (Noemi, 9 Oct 2026); older extractions have none


def extracted_dir(threads_dir: Path) -> Path:
    """Where the extractions of a threads folder live: next to it, so data/gold/threads -> data/gold/extracted."""
    return Path(threads_dir).parent / "extracted"


# --- The guardrail: checking one extraction against its thread ---

@dataclass
class CheckResult:
    kept: list[ExtractedMention] = field(default_factory=list)  # passed every check: safe to use
    rejected: list[tuple[ExtractedMention, str]] = field(default_factory=list)  # each with the reason it was dropped
    kept_notes: list[ExtractedNote] = field(default_factory=list)
    rejected_notes: list[tuple[ExtractedNote, str]] = field(default_factory=list)
    kept_agreements: list[ExtractedAgreement] = field(default_factory=list)
    rejected_agreements: list[tuple[ExtractedAgreement, str]] = field(default_factory=list)
    kept_care: list[ExtractedCareTip] = field(default_factory=list)  # care tips (instructions v7), checked like notes
    rejected_care: list[tuple[ExtractedCareTip, str]] = field(default_factory=list)

    @property
    def quote_pass_rate(self) -> float | None:
        """The share of mentions kept, from 0 to 1. None when there were no mentions to check."""
        return overall_quote_pass_rate([self])


def check_extraction(extraction: Extraction, thread: Thread) -> CheckResult:
    """Splits the AI's mentions into the ones safe to use and the ones dropped, with the reason for each.

    A mention is kept only when all of these hold, checked in this order (the first that fails is the reason):
    - the extraction is of this thread (if not, every mention is dropped);
    - its comment is in the thread;
    - the comment is still readable: one deleted or removed on Reddit can't be quoted;
    - its quote is in the comment word for word (engine.verify_quotes.find_quote);
    - the quote isn't from a quoted block (a line starting with ">", or a line straight after one in the same
      paragraph): those are someone else's words, and credit has to go to the person who wrote them. The exception
      (instructions v4, Noemi, 8 Oct 2026): a comment written entirely as a quoted block, whose quoted words appear
      nowhere else in the thread, is the writer's own;
    - the quote is at most QUOTE_MAX_WORDS words long, counting the words of the comment it matches (so a quote
      joined with HTML entities such as "&#32;" can't pass as one long word);
    - a reply marked as naming its product further up (refers_to) really is a reply (to a reply, for "earlier"),
      and the comment it takes its product from is still readable: a product named only in deleted or removed text
      can't be checked or used;
    - every evidence tag is a known one (config.EVIDENCE_TAGS; instructions v6).
    Mentions keep their order in both lists. Notes and care tips (instructions v7) go through the same checks of
    their comment and quote (the first six above); agreements too, and they must be replies.
    """
    comments = {comment.id: comment for comment in thread.comments}
    result = CheckResult()
    for mention in extraction.mentions:
        reason = _why_rejected(mention, extraction, thread, comments)
        if reason is None and mention.refers_to == "parent" and comments[mention.comment_id].parent_id is None:
            reason = f"comment {mention.comment_id} refers to the comment above, but it isn't a reply"
        if reason is None and mention.refers_to == "earlier" and not _reply_to_a_reply(comments[mention.comment_id], comments):
            reason = f"comment {mention.comment_id} refers to a comment further up, but it isn't a reply to a reply"
        if reason is None and mention.refers_to in ("parent", "earlier"):
            reason = _named_in_unreadable_comment(mention, comments)
        if reason is None:
            reason = _unknown_evidence_tags(mention)
        if reason is None:
            result.kept.append(mention)
        else:
            result.rejected.append((mention, reason))
    for note in extraction.notes:
        reason = _why_rejected(note, extraction, thread, comments)
        if reason is None:
            result.kept_notes.append(note)
        else:
            result.rejected_notes.append((note, reason))
    for agreement in extraction.agreements:
        reason = _why_rejected(agreement, extraction, thread, comments)
        if reason is None and comments[agreement.comment_id].parent_id is None:
            reason = f"comment {agreement.comment_id} isn't a reply, so it can't agree with the comment above"
        if reason is None:
            result.kept_agreements.append(agreement)
        else:
            result.rejected_agreements.append((agreement, reason))
    for tip in extraction.care:
        reason = _why_rejected(tip, extraction, thread, comments)
        if reason is None:
            result.kept_care.append(tip)
        else:
            result.rejected_care.append((tip, reason))
    return result


def _why_rejected(mention, extraction: Extraction, thread: Thread, comments: dict) -> str | None:
    """The first check a mention, note, agreement or care tip fails, or None. Each has a comment_id and a quote."""
    if extraction.thread_id != thread.id:
        return f"the extraction is of thread {extraction.thread_id}, not {thread.id}"
    comment = comments.get(mention.comment_id)
    if comment is None:
        return f"comment {mention.comment_id} is not in thread {thread.id}"
    if comment.status != "ok":
        return f"comment {mention.comment_id} was {comment.status} on Reddit, so it can't be quoted"
    span = find_quote(comment.body, mention.quote)
    if span is None:
        return f"quote not found word for word in comment {mention.comment_id}"
    if _in_quoted_block(comment.body, span):
        elsewhere = [thread.title, thread.body] + [c.body for c in thread.comments if c.id != comment.id]
        if not _own_words_in_quote_format(comment.body, mention.quote, elsewhere):
            return f"quote is from a quoted block in comment {mention.comment_id}: someone else's words"
    words = len(_as_written(comment.body, span).split())
    if words > QUOTE_MAX_WORDS:
        return f"quote has {words} words; the limit is {QUOTE_MAX_WORDS}"
    return None


def _unknown_evidence_tags(mention: ExtractedMention) -> str | None:
    """The reason to drop a mention whose evidence tags include one that isn't in config.EVIDENCE_TAGS, or None."""
    unknown = [tag for tag in mention.evidence_tags if tag not in EVIDENCE_TAGS]
    if not unknown:
        return None
    return f"unknown evidence tag(s) {', '.join(map(repr, unknown))}; choose from: {', '.join(EVIDENCE_TAGS)}"


def _as_written(body: str, span: tuple[int, int]) -> str:
    """The comment's own text that a quote matched (engine.verify_quotes.find_quote's span), with Reddit's HTML
    entities turned back into characters ("&amp;" as "&"). Its words are the ones the quote really stands for."""
    return html.unescape(body[span[0]:span[1]])


def _in_quoted_block(body: str, span: tuple[int, int]) -> bool:
    """Whether the quote starts on a line that quotes someone else.

    On Reddit a quoted block starts with a line beginning ">" (stored as "&gt;"), and the lines straight after it
    stay in the block until a blank line ends the paragraph: in "> It broke.\nNever buy it.", both lines are quoted.
    So a line is quoted when it, or an earlier line of its paragraph, starts with ">".
    """
    line_end = body.find("\n", span[0])
    paragraph = body[:line_end] if line_end != -1 else body
    for line in reversed(paragraph.split("\n")):
        if not line.strip():
            return False  # a blank line: the paragraph starts below it
        if line.lstrip().startswith((">", "&gt;")):
            return True
    return False


def _own_words_in_quote_format(body: str, quote: str, elsewhere: Iterable[str]) -> bool:
    """Whether a comment written entirely as a quoted block holds the writer's own words: no one else wrote them.

    Some people format their whole answer with ">". If the quote is found nowhere `elsewhere` (the thread's title,
    post and other comments; at answer time, the other comments), it isn't copied from anyone there. Every paragraph
    must start with ">": the lines after it are in the same block (see _in_quoted_block).
    """
    paragraphs = [p.lstrip() for p in re.split(r"\n\s*\n", body) if p.strip()]
    if not all(p.startswith((">", "&gt;")) for p in paragraphs):
        return False
    return all(find_quote(text, quote) is None for text in elsewhere)


def _named_in_unreadable_comment(mention: ExtractedMention, comments: dict) -> str | None:
    """Why a mention that takes its product from a comment above can't be kept, or None.

    "parent" takes it from the comment above, "earlier" from the one above that (review fixes, 9 Oct 2026). If that
    comment was deleted or removed, the product is named only in text that is gone: nothing can check it, and the
    deletion rule says gone text isn't used.
    """
    above = comments.get(comments[mention.comment_id].parent_id)
    if mention.refers_to == "earlier" and above is not None:
        above = comments.get(above.parent_id)
    if above is None:
        return f"comment {mention.comment_id} takes its product from a comment above that isn't in the thread"
    if above.status != "ok":
        return (f"comment {mention.comment_id} takes its product from comment {above.id}, which was {above.status} "
                f"on Reddit, so the product can't be checked")
    return None


def _reply_to_a_reply(comment, comments: dict) -> bool:
    """Whether a comment answers a reply, so there is a comment further up than its parent to take a name from."""
    parent = comments.get(comment.parent_id) if comment.parent_id else None
    return parent is not None and parent.parent_id is not None


def overall_quote_pass_rate(results: Iterable[CheckResult]) -> float | None:
    """The share of all mentions kept, across threads: each mention counts once, whatever its thread's size.

    None when there were no mentions at all.
    """
    kept = total = 0
    for result in results:
        kept += len(result.kept)
        total += len(result.kept) + len(result.rejected)
    return kept / total if total else None


# --- Loading a folder of extractions ---

def load_checked(threads_dir: Path) -> dict[str, CheckResult]:
    """Every extraction next to a threads folder, checked against its thread: {thread id: what was kept and dropped}.

    Threads with no extraction yet are left out. A malformed extraction file is never skipped quietly: every
    problem in every file is collected, then raised together as an ExtractionError naming each file. An extraction
    whose thread file is gone counts as a problem too. Problems in the thread files themselves raise GoldSetError.
    """
    results, problems = _check_folder(Path(threads_dir))
    if problems:
        raise ExtractionError(problems)
    return results


def _check_folder(threads_dir: Path) -> tuple[dict[str, CheckResult], list[str]]:
    """The results of the extraction files that could be read, and the problems of those that couldn't."""
    threads = {thread.id: thread for thread in load_threads(threads_dir)}
    folder = extracted_dir(threads_dir)
    results: dict[str, CheckResult] = {}
    problems: list[str] = []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        where = f"{folder.name}/{path.name}"
        extraction, file_problems = _read_extraction(path)
        if file_problems:
            problems.extend(f"{where}: {problem}" for problem in file_problems)
            continue
        thread = threads.get(path.stem)
        if thread is None:
            problems.append(f"{where}: there is no thread {path.stem} in {threads_dir.name}/; delete this file or put the thread back")
            continue
        # The file name says which thread it belongs to; if the file's own thread_id disagrees, every mention is dropped.
        results[path.stem] = check_extraction(extraction, thread)
    return results, problems


def _read_extraction(path: Path) -> tuple[Extraction | None, list[str]]:
    """The extraction in a file, or None and every problem that stops it from being read."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return None, [f"not valid JSON (line {e.lineno}, column {e.colno}): {e.msg}"]
    except UnicodeDecodeError:
        return None, ["not UTF-8 text"]
    try:
        return Extraction.model_validate(raw), []
    except ValidationError as e:
        return None, [_describe(error) for error in e.errors()]


# --- What still needs extracting ---

def current_instructions_version(path: Path = DEFAULT_INSTRUCTIONS) -> str:
    """The version of the extraction instructions, read from their first line, "Version: extract-v1"."""
    path = Path(path)
    if not path.is_file():
        raise ExtractionError([f"the instruction file {path} is missing"])
    lines = path.read_text(encoding="utf-8-sig").splitlines()  # utf-8-sig: an invisible marker some editors add is dropped
    first = lines[0] if lines else ""
    found = _VERSION_LINE.fullmatch(first)
    if found is None:
        raise ExtractionError([
            f"{path.name}: the first line must be 'Version: <name>', such as 'Version: extract-v1'; it is {first!r}"
        ])
    return found.group(1)


def todo(threads_dir: Path, version: str) -> list[str]:
    """The ids of the threads to extract (again) under these instructions, in file-name order.

    A thread is listed when it has no extraction, when its extraction followed another instructions version, or
    when its extraction file is malformed (writing it again fixes that; `check` says what is wrong with it).
    """
    return list(_todo(Path(threads_dir), version))


def _todo(threads_dir: Path, version: str) -> dict[str, str]:
    """For every thread to extract: why, in a few words."""
    if not threads_dir.is_dir():
        raise ExtractionError([f"there is no threads folder at {threads_dir}"])
    reasons: dict[str, str] = {}
    # Outside the gold set's own folder, a gold thread Noemi hasn't labelled yet is never listed for the AI to read
    # (10 Oct 2026; engine.gold.unlabelled_gold_ids).
    in_gold = threads_dir.resolve().is_relative_to(DEFAULT_GOLD_DIR.resolve())
    never = set() if in_gold else unlabelled_gold_ids()
    for thread_path in sorted(threads_dir.glob("*.json")):
        if thread_path.stem in never:
            continue
        path = extracted_dir(threads_dir) / thread_path.name
        if not path.is_file():
            reasons[thread_path.stem] = "not extracted yet"
            continue
        extraction, problems = _read_extraction(path)
        if problems:
            reasons[thread_path.stem] = "its extraction file is malformed (see `check`)"
        elif extraction.instructions_version != version:
            reasons[thread_path.stem] = f"extracted with {extraction.instructions_version}"
    return reasons


# --- Command line ---

# --- The compact reading view the extractor reads (8 Oct 2026) ---

def shown_comment_ids(thread: Thread, max_comments: int = EXTRACT_MAX_COMMENTS) -> list[str]:
    """The usable comments the extractor reads: the `max_comments` highest-scored, in thread order."""
    usable = [c for c in thread.comments if c.status == "ok"]
    keep = {c.id for c in sorted(usable, key=lambda c: c.score, reverse=True)[:max_comments]}
    return [c.id for c in usable if c.id in keep]


def render_thread(thread: Thread, max_comments: int = EXTRACT_MAX_COMMENTS) -> str:
    """The thread as plain text: the post, then each shown comment with its id, what it replies to, score,
    author and flair. About half the reading of the JSON, with everything extraction needs."""
    by_id = {c.id: c for c in thread.comments}
    shown = shown_comment_ids(thread, max_comments)
    usable = sum(c.status == "ok" for c in thread.comments)
    lines = [
        f"Thread {thread.id} in r/{thread.community} ({thread.category}): {thread.title}",
        thread.body.strip() or "(no post text)",
        f"--- {len(shown)} of {usable} comments (the highest-scored, in thread order) ---",
    ]
    for comment_id in shown:
        c = by_id[comment_id]
        author = c.author.name if c.author else "deleted account"
        flair = f" [{c.author.flair}]" if c.author and c.author.flair else ""
        header = f"[{c.id}] score {c.score} | {author}{flair}"
        if c.parent_id:
            parent = by_id.get(c.parent_id)
            snippet = " ".join((parent.body if parent else "").split())[:120]
            header += f" | reply to {c.parent_id}: \"{snippet}\""
        lines += ["", header, c.body]
    return "\n".join(lines)


def main(argv: list[str], instructions: Path = DEFAULT_INSTRUCTIONS) -> int:
    """`instructions` can be swapped for another file, which is how the tests run `todo`."""
    if argv and argv[0] == "show" and len(argv) in (2, 3):
        folder = Path(argv[2]) if len(argv) == 3 else DEFAULT_THREADS_DIR
        thread = Thread.model_validate_json((folder / f"{argv[1]}.json").read_text(encoding="utf-8"))
        print(render_thread(thread))
        return 0
    if not argv or argv[0] not in ("todo", "check") or len(argv) > 2:
        print(__doc__)
        return 2
    threads_dir = Path(argv[1]) if len(argv) == 2 else DEFAULT_THREADS_DIR
    try:
        if argv[0] == "todo":
            return _print_todo(threads_dir, current_instructions_version(instructions), Path(instructions))
        return _print_check(threads_dir)
    except (ExtractionError, GoldSetError) as e:
        print(e)
        return 1


def _print_todo(threads_dir: Path, version: str, instructions: Path) -> int:
    reasons = _todo(threads_dir, version)
    if not reasons:
        print(f"Nothing to extract: every thread in {_shown(threads_dir)} has an extraction made with {version}.")
        return 0
    print(f"{len(reasons)} thread(s) to extract with {version} ({_shown(instructions)}):")
    for thread_id, reason in reasons.items():
        print(f"  {thread_id}  {reason}")
    print(
        f"Read each thread from {_shown(threads_dir)}/<id>.json and write its extraction to "
        f"{_shown(extracted_dir(threads_dir))}/<id>.json."
    )
    return 0


def _print_check(threads_dir: Path) -> int:
    results, problems = _check_folder(threads_dir)
    for thread_id, result in results.items():
        # A thread with no products can still have notes and care tips: their counts are printed all the same.
        if not result.kept and not result.rejected:
            print(f"{thread_id}: no products mentioned")
        else:
            print(f"{thread_id}: {len(result.kept)} kept, {len(result.rejected)} rejected")
        for mention in result.kept:
            print(f"  kept      {mention.comment_id}  {mention.stance:<9}  {mention.product}")
        # A rejected quote is never printed: it failed verification, so it must not be shown.
        for mention, reason in result.rejected:
            print(f"  rejected  {mention.comment_id}  {mention.stance:<9}  {mention.product}: {reason}")
        for kind, kept_items, rejected_items in (("notes", result.kept_notes, result.rejected_notes),
                                                 ("agreements", result.kept_agreements, result.rejected_agreements),
                                                 ("care tips", result.kept_care, result.rejected_care)):
            if kept_items or rejected_items:
                print(f"  {kind}: {len(kept_items)} kept, {len(rejected_items)} rejected")
                for item, reason in rejected_items:
                    print(f"  rejected  {item.comment_id}  {kind[:-1]}: {reason}")

    kept = sum(len(result.kept) for result in results.values())
    total = kept + sum(len(result.rejected) for result in results.values())
    rate = overall_quote_pass_rate(results.values())
    print(f"Total: {len(results)} thread(s), {total} mention{'' if total == 1 else 's'}: {kept} kept, {total - kept} rejected.")
    print(f"Quote pass rate: {rate:.0%}" if rate is not None else "Quote pass rate: none yet (no mentions)")
    if problems:
        print("Malformed extraction files, not checked (fix them, or extract those threads again):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    return 0


def _shown(path: Path) -> str:
    """A path as short as it can be: from the project folder when it's inside it."""
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
