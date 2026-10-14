# On-demand reading's pieces on Google Cloud (Noemi's plan of 14 Oct 2026, part 3; engine/on_demand.py; DEPLOY.md, "On-
# demand reading"). Sourced by deploy.sh, which calls each step where it belongs: on_demand_secret before anything is
# built, on_demand_bucket before the site is deployed, on_demand_job once the site runs its new image. Uses deploy.sh's
# PROJECT, REGION, RUNNER, GCLOUD and, for the job, IMAGE. Safe to run again: each step creates what is missing and sets
# again what is there.
ON_DEMAND_BUCKET="${CREDIBLE_RECS_ON_DEMAND_BUCKET:-credible-picks-on-demand}"
READER_JOB="${CREDIBLE_RECS_GCP_READER_JOB:-credible-recs-reader}"
READER_JOB_NAME="projects/${PROJECT}/locations/${REGION}/jobs/${READER_JOB}"  # what the site starts (jobs:run)

# The Gemini key, the Secret Manager secret gemini-key, which Noemi creates herself (DEPLOY.md, "The Gemini key"). This
# script never makes or reads it; it stops before anything is built when it isn't there yet.
on_demand_secret() {
    if ! $GCLOUD secrets describe gemini-key --project "$PROJECT" >/dev/null 2>&1; then
        echo "The secret gemini-key isn't there yet: create it first (deploy/cloudrun/DEPLOY.md, The Gemini key)." >&2
        exit 1
    fi
}

# The bucket of the queue and the threads read on demand (two objects under on_demand/): private (uniform access,
# public access prevented), in the site's region, every object deleted once 37 days old (the archive's keeping time:
# a bundle the job stopped rewriting goes with its text), and nothing kept after a deletion (no soft delete). The site
# and both jobs run as RUNNER, which may read, write and delete its objects only.
on_demand_bucket() {
    if ! $GCLOUD storage buckets describe "gs://$ON_DEMAND_BUCKET" --project "$PROJECT" >/dev/null 2>&1; then
        $GCLOUD storage buckets create "gs://$ON_DEMAND_BUCKET" --project "$PROJECT" --location "$REGION" \
            --uniform-bucket-level-access --public-access-prevention --soft-delete-duration 0 \
            --lifecycle-file deploy/cloudrun/on_demand_lifecycle.json
    fi
    $GCLOUD storage buckets update "gs://$ON_DEMAND_BUCKET" --project "$PROJECT" --public-access-prevention \
        --clear-soft-delete --lifecycle-file deploy/cloudrun/on_demand_lifecycle.json
    $GCLOUD storage buckets add-iam-policy-binding "gs://$ON_DEMAND_BUCKET" --project "$PROJECT" \
        --member "serviceAccount:$RUNNER" --role roles/storage.objectUser >/dev/null
}

# The reading job, on the image the site now runs: `python -m engine.on_demand run`, never retried by Cloud Run (the
# site and the keep-warm ping start it again), 45 minutes at most a run (it starts no new reading after 15, and one
# takes about 12). Billed for its whole run, waiting included, so the least that works: 1 vCPU (a job's minimum) and
# 1 GiB (it never loads the open model). Its one secret is the Gemini key, which RUNNER may read; the site, which also
# runs as RUNNER, may start it. No schedule of its own: Cloud Scheduler's keep-warm ping drives the retries.
on_demand_job() {
    $GCLOUD secrets add-iam-policy-binding gemini-key --project "$PROJECT" \
        --member "serviceAccount:$RUNNER" --role roles/secretmanager.secretAccessor >/dev/null
    $GCLOUD run jobs deploy "$READER_JOB" --project "$PROJECT" --region "$REGION" --image "$IMAGE" \
        --command python --args=-m,engine.on_demand,run \
        --tasks 1 --max-retries 0 --task-timeout 45m --memory 1Gi --cpu 1 \
        --set-env-vars "CREDIBLE_RECS_ON_DEMAND_BUCKET=${ON_DEMAND_BUCKET},CREDIBLE_RECS_QUERY_MODEL=off" \
        --set-secrets "GEM_API_KEY=gemini-key:latest" --quiet
    $GCLOUD run jobs add-iam-policy-binding "$READER_JOB" --project "$PROJECT" --region "$REGION" \
        --member "serviceAccount:$RUNNER" --role roles/run.invoker >/dev/null
}
