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
"""

import json
import os
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

from engine.extract import DEFAULT_INSTRUCTIONS, Extraction, current_instructions_version, render_thread
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


class GeminiError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status  # the HTTP status Gemini answered, when it answered one


def _key_from_env_file() -> str:
    return _read_env_file(REPO_ROOT / ".env").get(KEY_NAME, "")


def _post_json(url: str, headers: dict, body: bytes) -> dict:
    """POSTs the body and returns Gemini's JSON answer. Errors name the status, never the key."""
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT, context=ssl.create_default_context(cafile=certifi.where())) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        raise GeminiError(f"Gemini answered {e.code}: {detail}", status=e.code) from None
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

    def generate(self, system: str, user: str) -> str:
        """The model's answer (JSON text) to the instructions `system` and the message `user`."""
        key = self._key or os.environ.get(KEY_NAME) or _key_from_env_file()
        if not key:
            raise GeminiError(f"no Gemini key: put it in .env as {KEY_NAME}=...")
        if self._last is not None:
            wait = self.min_interval - (time.monotonic() - self._last)
            if wait > 0:
                self._sleep(wait)
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "maxOutputTokens": 65536},
        }
        if self.thinking:
            body["generationConfig"]["thinkingConfig"] = {"thinkingLevel": self.thinking}
        headers = {"x-goog-api-key": key, "Content-Type": "application/json"}
        for pause in (*BUSY_PAUSES, None):
            self._last = time.monotonic()
            self.calls += 1
            try:
                answer = self._fetch(API.format(model=self.model), headers, json.dumps(body).encode("utf-8"))
                break
            except GeminiError as e:
                if e.status not in BUSY_STATUSES or pause is None:
                    raise
                self._sleep(pause)
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


def extract_threads(threads_dir: Path, out_dir: Path, client: GeminiClient, ids: Iterable[str] | None = None,
                    instructions: Path = DEFAULT_INSTRUCTIONS) -> ExtractReport:
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
    for thread_id in wanted:
        if thread_id in never:
            report.skipped.append(thread_id)
            continue
        thread = threads.get(thread_id)
        if thread is None:
            report.failed[thread_id] = "no such thread in the folder"
            continue
        user = (render_thread(thread) + f"\n\nWrite the extraction of thread {thread.id} as one JSON object, in the "
                "format of the instructions' Output section, and nothing else.")
        try:
            data = json.loads(client.generate(system, user))
            if not isinstance(data, dict):
                raise ValueError("the answer isn't a JSON object")
            data.update(thread_id=thread.id, instructions_version=version, extractor=f"gemini:{client.model}",
                        extracted_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
            Extraction.model_validate(data)
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
    print(f"Gemini calls: {client.calls} ({model}). Check the quotes with: python -m engine.extract check {out_dir}/threads")
    return 1 if report.failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
