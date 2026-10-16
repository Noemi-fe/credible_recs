# On-demand reading's pieces on Google Cloud (Noemi's plan of 14 Oct 2026, part 3; engine/on_demand.py; DEPLOY.md, "On-
# demand reading"). Sourced by deploy.sh, which calls each step where it belongs: on_demand_secret before anything is
# built, on_demand_bucket before the site is deployed, on_demand_job once the site runs its new image. Uses deploy.sh's
# PROJECT, REGION, RUNNER, GCLOUD and, for the job, IMAGE. Safe to run again: each step creates what is missing and sets
# again what is there.
ON_DEMAND_BUCKET="${CREDIBLE_RECS_ON_DEMAND_BUCKET:-credible-picks-on-demand}"
READER_JOB="${CREDIBLE_RECS_GCP_READER_JOB:-credible-recs-reader}"
READER_JOB_NAME="projects/${PROJECT}/locations/${REGION}/jobs/${READER_JOB}"  # what the site starts (jobs:run)

# The switch (Noemi's decision 6 of 16 Oct 2026: on-demand reading is off for the interviews, since Gemini's free
# allowance reads about one product a day and "check back in about 20 minutes" isn't true; Claude reads the likely
# products ahead instead). On only when CREDIBLE_RECS_ON_DEMAND is "on" for the deploy, else off, whatever else it says:
#     CREDIBLE_RECS_ON_DEMAND=on sh deploy/cloudrun/deploy.sh
# Off, a deploy is the one without the Gemini key below: the site gets none of on-demand reading's settings, so it answers
# a product it hasn't read about with the honest no-threads message and never queues a request or starts the reading
# job, and the pre-check doesn't look at the queue. Nothing is deleted: the code, the bucket (its objects go at 37 days
# as always) and the job stay, and the next deploy with the setting turns it on again.
ON_DEMAND_SWITCH="${CREDIBLE_RECS_ON_DEMAND:-off}"

# The Gemini key, the Secret Manager secret gemini-key, which Noemi creates herself (DEPLOY.md, "The Gemini key"). This
# script never makes or reads it. When it isn't there yet, on-demand reading stays off for this deploy (14 Oct 2026, the
# orchestrator: a missing key must not stop the site's own deploys): ON_DEMAND is "off", the site gets none of its
# settings (so it never says it has started reading), and no bucket, job or pull is touched; the next deploy after the
# key exists turns it on. Looked for only when the switch is on.
on_demand_secret() {
    if [ "$ON_DEMAND_SWITCH" != on ]; then
        ON_DEMAND=off
        echo "On-demand reading is off for this deploy (Noemi's decision 6 of 16 Oct 2026); CREDIBLE_RECS_ON_DEMAND=on sh deploy/cloudrun/deploy.sh turns it on (deploy/cloudrun/DEPLOY.md, On-demand reading)." >&2
        return 0
    fi
    if $GCLOUD secrets describe gemini-key --project "$PROJECT" >/dev/null 2>&1; then
        ON_DEMAND=on
    else
        ON_DEMAND=off
        echo "The secret gemini-key isn't there yet: on-demand reading stays off for this deploy (deploy/cloudrun/DEPLOY.md, The Gemini key)." >&2
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
