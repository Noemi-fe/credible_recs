"""Checking ahead (Noemi's decision of 13 Oct 2026): the comments answers would show are read live on Reddit in advance,
every day, within Reddit's limits, so a visitor's fresh answer finds its quotes already checked.

Why. Before an answer shows a quote, its comment is read live through Reddit's embed page (engine/live_check.py). A
fresh answer needs 20 to 40 such reads, and Reddit's embed pages allow about 200 reads in 10 minutes from one address:
once that allowance is used, each read waits its turn (one every 4 s), and a fresh answer took a minute or two. The
rule doesn't change: a quote is shown only with a passing live check from the last 48 hours. What changes is when the
check is made: mostly here, ahead of time, so answers find it saved.

What is read, worked out without reading Reddit (comments_to_check):
1. the requests (requests_to_check): the search page's example requests (the blind-test questions), the latency eval's
   requests, then every product type the library answers, by its name: module 1's own types, and the open model's
   types the library holds threads about (its request log, and config.PRECHECK_MODEL_TYPES where the log isn't kept);
2. each request's answer, as the live site writes it (engine.pipeline.answer_request, with writers' standing from the
   library), every quote taken as passing except where a saved check already says a comment was deleted or edited: then
   that comment drops out and what replaces it is shown, as for a visitor. Every quote the answer shows counts,
   wherever it is: a pick's quotes, its downsides and care tips, the care note, "What to look for" and "Avoid", the skip
   list, and anything else the answer holds quotes in (such as "Also worth a look");
3. what would be shown if checks failed: the answer written again (module 7's own write_answer, with what the pipeline
   gave it) without each comment it shows, one at a time, so that place's next in line shows (a pick's next quote, the
   next downside, care tip or note); with its picks set aside, so the products ranked just behind them show; and
   without every comment of those two, for the places' next in line after that (a pick left with too few quotes gives
   its place to the next product, as it would).
Each comment gets a tier (0: shown; 1: next in line; 2: behind the picks; 3: next after that), and they are read in
that order, a pick's own quotes before the rest of each tier, then by request, then by place in the answer: the
likeliest to be shown first. A comment in several answers or places is read once, at its likeliest.

How it is read (check_ahead): through the live site's own checker (engine.pipeline.live_checker: the same pace, the
same 48-hour cache, the same bucket), one comment at a time, until the run's budget of reads (--limit, default
config.PRECHECK_MAX_READS) is spent. A comment read less than config.PRECHECK_FRESH_HOURS ago is skipped; an older one
is read again, so the next day's answers never find its check expired. A run stops when Reddit stops answering
(config.PRECHECK_STOP_AFTER_UNKNOWN unreadable pages in a row). The report gives counts and times only, never a
comment's words.

    python -m engine.precheck [--limit N] [--dry-run]

--dry-run works out the comments and says how many would be read and how many are fresh, reading nothing on Reddit.
On Google Cloud a Cloud Run job runs it once a day (deploy/cloudrun/DEPLOY.md).
"""

import dataclasses
import inspect
import json
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

from engine import pipeline
from engine.answer import Answer, ShownQuote
from engine.config import (PICKS_SHOWN, PRECHECK_FRESH_HOURS, PRECHECK_MAX_READS, PRECHECK_MODEL_TYPES,
                           PRECHECK_STOP_AFTER_UNKNOWN)
from engine.library import DEFAULT_LIBRARY_DIR
from engine.live_check import LiveResult
from engine.parse_reddit import REPO_ROOT
from engine.query import PRODUCT_TYPES

QUESTIONS_FILE = REPO_ROOT / "eval" / "blind_test" / "questions.json"  # the search page's example requests
LATENCY_FILE = REPO_ROOT / "eval" / "edge_cases" / "latency_queries.json"
TIERS = ("shown", "next in line", "behind the picks", "next after those")  # each tier in words, for the report
SET_ASIDE = "set aside by the pre-check, to see what is ranked behind it"  # never shown: these answers are thrown away
PROGRESS_EVERY = 100  # reads between progress lines on stderr


@dataclass(frozen=True)
class Candidate:
    """A comment to read ahead: its link, its id, every quote of it an answer could show, and how likely it is to be
    shown (tier, then section: 0 for a pick's own quotes, 1 for the rest; then the request's place in the list and the
    quote's place in its answer)."""

    url: str
    comment_id: str
    quotes: tuple[str, ...]
    tier: int
    section: int
    request: int
    place: int

    @property
    def order(self) -> tuple[int, int, int, int]:
        return self.tier, self.section, self.request, self.place


@dataclass
class Reading:
    """What one run read, in counts."""

    read: int = 0  # comments read on Reddit now
    passing: int = 0  # still there, every quote found word for word
    gone: int = 0  # deleted or removed
    changed: int = 0  # edited: a quote no longer found
    unknown: int = 0  # the page couldn't be read
    fresh: int = 0  # skipped: read less than PRECHECK_FRESH_HOURS ago
    would_read: int = 0  # a dry run: what would have been read
    not_reached: int = 0  # left for lack of reads in this run's budget
    stopped: bool = False  # stopped early: Reddit stopped answering
    seconds: float = 0.0


@dataclass
class _Found:
    """The comments worked out for the requests, with counts for the report."""

    candidates: list[Candidate] = field(default_factory=list)
    answered: int = 0
    failed: int = 0  # requests the pipeline couldn't answer (each named on stderr)


# --- Which requests ---

def requests_to_check(questions: Path = QUESTIONS_FILE, latency: Path = LATENCY_FILE,
                      library_dir: Path = DEFAULT_LIBRARY_DIR) -> list[str]:
    """The requests whose answers are checked ahead, likeliest first, each once: the search page's example requests
    (the blind-test questions), the latency eval's requests, module 1's product types, the open model's types in the
    library's request log, then config.PRECHECK_MODEL_TYPES. A missing file adds nothing."""
    found = [q["text"] for q in _read_json(questions).get("questions", [])]
    found += [q["text"] for q in _read_json(latency).get("queries", [])]
    found += [p.name for p in PRODUCT_TYPES]
    found += _logged_types(Path(library_dir) / "requests.jsonl")
    found += list(PRECHECK_MODEL_TYPES)
    return list(dict.fromkeys(text.strip() for text in found if text and text.strip()))


def _read_json(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _logged_types(log: Path) -> list[str]:
    """The product types of the requests the library was filled for (`library add`'s log), as module 1 placed them."""
    try:
        lines = Path(log).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    types = []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("status") == "ok" and isinstance(entry.get("product_type"), str):
            types.append(entry["product_type"])
    return types


# --- Which comments ---

class _AsIfChecked:
    """The checker answers get while the pre-check works out what they show: a comment with a saved check is answered
    by it (one deleted or edited drops out, as it would for a visitor); one without is taken as passing, since it is
    about to be read. Reddit is never read here."""

    def __init__(self, live):
        self.live = live

    def check(self, url: str, quote: str) -> LiveResult:
        return self.live.saved_check(url, quote) or LiveResult("ok", "not checked yet: taken as passing for now")


@contextmanager
def _answers_kept():
    """While open, each answer the pipeline writes is kept with what it was written from (engine.answer.write_answer's
    arguments), so it can be written again as it would be if checks failed. The pipeline itself is unchanged, and the
    pre-check runs as a process of its own, never inside the site, so no visitor's answer passes through here."""
    written: list[tuple[dict, Answer]] = []
    original = pipeline.write_answer
    signature = inspect.signature(original)

    def keeping(*args, **kwargs):
        answer = original(*args, **kwargs)
        written.append((dict(signature.bind(*args, **kwargs).arguments), answer))
        return answer

    pipeline.write_answer = keeping
    try:
        yield written, original
    finally:
        pipeline.write_answer = original


def comments_to_check(requests: list[str], library_dir: Path = DEFAULT_LIBRARY_DIR, checker=None,
                      profiles=None) -> list[Candidate]:
    """The comments the requests' answers show or hold next in line, likeliest to be shown first (see the module's
    docstring). `checker`: the live checker whose saved checks count (engine.live_check.LiveChecker); it never reads
    Reddit here. `profiles`: writers' standing, as engine.pipeline takes it."""
    return _work_out(requests, library_dir, checker, profiles).candidates


def _work_out(requests: list[str], library_dir: Path, checker, profiles) -> _Found:
    found = _Found()
    as_if = _AsIfChecked(checker)
    every: list[Candidate] = []
    with _answers_kept() as (written, write_answer):
        for number, request in enumerate(requests):
            written.clear()
            try:
                result = pipeline.answer_request(request, library_dir=library_dir, profiles=profiles,
                                                 live_checker=as_if)
            except Exception as error:  # a broken library file, say: the other requests are still checked ahead
                found.failed += 1
                print(f"  {request!r} couldn't be answered ({type(error).__name__}: {error}): left out of this run.",
                      file=sys.stderr, flush=True)
                continue
            if result.answer is None:
                continue
            found.answered += 1
            arguments = next(args for args, answer in reversed(written) if answer is result.answer)
            for tier, answers in enumerate(_written_again(arguments, result.answer, write_answer)):
                every += [Candidate(quote.url, quote.comment_id, (quote.text,), tier, section, number, place)
                          for answer in answers for place, (section, quote) in enumerate(shown_quotes(answer))]
    found.candidates = merged(every)
    return found


def _written_again(arguments: dict, answer: Answer, write_answer) -> list[list[Answer]]:
    """The answer, then written again as it would be if checks failed, by tier: [the answer], [the answer without each
    comment it shows, one at a time: each place's next in line], [the answer with its picks set aside: the products
    ranked behind them], [the answer without every comment of the first two: the next in line after those]."""
    bodies = arguments["bodies"]
    shown = _comment_ids(answer)
    one_less = [write_answer(**{**arguments, "bodies": _without(bodies, {cid})}) for cid in sorted(shown)]
    picks = {pick.product_key for pick in answer.picks[:PICKS_SHOWN]}
    ranking = arguments["ranking"]
    set_aside = dataclasses.replace(ranking, products=[
        dataclasses.replace(p, qualifies=False, shortfall=SET_ASIDE) if p.key in picks else p
        for p in ranking.products])
    behind = write_answer(**{**arguments, "ranking": set_aside})
    next_in_line = set().union(*(_comment_ids(a) for a in one_less)) if one_less else set()
    after_those = write_answer(**{**arguments, "bodies": _without(bodies, shown | next_in_line)})
    return [[answer], one_less, [behind], [after_those]]


def _without(bodies, comment_ids: set[str]) -> dict[str, str]:
    """The comments' texts less these: their quotes fail module 7's check, as a comment dropped by a live check does."""
    return {cid: body for cid, body in bodies.items() if cid not in comment_ids}


def _comment_ids(answer: Answer) -> set[str]:
    return {quote.comment_id for _, quote in shown_quotes(answer)}


def shown_quotes(answer: Answer) -> list[tuple[int, ShownQuote]]:
    """Every quote the answer shows, in its own order (the picks first), each with its section: 0 for a pick's own
    quotes ("In their words"), 1 for everything else. Found wherever the answer holds them, so a part added to answers
    later (such as "Also worth a look") is checked ahead too."""
    found: list[tuple[int, ShownQuote]] = []

    def walk(value, path: tuple) -> None:
        if isinstance(value, ShownQuote):
            found.append((0 if path[:1] == ("picks",) and path[2:3] == ("quotes",) else 1, value))
        elif dataclasses.is_dataclass(value) and not isinstance(value, type):
            for f in dataclasses.fields(value):
                walk(getattr(value, f.name), path + (f.name,))
        elif isinstance(value, (list, tuple)):
            for i, item in enumerate(value):
                walk(item, path + (i,))
        elif isinstance(value, dict):
            for key, item in value.items():
                walk(item, path + (key,))

    walk(answer, ())
    return found


def merged(candidates: list[Candidate]) -> list[Candidate]:
    """One candidate per comment, at its likeliest order, holding every quote of it (each once, likeliest first);
    sorted likeliest first."""
    by_url: dict[str, list[Candidate]] = {}
    for candidate in sorted(candidates, key=lambda c: c.order):
        by_url.setdefault(candidate.url, []).append(candidate)
    out = []
    for same in by_url.values():
        quotes = tuple(dict.fromkeys(q for c in same for q in c.quotes))
        out.append(dataclasses.replace(same[0], quotes=quotes))
    return sorted(out, key=lambda c: c.order)


# --- Reading them ---

def check_ahead(candidates: list[Candidate], checker, limit: int = PRECHECK_MAX_READS, dry_run: bool = False,
                stop_after_unknown: int = PRECHECK_STOP_AFTER_UNKNOWN,
                fresh: timedelta = timedelta(hours=PRECHECK_FRESH_HOURS)) -> Reading:
    """Reads the candidates on Reddit in order through `checker` (engine.live_check.LiveChecker), skipping those read
    within `fresh`, until `limit` reads are made. `dry_run`: nothing is read; counts what would be."""
    run = Reading()
    started = time.perf_counter()
    unknown_in_a_row = 0
    for candidate in candidates:
        if run.stopped or run.read + run.would_read >= limit:
            run.not_reached += 1
            continue
        if checker.checked_at(candidate.url, max_age=fresh) is not None:
            run.fresh += 1
            continue
        if dry_run:
            run.would_read += 1
            continue
        status = _read(candidate, checker, fresh)
        run.read += 1
        setattr(run, status, getattr(run, status) + 1)
        unknown_in_a_row = unknown_in_a_row + 1 if status == "unknown" else 0
        if unknown_in_a_row >= stop_after_unknown:
            run.stopped = True
        if run.read % PROGRESS_EVERY == 0:
            print(f"  read {run.read:,} of up to {limit:,} ({(time.perf_counter() - started) / 60:.1f} min)",
                  file=sys.stderr, flush=True)
    run.seconds = time.perf_counter() - started
    return run


def _read(candidate: Candidate, checker, fresh: timedelta) -> str:
    """One comment read on Reddit (once: its other quotes are checked against what was read), as one word: "passing"
    when every quote is still found, else "gone", "changed" or "unknown"."""
    for quote in candidate.quotes:
        outcome = checker.check(candidate.url, quote, max_age=fresh)
        if not outcome.show:
            return outcome.status
    return "passing"


# --- The report and the command ---

def report(candidates: list[Candidate], run: Reading, requests: int, answered: int, seconds_working: float,
           seconds_reading: float, failed: int = 0) -> str:
    """The run in a few lines: counts and times only, never a comment's words."""
    by_tier = [sum(1 for c in candidates if c.tier == tier) for tier in range(len(TIERS))]
    tiers = ", ".join(f"{n:,} {words}" for n, words in zip(by_tier, TIERS))
    failures = f", {failed} failed (named above)" if failed else ""
    lines = [f"Requests: {requests} ({answered} answered{failures}). Comments their answers show or hold next in line: "
             f"{len(candidates):,} ({tiers})."]
    if run.would_read or not run.read:
        lines.append(f"Would read on Reddit: {run.would_read:,}." if run.would_read else "Read on Reddit now: none.")
    if run.read:
        lines.append(f"Read on Reddit now: {run.read:,} ({run.passing:,} passing, {run.gone:,} gone, {run.changed:,} "
                     f"changed, {run.unknown:,} unreadable).")
    lines.append(f"Skipped, read within {PRECHECK_FRESH_HOURS} hours: {run.fresh:,}. Not reached within this run's "
                 f"budget: {run.not_reached:,}.")
    if run.stopped:
        lines.append(f"Stopped early: {PRECHECK_STOP_AFTER_UNKNOWN} pages in a row couldn't be read (Reddit is "
                     "refusing reads); the rest wait for the next run.")
    lines.append(f"Time: {_duration(seconds_working)} working out the answers, {_duration(seconds_reading)} reading, "
                 f"{_duration(seconds_working + seconds_reading)} in all.")
    return "\n".join(lines)


def _duration(seconds: float) -> str:
    return f"{seconds:.0f} s" if seconds < 120 else f"{seconds / 60:.1f} min"


def options(argv: list[str]) -> tuple[int, bool] | None:
    """(--limit N, --dry-run) from the command line; None when anything else is given."""
    limit, dry_run, rest = PRECHECK_MAX_READS, False, list(argv)
    while rest:
        arg = rest.pop(0)
        if arg == "--dry-run":
            dry_run = True
        elif arg == "--limit" and rest and rest[0].isdigit():
            limit = int(rest.pop(0))
        else:
            return None
    return limit, dry_run


def run(requests: list[str], limit: int, dry_run: bool, library_dir: Path, checker, profiles) -> int:
    """Works out the comments, reads them, and prints the report."""
    started = time.perf_counter()
    found = _work_out(requests, library_dir, checker, profiles)
    working = time.perf_counter() - started
    print(f"Worked out {len(found.candidates):,} comments from {len(requests)} requests in {_duration(working)}; "
          f"{'counting' if dry_run else 'reading'} up to {limit:,}.", file=sys.stderr, flush=True)
    reading = check_ahead(found.candidates, checker, limit=limit, dry_run=dry_run)
    bucket = getattr(checker, "bucket", None)
    print(report(found.candidates, reading, len(requests), found.answered, working, reading.seconds, found.failed))
    if bucket is not None and bucket.problems:
        print(f"The bucket {bucket.name} failed {bucket.problems} time(s): those checks were kept on this machine only.")
    return 0


def main(argv: list[str]) -> int:
    parsed = options(argv)
    if parsed is None:
        print(__doc__)
        return 2
    limit, dry_run = parsed
    return run(requests_to_check(), limit, dry_run, DEFAULT_LIBRARY_DIR, pipeline.live_checker(),
               pipeline.cached_profiles())


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
