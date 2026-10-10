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
Also "non" and the model word after it are dropped: "1zpresso JX (non pro)" is the plain JX (10 Oct 2026).
Then two names mean the same product when:
- their words are the same; or
- every word of the shorter name is in the longer one ("cerave sa" in "cerave renewing sa cleanser"), as long as
  the shorter has at least 2 words, or is a single brand-like word (not just a number) that also starts the
  longer name ("zojirushi" and "zojirushi kettle"; but "kettle" alone names a kind of product, not this one);
  except when the longer name adds a word naming another model or version (PRODUCT_VARIANT_WORDS in
  engine/config.py: "Timemore C2" and "Timemore C2 Max", "Dynasty Cream" and "new Dynasty Cream"), or when the
  two names end in different kinds of product ("CeraVe cream" and "CeraVe Cream to Foam cleanser"). Since 10 Oct
  2026 a word of the shorter name may be found with a spelling slip (below): "Commandante" in "Comandante C40",
  "Kikumasamune Sake cream" in "Kikumasamume Sake Skin Care Cream". A slip in the shorter name's first word (most
  often its brand) is only forgiven where the longer name starts: "treitnoin .05" (tretinoin in general) is not
  "Obagi 0.05% tretinoin cream";
- they differ only by small spelling slips, word for word.
A spelling slip is: an "s" added to any word of 3 letters or more ("pan" and "pans", "ordinarys" and "ordinary"); a
letter written twice in a word of letters ("hurr" and "hur", "matt" and "mat"; not digits: "Lido 2" and "Lido 22"
are two models); or, in words of 5 letters or more that start with the same letter, one letter added, dropped or
changed, or letters moved within three neighbouring places ("zojirushi" and "zojurushi", "cosrx" and "corsx",
"creseut" and "creuset"; but "Hario" and "Vario" are two brands). Other short words must match exactly: model names
often differ by one letter ("V60", "V61"). Some words a slip apart are two different words (NOT_SLIPS: "retinal" and
"retinol" are two retinoids).
Before these rules, a word one name writes as one and the other splits in two counts as the same word
("SoonJung" and "Soon Jung", "spf50" and "spf 50"), and an "and" only one name writes is dropped, as "&" is
("Black and Decker" and "Black & Decker"; 10 Oct 2026).
Anything else is a different product ("cerave hydrating cleanser" and "cerave sa cleanser").

The known short names live in engine/data/product_aliases.json, per category, each with the library names that
show it is needed. A short name is only written out at the start of a name, because some are everyday words:
"TO" is The Ordinary, but "to" in "Cream to Foam" is not. Since 10 Oct 2026 it is written out also with a spelling
slip or a possessive ("BoJ's", "TO's": only with the apostrophe, since "Q2S" is not the "Q2"), and a name written out
can start with another short name, written out in turn ("BoJ retinal eye cream" -> "Beauty of Joseon retinal eye
cream" -> "Beauty of Joseon Revive Eye Serum"). A short name may also be a product's other name, where a rule would
be too risky ("Hario Slim" is the Hario Mini Slim, "House of Hur weightless sunscreen" its Weightless Sun Fluid).

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
- a model word that is the product's own name is read as another model ("Hario slim" and the "Hario Mini-Slim"),
  unless a known short name says otherwise (the alias list has the Hario Slim);
- a brand alone doesn't match its models that add a model word either ("Hario" and "Hario Skerton Pro"),
  because words can't tell a brand ("Hario") from a product ("Aeropress", whose "Aeropress Go" is another one);
- a shorter name, such as a brand with a kind of product ("Henckels classic", "Babish knives"), matches a set of
  those products ("Henckels 3 piece classic set"); answers leave sets out before grouping (engine/pipeline.py).
Also: a filler word that really is part of a name ("One" in a product called "One") is dropped too.
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
# "peeling solution by the ordinary"; "by" and "from" added 9 Oct 2026; "refurbished" on 10 Oct 2026: a refurbished
# unit is the same product, "Baratza Virtuoso+ (refurbished)").
FILLER_WORDS = frozenset({"one", "ones", "brand", "the", "my", "their", "by", "from", "refurbished"})
# "&" is punctuation, so dropped; "and" written out is dropped too when only one of two names has it (comparable).
AND = "and"
# A one-letter typo, or two swapped letters, is only forgiven in words at least this long.
TYPO_MIN_LENGTH = 5
# A plural "s" is forgiven on words at least this long ("pan" and "pans"; but "K" and "Ks" stay apart).
PLURAL_MIN_LENGTH = 3
# At most this many words written apart can make one word written as one ("J", "Max" and "JMax").
MAX_WORDS_JOINED = 3
# A letter written twice instead of once ("Hurr" for "Hur") is a slip in words of letters at least this long.
DOUBLED_MIN_LENGTH = 3
# Letters moved within this many neighbouring places are a slip ("Creseut" for "Creuset": three places).
MOVED_LETTERS_SPAN = 3
# Words a slip apart that are two different words: "retinal" and "retinol" are two retinoids (10 Oct 2026).
NOT_SLIPS = frozenset({frozenset({"retinal", "retinol"})})
# "non" before a model word says which model a name is not: "1zpresso JX (non pro)" is the plain JX.
NEGATION = "non"
# A short name written out can start with another short name, written out in turn, at most this many times.
MAX_SPELL_OUTS = 3
# Words naming a kind of product. Two names that each end in one of these, but not the same one, are different
# products, even when one is found inside the other: "CeraVe cream" and "CeraVe Cream to Foam cleanser".
PRODUCT_TYPE_WORDS = frozenset({
    "cream", "cleanser", "serum", "toner", "lotion", "sunscreen", "sunblock", "essence", "ampoule", "mask", "oil",
    "balm", "gel", "milk", "mist", "pad", "pads", "foam", "wash", "moisturizer", "moisturiser", "ointment", "powder",
    "soap", "scrub", "spray", "peel",
    "pan", "skillet", "kettle", "grinder", "knife", "pot", "lid", "oven", "scale", "burrs",
})

_APOSTROPHES = re.compile(r"['’‘`]")
_POSSESSIVE = re.compile(r"([^\W_]+)['’‘`]s(?![^\W_])")  # "TO's": the word before the apostrophe
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
    return _without_negated_models(_without_size_units([word for word in words if word not in FILLER_WORDS]))


# A size's unit after its number: '8 inch' reads as '8"', whose mark plain_words already drops (b07, 10 Oct 2026).
SIZE_UNITS = frozenset({"inch", "inches"})


def _without_size_units(words: list[str]) -> list[str]:
    """`words` without a unit word straight after a number: "wusthof classic 8 inch" -> wusthof classic 8."""
    return [word for i, word in enumerate(words) if not (word in SIZE_UNITS and i > 0 and words[i - 1].isdigit())]


def _without_negated_models(words: list[str]) -> list[str]:
    """`words` without "non" and the model word after it: "1zpresso jx non pro" is the plain JX (10 Oct 2026)."""
    kept, i = [], 0
    while i < len(words):
        if words[i] == NEGATION and i + 1 < len(words) and words[i + 1] in PRODUCT_VARIANT_WORDS:
            i += 2
            continue
        kept.append(words[i])
        i += 1
    return kept


def plain_words(text: str) -> list[str]:
    """Every word of a text, lowercase, without accents or punctuation, and with no word left out."""
    return _WORD.findall(_APOSTROPHES.sub("", _plain_text(text)))


def _plain_text(text: str) -> str:
    """The text in lowercase, with HTML codes turned back into characters and accents dropped."""
    text = html.unescape(text)
    # Split accented letters into the letter and its accent, then drop the accent.
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)).lower()


def product_words(name: str, aliases: Aliases = NO_ALIASES) -> list[str]:
    """The words of a name (normalize_name), with a known short name at its start written out in full.

    A short name written with a possessive is written out too ("TO's mandelic acid"), but only when the name shows the
    apostrophe: without it, an "s" after a model code is another model ("Q2S" is not the "Q2").
    """
    words = normalize_name(name)
    spelled = spell_out(words, aliases)
    if spelled == words and words and _written_possessive(words[0], name):
        unpossessive = [words[0][:-1], *words[1:]]
        if (spelled := spell_out(unpossessive, aliases)) != unpossessive:
            return spelled
        return words
    return spelled


def _written_possessive(word: str, name: str) -> bool:
    """Whether `word` ("tos") is written in `name` as a possessive ("TO's")."""
    return len(word) > 1 and word.endswith("s") and any(
        "".join(_WORD.findall(w)) == word[:-1] for w in _POSSESSIVE.findall(_plain_text(name)))


def spell_out(words: list[str], aliases: Aliases) -> list[str]:
    """Writes out a known short name at the start of a name: "to sunscreen" -> ordinary sunscreen.

    The longest short name that fits is used, even written with a small slip ("house of hurr weightless sunscreen",
    see _spelling_slip). A name that already holds every word of the full name ("Timemore C2", for the model "C2") is
    left as it is. A short name written out can start with another one, which is written out in turn: "boj retinal eye
    cream" -> beauty of joseon retinal eye cream -> beauty of joseon revive eye serum.
    """
    for _ in range(MAX_SPELL_OUTS):
        spelled = _spell_out_once(words, aliases)
        if spelled == words:
            break
        words = spelled
    return words


def _spell_out_once(words: list[str], aliases: Aliases) -> list[str]:
    for short in sorted(aliases, key=len, reverse=True):
        start = words[:len(short)]
        if len(start) == len(short) and all(x == y or _spelling_slip(x, y) for x, y in zip(start, short)):
            full = aliases[short]
            if _already_says(words, full) and not set(full) <= set(short):  # a longer short name ("Field Company"
                return words                                                 # for "Field") is written out anyway
            return full + words[len(short):]
    return words


def _already_says(words: list[str], full: list[str]) -> bool:
    """Whether a name already holds every word of a short name's full name, maybe written as one word or with a slip:
    "elta md" says "eltamd", "ettude houde" says "etude house"."""
    joined = join_split_words(words, full)
    return all(any(w == f or _spelling_slip(f, w) for w in joined) for f in full)


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
    words_a, words_b = comparable(words_a, words_b)
    if words_a == words_b:
        return True
    return _found_inside(words_a, words_b) or _only_typos_apart(words_a, words_b)


def written_alike(words_a: list[str], words_b: list[str]) -> bool:
    """Whether two names (product_words) are the same name, but for spacing, an "and" or small spelling slips: not one
    found inside the other. Price and facts lookups prefer an entry written alike to one that only fits (10 Oct 2026)."""
    words_a, words_b = comparable(words_a, words_b)
    return words_a == words_b or _only_typos_apart(words_a, words_b)


def comparable(words_a: list[str], words_b: list[str]) -> tuple[list[str], list[str]]:
    """Two names' words made ready to compare: words one name writes apart and the other as one are joined
    (join_split_words), and an "and" only one of them writes is dropped, since "&" is dropped as punctuation:
    "black and decker" and "black decker" (10 Oct 2026)."""
    words_a = join_split_words(words_a, words_b)
    words_b = join_split_words(words_b, words_a)
    if (AND in words_a) != (AND in words_b):
        words_a, words_b = [w for w in words_a if w != AND], [w for w in words_b if w != AND]
    return words_a, words_b


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
    """Whether every word of the shorter name is in the longer one (as it is, or with a spelling slip), the shorter
    says enough to be a name, and the longer doesn't add a word naming another model or version."""
    shorter, longer = sorted((words_a, words_b), key=len)
    found = _words_found(shorter, longer)
    if found is None:
        return False
    added = {w for i, w in enumerate(longer) if i not in found} - set(shorter)
    if added & PRODUCT_VARIANT_WORDS:
        return False
    if _different_types(shorter[-1], longer[-1]):
        return False
    if len(shorter) >= 2:
        return True
    # One word: a brand that starts the longer name, maybe with its possessive ("FAB" and "FAB's exfoliating pads").
    return _brand_like(shorter[0]) and (longer[0] == shorter[0] or _spelling_slip(shorter[0], longer[0]))


def _words_found(shorter: list[str], longer: list[str]) -> set[int] | None:
    """The places in `longer` of the words of `shorter`, each found as it is or else with a spelling slip (one place
    per word); None when a word isn't there. Since 10 Oct 2026 a slip is forgiven here too: "Commandante" in "Comandante
    C40", "Kikumasamune Sake cream" in "Kikumasamume Sake Skin Care Cream"."""
    found: set[int] = set()
    for n, word in enumerate(shorter):
        if word in longer:
            continue  # found as it is; repeated words are fine
        # A first word (most often the brand) is only forgiven a slip where the longer name starts: "treitnoin .05" is
        # tretinoin in general, not "Obagi 0.05% tretinoin cream".
        places = [i for i, w in enumerate(longer)
                  if i not in found and w not in shorter and _spelling_slip(word, w) and (n > 0 or i == 0)]
        if not places:
            return None
        found.add(places[0])
    return found | {i for i, w in enumerate(longer) if w in shorter}


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
    """Whether two different words are one word misspelled: a plural "s", a letter doubled ("hurr" for "hur"), or a
    slip in a long word that keeps its first letter: one letter added, dropped or changed, or letters moved within
    three neighbouring places ("creseut" for "creuset")."""
    if x == y or frozenset((x, y)) in NOT_SLIPS:
        return False
    shorter, longer = sorted((x, y), key=len)
    if longer == shorter + "s" and len(shorter) >= PLURAL_MIN_LENGTH:
        return True
    if _letter_doubled(shorter, longer):
        return True
    if len(shorter) < TYPO_MIN_LENGTH or x[0] != y[0]:
        return False
    return one_edit_apart(x, y) or _letters_moved(x, y)


def _letter_doubled(shorter: str, longer: str) -> bool:
    """True if writing one letter of `shorter` twice gives `longer` ("hur" and "hurr"), in words of letters only:
    digits are model numbers ("Lido 2" and "Lido 22")."""
    if len(longer) != len(shorter) + 1 or len(shorter) < DOUBLED_MIN_LENGTH or not longer.isalpha():
        return False
    return any(longer[i] == longer[i - 1] and longer[:i] + longer[i + 1:] == shorter for i in range(1, len(longer)))


def _letters_moved(x: str, y: str) -> bool:
    """True if x and y have the same letters, in places that differ only within MOVED_LETTERS_SPAN neighbouring
    places: two letters swapped ("cosrx" and "corsx"), or one moved two places ("creseut" and "creuset")."""
    if len(x) != len(y) or sorted(x) != sorted(y):
        return False
    differ = [i for i, (p, q) in enumerate(zip(x, y)) if p != q]
    return bool(differ) and differ[-1] - differ[0] < MOVED_LETTERS_SPAN


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
