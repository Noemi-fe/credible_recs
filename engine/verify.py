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
The library is baked into the site's image when it is deployed from Noemi's computer, so the reads are applied there
before each deploy (deploy/cloudrun/deploy.sh fetches the bucket's record): `python -m engine.library apply-checks`
stamps each passing comment's verified_at and drops what failed or ran out. check-live applies the deadline too.

    python -m engine.library apply-checks [--ledger FILE]... [--checks DIR] [--dry-run] [--library DIR]
"""

import json
import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from engine.config import LIBRARY_VERIFY_DAYS
from engine.extract import Extraction, extracted_dir
from engine.models import Thread
from engine.slim import PLACEHOLDERS, known_types, names_in, thread_json, write_file
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
    dropped: dict[str, int] = field(default_factory=dict)  # by why: deleted, removed, changed, expired
    items_removed: int = 0  # mentions, notes, care tips and agreements removed from the extractions
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


def apply_checks(folder: Path, ledger: Ledger, now: datetime | None = None, dry_run: bool = False) -> ApplyResult:
    """Applies the record's reads to the library's slimmed threads (see the module's docstring), then the deadline.
    Whole threads (not extracted yet, or gold-set threads) are never touched. With `dry_run`, counts and writes
    nothing. The thread file is written first, then the extraction, each whole."""
    now = now or datetime.now(UTC)
    result = ApplyResult(dry_run=dry_run)
    types = None  # known_types, worked out once there is something to drop
    for path, thread, raw, extraction in slimmed_threads(folder, result.problems):
        result.threads += 1
        stamps, drops = {}, {}
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
            elif expired(comment.model_copy(update={"verified_at": verified}), thread, now):
                drops[comment.id] = "expired"
        for comment_id in drops:
            stamps.pop(comment_id, None)
        # Items of a comment the thread no longer keeps whole (a run stopped between its two files) go too.
        status = {c.id: c.status for c in thread.comments}
        left_over = {item.comment_id for item in [*extraction.mentions, *extraction.notes, *extraction.agreements,
                                                  *extraction.care] if status.get(item.comment_id, "ok") != "ok"}
        if not stamps and not drops and not left_over:
            continue
        if drops and types is None:
            types = known_types(folder)
        new_thread, new_raw, removed = _applied(thread, raw, stamps, drops, types or (), left_over)
        result.stamped += len(stamps)
        for why in drops.values():
            result.dropped[why] = result.dropped.get(why, 0) + 1
        result.items_removed += removed
        result.changed_threads.append(thread.id)
        if not dry_run:
            write_file(path, thread_json(new_thread))
            if removed:
                write_file(extracted_dir(path.parent) / path.name,
                           (json.dumps(new_raw, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    return result


def _applied(thread: Thread, raw: dict, stamps: dict, drops: dict, types,
             left_over: set[str] = frozenset()) -> tuple[Thread, dict, int]:
    """The thread with its new stamps and drops, its extraction file's data without the items of the dropped comments
    (and of `left_over`: comments it already didn't keep whole), and how many items were removed."""
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
                                                 "verified_at": None})
        elif why is not None:  # edited, or not verified in time: still on Reddit as far as we know
            if found := names_in(comment.body, types):
                names[comment.id] = found
            gone_why[comment.id] = why
            name = comment.author.name if comment.author is not None else None
            if name in kept_since and comment.created_at < min(first_seen.get(name, kept_since[name]),
                                                              kept_since[name]):
                first_seen[name] = comment.created_at
            comment = comment.model_copy(update={"status": "not_kept", "body": "", "author": None,
                                                 "verified_at": None})
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
    outcome: str  # "passing": put back; else what Reddit's page says now ("changed"...), or why nothing was read
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
    writers' first comments). A comment Reddit shows edited, deleted or removed, or that slimming never kept, is left
    as it is. Made for 15 Oct 2026, when formatting had made a check take 7 comments as edited."""
    from engine.slim import _first_seen_dropped, kept_comment_ids

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
        if said != "passing":
            done.append(Restored(thread_id, comment_id, said, read_at=read[0]))
            continue
        comments = [original.model_copy(update={"verified_at": read[0]}) if c.id == comment_id else c
                    for c in current.comments]
        facts = current.whole_thread
        restored = Thread.model_validate(current.model_copy(update={"comments": comments, "whole_thread": facts.model_copy(
            update={"comment_names": {k: v for k, v in facts.comment_names.items() if k != comment_id},
                    "first_seen": _first_seen_dropped(whole, {c.id for c in comments if c.status == "ok"}),
                    "dropped": {k: v for k, v in facts.dropped.items() if k != comment_id}})}).model_dump())
        new_raw, back = dict(raw), 0
        for kind in ("mentions", "notes", "agreements", "care"):
            old_items, now_items = old_raw.get(kind) or [], raw.get(kind) or []
            back += sum(1 for i in old_items if i.get("comment_id") == comment_id and i not in now_items)
            new_raw[kind] = [i for i in old_items if i.get("comment_id") == comment_id or i in now_items] + [
                i for i in now_items if i not in old_items]
        if _items_checked(old_extraction, whole, comment_id) != _items_checked(
                Extraction.model_validate(new_raw), restored, comment_id):
            done.append(Restored(thread_id, comment_id, "its items wouldn't be checked as before slimming",
                                 read_at=read[0]))
            continue
        if not dry_run:
            write_file(thread_path, thread_json(restored))
            write_file(extraction_path, (json.dumps(new_raw, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
        done.append(Restored(thread_id, comment_id, "passing", back, read[0]))
    return done


def _items_checked(extraction: Extraction, thread: Thread, comment_id: str) -> tuple:
    """A comment's items as the extraction's check takes them: those kept, and those rejected with why."""
    from engine.extract import check_extraction

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
             f"Words and mentions dropped: deleted on Reddit: {d.get('deleted', 0)}, removed on Reddit: "
             f"{d.get('removed', 0)}, edited: {d.get('changed', 0)}, not verified within {LIBRARY_VERIFY_DAYS} days: "
             f"{d.get('expired', 0)} (items removed from the extractions: {result.items_removed})."]
    if result.dry_run:
        lines.append("Dry run: nothing written.")
    for thread_id, why in result.problems.items():
        lines.append(f"  not applied, {why}: {thread_id}")
    return "\n".join(lines)
