"""The quote guardrail (module 3): a quote counts only if it exists word for word in its comment.

Only formatting may differ: runs of spaces and line breaks, curly versus straight quote marks, HTML entities
such as &amp;, and markdown emphasis (* _ ~). Any change to the words themselves, their order or their case fails.
"""

import pytest

from engine.verify_quotes import find_quote, verify_quote

BODY = "I've used the CeraVe SA Cleanser for 2 years. Gentle, but it dries me out in winter."


def matched(body: str, quote: str) -> str:
    """The part of the original body the quote was found at."""
    span = find_quote(body, quote)
    assert span is not None, f"{quote!r} should be found in {body!r}"
    start, end = span
    return body[start:end]


# --- Found ---

def test_exact_match_returns_where_it_is():
    quote = "Gentle, but it dries me out in winter."
    assert find_quote(BODY, quote) == (BODY.index("Gentle"), len(BODY))
    assert verify_quote(BODY, quote)


def test_the_whole_comment_can_be_the_quote():
    assert find_quote(BODY, BODY) == (0, len(BODY))


def test_line_breaks_tabs_and_double_spaces_count_as_one_space():
    body = "Gentle,  but it\ndries me out\n\nin\twinter."
    assert matched(body, "Gentle, but it dries me out in winter.") == body


def test_a_quote_split_over_lines_matches_a_body_on_one_line():
    assert verify_quote(BODY, "Gentle, but it\ndries me out")


def test_spaces_around_the_quote_are_ignored():
    assert matched(BODY, "  \n Gentle, but it dries me out \t") == "Gentle, but it dries me out"


def test_curly_apostrophe_equals_a_straight_one():
    assert verify_quote(BODY, "I’ve used the CeraVe SA Cleanser")
    assert verify_quote("I‘ve used it, it’s fine‛", "I've used it, it's fine'")


def test_curly_double_quotes_equal_straight_ones():
    assert verify_quote('They call it "the holy grail" here.', "They call it “the holy grail” here.")
    assert verify_quote("They call it “the holy grail” here.", 'call it "the holy grail"')


def test_html_entities_equal_their_characters():
    body = "Le Creuset &amp; Staub both last. &gt; 20 years for mine, &lt;3"
    assert matched(body, "Le Creuset & Staub both last.") == "Le Creuset &amp; Staub both last."
    assert verify_quote(body, "> 20 years for mine, <3")
    assert verify_quote(body, "Le Creuset &amp; Staub")  # a quote copied with the entity still matches


def test_markdown_bold_is_ignored():
    assert verify_quote("**great** kettle", "great kettle")


def test_markdown_italics_and_strikethrough_are_ignored_on_both_sides():
    body = "It's *really* good, ~~not~~ _never_ peeling."
    assert verify_quote(body, "It's really good, not never peeling.")
    assert verify_quote("It's really good", "It's **really** good")


def test_emoji_and_accents_are_kept():
    body = "My crème brûlée torch 🔥 still works après 5 ans."
    assert matched(body, "crème brûlée torch 🔥 still works") == "crème brûlée torch 🔥 still works"
    assert not verify_quote(body, "creme brulee torch 🔥 still works")
    assert not verify_quote(body, "crème brûlée torch still works")


def test_the_span_points_into_the_original_body_despite_markdown_and_spaces():
    body = "Honestly? I **love**  this\n\nkettle &amp; its *lid*. Bought 2019."
    start, end = find_quote(body, "I love this kettle & its lid.")
    assert start == body.index("I **love**")
    assert body[start:end] == "I **love**  this\n\nkettle &amp; its *lid*."


def test_a_later_occurrence_is_found_when_the_first_one_cuts_a_word():
    body = "I refuse it at first. Now I use it daily."
    start, _ = find_quote(body, "use it daily")
    assert start == body.index("use it daily")
    assert matched(body, "use it") == "use it"
    assert find_quote(body, "use it")[0] == body.index("I use it") + 2


# --- Not found ---

def test_a_change_of_case_fails():
    assert find_quote(BODY, "gentle, but it dries me out in winter.") is None
    assert not verify_quote(BODY, "I've used the cerave SA cleanser")


def test_one_changed_word_fails():
    assert not verify_quote(BODY, "Gentle, but it dries me out in summer.")
    assert not verify_quote(BODY, "I've used the CeraVe SA Cleanser for 3 years.")


def test_a_paraphrase_fails():
    assert not verify_quote(BODY, "It's gentle but drying in winter.")


def test_a_missing_or_reordered_word_fails():
    assert not verify_quote(BODY, "Gentle, but dries me out in winter.")
    assert not verify_quote(BODY, "Gentle, but it me dries out in winter.")


@pytest.mark.parametrize("joint", ["…", "...", " … ", " ... ", " [...] "])
def test_parts_stitched_together_fail(joint):
    assert not verify_quote(BODY, f"I've used the CeraVe SA Cleanser{joint}it dries me out in winter.")


def test_a_quote_longer_than_the_body_fails():
    assert not verify_quote("Love it.", "Love it. Would buy again.")


@pytest.mark.parametrize("quote", ["", " ", "\n\t ", "** __ ~~"])
def test_an_empty_quote_fails(quote):
    assert find_quote(BODY, quote) is None
    assert not verify_quote(BODY, quote)


def test_a_quote_that_cuts_a_word_fails():
    # Part of a word is not the word: "like it" is not in "dislike it", "reliable" is not in "unreliable".
    assert not verify_quote("Honestly I dislike it.", "like it")
    assert not verify_quote("The lid is unreliable.", "reliable.")
    assert not verify_quote("Mine lasted 12 years.", "2 years")
    assert not verify_quote(BODY, "entle, but it dries")


def test_other_punctuation_must_match():
    assert not verify_quote(BODY, "Gentle but it dries me out in winter.")
    assert not verify_quote(BODY, "Gentle, but it dries me out in winter!")
