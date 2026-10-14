"""HTML's character codes in Reddit's texts (14 Oct 2026, found by the bulk-import builder).

Reddit's titles, posts and comments keep HTML's character codes ("pots &amp; pans", "&gt;" before a quoted line,
"&nbsp;"), sometimes twice over ("&amp;amp;"). Read as they are, "&" and ";" are word boundaries, so retrieval found
the word "amp" (the guitar amp's name and title word) in every "&amp;". The texts are now read with the codes written as
their characters, and a no-break space as a space, before any name or word is looked for. Made-up texts throughout.
"""

from engine.models import Thread
from engine.sources import _title_has, comments_naming, mentions_product, relevance, talking
from engine.tests.factories import make_comment, make_thread


def test_an_ampersand_code_is_no_guitar_amp():
    assert not mentions_product("Best pots &amp; pans for a first flat?", "guitar amp")
    assert not mentions_product("Pots &amp;amp; pans that last", "guitar amp")  # written twice over
    assert not mentions_product("&AMP; more", "guitar amp")
    assert mentions_product("A practice amp &amp; a cable", "guitar amp")  # a real one still counts


def test_other_codes_read_as_their_characters():
    assert mentions_product("a cast&nbsp;iron for searing", "cast iron skillet")  # a no-break space
    assert mentions_product("my old french&#32;press", "french press")  # a space by its number
    assert mentions_product("&quot;guitar amp&quot; reviews", "guitar amp")
    assert not mentions_product("&gt; &lt; &quot; &nbsp; &#x200B;", "guitar amp")


def test_a_title_word_is_not_found_in_a_code():
    assert not _title_has("pots &amp; pans that last?", "amp")
    assert not _title_has("pots &amp;amp; pans", "amp")
    assert _title_has("pots &amp; pans that last?", "pans")
    assert _title_has("a 10&quot; pan", "10")
    for code in ("quot", "gt", "lt", "nbsp"):
        assert not _title_has(f"a &{code}; b", code)


def test_comments_with_codes_name_nothing_they_dont_write():
    thread = Thread.model_validate(make_thread(
        title="Pots &amp; pans that lasted decades?", body="Kitchen &amp; dining &gt; cookware",
        comments=[make_comment(f"c{i}aaaa", body="Le Creuset &amp; Staub, both great &gt; anything else")
                  for i in range(6)]))
    assert relevance(thread, "guitar amp") == 0
    assert comments_naming(thread.comments, "guitar amp") == 0
    assert talking(thread, "guitar amp") == 0
