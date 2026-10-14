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


def test_the_bundle_leaves_out_threads_not_extracted_yet(tmp_path):
    # 14 Oct 2026 (the orchestrator, after the bulk import added 1,133 threads awaiting extraction): answers never use a
    # thread with no extraction, so the image doesn't carry it (the server reads and checks fewer files as it starts);
    # it ships once extracted. Gold-set threads aren't in the library folder at all.
    repo = a_repo(tmp_path)
    waiting = repo / "data" / "library" / "threads" / "1zzz.json"
    waiting.write_text("{}", encoding="utf-8")
    out = tmp_path / "bundle"
    make_context.copy_library(repo / "data" / "library", out / "data" / "library")
    assert not (out / "data" / "library" / "threads" / "1zzz.json").exists()
    assert (out / "data" / "library" / "threads" / "1abc.json").exists()


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


def test_the_gemini_key_is_checked_for_never_made_or_read_and_its_absence_turns_on_demand_off():
    # Changed on purpose, 14 Oct 2026 (the orchestrator): a missing key first stopped the whole deploy; it must not stop
    # the site's own deploys, so it turns on-demand reading off for that deploy (the site then never says it started).
    script = ON_DEMAND_SH.read_text(encoding="utf-8")
    assert "$GCLOUD secrets describe gemini-key" in script and "ON_DEMAND=off" in script and "exit 1" not in script
    assert "secrets create" not in script and "versions access" not in script  # Noemi makes it, nobody reads it
    grant = _command(script, '$GCLOUD secrets add-iam-policy-binding gemini-key')
    assert '"serviceAccount:$RUNNER"' in grant and "roles/secretmanager.secretAccessor" in grant
    deploy = DEPLOY_SH.read_text(encoding="utf-8")
    assert ". deploy/cloudrun/on_demand.sh" in deploy
    assert deploy.index("\non_demand_secret ") < deploy.index("-m deploy.cloudrun.make_context")  # before any build
    for step in ("on_demand_bucket", "on_demand_job", "-m engine.library pull-bucket", "-m engine.library forget-baked"):
        line = next(text for text in deploy.splitlines() if step in text and not text.lstrip().startswith("#"))
        before = deploy[:deploy.index(line)]
        assert before.rstrip().endswith('if [ "$ON_DEMAND" = on ]; then') or 'if [ "$ON_DEMAND" = on ]; then ' + step in line


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
    # 14 Oct 2026: the settings come through ON_DEMAND_SITE_VARS / ON_DEMAND_PRECHECK_VARS, empty while it is off.
    assert "${ON_DEMAND_SITE_VARS}" in service and "${ON_DEMAND_PRECHECK_VARS}" in _command(script, '$GCLOUD run jobs deploy')
    assert "CREDIBLE_RECS_ON_DEMAND_BUCKET=${ON_DEMAND_BUCKET}" in script.split('ON_DEMAND_SITE_VARS="', 1)[1].split("\n")[0]
    assert "CREDIBLE_RECS_ON_DEMAND_JOB=${READER_JOB_NAME}" in script.split('ON_DEMAND_SITE_VARS="', 1)[1].split("\n")[0]
    assert "CREDIBLE_RECS_ON_DEMAND_BUCKET=${ON_DEMAND_BUCKET}" in script.split('ON_DEMAND_PRECHECK_VARS="', 1)[1].split("\n")[0]
    names = ON_DEMAND_SH.read_text(encoding="utf-8")
    assert 'READER_JOB_NAME="projects/${PROJECT}/locations/${REGION}/jobs/${READER_JOB}"' in names


def test_a_deploy_bakes_in_the_threads_read_on_demand_and_then_the_bucket_lets_them_go():
    script = DEPLOY_SH.read_text(encoding="utf-8")
    pull = script.index("-m engine.library pull-bucket")
    assert pull < script.index("-m deploy.cloudrun.make_context") < script.index("$GCLOUD run deploy")
    assert script.index("$GCLOUD run deploy") < script.index("-m engine.library forget-baked")


# --- File times (14 Oct 2026): nothing in the image may be dated ahead of the clock ---

def test_every_file_of_the_bundle_is_dated_well_before_it_was_made(tmp_path):
    # The deploy's upload stores each file's time as the local time of the computer it runs on, which the build reads
    # as UTC: in British Summer Time the site's files were dated an hour ahead, and the server took the library's newest
    # files for ones still changing (engine.memo.changed_just_now). Stamped a day before the bundle was made, no time
    # zone's shift (at most 14 hours) can date a file ahead of the clock.
    import os
    import time

    repo = a_repo(tmp_path)
    future = time.time() + 3600
    os.utime(repo / "data" / "library" / "extracted" / "1abc.json", (future, future))  # a file already dated ahead
    out = tmp_path / "bundle"
    make_context.copy_library(repo / "data" / "library", out / "data" / "library")
    (out / "engine").mkdir()
    (out / "engine" / "web.py").write_text("# code\n", encoding="utf-8")
    made = time.time()
    make_context.stamp_files(out, made)
    times = {p.relative_to(out).as_posix(): p.stat().st_mtime for p in out.rglob("*")}
    assert set(times.values()) == {make_context.bundle_stamp(made)}
    assert make_context.bundle_stamp(made) + 14 * 3600 < made


def test_making_the_bundle_stamps_its_files(tmp_path, monkeypatch):
    stamped = []
    monkeypatch.setattr(make_context, "stamp_files", lambda dest, made: stamped.append(dest))
    repo = a_repo(tmp_path)
    import subprocess

    (repo / ".gitignore").write_text(".env\ndata/library/\n", encoding="utf-8")
    (repo / "engine").mkdir()
    (repo / "engine" / "web.py").write_text("# code\n", encoding="utf-8")
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.com", "PATH": __import__("os").environ["PATH"], "HOME": str(tmp_path)}
    for command in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "made-up"]):
        subprocess.run(["git", "-C", str(repo), *command], check=True, env=env)
    make_context.make_context(tmp_path / "bundle", repo=repo)
    assert stamped == [tmp_path / "bundle"]
