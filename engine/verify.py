"""Keeping a slimmed library current, comment by comment (Noemi, 13 Oct 2026: "Keep only comments we use").

A slimmed thread (engine/slim.py) keeps only the comments answers use, and each of them is verified on Reddit through
its embed page (engine/live_check.py: Reddit's own widget page, free, one comment at a time, within Reddit's limits). A
read says (outcome):

    passing     the comment is there, and every quote the library holds of it is still found in it word for word
                (verification_quotes: its mentions', notes', care tips' and agreement's quotes; a comment kept only
                because a reply takes its product from it holds none, and passes while it is there)
    deleted     Reddit shows "[deleted]" in its place
    removed     Reddit shows "[removed]"
    changed     it is there, but a quote is no longer found: it was edited
    unreadable  the embed page showed no comment ("Not supported comment", about 1 kept comment in 20 on 13 Oct 2026)

The rule (config.LIBRARY_VERIFY_DAYS, 30 days, within Noemi's "about 37 days"). A kept comment that is
- found deleted or removed becomes a stub, as Reddit shows it ("[deleted]" or "[removed]", no writer);
- found edited, or not verified within LIBRARY_VERIFY_DAYS (counted from its last passing read; for a comment never
  verified, from the day the thread was read from the archive), keeps only its shape ("not_kept": no words, no writer;
  what it named is kept as the thread's other dropped comments' is, since it may well still be on Reddit);
and in every case it loses its mentions: each item of the extraction pointing to it (product mentions, notes, care
tips, agreements) is removed from the extraction file, so none of its words stays anywhere in the library. An
unreadable page proves nothing either way: the comment just isn't verified by it (the pre-check verifies those answers
show through Bright Data instead: Noemi's "Use Bright Data" decision), and its words go only when the deadline passes.
So a page Reddit redesigns can never wipe the library in one go.

Edited comments keep what still verifies (Noemi's decision 3 of 15 Oct 2026). A comment found edited keeps Reddit's
current text, and only the items whose quotes are still found in it word for word (and that the extraction's checks
kept before); the rest go, as before. Its current text is the one a read showed, never words from anywhere else: the
text of the read that found it edited, or of a newer read, as this machine's checks or the bucket's bundle hold it
(`reads`: the site's reads of the last 48 hours, which deploy.sh fetches next to the record and deletes once applied).
Without such a read (none of the last 48 hours, or the record knows a newer one whose text isn't at hand), or with no
item left, it goes as before. Its verified_at is the read's, so the 30-day deadline counts from it, and its `edited`
says how the read was made: "embed" (the embed page, whose formatting is read as plain words: answers never widen its
quotes, engine/answer.py) or "bright_data" (as written). A reply that takes its product from such a comment (refers_to)
follows the same rule: its item stays only while the comment above keeps an item of the same product (module 4's
names), so still says it word for word; a comment nothing points to any more loses its words, as slimming would have
it. The daily plan lists such comments to be read again like answers' comments (every 40 hours, engine/read_ahead.py)
until a deploy applies them, so a read with their current text is always in the bundle (engine/precheck.py). A read
whose text holds the very words the library holds, formatting aside (a link's address, bold and italics, punctuation
and spacing: same_words), isn't an edit at all: it verifies the comment whole, which keeps its words and items (until
15 Oct 2026 the embed page's formatting was read as spaces, and such reads stay in the bundle for 48 hours).

Where the reads come from:
- the daily pre-check (engine/precheck.py: a Cloud Run job): the comments answers would show, then the kept comments
  verified longest ago, within config.LIBRARY_VERIFY_READS a day. Since 14 Oct 2026 (the free-tier redesign) the job
  lists them in its plan and the site reads them over the day (engine/read_ahead.py); the job's next run records what
  each read said, from the bundle the site shares (each read is in it for 48 hours, a page with no comment included).
  Every read is recorded in the verification record
  (Ledger): each kept comment's latest read (when, and its outcome) and its last pass. Ids, dates and outcomes only,
  never anyone's words, so it outlives the 48-hour checks: it is kept in the live checks' bucket next to their bundle
  (live_check/verified.json, written again every run, so the bucket's 2-day rule only removes it if the job stops) and
  on the machine that ran it (.cache/verified.json);
- the checks made on this machine in the last 48 hours (.cache/live_check: a pre-check run here, or answers' own).
- the site's reads of the last 48 hours, from the bucket's bundle (15 Oct 2026; `--bundle FILE`): what each read said,
  recorded like this machine's, and the text a comment found edited keeps.
The library is baked into the site's image when it is deployed from Noemi's computer, so the reads are applied there
before each deploy (deploy/cloudrun/deploy.sh fetches the bucket's record and bundle): `python -m engine.library
apply-checks` stamps each passing comment's verified_at and drops what failed or ran out. check-live applies the
deadline too.

    python -m engine.library apply-checks [--ledger FILE]... [--checks DIR] [--bundle FILE] [--dry-run] [--library DIR]
"""

import html
import json
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from engine.config import LIBRARY_VERIFY_DAYS
from engine.extract import Extraction, check_extraction, extracted_dir
from engine.match_products import known_aliases, same_product
from engine.models import Thread
from engine.slim import PLACEHOLDERS, _source_of, kept_comment_ids, known_types, names_in, thread_json, write_file
from engine.verify_quotes import find_quote

OUTCOMES = ("passing", "deleted", "removed", "changed", "unreadable")
FAILED = ("deleted", "removed", "changed")  # a read that drops the comment
LEDGER_NAME = "verified.json"  # the record's name, in the bucket (under live_check/) and on this machine (.cache/)
_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def outcome(text: str | None, quotes) -> str:
    """What a read of a kept comment says (see the module's docstring): `text` is the comment as Reddit's embed page
    showed it (None: no comment on the page), `quotes` the quotes the library holds of it."""
    if text is None:
        return "unreadable"
    shown = text.strip()
    if shown in PLACEHOLDERS:
        return "deleted" if shown == "[deleted]" else "removed"
    return "passing" if all(find_quote(text, quote) is not None for quote in quotes) else "changed"


def verification_quotes(thread: Thread, extraction: Extraction) -> dict[str, tuple[str, ...]]:
    """{kept comment id: the quotes of it its extraction holds, each found word for word in it}: what a read must find
    in it again. A quote the AI wrote that was never found in the comment (a rejected item) can't be looked for."""
    kept = {c.id: c for c in thread.comments if c.status == "ok"}
    quotes: dict[str, list[str]] = {cid: [] for cid in kept}
    for item in [*extraction.mentions, *extraction.notes, *extraction.agreements, *extraction.care]:
        comment = kept.get(item.comment_id)
        if comment is not None and item.quote not in quotes[comment.id] and find_quote(comment.body, item.quote):
            quotes[comment.id].append(item.quote)
    return {cid: tuple(found) for cid, found in quotes.items()}


# --- The verification record ---

@dataclass(frozen=True)
class LedgerEntry:
    """One kept comment's latest read (when, and what it said) and its last passing read."""

    at: datetime
    outcome: str
    passed: datetime | None = None


class Ledger:
    """The verification record: each kept comment's latest read and last pass, by comment id. No words, ever."""

    def __init__(self):
        self.entries: dict[str, LedgerEntry] = {}

    def get(self, comment_id: str) -> LedgerEntry | None:
        return self.entries.get(comment_id)

    def record(self, comment_id: str, at: datetime, outcome: str) -> None:
        """Takes in one read. The latest read decides what the comment's state is; the last pass is kept apart, so an
        unreadable page after a pass doesn't make a verified comment unverified."""
        old = self.entries.get(comment_id)
        passes = [d for d in (old.passed if old else None, at if outcome == "passing" else None) if d is not None]
        passed = max(passes) if passes else None
        if old is None or at > old.at:
            self.entries[comment_id] = LedgerEntry(at, outcome, passed)
        else:
            self.entries[comment_id] = replace(old, passed=passed)

    def merge(self, other: "Ledger") -> None:
        for comment_id, entry in other.entries.items():
            if entry.passed is not None:
                self.record(comment_id, entry.passed, "passing")
            self.record(comment_id, entry.at, entry.outcome)

    def keep_only(self, comment_ids: set[str]) -> None:
        """Forgets the comments no longer kept (dropped, or their thread gone)."""
        self.entries = {cid: entry for cid, entry in self.entries.items() if cid in comment_ids}

    def dumps(self, now: datetime) -> bytes:
        comments = {cid: {"at": e.at.isoformat(), "outcome": e.outcome,
                          "passed": e.passed.isoformat() if e.passed else None}
                    for cid, e in sorted(self.entries.items())}
        return json.dumps({"written_at": now.isoformat(), "comments": comments}).encode("utf-8")

    @classmethod
    def loads(cls, data: bytes | str | None) -> "Ledger":
        """A record as written by dumps; one that can't be read is empty, and an entry that can't be read is left out."""
        ledger = cls()
        try:
            comments = json.loads(data)["comments"]
        except (TypeError, ValueError, KeyError):
            return ledger
        for cid, entry in comments.items() if isinstance(comments, dict) else ():
            try:
                at, passed = _when(entry["at"]), _when(entry["passed"]) if entry["passed"] else None
                if _ID.match(cid) and entry["outcome"] in OUTCOMES:
                    ledger.entries[cid] = LedgerEntry(at, entry["outcome"], passed)
            except (TypeError, ValueError, KeyError):
                continue
        return ledger

    @classmethod
    def load(cls, path: Path) -> "Ledger":
        try:
            return cls.loads(Path(path).read_bytes())
        except OSError:
            return cls()

    def save(self, path: Path, now: datetime) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        write_file(Path(path), self.dumps(now))


def _when(value: str) -> datetime:
    moment = datetime.fromisoformat(value)
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


# --- The kept comments of a library ---

@dataclass(frozen=True)
class KeptComment:
    """A comment a slimmed thread keeps, as its verification needs it."""

    thread_id: str
    comment_id: str
    url: str
    quotes: tuple[str, ...]
    verified_at: datetime | None  # as the thread file says (the record may know a newer pass)
    collected_at: datetime  # when its thread was read: a comment never verified counts from it
    order: int  # its place in its thread


def slimmed_threads(folder: Path, problems: dict[str, str] | None = None):
    """Each slimmed thread of the library with its extraction, as (path, thread, extraction file's data, extraction).
    A thread or extraction that can't be read is named in `problems` and left out."""
    threads_dir = Path(folder) / "threads"
    for path in sorted(threads_dir.glob("*.json")) if threads_dir.is_dir() else ():
        try:
            thread = Thread.model_validate_json(path.read_bytes())
        except ValueError:
            if problems is not None:
                problems[path.stem] = "the thread file doesn't load"
            continue
        if not thread.slimmed:
            continue
        extraction_path = extracted_dir(threads_dir) / path.name
        try:
            raw = json.loads(extraction_path.read_text(encoding="utf-8"))
            extraction = Extraction.model_validate(raw)
        except (OSError, ValueError):
            if problems is not None:
                problems[thread.id] = "its extraction is missing or malformed"
            continue
        yield path, thread, raw, extraction


def kept_comments(folder: Path) -> list[KeptComment]:
    """Every comment the library's slimmed threads keep, in file and thread order."""
    found = []
    for _, thread, _, extraction in slimmed_threads(folder):
        quotes = verification_quotes(thread, extraction)
        for order, comment in enumerate(thread.comments):
            if comment.status == "ok":
                found.append(KeptComment(thread.id, comment.id, comment.url, quotes[comment.id], comment.verified_at,
                                         thread.collected_at, order))
    return found


def record_saved_checks(folder: Path, checker, ledger: Ledger, kept: list[KeptComment] | None = None) -> int:
    """Takes into the record what the checks saved in the last 48 hours say about the kept comments (`checker`: an
    engine.live_check.LiveChecker; Reddit is never read here). How many it took in."""
    taken = 0
    for comment in kept_comments(folder) if kept is None else kept:
        saved = checker.saved_text(comment.url)
        if saved is not None:
            ledger.record(comment.comment_id, saved[0], outcome(saved[1], comment.quotes))
            taken += 1
    return taken


# --- Applying the reads to the library ---

@dataclass
class ApplyResult:
    """What applying the record did, in counts (never anyone's words)."""

    threads: int = 0  # slimmed threads looked at
    kept: int = 0  # comments they kept whole before
    stamped: int = 0  # given a newer verified_at
    # by why: deleted, removed, changed, expired; and "not used": a comment nothing points to any more, once the items
    # of a reply that took its product from an edited comment went (15 Oct 2026)
    dropped: dict[str, int] = field(default_factory=dict)
    items_removed: int = 0  # mentions, notes, care tips and agreements removed from the extractions
    # Found edited on Reddit and kept Reddit's current text with the items still found in it word for word (Noemi's
    # decision 3 of 15 Oct 2026), and how many items those are.
    edited: int = 0
    items_after_edit: int = 0
    changed_threads: list[str] = field(default_factory=list)
    problems: dict[str, str] = field(default_factory=dict)
    dry_run: bool = False

    @property
    def dropped_total(self) -> int:
        return sum(self.dropped.values())


def expired(comment, thread: Thread, now: datetime) -> bool:
    """Whether a kept comment has gone more than LIBRARY_VERIFY_DAYS calendar days without a passing read (a comment
    never verified: since its thread was read)."""
    since = comment.verified_at or thread.collected_at
    return (now.date() - since.date()).days > LIBRARY_VERIFY_DAYS


def apply_checks(folder: Path, ledger: Ledger, now: datetime | None = None, dry_run: bool = False,
                 reads=()) -> ApplyResult:
    """Applies the record's reads to the library's slimmed threads (see the module's docstring), then the deadline.
    Whole threads (not extracted yet, or gold-set threads) are never touched. With `dry_run`, counts and writes
    nothing. The thread file is written first, then the extraction, each whole. `reads`: the live checkers
    (engine.live_check.LiveChecker; Reddit is never read here) whose reads of the last 48 hours give a comment found
    edited its current text (this machine's checks, the bucket's bundle: Noemi's decision 3 of 15 Oct 2026); with none,
    such a comment goes as before."""
    now = now or datetime.now(UTC)
    result = ApplyResult(dry_run=dry_run)
    types = None  # known_types, worked out once there is something to drop
    for path, thread, raw, extraction in slimmed_threads(folder, result.problems):
        result.threads += 1
        stamps, drops, texts = {}, {}, {}
        quotes = None  # verification_quotes, worked out once one of the thread's comments is found edited
        for comment in thread.comments:
            if comment.status != "ok":
                continue
            result.kept += 1
            entry = ledger.get(comment.id)
            verified = comment.verified_at
            if entry is not None and entry.passed is not None and (verified is None or entry.passed > verified):
                verified = stamps[comment.id] = entry.passed
            if entry is not None and entry.outcome in FAILED and (verified is None or entry.at > verified):
                drops[comment.id] = entry.outcome
                if entry.outcome == "changed" and reads:
                    quotes = verification_quotes(thread, extraction) if quotes is None else quotes
                    found = current_text(comment.url, entry.at, quotes.get(comment.id, ()), reads)
                    if found is not None and same_words(comment.body, found[1]):
                        # Formatting aside, Reddit shows the very words the library holds: it wasn't edited, and the
                        # read verifies it whole (a read made before the embed page's formatting fix of 15 Oct 2026).
                        del drops[comment.id]
                        stamps[comment.id] = max(found[0], verified) if verified is not None else found[0]
                    elif found is not None:
                        texts[comment.id] = found
            elif expired(comment.model_copy(update={"verified_at": verified}), thread, now):
                drops[comment.id] = "expired"
        for comment_id in drops:
            stamps.pop(comment_id, None)
        # Edited comments keep Reddit's current text and the items still found in it (Noemi, 15 Oct 2026); a comment
        # nothing points to once the items that went are gone loses its words too.
        edits, raw, removed_now, unused = (_kept_after_edit(thread, raw, extraction, texts) if texts
                                           else ({}, raw, 0, set()))
        for comment_id in edits:
            del drops[comment_id]
        drops |= {comment_id: "not used" for comment_id in unused if comment_id not in drops}
        # Items of a comment the thread no longer keeps whole (a run stopped between its two files) go too.
        status = {c.id: c.status for c in thread.comments}
        left_over = {item.comment_id for item in [*extraction.mentions, *extraction.notes, *extraction.agreements,
                                                  *extraction.care] if status.get(item.comment_id, "ok") != "ok"}
        if not stamps and not drops and not left_over and not edits:
            continue
        if drops and types is None:
            types = known_types(folder)
        new_thread, new_raw, removed = _applied(thread, raw, stamps, drops, types or (), left_over, edits)
        removed += removed_now
        result.stamped += len(stamps)
        for why in drops.values():
            result.dropped[why] = result.dropped.get(why, 0) + 1
        result.items_removed += removed
        result.edited += len(edits)
        result.items_after_edit += sum(1 for kind in _KINDS for item in new_raw.get(kind) or []
                                       if isinstance(item, dict) and item.get("comment_id") in edits)
        result.changed_threads.append(thread.id)
        if not dry_run:
            write_file(path, thread_json(new_thread))
            if removed:
                write_file(extracted_dir(path.parent) / path.name,
                           (json.dumps(new_raw, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    return result


_KINDS = ("mentions", "notes", "agreements", "care")  # the extraction's items, each pointing to its comment
_LINK = re.compile(r"\[([^\]]*)\]\([^)\s]*\)")  # a markdown link, which the embed page shows as its words only
_ESCAPED = re.compile(r"\\(\S)")  # Reddit's backslash before a markdown character: "\[", "\*"
_WORD = re.compile(r"[^\W_]+")


def same_words(body: str, text: str) -> bool:
    """Whether a read's text holds the very words a comment's body does, in the same order, formatting aside: a link's
    address (the embed page shows its words only), bold and italics, escapes, entities, punctuation and spacing (15 Oct
    2026). Until that day's fix the embed page's formatting was read as spaces ("solid**.**" as "solid ."), so such a
    read made a comment look edited when not one word had changed; it verifies the comment whole instead."""
    def words(value: str) -> list[str]:
        return _WORD.findall(html.unescape(_ESCAPED.sub(r"\1", _LINK.sub(r"\1", value))).lower())

    return bool(text) and words(body) == words(text)


def current_text(url: str, since: datetime, quotes, reads) -> tuple[datetime, str, str] | None:
    """Reddit's current text of a kept comment found edited (Noemi's decision 3 of 15 Oct 2026), as (when it was read,
    the text, how: "embed" or "bright_data"): the newest of `reads`' last reads of it in the last 48 hours
    (engine.live_check.LiveChecker.last_read), when it was made at `since` (the read the record's outcome comes from)
    or later, holds a comment and says it was edited too (`quotes`: those the library holds of it). None otherwise: no
    read with words is at hand, the record knows a newer read than any here, or the newest says something else."""
    found = [read for checker in reads if (read := checker.last_read(url)) is not None]
    if not found:
        return None
    at, text, via = max(found, key=lambda read: read[0])
    if text is None or at < since or outcome(text, quotes) != "changed":
        return None
    return at, text, via or "embed"


def _kept_after_edit(thread: Thread, raw: dict, extraction: Extraction,
                     texts: dict[str, tuple[datetime, str, str]]) -> tuple[dict, dict, int, set[str]]:
    """The edited comments that keep Reddit's current text ({comment id: (read at, text, via)}, from `texts`), the
    extraction file's data without the items that go, how many went, and the comments nothing points to any more
    (Noemi's decision 3 of 15 Oct 2026). An item of an edited comment stays when the extraction's checks kept it and its
    quote is found word for word in the text; a reply's mention taking its product from an edited comment (refers_to)
    stays when that comment keeps a mention of the same product (module 4's names). An edited comment left with no item
    isn't one of them: it goes whole, as before, and the replies taking their product from it stay as they were (the
    extraction's check rejects them, saying their source was edited). Every other item stays as it is."""
    checked = check_extraction(extraction, thread)
    passed = {id(item) for group in (checked.kept, checked.kept_notes, checked.kept_agreements, checked.kept_care)
              for item in group}
    comments = {c.id: c for c in thread.comments}
    items = [(kind, index, item) for kind in _KINDS for index, item in enumerate(getattr(extraction, kind))]
    edited = set(texts)

    def source_of(item):
        return _source_of(item, comments) if getattr(item, "refers_to", None) in ("parent", "earlier") else None

    while True:
        verdict: dict[int, bool] = {}

        def stays(item) -> bool:
            if id(item) in verdict:
                return verdict[id(item)]
            verdict[id(item)] = False  # a source is always further up the thread: no item waits on itself
            ok = item.comment_id not in edited or (id(item) in passed and find_quote(texts[item.comment_id][1],
                                                                                     item.quote) is not None)
            source = source_of(item)
            if ok and source is not None and source.id in edited:
                aliases = known_aliases().get(item.category, {})
                ok = any(stays(other) for other in extraction.mentions
                         if other.comment_id == source.id and same_product(other.product, item.product, aliases))
            verdict[id(item)] = ok
            return ok

        empty = {cid for cid in edited if not any(stays(item) for _, _, item in items if item.comment_id == cid)}
        if not empty:
            break
        edited -= empty  # nothing of it is still found: it goes whole, as before
    going = {(kind, index) for kind, index, item in items if not stays(item)
             and (item.comment_id in edited or ((source := source_of(item)) is not None and source.id in edited))}
    new_raw = dict(raw)
    for kind in _KINDS:
        if isinstance(raw.get(kind), list):
            new_raw[kind] = [item for index, item in enumerate(raw[kind]) if (kind, index) not in going]
    unused = kept_comment_ids(thread, extraction) - kept_comment_ids(thread, Extraction.model_validate(new_raw))
    return {cid: texts[cid] for cid in edited}, new_raw, len(going), unused - edited


def _applied(thread: Thread, raw: dict, stamps: dict, drops: dict, types,
             left_over: set[str] = frozenset(), edits: dict | None = None) -> tuple[Thread, dict, int]:
    """The thread with its new stamps and drops, its extraction file's data without the items of the dropped comments
    (and of `left_over`: comments it already didn't keep whole), and how many items were removed. `edits`: the comments
    found edited that keep Reddit's current text ({comment id: (read at, text, how it was read)}; 15 Oct 2026)."""
    facts = thread.whole_thread
    names, first_seen, gone_why = dict(facts.comment_names), dict(facts.first_seen), dict(facts.dropped)
    staying = [c for c in thread.comments if c.status == "ok" and c.id not in drops and c.author is not None]
    kept_since = {}
    for comment in staying:
        kept_since[comment.author.name] = min(kept_since.get(comment.author.name, comment.created_at),
                                              comment.created_at)
    comments = []
    for comment in thread.comments:
        why = drops.get(comment.id)
        if why in ("deleted", "removed"):  # gone from Reddit: a stub, as Reddit shows it
            comment = comment.model_copy(update={"status": why, "body": f"[{why}]", "author": None,
                                                 "verified_at": None, "edited": None})
        elif why is not None:  # edited, or not verified in time: still on Reddit as far as we know
            if found := names_in(comment.body, types):
                names[comment.id] = found
            if why in ("changed", "expired"):  # a verification's reason (WholeThread.dropped); "not used" has none:
                gone_why[comment.id] = why     # engine.ethics's removals leave a stub like slimming's (15 Oct 2026)
            name = comment.author.name if comment.author is not None else None
            if name in kept_since and comment.created_at < min(first_seen.get(name, kept_since[name]),
                                                              kept_since[name]):
                first_seen[name] = comment.created_at
            comment = comment.model_copy(update={"status": "not_kept", "body": "", "author": None,
                                                 "verified_at": None, "edited": None})
        elif comment.id in (edits or {}):  # Reddit's current text, as the read showed it (15 Oct 2026)
            at, text, via = edits[comment.id]
            comment = comment.model_copy(update={"body": text, "verified_at": at, "edited": via})
        elif comment.id in stamps:
            comment = comment.model_copy(update={"verified_at": stamps[comment.id]})
        comments.append(comment)
    first_seen = {name: when for name, when in first_seen.items() if name in kept_since}  # no other writer stays
    new_thread = Thread.model_validate(thread.model_copy(update={
        "comments": comments,
        "whole_thread": facts.model_copy(update={"comment_names": names, "first_seen": first_seen,
                                                 "dropped": gone_why})}).model_dump())
    new_raw, removed, gone = dict(raw), 0, set(drops) | set(left_over)
    for kind in ("mentions", "notes", "agreements", "care"):
        if isinstance(raw.get(kind), list):
            new_raw[kind] = [item for item in raw[kind] if item.get("comment_id") not in gone]
            removed += len(raw[kind]) - len(new_raw[kind])
    return new_thread, new_raw, removed


def expire(folder: Path, now: datetime | None = None, dry_run: bool = False) -> ApplyResult:
    """The deadline alone (check-live runs it): kept comments not verified within LIBRARY_VERIFY_DAYS lose their words
    and mentions."""
    return apply_checks(folder, Ledger(), now, dry_run)


# --- Words verification dropped by mistake, put back from the backup (15 Oct 2026) ---

@dataclass(frozen=True)
class Restored:
    """What restore_words did for one comment: ids and counts only."""

    thread_id: str
    comment_id: str
    # "passing": put back whole; "edited": put back with Reddit's current text and the items still found in it (Noemi's
    # decision 3 of 15 Oct 2026); else what Reddit's page says now ("changed": none of its quotes is still there,
    # "deleted"...), or why nothing was read
    outcome: str
    items: int = 0  # its items put back in the extraction file
    read_at: datetime | None = None


def restore_words(folder: Path, backup, pairs, checker, dry_run: bool = False) -> list[Restored]:
    """Gives back their words the comments of `pairs` ((thread id, comment id)) that slimming kept and verification
    then dropped (not_kept since), when Reddit's embed page, read now through `checker` (an
    engine.live_check.LiveChecker; a read of the last hour counts), passes the check of every quote the comment backed.
    From `backup`, the library as it was before slimming (a folder holding threads/ and extracted/, or the .tgz made of
    one): the comment's words and writer, and its items back in the extraction file, checked as they were then; its
    verified_at is the read, so the next deploy's apply-checks keeps it (a recorded "changed" is older). The thread's
    facts that hang on which comments are kept are worked out again (the product types listed for comments not kept,
    writers' first comments). Made for 15 Oct 2026, when formatting had made a check take 7 comments as edited.

    Since Noemi's decision 3 of 15 Oct 2026, a comment Reddit shows edited is put back as apply_checks keeps one: with
    Reddit's current text, as the read shows it, and only those of its items (from the backup) still found in it word
    for word, a reply taking its product from it keeping its item only while it keeps a mention of that product
    (_kept_after_edit; outcome "edited"). One whose words Reddit shows unchanged, formatting aside (same_words), is
    put back whole, as one passing. One none of whose quotes is still found, or that Reddit shows deleted or removed, or
    that slimming never kept, is left as it is."""
    from engine.slim import _first_seen_dropped

    whole_of, raw_of = _backup_reader(backup)
    done = []
    for thread_id, comment_id in pairs:
        thread_path = Path(folder) / "threads" / f"{thread_id}.json"
        extraction_path = extracted_dir(thread_path.parent) / thread_path.name
        whole_bytes, old_bytes = whole_of(thread_id), raw_of(thread_id)
        try:
            current = Thread.model_validate_json(thread_path.read_bytes())
            raw = json.loads(extraction_path.read_text(encoding="utf-8"))
            whole = Thread.model_validate_json(whole_bytes) if whole_bytes is not None else None
            old_raw = json.loads(old_bytes) if old_bytes is not None else None
            old_extraction = Extraction.model_validate(old_raw) if old_raw is not None else None
        except (OSError, ValueError):
            done.append(Restored(thread_id, comment_id, "not dropped by verification"))
            continue
        now = {c.id: c for c in current.comments}
        if (whole is None or old_extraction is None or not current.slimmed or comment_id not in now
                or now[comment_id].status != "not_kept" or comment_id not in kept_comment_ids(whole, old_extraction)):
            done.append(Restored(thread_id, comment_id, "not dropped by verification"))
            continue
        original = next(c for c in whole.comments if c.id == comment_id)
        read = checker.read_text(original.url, max_age=timedelta(hours=1))
        if read is None:
            done.append(Restored(thread_id, comment_id, "couldn't be read now"))
            continue
        said = outcome(read[1], verification_quotes(whole, old_extraction)[comment_id])
        if said == "changed" and same_words(original.body, read[1]):
            said = "passing"  # formatting aside, the very words it had (a link's address, bold, spacing: same_words)
        if said not in ("passing", "changed"):
            done.append(Restored(thread_id, comment_id, said, read_at=read[0]))
            continue
        comments = [original.model_copy(update={"verified_at": read[0]}) if c.id == comment_id else c
                    for c in current.comments]
        facts = current.whole_thread
        restored = Thread.model_validate(current.model_copy(update={"comments": comments, "whole_thread": facts.model_copy(
            update={"comment_names": {k: v for k, v in facts.comment_names.items() if k != comment_id},
                    "first_seen": _first_seen_dropped(whole, {c.id for c in comments if c.status == "ok"}),
                    "dropped": {k: v for k, v in facts.dropped.items() if k != comment_id}})}).model_dump())
        new_raw = dict(raw)
        for kind in _KINDS:
            old_items, now_items = old_raw.get(kind) or [], raw.get(kind) or []
            new_raw[kind] = [i for i in old_items if i.get("comment_id") == comment_id or i in now_items] + [
                i for i in now_items if i not in old_items]
        if said == "changed":  # Reddit's current text, and only the items still found in it (15 Oct 2026)
            last = checker.last_read(original.url)
            via = (last[2] if last is not None and last[0] == read[0] else None) or "embed"
            edits, new_raw, _, unused = _kept_after_edit(restored, new_raw, Extraction.model_validate(new_raw),
                                                         {comment_id: (read[0], read[1], via)})
            if comment_id not in edits:
                done.append(Restored(thread_id, comment_id, "changed", read_at=read[0]))
                continue
            restored, new_raw, _ = _applied(restored, new_raw, {}, {cid: "not used" for cid in unused},
                                            known_types(folder) if unused else (), edits=edits)
            check = check_extraction(Extraction.model_validate(new_raw), restored)
            if any(item.comment_id == comment_id for _, items in _rejected(check) for item, _ in items):
                done.append(Restored(thread_id, comment_id, "its items wouldn't be checked as before slimming",
                                     read_at=read[0]))
                continue
        elif _items_checked(old_extraction, whole, comment_id) != _items_checked(
                Extraction.model_validate(new_raw), restored, comment_id):
            done.append(Restored(thread_id, comment_id, "its items wouldn't be checked as before slimming",
                                 read_at=read[0]))
            continue
        back = sum(1 for kind in _KINDS for i in new_raw.get(kind) or []
                   if i.get("comment_id") == comment_id and i not in (raw.get(kind) or []))
        if not dry_run:
            write_file(thread_path, thread_json(restored))
            write_file(extraction_path, (json.dumps(new_raw, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
        done.append(Restored(thread_id, comment_id, "passing" if said == "passing" else "edited", back, read[0]))
    return done


def _rejected(check) -> list[tuple[str, list]]:
    """The items a check of an extraction rejected, by kind, with why."""
    return [("mentions", check.rejected), ("notes", check.rejected_notes), ("agreements", check.rejected_agreements),
            ("care", check.rejected_care)]


def _items_checked(extraction: Extraction, thread: Thread, comment_id: str) -> tuple:
    """A comment's items as the extraction's check takes them: those kept, and those rejected with why."""
    result = check_extraction(extraction, thread)
    kept = [i.model_dump_json() for group in (result.kept, result.kept_notes, result.kept_agreements, result.kept_care)
            for i in group if i.comment_id == comment_id]
    rejected = [(i.model_dump_json(), why) for group in (result.rejected, result.rejected_notes,
                                                          result.rejected_agreements, result.rejected_care)
                for i, why in group if i.comment_id == comment_id]
    return kept, rejected


def _backup_reader(backup):
    """(whole thread's bytes, extraction file's bytes) by thread id, from a backup folder or its .tgz (None: not in it)."""
    backup = Path(backup)
    if backup.is_dir():
        def read(kind):
            def of(thread_id):
                path = backup / kind / f"{thread_id}.json"
                return path.read_bytes() if path.is_file() else None
            return of
        return read("threads"), read("extracted")
    import tarfile

    archive = tarfile.open(backup, "r:*")
    members = {m.name: m for m in archive.getmembers() if m.isfile()}

    def member(kind):
        def of(thread_id):
            name = next((n for n in members if n.endswith(f"{kind}/{thread_id}.json")), None)
            return archive.extractfile(members[name]).read() if name else None
        return of
    return member("threads"), member("extracted")


def report(result: ApplyResult) -> str:
    """The run in a few lines: counts only."""
    d = result.dropped
    lines = [f"Kept comments in {result.threads} slimmed thread(s): {result.kept:,}; stamped with a newer passing check "
             f"on Reddit: {result.stamped:,}.",
             f"Found edited on Reddit: {result.edited} kept Reddit's current text, with the {result.items_after_edit} "
             f"item(s) still found in it word for word.",
             f"Words and mentions dropped: deleted on Reddit: {d.get('deleted', 0)}, removed on Reddit: "
             f"{d.get('removed', 0)}, edited: {d.get('changed', 0)}, not verified within {LIBRARY_VERIFY_DAYS} days: "
             f"{d.get('expired', 0)}, no longer used: {d.get('not used', 0)} (items removed from the extractions: "
             f"{result.items_removed})."]
    if result.dry_run:
        lines.append("Dry run: nothing written.")
    for thread_id, why in result.problems.items():
        lines.append(f"  not applied, {why}: {thread_id}")
    return "\n".join(lines)
