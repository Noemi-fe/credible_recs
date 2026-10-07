"""Scores module 1 (query understanding) against the hand-checked requests in eval/edge_cases/query.json.

Three numbers, each "right out of total":
- outcome: the right outcome (clear, ask a question, or out of scope), and for clear requests the right category;
- product: for clear requests, the right product type, matched loosely ("chemical exfoliant" counts as "exfoliant");
- constraints: for clear requests, budget, skin types, size, SPF and years all right. Must-haves are free text and
  aren't scored yet.
"""

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from engine.config import THREAD_CATEGORIES
from engine.models import Record
from engine.query import Constraints, ParsedQuery

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "eval" / "edge_cases" / "query.json"


class QueryCaseError(Exception):
    pass


class ExpectedQuery(Record):
    status: Literal["ok", "clarify", "out_of_scope"]
    category: Literal[THREAD_CATEGORIES] | None = None
    product_type: str | None = None
    constraints: Constraints = Constraints()


class QueryCase(Record):
    id: str
    text: str
    expected: ExpectedQuery
    notes: str = ""


class QueryCaseFile(Record):
    approved: bool  # True once Noemi has checked every expected answer
    approved_note: str = ""
    cases: list[QueryCase]


def load_query_cases(path: Path = DEFAULT_CASES) -> QueryCaseFile:
    try:
        data = QueryCaseFile.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
    except ValueError as e:  # bad JSON or a case that doesn't fit the shape
        raise QueryCaseError(f"{path}: {e}") from e
    repeated = sorted(case_id for case_id, n in Counter(c.id for c in data.cases).items() if n > 1)
    if repeated:
        raise QueryCaseError(f"{path}: case ids used more than once: {', '.join(repeated)}")
    return data


@dataclass
class CaseResult:
    case: QueryCase
    parsed: ParsedQuery | None
    problems: list[str]
    outcome_ok: bool
    product_ok: bool | None  # None when the case isn't a clear request
    constraints_ok: bool | None


@dataclass
class Summary:
    outcome: tuple[int, int]  # (right, total)
    product: tuple[int, int]
    constraints: tuple[int, int]


def score_cases(cases: list[QueryCase], parse: Callable[[str], ParsedQuery]) -> list[CaseResult]:
    results = []
    for case in cases:
        expected = case.expected
        clear = expected.status == "ok"
        try:
            parsed = parse(case.text)
        except Exception as e:  # a crash is a miss, with its reason, not the end of the run
            results.append(CaseResult(case, None, [f"parser failed: {e}"], False, False if clear else None, False if clear else None))
            continue

        problems = []
        outcome_ok = parsed.status == expected.status and (not clear or parsed.category == expected.category)
        if not outcome_ok:
            problems.append(f"outcome: expected {_outcome(expected)}, got {_outcome(parsed)}")
        product_ok = constraints_ok = None
        if clear:
            product_ok = _same_product(parsed.product_type, expected.product_type)
            if not product_ok:
                problems.append(f"product: expected {expected.product_type!r}, got {parsed.product_type!r}")
            differences = _constraint_differences(parsed.constraints, expected.constraints)
            constraints_ok = not differences
            problems.extend(differences)
        results.append(CaseResult(case, parsed, problems, outcome_ok, product_ok, constraints_ok))
    return results


def summarize(results: list[CaseResult]) -> Summary:
    clear = [r for r in results if r.case.expected.status == "ok"]
    return Summary(
        outcome=(sum(r.outcome_ok for r in results), len(results)),
        product=(sum(bool(r.product_ok) for r in clear), len(clear)),
        constraints=(sum(bool(r.constraints_ok) for r in clear), len(clear)),
    )


def report_lines(cases_file: QueryCaseFile, results: list[CaseResult], parser_name: str) -> list[str]:
    summary = summarize(results)
    status = "approved by Noemi" if cases_file.approved else "DRAFT: not yet approved by Noemi"
    lines = [
        f"Module 1, query understanding ({parser_name}), {len(results)} cases ({status})",
        f"  outcome and category: {_ratio(summary.outcome)}",
        f"  product type:         {_ratio(summary.product)}",
        f"  constraints:          {_ratio(summary.constraints)}",
    ]
    misses = [r for r in results if r.problems]
    if misses:
        lines.append("  misses:")
        for r in misses:
            lines.append(f"    {r.case.id} {r.case.text!r}")
            lines.extend(f"      - {p}" for p in r.problems)
    return lines


def _outcome(query) -> str:
    return f"{query.status} ({query.category})" if query.category else query.status


def _same_product(got: str | None, expected: str | None) -> bool:
    if not got or not expected:
        return got == expected
    got, expected = _normalise(got), _normalise(expected)
    return expected in got or got in expected


def _normalise(name: str) -> str:
    name = name.lower().replace("'s", "").replace("moisturizer", "moisturiser").strip()
    return name.removesuffix("s")


def _constraint_differences(got: Constraints, expected: Constraints) -> list[str]:
    differences = []
    for name in ("budget", "size", "spf", "min_years"):
        got_value, expected_value = getattr(got, name), getattr(expected, name)
        if got_value != expected_value:
            differences.append(f"{name}: expected {_show(expected_value)}, got {_show(got_value)}")
    if set(got.skin_types) != set(expected.skin_types):
        differences.append(f"skin_types: expected {expected.skin_types}, got {got.skin_types}")
    return differences


def _show(value) -> str:
    return str(value.model_dump(exclude_none=True)) if isinstance(value, Record) else repr(value)


def _ratio(pair: tuple[int, int]) -> str:
    right, total = pair
    return f"{right}/{total} ({right / total:.0%})" if total else "no cases"
