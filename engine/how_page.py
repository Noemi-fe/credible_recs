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
script of its own and loads nothing, except GoatCounter's script when visits are counted (11 Oct 2026; engine/web.py):
its styles are the search page's own (copied in from engine/templates/search.html when the page is made, so both look
alike), plus a few of its own.

Its last section, "Your privacy" (11 Oct 2026, going live), says what is collected about visitors and what isn't. What
it says about visit counts follows whether they are on, and the public site also names its host.

Wording: decided by Claude, 10 Oct 2026 (Noemi asked Claude to decide wording and report it). The explanation is in
the template; the words for each listed sign and each test result are below.
"""

import html
import re
from pathlib import Path

from engine import answer, config
from engine.group_products import brand_pick_name, plural
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
    "copied text": "<strong>Copies someone else:</strong> {{config:COPIED_TEXT_MIN_WORDS}} words or more in a row are "
                   "the same as another writer's comment in the thread, as when two accounts post the same "
                   "recommendation. Copies count once: only the first one posted counts at all.",
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
    "sulfate-free": "sulfate-free",
    "SPF": "a lip balm with SPF",  # 15 Oct 2026 (Noemi's decision 2; wording PROPOSED)
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
                        "or say politely that it isn't a product we recommend (a service, a place, food, a medicine "
                        "or a book, say)."),
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

# "Your privacy" (Noemi, 11 Oct 2026: going live; wording decided by Claude). The rest of the section is in the template.
VISITS_COUNTED = ("<strong>Visit counts.</strong> We count visits with GoatCounter, which sets no cookies and never "
                  "stores IP addresses. It keeps totals only: pages opened, the websites that sent people here, "
                  "browsers, screen sizes and countries, and a few events: that a search was made, the kind of answer "
                  "it got, which feedback button was pressed, and the answer to “First time here?”. Never what you "
                  "typed.")
VISITS_NOT_COUNTED = "<strong>Visit counts.</strong> Visits aren't counted at the moment."
# The public site's host and its logs (Noemi's decision 5 of 16 Oct 2026; wording PROPOSED): since 12 Oct 2026 the site
# runs on Google Cloud Run, whose request logs keep each request's time, address asked for, IP address and browser (and
# the website that linked there, when the browser says) in Cloud Logging's _Default bucket for its default 30 days (no
# exclusion or other keeping time is set: the website review of 16 Oct 2026). The request people type is in the body of
# a POST, which those logs never keep, and after the page's "#", which browsers never send. It had said the site ran on
# Hugging Face and kept no IP addresses.
REQUEST_LOG_DAYS = 30
REQUEST_LOGS = ("<li><strong>Google's request logs.</strong> The site runs on Google Cloud Run, which logs every request "
                "made to it, as web hosts do: the time, the part of the site asked for, your IP address and your "
                "browser, and the website you came from if your browser says, kept for {days} days. What you type is "
                "never in those logs: your search travels inside the request, not in its address, and it stays in "
                "this page's address only after the “#”, which your browser never sends.</li>")
PUBLIC_SITE = ("<p>To stop anyone flooding the site, our server counts each address's requests for a short while, in "
               "memory only: it never writes them down.</p>")
# A product sold only outside the UK (Noemi, 15 Oct 2026, evening) stays in answers with this note; an example day.
NOT_IN_UK_EXAMPLE_DAY = "15 Oct 2026"

# On-demand reading (14 Oct 2026; wording decided by Claude): on the live site, a request about a product we haven't
# read about yet is noted for the reading job (engine/on_demand.py). The page says so only where it happens.
ON_DEMAND_NOTE = ("<li><strong>Products we haven't read about yet.</strong> When you ask about one, we note the kind of "
                  "product and up to {words} words of what you asked for, nothing else: never your request as typed, "
                  "and nothing about you. A reading job uses the note to find Reddit threads about it, and it is kept "
                  "so the same product isn't read again within a month.</li>")
ON_DEMAND_EXCEPT = ", and the short note about a product we haven't read about yet"

# Noemi's upvote rule (14 Oct 2026; wording decided by Claude): explained under the picks rule only while it is on
# (config.UPVOTE_COUNTS_MORE), in the words of its variant: for any product (A), or only for one short of the bar (B, C,
# D), with variant C's thread (UPVOTE_TOP_OF_BIG_THREAD) and variant D's empty places only (UPVOTE_ONLY_TO_FILL).
UPVOTE_RULE = ("<p>{which} whose comment has at least {{{{config:UPVOTE_MIN_SCORE}}}} upvotes{thread} counts as two "
               "toward this rule, never more{as_needed}.{fill} The extra count never stands in for the second thread, "
               "upvotes never make a comment credible, and a warning always counts once. The pick's reason says which "
               "voice counted twice and for how many upvotes; every other number counts people.</p>")
UPVOTE_RULE_FILL = (" Such a product only takes a place the picks would otherwise leave empty: it never takes the place "
                    "of one that meets this rule on its own.")
UPVOTE_RULE_WHEN_SHORT = "When a product has fewer than {{config:MIN_CREDIBLE_MENTIONS}} credible recommendations, one"
UPVOTE_RULE_ANY = "A credible recommendation"
UPVOTE_RULE_AS_NEEDED = ", and only as many as the product needs to meet it"
UPVOTE_RULE_THREAD = (", and that scored higher than {{config%:UPVOTE_THREAD_SHARE_BEATEN}} of the other comments in a "
                      "thread of at least {{config:UPVOTE_THREAD_MIN_COMMENTS}} comments,")

# The need rule (11 Oct 2026; in every answer for haircare since Noemi's decision 4 of 14 Oct 2026 and for skincare since
# her decision 3 of 15 Oct 2026; wording decided by Claude, PROPOSED): a pick, or an Also worth a look item, needs a
# credible recommendation that talks about what the request asks for besides the product (engine.pipeline._ranked,
# engine.needs.judged_needs). {where} is NEED_RULE_EVERY with config.NEED_RULE_IN_EVERY_READING's categories, or
# NEED_RULE_WIDER alone when there are none.
NEED_RULE = ("<p>When you ask for more than the product, such as a skin type, a concern or a must-have, at least one of "
             "those credible recommendations must also talk about it{where}. An ingredient or a size you name isn't "
             "counted here: whether a product holds an ingredient is checked against its maker's list instead.</p>")
NEED_RULE_EVERY = ": in every answer for {categories}, and for anything else{wider}"
NEED_RULE_WIDER = " when we read more threads than usual"

# A comment that stands out in its thread (Noemi, 14 Oct 2026; wording decided by Claude): explained under Also worth a
# look only while it is on (config.STANDOUT_ON).
STANDOUT_RULE = ("<p>A product can also be shown when one comment about it stands out in its thread: a credible "
                 "recommendation whose comment has at least {{config:STANDOUT_MIN_SCORE}} upvotes, and at least "
                 "{{config%:STANDOUT_UPVOTES_PER_COMMENT}} as many upvotes as its thread has comments, in a thread "
                 "of at least {{config:STANDOUT_MIN_THREAD_COMMENTS}} comments. It must name at most "
                 "{{config:STANDOUT_MAX_PRODUCTS}} products, and talk about what you asked for when you ask for "
                 "more than the product. Its product can then take a place left empty under “{{worth_heading}}”, "
                 "even when that comment is its only credible recommendation{picks}. It never takes the place of a "
                 "product that meets the rules above. Upvotes never make a comment credible, the product needs more "
                 "credible recommendations than credible warnings, and its reason says which comment stands out and "
                 "by how much: “its comment has 74 upvotes in a 69-comment thread”.</p>")

STANDOUT_RULE_PICKS = (", and with one more credible recommendation, even from the same thread, a place the picks "
                       "would otherwise leave empty")

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


def page(metrics_path: Path = METRICS_FILE, counter: str = "", public: bool = False, on_demand: bool = False) -> str:
    """The whole page, with the decided values from config and the results from `metrics_path`, read now.

    `counter`: GoatCounter's script when visits are counted (engine.web.counter_script), else "", and the privacy
    section says which. `public`: the page is served by the public site, so it also names the site's host and what its
    request logs keep (16 Oct 2026).
    `on_demand`: the site notes requests about products not read yet (engine/on_demand.py), and the privacy section
    says what it keeps (14 Oct 2026).
    """
    slots = {
        "search_page_style": _search_page_style(),
        "communities": _communities(),
        "good_signs": _sign_list(GOOD_SIGNS),
        "red_flags": _sign_list(RED_FLAGS),
        "honesty_signs": _sign_list(HONESTY_SIGNS),
        "hard_rules": _hard_rules(),
        "upvote_rule": _upvote_rule(),
        "need_rule": _need_rule(),
        "standout_rule": _standout_rule(),
        "evaluation": evaluation_section(metrics_path),
        "visit_counting": VISITS_COUNTED if counter else VISITS_NOT_COUNTED,
        "public_site": PUBLIC_SITE if public else "",
        "request_logs": REQUEST_LOGS.format(days=REQUEST_LOG_DAYS) if public else "",
        "on_demand_note": ON_DEMAND_NOTE.format(words=_config_span("ON_DEMAND_NEED_WORDS")) if on_demand else "",
        "on_demand_except": html.escape(ON_DEMAND_EXCEPT) if on_demand else "",
        "counter_script": counter,
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
        "worth_heading": answer.WORTH_HEADING,  # "Also worth a look" (Noemi, 13 Oct 2026)
        "meets_bar": answer.MEETS_BAR,  # an item there meeting the picks bar (Noemi's decision 4 of 15 Oct 2026)
        "summary_label": answer.SUMMARY_LABEL,  # "In short:" (Noemi, 13 Oct 2026)
        "form_label": answer.FORM_LABEL,  # "Form" (active ingredients, 13 Oct 2026)
        "mixed_opinions": answer.DISAGREEMENT.split(":")[0],
        "other_type_words": ", ".join(config.OTHER_TYPE_WORDS[:OTHER_TYPE_EXAMPLES]) + " and so on",
        "brand_pick_example": brand_pick_name("Lodge", "cast iron skillet"),  # "Lodge cast iron skillet line"
        # A line's link to its maker's page (Noemi's night decision 1, 14 Oct 2026): "Browse Lodge cast iron skillets".
        "range_example": answer.RANGE_LINK.format(brand="Lodge", products=plural("cast iron skillet")),
        "default_currency": answer.CURRENCY_SIGNS.get(config.BUDGET_DEFAULT_CURRENCY, config.BUDGET_DEFAULT_CURRENCY),
        "soft_note_example": _soft_note_example(),
        "unconfirmed_example": answer.CAUTION.format(reason=unconfirmed_note(["PFAS"])),
        # Prescription-only products (Noemi's decision 5, 14 Oct 2026): the note they carry wherever they are shown.
        "prescription_example": answer.PRESCRIPTION_NOTE,
        # Buyable picks (Noemi's decisions of 15 Oct 2026, late afternoon): her own examples of what people buy vintage
        # on purpose (the first two of the kitchen's list), and a product's own link as cards show it.
        "vintage_example": " and ".join(config.SECOND_HAND_VINTAGE.get("kitchen", ())[:2]),
        "page_link_example": answer.PRODUCT_LINK.format(shop="John Lewis"),
        # A product sold only outside the UK (Noemi, 15 Oct 2026, evening): shown with this note, not left out.
        "not_in_uk_example": answer.AVAILABILITY_NOT_IN_UK.format(date=NOT_IN_UK_EXAMPLE_DAY),
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


def _upvote_rule() -> str:
    """The upvote rule under the picks rule (UPVOTE_RULE), in its variant's words, or "" while it is off."""
    if not config.UPVOTE_COUNTS_MORE:
        return ""
    short = config.UPVOTE_ONLY_WHEN_SHORT
    return fill(UPVOTE_RULE.format(which=UPVOTE_RULE_WHEN_SHORT if short else UPVOTE_RULE_ANY,
                                   thread=UPVOTE_RULE_THREAD if config.UPVOTE_TOP_OF_BIG_THREAD else "",
                                   as_needed=UPVOTE_RULE_AS_NEEDED if short else "",
                                   fill=UPVOTE_RULE_FILL if config.UPVOTE_ONLY_TO_FILL else ""), {})


def _need_rule() -> str:
    """The need rule under the picks rule (NEED_RULE): where it holds in every answer (config.NEED_RULE_IN_EVERY_READING),
    and that it holds for the rest when more threads are read."""
    categories = config.NEED_RULE_IN_EVERY_READING
    if not categories:
        return NEED_RULE.format(where=html.escape(NEED_RULE_WIDER))
    named = ", ".join(categories[:-1]) + " and " + categories[-1] if len(categories) > 1 else categories[0]
    return NEED_RULE.format(where=html.escape(NEED_RULE_EVERY.format(categories=named, wider=NEED_RULE_WIDER)))


def _standout_rule() -> str:
    """A comment standing out in its thread (STANDOUT_RULE, 14 Oct 2026), or "" while it is off."""
    if not config.STANDOUT_ON:
        return ""
    picks = STANDOUT_RULE_PICKS if config.STANDOUT_FILLS_PICKS else ""
    return fill(STANDOUT_RULE.replace("{picks}", picks), {"worth_heading": answer.WORTH_HEADING})


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
