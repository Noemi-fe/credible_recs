"""Writers who contradict themselves (module 6, ranking; Noemi's rule, 9 Oct 2026).

If the same writer recommends a product in one comment and warns against it in another, in any of the request's
threads, and never says what changed, we can't tell which of their opinions to believe. So every mention they make
counts as a low voice: its weight is worked out again with the low voice value (config.VOICE_VALUE["low"]), and none
of it is credible, so it never counts towards the minimum-evidence rule (engine.pipeline does this).

What counts:
- the same writer: the same username, compared lowercased. Deleted accounts never match: two of them can't be told
  apart;
- the same product: the same product group of module 4, so "Zojirushi" and "Zojirushi kettle" are one product. Every
  mention of the threads read counts, also those of products later left out of the ranking (another type, over
  budget): what the writer said is the same either way. Recommending different products for different needs is
  not a contradiction;
- a recommendation and a warning in two different comments. One comment with mixed feelings ("boils fast, but the lid
  is flimsy") is honest, not a contradiction. Neutral mentions take no side, so they never count;
- without saying something changed: an update is honest. A warning says something changed when the writer's own
  words (not a quoted block) report a change over time or an event: words of config.CHANGE_WORDS ("died", "broke",
  "reformulated", "no longer", "used to", "update", "edit", "developed a reaction"…) or "after" a number of days,
  weeks, months or years ("after 6 months", "after a couple of years"). It is enough that one of the writer's warnings
  about the product says so: a later "yeah, avoid it" continues the same story.

Who contradicts themselves is kept on the pipeline's result for reports (as a count), never shown to users.
"""

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping

from engine.config import CHANGE_WORDS
from engine.credibility import _own_words
from engine.group_products import ProductGroup
from engine.models import Comment
from engine.needs import has_word

# "after 6 months", "after a couple of years", "after about two weeks": up to three words between "after" and the time.
_AFTER_A_TIME = re.compile(r"\bafter\s+(?:[\w.+-]+\s+){1,3}?(?:days?|weeks?|months?|years?|yrs?)\b")


def contradicting_writers(groups: Iterable[ProductGroup], comments: Mapping[str, Comment]) -> set[str]:
    """The writers (lowercased names) who recommend a product in one comment and warn against it in another, without
    saying in any of those warnings that something changed.

    `groups` are module 4's product groups of every mention in the request's threads; `comments` is {comment id:
    Comment} for those threads.
    """
    contradicting = set()
    for group in groups:
        sides: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))  # writer -> stance -> comment ids
        for mention in group.mentions:
            comment = comments.get(mention.comment_id)
            if comment is None or comment.author is None or mention.stance == "neutral":
                continue  # a deleted account (no name) never matches anyone
            sides[comment.author.name.lower()][mention.stance].add(mention.comment_id)
        for name, said in sides.items():
            recommends, warnings = said["recommend"], said["warn"]
            in_two_comments = any(r != w for r in recommends for w in warnings)
            if in_two_comments and not any(says_something_changed(comments[w].body) for w in warnings):
                contradicting.add(name)
    return contradicting


def says_something_changed(body: str) -> bool:
    """Whether a comment's own words report a change over time or an event: something died, broke, was reformulated,
    "no longer", "used to", an update or edit, a reaction, or "after" some days, weeks, months or years."""
    text = _own_words(body)
    return any(has_word(text, word) for word in CHANGE_WORDS) or bool(_AFTER_A_TIME.search(text))
