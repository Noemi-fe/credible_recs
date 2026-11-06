"""The free-tier guard (6 Nov 2026, Noemi's doubling of on-demand reading, option A: "make sure ... stays under control").

Google's free allowance for Cloud Run is one pot in dollars at Tier 1 prices, shared by the site and both jobs
(engine/config.py, FREE_TIER_DOLLARS), and the hard caps alone can't keep 10% of it in hand once the reading month is
doubled (engine/tests/test_cloudrun.py). So before any backfill read, and before any visitor read past the first
ON_DEMAND_GUARD_FREE_SECONDS of the month, the reading job asks this guard, which reads what the month has used so far
from Cloud Monitoring and projects the month:

1. What it reads. For the site's kind (Cloud Run revisions, grouped by service) and the jobs' kind (grouped by job), three
   metrics, each summed over two windows: the month so far (Google's billing month, which runs on US Pacific time,
   counted from 08:00 UTC on the 1st: config.BILLING_MONTH_CUT_HOUR_UTC, 6 Nov 2026) and the last FREE_TIER_PACE_DAYS
   days. That is twelve small calls to Cloud Monitoring's read API (timeSeries.list, ALIGN_SUM over the whole window, so
   one point a service or job), with the job's own service account (its access token from the metadata server: no key
   file). The metrics: run.googleapis.com/container/billable_instance_time (seconds), cpu/allocation_time (vCPU-seconds:
   it holds the site's startup boosts, which Google bills) and memory/allocation_time (GiB-seconds).
2. Spent so far, per part. For a service or job it knows (config.CLOUD_RUN_SIZES): the CPU it was allocated, never under
   its billable seconds times its vCPUs now, and the memory it was allocated, never under its billable seconds times its
   GiB now; for the reader, never under the queue's own count of its seconds either (Cloud Monitoring lags a few
   minutes). Anything else (a small test service, say) counts as allocated. Each is priced as a service (request-billed)
   or a job (instance-billed) at Tier 1.
3. The projection. The spent so far, plus the days left in the month at the last 7 days' pace at today's sizes (so a
   service that has just stepped down in memory counts its old size for the days it ran at it, and its new size from
   now), plus the read about to start (its told minutes at the reader's size). For a backfill read the job adds what
   is left of visitors' first ON_DEMAND_GUARD_FREE_SECONDS this month to that read (fix round, 6 Nov 2026): they never
   ask the guard, so the month must have room for them too.
4. The answer: yes only while each part's projection stays under FREE_TIER_SHARE (90%) of the free dollars. No on any
   failure (fail closed): no project, no token, an HTTP error, an answer that isn't JSON, more than one page, a unit or a
   kind of value it doesn't expect, a series without points, a value that isn't a number of 0 or more (NaN, infinity,
   below 0), a service or job in some of the three metrics but not all, a series missing for the site (either window)
   or the pre-check (the last 7 days, and the month once it is FREE_TIER_MONTH_HOURS old for the site and
   FREE_TIER_PRECHECK_MONTH_HOURS for the pre-check, which runs at 4 am UK time, before the month's cut), or a
   projection that isn't a number (fix round, 6 Nov 2026, from the gate's and the reviews' probes).

A reading is kept FREE_TIER_READING_SECONDS (a failed one never), so a run asks at most once per 10 minutes: at worst a
few thousand readings a month, well inside Cloud Monitoring's free million time series a month (test_free_tier.py does
the sums). The guard sees only this project, while Google's pot is per billing account (DECISIONS.md, 6 Nov 2026).
"""

import http.client
import json
import math
import time
import urllib.error
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

from engine.config import (BILLING_MONTH_CUT_HOUR_UTC, CLOUD_RUN_PRECHECK, CLOUD_RUN_PRICES, CLOUD_RUN_READER,
                           CLOUD_RUN_SITE, CLOUD_RUN_SIZES, FREE_TIER_DOLLARS, FREE_TIER_MONTH_HOURS,
                           FREE_TIER_PACE_DAYS, FREE_TIER_PRECHECK_MONTH_HOURS, FREE_TIER_READING_SECONDS,
                           FREE_TIER_SHARE, ON_DEMAND_PRODUCT_MINUTES)
from engine.live_check import BUCKET_TIMEOUT, _http_request

PROJECT_VAR = "CREDIBLE_RECS_GCP_PROJECT"  # the project whose Cloud Run use is read (the reading job's settings)
MONITORING_API = "https://monitoring.googleapis.com/v3/projects/{project}/timeSeries"
METRICS = {"billable": ("run.googleapis.com/container/billable_instance_time", "s"),
           "cpu": ("run.googleapis.com/container/cpu/allocation_time", "s{CPU}"),
           "memory": ("run.googleapis.com/container/memory/allocation_time", "GiBy.s")}
KINDS = {"cloud_run_revision": ("service", "service_name"), "cloud_run_job": ("job", "job_name")}
CALLS_A_READING = len(METRICS) * len(KINDS) * 2  # the month so far and the last 7 days
SHORTEST_WINDOW = timedelta(seconds=60)  # Cloud Monitoring's shortest alignment period: a window is never shorter
VALUE_TYPES = {"DOUBLE": "doubleValue", "INT64": "int64Value"}
TIMEOUT = BUCKET_TIMEOUT * 2


class ReadingFailed(Exception):
    """Cloud Monitoring couldn't be read, or answered something the guard doesn't expect."""


@dataclass(frozen=True)
class Verdict:
    """The guard's answer: `yes` only while both parts' projections stay under their limits; `cpu` and `memory` are the
    month's projected dollars (None when the reading failed)."""

    yes: bool
    why: str
    cpu: float | None
    memory: float | None
    failed: bool = False


@dataclass(frozen=True)
class Use:
    """One service's or job's sums over a window."""

    billable: float = 0.0  # seconds
    cpu: float = 0.0  # vCPU-seconds allocated
    memory: float = 0.0  # GiB-seconds allocated


Reading = dict[tuple[str, str], Use]  # (resource type, service or job name) -> its sums


def limits() -> dict[str, float]:
    """The most each part's projection may reach, in dollars: FREE_TIER_SHARE of the free dollars."""
    return {part: FREE_TIER_SHARE * FREE_TIER_DOLLARS[part] for part in ("cpu", "memory")}


def _stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def month_start(now: datetime) -> datetime:
    """When the month holding `now` began, as the reading job and the guard count Google's billing month (6 Nov 2026):
    BILLING_MONTH_CUT_HOUR_UTC o'clock UTC on the 1st, never earlier than Google's month end (US Pacific time). A moment
    before the cut on the 1st belongs to the month before."""
    cut = timedelta(hours=BILLING_MONTH_CUT_HOUR_UTC)
    return (now.astimezone(UTC) - cut).replace(day=1, hour=0, minute=0, second=0, microsecond=0) + cut


def next_month(now: datetime) -> datetime:
    """When the next month begins: the cut on the next 1st."""
    return (month_start(now) + timedelta(days=32)).replace(day=1)


def month_key(now: datetime) -> str:
    """The month holding `now`, as the reading job's queue keeps it ("2026-11" until the cut on 1 December)."""
    return month_start(now).strftime("%Y-%m")


class Guard:
    """Asks Cloud Monitoring what the month has used, and answers whether one more read keeps the month under 90% of
    each part (see the module's docstring). `token` gives the service account's access token (None: none just now);
    `request` and `clock` (seconds) can be fakes."""

    def __init__(self, project: str | None, token: Callable[[], str | None], request=_http_request,
                 clock=time.monotonic):
        self.project, self._token, self._request, self._clock = project, token, request, clock
        self._kept: tuple[float, datetime, Reading, Reading] | None = None  # (read at, its now, month, week)

    def allows(self, now: datetime, extra_seconds: float = ON_DEMAND_PRODUCT_MINUTES * 60,
               reader_seconds: float = 0.0) -> Verdict:
        """Whether a read of `extra_seconds` (at the reader's size) may start now; `reader_seconds`, the reading job's
        own count of its seconds this month (a floor under Cloud Monitoring's)."""
        try:
            read_on, month, week = self._reading(now)
            cpu, memory = project(month, week, read_on, extra_seconds, reader_seconds)
            if not (math.isfinite(cpu) and math.isfinite(memory)):
                raise ReadingFailed("a projection that isn't a number")
        except ReadingFailed as error:
            return Verdict(False, f"Cloud Monitoring couldn't be read ({error}): no reading starts", None, None,
                           failed=True)
        except Exception as error:  # anything else unexpected answers no too
            return Verdict(False, f"the guard failed ({type(error).__name__}): no reading starts", None, None,
                           failed=True)
        limit = limits()
        shares = {"CPU": (cpu, FREE_TIER_DOLLARS["cpu"], limit["cpu"]),
                  "memory": (memory, FREE_TIER_DOLLARS["memory"], limit["memory"])}
        said = ", ".join(f"{part} ${spent:.2f} ({spent / free:.0%} of the free ${free:.2f})"
                         for part, (spent, free, _) in shares.items())
        over = [part for part, (spent, _, most) in shares.items() if spent >= most]
        if over:
            return Verdict(False, f"the month is projected at {said}: the {' and '.join(over)} part"
                                  f"{'s are' if len(over) > 1 else ' is'} at {FREE_TIER_SHARE:.0%} or more", cpu, memory)
        return Verdict(True, f"the month is projected at {said}", cpu, memory)

    def _reading(self, now: datetime) -> tuple[datetime, Reading, Reading]:
        """The month so far and the last days, kept FREE_TIER_READING_SECONDS; a failed reading is never kept."""
        if self._kept is not None and self._clock() - self._kept[0] < FREE_TIER_READING_SECONDS:
            return self._kept[1:]
        if not self.project:
            raise ReadingFailed(f"no project: {PROJECT_VAR} isn't set")
        try:
            token = self._token()
        except Exception as error:
            raise ReadingFailed(f"no access token ({type(error).__name__})") from None
        if not token:
            raise ReadingFailed("no access token")
        end = now.astimezone(UTC).replace(microsecond=0)
        month = self._window(token, min(month_start(end), end - SHORTEST_WINDOW), end)
        week = self._window(token, end - timedelta(days=FREE_TIER_PACE_DAYS), end)
        _required(month, week, end)
        self._kept = (self._clock(), end, month, week)
        return end, month, week

    def _window(self, token: str, start: datetime, end: datetime) -> Reading:
        """Each service's and job's three sums over [start, end]. One in some of the three metrics but not all is a
        failure: a sum left out would count as nothing (the site without its billable seconds would project no
        memory)."""
        sums: dict[tuple[str, str], dict[str, float]] = {}
        for rtype, (_, label) in KINDS.items():
            for part, (metric, unit) in METRICS.items():
                for name, value in self._series(token, metric, unit, rtype, label, start, end).items():
                    sums.setdefault((rtype, name), {})[part] = value
        for (_, name), parts in sums.items():
            missing = [part for part in METRICS if part not in parts]
            if missing:
                raise ReadingFailed(f"no {' or '.join(missing)} series for {name}, though it has the others")
        return {key: Use(**parts) for key, parts in sums.items()}

    def _series(self, token: str, metric: str, unit: str, rtype: str, label: str, start: datetime,
                end: datetime) -> dict[str, float]:
        """One metric's sum over [start, end] for each service or job of one kind: {name: sum}."""
        query = urlencode([
            ("filter", f'metric.type="{metric}" AND resource.type="{rtype}"'),
            ("interval.startTime", _stamp(start)), ("interval.endTime", _stamp(end)),
            ("aggregation.alignmentPeriod", f"{int((end - start).total_seconds())}s"),
            ("aggregation.perSeriesAligner", "ALIGN_SUM"), ("aggregation.crossSeriesReducer", "REDUCE_SUM"),
            ("aggregation.groupByFields", f"resource.label.{label}")])
        url = f"{MONITORING_API.format(project=self.project)}?{query}"
        try:
            status, data = self._request("GET", url, {"Authorization": f"Bearer {token}"}, None, timeout=TIMEOUT)
        except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as error:
            raise ReadingFailed(f"{type(error).__name__} asking for {metric}") from None
        if status != 200:
            raise ReadingFailed(f"HTTP {status} for {metric}")
        try:
            answer = json.loads(data)
        except (ValueError, TypeError):
            raise ReadingFailed(f"an answer for {metric} that isn't JSON") from None
        if not isinstance(answer, dict):
            raise ReadingFailed(f"an answer for {metric} that isn't an object")
        if answer.get("nextPageToken"):
            raise ReadingFailed(f"more than one page for {metric}")
        if answer.get("unit") != unit:
            raise ReadingFailed(f"{metric} in the unit {answer.get('unit')!r}, not {unit!r}")
        sums: dict[str, float] = {}
        found = answer.get("timeSeries") or []
        if not isinstance(found, list):
            raise ReadingFailed(f"series of {metric} that aren't a list")
        for series in found:
            if not isinstance(series, dict):
                raise ReadingFailed(f"a series of {metric} that isn't an object")
            field = VALUE_TYPES.get(series.get("valueType"))
            if field is None or series.get("metricKind") != "DELTA":
                raise ReadingFailed(f"{metric} as {series.get('metricKind')} {series.get('valueType')}, not DELTA "
                                    "DOUBLE or INT64")
            name = (series.get("resource") or {}).get("labels", {}).get(label)
            if not name:
                raise ReadingFailed(f"a series of {metric} without its {label}")
            points = series.get("points")
            if not points or not isinstance(points, list):  # Cloud Monitoring leaves out a series with nothing in it
                raise ReadingFailed(f"a series of {metric} for {name} without points")
            try:
                values = [float(point["value"][field]) for point in points]
            except (KeyError, TypeError, ValueError):
                raise ReadingFailed(f"a point of {metric} that can't be read") from None
            if not all(math.isfinite(value) and value >= 0 for value in values):  # NaN, infinity or below 0
                raise ReadingFailed(f"a value of {metric} for {name} that isn't a number of 0 or more")
            sums[name] = sums.get(name, 0.0) + sum(values)
        return sums


def _required(month: Reading, week: Reading, now: datetime) -> None:
    """The series that must be there: the site's and the pre-check's in the last days, and in the month so far once the
    month is FREE_TIER_MONTH_HOURS old for the site (before then it may have had no request) and
    FREE_TIER_PRECHECK_MONTH_HOURS old for the pre-check (6 Nov 2026: its 4 am UK run on the 1st comes before the
    month's cut, so its first run in the month is on the 2nd). The reader's may be missing: the queue counts its
    seconds."""
    for name, hours in ((CLOUD_RUN_SITE, FREE_TIER_MONTH_HOURS), (CLOUD_RUN_PRECHECK, FREE_TIER_PRECHECK_MONTH_HOURS)):
        settled = now - month_start(now) >= timedelta(hours=hours)
        windows = [("the last days", week)] + ([("the month so far", month)] if settled else [])
        rtype = next(rtype for rtype, (kind, _) in KINDS.items() if kind == CLOUD_RUN_SIZES[name][0])
        for said, window in windows:
            if (rtype, name) not in window:
                raise ReadingFailed(f"no series for {name} in {said}")


def project(month: Reading, week: Reading, now: datetime, extra_seconds: float = 0.0,
            reader_seconds: float = 0.0) -> tuple[float, float]:
    """The month's projected dollars of each part (CPU, memory): see the module's docstring, points 2 and 3."""
    days_left = (next_month(now) - now).total_seconds() / 86_400
    reader_key = ("cloud_run_job", CLOUD_RUN_READER)
    cpu = memory = 0.0
    for key in dict.fromkeys([*month, *week, reader_key]):
        rtype, name = key
        kind = KINDS[rtype][0]
        size = CLOUD_RUN_SIZES.get(name)
        so_far, lately = month.get(key, Use()), week.get(key, Use())
        if size is not None and size[0] == kind:
            _, vcpus, gib = size
            billable = max(so_far.billable, reader_seconds) if key == reader_key else so_far.billable
            spent = (max(so_far.cpu, billable * vcpus), max(so_far.memory, billable * gib))
            pace = (max(lately.cpu, lately.billable * vcpus) / FREE_TIER_PACE_DAYS,
                    lately.billable * gib / FREE_TIER_PACE_DAYS)
        else:  # not one of ours: as Cloud Monitoring says it was allocated
            spent = (so_far.cpu, so_far.memory)
            pace = (lately.cpu / FREE_TIER_PACE_DAYS, lately.memory / FREE_TIER_PACE_DAYS)
        price = CLOUD_RUN_PRICES[kind]
        cpu += (spent[0] + days_left * pace[0]) * price["cpu"]
        memory += (spent[1] + days_left * pace[1]) * price["memory"]
    _, vcpus, gib = CLOUD_RUN_SIZES[CLOUD_RUN_READER]
    job = CLOUD_RUN_PRICES["job"]
    return cpu + extra_seconds * vcpus * job["cpu"], memory + extra_seconds * gib * job["memory"]


def guard_from_env(environ, bucket, request=_http_request, clock=time.monotonic) -> Guard:
    """The reading job's guard: its project from CREDIBLE_RECS_GCP_PROJECT (deploy/cloudrun/on_demand.sh sets it), its
    token the bucket's (the job's own service account). Without the project it answers no."""
    project = (environ.get(PROJECT_VAR) or "").strip() or None
    return Guard(project, token=bucket.access_token, request=request, clock=clock)
