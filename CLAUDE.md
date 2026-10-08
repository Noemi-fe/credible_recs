# Working rules
- Explain every change in plain language. Noemi must be able to explain the whole system in interviews.
- Orchestrate: plan from docs/brief.md (both tabs), delegate each workstream to a sub-agent, then review and merge.
- Test first: write or extend the test (including the edge cases in the End-state tree tab), watch it fail, then make it pass.
- Never edit or delete a test just to make it pass. Gold-set labels belong to Noemi.
- Hill-climb: run eval/run_eval.py, fix the weakest metric, re-run. Keep a change only if metrics improve with no regression. Log every run in eval/RUNS.md.
- Never display a quote that fails word-for-word verification against its source comment.
- Reddit data comes only from the hand-collected gold set, the Parse reddit.com API (engine/parse_reddit.py) to read threads, and the Arctic Shift archive API to find them (ids and titles only: its text is never stored, since it may keep comments later deleted on Reddit). Both are third-party services, not Reddit's official API; Noemi chose Parse on 7 Oct 2026 after Reddit refused API access, and Arctic Shift the same day. No other scraping. Respect its rate limit and monthly credits, cache every response for at most 48 hours (the deletion rule); the saved library in data/library is refreshed monthly and each refresh drops content deleted on Reddit (Noemi, 7 Oct 2026), and never commit the Parse cache or gold-set threads: they stay on Noemi's machine (her decision, 7 Oct 2026). data/gold/CANDIDATES.md lists their links. Keep every source behind one adapter interface.
- Keep AI costs low: cache every call, batch where possible, log spend per run.
- Answers come from a library of saved threads, filled automatically by command, with AI steps run in batches (Noemi, 7 Oct 2026). Keep revisiting data sources and the no-API choice; the aim is a tool that can cover new products on its own.
- No Claude API key for now (Noemi, 7 Oct 2026). AI steps run through Claude Code under Noemi's existing plan, in batches, with results saved as files the engine reads. Revisit at module 3; the aim is to keep it this way.
- Keys live in .env. Never commit secrets.
- Ask Noemi before changing scoring weights, categories or anything user-facing.

# Project notes
- The brief is docs/brief.md, with the End-state tree as its last part. docs/context.md holds private background notes. Read both at the start of a session. docs/ is private and never committed.
- Recommendations: first list the options broadly (a breadth-first pass), compare them, then recommend one. Re-check earlier decisions the same way when new facts appear (Noemi, 7 Oct 2026).
- Build order (agreed 7 Oct 2026): a thin end-to-end slice first (module 1, then a basic version of modules 2–7 on the gold set, so one real request returns a top 3 with verified quotes), then improve each module through the evaluation loop.
- Decided values (categories, subreddits, label levels, reason tags) live in engine/config.py. Ask Noemi before changing them.
- Python 3.12 in `.venv`. Set up with `python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"`.
- Run tests with `.venv/bin/pytest`.
- Validate the gold set with `.venv/bin/python -m engine.gold`.
- Data shapes live in engine/models.py. The gold-set format is documented in data/gold/README.md.

# Open items
- When brief version 5 arrives: its "Never scrape" rule must be updated to match the Parse decision (Noemi asked to remember this on 7 Oct 2026).
- Also for brief version 5 (decided 7 Oct 2026): module 1 asks one clarifying question instead of guessing when a need is too vague or holds two needs; the build starts with a thin end-to-end slice; the brief's model name `claude-sonnet-5` is out of date (use the current Sonnet).
- Claude API key: not used for now (see the working rule). If it's ever needed, walk Noemi through creating one step by step (Claude Console, API keys, a monthly spend limit) and pasting ANTHROPIC_API_KEY into .env herself.
- Also for brief version 5: no Claude API key; AI steps run offline through Claude Code under Noemi's plan.
- The quarterly refresh of archived library threads (LIBRARY_ARCHIVED_REFRESH_DAYS) is provisional: revisit it when Noemi settles the data source / API choice (7 Oct 2026).
- When modules 5–6 exist: if a request lacks enough credible evidence (fewer than 3 credible mentions across 2 threads), fetch more threads automatically, smaller ones included, before giving up (Noemi, 7 Oct 2026).
