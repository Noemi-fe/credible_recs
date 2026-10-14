"""Module 4, kinds of product: the AI's notes ("carbon steel pan", "hand grinder for espresso") grouped by the kind
they are about, and each product group placed in the kinds its name names.

Kinds are made up or copied from the library's notes (the kind only, never comment text).
"""

from engine.extract import CheckResult, ExtractedNote
from engine.group_kinds import KindMention, group_kinds, kind_parts, kinds_of, notes_from_checked, placements
from engine.group_products import ProductMention, group_products
from engine.match_products import make_aliases

NO_ALIASES = {"skincare": {}, "kitchen": {}, "other": {}}
KITCHEN_KINDS = {**NO_ALIASES, "kitchen": make_aliases({"skillet": "pan", "frying pan": "pan", "Teflon": "nonstick"})}


def note(about: str, stance: str = "recommend", comment_id: str = "c1aaaa", thread_id: str = "1fake01") -> KindMention:
    return KindMention(thread_id=thread_id, comment_id=comment_id, about=about, stance=stance)


def kinds(notes, products=(), product_type="", category="kitchen", aliases=KITCHEN_KINDS):
    return group_kinds(list(notes), list(products), category, product_type, aliases)


def products(*names, category="kitchen"):
    mentions = [ProductMention("1fake01", f"c{i}", name, category, "recommend") for i, name in enumerate(names)]
    return group_products(mentions, NO_ALIASES)


def abouts(groups) -> list[list[str]]:
    return sorted(sorted(n.about for n in g.notes) for g in groups)


# --- What a note's kind is ---

def test_a_purpose_or_a_condition_after_the_kind_is_left_out():
    assert kind_parts("hand grinder for espresso", "", {}) == [["hand", "grinder"]]
    assert kind_parts("mineral powder over sunscreen", "", {}) == [["mineral", "powder"]]


def test_words_about_price_or_quality_are_left_out():
    assert kind_parts("cheap hand grinder", "", {}) == [["hand", "grinder"]]
    assert kind_parts("$50 burr grinder", "", {}) == [["burr", "grinder"]]


def test_two_kinds_joined_by_or_are_two_kinds():
    assert kind_parts("cast iron or carbon steel pan", "frying pan", KITCHEN_KINDS["kitchen"]) == [["cast", "iron"], ["carbon", "steel"]]


def test_the_requested_product_itself_is_not_a_kind():
    # In a frying pan request, "pan" says nothing about the kind; "cheap pan" names no kind at all.
    assert kind_parts("carbon steel pan", "frying pan", KITCHEN_KINDS["kitchen"]) == [["carbon", "steel"]]
    assert kind_parts("cheap pan", "frying pan", KITCHEN_KINDS["kitchen"]) == []


def test_hyphens_plurals_and_known_names_are_evened_out():
    assert kind_parts("non-stick pans", "frying pan", KITCHEN_KINDS["kitchen"]) == [["nonstick"]]
    assert kind_parts("Teflon pan", "frying pan", KITCHEN_KINDS["kitchen"]) == [["nonstick"]]
    assert kind_parts("cast iron skillet", "frying pan", KITCHEN_KINDS["kitchen"]) == [["cast", "iron"]]


# --- Grouping notes ---

def test_notes_about_the_same_kind_are_one_group():
    groups = kinds([note("carbon steel pan"), note("Carbon steel frying pan", "warn"), note("carbon steel skillet"),
                    note("cheap carbon steel pan"), note("cast iron pan")], product_type="frying pan")
    assert abouts(groups) == [["Carbon steel frying pan", "carbon steel pan", "carbon steel skillet", "cheap carbon steel pan"],
                              ["cast iron pan"]]
    carbon = next(g for g in groups if g.key == "carbon steel")
    assert carbon.stances == {"recommend": 3, "warn": 1}


def test_the_name_shown_is_the_kind_written_most_often():
    groups = kinds([note("hand grinder"), note("hand grinder", comment_id="c2"), note("hand grinder for espresso")],
                   product_type="coffee grinder")
    assert [g.name for g in groups] == ["hand grinder"]


def test_a_narrower_kind_stays_apart_but_names_the_broader_one():
    groups = kinds([note("cast iron pan"), note("enameled cast iron"), note("thick carbon steel pan", "warn"),
                    note("carbon steel pan")], product_type="frying pan")
    by_key = {g.key: g for g in groups}
    assert set(by_key) == {"cast iron", "enameled cast iron", "thick carbon steel", "carbon steel"}
    assert by_key["enameled cast iron"].broader == ["cast iron"]
    assert by_key["thick carbon steel"].broader == ["carbon steel"]
    assert by_key["cast iron"].broader == []


def test_kinds_that_mean_the_same_in_different_words_stay_apart():
    # "gyuto" is a Japanese chef knife, but no word says so: that needs the AI step.
    groups = kinds([note("gyuto"), note("Japanese chef knife")], product_type="chef knife")
    assert len(groups) == 2


def test_a_note_naming_no_kind_is_in_no_group():
    groups = kinds([note("cheap grinder"), note("quality grinder"), note("hand grinder")], product_type="coffee grinder")
    assert abouts(groups) == [["hand grinder"]]


def test_a_note_naming_two_kinds_is_in_both_groups():
    groups = kinds([note("cast iron or carbon steel pan"), note("cast iron pan"), note("carbon steel pan")],
                   product_type="frying pan")
    assert abouts(groups) == [["carbon steel pan", "cast iron or carbon steel pan"], ["cast iron or carbon steel pan", "cast iron pan"]]


def test_kind_aliases_only_apply_within_their_category():
    groups = kinds([note("Teflon pan"), note("nonstick pan")], product_type="frying pan", category="skincare")
    assert len(groups) == 2


# --- Placing products ---

def test_a_product_is_placed_in_the_kinds_its_name_names():
    groups = kinds([note("carbon steel pan"), note("cast iron"), note("enameled cast iron"), note("santoku")],
                   products("De Buyer carbon steel", "Lodge cast iron skillet", "Staub enameled cast iron", "Lodge", "Miyabi Santoku"),
                   product_type="frying pan")
    placed = {g.key: g.product_keys for g in groups}
    assert placed == {
        "carbon steel": ["kitchen:de buyer carbon steel"],
        "cast iron": ["kitchen:lodge cast iron skillet", "kitchen:staub enameled cast iron"],
        "enameled cast iron": ["kitchen:staub enameled cast iron"],
        "santoku": ["kitchen:miyabi santoku"],
    }


def test_a_product_is_placed_by_every_name_in_its_group():
    # Shown as "Hario Skerton", but one of its names says it is a hand grinder.
    groups = kinds([note("hand grinder")], products("Hario Skerton", "Hario Skerton", "Hario Skerton", "Hario Skerton hand grinder"),
                   product_type="coffee grinder")
    assert groups[0].product_keys == ["kitchen:hario skerton"]


def test_kind_groups_come_biggest_first():
    groups = kinds([note("cast iron"), note("carbon steel pan"), note("carbon steel", comment_id="c2")], product_type="frying pan")
    assert [g.key for g in groups] == ["carbon steel", "cast iron"]


# --- From the checked extractions ---

def test_notes_come_from_the_kept_notes_of_every_thread():
    kept = ExtractedNote(comment_id="c1aaaa", about="carbon steel pan", stance="recommend", quote="q")
    dropped = ExtractedNote(comment_id="c9zzzz", about="cast iron", stance="warn", quote="q")
    checked = {"1fake01": CheckResult(kept_notes=[kept], rejected_notes=[(dropped, "quote not found")])}
    assert notes_from_checked(checked) == [KindMention("1fake01", "c1aaaa", "carbon steel pan", "recommend")]


def test_a_kind_already_written_out_is_not_written_out_twice():
    aliases = make_aliases({"stainless": "stainless steel", "Teflon": "nonstick"})
    assert kind_parts("stainless steel pan", "frying pan", aliases) == [["stainless", "steel"]]
    assert kind_parts("stainless pan", "frying pan", aliases) == [["stainless", "steel"]]
    assert kind_parts("Teflon nonstick pan", "frying pan", aliases) == [["nonstick"]]


def test_a_word_repeated_in_the_second_kind_is_kept():
    assert kind_parts("stainless steel pan or carbon steel pan", "frying pan", {}) == [["stainless", "steel"], ["carbon", "steel"]]


# --- For the pipeline: each note's kinds (engine.rank.KindNote) and the placements ---

def test_each_note_can_be_looked_up_to_its_kinds_and_placements_list_the_products_per_kind():
    either = note("cast iron or carbon steel pan")
    plain = note("cheap pan", comment_id="c2")
    groups = kinds([either, note("cast iron pan", comment_id="c3"), plain], products("Lodge cast iron skillet"),
                   product_type="frying pan")
    lookup = kinds_of(groups)
    assert sorted(g.key for g in lookup[either]) == ["carbon steel", "cast iron"]
    assert plain not in lookup  # names no kind
    assert placements(groups) == {"cast iron": ["kitchen:lodge cast iron skillet"], "carbon steel": []}


# --- Review fixes, 9 Oct 2026 ---

def test_a_note_naming_two_kinds_names_neither_group():
    # "cast iron or carbon steel pan" is about two kinds: if it named both groups, they'd show the same name.
    groups = kinds([note("cast iron or carbon steel pan")], product_type="frying pan")
    assert sorted(g.name for g in groups) == ["carbon steel", "cast iron"]  # named by their key words


def test_a_group_is_named_by_the_notes_about_it_alone():
    groups = kinds([note("cast iron or carbon steel pan"), note("cast iron or carbon steel pan", comment_id="c2"),
                    note("carbon steel pan", comment_id="c3")], product_type="frying pan")
    by_key = {g.key: g.name for g in groups}
    assert by_key == {"carbon steel": "carbon steel pan", "cast iron": "cast iron"}
    assert len(set(by_key.values())) == len(by_key)


# --- Kinds compared once per pair of names (latency, 12 Oct 2026) ---

def _same_kind_sets_one_by_one(items):
    """The grouping as first written, comparing every note with every note of every set: what the faster one must
    give, set for set and in the same order."""
    from engine.group_kinds import _same_kind

    sets = []
    for item in items:
        matching = [s for s in sets if any(_same_kind(item[1], other[1]) for other in s)]
        merged = [item] + [x for s in matching for x in s]
        sets = [s for s in sets if s not in matching] + [merged]
    return sets


def test_kind_sets_are_the_same_as_comparing_every_note():
    import random

    from engine.group_kinds import KindMention, _same_kind_sets

    rng = random.Random(7)
    words = ["cast", "iron", "castiron", "carbon", "steel", "stainless", "nonstick", "non", "stick", "pan", "clad"]
    items = []
    for n in range(300):
        kind = [rng.choice(words) for _ in range(rng.randint(1, 3))]
        items.append((KindMention(f"t{n % 7}", f"c{n}", " ".join(kind), "recommend"), list(dict.fromkeys(kind))))
    assert _same_kind_sets(items) == _same_kind_sets_one_by_one(items)


def test_each_pair_of_kind_names_is_compared_once(monkeypatch):
    from engine import group_kinds
    from engine.group_kinds import KindMention

    calls = []
    real = group_kinds._same_kind
    monkeypatch.setattr(group_kinds, "_same_kind", lambda a, b: calls.append((tuple(a), tuple(b))) or real(a, b))
    items = [(KindMention("t1", f"c{n}", "cast iron", "recommend"), ["cast", "iron"]) for n in range(20)]
    items += [(KindMention("t1", f"d{n}", "carbon steel", "recommend"), ["carbon", "steel"]) for n in range(20)]
    sets = group_kinds._same_kind_sets(items)
    assert len(sets) == 2
    assert len(calls) == len(set(calls))  # never the same two names twice


# --- Two kinds compared with a quick look first (latency, 13 Oct 2026) ---

import random  # noqa: E402

from engine import group_kinds as kinds_module  # noqa: E402
from engine.match_products import join_split_words  # noqa: E402


def same_kind_by_joining(a: list[str], b: list[str]) -> bool:
    """_same_kind as first written, joining words both ways every time: the reference."""
    joined_a = join_split_words(a, b)
    return set(joined_a) == set(join_split_words(b, joined_a))


def test_two_kinds_compare_the_same_with_the_quick_look():
    rng = random.Random(13)
    stems = ["cast", "iron", "castiron", "carbon", "steel", "carbonsteel", "non", "stick", "nonstick", "pan", "hand",
             "grinder", "handgrinder", "a", "b", "ab", "abc", "c", "bc"]
    for _ in range(5000):
        a = [rng.choice(stems) for _ in range(rng.randint(1, 4))]
        b = [rng.choice(stems) for _ in range(rng.randint(1, 4))]
        assert kinds_module._same_kind(a, b) == same_kind_by_joining(a, b), (a, b)


def same_kind_sets_one_by_one(items):
    """_same_kind_sets as first written (12 Oct 2026): every new note compared with every set's kinds. The reference."""
    sets, kinds, known = [], [], {}

    def same(a, b):
        if (a, b) not in known:
            known[(a, b)] = same_kind_by_joining(list(a), list(b))
        return known[(a, b)]

    for item in items:
        words = tuple(item[1])
        matching = [i for i, held in enumerate(kinds) if any(same(words, other) for other in held)]
        merged = [item] + [x for i in matching for x in sets[i]]
        merged_kinds = {words}.union(*(kinds[i] for i in matching))
        matching_sets = [sets[i] for i in matching]
        keep = [i for i, s in enumerate(sets) if s not in matching_sets]
        sets = [sets[i] for i in keep] + [merged]
        kinds = [kinds[i] for i in keep] + [merged_kinds]
    return sets


def test_kind_sets_found_by_their_words_are_the_sets_found_one_by_one():
    # The same sets, holding the same notes in the same order, with words written as one or apart, repeated kinds,
    # the same words in another order, and notes that join two sets.
    rng = random.Random(14)
    stems = ["cast", "iron", "castiron", "carbon", "steel", "carbonsteel", "non", "stick", "nonstick", "hand",
             "grinder", "handgrinder", "a", "b", "ab", "abc", "c", "bc", "enameled"]
    for n in range(300):
        items = []
        for i in range(rng.randint(0, 40)):
            note = KindMention(f"t{n}", f"c{i}", f"about {i}", rng.choice(["recommend", "warn"]))
            items.append((note, [rng.choice(stems) for _ in range(rng.randint(1, 3))]))
        assert kinds_module._same_kind_sets(items) == same_kind_sets_one_by_one(items), n


# --- A text's kind words worked out once per text and list of known names (latency, 14 Oct 2026) ---

def test_a_texts_kind_words_are_worked_out_once_per_list_of_known_names(monkeypatch):
    # Writing an answer's "What to look for" asks the kind words of the same kinds, notes and names over and over
    # (9,470 times for 32 answers), each trying every known name at every word.
    from engine.match_products import known_aliases

    written_out = []
    real = kinds_module._write_out_anywhere
    monkeypatch.setattr(kinds_module, "_write_out_anywhere",
                        lambda words, aliases: written_out.append(1) or real(words, aliases))
    known = known_aliases("kinds").get("kitchen", {})
    texts = ["Teflon pans", "carbon steel pan", "a stainless-steel skillet", "Teflon pans"]
    first = [kinds_module._kind_words(text, known) for text in texts]
    assert len(written_out) == 3  # "Teflon pans" once
    assert [kinds_module._kind_words(text, known) for text in texts] == first and len(written_out) == 3
    first[0].append("changed")  # a caller changing the list changes nothing remembered
    assert kinds_module._kind_words("Teflon pans", known) == first[0][:-1]
    other = dict(known)  # another list of known names is another table
    assert kinds_module._kind_words("Teflon pans", other) == first[0][:-1] and len(written_out) == 4
