# Blind test runbook (week 3, 20–26 Oct 2026)

Drafted by Claude on 10 Oct 2026 for Noemi to adapt. The protocol is the brief's; the format of the answers is
FORMAT.md (Noemi's decisions of 10 Oct 2026). Nothing personal goes in this file: testers' names, rivals' answers and
our captured answers all live in `eval/blind_test/answers/`, which is never committed.

Updated 16 Oct 2026 (Noemi's decision 7): the rivals are asked as a UK shopper (Capture day), testers do the blind test
before they see the site, and the response form she makes is described field by field (The response form). The site's
example requests are no longer the test questions.

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

**The blind test comes before the site.** A tester who has used the site could recognise our answers (its picks, its
"In their words" quotes), so don't send testers the site's address, or name it, until their responses are in. Send the
link afterwards if they'd like to try it: the interview can start from there.

### A message to recruit them (draft)

> Hi! I'm testing a tool that recommends [skincare / kitchen gear] for my portfolio project, and I'd love your eye as
> someone who really knows the topic. It takes about 15 minutes: you'll read 5 questions, each with 3 answers from
> different tools (names hidden), and say which you'd trust with your own money. No sign-up, and your answers stay
> anonymous. Would you be up for it this week?

## Capture day (one day, around 20 Oct)

Everything on the same day, with exactly the same wording (protocol step 5).

### Ask as a UK shopper (set this up first)

Our answers are for UK shoppers (prices in pounds, UK shops; a budget with no currency is in pounds), and 6 of the 10
questions name no currency, so the rivals must see a UK shopper too, or they answer with US products and dollars. This
Mac's clock is on US Eastern time (New York), so, before anything else that day:

- **Time zone**: System Settings, General, Date & Time: turn off "Set time zone automatically using your current
  location" and choose London (United Kingdom). The capture's folder is then named by the UK date too.
- **Region and language**: System Settings, General, Language & Region: Region United Kingdom, and English (UK) first
  among the preferred languages. In Chrome, also Settings, Languages: English (United Kingdom) first (Safari follows
  the Mac's settings).
- **Where the sites think you are**: they go by your internet address, not by the settings above. Search "what is my
  IP location": if it doesn't say the United Kingdom, connect a VPN to a UK server and keep it on for the whole
  capture.
- **ChatGPT**: signed in as usual, but in a Temporary Chat (it neither reads nor saves memories), with custom
  instructions turned off for the day (Settings, Personalization). One new temporary chat per question. Note the model
  it says it used, whether it searched the web, and the time.
- **Vetted**: in a private window of the same browser, so no earlier searches; if it asks for a country or a currency,
  choose the United Kingdom and pounds.
- **The wording stays exactly as in capture.json**: nothing added such as "I'm in the UK". Where you are is said by the
  settings above, the same for both rivals.

### Capturing

1. `python -m engine.blind_test capture` saves our answers for all 10 questions, with live Reddit checks, in
   `eval/blind_test/answers/<today>/raw/ours/`, and writes `capture.json` with the exact wording of each question.
2. Ask Vetted and ChatGPT each question, word for word from `capture.json`, in a fresh chat each time, set up as above.
3. Paste each answer into `raw/vetted/<id>.md` and `raw/chatgpt/<id>.md`, and save a screenshot of each in
   `screenshots/` (name them `vetted-b01.png`, `chatgpt-b01.png`...). Note in `capture.json`'s "note", or a file of your
   own beside it, the ChatGPT model, the VPN's country if one was used, and the times.

## Making the answers look alike (FORMAT.md)

4. `python -m engine.blind_test shown eval/blind_test/answers/<day>` writes our answers into the template.
5. Claude fits each rival answer into the same template, in `shown/vetted/` and `shown/chatgpt/`: their own words, top 3
   picks, at most 90 words a pick, names and links removed. Nothing reworded, only cut.
6. Noemi checks each shown rival answer against its screenshot: same products, same order, nothing added.

## Packets

7. `python -m engine.blind_test packets eval/blind_test/answers/<day> eval/blind_test/answers/testers.csv --seed <any number>`.
   It refuses while an answer is empty, names a tool, or has a pick over 90 words, and says which file.
8. It writes, per tester, `packets/T01.html` (a plain page that opens on a phone) and `packets/T01.md`, plus `key.json`,
   which says which letter is which tool. Never send or show the key. Each question in a packet shows its code in
   brackets ("Question 1 (b01): ..."), and the packet tells the tester their code, for the form.
9. Send each tester their own page and the form's link, and nothing about the site (see Before 20 Oct). The order of
   the three answers goes round for each question across its testers (16 Oct 2026: it had followed the testers' rows,
   which with categories alternating gave each question 3 of the 6 orders), so no tool sits first more often.

### What each tester answers, per question

1. Which would you trust with your own money? A, B or C
2. And which would you trust least? A, B or C
3. How confident are you, from 1 to 5?
4. Why? (optional)

### The response form (Noemi makes it)

One form response per tester and question, so the form's export is `responses.csv` with only its first line changed.
A Google Form with these six questions, in this order; the name in brackets is the column the tally reads
(`python -m engine.blind_test tally`):

1. Your tester code (`tester`): short answer, required. The packet says it (T01...).
2. Question code (`question`): drop-down b01 to b10, required. Each question in the packet shows its code in brackets.
3. Which answer would you trust with your own money? (`choice`): A, B or C, required.
4. And which would you trust least? (`least`): A, B or C, required, and not the same as the first: the tally refuses a
   row where they are the same, and says which line.
5. How confident are you, from 1 to 5? (`confidence`): linear scale from 1 to 5, required.
6. Why? (optional) (`comment`): paragraph, optional.

In the form's settings: don't collect email addresses, and show the "Submit another response" link, which brings the
tester back for their next question (five responses each). A pre-filled link per tester (the form's three dots, "Get
pre-filled link", with their code filled in) saves them typing it. If a tester sends one question twice, keep their
last response and delete the other row: the tally refuses two for the same tester and question.

## Results

10. Put the responses in `eval/blind_test/answers/<day>/responses.csv`: download them from the form (Responses, the
    three dots, "Download responses (.csv)") and replace the file's first line with

```
Timestamp,tester,question,choice,least,confidence,comment
```

The tally ignores Timestamp. Typed by hand instead, the file is:

```
tester,question,choice,least,confidence,comment
T01,b01,B,C,4,the quotes from people who used it for years
```

11. `python -m engine.blind_test tally eval/blind_test/answers/<day> eval/blind_test/answers/<day>/responses.csv`
    prints, for each rival, how often ours was trusted more (the target: at least 60% against each), with the range a
    sample this small allows, the first choices, the confidence per tool and every comment, grouped by the answer
    chosen. The brief also asks for the three most common reasons: read the comments and group them by hand.
12. Run the tally again with `--save` at the end: the result goes into `eval/metrics.json`, and the how-we-score page
    shows it (later evaluation runs keep it). Log the result in `eval/RUNS.md`.

## Things to watch

- A tester who recognises a tool (the brief's edge case): note it in the comment column; it is reported, not hidden.
- An answer captured on another day, or with other words, breaks step 5: capture it again rather than mix days.
- Our answers quote Reddit: the captured files stay on this machine, like the library.
