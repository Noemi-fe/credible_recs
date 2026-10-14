"""The need evaluation (14 Oct 2026): requests that ask for something besides the product, through modules 1 to 7.

Why: Noemi's and a friend's tests of the live site. "shampoo for greasy hair" came back with generic and anti-dandruff
shampoos, and "dandruff shampoo that actually works" with clarifying shampoos from big curly-hair threads: an answer's
first reading (its first PIPELINE_MAX_THREADS threads) was filled by big general threads, which gave 3 picks, so the
wider, need-led reading never ran (engine.pipeline.answer_request). This evaluation measures, on the library, for the
made-up requests of eval/edge_cases/needs.json:
- the first reading: how many of its threads are about the request's need, by their title, and by their title or post
  (the post is the thread's own opening text; a slimmed thread keeps no words of its post, engine/slim.py, so it is
  judged by its title only, and the report says how many were). A thread is about the need when it holds one of the
  case's judge words:
  regular expressions matched at the start of a word, lowercased, chosen for each case apart from the engine's own need
  words (config.NEEDS), so the engine doesn't grade itself;
- what the answer shows: its picks and "Also worth a look", and how many threads it read (more than the first reading
  when the wider reading ran).
Since 14 Oct 2026 (the need-quality builder) a case may also judge each of its needs apart ("judge_each": {need: judge
words}): its first-reading threads about every one of them are counted, since a thread about curly hair alone tells a
request for a curly-hair shampoo that isn't drying less than one about both; and list the words of the opposite of what
it asks ("opposite": "clarif", "detox" for a shampoo that isn't drying): its first-reading threads titled with one, and
the products its answer shows named with one, are counted, since those ask for or are the opposite.
Answers run as the end-to-end evaluation's do (engine.slice_eval): writers' profiles from the cache and every shown
quote checked live. Nothing here is Reddit text: thread ids, counts and product names only.

    python -m engine.need_eval      prints the report, from data/library
"""

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from engine.config import PIPELINE_MAX_THREADS
from engine.library import DEFAULT_LIBRARY_DIR
from engine.library_cache import loaded
from engine.needs import request_needs
from engine.pipeline import answer_request

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "eval" / "edge_cases" / "needs.json"


@dataclass
class CaseResult:
    id: str
    text: str
    needs: list[str] = field(default_factory=list)  # the request's needs as the engine reads them (engine.needs)
    first: list[str] = field(default_factory=list)  # the first reading's thread ids, in the order read
    about_by_title: int = 0  # of those, the threads whose title holds a judge word
    about_by_title_or_post: int = 0  # ... whose title or post does
    picks: list[str] = field(default_factory=list)
    worth: list[str] = field(default_factory=list)  # "Also worth a look"
    threads_read: int = 0  # every thread the answer read (the wider reading's, when it ran)
    read_more: bool = False  # the wider reading ran and was kept
    message: str | None = None  # the answer's honest message, when it has fewer than 3 picks
    each_judged: bool = False  # the case judges each of its needs apart ("judge_each")
    about_every_need: int = 0  # first-reading threads whose title or post is about every one of them
    titled_opposite: int = 0  # first-reading threads whose title holds a word of the case's "opposite"
    named_opposite: int = 0  # picks and "Also worth a look" items whose name holds one
    slimmed: int = 0  # first-reading threads slimmed (engine/slim.py): their posts' words are gone, judged by title


def about_the_need(text: str, judge: list[str]) -> bool:
    """Whether a title or post holds one of the case's judge words, at the start of a word."""
    lowered = (text or "").lower()
    return any(re.search(rf"(?<![a-z0-9])(?:{pattern})", lowered) for pattern in judge)


def score_cases(cases_path: Path = DEFAULT_CASES, library_dir: Path = DEFAULT_LIBRARY_DIR, profiles=None,
                live_checker=None, max_threads: int = PIPELINE_MAX_THREADS) -> list[CaseResult]:
    """Each case through the pipeline, in the file's order. `max_threads`: the first reading's size (the pipeline's)."""
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))["cases"]
    threads = {t.id: t for t in loaded(Path(library_dir) / "threads").threads}
    results = []
    for case in cases:
        run = answer_request(case["text"], library_dir=library_dir, profiles=profiles, live_checker=live_checker,
                             max_threads=max_threads)
        # The wider reading reads the same threads in the same order, more of them: its first ones are the first
        # reading's.
        first = run.threads_used[:max_threads]
        result = CaseResult(case["id"], case["text"], [n.name for n in request_needs(run.query)], first,
                            threads_read=len(run.threads_used), read_more=run.read_more)
        judge, each, opposite = case["judge"], case.get("judge_each") or {}, case.get("opposite") or []
        result.each_judged = bool(each)
        for thread_id in first:
            thread = threads[thread_id]
            by_title = about_the_need(thread.title, judge)
            result.about_by_title += by_title
            result.about_by_title_or_post += by_title or about_the_need(thread.body, judge)
            result.slimmed += thread.slimmed
            result.about_every_need += bool(each) and all(
                about_the_need(thread.title, words) or about_the_need(thread.body, words) for words in each.values())
            result.titled_opposite += bool(opposite) and about_the_need(thread.title, opposite)
        if run.answer is not None:
            result.picks = [p.name for p in run.answer.picks]
            result.worth = [w.name for w in run.answer.worth_a_look]
            result.message = run.answer.message
            result.named_opposite = sum(bool(opposite) and about_the_need(name, opposite)
                                        for name in result.picks + result.worth)
        results.append(result)
    return results


def need_lines(results: list[CaseResult]) -> list[str]:
    """One summary line, then each case: its needs, its first reading and what its answer shows."""
    read = sum(len(r.first) for r in results)
    titled = sum(r.about_by_title for r in results)
    posted = sum(r.about_by_title_or_post for r in results)
    full = sum(len(r.picks) >= 3 for r in results)
    each = [r for r in results if r.each_judged]
    every = (f"; about every need {sum(r.about_every_need for r in each)}/{sum(len(r.first) for r in each)} (the "
             f"{len(each)} with each need judged), titled as the opposite {sum(r.titled_opposite for r in results)}, "
             f"shown named as the opposite {sum(r.named_opposite for r in results)}") if each else ""
    slimmed = sum(r.slimmed for r in results)
    gone = f" ({slimmed} slimmed: their posts' words are gone, judged by title only)" if slimmed else ""
    lines = [f"{len(results)} requests: first-reading threads about the need {posted}/{read} by title or post{gone}, "
             f"{titled}/{read} by title; {full} with 3 picks{every}"]
    for r in results:
        wider = f"; read {r.threads_read} threads (the wider reading)" if r.read_more else ""
        every = f", about every need {r.about_every_need}" if r.each_judged else ""
        opposite = (f"; titled as the opposite {r.titled_opposite}, shown named as the opposite {r.named_opposite}"
                    if r.titled_opposite or r.named_opposite else "")
        lines.append(f"  {r.id} {r.text!r}: needs {', '.join(r.needs) or 'none'}; first reading {len(r.first)} threads, "
                     f"about the need {r.about_by_title_or_post} by title or post ({r.about_by_title} by title){every}"
                     f"{wider}{opposite}")
        lines.append(f"    picks: {', '.join(r.picks) or 'none'}" + (f" ({r.message})" if r.message and not r.picks
                                                                       else ""))
        if r.worth:
            lines.append(f"    also worth a look: {', '.join(r.worth)}")
    return lines


_REAL = object()


def need_section(cases_path: Path = DEFAULT_CASES, library_dir: Path = DEFAULT_LIBRARY_DIR, profiles=_REAL,
                 live_checker=_REAL) -> str:
    """For eval/run_eval.py: the printed section. Runs as answers run (profiles from the cache, live checks)."""
    if not (Path(library_dir) / "threads").is_dir():
        return "Needs: skipped (no local library)"
    from engine import pipeline

    profiles = pipeline.cached_profiles() if profiles is _REAL else profiles
    live_checker = pipeline.live_checker() if live_checker is _REAL else live_checker
    results = score_cases(cases_path, library_dir, profiles, live_checker)
    return "Needs (eval/edge_cases/needs.json), on the library\n" + "\n".join(f"  {line}" for line in need_lines(results))


if __name__ == "__main__":
    print(need_section())
    sys.exit(0)
