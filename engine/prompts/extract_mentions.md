Version: extract-v7

# Finding product mentions in one Reddit thread

You read one Reddit thread saved as JSON (the shape of engine.models.Thread). For every comment, list each product
it mentions, what type of product it is, the writer's stance towards it, how well the writer knows it (the
evidence), and one supporting quote copied word for word from that comment. Also list advice about kinds of
product ("notes"), care tips on making a product last ("care") and replies that agree with the comment above
("agreements").
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
  from Walmart"), a product the writer deliberately doesn't name, or a service (laser treatments such as
  "Clear and Brilliant", facials, salon or clinic procedures: they're done to you, not bought to use). An upgrade
  part bought separately (replacement grinder burrs) is a product.
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

## Product type

Each mention gets "product_type": the type of the product itself, not the thread's ("CeraVe SA Cleanser" in an
exfoliant thread is "cleanser"; a cast iron pan praised in a kettle thread is "cast iron skillet"). A brand named
alone for the thread's kind of product ("my Lodge is 20 years old" in a cast iron thread) has the thread's type.

Use one of these names, written exactly as here, when it fits:
- skincare: "exfoliant", "cleanser", "moisturiser", "sunscreen", "retinoid", "serum", "toner", "eye cream",
  "lip balm"
- kitchen: "stovetop kettle", "electric kettle", "chef knife", "cast iron skillet", "frying pan", "saucepan",
  "dutch oven", "espresso machine", "coffee grinder", "teapot"

Otherwise write a short lowercase type in plain words ("face mask", "toaster", "makeup remover"). The names cover
their usual kinds: a gyuto or santoku is a "chef knife", a non-stick or carbon steel pan a "frying pan", an
essence a "toner", a retinol or tretinoin a "retinoid". Sun protection wins over the form: anything with SPF or
"UV" in its name, or sold to protect from the sun ("Biore UV Aqua Rich Watery Essence"), is a "sunscreen".

When you're not sure (Noemi, 9 Oct 2026): assume a product is of the thread's type unless the comment or its name
says otherwise. If you still can't tell what a product is, or whether a name is a real product at all, look it up
with a quick web search (the product's name and brand) before choosing its type, and use what you find only to
choose the type and the category. Never open a link from the thread, and never quote anything from the web: quotes
come only from the comment.

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
  - No: warn. It harmed them ("clogged my pores and burned"), it failed or broke early, they returned it or
    stopped using it, or they'd buy something else next time ("if I had my time again I'd spend a little extra").
  - A failure after a long life (Noemi, 9 Oct 2026) is recommend, with evidence "long-term use" and the tag
    "mentions flaws": "my Panasonic died after 14 years" in a thread about kettles that last praises how long it
    lasted. A failure after a short life stays warn ("died after a year").
  - A failure the writer caused themselves (a cast iron pan cracked on an induction hob, "learned that the hard
    way") is neutral: it isn't the product's fault.
- Sarcasm counts as what it means: "great if you like breakouts" is warn.
- Negation: "not a fan of X" is warn; "X didn't irritate me at all" is recommend.
- Comparisons: "X beats Y" makes X recommend and Y neutral; Y is warn only if the comment says Y itself is bad
  ("ditch Y and get X", "Y died, X is still going").

## Evidence: how well this writer knows this product

Each mention gets "evidence", one of three levels, and "evidence_tags", the reasons for it. Judge only what this
writer says about this product: not the thread, not other comments, not the other products in the same comment.
These are Noemi's definitions (data/gold/LABELLING_GUIDE.md).

- "long-term use": they say they've used it a year or more, or describe how it held up over time ("still going
  after 8 years").
- "short-term use": days or weeks, "just bought", "first impressions", or use with no time given ("I use X",
  "it's amazing").
- "no first-hand use": heard, read, someone else's experience, never tried, or suggested without saying they
  used it ("heard good things about X", "my sister swears by X", "is X any good?").

Tags, as many as fit (at least one), spelled exactly as here:
- "long-term use" or "short-term use": the level itself, when it is one of these two.
- "specific details": sizes, settings, how it failed. Not a size that is part of the product's name (the
  "8-inch" of "Victorinox Fibrox 8-inch", the "2%" of "Paula's Choice 2% BHA").
- "mentions flaws": honest about its downsides.
- "compares alternatives": names what they used before or instead ("switched from X", "better than my old Y"),
  not just a list of suggestions.
- "secondhand": someone else's experience ("my sister swears by it").
- "vague": nothing concrete; add it to short-term use or no first-hand use when there's nothing more to say.
- "cheaper alternative": suggested as a cheaper option than another product.
- "alternative for another need": suggested for a different skin type or use.
- "asks about it": a question about it ("is that the one you mean?"), with stance neutral.

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
season) are not notes: list them in "care" (below).

## Care tips: how to make it last

When a comment gives advice on looking after, using or maintaining a product or a kind of product, so it lasts or
works well ("descale it every 6 months", "never put a carbon steel knife in the dishwasher", "re-season after
scrubbing", "keep it away from sunlight"), add a care tip to "care" (Noemi, 9 Oct 2026):
- "about": the product ("Zojirushi kettle") or the kind of product ("cast iron skillet", "electric kettle"), named
  the way the comment names it, as for mentions and notes. A reply giving a tip about the product named in the
  comment it answers ("descale it monthly") takes the name from there.
- "is_kind": true when the tip is about a kind of product, false when it's about one specific product.
- "tip": the tip in a few plain words ("descale every 6 months", "no dishwasher", "store away from light"). Say only
  what the quote says: never add advice of your own.
- "quote": with the same quote rules as mentions: word for word, never from a quoted block, at most 50 words, and it
  makes sense on its own.
Advice about what to buy is a note, not a care tip. A comment can give both, and a care tip doesn't change what
counts as a product mention: list the mention too when the rules above make it one.

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
  "instructions_version": "extract-v7",
  "extracted_at": "<now, ISO 8601 in UTC, e.g. 2026-10-08T10:00:00Z>",
  "extractor": "claude-code",
  "mentions": [
    {"comment_id": "<id>", "product": "<name>", "category": "kitchen", "product_type": "electric kettle", "stance": "recommend", "evidence": "long-term use", "evidence_tags": ["long-term use", "specific details"], "quote": "<exact text>"},
    {"comment_id": "<reply id>", "product": "<name from the parent>", "category": "kitchen", "product_type": "electric kettle", "stance": "recommend", "evidence": "short-term use", "evidence_tags": ["short-term use", "vague"], "quote": "<exact text>", "refers_to": "parent"},
    {"comment_id": "<reply to a reply>", "product": "<name from further up>", "category": "kitchen", "product_type": "toaster", "stance": "recommend", "evidence": "no first-hand use", "evidence_tags": ["secondhand"], "quote": "<exact text>", "refers_to": "earlier"}
  ],
  "notes": [
    {"comment_id": "<id>", "about": "<kind or feature>", "stance": "recommend", "quote": "<exact text>"}
  ],
  "care": [
    {"comment_id": "<id>", "about": "<product or kind>", "is_kind": false, "tip": "descale every 6 months", "quote": "<exact text>"}
  ],
  "agreements": [
    {"comment_id": "<reply id>", "quote": "<exact text>"}
  ]
}
```

List everything in the order the comments appear. Values like "recommend", "kitchen", "electric kettle" and
"long-term use" are lowercase. Empty lists are fine.

## Before you finish

Run `.venv/bin/python -m engine.extract check <the threads folder>`. If anything is rejected, copy its quote
again from the comment, exactly, or fix what the reason names (an unknown evidence tag: use one from the list
above). Never change a thread file.
