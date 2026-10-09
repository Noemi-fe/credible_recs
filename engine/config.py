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
    # Added 9 Oct 2026 (Noemi's decision 13): signs module 5 already found, recorded as "other" until then.
    "replies agree",  # replies to the comment agree with it: a good sign
    "downvoted",  # more downvotes than upvotes: a red flag
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

# --- Modules 6–7: ranking and answers (proposed 9 Oct 2026; the ranking rules decided by Noemi, 9 Oct 2026) ---
# Values marked "brief" come from docs/brief.md; "decided" ones were approved by Noemi on 9 Oct 2026 as proposed
# (decisions 4 to 8); the ones still marked PROPOSED wait for her decision.

# A credible mention (decided by Noemi, 9 Oct 2026): a recommend or warn from a voice that isn't low, by someone who
# has used the product (long-term or short-term). Neutral mentions are never credible: they don't take a side.
CREDIBLE_VOICES = ("high", "medium")
CREDIBLE_EVIDENCE = ("long-term use", "short-term use")
# The minimum-evidence rule (brief; decided by Noemi, 9 Oct 2026): a product is shown only with this many credible
# recommendations, coming from at least this many different threads, and a score above zero (engine/rank.py).
MIN_CREDIBLE_MENTIONS = 3
MIN_THREADS = 2
PICKS_SHOWN = 3  # brief: the top 3
# The skip-these list (brief: at least 2 credible warnings). Decided by Noemi, 9 Oct 2026: it also needs more credible
# warnings than credible recommendations, so a product praised as much as it is warned against is never on it.
SKIP_MIN_CREDIBLE_WARNINGS = 2
# The disagreement flag (decided by Noemi, 9 Oct 2026): praised by at least one credible voice and warned against by
# at least this many.
DISAGREEMENT_MIN_CREDIBLE_WARNINGS = 2
# Kind support (Noemi, 8–9 Oct 2026). A kind's support is the sum of the weights of its credible notes. A kind leads
# when it has at least KIND_MIN_CREDIBLE_NOTES credible recommending notes and at least KIND_LEAD_RATIO times the
# support of the next kind ("far more"). Its products get KIND_BONUS points, on the same scale as a mention's
# weight: 1.0 is about one high voice with long-term use; a very large value (such as 1000) would always put the
# leading kind's products first.
KIND_MIN_CREDIBLE_NOTES = 2  # PROPOSED: decision 8 named the bonus and the lead ratio, not this
KIND_LEAD_RATIO = 2.0  # decided by Noemi, 9 Oct 2026
KIND_BONUS = 1.0  # decided by Noemi, 9 Oct 2026
# The answer (brief: two or three quotes per pick, every card at least 2 verified quotes). PROPOSED: up to 2
# downsides per pick, 2 quotes per skipped product, 3 "what to look for" notes.
QUOTES_PER_PICK = 3
MIN_QUOTES_PER_PICK = 2
DOWNSIDES_PER_PICK = 2
QUOTES_PER_SKIPPED_PRODUCT = 2
LOOK_FOR_NOTES = 3

# --- Module 5: credibility scoring (proposed 9 Oct 2026; decided by Noemi, 9 Oct 2026) ---
# Noemi approved these values as proposed on 9 Oct 2026 (decisions 4 to 8), except the one still marked PROPOSED.
# Values taken from the labelling guide (data/gold/LABELLING_GUIDE.md) say so. The rules that use them are in
# engine/credibility.py.

# A mention's weight = voice value x evidence value x stance value (STANCE_VALUE above).
# Decided by Noemi, 9 Oct 2026: each step down halves the weight, so a high voice counts 4 times a low one, and
# long-term use 4 times no first-hand use. Low stays above zero: a genuine expert on a new account still counts a
# little.
VOICE_VALUE: dict[str, float] = {"high": 1.0, "medium": 0.5, "low": 0.25}
EVIDENCE_VALUE: dict[str, float] = {"long-term use": 1.0, "short-term use": 0.5, "no first-hand use": 0.25}
# Decided by Noemi, 9 Oct 2026: each sign of honesty (mentions flaws, compares alternatives, specific details) adds
# this share to the evidence value. Three signs add 30%: never enough to beat the next evidence level, which is worth
# twice as much.
EVIDENCE_HONESTY_BONUS = 0.1

# Voice levels (the guide, confirmed by Noemi on 9 Oct 2026): high = good signs worth at least this much and no red
# flag; low = any red flag.
VOICE_HIGH_MIN_GOOD_SIGNS = 2  # from the guide: "at least two good signs"
# How much each good sign counts towards high. Decided by Noemi, 9 Oct 2026: all equal, as the brief says weights
# start equal. "replies agree" has had a tag of its own since 9 Oct 2026 (VOICE_TAGS above).
VOICE_SIGN_WEIGHTS: dict[str, float] = {
    "established member": 1,
    "well-regarded account": 1,
    "expert flair": 1,
    "well upvoted": 1,
    "replies agree": 1,
    "recent": 1,
    "enthusiast": 1,
}

# PROPOSED: off (still open: decisions 4 to 8 covered the values and thresholds, not this switch). The guide lists
# "no sign they've used anything" as a red flag (low voice), but in Noemi's first 33 labels it never made a voice low
# (the rule fired on 16 comments she rated 4 high, 12 medium), and the evidence layer already scores it ("no
# first-hand use"), so counting it twice would punish the same thing twice. True turns it on.
VOICE_RED_FLAG_NO_USE = False

# Community standing, measured on the day the comment was written. All decided by Noemi, 9 Oct 2026.
NEW_ACCOUNT_DAYS = 30  # an account younger than this is "new account", a red flag
ESTABLISHED_ACCOUNT_YEARS = 2  # "established member" needs an account at least this old...
ESTABLISHED_MIN_KARMA = 1000  # ...and this much karma as a sign of activity, until the commenter history exists
LOW_KARMA_PER_CONTRIBUTION = 1.0  # from the guide: under about 1 karma per contribution is a red flag
WELL_REGARDED_KARMA_PER_CONTRIBUTION = 5.0  # "plenty of karma per contribution"
WELL_REGARDED_KARMA_PER_YEAR = 2000  # stands in for the line above until contributions are known

# Endorsement: upvotes relative to the thread, never absolute numbers. Decided by Noemi, 9 Oct 2026.
WELL_UPVOTED_SHARE_BEATEN = 0.75  # "well upvoted" scores higher than at least 75% of the thread's other comments...
WELL_UPVOTED_MIN_SCORE = 3  # ...with at least this score, so the top of a tiny, quiet thread doesn't count
DOWNVOTED_BELOW = 0  # a score under this (more downvotes than upvotes) is "downvoted", a red flag

# Recency (the guide: "recent" = the last 2-3 years). Decided by Noemi, 9 Oct 2026.
VOICE_RECENT_YEARS = 3  # a comment written within this many years of collection is "recent"; older is "old post"
OLD_SKINCARE_POST_MAX_VOICE = "medium"  # formulas change, so an old skincare comment can't be high

# The comment's words. Decided by Noemi, 9 Oct 2026.
ENTHUSIAST_MIN_TERMS = 3  # using this many of the category's specialist words shows an "enthusiast"
LONG_TERM_MIN_MONTHS = 12  # from the guide: long-term use is a year or more

# --- Module 4: product matching (proposed 9 Oct 2026) ---
# Approved by Noemi, 9 Oct 2026 (decision 12): words that name another model or another version of a product. A name
# found inside a longer one is the same product, unless the longer name adds one of these words: "Timemore C2" and
# "Timemore C2 Max" are two grinders, "Dynasty Cream" and "new Dynasty Cream" two formulas.
PRODUCT_VARIANT_WORDS = frozenset({
    "pro", "max", "plus", "mini", "lite", "slim", "go",  # models
    "new", "newest", "old", "modern", "vintage", "antique",  # versions: a new formula, an old casting
})
# The brief's target for module 4: at least this share of the labelled same-or-different pairs right.
MATCHING_TARGET = 0.90

# --- The end-to-end slice (engine/pipeline.py; proposed 9 Oct 2026, awaiting Noemi) ---
# How many of the library's most relevant threads one request reads, counting only threads about the product (the
# title or post names it) that the AI has already read; a relevance score no longer decides (review fixes, 9 Oct).
PIPELINE_MAX_THREADS = 8
# Brand-only picks (decided by Noemi, 9 Oct 2026, decision 9): a brand or line that fits several products ("Lodge",
# "CeraVe") is ranked, under a name that says so ("Lodge (their cast iron skillets)"), when its threads make the
# product clear (BRAND_PICK_TITLE_SHARE below); otherwise it is left out, and listed on the result. False leaves
# every brand or line name out, as before 9 Oct 2026.
PIPELINE_BRAND_PICKS = True

# --- Commenter profiles (proposed 9 Oct 2026) ---
# engine/profiles.py looks up each writer's numbers on Arctic Shift, one call per writer, 10 seconds apart.
# PROPOSED: this many failed look-ups in a row means the trouble is Arctic Shift itself (down or busy), not one
# writer, so it stops asking and leaves the remaining writers as they were, instead of waiting on every one of them.
PROFILE_FAILURES_IN_A_ROW_TO_STOP = 3

# --- Module 8: local demo (proposed 9 Oct 2026) ---
# The search page and its JSON API (engine/web.py), served on this machine only. PROPOSED, for Noemi to approve.
WEB_PORT = 8765  # the local address is http://127.0.0.1:8765/; `python -m engine.web --port N` picks another
WEB_MAX_REQUEST_CHARS = 300  # a longer request is refused (400): a real need fits in far fewer words

# --- Decisions of 9 Oct 2026 ---
# Noemi approved 13 recommendations on 9 Oct 2026 (CLAUDE.md, "Decisions of 9 Oct 2026"). What she decided says so;
# the details and wording Claude chose to carry them out are PROPOSED.

# Decision 9, brand-only picks (engine/pipeline.py). A brand or line name's threads make the product clear when none
# of its names says another type of product, and more than this share of its mentions are in threads whose title
# names the requested product. PROPOSED: more than half.
BRAND_PICK_TITLE_SHARE = 0.5
# PROPOSED (added after checking the library, 9 Oct 2026): also, at least one of the brand's own products named in these
# threads must be of the requested type ("Griswold skillet" for "Griswold"). Without it, All-Clad, discussed in cast
# iron threads for its stainless and non-stick pans only, was ranked as "All-Clad (their cast iron skillets)".
# False drops this condition.
BRAND_PICK_NEEDS_A_PRODUCT_OF_THE_TYPE = True
# The name such a pick is shown under. PROPOSED wording: "Lodge (their cast iron skillets)".
BRAND_PICK_NAME = "{brand} (their {products})"
# The plural of each product type (engine/query.py, PRODUCT_TYPES), for the name above.
PRODUCT_TYPE_PLURALS: dict[str, str] = {
    "exfoliant": "exfoliants",
    "cleanser": "cleansers",
    "moisturiser": "moisturisers",
    "sunscreen": "sunscreens",
    "retinoid": "retinoids",
    "serum": "serums",
    "toner": "toners",
    "eye cream": "eye creams",
    "lip balm": "lip balms",
    "stovetop kettle": "stovetop kettles",
    "electric kettle": "electric kettles",
    "chef knife": "chef knives",
    "cast iron skillet": "cast iron skillets",
    "frying pan": "frying pans",
    "saucepan": "saucepans",
    "dutch oven": "Dutch ovens",
    "espresso machine": "espresso machines",
    "coffee grinder": "coffee grinders",
    "teapot": "teapots",
}

# Decision 11, budgets (engine/prices.py). Current prices live in data/prices.json, each with its shop and the day
# Claude looked it up. PROPOSED: a price checked more than this many days ago is still shown, with its date, but
# never used to leave a product out of a budget request: it may have changed since.
PRICE_MAX_AGE_DAYS = 30

# Decision 12, names shown to a UK audience (decided by Noemi, 9 Oct 2026): {brand word: the word shown}. Sage is
# Breville's UK and EU brand; the alias list (engine/data/product_aliases.json) already treats the two as one product,
# and the answer shows the UK name. Quotes are never changed: a quote that says "Breville" keeps it.
UK_BRAND_NAMES: dict[str, str] = {"Breville": "Sage"}

# --- Voice rubric (Noemi, 9 Oct 2026): red flags are counted, not any-one-is-low ---
# Two red flags or more make a voice low; exactly one caps it at medium, whatever the good signs.
VOICE_LOW_MIN_RED_FLAGS = 2
# Clear paid promotion (a discount code, an affiliate or referral link, "#ad") counts as this many red flags on its own.
PAID_PROMOTION_RED_FLAGS = 2

# A budget typed with no currency ("under 100") is in this currency (Noemi, 9 Oct 2026: the shoppers are in the UK).
BUDGET_DEFAULT_CURRENCY = "GBP"

# --- Live check of shown quotes (Noemi, 9 Oct 2026: Reddit's embed service) ---
# Seconds between two reads of Reddit's embed page (engine/live_check.py): an answer reads about 9 comments.
LIVE_CHECK_MIN_INTERVAL = 3.0

# --- Care tips (Noemi, 9 Oct 2026) ---
# Alongside each pick, credible advice from its threads on making it last ("descale it every 6 months"; extraction
# instructions v7, engine/care_tips.py), so what people buy lasts longer. Showing them is Noemi's decision.
# PROPOSED: up to this many per pick, the product's own tips first, then its kind's, never the same tip twice.
CARE_TIPS_PER_PICK = 2

# --- Archive reader and live checks (Noemi, 9 Oct 2026) ---
# Noemi decided on 9 Oct 2026, instead of paying for Parse: threads may be READ from Arctic Shift's archive (free) and
# their text stored in the library, but an archive keeps comments people later deleted, so archive-read threads are
# checked live (read again on Reddit through Parse, 2 credits each) regularly, and answers never show a quote from a
# thread not checked live recently. What she decided says so; the numbers Claude chose to carry it out are PROPOSED.

# How `python -m engine.library add` reads the threads it finds: "archive" (Arctic Shift, free) or "parse" (Parse,
# 2 credits a thread, as before 9 Oct 2026). Decided: the archive, since Parse credits are scarce.
LIBRARY_READER = "archive"
# Answers use a thread only if Reddit itself was read for it within this many days (a thread read through Parse counts
# from the day it was read). Days are calendar days, counted on the day the answer is given: a thread read live on
# 7 Oct can be quoted up to and including 21 Oct. Decided: 14 days.
LIVE_CHECK_SHOWN_DAYS = 14
# Every other archive-read thread is checked live when it never was, or was last checked more than this many days ago.
# Decided: 30 days, like the library's monthly refresh.
LIVE_CHECK_ALL_DAYS = 30
# PROPOSED: Parse credits a live-check run leaves untouched when no --max-credits is given (out of the month's 200),
# for adding threads and urgent re-reads.
LIVE_CHECK_CREDIT_RESERVE = 20
# Decided: answers require the live check. False (for an experiment only) lets answers use every thread whatever its
# last live check; the blind test must always run with True, so it can never show a quote that may have been deleted.
LIVE_CHECK_REQUIRED = True
# Retention (decided): an archive-read thread not checked live within LIVE_CHECK_ALL_DAYS + 7 days has its comments'
# text (and its post's text) removed from the library, keeping only ids, titles and dates so it can be read again.
# PROPOSED: the 7 days of grace, so one missed monthly run doesn't empty threads straight away. False turns it off.
ARCHIVE_TEXT_RETENTION = True
ARCHIVE_TEXT_KEPT_DAYS = LIVE_CHECK_ALL_DAYS + 7
# How many times an answer is written again after the live check drops comments (engine.pipeline._check_live).
LIVE_CHECK_ROUNDS = 3

# --- Bright Data reader (Noemi, 9 Oct 2026) ---
# Bright Data (brightdata.com) reads Reddit pages for us through its ready-made Reddit datasets (engine/bright_data.py).
# Noemi's account is on the free tier: this many records a month, and no charge beyond it (jobs simply stop working).
# One record is one post, or one top-level comment with its replies inside it.
BRIGHT_DATA_MONTHLY_RECORDS = 5000
# The two datasets used: the comments of a post, and the post itself (its title, text and writer).
BRIGHT_DATA_COMMENTS_DATASET = "gd_lvzdpsdlw09j6t702"
BRIGHT_DATA_POSTS_DATASET = "gd_lvz8ah06191smkebj4"
# A job runs on Bright Data's side (a 5-comment thread took about a minute). Its progress is asked every this many
# seconds, and after this many seconds the client stops waiting: asking again for the same thread picks the job up
# instead of paying for a new one.
BRIGHT_DATA_POLL_SECONDS = 10
BRIGHT_DATA_MAX_WAIT_SECONDS = 600
# Before a comments job, its cost is checked against the month's records left: at most the post's comment count.
# When the post couldn't be read first, that count is unknown, and the job is assumed to cost up to this many records.
BRIGHT_DATA_RECORDS_IF_UNKNOWN = 500
