"""Non-toxic cookware is PFAS-free cookware (18 Oct 2026, the ws-names builder; Claude's call of 18 Oct 2026 in CLAUDE.md,
which Noemi left to Claude: "About the pfas - do what you think is best").

For a product type that has the PFAS-free fact (config.PRODUCT_FACTS_BY_TYPE: frying pans and saucepans), "non toxic",
"non-toxic", "nontoxic" and "toxin free" ask for PFAS-free, since that is what non-toxic means for pans (no PTFE or
other PFAS, Noemi's rule of 11 Oct 2026), as "without teflon" has since 16 Oct 2026. For every other type they stay an
ordinary need word: in skincare or mattresses they mean something else. The reason line names the must-have, so the
reading shows: "about PFAS-free" (as refusing Teflon is named), counting the comments that talk about toxins or about
PFAS, PTFE, PFOA and Teflon.

Every request and comment here is made up; nothing reads data/ but the shipped lists.
"""

import pytest

from engine.needs import judged_needs, needs_met, request_needs
from engine.product_facts import hard_requirements, request_asks
from engine.query import parse_query


def parsed(text: str):
    return parse_query(text, model=None)


def labels(text: str) -> list[str]:
    """The judged needs as the reason names them, each once (engine.answer: two words of one need share its label)."""
    return list(dict.fromkeys(need.label or need.name for need in judged_needs(parsed(text))))


@pytest.mark.parametrize("text", [
    "non toxic frying pan",
    "non-toxic frying pan",
    "nontoxic frying pan",
    "toxin free frying pan",
    "toxin-free saucepan",
    "non toxic pan that lasts",
    "best non toxic non stick pan",
    "Non-Toxic saucepan for a small kitchen",
])
def test_non_toxic_cookware_asks_for_pfas_free(text):
    query = parsed(text)
    assert "PFAS-free" in request_asks(query)
    assert "PFAS" in hard_requirements(query)  # the checked rule: a PTFE pan is left out


@pytest.mark.parametrize("text", [
    "non toxic moisturiser",
    "non-toxic mattress",
    "non toxic shampoo",
    "toxin free sunscreen",
    "non toxic cutting board",  # no PFAS-free fact for boards: an ordinary need word
    "non toxic dutch oven",  # nor for Dutch ovens (enamelled cast iron)
])
def test_non_toxic_is_an_ordinary_need_for_other_types(text):
    query = parsed(text)
    assert "PFAS-free" not in request_asks(query)
    assert any("toxi" in label for label in labels(text)) and not any("PFAS" in label for label in labels(text))


def test_a_toxic_pan_asked_about_isnt_a_pfas_free_one():
    assert "PFAS-free" not in request_asks(parsed("is teflon toxic? frying pan"))


def test_the_reason_names_the_must_have():
    assert labels("non toxic frying pan") == ["PFAS-free"]
    assert labels("toxin-free saucepan") == ["PFAS-free"]
    assert labels("best non toxic non stick pan") == ["PFAS-free", "non stick"]


def test_a_moisturisers_non_toxic_keeps_its_own_words():
    assert labels("non toxic moisturiser") == ["non toxic"]


@pytest.mark.parametrize("body", [
    "Mine is ceramic and PFAS-free, eggs slide right off.",
    "I wanted a non-toxic pan and this one has been great.",
    "No PTFE in the coating, which was the point for me.",
    "Switched away from Teflon years ago and never looked back.",
    "Worried about toxins, so I went with stainless.",
])
def test_comments_about_pfas_or_toxins_talk_about_the_need(body):
    needs = judged_needs(parsed("non toxic frying pan"))
    assert needs_met(body, needs) == (needs[0].name,)


def test_a_comment_about_something_else_doesnt():
    needs = judged_needs(parsed("non toxic frying pan"))
    assert needs_met("Heats evenly and the handle stays cool.", needs) == ()


def test_the_first_reading_still_reads_threads_about_it():
    # One need, found in titles by the same words ("PFAS-free pans that last?"), as other needs are.
    needs = request_needs(parsed("non toxic frying pan"))
    assert len(needs) == 1 and needs_met("PFAS-free pans that last?", needs, thread=True)
