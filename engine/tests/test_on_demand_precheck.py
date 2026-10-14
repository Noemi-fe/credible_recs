"""The daily pre-check covers the products read on demand too (Noemi's plan of 14 Oct 2026, part 3): it takes the
bundle's threads into its library folder as it starts, and adds the queue's product types to the requests whose
answers it checks ahead, so a visitor coming back for one finds its quotes already checked. Every service is a made-up
stand-in: no test reaches the network.
"""

from engine import on_demand, precheck
from engine.live_check import Bucket
from engine.on_demand import entry_for, run_job
from engine.query import parse_query
from engine.tests.fake_google import FakeGoogle
from engine.tests.on_demand_fakes import (NOW, FakeArchive, FakeEmbed, FakeGemini, Ticks, archive, comment_url,
                                          gemini)
from engine.tests.test_precheck import REQUEST, live_checker
from engine.tests.test_web import kettle_library

NAME = "credible-test-on-demand"
ENV = {on_demand.BUCKET_VAR: NAME}


def read_teapots(tmp_path, google) -> None:
    def bucket():
        return Bucket(NAME, request=google, clock=lambda: 0.0, prefix=on_demand.PREFIX)

    entry = entry_for(parse_query("teapot for loose leaf tea"), had=0)
    on_demand.QueueStore(bucket()).change(lambda q: q.add(entry) and None)
    run_job(bucket(), tmp_path / "image", archive(tmp_path, FakeArchive()), gemini(FakeGemini()), now=lambda: NOW,
            clock=Ticks(), work_dir=tmp_path / "work")


def test_the_pre_check_takes_in_the_threads_read_on_demand_and_checks_their_answers_ahead(tmp_path):
    google = FakeGoogle()
    read_teapots(tmp_path, google)
    library = kettle_library(tmp_path)
    bucket = Bucket(NAME, request=google, clock=lambda: 0.0, prefix=on_demand.PREFIX)
    types = on_demand.precheck_types(ENV, library, bucket=bucket)
    assert types == ["teapot"] and (library / "threads" / "1tea001.json").is_file()
    candidates = precheck.comments_to_check(["teapot"], library_dir=library,
                                            checker=live_checker(tmp_path, FakeEmbed()), profiles=None)
    assert comment_url("1tea001", "t1a") in {c.url for c in candidates}


def test_the_daily_command_adds_the_queues_products_to_its_requests(monkeypatch):
    given = {}
    monkeypatch.setattr(precheck, "requests_to_check", lambda: [REQUEST, "teapot"])
    monkeypatch.setattr(precheck.on_demand, "precheck_types", lambda environ, library_dir: ["teapot", "air fryer"])
    monkeypatch.setattr(precheck.pipeline, "cached_profiles", lambda: None)
    monkeypatch.setattr(precheck, "run", lambda requests, limit, dry_run, library_dir, checker, profiles:
                        given.setdefault("requests", requests) and 0)
    assert precheck.main(["--dry-run"]) == 0
    assert given["requests"] == [REQUEST, "teapot", "air fryer"]  # each once, after the usual ones


def test_without_the_bucket_the_pre_check_is_as_before(tmp_path):
    assert on_demand.precheck_types({}, tmp_path) == []
