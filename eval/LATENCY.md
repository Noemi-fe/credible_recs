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
| 13 Oct 2026 | Check ahead: the daily pre-check job's checks in the bucket's bundle (1,099 after two runs: 53 min, then 5 min for the day's new picks), read by the server as it gets ready; plus the first-hand fix, the refill cap and 60 s wait limit (revision 00014) | 2.76 / 5.22 | 2.60 / 5.05 | 0.04 / 0.08 | 0.14 / 0.22 | 0.08 / 0.09 | 20 to 36 | yes: no fresh answer waited on Reddit (every quote shown already checked within 48 hours), all 8 under 5.3 s, and every answer kept Also worth a look (none put off). From 60.12 / 80.08 s this morning. What's left is the engine's own work (p50 2.6 s, against 1.34 in revision 00009, before Also worth a look, summaries and the first-hand rules) |

## The engine's own work (13 Oct 2026, evening)

Also worth a look, the one-line summaries and their checks, the first-hand rules, name grouping that knows the requested
type, brand lines on Skip these and ingredient-led answers (all merged on 13 Oct 2026) made each fresh answer's own work
grow: 2 to 8 s on Cloud Run's one processor, and getting ready (one answer per product type, engine.web.warm_up) no
longer fitted Cloud Run's 4-minute startup probe (capped at 120 s, 14 of 26 product types were left cold). Each change
below was measured on its own, on top of the ones kept before it, and kept only if every answer stayed byte for byte
the same and the engine got faster.

How to read a row. Seconds of this process's processor time (steadier than wall time on a machine shared with other
builders), on the frozen copy of the library taken on the afternoon of 13 Oct 2026 (436 threads), the open model off
(its loading and reading cost the same before and after every change; with it, getting ready takes about 10 s more),
writers' standing from that copy's profile store and the Arctic Shift cache, no live checks. The baseline and the change
took turns, twice each, and each figure is the lower of the two runs:

- Getting ready: engine.web.warm_up with no time limit: the library, the price and facts lists, and one answer per
  product type (26), each worked out for the first time.
- Fresh: the 40 requests of the answers check (the 22 latency requests, the 12 ingredient requests and 6 others), each
  asked once in a process that has got ready: what a visitor waits for, less the live checks. p50 / p95 / max / total.
- Warm: each product type asked again (the minimum of 2 runs): p50 / max / total over the 26 types.
- Identical: the 40 requests' answers (engine.web.answer_json) byte for byte the same as before any change, and the
  same for the 26 product types and the 40 requests with writers' standing; eval/run_eval.py's whole report byte for byte
  the same (run with no network: live checks from a copy of the live-check cache, at a fixed time); the full test suite
  passing.

| Date | Change | Getting ready | Fresh (p50 / p95 / max / total) | Warm (p50 / max / total) | Load | Identical? | Kept? |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 13 Oct 2026 | Baseline (576700a) | 37.6 | 0.67 / 2.94 / 3.86 / 40.7 | 0.36 / 1.51 / 12.3 | 3 to 4.5 | yes (the reference) | the baseline. With the open model, getting ready took 48.2 s on this Mac (58.6 s of processor time), and the warm serum answer 2.21 s (its model reading) |
| 13 Oct 2026 | Name matching settles most pairs of names with a quick look (engine.match_products._cannot_match): a word of the shorter name that is neither in the longer one nor could be a spelling slip of one of its words (same first letter, length within one, enough letters) rules the pair out, when no "and" or joined words could change the words compared; and join_split_words checks the runs of words it could join, worked out once per name | 33.1 | 0.51 / 2.08 / 2.28 / 32.0 | 0.32 / 1.25 / 10.2 | 2.5 to 3.7 | yes | yes: of the 700,872 pairs of names the 66 answers compared, 635,285 (91%) are settled by the quick look (all 700,872 give the same answer as before); the pairs remembered fell from 700,000 (past the memory's 200,000, so it started again over and over) to 66,000 |
| 13 Oct 2026 | Grouping asks the quick look first, before same_words and the held-back word (both need every word of the shorter name found in the longer one), and remembers each name's own words (engine.group_products._matching) | 32.3 | 0.52 / 1.80 / 1.87 / 27.6 | 0.28 / 1.09 / 9.0 | 3.1 to 6.7 | yes | yes: fresh answers 31.9 s now 27.6 (the held-back word's own_words was asked 5.4 million times for the 40 requests) |
| 13 Oct 2026 | The quote guardrail's plain form worked out run by run (engine.verify_quotes._plain): a run of characters that stay as they are (no backslash, "&", emphasis mark, curly quote or doubled space) is copied whole; the others one at a time, as before | 30.1 | 0.47 / 1.68 / 1.89 / 27.2 | 0.27 / 1.04 / 8.5 | 3.0 to 11.2 | yes | yes: reading the library (every quote of every extraction checked word for word) 4.3 s now 1.3; the plain form is the same, character for character and place for place, on every text of the library (37,688: titles, posts, comments and the AI's quotes), on 3,000 made-up texts and the guardrail's tricky ones (new tests keep the one-at-a-time version as their reference) |
| 13 Oct 2026 | Grouping's candidate pairs found by the quick look's own rules (engine.match_products.match_candidates): an index of the names' words, and of their first letters and lengths, lists the names each word could be found in, and a name's candidates are the names on every one of its words' lists (then asked the quick look, both ways round); the quick look also leaves out an "and" only one name writes, as comparable does, instead of giving up | 27.6 | 0.36 / 1.18 / 1.34 / 18.6 | 0.20 / 0.92 / 6.4 | 2.8 to 7.5 | yes | yes: the 292 lists of names of the 66 answers gave 3.9 million candidate pairs by first letters alone, now 344,000 (finding them 5.3 s now 1.1); fresh answers 26.6 s now 18.6. The candidates are exactly the pairs the quick look leaves, either way round (a new test against every pair of 600 made-up names) |
| 13 Oct 2026 | Module 5's first reading of a comment: a product's name words looked up among a sentence's words (the word, its plural, its singular, then a slip only among words of about its length) rather than compared with every word (engine.credibility._found_name_words); a phrase looked for as whole words only where it is written at all (_has_any, _first_phrase); one_edit_apart read from the first letter that differs (engine/text.py) | 23.9 | 0.47 / 1.21 / 1.25 / 19.8 | 0.20 / 0.95 / 6.7 | 6.6 to 7.9 (the first round, at 24 to 37, left out) | yes | yes: getting ready 29.9 s now 23.9 (the evidence and voice of all 11,192 mentions of the library 13.4 s now 5.7, every one the same); fresh and warm answers unchanged (their comments were read while getting ready). New reference tests for the name words and one_edit_apart |
| 14 Oct 2026 | Retrieval reads a thread's comments in one go (engine.sources.comments_naming, for relevance and talking): their texts joined by a character no name pattern can match or run across, so each match is one comment's; a longer name of something else read only in the comment holding a match; a slip looked for only in words long enough to be one, each word once, and not at all for a product with no long name | 12.0 | 0.24 / 0.72 / 0.79 / 11.1 | 0.12 / 0.57 / 3.9 | 3.5 to 5.3 | yes | yes: getting ready 13.3 s now 12.0, fresh answers 12.0 s now 11.1 (relevance and talking of every thread of the library for every product type, 25,288 values, 22 s now 12.7, every one the same). From this row on the machine was much quicker than in the rows above (the previous change measured 13.3 here, 23.9 there): compare a row with the one before it, measured in turns |
| 14 Oct 2026 | What a request asks for (engine.needs.request_needs, engine.product_facts.request_asks: asked thousands of times an answer) worked out once per request, known by everything module 1 read in it; which of its needs a comment talks about (needs_met) once per comment; two kinds compared by their sets of words when nothing can join (engine.group_kinds._same_kind) | 11.7 | 0.22 / 0.60 / 0.78 / 9.8 | 0.11 / 0.56 / 3.8 | 5.1 to 7.8 | yes | yes: fresh answers 10.7 s now 9.8, getting ready 12.0 now 11.7 |
| 14 Oct 2026 | mentions_product's answer remembered for short texts (names, types, titles, a name with its quote: engine.sources); each name's UK form remembered (engine.group_products.uk_name); grouping takes from match_candidates the pairs, in order, the quick look leaves, so it never asks the quick look again, and counts two names' words at once when nothing can join (_more_words); the names that name the requested type listed once per request for every brand (engine.pipeline._has_a_product_of_the_type) | 11.8 | 0.16 / 0.54 / 0.60 / 8.2 | 0.10 / 0.62 / 3.4 | 3.6 to 4.4 | yes | yes: fresh answers 9.8 s now 8.2, warm 3.8 now 3.4. The warm cast iron skillet answer, 0.57 s against 0.62 s in this run, was quicker on its own, 5 runs each (0.83 s now 0.62, minimum): the machine's noise |
| 14 Oct 2026 | Each text's plain words remembered (engine.match_products.plain_words, a new list each time), and what comparing two care tips reads of each tip (its words, "no", metal utensils) worked out once per tip (engine.care_tips._alike) | 19.1 | 0.27 / 0.92 / 1.13 / 14.2 | 0.15 / 0.54 / 4.6 | 5.4 to 6.2 (the machine slow again: the previous change measured 18.3 / 16.7 / 5.5 in the same turns) | yes | yes: fresh answers 16.7 s now 14.2, warm 5.5 now 4.6 (the warm cast iron skillet answer, 5 runs each: 1.31 s now 0.91; its pick's care tips were compared pair by pair, each comparison reading both tips' words six times) |
| 14 Oct 2026 | The open model's reading of a request kept, the last 1,000 (engine.query_model.LlamaQueryModel.read: temperature 0, so the same words always read the same) | n/a | n/a | serum (the one product type the open model reads): 4.06 s now 0.14 | 20 to 25 (the model's own threads) | yes (the answers checks replay the model's recorded readings; a new test checks the model is asked once) | yes: getting ready answers "serum" through the model, and a visitor asking it again no longer waits for the model (on this Mac 2 to 4 s a reading; more on Cloud Run's one processor, which has no graphics chip) |
| 14 Oct 2026 | The kinds a note is the same as looked up (its very words, and only the word lists its words may join with compared in full) rather than compared with every set's (engine.group_kinds._same_kind_sets); the request's own names and each kind's product types worked out once (engine.answer._own_names, _named_types: asked again for every kind) | 17.4 (one round: the machine's speed changed by half from one run to the next) | 0.26 / 0.99 / 1.85 / 14.5 | 0.18 / 0.70 / 6.0 | 5.0 to 7.5 | yes | yes, by the work done (the machine too unsteady for times): function calls of fresh answers 57.1 million now 51.9, warm 22.2 now 19.9, getting ready 56.2 now 54.2 (cProfile counts, the same in any machine state). New reference test: the kind sets found one by one |
