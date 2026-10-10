"""The how-we-score page (/how): how an answer is made and scored, in plain words, and the latest evaluation results.

The results come from a made-up eval/metrics.json written to tmp_path (a small, realistic example), so no test reads
the real one or data/.
"""

import json
import re
from pathlib import Path

import pytest

from engine import answer, config, credibility, how_page, metrics, web

EXAMPLE = {
    "measured_on": "2026-10-10",
    "metrics": {
        "quote_verification": {"value": 1.0, "target": 1.0, "count": 87, "out_of": 87, "threads": None},
        "extraction_precision": {"value": 45 / 47, "target": 0.9, "count": 45, "out_of": 47, "threads": 3},
        "extraction_recall": {"value": 1.0, "target": 0.8, "count": 45, "out_of": 45, "threads": 3},
        "voice_agreement": {"value": 0.75, "target": 0.8, "count": 9, "out_of": 12, "threads": 2},  # misses its target
        "evidence_agreement": {"value": 20 / 22, "target": 0.8, "count": 20, "out_of": 22, "threads": 2},
        "blind_test_vs_vetted": {"value": None, "target": 0.6, "count": None, "out_of": None, "threads": None},
        "blind_test_vs_chatgpt": {"value": None, "target": 0.6, "count": None, "out_of": None, "threads": None},
        "cost_per_question_usd": {"value": 0.0, "target": 0.05, "count": None, "out_of": None, "threads": None},
        "ai_quotes_found": {"value": 1.0, "target": None, "count": 2838, "out_of": 2838, "threads": None},
        "request_outcome": {"value": 1.0, "target": None, "count": 30, "out_of": 30, "threads": None},
        "request_product": {"value": 1.0, "target": None, "count": 22, "out_of": 22, "threads": None},
        "request_details": {"value": 21 / 22, "target": None, "count": 21, "out_of": 22, "threads": None},
        "threads_fit": {"value": 19 / 24, "target": None, "count": 19, "out_of": 24, "threads": None},
        "threads_useful": {"value": 23 / 24, "target": None, "count": 23, "out_of": 24, "threads": None},
        "thread_order": {"value": 75 / 79, "target": None, "count": 75, "out_of": 79, "threads": None},
        "name_matching": {"value": 72 / 75, "target": 0.9, "count": 72, "out_of": 75, "threads": None},
    },
    "end_to_end": {"questions": 10, "with_all_picks": 1, "with_a_pick": 8, "picks_wanted": 3, "quotes_shown": 87,
                   "unverified_quotes_shown": 0, "threads_waiting_live_check": 0},
}


def write(tmp_path: Path, data=EXAMPLE) -> Path:
    path = tmp_path / "metrics.json"
    path.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")
    return path


def get_how(tmp_path: Path, monkeypatch, data=EXAMPLE) -> str:
    """GET /how, the way the server answers it, with the metrics file at tmp_path."""
    if data is not None:
        write(tmp_path, data)
    monkeypatch.setattr(web, "METRICS_FILE", tmp_path / "metrics.json")
    status, content_type, body = web.handle_request("/how", tmp_path / "no library")
    assert status == 200 and content_type.startswith("text/html")
    return body.decode("utf-8")


def card(html: str, key: str) -> str:
    """The text of one metric's card."""
    found = re.search(rf'<li class="metric" id="metric-{key}">(.*?)</li>', html, re.DOTALL)
    assert found, f"no card for {key}"
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", found.group(1)))


def text_of(html: str) -> str:
    """The page's visible words, tags and styles removed, spaces collapsed."""
    html = re.sub(r"<style>.*?</style>", " ", html, flags=re.DOTALL)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).replace("&#x27;", "'").replace("&quot;", '"')


# --- The latest evaluation results ---

def test_the_page_is_served_at_how(tmp_path, monkeypatch):
    html = get_how(tmp_path, monkeypatch)
    assert "<title>How we score</title>" in html


def test_the_page_shows_each_metric_from_the_metrics_file(tmp_path, monkeypatch):
    html = get_how(tmp_path, monkeypatch)
    assert "45 out of 47 (96%)" in card(html, "extraction_precision")
    assert "45 out of 45 (100%)" in card(html, "extraction_recall")
    assert "87 out of 87 (100%)" in card(html, "quote_verification")
    assert "9 out of 12 (75%)" in card(html, "voice_agreement")
    assert "20 out of 22 (91%)" in card(html, "evidence_agreement")
    assert "$0.00" in card(html, "cost_per_question_usd")
    assert "2,838 out of 2,838 (100%)" in card(html, "ai_quotes_found")
    assert "72 out of 75 (96%)" in card(html, "name_matching")
    assert "75 out of 79 (95%)" in card(html, "thread_order")
    for key in metrics.METRIC_KEYS:
        card(html, key)  # every metric has its card


def test_each_card_names_its_target(tmp_path, monkeypatch):
    html = get_how(tmp_path, monkeypatch)
    assert "Target: at least 90%" in card(html, "extraction_precision")
    assert "Target: at least 80%" in card(html, "extraction_recall")
    assert "Target: 100%" in card(html, "quote_verification")
    assert "Target: at least 60%" in card(html, "blind_test_vs_chatgpt")
    assert "Target: under $0.05" in card(html, "cost_per_question_usd")
    assert "No target" in card(html, "thread_order")


def test_the_page_says_when_the_numbers_were_last_measured(tmp_path, monkeypatch):
    assert "Last measured on 10 Oct 2026" in text_of(get_how(tmp_path, monkeypatch))


def test_a_value_below_its_target_is_marked_as_missing_it(tmp_path, monkeypatch):
    html = get_how(tmp_path, monkeypatch)
    assert "Misses the target" in card(html, "voice_agreement")  # 75%, target 80%
    assert "Meets the target" not in card(html, "voice_agreement")
    assert "Meets the target" in card(html, "extraction_precision")  # 96%, target 90%
    assert "Meets the target" in card(html, "cost_per_question_usd")  # $0, under $0.05


def test_a_value_exactly_on_its_target_meets_it_and_a_cost_on_its_limit_misses_it(tmp_path, monkeypatch):
    data = json.loads(json.dumps(EXAMPLE))
    data["metrics"]["extraction_precision"].update(value=0.9, count=45, out_of=50)
    data["metrics"]["cost_per_question_usd"]["value"] = 0.05  # the target is "under $0.05"
    html = get_how(tmp_path, monkeypatch, data)
    assert "Meets the target" in card(html, "extraction_precision")
    assert "Misses the target" in card(html, "cost_per_question_usd")


def test_a_metric_not_measured_yet_says_so(tmp_path, monkeypatch):
    html = get_how(tmp_path, monkeypatch)
    for rival in ("blind_test_vs_vetted", "blind_test_vs_chatgpt"):
        assert "Not measured yet" in card(html, rival)
        assert "Meets the target" not in card(html, rival) and "Misses the target" not in card(html, rival)


def test_a_metric_missing_from_the_file_is_not_measured_yet(tmp_path, monkeypatch):
    data = json.loads(json.dumps(EXAMPLE))
    del data["metrics"]["name_matching"]
    assert "Not measured yet" in card(get_how(tmp_path, monkeypatch, data), "name_matching")


def test_the_page_shows_the_end_to_end_counts(tmp_path, monkeypatch):
    words = text_of(get_how(tmp_path, monkeypatch))
    assert "Of our 10 test questions" in words
    assert "1 got a full answer with 3 picks" in words
    assert "8 got at least one pick" in words
    assert "0 quotes failed the word-for-word check" in words


def test_threads_waiting_for_their_check_are_mentioned_only_when_there_are_some(tmp_path, monkeypatch):
    assert "waiting" not in text_of(get_how(tmp_path, monkeypatch))
    data = json.loads(json.dumps(EXAMPLE))
    data["end_to_end"]["threads_waiting_live_check"] = 4
    assert "4 saved threads were waiting for their regular re-check" in text_of(get_how(tmp_path, monkeypatch, data))


def test_the_sample_each_score_was_measured_on_is_said(tmp_path, monkeypatch):
    html = get_how(tmp_path, monkeypatch)
    assert "3 threads we labelled by hand" in card(html, "extraction_precision")
    assert "2 threads we labelled by hand" in card(html, "voice_agreement")


def test_a_missing_metrics_file_gives_a_clear_message_and_status_200(tmp_path, monkeypatch):
    html = get_how(tmp_path, monkeypatch, data=None)
    words = text_of(html)
    assert "No test results to show yet" in words and "eval/metrics.json" in words
    assert "How a product becomes a pick" in words  # the rest of the page is still there
    assert 'class="metric"' not in html


@pytest.mark.parametrize("broken", [
    "{not json",
    json.dumps({"measured_on": "<script>alert(1)</script>", "metrics": {}}),
    json.dumps({"measured_on": "2026-10-10", "metrics": {"extraction_precision": {"value": "<b>high</b>"}}}),
])
def test_a_broken_metrics_file_gives_a_clear_message_and_shows_nothing_from_it(tmp_path, monkeypatch, broken):
    html = get_how(tmp_path, monkeypatch, data=broken)
    assert "couldn't be read" in text_of(html)
    assert "<script>alert" not in html and "<b>high" not in html


def test_new_results_show_without_restarting_the_server(tmp_path, monkeypatch):
    # The brief's edge case: metrics change after a release. The page reads the file each time it is opened.
    assert "45 out of 47" in card(get_how(tmp_path, monkeypatch), "extraction_precision")
    data = json.loads(json.dumps(EXAMPLE))
    data["measured_on"] = "2026-10-17"
    data["metrics"]["extraction_precision"].update(value=0.5, count=24, out_of=48)
    html = get_how(tmp_path, monkeypatch, data)
    assert "24 out of 48 (50%)" in card(html, "extraction_precision")
    assert "Misses the target" in card(html, "extraction_precision")
    assert "Last measured on 17 Oct 2026" in text_of(html)


def test_numbers_on_the_page_match_the_runs_md_cells_for_the_same_run(tmp_path, monkeypatch):
    # The brief's test: "Numbers on the page match eval/RUNS.md". eval/run_eval.py prints the RUNS.md cells from the
    # very numbers it writes to eval/metrics.json; every one of them is on the page.
    html = get_how(tmp_path, monkeypatch)
    page_words = text_of(html).replace(",", "")
    cells = metrics.runs_cells(EXAMPLE)
    fractions = re.findall(r"(\d+)/(\d+)", cells)
    assert len(fractions) >= 12
    for count, out_of in fractions:
        assert f"{count} out of {out_of}" in page_words, f"{count}/{out_of}"
    assert cells.endswith("$0.00") and "$0.00" in page_words


# --- How an answer is made: the explanation, with every number from the code ---

SECTIONS = ["Where the threads come from", "How products and opinions are found", "Who counts as a credible voice",
            "How strong the evidence is", "How a product becomes a pick", "What gets left out", "How well it works"]


def test_the_explanation_comes_in_order(tmp_path, monkeypatch):
    headings = re.findall(r"<h2[^>]*>(.*?)</h2>", get_how(tmp_path, monkeypatch))
    assert [h for h in headings if h in SECTIONS] == SECTIONS


def config_value(name: str):
    """config.NAME, or config.NAME[key] for "NAME.key"."""
    attribute, _, key = name.partition(".")
    value = getattr(config, attribute)
    return value[key] if key else value


def test_the_decided_values_on_the_page_equal_configs(tmp_path, monkeypatch):
    html = get_how(tmp_path, monkeypatch)
    shown = dict(re.findall(r'<span class="config" data-config="([^"]+)">([^<]*)</span>', html))
    for name, text in shown.items():
        value = config_value(name.replace("&#x27;", "'"))
        if text.endswith("%"):
            assert text == f"{value:.0%}", name
        elif isinstance(value, (int, float)):
            assert text == f"{value:,g}", name
        else:
            assert text == str(value), name
    # The values the brief and Noemi decided are all there.
    for name in ("MIN_CREDIBLE_MENTIONS", "MIN_THREADS", "PICKS_SHOWN", "VOICE_VALUE.high", "VOICE_VALUE.medium",
                 "VOICE_VALUE.low", "EVIDENCE_VALUE.long-term use", "EVIDENCE_VALUE.short-term use",
                 "EVIDENCE_VALUE.no first-hand use", "EVIDENCE_HONESTY_BONUS", "VOICE_HIGH_MIN_GOOD_SIGNS",
                 "VOICE_LOW_MIN_RED_FLAGS", "PAID_PROMOTION_RED_FLAGS", "SKIP_MIN_CREDIBLE_WARNINGS",
                 "DISAGREEMENT_MIN_CREDIBLE_WARNINGS", "KIND_LEAD_RATIO", "KIND_BONUS", "LIVE_CHECK_SHOWN_DAYS",
                 "LIBRARY_REFRESH_DAYS", "QUOTE_MAX_WORDS", "EXTRACT_MAX_COMMENTS", "NEW_ACCOUNT_DAYS",
                 "ESTABLISHED_ACCOUNT_YEARS", "VOICE_RECENT_YEARS", "PRICE_MAX_AGE_DAYS", "MIN_QUOTES_PER_PICK",
                 "QUOTES_PER_PICK"):
        assert name in shown, name


def test_a_changed_config_value_changes_the_page(tmp_path, monkeypatch):
    # Nothing is typed into the page: change a decided value and the page follows.
    monkeypatch.setattr(config, "MIN_CREDIBLE_MENTIONS", 7)
    monkeypatch.setattr(config, "VOICE_VALUE", {"high": 1.0, "medium": 0.6, "low": 0.2})
    monkeypatch.setattr(config, "SUBREDDITS", {"skincare": ("MadeUpSkincare",), "kitchen": ("MadeUpKitchen",)})
    words = text_of(get_how(tmp_path, monkeypatch))
    assert "at least 7 credible recommendations" in words
    assert "a high voice counts 5 times as much as a low one" in words
    assert "r/MadeUpSkincare" in words and "r/MadeUpKitchen" in words and "r/AsianBeauty" not in words


def test_the_template_types_no_numbers():
    # Every number on the page comes from engine/config.py or eval/metrics.json, so the page can't drift from the code.
    template = how_page.TEMPLATE.read_text(encoding="utf-8")
    words = re.sub(r"<style>.*?</style>", " ", template, flags=re.DOTALL)
    words = re.sub(r"\{\{[^{}]*\}\}", " ", words)  # the slots the code fills
    words = re.sub(r"<[^>]+>", " ", words)
    assert not re.findall(r"\d", words), re.findall(r".{20}\d.{20}", words)
    for wording in (how_page.GOOD_SIGNS, how_page.RED_FLAGS, how_page.HONESTY_SIGNS, how_page.METRIC_WORDING):
        for text in wording.values():
            assert not re.findall(r"\d", re.sub(r"\{\{[^{}]*\}\}", " ", str(text))), text


def test_the_lists_of_signs_follow_the_code():
    assert list(how_page.GOOD_SIGNS) == list(config.VOICE_SIGN_WEIGHTS)  # every good sign the rules count
    assert set(how_page.RED_FLAGS) <= set(config.VOICE_TAGS) and not set(how_page.RED_FLAGS) & set(config.VOICE_SIGN_WEIGHTS)
    assert list(how_page.HONESTY_SIGNS) == list(credibility.HONESTY_TAGS)
    assert tuple(how_page.METRIC_WORDING) == metrics.METRIC_KEYS


def test_every_need_a_fact_rule_asks_for_has_plain_words():
    asks = {need for rule in config.PRODUCT_FACT_RULES.values() for need in rule["asks"]}
    assert asks <= set(how_page.ASKS_WORDS), asks - set(how_page.ASKS_WORDS)


def test_every_sign_of_voice_and_honesty_is_explained(tmp_path, monkeypatch):
    html = get_how(tmp_path, monkeypatch)
    for tag in list(config.VOICE_SIGN_WEIGHTS) + list(how_page.RED_FLAGS) + list(credibility.HONESTY_TAGS):
        assert f'data-tag="{tag}"' in html, tag


def test_what_gets_left_out_uses_the_answers_own_words(tmp_path, monkeypatch):
    from engine.product_facts import unconfirmed_note

    words = text_of(get_how(tmp_path, monkeypatch))
    assert answer.CAUTION.format(reason=unconfirmed_note(["PFAS"])) in words  # "Note: we couldn't confirm it's PFAS-free."
    for rule in config.PRODUCT_FACT_RULES.values():
        if rule["hard"]:
            assert rule["reason"] in words
    assert answer.SKIP_HEADING in words


# --- Like the search page: same look, phone width, nothing from outside ---

def test_the_page_matches_the_search_pages_look_and_fits_a_phone(tmp_path, monkeypatch):
    html = get_how(tmp_path, monkeypatch)
    search_style = re.search(r"<style>(.*?)</style>", web.PAGE_TEMPLATE.read_text(encoding="utf-8"), re.DOTALL).group(1)
    assert search_style in html  # the search page's own colours, fonts and dark mode
    assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in html
    assert "@media (max-width: 600px)" in html


def test_the_page_loads_nothing_and_runs_nothing(tmp_path, monkeypatch):
    html = get_how(tmp_path, monkeypatch)
    assert not re.search(r"<script|<link\b|<iframe|<img|<object|<embed|@import|url\(", html, re.IGNORECASE)
    assert re.findall(r'href="([^"]*)"', html) == ["/"]  # one link: back to the search
    assert "{{" not in html and "}}" not in html  # every slot filled


def test_the_search_page_links_to_how(tmp_path):
    status, _, body = web.handle_request("/", tmp_path / "no library")
    assert status == 200 and 'href="/how"' in body.decode("utf-8")
