"""Module 3, guardrail: checks in code that every quote exists word for word in its source comment.

The AI that lists the products in a thread also picks a supporting quote for each one, and an AI may tidy a
quote up, fix a typo, or join two sentences that weren't next to each other. The brief's rule: every quote shown
must exist word for word in the original comment, checked by code, not by the AI. A quote that fails is dropped.

Word for word means the same words, in the same order, with the same spelling and case, one right after the
other. Only differences that are formatting, not words, are tolerated:
- any run of spaces, line breaks and tabs counts as one space, and spaces around the quote are ignored;
- curly apostrophes and quote marks equal straight ones (’ ‘ ‛ as ', and “ ” as ");
- HTML entities equal their characters: Reddit stores "&" as "&amp;" and ">" as "&gt;";
- the markdown symbols for bold, italics and strikethrough (* _ ~) are ignored, so "**great** kettle" contains
  "great kettle", and so is a backslash escaping one ("a \\*lot\\* of eggs" contains "a lot of eggs"; 10 Oct 2026).
A quote must also start and end on whole words: "like it" is not in "I dislike it", because a cut word can flip
the meaning.

How it works: both texts are rewritten in a plain form with those differences taken out, then the quote's plain
form is looked for in the comment's. Each plain character remembers where it came from in the comment, so the
answer points into the comment exactly as written.
"""

import html
import re
import unicodedata

from engine.memo import Table

CURLY_TO_STRAIGHT = {"’": "'", "‘": "'", "‛": "'", "“": '"', "”": '"'}
EMPHASIS_MARKS = frozenset("*_~")  # markdown for **bold**, *italics* or _italics_, and ~~strikethrough~~
_ENTITY = re.compile(r"&(?:#[0-9]+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);")  # &amp; &gt; &#39; &#x27;


def find_quote(body: str, quote: str) -> tuple[int, int] | None:
    """Where the quote appears word for word in the comment body, or None if it doesn't.

    The answer is (start, end), character positions in the body exactly as written, so body[start:end] is the
    matching text with its original formatting. An empty quote, or one made only of spaces, is never found.

    It depends on the two texts alone, so each pair's answer is remembered (latency, 13 Oct 2026: writing an answer
    checks each quote it shows four times, and every answer the same quotes again); a comment that changes is another
    text, checked afresh.
    """
    key = (body, quote)
    found = _FOUND.get(key, _NOT_YET)
    if found is _NOT_YET:
        found = _FOUND.keep(key, _find_quote(body, quote))
    return found


_FOUND = Table()  # (body, quote) -> find_quote's answer
_NOT_YET = object()  # what _FOUND gives for a pair it doesn't hold (None is an answer: not found)


def _find_quote(body: str, quote: str) -> tuple[int, int] | None:
    wanted, _ = _plain(quote)
    wanted = wanted.strip(" ")
    if not wanted:
        return None
    text, origins = _plain(body)
    at = text.find(wanted)
    while at != -1:
        end = at + len(wanted)
        if not _cuts_a_word(text, at, end):
            return origins[at][0], origins[end - 1][1]
        at = text.find(wanted, at + 1)  # this one began or ended inside a word; a later one may not
    return None


def verify_quote(body: str, quote: str) -> bool:
    """True when the quote appears word for word in the comment body (see find_quote)."""
    return find_quote(body, quote) is not None


def _plain(text: str) -> tuple[str, list[tuple[int, int]]]:
    """The text with the tolerated formatting taken out, and where each of its characters came from.

    For every character of the plain text, (start, end) of the original characters it stands for: one character
    usually, a whole entity such as "&amp;" for its "&", or a whole run of spaces for its single space.

    Worked out run by run (latency, 13 Oct 2026: one character at a time, it was most of reading the library and of
    writing an answer's quotes): a run of characters that stay as they are (_ORDINARY: no backslash, "&", emphasis mark,
    curly quote mark or space, but single spaces between them) is copied whole, each character from its own place; the
    others are read one at a time, as before.
    """
    pieces: list[str] = []
    origins: list[tuple[int, int]] = []
    last = ""  # the plain text's last character so far
    i = 0
    while i < len(text):
        run = _ORDINARY.match(text, i)
        if run is not None:
            end = run.end()
            pieces.append(run.group())
            origins.extend(zip(range(i, end), range(i + 1, end + 1)))
            last, i = text[end - 1], end
            continue
        if text[i] == "\\" and i + 1 < len(text) and text[i + 1] in EMPHASIS_MARKS:  # Reddit's escape: "\\*lot\\*"
            i += 1
            continue
        entity = _ENTITY.match(text, i) if text[i] == "&" else None
        if entity and html.unescape(entity.group()) != entity.group():
            chunk, end = html.unescape(entity.group()), entity.end()
        else:  # an ordinary character, or something that only looks like an entity, such as "&foo;"
            chunk, end = text[i], i + 1
        for char in chunk:
            char = CURLY_TO_STRAIGHT.get(char, char)
            if char in EMPHASIS_MARKS:
                continue
            if char.isspace():
                if last == " ":  # still the same run of spaces: it grows, it doesn't repeat
                    origins[-1] = (origins[-1][0], end)
                    continue
                char = " "
            pieces.append(char)
            origins.append((i, end))
            last = char
        i = end
    return "".join(pieces), origins


# The characters _plain copies as they are: anything but a backslash, "&", an emphasis mark, a curly quote mark or a space
# (\s: str.isspace's spaces); a run of them may hold single spaces between them, which stay single spaces.
_KEPT = "[^" + re.escape("\\&" + "".join(sorted(EMPHASIS_MARKS)) + "".join(CURLY_TO_STRAIGHT)) + r"\s]"
_ORDINARY = re.compile(f"{_KEPT}+(?: {_KEPT}+)*")


def _cuts_a_word(text: str, start: int, end: int) -> bool:
    """True when text[start:end] begins or ends in the middle of a word, like "like it" inside "dislike it"."""
    cut_at_start = start > 0 and _in_word(text[start]) and _in_word(text[start - 1])
    cut_at_end = end < len(text) and _in_word(text[end - 1]) and _in_word(text[end])
    return cut_at_start or cut_at_end


def _in_word(char: str) -> bool:
    # Letters and digits in any alphabet, plus accents typed as a separate mark after their letter.
    return char.isalnum() or unicodedata.category(char).startswith("M")
