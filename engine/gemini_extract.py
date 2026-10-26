"""Module 3's reading step through Google's Gemini: the AI reads a saved thread and writes its extraction (Noemi,
12 Oct 2026).

Until now every extraction (engine/extract.py) has been written by Claude Code under Noemi's plan, one thread at a
time, which is slow and uses up her plan. Gemini can do the same reading on its own: it gets the same instructions
(engine/prompts/extract_mentions.md) and the same reading view of the thread (engine.extract.render_thread), and answers
with the extraction as JSON. Nothing else changes: every quote is checked word for word against its comment by code
(engine.extract.check_extraction), and a quote that fails is dropped, whoever wrote it. Each file says who wrote it
("extractor": "gemini:<model>").

Noemi's conditions (12 Oct 2026): a quality test first, on her labelled gold threads, scored the way Claude's
extractions are (engine.extraction_eval); only if it holds up does Gemini read threads for answers. Under Google's
Gemini API terms, for users in the UK the paid-service data terms apply to free use too: what we send isn't used to
improve Google's products.

The key: GEM_API_KEY in .env. It is never printed and never put in a web address: it goes in the request's
x-goog-api-key header. No thread on the gold set's unlabelled list is ever sent (engine.gold.unlabelled_gold_ids).

Command line:
    python -m engine.gemini_extract <threads folder> <out folder> [--model M] [--thinking low|high] [thread id ...]
        sends each thread (every thread in the folder when no id is given) and writes <out folder>/extracted/<id>.json,
        with <out folder>/threads/ linking to the threads read, so `python -m engine.extract check <out folder>/threads`
        checks them; then prints what was written, skipped or failed.

The reader's fields (26 Oct 2026): each message ends with plain rules for the fields Gemini 3.1 Flash-Lite mixed up
(field_rules: the evidence LEVEL and the reason TAGS are two fields, the tags allowed, the post's id is never a comment
id), and the reply is asked for in a JSON Schema that only allows the allowed values (extraction_schema). Gemini
refusing the schema is not fatal (GeminiClient.generate). The instructions file (engine/prompts/extract_mentions.md) and
its version are untouched, so no existing extraction is out of date.

The free allowance's daily limit (14 Oct 2026, for on-demand reading): a 429 that names Gemini's per-day quota can't
pass before the day resets (midnight Pacific time), so it is never asked again after a pause (DailyLimitReached), and a
batch stops there, naming the threads it didn't send, rather than failing each of them in turn.
"""

import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import certifi
from pydantic import ValidationError

from engine.config import EVIDENCE_LEVELS, EVIDENCE_TAGS, MENTION_CATEGORIES, STANCE_VALUE
from engine.extract import DEFAULT_INSTRUCTIONS, Extraction, current_instructions_version, shown_comment_ids
from engine.gold import load_threads, unlabelled_gold_ids
from engine.parse_reddit import REPO_ROOT, _read_env_file

DEFAULT_MODEL = "gemini-3.8-flash"  # the newest Flash model on Noemi's key, 12 Oct 2026
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
KEY_NAME = "GEM_API_KEY"
MIN_INTERVAL = 6.0  # seconds between calls, well inside the free allowance's per-minute limit
TIMEOUT = 600  # seconds: a long thread's extraction can take a few minutes to write
# A busy model (503 "high demand", 429 "too many requests") is asked again after these pauses, in seconds; then the
# thread is reported as failed, to try again later (12 Oct 2026: the quality test met 503s).
BUSY_PAUSES = (30, 90, 240)
BUSY_STATUSES = (429, 500, 503)
# A long thread is read in parts of this many comments, each with the post (12 Oct 2026: on Noemi's labelled threads,
# Gemini read whole found 84% of her products, against Claude's 97%; a smaller part leaves it less to miss).
PART_COMMENTS = 40
# The extraction's lists, joined across a thread's parts.
LISTS = ("mentions", "notes", "care", "agreements")


class GeminiError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status  # the HTTP status Gemini answered, when it answered one


class DailyLimitReached(GeminiError):
    """Gemini's free allowance for the day is used up (a 429 naming its per-day quota): asking again before the day
    resets, midnight Pacific time, only fails again."""


# How a 429's answer names the daily quota: its QuotaFailure details give the quota's id, such as
# "GenerateRequestsPerDayPerProjectPerModel-FreeTier" (a per-minute one says "PerMinute": waiting a little helps).
_PER_DAY = re.compile(r"per[ _-]?day", re.IGNORECASE)


def is_daily_limit(status: int | None, answer: str) -> bool:
    """Whether Gemini's answer (its status and text) says the free allowance for the day is used up."""
    return status == 429 and bool(_PER_DAY.search(answer or ""))


def _key_from_env_file() -> str:
    return _read_env_file(REPO_ROOT / ".env").get(KEY_NAME, "")


def _post_json(url: str, headers: dict, body: bytes) -> dict:
    """POSTs the body and returns Gemini's JSON answer. Errors name the status, never the key."""
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT, context=ssl.create_default_context(cafile=certifi.where())) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        answer = e.read().decode("utf-8", "replace")
        if is_daily_limit(e.code, answer):  # the quota's id can sit past the first 300 characters
            raise DailyLimitReached(f"Gemini answered {e.code}: the free allowance for the day is used up",
                                    status=e.code) from None
        raise GeminiError(f"Gemini answered {e.code}: {answer[:300]}", status=e.code) from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise GeminiError(f"couldn't reach Gemini: {e}") from None


class GeminiClient:
    """Asks one Gemini model for a JSON answer, at most one call every `min_interval` seconds. `fetch` and `sleep`
    are there for the tests, so no test reaches the network."""

    def __init__(self, key: str | None = None, model: str = DEFAULT_MODEL,
                 fetch: Callable[[str, dict, bytes], dict] | None = None, sleep: Callable[[float], None] = time.sleep,
                 min_interval: float = MIN_INTERVAL, thinking: str | None = None):
        self._key = key
        self.model = model
        self.thinking = thinking  # "low" or "high": how much the model reasons first; None leaves its default
        self._fetch = fetch or _post_json
        self._sleep = sleep
        self.min_interval = min_interval
        self._last: float | None = None
        self.calls = 0
        self.schema_refused: str | None = None  # Gemini's 400 to a reply schema, once it has refused one

    def _ask(self, headers: dict, body: dict) -> dict:
        """One request, at the client's pace, asked again after a pause while the model is busy."""
        if self._last is not None:
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                self._sleep(wait)
        for pause in (*BUSY_PAUSES, None):
            self._last = time.monotonic()
            self.calls += 1
            try:
                return self._fetch(API.format(model=self.model), headers, json.dumps(body).encode("utf-8"))
            except GeminiError as e:
                if isinstance(e, DailyLimitReached):
                    raise
                if is_daily_limit(e.status, str(e)):  # never asked again after a pause: it can't pass today
                    raise DailyLimitReached(str(e), status=e.status) from None
                if e.status not in BUSY_STATUSES or pause is None:
                    raise
                self._sleep(pause)

    def generate(self, system: str, user: str, schema: dict | None = None) -> str:
        """The model's answer (JSON text) to the instructions `system` and the message `user`. With a `schema` (JSON
        Schema, sent as generationConfig.responseJsonSchema) the model can only write what it allows. Gemini's 400 to
        a schema is not fatal (26 Oct 2026): the same request goes again at once without it, and the schema is not
        sent again by this client (`schema_refused` holds Gemini's answer), so one bad schema costs one extra call."""
        key = self._key or os.environ.get(KEY_NAME) or _key_from_env_file()
        if not key:
            raise GeminiError(f"no Gemini key: put it in .env as {KEY_NAME}=...")
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "maxOutputTokens": 65536},
        }
        if self.thinking:
            body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": self.thinking}
        if schema is not None and self.schema_refused is None:
            body["generationConfig"]["responseJsonSchema"] = schema
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
        try:
            answer = self._ask(headers, body)
        except GeminiError as e:
            if e.status != 400 or "responseJsonSchema" not in body["generationConfig"]:
                raise
            self.schema_refused = str(e)[:300]
            print(f"Gemini refused the reply schema ({self.schema_refused}): reading without the schema.",
                  file=sys.stderr)
            del body["generationConfig"]["responseJsonSchema"]
            answer = self._ask(headers, body)
        try:
            return "".join(part.get("text", "") for part in answer["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError, TypeError):
            reason = answer.get("promptFeedback") if isinstance(answer, dict) else None
            raise GeminiError(f"Gemini's answer held no text ({reason or 'no candidates'})") from None


@dataclass
class ExtractReport:
    written: list[str] = field(default_factory=list)  # thread ids whose extraction was written
    skipped: list[str] = field(default_factory=list)  # never sent: gold threads Noemi hasn't labelled yet
    failed: dict[str, str] = field(default_factory=dict)  # thread id -> why nothing was written
    stopped: str | None = None  # why the batch stopped before its end (Gemini's daily limit), or None
    not_sent: list[str] = field(default_factory=list)  # thread ids left for another day when it stopped


def extract_threads(threads_dir: Path, out_dir: Path, client: GeminiClient, ids: Iterable[str] | None = None,
                    instructions: Path = DEFAULT_INSTRUCTIONS, part_comments: int = PART_COMMENTS) -> ExtractReport:
    """Sends each thread (those in `ids`, or all) to Gemini and writes its extraction under `out_dir`.

    The bookkeeping fields are ours, whatever the model wrote: the thread id, the instructions version followed, when,
    and "gemini:<model>" as the extractor. An answer that isn't a valid extraction is reported and nothing is written.
    """
    system = Path(instructions).read_text(encoding="utf-8")
    version = current_instructions_version(instructions)
    threads = {t.id: t for t in load_threads(Path(threads_dir), skip_broken=True)}
    wanted = list(ids) if ids else sorted(threads)
    never = unlabelled_gold_ids()
    (Path(out_dir) / "threads").mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / "extracted").mkdir(parents=True, exist_ok=True)
    report = ExtractReport()
    for number, thread_id in enumerate(wanted):
        if thread_id in never:
            report.skipped.append(thread_id)
            continue
        thread = threads.get(thread_id)
        if thread is None:
            report.failed[thread_id] = "no such thread in the folder"
            continue
        if thread.slimmed:  # only the comments answers use are kept (13 Oct 2026): never read for extraction
            report.skipped.append(thread_id)
            continue
        try:
            data = {name: [] for name in LISTS}
            shown = shown_comment_ids(thread)
            parts = [shown[i:i + part_comments] for i in range(0, len(shown), part_comments)] or [[]]
            for number, part in enumerate(parts, 1):
                user = (render_part(thread, part, number, len(parts)) + "\n\n" + field_rules(thread, part)
                        + f"\n\nWrite the extraction of these comments of thread {thread.id} as one JSON object, in "
                        "the format of the instructions' Output section, and nothing else.")
                answer = json.loads(client.generate(system, user, schema=extraction_schema(part)))
                if not isinstance(answer, dict):
                    raise ValueError("the answer isn't a JSON object")
                for name in LISTS:
                    data[name] += answer.get(name) or []
            data.update(thread_id=thread.id, instructions_version=version, extractor=f"gemini:{client.model}",
                        extracted_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
            Extraction.model_validate(data)
        except DailyLimitReached:
            report.stopped = "Gemini's free allowance for the day is used up: the rest wait for tomorrow"
            report.not_sent = [tid for tid in wanted[number:] if tid not in never]
            break
        except GeminiError as e:
            report.failed[thread_id] = str(e)
            continue
        except (ValueError, ValidationError) as e:  # json.JSONDecodeError is a ValueError
            report.failed[thread_id] = f"not a valid extraction: {str(e).splitlines()[0][:200]}"
            continue
        link = Path(out_dir) / "threads" / f"{thread.id}.json"
        if not link.exists():
            link.symlink_to((Path(threads_dir) / f"{thread.id}.json").resolve())
        (Path(out_dir) / "extracted" / f"{thread.id}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        report.written.append(thread.id)
    return report


# Which tags suit a comment that isn't first-hand use is the reader's call, comment by comment; these are the ones the
# rules name as examples (only those still in config.EVIDENCE_TAGS are named).
NOT_FIRST_HAND_EXAMPLES = (("secondhand", "someone else's experience"), ("asks about it", "a question about it"),
                           ("vague", "nothing concrete"))


def _quoted(words) -> str:
    return ", ".join(f'"{word}"' for word in words)


def field_rules(thread, comment_ids: list[str]) -> str:
    """Plain words, ending each message, on the fields Gemini mixed up (26 Oct 2026, on-demand reading with Gemini 3.1
    Flash-Lite): of 45 mentions the check dropped from 28 threads, 20 had the evidence LEVEL "no first-hand use" in
    evidence_tags (reason tags; that level is not one) and 2 had the post's own id as their comment id. The lists are
    config's (EVIDENCE_LEVELS, EVIDENCE_TAGS), so the words can't fall behind them. Nothing maps a wrong value to a
    right one here or anywhere: which tag fits depends on the comment, and engine.extract's check still drops it."""
    both = [level for level in EVIDENCE_LEVELS if level in EVIDENCE_TAGS]
    levels_only = [level for level in EVIDENCE_LEVELS if level not in EVIDENCE_TAGS]
    lines = [
        "Three fields are easy to mix up, so plainly:",
        f'- "evidence" holds one level, exactly one of: {_quoted(EVIDENCE_LEVELS)}.',
        f'- "evidence_tags" holds reason tags, a different field from "evidence": a list of at least one, and only '
        f"these, spelled exactly: {_quoted(EVIDENCE_TAGS)}.",
    ]
    if both:
        names = " and ".join(_quoted([level]) for level in both)
        lines.append(f"  The levels {names} are also tags: when the level is one of them, that tag fits too.")
    for level in levels_only:
        examples = [f'"{tag}" for {what}' for tag, what in NOT_FIRST_HAND_EXAMPLES if tag in EVIDENCE_TAGS]
        lines.append(f'  The level "{level}" is not a reason tag: never write it in "evidence_tags". When "evidence" '
                     f'is "{level}", give the tags that fit what the comment says instead'
                     + (f" ({', '.join(examples)})." if examples else "."))
    example = f" (such as [{comment_ids[0]}])" if comment_ids else ""
    lines.append(f'- "comment_id" is the id in square brackets that starts a comment\'s header above{example}. '
                 f"The thread's id, {thread.id}, is the post's, not a comment's: never write it as a comment_id. Only "
                 "comments count, so a product named only in the post's own text is not a mention.")
    return "\n".join(lines)


def extraction_schema(comment_ids: list[str]) -> dict:
    """The JSON Schema of the reply (Gemini's generationConfig.responseJsonSchema), so the model can only write allowed
    values: reason tags from config.EVIDENCE_TAGS, a level from config.EVIDENCE_LEVELS, a stance, a category and a
    comment id of this part's comments (never the post's). It has exactly the fields of the extraction models' lists
    (the thread id, version, time and extractor are ours, never the model's); a test keeps the two in step. A part
    with no comments gets no list of ids: Gemini refuses an empty one."""
    comment_id = {"type": "string"}
    if comment_ids:
        comment_id["enum"] = list(comment_ids)
    text = {"type": "string"}
    stance = {"type": "string", "enum": list(STANCE_VALUE)}

    def items(properties: dict, required: list[str]) -> dict:
        return {"type": "array", "items": {"type": "object", "properties": properties, "required": required}}

    mention = {
        "comment_id": comment_id, "product": text,
        "category": {"type": "string", "enum": list(MENTION_CATEGORIES)}, "product_type": text, "stance": stance,
        "evidence": {"type": "string", "enum": list(EVIDENCE_LEVELS)},
        "evidence_tags": {"type": "array", "minItems": 1, "items": {"type": "string", "enum": list(EVIDENCE_TAGS)}},
        "quote": text, "refers_to": {"type": "string", "enum": ["parent", "post", "earlier"]},
    }
    properties = {
        "mentions": items(mention, [name for name in mention if name != "refers_to"]),
        "notes": items({"comment_id": comment_id, "about": text, "stance": stance, "quote": text},
                       ["comment_id", "about", "stance", "quote"]),
        "care": items({"comment_id": comment_id, "about": text, "is_kind": {"type": "boolean"}, "tip": text,
                       "quote": text}, ["comment_id", "about", "is_kind", "tip", "quote"]),
        "agreements": items({"comment_id": comment_id, "quote": text}, ["comment_id", "quote"]),
    }
    return {"type": "object", "properties": properties, "required": list(properties)}


def render_part(thread, comment_ids: list[str], number: int, parts: int) -> str:
    """One part of a thread as the AI reads it: the post, then these comments, in engine.extract.render_thread's
    format (each comment with its id, what it replies to, score, author and flair), the parent of a reply looked up in
    the whole thread."""
    by_id = {c.id: c for c in thread.comments}
    usable = sum(c.status == "ok" for c in thread.comments)
    lines = [
        f"Thread {thread.id} in r/{thread.community} ({thread.category}): {thread.title}",
        thread.body.strip() or "(no post text)",
        f"--- part {number} of {parts}: {len(comment_ids)} of the thread's {usable} comments (the highest-scored, in "
        "thread order) ---",
    ]
    for comment_id in comment_ids:
        c = by_id[comment_id]
        author = c.author.name if c.author else "deleted account"
        flair = f" [{c.author.flair}]" if c.author and c.author.flair else ""
        header = f"[{c.id}] score {c.score} | {author}{flair}"
        if c.parent_id:
            parent = by_id.get(c.parent_id)
            snippet = " ".join((parent.body if parent else "").split())[:120]
            header += f" | reply to {c.parent_id}: \"{snippet}\""
        lines += ["", header, c.body]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    args = list(argv)
    model, thinking = DEFAULT_MODEL, None
    if "--model" in args:
        i = args.index("--model")
        model = args[i + 1]
        del args[i:i + 2]
    if "--thinking" in args:
        i = args.index("--thinking")
        thinking = args[i + 1]
        del args[i:i + 2]
    if len(args) < 2:
        print(__doc__)
        return 2
    threads_dir, out_dir, ids = Path(args[0]), Path(args[1]), args[2:]
    client = GeminiClient(model=model, thinking=thinking)
    report = extract_threads(threads_dir, out_dir, client, ids or None)
    print(f"Written ({len(report.written)}): {', '.join(report.written) or '-'}")
    if report.skipped:
        print(f"Never sent (gold threads Noemi hasn't labelled yet): {', '.join(report.skipped)}")
    for thread_id, reason in report.failed.items():
        print(f"Failed {thread_id}: {reason}")
    if report.stopped:
        print(f"Stopped: {report.stopped}. Not sent ({len(report.not_sent)}): {', '.join(report.not_sent)}")
    print(f"Gemini calls: {client.calls} ({model}). Check the quotes with: python -m engine.extract check {out_dir}/threads")
    return 1 if report.failed or report.stopped else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
