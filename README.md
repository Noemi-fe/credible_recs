# Credibility-ranked shopping picks

Credibility-ranked product recommendations from public Reddit discussions.
Free, non-commercial research prototype: read-only, links back to every source comment.

It returns three picks for skincare and kitchen gear, ranked by how credible the recommenders are rather than by how popular a product is.

Read `CLAUDE.md` for how the build works, and `eval/RUNS.md` for every measured result.

## How it works

1. **Understanding the request** (`engine/query.py`): a typed need becomes a category, a product type, limits
   (budget, size, SPF, years, skin type) and search terms. A vague request gets one question instead of a guess.
2. **Finding threads** (`engine/sources.py`, `engine/library.py`): threads are found for free through the Arctic
   Shift archive and read through the Parse reddit.com API, then ranked so buying advice and long-term use beat
   popularity. A library of saved threads, refreshed monthly, is what answers are prepared from.
3. **Finding products in comments** (`engine/extract.py`): an AI, following `engine/prompts/extract_mentions.md`,
   lists each product, the writer's stance and a supporting quote. Code checks every quote word for word
   (`engine/verify_quotes.py`); a quote that fails is dropped.
4. Product matching, credibility scoring, ranking, answer writing and the website: next.

Quality is measured against a gold set Noemi labels by hand (`data/gold/`, with a labelling page in
`engine/labelling.py`), and against approved test sets in `eval/edge_cases/`. Reddit text stays on the machine
it was fetched on; only links, ids and labels are in this repository.

```
data/gold/   the gold set: thread links, Noemi's labels, the labelling guide
engine/      the pipeline, one module per step, with its tests in engine/tests/
api/         FastAPI service that exposes the engine (to come)
web/         Next.js site (to come)
eval/        evaluation harness, approved test sets, blind-test questions, RUNS.md
docs/        the full plan (kept out of the public repo)
```

## Setup

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest
```
