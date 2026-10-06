"""Rules about a single thread, comment or label row."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from engine.models import STANCE_VALUE, Comment, Label, Thread
from engine.tests.factories import make_comment, make_thread


def test_valid_thread_parses():
    thread = Thread.model_validate(make_thread())
    assert thread.category == "skincare"
    assert len(thread.comments) == 3
    assert thread.comments[1].parent_id == "c1aaaa"


def test_comment_body_is_kept_exactly_as_written():
    # Quote verification compares word for word, so the loader must never tidy the text.
    body = "  Two spaces first.\n\nThen a blank line, an emoji 🧴 and accents: crème, très.  "
    comment = Comment.model_validate(make_comment("c1aaaa", body=body))
    assert comment.body == body


def test_dates_without_timezone_are_read_as_utc():
    comment = Comment.model_validate(make_comment("c1aaaa", created_at="2025-03-02"))
    assert comment.created_at == datetime(2025, 3, 2, tzinfo=UTC)


def test_ambiguous_date_format_is_rejected():
    # 01/03/2025 could be 1 March or 3 January.
    with pytest.raises(ValidationError):
        Comment.model_validate(make_comment("c1aaaa", created_at="01/03/2025"))


def test_unknown_field_is_rejected():
    # A typo such as "scroe" must not silently drop the real value.
    with pytest.raises(ValidationError, match="scroe"):
        Comment.model_validate(make_comment("c1aaaa", scroe=5))


def test_unknown_category_is_rejected():
    with pytest.raises(ValidationError):
        Thread.model_validate(make_thread(category="electronics"))


def test_deleted_account_is_null_not_a_name():
    # "[deleted]" as a name would look like one prolific user and skew the credibility signals.
    with pytest.raises(ValidationError, match="null"):
        Comment.model_validate(make_comment("c1aaaa", author={"name": "[deleted]"}))
    comment = Comment.model_validate(make_comment("c1aaaa", author=None))
    assert comment.author is None


def test_readable_comment_needs_text():
    with pytest.raises(ValidationError):
        Comment.model_validate(make_comment("c1aaaa", body="   "))


def test_comment_reading_deleted_must_be_marked_deleted():
    with pytest.raises(ValidationError, match="status"):
        Comment.model_validate(make_comment("c1aaaa", body="[deleted]"))
    comment = Comment.model_validate(make_comment("c1aaaa", body="[deleted]", status="deleted", author=None))
    assert comment.status == "deleted"


def test_negative_comment_score_is_allowed():
    assert Comment.model_validate(make_comment("c1aaaa", score=-8)).score == -8


def test_url_must_be_a_web_link():
    with pytest.raises(ValidationError):
        Comment.model_validate(make_comment("c1aaaa", url="reddit.com/r/x"))


# Labels arrive from a CSV, so every value is a string and blanks are empty strings.

def label_row(**overrides) -> dict:
    row = {
        "thread_id": "1fake01",
        "comment_id": "c1aaaa",
        "product": "CeraVe Renewing SA Cleanser",
        "stance": "recommend",
        "credibility": "high",
        "reason": "2 years of use and names a downside",
    }
    row.update(overrides)
    return row


def test_valid_label_parses():
    label = Label.model_validate(label_row())
    assert label.stance == "recommend"
    assert STANCE_VALUE[label.stance] == 1


def test_label_values_are_tidied_from_spreadsheet_typing():
    label = Label.model_validate(label_row(stance=" Recommend ", credibility="HIGH", product="  CeraVe SA  "))
    assert label.stance == "recommend"
    assert label.credibility == "high"
    assert label.product == "CeraVe SA"


def test_label_rejects_unknown_stance():
    with pytest.raises(ValidationError):
        Label.model_validate(label_row(stance="love it"))


@pytest.mark.parametrize("missing", ["stance", "credibility", "reason"])
def test_product_mention_needs_stance_credibility_and_reason(missing):
    with pytest.raises(ValidationError, match=missing):
        Label.model_validate(label_row(**{missing: ""}))


def test_blank_product_means_reviewed_with_no_product():
    label = Label.model_validate(label_row(product="", stance="", credibility="", reason=""))
    assert label.product is None
    assert label.stance is None


def test_no_product_row_cannot_have_a_stance():
    with pytest.raises(ValidationError, match="stance"):
        Label.model_validate(label_row(product="", stance="recommend"))


def test_stance_values_match_the_brief():
    assert STANCE_VALUE == {"recommend": 1, "warn": -1, "neutral": 0}
