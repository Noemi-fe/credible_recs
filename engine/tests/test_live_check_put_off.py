"""The picks first (Noemi, 13 Oct 2026: "if the new section adds too much time, i'd rather not have that section but be
sure that the product i'm looking for is found").

The quotes of "Also worth a look" and the comments one-line summaries cite are checked live like every shown quote,
but never wait for Reddit's allowance (the checker's wait=False): a comment not saved that can't be read at once is
put off, and what it backs (the item, the summary) is left out of this answer, which is worked out again next time.
A put-off comment is never taken as failed: it keeps its votes, so the picks are the same as when everything is read.

Every library, product and summary here is made up; no test reads data/.
"""

from engine.answer import _every_quote, unverified_claims
from engine.live_check import LiveResult
from engine.pipeline import answer_request
from engine.tests.test_pick_polish import KNIFE_REQUEST
from engine.tests.test_pipeline import REQUEST, FakeLive, library
from engine.tests.test_pipeline_worth import TODAY, knives, picks, worth, write_summaries


class TightLive:
    """Reddit's allowance spent: a check that may wait is read (and passes); one that may not is put off."""

    def __init__(self):
        self.waited, self.put_off = [], []

    def check(self, url, quote, wait=True):
        comment_id = url.rstrip("/").split("/")[-1]
        (self.waited if wait else self.put_off).append(comment_id)
        return LiveResult("ok", "still there") if wait else LiveResult("later", "would have waited")


def test_also_worth_a_look_never_waits_and_never_changes_the_picks(tmp_path):
    lib = knives(tmp_path)
    everything = answer_request(KNIFE_REQUEST, library_dir=lib, prices=[], today=TODAY, live_checker=FakeLive())
    assert worth(everything) == ["Misono UX10 gyuto"]
    live = TightLive()
    tight = answer_request(KNIFE_REQUEST, library_dir=lib, prices=[], today=TODAY, live_checker=live)
    assert picks(tight) == picks(everything) and tight.answer.picks == everything.answer.picks
    assert worth(tight) == [] and tight.answer.worth_note is None
    assert {"u1a", "u2a"} & set(live.put_off) and not {"u1a", "u2a"} & set(live.waited)
    assert tight.live_put_off >= 1 and tight.live_dropped == {}
    assert unverified_claims(tight.answer, tight.bodies) == []


def test_the_picks_quotes_are_read_even_when_reddits_allowance_is_tight(tmp_path):
    live = TightLive()
    result = answer_request(KNIFE_REQUEST, library_dir=knives(tmp_path), prices=[], today=TODAY, live_checker=live)
    shown = {quote.comment_id for pick in result.answer.picks for quote in pick.quotes}
    assert shown and shown <= set(live.waited) and not shown & set(live.put_off)


def test_a_summary_citing_an_unshown_comment_is_left_out_when_it_would_wait(tmp_path):
    lib = library(tmp_path)
    before = answer_request(REQUEST, library_dir=lib)
    shown = {q.comment_id for _, q in _every_quote(before.answer)}
    zoji = next(p for p in before.ranking.products if p.name == "Zojirushi kettle")
    unshown = next(m.comment_id for m in zoji.credible_recommendations if m.comment_id not in shown)
    write_summaries(lib, [unshown], text="Owners say it keeps going.")
    everything = answer_request(REQUEST, library_dir=lib, live_checker=FakeLive())
    tight = answer_request(REQUEST, library_dir=lib, live_checker=TightLive())
    assert everything.answer.picks[0].summary is not None
    assert tight.answer.picks[0].summary is None  # left out, never shown on an unread comment
    assert [p.name for p in tight.answer.picks] == [p.name for p in everything.answer.picks]
    assert tight.live_put_off == 1 and tight.live_dropped == {}


def test_a_summary_citing_only_shown_comments_stays_when_reddits_allowance_is_tight(tmp_path):
    lib = library(tmp_path)
    write_summaries(lib, ["k1aaaa", "k2aaaa"])  # both quoted on the pick: read for the pick, so the summary is checked
    result = answer_request(REQUEST, library_dir=lib, live_checker=TightLive())
    assert result.answer.picks[0].summary is not None and result.live_put_off == 0


def test_nothing_is_put_off_when_every_comment_can_be_read(tmp_path):
    result = answer_request(KNIFE_REQUEST, library_dir=knives(tmp_path), prices=[], today=TODAY,
                            live_checker=FakeLive())
    assert result.live_put_off == 0 and worth(result) == ["Misono UX10 gyuto"]
