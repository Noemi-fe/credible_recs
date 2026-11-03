# Credible Picks

Three product picks for almost anything people buy, ranked by how credible the Reddit recommenders are rather than by
popularity. Every quote shown is checked word for word against its comment.

**Live: https://crediblepicks.com** (how it scores: https://crediblepicks.com/how)

A free, non-commercial research prototype: read-only, with every quote linked to its comment. It covers skincare,
haircare, kitchen gear and a general category (home, tech, pets, car gear and more). It went live on Cloud Run six days
after the first commit (6 Oct 2026). As of 2 Nov 2026: 790+ commits and 6,700+ automated tests.

## How it works

Seven modules, one per step; `engine/pipeline.py` passes each one's output to the next.

1. **Understanding the request** (`engine/query.py`): a typed need becomes a category, a product type, limits such as
   budget and skin type, and search terms. A vague request gets one question instead of a guess.
2. **Finding threads** (`engine/sources.py`, `engine/library.py`): threads are saved ahead of time (2,600+ so far)
   and ranked so buying advice and long-term use beat popularity.
3. **Finding products in comments** (`engine/extract.py`, `engine/verify_quotes.py`): an AI lists each product, the
   writer's stance and a quote; code checks every quote word for word and drops any that fails. The AI works ahead of
   time, so answering a request makes no paid AI call.
4. **Grouping and matching** (`engine/group_products.py`, `group_kinds.py`, `match_products.py`): the many ways
   commenters write one product's name become one product.
5. **Credibility** (`engine/credibility.py`): a public rubric rates each writer (account age, upvotes, expert flair,
   copied text, paid promotion) and each mention's evidence of first-hand use.
6. **Ranking** (`engine/rank.py`): a pick needs at least 3 credible recommendations from at least 2 threads. Credible
   warnings feed a "Skip these" list.
7. **Answer writing** (`engine/answer.py`): the top three from a fixed template, with verified quotes only.

`engine/web.py` is the site: a small web server on Python's standard library, running on Google Cloud Run's free tier
behind Firebase Hosting (`deploy/cloudrun/DEPLOY.md`).

## Quality and data

Quality is measured against a gold set Noemi labels by hand (`data/gold/`) and test sets in `eval/edge_cases/`.
`eval/run_eval.py` scores every module and each run is logged in `eval/RUNS.md`. On three hand-labelled threads,
extraction scores 94% precision (73 of 78) and 97% recall (73 of 75). On the ten end-to-end evaluation requests, all ten
return a full top three, and no logged run has shown a quote that fails the word-for-word check.

Threads come from the Arctic Shift archive, with Bright Data as the fallback reader, and are checked live through the
Parse reddit.com API. These three are third-party services; the project does not use Reddit's Data API. Before a quote
is shown, its comment is read again through Reddit's own embed page and needs a passing check from the last 48 hours,
so a quote whose comment was deleted, removed or edited away is never shown. Reddit text stays off this repository; only links, ids and labels
are tracked here.

## Run it locally

```bash
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest                                  # runs on a fresh clone
.venv/bin/python -m engine.pipeline "first chef's knife under £100 for a home cook"
.venv/bin/python -m engine.web                    # http://127.0.0.1:8765/, this computer only
```

The last two commands need the saved library (`data/library/`), which is not in this repository.

## Layout

```
engine/       the seven modules, the web server (web.py), pages (templates/), AI prompts (prompts/), tests (tests/)
data/gold/    the gold set: thread links, Noemi's labels, the labelling guide
data/*.json   reference lists: prices, product facts, brand lines, product pages, current models
eval/         the evaluation harness, test sets (edge_cases/) and RUNS.md
deploy/       cloudrun/ holds the live deployment (Cloud Run, Firebase Hosting) and its DEPLOY.md
```
