# Gold set

The hand-collected threads and Noemi's labels. Everything else is measured against this, so the loader checks it strictly.

```
data/gold/threads/<thread id>.json   one thread and its comments
data/gold/labels.csv                 one row per product mention
```

Check it at any time with:

```bash
.venv/bin/python -m engine.gold
```

It lists every problem at once, with the file and the line or field, or prints a summary when everything is clean.

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

## labels.csv

One row per product mentioned in a comment. Keep the header row as it is.

| Column | What to put |
| --- | --- |
| `thread_id`, `comment_id` | Which comment the row is about. |
| `product` | The product as you would name it. **Leave blank** to record "I read this comment and it mentions no product" (one row, nothing else needed). |
| `stance` | `recommend`, `warn` or `neutral`. |
| `credibility` | `high`, `medium` or `low`. It describes the comment, so give every row of the same comment the same value. |
| `reason` | One line on why, e.g. "3 years of use, names a downside". |
| `notes` | Optional, for yourself. Ignored by the engine. |

Capitals and stray spaces don't matter. Excel files saved with semicolons work too. If a reason contains a comma, the cell must be in double quotes; Excel and Numbers do this for you.
