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
    # Added 8 Oct 2026 from Noemi's "other" notes on her first labelled thread.
    "well-regarded account",  # high karma for its number of contributions
    "low karma for its activity",  # under about 1 karma per contribution: a red flag
    "enthusiast",  # shows care and taste for the category
)
EVIDENCE_TAGS = (
    "long-term use",
    "specific details",
    "mentions flaws",
    "compares alternatives",
    "short-term use",
    "secondhand",
    "vague",
    # Added 8 Oct 2026 from Noemi's "other" notes on her first labelled thread.
    "cheaper alternative",
    "alternative for another need",
    "asks about it",  # a clarifying question ("is that the one you mean?")
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

# How the library is built (Noemi, 7 Oct 2026). Per product type: a mix of thread kinds, each feeding a different
# step (advice -> the picks, long-term use -> evidence strength, warnings -> the skip-these list and downsides).
LIBRARY_THREADS_PER_PRODUCT = 6
LIBRARY_MIX = {"advice": 3, "long_term": 1, "warning": 2}
MAX_THREADS_PER_SUBREDDIT = 2  # per product type, so no single community's taste dominates
SKINCARE_RECENT_YEARS = 3  # skincare formulas change, so newer threads are preferred; kitchen threads can be any age
# Reddit locks threads after about 6 months; only deletions can still change them, so they are refreshed less often.
# Provisional (Noemi, 7 Oct 2026): holds only until the data source / API choice is settled.
REDDIT_ARCHIVE_DAYS = 180
LIBRARY_ARCHIVED_REFRESH_DAYS = 90

# Module 3: a supporting quote is short (Reddit's rule: quotes stay short, attributed and linked back).
QUOTE_MAX_WORDS = 50
# Extraction reads at most this many comments per thread, the highest-scored (8 Oct 2026): the long tail of a
# 400-comment thread adds little, and highly upvoted comments carry the community's endorsement.
EXTRACT_MAX_COMMENTS = 150

# --- Modules 6–7: ranking and answers (proposed 9 Oct 2026, awaiting Noemi) ---
# Values marked "brief" come from docs/brief.md; the others are PROPOSED and wait for Noemi's decision.

# A credible mention (PROPOSED): a recommend or warn from a voice that isn't low, by someone who has used the
# product (long-term or short-term). Neutral mentions are never credible: they don't take a side.
CREDIBLE_VOICES = ("high", "medium")
CREDIBLE_EVIDENCE = ("long-term use", "short-term use")
# The minimum-evidence rule (brief): a product is shown only with this many credible recommendations, coming
# from at least this many different threads.
MIN_CREDIBLE_MENTIONS = 3
MIN_THREADS = 2
PICKS_SHOWN = 3  # brief: the top 3
# The skip-these list (brief: at least 2 credible warnings). PROPOSED: it also needs more credible warnings than
# credible recommendations, so a product praised as much as it is warned against is never on it.
SKIP_MIN_CREDIBLE_WARNINGS = 2
# The disagreement flag (PROPOSED): praised by at least one credible voice and warned against by at least this many.
DISAGREEMENT_MIN_CREDIBLE_WARNINGS = 2
# Kind support (Noemi, 8–9 Oct 2026; values PROPOSED). A kind's support is the sum of the weights of its credible
# notes. A kind leads when it has at least KIND_MIN_CREDIBLE_NOTES credible recommending notes and at least
# KIND_LEAD_RATIO times the support of the next kind ("far more"). Its products get KIND_BONUS points, on the
# same scale as a mention's weight: 1.0 is about one high voice with long-term use; a very large value
# (such as 1000) would always put the leading kind's products first.
KIND_MIN_CREDIBLE_NOTES = 2
KIND_LEAD_RATIO = 2.0
KIND_BONUS = 1.0
# The answer (brief: two or three quotes per pick, every card at least 2 verified quotes). PROPOSED: up to 2
# downsides per pick, 2 quotes per skipped product, 3 "what to look for" notes.
QUOTES_PER_PICK = 3
MIN_QUOTES_PER_PICK = 2
DOWNSIDES_PER_PICK = 2
QUOTES_PER_SKIPPED_PRODUCT = 2
LOOK_FOR_NOTES = 3

# --- Module 5: credibility scoring (proposed 9 Oct 2026, awaiting Noemi) ---
# Every value marked PROPOSED is a starting point for Noemi to accept or change; none is decided yet. Values taken
# from the labelling guide (data/gold/LABELLING_GUIDE.md) say so. The rules that use them are in engine/credibility.py.

# A mention's weight = voice value x evidence value x stance value (STANCE_VALUE above).
# PROPOSED: each step down halves the weight, so a high voice counts 4 times a low one, and long-term use 4 times
# no first-hand use. Low stays above zero: a genuine expert on a new account still counts a little.
VOICE_VALUE: dict[str, float] = {"high": 1.0, "medium": 0.5, "low": 0.25}
EVIDENCE_VALUE: dict[str, float] = {"long-term use": 1.0, "short-term use": 0.5, "no first-hand use": 0.25}
# PROPOSED: each sign of honesty (mentions flaws, compares alternatives, specific details) adds this share to the
# evidence value. Three signs add 30%: never enough to beat the next evidence level, which is worth twice as much.
EVIDENCE_HONESTY_BONUS = 0.1

# Voice levels (the guide): high = good signs worth at least this much and no red flag; low = any red flag.
VOICE_HIGH_MIN_GOOD_SIGNS = 2  # from the guide: "at least two good signs"
# How much each good sign counts towards high. PROPOSED: all equal, as the brief says weights start equal.
# "replies agree" has no tag of its own yet (it is recorded as "other"); a tag for it is proposed to Noemi.
VOICE_SIGN_WEIGHTS: dict[str, float] = {
    "established member": 1,
    "well-regarded account": 1,
    "expert flair": 1,
    "well upvoted": 1,
    "replies agree": 1,
    "recent": 1,
    "enthusiast": 1,
}

# PROPOSED: off. The guide lists "no sign they've used anything" as a red flag (low voice), but in Noemi's first 33
# labels it never made a voice low (the rule fired on 16 comments she rated 4 high, 12 medium), and the evidence layer
# already scores it ("no first-hand use"), so counting it twice would punish the same thing twice. True turns it on.
VOICE_RED_FLAG_NO_USE = False

# Community standing, measured on the day the comment was written.
NEW_ACCOUNT_DAYS = 30  # PROPOSED: an account younger than this is "new account", a red flag
ESTABLISHED_ACCOUNT_YEARS = 2  # PROPOSED: "established member" needs an account at least this old...
ESTABLISHED_MIN_KARMA = 1000  # PROPOSED: ...and this much karma as a sign of activity, until the commenter history exists
LOW_KARMA_PER_CONTRIBUTION = 1.0  # from the guide: under about 1 karma per contribution is a red flag
WELL_REGARDED_KARMA_PER_CONTRIBUTION = 5.0  # PROPOSED: "plenty of karma per contribution"
WELL_REGARDED_KARMA_PER_YEAR = 2000  # PROPOSED: stands in for the line above until contributions are known

# Endorsement: upvotes relative to the thread, never absolute numbers.
WELL_UPVOTED_SHARE_BEATEN = 0.75  # PROPOSED: "well upvoted" scores higher than at least 75% of the thread's other comments...
WELL_UPVOTED_MIN_SCORE = 3  # PROPOSED: ...with at least this score, so the top of a tiny, quiet thread doesn't count
DOWNVOTED_BELOW = 0  # PROPOSED: a score under this (more downvotes than upvotes) is a red flag

# Recency (the guide: "recent" = the last 2-3 years).
VOICE_RECENT_YEARS = 3  # PROPOSED: a comment written within this many years of collection is "recent"; older is "old post"
OLD_SKINCARE_POST_MAX_VOICE = "medium"  # PROPOSED: formulas change, so an old skincare comment can't be high

# The comment's words.
ENTHUSIAST_MIN_TERMS = 3  # PROPOSED: using this many of the category's specialist words shows an "enthusiast"
LONG_TERM_MIN_MONTHS = 12  # from the guide: long-term use is a year or more

# --- Commenter profiles (proposed 9 Oct 2026) ---
# engine/profiles.py looks up each writer's numbers on Arctic Shift, one call per writer, 10 seconds apart.
# PROPOSED: this many failed look-ups in a row means the trouble is Arctic Shift itself (down or busy), not one
# writer, so it stops asking and leaves the remaining writers as they were, instead of waiting on every one of them.
PROFILE_FAILURES_IN_A_ROW_TO_STOP = 3
