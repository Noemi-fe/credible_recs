"""The routing evaluation of the general category (14 Oct 2026, Noemi's "I want recs regardless of the category"):
module 1 on made-up requests across the general category's departments, its new kitchen types, look-alikes, context
("headphones for my phone"), the long tail no rule lists, and what stays out (services, places, advice, food,
supplements, media, harmful items), from eval/edge_cases/general.json.

Each case expects module 1's outcome, and for a clear request its category, product type and (for the general
category) department. Four numbers, each "right out of total":
- outcome: the right outcome (clear, a question, or out of scope), and for a clear request the right category;
- product: for a clear request, exactly the expected product type (module 1's own name, or the long tail's own words);
- department: for a clear general request whose case names one, the right department;
- all: every expected field right.
Run twice: by the rules alone, and with the open model as answers use it (engine.query_model), when this machine has it.
Nothing here reads Reddit or the library.

    python -m engine.routing_eval      prints the report
"""

import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from engine.query import ParsedQuery, parse_query

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "eval" / "edge_cases" / "general.json"
FIELDS = ("status", "category", "product_type", "department")


@dataclass
class CaseResult:
    id: str
    text: str
    expected: dict
    got: dict
    outcome_ok: bool
    product_ok: bool | None = None  # None when the case isn't a clear request
    department_ok: bool | None = None  # None when the case names no department
    problems: list[str] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return not self.problems


def load_cases(path: Path = DEFAULT_CASES) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    ids = [case["id"] for case in data["cases"]]
    repeated = sorted({i for i in ids if ids.count(i) > 1})
    if repeated:
        raise ValueError(f"{path}: case ids used more than once: {', '.join(repeated)}")
    return data


def score(cases: list[dict], parse: Callable[[str], ParsedQuery]) -> list[CaseResult]:
    results = []
    for case in cases:
        expected = case["expected"]
        query = parse(case["text"])
        got = {name: getattr(query, name) for name in FIELDS}
        clear = expected["status"] == "ok"
        outcome_ok = got["status"] == expected["status"] and (not clear or got["category"] == expected["category"])
        result = CaseResult(case["id"], case["text"], expected, got, outcome_ok)
        if not outcome_ok:
            result.problems.append(f"outcome: expected {_outcome(expected)}, got {_outcome(got)}")
        if clear:
            result.product_ok = got["product_type"] == expected["product_type"]
            if not result.product_ok:
                result.problems.append(f"product: expected {expected['product_type']!r}, got {got['product_type']!r}")
            if expected.get("department"):
                result.department_ok = got["department"] == expected["department"]
                if not result.department_ok:
                    result.problems.append(f"department: expected {expected['department']!r}, "
                                           f"got {got['department']!r}")
        results.append(result)
    return results


def summary(results: list[CaseResult]) -> dict[str, tuple[int, int]]:
    clear = [r for r in results if r.product_ok is not None]
    named = [r for r in results if r.department_ok is not None]
    return {"outcome": (sum(r.outcome_ok for r in results), len(results)),
            "product": (sum(bool(r.product_ok) for r in clear), len(clear)),
            "department": (sum(bool(r.department_ok) for r in named), len(named)),
            "all": (sum(r.all_ok for r in results), len(results))}


def report_lines(data: dict, results: list[CaseResult], parser_name: str) -> list[str]:
    numbers = summary(results)
    status = "approved by Noemi" if data.get("approved") else "DRAFT: not yet approved by Noemi"
    lines = [f"The general category's routing ({parser_name}), {len(results)} made-up requests ({status})",
             f"  outcome and category: {_ratio(numbers['outcome'])}",
             f"  product type:         {_ratio(numbers['product'])}",
             f"  department:           {_ratio(numbers['department'])}",
             f"  every field right:    {_ratio(numbers['all'])}"]
    misses = [r for r in results if r.problems]
    if misses:
        lines.append("  misses:")
        for r in misses:
            lines.append(f"    {r.id} {r.text!r}")
            lines.extend(f"      - {p}" for p in r.problems)
    return lines


def routing_section(path: Path = DEFAULT_CASES, model=None) -> str:
    """The report: the rules alone, then with the open model when there is one (`model`: the one to use; by default the
    one engine.query_model finds on this machine)."""
    from engine.query_model import default_query_model  # here: only this report needs it

    data = load_cases(path)
    lines = report_lines(data, score(data["cases"], lambda text: parse_query(text, model=None)), "rules only")
    model = default_query_model() if model is None else model
    if model is not None:
        lines.append("")
        lines += report_lines(data, score(data["cases"], lambda text: parse_query(text, model=model)),
                              "rules, then the open model")
    return "\n".join(lines)


def _outcome(fields: dict) -> str:
    return f"{fields['status']} ({fields['category']})" if fields.get("category") else fields["status"]


def _ratio(pair: tuple[int, int]) -> str:
    right, total = pair
    return f"{right}/{total} ({right / total:.0%})" if total else "no cases"


if __name__ == "__main__":
    print(routing_section())
    sys.exit(0)
