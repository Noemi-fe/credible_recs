"""The end-to-end score: every blind-test question through modules 1 to 7, before the real blind test exists.

For each question in eval/blind_test/questions.json it runs engine.pipeline.answer_request on the library and
records how many picks came back, which, how many threads were read, and how many shown quotes failed the word
for word check (engine.answer.unverified_claims). That last number must always be 0: the answer drops a quote that
fails, so anything else is a bug.

The headline: how many questions get a full top 3, and how many get at least one pick. A question with no pick
gets the honest "not enough credible evidence" message, which is the right answer when the library is thin; the
fix is more threads, not looser rules.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from engine.answer import unverified_claims
from engine.config import PICKS_SHOWN
from engine.library import DEFAULT_LIBRARY_DIR
from engine.pipeline import answer_request

DEFAULT_QUESTIONS = Path(__file__).resolve().parents[1] / "eval" / "blind_test" / "questions.json"


@dataclass
class QuestionResult:
    id: str
    text: str
    status: str  # module 1's outcome: ok, clarify or out_of_scope
    picks: list[str] = field(default_factory=list)  # the picks' names, best first
    threads: int = 0  # threads read
    unverified: int = 0  # shown quotes that failed the check: must be 0


def score_questions(questions_path: Path = DEFAULT_QUESTIONS, library_dir: Path = DEFAULT_LIBRARY_DIR,
                    profiles=None) -> list[QuestionResult]:
    """Runs every question through the pipeline, in the file's order. `profiles`: as in engine.pipeline."""
    questions = json.loads(Path(questions_path).read_text(encoding="utf-8"))["questions"]
    results = []
    for q in questions:
        run = answer_request(q["text"], library_dir=library_dir, profiles=profiles)
        result = QuestionResult(q["id"], q["text"], run.query.status, threads=len(run.threads_used))
        if run.answer is not None:
            result.picks = [pick.name for pick in run.answer.picks]
            result.unverified = len(unverified_claims(run.answer, run.bodies))
        results.append(result)
    return results


def slice_lines(results: list[QuestionResult]) -> list[str]:
    """One summary line, then one line per question."""
    full = sum(len(r.picks) >= PICKS_SHOWN for r in results)
    some = sum(bool(r.picks) for r in results)
    unverified = sum(r.unverified for r in results)
    noun = "question" if len(results) == 1 else "questions"
    lines = [f"{len(results)} {noun}: {full} with {PICKS_SHOWN} picks, {some} with at least 1 pick; unverified quotes shown: {unverified}"]
    for r in results:
        if r.status != "ok":
            lines.append(f"  {r.id} {r.status}")
            continue
        picks = f"{len(r.picks)} pick{'' if len(r.picks) == 1 else 's'}"
        names = f": {', '.join(r.picks)}" if r.picks else " (not enough credible evidence)"
        lines.append(f"  {r.id} {picks}{names}; {r.threads} threads read")
    return lines


def slice_report(questions_path: Path = DEFAULT_QUESTIONS, library_dir: Path = DEFAULT_LIBRARY_DIR) -> str:
    """For eval/run_eval.py."""
    if not (Path(library_dir) / "threads").is_dir():
        return "End to end (modules 1-7): skipped (no local library)"
    from engine.pipeline import cached_profiles

    lines = slice_lines(score_questions(questions_path, library_dir, cached_profiles()))
    return "End to end (modules 1-7), blind-test questions on the library\n" + "\n".join(f"  {line}" for line in lines)
