# Gold set

The hand-collected threads and Noemi's labels. Everything else is measured against this, so the loader checks it strictly.

```
data/gold/threads/<thread id>.json   one thread and its comments
data/gold/voices.csv                 one row per comment you read: how credible the writer is
data/gold/mentions.csv               one row per product mentioned: stance and how well the writer knows it
```

Check it at any time with:

```bash
.venv/bin/python -m engine.gold
```

It lists every problem at once, with the file and the line or field. When everything is clean it prints a summary, including how often you used the "other" tag and the notes you wrote with it.

## Fetching a thread instead of copying it

```bash
.venv/bin/python -m engine.parse_reddit fetch <thread link> [<thread link> ...]
```

This saves each thread as `threads/<id>.json`, with every comment copied exactly. It uses the Parse reddit.com API (needs `PARSE_API_KEY` in `.env`) and costs 2 of the 200 free monthly credits per thread. It never overwrites a thread already in the folder, and it refuses subreddits outside the decided list before spending anything. Parse gives no account age, karma or flair; fill those in by hand if you want them. See what you've spent with `.venv/bin/python -m engine.parse_reddit usage`.

Thread files stay on your computer only: git ignores them, so Reddit content never reaches the public repo. Their links are listed in [CANDIDATES.md](CANDIDATES.md), so the set can be fetched again on a new machine. Back the folder up yourself (Time Machine or iCloud).

## A thread file

Save each thread as `threads/<thread id>.json`. The thread id is the part after `/comments/` in the Reddit link: in `reddit.com/r/SkincareAddiction/comments/1abc23/...` it is `1abc23`.

```json
{
  "id": "1abc23",
  "community": "SkincareAddiction",
  "category": "skincare",
  "title": "Gentle exfoliant for sensitive skin?",
  "body": "Text of the post, copied exactly. Use \"\" if it is only a title.",
  "author": {"name": "username", "account_created_at": "2019-05-02", "karma": 15400, "flair": null},
  "created_at": "2025-03-01",
  "score": 150,
  "num_comments": 42,
  "url": "https://www.reddit.com/r/SkincareAddiction/comments/1abc23/gentle_exfoliant_for_sensitive_skin/",
  "collected_at": "2026-10-06",
  "comments": [
    {
      "id": "kx9y8z7",
      "parent_id": null,
      "author": {"name": "another_user", "account_created_at": "2017-11-20", "karma": 8200, "flair": "Dry/sensitive"},
      "body": "Comment text, copied exactly, line breaks included.",
      "created_at": "2025-03-02",
      "score": 37,
      "url": "https://www.reddit.com/r/SkincareAddiction/comments/1abc23/comment/kx9y8z7/",
      "status": "ok"
    }
  ]
}
```

| Field | What to put |
| --- | --- |
| `id` | Thread id from the link (see above). Must match the file name. |
| `source` | Optional; defaults to `"reddit"`. |
| `community` | Subreddit name, with or without `r/`. Must be one of the decided subreddits for the category. |
| `category` | `"skincare"` or `"kitchen"`. |
| `body` (comment) | **Copy exactly.** Quotes are checked word for word against this text, so don't fix typos or spacing. |
| `author` | `null` if the account is deleted. `account_created_at`, `karma` and `flair` can be `null` if unknown. |
| `created_at`, `collected_at` | `YYYY-MM-DD`, or `YYYY-MM-DDTHH:MM` if you have the time. Dates without a timezone are read as UTC. `01/03/2025` is refused because it is ambiguous. |
| `score` | Upvotes shown on Reddit. Can be negative. |
| `num_comments` | The count Reddit shows for the whole thread, even if you collect fewer. |
| `parent_id` | `null` for a direct reply to the post; otherwise the id of the comment it answers. |
| `url` | The comment's own link (Share → Copy link). The id at the end is the comment id. |
| `status` | `"ok"`, or `"deleted"` / `"removed"` when Reddit shows `[deleted]` / `[removed]`. |

## Labels: two layers

Credibility has two layers (brief, version 4): a **voice** label for each comment you read, and an **evidence** label for each product it mentions. A mention's weight is voice × evidence × stance.

Every label needs a reason: one or more **tags** in one cell, separated by commas (`long-term use, mentions flaws`), plus an optional **note**. When no tag fits, use `other` and write the reason in the note; a note is then required. If more than 1 in 10 labels use `other`, the tag list needs work, and the summary says so.

The allowed values and tags live in [`engine/config.py`](../../engine/config.py). Adding a tag is a deliberate change made there.

### voices.csv: one row per comment you read

| Column | What to put |
| --- | --- |
| `thread_id`, `comment_id` | Which comment. |
| `voice` | `high`, `medium` or `low`. |
| `tags` | Voice tags: established member, expert flair, well upvoted, recent, new account, salesy language, promotes one brand, old post, or other. |
| `note` | Optional; required with `other`. |

A comment with a voice row and no rows in mentions.csv is a comment you read that mentions no product.

### mentions.csv: one row per product mentioned

| Column | What to put |
| --- | --- |
| `comment_id` | Which comment. It needs its voice row in voices.csv first. |
| `product` | The product as you would name it. |
| `category` | `skincare`, `kitchen` or `other`. Label every mention, including products outside the thread's category; the engine filters them out. |
| `stance` | `recommend`, `warn` or `neutral`. |
| `evidence` | `long-term use`, `short-term use` or `no first-hand use`. |
| `tags` | Evidence tags: long-term use, specific details, mentions flaws, compares alternatives, short-term use, secondhand, vague, or other. |
| `note` | Optional; required with `other`. |

Capitals and stray spaces don't matter. Excel files saved with semicolons work too. In a comma-separated file, a cell holding several tags (or any comma) must be in double quotes; Excel and Numbers do this for you.
