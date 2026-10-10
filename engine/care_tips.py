"""Care tips, "how to take care of it" (Noemi, 9 Oct 2026; renamed 11 Oct 2026): credible advice from the threads on looking after a product,
shown next to each pick, so what people buy lasts longer.

The AI lists care tips while it extracts a thread (instructions v7, engine.extract.ExtractedCareTip): what the tip is
about ("Zojirushi kettle", or a kind of product such as "electric kettle"), whether that is a kind, the tip in a few
plain words ("descale every 6 months") and a quote, checked word for word like every other quote. This module does
two things with the checked tips of one request:

1. credible_care_tips keeps only credible tips: the writer's voice (module 5, engine.credibility.score_voice) isn't
   low (config.CREDIBLE_VOICES). A tip has no stance and says nothing about how well the writer knows a product, so
   the voice alone decides. Each kept tip becomes a CareTip, with the link to its comment and the voice's badges.
2. attach_care_tips says which tips go with which products:
   - a product tip goes with the product it names, matched the way module 4 matches names
     (engine.match_products.same_product), among the products ranked for the request. A name written the same way as
     one of a product's names wins ("Lodge" goes with the brand pick "Lodge (their cast iron skillets)"). Otherwise,
     a specific product wins over a brand or line ("Lodge Blacklock" goes with "Lodge Blacklock skillet", not with
     "Lodge"). A name that still fits two products ("Lodge" next to two Lodge skillets, and no brand pick) goes with
     neither: we can't tell which one it means;
   - a kind tip goes with the kinds of product it is about, and so with the products placed in those kinds (module 4,
     engine.group_kinds). Its kind is read the way notes are (engine.group_kinds.kind_parts: the request's own words
     left out, "skillet" read as "pan", and so on), and it is about each kind group whose words it holds all of:
     "carbon steel knife" is about carbon steel. Of those, only the narrowest count: a carbon steel tip isn't for
     every steel knife, so when "carbon steel" and "steel" both fit, only "carbon steel" does;
   - a kind tip about the requested kind of product itself ("electric kettle", "kettles" in a kettle request, so no
     kind words are left) goes with every product: descaling is for every kettle.
3. tips_by_agreement says which of a product's tips to show first (decided by Claude, 10 Oct 2026, as Noemi asked):
   the ones most credible writers agree on. Showing the first two tips in thread order picked DIY repairs ("Seal a
   leaking water gauge with silicone", "Smooth with an angle grinder") over the advice nearly everyone gives
   ("descale with vinegar"). So:
   - tips that say the same thing are gathered into one group. Two tips say the same thing (similar_tips) when they
     are the same tip (same_tip), or when they share at least CARE_TIP_SHARED_WORDS words and, counting both tips'
     words together, at least CARE_TIP_SHARED_SHARE of them are words both have, little words and endings aside
     ("descale it with vinegar" and "descaling with white vinegar regularly"). Two tips of which only one says
     "don't", "no", "not", "never" or "avoid" never say the same thing: "use soap" and "don't use soap" are opposite
     advice. Nor do two tips that both give numbers, but not the same ones: "grind at 12 for pour-over" and "grind at
     20 for pour-over" are different advice. Tips are taken in order (the product's own first, then its kind's, each
     in thread order), and each joins the first group whose first tip says the same thing, or starts a group of its
     own. Comparing with the first tip only keeps a group from drifting: tried on the library on 10 Oct 2026, letting a
     group grow through a chain of tips, each like the one before, gathered 46 cast iron writers into one group
     through common words (oil, water, soap, scrub);
   - each group counts its distinct writers (one writer counts once, however many times they say it; a deleted
     account counts once per comment), and the group with the most comes first. On a tie: the group with the higher
     voice, then the one whose best tip is about the product itself rather than its kind, then thread order;
   - tips about fixing a broken part (config.CARE_TIP_REPAIR_WORDS: seal, glue, replace, solder, sand, epoxy, angle
     grinder, grinding something down, repair) come after every tip about looking after the product, however many
     writers agree on them. A repair and an upkeep tip are never in the same group;
   - within a group, the best writer comes first: the higher voice, then the product's own tip, then thread order.
   The answer (engine/answer.py) then shows up to CARE_TIPS_PER_PICK per pick, one per group: the best writer's tip, in
   their words, with their quote, checked again word for word before it is shown (when it fails, the group's next
   writer's tip and quote take its place). No tip text is ever made up or merged.

What words can't do (as for notes, engine/group_kinds.py): kinds that mean the same in other words stay apart, and
most product names don't say their kind ("Lodge"), so a tip about a kind other than the requested one reaches only
products whose names say it ("Lodge cast iron skillet"). A tip about a narrower kind than any group ("enameled cast
iron" when only "cast iron" has notes) goes with that broader kind's products.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from engine.config import (
    CARE_TIP_REPAIR_WORDS,
    CARE_TIP_SHARED_SHARE,
    CARE_TIP_SHARED_WORDS,
    CREDIBLE_VOICES,
    VOICE_LEVELS,
)
from engine.credibility import copied_comment_ids, score_voice
from engine.extract import CheckResult
from engine.group_kinds import KindGroup, kind_parts
from engine.group_products import ProductGroup
from engine.match_products import Aliases, join_split_words, known_aliases, plain_words, product_words, same_words
from engine.models import Thread


@dataclass(frozen=True)
class CareTip:
    """One credible care tip from one comment, ready to go with a product."""

    about: str  # the product or kind, as the AI wrote it: "Zojirushi kettle", "electric kettle"
    is_kind: bool  # True when it is about a kind of product, not one product
    tip: str  # the tip in a few plain words, as the AI wrote it: "descale every 6 months"
    quote: str  # checked at extraction; checked again before it is shown
    thread_id: str
    comment_id: str  # used to find the comment again and re-check the quote at answer time
    comment_url: str  # the link shown next to the quote
    voice: str  # the writer's voice (module 5): high or medium, never low
    badges: tuple[str, ...] = ()  # "why this voice counts", in words: "well upvoted", "expert flair"
    # The writer's name, lowercased, so a writer who gives the same tip twice counts once when tips are compared
    # (10 Oct 2026); None for a deleted account.
    author: str | None = None


@dataclass
class CareTips:
    """The care tips that go with one product: about the product itself, and about its kind. Each in thread order."""

    own: list[CareTip] = field(default_factory=list)
    kind: list[CareTip] = field(default_factory=list)


def credible_care_tips(threads: Iterable[Thread], checked: Mapping[str, CheckResult]) -> list[CareTip]:
    """The kept care tips of these threads (checked: {thread id: CheckResult}) whose writer's voice isn't low.

    An extraction made before instructions v7 has no care tips, so it gives none.
    """
    tips = []
    for thread in threads:
        result = checked.get(thread.id)
        if result is None or not result.kept_care:
            continue
        comments = {c.id: c for c in thread.comments}
        copied = copied_comment_ids(thread)  # once per thread: it reads the whole thread
        for care in result.kept_care:
            comment = comments[care.comment_id]
            voice = score_voice(comment, thread, result.kept_agreements, copied=copied)
            if voice.level not in CREDIBLE_VOICES:
                continue
            tips.append(CareTip(
                about=care.about, is_kind=care.is_kind, tip=care.tip, quote=care.quote, thread_id=thread.id,
                comment_id=care.comment_id, comment_url=str(comment.url), voice=voice.level, badges=voice.badges,
                author=comment.author.name.lower() if comment.author is not None else None,
            ))
    return tips


def attach_care_tips(tips: Iterable[CareTip], products: list[ProductGroup], kinds: list[KindGroup], category: str,
                     product_type: str = "", aliases: dict[str, Aliases] | None = None,
                     kind_aliases: dict[str, Aliases] | None = None) -> dict[str, CareTips]:
    """{product key: its care tips}, by the rules at the top of this file. Products with no tip are left out.

    `products` are the product groups ranked for the request, `kinds` its kind groups (engine.group_kinds), with the
    products placed in each; `category` and `product_type` are the request's. `aliases` and `kind_aliases` are
    {category: known short names} for products and kinds; by default, the shipped list
    (engine/data/product_aliases.json).
    """
    product_aliases = (known_aliases() if aliases is None else aliases).get(category, {})
    kind_known = (known_aliases("kinds") if kind_aliases is None else kind_aliases).get(category, {})
    names = {p.key: [product_words(name, product_aliases) for name in p.names] for p in products}
    care: dict[str, CareTips] = {}
    for tip in tips:
        if tip.is_kind:
            keys = _products_of_kind(tip.about, products, kinds, product_type, kind_known)
        else:
            keys = _product_named(tip.about, products, names, product_aliases)
        for key in keys:
            mine = care.setdefault(key, CareTips())
            (mine.kind if tip.is_kind else mine.own).append(tip)
    return care


def _product_named(about: str, products: list[ProductGroup], names: dict[str, list[list[str]]],
                   aliases: Aliases) -> list[str]:
    """The key of the one product a product tip names, as a list (empty when it names none, or fits two)."""
    words = product_words(about, aliases)
    if not words:
        return []  # a name made of filler words only ("the one") names nothing
    same_name = [p for p in products if any(_written_the_same(words, name) for name in names[p.key])]
    if same_name:
        return [same_name[0].key] if len(same_name) == 1 else []
    matching = [p for p in products if any(same_words(words, name) for name in names[p.key])]
    specific = [p for p in matching if not p.loose]
    fits = specific or matching
    return [fits[0].key] if len(fits) == 1 else []


def _written_the_same(a: list[str], b: list[str]) -> bool:
    """The same words, also when one writes as one word what the other splits in two ("SoonJung", "Soon Jung")."""
    joined = join_split_words(a, b)
    return joined == join_split_words(b, joined)


def _products_of_kind(about: str, products: list[ProductGroup], kinds: list[KindGroup], product_type: str,
                      aliases: Aliases) -> list[str]:
    """The keys of the products a kind tip goes with: those placed in the narrowest kinds it is about, or every
    product when it is about the requested kind of product itself."""
    parts = kind_parts(about, product_type, aliases)
    if not parts:
        return [p.key for p in products]
    keys: list[str] = []
    for part in parts:
        fitting = [g for g in kinds if set(g.key.split()) <= set(part)]
        narrowest = [g for g in fitting if not any(g.key in other.broader for other in fitting)]
        for group in narrowest:
            keys += [key for key in group.product_keys if key not in keys]
    ranked = {p.key for p in products}
    return [key for key in keys if key in ranked]


# Words that change nothing about a tip: "descale it every 6 months" is "descale every 6 months".
_NOT_TIP_WORDS = frozenset({"a", "an", "the", "it", "its", "them", "they", "your", "my", "you", "yours", "their"})


def same_tip(a: str, b: str) -> bool:
    """Whether two tips say the same in the same words, ignoring capitals, punctuation and little words such as "it"
    and "the": "Descale it every 6 months." and "descale every 6 months" are one tip."""
    return _tip_words(a) == _tip_words(b)


def _tip_words(tip: str) -> list[str]:
    return [w for w in plain_words(tip) if w not in _NOT_TIP_WORDS]


# --- Which tips to show first: the ones most writers agree on (decided by Claude, 10 Oct 2026) ---

def tips_by_agreement(tips: CareTips) -> list[list[CareTip]]:
    """A product's care tips gathered into groups that say the same thing, in the order to show them: tips about
    looking after the product first, the group most distinct credible writers agree on first, then the group with the
    higher voice, then the one whose best tip is about the product itself rather than its kind, then thread order;
    repairs last, in the same order. Each group lists its tips best writer first: the higher voice, then the product's
    own tip, then thread order. The rules are at the top of this file."""
    every = list(tips.own) + list(tips.kind)  # own tips first, each part in thread order: a tip's place breaks ties
    words = [_content_words(tip.tip) for tip in every]
    repair = [is_repair(tip.tip) for tip in every]
    groups: list[list[int]] = []  # each group's tips, by their place in `every`; its first tip comes first
    for i in range(len(every)):
        first = (g for g in groups if repair[g[0]] == repair[i]
                 and _alike(every[g[0]].tip, every[i].tip, words[g[0]], words[i]))
        group = next(first, None)
        if group is None:
            groups.append([i])
        else:
            group.append(i)

    def best_first(i: int) -> tuple:
        return VOICE_LEVELS.index(every[i].voice), i

    def order(members: list[int]) -> tuple:
        writers = {_writer(every[i]) for i in members}
        return repair[members[0]], -len(writers), min(map(best_first, members))

    return [[every[i] for i in sorted(members, key=best_first)] for members in sorted(groups, key=order)]


def similar_tips(a: str, b: str) -> bool:
    """Whether two tips say the same thing: the same tip (same_tip), or tips that share at least CARE_TIP_SHARED_WORDS
    words, with at least CARE_TIP_SHARED_SHARE of both tips' words, counted together, being words both have, little
    words and endings aside ("descale it with vinegar" and "descaling with white vinegar regularly": 4 of 6). A tip
    that says "don't" (or "no", "not", "never", "avoid") never says the same thing as one that doesn't: "use soap" is
    the opposite of "don't use soap". Two tips that both give numbers, but not the same ones, don't either: "grind at
    12" and "grind at 20"."""
    return _alike(a, b, _content_words(a), _content_words(b))


def _alike(a: str, b: str, words_a: set[str], words_b: set[str]) -> bool:
    """similar_tips, with each tip's words (_content_words) worked out once."""
    if same_tip(a, b):
        return True
    if _says_no(a) != _says_no(b):
        return False
    numbers_a, numbers_b = _numbers(words_a), _numbers(words_b)
    if numbers_a and numbers_b and numbers_a != numbers_b:
        return False
    shared = len(words_a & words_b)
    return shared >= CARE_TIP_SHARED_WORDS and 2 * shared >= CARE_TIP_SHARED_SHARE * (len(words_a) + len(words_b))


def is_repair(tip: str) -> bool:
    """Whether a tip is about fixing a broken part rather than looking after the product: it holds one of
    config.CARE_TIP_REPAIR_WORDS as whole words ("seal", "glue", "replace", "solder", "sand", "epoxy", "angle grinder",
    "grind it flat", "repair")."""
    text = " ".join(plain_words(tip))
    return any(re.search(rf"\b(?:{pattern})\b", text) for pattern in CARE_TIP_REPAIR_WORDS)


# Words that carry little of a tip's meaning, left out when two tips' words are compared (on top of _NOT_TIP_WORDS).
_LITTLE_WORDS = frozenset({
    "in", "on", "of", "to", "for", "with", "and", "or", "by", "at", "from", "into", "onto", "then", "so", "as", "is",
    "are", "be", "this", "that", "these", "those", "if", "when", "while", "all", "any", "some", "each", "every", "once",
    "too", "very", "just", "also", "up", "do", "does", "can", "will", "should", "much", "more", "less", "only", "out",
})
# Words that turn a tip into its opposite: "don't use soap" (apostrophes are dropped: "dont").
_NO_WORDS = frozenset({
    "no", "not", "never", "dont", "doesnt", "cant", "wont", "shouldnt", "avoid", "without", "nothing",
})


def _content_words(tip: str) -> set[str]:
    """The words of a tip that carry its meaning, without their endings: "Descaling it with vinegar" -> descal,
    vinegar. Words that say "no" are left out too: _says_no compares them."""
    left_out = _NOT_TIP_WORDS | _LITTLE_WORDS | _NO_WORDS
    return {_stem(word) for word in plain_words(tip) if word not in left_out}


def _says_no(tip: str) -> bool:
    return any(word in _NO_WORDS for word in plain_words(tip))


def _numbers(words: set[str]) -> set[str]:
    return {word for word in words if word.isdigit()}


def _stem(word: str) -> str:
    """A word without its ending, so "descale", "descales", "descaled" and "descaling" are one word: in words of 4
    letters or more, a final "s" (not "ss"), then "ing" or "ed" (leaving 3 letters at least), then a final "e"."""
    if len(word) < 4 or word.isdigit():
        return word
    if word.endswith("s") and not word.endswith("ss"):
        word = word[:-1]
    for ending in ("ing", "ed"):
        if word.endswith(ending) and len(word) - len(ending) >= 3:
            word = word[:-len(ending)]
            break
    return word[:-1] if word.endswith("e") and len(word) > 3 else word


def _writer(tip: CareTip) -> tuple[str, str]:
    """Who wrote a tip: the writer's name, or, for a deleted account, the comment (so each of its comments counts)."""
    return ("writer", tip.author) if tip.author is not None else ("comment", tip.comment_id)

