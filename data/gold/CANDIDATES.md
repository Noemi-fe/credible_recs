# Gold-set threads

Which threads make up the gold set, each described in our words (2 Nov 2026: the posters' own titles are left out of the repository). Their text stays on Noemi's machine (git ignores `threads/*.json`); these links let anyone with a Parse key fetch the same threads again. Fetching costs 2 Parse credits per thread.

## In the gold set

| Category | Thread | Fetched |
| --- | --- | --- |
| kitchen | [A request for a durable all-steel kettle](https://www.reddit.com/r/BuyItForLife/comments/1tfk6nm/) (r/BuyItForLife, 52 comments, May 2026) | 7 Oct 2026 |
| skincare | [A request for a facial exfoliant](https://www.reddit.com/r/SkincareAddiction/comments/1vumd3s/) (r/SkincareAddiction, 35 comments) | 7 Oct 2026 |
| kitchen | [A request for a good knife](https://www.reddit.com/r/BuyItForLife/comments/1ur9shv/) (r/BuyItForLife, 27 comments) | 7 Oct 2026 |

## Picked (7 Oct 2026, found without spending credits)

| Category | Thread | Why |
| --- | --- | --- |
| kitchen | [A request for an electric kettle](https://www.reddit.com/r/BuyItForLife/comments/1v40u3t/) (r/BuyItForLife, 46 comments, Jul 2026) | A plain request after a fourth kettle died: classic recommendations. |
| kitchen | [An owner's report on a kettle after 13 years](https://www.reddit.com/r/BuyItForLife/comments/1g4y12m/) (r/BuyItForLife, 390 comments, Oct 2024) | Rich in long-term-use evidence. Large, so label a subset. |
| skincare | [A poll on gentle exfoliants](https://www.reddit.com/r/SkincareAddiction/comments/14km9i2/) (r/SkincareAddiction) | Sensitive, dry, acne-prone skin: matches the brief's example need. |
| skincare | [A request for an exfoliant for sensitive skin](https://www.reddit.com/r/SkincareAddiction/comments/15l873f/) (r/SkincareAddiction) | Same need, different voices; mentions enzyme and chemical exfoliants. |

Fetch all four (8 credits):

```bash
.venv/bin/python -m engine.parse_reddit fetch https://www.reddit.com/r/BuyItForLife/comments/1v40u3t/ https://www.reddit.com/r/BuyItForLife/comments/1g4y12m/ https://www.reddit.com/r/SkincareAddiction/comments/14km9i2/ https://www.reddit.com/r/SkincareAddiction/comments/15l873f/
```

Backups: [a request for a gentle BHA](https://www.reddit.com/r/SkincareAddiction/comments/14h3awk/) (skincare).

No longer a backup (10 Oct 2026): the kettle thread asking which part failed first (r/BuyItForLife, id 1wvt0wl) was read into the library and extracted by the AI on 9 Oct 2026, before anyone noticed it was a backup, so it can no longer be a clean gold thread. It stays in the library. Since 10 Oct the library, Bright Data reads and `extract todo` refuse every gold thread not labelled yet (engine/gold.py, unlabelled_gold_ids).

## Still needed for 10 per category

- Kitchen (5 more after the picks): ideally other products and subreddits, e.g. chef knives, cast iron, espresso, coffee grinders, tea.
- Skincare (8 more): e.g. sunscreen (r/AsianBeauty), retinol (r/30PlusSkinCare), moisturiser and cleanser (r/SkincareAddiction), UK picks (r/SkincareAddictionUK).
- Best: match them to the 10 blind-test questions once those are written.
