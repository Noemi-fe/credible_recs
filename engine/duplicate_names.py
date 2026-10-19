"""The same product twice in one answer: an eval check over the answers a sweep writes (17 Oct 2026, the ws-names
builder; Claude's technical calls, reported to Noemi).

The 16 Oct review of module 4 found answers showing one product twice, as two picks or a pick and an Also worth a look
item: the baby carrier's Ergobaby Embrace (picks 1 and 2), the barbecue's Weber Spirit gas grill beside "Spirit II",
the King 1000/6000 whetstone twice. A tester reads that as a tool that can't tell products apart. Grouping (engine/
group_products.py) is what keeps them apart or together; this check reads the answers it makes, as a shopper sees them.

Each pair of names an answer shows (its picks and Also worth a look; its Skip these apart, as a shopper reads them apart)
is compared on its words: written out with the category's short names (engine/data/product_aliases.json), without the
requested type's words and their synonyms ("carrier", "grill", "whetstone"), without words that say nothing of which
model ("line", "version", "vintage", "new", "set"...), and without the brand at the start. Then a pair is
- "one product twice" (counted): the matcher calls the two names one product (engine.match_products.same_words), or
  they share a word of a model ("embrace", "spirit", "1000") and their brands don't differ: one has none, or both the
  same;
- "a line beside its own product" (shown, not counted): a brand's line ("Greenworks lawn mower line") beside one of its
  products ("Greenworks 80v");
- "two lines of one brand" (shown, not counted): "Dualit Classic toaster line" beside "Dualit 4-slice toaster line";
- "one brand written two ways" (shown, not counted): "1Zpresso" beside "1ZPresso".

    python -m engine.duplicate_names <sweep.jsonl> [more.jsonl...]     the answers with a finding, then the counts

Nothing here reads Reddit or the library; the shipped short names and the brands module 1 knows are read once.
"""

import json
import re
import sys
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from engine.config import PRODUCT_VARIANT_WORDS, TYPE_SYNONYMS
from engine.match_products import known_aliases, normalize_name, product_words, same_words

COUNTED = "one product twice"
LINE_AND_PRODUCT = "a line beside its own product"
TWO_LINES = "two lines of one brand"
BRAND_TWO_WAYS = "one brand written two ways"
# Words that say nothing of which model a name is: what kind of name it is, how old, how bought, how many, and the
# words of a combination ("double sided", "combo": the King 1000/6000 stone).
UNTELLING = frozenset({
    "line", "lines", "series", "range", "version", "versions", "edition", "model", "models", "type", "style", "kind",
    "new", "newer", "newest", "old", "older", "oldest", "vintage", "original", "used", "refurbished", "set", "sets",
    "kit", "pack", "the", "a", "an", "my", "their", "one", "ones", "brand", "product", "products", "and", "or", "with",
    "of", "for", "by", "from", "gen", "generation", "combo", "combination", "double", "sided", "reversible",
})


@dataclass(frozen=True)
class Finding:
    request: str
    kind: str
    names: tuple[str, str]
    places: tuple[str, str]


def shown_names(answer: dict) -> list[tuple[str, str]]:
    """(where, name) of each product an answer shows: its picks, then Also worth a look, then Skip these."""
    shown = [("pick", p["name"]) for p in answer.get("picks") or []]
    shown += [("worth a look", item["name"]) for item in answer.get("worth_a_look") or []]
    shown += [("skip", item["name"]) for item in answer.get("skip") or []]
    return shown


def findings(request: str, answer: dict, brands: Iterable[tuple[str, ...]] | None = None) -> list[Finding]:
    """Every pair of one answer's shown names that is one product twice, a line beside its own product, two lines of
    one brand or one brand written two ways (the module docstring). The skip list is compared with itself only."""
    if not answer:
        return []
    known = _known_brands() if brands is None else frozenset(tuple(b) for b in brands)
    category, product_type = answer.get("category") or "", answer.get("product_type") or ""
    aliases = known_aliases().get(category, {})
    untelling = UNTELLING | _type_words(product_type)
    shown = shown_names(answer)
    found = []
    for i, (place_a, a) in enumerate(shown):
        for place_b, b in shown[i + 1:]:
            if (place_a == "skip") != (place_b == "skip") or a == b:
                continue
            kind = _kind(a, b, aliases, untelling, known)
            if kind is not None:
                found.append(Finding(request, kind, (a, b), (place_a, place_b)))
    return found


def _kind(a: str, b: str, aliases, untelling: frozenset[str], brands: frozenset[tuple[str, ...]]) -> str | None:
    words_a, words_b = product_words(a, aliases), product_words(b, aliases)
    told_a = [w for w in words_a if w not in untelling]
    told_b = [w for w in words_b if w not in untelling]
    if not told_a or not told_b:
        return None
    maker_a, maker_b = _maker(told_a, told_b, brands), _maker(told_b, told_a, brands)
    if maker_a and maker_b and maker_a != maker_b:
        return None  # two makers' products
    maker = maker_a or maker_b
    written = (_written(a, maker), _written(b, maker)) if maker_a and maker_a == maker_b else ("", "")
    two_ways = BRAND_TWO_WAYS if all(written) and written[0] != written[1] else None
    rest_a = [w for w in told_a if w != maker]
    rest_b = [w for w in told_b if w != maker]
    line_a, line_b = _is_line(a), _is_line(b)
    if line_a or line_b:
        if line_a and line_b:
            return TWO_LINES if maker_a and maker_a == maker_b else (COUNTED if set(told_a) == set(told_b) else None)
        line, other = (told_a, told_b) if line_a else (told_b, told_a)
        return LINE_AND_PRODUCT if set(line) <= set(other) else two_ways
    if same_words(words_a, words_b) or _one_model(rest_a, rest_b):
        return COUNTED
    return two_ways


def _one_model(a: list[str], b: list[str]) -> bool:
    """Whether two names' words past their maker name one model: the same words, or one adds a single word that isn't
    a number nor a word of another model ("pro", "max", "mini": config.PRODUCT_VARIANT_WORDS): "Embrace" and "Embrace
    mesh", "Spirit" and "Spirit II", "King KDS 1000/6000" and its "stone"; never "Paperwhite 3" and "Paperwhite 4",
    "JX" and "JX-Pro", "Hydrating Cleanser" and "Hydrating Cream-to-Foam Cleanser"."""
    small, large = sorted((set(a), set(b)), key=len)
    if not small or not small <= large or not any(not w.isdigit() for w in small):
        return False
    added = large - small
    return not added or (len(added) == 1 and not next(iter(added)).isdigit()
                         and next(iter(added)) not in PRODUCT_VARIANT_WORDS)


def _maker(words: list[str], other: list[str], brands: frozenset[tuple[str, ...]]) -> str | None:
    """The word a name's telling words start with as its maker's: a known brand's, or any first word the other name
    doesn't write after its own start ("Embrace" in "Ergobaby Embrace" is a model, not a maker); None when the name
    starts with its model."""
    first = words[0]
    if (first,) in brands or (first not in other[1:] and not first.isdigit()):
        return first
    return None


def _written(name: str, maker: str) -> str:
    """How a name writes its maker's word, its capitals and marks as written ("1ZPresso", "Paula’s"); "" when it doesn't
    write it (a short name wrote it out)."""
    for token in name.split():
        if "".join(re.findall(r"[a-z0-9]+", token.lower().replace("’", "").replace("'", ""))) == maker:
            return token
    return ""


def _is_line(name: str) -> bool:
    return bool(re.search(r"\bline$", name.strip(), re.IGNORECASE))


def _type_words(product_type: str) -> frozenset[str]:
    """The requested type's words, its synonyms' (config.TYPE_SYNONYMS) and its title words' (engine.query.TITLE_WORDS:
    "whetstone", "grill", "smoker"), each with its plural."""
    from engine.query import TITLE_WORDS

    words = set(normalize_name(product_type))
    for other in (*TYPE_SYNONYMS.get(product_type, ()), *TITLE_WORDS.get(product_type, ())):
        words |= set(normalize_name(other))
    return frozenset(words | {w + "s" for w in words} | {w[:-1] for w in words if w.endswith("s")})


def _known_brands() -> frozenset[tuple[str, ...]]:
    from engine.query_model import brand_names

    return brand_names()


def read_sweep(path: Path) -> list[tuple[str, dict]]:
    """(request, answer) of each answered request of a sweep's JSON lines (eval/sweep.py answer)."""
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        answer = (row.get("json") or {}).get("answer")
        if answer:
            rows.append((row["request"], answer))
    return rows


def report(paths: list[Path]) -> tuple[list[str], Counter]:
    lines, counts, answers_with = [], Counter(), set()
    for path in paths:
        for request, answer in read_sweep(path):
            for f in findings(request, answer):
                counts[f.kind] += 1
                if f.kind == COUNTED:
                    answers_with.add(request)
                lines.append(f"{f.kind}: {request!r}: {f.names[0]!r} ({f.places[0]}) / {f.names[1]!r} ({f.places[1]})")
    counts["answers showing one product twice"] = len(answers_with)
    return lines, counts


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    lines, counts = report([Path(p) for p in argv])
    print("\n".join(lines))
    print("\n" + "; ".join(f"{kind}: {n}" for kind, n in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
