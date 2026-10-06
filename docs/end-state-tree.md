# End-state tree

The end state is a public, explainable engine whose picks enthusiasts trust more than Vetted's or ChatGPT's, with every quote verified. It splits into 7 workstreams and 21 sub-problems, each with a test written before its code.

The tree was built top-down from first principles: the end state splits into workstreams, and each workstream into sub-problems. For each sub-problem we listed the options (diverge), chose one on accuracy, cost, effort and explainability (converge), then wrote the test and edge cases that prove it works.

&#91;embedded content: end-state tree · 7 workstreams, 21 sub-problems\]

Workstreams 1–4 are the engine, 5 is what users see, 6 measures everything, and 7 is the business side.

## End state

The project is done when all six statements below are true and backed by numbers.

- **Users** type a skincare or kitchen need and get 3 picks. Each pick has verified quotes, credibility badges and downsides, plus a skip-these list.
- **Trust is proven:** blind-test preference is at least 60% against both Vetted and ChatGPT, and 100% of shown quotes are verified.
- **Quality is proven:** extraction precision is at least 90%, recall at least 80%, and credibility agreement with Noemi's labels at least 80%.
- **It runs cheaply:** under $0.05 per query, with spend logged on every run.
- **It survives Reddit's API closing:** every source sits behind one adapter, so a new source plugs in without touching the engine.
- **Recruiters can see it:** a live site, a public how-we-score page with evaluation results, a GitHub repo with tests, and the one-page venture memo.

## Workstreams 1–4: the engine

Each row is one sub-problem: the options explored, the v1 choice, the test written before the code, and the edge cases that test must cover.

### 1 Data and sources

| Sub-problem | Options explored | Chosen for v1 | Test written first | Edge cases |
| --- | --- | --- | --- | --- |
| Get discussions | Reddit API; hand-collected gold set; Reddit for Researchers (academic only); other forums | One adapter interface; gold set now, Reddit API if approved | The same pipeline runs on both sources and returns the same fields | Deleted or removed comments; threads with 500+ comments; non-English comments; link-only comments |
| Compliance | Store nothing; store with expiry; store minimal fields and purge | Minimal fields; deleted content purged within 48 hours | A comment marked deleted disappears after the purge job | A quote already shown is later deleted on Reddit |
| Gold set | 10 threads per category; 20 per category | 10 per category, about 100 labelled comments | Every file passes schema validation | Comments that mention products outside the category |

### 2 Understanding

| Sub-problem | Options explored | Chosen for v1 | Test written first | Edge cases |
| --- | --- | --- | --- | --- |
| Query parsing | Rules; AI; AI plus rules | AI turns the query into structured fields; rules handle budget and units | 30 sample queries map to the expected category and constraints | Vague needs ("something nice for my mum"); two needs in one query; out of scope ("best laptop") gets a polite no |
| Mention extraction | AI per comment; AI per thread; named-entity model | AI per thread; quotes checked by code | Precision ≥ 90% and recall ≥ 80% on the gold set | Sarcasm ("great if you like breakouts"); negation; comparisons ("X beats Y"); abbreviations |
| Product matching | Fuzzy text match; AI; curated product list | Curated list per category, fuzzy match, AI fallback flagged for review | ≥ 90% correct on labelled same-or-different pairs | Old versus new formula; sizes and variants; US versus EU names; brand versus product line |

### 3 Credibility

| Sub-problem | Options explored | Chosen for v1 | Test written first | Edge cases |
| --- | --- | --- | --- | --- |
| Six signals | Rules; AI judge; learned model | AI judge for proof of use and honesty; rules for standing, independence, endorsement and recency | High-versus-low agreement with Noemi ≥ 80% | Genuine expert on a new account; high-karma account that promotes; deleted author; unverified flair ("dermatologist") |
| Shill detection | Rules; account patterns; AI | Rules plus an AI second opinion | ≥ 90% of planted promotional comments flagged | Honest user who includes a shop link; brand rep who discloses |
| Weight tuning | Equal; hand-tuned; learned from feedback | Equal now; tuned with Noemi after the first evaluation | Raising one weight moves rankings in the expected direction | One signal dominating every ranking |

### 4 Ranking and answers

| Sub-problem | Options explored | Chosen for v1 | Test written first | Edge cases |
| --- | --- | --- | --- | --- |
| Aggregation | Sum of credibility × stance; Bayesian average; pairwise comparison | Sum, with a minimum-evidence rule and a disagreement flag | Synthetic threads with a known winner rank it first | Ties; one very credible voice versus many average ones; mixed opinions |
| Answer writing | Template; AI; AI inside a template | AI writes only from verified quotes, inside a fixed template | An automated check finds no claim without a verified quote | Fewer than 3 qualifying products (say so); discontinued products |
| Skip-these list | Off; warnings only; warnings with evidence | A product appears only with ≥ 2 credible warnings | Planted warned-against products appear; praised ones never do | A product that is both praised and warned against |

## Workstreams 5–7: experience, evaluation, launch

Same structure as above, for what users see, how quality is measured and how the project reaches people.

### 5 Web experience

| Sub-problem | Options explored | Chosen for v1 | Test written first | Edge cases |
| --- | --- | --- | --- | --- |
| Search and cards | Next.js pages; single-page app; Streamlit | Next.js with server rendering | End-to-end test: a query returns 3 cards | Slow answers (loading state); no results; phone layout |
| Transparency | Score number only; full breakdown | Expandable breakdown plus "why this voice counts" badges | Every card shows at least 2 linked, verified quotes | Very long quotes (trimmed, link kept) |
| How-we-score page | None; static page; live metrics | Static page with the latest evaluation results | Numbers on the page match eval/RUNS.md | Metrics change after a release |

### 6 Evaluation

| Sub-problem | Options explored | Chosen for v1 | Test written first | Edge cases |
| --- | --- | --- | --- | --- |
| Offline harness | Notebook; one command | One command runs every metric | The build fails if any metric drops | Missing labels; API errors mid-run |
| Edge-case suite | Ad hoc; one file per module | One file per module, seeded from this tab | Every edge case listed here has a test | A new failure from the blind test becomes a new case |
| Blind test | Friends only; friends plus community testers | 10 enthusiast testers, protocol in the main tab | A results table with preference per rival | Testers recognising a tool's writing style |

### 7 Launch and venture

| Sub-problem | Options explored | Chosen for v1 | Test written first | Edge cases |
| --- | --- | --- | --- | --- |
| Reddit access | Wait; build on the gold set; move to Devvit later | Applied 6 Oct; gold set now; adapter ready for a new source | The memo states the risk and the plan | Request refused; access removed in 2027 |
| User interviews | Survey; 5–10 short calls | 5–10 calls before launch | Notes saved with 3 clear insights | Interviewees who only want the cheapest option |
| Launch and memo | One big post; findings-first posts | Findings-first posts that follow each community's rules | Visitors, queries and returning users tracked | Posts removed as self-promotion |

## Beyond v1

Five extras turn a good prototype into an impressive product. Build them only once the v1 metrics are met, cheapest first.

| Extra | Why it impresses | Effort |
| --- | --- | --- |
| Longevity signal ("still using it after 3 years") | Hard to fake, and exactly what kitchen buyers want to know | Low |
| Head-to-head mode ("A or B?") | Mirrors how people actually decide | Medium |
| Formula-change alerts (same name, new formula) | Brings back the Beauty Passport idea; few tools track this per product | Medium |
| More categories and sources | Proves the adapter design works beyond Reddit | Medium |
| Learning from feedback (users rate picks, weights adjust) | Shows a system that improves itself, not a static one | High |

## How the agents work

The coding agent (Claude Code or Codex) orchestrates the build. This claude.ai chat stays the place for product decisions, and Noemi decides.

- **Orchestrator:** the main coding session. It reads both tabs, picks the next step, delegates it and merges the result.
- **Sub-agents:** one per engine workstream (data, understanding, credibility, ranking, web, evaluation). Each owns its folder and its tests.
- **Noemi:** the product owner. She owns the labels, weights, scope and anything users see.

**The hill-climbing loop**

1. Run the full evaluation and find the metric furthest below its target.
2. Write a failing test for the cause, including its edge cases.
3. Propose the smallest change that could fix it.
4. Implement it and re-run everything.
5. Keep the change only if that metric improves and nothing else drops; otherwise revert it.
6. Log the run in eval/RUNS.md.
7. Escalate to Noemi whenever the fix needs a product decision.

Tests are never edited just to pass, and the gold-set labels are only ever changed by Noemi.
