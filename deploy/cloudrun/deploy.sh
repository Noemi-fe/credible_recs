#!/bin/sh
# Builds and deploys the site to Google Cloud Run in Noemi's project (deploy/cloudrun/DEPLOY.md), with the daily
# pre-check of the quotes answers show (engine/precheck.py, Noemi's decision of 13 Oct 2026: "check ahead") as a Cloud
# Run job on the same image, and the private bucket it shares its checks with the site through (one object, written
# by the job twice a run, read by the site at most hourly). Run from the repository's root after committing:
#     sh deploy/cloudrun/deploy.sh
# It bundles the current commit with the saved library (deploy/cloudrun/make_context.py), has Cloud Build turn it into
# a private image, and deploys it: public site, one server at most, none when idle (the free tier). A new server gets
# visitors only once its /ready says it has got ready (up to 4 minutes; engine/web.py's warm_up), so a deploy never
# makes visitors wait on one getting ready: they stay with the server before it until then.
# Since 14 Oct 2026 also on-demand reading (Noemi's plan, part 3; deploy/cloudrun/on_demand.sh): its private bucket,
# its reading job on the same image (started by the site, no schedule of its own), and the threads it has read baked
# into the image first (pull-bucket), then let go of by the bucket once the site runs it (forget-baked). It needs the
# Gemini key's secret, gemini-key, which Noemi creates herself (DEPLOY.md): without it the script stops at once.
# Safe to run again: each step creates what is missing and sets again what is there.
set -eu
PROJECT="${CREDIBLE_RECS_GCP_PROJECT:-credible-picks}"
REGION="${CREDIBLE_RECS_GCP_REGION:-europe-west1}"
SERVICE="${CREDIBLE_RECS_GCP_SERVICE:-credible-recs}"
JOB="${CREDIBLE_RECS_GCP_JOB:-credible-recs-precheck}"
SCHEDULE="${JOB}-daily"
BUCKET="${CREDIBLE_RECS_LIVE_CACHE_BUCKET:-credible-picks-live-checks}"
PRECHECK_LIMIT="${CREDIBLE_RECS_PRECHECK_LIMIT:-1100}"
GCLOUD="${GCLOUD:-gcloud}"

NUMBER="$($GCLOUD projects describe "$PROJECT" --format='value(projectNumber)')"
RUNNER="${NUMBER}-compute@developer.gserviceaccount.com"  # the account the site and the job run as (the default)
. deploy/cloudrun/on_demand.sh  # on-demand reading's steps (ON_DEMAND_BUCKET, READER_JOB, READER_JOB_NAME)
on_demand_secret  # stops here, before anything is built, when the Gemini key's secret isn't there yet
HOSTS="${SERVICE}-${NUMBER}.${REGION}.run.app"
# The service's older-style address too, once it exists.
OLD="$($GCLOUD run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" --format='value(status.url)' 2>/dev/null || true)"
if [ -n "$OLD" ]; then HOSTS="$HOSTS,${OLD#https://}"; fi

# 1. The APIs the jobs, the schedule and the Gemini key need (nothing happens when they are on already).
$GCLOUD services enable storage.googleapis.com cloudscheduler.googleapis.com secretmanager.googleapis.com \
    --project "$PROJECT"

# 2. The live checks' bucket: private (uniform access, public access prevented), in the site's region, every object
#    deleted once 2 days old, and nothing kept after a deletion (no soft delete).
if ! $GCLOUD storage buckets describe "gs://$BUCKET" --project "$PROJECT" >/dev/null 2>&1; then
    $GCLOUD storage buckets create "gs://$BUCKET" --project "$PROJECT" --location "$REGION" \
        --uniform-bucket-level-access --public-access-prevention --soft-delete-duration 0 \
        --lifecycle-file deploy/cloudrun/live_cache_lifecycle.json
fi
$GCLOUD storage buckets update "gs://$BUCKET" --project "$PROJECT" --public-access-prevention --clear-soft-delete \
    --lifecycle-file deploy/cloudrun/live_cache_lifecycle.json
$GCLOUD storage buckets add-iam-policy-binding "gs://$BUCKET" --project "$PROJECT" \
    --member "serviceAccount:$RUNNER" --role roles/storage.objectUser >/dev/null
#    And on-demand reading's bucket (on_demand.sh): the queue and the threads read on demand, deleted at 37 days.
on_demand_bucket

# 3. The site: public, one server at most, none when idle (the free tier). First the threads read on demand come into
#    data/library (through gcloud's sign-in), so the image holds them; when that fails they stay in the bucket, where
#    the site finds them as it gets ready.
CREDIBLE_RECS_ON_DEMAND_BUCKET="$ON_DEMAND_BUCKET" GCLOUD="$GCLOUD" .venv/bin/python -m engine.library pull-bucket \
    || echo "The threads read on demand weren't pulled: the site still loads them from the bucket." >&2
BUNDLE="$(mktemp -d)/bundle"
.venv/bin/python -m deploy.cloudrun.make_context "$BUNDLE"
$GCLOUD run deploy "$SERVICE" --project "$PROJECT" --region "$REGION" --source "$BUNDLE" \
    --allow-unauthenticated --memory 2Gi --cpu 1 --cpu-boost --max-instances 1 --min-instances 0 \
    --concurrency 8 --timeout 300 \
    --startup-probe "httpGet.path=/ready,httpGet.port=8080,periodSeconds=3,timeoutSeconds=2,failureThreshold=80" \
    --set-env-vars "^;^CREDIBLE_RECS_ALLOWED_HOSTS=${HOSTS};CREDIBLE_RECS_GOATCOUNTER=noemix;CREDIBLE_RECS_FEEDBACK_REPO=Noemix/credible-recs-feedback;CREDIBLE_RECS_LIVE_CACHE_BUCKET=${BUCKET};CREDIBLE_RECS_ON_DEMAND_BUCKET=${ON_DEMAND_BUCKET};CREDIBLE_RECS_ON_DEMAND_JOB=${READER_JOB_NAME}" \
    --set-secrets "HF_TOKEN=hf-token:latest" --quiet
rm -rf "$(dirname "$BUNDLE")"

# 4. The pre-check: a Cloud Run job on the image just deployed, reading at most PRECHECK_LIMIT comments a run (at the
#    live check's pace, about 71 minutes for 1,100), never retried the same day. Billed for its whole run, sleeping
#    included, so it gets the least that works: 1 vCPU (a job's minimum) and 1.5 GiB (it peaked at 1.3 GB with the
#    open model loaded, 13 Oct 2026; 0.2 GB without it).
IMAGE="$($GCLOUD run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" --format='value(spec.template.spec.containers[0].image)')"
$GCLOUD run jobs deploy "$JOB" --project "$PROJECT" --region "$REGION" --image "$IMAGE" \
    --command python --args=-m,engine.precheck,--limit,${PRECHECK_LIMIT} \
    --tasks 1 --max-retries 0 --task-timeout 2h --memory 1536Mi --cpu 1 \
    --set-env-vars "CREDIBLE_RECS_LIVE_CACHE_BUCKET=${BUCKET},CREDIBLE_RECS_ON_DEMAND_BUCKET=${ON_DEMAND_BUCKET}" --quiet
$GCLOUD run jobs add-iam-policy-binding "$JOB" --project "$PROJECT" --region "$REGION" \
    --member "serviceAccount:$RUNNER" --role roles/run.invoker >/dev/null
#    And on-demand reading's job on the same image (on_demand.sh), which the site may start.
on_demand_job

# 5. Once a day at 4 am UK time, when the site is quietest, Cloud Scheduler starts the job.
if $GCLOUD scheduler jobs describe "$SCHEDULE" --project "$PROJECT" --location "$REGION" >/dev/null 2>&1; then
    VERB=update
else
    VERB=create
fi
$GCLOUD scheduler jobs "$VERB" http "$SCHEDULE" --project "$PROJECT" --location "$REGION" \
    --schedule "0 4 * * *" --time-zone "Europe/London" --http-method POST \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${JOB}:run" \
    --oauth-service-account-email "$RUNNER" --quiet

# 6. The site runs the new image: the bucket lets go of the threads read on demand that it now holds.
CREDIBLE_RECS_ON_DEMAND_BUCKET="$ON_DEMAND_BUCKET" GCLOUD="$GCLOUD" .venv/bin/python -m engine.library forget-baked \
    || echo "The bucket kept the threads read on demand: the next deploy lets them go." >&2

$GCLOUD run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" --format='value(status.url)'
