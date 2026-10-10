# How the three answers are shown to testers

Noemi's decision, 10 Oct 2026 (brief, blind test protocol step 3: "names removed, formatting matched and order
shuffled"). Every answer a tester reads, ours, Vetted's and ChatGPT's, is put into the same plain template, **in the
tool's own words**. Nothing is reworded. Words are only cut, and only by these rules.

## The template

```
**1. <product name>**

<why: the tool's own reason for this pick>

"<evidence, as the tool gave it>" (<what backs it, as the tool said it>)
"<a second piece of evidence, if the tool gave one>" (...)

Downside: <the tool's own words, if it gave one>

Note: <a caution, if the tool gave one>

Price: <the price, if the tool gave one>
```

Then `**2. ...**` and `**3. ...**`, and nothing before, between or after the picks.

## The rules, the same for all three

1. **Top 3 picks.** Keep the first three products the answer recommends, in its order. If it recommends fewer, keep
   those: fewer picks are part of the answer.
2. **About the same length.** At most 90 words per pick (BLIND_TEST_WORDS_PER_PICK). Cut from the end of the reason or
   the evidence, at a word, and mark the cut with "…". Never cut a product's name.
3. **Names removed.** Remove every mention of the tool itself ("ChatGPT", "Vetted", "As an AI…", "credible recs"),
   and the tool's own headings, intros and sign-offs ("Here are some great options!", "Let me know if…").
   `python -m engine.blind_test packets` refuses an answer that still names a tool.
4. **Links become labels.** A link is shown as "(source)" after the words it was attached to. Shops and websites
   the tool named stay as words.
5. **No styling of its own.** No emoji, tables, bold or italics other than the template's. Lists inside a reason
   become one sentence, joined with commas, in the tool's order.
6. **What is dropped.** Our score breakdown, our care tips and our "how many voices" support line, which have no
   counterpart in the rivals' answers. The rivals' general advice that isn't about one of the three picks.

## Who does what

- `python -m engine.blind_test capture` saves our raw answers on the day the rivals are asked.
- Noemi asks Vetted and ChatGPT the same questions that day, with the wording in capture.json, pastes each answer into
  raw/vetted/<id>.md and raw/chatgpt/<id>.md, and keeps a screenshot of each in screenshots/.
- `python -m engine.blind_test shown <answers folder>` writes our answers into shown/ours/ with the template,
  automatically.
- Claude puts each rival answer into the template by these rules, in shown/vetted/ and shown/chatgpt/, and Noemi
  checks them against the screenshots before the packets are built.
- `python -m engine.blind_test packets` checks every shown answer (not empty, no tool's name, at most 90 words a pick)
  and builds the packets.

## What testers answer, per question

1. Which would you trust with your own money? (A, B or C)
2. And which would you trust least? (A, B or C; the one left is the middle)
3. How confident are you, from 1 to 5?
4. Why? (optional)

The first answer is the protocol's question. With the second, every response ranks all three, so each one says
whether ours was trusted more than Vetted's and more than ChatGPT's: the brief's target is at least 60% against each.
