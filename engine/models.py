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
    """A comment's writer. Parse gives only the name; engine/profiles.py can fill in the rest from Arctic Shift.

    From Arctic Shift, account_created_at is the date of the writer's first comment or post in the archive
    ("active since"), which only approximates the account's age. Every field but the name may be unknown (None).
    """

    name: str = Field(min_length=1)
    account_created_at: UtcDatetime | None = None
    karma: int | None = None
    flair: str | None = None
    # How many comments and posts the account has written, for karma per contribution (module 5). Thread files
    # saved before this field existed have no such key, and still load.
    contributions: int | None = Field(default=None, ge=0)

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
    # Where the thread was read (Noemi, 9 Oct 2026): "parse" is Reddit itself, through Parse; "arctic_shift" is the
    # archive, which may still hold comments people later deleted on Reddit; "gold" is the hand-collected gold set.
    # Files saved before 9 Oct 2026 have no such key and still load (None): they were all read through Parse.
    read_from: Literal["parse", "arctic_shift", "bright_data", "gold"] | None = None
    # When Reddit itself was last read for this thread (a "live check"). None when it never was: a thread read from
    # the archive and not checked yet, or an older file, whose collected_at already says when Parse read it.
    checked_live_at: UtcDatetime | None = None

    @field_validator("community")
    @classmethod
    def _drop_r_prefix(cls, community: str) -> str:
        return community.strip().removeprefix("r/")

    def last_checked_live(self) -> datetime | None:
        """When Reddit itself was last read for this thread, or None if it never was.

        A thread read through Parse was read on Reddit when it was collected, so its collected_at counts (older files,
        all read through Parse, too). A thread read from the archive counts only once a live check has read it on
        Reddit (checked_live_at).
        """
        if self.checked_live_at is not None:
            return self.checked_live_at
        return None if self.read_from == "arctic_shift" else self.collected_at


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
        unknown = [tag for tag in tags if tag not in allowed]
        if unknown:
            raise ValueError(f"unknown tag(s) {', '.join(map(repr, unknown))}; choose from: {', '.join(allowed)}")
        return list(dict.fromkeys(tags))  # drop repeats, keep order

    @model_validator(mode="after")
    def _other_needs_a_note(self):
        if OTHER_TAG in self.tags and not self.note:
            raise ValueError(f'tag "{OTHER_TAG}" needs a note saying what the reason is')
        return self

    @model_validator(mode="after")
    def _reason_given(self):
        if self._needs_reason() and not self.tags:
            raise ValueError(f"needs at least one of the tags: {', '.join(self.allowed_tags + (OTHER_TAG,))}")
        return self

    def _needs_reason(self) -> bool:
        return True


def _lowercase(value):
    return value.lower() if isinstance(value, str) else value


def _yes_or_blank(value) -> bool:
    """A yes/blank spreadsheet column as True or False."""
    if value is None or isinstance(value, bool):
        return bool(value)
    return str(value).strip().lower() in ("yes", "y", "true", "1")


class VoiceLabel(_LabelRow):
    """One row of data/gold/voices.csv: a comment Noemi read, and how credible its writer is.

    Every comment she reads gets a row. A comment with product mentions needs a voice level and its tags; a
    comment with no product needs neither (Noemi, 8 Oct 2026: no metric uses them, and skipping saves time).
    `agrees` marks a reply that agrees with the comment above it ("This!", "Same, mine lasted 10 years"):
    evidence that the other writer is credible.
    """

    allowed_tags: ClassVar[tuple[str, ...]] = VOICE_TAGS
    thread_id: Id
    comment_id: Id
    voice: Literal[VOICE_LEVELS] | None = None
    agrees: bool = False

    _lower = field_validator("voice", mode="before")(_lowercase)

    _agrees = field_validator("agrees", mode="before")(lambda value: _yes_or_blank(value))

    @model_validator(mode="after")
    def _tags_need_a_voice(self) -> "VoiceLabel":
        if self.voice is None and self.tags:
            raise ValueError("tags given without a voice level: give the voice too, or clear the tags")
        return self

    def _needs_reason(self) -> bool:
        return self.voice is not None


class MentionLabel(_LabelRow):
    """One row of data/gold/mentions.csv: one product mentioned in one comment, and how well the writer knows it."""

    allowed_tags: ClassVar[tuple[str, ...]] = EVIDENCE_TAGS
    comment_id: Id
    product: str
    category: Literal[MENTION_CATEGORIES]
    stance: Literal[tuple(STANCE_VALUE)]
    evidence: Literal[EVIDENCE_LEVELS]
    # A kind of product rather than a brand ("sujihiki", "chemical exfoliant"; Noemi, 9 Oct 2026): the yes/blank
    # "kind" column. Kinds are scored against the AI's notes, not its products, and feed the ranking by kind.
    kind: bool = False

    _lower = field_validator("category", "stance", "evidence", mode="before")(_lowercase)
    _kind = field_validator("kind", mode="before")(lambda value: _yes_or_blank(value))
