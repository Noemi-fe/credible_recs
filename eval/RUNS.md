# Evaluation runs

One entry per run of `eval/run_eval.py`: date, change tested, every metric, kept or reverted.

| Date | Change | Module 1 (outcome / product / constraints) | Quote verification | Extraction P | Extraction R | Credibility agreement | Cost/query | "Other" tags (voice / evidence) | Kept? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 7 Oct 2026 | Module 1 baseline: rules only, no AI. 30 draft cases, not yet approved | 29/30 · 21/22 · 20/22 | n/a | n/a | n/a | n/a | $0 | 0/0 · 0/0 | yes (first run) |
| 7 Oct 2026 | Cases approved by Noemi; "bucks" read as US dollars | 29/30 · 21/22 · 21/22 | n/a | n/a | n/a | n/a | $0 | 0/0 · 0/0 | yes: constraints up, nothing down |

## Notes

- **7 Oct 2026, module 1 baseline.** The three misses: two typos the rules don't correct ("clenser", "sensitve"), and "50 bucks", whose currency is Noemi's call. Read the score as optimistic: the rules were written by the same team that drafted the cases, and one rule ("150 or less") was added after seeing them. Real requests will be messier, so new cases from real use should be added over time.
- **7 Oct 2026, cases approved.** Remaining misses are the two typos ("clenser", "sensitve"), left for the AI parser rather than adding spelling rules.
