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
- The pipeline (thin slice, 9 Oct 2026): `python -m engine.pipeline "<request>"` runs modules 1–7 on data/library and prints the answer. Modules: 1 engine/query.py, 2 engine/sources.py + engine/library.py, 3 engine/extract.py, 4 engine/group_products.py + engine/group_kinds.py + engine/match_products.py, 5 engine/credibility.py, 6 engine/rank.py, 7 engine/answer.py; glue in engine/pipeline.py. eval/run_eval.py ends with the end-to-end score over the blind-test questions.
- Parallel builders work in git worktrees under /Users/noemi/pj/credible-recs-worktrees/<branch> (one branch per module), run tests there with `/Users/noemi/pj/credible-recs/.venv/bin/python -m pytest -q` (the `-m` form imports the worktree's engine), and commit to their branch; the orchestrator merges into main. Proposed values go at the end of engine/config.py under a header per module, marked PROPOSED until Noemi decides.
- After Noemi labels a gold thread and the AI extracts it, copy its extraction from data/gold/extracted to data/library/extracted, so answers can use it.

# Open items
- When brief version 5 arrives: its "Never scrape" rule must be updated to match the Parse decision (Noemi asked to remember this on 7 Oct 2026).
- Also for brief version 5 (decided 7 Oct 2026): module 1 asks one clarifying question instead of guessing when a need is too vague or holds two needs; the build starts with a thin end-to-end slice; the brief's model name `claude-sonnet-5` is out of date (use the current Sonnet).
- Claude API key: not used for now (see the working rule). If it's ever needed, walk Noemi through creating one step by step (Claude Console, API keys, a monthly spend limit) and pasting ANTHROPIC_API_KEY into .env herself.
- Also for brief version 5: no Claude API key; AI steps run offline through Claude Code under Noemi's plan.
- The quarterly refresh of archived library threads (LIBRARY_ARCHIVED_REFRESH_DAYS) is provisional: revisit it when Noemi settles the data source / API choice (7 Oct 2026).
- Generic types ("a carbon steel pan") aren't product mentions, but credible advice about them is kept separately as "what to look for" notes, shown as a short blueprint under the picks (Noemi, 8 Oct 2026). Extraction instructions v2 and module 7; also for brief version 5.
- Voice rubric (data/gold/LABELLING_GUIDE.md): once enough labels exist, check the high/medium/low split; if there are too few highs or too many lows, recalibrate with Noemi (8 Oct 2026).
- Gold threads labelled by Noemi must never be extracted by the AI before she has labelled them (anchoring). First batch: 1vumd3s (exfoliant) and 1ur9shv (chef knife), then 1tfk6nm (kettle).
- When modules 5–6 exist: if a request lacks enough credible evidence (fewer than 3 credible mentions across 2 threads), fetch more threads automatically, smaller ones included, before giving up (Noemi, 7 Oct 2026).
- Arctic Shift's comment search times out on any search of two words or more, even within one month (8 Oct 2026); one-word searches with `fields=id,link_id,score` work and download no text. Warning threads are found by title for now.
- Commenter history (Noemi's idea, approved 9 Oct 2026), for module 5: from Arctic Shift, numbers only (subreddit, score, date of each comment; no text), turned into "active in this topic's communities" and "usually upvoted there". Keep only those derived numbers per username, under the 48-hour rule.
- Kind-level advice in the ranking (Noemi, 8–9 Oct 2026): if one kind ("Japanese gyuto") gets far more credible support than another, its products rank first. Kinds are open-ended (her choice, 9 Oct): labelled as rows with kind = yes and extracted as the AI's notes; for each request, the kinds found in its threads are grouped and each product placed in a group (modules 4 and 6). How much kind support moves a product is her decision.
- Warnings: only exfoliant, cleanser, electric kettle and frying pan are thin (8 Oct 2026). Plan approved 9 Oct: when Arctic Shift answers, find one big "most regretted / overhyped products" thread each for skincare and kitchen (4 Parse credits); otherwise wait for November's credits.
- Decisions of 9 Oct 2026 (Noemi approved all 13 recommendations):
  1. Commenter profile numbers (activity since, contributions, karma, flair) are kept with the library and refreshed monthly with it, not only 48 hours: they are public metadata, not the archived text the deletion rule is about.
  2. Extraction instructions v6: the AI also writes each product's type and an evidence level with tags; Noemi's kettle thread (1tfk6nm) is the fair test of v6, then the whole library is extracted again with it.
  3. November credits: about 60 to bring every blind-test product type to 6 or more threads about it (candidates in data/library/candidates.json).
  4–8. Module 5 and 6 values decided as proposed: voice and evidence values 1 / 0.5 / 0.25, honesty bonus +10% per sign; credible mention = recommend or warn from a high or medium voice with first-hand use; picks need 3 credible recommendations across 2 threads and a positive score; skip list needs 2+ credible warnings and more warnings than recommendations; mixed-opinions flag at 1+ credible recommendation and 2+ credible warnings; kind bonus +1 when a kind leads the next by 2x.
  9. A brand-only name can be a pick when its threads make the product clear, labelled as such ("Lodge (their cast iron skillets)").
  10. A product that failed after a long life counts as recommend (long-term use, mentions flaws), not warn.
  11. Budgets: current prices for each blind-test question's shortlist, looked up by Claude with the shop and the date.
  12. The 75 matching pairs, variant words and alias list approved; the UK name "Sage" is shown rather than "Breville".
  13. New voice tags "replies agree" and "downvoted"; a red flag means a low voice, as the guide says.
