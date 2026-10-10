"""Made-up scored mentions and kind notes for the ranking and answer tests (modules 6 and 7).

Kept apart from factories.py so the modules built in parallel don't edit the same file. Nothing here comes
from real threads. The weights follow a simple made-up scale standing in for module 5's real one:
voice high 1, medium 0.6, low 0.2; evidence long-term use 1, short-term use 0.6, no first-hand use 0.2;
times the stance (+1 recommend, -1 warn, 0 neutral).
"""

from itertools import count

from engine.rank import KindNote, ScoredMention

VOICE_VALUE = {"high": 1.0, "medium": 0.6, "low": 0.2}
EVIDENCE_VALUE = {"long-term use": 1.0, "short-term use": 0.6, "no first-hand use": 0.2}
STANCE_SIGN = {"recommend": 1, "warn": -1, "neutral": 0}

_comment_ids = count(1)


def made_up_weight(voice: str, evidence: str, stance: str) -> float:
    return VOICE_VALUE[voice] * EVIDENCE_VALUE[evidence] * STANCE_SIGN[stance]


def mention(
    product: str,
    thread: str = "t1",
    *,
    stance: str = "recommend",
    voice: str = "high",
    evidence: str = "long-term use",
    weight: float | None = None,
    category: str = "kitchen",
    comment: str | None = None,
    quote: str | None = None,
    badges: tuple[str, ...] = ("3 years of use",),
    key: str | None = None,
    written_as: str = "",
) -> ScoredMention:
    """One scored mention. Each call gets a new comment id and a quote of its own, unless given."""
    comment = comment or f"c{next(_comment_ids)}"
    return ScoredMention(
        product_key=key or product.lower().replace(" ", "-"),
        product_name=product,
        category=category,
        thread_id=thread,
        comment_id=comment,
        comment_url=f"https://www.reddit.com/r/test/comments/{thread}/comment/{comment}/",
        stance=stance,
        weight=made_up_weight(voice, evidence, stance) if weight is None else weight,
        voice=voice,
        evidence=evidence,
        badges=badges,
        quote=quote or f"My {stance} for the {product}, from comment {comment}.",
        written_as=written_as,
    )


def mentions(n: int, product: str, threads: tuple[str, ...] = ("t1", "t2"), **kwargs) -> list[ScoredMention]:
    """n mentions of one product, spread over the threads in turn: t1, t2, t1, t2..."""
    return [mention(product, threads[i % len(threads)], **kwargs) for i in range(n)]


def note(
    kind: str,
    thread: str = "t1",
    *,
    stance: str = "recommend",
    voice: str = "high",
    weight: float | None = None,
    comment: str | None = None,
    quote: str | None = None,
    key: str | None = None,
) -> KindNote:
    """One "what to look for" note about a kind of product."""
    comment = comment or f"c{next(_comment_ids)}"
    return KindNote(
        kind_key=key or kind.lower().replace(" ", "-"),
        kind_name=kind,
        thread_id=thread,
        comment_id=comment,
        comment_url=f"https://www.reddit.com/r/test/comments/{thread}/comment/{comment}/",
        stance=stance,
        weight=VOICE_VALUE[voice] * STANCE_SIGN[stance] if weight is None else weight,
        voice=voice,
        quote=quote or f"Go for a {kind}, says comment {comment}.",
    )


def bodies_for(*items) -> dict[str, str]:
    """A comment body for each mention or note, holding its quote word for word between other sentences."""
    return {item.comment_id: f"Some context first.\n\n{item.quote} And one last line." for item in items}
