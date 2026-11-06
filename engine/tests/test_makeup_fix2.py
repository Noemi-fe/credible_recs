"""Fix 2 after the profile warm (5 Nov 2026, past midnight; Claude's technical calls, reported to Noemi): what the
rules review, the shopper review and the summary fact-check of fix 1 still found. Which tips and quotes a makeup answer
shows, a discontinued bronzer checked as no longer sold, a maker's spelling, and the last paths by which the two
threads Noemi said to remove could come back. None changes a scoring weight, a product type or the picks bar.

Every comment, quote and product here is made up, but for real product names in the naming and price tests (names
only).
"""

import json

import pytest

from engine import config
from engine.answer import _stands_alone, write_answer
from engine.needs import judged_needs
from engine.query import parse_query
from engine.rank import rank_products
from engine.tests.ranking_factories import bodies_for, mention, mentions, note

OILY = judged_needs(parse_query("foundation for oily skin", model=None))
SUNSCREEN_OILY = judged_needs(parse_query("sunscreen for oily skin", model=None))


def kinds_shown(answer) -> list[str]:
    return [kind for item in answer.look_for for kind in item.kind.split(" or ")]


def two_notes(kind: str, first: str, second: str) -> list:
    return [note(kind, "t1", quote=first), note(kind, "t2", quote=second)]


def foundation_answer(notes, request="foundation for oily skin", needs=OILY):
    items = (mentions(3, "Velo foundation", category="general")
             + mentions(3, "Halo foundation", category="general"))
    return write_answer(rank_products(items, "general", notes), bodies_for(*items, *notes), "foundation",
                        request=request, needs=needs)


# --- Tips, with a need asked (the shopper review: "Look for: cream foundation stick" for oily skin) ---

def test_with_a_need_asked_a_makeup_look_for_saying_nothing_of_it_is_left_out():
    notes = two_notes("cream foundation stick", "A cream foundation stick gives a quick, sheer base.",
                      "I keep a cream foundation stick in my bag for touch-ups.")
    assert "cream foundation stick" not in kinds_shown(foundation_answer(notes))


def test_a_makeup_look_for_whose_comment_talks_about_the_need_stays():
    notes = two_notes("powder foundation", "Powder foundation keeps my oily skin matte until the evening.",
                      "Since switching over, powder foundation stops my oily skin shining by lunch.")
    assert "powder foundation" in kinds_shown(foundation_answer(notes))


def test_a_makeup_look_for_whose_own_name_names_the_need_stays():
    notes = two_notes("oil-control foundation", "An oil-control foundation was the answer for me.",
                      "Get an oil-control foundation and skip the rest.")
    assert "oil-control foundation" in kinds_shown(foundation_answer(notes))


def test_without_a_need_asked_a_makeup_look_for_needs_no_sign_of_one():
    notes = two_notes("cream foundation stick", "A cream foundation stick gives a quick, sheer base.",
                      "I keep a cream foundation stick in my bag for touch-ups.")
    assert "cream foundation stick" in kinds_shown(foundation_answer(notes, request="foundation", needs=()))


def test_outside_makeup_a_look_for_needs_no_sign_of_the_need():
    items = (mentions(3, "Velo sunscreen", category="skincare") + mentions(3, "Halo sunscreen", category="skincare"))
    notes = two_notes("gel sunscreen", "A gel sunscreen sinks in fast under makeup.",
                      "Gel sunscreens are the lightest I have tried.")
    answer = write_answer(rank_products(items, "skincare", notes), bodies_for(*items, *notes), "sunscreen",
                          request="sunscreen for oily skin", needs=SUNSCREEN_OILY)
    assert "gel sunscreen" in kinds_shown(answer)


# --- Tips: another makeup type worn as the type asked for stays (part 2's rule, kept) ---

def test_a_makeup_look_for_of_another_makeup_type_worn_as_this_one_stays():
    # Tried in fix 2 and dropped the same night: leaving out "pressed powder in a darker shade as bronzer" (the shopper
    # review, not blocking) would also have left out part 2's "bronzer worn as blush", which its test keeps on purpose
    # (engine/tests/test_answer_shows.py). Part 2's rule stands: a makeup tip naming this type too stays.
    items = (mentions(3, "Velo bronzer", category="general") + mentions(3, "Halo bronzer", category="general"))
    kind = "darker face powder as bronzer"
    notes = two_notes(kind, "A darker face powder works as a bronzer on my cool skin.",
                      "My face powder two shades deep is all the bronzer I need.")
    answer = write_answer(rank_products(items, "general", notes), bodies_for(*items, *notes), "bronzer",
                          request="bronzer")
    assert kind in kinds_shown(answer)


def test_a_makeup_look_for_of_a_kind_of_the_type_stays():
    items = (mentions(3, "Velo bronzer", category="general") + mentions(3, "Halo bronzer", category="general"))
    notes = two_notes("cream bronzer", "A cream bronzer melts in far better.", "Cream bronzer is easier to blend.")
    answer = write_answer(rank_products(items, "general", notes), bodies_for(*items, *notes), "bronzer",
                          request="bronzer")
    assert "cream bronzer" in kinds_shown(answer)


# --- Quotes thanking the thread (the shopper review: the Benefit brow gel pick led with one) ---

@pytest.mark.parametrize("quote", [
    "Many thanks to everybody who recommended the Rosa brow gel, it arrived yesterday and works well.",
    "Thanks to everyone who recommended the Rosa brow gel, it holds all day.",
    "Thanks all for the suggestions, the Rosa brow gel is great.",
    "Thank you so much everybody, I got the Rosa brow gel and love it.",
])
def test_a_quote_thanking_the_thread_leans_on_it(quote):
    assert not _stands_alone(quote, names_it=True)


@pytest.mark.parametrize("quote", [
    "Thanks to the Rosa brow gel my brows stay put all day.",
    "I thank my lucky stars for the Rosa brow gel, it never flakes.",
    "Everyone who sees my brows asks about the Rosa brow gel.",
    "Thanks to all the wax in it, the Rosa brow gel never flakes.",
])
def test_thanks_that_answer_no_one_still_stand(quote):
    assert _stands_alone(quote, names_it=True)


def test_a_pick_leads_with_a_clearer_quote_than_one_thanking_the_thread():
    thanks = mention("Rosa brow gel", "t1", category="general", weight=2.0,
                     quote="Big thanks to all of you who mentioned the Rosa brow gel, it holds my thick brows all day.")
    clear = mention("Rosa brow gel", "t2", category="general", weight=0.5,
                    quote="The Rosa brow gel holds my thick brows in place all day without crunch.")
    other = mention("Rosa brow gel", "t1", category="general", weight=0.5,
                    quote="I reach for the Rosa brow gel every morning, it keeps my brows neat.")
    items = [thanks, clear, other] + mentions(3, "Halo brow gel", category="general")
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "brow gel", request="brow gel")
    [rosa] = [pick for pick in answer.picks if pick.name == "Rosa brow gel"]
    shown = [quote.comment_id for quote in rosa.quotes]
    assert shown[0] != thanks.comment_id and set(shown[:2]) == {clear.comment_id, other.comment_id}


def test_a_quote_only_liking_its_product_by_a_plural_of_its_name_is_a_bare_like():
    # The Benefit brow gel pick's lead quote liked the brand by its plural and said nothing more: the plural of the
    # brand is its name, not a reason.
    from engine.answer import _bare_like
    assert _bare_like(mention("Rosa brow gel", "t1", category="general", quote="I like Rosas"))
    assert _bare_like(mention("Rosa brow gel", "t1", category="general", quote="I like Rosa"))  # as before
    assert not _bare_like(mention("Rosa brow gel", "t1", category="general", quote="I like Rosas for thick brows"))


def test_a_pick_leads_with_a_reason_before_a_plural_bare_like():
    bare = mention("Rosa brow gel", "t1", category="general", weight=2.0, quote="I like Rosas")
    why = mention("Rosa brow gel", "t2", category="general", weight=0.5,
                  quote="The Rosa brow gel holds my thick brows in place all day without crunch.")
    third = mention("Rosa brow gel", "t1", category="general", weight=0.5,
                    quote="I reach for the Rosa brow gel every morning, it keeps my brows neat.")
    items = [bare, why, third] + mentions(3, "Halo brow gel", category="general")
    answer = write_answer(rank_products(items, "general"), bodies_for(*items), "brow gel", request="brow gel")
    [rosa] = [pick for pick in answer.picks if pick.name == "Rosa brow gel"]
    assert rosa.quotes[0].comment_id != bare.comment_id


# --- Names ---

def test_ysl_lash_clash_as_its_maker_writes_it():
    from engine.group_products import maker_spelling
    assert maker_spelling("YSL lash clash", "general") == "YSL Lash Clash"


# --- The price list: the original Marc Jacobs bronzer ---

def test_the_original_marc_jacobs_bronzer_is_checked_as_no_longer_sold():
    from engine.prices import DEFAULT_PRICES, counts_as_sold, find_availability, load_prices
    prices = load_prices(DEFAULT_PRICES)
    entry = find_availability("Marc Jacobs bronzer", "general", prices, "bronzer")
    assert entry is not None and entry.available is False and counts_as_sold(entry) is False
    # It speaks for the bronzer only: the brand's mascara is another product.
    assert find_availability("Marc Jacobs Velvet Noir mascara", "general", prices, "mascara") is None


# --- Noemi's "Remove those 2 threads": the last paths ---

def test_pull_never_brings_a_removed_thread_into_the_library_nor_logs_it(tmp_path):
    from engine import on_demand
    from engine.live_check import Bucket
    from engine.on_demand import Bundle, BundleStore, Item, pull
    from engine.tests.fake_google import FakeGoogle
    from engine.tests.on_demand_fakes import NOW
    from engine.tests.test_web import kettle_library

    google = FakeGoogle()
    bucket = Bucket("credible-test-on-demand", request=google, clock=lambda: 0.0, prefix=on_demand.PREFIX)
    removed = config.REMOVED_THREADS[0]

    def two(bundle: Bundle):
        for tid in (removed, "1kept01"):
            bundle.threads[tid] = Item(thread='{"made": "up"}', extraction='{"made": "up"}', entry="general/blush/",
                                       product_type="blush", added_at=NOW.isoformat())

    BundleStore(bucket).change(two)
    local = kettle_library(tmp_path)
    report = pull(bucket, local, now=lambda: NOW)
    assert report.pulled == ["1kept01"] and report.waiting == 0 and report.kept_local == []
    assert not (local / "threads" / f"{removed}.json").exists()
    logged = [json.loads(line) for line in (local / "requests.jsonl").read_text(encoding="utf-8").splitlines()]
    assert all(removed not in entry["thread_ids"] for entry in logged)


def test_bright_data_refuses_to_read_a_removed_thread_into_the_library(tmp_path, monkeypatch, capsys):
    from engine import bright_data

    class NoCalls:
        def get_thread(self, link):
            raise AssertionError("a removed thread must be refused before anything is spent")

        def records_used_this_month(self):
            return 0

    removed = config.REMOVED_THREADS[0]
    monkeypatch.setattr(bright_data, "LIBRARY_THREADS_DIR", tmp_path / "library" / "threads")
    status = bright_data.main(["fetch", f"https://www.reddit.com/r/MakeupRehab/comments/{removed}/",
                               "--to", str(tmp_path / "library" / "threads")], client=NoCalls())
    assert status == 1
    assert removed in capsys.readouterr().out
    assert not (tmp_path / "library" / "threads" / f"{removed}.json").exists()


def test_a_removed_thread_read_on_an_earlier_try_takes_no_place_in_its_requests_round(tmp_path, monkeypatch):
    # Fix 1 left a removed thread out of on-demand reading's fresh posts even when the bundle holds it under the same
    # request (engine.on_demand._read_entry): it is never written into a library, so it takes no community's place in
    # the round, and the round reads as though the thread was never there. Here 1tea002 stands in for a removed thread.
    # Changed on purpose on 6 Nov 2026 (round 3, from the rules review of fix 2): with seven threads in one community
    # the communities' caps held the round back, so the test passed while the removed thread still counted among the
    # request's own threads (one place fewer, and its Gemini calls spent). Now twelve more threads across both teapot
    # communities give the round more than the caps allow, and _read_entry leaves the removed thread out of its own.
    from engine import on_demand
    from engine.live_check import Bucket
    from engine.on_demand import Bundle, BundleStore, Item, QueueStore, entry_for, run_job
    from engine.tests import on_demand_fakes
    from engine.tests.fake_google import FakeGoogle
    from engine.tests.on_demand_fakes import NOW, FakeArchive, FakeGemini, Ticks, archive, gemini
    from engine.tests.test_web import kettle_library

    communities = parse_query("teapot for loose leaf tea").subreddits
    for n in range(4, 16):
        monkeypatch.setitem(on_demand_fakes.TEAPOT_THREADS, f"1tea{n:03d}", (
            communities[n % len(communities)], f"Teapot number {n} worth it?",
            [(f"t{n}a", f"My Brown Betty teapot has lasted {n} years.", "Brown Betty teapot")]))
    every = tuple(on_demand_fakes.TEAPOT_THREADS)
    monkeypatch.setattr(on_demand, "REMOVED_THREADS", ("1tea002",))

    def a_round(folder, with_removed: bool):
        google = FakeGoogle()
        bucket = Bucket("credible-test-on-demand", request=google, clock=lambda: 0.0, prefix=on_demand.PREFIX)
        entry = entry_for(parse_query("teapot for loose leaf tea"), had=0)
        if with_removed:
            BundleStore(bucket).change(lambda b: b.threads.update({"1tea002": Item(
                thread="{}", extraction="{}", entry=entry.key, product_type="teapot", added_at=NOW.isoformat())}))
        QueueStore(bucket).change(lambda queue: queue.add(entry) and None)
        folder.mkdir()
        fake = FakeArchive(threads=every)
        run_job(bucket, kettle_library(folder), archive(folder, fake), gemini(FakeGemini()), now=lambda: NOW,
                clock=Ticks(), work_dir=folder / "work")
        read = sorted(tid for tid in Bundle.from_json(google.read("credible-test-on-demand", on_demand.PREFIX
                                                                  + "threads.json")).threads if tid != "1tea002")
        return read, fake

    with_it, fake = a_round(tmp_path / "with", True)
    without_it, _ = a_round(tmp_path / "without", False)
    assert with_it == without_it  # before fix 1 it took one of r/BuyItForLife's places: one thread fewer was read
    assert not any("ids=1tea002" in url for url in fake.requests)  # and it is never read again
