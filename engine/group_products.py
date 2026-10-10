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
A name made only of filler words ("the one") names nothing: it is a loose group of its own.

The name shown: the most complete name (the most words) among the names written at least half as often as the
group's most written name; on a tie, the one written more often. So "Sunday Riley water cream" (once) beats
"Sunday Riley" (twice), but "Timemore C2 with titanium coated burrs" (once) doesn't beat "Timemore C2" (24 times).
Then, brand first: if another name of the group is that name with words added at its start ("1Zpresso JX Pro"
for "JX Pro"), the most often written of those is shown instead. Of the spellings of that name, one that says its
words as they are is shown ("House of Hur Weightless Sun Fluid", not "House of Hurr Weightless Sunscreen", which a
short name writes out), then the most complete as written ("The Ordinary" rather than "TO"), then the most common,
then one with capitals.

The key is the category and the words of the name shown, such as "skincare:cerave renewing sa cleanser". The
same mentions, in any order, give the same groups and keys.

Two more steps happen only when the name is shown to a shopper (engine/pipeline.py calls them; Noemi's decisions of
9 Oct 2026). Grouping itself keeps the name above.
- uk_name: the brand the UK knows a product by (config.UK_BRAND_NAMES): "Sage Smart Grinder Pro", not "Breville".
- brand_pick_name: a brand or line ranked as a pick says so: "Lodge (their cast iron skillets)".
"""

import re
from collections import Counter, defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field

from engine.config import BRAND_PICK_NAME, PRODUCT_TYPE_PLURALS, UK_BRAND_NAMES
from engine.extract import CheckResult
from engine.match_products import (
    Aliases, comparable, join_split_words, known_aliases, normalize_name, product_words, same_words,
)

# Words that never tell two products apart, so a loose name equal to a product's name but for them names that product
# (step 5): "Cetaphil gentle cleanser" is the Cetaphil Gentle Skin Cleanser, not its Gentle Foaming Cleanser.
UNTELLING_WORDS = frozenset({"skin"})


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
        ProductMention(thread_id, m.comment_id, m.product, m.category, m.stance, m.product_type)
        for thread_id, result in checked.items()
        for m in result.kept
    ]


def group_of(groups: list[ProductGroup]) -> dict[ProductMention, ProductGroup]:
    """Each mention's group, so the pipeline can give every mention its product key and shown name."""
    return {m: g for g in groups for m in g.mentions}


def group_products(mentions: list[ProductMention], aliases: dict[str, Aliases] | None = None) -> list[ProductGroup]:
    """The mentions gathered into product groups, biggest first (then by key).

    `aliases` is {category: known short names}; by default, the shipped list (engine/data/product_aliases.json).
    """
    aliases = known_aliases() if aliases is None else aliases
    by_category: dict[str, list[ProductMention]] = defaultdict(list)
    for m in mentions:
        by_category[m.category].append(m)
    groups = [g for category, ms in by_category.items() for g in _group_category(category, ms, aliases.get(category, {}))]
    return sorted(groups, key=lambda g: (-len(g.mentions), g.key))


Words = tuple[str, ...]


def _group_category(category: str, mentions: list[ProductMention], aliases: Aliases) -> list[ProductGroup]:
    """Steps 1 to 5 of the module docstring, for the mentions of one category."""
    by_words: dict[Words, list[ProductMention]] = defaultdict(list)  # step 1
    nameless: dict[str, list[ProductMention]] = defaultdict(list)  # filler words only
    for m in mentions:
        words = tuple(product_words(m.product, aliases))
        if words:
            by_words[words].append(m)
        else:
            nameless[m.product.strip().lower()].append(m)

    names = sorted(by_words)
    matches = {w: [v for v in names if v != w and same_words(list(w), list(v))] for w in names}  # step 2
    spelling = {w: w for w in names}  # each name -> the first of its spellings
    for w in names:
        for v in matches[w]:
            if not _more_words(v, w) and not _more_words(w, v):
                _join(spelling, w, v)
    spellings: dict[Words, list[Words]] = defaultdict(list)
    for w in names:
        spellings[_root(spelling, w)].append(w)

    longer = {s: {v for w in ws for v in matches[w] if _more_words(v, w)} for s, ws in spellings.items()}
    loose = {s for s in spellings if _fits_two_products(longer[s])}  # step 3
    parent = {s: s for s in spellings}
    for s in spellings:  # step 4
        if s not in loose:
            for v in longer[s]:
                if _root(spelling, v) not in loose:
                    _join(parent, s, _root(spelling, v))
    # Step 5, longer loose names first, so a shorter one sees whether each loose name it fits found its product: one
    # still loose counts as a product of its own, since it fits several.
    for s in sorted(loose, key=lambda s: (-len(s), s)):
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
    groups = [_make_group(category, {w: by_words[w] for s in ss for w in spellings[s]}, loose=all(s in loose for s in ss))
              for ss in families.values()]
    groups += [ProductGroup(f"{category}:{name}", ms[0].product, category, list(ms), loose=True)
               for name, ms in nameless.items()]
    return groups


def _fits_two_products(longer: set[Words]) -> bool:
    """Whether a set of longer names a name matches holds two that don't match each other: two products."""
    ordered = sorted(longer)
    return any(not same_words(list(a), list(b)) for i, a in enumerate(ordered) for b in ordered[i + 1:])


def _more_words(a: Words, b: Words) -> bool:
    """Whether name a has more words than name b, once made ready to compare (engine.match_products.comparable: words
    one writes apart and the other as one joined, an "and" only one writes dropped)."""
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

def _make_group(category: str, by_words: dict[Words, list[ProductMention]], loose: bool) -> ProductGroup:
    shown = _shown_words(by_words)
    mentions = sorted((m for ms in by_words.values() for m in ms), key=lambda m: (m.thread_id, m.comment_id, m.product))
    return ProductGroup(f"{category}:{' '.join(shown)}", _shown_spelling(by_words[shown], shown), category, mentions, loose)


def _shown_words(by_words: dict[Words, list[ProductMention]]) -> Words:
    """The most complete of the names written often, or a name that adds its brand at its start."""
    most = max(len(ms) for ms in by_words.values())
    often = [w for w in by_words if 2 * len(by_words[w]) >= most]
    main = max(sorted(often), key=lambda w: (len(w), len(by_words[w])))
    with_brand = [w for w in by_words if _adds_words_at_start(w, main)]
    return max(sorted(with_brand), key=lambda w: (len(by_words[w]), len(w))) if with_brand else main


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
    "Breville Smart Grinder Pro" -> "Sage Smart Grinder Pro" (decision 12)."""
    for brand, uk_brand in shown.items():
        name = re.sub(rf"(?<!\w){re.escape(brand)}(?!\w)", lambda _: uk_brand, name, flags=re.IGNORECASE)
    return name


def brand_pick_name(brand: str, product_type: str) -> str:
    """The name a brand or line is shown under when it is ranked as a pick: "Lodge (their cast iron skillets)"
    (decision 9; the wording is config.BRAND_PICK_NAME). A name that already says the type is shown as it is:
    "CeraVe cleanser", not "CeraVe cleanser (their cleansers)" (Noemi, 9 Oct 2026)."""
    from engine.sources import mentions_product

    if mentions_product(brand, product_type):
        return brand
    return BRAND_PICK_NAME.format(brand=brand, products=PRODUCT_TYPE_PLURALS.get(product_type, f"{product_type}s"))
