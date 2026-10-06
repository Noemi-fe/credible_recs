"""Rules about a single thread, comment or label row."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from engine.config import STANCE_VALUE
from engine.models import Comment, MentionLabel, Thread, VoiceLabel
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


# Labels arrive from CSVs, so every value is a string and blanks are empty strings.
# Two layers (brief v4): a voice label per comment, and an evidence label per product mention.

def voice_row(**overrides) -> dict:
    row = {"thread_id": "1fake01", "comment_id": "c1aaaa", "voice": "high", "tags": "established member, well upvoted", "note": ""}
    row.update(overrides)
    return row


def mention_row(**overrides) -> dict:
    row = {
        "comment_id": "c1aaaa",
        "product": "CeraVe Renewing SA Cleanser",
        "category": "skincare",
        "stance": "recommend",
        "evidence": "long-term use",
        "tags": "long-term use, mentions flaws",
        "note": "",
    }
    row.update(overrides)
    return row


def test_valid_voice_label_parses():
    label = VoiceLabel.model_validate(voice_row())
    assert label.voice == "high"
    assert label.tags == ["established member", "well upvoted"]
    assert label.note is None


def test_valid_mention_label_parses():
    label = MentionLabel.model_validate(mention_row())
    assert label.evidence == "long-term use"
    assert label.tags == ["long-term use", "mentions flaws"]
    assert STANCE_VALUE[label.stance] == 1


def test_label_values_are_tidied_from_spreadsheet_typing():
    label = MentionLabel.model_validate(
        mention_row(stance=" Recommend ", evidence="Short-Term Use", category="SKINCARE", product="  CeraVe SA  ", tags=" Vague ;  secondhand")
    )
    assert (label.stance, label.evidence, label.category, label.product) == ("recommend", "short-term use", "skincare", "CeraVe SA")
    assert label.tags == ["vague", "secondhand"]


@pytest.mark.parametrize("field, value", [("voice", "very high"), ("tags", "")])
def test_voice_label_rejects(field, value):
    with pytest.raises(ValidationError, match=field):
        VoiceLabel.model_validate(voice_row(**{field: value}))


@pytest.mark.parametrize(
    "field, value",
    [("product", ""), ("category", "electronics"), ("stance", "love it"), ("evidence", "years"), ("tags", "")],
)
def test_mention_label_rejects(field, value):
    with pytest.raises(ValidationError, match=field):
        MentionLabel.model_validate(mention_row(**{field: value}))


def test_off_category_mention_is_labelled_with_category_other():
    assert MentionLabel.model_validate(mention_row(product="Bodum French press", category="other")).category == "other"


def test_voice_tags_and_evidence_tags_are_separate_lists():
    # "mentions flaws" describes evidence about a product, not the voice of the writer.
    with pytest.raises(ValidationError, match="established member"):
        VoiceLabel.model_validate(voice_row(tags="mentions flaws"))
    with pytest.raises(ValidationError, match="long-term use"):
        MentionLabel.model_validate(mention_row(tags="well upvoted"))


def test_misspelt_tag_is_rejected():
    with pytest.raises(ValidationError, match="longterm use"):
        MentionLabel.model_validate(mention_row(tags="longterm use"))


def test_other_tag_needs_a_note():
    with pytest.raises(ValidationError, match="note"):
        VoiceLabel.model_validate(voice_row(tags="other"))
    with pytest.raises(ValidationError, match="note"):
        MentionLabel.model_validate(mention_row(tags="specific details, other", note="  "))


def test_other_tag_with_a_note_is_fine():
    label = MentionLabel.model_validate(mention_row(tags="other", note="Bought it for her mum and watched her use it"))
    assert label.tags == ["other"]
    assert label.note == "Bought it for her mum and watched her use it"


def test_stance_values_match_the_brief():
    assert STANCE_VALUE == {"recommend": 1, "warn": -1, "neutral": 0}
