#!/bin/sh
# Builds and deploys the site to Google Cloud Run in Noemi's project (deploy/cloudrun/DEPLOY.md), with the daily
# pre-check of the quotes answers show (engine/precheck.py, Noemi's decision of 13 Oct 2026: "check ahead") as a Cloud
# Run job on the same image, and the private bucket the job and the site share through. Since 14 Oct 2026 (the
# free-tier redesign) the job works out what to read and leaves the site a plan there (live_check/plan.json, daily);
# the site reads ahead at Cloud Scheduler's keep-warm ping (engine/read_ahead.py) and writes what it read to the
# bucket's bundle (live_check/bundle.json, at most hourly). Run from the repository's root after committing:
#     sh deploy/cloudrun/deploy.sh
# It bundles the current commit with the saved library (deploy/cloudrun/make_context.py), has Cloud Build turn it into
# a private image, and deploys it: public site, one server at most, none when idle (the free tier). A new server gets
# visitors only once its /ready says it has got ready (up to 4 minutes; engine/web.py's warm_up), so a deploy never
# makes visitors wait on one getting ready: they stay with the server before it until then.
# Since 14 Oct 2026 also on-demand reading (Noemi's plan, part 3; deploy/cloudrun/on_demand.sh): its private bucket,
# its reading job on the same image (started by the site, no schedule of its own), and the threads it has read baked
# into the image first (pull-bucket), then let go of by the bucket once the site runs it (forget-baked). It needs the
# Gemini key's secret, gemini-key, which Noemi creates herself (DEPLOY.md): without it on-demand reading stays off.
# Safe to run again: each step creates what is missing and sets again what is there.
set -eu
PROJECT="${CREDIBLE_RECS_GCP_PROJECT:-credible-picks}"
REGION="${CREDIBLE_RECS_GCP_REGION:-europe-west1}"
SERVICE="${CREDIBLE_RECS_GCP_SERVICE:-credible-recs}"
JOB="${CREDIBLE_RECS_GCP_JOB:-credible-recs-precheck}"
SCHEDULE="${JOB}-daily"
BUCKET="${CREDIBLE_RECS_LIVE_CACHE_BUCKET:-credible-picks-live-checks}"
PRECHECK_MINUTES="${CREDIBLE_RECS_PRECHECK_MINUTES:-30}"
GCLOUD="${GCLOUD:-gcloud}"

NUMBER="$($GCLOUD projects describe "$PROJECT" --format='value(projectNumber)')"
RUNNER="${NUMBER}-compute@developer.gserviceaccount.com"  # the account the site and the job run as (the default)
. deploy/cloudrun/on_demand.sh  # on-demand reading's steps (ON_DEMAND_BUCKET, READER_JOB, READER_JOB_NAME)
on_demand_secret  # ON_DEMAND on or off: off while the Gemini key's secret isn't there yet (the site deploys anyway)
if [ "$ON_DEMAND" = on ]; then
    ON_DEMAND_SITE_VARS=";CREDIBLE_RECS_ON_DEMAND_BUCKET=${ON_DEMAND_BUCKET};CREDIBLE_RECS_ON_DEMAND_JOB=${READER_JOB_NAME}"
    ON_DEMAND_PRECHECK_VARS=",CREDIBLE_RECS_ON_DEMAND_BUCKET=${ON_DEMAND_BUCKET}"
else
    ON_DEMAND_SITE_VARS=""
    ON_DEMAND_PRECHECK_VARS=""
fi
HOSTS="${SERVICE}-${NUMBER}.${REGION}.run.app"
# The service's older-style address too, once it exists.
OLD="$($GCLOUD run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" --format='value(status.url)' 2>/dev/null || true)"
if [ -n "$OLD" ]; then HOSTS="$HOSTS,${OLD#https://}"; fi

# The pre-check's Bright Data key (Noemi, 13 Oct 2026, "Use Bright Data": comments the embed page can't show are
# verified through Bright Data): the Secret Manager secret bright-data-key, which Noemi creates (DEPLOY.md, The Bright
# Data key; there since 14 Oct 2026). This script never makes or reads it. Were it missing, the job would deploy with
# that verification off (PRECHECK_BRIGHT_DATA, which the job reads as CREDIBLE_RECS_PRECHECK_BRIGHT_DATA, and no secret
# given to it), and one line says so: a missing key never stops a deploy (14 Oct 2026, as on-demand reading's Gemini
# key, on_demand_secret).
precheck_secret() {
    if $GCLOUD secrets describe bright-data-key --project "$PROJECT" >/dev/null 2>&1; then
        PRECHECK_BRIGHT_DATA=on
        PRECHECK_SECRETS="--set-secrets=BRIGHT_DATA_API_KEY=bright-data-key:latest"
    else
        PRECHECK_BRIGHT_DATA=off
        PRECHECK_SECRETS="--clear-secrets"
        echo "The secret bright-data-key isn't there: the pre-check deploys with its Bright Data verification off (deploy/cloudrun/DEPLOY.md, The Bright Data key)." >&2
    fi
}
precheck_secret  # PRECHECK_BRIGHT_DATA on or off, and the job's secrets with it

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
if [ "$ON_DEMAND" = on ]; then on_demand_bucket; fi

# 3. The site: public, one server at most, none when idle (the free tier).
#    On Cloud Run's second-generation environment (14 Oct 2026, measured: getting ready warmed all 65 requests in 40.9 s
#    there, against 19 of 65 in 122 s on the first generation, whose sandbox makes the engine's many small file reads
#    slow); same price. First the threads read on demand come into
#    data/library (through gcloud's sign-in), so the image holds them; when that fails they stay in the bucket, where
#    the site finds them as it gets ready.
if [ "$ON_DEMAND" = on ]; then
    CREDIBLE_RECS_ON_DEMAND_BUCKET="$ON_DEMAND_BUCKET" GCLOUD="$GCLOUD" .venv/bin/python -m engine.library pull-bucket \
        || echo "The threads read on demand weren't pulled: the site still loads them from the bucket." >&2
fi
#    Then the library as the daily pre-check last verified it (Noemi, 13 Oct 2026: "Keep only comments we use"): the job
#    reads the comments the slimmed threads keep on Reddit's embed page and records each read (when, and what it said:
#    ids, dates and outcomes, no words) in the bucket's live_check/verified.json. Applied here, before bundling, so the
#    image built next reflects it: each passing comment gets its date, and one found deleted or edited, or not verified
#    within 30 days, loses its words and its mentions (engine/verify.py). With no record yet, this machine's checks of
#    the last 48 hours and the 30-day deadline are applied alone. A library not slimmed yet is left as it is.
#    Since 15 Oct 2026 (Noemi's decision 3: a comment found edited keeps Reddit's current text and the items still found
#    in it word for word) the site's reads of the last 48 hours come too, the bucket's live_check/bundle.json (what
#    Reddit's embed page showed of each comment read, for 48 hours at most): its text is what such a comment keeps.
#    One more call to the bucket a deploy; the copy is in the same temporary folder as the record, deleted once applied,
#    and on the way out should a step fail (it holds comments' words: never left behind).
READS_DIR="$(mktemp -d)"
trap 'rm -rf "$READS_DIR"' EXIT
RECORD="$READS_DIR/verified.json"
READS="$READS_DIR/bundle.json"
if $GCLOUD storage cp "gs://$BUCKET/live_check/bundle.json" "$READS" --project "$PROJECT" --quiet 2>/dev/null; then
    BUNDLE_READS="--bundle $READS"
else
    BUNDLE_READS=""
    echo "No bundle of the site's reads in gs://$BUCKET: a comment found edited loses its words, as before." >&2
fi
if $GCLOUD storage cp "gs://$BUCKET/live_check/verified.json" "$RECORD" --project "$PROJECT" --quiet 2>/dev/null; then
    .venv/bin/python -m engine.library apply-checks --ledger "$RECORD" $BUNDLE_READS
else
    echo "No verification record in gs://$BUCKET yet (the pre-check hasn't run): this machine's checks only." >&2
    .venv/bin/python -m engine.library apply-checks $BUNDLE_READS
fi
rm -rf "$READS_DIR"
BUNDLE="$(mktemp -d)/bundle"
.venv/bin/python -m deploy.cloudrun.make_context "$BUNDLE"
$GCLOUD run deploy "$SERVICE" --project "$PROJECT" --region "$REGION" --source "$BUNDLE" \
    --allow-unauthenticated --memory 4Gi --cpu 1 --cpu-boost --max-instances 1 --min-instances 0 \
    --execution-environment gen2 \
    --concurrency 8 --timeout 300 \
    --startup-probe "httpGet.path=/ready,httpGet.port=8080,periodSeconds=3,timeoutSeconds=2,failureThreshold=80" \
    --set-env-vars "^;^CREDIBLE_RECS_ALLOWED_HOSTS=${HOSTS};CREDIBLE_RECS_GOATCOUNTER=noemix;CREDIBLE_RECS_FEEDBACK_REPO=Noemix/credible-recs-feedback;CREDIBLE_RECS_LIVE_CACHE_BUCKET=${BUCKET}${ON_DEMAND_SITE_VARS}" \
    --set-secrets "HF_TOKEN=hf-token:latest" --quiet
rm -rf "$(dirname "$BUNDLE")"

# 4. The pre-check: a Cloud Run job on the image just deployed, `python -m engine.precheck --plan` (14 Oct 2026): it
#    reads nothing on Reddit's embed page itself, works out the plan the site reads ahead from, and verifies through
#    Bright Data the comments the embed page can't show, starting nothing PRECHECK_MINUTES after it started; 55 minutes
#    at most a run (one Bright Data job in flight may be waited for 20 minutes), never retried the same day. Billed for its whole run, so it gets the least that works: 1 vCPU (a
#    job's minimum) and 3 GiB with the open model off (15 Oct 2026: it ran out of memory at 1.5 and at 2 GiB with
#    ~2,000 threads; working out the 486 requests peaked at 2.97 GB with the model, 2.25 GB without, on Noemi's computer;
#    the rules place 484 of them, so the model isn't loaded).
#    Its one secret is the Bright Data key, which the account it runs as may read (when the secret is there).
if [ "$PRECHECK_BRIGHT_DATA" = on ]; then
    $GCLOUD secrets add-iam-policy-binding bright-data-key --project "$PROJECT" \
        --member "serviceAccount:$RUNNER" --role roles/secretmanager.secretAccessor >/dev/null
fi
IMAGE="$($GCLOUD run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" --format='value(spec.template.spec.containers[0].image)')"
$GCLOUD run jobs deploy "$JOB" --project "$PROJECT" --region "$REGION" --image "$IMAGE" \
    --command python --args=-m,engine.precheck,--plan,--minutes,${PRECHECK_MINUTES} \
    --tasks 1 --max-retries 0 --task-timeout 55m --memory 3Gi --cpu 1 \
    --set-env-vars "CREDIBLE_RECS_LIVE_CACHE_BUCKET=${BUCKET}${ON_DEMAND_PRECHECK_VARS},CREDIBLE_RECS_PRECHECK_BRIGHT_DATA=${PRECHECK_BRIGHT_DATA},CREDIBLE_RECS_QUERY_MODEL=off" \
    "$PRECHECK_SECRETS" --quiet
$GCLOUD run jobs add-iam-policy-binding "$JOB" --project "$PROJECT" --region "$REGION" \
    --member "serviceAccount:$RUNNER" --role roles/run.invoker >/dev/null
#    And on-demand reading's job on the same image (on_demand.sh), which the site may start.
if [ "$ON_DEMAND" = on ]; then on_demand_job; fi

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
if [ "$ON_DEMAND" = on ]; then
    CREDIBLE_RECS_ON_DEMAND_BUCKET="$ON_DEMAND_BUCKET" GCLOUD="$GCLOUD" .venv/bin/python -m engine.library forget-baked \
        || echo "The bucket kept the threads read on demand: the next deploy lets them go." >&2
fi

# 7. Every job runs the site's image (16 Oct 2026: revision 60's deploy stopped before the jobs step, and the cleanup
#    policy then deleted the image the jobs still ran, so the plan job and the reader failed with "Image not found"
#    for a day). A job left on another image is moved to the site's, before the policy below is applied.
for J in "$JOB" $( [ "$ON_DEMAND" = on ] && echo "$READER_JOB" ); do
    JOB_IMAGE="$($GCLOUD run jobs describe "$J" --region "$REGION" --project "$PROJECT" \
        --format='value(spec.template.spec.template.spec.containers[0].image)')"
    if [ "$JOB_IMAGE" != "$IMAGE" ]; then
        echo "The job $J ran $JOB_IMAGE, not the site's image: moved to $IMAGE." >&2
        $GCLOUD run jobs update "$J" --region "$REGION" --project "$PROJECT" --image "$IMAGE" --quiet >/dev/null
    fi
done

# 8. Only the newest site image is kept (Noemi, 14 Oct 2026, "Keep only the newest 1"): each image is about 1.15 GB,
#    most of it the open model, and Artifact Registry's free tier is 0.5 GB. The policy (image_cleanup_policy.json) is
#    applied last, once every job runs the new image (step 7), since the first deploy is what creates the repository;
#    Google runs it about once a day.
$GCLOUD artifacts repositories set-cleanup-policies cloud-run-source-deploy --project "$PROJECT" --location "$REGION" \
    --policy deploy/cloudrun/image_cleanup_policy.json --no-dry-run --quiet >/dev/null

$GCLOUD run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" --format='value(status.url)'
