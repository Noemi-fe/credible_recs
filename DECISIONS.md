# Decisions and build notes

Dated, oldest first (moved from CLAUDE.md's Open items on 18 Oct 2026). Noemi's decisions say so; "Decided by Claude" and "Built by Claude" notes are technical calls reported to her. Add new notes at the end.

- Generic types ("a carbon steel pan") aren't product mentions, but credible advice about them is kept separately as "what to look for" notes, shown as a short blueprint under the picks (Noemi, 8 Oct 2026). Extraction instructions v2 and module 7; also for brief version 5.
- When modules 5–6 exist: if a request lacks enough credible evidence (fewer than 3 credible mentions across 2 threads), fetch more threads automatically, smaller ones included, before giving up (Noemi, 7 Oct 2026).
- Arctic Shift's comment search times out on any search of two words or more, even within one month (8 Oct 2026); one-word searches with `fields=id,link_id,score` work and download no text. Warning threads are found by title for now.
- Commenter history (Noemi's idea, approved 9 Oct 2026), for module 5: from Arctic Shift, numbers only (subreddit, score, date of each comment; no text), turned into "active in this topic's communities" and "usually upvoted there". Keep only those derived numbers per username: since 9 Oct 2026 (Noemi's decision 1) in data/library/profiles.json, refreshed with the library every 30 days (engine/profiles.py).
- Kind-level advice in the ranking (Noemi, 8–9 Oct 2026): if one kind ("Japanese gyuto") gets far more credible support than another, its products rank first. Kinds are open-ended (her choice, 9 Oct): labelled as rows with kind = yes and extracted as the AI's notes; for each request, the kinds found in its threads are grouped and each product placed in a group (modules 4 and 6). How much kind support moves a product is her decision.
- Warnings: only exfoliant, cleanser, electric kettle and frying pan are thin (8 Oct 2026). Plan approved 9 Oct: when Arctic Shift answers, find one big "most regretted / overhyped products" thread each for skincare and kitchen (4 Parse credits); otherwise wait for November's credits.
- Decisions of 9 Oct 2026 (Noemi approved all 13 recommendations):
  1. Commenter profile numbers (activity since, contributions, karma, flair) are kept with the library and refreshed monthly with it, not only 48 hours: they are public metadata, not the archived text the deletion rule is about.
  2. Extraction instructions v6: the AI also writes each product's type and an evidence level with tags; Noemi's kettle thread (1tfk6nm) is the fair test of v6, then the whole library is extracted again with it.
  3. November credits: about 60 to bring every blind-test product type to 6 or more threads about it (candidates in data/library/candidates.json).
  4–8. Module 5 and 6 values decided as proposed: voice and evidence values 1 / 0.5 / 0.25, honesty bonus +10% per sign; credible mention = recommend or warn from a high or medium voice with first-hand use; picks need 3 credible recommendations across 2 threads and a positive score; skip list needs 2+ credible warnings and more warnings than recommendations; mixed-opinions flag at 1+ credible recommendation and 2+ credible warnings; kind bonus +1 when a kind leads the next by 2x.
  9. A brand-only name can be a pick when its threads make the product clear, labelled as such ("Lodge (their cast iron skillets)").
  10. A product that failed after a long life counts as recommend (long-term use, mentions flaws), not warn.
  11. Budgets: current prices for each blind-test question's shortlist, looked up by Claude with the shop and the date.
  12. The 75 matching pairs, variant words and alias list approved; the UK name "Sage" is shown rather than "Breville".
  13. New voice tags "replies agree" and "downvoted". Voice rubric (Noemi, 9 Oct 2026, replacing "a red flag means low"): one red flag caps a voice at medium; two or more make it low; clear paid promotion (a code, an affiliate link, #ad) is low on its own.
  Later the same day: budgets with no currency assume £; brand-only names may appear on the skip list; a brand-pick name drops the "(their …)" bracket when the name already says the type; a product counts as the thread's type unless said otherwise, and the AI looks a product up online when unsure (instructions v6).
- Decided by Claude on 10 Oct 2026 (reported to Noemi): (1) a pick folds into its own brand's specific product, brand picks are left out under hard requirements, care tips go by agreement; (2) new fact maker_warns_sensitive (recorded only when a maker's page says it; leaves a product out of sensitive-skin requests; never a requirement); (3) a pick whose facts can't confirm a hard requirement keeps its place with a note ("we couldn't confirm it's PFAS-free"); (4) prescription_only is a fact of retinoids and exfoliants only (of any skincare type since 14 Oct 2026, Noemi's decision 5, a requirement still only for these two); (5) a mention the AI types as a set, block, sharpener, stand and so on (config.OTHER_TYPE_WORDS) never counts for the product itself; (6) a pick with a facts entry is shown under the entry's name; (7) Dermalogica Microfoliant is priced at its full size (£65), so it is over a £30 budget; (8) later the same day: a brand pick is left out when every specific product of its brand in the threads is known not to be sold in the UK; two brand picks of the same brand fold into the one ranked higher; PIPELINE_MAX_THREADS is 12 (8 gave 6/10 full top 3s, 12 gave 9/10; raised to 16 late on 10 Oct 2026: 10/10 full top 3s with live checks on the 150-thread library); a "Tretinoin" facts entry and the alias "tret".
- Decided by Claude late on 10 Oct 2026, from reading the 10 blind-test answers as a tester would (reported to Noemi): a product written without its brand takes it from a longer name when the brand is written on its own elsewhere ("Fellow Stagg", not a bare "Stagg"; engine/group_products.py); groups that find the same facts entry are one product, ranked together (b02 had "Biore UV Aqua Rich Watery Essence SPF50" as a pick and a skip); a brand or line on the skip list that a shown pick belongs to isn't listed as a skip, its warnings go under that pick's Known downsides ("Lodge pans" next to the pick "Lodge"); module 5 reads "about to try" and "can't review it yet" as untried, and a common product word ("cleanser") is never a one-letter slip of a name ("Gleanser"). Later that night: a price-list entry under a brand's name, alone or followed only by the product type's words ("OXO kettle": OXO's kettles are 120 V, not sold in the UK), speaks for the brand pick, so "not sold" leaves it out unless one of its products here is known to be sold; a light moisturiser for a dry-skin request gets a note (config "light texture", moisturisers only); PIPELINE_MAX_THREADS 16. Then, from reading the blind-test view (engine.blind_test.shown_from_ours): among equally clear quotes, those whose own words talk about the request's needs come first (quotes and downsides); a skin reaction or its absence ("doesn't cause a rash") talks about sensitive skin; '8 inch' reads as '8"' in matching; a brand pick's named model with no single price says where it is sold; links in our quotes become "(source)" in the template (FORMAT.md rule 4); kind advice follows the hard facts rules (no "Look for: tret" for a beginner); a facts entry under a brand's own name (alone or with the product type's words, and of the request's type) speaks for its brand pick, as GreenPan's FAQ ("all our pans are PFAS-free") does, so b10's first pick is GreenPan. Data: 3 threads added for b04 (very dry skin / winter moisturisers) through Bright Data and extracted with v7.
- Decided by Claude in the night of 10 Oct 2026 (reported to Noemi): pack sizes (ml, g, oz) aren't part of a product's name (litres and inches still are), so a full-size price entry is found whatever the group is called (a £65 Dermalogica had led b01, which asks for under £30); a quote names its product when it uses its writer's own name for it ("Stagg" for "Fellow Stagg EKG"); "a decade" and "never failed" are experience, "failed" alone isn't; among quotes that don't name the product, those giving a view come first; a time the reader could keep something ("you could buy one and keep it for decades") isn't the writer's use; aliases for Paula's Choice's Skin Perfecting 2% BHA (two writers' names were two products) and CeraVe Hydrating Cleanser (the UK name of the Hydrating Facial Cleanser); no texture fact for a foaming cleanser (how it dispenses isn't how it feels); YesStyle prices count for UK shoppers, as before. Data: 3 exfoliant threads for b01 through Bright Data (3,729 of 5,000 records this month) and prices and facts round 8. Comment text copied into tests and code comments was replaced with made-up text after a scan of tracked files for 8-word runs found in the saved threads.
- Noemi's decisions of 11 Oct 2026: (1) care tips are only advice on looking after the product itself, stated (never a question or a guess), under the heading "How to take care of it" (was "How to make it last"); a pick shows the tips about itself, and the tips about its kind of product are shown once, in a note at the end of the answer, not under every pick (extraction instructions v8; config.CARE_NOTE_TIPS); (2) a pick whose facts can't confirm a must-have keeps its place with a note, but research goes deeper before settling for one, so such notes stay rare: the maker's FAQ and help pages, care and use guides, manuals and packaging, its pages in other countries and languages (Korean and Japanese makers), safety or regulatory documents, and UK shops quoting the maker; a coating the maker names as PTFE (Teflon) answers pfas_free: false, since PTFE is a PFAS under the OECD definition the UK and EU use; a fact about a brand's or line's range is judged on what UK shoppers can buy (decided by Claude, 11 Oct 2026: Scanpan's non-stick lines sold in the UK are all PTFE-based, and its PFAS-free Qraft line isn't sold here); (3) a comment that copies another writer's comment word for word is a red flag in the voice rubric, and copies count once (only the first posted counts; later copies' mentions, notes and care tips are left out); later the same day: "recent" counts for nothing in the voice rubric (weight 0: it fired on every labelled comment); b10's thin answer left to Claude's judgement ("whatever makes the tool the most reliable source of credible info"); the per-subreddit archive she approved downloading is no longer published (Academic Torrents returns not found), and the monthly archive is all of Reddit (3.8 TB), so nothing was downloaded; Arctic Shift's title search covers the need; (4) r/acne is a decided skincare subreddit (searched first for acne requests, config.CONDITION_SUBREDDITS); (5) old commit messages that quote short comment phrases stay as they are for now (no history rewrite); new ones never quote comments.
- Decided by Claude on 11 Oct 2026 (reported to Noemi): the library is read in module 2's graded order (engine.sources.post_score, the ranking her retrieval judgements grade: advice, the request's needs, long-term use, comments), not only by whether a thread names the product; b10's thin answer got 4 threads asking its exact question, found with Arctic Shift's free title search and read live through Bright Data; "gives you a white cast" says the opposite of a no-white-cast request, and a quote saying the opposite of an ask gets no boost for talking about the request; a hoped-for time ("if I get a year out of it", "hopefully it lasts 10 years") isn't the writer's use; Anessa's facts entry is named as the maker names it, with aliases for the writers' forms; "Gleanse" and "Gleanser" are never a spelling slip.
- Decided by Claude on the evening of 11 Oct 2026 (reported to Noemi): module 1's free open model (her choice): Qwen2.5 1.5B Instruct, q4_k_m GGUF (Apache-2.0), run through llama-cpp-python 0.3.16 (`.venv/bin/pip install -e ".[model]"`; the file lives in models/, git-ignored). The rules go first; the model is asked only when they can't place a request, and its answer is checked by code (engine/query_model.py): the product must be in the request's own words, category and place words ("kitchen gadget") aren't products, "other" is the polite no; a type the rules don't list becomes a product type of its own, found in threads by its whole name. `CREDIBLE_RECS_QUERY_MODEL=off` turns it off; tests never load it (conftest). Haircare is a category (Noemi asked for shampoo answers): shampoo, dry shampoo, conditioner, leave-in conditioner, hair mask, hair oil, from r/HaircareScience, r/curlyhair, r/wavyhair, r/Hair, r/femalehairadvice, r/malehairadvice, r/Dandruff (chosen by Claude); hair tools stay out of scope; extraction instructions v9 (v8 stays current for skincare and kitchen threads: config.EXTRACT_STILL_CURRENT); old haircare comments are capped like skincare ones (config.REFORMULATED_CATEGORIES). Phrases that hold a product's word but name something else are set aside (engine.query.LOOKALIKES: "ice cream maker", "crock pot", "vacuum sealer"); a skincare clue word ("cream") doesn't place a request about hair; a makeup remover is a cleanser.
- Decided by Claude late on 11 Oct 2026, from the data builders' findings (reported to Noemi): an answer short of picks reads more threads before giving up (her decision of 7 Oct, built for the library): 16 first, then up to 48 (config.PIPELINE_MORE_THREADS), kept only if it has more picks, and in that wider reading a pick needs a credible recommendation that talks about the request's needs (else every shampoo request got the same popular picks); "sulfate-free" is a checked requirement like PFAS-free (fact sulfate_free, shampoos); the product's own name is never a need ("dry" in "dry shampoo"), "anti-X" and "X-free" ask about X, "hair" is a stopword like "skin", "recs" asks for advice; only the head word marks a set or stand ("stand mixer" is a mixer), and for a type the open model named, the AI's type must end with it and not be another kind (config.OTHER_KIND_WORDS: an immersion blender isn't a blender); a request placed by a clue word alone also gets the model's reading ("rice cooker with a non-stick pot"); a time over config.USE_MAX_YEARS (60) isn't anyone's use; the archive's free search covers every decided subreddit, 100 posts each, older threads too, and goes on past a timeout (config.ARCHIVE_*); a comment link that doesn't point to its own thread is rebuilt (the archive's 2012 "t3_" links had stopped every answer).
- 12 Oct 2026 (Noemi's requests and decisions; Claude's calls reported to her): every answer says how many threads and comments it read ("Based on 48 Reddit threads and 1,402 comments", API "reading"); hosting is Google Cloud Run in her project credible-picks (europe-west1, free tier, max one instance, a 1 EUR budget alert; deploy/cloudrun/, `sh deploy/cloudrun/deploy.sh`), feedback goes to her private Hugging Face dataset Noemix/credible-recs-feedback, GoatCounter site code noemix (in .env and the Cloud Run settings, not in the repo); brand-only names count when data/brand_lines.json (researched, with sources) says the brand makes the requested type, and brand picks are named "<Brand> <type> line" (her wording); a "tea kettle" is a stovetop kettle unless it says electric. Gemini (her key GEM_API_KEY, engine/gemini_extract.py): on her 3 labelled threads Gemini 3.8 Flash read whole found 84% of her products (precision 93%), read in parts of 40 comments 89% on two of them (Claude: 97%, 94%); Claude's call (she left it to Claude): Gemini reads new library threads in bulk, Claude keeps the gold set and blind-test threads; the free allowance's daily limit (429) caps bulk reading, so paid use is her decision. Under Google's terms UK users get paid-tier data terms (not used for training) even for free use.
- Latency (12 Oct 2026, the latency builder; eval/latency.py, eval/LATENCY.md): the library, lookups, matching and each comment's signs are kept in memory between answers, and the server gets ready as it starts; live checks of shown quotes now run 8 at a time, paced under Reddit's embed limit (about 200 reads per 10 minutes per address: 40 at once, then one every 4 s), and keep going until every shown quote has passed. Warm answers dropped from 7.7 s to 0.4 s (p50) with checked quotes cached; a fresh answer is bounded by Reddit's read limit. Remembered answers are worked out again after 24 hours (web.ANSWER_KEEP_HOURS), within the 48-hour rule. Check ahead (built 13 Oct 2026; engine/precheck.py): daily at 4 am UK time, a Cloud Run job reads ahead the comments answers would show and the ones next in line, at most 1,100 reads (config.PRECHECK_*; since 14 Oct 2026, Claude's call: at most 2,000 reads and no read 75 minutes after the run started, so its bill stays inside the free tier whatever Reddit's pace: about 1,700 reads, where 1,100 had left 459 of 1,967 comments unread); checks are shared through the private bucket credible-picks-live-checks as one bundle, written by the job twice a run and read by the site at most hourly; the site never writes to it (objects deleted at 2 days, never used past 48 hours). Since the free-tier redesign of 14 Oct 2026 (below) the site reads ahead and writes the bundle, and the job only plans.
- Noemi's decisions of 13 Oct 2026: (1) Reddit's embed limit: check ahead. The quotes answers would show are checked live in advance, daily, within Reddit's limits (not only when about to be shown); a shown quote still needs a passing live check from the last 48 hours, and a failed or stale one is checked again or never shown; (2) picks rule: 3 credible recommendations across 2 threads stay the bar for the top picks, and products with 2 are shown apart under "Also worth a look", clearly labelled as less supported; (3) no paid Gemini: Gemini reads threads only within its free allowance, Claude stays the main reader; (4) one-line summaries per pick, written ahead of time from the pick's verified credible quotes, labelled as a summary (never in quotation marks), to try and judge.
- Noemi's decisions of 13 Oct 2026 on names and lines (from the name-merge builder's questions): (1) under a hard requirement, a brand line may still be listed under Skip these when its credible warnings put it there (never as a pick); (2) co-wash: types stay strict, a conditioner recommended for co-washing doesn't count for shampoo requests; (3) every brand line is shown as "<Brand> <type> line", also when its name already holds the type ("Davines conditioner line"), replacing the 9 Oct rule.
- Noemi's decisions of 13 Oct 2026 on ingredient questions (after her live test of "salicylic acid for acne"): a request naming an active ingredient shows only products with evidence they contain it (the ingredients builder's design, engine/ingredients.py); (1) forms: leave-on forms only (serum, liquid, toner, pads, cream, spot treatment); a cleanser or other rinse-off form counts only when the request names it ("salicylic acid cleanser"); (2) spot treatments (incl. pimple patches) become a product type, with threads added in the next data round. Claude's calls, reported: a product line whose versions differ (only some contain the ingredient) is left out; "retinol" keeps routing to the retinoid type with no extra requirement (her q05 call of 7 Oct).
- Noemi, 13 Oct 2026 ("Keep only comments we use"): Bright Data's free tier can't re-read the whole library monthly (~22 records a thread, ~9,600 a month for 436 threads, 5,000 free), and archive text not checked live within about 37 days must go. So the saved library keeps each thread's title and only the comments the answers use (those with extracted mentions, care tips or kind notes), plus the non-text facts the scoring needs from the rest (scores and reply counts, never their words or writers), and keeps those comments current through Reddit's embed page (free): a comment not verified within the deadline, deleted, edited or that the embed page can't show loses its text and its mentions. Gold-set threads are unchanged (Noemi's, on her machine).
- Built by Claude, 13 Oct 2026, from Noemi's decisions on ingredient questions (the ingredients builder; reported to her): (1) forms: an ingredient-led answer keeps a product with the ingredient only when its form is leave-on (config.LEAVE_ON_FORMS: serum, leave-on liquid, toner, pads, essence, cream, lotion, gel, oil, balm, sunscreen, spot treatment, patch, sleeping mask...), or one the request names next to the ingredient ("salicylic acid wash", "salicylic acid pads": constraints.forms, engine.ingredients.forms_named); a rinse-off one (cleanser, rinse-off powder, peel, mask, scrub) is left out with "a rinse-off cleanser: ask for a salicylic acid cleanser to see these", and an exfoliant whose name and facts don't give its form is left out as not confirmed leave-on (never guessed); all are counted (left_out_by_form; the footnote says how many, and the answer's note says how to see a cleanser). A cleanser still shows for "salicylic acid cleanser" (its own type). (2) "spot treatment" is a skincare type (spot treatments, spot gels and creams, pimple, acne and hydrocolloid patches and stickers; a hydrocolloid bandage, plaster or dressing, a blister plaster and a dark, age or sun spot are look-alikes), searched in r/acne first (config.CONDITION_PRODUCT_TYPES), a leave-on form ingredient-led answers may show (acids, benzoyl peroxide and azelaic acid); extraction instructions v10 add its name and keep every v9 extraction current (the AI had typed patches "pimple patch"). An alias joins the writers' "Mighty Patch" to Hero Mighty Patches.
- Noemi, 14 Oct 2026 (night): (1) brand-line picks get a link to the maker's range page for the type (from data/brand_lines.json's researched sources) and a researched, sourced, dated "From £X" price so lines can be checked against budgets (display and budget check only; how picks are chosen doesn't change); (2) upvotes: "let's be reasonable. if we have few credible mentions, a highly upvoted comment (10+) counts more": build it switched off (a config flag) and show her which picks would change before it is turned on; only a comment that is already credible can count more, and a pick still needs credible recommendations across 2 threads.
- Built by Claude, 14 Oct 2026, from Noemi's night decision 1 (the line-links builder; reported to her): a brand-line pick, and a line under Also worth a look, links to its brand-lines entry's range page ("Browse Victorinox chef knives", then "checked <date>": the day its sources were read; "... at <shop>" for an official UK stockist's page) and shows its from price ("From £25 at Victorinox UK, checked 14 Oct 2026", with the shop's link, and "Sold at <shop>", since the researcher found it on sale there); within a budget, "From £25, within your budget (up to £100)."; over it, the line is left out as before. Both come from data/brand_lines.json, never from a comment, and change nothing about which products are picks. Format: range_page (one of the sources, exactly as written), range_shop (a stockist's page), and from_price_shop, from_price_url (one of the sources) and from_price_checked_on, all three with a from price (one without them still leaves a line out under a lower budget, as on 12 Oct, but isn't shown). API: "range" on picks and items, "from_price" on prices (engine/web.py); the page checks a range link with its own rangeUrl (https, no name or password, never Reddit's) and says "From £X" in At a glance and an item's row; the how page explains both. Claude's calls: the brand as its maker writes it, no possessive (some entries are a line of a brand: "Instant Vortex Plus"); from prices from the maker's UK site, an official UK distributor (Tojiro's) or a big UK shop (Harts of Stur counted as one for Global), of full-size products only (no travel packs, minis or refill pouches: the 10 Oct Dermalogica rule), a product out of stock for now counting as sold (the price list's convention), a discontinued one not; no reliable UK price, no from price, and the note says why. 16 entries added for lines shown without one (Sage and Ninja kettles, Global, Mercer, GreenPan, OXO, Dualit, Tatung, Instant Vortex Plus, Hario Mini Mill, Herbal Essences, BYOMA, CeraVe, ILLIYOON, COSRX), so "illiyoon moisturiser line" is now shown as "ILLIYOON moisturiser line" (the 12 Oct rule for a lowercase brand with an entry). No range page for Bonavita (its site refuses connections); no entry for Griswold (no maker since 1957, sold second-hand only) or Wilfa Svart (Wilfa's own UK blog, 30 Jul 2026: Svart grinders discontinued, final stock only).
- Decided by Claude, 14 Oct 2026 (reported to Noemi): Gemini's free daily allowance is about 20 calls (a handful of threads), shared by everything using her key; it is reserved for the live site's on-demand reading (what visitors trigger). Bulk and data-round threads are read by Claude (builders), as before.
- Noemi's decisions of 14 Oct 2026 (morning, "yes to all" of the morning summary's six): (1) she creates the Gemini key's secret herself (on-demand reading stays off until it exists); (2) module-1 eval cases q28 (laptop), q29 (hair dryer) and q30 (dishwasher) relabelled as products, since "regardless of the category" supersedes her 7 Oct out-of-scope calls; (3) the upvote rule on, variant D (a credible recommendation with 10+ upvotes, in the top 10% of a 20+ comment thread, counts twice, only to fill a place the picks leave empty); (4) for haircare, a pick needs a credible recommendation that talks about the request's needs in every reading (option B); (5) a "prescription-only in the UK" note on prescription products wherever shown, and the fact settable on any skincare type; (6) the general category's polite nos stand (food and drink incl. pet food, medicines and supplements, books/films/games/apps, weapons, drugs, tobacco, vaping, adult products), and the builders' PROPOSED wording (polite nos, home page, departments, on-demand and no-threads messages) is approved.
- Noemi, 14 Oct 2026: "I want recs regardless of the category". Plan (Claude's, reported): (1) any product request is understood (a general category beside skincare, haircare and kitchen; same credibility rules, verified quotes and live checks for all); (2) a broad library prepared ahead for about 300 popular product types across categories, from the per-subreddit history files (more communities, shown to her with sizes before download) and Arctic Shift's API; (3) on-demand reading: a request about a product not read yet is queued, the site says so honestly, and a scheduled Cloud Run job finds and reads threads (Gemini free tier, quotes verified, slimmed) so the next ask gets an answer.
- Noemi, 14 Oct 2026 (breadth is the priority: "this project could get me a job"; Reddit never answered her API requests): (1) bulk history from Arctic Shift's published per-subreddit files (Academic Torrents), downloaded with aria2 after she sees the exact files and sizes; threads are chosen locally, only chosen threads enter the library (then extracted and slimmed as usual), and the raw files are deleted within 48 hours; (2) Gemini stays free tier only (she declined paid use again), Claude reads the rest; (3) more product types (kitchen appliances such as microwave and oven) and need-led thread choice. Not done, on purpose: multiple Arctic Shift identities to get round its limits (it has no accounts; it would mean evading a volunteer service's limits).
- Built by Claude, 14 Oct 2026 (the on-demand builder, branch on-demand; decided by Claude, reported to Noemi): on-demand reading, part 3 of her plan (engine/on_demand.py; deploy/cloudrun/DEPLOY.md, "On-demand reading"). On the live site, a request module 1 understands whose product has fewer than 6 extracted threads (config.ON_DEMAND_MIN_THREADS, the library's mix) is queued in its own private bucket, credible-picks-on-demand (on_demand/queue.json; a bucket apart from the live checks' because its objects must outlive their 2 days: deleted at 37 days, the archive's keeping time), holding only the product type, category, subreddits and up to 3 need words (never the request as typed, nothing about the visitor; one entry per product and need words); the answer says so ("We haven't read Reddit about teapots yet, so we've started: check back in about 20 minutes."; the API's "on_demand", the page's "Reading Reddit for you" notice; wording PROPOSED) and isn't remembered. No third Cloud Scheduler job: the site starts the reading job (Cloud Run job credible-recs-reader, jobs:run) as it queues, and the keep-warm ping starts it again when a start failed, so there are no empty runs. The job holds the queue with a lease, finds threads with Arctic Shift's title search and reads them from its archive (ArchiveSource, its own pace; no Bright Data, no Parse; threads already saved left out), has Gemini extract them one at a time (free allowance only: at most 100 calls a day of its own, none more after Gemini's daily 429 until 8 am UTC; engine.gemini_extract now stops a batch at the daily limit), runs the word-for-word check, slims them when engine.slim is there (kept whole until lean-library is merged), and bundles them (on_demand/threads.json); at most 50,000 s of runs a month (with the pre-check, 81% of Cloud Run jobs' free vCPU-seconds in the worst month; 88% since the pre-check's 75 minutes of 14 Oct 2026, summed by engine/tests/test_cloudrun.py). The site takes the threads in at the keep-warm ping (never over a baked thread), the pre-check covers the queue's products, and deploy.sh pulls them into data/library before building (`python -m engine.library pull-bucket`) and lets the bucket go of them after (`forget-baked`). The Gemini key is the Secret Manager secret gemini-key, which Noemi creates herself (DEPLOY.md has the one-line command); while it is missing, deploy.sh deploys the site with on-demand reading off (the orchestrator's change, so a missing key never stops a deploy). The how page's privacy section says what the queue keeps.
- Built by Claude, 14 Oct 2026, from Noemi's decision 3 of 14 Oct (the breadth-types builder; reported to her): (1) 17 kitchen appliances are module 1 product types routed by the rules (engine/query.py): microwave, oven (range cookers, wall ovens; a gas or electric range or cooker is a clue), toaster oven (countertop and air fryer ovens), air fryer, blender, food processor, stand mixer, hand mixer, slow cooker (crock pot), rice cooker, pressure cooker (multicookers, Instant Pot), coffee maker (drip and filter machines; a plain "coffee machine" stays an espresso machine), French press (cafetiere), toaster, waffle maker, juicer, kitchen scale, each with its plural, title words and communities most specific first; 6 kitchen subreddits added (Appliances, airfryer, instantpot, slowcooking, Baking, juicing); look-alikes set aside (microwave popcorn, oven gloves, a pizza oven, oven-safe, what goes in the oven, microwave or dishwasher, immersion, stick and hand blenders, toaster bags; one that starts inside a longer product name stays: "a dutch oven safe to 260c"); cleaning products and bathroom scales are out of scope; the seven the open model placed are module 1's own (config.PRECHECK_MODEL_TYPES keeps "body wash"). The dishwasher stays out of scope, as her approved module 1 case q30 says (her call of 7 Oct: large appliances aren't kitchen gear): whether it comes in is her call (adding it makes module 1 29/30 until q30 changes). Extraction instructions v11 list the new names (v10 and v9 extractions stay current). Advice about a look-alike of a listed type is no advice for it (an immersion blender for a blender, a bread knife for a chef's knife). (2) A haircare request's needs are its own (config.HAIR_NEEDS: oily hair, dry hair, dandruff, an itchy or sensitive scalp, fine hair, frizz, curly, wavy, colour-treated) in place of the skin types; "quiet" and "glass top stove" are needs for every category; "works" and "scalp" aren't needs of their own. (3) The library's first reading is need-led (engine.sources.LocalSource): the threads whose title or post talks about the request's needs come first, most needs first, unless the title names another type ("SPF for oily skin?" isn't a moisturiser thread); requests without needs and ingredient-led ones read as before, and rank_posts (what her retrieval judgements grade) is unchanged. Need eval (eval/edge_cases/needs.json, engine/need_eval.py, run by eval/run_eval.py): first-reading threads about the need 38/160 -> 67/160 by title or post; blind-test top 3s unchanged (8/10).
- Built by Claude, 14 Oct 2026 (the upvotes builder, branch upvotes; Noemi's night decision (2) above; reported to her): her upvote rule, switched off (config.UPVOTE_COUNTS_MORE = False) until she has seen its effect (eval/RUNS.md, 14 Oct 2026, and the builder's effect report). With it on, a credible recommendation (upvotes never make a comment credible) whose comment has 10 or more upvotes (config.UPVOTE_MIN_SCORE, its score) counts as two toward the picks bar (engine.rank.counts_twice): never a warning, never more than twice, never in place of the second thread; the score, the tie-breaks, Skip these and the mixed-opinions flag still count writers. Module 5 gives each comment's upvotes beside its thread's (engine.credibility.thread_upvotes). Variants, by config: A any product; B only a product short of the bar, as far as the bar; C as B, the comment scoring higher than 90% of its thread's comments in a thread of 20 or more readable ones (her earlier "needs to be a high quality thread"); D as C, a product it lifts only filling a place the picks would leave empty (config.UPVOTE_ONLY_TO_FILL, added by Claude after the first effect run; the settings name D, the variant proposed). In every variant nothing leaves the answer (a lifted product its score keeps out of the picks stays under Also worth a look; the first run had lost 6 such items) and how much an answer reads doesn't change (the reading is chosen as with the rule off, then ranked again with it from what it read, never read twice, and an answer it changes nothing in is written once: ranked with it, dandruff and oily-scalp answers had stopped before their need-led wider reading; a second reading had doubled a warm answer's time, ranking again costs about 0.1 s). The answer says so while it is on: the reason ("Recommended by 2 credible voices (one counted twice for its 12 upvotes), ..."), the meter (writers, and "1 counted twice for its upvotes"; the API's voices "twice"), the messages' bar ("..., or 2 when one of them has 10 or more upvotes") and the how page. In practice it can only lift a product with exactly 2 credible writers from 2 threads (today's Also worth a look). Effect on the frozen library, offline, 36 answered requests, on main at ae5a498: A, B and C give the same picks (A also says "counted twice" on 45 picks that met the bar anyway; C's thread rule dropped 5 lifts, none shown): 5 answers change, the frying pan (b10) and anti-dandruff answers gain a third pick and four shampoo answers (anti-dandruff among them) swap a three-writer pick for a two-writer one; D changes only the 2 fills; full top 3s 20 -> 22 of 36 and blind-test full top 3s 8 -> 9 of 10 in every variant, every shown quote verified. Merged with main at 3194ff2 (need-led first reading, engine-speed, the data round's fixes): switched off, the 38 requests' whole answers are byte for byte main's; with D, 2 answers change, the oily-scalp and greasy-hair shampoo answers each going from 1 pick to 3 (Aussie Miracle Curls and Aussie Miracle Volume, each with a voice whose comment tops a thread of 44 or 53 comments), full top 3s 17 -> 19 of 36, every shown quote verified; the frying pan and dandruff answers no longer change (their first readings now hold no product to lift). Open: Noemi's choice of variant and whether to turn it on; the Tefal non-stick pan, which D had lifted into b10 on the older code, has no PFAS fact while its own summary, first quote and facts entry's sources say its coating is PTFE: by her rule of 11 Oct 2026 that answers pfas_free: false (a facts fix to make either way).
- Built by Claude, 14 Oct 2026 (the upvotes builder, branch upvotes; Noemi's request after switching on variant D: "if a comment has a lot of upvotes compared to the size of the thread, i want it as a pick or worth a look"; switched on as she asked, the values PROPOSED, reported to her): a comment that stands out in its thread (engine.rank.stands_out, config.STANDOUT_*). A breadth-first pass on a frozen copy of the library (590 threads; 134 requests: the blind test, latency, ingredient, needs and general eval requests and 15 with standing-out comments) compared six measures (share of the thread's upvotes, upvotes per thread comment, against the others' median, over the next comment, against the post's score, the share of the thread beaten), 2-3 settings each, then safeguards, what qualifies and what it earns, every lift judged for sense (eval/RUNS.md). Chosen, quality first (the lowest values that lifted nothing senseless): a credible recommendation (upvotes never make a comment credible) whose comment has at least 0.75 upvotes per readable comment of its thread and at least 25, in a thread of 20 or more comments, names at most 5 products (module 3's kept mentions; a 21-product sunscreen review had lifted oil-control sunscreens into dry-skin answers) and, when the request asks for something besides the product, talks about it (without that, pans whose comments said nothing of induction were lifted for an induction hob). Its product, with more credible recommendations than credible warnings, a score above zero and not on Skip these, takes a place left empty under Also worth a look even with that one voice, and with a second credible writer, even from the same thread (the comment counting as two and standing in for the second thread), a place left empty in the picks: never the place of a product meeting a rule without it, as for D. D comes first (what it lifts, it lifts as before), and how much is read doesn't change (the reading is chosen with both rules off). The answer says so only where it matters: the reason ("Recommended by 1 credible voice (its comment has 74 upvotes in a 69-comment thread), ..."), the note under Also worth a look ("2 credible voices each, or one comment that stands out in its thread: ..."), the messages' bar when such a pick is shown ("..., or 2, even from one thread, when one of them stands out in its thread") and the how page; an answer it changes nothing in is byte for byte as before. Effect on the frozen library, offline: 6 of 122 answers gain one Also worth a look item each (PURITO Centella Unscented sunscreen for oily skin; Medik8 Crystal Retinal for both beginner-retinol requests; Coco & Eve oil for frizz; Ouai leave-in for curly hair; an IKEA cast iron pan), all judged sensible, no pick changes, every shown quote verified; on the latency eval's older snapshot it fills b01's third pick with prequel milk peel (a pick on its own in today's library). Open for Noemi: the picks part (config.STANDOUT_FILLS_PICKS, on as she asked "as a pick") sets aside, for this case, her night rule that a pick needs credible recommendations across 2 threads (off, a standing-out comment earns Also worth a look only); and whether such an item should take its place by score instead (on today's library one swap: an IKEA carbon steel pan for the Cuisinart non-stick skillets in "frying pan that lasts"). Measured again after merging main 36eb803 (haircare's need rule in every reading, the prescription-only note): the same 6 lifts.
- Built by Claude, 14 Oct 2026 (the need-quality builder; technical calls within Noemi's rules, reported to her): answers that fit the need asked. (1) Module 1's needs (engine/needs.py): a negation is never a need of its own ("isn't", "not", "no"; with "out" and words of degree, engine.sources._STOPWORDS); drying after a negation names the need "not drying" (config.NEGATED_NEEDS: "a shampoo that isn't drying", "won't dry out my hair"), whose "dry" names no other need, while every other need's words already say it either way round ("isn't greasy" is the oily need, "without frizz" frizz); hair types written together before "hair" each name their need (config.HAIR_LIST_NEEDS: "fine oily hair", "thin, greasy hair"), in requests, titles and comments; "doesn't strip" is a need of its own ("strip"); haircare needs are asked for (engine.product_facts.request_asks), and only needs found by their words are ("dry" in "a dry scalp" isn't the skin type). (2) Says the opposite (the 10-11 Oct rules: shown last, no credit for talking about the request, so never the wider reading's credible recommendation about it), config.OPPOSITE_QUOTE_PATTERNS: for a product that isn't drying or a gentle one, a quote calling it drying, stripping or harsh, or using it as a clarifying, detox, chelating or deep-clean shampoo or to strip buildup (only shampoo forms: a skincare name holding "clarifying" says nothing); for "strip", stripping or drying; colour-treated hair, stripping or fading the colour, or a clarifying shampoo; dry hair, as not drying; greasy and fine hair, leaving it greasy, heavy or flat; frizz, leaving more of it; for these a negation among the 8 words before a match in its sentence (up to "but" or "because") takes it back (OPPOSITE_NEGATED_IN_SENTENCE). (3) The library's first reading: a thread whose title asks for the opposite kind of product (config.OPPOSITE_TITLE_PATTERNS: "Which clarifying shampoo for my curls?" for one that isn't drying, a gentle one, or one for dry or colour-treated hair) has none of the request's needs, so it is read after every thread about them. Tried on the frozen library and not kept: counting each need by how rare it is among the threads (no answer better, one blind-test answer read an off-topic thread), and adding need points to module 2's graded score at title-need weights 1.5 to 8 (fewer need threads read at every weight). (4) Need eval: a case may judge each need apart ("judge_each") and list the opposite's words ("opposite"); cases n11-n15. Results: every eval before the need eval identical (9/10 full top 3s, the same picks, 264/264 shown quotes verified); need eval 15 cases: about every need 41 -> 43/96, threads titled as the opposite 3 -> 0, products shown named as the opposite 4 -> 0; the curly not-drying, colour-treated and live gentle-wavy answers lose their clarifying and detox shampoos. Noemi's decision 4 of 14 Oct 2026 (morning), built the same day: for haircare the wider reading's need rule holds in every reading (config.NEED_RULE_IN_EVERY_READING; on the frozen library, with live checks, only two Also worth a look items change; without them the gentle-wavy answer's Head & Shoulders Classic Clean and Maui Moisture give way to Pantene Volume and Ouai Fine Hair).
- Built by Claude, 14 Oct 2026, from Noemi's "I want recs regardless of the category" (the general-category builder, branch general-category; part 1 of her plan and the taxonomy for part 2; decided by Claude, reported to her): (1) a fourth engine category, "general" (config.THREAD_CATEGORIES), one category rather than one per department, because answers count only their category's threads and mentions and the AI that reads threads can't tell home from tech, or outdoor from clothing, the way module 1 does; its 11 departments (config.GENERAL_DEPARTMENTS: home, tech, outdoor and travel, clothing and accessories, baby and kids, pets, sport and fitness, tools and garden, beauty and personal care, hobbies, car) are shown above its answers (the API's query.department) and give the communities of a type the open model names; 134 communities (config.SUBREDDITS["general"]: the 32 of part 2 first, 95 specialist ones searched through Arctic Shift's API only, 7 shared with the other categories). (2) The taxonomy as data, engine/data/product_types.json (config.MORE_PRODUCT_TYPES): 351 types (336 general; 12 kitchen: dishwasher, fridge, freezer, hob, cooker hood, wok, knife sharpener, cutting board, pizza oven, barbecue, moka pot, milk frother; 3 haircare: hair gel, heat protectant, hairspray), each with its plural, names, clue words, title words and communities most specific first; body washes, body lotions, hand creams, cookware sets and curl creams left out on purpose (their names moved the first types' answers), the open model places them. (3) Module 1 (engine/query.py): the taxonomy's types are its own; a product named as what the request's product is for, with or on isn't the product ("headphones for my phone", "a pan for an induction hob"), "X for my Y" is read as "Y X" when that is a name ("a bed for my dog"), of two names written together the last is the product ("laptop backpack"), "-free" or "not X" is never the product; what stays out gets its own polite no: services, places and advice that isn't about buying; food and drink, for people or pets; medicines, supplements and medical devices; books, films, music, games and apps; weapons, drugs, tobacco and vaping, and adult products (checked first, their look-alikes set aside: a glue gun, a weed eater); a vague request asks within a department ("something for my dog"); typos are corrected only into long product nouns (GENERAL_TYPO_WORDS), never from everyday words ("dark spots" isn't "dark sports"); the open model answers with a department, and its "other" means not a product to buy. (4) Extraction instructions v12: "general" for every other product, "other" for what is never ranked, and the new names; the three categories' v11, v10 and v9 extractions stay current. (5) The engine: a thread read from a community two categories share takes the category of the request it was read for (engine.sources.for_request: r/BuyItForLife is the kitchen's and the general category's; on-demand reading too), and a Parse re-read keeps the category it was saved in; a mention the AI typed as one of module 1's types counts in that type's category; a type ending with a module 1 name that ends with a set word is that product (sleeping bag, tool set) in a request for it, and left out as a set in any other (a knife sharpener in a chef knife answer), and an AI type ending with another type's name is that type (a frying pan set is a cookware set); general threads take kitchen gear's warning words and searches, their care threads rank lower, specialist words show an enthusiast, and the types' head nouns are generic name words; with nothing saved about a product the answer says so ("We haven't read any Reddit threads about laptops yet..."); the first types' covering names count as before, so their answers read the same threads. Wording PROPOSED: the polite nos, the general question, the no-threads message, the page's hero and the department names. Eval (eval/RUNS.md, 14 Oct): every number as main's but module 1 27/30, its misses q28, q29 and q30 (a laptop, a hair dryer, a dishwasher): Noemi's approved cases of 7 Oct, superseded by her 14 Oct decision and not relabelled, for her to confirm; routing eval eval/edge_cases/general.json (67 made-up requests, a draft for her to check; engine/routing_eval.py, run by eval/run_eval.py): rules alone 62/67, with the open model 67/67 outcomes, 56/56 types, 48/50 departments. Merged with main (3194ff2, 22abcd7, then 3613a7f) the same day (eval/RUNS.md): the 49 eval requests' full answers are main's but the two intended (the laptop request is the general category's, the vague request's question), and the first 43 types' answers by name too but the honest no-threads message for the four with no threads (coffee maker, juicer, kitchen scale, waffle maker) and a travel mug counted as a general product, not as another kitchen type; to get there a set word spares a type only in its own request, curl creams are left out of the taxonomy, and the library's name index works out bases in the first types and the name's own category's taxonomy types only (getting ready as quick as main's). Getting ready warms the taxonomy's types by name after main's 65 requests (web.WARM_TAXONOMY_TYPES), as the coordinator asked; 20 requests may wait for on-demand reading, not 10 (config.ON_DEMAND_MAX_WAITING: about two days of the job's Gemini allowance; the free-tier sums don't change).
- Facts research, 14 Oct 2026 (the facts researcher, branch facts-research; decided by Claude, reported to Noemi; eval/RUNS.md): ingredient answers were short of formula evidence, not of threads, so the products each ingredient request left out were ranked by their credible recommendations and the makers' pages researched for those that could be shown: 46 formula entries (azelaic acid, niacinamide, vitamin C, glycolic acid, salicylic acid and benzoyl peroxide products), 13 aliases for writers' names of them, and UK prices where a budget needed one. Claude's calls: (1) an active the maker presents counts when its ingredient list holds it, even low in the list, as COSRX's AHA/BHA toner's did on 13 Oct (Goodal's Green Tangerine Vita C serum counts as vitamin C); a product whose maker discloses the active as a trace (100 ppm) got no entry; (2) prescription-only azelaic acid (Finacea, Skinoren) is typed as an exfoliant, the type the fact belongs to (config's own note counts azelaic acid 15%+ among the prescription versions), so a request for sensitive skin leaves it out (both retyped as moisturisers later the same day, once the fact could be set on any skincare type: below); (3) a formula lists only the actives every version of the product shares (Mentholatum's Acnes jelly: salicylic acid, sulfur only in its Asian versions), and products whose versions differ stay unconfirmed, as decided (La Roche-Posay's Effaclar Duo, benzoyl peroxide in North America but not in the UK; Starface's and Peach Slices' patches); (4) lookalikes get entries of their own (COSRX's Snail 96 essence, SKIN1004's plain centella ampoule) so a writer's short name never takes another product's formula. Tefal's non-stick pan isn't PFAS-free (her rule of 11 Oct: its maker names its coating PTFE); OXO and Circulon stay unknown (their UK ranges mix PTFE and ceramic). Wilfa Svart: Wilfa discontinued it (30 Jul 2026) but a UK shop still sells final stock, so b09 keeps it until the last one sells out. Open for Noemi then (she decided it the same day, her decision 5; built below): prescription-only is a fact of retinoids and exfoliants only, so a prescription product of another type (Duac, a clindamycin and benzoyl peroxide gel) can't be marked, and a prescription-only product is left out only of beginner, gentle and sensitive requests, with no note in the others.
- Built by Claude, 14 Oct 2026, from Noemi's decision 5 of 14 Oct (morning) (the facts researcher, branch facts-research; the wording and technical calls are Claude's, reported to her; eval/RUNS.md): (1) a product whose checked facts say it is prescription-only shows "Prescription-only in the UK: ask a doctor or pharmacist." wherever the answer shows it: on a pick (after its price and availability lines), under Also worth a look and under Skip these; in the answer's JSON ("prescription", null for every other product) and text (engine/answer.py's PRESCRIPTION_NOTE); and on the page, which draws the answer's own words in the warning colours, while a row under the picks, and a pick's row At a glance, carries a "Prescription-only" tag before it is opened (PRESCRIPTION_TAG, in the page settings' wording). The how page says so. Which products are shown doesn't change, and the rule that leaves a prescription-only product out of beginner, gentle and sensitive requests stays. (2) prescription_only can be set on any skincare product type (config.PRODUCT_FACTS_FOR_SKINCARE); not knowing it is a requirement only for retinoids and exfoliants, as before (the rule's new "confirm_types"), so a cleanser, moisturiser or sunscreen answer for sensitive skin gets no "we couldn't confirm" note and keeps its brand lines, while a product of any type known to be prescription-only is still left out of such requests. (3) Data: Duac Once Daily (eMC), BenzaClin and Tri-Luma (their US labels on DailyMed), typed as spot treatments, the type the engine reads their mentions as; Finacea and Skinoren retyped as moisturisers (the engine reads a mention of an azelaic acid cream or gel as a moisturiser, so such an answer now finds their facts: Finacea became a pick of "azelaic acid cream", with the note); Arazlo's entry gets its US label; a test checks that every prescription-only entry has an official source (eMC, MHRA, NHS, NHSBSA or DailyMed). Altreno, BenzaClin and Tri-Luma are marked not sold in the UK (US prescription products the eMC doesn't list), as Arazlo and Tazorac were: Altreno had been a pick of "tretinoin for acne". (4) Not done: a brand line has no facts entry, so the Differin retinoid line (a pick of three retinoid answers) shows no note, though both of Differin's UK products are prescription-only; an entry under the bare name "Differin" was tried and taken out: it took the place of Differin Gel's entry in "adapalene gel", which then lost its only pick (its name no longer said adapalene).
- Noemi, 15 Oct 2026 (evening), revising the buyable rule: "i'm okay with products being sold only outside the uk (like only us). if they're a stronger pick, let's show them with a note about availability. reddit is an american platform". A price-list entry not sold in the UK but not known to be discontinued carries "not_in_uk": true and its product stays in answers with "Not sold in the UK, checked <date>" (wording PROPOSED); a discontinued one is still left out and named. On 15 Oct 169 of the list's 220 not-sold entries became not_in_uk (the researchers' statuses, else their notes), 51 stayed discontinued. Images and links: they load from the makers' sites (nothing stored by us), only when a card is on screen, capped at 500 KB; she asked for an off switch if they cause trouble.
- Noemi, 15 Oct 2026 (night), of the links and images research left: "can you do it automatically?". Built by Claude (technical calls, reported to her): `python -m engine.maker_pages find <shown-products.jsonl> <found-auto.jsonl>` finds a shown product's own page with no web search, from its maker's sitemaps (robots.txt followed, one request a second a site, a site refusing tools left alone): the maker's sites are the ones our lists link whose address spells the brand (else the brand as a site), a page's address must hold the model's words and the page must be a product page (schema.org Product or og:type) whose own name holds them, never another country's page, a help site or a category; it writes findings the importer checks as the researchers': sold_new only with an in-stock price in pounds on the maker's page, else unsure (the page only). Gemini's Google Search grounding isn't used: its terms allow showing its results only with Google's search suggestions to whoever asked, not storing them for a site. The importer now also records the page of a product sold only abroad (not_sold_uk, its page there) and of one unsure where it is sold (no price-list entry), since answers show both (29 pages from the researchers' findings); a discontinued one is never linked. First run: 61 of 386 found, 28 kept after Claude read each page's own name (a brand-and-type name such as "Kuhl sweaters" can match one model's page, so its findings are read before they are imported: docs/handoff-2026-10-15/research/found-auto-checked.jsonl); rerun with the command above, then `python -m engine.buyable import <file> --write`.
- Noemi's decisions of 16 Oct 2026 (evening), on the breadth-first review of every phase (docs/bfs-2026-10-16/, six read-only reports; "I want every phase to be optimal and ready before I test it with the interviewees"): (1) a feature named before the product noun in kitchen and general requests ("noise cancelling headphones", "gaming laptop") ranks first the products with a credible voice talking about it, but an answer is never emptied by it: when no product has one, the type's best products are still shown ("if we can't find any, still show up with the main prod"), with a note saying none was praised for the feature (wording PROPOSED); (2) Skip these: warnings from 2 threads, complaints from the opposite need ignored (oily-skin complaints in a dry-skin answer), at most 5 shown; (3) first-hand use: the AI's reading counts when the rules miss it, after a check on her labelled gold threads; (4) no to leaving out products that may not work or be legal in the UK (US 120 V appliances, US car seats): "I want the best rec regardless of whether they're legal in a certain state only. The tool will be used broader than just the UK" (they stay with the not-sold note; UK-only rules are to be revisited with that in mind); (5) privacy: the request leaves the page's address and the API's, so Google's request logs never hold what people type, and the how page says what those logs keep (address, browser, 30 days) and no longer that the site runs on Hugging Face; (6) on-demand reading is off for the interviews (Gemini's free allowance reads about one product a day, so "check back in about 20 minutes" isn't true); Claude reads likely products ahead instead; (7) the blind test: ChatGPT and Vetted asked as a UK shopper, "Not sold in the UK" kept in the packets, a response form (hers to make), and the site's example requests changed (they were the blind-test questions); (8) Circulon and Ballarini's price-list names become brand lines, so the PFAS-free frying-pan answer (b10) keeps only GreenPan until more PFAS-free pans are researched.
- Built by Claude, 16 Oct 2026, from Noemi's decisions 5, 6 and 7 of 16 Oct (the site-and-kit builder; reported to her): (5) the page asks for an answer with a POST to /api/answer, the request in its JSON body ({"request": "..."}), never in an address: Cloud Run's request log keeps every address it is asked, with the visitor's IP address and browser, for 30 days, and never a body; GET /api/answer answers 405 and says how to ask; the answer's JSON is unchanged; eval/live_latency.py posts too (the blind test's capture runs the local engine); the address bar and the copied link keep the request after "#", GoatCounter counts fixed names only. The how page (wording PROPOSED): its privacy section names Google Cloud Run and what its logs keep, says feedback is kept privately and we never write IP addresses down ourselves, and no longer says the site runs on Hugging Face; from the website review, a quote's check is from the 48 hours before its answer, usually made ahead of time, and an answer is shown a day at most (was "just before" it is shown), each kept comment is read again within LIBRARY_VERIFY_DAYS (was whole threads every 30 days), and a product sold only outside the UK stays with its note (was "left out"). (6) On-demand reading is off unless a deploy is run with CREDIBLE_RECS_ON_DEMAND=on (deploy/cloudrun/on_demand.sh): off, the site gets none of its settings, so a product not read yet gets the honest no-threads message, nothing is queued and the reader is never started; nothing is deleted (DEPLOY.md, "On-demand reading"). (7) The site's examples are 10 other requests the 16 Oct sweep answered with full top 3s, of kinds of product the blind test doesn't ask (engine/data/example_requests.json, wording PROPOSED); our shown answers keep "Not sold in the UK, checked <date>.", "Sold second-hand only." and the prescription-only note, whole, within the 90 words (FORMAT.md rule 7, dated); a packet page keeps each answer's paragraphs (it ran them into one); the answers' order goes round per question (with rows alternating by category a question got 3 of the 6 orders; now 5, first places 2/2/1); packets show each question's code and the tester's; RUNBOOK.md: the rivals asked as a UK shopper (London time zone, UK region and language, a UK VPN when the internet address isn't British, ChatGPT's temporary chat without custom instructions, Vetted in a private window, the wording unchanged), the blind test before testers see the site, and the response form's six fields (tester, question, choice, least, confidence, comment), its CSV export becoming responses.csv. Not built (the website review's recommendation 7): a remembered answer can still show a check up to about 72 hours old (kept 24 hours after checks of up to 48), so the how page says "shown for a day at most".
- Decided by Claude, 18 Oct 2026 (Noemi: "About the pfas - do what you think is best"): for a product type that has the PFAS-free fact (cookware), "non toxic", "non-toxic", "nontoxic" and "toxin free" ask for PFAS-free, since that is what non-toxic means for pans (no PTFE or other PFAS, her 11 Oct rule); for every other type they stay an ordinary need word (in skincare or mattresses they mean something else). The reason line names the must-have, so the reading shows.
- Noemi's decisions of 15 Oct 2026, late afternoon (from the laptop answer: "what's the point of recommending it if i can't buy it?"): (1) buyable: a pick must be on sale in the UK now; second-hand only counts for things people buy vintage on purpose (her 10 Oct rule: Griswold, Wagner); a discontinued model (a 2011 MacBook Pro) is left out and named; for fast-moving products (laptops, phones, TVs, headphones and the like) the newest threads are read first; (2) images: each pick may show a small image from its maker's own product page, loaded only when its card is on screen, linked to that page, with no referrer sent (the maker sees the visitor's address, never the search); the how page says so; (3) links: direct links only, to the product's own page (its maker's, or a big UK shop's), researched with sources and dates; no search links, so a pick not researched yet shows no link.
- Noemi's decisions of 15 Oct 2026, afternoon ("yes to all three", and her note on a quote): (1) under a must-have (SPF, PFAS-free, sulfate-free...), a product whose facts confirm it ranks above one they can't confirm (replacing, for must-haves, the 10 and 11 Oct rule that a noted pick keeps its place); (2) her ethics rule goes both ways: a recommendation resting only on a maker's ethics, eco claims, identity or origin ("buy them, they're cruelty-free") counts for nothing, as an ethics-only warning does; a comment that also judges the product counts for that judgement only; (3) a comment edited on Reddit keeps Reddit's current text and only the items whose quotes are still found in it word for word; the rest go, as before; (4) quotes shown must be the most significant and coherent part of the comment for the stance they back: a recommendation is quoted where the comment recommends (praise, how long it lasted, how it held up), a warning where it warns (her example: a Vizio TV pick quoted "... we had for 14 years and then the picture went out" where the same comment says the writer's Vizio is holding up well).
- Noemi's decisions of 15 Oct 2026 ("yes to all your recommendations", on the five questions of 14 Oct evening): (1) the weapons list: zombie, gravity, OTF, push-dagger, karambit, bowie, trench, credit-card and other concealed knives, and daggers get the polite no (config.HARMFUL_KNIVES, now in engine.query.HARMFUL); a machete is a garden tool, a product; (2) SPF lip balms: lips are an exception to her 9 Oct rule "sun protection wins over the form": a lip product with SPF is a lip balm, "with SPF" is a checked requirement (as PFAS-free), and the library's lip products typed sunscreen are re-typed by script; (3) skincare's readings follow the need rule of her decision 4 of 14 Oct (config.NEED_RULE_IN_EVERY_READING gains skincare): a pick needs a credible recommendation that talks about the request's needs in every reading; (4) a product that meets the picks bar but ranks below the top 3 is listed first under Also worth a look, labelled as meeting the bar; (5) a warning that rests only on a maker's ethics (animal welfare, labour, politics, a boycott) and says nothing about the product itself counts for nothing (not a warning); a comment that also judges the product counts for that judgement only.
- Noemi, 14 Oct 2026 (evening), "Keep only the newest 1": every deploy had kept its container image (about 1.15 GB, mostly the open model) in Artifact Registry, 44 images and 51 GB (about 4.60 EUR a month; 0.5 GB is free); the other 43 were deleted, and deploy.sh applies a cleanup policy after each deploy that keeps the newest image only (deploy/cloudrun/image_cleanup_policy.json; about 0.07 EUR a month). Earlier versions can't be rolled back to without rebuilding them. Found on 16 Oct 2026 (the website review): revision 60's deploy had stopped before the jobs step, so the plan job and the reader still ran revision 59's image, which the policy then deleted; both failed with "Image not found" from 16 Oct 04:00 (the day's plan and 74 reader starts). Both jobs were moved to the site's image by hand and the plan job run again; deploy.sh now moves any job left on another image to the site's and applies the policy last (engine/tests/test_cloudrun.py).
- Noemi, 14 Oct 2026 (afternoon): (1) set-aside threads we will never need are deleted: 88 of the 90 imported threads set aside as off-topic (food and usage questions, megathreads, fault questions about one person's own unit, and the like) were deleted with their 3 extractions; kept and returned to the library for extraction: sd94rx, a kitchen "splurge purchases that disappointed" thread (the kitchen warnings source planned on 9 Oct), and s9lytz, a belt thread (a taxonomy type). Off-topic threads found later are deleted the same way, after a look for any that a product type needs. data/library/imports.jsonl keeps their ids (no text), so they are never imported again. (2) Claude may store a key from .env in Secret Manager without showing it (she: "you can also copy the key yourself"): the secret bright-data-key was created that way, from BRIGHT_DATA_API_KEY, with the command in deploy/cloudrun/DEPLOY.md.
- Noemi, 13 Oct 2026 ("Use Bright Data"): about 1 comment in 8 can't be verified through the embed page (it shows "Not supported comment", likely comments with photos); the daily pre-check verifies those comments through Bright Data instead (her account, free tier), reading their threads as Reddit shows them now, so they can back picks again. A comment Bright Data's answer doesn't hold (it returns top-level comments and direct replies only) stays unverified and is never shown. The site itself never calls Bright Data at answer time.
- Decided by Claude, 13 Oct 2026 (the first-hand builder; eval/RUNS.md): first-hand use needs the AI's agreement when the extraction says no use (the AI can only take use away), except a plain verdict on the product (the labelling guide's "it's amazing" rule); a mention the AI typed as another product type no longer counts for a product of the requested type, and a type tie keeps a product only if one of the tied types is the requested one; other kinds of knife (paring, bread, steak...) are look-alikes of chef knives. Gold credibility agreement unchanged (46/48 exact); sense eval 93% -> 96%; blind-test full top 3s 9/10 -> 8/10 (b01 lost a wrongly backed pick). Noemi, 13 Oct 2026: "keep the plain verdict rule as it is": a plain verdict on the product counts as use without the AI's agreement (the labelling guide's rule; requiring it would have changed 79 votes and cost b09 a pick).
- Active ingredients (13 Oct 2026; the orchestrator's decision after Noemi's live test of "salicylic acid for acne", which had come back as an exfoliant answer ignoring the acid; built by Claude, reported to Noemi; engine/ingredients.py, config "Active ingredients"): a request naming an active ingredient is answered with products that contain it. Module 1 finds the ingredients (salicylic acid, BHA, glycolic, lactic, mandelic, AHA, PHA, azelaic acid, niacinamide, vitamin C, benzoyl peroxide, hyaluronic acid, ceramides, centella, snail mucin, retinal, tretinoin, adapalene, tazarotene; "no X", "without X", "X-free" ask for nothing) into constraints.ingredients. A request naming a type too keeps it ("salicylic acid cleanser"); one naming none is ingredient-led ("salicylic acid product"): it reads the skincare threads that name the ingredient, whatever their type (comments naming it lift a thread), and keeps products of every type that can carry it, each shown with its form ("Form: pads"). "retinol" and "retinoid" stay the retinoid type with no further requirement (Noemi's q05 call of 7 Oct 2026). Evidence, never a guess: a facts entry's formula (data/product_facts.json "formula": the actives its maker presents, with its own sources and date) decides; without one, the name it is shown under (a writer's "... with salicylic acid" doesn't count); a writer's comment never counts. Products without evidence, with a formula lacking it, and brand lines are left out and counted (left_out_no_ingredient; the page's footnote says how many). A product named as the requested type counts as it when the request names an ingredient (the AI types acid toners as exfoliants). Facts researched for this: formulas for Paula's Choice 2% BHA, Dermalogica Daily Microfoliant (salicylic acid and papain: a rinse-off powder), Peach Slices Acne Exfoliating Toner, COSRX BHA Blackhead Power Liquid and AHA/BHA toner and Isntree's 0.9% toner (betaine salicylate, not salicylic acid), By Wishtrend's bakuchiol cream (retinal and bakuchiol); new entries Isntree Chestnut BHA 2% Clear Liquid (with the alias "Isntree 2% BHA") and CeraVe SA Smoothing Cleanser. Dr Dennis Gross's peel pads stay unconfirmed: two of its three Alpha Beta peels hold salicylic acid, the Ultra Gentle doesn't, and writers don't say which. Eval: eval/edge_cases/ingredients.json (engine/ingredient_eval.py, run by eval/run_eval.py).
- Live latency (13 Oct 2026, Claude, measured with eval/live_latency.py and logged in eval/LATENCY.md): 2 processors made no difference, so the site stays on 1; a new server gets visitors only once its /ready says it has got ready (Cloud Run's startup probe) and a Cloud Scheduler ping every 5 minutes keeps it awake; reads are paced by what Reddit's rate-limit headers say is left (Noemi: "go ahead with the reddit header pacing"), never slower than one every 4 s, and a visitor's read never waits over 60 s for Reddit's next 10 minutes (the pre-check waits). The picks first (Noemi: "if the new section adds too much time, i'd rather not have that section but be sure that the product i'm looking for is found"): the comments only Also worth a look or a summary quote are read only if that needs no wait; put off, they keep their votes and what stands on them is left out of that answer, which isn't remembered.
- The redesign (13 Oct 2026, the UX builder; Noemi: "something way nicer and advanced without sacrificing the speed of the service"; decided by Claude, reported to Noemi): engine/templates/search.html is calm and editorial (warm neutrals, one green accent, the system's own serif for headings: no font is downloaded), light and dark, from 360 px phones up. New: a hero with three steps, "/" to the search box, the visitor's last 5 requests kept in their browser only (never sent; Clear removes them; the how page's privacy section says so), grey blocks while an answer loads and an honest line after 4 s, a reading strip of numbers (Noemi's testing: the old sentence confused her), a credibility meter per pick and item (the API's new "voices": the same writers the reason, support and share lines count), "At a glance", cards whose first view is summary, meter, price and two quotes (one on a phone) with the rest behind a toggle saying what it holds, "Skip these" folded after its first 5, copy link, open all details. The rules stay: Reddit text as text only, links only through redditUrl/shopUrl, a summary never drawn as a quote, the answer's own wording, quotes whole; nothing typed goes into the page's title (GoatCounter sends it). The request stays after "#q=" (never sent anywhere), not "?q=". Budget: the served page at most 120 KB (engine/tests/test_web_ux.py): 93 KB (was 49 KB), sent gzipped (27 KB) to browsers that take it; drawing an answer takes 2-5 ms warm, about 20 ms the first time (User Timing "credible-recs:draw", kept in the browser). The how page is restyled to match. Round two the same day (Noemi: "a little more distinct from the picks... a little too uniform"; she kept recent searches, approved the proposed wording and the downsides behind the toggle): the picks are the only raised cards; under them each kind of section is a flat panel in its own colour family with a head (icon, name, thin rule): Also worth a look (stone) as compact rows with a "2 credible voices · 2 threads" tag, its summary and quotes a click away; Skip these (rose) with a warning mark per row; What to look for (blue) as a checklist, Look for beside Avoid; the care note (green) as a tip callout. The reading strip stays under the title (her 12 Oct rule) but quiet, between hairlines; what was left out and "Was this useful?" sit in a quiet zone after the answer, "First time here?" right after it, noted as asked only once it has been on screen ("pending" until then). A test computes every text colour's contrast from the page's tokens, light and dark. Active ingredients carried in: the answer's own title, its note under it, each product's form as a chip. 104 KB served (30 KB gzipped).
- Vintage products sold only second-hand (Griswold, Wagner) count as available to UK shoppers, and the answer says "sold second-hand only" (Noemi, 10 Oct 2026).
- Price-list entries (data/prices.json): the shop field is the shop's plain name only, as it is shown in answers; what a researcher found out goes in the entry's "note", which is never shown (10 Oct 2026).
- Decided by Claude on the evening of 10 Oct 2026 (reported to Noemi): `extract check` rejects services typed as products (config.SERVICE_TYPE_PATTERNS, instructions v7's own rule); `prices todo` also lists the 3 products next in line behind the picks; quotes that name their product are shown first, without the writer's markdown bold or italics; a comment backing two kinds, or a care tip that is its quote, is shown once; a pick shown by its UK name notes "sold as Breville outside the UK"; the matcher forgives spelling slips and possessives and takes product-level short names (engine/data/product_aliases.json), 73/75 labelled pairs. Later that evening: a brand pick steps aside only for its own product when that product is shown in the top 3 (Lodge had vanished from b08); a brand pick names its brand's most recommended model ("Most named model: ...", at least 2 credible recommendations, config.BRAND_MODEL_*). The named model shows its checked price when there is one (shown only, never a reason to leave the brand out). Also that evening: quotes naming the product and giving a view come first, a quote saying the opposite of the request is shown last (config.OPPOSITE_QUOTE_PATTERNS; for a request that asks for something lasting, a quote where it failed within three years); a quote that names nothing, gives no view and doesn't point at the product (b08: a one-line reply about sticking with cast iron) only makes up a pick's minimum of two quotes; `blind_test tally --save` puts the result in eval/metrics.json; eval/blind_test/RUNBOOK.md has the week-3 steps.
- Pending (10 Oct 2026): Arctic Shift was down (Cloudflare 522) from 9 Oct evening. When it answers again: (1) `python -m engine.profiles warm data/library/threads` for the ~550 writers still without a profile (684 stored); (2) a real sanity check of the archive reader (engine/arctic_shift.py get_thread: its comment-tree parsing is untested on real data); (3) title searches for more threads (frying pan, cleanser, chef knife). Meanwhile threads are found with Parse searches (2 credits each) or data/library/candidates.json and read through Bright Data (free 5,000 records a month).
- Built by Claude, 13 Oct 2026, from Noemi's decision "Keep only comments we use" (the lean-library builder; reported to her): `python -m engine.library slim` (engine/slim.py) keeps each extracted thread's title and, whole, every comment its extraction points to (mentions, notes, care tips and agreements, kept or rejected, and the comment a reply takes its product from); every other comment becomes a "not_kept" stub (id, parent, date, score, link: no words, no writer), and the post's words and writer go. What the scoring read from the whole thread is worked out first and kept in the thread's whole_thread: the product types the post and each dropped comment named (module 2; engine.slim.known_types: module 1's types, the open model's, the request log's, each active ingredient's), the pairs of copies that reach a kept comment, a kept writer's first comment when it is dropped, fingerprints of quotes found in dropped words. A guard reads every slimmed copy as answers do before writing it (extraction checks, every kept comment's voice, copies, relevance to every known type, comments read). On a copy of the 13 Oct library: 413 threads slimmed, 10,132 comments kept and 8,070 reduced to stubs, words 4.16 -> 2.48 MB, thread files 13.5 -> 9.6 MB; every answer the pre-check works out (65 requests), the blind test (8/10 full top 3s) and the 22 latency requests identical. Gold-set threads (3) and the 20 not extracted yet stay whole under the old rules. A product type unknown when a thread was slimmed is found in it by its title and kept comments only (add types before slimming). Each kept comment carries verified_at; the daily pre-check verifies kept comments on the embed page after the comments answers show, oldest first, within its own budget (config.LIBRARY_VERIFY_READS 400 a day, about 26 minutes; LIBRARY_VERIFY_DAYS 30; read again after 7 days at the soonest, an unreadable page after 10), and records each read in the bucket's live_check/verified.json (ids, dates, outcomes; engine.verify.Ledger); deploy.sh applies it before bundling (`python -m engine.library apply-checks`): a comment found deleted or edited, or not verified within 30 days, loses its words and its mentions (its items leave the extraction file too). An unreadable embed page proves nothing (the comment just isn't verified), so a page Reddit redesigns can't wipe the library. check-live and refresh never read a slimmed thread again (no Bright Data, no Parse); the 14-day rule applies comment by comment; the job's limit is 3 hours (45 minutes since the redesign below).
- Built by Claude, 14 Oct 2026 (the lean-library builder, after merging main and branch precheck; the coordinator's free-tier task; decided by Claude, reported to Noemi): (1) Reddit reads fit the free tier. A Cloud Run job is billed for its whole run, and two thirds of the pre-check's 87 minutes a day went on waiting for Reddit's allowance (88% of the jobs' free tier with on-demand reading's). Options compared breadth-first (deploy/cloudrun/DEPLOY.md, "Who reads ahead"): the site reads at the keep-warm ping (chosen), several short job runs a night, lower tiers less often, and others (Reddit's api/info, a fixed address, GitHub Actions, Noemi's computer). Now the job runs `python -m engine.precheck --plan` (45-minute timeout; 55 since that evening, Claude's call: Bright Data's jobs took up to 10 minutes on its side, so the client waits up to 20, config.BRIGHT_DATA_MAX_WAIT_SECONDS, and the job's sums are at most 102,300 vCPU-seconds a month, 43%, 63% with on-demand's): it starts from the bundle the site shares, records each read of a kept comment in live_check/verified.json, works out the answers' comments and writes live_check/plan.json (those comments likeliest first, the kept comments due to be verified, config.LIBRARY_VERIFY_READS 3,000 a day: 12,356 of a copy's 17,335 kept comments were never verified, read from the archive on 11 to 14 Oct and so due by 10 to 13 Nov, about 31,000 with the threads still to extract; then its Bright Data checks, made after the plan is written and starting nothing after 30 minutes). The site (engine/read_ahead.py) asks for the plan at most hourly and at each ping reads what is due (an answer's comment 40 hours after its last read, a comment to verify not read in 48 hours): at most 40 a ping, 4 at once, none after 5 seconds, never a read that would wait, never while Reddit says fewer than 120 reads are left (visitors' share); it writes its reads to the bundle at most hourly, only over the version it last read or wrote, and no longer reads the bundle each hour. A read that found no comment is known (and bundled) for 48 hours, used for 20 as before. Sums (engine/tests/test_cloudrun.py): the job at most 83,700 vCPU-seconds a month (35%; 56% with on-demand reading's), the site's reads at most 53,568 of its own request-billed 180,000 (30%; about 7% for today's 4,340 reads a day), Bright Data at most 930 records a month of 5,000; no new Cloud Scheduler job, two more bucket calls an hour for the site. The 48-hour rule is unchanged. (2) Branch precheck's Bright Data verification is merged; deploy.sh deploys the job with it off (CREDIBLE_RECS_PRECHECK_BRIGHT_DATA=off, no secret, one line saying so) when the secret bright-data-key is missing, as on-demand's Gemini key; the secret exists since 14 Oct 2026. (3) Main's need-led reading reads a thread's post, whose words slimming drops: a slimmed thread notes which of config's need words its post held, and which of the words the engine knows (engine.slim.known_words: every checked request's words, the product types', ingredients' and needs' own) it held as a request's own word is found; config's and the engine's words, never the post's; a request's word outside them is looked for in the title only.
- Built by Claude, 14 Oct 2026, late (the lean-library builder; the coordinator: both of the day's plan runs had failed on the same two threads and read no other, each run on Google Cloud starting with an empty disk; technical calls, reported to Noemi): the Bright Data step remembers the threads it couldn't read in the bucket beside the plan (live_check/bright_data.json: ids, dates and Bright Data's words only), and the run's report names each with Bright Data's status and error (engine.bright_data.BrightDataError's status, error and post_gone; never a comment's words). A thread that failed is left for 7 days (config.PRECHECK_BRIGHT_DATA_SKIP_DAYS), so the records go to the next threads; one whose post is gone (Reddit shows it removed or deleted, or Bright Data's dead page) holds comments taken as unverifiable for 30 days (config.PRECHECK_BRIGHT_DATA_GONE_DAYS): no record is spent on them again, and the plan reads what answers show instead (they drop out of the answers the job works out, as they do for a visitor).
- Found by Claude, 15 Oct 2026 (the lean-library builder; the coordinator's question about 5 mentions rejected after the migration because their product source had become a stub; reported to Noemi): slimming had kept those sources (each had items of its own); verification then found them edited on Reddit, so by her rule they lost their words and mentions, and the replies taking their product from them can't be checked (read again on 15 Oct: each still edited, so not restored). In the whole slimmed library 15 replies have such a source, 10 removed on Reddit and these 5, none left by slimming. But formatting had made the check take 7 of the 65 kept comments dropped as edited for edits: the live check read every HTML tag of the embed page as a space ("<strong>Zojirushi</strong>: it" became "Zojirushi : it"); now only the tags ending a block separate words, and Reddit's superscript mark (^) is ignored like * and _ (engine.verify_quotes). `python -m engine.library restore-words --backup <the pre-slimming .tgz>` gives such a comment its words and items back when the embed page, read again, passes (engine.verify.restore_words; the 7 pass); `extract check` now says when a source was found edited or went unverified (whole_thread.dropped).
- Decided by Claude, 14 Oct 2026 (the name-levels builder, branch name-levels; the orchestrator's task after b08 lost its Lodge pick to a writer's "lodge cast iron pan"; technical calls within Noemi's rules, reported to her; eval/RUNS.md): a brand, its line and its products are told apart the same way in grouping, folding and ranking (engine/group_products.py, "Name levels"). (1) A name made of a brand and only the requested type's words or their synonyms (config.TYPE_SYNONYMS, found among the library's names: "pan" for a cast iron skillet, "patches" for a spot treatment, "crockpot" for a slow cooker, "spf" for a sunscreen) is the brand's line, never a product its line steps aside for; in an ingredient-led answer, which has no one type, a one-word brand with its own type's words ("Zitsticka patches") is its line, left out as lines are. (2) A product of another of module 1's types never makes a name fit two products, nor joins one ("Stratia" is its Soft Touch AHA in an exfoliant answer though its moisturiser is named); a brand's mentions of another type leave its line one by one and never decide its type (a writer's Lodge Dutch ovens in a skillet answer, Anker's cables in a charger one); a requested type's words inside another type's name ("cast iron dutch oven") name none of it, in mentions and in module 2's thread titles. (3) Such a name, fitting products of other types too, joins its one product of the type only when the whole library names no other of the brand's products of that type (engine.group_products.LibraryRanges: "Nexxus" stays its line, the library naming three Nexxus shampoos), and a brand's or a line's name never names a product ("Skinceuticals" is shown as its C E Ferulic). (4) A name the facts list knows as one product is never a line, whatever descriptions writers add ("... SPF50+ PA++++"), and two such names are never joined; "esp" and "forte" are variant words (the Baratza Encore ESP, Epiduo Forte); IP and Instapot are Instant Pot. (5) The orchestrator's decision: a retinoid whose facts entry's formula lists benzoyl peroxide counts in a benzoyl peroxide answer (config.INGREDIENTS "facts_types": Epiduo, with its prescription-only note, never in beginner, gentle or sensitive requests). Prices added: Niche Zero £559, Fellow Ode Gen 2 £287.50 (both over b09's £150). On a frozen copy of the day's library: blind test 8/10 -> 9/10 full top 3s (b08: Griswold line, 10.25" Lodge, Field line), every other eval unchanged but the ingredient eval's count of products shown (56 -> 51, all with evidence). Open: an ingredient answer leaves out a line even when every product of it named there has the ingredient (Paula's Choice 2% BHA, its liquid and its gel), so "a bha for blackheads" lost it once the gel was named; "slow cooker" rests on vintage Rival crockpots (not sold new in the UK), and the Crock-Pot line folds into Rival's because "crock pot" is read inside "Rival crockpot"; two writers' names of The Ordinary's azelaic acid suspension don't match each other, so its commonest name is left out as a line (an alias would join them).
- Decided by Claude, 14 Oct 2026, evening (the name-levels follow-up, the orchestrator's six items; technical calls within Noemi's rules, reported to her; eval/RUNS.md): (1) b08 holds as the library grows: one new thread asking for lasting pots and pans "aside from cast iron" had taken a first-reading place, and threads titled as another type (an enamelled Dutch oven, a frying pan) kept theirs, so the first reading fell short and the wider one's need rule left Field out. Now a thread titled as another type, or as the opposite kind of product, is read after every thread about the requested one (engine.sources LocalSource._need_led), a title naming the type only as what it sets aside ("aside from", "besides", "other than"...) names another, "broke in my new pan" (seasoning) isn't about lasting (config.NEED_LOOKALIKES; "forever chemicals" and "takes forever" aren't either), and a comment saying a product lasts in the words people use ("will last forever", "a lifetime pan", decades, heirloom, BIFL; config.NEED_COMMENT_WORDS) talks about lasting, in comments only (nearly every r/BuyItForLife title says them, so they tell threads nothing apart); a size-first line ('12" Lodge cast iron skillet line') folds into its brand's like any line, as Also worth a look already did. b08's first reading now has the Lodge and Griswold lines (main's, the Lodge line alone; Field's recommendations there are in one thread), and in the wider reading Field's now talk about lasting: 3 picks on the frozen copy and on the live library at 20:31. (2) Two lines are one brand's only when their names start with it: the Crock-Pot line (its own brand, sold new in the UK) no longer folds into Rival's ("Rival Crock-Pot" is Rival's line), and the brand-lines list has it (its UK range page; from £14.99, its 1.8 L at Amazon UK), so it shows as "Crock-Pot slow cooker line"; Rival is sold second-hand only (eBay UK). Writers also say crock pot for any slow cooker, and those count for Crock-Pot's line. (3) Lines in ingredient answers (the orchestrator's call): a line stays when at least two of its products are named in the threads and every one has a facts entry confirming the ingredient (Paula's Choice 2% BHA, its liquid and its gel, as on the first name-levels frozen copy; on the evening's copy the threads of "a bha for blackheads" name its liquid alone, already a pick there), shown with their forms ("gel or leave-on liquid") and checked again by the ingredient eval; a line whose products all find one facts entry is that product ("Finacea", its "Gel 15%" and its "(15% azelaic acid)"); a line with one product named stays out (one version tells nothing of the others). (4) A name fitting two products the facts list knows apart names neither (engine.product_facts.find_facts: "Paula's Choice 2% BHA" had taken its gel's newer entry), and a group's other names then decide its entry. (5) Data: Sage's coffee grinders from £149.95 (the Dose Control Pro, £20 off its usual £169.95: check again when the offer ends, b09's budget is £150); Mad Hippie Vitamin C Serum £26.99 (Amazon UK, its own store) and CeraVe Skin Renewing Vitamin C Serum £22.50 (Boots), both over "vitamin c serum under £20", which now has two picks; Scanpan CTX is PTFE (Scanpan UK's FAQ: its pans contain PTFE; CTX is Stratanium+), pfas_free false, so it leaves b10; Ballarini's UK range mixes PFAS-free ceramic (Salina "manufactured without PFAS", Ledro, Bologna) with PTFE (Ferrara Granitium), so its PFAS fact stays unknown; Paula's Choice's 2% BHA gel's formula; The Ordinary Azelaic Acid Suspension 10% aliased so writers' two names are one product. On a frozen copy of the day's library: blind test 9/10 -> 10/10 full top 3s.
- Decided by Claude, 16 Oct 2026 (the interview-fixes builder; technical calls, reported to Noemi; branch interview-fixes-1, from the day's breadth-first reviews in docs/bfs-2026-10-16, eval/RUNS.md): (1) refusing Teflon, PTFE or PFOA ("without teflon", "no ptfe", "teflon-free", "pfoa free") or naming forever chemicals asks for PFAS-free (config.PRODUCT_FACT_REQUEST_WORDS; her rule of 11 Oct: PTFE is a PFAS; PTFE pans are made without PFOA, so reading a PFOA-free ask as PFAS-free is the stricter reading); "a teflon pan" asks for nothing; "non toxic" still asks for nothing (hers to decide); "non stick pan without teflon that lasts" now picks GreenPan, Ballarini and Circulon, as b10 does; (2) in a PFAS-free answer a quote recommending a Teflon or PTFE pan, or saying the pan is one, says the opposite of the ask (config.OPPOSITE_QUOTE_PATTERNS: shown last, no credit for talking about the request); (3) GreenPan's frying pans are non-stick (data/product_facts.json, checked 16 Oct: GreenPan UK's frying-pan collection lists only ceramic non-stick frying pans, its one uncoated item a stainless steel set; its FAQ names the coating Thermolon, with no PFAS including PTFE), so b10's first pick has no note (the 15 Oct follow-ups' GreenPan item); (4) module 1: what a product is easy, gentle, kind, soft or hard on, or won't dull, blunt, damage or scratch, is what it is for (engine.query._CONTEXT_MARKER: "cutting board that's easy on knives" is answered, Epicurean, Boos, Sani-Tuff); (5) need words: filler is no need (engine.sources._STOPWORDS: someone, makes, fixes, handles, at, least, willing, proper, from, quickly, all, daily, easy, number words, and "free", so "pfas free" asks about PFAS as "pfas-free" does), "kitchen" alone is ignored (config.NEED_IGNORED_WORDS), a type's own word in the plural is the product's ("lips", "knives"); in skincare and haircare the product's own names and clue words the request uses are no judged need (engine.needs.judged_needs: module 1's keywords and hints, config.TYPE_SYNONYMS, a named ingredient form: "night cream", "cleansing oil", "spf" in a sunscreen request, "wash" in "salicylic acid wash"), while kitchen and general requests keep them (a kind the type's names hold is what they ask: without "gaming", a comment standing out in its thread had lifted a MacBook Pro into "best gaming laptop under 800"); both stay needs for the first reading; two words that make one need are named whole in the reason (config.NEED_PHRASES: non stick, pour over, dark circles, back pain, flat feet, steam wand, brown rice, frozen fruit, small kitchen, home gym...; engine.needs.Need.label), comments still found by each word (found as the pair only, the espresso answer read fewer threads about steam wands and lost its machines with one); British and US spellings meet in comments and titles (engine.sources.spelling_variants: -ise/-ize and -ation, -our/-or, -lling/-ling: "vitamin c serum that doesn't oxidise quickly" has 3 picks, was 1); rosacea is sensitive skin (config.NEED_REQUEST_WORDS, replacing the 15 Oct call that it asks about itself: the rosacea answer loses Differin Gel and CeraVe's retinol, BoJ's eye serum, innisfree's and The INKEY List's come in), "40s", "50s", "60s", "over 40" and "older skin" are mature, "break me out" acne-prone; (6) a brand line whose entry under the brand says it isn't sold in the UK shows "Not sold in the UK, checked <date>" (engine.pipeline._within_budget; b08's Field, Tiger, Aroma, GE, Frigidaire, Hamilton Beach...), unless one of its products here is sold in the UK or its brand-lines entry gives a UK from price; (7) a brand written in other capitals is shown as the lists write it (engine.group_products.maker_spelling: config.MAKER_SPELLINGS, the shipped short names, the brand-lines list's brands, then the first word of the price and facts lists' names; small letters only from config, since the brand-lines list writes "shark", "all clad", "bowflex" so), and of the writers' spellings one with capitals comes before a commoner one in small letters (_shown_spelling): shown names starting in small letters 60 -> 23 of the sweep's 606; (8) facts entries named as their products: "Verb Ghost Shampoo" (was "Verb Ghost line"; its source is the shampoo's page), "COSRX Salicylic Acid Daily Gentle Cleanser" (was "... (SA cleanser)", in the price, facts and pages lists, with the alias "COSRX SA cleanser"); not renamed: the AirPods Pro line (a line of generations with a researched from price) and Derby blades (its name is the product's: that blades count as a razor is a type question); (9) "knife" alone doesn't make a mention the AI typed as another kind of knife (nakiri, cleaver, usuba, deba, petty..., with module 1's other knives) a chef knife (engine.pipeline._word_left_aside): b07's Kiwi line had its second thread from a nakiri's mentions, so it leaves b07 and "210mm gyuto for a beginner" (the Global and Shun lines take the places; the eval's b07 already had Global). Results: the eval on the base commit and the branch, back to back, identical but for names and three ingredient-eval left-out counts; blind test 10/10 full top 3s, every shown quote verified; the sweep's 95 changed answers in eval/RUNS.md. Open: item 10 (one product twice in an answer: Ergobaby Embrace, Weber Spirit, Kindle and Paperwhite lines, bowl-lift KitchenAids, King whetstone, Dualit) not started; "night cream for my 40s" now has 1 pick (the rule wants voices about mature skin: threads about anti-ageing night creams are a data job); the PFAS-free answers' Also worth a look holds Le Creuset's toughened non-stick and OXO's non-stick pans, unknown in the facts list (Le Creuset's is PTFE-based: research); in kitchen and general reasons the type's own words stay ("about freezer" in a fridge freezer answer); "eczema" isn't read as sensitive skin; writers' possessive "Grado's" is shown as the line's name; the morning's eval numbers for the need and ingredient evals move with the live-check cache (main's code moved too), so compare evals run back to back.
- Decided by Claude, 18 Oct 2026, under Noemi's cost policy (reported to her): new library threads are extracted by
  Sonnet 5.5. On her three gold threads (the repo's own scorer, extract-v15) Sonnet scored votes precision 72/80
  (90.0%) and recall 72/75 (96.0%) against Opus's 73/78 (93.6%) and 73/75 (97.3%) from the 9 Oct extractions; every
  quote passed the word-for-word check; stance and category 100% on matched products; evidence level against her
  labels 94.7% (Opus 92.2%). The precision gap (3 mentions in 80) is within the noise of so small a sample (a
  comment-level bootstrap: -9.6 to +1.2 points). Its own slips, now told to every extraction helper: a reply's
  product name comes from its parent's own words; a tool or applicator named in passing isn't a mention; tentative
  interest is neutral. Opus stays for the orchestrator, judgement reviews and code that changes scoring or rules.
- Built by Claude, 17-18 Oct 2026 (the converge round's ws-names builder, branch ws-names: module 1, the need words and
  module 4's names; Claude's technical calls within Noemi's rules, reported to her; eval/RUNS.md): (1) Module 1: the
  open model's product is placed by its own words (a mouse mat with the mouse in tech, a bike pump outdoors, guitar
  strings in hobbies, a tyre gauge in car, a baby food maker or a stock pot in the kitchen, a hair toner in haircare,
  a sheet mask in skincare); a model answering "case" names the request's "ipad case"; two products or a brand is
  never a type ("le creuset or staub" asks in the kitchen); a kitchen mixer tap is a tap; skin concerns ("dark
  circles", "dry lips", eczema) ask the skincare question, and eczema is sensitive skin, as rosacea is; a skincare or
  haircare maker's name places a vague request ("dupe for drunk elephant protini"), a brand with lines in two
  categories places none; a set of pots and pans asks frying pan or saucepan; "stocking filler" is never corrected to
  "filter", and a gift's question stands when the model names no product (the gift, dog, coffee and tea questions'
  wording PROPOSED); money in words is a budget ("less than a tenner" is £10, "about forty quid" £40, "under a grand"
  1000: engine.query.money_in_figures, the budget's own rules unchanged). Routing eval with the model 104/104 (main
  96/104), rules alone 89/104 (88). (2) Claude's call of 18 Oct, built: for a product type with the PFAS-free fact
  (frying pans, saucepans) "non toxic", "non-toxic", "nontoxic" and "toxin free" ask for PFAS-free
  (config.TYPE_ASKED_WORDS, engine.query.type_asks) and are one need, named "PFAS-free" in the reason and found by
  toxins, PFAS, PTFE, PFOA and Teflon; "non toxic moisturiser" stays an ordinary need. "non toxic frying pan" now
  shows GreenPan's line, De Buyer's carbon steel pans and HexClad (noted "we couldn't confirm it's PFAS-free") and
  leaves out 15 pans whose facts say they aren't PFAS-free (Tefal's PTFE pan had been pick 2). (3) Need words: in
  kitchen and general requests the type's own head words are no judged need ("about freezer", "about coffee" gone;
  config.TYPE_OTHER_NAMES: "portable" of a portable charger), a one-word kind stays one ("gyuto"); a brand is no
  judged need unless it is what the product is for ("for my iphone 15"); two-word needs and verbs are named whole
  ("dog hair", "three storey house", "staying cool"); a short need word is found with its plural ("dogs"), a request
  word in its other words (uni, college), a two-word need also written as one or with a hyphen ("nonstick"), never in
  removing makeup; skin types only for skin; conversation words, people, contractions and money in words are no needs;
  an induction hob, stove or cooktop is the induction need. (4) Names: one product shown once (`python -m
  engine.duplicate_names <sweep.jsonl>`: answers showing one product twice 2 -> 0 over the sweep, one brand written
  two ways 4 -> 0): short names for the Ergobaby Embrace, Kindle Paperwhite, Weber Spirit and Genesis, OtterBox and
  the King 1000/6000 stone, never one making two brand-lines entries one (a Dualit 4-slice short name broke the list's
  check and was taken out); makers' spellings (OtterBox, Oral-B, The INKEY List, KEVIN.MURPHY, iUNIK, e.l.f., got2b,
  Red Wing, Darn Tough, LG, GHD...), brands a letter apart kept apart (Graco is no Grado, Babylist no BaByliss, Molly
  Mutt no "melly"); a name keeps its own words after its maker's spelling ("Bosch Series 4", "Ryobi ONE+", "COSRX The
  6 Peptide") but not where or how it was bought ("from Costco", "(refurbished)"), quotation marks, a possessive or a
  "brand" after the maker; a price or facts list's own name keeps its letters, since an answer finds a product's
  price, availability, page and image by the name it is shown under (respelled, the price list's "OleHenricksen ..."
  eye cream lost its £38 price and a £35 budget no longer left it out: the list is the place to correct it). (5) Type
  rules (the decided rule of 10 Oct 2026, decision 5): razor blades and liners are no razor or sleeping bag (Derby's
  and Feather's blades leave both razor answers, which keep one pick, Merkur's line); a stock or pasta pot is no
  saucepan; a name's last word says it is another thing only for "blades" (the wider rule of 17 Oct had also left out
  the Boos Block, Peak Design's Travel Bag, PowerBlocks and OneBlade); the barbecue and sharpener synonyms of 17 Oct
  were taken out (they turned the Weber Spirit and the King stone into lines). Eval back to back with main's code:
  identical but for names, the library's groups (24,502 -> 24,475) and the routing eval; blind test 10/10 full top 3s,
  every shown quote verified; sweep 110 of 278 answers changed, each explained in the private report. Open for Noemi:
  whether an essence counts as a toner (COSRX Snail 96 tops "hydrating toner"); brand-only names shown as products
  (T3, Mous, Sleep Number, Jura, "King stones") until the brand-only-line rule is merged; a travel system as a
  stroller pick. For the data builders: the price and pages lists' "OleHenricksen banana bright + vitamin C under eye
  cream" named as its maker names it; the Kindle Keyboard (a 2010 model no longer sold) is the e-reader answers' third
  pick until a price entry says so; Scanpan's PTFE fact and HexClad's and Le Creuset's toughened non-stick coatings
  for the non-toxic and PFAS-free answers; more razor threads.
- Built by Claude, 17 Oct 2026 (ws-ranking, the converge round of 17-18 Oct; Noemi's decisions 1, 2 and 3 of 16 Oct 2026 and the 16 Oct reviews' module 5 and 6 items; technical calls and wording reported to her; eval/RUNS.md): (1) features (engine/features.py): in kitchen and general requests a feature named before the product noun, or right after it as "that's X" ("a kettle that's quiet", the same ask as "a quiet kettle"), ranks first the products a credible recommendation praises for it, right after the must-haves (engine.rank); a buyer's need (beginner, home cook, lasting), a checked requirement (non-stick, PFAS-free: the facts settle them) and a word that only names the product (config.FEATURE_PLAIN_WORDS: "coffee machine") are no feature; praise is the feature said and not denied in the product's own words (other products', other models' and other people's clauses aside), with nothing against it (quiet: noisy, loud; config.FEATURE_AGAINST_WORDS), or an answer in a thread whose title or post asks for it, but for a material (config.FEATURE_MATERIALS: stainless steel, cast iron, glass...) only the writer's own words in a clause holding the product; never a product whose name says the opposite (config.FEATURE_OPPOSITE_NAMES: a corded drill); when no pick is praised the answer's message says so (engine.features.FEATURE_NOT_PRAISED, PROPOSED; 12 of the sweep's answers: noise cancelling headphones, gaming laptops, automatic watches, cast iron kettles, stainless steel pans...). (2) Skip these: credible warnings from 2 threads (config.SKIP_MIN_THREADS; 140 of the 16 Oct sweep's 271 items had one), the opposite need's left aside (config.NEED_OPPOSITES: dry and oily skin and hair), at most 5 shown (config.SKIP_SHOWN); more credible warnings than recommendations still keep a product from the picks wherever they come from. (3) First-hand use: the AI's reading counts where the rules miss the writer's use (config.AI_FIRST_HAND_COUNTS) and their long use where they see use but no time (AI_LONG_TERM_COUNTS), only with a concrete tag or the writer speaking for themselves, never for someone else's experience; her gold threads: the rules' agreement and the credible votes unchanged (46/49, 44/45), the held-out kettle thread 27 -> 29 of 30 as answers use it; times of use read clause by clause (a writer's older model, another product, another person, a fresh start); about 6,400 of the library's 58,394 votes became first-hand. (4) Hearsay never first-hand: the AI's "secondhand" over the rules' verdict, or beside another person, without the writer's own use; gifts ("bought it for my boyfriend") and other people's years are theirs; more people words. (5) A brand line's warnings folded under a specific pick are counted apart and shown after its own (engine.answer DOWNSIDES_SHARE_BRAND and DOWNSIDES_BRAND_ONLY, PROPOSED; the API's brand_downsides: b01's COSRX toner reads "1 of 4 ..., and 4 more against the COSRX exfoliant line as a whole"). (6) PROPOSED, off (config.RANK_BY_CREDIBLE_POINTS: the brief's Sum rule is hers): the picks ordered by credible points, the full score breaking ties; on the branch 15 of 491 pairs of picks still put fewer, shorter credible voices first only by other mentions' points (b03's innisfree above CeraVe; 26 of 472 on main); on, 95 answers reorder. Results: every eval number as main's but ingredients 51/51 evidence (was 49/49) and 18/18 forms (17/17); blind test 10/10 full top 3s (b04, b05 third picks and b06's order change with more first-hand voices); sweep 197 of 278 answers changed (68 picks), full top 3s 151 -> 156. Open: new picks without a checked price or availability (the sweep's list in docs/bfs-2026-10-17/ws-ranking); a Mid 2012 MacBook Pro now a pick of two laptop answers (needs a discontinued entry) and a one-person tent of "tent for two people" (a size need); Sony's WF-1000XM4 earbuds grouped with its WH-1000XM4 headphones (module 4); the page and the packets could show brand_downsides apart (the packets' "Downside:" may be a brand line's).
- Built by Claude, 17-18 Oct 2026 (the converge round's ws-answer builder, branch ws-answer; docs/bfs-2026-10-17/PLAN.md; technical calls and PROPOSED wording, reported to Noemi): (1) the 48-hour rule for remembered answers: an answer is remembered only until its oldest shown quote's check turns 48 hours old, never past web.ANSWER_KEEP_HOURS (24), and not at all when a shown check can't be found (web._keep_seconds; it could show a check about 72 hours old); the how page says "shown for a day at most, and only while every check it shows is under 48 hours old" (PROPOSED); (2) reading ahead's capacity, measured read-only (the site's logs of 15-17 Oct, the bundle and plan at 18 Oct 01:20 UTC): every one of the plan's 7,574 answers' comments had a read under 48 hours old (one due), but a ping read 32 of its 40 (batches of 8 each waited for their slowest), 9,216 a day against about 7,545 due, the backlog after each new plan taking about a day to read; now a read starts as soon as one is back (engine.read_ahead.ReadAhead.read_due: 40 a ping in the same 5 seconds and the same share of Reddit's reads, 11,520 a day; after a failure no new read starts until those out are back), each fresh answer's comments are read again first (ReadAhead.shown: links only, in memory, the newest 2,000), and each ping's log line says how long its reads took; (3) "What to look for" never says the opposite of the request or of the picks (engine.answer._contradicts): no Avoid naming what the request asks for (an ingredient it names, a need's name or the request's own word, a feature of the product's own name: "mesh" of "mesh wifi"), a kind a pick is by its name or its writers' names (an inverter microwave, an electric sharpener, a gas grill) or, for a kind of the type asked for, by the products a line pick's credible writers recommend (the kettle answers' "variable temperature kettle" under the Bonavita and OXO lines' variable and adjustable temperature kettles; "adjustable" reads as "variable"), or a kind the same kind's credible advice under its other names recommends as strongly ("mineral SPFs" beside "mineral sunscreen"), unless the warning's own credible notes say what the request asks to be without (mineral SPFs' white cast in a no-white-cast answer: it agrees, and stays); another kind counts only when it is the same thing or one of it (its further words keep what it is: a heavy wool coat for wool coats in rain), never a wider kind (a knife sharpener's praise says nothing for a pull-through one) nor its opposite ("fridge without an ice maker" agrees with avoiding an ice maker); no Look for naming what the request refuses (a kind without it, "PFAS-free pans", agrees) or that stronger warnings argue against; an Avoid about what the request refuses (Teflon for a pan without it) or about a kind its facts rule out (tretinoin for a beginner) stays; a line left out leaves its place empty (the advice after the first lines is weaker); a kind named after a prescription-only active, misspelt too ("adalpalene"), gives a beginner no Look for (engine.pipeline._unsuited_kinds); first built counting any kind sharing words, at half the strength, which the whole sweep showed taking good lines out (pull-through sharpeners, ice makers, non-stick pans in a cast iron answer) for weaker ones; (4) a line pick's "Most named model" is only a product we know by name (a price or availability entry under its own name, a facts entry, a researched page, the matcher's known names), never with a shop's code or discontinued (engine.pipeline._a_known_model): sizes, descriptions and old models writers wrote are no longer shown, nor are real models not researched yet (Eufy L60, Honeywell HPA200, Kobo Libra 2...: price entries would bring them back); (5) the reason line names a must-have asked in other words as the must-have ("about PFAS-free", not "about teflon"; "non stick pan without teflon" as "non-stick or PFAS-free", as the other phrasings) and, in kitchen and general answers, never names nor counts another word of the product's own name in the request ("freezer" of "fridge freezer", "cordless", "mechanical", "gaming"); (6) a quote opening by agreeing with another writer, naming another product of its comment first or telling hearsay (module 5's reading) comes after a clearer quote of its tier that says as much for the request (only the order changes, so such a quote may fall after the few shown); (7) packets: a downside is cut only at the end of a sentence that keeps its point, else the evidence is cut to make room, else it is left out; a badge is never cut; the notes stay whole (one packet test changed, dated); (8) `python -m engine.summaries missing <sweep.jsonl>` lists every pick and Also worth a look item a sweep shows without a one-line summary (today's baseline: 485 products, 62 of 515 shown picks have one) and `todo --sweep <sweep.jsonl>` prepares the writer's reading for exactly those, for the final phase. Results: the whole suite passes (5,319); eval as main's run back to back (blind test 10/10 full top 3s, the same picks, every shown quote verified; one quote fewer shown, b06's left-out Avoid line); the sweep's changes in eval/RUNS.md; the sweep about as quick as the base's (126 s against 125 s for 278 answers, after making the new checks lazy). Open: engine.precheck's requests_to_check starts with the blind-test questions, no longer the site's examples (engine/data/example_requests.json; their answers' quotes are 90-100% in the plan anyway); kettle facts (variable temperature) would let What to look for know a non-line pick's kind when no name says it; "Most named model" waits for price entries of the real models no longer shown; if Noemi's feature rule (decision 1 of 16 Oct) is built, the reason should name its feature word again ("gaming"), now hidden as a word of the product's name; "stainless steel pan for searing" picks no stainless pan (De Buyer carbon steel, Tramontina and GreenPan non-stick: the must-have "stainless steel" has no facts rule); general answers' What to look for still holds other products' advice (diaper bags in a wallet answer).
- Built by Claude, 17 Oct 2026 (the ws-data-kitchen builder; the coordinator's technical call within Noemi's decision 8 of 16 Oct 2026, her 12 Oct 2026 rule on brand-only names made consistent; reported to her; eval/RUNS.md): a product named only by its brand is its brand's line (engine.pipeline._brand_only_lines, config.BRAND_ONLY_NAMES_AS_LINES). Writers name Circulon's and Ballarini's frying pans by brand only, and module 4 keeps a brand none of whose models is named as one product, so with their price-list and facts names gone (decision 8) "Circulon pans" was still a b10 pick, unpriced and noted as unconfirmed twice. Such a group is now ranked and shown as "<Brand> <type> line", with its range page and from price, when (1) its names find a brand-lines entry selling the requested type (find_brand_line, as any brand name does); (2) every name is that brand, or another name the entry gives it (Ballarini's also_called "Zwilling/Ballarini"; the maker's name written alone before the brand in such a co-brand, which module 4 joins to it, counts as it), alone or followed only by words that name no model (_names_a_model; "non stick" is read as "non-stick", a brand by its UK name); (3) no facts or price entry its names find names one product of it ("our place pan" stays the Always Pan); (4) the brand's line isn't among the answer's groups already (then the existing fold applies: OXO's non-stick pans next to the OXO line stay as they were). Under a must-have such a line is left out as a whole brand (10 Oct 2026). The rule on against off on one reading of the library (the 278 sweep requests, offline) changes 4 answers, all frying pans: b10 and "non stick pan without teflon that lasts" pick GreenPan, the Caraway frying pan line (PFAS-free by its maker; we couldn't confirm non-stick, as its range has a stainless pan; not sold in the UK) and OXO's non-stick pan (we couldn't confirm PFAS-free), with Circulon and Ballarini left out as whole brands; "28cm frying pan, non stick but pfas free, £30-60" keeps GreenPan alone; "a frying pan for an induction hob" swaps the Circulon line (a whole brand can't be checked for induction) for the Solidteknics US-ION pan. Also worth a look in the PFAS-free answers now reaches Made In's stainless pans and Member's Mark's non-stick pans (a facts entry under another name says Sam's Club's are PTFE): data for the round's PFAS research. Evals as the baseline's (matching 73/75, ingredient and need evals identical, blind test 10/10 full top 3s with b08's Lodge, Griswold and Field lines, every shown quote verified) but b10's picks and the quote counts of the round's new threads; 5,283 tests pass.
- Built by Claude, 18 Oct 2026 (the ws-data-kitchen builder, data round: items 2 to 4 and the coordinator's round-2 pan facts; technical calls within Noemi's rules, reported to her; eval/RUNS.md): (1) pan facts per named model, from the makers' disclosures: Made In's stainless frying pan isn't non-stick and its non-stick pan is PTFE (Made In's California disclosure), Cuisinart's French Classic and Advantage non-stick skillets are PTFE (Cuisinart's chemical disclosure; with two Cuisinart entries a writer's bare "Cuisinart non-stick" names neither), writers' Member's Mark commercial non-stick pans reach PTFE facts (Sam's Club's pages); OXO non-stick pans whose writers name no model keep an unknown PFAS fact (OXO's current pans are made without PFAS by its own disclosure, but writers' were mostly the older Good Grips non-stick, and a facts entry under the one model a writer names would have marked them all PFAS-free, as module 4 names their group after it). (2) Threads: 141 new library threads read from Arctic Shift's archive and extracted by Claude (extract-v15, 0 rejected: 3,278 mentions, 1,414 notes, 536 care tips, 691 agreements), slimmed (new threads only): saucepans 18, paring knives 7, quiet kettles 6 and a stovetop kettle, water filter jugs 9, juicers 7, waffle makers 8, beginner cast iron 10, bean-to-cup machines 10, cast iron on glass hobs 7, bread knives 7, pepper grinders 7, cleavers 8, meat grinders 8, garlic presses 7, immersion blenders 7, toastie makers 7, springform pans 7 (ids in the round's docs folder); writers' profiles warmed only for the 111 writers whose comments the answers quote (PLAN.md's rule; 2,362 others listed for a later run). Not read this round: wine glasses, sheet pans and bread makers (the fetch lock's queue). (3) Prices and lines, from makers' UK pages or big UK shops, with shop and day: the Chefman, Fellow and Fellow Stagg kettle lines, the Victorinox paring and bread knife lines, the All-Clad, Made In and Le Creuset saucepan lines, the Sage Barista Express line (from £629.95, so an under-£500 answer leaves it out), the Peugeot pepper mill, KitchenAid hand blender and OXO garlic press lines; the Wüsthof Classic paring knife, Demeyere's Industry 5 sauteuse, the Lelit Victoria, the Rancilio Silvia, the Pepper Cannon, IKEA's KONCIS press and KitchenAid's plastic grinder attachment; Unicorn's mills and the Snakmaster sandwich maker are not sold in the UK. (4) Pages, each read for its own name: the Wüsthof knife, the Demeyere sauteuse, the Rancilio Silvia, the Pepper Cannon, Mercer's Millennia bread knife, the KONCIS press and the KitchenAid attachment. Effect on the 278 sweep requests, offline: 31 answers change, each traced to its stage: "a good saucepan" 0 -> 3 picks (the All-Clad, Le Creuset and Made In lines), garlic press, immersion blender and pepper grinder answers 0 -> 3, bread knife and meat grinder 0 -> 2, water filter jug 1 -> 3; "cast iron skillet for a beginner" keeps 2 (Field's and Smithey's credible voices sit in one thread each). Evals as the baseline's but the library's counts, b10 (GreenPan, Caraway, OXO, as with the brand-only rule) and the need eval's first-reading threads about the need (113 -> 124/240); blind test 10/10 full top 3s, every shown quote verified; 5,299 tests pass. Left for others (notes for the integrator): writers' bare "Stagg" and "Barista Express" read as lines; US writers' "super automatic" isn't read as "bean to cup"; stock pots still count as saucepans (round 2's type rule).
- Built by Claude, 18 Oct 2026 (the ws-data-beauty builders: two Opus 5.5 copies on 17-18 Oct, then a Sonnet 5.5 copy that
  finished it under the cost policy; branch ws-data-beauty from c50651e, not merged; technical calls, reported to Noemi). Skincare
  and haircare data for the converge round. (1) Library: 144 new threads (115 skincare, 29 haircare; 4,389 mentions; extract-v15, every
  quote word for word, 0 rejected; slimmed; list with titles: docs/bfs-2026-10-17/ws-data-beauty-new-threads.txt), read from Arctic
  Shift's archive for the requests that had fewer than 3 picks: mature skin and night creams, eczema- and rosacea-prone skin,
  sunscreens that don't sting the eyes, hydrating toners, vitamin C, haircare, benzoyl peroxide, salicylic acid cleansers. 57 more
  threads were read, extracted and slimmed but held back (same list, last lines), each after a leave-out test: 25 niacinamide
  and vitamin C oxidation threads cost both niacinamide serum answers their picks, and of the last round's 18 threads (benzoyl
  peroxide 6, salicylic acid cleansers 5, glycolic toner 2, BHA for blackheads 5; one Sonnet helper, 278 mentions) 13 were held:
  the two BHA threads that gave "a bha for blackheads" a second pick took "salicylic acid wash" its only pick and put a US-only
  pad into b01, and the rest moved no answer (leaving a thread out is how it was found). (2) Need words: an age of 40 to 79
  written as an age in a comment, sagging, crepey skin and (peri)menopause read as mature skin (config's ws-data-beauty section,
  engine/tests/test_beauty_round1.py): "night cream for my 40s" 1 -> 3 picks. (3) Lists, each entry dated 17-18 Oct 2026 with its
  sources: prices +75, facts +12, brand lines +2, maker pages +22; b01-b05's picks checked again on 18 Oct (sold at the prices shown;
  Isntree's Chestnut BHA 2% and innisfree's Retinol Cica are out of stock in every UK shop read, so b01's and b03's picks are sold
  out for now but still count as sold, by the list's convention: check before the blind test; Boots refused tools that afternoon,
  its prices are those of the morning's reads). (4) Profiles (numbers only): the 220 writers the answers quote are warmed, 1,961
  more are listed for later (docs/bfs-2026-10-17/profiles-later-ws-data-beauty.txt). Results, offline, model on, from the worktree
  (docs/bfs-2026-10-17/sweep-ws-data-beauty.jsonl against sweep-base.jsonl, changes with reasons in sweep-ws-data-beauty-changes.txt):
  of 278 answers 50 beauty answers changed (38 with other picks, 12 price lines or voice counts; each traced by leaving the new
  threads or the lists out; one more, azelaic acid for redness, only has a support line that moved with the shared cache); official skincare and haircare requests with 3 picks 55 -> 58 of 68 (salicylic acid cleanser,
  benzoyl peroxide, "toner w/o alcohol..." and the night cream up; "vitamin c serum that doesn't oxidise quickly" 3 -> 1: CeraVe's
  serum has 8 credible warnings and loses three bare "CeraVe" recommendations to a CeraVe line, Rohto's essence becomes the Melano CC
  line without a voice about oxidation), the builders' own 39 beauty requests 19 -> 26 with 3 picks; blind test 10/10 full top 3s,
  every shown quote verified (b02 gets Biore UV Aqua Rich for Eucerin's gel, b04 Avene's XeraCalm A.D balm for Mary&May's cream, b05
  La Roche-Posay's Toleriane Hydrating Gentle Cleanser for CeraVe's cream-to-foam, shown as not sold in the UK); the other 36
  changed answers (kitchen, general: 32 differ in support lines only, two pan answers in the order of two picks, as in main today, and the two winter coat answers in a third pick) are not this workstream's: the winter
  coat answer is the same with main's library or this one, the lists as they were or now, and either profile store, and main today
  already differs from the 17 Oct baseline in 19 other answers (the shared Arctic Shift cache fills as builders warm profiles). 5,270 tests
  pass; the evaluation matches the base but for the library's counts (62,969/63,023 -> 67,358/67,412 quotes, shown 250/250 ->
  242/242), the ingredient eval (products with evidence 49/49 -> 55/55) and the need eval (first-reading threads about the need
  113 -> 119/240; n15 6 -> 9, n05 11 -> 10). Found, for others (PROPOSED, nothing built): a top-level answer in a thread whose title
  asks for the need should talk about it (the need rule reads comments only: "conditioner for dry damaged hair" has 33 threads about
  the need and 2 picks, night creams for the 40s lost their best-liked cream to it); picks not sold in the UK take top-3 places in
  more answers (official beauty picks flagged not sold 9 -> 14: Vanicream, EltaMD, Pipette, Stridex pads, La Roche-Posay's US cleanser:
  Noemi's call whether a UK-sold pick should come first); every new thread titled for a product type takes first-reading places from
  older ones (four other cleanser answers changed when the 5 kept benzoyl peroxide and salicylic acid cleanser threads arrived: the double cleansing oil answer swapped a non-oil cleanser for a cleansing balm);
  Effaclar Duo (13 credible voices) has no formula entry: not researched (the US cream is a benzoyl peroxide treatment; whether the UK Duo+ is not checked), and a UK pick must not be given a US formula.
- Tech and home data round, finished 18 Oct 2026 (branch ws-data-tech, three builders in turn; the last one under the
  cost policy; technical calls by Claude, reported to Noemi). The library copy holds 185 new threads (extract-v15, every
  quote word for word, 0 rejected: 5,521 mentions, 1,261 notes, 114 care tips, 547 agreements), all extracted by Sonnet
  in batches of 12 to 20 threads, slimmed (new threads only), with the profiles of the 160 writers whose comments
  answers quote warmed (3,197 other writers listed in docs/bfs-2026-10-17/profiles-later-ws-data-tech.txt). The last
  round read and extracted threads only for requests that still had fewer than 3 picks: office chair 6, standing desk 6,
  pillow 6, air purifier 6, pet-hair vacuum 2, 4k monitor 8, smartwatch 8 (and copied 35 threads the earlier builders had
  extracted). Four phone threads about phones that last were taken out again: for "a phone with a good camera" they put
  the iPhone 7 and 8 first, so a thread is kept only when it is about the request's need. Prices, pages and availability
  (dated 18 Oct, UK delivery address) for the picks shown: laptop lines (ThinkPad, Lenovo, Framework, Zenbook, MacBook
  Pro), Pixel, power banks, JBL Clip 5, SEBO, Garmin, Levoit, Winix, Steelcase, Fully's Jarvis desk, Tresanti at Costco UK.
  Left out and named as no longer sold new: Pixel 4a, Galaxy Note10+, Galaxy S9+, Ultimate Ears MEGABOOM 3 (units still
  listed on Amazon UK by marketplace sellers do not count as "final stock counts as sold": Claude's reading of Noemi's
  rule, for her to confirm). Sold abroad only, kept with the note: UPLIFT desks, Purple's Harmony pillow, Sleep On
  Latex, the TCL 27C2A Pro. Results: 5,404 tests pass; the evaluation equals the baseline except the library's size
  (62,969 -> 68,490 quotes found word for word, shown 250 -> 253 of 253 verified); blind test 10/10 full top 3s; of the
  278 sweep answers 58 changed (14 only by the date: the base code on the base library gives them today; 9 by the lists;
  7 by the threads; 28 by both; none by the warmed profiles). Still short of 3 picks, by data the decided communities do
  not hold: webcam for video calls (0), 4k monitor for work or photo editing (1: the market is split over many models),
  smartwatch for fitness (1), and, from the eval requests, mirrorless camera (0), mesh wifi (2), case for an iPhone 15
  (2), robot vacuum under 300 pounds (2: the budget rule removed the Eufy line). "Gaming laptop under 1000 pounds" shows
  laptop lines that are not gaming laptops (no need rule for the general category: Noemi's call, see the report).
- Built by Claude, 17-18 Oct 2026 (the converge round's ws-data-general builder, branch ws-data-general: the data for
  the general category's demo, interviewee and eval requests, by three builders in turn, the last under the 18 Oct
  cost policy; Claude's calls within Noemi's rules, reported to her; eval/RUNS.md): (1) Threads: 150 new threads in 26
  product types (hiking boots 4, rain jackets 4, backpacks 3, suitcases 6, tents 4, sleeping bags 4, water bottles 7,
  jeans 8, socks 6, winter coats 4, work boots 6, wallets 6, strollers 6, car seats 7, baby monitors 5, electric
  toothbrushes 2, razors 8, hair dryers 2, hair straighteners 8, dog beds 5, dog harnesses 9, drills 7, dumbbells 5,
  yoga mats 8, sports watches 7, running shoes 9), found by Arctic Shift's title search in the decided communities and
  read from its archive into the builder's own library copy (new files only: none of the shared library's 1,973
  threads and 1,953 extractions differs byte for byte), extracted with extract-v15 by helpers the first two builders
  spawned without a cheaper model (Opus, batches of 2 to 5 threads, before the cost policy; nothing was extracted
  under it): 8,845 mentions, 2,255 notes, 351 care tips, every quote word for word (0 rejected), then slimmed; one
  thread read and extracted was held back (its comments are about vacuums). A type got no more threads once it had 6
  to 8 on-type ones: sleeping bags stay at 1 pick (8 on-type threads; many voices praise bags they have not used, and
  the brands' models split the rest, so no product reaches 3 credible recommendations in 2 threads). (2) Lists,
  researched on makers' and UK shops' pages of 18 Oct and imported with engine.buyable: 84 more brand-lines entries
  (UK range pages and from prices for the brands writers name alone, or the maker's page abroad), 172 price-list
  entries and 155 product pages. Claude's calls: the cheapest regular price where the cheapest was one size on
  clearance (Carhartt, Columbia); a cordless kit for a drill line (Bosch); a UK store's tax-inclusive price over a
  maker's tax-exclusive one (GORUCK, Alpinetrek); no single price for a range named by its brand; waxed jackets left
  out of rain jackets; Bellroy's from price the £39 Mag Wallet as Bellroy EU lists it on Amazon UK, not a £25 listing
  whose buy-box price is hidden; Oral-B's a sale price at an online pharmacy (the big shops refuse to be read); the
  UK's Boondock Ultralight for writers' Timberland PRO Boondock (the entry's note says it is not provably the same
  build); and what could not be shown sold or gone left as "Availability not checked yet": Garmin's Forerunner 255 and
  955 (no Add To Cart at Garmin UK, out of stock or delisted at the UK shops, but not marked discontinued: if Noemi
  counts that as gone they leave the running watch answer), B Yoga's B Mat and Cinch's White Label. Brands are written
  as their makers write them (Oral-B, PowerBlock, Secrid, Timberland PRO, Jade, and in config Astra, lululemon,
  Brooklinen: writers' "astras" were shown as the running-shoe brand Altra, "lulu lemon" and "Brook Linen" as slips).
  (3) Profiles: 574 writers added to the builder's profile store (550 with numbers, 24 unknown to the archive; numbers
  and flair only) in four chunks (300, 217, 65 and 8 writers), those whose comments the 47 answers of these types
  quote; the other 5,031 writers of the new threads are listed in
  docs/bfs-2026-10-17/profiles-later-ws-data-general.txt. (4) Results: the eval identical to the baseline but for the
  library's counts and one ingredient-eval pick's place (writers' profiles warmed); blind test 10/10 full top 3s,
  253/253 shown quotes verified; the sweep's 77 changed answers in eval/RUNS.md; 26 of the 27 requests show 3 picks
  and the sleeping bag 1; the answers under 3 picks 127 -> 98. With ws-names, ws-ranking and the kitchen rule merged
  in a scratch tree, razors keep 3 real picks once razor blades are no razors (Merkur, Rockwell 6S, Rockwell 6C) and
  sleeping bags have 2 (the Western Mountaineering and Feathered Friends lines); eight short names for the integrator
  to add to engine/data/product_aliases.json (WM, EE, FF for sleeping bags; 255, FR 255, 265, 955, 965 for Garmin's
  Forerunners, which show as bare numbers now) are in the report. Open: other requests read the new threads when their
  posts name a word in passing (laptop, mattress, headphones, phone, monitor, towel, washing machine: 19 answers'
  reading counts, 7 "Look for" lists, one of them a washing machine's showing a dog bed tip), because
  engine/sources.py puts threads titled as another type last but still reads them when few are on-type; the 150
  threads are archive reads of 18 Oct that `library check-live` has not yet read on Reddit.
- Built by Claude, 18 Oct 2026 (the converge-1 integrator, branch converge-1: the orchestrator's task to merge the seven
  converge round-1 branches; technical calls, reported to Noemi; eval/RUNS.md): (1) Merged in the order ws-names,
  ws-ranking, ws-answer, ws-data-kitchen, ws-data-beauty, ws-data-tech, ws-data-general. CLAUDE.md stayed the short file
  and the dated notes three branches had added to it (ws-ranking's, ws-answer's, ws-data-kitchen's two) were moved to
  this file; every paragraph here and every row of eval/RUNS.md is kept once; every config section is kept; the four
  data lists were merged entry by entry, each in its own layout (prices 713 -> 1,119, brand lines 170 -> 307, facts 207
  -> 225, pages 384 -> 671), with no duplicate entry and no product twice on one day. (2) One fix for the merge itself:
  engine.answer._said_needs also hides the words of the product's own name that no need holds ("freezer" of "fridge
  freezer"), because ws-names' judged_needs now leaves them out of the needs and a ws-answer test lists one; the
  pipeline never gives a mention such a need. (3) engine/data/product_aliases.json: of ws-data-general's eight proposed
  short names only Garmin's 255, FR 255, 265 and 955 were added, because the shared library's general threads show no
  other use for them. Left out: WM (West Marine, in a duffel bag thread), EE (an electrical engineer, a shoe width), FF
  (forward-facing in car seat threads, Fleet Feet in a shoe thread) and 965 (a robot vacuum's model number). So the
  sleeping bag answer shows "WM sleeping bag line" and, in Also worth a look, "Western Mountaineering sleeping bag
  line", and the running watch answer a bare "965"; an alias scope per product type, or Noemi's word that those other
  uses don't matter, would let them in. (4) Library: 620 new threads and their extractions copied into the shared
  library from the four data builders' copies (kitchen 141, beauty 144 of the 201 it read, tech 185, general 150): no
  file overwritten, no id in two lists, no existing file changed in any copy. Also the extraction files ws-data-kitchen
  made for 3 threads the library held but had never extracted (1up22a0, xovg6z, m3zanh), and those 3 threads slimmed.
  1,045 writers' profiles and 1,069 flairs added (the shared file's entries untouched); the import log had no new line.
  Threads 1,973 -> 2,593, extractions 1,953 -> 2,576. The 57 threads ws-data-beauty held back were not copied. (5) What
  the live site needs before the new threads' comments show: nothing now. A thread's last live check (in a slimmed
  thread, each kept comment's last verification) holds a thread back only when an answer is written with no live checker
  and the rule left on, the function's default; the sweeps and evals switch it off, and the site passes its embed-page
  checker, which turns it off by itself: each quote shown then needs its own passing check from the last 48 hours, made
  as the answer is written, by reading ahead or by the daily plan. `library check-live` never reads a slimmed thread
  (all 620 are), so it would do nothing for them: ws-data-general's note to run it before deploying describes the
  default. With a stand-in checker, six requests gave 0 to 3 picks without a live checker (their new threads waiting)
  and 2 to 3 with it, with 4 to 12 new threads quoted. The new threads' 19,668 kept comments have never been verified,
  nor have 51,273 older ones (70,941 in all): each loses its words if not verified within 30 days of the archive read
  (dues 6 to 17 Nov); at 3,000 verifications a day that takes about 24 days, so the deploy, with ws-answer's faster
  reading ahead, should be by about 24 Oct. (6) Memory: reading the library takes 500 -> 619 MB and 60 answers 1.09 ->
  1.32 GB peak (+21%, the open model off), so the plan job (2.25 GB for 486 requests over ~1,950 threads, limit 3 GiB)
  will need about 2.7 to 2.8 GB. Results are in eval/RUNS.md's row: the whole suite 5,955 passed; no eval number worse
  than the baseline; blind test 10/10 full top 3s; the sweep's answers with 3 / 1 to 2 / 0 picks 151 / 43 / 84 -> 200 /
  20 / 58, every shown quote found word for word.
- Built by Claude, 18-19 Oct 2026 (the round-2 code builder, branch round2-code from main be59fc9: the orchestrator's
  six items from round 1's answers, docs/bfs-2026-10-17/round2-additions.md; technical calls within Noemi's rules,
  reported to her; eval/RUNS.md): (1) "smartwatch for fitness": no round-1 rule took the Garmin line's recommendations.
  On all 26 threads it keeps its 6 credible ones (2 about fitness) beside 4 warnings and is the wider reading's one
  pick; but two Huawei Watch GT 7 Pro recommendations now count as first-hand (the AI reads use with specific details,
  her decision 3 of 16 Oct; both writers speak of their own watch, checked), so the first 16 threads already give one
  pick, and the wider reading, kept only when it has more picks (11 Oct), isn't: the answer shows the Huawei, which no
  credible voice praises for fitness, and lists the Garmin line under Skip these from the first 16 threads' 1
  recommendation and 3 warnings. Right by the rules as written; which reading wins a tie is hers (reported). (2) What to
  look for shows only tips about the type asked for (her blueprint of 8 Oct is the requested product's): in a general
  answer, a thread read whose products the AI typed mostly as other types (under config.LOOK_FOR_TYPE_SHARE, a quarter,
  of the requested type; by its title when it has none) backs no tip unless the tip's own name names the type
  (engine.pipeline. _threads_about_another_type, engine.answer._another_types_tip). 16 answers' lists change; gone: the
  washing machine's dog bed tip, the towels' yoga mat tip, the perfume's air purifier, candle and diffuser tips, the
  phone's phone-case warning, the shotgun mic's air purifier, the speaker's soundbar and subwoofer, the water bottle's
  sling bag, the hunting knife's sharpening tips, the camera's mirror and phone tips; kept by their names: mat towels,
  wool socks, safety razors. Kitchen keeps its 10 Oct exception (tried for kitchen tips naming another type: it also
  took "Avoid: non-stick pans" from cast iron skillet answers and "Look for: cast iron" from saucepan ones, so not
  kept); a type as broad as "camera" still lets baby-monitor camera tips through by name. (3) Names: a brand-lines entry
  found through one of its other names shows its maker's name when that name is the brand's initials ("WM", "EE") or the
  line without its maker ("Stagg", "Copper Spur", "Barista Express"), and the items join (_one_per_name); a brand's own
  first words stay ("Field"). No shown name is a bare number: the price or facts list's one product of the type with
  that model number, up to it ("Garmin Forerunner 965", "G502"), else the writers' fuller name, else left out as naming
  no one product. (4) "bean to cup" is one need (config.NEEDS) with US writers' "super automatic", and named before the
  machine a feature (her decision 1 of 16 Oct): the bean-to-cup answer now reads the five bean-to-cup and super
  automatic threads first and picks the Sage Barista Express (a built-in grinder; UK shops sell it as bean to cup), the
  De'Longhi and Gaggia lines (was the Barista Express, a Mr. Coffee and the Rancilio Silvia). Every answer in a thread
  asking for one counts as praise for the feature, manual machines recommended instead too: a built-in grinder fact
  would settle it (hers). (5) Voice rubric, her red flags as written: Amazon associates' short links, redirect links
  hiding a shop behind a code and a deals app's referral links are paid promotion (an affiliate or referral link: two
  red flags); a writer linking their own site (its address holds their name) or a review outfit's account linking its
  write-up of products it tested promotes one brand (one red flag): 44 library comments newly flagged (36, 7, 1);
  shoppers' own a.co and amzn.eu share links stay unflagged. A writer repeating their own comment stays no red flag (her
  11 Oct rule; one vote per writer anyway). (6) The daily plan job works its requests one product type at a time and
  forgets what answers worked out between types (config.PLAN_ANSWERS_KEPT_TYPES = 1; each request keeps its place, so
  the same comments in the same order): on round 1's library its working out of the 486 requests peaked at 1.39 GB with
  the 64-type window and at 1.08 GB now (this Mac, the model off; 4.3 -> 4.8 minutes), so 3 GiB and deploy.sh stay. The
  shared library's files were rewritten at 22:40 on 18 Oct (1,615 threads, 104 extractions; not this branch): main's
  code on it already changes 24 answers of round 1's sweep (b04's third pick among them), so this branch's answers are
  compared with main's on the same library.
- Built by Claude, 18 Oct 2026 (the round-2 data builder, branch round2-data, from main be59fc9: the coordinator's
  five data items; the lists and tests only, no code; technical calls within Noemi's rules, reported to her;
  eval/RUNS.md): (1) The price and pages lists' eye cream is named as its maker spells it, "Ole Henriksen banana
  bright + vitamin C under eye cream" (the lists had kept a writer's slip, "OleHenricksen ..."): ws-names' rule
  respells the slip as the maker's name, which now finds the £38 price and the page again, and a £35 budget still
  leaves it out (engine/tests/test_round2_data.py). (2) The Kindle Keyboard (the 2010 third-generation Kindle) is
  discontinued in the price list ("Amazon Kindle Keyboard", also called "Kindle Keyboard" and "Kindle Keyboard 3G"):
  Amazon's help page on Kindle e-readers released in 2012 or earlier says they lose store access, and can't be
  registered, from 20 May 2026 (its text as a search result gave it: the page itself answered 503 to this round's
  read), and Amazon UK's Shop all Kindle page and John Lewis's search list none. It has left the e-reader answers'
  Also worth a look; the Kindle Voyage (2014) and Scribe 2024 are still there, not checked. (3) PFAS, from the makers'
  own pages, decided per named model. Scanpan's FAQ says its pans are free of PFOA and PFOS but do contain some PTFE,
  so every non-stick range is pfas_free false (Stratanium: Classic Induction, CTX, Urban; Stratanium+: Haptiq,
  Techniq, CS+; also Classic and Pro SB+), while its Impact, Fusion 5, STS, Maitre D and Black Iron pans are uncoated:
  new entries "Scanpan" (writers' bare name for the non-stick pans; every mention in the threads is of one) and
  "Scanpan Haptiq", beside the 14 Oct "Scanpan non-stick pans" and "Scanpan CTX". A bare "Scanpan" had no fact, so
  "non toxic frying pan" listed it under Also worth a look with "we couldn't confirm it's PFAS-free"; it is now left
  out as not PFAS-free, and with its non-stick fact confirmed it is the third pick of "best non stick frying pan" (7
  credible voices; a line with no brand-lines entry yet, so "Price not checked yet" and "Availability not checked
  yet", though Scanpan UK sells it: left for the next round). HexClad: its own FAQ and science page name its coating
  as TerraBond, a ceramic non-stick it calls PTFE-free and PFAS-free, and its FAQ lists newer induction cooktops among
  those it suits, so a "HexClad" entry says pfas_free, non_stick and induction true; the "we couldn't confirm" note
  leaves "non toxic frying pan", and HexClad can now show in "ptfe free frying pan" and "a frying pan for an induction
  hob" (hexclad.co.uk, its UK shop, wouldn't load for this round's tools, so HexClad has no UK price or availability
  yet). FOR NOEMI: reviews say HexClad switched from a PTFE coating to TerraBond in 2024/25 without announcing it, and
  11 of the 17 threads naming HexClad are from 2020-23, so the entry describes the pan sold now, not the one most
  quotes praise (the kitchen round left OXO's non-stick pans unconfirmed because writers' were mostly the older PTFE
  ones); deleting the "HexClad" entry puts it back to unconfirmed. Le Creuset's toughened non-stick was already
  recorded on 17 Oct (pfas_free false; a search result showed its US pages disclosing PFAS in the Toughened Non-stick
  PRO pans); its site gave this round's reads an empty page, so it was not read again. (4) The Snakmaster (the Clark
  Snakmaster, a grilled sandwich maker sold from a 1990 TV infomercial) is discontinued, no longer "not sold in the
  UK": Hunker (22 Aug 2026) says it is no longer sold new and House Digest (30 Jul 2026) that the infomercial's number
  no longer works; it is no vintage brand (config.SECOND_HAND_VINTAGE), so second-hand sales don't count. "toastie
  maker" now has no pick (the toastie threads praise only the Snakmaster); one kitchen-round test changed on purpose
  (test_kitchen_data_round.py: not_in_uk -> discontinued, with a dated note). (5) b01's Isntree Chestnut BHA 2% Clear
  Liquid and b03's innisfree Retinol Cica serum, read again late on 18 Oct: both still sold out in every UK shop read
  (Skinsider; Cult Beauty, Space NK and ASOS UK; Lookfantastic's search finds no Isntree chestnut BHA), and no page
  read says either is discontinued, so both count as sold by the list's convention (their two 18 Oct rows were
  updated, not doubled). Signs the Isntree liquid may be on its way out: YesStyle says it is no longer available, and
  its maker's Korean shop lists only the 0.9% toner among its BHA products; innisfree's own US store still lists its
  serum (stock unclear). FOR NOEMI: neither pick can be bought in the UK now, so a tester following b01's first pick
  or b03's second can't buy it; whether to keep, swap or re-capture is hers, and both are worth checking again on the
  capture day. Sites that refused or blocked this round's reads and were not tried another way: Amazon (503),
  TechRepublic, HotHardware and Skinsort (403), Liliputing (bot check), Sweetcare UK and Sephora Canada (403), Le
  Creuset (empty page); ASOS timed out for the fetch tool and loaded normally in the built-in browser. Results
  (eval/RUNS.md): the whole suite 6,000 passed (converge-1: 5,955; 45 new tests in engine/tests/test_round2_data.py,
  one kitchen-round test changed on purpose). The evaluation is the converge-1 run's in every number but the library's
  own, which others changed after that run (1,717 library files): quotes found word for word 85,111/85,165 ->
  84,953/85,024, the ingredient eval's shown products with evidence 54/54 -> 55/55, and b04's third pick (Avène
  XeraCalm A.D instead of Aquaphor, the same with the committed lists on the same library); blind test 10/10 full top
  3s, unverified quotes shown 0 (shown 246/246). On the same library, the committed lists against these edits, 84
  requests (the sweep's pan, e-reader, toastie, eye cream, exfoliant and retinol requests, the ten blind-test
  questions and the 27 sweep answers that differ from converge-1's): 18 answers differ, each in the items' scope. Of
  those 27, 5 are these edits (the two e-reader answers, the induction-hob frying pan, the toastie maker, eye cream
  for dark circles) and 22 the library's. Full sweep of 278 answers: 200 with 3 picks (converge-1: 200), 19 with 1 or
  2 (20), 59 with none (58), 631 picks (632), no error. Two answers move by more than their item: "non toxic frying
  pan for induction" loses Scanpan (PTFE), so its first reading has 2 picks and the pipeline reads 48 threads, which
  reshuffles it (Caraway, GreenPan and an All-Clad saute pan whose facts are unconfirmed; De Buyer's carbon steel pans
  drop out of the wider reading, not looked into: for the names owner); "a frying pan for an induction hob" gets
  HexClad as its second pick (induction confirmed by its FAQ) with no price or availability yet.
- Built by Claude, 19 Oct 2026 (the round-3 logic builder, branch round3-logic from main 4f2851d: the orchestrator's
  seven items from the final review, docs/bfs-2026-10-17/final-review.md; technical calls within Noemi's rules,
  reported to her; eval/RUNS.md): (1) Her feature rule (decision 1 of 16 Oct) didn't hold for "gaming laptop under
  £1000" because a thread asked for a feature by its post too: a uni laptop thread whose post said its writer games on
  a desktop counted as asking for a gaming laptop, so every answer in it, Apple's line among them, was praise for
  gaming. A thread now asks for a feature by its title only (engine.features.thread_asks_for: a slimmed post keeps a
  list of words, which can't tell an ask from a mention); no laptop is praised for gaming, so the answer shows the
  type's best (Lenovo, Framework, Asus Zenbook) with the not-praised note. Three other answers' picks move by the same
  rule (quiet dishwasher: a KitchenAid its writers call quiet for the Asko line; minimalist wallet: Ridge above
  Saddleback; laptop backpack: the Osprey Daylite for the GR2, each praised through a post only). For "stainless steel
  pan for searing" the note was right (no pick praised for it) but the reason counted any voice whose comment said
  stainless; it now counts a voice about a feature only when it praises its product for it (ScoredMention.
  needs_unpraised, the reason only: counted nowhere, the 2qt saucepan answer lost its Tramontina pick, whose writer
  listed it among stainless brands; dutch ovens' "about enamelled" and quiet kettles' "about noise" counts fall too).
  (2) A voice or a name saying the opposite never counts: open ear, bone conduction or hearing traffic is no praise
  for noise cancelling, even in a thread asking for it, nor is a product whose name has a word starting "open"
  (config.OPPOSITE_QUOTE_PATTERNS["noise cancelling"], FEATURE_OPPOSITE_NAMES): the three noise-cancelling answers'
  third pick is the Sony XM6 (was the Shokz OpenRun Pro 2, recommended as open-ear in an ANC thread). A recommendation
  whose words about its product say the opposite of a request word doesn't talk about it (OPPOSITE_QUOTE_PATTERNS
  ["cold"]: not insulated, won't keep drinks cold). Not fixed, since no voice in the threads read says the opposite:
  Nalgene (its "about keeping drinks cold" voices keep track of their water or mention cold water) and the
  Chef'sChoice electric sharpener for Japanese knives (no writer of it talks about Japanese knives; it is a pick on
  overall support, which a kitchen answer's first reading allows). (3) What to look for and Skip these never
  contradict a pick, its model, an item above or the requested form: an Avoid naming a pick's kind in the type's own
  words is left out ("oil cleanser", "balm" above an oil cleanser and a cleansing balm; the 17 Oct check read only the
  words beyond the type's); a Look for whose same kind's warnings say what the request asks to be without goes, its
  Avoid stays (mineral sunscreen beside mineral SPFs' white cast; one test changed on purpose, dated); a Look for
  naming the opposite of a feature the request names goes, an Avoid agrees (corded drill, bone conduction headphones);
  Skip these leaves out a product a shown pick, its most named model or an Also worth a look item names in full
  (Adrenaline beside the Brooks line's Adrenaline, G502 beside the G502 wireless). Not fixed: "Avoid: automatic milk
  frothers" above the Sage Milk Cafe (nothing we hold says it is automatic: no facts or price entry, no writer).
  (4) A kitchen or general tip naming another appliance (config.OTHER_APPLIANCES, or module 1's names: "hand grinder"
  is a coffee grinder) and not the type asked for is left out (pressure cooker, food processor, rice cookers, electric
  kettle for stovetop kettles, toaster ovens, hand grinder for espresso machines, heat pump water heater); cookware,
  knives and tools are no appliances, so kitchen's cast-iron exception stands; a general tip for a use the request
  doesn't name is left out ("Windows laptop for accounting", "SDS drill for concrete"; a reason or price after its
  "for" isn't a use: config.FOR_A_REASON_WORDS); DIY electrical and battery care tips are left out like repairs
  (config.CARE_TIP_LEFT_OUT_WORDS). (5) A pick's quotes, order only: one that swears (the page's masked words) or
  opens negatively (config.QUOTE_NEGATIVE_OPENINGS) comes after a clean one of its kind; one naming its product only
  as the yardstick for another (QUOTE_YARDSTICK, not after "nothing" or "never") or naming a sibling of it (the
  writer's name starts with its brand, has a word its name hasn't and lacks one it has, spellings compared loosely)
  after the rest of its tier, as a quote about another product does (one test changed on purpose, dated). Seven
  first quotes change: Cetaphil, CeraVe Eye Repair, JBL Clip, Eufy, Tempur, Herman Miller Aeron, All-Clad. (6) No
  "Price not checked yet" beside "Not sold in the UK": such a product's price text is empty (engine.answer.
  shown_price), the page shows no price line and says "Not sold in the UK" at a glance (93 picks and 61 items in the
  sweep). (7) The daily plan job's requests include the demo and interviewee requests (engine/data/demo_requests.json,
  98 product requests, now in the public repo), and those answers' and the blind-test questions' shown and
  next-in-line comments are read first (engine.precheck.Candidate.first and priority), so the site's reading ahead
  reads them first: 3,298 comments of 108 requests (4,945 with tiers 2 and 3), about 7 hours of pings at 40 a ping,
  then kept fresh as answers' comments are; 559 requests (config.PLAN_MAX_REQUESTS, 650, keeps the plan's working out
  well inside its 55-minute task timeout, which the free-tier sums count). Results: the whole suite passes (6,052);
  every eval number as main's but the library's own quote counts (266 thread files rewritten at 00:07 after main's
  eval) and shown 245/245 (b02's mineral sunscreen line); blind test 10/10 full top 3s with the same picks; the sweep
  (docs/bfs-2026-10-17/sweep-3-logic.jsonl) against sweep-final: 124 of 278 answers differ, each by an item, full top
  3s 200 as before. FOR NOEMI: may a credible warning against a pick's kind demote it in a kitchen need answer (the
  Chef'sChoice electric sharpener under "Avoid: pull-through sharpener")? Nalgene's "not insulated" and the Milk Cafe's
  "automatic" would need fact fields the lists don't have yet (data, not rules); the demo and interviewee lists are now
  public in the repo.
- Built by Claude, 19 Oct 2026 (the round-3 names builder, branch round3-names, from main 4f2851d: the orchestrator's
  four items from the final review of 19 Oct, docs/bfs-2026-10-17/final-review.md; the alias file, the brand-lines,
  facts, price and pages lists, module 4's name code and tests, no other code; technical calls within Noemi's rules,
  reported to her; eval/RUNS.md): (1) The same product twice in one answer, joined. Office chair: the alias file writes
  "Aeron" (and "Aeron remastered", "Aeron size B", "Aeron 2", whose single mentions had kept the bare name loose) as the
  "Herman Miller Aeron", so its 36 + 14 mentions are one product with the price, page and image the lists give it (24
  voices; it was "Aeron office chair line" beside "Herman Miller Aeron"). Phone: the brand-lines entry "iPhone" is now
  "Apple iPhone", with writers' "iPhone" as its other name, so that line is shown as "Apple phone line", as the Apple
  entry's is, and the two are one pick (17 voices; an alias would have shown every model as "Apple iPhone 11", and
  test_names_round_two keeps "iPhone 11" as written). Toothbrush: the alias file writes "Philips Sonicare" and "basic
  Sonicare" as "Sonicare", so the Sonicare line is one (151 mentions, 98 voices, instead of 95 and 52 apart); the bare
  Philips line stays apart (Philips makes other things) and is hidden beside the Sonicare pick; "Oral B Braun" and
  "Braun Oral-B" are written as "Oral-B" (Braun is its maker, not a model). FOR NOEMI: joining the two lines frees a
  place in the top three, and her 10 Oct rule (a brand line steps aside for its own product shown with it) lets a thin
  product take it: the answer is now Sonicare (98 voices), Oral-B Vitality (7) and Aquasonic (4), the Oral-B line's 62
  voices having stepped aside for Oral-B Vitality (first tried, "Sonicare" written as "Philips Sonicare": the same, with
  "Philips DiamondClean" first, then "Oral-B Braun"); a ranking rule that asked a product for a share of its line's
  support first would keep the line, and is hers to decide. Laptop: "ThinkPad" is written as "Lenovo ThinkPad", so
  ThinkPad and Lenovo are one "Lenovo laptop line" (29 voices; Framework's line takes the freed place). (2) Garbled
  names. "Sleep on latex latex bed" (what an extraction typed) is written as "Sleep On Latex mattress", the price and
  pages lists' name (still "Not sold in the UK"); Bose's "QuietComfort Pros (Ultras?)" as "Bose QuietComfort Ultra
  Headphones", the price list's name (the Bose line shows that model with its £399.95). The basic Kindle: "basic
  Kindle", "Basic in matcha green", "basic matcha", "matcha basic" and "2024 Basic" are written as "Kindle Basic"; a new
  brand-lines entry "Kindle Basic" gives its line a from price (£134.99, John Lewis, from the 18 Oct findings for the
  Amazon Kindle (2024), not read again); and module 4 (engine/group_products.py, _attach_descriptions) joins a name of
  descriptions alone to the one brand name here that holds it, as a model's one-word name takes its brand: the 29 bare
  "basic" are "Kindle Basic" (30 voices, was 17 under "Basic"); a name of descriptions alone with no such partner is
  generic (_only_a_description; a bare "basic" is the only one in the library). The e-reader answer is as before but for
  that line's name and its garbled model. A price in front of the requested type's words alone ("$30 rice cooker", "£20
  kettle") is no product (module 4, _a_price_point: generic, never ranked or shown); a price before a maker ("$150
  Ninja", 36 library names start with a price) stays that maker's mention. (3) Pan facts, from the makers' own pages
  read on 19 Oct 2026. OXO: oxouk.com says its Ceramic Professional pans (and its Agility ones) have a
  diamond-reinforced ceramic coating that is "No PFAS" (with the note that no intentionally added PFAS were used in the
  manufacture) and an induction base, so the model b10's pick names (writers' "OXO ceramic professional non-stick") has
  a facts entry "OXO Ceramic Professional" (pfas_free, non_stick and induction true), a price entry (John Lewis,
  re-read: £75 to £95 by size, £75 as before) and a pages entry (the OXO UK page). It is named without "non-stick" so
  that OXO's generic "non-stick" names (writers who name no model) don't find it: they stay on the older entry "OXO
  non-stick pan", PFAS unknown, since OXO's Good Grips Non-Stick Pro pans (Lakeland) are only marketed "PFOA-free",
  which is not PFAS-free, and the maker names none as PTFE (oxo.com, OXO's US site, answered 403 to the page read and
  was not tried another way). b10's pick is now "OXO Ceramic Professional", with no note, its £75 and its OXO UK link;
  the answers to b10 and to "non stick pan without teflon that lasts" change in that pick only. FOR NOEMI: the claim is
  OXO's own and hedged ("no intentionally added PFAS"), like HexClad's; this reverses round 2's caution on purpose (the
  coordinator's item: "decide by its named model"), and one test is changed with a dated note
  (test_kitchen_data_round.py: its OXO library no longer has a writer naming the model; the generic names still carry
  "we couldn't confirm it's PFAS-free"); if b10's answers were captured for the blind test already, this pick's name and
  note differ from the capture. Caraway: carawayhome.com's own page for its ceramic fry pan says non-stick, made without
  PTFE, PFOA and PFAS, and works on induction, so the line's entry "Caraway frying pans" says non_stick true (the note
  "we couldn't confirm it's non-stick" is gone); Caraway also sells an uncoated stainless steel fry pan, which the entry
  no longer cites. (4) Not built, FOR NOEMI: Anessa's origin ("korean sunscreen"), Nalgene's lack of insulation ("keeps
  drinks cold") and Berkey's being a countertop system ("water filter jug") have no fact in the vocabulary
  (engine/config.py: PRODUCT_FACT_VALUES has no origin, insulated or form fact, PRODUCT_FACT_RULES reads none, and the
  type "water filter" holds jugs and countertop systems alike), so no list can record them: each needs a new fact, its
  product types and its request words, a user-facing rule. Not done either: "Huawei watch gt7 pro" (lowercase) and the
  Lenovo line's model for a university laptop, "Lenovo Legion 5a Gen 10" (a gaming laptop, £1,780: one of the few Lenovo
  models with a price entry, while the ThinkPad E14 Gen 7 that writers name most, in 8 mentions, has none). Tests: 66
  new in engine/tests/test_round3_names.py (each item's names and facts from the committed lists, and made-up libraries
  that reproduce the final review's duplicates and garbles before the fix). Results (eval/RUNS.md): the whole suite
  6,089 tests (6,088 passed in the heavy run; the one left, test_metrics.py's check that the run has a row in
  eval/RUNS.md, passes with this note's row); the evaluation as round 2's in every number but the library's own (quotes
  found word for word 84,947/85,018, 71 not found as before; 6 fewer mentions, the price-in-front names; 11 fewer
  product groups and 4 fewer loose ones, as the short names join names); blind test 10/10 full top 3s, unverified quotes
  shown 0 (shown 246/246); the full sweep of 278 answers (docs/bfs-2026-10-17/sweep-round3-names-final.jsonl) against
  the final review's: 18 answers differ, each in these items' scope (office chair 1, phone 1, toothbrush 2, laptop 2,
  mattress 3, e-reader 2, rice cooker 2, headphones 3, the two pan questions), and the counts are the same: 200 answers
  with 3 picks, 19 with 1 or 2, 59 with none, 631 picks, no error.
- Noemi's decisions of 19 Oct 2026, on the convergence's last questions: (a) a first pick that is sold out
  everywhere stays the first pick, in answers and in the blind test ("if it's sold out it means it's good, i want to
  know about the product"); (b) when the first reading and the wider reading give as many picks, the wider one wins
  if more of its picks have a credible voice about the request's need or feature (the smartwatch answer's Garmin);
  (c) no country preference anywhere in ranking: "let's make sure we are showing the possible best picks
  independently of the country" (the not-sold notes stay, as information only); (d) a top-level answer in a thread
  whose title asks for the need counts as talking about it; (e) phone and webcam communities may be added; (f) a
  maker-discontinued product listed only by Amazon marketplace sellers isn't counted as still sold; (g) essences stay
  out of toner answers; (h) a travel system can be a stroller pick; (i) for fast-moving tech, "not super old tech, but
  let's make sure other options still relevant count": very old evidence about models no longer current can't make a
  pick, while evidence about models or lines still sold counts whatever its age; (j) a credible warning against a
  pick's whole kind (electric sharpeners for Japanese knives) pushes products of that kind down; (k) HexClad is shown
  as PFAS-free from its current coating, with a note that most reviews are of the older one; (l) on-demand reading
  comes back on after the interviews, with a cheaper reader; (m) in the blind-test packets, a pick's one-line summary
  is its "why". The blind-test capture of the rivals: Claude's call ("does it matter? let's do the best option").
- Built by Claude, 19 Oct 2026 (the round-4 builder, branch round4 from main 5683b2d: Noemi's decisions of 19 Oct 2026
  above, and the coordinator's items 10 and 11 from her later notes; technical calls reported here): (b) when both
  readings give as many picks, the wider one wins if more of its picks have a credible voice about the request's need
  or feature (engine.pipeline._wider_wins): "smartwatch for fitness" now shows Garmin's line first (and Amazfit's Bip
  6), from the wider reading, where Huawei's watch stood alone. (d) A top-level answer (a direct reply to the post) in
  a thread whose title asks for a need counts as talking about it for the need rule of every skincare and haircare
  reading and of the wider reading (ScoredMention.needs_by_title; its reason, weight and standing out still go by its
  own words, so a reason never counts a voice "about dry skin" that never said so); the feature rule takes a thread's
  ask for top-level answers only, replies needing their own words (until then every comment of such a thread had it).
  (g) Essences stay out of toner answers (config.KINDS_KEPT_OUT_OF_TYPE: a product the AI types as an essence, or
  named one and never a toner, is another type; a request naming an essence keeps them, and a toner whose name holds
  "essence" stays): "toner w/o alcohol for combination/normal skin" loses COSRX's Snail 96 essence and shows 2 picks.
  (h) A travel system already was a stroller pick ("travel system" is one of the stroller's names): a test keeps it so.
  (i) Fast-moving tech (config.FAST_MOVING_TYPES): a comment older than config.FAST_MOVING_OLD_EVIDENCE_YEARS (5,
  PROPOSED) says nothing for or against a product unless it, or the line it is, is known to be still sold (a price-list
  entry counting it as sold, abroad too, or a brand-lines entry saying the brand sells the type). The TV answer is
  unchanged: its 1999 Trinitron is told in comments of 2023 (the rule judges a comment's age, not the age of the set it
  describes); the laptop answers are unchanged; "mesh wifi for a three storey house" loses Eero and Netgear Orbi (no
  entry says either is sold: a brand-lines entry would bring them back) and shows 2 picks. (j) A kind credible voices
  warn off as they would a product (at least 2 writers, outnumbering its credible recommendations: engine.rank.
  warned_off_kinds) takes config.KIND_WARNING_PENALTY (PROPOSED: KIND_BONUS's size) off the products whose own kind it
  is, never for a kind the request names nor one warned about for one use ("... for bread", "... in dry climates":
  engine.pipeline._kinds_not_pushed). Tried first on any negatively supported kind a product was placed in: 59 picks
  moved, mostly by one passing note or by broad placements (a non-stick pan in "Teflon"), so it was narrowed. Now
  "knife sharpener for japanese knives" shows King stones where the Chef'sChoice electric line was third, Bonavita's
  line goes from first to third in "electric kettle that lasts 10+ years" (two writers warned against goosenecks) and
  2 Hounds from first to second in "dog harness". (k) HexClad's facts stay PFAS-free (its current coating), with a note
  shown under it wherever its entry is found: a new optional facts field, shown_note, as a caution ("Note: most reviews
  here are of its earlier PTFE-coated pans."; wording approved by Noemi, 19 Oct 2026). (m) In the blind-test packets a
  pick's why is its one-line summary, its reason line only without one (FORMAT.md, dated note). (c) Checked: no
  ranking step prefers products sold in the UK (rank's order has no availability; the budget, the sold-under-its-name
  and brand-model steps count a product sold only abroad as sold; the price check only compares a budget with prices
  in its currency, keeping the others; the answer never reorders by availability); nothing to fix, and (i)'s still-sold
  counts products sold only abroad. Item 10 (Noemi, of the ILLIYOON line's third quote): a shown quote never holds a
  question asking for other products or suggestions (config.QUOTE_ASKING_PATTERNS, read inside a question only); it is
  cut to the part before it ending on a clause that carries its stance, or not shown, and the pick's other quotes make
  up its two (engine.answer._without_asking). No quote of the 19 Oct sweeps holds one; in the sweeps of 16-17 Oct the
  ILLIYOON line's (17 words) would be cut to its first 6, the writer saying they use and love it. Item 11: the wording
  she approved is marked decided (the how page's privacy, logs, live-check, kept-comments and sold-abroad lines; the
  feature-not-praised note, both brand-wide warning lines, the HexClad note, the not-sold-in-the-UK line, the
  fewer-picks, no-pick, summary and Also worth a look notes; the packets' tester-code line and question heading; the
  vague, gift and department questions). PROPOSED, for her to see: the no-threads message, reworded at her request
  ("We haven't read Reddit about {products} yet, so we'd rather not guess. Try a related product, or one of the
  examples above.", shown as the answer's message under the search box and its examples), and the home page's six
  examples she asked for (dutch oven, pet-hair vacuum, beginner's espresso machine, frizzy curly conditioner, hiking
  boots, carry-on suitcase: none a blind-test type, each a full top 3 in the 19 Oct sweeps; the page groups them by
  category). Tests: engine/tests/test_round4.py (16) and one in test_blind_test.py; changed on purpose, with dated
  notes: the summary test of test_blind_test.py, the retinol library's title in test_needs_and_contradictions.py, the
  example and no-threads pins of test_web.py and test_general_engine.py. The whole suite, the evaluation and the
  sweep: eval/RUNS.md, 19 Oct 2026, round 4.
- Noemi's decisions of 20 Oct 2026 (the pairwise test), and how it was built: (1) friends do a short, blind, pairwise test across categories, about 4 minutes: two short answer cards to one shopping question, ours against ChatGPT's or Vetted's, "A", "B" or "About the same", and an optional why; (2) its 12 questions are docs/test-2026-10-20/questions.json: 7 of the 10 blind-test questions and 5 requests drawn at random (seed 20261020) from the demo requests, gift and pet questions left out; (3) a screenshot of every rival answer is kept as evidence for her interviews; (4) the agents' routine and repetitive work (writing and translating the cards, screenshots, data) runs on Sonnet under the 18 Oct cost policy, while the orchestrator keeps its own model; (5) she approved the "not read yet" message (engine/answer.py NO_THREADS), now marked decided. Built by Claude, 24 Oct 2026 (branch test-page from main bf02758; not merged, not deployed): GET /test (engine/templates/test.html, engine/pair_test.py) is one standalone mobile-first page, English or Italian from the browser's language with a toggle, that never names the site or links to it, and nothing on the site links to it. Each visit gets a new deck: 6 of the 12 questions, two from each category as far as the set allows (both skincare questions go to everyone, each kitchen or "other" one to about two visitors in five), each comparison ours against one rival, three against each, ours on side A in three and B in three (random shuffles, so no visit leans one way). A card shows its picks' names and one-line whys and nothing else; the page is never told the rival or the side (see the verification note below), and the reply is just {"saved": true}. A visitor picks A, B or About the same, may write the why, then presses Next (not an instant move on, so a mis-tap can be fixed); answers are sent as they are given and tried again if the network fails; the tab keeps only the visit's place (sessionStorage, so a reload carries on), no cookie, no visit counting. POST /api/test-response keeps each answer through engine/feedback.py's store as its own kind, "blind_pair" (the visit's id, question, rival, ours' side (both worked out by the server), choice, why of at most 300 characters, language, the page's clock, and the arrival time; never the address), with feedback's checks (JSON only, 8 KB, only from the site's own page, plain words saying what is wrong, a question the visit wasn't asked refused) and a rate limit of its own, RATE_LIMIT_PAIRS (30 in 10 minutes; Claude's call instead of sharing feedback's 15: a test is six answers, so friends on one network or an answer sent again are never turned away, and a test can't use up the feedback's allowance). The cards are data/library/blind_test_cards.json (git-ignored; deploy/cloudrun/make_context.py now includes it; the older Hugging Face Space's push doesn't, so /test says "not open yet" there), read by engine/pair_test.py, which refuses a card with a tool's name, a link, a price, a shop, availability words, more than 3 picks, a why over 20 words or a wrong "no recommendation" note: the page then says the test isn't open (503). `python -m engine.pair_test check` lists what breaks the rules; `python -m engine.pair_test serve` tries the page on this computer with a local store (data/feedback/pairs-trial.jsonl) and no library or model loaded. `python -m engine.blind_test tally-pairs [responses file or dataset export folder] [--cards FILE]` counts, per rival, both together and per category, how often ours was preferred, the rival was, or neither, each with a 95% range (Wilson), the share of ours among the answers that picked a side, and the reasons without who gave them; a visit's repeated answer counts once. The page's words, Italian included, are Claude's, PROPOSED for Noemi to read. Tests: 184 new (engine/tests/test_pair_cards.py, test_pair_feedback.py, test_pair_tally.py, test_pair_web.py, with made-up cards in pair_factories.py), including the page's size (44 KB with the longest cards the rules allow, 32 KB with ordinary ones) and its text contrast in light and dark; no test changed. The whole suite: eval/RUNS.md, 24 Oct 2026.
- Verification of the pairwise test, the night of 24 to 25 Oct 2026 (Claude, on branch test-page, before any deploy; reported to Noemi): the page was run locally with a local store (python -m engine.pair_test serve, answers to a scratch file) and two visits were taken in the built-in browser, one at phone width in English and Italian, one at desktop width, six answers each. Decks were spread (two questions from each category, three against each rival, ours on side A in three and on B in three, over 3,000 simulated decks too), the cards read well, the stored rows matched what each visit was shown, and `tally-pairs` counted them right. One real problem found and fixed: the deck block in the page carried each comparison's rival and ours' side, so view-source, the browser's developer tools or the tab's session storage told a friend which answer was ours. Now the server makes the visit's id (24 random hex characters and a 4-character fingerprint of the cards' questions) and the deck follows from that id and a key only the server has (HMAC-SHA-256 of CREDIBLE_RECS_TEST_KEY, else of HF_TOKEN, which the live site holds as a secret already; random per run without either), so when an answer comes in with its id and question the server builds the same deck again and reads the rival and the side off it; the page sends and holds neither (a page that sends either is refused), and nothing is kept between the page and the answers, so every Cloud Run instance agrees. An answer whose id was made for other cards (the cards' questions changed mid-visit) or for a question the visit wasn't asked is refused (400) instead of being given a wrong side; changing HF_TOKEN's value mid-test does the same. Tests: engine/tests/test_pair_cards.py, test_pair_feedback.py and test_pair_web.py changed to the new protocol (the spec changed: the page no longer sends rival and ours_side) and gained tests that the page's whole source has no tool name and no side, that a visit's deck is the same on every instance, and that each stored row matches what the visit was shown. Not changed, for Noemi to decide: our cards read recognisably (a count of credible voices, product-line names instead of single models) beside the rivals' use-case lines, which a friend who knows the project could use to tell which is ours.
- Noemi, 24 Oct 2026, "the tool should work for visitors anywhere, not just the UK ... country-aware availability: ok, do it now". Built on branch region (25 Oct 2026, the region builder, from main 1ed01ec; technical calls reported to her, wording PROPOSED). (1) A region choice: a small box under the search box, UK (the default), US, Elsewhere, remembered in the visitor's browser only (its own storage, one of three things it keeps now: the first-time note, recent searches, the region) and sent only inside the answer request. The API takes an optional "region" in the POST body ("uk", "us" or "elsewhere", any capitals, "uk" when left out or null; anything else is refused, 400 bad_region); an answer for another region says which ("region" in the JSON; the UK's answer is exactly as it was, byte for byte but for the timing, and is asked of the pipeline with no new keyword). Choosing another region asks again for the request on screen. (2) The price and availability lines follow the region and nothing else does: the same products in the same order and every other field the same (her decision (c) of 19 Oct 2026; a test compares every field but those two lines across regions). The pipeline looks up what the price list says about the US only for the other regions (engine.prices.us_sale): a USD entry that isn't about a discontinued product, or a page of a known US shop (config.US_SHOPS, 62 retailers and US makers' own stores, PROPOSED, matched by exact address) as an entry's url or among its sources; nothing is read from a note. Today the list has no USD entry; 68 of its 217 entries marked not sold in the UK have a US shop's page among their sources, so those say "Sold in the US at <shop>"; the other 149 say their US availability isn't checked (a USD research pass would add more; to record one, write the entry in USD with "available": false and "not_in_uk": true). The price line shows the same price as the UK's (the budget note is about it), the list's USD price standing in only when it has no other. Remembered answers are kept per region (web._answers keyed by request, library and region), and every region is forgotten together when threads change. PROPOSED wording (engine/answer.py, the page's LABELS, how.html): price "{amount} in the UK, at {shop}, checked {date}" / "From {amount} in the UK, at {shop}, checked {date}" / "{amount} in the US, at {shop}, checked {date}"; availability "Sold in the UK at {shop}, checked {date}" / "Sold second-hand only in the UK: {shop}, checked {date}" / "Sold in the US at {shop}, checked {date}" / "Availability in the US not checked yet" (a US visitor, a product sold only outside the UK, no US evidence; elsewhere "Availability not checked yet"); two sold sides join with "; " the visitor's own first ("Sold in the US at A, checked 9 Oct 2026; sold in the UK at B, checked 9 Oct 2026"); "Not sold in the UK" is shown to nobody outside the UK; the page: "Shopping from" with "UK", "US", "Elsewhere" and "Changes the price and availability lines, never the picks."; the API's refusal: "The region must be "uk", "us" or "elsewhere" (or left out, which means "uk")."; the how page's privacy line "Your region." (kept in the browser, sent with each search inside the request, only to fit the price and availability lines, never changes the picks) and a sentence under "No longer sold". (3) Fast first answers: getting ready warms the search page's six examples and then the 62 demo requests (engine/data/demo_requests.json, the committed copy of docs/bfs-2026-10-17/demo-requests.txt: docs/ isn't in the site's image) before its other warm-ups, with the time limit (WARM_UP_ANSWERS_SECONDS 90, the pings' 40 s slices), the startup probe (4 minutes), the answers' memory (ANSWERS_KEPT_TYPES 64) and the site's 4 GiB as they were. The demo requests span 60 product types, the examples 2 more, so the memory's 64 are nearly full: the list is cut to requests of at most 64 types (web._within_the_memory), the demo's first, and the rest of the old list (latency requests and one request per type, 85 requests now, was 71) is left to its first visitors, as the taxonomy's types are; a longer list would have forgotten the demo requests' warm work as it warmed the others. Noemi's call, left open: a visitor asking a third type outside the demo's makes the memory forget all of them (its existing design, 15 Oct), so keeping the demo warm for longer means a larger ANSWERS_KEPT_TYPES (more memory) or a per-type memory. Tests: engine/tests/test_region.py (42); changed on purpose with dated notes: test_web.py's three warm-list tests (the demo requests first, the list cut to the memory's types, "robot vacuum" now warmed as a demo request), test_web_ux.py's storage test (the region is the third thing the browser keeps) and test_request_privacy.py's body test (the answer's body is {request, region}). The page grew 2.0 KB (117,527 of 122,880 bytes). Run from the worktree (PYTHONPATH set to it), through the heavy lock: the whole suite 6,175 passed, 2 failed: the privacy test above (changed on purpose, then 15 passed) and test_precheck_verify.py's bucket-record test, which fails on main's code as well (it reads today's date against a record dated October 10; not touched). eval/run_eval.py: every number as round 4's but the library's own (84,807/84,901 quotes found word for word: the shared library changed since), blind test 10/10 full top 3s, unverified quotes shown 0. Offline sweep of the 278 answers in the UK region against main's code (the commit this branch started from, 1ed01ec) on the same library: 0 answers differ (199 with 3 picks, 631 picks, no error). The 99 demo and interviewee requests in all three regions on the real library: the same picks in the same order in all 99; every other field the same in 98 (car seat's "See it at Graco" link is left out of the US answer, since the availability line now links to that very page: the existing rule that a product's own link never repeats a line's); "Not sold in the UK" shown to no one outside the UK; the US region's picks say "Sold in the UK" 187 times, "Sold in the US" 17, "Availability in the US not checked yet" 31 and "Availability not checked yet" 42 (no UK entry either).
- Built by Claude, 25 Oct 2026 (branch ondemand2 from main 394e9bf; Noemi's decision (l) of 19 Oct 2026, on-demand reading comes back with a cheaper reader; decided by Claude and reported to Noemi; not merged, not deployed). The cheaper reader did NOT pass the gate (within about 5 points of Gemini 3.8 Flash on both measures), so the reader, the switch (CREDIBLE_RECS_ON_DEMAND stays off by default) and the deploy settings are unchanged and the decision is Noemi's. Measured on her three labelled gold threads with the scorer eval/run_eval.py uses (votes: recommend or warn; 75 of her products in 111 labelled comments), extraction instructions v15, threads read in parts of 40 comments, temperature 0, Google's free tier, written to scratch folders outside data/. Gemini 3.8 Flash today: found 63 of 75 (84%), precision 63/68 (93%), every quote word for word (71/71), matching the 12 Oct figures; Claude's extraction: 97% and 94%. gemini-3.1-flash-lite: found 60/75 (80%), precision 60/71 (85%), quotes 74/76, the same in two runs: 4 points under on found, 8 under on precision (11 products she did not label, for example kettle kinds and bare brand names). gemini-3.5-flash-lite: 75% found and 89% precision (quotes 65/81) in one run, 82% and 82% on the two threads that came back valid in another (the third was not a valid extraction), 79% and 83% with thinking high: noisier and no better. gemini-2.5-flash-lite: Google answers 404, no longer open to new users, on her key. Tried and worse for 3.1: thinking high (two of three threads cut off mid-answer), parts of 20 comments (found 64%, precision 72%). Free limits, read from Google's own 429 answers on 25 Oct (the published pages give none; AI Studio shows them): Flash (3.8 and 3.6) 20 requests a day and 5 a minute; both Flash-Lite 500 a day and 15 a minute. A Flash-Lite call took 10 to 25 seconds against 3.4 to 4.5 minutes for 3.8 Flash (its 4 calls took 16 minutes). So the reader today reads one request a day and takes about an hour of the job's time, not 12 minutes (15 calls a request), which also makes the month's 50,000 job seconds only about 12 requests; a Flash-Lite reader would read about 32 requests a day (480 of its 500 calls) and each would take about 11 minutes (21 at a safe minute a call), so the month's job time (ON_DEMAND_MONTH_SECONDS 50,000 seconds, 40 to 75 requests; the free-tier sums in engine/tests/test_cloudrun.py leave room up to about 113,000) would be the limit. For Noemi: is gemini-3.1-flash-lite acceptable at precision 8 points under Flash? If yes, the change is ON_DEMAND_GEMINI_MODEL, ON_DEMAND_GEMINI_CALLS_A_DAY = 480, ON_DEMAND_CALL_MINUTES = 1, and ON_DEMAND_SWITCH's default in deploy/cloudrun/on_demand.sh from off to on (with the switch tests of engine/tests/test_cloudrun.py, whose spec changes). Built anyway because it does not depend on the reader (engine/tests/test_on_demand_trigger.py, test_on_demand_wait.py, 27 new tests): (1) the trigger of the review of 16 Oct (reading.md R1 and R2): the bar of 6 threads counts only threads not titled as another type (PipelineResult.own_threads_available; a moisturiser had 51 of 102 such threads), and a fast-moving type (config.FAST_MOVING_TYPES) whose newest such thread is over 2 years old (config.ON_DEMAND_OLD_YEARS, PROPOSED) is queued with refresh set, which the job reads although the library has enough threads, taking only threads posted in the last 2 years; the answer keeps its picks and says the threads are a few years old; (2) the visitor's wait is worked out from the queue's length and the day's capacity (engine.on_demand.wait_for): "in about an hour" only while the day's Gemini calls and the month's job time can read the request, an hour more for each one ahead, else the place in line, the daily capacity and the day (tomorrow, the date, or the 1st of next month); wording PROPOSED: "We haven't read Reddit about teapots yet. It's in line: 2 products are ahead of it, and our free reading allowance covers about 1 a day. Check back tomorrow." and, for old threads, "The Reddit threads we've read about laptops are a few years old, so we've started reading newer ones: check back in about an hour."; (3) the job's model is config.ON_DEMAND_GEMINI_MODEL (still gemini-3.8-flash) or the job's CREDIBLE_RECS_ON_DEMAND_MODEL setting, its daily calls 18 (was 100: Google allows 20, and the 100 left the rest to bulk reading Claude's builders do now) and the call and request timings measured above (config.ON_DEMAND_CALL_MINUTES, ON_DEMAND_PRODUCT_MINUTES, ON_DEMAND_FIRST_MINUTES 70, ON_DEMAND_EACH_MINUTES 66, ON_DEMAND_LATE_MINUTES 150; were 20, 15 and 90). Tests changed on purpose, with dated notes: the first-request and second-request messages and the eleventh-in-line state of test_on_demand_site.py. The whole suite and the evaluation: eval/RUNS.md, 25 Oct 2026.
- Built by Claude, 25 Oct 2026 (the verify2 builder, branch verify2 from main 394e9bf; not merged, not deployed; the technical recommendations of the review docs/verify-bfs-2026-10-25.md, within Noemi's rules: the 30-day verification, the 48-hour rule for shown quotes and the free-tier sums engine/tests/test_cloudrun.py checks; technical calls, reported to Noemi; eval/RUNS.md): (1) config.LIBRARY_VERIFY_READS 3,000 to 4,500 a day, with reading ahead's capacity to match: 48 reads a ping in 6 seconds (was 40 in 5), 8 at once as before, and visitors keep 100 of Reddit's 200 reads in each 10 minutes (was 120), so reading ahead takes at most 96 of each 10 minutes' reads (was 80): 13,824 a day against about 9,350 falling due (7,025 first-tier comments every 40 hours, 3,147 fallback ones every 5 days, 4,500 kept ones; the site read 9,600 a day against a cap of 11,520 on 24 Oct). The reserve is the one change of a standing number here: 100 is two fresh answers of the biggest size (an answer reads 10 to 40 comments) and a margin of 20, and reading ahead still stops while Reddit says fewer than 100 are left. New free-tier sums (engine/tests/test_cloudrun.py): the site's reads ahead bill 7 seconds a ping, at most 62,496 vCPU-seconds a month (35% of 180,000; was 53,568, 30%) and, at its 4 GiB, 249,984 GiB-seconds (69% of 360,000; was 214,272, 60%); the pre-check job's 102,300 vCPU-seconds (43%; 152,300, 63%, with on-demand reading's) and Bright Data's 930 records a month are unchanged. (2) The answers' last two tiers (behind the picks, next after those: the fallbacks a failed check brings in) are read every 5 days, not every 40 hours (about 1,260 reads a day freed): the plan lists tiers 0 and 1 as before and the others in a new "fallback" list, a comment on its own day of five (a checksum of its id, precheck.fallback_due), and the site reads a listed one that has no read in the last 48 hours, as it does a kept comment to verify. The 48-hour rule is untouched: a quote is shown only with a passing check from the last 48 hours, and a fallback quote that has none is checked at answer time, as any quote not read ahead (a test reads one at answer time after its read has run out). (3) A kept comment whose embed page is unreadable twice, the second read at least 7 days after the first with no passing read between (config.LIBRARY_UNREADABLE_LAPSE_DAYS), lapses at the next deploy as an expired one does, and is read no more (engine.verify.Ledger.lapsed; the record now keeps when the run of unreadable reads began, \"unreadable_since\": ids, dates and outcomes only; an old record counts its unreadable read as the first). The plan also drops such a comment from the answers it works out, as the deploy will. One unreadable read still proves nothing, so a page Reddit redesigns can't wipe the library in one go. This is the review's option (i) and it changes answers: the 2,031 comments the embed page doesn't show, all from archive-read threads, back 124 of the 554 answers (57 picks), so answers lean on them until the second read: tell Noemi. (4) Kept comments are verified earliest deadline day first, and within one day by use (precheck.USE_LEVELS: the answers' own comments, which the site reads first anyway, then a credible mention of a product an answer shows, then another mention of one or any mention of a product ranked just behind, then the rest), where it was the minute and the thread's order; the plan report gains a projected-lapses line (precheck.projected_lapses: the day-by-day sum of what the budget leaves to pass its 30 days unread, with how many back products answers show, the day with most due, and the unreadable pages apart) and a line for the fallback tiers. On the real library (77,565 kept comments) it gives 23,198 due on 13 Nov and 19,996 on 17 Nov, 15,565 lapses at 2,000 reads a day, 3,241 at 2,400 and none at 2,700 or more or at 4,500, as the review found. Still to do, as the review said: deploy again by 17 Nov. (5) Writers' profiles: an expired profile (older than LIBRARY_REFRESH_DAYS, 30) is neither dropped nor kept but neutral: the store answers MISSING, so module 5 sees a writer the archive doesn't know, with no standing signs for or against them and no flair (no established-member or well-regarded sign, no new-account or low-karma flag). Measured on the 278-request sweep (eval requests, interviewee and demo requests; docs/verify2-2026-10-25/, private, with the profiles as stored and as taken expired, `eval/sweep.py answer ... --profiles-expired`): of 219 answers with picks 77 differ, 53 in the set of picks and 18 in the top pick, 115 differ in Also worth a look and 163 in the quotes shown; the high-credibility voices behind the 631 picks fall from 2,501 to 699; 4 of the 10 blind-test answers change (2 with another pick). So `python -m engine.profiles warm` now asks the writers of the comments in a list first (`--quoted FILE`; `eval/sweep.py quoted` lists the ids a sweep's answers quote: 3,640 comments, 3,448 writers), then those already stored, the stalest first, then those never looked up (neutral already); `--refresh-before TIME` asks again, flairs included, every writer looked up before TIME though the store still holds them, and ends when none is left; `--limit` takes a chunk and looks up only that chunk's flairs; the store is saved every 20 writers and merges what another run saved (a refresh runs for days beside data builders' warms). Found on the way: 40,243 of the 54,446 writers with kept mentions were never looked up (data rounds listed theirs in profiles-later-*.txt), so answers already see 74% of voices without standing; the 14,328 stored were looked up on 9 to 18 Oct and expire on 9 to 17 Nov. The refresh was started at 01:27 EDT on 25 Oct (docs/verify2-2026-10-25/profiles-refresh-loop.sh under caffeinate -i, chunks of 300 through the fetch lock, a frozen copy of the committed code, log docs/profiles-refresh-2026-10.log; stop it by ending that script, run it again with the same time to carry on): quoted writers first (3,448 writers, about 10 hours of calls), then every stored writer (12,195 more, about 34 hours), the quoted and stored tiers together about 44 hours of calls at Arctic Shift's 10 seconds a call, about 2 days; then the 38,803 others never looked up, about 109 hours more, 153 hours (6.4 days) for the whole library, plus a minute between chunks and the waits for the fetch lock (both slots were held by other jobs at the start). Everything is in the store well before 9 Nov if it runs on; it reaches the site at the next deploy (profiles.json is in the bundle). Tests: 68 new (engine/tests/test_read_ahead_capacity.py, test_fallback_tiers.py, test_unreadable_twice.py, test_verify_order_and_lapses.py, test_profiles_refresh.py, one in test_profiles.py); four existing tests changed on purpose, each with a dated note in the test: test_read_ahead.py's reserve (visitors keep at least 100, not 120), its pings' reads (48, not 40) and the 17 Oct batch figures (that day's 3,000 and 5 seconds written out), and test_cloudrun.py's caps on the site's reads ahead (35% of the vCPU-seconds and 70% of the GiB-seconds, no longer a third and 60%; renamed). The whole suite (6,401 passed) and eval/run_eval.py ran from the worktree through the heavy lock; the blind test is 10 of 10 with 3 picks, the same picks as 24 Oct's, unverified quotes shown 0; no scoring code changed. The sweeps hold comments' words, so they went to ~/.Trash/credible-recs-deletion-rule-2026-10-25 (Noemi empties the Trash); the numbers stay in this note and in docs/verify2-2026-10-25/profiles-expired-effect.txt (product names only).
- Built by Claude, 25 Oct 2026 (the data-tech2 builder, branch data-tech2 from main 1ed01ec: the tech data round's second
  pass, after Noemi's decision (e) of 19 Oct 2026, "phone and webcam communities may be added"; technical calls within
  her rules, reported to her; eval/RUNS.md): (1) Communities (test first, engine/tests/test_tech2_round.py): r/iphone,
  r/GooglePixel and r/samsung (each checked on Arctic Shift that day: it exists and posts daily) join the general
  category's decided subreddits and the phone type's communities, after its broad ones; r/Twitch joins both lists for
  webcams (about 25 "which webcam" threads with 10 or more comments in 2024-2026). Not r/webcam, the obvious name: it is
  an adult-content community whose last post is from 2021 (a test pins that it is never added); r/WorkFromHome had two
  weak webcam threads in the same years. (2) Threads: 32 new, 8 each for webcams (7 from r/Twitch, 1 from r/BuyItForLife),
  4k monitors for work (r/Monitors, 2025-2026), smartwatches for fitness (r/smartwatch 6, r/fitbit 2) and phones with a good camera (r/iphone 3, r/samsung 2, r/PickAnAndroidForMe 3), found by Arctic
  Shift title searches cut into date windows (a search over a big community's whole history times out: r/GooglePixel
  times out even on a five-day window, so it gave no thread), read from its archive into a private stage folder, extracted
  by two Sonnet helpers of 16 threads each (extract-v15, every quote word for word, 0 rejected: 1,069 mentions, 86 notes,
  45 agreements), slimmed, and copied to the worktree's own library; I read none of their text. Helpers were told: a
  reply's product name comes from its parent's own words, a tool or accessory named in passing is no mention, tentative
  interest is neutral. One correction by rule, not by reading: the helper typed the 30 bare "Garmin" and "Suunto"
  mentions of a "best smartwatch" thread as "sports watch", but the instructions give a brand named alone the thread's
  type, so they are "smartwatch" (before that, the Garmin line lost its recommenders to another type). The helpers named
  comment ids that look coordinated or paid (docs/bfs-2026-10-17/data-tech2-integrator-notes.txt): kept, as extraction
  never judges a voice. Profiles: Arctic Shift's users endpoint answered 422 and 500 for every try, so 2 of the 39
  writers the answers quote are stored; the rest, and the new threads' other writers, are listed in
  docs/bfs-2026-10-17/profiles-later-data-tech2.txt. (3) Prices, availability and pages for the picks and Also worth a
  look items shown (three Sonnet researchers on makers' UK pages and big UK shops, each page's own name read; Amazon UK in
  the built-in browser with a London delivery address, whose prices it shows in dollars, so only its stock is recorded):
  Logitech C920 GBP 84.99 and Streamcam GBP 139.99 (its page says sold out temporarily), Razer Kiyo V2 GBP 149.99, OBSBOT
  Meet 2 GBP 128.99, Anker C200 and OBSBOT Tiny 2 sold (no price: the maker's price excludes VAT), Dell U3225QE GBP
  853.20, Gigabyte M27UP GBP 298.99 (pre-order only at Scan and Overclockers), Gigabyte M27UA sold at Amazon UK (Scan
  lists it end of life: conflicting, no price), Garmin Venu 4 GBP 379 and Venu 3S GBP 379.99 at John Lewis, Amazfit
  Balance 2 GBP 299.90 re-read at Amazfit UK (one test changed on purpose, dated), Huawei Watch GT 7 Pro sold at Amazon UK
  (no price), the Apple Watch line from GBP 219 (Apple Watch SE 3) and the Samsung phone line from GBP 169 (Galaxy A17 5G,
  John Lewis). No longer sold new, so left out and named: Razer Kiyo Pro, Elgato Facecam Pro, iPhone 16 Pro, Galaxy
  S23 Ultra, iPhone 5S, iPhone XR, Pixel 3 XL, Pixel 2 XL. Left without an entry because the evidence conflicts: Innocn
  32M2V (the maker's page is its US store, Amazon UK lists it out of stock) and Pixel 8a (John Lewis says gone, Google's
  page could not be read); not recorded for a model doubt: Samsung's "Neo G8" (Samsung UK lists neither the G85NB nor its
  successor under that name). engine.maker_pages find ran over the two shown products still without a page (the Neo G8
  and the Vivo X200 Ultra): 0 found. Results: the whole suite (6,170 tests): all pass but test_precheck_verify.py's
  bucket test, which already fails on the base commit since 23 Oct (a made-up date a week old; main fixed it in 126e676);
  the evaluation as round 4's in every number but the library's own (85,876 of 85,970 quotes found word for word, the 94
  not found all in older threads, none in the 32 new; shown 247/247, unverified shown 0); blind test 10/10 full top 3s,
  the same picks; the sweep of 243 answers (docs/bfs-2026-10-17/sweep-data-tech2.jsonl) against main's code on main's
  library the same day (sweep-data-tech2-base.jsonl): 8 answers differ, each traced by stage runs to its threads or lists
  (webcam for video calls 0 to 3 picks, 4k monitor for work 1 to 3 and for photo editing 1 to 3, smartwatch for fitness 2
  to 3, a phone with a good camera the same 3 lines with more voices and the Samsung line's price, running watch one
  Forerunner's voices 4 to 5, and the look-for tips of two camera requests); 171 answers with 3 picks (167), 539 picks,
  no error. FOR NOEMI: (1) "smartwatch for fitness" now shows Huawei Watch GT 7 Pro, Amazfit Balance 2 and the Apple
  Watch line, with Garmin's smartwatch line under Skip these: the first reading takes the 16 threads closest to the
  request and now gives 3 picks, so the wider reading that gave Garmin's line (decision (b)) never runs; in those 16 the
  line has 3 credible recommendations, all from one thread (most Garmin recommendations come from writers who don't say
  they use the watch), against 4 credible warnings, and Garmin's running watches are typed "sports watch", so they don't
  count in a smartwatch answer. Whether a leading brand may go under Skip these on a reading this thin is a ranking
  call (read on when the first reading's top brand has few credible voices, or count sports watches for a fitness
  request), hers. (2) The comment ids that look coordinated (several near-identical
  plugs and one account pushing two brands in the smartwatch thread) count as credible voices today.
- Integrated by Claude, 25 Oct 2026 (the data-tech2 integrator; technical calls, reported to Noemi; the tech data round's second pass after main's 17 commits; eval/RUNS.md): (1) Merge: main merged into data-tech2; the only conflicts were the two append-only notes files (DECISIONS.md, eval/RUNS.md), where both sides' notes and rows stay; the price, page, brand-line and facts lists were not touched by main and load with the engine's loaders; config and code merged without conflict (this branch's four communities and main's new values both stay). (2) The shared library got the round's 32 threads and their 32 extractions (only ids it lacked, none overwritten, copies identical to the branch's) and the 2 warmed writers (its other profile entries untouched); they are archive-read and still need the usual live checks before production answers quote them. (3) Maker pages (Noemi's 15 Oct night rule): `engine.maker_pages find` over the 134 products that the demo, interviewee and blind-test answers show with no page found 18; each page's own name was read and 6 kept: Logitech Lift (UK page, GBP 42.99), Sunday Riley Good Genes (GBP 70), Dermalogica Daily Milkfoliant (GBP 65), Secretlab Magnus Pro (GBP 873), Stratia Velvet Cleansing Milk and Supergoop Unseen Sunscreen (pages and images). The two pages found for Logitech and Secretlab gave the site's generic share picture, not the product's, so their images were left out. Refused: a set for a pan (Misen), another model (Riccar Spirit for the Riccar upright, Baby Jogger City Mini GT2 for the City Mini, Oral-B Vitality PRO Kids Frozen for the Vitality, Midea 50-pint for the Midea Cube, Herman Miller's Mirra 2 stool for the chair, Zwilling's 8 cm vegetable knife for an 8-inch chef's knife, an IKEA 1.0 l pan for 'IKEA stainless steel saucepans'), a part (Orphan Espresso's Lido handle spring), another country's site (Pantene US, CeraVe US, Acaia's US store). Imported with `python -m engine.buyable import --write`: 4 price entries, 6 pages, 2 images. 91 of the 517 products these answers show (picks and also-worth-a-look, brand lines included) now have an image, was 89. One answer changed: 'gentle exfoliant for sensitive skin under 30 pounds' no longer lists Sunday Riley Good Genes (its price is over the budget); its picks, and every blind-test pick, are as before.
- Built by Claude, 25 Oct 2026 (the approvals builder, branch approvals from main 1dc0736; Noemi's "yes to all recommendations" of 25 Oct 2026 on three items; technical calls reported to her; not merged, not deployed; eval/RUNS.md). (1) On-demand reading is back on, read by Gemini 3.1 Flash-Lite (on her three gold threads 80% found, 85% precision, against 3.8 Flash's 84% and 93%; every quote still checked word for word, a test runs the job with this reader and a misquote). config: ON_DEMAND_GEMINI_MODEL gemini-3.1-flash-lite; ON_DEMAND_GEMINI_CALLS_A_DAY 450 (was 18; Google's free allowance is 500, so 50 in hand, since a thread's retries count as calls); new ON_DEMAND_GEMINI_CALLS_A_MINUTE 10, which the job's client (engine.on_demand.reader_client) turns into one call every 6 seconds, under the free 15 a minute; ON_DEMAND_CALL_MINUTES 1 (a call took 10 to 25 seconds, a safe minute), so a request is told 21 minutes (was 66), the first request's wait 25 and each one ahead 21 (were 70 and 66). The wait message's capacity sum: Gemini's 450 calls could read 30 requests a day, but the job's 50,000 seconds a month read only 39 of 21 minutes (about 75 at the 11 minutes a request actually took on 25 Oct), so the month's job time is now what limits the reading, not Gemini, and "covers about 30 a day" beside "check back on 1 November" would not be true: the message still says "about 30 a day" while Gemini's calls decide when the visitor's place is reached, and "about 39 a month" once the month's time does (engine.on_demand.capacity_text, products_a_month, month_places_left; the words around it are unchanged). I left ON_DEMAND_MONTH_SECONDS at 50,000: engine/tests/test_cloudrun.py's free-tier sums allow about 113,000, which would double the reading if she wants it. Left alone, a quirk that was there before: past 150 minutes of waiting a visitor is told the reading is "taking longer than usual", though a request far down the line (the seventh on, now) was promised hours. The deploy switch: CREDIBLE_RECS_ON_DEMAND defaults to on in deploy/cloudrun/on_demand.sh, "off" turns it off for a deploy (any other value is on), the Gemini key is still looked for (without it the deploy leaves on-demand reading off, as before); deploy.sh's comments and DEPLOY.md say so. Nothing was deployed: the first deploy will start the reader job on the site's image if the gemini-key secret is there. Tests changed on purpose, with dated notes (the spec changed): test_on_demand_wait.py (the first request's message and the old-threads message say 25 minutes, were an hour; the test pinning the old reader now pins the new), test_on_demand_site.py (two: the same minutes, and the second request in line), test_cloudrun.py (the switch's three tests: off is "off", not "anything but on"; the default is on) and the docstring of test_region.py. (2) The comments the tech data round's extraction helpers flagged (docs/bfs-2026-10-17/data-tech2-integrator-notes.txt; 19 threads, 54 comment ids of them kept in the library; ids only below, never words), each checked against the voice rubric (paid promotion is low on its own, one red flag caps at medium, copies count both). Already caught by a rule: mqnxxuv (an Amazon associate tag: low), o553a3s with o553tmf and the four near-identical plugs of 1g3d4d2 (copied text; the same writer repeating a comment, m2mv8bg with m2mvj1o, p3bjfgh with p3bjgmd and nijiwyn with nijiytx, stays no red flag by her 11 Oct rule). Moot: ltbvee9, my5b97v, mya4nee, n3n4ohq, m3z4wsx, mlc3hm1, oca4feu and loiw54f hold no mention, so slimming dropped their words and no voice of theirs can count. A rule applied and did not fire, fixed with tests first (made-up text only; engine/tests/test_approvals.py): (a) a page on some other site whose path is "dp-" and an Amazon product code (B0 and eight letters or digits; Amazon's own links say "/dp/") hides an Amazon product behind a redirect, as ra-sl.com's do (round 2 listed that one by host): mlg983p, n2v1wwa and nbyzpew of 1g3d4d2 carried such links under two other sites, so they are paid promotion now (two red flags, low), and the first posted copy, which was the one that counted, no longer counts as a credible voice; a scan of the whole library found the same shape in 1cts50s n0rgg5z, 1j9sqqx n25hbx6 and 1kcaoqg na7n6io (low now, not in the helpers' list) and nowhere else but ra-sl.com's one; (b) a last line that is a dash, a name and "at" a brand (or "from" a brand's team, support, care or service) says the writer works at it, as AFFILIATION_PHRASES does in words: p48aq14 of 1vm7nik (one red flag, "promotes one brand", still medium); it fires on nothing else in the library. Hunches, left alone (no rule applies; listed so Noemi can decide): m2mv8bg (a link to a site that gathers Reddit's recommendations, which the writer may run, but its address doesn't hold their name), m25z99i and m2hi1pa (one writer's app suggestion in two threads: the copy rule is within one thread), m2h4hns (an account named after a brand, whose comment names none of its products), mk8gn83 (a review outfit's name, but no link and no talk of testing), ma8unor (a link to a shop page on an unknown site), mntryyz (an ad-click link with tracking parameters, pasted by a shopper who earns nothing), ngn54ot (a redirect with a code of another shape, a later copy of the plug, so its mentions are left out already), and the praise the helpers found uniform or generated: n2erfm8, ls3q838, oa73uyc, p3d6ttn, p4kccra with p4rjsli, o55kvtr, o6qslqr, o54yjc4, me1wyg3, me40owy, me4m5pw, me4udeq, mam30o1, maqd8z0, ogphpqk, oj55spu, olpr2d6, oew42gk, oezebg0, ocqy0g7, ocx8498, lohwsgd, lp5d5iz, p8z6mbf, p9hsaxz. Effect on answers: none in 22 answers of the affected product types (waffle makers, water filter jugs, shampoos, smartwatches and fitness trackers, running watches; before and after the rules, same code and library): picks, Also worth a look, Skip these and reasons identical. (3) The wordings she approved on 25 Oct 2026 no longer say PROPOSED: the region lines ("{amount} in the UK, at {shop}, checked {date}", "{amount} in the US, ...", "Sold in the UK at {shop}, checked {date}", "Sold in the US at ...", "Availability in the US not checked yet"; engine/answer.py), the control ("Shopping from", "Changes the price and availability lines, never the picks."; engine/templates/search.html) and the on-demand wait message (engine/on_demand.py), each saying "approved by Noemi, 25 Oct 2026"; a test checks all three. Still PROPOSED: the rest of the region work's words (the how page's privacy line, the API's refusal, "Sold second-hand only in the UK" and "From {amount} in the UK"), the old-threads years (ON_DEMAND_OLD_YEARS) and the page's other new words. Whole suite from the worktree on the shared library, through the heavy lock: 6,542 passed (6,505 before; 39 new tests in engine/tests/test_approvals.py, 8 old ones changed on purpose). eval/run_eval.py: every number as round 4's but the library's own (85,010 of 85,200 quotes found word for word), blind test 10/10 full top 3s, unverified quotes shown 0.
- Built by Claude, the night of 25 to 26 Oct 2026 (the classics builder, branch classics from main 3de5185; the technical fixes
  of docs/classics-review-2026-10-25.md, within Noemi's rules: the picks bar, the weights, the voice rubric and the reading
  window are untouched; technical calls, reported to her; not merged, not deployed; eval/RUNS.md). (1) Facts, read on 25 Oct
  2026 (data/product_facts.json, engine/tests/test_classics.py): "Vanicream" (moisturiser; fragrance-free), a brand entry like
  GreenPan's, from Vanicream's own All Body Products page, which says all its products are free of fragrance, its face
  products page and its Moisturizing Cream page, so its moisturiser line can be checked for the must-have instead of left out
  as "a whole brand can't be checked"; "CeraVe Moisturizing Cream" (fragrance-free) from cerave.com's page, which says so
  twice (its UK page, "Moisturising Cream Pot", does not, so it is not cited); "La Roche-Posay Lipikar Balm AP+M"
  (fragrance-free) from two UK stockists' pages (Cult Beauty's, and LOOKFANTASTIC's, now titled Lipikar AP+Max): La
  Roche-Posay's own pages, and Boots, Feel Unique, Superdrug and Escentual, answered the reader with a bot check or a refusal
  and were not got around (the Cicaplast entry is also a stockist's), so a maker's page for it is left for a hand reading;
  "Misen Carbon Nonstick" (PFAS-free only) from Misen's We Don't Kill Birds page, which names the Carbon Nonstick pan
  uncoated and free of PFAS, PTFE and PFOA. Its "non_stick" is left out on purpose: config says non-stick means a coating,
  and this pan is uncoated, so recording it would take the pan out of every non-stick request, whether it counts is the
  review's open question for Noemi. No other product in the review is held back by a missing fact: the others are held back by
  the bar (INKEY, The Ordinary, Good Molecules, Victoria, Lodge Blacklock) or have their fact already (Aquaphor's balm).
  Side effects of the existing rules, kept: a name that fits two entries takes the newest, and names finding one entry are
  one product, so Vanicream names fitting no exact entry ("Vanicream lotion") now join the brand's line, and the CeraVe cream
  spelled with its tub ("... in the tub", "... in the blue tub"), which had stood as a skip of its own in two answers, is
  the cream. (2) Names (engine/data/product_aliases.json, the short names; 40 new tests in engine/tests/test_classics.py,
  written first: of the first 30, 22 failed on the unchanged code and the 8 that passed are neighbours that must not join). Each
  is a decision about what writers meant, so each is listed by name; a short name matches the start of a name, so where a
  shorter one could catch a sibling product a longer entry that gives the sibling its own name goes first. Steelcase Leap V2:
  "Leap V2" (the commonest spelling, 19 mentions in the office chair reading, had been dropped as loose because it fitted both
  "Steelcase Leap V2" and "leap v2 uph"), "Leap" and "leapv2" are written out as "Steelcase Leap V2"; "Leap V1", "Leap
  Plus" and "Leap Frog" (a baby monitor) are guarded; "older steelcase leap" is left alone (it may be the first Leap).
  Dualit Classic Kettle: "Dualit kettle", "Dualit kettles" and one "Dualit (big full size)" (the full-size one, against the
  cheaper smaller kettle) are the Classic Kettle, and module 4's step 5 then joins a bare "Dualit" to it, but only while the
  threads name no other Dualit kettle (a Design Series kettle in the threads keeps the brand a line: tested). Vanicream
  Moisturizing Cream: the tub spellings; "Vanicream cream" and "original cream" are not written out (a writer can
  mean two Vanicream products by them), and the bare brand stays the brand's line. La Roche-Posay Lipikar Balm
  AP+M: Baume, Balm, AP+, AP+M, "Triple Repair Moisturizer", "face and body"; the lotion, the Eczema Soothing Relief Cream,
  Cicaplast and the Baume Light (guarded) stay apart. Misen Carbon Nonstick: "nitrogenated carbon steel pan" and "Nitrited
  Misen" (nitriding is how Misen makes it); a plain "Misen carbon steel" may be the older seasoned pan and is left alone.
  Lodge Blacklock: "Blacklock" gets its maker and "Lodge Blacklock collection" is "Lodge Blacklock"; the 10 and 12 inch sizes
  stay two products, and no answer changes (2 credible recommendations, bar 3). Not built: the review's general rule, "a bare
  brand name joins the brand's only product of that type in the threads", which would fire on any brand whose threads happen
  to name one model (Lodge next to one Blacklock), the library-wide guard (LibraryRanges) being there for that; the same
  result for the five products needed only these names, and module 4's step 5 does the rest where the threads name one model.
  (3) Measured on the same library, offline, live checks off, the query model off, through the heavy lock, before (a copy of
  the worktree before any change, main 3de5185) and after: 278 answers (the blind-test questions, the edge cases, the 37 interviewee and 62 demo
  requests; docs/classics-2026-10-25/sweep-base.jsonl and sweep-after.jsonl, private): no error, 639 picks both ways, 204
  answers with 3 picks (203 before), 16 answers differ, each traced: b04 fragrance-free moisturiser for very dry skin in winter:
  Vanicream moisturiser line first (16 credible recommendations, 5.50; the line had scored 3.15 and been left out), ILLIYOON
  and AESTURA, CeraVe Skin Renewing Night Cream (3.00) now first under Also worth a look; b06 electric kettle that lasts 10+
  years: Cuisinart, Dualit Classic Kettle second (10 credible, 8.50; the Dualit line had 5.56, fifth of the qualifying),
  Fellow Stagg EKG, the OXO line to Also worth a look; b10 and "non stick pan without teflon that lasts": the same picks, Misen
  Carbon Nonstick first under Also worth a look (PFAS confirmed); r03 office chair for back pain: the same three chairs, the
  Steelcase Leap V2 second (14 credible, 7.71; it was "Leap v2 uph", third, 4 credible, 2.36, with a second "Steelcase Leap V2"
  under Also worth a look); "best office chair for long days, under 400": two picks to one, because the pooled Leap is now
  known as a Steelcase chair and priced from 1,239 pounds by the price list, while "Leap v2 uph" had no price and slipped
  past the budget (a thin answer, a correct one); "best moisturiser", "best moisturiser for dry skin in winter",
  "daily moisturizer w spf30+ for dry skin, 1.7 fl oz, $25 or less", "moisturiser without niacinamide", "fragrance free
  moisturiser for sensitive skin under £20" and "moisturiser for dry + sensitive skin, fragrance free pls, 15-25 quid": the
  Vanicream line (with its lotion and loosely named products joined) enters the picks or rises in them, at 3.95, 5.25, 3.70,
  4.17, 3.29 and 2.25, pushing the CeraVe night cream, Tatcha, Etude House, Cetaphil or Vanicream's own lotion to Also worth a look; "28cm frying pan,
  non stick but pfas free, £30-60": Misen Carbon Nonstick is third pick (3 credible, 2.35, with the note that its
  non-stickness could not be confirmed) where it was under Also worth a look in a two-pick answer, its pooled mentions now
  meeting the bar; "electric kettle with temperature control": the Dualit Classic Kettle is second under Also worth a look
  (a kettle with no temperature control; the request's feature orders products, it filters none); "moisturiser that works
  under makeup" and "night cream for my 40s": the skip of the CeraVe cream in its tub is gone, it being the cream. The other
  262 answers are identical (picks, Also worth a look, Skip these, messages). Blind test: 10 of 10 with 3 picks, 245 of 245
  shown quotes verified, unverified shown 0. Whole suite from the worktree (PYTHONPATH set) through the heavy lock: 6,582
  passed (6,542 before; the 40 new ones, and 3 old kettle tests changed on purpose, each with a dated note, since their
  made-up "Dualit kettle" is now the Classic Kettle: test_past_the_picks.py, test_precheck.py, test_summaries.py).
  eval/run_eval.py: every number as before (library 84,960 of 85,161 quotes found word for word; the library's groups 31,327
  to 31,310). FOR NOEMI: (a) whether an uncoated carbon steel pan counts as non-stick (the review's open question, still
  open; Misen's pan is uncoated and sold as "Carbon Nonstick"); (b) reading past 16 threads (the review's other open one) is
  untouched; (c) a brand line backed by a facts entry is not "loose" any more, so it does not step aside for its own product:
  in the under 20 pounds and 15-25 quid answers Vanicream's line and its Moisturizing Cream are both picks, a ranking choice
  left to her; (d) the Vanicream line has no price or brand-lines entry, so it shows "Price not checked yet" while its
  Moisturizing Cream entry says only a marketplace seller on Amazon UK ships it in: a data pass for it (Vanicream is sold
  in the UK by no shop) would settle that.

- 26 Oct 2026 (Claude, the orchestrator; technical, reported to Noemi; the classics round's note (c) decided rather than
  left open): a brand line shown by a facts entry under its brand's own name ("Vanicream moisturiser line": the classics
  round's brand-wide fragrance-free entry) is checked as a product, so its facts can meet the request's needs, but it is
  still its brand's line when picks fold (engine/pipeline.py, _fold_brand_picks, PipelineResult.line_keys): it steps
  aside for its own product shown with it, as every line has since 10 Oct 2026, so its support counts once. Not a new
  rule: the line had slipped past the existing one, and a tester saw Vanicream twice in one top 3. Two of 278 answers
  change, and only those: "fragrance free moisturiser for sensitive skin under £20" (Vanicream Moisturizing Cream,
  ILLIYOON, Vanicream Moisturizing Lotion: the cream and the lotion are two products) and "moisturiser for dry +
  sensitive skin, fragrance free pls, 15-25 quid" (ILLIYOON, the Vanicream cream, Etude House). The blind test is
  untouched (b04's Vanicream line has none of its own products in its top 3). Also data/brand_lines.json: Vanicream sells
  moisturisers (its products page and where-to-buy page, read today: seven moisturisers, only US shops, no UK price, so
  no from price), so its line links to the maker's page. Found reading the reader's output, for later: of the 28
  threads read on demand by Gemini 3.1 Flash-Lite, 45 of 695 mentions fail the extraction check, 20 of them because the
  reader wrote the evidence level "no first-hand use" as a reason tag (the reason tags are config.EVIDENCE_TAGS); 10
  are quotes not found word for word (corrected the same day: a first, rough count had said 2) and 13 replies marked as
  naming their product further up that aren't replies to a reply. The reader's instructions should say levels and tags
  apart.

- 26 Oct 2026, afternoon (Noemi: "okay to all four recommendations"), her decisions on the classics review and the
  comparison with ChatGPT and Vetted, each as recommended:
  1. Read past the first 16 threads even when they give 3 picks, for popular product types (many threads in the
     library), as long as answers stay fast (docs/classics-review-2026-10-25.md: b04 reads 16 of its 165 threads). With
     it, the type rule must stop dropping a product whole when many of its mentions are typed as another kind (Aquaphor:
     124 of its 194 mentions typed lip balm).
  2. An uncoated carbon steel pan does not count as non-stick: it becomes non-stick only after seasoning, so for
     "non-stick without PFAS" it isn't the same thing (ChatGPT had picked Misen's carbon steel pan).
  3. Model names instead of lines where credible writers name a model; the current tech models named where an
     owner-reviewed line continues; a "best for" label per pick, taken from what its credible voices talk about.
  4. The blind test's cards of our answers are refreshed to the improved answers before she sends the test; ChatGPT's
     and Vetted's stay as captured on 24 Oct 2026.
  Decision 2 built at once (Claude): data/product_facts.json's Misen Carbon Nonstick now says non_stick false, as every
  other uncoated carbon steel pan's entry already did (OXO, Merten & Storck, De Buyer, Lodge, IKEA, Matfer); the
  classics builder read Misen's page on 25 Oct 2026 and found it uncoated (the page refused a second read today: too
  many requests). In answers asking for non-stick it is now left out as not non-stick instead of shown with "we
  couldn't confirm it's non-stick".

- 26 Oct 2026 (Claude, readertags builder; a technical fix, nothing user-facing): the on-demand reader (Gemini 3.1
  Flash-Lite, extractor "gemini:gemini-3.1-flash-lite") mixed up two fields, so its instructions now keep them apart.
  What was wrong: over the 28 threads it had read, the word-for-word check kept 650 mentions and dropped 45. 20 of the
  45 had the evidence LEVEL "no first-hand use" written in evidence_tags, the field of reason tags (config.EVIDENCE_TAGS
  has no such tag; the levels are config.EVIDENCE_LEVELS): 10 had it alone, 10 beside a valid tag ("vague", "asks about
  it", "mentions flaws", "secondhand"). 2 used the thread's own id as the comment id (no refers_to). The rest: 10 quotes
  not found word for word and 13 refers_to problems (the orchestrator's recount, 26 Oct 2026, over the 29 extractions
  then in the library: 46 of 704 mentions dropped), which this does not touch. Checked against the real Gemini the same
  day (one call, a made-up kettle thread): the reply schema was accepted, and hearsay came back tagged "secondhand", a
  question "asks about it". The reader gets the extraction
  instructions (engine/prompts/extract_mentions.md), written for Claude Code, plus the thread; nothing in either said
  that "no first-hand use" has no tag of its own, and the thread's id sits on the first line of what it reads, next to
  the comment ids. What changed (engine/gemini_extract.py only): (1) every message now ends with plain rules built from
  config (field_rules): "evidence" holds one level; "evidence_tags" holds at least one reason tag from the listed ten,
  spelled exactly; "no first-hand use" is not a tag, so for it the reader gives the tags that fit the comment ("secondhand"
  for someone else's experience, "asks about it" for a question, "vague" for nothing concrete, offered as examples); a
  comment_id is one of the bracketed ids of the comments in that part, the thread's id is the post's and never a comment
  id, and a product named only in the post's own text is not a mention. (2) The reply is asked for in a JSON Schema
  (extraction_schema, generationConfig.responseJsonSchema) that only allows the listed tags, levels, stances, categories
  and, per part, that part's comment ids; a test keeps its fields equal to the extraction models'. If Gemini answers 400
  to the schema, the request goes again at once without it and the client stops sending it (one extra call; a line on
  stderr), so a schema it dislikes can't stop reading. Not changed, on purpose: no code maps "no first-hand use" to a tag
  (which tag fits depends on the comment), engine/extract.py's check is as before and still drops a wrong tag, the
  instructions file and its version (extract-v15) are untouched so no extraction counts as out of date, and no existing
  thread was extracted again. The effect on the dropped mentions is not measured yet: it shows when the next threads are
  read on demand. Not yet tried against the real Gemini (tests never reach it): Google's v1beta lists responseJsonSchema
  as deprecated in favour of generationConfig.responseFormat.text.schema, though it still takes it; one real read of a
  made-up thread would confirm the schema is accepted (the fallback above covers it if not).
- 26 Oct 2026 (the bestfor builder, Claude; Noemi approved the label in principle, "okay to all four recommendations",
  decision 3's third part; the rules, numbers and wording below are Claude's, reported to her, not yet approved one by
  one): a "best for" label per pick, from our own evidence only (engine/best_for.py; no AI writes anything per request).
  Three kinds, at most one a pick, never the same label twice in an answer, none for a lone pick (nothing to be best
  against):
  1. A topic its credible voices write about ("Most praised for sensitive skin", "...for being quiet", "...for build
     quality"; config.BEST_FOR_TOPICS: 49 topics with the words that find them, skin and hair types, what a product is or
     leaves, and kitchen and general features). The pipeline notes, for each credible recommendation, the topics its
     writer's own words about the product hold (ScoredMention.topics, engine/pipeline.py _score): only the sentences about
     that product (engine.credibility.product_text), never the words of the product's own name ("Bose QuietComfort" is
     not "quiet"; "Cetaphil Gentle Cleanser" is not "gentle"), never a clause that negates or complains ("not for
     sensitive skin"; a negation after the word counts unless it negates a complaint: "does not react"). A topic is a label
     when at least 2 of the pick's credible voices write about it, at least 2 more than any other pick has, and they are
     at least a fifth of the pick's own voices (2 of 175 voices is no trait of a pick). A topic the request asked for is
     never a label (every pick fits what was asked). Medical conditions (eczema, rosacea, dandruff) are not topics: a
     label can't say "for" them without suggesting a treatment. Each phrase says only what its words say (a test checks:
     "Best for eczema" would need a voice saying eczema; "unscented" and "fragrance-free", "wavy" and "curly" are separate
     labels).
  2. Long-term use ("Most backed by long-term use"): the pick with at least 2 voices after long-term use, at least 2 more
     than any other pick, at least half of its own voices, and a share at least 10 points above every other pick's (in
     buy-it-for-life threads nearly every voice writes after years of use, so the biggest pick would always lead).
  3. Price ("Lowest price of these picks"): only when every pick has a checked price in the shopper's region and
     currency (UK: pounds; US: dollars; elsewhere: none), checked in the last 30 days, and not a brand line's "from"
     price, and the cheapest is at least 10% below the next. Never from what voices say about price.
  Each label carries its basis, the numbers it rests on ("4 of its 12 credible voices write about sensitive skin; the
  other picks have 1 and 0."). Shown on the pick card under its name, in the JSON as `best_for` {text, basis, kind} (null
  for most picks), in the text answer, and in one sentence on the how-we-score page. The kinds of engine/group_kinds.py
  are not a label source: a kind says what a pick is (shown in the reason and under "What to look for"), not what it is
  best for. The 278-request sweep: 63 of 639 picks get a label (10%), in 61 of 220 answers; 28 long-term use, 14 price, 21
  topics; none repeated within an answer; no pick's order, quotes or anything else changes (the same 278 requests
  answered with and without the labels, in one process, differ in nothing but `best_for`). The numbers are cautious on
  purpose: with a lead of one voice instead of two, 37% more labels, but "2 against 1" is a thin "most". To label more,
  config.BEST_FOR_MIN_LEAD and BEST_FOR_MIN_SHARE are the levers; to cover more product types, config.BEST_FOR_TOPICS
  needs words per type (the sweep's commonest words in credible recommendations are the place to look). The reading
  builder's wider reading gives picks more voices, so the thresholds should be looked at again after that merge.
- 26 Oct 2026 (Claude, the names builder; Noemi's decision 3 of the afternoon, first two parts: "model names instead of
  lines" and "the current tech models named"; technical and wording calls reported to her, each new wording marked in
  engine/config.py; branch `names`, from main 66d410f, not merged, not deployed):
  1. A brand-line pick is titled by the model its credible writers clearly name most (engine/pipeline.py,
     _leading_models; engine/answer.py, _titled_by_its_model). The pick is still the line's: its key, score, reason,
     support, voices, downsides and place are the line's, so only what is shown changes. "Clearly" (my value, from the
     numbers; the brief's example was "at least half"): at least 2 credible voices, at least twice as many as any other model
     of the line, and at least a quarter of all the credible voices that name one of the line's models (the line's
     brand's specific products in the ranking whose names say a model, known or not). On the baseline's 398 line picks
     (170 lines) with a known one-model leader, "half and more than any other" gives 26 picks, 12 lines and models, three of
     them (Hero 4 voices to 3, Bonavita 4 to 3, Fellow 3 to 2) a one-voice margin, and misses four leaders by far in a
     long list of models (Kobo's Libra Colour 18 voices to 5 of 45, Travelpro's Platinum Elite 10 to 3 of 24, Vitamix's
     5200 18 to 4 of 44, LOWA's Renegade GTX 8 to 4 of 17); the rule used gives 36 picks, 13 lines and models. The values
     are config.BRAND_MODEL_TITLE_MIN_CREDIBLE, _LEAD_RATIO and _MIN_SHARE; BRAND_MODEL_TITLES_ON False gives the answers of
     26 Oct back. A title must also be a name we can stand behind: a name giving one model (never "Adrenaline/Glycerine
     GTS", "S7 or S8", "(Ultras?)"), not starting with a size ("8" wusthof classic"), a known product (_a_known_model, as
     for "Most named model": never a size, a description, a discontinued model or a shop's code), not another material than
     the one asked for (a non-stick Tramontina pan as the first pick of "stainless steel pan for searing": found in the
     baseline's answers), not less suited to the request than the line by the ranking's own keys (unconfirmed must-haves,
     features praised, skip list, a shortfall that is the request's and not the bar's), and not sold only abroad while
     another model of the line, or the line itself (its brand-lines entry found on sale), is sold in the visitor's region
     (the Vitamix 5200 against the Vitamix line). No clear lead: the line's name and "Most named model", as before.
     Shown with the title: a note saying how many credible voices are about the model and how many about the line in
     general, and that the counts below are the line's ("The model named most in the Bose QuietComfort headphones line.
     Credible voices: 2 about this model, 8 about the line in general. The counts below are the line's."; at the top of
     the box of counts on the page, and under the title in the text answer); the model's own price, where it is sold, page
     and image where the lists have them, else the line's as before; the quotes naming the model first (the model's own two
     at most, then the line's); no "In short:" summary (it sums up the line's voices, whose words may be about its other
     models). The blind-test packet keeps the note whole under the title (its last sentence aside) and cuts the reason
     and quotes to the 90 words instead.
  2. The current model of a fast-moving tech pick or Also worth a look item whose reviewed model a newer one of the same
     line has replaced (engine/current_models.py; data/current_models.json, 10 entries naming 12 products, read on 26 Oct
     2026 for the tech products the baseline sweep showed): "Current model: Kindle Scribe (2025)", the page's link
     ("John Lewis page") and "checked 26 Oct 2026", as one line on the card (a link opening in a new tab) and in the text
     answer. The reviewed model is the name the answer shows: a pick's or item's, the model that titles a line pick, or the
     "Most named model" of one; it must be exactly an entry's name (never a likeness: the XM4 and XM5 are one letter
     apart). A line (not one model) counts only when more than half of its credible voices wrote before the current model
     came out (the page's year or month; before its first day): the writers of a line reviewed whichever model was current
     when they wrote. None of the two Kindle lines' entries shows today (18 of the Paperwhite line's 45 voices wrote before
     2024, 3 of the basic Kindle line's 30 before 2026); they stay in the list for a later library. Nothing is shown for a
     current model, a model the list doesn't hold, or a type that isn't fast-moving. Sources: the maker's own page for
     Bose (UK), Ultimate Ears (UK) and Garmin (its UK guide of 29 July 2026, which lists the Forerunner 570 and 970 as its
     Advanced and Elite running watches, and its newsroom's announcement of 15 May 2025; Garmin's pages never say
     "replaces", so the 255, 265, 955 and 965 point to the 570 and 970 by tier); a big UK shop's, John Lewis's, where the
     maker's page refused an automated read (Sony 403, JBL 403, Amazon 503; Currys and Argos 403 too: none got around):
     the Sony XM6, JBL Flip 7, Kindle Paperwhite (12th generation, 2024), Kindle (2026), Kindle Scribe (2025) and Google
     Pixel 10a (Google's store pages gave no text). Left out for lack of a readable page: Roborock (its UK pages answered 429;
     one retry, then left alone), the JBL Clip (no page gives a release date). Not looked up: the lines whose current model
     differs by brand-wide choice (Apple, Samsung, TV lines), and models still current.
  New tests, written first: engine/tests/test_model_titles.py (55), engine/tests/test_current_models.py (38); changed on
  purpose, each with a dated note: the name helper and 4 tests of test_pick_polish.py, the pick helper and one list of
  test_line_links.py, one test of test_pipeline_worth.py, and the key lists of test_web.py (2) and test_answer_worth.py
  (a pick has "line", "line_note", "current_model"; an item "current_model"). Whole suite from the worktree (PYTHONPATH set)
  through the heavy lock: 6,676 passed (6,583 on main). Sweep of 278 answers against a control run of the same code with the
  two features off, back to back (so the library and the profiles are the same): 18 answers differ, 260 are identical. 14
  have a pick titled by its model (Victorinox Fibrox in "first chef's knife under £100 for a home cook", which is the blind
  test's b07, and in "best chef knife under £100"; Bose QuietComfort Ultra Headphones in 3 headphone answers; Kobo Libra
  Colour in 2 e-reader answers; Travelpro Platinum Elite in 2 suitcase answers; Sage Bit More toaster in 2; EltaMD UV Clear
  Broad-Spectrum SPF 46; COSRX Full Fit Propolis Synergy Toner; Garmin Venu 3S in "smartwatch for fitness"), and 4 more show
  only a current-model line; in all 18 every other field is as before (rank, score, reason, support, voices, picks and items,
  skip lists, messages). The baseline sweep itself differs from the control in 10 answers (two hiking boots answers, an air purifier, two
  dumbbell answers, a cutting board, a mineral sunscreen, "smartwatch for fitness" and two e-reader answers, mostly the
  order or the members of Also worth a look: the library and the refreshed profiles since the baseline ran, not this
  branch). 16 current-model lines are shown in 9 answers (Sony XM4 in 4 headphone answers, Bose in 3, a Pixel
  line pick, Garmin Forerunners 255 and 265 as picks and 955 and 965 as items in "running watch", the Kindle Scribe 2024
  twice, JBL Flip 3 and UE Boom 2). Blind test: 10 of 10 with 3 picks, every shown quote verified (244 of 244, unverified
  shown 0), every other evaluation number as in the control run. Warm times per answer, sweep seconds, against the control
  run back to back: mean 0.69 s to 0.68 s, 90th percentile 1.28 s to 1.22 s (the first version of _leading_models took 27 ms
  an answer and 1.3 s in the worst, +9% on the sweep, for looking under every line of the ranking; now only under the
  lines that may be shown and among the products credible voices named: 1.7 ms an answer on average, 15 ms at worst, with
  the same 278 answers; the current-models list is read once, 0.0 ms). No memory is held beyond the two small lists. FOR NOEMI: (a) "clearly" is twice the next model and a quarter of the voices, not half (above:
  the numbers); (b) a titled pick's "In short:" is left out, and the line's counts stay beside the model's title with the
  note; (c) Garmin's pages say no model "replaces" another: the 255, 265, 955 and 965 are shown the 570 and 970 by tier;
  (d) titles keep writers' spellings where no list writes the name ("Google pixel 8a" is not one today).

- 26 Oct 2026, night (Claude, the orchestrator; technical and wording, reported to Noemi), at the merges of `bestfor` and
  `names`: (1) the "best for" labels are worked out after the model titles, so the "Lowest price of these picks" label
  judges the prices shown (a titled pick shows its model's own price); (2) a model-titled pick keeps its one-line summary,
  said to be about its line ("In short, about the Victorinox chef knife line:", engine/answer.py SUMMARY_ABOUT_LABEL):
  the names builder had left it out, as it sums up the line's voices, but b07's Victorinox Fibrox and r01's Kobo Libra
  Colour, both in the blind test, then lost theirs; (3) the How we score page gets one sentence on model titles and
  current models (the names builder's proposal). Also decided: the names builder's "clearly leads" rule stands (at least
  twice the next model's voices and a quarter of the line's model-naming voices: it titled fewer picks on one-voice
  margins than "at least half" would have), and so does its reading of Garmin's tiers for the current Forerunners. The
  summaries for the 12 blind-test questions (a Sonnet helper, 26 Oct 2026): 42 new and 23 stale ones rewritten in
  data/library/summaries.json (813 entries), so 65 products those answers show or may show have one.
- 26 Oct 2026, evening (Claude, the reading builder, branch reading; technical values and rules within Noemi's decision 1
  of 26 Oct 2026, reported to her; not merged, not deployed). Decision 1 built, measured and explained:
  1. A popular type is read wider even when the first 16 threads give 3 picks. Popular means the library holds at least
     24 usable threads about the product (config.POPULAR_TYPE_MIN_THREADS: half again as many as the 16 read; reading
     every thread instead of the first 16 changed the top 3 of 101 of 130 requests from 24 threads up, 7 of 8 at 23, 3 of
     12 at 17 to 22). What it reads is a choice, made on the numbers: not every thread but every thread that talks about
     what the request asks for (a need in its title or post: PipelineResult.threads_about_needs), or every thread when
     the request asks for nothing besides the product or names an active ingredient, at most 200
     (config.PIPELINE_POPULAR_THREADS; the biggest type holds 172). Reading every thread for every request gave a type's
     most recommended products to all its requests: the 10 shampoo requests got 4 different top 3s (9 from the first 16
     threads, 7 from the threads about the need), the 6 cleanser requests 2 (5 and 5), and a gentle cleanser for
     acne-prone skin got two CeraVe cleansers and an oil cleanser. A reading of fewer than 24 threads is no wider one
     (a request with 17 to 23 threads about its need stays as it was). Short of picks, a popular type reads the same
     threads but never fewer than the 48 it always read (so the ingredient-led requests and "salicylic acid wash" go to
     every thread: 1 pick became 3). The wider reading is shown when it has more picks, or as many with as many of them
     talking about the need and not fewer credible voices about it (engine.pipeline._wider_wins, popular): the
     moisturiser for oily skin, read in full, had 90 credible voices behind its picks and 5 about oily skin, against 22
     and 8. `more_threads=None` still reads nothing more; read_more still means "too few picks" (the page's note says so),
     and a new PipelineResult.read_wider says the reading shown is a popular type's. With a live checker, the first
     reading of such a type is not checked against Reddit until it is known to be the one shown (the sweep's 36 popular
     answers would have read 9 comments each, from Reddit's allowance of about 200 in 10 minutes, for quotes not shown).
  2. The type rule no longer drops a product whole when many of its mentions are typed as the requested kind
     (engine.pipeline._many_typed_as_requested): at least 6 mentions typed so by the AI (twice a pick's 3), from at least
     4 threads (twice a pick's 2), count by the AI's type alone, not by the writer's words (counting words had kept a lip
     cream in a moisturiser answer, a glycolic toner in an exfoliant one and an air fryer oven in an air fryer one); a
     brand or line (loose group) is judged as before. On the library with every thread read, for the product type of each
     of the 278 requests, it keeps one product: Aquaphor Healing Ointment in moisturiser answers (9 mentions typed so, of
     29, in 5 threads; the rest are typed lip balm or ointment and still count for nothing). It then ranks 29th of 880
     in b04's widest reading, and a sweep with only this rule switched off gives the same 278 answers: it changes none.
  3. Measured, 278 requests, the change off and on back to back (docs/build-2026-10-26/reading, private): 41 answers read
     more threads (4,132 threads read in all became 5,674; 234,965 comments, 291,723), 39 answers change (31 change picks,
     15 of them the first pick; 8 only the Also worth a look or Skip lists; 3 gain a pick), none unexplained. Warm
     seconds (the sweep's): all answers mean 0.69 to 0.80, 90th percentile 1.27 to 1.61; the 41 widened answers mean 0.58
     to 1.32, 90th percentile 1.16 to 2.93, slowest 3.78. Memory (fresh processes): one answer over the biggest
     type, every one of its 172 threads, peaks within 50 MB of the first 16 threads' (913 and 923 MB with the open model off,
     991 and 944 MB in another run); 41 popular types one after another with the answers' memory emptied between types, as
     the plan job does, 994 MB against 988 MB; never forgetting, 1,357 MB against 1,221 MB. The distinct comments the 278 answers quote: 3,697 became 3,742, so
     the read-ahead load is about the same. Four more products show without a one-line summary (339, was 335). The
     blind test stays at 10 questions with 3 picks and no unverified quote (248 quotes shown, was 244); b04 reads 49
     threads, not 16, with the same three picks (Vanicream's line now backed by 31 credible voices across 11 threads).
  Left for Noemi: whether a request with needs should read every thread (the classics review's reading: more evidence
  behind a type's most recommended products, and the same top 3 for most requests of a type) or only the threads about
  the need (built). One switch: config.POPULAR_READS_ONLY_THREADS_ABOUT_THE_NEED.

- 26 Oct 2026, night (Claude, the orchestrator; technical, reported to Noemi), at the merge of `reading`: (1) a popular
  type's wider reading with as many picks is shown, for a request with needs, only when it brings more credible voices
  about the need behind its picks, at a share of their voices at least config.POPULAR_WIDER_NEED_SHARE_KEPT (0.75) of
  the first reading's (engine/pipeline.py, _wider_wins, _need_share; two of the builder's assertions changed on purpose,
  with dated notes). The builder's rule had shown it on as many voices about the need: "shampoo for curly hair that
  isn't drying" read 57 threads instead of 16 for the same 8 voices about the need behind 33 voices instead of 17, and
  put an anti-dandruff shampoo second; "shampoo for fine oily hair" went from 11 of 18 to 11 of 33. Both keep their first
  reading now; b04 (11 of 32, then 17 of 53) is still read wider. A request that asks for nothing but the product still
  takes the wider reading. (2) The builder's open question, read every thread of a popular type or only those about the
  request's needs: only those about the needs (its default, POPULAR_READS_ONLY_THREADS_ABOUT_THE_NEED), since every
  thread gave most requests of a type the same top 3 (10 shampoo requests: 4 different top 3s); a technical reading of
  Noemi's decision 1, reported to her.

- 26 Oct 2026, night (Claude, the orchestrator; Noemi's decision 4 of 26 Oct 2026): the blind test's cards of our answers
  (data/library/blind_test_cards.json, git-ignored; the old ones kept in docs/build-2026-10-26/cards-before-27oct.json)
  are refreshed to the answers of main f83f456 (the classics fixes, the reading, names and bestfor rounds, the
  summaries for the 12 questions); ChatGPT's and Vetted's cards are unchanged (captured 24 Oct 2026). Our picks change in
  b04 (Vanicream first; CeraVe's night cream out), b06 (the Dualit Classic in, Bonavita out), b07 (the Victorinox pick
  titled Victorinox Fibrox, its why said to be about Victorinox's chef knives), r01 (Kobo Libra Colour, likewise about
  Kobo's e-readers), r03 (the Leap V2 in, the Mirra 2 out) and r05 (three webcams, where our answer had none on 20
  Oct). The whys were written by a Sonnet helper from each pick's summary as the site shows it (the vague "Often
  recommended..." ones replaced; specific unchanged ones kept), at most 20 words in English and Italian; prices and
  "Lowest price" labels left out, as the cards' rules require; "KP" and "OBS" spelled out by the orchestrator.
  `python -m engine.pair_test check`: every rule followed.

- 2 Nov 2026 (Claude, the orchestrator; Noemi bought crediblepicks.com at Porkbun on Claude's recommendation of 31 Oct
  2026, after choosing the name Credible Picks): the site's address is crediblepicks.com, through Firebase Hosting in
  front of the Cloud Run service (deploy/cloudrun/hosting.py; DEPLOY.md, Firebase Hosting and the domain); www is sent
  on to it, and the run.app address keeps working. The service takes requests whose page names the domain, www,
  credible-picks.web.app or credible-picks.firebaseapp.com (deploy.sh's SITE_DOMAINS, set live on revision 00077 before
  the next deploy). The rate limit tells visitors apart behind Hosting by skipping Google's own front end, the last hop
  Hosting adds (engine.web.client_address, GOOGLE_FRONT_ENDS): Google's long-standing blocks for its own services from
  its published list, never Google Cloud customers' ranges, one hop at most, and only after a public address. Seen
  first-hand on 2 Nov 2026 with a throwaway service that echoed the headers it received (deleted the same hour):
  Hosting drops a visitor's own X-Forwarded-For, and Cloud Run's front end writes the address it was reached from
  last. A request that comes straight to run.app with a made-up X-Forwarded-For is still named by its own address.
- 2 Nov 2026 (Noemi, "yes remove both blind test metrics"): the How page no longer shows the blind test's two
  results, preferred over Vetted and preferred over ChatGPT (engine.how_page.SHOWN_HEADLINE_KEYS), and its test
  questions are no longer called the ones testers will judge in the blind test. The first round is done, the page
  showed both as not measured yet, and its result is told in person instead. Both keys stay in eval/metrics.json and
  engine/metrics.py, so the blind-test tooling (save_blind_test, carry_blind_test) keeps working for a second round.
- 2 Nov 2026 (Claude, the orchestrator; technical and wording calls, reported to Noemi; found by the launch drafts'
  fact-check): (1) the How page never rounds a share short of all to "100%" or a share above none to "0%"; it shows
  one decimal rounded toward the middle (62,969 of 63,023 quotes found had read "(100%)", now "(99.9%)";
  engine.how_page._percent). (2) data/gold/CANDIDATES.md describes each thread in our words: the posters' own titles
  are out of the repository, under the rule that keeps Reddit users' words out of tracked files (their links and ids
  stay). (3) The README gives each data source's real share: 2,500 of the 2,670 threads through Arctic Shift (about
  half from its published history files), 126 through Bright Data, the first 20 through Parse; live checks through
  Bright Data and Reddit's embed page.

- 3 Nov 2026, built by Claude (the launch-load fix (a), for the Show HN around 10 Nov; a technical call, reported to
  Noemi, nothing in the pages changes): the home page and the How page can now be kept by Firebase Hosting's CDN. The live
  site is one Cloud Run instance at most (8 requests at a time) behind Hosting, and every response said `Cache-Control:
  no-store`, so every visit to the home page woke and used the server that also works out answers. In public mode,
  `GET /` and `GET /how` answered 200 now say `public, max-age=60, s-maxage=600` (engine/web.py, PAGE_CACHE_CONTROL and
  cache_control); /api/*, /test, /ready, every error and 404, every other path, and local mode keep `no-store`
  (engine/tests/test_web_cache.py). Checked first: both pages are the same bytes for every visitor (nothing in them is
  read from the request; the site sets no cookies; the test asks both with different cookies, addresses, countries,
  languages, browsers, origins and query strings and compares them) and change only with a deploy: eval/metrics.json,
  which /how reads each time, is tracked in git and so baked into the image (`git archive HEAD`), like the templates,
  the example requests and data/product_pages.json. Values: 60 seconds in a browser, 600 in the CDN, so a spike costs the
  server about one request per CDN location per ten minutes. Firebase's documentation (manage-cache) says a Cloud Run
  response is kept only if it says `public` and a lifetime, that a redeploy clears all of a site's cached content across
  the CDN, and that cookies other than `__session` are stripped; it does not say the redeploy clear applies to Cloud Run's
  responses, so that is not proven. deploy.sh therefore releases Hosting right after the site is deployed (step 3b,
  `python -m deploy.cloudrun.hosting release`, the same release every time and a failure never stops a deploy), and the
  values are chosen so that if it clears nothing, a page is at most 11 minutes old after a deploy. Also: a response
  large enough to be gzipped now always says `Vary: Accept-Encoding` (the plain copy said nothing, so a cache could have
  held it for everyone); HEAD stays unsupported (Python's own 501, never marked `public`). Not done: answering
  conditional requests (ETag/304: the CDN's re-asks every 10 minutes get the page whole), a HEAD handler, and any
  defence against cache-busting query strings (a random `?x=` reaches the server each time; the page is cheap to make).
  DEPLOY.md, Firebase Hosting and the domain, has the details and how to check a deploy (`x-cache: HIT` on the second
  request).
- 3 Nov 2026, built by Claude (branch load-busy-cap; technical calls, reported to Noemi; the page's wording is PROPOSED and
  waits for her yes; merged into main on 3 Nov, not deployed): a load fix before the Show HN of about 10 Nov. The problem: fresh answers
  are worked out one at a time, Firebase Hosting cuts any request at 60 s, and the per-visitor rate limit does nothing
  against many visitors at once, so a crowd would queue behind the lock, see a generic error at 60 s, and leave the server
  working for answers nobody waits for. Built on the public site only (engine/web.py; values in engine/config.py, "A busy
  site", each with its grounds):
  (1) A cap. An answer that isn't remembered and would have to queue is refused at once, 503 with code "busy" and a
  Retry-After header, when 4 visitors already wait for their turn (BUSY_MAX_WAITING: Cloud Run lets 8 requests in at once,
  so the answer under way and 4 queued leave 3 places for pages, the keep-warm ping and remembered answers), or when its
  turn doesn't come within 20 s (BUSY_MAX_QUEUE_SECONDS: with the 45 s deadline it leaves 25 s for the visitor's own
  answer, over the slowest fresh answer measured through Hosting, 21 s on 2 Nov). Remembered answers are never refused,
  and a visitor whose time ran out is still given the answer worked out for someone else meanwhile. Warming (warm_up,
  warm_more) takes the same turns as before, with no limit, so it is never refused, and still gives way to a waiting
  visitor; the only other user of the lock is clear_answer_cache, which the tests use.
  (2) A deadline. No answer waits for Reddit past 45 s after the request arrived (ANSWER_DEADLINE_SECONDS: Hosting's 60 s
  less 15 s of slack), queue time included. The live checker can now be told how long a read may wait (LiveChecker.check,
  wait_at_most): a read that would start later is not made ("later"), as a read asked not to wait already was, and a check
  saved in the last 48 hours still answers at any time. For the comments only "Also worth a look" and the summaries quote,
  that is the road built on 13 Oct: what stands on them is left out and the answer isn't remembered. For the comments the
  picks need, that road doesn't work: the pipeline treats "later" as harmless only for those extras, and left on a pick's
  quote it would leave the quote shown unchecked. The other road, dropping them as unreadable (what the 60 s wait limit
  does today), changes the picks without a word, because the votes go with the comment (tried on the made-up kettle
  library: one comment dropped, the top 3 became 2, and the thinner answer was remembered). So, past the deadline, an
  answer whose picks can't be checked is refused as "busy", and the checks made are kept, so the retry finds them. No
  quote rule is loosened: a quote is shown only with a passing check from the last 48 hours, and an answer cut short is
  never remembered. The deadline cannot cut the engine's own work before the checks, or a Reddit read already begun.
  (3) The page's wording for "busy" (engine/templates/search.html, LABELS.errors): "Lots of people are asking right now.
  Please try again in a minute." (PROPOSED by Claude, waits for Noemi's yes; the page does not use Retry-After).
  (4) Local mode (python -m engine.web without --public) has neither the cap nor the deadline: it serves one visitor, with
  nothing in front of it that cuts a request, and a refusal there would only get in the way of Noemi's own testing.
  Two things found and left alone: an answer that dropped comments as unreadable (a read that failed, or would wait over
  60 s) is remembered like any other, so one visitor's thinner answer can be served to the next for up to a day; and a
  crowd asking the same request at once is queued like any other crowd, though all but the first would be answered at once
  when the first finishes (answering them together would be kinder; not built).

- 3 Nov 2026, Noemi's yes ("yes to everything"; built by Claude on branch home-wording, not merged or deployed; the
  facts behind each line were checked first, and the wording below is hers except where said):
  (1) The home page's intro now reads "Up to three picks for what you buy and use, across about 350 kinds of product,
  from moisturisers and kettles to headphones and suitcases, ranked by how credible the people recommending them are on
  Reddit, not by how popular a product is. Every quote is checked word for word against its comment." Checked: counting
  the product types with 6 or more saved threads the way the launch notes did (engine.library coverage, the saved
  threads each type's name finds) gives 354 on 3 Nov 2026 (353 at launch), inside the 330 to 370 that keeps "about
  350"; "carry on suitcase" and "noise cancelling headphones" each answer with 3 picks in the 3 Nov sweep.
  (2) Step 3 of "How it works" now reads "Word for word against its comment, and again on Reddit in the 48 hours before
  it's shown, so a comment found deleted or edited is never quoted." (the live check an answer relies on is the last 48
  hours', engine/live_check.py).
  (3) The How page's privacy item on Google's logs now says the site sits behind Google's Firebase Hosting and runs on
  Google Cloud Run. What Hosting keeps was looked up, not assumed: Google's Firebase privacy page says Hosting uses the IP
  addresses of incoming requests to detect abuse and keeps that IP data for a few months; Hosting's documentation says
  its CDN logs every request but the logs reach a project's Cloud Logging only once the project is linked in the
  Firebase console (then 30 days); and this project's Cloud Logging has no Firebase Hosting log and no sink for one
  (gcloud logging logs list, read-only), so it is not linked. The page therefore does NOT say Hosting keeps nothing (the
  suggested shape if it kept no logs): it says Firebase Hosting also sees every request, that Google says it uses IP
  addresses to detect abuse and keeps that IP data for a few months, and that we have not turned on Hosting's own
  request log for us to read. This is wording Claude wrote from those facts, not the approved sentence: Noemi to read it
  before the deploy ("a few months" is Google's own phrase; it gives no number of days).
  (4) The "hiking boots" example chip (its top pick, Danner, isn't sold in the UK; its third pick had no availability
  check) is replaced, in the same place, by "noise cancelling headphones": 3 picks (Sony XM4, Bose QuietComfort Ultra,
  Sony XM6), each sold in the UK, in the 3 Nov sweep; a tech request, so the chips now span kitchen, home, tech, hair and
  travel. The tests that pin the chips and the warm order hold: the headphones request is a demo request too, so it is
  now warmed fifth instead of at its place among the demo requests, and "hiking boots" is still warmed as a demo request.
  Left alone and told: the "conditioner for frizzy curly hair" chip has 3 picks, but all three read "Availability not
  checked yet" in that sweep.
  (5) /test is closed: data/library/blind_test_cards.json, the one file that opened it, was moved (not deleted) to
  eval/blind_test/answers/blind_test_cards.json, which git ignores and deploy/cloudrun/make_context.py never bundles (it
  bundles `git archive HEAD` and data/library's named files only), so the next deploy serves the closed page (503). The
  closed page now says "This test has closed. Thank you to everyone who took part." and, in Italian, "Questo test è
  chiuso. Grazie a chi ha partecipato." (was "isn't open yet ... try again later"). The runbook says how to check the
  cards where they are, and how to open a second round (put the file back in data/library and deploy). The API's own
  error text for an answer sent to a closed test (web.TEST_CLOSED, never shown by the page) was left as it was.

- 4 Nov 2026, built by Claude (branch makeup-threads, not merged or deployed), from Noemi's report that "blush" on the
  site said it had counted one thread while Google's top results for it were big Reddit threads in r/Makeup and
  r/Sephora ("let's do better threads wise"). Code only: no thread was read or extracted on this branch.
  (1) Communities, PROPOSED until Noemi said yes (she did the same day, "Yes, plus r/AsianBeauty": the note of the
  makeup rework below): r/Makeup and r/Sephora (a shoppers' community, not run by the
  retailer) are general-category subreddits, and r/AsianBeauty (skincare's already) is listed for the general category
  too, so foundation, concealer, mascara and lipstick may search it. Every makeup type searches r/Makeup, r/Sephora,
  r/MakeupAddiction and r/drugstoreMUA, in that order. r/MakeupRehab (a no-buy community) stays decided but no makeup
  type searches it. Not added: BeautyGuruChatter, Ulta, makeupexchange.
  (2) Types (401 now): bronzer (with the contour products), highlighter and setting powder are types of their own;
  until now "bronzer" was answered with blushes and "translucent powder" with setting sprays. Blush and setting spray
  lose those names. Every makeup type's title words include its plural ("blushes", "eyeshadows"...): Arctic Shift's title
  search matches whole words only. Plain "contour" is not a bronzer word ("a mattress that contours" stays a mattress),
  and "highlighter pen" is a lookalike. The extraction instructions are extract-v16 (v15 plus the three new names, as
  v13 was; every earlier extraction is still current: EXTRACT_STILL_CURRENT), so the extraction brief should name v16.
  (3) Advice searches (the archive reader only; Parse's paid search never runs them): the first two title words with
  "favorite", "recommendations" and "best", subreddit by subreddit, over the whole history, at most 12
  (ARCHIVE_ADVICE_WORDS, ARCHIVE_ADVICE_SEARCHES). A request with no need words ("blush") had no search but the newest
  100 posts per title word, which never reached the big threads asking for recommendations. "recommendations" is
  asked before "best" (the plan had them the other way) because in a replay of the searches only that order reached all
  three of Google's threads within 12. A post only an advice search found is kept only when its title asks for advice
  (a question mark, an asking start such as "what", "any", "best", "help", or a buying flair): "favorite" is also how
  people show off a look. When a round is ended by failures but some searches answered (a busy archive, not a down one),
  the need and advice searches still queued are asked once each, never halved, until 3 fail in a row: they are lighter
  than the broad ones.
  (4) On-demand: a site folder's threads that came from the job's own bundle are no longer counted as baked into the
  site (the queue's "had"), so a request whose only threads came from the bundle is read again instead of closed as
  having enough; the answer then says "more" rather than "haven't read" (PipelineResult.own_thread_ids).
  (5) A round cut short (some searches failed and fewer than 6 threads chosen) waits and is tried again later, up to
  ON_DEMAND_MAX_TRIES, keeping the threads it read; the next try reads only the rest, chosen from the whole mix.
  (6) Makeup's threads are ranked by age as skincare's and haircare's are: an old makeup thread loses the old-post
  points (REFORMULATED_TYPES: the 13 makeup types; general's other types are not reformulated). Corrected the same day
  (the reviewer): this note first said makeup "ranks like skincare and haircare", which is more than was built. The
  voice's old-post cap (OLD_SKINCARE_POST_MAX_VOICE, engine/credibility.py: an old comment is at most a medium voice)
  still applies to skincare and haircare only, so an old makeup comment can still be a high voice; left as it is, an
  open question for Noemi (the rework note below).
  (7) Timed on a busy archive: the blush request's search round took 455 and 876 seconds (22 and 41 calls; r/Makeup's
  searches timed out almost every time, over its whole history and over the last 3 years alike), and the six threads
  it chose (four of 107 to 238 comments) are 17 Gemini calls, up to 24 for six big ones. So ON_DEMAND_ARCHIVE_MINUTES is
  17 (6) and ON_DEMAND_CALLS_PER_PRODUCT 24 (15): a request is 41 minutes of the job (21). What visitors are told
  changes with it (the wording is unchanged): the first in line "in about 45 minutes" (25), the second "in about an
  hour" (45 minutes), "about 18 a day" (30) and "about 20 a month" (39). Noemi to be told. The minute a Gemini call is
  given is still the safe one (calls took 10 to 25 seconds), so these are generous. Superseded the same day: Noemi
  said "Keep 25 min", and the values are main's again (the rework note below).
  Measured on the dry run (no thread read): 762 candidates (280 in a first dry run whose round ended before the advice searches, which is why a busy round
  now still asks them), 6 threads chosen, none
  from r/MakeupRehab; of Google's three threads, the r/Sephora one was among them and chosen, a second r/Sephora one was
  found by an advice search in a later probe, and the r/Makeup one was out of reach while r/Makeup's searches timed out.
  Only "blush" is in Noemi's words; the other makeup types got the same changes because they share the cause.

- 4 Nov 2026, integrated by Claude (the makeup integrator, branch makeup-threads; technical calls, reported to Noemi; the
  first data round of the branch; not merged, not deployed; eval/RUNS.md): (1) Threads: 10 for blush (the plan's batch 1:
  r/Makeup 3, r/Sephora 4, r/MakeupAddiction 2, r/drugstoreMUA 1), among them Google's three (r/Makeup 1d62brq, r/Sephora
  1n4xixh and 1hyd7j3), read from Arctic Shift's archive with the branch's engine (14 calls, none failed, no Bright Data
  record; 1,376 comments saved), extracted by one Sonnet helper (extract-v15 with the makeup rules; v16 only adds the three
  new type names and every v15 extraction stays current): 1,771 mentions (1,621 recommend, 98 neutral, 52 warn), 11 notes,
  72 agreements, 0 rejected, in the stage and again in the library. Slimmed (995 comments kept whole), then copied into
  the shared library without overwriting (2,673 to 2,683 threads, 2,656 to 2,666 extractions; the unslimmed copies stay
  in the stage, under docs/, for the deletion rule). I read none of their text. Batches 2 to 7 (84 threads, 11 other
  makeup types) were not read: the plan holds them for Noemi's own yes (cost rule 3, no extra types), so bronzer,
  highlighter, setting powder, foundation, concealer, setting spray, makeup primer, mascara, eyeliner and brow gel still say
  "we haven't read Reddit about X yet", and lipstick still has 1 pick. (2) Comment ids the helper flagged (ids only, in
  docs/build-2026-11-04/makeup/integrator-notes.txt): two accounts that push one small brand across 3 threads each, a brand
  gift, a free sample, a makeup artist by trade, one generic praise; none is quoted in the three blush answers and that
  brand is in none of their lists; they count as ordinary voices, as in earlier rounds. (3) Profiles: 360 of the new
  threads' writers were looked up (29 behind the blush answers' quotes first, then the stalest; 1 failed), kept with the
  library for 30 days; 386 are listed for later in docs/build-2026-11-04/makeup/profiles-later-makeup.txt, which the
  refresh due before 24 Nov asks anyway (a writer not yet looked up counts as neutral). The warm also dropped 1,676 stored
  writers and 2,409 flairs of the 3 Nov store whom no kept comment in the library needs any more (what warm always does),
  and it changed no stored entry. The blush answers moved with the profiles: before any new profile the picks were Milani,
  Rare Beauty Soft Pinch and Nars Orgasm, after 360 writers Rare Beauty Soft Pinch, Milani and Patrick Ta (Nars Orgasm now
  Also worth a look), so they may move again when the other 386 are looked up. (4) Results, all offline with live checks
  off: the whole suite 6,915 passed and 1 failed (test_library's unlabelled gold thread 1v40u3t, which fails on main too);
  the evaluation as the 2 Nov row in every number but the library's two (30/30, 25/25, 25/25; fits 19/24, useful 23/24;
  ordering 75/79; votes 73/78 and 73/75; voice 12/12, evidence 30/30; blind test 10/10 full top 3s), the library's quote
  count 84,874 of 85,381 with the 10 new threads at 1,771 of 1,771 (the 507 not found are in older threads). Corrected
  the same day, from the reviewer: those two are worse than the 2 Nov row's, not the same (quotes found word for word
  99.41% of the library's, 99.60% on 2 Nov; 251 quotes shown in the 10 blind-test answers, 265), and the cause was
  found: the 3 Nov deploy's verification pass (deploy.sh's `engine.library apply-checks`, before the bundle) rewrote
  1,739 thread files and 1,012 extraction files in data/library between 07:30 and 08:40 that day, dropping the words
  of 2,345 kept comments (291 removed on Reddit, 176 edited, 1,877 unreadable twice at least 7 days apart, 1 no longer
  used) and 3,705 items from the extractions, the deletion and verification rules at work, not this round; the 162
  more not found (345 on 2 Nov) were not traced item by item; the sweep of 293 answers against main's code on main's
  library the same evening: 5 changed, all makeup (blush, blush for fair skin and cream blush from no pick to 3 picks
  of 3 quotes each, 71 quotes in all; bronzer no longer answered as blush; setting powder no longer as setting spray),
  the 10 blind-test answers identical, the other 278 with the same picks (the two e-reader answers differ only in a
  count of threads left out as loose, 10 to 11), 207 answers with 3 picks (204), 650 picks (641), 7,567 quotes shown
  and
  none failing the engine's word-for-word check. The blush answers read 11 threads (the 10 and the lipstick-repair thread
  from r/MakeupRehab that named blush, which no blush quote comes from). (5) Discovery dry run on the branch, run again that
  evening when the archive answered better than in the builder's runs: 408 candidates in 284 s, all three of Google's
  threads among them (ranks 1, 11 and 5), and the mix of 6 took two of them (1d62brq and 1hyd7j3), two more from r/Makeup and
  r/Sephora, one each from r/MakeupAddiction and r/drugstoreMUA, none from r/MakeupRehab.
  (6) Told, not changed: r/Makeup and r/Sephora (PROPOSED) hold 7 of the 10 threads, so main's engine, which does not
  know them, lists those 7 as problems in `engine.extract check` and the library check until the branch is merged (answers
  skip them); do not deploy from main before the merge. No price or page was looked up for the blush picks (the lists hold
  no makeup entry): they say "Price not checked yet" and "Availability not checked yet". "blush for fair skin" gives the
  same three picks as "blush", not the same answer, as this note first said (corrected the same day, from the
  reviewer, who compared the sweep files): its reason line adds "1 of them about fair", it gives 3 things to look for
  ("blush" 2), and Haus Labs' place and quotes differ. The need is recognised but weighs little. "lipstick" and "lip
  tint" still quote one comment of r/MakeupRehab (old library threads, as before this round). FOR NOEMI (answered the
  same day: the next note): yes or no to r/Makeup and r/Sephora as general subreddits (and r/AsianBeauty listed there
  too), whether she wants the 11 other makeup types read (84 threads, about 9,500 comments by the plan's table, Sonnet
  helpers), and the told wait of the builder's note (45 minutes for the first in line, 18 requests a day, 20 a month).

- 4 Nov 2026, evening, decided by Noemi on the makeup round, in her words, and the rework that follows from them (by
  Claude, the lead engineer, branch makeup-threads; not merged, not deployed):
  (1) "Yes, plus r/AsianBeauty": r/Makeup, r/Sephora and r/AsianBeauty are decided subreddits of the general category
  (engine/config.py SUBREDDITS; no longer PROPOSED). r/AsianBeauty was skincare's already: a thread read there for a
  makeup request is a general thread (the request's category wins when the community is listed for it), which the
  library's checks accept, and one read for a skincare request stays skincare (a test of each).
  (2) "Keep 25 min": what visitors are told is main's again (round 1's (7) above is undone): ON_DEMAND_ARCHIVE_MINUTES
  6 and ON_DEMAND_CALLS_PER_PRODUCT 15, so a request is 21 minutes of the job, the first in line is told "about 25
  minutes", each request ahead adds 21, "about 30 a day", "about 39 a month"; the tests of those numbers
  (test_on_demand_wait.py, test_approvals.py, test_on_demand_site.py's two wait checks), deploy/cloudrun/DEPLOY.md and
  on_demand.sh are main's again. To keep them true, the job now keeps a request inside them (technical calls,
  reported): (a) a request's searches are at most 16 calls (ON_DEMAND_SEARCH_CALLS: the round main asks for "blush", 2
  title words in 3 communities over both date windows and 4 warnings, the kind of round main's 6 minutes are for),
  every call counted, halves and second chances too; a search the archive client's 48-hour cache holds costs none;
  `library add` has no budget. (b) Inside it the advice searches replace the weak title searches instead of adding to
  them: the first title search goes alone, and when it answers its full 100 posts (the newest 100 of a word people
  post every day are its last weeks) or fails, the need searches and the advice searches come next (cut so the 4
  warning searches still fit), then the warnings, and the other title searches only fill what is left. When it answers
  fewer than 100, the title searches find every post with the word, and the round asked titles, needs, advice, then
  warnings until the budget was spent. (Corrected 5 Nov 2026, from the rules review: this note first said that order
  was main's. It was not: main has no advice searches and asks its warnings right after its needs, and with the advice
  first the 16 calls ran out before the warnings for most types. Changed the same day: see the note of 5 Nov 2026, the
  makeup fix round, (1).) For a blush-like request (a test with 110 posts a community) that is 1
  title search, 11 advice searches and 4 warnings, and the three big advice threads rank first. (c) Its threads are
  chosen to fit the 15 Gemini calls (engine.on_demand.within_calls: a thread is one call per 40 comments read, at most
  150 comments, so a big one is 4), counting the threads an earlier try already read, and a thread whose calls would
  pass them is left unread with a note; in the test job a blush-like request makes 16 searches and 14 Gemini calls and
  reads 3 of the 4 big advice threads (a fourth, 4 calls more, would pass the 15), a small advice thread and a small
  post. (d) A request cut short (round 1's (5)) and waiting an hour for its next try is told the wait of that try (an
  hour from the last one plus the first-in-line 25 minutes), not 25 minutes. Round 1's other on-demand fix (the
  bundle's own threads not counted as baked into the site) stays.
  (3) "Yes, all 11": the threads of the other 11 makeup types are to be read (batches 2 to 7: bronzer, highlighter,
  foundation, concealer, setting powder, setting spray, makeup primer, mascara, eyeliner, brow pencil, lipstick;
  bronzer, highlighter and setting powder the new types). Recorded here only: that data round is its own step, under
  the cost rules (Sonnet helpers, no builder reading thread text).
  Also, technical calls, reported: the daily pre-check reads the quotes of "blush", "blush for fair skin" and "cream
  blush" ahead first, without warming them (config.PRECHECK_FIRST_REQUESTS; engine/data/demo_requests.json is left
  alone, the answers' memory being nearly full), so their quotes have the 48-hour embed check before a visitor asks;
  the advice tests' two titles that were near copies of real r/Sephora threads, and two titles in code comments and
  a makeup test, are made up now (dated notes in the tests). Open, for Noemi: should an old makeup comment be at most
  a medium voice, as an old skincare or haircare one is (OLD_SKINCARE_POST_MAX_VOICE)? Makeup's threads already lose
  the ranking's old-post points (round 1's (6)); its voices were left as they were, since the voice rubric is hers.

- 4 to 5 Nov 2026, night, the makeup round integrated and checked against its gates (Claude, the integrator, part 2;
  technical calls, reported to Noemi; branch makeup-threads; nothing pushed, merged or deployed):
  (1) The data of "Yes, all 11": the 84 threads of batches 2 to 7 (r/Makeup 27, r/Sephora 26, r/MakeupAddiction 16,
  r/drugstoreMUA 13, r/AsianBeauty 2; about 9,500 comments by the plan) are read, extracted by Sonnet helpers
  (extract-v15; 8,910 mentions kept, 0 rejected, plus 183 notes, 634 agreements and 14 care tips), slimmed and in the
  shared library, now 2,767 threads and 2,750 extractions. The branch's prompt is extract-v16 (it only adds the three
  new type names), and v15 stays current for them (config.EXTRACT_STILL_CURRENT). The unslimmed copies of the 84 are in
  the stage folder until the deletion rule, with the sweeps (they hold commenters' words).
  (2) What the answers do now (sweep of 293 answers, the 15 makeup requests among them): 14 of the 15 give 3 picks
  ("blush", "blush for fair skin", "cream blush", bronzer, highlighter, foundation for oily skin, concealer for dark
  circles, setting powder, setting spray, mascara, eyeliner, brow gel, lipstick, lip tint). "makeup primer for large
  pores" gives 1 (ELF power grip) with the message that there is evidence for only one: the engine finds 2 of the 7
  primer threads, because 5 of their titles hold none of the type's keywords in engine/data/product_types.json ("makeup
  primer", "face primer", "pore primer"...; the titles say little more than "primer"), while an eyeshadow-primer thread
  gets in through the keyword "eyeshadow primer". A keyword fix (a bare "primer" in a makeup community counts as makeup
  primer; "eyeshadow primer" does not), not a data one; not made in this step; it is the next one. Every pick has 3
  shown quotes, each found word for word (8,108 quotes in the sweep, 8,092 after the warm of (7); 0 failing, checked a second
  time outside the engine against the saved comments).
  (3) One-line summaries (summarise-v1, written by Claude reading the extracted quotes,
  engine/prompts/summarise_pick.md): 69 for the products the 15 makeup answers show (picks and Also worth a look),
  checked by `engine.summaries check` in the 25 makeup answers and their wider readings: 0 problems, every one shown.
  One product has none (a glitter primer with two short comments that say nothing more than "it is good", rule 7). None
  cites a comment the helpers flagged (a brand employee, a free product, a recurring pusher of one small brand). The
  same check shows 252 of the 813 older entries failing (their cited comments are no longer credible or readable after
  the 3 Nov verification pass and the profile refresh): not makeup, not touched, and worth a pass of their own.
  (4) Against main of the same hour (517c2c9 on the same library without the 94 makeup threads, 2,673 threads, same
  profiles): the offline evaluation is identical in every number but the library's quote count, which is better (83,103
  of 83,610 found word for word, 99.39%; the branch 93,784 of 94,291, 99.46%: all 10,681 new items found, the same 507
  older ones not); the whole suite passes (6,929) but the known gold thread 1v40u3t; of the 278 non-makeup answers 276
  are identical and the two e-reader ones differ only in a counter, "loose" 10 to 11 (the brand and line names left
  out): one more name, which a makeup brand starting with the same word makes ambiguous (shown names, picks, Also worth
  a look, Skip these and message are the same); the 10 blind-test answers are identical. The branch's code on the
  library without the makeup threads gives 10, so it is the data, not the code.
  (5) The wait numbers are main's (a request 21 minutes, about 25 for the first in line, 30 a day, 39 a month; every
  ON_DEMAND_* value as main's, read from both engines), the page text, DEPLOY.md's numbers and on_demand.sh as in 4 (2).
  (6) Brand pushers: the small brand that two recurring accounts pushed across three blush threads (Phytosurgence,
  flagged by the blush helper) is in none of the 293 answers; the 22 writers the extraction helpers flagged or module 5
  marks (independence signs) back at most 1 of any pick's 4 to 65 credible voices, and the 15 answers keep the same
  picks without them. Taking out four more, whom a rough rule found (4 recommendations of one brand in 2 threads), moves
  one place: the third foundation pick ties with the fourth at 7.05 and a single voice, who also names other brands,
  decides it (Maybelline Super Stay; Nars Light Reflecting would take it). Not a pusher, so nothing changed.
  (7) Left open, for Noemi or the next step: (a) the lipstick and lip tint answers still show one care tip quoted from
  r/MakeupRehab, a no-buy community (an old library comment about wearing a bold lip, there on main too); it is the one
  thing keeping "no quote from an anti-buying community" from holding. Tested: without the two r/MakeupRehab threads the
  two answers keep the same three picks and the tip goes. Options: set those threads aside (the library's set_aside
  folder), or never quote a no-buy community (a small rule). (b) The writers' profiles: 4,519 of the library's writers
  have none yet (565 the answers quote or the blush threads), so many voices count as they are before warming; the full
  warm is the next step (4,519 writers, about 12 hours; the profiles are the 3 Nov refresh's and round 1's 360). To
  answer "are the blush answers stable after warming?" before it, the 205 writers of the blush threads who mention the
  seven blush brands the answers show were warmed first (4 Nov, 23:08 to 23:55 local time, 3 chunks of 70 under the
  fetch lock, one transient failure asked again; 54,152 to 54,361 writers in the store; the store before is saved in the
  scratchpad). Result: "blush" and "blush for fair skin" keep the same three picks in the same order (Rare Beauty Soft
  Pinch Liquid Blush, Milani, Nars Orgasm); the credible voices are the same in number but many move from medium to high
  (Rare Beauty 8 to 20 high of 27, Milani 4 to 10 of 19, Nars 5 to 10 of 16: a writer with no profile can't earn the
  signs of a high voice), and the scores rise (9.9 to 13.0, 9.8 to 12.5, 8.1 to 9.7). "cream blush" moves: Rare Beauty's
  blush line gains 9 high voices (score 6.9 to 8.25) and comes in second, Patrick Ta (7.65 to 7.9) goes from second to third, and
  Glossier Cloud Paint (one medium voice becomes a low one, 14 credible voices to 13; 6.9 to 7.15) leaves the picks for
  Also worth a look. So the blush answers are stable for the two main requests and not for cream blush, and 5 other
  makeup answers moved too (the third pick of bronzer and of highlighter, the order of brow gel's first two, a name in
  the Also worth a look of setting spray, lipstick and lip tint); the 278 non-makeup answers and the 10 blind-test
  answers are identical after it (a second sweep). Until the other 4,300 writers are warmed the makeup picks stay
  provisional, and then the sweep and the summaries are to be redone (6 products the answers now show have none yet).
  (c) The sweeps, the stage folders and the scratchpad files hold commenters' words: they go to the Trash with the
  deletion rule.
- 5 Nov 2026, early morning, the makeup fix round, part 1: matching and grouping (Claude, builder 1; technical calls,
  reported to Noemi; branch makeup-threads; nothing pushed, merged or deployed). From the rules, shopper and integrator
  reviews of the night. Noemi's four answers of the same night (about 00:25: lip tint and brow gel "Split both
  (Recommended)", the need-fit rule "Yes, measure first (Recommended)", the two r/MakeupRehab threads "Remove those 2
  threads", old makeup comments "Yes, like skincare (Recommended)") are the next step's, not this one's: the lip tint
  and brow gel types, the cap on old comments, the need-fit rule and those two threads are as they were. No scoring
  weight or wait number changed, no product type was added, and the engine makes no new call. Measured on one frozen
  copy of the writers' profile store (taken at about 01:30, while the profile warm went on writing the library's), both
  trees on the same copy, live checks off, b83ab95's code before and this round's after, back to back.
  (1) On-demand searches for a rare word (the first title search answers fewer than 100 posts; 4 Nov, evening (b)): the
  round asked titles, needs, advice, then warnings until its 16 calls (ON_DEMAND_SEARCH_CALLS) were spent, and the
  advice searches pushed main's warning searches out. Now it asks main's order, titles, needs, then the 4 warnings, the
  title searches cut so main's need and warning searches fit (the warnings first, then the needs, when even they don't),
  and the advice searches only fill what is left (engine.sources.search_archive). The common-word path is as it was.
  Measured with the reviewer's simulation (a fake archive answering 5 posts a search, every type name: 444 in this
  branch's list; the reviewer's list had 447): warning searches main 1,776, the branch before 486 (219 types with none;
  the reviewer counted 1,788, 486 and 360 of its 447), after 1,776 (every type its 4); title searches 4,348, 4,000,
  3,608; advice searches 0, 2,431, 1,533. Examples (title + need + advice + warning searches; main, before, after):
  teapot 8+0+0+4, 8+0+8+0, 8+0+4+4; conditioner for curly hair 14+7+0+4, 14+2+0+0, 5+7+0+4; robot vacuum for pet hair
  18+3+0+4, 16+0+0+0, 9+3+0+4; blush 12+0+0+4, 16+0+0+0, 12+0+0+4; makeup primer for large pores 6+6+0+4, 16+0+0+0,
  4+8+0+4. Tests: those three rare non-makeup requests keep main's need and warning searches (teapot its 4 warnings),
  and the blush test now expects 12 title searches and 4 warnings (changed on purpose, dated in the test). The note of 4
  Nov, evening, which said this order was main's, is corrected.
  (2) Makeup primer: a type may now list community names (engine/data/product_types.json, "community_names"): words that
  name it in a thread's title only when the thread is in one of its own communities (engine.sources.title_names; never
  in a post's text, where a bare "primer" is as often an eyeshadow's or a paint's). Makeup primer's are "primer" and
  "primers", so its 6 face-primer threads, whose titles say little more than "primer", are read. "eyeshadow primer" is
  no longer one of its keywords and is a look-alike (with "eye primer"), so the eyeshadow-primer thread 1vs5bqy (its
  mentions typed eyeshadow primer 168, eyeshadow 9, makeup primer 4) is out. "makeup primer for large pores" now reads
  1oxcf8e, 17tudja, 1ux2gcj, 1mm85fo, 1hk56ak and 1txl469 (it read 1ux2gcj and 1vs5bqy) and gives 3 picks instead of 1
  (Hourglass Mineral Veil, 6 credible voices; Danessa Myricks Blurring Balm, 4; NYX marshmallow primer, 3; ELF power
  grip, the one pick before, has its credible recommendations in 1 thread once the eyeshadow-primer thread is out, and a
  pick needs 2), needs_more_threads is false and the "evidence for only one" message is gone. A request for "eyeshadow
  primer" is now a type of its own (the open model's way), not makeup primer.
  (3) Kohl: "kohl" names eyeliner in a title only in eyeliner's communities (a community name), and "Kohl's" (the shop,
  either apostrophe) is a look-alike of eyeliner, so it names none anywhere: 177xg86 and d65x5e (r/BuyItForLife, about
  the shop's clothes) leave the eyeliner answer (10 threads to 8; other types' names left out 128 to 39), and a request
  for sweatpants from Kohl's is about sweatpants, not eyeliner, while "kohl eyeliner" still is eyeliner. Left: "Kohls"
  without an apostrophe in a comment still counts as eyeliner talk (18 comments outside the makeup communities), but a
  thread is never read on its comments alone. pipeline._clear_brand, which reads titles for any type's names, is as it
  was: it only acts for brands in data/brand_lines.json, and no makeup brand is one there.
  (4) Grouping and names (engine/data/product_aliases.json's short names, written out at the start of a name, and
  config.MAKER_SPELLINGS for how a name is shown). The shoppers' reports: "CT" is Charlotte Tilbury; "One size on til
  dawn" is shown ONE/SIZE On 'Til Dawn; "Essence Princess Lash" is Essence Lash Princess; MAC and NARS in capitals;
  Stila's liquid liner names are one product, Stila Stay All Day Liquid Liner (4 credible voices to 15); Maybelline
  Super Stay Skin Tint is apart from the Super Stay foundations (the foundation answer's Also worth a look shows the
  skin tint, 20 voices, where it showed the Super Stay foundation line, 19, mostly the tint's). Not done: the shopper's
  brush-tip NYX pen as Epic Ink, because the three mentions written "Epic Wear pen" sit in replies about Epic Wear, so
  the extraction's words don't make it certain. Found the same way in the 15 answers' ranked products (a writer's short
  brand name beside the written-out one; each short name occurs only in makeup communities in the library): VB (Victoria
  Beckham), T28 (Tower 28), ND and Denona (Natasha Denona), Huda (Huda Beauty), Thrive (Thrive Causemetics), ABH,
  Anastasia BH and Anastasia (Anastasia Beverly Hills), "NYX Epic Ink" alone (NYX Epic Ink Liner; Epic Wear stays
  apart), Got2be (got2b; and, as 'Leap V1' is, "ND filter" and "ND filters" are kept as they are before "ND", since the
  general category holds cameras too), and the spellings NYX, ONE/SIZE, Estée Lauder, L'Oréal, e.l.f., got2b, rom&nd,
  Lancôme and YSL. What moved: setting spray's Charlotte Tilbury is one product (23 credible recommendations and 17
  credible warnings, 20 and 9 under its name before and 3 and 9 under "CT"), ranked tenth, so it leaves Also worth a
  look and the CT skip line goes (shown nowhere: mixed, and that is what its voices say); concealer's picks are Tower 28
  (65 to 71 voices), Natasha Denona (19 to 29, from third to second) and Kosas (35 to 34, from second to third); setting
  powder keeps its three picks, Huda Beauty now first (7 to 12 voices, "Huda" and "Huda Beauty" together; it was third);
  brow gel's third pick is Anastasia Beverly Hills's brow pencils (9 voices) and got2b Glue Spiking Gel goes to Also
  worth a look; mascara's Thrive Causemetics has 30 voices (22); eyeliner shows NYX Epic Ink Liner (21), Stila Stay All
  Day Liquid Liner (15) and Victoria Beckham's eyeliners (20); blush and blush for fair skin show Tower 28's blushes in
  Also worth a look instead of Glossier Cloud Paint. One voice changed through an older rule: a writer who recommends
  Tower 28 in one comment and warns against "T28" in another now contradicts themselves (Noemi's rule, 9 Oct 2026), so
  all their comments are a low voice; one of them was the comment Kosas's summary cited.
  (5) In the 15 makeup answers (sweep of 293 answers): picks 43 to 45, answers with 3 picks 14 to 15, names shown (picks
  and Also worth a look) 86 to 90, quotes under picks 129 to 135; 518 quotes shown, each found word for word in its
  saved comment (checked outside the engine). Names shown without a summary 10 to 22: 8 are newly shown (the 6 primer
  names, two eyeliners), 5 renamed (a summary is kept by its name's words: Maybelline Super Stay Skin Tint, Thrive
  Causemetics, Essence Lash Princess, Anastasia Beverly Hills's brow pencils, e.l.f. brow lift), and 2 dropped by the
  summary check (Stila's now has a credible warning and its summary names no downside; Kosas's cited comment is the low
  voice of (4)). The summaries are to be written in the next summarising batch, with the redo after the full warm.
  Highlighter is the same; bronzer differs only in the names its left-out list holds; lipstick and lip tint only in
  rom&nd's spelling.
  (6) Checks, through the heavy lock: the whole suite 7,006 passed (77 new tests) and 1 failed, the unlabelled gold
  thread 1v40u3t, which fails on main too; eval/run_eval.py identical before and after in every number but module 4's
  count of the library's product groups (34,485 to 34,452, loose 4,760 to 4,752: the short names joining); of the 278
  non-makeup answers every one is identical in picks, Also worth a look, Skip these, message, threads, summaries,
  quotes, reasons and left-out lists, so no non-makeup answer changed. The makeup picks stay provisional until the full
  warm, as in the note of 4 to 5 Nov, (7). The sweeps and the frozen copy of the store hold commenters' words and
  writers' names: the store's copy is deleted, the sweeps go to the Trash with the deletion rule.
- 5 Nov 2026, small hours, the makeup fix round, part 2: what an answer shows (Claude, builder 2; Claude's technical
  calls, reported to Noemi; branch makeup-threads; nothing pushed, merged or deployed). From the shopper review of 4 to
  5 Nov 2026 (shoppers 5, 7, 10 to 15, 17 and 18). Only which quotes, tips and notes an answer shows and how its reason
  line names a need changed: no pick and no pick's order moved ((8)), and no scoring weight, product type, wait number
  or the 48-hour quote rule changed. The need-fit rule Noemi said to measure first ("Yes, measure first (Recommended)")
  stays off, and her other three answers of the night are the next builder's. The engine makes no new call: every rule
  reads the quote's own words and what the extraction already holds. Values in engine/config.py under "Makeup fix round,
  part 2"; tests in engine/tests/test_answer_shows.py (made-up text).
  (1) Quotes for a need (shoppers 7, 13, 15). A quote "talks about a need" as the reason line counts it now: a need of
  two words whose first word alone says something else (config.NEED_PHRASES_WHOLE: dark circles, dark spots, dark marks,
  large and open pores) counts only with its last word, so "I have dark skin" no longer passes for a dark-circles quote
  (engine.answer._fits_a_need). Every other phrase's first word still counts alone ("my lower back" is about back pain):
  read whole, the second sweep counted fewer voices in 47 non-makeup reason lines, most of them rightly counted before
  ("fits in my car" for a car boot, "I sleep on my side"). Within a tier of _naming_first, such a quote still comes
  first. A quote whose comment talks about the need (the extraction's needs) but whose own words don't takes in the
  sentence that does where the comment allows (_with_the_need, _need_stretch): the sentences before it only when the
  comment names no other product, the first of them is the writer's own ("my own dark circles are deep", never "most
  people get this wrong"), none says "it" or "this one" (most often another product) and no line starts between; the
  sentences after it one at a time, never past a question, a new line, a quoted block, a turn ("but", "however"), praise
  of something else ("I like the X", "X is good too": a product the extraction didn't list for that comment), another
  product's name or QUOTE_MAX_WORDS. Those limits came from reading the widened quotes of the first three sweeps. With a
  need asked, a makeup quote about a shade (a named or numbered shade, a match, an undertone, a skin tone) and not the
  need is a filler: it only makes up a pick's minimum (config.QUOTE_SHADE_WORDS; "I own it in three shades" is no shade
  quote). Tried and dropped: a need quote before every other, whatever its tier. In the first sweep it put a quote
  naming the product without a view ("I have the X") before years of praise in many non-makeup answers, and changed only
  one makeup quote.
  (2) Quotes that undercut their own product (shoppers 12, 15, 17, 18). A recommendation's quote that ranks another
  product of its comment above it, tells of leaving it for another, turns to another one ("but I'd rather pick up a
  drugstore one"), is a step of a routine of several products, or praises an old version of it only makes up a pick's
  minimum (so no pick drops for want of quotes) and is an Also worth a look item's quote only when it has no other
  (engine.answer._undercuts; config.QUOTE_FAVOURING_WORDS, QUOTE_LEAVING, QUOTE_GOING_ELSEWHERE, QUOTE_ELSEWHERE_WORDS,
  QUOTE_ROUTINE_STEP, QUOTE_OLD_VERSION). A comparison is read for which product it ranks lower: what comes after its
  "than" or "over" ("Y is better than X" undercuts X; "it is far better than the Y was" doesn't), else the product named
  last before the favouring word ("I like X, but Y is better"), or the first after "prefer" or "nothing beats"; a
  negated one ("no, Y is not better") says neither. Of the 22 quotes the first sweep's rule judged undercut in the
  non-makeup answers, 11 were praise: 9 comparisons read the wrong way round (a rival after "than" or "over", the
  product called "it", a negation) and 2 an "old" that was the writer's own (an old Kindle, an old air fryer); the
  reading above was written from them. So "the old X" counts in makeup answers only (the formula before a change; of an
  air fryer it is most often the writer's long-lived one), and "an old version" or "my old version" never does. The
  other product must be one the extraction found in the same comment. Skip these no longer shows a quote that only makes
  sense with an earlier comment: a warning's quote that still leans on the thread is left out, and the product makes way
  for the next (a pick's downsides keep one, as before).
  (3) Tips ("What to look for", engine.answer._look_for), each a generic rule: a note whose writer hasn't tried what
  they advise (engine.credibility._proof_of_use: "hasn't tried it", "heard about it, not used", "someone else's
  experience") backs no tip (shopper 7; every answer); an Avoid line goes against no Also worth a look item, as it
  already went against no pick (shopper 12, part 1: "pencil eyeliner" against the Urban Decay pencil); in a makeup
  answer an Avoid needs credible warnings from at least 2 writers (config.AVOID_MIN_WRITERS; makeup only, because 19
  tests of the kitchen and skincare rules expect one writer's Avoid); a makeup tip named after another makeup type is
  left out unless it names this one too (shopper 14: bronzer in a blush answer; "bronzer worn as blush" stays), and so
  is one for something not made for the face (shoppers 10 and 11: config.TIP_OFF_LABEL_CATEGORIES, haircare, and
  TIP_OFF_LABEL_WORDS: hairspray, baby powder, hair gel, glues), one backed by a health scare the answer can't check
  (shopper 11: config.TIP_HEALTH_SCARE_WORDS, asbestos and cancer words, read in the note's whole comment) and one of
  the opposite form when the request names cream or liquid (shopper 5: config.TIP_FORM_OPPOSITES, a pressed or powder
  tip in "cream blush"); in every answer, a tip whose label ends on a word like "of" or "for" (cut short when module 4
  named it) is left out (config.KIND_DANGLING_END_WORDS).
  (4) The reason line (shopper 7): a need word named alone is named with the word after it when that word says what it
  describes (config.NEED_LABEL_NOUNS, engine.needs._labels): "about fair skin", "about old dog", "about damaged hair",
  in every answer. Its count is of whole needs for the phrases of (1): "2 of them about dark circles" no longer counts a
  voice saying only "dark". The score's own count of need voices (module 6's breakdown and boost) still counts "dark"
  alone; it is scoring, so it is left for Noemi.
  (5) Product notes: a checked fact shown under a product as "Note: ..." (engine/product_notes.py,
  data/product_notes.json, committed: no Reddit data in it). A note never changes which products are shown or their
  order. NARS's powder blushes (the Orgasm line): reformulated in 2024 (checked on 5 Nov 2026 on musingsofamuse.com,
  alittlebitetc.com and marieclaire.com). Becca Champagne Pop: Becca closed in 2021 and Smashbox took the highlighter
  over as Smashbox x Becca Shimmering Skin Perfector (cosmeticsbusiness.com, musingsofamuse.com), so it is still sold:
  noted, not left out. A product no longer sold is left out by its price check (data/prices.json's "available": false),
  as before; none of these three is. rom&nd's Juicy Lasting tint: no note, because no reliable page gave the date of its
  renewal; its quote praising "the old" one is an undercut quote ((2)).
  (6) got2b Glue Spiking Gel: noted as "A hair styling gel, which some writers use to hold their brows", in the threads'
  own sense (1ft2dmj, 1u2uw74), by its name rather than its product type, so it holds whatever type the next builder
  gives brow gel.
  (7) Not caught without a new extraction (a Gemini call): a preference or a switch said with none of the words above,
  or about a rival the extraction didn't list for that comment (the need widening has the same limit, narrowed by its
  praise words: "I like the X" and "X is good too" are caught, a rival named without praise is not); a reply that leans
  on its parent without a telling word (the extraction's refers_to doesn't reach the quote step); which formula a quote
  describes when no date of a reformulation is known; first-hand use or an off-label use beyond the words listed.
  (8) Measured through the heavy lock on builder 1's frozen copy of the writers' profile store (taken at about 01:30),
  live checks off, 36704fa's code before and this round's after, back to back (the before sweep, run four times in the
  night, gave the same answers each time). Sweep of 293 answers: no answer's picks, their order or its Also worth a look
  changed, and 78 answers show something different. The 15 makeup answers: 13 changed (bronzer and mascara are the
  same). 17 of their 225 quotes under picks and Also worth a look changed (16 for another quote of the same product, 1
  widened to its need sentence), among them the NARS, Tower 28, Victoria Beckham, Kosas and rom&nd quotes undercutting
  their product, the shade quotes of the need answers, and the dark-circles and fair-skin quotes the shoppers missed
  (Natasha Denona, Kosas and Haus Labs). Tips 43 to 41: left out bronzer (twice), hairspray, baby powder, the two talc
  Avoids, "pencil eyeliner", "pot concealer under the eye" and "separate makeup primer" (one writer each); "hydrating"
  now shares its line with rose water; in came other tips of the same answers, among them "Look for: drugstore" in the
  two blush answers and "Look for: mini" in setting powder, kinds module 4 had named before. Notes on 4 answers (NARS in
  blush and blush for fair skin, Becca in highlighter, got2b in brow gel); reason lines in 2 ("about fair skin" three
  times; Haus Labs concealer 4 to 3 voices about dark circles, NARS Radiant Creamy 3 to 2); Skip these in 1 (eyeliner:
  NYX Epic Wear pen eyeliner leaves it, its only warning leaning on an earlier comment). The other 278 answers: 65
  changed. 37 of their 2,978 quotes were widened to their need sentence and 46 changed for another (two items now show
  one quote fewer, the dropped one undercutting them: the Feathered Friends sleeping bag and a Calphalon saucepan). Tips
  changed in 9 answers: the untried-writer rule left out a ceramic kamado grill, condenser microphones (in a shotgun-mic
  answer), an exfoliating glycolic toner and ballistic nylon work boots, and changed the comment behind a car seat tip;
  the Also worth a look rule left out three Avoids (Teflon, balm, electric knife sharpener) that went against an item
  shown. Reason lines in 3 answers ("about old dog", "about damaged hair", and an eye cream answer's dark-circles
  counts, 2 to 1 for two products). Every quote the after sweep shows, 5,587 (5,596 before), was found word for word in
  its saved comment (checked outside the engine). Whole suite: 7,064 passed (58 new tests) and 1 failed, the unlabelled
  gold thread 1v40u3t, which fails on main too. eval/run_eval.py printed the same output before and after (shown quotes
  252 of 252 verified), so eval/metrics.json is unchanged.
  (9) Left, for Noemi or later: the score's need count ((4)); AVOID_MIN_WRITERS is makeup-only ((3)); rom&nd has no note
  until a reliable page dates its renewal; Becca is noted, not left out, as Smashbox still sells it; what (7) can't
  catch; "Look for: mini" and "Look for: drugstore" are terse kinds module 4 named, now shown where the tips above left
  room; the Haus Labs foundation pick for oily skin still shows no oily-skin quote, as its oily-skin quote doesn't name
  the product and quotes naming their product come first (_naming_first's tiers). The sweeps, the frozen store's copy
  and this round's scratch files hold commenters' words and writers' names: they go to the Trash with the deletion rule.
- 5 Nov 2026, early morning, the makeup fix round, part 3: Noemi's four answers of about 00:25 (Claude, builder 3;
  branch makeup-threads; nothing pushed, merged or deployed). Her answers are quoted as she gave them; everything else
  is Claude's technical call, reported to her. No scoring weight but (D), no product type but (A), no rule about no-buy
  communities, no told number, no new call by the engine and the 48-hour quote rule untouched. Values in
  engine/config.py; tests in engine/tests/test_makeup_split.py (made-up text).
  (A) Asked "Lip tint is filed under lipstick and brow gel under brow pencil, so those requests get the wrong products.
  Should I give them their own types?", Noemi: "Split both (Recommended)". Module 1 has two more makeup types
  (engine/data/product_types.json, 401 to 403): "lip tint" (lip tint, lip stain, water tint and their plurals; r/Makeup,
  r/Sephora, r/MakeupAddiction, r/drugstoreMUA, then r/AsianBeauty, as lipstick) and "brow gel" (brow gel, eyebrow gel,
  clear and tinted brow gel, brow glue, soap, wax and mascara; the four makeup communities); lipstick and brow pencil
  lost those words. Both are in config.REFORMULATED_TYPES, the pre-check's and on-demand reading's lists (which take
  module 1's names) and the extraction instructions, now v17: a tint or stain is a "lip tint", a brow gel, soap, wax or
  glue, or a hair gel a writer uses on their brows, a "brow gel" (config.EXTRACT_STILL_CURRENT keeps every older
  extraction current, as v14 did). Claude's calls: a lip stain is a lip tint (shoppers use both words for the same
  sheer, long-wearing products); a tinted lip balm stays a lip balm and a skin tint a foundation. No data file types
  products by line, so the library's mentions were re-typed by command, as the SPF lip balms were on 15 Oct
  (engine/makeup_types.py, `python -m engine.makeup_types retype [--write]`, ids and names only in its output): a
  mention typed lipstick is a lip tint when its name says tint or stain, or names a tints-only line (Benetint, Peripera
  Ink, Tony Moly Shocking Lip, Fenty Poutsicle), and doesn't say lipstick or crayon, or when the writer named the maker
  alone ("Etude") in a thread whose title asks for lip tints; one typed brow pencil is a brow gel when its name names no
  pencil form (pencil, pen, pomade, powder, paste, Brow Wiz, Dipbrow, micro, slim, styler...) and says gel, glue, soap,
  wax, setter, laminator, freeze or mascara, or names a gel's line (Boy Brow, Gimme Brow, Brow Lift, Super Lock, Air
  Brow...), or sits in a thread whose title asks for brow gels (there writers name their gel by the maker, "Benefit",
  "Kosas", or a hair gel, got2b). Each was judged from its name, its thread's title and the extraction's own fields; no
  quote was read. The shared library (backed up to the scratchpad first; each file written whole, then swapped in; only
  "product_type" changed, versions and dates kept): 380 mentions in 17 extraction files (all v15), 158 lipstick to lip
  tint (92 names, among them rom&nd Juicy Lasting Tint, rom&nd Glasting Water Tint, Peripera Ink Mood Glowy Tint,
  Peripera Water Bare Tint, Dinto Blur Glowy tint, Laka Fruity Glam Tint, Etude Fixing Tint, Tony Moly Shocking Lip,
  3CE Blur Water Tint, Milani Color Fetish Hydrating Lip Stain, Benefit Benetint, Fenty Poutsicle) and 222 brow pencil to
  brow gel (105 names, among them Maybelline Super Lock Brow Glue, got2b Glue Spiking Gel, Glossier Boy Brow, Rare
  Beauty eyebrow gel, Benefit brow gel, Ardell Brow Glue, NYX Brow Glue, Refy, e.l.f. Brow Lift, Maybelline Super Fluff,
  Kosas Air Brow, NYX Thick It Stick It, Julep 101 brow sculpting stick and gel). Kept as they were: Kate Lip Monster and
  the other lipsticks, balms and glosses of the lip tint threads, Colourpop's tint lip crayon, Rare Beauty's and Kosas's
  brow pencils, Kevyn Aucoin's brow pen and gel duo, e.l.f.'s eyebrow paste. `engine.extract check` on the library:
  93,773 of 94,276 mentions kept, 503 rejected, all from before (the 17 re-typed files: 1,479 kept, 12 rejected, the same
  as before the change). Effect: "lip tint" (and "lip stain") is answered under "Top picks: lip tint" with rom&nd Juicy
  Lasting Tint, Peripera Ink Mood Glowy Tint and rom&nd Glasting Water Tint (Also worth a look: Tony Moly Shocking Lip,
  Etude Fixing Tint), where it was a lipstick answer led by MAC Ruby Woo; "lipstick" has no tint among its picks or
  items (MAC Ruby Woo, Revlon Super Lustrous lipstick line, Clinique Almost Lipstick Black Honey; it showed rom&nd's and
  Peripera's tints second and third); "brow gel" (and "eyebrow gel") is answered under "Top picks: brow gel" with
  Maybelline Super Lock Brow Glue, Benefit brow gel line and got2b Glue Spiking Gel (Also worth a look: Kosas Air Brow,
  e.l.f. Brow Lift, got2b Glued Brows & Edges), where the Benefit and Anastasia Beverly Hills brow pencil lines were
  picks; "brow pencil" still answers with pencils, Benefit Precisely My Brow, Anastasia Beverly Hills Brow Wiz and NYX
  Lift and Snatch (it had Super Lock Brow Glue first). The kinds the home page counts ("about 350 kinds of product":
  types with 6 or more saved threads, engine.library coverage) are 366 before and 368 after, inside the 330 to 370 that
  keeps "about 350", near its top. Found: lip tint has 3 threads about it, brow gel 5 and brow pencil 3 now (lipstick
  had 14 and brow pencil 8), under on-demand reading's bar of 6, so on the site their first visitor queues an on-demand
  reading, as for any thin type; the answers above already have 3 picks each, so no data round was asked for.
  (D) Asked "Old skincare and haircare comments count as medium voices at most, because formulas change. Should old
  makeup comments work the same way?", Noemi: "Yes, like skincare (Recommended)". A makeup thread is a general one, so
  the cap goes by the request: every comment an answer for one of the 15 makeup types counts (picks, items, warnings,
  care tips) is at most a medium voice when it is more than VOICE_RECENT_YEARS (3) years old
  (engine.credibility.score_voice's `reformulated`, engine.pipeline._reformulated). config.py no longer says the cap is
  skincare and haircare only, and the how-we-score page's "Skincare formulas change, so a skincare comment older than 3
  years is medium at most" (already short of haircare) now reads "Skincare, haircare and makeup formulas change, so a
  comment about any of them older than 3 years is medium at most" (a wording fix with her answer). Effect, measured
  with the cap switched off and on over the same code and library: 11 of the 15 makeup answers change, no other answer;
  the high voices behind the 45 makeup picks fall from 407 to 330. Picks: bronzer's third (Makeup by Mario SoftSculpt
  Skin Enhancer to NARS cream bronzer), setting spray's (Ben Nye Final Seal to ONE/SIZE On 'Til Dawn), brow gel's (Kosas
  Air Brow to got2b Glue Spiking Gel) and lipstick's (Maybelline vinyl liquid lipstick to Clinique Almost Lipstick Black
  Honey), and the order of cream blush's last two (Patrick Ta before Rare Beauty) and setting powder's first two (Huda
  Beauty before Hourglass); Also worth a look in blush and blush for fair skin (Glossier Cloud Paint for Tower 28),
  setting powder (Maybelline Fit Me Loose Powder for Wet n Wild Photo Focus), eyeliner (Urban Decay 24/7 Glide-On for
  Wet n Wild Breakup Proof Skinny-Tip) and mascara (order); concealer for dark circles only in its voices (mascara's
  three picks go from 34 high voices to 9, the same picks). Highlighter, foundation for oily skin, makeup primer for
  large pores and lip tint are as they were.
  (C) Asked about the lipstick answers quoting a care tip from r/MakeupRehab, Noemi: "Remove those 2 threads". 1co3r5i
  and 1jlzpoa (thread and extraction files) moved to data/library/set_aside, the library's place for threads set aside
  (14 Oct 2026); ids only here; no rule about no-buy communities. Measured alone against builder 2's code: the 15 makeup
  answers keep their picks, order and Also worth a look; lipstick and lip tint lose that care tip (1jlzpoa was read by
  the three blush answers too, unchanged); after the round no answer quotes or reads r/MakeupRehab (two quoted it
  before, five read the two threads).
  (B) Asked "The top 'cream blush' pick has no voices about cream. Should a top pick need at least one credible voice
  that fits what was asked (cream, fair skin, oily skin) before it's shown?", Noemi: "Yes, measure first
  (Recommended)". Built and off: config.NEED_FIT_FOR_PICKS = False. On, a product that meets the bar is a pick only when
  at least one of its credible recommendations talks about one of the request's needs in its own words (a form, cream
  or liquid; a skin type or tone; dark circles; curly hair; pet hair; lasting...), read as the reason line reads them (a
  two-word need such as dark circles whole; praise of a feature for another product no fit), and one without heads Also
  worth a look, labelled as meeting the bar, so nothing leaves the answer (engine.pipeline._fits_the_need,
  engine.rank.ProductScore.fits_need). Claude's calls: a thread's title asking for the need is not enough, unlike the
  need rule (her decision (d) of 19 Oct 2026), as her question was about voices: with titles counted, "cream blush"
  would not change at all (its top pick, Milani's line, has one top-level answer in a thread asking for cream blushes and
  no voice saying cream); a need that is a word of the product's name ("cream" of "cream blush") counts though the
  reason line never names it. Measured on, against off, on the full 293 answers (235 with picks): 77 answers change their
  picks (4 of the 15 makeup answers, 73 of the 220 others with picks), 43 their top pick (2 and 41), and 33 go from 3
  picks to fewer (1 and 32), 7 of them to none (all non-makeup: microwave with a grill, air purifier for allergies,
  webcam for video calls, fridge freezer that's quiet, wine cooler, automatic watch, dash cam with parking mode); answers
  with fewer than 3 picks would go from 74 to 107. Makeup: cream blush (Milani blush line and Rare Beauty blush line to
  Also worth a look; Patrick Ta blush line, Glossier Cloud Paint and Haus Labs blush line), blush for fair skin (Milani
  and NARS Orgasm out, Patrick Ta and Haus Labs in), foundation for oily skin (NARS Light Reflecting out, Maybelline
  Super Stay Skin Tint in), makeup primer for large pores (Hourglass Mineral Veil and Danessa Myricks Blurring Balm out,
  2 picks left: NYX Marshmallow primer, Smashbox Photo Finish). With titles counted it would be 50, 29, 26 and 5, and 3
  makeup answers. Before switching it on: 12 of the 77 come from a word of the product's own name where every product
  is that kind already (cordless drill, mechanical keyboard, merino socks, noise cancelling headphones, gaming laptop),
  its fuller readings group some names differently (two picks both named "Boos block" in the cutting board answer), and
  the reason line says nothing about a form, so a cream blush pick shows no sign of its cream voices. Every quote the
  rule's sweep shows was found word for word (5,396).
  Measured through the heavy lock on one frozen copy of the writers' profile store (taken at 04:23 EST, while the warm
  writes the library's), with copies of the library before and after, live checks off, builder 2's code (24bbc31)
  before and this round's after, back to back (repeated sweeps gave the same answers). Sweep of 293 answers: the 278
  non-makeup answers are unchanged in every part; of the 15 makeup answers 13 changed (12 in what they show, concealer
  for dark circles in its voices only), 7 of them in their picks or order (cream blush, bronzer, setting powder, setting
  spray, brow gel, lipstick, lip tint). Every quote the after sweep shows, 5,586, was found word for word in its saved
  comment (checked outside the engine). eval/run_eval.py: every number as before but two of the library's: its quote
  count, 93,784 of 94,291 to 93,773 of 94,276 (the two set-aside threads' 15 mentions, 11 found), and module 4's product
  groups, 34,452 to 34,441 (loose 4,752 to 4,750); eval/metrics.json holds only the first, so it changes only there.
  (Corrected in part 4, the same morning, after the rules review: this sentence first named the quote count alone.) Whole suite: 7,146 passed and 1 failed (the unlabelled gold thread 1v40u3t, which fails on main too); the
  tests changed on purpose say so in place (test_makeup_coverage: lip tint and brow gel are their own types; test_extract:
  the instructions are v17; test_web: the warm taxonomy has 403 types).
  Left, for Noemi or later: the need-fit rule's switch and the points above it; "got2b Glued Brows 38 Edges hair gel" is
  how one extraction names got2b's Glued Brows & Edges (a shop link's spelling), shown in brow gel's Also worth a look:
  a name fix in that extraction or an alias; main's product types still have r/MakeupRehab for some makeup types
  until this branch is merged, and on-demand reading's skip list doesn't read the set_aside folder, so a later reading
  of r/MakeupRehab could bring the two threads back (bulk import does read it). The scratch sweeps, the library copies
  and the frozen store's copy hold commenters' words and writers' names: they go to the Trash with the deletion rule.
- 5 Nov 2026, morning, the makeup fix round, part 4: the fixer (Claude; Claude's technical calls, reported to Noemi;
  branch makeup-threads; nothing pushed, merged or deployed). From the rules review and the shopper review of part 3.
  Noemi's one answer acted on here is quoted as she gave it; everything else is Claude's call. Inside her bounds: no
  scoring weight but (D), no product type but (A), the need-fit rule left off, no rule about no-buy communities, no told
  number, no new call by the engine (every rule reads a quote's own words and what the extraction already holds) and
  the 48-hour quote rule untouched. Values at the end of engine/config.py ("Makeup fix round, part 4"); tests in
  engine/tests/test_makeup_fixes.py (made-up text).
  (1) The two removed threads. Noemi, part 3 (C): "Remove those 2 threads". Their thread and extraction files left
  data/library/set_aside for the Trash (~/.Trash/credible-recs-deletion-rule-2026-11-05-removed-threads; Noemi empties
  it), and their ids, 1co3r5i and 1jlzpoa, are kept in config.REMOVED_THREADS, a list nothing reads a thread from: it
  is in the library's never-read set (engine.library.not_to_read), bulk import's (engine.bulk_import.imported_before)
  and on-demand reading's skip list (engine.on_demand), so no later reading brings them back (part 3 found on-demand
  reading missed the set_aside folder; corrected in fix 2 after the warm, from the rules review: "nothing" overstated
  it, as `python -m engine.bright_data fetch` into the library didn't check the list until fix 2, and the on-demand
  job's extraction step and forget_baked still don't). The library's request log still lists the two ids under the
  on-demand reading that brought them in: a record of what happened, ids only.
  (2) Quotes that undercut their product only make up a pick's minimum (engine.answer._undercuts, as in part 2), now
  also: a rival named by its line alone, without its brand (_names_by_its_line: "but True Match suits me better" in a
  Milani blush quote; a line read accents aside, as "L'Oréal" had split in two, and of one word only when it has 4
  letters or more); a quote saying its product was reformulated and is worse or was the writer's (QUOTE_REFORMULATED
  with QUOTE_WORSE_SINCE: Double Wear's); one ranking it second in a clause naming it and no other (QUOTE_SECOND_PLACE:
  Brow Wiz's); and one whose writer, after naming it, means to try others (QUOTE_TRYING_OTHERS, found in this round's
  own sweep: a brow gel line's quote; others "from" its own maker are more of the same).
  (3) A writer who says, in the quote, that they work or worked for the product's maker (QUOTE_WORKED_FOR, the maker's
  name right after it, "the" or "a" aside) is never quoted, not even to make up the minimum: a Clinique lipstick
  quote. Working "at a department store" or "from home" ties a writer to no maker, nor does "the gym where I work
  stocks X" (the round's own first sweep had dropped a yoga mat quote so, with the maker anywhere in the next 3
  words). Whether the voice counts is module 5's, as before.
  (4) No longer made (QUOTE_NO_LONGER_MADE: "discontinued", "taken out of production", "no longer sold"). A pick's
  quote saying so only makes up the minimum; an "Also worth a look" item never shows one, and an item that
  NO_LONGER_MADE_VOICES (2) of its credible recommendations, from different comments, say is no longer made is left
  out (_said_to_be_gone): in makeup primer for large pores the Estée Lauder primer, two of whose three voices said it
  was discontinued, gives its place to The Ordinary High-Adherence Silicone Primer. A quote naming another product too
  ("X was discontinued, so I switched to Y") is about that one and stays, and so is one naming its product only after
  saying so ("after my old one was discontinued I switched to X"; the first sweep had taken a benzoyl peroxide gel's
  quote so).
  (5) A need given to another product (config.NEED_ELSEWHERE: "a separate" or "a different" thing, "something else",
  in a clause of the quote's sentence that talks about the need and doesn't name the product; _given_away). That voice
  isn't counted "about" the need in the reason line, and its quote never takes in a sentence for it: NYX Marshmellow
  primer's reason loses "1 of them about large pores", and its quote no longer runs on into its writer's "separate
  primer" for pores. Module 6's count of need voices, a score, is as it was. The first version also read "the other",
  "my second" and "another": the first full sweep showed it took a need voice from 12 reason lines in 9 non-makeup
  answers, all wrongly ("less greasy than the other brands", "on my second bottle", "another puppy coming"), so those
  words are out.
  (6) Quote order. A quote ending on a question comes after a clearer quote of its tier (_ends_asking; a question in
  brackets at the end is an aside: "fairly cheap (about $40?)"). A pick with a need asked, none of whose chosen quotes
  talks about it, shows one that does in the last place (_with_a_need_quote): foundation for oily skin's Haus Labs
  pick drops a hedging quote for an oily-skin one. That quote says something about the product, names no other product
  of its comment, comes from a writer the extraction read as talking about the need, and talks about it outright, in
  its own sense (_said_outright: "feeding six? buy the larger size" is not for a family, "a few years back" is no
  back pain, "dry days" no dry skin); and a need that is a word of the product's own name ("mechanical" of "mechanical
  keyboard", which the reason line never names either) asks for none. Without those conditions the first full sweep
  had shown a grinder quote whose writer mostly uses another grinder and a rice cooker quote saying a big family
  should buy a bigger one, and the second an office chair's "a few years back" for back pain.
  (7) Tips. A writer who hasn't tried it backs no tip whatever the apostrophe (a curly one slipped through: blush's
  purple blush tip now quotes a writer who has; only the apostrophes are straightened, since reading the words in small
  letters also made a writer's tale of their own smart appliance, told through their spouse, someone else's experience
  in the first sweep); a tip that is the type asked for itself is none (_one_of_the_types_names with
  config.TYPE_PLACE_WORDS: "Avoid: face primer" in a makeup primer answer); a one-word makeup tip naming another makeup
  type is none ("Look for: spray" in lip tint and lip stain; highlighter's tip for a balm highlighter, against glitter,
  loses "or stick").
  (8) Names. got2b's Glued Brows & Edges, which one extraction spells as a shop link does ("Glued Brows 38 Edges hair
  gel"), has two aliases (engine/data/product_aliases.json) and joins its own group, "got2b Glued Brow & Edge Gel", so a
  plain got2b hair gel no longer joins it and its complaint is no longer shown as a recommendation; with its voices its
  own, it has too few for brow gel's "Also worth a look", where the Anastasia Beverly Hills brow gel line takes its
  place. Makers' capitals (config.MAKER_SPELLINGS): NARS Radiant Creamy, Anastasia Beverly Hills Brow Wiz, e.l.f. Brow
  Lift, Dior Forever, and NYX's own "Marshmellow". Three expectations of engine/tests/test_makeup_names.py changed on
  purpose for them, dated in place.
  (9) From the rules review: part 3's measurement sentence above and its eval/RUNS.md row now say that module 4's
  product groups moved too, 34,452 to 34,441 (loose 4,752 to 4,750), where they had named the quote count alone.
  Measured through the heavy lock on one frozen copy of the writers' profile store (taken at 06:24 EST, while the warm
  writes the library's), live checks off, part 3's code (e079eee) before and this round's after, back to back (the
  before sweep run twice gave the same answers). Sweep of 296 requests (the 293 of part 3 and brow pencil, lip stain
  and eyebrow gel): no pick, no pick's order and no "Also worth a look" or "Skip these" item moved in any non-makeup
  answer; 19 of the 278 non-makeup answers show another quote for one or two picks, every one the need quote of (6): a
  pick whose quotes said nothing of the need asked now ends on one that does (a KitchenAid dishwasher said to be
  quiet, Red Wing boots resoled, a Miele for pet hair, a Biore sunscreen leaving no white cast), in place of its last
  quote. Of the 15 makeup answers 10 changed what they show and 5 are as they were (bronzer, setting powder, setting
  spray, mascara, eyeliner), and brow pencil, lip stain and eyebrow gel changed too; no makeup pick or pick's order
  moved (two picks only took their makers' capitals), and three "Also worth a look" items changed (makeup primer for
  large pores, brow gel, eyebrow gel). Every quote the after sweep shows, 8,072 (all quotes in the answers' data:
  picks, items, warnings, tips), was found word for word in its saved comment (checked outside the engine), 592 of
  them in the 18 makeup answers. eval/run_eval.py, run on the same copy before and after: every number as before but
  module 4's product groups, 34,441 to 34,442 (the got2b alias: the plain got2b hair gel is a group of its own again),
  so eval/metrics.json doesn't change. Whole suite: 7,196 passed and 1 failed (the unlabelled gold thread 1v40u3t,
  which fails on main too): part 3's 7,146 and this round's 50.
  The rules review's other points, not fixed here: the commit metadata of older commits on this branch (b83ab95 and
  15835d6 signed by a Sonnet line; 1429829 and 15835d6 dated -0500) needs a rebase, the orchestrator's; lip tint (3
  threads), brow gel (5) and brow pencil (3) are under on-demand reading's bar of 6 (a data round or Noemi); 32 of the
  79 products the makeup answers show have no summary, Urban Decay's among them, until the summarising batch after the
  warm; the product notes for NARS Orgasm, Becca and got2b (data/product_notes.json) are user-facing and wait for
  Noemi's yes; "eyeshadow primer" is a look-alike or open-model type now, so (D)'s cap doesn't reach it; the picks'
  order moves with the profile copy, so these numbers hold for one frozen copy until the warm ends; main's engine
  can't read the r/Makeup, r/Sephora and r/AsianBeauty threads, so this branch is merged before any deploy. The
  scratch folders of parts 3 and 4 (sweeps, library and profile copies) hold commenters' words and writers' names:
  they go to the Trash with the deletion rule by about 7 Nov.
- 5 Nov 2026, evening, the warm finished, the summaries written, the makeup picks settled (Claude, the integrator;
  Claude's technical calls, reported to Noemi; branch makeup-threads; nothing pushed, merged or deployed). No code,
  config, product note or told number changed in this round: it is data (the writers' profiles and the summaries) and
  the checks of both. Inside Noemi's bounds: no scoring weight, picks bar or product type touched, the need-fit rule
  still off (config.NEED_FIT_FOR_PICKS = False), the product notes (data/product_notes.json: NARS's reformulation,
  Becca, got2b's hair gel) still waiting for her yes and unchanged, the told wait (about 25 minutes), 30 a day, 39 a
  month and the 15 calls a request the same as main's, and the 48-hour quote rule untouched.
  (1) The warm. The full profile warm of the writers' Reddit histories finished at 18:18 EST after 44 chunks. The store
  went from 54,361 writers to 58,665 (4,310 added: 4,063 with stats, 247 unknown to the archive; 74,005 flairs to
  79,486). Nobody lost their stats and no older entry was looked up again (their 30 days run out from 24 Nov). Six
  writers are gone, with nine flairs, on purpose: they only appear in the two removed threads, 1co3r5i and 1jlzpoa.
  Every writer with a kept mention now has a stored profile; 1,798 (3.1%) are unknown to the archive and count as
  having none. 42 look-ups failed over 14 of the chunks (Arctic Shift 502s, timeouts, resets); a failed look-up is not
  stored, so the next chunk asked again, and the last chunk had none. One batch of 32 comments' flairs was not fetched
  (a 502): 1,021 of the library's 80,507 kept comments have no stored flair, and none of them had one before the warm
  either (corrected in fix 1 the same night, from the rules review: this note first said 893 of them had none).
  The store's sha was the same before and after each sweep below (d78c2535f930cc8fd6491c203c9156e8721c7f12).
  (2) The makeup picks, settled. Part 4's picks were measured on a frozen copy of the profiles (06:24 EST) and called
  provisional. On the finished warm 7 of the 15 makeup requests moved their picks or their order and 8 did not. No code
  moved them: the profiles did (scores rose for nearly every pick, as high voices arrived). Pick sets changed in four:
  bronzer (the Hourglass bronzer line, 5.025 to 6.575, takes third from NARS cream bronzer, 5.8 to 6.175, now under
  Also worth a look); foundation for oily skin (Maybelline Super Stay Skin Tint, 7.65 to 10.625, takes third from NARS
  Light Reflecting, 8.125 to 10.375, now under Also worth a look); makeup primer for large pores (Hourglass Mineral
  Veil stays first, Maybelline's grippy primer serum, 1.325 to 1.85, comes in second and NYX Marshmellow, 1.5 to 1.8,
  third; Danessa Myricks Blurring Balm drops to Also worth a look); brow gel (got2b Glue Spiking Gel, 1.775 to 2.025,
  takes third from Kosas Air Brow, 1.85, now under Also worth a look). Same three picks in another order in three:
  concealer for dark circles (Tower 28, Kosas, Natasha Denona), setting spray (Urban Decay All Nighter, ONE/SIZE,
  Milani Make It Last) and lip tint (rom&nd Juicy Lasting Tint, rom&nd Glasting Water Tint, Peripera Ink Mood Glowy
  Tint). Picks and their order unchanged: blush, blush for fair skin, cream blush, highlighter, setting powder,
  mascara, eyeliner, lipstick; lip stain gives lip tint's answer and eyebrow gel brow gel's. Their "Also worth a look"
  items did change in five of those eight (corrected in fix 1 the same night, from the rules review: this note first
  called the eight unchanged): highlighter (Essence Pure Nude in, Becca Champagne Pop out), mascara (YSL lash clash in,
  Clio Kill Lash out), eyeliner (the Stila gel eyeliner and the Urban Decay eyeliner line in, Urban Decay 24/7 Glide-On
  and Too Faced Better Than Sex out), lipstick (Maybelline vinyl liquid lipstick and Lisa Eldridge velvets in, the
  Charlotte Tilbury and YSL lipstick lines out) and setting powder (another order); and beside their pick changes,
  bronzer's (Marc Jacobs in, Physicians Formula out) and makeup primer for large pores' (Smashbox's mattifying primer
  in, Caliray out). All 17 makeup answers (the 15, lip stain and eyebrow gel)
  give 3 picks, from 3 threads (lip tint, lip stain) to 12 (blush, blush for fair skin, cream blush, foundation
  for oily skin, concealer for dark circles, lipstick). The 278 non-makeup answers are unchanged by the warm: every
  pick, score, order, Also worth a look name, Skip name and message equals main's, the 10 blind-test answers
  included (same picks, same scores). They differ from main only where the fix rounds meant them to: other quotes for
  69 picks in 58 answers and Also worth a look items in 21, 9 tip lists and reason lines in 3 answers.
  (3) The summaries (one-line "In short", engine/prompts/summarise_pick.md, summarise-v1). The summarising batch was
  only the makeup products and the first skincare ones of the todo: 48 products, in four chunks of 12 (37 makeup
  products, Urban Decay first, and 11 skincare ones), written by four writers (45 entries) and merged by the
  integrator into data/library/summaries.json (backup of the 882 entries from before: summaries-before.json in the
  scratch folder), atomically. The calls:
  (a) Urban Decay All Nighter's summary is rewritten (it replaced the saved one under the same key) and says nothing
  of a newer formula, as no cited comment does. The Tower 28, Kosas, Givenchy, Stila liquid liner, got2b, rom&nd and
  Peripera entries replaced older ones too, as did three skincare ones, Beauty of Joseon's eye serum, CeraVe's
  retinol serum and Eucerin's Sun Gel-Creme (the todo had listed each older one as failing in some answer; corrected
  in fix 2 after the warm, from the rules review: this note said six, counting the three dropped in (c)). Of the 41
  entries kept, 30 are new and 11 replaced an older one (corrected in fix 1 the same night: this note first said 14
  replaced one, counting the three dropped in (c)).
  (b) ROC retinol's entry is dropped (rule 7): its two citable comments say little beyond that it is good. Three
  skincare products got no entry from their writer, as none of their credible comments is in every answer that shows
  them: Beauty of Joseon Relief Sun (rice and niacinamide), Medik8 Crystal Retinal and Eucerin Aquaphor. Smashbox's
  entry now says "apparently" of the eighth tube, as its writer was hedging. Benefit Roller Lash's reformulation
  suspicion and The Ordinary primer's "discontinued" stay in their sentences as what commenters say, said as theirs.
  (c) `python -m engine.summaries check` (912 entries, 1,109 requests answered, 509 s) rejected 2 of this round's 44
  entries in some answers, both skincare: Biore UV Aqua Rich and ILLIYOON Ceramide Ato. Their writer had cited only
  comments that are credible in every answer of the sweep; the check reads more answers than the sweep, wider readings
  among them (7 answers show Biore and 13 ILLIYOON in all; corrected in fix 1 the same night: this note first called
  all of them wider), and across those answers none of the product's credible comments is in every one (0 of 26 for
  Biore, 0 of 25 for ILLIYOON),
  so no rewrite can pass. Beauty of Joseon Relief Sun Aqua-Fresh's new entry passed but rested on one warning, the
  only comment credible in every answer (1 of 10), so it read worse than the pick's backing. All three new entries
  are dropped and the saved ones of before the round are back as they were: the same state as at the start for those
  three, with the same known failures (the check still lists them). Effect: no non-makeup answer lost a summary it
  had, and 6 shown items gained one (Eucerin Sun Gel-Creme, Nivea Sun Super Water Gel, Beauty of Joseon's eye serum,
  CeraVe's retinol serum).
  (d) What the check says now: 912 entries, 663 fine, 249 with problems: 246 older entries (a cited comment no longer
  readable in the library, or not credible in some answer) and the 3 restored ones, none from this round. All 41
  entries of this round that stay (37 makeup, 4 skincare) pass. The engine never shows a summary in an answer where it
  fails, so the 249 only cost the answers where they fail.
  (e) Effect on what the answers show. In the 15 makeup requests plus lip stain and eyebrow gel (17 answers, 79
  makeup products, 100 shown items: 51 picks and 49 Also worth a look items), shown items without a summary went from
  44 (36 products) to 0: every shown makeup product has a summary, and so has every pick. Non-makeup: shown items
  with a summary 624 to 630 of 1,212, picks with one 362 to 365 of 639. The summaries' cited quotes are quotes like
  the others: all verified.
  Measured through the heavy lock on the live profile store (sha above, unchanged by any run), live checks off. Sweep of
  295 answers (the 293 of the earlier sweeps and lip stain and eyebrow gel), no error: every quote shown, 8,238 (picks,
  Also worth a look items, warnings, tips and the summaries' cited quotes), was found word for word in its saved
  comment, checked outside the engine, 740 of them in the 17 makeup answers (r/Makeup 216, r/Sephora 300,
  r/MakeupAddiction 100, r/drugstoreMUA 85, r/AsianBeauty 39; none from r/MakeupRehab, the no-buy community), 663 in
  the 15 makeup requests alone (corrected in fix 1 the same night, from the rules review: this note first gave the
  15's count and communities for the 17). Brand
  accounts: for the 100 makeup items shown (79 products), all 1,345 credible voices behind them were run through
  module 5's own signs again: none works for, owns or links a brand, and one (a Thrive Causemetics mascara voice,
  medium, not shown) carries "salesy language", on an ordinary shopper's comment. eval/run_eval.py (the warm profiles,
  live checks off): every scored number as in part 4's row; the quotes the blind-test answers show, 252 to 257 (all
  verified), and threads waiting for a live check, 42 to 56 (the day passing), the only changes, and eval/metrics.json
  holds just these two (its date kept as 5 Nov, Noemi's day; the run ended after midnight UTC). The ingredient and
  needs sections print a few other picks than part 4's run (shampoo, vitamin C, spot treatment): the warm moved them,
  not this branch's code (those requests are in the sweep, where their picks equal main's). (Corrected in fix 2 after
  the warm, from the rules review: not the warm but the day judged moved them, as it moved the two counts. This run
  set TZ=UTC and so judged 6 Nov, and eval/metrics.json holds 6 Nov's two counts under a 5 Nov date.) Whole suite:
  7,196 passed and 1 failed (the unlabelled gold thread 1v40u3t, which fails on main too).
  Left, for Noemi or later: 393 products of the todo are still without a summary (none makeup: 144 general, 120
  kitchen, 94 skincare, 35 haircare), and 246 older entries fail in some answer: the next summarising batches. A
  summary must now be credible in every answer that shows its product, and for a product shown in many wider answers
  that can leave no comment to cite (Biore UV Aqua Rich, ILLIYOON): a follow-up to judge a summary only in the answers
  that show it (code, not done here). The product notes wait for her yes. The scratch files of this round (sweeps,
  the todo and its chunks, the profile copy) hold commenters' words and writers' names and go to the Trash with the
  deletion rule.
- 5 Nov 2026, night, fix 1 after the warm (Claude, the fixer; Claude's technical calls, reported to Noemi; branch
  makeup-threads; nothing pushed, merged or deployed). From the rules review, the shopper review and the summary
  fact-check of the settled makeup answers (fa6ee08). Inside Noemi's bounds: no scoring weight, picks bar, product type,
  told number (about 25 minutes, 30 a day, 39 a month) or the 48-hour quote rule touched; the need-fit rule still off
  (config.NEED_FIT_FOR_PICKS = False); the product notes (data/product_notes.json: NARS's reformulation, Becca, got2b's
  hair gel) still waiting for her yes and unchanged. The changes have their tests
  (engine/tests/test_makeup_after_warm.py, 31 on made-up text: 21 fail on fa6ee08's code, and 10 guard what stays as it
  was; corrected in fix 2 after the warm, from the rules review: 9 guard it, and the tenth, the tinted moisturiser tip
  for foundation, was meant to show the change but passed on fa6ee08's code too, as it asked "foundation" without the
  oily-skin need; fix 2 asks "foundation for oily skin" with its need, and it now fails on fa6ee08's code).
  (1) Tips (engine/answer.py _not_for_this_makeup, _names_this_makeup; config.TIP_OTHER_CATEGORIES and
  TIP_OTHER_CATEGORY_WORDS). In a makeup answer a tip whose name names nothing of the type asked for, by one of module
  1's names for it or the last word of the type's name, is left out: a tool ("eyelash curler" for mascara), another
  product in its place ("lip oils" for lipstick, "skin prep" for a primer) and terse labels ("drugstore", "mini"). And a
  "Look for" whose name, before its purpose word, names another category's product and not the type is left out as
  offered in the type's place ("sunscreen as a primer", "spf as a primer", "moisturizer", "tinted moisturizer for oily
  skin" for foundation). Part 4's test that kept "drugstore" in a lip tint answer (corrected in fix 2 after the warm,
  from the rules review: this note said blush) now says the opposite, on purpose (dated comment in
  engine/tests/test_makeup_fixes.py). Not done: "twist-up lip liners" stays under lipstick, as module 1 files
  lip liner under lipstick (a product type, Noemi's).
  (2) An "Avoid" against a shown item's products (engine/answer.py _lines_products, _line_brand). The products ranked
  under an "Also worth a look" line now count with the picks' (the rule of 18 Oct 2026 looked at the picks only), and in
  a makeup answer a line grouped under its brand and the type's name ("Urban Decay eyeliner line", key "urban decay
  eyeliner") holds the brand's products of the type grouped under the brand alone (corrected in fix 2 after the warm,
  from the rules review: the code, _line_brand, reads any makeup key ending in the type's last word so, single products
  too: "Caliray primer" gives the brand "caliray" and "rom&nd Juicy Lasting Tint" gives "rom nd juicy lasting"; no
  answer moves by it today). "Avoid: pencil eyeliner" goes: the
  Victoria Beckham pick's kohl and kajal pencils and the Urban Decay line's waterline pencils went against it. Outside
  makeup one answer moved the same way: the long-lasting kettle's "Avoid: variable temperature kettle", as all three
  lines under its "Also worth a look" (OXO, Sage, Bonavita) hold variable temperature kettles.
  (3) Quotes (config.QUOTE_SOMEONE_SAID in engine/answer.py _ELSEWHERE; config.QUOTE_LEAVING with "started buying", the
  reason after "because" cut off, in _undercuts). A quote saying it answers what someone else said ("someone said",
  "somebody else mentioned", "as others have said") leans on a comment the reader can't see, so it comes after a clearer
  quote: NARS Orgasm's pick quote of that kind is replaced in the two blush answers that show it, and outside makeup
  three other picks swap one for another quote (the webcam's Logitech C920, the two mechanical keyboard answers' IBM
  Model M, the pimple patches' COSRX line). A first version also caught "others" meaning other products (the yoga mat
  answers lost a plain quote in the probe sweep): "others" counts only after "as", "like" or "what". A quote telling of
  starting to buy another product instead undercuts its own: ONE/SIZE's setting spray quote of that kind no longer
  leads.
  (4) Names (engine/data/product_aliases.json, engine/match_products.py). "Stila Waterproof Stay All Day" and "Stila
  Stay All Day Waterproof" are its Stay All Day Liquid Liner (they had made a gel liner group praised for the liquid
  one); the gel liner's long written name is "Stila gel eyeliner"; "Smashbox’s mattifying/Photo Finish primer" is shown
  as "Smashbox mattifying primer" (a name written exactly as a listed short name is now written out even when it already
  holds the full name's words, unless only its spacing differs, as "Leap Frog" does). Effects: the Stila liquid liner
  gains four mentions, three credible (15 to 18 credible voices, score 5.9875 to 7.7875), and moves from third to second
  eyeliner pick, above the Victoria Beckham line (the same three picks); the Stila gel liner, now three mentions from
  one thread, leaves "Also worth a look" and Natasha Denona's Macro Liquid Eyeliner comes in. Four older entries of the
  list were already spelling fixes and now also apply to a name written exactly so (Kenmoore, Kevyn Murphy, Giovanni's
  "triple threat", ONE/SIZE's "till"): one answer's key moved (the quiet fridge freezer's Kenmore line, its shown name
  the same).
  (5) The price list (data/prices.json): The Ordinary High-Adherence Silicone Primer is checked as no longer sold (5 Nov
  2026: John Lewis, Well.ca and Lyko list it as discontinued or no longer available), so it leaves the large-pores
  primer answer's "Also worth a look", the existing route for a product no longer made; the Caliray primer, still sold
  (a web check), comes back in its place.
  (6) Noemi's "Remove those 2 threads", the bundle's own paths (engine/on_demand.py): write_threads (so the site's
  load_threads too) and Noemi's pull never write 1co3r5i or 1jlzpoa into a library, and on-demand reading never reads
  one again because it was in the bundle under the same request.
  (7) The summaries (data/library/summaries.json, backed up before each write, written atomically; git-ignored). 3
  dropped: Smashbox's old entry (it gave another brand's praise and complaints), the Stila gel liner's (the liquid
  liner's praise) and Eucerin's Sun Gel-Creme (no comment credible in every answer gives a downside, and the one shown
  says the opposite of its text). 3 new: Smashbox mattifying primer, Caliray primer, Natasha Denona Macro Liquid
  Eyeliner. 17 rewritten: Givenchy's setting powder (it said the powder suits dry under eyes, which a warning shown
  under it denies; the first rewrite cited a comment that isn't one of its credible mentions in the setting powder
  answer, so the probe sweep showed none, and the second cites four that are), Marc Jacobs's bronzer (it now says its
  writers mourn the original as gone), NARS Orgasm (one repeat buyer saw no change in the formula, another praises only
  the original), The Ordinary's primer (without the comment calling it discontinued), counts one writer can't carry
  ("some", "several", "users" for one: Stila's liquid liner, now citing a second long-term user, Urban Decay's eyeliner
  line, Maybelline's vinyl liquid lipstick, MAC Fix+ Stay Over, Beauty of Joseon's eye serum, and four more read the
  same way: Double Wear, whose matte skin was one writer's and in the past, Gucci's bronzer, NARS Radiant Creamy and
  Glossier Cloud Paint, now without the comment the shopper review found praising it only as a topper), YSL lash clash's
  flaking as a writer put it, Essence Pure Nude's grammar, and two that kept runs of a writer's own words (Danessa
  Myricks, Peripera). Every entry passes engine.summaries' own text and number checks, has no five-word run of a cited
  comment's words and cites only comments credible in every answer that shows its product (corrected in fix 2 after
  the warm, from the summary fact-check: Benefit Roller Lash's rewrite kept one five-word run of a writer's words,
  which this round's scan missed, and seven entries still gave one writer's view to several people; fix 2 rewrites
  them).
  (8) The integrator's note above (5 Nov, evening) is corrected in five places, each marked: the flairs, the "Also worth
  a look" changes the warm made, the count of replaced summaries, the answers showing Biore and ILLIYOON, and the makeup
  quotes by community.
  Measured through the heavy lock on the live profile store (sha d78c2535f930, the same before and after every run),
  live checks off. Sweep of 295 answers (eval/sweep.py's requests, the interviewee, demo and makeup lists, lip tint, lip
  stain, brow gel and eyebrow gel), no error, against the integrator's: picks or their order moved in one answer
  (eyeliner: Stila and Victoria Beckham swap second and third), "Also worth a look" in two (eyeliner, makeup primer for
  large pores), tips in 14 (13 makeup and the kettle), pick quotes in 8 (4 makeup, 4 not), summaries in 21 (15 makeup;
  outside makeup Beauty of Joseon's eye serum reworded in four retinol answers and Eucerin's dropped in two sunscreen
  answers). No other non-makeup answer differs in anything; no Skip item moved anywhere. All 17 makeup answers give 3
  picks, and all 100 shown makeup items have a summary (0 without, as before). Non-makeup shown items with a summary 630
  to 628 of 1,212 (Eucerin's). Every quote shown, 8,223, was found word for word in its saved comment, checked outside
  the engine; 730 in the 17 makeup answers (r/Makeup 213, r/Sephora 306, r/MakeupAddiction 94, r/drugstoreMUA 80,
  r/AsianBeauty 37; none from r/MakeupRehab). `python -m engine.summaries check`: 912 entries, 663 fine, 249 with
  problems, the same 249 entries as the integrator's check (older entries and the 3 restored ones); none makeup, none
  written since 5 Nov. Whole suite: 7,227 passed and 1 failed (the unlabelled gold thread 1v40u3t, which fails on main
  too). eval/run_eval.py on a copy of the store, live checks off: every scored number as in the integrator's row but
  module 4's product groups, 34,442 to 34,441 (4,750 to 4,749 loose: the Stila and Smashbox names joining their
  products). The blind-test answers' quotes shown, 257 to 252 (all verified), and threads waiting for a live check, 56
  to 42, moved too, but fa6ee08's own code gives the same 252 and 42 on the same copy minutes later, so they follow the
  live-check cache's state, not this round; so do the ingredient and needs sections, which print part 4's picks again
  with either code (the integrator's note put their change down to the warm). eval/metrics.json holds the two counts.
  (Corrected in fix 2 after the warm, from the rules review: not the cache's state but the day the evaluation judges
  by. pipeline._today() is date.today(), which sets the 14-day live-check window; the integrator's runs set TZ=UTC and
  judged 6 Nov, this round's ran at 23:51 EST without it and judged 5 Nov, as did fa6ee08's run minutes later. Judged
  on 6 Nov the same code gives 257 and 56 and the integrator's ingredient and needs picks. The fix 1 row of
  eval/RUNS.md is corrected the same way; 2183482's commit message gives the same wrong cause and stays as it is, as
  correcting it would need a rebase.)
  Left for Noemi: whether Marc Jacobs's bronzer should stay under "Also worth a look" (its voices praise the original,
  no longer made; the brand relaunched in 2026 with another bronzer); NARS Orgasm as a blush pick beside "Skip: NARS
  Orgasm (new formula)" and got2b's hair gel as a brow gel pick (the product notes); the need-fit rule; lip tint and
  brow gel's thin threads. Later, code: the summaries check doesn't see warnings folded in from a line or brand
  (Givenchy's case; done by hand here: judging them would hide 11 shown summaries of 7 products today, so not in this
  round), and a "but" or "though" passes it however small the downside. The scratch files of this round hold commenters'
  words and go to the Trash with the deletion rule.
- 5 Nov 2026, night, into 6 Nov (past midnight EST), fix 2 after the warm (Claude, the fixer; Claude's technical calls,
  reported to Noemi; branch makeup-threads; nothing pushed, merged or deployed). From the second rules review, the
  shopper review and the summary fact-check of fix 1 (2183482). Inside Noemi's bounds: no scoring weight, picks bar,
  product type, told number (about 25 minutes, 30 a day, 39 a month) or the 48-hour quote rule touched; the need-fit
  rule still off (config.NEED_FIT_FOR_PICKS = False); the product notes (data/product_notes.json: NARS's
  reformulation, Becca, got2b's hair gel) unchanged, waiting for her yes. Values at the end of engine/config.py ("fix
  2"); tests in engine/tests/test_makeup_fix2.py (23 on made-up text: 11 fail on 2183482's code, 10 guard what stays
  and 2 cover fix 1's on-demand lines, which had none, each failing when its line is undone), and one case of
  engine/tests/test_makeup_after_warm.py changed on purpose with a dated comment (fix 1's note above says why).
  (1) Tips (engine/answer.py _look_for, _talks_about_a_need). In a makeup answer with a need asked, a "Look for" whose
  own name doesn't talk about the need stands only on the notes whose quote or comment does, read as the reason line
  reads needs; with none it is no tip. "Look for: cream foundation stick", from a thread about favourite foundations
  that says nothing of oily skin, leaves the oily-skin foundation answer, and so does "powder foundation"; "dusty rose
  blush" leaves blush for fair skin; cream blush loses both its tips ("dusty rose blush", "brush for liquid blush"), as
  module 1 reads "cream" as its need; the bare "color corrector" leaves concealer for dark circles, where "oil-based
  cream concealer for dark circles" comes in. Makeup only, as fix 1's tip rules: no tip moved outside makeup. Tried
  and dropped the same night: leaving out a "Look for" that names another makeup type worn as the type asked for
  ("pressed powder in a darker shade as bronzer", which the shopper review listed as not blocking). The first final
  run's whole suite failed on it: part 2 keeps "bronzer worn as blush" on purpose, with a test. Part 2's rule stands, a
  new test guards it, and the bronzer tip stays, as does eyeliner's "black eyeshadow to set eyeliner".
  (2) Quotes (config.QUOTE_THANKS_THREAD in engine/answer.py _ELSEWHERE; _bare_like). A quote thanking the thread for
  its suggestions leans on comments the reader can't see, as one answering what someone else said does (fix 1): it
  comes after a clearer quote and only makes up a pick's minimum. Thanks for a thing ("thanks to the wax in it")
  stands. And a quote that only likes its product, naming it by a plural of one of its name's words ("I like Rosas"),
  is a bare like and comes last, as one naming it plainly already did. Effect: the Benefit brow gel pick (brow gel,
  eyebrow gel) no longer shows the thank-you quote or the plural like; it leads with a comparison with Anastasia,
  then its all-day hold. Outside makeup one quote moved: in "moisturiser without niacinamide", La Roche-Posay
  Lipikar's second "Also worth a look" quote, a bare like of the Triple Repair moisturiser ("moisturizers" now read
  as its name), gives way to one about dry, sensitive skin.
  (3) Names: "YSL Lash Clash" as its maker writes it (config.MAKER_SPELLINGS; the mascara answer had "YSL lash clash").
  (4) The price list (data/prices.json): Marc Jacobs O!Mega Bronzer, also called "Marc Jacobs bronzer", is checked as no
  longer sold (6 Nov 2026, Cosmetics Business: the brand's makeup was discontinued in 2021, and it relaunched on 1 June
  2026 under Coty with another bronzer). The library's voices for it praise the original, so it leaves bronzer's "Also
  worth a look" by the route fix 1 used for The Ordinary's primer, and Physicians Formula Butter Bronzer comes in, with
  a new summary. Fix 1 had left this for Noemi; the shopper review called it blocking, as a shopper can't buy it, and
  whether a product is still sold is a fact, so Claude made the call. Deleting the entry undoes it. One rule for
  discontinued products, and an entry for the relaunch's bronzer once voices for it arrive, are hers to decide.
  (5) The removed threads (Noemi's "Remove those 2 threads"): `python -m engine.bright_data fetch` into the library now
  refuses 1co3r5i and 1jlzpoa (config.REMOVED_THREADS), as it refuses unlabelled gold threads, and fix 1's two
  untested on-demand lines have tests (pull skips the two threads; one already in the bundle under the same request
  no longer gets past the skip list). Left: the on-demand job's extraction step and forget_baked don't check the list
  (a copy would have to be in the bucket's bundle, which the deploy of 3 Nov should have emptied).
  (6) The summaries (data/library/summaries.json, backed up before each write, written atomically; git-ignored). From
  the fact-check: Givenchy's setting powder entry is dropped. The answer shows a warning under the pick, folded in
  from the brand's line, that the sentence didn't tell, and as that warning isn't one of the product's own credible
  mentions no entry can cite it (checked again this round), so the pick shows no summary until the check can judge
  warnings folded in from a line (code, later). 12 rewritten: one writer's view given to several (Haus Labs Glassy
  Balm, Anastasia Beverly Hills brow gel, NYX Marshmellow, Tower 28 concealer, ONE/SIZE setting spray, CeraVe's
  retinol serum; Maybelline Super Stay Skin Tint keeps its words and cites a second writer for them), one writer on
  both sides (NARS Radiant Creamy), wording (Urban Decay's eyeliner line; Benefit Roller Lash, which kept a five-word
  run of a writer's words), and downsides left out (The Ordinary's primer, said again to be discontinued as a
  commenter says; MAC Lady Danger, the writer who gave up MAC lipsticks after contact reactions). 1 new: Physicians
  Formula Butter Bronzer. The 16 entries fix 1 wrote that stay as written are restamped with when they were really
  written (04:12:30Z for its first write, within 15 seconds, and 04:26:00Z for its second, the file's time), not 04:30
  and 04:40. Every entry passes engine.summaries' own text and number checks, has no five-word run of a cited
  comment's words (apostrophes and punctuation dropped) and cites only comments credible in every answer that shows
  its product.
  (7) Earlier notes corrected, each marked "corrected in fix 2": part 4's "a list nothing reads a thread from"; the
  integrator's "six skincare" (three) and the cause it gave for the evaluation's other ingredient and needs picks;
  fix 1's test counts, "blush" (a lip tint answer), its wording of _line_brand, its five-word-run claim and the cause
  it gave for the evaluation's two moving counts. That cause is the day the evaluation judges by, not the live-check
  cache or the warm: pipeline._today() is date.today(), which sets the 14-day live-check window, and the integrator's
  runs set TZ=UTC (judged 6 Nov) while fix 1's evaluation ran at 23:51 EST without it (judged 5 Nov). The fix 1 row of
  eval/RUNS.md is corrected the same way; 2183482's commit message keeps the wrong cause, as correcting it would need
  a rebase.
  Measured through the heavy lock on the live profile store (sha d78c2535f930, the same before and after every run),
  live checks off, with TZ=UTC (judged 6 Nov). Sweep of 295 answers (the same lists as fix 1's), no error, against
  fix 1's: no pick, pick order, score, Skip item or message moved anywhere; "Also worth a look" in two answers
  (bronzer, the mascara answer's YSL name), tips in 4 (all makeup), pick quotes in 2 (brow gel, eyebrow gel), "Also
  worth a look" quotes in 2 (bronzer and the "moisturiser without niacinamide" answer; corrected in round 3, it said
  3: the mascara answer's YSL item changed only its name), summaries in 14 (11 makeup; outside makeup
  CeraVe's retinol serum reworded in three retinol answers). All 17 makeup answers give 3 picks; 99 of their 100
  shown items have a summary (Givenchy's, above). Non-makeup shown items with a summary: 628 of 1,212, as before.
  Every quote shown, 8,216, was found word for word in its saved comment, checked outside the engine; 723 in the 17
  makeup answers (r/Makeup 208, r/Sephora 301, r/MakeupAddiction 97, r/drugstoreMUA 80, r/AsianBeauty 37; none from
  r/MakeupRehab). Brand accounts: 1,346 credible voices behind the 100 shown makeup items, run through module 5's own
  signs again: the same one flag as before (a Thrive Causemetics mascara voice, not shown). `python -m
  engine.summaries check`: 912 entries, 663 fine, 249 with problems, the same 249 as fix 1's check; none written
  since 5 Nov. Whole suite: 7,249 passed and 2 failed, the unlabelled gold thread 1v40u3t (which fails on main too)
  and the check that eval/metrics.json's date has a RUNS.md row, which this round's row of 6 Nov answers.
  eval/run_eval.py on a copy of the store: identical to the integrator's run (judged 6 Nov too) but module 4's product
  groups, 34,442 to 34,441 (4,750 to 4,749 loose: fix 1's names), so the blind-test answers show 257 quotes (all
  verified) and 56 threads wait for a live check, and the ingredient and needs sections print the integrator's picks:
  this confirms the cause in (7). eval/metrics.json is dated 6 Nov, the day it judged.
  Left for Noemi: NARS Orgasm as a blush pick beside "Skip: NARS Orgasm (new formula)" and got2b's hair gel as a brow
  gel pick (the product notes); the need-fit rule; lip tint's and lip stain's 3 threads and brow gel's 5; "twist-up lip
  liners" under lipstick (module 1 files lip liner under lipstick); one rule for discontinued products and for
  substitute tips. Not blocking and left: the Etude Fixing Tint quote about its glossy sibling, the Hourglass Veil
  quote meaning another product, ONE/SIZE's weak quotes, the colour-corrector tips, Gucci's third quote, the KVD Skip
  and makers' lower-case names. The scratch files of this round hold commenters' words and go to the Trash with the
  deletion rule.
- 6 Nov 2026, round 3 after the warm (Claude: the builder, then the summaries writer and the integrator; branch
  makeup-threads; nothing pushed, merged or deployed).
  Noemi's decisions of 6 Nov 2026 ("yes to all three", in chat), hers, and the round's technical calls from the third
  reviews, Claude's, reported to Noemi. Inside her bounds: apart from her decisions (2) and (3), no scoring weight,
  picks bar, product type, told number (about 25 minutes, 30 a day, 39 a month) or the 48-hour quote rule touched; the
  need-fit rule still off (config.NEED_FIT_FOR_PICKS = False). Values at the end of engine/config.py ("Noemi's
  decisions of 6 Nov 2026"); tests in engine/tests/test_makeup_round3.py (26 on made-up text, each failing on 4e2ebc9's
  code), and fix 2's on-demand test changed on purpose with a dated comment ((5) below).
  (1) Noemi's: the product notes stay (data/product_notes.json: NARS's 2024 reformulation, Becca's closure, got2b's hair
  gel), each shown wherever its product is shown. Checked in this round's sweep of 295 answers: every shown item whose
  name gets a note shows it (NARS Orgasm blush line in blush and blush for fair skin, got2b Glue Spiking Gel in brow gel
  and eyebrow gel, all four now under "Also worth a look"); Becca's highlighter is shown in none; no Skip item (which
  shows no notes) carries a noted name now, as the three "NARS Orgasm (new formula)" items are gone ((3)).
  (2) Noemi's: a hair product is never a pick in a face-makeup answer, known by what it is rather than by one name. A
  product one of whose names (the shown one or a writer's) says hair gel, spiking gel, hairspray, hair glue and the like
  (config.HAIR_PRODUCT_WORDS, beside the tips' TIP_OFF_LABEL_WORDS), and doesn't also name the type asked for, is never
  one of the picks of an answer for config.FACE_AND_EYE_TYPES (engine.pipeline._a_hair_product; engine.rank.
  ProductScore.pickable). Its score is unchanged, and Claude's call: when it meets the bar on its own it still heads
  "Also worth a look", labelled as meeting the bar as a product ranked below the picks is, with its product note. A
  brow glue, brow soap or brow wax is a brow gel; hair words only ("pomade", "mousse" and "wax" also name makeup).
  Outside face makeup nothing changes. Measured: in brow gel and eyebrow gel, got2b Glue Spiking Gel (third, score
  2.025) leaves the picks, Kosas Air Brow (1.85) comes third, and got2b heads "Also worth a look" with its note, before
  e.l.f. Brow Lift and Anastasia's line as before. No other answer moved by it.
  (3) Noemi's, NARS Orgasm, option (b): the credible warnings filed under a "(new formula)" item are about the product
  sold today, so they fold into the product they are about, show as its downsides and in its share line, and it lands
  where the unchanged scoring puts it (engine.pipeline._new_formulas_folded; config.NEW_FORMULA_WORDS). General: any
  item a name calls "(new formula)", "new formulation of", "reformulated" or "post-reformulation", in any category, when
  the answer has its product (module 4 groups the renamed mention with a mention named otherwise); a new formula of a
  product the answer doesn't have stays a Skip item of its own; an old, original or pre-reformulation formula, and a
  bare "(new)", are other products. Only a renamed mention is ever dropped, when its writer's comment already names the
  product sold today with the same stance. (The round's first sweep had also merged repeated mentions of other
  products, which moved a CeraVe share line in "moisturiser that works under makeup"; fixed, with a test, before the
  final sweep.) Measured: in blush and blush for fair skin, NARS Orgasm blush line takes the three credible warnings
  ("3 of 19 credible voices warned against it", two shown as its downsides), its score goes from 8.85 to 7.36, below
  Patrick Ta's line (7.9), which becomes the third pick; NARS heads "Also worth a look" with its note, and "Skip: NARS
  Orgasm (new formula)" leaves both answers. In cream blush the same Skip item folds into the NARS line, which that
  answer ranks but doesn't show, so it has no Skip item now. In lipstick, MAC Ruby Woo takes one credible warning of
  its new formula (score 7.55 to 7.3, still the first pick, now "1 of 15 credible voices warned against it"). The
  library's other new-formula items (Eucerin's urea cream, Aestura, Urban Decay All Nighter, Dior 999, Maybelline Lash
  Sensational, a NARS blush) move nothing shown in the 295 answers.
  (4) Claude's: the bare swear word the page didn't mask (the rules review: a brow gel pick led with it).
  engine.answer.MASKED_WORDS (shared with the search page's script) now holds the bare word and its British spelling,
  singular and plural, as whole words: "class", "pass", "assess", "bass", "Assam" and "badass" stay as written;
  "kick-ass" is masked. A quote holding a masked word comes after a clearer one (_unfit_first, as before). Measured:
  fix 2's sweep showed it in 14 places (8 comments, 12 answers), all masked on the page now (display only, as every
  masked word: the API keeps the verified words). 6 gave way to a clearer quote (the Benefit brow gel pick's first quote
  in brow gel and eyebrow gel, King stones' third in the Japanese knife sharpener answer, the Aroma rice cooker line's
  first downside in both rice cooker answers, the Brooklinen sheets Skip item's second quote); 8 stay where they were,
  masked (downsides of the Philips air fryer and Miele vacuum lines, a Metabo drill Skip quote).
  (5) Claude's, on-demand reading (from the rules review of fix 2): engine.on_demand._read_entry leaves Noemi's two
  removed threads (config.REMOVED_THREADS) out of the request's threads twice more: out of the count of threads already
  extracted for its product type (a removed thread in the bundle no longer closes a request one thread short as "enough
  threads about it already"), and out of the threads read on an earlier try that keep a place in its round. Fix 2's
  test of that place (engine/tests/test_makeup_fix2.py) changed on purpose, with a dated comment: it now gives the
  communities more threads than their caps, so it fails when the line is undone (it passed either way before).
  (6) Claude's, an extraction error: comment lc27xk3 of thread 1dxfrqq was extracted as five setting spray warnings
  (Laura Mercier, Charlotte Tilbury, NARS, Sephora Collection, ONE/SIZE). The writer sets with spray only, as powder
  never helped their very dry skin, and the brands they turn down come straight after that, most likely the powders
  they tried; the comment doesn't say which products. Filed as setting powder warnings they would rest on a guess and
  on the writer's skin type, so they are removed rather than re-filed, by the project's own route (`python -m
  engine.ethics apply`, "remove": checked as an extraction is, written atomically; the comment, left with nothing to
  use, keeps only its shape, as every such comment does). The library is outside git; the files before are kept in the
  round's scratch folder. Measured: ONE/SIZE's setting spray line (second pick) loses its only downside and its share
  line, its score goes from 6.5 to 7.05, the picks and their order stay; its summary cited that comment, so it isn't
  shown until rewritten (below). No other shown item named in the comment moved.
  (7) Claude's, the public repo (from the reviews): a test and a docstring had kept a commenter's short phrase about a
  brand (fix 2's plural like), and every run of four or more words the branch adds that is also in a library comment
  was checked by hand. The ones taken from comments are paraphrased with made-up text that tests the same thing
  (engine/answer.py's docstrings and comments, engine/config.py's comments, engine/tests/test_makeup_fixes.py,
  engine/tests/test_answer_shows.py, engine/tests/test_makeup_fix2.py and five example phrases in the notes of 4 and 5
  Nov above); the rest are common English or product names. (Corrected by round 3's fixer, from the rules review: this
  note first said fix 2's commit message still held the phrase. It doesn't: the phrase is in two of that commit's
  files, engine/answer.py's _bare_like docstring and engine/tests/test_makeup_fix2.py; 31abbd2 takes it out of both, and
  no other commit's files or message hold it. So the history rewrite before the merge must fold 4e2ebc9 into 31abbd2,
  or rewrite 4e2ebc9's files; rewording its message is not enough: the orchestrator's call.)
  (8) Corrected in round 3: fix 2's note above and its eval/RUNS.md row counted "Also worth a look" quotes changed in 3
  answers; it was 2 (bronzer and "moisturiser without niacinamide"), as the mascara answer's YSL item changed only its
  name.
  Measured through the heavy lock on the live profile store (sha d78c2535f930, the same before and after), live checks
  off, TZ=UTC (judged 6 Nov). Sweep of 295 answers (fix 2's lists), no error, against fix 2's: picks and "Also worth a
  look" moved only in blush, blush for fair skin, brow gel and eyebrow gel (above); scores in those four, setting spray
  and lipstick; Skip in 3 (the NARS new formula); downsides in 8 (6 makeup, the 2 rice cooker answers' masked quote);
  pick quotes in 5 (one outside makeup, the knife sharpener's), Skip quotes in 4 (one outside makeup, the sheets');
  tips, messages and every non-makeup pick, order and score unchanged. All 17 makeup answers give 3 picks; 98 of their
  100 shown items show a summary (not Givenchy's setting powder line, as in fix 2, nor ONE/SIZE's). Every quote shown,
  8,211, was found word for word in its saved comment, checked outside the engine; 718 in the makeup answers, none from
  r/MakeupRehab. The summaries todo for the 17 makeup answers lists 4 products for the writer: Givenchy's and ONE/SIZE's
  lines, NARS Orgasm blush line and MAC Ruby Woo, whose summaries leave out the folded warnings they now show. `python
  -m engine.summaries check`: 912 entries, 662 fine, 250 with problems, fix 2's 249 and ONE/SIZE's (the removed
  comment). Whole suite: 7,276 passed and 1 failed, the unlabelled gold thread 1v40u3t (which fails on main too).
  (9) Claude's, the summaries round (the summaries writer; data/library/summaries.json is outside git, and its file
  from before is kept in the round's scratch folder): 18 summaries written or rewritten, each passing `python -m
  engine.summaries check`: NARS Orgasm blush line and MAC Ruby Woo (each now tells the warnings (3) folds into it),
  ONE/SIZE's setting spray line (without the comment removed in (6)), Tower 28's concealer line (it cites the warning
  it shows) and 14 more from fix 2's fact-check list (each fixed as its finding said), Marc Jacobs's bronzer among
  them (no answer shows it; worded as a 19th by mistake at first, corrected by round 3's fixer). Givenchy's setting powder line stays without one: the downside its pick shows is filed under
  another name of the brand's powder, which is not one of the line's credible mentions, so no summary can cite it and
  one that left it out would contradict it (its share line reads "1 of 10" while its score breakdown counts no
  credible warning: the same shape as 34 items of main's own sweep, a downside shown from the line's other names; not
  new in this round). Seven makeup products (Milani's blush line, Natasha Denona's, Huda Beauty's, Laura Mercier's,
  Urban Decay All Nighter's, L'Oréal Telescopic's and Victoria Beckham's lines) still leave one shown downside uncited
  in their summaries; the summaries pass the check, and the pass is left for later. A summary is shown only while
  every comment it cites passes its live check, so the ones citing most comments (Tower 28's and Kosas's concealer
  lines, 9 each; Thrive's mascara line, 8) drop out first on a day when one cited comment fails.
  (10) Claude's, the public repo once more, by the integrator: every run of four or more words that the branch adds
  (code, tests, DECISIONS.md, RUNS.md, data files and every commit message) was checked against every library comment
  and thread title, as one comment's longest shared run, not a run stitched from several. No username appears, no
  whole thread title of four words or more; the longest shared runs (up to 9 words) are product names or lists of
  product types, and the 6-word overlaps otherwise occur in three or more comments each (everyday phrases), except two
  sentences that ran close to one comment's own words (a test sentence about daily use in
  engine/tests/test_makeup_split.py and the "same experience" warning of engine/tests/test_answer_shows.py's skip
  test): both reworded with made-up text that tests the same thing (the tests pass unchanged otherwise). Commit
  4e2ebc9's files (not its message, as this note first said; corrected by round 3's fixer) still hold the phrase noted
  in (7).
  (11) The integrator's final run (6 Nov 2026, 08:13 to 08:40 UTC), through the heavy lock on the live profile store
  (sha d78c2535f930 before and after every step), live checks off, TZ=UTC, on the committed code with the summaries of
  (9). Sweep of 295 answers (the same lists), no error: against the builder's sweep only summaries moved, in 13 makeup
  answers; against fix 2's the changes are the builder's (picks and "Also worth a look" in blush, blush for fair skin,
  brow gel and eyebrow gel; scores in those four, setting spray and lipstick; Skip in 3; downsides in 8; pick quotes
  in 5; Skip quotes in 4; "Also worth a look" quotes in 4), all traced to (2) to (6); against main's (278 non-makeup
  answers): no pick, pick order, score, "Also worth a look" item or Skip item differs, the 10 blind-test answers
  included (80 of the 278 differ from main's in a shown quote, summary or reason line, 76 at fix 2: the 4 more are
  (4)'s masked word). All 17 makeup answers give 3 picks; 99 of their 100 shown items have a summary (the builder's
  sweep: 98; not Givenchy's); non-makeup 628 of 1,212, as before. Every quote shown, 8,238 (the summaries' cited
  quotes included), was found word for word in its saved comment, checked outside the engine; 745 in the 17 makeup
  answers (r/Makeup 211, r/Sephora 309, r/MakeupAddiction 101, r/drugstoreMUA 83, r/AsianBeauty 41), none from
  r/MakeupRehab and none anywhere from threads 1co3r5i or 1jlzpoa. Brand accounts: 1,352 credible voices behind the
  100 shown makeup items, run through module 5's own signs again: the same one flag as before (a Thrive Causemetics
  mascara voice, one of 30 behind that pick, a customer's plain remark, not shown), so no brand account drives a pick.
  NARS Orgasm shows its three new-formula warnings and its note in both answers that show it; got2b's note shows in
  both brow answers; Becca's is shown nowhere. No hair product is among the picks of the 17 answers. `python -m
  engine.summaries check`: 912 entries, 663 fine, 249 with problems, fix 2's 249 older entries; none of a makeup type.
  Whole suite, three times (before and after the two test sentences of (10), the last on the final commit's code
  before its message was amended, ending at 08:46:31 UTC, while d453d6d was committed at 08:46:53; corrected by round
  3's fixer: the rules review's own run on d453d6d gave the same): 7,276
  passed and 1 failed, the unlabelled gold thread 1v40u3t (which fails on main too). Offline evaluation on a copy of
  the store: identical to fix 2's run in every number but the library's quote count, 93,773/94,276 to 93,768/94,271
  (the five mentions of (6), all five found word for word, so the share is the same to five places, 0.9946646 against
  0.9946643; corrected by round 3's fixer, it said six); against main's
  last row (2 Nov), the same cells but two: the library's quotes found word for word, 99.60% to 99.47%, and quotes
  shown, 265 to 257 (all verified). The lower share is the library's, not this branch's code (engine/extract.py equals
  main's) and was already in the 4 Nov row, from the 3 Nov verification pass that rewrote kept comments: 99.41% of the
  78,110 mentions outside the makeup communities (the 4 Nov row had 99.41%) and 99.75% of the 16,161 in them.
  eval/metrics.json is saved from this run, dated 6 Nov. Told numbers (products a day 30, a month 39, the wait told 25
  minutes for the first and 21 for each, 15 calls a product at a minute each and 6 for the archive, 450 Gemini calls a
  day, 50,000 seconds a month, 20 waiting, 150 minutes late) are equal to main's in every value; the one config
  difference, ON_DEMAND_SEARCH_CALLS = 16 (4 Nov, Noemi's "Keep 25 min": the cap that keeps a round inside main's own
  numbers), is not a told number and unchanged this round (no ON_DEMAND constant moved since 4e2ebc9). The need-fit
  rule is off (config.NEED_FIT_FOR_PICKS = False) and the three product notes are in data/product_notes.json. Every
  commit since main is dated +0000 with the one Opus 5.5 trailer, except fa6ee08's extra Sonnet 5.5 trailer, which the
  orchestrator rewrites before the merge.
  Left for Noemi: whether a hair product under "Also worth a look" should carry the "Meets the bar for a pick" label
  (it does, as a product ranked below the picks does, though got2b's can never be a pick); cream blush losing its only
  Skip item to a product it doesn't show. Left for the orchestrator: 4e2ebc9's files, which hold the phrase of (7) (fold
  that commit into 31abbd2 or rewrite its files: rewording its message is not enough; corrected by round 3's fixer, it
  said the message), and fa6ee08's extra trailer.
  Round 3's fixer (6 Nov 2026, from 09:20 UTC; Claude: the rules review, the shopper review and the summary fact-check
  of d453d6d; Claude's technical calls, reported to Noemi; nothing pushed, merged or deployed). Inside the same bounds:
  no scoring weight, picks bar, product type, told number or the 48-hour quote rule touched, engine/config.py unchanged,
  the need-fit rule still off and data/product_notes.json unchanged. Tests in engine/tests/test_makeup_round3_fix.py (7
  on made-up text, each failing on d453d6d's code); two tests that list an "Also worth a look" item's fields
  (engine/tests/test_web.py, engine/tests/test_answer_worth.py) changed on purpose with a dated comment, for its new
  field.
  (12) Claude's, the rules review's one blocking problem: (7), (10) and the last lines of (11) said a commenter's phrase
  was still in fix 2's commit message. It was in two of that commit's files instead; the three sentences are corrected
  above, and so is the orchestrator's task: fold 4e2ebc9 into 31abbd2, or rewrite 4e2ebc9's files, before the merge.
  Also corrected above, from the same review: the library's share found word for word is the same to five places, not
  six (and in its eval/RUNS.md row); the 18 summaries of (9) were worded as 19; and the integrator's last suite run was
  on the final commit's code before its message was amended.
  (13) Claude's, wording (Noemi's decision (2) keeps a hair product out of the picks; the reviews found its label
  untrue): got2b Glue Spiking Gel outscores the third brow gel pick, so neither the "Meets the bar for a pick" tag nor
  "ranks below the top 3" was true of it. A hair product under Also worth a look is now tagged "A hair product, never a
  makeup pick" instead (engine.answer.HAIR_PRODUCT_TAG; the API's worth items carry "hair_product", true only for such
  an item; the page and the text answer show the tag), and the note under the heading says why it isn't a pick: in
  brow gel and eyebrow gel, "Each meets the bar for a pick (...); the hair product is never a makeup pick, and the
  others rank below the top 3." (engine.answer._worth_note_hair, every shape tested). Its place, score and product
  note are unchanged. Measured: those two answers' note and tag change, and nothing else in the 295.
  (14) Claude's, Noemi's decision (1) made general: a product note now shows under Skip these too (engine.pipeline.
  _note_products returns the notes it adds; engine.answer.SkipItem.cautions holds them, and no other caution, as a
  caution about fit to the request says nothing to a product to skip; the API's skip items carry "cautions", and the
  page and the text answer show them). Measured: no Skip item of the 295 answers is a noted product, so nothing shown
  changes today.
  (15) Claude's, on-demand reading (the rules review): engine.on_demand._finish_complete no longer counts a removed
  thread (config.REMOVED_THREADS) filed under a request in the bundle, in its count, its note or the wait for its
  extraction.
  (16) Claude's, summaries (data/library/summaries.json is outside git; written atomically, the file from before kept
  in the round's scratch folder): 10 rewritten, each passing `python -m engine.summaries check` in every answer that
  ranks its product, all writers cited in one summary different people. Kosas's concealer line: looks orange on fair
  skin, not turns orange (the writer is too fair for the shade). L'Oréal Telescopic's line: no longer says it lifts
  without clumping beside a shown downside that says the opposite, and now tells the waterproof version's removal
  downside it shows. Natasha Denona's concealer line: now tells its two shown downsides (too thick; it burns for a
  writer with eczema). Tower 28's concealer line: in proportion to its 71 credible voices for and 8 against, with the
  sheer coverage a dark-circles reader needs to know. And six that gave one writer's words to a group, now told as
  one writer's: Patrick Ta's blush line, Rare Beauty Soft Pinch Liquid Blush, Maybelline Super Lock Brow Glue, Too
  Faced Chocolate Soleil, Huda Beauty's setting powder line (now also telling the cakey downside it shows) and
  L'Oréal True Match. The first Rare Beauty rewrite cited a comment that the cream blush answer, which ranks it without
  showing it, doesn't count, so the check flagged it; rewritten again before the final sweep. Measured: the 10 show in
  14 places of 10 makeup answers; the check lists 912 entries, 663 fine and the same 249 older entries with problems
  as before, none of a makeup type.
  (17) Left, with why: quote choice (ONE/SIZE's three weakest quotes leading, Tower 28's shelf-life quotes, brand lists
  leading Patrick Ta, NYX Epic Ink and a Cloud Paint quote, Maybelline's and Kosas Air Brow's first quotes): each needs
  a general rule for which quote leads, which would move quotes in many answers outside makeup, so it is a measured
  round of its own, not a quick fix; three tip labels in American spelling and the highlighter tip whose quote never
  names glitter (the tips' names come from module 4's kinds, used in matching; respelling them is not display-only);
  Milani's blush line's glitter downside, which no summary can cite (the comment is not one of the line's credible
  mentions); Etude Fixing Tint, joined by module 4 with the glossy Glow Fixing Tint, and its summary's source quote
  naming the glossy one (a grouping change, not a name fix); the uncited shown downsides of Laura Mercier's, Urban
  Decay All Nighter's and Victoria Beckham's lines (covered in spirit, the fact-check said); and the earlier leftovers
  (Rare Beauty's powder highlighter quote, the NYX Brow Glue Skip item's first quote, the fair-skin tip in plain
  blush).
  (18) The fixer's run, through the heavy lock on the live profile store (sha d78c2535f930 before and after every
  step), live checks off, TZ=UTC. Sweep of 295 answers (the same lists), no error, against the integrator's final
  sweep: only the hair tag and the note in brow gel and eyebrow gel, and the 10 summaries, differ; no pick, order,
  score, Also worth a look or Skip item, quote, downside, share line, tip or message moved anywhere, and against main's
  the 278 non-makeup answers' picks, order, scores, Also worth a look and Skip names are equal, the 10 blind-test
  answers included. All 17 makeup answers give 3 picks; 99 of their 100 shown items show a summary (not Givenchy's
  setting powder line, as before); non-makeup 628 of 1,212. Every quote shown, 8,251 (the summaries' cited quotes
  included; 758 in the makeup answers, the 13 more being the rewritten summaries' sources), was found word for word in
  its saved comment, checked outside the engine; none from r/MakeupRehab or the two removed threads. No hair product
  is a pick, and no Skip item carries a note. Whole suite: 7,283 passed and 1 failed, the unlabelled gold thread
  1v40u3t (which fails on main too). Offline evaluation on a copy of the store: every number identical to the
  integrator's run, so eval/metrics.json is unchanged.
  Left for Noemi, as before: whether she wants a hair product listed under Also worth a look at all (its label is
  settled by (13)), and cream blush losing its only Skip item to the NARS line it ranks but doesn't show (her decision
  spoke of a shown product; folding it for an unshown one too is Claude's reading).
  The scratch files of this round hold commenters' words and go to the Trash with the deletion rule.
- 6 Nov 2026, before the merge (Claude, the orchestrator): the branch history after 1744cec was rewritten with git
  filter-branch, so no commit holds the commenter's phrase of (7) or the extra Sonnet 5.5 trailer. 4e2ebc9's two
  files now carry the paraphrase that 31abbd2 had brought, and fa6ee08's message ends with the one Opus 5.5 trailer.
  The final tree is identical to the one the three reviews passed, and every date is unchanged. The commit ids in
  these notes, eval/RUNS.md and one test comment were updated to the rewritten ones (fa6ee08, 2183482, 4e2ebc9,
  31abbd2, d453d6d, f98f945).
- 5 Nov 2026, midday, the site's memory back to 2 GiB (Claude, the site-memory builder, branch site-memory from makeup-threads
  1744cec, not merged and not deployed because the makeup branch merges first. Noemi chose it on 5 Nov 2026 with "Let's do A":
  the site goes back from 4 GiB to 2 GiB with margin. Google's free allowance for Cloud Run is most likely one pot shared by the
  site and the jobs, October's real use came to 84% of its memory part and most of that was the site at 4 GiB, and halving it
  frees room to double on-demand reading for free. Everything below is Claude's technical calls, reported to Noemi. No answer,
  wording, score, rule, read-ahead count, busy cap, concurrency or on-demand behaviour changed.)
  Measured first. Cloud Monitoring (read only) for the site's 4 GiB revisions from 15 Oct to 5 Nov 2026, 6,061 five-minute
  windows: the busiest window of each day rose from 1.28 GiB (16 Oct) to 2.00 GiB (5 Nov), as the library grew from ~1,950 to
  2,748 threads and as each instance's memory climbed through its life (the evening note below). The median window was 1.64 GiB, 54% of the windows were over 1.6 GiB, 19% over 1.8 and 0.9%
  over 2.0. At 2 GiB it would have run out of memory within hours. The pre-check job used 1.1 to 1.47 GiB of its 3 GiB since 16 Oct (1.47 on 19 Oct, 1.35 on 4 Nov).
  The site was then run on Noemi's computer the way the image runs it: the library as the image holds it (2,748 threads), the open
  model, the keep-warm ping reading ahead against stand-ins for Reddit and the bucket, 8 answers at once, a bundle of 300 threads
  read on demand and a 34-minute soak of about 4,200 different requests, with its macOS footprint read every 1.5 seconds. On the
  code as it was it peaked at 2,075 MB (Cloud Monitoring's busiest window of that week was 2,048 MB, which is no calibration, as
  the evening note below says). The breakdown, each object counted once after the 85 warm answers: the library's threads 371 MB and extractions
  168, the tables of every name's words and features that the library's name index fills 290, the brand rules' pairs 75, the
  credibility tables 85, the profile store 69, the name index 63 and ranges 43, and the comments read for each thread 56 once all
  are touched. Remembered answers were never let go of.
  Bounded, each with its tests written first (engine/tests/test_site_memory.py). One: objects of one shape share the set of field
  names that pydantic keeps for each (728 bytes a comment), made as each thread is read (engine/compact.py), about 250 MB, and a
  library read again no longer holds two sizes. Two: the tables of names' words and features are emptied once a category's name
  index is built, about 190 MB. Three: the profile store the site reads is held compactly and read only, 69 MB to 41. Four: the
  brand rules' pairs share their sets of names, 75 MB to 15. Five: remembered answers are kept to 24 MB, about 1,000 answers,
  expired ones first and then the oldest. Six: a Table holds 40,000 answers (200,000 before), the facts of recent threads 256
  (512) and the library's names share their words, about 100 MB together. Not changed: the 64 product types the answers' memory
  keeps and what warming warms (the search page's examples and the 62 demo requests stay warm).
  Result, footprint in MB by load phase, as it was and as it is: getting ready 1,821 and 1,208, keep-warm pings 1,847 and 1,209,
  8 cold answers at once 1,846 and 1,209, remembered answers 1,791 and 1,170, on-demand status polls 1,795 and 1,172, the bundle
  taken in 1,834 and 1,172, the soak 2,075 and 1,449. The resident set, with the open model's file counted, peaked at 2,509 and
  2,035. The worst case of this round was 70.7% of 2 GiB, which the review found was not the worst case (the evening note below).
  With the 300 largest library threads as the bundle in place of a typical 300 (92,855 comments against 24,015) the bundle phase peaked at 1,210 MB and a 17-minute soak at 1,530 MB (74.7%), where the typical bundle's soak was 1,432 MB at that point.
  Nothing a visitor sees changed. All 296 requests of eval/sweep.py (the 182 of the eval files, 62 demo, 37 interviewee, 15
  makeup and 3 extra) gave identical answers in every field, before and after on one frozen copy of the profile store with live
  checks off, twice (the second time on the committed code). eval/run_eval.py with live checks off gave identical output
  (333 lines) and an identical eval/metrics.json. Speed did not move: warmed answers had a median of 0.235 s before and 0.237 s
  after (24 requests), first answers of a type 0.281 and 0.282 s (20 types), remembered answers take no time, getting ready took
  132.7 and 132.6 s, and the sweep's 296 answers took 282 and 272 s in all. The whole suite: 7,221 passed and 1 failed, the known unlabelled gold thread 1v40u3t (7,196 passed and the same 1 failed before, so the 25 new tests are the difference). Two assertions of existing tests changed on purpose, dated where they stand: test_cloudrun's site and pre-check memory (4 GiB to 2 GiB, 3 GiB to 2 GiB) and test_region's `--memory 4Gi` check.
  The pre-check job (the same library, the open model off, 559 requests) peaked at 1,410 MB before and 1,092 after on Noemi's
  computer, against 1.35 GiB on Cloud Run on 4 Nov 2026, so it runs at 2 GiB too (53% of it, inside the same 80%) and bills a third
  fewer GiB-seconds. The site's reading ahead bills at most 124,992 GiB-seconds a month now, where 4 GiB billed 249,984.
  Room: a library thread costs the site 0.255 MB when warm (it was 0.40) and about 0.31 on the worst case. The count of threads
  that fit and the weeks of room first worked out from that are withdrawn (the evening note below). The next bounds, by what the
  measurement shows: the comments read for each thread (56 MB, about half could go), the name index and the library's ranges (63
  and 57 MB, packable with their words shared), the name features (38 MB, their sets of letters and lengths shared) and the
  credibility tables (~90 MB, capped at 40,000 each already).
  The harness is in eval/site_memory now: a fake Reddit and bucket, a load driver that runs in segments with the server frozen
  between them, and the structure sizers. Not measured here: Linux (glibc's arenas per thread may add to or take from the
  figures), Cloud Run's own count of memory, and the real Reddit and bucket. After a deploy, read Cloud Monitoring's memory for the
  first day and compare it with the evening note's figures.
- 5 Nov 2026, evening, the site's memory: the review's four blockers (Claude, the site-memory fixer, branch site-memory on
  top of beab67c, not merged and not deployed). The midday note above is the first round. A reviewer ran the site on Noemi's
  computer the way the image runs it, with the library of 2,748 threads, the open model, the 300 largest threads as an
  on-demand bundle and a 60-minute soak of 7,547 different answers, and found the code right (answers identical, the suite
  green) and the memory not yet safe at 2 GiB. What the first round got wrong and what was done, all Claude's technical calls
  with nothing a visitor sees changed: no answer, wording, score, rule, the 48-hour quote rule, the concurrency of 8, reading
  ahead's counts, the busy cap or on-demand behaviour. Speed is the one thing that may move, and it is reported below.
  One, the soak went over the line: 1,742.5 MiB, 85.1% of 2 GiB, where the midday note called 1,449 MB the worst case. The
  cause was not fragmentation. A compiled expression of 549 KB that finds a type's names inside the names of the other types
  of the general category (engine/sources.py, _inside_pattern) was kept for every type ever asked about: 31 MB after getting
  ready, 153 MB after a soak that touched 338 types, 196 MB for all 446, and a visitor's own words for a type the open model
  names added one each. Two more were the same in kind (_covering_pattern with
  _covering_phrases, and _community_covers, which is small: 6 Nov 2026, only 2 types have community names, about 1 KiB each,
  and the up to 0.6 MB each first written came from building it for types with none, which the code never does). A heap dump
  after 11 minutes of the soak showed the compiled expressions up 150 MB, the memory Python
  keeps for small objects up 59 MB and the footprint up 240 MB. They are now least-recently-used caches of ANSWERS_KEPT_TYPES
  (64) types, about 47 MiB for the 64 biggest general types (measured 6 Nov 2026, 37.8 for _inside_pattern, 5.6 for
  _covering_pattern and 4.0 for _covering_phrases, and a floor, since Python's own re cache of 512 patterns can hold ones the
  cache let go), and one let go is made again, the same expression, in 3 to 50 ms. In one process (the library and
  the 300 largest threads), 700 different requests after getting ready left the footprint at 1,067 MiB where it had been
  1,246 MiB, and the compiled expressions at 35 MB where they were 166 MB. Corrected 6 Nov 2026: this was the soak's climb,
  not the climb through each instance's life that Cloud Monitoring shows with pings alone (below), because no new product
  types are asked then and these caches do not grow.
  Two, the on-demand bundle's spike: taking a bundle in parsed the whole file at once, about 7.8 times its size for a moment
  (+119 MiB for the typical 16.1 MiB bundle, +416 MiB for the 300 largest threads). It is read one item at a time now
  (engine/on_demand.py, bundle_items): +25 MiB and +64 MiB, the file itself being the floor. The whole file is checked first,
  so a bundle that cannot be read still writes nothing.
  Three, Cloud Run's memory disk: a saved check is a file there and takes a 4 KiB page of memory whatever its size, which no
  macOS figure shows (18,400 files from the bucket's bundle at a start, 44,838 after the review's soak: 70 to 215 MiB). The
  public site keeps its saved checks in memory now (engine/live_check.py, _MemoryChecks, with the bucket set): 526 bytes
  each, 9 MiB for 18,400 and 23 MiB for 44,838, so the computer's figures count them. Any over 48 hours old, which nothing
  uses, is let go whenever the bundle is made. The daily job and Noemi's computer keep files as before.
  Four, the live projection was wrong. Cloud Monitoring's memory climbs through each instance's life and falls at each start
  (0.055 to 0.132 GiB a day with pings alone, 0.16 to 0.38 with the Show HN traffic, over instances of 4 to 73 hours), and
  the level 3 hours after a start rose from 1.16 to 1.20 GiB on 16 Oct to 1.60 to 1.72 GiB by 3 Nov. The first round read
  that as the library's growth (0.035 GiB a day), counted two weeks of room from it ("about 600 more threads fit"), expected
  the live site near 1.4 GiB, and took the 1.3% match between a 34-minute soak and a week's busiest window for a calibration.
  All four claims are withdrawn. Corrected 6 Nov 2026: the climb is only partly explained. With pings alone no new product
  types are asked, so the expressions above do not grow, and the checks' pages (reading ahead adds up to about 9,350 files a
  day, about 40 MiB) explain about 40 MiB a day at most, so 16 to 95 MiB a day of it is still unexplained, over instances
  that live up to 73 hours. The checks are in memory now and the expressions are bounded. MALLOC_ARENA_MAX=2 is in the
  image as well (glibc keeps two arenas, not one per thread), the one change no Mac can measure.
  The review's runs again on this code: getting ready 1,196 MiB, the largest bundle taken in 1,257 (it was 1,573.5), the
  60.6-minute soak 1,584.3 for the lifetime (it was 1,742.5, 85.1%), the largest bundle changing again at that level no new
  peak (it was 2,016.5, 98.5%), the control run 1,259 (it was 1,494), no error and no 503 in the soaks, and the saved checks
  counted (67,732 of them at the end of the soak, 35 MiB in memory).
  deploy.sh stays at 2 GiB, which Noemi chose (replaced 6 Nov 2026: 3 GiB first, see the last note). The worst case on the
  computer is 1,584.3 MiB, 77.4% of 2 GiB, under the 80% ceiling of 1,638 MiB, with the saved checks counted (corrected 6 Nov
  2026: the on-demand bundle's files on Cloud Run's memory disk were not counted, which makes it about 1,633 MiB, 79.8%).
  The margin is 54 MiB, it was measured on a Mac with reading ahead and
  the bundle's sharing sped up 60 times, and no Linux figure exists, so the first deploy is to be watched in Cloud Monitoring
  for a day and a week, and `--memory 3Gi` is the one-flag fallback (reading ahead then bills 187,488 GiB-seconds a month,
  52% of 360,000, against 124,992 at 2 GiB and 249,984 at 4 GiB). The reviewer's own alternative was to stay at 4 GiB or try
  3 GiB until Linux is measured, and that stays Noemi's call.
  Nothing a visitor sees changed: all 296 requests of eval/sweep.py (the 182 of the eval files, 62 demo, 37 interviewee, 15
  makeup and 3 extra) gave answers identical in every field except the seconds, on one frozen copy of the profile store with
  live checks off, and eval/run_eval.py with live checks off gave identical output and an identical eval/metrics.json.
  Speed: warmed answers had a median of 0.249 s before the first round, 0.263 s after it and 0.262 s now (the review's bench,
  best of two, 24 requests), first answers of a type 1.203, 1.304 and 1.131 s (20 types), so the second round moved nothing
  and the first round's 4% on warmed answers (3.7% here) stays. The sweep took 268.8 s and the eval 168 s. The whole suite:
  7,266 passed and the 1 known failure (test_library::test_real_gold_threads_saved_to_the_library_load_back, the unlabelled
  gold thread 1v40u3t), in 171 s under the heavy lock, where the first round had 7,221 and the same 1, so the 45 new tests
  are the difference. New tests are in engine/tests/test_site_memory.py, each written before its change. The measuring
  scripts are in eval/site_memory now (README.md there), so the numbers can be reproduced.
  Left as they are, with reasons. Remembered answers are kept to 24 MB, about 1,000 answers, so with more than that many
  different answers inside their 24 hours a remembered one can be let go and worked out again under the busy cap, and a
  repeat visitor may then wait or get a 503 in a rush: the answers stay the same, and a larger cap or keeping the most used
  would be the fix if it shows. The 4% slower warmed answers (the review's paired median 0.249 s to 0.262 s) are most likely
  forget_names and the smaller tables working some things out again: not noticeable, left. Taking in a bundle with new
  threads still makes the first answer wait 25 to 50 s (the library is read again) and refuses the visitors who ask meanwhile
  after 20 s, the busy cap, as before: nothing a visitor sees was changed. The hourly bundle write still builds the whole
  bundle in memory (about 40 to 90 MB for a moment at 20,000 to 70,000 saved checks), which writing it in pieces would trim.
  No Monitoring alert was made (it sends email in Noemi's name), and no gcloud command that changes anything was run. Linux
  is unmeasured, so read Cloud Monitoring's memory for the first day and week after the deploy, and use `--memory 3Gi` if it
  passes 1.6 GiB (80%) (replaced 6 Nov 2026: it starts at 3 GiB, see the last note). The control run's first ping after the typical bundle took 75 s on the review's code (uncompressed
  reading ahead against the stand-in for Reddit): 0.5 s now, the bundle read item by item, so the whole-file parse was at
  least part of it and I have no run of the older code to say what else. The scratch folders (library and profile copies,
  fake Reddit's pages, bundles, sweeps and evals) hold commenters' words and writers' names, and go to the Trash with the
  deletion rule.
- 6 Nov 2026, the site's memory: 3 GiB for the first deploy (Claude, the site-memory follow-up on top of f4d4be1, branch
  site-memory, not merged and not deployed). Two independent reviews of f4d4be1 found the code correct and the answers
  unchanged in all 296 sweep requests. The site deploys at 3 GiB first, for the reasons below, and steps down to 2 GiB once
  Cloud Monitoring shows p99 memory under about 1.5 GiB on instances at least 2 days old. It goes back to 3 GiB if the p99
  goes over 0.8 of the limit in any 5-minute window or the warmed level climbs more than about 0.05 GiB a day. The only
  behaviour change is the memory flag (deploy.sh, `--memory 3Gi`). The pre-check job stays at 2 GiB and the reading job at
  1 GiB.
  Why 3 GiB first. One, the 1,584.3 MiB lifetime peak did not count everything. On Cloud Run, write_items puts an on-demand
  bundle's threads into data/library/{threads,extracted} on the in-memory disk, and a Mac's footprint never counts files. For
  the 300 largest threads that is 49.0 MiB in 4 KiB pages, so the same worst case on Cloud Run is about 1,633 MiB, 79.8% of
  2 GiB and 5 MiB under the 80% ceiling of 1,638 MiB. A second measurement review found a lifetime peak of 1,459.3 MiB
  (71.3%) with its own soak, and Cloud Monitoring put the live old code, once warm, at 88 to 93% of the Mac's figure for the
  same code. That makes the Mac a conservative stand-in, but Linux, glibc with MALLOC_ARENA_MAX=2 and several days of creep
  are still unmeasured. Two, the climb with pings alone (live: 0.055 to 0.132 GiB a day) is only partly explained. No new
  product types are asked then, so the compiled patterns do not grow, and the saved checks explain about 40 MiB a day at
  most, so 16 to 95 MiB a day is unexplained, over instances that live up to 73 hours. The earlier notes said the patterns
  were most likely the larger part of it, and that is withdrawn.
  3 GiB costs reading ahead at most 187,488 GiB-seconds a month (52% of the free 360,000), where 2 GiB costs 124,992 (35%).
  The memory bound in test_cloudrun's reading-ahead test was raised from 0.35 to 0.55 for this, dated where it stands.
  Corrected on the way, in docs, comments and docstrings only. The 64 biggest general types' patterns are about 47 MiB
  measured (37.8 _inside_pattern, 5.6 _covering_pattern, 4.0 _covering_phrases), not 35 MB, and a floor, since Python's own
  re cache can hold patterns the cache let go. The 268 MB for _community_covers came from building it for types with no
  community names, which the code never does. Only 2 types have community names, about 1 KiB each. The pre-check job's
  figures read 913 MB on the computer and 1.47 GiB of its 3 on Cloud Run (19 Oct). bundle_items accepts a broken item that a
  later copy of the same thread overrides, where a parse of the whole file refuses it, which is harmless since the reading
  job writes the bundle with json.dumps of a dict. LiveChecker's old checks are let go in _bundle_data, through
  share_bundle, at most hourly and only when reading ahead has read something new, and nothing in production calls
  forget_old_checks. eval/site_memory's prep_cloud.py fixes the bundle's check ages when it is run, so a run more than about
  7 hours later loses those checks to the 48-hour rule, and the README says to run it again before each run.
  The whole suite under the heavy lock: 7,266 passed and the 1 known failure
  (test_library::test_real_gold_threads_saved_to_the_library_load_back, the unlabelled gold thread 1v40u3t), as before.
  No gcloud command was run, nothing was pushed or deployed, and no Monitoring alert was made. No eval/RUNS.md row, since
  this is a docs and config commit and no eval ran.
- 6 Nov 2026, the deploys (Claude, the orchestrator; Noemi's go-ahead of 5 Nov: merge and deploy once every gate
  passes). The makeup branch was merged as 2a9944b and deployed as revision 00080 at 4 GiB. The deploy pulled 4 blush
  threads read on demand and applied the pre-check's verification record (1,078 items of comments removed, edited or
  unreadable twice on Reddit dropped), which moved 10 answers' picks against the last review sweep, cream blush among
  them (now Patrick Ta, Milani baked blush and Haus Labs: the need-fit rule is still off). Live, all 19 checked requests
  (the 17 makeup answers and two others) gave 3 picks: NARS Orgasm under Also worth a look with its note and warnings,
  got2b tagged as a hair product with its note, ONE/SIZE without the misread warning. The site-memory branch was rebased
  onto it (one conflict in engine/on_demand.py: write_items keeps the removed-threads check), its suite passed (7,353,
  the known gold thread aside), and sweeps of main and of the branch on the same library were identical in all 295
  answers. It was merged as d12d0f1 and deployed as revision 00081 at 3 GiB. Its first minutes warmed slowly and
  visitors were told the site was busy for 8 minutes: the CPU sat at 10 to 40%, so the wait was for Reddit's embed
  reads (about 200 in 10 minutes), which the live check of 19 fresh makeup answers on 00080 had used up just before,
  and which a new instance has to read again for any check made since the bucket's last hourly share. The old code
  does the same. Answers came back in 1 to 11 s once the reads were back, and the pre-check job was run once at
  11:40 UTC so the makeup answers' quotes are checked ahead. Cloud Monitoring is read about an hour after the deploy
  and then daily, by the step-down rule above.
- 6 Nov 2026, on-demand reading doubled, with backfill and a free-tier guard (Claude, the builder, branch doubling from
  80ac0ab; Noemi, 5 Nov: "You can double (do it with random products if people don't research any), but make sure my
  claude usage for this week and in general stays under control", then "Let's do A"; Claude's technical calls, reported
  to her; not pushed, not merged, not deployed).
  The sources, each read on 6 Nov 2026. Cloud Run's pricing page (https://cloud.google.com/run/pricing): the free tier
  "is applied as a spending based discount using Tier 1 pricing", aggregated across projects by billing account, and it
  is the same money in every section: a job's (instance-billed) 240,000 vCPU-seconds at $0.000018 and 450,000
  GiB-seconds at $0.000002, and a request-billed service's 180,000 at $0.000024 and 360,000 at $0.0000025, are each
  $4.32 of CPU and $0.90 of memory. europe-west1 is Tier 1. So the site and both jobs share one pot per part, and the
  brief's check of separate allowances (its 98,000 seconds) doesn't hold. The site is request-billed (deploy.sh: no
  --no-cpu-throttling, --min-instances 0). Its startup CPU boost (https://cloud.google.com/run/docs/configuring/services/cpu,
  last updated 30 Oct 2026: a 1 vCPU service gets 2 while it starts and 10 s after) is billed, and Cloud Monitoring's
  cpu/allocation_time holds it. Cloud Monitoring's pricing (https://cloud.google.com/stackdriver/pricing): reading time
  series costs $0.50 a million series returned, the first million a month free per billing account, each call counting
  its series or one, whichever is more. The project's quota, read through the Service Usage API (read only), is 6,000
  time-series queries a minute. The metrics' real shape was read from Cloud Monitoring, read only, with gcloud's token
  (never printed): billable_instance_time in "s", cpu/allocation_time in "s{CPU}", memory/allocation_time in "GiBy.s",
  all DELTA and DOUBLE, by cloud_run_revision (service_name) and cloud_run_job (job_name). ALIGN_SUM with REDUCE_SUM over
  an alignment period as long as the window gives one point a service or job, and Cloud Monitoring's shortest period is
  60 s. Nothing in the cloud project was changed.
  The pot (engine/tests/test_cloudrun.py does these sums from deploy.sh's own flags; DEPLOY.md, Costs, The shared pot).
  By the hard caps, in a 31-day month: the pre-check at its 55 minutes every day is $1.84 of CPU and $0.41 of memory;
  reading ahead at its limit is $1.50 of CPU and $0.47 of memory with the site at 3 GiB ($0.31 at 2 GiB); together 77% of
  the CPU part and 98% of the memory part at 3 GiB (80% at 2 GiB). On-demand reading's 92,000 seconds add $1.66 and
  $0.18: 116% of CPU and 118% of memory at 3 GiB (101% at 2 GiB). Visitors' answers on the site have no cap. So, said
  plainly: the caps alone can't keep 10% in hand. At 3 GiB the memory part can't at any month seconds (it is past 90%
  before on-demand reading reads a second), and the CPU part could only with 30,372 seconds (44,160 on memory at 2 GiB),
  under even the 50,000 of before. Lowering the month seconds can't fix that, so the guard below keeps the margin at run
  time. The month's seconds were chosen on what was measured (Cloud Monitoring, summed by day; corrected in the fix round
  below, which found the builder had taken the pre-check's 19 days of October as its whole month): over the 20 days from
  17 Oct to 5 Nov 2026, scaled to a 31-day month, the site billed 52,223 s with 57,916 vCPU-seconds allocated (it came up
  on 12 Oct, and its first days were its busiest) and the pre-check 44,028 s (44,425 vCPU-s). At today's sizes, the site
  at 3 GiB and the pre-check at 2 GiB, that is $1.39 and $0.80 of CPU, and $0.39 (site; $0.26 at 2 GiB) and $0.18 of
  memory. The CPU part binds: the reader's month may be at most 94,353 s at 90% on these days (90,325 on the last 14
  days alone, 95,222 on the last 7), and ON_DEMAND_MONTH_SECONDS is 92,000: CPU 89.0%, memory 83.5% at 3 GiB and 69.0%
  at 2 GiB (the builder's figures on October were 89.6%, 79.6% and 65.0%). The told capacity follows: 73 a month at 21
  minutes (engine.on_demand.products_a_month; 39 before); the told wait (about 25 minutes) and the daily cap (450 calls)
  are unchanged. A busier month is the guard's to catch: at the last 30 days' pace (7 Oct to 6 Nov, with their deploys)
  the reader would have room for only about 65,650 s, so in such a month the guard stops reading before the told 73.
  The guard (engine/free_tier.py). Before every backfill read, and before any visitor read once visitors' own seconds of
  the month reach ON_DEMAND_GUARD_FREE_SECONDS (50,000, the month before the doubling; backfill's seconds never count
  toward them), the reading job asks it. It reads Cloud Monitoring with the job's own service account (the metadata
  server's token, no key file): billable_instance_time, cpu/allocation_time and memory/allocation_time, summed by
  service and by job over the month so far and over the last 7 days, 12 calls a reading. Spent so far: for the site and
  the two jobs, the CPU allocated, never under billable seconds times today's vCPUs, and the memory allocated, never
  under billable seconds times today's GiB; for the reader also never under the queue's own count of its seconds (Cloud
  Monitoring lags); for anything else on Cloud Run in the project, as allocated. The projection: spent so far, plus the
  days left at the last 7 days' pace at today's sizes (a service that stepped down in memory counts its old size for
  the days it ran at it and its new size from now; November's plain extrapolation from the 4 GiB days reads about 107%
  of memory, the projection at today's sizes about 85%), plus the read about to start (21 minutes at the reader's 1 vCPU
  and 1 GiB), priced as a service or a job at Tier 1. Yes only while each part is under 90% ($3.888 of CPU, $0.81 of
  memory). No on any failure, fail closed: no project (CREDIBLE_RECS_GCP_PROJECT, which on_demand.sh now gives the
  reader job), no token, any HTTP status but 200, a call that raises, an answer that isn't JSON, a second page, a unit or
  kind of value it doesn't expect, or a series missing for the site (either window) or the pre-check (the last 7 days,
  and the month once it is 6 hours old: the pre-check runs at 4 am UK time); since the fix round also a series without
  points, a value that isn't a number of 0 or more (NaN, infinity, below 0), a service or job in some of the three
  metrics but not all, and a projection that isn't a number. A reading is kept 10 minutes, a failed one never. A no, or
  a reading that failed, rests reading past the first 50,000 seconds for 6 hours (never past the month's end) and
  backfill for a day (the fix round; the builder had 6 hours for both, an hour after a failed reading), and a visitor
  is then told the free reading allowance is used up for now (capacity_text treats a "guard" rest as the month's). Its
  calls: only a run whose time counts in the month's seconds asks, at least a minute each since the fix round, so at
  worst about 1,700 readings a month x 12 calls x about 2 series is about 41,000 series, under a twentieth of the free
  million; a likely month about 7,000. deploy.sh grants the
  runtime service account roles/monitoring.viewer on the project, with on-demand reading on, before the reader job is
  deployed (`gcloud projects add-iam-policy-binding ... --condition=None`: adding a binding that is there changes
  nothing). The account had only roles/logging.logWriter and roles/run.builder at project level (read, 6 Nov 2026), so
  until the next deploy runs that line the guard can't read and says no: visitors' first 50,000 seconds still read as
  today, nothing past them and no backfill. deploy.sh wasn't run.
  Backfill (engine/on_demand.py, "Backfill"). The daily pre-check's plan run lists in the queue the requests whose
  answers are thin (Answer.needs_more_threads: fewer than 3 picks), one per product type, at most 200, with the same
  fields a visitor's entry keeps (product type, category, subreddits, up to 3 need words, the threads it had). When
  nothing waits and nothing rests, the site's keep-warm ping (at most hourly, ON_DEMAND_BACKFILL_EVERY_SECONDS) or the
  pre-check queues one, in a random order seeded by the day the list was made (random.Random("backfill <day>") over the
  entries sorted by key), never a product type queued or read in the last 30 days (for any need words), and the ping
  starts the job as for any request. No new Cloud Scheduler job. Visitors first: the job reads visitors' requests, and
  extracts their threads, before any backfill's; a visitor asking for the product a backfill waits on makes it theirs
  (read first, within visitors' month); a full queue (20) counts visitors only; a backfill read the running job has
  begun adds one request (21 minutes) to the wait a visitor is told. Backfill's own limits, checked before each read
  with this run's seconds counted: the month's time ("month"), at most 42,000 seconds a month (half the month, and never
  into visitors' 50,000: ON_DEMAND_BACKFILL_SECONDS, "half"), never more than its share of the days gone ("pace": paced
  evenly, so the first can start about 22 hours into a month), only while the day's Gemini calls leave 20 visitors'
  requests' worth (at most 135 of the 450 used, "gemini"), never while the bundle holds 150 threads or more not baked in
  ("bundle"), and then the guard. A backfill that can't start is taken off the queue and backfill rests until its limit
  lifts (the run goes on with visitors); forget-baked tells the queue the bundle's new count and ends a "bundle" rest.
  It reads from Arctic Shift only, as visitors' reads do (the library's own archive reader; no Bright Data), reads even
  when the library holds 6 threads about the type (an answer can be thin with many threads), closes with what it found
  rather than waiting for another try when the archive is busy, and its threads go through every usual check (each quote
  word for word at extraction, and live on Reddit within 48 hours before an answer shows it). Time is split by what each
  step took: a run that did only backfill counts wholly as backfill's, its start included; otherwise backfill's steps'
  seconds. The run's report logs each backfill read beside the visitors' (product type, minutes, Gemini calls), in the
  job's log and the queue's last_run; `python -m engine.on_demand status` shows backfill's hours and its list. No Claude
  at run time. The How page is unchanged (backfill shows visitors nothing but the wait above).
  Tests first, each failing before its change: engine/tests/test_free_tier.py (28) and test_on_demand_backfill.py (31),
  and in test_cloudrun.py the one-pot prices, the site's request billing, the guard's sizes and names against the
  deploy's flags, the doubled month on October's use, and the grant and the job's project. Changed on purpose, with dated
  notes: test_cloudrun.py's two free-tier tests (the jobs' sums and reading ahead's) now in the pot's dollars, with the
  hard caps' plain "can't"; test_approvals.py's told capacity, 39 to 73; a comment in test_on_demand_job.py.
  The whole suite passed on the branch: 7,415 passed and 3 skipped, none failed (2 min 52 s, under the heavy lock).
  Sweeps of eval/sweep.py's own requests and the interviewee, demo and makeup request files (293 requests) on main
  (80ac0ab) and on this branch, on the same library, were identical in all 293 answers, timings aside: the change
  touches no answer, and no swept answer tells the on-demand capacity.
  Left for Noemi (only she can decide): the guard sees this project only, while Google's pot is per billing account,
  which also pays for "My First Project" (no Cloud Run API there today); anything that starts using Cloud Run there
  would share the pot unseen. No eval/RUNS.md row: no evaluation ran (the engine's answers don't change).
  Fix round, 6 Nov 2026 (Claude, the fixer, after the gate, which failed on the guard failing open, and the code and
  cost reviews; Claude's technical calls, reported to Noemi; not pushed, merged or deployed). (1) Backfill could use up
  the room visitors' first 50,000 seconds need: they never ask the guard, and the guard counted a backfill read alone,
  so in a month where visitors came late every backfill could get a yes and the month still end past 90% (the reviews'
  sums: about 98.6% of CPU at this month's pace, past the free tier at the last 30 days'). A backfill read now asks the
  guard about itself and what is left of visitors' 50,000 this month together, at the reader's size. Read only against
  Cloud Monitoring at about 13:30 UTC with the fixed guard: one read alone is a yes (CPU 67%, memory 84%), with visitors'
  48,232 seconds still to come a no (memory 94%), so at this month's pace backfill doesn't run while the site is at
  3 GiB; it gets room once the site steps down to 2 GiB. (2) The guard said yes to answers it couldn't trust: a NaN
  value (the string or the JSON token), a series with no points (the site's or the pre-check's counted as nothing), a
  value below 0, or the site's billable series alone missing (its memory pace then nothing: the code review's probe
  turned a no into a yes). Now a series without points, a value that isn't a number of 0 or more, a service or job in
  some of the three metrics but not all, and a projection that isn't a number are failed readings, and every failure
  path has a test (the token raising, an answer that isn't an object, a kind that isn't DELTA, a missing label, an
  unreadable point, anything else raising inside the guard, no guard, a guard that raises). The fixed guard read real
  Cloud Monitoring without a failure. (3) After a no, or a reading that failed, the keep-warm ping started the paid job
  again whenever a rest ended (every hour after a failed reading), only for it to be refused, and runs that short were
  counted at half a minute where Google bills a job's run at least a minute and Cloud Monitoring shows about nothing.
  Now a no or a failed reading rests backfill a day and reading past visitors' 50,000 seconds 6 hours (never past the
  month's end), and a run that asks the guard or does anything for backfill counts at least 60 s (Cloud Run's pricing
  page, read 6 Nov 2026: jobs are billed "for the entire lifetime of any instance started, with a minimum of 1 minute");
  a visitor's run within their first 50,000 seconds counts as before. (4) The pot's measured month (the table above,
  DEPLOY.md and test_cloudrun.py) took the pre-check's 19 days of October as a month; it is now one window, 17 Oct to
  5 Nov, scaled to 31 days, for the site and the pre-check alike: 92,000 stays (89.0% of CPU; the builder's "the most to
  the thousand" no longer holds, since 94,000 would fit on this window but not on the last 14 days). Smaller fixes from
  the reviews: backfill's last read of the month starts only while a whole run (its 50-minute lease) still fits in its
  42,000 seconds, so a slow read never eats into visitors' 50,000; a backfill whose product type a visitor waits for or
  had read in the last 30 days (other need words) is dropped unread, as backfill_due already did when queuing; DEPLOY.md's
  bucket costs for the doubled month (under 0.03 USD) and the guard's reading sums (at worst about 1,700 readings and
  41,000 series a month: only runs whose time counts in the month's seconds ask). Tests first, each watched failing on
  the builder's commit (25 failed there) and each behaviour undone once in a scratch copy to see its test fail (23
  undone, all caught): test_free_tier.py 28 to 54, test_on_demand_backfill.py 31 to 46 (with tests for the builder's
  changes the gate found untested: backfill_due asking backfill's limits, a new month starting backfill's seconds from
  nothing, a request queued again starting afresh as whoever asks, backfill's no-retry rule, a backfill read though the
  threads suffice, the command line giving the job its guard, a guard rest told as the month's allowance), and
  test_cloudrun.py's measured month redone; three of the builder's tests changed on purpose with dated notes (the guard's
  extra seconds, backfill's rest, the measured month). The whole suite passed: 7,456 passed and 3 skipped, none failed
  (2 min 55 s, under the heavy lock). Left as they are, small and noted by the reviews: Google's
  billing month runs in US Pacific time while the queue and the guard count UTC months (backfill is paced out of a
  month's first day, so only visitors' first reads of the 1st, as on main, land in Google's previous month; about 1% of
  a part at worst. Corrected the same day: that was about ten times too low, since a rest woke at midnight UTC and the
  backlog read under visitors' fresh first 50,000 seconds, up to about 102% of the CPU part with the site at 2 GiB in
  the second cost review's simulation, and it is now fixed by the 08:00 UTC cut below); a visitor queued behind a
  backfill's threads left waiting for Gemini by a run cut short isn't told
  those minutes; "30 a day" is told on days backfill has used some calls; a backfill can take a thin type past 8
  threads (Gemini, not Claude, so CLAUDE.md's cost rule holds); the site's hourly backfill look holds its lock while it
  reads the bucket. No eval/RUNS.md row and no sweeps this round: nothing an answer, its told wait or its told capacity
  reads changed (the job's code, the guard and their tests only).
  Month boundary round, 6 Nov 2026 (Claude, after the fix round's second cost and code reviews, with the orchestrator's
  decision of one fixed cut: technical calls, reported to Noemi, not pushed, merged or deployed). Google's billing month
  runs on US Pacific time (Cloud Billing reports start a day at midnight US and Canadian Pacific Time), so it ends at
  08:00 UTC on the 1st in winter and 07:00 in summer, while the queue and the guard counted months from midnight UTC. A
  month rest, or a guard rest capped at the month's end, woke at midnight UTC and the backlog then read under visitors'
  fresh first 50,000 seconds, which never ask the guard, while Google still billed the old month (the second cost review
  simulated up to about 102% of the CPU part with the site at 2 GiB). Every month now turns at one fixed cut, 08:00 UTC
  on the 1st (config.BILLING_MONTH_CUT_HOUR_UTC, engine.free_tier.month_start, next_month and month_key), never earlier
  than Google's month end and with no time-zone data: the queue's month (a moment before the cut belongs to the month
  before), the month and guard rests, backfill's pacing and the guard's Cloud Monitoring window with its days left.
  Unchanged: visitors' 50,000 unguarded seconds a month (now Google's month), the told wait, the 450 Gemini calls (30
  requests) a day and the told 73 a month. Visitors are still told the 1st (08:00 UTC is the 1st in UK time too). A
  queue in the bucket written before the change is read without losing its seconds: mid-month its month is the same
  either way, a month that can't be read starts afresh as before and one written between midnight and 08:00 UTC on a
  1st is a month ahead and keeps its seconds (they count in the month they were written for) where a plain comparison
  would have started it afresh. One knock-on call: the daily pre-check runs at 4 am UK time, before the cut, so its
  first run in a month is now on the 2nd, and the guard requires its month series 22 hours after the cut (config
  FREE_TIER_PRECHECK_MONTH_HOURS: 2 or 3 hours after that run, as 6 hours from midnight were), the site's still 6.
  Counted from the cut at 6 hours, the guard would have failed closed every month from 14:00 UTC on the 1st until the
  pre-check ran on the 2nd. Left, small: in summer the cut comes an hour after Google's month ends, so reading in that
  hour (an hour of the reader at most, 1.5% of the CPU part) counts in our old month while Google bills its new one.
  Also tests for six behaviours the second code review found untested: a reading that fails its required series is
  never kept (swapped, the guard failed open), a refused backfill a visitor took over meanwhile stays theirs, a visitor
  read past 50,000 seconds asks the guard about one read's 1,260 seconds, only a backfill begun in this run counts in a
  visitor's told wait, this run's backfill seconds never count as visitors' and a backfill queued before backfill
  began resting is dropped unread with the rest kept. Tests first: the 7 month tests failed on 49c242f (the queue's
  month at 07:59 and 08:00 UTC on the 1st, a backlog left late on the last day by a month rest and by a guard rest read
  only after the cut, backfill paced from the cut, the guard's window from the cut, the site's month series required 6
  hours after the cut and the pre-check's 22). The old queue's test passed there, as it should. 13 behaviours undone
  once each in a scratch copy, all caught. test_free_tier.py 54 to 57, test_on_demand_backfill.py 46 to 56. Changed on
  purpose with dated notes, the tests that pinned midnight UTC: the month rest's wake (test_on_demand_job.py and
  test_on_demand_backfill.py), the guard rest capped at the month's end, november() for the pacing tests, the
  pre-check's hours, the guard's figures for 9 October at noon (72% and 93%, from 71% and 92%), backfill's seconds in
  one test (9,000, as 10,000 now passes its share) and test_free_tier.py's clock (08:00). The whole suite passed:
  7,469 passed and 3 skipped, none failed (2 min 53 s, under the heavy lock). No eval/RUNS.md row and no sweeps:
  nothing an answer, its told wait or its told capacity reads changed.
