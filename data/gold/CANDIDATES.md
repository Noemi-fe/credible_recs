# Gold-set threads

Which threads make up the gold set. Their text stays on Noemi's machine (git ignores `threads/*.json`); these links let anyone with a Parse key fetch the same threads again. Fetching costs 2 Parse credits per thread.

## In the gold set

| Category | Thread | Fetched |
| --- | --- | --- |
| kitchen | [All steel electric kettle that lasts for years?](https://www.reddit.com/r/BuyItForLife/comments/1tfk6nm/) (r/BuyItForLife, 52 comments, May 2026) | 7 Oct 2026 |
| skincare | [[Product Request] Best facial exfoliant?](https://www.reddit.com/r/SkincareAddiction/comments/1vumd3s/) (r/SkincareAddiction, 35 comments) | 7 Oct 2026 |
| kitchen | [Which knife is best?](https://www.reddit.com/r/BuyItForLife/comments/1ur9shv/) (r/BuyItForLife, 27 comments) | 7 Oct 2026 |

## Picked (7 Oct 2026, found without spending credits)

| Category | Thread | Why |
| --- | --- | --- |
| kitchen | [Electric Kettle Recommendation?](https://www.reddit.com/r/BuyItForLife/comments/1v40u3t/) (r/BuyItForLife, 46 comments, Jul 2026) | A plain request after a fourth kettle died: classic recommendations. |
| kitchen | [This electric kettle has been going strong for 13 years now](https://www.reddit.com/r/BuyItForLife/comments/1g4y12m/) (r/BuyItForLife, 390 comments, Oct 2024) | Rich in long-term-use evidence. Large, so label a subset. |
| skincare | [Whats Your Favorite Gentle Exfoliant?](https://www.reddit.com/r/SkincareAddiction/comments/14km9i2/) (r/SkincareAddiction) | Sensitive, dry, acne-prone skin: matches the brief's example need. |
| skincare | [a good sensitive skin exfoliator?](https://www.reddit.com/r/SkincareAddiction/comments/15l873f/) (r/SkincareAddiction) | Same need, different voices; mentions enzyme and chemical exfoliants. |

Fetch all four (8 credits):

```bash
.venv/bin/python -m engine.parse_reddit fetch https://www.reddit.com/r/BuyItForLife/comments/1v40u3t/ https://www.reddit.com/r/BuyItForLife/comments/1g4y12m/ https://www.reddit.com/r/SkincareAddiction/comments/14km9i2/ https://www.reddit.com/r/SkincareAddiction/comments/15l873f/
```

Backups: [most gentle BHA product](https://www.reddit.com/r/SkincareAddiction/comments/14h3awk/) (skincare).

No longer a backup (10 Oct 2026): the kettle thread "what actually failed first?" (r/BuyItForLife, id 1wvt0wl) was read into the library and extracted by the AI on 9 Oct 2026, before anyone noticed it was a backup, so it can no longer be a clean gold thread. It stays in the library. Since 10 Oct the library, Bright Data reads and `extract todo` refuse every gold thread not labelled yet (engine/gold.py, unlabelled_gold_ids).

## Still needed for 10 per category

- Kitchen (5 more after the picks): ideally other products and subreddits, e.g. chef knives, cast iron, espresso, coffee grinders, tea.
- Skincare (8 more): e.g. sunscreen (r/AsianBeauty), retinol (r/30PlusSkinCare), moisturiser and cleanser (r/SkincareAddiction), UK picks (r/SkincareAddictionUK).
- Best: match them to the 10 blind-test questions once those are written.
