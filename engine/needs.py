"""What the person asked for, and which comments talk about it (module 6, ranking; 9 Oct 2026).

"retinol for a beginner with sensitive skin" asks for more than a retinol: it asks for one that suits a beginner with
sensitive skin. A comment that talks about those needs ("I have sensitive skin and started slowly with Differin") tells
this shopper more than one that doesn't, whether it recommends the product or warns against it ("too harsh for
sensitive skin"). So the ranking counts such mentions more: the pipeline multiplies their weight by
config.NEED_MATCH_BOOST (off, 1.0, since 9 Oct 2026; see config). The minimum-evidence rule doesn't change: it counts credible mentions, not weights.

A request's needs (request_needs), in the order the request gives them:
- the needs of config.NEEDS that it names: by name or by one of the need's words ("new to retinol" names
  "beginner", "doesn't leave a white cast" names "no white cast"); module 1's skin types ("sensitive") and must-haves
  ("fragrance-free"); a few other words of config.NEED_REQUEST_WORDS ("first chef's knife" names "beginner", "will
  last decades" names "lasting"); and module 1's "lasts 10+ years" (min_years), which names "lasting" too;
- every other specific word of the request (engine.sources.need_words: "pour-over", "PFAS", "winter"), each a need of
  its own, found in comments by that word alone. The words of config.NEED_IGNORED_WORDS ("leave", "cook", "burr")
  are left out: they are too common in comments to show anything.

A comment talks about a need (needs_met) when its own words (not quoted blocks: those are someone else's words) hold one
of the need's words, at the start of a word: a word beginning finds its longer forms ("sensitiv" finds "sensitive" and
"sensitivity"), and a phrase is found whole ("white cast", "white casts"). A request's own word is found the way
module 2 finds it in a thread title: "pour over" and "pourover" both find "pour-over" (engine.sources._title_has).
A mention with long-term use (module 5) also talks about "lasting": it describes long use.
"""

import re
from dataclasses import dataclass
from functools import cache

from engine.config import NEED_IGNORED_WORDS, NEED_REQUEST_WORDS, NEEDS
from engine.credibility import _own_words
from engine.query import ParsedQuery
from engine.sources import _stem, _title_has, need_words

LASTING = "lasting"  # the need that long-term use also speaks to


@dataclass(frozen=True)
class Need:
    """One thing the request asks for, and how to recognise a comment that talks about it."""

    name: str  # a need of config.NEEDS ("sensitive"), or a word of the request as typed ("pour-over")
    words: tuple[str, ...] = ()  # config.NEEDS's words for it; empty for a word of the request
    request_word: str | None = None  # a word of the request, as module 2 matches it ("pourover"); None otherwise


def request_needs(query: ParsedQuery) -> tuple[Need, ...]:
    """The needs the request names, in the order it names them (a need module 1 found but the words don't show, last).

    Nothing for a request module 1 didn't understand (a question or a polite no).
    """
    if query.status != "ok":
        return ()
    text = _plain(query.text)
    found: dict[str, int] = {}  # need name -> where the request names it

    def name(need: str, at: int) -> None:
        if need in NEEDS:
            found[need] = min(at, found.get(need, at))

    for need, words in NEEDS.items():
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
    for word in need_words(query):
        at, typed = _as_typed(query.text, word)
        if word in NEED_REQUEST_WORDS:
            name(NEED_REQUEST_WORDS[word], at)
        elif not _covered(word, found):
            own_words.append((at, Need(typed, request_word=word)))
    listed = [(at, Need(need, NEEDS[need])) for need, at in found.items()]
    return tuple(need for _, need in sorted(listed + own_words, key=lambda pair: pair[0]))


def needs_met(body: str, needs: tuple[Need, ...], long_term_use: bool = False) -> tuple[str, ...]:
    """The names of the needs a comment talks about, in the request's order: an empty tuple when it talks about none.

    `body` is the comment as saved; only the writer's own words count, not quoted blocks. `long_term_use` is module
    5's finding for this mention: long use also speaks to "lasting".
    """
    if not needs:
        return ()
    text = _own_words(body)
    met = []
    for need in needs:
        if need.request_word is not None:
            talks = _title_has(text, need.request_word)
        else:
            talks = any(_first_at(text, word) is not None for word in need.words)
            talks = talks or (need.name == LASTING and long_term_use)
        if talks:
            met.append(need.name)
    return tuple(met)


def has_word(text: str, word: str) -> bool:
    """Whether `text` (lowercase) holds `word` at the start of a word, or the phrase `word` whole (a plural "s"
    may follow)."""
    return _first_at(text, word) is not None


# --- Helpers ---

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


def _covered(word: str, found: dict[str, int]) -> bool:
    """Whether a need word is already part of a need found, or is a word too common to show a need.

    "sensitive" is the need "sensitive" (one of its words begins it), "acneprone" is "acne-prone" (the name without its
    hyphen), "white" and "cast" are words of the phrase "white cast".
    """
    if word in NEED_IGNORED_WORDS:
        return True
    for need in found:
        if word == re.sub(r"[\s-]", "", need):
            return True
        for need_word in NEEDS[need]:
            if " " in need_word and word in need_word.split():
                return True
            if " " not in need_word and word.startswith(need_word.replace("-", "")):
                return True
    return False
