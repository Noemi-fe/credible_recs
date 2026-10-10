"""Settings shared by every test.

Answers only quote threads checked live on Reddit in the last 14 days (engine.pipeline; Noemi's decision of 9 Oct
2026), judged on today's date. The made-up threads the tests use are dated October 2026 (engine/tests/factories.py:
collected on 6 Oct 2026), so on the real calendar they would stop counting after 20 Oct 2026 and tests would start
failing for no reason. So every test runs with the pipeline's "today" set to 9 Oct 2026, the day this rule was added;
a test that is about dates passes its own `today`, or sets engine.pipeline._today itself.
"""

from datetime import date

import pytest

from engine import pipeline

TESTS_TODAY = date(2026, 10, 9)


@pytest.fixture(autouse=True)
def _pipeline_today_is_9_october_2026(monkeypatch):
    monkeypatch.setattr(pipeline, "_today", lambda: TESTS_TODAY)


@pytest.fixture(autouse=True)
def _no_real_price_list(monkeypatch):
    # The pipeline reads data/prices.json when a test passes no `prices`. That real list holds real products (since
    # 9 Oct 2026 some marked not sold in the UK), so a made-up product with a similar name would be left out for a
    # reason that has nothing to do with the test. Tests about prices pass their own list.
    monkeypatch.setattr(pipeline, "load_prices", lambda *args, **kwargs: [])


@pytest.fixture(autouse=True)
def _no_real_product_facts(monkeypatch):
    # The same for data/product_facts.json (9 Oct 2026): tests about facts pass their own.
    monkeypatch.setattr(pipeline, "load_product_facts", lambda *args, **kwargs: [])


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    # Found on 11 Oct 2026: a test reached the real Bright Data API through the new "auto" reader and spent 255 of
    # Noemi's records. Every client (Bright Data, Arctic Shift, Parse, Reddit's embed page) goes through
    # urllib.request.urlopen, so no test may call it: a test that does fails loudly instead of spending anything.
    import urllib.request
    from urllib.parse import urlparse

    real_urlopen = urllib.request.urlopen

    def refuse(request, *args, **kwargs):
        url = request.full_url if isinstance(request, urllib.request.Request) else str(request)
        if urlparse(url).hostname in ("127.0.0.1", "localhost"):  # the local demo server's own tests
            return real_urlopen(request, *args, **kwargs)
        raise RuntimeError(f"a test tried to reach the network ({urlparse(url).hostname}): give the client a fake "
                           "fetch instead")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)


@pytest.fixture(autouse=True)
def _no_real_bright_data_or_outage_memo(monkeypatch, tmp_path):
    # The same incident: the test went through the library's default source, which built a real Bright Data client
    # (whose answers were in the real cache) and read the real "Arctic Shift is down" memo. A test that needs a Bright
    # Data client gives its own fake (monkeypatching library.BrightDataClient), and the memo is a temporary file.
    from engine import library

    def refuse(*args, **kwargs):
        raise RuntimeError("a test tried to build a real Bright Data client: monkeypatch library.BrightDataClient")

    monkeypatch.setattr(library, "BrightDataClient", refuse)
    monkeypatch.setattr(library, "ARCHIVE_DOWN_MEMO", tmp_path / "arctic_shift_down.json")
