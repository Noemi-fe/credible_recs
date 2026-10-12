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
