"""The thin end-to-end slice: a request typed in plain words goes through modules 1 to 7 and comes back as a top 3.

A made-up library of two kettle threads, written to a temporary folder with their extraction files, so no test
reads data/.
"""

import json
from datetime import date, timedelta
from pathlib import Path

from engine import answer as answer_wording
from engine import pipeline
from engine.answer import unverified_claims
from engine.config import PRICE_MAX_AGE_DAYS
from engine.pipeline import answer_request
from engine.prices import Price
from engine.tests.factories import make_comment, make_thread, write_gold

REQUEST = "electric kettle that lasts 10+ years"


def kettle_thread(thread_id: str, comments: list[dict]) -> dict:
    return make_thread(
        id=thread_id, community="BuyItForLife", category="kitchen", title="Which electric kettle lasts?",
        body="My kettle died again.", url=f"https://www.reddit.com/r/BuyItForLife/comments/{thread_id}/kettle/",
        comments=comments,
    )


def comment(comment_id: str, thread_id: str, body: str, **overrides) -> dict:
    url = f"https://www.reddit.com/r/BuyItForLife/comments/{thread_id}/comment/{comment_id}/"
    return make_comment(comment_id, thread_id=thread_id, body=body, url=url, **overrides)


def mention(comment_id: str, product: str, quote: str, stance: str = "recommend", category: str = "kitchen") -> dict:
    return {"comment_id": comment_id, "product": product, "category": category, "stance": stance, "quote": quote}


ZOJI_1 = "My Zojirushi kettle has lasted 6 years and still boils perfectly."
ZOJI_2 = "Had my Zojirushi kettle for 4 years now, no problems at all."
ZOJI_3 = "Our Zojirushi kettle is 8 years old and still going strong."
ZOJI_4 = "I've used the Zojirushi kettle daily for 5 years."
LODGE = "My Lodge cast iron skillet has lasted 20 years."
CHEFMAN_1 = "The Chefman kettle died after 6 months of use."
CHEFMAN_2 = "Two Chefman kettles broke within a year of use, avoid them."
HARIO_1 = "My Hario Skerton has ground beans for my kettle pour-overs for 5 years."
HARIO_2 = "I've used a Hario Skerton for 3 years, still great with a gooseneck kettle."
HARIO_3 = "Hario Skerton for 4 years, heat the kettle while you grind."


def library(tmp_path: Path) -> Path:
    """Two kettle threads: the Zojirushi praised four times across both, a skillet praised, the Chefman warned against."""
    threads = [
        kettle_thread("1kett01", [
            comment("k1aaaa", "1kett01", ZOJI_1),
            comment("k1bbbb", "1kett01", ZOJI_2),
            comment("k1cccc", "1kett01", LODGE),
            comment("k1dddd", "1kett01", CHEFMAN_1),
        ]),
        kettle_thread("1kett02", [
            comment("k2aaaa", "1kett02", ZOJI_3),
            comment("k2bbbb", "1kett02", ZOJI_4),
            comment("k2cccc", "1kett02", CHEFMAN_2),
        ]),
    ]
    # A coffee thread whose comments mention a kettle in passing: not about kettles, so never read for one.
    threads.append(make_thread(
        id="1coff01", community="Coffee", category="kitchen", title="Which hand grinder should I get?",
        body="Budget is about 100.", url="https://www.reddit.com/r/Coffee/comments/1coff01/grinder/",
        comments=[comment("c1aaaa", "1coff01", HARIO_1), comment("c1bbbb", "1coff01", HARIO_2),
                  comment("c1cccc", "1coff01", HARIO_3)],
    ))
    root = write_gold(tmp_path / "library", threads, voices=None, mentions=None)
    extractions = {
        "1kett01": [mention("k1aaaa", "Zojirushi kettle", ZOJI_1), mention("k1bbbb", "Zojirushi kettle", ZOJI_2),
                    mention("k1cccc", "Lodge cast iron skillet", LODGE), mention("k1dddd", "Chefman kettle", CHEFMAN_1, "warn")],
        "1kett02": [mention("k2aaaa", "Zojirushi kettle", ZOJI_3), mention("k2bbbb", "Zojirushi kettle", ZOJI_4),
                    mention("k2cccc", "Chefman kettle", CHEFMAN_2, "warn")],
        "1coff01": [mention("c1aaaa", "Hario Skerton", HARIO_1), mention("c1bbbb", "Hario Skerton", HARIO_2),
                    mention("c1cccc", "Hario Skerton", HARIO_3)],
    }
    (root / "extracted").mkdir()
    for thread_id, mentions in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v5", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions,
        }), encoding="utf-8")
    return root


def test_a_request_comes_back_as_picks_with_verified_quotes(tmp_path):
    result = answer_request(REQUEST, library_dir=library(tmp_path))
    assert result.query.product_type == "electric kettle"
    assert [pick.name for pick in result.answer.picks][:1] == ["Zojirushi kettle"]
    assert sorted(result.threads_used) == ["1kett01", "1kett02"]
    assert unverified_claims(result.answer, result.bodies) == []


def test_products_of_another_type_are_left_out(tmp_path):
    # A skillet praised in a kettle thread is a real product, but not an answer to a kettle request.
    result = answer_request(REQUEST, library_dir=library(tmp_path))
    names = [p.name for p in result.ranking.products]
    assert "Lodge cast iron skillet" not in names
    assert "Lodge cast iron skillet" in result.left_out_as_other_type


def test_a_product_warned_against_twice_is_never_a_pick(tmp_path):
    result = answer_request(REQUEST, library_dir=library(tmp_path))
    assert "Chefman kettle" not in [pick.name for pick in result.answer.picks]


def test_a_request_that_needs_a_question_fetches_nothing(tmp_path):
    result = answer_request("something nice for my mum", library_dir=library(tmp_path))
    assert result.query.status == "clarify" and result.answer is None and result.threads_used == []


def test_the_answer_reads_as_text(tmp_path):
    text = answer_request(REQUEST, library_dir=library(tmp_path)).text()
    assert "Zojirushi kettle" in text and ZOJI_1 in text


def test_only_threads_about_the_product_are_read(tmp_path):
    # Its title or post must name the product: a coffee thread mentioning kettles in passing isn't about kettles.
    result = answer_request(REQUEST, library_dir=library(tmp_path))
    assert "1coff01" not in result.threads_used
    assert "Hario Skerton" not in [p.name for p in result.ranking.products]


class FakeProfiles:
    """Profiles as the cache would give them: every writer an old, active, well-regarded account."""

    def user_stats(self, author):
        return {"num_comments": 2000, "num_posts": 20, "total_karma": 30000, "earliest_comment_at": 1400000000}

    def comment_flairs(self, comment_ids):
        return {}


def plain_writers_library(tmp_path: Path) -> Path:
    """The kettle library, with writers known only by name, as Parse saves them."""
    root = library(tmp_path)
    for path in (root / "threads").glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        for c in data["comments"]:
            c["author"] = {"name": c["author"]["name"]}
        path.write_text(json.dumps(data), encoding="utf-8")
    return root


def test_profiles_from_the_cache_raise_the_writers_standing(tmp_path):
    lib = plain_writers_library(tmp_path)
    without = answer_request(REQUEST, library_dir=lib)
    with_profiles = answer_request(REQUEST, library_dir=lib, profiles=FakeProfiles())
    zoji = lambda result: next(p for p in result.ranking.products if p.name == "Zojirushi kettle")
    assert zoji(without).breakdown.recommend_voices["high"] < zoji(with_profiles).breakdown.recommend_voices["high"]


# --- Decisions of 9 Oct 2026: brand-only picks (9), budgets (11) and the UK name (12) ---

TODAY = date(2026, 10, 9)


def write_library(tmp_path: Path, threads: dict[str, tuple[str, str, list[tuple]]], community: str = "castiron") -> Path:
    """A made-up library: {thread id: (title, post, [(comment id, product, text, stance)])}.

    Each comment's text is also its quote, so every quote is found word for word.
    """
    saved, extractions = [], {}
    for thread_id, (title, body, comments) in threads.items():
        url = f"https://www.reddit.com/r/{community}/comments/{thread_id}/thread/"
        saved.append(make_thread(id=thread_id, community=community, category="kitchen", title=title, body=body, url=url,
                                 comments=[comment(cid, thread_id, text) for cid, _, text, _ in comments]))
        extractions[thread_id] = [mention(cid, product, text, stance) for cid, product, text, stance in comments]
    root = write_gold(tmp_path / "library", saved, voices=None, mentions=None)
    (root / "extracted").mkdir()
    for thread_id, mentions in extractions.items():
        (root / "extracted" / f"{thread_id}.json").write_text(json.dumps({
            "thread_id": thread_id, "instructions_version": "extract-v5", "extracted_at": "2026-10-09T10:00:00Z",
            "extractor": "claude-code", "mentions": mentions,
        }), encoding="utf-8")
    return root


def praise(comment_id: str, product: str, years: int) -> tuple:
    return comment_id, product, f"My {product} has lasted {years} years and still works perfectly.", "recommend"


def skillet_library(tmp_path: Path) -> Path:
    """Skillet threads. "Lodge" and "Smithey" are brand names that fit two skillets each (so grouping marks them
    loose); "All-Clad" fits two pans, neither a skillet; "the one" names nothing; "Le Creuset dutch oven" is a line
    of another type of product."""
    return write_library(tmp_path, {
        "1skil01": ("Best cast iron skillet for a beginner?", "My first one.", [
            praise("s1a", "Lodge", 20), praise("s1b", "Lodge", 12),
            praise("s1c", "Lodge Blacklock skillet", 3), praise("s1d", "Lodge Chef Collection skillet", 4),
            praise("s1e", "Smithey", 5), praise("s1f", "Smithey", 6),
            praise("s1g", "Smithey No. 10 skillet", 2), praise("s1h", "Smithey No. 12 skillet", 2),
            praise("s1i", "the one", 30), praise("s1j", "the one", 25),
            praise("s1k", "Le Creuset dutch oven", 10), praise("s1l", "Le Creuset dutch oven", 11),
            praise("s1m", "Le Creuset 5.5 qt dutch oven", 3), praise("s1n", "Le Creuset 7 qt dutch oven", 3),
            praise("s1o", "All-Clad", 9), praise("s1p", "All-Clad", 8),
            praise("s1q", "All-Clad stainless", 4), praise("s1r", "All-Clad non-stick", 2),
        ]),
        "1skil02": ("Which cast iron skillet lasts?", "Mine cracked.", [
            praise("s2a", "Lodge", 15), praise("s2b", "the one", 40), praise("s2c", "Le Creuset dutch oven", 9),
            praise("s2d", "All-Clad", 7),
        ]),
        # Read (its post names a skillet), but its title doesn't: what it says about a brand is less clear.
        "1skil03": ("What should I cook my first steak in?", "Thinking of a cast iron skillet.", [
            praise("s3a", "Smithey", 7), praise("s3b", "Smithey", 8),
        ]),
    })


def test_a_brand_whose_threads_make_the_product_clear_is_a_pick_named_as_a_brand(tmp_path):
    result = answer_request("cast iron skillet that lasts", library_dir=skillet_library(tmp_path), prices=[], today=TODAY)
    assert "Lodge (their cast iron skillets)" in [pick.name for pick in result.answer.picks]
    assert "Lodge" not in result.left_out_loose
    assert unverified_claims(result.answer, result.bodies) == []


def test_a_brand_mentioned_mostly_in_threads_about_something_else_stays_out(tmp_path):
    # Smithey: 4 credible recommendations across 2 threads, but only half of them in threads whose title names a
    # skillet. More than half is needed.
    result = answer_request("cast iron skillet that lasts", library_dir=skillet_library(tmp_path), prices=[], today=TODAY)
    assert "Smithey" in result.left_out_loose
    assert not any("Smithey" in p.name and "their" in p.name for p in result.ranking.products)


def test_a_line_of_another_type_or_a_name_that_names_nothing_stays_out(tmp_path):
    result = answer_request("cast iron skillet that lasts", library_dir=skillet_library(tmp_path), prices=[], today=TODAY)
    assert {"Le Creuset dutch oven", "the one"} <= set(result.left_out_loose)
    assert not any("their" in p.name and p.name != "Lodge (their cast iron skillets)" for p in result.ranking.products)


def test_a_brand_none_of_whose_products_here_is_of_the_type_stays_out(tmp_path, monkeypatch):
    # Found in the library on 9 Oct 2026: All-Clad, praised in cast iron threads for its stainless and non-stick
    # pans, would be shown as "All-Clad (their cast iron skillets)". At least one of the brand's own products named
    # in the threads must be of the requested type ("Lodge Blacklock skillet").
    lib = skillet_library(tmp_path)
    result = answer_request("cast iron skillet that lasts", library_dir=lib, prices=[], today=TODAY)
    assert "All-Clad" in result.left_out_loose
    monkeypatch.setattr(pipeline, "BRAND_PICK_NEEDS_A_PRODUCT_OF_THE_TYPE", False)
    loose_rule_only = answer_request("cast iron skillet that lasts", library_dir=lib, prices=[], today=TODAY)
    assert "All-Clad (their cast iron skillets)" in [pick.name for pick in loose_rule_only.answer.picks]


def test_brand_picks_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "PIPELINE_BRAND_PICKS", False)
    result = answer_request("cast iron skillet that lasts", library_dir=skillet_library(tmp_path), prices=[], today=TODAY)
    assert "Lodge" in result.left_out_loose
    assert not any("their" in p.name for p in result.ranking.products)


def made_up_price(product: str, amount: float, checked_on: date = TODAY, currency: str = "GBP") -> Price:
    return Price(product=product, category="kitchen", price=amount, currency=currency, shop="Made-up Kitchen Shop",
                 url="https://shop.example/" + product.lower().replace(" ", "-"), checked_on=checked_on)


def test_a_product_over_the_budget_is_left_out_and_listed(tmp_path):
    result = answer_request("electric kettle under £100", library_dir=library(tmp_path),
                            prices=[made_up_price("Zojirushi kettle", 120.0)], today=TODAY)
    assert result.left_out_over_budget == ["Zojirushi kettle"]
    assert "Zojirushi kettle" not in [p.name for p in result.ranking.products]
    assert "Zojirushi" not in result.text()


def test_a_product_within_the_budget_shows_its_price_shop_and_date(tmp_path):
    result = answer_request("electric kettle under £100", library_dir=library(tmp_path),
                            prices=[made_up_price("Zojirushi kettle", 80.0)], today=TODAY)
    pick = result.answer.picks[0]
    assert pick.name == "Zojirushi kettle" and result.left_out_over_budget == []
    assert pick.price.amount == 80.0 and pick.price.shop == "Made-up Kitchen Shop"
    assert pick.price.url == "https://shop.example/zojirushi-kettle" and pick.price.checked_on == "2026-10-09"
    assert pick.price.budget_status == "within"


def test_a_product_with_no_known_price_is_kept_and_marked(tmp_path):
    result = answer_request("electric kettle under £100", library_dir=library(tmp_path), prices=[], today=TODAY)
    pick = result.answer.picks[0]
    assert pick.name == "Zojirushi kettle"
    assert pick.price.amount is None and pick.price.text == answer_wording.PRICE_UNKNOWN
    assert pick.price.budget_status == "unknown" and pick.price.budget_note


def test_an_old_price_is_shown_but_never_leaves_a_product_out(tmp_path):
    old = TODAY - timedelta(days=PRICE_MAX_AGE_DAYS + 1)
    result = answer_request("electric kettle under £100", library_dir=library(tmp_path),
                            prices=[made_up_price("Zojirushi kettle", 120.0, checked_on=old)], today=TODAY)
    pick = result.answer.picks[0]
    assert pick.name == "Zojirushi kettle" and result.left_out_over_budget == []
    assert pick.price.amount == 120.0 and pick.price.checked_on == old.isoformat()
    assert pick.price.budget_status == "out of date"


def test_a_price_in_another_currency_is_kept_and_marked(tmp_path):
    result = answer_request("electric kettle under £100", library_dir=library(tmp_path),
                            prices=[made_up_price("Zojirushi kettle", 500.0, currency="EUR")], today=TODAY)
    assert result.answer.picks[0].price.budget_status == "other currency"


def test_without_a_budget_a_known_price_is_still_shown(tmp_path):
    result = answer_request(REQUEST, library_dir=library(tmp_path), prices=[made_up_price("Zojirushi kettle", 120.0)],
                            today=TODAY)
    pick = result.answer.picks[0]
    assert pick.price.amount == 120.0 and pick.price.budget_status is None and pick.price.budget_note is None


def test_a_brand_pick_has_no_single_price_so_a_budget_never_leaves_it_out(tmp_path):
    result = answer_request("cast iron skillet under £50", library_dir=skillet_library(tmp_path),
                            prices=[made_up_price("Lodge", 500.0)], today=TODAY)
    lodge = next(pick for pick in result.answer.picks if pick.name == "Lodge (their cast iron skillets)")
    assert lodge.price.amount is None and lodge.price.budget_status == "unknown"


def test_the_uk_name_sage_is_shown_rather_than_breville(tmp_path):
    lib = write_library(tmp_path, {
        "1kett01": ("Which electric kettle lasts?", "Mine died.", [praise("k1a", "Breville IQ kettle", 6),
                                                                    praise("k1b", "Breville IQ kettle", 7)]),
        "1kett02": ("Electric kettle advice", "Need a new one.", [praise("k2a", "Sage IQ kettle", 5)]),
    }, community="BuyItForLife")
    result = answer_request("electric kettle under £100", library_dir=lib, prices=[made_up_price("Sage IQ kettle", 90.0)],
                            today=TODAY)
    assert [pick.name for pick in result.answer.picks] == ["Sage IQ kettle"]
    assert result.answer.picks[0].price.budget_status == "within"
    assert "## 1. Sage IQ kettle" in result.text()  # the quotes keep their own words: they are never changed
