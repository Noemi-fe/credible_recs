"""Ethics-only warnings (Noemi's decision 5 of 15 Oct 2026): a warning that rests only on a maker's ethics (animal
welfare, labour practices, politics, a boycott) and says nothing about the product itself counts for nothing (it isn't
a warning); a comment that also judges the product counts for that judgement only.

Extraction instructions v14 say so for new extractions (engine/prompts/extract_mentions.md). For the extractions made
before, this module helps a person do it by hand, in two steps:

1. candidates: the warnings (product mentions and "what to look for" notes with stance warn) whose quote or comment
   holds a word of an ethics keyword family (FAMILIES: animal welfare, ethics, labour, boycotts, politics and owners,
   the environment). Keywords only find candidates: most are about the product ("parts and labour are costly", "made
   cheaply since it was bought out"), so each is judged from its quote and its comment. Only ids, names and the
   families found are printed, never anyone's words.
2. apply: the decisions, a JSON list of ids and names (Decision): "remove" an ethics-only item; "requote" a mixed one,
   so it keeps its judgement of the product with its own quote (and, when the judgement left is the other way, its
   stance: "it worked wonders, but I quit buying from them over the founder's views" is a recommendation). Every
   requote is checked as an extraction is (engine.extract.check_extraction: word for word, at most 50 words); a thread
   any of whose decisions can't be applied is left as it was, with the reasons. A slimmed thread keeps whole only the
   comments answers use (Noemi's "Keep only comments we use", 13 Oct 2026; engine/slim.py), so a comment left with
   nothing to use keeps only its shape, as one not verified in time does (engine.verify): no words, no writer, the
   product types it named kept for module 2. The extraction's version and date stay, so a slimmed thread's stamp still
   matches, and each file keeps its layout.

Files changed at or after a time are only listed (candidates: marked newer; apply: left_for_later): on 15 Oct 2026
three extractors, told the rule that night, were still publishing new files, which wait until their lists finish.

    python -m engine.ethics candidates [--since ISO-TIME] [--library DIR]
    python -m engine.ethics apply DECISIONS.json [--write] [--before ISO-TIME] [--library DIR]
"""

import argparse
import copy
import json
import re
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from engine.extract import Extraction, check_extraction, extraction_bytes
from engine.library import DEFAULT_LIBRARY_DIR
from engine.models import Thread
from engine.slim import kept_comment_ids, known_types, thread_json, write_file

# The keyword families (chosen by Claude, 15 Oct 2026, from Noemi's examples and a reading of the library's warnings):
# lowercase regular expressions, found anywhere in a warning's quote or its comment's words.
FAMILIES: dict[str, str] = {
    "animal": r"\banimals?\b|cruelty|animal[- ]?test|test(?:s|ed|ing)? on animals|\bvegan\b|\bfur\b|plucked|"
              r"\bgoose down\b|\bduck down\b|\bmules(?:ing|ed)\b",
    "ethics": r"\bethic|\bunethical|\bimmoral|\bmorals?\b|\bmorally\b|\bscumm?y\b|\bshady\b",
    "labour": r"\blabou?r\b|sweatshop|\bworkers?\b|\bemployees?\b|\bwages?\b|\bslave|\bunions?\b|union[- ]?bust|"
              r"uyghur|xinjiang|exploit",
    "boycott": r"boycott|won'?t support|(?:don'?t|refuse to|stopped|stop|never|quit) (?:supporting|support|buying from|"
               r"buy from|giving)|\bvote with (?:my|your|our) wallet|\bgive (?:them|him|her) (?:my|any|a penny|a cent)",
    "politics": r"\bpolitic|\bceo\b|\bfounders?\b|\bowners?\b|owned by|\bdonat|\btrump\b|\bmaga\b|\bnazi|\bracis|"
                r"homophob|transphob|\bisrael|\bpalestin|\bgaza\b|\brussia|\bnestl[eé]|\bscandal|controvers|"
                r"\bbillionaire|\bconservative\b|\bliberal\b|\bwoke\b|\bmonopol",
    "environment": r"greenwash|sustainab|\benvironment|palm oil|\bplanet\b|carbon footprint",
}
_FAMILIES = {name: re.compile(pattern) for name, pattern in FAMILIES.items()}
_KINDS = {"mention": ("mentions", "product"), "note": ("notes", "about")}  # kind -> (the file's list, its name field)


@dataclass(frozen=True)
class Candidate:
    """A warning to judge: ids, its name and the keyword families found, never its words."""

    thread_id: str
    comment_id: str
    kind: str  # "mention" or "note"
    name: str  # the product, or what the note is about
    families: tuple[str, ...]  # in FAMILIES' order
    in_quote: bool  # a keyword in the quote itself, not only elsewhere in the comment
    newer: bool  # its extraction file changed at or after `since`


def candidates(library_dir: Path = DEFAULT_LIBRARY_DIR, since: datetime | None = None) -> list[Candidate]:
    """Every warning of the library's extractions whose quote or comment holds an ethics keyword (see the module's
    docstring), in file order. `since` (local time) marks those in files changed at or after it as newer."""
    library_dir, found = Path(library_dir), []
    cutoff = since.timestamp() if since is not None else None
    for path in sorted((library_dir / "extracted").glob("*.json")):
        thread_path = library_dir / "threads" / path.name
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            thread = json.loads(thread_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        bodies = {c.get("id"): c.get("body") or "" for c in thread.get("comments", []) if isinstance(c, dict)}
        newer = cutoff is not None and path.stat().st_mtime >= cutoff
        for kind, (field_name, name_field) in _KINDS.items():
            for item in data.get(field_name) or []:
                if not isinstance(item, dict) or item.get("stance") != "warn":
                    continue
                quote = str(item.get("quote") or "").lower()
                words = quote + "\n" + str(bodies.get(item.get("comment_id"), "")).lower()
                families = tuple(name for name, pattern in _FAMILIES.items() if pattern.search(words))
                if families:
                    found.append(Candidate(str(data.get("thread_id", path.stem)), str(item.get("comment_id")), kind,
                                           str(item.get(name_field)), families,
                                           any(_FAMILIES[name].search(quote) for name in families), newer))
    return found


@dataclass(frozen=True)
class Decision:
    """What to do with one warning, by ids and its name. "remove": it rests only on the maker's ethics. "requote": the
    comment also judges the product, so it keeps that judgement with its own `quote` (copied word for word from the
    comment), and the `stance`, `evidence` and `evidence_tags` given (None: as they were)."""

    thread_id: str
    comment_id: str
    kind: str  # "mention" or "note"
    name: str  # the product, or what the note is about, exactly as the extraction has it
    action: str  # "remove" or "requote"
    quote: str | None = None
    stance: str | None = None
    evidence: str | None = None
    evidence_tags: tuple[str, ...] | None = None

    @property
    def key(self) -> str:
        return f"{self.thread_id} {self.comment_id} {self.kind} [{self.name}]"


def load_decisions(path: Path) -> list[Decision]:
    """The decisions in a JSON file: a list of objects with Decision's fields."""
    decisions = []
    for entry in json.loads(Path(path).read_text(encoding="utf-8")):
        tags = entry.get("evidence_tags")
        decisions.append(Decision(entry["thread_id"], entry["comment_id"], entry["kind"], entry["name"],
                                  entry["action"], entry.get("quote"), entry.get("stance"), entry.get("evidence"),
                                  tuple(tags) if tags is not None else None))
    return decisions


@dataclass
class ApplyResult:
    """What a run did (a dry run: would do), in ids and names only."""

    removed: list[Decision] = field(default_factory=list)
    requoted: list[Decision] = field(default_factory=list)
    stubbed: list[tuple[str, str]] = field(default_factory=list)  # (thread id, comment id): words gone, nothing used
    left_for_later: list[Decision] = field(default_factory=list)  # in files changed at or after `before`
    refused: dict[str, str] = field(default_factory=dict)  # Decision.key -> why; its thread is left as it was
    dry_run: bool = True


def apply(library_dir: Path, decisions: Iterable[Decision], write: bool = False,
          before: datetime | None = None) -> ApplyResult:
    """Applies the decisions to the library's extractions, a thread at a time (see the module's docstring). With
    `write` False (the default) nothing is written. A thread's extraction changed at or after `before` (local time) is
    left alone and its decisions listed in left_for_later. The thread file is written first, then the extraction."""
    library_dir, result = Path(library_dir), ApplyResult(dry_run=not write)
    cutoff = before.timestamp() if before is not None else None
    by_thread: dict[str, list[Decision]] = {}
    for decision in decisions:
        by_thread.setdefault(decision.thread_id, []).append(decision)
    types = None  # known_types, worked out once there is a comment to stub
    for thread_id, theirs in by_thread.items():
        path, thread_path = library_dir / "extracted" / f"{thread_id}.json", library_dir / "threads" / f"{thread_id}.json"
        if not path.is_file() or not thread_path.is_file():
            _refuse(result, theirs, {d.key: "no such thread or extraction file" for d in theirs})
            continue
        if cutoff is not None and path.stat().st_mtime >= cutoff:
            result.left_for_later.extend(theirs)
            continue
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        thread = Thread.model_validate_json(thread_path.read_bytes())
        new, problems = _decided(data, theirs)
        if not problems:
            problems = _checked(new, thread, theirs)
        if problems:
            _refuse(result, theirs, problems)
            continue
        lost = set()
        if thread.slimmed:
            lost = kept_comment_ids(thread, Extraction.model_validate(data)) - kept_comment_ids(
                thread, Extraction.model_validate(new))
        new_thread = None
        if lost:
            from engine.verify import _applied  # here: engine.verify builds on engine.slim, as this module does

            types = known_types(library_dir) if types is None else types
            new_thread, new, _ = _applied(thread, new, {}, {comment_id: "not used" for comment_id in lost}, types)
        result.removed += [d for d in theirs if d.action == "remove"]
        result.requoted += [d for d in theirs if d.action == "requote"]
        result.stubbed += [(thread_id, comment_id) for comment_id in sorted(lost)]
        if write:
            if new_thread is not None:
                write_file(thread_path, thread_json(new_thread))
            write_file(path, extraction_bytes(new, like=text))
    return result


def _decided(data: dict, decisions: list[Decision]) -> tuple[dict, dict[str, str]]:
    """The extraction's data with the decisions carried out, and the problems ({Decision.key: why})."""
    new, problems = copy.deepcopy(data), {}
    for decision in decisions:
        if decision.kind not in _KINDS or decision.action not in ("remove", "requote"):
            problems[decision.key] = f"unknown kind or action ({decision.kind}, {decision.action})"
            continue
        field_name, name_field = _KINDS[decision.kind]
        items = new.get(field_name) or []
        matching = [item for item in items if isinstance(item, dict) and item.get("comment_id") == decision.comment_id
                    and item.get(name_field) == decision.name]
        if not matching:
            problems[decision.key] = "no such item in the extraction"
        elif decision.action == "remove":
            new[field_name] = [item for item in items if not any(item is m for m in matching)]
        elif not decision.quote:
            problems[decision.key] = "a requote needs its quote"
        else:
            for item in matching:
                item["quote"] = decision.quote
                for name in ("stance", "evidence"):
                    if getattr(decision, name) is not None:
                        item[name] = getattr(decision, name)
                if decision.evidence_tags is not None:
                    item["evidence_tags"] = list(decision.evidence_tags)
    return new, problems


def _checked(new: dict, thread: Thread, decisions: list[Decision]) -> dict[str, str]:
    """The problems of the new extraction: it must load, and every requoted item pass the extraction's checks."""
    try:
        extraction = Extraction.model_validate(new)
    except ValidationError as e:
        return {d.key: f"the extraction wouldn't load ({e.error_count()} problem(s))" for d in decisions}
    checked = check_extraction(extraction, thread)
    rejected = [(item, why) for item, why in checked.rejected + checked.rejected_notes]
    problems = {}
    for decision in decisions:
        if decision.action != "requote":
            continue
        name_field = _KINDS[decision.kind][1]
        for item, why in rejected:
            if item.comment_id == decision.comment_id and getattr(item, name_field) == decision.name:
                problems[decision.key] = ("its new quote isn't word for word in its comment" if "word for word" in why
                                          else f"its new quote fails the extraction's check: {why}")
    return problems


def _refuse(result: ApplyResult, decisions: list[Decision], problems: dict[str, str]) -> None:
    for decision in decisions:
        result.refused[decision.key] = problems.get(
            decision.key, "left as it was: another decision for its thread can't be applied")


def report(result: ApplyResult) -> str:
    """The run in lines: counts, then each decision by ids and name; never a quote."""
    verb = "Would apply" if result.dry_run else "Applied"
    lines = [f"{verb}: {len(result.removed)} removed, {len(result.requoted)} requoted, {len(result.stubbed)} comment(s) "
             f"left with nothing to use reduced to their shape" + (" (dry run: nothing written)." if result.dry_run
                                                                  else ".")]
    lines += [f"  removed  {d.key}" for d in result.removed] + [f"  requoted {d.key}" for d in result.requoted]
    lines += [f"  stubbed  {thread_id} {comment_id}" for thread_id, comment_id in result.stubbed]
    lines += [f"  left for later (changed since the cutoff) {d.key}" for d in result.left_for_later]
    lines += [f"  refused  {key}: {why}" for key, why in result.refused.items()]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m engine.ethics", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    find = sub.add_parser("candidates", help="list warnings with ethics keywords (ids, names, families)")
    find.add_argument("--since", type=datetime.fromisoformat, default=None,
                      help="mark candidates in files changed at or after this local time (ISO) as newer")
    find.add_argument("--library", type=Path, default=DEFAULT_LIBRARY_DIR)
    run = sub.add_parser("apply", help="apply a JSON list of decisions")
    run.add_argument("decisions", type=Path)
    run.add_argument("--write", action="store_true", help="write the changes (without it: a dry run)")
    run.add_argument("--before", type=datetime.fromisoformat, default=None,
                     help="leave alone files changed at or after this local time (ISO)")
    run.add_argument("--library", type=Path, default=DEFAULT_LIBRARY_DIR)
    args = parser.parse_args(argv)
    if args.command == "candidates":
        found = candidates(args.library, args.since)
        newer = sum(c.newer for c in found)
        print(f"{len(found)} warning(s) with ethics keywords to judge"
              + (f", {newer} in files changed since {args.since.isoformat()}" if args.since else "") + ":")
        for c in found:
            print(f"  {c.thread_id} {c.comment_id} {c.kind} [{c.name}] families={','.join(c.families)}"
                  f"{' in-quote' if c.in_quote else ''}{' NEWER' if c.newer else ''}")
        return 0
    result = apply(args.library, load_decisions(args.decisions), write=args.write, before=args.before)
    print(report(result))
    return 1 if result.refused else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
