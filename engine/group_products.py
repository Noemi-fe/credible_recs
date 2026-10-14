"""Module 4, grouping: gathers every mention of one product, across threads, under one name.

The AI lists each product as the comment names it, so one product shows up under many names ("CeraVe SA",
"cerave sa cleanser", "CeraVe Renewing SA Cleanser"). group_products turns a request's mentions into product
groups: one per product, with a key, the name to show, the category and every mention of it.

How names are grouped, one category at a time (a skincare name never joins a kitchen one):
1. Names with the same words (engine.match_products.product_words: case, punctuation and known short names
   aside) are one name: "CeraVe" and "cerave".
2. Each pair of names is compared with the matcher's rules (engine.match_products.same_words). Names that match
   with as many words as each other are spellings of one name ("Lodge pans" and "lodge pan", "SoonJung" and
   "Soon Jung"): they are judged together from here on.
3. The catch: matching is not transitive. "CeraVe" matches "CeraVe SA Cleanser" and "CeraVe Hydrating
   Cleanser", which don't match each other, so joining every matching pair would chain all of a brand's products
   into one group. So a name is loose when it (or another spelling of it) matches two longer names that don't
   match each other: it fits more than one product ("CeraVe", "CeraVe cleanser", "Lodge skillet" next to a 10
   and a 12 inch skillet).
4. The other names, the specific ones, are joined pair by pair: two specific names that match are one product.
5. A loose name joins a product only when everything it matches is one product: the specific names it matches, and
   the loose names it matches that joined a product (longer loose names are judged first). A loose name it matches
   that stays loose counts as another product ("MM" next to an "MM Factory pan" that fits two pans, and an MM
   Factory lid, joins neither; 10 Oct 2026). When it matches more than one product, it joins the one that has its
   very name but for a word that never tells products apart, if exactly one does (UNTELLING_WORDS, "skin":
   "Cetaphil gentle cleanser" is the Gentle Skin Cleanser, not the Gentle Foaming Cleanser; 10 Oct 2026).
   Otherwise it stays a group of its own, with its other spellings, flagged loose (a brand or product line, not one
   product). A loose name never joins two products together.
A name made only of filler words ("the one") names nothing: it is a loose group of its own. A name of one word and a
kind of product without its brand ("Chai shampoo") matches a longer name only when that is it with a brand before it,
or when its word is written alone as a name here, so a brand ("Ballarini pans" in "Zwilling/Ballarini non-stick pans"):
a flavour many makers use never joins another maker's product (engine.match_products.held_back_word, 13 Oct 2026).

In one request (13 Oct 2026, from reading the day's answers; engine/pipeline.py gives the requested type): a name made
of another name and the type's words, at its end ("Fellow kettle" in an electric kettle request, "Torriden balm" in a
lip balm one, "Vichy shampoos"), says no more than that other name, its base ("Fellow"), in this type. b06 had shown
"Fellow kettle" as a pick next to "Fellow Stagg EKG": no Fellow model's name says "kettle", so it had fitted no product.
a. It also fits, as its base, the longer names of products of the type, as the AI typed most of their mentions (or,
   with no type given, whose names say no other kind of product, engine.match_products.KIND_WORDS): "Fellow kettle"
   fits the Stagg EKG and the Corvo EKG, so it is loose, Fellow's kettle line; "Fellow Stag kettle" fits the Stagg EKG
   alone and joins it; "TO sunscreen" never fits The Ordinary's lactic acid (an exfoliant), nor its own plural. A name
   that fits one product only this way joins it only when its base isn't a brand here, the start of two or more
   products' names: "our place pan" fitted Our Place's titanium cookware alone (its Always Pan Pro has a model word
   the brand never fits), though its writer's pan was ceramic, so it joins nothing.
b. A brand (or line) written alone and with the type's words ("Tiger" and "Tiger rice cooker") is its line whenever it
   fits a model of the type, even one alone: writers name the brand's products of the type. (A brand alone, with no
   such name, still joins its one product, as in step 5.) "Suave Naturals ocean breeze" fits no other shampoo than its
   own "Suave Naturals ocean breeze shampoo", so that stays a product, apart from the line's conditioner.
c. Loose groups whose names, without the type's words, are written alike are one line ("Torriden" and "Torriden balm",
   which a lip balm answer had listed twice on its skip list), shown as the brand, by a name without the type's words
   ("Fellow", which the answer shows as "Fellow electric kettle line"; never "cast iron Lodge"). A product is shown by
   a name that names it, not by its brand and the type ("Lancôme Génifique", not "Lancome eye creams").
Without a requested type (the whole library, engine/matching_eval.py) names are grouped by these words alone.

The name shown: the most complete name (the most words) among the names written at least half as often as the
group's most written name; on a tie, the one written more often. So "Sunday Riley water cream" (once) beats
"Sunday Riley" (twice), but "Timemore C2 with titanium coated burrs" (once) doesn't beat "Timemore C2" (24 times).
Then, brand first: if another name of the group is that name with words added at its start ("1Zpresso JX Pro"
for "JX Pro"), the most often written of those is shown instead. If none is, but a longer name has it after a brand
(words written on their own as a name in the same category, such as "Fellow"), the brand goes before it: "Fellow
Stagg" for a group mostly written "Stagg" that also holds "Fellow Stagg EKG" (10 Oct 2026). A size or a colour before
it ('12"') is never written alone, so it is never taken for a brand. When the brand and the name together are another
group's name, the group's own shortest name that starts with both is shown ("Fellow Stagg EKG"), so no two groups
share a name or a key. Of the spellings of that name, one that says its
words as they are is shown ("House of Hur Weightless Sun Fluid", not "House of Hurr Weightless Sunscreen", which a
short name writes out), then the most complete as written ("The Ordinary" rather than "TO"), then the most common,
then one with capitals.

The key is the category and the words of the name shown, such as "skincare:cerave renewing sa cleanser". The
same mentions, in any order, give the same groups and keys.

Two more steps happen only when the name is shown to a shopper (engine/pipeline.py calls them; Noemi's decisions of
9 Oct 2026). Grouping itself keeps the name above.
- uk_name: the brand the UK knows a product by (config.UK_BRAND_NAMES): "Sage Smart Grinder Pro", not "Breville".
- brand_pick_name: a brand or line ranked as a pick says so: "Lodge cast iron skillet line" (Noemi's wording of
  12 Oct 2026; it was "Lodge (their cast iron skillets)").
"""

import re
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache

from engine.config import BRAND_PICK_NAME, PRODUCT_TYPE_PLURALS, PRODUCT_TYPE_SHOWN, UK_BRAND_NAMES
from engine.extract import CheckResult
from engine.memo import register
from engine.match_products import (
    KIND_WORDS, Aliases, _features, comparable, held_back_word, join_split_words, known_aliases,
    match_candidates_and_open, normalize_name, own_words, product_words, same_words, same_words_looked_at, written_alike,
)

# Words that never tell two products apart, so a loose name equal to a product's name but for them names that product
# (step 5): "Cetaphil gentle cleanser" is the Cetaphil Gentle Skin Cleanser, not its Gentle Foaming Cleanser.
UNTELLING_WORDS = frozenset({"skin"})
# Words at a brand pick's name's end that say nothing about it ("aveeno one", "Haden brand"): left out of its shown name.
TRAILING_FILLER = frozenset({"one", "ones", "brand"})


@dataclass(frozen=True)
class ProductMention:
    """One product named in one comment: what grouping needs from a kept ExtractedMention."""

    thread_id: str
    comment_id: str
    product: str  # the name as the AI wrote it
    category: str  # skincare, kitchen or other
    stance: str  # recommend, warn or neutral
    # The type the AI gave the product (instructions v6, such as "electric kettle"); None in older extractions.
    # Extra information, not part of which mention this is: compare=False keeps it out of equality and hashing, so
    # a mention looked up without its type (as the pipeline does) still finds its group.
    product_type: str | None = field(default=None, compare=False)
    # The mention's supporting quote (checked word for word at extraction), extra information like the type: the
    # pipeline reads it to tell whether a mention the AI typed as another type still names the requested one (13 Oct
    # 2026). "" when not given.
    quote: str = field(default="", compare=False)


@dataclass
class ProductGroup:
    """Every mention of one product, across threads."""

    key: str  # the category and the shown name's words: "skincare:cerave renewing sa cleanser"
    name: str  # the name to show
    category: str
    mentions: list[ProductMention] = field(default_factory=list)
    # True when the name is a brand or product line that fits more than one product ("CeraVe", "Lodge cast iron"):
    # its mentions can't count for any one product.
    loose: bool = False

    @property
    def names(self) -> Counter:
        """How often each name was written."""
        return Counter(m.product for m in self.mentions)

    @property
    def stances(self) -> Counter:
        """How many mentions recommend, warn or are neutral."""
        return Counter(m.stance for m in self.mentions)


def mentions_from_checked(checked: dict[str, CheckResult]) -> list[ProductMention]:
    """The kept mentions of checked extractions ({thread id: CheckResult}, from engine.extract.load_checked)."""
    return [
        ProductMention(thread_id, m.comment_id, m.product, m.category, m.stance, m.product_type, m.quote)
        for thread_id, result in checked.items()
        for m in result.kept
    ]


Words = tuple[str, ...]


def group_of(groups: list[ProductGroup]) -> dict[ProductMention, ProductGroup]:
    """Each mention's group, so the pipeline can give every mention its product key and shown name."""
    return {m: g for g in groups for m in g.mentions}


def group_products(mentions: list[ProductMention], aliases: dict[str, Aliases] | None = None,
                   product_type: str | None = None, index: Mapping[str, "NameIndex"] | None = None) -> list[ProductGroup]:
    """The mentions gathered into product groups, biggest first (then by key).

    `aliases` is {category: known short names}; by default, the shipped list (engine/data/product_aliases.json).
    `product_type`: the requested type of product, when grouping for one request (engine/pipeline.py): a name made of
    another name and that type's words then names what that name names, in that type (the module docstring's "In one
    request"). None groups names alone, as for the whole library. `index`: {category: NameIndex} of the library the
    mentions come from (library_name_index, with the same short names), whose pairs of names stand in for working
    them out again; the groups are the same with it or without.
    """
    aliases = known_aliases() if aliases is None else aliases
    by_category: dict[str, list[ProductMention]] = defaultdict(list)
    for m in mentions:
        by_category[m.category].append(m)
    groups = [g for category, ms in by_category.items()
              for g in _group_category(category, ms, aliases.get(category, {}), product_type,
                                       (index or {}).get(category))]
    return sorted(groups, key=lambda g: (-len(g.mentions), g.key))


class NameIndex:
    """The pairs of names the quick look leaves (engine.match_products.match_candidates_and_open), among all the names
    of one category of a library's mentions and their names without each product type's words (their bases): worked
    out once for the library, so a request's grouping takes its own names' pairs from it instead of working them out
    again (latency, 13 Oct 2026: that was half of grouping, and grouping a third of a fresh answer)."""

    def __init__(self, names: Iterable[Words]):
        self.candidates, self.open_pairs = match_candidates_and_open(sorted(set(names)))

    def among(self, names: list[Words]) -> tuple[dict[Words, set[Words]], set[tuple[Words, Words]]] | None:
        """match_candidates_and_open(names), from the index: the candidates among `names` (and the pairs, in order,
        the quick look leaves: the index's, a pair of them is asked about only when both are among `names`); None when
        a name isn't in the index (a type the open model named has bases of its own)."""
        candidates = self.candidates
        if not all(name in candidates for name in names):
            return None
        among = set(names)
        return {name: candidates[name] & among for name in dict.fromkeys(names)}, self.open_pairs


def library_name_index(mentions: Iterable[ProductMention],
                       aliases: dict[str, Aliases] | None = None) -> dict[str, NameIndex]:
    """{category: NameIndex} for a library's mentions: every name, as grouping reads it (product_words, with these
    short names: the shipped list by default), and its base in each of module 1's first product types and in each type
    of the taxonomy (engine/data/product_types.json) of the name's own category (14 Oct 2026: its base in all 351 of
    the taxonomy's types had made the index seven times slower). A request of a taxonomy type grouping the names of
    another category works their pairs out itself (NameIndex.among: a base not in the index), as for a type the open
    model named."""
    from engine.query import FIRST_PRODUCT_TYPES, PRODUCT_TYPES  # here: engine.query's own imports reach this module's

    aliases = known_aliases() if aliases is None else aliases
    names: dict[str, set[Words]] = defaultdict(set)
    for m in mentions:
        words = tuple(product_words(m.product, aliases.get(m.category, {})))
        if words:
            names[m.category].add(words)
    first = [_type_words(p.name) for p in FIRST_PRODUCT_TYPES]
    more: dict[str, list[frozenset[str]]] = defaultdict(list)
    for p in PRODUCT_TYPES[len(FIRST_PRODUCT_TYPES):]:
        more[p.category].append(_type_words(p.name))
    return {category: NameIndex(own | {base for words in own for type_words in first + more[category]
                                       if (base := _without_type_words(words, type_words))})
            for category, own in names.items()}


def _group_category(category: str, mentions: list[ProductMention], aliases: Aliases,
                    product_type: str | None = None, index: "NameIndex | None" = None) -> list[ProductGroup]:
    """Steps 1 to 5 of the module docstring, for the mentions of one category; with the requested `product_type`, the
    steps of "In one request" too. `index`: the category's NameIndex, for the pairs of names that could match."""
    type_words = _type_words(product_type)
    by_words: dict[Words, list[ProductMention]] = defaultdict(list)  # step 1
    nameless: dict[str, list[ProductMention]] = defaultdict(list)  # filler words only
    for m in mentions:
        words = tuple(product_words(m.product, aliases))
        if words:
            by_words[words].append(m)
        else:
            nameless[m.product.strip().lower()].append(m)

    names = sorted(by_words)
    # Words written alone as a name: brands, or lines writers name on their own ("Ballarini"). A name of one such word
    # and a kind of product matches a longer name that holds it later ("Zwilling/Ballarini non-stick pans"), as a
    # flavour wouldn't ("Chai shampoo"; engine.match_products.held_back_word, 13 Oct 2026).
    alone = {w[0] for w in names if len(w) == 1}
    # The name each name is, without the requested type's words at its end: "fellow" for "fellow kettle" in a kettle
    # request (None when it has none, or nothing else).
    bases = {w: _without_type_words(w, type_words) for w in names} if type_words else {}
    # Step 2. Only pairs that could match are compared (engine.match_products.match_candidates; latency, 12 Oct 2026):
    # every pair that matches is among them, in the same order as before.
    universe = names + sorted({b for b in bases.values() if b})
    found = index.among(universe) if index is not None else None
    candidates, open_pairs = found if found is not None else match_candidates_and_open(universe)
    matches = {w: [v for v in sorted(candidates[w]) if v in by_words and _matching(w, v, alone, open_pairs)]
               for w in names}
    spelling = {w: w for w in names}  # each name -> the first of its spellings
    for w in names:
        for v in matches[w]:
            if not _more_words(v, w) and not _more_words(w, v):
                _join(spelling, w, v)
    spellings: dict[Words, list[Words]] = defaultdict(list)
    for w in names:
        spellings[_root(spelling, w)].append(w)

    # In one request: a name with the type's words fits, as its base, the longer names of products of the type (a.).
    # Never another way of writing the same brand and type ("TO sunscreens" for "TO sunscreen"), nor its own spellings.
    fits_as_base = {w: {v for v in sorted(candidates[base]) if v in by_words and v != w and _could_start(base, v)
                        and _matching(base, v, alone, open_pairs) and _more_words(v, base)
                        and _of_the_type(v, by_words[v], product_type, type_words)
                        and not (bases.get(v) and _alike(bases[v], base))}
                    for w, base in bases.items() if base}
    plainly_longer = {s: {v for w in ws for v in matches[w] if _more_words(v, w)} for s, ws in spellings.items()}
    longer = {s: plainly_longer[s] | {v for w in ws for v in fits_as_base.get(w, ()) if _root(spelling, v) != s}
              for s, ws in spellings.items()}
    # What a name may join in step 4. A base that starts two or more other names here is a brand or a line ("Our Place"
    # before "Our Place titanium cookware" and "Our Place Titanium Always Pan Pro"): its name with the type's words that
    # fits one of them alone fits it by chance (the others are named another way), so it joins nothing by that alone.
    brand_bases = _brand_bases(bases, by_words)
    joinable = {s: plainly_longer[s] | {v for w in ws if bases.get(w) not in brand_bases
                                        for v in fits_as_base.get(w, ()) if _root(spelling, v) != s}
                for s, ws in spellings.items()}
    loose = {s for s in spellings if _fits_two_products(longer[s])}  # step 3
    # In one request, a brand written alone and with the type's words is its line (b.): loose, joining no model in 5.
    lines = (_lines_of_the_type(spellings, spelling, longer, bases, by_words, product_type, candidates) if type_words
             else set())
    loose |= lines
    parent = {s: s for s in spellings}
    for s in spellings:  # step 4
        if s not in loose:
            for v in joinable[s]:
                if _root(spelling, v) not in loose:
                    _join(parent, s, _root(spelling, v))
    # Step 5, longer loose names first, so a shorter one sees whether each loose name it fits found its product: one
    # still loose counts as a product of its own, since it fits several.
    for s in sorted(loose - lines, key=lambda s: (-len(s), s)):
        products = {_root(parent, _root(spelling, v)) for v in longer[s]}
        if len(products) > 1:  # more than one: the one it names but for words like "skin", if there is exactly one
            named = [v for v in longer[s] if _root(spelling, v) not in loose
                     and any(_equal_but_untelling(v, w) for w in spellings[s])]
            products = {_root(parent, _root(spelling, v)) for v in named}
        if len(products) == 1:
            _join(parent, products.pop(), s)

    families: dict[Words, list[Words]] = defaultdict(list)  # each group's root -> the names judged together in it
    for s in spellings:
        families[_root(parent, s)].append(s)
    if type_words:  # in one request, a brand's lines with and without the type's words are one line
        families = _one_line_per_base(families, loose, spellings, bases)
    members = [({w: by_words[w] for s in ss for w in spellings[s]}, all(s in loose for s in ss)) for ss in families.values()]
    shown = [_shown_words(own if not type_words else _without_the_type(own, type_words) if is_loose
                          else _without_brand_and_type(own, bases))
             for own, is_loose in members]
    taken = set(by_words) | set(shown)  # names no group may take as its brand-first name: they are names already
    groups = []
    for (own, is_loose), words in zip(members, shown):
        with_brand = _with_brand_before(words, own, by_words, taken)
        if with_brand:
            taken.add(with_brand[0])
        groups.append(_make_group(category, own, is_loose, with_brand or (words, _shown_spelling(own[words], words))))
    groups += [ProductGroup(f"{category}:{name}", ms[0].product, category, list(ms), loose=True)
               for name, ms in nameless.items()]
    return groups


def _matching(w: Words, v: Words, alone: set[str], open_pairs: set[tuple[Words, Words]]) -> bool:
    """Whether two names match (engine.match_products.same_words), or would but for a one-word name without its brand
    whose word is written alone as a name here (held_back_word): "Ballarini pans" and "Zwilling/Ballarini pans". Only
    a name whose one word besides its kinds is written alone is asked about (latency, 13 Oct 2026). A pair the quick
    look rules out (engine.match_products._cannot_match: 9 pairs in 10) is neither: both need every word of the
    shorter name found in the longer one. `open_pairs` are the pairs (in order) of the names' candidates the quick look
    leaves (engine.match_products.match_candidates_and_open): (w, v) is one of the candidates."""
    if (w, v) not in open_pairs:
        return False
    if same_words_looked_at(w, v):
        return True
    return any(len(own) == 1 and own[0] in alone and own[0] in other
               for own, other in ((_own_words(w), v), (_own_words(v), w))) and (
        held_back_word(list(w), list(v)) in alone)


_OWN_WORDS: dict[Words, list[str]] = {}  # a name's words -> its words besides its kinds of product (own_words)
register(_OWN_WORDS.clear)


def _own_words(words: Words) -> list[str]:
    """engine.match_products.own_words, worked out once per name (latency, 13 Oct 2026). Never changed by a caller."""
    found = _OWN_WORDS.get(words)
    if found is None:
        if len(_OWN_WORDS) >= 200_000:
            _OWN_WORDS.clear()
        found = _OWN_WORDS[words] = own_words(list(words))
    return found


# --- In one request: a name with the requested type's words (13 Oct 2026) ---

def _could_start(base: Words, v: Words) -> bool:
    """A quick no before the matcher: a one-word base (a brand, "fellow") matches only names it starts, maybe with a
    slip; longer bases are left to the matcher (latency, 13 Oct 2026)."""
    return len(base) > 1 or bool(v) and (v[0] == base[0] or v[0][:1] == base[0][:1])

def _type_words(product_type: str | None) -> frozenset[str]:
    """The words of a requested type of product and of its plural: electric, kettle, kettles."""
    if not product_type:
        return frozenset()
    return frozenset(normalize_name(product_type)) | frozenset(normalize_name(plural(product_type)))


@lru_cache(maxsize=65536)
def _is_type_word(word: str, type_words: frozenset[str]) -> bool:
    """Whether a word is one of the type's words, maybe with a spelling slip ("moisturizer" for "moisturiser")."""
    return word in type_words or any(written_alike([word], [t]) for t in type_words)


@lru_cache(maxsize=65536)
def _alike(a: Words, b: Words) -> bool:
    """engine.match_products.written_alike, remembered (latency, 13 Oct 2026: a big request asks it of the same names
    many times)."""
    return a == b or written_alike(list(a), list(b))


for _remembered in (_is_type_word, _alike):
    register(_remembered.cache_clear)  # engine.memo.forget_all empties them


def _without_type_words(words: Words, type_words: frozenset[str]) -> Words | None:
    """A name without the type's words at its end ("fellow kettle" -> fellow), or None when it has none there, or
    nothing else that names something."""
    end = len(words)
    while end and _is_type_word(words[end - 1], type_words):
        end -= 1
    base = words[:end]
    if end == len(words) or not base or not any(any(ch.isalpha() for ch in w) for w in base):
        return None
    return base


def _of_the_type(words: Words, mentions: list[ProductMention], product_type: str, type_words: frozenset[str]) -> bool:
    """Whether a name's product can be of the requested type: as the AI typed most of its mentions ("electric kettle"
    for "Fellow Corvo EKG"; a "basket air fryer" is an air fryer), and with no type given (older extractions), when its
    name says no other kind of product (_says_another_kind). "The Ordinary Lactic Acid", an exfoliant, is no product a
    "TO sunscreen" can mean; a "Cetaphil Moisturising Cream" the AI typed as a moisturiser is one a "Cetaphil
    moisturizer" can."""
    types = Counter(m.product_type.strip().lower() for m in mentions if m.product_type)
    if not types:
        return not _says_another_kind(words, type_words)
    most = max(types.values())
    wanted = product_type.strip().lower()
    return any(t == wanted or t.endswith(" " + wanted) for t, n in types.items() if n == most)


def _says_another_kind(words: Words, type_words: frozenset[str]) -> bool:
    """Whether a name ends in a word naming another kind of product than the type's (engine.match_products.KIND_WORDS):
    in a shampoo request "Suave Naturals ocean breeze conditioner" does; "Fellow Stagg EKG" (no kind) and "Shun chef's
    knife" in a chef knife request (the type's own word) don't."""
    last = words[-1]
    return (last in KIND_WORDS or last.removesuffix("s") in KIND_WORDS) and not _is_type_word(last, type_words)


def _brand_bases(bases: dict[Words, Words | None], by_words: dict[Words, list[ProductMention]]) -> set[Words]:
    """The bases (names without the type's words) that start the names of two or more products here (two names that
    don't match each other), not counting names of the same base and the type's words: brands or lines ("our place"
    before "our place titanium cookware" and "our place titanium always pan pro"), not one product's name ("suave
    coconut"; "ole henriksen peptide" before two spellings of its lip treatment)."""
    by_first: dict[str, list[Words]] = defaultdict(list)
    for v in by_words:
        by_first[v[0]].append(v)
    found = set()
    for base in {b for b in bases.values() if b}:
        others = [v for v in by_first.get(base[0], ()) if len(v) > len(base) and _alike(v[:len(base)], base)
                  and not (bases.get(v) and _alike(bases[v], base))]
        if len(others) >= 2 and _fits_two_products(set(others)):
            found.add(base)
    return found


def _lines_of_the_type(spellings: dict[Words, list[Words]], spelling: dict[Words, Words],
                       longer: dict[Words, set[Words]], bases: dict[Words, Words | None],
                       by_words: dict[Words, list[ProductMention]], product_type: str,
                       candidates: dict[Words, set[Words]]) -> set[Words]:
    """The spellings of a brand (or line) written alone and with the type's words ("Tiger" and "Tiger rice cooker" in a
    rice cooker request), when it fits at least one model of that type: writers who name a brand both ways speak of its
    line, so it is a line even when one model alone is named (it would otherwise join that model, as a brand alone
    joins its one product). A model of the type is the name with words after it, of that type by the AI's types for its
    mentions or, with none, by its name saying no other kind of product ("Suave Naturals ocean breeze conditioner" isn't
    one in a shampoo request; "Neutrogena T-Gel", the brand before "T-Gel", is T-Gel itself, not a model of it)."""
    type_words = _type_words(product_type)
    with_base: dict[Words, list[Words]] = defaultdict(list)  # a base -> the names that are it and the type's words
    for v, base in bases.items():
        if base:
            with_base[base].append(v)
    found = set()
    for s, ws in spellings.items():
        # Bases written alike to a name are among its match candidates (engine.match_products.match_candidates).
        typed_forms = {_root(spelling, v) for w in ws for base in {w} | candidates.get(w, set()) if base in with_base
                       and _alike(base, w) for v in with_base[base]}
        if not typed_forms:
            continue
        # A model is the name with words after it ("Tiger 1 button"), not before ("Neutrogena T-Gel" is T-Gel itself).
        models = [v for v in longer[s] if _root(spelling, v) not in typed_forms
                  and any(len(v) > len(w) and _alike(v[:len(w)], w) for w in ws)
                  and not (bases.get(v) and any(_alike(bases[v], w) for w in ws))
                  and _of_the_type(v, by_words[v], product_type, type_words)]
        if models:
            found |= {s} | typed_forms
    return found


def _one_line_per_base(families: dict[Words, list[Words]], loose: set[Words], spellings: dict[Words, list[Words]],
                       bases: dict[Words, Words | None]) -> dict[Words, list[Words]]:
    """The families, with every two loose ones whose names without the type's words are written alike joined: "Torriden"
    and "Torriden balm" in a lip balm request, "Fellow" and "Fellow kettle" in a kettle request."""
    lines = [root for root, ss in families.items() if all(s in loose for s in ss)]
    said = {root: {bases.get(w) or w for s in families[root] for w in spellings[s]} for root in lines}
    joined = {root: root for root in lines}
    for i, a in enumerate(lines):
        for b in lines[i + 1:]:
            if any(_alike(x, y) for x in said[a] for y in said[b]):
                _join(joined, a, b)
    merged: dict[Words, list[Words]] = defaultdict(list)
    for root, ss in families.items():
        merged[_root(joined, root) if root in joined else root] += ss
    return merged


def _without_the_type(own: dict[Words, list[ProductMention]],
                      type_words: frozenset[str]) -> dict[Words, list[ProductMention]]:
    """A loose group's names without any of the type's words, when it has any: the line is shown as its brand ("Fellow",
    then "Fellow electric kettle line" in the answer), not as one of its names with the type ("Fellow kettle", or
    "cast iron Lodge" in a cast iron skillet answer)."""
    plain = {w: ms for w, ms in own.items() if not any(_is_type_word(word, type_words) for word in w)}
    return plain or own


def _without_brand_and_type(own: dict[Words, list[ProductMention]],
                            bases: dict[Words, Words | None]) -> dict[Words, list[ProductMention]]:
    """A product's names without those that are its brand (the start of another of its names, written at least as
    often) and the type's words: the product is shown by what names it ("Lancôme Génifique"), not as "Lancome eye
    creams" (13 Oct 2026). A name written more often stays: "Clinique All About Eyes" (its "eyes" reads as the type's
    word) next to one "All About Eyes Rich"."""
    def brand_and_type(w: Words) -> bool:
        base = bases.get(w)
        return bool(base) and any(len(v) > len(base) and len(own[v]) >= len(own[w])
                                  and written_alike(list(v[:len(base)]), list(base))
                                  for v in own if v != w and not bases.get(v))
    kept = {w: ms for w, ms in own.items() if not brand_and_type(w)}
    return kept or own


def _fits_two_products(longer: set[Words]) -> bool:
    """Whether a set of longer names a name matches holds two that don't match each other: two products."""
    ordered = sorted(longer)
    return any(not same_words(a, b) for i, a in enumerate(ordered) for b in ordered[i + 1:])


def _more_words(a: Words, b: Words) -> bool:
    """Whether name a has more words than name b, once made ready to compare (engine.match_products.comparable: words
    one writes apart and the other as one joined, an "and" only one writes dropped). When comparable would change
    neither (no words to join, an "and" in both or neither), their own words are counted at once (latency, 13 Oct
    2026)."""
    features_a, features_b = _features(a), _features(b)
    if (features_a.has_and == features_b.has_and and features_a.runs.isdisjoint(features_b.words)
            and features_b.runs.isdisjoint(features_a.words)):
        return len(features_a.words) > len(features_b.words)
    words_a, words_b = comparable(list(a), list(b))
    return len(set(words_a)) > len(set(words_b))


def _equal_but_untelling(a: Words, b: Words) -> bool:
    """Whether two names have the same words once UNTELLING_WORDS are left out of both, and one of them has such a word:
    "cetaphil gentle skin cleanser" and "cetaphil gentle cleanser"."""
    kept_a, kept_b = [w for w in a if w not in UNTELLING_WORDS], [w for w in b if w not in UNTELLING_WORDS]
    if not kept_a or len(kept_a) + len(kept_b) == len(a) + len(b):
        return False
    words_a, words_b = comparable(kept_a, kept_b)
    return words_a == words_b


def _root(parent: dict[Words, Words], w: Words) -> Words:
    while parent[w] != w:
        w = parent[w]
    return w


def _join(parent: dict[Words, Words], a: Words, b: Words) -> None:
    """Puts two names in one group. The smaller root leads, so the result doesn't depend on the order of joins."""
    ra, rb = _root(parent, a), _root(parent, b)
    if ra != rb:
        parent[max(ra, rb)] = min(ra, rb)


# --- The name shown ---

def _make_group(category: str, by_words: dict[Words, list[ProductMention]], loose: bool,
                shown: tuple[Words, str]) -> ProductGroup:
    """The group of these names, shown as `shown`: (the words its key is made of, the name as it is shown)."""
    words, name = shown
    mentions = sorted((m for ms in by_words.values() for m in ms), key=lambda m: (m.thread_id, m.comment_id, m.product))
    return ProductGroup(f"{category}:{' '.join(words)}", name, category, mentions, loose)


def _shown_words(by_words: dict[Words, list[ProductMention]]) -> Words:
    """The most complete of the names written often, or a name that adds its brand at its start."""
    most = max(len(ms) for ms in by_words.values())
    often = [w for w in by_words if 2 * len(by_words[w]) >= most]
    main = max(sorted(often), key=lambda w: (len(w), len(by_words[w])))
    with_brand = [w for w in by_words if _adds_words_at_start(w, main)]
    return max(sorted(with_brand), key=lambda w: (len(by_words[w]), len(w))) if with_brand else main


def _with_brand_before(main: Words, own: dict[Words, list[ProductMention]], every_name: dict[Words, list[ProductMention]],
                       taken: set[Words]) -> tuple[Words, str] | None:
    """The brand-first name of a group whose name to show (`main`) has no brand before it in any of its names, but
    sits after a brand in a longer one: "Stagg", next to "Fellow Stagg EKG" (10 Oct 2026: the kettle answer showed a
    bare "Stagg"). Returns (its words, the name as shown), or None.

    The words before `main` are a brand only when they are a name of their own in the category (`every_name`, every
    name written: "Fellow" written alone), so a size or a colour ('12" De Buyer crepe pan') never is. Shown: the brand,
    then the name ("Fellow Stagg"), each spelled as written. When that is a name already (`taken`: another group's), the
    group's own shortest name that starts with both is shown instead ("Fellow Stagg EKG"), so two groups never share a
    name or a key. Among several brands, the one before the most mentions; then the first alphabetically.
    """
    if any(_adds_words_at_start(w, main) for w in own):  # a name already gives it: _shown_words showed that one
        return None
    found: Counter = Counter()
    for w, mentions in own.items():
        for i in range(1, len(w) - len(main) + 1):
            if w[i:i + len(main)] == main and w[:i] in every_name:
                found[w[:i]] += len(mentions)
    if not found:
        return None
    brand = max(sorted(found), key=lambda b: found[b])
    joined = brand + main
    if joined not in taken:
        return joined, f"{_shown_spelling(every_name[brand], brand)} {_shown_spelling(own[main], main)}"
    starting = sorted(w for w in own if w[:len(joined)] == joined)  # this group's names: never another's
    if not starting:
        return None
    longer = min(starting, key=lambda w: (len(w), -len(own[w])))
    return longer, _shown_spelling(own[longer], longer)


def _adds_words_at_start(longer: Words, name: Words) -> bool:
    """Whether `longer` is `name` with words added at its start: 1zpresso jx pro for jx pro."""
    a = join_split_words(list(longer), list(name))
    b = join_split_words(list(name), a)
    return len(a) > len(b) and a[-len(b):] == b


def _shown_spelling(mentions: list[ProductMention], words: Words) -> str:
    """Of the spellings of one name (`words`): one that says those words as they are, with no short name or slip to
    write out ("House of Hur Weightless Sun Fluid", not "House of Hurr Weightless Sunscreen"; 10 Oct 2026), then the
    most complete as written (letters and digits: "The Ordinary" rather than "TO"), then the most common, then one with
    capital letters (but not all capitals), then the first alphabetically."""
    counts = Counter(m.product for m in mentions)

    def preference(spelling: str):
        as_written = normalize_name(spelling)
        letters = len("".join(as_written))
        capitalised = spelling != spelling.lower() and spelling != spelling.upper()
        return tuple(as_written) == words, letters, counts[spelling], capitalised

    return max(sorted(counts), key=preference)


# --- The name shown to a shopper ---

def uk_name(name: str, shown: Mapping[str, str] = UK_BRAND_NAMES) -> str:
    """The name with each brand the UK knows by another name replaced, whole words only, in any case:
    "Breville Smart Grinder Pro" -> "Sage Smart Grinder Pro" (decision 12). With the shipped list of UK names, each
    name is worked out once (latency, 13 Oct 2026: answers ask it of the same names thousands of times)."""
    if shown is UK_BRAND_NAMES:
        found = _UK_NAMES.get(name)
        if found is None:
            if len(_UK_NAMES) >= 200_000:
                _UK_NAMES.clear()
            found = _UK_NAMES[name] = _uk_name(name, shown)
        return found
    return _uk_name(name, shown)


def _uk_name(name: str, shown: Mapping[str, str]) -> str:
    for brand, uk_brand in shown.items():
        name = re.sub(rf"(?<!\w){re.escape(brand)}(?!\w)", lambda _: uk_brand, name, flags=re.IGNORECASE)
    return name


_UK_NAMES: dict[str, str] = {}  # a name -> as the UK knows it, with the shipped list (uk_name)
register(_UK_NAMES.clear)


def brand_pick_name(brand: str, product_type: str) -> str:
    """The name a brand or line is shown under when it is ranked as a pick, the brand's whole line of the requested
    type: "Lodge cast iron skillet line", "Zojirushi rice cooker line" (decision 9; Noemi's wording of 12 Oct 2026,
    config.BRAND_PICK_NAME; it was "Lodge (their cast iron skillets)"). Every line is shown so, also when its name
    already holds the type (Noemi's decision 3 of 13 Oct 2026, replacing her rule of 9 Oct, which showed such a name as
    it is, "CeraVe cleanser"): the type is said once, so the shortest ending of the name that names the type
    (engine.sources.mentions_product: "conditioner", "kettle", "cast iron pan") gives way to it: "Davines conditioner
    line", "Sage electric kettle line", "Lodge cast iron skillet line". Nor does a name say part of its type twice: its
    last words that are the type's own words, or a plural or slip of them, give way to the type ("Zojirushi cooker" is
    the "Zojirushi rice cooker line"; 12 Oct 2026), and so do filler words at its end ("aveeno one", "Haden brand"; 13
    Oct 2026). A type is written as a name shows it (config.PRODUCT_TYPE_SHOWN): "Le Creuset Dutch oven line"."""
    from engine.sources import mentions_product

    type_words = [[word] for word in product_words(product_type)]
    words = brand.split()
    ending = next((k for k in range(1, len(words)) if mentions_product(" ".join(words[-k:]), product_type)), 0)
    if ending:
        words = words[:-ending]
    while len(words) > 1 and (words[-1].casefold() in TRAILING_FILLER
                              or any(written_alike(product_words(words[-1]), word) for word in type_words)):
        words.pop()
    return BRAND_PICK_NAME.format(brand=" ".join(words), product_type=PRODUCT_TYPE_SHOWN.get(product_type, product_type))


def plural(product_type: str) -> str:
    """A product type's plural: config.PRODUCT_TYPE_PLURALS for module 1's types ("chef knives", "Dutch ovens"), and
    English's usual rules for a type the open model named (11 Oct 2026): "dish brushes", "french presses", "air fryers"."""
    if product_type in PRODUCT_TYPE_PLURALS:
        return PRODUCT_TYPE_PLURALS[product_type]
    if re.search(r"(?:s|sh|ch|x|z)$", product_type):
        return product_type + "es"
    if re.search(r"[^aeiou]y$", product_type):
        return product_type[:-1] + "ies"
    return product_type + "s"
