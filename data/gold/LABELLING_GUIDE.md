# Labelling guide (approved by Noemi, 8 Oct 2026)

One page to keep labels consistent: the same comment should get the same label on Monday and on Thursday.
The AI's instructions (engine/prompts/extract_mentions.md) use the same definitions, so your labels and the AI's
answers measure the same thing. Label before you ever see the AI's output for a thread.

## For each comment

1. Does it mention a product? A product is something you could buy: a brand with a line or model ("CeraVe
   Hydrating Cleanser", "Zojirushi kettle"), or a brand alone when it clearly means that brand's product here
   ("my Lodge is 20 years old" in a cast iron thread).
   - A reply about a product named in the comment above, or in the post ("had this one 13 years", "the one you
     listed"), mentions that product: write its name.
   - Not a product: a type with no brand ("a carbon steel pan"), an ingredient alone ("niacinamide"), a shop
     (Amazon, Sephora), a parts maker (Strix), an unnamed store brand ("a cheap Walmart one").
   - Variants with different verdicts are separate products (Nature Republic's pink line versus its blue one).
   - If there's no product: tick "No product" and move on: no voice needed.
2. A reply that agrees with the comment above ("This!", "Same, mine lasted 10 years"): tick "Agrees with the
   comment above", with or without products. It's evidence the other writer is credible.
3. Voice, only for comments with products: how much to trust the writer and this comment, whatever the product.
4. For each product: category, stance, evidence, and the tags that explain your evidence call.

## Voice: about the writer and the comment

| Level | When |
| --- | --- |
| high | At least two good signs (established member, expert flair, well upvoted for the thread's size, recent) and no red flag. |
| medium | No red flag, but fewer good signs: an ordinary owner. |
| low | Any red flag: salesy language, promotes one brand, brand-new account, downvoted, or no sign they've used anything. |

If, after labelling a while, almost nobody is high or most are low, tell Claude: the rubric gets recalibrated.

Tags record the signs you used. "well upvoted" means high for this thread, not in absolute numbers. "recent"
means the last 2–3 years; "old post" means older, which matters more for skincare (formulas change) than for
kitchen gear.

## Evidence: about this product, from this writer

| Level | When |
| --- | --- |
| long-term use | They say they've used it for a year or more, or describe how it held up over time. |
| short-term use | Days or weeks, "just bought", "first impressions". |
| no first-hand use | Heard, read or wondering about it; a recommendation without saying they used it. |

Tags: "specific details" (sizes, settings, how it failed), "mentions flaws" (honest about downsides),
"compares alternatives" (names what they used before or instead), "secondhand" (someone else's experience),
"vague" (nothing concrete).

## Stance

- recommend: endorses it or speaks well of it from use ("still going strong", "get the X").
- warn: advises against it or reports a failure, a reaction or regret ("died after a year", "broke me out").
- neutral: named without a judgement ("is X any good?", "I've heard of X").
- A bare answer in a thread asking for recommendations ("bonavita", "I use X") is recommend: it's a vote. The
  evidence label says how weak it is.
- "Heard good things about X" or "my sister swears by X" is recommend, with evidence "no first-hand use".
- A harmful reaction or a failure is warn, even if they liked something about it ("nice, but it clogged my
  pores and burned"). A mild downside stays recommend ("love it, but it dries me out in winter").
- Sarcasm counts as what it means ("great if you like breakouts" is warn). "X beats Y": X recommend, Y neutral,
  unless they say Y itself is bad. Mixed ("love it but it dries me out") is recommend; the downside goes in the
  evidence tags as "mentions flaws".
- Words in a quoted block (lines starting with ">") are someone else's: label only what this writer says.

## Category

skincare, kitchen or other: anything outside the two, even inside a skincare or kitchen thread.

## When no tag fits

Use "other" and write the reason in the note. If you keep writing the same note, it becomes a new tag at the
Sunday review.
