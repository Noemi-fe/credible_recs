"""Module 5, credibility scoring: how far to trust a comment's writer, how well they know each product they
mention, and so how much each mention weighs.

Two layers (the brief's "Credibility score v1", with Noemi's definitions from data/gold/LABELLING_GUIDE.md):

- Voice, once per comment (score_voice): about the writer and the comment, whatever the product. It looks for
  good signs (established member, well-regarded account, expert flair, well upvoted for the thread's size, replies
  that agree, recent, enthusiast) and red flags (new account, low karma for its activity, salesy language, promotes
  one brand, downvoted, and since 11 Oct 2026 copied text: the same words as another writer's comment in the thread,
  worked out once per thread by copied_comment_ids). The rubric (Noemi, 9 Oct 2026) turns them into a level by
  counting red flags:
      high    good signs worth at least 2 (VOICE_HIGH_MIN_GOOD_SIGNS) and no red flag;
      medium  no red flag and fewer good signs (an ordinary owner), or exactly one red flag whatever the good signs:
              a new account alone doesn't sink a genuine expert, but it stops them being high;
      low     two red flags or more (VOICE_LOW_MIN_RED_FLAGS). Clear paid promotion (a discount code, an affiliate
              or referral link, "#ad") counts as two on its own (PAID_PROMOTION_RED_FLAGS): it isn't a hint, it's a
              conflict of interest.
  An old skincare or haircare comment can be at most medium (OLD_SKINCARE_POST_MAX_VOICE): formulas change.
  The guide also lists "no sign they've used anything" as a red flag. It is a switch (VOICE_RED_FLAG_NO_USE), off
  for now: Noemi's labels never applied it, and the evidence layer already scores it.
- Evidence, once per product mention (score_evidence): how well this writer knows this product. Proof of use sets
  the level (long-term use: a year or more, or "still going"; short-term use: days, weeks, "just bought", or use
  with no time given; no first-hand use: heard, read, never tried, or suggested without saying they used it).
  Honesty adds tags: mentions flaws, compares alternatives (names other products it was used with, before or
  instead), specific details (sizes, settings, how it failed), and "vague" when there is nothing concrete.

A mention's weight (mention_weight) = voice value x evidence value x stance value, with the values in
engine/config.py (VOICE_VALUE, EVIDENCE_VALUE, STANCE_VALUE): recommend counts plus, warn minus, neutral nothing.

For Noemi's upvote rule (14 Oct 2026, switched off: config.UPVOTE_COUNTS_MORE), thread_upvotes also gives each comment's
upvotes beside its thread's (its score, the thread's size, the share of its comments it beats): numbers only. Whether a
credible recommendation then counts twice toward the picks bar is module 6's rule (engine/rank.py).

Every result keeps its reasons in words ("2 years of use", "compares 4 alternatives", "flair says Dermatologist
(not verified)"), so the answer can show why a voice counts. Tags come from config.VOICE_TAGS and
config.EVIDENCE_TAGS, so the results compare directly with Noemi's labels (engine/credibility_eval.py).

What this version can't see yet:
- The brief's v1 uses an AI judge for proof of use and honesty. There is no API key, so these are word rules: they
  read phrases, not meaning, and miss what is said in unusual ways.
- Account age, karma, contributions and flair: Parse gives only a username, so saved threads have none of them.
  engine/profiles.py fills them in from the Arctic Shift archive before scoring (numbers and flair only); the rules
  use them whenever they are filled in. "Account age" is then the writer's first activity in the archive.
- The writer's history in this topic (active in this topic, usually upvoted): it will come from the Arctic Shift
  archive as numbers only (CLAUDE.md, "Commenter history"). CommenterHistory is the place it plugs in.
"""

import html
import re
from bisect import bisect_left
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from functools import cache
from datetime import datetime
from itertools import combinations
from typing import Literal

from engine import config
from engine.extract import ExtractedAgreement
from engine.match_products import normalize_name, same_product
from engine.memo import Table
from engine.models import Author, Comment, Thread
from engine.text import one_edit_apart

# --- What the scores look like ---

SignKind = Literal["good", "red flag", "note"]


@dataclass(frozen=True)
class Sign:
    """One thing noticed about a comment's writer, such as "well upvoted" or "new account"."""

    name: str  # a voice tag ("well upvoted", "downvoted"), or a sign with no tag of its own ("deleted comment")
    reason: str  # the same thing in words, for the "why this voice counts" badge
    kind: SignKind  # a good sign, a red flag, or just noted (an old post, a deleted account)
    red_flags: int = 1  # how many red flags it counts as: paid promotion counts as PAID_PROMOTION_RED_FLAGS

    @property
    def tag(self) -> str | None:
        """The voice tag this sign is recorded under: its name, or "other" for a sign with no tag of its own.

        "replies agree" and "downvoted" became tags on 9 Oct 2026 (Noemi's decision 13), so they are recorded under
        their own names, as "copied text" is from the start (11 Oct 2026); "deleted comment" and "no sign of use" are
        still "other".
        """
        if self.name in config.VOICE_TAGS:
            return self.name
        return config.OTHER_TAG if self.kind != "note" else None


@dataclass(frozen=True)
class VoiceScore:
    """How far to trust the writer of one comment: a level and the signs behind it."""

    level: str  # "high", "medium" or "low"
    signs: tuple[Sign, ...]

    @property
    def tags(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(sign.tag for sign in self.signs if sign.tag))

    @property
    def reasons(self) -> tuple[str, ...]:
        return tuple(sign.reason for sign in self.signs)

    @property
    def good_signs(self) -> tuple[Sign, ...]:
        return tuple(sign for sign in self.signs if sign.kind == "good")

    @property
    def red_flags(self) -> tuple[Sign, ...]:
        return tuple(sign for sign in self.signs if sign.kind == "red flag")

    @property
    def badges(self) -> tuple[str, ...]:
        """The good signs in words, for "why this voice counts". Recency is left out: nearly every comment has it."""
        return tuple(sign.reason for sign in self.good_signs if sign.name != "recent")


@dataclass(frozen=True)
class EvidenceScore:
    """How well one writer knows one product: a level, the evidence tags, and the reasons in words."""

    level: str  # "long-term use", "short-term use" or "no first-hand use"
    tags: tuple[str, ...]
    reasons: tuple[str, ...]
    badges: tuple[str, ...] = ()  # the reasons worth showing: long-term use and signs of honesty ("3 years of use")


@dataclass(frozen=True)
class CommenterHistory:
    """What the writer's past comments say about them: numbers only, never their text.

    It will come from the Arctic Shift archive (CLAUDE.md, "Commenter history", approved 9 Oct 2026): the subreddit,
    score and date of each past comment, turned into these few numbers and kept at most 48 hours. Nothing fetches it
    yet; this is where it plugs in. None means unknown.
    """

    contributions: int | None = None  # how many posts and comments the account has written (Author.contributions first)
    active_in_topic: bool | None = None  # regularly active in this topic's subreddits
    usually_upvoted: bool | None = None  # its comments there are usually upvoted


# What a comment's own words show, worked out once per comment and remembered (latency, 12 Oct 2026): the next answer
# reading the same thread asks again. Each depends only on what its key holds (engine.memo.Table).
_INDEPENDENCE = Table()
_CARE = Table()
_EVIDENCE = Table()
_COPIES = Table(limit=20_000)


# --- Voice: once per comment ---

def score_voice(
    comment: Comment,
    thread: Thread,
    agreements: Iterable[ExtractedAgreement] = (),
    history: CommenterHistory | None = None,
    copied: Collection[str] | None = None,
) -> VoiceScore:
    """How far to trust the writer of `comment`, a comment of `thread`.

    `agreements` are the replies the extraction found agreeing with the comment above them (any in the thread; only
    the ones answering this comment count). `history` is the writer's commenter history, when known. `copied` are the
    thread's comments that copy another writer's words (copied_comment_ids): a caller scoring many comments of one
    thread works them out once and passes them in; left out, they are worked out here.
    """
    if comment.status != "ok":
        return VoiceScore("low", (Sign("deleted comment", f"the comment was {comment.status}: nothing to go on", "red flag"),))
    text = _own_words(comment.body)
    if copied is None:
        copied = copied_comment_ids(thread)
    signs = (
        _standing_signs(comment, history)
        + _independence_signs(text)
        + _copy_signs(comment, copied)
        + _endorsement_signs(comment, thread, agreements)
        + _recency_signs(comment, thread)
        + _care_signs(text, thread.category)
    )
    return VoiceScore(_voice_level(signs, thread.category), tuple(signs))


def _voice_level(signs: list[Sign], category: str) -> str:
    """The rubric: two red flags or more are low; one caps the voice at medium; good signs worth enough are high."""
    red_flags = sum(sign.red_flags for sign in signs if sign.kind == "red flag")
    if red_flags >= config.VOICE_LOW_MIN_RED_FLAGS:
        return "low"
    worth = sum(config.VOICE_SIGN_WEIGHTS.get(sign.name, 1) for sign in signs if sign.kind == "good")
    level = "high" if worth >= config.VOICE_HIGH_MIN_GOOD_SIGNS and not red_flags else "medium"
    if category in config.REFORMULATED_CATEGORIES and any(sign.name == "old post" for sign in signs):
        level = _lower(level, config.OLD_SKINCARE_POST_MAX_VOICE)
    return level


def _lower(level: str, cap: str) -> str:
    """The lower of two voice levels."""
    return max(level, cap, key=config.VOICE_LEVELS.index)


# Community standing: who the writer is.

# Words in a flair that claim expertise. Anyone can type them in most subreddits, so they are worded as a claim.
EXPERT_FLAIR_WORDS = (
    "dermatologist", "dermatology", "derm", "esthetician", "aesthetician", "chemist", "formulator", "cosmetologist",
    "pharmacist", "physician", "doctor", "md", "nurse",
    "chef", "line cook", "professional", "culinary", "bladesmith", "knifemaker", "knife maker", "sharpener",
    "butcher", "barista", "roaster", "food scientist",
)
# Words that make a flair a hobby, not a profession ("Home Cook", "Aspiring Chef").
NOT_EXPERT_FLAIR_WORDS = ("home", "amateur", "hobby", "hobbyist", "aspiring", "student", "wannabe")


def _standing_signs(comment: Comment, history: CommenterHistory | None) -> list[Sign]:
    """Account age, karma and flair, measured when the comment was written; plus the commenter history if known."""
    author = comment.author
    if author is None:
        return [Sign("deleted account", "account deleted: its age, karma and flair are unknown", "note")]
    age_days = _account_age_days(author, comment.created_at)
    signs = []
    if age_days is not None and age_days < config.NEW_ACCOUNT_DAYS:
        signs.append(Sign("new account", f"account {age_days} days old when it wrote this", "red flag"))
    established = _established(author, age_days, history)
    if established:
        signs.append(Sign("established member", established, "good"))
    regard = _regard(author, age_days, history)
    if regard:
        signs.append(regard)
    if _is_expert_flair(author.flair):
        signs.append(Sign("expert flair", f'flair says "{author.flair}" (not verified)', "good"))
    return signs


def _account_age_days(author: Author, written: datetime) -> int | None:
    if author.account_created_at is None:
        return None
    return max(0, (written - author.account_created_at).days)


def _established(author: Author, age_days: int | None, history: CommenterHistory | None) -> str | None:
    """Why the writer is an established member (old enough and active), or None.

    Activity comes from the commenter history when known; until then, karma stands in for it.
    """
    if age_days is None or age_days < config.ESTABLISHED_ACCOUNT_YEARS * 365.25:
        return None
    years = int(age_days // 365.25)
    if history is not None and history.active_in_topic is not None:
        return f"account {years} years old, active in this topic's communities" if history.active_in_topic else None
    if author.karma is not None and author.karma >= config.ESTABLISHED_MIN_KARMA:
        return f"account {years} years old, {author.karma:,} karma"
    return None


def _regard(author: Author, age_days: int | None, history: CommenterHistory | None) -> Sign | None:
    """How the writer's comments are received: "well-regarded account", "low karma for its activity", or neither.

    Karma per contribution decides when the number of contributions is known; only when it isn't do the commenter
    history's "usually upvoted" and then karma per year of account age stand in.
    """
    karma = author.karma
    contributions = _contributions(author, history)
    if karma is not None and karma < 0:
        return Sign("low karma for its activity", f"negative karma ({karma:,})", "red flag")
    if karma is not None and contributions:
        per_contribution = karma / contributions
        if per_contribution < config.LOW_KARMA_PER_CONTRIBUTION:
            return Sign("low karma for its activity", f"{karma:,} karma for {contributions:,} contributions", "red flag")
        if per_contribution >= config.WELL_REGARDED_KARMA_PER_CONTRIBUTION:
            return Sign("well-regarded account", f"{per_contribution:.0f} karma per contribution", "good")
        return None
    if history is not None and history.usually_upvoted:
        return Sign("well-regarded account", "usually upvoted in this topic's communities", "good")
    if karma is not None and age_days:
        per_year = karma / (age_days / 365.25)
        if per_year >= config.WELL_REGARDED_KARMA_PER_YEAR:
            return Sign("well-regarded account", f"about {per_year:,.0f} karma a year", "good")
    return None


def _contributions(author: Author, history: CommenterHistory | None) -> int | None:
    """How many comments and posts the writer has made: from their profile (engine/profiles.py), else the history."""
    if author.contributions is not None:
        return author.contributions
    return history.contributions if history else None


def _is_expert_flair(flair: str | None) -> bool:
    if not flair:
        return False
    text = flair.lower()
    return _has_any(text, EXPERT_FLAIR_WORDS) and not _has_any(text, NOT_EXPERT_FLAIR_WORDS)


# Independence: no sign of paid or fake advice.

# Phrases that sell rather than advise. Each is skipped after "not" or "no" ("not sponsored", "no affiliate link").
SALESY_PHRASES = (
    "use my code", "use code", "my code", "discount code", "promo code", "coupon code", "referral code",
    "referral link", "affiliate link", "affiliate", "link in bio", "link in my bio", "link in my profile",
    "dm me", "pm me", "check out my", "visit my", "my etsy", "my website", "my channel", "my youtube", "my blog",
    "follow me", "subscribe", "sponsored", "#ad", "#sponsored", "#partner", "limited time", "buy now",
    "order now", "shop now", "click here", "while supplies last",
)
# Of those, the ones that show the writer is paid when people buy (Noemi, 9 Oct 2026): they count as two red flags.
PAID_PROMOTION_PHRASES = (
    "use my code", "use code", "my code", "discount code", "promo code", "coupon code", "referral code",
    "referral link", "affiliate link", "affiliate", "sponsored", "#ad", "#sponsored", "#partner",
)
# Parts of a link that pay the writer when someone buys: an Amazon associate tag, affiliate networks.
AFFILIATE_LINK_MARKERS = (
    "tag=", "affiliate", "aff_id=", "affid=", "aff=", "rstyle.me", "shopmy.us", "liketk.it", "skimresources",
    "linksynergy", "shareasale", "awin1.com", "howl.me",
)
# The writer works for, owns or represents a brand: even when honest about it, they aren't independent.
AFFILIATION_PHRASES = (
    "i'm the founder", "i am the founder", "founder of", "co-founder", "cofounder", "i own the company",
    "i work for the company", "i work for the brand", "our products", "our product", "our brand", "our company",
    "our formula", "brand ambassador", "i'm an ambassador", "i'm a rep for", "sales rep",
)
_LINK = re.compile(r"https?://\S+")


def _independence_signs(text: str) -> list[Sign]:
    """Paid promotion, sales talk or working for a brand, in the comment's own words. They depend on the words alone,
    so each comment's are worked out once and remembered (latency, 12 Oct 2026)."""
    key = (text, config.PAID_PROMOTION_RED_FLAGS)
    if key not in _INDEPENDENCE:
        _INDEPENDENCE.keep(key, tuple(_independence_signs_of(text)))
    return list(_INDEPENDENCE[key])


def _independence_signs_of(text: str) -> list[Sign]:
    signs = []
    paid = _first_phrase(text, PAID_PROMOTION_PHRASES)
    pitch = _first_phrase(text, SALESY_PHRASES)
    if paid:
        signs.append(Sign("salesy language", f'paid promotion: "{paid}"', "red flag", config.PAID_PROMOTION_RED_FLAGS))
    elif any(marker in link for link in _LINK.findall(text) for marker in AFFILIATE_LINK_MARKERS):
        signs.append(Sign("salesy language", "an affiliate link: the writer earns from sales", "red flag",
                          config.PAID_PROMOTION_RED_FLAGS))
    elif pitch:
        signs.append(Sign("salesy language", f'sales talk: "{pitch}"', "red flag"))
    if _first_phrase(text, AFFILIATION_PHRASES):
        signs.append(Sign("promotes one brand", "says they work for or represent a brand", "red flag"))
    return signs


# Copied text (Noemi's decision 3, 11 Oct 2026): another writer's comment, word for word. Found in the library: two
# accounts posted the same promotional recommendation in one thread, and each counted as an independent voice.

COPIED_TEXT_REASON = "the same words as another writer's comment in this thread"
# A word, for comparing texts: letters and digits, with any apostrophes inside ("don't"). Punctuation, markdown and
# spaces fall between words, so a copy with a comma more or a word in bold is still a copy.
_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)*")


def copy_groups(thread: Thread) -> list[frozenset[str]]:
    """The comments of `thread` whose own words share a run of at least COPIED_TEXT_MIN_WORDS words in a row with
    another writer's comment there: "copied text", a red flag.

    Both copies are flagged: the same words under two names suggest coordinated promotion, and the order they were
    posted can't show who copied. Never flagged: a writer posting twice, a reply and the comment it answers (replies
    often repeat it), a deleted or removed comment (nor does its text count against others), words quoted from
    someone else (lines starting with ">", as _own_words leaves out) and a comment too short to hold such a run.
    Links don't count as words.

    Worked out once per thread, not comment by comment: every run of that many words is listed with the comments it
    appears in, so a thread of hundreds of comments is read once. Returns the sets of comments that copy one another
    (a comment copied by two others joins them in one set); copied_comment_ids and repeated_copies read them. Since 12
    Oct 2026 (latency) also remembered, by everything of the thread it reads, so the next answer reading the same
    thread doesn't work it out again.
    """
    key = (thread.id, config.COPIED_TEXT_MIN_WORDS,
           tuple((c.id, c.status, c.parent_id, c.author.name if c.author else None, c.body) for c in thread.comments))
    if key not in _COPIES:
        _COPIES.keep(key, tuple(_copy_groups(thread)))
    return list(_COPIES[key])


def _copy_groups(thread: Thread) -> list[frozenset[str]]:
    size = config.COPIED_TEXT_MIN_WORDS
    readable = {c.id: c for c in thread.comments if c.status == "ok"}
    found_in: dict[tuple[str, ...], list[str]] = {}  # each run of `size` words: the comments that have it
    for comment in readable.values():
        words = _WORD.findall(_LINK.sub(" ", _own_words(comment.body)))
        for run in {tuple(words[start:start + size]) for start in range(len(words) - size + 1)}:
            found_in.setdefault(run, []).append(comment.id)
    joined: dict[str, str] = {}  # each copy's set, by one comment standing for it (union-find)

    def root(cid: str) -> str:
        while joined.get(cid, cid) != cid:
            cid = joined[cid]
        return cid

    # The same passage gives many runs with the same comments: each set of comments is compared once.
    for sharing in {tuple(ids) for ids in found_in.values() if len(ids) > 1}:
        for first, second in combinations(sharing, 2):
            if _two_writers_copies(readable[first], readable[second]):
                joined.setdefault(first, first)
                joined.setdefault(second, second)
                joined[root(first)] = root(second)
    groups: dict[str, set[str]] = {}
    for cid in joined:
        groups.setdefault(root(cid), set()).add(cid)
    return [frozenset(group) for group in groups.values()]


def copied_comment_ids(thread: Thread, groups: list[frozenset[str]] | None = None) -> frozenset[str]:
    """The comments of `thread` with the "copied text" red flag: every comment of copy_groups (or of `groups`, when the
    caller has them already)."""
    return frozenset(cid for group in (copy_groups(thread) if groups is None else groups) for cid in group)


def repeated_copies(thread: Thread, groups: list[frozenset[str]] | None = None) -> frozenset[str]:
    """The copies that don't count (Noemi's decision of 11 Oct 2026: copies count once): of each set of comments that
    copy one another (copy_groups, or `groups`), every one but the first posted (on the same second, the lowest id).
    The pipeline leaves their mentions, notes and care tips out; the copy that counts keeps its red flag."""
    by_id = {c.id: c for c in thread.comments}

    def posted(cid: str) -> tuple:
        when = by_id[cid].created_at
        return when is None, when.timestamp() if when is not None else 0.0, cid

    repeats: set[str] = set()
    for group in copy_groups(thread) if groups is None else groups:
        repeats |= group - {min(group, key=posted)}
    return frozenset(repeats)


def _two_writers_copies(a: Comment, b: Comment) -> bool:
    """Whether two comments with the same words are two writers' copies: neither answers the other, and the writers
    aren't the same. Two deleted accounts can't be told apart, so they get the benefit of the doubt, as a writer
    posting twice would; a deleted account and a named one are two accounts."""
    if a.parent_id == b.id or b.parent_id == a.id:
        return False
    if a.author is None or b.author is None:
        return not (a.author is None and b.author is None)
    return a.author.name.casefold() != b.author.name.casefold()


def _copy_signs(comment: Comment, copied: Collection[str]) -> list[Sign]:
    return [Sign("copied text", COPIED_TEXT_REASON, "red flag")] if comment.id in copied else []


# Endorsement: others back it up.

def _endorsement_signs(comment: Comment, thread: Thread, agreements: Iterable[ExtractedAgreement]) -> list[Sign]:
    """Upvotes relative to the rest of the thread (never absolute numbers), and replies that agree."""
    signs = []
    others = [c.score for c in thread.comments if c.status == "ok" and c.id != comment.id]
    if comment.score < config.DOWNVOTED_BELOW:
        signs.append(Sign("downvoted", f"downvoted (score {comment.score})", "red flag"))
    elif others and comment.score >= config.WELL_UPVOTED_MIN_SCORE:
        below = sum(score < comment.score for score in others)
        beaten = below / len(others)
        if beaten >= config.WELL_UPVOTED_SHARE_BEATEN:
            # Rounded down, so it never says "more than 100%" (the demo page did, 10 Oct 2026).
            where = ("the top comment in this thread" if below == len(others)
                     else f"more than {below * 100 // len(others)}% of this thread's comments")
            signs.append(Sign("well upvoted", f"{comment.score} points, {where}", "good"))
    parent_of = {c.id: c.parent_id for c in thread.comments}
    # A reply by the writer themselves isn't someone else backing them up (review fixes, 9 Oct 2026). Only a reply
    # known to be theirs is left out: two deleted accounts can't be told apart.
    writer_of = {c.id: c.author.name.casefold() for c in thread.comments if c.author is not None}
    me = comment.author.name.casefold() if comment.author is not None else None
    agreeing = {
        a.comment_id for a in agreements
        if parent_of.get(a.comment_id) == comment.id and not (me is not None and writer_of.get(a.comment_id) == me)
    }
    if agreeing:
        n = len(agreeing)
        signs.append(Sign("replies agree", f"{n} {'reply agrees' if n == 1 else 'replies agree'}", "good"))
    return signs


@dataclass(frozen=True)
class Upvotes:
    """A comment's upvotes beside its thread's, numbers only: what Noemi's upvote rule reads (14 Oct 2026: "if we have
    few credible mentions, a highly upvoted comment (10+) counts more"; config.UPVOTE_*, the rule in engine/rank.py)."""

    score: int  # the comment's score: upvotes minus downvotes
    thread_comments: int  # the thread's comments readable when it was read, this one included
    share_beaten: float  # the share of those others it scores higher than ("well upvoted" reads the same); 0 with none


def thread_upvotes(thread: Thread) -> dict[str, Upvotes]:
    """{comment id: Upvotes} for every comment of `thread` readable when it was read, worked out once per thread.

    The same comments the "well upvoted" sign compares a comment with (_endorsement_signs): those not deleted or removed
    (so also one whose words the library doesn't keep, by its score). A tie beats no one. A deleted or removed comment
    has no entry: it is never credible, so it never counts twice.
    """
    readable = [c for c in thread.comments if c.status not in ("deleted", "removed")]
    scores = sorted(c.score for c in readable)
    others = len(readable) - 1
    return {c.id: Upvotes(c.score, len(readable), bisect_left(scores, c.score) / others if others else 0.0)
            for c in readable}


# Recency: still true today.

def _recency_signs(comment: Comment, thread: Thread) -> list[Sign]:
    """Recent (within VOICE_RECENT_YEARS of when the thread was saved) is a good sign; older is an old post."""
    years = (thread.collected_at - comment.created_at).days / 365.25
    when = comment.created_at.strftime("%b %Y")
    if years <= config.VOICE_RECENT_YEARS:
        return [Sign("recent", f"written {when}", "good")]
    return [Sign("old post", f"written {when}, over {config.VOICE_RECENT_YEARS} years ago", "note")]


# What the words show about the writer: care for the category, and whether they've used anything at all.

# Specialist words that show care and taste for the category ("enthusiast"). A word counts once however often used.
CATEGORY_TERMS = {
    "skincare": (
        "aha", "bha", "pha", "glycolic", "lactic", "mandelic", "salicylic", "azelaic", "gluconolactone", "retinol",
        "retinal", "retinoid", "retinoids", "tretinoin", "tret", "adapalene", "niacinamide", "ceramide", "ceramides",
        "peptide", "peptides", "panthenol", "centella", "squalane", "ph", "purge", "purging", "patch test",
        "occlusive", "humectant", "emollient", "comedogenic", "comedones", "fungal acne", "malassezia", "sebum",
        "moisture barrier", "skin barrier", "actives", "concentration", "formulation", "uva", "uvb", "filters",
        "tinosorb", "zinc oxide", "white cast", "hyperpigmentation", "pih", "melasma", "slugging", "double cleanse",
    ),
    "kitchen": (
        "gyuto", "santoku", "nakiri", "petty", "sujihiki", "bunka", "kiritsuke", "honesuki", "deba", "yanagiba",
        "usuba", "hrc", "rockwell", "vg10", "vg-10", "aogami", "shirogami", "sg2", "r2", "aus-8", "aus8", "440c",
        "x50crmov15", "carbon steel", "whetstone", "whetstones", "honing", "strop", "bevel", "microbevel", "grit",
        "patina", "full tang", "bolster", "choil", "edge retention", "cladding", "san mai", "damascus",
        "wa handle", "seasoning", "polymerized", "enameled", "tri-ply", "fully clad", "fond", "gooseneck", "burr",
        "burrs", "conical", "grind size", "extraction", "bloom", "heat retention", "descale", "descaling",
        "limescale",
    ),
    # Haircare (11 Oct 2026): the words of people who study their hair and its products.
    "haircare": (
        "sulfate", "sulfates", "sulphate", "sulphates", "sls", "sles", "silicone", "silicones", "cones", "protein",
        "porosity", "humectant", "humectants", "emollient", "emollients", "co-wash", "cowash", "clarify", "clarifying",
        "chelating", "build-up", "buildup", "plopping", "scrunch", "scrunching", "squish to condish", "curly girl",
        "cg method", "ketoconazole", "zinc pyrithione", "selenium sulfide", "piroctone olamine", "seborrheic",
        "malassezia", "film former", "cationic", "behentrimonium", "polyquaternium", "cuticle", "hygral fatigue",
        "heat protectant", "bond builder", "wet line", "cast",
    ),
}


def _care_signs(text: str, category: str) -> list[Sign]:
    """The category's specialist words (an enthusiast) and, when switched on, no sign of use. They depend on the words
    and the category alone, so each comment's are worked out once and remembered (latency, 12 Oct 2026)."""
    key = (text, category, config.ENTHUSIAST_MIN_TERMS, config.VOICE_RED_FLAG_NO_USE, config.LONG_TERM_MIN_MONTHS,
           config.USE_MAX_YEARS)
    if key not in _CARE:
        _CARE.keep(key, tuple(_care_signs_of(text, category)))
    return list(_CARE[key])


def _care_signs_of(text: str, category: str) -> list[Sign]:
    signs = []
    terms = [term for term in CATEGORY_TERMS.get(category, ()) if _has_any(text, (term,))]
    if len(terms) >= config.ENTHUSIAST_MIN_TERMS:
        signs.append(Sign("enthusiast", f"uses the category's specialist words: {', '.join(terms[:4])}", "good"))
    if config.VOICE_RED_FLAG_NO_USE and not _shows_use(text):
        signs.append(Sign("no sign of use", "no sign they've used anything they mention", "red flag"))
    return signs


def _shows_use(text: str) -> bool:
    """Whether any sentence of the comment shows the writer using something (any product, any length of time)."""
    return any(_proof_of_use(sentence, None)[0] != "no first-hand use" for sentence in _sentences(text))


# --- Evidence: once per product mention ---

def score_evidence(comment: Comment, product_name: str, stance: str, other_products: Iterable[str] = ()) -> EvidenceScore:
    """How well the writer of `comment` knows `product_name`, which they mention with `stance`.

    `other_products` are the other products named in the same comment. Their sentences are kept apart, so "had my
    Lodge 10 years; never tried Staub" gives each its own evidence, and they are the alternatives counted when the
    writer compares ("compares 2 alternatives"). It depends on the comment's words and date, the product, the stance
    and the others alone, so each is worked out once and remembered (latency, 12 Oct 2026).
    """
    other_products = tuple(other_products)
    key = (comment.body, comment.created_at, product_name, stance, other_products, config.LONG_TERM_MIN_MONTHS,
           config.USE_MAX_YEARS)
    if key not in _EVIDENCE:
        _EVIDENCE.keep(key, _score_evidence(comment, product_name, stance, other_products))
    return _EVIDENCE[key]


def _score_evidence(comment: Comment, product_name: str, stance: str, other_products: tuple[str, ...]) -> EvidenceScore:
    others = _distinct_others(product_name, other_products)
    context = _product_context(_own_words(comment.body), product_name, others)
    text = " ".join(context)
    level, reasons = _proof_of_use(text, comment.created_at)
    tags = [level] if level != "no first-hand use" else []  # "long-term use" and "short-term use" are tags too
    if reasons == [_SECONDHAND_REASON]:
        tags.append("secondhand")
    honesty = _honesty_tags(_without_name_details(text, product_name))
    tags += honesty
    reasons += honesty
    if others and _compares(context, product_name, others):
        tags.append("compares alternatives")
        reasons.append(f"compares {len(others)} alternative{'s' if len(others) > 1 else ''}")
    if stance == "neutral" and any(sentence.rstrip().endswith("?") for sentence in context):
        tags.append("asks about it")
    if level != "long-term use" and not set(tags) & _CONCRETE_TAGS:
        tags.append("vague")
    shown = reasons[:1] if level == "long-term use" else []
    shown += [reason for reason in reasons if reason in HONESTY_TAGS or reason.startswith("compares ")]
    return EvidenceScore(level, tuple(dict.fromkeys(tags)), tuple(reasons), tuple(shown))


NO_USE = "no first-hand use"
_VERDICT_REASON = "speaks of it from use (no time given)"
_SECONDHAND_TAG = "secondhand"
_AI_NO_USE_REASON = "no use of it in the AI's reading of the whole comment"


def with_ai_evidence(evidence: EvidenceScore, ai_level: str | None, ai_tags: Iterable[str] = ()) -> EvidenceScore:
    """The mention's evidence once the AI's own reading of it is taken in: first-hand use needs both readers to see it.

    From extraction instructions v6 the AI writes an evidence level for every mention, reading the whole comment
    (`ai_level`, with its tags `ai_tags`). When it says "no first-hand use" and these rules found use, the words the
    rules read as use were about something else, so the mention has no first-hand use (13 Oct 2026). A review of the
    answers had found picks backed by writers who only suggested the product: a "my" in a phrase of opinion and "for
    me" read as the writer's own, a "mine" that was the writer's other machine, a time of use that was another product's. On
    Noemi's labels the AI never said "no first-hand use" where she saw use (48 of the gold set's products, and all 29 of
    the held-out kettle thread's).

    One exception, from the labelling guide: a verdict on the product alone ("it's amazing", the rules' "speaks of it
    from use") is short-term use, so it stays use unless the AI says it is someone else's experience ("secondhand").
    Whether a plain verdict should need the AI's agreement too is Noemi's call (see eval/RUNS.md, 13 Oct 2026).

    The AI's reading only ever takes use away: when it sees use the rules don't, the rules' level stands. With no
    level from the AI (an older extraction), the rules decide alone, as before. The honesty tags stay what they are.
    """
    ai_tags = tuple(ai_tags)
    if ai_level != NO_USE or evidence.level == NO_USE:
        return evidence
    if evidence.reasons[:1] == (_VERDICT_REASON,) and _SECONDHAND_TAG not in ai_tags:
        return evidence
    tags = [tag for tag in evidence.tags if tag not in ("long-term use", "short-term use")]
    if _SECONDHAND_TAG in ai_tags and _SECONDHAND_TAG not in tags:
        tags.append(_SECONDHAND_TAG)
    if not set(tags) & _CONCRETE_TAGS and "vague" not in tags:
        tags.append("vague")
    honest = tuple(r for r in evidence.reasons if r in HONESTY_TAGS or r.startswith("compares "))
    return EvidenceScore(NO_USE, tuple(tags), (_AI_NO_USE_REASON,) + honest, honest)


# Words that compare one product with another ("better than", "switched from", "instead of").
_COMPARISON = re.compile(
    r"\b(?:than|vs|versus|compared?|comparison|instead|switched|switch|prefer|preferred|beats?|superior|inferior"
    r"|replaced|replacement|rather|unlike|similar|same as|dupes?|alternatives?|upgraded?|both"
    r"|(?:used|had|tried) (?:\w+ ){0,3}before)\b"
)


def _compares(context: list[str], product_name: str, others: list[str]) -> bool:
    """Whether the writer compares this product with the others they name (the guide: "names what they used before
    or instead"): in comparing words, or by saying they used them side by side ("I've used X, Y and Z"). A plain list
    of suggestions ("Recs: X, Y, Z") is not a comparison."""
    if any(_COMPARISON.search(sentence) for sentence in context):
        return True
    mine, theirs = _name_words(product_name), [_name_words(other) for other in others]
    return any(_FIRST_HAND.search(sentence) and all(_naming(sentence, mine, theirs)) for sentence in context)


# Tags that say something concrete; without any of them, short-term and no first-hand use are "vague".
_CONCRETE_TAGS = {"specific details", "mentions flaws", "compares alternatives", "secondhand", "cheaper alternative",
                  "alternative for another need", "asks about it"}
# The signs of honesty that add to a mention's weight (EVIDENCE_HONESTY_BONUS each).
HONESTY_TAGS = ("mentions flaws", "compares alternatives", "specific details")


def _distinct_others(product_name: str, other_products: Iterable[str]) -> list[str]:
    """The other products, each once, leaving out any that is this product under another name."""
    distinct: list[str] = []
    for other in other_products:
        if not same_product(other, product_name) and not any(same_product(other, kept) for kept in distinct):
            distinct.append(other)
    return distinct


# Proof of use. Each pattern reads lowercase text with straight apostrophes.

_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
    "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "a couple of": 2, "a couple": 2, "couple of": 2, "couple": 2, "a few": 3, "few": 3,
    "several": 3, "many": 5,
}
_MONTHS_PER_UNIT = {"decade": 120, "year": 12, "yr": 12, "month": 1, "mo": 1, "week": 0.25, "wk": 0.25, "day": 1 / 30}
_COUNT = r"(\d+(?:\.\d+)?|" + "|".join(sorted(map(re.escape, _NUMBER_WORDS), key=len, reverse=True)) + r")"
# "2 years", "a few weeks", "10+ yrs", "20-year-old", "6 months"
_DURATION = re.compile(r"\b" + _COUNT + r"\+?[\s-]*(decade|year|yr|month|mo|week|wk|day)s?\b")
# "since 2019", or "bought it in 2019": counted from the end of that year, the shortest it can mean.
_SINCE_YEAR = re.compile(r"\b(?:since|(?:bought|got|purchased)\s+(?:\w+\s+){0,3}in)\s+(?:early\s+|late\s+|mid\s+)?((?:19|20)\d\d)\b")
# Use over a long time, said without a number.
_HELD_UP = re.compile(
    r"\b(?:still (?:going|works|working|kicking|use|using|have|has|in use|sharp|perfect|holding|my go-to|my favou?rite)"
    r"|held up|holds up|holding up|has lasted|years later|to this day|for years|for ages|for decades|decades"
    r"|for a long time|years ago|after all these years|since (?:college|high school|uni|university|childhood|i was))\b"
)
# Days or weeks of use, or a fresh start.
_SHORT_TERM = re.compile(
    r"\b(?:(?:just|recently) (?:bought|got|started|received|picked up|tried|switched|purchased|grabbed)"
    r"|first (?:impressions?|use|week|few (?:days|weeks|uses))|first time (?:using|trying|i used|i tried)"
    r"|so far|started using|only (?:had|used|tried)|trying (?:it|them|this|out))\b"
)
# The writer using, owning or judging something themselves.
_FIRST_HAND = re.compile(
    r"\b(?:(?:i|we)\s+(?:also\s+|still\s+|really\s+|just\s+|personally\s+|now\s+|currently\s+|actually\s+|absolutely\s+)?"
    r"(?:use|used|using|have(?!\s+(?:heard|read|seen|no|never|not|to|been told))|had|own|owned|bought|got|tried"
    r"|love|loved|like|liked|swear by|switched|went with|ended up"
    r"|keep|kept|reach for|replaced|returned|threw|stopped|started|cook|apply|sharpen|sharpened|wash)"
    r"|(?:i|we)'?ve\s+(?:been\s+)?(?:using|used|had|owned|bought|got|gotten|tried|loved|cooked|made|sharpened)"
    r"|i'?m (?:using|loving)|mine|for me|broke me out"
    r"|(?:irritat\w*|broke|breaks|gives|gave|makes|made|leaves|left|helped|helps|saved|saves) (?:me|my)\b"
    r"|my (?!(?:sister|brother|mom|mum|mother|dad|father|parents|friends?|wife|husband|partner|boyfriend|girlfriend"
    r"|roommate|flatmate|coworker|colleague|grandma|grandmother|grandpa|aunt|uncle|cousin|daughter|son|family"
    r"|derm|dermatologist|doctor|advice|opinion|question|guess|recommendation|suggestion|vote|two|2|bad|god"
    r"|budget|understanding)\b)[a-z0-9])"
)
# A verdict on the product, which the guide counts as use with no time given ("it's amazing", "X is very nice").
# Weaker than the cues above: "I've heard X is great" is still hearsay.
_VERDICT = re.compile(
    r"\b(?:(?:it'?s|is|are|they'?re|was|were)\s+(?:so\s+|really\s+|very\s+|super\s+|just\s+|absolutely\s+|honestly\s+)?"
    r"(?:amazing|fantastic|great|awesome|incredible|the best|perfect|excellent|so good|wonderful|nice|lovely"
    r"|satisfying|effective|a workhorse)|holy grail|game ?changer|obsessed|my go-to)\b"
)
# Never used it, or only wanting to. "never used anything else" is not one: it says they stuck with this one.
_UNTRIED = re.compile(
    r"\b(?:(?:never|haven'?t|have not|hasn'?t|didn'?t|not yet)\s+(?:ever\s+)?(?:tried|used|owned|bought)"
    r"(?!\s+(?:anything|any other|another|other|a different|any|something))"
    r"|(?:want|wanting|planning|plan|hoping|thinking of|thinking about|tempted) to (?:try|buy|get|order|pick up)"
    r"|on my (?:wish ?list|list)|wish ?list|eyeing"
    # About to: "I am about to try it", "yet to try", "excited to try", "gonna try it", "can't review it yet" (b05,
    # 10 Oct 2026). "Going to try" only with "it", "them" or "one": "I'm going to try a carbon steel pan next", after
    # years with a skillet, is about the next pan. "Yet to" only before "try" or "test": "yet to get a breakout" is use.
    r"|about to (?:try|test|use|buy|get|order)|(?:yet|excited|eager|keen|can'?t wait|cannot wait) to (?:try|test)"
    r"|(?:going to|gonna) try (?:it|them|this|that|one)|(?:can'?t|cannot) review\b[^.!?]{0,40}?\byet"
    r"|haven'?t (?:had (?:a|the) chance|gotten around|got around|gotten|got) to (?:try|use))\b"
)
# Someone else's experience.
_SECONDHAND = re.compile(
    r"\bmy (?:sister|brother|mom|mum|mother|dad|father|parents|friends?|wife|husband|partner|boyfriend|girlfriend"
    r"|roommate|flatmate|coworker|colleague|grandma|grandmother|grandpa|aunt|uncle|cousin|daughter|son|family)\b"
)
_SECONDHAND_REASON = "someone else's experience"
# Heard or read about it.
_HEARSAY = re.compile(
    r"\b(?:heard|i read|read (?:good|great|that)|people (?:say|swear|rave|love|recommend)|supposedly|apparently"
    r"|reviews (?:say|are)|(?:is|are) supposed to be|said to be|everyone (?:says|loves|raves)|known for|reputation)\b"
)


def _proof_of_use(text: str, written: datetime | None) -> tuple[str, list[str]]:
    """The evidence level that `text` shows, and the reasons for it in words.

    In this order: never used it (or only wants to) -> no first-hand use; heard about it or someone else's
    experience, with no use of their own -> no first-hand use; a year or more, or "still going" -> long-term use;
    days, weeks, a fresh start, any use of their own, or a verdict on it ("it's amazing") -> short-term use;
    anything else (a bare name, "get X") -> no first-hand use.
    """
    if _UNTRIED.search(text):
        return "no first-hand use", ["hasn't tried it"]
    own_use = _FIRST_HAND.search(text)
    if _SECONDHAND.search(text) and not own_use:
        return "no first-hand use", [_SECONDHAND_REASON]
    if _HEARSAY.search(text) and not own_use:
        return "no first-hand use", ["heard about it, not used"]
    months, how_long = _longest_use(text, written)
    if months is not None and months >= config.LONG_TERM_MIN_MONTHS:
        return "long-term use", [how_long]
    if _HELD_UP.search(text):
        return "long-term use", ["used for a long time"]
    if months is not None:
        return "short-term use", [how_long]
    if _SHORT_TERM.search(text):
        return "short-term use", ["just started using it"]
    if own_use:
        return "short-term use", ["uses it (no time given)"]
    if _VERDICT.search(text):
        return "short-term use", [_VERDICT_REASON]
    return "no first-hand use", ["suggests it without saying they used it"]


def _longest_use(text: str, written: datetime | None) -> tuple[float | None, str]:
    """The longest time of use the text gives, in months, with its badge ("2 years of use"); None if it gives none."""
    found: list[tuple[float, str]] = []
    for match in _DURATION.finditer(text):
        if _is_an_age(text, match) or _is_not_a_duration(text, match):
            continue
        count_text, unit = match.group(1), match.group(2)
        count = float(count_text) if count_text[0].isdigit() else _NUMBER_WORDS[count_text]
        if count * _MONTHS_PER_UNIT[unit] > config.USE_MAX_YEARS * 12:
            continue  # a tradition's or a design's age ("a 400 year history"), not anyone's use (11 Oct 2026)
        plural = "s" if count != 1 else ""
        found.append((count * _MONTHS_PER_UNIT[unit], f"{count_text} {_UNIT_NAMES[unit]}{plural} of use"))
    if written is not None:
        for match in _SINCE_YEAR.finditer(text):
            year = int(match.group(1))
            months = max(0, (written.year - year - 1) * 12 + written.month)
            found.append((months, f"since {year}"))
    return max(found) if found else (None, "")


_UNIT_NAMES = {"decade": "decade", "year": "year", "yr": "year", "month": "month", "mo": "month", "week": "week",
               "wk": "week", "day": "day"}


# "can last 100 years", "will all last decades", "built to last 20 years": a claim about how long something can
# last, not how long the writer has used theirs (9 Oct 2026: it gave the badge "100 years of use").
_CLAIMED_LIFE = re.compile(r"\b(?:can|could|will|would|should|may|might|supposed to|built to|made to|designed to)"
                           r"(?:\s+\w+){0,2}\s+last\s+(?:for\s+|up to\s+|over\s+)?$")
# "a 5 year warranty", "2-year limited warranty", "10 years guarantee": what the maker promises, not use (review
# fixes, 9 Oct 2026: it gave the badge "5 years of use"). Read right after the time.
_WARRANTY_AFTER = re.compile(r"^[\s-]*(?:(?:limited|full|extended|manufacturer'?s?|parts|of)\s+)?"
                             r"(?:warrant(?:y|ies)|guarantee)")


# "you could buy one for £20 and keep it for 40 years", "you've put up with it for three years": how long the reader
# could keep it or has had it, not the writer's own use (b08 and b09, 10 Oct 2026, night: they gave the badges "30 years
# of use" and "three years of use"). A "you" with "can", "could", "will", "have", "used"... (not "can't") earlier in
# the same sentence, and no "I", "my" or "we" between it and the time. "Thank you, I had mine 7 years" still counts.
_READERS_TIME = re.compile(r"\byou(?:'ll|'d|'ve| will| would| can| could| should| might| may| have| had| got"
                           r"| put up| stuck| used| owned| kept| been)(?!n't|'t|not)\b"
                           r"(?:(?!\b(?:i|i've|i'd|i'm|my|mine|we|we've|our)\b)[^.!?;])*$")


# "if I get a year out of it", "hopefully it lasts 10 years": a hoped-for time, not the writer's use (b10, 11 Oct 2026:
# a writer two months into a pan had the badge "a year of use"). Read just before the time, in the same sentence.
_HOPED_TIME = re.compile(r"(\bif (i|we|it|they|this|mine) (can |could )?(get|gets|last|lasts|make it|manage|manages)\b"
                         r"|\b(hopefully|hope|hoping|expect|expecting)\b)[^.!?;]{0,30}$")


def _is_not_a_duration(text: str, match: re.Match) -> bool:
    """Whether "a day" or "one day" here is a frequency ("twice a day", "once a week") or a figure of speech
    ("one day it broke"), or the time is how long something can last rather than how long the writer used it,
    how long the reader could keep it, how long the writer hopes it lasts, or how long its warranty is."""
    if _CLAIMED_LIFE.search(text[max(0, match.start() - 60):match.start()]):
        return True
    if _READERS_TIME.search(text[max(0, match.start() - 200):match.start()]):
        return True
    if _HOPED_TIME.search(text[max(0, match.start() - 60):match.start()]):
        return True
    if _WARRANTY_AFTER.search(text[match.end():match.end() + 40]):
        return True
    words_before = text[:match.start()].split()[-1:]
    previous = words_before[0] if words_before else ""
    if previous in ("once", "twice", "times", "per", "x", "every"):
        return True
    return match.group(0) in ("one day", "some day") and previous not in ("for", "after", "within", "in")


# Words for a person, after "N years old": "my 6 year old son", "40 year old guy here" (review fixes, 9 Oct 2026).
_OLD_PERSON_AFTER = re.compile(r"^[\s-]+old[\s-]+(?:sons?|daughters?|kids?|child|children|bab(?:y|ies)|wom[ae]n|m[ae]n"
                               r"|guys?|girls?|boys?|husband|wife)\b")
_OLD_AFTER = re.compile(r"^[\s-]+old\b")


def _is_an_age(text: str, match: re.Match) -> bool:
    """Whether the time found is a person's age, not a time of use: the writer's ("I'm 35 years old"), or anyone's.

    "N years old" is a person's age after "a" ("as a 30 year old", "a 30 year old with oily skin") or before a word
    for a person ("my 6 year old son", "our 3-year-old daughter", "40 year old guy here"). After "my" or "our" with
    no such word, it is the age of the writer's own thing, which is how long they've had it: "My 20 year old Lodge
    skillet" stays a time of use. (Review fixes, 9 Oct 2026: ages and warranties gave badges like "30 years of use".)
    """
    before = text[max(0, match.start() - 8):match.start()]
    if re.search(r"\b(?:i'?m|i am|im|age|aged)\s+$", before):
        return True
    after = text[match.end():match.end() + 30]
    if _OLD_PERSON_AFTER.search(after):
        return True
    return bool(re.search(r"\ba\s+$", before) and _OLD_AFTER.search(after))


# Honesty.

_FLAWS = re.compile(
    r"\b(?:downsides?|drawbacks?|complaints?|cons|gripes?|issues?|problems?|annoying|wish (?:it|they|the)|pricey"
    r"|expensive|overpriced|heavy|flimsy|fragile|finicky|fussy|high maintenance|rust(?:s|ed|y)?|chip(?:s|ped|py)?"
    r"|stain(?:s|ed)?|dull(?:s|ed)?|warp(?:s|ed)?|crack(?:s|ed)?|peel(?:s|ed)|flak(?:e|es|ed|ing)|leak(?:s|ed|y)?"
    r"|scratch(?:es|ed)?|pill(?:s|ing)|sticky|tacky|greasy|drying|dries (?:me |my skin )?out|dried (?:me )?out"
    r"|irritat\w*|sting(?:s|ing)?|burn(?:s|ed|ing)?|broke me out|purg\w*|white cast|smells? (?:bad|weird|awful|off)"
    r"|hard to (?:clean|use|find|sharpen|maintain|open|get)|difficult|tricky|takes? (?:a while|time|forever)|loud"
    r"|noisy|mediocre|meh|learning curve"
    r"|too (?:much|harsh|strong|heavy|thick|thin|small|big|expensive|sticky|greasy|drying|hot|loud|slow|long)"
    r"|not (?:great|perfect|the best|ideal|cheap|worth))\b"
)
_DETAILS = re.compile(
    r"(?:\d+(?:\.\d+)?\s?(?:%|percent\b|mm\b|cm\b|in\b|inch(?:es)?\b|\"|ml\b|oz\b|fl\.? ?oz\b|g\b|grams?\b|kg\b"
    r"|lbs?\b|pounds?\b|qt\b|quarts?\b|l\b|liters?\b|litres?\b|hrc\b|°|degrees?\b|grit\b|watts?\b|w\b|cups?\b)"
    r"|[$£€]\s?\d|\bph\s?\d"
    r"|\b(?:once|twice|\d+\s?x|\d+ times|two times|three times) (?:a|per|every) (?:day|night|week|month|morning)\b"
    r"|\bevery (?:other )?(?:day|night|morning|evening|week)\b|\bsettings?\b|\bon (?:low|medium|high)(?: heat)?\b"
    r"|\b(?:chipped|rusted|cracked|warped|peeled|flaked|leaked|snapped|bent|melted|stopped working|died|broke"
    r"|broken|fell apart|wore out|worn out|discolou?red)\b"
    r"|\b(?:handle|lid|spout|base|button|switch|coating|tip|heel|spine|bolster|tang|finish|texture|scent"
    r"|consistency|bottle|pump|packaging|cap|filter|carafe|element)\b)"
)
_CHEAPER = re.compile(
    r"\b(?:cheaper|budget|affordable|inexpensive|less expensive|dupes?|for less|half the price"
    r"|fraction of the (?:price|cost)|drugstore|bang for (?:the|your) buck)\b"
)
_OTHER_NEED = re.compile(
    r"\bif (?:you(?:'re| are)?|your) (?:have|want|need|prefer|like|don'?t|do|skin|budget|are|looking for)\b"
)


def _without_name_details(text: str, product_name: str) -> str:
    """The text with the sizes and strengths of the product's own name taken out ("5%" in "Mandelic acid 5%"):
    they are its name, not a detail the writer adds."""
    name = html.unescape(product_name).replace("’", "'").lower()
    for detail in {match.group(0) for match in _DETAILS.finditer(name)}:
        text = text.replace(detail, " ")
    return text


def _honesty_tags(text: str) -> list[str]:
    """Mentions flaws, specific details, cheaper alternative, alternative for another need: what `text` shows."""
    tags = []
    if _found(_FLAWS, text):
        tags.append("mentions flaws")
    if _DETAILS.search(text):
        tags.append("specific details")
    if _CHEAPER.search(text):
        tags.append("cheaper alternative")
    if _OTHER_NEED.search(text):
        tags.append("alternative for another need")
    return tags


# --- Which sentences talk about which product ---

# Words in product names that name a kind of product rather than this one, so they can't tell products apart.
GENERIC_NAME_WORDS = frozenset({
    "knife", "knives", "chef", "chefs", "kitchen", "set", "block", "pan", "pans", "skillet", "skillets", "pot", "pots",
    "kettle", "kettles", "electric", "cast", "iron", "steel", "stainless", "carbon", "nonstick", "non", "stick",
    "dutch", "oven", "cookware", "grinder", "coffee", "machine", "maker", "espresso", "burr", "blade", "board",
    "cutting", "sharpener", "whetstone", "stone", "inch", "santoku", "gyuto", "paring", "bread", "utility", "petty",
    "fillet", "nakiri", "cleaver", "wok", "saucepan", "frying", "fry", "sheet", "mixer", "blender", "toaster",
    "scale", "tea", "gooseneck", "glass", "ceramic", "enameled", "classic", "original", "pro", "series", "edition",
    "model", "new", "old", "black", "white", "large", "small", "mini", "plus",
    "cleanser", "cleansers", "toner", "toners", "serum", "serums", "cream", "creams", "moisturizer", "moisturiser",
    "moisturizing", "moisturising", "lotion", "gel", "sunscreen", "spf", "oil", "balm", "mask", "pads", "pad",
    "exfoliant", "exfoliating", "exfoliator", "peel", "peeling", "solution", "acid", "acids", "aha", "bha", "pha",
    "glycolic", "lactic", "salicylic", "mandelic", "azelaic", "retinol", "niacinamide", "hydrating", "gentle",
    "foaming", "facial", "face", "daily", "body", "skin", "care", "eye", "lip", "night", "day", "water", "essence",
    "mist", "wash", "liquid", "toning", "clarifying", "renewing", "calming", "soothing", "barrier", "repair",
    # Haircare and the open model's kitchen types (11 Oct 2026).
    "shampoo", "shampoos", "conditioner", "conditioners", "conditioning", "hair", "scalp", "leave", "deep", "dry",
    "curl", "curls", "curly", "wavy", "dandruff", "anti", "clean", "purple", "silver", "blonde", "colour", "color",
    "volume", "volumizing", "volumising", "thickening", "strengthening", "smoothing", "smooth", "frizz", "shine",
    "treatment", "spray", "mousse", "masque", "styling", "bond", "keratin", "protein", "sulfate", "sulphate", "free",
    "argan", "air", "fryer", "fryers", "rice", "cooker", "cookers", "slow", "pressure", "processor", "food", "stand",
    "hand", "immersion", "basket",
})


# Small words that join the words of a name ("lactic acid 10% with hyaluronic acid"), so they name nothing.
_NAME_JOINING_WORDS = frozenset({"with", "and", "for", "of", "in", "on", "to", "or", "not", "only", "version"})


def _product_context(text: str, product_name: str, others: list[str]) -> list[str]:
    """The sentences of a comment that talk about one product.

    A comment that names only this product talks about it throughout. When it names others too, this product gets
    the sentences that name it, plus the ones right after (they go on about it), until a sentence names another
    product. When it isn't named at all (a reply about the product above, "had this one 13 years"), it gets every
    sentence that doesn't name another product.
    """
    sentences = _sentences(text)
    mine = _name_words(product_name)
    theirs = [_name_words(other) for other in others]
    naming = [_naming(sentence, mine, theirs) for sentence in sentences]
    names_mine = [is_mine for is_mine, _ in naming]
    names_other = [is_other for _, is_other in naming]
    if not any(names_mine):
        return [s for s, other in zip(sentences, names_other) if not other] or sentences
    if not any(names_other):
        return sentences
    context, following = [], False
    for sentence, is_mine, is_other in zip(sentences, names_mine, names_other):
        if is_mine:
            context.append(sentence)
            following = True
        elif is_other:
            following = False
        elif following:
            context.append(sentence)
    return context


def _name_words(product_name: str) -> set[str]:
    """The words of a product name that can pick it out in a sentence: no generic words, no bare numbers."""
    words = set()
    for word in normalize_name(product_name):
        has_letters = any(ch.isalpha() for ch in word)
        long_enough = len(word) >= 3 or (has_letters and any(ch.isdigit() for ch in word))
        if has_letters and long_enough and word not in GENERIC_NAME_WORDS | _NAME_JOINING_WORDS:
            words.add(word)
    return words


def _naming(sentence: str, mine: set[str], theirs: list[set[str]]) -> tuple[bool, bool]:
    """Whether a sentence names this product, and whether it names another one.

    A product is named when some of its name words appear. But when another product's words found there include
    all of its own and more, the sentence is about that other, more specific product: in "I like the Ordinary weekly
    peeling solution", "Ordinary" alone doesn't make it about the Ordinary's glycolic toner.
    """
    words = normalize_name(sentence)
    found = [_found_name_words(words, name_words) for name_words in [mine] + theirs]
    named = [bool(f) and not any(f < other for other in found) for f in found]
    return named[0], any(named[1:])


def _found_name_words(words: list[str], name_words: set[str]) -> frozenset[str]:
    """The name words that appear among `words`, give or take a plural "s" or a one-letter typo."""
    return frozenset(name_word for name_word in name_words if any(_same_word(word, name_word) for word in words))


def _same_word(word: str, name_word: str) -> bool:
    """The same word, give or take a plural "s", or a one-letter slip of a long name word. A common product word is
    never a slip: "cleanser" is a word of its own, not "Gleanser" misspelt (b05, 10 Oct 2026)."""
    if word == name_word or word in (name_word + "s", name_word.removesuffix("s")):
        return True
    return len(name_word) >= 5 and word not in GENERIC_NAME_WORDS and one_edit_apart(word, name_word)


# --- Small text helpers ---

def _own_words(body: str) -> str:
    """The comment in lowercase with HTML codes and curly apostrophes undone, without quoted blocks.

    Lines starting with ">" quote someone else, so they don't count, unless the whole comment is written that way
    (then it is the writer's own formatting, as in the labelling guide).
    """
    text = html.unescape(body).replace("’", "'").replace("‘", "'").lower()
    lines = [line for line in text.splitlines() if line.strip()]
    own = [line for line in lines if not line.lstrip().startswith(">")]
    return "\n".join(own if own else [line.lstrip().lstrip(">") for line in lines])


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")


def _sentences(text: str) -> list[str]:
    """The sentences of a text. A link on its own line joins the sentence before it ("I ended up getting this:")."""
    sentences: list[str] = []
    for piece in _SENTENCE_END.split(text):
        piece = piece.strip()
        if sentences and _LINK.fullmatch(piece):
            sentences[-1] += " " + piece
        elif piece:
            sentences.append(piece)
    return sentences


@cache
def _phrase_pattern(phrase: str) -> re.Pattern:
    """The pattern finding a phrase as whole words, made once per phrase (latency, 12 Oct 2026: hundreds of phrases
    were compiled again for every comment, more than Python's own cache of patterns holds)."""
    return re.compile(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)")


def _has_any(text: str, phrases: Iterable[str]) -> bool:
    return any(_phrase_pattern(phrase).search(text) for phrase in phrases)


_NEGATION = re.compile(r"\b(?:no|not|never|without|zero|any|nor|hardly|(?:does|do|did|is|was|has|have|wo|ca)n'?t|dont|doesnt|wont)\b")


def _negated(text: str, start: int) -> bool:
    """Whether the three words before position `start` hold a negation ("no issues", "doesn't rust", "not sponsored")."""
    before = text[:start].split()[-3:]
    return bool(_NEGATION.search(" ".join(before)))


def _found(pattern: re.Pattern, text: str) -> bool:
    """Whether `pattern` matches somewhere in `text` without a negation just before it."""
    return any(not _negated(text, match.start()) for match in pattern.finditer(text))


def _first_phrase(text: str, phrases: Iterable[str]) -> str | None:
    """The first of `phrases` found in `text` without a negation just before it, or None."""
    for phrase in phrases:
        if _found(_phrase_pattern(phrase), text):
            return phrase
    return None


# --- What a mention weighs, and what the answer shows ---

def badges(voice: VoiceScore, evidence: EvidenceScore) -> tuple[str, ...]:
    """The "why this voice counts" badges for one mention: the writer's good signs, then what shows they know the
    product ("3 years of use", "mentions flaws", "compares 4 alternatives"). Nothing against them is shown here."""
    return voice.badges + evidence.badges


def evidence_value(evidence: EvidenceScore) -> float:
    """The evidence level's value, plus EVIDENCE_HONESTY_BONUS for each sign of honesty (HONESTY_TAGS)."""
    honesty = sum(tag in HONESTY_TAGS for tag in evidence.tags)
    return config.EVIDENCE_VALUE[evidence.level] * (1 + config.EVIDENCE_HONESTY_BONUS * honesty)


def mention_weight(voice: VoiceScore, evidence: EvidenceScore, stance: str) -> float:
    """How much one mention counts towards its product's score: voice value x evidence value x stance value.

    Positive for a recommendation, negative for a warning, zero for a neutral mention.
    """
    return config.VOICE_VALUE[voice.level] * evidence_value(evidence) * config.STANCE_VALUE[stance]
