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
def _no_real_query_model(monkeypatch):
    # Module 1's open model (Noemi, 11 Oct 2026) is a 1.12 GB file on this machine: tests never load it. A test about
    # the model passes its own stand-in (engine/tests/test_query_model.py).
    from engine import query_model

    monkeypatch.setattr(query_model, "default_query_model", lambda: None)


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
def _no_real_brand_lines(monkeypatch):
    # The same for data/brand_lines.json (12 Oct 2026): it says which real brands sell which kinds of product, so a
    # made-up library's real brand names would be ranked or left out by it. Tests about brand lines pass their own.
    monkeypatch.setattr(pipeline, "load_brand_lines", lambda *args, **kwargs: [])


@pytest.fixture(autouse=True)
def _no_real_product_pages(monkeypatch):
    # The same for data/product_pages.json (15 Oct 2026): real products' pages and makers' images, which the answers
    # link and the page's security policy lets in. Tests about pages and images pass their own.
    from engine import web

    monkeypatch.setattr(pipeline, "load_product_pages", lambda *args, **kwargs: [])
    monkeypatch.setattr(web, "load_product_pages", lambda *args, **kwargs: [])


@pytest.fixture(autouse=True)
def _no_real_lists_written(monkeypatch, tmp_path):
    # Found on 15 Oct 2026: an importer test that named no brand-lines list wrote into the real data/brand_lines.json.
    # The importer (engine/buyable.py) reads its default lists when called; in tests they are empty copies, so a test
    # can never change the committed lists, however it calls the importer.
    from engine import buyable

    for name, key in (("DEFAULT_PRICES", "prices"), ("DEFAULT_PRODUCT_PAGES", "pages"),
                      ("DEFAULT_BRAND_LINES", "brand_lines")):
        copy = tmp_path / f"real-{key}-stand-in.json"
        copy.write_text(f'{{"{key}": []}}\n', encoding="utf-8")
        monkeypatch.setattr(buyable, name, copy)


@pytest.fixture(autouse=True)
def _no_real_summaries(monkeypatch, tmp_path):
    # The one-line summaries (13 Oct 2026) live in data/library/summaries.json, and the sense evaluation reads them from
    # there whatever library it answers on: in tests, from a file that isn't there. Tests about summaries pass their own.
    from engine import sense_eval

    monkeypatch.setattr(sense_eval, "SUMMARIES_FILE", tmp_path / "no summaries here.json")


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    # Found on 10 Oct 2026: a test reached the real Bright Data API through the new "auto" reader and spent 255 of
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


@pytest.fixture(autouse=True)
def _nothing_remembered_from_another_test():
    # Answers keep what they work out between requests (the library, price and facts lookups, product names, comment
    # signs: engine/memo.py; latency, 12 Oct 2026). Each test starts with nothing kept, so none depends on another's.
    from engine import memo

    memo.forget_all()


@pytest.fixture
def skincare_need_rule_set_aside(monkeypatch):
    """Since 15 Oct 2026 (Noemi's decision 3) a skincare pick, or "Also worth a look" item, needs a credible
    recommendation that talks about the request's needs in every reading, as a haircare one does
    (engine/tests/test_skincare_needs.py). The tests that ask for this fixture are about something else (product facts,
    active ingredients, prescription notes, how needs weigh, the wider reading): their made-up comments don't talk about
    their requests' needs, so for them skincare's first reading is as it was before that day."""
    monkeypatch.setattr(pipeline, "NEED_RULE_IN_EVERY_READING",
                        tuple(category for category in pipeline.NEED_RULE_IN_EVERY_READING if category != "skincare"))
