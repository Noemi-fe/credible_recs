"""The home page's intro and its third step (3 Nov 2026, Noemi's yes to the new wording).

Both live in the LABELS block at the top of engine/templates/search.html and reach the visitor as the page's own script
draws them, so the tests read them from the page as the server sends it. Nothing here reads the library or the network.
"""

import re

from engine.tests.test_web_public import page_text

INTRO = ("Up to three picks for what you buy and use, across about 350 kinds of product, from moisturisers and kettles "
         "to headphones and suitcases, ranked by how credible the people recommending them are on Reddit, not by how "
         "popular a product is. Every quote is checked word for word against its comment.")
STEP_THREE = ["Checks every quote",
              "Word for word against its comment, and again on Reddit in the 48 hours before it's shown, so a comment "
              "found deleted or edited is never quoted."]


def label(html: str, key: str) -> str:
    """One LABELS entry that is a plain string, as written in the page."""
    found = re.search(rf'^\s*{key}: "(.*)",\s*$', html, re.MULTILINE)
    assert found, key
    return found.group(1)


def test_the_intro_says_up_to_three_picks_across_about_350_kinds_of_product(tmp_path):
    html = page_text(tmp_path)
    assert label(html, "intro") == INTRO
    # Changed on purpose 3 Nov 2026: "Three picks for almost anything you buy and use, from moisturisers and kettles to
    # headphones and hiking boots": some requests get fewer than three picks, "almost anything" claimed too much, and
    # hiking boots left the examples (their top pick isn't sold in the UK).
    assert "almost anything" not in html and "hiking boots" not in label(html, "intro")


def test_the_intro_keeps_what_the_site_stands_for(tmp_path):
    intro = label(page_text(tmp_path), "intro")
    assert "ranked by how credible the people recommending them are on Reddit" in intro
    assert "not by how popular a product is" in intro
    assert intro.endswith("Every quote is checked word for word against its comment.")


def test_the_third_step_says_the_48_hours_and_what_happens_to_a_comment_found_changed(tmp_path):
    html = page_text(tmp_path)
    steps = re.search(r"steps: \[\n(.*?)\n  \],", html, re.DOTALL).group(1)
    found = re.findall(r'\["([^"]*)", "([^"]*)"\]', steps)
    assert len(found) == 3 and list(found[2]) == STEP_THREE
    # Changed on purpose 3 Nov 2026. Was: "..., and again on Reddit, so a deleted or edited comment is never quoted."
    # The check the answer relies on is the last 48 hours' (engine/live_check.py), so the step says so.
    assert "so a deleted or edited comment is never quoted" not in html
    assert [step[0] for step in found[:2]] == ["Reads the threads", "Weighs every voice"]  # the others are as they were
