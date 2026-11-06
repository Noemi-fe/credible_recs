"""Product notes (5 Nov 2026, the makeup fix round, part 2; Claude's technical calls, reported to Noemi): a checked fact a
reader needs beside a product's quotes, shown as one of its notes ("Note: ...", engine.answer.CAUTION).

Why: the shopper review of 4-5 Nov 2026 found three makeup products whose quotes read wrongly without a fact the threads
only hint at. NARS reformulated its powder blushes in 2024, and the same answer's Skip these warns about the new formula,
so a pick praising years of the old one needs to say so. Becca closed in 2021, so a highlighter praised as Becca's needs
to say who makes it now. And a hair styling gel some writers use on their brows was shown as a brow gel with no word
about what it is. Noemi kept all three on 6 Nov 2026, with two decisions beside them: a hair product is never a pick in
a face-makeup answer (it may still be listed under Also worth a look, with its note), and a "(new formula)" item's
warnings are the product's own downsides, not a Skip item of their own (engine.pipeline).

A note is only a fact checked on a reliable public page, or the threads' own words (a hair gel some writers use on their
brows), and names its sources; it never changes which products are shown or their order (a product no longer sold is
left out by its price check, data/prices.json's "available": false, never by a note). Notes aren't Reddit data, so the
list, data/product_notes.json, is committed with the code. Its format:

    {"product_notes": [{"names": ["NARS Orgasm"],          the product's names as an answer shows them: a product
                                                           whose shown name holds every word of one of these (in
                                                           any order, any case) gets the note
                        "category": "general",             the answers' category it applies in: general for makeup
                        "note": "NARS reformulated ...",   the note as shown, without "Note: " and the full stop
                        "sources": ["https://..."],        the pages it was checked on (https), or "threads" for a
                                                           note in the threads' own words, with their ids in
                                                           "threads"
                        "threads": ["17exp4y"],            optional: the threads whose comments say it
                        "checked_on": "2026-11-05"}]}      the day it was checked
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from engine.memo import FileMemo

DEFAULT_PRODUCT_NOTES = Path(__file__).resolve().parents[1] / "data" / "product_notes.json"


class ProductNotesError(ValueError):
    """The notes list is missing, malformed, or has an entry without what it needs."""


@dataclass(frozen=True)
class ProductNote:
    names: tuple[str, ...]
    category: str
    note: str
    sources: tuple[str, ...]
    checked_on: str
    threads: tuple[str, ...] = ()


def load_product_notes(path: Path = DEFAULT_PRODUCT_NOTES) -> list[ProductNote]:
    """Every note of the list; a missing file is an empty list (no product has a note), a malformed one raises
    ProductNotesError naming the entry. Read once while the file is unchanged (engine.memo)."""
    if not Path(path).exists():
        return []
    return _LOADED.get(Path(path), _read)


_LOADED = FileMemo()
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def _read(path: Path) -> list[ProductNote]:
    try:
        entries = json.loads(Path(path).read_text(encoding="utf-8"))["product_notes"]
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as e:
        raise ProductNotesError(f"{path}: not a product notes list ({e})") from e
    notes = []
    for number, entry in enumerate(entries, start=1):
        try:
            note = ProductNote(names=tuple(entry["names"]), category=entry["category"], note=entry["note"].strip(),
                               sources=tuple(entry["sources"]), checked_on=entry["checked_on"],
                               threads=tuple(entry.get("threads", ())))
        except (KeyError, TypeError, AttributeError) as e:
            raise ProductNotesError(f"{path}, entry {number}: missing or wrong field ({e})") from e
        problem = (not note.names and "no names" or not note.note and "no note"
                   or note.note.endswith(".") and "the note ends with a full stop (the answer adds it)"
                   or not note.sources and "no sources"
                   or any(s != "threads" and not s.startswith("https://") for s in note.sources) and "a source isn't https"
                   or "threads" in note.sources and not note.threads and "a note in the threads' words names no thread"
                   or not _DAY.fullmatch(note.checked_on) and "checked_on isn't YYYY-MM-DD")
        if problem:
            raise ProductNotesError(f"{path}, entry {number}: {problem}")
        notes.append(note)
    return notes


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.casefold().replace("&", "")))


def notes_for(name: str, category: str, notes: list[ProductNote]) -> list[str]:
    """The notes of a product shown as `name` in an answer of `category`: those of entries one of whose names has every
    word in it, once each, in the list's order."""
    words = _words(name)
    return list(dict.fromkeys(note.note for note in notes if note.category == category
                              and any(_words(n) and _words(n) <= words for n in note.names)))
