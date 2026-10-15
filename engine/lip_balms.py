"""SPF lip balms (Noemi's decision 2 of 15 Oct 2026): a product for the lips with SPF is a lip balm, not a sunscreen.

Why. Lips are an exception to her 9 Oct 2026 rule "sun protection wins over the form". Extraction instructions v6 to
v13 typed anything with SPF as a "sunscreen", so the library's SPF lip balms (about 80 mentions on 15 Oct 2026, most of
them in threads asking for lip balms) counted for sunscreen requests and never for lip balm ones, and "lip balm with
spf" showed lip balms without SPF. Instructions v14 type them as lip balms (engine/prompts/extract_mentions.md); this
module re-types the extractions made before. "With SPF" is then a checked requirement of a lip balm request
(engine/product_facts.py, config "no SPF").

Which mentions (retype): those typed "sunscreen" whose product name is a lip product's (is_lip_product): its words name
the lips ("lip", "lips", "lipbalm", "lipscreen", "lip gloss", "chapstick"), or a maker or line that sells lip care only
(LIP_ONLY_NAMES: "Blistex Deep Renewal"). Judged from the name alone, never from the thread: a face sunscreen stick a
writer uses on their lips stays a sunscreen, and a brand named alone ("Panama Jack") stays as it was typed. Only their
product_type changes ("lip balm"); every other field, the file's instructions version and its date stay (a slimmed
thread's stamp, engine/slim.py, still matches), and the file keeps its layout.

Files changed at or after `before` are listed and left alone (15 Oct 2026: three extractors were still writing v13
files, which type SPF lip balms as sunscreens): run it again once they have finished.

    python -m engine.lip_balms retype [--write] [--before ISO-TIME] [--library DIR]

It prints thread ids, comment ids and product names only, never a quote. Without --write it is a dry run.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from engine.extract import extraction_bytes
from engine.library import DEFAULT_LIBRARY_DIR
from engine.slim import write_file

LIP_TYPE = "lip balm"
SUNSCREEN = "sunscreen"
# A name naming the lips: "lip" or "lips" as a word, the words people write with it joined ("lipbalm", "lipscreen",
# "lipgloss", "lipstick", "lipcare", "lipcream"), and chapsticks. "Lipikar" (a body balm) and "Philip" aren't.
_LIP_WORDS = re.compile(r"\blips?\b|\blip(?:balm|screen|gloss|stick|care|cream|tint)s?\b|\bchap ?sticks?\b")
# Makers and lines that sell lip care only, so their names make a lip product without the word (chosen by Claude, 15 Oct
# 2026, from the library's sunscreen-typed names): Blistex, Carmex, ChapStick, Labello (Nivea's lip care), and
# Mentholatum's Deep Moist lip balms.
LIP_ONLY_NAMES = ("blistex", "carmex", "chapstick", "labello", "mentholatum deep moist", "rohto deep moist")
_LIP_ONLY = re.compile(r"\b(?:" + "|".join(re.escape(name) for name in LIP_ONLY_NAMES) + r")\b")


def is_lip_product(name: str) -> bool:
    """Whether a product's name is a lip product's: it names the lips, or a maker or line selling lip care only."""
    text = name.lower().replace("’", "'")
    return bool(_LIP_WORDS.search(text) or _LIP_ONLY.search(text))


@dataclass(frozen=True)
class Retyped:
    thread_id: str
    comment_id: str
    product: str  # as the writer named it


@dataclass
class RetypeResult:
    """What a run did (a dry run: would do), in ids and names only."""

    retyped: list[Retyped] = field(default_factory=list)
    left_for_later: list[Retyped] = field(default_factory=list)  # in files changed at or after `before`
    files_changed: list[str] = field(default_factory=list)  # thread ids
    problems: dict[str, str] = field(default_factory=dict)  # file name -> why it wasn't read
    dry_run: bool = True


def retype(library_dir: Path = DEFAULT_LIBRARY_DIR, write: bool = False, before: datetime | None = None) -> RetypeResult:
    """Re-types the library's lip products typed sunscreen as lip balms (see the module's docstring). With `write`
    False (the default) it only says what it would change. A file changed at or after `before` (local time), or by
    another process while this one was at it, is left alone, its mentions listed in left_for_later. Each file is
    written whole, then swapped in."""
    result = RetypeResult(dry_run=not write)
    cutoff = before.timestamp() if before is not None else None
    for path in sorted((Path(library_dir) / "extracted").glob("*.json")):
        try:
            stamp = path.stat().st_mtime_ns  # to leave alone a file another process writes meanwhile
            text = path.read_text(encoding="utf-8")
            data = json.loads(text)
            mentions = data["mentions"]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as e:
            result.problems[path.name] = f"not read ({type(e).__name__})"
            continue
        found = [m for m in mentions if isinstance(m, dict) and _to_retype(m)]
        if not found:
            continue
        thread_id = str(data.get("thread_id", path.stem))
        changes = [Retyped(thread_id, str(m.get("comment_id")), str(m.get("product"))) for m in found]
        if cutoff is not None and path.stat().st_mtime >= cutoff:
            result.left_for_later.extend(changes)
            continue
        places = {i for i, m in enumerate(mentions) if any(m is f for f in found)}
        for mention in found:
            mention["product_type"] = LIP_TYPE
        if write:
            new = _in_place(text, places, data) or extraction_bytes(data, like=text)
            if path.stat().st_mtime_ns != stamp:  # written by another process since it was read: theirs
                result.left_for_later.extend(changes)
                continue
            write_file(path, new)
        result.retyped.extend(changes)
        result.files_changed.append(thread_id)
    return result


_TYPE_VALUE = re.compile(r'("product_type"\s*:\s*)"(?:[^"\\]|\\.)*"')


def _in_place(text: str, places: set[int], data: dict) -> bytes | None:
    """The file's text with the product type of the mentions at `places` (their places in "mentions") changed to lip
    balm and every other character as it was, so hand-laid-out files keep their layout; None when the text can't be
    changed that way and still read as `data` (the caller then writes `data` out whole)."""
    decoder, start = json.JSONDecoder(), re.search(r'"mentions"\s*:\s*\[', text)
    if start is None:
        return None
    pieces, last, pos, index = [], 0, start.end(), 0
    try:
        while True:
            pos = re.compile(r"[\s,]*").match(text, pos).end()
            if text[pos] == "]":
                break
            _, end = decoder.raw_decode(text, pos)
            if index in places:
                changed, count = _TYPE_VALUE.subn(lambda m: m.group(1) + json.dumps(LIP_TYPE), text[pos:end])
                if count != 1:
                    return None
                pieces += [text[last:pos], changed]
                last = end
            pos, index = end, index + 1
    except (IndexError, ValueError):
        return None
    new = "".join(pieces) + text[last:]
    try:
        return new.encode("utf-8") if json.loads(new) == data else None
    except ValueError:
        return None


def _to_retype(mention: dict) -> bool:
    """A skincare mention typed sunscreen whose name is a lip product's."""
    product_type = mention.get("product_type")
    return (isinstance(product_type, str) and product_type.strip().lower() == SUNSCREEN
            and mention.get("category") == "skincare" and isinstance(mention.get("product"), str)
            and is_lip_product(mention["product"]))


def report(result: RetypeResult) -> str:
    """The run in lines: counts, then each change (thread id, comment id, product name); never a quote."""
    verb = "Would re-type" if result.dry_run else "Re-typed"
    lines = [f"{verb} {len(result.retyped)} lip product mention(s) typed sunscreen as lip balms, in "
             f"{len(result.files_changed)} extraction file(s)" + (" (dry run: nothing written)." if result.dry_run
                                                                  else ".")]
    lines += [f"  {r.thread_id} {r.comment_id} {r.product}" for r in result.retyped]
    if result.left_for_later:
        lines.append(f"Left for later (files changed since the cutoff): {len(result.left_for_later)} mention(s)")
        lines += [f"  {r.thread_id} {r.comment_id} {r.product}" for r in result.left_for_later]
    for name, why in result.problems.items():
        lines.append(f"  not read, {why}: {name}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m engine.lip_balms", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("retype", help="re-type the library's lip products typed sunscreen as lip balms")
    run.add_argument("--write", action="store_true", help="write the changes (without it: a dry run)")
    run.add_argument("--before", type=datetime.fromisoformat, default=None,
                     help="leave alone files changed at or after this local time (ISO, e.g. 2026-10-15T00:00)")
    run.add_argument("--library", type=Path, default=DEFAULT_LIBRARY_DIR)
    args = parser.parse_args(argv)
    print(report(retype(args.library, write=args.write, before=args.before)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
