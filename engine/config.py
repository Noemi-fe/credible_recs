"""Product decisions that shape the data, all in one place (docs/brief.md, version 4).

Every value here is Noemi's decision. Changing one is a deliberate product change, never a way to make
a label or a test pass: ask Noemi first. After a change, run `python -m engine.gold`; any existing label
that no longer fits is reported with its file and line.
"""

# Categories the engine ranks. A product mention can also be "other" (outside every category).
# "haircare" added on 11 Oct 2026 (Noemi: "i want to be able to ask about shampoo and receive some proper answers"):
# products put on the hair or scalp. Hair tools (dryers, straighteners) stay out of scope.
THREAD_CATEGORIES = ("skincare", "kitchen", "haircare")
MENTION_CATEGORIES = THREAD_CATEGORIES + ("other",)

SUBREDDITS: dict[str, tuple[str, ...]] = {
    # "acne" added by Noemi on 11 Oct 2026 (an agent had skipped r/acne threads for the acne-prone cleanser question).
    "skincare": ("SkincareAddiction", "AsianBeauty", "30PlusSkinCare", "SkincareAddictionUK", "acne"),
    "kitchen": ("BuyItForLife", "AskCulinary", "chefknives", "Cooking", "castiron", "Coffee", "espresso", "tea"),
    # Chosen by Claude on 11 Oct 2026 (reported to Noemi): the science-minded and product-heavy haircare communities,
    # most general advice first.
    "haircare": ("HaircareScience", "curlyhair", "wavyhair", "Hair", "femalehairadvice", "malehairadvice", "Dandruff"),
}
# Subreddits about one skin condition, {subreddit: the skin type that brings it in} (decided by Claude, 11 Oct 2026, when
# Noemi added r/acne): searched first for a request about that condition, as the most specific, and not for others.
CONDITION_SUBREDDITS: dict[str, str] = {"acne": "acne-prone"}

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
    # Added 11 Oct 2026 (Noemi's decision 3).
    "copied text",  # the same words as another writer's comment in the thread: a red flag (COPIED_TEXT_MIN_WORDS)
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
    # Noemi's decision of 11 Oct 2026: 0 (was 1). "Recent" fired on all 64 comments she labelled, so it told no one
    # apart and lifted voices to high (the rules said high 52 times to her 31). Still recorded as a tag.
    "recent": 0,
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
# The categories whose formulas change, so OLD_SKINCARE_POST_MAX_VOICE and the ranking's old-post penalty apply to them
# (haircare added by Claude on 11 Oct 2026, reported to Noemi: shampoos are reformulated as skincare is).
REFORMULATED_CATEGORIES = ("skincare", "haircare")

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

# --- The end-to-end slice (engine/pipeline.py; proposed 9 Oct 2026) ---
# How many of the library's most relevant threads one request reads, counting only threads about the product (the
# title or post names it) that the AI has already read; a relevance score no longer decides (review fixes, 9 Oct).
# Decided by Claude on 10 Oct 2026 (a technical value, reported to Noemi), measured on the 97-thread library without
# live checks: 8 threads gave 6/10 blind-test questions a full top 3, 12 gave 9/10, 16 and 24 also 9/10 but split
# one product's evidence across two spellings (b05's Cetaphil). With 8, bigger new threads pushed out the ones that
# held b02's evidence. Raised to 16 late on 10 Oct 2026 (a technical value, decided by Claude, reported to Noemi), on
# the 150-thread library with live checks and writers' profiles: 12 gave 8/10 a full top 3 (b03 retinol and b10 frying
# pan short), 16 gives 10/10 with every shown quote verified. It waited on the kettle research: at 16, b06's first pick
# is Bonavita, whose 1L Variable Temp kettle the research found sold in the UK with a UK plug, and OXO (not sold: 120 V)
# leaves. 16 also drops b08's "Look for: mason jars". The cost: b04 reads four cleanser, sunscreen and exfoliant threads
# whose posts mention moisturiser (its picks don't change).
PIPELINE_MAX_THREADS = 16
# When those threads give fewer than 3 picks, up to this many are read before giving up (Noemi's decision of 7 Oct
# 2026: "fetch more threads automatically before giving up"; built 11 Oct 2026, the value chosen by Claude and reported
# to her). Shampoo advice is spread over many brands: its 16 most relevant threads gave no pick, 24 and 32 gave one,
# 48 gave three (Nizoral, Neutrogena T-Gel, Head & Shoulders for an oily scalp).
PIPELINE_MORE_THREADS = 48
# Brand-only picks (decided by Noemi, 9 Oct 2026, decision 9): a brand or line that fits several products ("Lodge",
# "CeraVe") is ranked, under a name that says so ("Lodge cast iron skillet line", BRAND_PICK_NAME below), when its
# threads make the product clear (BRAND_PICK_TITLE_SHARE below) or, since 12 Oct 2026, when the brand-lines list says
# the brand sells that kind of product (BRAND_LINE_NOT_SOLD below); otherwise it is left out, and listed on the result.
# False leaves every brand or line name out, as before 9 Oct 2026.
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
# The name such a pick is shown under: "Lodge cast iron skillet line". Noemi's wording of 12 Oct 2026, from testing the
# demo ("L'Oreal hair oil serum line"); from 9 Oct it was "Lodge (their cast iron skillets)". A name that already says
# the type is shown as it is: "CeraVe cleanser" (Noemi, 9 Oct 2026), never "CeraVe cleanser cleanser line".
BRAND_PICK_NAME = "{brand} {product_type} line"
# A product type as a name shows it, when that isn't module 1's lowercase name: "Le Creuset Dutch oven line".
PRODUCT_TYPE_SHOWN: dict[str, str] = {"dutch oven": "Dutch oven"}
# The plural of each product type (engine/query.py, PRODUCT_TYPES): for the name of a brand line left out because its
# brand doesn't sell them ("Batiste doesn't sell shampoos", BRAND_LINE_NOT_SOLD), and for the words a price or facts
# entry under a brand's name may add ("OXO kettles"; engine/pipeline.py, _type_words).
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
    "shampoo": "shampoos",
    "dry shampoo": "dry shampoos",
    "conditioner": "conditioners",
    "leave-in conditioner": "leave-in conditioners",
    "hair mask": "hair masks",
    "hair oil": "hair oils",
}

# Decision 11, budgets (engine/prices.py). Current prices live in data/prices.json, each with its shop and the day
# Claude looked it up. PROPOSED: a price checked more than this many days ago is still shown, with its date, but
# never used to leave a product out of a budget request: it may have changed since.
PRICE_MAX_AGE_DAYS = 30

# Decision 12, names shown to a UK audience (decided by Noemi, 9 Oct 2026): {brand word: the word shown}. Sage is
# Breville's UK and EU brand; the alias list (engine/data/product_aliases.json) already treats the two as one product,
# and the answer shows the UK name. Quotes are never changed: a quote that says "Breville" keeps it.
UK_BRAND_NAMES: dict[str, str] = {"Breville": "Sage"}
# Under a pick shown by its UK name, a note says why its quotes use the other one (Claude, 10 Oct 2026). Shown as a
# note ("Note: ...") like the product-facts cautions.
OTHER_NAME_NOTE = "sold as {brand} outside the UK, so writers often call it {brand}"

# --- Voice rubric (Noemi, 9 Oct 2026): red flags are counted, not any-one-is-low ---
# Two red flags or more make a voice low; exactly one caps it at medium, whatever the good signs.
VOICE_LOW_MIN_RED_FLAGS = 2
# Clear paid promotion (a discount code, an affiliate or referral link, "#ad") counts as this many red flags on its own.
PAID_PROMOTION_RED_FLAGS = 2

# A budget typed with no currency ("under 100") is in this currency (Noemi, 9 Oct 2026: the shoppers are in the UK).
BUDGET_DEFAULT_CURRENCY = "GBP"

# --- Live check of shown quotes (Noemi, 9 Oct 2026: Reddit's embed service) ---
# Seconds between the starts of two reads of Reddit's embed page (engine/live_check.py). 3.0 when an answer read about 9
# comments one at a time; answers now show 10 to 40 quotes, and a fresh answer waited up to a minute on them. PROPOSED
# (latency, 12 Oct 2026, decided by Claude as the orchestrator asked, to be confirmed by Noemi): the comments of an
# answer are read the way a web page that embeds them is loaded by a browser: LIVE_CHECK_PARALLEL at once, each read
# starting at least LIVE_CHECK_MIN_INTERVAL after the one before (so never more than 10 reads a second), each comment
# read once and kept for 48 hours as before.
LIVE_CHECK_MIN_INTERVAL = 0.1
LIVE_CHECK_PARALLEL = 8
# Never more than Reddit allows (12 Oct 2026): its embed pages answer about 200 reads in 10 minutes from one address
# (x-ratelimit-used 200 in its "429 Too Many Requests" answer to a test run that read faster), and a read refused that
# way can't check a quote, which is then dropped. So up to LIVE_CHECK_BURST reads at once, then one more every
# LIVE_CHECK_REFILL_SECONDS: at most 40 + 600 / 4 = 190 in any 10 minutes, leaving room for other reads from the same
# address. A fresh answer (10 to 40 comments) reads at full speed; many answers in a row slow to a read every 4 s, as
# 3 s spacing did before. Decided by Claude, reported.
LIVE_CHECK_BURST = 40
LIVE_CHECK_REFILL_SECONDS = 4.0
# Paced by what Reddit says is left (13 Oct 2026, Noemi: "go ahead with the reddit header pacing"): every embed page
# says how many reads the address has left in the current 10 minutes (x-ratelimit-remaining) and when they come back
# (x-ratelimit-reset, seconds). Reads go at once while LIVE_CHECK_SPREAD_BELOW or more are left beyond the
# LIVE_CHECK_RESERVE kept for other reads from the same address (on Google Cloud Run it is shared); with fewer, they are
# spread evenly over the rest of the 10 minutes, so they never run out before it ends; with none, the next read waits
# for the next 10 minutes. About 140 of each 200 go at once, against 40 with the burst alone. Until Reddit has said,
# the burst and refill above. Numbers decided by Claude, reported.
LIVE_CHECK_RESERVE = 10
LIVE_CHECK_SPREAD_BELOW = 50

# --- Care tips (Noemi, 9 Oct 2026) ---
# Alongside each pick, credible advice from its threads on looking after it ("descale it every 6 months"; extraction
# instructions v8, engine/care_tips.py), so what people buy lasts longer. Showing them is Noemi's decision. Up to this
# many per pick, about the pick itself (Noemi, 11 Oct 2026), never the same tip twice.
CARE_TIPS_PER_PICK = 2
# Tips about the kind of product ("descale any electric kettle") are shown once, in a note at the end of the answer,
# not under every pick (Noemi, 11 Oct 2026): at most this many (decided by Claude, 11 Oct 2026).
CARE_NOTE_TIPS = 3

# --- Archive reader and live checks (Noemi, 9 Oct 2026) ---
# Noemi decided on 9 Oct 2026, instead of paying for Parse: threads may be READ from Arctic Shift's archive (free) and
# their text stored in the library, but an archive keeps comments people later deleted, so archive-read threads are
# checked live (read again on Reddit through Parse, 2 credits each) regularly, and answers never show a quote from a
# thread not checked live recently. What she decided says so; the numbers Claude chose to carry it out are PROPOSED.

# How `python -m engine.library add` reads the threads it finds: "archive" (Arctic Shift, free) or "parse" (Parse,
# 2 credits a thread, as before 9 Oct 2026). Decided: the archive, since Parse credits are scarce.
LIBRARY_READER = "auto"
# Since 10 Oct 2026 (Noemi asked for a Bright Data tool "to not get stuck with parse and everything else", and for it
# to be built if it made sense): "auto" tries Arctic Shift's archive first (free search, full reply trees), and when it
# fails (down since 9 Oct 2026: Cloudflare 522) finds and reads the threads through Bright Data instead
# (engine.sources.FallbackSource and BrightDataSource). "archive", "parse" and "bright_data" each use one source only.
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
# LIVE_CHECK_ROUNDS (3), how many times an answer was written again after the live check dropped comments, is gone
# (12 Oct 2026): an answer written after the third round was shown with its new quotes unchecked. It is now written
# again until every quote it shows has passed (engine.pipeline._check_live).

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

# --- Needs and contradictions (9 Oct 2026) ---
# Two changes to the ranking decided on 9 Oct 2026 (engine/needs.py, engine/contradictions.py, engine/pipeline.py).
# The words below are Claude's choice to carry them out (9 Oct 2026); Noemi may change any of them.

# 1. Needs. A mention whose comment talks about what the request asks for ("sensitive skin", "a beginner") counts
# this many times its weight, a recommendation or a warning alike ("too harsh for sensitive skin"). The starting value
# set with the change.
# Off (1.0) since 9 Oct 2026: tried at 1.5, word rules made the retinol-for-a-beginner answer worse (a Tazorac comment
# "started on" read as beginner-friendly; Differin's honest warnings weighed more). Needs a judgement of whether a
# product suits the request (product knowledge), not words in comments. Kept as a switch; tests set it explicitly.
NEED_MATCH_BOOST = 1.0
# The needs a request can name, each with the words that show a comment talks about it. A word is found at the start
# of a word, so a word beginning finds its longer forms ("sensitiv" finds "sensitive" and "sensitivity", "start"
# finds "started" and "starting"); a phrase is found whole ("white cast", "white casts"). The skin types and
# must-haves module 1 finds (engine/query.py) each have an entry, plus a few needs typed in other words. A request
# names a need when it says its name or one of its words ("for a beginner", "new to retinol" name "beginner").
NEEDS: dict[str, tuple[str, ...]] = {
    # Skin types (engine/query.py, SKIN_TYPES).
    # A reaction, or the lack of one, talks about sensitive skin too ("doesn't cause a rash", "no redness"; 10 Oct
    # 2026, late: b01's Stratia quote wasn't counted).
    "sensitive": ("sensitiv", "reactive", "easily irritated", "irritated easily", "irritates easily", "irritat",
                  "rash", "redness", "sting"),
    "dry": ("dry", "dries", "dehydrated", "flaky"),
    "oily": ("oily", "greasy", "shiny"),
    "combination": ("combination", "combo skin"),
    "acne-prone": ("acne", "breakout", "break out", "broke me out", "breaks me out", "pimple"),
    "normal": ("normal skin",),
    "mature": ("mature", "anti-aging", "anti-ageing", "anti aging", "anti ageing", "wrinkle", "fine line"),
    # Must-haves (engine/query.py, MUST_HAVES): a comment about the thing itself talks about the need, for or against.
    "fragrance-free": ("fragrance", "unscented", "scent", "perfume"),
    "non-comedogenic": ("comedogenic", "clog"),
    "no white cast": ("white cast",),
    "cruelty-free": ("cruelty",),
    "vegan": ("vegan",),
    "reef-safe": ("reef",),
    "plastic-free": ("plastic",),
    "stainless steel": ("stainless",),
    "dishwasher-safe": ("dishwasher",),
    "induction-compatible": ("induction",),
    "temperature control": ("temperature", "temp control", "variable temp"),
    # Needs typed in other words.
    # First-timers. "first" alone is too loose in comments ("I used the first one"), so only these two phrases.
    "beginner": ("beginner", "first time", "my first", "new to", "start", "newbie", "novice"),
    "gentle": ("gentle", "mild", "harsh"),  # "too harsh" talks about gentleness too
    "home cook": ("home cook", "home cooking"),
    # Something that lasts. A mention with long-term use (module 5) talks about it too: it describes long use.
    "lasting": ("lasts", "lasted", "lasting", "outlast", "durab", "held up", "holds up", "died", "broke",
                "stopped working", "fell apart"),
}
# Other words of a request that name one of those needs: "first chef's knife", "will last decades", "lasts 10+ years".
# Module 1's "lasts 10+ years" (min_years) names "lasting" as well.
NEED_REQUEST_WORDS: dict[str, str] = {
    "first": "beginner", "last": "lasting", "year": "lasting", "decade": "lasting", "lifetime": "lasting",
}
# Words of a request too common in comments to show a need: "doesn't leave a white cast", "for a home cook", and
# "burr coffee grinder" (the kind of grinder nearly every grinder comment is about).
NEED_IGNORED_WORDS = ("leave", "cook", "burr")

# 2. Writers who contradict themselves (Noemi's rule, 9 Oct 2026). A writer who recommends a product in one comment and
# warns against it in another, in any of the request's threads, without saying something changed, counts as a low
# voice in every mention they make (so none of them is credible). Their warning says something changed when its own
# words hold one of these (word beginnings, as for needs above), or "after" a number of days, weeks, months or years
# ("after 6 months", engine/contradictions.py): an update is honest, not a contradiction.
CHANGE_WORDS = (
    "died", "broke", "stopped", "fail", "reformulat", "new formula", "change", "changing", "no longer", "anymore",
    "any more", "used to", "update", "edit", "developed a reaction", "developed an allergy",
)

# --- Upkeep and availability (9 Oct 2026) ---
# The monthly live check (`python -m engine.library check-live`) reads threads again through Bright Data (free tier:
# BRIGHT_DATA_MONTHLY_RECORDS records a month) instead of Parse, whose free credits are nearly used up this month.
# Decided 9 Oct 2026. `--reader parse` still reads through Parse (2 credits a thread), as before.
LIVE_CHECK_READER = "bright_data"
# Chosen by Claude (a technical value, reported to Noemi): Bright Data records a live-check run leaves untouched when no
# --max-records is given (out of the month's 5,000), for backup reads and urgent re-reads.
LIVE_CHECK_RECORD_RESERVE = 300

# --- Sold second-hand only (Noemi's decision, 10 Oct 2026) ---
# Vintage products no longer made, sold only second-hand (cast iron by Griswold and Wagner, out of production for
# decades), count as available to UK shoppers, and the answer says so: "Sold second-hand only: eBay UK, checked 10 Oct
# 2026" (engine.answer.AVAILABILITY_SECOND_HAND). A price-list entry says it with "second_hand": true, only with
# "available": true (engine/prices.py). Before, "available" meant sold new by a shop, so Wagner was left out of b08
# while the brand pick "Griswold (their cast iron skillets)" stayed only because brand picks are never checked. Brand
# picks are still never priced and never left out for an entry under their own name, but one whose brand's own name
# has a second-hand entry ("Griswold") shows the second-hand line. No value to set.

# --- Product facts (9 Oct 2026) ---
# Decided by Claude (the orchestrator) on 9 Oct 2026, as Noemi asked, and reported to her. The ranking reads only what
# Reddit says, so it ignored what a request asks for: "retinol for a beginner with sensitive skin" picked Tazorac, a
# strong prescription retinoid. Word rules on comments made it worse (NEED_MATCH_BOOST above): comments rarely say "too
# strong for beginners". So each product can have a few facts, looked up online with a source (data/product_facts.json,
# engine/product_facts.py), and the request is matched against them. A fact that isn't known never counts against a
# product.

# The vocabulary: every fact a product can have, and the values it can take. True/false facts take JSON true or false
# only. Whether a product is sold (in the UK, or at all) isn't a fact here: the price list says it (data/prices.json,
# "available"), so it isn't kept twice.
PRODUCT_FACT_VALUES: dict[str, tuple] = {
    "fragrance_free": (True, False),  # no added fragrance or perfume
    "prescription_only": (True, False),  # sold in the UK only on a prescription (Tazorac, tretinoin, Differin)
    "strength": ("gentle", "moderate", "strong"),  # how strong a retinoid or an exfoliant is
    "white_cast": (True, False),  # a sunscreen that leaves a white cast on the skin
    "finish": ("matte", "natural", "dewy"),  # how a sunscreen looks once on
    "filters": ("mineral", "chemical", "hybrid"),  # a sunscreen's UV filters
    "texture": ("light", "rich"),  # a moisturiser's or a cleanser's feel
    "plastic_free_inside": (True, False),  # a kettle where no plastic touches the water
    "pfas_free": (True, False),  # a pan with no PFAS ("forever chemicals", such as PTFE / Teflon) in its coating
    "non_stick": (True, False),  # a pan with a non-stick coating (ceramic or PTFE); seasoned steel or iron isn't
    "induction": (True, False),  # works on an induction hob
    "maker_warns_sensitive": (True, False),  # the maker's own page says not to use it on sensitive skin (10 Oct 2026)
    "sulfate_free": (True, False),  # a shampoo that cleans without sulfates (SLS, SLES, ALS...) (11 Oct 2026)
}
# The facts each product type (engine/query.py, PRODUCT_TYPES) can have. Every skincare product can say whether it is
# fragrance-free and whether its maker warns against sensitive skin; only retinoids and exfoliants, the skincare sold in
# prescription versions (tretinoin, adapalene, azelaic acid 15%+) and in strengths, can be prescription-only or have a
# strength (10 Oct 2026: a moisturiser's "prescription_only: false" was always true and only asked researchers for busy
# work). A type not listed (a chef knife, a coffee grinder) has no facts yet.
PRODUCT_FACTS_FOR_SKINCARE = ("fragrance_free", "maker_warns_sensitive")
PRODUCT_FACTS_FOR_TREATMENTS = ("fragrance_free", "prescription_only", "strength", "maker_warns_sensitive")
PRODUCT_FACTS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "exfoliant": PRODUCT_FACTS_FOR_TREATMENTS,
    "retinoid": PRODUCT_FACTS_FOR_TREATMENTS,
    "sunscreen": PRODUCT_FACTS_FOR_SKINCARE + ("white_cast", "finish", "filters"),
    "moisturiser": PRODUCT_FACTS_FOR_SKINCARE + ("texture",),
    "cleanser": PRODUCT_FACTS_FOR_SKINCARE + ("texture",),
    "serum": PRODUCT_FACTS_FOR_SKINCARE,
    "toner": PRODUCT_FACTS_FOR_SKINCARE,
    "eye cream": PRODUCT_FACTS_FOR_SKINCARE,
    "lip balm": PRODUCT_FACTS_FOR_SKINCARE,
    "electric kettle": ("plastic_free_inside",),
    "stovetop kettle": ("plastic_free_inside",),
    "frying pan": ("pfas_free", "non_stick", "induction"),
    "saucepan": ("pfas_free", "non_stick", "induction"),
    "shampoo": ("sulfate_free",),  # 11 Oct 2026: "sulfate-free" is the shampoo requirement people type most
}
# The rules: when a request asks for one of "asks", a product whose fact has "value" doesn't suit it. "hard": True
# leaves the product out (listed on the result); False keeps it and shows the reason under the pick as a caution. A
# request asks for something when module 1 finds it (a skin type, a must-have such as "fragrance-free"), when
# engine/needs.py finds a need that isn't a must-have ("beginner" in "new to retinol", "gentle"), or when
# PRODUCT_FACT_REQUEST_WORDS below finds its words. "gentle" is Claude's addition to "a beginner or sensitive skin": a
# request for a gentle product is not one for a strong formula either. The reasons are shown to users: wording decided
# by Claude, 9 Oct 2026.
PRODUCT_FACT_RULES: dict[str, dict] = {
    "too strong": {"asks": ("beginner", "sensitive", "gentle"), "fact": "strength", "value": "strong", "hard": True,
                   "reason": "it is a strong formula, too strong for beginners or sensitive skin"},
    "prescription only": {"asks": ("beginner", "sensitive", "gentle"), "fact": "prescription_only", "value": True,
                          "hard": True,
                          "reason": "it is prescription-only: a strong treatment, not one for beginners or sensitive "
                                    "skin"},
    "fragrance": {"asks": ("fragrance-free",), "fact": "fragrance_free", "value": False, "hard": True,
                  "reason": "it has added fragrance"},
    "white cast": {"asks": ("no white cast",), "fact": "white_cast", "value": True, "hard": True,
                   "reason": "it leaves a white cast"},
    "PFAS": {"asks": ("PFAS-free",), "fact": "pfas_free", "value": False, "hard": True,
             "reason": "it isn't PFAS-free"},
    "not non-stick": {"asks": ("non-stick",), "fact": "non_stick", "value": False, "hard": True,
                      "reason": "it isn't non-stick"},
    "plastic": {"asks": ("plastic-free",), "fact": "plastic_free_inside", "value": False, "hard": True,
                "reason": "it has plastic inside"},
    "not induction": {"asks": ("induction-compatible",), "fact": "induction", "value": False, "hard": True,
                      "reason": "it doesn't work on an induction hob"},
    "rich texture": {"asks": ("oily", "acne-prone"), "fact": "texture", "value": "rich", "hard": False,
                     "reason": "its texture is rich, which can feel heavy on oily or acne-prone skin"},
    # Decided by Claude, 10 Oct 2026 (late), reported to Noemi: the mirror of "rich texture". Found in b04: "fragrance-
    # free moisturiser for very dry skin in winter" had a light gel as its first pick with nothing said. A note only.
    # "types": the product types a rule applies to (every type that has the fact when left out): a light cleanser
    # suits dry skin, so this one is for moisturisers.
    "light texture": {"asks": ("dry",), "fact": "texture", "value": "light", "hard": False, "types": ("moisturiser",),
                      "reason": "its texture is light, which may not be enough on its own for dry skin"},
    # Decided by Claude, 10 Oct 2026: The Ordinary's Mandelic Acid is gentle by strength, but its maker's page says not
    # to use it on sensitive skin. "confirm": False: most makers say nothing either way, so this fact is recorded only
    # when a maker's page says it, and not knowing it is never a requirement (no note, no brand pick left out, not
    # asked for by `python -m engine.product_facts todo`). Every other rule is one to confirm.
    "maker warns sensitive": {"asks": ("sensitive",), "fact": "maker_warns_sensitive", "value": True, "hard": True,
                              "confirm": False, "reason": "its maker says not to use it on sensitive skin"},
    # Decided by Claude, 11 Oct 2026, reported to Noemi: "sulfate-free shampoo for curly hair" had picked Head &
    # Shoulders, which has sulfates. A requirement like PFAS-free: left out when its facts say it has sulfates.
    "sulfates": {"asks": ("sulfate-free",), "fact": "sulfate_free", "value": False, "hard": True,
                 "reason": "it has sulfates"},
}
# Words of a request that ask for something module 1 doesn't find on its own: regular expressions, found at the start
# of a word in the request (lowercased). "doesn't leave a white cast" asks for no white cast (module 1 finds only "no"
# or "without a white cast"); "without PFAS" and "PFAS-free" ask for PFAS-free; "non-stick" asks for non-stick, unless
# a word just before it says the opposite ("not non-stick", "instead of non-stick").
PRODUCT_FACT_REQUEST_WORDS: dict[str, tuple[str, ...]] = {
    "no white cast": (r"white cast",),
    "PFAS-free": (r"pfas",),
    "sulfate-free": (r"sul(?:f|ph)ate[- ]?free", r"(?<=no )sul(?:f|ph)ates?", r"(?<=without )sul(?:f|ph)ates?"),
    "non-stick": (r"(?<!not )(?<!not a )(?<!no )(?<!without )(?<!avoid )(?<!instead of )(?<!rather than )"
                  r"(?<!other than )non[- ]?stick",),
}
# `python -m engine.product_facts todo` looks at this many candidates per blind-test question: its picks, then the
# products that qualify or nearly qualify, in the ranking's order.
PRODUCT_FACTS_TODO_CANDIDATES = 5

# --- Pick polish (10 Oct 2026) ---
# Decided by Claude (the orchestrator) on 10 Oct 2026, as Noemi asked, and reported to her. Three fixes to what a pick
# shows, found in the 10 Oct evaluation run (eval/RUNS.md).
#
# 1. A brand pick never appears next to its own specific product ("Victorinox chef knife line" next to "Victorinox
# chef's knife"): when both qualify, the specific product stays and the brand pick steps aside (engine/pipeline.py). No
# value to set.
#
# 2. A brand pick can't be checked against product facts (a brand has many products), so when the request has a hard
# requirement that its product type can have (PRODUCT_FACT_RULES above, "hard": True), brand picks are left out and
# listed with this reason. The wording is shown to users: "a whole brand can't be checked for PFAS or a non-stick
# coating". HARD_REQUIREMENT_NAMES says what each hard rule checks for, in words that fit the sentence; several are
# joined with commas and a last "or".
BRAND_PICK_UNCHECKABLE = "a whole brand can't be checked for {requirements}"
HARD_REQUIREMENT_NAMES: dict[str, str] = {
    "too strong": "strength",
    "prescription only": "prescription-only formulas",
    "fragrance": "added fragrance",
    "white cast": "a white cast",
    "PFAS": "PFAS",
    "not non-stick": "a non-stick coating",
    "plastic": "plastic inside",
    "not induction": "working on an induction hob",
    "maker warns sensitive": "a maker's warning against sensitive skin",
    "sulfates": "sulfates",
}
#
# 3. Care tips most writers agree on come first (engine/care_tips.py, tips_by_agreement). Two tips say the same thing
# when they are the same tip (same_tip), or when they share at least CARE_TIP_SHARED_WORDS words and, counting both
# tips' words together, at least CARE_TIP_SHARED_SHARE of them are words both have (little words such as "with" and
# "the" aside, and endings: "descale it with vinegar" and "descaling with white vinegar regularly" share 2 words, 4 of
# their 6, so they say the same thing; "descale every 6 months" and "descale with citric acid", one word in common,
# don't). Measured on the 10 Oct 2026 library against a looser rule (half of the shorter tip's words), which put
# "only for boiling water; brew elsewhere" with the kettle's descaling tips.
CARE_TIP_SHARED_WORDS = 2
CARE_TIP_SHARED_SHARE = 0.5
# Tips about fixing a broken part rather than looking after the product come after every other tip, however many
# writers agree on them: regular expressions, matched on whole words of the tip (lowercase, punctuation aside). "grind"
# counts only as grinding something down ("grind it flat"): a coffee grinder's "only grind with the cap on" is upkeep.
# Since 12 Oct 2026 (Noemi: "a repair story isn't one") repairs are left out of answers altogether (engine/answer.py),
# bending or pushing a part back into shape is one, and replacing the product itself when it wears out ("replace it
# when the coating is damaged") isn't: only replacing a part ("replace the thermal fuse") is.
CARE_TIP_REPAIR_WORDS = (
    r"seal(s|ed|ing|ant)?",
    r"glue(s|d)?", r"gluing",
    r"replac(e|es|ed|ing|ement)(?! (it|them|when|once|if|as soon as|after)\b)",
    r"(push|pushed|pushing|bend|bends|bent|bending|hammer|hammered) (it |them |the \w+ )?back",
    r"back (in)?to (its |their )?(original )?shape", r"straighten(s|ed|ing)?",
    r"solder(s|ed|ing)?",
    r"grind(s|ing)? (it |them )?(down|flat|smooth|off|away)", r"angle grinders?",
    r"sand(s|ed|ing|er|paper)?",
    r"epoxy",
    r"repair(s|ed|ing)?",
)

# --- Facts we couldn't confirm (10 Oct 2026) ---
# Decided by Claude (the orchestrator) on 10 Oct 2026, as Noemi asked, and reported to her. When a request has a hard
# requirement (engine.product_facts.hard_requirements: "without PFAS") and a pick's facts don't say whether it meets it
# ("OXO non-stick pan": OXO sells both PTFE and ceramic pans), the pick keeps its place and shows a note under it:
# "Note: we couldn't confirm it's PFAS-free or that it's non-stick." Leaving such picks out would empty most answers;
# showing them silently would mislead. A note never changes the ranking. The wording is shown to users: each rule's
# words fit "we couldn't confirm ..."; several are joined with commas, a last "or", and "that" before all but the first.
UNCONFIRMED_NOTE = "we couldn't confirm {facts}"
UNCONFIRMED_FACT_NAMES: dict[str, str] = {
    "too strong": "it's gentle enough for beginners or sensitive skin",
    "prescription only": "it's sold without a prescription",
    "fragrance": "it's fragrance-free",
    "white cast": "it leaves no white cast",
    "PFAS": "it's PFAS-free",
    "not non-stick": "it's non-stick",
    "plastic": "no plastic touches the water",
    "not induction": "it works on an induction hob",
    "sulfates": "it's sulfate-free",
}

# --- Sets, blocks and sharpeners aren't the product (10 Oct 2026) ---
# Decided by Claude (the orchestrator) on 10 Oct 2026, as Noemi asked, and reported to her. Found in the 10 Oct
# evaluation run: "Henckels knife block" (the AI's type: "knife set") was a pick for "first chef's knife", because
# "knife set" names a knife. A type in the AI's own words that has one of these words names something that holds,
# sharpens, covers or bundles the product, not the product, so it is another type (engine/pipeline.py,
# _another_type_by_ai). Whole words, with or without a plural "s"; "steel" and "stone" aren't here: "stainless steel
# kettle" and "stone frying pan" are the product.
# Words that, just before a product type the open model named, make another kind of product (11 Oct 2026): an
# "immersion blender" or a "stick blender" isn't a blender, a "hand mixer" isn't a mixer. Chosen by Claude, reported.
OTHER_KIND_WORDS = ("immersion", "stick", "hand", "handheld")
OTHER_TYPE_WORDS = ("set", "block", "sharpener", "stand", "rack", "holder", "roll", "bag", "case", "cover", "lid", "kit",
                    "bundle", "strip", "guard", "sheath")

# --- The blind test (engine/blind_test.py, 10 Oct 2026) ---
# From the brief's protocol: each tester gets 5 of the 10 questions, and the target is at least 60% preference
# against each rival. Decided by Claude (10 Oct 2026): the names that give a tool away in an answer shown to a tester
# (any case, whole words); packets are refused while an answer to show has one.
BLIND_TEST_QUESTIONS_PER_TESTER = 5
BLIND_TEST_TARGET = 0.6
BLIND_TEST_GIVEAWAYS = ("chatgpt", "openai", "gpt", "vetted", "credible recs", "claude", "anthropic")
# Noemi's decision, 10 Oct 2026 (eval/blind_test/FORMAT.md): every answer shown to a tester uses the same template, in
# each tool's own words, with at most this many words per pick (cut at a word, marked "…"), so no answer wins by length.
BLIND_TEST_WORDS_PER_PICK = 90

# --- The evaluation's targets (docs/brief.md, "Evaluation and success metrics") ---
# Written down here on 10 Oct 2026 so eval/run_eval.py, eval/metrics.json and the how-we-score page (/how) all read
# the same targets. They are the brief's, not new decisions. MATCHING_TARGET (module 4) and BLIND_TEST_TARGET (against
# each rival) are above.
QUOTE_VERIFICATION_TARGET = 1.0  # every shown quote found word for word in its comment
EXTRACTION_PRECISION_TARGET = 0.90  # of the AI's products, the share Noemi's labels confirm
EXTRACTION_RECALL_TARGET = 0.80  # of Noemi's labelled products, the share the AI finds
CREDIBILITY_AGREEMENT_TARGET = 0.80  # high-versus-low match with Noemi's labels
COST_PER_QUESTION_TARGET_USD = 0.05  # "under $0.05": logged API spend divided by questions

# --- The price to-do looks past the picks (10 Oct 2026) ---
# Decided by Claude, reported to Noemi. Pricing a pick over budget let the next, unpriced product into b09's top 3
# (the Comandante C40, then the Baratza Sette 270). So `python -m engine.prices todo` also lists, per question, up to
# this many products right behind the picks (picks-in-waiting: qualifying or nearly, by engine.product_facts.candidates).
PRICES_TODO_NEXT_IN_LINE = 3

# --- Services aren't products (10 Oct 2026) ---
# Instructions v7 say a service (laser treatments, facials, salon or clinic procedures: done to you, not bought to use)
# is never a product mention, but the AI still listed four laser treatments in one thread. `python -m engine.extract
# check` enforces it: a mention whose type (in the AI's words) matches one of these, as whole words, is rejected.
# Decided by Claude, reported to Noemi. "treatment" alone isn't here: a spot treatment is a product; nor "facial"
# alone: a facial cleanser or oil is one.
SERVICE_TYPE_PATTERNS = (r"laser", r"procedures?", r"microneedling", r"salon", r"clinic", r"in-office",
                         r"(salon |spa )?facials?$")

# --- A brand pick names its most recommended model (10 Oct 2026) ---
# Decided by Claude, reported to Noemi. Under a brand pick ("Victorinox chef knife line"), the answer names the model
# of that brand its credible writers recommend most, when at least this many of them recommend it and its name says
# more than the brand and these generic words (or holds a number: "Lodge 10 skillet"): "Lodge cast iron pan" names no
# model. Only products still in the ranking count: never one left out as another type, not sold or over budget.
BRAND_PICK_MODEL = "Most named model: {model}"
BRAND_MODEL_MIN_CREDIBLE = 2
BRAND_MODEL_GENERIC_WORDS = ("the", "a", "their", "my", "one", "ones", "pan", "pans", "skillet", "skillets", "knife",
                             "knives", "kettle", "kettles", "grinder", "grinders", "chef", "chefs", "chef's", "cast",
                             "iron", "electric", "coffee", "burr", "hand", "manual", "set", "line", "range",
                             "product", "products", "stuff", "cookware", "frying", "fry", "non-stick", "nonstick",
                             "stainless", "steel", "carbon",
                             # descriptions, not models ("restored", "vintage Griswold"): 10 Oct 2026
                             "restored", "vintage", "old", "older", "used", "new", "newer", "original", "any", "good",
                             "cheap", "basic", "big", "small", "large", "little", "or", "and")

# --- A quote that says the opposite of the request is shown last (10 Oct 2026) ---
# Decided by Claude, reported to Noemi. Found in b02: a pick's supporting quote said "does leave a white cast" for a
# request asking for none (its writer recommends the sunscreen anyway). For each ask, a quote matching one of these
# (lowercase, whole words) is tried only after every other credible quote. Never hidden, never a reason to leave a
# product out: the writer still recommends it.
OPPOSITE_QUOTE_PATTERNS: dict[str, tuple[str, ...]] = {
    "no white cast": (r"(?<!n't )(?<!not )(?<!never )(?<!no )\bleaves? (a |any |some |slight |a slight |a little |a bit "
                      r"of |an? obvious )?white cast",
                      r"\b(has|have|had|with) (a |some |slight |a slight |a little |a bit of |an? obvious )?white cast",
                      # "will give you a white cast", "gave me a slight white cast" (b02, 11 Oct 2026); never
                      # "doesn't give a white cast" or "never gives me any".
                      r"(?<!n't )(?<!not )(?<!never )\b(gives?|gave|giving|causes?|caused) (you |me |us )?(a |any |some "
                      r"|slight |a slight |a little |a bit of |an? obvious )?white cast",
                      # "there's a slight white cast" (12 Oct 2026: a "Look for: mineral sunscreen" note said so for a
                      # request asking for none); never "there's no white cast".
                      r"\bthere('s| is| was| will be| would be) (a |some |slight |a slight |a little |a bit of "
                      r"|an? obvious )?white cast"),
    "fragrance-free": (r"(?<!no )(?<!without )(?<!n't )\b(smells?|scent(ed)?|perfume(d)?)\b(?! ?-?free)",
                       r"\bfragrance(d)?\b(?! ?-?free)(?<!no fragrance)"),
}
# Something that lasts (10 Oct 2026, b06: an Oxo pick's first quote said its kettle stopped working within a year):
# failing within days, weeks, months or up to three years, said either way round ("died within 6 months", "after two
# years it broke"). "Broke in" counts only before a length of time: "it broke in nicely" is breaking a pan in.
_FAILED = (r"(stop(s|ped|ping)? working|died|dies|broke(?! in (?!(about |around |only |just |under |less than )?"
           r"(a |an |one |two |three |\d|a few |a couple )))|breaks|failed|fails|quit|gave out|fell apart|falls apart"
           r"|crapped out|packed (in|up)|started leaking|cracked|rusted|warped)")
_SOON = (r"(after|within|in|under) (just |only |about |around |roughly |barely |less than |under |a little over )?"
         r"((a|an|one|two|three|four|five|six|\d+|a few|(a )?couple( of)?|several|few) (days?|weeks?|months?)"
         r"|(a|one|1|two|2|three|3|a few|(a )?couple( of)?) years?|the first (few )?(days?|weeks?|months?|year))")
# Saying outright that it won't last counts too ("not BIFL", "doesn't last"; b10, 10 Oct).
OPPOSITE_QUOTE_PATTERNS["lasting"] = (rf"\b{_FAILED}\b[^.!?]{{0,40}}?\b{_SOON}\b",
                                      rf"\b{_SOON}\b[^.!?]{{0,30}}?\b{_FAILED}\b",
                                      r"\b(not|isn't|aren't|wasn't|weren't|never) (really |exactly |quite )?"
                                      r"(bifl|buy it for life)\b",
                                      r"\b(won't|doesn't|didn't|don't|will not|does not|did not|do not|never) "
                                      r"(really |ever |just )?last\b",
                                      # A short life said plainly ("lasts around 2 years"; b06),
                                      # but not "has lasted 2 years so far" or "3 years and counting".
                                      r"\blast(s|ed)? (only |just |about |around |somewhere around |roughly |maybe "
                                      r"|barely |under |less than )*((a|an|one|two|three|four|five|six|\d+|a few"
                                      r"|(a )?couple( of)?|several) (days?|weeks?|months?)|(a|one|two|three|1|2|3"
                                      r"|a few|(a )?couple( of)?) years?)\b(?! (so far|and (it'?s |is )?(still|counting)"
                                      r"|now))",
                                      # Buy the cheapest and swap it for a new one when it fails (12 Oct 2026: a "Look for" note
                                      # said so for an air fryer that lasts).
                                      r"\breplace (it|them) (before|once|as soon as) (it|they)\b")

# --- Quotes that say what the writer thinks come first (10 Oct 2026) ---
# Decided by Claude, reported to Noemi. Found in b09: a writer listing the grinders they own (an Encore, a C2 at work
# and a JX) named the C2 but gave no view. Among credible quotes, those that name the product and hold one of these words
# (a view or an experience, whole words, any case) come first; then those that only name it; then the rest.
QUOTE_VIEW_WORDS = ("great", "love", "loved", "loving", "recommend", "recommended", "best", "solid", "bargain",
                    "amazing", "excellent", "fantastic", "good", "perfect", "happy", "favourite", "favorite", "works",
                    "worked", "lasted", "lasts", "lasting", "years", "still", "swear", "hg", "gentle", "reliable",
                    "durable", "sturdy", "quality", "value", "worth", "nice", "awesome", "brilliant", "impressed",
                    "fine", "decent", "enjoy", "enjoyed", "helped", "improved", "game changer",
                    # What a writer went through, too (10 Oct 2026, night: a writer's decade of use without a failure).
                    # Not "failed" alone: a reviewer who failed to mention a feature says nothing about the product.
                    "decade", "decades", "never failed")
# Not "like": "features like a scale" isn't a view.

# --- Bright Data as a full source (10 Oct 2026) ---
# Noemi's request of 10 Oct 2026. `library add` can find threads with Reddit's own search through Bright Data (inside
# the request's decided subreddits) and read them through Bright Data, and `library refresh` reads through it too, so
# no single service being down or out of credits stops the library. Searches per request: up to this many (subreddit,
# title word) searches, then this many warning searches ("kettle died") in the most specialist subreddit, each listing
# up to engine.bright_data.DISCOVER_POSTS_EACH posts (1 record each). Reads cost 1 record for the post and 1 per
# top-level comment. An add never spends records needed by live checks: by default it stops this many records short
# of the monthly allowance (`--max-records N` sets its own cap).
BRIGHT_DATA_ADD_SEARCHES = 4
BRIGHT_DATA_ADD_WARNING_SEARCHES = 2
BRIGHT_DATA_ADD_RECORD_RESERVE = 300
# How `library refresh` reads the threads that are due (10 Oct 2026): Bright Data, merged into the saved copy as
# check-live does, since Parse's credits are spent; "parse" with `--reader parse`.
REFRESH_READER = "bright_data"
# Threads read together in one pair of Bright Data jobs (engine.bright_data.BrightDataClient.prefetch, 10 Oct 2026):
# one thread at a time took about 2.5 minutes, two jobs each. The docs advise up to 20 links for a quick answer.
BRIGHT_DATA_BATCH_THREADS = 20
# After Arctic Shift fails, `library add` goes straight to Bright Data for this many minutes instead of waiting about 4
# minutes for it to fail again (10 Oct 2026); then it tries Arctic Shift first again.
ARCHIVE_DOWN_MINUTES = 30

# --- Copied text (Noemi's decision 3, 11 Oct 2026) ---
# A comment that copies another writer's comment word for word is a red flag in the voice rubric ("copied text" in
# VOICE_TAGS; engine/credibility.py): its own words share at least this many words in a row with another writer's
# comment in the same thread. Chosen by Claude (a technical value, reported to Noemi): 20 words is a sentence or two.
# Writers who agree echo short phrases, not whole sentences: in the library (159 threads, 11 Oct 2026), two writers not
# answering each other shared at most 9 words in a row, apart from the one copy found, which shared 59.
COPIED_TEXT_MIN_WORDS = 20

# --- Haircare (Noemi, 11 Oct 2026) ---
# Extraction instructions that only add a category leave the other categories' extractions as they were:
# {current version: {older version: the thread categories it is still current for}}. v9 added haircare (its category
# and product types) and changed nothing else, so skincare and kitchen threads extracted with v8 aren't done again.
EXTRACT_STILL_CURRENT: dict[str, dict[str, tuple[str, ...]]] = {"extract-v9": {"extract-v8": ("skincare", "kitchen")}}

# --- Going live (Noemi, 11 Oct 2026) ---
# Noemi approved putting the demo online as a Hugging Face Space, with GoatCounter visit counts, a "First time here?"
# question and an anonymous feedback form (engine/web.py --public, engine/feedback.py, deploy/huggingface/DEPLOY.md).
# The values below were chosen by Claude to carry that out (technical values, reported to her).
# Feedback (engine/feedback.py): a comment is at most this many characters, as the page's comment box says. The request
# it is about has the search's own limit, WEB_MAX_REQUEST_CHARS, and so does the product type sent with it: module 1
# can take a product type from the request's own words, so it is never longer than a request.
FEEDBACK_MAX_COMMENT_CHARS = 1000
FEEDBACK_MAX_PRODUCT_TYPE_CHARS = WEB_MAX_REQUEST_CHARS
# A feedback request (JSON) longer than this many bytes is refused (413) before it is read: the longest real one, every
# text at its limit in a three-byte script, is about 5,000 bytes.
FEEDBACK_MAX_BODY_BYTES = 8192
# On the Space, feedback waits in memory and is uploaded to Noemi's private dataset in one batch at most once every this
# many seconds, so a click never makes a commit of its own (Hugging Face advises 5 minutes or more between such commits).
FEEDBACK_UPLOAD_EVERY_SECONDS = 300
# If uploads keep failing, at most this many records wait; past it new feedback is refused (503) instead of filling memory.
FEEDBACK_MAX_PENDING = 10000
# Public mode only (engine/web.py): each visitor, told apart by address in memory only (never stored or logged), may ask
# for RATE_LIMIT_ANSWERS answers and send RATE_LIMIT_FEEDBACK pieces of feedback in any RATE_LIMIT_WINDOW_SECONDS; more
# gets a polite "please wait" (429). Remembered answers count too. Feedback is tighter: one per answer is all a page sends.
RATE_LIMIT_WINDOW_SECONDS = 600
RATE_LIMIT_ANSWERS = 30
RATE_LIMIT_FEEDBACK = 15

# --- Time of use (11 Oct 2026) ---
# A time longer than this many years is nobody's own use of a product: "a 400 year history" is a tradition's age (a
# teapot note had the badge "400 years of use"). Chosen by Claude, reported to Noemi: a long cooking life with one pan
# (40 or 50 years, often inherited) still counts.
USE_MAX_YEARS = 60

# --- The archive's free search (11 Oct 2026, from the data builders' findings) ---
# `library add --reader archive` searched only the first 4 subreddits, for the 25 newest posts each, and a timeout in
# one ended the whole search: haircare's big threads, mostly years old, were out of reach. Its searches are free, so
# now: up to ARCHIVE_MAX_SEARCHES title searches (every decided subreddit), ARCHIVE_POSTS_EACH posts each (the most
# Arctic Shift gives), then the same searches again for posts from before ARCHIVE_OLDER_YEARS ago; a failed search is
# skipped and named, and ARCHIVE_SEARCH_MAX_FAILURES of them end the round. Chosen by Claude, reported to Noemi.
ARCHIVE_MAX_SEARCHES = 16
ARCHIVE_POSTS_EACH = 100
ARCHIVE_OLDER_YEARS = 3
ARCHIVE_SEARCH_MAX_FAILURES = 3
# 12 Oct 2026: a title search over a big subreddit's whole history timed out, one bounded by dates didn't (r/curlyhair,
# "conditioner": 35 s for the last 3 years, 11 s for the 6 before). So both rounds are bounded: the last
# ARCHIVE_OLDER_YEARS years, then back to ARCHIVE_OLDEST_FACTOR times as far (9 years).
ARCHIVE_OLDEST_FACTOR = 3

# --- Brand lines (Noemi's note of 12 Oct 2026, from testing the demo) ---
# "Are we making sure that the brand mentioned doesn't sell the product we're looking for?" Decided by Claude, as she
# asked, and reported to her: data/brand_lines.json records, from the makers' own pages, whether a brand sells a kind
# of product (engine/brand_lines.py). A brand or line name counts for a request, as the brand's whole line, when the
# list says its brand sells that kind of product, whatever its threads' clues; when the list says it doesn't, the name
# is left out with this reason ("Batiste doesn't sell shampoos": its whole range is dry shampoos). With no entry, the
# clues decide as before (BRAND_PICK_TITLE_SHARE, BRAND_PICK_NEEDS_A_PRODUCT_OF_THE_TYPE).
BRAND_LINE_NOT_SOLD = "{brand} doesn't sell {products}"
# What the page's footnote counts (Noemi asked whether its numbers were mentions or threads: they are names). The
# answer's JSON names this many of the names left out of each kind, products of another type and brand or line names,
# for the footnote to give as examples ("19 brand or line names that could mean several products, such as L'Oréal,
# Suave and Aveda"). Chosen by Claude: a handful, so the footnote stays short.
LEFT_OUT_NAMES_SHOWN = 3

# --- Also worth a look (Noemi's decision 2 of 13 Oct 2026) ---
# "Picks rule: let's follow your suggestion." The top picks keep their bar (MIN_CREDIBLE_MENTIONS across MIN_THREADS);
# products with exactly WORTH_A_LOOK_CREDIBLE credible recommendations, from at least WORTH_A_LOOK_MIN_THREADS threads,
# are shown apart, after the picks, under "Also worth a look", clearly labelled as less supported (engine/rank.py,
# engine/answer.py). The same filters as picks apply (the request's type, a score above zero, not on the skip list,
# budget, availability, hard requirements, brand lines). Up to WORTH_A_LOOK_SHOWN of them, each with up to
# WORTH_A_LOOK_QUOTES verified quotes. They never take a pick's place, and the blind test shows the picks only.
WORTH_A_LOOK_CREDIBLE = 2
WORTH_A_LOOK_MIN_THREADS = 2
WORTH_A_LOOK_SHOWN = 3
WORTH_A_LOOK_QUOTES = 2

# --- One-line summaries (Noemi's decision 4 of 13 Oct 2026: "let's do the one line summary and see how it turns out") ---
# One sentence per pick (and "Also worth a look" item) saying what its credible backers say, in our words, written
# ahead of time by Claude Code from the product's credible comments (engine/prompts/summarise_pick.md) and saved in
# data/library/summaries.json (engine/summaries.py). Code checks it before it is shown; one that fails isn't shown.
# The rules' values, chosen by Claude and reported to Noemi:
SUMMARY_MAX_WORDS = 30  # at most this many words
# A summary of a product with credible warnings must acknowledge a downside: it holds one of these words (a contrast or
# a drawback), as a whole word. A simple rule, so it can be tested; whether the downside is told faithfully is judged
# by hand (the sense evaluation).
SUMMARY_DOWNSIDE_WORDS = ("but", "though", "although", "however", "except", "downside", "downsides", "drawback",
                          "drawbacks", "complain", "complains", "complained", "complaint", "complaints", "warn", "warns",
                          "warned", "warning", "warnings", "flaw", "flaws", "problem", "problems", "issue", "issues",
                          "fault", "faults", "gripe", "gripes")
# A number followed by one of these words counts people ("two owners", "3 users"): it may be at most the number of
# comments the summary cites. Every other number must be written in one of the cited comments.
SUMMARY_PEOPLE_WORDS = ("owner", "owners", "user", "users", "people", "person", "writer", "writers", "voice", "voices",
                        "commenter", "commenters", "reviewer", "reviewers", "buyer", "buyers", "cook", "cooks",
                        "backer", "backers", "fan", "fans", "customer", "customers", "others")
