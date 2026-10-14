# The live site on Google Cloud Run

Chosen on 12 Oct 2026 instead of a Hugging Face Space, which now needs a paid plan to run code. Cloud Run runs the site
in Noemi's own Google Cloud project (credible-picks), on the free tier: one server at most, none while nobody visits,
in europe-west1 (Belgium, the nearest free-tier region). A budget alert at 1 EUR warns long before anything is spent.

Since 13 Oct 2026 (Noemi's decision: "check ahead") a second piece runs next to it: the daily pre-check
(engine/precheck.py). Before an answer shows a quote, the comment is read live on Reddit's embed page, and Reddit allows
about 200 such reads in 10 minutes from one address, so a fresh answer (20 to 40 reads) could wait a minute or two.
Once a day the pre-check reads the comments answers would show, so visitors' answers find them already checked. The
rule is unchanged: a quote is shown only with a passing check from the last 48 hours.

## What lives where

- **The image** (the code, the saved library of Reddit threads, the open model): private, in the project's own
  Artifact Registry. Built by Cloud Build from a bundle made on Noemi's computer (deploy/cloudrun/make_context.py), so
  the library is never in this public repository and never public anywhere.
- **The live checks' bucket** (`credible-picks-live-checks`, CREDIBLE_RECS_LIVE_CACHE_BUCKET): one object,
  `live_check/bundle.json`, holding what Reddit's embed page said about each comment the pre-check holds a check of
  from the last 48 hours (its text and when it was read, nothing else; about 0.6 MB). The pre-check runs on a machine
  of its own whose disk starts empty: it reads the bundle as it starts, so what is still fresh isn't read again, and
  writes it back twice a run (midway, in case the run is cut short, and at the end). The site reads it into its own
  folder as it gets ready and then at most once an hour, when the keep-warm ping asks /ready (Cloud Run gives the
  server its processor only during a request), downloading it only when it has changed (a small metadata read of its
  version first), and never writes to the bucket: its own checks stay in its folder (the keep-warm ping
  keeps the server, and so its folder, alive). Private: uniform bucket-level access, public access prevention, readable
  only by the project's compute service account. In europe-west1. Every object is deleted once it is 2 days old
  (deploy/cloudrun/live_cache_lifecycle.json; Google runs these deletions about once a day, so it can stay up to a day
  longer, unused; it is written again every day, so it goes only if the pre-check stops), and soft delete is off, so
  nothing deleted is kept. No entry older than 48 hours is ever written into the bundle, copied out of it or used.
- **The pre-check** (Cloud Run job `credible-recs-precheck`): the site's own image, running
  `python -m engine.precheck --limit 2000 --minutes 75`, started by Cloud Scheduler (`credible-recs-precheck-daily`) at
  4 am UK time. It reads as fast as Reddit's rate-limit headers allow (never slower than one every 4 s) and starts no
  read 75 minutes after it started, so a run's length, and its bill, doesn't depend on Reddit's pace (14 Oct 2026: the
  run before read its then budget of 1,100 in 46 minutes, after 84 s working out the answers, and left 459 of 1,967
  comments unread; 75 minutes is about 1,700 reads). Its report (counts and times, never a comment's words) is in the job's logs. On
  Noemi's computer on 13 Oct 2026 a run worked out 1,145 comments in 3.7 minutes and read 928 of them in 59 minutes
  (872 passing, 2 deleted, 8 edited, 46 pages that couldn't be read). Then, for the comments whose embed page shows no
  comment ("Not supported comment", about 1 in 8; Noemi, 13 Oct 2026: "Use Bright Data"), it reads their threads
  through Bright Data, within 30 records a run (the most useful threads first), and saves a check for each comment it
  finds there. It needs the Bright Data key, the Secret Manager secret `bright-data-key` (below; there since 14 Oct
  2026): deployed without it, the job runs with this step off. The site never calls Bright Data. Since 13 Oct 2026
  (Noemi: "Keep only comments we use") it then verifies the comments the slimmed library keeps, up to 400 a run
  (config.LIBRARY_VERIFY_READS), those verified longest ago first, about 26 minutes more (see "The slimmed library"
  below).
- **The verification record** (`live_check/verified.json`, in the same bucket): for each comment the slimmed library
  keeps, its latest read on Reddit (when, and what it said: passing, deleted, removed, edited or unreadable) and its
  last passing read. Ids, dates and outcomes only, never a comment's words (about 1 MB for 10,000 comments). Written by
  the pre-check at the end of each run, and read by deploy.sh before it bundles the library. Like every object in the
  bucket it is deleted once 2 days old, but it is written again every day: it goes only if the pre-check stops for two
  days, and then the library's own dates (as of the last deploy) are the record, so nothing unverified is ever kept
  longer, only verified comments are read again.
- **On-demand reading's bucket** (`credible-picks-on-demand`, CREDIBLE_RECS_ON_DEMAND_BUCKET; 14 Oct 2026, Noemi's plan,
  part 3; engine/on_demand.py): two objects. `on_demand/queue.json`, the requests the library couldn't answer yet: for
  each, only the product type module 1 understood, its category and subreddits and up to 3 of its need words (never
  the request as typed, never a time or anything about the visitor), and the reading job's own state (its lease, its
  time this month, its Gemini calls today). `on_demand/threads.json`, the bundle of the threads the job has read and
  not yet baked into the image: each thread's file and its extraction's, as the library saves them. Private like the
  live checks' bucket (uniform access, public access prevention, soft delete off, europe-west1), readable and writable
  by the project's compute service account only. A separate bucket because its objects must outlive the live checks'
  2 days: every object is deleted once 37 days old (deploy/cloudrun/on_demand_lifecycle.json, the archive's keeping
  time), and every deploy empties the bundle of what the new image holds.
- **The reading job** (Cloud Run job `credible-recs-reader`): the site's own image, running `python -m engine.on_demand
  run`. No schedule of its own: the site starts it (Cloud Run's jobs:run) as soon as it queues a request, and the
  keep-warm ping starts it again when a start failed. For each waiting request it finds threads with Arctic Shift's
  free title search and reads them from its archive (the library's own archive reader, at its 10 s pace; no Bright
  Data, no Parse), has Gemini extract each within the free allowance, checks every quote word for word, slims them when
  the lean library is there, and adds them to the bundle; the site takes them in within 5 minutes. Its one secret is
  the Gemini key (`gemini-key`, below).
- **Feedback**: Noemi's private Hugging Face dataset Noemix/credible-recs-feedback. The site uploads it in batches with
  the token stored as the Secret Manager secret `hf-token`.
- **Visit counts**: GoatCounter, site code noemix (CREDIBLE_RECS_GOATCOUNTER).
- **Settings** the site reads: CREDIBLE_RECS_ALLOWED_HOSTS (the site's own addresses), CREDIBLE_RECS_GOATCOUNTER,
  CREDIBLE_RECS_FEEDBACK_REPO, CREDIBLE_RECS_LIVE_CACHE_BUCKET, CREDIBLE_RECS_ON_DEMAND_BUCKET and
  CREDIBLE_RECS_ON_DEMAND_JOB (`projects/credible-picks/locations/europe-west1/jobs/credible-recs-reader`, the job it
  starts; without it the site queues nothing); the secret HF_TOKEN. The pre-check job reads
  CREDIBLE_RECS_LIVE_CACHE_BUCKET, CREDIBLE_RECS_ON_DEMAND_BUCKET, CREDIBLE_RECS_PRECHECK_BRIGHT_DATA ("off" when it was
  deployed without the Bright Data key) and the secret BRIGHT_DATA_API_KEY; the reading job
  CREDIBLE_RECS_ON_DEMAND_BUCKET and the secret GEM_API_KEY.

## Updating the site

After committing (and after new threads are extracted), from the repository's root:

    sh deploy/cloudrun/deploy.sh

It turns on-demand reading off for that deploy if the Gemini key's secret isn't there yet (below; the site deploys
anyway and never says it has started reading), and the pre-check's Bright Data verification off if the Bright Data
key's isn't (the job deploys anyway), makes sure both buckets exist with their rules,
brings the threads read on demand into data/library, applies the pre-check's verification record to the
library, bundles the current commit with the library, builds the private
image and deploys the site, then points the pre-check job and the reading job at the same image, makes sure the daily
schedule exists, lets the on-demand bucket go of the threads the image now holds, and prints the address. Safe to run
again: each step creates what is missing and sets again what is there.

## The slimmed library (Noemi, 13 Oct 2026: "Keep only comments we use")

Each extracted thread keeps its title and only the comments answers use (`python -m engine.library slim`,
engine/slim.py); every other comment keeps its id, date, score and replies, never its words or writer. Each kept
comment must be verified on Reddit (its embed page, free) within 30 days, or it loses its words and its mentions
(engine/verify.py). The library is baked into the image, and the checks happen in the cloud, so the two meet at each
deploy:

1. every day the pre-check reads the kept comments verified longest ago (400 a run) and writes what each read said to
   `live_check/verified.json`;
2. `deploy.sh` copies that record to a temporary file (`gcloud storage cp`) and runs
   `python -m engine.library apply-checks --ledger <it>` before bundling: each passing comment gets its date, and a
   comment found deleted or edited, or not verified within 30 days, loses its words and its mentions, in
   data/library on this computer; the image built next holds the result. With no record yet (before the pre-check's
   first run), this computer's checks of the last 48 hours and the 30-day deadline are applied alone.

So deploy at least every couple of weeks: the image keeps what the last deploy applied, and a comment the pre-check
finds deleted is dropped from the image at the next deploy (until then answers never show it: every quote shown is
checked live within 48 hours). After a data round, once the new threads' extractions are final, slim them
(`python -m engine.library slim`; `--dry-run` first says what it would do): a thread not slimmed yet stays whole and
under the whole-thread rules (read again monthly through Bright Data, its text removed at 37 days if not).

To catch up by hand (say the pre-check stopped for a while): run it on this computer with a bigger verification
budget, then apply its record (it is kept in .cache/verified.json):

    .venv/bin/python -m engine.precheck --limit 0 --verify 2000
    .venv/bin/python -m engine.library apply-checks

### The commands it runs, in order

The project number is `NUMBER` below (`gcloud projects describe credible-picks --format='value(projectNumber)'`), and
`RUNNER` is the account the site and the job run as, `NUMBER-compute@developer.gserviceaccount.com`.

0. The two keys' secrets, which Noemi creates herself ("The Gemini key" and "The Bright Data key" below). The script
   never makes or reads them; it only checks they are there, and without one it deploys anyway with that piece off:
   on-demand reading without the Gemini key, the pre-check's Bright Data verification without the Bright Data key
   (14 Oct 2026: a missing key never stops a deploy):

       gcloud secrets describe gemini-key --project credible-picks
       gcloud secrets describe bright-data-key --project credible-picks

1. The APIs: `gcloud services enable storage.googleapis.com cloudscheduler.googleapis.com secretmanager.googleapis.com
   --project credible-picks`
2. The bucket, the first time only:

       gcloud storage buckets create gs://credible-picks-live-checks --project credible-picks --location europe-west1 \
           --uniform-bucket-level-access --public-access-prevention --soft-delete-duration 0 \
           --lifecycle-file deploy/cloudrun/live_cache_lifecycle.json

   then, every time, its rules set again and the service account let in (read, write and delete objects only):

       gcloud storage buckets update gs://credible-picks-live-checks --project credible-picks \
           --public-access-prevention --clear-soft-delete --lifecycle-file deploy/cloudrun/live_cache_lifecycle.json
       gcloud storage buckets add-iam-policy-binding gs://credible-picks-live-checks --project credible-picks \
           --member serviceAccount:RUNNER --role roles/storage.objectUser

   and the same for on-demand reading's bucket, with its own rules (every object deleted once 37 days old):

       gcloud storage buckets create gs://credible-picks-on-demand --project credible-picks --location europe-west1 \
           --uniform-bucket-level-access --public-access-prevention --soft-delete-duration 0 \
           --lifecycle-file deploy/cloudrun/on_demand_lifecycle.json
       gcloud storage buckets update gs://credible-picks-on-demand --project credible-picks \
           --public-access-prevention --clear-soft-delete --lifecycle-file deploy/cloudrun/on_demand_lifecycle.json
       gcloud storage buckets add-iam-policy-binding gs://credible-picks-on-demand --project credible-picks \
           --member serviceAccount:RUNNER --role roles/storage.objectUser

3. The threads read on demand into data/library (through gcloud's own sign-in; when it fails, the deploy goes on and
   the site still finds them in the bucket):

       CREDIBLE_RECS_ON_DEMAND_BUCKET=credible-picks-on-demand .venv/bin/python -m engine.library pull-bucket

   Then the verification record applied to the library (13 Oct 2026), before it is bundled:

       gcloud storage cp gs://credible-picks-live-checks/live_check/verified.json <a temporary file>
       .venv/bin/python -m engine.library apply-checks --ledger <that file>

   (with no record there yet, `apply-checks` alone). Then the site, as before, with `CREDIBLE_RECS_LIVE_CACHE_BUCKET=credible-picks-live-checks`,
   `CREDIBLE_RECS_ON_DEMAND_BUCKET=credible-picks-on-demand` and
   `CREDIBLE_RECS_ON_DEMAND_JOB=projects/credible-picks/locations/europe-west1/jobs/credible-recs-reader` in its settings
   (`gcloud run deploy credible-recs --source <bundle> ...`).
4. The job, on the image the site now runs (create or update), allowed to read the Bright Data key (when its secret
   isn't there: no grant, `CREDIBLE_RECS_PRECHECK_BRIGHT_DATA=off` and `--clear-secrets` instead of `--set-secrets`):

       gcloud secrets add-iam-policy-binding bright-data-key --project credible-picks \
           --member serviceAccount:RUNNER --role roles/secretmanager.secretAccessor
       IMAGE=$(gcloud run services describe credible-recs --region europe-west1 --project credible-picks \
           --format='value(spec.template.spec.containers[0].image)')
       gcloud run jobs deploy credible-recs-precheck --project credible-picks --region europe-west1 --image "$IMAGE" \
           --command python --args=-m,engine.precheck,--limit,2000,--minutes,75 \
           --tasks 1 --max-retries 0 --task-timeout 2h --memory 1536Mi --cpu 1 \
           --set-env-vars CREDIBLE_RECS_LIVE_CACHE_BUCKET=credible-picks-live-checks,CREDIBLE_RECS_ON_DEMAND_BUCKET=credible-picks-on-demand,CREDIBLE_RECS_PRECHECK_BRIGHT_DATA=on \
           --set-secrets BRIGHT_DATA_API_KEY=bright-data-key:latest
       gcloud run jobs add-iam-policy-binding credible-recs-precheck --project credible-picks --region europe-west1 \
           --member serviceAccount:RUNNER --role roles/run.invoker

   and the reading job on the same image (deploy/cloudrun/on_demand.sh), allowed to read the Gemini key, and startable
   by the account the site runs as:

       gcloud secrets add-iam-policy-binding gemini-key --project credible-picks \
           --member serviceAccount:RUNNER --role roles/secretmanager.secretAccessor
       gcloud run jobs deploy credible-recs-reader --project credible-picks --region europe-west1 --image "$IMAGE" \
           --command python --args=-m,engine.on_demand,run \
           --tasks 1 --max-retries 0 --task-timeout 45m --memory 1Gi --cpu 1 \
           --set-env-vars CREDIBLE_RECS_ON_DEMAND_BUCKET=credible-picks-on-demand,CREDIBLE_RECS_QUERY_MODEL=off \
           --set-secrets GEM_API_KEY=gemini-key:latest
       gcloud run jobs add-iam-policy-binding credible-recs-reader --project credible-picks --region europe-west1 \
           --member serviceAccount:RUNNER --role roles/run.invoker

5. The schedule (`create` the first time, `update` after):

       gcloud scheduler jobs create http credible-recs-precheck-daily --project credible-picks --location europe-west1 \
           --schedule "0 4 * * *" --time-zone "Europe/London" --http-method POST \
           --uri https://europe-west1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/credible-picks/jobs/credible-recs-precheck:run \
           --oauth-service-account-email RUNNER

6. Once the site runs the new image, the on-demand bucket lets go of the threads it now holds (written only over the
   version read, so a thread the job adds meanwhile stays):

       CREDIBLE_RECS_ON_DEMAND_BUCKET=credible-picks-on-demand .venv/bin/python -m engine.library forget-baked

To run the pre-check at once (the first time, say) instead of waiting for 4 am:

    gcloud run jobs execute credible-recs-precheck --region europe-west1 --project credible-picks

and to see its report: `gcloud run jobs executions list --job credible-recs-precheck --region europe-west1` then the
execution's logs in the console (Cloud Run, Jobs, credible-recs-precheck, Logs).

Reddit's limit is per address. The job and the site usually leave Google from different addresses, but not always: the
job runs at 4 am, when the site is quietest, and at its pace leaves about 50 of every 200 reads in 10 minutes free.

## On-demand reading

Since 14 Oct 2026 (Noemi: "I want recs regardless of the category"; the plan's part 3). A request module 1 understands,
about a product the library holds fewer than 6 extracted threads about, is queued, and the answer says so in the
page's words, for example "We haven't read Reddit about teapots yet, so we've started: check back in about 20 minutes."
(15 more minutes for each request ahead of it; "taking longer than usual" after 90 minutes; and when the free
allowance is used up, when it is back). That answer isn't remembered: the next ask works it out again. The site starts
the reading job at once, and at every keep-warm ping while a request waits it asks the bundle's version (one small
read, a download only when it changed), takes the new threads into its library folder and answers with them, every
quote shown checked live on Reddit as always. The daily pre-check takes them in too and checks their answers ahead.

To see the queue (on Noemi's computer, through gcloud's sign-in; counts and product types only):

    .venv/bin/python -m engine.on_demand status

To run the job by hand (it does nothing when no request waits): `gcloud run jobs execute credible-recs-reader --region
europe-west1 --project credible-picks`; its report (counts and product types, never a comment's words) is in its logs
(Cloud Run, Jobs, credible-recs-reader, Logs).

The job's limits, all in engine/config.py ("On-demand reading"): it starts no new reading after 15 minutes of a run and
stops at 45; its runs read for at most 50,000 seconds a month (then the queue rests until the 1st); it makes at most 100
Gemini calls a day of the free allowance, leaving the rest to Noemi's own bulk reading, and none more that day after
Gemini's daily 429 (until 8 am UTC, when the allowance is surely back); at most 20 requests wait at once (10 until
14 Oct 2026: with the general category most requests queue; 20 is about two days of the job's reading, and the
sums below don't change, since the job's time and Gemini calls have caps of their own); a request
whose archive search fails is tried again an hour later and set aside for a day after 3 tries; a product read once is
read again only after 30 days, if its library is still thin then.

## The Gemini key

The reading job reads the key from the environment (GEM_API_KEY), which Cloud Run fills from the Secret Manager secret
`gemini-key`. Noemi creates it once, from the repository's root on her computer, with the key taken from her .env by
the project's own reader and handed straight to gcloud, never shown on screen or kept anywhere else (in Belgium, like
the rest):

    .venv/bin/python -c "import sys; from pathlib import Path; from engine.parse_reddit import _read_env_file; sys.stdout.write(_read_env_file(Path('.env'))['GEM_API_KEY'])" | gcloud secrets create gemini-key --project credible-picks --replication-policy user-managed --locations europe-west1 --data-file=-

When the key changes: the same command with `gcloud secrets versions add gemini-key --project credible-picks
--data-file=-` after the pipe. deploy.sh never makes or reads it: it only checks it is there, and leaves on-demand reading
off for that deploy when it isn't (14 Oct 2026: a missing key must not stop the site's own deploys). Free use only: Noemi's key is on Gemini's free tier, and under Google's terms UK users' free use
gets the paid-tier data terms (not used for training).

## The Bright Data key

The pre-check reads the key from the environment (BRIGHT_DATA_API_KEY), which Cloud Run fills from the Secret Manager
secret `bright-data-key`. The secret exists: it was created on 14 Oct 2026, with Noemi's go-ahead, with the command
below (version 1, in Belgium like the rest), the key taken from her .env by the project's own reader and handed
straight to gcloud, never shown on screen or kept anywhere else. To create it again (if it were ever deleted), from
the repository's root on her computer:

    .venv/bin/python -c "import sys; from pathlib import Path; from engine.parse_reddit import _read_env_file; sys.stdout.write(_read_env_file(Path('.env'))['BRIGHT_DATA_API_KEY'])" | gcloud secrets create bright-data-key --project credible-picks --replication-policy user-managed --locations europe-west1 --data-file=-

When the key changes: the same command with `gcloud secrets versions add bright-data-key --project credible-picks
--data-file=-` after the pipe. deploy.sh never makes or reads it: it only checks it is there, and when it isn't, it
deploys the job with its Bright Data verification off (`CREDIBLE_RECS_PRECHECK_BRIGHT_DATA=off`, no secret given to the
job, no access granted) and says so in one line (14 Oct 2026: a missing key never stops a deploy); each run's report
then says the step is off. Secret Manager's free tier covers it (6 secret versions and 10,000 reads a month: the job
reads it once a run).

## Keeping it awake

A server that has slept takes about a minute to get ready (engine/web.py's warm_up: 65 s on 13 Oct 2026), and Cloud
Run sends it visitors only once its /ready says so (deploy.sh's startup probe). So a Cloud Scheduler job asks /ready
every 5 minutes, and a visitor never waits for one to start. It was set up once (13 Oct 2026) with:

    gcloud services enable cloudscheduler.googleapis.com --project credible-picks
    gcloud scheduler jobs create http credible-recs-keep-warm --project credible-picks --location europe-west1 \
        --schedule "*/5 * * * *" --time-zone "Europe/London" --http-method GET --attempt-deadline 300s \
        --uri "https://credible-recs-446702383157.europe-west1.run.app/ready"

`gcloud scheduler jobs pause credible-recs-keep-warm --location europe-west1` stops it.

## Costs

The free tier covers our traffic (Cloud Run: 180,000 vCPU-seconds, 360,000 GiB-seconds and 2 million requests a
month). The image is about 1.5 GB in Artifact Registry, whose free storage is 0.5 GB: about 0.10 EUR a month for the
rest. Cloud Scheduler's first 3 jobs are free; a ping is one short request, and a server between requests costs
nothing. The budget alert emails Noemi at 50% and 100% of 1 EUR.

The pre-check (estimates, 13 Oct 2026; the time limit 14 Oct 2026). A job is billed per instance-second for its whole run, sleeping between reads
included, so it runs with the least that works: 1 vCPU (a job's minimum) and 1.5 GiB (on Noemi's computer it peaked at
1.3 GB with module 1's open model loaded; 0.2 GB without it, but without the model the open model's product types, such
as air fryers, would not be checked ahead). A run is at most about 87 minutes (no read starts 75 minutes after the
run started, working out the answers included; the last may wait up to 11 for Reddit's next 10 minutes; a minute to
save), 5,220 seconds a day, 161,820 in a 31-day month: 161,820 vCPU-seconds and 242,730 GiB-seconds, 67% and 54% of the
free tier for instance-billed work (240,000 vCPU-seconds and 450,000 GiB-seconds a month; the site itself is billed by
request, under its own free tier). So 0 EUR. engine/tests/test_cloudrun.py does these sums from deploy.sh's own
settings. If a run's log says the memory limit was exceeded, 2 GiB (`--memory 2Gi`) is still inside the free tier:
323,640 GiB-seconds, 72%. The schedule is
the second of Cloud Scheduler's 3 free jobs (the keep-warm ping is the first).

On-demand reading (estimates, 14 Oct 2026; 0 EUR). The reading job is billed like the pre-check, per instance-second
for its whole run, waiting included, on 1 vCPU and 1 GiB. One product takes about 12 minutes: about 6 minutes of
Arctic Shift at its 10 s pace (20 title searches and about 15 reads for a kitchen type with no title words of its own,
fewer for most), about 5 for Gemini (about 9 calls for 6 threads read in parts of 40 comments, each paced 6 s apart),
and half a minute to start. Its runs are capped at 50,000 s a month (about 70 products), so the worst month is 50,000
vCPU-seconds and 50,000 GiB-seconds; with the pre-check's 161,820 and 242,730, 211,820 of the free 240,000
vCPU-seconds (88%) and 292,730 of the free 450,000 GiB-seconds (65%). There are no empty runs: nothing is scheduled,
the job runs only when a request waits. Cloud Scheduler: no new job (the site starts the reading job, and the keep-warm
ping starts it again when a start failed), so still 2 of the 3 free jobs. Gemini: free tier only, at most 100 calls a
day by the job (about 10 products), stopping at Gemini's own daily limit. Secret Manager: a third secret (gemini-key,
with hf-token and bright-data-key), inside the free 6 secret versions, and the job reads it once a run (free: 10,000
reads a month). Arctic Shift: free, at its own pace. Starting a job (Cloud Run's Admin API): free. Sending threads to
Gemini is the only traffic out of Google: about 0.25 MB a product, about 17 MB in a capped month, about 0.002 USD.
The on-demand bucket, effectively nothing, like the live checks': Class A (writes), the site's 1 a queued request and
the job's about 20 a product (the queue's lease, usage and states, the bundle after each thread: 11 for 3 threads in
the tests), about 1,500 in a capped month, 0.008 USD; Class B (reads), the job's about 120 a product (it reads the
queue and the bundle afresh before every change: 63 for 3 threads in the tests), the site's hourly question about the
bundle's version (about 720 a month) and its every-5-minutes questions while a request waits (about 18 a product), the
pre-check's few a run, about 10,500 in all, 0.004 USD; storage: only threads not baked in yet (about 35 KB each with
its extraction, at most 300 threads, about 10 MB, 0.0002 USD a month). Under 0.02 USD a month in all.

Bright Data (estimates, 13 Oct 2026; no money: the free tier is 5,000 records a month, and past it jobs simply stop).
Reading a thread costs a record for its post and one for each top-level comment: 22 for the median thread the answers
quote, 63 at the 90th percentile. The pre-check reads at most 30 records a run (PRECHECK_BRIGHT_DATA_RECORDS), so at most
930 a month, under a fifth of the free records, leaving the rest to the library's own reads (3,972 were used in October
by the 13th). That is about one thread a day: at 1 comment in 8, the answers' 1,288 comments hold about 161 the embed
page can't show, in about 105 threads, and the shown ones alone about 89 in 68 threads (about 3,000 records). So the
threads verifying the most shown comments for their records go first, a comment verified that way lasts 48 hours and is
read again only every other run, and covering them all would need far more records than the free tier has: Noemi's
call.

The bucket (estimates, 13 Oct 2026), effectively nothing: Cloud Storage's free tier is for US regions only, so every
operation is billed, but there are very few. Class A (writes): the pre-check's 2 a run, about 60 a month, 0.0003 USD
at 0.005 USD per 1,000. Class B (reads): the site's hourly question about the bundle's version, about 720 a month,
plus a download each time it changed (up to 2 a day) and the pre-check's own 2 a run, about 900 a month in all, 0.0004
USD at 0.0004 USD per 1,000. Storage: one object of about 0.6 MB, 0.00001 USD a month. Reading it from Cloud Run in the
same region is free. Under 0.001 USD a month in all; with the image's storage, about 0.10 EUR a month, under the 1 EUR
alert.
