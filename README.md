# Credibility-ranked shopping picks

Credibility-ranked product recommendations from public Reddit discussions.
Free, non-commercial research prototype: read-only, links back to every source comment.

It returns three picks for skincare and kitchen gear, ranked by how credible the recommenders are rather than by how popular a product is.

Read `docs/end-state-tree.md` for the plan, and `CLAUDE.md` for how the build works.

```
data/gold/   hand-collected threads (JSON) and Noemi's labels (CSV); format in data/gold/README.md
engine/      the pipeline, one module per step
api/         FastAPI service that exposes the engine
web/         Next.js site
eval/        evaluation harness, edge cases, blind test, RUNS.md
docs/        the end-state tree
```

## Setup

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```
