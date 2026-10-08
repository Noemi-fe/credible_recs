Version: extract-v2

# Finding product mentions in one Reddit thread

You read one Reddit thread saved as JSON (the shape of engine.models.Thread). For every comment, list each product
it mentions, the writer's stance towards it, and one supporting quote copied word for word from that comment. Also
list advice about kinds of product ("notes") and replies that agree with the comment above ("agreements").
Write the result as JSON to the file you're given, in the format at the end. Nothing else.

These rules match Noemi's labelling guide (data/gold/LABELLING_GUIDE.md), so the extraction and her labels
measure the same thing.

## How to read the thread

Read it with `.venv/bin/python -m engine.extract show <thread id> <threads folder>`, not the JSON file: it prints
the post and each comment you should extract, with its id, what it replies to, score, author and flair. On big
threads it shows only the highest-scored comments; extract only the comments it shows. Copy quotes from the
comment text it prints.

## What counts as a product mention

- A specific product someone could buy: a brand with a product line or model ("CeraVe Hydrating Cleanser",
  "Zojirushi kettle", "Victorinox Fibrox 8-inch"), or a brand alone when the comment clearly means that brand's
  product of the kind the thread is about ("my Lodge is 20 years old" in a cast iron thread).
- A reply about a product named in the comment it replies to ("had this one 13 years") counts as mentioning that
  product: take the name from the parent comment and set "refers_to": "parent". The same for a product named in
  the post ("the moisturizer you listed"): set "refers_to": "post". Otherwise leave "refers_to" out.
- A product named only in a link counts: take its name from the link's words.
- Not a product: a kind with no brand ("a gooseneck kettle", "a carbon steel pan": see notes below), an
  ingredient alone ("salicylic acid", "niacinamide") unless it names a product ("The Ordinary Niacinamide"), a
  shop (Amazon, Costco, Sephora), a maker of parts inside products (Strix), an unnamed store brand ("a cheap
  Walmart one"), or a product the writer deliberately doesn't name.
- Name the product as the comment writes it, abbreviations included ("Encore", "TO peeling solution", "BoJ
  sunscreen"), but without a leading "the" or "a", and with HTML codes turned back into characters ("Black &
  Decker", not "Black &amp; Decker"). Don't expand, correct or merge names: module 4 does that.
- Each product once per comment. If a comment names it twice, give one mention with the best quote. Variants
  with different verdicts are separate products ("the pink line is too heavy, the blue one is great").
- Only comments count, not the post's own title or text.
- Category: "skincare", "kitchen" or "other". Other is anything outside skincare and kitchen gear, even in a
  kitchen or skincare thread: a humidifier, a laptop, a hair dryer, a box-cutter "utility knife".

## Stance

- recommend: the writer endorses it, or speaks well of it from their own use ("love it", "still going strong
  after 8 years", "worth every penny", "get the X").
- warn: the writer advises against it or reports a failure, a bad reaction or regret ("died after a year",
  "broke me out", "avoid", "overhyped", "returned it").
- neutral: named without a judgement: a question ("is X any good?"), "I've heard of X", or a comparison with no
  verdict about it.

Tricky cases:
- A bare answer in a thread that asks for recommendations ("bonavita", "I use Isntree Yam Cream") is recommend:
  it's a vote. How weak a vote it is gets judged later, in module 5.
- "Heard good things about X", "my sister swears by X", "I'm buying X for the warranty" are recommend.
- A harmful reaction or a failure is warn, even when the writer liked something about it ("nice texture, but it
  clogged my pores and burned"). A mild, situational downside stays recommend ("love it, but it dries me out in
  winter"); pick the quote that shows the judgement.
- Sarcasm counts as what it means: "great if you like breakouts" is warn.
- Negation: "not a fan of X" is warn; "X didn't irritate me at all" is recommend.
- Comparisons: "X beats Y" makes X recommend and Y neutral; Y is warn only if the comment says Y itself is bad
  ("ditch Y and get X", "Y died, X is still going").

## The quote

- Copy it exactly from that comment's body: same words, spelling, capitals and punctuation. Never fix a typo,
  never shorten with "..." or "…", never join separate sentences. Formatting marks such as ** may be left out.
- Never quote from a quoted block (lines starting with ">"): those are someone else's words.
- It must make sense on its own to a reader who sees only the quote and the product's name: prefer a full
  sentence that shows the judgement ("Love it!" alone is too thin when a fuller sentence exists). At most 50
  words. One quote may serve several products when a single sentence judges them all.

## Notes: advice about a kind of product

When a comment gives buying advice about a kind of product or a feature rather than a specific product ("get one
with no plastic touching the water", "carbon steel will outlast any non-stick", "avoid anything with a plastic
lid"), add a note: what it's about ("plastic-free kettle", "carbon steel pan"), the stance and a quote, with the
same quote rules. Care tips that aren't about choosing (how to descale, how to season) are not notes.

## Agreements: replies that back up the comment above

When a reply agrees with the comment it answers ("This!", "Agreed, great advice", "Same, mine lasted 10 years"),
add an agreement with a quote that shows it. Only replies can agree. A reply can be both an agreement and a
product mention.

## Skip

- Deleted or removed comments (status "deleted" or "removed", or a body of "[deleted]" or "[removed]").
- Comments with nothing to list.

## Output

```json
{
  "thread_id": "<the thread's id>",
  "instructions_version": "extract-v2",
  "extracted_at": "<now, ISO 8601 in UTC, e.g. 2026-10-08T10:00:00Z>",
  "extractor": "claude-code",
  "mentions": [
    {"comment_id": "<id>", "product": "<name>", "category": "kitchen", "stance": "recommend", "quote": "<exact text>"},
    {"comment_id": "<reply id>", "product": "<name from the parent>", "category": "kitchen", "stance": "recommend", "quote": "<exact text>", "refers_to": "parent"}
  ],
  "notes": [
    {"comment_id": "<id>", "about": "<kind or feature>", "stance": "recommend", "quote": "<exact text>"}
  ],
  "agreements": [
    {"comment_id": "<reply id>", "quote": "<exact text>"}
  ]
}
```

List everything in the order the comments appear. Values like "recommend" and "kitchen" are lowercase. Empty
lists are fine.

## Before you finish

Run `.venv/bin/python -m engine.extract check <the threads folder>`. If anything is rejected, copy its quote
again from the comment, exactly. Never change a thread file.
