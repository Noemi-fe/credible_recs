"""Module 4, kinds of product: groups the AI's notes by the kind of product they are about, and places each product
group in the kinds its name names.

Kinds are open-ended (Noemi, 9 Oct 2026): the AI's notes (engine.extract.ExtractedNote) say what kind of product
a piece of advice is about, in its own words: "carbon steel pan", "hand grinder for espresso", "plastic-free
kettle", "chemical exfoliant". For the threads of one request, group_kinds gathers the notes that are about the
same kind, so the ranking (module 6) can see which kinds get the most credible support, and says which products
belong to each kind ("Miyabi Santoku" to santoku).

What a note's kind is (kind_parts), in this order:
1. hyphens inside a word are dropped ("non-stick" as "nonstick"), then the words are taken as for product names,
   but no word is skipped yet; a plural "s" is dropped ("pans" as "pan"), and the category's known names for a
   kind are written out (engine/data/product_aliases.json, "kinds": "skillet" as "pan", "BHA" as "salicylic
   acid");
2. what comes after a word like "for", "with", "on" or "over" says what it is for, not what it is, so it is left
   out: "hand grinder for espresso" is a hand grinder;
3. "or", "and" and "plus" join two kinds: "cast iron or carbon steel pan" is about cast iron and carbon steel;
4. words about price or quality ("cheap", "good", "$50"), sizes and articles are left out: "cheap hand grinder"
   is a hand grinder;
5. the words of the requested product itself say nothing about its kind, so they are left out: in a frying pan
   request, "carbon steel pan" is carbon steel. A note left with no words ("cheap grinder" in a grinder request)
   names no kind: it is in no group, and stays a "what to look for" note for the answer.

Two notes are about the same kind when they are left with the same words, in any order, also when one writes as
one word what the other splits in two. A narrower kind ("thick carbon steel", "enameled cast iron") is a group of
its own, which names the broader kinds it is part of (`broader`), so the ranking can decide whether its notes
count for them.

What words can't do: kinds that mean the same in different words stay apart: "gyuto" and "Japanese chef knife",
"steel pan" (probably carbon steel) and "carbon steel pan", "kettle without extra features" and "boil-only kettle".
That needs an AI step, later.

Placing products: a product group is in a kind when the words of any of its names hold every word of the kind
(after steps 1 and 5): "Lodge cast iron skillet" is in cast iron, "Staub enameled cast iron" in both enameled
cast iron and cast iron. Most product names don't name their kind ("Lodge", "Hario Skerton"): placing those
needs a list of known products or the AI.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from engine.extract import CheckResult
from engine.group_products import ProductGroup
from engine.match_products import Aliases, join_split_words, known_aliases, plain_words

# Step 2: a word that starts what the kind is for or how it is used.
PURPOSE_WORDS = frozenset({
    "for", "to", "with", "instead", "as", "while", "before", "after", "on", "over", "under", "in", "at", "around",
    "from", "than", "when", "if", "that", "which", "by",
})
# Step 3: words that join two kinds.
JOINING_WORDS = frozenset({"or", "and", "plus", "vs", "versus"})
# Step 4: words about price, quality or size, and articles: they don't change the kind.
NOT_KIND_WORDS = frozenset({
    "a", "an", "the", "my", "your", "some", "any", "one",
    "cheap", "cheaper", "cheapest", "ultracheap", "inexpensive", "affordable", "expensive", "pricey", "budget",
    "very", "really", "good", "better", "best", "decent", "quality", "proper", "competent", "fancy", "nice", "great",
    "high", "highend", "low", "lowend", "lowcost", "cost", "mid", "midpriced", "priced", "entry", "entrylevel",
    "level", "regular", "basic", "simple", "more", "less", "most", "big", "bigger", "large", "larger", "small",
    "smaller", "single", "other", "same", "similar", "inch", "inches",
})
_HYPHEN_IN_WORD = re.compile(r"(?<=[^\W\d_])-(?=[^\W\d_])")


@dataclass(frozen=True)
class KindMention:
    """One note about a kind of product, in one comment: what grouping needs from a kept ExtractedNote.

    Not engine.rank.KindNote: the pipeline builds one of those per note and kind group it is in (kinds_of), with
    the group's key and name as kind_key and kind_name.
    """

    thread_id: str
    comment_id: str
    about: str  # the kind or feature, as the AI wrote it: "plastic-free kettle"
    stance: str  # recommend, warn or neutral


@dataclass
class KindGroup:
    """The notes about one kind of product, and the product groups that are of this kind."""

    key: str  # the kind's words: "carbon steel"
    name: str  # the kind as written most often: "carbon steel pan"
    notes: list[KindMention] = field(default_factory=list)
    product_keys: list[str] = field(default_factory=list)  # ProductGroup keys, alphabetical
    broader: list[str] = field(default_factory=list)  # keys of the broader kinds this one is part of

    @property
    def stances(self) -> Counter:
        return Counter(n.stance for n in self.notes)


def notes_from_checked(checked: dict[str, CheckResult]) -> list[KindMention]:
    """The kept notes of checked extractions ({thread id: CheckResult}, from engine.extract.load_checked)."""
    return [
        KindMention(thread_id, n.comment_id, n.about, n.stance)
        for thread_id, result in checked.items()
        for n in result.kept_notes
    ]


def kinds_of(groups: list[KindGroup]) -> dict[KindMention, list[KindGroup]]:
    """Each note's kind groups (usually one; two for "cast iron or carbon steel"). Notes naming no kind are left out."""
    found: dict[KindMention, list[KindGroup]] = defaultdict(list)
    for g in groups:
        for n in g.notes:
            found[n].append(g)
    return dict(found)


def placements(groups: list[KindGroup]) -> dict[str, list[str]]:
    """Which products belong to which kind, {kind key: [product keys]}, as engine.rank.rank_products takes it."""
    return {g.key: list(g.product_keys) for g in groups}


def group_kinds(notes: list[KindMention], products: list[ProductGroup], category: str, product_type: str = "",
                aliases: dict[str, Aliases] | None = None) -> list[KindGroup]:
    """The notes of one request grouped by kind, biggest first (then by key), each with the products placed in it.

    `category` and `product_type` are the request's ("kitchen", "frying pan"). `aliases` is {category: known names
    of kinds}; by default, the "kinds" part of the shipped alias file.
    """
    known = (known_aliases("kinds") if aliases is None else aliases).get(category, {})
    type_words = set(_kind_words(product_type, known))
    items = [(n, words) for n in notes for words in kind_parts(n.about, product_type, known, type_words)]
    groups = [_make_group(members) for members in _same_kind_sets(items)]
    product_words = {p.key: _words_of_product(p, known) for p in products}
    for g in groups:
        kind = set(g.key.split())
        g.product_keys = sorted(key for key, words in product_words.items() if kind <= words)
        g.broader = sorted(h.key for h in groups if set(h.key.split()) < kind)
    return sorted(groups, key=lambda g: (-len(g.notes), g.key))


def kind_parts(about: str, product_type: str, aliases: Aliases, type_words: set[str] | None = None) -> list[list[str]]:
    """The kind words of a note, one list per kind it names (steps 1 to 5 of the module docstring)."""
    if type_words is None:
        type_words = set(_kind_words(product_type, aliases))
    words = _kind_words(about, aliases)
    cut = next((i for i, w in enumerate(words) if w in PURPOSE_WORDS), len(words))
    parts: list[list[str]] = [[]]
    for w in words[:cut]:
        if w in JOINING_WORDS:
            parts.append([])
        elif w not in NOT_KIND_WORDS and not any(ch.isdigit() for ch in w) and w not in type_words and w not in parts[-1]:
            parts[-1].append(w)
    return [part for part in parts if part]


def _kind_words(text: str, aliases: Aliases) -> list[str]:
    """Step 1: the words of a kind or a name, hyphens joined, plurals dropped, known names written out."""
    words = [_singular(w) for w in plain_words(_HYPHEN_IN_WORD.sub("", text))]
    return _write_out_anywhere(words, aliases)


def _singular(word: str) -> str:
    """A plural "s" dropped from words of 4 letters or more ("pans" as "pan"), but not from "glass", "plus" or "basis"."""
    if len(word) >= 4 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def _write_out_anywhere(words: list[str], aliases: Aliases) -> list[str]:
    """Every known name of a kind in the words written out ("teflon pan" -> nonstick pan), unless it already is
    ("stainless steel" stays as it is)."""
    shorts = sorted(aliases, key=len, reverse=True)
    result, i = [], 0
    while i < len(words):
        short = next((s for s in shorts if tuple(words[i:i + len(s)]) == s), None)
        full = aliases[short] if short else []
        if short is None or words[i:i + len(full)] == full:
            result.append(words[i])
            i += 1
        else:
            result.extend(full)
            i += len(short)
    return result


def _same_kind(a: list[str], b: list[str]) -> bool:
    """The same words, in any order, also when one writes as one word what the other splits in two."""
    joined_a = join_split_words(a, b)
    return set(joined_a) == set(join_split_words(b, joined_a))


def _same_kind_sets(items: list[tuple[KindMention, list[str]]]) -> list[list[tuple[KindMention, list[str]]]]:
    """The items split into sets of the same kind."""
    sets: list[list[tuple[KindMention, list[str]]]] = []
    for item in items:
        matching = [s for s in sets if any(_same_kind(item[1], other[1]) for other in s)]
        merged = [item] + [x for s in matching for x in s]
        sets = [s for s in sets if s not in matching] + [merged]
    return sets


def _make_group(members: list[tuple[KindMention, list[str]]]) -> KindGroup:
    """The kind written most often names the group (on a tie, the shortest, then alphabetically); its words are the key."""
    counts = Counter(n.about for n, _ in members)
    shown = min(counts, key=lambda about: (-counts[about], len(about), about))
    key_words = next(words for n, words in members if n.about == shown)
    notes = sorted({n for n, _ in members}, key=lambda n: (n.thread_id, n.comment_id, n.about))
    return KindGroup(key=" ".join(key_words), name=shown, notes=notes)


def _words_of_product(product: ProductGroup, aliases: Aliases) -> set[str]:
    """Every word of every name of a product group, read the way kinds are."""
    return {w for name in product.names for w in _kind_words(name, aliases)}
