"""Reading ahead on the site (14 Oct 2026, the coordinator's free-tier task; decided by Claude, reported to Noemi).

Why. Before an answer shows a quote, its comment is read live on Reddit's embed page, which answers about 200 reads in
10 minutes from one address, and a quote needs a passing check from the last 48 hours (Noemi's decision of 13 Oct 2026:
"check ahead"). The daily pre-check read those comments as a Cloud Run job, but a job is billed for its whole run,
sleeping included: two thirds of its 87 minutes a day were spent waiting for Reddit's allowance, and with on-demand
reading's job that was 88% of the jobs' free tier, still short of reads. The site is billed only while it answers a
request, and Cloud Scheduler's keep-warm ping asks it every 5 minutes anyway. So the daily job now only works out what
to read (`python -m engine.precheck --plan`), and the site reads it, a few comments at each ping.

- The plan (live_check/plan.json, in the live checks' bucket, written by the daily job): the comments answers would
  show or hold next in line, likeliest to be shown first; the comments the slimmed library keeps that are due to be
  verified (engine/verify.py), longest unverified first; and the checks the job made through Bright Data (comments the
  embed page can't show). Links and those checks only. The site asks for its version at most once an hour
  (config.PLAN_RELOAD_SECONDS), downloads it only when it changed, and takes its checks into its folder.
- At each ping the site reads the plan's comments that are due, in the plan's order: an answer's comment whose last
  read is config.READ_AHEAD_AGAIN_HOURS old, or that has none, so its check never runs out at 48 hours; a comment to
  verify that hasn't been read in the last 48 hours (the job records the read, and lists it again only when it is due
  once more). A comment verified through Bright Data is left to the job, and a page that showed no comment is read
  again only as an answer's comment is, 40 hours on. At most config.READ_AHEAD_PER_PING reads a ping,
  config.READ_AHEAD_PARALLEL at once, none starting config.READ_AHEAD_SECONDS after the ping began, never one that would
  wait for Reddit's allowance, and none while Reddit says fewer than config.READ_AHEAD_KEEP reads are left in its 10
  minutes: those are visitors' answers'.
- At most once an hour (config.BUNDLE_SHARE_SECONDS), when it has read something new, it writes every read of the last
  48 hours in its folder to the bucket's bundle (live_check/bundle.json), only over the version it last read or wrote
  (engine.live_check.LiveChecker.share_bundle: another writer's version is read in first). The daily job starts from
  it and records what each read of a kept comment said; the site reads it as it gets ready after a restart.

So the site asks the bucket about twice an hour, and the rule is unchanged: every quote shown has a passing check from
the last 48 hours, read on Reddit, and a failed or stale one is read again or never shown. Only who reads ahead changed.
"""

import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta

from engine.config import (BUNDLE_SHARE_SECONDS, PLAN_RELOAD_SECONDS, READ_AHEAD_AGAIN_HOURS, READ_AHEAD_KEEP,
                           READ_AHEAD_PARALLEL, READ_AHEAD_PER_PING, READ_AHEAD_SECONDS)
from engine.live_check import MAX_AGE

PLAN_NAME = "plan.json"  # in the live checks' bucket, under live_check/, next to the bundle
_COMMENT_LINK = re.compile(r"^https://(?:www\.|old\.)?reddit\.com/r/[A-Za-z0-9_]+/comments/[A-Za-z0-9]+/\S*$")


@dataclass(frozen=True)
class Plan:
    """What the daily job asks the site to read: links in order, and its checks through Bright Data."""

    written_at: datetime
    answers: tuple[str, ...]  # the comments answers would show or hold next in line, likeliest to be shown first
    verify: tuple[str, ...]  # kept comments due to be verified, longest unverified first
    checks: dict  # its reads through Bright Data, by name, as the bundle holds them


def plan_bytes(answers: list[str], verify: list[str], checks: dict, now: datetime) -> bytes:
    """A plan as the job writes it to the bucket."""
    return json.dumps({"written_at": now.isoformat(), "answers": list(answers), "verify": list(verify),
                       "checks": checks}, ensure_ascii=False).encode("utf-8")


def read_plan(data: bytes | None) -> Plan | None:
    """A plan as written by plan_bytes; None when it can't be read. Only Reddit comment links are kept."""
    try:
        raw = json.loads(data)
        written_at = datetime.fromisoformat(raw["written_at"])
        answers, verify, checks = raw["answers"], raw["verify"], raw.get("checks") or {}
    except (TypeError, ValueError, KeyError):
        return None
    if not isinstance(answers, list) or not isinstance(verify, list) or not isinstance(checks, dict):
        return None
    links = lambda items: tuple(i for i in items if isinstance(i, str) and _COMMENT_LINK.match(i))
    return Plan(written_at, links(answers), links(verify), checks)


@dataclass
class PingReading:
    """What one keep-warm ping read ahead, in counts."""

    due: int = 0  # the plan's comments due now
    read: int = 0  # read now (a page with no comment on it included)
    failed: int = 0  # couldn't be read now (an error, a refusal): due again at the next ping
    fresh: int = 0  # found checked meanwhile (a visitor's answer read it)
    left: int = 0  # due, left for the next pings (this ping's reads, time or Reddit's allowance ran out)
    kept_for_visitors: bool = False  # stopped: Reddit said fewer than READ_AHEAD_KEEP reads are left
    put_off: bool = False  # stopped: the next read would have waited for Reddit's allowance
    new_plan: bool = False  # a new plan was taken in
    shared: int | None = None  # reads written to the bucket's bundle at this ping (None: not written)


class ReadAhead:
    """The site's reads ahead (see the module's docstring) through `checker`, the site's own live checker (an
    engine.live_check.LiveChecker with the bucket), so answers find the checks at once and Reddit's allowance is shared
    with them. `clock`: the server's seconds (time.monotonic), for its hourly steps and each ping's seconds."""

    def __init__(self, checker, clock=time.monotonic, per_ping: int = READ_AHEAD_PER_PING,
                 seconds: float = READ_AHEAD_SECONDS, parallel: int = READ_AHEAD_PARALLEL, keep: int = READ_AHEAD_KEEP,
                 again: timedelta = timedelta(hours=READ_AHEAD_AGAIN_HOURS),
                 reload_seconds: float = PLAN_RELOAD_SECONDS, share_seconds: float = BUNDLE_SHARE_SECONDS):
        self.checker = checker
        self.bucket = getattr(checker, "bucket", None)
        self._clock = clock
        self.per_ping, self.seconds, self.parallel, self.keep, self.again = per_ping, seconds, max(parallel, 1), keep, again
        self.reload_seconds, self.share_seconds = reload_seconds, share_seconds
        self.plan: Plan | None = None
        self._plan_generation: str | None = None
        self._plan_asked_at: float | None = None
        self._shared_at: float | None = None
        self._unshared = 0  # reads made, or taken in from a plan, since the bundle was last written
        # When each of the plan's comments was last read, and how (None: the embed page), as the folder said when last
        # looked: read from the folder as a plan comes in and after each read here, so a ping doesn't read 4,000 files
        # (about 0.4 s). A visitor's read since is found as the read is about to be made ("fresh"): nothing is read.
        self._last: dict[str, tuple[datetime, str | None]] = {}
        self._lock = threading.Lock()  # one ping at a time: a ping arriving meanwhile only says the server is ready

    def on_ping(self) -> PingReading | None:
        """At Cloud Scheduler's keep-warm ping: a new plan when due, the comments due read, the bundle written when due.
        A problem is said where the server runs and never stops the ping. None when another ping is at it."""
        if not self._lock.acquire(blocking=False):
            return None
        try:
            reading = PingReading()
            try:
                reading.new_plan = self.reload_plan_if_due()
                self.read_due(reading)
                reading.shared = self.share_if_due()
            except Exception as error:  # reported where the server runs; answers go on reading what they need
                print(f"Reading ahead stopped at this ping ({type(error).__name__}: {error}).", file=sys.stderr,
                      flush=True)
            if reading.read or reading.failed or reading.shared is not None or reading.new_plan:
                print(report(reading, self.plan), flush=True)
            return reading
        finally:
            self._lock.release()

    def reload_plan_if_due(self) -> bool:
        """The plan's version asked at most once every reload_seconds; downloaded, and its checks taken into the
        folder, only when it changed. Whether a new plan was taken in."""
        if self.bucket is None:
            return False
        now = self._clock()
        if self._plan_asked_at is not None and now - self._plan_asked_at < self.reload_seconds:
            return False
        self._plan_asked_at = now
        generation = self.bucket.generation(PLAN_NAME)
        if generation is None or generation == self._plan_generation:
            return False
        plan = read_plan(self.bucket.get(PLAN_NAME, generation))
        if plan is None:
            return False
        self.plan, self._plan_generation = plan, generation
        self._unshared += self.checker.take_checks(plan.checks)
        self._last = {}
        for url in dict.fromkeys(plan.answers + plan.verify):
            self._look(url)
        return True

    def _look(self, url: str) -> None:
        """The comment's last read, as the folder says now (LiveChecker.last_read), into what this knows."""
        last = self.checker.last_read(url)
        if last is None:
            self._last.pop(url, None)
        else:
            self._last[url] = (last[0], last[2])

    def due_now(self) -> list[str]:
        """The plan's comments due now, in its order (see the module's docstring)."""
        if self.plan is None:
            return []
        now = self.checker.now()

        def last(url):  # within the last 48 hours, or None
            known = self._last.get(url)
            return known if known is not None and now - known[0] < MAX_AGE else None

        due, seen = [], set()
        for url in self.plan.answers:
            read = last(url)
            if url not in seen and (read is None or read[1] is None and now - read[0] >= self.again):
                due.append(url)
            seen.add(url)
        for url in self.plan.verify:
            if url not in seen and last(url) is None:
                due.append(url)
            seen.add(url)
        return due

    def read_due(self, reading: PingReading) -> PingReading:
        """Reads the comments due, `parallel` at a time, within the ping's reads, its seconds and Reddit's allowance."""
        due = self.due_now()
        reading.due = len(due)
        started, done = self._clock(), 0
        with ThreadPoolExecutor(max_workers=self.parallel, thread_name_prefix="read-ahead") as pool:
            while done < len(due):
                if reading.read + reading.failed >= self.per_ping or self._clock() - started >= self.seconds:
                    break
                spare = self.checker.spare()
                if spare is not None and spare < self.keep:
                    reading.kept_for_visitors = True
                    break
                batch = due[done:done + min(self.parallel, self.per_ping - reading.read - reading.failed)]
                outcomes = list(pool.map(self._read_one, batch))
                for url in batch:
                    self._look(url)
                done += len(batch)
                for outcome in outcomes:
                    if outcome == "later":
                        done -= 1  # not read: still due
                    else:
                        setattr(reading, outcome, getattr(reading, outcome) + 1)
                if "later" in outcomes:
                    reading.put_off = True
                    break
        reading.left = len(due) - reading.read - reading.failed - reading.fresh
        self._unshared += reading.read
        return reading

    def _read_one(self, url: str) -> str:
        max_age = self.again if self.plan is not None and url in self.plan.answers else MAX_AGE
        return self.checker.read_if_free(url, max_age)

    def share_if_due(self) -> int | None:
        """Every read of the last 48 hours written to the bucket's bundle, at most once every share_seconds and only
        when something new was read or taken in: how many it holds; None when it wasn't written."""
        if self.bucket is None or not self._unshared:
            return None
        now = self._clock()
        if self._shared_at is not None and now - self._shared_at < self.share_seconds:
            return None
        self._shared_at = now  # tried: again at the hour, whatever happened
        shared = self.checker.share_bundle()
        if shared is not None:
            self._unshared = 0
        return shared


def report(reading: PingReading, plan: Plan | None) -> str:
    """One ping's reads ahead in a line: counts only, never a comment's words."""
    parts = []
    if reading.new_plan and plan is not None:
        parts.append(f"a new plan ({len(plan.answers):,} answers' comments, {len(plan.verify):,} to verify, "
                     f"{len(plan.checks):,} checks through Bright Data)")
    if reading.due or reading.read or reading.failed:
        stopped = ("; stopped to keep Reddit's reads for visitors" if reading.kept_for_visitors else
                   "; stopped: the next read would have waited" if reading.put_off else "")
        failed = f" ({reading.failed} couldn't be read)" if reading.failed else ""
        parts.append(f"{reading.read} read{failed} of {reading.due:,} due, {reading.left:,} left for the next pings"
                     f"{stopped}")
    if reading.shared is not None:
        parts.append(f"{reading.shared:,} reads of the last 48 hours shared through the bucket")
    return "Reading ahead: " + "; ".join(parts) + "."
