"""Stand-ins for Google Cloud and Reddit, so the site can be run locally the way it runs on Cloud Run with nothing leaving
this computer: a bucket that is a folder, and a Reddit whose embed page for a comment is the comment's saved text."""
import html
import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path


class FakeBucket:
    """engine.live_check.Bucket's methods, on a local folder (the object is <folder>/<prefix><name>)."""

    CHANGED = "changed"

    def __init__(self, folder, name="fake-bucket", prefix="live_check/"):
        self.folder, self.name, self.prefix = Path(folder), name, prefix
        self.problems = 0
        self._lock = threading.Lock()

    def _path(self, name):
        return self.folder / (self.prefix + name)

    def generation(self, name):
        try:
            return str(os.stat(self._path(name)).st_mtime_ns)
        except OSError:
            return None

    def lookup(self, name):
        return True, self.generation(name)

    def get(self, name, generation=None):
        try:
            return self._path(name).read_bytes()
        except OSError:
            return None

    def put(self, name, data):
        path = self._path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return True

    def put_if(self, name, data, generation):
        with self._lock:
            now = self.generation(name)
            if (generation or None) != now:
                return self.CHANGED
            self.put(name, data)
            return self.generation(name)


def fake_reddit(pages_dir):
    """A `fetch` for engine.live_check.LiveChecker: the embed page of a comment shows the comment's text, kept in a folder
    apart from the site's own (pages_dir), so a read 'on Reddit' finds what the site's folder of saved checks does not hold."""
    from engine.live_check import _entry_name

    def fetch(url, headers):
        try:
            entry = json.loads((Path(pages_dir) / _entry_name(url)).read_bytes())
            text = entry["text"]
        except (OSError, ValueError, KeyError):
            return 404, b"", {}
        if text is None:
            return 200, b"<html></html>", {}
        page = f'<div class="text-14"><div class="inline-block">{html.escape(text)}</div></div>'
        return 200, page.encode("utf-8"), {}

    return fetch


def fake_live(cache_dir, bucket, pages_dir=None, in_memory=False):
    from engine.live_check import LiveChecker

    extra = {"in_memory": True} if in_memory else {}
    return LiveChecker(cache_dir=Path(cache_dir), fetch=fake_reddit(pages_dir or cache_dir), min_interval=0.0, burst=100000,
                       refill=0.0001, bucket=bucket, **extra)
