"""Module 4 duplicates and wrong joins found in the answers on 15 Oct 2026 (the general-quality builder; Claude's
technical calls within the name-levels rules, reported to Noemi). Each rule with made-up products:

1. A name ending in "line" or "series" names the line of what comes before it ("Verb Ghost line" had been shown beside
   "Verb Ghost Shampoo"; "JBL Flip series" beside the JBL Flip line): the word is dropped, so such a name is grouped as
   its line written alone is, by the name-levels rules. A facts entry named so is a line, never one product.
2. A name giving two or more models ("JBL Flip 4, 5, or 6", "6 or 7 quart bowl lift Kitchen Aid") names no one
   product: it joins none, so it never brings one model's mentions into another's (the JBL Flip 4 had held the Flip
   5's).
3. A name the whole library writes, without a maker, only after two or more makers' names ("SA cleanser" after
   CeraVe's, COSRX's and Clinique's) names no one product either: a bare type-word name never joins a brand's product,
   whichever one an answer's threads name, so it never joins two brands' products (CeraVe's and COSRX's SA cleansers
   had been one product through it). Neither kind of name is ranked, nor listed as a brand or a line.
4. A model's one-word name written without its brand ("wave", "squeeze") is its name with the brand before it
   ("Leatherman Wave", "Sawyer Squeeze"): each had been a pick of its own beside it. Not when two makers' names end
   with it.
5. Short names and model words: "Pro" is KitchenAid's Professional, "S7" Braun's Series 7, writers' "Owlet camera" the
   Owlet Cam, "Portland Leather Co" and "Company" Portland Leather Goods (the shipped alias list); "micro" names
   another model, as "mini" does ("Sawyer Squeeze Micro" had been the Sawyer Squeeze).
6. A line written only with the type's words ("LL Bean sheets") is its brand's line in the brand rules: listed under
   Skip these, it folds into a pick of its brand.
7. The general category's other names for its types (config.TYPE_SYNONYMS: "compressor" for a tyre inflator).

Every library, product and writer here is made up, but for rule 5's real names in the shipped alias list; no test
reads data/ but the shipped alias list.
"""

from datetime import date

from engine import pipeline
from engine.group_products import ProductMention, brand_pick_name, group_products, library_ranges
from engine.match_products import known_aliases, normalize_name, product_words, same_product
from engine.product_facts import ProductFacts
from engine.query import ParsedQuery

TODAY = date(2026, 10, 15)
NO_ALIASES = {"skincare": {}, "kitchen": {}, "haircare": {}, "general": {}, "other": {}}


def typed(product: str, product_type: str | None, comment_id: str, category: str = "general",
          thread_id: str = "1fake01") -> ProductMention:
    return ProductMention(thread_id, comment_id, product, category, "recommend", product_type=product_type)


def names_by_group(groups) -> list[list[str]]:
    return sorted((sorted({m.product for m in g.mentions}) for g in groups), key=lambda names: names[0])


def group_holding(groups, name: str):
    return next(g for g in groups if name in g.names)


# --- 1. A name ending in "line" or "series" names the line of what comes before it ---

def test_a_name_ending_in_line_or_series_is_the_name_before_it():
    assert product_words("Lumora Ghost line") == ["lumora", "ghost"]
    assert product_words("Lumora Ghost product line") == ["lumora", "ghost"]
    assert product_words("Lumora Ghost lines") == ["lumora", "ghost"]
    assert product_words("Bexley Flip series") == ["bexley", "flip"]
    assert same_product("Bexley Flip series", "Bexley Flip") and same_product("Lumora Ghost line", "Lumora Ghost")
    # Only at its end: a word of a name's own ("Tarvo cross line laser", "Brava Series 7") stays, and so does a name of
    # that word alone.
    assert product_words("Tarvo cross line laser") == ["tarvo", "cross", "line", "laser"]
    assert product_words("Brava Series 7") == ["brava", "series", "7"]
    assert product_words("Line") == ["line"]
    # A name's words for other uses keep it: a summary is saved under the shown name's words ("... skillet line").
    assert normalize_name("Lumora Ghost line") == ["lumora", "ghost", "line"]


def test_a_line_written_as_a_line_is_its_one_product_of_the_type():
    # The "Verb Ghost line" case: writers' "line" said no more than the line's name, which, in a shampoo answer, is its
    # one shampoo when the library names no other (name levels, LibraryRanges); it had been a product of its own.
    mentions = [typed(n, t, f"c{i}", "haircare") for i, (n, t) in enumerate([
        ("Lumora Ghost line", "shampoo"), ("Lumora Ghost line", "shampoo"), ("Lumora Ghost product line", "shampoo"),
        ("Lumora Ghost Shampoo", "shampoo"), ("Lumora Ghost Shampoo", "shampoo"), ("Lumora Ghost Oil", "hair oil")])]
    groups = group_products(mentions, NO_ALIASES, product_type="shampoo", ranges=library_ranges(mentions, NO_ALIASES))
    shampoo = group_holding(groups, "Lumora Ghost Shampoo")
    assert set(shampoo.names) == {"Lumora Ghost line", "Lumora Ghost product line", "Lumora Ghost Shampoo"}
    assert shampoo.name == "Lumora Ghost Shampoo" and not shampoo.loose
    # With two more of the line's shampoos in the library, it is the line, as its name written alone would be.
    elsewhere = [typed(n, "shampoo", f"e{i}", "haircare", "1fake09")
                 for i, n in enumerate(["Lumora Ghost Detox Shampoo", "Lumora Ghost Volume Shampoo"])]
    groups = group_products(mentions, NO_ALIASES, product_type="shampoo",
                            ranges=library_ranges(mentions + elsewhere, NO_ALIASES))
    line = group_holding(groups, "Lumora Ghost line")
    assert line.loose and set(line.names) == {"Lumora Ghost line", "Lumora Ghost product line"}


def test_a_line_pick_named_as_a_line_says_line_once():
    assert brand_pick_name("Lumora Ghost line", "shampoo") == "Lumora Ghost shampoo line"
    assert brand_pick_name("Lumora Ghost product line", "shampoo") == "Lumora Ghost shampoo line"
    assert brand_pick_name("Bexley Flip series", "bluetooth speaker") == "Bexley Flip bluetooth speaker line"


def test_a_facts_entry_named_as_a_line_is_no_one_product():
    # The facts list names some lines so ("Medik8 Crystal Retinal line": six strengths): such an entry speaks for the
    # line, so grouping never takes the line's name for one product's (_known_products), now "line" is dropped from it.
    entries = [ProductFacts(product=name, category="skincare", product_type="retinoid",
                            facts={"prescription_only": False}, sources=["https://facts.example/page"],
                            checked_on=TODAY)
               for name in ("Calder Crystal Retinal line", "Calder Crystal Retinal 6")]
    known = pipeline._known_products(entries)["skincare"]
    assert ("calder", "crystal", "retinal", "6") in known
    assert ("calder", "crystal", "retinal") not in known


# --- 2. A name giving two or more models names no one product ---

def test_a_name_giving_two_models_joins_neither():
    mentions = [typed(n, "bluetooth speaker", f"c{i}") for i, n in enumerate(
        ["Bexley Flip 4", "Bexley Flip 4", "Bexley Flip 5", "Bexley Flip 5", "Bexley Flip 4, 5, or 6"])]
    groups = group_products(mentions, NO_ALIASES, product_type="bluetooth speaker")
    assert names_by_group(groups) == [["Bexley Flip 4"], ["Bexley Flip 4, 5, or 6"], ["Bexley Flip 5"]]
    both = group_holding(groups, "Bexley Flip 4, 5, or 6")
    assert both.loose and both.generic
    assert not group_holding(groups, "Bexley Flip 4").generic
    # The KitchenAid case: a size given two ways names no one mixer.
    mentions = [typed(n, "stand mixer", f"c{i}", "kitchen") for i, n in enumerate(
        ["Marlo 6-quart bowl-lift", "Marlo 6-quart bowl-lift", "6 or 7 quart bowl lift Marlo"])]
    groups = group_products(mentions, NO_ALIASES, product_type="stand mixer")
    assert names_by_group(groups) == [["6 or 7 quart bowl lift Marlo"], ["Marlo 6-quart bowl-lift"]]


def test_or_as_a_names_first_word_is_a_brand():
    # Outdoor Research writes itself OR: "or" first gives no alternatives.
    mentions = [typed(n, "rain jacket", f"c{i}") for i, n in enumerate(["OR Helium", "OR Helium", "OR Helium jacket"])]
    groups = group_products(mentions, NO_ALIASES, product_type="rain jacket")
    assert not any(g.generic for g in groups)
    assert names_by_group(groups) == [["OR Helium", "OR Helium jacket"]]


# --- 3. A kind of product written without a maker names no one product ---

def sa_library() -> list[ProductMention]:
    """Two makers' SA cleansers, each maker also written alone, and a writer's bare "SA cleanser"."""
    return [typed(n, "cleanser", f"c{i}", "skincare", thread) for i, (n, thread) in enumerate([
        ("Cerona", "1fake01"), ("Cerona SA cleanser", "1fake01"), ("Cerona SA cleanser", "1fake02"),
        ("Cerona Renewing SA Cleanser", "1fake02"), ("SA cleanser", "1fake02"),
        ("Coviq", "1fake03"), ("Coviq SA cleanser", "1fake03"), ("Coviq Salicylic Acid Daily Cleanser", "1fake03")])]


def test_a_kind_written_after_two_makers_names_joins_neither_makers_product():
    library = sa_library()
    ranges = library_ranges(library, NO_ALIASES)
    # An answer whose threads name only one maker's SA cleanser: the bare name still names no one product.
    read = [m for m in library if m.thread_id in {"1fake01", "1fake02"}]
    groups = group_products(read, NO_ALIASES, product_type="cleanser", ranges=ranges)
    bare = group_holding(groups, "SA cleanser")
    assert set(bare.names) == {"SA cleanser"} and bare.loose and bare.generic
    assert "SA cleanser" not in group_holding(groups, "Cerona SA cleanser").names
    groups = group_products(library, NO_ALIASES, product_type="cleanser", ranges=ranges)
    assert set(group_holding(groups, "SA cleanser").names) == {"SA cleanser"}


def test_a_name_after_one_makers_name_still_joins_it():
    # A model written without its maker is that maker's model: "Soft Peel" after Aveline's name only, and "Glide Air"
    # after Dellan's name and its line Arcos's (a maker and its line are one maker).
    mentions = [typed(n, t, f"c{i}", "skincare") for i, (n, t) in enumerate([
        ("Aveline", "exfoliant"), ("Aveline Soft Peel", "exfoliant"), ("Aveline Soft Peel", "exfoliant"),
        ("Soft Peel", "exfoliant"), ("Aveline Glow Serum", "serum")])]
    groups = group_products(mentions, NO_ALIASES, product_type="exfoliant", ranges=library_ranges(mentions, NO_ALIASES))
    assert {"Soft Peel", "Aveline Soft Peel"} <= set(group_holding(groups, "Soft Peel").names)
    mentions = [typed(n, "hair dryer", f"c{i}") for i, n in enumerate(
        ["Dellan", "Arcos", "Dellan Arcos Glide Air", "Arcos Glide Air", "Glide Air", "Dellan Breeze"])]
    groups = group_products(mentions, NO_ALIASES, product_type="hair dryer",
                            ranges=library_ranges(mentions, NO_ALIASES))
    assert {"Glide Air", "Arcos Glide Air", "Dellan Arcos Glide Air"} <= set(group_holding(groups, "Glide Air").names)
    assert not any(g.generic for g in groups)


def test_a_name_naming_no_one_product_is_never_ranked_nor_listed_as_a_brand():
    # 'SA cleanser line' had been ranked as a brand line: its threads were titled for cleansers, and Cerona's SA
    # cleanser holds its name.
    library = sa_library()
    groups = group_products(library, NO_ALIASES, product_type="cleanser", ranges=library_ranges(library, NO_ALIASES))
    query = ParsedQuery(text="cleanser", status="ok", category="skincare", product_type="cleanser",
                        search_terms=["cleanser"], subreddits=["SkincareAddiction"])
    result = pipeline.PipelineResult(query=query)
    titles = {t: "Best cleanser for oily skin?" for t in ("1fake01", "1fake02", "1fake03")}
    kept = pipeline._groups_to_rank(groups, query, result, titles)
    assert not any("SA cleanser" in g.names and len(g.names) == 1 for g in kept)
    assert "SA cleanser" not in result.brand_or_line_names_left_out
    assert result.left_out_generic == ["SA cleanser"]


# --- 4. A model's one-word name written without its brand ---

def test_a_models_one_word_name_is_its_name_with_the_brand_before_it():
    mentions = [typed(n, "multi-tool", f"c{i}") for i, n in enumerate(
        ["Tolman", "Tolman", "Tolman Wave", "Tolman Wave", "Tolman Wave", "Tolman Surge", "wave", "Wave",
         "original Wave"])]
    groups = group_products(mentions, NO_ALIASES, product_type="multi-tool",
                            ranges=library_ranges(mentions, NO_ALIASES))
    wave = group_holding(groups, "Tolman Wave")
    assert set(wave.names) == {"Tolman Wave", "wave", "Wave"} and wave.name == "Tolman Wave" and not wave.loose
    assert set(group_holding(groups, "original Wave").names) == {"original Wave"}  # a description before it, no brand
    assert group_holding(groups, "Tolman").loose  # the brand itself, as before


def test_a_one_word_name_ending_two_makers_names_joins_neither():
    mentions = [typed(n, "multi-tool", f"c{i}") for i, n in enumerate(
        ["Tolman", "Tolman Wave", "Tolman Wave", "Brisk", "Brisk Wave", "wave"])]
    groups = group_products(mentions, NO_ALIASES, product_type="multi-tool")
    assert set(group_holding(groups, "wave").names) == {"wave"}
    # And when the library writes both, a request whose threads name only one of them leaves it apart too.
    read = [m for m in mentions if "Brisk" not in m.product]
    groups = group_products(read, NO_ALIASES, product_type="multi-tool", ranges=library_ranges(mentions, NO_ALIASES))
    assert set(group_holding(groups, "wave").names) == {"wave"}


def test_a_one_word_brand_never_joins_another_brands_product_ending_with_it():
    # "Pellam" is a brand here (it starts its own products' names), not a model of Gorsey's.
    mentions = [typed(n, "cast iron skillet", f"c{i}", "kitchen") for i, n in enumerate(
        ["Pellam", "Pellam No. 8", "Pellam No. 10", "Gorsey", "Gorsey Pellam"])]
    groups = group_products(mentions, NO_ALIASES, product_type="cast iron skillet")
    assert "Gorsey Pellam" not in group_holding(groups, "Pellam").names


# --- 5. Short names and model words ---

def test_the_shipped_short_names_for_writers_names_of_these_products():
    kitchen, general = known_aliases()["kitchen"], known_aliases()["general"]
    assert product_words("KitchenAid Pro 600", kitchen) == ["kitchenaid", "professional", "600"]
    assert product_words("Kitchen Aid Pro stand mixer", kitchen) == ["kitchenaid", "professional", "stand", "mixer"]
    assert product_words("KitchenAid Professional 600", kitchen) == ["kitchenaid", "professional", "600"]
    assert same_product("Braun S7", "Braun Series 7", general)
    assert same_product("owlet camera", "Owlet Cam", general)
    assert product_words("Portland Leather Co bag", general)[:3] == ["portland", "leather", "goods"]  # the maker's name
    assert product_words("Portland Leather Company", general) == product_words("Portland Leather Goods", general)


def test_micro_names_another_model():
    assert not same_product("Trailo Squeeze", "Trailo Squeeze Micro")
    mentions = [typed(n, "camping water filter", f"c{i}") for i, n in enumerate(
        ["Trailo Squeeze", "Trailo Squeeze", "Trailo Squeeze Micro", "micro squeeze"])]
    groups = group_products(mentions, NO_ALIASES, product_type="camping water filter")
    assert names_by_group(groups) == [["Trailo Squeeze"], ["Trailo Squeeze Micro", "micro squeeze"]]


# --- 6. A line written only with the type's words is its brand's line in the brand rules ---

def fernby_groups():
    """A bed sheets answer's groups: Fernby's line, always written with the type's words, and two Fernby sheets."""
    mentions = [typed(n, "bed sheets", f"c{i}") for i, n in enumerate(
        ["Fernby sheets", "Fernby sheets", "Fernby bed sheets", "Fernby Percale Pima", "Fernby Percale Pima",
         "Fernby Flannel"])]
    groups = group_products(mentions, NO_ALIASES, product_type="bed sheets")
    return group_holding(groups, "Fernby sheets"), group_holding(groups, "Fernby Percale Pima"), groups


def test_a_line_written_with_the_types_words_on_the_skip_list_folds_into_its_brands_pick():
    # The bed sheets case: "LL Bean bed sheets line" was listed under Skip these while "LL Bean Percale Pima Cotton",
    # one of its sheets, was a pick: its writers always wrote the line with the type's words ("LL Bean sheets"), which
    # the brand rules didn't read as the brand's name. Its warnings now go under the pick's Known downsides (10 Oct).
    from engine.rank import rank_products
    from engine.tests.ranking_factories import mentions as scored

    line, percale, groups = fernby_groups()
    assert line.loose and line.bases == ("fernby",)
    ranking = rank_products(scored(4, "Fernby Percale Pima", key=percale.key, category="general")
                            + scored(3, "Fernby bed sheets line", key=line.key, stance="warn", category="general"),
                            "general")
    assert [p.key for p in ranking.skip_list] == [line.key]
    result = pipeline.PipelineResult(query=None)
    # 17 Oct 2026 (ws-ranking item 5): a brand line's warnings folded under a specific product of its brand are about the
    # line as a whole, so they come back apart, with the line's name, and the pick's own count leaves them out.
    skipped_name = ranking.skip_list[0].name
    folded, downsides, apart = pipeline._fold_brand_skips(ranking, groups, result)
    assert folded.skip_list == [] and percale.key not in downsides
    name, warnings = apart[percale.key]
    assert name == skipped_name and len(warnings) == 3


def test_the_brands_unsold_products_rule_reads_the_line_as_written():
    # A brand's line is left out when every product of its brand named here is known not to be sold (10 Oct 2026); that
    # rule still reads the line's names as written ("Fernby sheets" names no "Fernby Percale Pima"): a line its writers
    # name thirty times isn't taken for its one unsold model.
    line, percale, groups = fernby_groups()
    flannel = group_holding(groups, "Fernby Flannel")
    assert not pipeline._only_unsold_products(line, groups, [percale, flannel])
    assert pipeline._same_brand(line, percale)


# --- 7. The general category's other names for its types (config.TYPE_SYNONYMS) ---

def test_a_brand_and_the_american_name_of_a_type_is_the_brands_line_or_its_one_model():
    # The tyre inflator case: "Viair compressor" was a pick beside "Viair 88P" under Also worth a look, the only
    # Viair model its threads name; a compressor is what American writers call a tyre inflator.
    mentions = [typed(n, "tyre inflator", f"c{i}") for i, n in enumerate(
        ["Varo compressor", "Varo compressor", "Varo 88P", "Varo 88P", "Ryland 18V inflator"])]
    groups = group_products(mentions, NO_ALIASES, product_type="tyre inflator")
    assert names_by_group(groups) == [["Ryland 18V inflator"], ["Varo 88P", "Varo compressor"]]
    # A brand written alone and with the American name, next to a model, is its line (name levels, rule b.).
    mentions = [typed(n, "jumper", f"c{i}") for i, n in enumerate(
        ["Kelso", "Kelso sweater", "Kelso sweaters", "Kelso Merino Crew", "Kelso Merino Crew"])]
    groups = group_products(mentions, NO_ALIASES, product_type="jumper")
    line = group_holding(groups, "Kelso sweater")
    assert line.loose and set(line.names) == {"Kelso", "Kelso sweater", "Kelso sweaters"}


def test_a_maker_and_its_line_are_one_maker():
    # "M12 Sawzall" is Milwaukee's: a library name starts "Milwaukee M12". So a bare "Sawzall" is Milwaukee's model,
    # not a kind two makers' names end with.
    library = [typed(n, "power tool", f"c{i}") for i, n in enumerate(
        ["Torvik", "Torvik Sawzall", "R12", "R12 Sawzall", "Torvik R12 drill", "Sawzall"])]
    ranges = library_ranges(library, NO_ALIASES)
    assert not ranges.generic("general", ("sawzall",))
    library.append(typed("Brenner", "power tool", "c9"))
    library.append(typed("Brenner Sawzall", "power tool", "c10"))
    assert library_ranges(library, NO_ALIASES).generic("general", ("sawzall",))


# --- 8. A brand's initials written in capitals (the product researcher's cases, 15 Oct 2026) ---

def test_a_brands_initials_written_in_capitals_are_the_brand():
    # "AG hoodie line" was shown beside "American Giant hoodie line": writers wrote the brand's initials.
    mentions = [typed(n, "hoodie", f"c{i}") for i, n in enumerate(
        ["Copper Fox", "Copper Fox", "Copper Fox hoodie", "CF", "CF", "CF hoodie", "Copper Fox Sherpa Zip"])]
    groups = group_products(mentions, NO_ALIASES, product_type="hoodie")
    line = group_holding(groups, "Copper Fox")
    assert {"Copper Fox", "Copper Fox hoodie", "CF", "CF hoodie"} <= set(line.names) and line.loose
    # Written in small letters, or fitting two brands here, initials are left as they are.
    mentions = [typed(n, "hoodie", f"c{i}") for i, n in enumerate(
        ["Copper Fox", "Copper Fox hoodie", "cf hoodie", "Cobalt Forge", "CF"])]
    groups = group_products(mentions, NO_ALIASES, product_type="hoodie")
    assert "CF" not in group_holding(groups, "Copper Fox").names
    assert "cf hoodie" not in group_holding(groups, "Copper Fox").names


# --- 9. A brand shown as its maker writes it ---

def test_a_misspelled_brand_is_shown_as_its_maker_writes_it():
    from engine.group_products import maker_spelling

    assert maker_spelling("Phillips Avent Natural", "general") == "Philips Avent Natural"
    assert maker_spelling("Mountain Hardware Ghost Whisperer", "general") == "Mountain Hardwear Ghost Whisperer"
    assert maker_spelling("Simple Human", "general") == "simplehuman"
    assert maker_spelling("Levelor blinds", "general") == "Levolor blinds"
    assert maker_spelling("LL Beans", "general") == "L.L.Bean"
    assert maker_spelling("Audio -Technica ATH-M50", "general") == "Audio-Technica ATH-M50"
    assert maker_spelling("Kitchen Aide hand held", "kitchen") == "KitchenAid hand held"  # the shipped short name
    # A word of its own isn't a brand's slip ("Phillips" screwdrivers).
    assert maker_spelling("Phillips screwdriver set", "general") == "Phillips screwdriver set"
    # Changed on purpose 16 Oct 2026 (the interview-fixes builder, the orchestrator's item 7): a brand written in other
    # capitals is shown as its maker writes it too; it had been left as written ("kitchenaid mixer").
    assert maker_spelling("kitchenaid mixer", "kitchen") == "KitchenAid mixer"


def test_a_brand_in_other_capitals_is_shown_as_the_lists_write_it():
    # 16 Oct 2026 (the interview-fixes builder): 58 names shown in the day's answers had their brand in small letters or
    # other capitals ("Cosrx spot treatment line", "Oxo electric kettle line", "paula's choice ..."). The brand is
    # written as the lists write it: the brand-lines list's brands, the shipped short names, config.MAKER_SPELLINGS,
    # then the price and facts lists' names' first words (the brand); never into small letters from those names.
    from engine.group_products import maker_spelling

    assert maker_spelling("Cosrx spot treatment", "skincare", more=("COSRX",)) == "COSRX spot treatment"
    assert maker_spelling("paula’s choice 2% BHA", "skincare", more=("Paula's Choice",)) == "Paula's Choice 2% BHA"
    # Small letters come only from config's own spellings (a maker's style: "Simple Human" is "simplehuman", above).
    assert maker_spelling("innisfree serum", "skincare", more=("innisfree",)) == "innisfree serum"
    assert maker_spelling("Innisfree serum", "skincare", more=("innisfree",)) == "Innisfree serum"
    # Changed on purpose 17 Oct 2026 (the ws-names builder): the shipped short names now write "Paperwhite" out as
    # "Kindle Paperwhite" (a Kindle beside a Paperwhite line had been one product shown twice), so that whole name is a
    # known spelling, as Amazon writes it. Was: "Kindle paperwhite". The brand alone, its first word, as before:
    assert maker_spelling("kindle paperwhite", "general", whole=("Kindle Paperwhite Signature Edition",)) == (
        "Kindle Paperwhite")
    assert maker_spelling("kindle oasis", "general", whole=("Kindle Paperwhite Signature Edition",)) == (
        "Kindle oasis")  # the brand: its first word
    assert maker_spelling("kindle e-reader", "general", whole=("Kindle Paperwhite Signature Edition",)) == (
        "Kindle e-reader")
    assert maker_spelling("Brisa serum", "skincare", whole=("brisa gel",)) == "Brisa serum"
    # Changed on purpose 17 Oct 2026 (the ws-names builder): config.MAKER_SPELLINGS writes "Laifen Swift" now, and a
    # name no list writes starts with a capital (engine.group_products._tidied). Was: "laifen swift", as written.
    assert maker_spelling("laifen swift", "general") == "Laifen Swift"
    assert maker_spelling("zorvo swift", "general") == "Zorvo swift"  # no list writes it: as written, with a capital
    # A brand the brand-lines list writes in small letters only is no maker's style: never a reason for small letters.
    assert maker_spelling("Shark robot vacuum", "general", more=("shark",)) == "Shark robot vacuum"
    assert maker_spelling("shark robot vacuum", "general", more=("shark",)) == "shark robot vacuum"


def test_answers_show_the_makers_spelling():
    mentions = [typed(n, "bin", f"c{i}") for i, n in enumerate(["Simple Human", "simple human", "Simplehuman"])]
    groups = group_products(mentions, NO_ALIASES, product_type="bin")
    query = ParsedQuery(text="bin", status="ok", category="general", product_type="bin", search_terms=["bin"],
                        subreddits=["BuyItForLife"])
    result = pipeline.PipelineResult(query=query)
    kept = pipeline._groups_to_rank(groups, query, result, {"1fake01": "Best kitchen bin?"})
    assert [g.name for g in kept] in ([], ["simplehuman"], ["simplehuman bin line"])
    assert all("Simple Human" not in g.name for g in kept)


# --- 10. A shop is no product's maker ---

def test_where_a_product_was_bought_is_no_part_of_its_name():
    assert product_words("Hisense model from Costco") == ["hisense"]
    assert product_words("Pellam 6 quart (Costco)") == ["pellam", "6", "quart"]
    assert product_words("cotton sheets from Target") == ["cotton", "sheets"]
    assert product_words("Kirkland sheets") == ["kirkland", "sheets"]  # a shop's own brand is a maker's name


def test_a_shops_name_with_the_type_names_no_one_product():
    mentions = [typed(n, "bed sheets", f"c{i}") for i, n in enumerate(
        ["Costco sheets", "Costco sheets", "Target bed sheets", "Kirkland sheets", "Kirkland sheets"])]
    groups = group_products(mentions, NO_ALIASES, product_type="bed sheets")
    assert group_holding(groups, "Costco sheets").generic
    assert group_holding(groups, "Target bed sheets").generic
    assert not group_holding(groups, "Kirkland sheets").generic


# --- 11. A refill is no pen ---

def test_a_refill_never_counts_for_its_pen():
    # "Fisher Space Pen refill" had been a fountain pen pick: the AI typed it a pen refill.
    assert pipeline._names_a_set("pen refill", "pen") and pipeline._names_a_set("ink refills", "fountain pen")


# --- 12. Writers' names the shipped short names write out ---

def test_the_shipped_short_names_for_the_researchers_cases():
    general, skincare = known_aliases()["general"], known_aliases()["skincare"]
    assert product_words("Roomba 980", general) == ["irobot", "roomba", "980"]  # Roomba is iRobot's line
    assert product_words("iRobot Roomba", general) == ["irobot", "roomba"]
    assert product_words("Alexa", general) == ["amazon", "echo"]  # the assistant, written for its speaker
    assert product_words("Rohto Mentholatum Acnes", skincare) == ["mentholatum", "acnes"]


# --- 13. The second product researcher's cases (15 Oct 2026) ---

def test_model_codes_a_digit_apart_are_two_models():
    # "Sony WF-1000XM3 earbuds line" was a line: the XM3 fitted the XM4 as a one-letter slip, so it fitted two products.
    assert not same_product("Sonor WF-1000XM3", "Sonor WF-1000XM4")
    assert not same_product("Kelvar KDTM604KPS", "Kelvar KDTM704KPS")
    assert same_product("Urbanic 070", "urbanic 070s")  # a plural is still forgiven
    assert same_product("Kelvar KDTM604KPS", "Kelvar KDTM604KPS dishwasher")


def test_a_curated_entry_gives_the_makers_writing_of_a_whole_name():
    # "Mad Hippie vitamin c serum" in one answer and "Mad Hippie Vitamin C Serum" in another: the price list writes it
    # as its maker does, so every answer shows it so.
    from engine.group_products import maker_spelling

    entries = ("Brisa Vitamin C Serum", "Kelvar KDTM604KPS")
    assert maker_spelling("Brisa vitamin c serum", "skincare", whole=entries) == "Brisa Vitamin C Serum"
    assert maker_spelling("Brisa vitamin c serum", "skincare") == "Brisa vitamin c serum"
    assert maker_spelling("Brisa vitamin c serum with ferulic", "skincare", whole=entries) == (
        "Brisa vitamin c serum with ferulic")  # another name, as written


def test_shops_with_a_brand_of_their_own_elsewhere_are_still_shops():
    mentions = [typed(n, "spot treatment", f"c{i}", "skincare") for i, n in enumerate(
        ["Olive Young", "Olive Young patches", "Care Plus spot patch", "Care Plus spot patch"])]
    groups = group_products(mentions, NO_ALIASES, product_type="spot treatment")
    assert group_holding(groups, "Olive Young").generic and group_holding(groups, "Olive Young patches").generic
    assert not group_holding(groups, "Care Plus spot patch").generic


def test_the_uk_knows_aquaphor_as_eucerin_aquaphor():
    from engine.group_products import uk_name

    assert uk_name("Aquaphor Healing Ointment") == "Eucerin Aquaphor Soothing Skin Balm"
    assert uk_name("Aquaphor Lip Repair") == "Eucerin Aquaphor Lip Repair"
    assert uk_name("Eucerin Aquaphor Lip Repair") == "Eucerin Aquaphor Lip Repair"  # never twice
    assert uk_name("aquaphor") == "Eucerin Aquaphor"


def test_a_short_names_full_name_is_never_written_twice():
    from engine.group_products import maker_spelling

    # The shipped short names "Encore" (Baratza Encore) and "Field Company" (Field): a name already holding the other
    # words keeps them once, and one written as its maker writes it but for capitals is left as it is.
    assert maker_spelling("Encore Baratza burr grinder", "kitchen") == "Encore Baratza burr grinder"
    assert maker_spelling("Encore grinder", "kitchen") == "Baratza Encore grinder"
    assert maker_spelling("Field Company", "kitchen", more=("Field Company",)) == "Field Company"
    assert maker_spelling("Brisa", "skincare", whole=("brisa",)) == "Brisa"  # never into small letters
    # Nor with the pack size a price was found for: the product is no one size.
    assert maker_spelling("Brisa gel cream", "skincare", whole=("Brisa Gel Cream 50ml",)) == "Brisa gel cream"


def test_an_ingredients_or_sun_protections_short_form_is_no_brands_initials():
    mentions = [typed(n, "sunscreen", f"c{i}", "skincare") for i, n in enumerate(
        ["Ultra Violette", "Ultra Violette Queen Screen", "UV Clear", "UV Clear"])]
    groups = group_products(mentions, NO_ALIASES, product_type="sunscreen")
    assert group_holding(groups, "UV Clear").key == "skincare:uv clear"  # not read as "Ultra Violette Clear"
