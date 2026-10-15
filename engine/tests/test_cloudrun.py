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


def test_only_the_newest_site_image_is_kept():
    # Noemi, 14 Oct 2026 ("Keep only the newest 1"): every deploy stores its container image (about 1.15 GB, most of it
    # the open model) in Artifact Registry, whose free tier is 0.5 GB; 44 images had grown to 51 GB (about 4.60 EUR a
    # month). deploy.sh applies a cleanup policy after each deploy that keeps the newest image only.
    import json

    policy = json.loads((DEPLOY_SH.parent / "image_cleanup_policy.json").read_text(encoding="utf-8"))
    keep = [rule for rule in policy if rule["action"]["type"] == "Keep"]
    delete = [rule for rule in policy if rule["action"]["type"] == "Delete"]
    assert [rule["mostRecentVersions"]["keepCount"] for rule in keep] == [1]
    assert [rule["condition"] for rule in delete] == [{"tagState": "ANY"}]
    script = DEPLOY_SH.read_text(encoding="utf-8")
    command = _command(script, '$GCLOUD artifacts repositories set-cleanup-policies')
    assert "cloud-run-source-deploy" in command and "--policy deploy/cloudrun/image_cleanup_policy.json" in command
    assert "--no-dry-run" in command
    assert script.index("set-cleanup-policies") > script.index('$GCLOUD run deploy "$SERVICE"')  # the repository exists


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
    assert '--image "$IMAGE"' in job  # the service's image
    # Its one secret is the Bright Data key (Noemi, 13 Oct 2026: "Use Bright Data"), never the feedback token. Changed on
    # purpose 14 Oct 2026 (the orchestrator): given through PRECHECK_SECRETS, none when the key's secret isn't there.
    assert '"$PRECHECK_SECRETS"' in job and "HF_TOKEN" not in job
    assert 'PRECHECK_SECRETS="--set-secrets=BRIGHT_DATA_API_KEY=bright-data-key:latest"' in script
    assert "CREDIBLE_RECS_PRECHECK_BRIGHT_DATA=${PRECHECK_BRIGHT_DATA}" in job
    # Changed on purpose, 14 Oct 2026 (the free-tier redesign): the job runs the plan, the site reads ahead.
    assert "--args=-m,engine.precheck,--plan," in job and "--max-retries 0" in job


def _precheck_settings(script: str) -> tuple[int, int]:
    """The pre-check's minutes (no Bright Data read starts after them) and its task timeout in minutes, as deploy.sh
    gives them to the job."""
    import re

    minutes = int(re.search(r'PRECHECK_MINUTES="\$\{CREDIBLE_RECS_PRECHECK_MINUTES:-(\d+)\}"', script).group(1))
    job = _command(script, '$GCLOUD run jobs deploy')
    assert "--args=-m,engine.precheck,--plan,--minutes,${PRECHECK_MINUTES}" in job
    return minutes, int(re.search(r"--task-timeout (\d+)m", job).group(1))


def test_the_pre_checks_run_fits_in_its_time():
    # Changed on purpose, 14 Oct 2026 (the free-tier redesign): the job reads nothing on the embed page; it starts no
    # Bright Data read after its minutes, and one in flight may wait up to BRIGHT_DATA_MAX_WAIT_SECONDS for Bright
    # Data's answer; five minutes more for starting and writing the plan.
    from engine.config import BRIGHT_DATA_MAX_WAIT_SECONDS, PRECHECK_PLAN_MINUTES

    minutes, timeout = _precheck_settings(DEPLOY_SH.read_text(encoding="utf-8"))
    assert minutes == PRECHECK_PLAN_MINUTES
    assert minutes * 60 + BRIGHT_DATA_MAX_WAIT_SECONDS + 5 * 60 <= timeout * 60


def test_the_pre_check_has_room_for_the_grown_library():
    # 15 Oct 2026: the plan run was killed for running out of memory at 1.5 GiB, then at 2 GiB (a library of ~2,000
    # threads; working out its 486 requests peaked at 2.97 GB on Noemi's computer with the open model, 2.25 GB without).
    # So 3 GiB, inside the free tier (the test below), and the open model off: the rules place 484 of the 486 requests
    # ("body wash" and a vague request are the two left), and the model alone is about 0.7 GB.
    import re

    job = _command(DEPLOY_SH.read_text(encoding="utf-8"), '$GCLOUD run jobs deploy')
    amount, unit = re.search(r"--memory (\d+)(Mi|Gi)", job).groups()
    assert int(amount) / (1024 if unit == "Mi" else 1) >= 3
    assert "CREDIBLE_RECS_QUERY_MODEL=off" in job


def test_the_jobs_stay_inside_cloud_runs_free_tier_in_the_longest_month():
    # Free tiers only. Cloud Run jobs are billed per instance-second for their whole run, waiting included: 240,000
    # vCPU-seconds and 450,000 GiB-seconds a month are free. Changed on purpose, 14 Oct 2026 (the free-tier redesign):
    # the pre-check runs daily for at most its task timeout (Cloud Run stops it there), the whole 31-day month;
    # on-demand reading for at most ON_DEMAND_MONTH_SECONDS a month. 10% is kept in hand.
    import re

    from engine.config import ON_DEMAND_MONTH_SECONDS

    script = DEPLOY_SH.read_text(encoding="utf-8")
    _, timeout = _precheck_settings(script)
    precheck = _command(script, '$GCLOUD run jobs deploy')
    reader = _command(ON_DEMAND_SH.read_text(encoding="utf-8"), '$GCLOUD run jobs deploy')

    def size(job: str) -> tuple[float, float]:  # vCPUs and GiB
        memory = re.search(r"--memory (\d+)(Mi|Gi)", job)
        return float(re.search(r"--cpu (\d+)", job).group(1)), int(memory.group(1)) / (1024 if memory.group(2) ==
                                                                                           "Mi" else 1)

    precheck_seconds = 31 * timeout * 60
    (cpu, gib), (reader_cpu, reader_gib) = size(precheck), size(reader)
    assert precheck_seconds * cpu + ON_DEMAND_MONTH_SECONDS * reader_cpu <= 0.9 * 240_000
    assert precheck_seconds * gib + ON_DEMAND_MONTH_SECONDS * reader_gib <= 0.9 * 450_000
    # The sums DEPLOY.md gives: 102,300 vCPU-seconds (43%) for the pre-check at most, 152,300 (63%) with on-demand's
    # (55 minutes since 14 Oct 2026: Bright Data's jobs may be waited for 20 minutes).
    assert (precheck_seconds * cpu, precheck_seconds * cpu + ON_DEMAND_MONTH_SECONDS * reader_cpu) == (102_300, 152_300)


def test_the_site_reads_ahead_within_a_third_of_its_own_free_tier():
    # 14 Oct 2026 (the free-tier redesign): the site is billed only while it answers (request-billed: 180,000
    # vCPU-seconds and 360,000 GiB-seconds free a month). Reading ahead adds at most READ_AHEAD_SECONDS (and a second for
    # the last reads to come back) to each keep-warm ping, every 5 minutes (DEPLOY.md's schedule), on the site's size.
    import re

    from engine.config import READ_AHEAD_SECONDS

    deploy = (Path(make_context.REPO_ROOT) / "deploy" / "cloudrun" / "DEPLOY.md").read_text(encoding="utf-8")
    assert '--schedule "*/5 * * * *"' in deploy  # the keep-warm ping
    site = _command(DEPLOY_SH.read_text(encoding="utf-8"), '$GCLOUD run deploy')
    cpu = float(re.search(r"--cpu (\d+)", site).group(1))
    gib = int(re.search(r"--memory (\d+)Gi", site).group(1))
    seconds = 31 * 24 * 12 * (READ_AHEAD_SECONDS + 1)
    # Changed on purpose 15 Oct 2026: the site runs at 4 GiB, a stopgap (at 2 GiB it ran out of memory every 20 to 40
    # minutes with ~1,950 threads, the open model and its warmed answers), so reading ahead's GiB-seconds rise from a
    # third of the free tier to 60% at most (214,272 of 360,000); its vCPU-seconds stay under a third. Bringing the
    # site's memory back down is in CLAUDE.md's follow-ups.
    assert seconds * cpu <= 180_000 / 3 and seconds * gib <= 360_000 * 0.6
    assert seconds * cpu == 53_568  # DEPLOY.md's sum


def test_the_bright_data_records_stay_well_inside_its_free_tier():
    # The pre-check's records a month (30 a run, every day of a 31-day month): under a fifth of Bright Data's free
    # 5,000, which it shares with the library's own reads.
    from engine.config import BRIGHT_DATA_MONTHLY_RECORDS, PRECHECK_BRIGHT_DATA_RECORDS

    assert 31 * PRECHECK_BRIGHT_DATA_RECORDS == 930 <= BRIGHT_DATA_MONTHLY_RECORDS / 5


def test_the_kept_comments_reads_are_applied_to_the_library_before_it_is_bundled():
    # Noemi, 13 Oct 2026 ("Keep only comments we use"): the image holds the library, so the pre-check's record of its
    # reads of the kept comments (in the bucket, next to the bundle) is applied before the bundle is made.
    script = DEPLOY_SH.read_text(encoding="utf-8")
    fetch = script.index('$GCLOUD storage cp "gs://$BUCKET/live_check/verified.json"')
    apply = script.index("-m engine.library apply-checks --ledger")
    assert fetch < apply < script.index("-m deploy.cloudrun.make_context")
    assert script.count("-m engine.library apply-checks") == 2  # with the record, or this machine's checks alone


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


def test_the_job_may_read_the_bright_data_key_which_the_script_never_reads_or_makes():
    script = DEPLOY_SH.read_text(encoding="utf-8")
    grant = _command(script, '$GCLOUD secrets add-iam-policy-binding')
    assert "bright-data-key" in grant and "roles/secretmanager.secretAccessor" in grant and '"serviceAccount:$RUNNER"' in grant
    assert script.index("$GCLOUD secrets add-iam-policy-binding") < script.index("$GCLOUD run jobs deploy")
    # Changed on purpose 14 Oct 2026 (the orchestrator): granted when the secret is there (it is since that day).
    before = script[:script.index("$GCLOUD secrets add-iam-policy-binding bright-data-key")]
    assert before.rstrip().endswith('if [ "$PRECHECK_BRIGHT_DATA" = on ]; then')
    # Noemi creates the secret herself (DEPLOY.md); the script only checks it is there, before building anything.
    assert "secrets create" not in script and "versions access" not in script and "BRIGHT_DATA_API_KEY=$" not in script
    assert script.index("$GCLOUD secrets describe bright-data-key") < script.index("-m deploy.cloudrun.make_context")
    assert script.index("\nprecheck_secret ") < script.index("-m deploy.cloudrun.make_context")


def _precheck_secret(tmp_path: Path, there: bool) -> tuple[list[str], str]:
    """deploy.sh's precheck_secret run on its own, with a made-up gcloud whose `secrets describe` finds the secret or
    not (nothing reaches Google): what it set, and what it said."""
    import subprocess

    script = DEPLOY_SH.read_text(encoding="utf-8")
    start = script.index("precheck_secret() {")
    function = script[start:script.index("\n}\n", start) + 3]
    gcloud = tmp_path / "gcloud"
    gcloud.write_text(f"#!/bin/sh\nexit {0 if there else 1}\n", encoding="utf-8")
    gcloud.chmod(0o755)
    shell = (f"set -eu\nGCLOUD={gcloud}\nPROJECT=made-up\n{function}"
             'precheck_secret\necho "$PRECHECK_BRIGHT_DATA"\necho "$PRECHECK_SECRETS"\n')
    done = subprocess.run(["sh", "-c", shell], capture_output=True, text=True, check=True)
    return done.stdout.splitlines(), done.stderr


def test_a_missing_bright_data_key_turns_the_step_off_says_so_once_and_never_stops_the_deploy(tmp_path):
    # 14 Oct 2026 (the orchestrator): as on-demand reading's on_demand_secret, a missing key must never stop a deploy.
    assert _precheck_secret(tmp_path, there=True) == (["on", "--set-secrets=BRIGHT_DATA_API_KEY=bright-data-key:latest"], "")
    (state, secrets), said = _precheck_secret(tmp_path, there=False)
    assert (state, secrets) == ("off", "--clear-secrets")  # no secret the job would fail to find
    assert len(said.splitlines()) == 1 and "bright-data-key" in said and "off" in said
    assert "exit 1" not in DEPLOY_SH.read_text(encoding="utf-8")
