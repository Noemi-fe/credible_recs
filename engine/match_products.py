"""Module 4, product matching: tells whether two names, written by different people, mean the same product.

Commenters, Noemi and the AI all write product names their own way: "CeraVe SA", "the CeraVe Renewing SA
Cleanser", "cerave sa cleanser". This file compares two names, using their words and a short list of known short
names (aliases). Module 3's scores use it (engine/extraction_eval.py), to pair the AI's mentions with Noemi's, and
engine/group_products.py uses it to gather every mention of one product across threads. An AI step for the hard
cases, flagged for review, comes later.

How two names are compared. Each is first turned into a list of words (normalize_name): lowercase, HTML codes
turned back into characters ("&amp;" into "&"), accents dropped ("Avène" as "avene"), apostrophes dropped inside
a word ("Paula's" as "paulas"), every other punctuation mark treated as a space, and filler words left out. Then,
when a category's list of known short names is given (product_words), a short name at the start of a name is
written out in full: "TO sunscreen" becomes "the ordinary sunscreen", "Sage" (the UK name) becomes "Breville".
Then two names mean the same product when:
- their words are the same; or
- every word of the shorter name is in the longer one ("cerave sa" in "cerave renewing sa cleanser"), as long as
  the shorter has at least 2 words, or is a single brand-like word (not just a number) that also starts the
  longer name ("zojirushi" and "zojirushi kettle"; but "kettle" alone names a kind of product, not this one);
  except when the longer name adds a word naming another model or version (PRODUCT_VARIANT_WORDS in
  engine/config.py: "Timemore C2" and "Timemore C2 Max", "Dynasty Cream" and "new Dynasty Cream"), or when the
  two names end in different kinds of product ("CeraVe cream" and "CeraVe Cream to Foam cleanser");
- they differ only by small spelling slips, word for word: one letter added, dropped or changed, or two
  neighbouring letters swapped, in words of 5 letters or more that start with the same letter ("zojirushi"
  and "zojurushi", "cosrx" and "corsx"; but "Hario" and "Vario" are two brands); or an "s" added to any word of
  3 or more ("pan" and "pans"). Other short words must match exactly: model names often differ by one letter
  ("V60", "V61").
Before these rules, a word one name writes as one and the other splits in two counts as the same word
("SoonJung" and "Soon Jung", "spf50" and "spf 50").
Anything else is a different product ("cerave hydrating cleanser" and "cerave sa cleanser").

The known short names live in engine/data/product_aliases.json, per category, each with the library names that
show it is needed. A short name is only written out at the start of a name, because some are everyday words:
"TO" is The Ordinary, but "to" in "Cream to Foam" is not.

Known gaps, the edge cases in the brief's End-state tree that rules on words can't settle yet:
- old versus new formula: a reformulated product keeps its name, so the two look identical here, unless a name
  says "new" or "old";
- sizes and variants: "Lodge skillet" matches "Lodge 12 inch skillet", so every size of a product would merge
  under its shorter name, while two sizes written out in full ("10 inch", "12 inch") stay apart. Grouping
  (engine/group_products.py) keeps a shorter name that fits two sizes apart from both;
- US versus EU names: only the ones on the list of known short names ("Sage" for Breville);
- brand versus product line: a brand alone ("CeraVe") matches any of its products, and a loose name ("CeraVe
  cleanser") matches each of the brand's cleansers. Grouping keeps such names apart when they fit more than one
  product;
- one description written two ways ("Professional Fillet Knife 7 Les Forges 1890" and "Opinel Les Forges 1890 7
  Fillet Knife"): a rule for "most words shared" was tried on 9 Oct 2026 and dropped, because in the library it
  merged far more different products ("Round Lab Birch Juice Pads" and "... cream") than renamed ones;
- a spelling slip and an extra word together ("Kikumasamume Sake Skin Care Cream" and "Kikumasamune Sake cream");
- a model word that says what the product is not ("1zpresso JX (non pro)"), or a model word that is the product's
  own name ("Hario slim" is the "Hario Mini-Slim"): both are read as another model;
- a brand alone doesn't match its models that add a model word either ("Hario" and "Hario Skerton Pro"),
  because words can't tell a brand ("Hario") from a product ("Aeropress", whose "Aeropress Go" is another one).
Also: a filler word that really is part of a name ("One" in a product called "One") is dropped too; a typo is
only forgiven when the two names have the same number of words, so "Zojurushi" doesn't match "Zojirushi kettle".
"""

import html
import json
import re
import unicodedata
from functools import cache
from pathlib import Path

from engine.config import MENTION_CATEGORIES, PRODUCT_VARIANT_WORDS
from engine.text import one_edit_apart

DEFAULT_ALIASES = Path(__file__).resolve().parent / "data" / "product_aliases.json"

# Dropped from the start of a name only: "a" inside a name is often part of it ("Vitamin A serum").
LEADING_WORDS = ("the", "a", "my")
# Dropped anywhere: words people add around a name that aren't part of it ("the Victorinox one", "Le Creuset brand",
# "peeling solution by the ordinary"; "by" and "from" added 9 Oct 2026).
FILLER_WORDS = frozenset({"one", "ones", "brand", "the", "my", "their", "by", "from"})
# A one-letter typo, or two swapped letters, is only forgiven in words at least this long.
TYPO_MIN_LENGTH = 5
# A plural "s" is forgiven on words at least this long ("pan" and "pans"; but "K" and "Ks" stay apart).
PLURAL_MIN_LENGTH = 3
# At most this many words written apart can make one word written as one ("J", "Max" and "JMax").
MAX_WORDS_JOINED = 3
# Words naming a kind of product. Two names that each end in one of these, but not the same one, are different
# products, even when one is found inside the other: "CeraVe cream" and "CeraVe Cream to Foam cleanser".
PRODUCT_TYPE_WORDS = frozenset({
    "cream", "cleanser", "serum", "toner", "lotion", "sunscreen", "sunblock", "essence", "ampoule", "mask", "oil",
    "balm", "gel", "milk", "mist", "pad", "pads", "foam", "wash", "moisturizer", "moisturiser", "ointment", "powder",
    "soap", "scrub", "spray", "peel",
    "pan", "skillet", "kettle", "grinder", "knife", "pot", "lid", "oven", "scale", "burrs",
})

_APOSTROPHES = re.compile(r"['’‘`]")
_WORD = re.compile(r"[^\W_]+")  # a run of letters and digits

# Known short names of one category: the short name's words -> the full name's words.
Aliases = dict[tuple[str, ...], list[str]]
NO_ALIASES: Aliases = {}


class AliasError(Exception):
    pass


def normalize_name(name: str) -> list[str]:
    """The words of a product name, in a form that compares cleanly: "The Paula's Choice 2% BHA" -> paulas choice 2 bha."""
    words = plain_words(name)
    while words and words[0] in LEADING_WORDS:
        words.pop(0)
    return [word for word in words if word not in FILLER_WORDS]


def plain_words(text: str) -> list[str]:
    """Every word of a text, lowercase, without accents or punctuation, and with no word left out."""
    text = html.unescape(text)
    # Split accented letters into the letter and its accent, then drop the accent.
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    return _WORD.findall(_APOSTROPHES.sub("", text.lower()))


def product_words(name: str, aliases: Aliases = NO_ALIASES) -> list[str]:
    """The words of a name (normalize_name), with a known short name at its start written out in full."""
    return spell_out(normalize_name(name), aliases)


def spell_out(words: list[str], aliases: Aliases) -> list[str]:
    """Writes out a known short name at the start of a name: "to sunscreen" -> ordinary sunscreen.

    The longest short name that fits is used. A name that already holds every word of the full name ("Timemore
    C2", for the model "C2") is left as it is.
    """
    for short in sorted(aliases, key=len, reverse=True):
        if tuple(words[:len(short)]) == short:
            full = aliases[short]
            if set(full) <= set(join_split_words(words, full)):  # "elta md" already says "eltamd"
                return words
            return full + words[len(short):]
    return words


def same_product(a: str, b: str, aliases: Aliases = NO_ALIASES) -> bool:
    """Whether two names mean the same product, by the rules at the top of this file.

    `aliases` is one category's list of known short names (load_aliases()["skincare"]); without it, names are
    compared on their own words only.
    """
    return same_words(product_words(a, aliases), product_words(b, aliases))


def same_words(words_a: list[str], words_b: list[str]) -> bool:
    """same_product on names already turned into words (product_words)."""
    if not words_a or not words_b:
        return False  # a name made only of filler words ("the one") names nothing
    words_a = join_split_words(words_a, words_b)
    words_b = join_split_words(words_b, words_a)
    if words_a == words_b:
        return True
    return _found_inside(words_a, words_b) or _only_typos_apart(words_a, words_b)


def join_split_words(words: list[str], other: list[str]) -> list[str]:
    """`words`, with any run of neighbouring words that the other name writes as one word joined into it.

    "tir tir milk" against "tirtir milk" gives tirtir milk. Runs of up to MAX_WORDS_JOINED words are tried,
    the longest first.
    """
    targets = set(other)
    joined, i = [], 0
    while i < len(words):
        for size in range(min(MAX_WORDS_JOINED, len(words) - i), 1, -1):
            if "".join(words[i:i + size]) in targets:
                joined.append("".join(words[i:i + size]))
                i += size
                break
        else:
            joined.append(words[i])
            i += 1
    return joined


def _found_inside(words_a: list[str], words_b: list[str]) -> bool:
    """Whether every word of the shorter name is in the longer one, the shorter says enough to be a name, and the
    longer doesn't add a word naming another model or version."""
    shorter, longer = sorted((words_a, words_b), key=len)
    if len(shorter) == 1 and shorter[0].isalpha() and longer[0] == shorter[0] + "s":
        longer = shorter + longer[1:]  # a brand and its possessive: "FAB" and "FAB's exfoliating pads" (9 Oct 2026)
    if not set(shorter) <= set(longer):
        return False
    if (set(longer) - set(shorter)) & PRODUCT_VARIANT_WORDS:
        return False
    if _different_types(shorter[-1], longer[-1]):
        return False
    if len(shorter) >= 2:
        return True
    return _brand_like(shorter[0]) and longer[0] == shorter[0]


def _different_types(last_a: str, last_b: str) -> bool:
    """Whether two last words name two different kinds of product ("cream" and "cleanser"; not "pan" and "pans")."""
    return (last_a in PRODUCT_TYPE_WORDS and last_b in PRODUCT_TYPE_WORDS
            and last_a != last_b and not _spelling_slip(last_a, last_b))


def _brand_like(word: str) -> bool:
    """A single word could be a brand if it has a letter: "zojirushi" could, "10" (a size) can't."""
    return any(ch.isalpha() for ch in word)


def _only_typos_apart(words_a: list[str], words_b: list[str]) -> bool:
    """Whether the names have the same words in the same order, except small spelling slips."""
    if len(words_a) != len(words_b):
        return False
    return all(x == y or _spelling_slip(x, y) for x, y in zip(words_a, words_b))


def _spelling_slip(x: str, y: str) -> bool:
    """Whether two different words are one word misspelled: a plural "s", or a slip in a long word that keeps its
    first letter."""
    shorter, longer = sorted((x, y), key=len)
    if longer == shorter + "s" and len(shorter) >= PLURAL_MIN_LENGTH:
        return True
    if len(shorter) < TYPO_MIN_LENGTH or x[0] != y[0]:
        return False
    return one_edit_apart(x, y) or _neighbours_swapped(x, y)


def _neighbours_swapped(x: str, y: str) -> bool:
    """True if swapping two neighbouring letters turns x into y ("cosrx" and "corsx")."""
    if len(x) != len(y):
        return False
    differ = [i for i, (p, q) in enumerate(zip(x, y)) if p != q]
    return len(differ) == 2 and differ[1] == differ[0] + 1 and x[differ[0]] == y[differ[1]] and x[differ[1]] == y[differ[0]]


# --- The list of known short names ---

def make_aliases(pairs: dict[str, str]) -> Aliases:
    """A list of known short names from {short name: full name} as written: {"TO": "The Ordinary"}."""
    return _build_aliases(list(pairs.items()))


def _build_aliases(pairs: list[tuple[str, str]]) -> Aliases:
    aliases: Aliases = {}
    for short, full in pairs:
        short_words, full_words = normalize_name(short), normalize_name(full)
        if not short_words or not full_words:
            raise AliasError(f"{short!r} -> {full!r}: both names need a word that isn't filler")
        if tuple(short_words) in aliases:
            raise AliasError(f"the short name {' '.join(short_words)!r} is listed twice")
        aliases[tuple(short_words)] = full_words
    return aliases


def load_aliases(path: Path = DEFAULT_ALIASES, section: str = "products") -> dict[str, Aliases]:
    """The known short names of every category ({category: Aliases}), read from the alias file.

    `section` is "products" for product names, or "kinds" for kinds of product (engine/group_kinds.py). A
    category with no entry gets an empty list. A malformed file raises AliasError, naming the problem.
    """
    try:
        listed = json.loads(Path(path).read_text(encoding="utf-8")).get(section, {})
        unknown = sorted(set(listed) - set(MENTION_CATEGORIES))
        if unknown:
            raise AliasError(f"unknown categories: {', '.join(unknown)}")
        return {
            category: _build_aliases([(entry["short"], entry["full"]) for entry in listed.get(category, [])])
            for category in MENTION_CATEGORIES
        }
    except (OSError, json.JSONDecodeError, AttributeError, KeyError, TypeError, AliasError) as e:
        raise AliasError(f"{path}, {section}: {e}") from e


@cache
def known_aliases(section: str = "products") -> dict[str, Aliases]:
    """The shipped alias file (engine/data/product_aliases.json), read once."""
    return load_aliases(DEFAULT_ALIASES, section)
