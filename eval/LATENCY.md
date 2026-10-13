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
| 12 Oct 2026 | Retrieval's per-thread work kept with the library | 0.60 / 1.60 | 1.37 / 2.89 | 2.11 / 3.65 | 5.61 / 11.37 after 0.30 | 2.89 | 4.7 | yes | yes: finding threads (warm) 0.20 / 0.46 s now 0.00 / 0.01 |
| 12 Oct 2026 | Each quote matched in its comment once (find_quote remembered) | 0.62 / 2.43 | 1.43 / 3.72 | 2.42 / 4.78 | 5.38 / 10.38 after 0.28 | 2.76 | 4.0 | yes | no: 3 ms an answer (the web's last quote re-check, 15 ms for 5 answers), not worth a memory inside the guardrail itself |
| 12 Oct 2026 | Each pair of names compared once (same_words remembered) | 0.37 / 2.61 | 1.21 / 3.37 | 1.81 / 4.51 | 4.09 / 9.91 after 0.19 | 2.18 | 5.4 | yes | yes: grouping (warm) 0.08 / 0.54 s now 0.06 / 0.32 (CPU benchmark 0.33 s now 0.18) |
| 12 Oct 2026 | The web server gets ready as it starts: library, lists, open model (in the background) | 0.38 / 1.71 | 1.13 / 2.85 | 1.86 / 5.13 | 2.61 / 6.71 after 12.82 | 2.17 | 11.8 | yes | yes: a server's first request 4.09 / 9.91 s now 2.61 / 6.71 (start-up in the background) |
| 12 Oct 2026 | While getting ready, the server also works out (and throws away) one answer per product type, without live checks, so answers' memories are ready (taking turns with visitors) | 0.62 / 4.84 | 1.41 / 5.04 | 1.48 / 13.44 | 1.59 / 8.12 after 46.56 | 2.54 | 7.7 (10 during the run) | yes | yes: first ask p50 1.86 s now 1.48 (credibility 0.35 now 0.09, finding threads 0.20 now 0.01, medians), a server's first request 2.61 now 1.59; the p95s are the open model held up by the load (up to 17 s for one call) |
| 12 Oct 2026 | `--live`, first try (real Reddit, empty cache; 8 reads at once, 0.1 s apart, no budget) | 0.69 / 30.00 | n/a | 3.80 / 31.81 | n/a | n/a | 5 | no: after about 200 reads Reddit answered 429 Too Many Requests (its limit: 200 reads in 10 minutes from one address), unread pages dropped their quotes, and the new product types lost every pick (a first attempt had also stopped on a page cut off halfway) | led to two fixes: a cut-off page drops its quote (d8e47b2); a read budget under Reddit's limit (19cfed9) |
| 12 Oct 2026 | All kept changes, stand-in checks | 0.37 / 1.75 | 1.10 / 3.23 | 1.20 / 3.34 | 1.26 / 3.41 after 26.50 | 2.02 | 4.9 | yes | final: every target met |
| 12 Oct 2026 | All kept changes, `--live` (real Reddit, empty cache, the 22 requests one after another) | 0.62 / 30.21 | n/a | 68.00 / 103.82 | n/a | n/a | 5 | no, as expected: 10 of 22 differ where Reddit changed since the snapshot (comments deleted, edited, or whose embed page no longer shows them; 7 of 40 such pages checked by hand); every quote shown passed its live check | b01 2.06 s and b02 3.23 s while the burst of 40 reads lasted; then every fresh answer waited for Reddit's budget (a read every 4 s): 22 fresh answers need about 800 reads, 4 windows of 10 minutes. Repeats: 0.2 to 0.7 s (cached checks) |

## The live site (Google Cloud Run)

Measured from outside with `python eval/live_latency.py --limit 8 --repeat` (13 Oct 2026 on): the first 8 requests
of eval/edge_cases/latency_queries.json asked one after another, straight after a deploy (a new server, an empty
cache of checks), then each again. Waited is what a visitor waits; the server reports its own time, split into the
Reddit wait (live checks of the quotes shown, which Reddit's allowance of about 200 embed reads in 10 minutes paces
once the burst of 40 is spent) and the engine's own work; queued is the rest (the network, and a server still
getting ready or working out another answer). Fresh times are p50 / max; a repeat is a remembered answer.

| Date | Change | Fresh: waited | Engine | Reddit | Queued | Repeat | Checks an answer | Kept? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 13 Oct 2026 | Baseline: 1 processor, 2 GiB (revision 00006) | 60.12 / 80.08 | 2.04 / 11.04 | 54.65 / 76.13 | 2.76 / 8.08 | 0.11 / 0.14 | 12 to 21 | the baseline. The first 3 answers took 7 to 13 s while the burst lasted; from the 4th, each waited 45 to 76 s on Reddit's pace (a read every 4 s) |
| 13 Oct 2026 | 2 processors (revision 00007) | 52.09 / 80.02 | 1.86 / 12.17 | 36.57 / 78.56 | 0.15 / 33.14 | 0.08 / 0.11 | 12 to 21 | no: the engine's time is the same within noise, and Reddit's pace is the same. Back to 1 (revision 00008). It showed the queue: the 2nd and 3rd answers waited 17 s and 33 s before their work began, behind a new server getting ready (warm_up) with the processor Cloud Run gives only during a request |
| 13 Oct 2026 | A new server gets visitors only once its /ready says it has got ready (Cloud Run's startup probe; it got ready in 65.3 s, with the processor in full), and a ping to /ready every 5 minutes (Cloud Scheduler, free tier) keeps it awake (revision 00009) | 62.25 / 80.02 | 1.34 / 3.61 | 59.55 / 78.66 | 0.16 / 0.67 | n/a | 12 to 21 | yes: no answer waits behind a server getting ready (queued max 33.14 s now 0.67), and the first answers find everything ready (engine max 12.17 s now 3.61). The first 3 answers took 3.1 to 5.9 s; from the 4th, Reddit's pace again (what checking ahead removes) |

## Checked ahead (13 Oct 2026)

Noemi's decision of 13 Oct 2026, "check ahead": the comments answers would show are read live in advance, daily
(engine/precheck.py), so a fresh answer finds its quotes already checked. `python eval/latency.py --prechecked
[CACHE_DIR]` measures it on the live library (data/library), today, with writers' standing as the site reads it, the
checker reading the pre-check's saved checks only (no network): the share of shown quotes already pre-checked, the
Reddit reads each fresh answer still needs, and fresh answers' times (each request asked once before, with instant
checks, so the engine is equally ready), with the pre-check and with nothing pre-checked (0.3 s a read while Reddit's
allowance lasts; once it is spent, worked out as a read every 4 s). Seconds as p50 / p95 over the 20 answers that show
quotes (of the 22 latency requests).

The one real run, on Noemi's computer: 56 requests (53 answered), 1,145 comments worked out in 3.7 minutes, 928 read on
Reddit in 59.2 minutes (872 passing, 2 deleted, 8 edited, 46 pages that couldn't be read) and 217 skipped as read
within 20 hours; 62.9 minutes in all. It ran before "Also worth a look" and the one-line summaries were merged, so
their comments weren't in it: the second row is the merged pre-check's next run, simulated on a copy of the cache (the
241 comments it would read taken as still saying what the library saved; about 6% failed in the real run).

| Date | Saved checks | Shown quotes pre-checked | Answers needing no read | Reads still needed (p50 / p95 / max) | Fresh, pre-checked | Nothing pre-checked, within the allowance | Nothing pre-checked, allowance spent | Requests never asked (14 made up) | Load |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 13 Oct 2026 | after the real run | 391 of 432 (90.5%) | 11 of 20 | 0 / 10 / 11 | 2.16 / 80.67 (first ask: the open model, not reads) | 4.35 / 11.18 | 110.35 / 136.04 | 85.9% of their quotes, 1 of 14 answers with no read | 20 |
| 13 Oct 2026 | after the merged pre-check's next run (simulated) | 432 of 432 (100%) | 20 of 20 | 0 / 0 / 0 | 0.78 / 21.48 | 1.79 / 4.07 | 106.45 / 129.08 | 97.4%, 8 of 14 with no read, 2 reads at most | 23 |

With the pre-check, the 10 blind-test questions needed no Reddit read in both rows: their fresh answers took 0.2 to
1.5 s. The p95s "with the pre-check" are module 1's open model on a machine loaded at 23 (l08 and l09, 46 s and 21 s
with no read at all), not live checks. Without it, a fresh answer needs 26 reads (p50): about 2 s while Reddit's
allowance lasts, and over 100 s once it is spent.
| 13 Oct 2026 | With Also worth a look and summaries (merged that day): reads paced by what Reddit's rate-limit headers say is left (at once while 50+ are left beyond 10 kept, then spread over the rest of the 10 minutes), and the comments only Also worth a look or a summary quote never wait (revision 00011) | 7.96 / 109.71 | 1.89 / 4.91 | 3.76 / 107.63 | 0.10 / 0.14 | n/a | 20 to 35 | yes, with a fix: the first 5 answers took 4.3 to 9.0 s (from the 4th, 50 to 80 s before), and when reads ran short the answers kept their 3 picks and left Also worth a look out (5 to 11 comments put off). But spread over a long rest of the 10 minutes a read waited up to 20 s (answers 6 to 8: 21, 110 and 93 s), so spread-out reads are now never slower than one every 4 s, and a visitor's read never waits over 60 s for the next 10 minutes (e8ba80b) |
