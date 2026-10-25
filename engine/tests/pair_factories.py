"""Made-up cards for the pairwise test's tests (engine/pair_test.py): the same shape as the real file,
data/library/blind_test_cards.json, with invented products and invented one-line reasons. Nothing here comes from
Reddit or from any tool's answer.
"""

import json
from pathlib import Path

NOTE = {"en": "No recommendation given.", "it": "Nessun consiglio dato."}
# 12 questions as the real set is split: 2 skincare, 5 kitchen, 5 other.
CATEGORIES = {"skincare": ("b01", "b04"), "kitchen": ("b06", "b07", "b08", "b09", "b10"),
              "other": ("r01", "r02", "r03", "r04", "r05")}
QUESTION_IDS = [question for ids in CATEGORIES.values() for question in ids]


def pick(name: str, why: str | None = None) -> dict:
    why = why or f"Holds up well after a year of daily use, said {name}'s fans."
    return {"name": name, "why": {"en": why, "it": f"{why} (it)"}}


# Made-up products, one word for each tool, so a test can tell whose card is whose; no word is a tool's name.
PRODUCT_WORD = {"ours": "Orchid", "chatgpt": "Cedar", "vetted": "Maple"}


def card(question: str, tool: str, picks: int = 3, nothing: bool = False) -> dict:
    """One tool's answer to a question: `picks` made-up picks, or the note when it gave none."""
    if nothing:
        return {"picks": [], "note": dict(NOTE)}
    return {"picks": [pick(f"{PRODUCT_WORD[tool]} {question} model {n}") for n in range(1, picks + 1)], "note": None}


def made_up_cards(**changes) -> dict:
    """The cards file's content: every question answered by the three tools. `changes` replace top-level keys."""
    questions = []
    for category, ids in CATEGORIES.items():
        for question in ids:
            questions.append({"id": question, "category": category,
                              "text": {"en": f"Question {question}, as asked", "it": f"Domanda {question}, come posta"},
                              "answers": {"ours": card(question, "ours"), "chatgpt": card(question, "chatgpt"),
                                          "vetted": card(question, "vetted", nothing=question == "b04")}})
    return {"version": 1, "captured": "2026-10-20", "questions": questions} | changes


def write_cards(folder: Path, cards: dict | None = None) -> Path:
    """Writes the cards as folder/blind_test_cards.json (the library folder's own file name); returns the folder."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "blind_test_cards.json").write_text(json.dumps(cards or made_up_cards(), ensure_ascii=False, indent=1),
                                                  encoding="utf-8")
    return folder


def question_of(cards: dict, question: str) -> dict:
    return next(q for q in cards["questions"] if q["id"] == question)
