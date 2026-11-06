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
    # Changed on purpose 5 Nov 2026 (the site-memory builder, Noemi's "Let's do A"): 2 GiB. The library's objects take about a
    # third less memory (engine/tests/test_site_memory.py), and the plan run for 559 requests over 2,748 threads peaked at
    # 913 MB on Noemi's computer (1,410 MB before), well under 2 GiB where 80% is the ceiling. The job on Cloud Run peaked at
    # 1.47 GiB of its 3 on 19 Oct 2026 (Cloud Monitoring). A job of 2 GiB bills a third fewer GiB-seconds.
    import re

    job = _command(DEPLOY_SH.read_text(encoding="utf-8"), '$GCLOUD run jobs deploy')
    amount, unit = re.search(r"--memory (\d+)(Mi|Gi)", job).groups()
    assert int(amount) / (1024 if unit == "Mi" else 1) == 2
    assert "CREDIBLE_RECS_QUERY_MODEL=off" in job


# --- Google's free allowance: one pot in dollars (6 Nov 2026, Noemi's doubling of on-demand reading, option A) ---
#
# Cloud Run's pricing page (https://cloud.google.com/run/pricing, read 6 Nov 2026): "The free tier is applied as a
# spending based discount using Tier 1 pricing", the same money in each section: 240,000 vCPU-seconds of a job at
# $0.000018 and 180,000 of a request-billed service at $0.000024 are both $4.32, and 450,000 GiB-seconds at $0.000002
# and 360,000 at $0.0000025 both $0.90. So the site and both jobs share one pot per part (CPU and memory), in dollars,
# and every sum below is in that pot. Until 6 Nov 2026 the jobs' and the site's allowances were summed apart.

def _size(command: str) -> tuple[float, float]:
    """A deploy command's vCPUs and GiB."""
    import re

    memory = re.search(r"--memory (\d+)(Mi|Gi)", command)
    return (float(re.search(r"--cpu (\d+)", command).group(1)),
            int(memory.group(1)) / (1024 if memory.group(2) == "Mi" else 1))


def _pot(cpu_seconds: float, gib_seconds: float, kind: str) -> tuple[float, float]:
    """Dollars of each part at Tier 1 prices: kind "job" (instance-billed) or "service" (request-billed)."""
    from engine.config import CLOUD_RUN_PRICES

    return cpu_seconds * CLOUD_RUN_PRICES[kind]["cpu"], gib_seconds * CLOUD_RUN_PRICES[kind]["memory"]


def test_the_free_allowance_is_one_pot_in_dollars_at_tier_1_prices():
    from engine.config import CLOUD_RUN_PRICES, FREE_TIER_DOLLARS, FREE_TIER_SHARE

    job, service = CLOUD_RUN_PRICES["job"], CLOUD_RUN_PRICES["service"]
    assert (job["cpu"], job["memory"], service["cpu"], service["memory"]) == (0.000018, 0.000002, 0.000024, 0.0000025)
    assert FREE_TIER_DOLLARS["cpu"] == pytest.approx(240_000 * job["cpu"]) == pytest.approx(180_000 * service["cpu"])
    assert FREE_TIER_DOLLARS["memory"] == pytest.approx(450_000 * job["memory"]) == pytest.approx(
        360_000 * service["memory"])
    assert FREE_TIER_DOLLARS == {"cpu": pytest.approx(4.32), "memory": pytest.approx(0.90)}
    assert FREE_TIER_SHARE == 0.9  # 10% kept in hand on each part


def test_the_site_is_request_billed_with_its_startup_boost():
    # Billed only while it answers (no --no-cpu-throttling, none when idle), at the service prices; its startup boost (2
    # vCPU while it starts and 10 s after, https://cloud.google.com/run/docs/configuring/services/cpu) is billed, so the
    # guard counts Cloud Monitoring's CPU allocation, which holds it, never billable time alone.
    site = _command(DEPLOY_SH.read_text(encoding="utf-8"), '$GCLOUD run deploy')
    assert "--no-cpu-throttling" not in site and "--min-instances 0" in site and "--cpu-boost" in site


def test_the_guards_sizes_and_names_are_the_deploys():
    import re

    from engine.config import CLOUD_RUN_PRECHECK, CLOUD_RUN_READER, CLOUD_RUN_SITE, CLOUD_RUN_SIZES

    script, reader = DEPLOY_SH.read_text(encoding="utf-8"), ON_DEMAND_SH.read_text(encoding="utf-8")
    assert re.search(r'SERVICE="\$\{CREDIBLE_RECS_GCP_SERVICE:-([a-z-]+)\}"', script).group(1) == CLOUD_RUN_SITE
    assert re.search(r'JOB="\$\{CREDIBLE_RECS_GCP_JOB:-([a-z-]+)\}"', script).group(1) == CLOUD_RUN_PRECHECK
    assert re.search(r'READER_JOB="\$\{CREDIBLE_RECS_GCP_READER_JOB:-([a-z-]+)\}"', reader).group(1) == CLOUD_RUN_READER
    assert CLOUD_RUN_SIZES == {
        CLOUD_RUN_SITE: ("service", *_size(_command(script, '$GCLOUD run deploy'))),
        CLOUD_RUN_PRECHECK: ("job", *_size(_command(script, '$GCLOUD run jobs deploy'))),
        CLOUD_RUN_READER: ("job", *_size(_command(reader, '$GCLOUD run jobs deploy')))}


def _read_ahead_seconds() -> float:
    """Reading ahead's most billed seconds in a 31-day month: READ_AHEAD_SECONDS and a second more at each keep-warm
    ping, every 5 minutes (DEPLOY.md's schedule)."""
    from engine.config import READ_AHEAD_SECONDS

    deploy = (Path(make_context.REPO_ROOT) / "deploy" / "cloudrun" / "DEPLOY.md").read_text(encoding="utf-8")
    assert '--schedule "*/5 * * * *"' in deploy  # the keep-warm ping
    return 31 * 24 * 12 * (READ_AHEAD_SECONDS + 1)


def test_the_jobs_stay_inside_cloud_runs_free_tier_in_the_longest_month():
    # Free tiers only. Cloud Run jobs are billed per instance-second for their whole run, waiting included. Changed on
    # purpose, 14 Oct 2026 (the free-tier redesign): the pre-check runs daily for at most its task timeout (Cloud Run
    # stops it there), the whole 31-day month; on-demand reading for at most ON_DEMAND_MONTH_SECONDS a month.
    # Changed on purpose 6 Nov 2026 (Noemi's doubling, option A: one shared pot): the sums are in the pot's dollars, with
    # the site's reading ahead at its own limit beside the jobs, and they show plainly what the hard caps can't do. The
    # pre-check at its 55 minutes every day and reading ahead at its limit are 77% of the CPU part and, with the site at
    # 3 GiB, 97.5% of the memory part before on-demand reading reads a second (80.2% at 2 GiB); visitors' answers on the
    # site have no cap at all. So no month seconds keep 10% in hand on the memory part at 3 GiB by the caps alone, and
    # on the CPU part only 30,372 would (44,160 on memory at 2 GiB), under the 50,000 of before the doubling. The caps
    # can't keep the margin: the free-tier guard (engine/free_tier.py) does, from Cloud Monitoring, before any backfill
    # read and before any visitor read past the first ON_DEMAND_GUARD_FREE_SECONDS (engine/tests/test_free_tier.py).
    from engine.config import FREE_TIER_DOLLARS, FREE_TIER_SHARE, ON_DEMAND_MONTH_SECONDS

    script = DEPLOY_SH.read_text(encoding="utf-8")
    _, timeout = _precheck_settings(script)
    (cpu, gib), (reader_cpu, reader_gib) = (_size(_command(script, '$GCLOUD run jobs deploy')),
                                            _size(_command(ON_DEMAND_SH.read_text(encoding="utf-8"),
                                                           '$GCLOUD run jobs deploy')))
    site_cpu, site_gib = _size(_command(script, '$GCLOUD run deploy'))
    precheck_seconds, ahead = 31 * timeout * 60, _read_ahead_seconds()
    precheck = _pot(precheck_seconds * cpu, precheck_seconds * gib, "job")
    read_ahead = {gib_: _pot(ahead * site_cpu, ahead * gib_, "service") for gib_ in (site_gib, 2)}
    reader = _pot(ON_DEMAND_MONTH_SECONDS * reader_cpu, ON_DEMAND_MONTH_SECONDS * reader_gib, "job")
    assert site_gib == 3
    # The pot table (DEPLOY.md, Costs): dollars of each part at 3 GiB, and at 2 GiB beside it.
    assert (precheck_seconds * cpu, precheck_seconds * gib) == (102_300, 204_600)
    assert precheck == (pytest.approx(1.8414), pytest.approx(0.4092))
    assert read_ahead[3] == (pytest.approx(1.499904), pytest.approx(0.46872))
    assert read_ahead[2] == (pytest.approx(1.499904), pytest.approx(0.31248))
    assert ON_DEMAND_MONTH_SECONDS == 92_000 and reader == (pytest.approx(1.656), pytest.approx(0.184))
    cpu_part = precheck[0] + read_ahead[3][0]
    memory_part = {gib_: precheck[1] + read_ahead[gib_][1] for gib_ in (3, 2)}
    assert cpu_part / FREE_TIER_DOLLARS["cpu"] == pytest.approx(0.7734, abs=1e-4)
    assert memory_part[3] / FREE_TIER_DOLLARS["memory"] == pytest.approx(0.9755, abs=1e-4)
    assert memory_part[2] / FREE_TIER_DOLLARS["memory"] == pytest.approx(0.8019, abs=1e-4)
    # Plainly: at 3 GiB the memory part is past 90% by the caps alone, and with the reader's month both parts are over
    # the whole pot (CPU 115.7%, memory 118.0%; 100.6% at 2 GiB).
    assert memory_part[3] > FREE_TIER_SHARE * FREE_TIER_DOLLARS["memory"]
    assert (cpu_part + reader[0]) / FREE_TIER_DOLLARS["cpu"] == pytest.approx(1.1568, abs=1e-4)
    assert (memory_part[3] + reader[1]) / FREE_TIER_DOLLARS["memory"] == pytest.approx(1.1799, abs=1e-4)
    assert (memory_part[2] + reader[1]) / FREE_TIER_DOLLARS["memory"] == pytest.approx(1.0063, abs=1e-4)
    room_cpu = (FREE_TIER_SHARE * FREE_TIER_DOLLARS["cpu"] - cpu_part) / _pot(reader_cpu, 0, "job")[0]
    room_memory_2 = (FREE_TIER_SHARE * FREE_TIER_DOLLARS["memory"] - memory_part[2]) / _pot(0, reader_gib, "job")[1]
    assert (round(room_cpu), round(room_memory_2)) == (30_372, 44_160)


# The month as it was measured (Cloud Monitoring, read-only, 6 Nov 2026: run.googleapis.com/container/
# billable_instance_time and cpu/allocation_time, summed by day, UTC): the site's billable seconds and its CPU
# allocation (the startup boosts held in it), and the pre-check's, over the 20 days from 17 Oct to 5 Nov 2026, scaled to
# a 31-day month. Changed on purpose 6 Nov 2026 (fix round, the cost review): the builder took October's sums, but the
# site came up on 12 Oct and the pre-check ran 19 days of October, so the pre-check's month was short by a third. One
# window for both: the site's steady days (its first ones were its busiest: deploys, boosts, the 4 GiB stopgap's
# restarts), with the pre-check at its November pace in it.
MEASURED_DAYS = 20
MEASURED = {"site": (33_692.3, 37_365.4), "precheck": (28_405.3, 28_661.2)}


def test_the_doubled_month_keeps_10_percent_in_hand_on_the_measured_use():
    # 6 Nov 2026 (Noemi's doubling, option A): the brief's 98,000 seconds were for jobs with a pot of their own. In the
    # shared pot, the measured use at today's sizes (the site at 3 GiB, the pre-check at 2 GiB, the reader at 1 GiB)
    # leaves the reader at most 94,353 seconds on the CPU part (the part that binds): 92,000 is 89.0% of it, 73 requests
    # at 21 minutes (39 before). On memory it is 83.5% of the part at 3 GiB and 69.0% at 2 GiB. The last 14 days alone
    # were busier (the reader's room 90,325, so 92,000 is 90.7% there); a busier month is the free-tier guard's to
    # catch: it projects the month from Cloud Monitoring before every read past the first 50,000 seconds and every
    # backfill read. (Until the fix round the test said 92,000 was the most to the thousand on October's use: CPU
    # 89.6%, memory 79.6% and 65.0%.)
    from engine.config import CLOUD_RUN_PRECHECK, CLOUD_RUN_READER, CLOUD_RUN_SITE, CLOUD_RUN_SIZES, \
        FREE_TIER_DOLLARS, FREE_TIER_SHARE, ON_DEMAND_MONTH_SECONDS

    (_, _, site_gib), (_, _, precheck_gib), (_, reader_cpu, reader_gib) = (
        CLOUD_RUN_SIZES[CLOUD_RUN_SITE], CLOUD_RUN_SIZES[CLOUD_RUN_PRECHECK], CLOUD_RUN_SIZES[CLOUD_RUN_READER])
    scale = 31 / MEASURED_DAYS
    (site_billable, site_cpu), (precheck_billable, precheck_cpu) = (
        [value * scale for value in MEASURED[name]] for name in ("site", "precheck"))

    def parts(month_seconds: int, gib: float) -> tuple[float, float]:
        site = _pot(site_cpu, site_billable * gib, "service")
        precheck = _pot(precheck_cpu, precheck_billable * precheck_gib, "job")
        reader = _pot(month_seconds * reader_cpu, month_seconds * reader_gib, "job")
        return (site[0] + precheck[0] + reader[0]) / FREE_TIER_DOLLARS["cpu"], \
            (site[1] + precheck[1] + reader[1]) / FREE_TIER_DOLLARS["memory"]

    assert (round(site_billable), round(site_cpu), round(precheck_billable), round(precheck_cpu)) == (
        52_223, 57_916, 44_028, 44_425)
    cpu, memory = parts(ON_DEMAND_MONTH_SECONDS, site_gib)
    assert cpu < FREE_TIER_SHARE and memory < FREE_TIER_SHARE
    assert (round(cpu, 3), round(memory, 3), round(parts(ON_DEMAND_MONTH_SECONDS, 2)[1], 3)) == (0.89, 0.835, 0.69)
    room = (FREE_TIER_SHARE * FREE_TIER_DOLLARS["cpu"] - _pot(site_cpu, 0, "service")[0]
            - _pot(precheck_cpu, 0, "job")[0]) / _pot(reader_cpu, 0, "job")[0]
    assert round(room) == 94_353 and ON_DEMAND_MONTH_SECONDS == 92_000 < room


def test_the_site_reads_ahead_within_a_third_and_a_bit_of_its_own_free_tier():
    # 14 Oct 2026 (the free-tier redesign): the site is billed only while it answers (request-billed: 180,000
    # vCPU-seconds and 360,000 GiB-seconds free a month). Reading ahead adds at most READ_AHEAD_SECONDS (and a second for
    # the last reads to come back) to each keep-warm ping, every 5 minutes (DEPLOY.md's schedule), on the site's size.
    # Changed on purpose 15 Oct 2026: the site runs at 4 GiB, a stopgap (at 2 GiB it ran out of memory every 20 to 40
    # minutes with ~1,950 threads, the open model and its warmed answers), so reading ahead's GiB-seconds rise from a
    # third of the free tier to 60% at most (214,272 of 360,000); its vCPU-seconds stay under a third. Bringing the
    # site's memory back down is in CLAUDE.md's follow-ups.
    # Changed on purpose 25 Oct 2026 (the verify2 builder, from the review's option (c); reported to Noemi): reading ahead
    # takes 48 reads a ping in 6 seconds instead of 40 in 5 (engine/config.py), so it bills 7 seconds a ping, not 6: at most
    # 62,496 vCPU-seconds a month (35% of the site's 180,000 free, no longer under a third) and, at 4 GiB, 249,984
    # GiB-seconds (69% of 360,000, no longer 60%). Still free, with 65% of the vCPU-seconds and 31% of the GiB-seconds left
    # for answering visitors.
    # Changed on purpose 5 Nov 2026 (the site-memory builder, Noemi's "Let's do A" of 5 Nov 2026): the site runs at 2 GiB again,
    # its memory bounded (engine/tests/test_site_memory.py and DEPLOY.md, The site's memory), so reading ahead bills at most
    # 124,992 GiB-seconds a month (34.7% of 360,000, where 4 GiB billed 249,984, 69%), which frees the site's free GiB-seconds
    # for answering visitors and for reading on demand to be doubled later. Its vCPU-seconds are as they were.
    # Changed on purpose 6 Nov 2026 (after two reviews of that work): the first deploy of this code is at 3 GiB, because the
    # same worst case counted on Cloud Run is about 1,633 MiB, 79.8% of 2 GiB (the on-demand files on its memory disk are
    # no part of a Mac's footprint), and Linux is not measured. Reading ahead then bills at most 187,488 GiB-seconds a month
    # (52.1% of 360,000), so the memory bound is raised from 0.35 to 0.55. The site steps down to 2 GiB (124,992, 34.7%)
    # once Cloud Monitoring's p99 memory stays under about 1.5 GiB (DEPLOY.md, The site's memory), and this bound can then
    # come back down.
    # Changed on purpose 6 Nov 2026 (Noemi's doubling, option A: one shared pot): the same shares, now of the pot's
    # dollars (the site's 180,000 free vCPU-seconds are the pot's $4.32 at the service price, its 360,000 GiB-seconds its
    # $0.90): $1.50 of CPU (34.7%) and $0.47 of memory at 3 GiB (52.1%; $0.31, 34.7%, at 2 GiB). What is left is shared
    # with the jobs (the test above).
    from engine.config import FREE_TIER_DOLLARS

    site = _command(DEPLOY_SH.read_text(encoding="utf-8"), '$GCLOUD run deploy')
    cpu, gib = _size(site)
    seconds = _read_ahead_seconds()
    assert gib == 3
    assert seconds * cpu <= 180_000 * 0.35 and seconds * gib <= 360_000 * 0.55
    assert (seconds * cpu, seconds * gib) == (62_496, 187_488)  # DEPLOY.md's sums
    dollars = _pot(seconds * cpu, seconds * gib, "service")
    assert dollars[0] <= FREE_TIER_DOLLARS["cpu"] * 0.35 and dollars[1] <= FREE_TIER_DOLLARS["memory"] * 0.55
    assert _pot(seconds * cpu, seconds * 2, "service")[1] <= FREE_TIER_DOLLARS["memory"] * 0.35


def test_the_reading_job_may_read_cloud_monitoring_and_knows_its_project():
    # 6 Nov 2026 (the free-tier guard): the reading job reads the month's use from Cloud Monitoring with its own service
    # account (no key file), so the deploy grants that account roles/monitoring.viewer on the project (adding a binding
    # that is there already changes nothing), and the job is told its project. Without either the guard says no.
    script = DEPLOY_SH.read_text(encoding="utf-8")
    grant = _command(script, '$GCLOUD projects add-iam-policy-binding')
    assert '"$PROJECT"' in grant and '--member "serviceAccount:$RUNNER"' in grant
    assert "--role roles/monitoring.viewer" in grant and "--condition=None" in grant
    before = script[:script.index('$GCLOUD projects add-iam-policy-binding')]
    assert before.rstrip().endswith('if [ "$ON_DEMAND" = on ]; then')  # only with on-demand reading on
    assert script.index("roles/monitoring.viewer") < script.index("on_demand_job; fi")
    job = _command(ON_DEMAND_SH.read_text(encoding="utf-8"), '$GCLOUD run jobs deploy')
    assert "CREDIBLE_RECS_GCP_PROJECT=${PROJECT}" in job


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


def test_the_image_cleanup_comes_after_every_job_runs_the_new_image():
    # 16 Oct 2026: revision 60's deploy stopped before the jobs step and the keep-newest-image policy then deleted the
    # image the plan job and the reader still ran ("Image not found" for a day). The policy is applied last, after
    # every job left on another image is moved to the site's.
    script = DEPLOY_SH.read_text(encoding="utf-8")
    cleanup = script.index("set-cleanup-policies")
    assert script.index('run jobs deploy "$JOB"') < cleanup
    assert script.index("on_demand_job; fi") < cleanup
    assert script.index('if [ "$JOB_IMAGE" != "$IMAGE" ]') < cleanup


# --- On-demand reading: off for the interviews (Noemi's decision 6 of 16 Oct 2026), on again by default since 25 Oct 2026 ---
# Changed on purpose, 25 Oct 2026: Noemi approved turning it on again, read by Gemini 3.1 Flash-Lite ("yes to all
# recommendations"). A deploy now has it on unless CREDIBLE_RECS_ON_DEMAND says "off"; the tests below were the switch's
# three tests of 16 Oct (off unless "on"), changed to say the same of "off".

def _on_demand_switch(tmp_path: Path, there: bool, switch: str | None) -> tuple[str, str, list[str]]:
    """on_demand.sh's on_demand_secret run on its own, as deploy.sh runs it, with a made-up gcloud whose `secrets describe`
    finds the Gemini key or not (each call noted in a file; nothing reaches Google) and CREDIBLE_RECS_ON_DEMAND set to
    `switch` (None: not set): what ON_DEMAND became, what it said, and the calls gcloud got."""
    import os
    import subprocess

    calls = tmp_path / "calls"
    gcloud = tmp_path / "gcloud"
    gcloud.write_text(f'#!/bin/sh\necho "$@" >> "{calls}"\nexit {0 if there else 1}\n', encoding="utf-8")
    gcloud.chmod(0o755)
    env = {"PATH": os.environ["PATH"], "GCLOUD": str(gcloud)}
    if switch is not None:
        env["CREDIBLE_RECS_ON_DEMAND"] = switch
    shell = f'set -eu\nPROJECT=made-up\nREGION=europe-west1\n. "{ON_DEMAND_SH}"\non_demand_secret\necho "$ON_DEMAND"\n'
    done = subprocess.run(["sh", "-c", shell], capture_output=True, text=True, check=True, env=env)
    return done.stdout.strip(), done.stderr, calls.read_text().splitlines() if calls.exists() else []


def test_on_demand_reading_is_off_for_a_deploy_that_says_off(tmp_path):
    # Off even with the key there, and the key isn't even looked for. Said once, with the setting that did it.
    state, said, calls = _on_demand_switch(tmp_path, there=True, switch="off")
    assert state == "off" and calls == []
    assert len(said.splitlines()) == 1 and "CREDIBLE_RECS_ON_DEMAND=off" in said


def test_turned_on_it_needs_the_gemini_key_as_before(tmp_path):
    with_key, without_key = tmp_path / "with", tmp_path / "without"
    with_key.mkdir()
    without_key.mkdir()
    assert _on_demand_switch(with_key, there=True, switch="on") == ("on", "", ["secrets describe gemini-key --project made-up"])
    state, said, _ = _on_demand_switch(without_key, there=False, switch="on")
    assert state == "off" and len(said.splitlines()) == 1 and "gemini-key" in said


@pytest.mark.parametrize("switch, on", [("off", False), (None, True), ("on", True)])
def test_switched_off_the_site_and_the_pre_check_get_none_of_its_settings(tmp_path, switch, on):
    # Without CREDIBLE_RECS_ON_DEMAND_BUCKET and _JOB the site never queues a request or starts the reader
    # (engine.on_demand.site_reader_from_env), and answers a product it hasn't read about with the no-threads message.
    import os
    import subprocess

    script = DEPLOY_SH.read_text(encoding="utf-8")
    opening = script[:script.index('HOSTS="${SERVICE}-')]
    gcloud = tmp_path / "gcloud"
    gcloud.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")  # every secret there, every call fine
    gcloud.chmod(0o755)
    env = {"PATH": os.environ["PATH"], "GCLOUD": str(gcloud), **({"CREDIBLE_RECS_ON_DEMAND": switch} if switch else {})}
    shell = opening + 'echo "site:$ON_DEMAND_SITE_VARS"\necho "precheck:$ON_DEMAND_PRECHECK_VARS"\n'
    done = subprocess.run(["sh", "-c", shell], capture_output=True, text=True, check=True, env=env,
                          cwd=make_context.REPO_ROOT)
    site, precheck = done.stdout.splitlines()
    assert ("CREDIBLE_RECS_ON_DEMAND_JOB=" in site) is on and ("CREDIBLE_RECS_ON_DEMAND_BUCKET=" in precheck) is on
    if not on:
        assert (site, precheck) == ("site:", "precheck:")


def test_the_switch_is_one_setting_and_its_default_is_on():
    script = ON_DEMAND_SH.read_text(encoding="utf-8")
    assert 'ON_DEMAND_SWITCH="${CREDIBLE_RECS_ON_DEMAND:-on}"' in script
    deploy_md = (DEPLOY_SH.parent / "DEPLOY.md").read_text(encoding="utf-8")
    assert "CREDIBLE_RECS_ON_DEMAND=off sh deploy/cloudrun/deploy.sh" in deploy_md


def test_the_site_answers_its_own_domain_and_firebase_hostings_addresses(tmp_path):
    # 2 Nov 2026 (Noemi bought crediblepicks.com): visitors reach the service through Firebase Hosting, whose Host
    # header names the service, but the page's Origin (what feedback and the blind test's answers are checked by) names
    # the address the visitor opened, so the site must take those too, or a deploy would drop them again.
    import os
    import subprocess

    script = DEPLOY_SH.read_text(encoding="utf-8")
    opening = script[:script.index("# The pre-check's Bright Data key")]
    gcloud = tmp_path / "gcloud"
    gcloud.write_text('#!/bin/sh\ncase "$*" in *"projects describe"*) echo 123;; *"services describe"*) '
                      'echo https://credible-recs-abc-ew.a.run.app;; esac\nexit 0\n', encoding="utf-8")
    gcloud.chmod(0o755)
    shell = opening + 'echo "$HOSTS"\n'
    done = subprocess.run(["sh", "-c", shell], capture_output=True, text=True, check=True,
                          env={"PATH": os.environ["PATH"], "GCLOUD": str(gcloud)}, cwd=make_context.REPO_ROOT)
    hosts = done.stdout.strip().splitlines()[-1].split(",")
    assert hosts == ["credible-recs-123.europe-west1.run.app", "credible-recs-abc-ew.a.run.app", "crediblepicks.com",
                     "www.crediblepicks.com", "credible-picks.web.app", "credible-picks.firebaseapp.com"]


def test_firebase_hosting_passes_every_request_to_the_service_in_its_region():
    # 2 Nov 2026: crediblepicks.com and credible-picks.web.app are Firebase Hosting's, which hands each request to the
    # Cloud Run service deploy.sh deploys (its default name and region), and www is sent on to the domain itself.
    from deploy.cloudrun import hosting

    script = DEPLOY_SH.read_text(encoding="utf-8")
    assert 'SERVICE="${CREDIBLE_RECS_GCP_SERVICE:-credible-recs}"' in script
    assert 'REGION="${CREDIBLE_RECS_GCP_REGION:-europe-west1}"' in script
    assert hosting.config() == {"rewrites": [{"glob": "**", "run": {"serviceId": "credible-recs",
                                                                   "region": "europe-west1"}}]}
    assert hosting.DOMAINS == {"crediblepicks.com": None, "www.crediblepicks.com": "crediblepicks.com"}
    assert set(hosting.DOMAINS) | {f"{hosting.SITE}.web.app", f"{hosting.SITE}.firebaseapp.com"} <= set(
        script.split('SITE_DOMAINS="${CREDIBLE_RECS_SITE_DOMAINS:-', 1)[1].split("}", 1)[0].split(","))


# --- The pages Hosting's CDN keeps (3 Nov 2026, the launch-load fix): a deploy clears them by releasing Hosting again ---

def test_a_deploy_releases_firebase_hosting_once_the_site_is_deployed_and_before_the_steps_that_can_stop_it():
    # The home page and the How page are kept by Hosting's CDN for up to 10 minutes (engine/web.py, PAGE_CACHE_CONTROL).
    # Firebase's docs: redeploying a site clears all its cached content across the CDN until the next request. So after
    # the new revision serves (`gcloud run deploy` waits for that), Hosting is released again, with the same Python as the
    # script's other steps. It comes before the jobs' steps: the script stops at the first failure (set -e), and a deploy
    # that stopped later would leave the old pages in the CDN.
    script = DEPLOY_SH.read_text(encoding="utf-8")
    release = _command(script, ".venv/bin/python -m deploy.cloudrun.hosting release")
    assert script.index("$GCLOUD run deploy") < script.index(".venv/bin/python -m deploy.cloudrun.hosting release")
    assert script.index(".venv/bin/python -m deploy.cloudrun.hosting release") < script.index("$GCLOUD run jobs deploy")
    assert "set -eu" in script
    # A Hosting problem never stops a deploy (the new site is live by now): it says so in one line, on stderr.
    assert "||" in release and release.split("||", 1)[1].strip().startswith("echo ") and release.endswith(">&2")


@pytest.mark.parametrize("hosting_exit", [0, 1])
def test_a_hosting_release_that_fails_never_stops_the_deploy_and_says_so(tmp_path, hosting_exit):
    import os
    import subprocess

    script = DEPLOY_SH.read_text(encoding="utf-8")
    release = _command(script, ".venv/bin/python -m deploy.cloudrun.hosting release")
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text(f'#!/bin/sh\necho "$@" >> calls.txt\nexit {hosting_exit}\n', encoding="utf-8")
    python.chmod(0o755)
    done = subprocess.run(["sh", "-c", f"set -eu\n{release}\necho carried on\n"], capture_output=True, text=True,
                          env={"PATH": os.environ["PATH"]}, cwd=tmp_path)
    assert done.returncode == 0 and done.stdout.strip() == "carried on"
    assert (tmp_path / "calls.txt").read_text(encoding="utf-8").splitlines() == ["-m deploy.cloudrun.hosting release"]
    assert ("Firebase Hosting wasn't released" in done.stderr) == (hosting_exit != 0)


def test_releasing_hosting_again_and_again_only_makes_the_same_new_version_each_time(monkeypatch, capsys):
    # Safe to run on every deploy: a release adds a version of the same config (every path to the service) and points the
    # site at it; it changes no domain, deletes nothing, and a second one is the same four calls.
    import re

    from deploy.cloudrun import hosting

    calls = []

    def fake_call(method, url, body=None, auth=""):
        calls.append((method, url.replace(hosting.API, ""), body))
        return {"name": f"sites/{hosting.SITE}/versions/v{len(calls)}"} if url.endswith("/versions") else {"name": "r"}

    monkeypatch.setattr(hosting, "_token", lambda: "token")
    monkeypatch.setattr(hosting, "_call", fake_call)
    hosting.release()
    hosting.release()
    capsys.readouterr()

    def shape(batch):
        return [(method, re.sub(r"/v\d+", "/V", url)) for method, url, _ in batch]

    site = f"/sites/{hosting.SITE}"
    one_release = [("POST", f"{site}/versions"), ("POST", f"{site}/versions/V:populateFiles"),
                   ("PATCH", f"{site}/versions/V?update_mask=status"),
                   ("POST", f"{site}/releases?versionName=sites/{hosting.SITE}/versions/V")]
    assert len(calls) == 8 and shape(calls[:4]) == shape(calls[4:]) == one_release
    assert calls[0][2] == calls[4][2] == {"config": hosting.config()}


def test_deploy_md_tells_how_the_pages_are_kept_and_that_a_deploy_releases_hosting():
    deploy_md = (DEPLOY_SH.parent / "DEPLOY.md").read_text(encoding="utf-8")
    section = deploy_md.split("## Firebase Hosting and the domain", 1)[1].split("\n## ", 1)[0]
    assert "public, max-age=60, s-maxage=600" in section and "deploy.sh" in section and "release" in section
    updating = deploy_md.split("## Updating the site", 1)[1].split("\n## ", 1)[0]
    assert "Firebase Hosting" in updating
