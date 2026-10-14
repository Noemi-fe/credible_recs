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
  longer name ("zojirushi" and "zojirushi kettle"; but "kettle" alone names a kind of product, not this one). Since
  13 Oct 2026 a shorter name that doesn't start where the longer one starts (most often, written without its brand)
  needs two words besides its kinds of product (KIND_WORDS, haircare's "shampoo" and "conditioner" among them): one
  word and a kind ("Chai shampoo") is only the longer name's product when the longer name is it with a brand before it
  ("Ecoslay Chai shampoo"); a flavour found among another maker's words is not ("Hair Food coconut milk and chai spice
  shampoo"). Grouping lets such a name in when its word is written alone as a name (held_back_word: a brand);
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
from collections import defaultdict
from collections.abc import Iterable
from functools import cache
from pathlib import Path
from typing import NamedTuple

from engine.config import MENTION_CATEGORIES, PRODUCT_VARIANT_WORDS
from engine.memo import Table, register
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
# Words a slip apart that are two different words: "retinal" and "retinol" are two retinoids (10 Oct 2026); Prequel's
# "Pre-Gleanse" is a cleansing balm, not its "Gleanser" (11 Oct 2026, b05).
NOT_SLIPS = frozenset({frozenset({"retinal", "retinol"}), frozenset({"gleanse", "gleanser"})})
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
# Every word that says what kind of product a name is: the words above, and haircare's (13 Oct 2026; the category came
# on 11 Oct). A name without its brand needs more than one word besides these (_says_enough_without_its_brand). The
# haircare words don't tell two names apart by their last words, as the words above do: haircare's line names often end
# in a kind ("Neutrogena T/Gel", "SheaMoisture Castor Oil"), and the T/Gel is its shampoo.
KIND_WORDS = PRODUCT_TYPE_WORDS | {"shampoo", "conditioner"}

_APOSTROPHES = re.compile(r"['’‘`]")
_POSSESSIVE = re.compile(r"([^\W_]+)['’‘`]s(?![^\W_])")  # "TO's": the word before the apostrophe
_WORD = re.compile(r"[^\W_]+")  # a run of letters and digits

# Known short names of one category: the short name's words -> the full name's words.
Aliases = dict[tuple[str, ...], list[str]]
NO_ALIASES: Aliases = {}


class AliasError(Exception):
    pass


def normalize_name(name: str) -> list[str]:
    """The words of a product name, in a form that compares cleanly: "The Paula's Choice 2% BHA" -> paulas choice 2 bha.

    Each name is worked out once and remembered (latency, 12 Oct 2026): answers compare the same names thousands of
    times. The list handed back is a new one each time, so a caller changing it changes nothing remembered."""
    words = _NORMALIZED.get(name)
    if words is None:
        words = _NORMALIZED[name] = tuple(_normalize_name(name))
        _limit(_NORMALIZED)
    return list(words)


def _normalize_name(name: str) -> list[str]:
    words = plain_words(PACK_SIZE.sub(" ", name))
    while words and words[0] in LEADING_WORDS:
        words.pop(0)
    return _without_negated_models(_without_size_units([word for word in words if word not in FILLER_WORDS]))


# --- Names already worked out (latency, 12 Oct 2026) ---
# A name's words depend only on the name and the list of short names used, so each is worked out once. A list of short
# names is known by its identity (the shipped list is read once: known_aliases), and kept with its answers, so a list
# the caller drops can't be mistaken for a new one made in its place. Lists are never changed once made.
_NORMALIZED: dict[str, tuple[str, ...]] = {}
_WORDS_BY_LIST: dict[int, tuple[dict, dict[str, tuple[str, ...]]]] = {}  # id(list) -> (the list, {name: words})
_WORDS_NO_ALIASES: dict[str, tuple[str, ...]] = {}  # every empty list gives the same words
_FEATURES: dict[tuple[str, ...], "_Features"] = {}  # a name's words -> what _cannot_match reads of them
_SLIP_KEYS: dict[str, tuple] = {}  # a word -> the first letters and lengths it could be a slip of (_slip_keys)
MAX_LISTS_REMEMBERED = 16
MAX_NAMES_REMEMBERED = 200_000  # per table; a full table starts again (a long-running server never grows past it)
for _table in (_NORMALIZED, _WORDS_BY_LIST, _WORDS_NO_ALIASES, _FEATURES, _SLIP_KEYS):
    register(_table.clear)  # engine.memo.forget_all empties them
_SAME = Table()  # (words, words) -> whether they name the same product (same_words)
_PLAIN_WORDS = Table()  # a text -> its words (plain_words)
_HELD_BACK = Table()  # (words, words) -> held_back_word's word, or "" for none


def _limit(table: dict) -> None:
    if len(table) > MAX_NAMES_REMEMBERED:
        table.clear()


def _words_table(aliases: "Aliases") -> dict[str, tuple[str, ...]]:
    """The remembered words of names under this list of short names."""
    if not aliases:
        return _WORDS_NO_ALIASES
    found = _WORDS_BY_LIST.get(id(aliases))
    if found is not None and found[0] is aliases:
        return found[1]
    if len(_WORDS_BY_LIST) >= MAX_LISTS_REMEMBERED:
        _WORDS_BY_LIST.pop(next(iter(_WORDS_BY_LIST)))  # the list remembered first
    table: dict[str, tuple[str, ...]] = {}
    _WORDS_BY_LIST[id(aliases)] = (aliases, table)
    return table


# A pack size ("74g", "118 ml", "1.7 fl oz") says which size was priced, not which product it is: it is dropped (b01,
# 10 Oct 2026: the entry "Dermalogica Daily Microfoliant 74g" wasn't found for a group shown with its type word at the
# end). Litres and inches are kept: a kettle's capacity and a pan's size tell models apart.
PACK_SIZE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:ml|g|fl\.?\s*oz|oz)\b", re.IGNORECASE)

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
    """Every word of a text, lowercase, without accents or punctuation, and with no word left out. Each text's words are
    worked out once (latency, 13 Oct 2026: care tips and kinds compare the same texts over and over); the list handed
    back is a new one each time, so a caller changing it changes nothing remembered."""
    words = _PLAIN_WORDS.get(text)
    if words is None:
        words = _PLAIN_WORDS.keep(text, tuple(_WORD.findall(_APOSTROPHES.sub("", _plain_text(text)))))
    return list(words)


def _plain_text(text: str) -> str:
    """The text in lowercase, with HTML codes turned back into characters and accents dropped."""
    text = html.unescape(text)
    # Split accented letters into the letter and its accent, then drop the accent.
    return "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)).lower()


def product_words(name: str, aliases: Aliases = NO_ALIASES) -> list[str]:
    """The words of a name (normalize_name), with a known short name at its start written out in full.

    A short name written with a possessive is written out too ("TO's mandelic acid"), but only when the name shows the
    apostrophe: without it, an "s" after a model code is another model ("Q2S" is not the "Q2"). Each name is worked out
    once per list of short names and remembered (latency, 12 Oct 2026); the list handed back is a new one each time.
    """
    table = _words_table(aliases)
    words = table.get(name)
    if words is None:
        words = table[name] = tuple(_product_words(name, aliases))
        _limit(table)
    return list(words)


def _product_words(name: str, aliases: Aliases) -> list[str]:
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
    """same_product on names already turned into words (product_words). It depends on the two names' words alone, so
    each pair is compared once and remembered (latency, 12 Oct 2026). Most pairs are settled by a quick look first
    (_cannot_match, 13 Oct 2026), and those are never remembered: the memory keeps only the pairs worth it."""
    if _cannot_match(words_a, words_b):
        return False
    return same_words_looked_at(words_a, words_b)


def same_words_looked_at(words_a, words_b) -> bool:
    """same_words for a pair the quick look leaves (_cannot_match is False): compared once and remembered."""
    key = (tuple(words_a), tuple(words_b))
    found = _SAME.get(key)
    if found is None:
        found = _SAME.keep(key, _same_words(words_a, words_b))
    return found


def _cannot_match(words_a, words_b) -> bool:
    """A quick, sure no for most pairs of names, before same_words compares them (latency, 13 Oct 2026: of the 700,000
    pairs of names the 40 latency requests compare, 9 in 10; only 1 in 60 match). True when a word of the shorter name
    is neither one of the longer name's words nor could be a spelling slip of one (_spelling_slip: a slip keeps the
    first letter and the length within one, a word of 1 or 2 letters has none, one of 3 or 4 only gains or loses a
    letter, and the shorter name's first word only slips at the longer name's start; _words_found). The words compared
    are the ones comparable gives: an "and" only one name writes left out of both. When two or three neighbouring words
    of one are a word of the other ("soon jung", "soonjung"), comparable may join them, so it says nothing (False) and
    same_words looks closely."""
    if not words_a or not words_b:
        return True
    a, b = _features(words_a), _features(words_b)
    if not a.runs.isdisjoint(b.words) or not b.runs.isdisjoint(a.words):
        return False
    if a.has_and != b.has_and:  # comparable leaves the "and" out of both
        words_a, words_b = a.without_and, b.without_and
        if not words_a or not words_b:
            return False  # a name of "and" alone: left to same_words
        a, b = _features(words_a), _features(words_b)
    shorter, longer = (words_a, b) if len(words_a) <= len(words_b) else (words_b, a)  # as _found_inside sorts them
    first = True
    for word in shorter:
        if word not in longer.words and not _could_slip(word, longer.starts if first else longer.lengths):
            return True
        first = False
    return False


class _Features(NamedTuple):
    """What _cannot_match reads of a name's words, worked out once per name."""

    words: frozenset[str]
    runs: frozenset[str]  # every 2 or 3 neighbouring words written as one (join_split_words joins only into those)
    lengths: frozenset[tuple[str, int]]  # (first letter, length) of each word
    starts: frozenset[tuple[str, int]]  # the same, of its first word only
    has_and: bool
    without_and: tuple[str, ...]  # its words but "and"


def _features(words) -> _Features:
    words = tuple(words)
    found = _FEATURES.get(words)
    if found is None:
        found = _FEATURES[words] = _Features(
            frozenset(words), _runs(words), frozenset((w[:1], len(w)) for w in words),
            frozenset((w[:1], len(w)) for w in words[:1]), AND in words, tuple(w for w in words if w != AND))
        _limit(_FEATURES)
    return found


def _runs(words: tuple[str, ...]) -> frozenset[str]:
    """Every run of 2 to MAX_WORDS_JOINED neighbouring words, written as one word: the only words join_split_words can
    make."""
    return frozenset("".join(words[i:i + size]) for size in range(2, MAX_WORDS_JOINED + 1)
                     for i in range(len(words) - size + 1))


def _could_slip(word: str, lengths: frozenset[tuple[str, int]]) -> bool:
    """Whether `word` could be a spelling slip of a word with one of these (first letter, length), by _spelling_slip's
    rules on letters and lengths alone: the same length needs 5 letters or more (a letter changed or moved); one
    letter more or less needs the shorter word to have 3 or more (a plural "s", a doubled letter, a letter added)."""
    return not lengths.isdisjoint(_slip_keys(word))


def _slip_keys(word: str) -> tuple[tuple[str, int], ...]:
    """The (first letter, length) of the words `word` could be a spelling slip of (_could_slip), worked out once per
    word."""
    found = _SLIP_KEYS.get(word)
    if found is None:
        first, n = word[:1], len(word)
        found = _SLIP_KEYS[word] = tuple(key for key, possible in (
            ((first, n), n >= TYPO_MIN_LENGTH), ((first, n + 1), n >= _SHORTEST_SLIPPING),
            ((first, n - 1), n - 1 >= _SHORTEST_SLIPPING)) if possible)
        _limit(_SLIP_KEYS)
    return found


# The fewest letters the shorter of two words a letter apart in length needs for a slip (a plural, a doubled letter or a
# letter added): _spelling_slip.
_SHORTEST_SLIPPING = min(PLURAL_MIN_LENGTH, DOUBLED_MIN_LENGTH, TYPO_MIN_LENGTH)


def _same_words(words_a: list[str], words_b: list[str]) -> bool:
    if not words_a or not words_b:
        return False  # a name made only of filler words ("the one") names nothing
    words_a, words_b = comparable(words_a, words_b)
    if words_a == words_b:
        return True
    return _found_inside(words_a, words_b) or _only_typos_apart(words_a, words_b)


def match_candidates(names: Iterable[tuple[str, ...]]) -> dict[tuple[str, ...], set[tuple[str, ...]]]:
    """For each name, the names among `names` it could match (match_candidates_and_open)."""
    return match_candidates_and_open(names)[0]


def match_candidates_and_open(names: Iterable[tuple[str, ...]]) -> tuple[dict[tuple[str, ...], set[tuple[str, ...]]],
                                                                         set[tuple[tuple[str, ...], tuple[str, ...]]]]:
    """For each name (its words, as product_words gives them), the names among `names` it could match: the pairs the
    quick look (_cannot_match) doesn't rule out, one way round or the other, so grouping (engine/group_products.py)
    compares only these. Every pair that matches by same_words, has a held-back word or is written alike is among them
    (each needs every word of the shorter name found in the longer one). A big request has 1,000 names, half a million
    pairs: comparing them all took seconds (latency, 12 Oct 2026).

    How they are found without looking at every pair (13 Oct 2026; until then by first letters alone, ten times as many
    pairs): when a name is the shorter of two that can match, each of its words is one of the other's, or could be a
    spelling slip of one (_could_slip: the same first letter, a length within one), its first word only of the other's
    first word. So the names each word could be found in are listed once (an index of every name's words, and of their
    words' first letters and lengths), and the names on every list of a name's words are the ones it could match as the
    shorter; pairs where the other is the shorter are found from the other's side. An "and" only one of two names
    writes is left out of both (comparable), so a name's "and" never needs finding, its first word is any of its words,
    and each name is listed under its first word and its first word but "and". Words written apart that may join into
    one of the other's ("soon jung", "soonjung") keep the pair. Each pair found is then asked the quick look itself,
    both ways round. Also the pairs, in order, the quick look leaves (a, b): grouping asks no more about them
    (engine.group_products._matching)."""
    names = list(dict.fromkeys(names))
    by_word: dict[str, set] = defaultdict(set)  # a word -> the names with it
    by_length: dict[tuple[str, int], set] = defaultdict(set)  # a word's first letter and length -> the names with one
    by_start: dict[tuple[str, int], set] = defaultdict(set)  # the same, for names' first words (and first but "and")
    for name in names:
        for word in name:
            by_word[word].add(name)
            by_length[(word[:1], len(word))].add(name)
        for word in {*name[:1], *_features(name).without_and[:1]}:
            by_start[(word[:1], len(word))].add(name)
    covers: dict[tuple[str, bool], set] = {}

    def cover(word: str, first: bool) -> set:
        """The names `word` could be found in (as a first word: slipped only at their start)."""
        found = covers.get((word, first))
        if found is None:
            index = by_start if first else by_length
            found = set(by_word.get(word, ()))
            for key in _slip_keys(word):
                found |= index.get(key, set())
            covers[(word, first)] = found
        return found

    candidates: dict[tuple[str, ...], set[tuple[str, ...]]] = {name: set() for name in names}
    open_pairs: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    for name in names:
        features = _features(name)
        words = list(dict.fromkeys(features.without_and if features.has_and else name))
        if words:
            lists = sorted((cover(word, i == 0 and not features.has_and) for i, word in enumerate(words)), key=len)
            found = lists[0].intersection(*lists[1:])
        else:  # no word to tell by (an empty name, or "and" alone): every name
            found = set(names)
        for run in features.runs:
            found |= by_word.get(run, set())
        for other in found:
            if other == name or other in candidates[name]:
                continue  # the same name, or a pair already found from the other's side
            forth, back = not _cannot_match(name, other), not _cannot_match(other, name)
            if forth:
                open_pairs.add((name, other))
            if back:
                open_pairs.add((other, name))
            if forth or back:
                candidates[name].add(other)
                candidates[other].add(name)
    return candidates, open_pairs


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
    # A run joins only into a word of the other name that is the run written as one: when none is, nothing joins (a
    # quick answer for most pairs of names; latency, 12 Oct 2026, and 13 Oct 2026: the runs, worked out once per name).
    if _features(words).runs.isdisjoint(targets):
        return list(words)
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


def _found_inside(words_a: list[str], words_b: list[str], waive_brandless: bool = False) -> bool:
    """Whether every word of the shorter name is in the longer one (as it is, or with a spelling slip), the shorter
    says enough to be a name, and the longer doesn't add a word naming another model or version. `waive_brandless`
    leaves out the rule for a name without its brand (held_back_word)."""
    shorter, longer = sorted((words_a, words_b), key=len)
    found = _words_found(shorter, longer)
    if found is None:
        return False
    added = {w for i, w in enumerate(longer) if i not in found} - set(shorter)
    if added & PRODUCT_VARIANT_WORDS:
        return False
    if _different_types(shorter[-1], longer[-1]):
        return False
    starts_it = longer[0] == shorter[0] or _spelling_slip(shorter[0], longer[0])
    if len(shorter) >= 2:
        return starts_it or waive_brandless or _says_enough_without_its_brand(shorter, longer)
    # One word: a brand that starts the longer name, maybe with its possessive ("FAB" and "FAB's exfoliating pads").
    return _brand_like(shorter[0]) and starts_it


def _says_enough_without_its_brand(shorter: list[str], longer: list[str]) -> bool:
    """For a shorter name that doesn't start where the longer one starts (most often, written without its brand):
    whether it says enough to be the longer one's product. Two words besides its kinds of product (KIND_WORDS) do ("SA
    cleanser" in "CeraVe Renewing SA Cleanser"); one word and a kind ("Chai shampoo") only when the longer name is it
    with words before it, a brand ("Ecoslay Chai shampoo", "Neutrogena T Gel"). A flavour or an ingredient many makers
    use ("chai", "mugwort") found among another maker's words isn't its product (13 Oct 2026: one maker's chai shampoo,
    named without its brand, had joined another maker's coconut milk and chai spice shampoo)."""
    if len(own_words(shorter)) >= 2:
        return True
    ending = longer[-len(shorter):]
    return all(x == y or _spelling_slip(x, y) for x, y in zip(shorter, ending))


def own_words(words: list[str]) -> list[str]:
    """A name's words besides its kinds of product (KIND_WORDS, or their plurals): "chai shampoo" -> chai."""
    return [w for w in words if w not in KIND_WORDS and w.removesuffix("s") not in KIND_WORDS]


def held_back_word(words_a: list[str], words_b: list[str]) -> str | None:
    """The one word a shorter name says besides its kinds of product, when that rule alone keeps two names apart
    (_says_enough_without_its_brand): "ballarini" for "Ballarini pans" and "Zwilling/Ballarini non-stick pans", "chai"
    for "Chai shampoo" and another maker's chai spice shampoo; None otherwise (they match, or never would). Grouping
    lets them match when that word is written alone as a name there, so it is a brand, not a flavour (13 Oct 2026).
    Remembered like same_words."""
    key = (tuple(words_a), tuple(words_b))
    found = _HELD_BACK.get(key)
    if found is None:
        found = _HELD_BACK.keep(key, _held_back_word(words_a, words_b) or "")
    return found or None


def _held_back_word(words_a: list[str], words_b: list[str]) -> str | None:
    if not words_a or not words_b or same_words(words_a, words_b):
        return None
    words_a, words_b = comparable(words_a, words_b)
    if not _found_inside(words_a, words_b, waive_brandless=True):
        return None
    shorter = min((words_a, words_b), key=len)
    own = own_words(shorter)
    return own[0] if len(own) == 1 else None


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
                  if (n > 0 or i == 0) and i not in found and w not in shorter and _spelling_slip(word, w)]
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
    if x == y or not x or not y or x[0] != y[0] or abs(len(x) - len(y)) > 1:
        return False  # every slip below keeps the first letter and the length within one: a quick no for most pairs
    if frozenset((x, y)) in NOT_SLIPS:
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
