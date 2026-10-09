"""Care tips, "how to make it last" (Noemi, 9 Oct 2026): credible advice from the threads on looking after a product,
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
   The answer (engine/answer.py) then shows up to CARE_TIPS_PER_PICK per pick, the product's own tips first, never
   the same tip twice (same_tip), each quote checked again word for word before it is shown.

What words can't do (as for notes, engine/group_kinds.py): kinds that mean the same in other words stay apart, and
most product names don't say their kind ("Lodge"), so a tip about a kind other than the requested one reaches only
products whose names say it ("Lodge cast iron skillet"). A tip about a narrower kind than any group ("enameled cast
iron" when only "cast iron" has notes) goes with that broader kind's products.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from engine.config import CREDIBLE_VOICES
from engine.credibility import score_voice
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
        if result is None:
            continue
        comments = {c.id: c for c in thread.comments}
        for care in result.kept_care:
            comment = comments[care.comment_id]
            voice = score_voice(comment, thread, result.kept_agreements)
            if voice.level not in CREDIBLE_VOICES:
                continue
            tips.append(CareTip(
                about=care.about, is_kind=care.is_kind, tip=care.tip, quote=care.quote, thread_id=thread.id,
                comment_id=care.comment_id, comment_url=str(comment.url), voice=voice.level, badges=voice.badges,
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
