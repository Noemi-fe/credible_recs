"""The ingredient evaluation (13 Oct 2026): requests naming an active ingredient, through modules 1 to 7.

Why: Noemi's live test of "salicylic acid for acne" showed an exfoliant answer that ignored the acid. The fix
(engine/ingredients.py) makes such answers ingredient-led. This evaluation checks it on the library, for the made-up
requests of eval/edge_cases/ingredients.json, each with the routing module 1 should give it:
- routing: the product type, the ingredients required and whether the request is ingredient-led, as expected;
- what the answer shows: the picks, "Also worth a look" and "Skip these", each with its form (ingredient-led answers);
- evidence: for every product shown, whether it contains each ingredient asked for, checked again here, apart from the
  pipeline (engine.ingredients.evidence on the name shown and its facts entry's formula): "facts", "name", or "none"
  (a product shown without evidence: a bug). A request whose ingredient is its type's own word ("retinol": the
  retinoid type, Noemi's call of 7 Oct 2026) requires nothing more, and its products' retinoid evidence is reported
  only;
- form (Noemi's decision 1 of 13 Oct 2026): for an ingredient-led request, whether every product shown is of a
  leave-on form, or of a form the request names ("salicylic acid wash"); and how many products with the ingredient
  were left out for their form, how many of them rinse-off.
Answers run as the end-to-end evaluation's do (engine.slice_eval): writers' profiles from the cache and every shown
quote checked live. Nothing here is Reddit text: names, forms and counts only.

    python -m engine.ingredient_eval      prints the report, from data/library
"""

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from engine.ingredients import TYPE_OWN_INGREDIENT, evidence, find_ingredients, form_kind, own_name
from engine.library import DEFAULT_LIBRARY_DIR
from engine.pipeline import answer_request
from engine.product_facts import ProductFacts, find_facts, load_product_facts

DEFAULT_CASES = Path(__file__).resolve().parents[1] / "eval" / "edge_cases" / "ingredients.json"


@dataclass(frozen=True)
class Shown:
    """One product an answer shows."""

    where: str  # "pick", "worth" or "skip"
    name: str
    form: str | None
    evidence: str  # "facts", "name" or "none" for the ingredients asked for (all of them); "-" when none is asked for
    required: bool  # whether the ingredient is required (False: reported only, as for a retinol request)
    # For an ingredient-led request: whether its form is leave-on, or one the request names; None for other requests.
    form_ok: bool | None = None


@dataclass
class CaseResult:
    id: str
    text: str
    routing: str  # "<product type>, ingredients [...], ingredient-led" as module 1 gave it
    routing_ok: bool
    expected: str  # the same, as the case expects it
    shown: list[Shown] = field(default_factory=list)
    left_out: int = 0  # products left out for want of evidence of the ingredient
    left_out_by_form: int = 0  # products with the ingredient left out for their form (ingredient-led requests)
    rinse_off: int = 0  # of those, the rinse-off ones
    message: str | None = None  # the answer's honest message, when it has fewer than 3 picks

    @property
    def evidence_holds(self) -> tuple[int, int]:
        """(shown products with evidence, shown products) among those the ingredient is required for."""
        required = [s for s in self.shown if s.required]
        return sum(s.evidence in ("facts", "name") for s in required), len(required)

    @property
    def form_holds(self) -> tuple[int, int]:
        """(shown products of a leave-on form or one the request names, shown products) of an ingredient-led request."""
        checked = [s for s in self.shown if s.form_ok is not None]
        return sum(bool(s.form_ok) for s in checked), len(checked)


def score_cases(cases_path: Path = DEFAULT_CASES, library_dir: Path = DEFAULT_LIBRARY_DIR, profiles=None,
                live_checker=None, product_facts: list[ProductFacts] | None = None) -> list[CaseResult]:
    """Each case through the pipeline, in the file's order. `product_facts`: the facts list (None: the committed
    data/product_facts.json)."""
    facts = load_product_facts() if product_facts is None else product_facts
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))["cases"]
    results = []
    for case in cases:
        run = answer_request(case["text"], library_dir=library_dir, profiles=profiles, live_checker=live_checker,
                             product_facts=facts)
        query = run.query
        expected = case["expected"]
        got = _routing(query.product_type, query.constraints.ingredients, query.ingredient_led, query.constraints.forms)
        result = CaseResult(case["id"], case["text"], got,
                            (query.product_type, query.constraints.ingredients, query.ingredient_led,
                             query.constraints.forms)
                            == (expected["product_type"], expected["ingredients"], expected["ingredient_led"],
                                expected.get("forms", [])),
                            _routing(expected["product_type"], expected["ingredients"], expected["ingredient_led"],
                                     expected.get("forms", [])),
                            left_out=len(run.left_out_no_ingredient), left_out_by_form=len(run.left_out_by_form),
                            rinse_off=sum(item.rinse_off for item in run.left_out_by_form))
        if run.answer is not None:
            required = list(query.constraints.ingredients)
            reported = required or [f.ingredient for f in find_ingredients(case["text"])
                                    if TYPE_OWN_INGREDIENT.get(query.product_type or "") == f.ingredient]
            items = ([("pick", p.name, p.form) for p in run.answer.picks]
                     + [("worth", w.name, w.form) for w in run.answer.worth_a_look]
                     + [("skip", s.name, s.form) for s in run.answer.skip])
            for where, name, form in items:
                form_ok = (form in query.constraints.forms if query.constraints.forms else form_kind(form) == "leave-on"
                           ) if query.ingredient_led else None
                result.shown.append(Shown(where, name, form, _evidence(name, query.category, facts, reported),
                                          bool(required), form_ok))
            result.message = run.answer.message
        results.append(result)
    return results


def _routing(product_type: str | None, ingredients: list[str], led: bool, forms: list[str] = ()) -> str:
    return (f"{product_type}, ingredients {ingredients}" + (", ingredient-led" if led else "")
            + (f", forms {list(forms)}" if forms else ""))


def _evidence(name: str, category: str, facts: list[ProductFacts], ingredients: list[str]) -> str:
    """How we know the product shown contains every ingredient: "facts" (its entry's formula), "name", "none"; "-"
    when nothing is asked for. The name is the one shown, and its entry is found as the pipeline finds one."""
    if not ingredients:
        return "-"
    entry = find_facts(name, category, facts)
    actives = entry.formula.actives if entry is not None and entry.formula is not None else None
    named = entry.product if entry is not None else own_name(name)
    found = [evidence(ingredient, named, actives) for ingredient in ingredients]
    if all(f.contains for f in found):
        return "facts" if any(f.how == "facts" for f in found) else "name"
    return "none"


def ingredient_lines(results: list[CaseResult]) -> list[str]:
    """One summary line, then each case: its routing, what it shows and how each product's evidence holds."""
    routed = sum(r.routing_ok for r in results)
    held = sum(r.evidence_holds[0] for r in results)
    shown = sum(r.evidence_holds[1] for r in results)
    formed = sum(r.form_holds[0] for r in results)
    led = sum(r.form_holds[1] for r in results)
    lines = [f"{len(results)} requests: routing {routed}/{len(results)} as expected; shown products with evidence of "
             f"the ingredient {held}/{shown}; ingredient-led products in a leave-on form or the form asked for "
             f"{formed}/{led}"]
    for r in results:
        lines.append(f"  {r.id} {r.text!r}: {r.routing}" + ("" if r.routing_ok else f" (expected {r.expected})"))
        for s in r.shown:
            form = f" [{s.form}]" if s.form else ""
            how = s.evidence if s.required else f"{s.evidence}, reported only"
            fits = "" if s.form_ok is None else ("" if s.form_ok else ", NOT a leave-on form or the form asked for")
            lines.append(f"    {s.where}: {s.name}{form}, evidence: {how}{fits}")
        if not r.shown:
            lines.append("    nothing shown" + (f": {r.message}" if r.message else ""))
        lines.append(f"    left out for want of evidence of the ingredient: {r.left_out}"
                     + (f"; for their form: {r.left_out_by_form} ({r.rinse_off} rinse-off)"
                        if r.left_out_by_form else ""))
    return lines


_REAL = object()


def ingredient_section(cases_path: Path = DEFAULT_CASES, library_dir: Path = DEFAULT_LIBRARY_DIR, profiles=_REAL,
                       live_checker=_REAL) -> str:
    """For eval/run_eval.py: the printed section. Runs as answers run (profiles from the cache, live checks)."""
    if not (Path(library_dir) / "threads").is_dir():
        return "Active ingredients: skipped (no local library)"
    from engine import pipeline

    profiles = pipeline.cached_profiles() if profiles is _REAL else profiles
    live_checker = pipeline.live_checker() if live_checker is _REAL else live_checker
    results = score_cases(cases_path, library_dir, profiles, live_checker)
    return "Active ingredients (eval/edge_cases/ingredients.json), on the library\n" + "\n".join(
        f"  {line}" for line in ingredient_lines(results))


if __name__ == "__main__":
    print(ingredient_section())
    sys.exit(0)
