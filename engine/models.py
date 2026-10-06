"""The shapes of the data every module passes around: threads, comments, authors and gold-set labels.

A Thread looks the same whichever source it came from (the hand-collected gold set today, the
Reddit API later, another forum one day), so the rest of the engine never needs to know the source.

Rules about a single object live here. Rules about how objects connect (a reply points to a real
comment, a label points to a real comment) live in engine/gold.py.
"""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

Category = Literal["skincare", "kitchen"]
Source = Literal["reddit"]

# Decided in docs/brief.md, "Open decisions". Ask Noemi before changing.
SUBREDDITS: dict[str, tuple[str, ...]] = {
    "skincare": ("SkincareAddiction", "AsianBeauty", "30PlusSkinCare", "SkincareAddictionUK"),
    "kitchen": ("BuyItForLife", "AskCulinary", "chefknives", "Cooking", "castiron", "Coffee", "espresso", "tea"),
}

Stance = Literal["recommend", "warn", "neutral"]
STANCE_VALUE: dict[str, int] = {"recommend": 1, "warn": -1, "neutral": 0}

Credibility = Literal["high", "medium", "low"]


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
    category: Category
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


class Label(Record):
    """One row of data/gold/labels.csv: Noemi's judgement of one product mention in one comment.

    A row with a blank product means "I read this comment and it mentions no product".
    Credibility describes the comment, so every row for the same comment carries the same value.
    """

    thread_id: Id
    comment_id: Id
    product: str | None = None
    stance: Stance | None = None
    credibility: Credibility | None = None
    reason: str | None = None
    notes: str | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _tidy(cls, value):
        # Spreadsheets add stray spaces and capitals; blank cells mean "no value".
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @field_validator("stance", "credibility", mode="before")
    @classmethod
    def _lowercase(cls, value):
        return value.lower() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _row_is_complete(self) -> "Label":
        if self.product:
            missing = [f for f in ("stance", "credibility", "reason") if getattr(self, f) is None]
            if missing:
                raise ValueError(f"a product mention needs: {', '.join(missing)}")
        elif self.stance:
            raise ValueError("stance given but product is blank; fill in the product or clear the stance")
        if self.credibility and not self.reason:
            raise ValueError("credibility given without a reason")
        return self
