"""Features a request names for its product, and whether a credible voice praises a product for them (module 6;
Noemi's decision 1 of 16 Oct 2026, built 17 Oct 2026 in the converge round, ws-ranking).

"noise cancelling headphones", "gaming laptop", "automatic watch", "quiet kettle": in a kitchen or general request the
words before the product noun name a feature the shopper wants, not a need about themselves. The review of 16 Oct had
found studio headphones, wired and open-back, answering noise cancelling headphones, a MacBook Air the gaming laptop,
quartz watches the automatic one and kettles nobody calls quiet a quiet kettle. Her decision: the products a credible
voice praises for the feature rank first (engine.rank), but an answer is never emptied by it: when no pick is praised
for it, the type's best products are still shown, with a note saying so (FEATURE_NOT_PRAISED, wording PROPOSED).
Skincare and haircare keep their own need rule (engine.pipeline._ranked).

Which words are a feature (request_features): the request's needs a comment can talk about (engine.needs.judged_needs)
that it names before the product noun (the type's last word, or one of its one-word names: "headphones", "kettle",
"hoover"), or right after it as "that's X" ("a kettle that's quiet", the same ask as "a quiet kettle"). Never a need
about the buyer (beginner, home cook, lasting: config.FEATURE_CONFIG_NEEDS lists the config needs that describe a
product), a word of a checked requirement (a PFAS-free or non-stick pan: the product's facts settle those, engine.
product_facts.hard_requirements, and must-haves already rank first), or a word that only names the product ("coffee" in
"coffee machine", config.FEATURE_PLAIN_WORDS). Request words written together are one feature ("noise cancelling",
"true wireless", "cast iron"). A request whose product noun isn't in its words ("portable charger" for a power bank)
names no feature.

When a credible recommendation praises a product for a feature (praised_for): in the product's own words (engine.
credibility.product_text: its sentences, without the clauses about another product, another model or another person),
the feature is said and not denied ("great noise cancelling", "so quiet", "not loud"), and nothing says its opposite
("very noisy" for quiet: config.FEATURE_AGAINST_WORDS); or the comment answers a thread whose title or post asks for the
feature (a thread asking which adjustable dumbbells to buy) and says nothing against it. Never when the product's own name
says the opposite (config.FEATURE_OPPOSITE_NAMES: a corded drill for a cordless one, whose writer had said "cordless can
be handy, but..."). The review's examples, on the 16 Oct library: a Cuisinart line whose one voice about noise called it
very noisy had come first for a quiet kettle by mere talk; the Sage line, called much quieter, is praised.
"""

import re
from dataclasses import dataclass
from functools import cache

from engine import config
from engine.models import Thread
from engine.needs import Need, judged_needs, thread_needs
from engine.query import PRODUCT_TYPES, ParsedQuery

# What the answer says when no pick is praised for a feature asked for (Noemi's decision 1 of 16 Oct 2026: "if we can't
# find any, still show up with the main prod"). Wording PROPOSED (decided by Claude, waiting for Noemi): the typed words
# in quotation marks, since they can be any words ("gaming", "noise cancelling", "4k").
FEATURE_NOT_PRAISED = ("No credible voice in the threads we read praised these picks for {features}: they are the "
                       "best-supported {products} overall, so check that before you buy.")
FEATURE_NOT_PRAISED_ONE = ("No credible voice in the threads we read praised this pick for {features}: it is the "
                           "best-supported {product} overall, so check that before you buy.")
FEATURES_JOIN = " or "


@dataclass(frozen=True)
class Feature:
    """One feature the request names, and how a comment praises a product for it."""

    name: str  # as typed in the request: "noise cancelling", "quiet", "4k"
    needs: tuple[Need, ...]  # the request's needs it is made of (engine.needs.judged_needs)
    praise: str  # a pattern finding the feature said in a comment (lowercase)
    against: str | None = None  # a pattern finding its opposite said ("noisy", "loud" for quiet), or None
    # A material (config.FEATURE_MATERIALS: stainless steel, cast iron, glass...): comments compare materials and
    # threads asking for one get answers proposing another, so only the writer's own words count, and only in a clause
    # that holds the product itself (its name or a word pointing at it: "it", "these").
    material: bool = False


def request_features(query: ParsedQuery) -> tuple[Feature, ...]:
    """The features a kitchen or general request names for its product, in its order (see the module's docstring);
    none for any other request. Worked out once per request."""
    if query.status != "ok" or query.category not in config.FEATURE_CATEGORIES or query.ingredient_led:
        return ()
    key = query.model_dump_json()
    if key not in _FEATURES:
        if len(_FEATURES) > 10_000:
            _FEATURES.clear()
        _FEATURES[key] = _request_features(query)
    return _FEATURES[key]


_FEATURES: dict[str, tuple] = {}  # a request, as module 1 read it -> its features


def _request_features(query: ParsedQuery) -> tuple[Feature, ...]:
    text = _plain(query.text)
    head = _head_noun(text, query.product_type or "")
    if head is None:
        return ()
    head_start, head_end, noun_start = head
    after = _THATS.match(text, head_end)  # "a kettle that's quiet": the words right after "that's" too
    window = (after.end(), after.end() + len(_THATS_WORDS.match(text, after.end()).group(0))) if after else None
    asked, required = _requirements(query)
    plain_words = set(config.FEATURE_PLAIN_WORDS) | required
    found: list[tuple[int, int, Need]] = []  # (start, end, need) of the request's needs named as features
    for need in judged_needs(query):
        if need.request_word is None:
            if need.name not in config.FEATURE_CONFIG_NEEDS or need.name in asked:
                continue
            spans = [m.span() for word in (need.name,) + need.words for m in _whole(word).finditer(text)]
        else:
            if need.request_word in plain_words:
                continue
            spans = [m.span() for m in _typed_word(need.request_word).finditer(text)]
        spans = [s for s in spans if s[1] <= head_start or (window and window[0] <= s[0] < window[1])]
        if spans:
            start, end = min(spans, key=lambda span: (span[0], -span[1]))  # the longest of the earliest
            found.append((start, end, need))
    found.sort(key=lambda f: f[0])
    features: list[Feature] = []
    group: list[tuple[int, int, Need]] = []
    for item in found + [None]:
        joined = (item is not None and group and item[2].request_word is not None and group[-1][2].request_word
                  is not None and _JOINED.fullmatch(text[group[-1][1]:item[0]]))
        if group and not joined:
            # Named up to the noun itself when the product's other names come between ("raw denim" in "raw denim jeans").
            name_end = noun_start if _JOINED.fullmatch(text[group[-1][1]:head_start]) else None
            features.append(_feature(query.text, text, group, name_end))
            group = []
        if item is not None:
            group.append(item)
    return tuple(features)


def _feature(typed: str, text: str, group: list[tuple[int, int, Need]], name_end: int | None = None) -> Feature:
    """One feature from request needs written together ("noise" and "cancelling"): named as typed (up to `name_end` when
    given), praised when its words are said in a row, or as config's short forms ("anc"); a config need ("quiet") by
    its praise words."""
    start, end = group[0][0], group[-1][1]
    name = typed[start:max(end, name_end or 0)].strip()
    needs = tuple(need for _, _, need in group)
    material = _a_material(name)
    if needs[0].request_word is None:
        words = config.FEATURE_PRAISE_WORDS.get(needs[0].name, (needs[0].name,) + needs[0].words)
        against = config.FEATURE_AGAINST_WORDS.get(needs[0].name)
        return Feature(name, needs, _any_of(words), _any_of(against) if against else None, material)
    phrase = r"[\s-]*".join(_word_pattern(need.request_word) for need in needs)
    shorts = config.FEATURE_SHORT_FORMS.get(" ".join(n.request_word for n in needs), ())
    praise = "|".join([rf"(?<![a-z0-9]){phrase}"] + [rf"(?<![a-z0-9]){re.escape(s)}(?![a-z0-9])" for s in shorts])
    return Feature(name, needs, praise, None, material)


def _a_material(name: str) -> bool:
    words = name.lower().replace("-", " ").split()
    return any(" ".join(words[i:]) in config.FEATURE_MATERIALS for i in range(len(words)))


def praised_for(feature: Feature, text: str, names: tuple[str, ...] = (), thread_asks: bool = False) -> bool:
    """Whether a comment's words about a product (`text`: engine.credibility.product_text, lowercase) praise it for the
    feature: said and not denied, with nothing against it; or the comment answers a thread asking for the feature
    (`thread_asks`) and says nothing against it. Never when one of the product's own `names` says the opposite."""
    if _named_the_opposite(feature, names):
        return False
    holder = _holds_the_product(names) if feature.material else None
    said, denied = _said(feature.praise, text, holder)
    against, against_denied = _said(feature.against, text, holder) if feature.against else (False, False)
    if denied or against:
        return False
    return said or against_denied or (thread_asks and not feature.material)


def thread_asks_for(thread: Thread, feature: Feature, titled_as_another_type: bool = False) -> bool:
    """Whether a thread's title or post asks for the feature (engine.needs.thread_needs, as the need-led first reading
    reads them): every need of the feature, so "noise from my fridge" asks nothing of noise cancelling, or the feature
    said in the title as a comment would praise it (its short forms too: "wireless earbuds" for true wireless ones). A
    material's thread asks nothing that counts (Feature.material)."""
    if feature.material or titled_as_another_type:
        return False
    met = thread_needs(thread, feature.needs, titled_as_another_type)
    if all(need.name in met for need in feature.needs):
        return True
    return bool(_compiled(feature.praise).search(_plain(thread.title or "")))


def feature_note(features: tuple[Feature, ...], praised_by_pick: list[tuple[str, ...]], products: str,
                 product: str | None = None) -> str | None:
    """FEATURE_NOT_PRAISED for the features no shown pick is praised for (`praised_by_pick`: each pick's praised
    features; `products` the type in the plural, `product` in the singular for an answer of one pick,
    FEATURE_NOT_PRAISED_ONE), or None when every feature has a praised pick, or there are no picks or no features."""
    if not features or not praised_by_pick:
        return None
    unmet = [f.name for f in features if not any(f.name in praised for praised in praised_by_pick)]
    if not unmet:
        return None
    named = FEATURES_JOIN.join(f'"{name}"' for name in unmet)
    if len(praised_by_pick) == 1:
        return FEATURE_NOT_PRAISED_ONE.format(features=named, product=product or products)
    return FEATURE_NOT_PRAISED.format(features=named, products=products)


# --- Helpers ---

_THATS = re.compile(r"\s+(?:that|which)(?:'s|'re| is| are)\s+(?:(?:really|very|super|actually|fairly|pretty|properly"
                    r"|truly|quite|reasonably)\s+)?")
_JOINED = re.compile(r"[\s-]*")  # two request words written together: "noise cancelling", "noise-cancelling"
# The words "that's" describes, up to where the sentence goes on to something else ("for", "under", "and"...).
_THATS_WORDS = re.compile(r"[a-z0-9' -]*?(?=$|[,.;!?]|\s(?:and|but|or|for|with|under|over|from|to|in|on|at|that|which"
                          r"|so|because|less|more|than)(?![a-z0-9]))")


def _head_noun(text: str, product_type: str) -> tuple[int, int, int] | None:
    """Where the product noun is in the request (lowercase): the earliest of the type's last word (or its plural) and its
    one-word names, as whole words, (its start, its end, the start of the last of the product's words written in a row
    from it: "jeans" in "denim jeans"); None when none is written ("portable charger" for a power bank)."""
    heads = {product_type.split()[-1]} if product_type else set()
    product = next((p for p in PRODUCT_TYPES if p.name == product_type), None)
    if product is not None:
        heads |= {k.lower() for k in product.keywords if " " not in k}
    forms = {form for head in heads for form in (head, head + "s", head + "es")}
    best = None
    for form in forms:
        match = re.search(rf"(?<![a-z0-9]){re.escape(form)}(?![a-z0-9])", text)
        if match and (best is None or match.start() < best[0]):
            best = match.span()
    if best is None:
        return None
    noun_start, at = best[0], best[1]
    while (following := re.match(r"\s+([a-z0-9'-]+)", text[at:])) and following.group(1) in forms:
        noun_start, at = at + following.start(1), at + following.end(1)
    return best[0], best[1], noun_start


def _requirements(query: ParsedQuery) -> tuple[set[str], set[str]]:
    """(the checked requirements' asks the request names, their words as need words are written): a PFAS-free or
    non-stick pan, which the product's facts settle (engine.product_facts.hard_requirements). The words also written
    together ("nonstick" for "non-stick"), as need words drop hyphens."""
    from engine.product_facts import hard_requirements  # here: engine.product_facts builds on engine.needs

    asked, words = set(), set()
    for name in hard_requirements(query):
        for ask in config.PRODUCT_FACT_RULES[name]["asks"]:
            asked.add(ask)
            parts = re.findall(r"[a-z0-9]+", ask.lower())
            words |= {_stem(word) for word in parts} | {_stem("".join(parts))}
    return asked, words


def _named_the_opposite(feature: Feature, names: tuple[str, ...]) -> bool:
    opposites = config.FEATURE_OPPOSITE_NAMES.get(feature.name.lower().replace("-", " "), ())
    return any(re.search(_any_of(opposites), _plain(name)) for name in names if name) if opposites else False


def _said(pattern: str | None, text: str, holder: re.Pattern | None = None) -> tuple[bool, bool]:
    """(said and not denied, said and denied): whether `pattern` is found in `text`, and with a negation among the
    three words before it ("not", "isn't", "no", "never"...). Only in a clause `holder` finds, when given (a material's:
    the product's name or a word pointing at it)."""
    if not pattern:
        return False, False
    said = denied = False
    for match in _compiled(pattern).finditer(text):
        clause = _clause_around(text, match.start())
        if _ASIDE.search(clause):
            continue  # "if you want noise cancelling, ...", "skip the gaming laptops": nothing said of this one
        if holder is not None and not holder.search(clause):
            continue  # a general word for stainless steel says nothing of this pan
        before = " ".join(text[:match.start()].split()[-3:])
        if _NEGATION.search(before):
            denied = True
        else:
            said = True
    return said, denied


def _holds_the_product(names: tuple[str, ...]) -> re.Pattern:
    """A pattern finding the product in a clause: a word of its own names that picks it out (engine.credibility's
    name words: "tramontina", "allclad"), or a word pointing at it ("it", "these", "this one")."""
    from engine.credibility import name_words  # here: engine.credibility reads names as module 5 does

    words = sorted({word for name in names if name for word in name_words(name)}, key=len, reverse=True)
    alternatives = [re.escape(word) for word in words] + list(_POINTERS)
    return re.compile(r"(?<![a-z0-9'])(?:" + "|".join(alternatives) + r")(?![a-z0-9'])")


# Never "my" or "our" alone: "I heat my stainless on medium", beside a ceramic pan, is the writer's other pan.
_POINTERS = (r"it", r"it's", r"its", r"they", r"they're", r"them", r"these", r"this", r"those", r"this one",
             r"that one")


def _clause_around(text: str, at: int) -> str:
    """The clause of `text` holding position `at`: between the punctuation or "but" before and after it."""
    starts = [m.end() for m in _CLAUSE_EDGE.finditer(text, 0, at)]
    end = _CLAUSE_EDGE.search(text, at)
    return text[(starts[-1] if starts else 0):(end.start() if end else len(text))]


_CLAUSE_EDGE = re.compile(r"[,;:.!?()\n]|\s(?:but|though|although|whereas|while)\s")
# A clause that speaks of a feature without praising a product for it: a condition or advice for someone else ("if you
# want noise cancelling", "for anyone who needs a cordless one"), or a setting aside ("skip the gaming laptops",
# "instead of a cordless drill", "over the noise cancelling ones").
_ASIDE = re.compile(r"^\s*(?:if|unless|when|whether|for (?:anyone|those|people|someone)|anyone who|those who)(?![a-z'])"
                    r"|(?<![a-z'])(?:instead of|rather than|skip|avoid|steer clear|stay away|over (?:the|a|any))(?![a-z'])")


_NEGATION = re.compile(r"(?<![a-z'])(?:no|not|never|without|zero|nor|hardly|barely|non|isn'?t|aren'?t|wasn'?t|weren'?t"
                       r"|doesn'?t|don'?t|didn'?t|won'?t|wouldn'?t|can'?t|cannot|couldn'?t|lacks?|lacking)(?![a-z'])")


@cache
def _compiled(pattern: str) -> re.Pattern:
    return re.compile(pattern)


def _any_of(words) -> str:
    return "|".join(rf"(?<![a-z0-9]){re.escape(word.lower())}" + (r"(?![a-z0-9])" if " " in word or len(word) < 4
                                                                    else "") for word in words)


def _word_pattern(word: str) -> str:
    """A request word as a comment may write it: whole when short, else its beginning (longer forms), in British and US
    spellings (engine.sources.spelling_variants: "cancel" finds cancelling, canceling and cancellation)."""
    from engine.sources import spelling_variants

    if len(word) < 4:
        return re.escape(word) + r"(?![a-z0-9])"
    return "(?:" + "|".join(re.escape(form) for form in spelling_variants(word)) + r")[a-z]*"


@cache
def _typed_word(word: str) -> re.Pattern:
    """A need word (engine.sources.need_words: letters and digits, a plural trimmed) where the request typed it."""
    letters = r"['-]?".join(re.escape(ch) for ch in word)
    return re.compile(rf"(?<![a-z0-9]){letters}s?(?![a-z0-9])")


@cache
def _whole(word: str) -> re.Pattern:
    return re.compile(rf"(?<![a-z0-9]){re.escape(word.lower())}")


def _stem(word: str) -> str:
    return word[:-1] if len(word) > 4 and word.endswith("s") and not word.endswith("ss") else word


def _plain(text: str) -> str:
    return text.lower().replace("’", "'").replace("‘", "'")
