"""The search page's side of on-demand reading (Noemi's plan of 14 Oct 2026, part 3): an answer the site is reading
Reddit for is drawn as a clear, friendly state, not an error: its own notice with the server's sentence, a short hint
and "Check again"; the "not enough evidence" message is left out when nothing has been read yet (it would be about
threads that aren't there). No test reaches the network.
"""

import re

from engine.tests.test_web_public import function_body, page_text, script_of
from engine.tests.test_web_ux import _contrast, _tokens


def test_the_page_has_its_words_for_the_reading_state(tmp_path):
    html = page_text(tmp_path)
    for words in ('onDemandHeading: "Reading Reddit for you"', "onDemandAgain: \"Check again\"",
                  'onDemandHint: "Every quote from the new threads is checked word for word, like all the others."'):
        assert words in html


def test_an_answer_being_read_gets_its_own_notice_with_the_servers_sentence(tmp_path):
    script = script_of(page_text(tmp_path))
    parts = function_body(script, "function answerParts(data, request)")
    assert "data.on_demand ? onDemandNotice(data.on_demand, request) : null" in parts
    assert "answer.message && !(data.on_demand && !(data.reading && data.reading.threads))" in parts
    notice = function_body(script, "function onDemandNotice(state, request)")
    assert 'notice("reading", LABELS.onDemandHeading, state.message, LABELS.onDemandHint)' in notice
    assert "search(request, false)" in notice and "LABELS.onDemandAgain" in notice
    assert "answerParts(data, request)" in function_body(script, "function drawAnswer(data, request)")


def test_the_reading_notice_is_friendly_not_an_error(tmp_path):
    html = page_text(tmp_path)
    assert re.search(r"\.notice\.reading \{ background: var\(--accent-soft\); border-color: transparent; \}", html)
    assert 'reading: "clock"' in function_body(script_of(html), "function notice(kind, heading, ...lines)")
    css = re.search(r"<style>(.*?)</style>", html, re.DOTALL).group(1)
    for mode, tokens in zip(("light", "dark"), _tokens(css)):
        for colour in ("text", "accent"):  # its words and its clock
            ratio = _contrast(tokens[colour], tokens["accent-soft"])
            assert ratio >= 4.5, f"{mode}: {colour} on accent-soft is {ratio:.2f}:1"


def test_the_privacy_section_says_what_on_demand_reading_keeps_only_where_it_happens(tmp_path):
    from engine import how_page
    from engine.tests.test_how_page import text_of, write

    words = text_of(how_page.page(write(tmp_path), public=True, on_demand=True))
    assert "Products we haven't read about yet." in words and "never your request as typed" in words
    assert "Your searches aren't saved by us, except the request you send with feedback, and the short note" in words
    plain = text_of(how_page.page(write(tmp_path)))
    assert "Products we haven't read about yet." not in plain
    assert "Your searches aren't saved by us, except the request you send with feedback." in plain
