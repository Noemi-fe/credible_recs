"""On-demand reading from end to end (Noemi's plan of 14 Oct 2026, part 3), with made-up stand-ins for every service and
no network: a visitor asks about a product the library hasn't read about; the site queues it and starts the job; the
job, on a machine of its own, finds and reads the threads in Arctic Shift's archive, has Gemini extract them and keeps
only quotes found word for word, into the bucket; the keep-warm ping brings them into the site; the visitor asks again
and gets picks whose every quote is in its comment and was read live on Reddit's embed page. Then the daily pre-check
covers the product too, and a deploy bakes the threads in and empties the bucket of them.
"""

import json
import shutil
import threading
from urllib.parse import quote

from engine import on_demand, web
from engine.live_check import Bucket, LiveChecker
from engine.on_demand import Bundle, JobStarter, Queue, SiteReader, forget_baked, precheck_types, pull, run_job
from engine.tests.fake_google import FakeGoogle
from engine.tests.on_demand_fakes import (MISQUOTED, NOW, FakeArchive, FakeEmbed, FakeGemini, Ticks, archive, body_of,
                                          gemini)
from engine.tests.test_live_check import Clock
from engine.tests.test_web import kettle_library
from engine.verify_quotes import find_quote

NAME = "credible-test-on-demand"
JOB = "projects/credible-picks/locations/europe-west1/jobs/credible-recs-reader"
REQUEST = "teapot for loose leaf tea"


def test_a_product_not_read_yet_is_queued_read_checked_and_answered_with_verified_quotes(tmp_path, monkeypatch):
    google, ticks, clock, embed = FakeGoogle(), Ticks(), Clock(), FakeEmbed()

    def bucket():
        return Bucket(NAME, request=google, clock=lambda: 0.0, prefix=on_demand.PREFIX)

    image = kettle_library(tmp_path)  # the library baked into the image: two kettle threads
    site_library = tmp_path / "site"
    shutil.copytree(image, site_library)  # each machine starts from the image
    site_bucket = bucket()
    monkeypatch.setattr(web, "on_demand", SiteReader(site_bucket, site_library, job=JobStarter(JOB, site_bucket,
                                                                                                request=google),
                                                     clock=ticks, now=lambda: NOW))
    monkeypatch.setattr(web, "live", LiveChecker(cache_dir=tmp_path / "checks", fetch=embed, clock=clock,
                                                 sleep=clock.sleep))
    monkeypatch.setattr(web, "ready", threading.Event())
    web.ready.set()
    web.clear_answer_cache()

    def ask() -> dict:
        status, _, body = web.handle_request(f"/api/answer?q={quote(REQUEST)}", site_library)
        assert status == 200
        return json.loads(body)

    # 1. The visitor asks: nothing about teapots is saved, so it is queued and the job started at once.
    first = ask()
    assert first["on_demand"]["state"] == "reading" and first["answer"]["picks"] == []
    assert first["on_demand"]["message"].startswith("We haven't read Reddit about teapots yet, so we've started")
    [entry] = Queue.from_json(google.read(NAME, "on_demand/queue.json")).entries
    assert (entry.product_type, entry.needs) == ("teapot", ["loose", "leaf"]) and REQUEST not in json.dumps(
        entry.as_json())
    assert google.jobs_started == [JOB]

    # 2. The job runs on its own machine: the archive's title search finds the threads, Gemini extracts them, every
    #    quote is checked word for word, and they go into the bucket.
    job_library = tmp_path / "job"
    shutil.copytree(image, job_library)
    report = run_job(bucket(), job_library, archive(tmp_path, FakeArchive()), gemini(FakeGemini()),
                     now=lambda: NOW, clock=Ticks(), work_dir=tmp_path / "work")
    assert (report.threads_read, report.extracted, report.quotes_kept, report.quotes_dropped) == (3, 3, 9, 1)
    assert len(Bundle.from_json(google.read(NAME, "on_demand/threads.json")).extracted("teapot")) == 3

    # 3. The keep-warm ping brings them into the site, and the visitor's next ask answers with them.
    ticks.now += 300
    assert web.handle_request("/ready", site_library)[0] == 200
    second = ask()
    assert "on_demand" not in second
    picks = second["answer"]["picks"]
    assert sorted(p["name"] for p in picks) == ["Brown Betty teapot", "Hario Jumping teapot"]
    shown = [q for p in picks for q in p["quotes"]] + [q for item in second["answer"]["worth_a_look"]
                                                       for q in item["quotes"]]
    for shown_quote in shown:  # word for word in its comment, and read live on the embed page before it was shown
        assert find_quote(body_of(shown_quote["comment_id"]), shown_quote["text"]) is not None
        assert any(f"/comment/{shown_quote['comment_id']}/" in url for url in embed.asked)
    assert MISQUOTED[1] not in json.dumps(second)  # the quote Gemini got wrong is never shown
    assert web._answers  # a real answer now: remembered

    # 4. The daily pre-check, on its own machine, takes the threads in and checks the teapot answer ahead.
    precheck_library = tmp_path / "precheck"
    shutil.copytree(image, precheck_library)
    assert precheck_types({on_demand.BUCKET_VAR: NAME}, precheck_library, bucket=bucket()) == ["teapot"]
    assert (precheck_library / "threads" / "1tea001.json").is_file()

    # 5. A deploy bakes them into the image and the bucket lets them go.
    noemis_library = tmp_path / "noemi"
    shutil.copytree(image, noemis_library)
    assert pull(bucket(), noemis_library, now=lambda: NOW).pulled == ["1tea001", "1tea002", "1tea003"]
    assert forget_baked(bucket(), noemis_library) == 3
    assert Bundle.from_json(google.read(NAME, "on_demand/threads.json")).threads == {}
    web.clear_answer_cache()
