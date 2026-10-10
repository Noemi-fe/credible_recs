"""The blind test (docs/brief.md, "Blind test protocol"; week 3, 20-26 Oct 2026): three commands.

    python -m engine.blind_test capture [--date YYYY-MM-DD]
        Saves our answer to every blind-test question (eval/blind_test/questions.json) in
        eval/blind_test/answers/<date>/raw/ours/, as users see it (.md) and as data (.json), run the way the evaluation
        runs (writer profiles and live checks). Creates an empty file per rival and question (raw/vetted/<id>.md,
        raw/chatgpt/<id>.md) to paste the rival's answer into, a screenshots/ folder, an empty file per tool and
        question under shown/ for the answer testers will see, and capture.json with the exact wording to give the
        rivals. Protocol step 5: capture every rival answer on the same day, with the same wording, and keep
        screenshots. Never overwrites a rival's answer already pasted.

    python -m engine.blind_test shown <answers folder>
        Writes our answers into the template every tool's answer is shown in (eval/blind_test/FORMAT.md, Noemi's
        decision of 10 Oct 2026), from raw/ours/<id>.json into shown/ours/<id>.md: each pick's name, its reason, two
        quotes with what backs them, a downside and any caution, and the price, at most BLIND_TEST_WORDS_PER_PICK
        words a pick. The score breakdown, care tips and support line are left out. The rivals' answers are put into
        the same template by hand, by FORMAT.md's rules.

    python -m engine.blind_test packets <answers folder> <testers.csv> [--seed N]
        testers.csv has the columns tester,category: skincare or kitchen (the tester gets that category's questions)
        or any (the questions fewest testers have so far). Each tester gets 5 questions; for each one, the three
        answers to show (shown/<tool>/<id>.md) named only A, B and C, in an order balanced across testers. Writes
        packets/<tester>.md, the same as a plain page to give the tester (packets/<tester>.html), and key.json
        (which letter is which tool). Each question asks which answer the tester
        would trust with their own money, and which least, so every response ranks all three. Refuses, writing
        nothing, while an answer to show is empty, names a tool ("ChatGPT", "Vetted"...) or has a pick longer than
        BLIND_TEST_WORDS_PER_PICK words.

    python -m engine.blind_test tally <answers folder> <responses.csv> [--save]
        responses.csv has the columns tester,question,choice,least,confidence,comment (choice and least A, B or C,
        not the same; confidence 1 to 5). Prints how often ours was trusted more than each rival (the brief's target:
        at least 60% against each), with the 95% range such a small sample allows, the first choices, the
        confidence per tool, and every comment by the tool chosen. With --save, the result also goes into
        eval/metrics.json, which the how-we-score page shows (later evaluation runs keep it).

The answers folder is never committed (.gitignore): our answers quote Reddit, and the rivals' answers and the testers'
names aren't ours to publish. How each tool's raw answer becomes the answer shown (protocol step 3: "names removed,
formatting matched") is eval/blind_test/FORMAT.md (Noemi's decision, 10 Oct 2026).
"""

import csv
import html
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
from engine.config import (
    BLIND_TEST_GIVEAWAYS,
    BLIND_TEST_QUESTIONS_PER_TESTER,
    BLIND_TEST_TARGET,
    BLIND_TEST_WORDS_PER_PICK,
    BRAND_PICK_MODEL,
)
from engine.metrics import METRICS_FILE, MetricsError, save_blind_test
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


# --- 1b. The answer testers see (Noemi's decision, 10 Oct 2026: eval/blind_test/FORMAT.md) ---

QUOTES_SHOWN = 2  # pieces of evidence per pick, for every tool
MIN_CUT_WORDS = 12  # a part cut shorter than this says nothing, so it is left out instead
_PICK_HEADING = re.compile(r"^\*\*\d+\. .+\*\*$")


def shown_from_ours(data: dict | None, words: int = BLIND_TEST_WORDS_PER_PICK) -> str:
    """Our answer (engine.answer.answer_to_dict) in the template every tool's answer is shown in. Per pick: its name,
    its reason, its first two quotes with the badge that says what backs them (the writer's use when there is one),
    its first downside, its cautions and its price when known, at most `words` words, cut at a word. Our words only:
    the support line, score breakdown, care tips, links and availability are left out. With no picks, the answer's
    own message."""
    if data is None:
        return "No answer."
    if not data.get("picks"):
        return data.get("message") or "No picks."
    return "\n\n".join(_shown_pick(pick, words) for pick in data["picks"])


def _shown_pick(pick: dict, words: int) -> str:
    fixed = list(pick.get("cautions") or [])  # always kept: a caution is part of the pick
    availability = pick.get("availability") or {}
    if availability.get("second_hand"):  # vintage, sold second-hand only (Noemi, 10 Oct 2026): testers should know
        fixed.append("Sold second-hand only.")
    price = pick.get("price") or {}
    if price.get("amount") is not None and price.get("text"):
        fixed.append(f"Price: {price['text'].split(', checked')[0]}")
    parts = [pick["reason"].rstrip(".") + "."]
    if pick.get("model"):  # a brand pick's most recommended model (10 Oct 2026): our own words too
        price = f" ({pick['model_price'].split(', checked')[0]})" if pick.get("model_price") else ""
        parts[0] = BRAND_PICK_MODEL.format(model=pick["model"]) + price + ". " + parts[0]
    for quote in (pick.get("quotes") or [])[:QUOTES_SHOWN]:
        badge = _evidence_badge(quote.get("badges") or [])
        parts.append(f'"{_one_line(quote["text"])}"' + (f" ({badge})" if badge else ""))
    if pick.get("downsides"):
        parts.append(f'Downside: "{_one_line(pick["downsides"][0]["text"])}"')
    left = words - sum(len(line.split()) for line in fixed)
    kept = []
    for part in parts:
        count = len(part.split())
        if count <= left:
            kept.append(part)
            left -= count
            continue
        if left >= MIN_CUT_WORDS:
            kept.append(_cut(part, left))
        break
    return "\n\n".join([f"**{pick['rank']}. {pick['name']}**"] + kept + fixed)


def _one_line(text: str) -> str:
    """A quote on one line: line breaks and runs of spaces are formatting, not words. Links become labels, as for every
    tool (FORMAT.md rule 4): "[OXO non-stick pan](https://...)" -> "OXO non-stick pan (source)"."""
    return " ".join(_links_as_labels(text).split())


_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\((?:https?://[^)\s]+)\)")
_BARE_LINK = re.compile(r"<https?://[^>\s]+>|https?://\S+")


def _links_as_labels(text: str) -> str:
    return _BARE_LINK.sub("(source)", _MARKDOWN_LINK.sub(r"\1 (source)", text))


def _evidence_badge(badges: list[str]) -> str | None:
    """The badge that says what backs a quote: the writer's use ("five years of use"), else how well it was upvoted
    ("18 points, more than 86% of this thread's comments"), else none."""
    return next((b for b in badges if b.endswith(" use")), next((b for b in badges if " points" in b), None))


def _cut(text: str, words: int) -> str:
    """The first `words` words of the text, with "…" on the last, and a closing quote mark if the cut left one open:
    what is left of a quote is still word for word from its start."""
    kept = " ".join(text.split()[:words]) + "…"
    return kept + '"' if kept.count('"') % 2 else kept


def words_per_pick(shown: str) -> list[int]:
    """The words of each pick in a shown answer, its heading ("**1. Name**") left out."""
    counts: list[int] = []
    for line in shown.splitlines():
        if _PICK_HEADING.match(line.strip()):
            counts.append(0)
        elif counts:
            counts[-1] += len(line.split())
    return counts


def write_shown_ours(folder: Path) -> int:
    """Writes shown/ours/<id>.md from every raw/ours/<id>.json in the day's folder, and returns how many. The rivals'
    shown answers are never touched."""
    folder = Path(folder)
    count = 0
    for path in sorted((folder / "raw" / "ours").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        (folder / "shown" / "ours" / f"{path.stem}.md").write_text(shown_from_ours(data) + "\n", encoding="utf-8")
        count += 1
    return count


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
            else:
                problems += [f"{relative}: pick {number} has {count} words (at most {BLIND_TEST_WORDS_PER_PICK})"
                             for number, count in enumerate(words_per_pick(text), start=1)
                             if count > BLIND_TEST_WORDS_PER_PICK]
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
                 "order. Read all three, then say which one you would trust with your own money, which one you "
                 "would trust least, how confident you are from 1 to 5, and, if you like, why.", ""]
        for number, qid in enumerate(assigned[tester.id], start=1):
            order = order_for(tester_index, index[qid], seed)
            key[tester.id][qid] = dict(zip(LETTERS, order))
            lines += [f'## Question {number}: "{texts[qid]}"', ""]
            for letter, tool in zip(LETTERS, order):
                lines += [f"### Answer {letter}", "", answers[(tool, qid)], ""]
            lines += ["**Which would you trust with your own money?** A / B / C", "",
                      "**And which would you trust least?** A / B / C", "",
                      "**How confident are you, from 1 to 5?**", "", "**Why? (optional)**", "", "---", ""]
        (folder / "packets" / f"{tester.id}.md").write_text("\n".join(lines), encoding="utf-8")
        (folder / "packets" / f"{tester.id}.html").write_text(packet_page(tester.id, lines), encoding="utf-8")
    (folder / "key.json").write_text(json.dumps(key, indent=1), encoding="utf-8")
    return key


_PAGE_STYLE = ("body{font:17px/1.5 system-ui,sans-serif;max-width:42rem;margin:0 auto;padding:16px;"
               "background:#fff;color:#111}h3{margin-top:1.6em;border-top:1px solid #ccc;padding-top:.8em}"
               "hr{margin:2em 0}")


def packet_page(tester: str, lines: list[str]) -> str:
    """A tester's packet as a plain, phone-friendly web page, from its Markdown lines: headings, paragraphs, **bold**
    and rules only. Every text is escaped, so an answer can never add its own HTML."""
    body, paragraph = [], []

    def flush():
        if paragraph:
            body.append(f"<p>{_bold(' '.join(paragraph))}</p>")
            paragraph.clear()

    for line in lines:
        heading = re.match(r"^(#{1,3}) (.*)$", line)
        if heading:
            flush()
            level = len(heading.group(1))
            body.append(f"<h{level}>{html.escape(heading.group(2))}</h{level}>")
        elif line.strip() == "---":
            flush()
            body.append("<hr>")
        elif not line.strip():
            flush()
        else:
            paragraph.append(line.strip())
    flush()
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            f"<title>Blind test: {html.escape(tester)}</title><style>{_PAGE_STYLE}</style></head><body>\n"
            + "\n".join(body) + "\n</body></html>\n")


def _bold(text: str) -> str:
    """Escaped text, with Markdown's **bold** turned into <strong>."""
    parts = text.split("**")
    return "".join(f"<strong>{html.escape(part)}</strong>" if i % 2 else html.escape(part)
                   for i, part in enumerate(parts))


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
    choice: str  # the answer trusted most, with the tester's own money (the protocol's question)
    least: str  # the answer trusted least; the one left is the middle (Noemi's decision, 10 Oct 2026)
    confidence: str
    comment: str


@dataclass
class Tally:
    total: int = 0
    choices: dict[str, int] = field(default_factory=lambda: {tool: 0 for tool in TOOLS})  # trusted most
    least: dict[str, int] = field(default_factory=lambda: {tool: 0 for tool in TOOLS})  # trusted least
    # {rival: (rankings with ours above the rival, rankings)}: every response ranks all three, so each one counts.
    against: dict[str, tuple[int, int]] = field(default_factory=dict)
    confidence: dict[str, float] = field(default_factory=dict)  # {tool: mean confidence when chosen}
    comments: dict[str, list[str]] = field(default_factory=lambda: {tool: [] for tool in TOOLS})


def load_responses(path: Path) -> list[Response]:
    """The testers' responses, each with its line number. Refuses a file without the columns
    tester,question,choice,least,confidence (comment is optional)."""
    with Path(path).open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        columns = [c.strip() for c in reader.fieldnames or []]
        if not {"tester", "question", "choice", "least", "confidence"} <= set(columns):
            raise BlindTestError(f"{path}: the first line must be the columns tester,question,choice,least,"
                                 "confidence,comment")
        return [Response(number, (row.get("tester") or "").strip(), (row.get("question") or "").strip(),
                         (row.get("choice") or "").strip().upper(), (row.get("least") or "").strip().upper(),
                         (row.get("confidence") or "").strip(), (row.get("comment") or "").strip())
                for number, row in enumerate(reader, start=2)]


def tally(folder: Path, responses: list[Response]) -> Tally:
    """The rankings, by tool, read through folder/key.json. Refuses a response for a tester or question the key
    doesn't have, a choice or least other than A, B or C, the same answer as both, a confidence outside 1 to 5, or a
    second response from a tester to the same question, naming the line."""
    key = json.loads((Path(folder) / "key.json").read_text(encoding="utf-8"))
    result, confidences, answered = Tally(), {tool: [] for tool in TOOLS}, set()
    above = {rival: 0 for rival in RIVALS}
    for r in responses:
        where = f"responses, line {r.line}"
        if r.tester not in key:
            raise BlindTestError(f"{where}: tester {r.tester} has no packet")
        if r.question not in key[r.tester]:
            raise BlindTestError(f"{where}: question {r.question} isn't in {r.tester}'s packet")
        if r.choice not in LETTERS:
            raise BlindTestError(f"{where}: the choice must be A, B or C")
        if r.least not in LETTERS or r.least == r.choice:
            raise BlindTestError(f"{where}: the least trusted must be A, B or C, and not the choice")
        if r.confidence not in {"1", "2", "3", "4", "5"}:
            raise BlindTestError(f"{where}: the confidence must be 1 to 5")
        if (r.tester, r.question) in answered:
            raise BlindTestError(f"{where}: {r.tester} already answered {r.question}")
        answered.add((r.tester, r.question))
        letters = key[r.tester][r.question]
        middle = next(letter for letter in LETTERS if letter not in (r.choice, r.least))
        order = [letters[r.choice], letters[middle], letters[r.least]]  # most trusted first
        result.total += 1
        result.choices[order[0]] += 1
        result.least[order[2]] += 1
        for rival in RIVALS:
            above[rival] += order.index("ours") < order.index(rival)
        confidences[order[0]].append(int(r.confidence))
        if r.comment:
            result.comments[order[0]].append(r.comment)
    result.against = {rival: (above[rival], result.total) for rival in RIVALS}
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
    """The report: how often ours was trusted more than each rival, with its range, the first choices, confidence
    and comments. No tester names."""
    if not result.total:
        return ["No responses yet."]
    lines = []
    for rival, (wins, total) in result.against.items():
        low, high = wilson_range(wins, total)
        verdict = "met" if wins / total >= BLIND_TEST_TARGET else "not met"
        lines.append(f"against {rival}: ours trusted more in {wins} of {total} ({_percent(wins, total)}), 95% range "
                     f"{low:.0%} to {high:.0%}, target {BLIND_TEST_TARGET:.0%}: {verdict}")
    lines.append("first choice: " + ", ".join(
        f"{tool} {result.choices[tool]} of {result.total} ({_percent(result.choices[tool], result.total)})"
        for tool in TOOLS))
    lines.append("trusted least: " + ", ".join(f"{tool} {result.least[tool]}" for tool in TOOLS))
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
        if argv[:1] == ["shown"] and len(argv) == 2:
            count = write_shown_ours(Path(argv[1]))
            print(f"{count} of our answers written in {Path(argv[1]) / 'shown' / 'ours'}, in the template of "
                  "eval/blind_test/FORMAT.md. Put the rivals' answers into the same template by its rules.")
            return 0
        if argv[:1] == ["packets"] and len(argv) in (3, 5) and (len(argv) == 3 or argv[3] == "--seed"):
            seed = int(argv[4]) if len(argv) == 5 else 0
            key = build_packets(Path(argv[1]), DEFAULT_QUESTIONS, load_testers(Path(argv[2])), seed)
            print(f"{len(key)} packets written in {Path(argv[1]) / 'packets'}; the key is key.json (never show it "
                  "to a tester).")
            return 0
        if argv[:1] == ["tally"] and len(argv) in (3, 4) and (len(argv) == 3 or argv[3] == "--save"):
            result = tally(Path(argv[1]), load_responses(Path(argv[2])))
            print("\n".join(tally_lines(result)))
            if len(argv) == 4:
                save_blind_test(result.against, METRICS_FILE)
                print(f"Saved in {METRICS_FILE.name}: the how-we-score page (/how) now shows it.")
            return 0
    except (BlindTestError, MetricsError, OSError, ValueError) as e:
        print(e)
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
