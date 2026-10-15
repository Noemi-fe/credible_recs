"""Edited comments keep what still verifies (Noemi's decision 3 of 15 Oct 2026).

Until then a kept comment found edited on Reddit (one of its quotes no longer there word for word) lost all its words
and items when the reads were applied (engine/verify.py apply_checks, before each deploy): of 58 really edited
comments, 29 still held at least half their quotes. Now such a comment keeps Reddit's current text, as the read that
found it edited showed it, and only the items whose quotes are still found in it word for word; the rest go, as before.
A reply that takes its product from such a comment (refers_to) follows the same rule: its item stays only while the
comment above still says, word for word, what it said of that product.

The rules it keeps:
- no word is kept that Reddit didn't show in a read of the last 48 hours: the current text is the text of the read
  that found the comment edited, or of a newer one, taken from this machine's checks or the bucket's bundle (the site's
  reads of the last 48 hours, which deploy.sh now fetches once next to the record); with neither, the comment goes as
  before. Its verified_at is that read's, so the 30-day deadline counts from it;
- the verification record and the plan carry ids, dates and outcomes only; the bundle carries reads for 48 hours, as
  before, and the fetched copy is deleted once applied;
- the site reads such a comment again like an answer's comment (every 40 hours) until a deploy has applied it, so a
  read with its current text is always in the bundle;
- an edited comment's words are its embed page's text, whose formatting is read as plain words: its quotes are never
  widened to the sentences before them (a quoted block of someone else's words can't be told from the rest);
- restore-words (the backup's items for comments verification dropped since slimming) gives back the items still found
  in Reddit's current text, under the same rule.

Made-up threads, comments and pages only: no test reads data/ or reaches the network.
"""

import json
from datetime import timedelta

import pytest

from engine import library
from engine.answer import write_answer
from engine.extract import check_extraction
from engine.live_check import LiveChecker, _entry_name, embed_url
from engine.models import Comment
from engine.precheck import due_for_verification
from engine.rank import rank_products
from engine.read_ahead import Plan, plan_bytes, read_plan
from engine.slim import slim_library
from engine.tests.ranking_factories import mention
from engine.tests.test_live_check import Clock
from engine.tests.test_restore_words import Embed
from engine.tests.test_slim import SOURCE, TID, ZOJI, a_library, c, extraction_dict, whole_thread_dict
from engine.tests.test_verify import SLIMMED, comment, day, extraction_of, items_of, thread_of
from engine.verify import Ledger, apply_checks, kept_comments, outcome, restore_words, verification_quotes

RINSE = "Rinse it with white vinegar every month."
GOOSE = "A gooseneck spout makes pour-over so much easier."
EDIT = "Edit: it survived the move too."


def two_item_thread() -> dict:
    """The slimming tests' kettle thread, with two items on each of two comments: the Zojirushi comment holds its
    mention and a care tip; the comment a reply takes the Fellow Stagg EKG from holds its own mention of it and a note."""
    thread = whole_thread_dict()
    for cm in thread["comments"]:
        if cm["id"] == "s1kept":
            cm["body"] = f"{ZOJI} {RINSE}"
        if cm["id"] == "s4source":
            cm["body"] = f"{SOURCE} {GOOSE}"
    return thread


def two_item_extraction() -> dict:
    data = extraction_dict()
    data["mentions"].append({"comment_id": "s4source", "product": "Fellow Stagg EKG", "category": "kitchen",
                             "stance": "recommend", "quote": SOURCE, "product_type": "electric kettle"})
    data["care"].append({"comment_id": "s1kept", "about": "Zojirushi kettle", "is_kind": False,
                         "tip": "rinse with vinegar monthly", "quote": RINSE})
    data["notes"].append({"comment_id": "s4source", "about": "gooseneck kettle", "stance": "recommend",
                          "quote": GOOSE})
    return data


def library_with_two_items(tmp_path):
    root = a_library(tmp_path, [two_item_thread()], {TID: two_item_extraction()})
    assert slim_library(root, now=SLIMMED, gold_ids=set()).slimmed == [TID]
    return root


def reads_at(tmp_path, now, texts: dict[str, tuple[timedelta, str | None]], folder: str = "reads",
             via: str | None = None) -> LiveChecker:
    """A checker whose folder holds a read of each comment link: how long ago, and the text Reddit showed."""
    checker = LiveChecker(cache_dir=tmp_path / folder, clock=lambda: now)
    for url, (ago, text) in texts.items():
        entry = {"fetched_at": (now - ago).isoformat(), "text": text} | ({"via": via} if via else {})
        path = tmp_path / folder / _entry_name(embed_url(url))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entry), encoding="utf-8")
    return checker


def link(root, comment_id: str) -> str:
    return comment(root, comment_id).url


def edited_read(root, tmp_path, comment_id: str, text: str, hours_ago: float = 3, **more):
    """The ledger and a read saying `comment_id` was found edited `hours_ago`, Reddit showing `text`."""
    now = day(15)
    at = now - timedelta(hours=hours_ago)
    ledger = Ledger()
    ledger.record(comment_id, at, outcome(text, verification_quotes(thread_of(root), extraction_of(root))[comment_id]))
    assert ledger.get(comment_id).outcome == "changed"
    return ledger, reads_at(tmp_path, now, {link(root, comment_id): (timedelta(hours=hours_ago), text)}, **more), now


# --- Applying the reads (engine/verify.py apply_checks) ---

def test_an_edited_comment_keeps_reddits_current_text_and_the_items_still_found_in_it(tmp_path):
    root = library_with_two_items(tmp_path)
    shown = f"{ZOJI} {EDIT}"  # the care tip's sentence is gone, the mention's quote is still there
    ledger, reads, now = edited_read(root, tmp_path, "s1kept", shown)
    result = apply_checks(root, ledger, now=now, reads=[reads])
    kept = comment(root, "s1kept")
    assert (kept.status, kept.body, kept.verified_at, kept.edited) == ("ok", shown, now - timedelta(hours=3), "embed")
    assert kept.author.name == "alice_t"  # still hers on Reddit
    left = items_of(extraction_of(root), "s1kept")
    assert [item.quote for item in left] == [ZOJI]  # the mention stays, the care tip goes
    check = check_extraction(extraction_of(root), thread_of(root))
    assert [m.comment_id for m in check.kept if m.comment_id == "s1kept"] == ["s1kept"]
    assert (result.edited, result.items_after_edit, result.items_removed, result.dropped) == (1, 1, 1, {})
    assert "s1kept" not in thread_of(root).whole_thread.dropped
    assert RINSE not in (root / "threads" / f"{TID}.json").read_text() + (root / "extracted" / f"{TID}.json").read_text()


def test_its_next_read_verifies_the_items_it_kept(tmp_path):
    root = library_with_two_items(tmp_path)
    shown = f"{ZOJI} {EDIT}"
    ledger, reads, now = edited_read(root, tmp_path, "s1kept", shown)
    apply_checks(root, ledger, now=now, reads=[reads])
    [quotes] = [k.quotes for k in kept_comments(root) if k.comment_id == "s1kept"]
    assert quotes == (ZOJI,) and outcome(shown, quotes) == "passing"


def test_an_edited_comment_with_no_quote_left_goes_as_before(tmp_path):
    root = library_with_two_items(tmp_path)
    ledger, reads, now = edited_read(root, tmp_path, "s1kept", "Edit: it broke after all, avoid it.")
    result = apply_checks(root, ledger, now=now, reads=[reads])
    gone = comment(root, "s1kept")
    assert (gone.status, gone.body, gone.author, gone.edited) == ("not_kept", "", None, None)
    assert items_of(extraction_of(root), "s1kept") == []
    assert result.dropped == {"changed": 1} and result.edited == 0
    assert thread_of(root).whole_thread.dropped == {"s1kept": "changed"}


def test_without_the_reads_text_an_edited_comment_goes_as_before(tmp_path):
    root = library_with_two_items(tmp_path)
    ledger, _, now = edited_read(root, tmp_path, "s1kept", f"{ZOJI} {EDIT}")
    result = apply_checks(root, ledger, now=now)  # the record alone: ids, dates and outcomes, no words
    assert comment(root, "s1kept").status == "not_kept" and result.dropped == {"changed": 1}


def test_a_read_older_than_48_hours_is_never_used(tmp_path):
    root = library_with_two_items(tmp_path)
    ledger, reads, now = edited_read(root, tmp_path, "s1kept", f"{ZOJI} {EDIT}", hours_ago=49)
    apply_checks(root, ledger, now=now, reads=[reads])
    assert comment(root, "s1kept").status == "not_kept"


def test_an_older_read_than_the_records_latest_is_never_taken_for_the_current_text(tmp_path):
    # The record knows a newer read (made elsewhere, its text not at hand): the older text may no longer be Reddit's.
    root = library_with_two_items(tmp_path)
    ledger, reads, now = edited_read(root, tmp_path, "s1kept", f"{ZOJI} {EDIT}", hours_ago=20)
    ledger.record("s1kept", now - timedelta(hours=2), "changed")
    apply_checks(root, ledger, now=now, reads=[reads])
    assert comment(root, "s1kept").status == "not_kept"


def test_the_newest_read_with_text_decides_wherever_it_was_made(tmp_path):
    root = library_with_two_items(tmp_path)
    now = day(15)
    url = link(root, "s1kept")
    older = reads_at(tmp_path, now, {url: (timedelta(hours=30), f"{ZOJI} Edit: older words.")}, folder="here")
    newer = reads_at(tmp_path, now, {url: (timedelta(hours=5), f"{ZOJI} {EDIT}")}, folder="bundle")
    ledger = Ledger()
    ledger.record("s1kept", now - timedelta(hours=30), "changed")
    ledger.record("s1kept", now - timedelta(hours=5), "changed")
    apply_checks(root, ledger, now=now, reads=[older, newer])
    assert comment(root, "s1kept").body == f"{ZOJI} {EDIT}"
    assert comment(root, "s1kept").verified_at == now - timedelta(hours=5)


def test_a_read_through_bright_data_keeps_its_text_as_written(tmp_path):
    root = library_with_two_items(tmp_path)
    shown = f"{ZOJI}\n\n{EDIT}"
    ledger, reads, now = edited_read(root, tmp_path, "s1kept", shown, via="bright_data")
    apply_checks(root, ledger, now=now, reads=[reads])
    kept = comment(root, "s1kept")
    assert (kept.status, kept.body, kept.edited) == ("ok", shown, "bright_data")


def test_a_dry_run_counts_and_writes_nothing(tmp_path):
    root = library_with_two_items(tmp_path)
    files = {p: p.read_bytes() for p in root.rglob("*.json")}
    ledger, reads, now = edited_read(root, tmp_path, "s1kept", f"{ZOJI} {EDIT}")
    result = apply_checks(root, ledger, now=now, reads=[reads], dry_run=True)
    assert (result.edited, result.items_after_edit) == (1, 1)
    assert {p: p.read_bytes() for p in root.rglob("*.json")} == files


# --- A reply that takes its product from an edited comment ---

def test_a_reply_keeps_its_product_while_the_comment_above_still_says_it(tmp_path):
    root = library_with_two_items(tmp_path)
    ledger, reads, now = edited_read(root, tmp_path, "s4source", f"{SOURCE} {EDIT}")  # the note's sentence is gone
    apply_checks(root, ledger, now=now, reads=[reads])
    assert [item.quote for item in items_of(extraction_of(root), "s4source")] == [SOURCE]
    check = check_extraction(extraction_of(root), thread_of(root))
    assert any(m.comment_id == "s5reply" and m.product == "Fellow Stagg EKG" for m in check.kept)


def test_a_reply_loses_its_product_when_the_comment_above_no_longer_says_it(tmp_path):
    root = library_with_two_items(tmp_path)
    ledger, reads, now = edited_read(root, tmp_path, "s4source", f"Edit: I sold it. {GOOSE}")
    result = apply_checks(root, ledger, now=now, reads=[reads])
    source = comment(root, "s4source")
    assert (source.status, source.edited) == ("ok", "embed")
    assert [item.quote for item in items_of(extraction_of(root), "s4source")] == [GOOSE]  # its note stays
    assert items_of(extraction_of(root), "s5reply") == []  # the reply's product was the one no longer named
    reply = comment(root, "s5reply")
    assert (reply.status, reply.body, reply.author) == ("not_kept", "", None)  # nothing uses its words now
    assert result.items_removed == 2 and result.edited == 1


# --- The answer: an edited comment's quotes are never widened ---

def test_a_quote_from_an_edited_comment_is_never_widened_to_the_sentences_before_it(tmp_path):
    # On the embed page a quoted block of someone else's words reads like the writer's own sentences: an edited
    # comment's words are that page's text, so the sentence before its quote may be anyone's.
    lead = "The Zojirushi kettle is the one to get."
    quote = "Had it 3 years, still great."
    items = [mention("Zojirushi kettle", "t1", comment="e1", quote=quote),
             *[mention("Zojirushi kettle", t) for t in ("t1", "t2")]]
    bodies = {m.comment_id: f"{lead} {m.quote}" for m in items}
    ranking = rank_products(items, "kitchen")
    plain = write_answer(ranking, bodies, "electric kettle")
    assert any(q.text == f"{lead} {quote}" for q in plain.picks[0].quotes)  # widened to name its product
    edited = write_answer(ranking, bodies, "electric kettle", flattened={"e1"})
    assert all(lead not in q.text for q in edited.picks[0].quotes if q.comment_id == "e1")


def test_the_pipeline_says_which_comments_hold_the_embed_pages_text(tmp_path):
    from engine.answer import flattened_comments

    root = library_with_two_items(tmp_path)
    ledger, reads, now = edited_read(root, tmp_path, "s1kept", f"{ZOJI} {EDIT}")
    apply_checks(root, ledger, now=now, reads=[reads])
    assert flattened_comments([thread_of(root)]) == {"s1kept"}


def test_an_edited_mark_is_only_for_a_comment_the_library_keeps():
    with pytest.raises(ValueError):
        Comment.model_validate(c("s1x", None, "", 1, status="not_kept") | {"edited": "embed"})


# --- The plan: edited comments are read again until a deploy applies them ---

def test_an_edited_comment_is_listed_to_be_read_again_until_a_deploy_applies_it(tmp_path):
    root = library_with_two_items(tmp_path)
    kept = kept_comments(root)
    ledger = Ledger()
    ledger.record("s1kept", day(14), "changed")
    ledger.record("s2agree", day(14), "deleted")
    due = due_for_verification(kept, ledger, day(15))
    assert [k.comment_id for k in due.edited] == ["s1kept"]
    assert "s1kept" not in [k.comment_id for k in due.chosen]
    assert due.gone_already == 1  # the deleted one: the next deploy drops it, as before


def test_the_plan_carries_the_edited_comments_and_the_site_reads_them_like_answers_comments(tmp_path):
    clock = Clock()
    url = "https://www.reddit.com/r/BuyItForLife/comments/1kett01/which_kettle/c0001x/"
    plan = read_plan(plan_bytes([], [], {}, clock.now, edited=[url]))
    assert isinstance(plan, Plan) and plan.edited == (url,)
    assert read_plan(plan_bytes([], [], {}, clock.now)).edited == ()  # a plan written before has none
    from engine.read_ahead import ReadAhead

    checker = LiveChecker(cache_dir=tmp_path / "site", clock=clock)
    ahead = ReadAhead(checker)
    ahead.plan = plan
    assert ahead.due_now() == [url]  # never read: due
    entry = {"fetched_at": (clock.now - timedelta(hours=20)).isoformat(), "text": "Edited words."}
    (tmp_path / "site").mkdir(exist_ok=True)
    (tmp_path / "site" / _entry_name(embed_url(url))).write_text(json.dumps(entry), encoding="utf-8")
    ahead._look(url)
    assert ahead.due_now() == []  # read 20 hours ago: its text is in the bundle
    clock.now += timedelta(hours=21)
    assert ahead.due_now() == [url]  # 41 hours: read again before the bundle loses its text at 48


# --- The command line and the deploy ---

def test_apply_checks_takes_the_bundles_reads_of_the_last_48_hours(tmp_path, capsys):
    from datetime import UTC, datetime

    root = library_with_two_items(tmp_path)
    now = datetime.now(UTC)
    shown = f"{ZOJI} {EDIT}"
    ledger = Ledger()
    ledger.record("s1kept", now - timedelta(hours=3), "changed")
    record = tmp_path / "verified.json"
    record.write_bytes(ledger.dumps(now))
    checks = {_entry_name(embed_url(link(root, "s1kept"))): {"fetched_at": (now - timedelta(hours=3)).isoformat(),
                                                            "text": shown},
              _entry_name(embed_url(link(root, "s12note"))): {"fetched_at": (now - timedelta(hours=50)).isoformat(),
                                                             "text": "Too old to use."}}
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps({"written_at": now.isoformat(), "checks": checks}), encoding="utf-8")
    assert library.main(["apply-checks", "--ledger", str(record), "--bundle", str(bundle),
                         "--checks", str(tmp_path / "no checks")], folder=root) == 0
    out = capsys.readouterr().out
    assert comment(root, "s1kept").body == shown
    assert "Too old to use." not in (root / "threads" / f"{TID}.json").read_text()  # a read past 48 hours: never used
    assert "edited on Reddit: 1 kept Reddit's current text" in out and ZOJI not in out and "Edit:" not in out


def test_the_deploy_fetches_the_sites_reads_next_to_the_record_and_deletes_them_after():
    from engine.tests.test_cloudrun import DEPLOY_SH

    script = DEPLOY_SH.read_text(encoding="utf-8")
    fetch = script.index('$GCLOUD storage cp "gs://$BUCKET/live_check/bundle.json"')
    apply = script.index("-m engine.library apply-checks --ledger")
    assert fetch < apply < script.index('rm -rf "$(dirname "$RECORD")"') < script.index("-m deploy.cloudrun.make_context")
    assert script.count("$BUNDLE_READS") >= 2  # with the record, or without it


# --- restore-words: the backup's items, under the same rule ---

def test_restore_words_gives_back_the_items_still_found_in_reddits_current_text(tmp_path):
    root = a_library(tmp_path, [two_item_thread()], {TID: two_item_extraction()})
    backup = tmp_path / "backup" / "library"
    import shutil

    shutil.copytree(root, backup)
    assert slim_library(root, now=SLIMMED, gold_ids=set()).slimmed == [TID]
    ledger = Ledger()
    ledger.record("s1kept", day(8), "changed")
    apply_checks(root, ledger, now=day(8))  # dropped whole, as before 15 Oct
    assert comment(root, "s1kept").status == "not_kept"
    clock = Clock()
    clock.now = day(9)
    checker = LiveChecker(cache_dir=tmp_path / "checks", fetch=Embed(f"{ZOJI} {EDIT}"), clock=clock,
                          sleep=clock.sleep, min_interval=0)
    [restored] = restore_words(root, backup, [(TID, "s1kept")], checker)
    assert (restored.outcome, restored.items) == ("edited", 1)
    kept = comment(root, "s1kept")
    assert (kept.status, kept.body, kept.verified_at, kept.edited) == ("ok", f"{ZOJI} {EDIT}", day(9), "embed")
    assert [item.quote for item in items_of(extraction_of(root), "s1kept")] == [ZOJI]
    apply_checks(root, ledger, now=day(10))  # the next deploy, with the record's older "changed"
    assert comment(root, "s1kept").status == "ok"
