"""Module 7, answer writing: writes the top 3 picks from a fixed template, using only verified quotes.

There is no Claude API key for now (Noemi, 7 Oct 2026), so the answer is a fixed template whose slots are filled
from the ranking's data only: names, counts and quotes. Nothing is made up or paraphrased. Later, an AI step may
write the one-line reasons, but only from the verified quotes, inside this same template.

What each pick shows (the brief):
- the product name and a one-line reason it wins;
- its credible support: how many high- and medium-credibility voices recommend it, across how many threads;
- two or three quotes, the most credible first, each with its "why this voice counts" badges and a link to the
  comment;
- known downsides: quotes from credible warnings (and the disagreement flag when there are several);
- the score breakdown, signal by signal;
- its price (Noemi's decision 11, 9 Oct 2026): from the price list (engine/prices.py), with the shop, the day it was
  checked and a link to the shop's own page for it (https only); or "Price not checked yet". When the request has a
  budget, a line says how the price compares with it. Products over the budget never get here: the pipeline leaves
  them out.
Under the picks: "what to look for" (a short blueprint from credible notes about kinds of product), the
skip-these list, and an honest message when fewer than 3 products have enough evidence.

The guardrail (the brief's most important rule): every quote is checked again, word for word, against its
comment as it is now (engine.verify_quotes), right before it is shown. A comment may have been edited or deleted
since the extraction. A quote that fails, whose comment is gone, that comes from a quoted block (someone else's
words, as at extraction), or whose matched words are over QUOTE_MAX_WORDS is dropped and never shown, anywhere:
not in the text, not in the structured answer. What is shown is the comment's own text that the quote matched,
with Reddit's HTML entities read ("&amp;" as "&"). The answer never carries the ranking's raw mentions, only the
quotes that passed. Then, "no claim without a verified quote":
- a pick needs at least 2 verified quotes (MIN_QUOTES_PER_PICK); one that has fewer gives its place to the
  next qualifying product;
- a skip-these product needs at least 1 verified warning quote, or it is left out;
- a "what to look for" note is a verified quote, or nothing.
unverified_claims() runs the same checks over a finished answer, as an automated proof.

The wording users see is in the constants below, marked PROPOSED: it waits for Noemi.
"""

import dataclasses
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from datetime import date

from engine.config import (
    DOWNSIDES_PER_PICK,
    LOOK_FOR_NOTES,
    MIN_CREDIBLE_MENTIONS,
    MIN_QUOTES_PER_PICK,
    MIN_THREADS,
    PICKS_SHOWN,
    PRICE_MAX_AGE_DAYS,
    QUOTE_MAX_WORDS,
    QUOTES_PER_PICK,
    QUOTES_PER_SKIPPED_PRODUCT,
)
from engine.extract import _as_written, _in_quoted_block, _own_words_in_quote_format
from engine.models import Thread
from engine.prices import PriceCheck
from engine.rank import KindNote, ProductScore, RankingResult, ScoredMention, ScoreBreakdown, is_credible
from engine.verify_quotes import find_quote, verify_quote

# --- Wording users see: PROPOSED 9 Oct 2026, awaiting Noemi ---
TITLE = "Top picks: {product_type}"
TITLE_ANY = "Top picks"
REASON = "Recommended by {voices}{long_term}{kind}."
REASON_LONG_TERM = ", {n} of them after long-term use"
REASON_KIND = "; credible voices favour its kind most ({kind})"
SUPPORT = "Backed by {voices}, across {threads}."
DISAGREEMENT = "Mixed opinions: also warned against by {voices}."
NO_DOWNSIDES = "No credible voice in these threads warned against it."
SKIP_REASON = "Warned against by {voices}{praised}."
SKIP_ALSO_PRAISED = ", though still recommended by {voices}"
LOOK_FOR = "Look for"  # a kind credible voices recommend
AVOID = "Avoid"  # a kind credible voices warn against
RULE = "at least {mentions} credible recommendations across at least {threads} threads"
NO_PICKS = "Not enough credible evidence to recommend {what} yet: a pick needs {rule}. We'd rather say so than guess."
FEWER_PICKS = "Enough credible evidence for only {products} ({rule}), so we show {n} instead of {wanted}."
BADGE_VOICE = "{voice}-credibility voice"  # the badge when module 5 gave no reason in words
QUOTES_HEADING = "In their words"
DOWNSIDES_HEADING = "Known downsides"
SUPPORT_LABEL = "Credible support"
BREAKDOWN_HEADING = "Score breakdown"
LOOK_FOR_HEADING = "What to look for"
SKIP_HEADING = "Skip these"
LINK_TEXT = "see the comment"
# Prices and budgets (decision 11; wording PROPOSED 9 Oct 2026, awaiting Noemi).
PRICE_LABEL = "Price"
PRICE = "{amount} at {shop}, checked {date}"
PRICE_UNKNOWN = "Price not checked yet"
PRICE_LINK_TEXT = "see it at the shop"
BUDGET_WITHIN = "Within your budget (up to {max})."
BUDGET_NOT_CHECKED = "Not checked against your budget (up to {max}): {why}."
BUDGET_WHY_UNKNOWN = "no price checked yet"
BUDGET_WHY_CURRENCY = "its price is in {currency}"
BUDGET_WHY_OLD = "its price was checked over {days} days ago, so it may have changed"
CURRENCY_SIGNS = {"GBP": "£", "EUR": "€", "USD": "$"}


# --- The answer ---

@dataclass(frozen=True)
class ShownQuote:
    """A quote that passed the word-for-word check, ready to show."""

    text: str  # the comment's own text the quote matched, entities read ("&amp;" as "&"); verified word for word
    comment_id: str
    url: str  # the link to the comment
    badges: tuple[str, ...]  # why this voice counts: "3 years of use", "expert flair"


@dataclass(frozen=True)
class ShownPrice:
    """A pick's price as shown, from the price list (engine/prices.py). Unknown: only `text` and the budget fields."""

    text: str  # "£120 at John Lewis, checked 9 Oct 2026", or PRICE_UNKNOWN
    amount: float | None
    currency: str | None  # GBP, EUR or USD
    shop: str | None
    url: str | None  # the shop's own page for the product, from the price list: https only
    checked_on: str | None  # the day the price was looked up, as "2026-10-09"
    budget_status: str | None  # "within", "unknown", "other currency" or "out of date"; None without a budget
    budget_note: str | None  # the same in words, for the shopper; None without a budget


@dataclass
class Pick:
    rank: int  # 1, 2 or 3
    product_key: str
    name: str
    reason: str  # the one-line reason it wins
    support: str  # how many credible voices back it, across how many threads
    quotes: list[ShownQuote]  # 2 or 3, the most credible first
    downsides: list[ShownQuote]  # from credible warnings; empty when there are none
    disagreement: str | None  # the disagreement flag in words, or None
    score: float
    breakdown: ScoreBreakdown  # numbers only: no quote is in it
    price: ShownPrice  # from the price list, or PRICE_UNKNOWN


@dataclass
class SkipItem:
    product_key: str
    name: str
    reason: str
    quotes: list[ShownQuote]  # credible warnings, at least 1


@dataclass
class LookFor:
    kind: str  # "Japanese gyuto"
    advice: str  # LOOK_FOR or AVOID
    quote: ShownQuote


@dataclass
class Answer:
    category: str
    product_type: str | None  # from the request, such as "chef knife"; only used in the wording
    picks: list[Pick]
    look_for: list[LookFor]
    skip: list[SkipItem]
    message: str | None  # the honest message when fewer than 3 picks have enough evidence
    needs_more_threads: bool  # fewer than 3 picks: fetching more threads may help
    quotes_dropped: int  # quotes that failed the check at answer time (for the logs; never shown)


def answer_to_dict(answer: Answer) -> dict:
    """The answer as plain dictionaries and lists, ready to turn into JSON for the web interface."""
    return dataclasses.asdict(answer)


def comment_bodies(threads: Iterable[Thread]) -> dict[str, str]:
    """{comment id: body} for every comment still readable: deleted or removed ones are left out, so their quotes fail."""
    return {c.id: c.body for thread in threads for c in thread.comments if c.status == "ok"}


# --- Writing the answer ---

def write_answer(ranking: RankingResult, bodies: Mapping[str, str], product_type: str | None = None,
                 prices: Mapping[str, PriceCheck] | None = None) -> Answer:
    """The answer for one request, from its ranking and the current text of its comments ({comment id: body}).

    `prices` is each product's price check ({product key: engine.prices.PriceCheck}), made by the pipeline; a product
    with none shows PRICE_UNKNOWN.
    """
    check = _QuoteCheck(bodies)
    prices = prices or {}
    picks: list[Pick] = []
    for product in ranking.qualifying:
        if len(picks) == PICKS_SHOWN:
            break
        quotes = check.first(_most_credible_first(product.credible_recommendations), QUOTES_PER_PICK)
        if len(quotes) >= MIN_QUOTES_PER_PICK:
            price = shown_price(prices.get(product.key))
            picks.append(_pick(len(picks) + 1, product, quotes, check, ranking, price))
    skip = [_skip_item(product, check) for product in ranking.skip_list]
    look_for = _look_for(ranking, check)
    return Answer(
        category=ranking.category,
        product_type=product_type,
        picks=picks,
        look_for=look_for,
        skip=[item for item in skip if item is not None],
        message=_message(len(picks), product_type),
        needs_more_threads=len(picks) < PICKS_SHOWN,
        quotes_dropped=check.dropped,
    )


class _QuoteCheck:
    """Checks quotes against the comments as they are now, and counts the ones dropped."""

    def __init__(self, bodies: Mapping[str, str]):
        self.bodies = bodies
        self.dropped = 0

    def first(self, items: Iterable[ScoredMention | KindNote], limit: int) -> list[ShownQuote]:
        """The first `limit` items whose quote passes the check, as quotes to show."""
        shown: list[ShownQuote] = []
        for item in items:
            if len(shown) == limit:
                break
            if _quote_problem(item.quote, item.comment_id, self.bodies):
                self.dropped += 1
            else:
                text = _shown_text(item.quote, self.bodies[item.comment_id])
                shown.append(ShownQuote(text, item.comment_id, item.comment_url, _badges(item)))
        return shown


def _quote_problem(text: str, comment_id: str, bodies: Mapping[str, str]) -> str | None:
    """Why a quote can't be shown, in words, or None when it passes. The reason never repeats the quote.

    The same checks as at extraction (engine.extract), on the comment as it is now. A quote from a quoted block is
    someone else's words, unless the whole comment is a quoted block whose words no other comment here has (at
    answer time only the comments are at hand: the title and post were checked at extraction). The word limit
    counts the words of the comment the quote matches.
    """
    body = bodies.get(comment_id)
    if body is None:
        return f"comment {comment_id} is not available to check against (deleted, removed or missing)"
    span = find_quote(body, text)
    if span is None:
        return f"quote not found word for word in comment {comment_id}"
    if _in_quoted_block(body, span):
        elsewhere = (other for other_id, other in bodies.items() if other_id != comment_id)
        if not _own_words_in_quote_format(body, text, elsewhere):
            return f"quote from comment {comment_id} is from a quoted block: someone else's words"
    words = len(_as_written(body, span).split())
    if words > QUOTE_MAX_WORDS:
        return f"quote from comment {comment_id} has {words} words; the limit is {QUOTE_MAX_WORDS}"
    return None


def _shown_text(quote: str, body: str) -> str:
    """What the reader sees for a quote that passed: the comment's own text it matched, entities read ("&amp;" as
    "&"), so the page never shows "&#32;" or more words than were counted. In the rare case that text wouldn't pass
    the check itself (a comment holding an escaped entity such as "&amp;gt;"), the quote as checked is shown."""
    text = _as_written(body, find_quote(body, quote))
    return text if verify_quote(body, text) else quote


def _badges(item: ScoredMention | KindNote) -> tuple[str, ...]:
    """Module 5's reasons in words; when it gave none, the plain levels ("medium-credibility voice", "short-term use")."""
    if item.badges:
        return item.badges
    plain = (BADGE_VOICE.format(voice=item.voice),)
    return plain + ((item.evidence,) if isinstance(item, ScoredMention) else ())


def _most_credible_first(items: Iterable[ScoredMention]) -> list[ScoredMention]:
    """Largest weight first; equal weights keep their order, so the result is always the same."""
    return sorted(items, key=lambda m: -abs(m.weight))


def _pick(rank: int, product: ProductScore, quotes: list[ShownQuote], check: _QuoteCheck, ranking: RankingResult,
          price: ShownPrice) -> Pick:
    warnings = product.credible_warnings
    return Pick(
        rank=rank,
        product_key=product.key,
        name=product.name,
        reason=_reason(product, ranking),
        support=_support(product),
        quotes=quotes,
        downsides=check.first(_most_credible_first(warnings), DOWNSIDES_PER_PICK),
        disagreement=DISAGREEMENT.format(voices=_plural(len(warnings), "credible voice")) if product.disputed else None,
        score=product.score,
        breakdown=product.breakdown,
        price=price,
    )


def _reason(product: ProductScore, ranking: RankingResult) -> str:
    """The one-line reason: how many credible voices, how many after long-term use, and the kind if it leads."""
    recommendations = product.credible_recommendations
    long_term = sum(m.evidence == "long-term use" for m in recommendations)
    has_bonus = product.breakdown.kind_bonus > 0 and ranking.leading_kind is not None
    return REASON.format(
        voices=_plural(len(recommendations), "credible voice"),
        long_term=REASON_LONG_TERM.format(n=long_term) if long_term else "",
        kind=REASON_KIND.format(kind=ranking.leading_kind.name) if has_bonus else "",
    )


def _support(product: ProductScore) -> str:
    """How many high- and medium-credibility voices recommend it, across how many threads."""
    recommendations = product.credible_recommendations
    counts = {level: sum(m.voice == level for m in recommendations) for level in ("high", "medium")}
    voices = [_plural(n, f"{level}-credibility voice") for level, n in counts.items() if n]
    return SUPPORT.format(voices=" and ".join(voices), threads=_plural(product.breakdown.credible_threads, "thread"))


def _skip_item(product: ProductScore, check: _QuoteCheck) -> SkipItem | None:
    """A skip-these entry with its verified warnings, or None when no warning quote passes the check."""
    quotes = check.first(_most_credible_first(product.credible_warnings), QUOTES_PER_SKIPPED_PRODUCT)
    if not quotes:
        return None
    praised = len(product.credible_recommendations)
    reason = SKIP_REASON.format(
        voices=_plural(len(product.credible_warnings), "credible voice"),
        praised=SKIP_ALSO_PRAISED.format(voices=_plural(praised, "credible voice")) if praised else "",
    )
    return SkipItem(product.key, product.name, reason, quotes)


def _look_for(ranking: RankingResult, check: _QuoteCheck) -> list[LookFor]:
    """Up to LOOK_FOR_NOTES kinds, strongest credible advice first, each with its strongest verified note.

    A kind with positive support gets "Look for" and a recommending note; negative support gets "Avoid" and a
    warning note. A kind whose support is zero (no credible notes, or as many for as against) gives no advice.
    """
    items: list[LookFor] = []
    for kind in sorted(ranking.kinds, key=lambda k: -abs(k.support)):  # sorted keeps ties in the ranking's order
        if len(items) == LOOK_FOR_NOTES:
            break
        if kind.support == 0:
            continue
        stance, advice = ("recommend", LOOK_FOR) if kind.support > 0 else ("warn", AVOID)
        notes = [n for n in ranking.kind_notes if n.kind_key == kind.key and n.stance == stance and is_credible(n)]
        quote = check.first(_most_credible_first(notes), 1)
        if quote:
            items.append(LookFor(kind.name, advice, quote[0]))
    return items


def _message(picks: int, product_type: str | None) -> str | None:
    """The honest message when fewer than 3 products have enough evidence, or None when there are 3."""
    if picks >= PICKS_SHOWN:
        return None
    rule = RULE.format(mentions=MIN_CREDIBLE_MENTIONS, threads=MIN_THREADS)
    if picks == 0:
        return NO_PICKS.format(what=f"any {product_type}" if product_type else "a product", rule=rule)
    return FEWER_PICKS.format(products=_plural(picks, "product"), rule=rule, n=picks, wanted=PICKS_SHOWN)


def shown_price(check: PriceCheck | None) -> ShownPrice:
    """A product's price as the shopper sees it: amount, shop and date when known, and how it meets the budget."""
    budget_status = None if check is None or check.status == "no budget" else check.status
    budget_note = _budget_note(check) if budget_status else None
    price = check.price if check is not None else None
    if price is None:
        return ShownPrice(PRICE_UNKNOWN, None, None, None, None, None, budget_status, budget_note)
    text = PRICE.format(amount=_money(price.price, price.currency), shop=price.shop, date=_day(price.checked_on))
    url = price.url if price.url.startswith("https://") else None  # the price list allows https only; checked again
    return ShownPrice(text, price.price, price.currency, price.shop, url, price.checked_on.isoformat(),
                      budget_status, budget_note)


def _budget_note(check: PriceCheck) -> str:
    """How the price meets the budget, in words: within it, or why it wasn't checked against it."""
    most = _money(check.budget.max, check.budget.currency)
    if check.status == "within":
        return BUDGET_WITHIN.format(max=most)
    why = {
        "unknown": BUDGET_WHY_UNKNOWN,
        "other currency": BUDGET_WHY_CURRENCY.format(currency=check.price.currency if check.price else ""),
        "out of date": BUDGET_WHY_OLD.format(days=PRICE_MAX_AGE_DAYS),
    }[check.status]
    return BUDGET_NOT_CHECKED.format(max=most, why=why)


def _money(amount: float, currency: str) -> str:
    """£120, £119.99, €1,200: whole amounts without pennies."""
    number = f"{amount:,.0f}" if amount == int(amount) else f"{amount:,.2f}"
    return CURRENCY_SIGNS.get(currency, currency + " ") + number


def _day(day: date) -> str:
    """9 Oct 2026."""
    return f"{day.day} {day:%b %Y}"


def _plural(n: int, noun: str) -> str:
    """'1 thread', '3 threads'."""
    return f"{n} {noun}" if n == 1 else f"{n} {noun}s"


# --- The automated check: no claim without a verified quote ---

def unverified_claims(answer: Answer, bodies: Mapping[str, str]) -> list[str]:
    """Every problem with a finished answer's quotes, in words; an empty list means every claim is backed.

    Checks that each quote shown is found word for word in its comment as it is now, isn't from a quoted block,
    and matches at most QUOTE_MAX_WORDS words, that each pick has at least MIN_QUOTES_PER_PICK quotes, and that
    each skip-these product has at least one. The problems name the comment, never the failed quote's words.
    """
    problems = []
    for where, quote in _every_quote(answer):
        problem = _quote_problem(quote.text, quote.comment_id, bodies)
        if problem:
            problems.append(f"{where}: {problem}")
    for pick in answer.picks:
        if len(pick.quotes) < MIN_QUOTES_PER_PICK:
            problems.append(f"pick {pick.rank} ({pick.name}): {len(pick.quotes)} quote(s); a pick needs {MIN_QUOTES_PER_PICK}")
    for item in answer.skip:
        if not item.quotes:
            problems.append(f"skip-these ({item.name}): no quote backs the warning")
    return problems


def _every_quote(answer: Answer) -> Iterator[tuple[str, ShownQuote]]:
    """Each quote in the answer, with where it is shown."""
    for pick in answer.picks:
        for quote in pick.quotes:
            yield f"pick {pick.rank} ({pick.name})", quote
        for quote in pick.downsides:
            yield f"pick {pick.rank} ({pick.name}) downside", quote
    for item in answer.look_for:
        yield f"what to look for ({item.kind})", item.quote
    for item in answer.skip:
        for quote in item.quotes:
            yield f"skip-these ({item.name})", quote


# --- Rendering as text (markdown) ---

def render_markdown(answer: Answer) -> str:
    """The answer as markdown text, readable as plain text too."""
    title = TITLE.format(product_type=answer.product_type) if answer.product_type else TITLE_ANY
    lines = [f"# {title}", ""]
    if answer.message:
        lines += [answer.message, ""]
    for pick in answer.picks:
        lines += _render_pick(pick)
    if answer.look_for:
        lines += [f"## {LOOK_FOR_HEADING}", ""]
        for item in answer.look_for:
            lines.append(f"- **{item.advice}: {item.kind}.** {_render_quote_inline(item.quote)}")
        lines.append("")
    if answer.skip:
        lines += [f"## {SKIP_HEADING}", ""]
        for item in answer.skip:
            lines.append(f"- **{item.name}:** {item.reason}")
            lines += [f"  - {_render_quote_inline(quote)}" for quote in item.quotes]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_pick(pick: Pick) -> list[str]:
    lines = [f"## {pick.rank}. {pick.name}", "", pick.reason, "", f"**{SUPPORT_LABEL}:** {pick.support}", ""]
    lines += _render_price(pick.price)
    if pick.disagreement:
        lines += [f"**{pick.disagreement}**", ""]
    lines += [f"**{QUOTES_HEADING}**", ""]
    for quote in pick.quotes:
        lines += _render_quote_block(quote)
    lines += [f"**{DOWNSIDES_HEADING}**", ""]
    if pick.downsides:
        for quote in pick.downsides:
            lines += _render_quote_block(quote)
    else:
        lines += [NO_DOWNSIDES, ""]
    lines += [f"**{BREAKDOWN_HEADING}**", ""] + _render_breakdown(pick.score, pick.breakdown) + [""]
    return lines


def _render_price(price: ShownPrice) -> list[str]:
    """The price line (with the shop's link when there is one) and the budget line, if any."""
    if price.amount is None:
        line = price.text
    else:
        link = f" · [{PRICE_LINK_TEXT}]({price.url})" if price.url else ""
        line = f"**{PRICE_LABEL}:** {price.text}{link}"
    return [line, ""] + ([price.budget_note, ""] if price.budget_note else [])


def _one_line(text: str) -> str:
    """The quote on one line: line breaks and runs of spaces become one space (formatting, not words)."""
    return " ".join(text.split())


def _render_quote_block(quote: ShownQuote) -> list[str]:
    credit = " · ".join(quote.badges + (f"[{LINK_TEXT}]({quote.url})",))
    return [f'> "{_one_line(quote.text)}"', f"> — {credit}", ""]


def _render_quote_inline(quote: ShownQuote) -> str:
    credit = " · ".join(quote.badges + (f"[{LINK_TEXT}]({quote.url})",))
    return f'"{_one_line(quote.text)}" ({credit})'


def _render_breakdown(score: float, b: ScoreBreakdown) -> list[str]:
    """The score breakdown as a list, signal by signal."""
    total = f"- Score {score:.2f} = {b.mention_points:.2f} from mentions"
    if b.kind_bonus:
        total += f" + {b.kind_bonus:.2f} kind bonus ({b.kind}, support {b.kind_support:.2f})"
    lines = [
        total,
        f"- Recommendations: {b.recommends}, {b.credible_recommends} credible. "
        f"Voices: {_levels(b.recommend_voices)}. Evidence: {_levels(b.recommend_evidence)}.",
        f"- Warnings: {b.warnings}, {b.credible_warnings} credible. "
        f"Voices: {_levels(b.warn_voices)}. Evidence: {_levels(b.warn_evidence)}.",
        f"- Neutral mentions: {b.neutral} (they never count)",
        f"- Threads: {b.threads}, {b.credible_threads} with a credible recommendation",
    ]
    if b.kind and not b.kind_bonus:
        lines.append(f"- Kind: {b.kind} (support {b.kind_support:.2f}; no bonus: it doesn't lead by far)")
    return lines


def _levels(counts: dict[str, int]) -> str:
    """{"high": 2, "medium": 1, "low": 0} as "2 high, 1 medium, 0 low"."""
    return ", ".join(f"{n} {level}" for level, n in counts.items())
