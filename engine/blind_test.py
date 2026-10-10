"""The blind test (docs/brief.md, "Blind test protocol"; week 3, 20-26 Oct 2026): three commands.

    python -m engine.blind_test capture [--date YYYY-MM-DD]
        Saves our answer to every blind-test question (eval/blind_test/questions.json) in
        eval/blind_test/answers/<date>/raw/ours/, as users see it (.md) and as data (.json), run the way the evaluation
        runs (writer profiles and live checks). Creates an empty file per rival and question (raw/vetted/<id>.md,
        raw/chatgpt/<id>.md) to paste the rival's answer into, a screenshots/ folder, an empty file per tool and
        question under shown/ for the answer testers will see, and capture.json with the exact wording to give the
        rivals. Protocol step 5: capture every rival answer on the same day, with the same wording, and keep
        screenshots. Never overwrites a rival's answer already pasted.

    python -m engine.blind_test packets <answers folder> <testers.csv> [--seed N]
        testers.csv has the columns tester,category: skincare or kitchen (the tester gets that category's questions)
        or any (the questions fewest testers have so far). Each tester gets 5 questions; for each one, the three
        answers to show (shown/<tool>/<id>.md) named only A, B and C, in an order balanced across testers. Writes
        packets/<tester>.md and key.json (which letter is which tool). Refuses, writing nothing, while an answer to
        show is empty or names a tool ("ChatGPT", "Vetted"...).

    python -m engine.blind_test tally <answers folder> <responses.csv>
        responses.csv has the columns tester,question,choice,confidence,comment (choice A, B or C; confidence 1 to 5).
        Prints how often ours was chosen against each rival (the brief's target: at least 60% against each), with
        the 95% range such a small sample allows, the confidence per tool, and every comment by the tool chosen.

The answers folder is never committed (.gitignore): our answers quote Reddit, and the rivals' answers and the testers'
names aren't ours to publish. How each tool's raw answer becomes the answer shown (protocol step 3: "names removed,
formatting matched") is Noemi's decision; until then shown/ is filled by hand.
"""

import csv
import json
import math
import random
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from itertools import permutations
from pathlib import Path

from engine.answer import answer_to_dict
from engine.config import BLIND_TEST_GIVEAWAYS, BLIND_TEST_QUESTIONS_PER_TESTER, BLIND_TEST_TARGET
from engine.pipeline import answer_request
from engine.slice_eval import DEFAULT_QUESTIONS

TOOLS = ("ours", "vetted", "chatgpt")
RIVALS = ("vetted", "chatgpt")
LETTERS = ("A", "B", "C")
CATEGORIES = ("skincare", "kitchen", "any")
DEFAULT_ANSWERS_DIR = Path(__file__).resolve().parents[1] / "eval" / "blind_test" / "answers"


class BlindTestError(Exception):
    """A file the blind test reads is missing, malformed or not ready; the message says which and why."""


def _questions(questions_path: Path) -> list[dict]:
    return json.loads(Path(questions_path).read_text(encoding="utf-8"))["questions"]


# --- 1. Capture ---

def capture(questions_path: Path, answers_dir: Path, day: date, profiles=None, live_checker=None) -> Path:
    """Our answer to every question, saved in answers_dir/<day>/raw/ours, with empty files for the rivals' answers
    and the answers to show (an existing file is never emptied). Returns the day's folder. `profiles` and
    `live_checker`: as in engine.pipeline.answer_request."""
    folder = Path(answers_dir) / day.isoformat()
    questions = _questions(questions_path)
    for name in ["raw/" + tool for tool in TOOLS] + ["shown/" + tool for tool in TOOLS] + ["screenshots"]:
        (folder / name).mkdir(parents=True, exist_ok=True)
    for q in questions:
        run = answer_request(q["text"], profiles=profiles, live_checker=live_checker)
        (folder / "raw" / "ours" / f"{q['id']}.md").write_text(run.text(), encoding="utf-8")
        data = answer_to_dict(run.answer) if run.answer is not None else None
        (folder / "raw" / "ours" / f"{q['id']}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                                                 encoding="utf-8")
        for path in [folder / "raw" / rival / f"{q['id']}.md" for rival in RIVALS] + \
                    [folder / "shown" / tool / f"{q['id']}.md" for tool in TOOLS]:
            if not path.exists():
                path.write_text("", encoding="utf-8")
    (folder / "capture.json").write_text(json.dumps({
        "captured_on": day.isoformat(),
        "note": "Ask each rival exactly these questions, on this day, and keep a screenshot of each answer in "
                "screenshots/.",
        "questions": [{"id": q["id"], "category": q["category"], "text": q["text"]} for q in questions],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return folder


# --- 2. Packets ---

@dataclass(frozen=True)
class Tester:
    __test__ = False  # not a test class, whatever pytest thinks of its name

    id: str
    category: str  # skincare, kitchen or any


def load_testers(path: Path) -> list[Tester]:
    """The testers, in the file's order. Refuses a file without the columns tester,category, an unknown category,
    a tester listed twice, or no testers, naming the line."""
    with Path(path).open(encoding="utf-8", newline="") as f:
        rows = list(csv.reader(f))
    if not rows or [cell.strip() for cell in rows[0]] != ["tester", "category"]:
        raise BlindTestError(f"{path}: the first line must be the columns tester,category")
    testers, seen = [], set()
    for number, row in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in row):
            continue
        if len(row) != 2 or row[1].strip() not in CATEGORIES:
            raise BlindTestError(f"{path}, line {number}: give a tester and a category ({', '.join(CATEGORIES)})")
        tester = Tester(row[0].strip(), row[1].strip())
        if tester.id in seen:
            raise BlindTestError(f"{path}, line {number}: {tester.id} is listed twice")
        seen.add(tester.id)
        testers.append(tester)
    if not testers:
        raise BlindTestError(f"{path}: no testers")
    return testers


def assign_questions(testers: list[Tester], questions: list[dict],
                     per_tester: int = BLIND_TEST_QUESTIONS_PER_TESTER) -> dict[str, list[str]]:
    """{tester: question ids, in the file's order}. A tester of a category gets that category's first `per_tester`
    questions (protocol step 2: 5 of the 10, and with 5 per category a skincare tester sees every skincare question).
    A tester of any category gets the questions the fewest testers have so far, the file's order breaking ties."""
    seen = {q["id"]: 0 for q in questions}
    order = {q["id"]: i for i, q in enumerate(questions)}
    assigned = {}
    for tester in testers:
        if tester.category == "any":
            chosen = sorted(seen, key=lambda qid: (seen[qid], order[qid]))[:per_tester]
        else:
            chosen = [q["id"] for q in questions if q["category"] == tester.category][:per_tester]
        assigned[tester.id] = sorted(chosen, key=order.get)
        for qid in chosen:
            seen[qid] += 1
    return assigned


def order_for(tester_index: int, question_index: int, seed: int) -> tuple[str, ...]:
    """The order of the three tools for one tester and question (A first). The six possible orders, shuffled once by
    the seed, are taken in turn, so across six testers each order comes up once and no tool sits first more often."""
    orders = list(permutations(TOOLS))
    random.Random(seed).shuffle(orders)
    return orders[(tester_index + question_index) % len(orders)]


def build_packets(folder: Path, questions_path: Path, testers: list[Tester], seed: int,
                  per_tester: int = BLIND_TEST_QUESTIONS_PER_TESTER) -> dict:
    """Writes folder/packets/<tester>.md and folder/key.json, and returns the key: {tester: {question id: {letter:
    tool}}}. Everything is checked first: an empty answer to show, or one naming a tool, stops it before any file is
    written."""
    folder = Path(folder)
    questions = _questions(questions_path)
    assigned = assign_questions(testers, questions, per_tester)
    needed = sorted({qid for qids in assigned.values() for qid in qids})
    answers, problems = {}, []
    for qid in needed:
        for tool in TOOLS:
            relative = f"shown/{tool}/{qid}.md"
            path = folder / relative
            text = path.read_text(encoding="utf-8").strip() if path.exists() else ""
            if not text:
                problems.append(f"{relative} is empty")
            elif giveaway := _giveaway(text):
                problems.append(f'{relative} names a tool ("{giveaway}")')
            answers[(tool, qid)] = text
    if problems:
        raise BlindTestError("Not ready for packets:\n  " + "\n  ".join(problems))
    index = {q["id"]: i for i, q in enumerate(questions)}
    texts = {q["id"]: q["text"] for q in questions}
    key: dict[str, dict] = {}
    (folder / "packets").mkdir(exist_ok=True)
    for tester_index, tester in enumerate(testers):
        key[tester.id] = {}
        lines = [f"# Blind test: {tester.id}", "",
                 "For each question below there are three answers, from three different tools, in no particular "
                 "order. Read all three, then say which one you would trust with your own money, how confident you "
                 "are from 1 to 5, and, if you like, why.", ""]
        for number, qid in enumerate(assigned[tester.id], start=1):
            order = order_for(tester_index, index[qid], seed)
            key[tester.id][qid] = dict(zip(LETTERS, order))
            lines += [f'## Question {number}: "{texts[qid]}"', ""]
            for letter, tool in zip(LETTERS, order):
                lines += [f"### Answer {letter}", "", answers[(tool, qid)], ""]
            lines += ["**Which would you trust with your own money?** A / B / C", "",
                      "**How confident are you, from 1 to 5?**", "", "**Why? (optional)**", "", "---", ""]
        (folder / "packets" / f"{tester.id}.md").write_text("\n".join(lines), encoding="utf-8")
    (folder / "key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    return key


def _giveaway(text: str) -> str | None:
    """The first tool name the text gives away (config.BLIND_TEST_GIVEAWAYS, any case), or None."""
    for name in BLIND_TEST_GIVEAWAYS:
        if re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", text, re.IGNORECASE):
            return name
    return None


# --- 3. Tally ---

@dataclass(frozen=True)
class Response:
    line: int
    tester: str
    question: str
    choice: str
    confidence: str
    comment: str


@dataclass
class Tally:
    total: int = 0
    choices: dict[str, int] = field(default_factory=lambda: {tool: 0 for tool in TOOLS})
    against: dict[str, tuple[int, int]] = field(default_factory=dict)  # {rival: (ours chosen, rival chosen)}
    confidence: dict[str, float] = field(default_factory=dict)  # {tool: mean confidence when chosen}
    comments: dict[str, list[str]] = field(default_factory=lambda: {tool: [] for tool in TOOLS})


def load_responses(path: Path) -> list[Response]:
    """The testers' responses, each with its line number. Refuses a file without the columns
    tester,question,choice,confidence (comment is optional)."""
    with Path(path).open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        columns = [c.strip() for c in reader.fieldnames or []]
        if not {"tester", "question", "choice", "confidence"} <= set(columns):
            raise BlindTestError(f"{path}: the first line must be the columns tester,question,choice,confidence,"
                                 "comment")
        return [Response(number, (row.get("tester") or "").strip(), (row.get("question") or "").strip(),
                         (row.get("choice") or "").strip().upper(), (row.get("confidence") or "").strip(),
                         (row.get("comment") or "").strip())
                for number, row in enumerate(reader, start=2)]


def tally(folder: Path, responses: list[Response]) -> Tally:
    """The choices, by tool, read through folder/key.json. Refuses a response for a tester or question the key
    doesn't have, a choice other than A, B or C, a confidence outside 1 to 5, or a second response from a tester to
    the same question, naming the line."""
    key = json.loads((Path(folder) / "key.json").read_text(encoding="utf-8"))
    result, confidences, answered = Tally(), {tool: [] for tool in TOOLS}, set()
    for r in responses:
        where = f"responses, line {r.line}"
        if r.tester not in key:
            raise BlindTestError(f"{where}: tester {r.tester} has no packet")
        if r.question not in key[r.tester]:
            raise BlindTestError(f"{where}: question {r.question} isn't in {r.tester}'s packet")
        if r.choice not in LETTERS:
            raise BlindTestError(f"{where}: the choice must be A, B or C")
        if r.confidence not in {"1", "2", "3", "4", "5"}:
            raise BlindTestError(f"{where}: the confidence must be 1 to 5")
        if (r.tester, r.question) in answered:
            raise BlindTestError(f"{where}: {r.tester} already answered {r.question}")
        answered.add((r.tester, r.question))
        tool = key[r.tester][r.question][r.choice]
        result.total += 1
        result.choices[tool] += 1
        confidences[tool].append(int(r.confidence))
        if r.comment:
            result.comments[tool].append(r.comment)
    result.against = {rival: (result.choices["ours"], result.choices[rival]) for rival in RIVALS}
    result.confidence = {tool: sum(c) / len(c) for tool, c in confidences.items() if c}
    return result


def wilson_range(wins: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """The 95% range of a share of wins out of `total` (Wilson's interval): with 50 choices, 62% could be anywhere
    from about 48% to 74%."""
    if total == 0:
        return 0.0, 1.0
    share = wins / total
    centre = (share + z * z / (2 * total)) / (1 + z * z / total)
    half = z * math.sqrt(share * (1 - share) / total + z * z / (4 * total * total)) / (1 + z * z / total)
    return max(0.0, centre - half), min(1.0, centre + half)


def tally_lines(result: Tally) -> list[str]:
    """The report: counts, shares, ranges, confidence and comments. No tester names."""
    if not result.total:
        return ["No responses yet."]
    lines = [f"{result.total} choices: " + ", ".join(
        f"{tool} chosen {result.choices[tool]} of {result.total} ({_percent(result.choices[tool], result.total)})"
        for tool in TOOLS)]
    for rival, (ours, theirs) in result.against.items():
        head_to_head = ours + theirs
        if not head_to_head:
            lines.append(f"against {rival}: neither was chosen yet")
            continue
        low, high = wilson_range(ours, head_to_head)
        verdict = "met" if ours / head_to_head >= BLIND_TEST_TARGET else "not met"
        lines.append(f"against {rival}: {ours} of {head_to_head} ({_percent(ours, head_to_head)}), 95% range "
                     f"{low:.0%} to {high:.0%}, target {BLIND_TEST_TARGET:.0%}: {verdict} (only the choices of ours "
                     f"or {rival} count)")
    for tool, mean in result.confidence.items():
        lines.append(f"confidence when {tool} was chosen: {mean:.1f} of 5")
    for tool in TOOLS:
        if result.comments[tool]:
            lines.append(f"why testers chose {tool}:")
            lines += [f"  - {comment}" for comment in result.comments[tool]]
    return lines


def _percent(part: int, whole: int) -> str:
    return f"{part / whole:.0%}"


# --- The command line ---

def main(argv: list[str]) -> int:
    try:
        if argv[:1] == ["capture"] and len(argv) in (1, 3) and (len(argv) == 1 or argv[1] == "--date"):
            from engine.pipeline import cached_profiles, live_checker

            day = date.fromisoformat(argv[2]) if len(argv) == 3 else date.today()
            folder = capture(DEFAULT_QUESTIONS, DEFAULT_ANSWERS_DIR, day, cached_profiles(), live_checker())
            print(f"Our answers saved in {folder}/raw/ours. Paste each rival's answer, asked today with the wording "
                  f"in capture.json, into raw/vetted and raw/chatgpt, with screenshots in screenshots/.")
            return 0
        if argv[:1] == ["packets"] and len(argv) in (3, 5) and (len(argv) == 3 or argv[3] == "--seed"):
            seed = int(argv[4]) if len(argv) == 5 else 0
            key = build_packets(Path(argv[1]), DEFAULT_QUESTIONS, load_testers(Path(argv[2])), seed)
            print(f"{len(key)} packets written in {Path(argv[1]) / 'packets'}; the key is key.json (never show it "
                  "to a tester).")
            return 0
        if argv[:1] == ["tally"] and len(argv) == 3:
            print("\n".join(tally_lines(tally(Path(argv[1]), load_responses(Path(argv[2]))))))
            return 0
    except (BlindTestError, OSError, ValueError) as e:
        print(e)
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
