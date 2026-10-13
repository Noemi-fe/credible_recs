Version: summarise-v1

# Writing a pick's one-line summary

Noemi's decision of 13 Oct 2026: under a pick's name (and an "Also worth a look" item's), one sentence in our own words
saying what its credible backers say, such as: Owners of 5+ years praise how it holds heat, but two owners find it
heavy.
It is shown as "In short:", marked as our summary and never as a quote. You write it ahead of time, as with
extraction: never while someone waits for an answer. Code checks it before it is shown (engine/summaries.py), and a
summary that fails a check is simply not shown.

## What you get

`.venv/bin/python -m engine.summaries todo` answers the requests in eval/blind_test/questions.json and
eval/edge_cases/latency_queries.json from data/library and lists every pick and "Also worth a look" item that needs a
summary: none yet, one written under older instructions, or one that would not be shown in one of those answers (with
the reason). It writes data/library/summaries_todo.json (git-ignored: it holds Reddit text). For each product:
- `key`: the product's key, which the summary is saved under;
- `product`, `category`, `product_type`, and `requests`: the answers that show it;
- `credible`: its credible mentions, one per writer: `comment_id`, `stance` (recommend or warn), `voice`, `evidence`,
  `quote` (the extracted quote), `body` (the whole comment), `shown` (whether the answer shows its quote), and
  `in_every_answer` (whether it is a credible mention in every answer that shows the product);
- `has_credible_warnings`: whether any answer that shows it has a credible warning about it.

## How to write it

1. Read the quotes, and the comment around each quote, for what each writer says about this product only (a comment
   often talks about several products). Write one sentence, at most 30 words, in plain British English.
2. Say only what the comments you cite say. No praise they don't give, no advice of your own, nothing from what you
   know about the product. Say what kind of experience backs it when the comments say so (years of use, daily use).
3. Cite every comment the sentence draws on (`cites`: their comment ids), usually 2 to 5. Cite only comments marked
   `in_every_answer`, so the summary can be shown in every answer that shows the product. Prefer comments whose quote
   is `shown`, so the reader can see what the summary sums up.
4. Downsides: when `has_credible_warnings` is true, or you cite a warning, the sentence must tell the downside, with a
   contrast or a drawback word (but, though, however, warns, complains...). Cite at least one warning when there is one
   in every answer. When a recommending comment you cite gives a flaw, you may tell it too.
5. Numbers: write a number (years, months, prices, percentages, sizes) only as a cited comment gives it, in digits or
   in words. A count of people needs a people word after it ("two owners", "one user") and may not be more than the
   comments you cite. Prefer "most", "several" or "some" when an exact count adds nothing.
6. No quotation marks of any kind, and no words in the writer's own phrasing beyond a few common ones: it is our
   summary, not a quote. Don't repeat the product's name: the summary is shown under it. One sentence: use a comma or
   a semicolon, never a second full stop.
7. When the comments give nothing more than "it's good" (no detail, no experience), write nothing for that product:
   a summary that says nothing new is worse than none.

## Where to write it

data/library/summaries.json (git-ignored with the library: it paraphrases Reddit comments) holds one entry per product
key:

    {
      "kitchen:zojirushi kettle": {
        "product": "Zojirushi kettle",
        "category": "kitchen",
        "product_type": "electric kettle",
        "text": "Owners of 6 years say it still boils fast, but one owner finds the lid stiff.",
        "cites": ["c1aaaa", "c2bbbb"],
        "written_at": "2026-10-13T10:00:00Z",
        "writer": "claude-code",
        "instructions_version": "summarise-v1"
      }
    }

Then run `.venv/bin/python -m engine.summaries check`, which checks every entry with reasons, and fix or remove what
it names. Judge them as the sense evaluation does (engine/sense_eval.py), and ask of each: is it faithful to the
comments it cites?
