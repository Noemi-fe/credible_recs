"""The how-we-score page (/how on the local demo, engine/web.py): how an answer is made and scored, in plain words,
and the latest evaluation results (docs/brief.md, workstream 5: "a static page with the latest evaluation results").

How it stays true:
- The explanation is engine/templates/how.html. No number is typed into it: every number is a slot filled here from
  engine/config.py (the decided values), engine/answer.py (the answer's own words) or eval/metrics.json. A test fails
  if a digit is typed into the template, and another changes a config value and checks the page follows.
- The results are read from eval/metrics.json each time the page is opened (engine/metrics.py), so a new evaluation
  run shows without restarting the server (the brief's edge case: "metrics change after a release"). eval/run_eval.py
  prints the same numbers as cells for eval/RUNS.md, so the page and the log show one run's numbers.
- Each result says plainly whether it meets its target, misses it, or isn't measured yet.
- When eval/metrics.json is missing or can't be read, the page says so where the results would be; the rest of the
  page is still shown.

Everything put into the page is escaped (html.escape), the numbers from eval/metrics.json included. The page has no
script and loads nothing: its styles are the search page's own (copied in from engine/templates/search.html when the
page is made, so both look alike), plus a few of its own.

Wording: decided by Claude, 10 Oct 2026 (Noemi asked Claude to decide wording and report it). The explanation is in
the template; the words for each listed sign and each test result are below.
"""

import html
import re
from pathlib import Path

from engine import answer, config
from engine.metrics import HEADLINE_KEYS, LOWER_IS_BETTER, METRICS_FILE, OTHER_KEYS, MetricEntry, MetricsError, load_metrics
from engine.product_facts import unconfirmed_note

TEMPLATE = Path(__file__).resolve().parent / "templates" / "how.html"
SEARCH_TEMPLATE = Path(__file__).resolve().parent / "templates" / "search.html"

# The good signs the rules count towards a high voice (engine/credibility.py), in config.VOICE_SIGN_WEIGHTS' order.
# Each slot is filled as in the template. A test checks this list is exactly the rules' good signs.
GOOD_SIGNS: dict[str, str] = {
    "established member": "<strong>Been around:</strong> their account is at least {{config:ESTABLISHED_ACCOUNT_YEARS}} "
                          "years old and they take part a lot (at least {{config:ESTABLISHED_MIN_KARMA}} karma, the "
                          "points Reddit gives for upvotes).",
    "well-regarded account": "<strong>Well liked:</strong> people usually upvote what they write, at least "
                             "{{config:WELL_REGARDED_KARMA_PER_CONTRIBUTION}} karma for each comment or post.",
    "expert flair": "<strong>Expert flair:</strong> the label next to their name in that community says they do it for a "
                    "living, like dermatologist or chef. Anyone can type a flair, so it's a claim, not proof.",
    "well upvoted": "<strong>Well upvoted:</strong> the comment scored higher than "
                    "{{config%:WELL_UPVOTED_SHARE_BEATEN}} of the other comments in its thread.",
    "replies agree": "<strong>Backed up:</strong> other people replied to say they agree.",
    "recent": "<strong>Recent:</strong> written in the last {{config:VOICE_RECENT_YEARS}} years.",
    "enthusiast": "<strong>Knows the topic:</strong> uses at least {{config:ENTHUSIAST_MIN_TERMS}} expert words for it, "
                  "like “gyuto” for knives or “niacinamide” for skincare.",
}
# The red flags the rules count (engine/credibility.py), each one of config.VOICE_TAGS.
RED_FLAGS: dict[str, str] = {
    "new account": "<strong>Brand-new account:</strong> less than {{config:NEW_ACCOUNT_DAYS}} days old when they wrote "
                   "the comment.",
    "low karma for its activity": "<strong>Few upvotes for how much they write:</strong> under "
                                  "{{config:LOW_KARMA_PER_CONTRIBUTION}} karma for each comment or post.",
    "salesy language": "<strong>Sounds like an advert:</strong> “buy now”, “link in bio”, “use my code”.",
    "promotes one brand": "<strong>Works for a brand:</strong> they say they work for, own or represent one.",
    "downvoted": "<strong>Downvoted:</strong> more people voted the comment down than up.",
}
# The signs of honesty that add to the evidence (engine/credibility.py, HONESTY_TAGS), in that order.
HONESTY_SIGNS: dict[str, str] = {
    "mentions flaws": "they mention its flaws, not just the good bits;",
    "compares alternatives": "they compare it with other products they've used;",
    "specific details": "they give specific details: sizes, settings, how it broke.",
}
# What a request asks for, in words that fit "you ask for ..." (the "asks" of config.PRODUCT_FACT_RULES).
ASKS_WORDS: dict[str, str] = {
    "beginner": "something for a beginner",
    "sensitive": "something for sensitive skin",
    "gentle": "something gentle",
    "fragrance-free": "fragrance-free",
    "no white cast": "no white cast",
    "PFAS-free": "PFAS-free",
    "non-stick": "non-stick",
    "plastic-free": "plastic-free",
    "induction-compatible": "something that works on induction",
    "oily": "something for oily skin",
    "dry": "something for dry skin",
    "acne-prone": "something for acne-prone skin",
}
# Each result of eval/metrics.json: its name and what it measures (engine/metrics.py, METRIC_KEYS, in that order).
METRIC_WORDING: dict[str, tuple[str, str]] = {
    "quote_verification": ("Every quote checked word for word",
                           "Of the quotes shown in the answers to our test questions, the share that code found word "
                           "for word in their comment."),
    "extraction_precision": ("The products the AI finds are right",
                             "Of the recommendations and warnings the AI noted, the share we noted too when we read the "
                             "same comments ourselves."),
    "extraction_recall": ("The AI misses few products",
                          "Of the recommendations and warnings we noted by hand, the share the AI found too."),
    "voice_agreement": ("Trusting the right writers",
                        "Of the writers we rated high or low by hand, the share the rules didn't put at the opposite "
                        "end. Trusting a seller or ignoring an expert is the costly mistake."),
    "evidence_agreement": ("Knowing who has really used it",
                           "Of the mentions we rated long-term use or no first-hand use by hand, the share the rules "
                           "didn't put at the opposite end."),
    "blind_test_vs_vetted": ("Preferred over Vetted",
                             "In a blind test with the names hidden, how often people who care about skincare or "
                             "kitchen gear trust our answer more than Vetted's."),
    "blind_test_vs_chatgpt": ("Preferred over ChatGPT",
                              "In a blind test with the names hidden, how often people who care about skincare or "
                              "kitchen gear trust our answer more than ChatGPT's."),
    "cost_per_question_usd": ("Cost per question",
                              "What we pay for paid services to answer one question. The AI reads the threads ahead of "
                              "time, in batches under a flat subscription, and the data services we use are on free "
                              "plans, so answering itself makes no paid calls."),
    "ai_quotes_found": ("Quotes the AI copied exactly",
                        "Of all the quotes the AI copied from the saved threads, the share code found word for word. "
                        "The rest are thrown away and never shown."),
    "request_outcome": ("Understanding the request",
                        "Of our test requests, the share it handled the right way: answer it, ask one question first, "
                        "or say it's outside skincare and kitchen."),
    "request_product": ("Spotting the product",
                        "Of the clear test requests, the share where it read the right kind of product (a kettle, a "
                        "sunscreen)."),
    "request_details": ("Spotting the details",
                        "Of the clear test requests, the share where it read every detail right: budget, skin type, "
                        "size, SPF and how long it should last."),
    "threads_fit": ("Threads that fit the question",
                    "Of the threads chosen first for each test question, the share that fit it exactly: buying advice "
                    "for that very need."),
    "threads_useful": ("Useful threads",
                       "Of the same threads, the share that are at least useful: real experience with that kind of "
                       "product."),
    "thread_order": ("Useful threads first",
                     "Of the pairs of a useful and an off-topic thread, the share where the useful one is ranked "
                     "higher."),
    "name_matching": ("Telling products apart",
                      "Of pairs of product names we labelled by hand, the share where it says rightly whether they're "
                      "the same product."),
}

MEASURED_ON = "Last measured on {date}."
TARGETS_HEADING = "The targets we set"
OTHER_HEADING = "Other checks"
QUESTIONS_HEADING = "Our test questions"
QUESTIONS = ("Of our {questions} test questions (the ones real testers will judge in the blind test), {full} got a full "
             "answer with {picks_wanted} picks and {some} got at least one pick. Those answers showed {shown}, and "
             "{unverified} failed the word-for-word check.")
WAITING = ("{n} saved threads were waiting for their regular re-check on Reddit, so these answers couldn't use them.")
SAMPLE = "Measured on {threads} threads we labelled by hand."
MEETS, MISSES, NOT_MEASURED, NO_TARGET = "Meets the target", "Misses the target", "Not measured yet", "No target"
NO_RESULTS = ("No test results to show yet: the results file (eval/metrics.json) isn't there. It is written each time "
              "the evaluation runs.")
BROKEN_RESULTS = "The test results file (eval/metrics.json) couldn't be read, so no numbers are shown here."
# How many of config.OTHER_TYPE_WORDS the page names as examples.
OTHER_TYPE_EXAMPLES = 5

_SLOT = re.compile(r"\{\{([^{}]+)\}\}")


def page(metrics_path: Path = METRICS_FILE) -> str:
    """The whole page, with the decided values from config and the results from `metrics_path`, read now."""
    slots = {
        "search_page_style": _search_page_style(),
        "communities": _communities(),
        "good_signs": _sign_list(GOOD_SIGNS),
        "red_flags": _sign_list(RED_FLAGS),
        "honesty_signs": _sign_list(HONESTY_SIGNS),
        "hard_rules": _hard_rules(),
        "evaluation": evaluation_section(metrics_path),
    }
    texts = {
        "medium_red_flags": _medium_red_flags(),
        "voice_ratio": _number(config.VOICE_VALUE["high"] / config.VOICE_VALUE["low"]),
        "long_term": _long_term(),
        "example_strong": _points(config.VOICE_VALUE["high"] * config.EVIDENCE_VALUE["long-term use"]),
        "example_weak": _points(config.VOICE_VALUE["medium"] * config.EVIDENCE_VALUE["short-term use"]),
        "credible_voices": " or ".join(config.CREDIBLE_VOICES),
        "credible_evidence": " or ".join(config.CREDIBLE_EVIDENCE),
        "skip_heading": answer.SKIP_HEADING,
        "mixed_opinions": answer.DISAGREEMENT.split(":")[0],
        "other_type_words": ", ".join(config.OTHER_TYPE_WORDS[:OTHER_TYPE_EXAMPLES]) + " and so on",
        "brand_pick_example": config.BRAND_PICK_NAME.format(
            brand="Lodge", products=config.PRODUCT_TYPE_PLURALS["cast iron skillet"]),
        "default_currency": answer.CURRENCY_SIGNS.get(config.BUDGET_DEFAULT_CURRENCY, config.BUDGET_DEFAULT_CURRENCY),
        "soft_note_example": _soft_note_example(),
        "unconfirmed_example": answer.CAUTION.format(reason=unconfirmed_note(["PFAS"])),
    }
    return fill(TEMPLATE.read_text(encoding="utf-8"), texts, slots)


def fill(template: str, texts: dict[str, str], html_parts: dict[str, str] | None = None) -> str:
    """Fills every {{slot}}: "config:NAME" (or "config:NAME.key" for one value of a dict) with that config value,
    "config%:NAME" with it as a percentage, a name in `texts` with that text, escaped, and a name in `html_parts` with
    that piece of page, already built (and escaped) by the code. A slot with no value is an error, never left blank."""
    html_parts = html_parts or {}

    def value_of(match: re.Match) -> str:
        name = match.group(1).strip()
        if name.startswith(("config:", "config%:")):
            kind, _, setting = name.partition(":")
            return _config_span(setting, percent=kind == "config%")
        if name in html_parts:
            return html_parts[name]
        if name in texts:
            return html.escape(texts[name])
        raise KeyError(f"no value for the slot {{{{{name}}}}}")

    return _SLOT.sub(value_of, template)


def _config_span(setting: str, percent: bool = False) -> str:
    """One value of engine/config.py, marked with its name so a test can check it against config."""
    attribute, _, key = setting.partition(".")
    value = getattr(config, attribute)
    if key:
        value = value[key]
    text = f"{value:.0%}" if percent else _number(value) if isinstance(value, (int, float)) else str(value)
    return f'<span class="config" data-config="{html.escape(setting)}">{html.escape(text)}</span>'


def _number(value: float) -> str:
    """1.0 as "1", 0.25 as "0.25", 1000 as "1,000"."""
    return f"{value:,g}"


def _points(value: float) -> str:
    return f"{_number(value)} point" + ("" if value == 1 else "s")


def _medium_red_flags() -> str:
    """The red flags a medium voice can have: one fewer than make it low."""
    most = config.VOICE_LOW_MIN_RED_FLAGS - 1
    return "only one red flag" if most == 1 else f"up to {most} red flags"


def _long_term() -> str:
    """config.LONG_TERM_MIN_MONTHS in words: "a year", "2 years" or "18 months"."""
    months = config.LONG_TERM_MIN_MONTHS
    if months % 12:
        return f"{months} months"
    return "a year" if months == 12 else f"{months // 12} years"


def _search_page_style() -> str:
    """The search page's own <style> block, so this page has its colours, fonts, dark mode and layout."""
    return re.search(r"<style>.*?</style>", SEARCH_TEMPLATE.read_text(encoding="utf-8"), re.DOTALL).group(0)


def _communities() -> str:
    """The subreddits answers come from (config.SUBREDDITS), by category."""
    items = "".join(
        f"<li><strong>{html.escape(category.capitalize())}:</strong> "
        f"{html.escape(', '.join('r/' + name for name in names))}</li>"
        for category, names in config.SUBREDDITS.items())
    return f"<ul>{items}</ul>"


def _sign_list(signs: dict[str, str]) -> str:
    """A list of signs, each marked with its tag; their own slots filled from config."""
    items = "".join(f'<li data-tag="{html.escape(tag)}">{fill(words, {})}</li>' for tag, words in signs.items())
    return f"<ul>{items}</ul>"


def _hard_rules() -> str:
    """Each fact rule that leaves a product out (config.PRODUCT_FACT_RULES, "hard"), as "you ask for X, and <reason>"."""
    items = []
    for rule in config.PRODUCT_FACT_RULES.values():
        if rule["hard"]:
            asks = [ASKS_WORDS.get(need, need) for need in rule["asks"]]
            # "something for a beginner, for sensitive skin or gentle": "something" said once.
            asks = asks[:1] + [a.removeprefix("something ") if asks[0].startswith("something ") else a for a in asks[1:]]
            listed = ", ".join(asks[:-1]) + " or " + asks[-1] if len(asks) > 1 else asks[0]
            items.append(f"<li>you ask for {html.escape(listed)}, and {html.escape(rule['reason'])}</li>")
    return f"<ul>{''.join(items)}</ul>"


def _soft_note_example() -> str:
    """The note a smaller clash shows under a pick, from the first rule that keeps the product ("hard": False)."""
    soft = [rule for rule in config.PRODUCT_FACT_RULES.values() if not rule["hard"]]
    return answer.CAUTION.format(reason=soft[0]["reason"]) if soft else ""


# --- The results ---

def evaluation_section(metrics_path: Path = METRICS_FILE) -> str:
    """The latest results from eval/metrics.json, read now; or a plain message when there are none to show."""
    try:
        loaded = load_metrics(metrics_path)
    except MetricsError:
        return _notice(BROKEN_RESULTS)
    if loaded is None:
        return _notice(NO_RESULTS)
    day = loaded.measured_on
    parts = [f'<p class="measured">{html.escape(MEASURED_ON.format(date=f"{day.day} {day:%b %Y}"))}</p>',
             f'<h3 class="group">{html.escape(TARGETS_HEADING)}</h3>',
             _cards(HEADLINE_KEYS, loaded.metrics)]
    if loaded.end_to_end is not None:
        e = loaded.end_to_end
        lines = [QUESTIONS.format(questions=e.questions, full=e.with_all_picks, picks_wanted=e.picks_wanted,
                                  some=e.with_a_pick, shown=_count(e.quotes_shown, "quote"),
                                  unverified=_count(e.unverified_quotes_shown, "quote"))]
        if e.threads_waiting_live_check:
            lines.append(WAITING.format(n=e.threads_waiting_live_check))
        parts.append(f'<div class="box"><h3>{html.escape(QUESTIONS_HEADING)}</h3>'
                     + "".join(f"<p>{html.escape(line)}</p>" for line in lines) + "</div>")
    parts += [f'<h3 class="group">{html.escape(OTHER_HEADING)}</h3>', _cards(OTHER_KEYS, loaded.metrics)]
    return "\n".join(parts)


def _cards(keys: tuple[str, ...], entries: dict[str, MetricEntry]) -> str:
    return '<ul class="metrics">' + "".join(_card(key, entries.get(key, MetricEntry())) for key in keys) + "</ul>"


def _card(key: str, entry: MetricEntry) -> str:
    """One result: what it measures, the score, the target, and whether it meets it."""
    title, about = METRIC_WORDING[key]
    lower = key in LOWER_IS_BETTER
    what = [f"<h4>{html.escape(title)}</h4>", f'<p class="about">{html.escape(about)}</p>']
    if entry.threads is not None:
        what.append(f'<p class="sample">{html.escape(SAMPLE.format(threads=entry.threads))}</p>')
    result = []
    if entry.value is not None:
        result.append(f'<p class="score">{html.escape(_score(entry, lower))}</p>')
    result.append(f'<p class="target">{html.escape(_target(entry.target, lower))}</p>')
    verdict = _verdict(entry.value, entry.target, lower)
    if verdict:
        word, kind = verdict
        result.append(f'<p class="verdict {kind}">{html.escape(word)}</p>')
    return (f'<li class="metric" id="metric-{html.escape(key)}"><div class="what">{"".join(what)}</div>'
            f'<div class="result">{"".join(result)}</div></li>')


def _score(entry: MetricEntry, lower: bool) -> str:
    """"45 out of 47 (96%)", or "$0.00 per question" for the cost."""
    if lower:
        return f"${entry.value:.2f} per question"
    percent = _percent(entry.value, entry.target)
    if entry.count is not None and entry.out_of is not None:
        return f"{entry.count:,} out of {entry.out_of:,} ({percent})"
    return percent


def _percent(value: float, target: float | None) -> str:
    """The share as a whole percentage; with one decimal when rounding would make a miss look like the target."""
    shown = f"{value:.0%}"
    if target is not None and value < target and shown == f"{target:.0%}":
        shown = f"{value:.1%}"
    return shown


def _target(target: float | None, lower: bool) -> str:
    if target is None:
        return NO_TARGET
    if lower:
        return f"Target: under ${target:.2f}"
    return "Target: 100%" if target >= 1 else f"Target: at least {target:.0%}"


def _verdict(value: float | None, target: float | None, lower: bool) -> tuple[str, str] | None:
    """(the words, a class for their colour): meets, misses or not measured yet; None when there is no target."""
    if value is None:
        return NOT_MEASURED, "unmeasured"
    if target is None:
        return None
    meets = value < target if lower else value >= target - 1e-9
    return (MEETS, "meets") if meets else (MISSES, "misses")


def _count(n: int, noun: str) -> str:
    return f"{n:,} {noun}" + ("" if n == 1 else "s")


def _notice(text: str) -> str:
    return f'<div class="notice honest"><p>{html.escape(text)}</p></div>'
