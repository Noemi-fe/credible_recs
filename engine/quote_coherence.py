"""The library's incoherent quotes (Noemi's decision 4 of 15 Oct 2026): a quote shown must be the most significant and
coherent part of its comment for the stance it backs. A recommendation is quoted where the comment recommends (praise,
how long it lasted, how it held up), a warning where it warns. Her example: a TV pick quoted for the 14 years its
writer's last TV of the brand lasted before its picture went out, where the same comment says the writer's current one
is holding up well.

Extraction instructions v15 say so for new extractions (engine/prompts/extract_mentions.md), and module 7 shows a
product's coherent quotes first (engine.answer._naming_first). For the extractions made before, this module helps a
person re-quote them by hand, in two steps:

1. candidates: the mentions whose quote reads against its stance (engine.answer.reads_against_its_stance: a
   recommendation quoted for a failure or a complaint, "reads=failure"; a warning quoted for praise, "reads=praise"),
   and, since the coordinator's trial comparison of 15 Oct 2026, those whose quote is about another product of their
   comment (engine.answer.names_another_product: the comment's other product of another type with the same stance,
   "reads=another product": a cast iron recommendation quoting the writer's carbon steel skillet). Words only find
   candidates: each is judged by reading its comment. Only ids, names and what was found are printed, never anyone's
   words; a mention whose comment kept no words (a slimmed thread's stub) has nothing to re-quote and isn't listed.
2. apply: the decisions, a JSON list of engine.ethics.Decision ("requote", with the new `quote`: an unbroken, word for
   word stretch of the same comment, a part of a sentence if need be, at most 50 words, that carries the stance and
   names or points at the product), applied and checked as engine.ethics.apply does: every requote is checked as an
   extraction is, a thread any of whose decisions can't be applied is left as it was, a file changed by another process
   meanwhile is left to it, and a file changed at or after `--before` is only listed. The mention's stance, evidence and
   tags stay as they were: only its quote changes.

    python -m engine.quote_coherence candidates [--since ISO-TIME] [--library DIR]
    python -m engine.quote_coherence apply DECISIONS.json [--write] [--before ISO-TIME] [--library DIR]
"""

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from engine.answer import names_another_product, reads_against_its_stance
from engine.ethics import apply, load_decisions, report
from engine.extract import Extraction
from engine.library import DEFAULT_LIBRARY_DIR

__all__ = ["Candidate", "apply", "candidates", "main"]


@dataclass(frozen=True)
class Candidate:
    """A quote to judge: ids, its product as written, its stance and what was found, never its words."""

    thread_id: str
    comment_id: str
    name: str  # the product, exactly as the extraction has it
    stance: str  # "recommend" or "warn"
    reads: str  # "failure", "praise" or "another product"
    newer: bool  # its extraction file changed at or after `since`


def candidates(library_dir: Path = DEFAULT_LIBRARY_DIR, since: datetime | None = None) -> list[Candidate]:
    """Every recommendation or warning of the library's extractions whose quote reads against its stance or is about
    another product of its comment (see the module's docstring), in file order. `since` (local time) marks those in
    files changed at or after it as newer."""
    from engine.pipeline import _others_of_another_type  # here: the pipeline is only needed for this

    library_dir, found = Path(library_dir), []
    cutoff = since.timestamp() if since is not None else None
    for path in sorted((library_dir / "extracted").glob("*.json")):
        thread_path = library_dir / "threads" / path.name
        try:
            extraction = Extraction.model_validate(json.loads(path.read_text(encoding="utf-8")))
            thread = json.loads(thread_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValueError, ValidationError):
            continue
        bodies = {c.get("id"): c.get("body") or "" for c in thread.get("comments", []) if isinstance(c, dict)}
        newer = cutoff is not None and path.stat().st_mtime >= cutoff
        for mention in extraction.mentions:
            if mention.stance not in ("recommend", "warn") or not bodies.get(mention.comment_id, "").strip():
                continue
            names = (mention.product,)
            if reads_against_its_stance(mention.quote, mention.stance, names):
                reads = "failure" if mention.stance == "recommend" else "praise"
            elif names_another_product(mention.quote, names, _others_of_another_type(mention, extraction.mentions)):
                reads = "another product"
            else:
                continue
            found.append(Candidate(extraction.thread_id, mention.comment_id, mention.product, mention.stance, reads,
                                   newer))
    return found


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m engine.quote_coherence", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    find = sub.add_parser("candidates", help="list quotes that read against their stance (ids, names, what was found)")
    find.add_argument("--since", type=datetime.fromisoformat, default=None,
                      help="mark candidates in files changed at or after this local time (ISO) as newer")
    find.add_argument("--library", type=Path, default=DEFAULT_LIBRARY_DIR)
    run = sub.add_parser("apply", help="apply a JSON list of requote decisions")
    run.add_argument("decisions", type=Path)
    run.add_argument("--write", action="store_true", help="write the changes (without it: a dry run)")
    run.add_argument("--before", type=datetime.fromisoformat, default=None,
                     help="leave alone files changed at or after this local time (ISO)")
    run.add_argument("--library", type=Path, default=DEFAULT_LIBRARY_DIR)
    args = parser.parse_args(argv)
    if args.command == "candidates":
        found = candidates(args.library, args.since)
        newer = sum(c.newer for c in found)
        print(f"{len(found)} quote(s) reading against their stance or about another product to judge"
              + (f", {newer} in files changed since {args.since.isoformat()}" if args.since else "") + ":")
        for c in found:
            print(f"  {c.thread_id} {c.comment_id} {c.stance} [{c.name}] reads={c.reads}{' NEWER' if c.newer else ''}")
        return 0
    result = apply(args.library, load_decisions(args.decisions), write=args.write, before=args.before)
    print(report(result))
    return 1 if result.refused else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
