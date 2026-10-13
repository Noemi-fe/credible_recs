"""The Google Cloud Run package (Noemi, 12 Oct 2026): what goes into the private build bundle, and what never does."""

from pathlib import Path

import pytest

from deploy.cloudrun import make_context


def a_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    for name in ("threads/1abc.json", "extracted/1abc.json", "profiles.json", "requests.jsonl", "candidates.json"):
        path = repo / "data" / "library" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    (repo / ".env").write_text("HF_TOKEN=hf_secret", encoding="utf-8")
    (repo / "deploy" / "cloudrun").mkdir(parents=True)
    (repo / "deploy" / "cloudrun" / "Dockerfile").write_text("FROM python:3.12-slim\n", encoding="utf-8")
    return repo


def test_the_bundle_holds_the_library_the_answers_read_and_nothing_else_of_it(tmp_path):
    repo = a_repo(tmp_path)
    out = tmp_path / "bundle"
    make_context.copy_library(repo / "data" / "library", out / "data" / "library")
    copied = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    assert copied == ["data/library/extracted/1abc.json", "data/library/profiles.json", "data/library/threads/1abc.json"]


def test_a_bundle_with_a_secret_or_a_cache_is_refused(tmp_path):
    out = tmp_path / "bundle"
    out.mkdir()
    (out / "engine").mkdir()
    make_context.check_bundle(out)  # clean: no error
    (out / ".env.example").write_text("HF_TOKEN=", encoding="utf-8")  # the repository's template, no secret in it
    make_context.check_bundle(out)
    (out / ".env").write_text("HF_TOKEN=hf_secret", encoding="utf-8")
    with pytest.raises(make_context.BundleError, match=".env"):
        make_context.check_bundle(out)
    (out / ".env").unlink()
    (out / ".cache").mkdir()
    with pytest.raises(make_context.BundleError, match=".cache"):
        make_context.check_bundle(out)


# --- Checking ahead (13 Oct 2026): the live checks' bucket and the daily pre-check job ---

DEPLOY_SH = Path(make_context.REPO_ROOT) / "deploy" / "cloudrun" / "deploy.sh"
LIFECYCLE = Path(make_context.REPO_ROOT) / "deploy" / "cloudrun" / "live_cache_lifecycle.json"


def _command(script: str, starts: str) -> str:
    """The whole command (its continued lines joined) that starts with `starts`."""
    lines = script.replace("\\\n", " ").splitlines()
    (found,) = [line for line in lines if line.strip().startswith(starts)]
    return " ".join(found.split())


def test_the_bucket_deletes_every_check_two_days_old():
    import json

    rules = json.loads(LIFECYCLE.read_text(encoding="utf-8"))
    assert rules == {"rule": [{"action": {"type": "Delete"}, "condition": {"age": 2}}]}


def test_the_bucket_is_private_keeps_nothing_deleted_and_has_the_two_day_rule():
    script = DEPLOY_SH.read_text(encoding="utf-8")
    create = _command(script, '$GCLOUD storage buckets create')
    for flag in ("--uniform-bucket-level-access", "--public-access-prevention", "--soft-delete-duration 0",
                 "--lifecycle-file deploy/cloudrun/live_cache_lifecycle.json", '--location "$REGION"'):
        assert flag in create
    update = _command(script, '$GCLOUD storage buckets update')
    for flag in ("--public-access-prevention", "--clear-soft-delete",
                 "--lifecycle-file deploy/cloudrun/live_cache_lifecycle.json"):
        assert flag in update  # set again at every deploy, so a change made by hand doesn't last
    grant = _command(script, '$GCLOUD storage buckets add-iam-policy-binding')
    assert "roles/storage.objectUser" in grant and '"serviceAccount:$RUNNER"' in grant


def test_the_site_and_the_pre_check_share_the_bucket_and_the_image():
    script = DEPLOY_SH.read_text(encoding="utf-8")
    service = _command(script, '$GCLOUD run deploy')
    job = _command(script, '$GCLOUD run jobs deploy')
    assert "CREDIBLE_RECS_LIVE_CACHE_BUCKET=${BUCKET}" in service and "CREDIBLE_RECS_LIVE_CACHE_BUCKET=${BUCKET}" in job
    assert '--image "$IMAGE"' in job and "--set-secrets" not in job  # the service's image; the job needs no secret
    assert "--args=-m,engine.precheck,--limit,${PRECHECK_LIMIT}" in job and "--max-retries 0" in job


def test_the_pre_checks_reads_fit_in_its_time_and_reddits_pace():
    import re

    from engine.config import LIVE_CHECK_BURST, LIVE_CHECK_REFILL_SECONDS, PRECHECK_MAX_READS

    script = DEPLOY_SH.read_text(encoding="utf-8")
    limit = int(re.search(r'PRECHECK_LIMIT="\$\{CREDIBLE_RECS_PRECHECK_LIMIT:-(\d+)\}"', script).group(1))
    hours = int(re.search(r"--task-timeout (\d+)h", _command(script, '$GCLOUD run jobs deploy')).group(1))
    assert limit == PRECHECK_MAX_READS
    reading = (limit - LIVE_CHECK_BURST) * LIVE_CHECK_REFILL_SECONDS  # seconds, at the live check's pace
    assert reading + 30 * 60 < hours * 3600  # and half an hour to work out the answers on one processor


def test_the_pre_check_runs_once_a_day_at_night_uk_time():
    script = DEPLOY_SH.read_text(encoding="utf-8")
    schedule = _command(script, '$GCLOUD scheduler jobs "$VERB" http')
    assert '--schedule "0 4 * * *"' in schedule and '--time-zone "Europe/London"' in schedule
    assert '--oauth-service-account-email "$RUNNER"' in schedule and "jobs/${JOB}:run" in schedule
    assert "roles/run.invoker" in _command(script, '$GCLOUD run jobs add-iam-policy-binding')
