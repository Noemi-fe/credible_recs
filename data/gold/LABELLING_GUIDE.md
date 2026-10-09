# Labelling guide (approved by Noemi, 8 Oct 2026; rules added the same day for instructions v4)

One page to keep labels consistent: the same comment should get the same label on Monday and on Thursday.
The AI's instructions (engine/prompts/extract_mentions.md) use the same definitions, so your labels and the AI's
answers measure the same thing. Label before you ever see the AI's output for a thread.

## For each comment

1. Does it mention a product? A product is something you could buy: a brand with a line or model ("CeraVe
   Hydrating Cleanser", "Zojirushi kettle"), or a brand alone when it clearly means that brand's product here
   ("my Lodge is 20 years old" in a cast iron thread).
   - A reply about a product named in the comment above, or in the post ("had this one 13 years", "the one you
     listed"), mentions that product: write its name.
   - A store brand counts when it's clear which product it is ("the Walgreens one" under a glycolic toner
     comment: "Walgreens glycolic acid toner"). A vague "a cheap one from Walmart" doesn't.
   - A product you only identify by opening a link: label the true product and add the note "from link".
   - Not a product: a type with no brand ("a carbon steel pan"), an ingredient alone ("niacinamide"), a shop
     (Amazon, Sephora), a parts maker (Strix), a service (laser treatments, facials, clinic procedures). An upgrade
     part you buy separately (replacement burrs) is one.
   - Advice about a kind of product ("a sujihiki is the safer bet", "look for VG10 steel", "chemical exfoliants
     beat scrubs"): add a row, tick "kind, not a brand" and name the kind any way you like. Kinds are open-ended:
     they're grouped per request later, so "gyuto" and "Japanese chef knife" can count together.
   - Write the brand first ("FAB's exfoliating pads", "MAC fillet knife"), so names compare cleanly.
   - Skip a product named only in passing, when the comment says nothing about it (no verdict, no use, no
     question): the poster's list of gear they own, "V60" used only as a brewing method, snacks in a story.
   - Bot comments (AutoModerator and similar): "No product", never "agrees".
   - Variants with different verdicts are separate products (Nature Republic's pink line versus its blue one).
   - If there's no product: tick "No product" and move on: no voice needed.
2. A reply that backs up what the comment above says ("This!", "I second this", "Same, mine lasted 10 years"):
   tick "Agrees with the comment above", with or without products. It's evidence the other writer is credible.
   Not agreeing: the poster's thanks, "great write-up" or "saved this", a reply to a deleted comment (no one left
   to credit), agreeing with a different comment.
3. Voice, only for comments with products: how much to trust the writer and this comment, whatever the product.
4. For each product: category, stance, evidence, and the tags that explain your evidence call.

## Voice: about the writer and the comment

| Level | When |
| --- | --- |
| high | At least two good signs (established member, expert flair, well upvoted for the thread's size, recent) and no red flag. |
| medium | No red flag and fewer good signs (an ordinary owner), or exactly one red flag, whatever the good signs. |
| low | Two red flags or more (salesy language, promotes one brand, brand-new account, low karma for its activity, downvoted), or clear paid promotion on its own (a discount code, an affiliate or referral link, "#ad"). |

If, after labelling a while, almost nobody is high or most are low, tell Claude: the rubric gets recalibrated.
Red flags are counted (Noemi, 9 Oct 2026): a new account alone doesn't sink a genuine expert, it only stops
them being high.

Established member and well-regarded account are different signs (9 Oct 2026). Established: the account has
been around for a while and is regularly active (time and activity). Well-regarded: other people upvote what it
writes, plenty of karma for its number of contributions (how it's received). An old, active account with little
karma per contribution is established but not well-regarded; a young account whose few comments are loved is
the reverse.

Karma against activity: on the writer's profile, compare karma with contributions. Under about 1 karma per
contribution (209 karma for 450 contributions) is "low karma for its activity", a red flag; plenty of karma per
contribution is "well-regarded account", a good sign. "enthusiast" means the comment shows care and taste for
the category.

Tags record the signs you used. "well upvoted" means high for this thread, not in absolute numbers. "recent"
means the last 2–3 years; "old post" means older, which matters more for skincare (formulas change) than for
kitchen gear.

## Evidence: about this product, from this writer

| Level | When |
| --- | --- |
| long-term use | They say they've used it for a year or more, or describe how it held up over time. |
| short-term use | Days or weeks, "just bought", "first impressions", or used without saying for how long ("I like X", "I use X", "it's amazing"): add "vague" when there's nothing more concrete. |
| no first-hand use | Heard, read or wondering about it; a recommendation without saying they used it. |

Tags: "specific details" (sizes, settings, how it failed), "mentions flaws" (honest about downsides),
"compares alternatives" (names what they used before or instead), "secondhand" (someone else's experience),
"vague" (nothing concrete), "cheaper alternative", "alternative for another need" (suggested for a different
skin type or use), "asks about it" (a clarifying question, labelled neutral).

## Stance

- recommend: endorses it or speaks well of it from use ("still going strong", "get the X").
- warn: advises against it or reports a failure, a reaction or regret ("died after a year", "broke me out").
- neutral: named without a judgement ("is X any good?", "I've heard of X", "X is probably the most popular").
  A clarifying question ("is that the one you mean?") is neutral, with the tag "asks about it". Neutral adds
  nothing to a product's score: it never lowers it.
- A suggestion is a recommendation, even untried: a list headed "Recs", "you might like X", "there are dupes:
  X and Y". The evidence label says how much they know.
- A bare answer in a thread asking for recommendations ("bonavita", "I use X") is recommend: it's a vote. The
  evidence label says how weak it is.
- "Heard good things about X" or "my sister swears by X" is recommend, with evidence "no first-hand use".
- Mixed verdicts: would this writer tell a friend with the same need to buy it? Yes, even with complaints ("a
  bit pricey", "irritates me a bit, but it's my second pick") → recommend, tagged "mentions flaws". No → warn: it
  harmed them ("clogged my pores and burned"), failed, was returned or dropped, or they'd buy something else next
  time ("I'd spend a little extra"). A failure they caused themselves ("cracked it on induction, learned the hard
  way") → neutral.
- Sarcasm counts as what it means ("great if you like breakouts" is warn). "X beats Y": X recommend, Y neutral,
  unless they say Y itself is bad.
- Words in a quoted block (lines starting with ">") are someone else's: label only what this writer says. The
  exception: a whole comment formatted as a quote block, not copied from the post or another comment, is theirs.

## Category

skincare, kitchen or other: anything outside the two, even inside a skincare or kitchen thread. Makeup, cleaning
products and cooking fats are other; makeup sold as sun protection (a BB cream with SPF) is skincare.

## When no tag fits

Use "other" and write the reason in the note. If you keep writing the same note, it becomes a new tag at the
Sunday review.
