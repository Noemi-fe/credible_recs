# Working rules
- Explain every change in plain language. Noemi must be able to explain the whole system in interviews.
- Orchestrate: plan from docs/brief.md (both tabs), delegate each workstream to a sub-agent, then review and merge.
- Test first: write or extend the test (including the edge cases in the End-state tree tab), watch it fail, then make it pass.
- Never edit or delete a test just to make it pass. Gold-set labels belong to Noemi.
- Hill-climb: run eval/run_eval.py, fix the weakest metric, re-run. Keep a change only if metrics improve with no regression. Log every run in eval/RUNS.md.
- Never display a quote that fails word-for-word verification against its source comment.
- Reddit data comes only from the hand-collected gold set or the Parse reddit.com API (engine/parse_reddit.py). Parse is a third-party scraping service, not Reddit's official API; Noemi chose it on 7 Oct 2026 after Reddit refused API access. No other scraping. Respect its rate limit and monthly credits, cache every response for at most 48 hours (the deletion rule), and never commit the Parse cache or gold-set threads: they stay on Noemi's machine (her decision, 7 Oct 2026). data/gold/CANDIDATES.md lists their links. Keep every source behind one adapter interface.
- Keep AI costs low: cache every call, batch where possible, log spend per run.
- Keys live in .env. Never commit secrets.
- Ask Noemi before changing scoring weights, categories or anything user-facing.

# Project notes
- The brief is docs/brief.md, with the End-state tree as its last part. It's kept out of git because it holds job-search notes.
- Decided values (categories, subreddits, label levels, reason tags) live in engine/config.py. Ask Noemi before changing them.
- Python 3.12 in `.venv`. Set up with `python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"`.
- Run tests with `.venv/bin/pytest`.
- Validate the gold set with `.venv/bin/python -m engine.gold`.
- Data shapes live in engine/models.py. The gold-set format is documented in data/gold/README.md.

# Open items
- When brief version 5 arrives: its "Never scrape" rule must be updated to match the Parse decision (Noemi asked to remember this on 7 Oct 2026).
