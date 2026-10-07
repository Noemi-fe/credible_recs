"""Product decisions that shape the data, all in one place (docs/brief.md, version 4).

Every value here is Noemi's decision. Changing one is a deliberate product change, never a way to make
a label or a test pass: ask Noemi first. After a change, run `python -m engine.gold`; any existing label
that no longer fits is reported with its file and line.
"""

# Categories the engine ranks. A product mention can also be "other" (outside both categories).
THREAD_CATEGORIES = ("skincare", "kitchen")
MENTION_CATEGORIES = THREAD_CATEGORIES + ("other",)

SUBREDDITS: dict[str, tuple[str, ...]] = {
    "skincare": ("SkincareAddiction", "AsianBeauty", "30PlusSkinCare", "SkincareAddictionUK"),
    "kitchen": ("BuyItForLife", "AskCulinary", "chefknives", "Cooking", "castiron", "Coffee", "espresso", "tea"),
}

STANCE_VALUE: dict[str, int] = {"recommend": 1, "warn": -1, "neutral": 0}

# Two-layer credibility: a voice label per comment, an evidence label per product mention.
VOICE_LEVELS = ("high", "medium", "low")
EVIDENCE_LEVELS = ("long-term use", "short-term use", "no first-hand use")

# Reason tags. Every label needs at least one tag from its own list.
VOICE_TAGS = (
    "established member",
    "expert flair",
    "well upvoted",
    "recent",
    "new account",
    "salesy language",
    "promotes one brand",
    "old post",
)
EVIDENCE_TAGS = (
    "long-term use",
    "specific details",
    "mentions flaws",
    "compares alternatives",
    "short-term use",
    "secondhand",
    "vague",
)

# For a reason no tag fits. It needs a note; recurring notes become new tags at the Sunday review.
OTHER_TAG = "other"
# More than this share of labels using "other" means the tag list needs work.
OTHER_TAG_LIMIT = 0.10

# Parse reddit.com API (parse.bot): a third-party scraping service Noemi chose on 7 Oct 2026, after
# Reddit refused official API access. These are the free plan's limits.
PARSE_MONTHLY_CREDITS = 200
PARSE_CREDITS_PER_CALL = 2
PARSE_CALLS_PER_MINUTE = 5

# The deletion rule: nothing fetched from Reddit is kept in the cache longer than this.
CACHE_MAX_AGE_HOURS = 48

# The library: saved threads that answers are prepared from (Noemi, 7 Oct 2026). It is refreshed this often,
# and each refresh drops comments deleted or removed on Reddit since the last one.
LIBRARY_REFRESH_DAYS = 30
