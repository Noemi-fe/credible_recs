"""What the person asked for, and which comments talk about it (module 6, ranking; 9 Oct 2026).

"retinol for a beginner with sensitive skin" asks for more than a retinol: it asks for one that suits a beginner with
sensitive skin. A comment that talks about those needs ("I have sensitive skin and started slowly with Differin") tells
this shopper more than one that doesn't, whether it recommends the product or warns against it ("too harsh for
sensitive skin"). So the ranking counts such mentions more: the pipeline multiplies their weight by
config.NEED_MATCH_BOOST (off, 1.0, since 9 Oct 2026; see config). The minimum-evidence rule doesn't change: it counts credible mentions, not weights.

A request's needs (request_needs), in the order the request gives them:
- the needs of config.NEEDS that it names (for a haircare request, config.HAIR_NEEDS in place of the skin types, since
  14 Oct 2026: "greasy hair" is an oily scalp, "fine flat hair" fine hair): by name or by one of the need's words
  ("new to retinol" names "beginner", "doesn't leave a white cast" names "no white cast"); module 1's skin types
  ("sensitive") and must-haves ("fragrance-free"); a few other words of config.NEED_REQUEST_WORDS ("first chef's knife"
  names "beginner", "will last decades" names "lasting"); and module 1's "lasts 10+ years" (min_years), which names
  "lasting" too;
- every other specific word of the request (engine.sources.need_words: "pour-over", "PFAS", "winter"), each a need of
  its own, found in comments by that word alone. The words of config.NEED_IGNORED_WORDS ("leave", "cook", "burr")
  are left out: they are too common in comments to show anything;
- since 18 Oct 2026, words that ask the product's type for a checked fact (config.TYPE_ASKED_WORDS: "non toxic" asks a
  frying pan or a saucepan for PFAS-free) as one need named by what they ask, found by toxins and by PFAS, PTFE, PFOA
  and Teflon.
Since 14 Oct 2026 (the need-quality builder) a negation is never a need of its own ("isn't", "not", "no": engine.sources.
_STOPWORDS), and what a request asks a product not to do names the need it asks for (config.NEGATED_NEEDS): "a shampoo
that isn't drying" or "won't dry out my hair" names "not drying", and its "dry" names no other need (not dry hair). Hair
types written together before "hair" each name their need (config.HAIR_LIST_NEEDS): "fine oily hair" names fine hair
and an oily scalp, though "fine" alone is no word of fine hair ("it works fine").

A comment talks about a need (needs_met) when its own words (not quoted blocks: those are someone else's words) hold one
of the need's words, at the start of a word: a word beginning finds its longer forms ("sensitiv" finds "sensitive" and
"sensitivity"), and a phrase is found whole ("white cast", "white casts"). A request's own word is found the way
module 2 finds it in a thread title: "pour over" and "pourover" both find "pour-over" (engine.sources._title_has).
A mention with long-term use (module 5) also talks about "lasting": it describes long use. Hair types written together
count in comments and titles too ("my fine, oily hair", "thin/greasy hair").

A thread talks about a need (thread_needs, 14 Oct 2026) when its title or post does, the same way, unless its title
names another type of product and not the one asked for: the library's first reading reads such threads first
(engine.sources.LocalSource). A slimmed thread keeps no words of its post (engine/slim.py, Noemi's "Keep only comments
we use"): which of config's need words its post held were noted before they went (post_need_words, post_list_words),
and which of the words the engine knows (engine.slim.known_words: every checked request's words, the product types',
ingredients' and needs' own) it held as a request's own word is found (post_request_words), so it talks about those as
before; a request's word the engine didn't know then is looked for in its title only.
"""

import re
from dataclasses import dataclass, field
from functools import cache

from engine.config import (
    EVERYDAY_BRAND_WORDS, HAIR_LIST_NEEDS, HAIR_LIST_NOUNS, HAIR_LIST_WORDS, HAIR_NEEDS, INGREDIENT_FORM_WORDS,
    INGREDIENTS, NEED_COMMENT_WORDS, NEED_IGNORED_WORDS, NEED_LOOKALIKES, NEED_PHRASES, NEED_REQUEST_WORDS,
    NEED_SIZE_UNITS, NEED_VERB_LABELS, NEEDS, NEGATED_NEEDS, NEGATION_REACH, NEGATIONS, NO_HELP_LEADS,
    NO_HELP_PATTERNS, NO_HELP_POINTERS, REQUEST_WORD_SYNONYMS, TYPE_ASKED_LABEL, TYPE_ASKED_WORDS, TYPE_OTHER_NAMES,
    TYPE_SYNONYMS,
)
from engine.credibility import _own_words
from engine.ingredients import _whole as _whole_words
from engine.memo import Table
from engine.models import Thread
from engine.query import CATEGORY_HINTS, PRODUCT_TYPES, SKIN_TYPES, ParsedQuery, type_asked_spans
from engine.sources import _stem, _title_has, _title_words, need_words

LASTING = "lasting"  # the need that long-term use also speaks to


@dataclass(frozen=True)
class Need:
    """One thing the request asks for, and how to recognise a comment that talks about it."""

    name: str  # a need of config.NEEDS ("sensitive"), or a word of the request as typed ("pour-over")
    words: tuple[str, ...] = ()  # config.NEEDS's words for it; empty for a word of the request
    request_word: str | None = None  # a word of the request, as module 2 matches it ("pourover"); None otherwise
    # The words of config.HAIR_LIST_NEEDS that name it in hair types written together ("fine" in "fine oily hair").
    list_words: tuple[str, ...] = ()
    # How the answer names it, when not by its name: a word of two that make one need (config.NEED_PHRASES, 16 Oct
    # 2026) is named by both, as typed ("dark circles" for "dark" and for "circles"); None otherwise. Words only: it says
    # nothing of which comments talk about it, so it is no part of which need this is.
    label: str | None = field(default=None, compare=False)


def needs_of(category: str | None) -> dict[str, tuple[str, ...]]:
    """The needs a request of this category can name, with their words: config.NEEDS, and for haircare config.HAIR_NEEDS
    in place of the skin types (14 Oct 2026: "greasy hair" is an oily scalp, not oily skin)."""
    if category == "haircare":
        return {need: words for need, words in NEEDS.items() if need not in SKIN_TYPES} | HAIR_NEEDS
    return NEEDS


def request_needs(query: ParsedQuery) -> tuple[Need, ...]:
    """The needs the request names, in the order it names them (a need module 1 found but the words don't show, last).

    Nothing for a request module 1 didn't understand (a question or a polite no). They depend on the request alone, so
    they are worked out once per request, known by everything module 1 read in it (latency, 13 Oct 2026: an answer asks
    for them thousands of times, through engine.product_facts.request_asks).
    """
    if query.status != "ok":
        return ()
    key = query.model_dump_json()
    found = _REQUEST_NEEDS.get(key)
    if found is None:
        found = _REQUEST_NEEDS.keep(key, _request_needs(query))
    return found


_REQUEST_NEEDS = Table(limit=10_000)  # a request, as module 1 read it -> its needs
_NEEDS_MET = Table()  # (comment, needs, long-term use) -> the needs it talks about


def _request_needs(query: ParsedQuery) -> tuple[Need, ...]:
    needs = needs_of(query.category)
    found: dict[str, int] = {}  # need name -> where the request names it

    def name(need: str, at: int) -> None:
        if need in needs:
            found[need] = min(at, found.get(need, at))

    # What it asks a product not to do first (14 Oct 2026): those words name no other need ("dry" in "isn't drying").
    text, negated = _without_negated(_without_product_names(_plain(query.text), query.product_type))
    for need, at in negated:
        name(need, at)
    if query.category == "haircare":
        for need, at in _hair_list_needs(text):
            name(need, at)
    # A skin type is a kitchen or general request's need only when module 1 read it as one, in skin's words (17 Oct
    # 2026: "towels that dry fast" had asked about dry skin; "razor for sensitive skin" still asks about it).
    skin_only = query.category in ("kitchen", "general")
    for need, words in needs.items():
        if skin_only and need in SKIN_TYPES and need not in query.constraints.skin_types:
            continue
        for word in (need,) + words:
            at = _first_at(text, word)
            if at is not None:
                name(need, at)
    end = len(text)
    for need in list(query.constraints.skin_types) + list(query.constraints.must_haves):
        name(need, end)
    if query.constraints.min_years:
        name(LASTING, end)
    own_words: list[tuple[int, str, str]] = []  # (where, the word as need words write it, as typed)
    # The request's own words, less those a negation took ("drying" in "isn't drying"): the same length, so where each
    # word is doesn't move.
    plain = _without_negated(_plain(query.text))[0]
    rest = query if not negated else query.model_copy(update={"text": plain})
    for word in need_words(rest):
        at, typed = _as_typed(query.text, word)
        if word in NEED_REQUEST_WORDS and _own_need(NEED_REQUEST_WORDS[word], needs):
            name(_own_need(NEED_REQUEST_WORDS[word], needs), at)
        elif not _covered(word, found, needs):
            own_words.append((at, word, typed))
    phrased, labels = _labels(query, plain, {word for _, word, _ in own_words})
    listed = [(at, Need(need, needs[need], list_words=_list_words(need) if query.category == "haircare" else (),
                        label=phrased.get(at))) for need, at in found.items()]
    own = [(at, Need(typed, request_word=word, label=labels.get(at))) for at, word, typed in own_words]
    # Words that ask the product's type for a checked fact (config.TYPE_ASKED_WORDS, 18 Oct 2026: "non toxic" asks a pan
    # for PFAS-free) are one need, named by what they ask ("PFAS-free"), which comments about toxins or about PFAS,
    # PTFE, PFOA or Teflon talk about; the words' own needs ("non", "toxic") give way to it.
    for start, asked, end in type_asked_spans(query.text, query.product_type):
        typed = query.text[start:end]
        taken = {_need_form(token) for token in _TOKEN.findall(_plain(typed))}
        own = [(at, need) for at, need in own if need.request_word not in taken]
        own.append((start, Need(typed, TYPE_ASKED_WORDS[asked]["comment_words"],
                                label=TYPE_ASKED_LABEL.format(typed=typed, asked=asked))))
    return tuple(need for _, need in sorted(listed + own, key=lambda pair: pair[0]))


def _labels(query: ParsedQuery, text: str, own: set[str]) -> tuple[dict[int, str], dict[int, str]]:
    """How the reason names the request's needs, by where each word starts in the request: ({where: label} from
    config.NEED_PHRASES alone, for config's needs; {where: label} for the request's own words, `own`).

    Two words that make one need (config.NEED_PHRASES, 16 Oct 2026) are named whole ("about dark circles", not "about
    dark or circles"; "about pour over", whose "over" is no need word), since 17 Oct 2026 also inside the product's name
    ("noise cancelling headphones", "true wireless earbuds") and for a need of config's ("dry lips" in a lip balm
    request, not "dry skin"). And since 17 Oct 2026 (the ws-names builder), the request's own words written next to each
    other are named together, as typed ("small living room", "bread dough", "video calls"), with a number before them
    ("three storey house"), and a need that is a verb reads as one (config.NEED_VERB_LABELS: "drying fast", "staying
    cool", "slipping"). Words that name the product or a brand (judged_needs) part them: "double cleansing oil" is
    "double cleansing". Comments are still found by each word: found as the two words together only, the espresso
    machine answer had read fewer threads about steam wands and lost its machines with one (16 Oct 2026). `text` is the
    request in small letters, without what a negation took: the same length as the request, so places don't move."""
    tokens = list(_TOKEN.finditer(text))
    phrased: dict[int, str] = {}
    for start, end, _ in _phrases(text):
        for token in tokens:
            if start <= token.start() < end:
                phrased.setdefault(token.start(), query.text[start:end])
    parted = _ingredient_words(text) | _product_name_words(query) | _brand_words(query)
    forms = [_need_form(token.group(0)) for token in tokens]
    labels = dict(phrased)
    group: list[int] = []  # the tokens of a run of the request's own words

    def close() -> None:
        if not group:
            return
        first, last = tokens[group[0]], tokens[group[-1]]
        start = first.start()
        before = group[0] - 1
        if (len(group) > 1 and before >= 0 and _is_number(tokens[before].group(0))
                and not text[tokens[before].end():start].strip()):
            start = tokens[before].start()  # "three storey house"
        words = query.text[start:last.end()].split()
        verb = NEED_VERB_LABELS.get(first.group(0))
        if verb is not None:
            words[words.index(next(w for w in words if w.lower() == first.group(0)))] = verb
        label = " ".join(words) if len(group) > 1 or verb is not None else None
        for i in group:
            if label is not None:
                labels.setdefault(tokens[i].start(), label)
        group.clear()

    for i, (token, form) in enumerate(zip(tokens, forms)):
        if form in own and form not in parted and len(form) > 1 and not _is_size(form):
            if group and text[tokens[group[-1]].end():token.start()].strip():
                close()
            group.append(i)
        else:
            close()
    close()
    return phrased, labels


def _need_form(token: str) -> str:
    """A request's word as need words are written (engine.sources.need_words): "anti-" and "-free" left out, no hyphens
    or apostrophes, a plural trimmed."""
    token = re.sub(r"^anti-(?=[a-z])|(?<=[a-z])-free$", "", token)
    return _stem(re.sub(r"['-]", "", token))


_NUMBER_WORDS = frozenset({"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "single",
                           "double", "triple"})


def _is_number(word: str) -> bool:
    return word.isdigit() or word in _NUMBER_WORDS


# A need a word names, in a category whose needs name it otherwise (17 Oct 2026, the ws-names builder): eczema or rosacea
# on a scalp is a sensitive scalp, not sensitive skin, which no haircare request names (needs_of).
_HAIR_EQUIVALENTS = {"sensitive": "sensitive scalp"}


def _own_need(need: str, needs: dict[str, tuple[str, ...]]) -> str | None:
    """The need of this category's (`needs`) that config.NEED_REQUEST_WORDS's `need` is: itself, or its haircare
    equivalent ("sensitive scalp" for "sensitive"); None when the category has neither, so the word is a need of its
    own, as typed."""
    if need in needs:
        return need
    equivalent = _HAIR_EQUIVALENTS.get(need)
    return equivalent if equivalent in needs else None


def judged_needs(query: ParsedQuery) -> tuple[Need, ...]:
    """The request's needs (request_needs) that the need rule judges a pick by (engine.pipeline._ranked: a pick needs a
    credible recommendation that talks about one of them; 15 Oct 2026, with skincare's readings in the rule, Noemi's
    decision 3): every need but a word that says what the product is or holds, which comments' words can't settle:
    - a word of an active ingredient the request names (config.INGREDIENTS): one it asks for ("vitamin c serum":
      "vitamin", "c") is the product asked for, checked against the maker's list of actives (engine/ingredients.py), and
      so is one it asks to leave out ("moisturiser without niacinamide"): writers say either way whether a cream holds
      it, and on the frozen library the rule had picked two creams whose writers say they do;
    - a size (config.NEED_SIZE_UNITS: "15ml", "28cm", "1.7 fl oz"), which nobody's praise is about;
    - a single letter ("w" of "w/o"), which names nothing;
    - in a category whose every reading follows the rule (config.NEED_RULE_IN_EVERY_READING: skincare and haircare), a
      word of a checked requirement the request asks for (engine.product_facts.hard_requirements: SPF in a lip balm
      request, Noemi's decision 2 of 15 Oct 2026; "sulfate" in a sulfate-free one), which the product's facts settle,
      as they settle an ingredient (15 Oct 2026, the orchestrator, merging decisions 2 and 3). Kitchen and general
      requests keep these words in their wider reading's rule, as before (a PFAS-free pan's voices still talk about it).
    Since 15 Oct 2026 everything an answer says or shows about the request's needs goes by these too (engine.pipeline's
    _score and write_answer): the reason's "2 of them about ...", the breakdown's counts, the quotes about them shown
    first, and whether a comment standing out in its thread talks about what was asked; a vitamin C serum's reason had
    said "3 of them about vitamin or c". They stay needs for the threads read first (engine.sources), as before."""
    named = (_ingredient_words(_plain(query.text)) | _requirement_words(query) | _product_name_words(query)
             | _brand_words(query))
    return tuple(need for need in request_needs(query) if need.request_word is None or not (
        need.request_word in named or _is_size(need.request_word) or len(need.request_word) == 1))


def _product_name_words(query: ParsedQuery) -> frozenset[str]:
    """The words of the request that name the product asked for, as need words are written (16 Oct 2026, the
    interview-fixes builder; the decided rule of 11 Oct 2026 that the product's own name is never a need).

    In a category whose every reading follows the need rule (config.NEED_RULE_IN_EVERY_READING: skincare and haircare):
    each of its type's names and clue words the request uses (module 1's keywords and hints, config.TYPE_SYNONYMS:
    "night cream" for a moisturiser, "cleansing oil" for a cleanser, "spf" for a sunscreen, "patches" for a spot
    treatment), and the words of a form it names next to an ingredient ("wash" in "salicylic acid wash"). Reason lines
    had said "about night or cream" and "about spf", and a word nearly every comment says ("cream", "oil", which also
    begins "oily") had let every product through the rule.

    In kitchen and general requests (17 Oct 2026, the ws-names builder): the last word of each of the type's names the
    request uses, the noun that names the product ("freezer" in "fridge freezer", "machine" in "coffee machine",
    "charger" in "portable charger", "casserole" in "cast iron casserole"), and the kitchen's, skincare's or haircare's
    own words inside such a name ("coffee" in "coffee machine", "tea" in "tea kettle"), which every comment about it
    says. Reason lines had said "about freezer" in a fridge freezer answer. A kind named in the type's names stays a
    need: it is what they ask ("gaming" in "gaming laptop": without it, a comment standing out in its thread had lifted
    a MacBook Pro into "best gaming laptop under 800"; "cast iron" in "cast iron kettle"; "wine" in "wine cooler").
    They stay needs for the threads read first (engine.sources), as before."""
    from engine.config import NEED_RULE_IN_EVERY_READING

    product = next((p for p in PRODUCT_TYPES if p.name == query.product_type), None)
    if query.category not in NEED_RULE_IN_EVERY_READING:
        return _heads_of_names(_plain(query.text), tuple(product.keywords) if product else ()) | _named_words(
            _plain(query.text), tuple(re.escape(name) for name in TYPE_OTHER_NAMES.get(query.product_type or "", ())))
    names = list(product.keywords + product.hints) if product else []
    names += list(TYPE_SYNONYMS.get(query.product_type or "", ()))
    patterns = [re.escape(name.lower()) for name in names]
    patterns += [words for words, form in INGREDIENT_FORM_WORDS if form in query.constraints.forms]
    return _named_words(_plain(query.text), tuple(patterns))


@cache
def _heads_of_names(text: str, names: tuple[str, ...]) -> frozenset[str]:
    """The last word of each of `names` of two words or more that `text` holds as whole words, and the categories' own
    words inside it (engine.query.CATEGORY_HINTS: "coffee", "tea", "cooking"...), as need words are written. A name of
    one word is no head of another's (18 Oct 2026): it is a kind, a maker's line or a model ("gyuto", "macbook",
    "kindle"), what the request asks for, or a plain synonym the request's other words already leave out."""
    hints = {hint for words in CATEGORY_HINTS.values() for hint in words}
    words: set[str] = set()
    for name in names:
        written = name.lower().split()
        if len(written) < 2 or not re.search(rf"(?<![a-z0-9]){re.escape(name.lower())}(?:s|es)?(?![a-z0-9])", text):
            continue
        words.add(_need_form(written[-1]))
        words |= {_need_form(word) for word in written[:-1] if word in hints}
    return frozenset(words)


def _brand_words(query: ParsedQuery) -> frozenset[str]:
    """The words of the brands a request names (17 Oct 2026, the ws-names builder: "cerave or similar" had made
    "cerave" a need, "about fragrance, oily skin, acne-prone skin or cerave"): a brand says which products, not what
    they are for, so it is no judged need, though it still leads the first reading to threads about it. Brands are the
    ones module 1 knows (engine.query_model's list: the brand-lines list, config.MAKER_SPELLINGS and the shipped short
    names' full names), but those that are everyday words too (config.EVERYDAY_BRAND_WORDS: "global", "field")."""
    from engine.query import _context_ranges
    from engine.query_model import brand_names

    # A brand written as what the product is for, with or on is what it needs (18 Oct 2026): a case "for my iphone 15"
    # is about the iPhone, a charger "for my macbook" about the MacBook; and so is a brand's line that is one of the
    # type's own names, the product asked for ("macbook for uni", "kindle with a warm light").
    text = _plain(query.text)
    product = next((p for p in PRODUCT_TYPES if p.name == query.product_type), None)
    spans = list(_context_ranges(text))
    for name in (product.keywords if product else ()):
        spans += [m.span() for m in re.finditer(rf"(?<![a-z0-9]){re.escape(name.lower())}(?:s|es)?(?![a-z0-9])", text)]
    for start, end in spans:
        text = text[:start] + " " * (end - start) + text[end:]
    return _brands_in(text, brand_names())


@cache
def _brands_in(text: str, brands: frozenset[tuple[str, ...]]) -> frozenset[str]:
    plain = " " + " ".join(re.findall(r"[a-z0-9]+", text.replace("'", "").replace("’", ""))) + " "
    words: set[str] = set()
    for brand in brands:
        if len(brand) == 1 and brand[0] in EVERYDAY_BRAND_WORDS:
            continue
        if f" {' '.join(brand)} " in plain:
            words |= {_stem(word) for word in brand}
    return frozenset(words)


@cache
def _named_words(text: str, patterns: tuple[str, ...]) -> frozenset[str]:
    """The words, as need words are written, of each stretch of `text` one of `patterns` finds as whole words."""
    words: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(rf"(?<![a-z0-9])(?:{pattern})(?:s|es)?(?![a-z0-9])", text):
            words |= {_stem(re.sub(r"['-]", "", token))
                      for token in re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)*", match.group(0))}
    return frozenset(words)


def _phrases(text: str) -> list[tuple[int, int, tuple[str, ...]]]:
    """The two-word needs of config.NEED_PHRASES a request (lowercase, the product's names blanked) holds, written with a
    space: (where it starts, where it ends, its words as need words are written)."""
    found = []
    for phrase in NEED_PHRASES:
        for match in _phrase_pattern(phrase).finditer(text):
            found.append((match.start(), match.end(), tuple(_stem(word) for word in match.group(0).split())))
    return found


@cache
def _phrase_pattern(phrase: str) -> re.Pattern:
    words = phrase.split()
    return re.compile(r"(?<![a-z0-9-])" + r"\s+".join(map(re.escape, words)) + r"s?(?![a-z0-9-])")


def _requirement_words(query: ParsedQuery) -> frozenset[str]:
    """The words of the checked requirements the request asks for (their rules' "asks", config.PRODUCT_FACT_RULES), as
    need words are written: "spf" for a lip balm with SPF, "sulfate" and "free" for a sulfate-free shampoo."""
    from engine.config import NEED_RULE_IN_EVERY_READING, PRODUCT_FACT_RULES
    from engine.product_facts import hard_requirements  # here: engine.product_facts builds on this module

    if query.category not in NEED_RULE_IN_EVERY_READING:
        return frozenset()
    words = set()
    for name in hard_requirements(query):
        for asked in PRODUCT_FACT_RULES[name]["asks"]:
            words |= {_stem(word) for word in re.findall(r"[a-z0-9]+", asked.lower())}
    return frozenset(words)


@cache
def _ingredient_words(text: str) -> frozenset[str]:
    """The words of every active ingredient a request (lowercase) names, asked for or not (config.INGREDIENTS' "asked",
    found as engine.ingredients finds them), as need words are written (engine.sources.need_words: no hyphens or
    apostrophes, a plural "s" trimmed)."""
    words = set()
    for key, entry in INGREDIENTS.items():
        if any(_whole_words(pattern).search(text) for pattern in entry["asked"]):
            for written in (key, *entry["asked"]):
                words |= {_stem(word) for word in re.findall(r"[a-z0-9]+", written.lower())}
    return frozenset(words)


_SIZE = re.compile(r"\d+(?:{units}|in)|(?:{units})".replace("{units}", "|".join(
    sorted(map(re.escape, NEED_SIZE_UNITS), key=len, reverse=True))))


def _is_size(word: str) -> bool:
    """Whether a need word (as engine.sources.need_words writes it) only says a size: "15ml", "7l" (of "1.7l"),
    "210mm", "2qt", or a unit on its own ("fl", "oz", "inch", "quart")."""
    return _SIZE.fullmatch(word) is not None


def thread_needs(thread: Thread, needs: tuple[Need, ...], titled_as_another_type: bool = False) -> tuple[str, ...]:
    """The names of the request's needs a thread's title or post talks about, in the request's order (14 Oct 2026, the
    library's need-led first reading: engine.sources.LocalSource). Nothing when `titled_as_another_type`: its title
    names another type of product and not the one asked for (engine.sources.titled_as_another_type), so the thread is
    about that one, whatever its post says ("SPF for oily skin?" is no moisturiser thread for oily skin)."""
    if not needs or titled_as_another_type:
        return ()
    met = set(needs_met(thread.title, needs, thread=True)) | set(_post_needs(thread, needs))
    return tuple(need.name for need in needs if need.name in met)


def _post_needs(thread: Thread, needs: tuple[Need, ...]) -> tuple[str, ...]:
    """The needs the thread's post talks about: from its words, or for a slimmed thread from the words of config's
    needs noted before its post's words went (engine.models.WholeThread.post_need_words and post_list_words)."""
    facts = thread.whole_thread
    if facts is None:
        return needs_met(thread.body or "", needs, thread=True)
    words, listed, known = set(facts.post_need_words), set(facts.post_list_words), set(facts.post_words)
    return tuple(need.name for need in needs if (need.request_word in known if need.request_word is not None else (
        words.intersection(need.words) or listed.intersection(need.list_words))))


def every_config_need() -> tuple[Need, ...]:
    """Every need of config.NEEDS and config.HAIR_NEEDS with its words (a hair need with the words that name it in hair
    types written together too), as a request of either category names them: what slimming notes a post held."""
    return tuple(Need(name, words) for name, words in NEEDS.items()) + tuple(
        Need(name, words, list_words=_list_words(name)) for name, words in HAIR_NEEDS.items())


def post_need_words(body: str) -> list[str]:
    """The words of config's needs (every_config_need) a post's own words hold, found as needs_met finds them: what a
    slimmed thread keeps of its post for need-led reading (engine/slim.py). Config's words only, never the post's."""
    text = _own_words(body or "")
    for name in NEED_LOOKALIKES:  # what a need's words say something else in (config.NEED_LOOKALIKES)
        text = _without_lookalikes(text, name)
    vocabulary = sorted({word for need in every_config_need() for word in need.words})
    return [word for word in vocabulary if _first_at(text, word) is not None]


def post_list_words(body: str) -> list[str]:
    """The words of config.HAIR_LIST_NEEDS a post's hair types written together hold ("fine" in "fine, oily hair")."""
    return sorted(_hair_list_words(_own_words(body or "")))


def post_request_words(body: str, vocabulary) -> list[str]:
    """The words of `vocabulary` (words as engine.sources.need_words gives a request's: letters and digits only) that
    a post's own words hold as needs_met finds a request's word in them (engine.sources._title_has: whole words, two
    words written as one, longer forms), worked out once for the post: what a slimmed thread keeps of its post for a
    request's own words (engine/slim.py)."""
    candidates = _title_words(_own_words(body or ""))
    return sorted(word for word in set(vocabulary)
                  if (f" {word}" in candidates if len(word) >= 4 else f" {word} " in candidates))


def needs_met(body: str, needs: tuple[Need, ...], long_term_use: bool = False, thread: bool = False) -> tuple[str, ...]:
    """The names of the needs a comment talks about, in the request's order: an empty tuple when it talks about none.

    `body` is the comment as saved; only the writer's own words count, not quoted blocks. `long_term_use` is module
    5's finding for this mention: long use also speaks to "lasting". `thread`: the body is a thread's title or post,
    which config.NEED_COMMENT_WORDS never speak for (14 Oct 2026). It depends on these alone, so each is worked out
    once (latency, 13 Oct 2026: a comment naming several products was read again for each).
    """
    if not needs:
        return ()
    key = (body, needs, long_term_use, thread)
    found = _NEEDS_MET.get(key)
    if found is None:
        found = _NEEDS_MET.keep(key, _needs_met(body, needs, long_term_use, thread))
    return found


def _needs_met(body: str, needs: tuple[Need, ...], long_term_use: bool, thread: bool = False) -> tuple[str, ...]:
    text = _own_words(body)
    listed = None  # the words of hair types written together in the text, looked for once, when a need has some
    met = []
    for need in needs:
        if need.request_word is not None:
            # A request's own word in its other words too (17 Oct 2026: "uni" and "college" for "university",
            # config.REQUEST_WORD_SYNONYMS), and never in words that say something else (config.NEED_LOOKALIKES:
            # "taking off my makeup" isn't wearing it).
            # A short word is found with its plural too ("dogs" and "dog's" for "dog"; a longer word's are found as
            # its beginning).
            own = _without_lookalikes(text, need.request_word)
            talks = any(_title_has(own, form)
                        for word in (need.request_word, *REQUEST_WORD_SYNONYMS.get(need.request_word, ()))
                        for form in ((word, word + "s") if len(word) < 4 else (word,)))
        else:
            own = _without_lookalikes(text, need.name)  # "broke in my new pan" isn't about lasting (14 Oct 2026)
            words = need.words if thread else need.words + NEED_COMMENT_WORDS.get(need.name, ())
            talks = any(_first_at(own, word) is not None for word in words)
            talks = talks or (need.name == LASTING and long_term_use)
            if not talks and need.list_words:
                listed = _hair_list_words(text) if listed is None else listed
                talks = any(word in listed for word in need.list_words)
        if talks:
            met.append(need.name)
    return tuple(met)


def said_not_to_help(quote: str, needs: tuple[Need, ...]) -> tuple[str, ...]:
    """The names of the needs a quote says its own product didn't help with, in the request's order (15 Oct 2026;
    config.NO_HELP_PATTERNS): "it did nothing for my oily skin", "doesn't help redness much", "I bought it for my dark
    spots, which it didn't help with". The quote's own product only: in the phrase's clause (up to a full stop, "but",
    "though", "however"...), the words before it are none or point at it ("it", "this one", "which it":
    config.NO_HELP_POINTERS), so "the other cream did nothing for my oily skin" says nothing of this one. The engine
    gives such a recommendation no credit for talking about those needs (engine.pipeline._score), and shows its quote
    after the others (engine.answer); a warning keeps them."""
    if not needs:
        return ()
    said: set[str] = set()
    for clause in _CLAUSE_END.split(_own_words(quote)):
        for match in _no_help().finditer(clause):
            before = clause[:match.start()]
            pointer = _pointer(before)
            if pointer is None:
                continue
            said.update(needs_met(clause[match.end():], needs))  # "... nothing for my oily skin"
            if pointer and pointer.split()[0] in ("which", "that"):  # "my oily skin, which it didn't help with"
                said.update(needs_met(before[:before.rfind(pointer.split()[0])], needs))
    return tuple(need.name for need in needs if need.name in said)


_CLAUSE_END = re.compile(r"[.!?;:\n]|(?<![a-z0-9'])(?:but|though|although|however|yet|whereas)(?![a-z0-9'])")


@cache
def _no_help() -> re.Pattern:
    return re.compile(r"(?<![a-z0-9'])(?:" + "|".join(f"(?:{p})" for p in NO_HELP_PATTERNS) + ")")


def _pointer(before: str) -> str | None:
    """The words pointing at the quote's own product that end `before` (config.NO_HELP_POINTERS), "" when only words
    leading into a clause (config.NO_HELP_LEADS) or nothing come before; None when something else does (another
    product, a person)."""
    words = re.findall(r"[a-z0-9']+", before)
    while words and words[0] in NO_HELP_LEADS:
        words = words[1:]
    if not words:
        return ""
    for size in (2, 1):
        tail = " ".join(words[-size:])
        if len(words) >= size and tail in NO_HELP_POINTERS:
            return tail
    return None


def has_word(text: str, word: str) -> bool:
    """Whether `text` (lowercase) holds `word` at the start of a word, or the phrase `word` whole (a plural "s"
    may follow)."""
    return _first_at(text, word) is not None


# --- Helpers ---

def _without_lookalikes(text: str, need: str) -> str:
    """The text (lowercase) with the phrases that hold the need's words but say something else blanked out
    (config.NEED_LOOKALIKES: "broke in my new pan" is seasoning, not lasting; 14 Oct 2026)."""
    for pattern in _lookalike_patterns(need):
        text = pattern.sub(lambda m: " " * len(m.group(0)), text)
    return text


@cache
def _lookalike_patterns(need: str) -> tuple[re.Pattern, ...]:
    return tuple(re.compile(p, re.IGNORECASE) for p in NEED_LOOKALIKES.get(need, ()))


def _first_at(text: str, word: str) -> int | None:
    """Where `word` first starts in `text`, as has_word finds it; None when it isn't there."""
    match = _pattern(word).search(text)
    return match.start() if match else None


@cache
def _pattern(word: str) -> re.Pattern:
    """A single word is a word beginning ("sensitiv"); a phrase must end where a word ends ("white cast", "white
    casts")."""
    start = r"(?<![a-z0-9])" + re.escape(word.lower())
    return re.compile(start + (r"s?(?![a-z0-9])" if " " in word else ""))


_TOKEN = re.compile(r"[a-z0-9]+(?:['-][a-z0-9]+)*")
# Words a word just before them describes: "dry" in "doesn't make my dry hair worse" is dry hair, not drying.
_DESCRIBED = ("hair", "skin", "scalp", "curls", "ends", "strands", "face", "waves", "locks", "roots")


def _without_negated(text: str) -> tuple[str, list[tuple[str, int]]]:
    """The request (lowercase) with the words a negation negates blanked out (same length), and the needs they name
    with where their negation starts (config.NEGATED_NEEDS): "isn't drying", "won't dry out my hair", "doesn't leave my
    hair dry", "non-drying" all name "not drying"."""
    tokens = list(_TOKEN.finditer(text))
    found, blanks = [], []
    for i, token in enumerate(tokens):
        word = token.group(0)
        if word.startswith("non-"):  # "non-drying": the negation and its word in one
            candidates = [(word[4:], token.start() + 4, token.end(), i)]
        elif word in NEGATIONS:
            candidates = [(t.group(0), t.start(), t.end(), j)
                          for j, t in enumerate(tokens[i + 1:i + 2 + NEGATION_REACH], start=i + 1)]
        else:
            continue
        for candidate, start, end, j in candidates:
            described = j + 1 < len(tokens) and tokens[j + 1].group(0) in _DESCRIBED
            need = next((need for need, words in NEGATED_NEEDS.items() if candidate.startswith(words)), None)
            if need is not None and not described:
                found.append((need, token.start()))
                blanks.append((start, end))
                break
    for start, end in blanks:
        text = text[:start] + " " * (end - start) + text[end:]
    return text, found


@cache
def _hair_list() -> re.Pattern:
    """Hair types written together before a hair word ("fine oily hair", "thin, greasy hair"; config.HAIR_LIST_*)."""
    words = sorted(set(HAIR_LIST_NEEDS) | set(HAIR_LIST_WORDS), key=len, reverse=True)
    word = "(?:" + "|".join(re.escape(w) for w in words) + ")"
    run = rf"{word}(?:(?:\s*[,/&+]\s*|\s+)(?:(?:and|or|but|yet)\s+)?{word})*"
    nouns = "|".join(re.escape(n) for n in HAIR_LIST_NOUNS)
    return re.compile(rf"(?<![a-z0-9])({run})\s+(?:{nouns})(?![a-z0-9])")


@cache
def _hair_list_word() -> re.Pattern:
    return re.compile("(?<![a-z0-9])(?:" + "|".join(re.escape(w) for w in HAIR_LIST_NEEDS) + ")(?![a-z0-9])")


def _hair_list_needs(text: str) -> list[tuple[str, int]]:
    """The needs that hair types written together name (config.HAIR_LIST_NEEDS), with where each word is."""
    return [(HAIR_LIST_NEEDS[word.group(0)], run.start(1) + word.start())
            for run in _hair_list().finditer(text) for word in _hair_list_word().finditer(run.group(1))]


def _hair_list_words(text: str) -> set[str]:
    """The words of config.HAIR_LIST_NEEDS found in hair types written together in a text."""
    return {word.group(0) for run in _hair_list().finditer(text) for word in _hair_list_word().finditer(run.group(1))}


def _list_words(need: str) -> tuple[str, ...]:
    """The words of config.HAIR_LIST_NEEDS that name a need in hair types written together ("fine", "thin"...)."""
    return tuple(word for word, named in HAIR_LIST_NEEDS.items() if named == need)


def _without_product_names(text: str, product_type: str | None) -> str:
    """The request with the product's own names blanked out (same length, so positions don't move): "dry" in "dry
    shampoo" names the product, not dry skin (11 Oct 2026)."""
    known = {p.name: p.keywords for p in PRODUCT_TYPES}
    for name in sorted({product_type or "", *known.get(product_type or "", ())} - {""}, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(name)}s?\b", lambda m: " " * len(m.group(0)), text)
    return text


def _plain(text: str) -> str:
    """Lowercase, with curly apostrophes made straight, as a comment's own words are read (engine.credibility)."""
    return text.lower().replace("’", "'").replace("‘", "'")


def _as_typed(request: str, word: str) -> tuple[int, str]:
    """Where a need word (engine.sources.need_words: "pourover") is in the request, and how it was typed
    ("pour-over")."""
    for match in re.finditer(r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*", request):
        if _stem(re.sub(r"['’-]", "", match.group(0).lower())) == word:
            return match.start(), match.group(0)
    return len(request), word


def _covered(word: str, found: dict[str, int], needs: dict[str, tuple[str, ...]] = NEEDS) -> bool:
    """Whether a need word is already part of a need found, or is a word too common to show a need.

    "sensitive" is the need "sensitive" (one of its words begins it), "acneprone" is "acne-prone" (the name without its
    hyphen), "white" and "cast" are words of the phrase "white cast". So is a word of the need's own name (15 Oct 2026):
    "acne prone", "fragrance free" and "stainless steel" each name their need, and "prone", "free" or "steel" had been a
    need of its own, found in any comment saying it ("sulfate free", "free shipping") and listed in the reason ("about
    acne-prone skin or prone").
    """
    if word in NEED_IGNORED_WORDS:
        return True
    for need in found:
        if word == re.sub(r"[\s-]", "", need) or word in re.split(r"[\s-]+", need):
            return True
        for need_word in needs[need]:
            if " " in need_word and word in need_word.split():
                return True
            if " " not in need_word and word.startswith(need_word.replace("-", "")):
                return True
    return False
