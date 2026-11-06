"""Lip tints and brow gels (Noemi's "Split both (Recommended)", 5 Nov 2026): two makeup types of their own.

Why. Asked "Lip tint is filed under lipstick and brow gel under brow pencil, so those requests get the wrong products.
Should I give them their own types?", Noemi said "Split both (Recommended)". Module 1 now has a "lip tint" type (tints
and stains, out of lipstick) and a "brow gel" type (gels, soaps, waxes and glues, out of brow pencil):
engine/data/product_types.json. Extraction instructions v17 type them so (engine/prompts/extract_mentions.md); the
library's extractions were made before (the 17 files with tints or gels, under v15), when every tint was a "lipstick"
and every brow product a "brow pencil", so a lip tint answer would have left all of them out as another type. This
module re-types those mentions, as engine/lip_balms.py re-typed the SPF lip balms on 15 Oct 2026.

Which mentions (retype), judged by the mention's own name and its thread's title, never by its quote:
- A mention typed "lipstick" is a lip tint when its name says it is a tint or a stain ("Peripera Ink Mood Glowy Tint",
  "Milani Color Fetish Hydrating Lip Stain") or names a line that sells only tints and stains (TINT_LINES: Benefit's
  Benetint, Peripera's Ink tints, Tony Moly's Shocking Lip, Fenty's Poutsicle), unless it also says lipstick or crayon
  ("Colourpop Just A Tint Lip Crayon" stays a lipstick); or when its thread asks for lip tints (its title names a lip
  tint and no lipstick, as module 2 reads titles) and the writer named the maker alone ("Etude"): there it is the
  maker's tint. Not every other name of such a thread: they also name lipsticks, balms and glosses by their lines,
  which the AI typed rightly ("Kate Lip Monster" is a lipstick).
- A mention typed "brow pencil" is a brow gel when its name names no pencil form (a pencil, pen, pomade, powder,
  paste, Brow Wiz, Dipbrow, a micro or slim pencil, a styler: PENCIL_NAMES) and either says it is a gel, soap, wax,
  glue, setter, laminator, freeze or clear mascara, or names a gel's line (GEL_LINES: Glossier Boy Brow, Benefit Gimme
  Brow, e.l.f. Brow Lift...), or sits in a thread asking for brow gels (its title names a brow gel and no brow pencil):
  in those threads the writers name their gel by its maker alone ("Benefit", "Kosas") or as a hair gel they use on
  their brows ("Got2b"), and a pencil named there says so ("Rare Beauty brow pencil" stays a pencil).
Only the mention's product_type changes ("lip tint", "brow gel"); every other field, the file's instructions version
and its date stay (a slimmed thread's stamp, engine/slim.py, still matches), and the file keeps its layout. Each file
is written whole under another name, then swapped in; one another process changes meanwhile is left alone.

    python -m engine.makeup_types retype [--write] [--library DIR]

It prints thread ids, comment ids and product names only, never a quote. Without --write it is a dry run.
"""

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from engine.extract import extraction_bytes
from engine.library import DEFAULT_LIBRARY_DIR
from engine.slim import write_file
from engine.sources import mentions_product

LIPSTICK, LIP_TINT = "lipstick", "lip tint"
BROW_PENCIL, BROW_GEL = "brow pencil", "brow gel"

# A name saying it is a tint or a stain, or naming a line that sells only those (chosen by Claude, 5 Nov 2026, from the
# library's names typed lipstick): Benefit's Benetint, Peripera's Ink tints (Ink Mood, Ink Velvet...), Tony Moly's
# Shocking Lip, Fenty's Poutsicle.
TINT_LINES = ("benetint", "peripera ink", "shocking lip", "shocking lips", "poutsicle")
_TINT = re.compile(r"\b(?:tints?|stains?)\b|\b(?:" + "|".join(re.escape(line) for line in TINT_LINES) + r")\b")
_LIPSTICK = re.compile(r"\blipsticks?\b|\bcrayons?\b")
# A name saying it is a gel, a soap, a wax, a glue, a setter, a laminator, a freeze or a clear mascara, or naming a
# gel's line (chosen by Claude, 5 Nov 2026, from the library's names typed brow pencil).
GEL_LINES = ("boy brow", "gimme brow", "brow lift", "wow brow", "air brow", "brow 1980", "big bush brow",
             "control freak", "thick it stick it", "super lock", "super fluff", "make me brow")
_GEL = re.compile(r"\b(?:gels?|glues?|soaps?|wax|setter|laminat\w*|mascara|freeze)\b|\b(?:"
                  + "|".join(re.escape(line) for line in GEL_LINES) + r")\b")
# A name naming a pencil form: a pencil or pen, a pomade, powder or paste, Anastasia's Brow Wiz and Dipbrow, a micro or
# slim pencil, a styler (Dior's and MAC's pencils), Charlotte Tilbury's Brow Cheat, Benefit's Precisely My Brow and Goof
# Proof, a crayon, a fine liner, a razor or blade pencil, Shu Uemura's hard formula.
PENCIL_NAMES = ("pencils?", "pens?", "pomade", "powder", "powdery", "paste", "wiz", "whiz", "definer", r"micro\w*",
                "dip ?brow", "styler", "cheat", "precisely", "goof proof", "crayons?", "multi-tasker", "fine liner",
                "razor", r"slim\w*", "blade", "hard formula")
_PENCIL = re.compile(r"\b(?:" + "|".join(PENCIL_NAMES) + r")\b")


def new_type(product_type: str | None, product: str, title: str = "") -> str | None:
    """The type a mention the AI typed `product_type`, named `product`, in a thread titled `title`, is re-typed as
    ("lip tint" or "brow gel"), or None when it keeps its type (the rules of the module's docstring)."""
    typed = (product_type or "").strip().lower()
    name = " ".join(product.lower().replace("’", "'").split())
    if typed == LIPSTICK:
        if _TINT.search(name) and not _LIPSTICK.search(name):
            return LIP_TINT
        if len(name.split()) == 1 and _asks_for(title, LIP_TINT, LIPSTICK):
            return LIP_TINT
    elif typed == BROW_PENCIL and not _PENCIL.search(name):
        if _GEL.search(name) or _asks_for(title, BROW_GEL, BROW_PENCIL):
            return BROW_GEL
    return None


def _asks_for(title: str, wanted: str, other: str) -> bool:
    """Whether a thread's title asks for the new type: it names it and not the old one, as module 2 reads titles."""
    return bool(title) and mentions_product(title, wanted) and not mentions_product(title, other)


@dataclass(frozen=True)
class Retyped:
    thread_id: str
    comment_id: str
    product: str  # as the writer named it
    product_type: str  # what it is now: "lip tint" or "brow gel"


@dataclass
class RetypeResult:
    """What a run did (a dry run: would do), in ids and names only."""

    retyped: list[Retyped] = field(default_factory=list)
    left_for_later: list[Retyped] = field(default_factory=list)  # in files another process changed meanwhile
    files_changed: list[str] = field(default_factory=list)  # thread ids
    problems: dict[str, str] = field(default_factory=dict)  # file name -> why it wasn't read
    dry_run: bool = True


def retype(library_dir: Path = DEFAULT_LIBRARY_DIR, write: bool = False) -> RetypeResult:
    """Re-types the library's lip tints typed lipstick and brow gels typed brow pencil (the module's docstring). With
    `write` False (the default) it only says what it would change. A file changed by another process while this one was
    at it is left alone, its mentions listed in left_for_later. Each file is written whole, then swapped in."""
    result = RetypeResult(dry_run=not write)
    library_dir = Path(library_dir)
    for path in sorted((library_dir / "extracted").glob("*.json")):
        try:
            stamp = path.stat().st_mtime_ns  # to leave alone a file another process writes meanwhile
            text = path.read_text(encoding="utf-8")
            data = json.loads(text)
            mentions = data["mentions"]
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as e:
            result.problems[path.name] = f"not read ({type(e).__name__})"
            continue
        if not any(isinstance(m, dict) and str(m.get("product_type") or "").strip().lower() in (LIPSTICK, BROW_PENCIL)
                   for m in mentions):
            continue
        thread_id = str(data.get("thread_id", path.stem))
        title = _title(library_dir / "threads" / f"{thread_id}.json")
        places: dict[int, str] = {}
        for i, mention in enumerate(mentions):
            if isinstance(mention, dict) and isinstance(mention.get("product"), str):
                found = new_type(mention.get("product_type"), mention["product"], title)
                if found is not None:
                    places[i] = found
        if not places:
            continue
        changes = [Retyped(thread_id, str(mentions[i].get("comment_id")), str(mentions[i].get("product")), new)
                   for i, new in places.items()]
        for i, new in places.items():
            mentions[i]["product_type"] = new
        if write:
            new_text = _in_place(text, places, data) or extraction_bytes(data, like=text)
            if path.stat().st_mtime_ns != stamp:  # written by another process since it was read: theirs
                result.left_for_later.extend(changes)
                continue
            write_file(path, new_text)
        result.retyped.extend(changes)
        result.files_changed.append(thread_id)
    return result


def _title(path: Path) -> str:
    """A saved thread's title, or "" when it can't be read (its mentions are then judged by their names alone)."""
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("title") or "")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
        return ""


_TYPE_VALUE = re.compile(r'("product_type"\s*:\s*)"(?:[^"\\]|\\.)*"')


def _in_place(text: str, places: dict[int, str], data: dict) -> bytes | None:
    """The file's text with the product type of the mentions at `places` ({place in "mentions": new type}) changed and
    every other character as it was, so hand-laid-out files keep their layout; None when the text can't be changed
    that way and still read as `data` (the caller then writes `data` out whole). As engine.lip_balms._in_place."""
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
                new = places[index]
                changed, count = _TYPE_VALUE.subn(lambda m: m.group(1) + json.dumps(new), text[pos:end])
                if count != 1:
                    return None
                pieces += [text[last:pos], changed]
                last = end
            pos, index = end, index + 1
    except (IndexError, ValueError):
        return None
    new_text = "".join(pieces) + text[last:]
    try:
        return new_text.encode("utf-8") if json.loads(new_text) == data else None
    except ValueError:
        return None


def report(result: RetypeResult) -> str:
    """The run in lines: counts, then each change (thread id, comment id, new type, product name); never a quote."""
    verb = "Would re-type" if result.dry_run else "Re-typed"
    counts = {kind: sum(r.product_type == kind for r in result.retyped) for kind in (LIP_TINT, BROW_GEL)}
    lines = [f"{verb} {len(result.retyped)} mention(s) ({counts[LIP_TINT]} lipstick as lip tint, {counts[BROW_GEL]} "
             f"brow pencil as brow gel), in {len(result.files_changed)} extraction file(s)"
             + (" (dry run: nothing written)." if result.dry_run else ".")]
    lines += [f"  {r.thread_id} {r.comment_id} {r.product_type}: {r.product}" for r in result.retyped]
    if result.left_for_later:
        lines.append(f"Left for later (files changed meanwhile): {len(result.left_for_later)} mention(s)")
        lines += [f"  {r.thread_id} {r.comment_id} {r.product_type}: {r.product}" for r in result.left_for_later]
    for name, why in result.problems.items():
        lines.append(f"  not read, {why}: {name}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="python -m engine.makeup_types", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("retype",
                         help="re-type the library's lip tints typed lipstick and brow gels typed brow pencil")
    run.add_argument("--write", action="store_true", help="write the changes (without it: a dry run)")
    run.add_argument("--library", type=Path, default=DEFAULT_LIBRARY_DIR)
    args = parser.parse_args(argv)
    print(report(retype(args.library, write=args.write)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
