# Blind test runbook (week 3, 20–26 Oct 2026)

Drafted by Claude on 10 Oct 2026 for Noemi to adapt. The protocol is the brief's; the format of the answers is
FORMAT.md (Noemi's decisions of 10 Oct 2026). Nothing personal goes in this file: testers' names, rivals' answers and
our captured answers all live in `eval/blind_test/answers/`, which is never committed.

## Before 20 Oct: testers

The brief asks for 10 testers who genuinely care about skincare or kitchen gear. Each one gets the 5 questions of
their category, so 5 skincare and 5 kitchen testers give every question 5 testers.

Write them into `eval/blind_test/answers/testers.csv` (kept on this machine only):

```
tester,category
T01,skincare
T02,kitchen
...
```

Use codes (T01, T02...), not names; keep who is who somewhere private. A tester who cares about both can be `any`.

### A message to recruit them (draft)

> Hi! I'm testing a tool that recommends [skincare / kitchen gear] for my portfolio project, and I'd love your eye as
> someone who really knows the topic. It takes about 15 minutes: you'll read 5 questions, each with 3 answers from
> different tools (names hidden), and say which you'd trust with your own money. No sign-up, and your answers stay
> anonymous. Would you be up for it this week?

## Capture day (one day, around 20 Oct)

Everything on the same day, with exactly the same wording (protocol step 5).

1. `python -m engine.blind_test capture` saves our answers for all 10 questions, with live Reddit checks, in
   `eval/blind_test/answers/<today>/raw/ours/`, and writes `capture.json` with the exact wording of each question.
2. Ask Vetted and ChatGPT each question, word for word from `capture.json`, in a fresh chat each time.
3. Paste each answer into `raw/vetted/<id>.md` and `raw/chatgpt/<id>.md`, and save a screenshot of each in
   `screenshots/` (name them `vetted-b01.png`, `chatgpt-b01.png`...).

## Making the answers look alike (FORMAT.md)

4. `python -m engine.blind_test shown eval/blind_test/answers/<day>` writes our answers into the template.
5. Claude fits each rival answer into the same template, in `shown/vetted/` and `shown/chatgpt/`: their own words, top 3
   picks, at most 90 words a pick, names and links removed. Nothing reworded, only cut.
6. Noemi checks each shown rival answer against its screenshot: same products, same order, nothing added.

## Packets

7. `python -m engine.blind_test packets eval/blind_test/answers/<day> eval/blind_test/answers/testers.csv --seed <any number>`.
   It refuses while an answer is empty, names a tool, or has a pick over 90 words, and says which file.
8. It writes, per tester, `packets/T01.html` (a plain page that opens on a phone) and `packets/T01.md`, plus `key.json`,
   which says which letter is which tool. Never send or show the key.
9. Send each tester their own page. The order of the three answers is balanced across testers, so no tool sits first
   more often.

### What each tester answers, per question

1. Which would you trust with your own money? A, B or C
2. And which would you trust least? A, B or C
3. How confident are you, from 1 to 5?
4. Why? (optional)

A simple form (Google Forms or similar) with these four questions per question works; one row per tester and question.

## Results

10. Put the responses in `eval/blind_test/answers/<day>/responses.csv`:

```
tester,question,choice,least,confidence,comment
T01,b01,B,C,4,the quotes from people who used it for years
```

11. `python -m engine.blind_test tally eval/blind_test/answers/<day> eval/blind_test/answers/<day>/responses.csv`
    prints, for each rival, how often ours was trusted more (the target: at least 60% against each), with the range a
    sample this small allows, the first choices, the confidence per tool and every comment, grouped by the answer
    chosen. The brief also asks for the three most common reasons: read the comments and group them by hand.
12. Log the result in `eval/RUNS.md`. The how-we-score page reads `eval/metrics.json`, whose two blind-test lines
    stay "not measured yet" until the result is written there (not automated yet: a small step to add before 26 Oct).

## Things to watch

- A tester who recognises a tool (the brief's edge case): note it in the comment column; it is reported, not hidden.
- An answer captured on another day, or with other words, breaks step 5: capture it again rather than mix days.
- Our answers quote Reddit: the captured files stay on this machine, like the library.
