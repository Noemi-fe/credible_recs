"""Product decisions that shape the data, all in one place (docs/brief.md, version 4).

Every value here is Noemi's decision. Changing one is a deliberate product change, never a way to make
a label or a test pass: ask Noemi first. After a change, run `python -m engine.gold`; any existing label
that no longer fits is reported with its file and line.
"""

import json
from pathlib import Path

# Categories the engine ranks. A product mention can also be "other" (outside every category).
# "haircare" added on 11 Oct 2026 (Noemi: "i want to be able to ask about shampoo and receive some proper answers"):
# products put on the hair or scalp. Hair tools (dryers, straighteners) were out of scope until 14 Oct 2026.
# "general" added on 14 Oct 2026 (Noemi: "I want recs regardless of the category"; her plan's part 1): every other
# product people buy and use, from robot vacuums and headphones to hiking boots, dog harnesses and baby carriers, in
# departments (GENERAL_DEPARTMENTS below) that the page shows and that choose the communities of a product the rules
# don't list. One engine category rather than one per department, chosen by Claude (reported to Noemi): answers count
# only mentions and threads of the request's category, and the AI that reads threads can't be relied on to tell home
# from tech, or outdoor from clothing, the same way module 1 does (a robot vacuum, a rain jacket, a smart lock), so
# mentions would have been lost at those borders; inside one category the product type alone tells them apart. Still
# out of scope, each with its own polite no (engine/query.py): services, places and advice that isn't about buying;
# food and drink; medicines and supplements; books, films, music, games and apps; weapons, drugs, tobacco and vaping,
# and adult products.
THREAD_CATEGORIES = ("skincare", "kitchen", "haircare", "general")
MENTION_CATEGORIES = THREAD_CATEGORIES + ("other",)

SUBREDDITS: dict[str, tuple[str, ...]] = {
    # "acne" added by Noemi on 11 Oct 2026 (an agent had skipped r/acne threads for the acne-prone cleanser question).
    "skincare": ("SkincareAddiction", "AsianBeauty", "30PlusSkinCare", "SkincareAddictionUK", "acne"),
    # The six after "tea" added on 14 Oct 2026 with the kitchen appliances (Noemi's decision 3 of 14 Oct; chosen by
    # Claude, reported to her): appliance advice and repair (r/Appliances), and the communities of one appliance or use.
    # The last five the same day with the general category's kitchen types (chosen by Claude, reported): knife
    # sharpening, pizza ovens, and barbecues and smokers.
    "kitchen": ("BuyItForLife", "AskCulinary", "chefknives", "Cooking", "castiron", "Coffee", "espresso", "tea",
                "Appliances", "airfryer", "instantpot", "slowcooking", "Baking", "juicing",
                "sharpening", "Pizza", "BBQ", "smoking", "grilling"),
    # Chosen by Claude on 11 Oct 2026 (reported to Noemi): the science-minded and product-heavy haircare communities,
    # most general advice first.
    "haircare": ("HaircareScience", "curlyhair", "wavyhair", "Hair", "femalehairadvice", "malehairadvice", "Dandruff"),
    # The general category (14 Oct 2026). First the 32 communities of Noemi's plan for it (part 2: the ones whose
    # history she approved downloading, r/BuyItForLife being the broad one), then the specialist ones of the types
    # they don't cover well (phones, TVs, cameras, makeup, shaving, cats, cars, gardens...), chosen by Claude and
    # reported to her: searched through Arctic Shift's API when a request is read on demand, never downloaded in bulk.
    # Seven are shared with the other categories (r/Appliances, r/Coffee, hair and skin communities for hair tools and
    # deodorants): a thread read from one of them for a request takes the request's category (engine/sources.py).
    "general": (
        "BuyItForLife", "headphones", "BudgetAudiophile", "MechanicalKeyboards", "SuggestALaptop", "laptops",
        "Monitors", "HomeImprovement", "homeowners", "VacuumCleaners", "Mattress", "smarthome", "homeautomation",
        "Tools", "HomeDecorating", "Frugal", "Ultralight", "CampingGear", "onebag", "HerOneBag", "bicycling",
        "malefashionadvice", "femalefashionadvice", "frugalmalefashion", "goodyearwelt", "Boots", "RunningShoeGeeks",
        "homegym", "NewParents", "beyondthebump", "dogs", "Watches",
        # home
        "AirPurifiers", "battlestations", "candles", "CleaningTips", "hvacadvice", "laundry", "malelivingspace",
        "OfficeChairs", "Appliances",
        # 15 Oct 2026 (the general-quality builder, chosen by Claude, reported to Noemi): where people ask which
        # furniture, lamps and bedding to buy, searched before r/HomeDecorating, whose threads are mostly decorating
        # talk (sofas, armchairs, lamps, curtains, dining tables and bed sheets had got no threads from it). Each checked
        # on Arctic Shift that day: it exists and had 25 new posts in two days. Not chosen: r/InteriorDesign and
        # r/interiordecorating (room layouts), r/IKEA (one maker's products), r/femalelivingspace (the archive doesn't
        # know it).
        "furniture", "Lighting", "Bedding",
        # tech
        "3Dprinting", "4kTV", "audiophile", "buildapc", "Cameras", "DataHoarder", "drones", "HomeNetworking",
        "hometheater", "kindle", "MouseReview", "photography", "PickAnAndroidForMe", "printers", "projectors",
        "smartwatch", "vinyl", "virtualreality",
        # outdoor and travel
        "bikecommuting", "birding", "ebikes", "EDC", "ElectricScooters", "Fishing", "flashlight", "golf", "hiking",
        "Kayaking", "Paddleboarding", "whichbike",
        # 14 Oct 2026 (the routing audit, chosen by Claude, reported to Noemi): the communities of the knives that
        # aren't the kitchen's (pocket, outdoor and whittling knives)
        "knives", "Bushcraft", "Whittling",
        # clothing and accessories
        "ABraThatFits", "handbags", "rawdenim", "Sneakers", "suits",
        # 15 Oct 2026 (the general-quality builder, as for the home communities above): backpacks of every kind
        "backpacks",
        # baby and kids
        "BabyBumps", "babywearing", "CarSeats", "ExclusivelyPumping", "Mommit",
        # pets
        "Aquariums", "CatAdvice", "cats", "Dogtraining", "puppy101",
        # sport and fitness
        "bootroom", "boxing", "fitbit", "Fitness", "Garmin", "kettlebell", "powerlifting", "Rowing", "running",
        "skateboarding", "Swimming", "tennis", "xxfitness", "yoga", "Zwift",
        # tools and garden
        "gardening", "lawncare", "MechanicAdvice", "woodworking",
        # beauty and personal care
        "drugstoreMUA", "Fragrance", "MakeupAddiction", "MakeupRehab", "malegrooming", "RedditLaqueristas",
        "wicked_edge", "HaircareScience", "curlyhair", "Hair", "femalehairadvice", "SkincareAddiction",
        # hobbies
        "astronomy", "boardgames", "DigitalArt", "drums", "fountainpens", "Guitar", "notebooks", "pens", "piano",
        "sewing", "telescopes",
        # car
        "AutoDetailing", "cars", "Dashcam", "electricvehicles", "Tires",
        "Coffee",
    ),
}
# The general category's departments (14 Oct 2026; chosen by Claude, reported to Noemi; the words shown are PROPOSED,
# but for the question's, its "noun" and "examples", approved by Noemi, 19 Oct 2026):
# each product type of the category belongs to one (engine/data/product_types.json), and the page shows it above the
# answer as the other categories' names are shown. For each: the name shown ("label"), the words a question about it
# uses ("noun": "What kind of pet product are you after?") with its examples, the words that place a vague request in it
# ("hints": "something for my dog"), and the communities searched for a product of it that module 1's rules don't list,
# placed there by the open model ("communities", engine/query_model.py: an "eyelash curler"), broad ones first.
GENERAL_DEPARTMENTS: dict[str, dict] = {
    "home": {"label": "Home", "noun": "home", "examples": "a vacuum cleaner, a mattress or an air purifier",
             "hints": ("home", "house", "bedroom", "living room", "bathroom", "cleaning", "laundry", "furniture",
                       "decor"),
             "communities": ("BuyItForLife", "HomeImprovement", "homeowners", "Frugal", "HomeDecorating")},
    "tech": {"label": "Tech", "noun": "tech", "examples": "headphones, a laptop or a monitor",
             "hints": ("tech", "gadget", "gadgets", "electronics", "gaming"),
             "communities": ("BuyItForLife", "Frugal", "laptops", "smarthome")},
    "outdoor": {"label": "Outdoor and travel", "noun": "outdoor or travel", "examples": "a tent, a suitcase or hiking boots",
                "hints": ("camping", "hiking", "outdoor", "outdoors", "travel", "travelling", "traveling",
                          "backpacking", "cycling"),
                "communities": ("CampingGear", "Ultralight", "BuyItForLife", "onebag")},
    "clothing": {"label": "Clothing and accessories", "noun": "clothing", "examples": "jeans, boots or a winter coat",
                 "hints": ("clothes", "clothing", "outfit", "wardrobe", "fashion"),
                 "communities": ("BuyItForLife", "malefashionadvice", "femalefashionadvice", "frugalmalefashion")},
    "baby": {"label": "Baby and kids", "noun": "baby", "examples": "a stroller, a car seat or a baby carrier",
             "hints": ("baby", "babies", "newborn", "toddler", "infant", "kids", "pregnancy", "pregnant", "nursery"),
             "communities": ("NewParents", "beyondthebump", "BabyBumps", "BuyItForLife")},
    "pets": {"label": "Pets", "noun": "pet", "examples": "a dog harness, a crate or a litter box",
             "hints": ("dog", "puppy", "cat", "kitten", "pet"),
             "communities": ("dogs", "cats", "BuyItForLife")},
    "fitness": {"label": "Sport and fitness", "noun": "sport or fitness", "examples": "running shoes, dumbbells or a yoga mat",
                "hints": ("gym", "home gym", "workout", "fitness", "exercise", "running", "sport", "sports",
                          "lifting"),
                "communities": ("homegym", "Fitness", "BuyItForLife")},
    "tools": {"label": "Tools and garden", "noun": "tool or garden", "examples": "a drill, a lawn mower or a pressure washer",
              "hints": ("diy", "garden", "gardening", "lawn", "workshop"),
              "communities": ("Tools", "HomeImprovement", "BuyItForLife", "gardening")},
    "beauty": {"label": "Beauty and personal care", "noun": "beauty or grooming",
               "examples": "a hair dryer, a razor or a perfume",
               "hints": ("makeup", "make-up", "beauty", "shaving", "grooming", "nails"),
               "communities": ("BuyItForLife", "MakeupAddiction", "malegrooming", "SkincareAddiction")},
    "hobbies": {"label": "Hobbies", "noun": "hobby", "examples": "a guitar, a board game or a fountain pen",
                "hints": ("hobby", "hobbies", "crafts", "crafting"),
                "communities": ("BuyItForLife", "Frugal")},
    "car": {"label": "Car", "noun": "car", "examples": "a dash cam, tyres or a jump starter",
            "hints": ("car", "vehicle", "driving"),
            "communities": ("cars", "MechanicAdvice", "AutoDetailing", "BuyItForLife")},
}
# Module 1's product types beyond its first 43 (engine/query.py's own list), as data: 336 popular types of the general
# category, plus large kitchen appliances, barbecues and cooking gear, and a few haircare types (14 Oct 2026, Noemi's
# plan part 1, for the library prepared ahead in part 2; chosen by Claude, reported to Noemi). Left out on purpose,
# because they changed answers about the first types (their names would have covered words those answers read):
# body washes, body lotions and hand creams (moisturiser answers read their threads) and cookware sets (frying pan and
# skillet answers do); and curl creams (found merging main, 14 Oct 2026: a leave-in conditioner answer's "what to look
# for" names them, and a listed type's name there is another type's advice); the open model still places them.
# Each with its plural, category and department, the names people use for it, its title words and its communities.
PRODUCT_TYPES_FILE = Path(__file__).resolve().parent / "data" / "product_types.json"
MORE_PRODUCT_TYPES: tuple[dict, ...] = tuple(json.loads(PRODUCT_TYPES_FILE.read_text(encoding="utf-8"))["types"])
# Subreddits about one skin condition, {subreddit: the skin type that brings it in} (decided by Claude, 11 Oct 2026, when
# Noemi added r/acne): searched first for a request about that condition, as the most specific, and not for others.
CONDITION_SUBREDDITS: dict[str, str] = {"acne": "acne-prone"}
# The product types made for one condition (13 Oct 2026, Noemi's decision 2: spot treatments become a type): their
# condition's subreddit is searched first for them, whether or not the request names the condition ("pimple patches").
CONDITION_PRODUCT_TYPES: dict[str, tuple[str, ...]] = {"acne": ("spot treatment",)}

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
    # Added by Claude, 14 Oct 2026 (name levels; reported to Noemi): the Baratza Encore ESP is another grinder than the
    # Encore (with it in the threads, "Baratza Encore" fitted two products and b09's first pick became a line), and
    # Epiduo Forte another gel than Epiduo (a stronger adapalene).
    "esp", "forte",
    # Added by Claude, 15 Oct 2026 (the general-quality builder; reported to Noemi): the Sawyer Squeeze Micro is another
    # filter than the Squeeze, as a "mini" is another model (the camping water filter answer's Squeeze held it).
    "micro",
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
# In the wider reading a pick, and an Also worth a look item, needs a credible recommendation that talks about the
# request's needs (11 Oct 2026); in these categories it needs one in every reading (Noemi's decision 4 of 14 Oct 2026,
# morning: option B of the need-quality builder). Haircare's first reading is filled by big curly-hair threads, so its
# popular picks needn't be about what was asked: on the frozen library "gentle shampoo for wavy hair" had picked an
# anti-dandruff shampoo its writers used for a deep clean. Measured there before her decision: 2 answers change, the
# blind test's (skincare and kitchen) not at all. An empty tuple keeps the rule to the wider reading, as before.
# Skincare since Noemi's decision 3 of 15 Oct 2026 ("a bha for blackheads" had shown a microdart patch none of whose
# credible comments talk about blackheads).
NEED_RULE_IN_EVERY_READING = ("haircare", "skincare")
# The rule judges a pick by the needs a comment can talk about (engine.needs.judged_needs; 15 Oct 2026, Claude's call
# within Noemi's rule, reported to her), not by the words that say what the product is or holds: an active ingredient
# the request names, asked for (the ingredient rule checks it against the maker's list) or asked to leave out (writers
# say either way whether a cream holds it), a single letter ("w/o"), or a size, a number with one of these units or a
# unit on its own ("15ml", "28cm", "1.7 fl oz", "10 inch"). Judged by those words too, on the frozen library with
# skincare in the rule, "need an eye cream 15ml max £35" had lost its three picks, its one need being "15ml", "vitamin c
# serum under £20" a vitamin C serum whose writers call it by its name, and "moisturiser without niacinamide" had picked
# creams whose writers say they hold it.
NEED_SIZE_UNITS = ("ml", "millilitre", "milliliter", "cl", "l", "litre", "liter", "fl", "floz", "oz", "ounce", "g",
                   "kg", "lb", "lbs", "mm", "cm", "inch", "inche", "inches", "qt", "quart", "pint", "gallon")
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
# How many product types' work the answers' memory keeps (engine.memo.TypeWindow, 15 Oct 2026; Claude's call, a
# technical value): once answers have asked about more types since it last did, the site and the daily plan job forget
# what answers worked out (engine.memo.forget_answers), keeping the library and what it worked out of itself. With
# ~1,950 threads the live site had run out of memory at 2 GiB as it warmed ~480 requests, every type's work kept. 64
# holds getting ready's requests (the examples, the latency set and one request per first type: 56 types) and the
# types visitors ask next; a type asked after its work was forgotten is worked out again, a cold answer of its type.
ANSWERS_KEPT_TYPES = 64

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
# the type was shown as it is, "CeraVe cleanser" (Noemi, 9 Oct 2026); since Noemi's decision 3 of 13 Oct 2026 every
# brand line is shown so, the type said once: "CeraVe cleanser line", "Davines conditioner line" (never "CeraVe
# cleanser cleanser line"; engine.group_products.brand_pick_name).
BRAND_PICK_NAME = "{brand} {product_type} line"
# A product type as a name shows it, when that isn't module 1's lowercase name: "Le Creuset Dutch oven line".
PRODUCT_TYPE_SHOWN: dict[str, str] = {"dutch oven": "Dutch oven", "french press": "French press"}
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
    "spot treatment": "spot treatments",
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
    # Kitchen appliances (14 Oct 2026).
    "microwave": "microwaves",
    "oven": "ovens",
    "toaster oven": "toaster ovens",
    "air fryer": "air fryers",
    "blender": "blenders",
    "food processor": "food processors",
    "stand mixer": "stand mixers",
    "hand mixer": "hand mixers",
    "slow cooker": "slow cookers",
    "rice cooker": "rice cookers",
    "pressure cooker": "pressure cookers",
    "coffee maker": "coffee makers",
    "french press": "French presses",
    "toaster": "toasters",
    "waffle maker": "waffle makers",
    "juicer": "juicers",
    "kitchen scale": "kitchen scales",
}
# The types of engine/data/product_types.json (14 Oct 2026), each with its own plural, and a few shown with capitals
# ("TV", "EV charger").
PRODUCT_TYPE_PLURALS |= {entry["name"]: entry["plural"] for entry in MORE_PRODUCT_TYPES}
PRODUCT_TYPE_SHOWN |= {entry["name"]: entry["shown"] for entry in MORE_PRODUCT_TYPES if "shown" in entry}

# Decision 11, budgets (engine/prices.py). Current prices live in data/prices.json, each with its shop and the day
# Claude looked it up. PROPOSED: a price checked more than this many days ago is still shown, with its date, but
# never used to leave a product out of a budget request: it may have changed since.
PRICE_MAX_AGE_DAYS = 30

# Decision 12, names shown to a UK audience (decided by Noemi, 9 Oct 2026): {brand word: the word shown}. Sage is
# Breville's UK and EU brand; the alias list (engine/data/product_aliases.json) already treats the two as one product,
# and the answer shows the UK name. Quotes are never changed: a quote that says "Breville" keeps it.
# 15 Oct 2026 (the UK availability pass; the orchestrator's rule that a brand sold in the UK under another name follows
# this decision): Tempur-Pedic is TEMPUR outside North America (Tempur-Pedic's help page: it doesn't ship outside the
# US; tempur.com sells TEMPUR mattresses and pillows in the UK), in the four ways writers spell it.
# Aquaphor (15 Oct 2026, the second product researcher's finding, checked on eucerin.co.uk, Boots and Superdrug that
# day): sold in the UK under Eucerin, its Healing Ointment as the Eucerin Aquaphor Soothing Skin Balm. A product's UK
# name comes before its brand's, and a UK name that adds words before the brand ("Eucerin") is never added twice.
UK_BRAND_NAMES: dict[str, str] = {"Breville": "Sage", "Tempur-Pedic": "TEMPUR", "Tempur Pedic": "TEMPUR",
                                  "Tempurpedic": "TEMPUR", "Temperpedic": "TEMPUR",
                                  "Aquaphor Healing Ointment": "Eucerin Aquaphor Soothing Skin Balm",
                                  "Aquaphor": "Eucerin Aquaphor"}
# Under a pick shown by its UK name, a note says why its quotes use the other one (Claude, 10 Oct 2026). Shown as a
# note ("Note: ...") like the product-facts cautions.
OTHER_NAME_NOTE = "sold as {brand} outside the UK, so writers often call it {brand}"
# Brands as their makers write them, shown in place of writers' misspellings of them (15 Oct 2026, the general-quality
# builder, from the product researcher's list: "Phillips Avent", "Levelor", "LL Beans", "Mountain Hardware", "Simple
# Human", "Audio -Technica"; Claude's call, reported to Noemi). Answers also take a brand's spelling from the short
# names' full names (engine/data/product_aliases.json) and the brand-lines list; these are the ones neither has. A
# brand whose name is an everyday word others spell the same way is listed with its line ("Philips Avent", never a bare
# "Philips": "Phillips screwdriver" is a kind of screwdriver). engine.group_products.maker_spelling.
MAKER_SPELLINGS: dict[str, tuple[str, ...]] = {
    "general": ("Philips Avent", "Philips Sonicare", "Philips Hue", "Philips Norelco", "Philips OneBlade", "Levolor",
                "L.L.Bean", "Mountain Hardwear", "simplehuman", "Audio-Technica"),
}
# Shops that sell other makers' products under those makers' names (15 Oct 2026, the general-quality builder, Claude's
# call, reported): "Hisense model from Costco" was shown as a pick, "cotton sheets from Costco" under Also worth a look.
# Where a product was bought is no part of its name (engine.match_products.product_words drops a shop's name at a
# name's end), and a shop's name with words that name no maker of its own ("Costco sheets", "Target bath towel") names
# no one product (engine.group_products). Not here: makers that are also their own shops (IKEA, Muji, Uniqlo), shops'
# own brands (Kirkland, Great Value, Amazon Basics), Amazon (it makes the Echo and the Kindle), and the British shops
# whose name is their own brand's (Argos, John Lewis, Tesco, Aldi, Boots). Written as product_words writes them.
SHOPS = ("costco", "target", "walmart", "home depot", "lowes", "best buy", "kohls", "macys", "tj maxx", "tjmaxx",
         "marshalls", "homegoods", "sams club", "bed bath and beyond", "wayfair", "overstock", "ebay", "etsy",
         "aliexpress", "temu",
         # the second product researcher's (15 Oct 2026): Korean beauty shops ("Olive young spot treatment line"; Olive
         # Young's own patches are Care Plus's)
         "olive young", "yesstyle", "stylevana")

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
# Measured live the same day: spread over a long rest of the 10 minutes, a read waited up to 20 s and an answer 110 s.
# So spread-out reads are never slower than one every LIVE_CHECK_REFILL_SECONDS, and a read never waits more than
# LIVE_CHECK_MAX_WAIT_SECONDS for Reddit's next 10 minutes: past that its page is taken as unreadable now (its quote is
# dropped), so an answer comes back well before Cloud Run's 5-minute timeout.
LIVE_CHECK_MAX_WAIT_SECONDS = 60
# A comment whose embed page has no comment on it (a whole Reddit page instead, every time: 37 of a pre-check run's 89
# reads, 13 Oct 2026) is kept as unreadable (when, and no text) this long, so answers and the pre-check stop reading it
# again; its quote is never shown meanwhile. As long as the pre-check's PRECHECK_FRESH_HOURS, so each day's run reads
# it once. A page Reddit refused or failed on (429, 5xx, a timeout) is never kept. Decided by Claude, 13 Oct 2026.
# Since 14 Oct 2026 such a read is still known, and shared in the bundle, for 48 hours like any read (the verification
# record and the site's reads ahead need to know it was made: engine.live_check.LiveChecker.last_read); it is used for
# this long only.
LIVE_CHECK_UNREADABLE_KEEP_HOURS = 20
# Checking ahead (Noemi's decision of 13 Oct 2026: "check ahead"): the comments answers would show are read live in
# advance, daily, within the same limits (engine/precheck.py). The numbers are Claude's, reported to Noemi. A comment
# read less than PRECHECK_FRESH_HOURS ago is left as it is ("fresh for most of a day"), so after a run every check it
# covers has 28 hours or more to go: the next day's run reads it again before it runs out, even a run that is late.
PRECHECK_FRESH_HOURS = 20
# A run's budget, reads and time, whichever runs out first. Time (14 Oct 2026, Claude's call, reported to Noemi): a run
# starts no read PRECHECK_MAX_RUN_MINUTES after it started (working out the answers included), so the job's bill stayed
# inside Cloud Run's free tier however fast Reddit lets it read (with on-demand reading, at most 88% of the free
# vCPU-seconds in a 31-day month). Reads: a ceiling, about what Reddit allows in that time. On 14 Oct 2026 a run read
# its 1,100 in 46 minutes (Reddit's headers let it go faster than the refill pace) and left 459 of the 1,967 comments
# answers show or hold next in line unread; 75 minutes is about 1,700 reads. Since the free-tier redesign the same day
# the job runs the plan instead (`--plan`: the site reads ahead, below), and these bound a run that reads itself, on
# Noemi's computer say.
PRECHECK_MAX_READS = 2000
PRECHECK_MAX_RUN_MINUTES = 75
# Unlike a visitor's answer (LIVE_CHECK_MAX_WAIT_SECONDS), nobody waits on the pre-check: a read waits for Reddit's next
# 10 minutes however long that is (13 Oct 2026).
PRECHECK_MAX_WAIT_SECONDS = 660
# A run stops after this many unreadable pages in a row: Reddit is refusing reads (its allowance used from elsewhere).
PRECHECK_STOP_AFTER_UNKNOWN = 20
# Reading ahead on the site (14 Oct 2026, the coordinator's free-tier task; engine/read_ahead.py; the values are Claude's,
# reported to Noemi). A Cloud Run job is billed for its whole run, sleeping included, and two thirds of the daily run's
# 87 minutes were spent waiting for Reddit's allowance; the site is billed only while it answers, and Cloud Scheduler's
# keep-warm ping asks it every 5 minutes anyway. So the daily job only works out what to read (`python -m engine.precheck
# --plan`) and the site reads it, a few comments at each ping: at most READ_AHEAD_PER_PING, starting none
# READ_AHEAD_SECONDS after the ping began (so its worst month is about 30% of the site's free tier, and a typical one
# about 5%), READ_AHEAD_PARALLEL at once, never waiting on Reddit, and never while Reddit says fewer than
# READ_AHEAD_KEEP reads are left in its 10 minutes: those are visitors' answers' (at most about 80 of each 200 go to
# reading ahead). An answer's comment is read again once its last read is READ_AHEAD_AGAIN_HOURS old, so its check
# never runs out at 48 hours (each comment about 0.6 reads a day, against one a day for the daily run). The site looks
# for a new plan at most every PLAN_RELOAD_SECONDS, and writes what it read to the bucket's bundle at most every
# BUNDLE_SHARE_SECONDS: about two calls an hour. READ_AHEAD_PARALLEL 8 since 15 Oct 2026 (Claude, the coordinator's
# task; was 4): at 4 at once a ping read about 20 in its 5 seconds (each batch about a second on Reddit's side), 5,760 a
# day, while about 7,650 fell due (the plan's ~7,750 answers' comments every 40 hours and LIBRARY_VERIFY_READS a day);
# at 8, as many at once as an answer reads (LIVE_CHECK_PARALLEL), a ping reaches its 40: 11,520 a day, with no more of
# Reddit's reads (at most 80 of each 10 minutes' 200, as before) and no more billed seconds.
READ_AHEAD_PER_PING = 40
READ_AHEAD_SECONDS = 5
READ_AHEAD_PARALLEL = 8
READ_AHEAD_KEEP = 120
READ_AHEAD_AGAIN_HOURS = 40
PLAN_RELOAD_SECONDS = 3600
BUNDLE_SHARE_SECONDS = 3600
# The daily plan run (`--plan`): a run starts no Bright Data read this many minutes after it started (working out the
# answers takes a few), so with the job's 45-minute timeout its worst month stays well inside the jobs' free tier.
PRECHECK_PLAN_MINUTES = 30
# The open model's product types (engine.query_model) the library had threads about on 13 Oct 2026, from its request
# log (data/library/requests.jsonl, which isn't in the Cloud Run image): checked ahead by their names, like module 1's
# own types. Types the log names later are checked too wherever the log is. Since 14 Oct 2026 the air fryer, slow
# cooker, toaster, blender, food processor, rice cooker and stand mixer are module 1's own types (checked ahead as such).
PRECHECK_MODEL_TYPES = ("body wash",)
# Comments the embed page can't show ("Not supported comment", about 1 in 8), verified through Bright Data by the
# pre-check (Noemi, 13 Oct 2026: "Use Bright Data"): their threads are read as Reddit shows them now, likeliest to be
# shown first. Its free tier is 5,000 records a month, shared with the library's own reads (3,972 used by 13 Oct 2026),
# and a thread costs a record for its post and one for each top-level comment (14 for the median library thread, 49
# at the 90th percentile). So a run reads at most PRECHECK_BRIGHT_DATA_RECORDS records (estimated from the library's
# copy of each thread), in one batch of at most PRECHECK_BRIGHT_DATA_MAX_THREADS threads: at most 930 a month, under a
# fifth of the free tier. A comment verified that way is read again after PRECHECK_BRIGHT_DATA_FRESH_HOURS (every other
# daily run, just before its check runs out at 48 hours), never on the embed page meanwhile. Chosen by Claude, reported.
PRECHECK_BRIGHT_DATA_RECORDS = 30
PRECHECK_BRIGHT_DATA_MAX_THREADS = 20
PRECHECK_BRIGHT_DATA_FRESH_HOURS = 40
# Threads Bright Data couldn't read (14 Oct 2026, the coordinator: each run on Google Cloud starts with an empty disk,
# so the day's two runs chose the same two threads, failed on them, and read no other). The job remembers them in the
# bucket beside the plan (engine.precheck.BrightDataMemory): one that failed isn't asked again for
# PRECHECK_BRIGHT_DATA_SKIP_DAYS, so the run's records go to the next threads; one whose post is gone (removed, deleted,
# its page no longer there) holds comments that can't be verified that way, taken as unverifiable for
# PRECHECK_BRIGHT_DATA_GONE_DAYS (as long as a kept comment may go unverified) without a record spent on them again.
# Chosen by Claude, reported.
PRECHECK_BRIGHT_DATA_SKIP_DAYS = 7
PRECHECK_BRIGHT_DATA_GONE_DAYS = 30

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

# --- Keep only the comments answers use (Noemi, 13 Oct 2026: "Keep only comments we use"; engine/slim.py) ---
# A slimmed thread keeps its title and the comments its extraction points to, and each of them is verified on Reddit's
# embed page one by one (engine/verify.py); the thread-level rules above (14 days, monthly checks, 37 days) apply to
# whole threads only (not extracted yet, or gold-set threads). The values below were chosen by Claude, reported.
# A kept comment not verified on Reddit within this many calendar days (since its last passing read; never verified:
# since its thread was read from the archive) loses its words and its mentions. 30, as the monthly check above, inside
# Noemi's "about 37 days": the week left over covers a missed run or a deploy a few days late.
LIBRARY_VERIFY_DAYS = 30
# The kept comments verified longest ago that the daily plan asks the site to read (engine/read_ahead.py), after the
# comments answers would show. 400 a run of the daily job on 13 Oct 2026 (about 26 minutes of its run); 3,000 a day
# since 14 Oct 2026, when the site took the reads over (each about a tenth of a second of its time). Sized on a copy of
# that day's library slimmed: 17,335 kept comments, 12,356 of them never verified, read from the archive on 11 to 14 Oct
# (so due by 10 to 13 Nov), and with the 846 threads still to extract about 31,000 never verified: 11 days at 3,000 a
# day, oldest first, so a migration in late October still verifies every one in time. After that, about 36,000 kept
# comments (about 33,500 outside the answers) are each read every 12 days, well inside LIBRARY_VERIFY_DAYS.
LIBRARY_VERIFY_READS = 3000
# A kept comment verified within this many days isn't read again by that pass (the comments answers show still are,
# daily): with a library smaller than its budget, it doesn't spend reads verifying again what is a few days old.
LIBRARY_VERIFY_AGAIN_DAYS = 7
# An embed page that showed no comment ("Not supported comment") is tried again only after this many days: such a
# comment usually stays unreadable there, and each try would take a read from the comments that can pass.
LIBRARY_VERIFY_RETRY_DAYS = 10
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
# instead of paying for a new one. 20 minutes since 14 Oct 2026 (Claude's call, reported to Noemi): that day a
# 3-comment thread's comments job took 9.6 minutes on Bright Data's side, and the daily job's two reads were both cut
# off at the old 10 (on Google Cloud each run starts with an empty disk, so a job cut off is never picked up again).
BRIGHT_DATA_POLL_SECONDS = 10
BRIGHT_DATA_MAX_WAIT_SECONDS = 1200
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
    # 2026, late: b01's Stratia quote wasn't counted). Since 15 Oct 2026 (Claude, reported to Noemi) redness counts
    # only as a reaction or its absence ("no redness", "it caused redness": NEED_COMMENT_WORDS below): redness a
    # product treats isn't sensitive skin (exfoliant pads a writer used to clear bumps and redness on their underarms
    # had made them a pick for a gentle exfoliant for sensitive skin), and a request about redness asks about redness
    # itself ("azelaic acid for redness", a need found as typed).
    "sensitive": ("sensitiv", "reactive", "easily irritated", "irritated easily", "irritates easily", "irritat",
                  "rash", "sting"),
    "dry": ("dry", "dries", "dehydrated", "flaky"),
    # 15 Oct 2026 (Claude, reported to Noemi): the words skincare writers use for oily skin besides "oily" (sebum,
    # sebaceous filaments, oiliness, oil control, mattifying, greasiness): a voice saying a niacinamide serum helped
    # with sebaceous pores hadn't talked about oily skin. "oil" alone stays no word of it (a cleansing oil), and so
    # does "grease" (a kitchen request's grease splatter); "oil control sunscreen" asks for oily skin, not "oil" and
    # "control".
    "oily": ("oily", "oiliness", "oilier", "oiliest", "greasy", "greasiness", "shiny", "sebum", "sebac", "oil control",
             "oil-control", "controls oil", "control oil", "controlling oil", "mattif", "shine control"),
    "combination": ("combination", "combo skin", "t-zone", "t zone", "tzone"),  # "an oily t-zone": 15 Oct 2026
    # 15 Oct 2026 (Claude): "broke out", "breaking out", blemishes and zits too.
    # "break me out" (16 Oct 2026: "sunscreen that doesn't break me out" had a need "break").
    "acne-prone": ("acne", "breakout", "break out", "broke me out", "breaks me out", "broke out", "breaks out",
                   "breaking out", "broken out", "pimple", "blemish", "zit", "break me out", "breaking me out"),
    "normal": ("normal skin",),
    # "aging skin": 15 Oct 2026; a decade of life ("night cream for my 40s"), 16 Oct 2026 (the interview-fixes builder).
    "mature": ("mature", "anti-aging", "anti-ageing", "anti aging", "anti ageing", "aging", "ageing", "wrinkle",
               "fine line", "40s", "50s", "60s", "over 40", "over 50", "older skin"),
    # Must-haves (engine/query.py, MUST_HAVES): a comment about the thing itself talks about the need, for or against.
    "fragrance-free": ("fragrance", "unscented", "scent", "perfume"),
    "non-comedogenic": ("comedo", "noncomedogenic", "clog"),  # closed comedones are clogged pores: 15 Oct 2026
    # The cast in other colours and spellings (15 Oct 2026); "no cast" in comments only (NEED_COMMENT_WORDS).
    "no white cast": ("white cast", "white-cast", "whitecast", "purple cast", "grey cast", "gray cast", "blue cast"),
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
    # 14 Oct 2026 (need-led thread choice, Noemi's decision 3 of 14 Oct; words chosen by Claude, reported to her): a quiet
    # appliance, and a pan for a glass-top (ceramic) stove, said in the words people use. "glass" alone isn't one.
    "quiet": ("quiet", "noise", "noisy", "loud", "silent", "silence"),
    "glass top stove": ("glass top", "glass-top", "glasstop", "glass stove", "glass cooktop", "glass hob",
                        "ceramic hob", "ceramic cooktop", "ceramic top", "ceramic stove", "smooth top", "smooth-top",
                        "smoothtop"),
    # 14 Oct 2026 (the need-quality builder; words chosen by Claude, reported to Noemi): a product that isn't drying,
    # asked for after a negation ("a shampoo that isn't drying", "won't dry out my hair": NEGATED_NEEDS below). A comment
    # talks about it when it says how drying a product is, either way ("too drying", "not drying at all", "dried out
    # my ends"), or how stripping ("stripped", "stripping"); never "drying" alone, which is mostly air-drying or
    # blow-drying hair.
    "not drying": ("not drying", "isn't drying", "non-drying", "non drying", "less drying", "so drying", "too drying",
                   "very drying", "bit drying", "little drying", "pretty drying", "quite drying", "super drying",
                   "really drying", "incredibly drying", "extremely drying", "slightly drying", "kinda drying",
                   "harsh and drying", "dries out", "dried out", "drying out", "dry out", "dries my", "dryness",
                   "stripp"),
    # A product that doesn't strip ("a cleanser that won't strip my skin"): a word of the request found as typed until
    # 14 Oct 2026, a need of its own since, so a quote saying a product strips says the opposite (OPPOSITE_QUOTE_PATTERNS).
    "strip": ("strip",),
}
_SENSITIVE_IN_COMMENTS = ("no redness", "any redness", "zero redness", "without redness", "without any redness",
                          "caused redness", "causes redness", "cause redness", "causing redness", "more redness",
                          "extra redness", "increased redness", "rosacea", "eczema", "react")
# More words that show a comment talks about a need, never a thread's title or post (decided by Claude, 14 Oct 2026, b08's
# follow-up; reported to Noemi): the words people use most for something that lasts ("will last forever", "a lifetime
# pan", "for decades", "an heirloom", BIFL), which none of NEEDS' words caught, so the wider reading's need rule left out
# Field from "cast iron skillet for a beginner that will last decades", though every one of its recommendations said
# so. In a thread's title or post they tell nothing apart: nearly every r/BuyItForLife thread says them.
NEED_COMMENT_WORDS: dict[str, tuple[str, ...]] = {
    "lasting": ("forever", "lifetime", "decade", "heirloom", "bifl", "buy it for life", "for generations",
                "will last", "built to last", "should last"),
    # 15 Oct 2026 (Claude, reported to Noemi), each in comments only, so a request in these words keeps its own need:
    # redness as a reaction to the product, or its absence, the skin conditions that go with sensitive skin and "my
    # skin reacts" (a request about redness, rosacea or eczema asks about that itself, and a pan that "doesn't react
    # with tomatoes" isn't for sensitive skin); the forms of dry skin the words missed; a smell, which is a scent (but a
    # litter box that "doesn't smell" isn't a fragrance-free one); "no cast", but not "no cast iron" (NEED_LOOKALIKES).
    "sensitive": _SENSITIVE_IN_COMMENTS,
    "sensitive scalp": _SENSITIVE_IN_COMMENTS,
    "dry": ("dehydration", "flaking", "flakes", "flakey", "flakiness"),
    "fragrance-free": ("smell",),
    "no white cast": ("no cast", "any cast", "a cast", "zero cast", "without a cast"),
}
# Phrases that hold a need's word but say something else, left aside before the need's words are looked for (decided by
# Claude, 14 Oct 2026, b08's follow-up; reported to Noemi): "broke in my new cast iron" or a pan "nicely broken in" is a
# pan seasoned with its first cooks, not one that broke, as "it broke in half" or "broke in the dishwasher" is. r/castiron
# titles of that kind had counted as threads about lasting and taken first-reading places from recommendation threads.
NEED_LOOKALIKES: dict[str, tuple[str, ...]] = {
    "lasting": (r"(?<![a-z0-9])broken?\s+(?:it\s+|them\s+)?in(?![a-z0-9])(?!\s+(?:half|two|2|pieces?|three|3|parts?|"
                r"bits|the\s+(?:dishwasher|oven|sink|middle|first|second)|transit|a\s+(?:year|month|week|day)|"
                r"under|less|after|within|\d))",
                # "forever" says how long something lasts, but not in "takes forever to heat" or PFAS's "forever
                # chemicals" (non-stick threads talk about them a lot).
                r"(?<![a-z0-9])(?:takes?|took|taking)\s+forever(?![a-z0-9])",
                r"(?<![a-z0-9])forever[\s-]+chemicals?(?![a-z0-9])"),
    # "no cast" and "a cast" are no white cast, but not in "no cast iron" (15 Oct 2026).
    "no white cast": (r"(?<![a-z0-9])cast[\s-]*irons?(?![a-z0-9])",),
}
# A need asked for by saying what a product mustn't do (14 Oct 2026, the need-quality builder; chosen by Claude, reported
# to Noemi). A negation of NEGATIONS followed, at most NEGATION_REACH words later, by a word beginning with one of a
# need's words here names that need, and that word names no other need: "dry" in "a shampoo that isn't drying" or
# "doesn't leave my hair dry" isn't dry hair. A word just before a hair or skin word still describes it ("doesn't make my
# dry hair worse" is about dry hair). Only drying so far: every other need's words already say it whichever way round
# ("isn't greasy" is about greasiness, the oily need; "without frizz" the frizzy need; "doesn't leave a white cast" no
# white cast; "isn't loud" quiet), and a negation is never a need of its own (engine.sources._STOPWORDS).
NEGATED_NEEDS: dict[str, tuple[str, ...]] = {
    "not drying": ("dry", "dries", "dried"),
}
NEGATIONS = ("not", "isn't", "isnt", "aren't", "arent", "doesn't", "doesnt", "don't", "dont", "won't", "wont",
             "wouldn't", "shouldn't", "never", "no", "non", "without", "nor")
NEGATION_REACH = 3  # words between the negation and the word it negates, at most ("doesn't leave my hair dry")
# Hair types written together before "hair" each name their need (14 Oct 2026, the need-quality builder): "fine", "thin",
# "flat", "limp" and "dry" alone aren't words of their needs ("it works fine", "let it air dry"), so "shampoo for fine
# oily hair" found only the oily scalp, and "fine" became a word of its own, found in every comment saying something
# works fine. In a list ending in one of HAIR_LIST_NOUNS ("fine oily hair", "thin, greasy hair", "very fine and
# slightly oily hair") each word of HAIR_LIST_NEEDS names its need; HAIR_LIST_WORDS may sit in the list, naming none
# themselves (or named by their need's own words: "oily", "curly").
HAIR_LIST_NEEDS: dict[str, str] = {"fine": "fine hair", "thin": "fine hair", "flat": "fine hair", "limp": "fine hair",
                                   "dry": "dry hair"}
HAIR_LIST_WORDS = ("oily", "greasy", "curly", "wavy", "frizzy", "coloured", "colored", "dyed", "bleached", "damaged",
                   "brittle", "thick", "coarse", "long", "short", "straight", "natural", "porous", "low porosity",
                   "high porosity", "normal", "healthy", "very", "super", "really", "quite", "slightly", "extremely",
                   "somewhat", "kinda", "a bit", "a little")
HAIR_LIST_NOUNS = ("hair", "curls", "waves", "strands", "locks")
# A haircare request's needs (14 Oct 2026, need-led thread choice, Noemi's decision 3 of 14 Oct; words chosen by Claude,
# reported to her), in place of the skin types': a scalp is oily, hair is dry, fine or frizzy, and the words differ
# ("shiny" hair isn't greasy, a "flaky" scalp is dandruff, not dry hair). Found as NEEDS' words are: a word at the start
# of a word, a phrase whole. "fine" or "dry" alone aren't words of them: "it works fine", "I let it air dry".
HAIR_NEEDS: dict[str, tuple[str, ...]] = {
    "oily hair": ("oily", "oili", "greas", "sebum"),
    "dry hair": ("dry hair", "dry ends", "dry curls", "dry strands", "dry and", "dry,", "dry curly", "dry wavy",
                 "dry frizzy", "dryness", "brittle", "like straw", "straw-like", "dehydrat", "parched"),
    "dandruff": ("dandruff", "flak", "seborrh", "seb derm", "sebderm", "malassezia"),
    "itchy scalp": ("itch",),
    "sensitive scalp": NEEDS["sensitive"],
    "fine hair": ("fine hair", "fine strands", "fine curly", "fine wavy", "fine straight", "fine flat", "fine thin",
                  "fine and thin", "thin hair", "thin fine", "flat hair", "falls flat", "fall flat", "limp", "volum",
                  "weigh", "lifeless"),
    "frizzy": ("frizz", "flyaway", "fly-away", "fly away"),
    "curly": ("curl", "coil", "ringlet", "3a", "3b", "3c", "4a", "4b", "4c"),
    "wavy": ("wavy", "waves", "wavies", "2a", "2b", "2c"),
    "colour-treated": ("colour-treated", "color-treated", "colour treated", "color treated", "coloured", "colored",
                       "dye", "bleach", "highlight", "colour-safe", "color-safe", "colour safe", "color safe"),
}
# Other words of a request that name one of those needs: "first chef's knife", "will last decades", "lasts 10+ years".
# Module 1's "lasts 10+ years" (min_years) names "lasting" as well.
NEED_REQUEST_WORDS: dict[str, str] = {
    "first": "beginner", "last": "lasting", "year": "lasting", "decade": "lasting", "lifetime": "lasting",
    # 16 Oct 2026 (the interview-fixes builder, Claude's call, reported to Noemi): rosacea is sensitive skin (the
    # sensitive-skin rules apply: no strong or prescription-only retinoid for "retinol for someone with rosacea", which
    # had picked Differin Gel), replacing the call of 15 Oct that a request about rosacea asks about rosacea itself;
    # comments about rosacea already talked about sensitive skin (NEED_COMMENT_WORDS).
    "rosacea": "sensitive",
}
# Words of a request too common in comments to show a need: "doesn't leave a white cast", "for a home cook", and
# "burr coffee grinder" (the kind of grinder nearly every grinder comment is about); "kitchen", which nearly every
# kitchen comment says (16 Oct 2026: "wine cooler for the kitchen" had a need "kitchen"; a small kitchen is a need of
# its own, NEED_PHRASES).
NEED_IGNORED_WORDS = ("leave", "cook", "burr", "kitchen")
# Two words of a request that make one need (16 Oct 2026, the interview-fixes builder; Claude's choice, reported to
# Noemi), named whole in the reason ("about dark circles", not "about dark or circles"; "about pour over", whose "over"
# is no need word). Comments and titles are still found by each word, as before: found only as the two words together,
# readings were stricter (the espresso machine answer read fewer threads about steam wands and lost its machines with
# one). One written with a hyphen ("pour-over", "non-stick") was one word already.
NEED_PHRASES = ("non stick", "pour over", "dark circles", "dark spots", "dark marks", "dark eye circles", "back pain",
                "neck pain", "joint pain", "flat feet", "wide feet", "steam wand", "brown rice", "frozen fruit",
                "small kitchen", "small space", "home gym", "car boot", "pressure sensor", "side sleeper",
                "back sleeper", "stomach sleeper", "loose leaf", "battery life", "noise cancelling", "noise canceling")
# A recommendation saying its product didn't help with a need (15 Oct 2026, Claude, reported to Noemi; engine.needs.
# said_not_to_help): "it did nothing for my oily skin", "doesn't help redness much", "I bought it for my dark spots,
# which it didn't help with". It talks about the need, but against it, like a quote saying the opposite of the request
# (OPPOSITE_QUOTE_PATTERNS): the mention gets no credit for talking about it (never the need rule's recommendation
# about it, nor one the reason counts), and among equally clear quotes it is shown last. Only the quote's own product:
# the words before the phrase, in its clause, are none or point at it (NO_HELP_POINTERS: "it", "this one", "which it"),
# so "the other cream did nothing for my oily skin, this one did" is about another product, and its writer, who has the
# need and compared, still talks about it. A warning keeps its need: not helping is what it warns about.
NO_HELP_PATTERNS = (
    r"(?:didn't|didnt|did not|doesn't|doesnt|does not|don't|dont|do not|won't|wont|will not|wouldn't|wouldnt|never|"
    r"hasn't|hasnt|has not|haven't|havent|have not|wasn't|wasnt|was not|isn't|isnt|is not)\s+"
    r"(?:really\s+|even\s+|actually\s+|seem\s+to\s+|seemed\s+to\s+|ever\s+|quite\s+|much\s+|always\s+)?"
    r"(?:help(?:ed|s|ing)?|work(?:ed|s|ing)?\s+(?:for|on)|do\s+(?:much|anything|a\s+thing)|make\s+(?:a|any|much)\s+"
    r"difference|improve[sd]?|fix(?:ed)?|clear(?:ed)?)(?![a-z])",
    r"(?:did|does|do)\s+(?:absolutely\s+|literally\s+|basically\s+)?nothing\s+(?:for|to|about|with)(?![a-z])",
    r"no\s+(?:real\s+|noticeable\s+|visible\s+)?(?:difference|improvement|change)\s+(?:in|to|for|with)(?![a-z])",
)
# What may stand before such a phrase in its clause, when it is about the quote's own product: nothing, or one of these
# (each may follow "and", "but", "sadly"...: NO_HELP_LEADS), as the clause's last words before it.
NO_HELP_POINTERS = ("it", "this", "this one", "that", "that one", "they", "these", "those", "which", "which it",
                    "that it", "which they", "it just", "it really", "it honestly", "it sadly", "it unfortunately",
                    "it also", "it still", "it actually", "it personally", "they just", "they really", "this just")
NO_HELP_LEADS = ("and", "but", "though", "sadly", "unfortunately", "honestly", "however", "also", "personally",
                 "although", "just", "still")

# 2. Writers who contradict themselves (Noemi's rule, 9 Oct 2026). A writer who recommends a product in one comment and
# warns against it in another, in any of the request's threads, without saying something changed, counts as a low
# voice in every mention they make (so none of them is credible). Their warning says something changed when its own
# words hold one of these (word beginnings, as for needs above), or "after" a number of days, weeks, months or years
# ("after 6 months", engine/contradictions.py): an update is honest, not a contradiction.
# The groups added 15 Oct 2026 (Claude, reported to Noemi), judged one by one on the library's flagged writers (34
# writer-product pairs over the 632 requests of the evals and the pre-check): about a dozen reported a change over time
# or a failure in words the list lacked (a device fine at first that lately missed things, boots that cracked within
# months where an older pair had lasted years, a stone worn out, a newer model worse than the older one, a pot given
# away). None of the flagged pairs that were real contradictions (a downside said in another comment: too thick, too
# tight, strips colour) holds one of them. "quit" only as "quit working" or "quit on": a word beginning, it would find
# "quite".
CHANGE_WORDS = (
    "died", "broke", "stopped", "fail", "reformulat", "new formula", "change", "changing", "no longer", "anymore",
    "any more", "used to", "update", "edit", "developed a reaction", "developed an allergy",
    # Over time.
    "at first", "when i first", "when we first", "first got", "first bought", "initially", "in the beginning",
    "started", "starting to", "began", "begun", "lately", "recently", "these days", "nowadays", "over time",
    "over the years", "over the months", "over a couple", "over a few", "over the past", "eventually", "since then",
    "ever since", "after using", "after a while", "after some time", "after trying", "after a few", "after more use",
    # A failure or wear that happened.
    "cracked", "chipped", "wore out", "worn out", "wears out", "wearing out", "fell apart", "falls apart",
    "fallen apart", "gave out", "gives out", "crapped out", "craps out", "crap out", "rusted", "warped", "degrad",
    "peeled", "lasted", "leaked", "quit working", "quit on",
    # Moving on from it, or a new version of it.
    "switched", "gave it away", "got rid of", "returned it", "replaced it", "went back to", "moved on", "newer model",
    "new model", "new version", "newer version", "older model", "older version", "old version", "downhill",
    "quality went down", "quality has gone down",
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
    "prescription_only": (True, False),  # sold in the UK only on a prescription (tretinoin, Differin, Duac, Finacea)
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
    "spf": (True, False),  # a lip balm with sun protection, any SPF (15 Oct 2026, Noemi's decision 2: SPF lip balms)
}
# The facts each product type (engine/query.py, PRODUCT_TYPES) can have. Every skincare product can say whether it is
# fragrance-free, whether its maker warns against sensitive skin and, since Noemi's decision 5 of 14 Oct 2026, whether it
# is prescription-only (Duac, a clindamycin and benzoyl peroxide gel, is a spot treatment; Finacea's azelaic acid gel is
# read as a cream); only retinoids and exfoliants come in strengths. Not knowing whether a product is prescription-only
# is a requirement for retinoids and exfoliants only, the skincare mostly sold in prescription versions (the rule's
# "confirm_types" below): for every other type the fact is recorded when an official source says so and never asked
# for (10 Oct 2026: a moisturiser's "prescription_only: false" was always true and only asked researchers for busy
# work). A type not listed (a chef knife, a coffee grinder) has no facts yet.
PRODUCT_FACTS_FOR_SKINCARE = ("fragrance_free", "maker_warns_sensitive", "prescription_only")
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
    # 15 Oct 2026 (Noemi's decision 2): "with SPF" is a checked requirement of a lip balm, as PFAS-free is of a pan. A
    # sunscreen has SPF by what it is, and a moisturiser's isn't asked for, so neither has the fact.
    "lip balm": PRODUCT_FACTS_FOR_SKINCARE + ("spf",),
    "spot treatment": PRODUCT_FACTS_FOR_SKINCARE,  # 13 Oct 2026 (Noemi's decision 2)
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
    # "confirm_types" (14 Oct 2026, Noemi's decision 5): the product types for which not knowing the fact is a
    # requirement ("we couldn't confirm it's sold without a prescription"; a brand line can't be checked for it). Any
    # skincare product can have the fact; a product whose facts say it is prescription-only also shows a note wherever it
    # is shown (engine/answer.py, PRESCRIPTION_NOTE).
    "prescription only": {"asks": ("beginner", "sensitive", "gentle"), "fact": "prescription_only", "value": True,
                          "hard": True, "confirm_types": ("retinoid", "exfoliant"),
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
    # Noemi's decision 2 of 15 Oct 2026: a lip product with SPF is a lip balm, and "with SPF" is a checked requirement,
    # as PFAS-free is. Only a lip balm can have the fact, so a sunscreen or moisturiser request naming SPF asks for
    # nothing to check. Besides a facts entry from the maker's page, a lip balm's own name can say it has SPF
    # (NAME_FACT_WORDS below: "... SPF 25"). Wording PROPOSED.
    "no SPF": {"asks": ("SPF",), "fact": "spf", "value": False, "hard": True, "reason": "it has no SPF"},
}
# Words of a request that ask for something module 1 doesn't find on its own: regular expressions, found at the start
# of a word in the request (lowercased). "doesn't leave a white cast" asks for no white cast (module 1 finds only "no"
# or "without a white cast"); "without PFAS" and "PFAS-free" ask for PFAS-free; "non-stick" asks for non-stick, unless
# a word just before it says the opposite ("not non-stick", "instead of non-stick").
_NOT_REFUSED = "(?<!non-)" + "".join(f"(?<!{before} )" for before in ("no", "not", "non", "without", "without a",
                                                                         "without an", "without any", "free of"))
# 16 Oct 2026 (the interview-fixes builder, Claude's call, reported to Noemi): Teflon is PTFE, a PFAS (her rule of 11 Oct
# 2026), so refusing Teflon, PTFE or PFOA ("without teflon", "no ptfe", "teflon-free", "pfoa free") or naming forever
# chemicals asks for PFAS-free too; "a teflon pan" doesn't. Every PFAS-free pan is also free of PFOA, so reading a
# PFOA-free ask as PFAS-free only leaves out PTFE pans made without PFOA, which that shopper is most likely avoiding.
_PFAS_WORDS = r"(?:teflon|ptfe|pfoa)"
_REFUSED_BEFORE = "(?:" + "|".join(f"(?<={before} )" for before in (
    "no", "not", "non", "without", "without any", "free of", "free from", "avoid", "avoiding", "isn't", "isnt",
    "aren't", "not a", "not made with", "instead of", "rather than", "other than")) + "|(?<=non-))"
PRODUCT_FACT_REQUEST_WORDS: dict[str, tuple[str, ...]] = {
    "no white cast": (r"white cast",),
    "PFAS-free": (r"pfas", rf"{_REFUSED_BEFORE}{_PFAS_WORDS}", rf"{_PFAS_WORDS}[- ]?free", r"forever[- ]chemicals?"),
    "sulfate-free": (r"sul(?:f|ph)ate[- ]?free", r"(?<=no )sul(?:f|ph)ates?", r"(?<=without )sul(?:f|ph)ates?"),
    # 15 Oct 2026 (Noemi's decision 2): "with SPF", "spf lip balm", "lip balm with sunscreen" ask for SPF; "without
    # SPF", "no SPF" and "SPF-free" don't. It is a requirement only of the types that can have the fact (lip balms).
    "SPF": tuple(rf"{_NOT_REFUSED}{words}" for words in (r"spf(?![- ]?free)", r"sun ?screen", r"sun ?block",
                                                         r"sun ?cream", r"sun protection", r"uv protection")),
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
# listed with this reason (since Noemi's decision 1 of 13 Oct 2026 such a line is still listed under Skip these when its
# credible warnings put it there, never as a pick). The wording is shown to users: "a whole brand can't be checked for
# PFAS or a non-stick coating". HARD_REQUIREMENT_NAMES says what each hard rule checks for, in words that fit the
# sentence; several are joined with commas and a last "or".
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
    "no SPF": "SPF",  # "a whole brand can't be checked for SPF" (15 Oct 2026; wording PROPOSED)
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
# ("OXO non-stick pan": OXO sells both PTFE and ceramic pans), the pick shows a note under it: "Note: we couldn't
# confirm it's PFAS-free or that it's non-stick." Leaving such picks out would empty most answers; showing them silently
# would mislead. Until 15 Oct 2026 such a pick kept its place; since Noemi's decision 1 of 15 Oct 2026 it ranks after
# the products whose facts or name confirm the must-have, fewer unconfirmed first (engine.rank), still with its note.
# The wording is shown to users: each rule's words fit "we couldn't confirm ..."; several are joined with commas, a
# last "or", and "that" before all but the first.
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
    "no SPF": "it has SPF",  # "we couldn't confirm it has SPF" (15 Oct 2026; wording PROPOSED)
}
# What a product's own name can say about its facts (15 Oct 2026, Noemi's decision 2: "the product's name says SPF"),
# as the name it is shown under says which active ingredient it holds (INGREDIENTS above). Regular expressions, found
# at the start of a word of the name (lowercased), for the types that can have the fact (PRODUCT_FACTS_BY_TYPE): a lip
# balm named "... SPF 25", "... with sunscreen" or "UV lip 50+ PA++++" has SPF. A name saying the fact is absent ("no
# SPF", "without SPF", "SPF-free") says nothing (NAME_FACT_REFUSALS: the words are left out first). A name never says
# a fact is false, and an entry from the maker's page wins over a name: a name that says SPF never takes the entry of a
# version without it (engine.product_facts.find_facts), since a maker may sell a lip balm with and without SPF.
NAME_FACT_WORDS: dict[str, tuple[str, ...]] = {
    "spf": (r"spf", r"sun ?screen", r"sun ?block", r"sun protection", r"uv(?![a-z])", r"pa\+"),
}
NAME_FACT_REFUSALS: dict[str, tuple[str, ...]] = {
    "spf": (r"(?:no|non|without|zero)[- ](?:an? |any )?spf", r"spf[- ]free\b"),
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
                    "bundle", "strip", "guard", "sheath",
                    # 15 Oct 2026 (the general-quality builder): a pen refill is no pen ("Fisher Space Pen refill" had
                    # been a fountain pen pick)
                    "refill")

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
# Since 14 Oct 2026 (the general category) "laser" and "salon" count only as the whole type or before a treatment word:
# a laser printer, a laser level and a salon hair dryer are products ("laser treatment" and "salon visit" still aren't).
_TREATMENT = (r"(?:\s+(?:treatments?|resurfacing|therapy|facials?|toning|peels?|genesis|sessions?|hair removal"
              r"|services?|visits?|appointments?))?$")
SERVICE_TYPE_PATTERNS = (rf"laser{_TREATMENT}", r"procedures?", r"microneedling", rf"salon{_TREATMENT}", r"clinic",
                         r"in-office", r"(salon |spa )?facials?$")

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
# A product that isn't drying or stripping, and a gentle one (14 Oct 2026, the need-quality builder; chosen by
# Claude, reported to Noemi). Found on the library: "shampoo for curly hair that isn't drying" picked a detox shampoo
# and "gentle shampoo for wavy hair" an anti-dandruff one its writer used for a deep clean. A quote describing the
# product as drying, stripping or harsh says the opposite, and so does one using it as a clarifying, detox or chelating
# shampoo, or to get rid of buildup: such shampoos are made to strip the hair, used now and then, not every wash. Only
# their shampoo forms: a skincare product's name that holds the word ("COSRX AHA/BHA Clarifying Treatment Toner") says
# nothing about harshness. For these asks (OPPOSITE_NEGATED_IN_SENTENCE below), a negation among the
# OPPOSITE_NEGATION_WINDOW words before a match, in its sentence (up to "but" or "because"), takes it back: "none of
# the three ever stripped my face", "neither has ever dried my hair out", "it doesn't burn, smell or strip the skin",
# "far less harsh".
_DEGREE = (r"(?:so|too|very|really|pretty|quite|super|incredibly|extremely|kinda|kind of|a bit|a little|bit|little"
           r"|somewhat|slightly|a tad|overly)")
_BODY = r"(?:hair|skin|scalp|curls?|ends|strands|face|waves|roots)"
_WHOSE = r"(?:my|your|the|our|her|his|their)"
_DRYING = (rf"\b{_DEGREE} drying\b",  # "too drying", "pretty drying"
           r"\b(?:is|was|are|were|be|been|being|it's|its|they're|feels?|felt|harsh and)\s+drying\b",
           rf"\b(?:find|found|finds) (?:it|them|this) (?:{_DEGREE} )?drying\b",
           rf"\bdr(?:y|ies|ied|ying) {_WHOSE} (?:\w+ )?{_BODY} out\b",  # "dried my hair out"
           rf"\bdr(?:y|ies|ied|ying) out {_WHOSE} (?:\w+ )?{_BODY}\b",  # "dried out my ends"
           r"\b(?:it|this|they|that|which) (?:really |totally |completely )?(?:dries|dried) (?:\w+ )?out\b",
           rf"\b(?:left|leaves|leave|leaving|made|makes|make|making) {_WHOSE} {_BODY} (?:feel(?:ing)? )?(?:{_DEGREE} )?"
           r"(?:dry|drier|dryer|like straw|crunchy|brittle)\b")
_STRIPPING = (rf"\b{_DEGREE} stripping\b",
              r"\b(?:is|was|are|were|be|been|it's|its|they're|feels?|felt|harsh and)\s+stripping\b",
              rf"\b(?:find|found|finds) (?:it|them|this) (?:{_DEGREE} )?stripping\b",
              rf"\bstrip(?:s|ped)? {_WHOSE} (?:\w+ )?(?:{_BODY}|colou?r|oils?|moisture)\b",  # "strips my skin"
              r"\bstrip(?:s|ped)? (?:away|off|everything|all)\b",
              rf"\b(?:left|leaves|leave|leaving|made|makes|make|feels?|felt|feeling) (?:{_WHOSE} {_BODY} )?"
              rf"(?:feel(?:ing)? )?(?:{_DEGREE} )?stripped\b")
_CLARIFYING = (r"\b(?:clarifying|detox|chelating|deep[- ]clean(?:ing|sing)?|purifying) (?:shampoo|wash|poo)s?\b",
               r"\bfor clarifying\b", r"\b(?:i|to|we) clarify (?:with|once|every|weekly|monthly|twice|my|your|the)\b",
               r"\bclarif(?:y|ies|ied|ying) (?:once a|every|weekly|monthly|twice)\b",
               r"\b(?:for|to get|gives?|giving|get) (?:a |that |me a )?(?:really |good |nice |proper )?deep clean\b",
               r"\b(?:for|removes?|removing|strips?|get rid of|gets rid of|cuts? through|clears?|lifts?) "
               r"(?:all |the |my |any |of |product |hard water |mineral |silicone )*build[- ]?up\b")
_HARSH = (rf"\b(?:{_DEGREE}|is|was|are|were|it's|its|they're|feels?|felt|find it|found it) harsh\b",
          rf"\bharsh (?:on|for) {_WHOSE}\b")
OPPOSITE_QUOTE_PATTERNS["not drying"] = _DRYING + _STRIPPING + _CLARIFYING
OPPOSITE_QUOTE_PATTERNS["strip"] = _STRIPPING + _DRYING
OPPOSITE_QUOTE_PATTERNS["gentle"] = _HARSH + _STRIPPING + _DRYING + _CLARIFYING
# Haircare needs (14 Oct 2026, the same builder; asked for since then: engine.product_facts.request_asks): a shampoo for
# colour-treated hair that strips or fades the colour, or a clarifying one (it lifts dye with the buildup); for dry hair
# one that dries it; for greasy or fine hair one that leaves it greasy, heavy or flat; for frizz one that leaves more.
# Only what the product does to the writer's hair: "my roots get greasy by noon" is the need itself.
_COLOUR = (rf"\bstrip(?:s|ped|ping)? (?:{_WHOSE} |the |out )?(?:hair )?colou?r\b",
           rf"\bfad(?:e|es|ed|ing) {_WHOSE} (?:hair )?colou?r\b")
_HEAVY = (rf"\b(?:left|leaves|leave|leaving|made|makes|make|making) {_WHOSE} (?:hair|scalp|roots|curls|waves) "
          rf"(?:feel(?:ing)? |look(?:ing)? )?(?:{_DEGREE} )?(?:greas(?:y|ier)|oil(?:y|ier)|heavy|heavier|flat|limp"
          r"|weighed down)\b",
          rf"\bweigh(?:s|ed|ing)? {_WHOSE} (?:\w+ )?(?:hair|curls|waves|roots) down\b",
          rf"\b{_DEGREE} heavy\b")
_FRIZZ = (rf"\b(?:left|leaves|leave|leaving|made|makes|make|making) {_WHOSE} (?:hair|curls?|waves|ends) "
          rf"(?:feel(?:ing)? |look(?:ing)? )?(?:{_DEGREE} )?(?:frizz(?:y|ier)|puffy|poofy)\b",
          r"\b(?:more|so much|lots of|a lot of|tons of|adds?|added|extra) frizz\b",
          r"\bfrizzier\b")
OPPOSITE_QUOTE_PATTERNS["colour-treated"] = _COLOUR + _CLARIFYING
OPPOSITE_QUOTE_PATTERNS["dry hair"] = _DRYING + _STRIPPING + _CLARIFYING
OPPOSITE_QUOTE_PATTERNS["oily hair"] = _HEAVY
OPPOSITE_QUOTE_PATTERNS["fine hair"] = _HEAVY
OPPOSITE_QUOTE_PATTERNS["frizzy"] = _FRIZZ
# PFAS-free (16 Oct 2026, the interview-fixes builder; Claude's call, reported to Noemi): Teflon is PTFE, a PFAS (her rule
# of 11 Oct 2026), so a quote recommending a Teflon or PTFE pan ("just buy a cheap teflon pan", "PTFE pans are fine") or
# saying the pan is one ("the coating is PTFE", "teflon-coated") says the opposite of a PFAS-free ask (b10's Ballarini
# pick had quoted advice to buy a cheap Teflon pan); "teflon-free" and "PTFE-free" don't, nor a negation before it.
_TEFLON = r"(?:teflon|ptfe)(?![- ]?free)"
OPPOSITE_QUOTE_PATTERNS["PFAS-free"] = (
    rf"\b(?:buy|get|go with|grab|use|stick with|stick to|recommend|try|pick up|choose)\b(?:\s+[a-z']+){{0,4}}?\s+"
    rf"{_TEFLON}\b",
    rf"\b{_TEFLON}\b(?:\s+[a-z-]+){{0,2}}?\s+(?:is|are|'s)\s+(?:perfectly\s+|totally\s+|completely\s+|really\s+)?"
    rf"(?:fine|safe|great|good|ok|okay|best|the way to go)\b",
    rf"\b(?:it's|it is|they're|they are|coating is|coating's)\s+(?:a\s+|just\s+)?{_TEFLON}\b",
    rf"\b{_TEFLON}[- ]?coat(?:ed|ing)\b",
    rf"\bcoated (?:with|in) {_TEFLON}\b",
)
OPPOSITE_NEGATED_IN_SENTENCE = ("not drying", "strip", "gentle", "colour-treated", "dry hair", "oily hair", "fine hair",
                                "frizzy", "PFAS-free")
# A thread whose title asks for the opposite kind of product (14 Oct 2026, the need-quality builder): "Which clarifying
# shampoo for my curls?" is no thread about a shampoo that isn't drying, a gentle one, or one for dry or colour-treated
# hair, however much its title and post talk about curls or dryness: its answers are clarifying shampoos. The library's
# first reading reads it after every thread about the request's needs (engine.sources.LocalSource). Only the kind of
# product: a title saying a product dried someone's hair ("this shampoo is so drying, help") is about the need.
OPPOSITE_TITLE_PATTERNS: dict[str, tuple[str, ...]] = {ask: _CLARIFYING
                                                       for ask in ("not drying", "gentle", "colour-treated", "dry hair")}
OPPOSITE_NEGATION_WINDOW = 8

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

# --- Quotes coherent with their stance (Noemi's decision 4 of 15 Oct 2026) ---
# "Quotes shown must be the most significant and coherent part of the comment for the stance they back: a recommendation
# is quoted where the comment recommends (praise, how long it lasted, how it held up), a warning where it warns." Her
# example: a TV pick's first quote told of the 14 years the writer's last TV of its brand lasted before its picture went
# out, where the same comment says their current one is holding up well. So among a product's quotes, those whose own
# words carry the stance they back come first, and one whose words read against it (a recommendation's telling of a
# failure or a complaint, a warning's praising) comes after every other, before only those saying the opposite of the
# request and those leaning on the thread (engine.answer._naming_first); the words read here also find the library's
# incoherent quotes to judge (engine/quote_coherence.py). Chosen by Claude from a reading of the library's quotes
# (technical values, reported to Noemi): lowercase regular expressions, found in a quote's words, a product's own name
# aside ("Perfect Gel", "Great Barrier Relief": two or more of its words together).
# What went wrong, as the writer tells it: the product broke, died, stopped working, went out, cracked, peeled, leaked,
# wore out, was sent back; a bad reaction; a complaint ("hard to clean", "the only problem is"). Not a person dying,
# breaking a pan in, being broke, cracked lips or pepper, a failure that may come ("if it ever breaks").
QUOTE_FAILURE_PATTERNS = (
    r"\b(?:stop(?:s|ped|ping)?|quit(?:s|ting)?) (?:working|heating|boiling|charging|holding|grinding|turning on"
    r"|switching on|spinning|cooling|running|sealing|closing|locking|pumping|cutting|functioning|responding)\b",
    r"\b(?:died|dies)\b|\bdying\b(?! (?:to|for|of)\b)",
    r"\b(?:is|was|went|now|totally|completely|already|it's|its) dead\b(?! (?:simple|easy|quiet|silent|on|cent(?:re|er)"
    r"|level|straight|sharp|accurate|even|serious|set|reliable)\b)|\bdead (?:pixels?|battery|on arrival)\b|\bdoa\b",
    r"(?<!was )(?<!am )(?<!i'm )(?<!im )(?<!were )(?<!being )(?<!so )(?<!too )(?<!flat )(?<!a )\bbroke\b"
    r"(?! in\b(?! (?:about |around |only |just |under |less than )?(?:a |an |one |two |three |\d|a few |a couple )))"
    r"(?! the bank)(?! (?:college|uni|grad|student)s?\b)"
    r"(?! down and (?:i |we )?(?:bought|got|ordered|purchased|caved|splurged|found|went|picked)\b)",
    r"\bbroken\b(?! in\b)(?![- ]in\b)(?! skin\b)(?! out\b)",
    r"\b(?:it|they|this|that|which|mine|handles?|lids?) breaks\b(?! (?:everything|it|them|stuff|things|food|grease|oil"
    r"|makeup|down|up|the|in)\b)|\bbreaks (?:easily|apart|off)\b",
    r"\bfail(?:ed|s|ing)\b(?! to\b)|\bfailures?\b",
    r"\b(?:gave|gives|giving|give) out\b|\bgave up the ghost\b|\bgave up on me\b",
    r"\b(?:went|goes|going|gone) (?:out|kaput|belly up|haywire|dark|black)\b"
    r"(?! (?:and|to|of|for|there|shopping|looking|searching|today|yesterday|tonight|together|with|again|later)\b)",
    r"\b(?:crapped|conked|pooped|petered|fizzled|konked) out\b|\bbit the dust\b|\bkicked the bucket\b"
    r"|\bs(?:hat|hit) the bed\b|\bpacked in\b|\bself[- ]destruct\w*",
    r"\b(?:fell|falls|falling|came|comes|coming) (?:apart|loose|undone)\b|\bf(?:ell|alls|alling) to pieces\b",
    r"\bsnapped\b(?! (?:up|it up|them up|one up|on|off|in|into|together|shut|closed|back)\b)",
    r"\bcrack(?:ed|s|ing)?\b(?! (?:lips?|skin|heels?|hands?|feet|foot|fingers?|knuckles?|corners?|cuticles?|nipples?"
    r"|(?:black )?pepper(?:corns?)?|eggs?|open|under|and (?:bought|got|ordered|purchased|caved)|down|up|on)\b)"
    r"(?<!like crack)",
    r"\bchip(?:ped|ping)\b(?! in\b)",
    r"(?<!eyes )(?<!from )(?<!stop )(?<!stops )(?<!dry and )\bpeel(?:ed|ing)\b(?! (?:solution|gel|pads?|serum|toner|mask"
    r"|lotion|liquid|cream|ampoule|essence|eggs?|vegetables|veggies|potatoes|fruits?|apples?|carrots?|skin|lips"
    r"|on accutane)\b)",
    r"\brust(?:ed|ing|s|y)\b",
    r"\bwarp(?:ed|ing|s)\b(?![- ](?:resistant|proof|free)\b)",
    r"\bleak(?:ed|ing|s|y)?\b(?![- ]?(?:proof|free|resistant)\b)",
    r"\b(?:burn(?:ed|t)|blew|blown) (?:out|up)\b|\bblew a fuse\b|\bshort[- ]?circuit(?:ed)?\b",
    r"\b(?:wore|worn) (?:out|off|through)\b|\bwearing (?:out|through)\b|\bbrittle\b",
    r"\b(?:a|has a|have a|got a|wore a) holes?\b|(?<!vent )(?<!air )(?<!drainage )(?<!unnoticeable )(?<!hundred )"
    r"\bholes in\b(?! (?:concrete|the walls?|walls|wood|the loaf|the top|the bottom)\b)",
    r"\bpills? (?:very |so |really )?(?:easily|quickly|fast|badly|after)\b|\bpill(?:ed|ing)\b",
    r"\b(?:defective|faulty|malfunction(?:ed|ing|s)?)\b",
    r"\b(?:had|have|needed|need) to (?:be )?replace(?:d)?\b|\bneeded replacing\b",
    r"\b(?:didn't|did not|doesn't|does not|don't|do not|dont|didnt|doesnt) do (?:a |an )?(?:great|good|very good"
    r"|decent|nice) job\b"
    r"|\b(?:didn't|did not|doesn't|does not|don't|do not|never|dont|didnt|doesnt) (?:really |even )?work(?:ed|s)?\b"
    r"|\b(?:never|didn't|did not|doesn't|does not) (?:really )?do (?:anything|much|a thing)\b"
    r"|\bnever did (?:anything|much)\b"
    r"|\b(?:did|does|do) nothing\b|\b(?:can't|cannot|couldn't|could not) handle\b",
    r"\b(?:don't|doesn't|didn't|won't|wouldn't|never) (?:really |even )?last\b",
    # Sent back, regretted.
    r"\breturn(?:ed|ing) (?:it|them|mine|one|both|the)\b|\b(?:sent|took) (?:it|them|mine|one|both) back\b"
    r"|\b(?:got|get|asked for|requested) a refund\b|\brefunded\b",
    r"(?<!only )(?<!biggest )(?<!say i )\bregret(?:s|ted|ting)?\b(?! not\b)(?! waiting\b)(?![- ]free\b)(?! nothing\b)"
    r"(?! (?:getting rid|selling|giving|tossing|returning|parting)\b)",
    r"(?<!be )\bdisappoint(?:ed|ing|ment|s)?\b|\bwaste of (?:money|time|cash)\b|\ba waste\b"
    r"|(?<!made the )(?<!made a )(?<!of )\bmistakes?\b(?! of\b)",
    # Complaints.
    r"\b(?:terrible|awful|horrible|horrendous|dreadful|abysmal|rubbish|junk|pathetic|useless|flimsy|crappy|shitty)\b"
    r"(?! (?:lot|tire)\b)(?! (?:\w+[ /])?(?:acne|chapped|dryness|irritation|eczema|rosacea|dandruff|breakouts?|skin"
    r"|pimples?|lips|flakes|puller|sunburn|cystic|cracked)\b)"
    r"|\bpiece of (?:crap|junk|garbage|shit)\b|(?<!holy )(?<!with )(?<!much )\bcrap\b(?! out of\b)|\bgarbage\b(?! disposals?\b)"
    r"|\bme+h+\b|\buncomfortable\b",
    r"\bworst\b(?! (?:case|of|bout|that|we've|i've had)\b)"
    r"|(?<!would )(?<!i'd )(?<!id )(?<!who )\bhat(?:e|ed|es|ing)\b(?! to (?:see|be without|lose|give)\b)"
    r"(?! (?:when|being|feeling)\b)"
    r"|\bsuck(?:s|ed|y)?\b(?! (?:it |them |everything |anything |all )?(?:up|out|in|away|on)\b)(?! like a champ\b)"
    r"|(?<!my )\bbad\b(?![- ]?ass)(?! boys?\b)(?! (?:\w+ )?(?:acne|rosacea|eczema|skin|breakouts?|dandruff|dryness"
    r"|flak\w+|sunburns?|feet|knees?|backs?|habits?|weather|winters?|roads|sidewalks)\b)",
    r"\b(?:shit|crap|crappy|shitty|poor|low|cheap|bad|terrible|awful) quality\b|\bpoorly (?:made|built|designed)\b"
    r"|\bcheaply made\b|\b(?:poor|bad|terrible|awful|horrible) (?:experience|customer service|service|support)\b",
    r"\b(?:downsides?|drawbacks?)\b|\b(?:the )?(?:only )?(?:problem|issue|complaint) (?:is|was)\b"
    r"|\b(?:have|had|having|has) (?:some |a few |many |lots of |a lot of |constant |so many )?(?:issues?|problems?"
    r"|trouble)\b|\b(?:many|so many|lots of|a lot of|constant|endless|numerous) (?:issues|problems)\b"
    r"|\b(?:would|will|always|kept|keep|constantly|often|regularly) blow(?:ing)? out\b|\b(?:hard|difficult|a pain|impossible) to (?:clean|use|open|close|remove|wash)\b",
    r"\b(?:don't|didn't|do not|did not|dont|didnt|never) (?:really )?like[sd]?\b"
    r"|\b(?:couldn't|could not|didn't|did not|don't|do not) care for\b",
    r"\b(?:changed|ruined) (?:the|their|its) formula\b|\breformulat\w+|\bused to (?:be |love|like)"
    r"|\bused to (?:work|do) (?:great|well|fine|perfectly|for me|wonders|so well|really well)\b",
    r"\bswitch(?:ed|ing) (?:away )?from\b(?![^.!?;]*\bto\b)",
    r"\bleast (?:favou?rite|impressed)\b|\bunimpressed\b|\bf(?:allen|ell) out of love\b",
    # Bad reactions (skincare, haircare). Not breakouts or irritated skin alone: they are what a request can be about.
    r"\bbr(?:oke|eaks?|eaking) (?:me|my skin|my face) out\b|\bmade me break out\b|\bclogged (?:my )?pores\b"
    r"|\b(?:caused|causes|causing) (?:breakouts?|a rash|irritation|milia)\b"
    r"|\b(?:gave|gives|giving) me (?:a )?(?:rash|hives|bumps|breakouts?|milia|cystic acne|a reaction|dermatitis)\b",
    r"\b(?:irritated|irritating|burned|burnt|stung|stings|itchy|itched) (?:my|me)\b|\ballergic reaction\b"
    r"|(?<!minimal )(?<!little )(?<!barely any )(?<!very little )\bwhite cast\b"
    r"|\b(?:constant|frequent|so many|lots of|tons of|multiple|several|daily|endless|non-?stop|always|more) blow ?outs?\b"
    r"|\bblow ?outs? (?:every|with every|all the time|constantly|daily|each)\b"
    r"|\b(?:had|have|having|get|got|getting) (?:a )?blow ?outs?\b(?! (?:pouch|pocket|flap|protection)\b)",
)
# Advice against it.
QUOTE_ADVICE_AGAINST_PATTERNS = (
    r"\bavoid (?:it|them|this|that|these|those|at all costs|like the plague)\b|\b(?:i'd|i would|you should|definitely"
    r"|strongly) avoid\b|\b(?:steer clear of|stay away from)\b",
    r"(?<!if you )\b(?:don't|do not|never|wouldn't|would not|won't) (?:buy|get|bother with)\b"
    r"(?! (?:another|anything else|any other|others|a different|better|much better|any better|rid|to)\b)"
    r"(?! (?:\w+ )?without\b)",
    r"\b(?:wouldn't|would not|don't|do not|can't|cannot|won't|couldn't|could not|never) recommend\b"
    r"(?! (?:\w+ ){0,4}?(?:enough|highly enough)\b)(?! (?:it |them |this |these )?more\b)"
    r"|\brecommend (?:not|against|avoiding)\b",
    r"\bnot (?:worth|recommended)\b|\bover(?:rated|hyped|priced)\b|\bskip (?:it|this|them|that|the)\b"
    r"(?! (?:first|second|third|next|last|extra|whole|steps?|line|queue|hassle|wait|middle ?man|fancy|trendy|expensive"
    r"|useless|cheap|cheaper|plastic|gimmicky)\b)|\bsave your (?:money|cash)\b",
    r"\b(?:not sure|unsure) (?:if |that |whether )?i(?:'d| would)? recommend\b"
    r"|\b(?:can't|cannot) say i(?:'d| would)? recommend\b",
    r"\b(?:recommend|suggest|get|buy|go with|choose) (?:a different|something else|something different)\b",
)
# Praise, how it held up, and endorsements. Not how long it lasted alone ("we had it 14 years"): a long life ending in
# a failure reads as the failure (Noemi's example). Not a wish ("I'd love to try it", "I wish mine held up this well").
QUOTE_PRAISE_PATTERNS = (
    r"(?<!would )(?<!i'd )(?<!you'd )(?<!out of )\blov(?:e|ed|es|ing)\b(?! to (?:know|hear|see|try|get|have|find|own|buy)\b)"
    r"|\blovely\b",
    r"\bgreat\b(?![- ]?grand)(?! deal\b)(?! many\b)",
    r"\b(?:really|very|so|pretty|super|incredibly|quite|damn|darn) good\b"
    r"|\bgood (?:quality|value|buy|purchase|investment|choice|stuff|product|one|ones)\b"
    r"|\b(?:is|are|it's|its|they're|was|were) (?:very |really |so |pretty )?good\b",
    r"(?<!at )\bbest\b(?! (?:way|practice|of luck|guess|case|before|by)\b)",
    r"(?<!sure i would )(?<!sure i'd )(?<!say i would )(?<!say i'd )(?<!sure i )(?<!say i )\brecommend(?:ed|s|ing)?\b",
    r"\b(?:excellent|amazing|fantastic|awesome|brilliant|superb|outstanding|wonderful|incredible|phenomenal|stellar"
    r"|terrific|exceptional|flawless(?:ly)?|perfect(?:ly)?|solid|sturdy|durable|reliable|dependable|robust|effective"
    r"|invincible)\b",
    r"\bwell[- ](?:made|built|designed)\b|\bbuilt like a tank\b|\bindestructible\b|\bbulletproof\b"
    r"|\ba (?:beast|tank|workhorse)\b|\bworkhorse\b",
    r"\b(?:a (?:big |huge |massive )?|such a (?:big |huge )?|big |huge |massive |biggest )fan\b(?! (?:blades?|motor|noise"
    r"|speed|setting|would|that|inside"
    r"|of (?:the|their|this) (?:idea|concept))\b)|\bfans? of\b(?! (?:the|their|this) (?:idea|concept)\b)"
    r"|\bage[sd]? well\b|\bholy grail\b|\bhg\b|\bswear by\b|(?<!least )\bfavou?rites?\b|\bgo[- ]to\b|\bgame[- ]?changer\b",
    r"\b(?:happy|pleased|satisfied) with\b|(?<!least )\bimpress(?:ed|ive)\b|\bhappy\b(?! (?:to|birthday|accident)\b)"
    r"|\bhappier\b|\bso far,? so good\b|\b(?:couldn't|could not|can't|cannot) be (?:any )?(?:more )?(?:happier|happy|pleased"
    r"|satisfied)\b|\bnothing short of (?:amazing|perfect|perfection|incredible|excellent|fantastic|brilliant|great|awesome"
    r"|phenomenal|stellar|a (?:miracle|dream))\b"
    r"|\b(?:buy|bought|give|gave|gift|gifted) (?:them|it|one|these|those) (?:as|for) (?:a )?(?:gifts?|presents?"
    r"|wedding presents?|christmas presents?|birthday presents?)\b",
    r"\bworth (?:it|every|the (?:money|price|cost|investment|splurge|extra)|a (?:try|shot|look))\b",
    r"\b(?:would|will|i'd|i'll) (?:buy|get|purchase) (?:it |them |one |another |this )?again\b"
    r"|\bbought (?:another|a second|two more|the same|a backup|a spare|a replacement of the same)\b"
    r"|\brepurchas\w+\b|\bre-?bought\b|\bon my (?:second|third|fourth|fifth|sixth|\w+th) (?:bottle|tube|jar|tub|one)\b"
    r"|\b(?:will|would|'ll|'d|i'll|i'd|we'll|we'd) (?:\w+ )?(?:buy|purchase|get) another\b",
    r"\bstill (?:going|works|working|kick(?:s|ing)?|alive|running|in use|use (?:it|them|mine)|using (?:it|them|mine)"
    r"|have (?:it|them|mine)|has (?:it|them)|looks? (?:new|great|good|brand new|amazing)|holding up|holds up"
    r"|my (?:go-?to|favou?rite|daily)|the best|love)\b",
    r"\b(?:held|holds|holding) up\b|\bgoing strong\b|\bstood the test of time\b|\b(?:as good as|like|as \w+ as) "
    r"(?:brand )?new\b|\blast(?:s|ed)? (?:forever|a lifetime|for ever|for ages|ages|a (?:really |very )?long time)\b"
    r"|\btakes? a beating\b|\bstill (?:looks|doing its job|does its job|does the job)\b"
    r"|\bstill feels? (?:new|like new|brand new|great|good|amazing|solid|sturdy|soft|nice)\b|\boutlast(?:ed|s|ing)?\b"
    r"|\b(?:always|keep|kept|still) (?:go|going|went|come|coming|came) back to\b|\bwork(?:s|ed)? (?:for me|for us|on me)\b",
    # What didn't go wrong, said in one go ("won't break", "never had a single issue", "not a single one has died").
    r"\b(?:won't|wont|doesn't|doesnt|don't|dont|didn't|didnt|never|can't|cant|hasn't|hasnt|haven't|havent) "
    r"(?:ever |once )?(?:break(?! in\b)|crack|chip|rust|warp|leak|peel|fail|die|wear out|fall apart|let (?:me|us) down)\b",
    r"\bnever (?:failed|let me down|disappointed|had (?:a|an|any) (?:issues?|problems?|complaints?))\b"
    r"|\bnever (?:once )?had (?:it|one|them|mine) (?:fail|break|crack|die|leak|rust|warp|chip|peel)\b"
    r"|\b(?:can't|cannot|cant) imagine (?:it|them|one) (?:ever )?(?:failing|breaking|dying|wearing out)\b",
    r"\b(?:no|zero|without (?:a|an|any)|not (?:a|one)|haven't had (?:a|an|any)|have not had (?:a|an|any)"
    r"|never had (?:a|an|any)) (?:single )?(?:issues?|problems?|complaints?|trouble|regrets|leaks?|blow ?outs?|rust"
    r"|cracks?|chips?)\b"
    r"|\bnone of (?:them|mine|ours|the \w+) (?:have|has|ever|had) (?:ever )?(?:broken|broke|died|failed|burned out"
    r"|burnt out|cracked|leaked|rusted|warped|worn out)\b",
    r"\bnot (?:a |one )?(?:single )?(?:one )?(?:of them )?(?:has |have |had )?(?:ever )?(?:died|failed|broken|broke"
    r"|cracked|leaked|rusted|warped)\b",
    r"\b(?:can't|cannot|can not) (?:go wrong|beat|best|fault)\b|\bhard to beat\b|\bwon't regret\b|\bsuccess(?:ful)?\b",
    r"\bnever (?:buy|get|need|want|use|look at) (?:another|anything else|any other|others|a different)\b"
    r"|\b(?:won't|wont|will not) (?:buy|get|use|need) (?:another|anything else|any other|others)\b"
    r"|\bnever (?:get rid of|part with|go back(?! to\b))\b",
    r"\b(?:can't|cannot|can not) recommend (?:\w+ ){0,4}?(?:enough|highly enough)\b"
    r"|\b(?:can't|cannot|can not) recommend (?:it |them |this |these )?more\b"
    r"|\b(?:won't|wont|will not|wouldn't|would not|can't|cannot) (?:get|find) (?:any |much )?better\b"
    r"|\b(?:won't|wont|wouldn't|wouldnt|will not|would not|never|not) be disappointed\b"
    r"|\b(?:don't|dont|do not) think (?:you'?d|you would|you'?ll|you will) be disappointed\b",
    r"\bbetter than\b|\b(?:so|much|way|far|a lot|miles) better\b|\bhelped\b"
    r"|\bnothing (?:else )?(?:beats|compares|comes close)\b|\bnothing (?:\w+ )?better\b"
    r"|\bnothing else (?:has )?(?:works?|worked|helps?|helped|does it)\b|\bthere(?:'s| is) no better\b"
    r"|\bno better \w+ than\b"
    r"|\bsaved my (?:skin|life|lips|hair|face|hands|feet)\b|\blife ?saver\b|\bhands down\b|\b(?:is |are )?the goat\b"
    r"|\bquality (?:product|stuff|build|item|piece)\b|\bcomfortable\b|\bcomfy\b|\bcute\b"
    r"|\b(?:switched|switching|upgraded|moved) to\b|\b(?:stick|stuck|sticking|sticks) with\b"
    r"|\b(?:never|don't imagine|can't imagine|doubt) (?:i'll|i will|i'd|i would) (?:ever )?(?:buy|need) another\b",
    r"\bwork(?:s|ed)? (?:well|great|perfectly|fine|wonders|like a charm|a treat|beautifully|flawlessly|really well"
    r"|so well)\b"
    r"|\bdoes (?:the job|what it says)\b|\bgets the job done\b",
    r"\bthe way to go\b|\bstands? (?:by|behind) (?:their|its|it|them|the|our)\b|\bno questions asked\b"
    r"|\beasy to (?:clean|use|maintain|repair|fix|care for|sharpen|assemble|set up)\b|\beasy (?:fix|repair)\b"
    r"|\bsaviou?r\b|\bcured (?:my|it|the|her|his)\b|\bheal(?:ed|s)\b(?! me\b)"
    r"|\bclear(?:ed|s) (?:it |them |my (?:\w+ )?(?:skin|acne|face|breakouts?) )?up\b"
    r"|\bgot rid of (?:my|the|all (?:of )?my) (?:\w+ )?(?:acne|breakouts?|dandruff|eczema|flakes|frizz|redness|itch\w*"
    r"|dryness|pimples?|spots|blackheads|smell|odou?r|fleas|stains?)\b|\bnot once (?:has|did|have) (?:it|they|mine)\b|\blast(?:s|ed)? (?:much |way |a lot |far )?longer\b"
    r"|\bmade (?:a |such a )?(?:huge|big|massive|noticeable|real|significant) difference\b|\ba world of difference\b"
    r"|\b(?:would|i'd|id) (?:really )?hate to (?:be without|lose|give up|part with)\b"
    r"|\bregret(?:ted)? (?:getting rid of|selling|giving (?:it |them )?away|tossing|returning|parting with)\b"
    r"|\bregret[- ]free\b|\bregret nothing\b|\b(?:can't|cannot) say i regret\b"
    r"|\breplaced (?:it|them|mine) with (?:the same|another)\b",
    r"\b(?:really|very|so|super|pretty) nice\b|\bi like[sd]?\b(?! to\b)|\bi (?:really|also|still|do|just|absolutely"
    r"|honestly|actually|genuinely|personally|definitely|quite|kinda|kind of) like[sd]?\b(?! to\b)"
    r"|\benjoy(?:ed|ing|s)?\b",
    # An endorsement: "Get the Zojirushi", "..., just buy a Lodge", "you should go for the C2".
    r"(?:^|[.!?,;:]\s+|\b(?:just|definitely|so|then|i'd|i would|you should|you could|you'll want to|i'd say))\s*"
    r"(?:get|buy|grab|go for|go with|pick up)\b(?! (?:something|a different|anything|one with)\b)",
)
# A negation among this many words just before a match, in its part of the sentence, takes it back ("never broke",
# "isn't worth it"), or this many twice over when the words between hold "or", "nor" or "and" ("didn't chip, crack or
# warp"), not counting "ever", "even", "once", "really" and the like ("barely ever had leaks"). The part ends at a full
# stop, a semicolon, "but", "though", "because", "until", "then"..., or a comma before a new subject ("Not Ring, it's
# junk"). Two words: wider windows took back what a negation before them said of something else ("I don't like how
# low quality it is").
QUOTE_STANCE_NEGATION_WINDOW = 2
# Before "died" or "dies", one of these among the two words just before makes it someone's death, not the product's.
QUOTE_STANCE_PEOPLE_WORDS = ("grandma", "grandpa", "grandmother", "grandfather", "grandparents", "granny", "gran",
                             "nan", "nana", "mother", "father", "mom", "mum", "dad", "parent", "parents", "aunt",
                             "uncle", "husband", "wife", "partner", "friend", "brother", "sister", "son", "daughter",
                             "neighbor", "neighbour", "dog", "cat", "he", "she")

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
# v10 (13 Oct 2026, Noemi's decision 2) only added the "spot treatment" type's name to the list the AI types products
# with, so every v9 extraction stays current (the AI had typed pimple patches in plain words, "pimple patch", which the
# spot treatment type's words find), and v8 ones of skincare and kitchen threads, as under v9.
# v11 (14 Oct 2026, Noemi's decision 3: kitchen appliances as product types) only added the appliances' names, and how
# their usual kinds are typed, to that list: the AI had typed appliances in plain words ("air fryer", "rice cooker",
# "multicooker", "air fryer oven"), which module 1's names and words find, so every v10 and v9 extraction stays current,
# and v8 ones of skincare and kitchen threads.
# v12 (14 Oct 2026, Noemi's "recs regardless of the category") adds the general category, so a product outside skincare,
# haircare and kitchen gear is "general" rather than "other", and lists module 1's new types. The three categories'
# threads were read for their own products, and their answers rank their own category's mentions only, so whether a
# laptop in a kettle thread was "other" or "general" changes nothing: their v11, v10 and v9 extractions stay current
# (v8 ones of skincare and kitchen threads too); a general thread is extracted with v12. Decided by Claude, reported.
_BEFORE_GENERAL = ("skincare", "kitchen", "haircare")
EXTRACT_STILL_CURRENT: dict[str, dict[str, tuple[str, ...]]] = {
    "extract-v9": {"extract-v8": ("skincare", "kitchen")},
    "extract-v10": {"extract-v9": _BEFORE_GENERAL, "extract-v8": ("skincare", "kitchen")},
    "extract-v11": {"extract-v10": _BEFORE_GENERAL, "extract-v9": _BEFORE_GENERAL,
                    "extract-v8": ("skincare", "kitchen")},
    "extract-v12": {"extract-v11": _BEFORE_GENERAL, "extract-v10": _BEFORE_GENERAL, "extract-v9": _BEFORE_GENERAL,
                    "extract-v8": ("skincare", "kitchen")},
    # v13 (14 Oct 2026, the routing audit) only adds the names of module 1's new types (the kitchen's paring, bread and
    # carving knives, cleavers, pepper grinders, baking trays, bread makers...; the general category's pocket, outdoor,
    # whittling and craft knives, box cutters and camping cookware) to the list the AI types products with. The AI had
    # typed them in plain words ("paring knife", "bread maker", "pocket knife") that those types' names find, so every
    # v12 extraction stays current, general threads' too, and the older ones as under v12. Decided by Claude, reported.
    "extract-v13": {"extract-v12": THREAD_CATEGORIES, "extract-v11": _BEFORE_GENERAL, "extract-v10": _BEFORE_GENERAL,
                    "extract-v9": _BEFORE_GENERAL, "extract-v8": ("skincare", "kitchen")},
    # v14 (15 Oct 2026, Noemi's decisions 2 and 5 of 15 Oct) adds two rules. A product for the lips with SPF is a "lip
    # balm", not a "sunscreen" (lips are an exception to her 9 Oct rule "sun protection wins over the form"), and a
    # warning resting only on a maker's ethics (animal welfare, labour, politics, a boycott) is no mention. Both are
    # brought to the older extractions by command rather than by extracting the library again: `python -m
    # engine.lip_balms retype` re-types the lip products typed sunscreen, judged by their names, and the ethics-only
    # warnings were found by keyword and judged one by one (`python -m engine.ethics candidates`, then `apply`). So
    # every v13 extraction stays current, of all four categories (three extractors were writing v13 files when v14
    # came), and the older ones as under v13. Decided by Claude, reported.
    "extract-v14": {"extract-v13": THREAD_CATEGORIES, "extract-v12": THREAD_CATEGORIES,
                    "extract-v11": _BEFORE_GENERAL, "extract-v10": _BEFORE_GENERAL, "extract-v9": _BEFORE_GENERAL,
                    "extract-v8": ("skincare", "kitchen")},
    # v15 (15 Oct 2026, Noemi's decisions 2 and 4 of that afternoon) adds two rules: a recommendation resting only on a
    # maker's ethics, eco claims, identity or origin is no mention, as an ethics-only warning isn't; and a quote carries
    # its mention's stance (a recommendation quoted where the comment recommends, a long-life failure for its long life,
    # a warning where it warns). Both are brought to the older extractions by command, judged one by one, rather than by
    # extracting the library again: `python -m engine.ethics candidates --stance recommend`, then `apply`, and `python -m
    # engine.quote_coherence candidates`, then `apply`. So every v14 extraction stays current, of all four categories,
    # and the older ones as under v14. Decided by Claude, reported.
    "extract-v15": {"extract-v14": THREAD_CATEGORIES, "extract-v13": THREAD_CATEGORIES,
                    "extract-v12": THREAD_CATEGORIES, "extract-v11": _BEFORE_GENERAL, "extract-v10": _BEFORE_GENERAL,
                    "extract-v9": _BEFORE_GENERAL, "extract-v8": ("skincare", "kitchen")},
}

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
# skipped and named, and ARCHIVE_SEARCH_MAX_FAILURES of them end the round (in a row since 13 Oct 2026: a busy archive
# fails some searches and answers others; one that is down fails every one). Chosen by Claude, reported to Noemi.
ARCHIVE_MAX_SEARCHES = 16
ARCHIVE_POSTS_EACH = 100
ARCHIVE_OLDER_YEARS = 3
ARCHIVE_SEARCH_MAX_FAILURES = 3
# 13 Oct 2026 (the data round): Arctic Shift timed out on half the searches for "shampoo" over 3 years in the big
# haircare subreddits, round after round, and answered one over the last year in 14 s. A search that times out is asked
# again as the two halves of its span (an undated one as the two windows above): the newer half of its first timeout right
# away, every other half at the end of the round, so one search that times out over any span can't end the round. At
# most this many halvings: then it counts as failed. Chosen by Claude, reported to Noemi.
ARCHIVE_SPLIT_DEPTH = 2
# 13 Oct 2026 (the data round): Arctic Shift answers the newest 100 posts of a title search, so "conditioner" over 3 years
# in r/curlyhair finds the last few months of small posts, and the threads asking a request's exact question ("best
# conditioner for curly hair?", often years old and big) stayed out of reach. The archive's round also searches the
# product's title word with each of the request's first ARCHIVE_NEED_WORDS need words ("conditioner curly"), in each of
# its subreddits, over the whole history: few posts match both. Chosen by Claude, reported to Noemi.
ARCHIVE_NEED_WORDS = 2
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

# --- Name levels: a brand, its line and its products (14 Oct 2026; engine/group_products.py, engine/pipeline.py) ---
# Decided by Claude, as the orchestrator asked, and reported to Noemi. A name made of a brand and only the requested
# type's words says no more than the brand in that type: it is the brand's line, never one of its products ("Victorinox
# chef knife", "Sage kettle"; the 10 and 12 Oct rules for price and facts entries under a brand's name already read such
# names so). The type's words are its name and plural; these are the other words writers use for a type, as whole
# phrases (a plural too), found among the library's names of products of the type on 14 Oct 2026. b08 had lost its
# Lodge pick to a writer's "lodge cast iron pan", taken for a Lodge product the Lodge line stepped aside for. Only words
# that never tell a brand's products of the type apart: not a kind within the type ("non-stick pan", "night cream",
# "vitamin c serum": a brand's niacinamide serum is often its one product), nor a form ("gel", "cream", "lotion").
TYPE_SYNONYMS = {
    "cast iron skillet": ("pan", "frying pan", "fry pan"),
    "frying pan": ("skillet", "fry pan"),
    "saucepan": ("pot", "pan", "sauce pan"),
    "dutch oven": ("pot", "casserole", "cocotte"),
    "electric kettle": ("tea kettle",),
    "chef knife": ("kitchen knife",),
    "coffee grinder": ("burr grinder", "hand grinder", "manual grinder"),
    "espresso machine": ("espresso maker", "coffee machine"),
    "slow cooker": ("crock pot", "crockpot"),
    "pressure cooker": ("multicooker", "multi cooker"),
    "air fryer": ("airfryer",),
    "sunscreen": ("sun cream", "suncream", "sunblock", "sun screen", "spf"),
    "spot treatment": ("patch", "sticker", "dot", "pimple patch", "acne patch", "zit patch", "blemish patch",
                       "spot patch", "hydrocolloid patch", "pimple sticker", "acne sticker", "spot gel", "spot cream"),
    "cleanser": ("face wash", "facial wash", "facial cleanser", "wash"),
    "eye cream": ("eye serum", "under eye cream"),
    # The general category's (15 Oct 2026, the general-quality builder; Claude's call, reported to Noemi): the American
    # names its mostly American writers use for types named the British way, and plain other names, each found among the
    # library's names of the type after two or more brands, most after three or more ("Viair compressor" beside the
    # Viair 88P, "Portland Leather Co bag" beside its handbag line). Kinds within a type stay out ("tote", "parka").
    "jumper": ("sweater",),
    "trousers": ("pants",),
    "washing machine": ("washer",),
    "handbag": ("bag", "purse"),
    "t-shirt": ("tee", "tshirt"),
    "nappies": ("diaper",),
    "barbell": ("bar",),
    "sofa": ("couch",),
    "duvet": ("comforter",),
    "hair straightener": ("flat iron",),
    "security camera": ("camera", "cam"),
    "tyre inflator": ("compressor", "air compressor"),
    "smoke alarm": ("smoke detector",),
    "baby sleeping bag": ("sleep sack",),
    "changing bag": ("diaper bag",),
    "wellies": ("boots",),
}

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

# --- Active ingredients (13 Oct 2026; engine/ingredients.py) ---
# The orchestrator's decision of 13 Oct 2026, after Noemi tested the live site ("when I put salicylic acid, it should
# give me like a serum, not an exfoliant": "salicylic acid for acne" was read as an exfoliant request, and its answer
# showed exfoliants without the acid). When a request names an active ingredient, the answer is ingredient-led: every
# product it shows (picks, Also worth a look, Skip these) contains that ingredient, and the ingredient is a hard
# requirement like the product facts' ones. A request that names a product type too ("salicylic acid cleanser") keeps
# its type and adds the requirement; one that names only the ingredient ("salicylic acid for acne") reads the skincare
# threads of every product type that can carry it, and each product shown says its form ("pads", "toner", "cleanser").
# The list below was chosen by Claude (the builder), reported to Noemi. Each ingredient, by its key (the name shown):
# - "asked": how a request names it: regular expressions, matched on whole words of the lowercased request (a plural
#   "s" may follow). A request's "no X", "without X", "X-free", "instead of X" (and the like) doesn't ask for it;
# - "named": how a product's own name shows it contains it (whole words, as above): "Paula's Choice 2% BHA" names a
#   BHA. Stricter than "asked" where it must be: a BHA in a name isn't proof of salicylic acid (COSRX's BHA is betaine
#   salicylate), so salicylic acid is only "salicylic";
# - "actives": the actives of a product-facts entry's formula that count for it (data/product_facts.json, "formula";
#   the vocabulary is INGREDIENT_ACTIVES below): a BHA is salicylic acid or betaine salicylate;
# - "types": the product types (engine/query.py, PRODUCT_TYPES) that can carry it, read for an ingredient-led request;
# - "related" (optional): other ingredients whose words also show a thread talks about it, for choosing threads (a
#   thread about BHAs is about salicylic acid too), never as evidence;
# - "facts_types" (optional): more product types that can carry it, whose products count only when their facts entry's
#   formula lists it (engine.ingredients.facts_types; 14 Oct 2026).
# The retinoid words that are module 1's own name for the retinoid type ("retinol", "retinoid") add no requirement:
# Noemi decided on 7 Oct 2026 (eval/edge_cases/query.json, q05) that "retinol" means the generic retinoid, so the type
# already is the requirement. The specific forms ("retinal", "tretinoin", "adapalene", "tazarotene") are required.
_ACID_TYPES = ("exfoliant", "toner", "serum", "cleanser", "moisturiser", "spot treatment")
_SOOTHING_TYPES = ("moisturiser", "serum", "toner", "cleanser", "sunscreen", "eye cream")
_RETINOID_TYPES = ("retinoid", "serum", "moisturiser", "eye cream")
INGREDIENTS: dict[str, dict] = {
    "salicylic acid": {"asked": (r"salicylic(?: acid)?",), "named": (r"salicylic",),
                       "actives": ("salicylic acid",), "types": _ACID_TYPES, "related": ("BHA",)},
    "BHA": {"asked": (r"bha", r"beta[- ]hydroxy(?: acid)?"), "named": (r"bha", r"salicylic", r"betaine salicylate"),
            "actives": ("salicylic acid", "betaine salicylate"), "types": _ACID_TYPES, "related": ("salicylic acid",)},
    "glycolic acid": {"asked": (r"glycolic(?: acid)?",), "named": (r"glycolic",), "actives": ("glycolic acid",),
                      "types": _ACID_TYPES, "related": ("AHA",)},
    "lactic acid": {"asked": (r"lactic acid",), "named": (r"lactic",), "actives": ("lactic acid",),
                    "types": _ACID_TYPES, "related": ("AHA",)},
    "mandelic acid": {"asked": (r"mandelic(?: acid)?",), "named": (r"mandelic",), "actives": ("mandelic acid",),
                      "types": _ACID_TYPES, "related": ("AHA",)},
    "AHA": {"asked": (r"aha", r"alpha[- ]hydroxy(?: acid)?"), "named": (r"aha", r"glycolic", r"lactic", r"mandelic"),
            "actives": ("glycolic acid", "lactic acid", "mandelic acid"), "types": _ACID_TYPES,
            "related": ("glycolic acid", "lactic acid", "mandelic acid")},
    "PHA": {"asked": (r"pha", r"gluconolactone", r"lactobionic(?: acid)?"),
            "named": (r"pha", r"gluconolactone", r"lactobionic"), "actives": ("gluconolactone", "lactobionic acid"),
            "types": _ACID_TYPES},
    "azelaic acid": {"asked": (r"azelaic(?: acid)?",), "named": (r"azelaic",), "actives": ("azelaic acid",),
                     "types": ("serum", "moisturiser", "exfoliant", "toner", "spot treatment")},
    "niacinamide": {"asked": (r"niacinamide", r"nicotinamide", r"vitamin b3"),
                    "named": (r"niacinamide", r"nicotinamide"), "actives": ("niacinamide",),
                    "types": _SOOTHING_TYPES},
    "vitamin C": {"asked": (r"vitamin c", r"vit c", r"ascorbic(?: acid)?", r"ascorbyl"),
                  "named": (r"vitamin c", r"vit\.? c", r"ascorbic", r"ascorbyl", r"ascorbate"),
                  "actives": ("vitamin c",), "types": ("serum", "moisturiser", "toner", "eye cream", "sunscreen")},
    "benzoyl peroxide": {"asked": (r"benzoyl(?: peroxide)?", r"bpo"), "named": (r"benzoyl", r"bpo"),
                         "actives": ("benzoyl peroxide",),
                         "types": ("cleanser", "moisturiser", "serum", "spot treatment"),
                         # The orchestrator's decision of 14 Oct 2026: a retinoid counts too when its facts entry's
                         # formula lists benzoyl peroxide (Epiduo: adapalene and benzoyl peroxide, prescription-only in
                         # the UK), never by its name alone.
                         "facts_types": ("retinoid",)},
    "hyaluronic acid": {"asked": (r"hyaluronic(?: acid)?", r"sodium hyaluronate"),
                        "named": (r"hyaluronic", r"hyaluronate", r"ha"), "actives": ("hyaluronic acid",),
                        "types": _SOOTHING_TYPES},
    "ceramides": {"asked": (r"ceramide",), "named": (r"ceramide",), "actives": ("ceramides",),
                  "types": _SOOTHING_TYPES + ("lip balm",)},
    "centella": {"asked": (r"centella(?: asiatica)?", r"cica", r"tiger grass", r"madecassoside"),
                 "named": (r"centella", r"cica", r"madecass\w*", r"tiger grass"), "actives": ("centella asiatica",),
                 "types": _SOOTHING_TYPES},
    "snail mucin": {"asked": (r"snail(?: mucin| secretion)?",), "named": (r"snail", r"mucin"),
                    "actives": ("snail mucin",), "types": ("serum", "moisturiser", "toner", "eye cream", "cleanser")},
    # Retinoids: the retinoid type itself, named by module 1's words ("retinol"), adds no requirement (above);
    # "vitamin A" isn't one of the type's words, so "vitamin a serum" is a serum with a retinoid.
    "retinoid": {"asked": (r"retinol", r"retinoid", r"vitamin a"),
                 "named": (r"retin(?:ol|al|aldehyde|oid|yl)\w*", r"tretinoin", r"adapalene", r"tazarotene",
                           r"retin-a"),
                 "actives": ("retinol", "retinal", "retinyl ester", "hydroxypinacolone retinoate", "tretinoin",
                             "adapalene", "tazarotene"),
                 "types": _RETINOID_TYPES},
    "retinal": {"asked": (r"retinal", r"retinaldehyde"), "named": (r"retinal", r"retinaldehyde"),
                "actives": ("retinal",), "types": _RETINOID_TYPES},
    "tretinoin": {"asked": (r"tretinoin", r"tret"), "named": (r"tretinoin", r"retin-a"), "actives": ("tretinoin",),
                  "types": _RETINOID_TYPES},
    "adapalene": {"asked": (r"adapalene",), "named": (r"adapalene",), "actives": ("adapalene",),
                  "types": _RETINOID_TYPES},
    "tazarotene": {"asked": (r"tazarotene",), "named": (r"tazarotene",), "actives": ("tazarotene",),
                   "types": _RETINOID_TYPES},
}
# A product-facts entry may say what a product is made with and its form, in a block of its own with its own sources and
# date (data/product_facts.json, "formula": {"actives": [...], "form": "...", "sources": [...], "checked_on": "..."};
# engine/product_facts.py), so adding it never claims the entry's other facts were checked again.
# The actives a formula may list (INGREDIENT_ACTIVES): what its maker presents as the
# product's actives (its name, its stated strengths or its "key ingredients"), checked against its ingredient list. A
# trace further down the list isn't an active: a moisturiser with a little sodium hyaluronate isn't a hyaluronic acid
# product. "vitamin c" is ascorbic acid or one of its derivatives; "retinyl ester" is retinyl palmitate or retinyl
# retinoate; "bakuchiol" and "papain" are listed so an entry can say what a product is made with when that isn't one of
# the ingredients above.
INGREDIENT_ACTIVES = (
    "salicylic acid", "betaine salicylate", "glycolic acid", "lactic acid", "mandelic acid", "malic acid",
    "citric acid", "gluconolactone", "lactobionic acid", "azelaic acid", "niacinamide", "vitamin c", "benzoyl peroxide",
    "hyaluronic acid", "ceramides", "centella asiatica", "snail mucin", "retinol", "retinal", "retinyl ester",
    "hydroxypinacolone retinoate", "tretinoin", "adapalene", "tazarotene", "bakuchiol", "papain", "sulfur", "zinc",
)
# The words a request may put before an ingredient so it doesn't ask for it ("no", "without"), or after it ("-free").
INGREDIENT_NOT_ASKED_BEFORE = (r"no", r"not", r"without", r"avoid(?:ing)?", r"instead of", r"rather than",
                               r"other than", r"alternative to", r"alternatives to", r"allergic to", r"sensitive to",
                               r"can'?t use", r"cannot use", r"can'?t tolerate", r"except", r"minus", r"never")
INGREDIENT_NOT_ASKED_AFTER = (r"[- ]?free", r" alternatives?", r" dupes? for")
# Why a product is left out of an ingredient request (the pipeline's left_out_no_ingredient), in words for the shopper.
# Wording decided by Claude, 13 Oct 2026.
INGREDIENT_NOT_CONFIRMED = "we couldn't confirm it contains {ingredient}"
INGREDIENT_NOT_LISTED = "its maker doesn't list {ingredient} among its actives"
INGREDIENT_BRAND_UNCHECKABLE = "a whole brand can't be checked for {ingredient}"
# Why a product with the ingredient is left out of an ingredient-led request for its form (Noemi's decision 1 of 13 Oct
# 2026; the pipeline's left_out_by_form). Wording decided by Claude.
INGREDIENT_RINSE_OFF = "a rinse-off {noun}: ask for a {ingredient} {noun} to see these"
INGREDIENT_FORM_UNKNOWN = "we couldn't confirm it's a leave-on form"
INGREDIENT_NOT_FORM_ASKED = "not the form you asked for ({forms})"
INGREDIENT_FORM_NOT_CONFIRMED = "we couldn't confirm it's the form you asked for ({forms})"
# Choosing threads for an ingredient-led request (engine/sources.py, LocalSource): its products may be of any type, so a
# thread's title rarely names them. Each comment that names the ingredient (or a related one) adds this many points to
# the thread's grade (module 2's post_score), up to INGREDIENT_TALK_MAX: a thread where 6 comments name salicylic acid
# gains 3, as much as an advice title about it. Chosen by Claude, 13 Oct 2026.
INGREDIENT_TALK_POINTS = 0.5
INGREDIENT_TALK_MAX = 3.0
# The forms a formula may give (its maker's own description of what the product is), when its name doesn't say.
INGREDIENT_FORMS = ("serum", "leave-on liquid", "toner", "pads", "essence", "cream", "lotion", "gel", "oil", "balm",
                    "sunscreen", "eye cream", "spot treatment", "patch", "sleeping mask",
                    "cleanser", "rinse-off powder", "peel", "mask", "scrub")
# The form shown with each product of an ingredient-led answer ("Form: pads"), from the first that gives one:
# 1. its product-facts entry's formula "form" (INGREDIENT_FORMS);
# 2. its own name, by these words (regular expressions on whole words of the lowercased name, in this order, so
#    "peel pads" are pads and "cleansing foam" a cleanser);
# 3. its product type (PRODUCT_TYPE_FORMS).
INGREDIENT_FORM_WORDS: tuple[tuple[str, str], ...] = (
    (r"pads?", "pads"),
    (r"peel(?:ing)?", "peel"),
    (r"(?:sleeping|overnight) (?:masks?|masques?|packs?)", "sleeping mask"),
    (r"(?:pimple|acne|spot|zit|blemish|hydrocolloid) (?:patch(?:es)?|stickers?|dots?)|patch(?:es)?", "patch"),
    (r"(?<!dark )(?<!age )(?<!sun )spot[- ](?:treatments?|gels?|creams?)", "spot treatment"),
    (r"toners?", "toner"),
    (r"essences?", "essence"),
    (r"serums?|ampoules?|boosters?", "serum"),
    (r"scrubs?|polish", "scrub"),
    (r"cleansers?|cleansing|face ?wash|wash|foam|gleanser", "cleanser"),
    (r"liquids?|solutions?", "leave-on liquid"),
    (r"masks?|masques?", "mask"),
    (r"sunscreens?|spf\s?\d*|sun (?:cream|fluid|milk|gel|stick|essence)", "sunscreen"),
    (r"eye (?:creams?|serums?|gels?)", "eye cream"),
    (r"lotions?", "lotion"),
    (r"gel[- ]?creams?|creams?|cremes?|moisturi[sz]ers?|emulsions?", "cream"),
    (r"gels?", "gel"),
    (r"oils?", "oil"),
    (r"balms?", "balm"),
    (r"powders?", "rinse-off powder"),
)
# Leave-on and rinse-off forms (Noemi's decision 1 of 13 Oct 2026): an ingredient-led request ("salicylic acid for
# acne") shows leave-on forms only; a rinse-off form counts only when the request names it ("salicylic acid wash", or
# a type: "salicylic acid cleanser"). Every form a name, a type or a formula can give is one or the other, except an
# exfoliant whose name and facts don't say (a leave-on liquid or a rinse-off scrub): its form isn't known, so it is
# left out of such a request, never guessed. RINSE_OFF_FORMS gives the word a request names each by ("a salicylic acid
# powder"), for the reason a product is left out with.
LEAVE_ON_FORMS = ("serum", "leave-on liquid", "toner", "pads", "essence", "cream", "moisturiser", "lotion", "gel",
                  "oil", "balm", "sunscreen", "eye cream", "spot treatment", "patch", "sleeping mask",
                  "retinoid treatment", "lip balm")
RINSE_OFF_FORMS: dict[str, str] = {"cleanser": "cleanser", "rinse-off powder": "powder", "peel": "peel",
                                   "mask": "mask", "scrub": "scrub"}
PRODUCT_TYPE_FORMS: dict[str, str] = {
    "exfoliant": "exfoliant", "cleanser": "cleanser", "moisturiser": "moisturiser", "sunscreen": "sunscreen",
    "retinoid": "retinoid treatment", "serum": "serum", "toner": "toner", "eye cream": "eye cream",
    "lip balm": "lip balm", "spot treatment": "spot treatment",
}

# --- On-demand reading (Noemi's plan of 14 Oct 2026, part 3; values chosen by Claude, reported to Noemi) ---
# engine/on_demand.py. A request module 1 understands, about a product type the library holds fewer extracted threads
# about than this, is queued for a reading job (Arctic Shift's archive, Gemini's free allowance), and the site says so:
# the library's own mix per product type.
ON_DEMAND_MIN_THREADS = LIBRARY_THREADS_PER_PRODUCT
# What the queue keeps of a request: its product type, category and subreddits (module 1's), and at most this many of its
# need words (engine.sources.need_words: its own words less the product's name, filler words and numbers), for a
# need-led choice of threads. Never the request as typed, never a time or an address (Noemi's rule of 11 Oct 2026).
ON_DEMAND_NEED_WORDS = 3
# At most this many requests wait at once: more are answered from what the library has, and asked about again later.
# 20 since 14 Oct 2026 (10 before; the coordinator asked to raise it with the general category, whose types mostly have
# no threads yet, so most of its requests queue; chosen by Claude, reported to Noemi): about two days of the job's
# reading within Gemini's free allowance (about 11 products a day, at about 9 calls each), and their threads (6 each)
# fit the bundle (ON_DEMAND_BUNDLE_MAX_THREADS) before a deploy takes them in. The free-tier sums don't change: the
# job's time and its Gemini calls have caps of their own (ON_DEMAND_MONTH_SECONDS, ON_DEMAND_GEMINI_CALLS_A_DAY), and
# the site never starts the job while the queue rests.
ON_DEMAND_MAX_WAITING = 20
# The queue remembers at most this many requests already read (the oldest are forgotten): each is read again, when its
# library is still thin, after ON_DEMAND_READ_AGAIN_DAYS (Reddit may have more by then), or after ON_DEMAND_RETRY_DAYS
# when its reading failed ON_DEMAND_MAX_TRIES times (Arctic Shift down, say), each try at least an hour apart.
ON_DEMAND_MAX_DONE = 300
ON_DEMAND_READ_AGAIN_DAYS = 30
ON_DEMAND_RETRY_DAYS = 1
ON_DEMAND_MAX_TRIES = 3
ON_DEMAND_RETRY_MINUTES = 60
# A thread whose extraction fails this many times (not for the daily limit) is let go.
ON_DEMAND_EXTRACT_TRIES = 3
# The job's time (Cloud Run jobs are billed for their whole run, waiting included; free tiers only): a run starts no new
# request's reading after ON_DEMAND_NEW_READING_SECONDS (its task timeout, 45 minutes, leaves room to finish one), and
# the runs of a month read for at most ON_DEMAND_MONTH_SECONDS, which with the daily pre-check keeps Cloud Run jobs
# inside their free 240,000 vCPU-seconds a month (deploy/cloudrun/DEPLOY.md). Each run also counts
# ON_DEMAND_START_SECONDS for starting up. A run holds the queue (its lease) for ON_DEMAND_LEASE_MINUTES at most: longer
# than its task timeout, so a run cut short never keeps the next one out for long.
ON_DEMAND_NEW_READING_SECONDS = 15 * 60
ON_DEMAND_MONTH_SECONDS = 50_000
ON_DEMAND_START_SECONDS = 30
ON_DEMAND_LEASE_MINUTES = 50
# Gemini calls a day the job may make (Gemini's free allowance only, Noemi's decision of 14 Oct 2026), leaving the rest
# of the free daily allowance to Noemi's own bulk reading; a 429 for the day stops it sooner. The allowance resets at
# midnight Pacific time: the job waits until GEMINI_RESET_HOUR_UTC (8 am UTC: midnight in winter, 1 am in summer), so
# it never asks before the reset.
ON_DEMAND_GEMINI_CALLS_A_DAY = 100
GEMINI_RESET_HOUR_UTC = 8
# The bundle holds at most this many threads not baked into the site's image yet: past it the job reads no new request
# until a deploy takes them in (python -m engine.library pull-bucket, run by deploy/cloudrun/deploy.sh).
ON_DEMAND_BUNDLE_MAX_THREADS = 300
# What a visitor is told: the first request waiting is read in about ON_DEMAND_FIRST_MINUTES (the job starts at once:
# about 6 minutes of Arctic Shift's paced searches and reads, then Gemini's extraction and the site's pick-up), each one
# ahead of it about ON_DEMAND_EACH_MINUTES more; past ON_DEMAND_LATE_MINUTES of waiting (by the site's own clock, kept in
# memory only) it is said to be taking longer than usual.
ON_DEMAND_FIRST_MINUTES = 20
ON_DEMAND_EACH_MINUTES = 15
ON_DEMAND_LATE_MINUTES = 90
# The site starts the job at most this often, when requests wait and no run holds the queue (the keep-warm ping, every 5
# minutes, starts it again when a start failed), and reads the queue again at most this often when asked about a
# request it knows is waiting.
ON_DEMAND_START_EVERY_SECONDS = 300
ON_DEMAND_QUEUE_FRESH_SECONDS = 60

# --- Upvotes count more when credible mentions are few (Noemi, 14 Oct 2026; built switched off) ---
# Noemi: "let's be reasonable. if we have few credible mentions, a highly upvoted comment (10+) counts more", and she
# asked to see which picks it would change before it is turned on (the effect report: eval/RUNS.md, 14 Oct 2026). With
# it on, a credible recommendation (CREDIBLE_VOICES, CREDIBLE_EVIDENCE: upvotes never make a comment credible) whose
# comment has at least UPVOTE_MIN_SCORE upvotes (its score: upvotes minus downvotes) counts as two credible
# recommendations toward the picks bar (MIN_CREDIBLE_MENTIONS) and Also worth a look's (WORTH_A_LOOK_CREDIBLE): never
# more than two, never for a warning, and never in place of the second thread (MIN_THREADS still counts threads). The
# score, the order's tie-breaks, Skip these and the mixed-opinions flag still count writers, and the answer says which
# voices counted twice and for how many upvotes (engine/rank.py, engine/answer.py). Four variants, by the three
# settings below (UPVOTE_ONLY_WHEN_SHORT, UPVOTE_TOP_OF_BIG_THREAD, UPVOTE_ONLY_TO_FILL):
#   A: any product (False, False, False);
#   B: only a product with fewer credible recommendations than the bar, and only as many as it needs, the most upvoted
#      first: it can lift a product to the picks, never inflate one that qualifies (True, False, False);
#   C: as B, and the comment must be among the top of a big thread, her earlier "needs to be a high quality thread":
#      at least UPVOTE_THREAD_MIN_COMMENTS comments readable when it was read, and scoring higher than at least
#      UPVOTE_THREAD_SHARE_BEATEN of the others, its top 10% (True, True, False);
#   D: as C, and a product it lifts ranks after every product meeting the bar on its own, so it only fills a place the
#      picks would leave empty, never takes one (True, True, True; added by Claude after the first effect run, where B
#      and C put lifted shampoos in place of picks with three credible writers).
# In every variant nothing leaves the answer (a lifted product its score keeps out of the picks stays under Also worth a
# look) and how much an answer reads doesn't change (engine.pipeline.answer_request).
# Decided (Noemi, 14 Oct 2026: "yes" to turning on variant D, as recommended after its effect report): the switch is on,
# with D's values below (her "10+", the top 10% of a thread of 20+ comments, filling empty places only).
UPVOTE_COUNTS_MORE = True
UPVOTE_MIN_SCORE = 10  # Noemi's "10+"
UPVOTE_ONLY_WHEN_SHORT = True
UPVOTE_TOP_OF_BIG_THREAD = True
UPVOTE_ONLY_TO_FILL = True
UPVOTE_THREAD_MIN_COMMENTS = 20
UPVOTE_THREAD_SHARE_BEATEN = 0.9

# --- Bulk import from Arctic Shift's per-subreddit history files (Noemi, 14 Oct 2026; engine/bulk_import.py) ---
# Noemi's decision 1 of 14 Oct 2026: threads are chosen on this machine from the per-subreddit files, only the chosen
# ones enter the library, and the raw files are deleted within BULK_RAW_FILES_KEPT_HOURS of the download's start. The
# values below were chosen by Claude (technical calls, reported to Noemi).
# The files: Academic Torrents' "subreddits23" (every post and comment of a subreddit from June 2005 to December 2023,
# from Pushshift and Arctic Shift), and the last day they hold.
BULK_DUMP = "subreddits23 (Arctic Shift's per-subreddit history files, 2005-06 to 2023-12)"
BULK_DUMP_LAST_DAY = "2023-12-31"
BULK_RAW_FILES_KEPT_HOURS = 48
# Real engagement: at least as many comments as module 2's small-thread bar (engine.sources.SMALL_THREAD, 15) and a
# score of 5, so the community answered and didn't bury it. A post the archive saved within a day of its writing (much
# of late 2023) had neither settled yet: its comments in the file are counted instead, and its score isn't asked for.
BULK_MIN_COMMENTS = 15
BULK_MIN_SCORE = 5
# Posts from this year on: products and formulas change (module 2 already prefers recent skincare threads), and these
# five years hold enough threads for every type but the smallest.
BULK_FIRST_YEAR = 2019
# How many threads a run adds. Each product type aims at BULK_TYPE_TARGET threads about it (its title or post names it,
# as answers read them), split as the library's mix (LIBRARY_MIX: 18 advice, 6 long-term use, 12 warnings), and takes
# only the kinds it is short of: the thinnest types and kinds first. At most BULK_MAX_NEW_PER_TYPE new threads per type
# in one run, so the extraction backlog stays readable.
BULK_TYPE_TARGET = 36
BULK_MAX_NEW_PER_TYPE = 30
# The general category's types (336 on 14 Oct 2026) aim at one library mix each in a run (LIBRARY_THREADS_PER_PRODUCT:
# 3 advice, 1 long-term use, 2 warnings): the extracted threads at which the site stops queueing a request for
# on-demand reading (ON_DEMAND_MIN_THREADS). 30 each would be about 10,000 threads, far more than can be extracted
# before the archive text's retention (ARCHIVE_TEXT_KEPT_DAYS) removes it.
BULK_GENERAL_TYPE_TARGET = LIBRARY_THREADS_PER_PRODUCT
# A request given to the import (need-led choice, Noemi's decision 3 of 14 Oct 2026: "conditioner for curly hair") takes
# up to this many threads asking about its needs, within its type's BULK_MAX_NEW_PER_TYPE.
BULK_PER_REQUEST = 8

# --- A comment that stands out in its thread (Noemi, 14 Oct 2026, after switching on variant D) ---
# Noemi: "if a comment has a lot of upvotes compared to the size of the thread, i want it as a pick or worth a look". A
# credible recommendation (CREDIBLE_VOICES, CREDIBLE_EVIDENCE: upvotes never make a comment credible) stands out in its
# thread when its comment has at least STANDOUT_UPVOTES_PER_COMMENT upvotes for each comment of its thread readable when
# it was read (3 for every 4) and at least STANDOUT_MIN_SCORE upvotes, in a thread of at least
# STANDOUT_MIN_THREAD_COMMENTS comments; it names at most STANDOUT_MAX_PRODUCTS products (a whole routine or a review of
# many shares its upvotes among them); and, when the request asks for anything besides the product (engine/needs.py),
# it talks about that (engine/rank.py, stands_out). Its product, with more credible recommendations than credible
# warnings and a score above zero, can then take a place left empty under Also worth a look even with that one credible
# voice, and with a second credible writer, even from the same thread, it meets the picks bar (STANDOUT_FILLS_PICKS),
# only to fill a place the products meeting it otherwise leave empty (RankingResult.qualifying): never the place of a
# product that meets the rules without it, as for variant D. Variant D comes first: what it lifts, it lifts as before.
# The answer says which comment stands out and by how much ("its comment has 74 upvotes in a 69-comment thread"), and
# how much an answer reads doesn't change (engine.pipeline.answer_request). The measure and the values were chosen by a
# breadth-first pass over six ways of measuring standing out on the library of 14 Oct 2026, quality first: the lowest
# values that lifted nothing that made no sense (eval/RUNS.md, 14 Oct 2026). Switched on as Noemi asked; the values
# PROPOSED by Claude.
STANDOUT_ON = True
STANDOUT_UPVOTES_PER_COMMENT = 0.75
STANDOUT_MIN_SCORE = 25
STANDOUT_MIN_THREAD_COMMENTS = 20
STANDOUT_MAX_PRODUCTS = 5
# Into the picks with a second credible writer even from one thread: her "as a pick", which sets aside, for this case
# only, her night rule for the upvote rule that "a pick still needs credible recommendations across 2 threads". False
# keeps that rule: then a standing-out comment earns a place under Also worth a look only. For Noemi to confirm.
STANDOUT_FILLS_PICKS = True

# --- Module 1: weapon-like knives get the polite no (Noemi, 15 Oct 2026: "yes to all your recommendations") ---
# Proposed by the routing audit on 14 Oct 2026, decided by Noemi on 15 Oct: refused as engine.query.HARMFUL refuses a
# combat knife. Until 14 Oct 2026 each was taken for the kitchen's chef knife. Some can't be sold in the UK at all
# (zombie knives, gravity knives, push daggers, knives disguised as an everyday object such as a credit card knife); the
# others are sold mostly as fighting or concealed-carry knives. A machete is a garden tool, a product (her same answer).
HARMFUL_KNIVES = (
    "zombie knife", "karambit", "push dagger", "gravity knife", "knuckle knife", "trench knife", "otf knife",
    "automatic knife", "stiletto knife", "credit card knife", "hidden knife", "concealed knife", "boot knife",
    "neck knife", "bowie knife", "fighting knife", "dagger",
)

# --- Buyable picks, makers' images and direct links (Noemi's decisions of 15 Oct 2026, late afternoon) ---
# From the live laptop answer, whose first pick was 2010-2011 MacBook Pros, read from old threads, with no price and no
# link ("what's the point of recommending it if i can't buy it?"). (1) A pick must be on sale in the UK now; whether it
# is comes from researched data (data/prices.json, which `python -m engine.buyable import` fills from researchers'
# findings), never guessed: a product found not sold to UK shoppers, or discontinued, is left out and named
# (engine.pipeline's left_out_unavailable, the page's "About this answer"). Sold second-hand only counts only for things
# people buy vintage on purpose (her rule of 10 Oct 2026): the brands or products below, by category, whose old ones
# people seek out and UK shoppers can use; any other product sold second-hand only counts as not sold
# (engine.prices.counts_as_sold). Claude's calls, reported: besides her Griswold and Wagner cast iron, the Hobart-era
# KitchenAid stand mixers (made by Hobart until 1986, sought second-hand; UK 240 V ones exist), IBM's Model M keyboard
# (bought used on purpose by collectors; it works here with an adapter) and AKG's K240 Sextett headphones (the vintage
# K240, sought for its sound; no mains voltage to mind), from the first findings; but not American mains appliances
# made for 110-120 V only, though people buy some vintage on purpose in the US: Rival's crock pots, and Sunbeam's Radiant
# Control and Toastmaster's toasters (a UK shopper needs a step-down transformer, as OXO's 120 V kettles aren't sold
# here), so Rival's line now leaves the slow cooker answer. A name holding one of these counts ("vintage pre 1970s
# Griswold or Wagner Ware skillet").
SECOND_HAND_VINTAGE = {"kitchen": ("Griswold", "Wagner", "Hobart-era KitchenAid", "Hobart KitchenAid"),
                       "general": ("IBM Model M", "AKG K240 Sextett")}
# (2) Newest threads first for fast-moving products: types whose models are replaced every year or two, so a thread's
# picks go out of sale as it ages (Claude's list, reported to Noemi). For these, module 2's first reading reads the
# threads newest first, FAST_MOVING_YEARS at a time counted back from the newest thread about the product, each span in
# module 2's graded and need-led order (engine.sources.LocalSource._need_led); a thread titled as another type still
# comes last. Every type here is a general one, so kitchen, skincare and haircare answers read as before.
FAST_MOVING_TYPES = (
    "laptop", "desktop computer", "monitor", "headphones", "earbuds", "gaming headset", "bluetooth speaker", "soundbar",
    "tv", "projector", "streaming device", "phone", "tablet", "e-reader", "smartwatch", "smart ring", "camera",
    "action camera", "webcam", "drone", "printer", "3d printer", "wifi router", "gaming console", "vr headset",
    "drawing tablet", "smart speaker", "robot vacuum", "robot lawn mower", "security camera", "video doorbell",
    "fitness tracker", "sports watch", "dash cam",
)
FAST_MOVING_YEARS = 1
# (3) Direct links only: a shop's or a search engine's results page is never linked (engine.links.is_search_page): its
# path has one of these steps ("/search", eBay's "/sch/", Amazon's "/s"), or its query names the words searched for.
SEARCH_PAGE_PATH_STEPS = ("search", "sitesearch", "searchresults", "sch", "s", "find", "results")
SEARCH_PAGE_QUERY_KEYS = ("q", "k", "query", "search", "searchterm", "search-term", "search_term", "search_query",
                          "searchquery", "text", "_nkw", "keyword", "keywords", "term", "kw")
# (4) Makers' images checked as they are imported (the coordinator, 15 Oct 2026: lazy loading doesn't help a phone that
# opens a card with a 5 MB image): `python -m engine.buyable import` asks each image's server for its size (headers only,
# never the image itself, as an honest tool: never pretending to be a browser), keeps one of at most IMAGE_MAX_BYTES,
# else asks the maker's own server for a smaller size of the same image (IMAGE_SMALLER_WIDTH pixels wide, the way its
# image server takes a width), else leaves the image out and records why in the page's note; one whose size can't be
# checked is left out too, never guessed.
IMAGE_MAX_BYTES = 500_000  # about 500 KB, as phones and servers count them
IMAGE_SMALLER_WIDTH = 600
IMAGE_CHECK_TIMEOUT_SECONDS = 15

# --- Converge round 1: ws-names (17 Oct 2026) ---
# Module 1's need words and module 4's names, from the 16 Oct breadth-first reviews (docs: understanding, reading and
# extraction-and-names); Claude's technical calls within Noemi's rules, reported to her. Each value added here, merged
# into the shared one it extends.
# Eczema is sensitive skin, as rosacea is (16 Oct 2026): the sensitive-skin rules apply ("moisturiser for eczema"), and
# comments about eczema already talked about sensitive skin (NEED_COMMENT_WORDS). For a scalp, a sensitive scalp
# (engine.needs: a need of another category's words is its own category's).
NEED_REQUEST_WORDS = NEED_REQUEST_WORDS | {"eczema": "sensitive"}
# Need words, round two (17 Oct 2026; engine/needs.py). More two words that make one need, named whole in the reason:
# ones written with a word that is no need on its own ("dog hair", "no pull", "carry on"), with a word of the product's
# name ("raw denim", "double cleansing", "chapped lips", "true wireless"), or with the skin need's word for the lips
# ("dry lips", which had been named "dry skin").
NEED_PHRASES = NEED_PHRASES + (
    "dog hair", "pet hair", "cat hair", "no pull", "true wireless", "raw denim", "large pores", "open pores",
    "clogged pores", "double cleansing", "chapped lips", "cracked lips", "dry lips", "carry on", "memory foam",
    "non toxic", "bread dough", "pizza dough")
# A need that is a verb, as the reason names it (17 Oct 2026): "about drying fast", not "about dry or fast"; "about
# staying cool", "about keeping drinks cold", "about slipping" ("a yoga mat that doesn't slip"). Only the label: the
# need is still found by the word as typed.
NEED_VERB_LABELS: dict[str, str] = {
    "dry": "drying", "dries": "drying", "stay": "staying", "stays": "staying", "keep": "keeping", "keeps": "keeping",
    "fade": "fading", "fades": "fading", "fold": "folding", "folds": "folding", "fit": "fitting", "fits": "fitting",
    "hold": "holding", "holds": "holding", "heat": "heating", "heats": "heating", "charge": "charging",
    "charges": "charging", "grip": "gripping", "grips": "gripping", "slip": "slipping", "slips": "slipping",
    "wobble": "wobbling", "wobbles": "wobbling", "chip": "chipping", "crease": "creasing", "creases": "creasing",
    "pinch": "pinching", "pinches": "pinching", "leak": "leaking", "leaks": "leaking", "rust": "rusting",
    "rusts": "rusting", "scratch": "scratching", "scratches": "scratching", "break": "breaking", "breaks": "breaking",
    "shrink": "shrinking", "shrinks": "shrinking", "pill": "pilling", "stain": "staining", "stains": "staining",
    "smudge": "smudging", "smudges": "smudging", "warp": "warping", "warps": "warping", "fog": "fogging",
    "fogs": "fogging", "tangle": "tangling", "tangles": "tangling", "squeak": "squeaking", "squeaks": "squeaking",
    "sag": "sagging", "sags": "sagging", "peel": "peeling", "peels": "peeling", "fray": "fraying", "frays": "fraying",
    "whistle": "whistling", "whistles": "whistling", "boil": "boiling", "boils": "boiling", "clean": "cleaning",
    "cleans": "cleaning", "blunt": "blunting", "dull": "dulling"}
# A request's own word is also found in a comment's other words for it (17 Oct 2026, from the 16 Oct review of module 1:
# "a laptop for university" found no comment saying "uni" or "college"), each written as need words are (letters and
# digits only; two words are found written as one too: "stovetop" finds "stove top").
REQUEST_WORD_SYNONYMS: dict[str, tuple[str, ...]] = {
    "university": ("uni", "college", "student"), "uni": ("university", "college", "student"),
    "college": ("university", "uni", "student"), "student": ("university", "uni", "college"),
    "commuting": ("commute", "commuter"), "commute": ("commuting", "commuter"),
    "hob": ("stove", "stovetop", "cooktop"), "stove": ("hob", "stovetop", "cooktop"),
    "stovetop": ("hob", "stove", "cooktop"), "newborn": ("infant", "newborns"),
}
# Words that hold a request's own word but say something else (17 Oct 2026, from the 16 Oct review of ranking: a
# comment about taking makeup off had made a moisturiser "work under makeup"), as NEED_LOOKALIKES are for its needs.
NEED_LOOKALIKES = NEED_LOOKALIKES | {
    "makeup": (r"(?<![a-z0-9])(?:remov\w*|take|takes|taking|took|wipe|wipes|wiping|melt\w*|break\w* down|dissolv\w*|"
               r"get|gets|getting)\s+(?:\w+\s+){0,3}?(?:off\s+)?(?:all\s+|my\s+|the\s+|your\s+|of\s+|eye\s+)*"
               r"make-?up(?:\s+off)?(?![a-z0-9])",
               r"(?<![a-z0-9])make-?up\s+(?:remov\w*|wipes?|residue|off)(?![a-z0-9])"),
}
# Brands that are everyday words too: a request's word is no brand of these (engine.needs: a brand is no judged need),
# found among data/brand_lines.json's one-word brands on 17 Oct 2026.
EVERYDAY_BRAND_WORDS = frozenset({"field", "global", "hero", "tiger", "wolf", "aroma", "flair", "luxe", "nest", "sage",
                                  "apple", "ego", "kyte", "epicurean", "icebreaker", "simple", "always", "instant",
                                  "fresh", "glow", "honest", "native", "pure", "smart", "true", "original", "solo"})
# Module 4's names (17 Oct 2026). Barbecue and knife sharpener synonyms were tried here on 17 Oct and taken out on 18 Oct
# 2026 (the ws-names builder): with them a model's name and the type's word ("Weber Spirit gas grill", "King KDS
# 1000/6000 combo stone") read as a line of the model (engine.group_products, "Name levels"), so the barbecue answer
# folded the Spirit into Weber's line and lost a pick, and the King stone and the Shapton Pro 1500 became lines; the
# short names alone keep one product shown once (engine/data/product_aliases.json).
# Brands as their makers write them (17 Oct 2026, from the day's sweep: names still shown in small letters or other
# capitals, a writer's possessive or plural of a brand), merged into MAKER_SPELLINGS. A maker's own small letters are
# kept ("smartwater"); a model's name with its brand where writers write the model in small letters ("Laifen Swift",
# "Spyderco Sharpmaker", "Shapton Pro").
_NAMES_ROUND_TWO_SPELLINGS: dict[str, tuple[str, ...]] = {
    "general": ("OtterBox Defender", "OtterBox", "Laifen Swift", "Laifen", "Nanit", "Momcozy", "Durston X-Mid",
                "Durston", "Sea to Summit", "Bowflex", "BaByliss", "Grado", "Oral-B", "Fisher & Paykel", "Kenmore",
                "BabyBjörn", "Ergobaby", "Smartwool", "Dogbed4less", "Wrangler", "Danner", "Feather", "IKEA",
                "Unique Melody", "Shure", "Logitech", "Lenovo", "Melanzana", "smartwater"),
    "kitchen": ("Chef'sChoice", "Our Place", "Finex", "Hario", "All-Clad", "Amazon Basics", "Big Green Egg", "Char-Broil",
                "Henckels", "Kenmore", "Weber", "Spyderco Sharpmaker", "Shapton Pro", "1Zpresso", "Sunbeam",
                "Toastmaster", "IKEA", "Orphan Espresso"),
    "skincare": ("Paula's Choice", "Vanicream", "Sun Bum", "SKINFOOD", "Neutrogena", "Estée Lauder", "Ole Henriksen",
                 "The INKEY List"),
    "haircare": ("Native", "Viori", "KEVIN.MURPHY", "Hairstory", "Giovanni"),
}
MAKER_SPELLINGS = {category: MAKER_SPELLINGS.get(category, ()) + _NAMES_ROUND_TWO_SPELLINGS.get(category, ())
                   for category in sorted(set(MAKER_SPELLINGS) | set(_NAMES_ROUND_TWO_SPELLINGS))}
# 18 Oct 2026 (the ws-names builder, from every library name spelled with the 17 Oct rules): makers who write their
# brand in small letters or capitals of their own, which a capital to start a name as a last resort had turned into
# "E.l.f.", "Iunik", "Got2b" or "Ogx" (innisfree's small letters come from the facts list's own names, engine.
# group_products._tidied: config's would also write writers' "Innisfree" so, which 16 Oct left to config alone); and
# brands writers write apart, together or in the plural ("darn tough", "all birds", "fat max", "redwings"; "la creuset"
# is in the short names).
_NAMES_ROUND_THREE_SPELLINGS: dict[str, tuple[str, ...]] = {
    "general": ("REI", "KEF", "iFi", "J.Crew", "UGG", "MAM", "Big Agnes", "FatMax", "Bar Keepers Friend", "Allbirds",
                "IceMule", "Darn Tough", "Red Wing"),
    "skincare": ("e.l.f.", "iUNIK", "Melano CC", "Drunk Elephant", "Haruharu"),
    "haircare": ("got2b", "OGX"),
}
MAKER_SPELLINGS = {category: MAKER_SPELLINGS.get(category, ()) + _NAMES_ROUND_THREE_SPELLINGS.get(category, ())
                   for category in sorted(set(MAKER_SPELLINGS) | set(_NAMES_ROUND_THREE_SPELLINGS))}
# Type rules (17 Oct 2026; the decided rule of 10 Oct 2026, decision 5: what holds, covers, sharpens or refills a
# product never counts for it). A razor's blade is such a thing: "blade" joins OTHER_TYPE_WORDS (an existing value,
# extended in place for this item), so the AI's 30 "razor blade" mentions, and a product every writer names as blades
# (engine.group_products), stay out of razor answers ("Derby blades" had been the second razor pick).
OTHER_TYPE_WORDS = OTHER_TYPE_WORDS + ("blade",)
# And a liner (18 Oct 2026): a sleeping bag liner goes inside a sleeping bag, a bin liner in a bin; the AI's "sleeping bag
# liner" mentions had made Sea to Summit's liners a sleeping bag answer's Skip these.
OTHER_TYPE_WORDS = OTHER_TYPE_WORDS + ("liner",)
# Non-toxic cookware is PFAS-free cookware (18 Oct 2026, the ws-names builder; Claude's call of 18 Oct 2026, Noemi:
# "About the pfas - do what you think is best"). For a product type that has the fact (PRODUCT_FACTS_BY_TYPE: frying pans
# and saucepans), "non toxic", "non-toxic", "nontoxic" and "toxin free" ask for PFAS-free, since that is what non-toxic
# means for pans (no PTFE or other PFAS, Noemi's rule of 11 Oct 2026), as refusing Teflon has since 16 Oct 2026
# (PRODUCT_FACT_REQUEST_WORDS); for every other type they stay an ordinary need word (engine.query.type_asks). {what is
# asked: its fact, the request's words (regular expressions, whole words, lowercase) and the words of comments that talk
# about it: toxins, and PFAS, PTFE, PFOA or Teflon by name}. The reason line names the must-have (TYPE_ASKED_LABEL:
# "about PFAS-free", as the ws-answer builder names refusing Teflon on 17 Oct 2026), so the reading shows.
TYPE_ASKED_WORDS: dict[str, dict] = {
    "PFAS-free": {"fact": "pfas_free", "words": (r"non[- ]?toxic", r"toxi(?:ns?|c)[- ]?free"),
                  "comment_words": ("toxic", "toxin", "nontoxic", "non-toxic", "pfas", "ptfe", "pfoa", "teflon",
                                    "forever chemical")},
}
TYPE_ASKED_LABEL = "{asked}"
# Need words, round three (18 Oct 2026, the ws-names builder; engine/needs.py). A name of a type that is another name
# for it, not a kind of it: in kitchen and general requests its words are the product's, as a type's own name is
# ("portable charger" is a power bank, so "portable" is no need; a "wine cooler" stays a kind of fridge, "gaming laptop"
# a kind of laptop).
TYPE_OTHER_NAMES: dict[str, tuple[str, ...]] = {
    "power bank": ("portable charger", "portable chargers", "portable battery", "portable batteries", "battery pack",
                   "battery packs", "battery bank", "battery banks"),
}
# An induction hob, stove or cooktop is the induction need, named once (the hob, stove or cooktop had been a need of its
# own: "about induction or hob"), extending the need's words in place for this item.
NEEDS = NEEDS | {"induction-compatible": NEEDS["induction-compatible"] + (
    "induction hob", "induction stove", "induction cooktop", "induction hot plate", "induction range")}

# --- Converge round 1: ws-ranking (17 Oct 2026) ---
# Modules 5 and 6, from the breadth-first review of 16 Oct 2026 (docs/bfs-2026-10-16/credibility-and-ranking.md) and
# Noemi's decisions of 16 Oct 2026 (evening). Values chosen by Claude within her decisions; what goes beyond them is
# marked PROPOSED and switched off.
# Item 3, her decision 3 (first-hand use): the AI's reading of the whole comment counts when the rules miss the writer's
# use (engine.credibility.with_ai_evidence), only with a concrete tag or the writer speaking for themselves, and never
# for someone else's experience. On because her gold threads' agreement and votes didn't get worse (eval/RUNS.md, 17
# Oct 2026); False goes back to the rules' reading, the AI only taking use away.
AI_FIRST_HAND_COUNTS = True
# And its long use (the same decision, 17 Oct 2026): where the rules see use but no time ("I use it", a verdict) and the
# AI reads long-term use, the AI's reading counts. Her held-out kettle thread: 27 -> 29 of 30 products as answers use
# them; her scored threads unchanged. False keeps the rules' short-term use there.
AI_LONG_TERM_COUNTS = True
# Item 2, her decision 2 (Skip these): a product is listed under Skip these only with credible warnings from at least
# SKIP_MIN_THREADS threads (the picks bar's two threads; 140 of the 16 Oct sweep's 271 shown items came from one), the
# warnings from the opposite of a need the request asks about left aside (NEED_OPPOSITES: an oily-skin complaint in a
# dry-skin answer, unless it talks about dry skin too), and at most SKIP_SHOWN are shown (engine/answer.py).
SKIP_MIN_THREADS = 2
SKIP_SHOWN = 5
# The needs whose opposite a request can name, skin and hair types (Claude's list, from her example): {need: its
# opposites}. Kitchen and general needs have none listed; a warning about something else there still counts.
NEED_OPPOSITES: dict[str, tuple[str, ...]] = {
    "dry": ("oily",), "oily": ("dry",),
    "dry hair": ("oily hair",), "oily hair": ("dry hair",),
}
# Item 6 (PROPOSED, off: it changes the brief's Sum rule, Noemi's to decide): the picks ordered by credible support, the
# sum of their credible mentions' weights, with every mention's score (hearsay and low voices included) breaking ties.
# On the 16 Oct sweep 26 of 472 pairs of picks had a pick with fewer and shorter credible voices first only because of
# its other mentions' points (b03: innisfree's 3 credible voices and 8 hearsay ones above CeraVe's 7 credible).
RANK_BY_CREDIBLE_POINTS = False
# Item 1, her decision 1 (features before the product noun; engine/features.py). Claude's lists, from the 16 Oct sweep's
# 41 requests naming a feature: the categories it applies to (skincare and haircare keep their need rule); the config
# needs that describe a product, so a request naming them before its noun asks for a feature (a beginner, a home cook or
# lasting is about the buyer or the whole library); words that only name the product ("coffee machine", "tea kettle",
# "computer mouse"); how a comment praises a product for a config need and what says the opposite (quiet: "very noisy"
# isn't praise); short forms a comment may use for a feature; and the words of a product's own name that say a feature's
# opposite (a "corded DeWalt drill" is no cordless drill, whatever its writer says of cordless ones).
FEATURE_CATEGORIES = ("kitchen", "general")
FEATURE_CONFIG_NEEDS = ("quiet", "stainless steel", "dishwasher-safe", "induction-compatible", "plastic-free",
                        "temperature control")
FEATURE_PLAIN_WORDS = ("coffee", "tea", "computer", "pc", "mobile", "cell", "wrist", "bed", "bath", "drink", "drinks",
                       "power", "web", "home", "kitchen", "pair")
FEATURE_PRAISE_WORDS: dict[str, tuple[str, ...]] = {
    "quiet": ("quiet", "silent", "silence", "whisper", "no noise", "barely any noise", "hardly any noise",
              "little noise"),
}
FEATURE_AGAINST_WORDS: dict[str, tuple[str, ...]] = {
    "quiet": ("noisy", "loud", "rattl", "racket", "screech", "whine", "whining"),
}
FEATURE_SHORT_FORMS: dict[str, tuple[str, ...]] = {"noise cancelling": ("anc",), "true wireless": ("tws", "wireless")}
# Materials (Claude's list): a request naming one before its noun ("stainless steel pan", "cast iron kettle", "glass
# teapot") gets praise from the writer's own words only, in a clause holding the product, never from a thread's ask:
# on the 16 Oct library a cast iron kettle thread's answers proposed enamel and stainless kettles, and comments compare
# materials (one praised stainless steel in general, then named a non-stick Tramontina for those who want one).
FEATURE_MATERIALS = ("stainless steel", "stainless", "cast iron", "carbon steel", "steel", "iron", "enamel", "enamelled",
                     "enameled", "ceramic", "copper", "glass", "aluminium", "aluminum", "titanium", "wood", "wooden",
                     "bamboo", "teak", "walnut", "maple", "olive wood", "plastic", "silicone", "porcelain", "stoneware",
                     "clay", "leather", "suede", "canvas", "wool", "merino", "cotton", "linen", "silk", "cashmere",
                     "denim", "raw denim", "down", "nylon", "polyester", "gore-tex", "goretex")
FEATURE_OPPOSITE_NAMES: dict[str, tuple[str, ...]] = {
    "cordless": ("corded",), "wireless": ("wired",), "true wireless": ("wired",),
    "noise cancelling": ("open back", "open-back"), "automatic": ("quartz", "solar", "eco-drive", "eco drive"),
    "mechanical": ("membrane",),
}

# --- Converge round 1: ws-data-kitchen (17 Oct 2026) ---
# A product named only by its brand is its brand's line (the coordinator's technical call of 17 Oct 2026, within Noemi's
# decision 8 of 16 Oct 2026 and her 12 Oct 2026 rule on brand-only names; engine.pipeline._brand_only_lines): when every
# name of a group is the brand (or another name its brand-lines entry gives it) alone or with words that name no model,
# no facts or price entry names one product of it, and its brand-lines entry says the brand sells the requested type, it
# is ranked and shown as that line ("Circulon frying pan line"), and a must-have leaves it out as a whole brand. False
# keeps such a group one product, as before.
BRAND_ONLY_NAMES_AS_LINES = True

# --- Converge round 1: ws-data-beauty (17 Oct 2026) ---
# Mature skin in the words writers use (decided by Claude, 18 Oct 2026, from the skincare data round; reported to
# Noemi). In threads about mature skin, writers mostly give their age as a number ("I'm 46", "46F", "a 58 yo", "44 yr old") rather
# than a decade ("my 40s", which NEEDS already reads), so the need rule (a pick needs a credible recommendation that
# talks about the request's needs) found almost no voice about mature skin, and "night cream for my 40s" kept one pick
# however many threads about it were read. An age of 40 to 79 written as an age talks about mature skin, in comments
# only (NEED_COMMENT_WORDS: a number in a title is too loose to rank threads by); a number written any other way says
# nothing ("SPF 50+", "for 45 minutes", "40 pounds", and "50 f..." is left out, since "SPF 50 for" would read as an age).
# The signs of ageing and the decades in letters are mature words everywhere (NEEDS): sagging, crepey skin, menopause
# and perimenopause, forties to sixties.
MATURE_AGES = range(40, 80)
MATURE_AGE_FORMS = ("{n}f", "{n}yo", "{n} yo", "{n} y/o", "{n} year old", "{n} years old", "{n}-year-old",
                    "{n} yr old", "{n} yrs old", "{n}yr old", "{n}yrs old",
                    "i'm {n}", "im {n}", "i am {n}", "turning {n}")
NEED_COMMENT_WORDS["mature"] = NEED_COMMENT_WORDS.get("mature", ()) + tuple(
    form.format(n=n) for n in MATURE_AGES for form in MATURE_AGE_FORMS)
NEEDS["mature"] = NEEDS["mature"] + ("forties", "fifties", "sixties", "menopaus", "perimenopaus", "sagging", "saggy",
                                     "crepey", "crepiness")

# --- Converge round 1: ws-data-general (17 Oct 2026) ---
# Astra, the razor-blade maker, as its maker writes it (18 Oct 2026, the general data builder; Claude's call, reported):
# with the new razor threads, writers' "astras" (Astra Superior Platinum blades) became a pick of "razor for sensitive
# skin", shown as "Altra razor line": the brand-lines list's "Altra" (running shoes) was the only known spelling of a
# brand one letter away (engine.group_products.maker_spelling). A spelling of its own comes first, so it is shown as
# Astra; Altra's own names are unchanged.
MAKER_SPELLINGS["general"] = (*MAKER_SPELLINGS["general"], "Astra")
# lululemon, which writes its name in small letters (a maker's own style is taken from config only): with the new
# yoga threads, writers' "lulu lemon mats" became a pick of "yoga mat", shown as written.
MAKER_SPELLINGS["general"] = (*MAKER_SPELLINGS["general"], "lululemon")
# Brooklinen (bed sheets): with Brooks (running shoes) in the brand-lines list, writers' "Brook Linen" was shown as
# "Brooks Linen" on a skip list (the same slip between two makers' names as Astra's).
MAKER_SPELLINGS["general"] = (*MAKER_SPELLINGS["general"], "Brooklinen")

# --- Converge round 2: code (18 Oct 2026) ---
# The round-2 code builder's values (docs/bfs-2026-10-17/round2-additions.md and the orchestrator's list); Claude's
# technical calls within Noemi's rules, reported to her (DECISIONS.md, 18 Oct 2026).
# "What to look for" shows only tips about the type asked for (her blueprint of 8 Oct 2026 is the requested product's):
# in these categories' answers a thread read whose products are mostly of another type gives no tip unless the tip's
# own name names the type asked for (engine.pipeline._threads_about_another_type, engine.answer._look_for). A thread is
# about another type when fewer than LOOK_FOR_TYPE_SHARE of the products the AI found in it are of the requested type:
# a quarter keeps the threads comparing the type with a close one (headphones and earbuds threads, about a third each)
# and leaves out a yoga mat thread read for towels (one product in seven a towel) or a dog bed thread read for washing
# machines (none). Kitchen answers keep another kind of cookware as an alternative (10 Oct 2026: "Look for: cast iron"
# for a non-stick pan; tried on 18 Oct 2026 for kitchen tips naming another type of product, it also took "Avoid:
# non-stick pans" from cast iron skillet answers and "Look for: cast iron" from saucepan ones, so not kept); skincare
# and haircare have their own rule for another type's advice.
LOOK_FOR_OWN_TYPE_CATEGORIES = ("general",)
LOOK_FOR_TYPE_SHARE = 0.25
# Bean to cup (UK) is what US writers call a super automatic machine: one need, so the request's need-led reading finds
# the threads titled "super automatic ..." and its comments about them, and, named before the machine ("bean to cup
# coffee machine"), it is a feature the answer ranks by (Noemi's decision 1 of 16 Oct 2026; it had picked manual
# espresso machines). Found at the start of a word, as every need word is. Not "fully automatic": a request for a
# fully automatic washing machine would have asked about bean to cup.
NEEDS["bean-to-cup"] = ("bean to cup", "bean-to-cup", "beantocup", "super automatic", "super-automatic",
                        "superautomatic", "super auto")
FEATURE_CONFIG_NEEDS = FEATURE_CONFIG_NEEDS + ("bean-to-cup",)
# The daily plan job works out its requests one product type at a time (their order kept for what it reads first) and
# forgets what answers worked out between types (engine.precheck._work_out): one type's work kept at a time, so its
# memory no longer grows with the types it answers (it needed about 2.7 to 2.8 GB of its 3 GiB with round 1's library).
PLAN_ANSWERS_KEPT_TYPES = 1

# --- Converge round 3: logic (19 Oct 2026) ---
# The round-3 logic builder's values (docs/bfs-2026-10-17/final-review.md and the orchestrator's list); Claude's
# technical calls within Noemi's rules, reported to her (DECISIONS.md, 19 Oct 2026).
# A voice saying the opposite of a feature (her decision 1 of 16 Oct 2026; engine/features.py) or of a request's own need
# word never counts as talking about it (engine.features.says_its_opposite, engine.pipeline._needs_talked_about): open
# ear or bone conduction headphones, or a writer hearing the traffic around them, for noise cancelling (an open-ear pair
# recommended in a thread asking about ANC had been praised for it by the thread's ask); a bottle its writer says isn't
# insulated, or won't keep drinks cold, for keeping drinks cold. Lowercase, as the other asks' patterns are.
OPPOSITE_QUOTE_PATTERNS["noise cancelling"] = (
    r"\bopen[- ]?(?:ear|back)(?:ed|s)?\b",
    r"\bbone[- ]?conduct\w*",
    r"\bsituational awareness\b",
    r"\bhear(?:ing)? (?:\w+ ){0,2}?(?:surroundings|traffic|cars|everything around|the world around)\b",
    r"\b(?:don't|dont|do not|doesn't|doesnt|didn't|didnt) (?:really )?(?:care about|need|want) (?:the |any )?"
    r"(?:anc|noise[- ]?cancel\w*)",
)
OPPOSITE_QUOTE_PATTERNS["cold"] = (
    r"\b(?:not|isn't|isnt|aren't|arent|wasn't|wasnt|never|non|un)[- ]?insulated\b",
    r"\bno insulation\b",
    r"\b(?:doesn't|doesnt|does not|don't|dont|do not|won't|wont|will not|didn't|didnt|can't|cant|never) (?:really |"
    r"actually )?keeps? (?:\w+ ){0,3}?(?:cold|cool)\b",
)
# A product whose own name says it is an open design is never praised for noise cancelling: "open" at the start of a
# word of its name (OpenRun, Open Fit, open-back), or bone conduction (16 Oct's list had open-back only).
FEATURE_OPPOSITE_NAMES["noise cancelling"] = (*FEATURE_OPPOSITE_NAMES["noise cancelling"], "open", "bone conduction")
# Only tips about the type asked for (her blueprint of 8 Oct 2026; round 2 did it for general answers by their threads):
# a kitchen or general tip naming another appliance (these types, as whole words, a plural too, the longest name found:
# "toaster ovens" is a toaster oven, not a toaster) is left out of an answer for another type (engine.answer.
# _another_appliance): a pressure cooker in a dutch oven answer, a food processor in a blender one, rice cookers in a
# saucepan one, a heat pump water heater in a dehumidifier one. Kitchen keeps its exception of 10 Oct 2026, untouched:
# cookware, knives and tools are no appliances, so "Look for: cast iron" for a saucepan and "Avoid: non-stick pans" for
# a cast iron skillet stay; nor are a fridge's freezer or ice maker, which its own answers talk about.
OTHER_APPLIANCES: dict[str, tuple[str, ...]] = {
    "kitchen": ("air fryer", "blender", "bread maker", "coffee grinder", "coffee maker", "coffee machine", "deep fryer",
                "dishwasher", "electric grill", "electric kettle", "espresso machine", "food dehydrator",
                "food processor", "hand mixer", "ice cream maker", "immersion blender", "stick blender", "juicer",
                "meat grinder", "microwave", "milk frother", "pasta maker", "pizza oven", "popcorn maker",
                "pressure cooker", "instant pot", "rice cooker", "sandwich maker", "slow cooker", "soda maker",
                "sous vide cooker", "spice grinder", "stand mixer", "toaster", "toaster oven", "vacuum sealer",
                "waffle maker"),
    "general": ("heat pump", "water heater", "air conditioner", "air purifier", "humidifier", "space heater",
                "washing machine", "tumble dryer", "boiler"),
}
# In a general answer, a tip for another use than the request's (its name's words after "for", none of them the
# request's: "Windows laptop for accounting" in a gaming laptop answer) is someone else's (engine.answer.
# _for_another_use). What a kind is good for isn't a use: words opening with these say a reason or a price ("for a
# better angle", "for maximum accuracy", "for $200").
FOR_A_REASON_WORDS = ("a", "an", "the", "more", "most", "less", "better", "best", "maximum", "max", "extra", "longer",
                      "under", "over", "around", "about", "less", "every", "any", "your", "my")
# Care tips left out of answers altogether, like repairs (CARE_TIP_REPAIR_WORDS; the final review of 19 Oct 2026): DIY
# electrical work (rewiring a plug, earthing a metal case, a GFCI socket) and battery care (chilling batteries before
# charging, how full to store them), which are no advice on looking after the product asked for and, for wiring, unsafe
# to give. Regular expressions on the tip's whole words, as the repair words are; "grounds" (coffee) isn't "grounded".
CARE_TIP_LEFT_OUT_WORDS = (
    r"re-?wir(e|es|ed|ing)", r"wiring", r"(properly |well )?ground(ed|ing)", r"earth(ed|ing)", r"gfci", r"rcd",
    r"fuses?", r"electrocut\w*", r"short circuits?", r"live wires?",
    r"batter(y|ies)", r"charg(e|er|ers|ing|ed)", r"discharg\w*",
)
# A pick's first quote (the final review of 19 Oct 2026; engine.answer._naming_first): only the order of its quotes
# changes, never their words. One that swears (a word the page masks: engine.answer.MASKED_WORDS), opens by telling
# readers to ignore, avoid or not buy it (or that its writer can't recommend it), names the product only as the
# yardstick for another ("as good as my X") or is about a sibling of it (another product of its brand:
# "Cetaphil Gentle Clear Acne" for Cetaphil's Gentle Skin Cleanser) comes after a quote of its kind that doesn't.
# Lowercase regular expressions; the negative ones on its first sentence.
QUOTE_NEGATIVE_OPENINGS = (
    r"\b(?:ignore|avoid|avoided|steer clear|stay away|don't bother|regret)\b",
    r"\b(?:can't|cant|cannot|couldn't|wouldn't|won't|don't|do not|never|not) (?:really |personally |honestly )?"
    r"recommend",
    r"\b(?:don't|do not|wouldn't|would not|never) (?:buy|get)\b",
)
QUOTE_YARDSTICK = (r"(?:\bthan|\bas \w+(?: \w+){0,5} as|\bcompared (?:to|with)|\bsimilar to|\bjust like|\bthe same as)"
                   r"(?: (?:my|the|a|an|our|your|their|his|her))?(?: \S+){0,2} $")
# The daily plan job's requests (engine.precheck.requests_to_check: the blind-test questions, the demo and interviewee
# requests of engine/data/demo_requests.json, then the rest): at most this many, so its working out (486 requests took
# about 5 minutes on Noemi's computer with the model off, 18 Oct 2026) stays well inside its 55-minute task timeout,
# which the free-tier sums count (engine/tests/test_cloudrun.py). Claude's bound.
PLAN_MAX_REQUESTS = 650

# --- Round 4 of the convergence (19 Oct 2026, Noemi's decisions of 19 Oct 2026; DECISIONS.md) ---
# (g) Essences stay out of toner answers (her decision): {the type asked for: the kinds of product that aren't it,
# though module 1 routes their name to it}. A product the AI types as one of these, or whose names call it one and never
# the type asked for, is another type in its answers ("COSRX Snail 96 Mucin Power Essence" in a toner answer; a
# "Pyunkang Yul Essence Toner" is a toner), unless the request names that kind itself ("hydrating essence" still
# routes to toners and keeps its essences). Whole words, lowercase, a plural "s" allowed.
KINDS_KEPT_OUT_OF_TYPE = {"toner": ("essence",)}
# (i) For fast-moving tech (FAST_MOVING_TYPES; her decision: "not super old tech, but let's make sure other options still
# relevant count"): a comment older than this many years, counted back from the answer's day, says nothing for or
# against a product unless the product, or the line it is, is known to be still sold (a price-list entry counting it
# as sold, abroad too: her decision (c), no country preference; or a brand-lines entry saying the brand sells the
# type). Newer comments count as before. PROPOSED (Claude's value, waiting for Noemi).
FAST_MOVING_OLD_EVIDENCE_YEARS = 5
# (j) A credible warning against a whole kind of product (her decision: "electric sharpeners" for Japanese knives) pushes
# the products of that kind down: a kind whose credible notes warn against it more than they recommend it (its support
# below zero, engine.rank.kind_support) takes this many points off each of its products' scores, as the leading kind's
# products gain KIND_BONUS, so they rank below others with similar support. PROPOSED (Claude's size: the bonus's own).
KIND_WARNING_PENALTY = KIND_BONUS
# Item 10 (Noemi, 19 Oct 2026, of a pick's third quote that praised it and then asked the thread for something more
# moisturising: "that's not bringing any further info to the user"), under her rule 4 of 15 Oct 2026 (a quote is the
# most significant, coherent part of its comment for the stance it backs): a shown quote never holds a question asking
# for other products or for suggestions. It is cut to the part before the question that ends on a clause carrying its
# stance (at a sentence's end or at a turn: "but", "though"), or not shown (engine.answer._without_asking); a pick's
# other quotes make up its two. Lowercase regular expressions, read only inside a question (a sentence ending with
# "?"), so "I was looking for something better and found this" asks nothing; "Have you tried X?" suggests, it doesn't
# ask. Claude's patterns.
QUOTE_ASKING_PATTERNS = (
    r"\bany (?:other |good |better |more )?(?:suggestions?|recommendations?|recs?|ideas|alternatives?|advice|tips)\b",
    r"\b(?:suggestions?|recommendations?|recs|alternatives|ideas)\s*\?",
    r"\b(?:can|could|would|will) (?:anyone|anybody|someone|somebody|you|y'all|people) (?:please )?"
    r"(?:suggest|recommend|point me)\b",
    r"\b(?:what|which)(?: \w+){0,3} (?:should|would|do|could|can) (?:i|we|you|y'all|people)(?: \w+){0,2} "
    r"(?:recommend|suggest|use|try|get|buy|go for|pick)\b",
    r"\bwhat else\b",
    r"\b(?:anyone|anybody|someone|somebody) (?:recommend|suggest)\b",
    r"\b(?:anyone|anybody|someone|somebody) (?:have|has|got|know(?: of)?) (?:a |an |any )?(?:good |better |cheaper )?"
    r"(?:recommendations?|suggestions?|alternatives?|ideas|dupes?|substitutes?|replacements?)\b",
    r"\b(?:is there|are there|know of|looking for|recommend|suggest) (?:a |an |any |some )?(?:good |better |cheaper "
    r"|similar )?(?:alternatives?|dupes?|substitutes?|replacements?|recommendations?|suggestions?)\b",
    r"\b(?:anything|something) (?:else|similar|better|cheaper|richer|lighter|more|less|like (?:it|this|that))\b",
)

# --- Region (24 Oct 2026) ---
# Noemi, 24 Oct 2026: "the tool should work for visitors anywhere, not just the UK ... country-aware availability: ok,
# do it now". The page offers UK (the default), US and Elsewhere; the API takes an optional "region" in the POST body. A
# region changes the price and availability lines only: which picks are shown and their order never change (her decision
# (c) of 19 Oct 2026: no country preference anywhere in ranking), and the UK region is exactly as it was. Claude's
# technical values; the lines' wording is PROPOSED (engine/answer.py).
REGIONS = ("uk", "us", "elsewhere")
DEFAULT_REGION = "uk"
# What the price list says about the US (engine.prices.us_sale). Evidence that a product is sold in the US is a USD entry
# that isn't about a discontinued product (the entry's currency is its shop's), or a page of one of these shops among an
# entry's url and sources: the shop's address without "www." (matched exactly, never as a subdomain: "global.danner.com"
# is an international store) and the name the line shows. US retailers, and the US makers' own stores that appear in
# data/prices.json's entries for products not sold in the UK. PROPOSED, a list for Claude to extend as researchers read
# more US shops; a product with none of this evidence is simply not said to be sold in the US.
US_SHOPS = {
    "amazon.com": "Amazon US", "walmart.com": "Walmart", "target.com": "Target", "homedepot.com": "The Home Depot",
    "lowes.com": "Lowe's", "bestbuy.com": "Best Buy", "costco.com": "Costco US", "ebay.com": "eBay US",
    "macys.com": "Macy's", "kohls.com": "Kohl's", "nordstrom.com": "Nordstrom", "crateandbarrel.com": "Crate & Barrel",
    "roomandboard.com": "Room & Board", "garnethill.com": "Garnet Hill", "backcountry.com": "Backcountry",
    "oldnavy.gap.com": "Old Navy", "ulta.com": "Ulta Beauty", "sephora.com": "Sephora US", "dermstore.com": "Dermstore",
    "harborfreight.com": "Harbor Freight", "go.harborfreight.com": "Harbor Freight", "rei.com": "REI",
    "williams-sonoma.com": "Williams Sonoma", "wayfair.com": "Wayfair", "chewy.com": "Chewy", "petco.com": "Petco",
    "newegg.com": "Newegg", "bhphotovideo.com": "B&H Photo",
    "purple.com": "Purple", "upliftdesk.com": "UPLIFT Desk", "geappliances.com": "GE Appliances",
    "frigidaire.com": "Frigidaire", "kenmore.com": "Kenmore", "jennair.com": "JennAir",
    "hamiltonbeach.com": "Hamilton Beach", "mrcoffee.com": "Mr. Coffee", "sunbeam.com": "Sunbeam",
    "craftsman.com": "Craftsman", "ridgid.com": "RIDGID", "evenflo.com": "Evenflo", "gracobaby.com": "Graco",
    "babyjogger.com": "Baby Jogger", "eddiebauer.com": "Eddie Bauer", "danner.com": "Danner",
    "redwingshoes.com": "Red Wing", "thorogoodusa.com": "Thorogood", "johnboos.com": "John Boos",
    "duluthtrading.com": "Duluth Trading", "lovesac.com": "Lovesac", "casper.com": "Casper",
    "avocadogreenmattress.com": "Avocado Green Mattress", "parachutehome.com": "Parachute", "article.com": "Article",
    "flexsteel.com": "Flexsteel", "mypillow.com": "MyPillow", "levolor.com": "Levolor", "speedqueen.com": "Speed Queen",
    "vanicream.com": "Vanicream", "all-clad.com": "All-Clad", "saddlebackleather.com": "Saddleback Leather",
    "tarptent.com": "Tarptent", "durstongear.com": "Durston Gear",
}
