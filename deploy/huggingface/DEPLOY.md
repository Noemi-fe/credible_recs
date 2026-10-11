# Putting the demo online

This guide puts the demo on a Hugging Face Space: a public web address such as
`https://<you>-credible-recs.hf.space`, where anyone can try it. Below, `<you>` stands for your Hugging Face username.

Only you can do these steps: they create accounts and keys, and publishing is your call. Nothing here was created or
uploaded for you. Allow about an hour the first time.

## Before you start: the cost

Hugging Face now asks for its **PRO plan ($9 a month, checked on 11 Oct 2026)** before you can create a Space that
runs your own code (a "Docker Space"). The computer the Space runs on ("CPU basic": 2 processors, 16 GB of memory) is
free on top of that. This changed in July 2026: users reported it on Hugging Face's forum, and the screen asking for it
offers either PRO or adding prepaid credits to your account; Hugging Face hasn't announced it, so check what the
"Create Space" page says on the day. GoatCounter, for visit counts, is free for non-commercial sites. Whether to pay is
your decision: nothing below spends money unless you subscribe.

## What stays private, and what is public

- **The library** (the saved threads: Reddit text) goes into a **private dataset** on Hugging Face. Only the Space
  downloads it, each time it starts. It is never in the code and never in the Space's image (Hugging Face lets anyone
  run a public Space's image, so this matters).
- **Feedback** goes into a second **private dataset**.
- **The Space itself can be public.** It holds two files, `Dockerfile` and `README.md`, with no secrets and no Reddit
  text. The code it runs is the public GitHub repository.
- **Tokens** (Hugging Face's passwords for programs) live only in your `.env` file, which git never uploads, and in the
  Space's secret settings.

## 1. Create your Hugging Face account

1. Go to <https://huggingface.co/join> and sign up. Confirm your email.
2. Your username is the `<you>` in every name below.
3. Recommended: turn on two-factor authentication (Settings, Authentication).
4. If you decided to go ahead: subscribe to PRO (Settings, Billing).

## 2. A token for your computer, to upload the library

1. On Hugging Face: your picture (top right), **Settings**, **Access Tokens**, **Create new token**.
2. Choose **Write**. Name it `credible-recs computer`. Create it and copy it (it starts with `hf_`).
3. Open the `.env` file in the project folder (the one with your other keys) and add a line:

   ```
   HF_TOKEN=hf_paste_your_token_here
   ```

4. In the project folder, install what uploading needs:

   ```bash
   .venv/bin/pip install -e ".[deploy]"
   ```

## 3. Create two private datasets

On Hugging Face: **New** (top right, the "+" menu), **Dataset**. Do this twice:

| Name                     | Visibility  | Holds                                      |
|--------------------------|-------------|--------------------------------------------|
| `credible-recs-library`  | **Private** | the saved library                          |
| `credible-recs-feedback` | **Private** | what visitors send through the feedback form |

Double-check both say **Private**. (The upload command can also create the library one for you, private: add
`--create` in step 4.)

## 4. Upload the library

In the project folder, first a dry run, which changes nothing and says what would go up:

```bash
.venv/bin/python -m deploy.push_library <you>/credible-recs-library --dry-run
```

It should name about as many threads and extractions as you have in `data/library`. Then the real upload:

```bash
.venv/bin/python -m deploy.push_library <you>/credible-recs-library
```

It uploads the threads, the extractions and `profiles.json`, and nothing else. It refuses if the dataset isn't
private.

## 5. A token for the Space

The Space needs its own token: one that can only touch these two datasets.

1. **Settings**, **Access Tokens**, **Create new token**, and this time choose **Fine-grained**.
2. Name it `credible-recs space`.
3. Under **Repositories permissions**, search for and add both datasets: `<you>/credible-recs-library` and
   `<you>/credible-recs-feedback`.
4. Tick **Read access to contents of selected repos** and **Write access to contents/settings of selected repos**.
   Leave everything else unticked.
5. Create it and copy it. You'll paste it in step 7; you don't need to keep it anywhere else.

Why "write"? The Space writes feedback into the feedback dataset. It only ever reads the library (the code never writes
there), but Hugging Face gives both selected datasets the same rights. If you'd rather the Space's token could only
read, tick only the read box and skip `CREDIBLE_RECS_FEEDBACK_REPO` in step 7: feedback then stays on the Space's own
disk, which is wiped at every restart.

## 6. Create the Space

**New**, **Space**:

- Name: `credible-recs`
- SDK: **Docker**, template **Blank**
- Hardware: **CPU basic** (free)
- Visibility: **Public**

## 7. The Space's settings

In the Space: **Settings**, **Variables and secrets**.

Add one **secret** (secrets stay hidden, even from you, once saved):

| Name       | Value                       |
|------------|-----------------------------|
| `HF_TOKEN` | the Space token from step 5 |

Add these **variables** (variables are public on Hugging Face, so nothing secret goes here):

| Name                          | Value                             |
|-------------------------------|-----------------------------------|
| `CREDIBLE_RECS_LIBRARY_REPO`  | `<you>/credible-recs-library`     |
| `CREDIBLE_RECS_FEEDBACK_REPO` | `<you>/credible-recs-feedback`    |

Optional variables, only if you need them:

| Name                          | What it does |
|-------------------------------|--------------|
| `CREDIBLE_RECS_ALLOWED_HOSTS` | The addresses the site answers, comma-separated. Without it, the Space's own address (`<you>-credible-recs.hf.space`). Add one only for another address, such as your own domain. |
| `CREDIBLE_RECS_GOATCOUNTER`   | Turns on visit counts: see step 11. |
| `CREDIBLE_RECS_QUERY_MODEL`   | `off` runs module 1 on its rules alone, without the open model (faster to start). |
| `CREDIBLE_RECS_REF`           | Which version of the code to run: a branch, a tag or a commit of the GitHub repository. `main` without it. |

## 8. Give the Space its two files

In the Space: **Files**, **Add file**, **Upload files**. From this folder (`deploy/huggingface/`), upload
`Dockerfile` and `README.md` (replace the README Hugging Face made). Commit.

That's all the Space holds. Everything else, `start.sh` included, comes with the code from GitHub.

## 9. Watch it start

The Space shows **Building** for a few minutes (the **Logs** tab, **Build**, shows progress), then **Running**. In
**Logs**, **Container**, you should see, in this order:

- `Library ready: ... threads, ... extractions.`
- `Open model ready.` (about a minute: it downloads the 1.1 GB model each time the Space starts)
- `Feedback is uploaded to the private dataset <you>/credible-recs-feedback every 5 minutes.`
- `Serving the public site for <you>-credible-recs.hf.space on port 7860`

Then open `https://<you>-credible-recs.hf.space` and try an example. The first answer to a new question can take up
to a minute: every quote is checked live on Reddit first, a few seconds apart. Asking again is instant.

## 10. Check feedback arrives

Answer "Was this useful?" on the site, wait five minutes, then on your computer:

```bash
.venv/bin/python -m engine.feedback --repo <you>/credible-recs-feedback
```

It downloads the feedback into `data/feedback/downloaded/` (which git ignores) and sums it up: how many found answers
useful, the answers to "First time here?", and every comment with the request it was about. You can also browse the
files in the dataset on Hugging Face (one small file per upload).

## 11. Turn on visit counts, when you're ready

1. Sign up at <https://www.goatcounter.com> (free for non-commercial sites). The code you choose becomes your counting
   address: `credible-recs` gives `credible-recs.goatcounter.com`.
2. In the Space's variables, add `CREDIBLE_RECS_GOATCOUNTER` with that code (letters, digits and hyphens only).
3. **Settings**, **Restart this Space** (if it hasn't restarted by itself).

Your GoatCounter page then shows visits, and these events: `search`, `answer-ok`, `answer-clarify`,
`answer-out-of-scope`, `feedback-useful`, `feedback-not-useful`, `first-time-yes`, `first-time-no`. Never what anyone
typed. GoatCounter uses no cookies, and it never counts visits to the demo on your own computer.

## Later

- **A new library**, after a monthly refresh: run step 4 again (without `--dry-run`), then the Space's **Settings**,
  **Restart this Space**. Threads dropped from the library are removed from the dataset too.
- **New code**, once it's on GitHub's `main`: **Settings**, **Factory reboot** (on some accounts "Factory rebuild"),
  which builds the Space again from scratch. The sure way, which also keeps the Space on one version: set the variable
  `CREDIBLE_RECS_REF` to the newest commit's long code (from GitHub); a new value always fetches the code anew.
- **Sleeping**: on free hardware the Space goes to sleep after a while without visitors. The next visit wakes it, in a
  minute or two.
- **Taking it down**: in **Settings**, pause the Space (or delete it). The datasets stay until you delete them.
- **A token leaked?** Delete it under **Access Tokens**, make a new one, and put it where the old one was.

## If something goes wrong

Look at the Space's **Logs**, **Container**.

| The logs say | What to do |
|---|---|
| `Not starting: this Space needs the secret HF_TOKEN and the variable CREDIBLE_RECS_LIBRARY_REPO` | Step 7. |
| `Not starting: the library couldn't be downloaded` | Check the dataset's name in step 7, and that the Space token can read it (step 5). |
| `Not starting: the dataset ... has no threads` | Step 4. |
| `Not starting: the public site needs CREDIBLE_RECS_ALLOWED_HOSTS` | Set that variable to `<you>-credible-recs.hf.space`. |
| `Refused a request addressed to '...'` while the site says it only answers its own website | If the name in the logs is the site's own address as Hugging Face writes it, add it to `CREDIBLE_RECS_ALLOWED_HOSTS`. |
| `Feedback not uploaded: the dataset ... is public` | Make the feedback dataset private: nothing is uploaded until it is. |
| `Feedback upload to ... failed` | The Space token needs write access to the feedback dataset (step 5). |
| `llama.cpp can't run here` or `The open model couldn't be downloaded` | Nothing breaks: module 1 uses its rules alone. |
| The site works, but every answer comes back without picks | The live check on Reddit may be failing from Hugging Face's servers: ask Claude to look at the logs. |
