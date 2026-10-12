# Latency runs

One row per run of `eval/latency.py` (Noemi, 12 Oct 2026: "latency times are WAY too long. let's fix them asap,
ideally hill climbing latency through a set of eval"). Every change was measured on its own, on top of the ones kept
before it, and kept only if no answer changed and the answers got faster.

How to read a row. Seconds, as p50 / p95 over the 22 requests of eval/edge_cases/latency_queries.json (the 10
blind-test questions and 12 others), on the frozen library snapshot (data/eval/library_snapshot), with the stand-in live
checker (every check passes, 0.3 s for each comment not read yet) unless the row says `--live`:

- Warm, cached: a request asked again in a running process, every comment already checked: the engine's own time.
- Warm, uncached: the same, each comment checked costing the stand-in's 0.3 s.
- First ask: a running process asked this request for the first time, uncached checks. What a visitor of the web demo
  waits for, since the demo remembers every answer it has given.
- Cold: a fresh process: its first request, p50 / p95, "after" the start-up's own p50 (what the web server does
  before taking requests: the imports, and from the last change on, reading the library and loading the open model,
  in the background as the server starts).
- Wider: the slowest answer that read more than 16 threads (l02, 48 threads), warm, uncached checks.
- Load: the machine's 5-minute load average (8 cores) at the end of the run. Other programs ran at the same time
  (other builders' work): a higher load slows every wall-clock time, so compare rows of similar load, or the stage
  times and the CPU benchmarks given in each change's commit message.
- Identical: every answer (picks, order, quotes, look-for, skip list, notes, prices, and the lists of what was left out)
  matched the one saved before any change (data/eval/latency_baseline, git-ignored: it holds Reddit quotes), in every
  run of every request, and every quote shown had been checked live and passed.

Targets (12 Oct 2026): a warm 16-thread answer under 2 s with cached checks, under 6 s with uncached ones (0.3 s
each); the 48-thread answer under 10 s uncached.

| Date | Change | Warm, cached | Warm, uncached | First ask | Cold | Wider | Load | Identical? | Kept? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 12 Oct 2026 | Baseline: the code before any change (f699e30), stand-in checks | 7.70 / 16.36 | 14.28 / 35.52 | 12.29 / 21.48 | 18.99 / 72.28 after 0.25 | 21.01 | 13.5 | yes (it saved the baseline answers) | the baseline |
| 12 Oct 2026 | The library read once and kept in memory until a file changes | 3.38 / 9.50 | 8.98 / 15.15 | 10.65 / 19.71 | 11.48 / 17.10 after 0.19 | 15.15 | 3.2 | yes | yes: reading and checking the library, 1.97 s an answer (median), now 0.00 |
| 12 Oct 2026 | Module 4 remembers each name's words | 1.55 / 4.47 | 7.08 / 10.96 | 7.11 / 10.97 | 11.75 / 17.39 after 0.29 | 14.57 | 3.0 | yes | yes: prices 1.43 / 7.58 s (median / max) now 0.20 / 1.11, facts 0.12 / 1.52 now 0.02 / 0.24 |
| 12 Oct 2026 | Exact quick answers in name matching (a slip keeps the first letter; nothing joins without a shared start) | 2.21 / 6.12 | 7.79 / 11.77 | 7.79 / 11.67 | 10.85 / 18.77 after 0.29 | 15.61 | 3.8 | yes | yes: CPU benchmark on 3 requests, grouping 3.59 s now 2.29, lookups 0.64 now 0.43; the eval's times are within its noise (the load rose to 8 at the end) |
| 12 Oct 2026 | Grouping compares only the pairs of names that can match | 1.93 / 3.79 | 7.56 / 35.60 | 6.63 / 11.01 | 11.79 / 17.34 after 0.31 | 14.46 | 6.9 | yes | yes: grouping 0.38 / 4.01 s now 0.08 / 0.55 (CPU benchmark 2.29 s now 0.33); the 35.60 is one run held up by the machine |
| 12 Oct 2026 | Price and facts lists read once; each product's lookup worked out once per list | 1.53 / 3.62 | 6.06 / 10.69 | 6.63 / 10.71 | 11.22 / 17.06 after 0.31 | 11.95 | 6.2 | yes | yes: prices 0.21 / 1.25 s now 0.03 / 0.30, facts 0.03 / 0.30 now 0.02 / 0.08 |
| 12 Oct 2026 | Live checks of one round read up to 8 comments at once | 1.52 / 3.66 | 2.14 / 4.78 | 2.88 / 6.05 | 5.62 / 9.87 after 0.30 | 5.85 | 3.9 | yes | yes: live checks 5.04 / 8.20 s now 0.79 / 1.22 (stand-in, 0.3 s a comment) |
| 12 Oct 2026 | Fix: the live check goes on until every shown quote has passed (it stopped after 3 rounds, showing the fourth answer's new quotes unchecked) | 1.52 / 3.86 | 2.14 / 4.85 | 2.49 / 9.14 | 5.98 / 25.20 after 0.32 | 5.92 | 5.4 | yes | yes, as a fix of the verification rule (no speed-up; with the stand-in no check fails, so no extra round) |
| 12 Oct 2026 | Kinds grouped by comparing each pair of kind names once | 1.77 / 4.54 | 2.81 / 5.58 | 2.83 / 8.52 | 6.75 / 63.57 after 0.36 | 5.58 | 9.5 | yes | yes: kinds 0.86 s (max) now 0.29; the other times rose with the load (9.5) |
| 12 Oct 2026 | Module 5 remembers what each comment's words show (signs, evidence, copies) | 0.84 / 1.70 | 1.55 / 3.30 | 2.40 / 4.39 | 5.69 / 10.72 after 0.30 | 2.84 | 6.4 | yes | yes: credibility (warm) 0.52 / 2.26 s now 0.05 / 0.17, care tips 0.03 / 0.88 now 0.00 / 0.11 |
