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
