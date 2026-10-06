"""The shapes of the data every module passes around: threads, comments, authors and gold-set labels.

The allowed values (categories, subreddits, label levels, reason tags) live in engine/config.py.

A Thread looks the same whichever source it came from (the hand-collected gold set today, the
Reddit API later, another forum one day), so the rest of the engine never needs to know the source.

Rules about a single object live here. Rules about how objects connect (a reply points to a real
comment, a label points to a real comment) live in engine/gold.py.
"""

import re
from datetime import UTC, datetime
from typing import Annotated, ClassVar, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from engine.config import (
    EVIDENCE_LEVELS,
    EVIDENCE_TAGS,
    MENTION_CATEGORIES,
    OTHER_TAG,
    STANCE_VALUE,
    THREAD_CATEGORIES,
    VOICE_LEVELS,
    VOICE_TAGS,
)

Source = Literal["reddit"]


def _as_utc(value: datetime) -> datetime:
    """Dates typed without a timezone are read as UTC, so every date compares cleanly."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


UtcDatetime = Annotated[datetime, AfterValidator(_as_utc)]
Id = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]+$")]
WebUrl = Annotated[str, Field(pattern=r"^https?://\S+$")]


class Record(BaseModel):
    # Unknown fields are errors, so a typo like "scroe" can't silently drop the real value.
    model_config = ConfigDict(extra="forbid")


class Author(Record):
    name: str = Field(min_length=1)
    account_created_at: UtcDatetime | None = None
    karma: int | None = None
    flair: str | None = None

    @field_validator("name")
    @classmethod
    def _deleted_is_not_a_name(cls, name: str) -> str:
        if name.strip().lower() == "[deleted]":
            raise ValueError('use null for a deleted account ("author": null), not the name "[deleted]"')
        return name


class Comment(Record):
    id: Id
    parent_id: Id | None = None  # None means a direct reply to the thread's post
    author: Author | None  # None when the account was deleted
    body: str  # exactly as written: never trimmed or reformatted, because quotes are checked against it
    created_at: UtcDatetime
    score: int  # upvotes minus downvotes; can be negative
    url: WebUrl
    status: Literal["ok", "deleted", "removed"] = "ok"

    @model_validator(mode="after")
    def _readable_comment_has_text(self) -> "Comment":
        if self.status == "ok":
            if not self.body.strip():
                raise ValueError("body is empty; a comment with status 'ok' needs its text")
            if self.body.strip() in ("[deleted]", "[removed]"):
                raise ValueError(f"body is {self.body.strip()!r} but status is 'ok'; set status to 'deleted' or 'removed'")
        return self


class Thread(Record):
    id: Id
    source: Source = "reddit"
    community: str = Field(min_length=1)  # the subreddit, without "r/"
    category: Literal[THREAD_CATEGORIES]
    title: str = Field(min_length=1)
    body: str = ""
    author: Author | None
    created_at: UtcDatetime
    score: int
    num_comments: int = Field(ge=0)  # as reported by the source, which can be more than were collected
    url: WebUrl
    collected_at: UtcDatetime  # when the data was saved; needed for the deletion rule and for recency
    comments: list[Comment]

    @field_validator("community")
    @classmethod
    def _drop_r_prefix(cls, community: str) -> str:
        return community.strip().removeprefix("r/")


class _LabelRow(Record):
    """What voice and mention labels share: tidy spreadsheet values, and a reason made of tags plus an optional note."""

    allowed_tags: ClassVar[tuple[str, ...]]
    tags: list[str]
    note: str | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _tidy(cls, value):
        # Spreadsheets add stray spaces and capitals; blank cells mean "no value".
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("tags", mode="before")
    @classmethod
    def _split_tags(cls, value):
        # One cell, tags separated by commas (or semicolons): "long-term use, mentions flaws".
        if value is None:
            return []
        if isinstance(value, str):
            return [" ".join(tag.split()).lower() for tag in re.split(r"[,;]", value) if tag.strip()]
        return value

    @field_validator("tags")
    @classmethod
    def _known_tags(cls, tags: list[str]) -> list[str]:
        allowed = cls.allowed_tags + (OTHER_TAG,)
        if not tags:
            raise ValueError(f"needs at least one tag: {', '.join(allowed)}")
        unknown = [tag for tag in tags if tag not in allowed]
        if unknown:
            raise ValueError(f"unknown tag(s) {', '.join(map(repr, unknown))}; choose from: {', '.join(allowed)}")
        return list(dict.fromkeys(tags))  # drop repeats, keep order

    @model_validator(mode="after")
    def _other_needs_a_note(self):
        if OTHER_TAG in self.tags and not self.note:
            raise ValueError(f'tag "{OTHER_TAG}" needs a note saying what the reason is')
        return self


def _lowercase(value):
    return value.lower() if isinstance(value, str) else value


class VoiceLabel(_LabelRow):
    """One row of data/gold/voices.csv: how credible the writer of one comment is.

    Every comment Noemi reads gets one. A comment with a voice label and no mention labels
    is a comment she read that mentions no product.
    """

    allowed_tags: ClassVar[tuple[str, ...]] = VOICE_TAGS
    thread_id: Id
    comment_id: Id
    voice: Literal[VOICE_LEVELS]

    _lower = field_validator("voice", mode="before")(_lowercase)


class MentionLabel(_LabelRow):
    """One row of data/gold/mentions.csv: one product mentioned in one comment, and how well the writer knows it."""

    allowed_tags: ClassVar[tuple[str, ...]] = EVIDENCE_TAGS
    comment_id: Id
    product: str
    category: Literal[MENTION_CATEGORIES]
    stance: Literal[tuple(STANCE_VALUE)]
    evidence: Literal[EVIDENCE_LEVELS]

    _lower = field_validator("category", "stance", "evidence", mode="before")(_lowercase)
