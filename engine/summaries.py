"""One-line summaries (Noemi's decision 4 of 13 Oct 2026: "let's do the one line summary and see how it turns out").

Under a pick's name (and an "Also worth a look" item's), one sentence in our own words saying what its credible
backers say: "Owners of 6 years say it still boils fast, but one owner finds the lid stiff." It is shown as "In
short:", marked as our summary, never in quotation marks and never as a quote.

Who writes it and when: like extraction, an AI step run offline by Claude Code under Noemi's plan, following
engine/prompts/summarise_pick.md, and saved as a file the engine reads: never written while someone waits for an
answer. The file is data/library/summaries.json (git-ignored with the library, since it paraphrases Reddit comments),
one entry per product, under its key: the category and the words of the name the product is shown under (summary_key,
the way module 4 makes a group's key). The name shown, not module 4's group key: a brand's line has one group key for
every type of product ("kitchen:lodge"), but "Lodge cast iron skillet line" and "Lodge Dutch oven line" are two
products, with two summaries ("kitchen:lodge cast iron skillet line", "kitchen:lodge dutch oven line"; 13 Oct 2026).

    {"kitchen:zojirushi kettle": {"product": "Zojirushi kettle", "category": "kitchen",
                                  "product_type": "electric kettle", "text": "...", "cites": ["c1aaaa", "c2bbbb"],
                                  "written_at": "2026-10-13T10:00:00Z", "writer": "claude-code",
                                  "instructions_version": "summarise-v1"}}

A summary depends on the product, not on the request, so one entry serves every answer that shows the product. Before
it is shown, code checks it in that answer (shown_problems, and engine.answer for the quotes), and a summary failing
any check is simply not shown:
- the text: one sentence, at most SUMMARY_MAX_WORDS words, no quotation marks (text_problems);
- every comment it cites is one of the product's credible mentions in this answer (a credible recommendation or
  warning, one per writer: engine.rank), still readable, and its quote passes the word-for-word check; with the live
  check on, the cited quotes are checked on Reddit too, like every shown quote (engine.pipeline);
- every number in the text (years, counts, prices, percentages) is written in one of the cited comments, in digits or
  in words; a number followed by a people word ("two owners", config.SUMMARY_PEOPLE_WORDS) counts people instead, and
  may not be more than the comments cited (number_problems). A number in the product's own name isn't checked;
- when the product has credible warnings in this answer, or a cited comment is one, the text acknowledges a downside:
  it holds a contrast or a drawback word (config.SUMMARY_DOWNSIDE_WORDS; acknowledges_downside).

Which products: every product that can be a pick or an "Also worth a look" item (Noemi, 13 Oct 2026: "why are we
giving In short just for a few recommendations instead of for all of them?"). That is every product that qualifies, or
is worth a look, in the ranking of an answer to one of these requests (all_requests), shown or not: a product ranked
fourth is shown when a request's budget or must-haves leave one of the first three out. The requests are those the
pre-check answers ahead (engine.precheck.requests_to_check: the search page's examples, the latency requests and every
product type by name, the open model's types included) and the sense evaluation's other requests; and for every
product type asked by name, also its wider reading (config.PIPELINE_MORE_THREADS threads, as an answer short of picks
reads), so a product that only qualifies there is covered too. Answers come from data/library without live checks.

Command line:
    python -m engine.summaries todo    which products need a summary: none yet, one written under older instructions,
                                       or one that wouldn't be shown in one of the answers where its product qualifies
                                       (with the reason). Writes data/library/summaries_todo.json, the writer's reading
                                       (git-ignored: it holds Reddit text); prints names and reasons only.
    python -m engine.summaries check   every entry checked, with reasons: its shape and text, its cited comments (still
                                       in the library and readable, their numbers), and, in each answer where its
                                       product qualifies, whether it would be shown. Exits 1 if any fails. Both answer
                                       about 90 requests: a few minutes.
"""

import json
import re
import sys
import threading
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

from pydantic import Field, ValidationError, field_validator

from engine.config import (
    PIPELINE_MORE_THREADS,
    SUMMARY_DOWNSIDE_WORDS,
    SUMMARY_MAX_WORDS,
    SUMMARY_PEOPLE_WORDS,
    THREAD_CATEGORIES,
)
from engine.match_products import normalize_name
from engine.models import Id, Record, UtcDatetime

REPO_ROOT = Path(__file__).resolve().parents[1]
SUMMARIES_FILE = "summaries.json"  # in the library folder: data/library/summaries.json
TODO_FILE = "summaries_todo.json"  # the writer's reading, next to it
DEFAULT_INSTRUCTIONS = REPO_ROOT / "engine" / "prompts" / "summarise_pick.md"
QUESTIONS_FILE = REPO_ROOT / "eval" / "blind_test" / "questions.json"  # the search page's examples
LATENCY_FILE = REPO_ROOT / "eval" / "edge_cases" / "latency_queries.json"
REQUEST_FILES = (QUESTIONS_FILE, LATENCY_FILE)
WIDER = "{request} ({threads} threads)"  # a wider reading's id: "electric kettle (48 threads)"


class Summary(Record):
    """One product's summary, as saved."""

    product: str = Field(min_length=1)  # the product's name when it was written, for whoever reads the file
    category: str
    product_type: str | None = None  # the type of product the answers asked for, when it was written
    text: str = Field(min_length=1)
    cites: list[Id] = Field(min_length=1)  # the comments it sums up: their ids
    written_at: UtcDatetime
    writer: str = Field(min_length=1)  # "claude-code"
    instructions_version: str = Field(min_length=1)  # "summarise-v1": the instructions it followed

    @field_validator("category")
    @classmethod
    def _known_category(cls, value: str) -> str:
        if value not in THREAD_CATEGORIES:
            raise ValueError(f"unknown category {value!r}; choose from: {', '.join(THREAD_CATEGORIES)}")
        return value


@dataclass(frozen=True)
class LoadedSummaries:
    entries: dict[str, Summary] = field(default_factory=dict)  # {product key: its summary}
    problems: list[str] = field(default_factory=list)  # entries left out, with the reason; or the file's own problem


def summary_key(category: str, name: str) -> str:
    """The key a product's summary is saved under: its category and the words of the name it is shown under
    (engine.match_products.normalize_name): "Lodge Dutch oven line" in kitchen is "kitchen:lodge dutch oven line"."""
    return f"{category}:{' '.join(normalize_name(name))}"


def current_version(instructions: Path = DEFAULT_INSTRUCTIONS) -> str:
    """The version the instructions' first line names ("Version: summarise-v1")."""
    first = Path(instructions).read_text(encoding="utf-8").splitlines()[0]
    return first.removeprefix("Version:").strip()


_loaded: dict[str, tuple[tuple, LoadedSummaries]] = {}  # path -> (its size and time, what it held)
_loaded_lock = threading.Lock()


def load_summaries(path: Path) -> LoadedSummaries:
    """The summaries in `path`: none when there is no file. An entry that doesn't load (a missing field, no cites, a
    key whose category isn't its entry's) is left out and named in `problems`, never the whole file; a file that isn't
    JSON is named the same way. Read again whenever the file changes."""
    path = Path(path)
    try:
        stat = path.stat()
    except FileNotFoundError:
        return LoadedSummaries()
    stamp = (stat.st_size, stat.st_mtime_ns)
    with _loaded_lock:
        kept = _loaded.get(str(path))
        if kept is not None and kept[0] == stamp:
            return kept[1]
    loaded = _read(path)
    with _loaded_lock:
        _loaded[str(path)] = (stamp, loaded)
    return loaded


def _read(path: Path) -> LoadedSummaries:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as error:
        return LoadedSummaries(problems=[f"{path.name}: not readable as JSON ({error})"])
    if not isinstance(data, dict):
        return LoadedSummaries(problems=[f"{path.name}: should map each product key to its summary"])
    entries, problems = {}, []
    for key, value in data.items():
        try:
            summary = Summary.model_validate(value)
        except ValidationError as error:
            reasons = "; ".join(f"{'.'.join(map(str, e['loc'])) or 'entry'}: {e['msg']}" for e in error.errors())
            problems.append(f"{path.name}: {key}: {reasons}")
            continue
        if not key.startswith(f"{summary.category}:"):
            problems.append(f"{path.name}: {key}: the key doesn't start with its category ({summary.category})")
            continue
        entries[key] = summary
    return LoadedSummaries(entries, problems)


# --- The text ---

# Quotation marks: double ones of any kind, an opening single one, and a straight or curly apostrophe opening a word
# ('like this'). An apostrophe inside or at the end of a word (it's, owners') is no quotation mark.
_QUOTATION = re.compile(r"[\"“”„«»‘]|(?:^|(?<=[\s(\[]))['’](?=\w)")
_SENTENCE_BREAK = re.compile(r"[.!?…][\"')\]]*\s+\S|\n")


def text_problems(text: str) -> list[str]:
    """What is wrong with a summary's text, in words; [] when it may be shown."""
    if not text.strip():
        return ["the text is empty"]
    problems = []
    words = len(text.split())
    if words > SUMMARY_MAX_WORDS:
        problems.append(f"it has {words} words; the most is {SUMMARY_MAX_WORDS}")
    if _QUOTATION.search(text):
        problems.append("it has quotation marks: a summary is never a quote")
    if _SENTENCE_BREAK.search(text.strip()):
        problems.append("it is more than one sentence")
    return problems


# --- Numbers ---

NUMBER_WORDS = {
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90, "hundred": 100, "dozen": 12,
}
# "one" is a number only before one of these ("one year") or a people word ("one owner"): "one of the best" isn't.
ONE_BEFORE = frozenset({"year", "years", "month", "months", "week", "weeks", "day", "days", "hour", "hours",
                        "decade", "decades", "time", "times"})
_TOKEN = re.compile(r"\d+(?:[.,]\d+)*|[a-z]+(?:['’-][a-z]+)*")
_PEOPLE = frozenset(SUMMARY_PEOPLE_WORDS)


@dataclass(frozen=True)
class Number:
    value: float
    written: str  # as the text writes it: "6", "six"
    people: bool  # a count of people ("two owners"), not a fact


def numbers_in(text: str) -> list[Number]:
    """Every number in a text, in order: digits ("6", "1.7", "£1,200", "5+", "2%"), number words ("six", "a dozen")
    and "one" before a unit or people word; each marked as a count of people when a people word follows it, straight
    after or after one more word ("two owners", "two long-time owners", "two of them")."""
    tokens = [m.group() for m in _TOKEN.finditer(text.lower())]
    found = []
    for i, token in enumerate(tokens):
        after = tokens[i + 1:i + 3]
        people = bool(after) and (after[0] in _PEOPLE or after[:2] == ["of", "them"]
                                  or (len(after) == 2 and after[1] in _PEOPLE and not _is_number(after[0])))
        if token[0].isdigit():
            found.append(Number(_digits(token), token, people))
        elif token in NUMBER_WORDS:
            found.append(Number(float(NUMBER_WORDS[token]), token, people))
        elif token == "one" and after and (after[0] in ONE_BEFORE or people):
            found.append(Number(1.0, token, people))
    return found


def _is_number(token: str) -> bool:
    return token[0].isdigit() or token in NUMBER_WORDS


def _digits(token: str) -> float:
    """"1,200" is 1200 and "1.7" is 1.7 (a comma before three digits groups thousands)."""
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", token):
        token = token.replace(",", "")
    return float(token.replace(",", "."))


def _values(text: str) -> set[float]:
    """Every number a comment writes, in digits or in words ("one" too, wherever it stands)."""
    values = {n.value for n in numbers_in(text)}
    values |= {1.0 for token in _TOKEN.findall(text.lower()) if token == "one"}
    return values


def number_problems(text: str, cited_texts: Iterable[str], cited: int, product_name: str = "") -> list[str]:
    """The numbers of a summary that its cited comments don't back: a fact number written in none of `cited_texts`, or a
    count of people over `cited` (the number of comments cited). Numbers in the product's own name aren't checked."""
    written = set().union(*(_values(t) for t in cited_texts)) if cited_texts else set()
    own = {n.value for n in numbers_in(product_name)}
    problems = []
    for number in numbers_in(text):
        if number.people:
            if number.value > cited:
                problems.append(f"it counts {number.value:g} people ({number.written}), but cites {cited} comment"
                                f"{'' if cited == 1 else 's'}")
        elif number.value not in written and number.value not in own:
            problems.append(f"the number {number.written} isn't in any comment it cites")
    return problems


# --- Downsides ---

_DOWNSIDE = re.compile(r"\b(?:" + "|".join(map(re.escape, SUMMARY_DOWNSIDE_WORDS)) + r")\b", re.IGNORECASE)


def acknowledges_downside(text: str) -> bool:
    """Whether a summary acknowledges a downside: it holds a contrast or a drawback word (config.SUMMARY_DOWNSIDE_WORDS:
    "but", "though", "warns", "complains"...), as a whole word. A simple rule, so it can be tested; whether the downside
    is told faithfully is judged by hand."""
    return bool(_DOWNSIDE.search(text))


# --- Before a summary is shown ---

def shown_problems(summary: Summary, credible: Mapping[str, str], bodies: Mapping[str, str],
                   has_warnings: bool) -> list[str]:
    """Why a summary can't be shown in this answer, in words; [] when it can (its quotes are checked word for word by
    engine.answer, which has the mentions). `credible` is the product's credible mentions in this answer, {comment id:
    stance}; `bodies` the comments as they are now, {comment id: text}; `has_warnings`: the product has credible
    warnings in this answer."""
    problems = text_problems(summary.text)
    cites = list(dict.fromkeys(summary.cites))
    for cid in cites:
        if cid not in credible:
            problems.append(f"cited comment {cid} isn't one of its credible mentions in this answer")
        elif cid not in bodies:
            problems.append(f"cited comment {cid} isn't readable any more")
    problems += number_problems(summary.text, [bodies[c] for c in cites if c in bodies], len(cites), summary.product)
    warned = has_warnings or any(credible.get(cid) == "warn" for cid in cites)
    if warned and not acknowledges_downside(summary.text):
        problems.append("it doesn't acknowledge a downside, though credible voices warn against it")
    return problems


# --- todo and check: the AI step's bookkeeping ---

class Request(NamedTuple):
    """One request to answer: its id (from its file, else the request itself), the request, and whether to read it
    wider (config.PIPELINE_MORE_THREADS threads, more_threads off) instead of as an answer does."""

    id: str
    text: str
    wider: bool = False


def all_requests(questions: Path = QUESTIONS_FILE, latency: Path = LATENCY_FILE, library_dir: Path | None = None,
                 extra: Iterable[str] | None = None) -> list[Request]:
    """Every request whose answers' products need a summary (13 Oct 2026): the pre-check's (engine.precheck.
    requests_to_check: the examples in `questions`, the latency requests in `latency`, every product type by name and
    the open model's types), then `extra` (None: the sense evaluation's other requests), each once; then the wider
    reading of every product type asked by name. Ids come from the files where they have one."""
    from engine.library import DEFAULT_LIBRARY_DIR  # imported here: these modules import this one
    from engine.precheck import requests_to_check
    from engine.sense_eval import OTHER_REQUESTS

    texts = requests_to_check(questions, latency, library_dir or DEFAULT_LIBRARY_DIR)
    extra = list(OTHER_REQUESTS if extra is None else extra)
    texts += [text for text in extra if text not in texts]
    ids = dict((text, request_id) for request_id, text in requests_to_answer((questions, latency), missing_ok=True))
    named_types = [text for text in texts if text not in ids and text not in extra]
    found = [Request(ids.get(text, text), text) for text in texts]
    return found + [Request(WIDER.format(request=text, threads=PIPELINE_MORE_THREADS), text, True)
                    for text in named_types]


def requests_to_answer(files: Iterable[Path] = REQUEST_FILES, missing_ok: bool = False) -> list[tuple[str, str]]:
    """(id, request) for each request in the files (a "questions" or a "queries" list), in order, each request once."""
    found, seen = [], set()
    for path in files:
        if missing_ok and not Path(path).is_file():
            continue
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for item in data.get("questions", data.get("queries", [])):
            if item["text"] not in seen:
                seen.add(item["text"])
                found.append((item["id"], item["text"]))
    return found


@dataclass
class ProductToSummarise:
    """A pick or "Also worth a look" item that needs a summary, with what the writer reads to write one."""

    key: str  # summary_key: what its summary is saved under
    product: str
    category: str
    product_type: str | None
    requests: list[str] = field(default_factory=list)  # the ids of the answers where it can be shown
    reasons: list[str] = field(default_factory=list)  # why it needs one, by answer: "b06: no summary yet"
    # Its credible mentions in those answers, one per writer: comment_id, stance, voice, evidence, badges, quote, body,
    # url, shown (its quote is shown in an answer) and in_every_answer (a credible mention in each of them).
    credible: list[dict] = field(default_factory=list)
    has_credible_warnings: bool = False


@dataclass
class _Shown:
    """One product that can be shown in one answer: its ranking entry, and the comment ids of its quotes shown there
    (none when the answer doesn't show it)."""

    request_id: str
    product: object  # engine.rank.ProductScore
    shown: set[str]
    product_type: str | None
    bodies: Mapping[str, str]


def _answers(requests: Iterable[Request | tuple[str, str]], library_dir: Path, profiles=None,
             entries: Mapping[str, Summary] | None = None) -> list[_Shown]:
    """Every product that qualifies as a pick, or is worth a look, in the ranking of each request's answer, shown or
    not, from the library and without live checks (as engine.prices.todo answers): no comment is read on Reddit, and
    threads waiting for their live check count too. A wider request reads config.PIPELINE_MORE_THREADS threads."""
    from engine import pipeline  # here: the pipeline imports this module

    found = []
    for request in (Request(*r) for r in requests):
        wider = dict(max_threads=PIPELINE_MORE_THREADS, more_threads=None) if request.wider else {}
        run = pipeline.answer_request(request.text, library_dir=library_dir, profiles=profiles,
                                      live_check_required=False, summaries=entries, **wider)
        if run.answer is None:
            continue
        quotes = {item.product_key: {q.comment_id for q in [*item.quotes, *item.downsides]}
                  for item in [*run.answer.picks, *run.answer.worth_a_look]}
        for product in run.ranking.products:
            if product.qualifies or product.worth_a_look:
                found.append(_Shown(request.id, product, quotes.get(product.key, set()), run.query.product_type,
                                    run.bodies))
    return found


def todo(requests: Iterable[Request | tuple[str, str]], library_dir: Path, profiles=None) -> list[ProductToSummarise]:
    """The products that can be a pick or an "Also worth a look" item in the requests' answers (_answers) and need a
    summary: none yet, one written under older instructions, or one that wouldn't be shown in one of the answers where
    the product qualifies (engine.answer.summary_reasons, with the reason). In the order they are first met."""
    from engine.answer import summary_reasons

    loaded = load_summaries(Path(library_dir) / SUMMARIES_FILE)
    version = current_version()
    found: dict[str, ProductToSummarise] = {}
    per_answer: dict[str, list[_Shown]] = {}
    for item in _answers(requests, library_dir, profiles, loaded.entries):
        per_answer.setdefault(_key_of(item.product), []).append(item)
    for key, shown in per_answer.items():
        product = shown[0].product
        entry = loaded.entries.get(key)
        reasons = [f"{s.request_id}: {reason}" for s in shown for reason in summary_reasons(s.product, entry, s.bodies)]
        if entry is not None and entry.instructions_version != version:
            reasons.append(f"written under older instructions ({entry.instructions_version}; now {version})")
        if not reasons:
            continue
        found[key] = ProductToSummarise(key, product.name, product.mentions[0].category, shown[0].product_type,
                                        list(dict.fromkeys(s.request_id for s in shown)), reasons,
                                        _credible(shown), any(s.product.credible_warnings for s in shown))
    return list(found.values())


def _key_of(product) -> str:
    """The summary key of a ranked product (engine.rank.ProductScore)."""
    return summary_key(product.mentions[0].category, product.name)


def _credible(shown: list[_Shown]) -> list[dict]:
    """A product's credible mentions across the answers that show it, for the writer, best first."""
    every = [{m.comment_id for m in [*s.product.credible_recommendations, *s.product.credible_warnings]} for s in shown]
    rows: dict[str, dict] = {}
    for s in shown:
        for m in [*s.product.credible_recommendations, *s.product.credible_warnings]:
            row = rows.setdefault(m.comment_id, {
                "comment_id": m.comment_id, "stance": m.stance, "voice": m.voice, "evidence": m.evidence,
                "badges": list(m.badges), "quote": m.quote, "body": s.bodies.get(m.comment_id, ""),
                "url": m.comment_url, "shown": False,
                "in_every_answer": all(m.comment_id in ids for ids in every)})
            row["shown"] = row["shown"] or m.comment_id in s.shown
    return sorted(rows.values(), key=lambda r: (r["stance"] != "recommend", not r["shown"], r["comment_id"]))


def write_todo(found: list[ProductToSummarise], library_dir: Path) -> Path:
    """The writer's reading, data/library/summaries_todo.json (git-ignored with the library: it holds Reddit text)."""
    path = Path(library_dir) / TODO_FILE
    path.write_text(json.dumps({
        "instructions": str(DEFAULT_INSTRUCTIONS.relative_to(REPO_ROOT)),
        "instructions_version": current_version(),
        "made_at": _now().isoformat(timespec="seconds"),
        "products": [vars(item) for item in found],
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def check(library_dir: Path, requests: Iterable[Request | tuple[str, str]],
          profiles=None) -> tuple[list[str], list[str]]:
    """(problems, notes) for every entry of the library's summaries.json, each problem naming its entry: entries that
    don't load; each entry's text, instructions version, cited comments (in the library and still readable) and their
    numbers; then, in each of the requests' answers where its product can be shown (_answers), why it wouldn't be shown
    there. The notes name the entries whose product no answer can show (not a problem: the product may come back)."""
    from engine.answer import summary_reasons
    from engine.library_cache import loaded as loaded_library

    loaded = load_summaries(Path(library_dir) / SUMMARIES_FILE)
    problems = list(loaded.problems)
    version = current_version()
    library = loaded_library(Path(library_dir) / "threads")
    readable = {c.id: c.body for t in library.threads for c in t.comments if c.status == "ok"}
    for key, entry in loaded.entries.items():
        mine = text_problems(entry.text)
        if entry.instructions_version != version:
            mine.append(f"written under older instructions ({entry.instructions_version}; now {version})")
        missing = [cid for cid in entry.cites if cid not in readable]
        mine += [f"cited comment {cid} isn't a readable comment in the library" for cid in missing]
        mine += number_problems(entry.text, [readable[c] for c in entry.cites if c in readable], len(set(entry.cites)),
                                entry.product)
        problems += [f"{key}: {problem}" for problem in mine]
    shown_keys = set()
    for item in _answers(list(requests), library_dir, profiles, loaded.entries) if loaded.entries else []:
        key = _key_of(item.product)
        entry = loaded.entries.get(key)
        if entry is None:
            continue
        shown_keys.add(key)
        problems += [f"{key}: in {item.request_id}: {reason}"
                     for reason in summary_reasons(item.product, entry, item.bodies)]
    notes = [f"{key}: its product isn't a pick or worth a look in any of these answers" for key in loaded.entries
             if requests and key not in shown_keys]
    return list(dict.fromkeys(problems)), notes


def main(argv: list[str], request_files: Iterable[Path] | None = None, library_dir: Path | None = None) -> int:
    """`request_files` and `library_dir` can be swapped for made-up ones, which is how the tests run it. It prints
    product names and reasons only: never a quote."""
    if argv not in (["todo"], ["check"]):
        print(__doc__)
        return 2
    from engine.library import DEFAULT_LIBRARY_DIR

    library_dir = Path(library_dir or DEFAULT_LIBRARY_DIR)
    requests = (requests_to_answer(request_files) if request_files is not None
                else all_requests(library_dir=library_dir))
    profiles = _profiles(library_dir)
    started = time.monotonic()
    if argv == ["todo"]:
        found = todo(requests, library_dir, profiles)
        path = write_todo(found, library_dir)
        print(f"Products that need a one-line summary, of those that can be shown in the answers to {len(requests)} "
              "requests (from the library, without live checks):")
        for item in found:
            print(f"  {item.key} ({item.product}; {', '.join(item.requests)}):")
            print("".join(f"    - {reason}\n" for reason in item.reasons), end="")
        print(f"{len(found)} product{'' if len(found) == 1 else 's'} to summarise. What to read: {path} "
              f"({time.monotonic() - started:.0f} s)")
        return 0
    problems, notes = check(library_dir, requests, profiles)
    entries = load_summaries(library_dir / SUMMARIES_FILE).entries
    failing = {problem.split(": ")[0] for problem in problems}
    fine = sum(key not in failing for key in entries)
    print(f"{len(entries)} summar{'y' if len(entries) == 1 else 'ies'} checked: {fine} fine"
          + (f", {len(entries) - fine} with problems" if len(entries) - fine else ""))
    for problem in problems:
        print(f"  - {problem}")
    for note in notes:
        print(f"  (note) {note}")
    print(f"({len(requests)} requests answered in {time.monotonic() - started:.0f} s)")
    return 1 if problems else 0


def _profiles(library_dir: Path):
    """Writers' standing as answers have it (engine.pipeline.cached_profiles) for the real library; none for another
    one, such as the tests' made-up libraries."""
    from engine.library import DEFAULT_LIBRARY_DIR

    if Path(library_dir).resolve() != Path(DEFAULT_LIBRARY_DIR).resolve():
        return None
    from engine.pipeline import cached_profiles

    return cached_profiles()


def _now() -> datetime:
    return datetime.now(UTC)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
