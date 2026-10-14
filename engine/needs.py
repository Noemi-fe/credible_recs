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
  are left out: they are too common in comments to show anything.
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
from dataclasses import dataclass
from functools import cache

from engine.config import (
    HAIR_LIST_NEEDS, HAIR_LIST_NOUNS, HAIR_LIST_WORDS, HAIR_NEEDS, NEED_COMMENT_WORDS, NEED_IGNORED_WORDS,
    NEED_LOOKALIKES, NEED_REQUEST_WORDS, NEEDS, NEGATED_NEEDS, NEGATION_REACH, NEGATIONS,
)
from engine.credibility import _own_words
from engine.memo import Table
from engine.models import Thread
from engine.query import PRODUCT_TYPES, SKIN_TYPES, ParsedQuery
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
    for need, words in needs.items():
        for word in (need,) + words:
            at = _first_at(text, word)
            if at is not None:
                name(need, at)
    end = len(text)
    for need in list(query.constraints.skin_types) + list(query.constraints.must_haves):
        name(need, end)
    if query.constraints.min_years:
        name(LASTING, end)
    own_words: list[tuple[int, Need]] = []
    # The request's own words, less those a negation took ("drying" in "isn't drying"): the same length, so where each
    # word is doesn't move.
    rest = query if not negated else query.model_copy(update={"text": _without_negated(_plain(query.text))[0]})
    for word in need_words(rest):
        at, typed = _as_typed(query.text, word)
        if word in NEED_REQUEST_WORDS:
            name(NEED_REQUEST_WORDS[word], at)
        elif not _covered(word, found, needs):
            own_words.append((at, Need(typed, request_word=word)))
    listed = [(at, Need(need, needs[need], list_words=_list_words(need) if query.category == "haircare" else ()))
              for need, at in found.items()]
    return tuple(need for _, need in sorted(listed + own_words, key=lambda pair: pair[0]))


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
            talks = _title_has(text, need.request_word)
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
    hyphen), "white" and "cast" are words of the phrase "white cast".
    """
    if word in NEED_IGNORED_WORDS:
        return True
    for need in found:
        if word == re.sub(r"[\s-]", "", need):
            return True
        for need_word in needs[need]:
            if " " in need_word and word in need_word.split():
                return True
            if " " not in need_word and word.startswith(need_word.replace("-", "")):
                return True
    return False
