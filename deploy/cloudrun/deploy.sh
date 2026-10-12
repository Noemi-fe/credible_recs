#!/bin/sh
# Builds and deploys the site to Google Cloud Run in Noemi's project (deploy/cloudrun/DEPLOY.md). Run from the
# repository's root after committing:   sh deploy/cloudrun/deploy.sh
# It bundles the current commit with the saved library (deploy/cloudrun/make_context.py), has Cloud Build turn it into
# a private image, and deploys it: public site, one server at most, none when idle (the free tier).
set -eu
PROJECT="${CREDIBLE_RECS_GCP_PROJECT:-credible-picks}"
REGION="${CREDIBLE_RECS_GCP_REGION:-europe-west1}"
SERVICE="${CREDIBLE_RECS_GCP_SERVICE:-credible-recs}"
GCLOUD="${GCLOUD:-gcloud}"

NUMBER="$($GCLOUD projects describe "$PROJECT" --format='value(projectNumber)')"
HOSTS="${SERVICE}-${NUMBER}.${REGION}.run.app"
# The service's older-style address too, once it exists.
OLD="$($GCLOUD run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" --format='value(status.url)' 2>/dev/null || true)"
if [ -n "$OLD" ]; then HOSTS="$HOSTS,${OLD#https://}"; fi

BUNDLE="$(mktemp -d)/bundle"
.venv/bin/python -m deploy.cloudrun.make_context "$BUNDLE"
$GCLOUD run deploy "$SERVICE" --project "$PROJECT" --region "$REGION" --source "$BUNDLE" \
    --allow-unauthenticated --memory 2Gi --cpu 1 --cpu-boost --max-instances 1 --min-instances 0 \
    --concurrency 8 --timeout 300 \
    --set-env-vars "CREDIBLE_RECS_ALLOWED_HOSTS=${HOSTS},CREDIBLE_RECS_GOATCOUNTER=noemix,CREDIBLE_RECS_FEEDBACK_REPO=Noemix/credible-recs-feedback" \
    --set-secrets "HF_TOKEN=hf-token:latest" --quiet
rm -rf "$(dirname "$BUNDLE")"
$GCLOUD run services describe "$SERVICE" --region "$REGION" --project "$PROJECT" --format='value(status.url)'
