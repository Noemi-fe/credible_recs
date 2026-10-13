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
HOSTS="${SERVICE}-${NUMBER}.${REGION}.run.app"
# The service's older-style address too, once it exists.
OLD="$($GCLOUD run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" --format='value(status.url)' 2>/dev/null || true)"
if [ -n "$OLD" ]; then HOSTS="$HOSTS,${OLD#https://}"; fi

# 1. The APIs the job and its schedule need (nothing happens when they are on already).
$GCLOUD services enable storage.googleapis.com cloudscheduler.googleapis.com --project "$PROJECT"

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

# 3. The library as the daily pre-check last verified it (Noemi, 13 Oct 2026: "Keep only comments we use"). The job
#    reads each comment the slimmed threads keep on Reddit's embed page and records each read (when, and what it said:
#    ids, dates and outcomes, no words) in the bucket's live_check/verified.json. Applied here, before bundling, so the
#    image built next reflects it: each passing comment gets its date, and one found deleted or edited, or not verified
#    within 30 days, loses its words and its mentions (engine/verify.py). With no record yet, this machine's checks of
#    the last 48 hours and the 30-day deadline are applied alone.
RECORD="$(mktemp -d)/verified.json"
if $GCLOUD storage cp "gs://$BUCKET/live_check/verified.json" "$RECORD" --project "$PROJECT" --quiet 2>/dev/null; then
    .venv/bin/python -m engine.library apply-checks --ledger "$RECORD"
else
    echo "No verification record in gs://$BUCKET yet (the pre-check hasn't run): this machine's checks only." >&2
    .venv/bin/python -m engine.library apply-checks
fi
rm -rf "$(dirname "$RECORD")"

# 4. The site: public, one server at most, none when idle (the free tier).
BUNDLE="$(mktemp -d)/bundle"
.venv/bin/python -m deploy.cloudrun.make_context "$BUNDLE"
$GCLOUD run deploy "$SERVICE" --project "$PROJECT" --region "$REGION" --source "$BUNDLE" \
    --allow-unauthenticated --memory 2Gi --cpu 1 --cpu-boost --max-instances 1 --min-instances 0 \
    --concurrency 8 --timeout 300 \
    --startup-probe "httpGet.path=/ready,httpGet.port=8080,periodSeconds=3,timeoutSeconds=2,failureThreshold=80" \
    --set-env-vars "^;^CREDIBLE_RECS_ALLOWED_HOSTS=${HOSTS};CREDIBLE_RECS_GOATCOUNTER=noemix;CREDIBLE_RECS_FEEDBACK_REPO=Noemix/credible-recs-feedback;CREDIBLE_RECS_LIVE_CACHE_BUCKET=${BUCKET}" \
    --set-secrets "HF_TOKEN=hf-token:latest" --quiet
rm -rf "$(dirname "$BUNDLE")"

# 5. The pre-check: a Cloud Run job on the image just deployed, reading at most PRECHECK_LIMIT comments a run (at the
#    live check's pace, about 71 minutes for 1,100), then up to LIBRARY_VERIFY_READS (400) of the slimmed threads' kept
#    comments verified longest ago (about 26 minutes more), never retried the same day. Billed for its whole run,
#    sleeping included, so it gets the least that works: 1 vCPU (a job's minimum) and 1.5 GiB (it peaked at 1.3 GB with
#    the open model loaded, 13 Oct 2026; 0.2 GB without it). 3 hours at most, so even at the slowest pace (one read every
#    4 s) both parts fit; a run is billed for the time it takes, not for its limit.
IMAGE="$($GCLOUD run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" --format='value(spec.template.spec.containers[0].image)')"
$GCLOUD run jobs deploy "$JOB" --project "$PROJECT" --region "$REGION" --image "$IMAGE" \
    --command python --args=-m,engine.precheck,--limit,${PRECHECK_LIMIT} \
    --tasks 1 --max-retries 0 --task-timeout 3h --memory 1536Mi --cpu 1 \
    --set-env-vars "CREDIBLE_RECS_LIVE_CACHE_BUCKET=${BUCKET}" --quiet
$GCLOUD run jobs add-iam-policy-binding "$JOB" --project "$PROJECT" --region "$REGION" \
    --member "serviceAccount:$RUNNER" --role roles/run.invoker >/dev/null

# 6. Once a day at 4 am UK time, when the site is quietest, Cloud Scheduler starts the job.
if $GCLOUD scheduler jobs describe "$SCHEDULE" --project "$PROJECT" --location "$REGION" >/dev/null 2>&1; then
    VERB=update
else
    VERB=create
fi
$GCLOUD scheduler jobs "$VERB" http "$SCHEDULE" --project "$PROJECT" --location "$REGION" \
    --schedule "0 4 * * *" --time-zone "Europe/London" --http-method POST \
    --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/${JOB}:run" \
    --oauth-service-account-email "$RUNNER" --quiet

$GCLOUD run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" --format='value(status.url)'
