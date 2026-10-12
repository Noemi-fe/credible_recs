"""The latency eval: how long an answer takes, end to end and stage by stage, on a fixed set of requests (12 Oct 2026).

Noemi (12 Oct 2026): "latency times are WAY too long". Warm answers took 8-14 s, and up to a minute when their quotes
weren't yet checked live. Every change made to speed them up is measured here first, and kept only when no answer
changes (the answer-equality guard, below). Each run is logged in eval/LATENCY.md.

    python eval/latency.py [--runs N] [--live] [--only ID,ID] [--no-cold] [--save-baseline] [--library DIR]

The requests: eval/edge_cases/latency_queries.json, the 10 blind-test questions and 12 others (the product types added
on 11 Oct 2026, the slowest known case, a clarifying question and a polite no). Each goes through
engine.pipeline.answer_request as the web demo runs it, on the FROZEN library snapshot data/eval/library_snapshot
(git-ignored: Reddit text), so the data builders adding threads to the live library meanwhile don't change the answers
under it. So that the answers can't drift either: writers' standing comes from the snapshot's own profile store (not
Arctic Shift's 48-hour cache), the day is fixed (FROZEN_DAY: prices' ages, module 2's "older than 3 years" rule).

The live check of shown quotes. By default a stand-in checker answers every check "shown" after a fixed pause
(STAND_IN_PAUSE, 0.3 s: Reddit's usual answer time), with no network, so changes are measured without network noise.
Like the real checker (engine.live_check.LiveChecker, whose cache keeps each comment for 48 hours), it remembers each
comment it has read: asking about it again costs nothing. With --live, the real checker is used, with an empty
temporary cache: real calls to Reddit's embed page, so use it sparingly (it is free, but a couple of full runs at most).
Either way the eval checks the rule that matters most: every quote an answer shows was checked live, and passed. A
quote shown without its check stops the run.

What it measures (seconds), each as p50 / p95 / max over the requests (per request, the median of its runs):
- warm, cached checks: a request asked again in a process that has answered it before, every comment already checked
  (the stand-in answers at once): the engine's own time;
- warm, uncached checks: the same, with the stand-in's memory emptied first, so each comment checked costs the pause;
- first ask: in a process that has answered another request and done what the web server does as it starts
  (engine.web.warm_up, when there is one), this request asked for the first time, uncached checks;
- cold: a fresh process, one per request: "start-up" is what a server does before its first request (the imports,
  and engine.web.warm_up when there is one: reading the library, loading the open model), then the first request
  (uncached checks). Reported both ways: start-up plus first request, and the first request alone, which is what the
  first visitor of a server that has finished getting ready waits for.
Then the time of each stage (module 1, the library, retrieval, ..., the live checks), its median and max over the
requests, each stage's own time without the stages it calls, so they add up to the whole. Times are wall-clock;
"cpu" is the process's processor time over the same request, steadier when other programs share the machine.

The answer-equality guard. --save-baseline saves each request's whole answer (engine.web.answer_json, the answer as
markdown, and the result's lists of what was left out and why) in data/eval/latency_baseline/ (git-ignored: it holds
Reddit quotes). Every run compares its answers with it and names each difference: a change that alters any answer
isn't kept. With --live, differences are expected wherever a comment was deleted or edited on Reddit since the snapshot
(the live check drops it), so they are listed but don't fail the run.
"""

import argparse
import contextlib
import functools
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))  # this checkout's engine, never another installed copy

QUERIES = REPO_ROOT / "eval" / "edge_cases" / "latency_queries.json"
DEFAULT_SNAPSHOT = REPO_ROOT / "data" / "eval" / "library_snapshot"
DEFAULT_BASELINE = REPO_ROOT / "data" / "eval" / "latency_baseline"
FROZEN_DAY = date(2026, 10, 12)  # the day the snapshot was taken: answers are judged on it
FROZEN_NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
STAND_IN_PAUSE = 0.3  # seconds the stand-in checker takes for a comment it hasn't read yet
WARM_UP_REQUEST = "slow cooker that lasts"  # not in the set: loads the library and the open model before "first ask"
SIXTEEN_THREAD_TARGETS = {"cached": 2.0, "uncached": 6.0}  # Noemi's targets (12 Oct 2026), warm 16-thread answers
# The answers that read more than 16 threads (48 at most: l02 on the snapshot), warm, uncached checks. The orchestrator's
# slow case, "anti-dandruff shampoo" (l01), read 48 threads on the live library when live checks dropped comments; on the
# snapshot, with every check passing, its first 16 threads give 3 picks.
WIDER_TARGET = 10.0


# --- The live checkers ---

class StandInChecker:
    """Answers every check "shown" after STAND_IN_PAUSE, without the network; a comment it has read before (by its
    link) is answered at once, as the real checker's cache does. Safe to call from several threads at once. It keeps
    every check it was asked, so the eval can tell that each quote shown was checked."""

    def __init__(self, pause: float = STAND_IN_PAUSE):
        self.pause = pause
        self._read: set[str] = set()
        self._lock = threading.Lock()
        self.asked: list[tuple[str, str]] = []  # (comment link, quote), every check asked
        self.passed: set[tuple[str, str]] = set()

    def check(self, comment_url: str, quote: str):
        from engine.live_check import LiveResult

        with self._lock:
            new = comment_url not in self._read
            self._read.add(comment_url)
        if new and self.pause:
            time.sleep(self.pause)
        with self._lock:
            self.asked.append((comment_url, quote))
            self.passed.add((comment_url, quote))
        return LiveResult("ok", "the stand-in shows everything")

    def forget(self) -> None:
        """Empties its memory of comments read: every comment costs the pause again."""
        with self._lock:
            self._read.clear()

    def new_request(self) -> None:
        with self._lock:
            self.asked.clear()
            self.passed.clear()


class RecordingChecker:
    """The real checker (--live), keeping every check asked and the ones that passed, for the same rule."""

    def __init__(self, cache_dir: Path):
        from engine.live_check import LiveChecker

        self.real = LiveChecker(cache_dir=cache_dir)
        self.cache_dir = cache_dir
        self._lock = threading.Lock()
        self.asked: list[tuple[str, str]] = []
        self.passed: set[tuple[str, str]] = set()

    def check(self, comment_url: str, quote: str):
        outcome = self.real.check(comment_url, quote)
        with self._lock:
            self.asked.append((comment_url, quote))
            if outcome.show:
                self.passed.add((comment_url, quote))
        return outcome

    def forget(self) -> None:
        shutil.rmtree(self.cache_dir, ignore_errors=True)

    def new_request(self) -> None:
        with self._lock:
            self.asked.clear()
            self.passed.clear()


# --- Timing each stage ---

# (module, function, stage): the pipeline's steps, each timed on its own. A name another change has removed is skipped.
STAGES = [
    ("engine.pipeline", "parse_query", "1 understand the request"),
    ("engine.pipeline", "load_checked", "library: load and check"),
    ("engine.pipeline", "loaded_library", "library: load and check"),
    ("engine.pipeline", "LocalSource.find_threads", "2 find threads"),
    ("engine.pipeline", "with_profiles", "writers' profiles"),
    ("engine.pipeline", "group_products", "4 group products"),
    ("engine.pipeline", "_groups_to_rank", "4 types and brand picks"),
    ("engine.pipeline", "_within_budget", "prices and availability"),
    ("engine.pipeline", "_suited_to_request", "product facts"),
    ("engine.pipeline", "_unsuited_kinds", "product facts"),
    ("engine.pipeline", "group_kinds", "4 kinds"),
    ("engine.pipeline", "contradicting_writers", "5 contradictions"),
    ("engine.pipeline", "_score", "5 credibility"),
    ("engine.pipeline", "_ranked", "6 ranking"),
    ("engine.pipeline", "_fold_brand_picks", "6 ranking"),
    ("engine.pipeline", "_fold_brand_skips", "6 ranking"),
    ("engine.pipeline", "_brand_models", "6 ranking"),
    ("engine.pipeline", "_care_tips", "care tips"),
    ("engine.pipeline", "write_answer", "7 write the answer"),
    ("engine.pipeline", "_check_live", "live checks"),
]


class StageClock:
    """Wraps the pipeline's steps (STAGES) to add up each one's own time: a step's time less the timed steps it calls,
    so the stages add up to the whole request. Each thread keeps its own stack."""

    def __init__(self):
        self.totals: dict[str, float] = defaultdict(float)
        self._local = threading.local()

    def install(self) -> None:
        import importlib

        for module_name, path, stage in STAGES:
            owner = importlib.import_module(module_name)
            *parents, name = path.split(".")
            for parent in parents:
                owner = getattr(owner, parent, None)
            if owner is not None and callable(getattr(owner, name, None)):
                setattr(owner, name, self._timed(getattr(owner, name), stage))

    def reset(self) -> dict[str, float]:
        totals, self.totals = dict(self.totals), defaultdict(float)
        return totals

    def _timed(self, function, stage: str):
        clock = self

        @functools.wraps(function)
        def timed(*args, **kwargs):
            stack = clock._stack()
            stack.append(0.0)  # time spent in the timed steps it calls
            started = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - started
                inner = stack.pop()
                clock.totals[stage] += elapsed - inner
                if stack:
                    stack[-1] += elapsed

        return timed

    def _stack(self) -> list[float]:
        if not hasattr(self._local, "stack"):
            self._local.stack = []
        return self._local.stack


# --- Fixing time and data, so answers can't drift ---

def freeze_time() -> None:
    """Module 2's "older than 3 years" rule reads the clock (engine.sources.post_score): here it reads FROZEN_NOW."""
    import engine.sources

    class Frozen(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN_NOW if tz is None else FROZEN_NOW.astimezone(tz)

    engine.sources.datetime = Frozen


def snapshot_profiles(library: Path):
    """Writers' standing from the snapshot's profile store only, read as on FROZEN_NOW."""
    from engine.profiles import ProfileStore, StoredProfiles

    return StoredProfiles(ProfileStore(library / "profiles.json", clock=lambda: FROZEN_NOW), client=None)


# --- One request ---

def answer_record(result) -> dict:
    """Everything the guard compares: the answer as the web demo sends it, as markdown, and what was left out and why."""
    from engine.web import answer_json

    record = answer_json(result)
    record["markdown"] = result.text()
    record["details"] = {
        "left_out_as_other_type": list(result.left_out_as_other_type),
        "left_out_loose": list(result.left_out_loose),
        "left_out_over_budget": list(result.left_out_over_budget),
        "left_out_unavailable": list(result.left_out_unavailable),
        "not_priced": list(result.not_priced),
        "left_out_not_suited": [[n.name, n.reason] for n in result.left_out_not_suited],
        "folded_brand_picks": [[f.name, f.stepped_aside_for] for f in result.folded_brand_picks],
        "folded_skips": [[f.name, f.stepped_aside_for] for f in result.folded_skips],
        "notes_without_kind": list(result.notes_without_kind),
        "contradicting_writers": list(result.contradicting_writers),
        "threads_quoted": list(result.threads_quoted),
        "not_extracted": list(result.not_extracted),
        "waiting_live_check": list(result.waiting_live_check),
        "live_dropped": dict(sorted(result.live_dropped.items())),
        "skipped_files": len(result.skipped_files),
        "read_more": result.read_more,
    }
    return json.loads(json.dumps(record, ensure_ascii=False))  # as the file holds it: tuples as lists


def unchecked_quotes(result, checker) -> list[str]:
    """Where an answer shows a quote whose comment was never checked live, or didn't pass: must be none."""
    from engine.answer import _every_quote

    if result.answer is None:
        return []
    return [where for where, quote in _every_quote(result.answer) if (quote.url, quote.text) not in checker.passed]


def run_request(text: str, library: Path, profiles, checker, clock: StageClock) -> dict:
    """One request through the pipeline: its times, stages, answer record, and checks."""
    from engine.pipeline import answer_request

    clock.reset()
    checker.new_request()
    cpu, started = time.process_time(), time.perf_counter()
    result = answer_request(text, library_dir=library, profiles=profiles, today=FROZEN_DAY, live_checker=checker)
    seconds, cpu = time.perf_counter() - started, time.process_time() - cpu
    return {"seconds": seconds, "cpu": cpu, "stages": clock.reset(), "record": answer_record(result),
            "checks": len(checker.asked), "comments_checked": len({url for url, _ in checker.asked}),
            "unchecked": unchecked_quotes(result, checker), "threads": len(result.threads_used),
            "read_more": result.read_more, "status": result.query.status}


# --- Comparing answers ---

def differences(new, old, path: str = "") -> list[str]:
    """Where two answer records differ, as paths ("answer.picks[0].name"), each with a short view of both sides."""
    if isinstance(new, dict) and isinstance(old, dict):
        found = []
        for key in list(old) + [k for k in new if k not in old]:
            where = f"{path}.{key}" if path else str(key)
            if key not in new:
                found.append(f"{where}: missing now")
            elif key not in old:
                found.append(f"{where}: new")
            else:
                found += differences(new[key], old[key], where)
        return found
    if isinstance(new, list) and isinstance(old, list):
        found = [f"{path}: {len(old)} items before, {len(new)} now"] if len(new) != len(old) else []
        for i, (a, b) in enumerate(zip(new, old)):
            found += differences(a, b, f"{path}[{i}]")
        return found
    if new != old:
        return [f"{path}: {_short(old)} before, {_short(new)} now"]
    return []


def _short(value) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= 60 else text[:57] + "..."


# --- Numbers ---

def percentile(values: list[float], share: float) -> float:
    """The nearest-rank percentile: the smallest value with at least `share` of the values at or below it."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(share * len(ordered)) - 1)]


def spread(values: list[float]) -> str:
    if not values:
        return "n/a"
    return f"{percentile(values, 0.5):.2f} / {percentile(values, 0.95):.2f} / {max(values):.2f}"


# --- The passes ---

def load_queries(only: set[str] | None) -> list[dict]:
    queries = json.loads(QUERIES.read_text(encoding="utf-8"))["queries"]
    return [q for q in queries if not only or q["id"] in only]


def warm_passes(queries: list[dict], library: Path, runs: int, live: bool) -> dict:
    """First ask, then `runs` warm passes with cached checks and (stand-in only) with uncached ones, in this process."""
    from engine.pipeline import answer_request

    clock = StageClock()
    clock.install()
    profiles = snapshot_profiles(library)
    temporary = Path(tempfile.mkdtemp(prefix="latency-live-")) if live else None
    checker = RecordingChecker(temporary) if live else StandInChecker()
    answer_request(WARM_UP_REQUEST, library_dir=library, profiles=profiles, today=FROZEN_DAY,
                   live_checker=StandInChecker(pause=0))
    import engine.web

    if hasattr(engine.web, "warm_up"):  # what the server does before its first visitor, when it does anything
        engine.web.warm_up(library)
    passes: dict[str, dict[str, list[dict]]] = {"first ask": {}, "warm, cached": {}, "warm, uncached": {}}
    try:
        for q in queries:  # each asked for the first time
            if not live:  # its comments never checked (live: the run's cache is kept, so no comment is read twice)
                checker.forget()
            _ran(passes["first ask"], q, run_request(q["text"], library, profiles, checker, clock), "first ask")
        for _ in range(runs):
            for q in queries:  # asked again: every comment checked already (cached: kept since the first ask)
                _ran(passes["warm, cached"], q, run_request(q["text"], library, profiles, _instant(checker, live),
                                                            clock), "warm, cached")
            if live:
                continue  # uncached again would read every comment on Reddit again: once is enough
            for q in queries:
                checker.forget()
                _ran(passes["warm, uncached"], q, run_request(q["text"], library, profiles, checker, clock),
                     "warm, uncached")
    finally:
        if temporary is not None:
            shutil.rmtree(temporary, ignore_errors=True)
    return passes


def _instant(checker, live: bool):
    """The checker for "cached" passes: the stand-in with nothing left to read; the real one with its cache kept."""
    return checker if live else StandInChecker(pause=0)


def _ran(runs: dict[str, list[dict]], query: dict, run: dict, name: str) -> None:
    """Keeps a run, and says how it went (on stderr, so the report stays clean)."""
    runs.setdefault(query["id"], []).append(run)
    print(f"  {name:<16} {query['id']} {run['seconds']:6.2f} s  ({run['checks']} checks, {run['threads']} threads)",
          file=sys.stderr, flush=True)


def cold_runs(queries: list[dict], library: Path) -> dict[str, list[dict]]:
    """Each request as the first of a fresh process (this script with --one), with uncached stand-in checks."""
    found = {}
    for q in queries:
        command = [sys.executable, str(Path(__file__).resolve()), "--one", q["id"], "--library", str(library)]
        out = subprocess.run(command, capture_output=True, text=True, cwd=REPO_ROOT)
        lines = [line for line in out.stdout.splitlines() if line.startswith("{")]
        if out.returncode != 0 or not lines:
            raise RuntimeError(f"cold run of {q['id']} failed:\n{out.stderr[-2000:]}")
        found[q["id"]] = [json.loads(lines[-1])]
        print(f"  {'cold':<16} {q['id']} {found[q['id']][0]['seconds']:6.2f} s  (start-up "
              f"{found[q['id']][0]['startup']:.2f} s)", file=sys.stderr, flush=True)
    return found


def one_cold_request(query_id: str, library: Path) -> dict:
    """--one: the start-up a server does, then one request, timed, in this fresh process."""
    started = time.perf_counter()
    cpu = time.process_time()
    import engine.pipeline  # noqa: F401  (the imports are part of a cold start)
    import engine.web

    freeze_time()
    if hasattr(engine.web, "warm_up"):  # what the server does before taking requests, when it does anything
        engine.web.warm_up(library)
    startup = time.perf_counter() - started
    clock = StageClock()
    clock.install()
    query = next(q for q in load_queries(None) if q["id"] == query_id)
    run = run_request(query["text"], library, snapshot_profiles(library), StandInChecker(), clock)
    run["startup"] = startup
    run["seconds"] += startup
    run["cpu"] = time.process_time() - cpu
    return run


# --- The report ---

def median_run(runs: list[dict]) -> dict:
    """The run with the median time (the lower middle one for an even count)."""
    ordered = sorted(runs, key=lambda r: r["seconds"])
    return ordered[(len(ordered) - 1) // 2]


def report(passes: dict, queries: list[dict], baseline: Path, live: bool, save: bool) -> int:
    status = 0
    medians = {name: {qid: median_run(runs) for qid, runs in by_query.items()} for name, by_query in passes.items()
               if by_query}
    print("\nTimes in seconds, p50 / p95 / max over the requests (each request: the median of its runs)")
    print(f"{'':<16} {'wall':>22} {'cpu':>22}")
    for name, by_query in medians.items():
        walls = [r["seconds"] for r in by_query.values()]
        cpus = [r["cpu"] for r in by_query.values()]
        print(f"{name:<16} {spread(walls):>22} {spread(cpus):>22}")
    if medians.get("cold"):
        print(f"{'  start-up':<16} {spread([r['startup'] for r in medians['cold'].values()]):>22}")
        print(f"{'  first request':<16} {spread([r['seconds'] - r['startup'] for r in medians['cold'].values()]):>22}")

    print("\nPer request (median run), seconds")
    names = list(medians)
    print(f"{'id':<5} {'threads':>7} {'checks':>6}  " + "  ".join(f"{n:>15}" for n in names))
    for q in queries:
        any_run = next((medians[n][q["id"]] for n in names if q["id"] in medians[n]), None)
        if any_run is None:
            continue
        cells = "  ".join(f"{medians[n][q['id']]['seconds']:>15.2f}" if q["id"] in medians[n] else f"{'':>15}"
                          for n in names)
        threads = f"{any_run['threads']}{'+' if any_run['read_more'] else ''}"
        print(f"{q['id']:<5} {threads:>7} {any_run['checks']:>6}  {cells}")

    print("\nStages, seconds: median / max over the requests")
    stages = sorted({s for by_query in medians.values() for r in by_query.values() for s in r["stages"]})
    print(f"{'stage':<26} " + "  ".join(f"{n:>15}" for n in names))
    for stage in stages:
        cells = []
        for n in names:
            values = [r["stages"].get(stage, 0.0) for r in medians[n].values()]
            cells.append(f"{statistics.median(values):>6.2f} / {max(values):>6.2f}")
        print(f"{stage:<26} " + "  ".join(f"{c:>15}" for c in cells))
    for n in names:
        rest = [r["seconds"] - sum(r["stages"].values()) - r.get("startup", 0.0) for r in medians[n].values()]
        print(f"{'(the rest) ' + n:<26} median {statistics.median(rest):.2f}, max {max(rest):.2f}")

    # The rule that matters most: no quote shown without its live check.
    unchecked = [(n, qid, where) for n, by_query in passes.items() for qid, runs in by_query.items()
                 for run in runs for where in run["unchecked"]]
    if unchecked:
        status = 1
        print(f"\nQUOTES SHOWN WITHOUT A PASSED LIVE CHECK: {len(unchecked)}")
        for n, qid, where in unchecked[:20]:
            print(f"  {n} {qid}: {where}")
    else:
        print("\nEvery quote shown was checked live and passed.")

    # The answer-equality guard.
    records = {qid: run["record"] for by_query in passes.values() for qid, runs in by_query.items() for run in runs}
    all_records = defaultdict(list)
    for name, by_query in passes.items():
        for qid, runs in by_query.items():
            all_records[qid] += [(name, run["record"]) for run in runs]
    unsteady = [qid for qid, runs in all_records.items() if any(r != runs[0][1] for _, r in runs)]
    if unsteady:
        status = 1
        print(f"\nANSWERS THAT DIFFER BETWEEN RUNS OF THIS EVAL: {', '.join(unsteady)}")
        for qid in unsteady:
            first = all_records[qid][0][1]
            for name, record in all_records[qid][1:]:
                for line in differences(record, first)[:5]:
                    print(f"  {qid} ({name}): {line}")
    if save and unsteady:
        print("Baseline not saved: the answers aren't steady.")
        save = False
    if save:
        baseline.mkdir(parents=True, exist_ok=True)
        for qid, record in records.items():
            (baseline / f"{qid}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Baseline saved: {len(records)} answers in {baseline}")
    changed = {}
    for qid, runs in all_records.items():
        path = baseline / f"{qid}.json"
        if not path.exists():
            changed[qid] = ["no baseline answer"]
            continue
        old = json.loads(path.read_text(encoding="utf-8"))
        for name, record in runs:
            found = differences(record, old)
            if found:
                changed.setdefault(qid, []).extend(f"({name}) {d}" for d in found)
    if changed:
        print(f"\nANSWERS DIFFERENT FROM THE BASELINE: {len(changed)} of {len(all_records)}"
              + (" (expected where Reddit changed since the snapshot)" if live else ""))
        for qid, found in changed.items():
            unique = list(dict.fromkeys(found))
            print(f"  {qid}: {len(unique)} difference(s)")
            for line in unique[:8]:
                print(f"    {line}")
        if not live:
            status = 1
    else:
        print(f"Answers identical to the baseline: {len(all_records)} of {len(all_records)}.")

    # Noemi's targets.
    print("\nTargets")
    for name, key in (("warm, cached", "cached"), ("warm, uncached", "uncached")):
        sixteen = [r["seconds"] for r in medians.get(name, {}).values() if r["status"] == "ok" and not r["read_more"]]
        if sixteen:
            print(f"  {name}: 16-thread answers max {max(sixteen):.2f} s (target under "
                  f"{SIXTEEN_THREAD_TARGETS[key]:.0f} s)")
    wider = {qid: r for qid, r in medians.get("warm, uncached", {}).items() if r["read_more"]}
    if wider:
        slowest = max(wider, key=lambda qid: wider[qid]["seconds"])
        print(f"  warm, uncached: answers reading more threads max {wider[slowest]['seconds']:.2f} s ({slowest}, "
              f"{wider[slowest]['threads']} threads; target under {WIDER_TARGET:.0f} s)")
    l01 = medians.get("warm, uncached", {}).get("l01")
    if l01:
        print(f"  warm, uncached: l01 anti-dandruff shampoo ({l01['threads']} threads) {l01['seconds']:.2f} s")

    cells = []
    for name in ("warm, cached", "warm, uncached", "first ask"):
        walls = [r["seconds"] for r in medians.get(name, {}).values()]
        cells.append(f"{percentile(walls, 0.5):.2f} / {percentile(walls, 0.95):.2f}" if walls else "n/a")
    cold = list(medians.get("cold", {}).values())
    if cold:
        first = [r["seconds"] - r["startup"] for r in cold]
        cells.append(f"{percentile(first, 0.5):.2f} / {percentile(first, 0.95):.2f} after "
                     f"{percentile([r['startup'] for r in cold], 0.5):.2f}")
    else:
        cells.append("n/a")
    wider_cell = f"{max(r['seconds'] for r in wider.values()):.2f}" if wider else "n/a"
    same = "no" if changed else "yes"
    print("\nRow cells for eval/LATENCY.md (warm cached | warm uncached | first ask | cold: first request after start-up "
          "| wider reading, uncached | identical):")
    print(f"| {' | '.join(cells)} | {wider_cell} | {same} |")
    return status


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="The latency eval (see the module docstring).")
    parser.add_argument("--runs", type=int, default=3, help="warm passes per checker setting (default 3)")
    parser.add_argument("--live", action="store_true", help="the real live checker, empty cache: real network")
    parser.add_argument("--only", help="comma-separated request ids (default: all)")
    parser.add_argument("--no-cold", action="store_true", help="skip the fresh-process runs")
    parser.add_argument("--save-baseline", action="store_true", help="save these answers as the baseline")
    parser.add_argument("--library", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--one", help=argparse.SUPPRESS)  # internal: one cold request in this fresh process
    args = parser.parse_args(argv)

    if args.one:
        print(json.dumps(one_cold_request(args.one, args.library), ensure_ascii=False))
        return 0
    if not (args.library / "threads").is_dir():
        print(f"No library snapshot at {args.library} (a threads/ folder).")
        return 2
    freeze_time()
    queries = load_queries(set(args.only.split(",")) if args.only else None)
    print(f"{len(queries)} requests on {args.library}; {'real live checks (--live)' if args.live else 'stand-in checks'}"
          f"; {args.runs} warm run(s) each; machine load {_load()}", file=sys.stderr)
    passes = warm_passes(queries, args.library, args.runs, args.live)
    if not args.no_cold and not args.live:
        passes["cold"] = cold_runs(queries, args.library)
    print(f"\nMachine load (1, 5, 15 minutes) at the end: {_load()}; the machine has {os.cpu_count()} cores. Other "
          "programs running at the same time slow the wall-clock times: compare runs made at similar loads, and cpu.")
    return report(passes, queries, args.baseline, args.live, args.save_baseline)


def _load() -> str:
    return ", ".join(f"{n:.1f}" for n in os.getloadavg())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
