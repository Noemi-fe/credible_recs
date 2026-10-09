"""Module 4, product matching: tells whether two names, written by different people, mean the same product.

Commenters, Noemi and the AI all write product names their own way: "CeraVe SA", "the CeraVe Renewing SA
Cleanser", "cerave sa cleanser". This is the first, rules-only version: it compares the words of two names and
nothing else. Module 3's scores use it today (engine/extraction_eval.py), to pair the AI's mentions with Noemi's.
Module 4 proper will add a curated list of known products per category, and an AI step for the hard cases,
flagged for review.

How two names are compared. Each is first turned into a list of words (normalize_name): lowercase, HTML codes
turned back into characters ("&amp;" into "&"), accents dropped ("Avène" as "avene"), apostrophes dropped inside
a word ("Paula's" as "paulas"), every other punctuation mark treated as a space, and filler words left out. Then
two names mean the same product when:
- their words are the same; or
- every word of the shorter name is in the longer one ("cerave sa" in "cerave renewing sa cleanser"), as long as
  the shorter has at least 2 words, or is a single brand-like word (not just a number) that also starts the
  longer name ("zojirushi" and "zojirushi kettle"; but "kettle" alone names a kind of product, not this one);
- they differ only by a one-letter typo in some words of 5 letters or more ("zojirushi" and "zojurushi").
  Shorter words must match exactly: model names often differ by one letter ("V60", "V61").
Anything else is a different product ("cerave hydrating cleanser" and "cerave sa cleanser").

Known gaps, the edge cases in the brief's End-state tree that rules on words can't settle yet:
- old versus new formula: a reformulated product keeps its name, so the two look identical here;
- sizes and variants: "Lodge skillet" matches "Lodge 12 inch skillet", so every size of a product is merged
  under its shorter name, while two sizes written out in full ("10 inch", "12 inch") stay apart;
- US versus EU names: one product sold under two names is not matched, as there is no list of known aliases yet;
- brand versus product line: a brand alone ("CeraVe") matches any of its products, and a loose name ("CeraVe
  cleanser") matches each of the brand's cleansers, so a vague name can't be told from a specific one.
- one description written two ways ("Professional Fillet Knife 7 Les Forges 1890" and "Opinel Les Forges 1890 7
  Fillet Knife"): a rule for "most words shared" was tried on 9 Oct 2026 and dropped, because in the library it
  merged far more different products ("Round Lab Birch Juice Pads" and "... cream") than renamed ones.
Also: a filler word that really is part of a name ("One" in a product called "One") is dropped too; a typo is
only forgiven when the two names have the same number of words, so "Zojurushi" doesn't match "Zojirushi kettle".
"""

import html
import re
import unicodedata

from engine.text import one_edit_apart

# Dropped from the start of a name only: "a" inside a name is often part of it ("Vitamin A serum").
LEADING_WORDS = ("the", "a", "my")
# Dropped anywhere: words people add around a name that aren't part of it ("the Victorinox one", "Le Creuset brand",
# "peeling solution by the ordinary"; "by" and "from" added 9 Oct 2026).
FILLER_WORDS = frozenset({"one", "ones", "brand", "the", "my", "their", "by", "from"})
# A one-letter typo is only forgiven in words at least this long.
TYPO_MIN_LENGTH = 5

_APOSTROPHES = re.compile(r"['’‘`]")
_WORD = re.compile(r"[^\W_]+")  # a run of letters and digits


def normalize_name(name: str) -> list[str]:
    """The words of a product name, in a form that compares cleanly: "The Paula's Choice 2% BHA" -> paulas choice 2 bha."""
    text = html.unescape(name)
    # Split accented letters into the letter and its accent, then drop the accent.
    text = "".join(ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch))
    words = _WORD.findall(_APOSTROPHES.sub("", text.lower()))
    while words and words[0] in LEADING_WORDS:
        words.pop(0)
    return [word for word in words if word not in FILLER_WORDS]


def same_product(a: str, b: str) -> bool:
    """Whether two names mean the same product, by the rules at the top of this file."""
    words_a, words_b = normalize_name(a), normalize_name(b)
    if not words_a or not words_b:
        return False  # a name made only of filler words ("the one") names nothing
    if words_a == words_b:
        return True
    return _found_inside(words_a, words_b) or _only_typos_apart(words_a, words_b)


def _found_inside(words_a: list[str], words_b: list[str]) -> bool:
    """Whether every word of the shorter name is in the longer one, and the shorter says enough to be a name."""
    shorter, longer = sorted((words_a, words_b), key=len)
    if not set(shorter) <= set(longer):
        return False
    if len(shorter) >= 2:
        return True
    return _brand_like(shorter[0]) and longer[0] == shorter[0]


def _brand_like(word: str) -> bool:
    """A single word could be a brand if it has a letter: "zojirushi" could, "10" (a size) can't."""
    return any(ch.isalpha() for ch in word)


def _only_typos_apart(words_a: list[str], words_b: list[str]) -> bool:
    """Whether the names have the same words in the same order, except one-letter typos in long words."""
    if len(words_a) != len(words_b):
        return False
    return all(
        x == y or (min(len(x), len(y)) >= TYPO_MIN_LENGTH and one_edit_apart(x, y))
        for x, y in zip(words_a, words_b)
    )
