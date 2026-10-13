"""The sense evaluation (Noemi's note, 12 Oct 2026): every item an answer shows, listed, judged once, and counted.

All data is made up (engine/tests/ranking_factories.py and the made-up kettle library of test_pipeline.py).
"""

import json

from engine import answer as wording
from engine import sense_eval
from engine.answer import write_answer
from engine.care_tips import CareTip, CareTips
from engine.rank import rank_products
from engine.sense_eval import Item, Verdict, answer_items, collect, report_lines, to_judge
from engine.tests.ranking_factories import bodies_for, mention, mentions, note
from engine.tests.test_pipeline import REQUEST, library


def care_tip(tip: str, comment: str, is_kind: bool = False) -> CareTip:
    return CareTip(about="Acme kettle", is_kind=is_kind, tip=tip, quote=f"I {tip} and it still works.", thread_id="t1",
                   comment_id=comment, comment_url=f"https://www.reddit.com/r/test/comments/t1/comment/{comment}/",
                   voice="high")


def full_answer():
    """An answer with every kind of item: picks with quotes, a downside and a care tip, a kind to look for and one to
    avoid, a skipped product and the care note at the end."""
    items = (mentions(3, "Acme kettle") + [mention("Acme kettle", "t2", stance="warn", quote="The Acme kettle's lid sticks.")]
             + mentions(3, "Bolt kettle") + mentions(2, "Crumb kettle", stance="warn"))
    notes = [note("Steel kettle", "t1"), note("Steel kettle", "t2"), note("Plastic kettle", "t1", stance="warn")]
    own, kind = care_tip("descale it monthly", "cOWN"), care_tip("use filtered water", "cKIND", is_kind=True)
    ranking = rank_products(items, "kitchen", notes, {})
    bodies = bodies_for(*items, *notes) | {tip.comment_id: f"Well. {tip.quote}" for tip in (own, kind)}
    care = {"acme-kettle": CareTips([own], [kind])}
    return write_answer(ranking, bodies, "electric kettle", care=care)


def test_every_item_an_answer_shows_is_listed_under_its_heading():
    shown = answer_items(full_answer(), "k01", "a kettle that lasts")
    where = {(item.where, item.heading) for item in shown}
    assert {("pick quote", "Acme kettle"), ("pick quote", "Bolt kettle"), ("downside", "Acme kettle"),
            ("care tip", "Acme kettle"), ("look for", "Steel kettle"), ("avoid", "Plastic kettle"),
            ("skip", "Crumb kettle"), ("care note", "How to take care of your electric kettle")} <= where
    assert all(item.request == "a kettle that lasts" and item.request_id == "k01" for item in shown)
    tip = next(item for item in shown if item.where == "care tip")
    assert (tip.lead, tip.text) == ("Descale it monthly.", "I descale it monthly and it still works.")
    # A downside is read with the line above it (Noemi, 12 Oct 2026): how many credible voices warned, of all.
    downside = next(item for item in shown if item.where == "downside")
    assert downside.lead == "1 of 4 credible voices warned against it:"
    assert len(shown) == len({item.key for item in shown})


def test_an_items_key_changes_only_when_what_is_shown_changes():
    item = Item("k01", "a kettle that lasts", "pick quote", "Acme kettle", "", "Lasted 9 years.", "https://example.com/1")
    assert item.key == Item("k01", "a kettle that lasts", "pick quote", "Acme kettle", "", "Lasted 9 years.",
                            "https://example.com/other").key  # the link isn't what a reader judges
    assert item.key != Item("k01", "a kettle that lasts", "pick quote", "Acme kettle", "",
                            "Mine lasted 9 years. Lasted 9 years.", "https://example.com/1").key
    assert item.key != Item("k01", "a kettle that lasts", "downside", "Acme kettle", "", "Lasted 9 years.", "").key
    assert item.key != Item("k01", "a kettle that lasts", "pick quote", "Acme kettle", "About the Acme kettle:",
                            "Lasted 9 years.", "https://example.com/1").key


def test_saved_verdicts_are_reused_and_only_new_items_are_listed_for_judging():
    items = answer_items(full_answer(), "k01", "a kettle that lasts")
    verdicts = {items[0].key: Verdict(True, ""), items[1].key: Verdict(False, "says nothing about the kettle")}
    assert to_judge(items, verdicts) == items[2:]
    lines = report_lines(items, verdicts)
    assert lines[0] == f"{len(items)} items shown; 2 judged, 1 makes sense (50%); {len(items) - 2} still to judge"
    assert any("says nothing about the kettle" in line for line in lines)


def test_verdicts_are_saved_with_the_item_they_judge(tmp_path):
    items = answer_items(full_answer(), "k01", "a kettle that lasts")
    path = tmp_path / "verdicts.json"
    sense_eval.add_verdicts(path, {items[0].key: (False, "a reply with no name in it")}, items)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved[items[0].key]["sense"] is False and saved[items[0].key]["text"] == items[0].text
    assert sense_eval.load_verdicts(path) == {items[0].key: Verdict(False, "a reply with no name in it")}
    sense_eval.add_verdicts(path, {items[1].key: (True, "")}, items)  # later verdicts join the earlier ones
    assert set(sense_eval.load_verdicts(path)) == {items[0].key, items[1].key}


def test_each_request_is_answered_on_the_library_given_and_its_quotes_checked(tmp_path):
    found = collect([("k01", REQUEST)], library(tmp_path), profiles=None)
    assert found.items and {item.request_id for item in found.items} == {"k01"}
    assert found.unverified == {"k01": 0}
    assert found.picks["k01"][:1] == ["Zojirushi kettle"]


def test_the_requests_are_the_blind_test_questions_and_ten_more():
    requests = sense_eval.sense_requests()
    assert len(requests) == 20 and len({text for _, text in requests}) == 20
    assert requests[2] == ("b03", "retinol for a beginner with sensitive skin")
    assert {category for category in ("shampoo", "air fryer", "eye cream")
            if any(category in text for _, text in requests)} == {"shampoo", "air fryer", "eye cream"}


def test_the_look_for_heading_is_the_kind_and_its_advice_is_where_it_is():
    shown = answer_items(full_answer(), "k01", "a kettle that lasts")
    look = [item for item in shown if item.where in ("look for", "avoid")]
    assert {(item.where, item.heading) for item in look} == {("look for", "Steel kettle"), ("avoid", "Plastic kettle")}
    assert wording.LOOK_FOR == "Look for" and wording.AVOID == "Avoid"


def test_also_worth_a_look_items_and_summaries_are_judged_too():
    # Noemi's decisions 2 and 4 of 13 Oct 2026: what they show is judged like everything else an answer shows.
    from engine.summaries import Summary, current_version

    items = (mentions(3, "Acme kettle") + mentions(2, "Dune kettle")
             + [mention("Dune kettle", "t1", stance="warn", quote="The Dune kettle's spout drips.")])
    ranking = rank_products(items, "kitchen")
    acme = next(p for p in ranking.products if p.name == "Acme kettle")
    summary = Summary(product="Acme kettle", category="kitchen", text="Owners say it boils fast.",
                      cites=[acme.credible_recommendations[0].comment_id], written_at="2026-10-13T10:00:00Z",
                      writer="claude-code", instructions_version=current_version())
    answer = write_answer(ranking, bodies_for(*items), "electric kettle", summaries={"kitchen:acme kettle": summary})
    shown = answer_items(answer, "k01", "a kettle that lasts")
    where = [(item.where, item.heading) for item in shown]
    assert ("worth quote", "Dune kettle") in where and ("worth downside", "Dune kettle") in where
    assert where.index(("summary", "Acme kettle")) < where.index(("pick quote", "Acme kettle"))  # under the name
    assert where.index(("pick quote", "Acme kettle")) < where.index(("worth quote", "Dune kettle"))
    item = next(item for item in shown if item.where == "summary")
    assert (item.lead, item.text) == (wording.SUMMARY_LABEL, "Owners say it boils fast.")
    downside = next(item for item in shown if item.where == "worth downside")
    assert downside.lead == "1 of 3 credible voices warned against it:"


def test_summaries_are_read_from_the_file_they_are_written_in_not_the_frozen_snapshot(tmp_path):
    # The snapshot was frozen before summaries existed (13 Oct 2026); they are written in data/library/summaries.json.
    import json as _json

    from engine.summaries import current_version

    written = tmp_path / "summaries.json"
    written.write_text(_json.dumps({"kitchen:zojirushi kettle": {
        "product": "Zojirushi kettle", "category": "kitchen", "product_type": "electric kettle",
        "text": "Owners of 6 years say it still boils fast.", "cites": ["k1aaaa"], "written_at": "2026-10-13T10:00:00Z",
        "writer": "claude-code", "instructions_version": current_version()}}), encoding="utf-8")
    found = collect([("k01", REQUEST)], library(tmp_path), profiles=None, summaries_file=written)
    summaries = [item for item in found.items if item.where == "summary"]
    assert [(item.heading, item.text) for item in summaries] == [("Zojirushi kettle",
                                                                  "Owners of 6 years say it still boils fast.")]
