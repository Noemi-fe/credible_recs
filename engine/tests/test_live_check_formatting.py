"""Formatting is not words (15 Oct 2026, from the coordinator's question about replies whose product source had lost its
words after the migration: the sources had been found edited on Reddit, and of 35 kept comments this computer's checks
had found edited, 7 held every quote word for word once formatting was set aside).

Reddit's embed page shows a comment's markdown rendered, so the live check reads its text out of HTML. A tag that only
formats (bold, italics, strikethrough, a link, a superscript, code) is no space between words: read as one,
"<strong>Zojirushi</strong>: it lasted" had become "Zojirushi : it lasted", and a quote holding "**Zojirushi**:" was
no longer found, its comment taken as edited and its words dropped from the library. Paragraphs, line breaks, list
items and quoted blocks still separate words. And Reddit's superscript mark "^" is formatting, like the emphasis marks
(engine.verify_quotes). Made-up pages: no test reaches the network.
"""

from engine.live_check import LiveChecker
from engine.tests.test_live_check import URL, Clock, FakeReddit, page
from engine.verify_quotes import find_quote


def read(tmp_path, html: str) -> str | None:
    """The comment's text as the live check reads it from this embed page."""
    clock = Clock()
    live = LiveChecker(cache_dir=tmp_path / "cache", fetch=FakeReddit(answer=(200, page(html))), clock=clock,
                       sleep=clock.sleep)
    got = live.read_text(URL)
    return None if got is None else got[1]


def test_bold_and_italics_put_no_space_into_a_comments_words(tmp_path):
    body = "Get the **Zojirushi**: mine lasted 9 years, and the *lid*'s hinge never broke."
    text = read(tmp_path, "Get the <strong>Zojirushi</strong>: mine lasted 9 years, and the <em>lid</em>'s hinge "
                          "never broke.")
    assert text == "Get the Zojirushi: mine lasted 9 years, and the lid's hinge never broke."
    for quote in ("the **Zojirushi**: mine lasted 9 years", "the *lid*'s hinge never broke"):
        assert find_quote(body, quote) is not None and find_quote(text, quote) is not None


def test_a_link_and_struck_out_words_read_as_their_text(tmp_path):
    text = read(tmp_path, 'The <a href="https://example.com/kettle">Fellow</a>-made kettle, <del>not</del> great.')
    assert text == "The Fellow-made kettle, not great."


def test_paragraphs_line_breaks_list_items_and_quoted_blocks_still_separate_words(tmp_path):
    text = read(tmp_path, "One kettle.</p><p>Two kettles.<br>Three.</p><ul><li>Zojirushi</li><li>Fellow</li></ul>"
                          "<blockquote><p>someone else</p></blockquote><p>end")
    assert text == "One kettle. Two kettles. Three. Zojirushi Fellow someone else end"


def test_reddits_superscript_mark_is_formatting(tmp_path):
    body = "It lasted ^nine years, honestly."
    text = read(tmp_path, "It lasted <sup>nine</sup> years, honestly.")
    assert find_quote(body, "It lasted ^nine years") is not None
    assert find_quote(text, "It lasted ^nine years") is not None
    assert find_quote("It lasted nine years", "lasted nine years") is not None


def test_a_word_that_changed_is_still_a_change(tmp_path):
    text = read(tmp_path, "Get the <strong>Zojirushi</strong>: mine broke after 9 months.")
    assert find_quote(text, "the **Zojirushi**: mine lasted 9 years") is None
