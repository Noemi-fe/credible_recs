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
- **The live checks' bucket** (`credible-picks-live-checks`, CREDIBLE_RECS_LIVE_CACHE_BUCKET): what Reddit's embed page
  said about each comment checked (its text and when it was read, nothing else), kept so the site, whose disk is wiped
  whenever it sleeps, and the pre-check, which runs on a machine of its own, share it. Private: uniform bucket-level
  access, public access prevention, readable only by the project's compute service account. In europe-west1. Every
  object is deleted once it is 2 days old (deploy/cloudrun/live_cache_lifecycle.json; Google runs these deletions
  about once a day, so one can stay up to a day longer, unused), and soft delete is off, so nothing deleted is kept.
  The code never uses an entry older than 48 hours either way.
- **The pre-check** (Cloud Run job `credible-recs-precheck`): the site's own image, running
  `python -m engine.precheck --limit 1300`, started by Cloud Scheduler (`credible-recs-precheck-daily`) at 4 am UK time.
  It reads at the live check's pace (40 at once, then one every 4 s): 1,300 reads take about 85 minutes, plus a few
  minutes working out the answers. Its report (counts and times, never a comment's words) is in the job's logs.
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

1. The APIs: `gcloud services enable storage.googleapis.com cloudscheduler.googleapis.com --project credible-picks`
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
4. The job, on the image the site now runs (create or update):

       IMAGE=$(gcloud run services describe credible-recs --region europe-west1 --project credible-picks \
           --format='value(spec.template.spec.containers[0].image)')
       gcloud run jobs deploy credible-recs-precheck --project credible-picks --region europe-west1 --image "$IMAGE" \
           --command python --args=-m,engine.precheck,--limit,1300 \
           --tasks 1 --max-retries 0 --task-timeout 3h --memory 2Gi --cpu 1 \
           --set-env-vars CREDIBLE_RECS_LIVE_CACHE_BUCKET=credible-picks-live-checks
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

## Costs

The free tier covers our traffic (Cloud Run: 180,000 vCPU-seconds, 360,000 GiB-seconds and 2 million requests a
month). The image is about 1.5 GB in Artifact Registry, whose free storage is 0.5 GB: about 0.10 EUR a month for the
rest. The budget alert emails Noemi at 50% and 100% of 1 EUR.

The pre-check (estimates, 13 Oct 2026): jobs have a free tier of their own, 240,000 vCPU-seconds and 450,000
GiB-seconds a month; a 90-minute run a day with 1 vCPU and 2 GiB uses about 162,000 and 324,000 of them. Cloud
Scheduler gives 3 schedules free. The bucket is tiny (a few MB), but Cloud Storage's free operations are for US regions
only: about 1,300 writes a day are about 40,000 a month, about 0.20 EUR at 0.005 USD per 1,000; reads cost almost
nothing. So about 0.30 EUR a month in all, under the 1 EUR alert.
