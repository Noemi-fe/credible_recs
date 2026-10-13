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
  `python -m engine.precheck --limit 1100`, started by Cloud Scheduler (`credible-recs-precheck-daily`) at 4 am UK time.
  It reads at the live check's pace (40 at once, then one every 4 s): 1,100 reads take about 71 minutes, plus a few
  minutes working out the answers. Its report (counts and times, never a comment's words) is in the job's logs. On
  Noemi's computer on 13 Oct 2026 a run worked out 1,145 comments in 3.7 minutes and read 928 of them in 59 minutes
  (872 passing, 2 deleted, 8 edited, 46 pages that couldn't be read).
  Then, for the comments whose embed page shows no comment ("Not supported comment", about 1 in 8; Noemi, 13 Oct 2026:
  "Use Bright Data"), it reads their threads through Bright Data, within 30 records a run (the most useful threads
  first), and saves a check for each comment it finds there. It needs the Bright Data key, the Secret Manager secret
  `bright-data-key` (below). The site never calls Bright Data.
- **Feedback**: Noemi's private Hugging Face dataset Noemix/credible-recs-feedback. The site uploads it in batches with
  the token stored as the Secret Manager secret `hf-token`.
- **Visit counts**: GoatCounter, site code noemix (CREDIBLE_RECS_GOATCOUNTER).
- **Settings** the site reads: CREDIBLE_RECS_ALLOWED_HOSTS (the site's own addresses), CREDIBLE_RECS_GOATCOUNTER,
  CREDIBLE_RECS_FEEDBACK_REPO, CREDIBLE_RECS_LIVE_CACHE_BUCKET; the secret HF_TOKEN. The job reads
  CREDIBLE_RECS_LIVE_CACHE_BUCKET only.

## Updating the site

After committing (and after new threads are extracted), from the repository's root:

    sh deploy/cloudrun/deploy.sh

It makes sure the bucket exists with its rules, bundles the current commit with the library, builds the private image
and deploys the site, then points the pre-check job at the same image and makes sure its daily schedule exists, and
prints the address. Safe to run again: each step creates what is missing and sets again what is there.

### The commands it runs, in order

The project number is `NUMBER` below (`gcloud projects describe credible-picks --format='value(projectNumber)'`), and
`RUNNER` is the account the site and the job run as, `NUMBER-compute@developer.gserviceaccount.com`.

0. Noemi's Bright Data key as a secret, once, by Noemi herself (see "The Bright Data key" below). deploy.sh stops
   before building anything if it isn't there, and never makes or reads it.
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

3. The site, as before, with `CREDIBLE_RECS_LIVE_CACHE_BUCKET=credible-picks-live-checks` added to its settings
   (`gcloud run deploy credible-recs --source <bundle> ...`).
4. The job, on the image the site now runs (create or update), allowed to read the Bright Data key:

       gcloud secrets add-iam-policy-binding bright-data-key --project credible-picks \
           --member serviceAccount:RUNNER --role roles/secretmanager.secretAccessor
       IMAGE=$(gcloud run services describe credible-recs --region europe-west1 --project credible-picks \
           --format='value(spec.template.spec.containers[0].image)')
       gcloud run jobs deploy credible-recs-precheck --project credible-picks --region europe-west1 --image "$IMAGE" \
           --command python --args=-m,engine.precheck,--limit,1100 \
           --tasks 1 --max-retries 0 --task-timeout 2h --memory 1536Mi --cpu 1 \
           --set-env-vars CREDIBLE_RECS_LIVE_CACHE_BUCKET=credible-picks-live-checks \
           --set-secrets BRIGHT_DATA_API_KEY=bright-data-key:latest
       gcloud run jobs add-iam-policy-binding credible-recs-precheck --project credible-picks --region europe-west1 \
           --member serviceAccount:RUNNER --role roles/run.invoker

5. The schedule (`create` the first time, `update` after):

       gcloud scheduler jobs create http credible-recs-precheck-daily --project credible-picks --location europe-west1 \
           --schedule "0 4 * * *" --time-zone "Europe/London" --http-method POST \
           --uri https://europe-west1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/credible-picks/jobs/credible-recs-precheck:run \
           --oauth-service-account-email RUNNER

To run the pre-check at once (the first time, say) instead of waiting for 4 am:

    gcloud run jobs execute credible-recs-precheck --region europe-west1 --project credible-picks

and to see its report: `gcloud run jobs executions list --job credible-recs-precheck --region europe-west1` then the
execution's logs in the console (Cloud Run, Jobs, credible-recs-precheck, Logs).

Reddit's limit is per address. The job and the site usually leave Google from different addresses, but not always: the
job runs at 4 am, when the site is quietest, and at its pace leaves about 50 of every 200 reads in 10 minutes free.

## The Bright Data key

The pre-check reads the key from the environment (BRIGHT_DATA_API_KEY), which Cloud Run fills from the Secret Manager
secret `bright-data-key`. Noemi creates it once, from the repository's root on her computer, with the key taken from
her .env and handed straight to gcloud, never shown on screen or kept anywhere else (in Belgium, like the rest):

    .venv/bin/python -c "import sys; from pathlib import Path; from engine.parse_reddit import _read_env_file; sys.stdout.write(_read_env_file(Path('.env'))['BRIGHT_DATA_API_KEY'])" | gcloud secrets create bright-data-key --project credible-picks --replication-policy user-managed --locations europe-west1 --data-file=-

When the key changes: the same command with `gcloud secrets versions add bright-data-key --project credible-picks
--data-file=-` after the pipe. Secret Manager's free tier covers it (6 secret versions and 10,000 reads a month: the job
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

The pre-check (estimates, 13 Oct 2026). A job is billed per instance-second for its whole run, sleeping between reads
included, so it runs with the least that works: 1 vCPU (a job's minimum) and 1.5 GiB (on Noemi's computer it peaked at
1.3 GB with module 1's open model loaded; 0.2 GB without it, but without the model the open model's product types, such
as air fryers, would not be checked ahead). A run is at most about 80 minutes (5 to work out the answers on one
processor, 71 to read 1,100 comments), about 4,800 seconds a day, 144,000 a month: 144,000 vCPU-seconds and 216,000
GiB-seconds, 60% and 48% of the free tier for instance-billed work (240,000 vCPU-seconds and 450,000 GiB-seconds a
month; the site itself is billed by request, under its own free tier). So 0 EUR. If the first run's log says the memory
limit was exceeded, 2 GiB (`--memory 2Gi`) is still inside the free tier: 288,000 GiB-seconds, 64%. The schedule is
the second of Cloud Scheduler's 3 free jobs (the keep-warm ping is the first).

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
