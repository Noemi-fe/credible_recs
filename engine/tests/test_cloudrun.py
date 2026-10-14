"""The Google Cloud Run package (Noemi, 12 Oct 2026): what goes into the private build bundle, and what never does."""

from pathlib import Path

import pytest

from deploy.cloudrun import make_context


def a_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    for name in ("threads/1abc.json", "extracted/1abc.json", "profiles.json", "summaries.json", "requests.jsonl",
                 "candidates.json", "summaries_todo.json"):
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
    assert copied == ["data/library/extracted/1abc.json", "data/library/profiles.json", "data/library/summaries.json",
                      "data/library/threads/1abc.json"]  # the one-line summaries too (13 Oct 2026), not their to-do list


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


# --- On-demand reading (Noemi's plan of 14 Oct 2026, part 3): its bucket, its job and the Gemini key ---

ON_DEMAND_SH = Path(make_context.REPO_ROOT) / "deploy" / "cloudrun" / "on_demand.sh"
ON_DEMAND_LIFECYCLE = Path(make_context.REPO_ROOT) / "deploy" / "cloudrun" / "on_demand_lifecycle.json"


def test_the_threads_read_on_demand_go_from_the_bucket_after_the_archives_keeping_time():
    import json

    from engine.config import ARCHIVE_TEXT_KEPT_DAYS

    rules = json.loads(ON_DEMAND_LIFECYCLE.read_text(encoding="utf-8"))
    assert rules == {"rule": [{"action": {"type": "Delete"}, "condition": {"age": ARCHIVE_TEXT_KEPT_DAYS}}]}


def test_the_on_demand_bucket_is_private_and_keeps_nothing_deleted():
    script = ON_DEMAND_SH.read_text(encoding="utf-8")
    create = _command(script, '$GCLOUD storage buckets create')
    for flag in ('"gs://$ON_DEMAND_BUCKET"', "--uniform-bucket-level-access", "--public-access-prevention",
                 "--soft-delete-duration 0", "--lifecycle-file deploy/cloudrun/on_demand_lifecycle.json",
                 '--location "$REGION"'):
        assert flag in create
    update = _command(script, '$GCLOUD storage buckets update')
    for flag in ("--public-access-prevention", "--clear-soft-delete",
                 "--lifecycle-file deploy/cloudrun/on_demand_lifecycle.json"):
        assert flag in update
    grant = _command(script, '$GCLOUD storage buckets add-iam-policy-binding')
    assert '"gs://$ON_DEMAND_BUCKET"' in grant and "roles/storage.objectUser" in grant


def test_the_gemini_key_is_checked_for_never_made_or_read_and_its_absence_stops_the_deploy():
    script = ON_DEMAND_SH.read_text(encoding="utf-8")
    assert "$GCLOUD secrets describe gemini-key" in script and "exit 1" in script
    assert "secrets create" not in script and "versions access" not in script  # Noemi makes it, nobody reads it
    grant = _command(script, '$GCLOUD secrets add-iam-policy-binding gemini-key')
    assert '"serviceAccount:$RUNNER"' in grant and "roles/secretmanager.secretAccessor" in grant
    deploy = DEPLOY_SH.read_text(encoding="utf-8")
    assert ". deploy/cloudrun/on_demand.sh" in deploy
    assert deploy.index("\non_demand_secret ") < deploy.index("-m deploy.cloudrun.make_context")  # before any build


def test_the_reading_job_runs_on_the_sites_image_with_the_key_and_the_site_may_start_it():
    script = ON_DEMAND_SH.read_text(encoding="utf-8")
    job = _command(script, '$GCLOUD run jobs deploy')
    assert '--image "$IMAGE"' in job and "--args=-m,engine.on_demand,run" in job and "--max-retries 0" in job
    assert '--set-secrets "GEM_API_KEY=gemini-key:latest"' in job
    assert "CREDIBLE_RECS_ON_DEMAND_BUCKET=${ON_DEMAND_BUCKET}" in job
    assert "roles/run.invoker" in _command(script, '$GCLOUD run jobs add-iam-policy-binding')
    assert "scheduler" not in script  # no schedule of its own: the site starts it, the keep-warm ping again


def test_the_reading_jobs_timeout_covers_a_run_and_its_lease_outlasts_it():
    import re

    from engine.config import ON_DEMAND_LEASE_MINUTES, ON_DEMAND_NEW_READING_SECONDS

    job = _command(ON_DEMAND_SH.read_text(encoding="utf-8"), '$GCLOUD run jobs deploy')
    minutes = int(re.search(r"--task-timeout (\d+)m", job).group(1))
    assert ON_DEMAND_NEW_READING_SECONDS / 60 + 15 <= minutes < ON_DEMAND_LEASE_MINUTES  # one more reading fits


def test_the_site_and_the_pre_check_know_the_bucket_and_the_site_knows_the_job():
    script = DEPLOY_SH.read_text(encoding="utf-8")
    service = _command(script, '$GCLOUD run deploy')
    assert "CREDIBLE_RECS_ON_DEMAND_BUCKET=${ON_DEMAND_BUCKET}" in service
    assert "CREDIBLE_RECS_ON_DEMAND_JOB=${READER_JOB_NAME}" in service
    assert "CREDIBLE_RECS_ON_DEMAND_BUCKET=${ON_DEMAND_BUCKET}" in _command(script, '$GCLOUD run jobs deploy')
    names = ON_DEMAND_SH.read_text(encoding="utf-8")
    assert 'READER_JOB_NAME="projects/${PROJECT}/locations/${REGION}/jobs/${READER_JOB}"' in names


def test_a_deploy_bakes_in_the_threads_read_on_demand_and_then_the_bucket_lets_them_go():
    script = DEPLOY_SH.read_text(encoding="utf-8")
    pull = script.index("-m engine.library pull-bucket")
    assert pull < script.index("-m deploy.cloudrun.make_context") < script.index("$GCLOUD run deploy")
    assert script.index("$GCLOUD run deploy") < script.index("-m engine.library forget-baked")
