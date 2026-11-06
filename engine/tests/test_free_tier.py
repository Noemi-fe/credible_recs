"""The free-tier guard (6 Nov 2026, Noemi's doubling of on-demand reading: "make sure ... stays under control"): Google's
free allowance for Cloud Run is one pot in dollars at Tier 1 prices, shared by the site and both jobs, so before any
reading past visitors' first 50,000 seconds a month, and before any backfill read, the reading job asks Cloud Monitoring
what the month has used so far and starts only while the month's projected spend stays under 90% of each part (CPU and
memory). Anything it can't read answers no.

Cloud Monitoring is a made-up stand-in here (FakeMonitoring): no test reaches the network.
"""

import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from engine import config, free_tier
from engine.free_tier import Guard

PROJECT = "made-up-project"
# Moved from midnight to 08:00 UTC on purpose, 6 Nov 2026: the guard's month now starts at 08:00 UTC on the 1st
# (Google's billing month, config.BILLING_MONTH_CUT_HOUR_UTC), and at 08:00 the sums below still have 10 days gone.
NOW = datetime(2026, 11, 11, 8, 0, tzinfo=UTC)  # 10 days of November gone, 20 left
MONTH_START = "2026-11-01T08:00:00Z"
WEEK_START = "2026-11-04T08:00:00Z"
SITE, PRECHECK, READER = config.CLOUD_RUN_SITE, config.CLOUD_RUN_PRECHECK, config.CLOUD_RUN_READER
METRICS = {"billable": "run.googleapis.com/container/billable_instance_time",
           "cpu": "run.googleapis.com/container/cpu/allocation_time",
           "memory": "run.googleapis.com/container/memory/allocation_time"}
UNITS = {"billable": "s", "cpu": "s{CPU}", "memory": "GiBy.s"}

# What the month and the last 7 days used, as Cloud Monitoring adds them up: (billable seconds, vCPU-seconds allocated,
# GiB-seconds allocated). The site ran at 4 GiB at the start of the month and at 3 GiB now (its memory part so far is
# 4 times its billable seconds); its CPU allocation is above its billable time by its startup boosts.
MONTH = {("cloud_run_revision", SITE): (15_000, 16_000, 60_000),
         ("cloud_run_job", PRECHECK): (18_000, 18_100, 54_000),
         ("cloud_run_job", READER): (10_000, 10_050, 10_000)}
WEEK = {("cloud_run_revision", SITE): (10_500, 11_200, 42_000),
        ("cloud_run_job", PRECHECK): (12_600, 12_600, 25_200),
        ("cloud_run_job", READER): (7_000, 7_000, 7_000)}


class FakeMonitoring:
    """Cloud Monitoring's timeSeries.list as it answers the guard's question (summed over the window, grouped by
    service or job): one series per service or job that ran in the window, one point each, and the metric's unit."""

    def __init__(self, month=None, week=None, status=200, units=None, extra=None, starts=(MONTH_START, WEEK_START)):
        self.month, self.week = dict(MONTH if month is None else month), dict(WEEK if week is None else week)
        self.starts = starts  # when the month and the last 7 days begin
        self.status, self.units, self.extra = status, dict(UNITS, **(units or {})), extra or {}
        self.calls: list[str] = []

    def __call__(self, method, url, headers, body=None, timeout=None):
        self.calls.append(url)
        assert method == "GET" and headers["Authorization"] == "Bearer token-1"
        parts = urlsplit(url)
        assert parts.scheme == "https" and parts.netloc == "monitoring.googleapis.com"
        assert parts.path == f"/v3/projects/{PROJECT}/timeSeries"
        query = parse_qs(parts.query)
        if isinstance(self.status, Exception):
            raise self.status
        if self.status != 200:
            return self.status, b'{"error": {"message": "made-up refusal"}}'
        metric, rtype = query["filter"][0].split('metric.type="')[1].split('"')[0], \
            query["filter"][0].split('resource.type="')[1].split('"')[0]
        part = next(name for name, full in METRICS.items() if full == metric)
        window = self.month if query["interval.startTime"][0] == self.starts[0] else self.week  # the last 7 days
        label = "service_name" if rtype == "cloud_run_revision" else "job_name"
        assert query["aggregation.groupByFields"] == [f"resource.label.{label}"]
        series = [{"metric": {"type": metric}, "resource": {"type": rtype, "labels": {label: name, "project_id": PROJECT}},
                   "metricKind": "DELTA", "valueType": "DOUBLE",
                   "points": [{"interval": {"startTime": query["interval.startTime"][0],
                                            "endTime": query["interval.endTime"][0]},
                               "value": {"doubleValue": float(figures[("billable", "cpu", "memory").index(part)])}}]}
                  for (kind, name), figures in window.items() if kind == rtype]
        answer = {"timeSeries": series, "unit": self.units[part], **self.extra} if series else {"unit": self.units[part]}
        return 200, json.dumps(answer).encode()


def a_guard(monitoring, token="token-1", project=PROJECT, clock=None) -> Guard:
    return Guard(project, token=lambda: token, request=monitoring, clock=clock or (lambda: 0.0))


# --- The projection ---

def expected(site_week_billable=10_500, site_week_cpu=11_200, reader_month=None):
    """The guard's sums written out: the month so far (Cloud Monitoring's allocation, never under the billable seconds
    at today's size) plus the 20 days left at the last 7 days' pace at today's sizes, plus the read about to start (21
    minutes of the reader, 1 vCPU and 1 GiB), in dollars at Tier 1 prices."""
    service, job = config.CLOUD_RUN_PRICES["service"], config.CLOUD_RUN_PRICES["job"]
    reader_cpu, reader_gib = (10_050, 10_000) if reader_month is None else (reader_month, reader_month)
    spent_cpu = 16_000 * service["cpu"] + 18_100 * job["cpu"] + reader_cpu * job["cpu"]
    spent_memory = 60_000 * service["memory"] + 54_000 * job["memory"] + reader_gib * job["memory"]
    reader_pace = 1_000 if reader_month is None else 0
    pace_cpu = (max(site_week_cpu, site_week_billable) / 7 * service["cpu"] + 1_800 * job["cpu"]
                + reader_pace * job["cpu"])
    pace_memory = site_week_billable / 7 * 3 * service["memory"] + 1_800 * 2 * job["memory"] + reader_pace * job["memory"]
    extra = 21 * 60
    return (spent_cpu + 20 * pace_cpu + extra * job["cpu"],
            spent_memory + 20 * pace_memory + extra * job["memory"])


def test_the_month_is_what_it_used_so_far_plus_the_rest_at_the_last_weeks_pace_at_todays_sizes():
    verdict = a_guard(FakeMonitoring()).allows(NOW)
    cpu, memory = expected()
    assert verdict.cpu == pytest.approx(cpu) and verdict.memory == pytest.approx(memory)
    assert verdict.cpu == pytest.approx(2.68938) and verdict.memory == pytest.approx(0.68952)  # 62% and 77% of the pot
    assert verdict.yes, verdict.why


def test_the_site_stepping_down_in_memory_counts_its_old_size_so_far_and_its_new_size_from_now():
    # The memory part so far is Cloud Monitoring's allocation (60,000 GiB-seconds: the 4 GiB days), never the billable
    # seconds at today's 3 GiB (45,000); the days left are at today's 3 GiB, never at the week's 4 GiB allocation.
    verdict = a_guard(FakeMonitoring()).allows(NOW)
    at_old_size_from_now = expected()[1] + 20 * (42_000 / 7 - 10_500 / 7 * 3) * config.CLOUD_RUN_PRICES["service"]["memory"]
    assert verdict.memory < at_old_size_from_now


def test_startup_boosts_count_in_the_cpu_part():
    # The site's CPU allocation (16,000 vCPU-seconds) is above its billable time (15,000) by its startup boosts, which
    # Google bills: the CPU part counts the allocation.
    boosted = a_guard(FakeMonitoring()).allows(NOW).cpu
    unboosted = a_guard(FakeMonitoring(month={**MONTH, ("cloud_run_revision", SITE): (15_000, 15_000, 60_000)})).allows(NOW).cpu
    assert boosted - unboosted == pytest.approx(1_000 * config.CLOUD_RUN_PRICES["service"]["cpu"])


def test_a_memory_projection_at_90_percent_or_more_says_no():
    monitoring = FakeMonitoring(week={**WEEK, ("cloud_run_revision", SITE): (21_000, 11_200, 84_000)})
    verdict = a_guard(monitoring).allows(NOW)
    assert verdict.memory == pytest.approx(expected(site_week_billable=21_000)[1])
    assert verdict.memory >= 0.9 * config.FREE_TIER_DOLLARS["memory"]  # 102% of the memory part
    assert not verdict.yes and "memory" in verdict.why


def test_a_cpu_projection_at_90_percent_or_more_says_no():
    monitoring = FakeMonitoring(week={**WEEK, ("cloud_run_revision", SITE): (10_500, 30_000, 42_000)})
    verdict = a_guard(monitoring).allows(NOW)
    assert verdict.cpu == pytest.approx(expected(site_week_cpu=30_000)[0]) == pytest.approx(3.97851, abs=1e-4)
    assert verdict.cpu >= 0.9 * config.FREE_TIER_DOLLARS["cpu"]  # 92% of the CPU part
    assert verdict.memory < 0.9 * config.FREE_TIER_DOLLARS["memory"]
    assert not verdict.yes and "CPU" in verdict.why


def test_the_limits_are_90_percent_of_the_free_dollars():
    assert config.FREE_TIER_SHARE == 0.9
    assert free_tier.limits() == {"cpu": pytest.approx(3.888), "memory": pytest.approx(0.81)}


def test_a_service_or_job_it_has_no_size_for_counts_by_its_allocation():
    # Whatever else runs on Cloud Run in the project shares the pot (a small test service, say): counted from what
    # Cloud Monitoring says it was allocated, its pace too.
    other = ("cloud_run_revision", "made-up-echo")
    plain = a_guard(FakeMonitoring()).allows(NOW)
    with_other = a_guard(FakeMonitoring(month={**MONTH, other: (5, 12, 2.5)}, week={**WEEK, other: (5, 12, 2.5)})).allows(NOW)
    service = config.CLOUD_RUN_PRICES["service"]
    assert with_other.cpu - plain.cpu == pytest.approx(12 * service["cpu"] + 20 * 12 / 7 * service["cpu"])
    assert with_other.memory - plain.memory == pytest.approx(2.5 * service["memory"] + 20 * 2.5 / 7 * service["memory"])


def test_the_reader_not_in_cloud_monitoring_yet_counts_as_the_queues_own_seconds():
    # The reading job asks while it runs, before Cloud Monitoring has its first minutes: its own count of the month's
    # seconds (the queue's) stands in, at its size. Any other missing series is a failure (below).
    month = {key: value for key, value in MONTH.items() if key[1] != READER}
    week = {key: value for key, value in WEEK.items() if key[1] != READER}
    verdict = a_guard(FakeMonitoring(month=month, week=week)).allows(NOW, reader_seconds=4_000)
    assert verdict.cpu == pytest.approx(expected(reader_month=4_000)[0])
    assert verdict.memory == pytest.approx(expected(reader_month=4_000)[1])
    # And the queue's count is a floor under Cloud Monitoring's when Cloud Monitoring is behind.
    behind = a_guard(FakeMonitoring()).allows(NOW, reader_seconds=12_000)
    ahead = a_guard(FakeMonitoring()).allows(NOW, reader_seconds=1_000)
    assert behind.cpu - ahead.cpu == pytest.approx((12_000 - 10_050) * config.CLOUD_RUN_PRICES["job"]["cpu"])


# --- Fail closed: anything it can't read answers no ---

@pytest.mark.parametrize("monitoring, token, project, why", [
    (FakeMonitoring(), None, PROJECT, "token"),
    (FakeMonitoring(), "token-1", None, "project"),
    (FakeMonitoring(status=403), "token-1", PROJECT, "HTTP 403"),
    (FakeMonitoring(status=500), "token-1", PROJECT, "HTTP 500"),
    (FakeMonitoring(status=TimeoutError("timed out")), "token-1", PROJECT, "TimeoutError"),
    (FakeMonitoring(units={"memory": "MiBy.s"}), "token-1", PROJECT, "unit"),
    (FakeMonitoring(units={"cpu": None}), "token-1", PROJECT, "unit"),
    (FakeMonitoring(extra={"nextPageToken": "more"}), "token-1", PROJECT, "page"),
    (FakeMonitoring(month={k: v for k, v in MONTH.items() if k[1] != SITE}), "token-1", PROJECT, SITE),
    (FakeMonitoring(week={k: v for k, v in WEEK.items() if k[1] != SITE}), "token-1", PROJECT, SITE),
    (FakeMonitoring(week={k: v for k, v in WEEK.items() if k[1] != PRECHECK}), "token-1", PROJECT, PRECHECK),
    (FakeMonitoring(month={k: v for k, v in MONTH.items() if k[1] != PRECHECK}), "token-1", PROJECT, PRECHECK),
])
def test_anything_it_cant_read_answers_no(monitoring, token, project, why):
    verdict = Guard(project, token=lambda: token, request=monitoring, clock=lambda: 0.0).allows(NOW)
    assert not verdict.yes and verdict.failed and why in verdict.why
    assert verdict.cpu is None and verdict.memory is None


def test_an_answer_that_isnt_json_answers_no():
    def garbled(method, url, headers, body=None, timeout=None):
        return 200, b"<html>not json</html>"

    verdict = a_guard(garbled).allows(NOW)
    assert not verdict.yes and verdict.failed


def test_a_series_of_another_kind_of_value_answers_no():
    monitoring = FakeMonitoring()
    real = monitoring.__call__

    def distribution(method, url, headers, body=None, timeout=None):
        status, data = real(method, url, headers, body, timeout)
        answer = json.loads(data)
        for series in answer.get("timeSeries", []):
            series["valueType"] = "DISTRIBUTION"
        return status, json.dumps(answer).encode()

    verdict = a_guard(distribution).allows(NOW)
    assert not verdict.yes and verdict.failed


# Fix round, 6 Nov 2026 (the gate's and the reviews' probes): answers Cloud Monitoring is unlikely to give, but each one
# made the guard say yes with what it couldn't read. Each is a failed reading now.

def altered(change, monitoring=None):
    """Cloud Monitoring's answers (FakeMonitoring's), each changed by `change(answer, metric part, resource type,
    window)` before the guard reads it."""
    monitoring = monitoring or FakeMonitoring()

    def ask(method, url, headers, body=None, timeout=None):
        status, data = monitoring(method, url, headers, body, timeout)
        query = parse_qs(urlsplit(url).query)
        metric = query["filter"][0].split('metric.type="')[1].split('"')[0]
        rtype = query["filter"][0].split('resource.type="')[1].split('"')[0]
        window = "month" if query["interval.startTime"][0] == monitoring.starts[0] else "week"
        answer = json.loads(data)
        answer = change(answer, next(part for part, full in METRICS.items() if full == metric), rtype, window)
        return status, answer if isinstance(answer, bytes) else json.dumps(answer).encode()

    return ask


def each_value(new):
    """Every point's value changed to `new` (a value, or a function of the value)."""
    def change(answer, part, rtype, window):
        for series in answer.get("timeSeries", []):
            for point in series["points"]:
                old = point["value"]["doubleValue"]
                point["value"]["doubleValue"] = new(old) if callable(new) else new
        return answer
    return change


def of(name, change_series):
    """`change_series(series)` on `name`'s series only (None leaves it out)."""
    def change(answer, part, rtype, window):
        kept = []
        for series in answer.get("timeSeries", []):
            if next(iter(series["resource"]["labels"].values())) == name:
                series = change_series(series, part, window)
            if series is not None:
                kept.append(series)
        answer["timeSeries"] = kept
        return answer
    return change


@pytest.mark.parametrize("change, why", [
    (each_value("NaN"), "number"),  # the string Cloud Monitoring's JSON could hold
    (each_value(float("nan")), "number"),  # the JSON token NaN
    (each_value(float("inf")), "number"),
    (each_value(lambda value: -value), "number"),
    (each_value(lambda value: -1e12), "number"),
    (each_value("abc"), "can't be read"),
    (of(SITE, lambda series, part, window: {**series, "points": []}), "without points"),
    (of(PRECHECK, lambda series, part, window: {**series, "points": []}), "without points"),
    (of(READER, lambda series, part, window: {**series, "points": []}), "without points"),
    (of(SITE, lambda series, part, window: {k: v for k, v in series.items() if k != "points"}), "without points"),
    # The site's billable seconds alone left out of the last 7 days: its memory pace would be nothing (the code review's
    # probe: memory $0.817, a no, fell to $0.660, a yes).
    (of(SITE, lambda series, part, window: None if (part, window) == ("billable", "week") else series), "billable"),
    (of(PRECHECK, lambda series, part, window: None if part == "memory" else series), "memory"),
    (of(READER, lambda series, part, window: None if part == "cpu" else series), "cpu"),
    (of(SITE, lambda series, part, window: {**series, "metricKind": "GAUGE"}), "not DELTA"),
    (of(SITE, lambda series, part, window: {**series, "resource": {"labels": {}}}), "service_name"),
    (of(READER, lambda series, part, window: {**series, "resource": {"labels": {"project_id": PROJECT}}}), "job_name"),
    (of(SITE, lambda series, part, window: {**series, "points": [{"value": {}}]}), "can't be read"),
    (of(SITE, lambda series, part, window: {**series, "points": [{"value": {"int64Value": "12"}}]}), "can't be read"),
    (lambda answer, part, rtype, window: [answer], "isn't an object"),
    (lambda answer, part, rtype, window: {**answer, "timeSeries": {"made-up": 1}}, "aren't a list"),
    (lambda answer, part, rtype, window: {**answer, "timeSeries": ["made-up"]}, "isn't an object"),
])
def test_an_answer_it_cant_trust_answers_no(change, why):
    verdict = a_guard(altered(change)).allows(NOW)
    assert not verdict.yes and verdict.failed and why in verdict.why, verdict.why
    assert verdict.cpu is None and verdict.memory is None


def test_with_every_answer_whole_the_same_reading_says_yes():
    # The changes above, undone: the stand-in's own answers pass through `altered` unharmed.
    verdict = a_guard(altered(lambda answer, part, rtype, window: answer)).allows(NOW)
    assert verdict.yes and not verdict.failed


def test_values_too_big_to_add_up_answer_no():
    # Each value finite, but their sum in dollars isn't a number the guard can compare: a failed reading, never a yes.
    verdict = a_guard(altered(each_value(1e308))).allows(NOW)
    assert not verdict.yes and verdict.failed and "projection" in verdict.why


def test_a_token_that_cant_be_had_answers_no():
    def broken():
        raise OSError("made-up: the metadata server didn't answer")

    verdict = Guard(PROJECT, token=broken, request=FakeMonitoring(), clock=lambda: 0.0).allows(NOW)
    assert not verdict.yes and verdict.failed and "token" in verdict.why


def test_anything_else_going_wrong_inside_the_guard_answers_no(monkeypatch):
    def broken(*args, **kwargs):
        raise ZeroDivisionError("made-up")

    monkeypatch.setattr(free_tier, "project", broken)
    verdict = a_guard(FakeMonitoring()).allows(NOW)
    assert not verdict.yes and verdict.failed and "ZeroDivisionError" in verdict.why


def test_an_answer_with_an_int64_value_reads_as_a_number():
    # INT64 values come as strings in Cloud Monitoring's JSON; read as numbers, the same reading as the doubles.
    def as_int64(answer, part, rtype, window):
        for series in answer.get("timeSeries", []):
            series["valueType"] = "INT64"
            for point in series["points"]:
                point["value"] = {"int64Value": str(int(point["value"]["doubleValue"]))}
        return answer

    doubles, int64s = a_guard(FakeMonitoring()).allows(NOW), a_guard(altered(as_int64)).allows(NOW)
    assert int64s.yes and int64s.cpu == pytest.approx(doubles.cpu) and int64s.memory == pytest.approx(doubles.memory)


def test_the_pre_check_not_run_yet_in_the_month_is_no_failure():
    # The pre-check runs at 4 am UK time: in the first hours of a month it has no series for the month yet.
    # Changed on purpose 6 Nov 2026 (the month now turns at 08:00 UTC on the 1st, Google's billing month): the 4 am run
    # on the 1st is the month before's, so the first in the month is on the 2nd, 19 or 20 hours after the cut. Its
    # series is required 22 hours after the cut (06:00 UTC on the 2nd), where it was 6 hours after midnight UTC.
    month = {k: v for k, v in MONTH.items() if k[1] != PRECHECK}
    early = datetime(2026, 12, 2, 5, 59, tzinfo=UTC)
    verdict = a_guard(FakeMonitoring(month=month, starts=("2026-12-01T08:00:00Z", "2026-11-25T05:59:00Z"))).allows(early)
    assert not verdict.failed, verdict.why
    later = datetime(2026, 12, 2, 6, 0, tzinfo=UTC)
    verdict = a_guard(FakeMonitoring(month=month, starts=("2026-12-01T08:00:00Z", "2026-11-25T06:00:00Z"))).allows(later)
    assert verdict.failed and PRECHECK in verdict.why
    assert config.FREE_TIER_PRECHECK_MONTH_HOURS == 22


# --- What it asks, and how often ---

def test_one_reading_is_twelve_small_questions_summed_by_service_and_job():
    monitoring = FakeMonitoring()
    a_guard(monitoring).allows(NOW)
    assert len(monitoring.calls) == 12  # 3 metrics x the site's and the jobs' kinds x the month and the last 7 days
    asked = set()
    for url in monitoring.calls:
        query = parse_qs(urlsplit(url).query)
        assert query["aggregation.perSeriesAligner"] == ["ALIGN_SUM"]
        assert query["aggregation.crossSeriesReducer"] == ["REDUCE_SUM"]
        assert query["interval.endTime"] == ["2026-11-11T08:00:00Z"]
        start = datetime.fromisoformat(query["interval.startTime"][0].replace("Z", "+00:00"))
        assert query["aggregation.alignmentPeriod"] == [f"{int((NOW - start).total_seconds())}s"]  # one sum each
        asked.add((query["filter"][0], query["interval.startTime"][0]))
    assert len(asked) == 12
    assert {start for _, start in asked} == {MONTH_START, WEEK_START}


def test_a_reading_is_kept_for_a_while_so_the_job_never_asks_per_item():
    monitoring, now = FakeMonitoring(), [0.0]
    guard = a_guard(monitoring, clock=lambda: now[0])
    guard.allows(NOW)
    now[0] = config.FREE_TIER_READING_SECONDS - 1
    guard.allows(NOW + timedelta(minutes=9), extra_seconds=0)
    assert len(monitoring.calls) == 12
    now[0] = config.FREE_TIER_READING_SECONDS + 1
    guard.allows(NOW + timedelta(minutes=11))
    assert len(monitoring.calls) == 24


def test_a_failed_reading_is_never_kept():
    monitoring = FakeMonitoring(status=503)
    guard = a_guard(monitoring)
    assert not guard.allows(NOW).yes
    monitoring.status = 200
    assert guard.allows(NOW).yes


def test_the_months_readings_stay_far_inside_cloud_monitorings_free_allowance():
    # Cloud Monitoring's read API (https://cloud.google.com/stackdriver/pricing, read 6 Nov 2026): the first million time
    # series returned a month are free per billing account, each call counting its series or one, whichever is more;
    # and 6,000 time-series queries a minute per project (the project's quota, read 6 Nov 2026). Only the reading job
    # asks, at most once per FREE_TIER_READING_SECONDS in a run, and each run counts at least ON_DEMAND_START_SECONDS
    # of the month's ON_DEMAND_MONTH_SECONDS: at worst a run of half a minute every time.
    readings = (config.ON_DEMAND_MONTH_SECONDS // config.ON_DEMAND_START_SECONDS
                + config.ON_DEMAND_MONTH_SECONDS // config.FREE_TIER_READING_SECONDS)
    series_a_call = 3  # the site and one more service, or the two jobs and one more
    assert readings * free_tier.CALLS_A_READING * series_a_call <= 1_000_000 / 5
    assert free_tier.CALLS_A_READING <= 6_000 / 100


def test_from_the_jobs_settings_it_uses_the_jobs_own_token_and_project():
    class Bucket:
        def access_token(self):
            return "token-1"

    guard = free_tier.guard_from_env({"CREDIBLE_RECS_GCP_PROJECT": PROJECT}, Bucket(), request=FakeMonitoring(),
                                     clock=lambda: 0.0)
    assert guard.allows(NOW).yes
    assert not free_tier.guard_from_env({}, Bucket(), request=FakeMonitoring(), clock=lambda: 0.0).allows(NOW).yes


# --- Google's billing month: one cut at 08:00 UTC on the 1st (6 Nov 2026, the second cost review) ---

def test_the_month_window_starts_at_08_00_utc_on_the_1st():
    # Google's billing month runs on US Pacific time (Cloud Billing reports start a day at midnight US and Canadian
    # Pacific Time): it ends at 08:00 UTC on the 1st in winter and 07:00 in summer. The guard's month starts at 08:00
    # UTC, never before Google's, so a moment before the cut on the 1st is still the month before.
    cut = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)
    before = cut - timedelta(minutes=1)
    assert free_tier.month_start(before) == datetime(2026, 11, 1, 8, 0, tzinfo=UTC)
    assert free_tier.next_month(before) == cut
    assert free_tier.month_start(cut) == cut and free_tier.next_month(cut) == datetime(2027, 1, 1, 8, 0, tzinfo=UTC)
    summer = datetime(2026, 7, 1, 7, 30, tzinfo=UTC)  # Google's July began half an hour ago: the guard's hasn't yet
    assert free_tier.month_start(summer) == datetime(2026, 6, 1, 8, 0, tzinfo=UTC)
    monitoring = FakeMonitoring(starts=("2026-11-01T08:00:00Z", "2026-11-24T07:59:00Z"))
    a_guard(monitoring).allows(before)
    starts = {parse_qs(urlsplit(url).query)["interval.startTime"][0] for url in monitoring.calls}
    assert starts == {"2026-11-01T08:00:00Z", "2026-11-24T07:59:00Z"}
    assert config.BILLING_MONTH_CUT_HOUR_UTC == 8


def test_the_sites_month_so_far_is_required_6_hours_after_the_cut():
    cut = datetime(2026, 12, 1, 8, 0, tzinfo=UTC)
    month = {k: v for k, v in MONTH.items() if k[1] != SITE}

    def verdict(when):
        week = free_tier._stamp(when - timedelta(days=7))
        return a_guard(FakeMonitoring(month=month, starts=("2026-12-01T08:00:00Z", week))).allows(when)

    assert not verdict(cut + timedelta(hours=6) - timedelta(minutes=1)).failed
    late = verdict(cut + timedelta(hours=6))
    assert late.failed and SITE in late.why
    assert config.FREE_TIER_MONTH_HOURS == 6


def test_a_reading_missing_a_required_series_is_never_kept_so_the_next_ask_reads_again_and_says_no():
    # The second code review (6 Nov 2026): kept before the check, the next ask in the 10 minutes would project the
    # reading as whole and could say yes (failing open).
    monitoring = FakeMonitoring(month={k: v for k, v in MONTH.items() if k[1] != SITE})
    guard = a_guard(monitoring)
    first = guard.allows(NOW)
    assert first.failed and SITE in first.why and len(monitoring.calls) == 12
    second = guard.allows(NOW + timedelta(minutes=1))
    assert len(monitoring.calls) == 24 and not second.yes and second.failed and SITE in second.why
