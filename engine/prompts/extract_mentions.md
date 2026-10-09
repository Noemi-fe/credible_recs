Version: extract-v5

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
  the post ("the moisturizer you listed"): set "refers_to": "post", and for one named further up the same reply
  chain ("how did you like it?", then "loved it"): set "refers_to": "earlier". Otherwise leave "refers_to" out.
- Skip a product named only in passing, when the comment says nothing about it: no verdict, no use of it, no
  question about it. The poster's list of the gear they own, "V60" used only as the name of a brewing method ("for
  V60 and AeroPress") and snacks in a story are not mentions.
- A product named only in a link counts: take its name from the link's words. Never open a link. If the link's
  words don't say what it is, skip it.
- A store brand counts when it's clear which product it is ("the Walgreens one" under a comment about glycolic
  toner: "Walgreens glycolic acid toner").
- Not a product: a kind with no brand ("a gooseneck kettle", "a carbon steel pan": see notes below), an
  ingredient alone ("salicylic acid", "niacinamide") unless it names a product ("The Ordinary Niacinamide"), a
  shop (Amazon, Costco, Sephora), a maker of parts inside products (Strix), a vague store brand ("a cheap one
  from Walmart"), or a product the writer deliberately doesn't name. An upgrade part bought separately
  (replacement grinder burrs) is a product.
- Name the product as the comment writes it, abbreviations included ("Encore", "TO peeling solution", "BoJ
  sunscreen"), but without a leading "the" or "a" (keep it when it's part of the brand: "The Ordinary", "The Face
  Shop"), and with HTML codes turned back into characters ("Black & Decker", not "Black &amp; Decker"). Don't
  expand, correct or merge names: module 4 does that. The one exception: when the comment points at a product
  named earlier ("the white one" under a Biore comment, "their mineral one"), complete the name from where it was
  named ("Biore white bottle"), as with the Walgreens example. A brand in another sentence of the same comment
  doesn't count as pointing: name the product as written.
- Each product once per comment. If a comment names it twice, give one mention with the best quote. Variants
  with different verdicts are separate products ("the pink line is too heavy, the blue one is great"), and so
  are strengths and sizes named separately, even with one verdict ("Mandelic acid 5%" and "Mandelic acid 10%"
  in a list are two mentions).
- Only comments count, not the post's own title or text.
- Category: "skincare", "kitchen" or "other". Other is anything outside skincare and kitchen gear, even in a
  kitchen or skincare thread: a humidifier, a laptop, a hair dryer, a box-cutter "utility knife", makeup (primer,
  powder, foundation), cleaning products and cooking fats (dish soap, oven cleaner, Crisco). Makeup sold as sun
  protection (a BB cream or tinted product with SPF) is skincare.

## Stance

- recommend: the writer endorses it, or speaks well of it from their own use ("love it", "still going strong
  after 8 years", "worth every penny", "get the X").
- warn: the writer advises against it or reports a failure, a bad reaction or regret ("died after a year",
  "broke me out", "avoid", "overhyped", "returned it").
- neutral: named without a judgement: a question ("is X any good?", "is that the one you mean?"), "I've heard
  of X", "X is probably the most popular", "just ordered X", or a comparison with no verdict about it.
- A suggestion is recommend even when untried: a list headed "Recs", "you might like X", "there are dupes: X and
  Y".

Tricky cases:
- A bare answer in a thread that asks for recommendations ("bonavita", "I use Isntree Yam Cream") is recommend:
  it's a vote. So is telling how you use it ("I got this toner and use it on my scalp too"): using it is the
  verdict. How weak a vote it is gets judged later, in module 5.
- "Heard good things about X", "my sister swears by X", "I'm buying X for the warranty" are recommend.
- Mixed verdicts (Noemi, 8 Oct 2026): ask "would this writer tell a friend with the same need to buy it?"
  - Yes, even with complaints: recommend ("love it, but it dries me out in winter", "a bit pricey", "not quite
    enough moisture", "irritates me a bit, but it's my second pick"). Pick the quote that shows the judgement.
  - No: warn. It harmed them ("clogged my pores and burned"), it failed or broke, they returned it or stopped
    using it, or they'd buy something else next time ("if I had my time again I'd spend a little extra").
  - A failure the writer caused themselves (a cast iron pan cracked on an induction hob, "learned that the hard
    way") is neutral: it isn't the product's fault.
- Sarcasm counts as what it means: "great if you like breakouts" is warn.
- Negation: "not a fan of X" is warn; "X didn't irritate me at all" is recommend.
- Comparisons: "X beats Y" makes X recommend and Y neutral; Y is warn only if the comment says Y itself is bad
  ("ditch Y and get X", "Y died, X is still going").

## The quote

- Copy it exactly from that comment's body: same words, spelling, capitals and punctuation. Never fix a typo,
  never shorten with "..." or "…", never join separate sentences. Formatting marks such as ** may be left out.
- Never quote from a quoted block (lines starting with ">"): those are someone else's words.
- The exception: a comment written entirely as a quoted block, with words not copied from the post or another
  comment, is the writer's own formatting: quote it. The check confirms no one else in the thread wrote them.
- It must make sense on its own to a reader who sees only the quote and the product's name: prefer a full
  sentence that shows the judgement ("Love it!" alone is too thin when a fuller sentence exists). At most 50
  words; when one sentence runs longer, quote an unbroken part of it that shows the judgement. One quote may
  serve several products when a single sentence judges them all.

## Notes: advice about a kind of product

When a comment gives buying advice about a kind of product or a feature rather than a specific product ("get one
with no plastic touching the water", "carbon steel will outlast any non-stick", "avoid anything with a plastic
lid"), add a note: what it's about ("plastic-free kettle", "carbon steel pan"), named the way the comment names the
kind ("sujihiki", "VG10 steel"), the stance and a quote, with the same quote rules. Experience with a kind counts ("used cast iron for decades, never a problem"), and so does
advice about ingredients ("look for niacinamide"). Care tips that aren't about choosing (how to descale, how to
season) are not notes.

## Agreements: replies that back up the comment above

When a reply backs up what the comment it answers says ("This!", "I second this", "Same, mine lasted 10 years",
or the same verdict from their own use), add an agreement with a quote that shows it. Only replies can agree. A
reply can be both an agreement and a product mention. Not agreements (Noemi, 8 Oct 2026): the poster's thanks
("sounds good, thanks"), praise for the writing ("great write-up", "saved this"), replies to a deleted or removed
comment (there's no one left to credit), and agreement with a comment other than the one replied to.

## Skip

- Deleted or removed comments (status "deleted" or "removed", or a body of "[deleted]" or "[removed]").
- Comments by bots (AutoModerator and similar accounts that post rules or links): they aren't people.
- Comments with nothing to list.

## Output

```json
{
  "thread_id": "<the thread's id>",
  "instructions_version": "extract-v5",
  "extracted_at": "<now, ISO 8601 in UTC, e.g. 2026-10-08T10:00:00Z>",
  "extractor": "claude-code",
  "mentions": [
    {"comment_id": "<id>", "product": "<name>", "category": "kitchen", "stance": "recommend", "quote": "<exact text>"},
    {"comment_id": "<reply id>", "product": "<name from the parent>", "category": "kitchen", "stance": "recommend", "quote": "<exact text>", "refers_to": "parent"},
    {"comment_id": "<reply to a reply>", "product": "<name from further up>", "category": "kitchen", "stance": "recommend", "quote": "<exact text>", "refers_to": "earlier"}
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
