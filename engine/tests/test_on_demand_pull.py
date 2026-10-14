"""Baking the threads read on demand into the site's image (Noemi's plan of 14 Oct 2026, part 3): before a deploy builds
the image, `python -m engine.library pull-bucket` brings the bundle's threads into data/library on Noemi's computer;
once the site is deployed, `forget-baked` lets the bundle go of what the image now holds (deploy/cloudrun/deploy.sh
runs both). Every service is a made-up stand-in: no test reaches the network.
"""

import json
import os
import stat

import pytest

from engine import library, on_demand, precheck
from engine.live_check import Bucket
from engine.on_demand import Bundle, Item, entry_for, forget_baked, pull, run_job
from engine.query import parse_query
from engine.tests.fake_google import FakeGoogle
from engine.tests.on_demand_fakes import NOW, FakeArchive, FakeGemini, Ticks, archive, gemini
from engine.tests.test_web import kettle_library

NAME = "credible-test-on-demand"
THREADS = "on_demand/threads.json"


def bucket(google) -> Bucket:
    return Bucket(NAME, request=google, clock=lambda: 0.0, prefix=on_demand.PREFIX)


def read_on_demand(tmp_path, google) -> None:
    """The job has read three teapot threads into the bundle; one more thread waits for Gemini."""
    entry = entry_for(parse_query("teapot for loose leaf tea"), had=0)
    on_demand.QueueStore(bucket(google)).change(lambda q: q.add(entry) and None)
    run_job(bucket(google), tmp_path / "image", archive(tmp_path, FakeArchive()), gemini(FakeGemini()),
            now=lambda: NOW, clock=Ticks(), work_dir=tmp_path / "work")

    def one_waits(bundle: Bundle):
        bundle.threads["1wait01"] = Item(thread="{}", extraction=None, entry=entry.key, product_type="teapot",
                                         added_at=NOW.isoformat())

    on_demand.BundleStore(bucket(google)).change(one_waits)


def test_pulling_brings_the_extracted_threads_into_the_library_and_keeps_its_own_copies(tmp_path):
    google = FakeGoogle()
    read_on_demand(tmp_path, google)
    local = kettle_library(tmp_path)
    (local / "threads" / "1tea002.json").write_text('{"read": "live"}', encoding="utf-8")  # saved and extracted here
    (local / "extracted" / "1tea002.json").write_text('{"by": "claude"}', encoding="utf-8")
    report = pull(bucket(google), local, now=lambda: NOW)
    assert report.pulled == ["1tea001", "1tea003"] and report.kept_local == ["1tea002"] and report.waiting == 1
    assert (local / "threads" / "1tea002.json").read_text(encoding="utf-8") == '{"read": "live"}'
    stored = Bundle.from_json(google.read(NAME, THREADS)).threads["1tea001"]
    assert (local / "threads" / "1tea001.json").read_text(encoding="utf-8") == stored.thread
    assert (local / "extracted" / "1tea001.json").read_text(encoding="utf-8") == stored.extraction
    assert not (local / "threads" / "1wait01.json").exists()  # waiting for Gemini: not pulled
    [logged] = [json.loads(line) for line in (local / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
    assert logged["product_type"] == "teapot" and logged["request"] is None and logged["status"] == "ok"
    assert "teapot" in precheck.requests_to_check(library_dir=local)  # checked ahead on Noemi's computer too


def test_after_the_deploy_the_bundle_lets_go_of_what_the_image_holds(tmp_path):
    google = FakeGoogle()
    read_on_demand(tmp_path, google)
    local = kettle_library(tmp_path)
    pull(bucket(google), local, now=lambda: NOW)

    def the_job_adds_one_meanwhile():
        stored = Bundle.from_json(google.read(NAME, THREADS))
        stored.threads["1new001"] = Item(thread="{}", extraction="{}", entry="kitchen/teapot/", product_type="teapot",
                                         added_at=NOW.isoformat())
        google.put(NAME, THREADS, json.dumps(stored.as_json()).encode())

    google.before_writing[THREADS] = the_job_adds_one_meanwhile
    assert forget_baked(bucket(google), local) == 3
    assert sorted(Bundle.from_json(google.read(NAME, THREADS)).threads) == ["1new001", "1wait01"]


def test_the_library_command_pulls_and_forgets(tmp_path, capsys):
    google = FakeGoogle()
    read_on_demand(tmp_path, google)
    local = kettle_library(tmp_path)
    assert library.main(["pull-bucket"], folder=local, bucket=bucket(google)) == 0
    assert "Pulled 3 thread(s)" in capsys.readouterr().out
    assert library.main(["forget-baked"], folder=local, bucket=bucket(google)) == 0
    assert "let go of 3 thread(s)" in capsys.readouterr().out
    assert library.main(["pull-bucket"], folder=local, bucket=bucket(FakeGoogle(down=True))) == 1


def test_on_noemis_computer_the_token_comes_from_gcloud_and_is_never_printed(tmp_path, monkeypatch, capsys):
    script = tmp_path / "gcloud"
    script.write_text("#!/bin/sh\n[ \"$1 $2\" = \"auth print-access-token\" ] && echo token-from-gcloud\n",
                      encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("GCLOUD", str(script))
    assert on_demand.gcloud_token() == ("token-from-gcloud", 3000.0)
    script.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    with pytest.raises(OSError, match="gcloud auth login"):
        on_demand.gcloud_token()
    assert "token-from-gcloud" not in capsys.readouterr().out
