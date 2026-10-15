# The live site on Google Cloud Run

Chosen on 12 Oct 2026 instead of a Hugging Face Space, which now needs a paid plan to run code. Cloud Run runs the site
in Noemi's own Google Cloud project (credible-picks), on the free tier: one server at most, none while nobody visits,
in europe-west1 (Belgium, the nearest free-tier region). A budget alert at 1 EUR warns long before anything is spent.

Since 13 Oct 2026 (Noemi's decision: "check ahead") the comments answers would show are read ahead (engine/precheck.py).
Before an answer shows a quote, the comment is read live on Reddit's embed page, and Reddit allows about 200 such reads
in 10 minutes from one address, so a fresh answer (20 to 40 reads) could wait a minute or two. Reading them ahead,
visitors' answers find them already checked. The rule is unchanged: a quote is shown only with a passing check from the
last 48 hours.

Since 14 Oct 2026 (the free-tier redesign, "Who reads ahead" below) the site does the reading ahead itself, a few
comments each time the keep-warm ping asks it, and the daily pre-check job only works out what to read and leaves the
site a plan: a job is billed for its whole run, and two thirds of the old daily run went on waiting for Reddit.

## What lives where

- **The image** (the code, the saved library of Reddit threads, the open model): private, in the project's own
  Artifact Registry. Built by Cloud Build from a bundle made on Noemi's computer (deploy/cloudrun/make_context.py), so
  the library is never in this public repository and never public anywhere.
- **The live checks' bucket** (`credible-picks-live-checks`, CREDIBLE_RECS_LIVE_CACHE_BUCKET): four objects.
  - `live_check/bundle.json`: what Reddit's embed page said about each comment read in the last 48 hours (its text and
    when it was read, nothing else; about 3 MB once the site reads ahead), a page that showed no comment included (used
    for 20 hours, known for 48). Written by the site, at most once an hour and only over the version it last read or
    wrote (another writer's, say a second server during a deploy, is read in first); read by the site as it gets ready
    (its disk starts empty at every restart) and by the daily job as it starts.
  - `live_check/plan.json`: what the site should read ahead, from the daily job: the links of the comments answers would
    show or hold next in line, likeliest first; the links of the slimmed library's kept comments due to be verified; and
    the job's checks through Bright Data. The site asks for its version at most once an hour (a small metadata read) and
    downloads it only when it changed.
  - `live_check/verified.json`: the verification record (below).
  - `live_check/bright_data.json` (14 Oct 2026): the threads the job's Bright Data step couldn't read lately, since each
    of its runs starts with an empty disk: for each, when, Bright Data's status and error ("ready: dead_page: Page not
    reachable"), whether the post itself is gone, and then the ids of the comments that needed it. Ids, dates and
    Bright Data's words only, a few dozen entries (under 25 KB for 100). Written by the job after each thread that fails
    and at the end of every run that holds any (so the 2-day rule never removes it while the job runs), read as it
    starts.
  Private: uniform bucket-level access, public access prevention, readable and writable only by the project's compute
  service account (the site and the jobs run as it). In europe-west1. Every object is deleted once it is 2 days old
  (deploy/cloudrun/live_cache_lifecycle.json; Google runs these deletions about once a day, so one can stay up to a day
  longer, unused; each is written again every day or hour, so it goes only if what writes it stops), and soft delete is
  off, so nothing deleted is kept. No check older than 48 hours is ever written into the bundle, copied out of it or used.
- **The pre-check** (Cloud Run job `credible-recs-precheck`): the site's own image, running
  `python -m engine.precheck --plan --minutes 30`, started by Cloud Scheduler (`credible-recs-precheck-daily`) at 4 am UK
  time; since 14 Oct 2026 it reads nothing on Reddit's embed page itself. It reads the bundle, records in the
  verification record what each of the site's reads of a kept comment said, works out the comments answers would show
  (2,260 from 439 requests on a copy of 14 Oct 2026's library, slimmed: the whole plan run took 2.1 minutes on Noemi's
  computer; the old run's working out took 84 s on Cloud Run for 1,967) and the kept comments due (oldest first, at most 3,000 a day: config.LIBRARY_VERIFY_READS, the answers'
  own left out), and writes the record and the plan. Then, for the comments whose embed page shows no comment ("Not
  supported comment", about 1 in 8; Noemi, 13 Oct 2026: "Use Bright Data"), it reads their threads through Bright
  Data, within 30 records a run (the most useful threads first), starting nothing 30 minutes after it started, and
  writes the plan again with a check for each comment it found there. A thread Bright Data couldn't read is left for 7
  days (config.PRECHECK_BRIGHT_DATA_SKIP_DAYS), so the next run's records go to the next threads (until 14 Oct 2026's
  evening each run chose, and failed on, the same two); one whose post is gone (removed, deleted, its page no longer
  there) holds comments that can't be verified that way: they are taken as unverifiable for 30 days (no record spent on
  them again), and the plan reads what answers show instead. The report names each thread that couldn't be read, with
  Bright Data's status and error. It needs the Bright Data key, the Secret
  Manager secret `bright-data-key` (below; there since 14 Oct 2026): deployed without it, the job runs with this step
  off. The site never calls Bright Data. Cloud Run stops a run at 55 minutes (45 until 14 Oct 2026's evening, when a
  Bright Data job, waited for up to 20 minutes since, had been cut off at 10). Its report (counts and times, never a
  comment's words) is in the job's logs.
- **The site's reads ahead** (engine/read_ahead.py, 14 Oct 2026): at each keep-warm ping (every 5 minutes, below) the
  site reads the plan's comments that are due: an answer's comment once its last read is 40 hours old (so its check
  never runs out at 48 hours), or that has none; a comment to verify not read in the last 48 hours. At most 40 a ping, 4
  at once, none starting 5 seconds after the ping began, never a read that would wait for Reddit's allowance, and none
  while Reddit says fewer than 120 reads are left in its 10 minutes (those are visitors' answers'). Each ping's counts
  are in the site's logs ("Reading ahead: ...").
- **The verification record** (`live_check/verified.json`, in the same bucket): for each comment the slimmed library
  keeps, its latest read on Reddit (when, and what it said: passing, deleted, removed, edited or unreadable) and its
  last passing read. Ids, dates and outcomes only, never a comment's words (about 1 MB for 10,000 comments). Written by
  the daily job from the reads the site shared (each is in the bundle for 48 hours, so a run a day sees every one), and
  read by deploy.sh before it bundles the library. Like every object in the bucket it is deleted once 2 days old, but
  it is written again every day: it goes only if the job stops for two days, and then the library's own dates (as of
  the last deploy) are the record, so nothing unverified is ever kept longer, only verified comments are read again.
- **On-demand reading's bucket** (`credible-picks-on-demand`, CREDIBLE_RECS_ON_DEMAND_BUCKET; 14 Oct 2026, Noemi's plan,
  part 3; engine/on_demand.py): two objects. `on_demand/queue.json`, the requests the library couldn't answer yet: for
  each, only the product type module 1 understood, its category and subreddits and up to 3 of its need words (never
  the request as typed, never a time or anything about the visitor), and the reading job's own state (its lease, its
  time this month, its Gemini calls today). `on_demand/threads.json`, the bundle of the threads the job has read and
  not yet baked into the image: each thread's file and its extraction's, as the library saves them. Private like the
  live checks' bucket (uniform access, public access prevention, soft delete off, europe-west1), readable and writable
  by the project's compute service account only. A separate bucket because its objects must outlive the live checks'
  2 days: every object is deleted once 37 days old (deploy/cloudrun/on_demand_lifecycle.json, the archive's keeping
  time), and every deploy empties the bundle of what the new image holds.
- **The reading job** (Cloud Run job `credible-recs-reader`): the site's own image, running `python -m engine.on_demand
  run`. No schedule of its own: the site starts it (Cloud Run's jobs:run) as soon as it queues a request, and the
  keep-warm ping starts it again when a start failed. For each waiting request it finds threads with Arctic Shift's
  free title search and reads them from its archive (the library's own archive reader, at its 10 s pace; no Bright
  Data, no Parse), has Gemini extract each within the free allowance, checks every quote word for word, slims them when
  the lean library is there, and adds them to the bundle; the site takes them in within 5 minutes. Its one secret is
  the Gemini key (`gemini-key`, below).
- **Feedback**: Noemi's private Hugging Face dataset Noemix/credible-recs-feedback. The site uploads it in batches with
  the token stored as the Secret Manager secret `hf-token`.
- **Visit counts**: GoatCounter, site code noemix (CREDIBLE_RECS_GOATCOUNTER).
- **Settings** the site reads: CREDIBLE_RECS_ALLOWED_HOSTS (the site's own addresses), CREDIBLE_RECS_GOATCOUNTER,
  CREDIBLE_RECS_FEEDBACK_REPO, CREDIBLE_RECS_LIVE_CACHE_BUCKET, CREDIBLE_RECS_ON_DEMAND_BUCKET and
  CREDIBLE_RECS_ON_DEMAND_JOB (`projects/credible-picks/locations/europe-west1/jobs/credible-recs-reader`, the job it
  starts; without it the site queues nothing); the secret HF_TOKEN. The site reads ahead when it has the live checks'
  bucket. The pre-check job reads
  CREDIBLE_RECS_LIVE_CACHE_BUCKET, CREDIBLE_RECS_ON_DEMAND_BUCKET, CREDIBLE_RECS_PRECHECK_BRIGHT_DATA ("off" when it was
  deployed without the Bright Data key) and the secret BRIGHT_DATA_API_KEY; the reading job
  CREDIBLE_RECS_ON_DEMAND_BUCKET and the secret GEM_API_KEY.

## Who reads ahead (14 Oct 2026, the free-tier redesign)

The daily job read ahead itself until 14 Oct 2026: 75 minutes of reads a day, plus up to 11 waiting for Reddit's next
10 minutes, about 80% of it asleep between reads (Reddit's embed pages answer about 200 reads in 10 minutes from one
address), and a job is billed for all of it: 161,820 vCPU-seconds a month, 88% of the jobs' free tier with on-demand
reading's 50,000, while about 5,200 reads a day were wanted once the slimmed library is verified (the answers' 2,229
comments and 3,000 kept comments). Compared on cost (vCPU-seconds a month, worst month), visitors' waits, simplicity
and the 48-hour rule:

- (a) the site reads at the keep-warm ping, the job only works out the plan (chosen). The site is billed only while
  it answers, and the ping comes every 5 minutes anyway: reads ahead at most 53,568 of the site's own 180,000 (30%;
  about 7% for today's 4,340 reads a day), the job at most 102,300 (43%; 63% with on-demand's). Visitors keep 120 of
  Reddit's 200 reads in each 10 minutes, and answers' checks are read again every 40 hours, so they never run out.
  Two more bucket calls an hour for the site. No new Cloud Scheduler job.
- (b) several short job runs a night, from a list the first run stores. Each run still pays for its start (about a
  minute with the image and the library) and Reddit's 200 reads in 10 minutes cap each one, so 5,200 reads a day are
  about 28 runs, roughly 30 to 60 minutes a day: 52,000 to 117,000 vCPU-seconds, plus the planning run and on-demand's
  about 110,000 to 190,000 (45% to 80%), growing with every read, and the last free Cloud Scheduler job used. Checks
  read at night only, 20 to 30 hours old by evening.
- (c) lower tiers read less often (the comments behind the picks every other day). Saves about 370 reads a day of a
  daily run's, but the run is paid by its minutes, which Reddit's pace sets, and verifying the slimmed library needs
  the reads anyway. Folded into (a) as its order: what is likeliest to be shown is read first, so when reads run short
  the least likely wait.
- (d) others, not taken: Reddit's API reads up to 100 comments a call (`api/info`), but it is Reddit's Data API, whose
  terms need an approved app (Reddit never answered Noemi's request), not the embed widget she approved; a fixed
  address for the jobs (Cloud NAT) costs money; a free GitHub Actions schedule would run in a public repository's logs
  with Reddit's text passing through someone else's machines; Noemi's computer isn't always on.

## Updating the site

After committing (and after new threads are extracted), from the repository's root:

    sh deploy/cloudrun/deploy.sh

It turns on-demand reading off for that deploy if the Gemini key's secret isn't there yet (below; the site deploys
anyway and never says it has started reading), and the pre-check's Bright Data verification off if the Bright Data
key's isn't (the job deploys anyway), makes sure both buckets exist with their rules,
brings the threads read on demand into data/library, applies the pre-check's verification record to the
library, bundles the current commit with the library, builds the private
image and deploys the site, then points the pre-check job and the reading job at the same image, makes sure the daily
schedule exists, lets the on-demand bucket go of the threads the image now holds, and prints the address. Safe to run
again: each step creates what is missing and sets again what is there.

The first deploy with the site reading ahead (14 Oct 2026): run the job once after it (below, "To run the pre-check at
once"), so the site has a plan at once rather than after 4 am; until then the checks the old job left (48 hours) and
visitors' own reads cover the answers.

## The slimmed library (Noemi, 13 Oct 2026: "Keep only comments we use")

Each extracted thread keeps its title and only the comments answers use (`python -m engine.library slim`,
engine/slim.py); every other comment keeps its id, date, score and replies, never its words or writer. Each kept
comment must be verified on Reddit (its embed page, free) within 30 days, or it loses its words and its mentions
(engine/verify.py). The library is baked into the image, and the checks happen in the cloud, so the two meet at each
deploy:

1. every day the pre-check job lists in its plan the kept comments verified longest ago (3,000), the site reads them
   over the day (its reads ahead), and the next run records what each read said in `live_check/verified.json`;
2. `deploy.sh` copies that record to a temporary file (`gcloud storage cp`) and runs
   `python -m engine.library apply-checks --ledger <it>` before bundling: each passing comment gets its date, and a
   comment found deleted or edited, or not verified within 30 days, loses its words and its mentions, in
   data/library on this computer; the image built next holds the result. With no record yet (before the pre-check's
   first run), this computer's checks of the last 48 hours and the 30-day deadline are applied alone.

So deploy at least every couple of weeks: the image keeps what the last deploy applied, and a comment the pre-check
finds deleted is dropped from the image at the next deploy (until then answers never show it: every quote shown is
checked live within 48 hours). After a data round, once the new threads' extractions are final, slim them
(`python -m engine.library slim`; `--dry-run` first says what it would do): a thread not slimmed yet stays whole and
under the whole-thread rules (read again monthly through Bright Data, its text removed at 37 days if not).

To catch up by hand (say the pre-check stopped for a while): run it on this computer (without --plan it reads Reddit
itself, at Reddit's pace) with a bigger verification budget, then apply its record (it is kept in .cache/verified.json):

    .venv/bin/python -m engine.precheck --limit 0 --verify 2000
    .venv/bin/python -m engine.library apply-checks

A comment verification dropped can be given its words back while the backup made before slimming is kept (15 Oct
2026: until 21 Oct, the deletion rule), but only when Reddit still shows it word for word: the command reads each one
again on the embed page and puts back only those that pass (its words, writer and items from the backup, today's read
as its verification, so the next deploy keeps it), and says what Reddit shows of the others (`--dry-run` first):

    .venv/bin/python -m engine.library restore-words --backup ~/credible-recs-backups/library-before-slim-20261014-2211.tgz --dry-run <thread>:<comment> ...

`extract check` names a reply whose product source lost its words: "which was edited on Reddit since it was read" or
"which wasn't verified on Reddit within 30 days" for a source verification dropped (since 15 Oct 2026; earlier drops
say "whose words aren't kept in the library", as a source slimming didn't keep would, which no thread has).

### The commands it runs, in order

The project number is `NUMBER` below (`gcloud projects describe credible-picks --format='value(projectNumber)'`), and
`RUNNER` is the account the site and the job run as, `NUMBER-compute@developer.gserviceaccount.com`.

0. The two keys' secrets, which Noemi creates herself ("The Gemini key" and "The Bright Data key" below). The script
   never makes or reads them; it only checks they are there, and without one it deploys anyway with that piece off:
   on-demand reading without the Gemini key, the pre-check's Bright Data verification without the Bright Data key
   (14 Oct 2026: a missing key never stops a deploy):

       gcloud secrets describe gemini-key --project credible-picks
       gcloud secrets describe bright-data-key --project credible-picks

1. The APIs: `gcloud services enable storage.googleapis.com cloudscheduler.googleapis.com secretmanager.googleapis.com
   --project credible-picks`
2. The bucket, the first time only:

       gcloud storage buckets create gs://credible-picks-live-checks --project credible-picks --location europe-west1 \
           --uniform-bucket-level-access --public-access-prevention --soft-delete-duration 0 \
           --lifecycle-file deploy/cloudrun/live_cache_lifecycle.json

   then, every time, its rules set again and the service account let in (read, write and delete objects only):

       gcloud storage buckets update gs://credible-picks-live-checks --project credible-picks \
           --public-access-prevention --clear-soft-delete --lifecycle-file deploy/cloudrun/live_cache_lifecycle.json
       gcloud storage buckets add-iam-policy-binding gs://credible-picks-live-checks --project credible-picks \
           --member serviceAccount:RUNNER --role roles/storage.objectUser

   and the same for on-demand reading's bucket, with its own rules (every object deleted once 37 days old):

       gcloud storage buckets create gs://credible-picks-on-demand --project credible-picks --location europe-west1 \
           --uniform-bucket-level-access --public-access-prevention --soft-delete-duration 0 \
           --lifecycle-file deploy/cloudrun/on_demand_lifecycle.json
       gcloud storage buckets update gs://credible-picks-on-demand --project credible-picks \
           --public-access-prevention --clear-soft-delete --lifecycle-file deploy/cloudrun/on_demand_lifecycle.json
       gcloud storage buckets add-iam-policy-binding gs://credible-picks-on-demand --project credible-picks \
           --member serviceAccount:RUNNER --role roles/storage.objectUser

3. The threads read on demand into data/library (through gcloud's own sign-in; when it fails, the deploy goes on and
   the site still finds them in the bucket):

       CREDIBLE_RECS_ON_DEMAND_BUCKET=credible-picks-on-demand .venv/bin/python -m engine.library pull-bucket

   Then the verification record applied to the library (13 Oct 2026), before it is bundled:

       gcloud storage cp gs://credible-picks-live-checks/live_check/verified.json <a temporary file>
       .venv/bin/python -m engine.library apply-checks --ledger <that file>

   (with no record there yet, `apply-checks` alone). Then the site, as before, with `CREDIBLE_RECS_LIVE_CACHE_BUCKET=credible-picks-live-checks`,
   `CREDIBLE_RECS_ON_DEMAND_BUCKET=credible-picks-on-demand` and
   `CREDIBLE_RECS_ON_DEMAND_JOB=projects/credible-picks/locations/europe-west1/jobs/credible-recs-reader` in its settings
   (`gcloud run deploy credible-recs --source <bundle> ...`).
4. The job, on the image the site now runs (create or update), running the plan (14 Oct 2026), allowed to read the
   Bright Data key (when its secret isn't there: no grant, `CREDIBLE_RECS_PRECHECK_BRIGHT_DATA=off` and
   `--clear-secrets` instead of `--set-secrets`):

       gcloud secrets add-iam-policy-binding bright-data-key --project credible-picks \
           --member serviceAccount:RUNNER --role roles/secretmanager.secretAccessor
       IMAGE=$(gcloud run services describe credible-recs --region europe-west1 --project credible-picks \
           --format='value(spec.template.spec.containers[0].image)')
       gcloud run jobs deploy credible-recs-precheck --project credible-picks --region europe-west1 --image "$IMAGE" \
           --command python --args=-m,engine.precheck,--plan,--minutes,30 \
           --tasks 1 --max-retries 0 --task-timeout 55m --memory 3Gi --cpu 1 \
           --set-env-vars CREDIBLE_RECS_LIVE_CACHE_BUCKET=credible-picks-live-checks,CREDIBLE_RECS_ON_DEMAND_BUCKET=credible-picks-on-demand,CREDIBLE_RECS_PRECHECK_BRIGHT_DATA=on,CREDIBLE_RECS_QUERY_MODEL=off \
           --set-secrets BRIGHT_DATA_API_KEY=bright-data-key:latest
       gcloud run jobs add-iam-policy-binding credible-recs-precheck --project credible-picks --region europe-west1 \
           --member serviceAccount:RUNNER --role roles/run.invoker

   and the reading job on the same image (deploy/cloudrun/on_demand.sh), allowed to read the Gemini key, and startable
   by the account the site runs as:

       gcloud secrets add-iam-policy-binding gemini-key --project credible-picks \
           --member serviceAccount:RUNNER --role roles/secretmanager.secretAccessor
       gcloud run jobs deploy credible-recs-reader --project credible-picks --region europe-west1 --image "$IMAGE" \
           --command python --args=-m,engine.on_demand,run \
           --tasks 1 --max-retries 0 --task-timeout 45m --memory 1Gi --cpu 1 \
           --set-env-vars CREDIBLE_RECS_ON_DEMAND_BUCKET=credible-picks-on-demand,CREDIBLE_RECS_QUERY_MODEL=off \
           --set-secrets GEM_API_KEY=gemini-key:latest
       gcloud run jobs add-iam-policy-binding credible-recs-reader --project credible-picks --region europe-west1 \
           --member serviceAccount:RUNNER --role roles/run.invoker

5. The schedule (`create` the first time, `update` after):

       gcloud scheduler jobs create http credible-recs-precheck-daily --project credible-picks --location europe-west1 \
           --schedule "0 4 * * *" --time-zone "Europe/London" --http-method POST \
           --uri https://europe-west1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/credible-picks/jobs/credible-recs-precheck:run \
           --oauth-service-account-email RUNNER

6. Once the site runs the new image, the on-demand bucket lets go of the threads it now holds (written only over the
   version read, so a thread the job adds meanwhile stays):

       CREDIBLE_RECS_ON_DEMAND_BUCKET=credible-picks-on-demand .venv/bin/python -m engine.library forget-baked

To run the pre-check at once (the first time, say) instead of waiting for 4 am:

    gcloud run jobs execute credible-recs-precheck --region europe-west1 --project credible-picks

and to see its report: `gcloud run jobs executions list --job credible-recs-precheck --region europe-west1` then the
execution's logs in the console (Cloud Run, Jobs, credible-recs-precheck, Logs).

Reddit's limit is per address, and since 14 Oct 2026 the site's reads ahead share it with visitors' answers: at two
pings in Reddit's 10 minutes they take at most 80 of its 200, and none while fewer than 120 are left, so three fresh
answers' worth (an answer reads 10 to 40 comments) stays for visitors. The site's other reads (on-demand reading's
archive, the bucket) aren't Reddit's.

## On-demand reading

Since 14 Oct 2026 (Noemi: "I want recs regardless of the category"; the plan's part 3). A request module 1 understands,
about a product the library holds fewer than 6 extracted threads about, is queued, and the answer says so in the
page's words, for example "We haven't read Reddit about teapots yet, so we've started: check back in about 20 minutes."
(15 more minutes for each request ahead of it; "taking longer than usual" after 90 minutes; and when the free
allowance is used up, when it is back). That answer isn't remembered: the next ask works it out again. The site starts
the reading job at once, and at every keep-warm ping while a request waits it asks the bundle's version (one small
read, a download only when it changed), takes the new threads into its library folder and answers with them, every
quote shown checked live on Reddit as always. The daily pre-check takes them in too and checks their answers ahead.

To see the queue (on Noemi's computer, through gcloud's sign-in; counts and product types only):

    .venv/bin/python -m engine.on_demand status

To run the job by hand (it does nothing when no request waits): `gcloud run jobs execute credible-recs-reader --region
europe-west1 --project credible-picks`; its report (counts and product types, never a comment's words) is in its logs
(Cloud Run, Jobs, credible-recs-reader, Logs).

The job's limits, all in engine/config.py ("On-demand reading"): it starts no new reading after 15 minutes of a run and
stops at 45; its runs read for at most 50,000 seconds a month (then the queue rests until the 1st); it makes at most 100
Gemini calls a day of the free allowance, leaving the rest to Noemi's own bulk reading, and none more that day after
Gemini's daily 429 (until 8 am UTC, when the allowance is surely back); at most 20 requests wait at once (10 until
14 Oct 2026: with the general category most requests queue; 20 is about two days of the job's reading, and the
sums below don't change, since the job's time and Gemini calls have caps of their own); a request
whose archive search fails is tried again an hour later and set aside for a day after 3 tries; a product read once is
read again only after 30 days, if its library is still thin then.

## The Gemini key

The reading job reads the key from the environment (GEM_API_KEY), which Cloud Run fills from the Secret Manager secret
`gemini-key`. Noemi creates it once, from the repository's root on her computer, with the key taken from her .env by
the project's own reader and handed straight to gcloud, never shown on screen or kept anywhere else (in Belgium, like
the rest):

    .venv/bin/python -c "import sys; from pathlib import Path; from engine.parse_reddit import _read_env_file; sys.stdout.write(_read_env_file(Path('.env'))['GEM_API_KEY'])" | gcloud secrets create gemini-key --project credible-picks --replication-policy user-managed --locations europe-west1 --data-file=-

When the key changes: the same command with `gcloud secrets versions add gemini-key --project credible-picks
--data-file=-` after the pipe. deploy.sh never makes or reads it: it only checks it is there, and leaves on-demand reading
off for that deploy when it isn't (14 Oct 2026: a missing key must not stop the site's own deploys). Free use only: Noemi's key is on Gemini's free tier, and under Google's terms UK users' free use
gets the paid-tier data terms (not used for training).

## The Bright Data key

The pre-check reads the key from the environment (BRIGHT_DATA_API_KEY), which Cloud Run fills from the Secret Manager
secret `bright-data-key`. The secret exists: it was created on 14 Oct 2026, with Noemi's go-ahead, with the command
below (version 1, in Belgium like the rest), the key taken from her .env by the project's own reader and handed
straight to gcloud, never shown on screen or kept anywhere else. To create it again (if it were ever deleted), from
the repository's root on her computer:

    .venv/bin/python -c "import sys; from pathlib import Path; from engine.parse_reddit import _read_env_file; sys.stdout.write(_read_env_file(Path('.env'))['BRIGHT_DATA_API_KEY'])" | gcloud secrets create bright-data-key --project credible-picks --replication-policy user-managed --locations europe-west1 --data-file=-

When the key changes: the same command with `gcloud secrets versions add bright-data-key --project credible-picks
--data-file=-` after the pipe. deploy.sh never makes or reads it: it only checks it is there, and when it isn't, it
deploys the job with its Bright Data verification off (`CREDIBLE_RECS_PRECHECK_BRIGHT_DATA=off`, no secret given to the
job, no access granted) and says so in one line (14 Oct 2026: a missing key never stops a deploy); each run's report
then says the step is off. Secret Manager's free tier covers it (6 secret versions and 10,000 reads a month: the job
reads it once a run).

## Keeping it awake

A server that has slept takes about a minute to get ready (engine/web.py's warm_up: 65 s on 13 Oct 2026), and Cloud
Run sends it visitors only once its /ready says so (deploy.sh's startup probe). So a Cloud Scheduler job asks /ready
every 5 minutes, and a visitor never waits for one to start. It was set up once (13 Oct 2026) with:

    gcloud services enable cloudscheduler.googleapis.com --project credible-picks
    gcloud scheduler jobs create http credible-recs-keep-warm --project credible-picks --location europe-west1 \
        --schedule "*/5 * * * *" --time-zone "Europe/London" --http-method GET --attempt-deadline 300s \
        --uri "https://credible-recs-446702383157.europe-west1.run.app/ready"

`gcloud scheduler jobs pause credible-recs-keep-warm --location europe-west1` stops it. Since 14 Oct 2026 the ping also
drives the site's reads ahead (engine/read_ahead.py): paused, they stop too, the checks run out within 48 hours, and
visitors' answers read what they need themselves, as before check ahead.

## Costs

The free tier covers our traffic (Cloud Run: 180,000 vCPU-seconds, 360,000 GiB-seconds and 2 million requests a
month). The image is about 1.5 GB in Artifact Registry, whose free storage is 0.5 GB: about 0.10 EUR a month for the
rest. Cloud Scheduler's first 3 jobs are free; a ping is one short request, and a server between requests costs
nothing. The budget alert emails Noemi at 50% and 100% of 1 EUR.

The pre-check (14 Oct 2026, the free-tier redesign; engine/tests/test_cloudrun.py does these sums from deploy.sh's own
settings). A job is billed per instance-second for its whole run, waiting included, so it runs with the least that
works: 1 vCPU (a job's minimum) and 3 GiB, with module 1's open model off (15 Oct 2026: with ~2,000 threads it ran out
of memory at 1.5 and at 2 GiB; working out the 486 requests peaked at 2.97 GB with the model and 2.25 GB without on
Noemi's computer, and the rules place 484 of them; on 13 Oct, with 436 threads, it had peaked at 1.3 GB with the model;
0.2 GB without it, but without the model the open model's product types would not be checked ahead). It no longer
waits for Reddit: a run is working out the answers (the whole plan run took 2.1 minutes on Noemi's computer for 439
requests on 14 Oct 2026's library, slimmed; the old run's working out took 84 s on Cloud Run), the record and the plan, then Bright Data's batch (a few minutes on Bright Data's side
when there is something to read), so a typical run should take 5 to 10 minutes, 9,300 to 18,600 vCPU-seconds a month
(an estimate: the first runs' logs will say; the first, on 14 Oct 2026, took 32 minutes, 29 of them waiting on Bright
Data's two jobs, both cut off at the then 10-minute wait). Its bound is Cloud Run's 55-minute task timeout: 3,300
seconds a day, 102,300 in a 31-day month, 102,300 vCPU-seconds and 306,900 GiB-seconds, 43% and 68% of the free tier for
instance-billed work (240,000 vCPU-seconds and 450,000 GiB-seconds a month), where the old run's 87 minutes a day were
161,820 and 242,730 (67% and 54%). So 0 EUR. If a run's log says the memory limit was exceeded, 2 GiB (`--memory 2Gi`)
is still inside the free tier: 167,400 GiB-seconds, 37%. The schedule is the second of Cloud Scheduler's 3 free jobs
(the keep-warm ping is the first); the redesign adds none.

The site's reads ahead (14 Oct 2026). The site is billed by request, under its own free tier (180,000 vCPU-seconds and
360,000 GiB-seconds a month): only while it answers, and a read ahead runs inside the keep-warm ping's request, 4 at
once, each mostly waiting on Reddit's answer (about 0.3 s), so about a tenth of a second of the site's time a read. A
ping starts no read 5 seconds after it began, so at most about 6 seconds a ping with the last reads' answers: 288 pings
a day, at most 53,568 vCPU-seconds and 107,136 GiB-seconds in a 31-day month on the site's 1 vCPU and 2 GiB, 30% of
each. Since 15 Oct 2026 the site runs at 4 GiB, a stopgap: at 2 GiB it ran out of memory every 20 to 40 minutes with
~1,950 threads, the open model and its warmed answers, so reading ahead's GiB-seconds are at most 214,272 (60%) until
the site's memory is brought back down. What is due on 14 Oct 2026's library, slimmed (17,335 kept comments): the answers' 2,229 comments once every 40
hours (about 1,340 a day) and up to 3,000 kept comments to verify, about 4,340 reads a day, 15 a ping, about 1.5
seconds of each: about 13,400 vCPU-seconds a month, 7%. 12,356 of the kept comments were never verified (read from the
archive on 11 to 14 Oct, so due by 10 to 13 Nov), about 31,000 once the 846 threads still to extract are slimmed: 11
days at 3,000 a day, oldest first. With the whole library extracted (about 36,000 kept comments) the reads stay the
same (the 3,000 a day are the budget; each kept comment is then read every 12 days, well inside the 30-day deadline).
4,340 reads a day are 38% of what the pings may read (40 a ping, 11,520 a day). Finding what is
due takes about a millisecond a ping (each comment's last read is kept in memory, read from the folder in 0.3 s once a
day as the new plan comes in).

Container images (14 Oct 2026). Each deploy stores the site's image in Artifact Registry (the repository `cloud-run-source-deploy`, which `gcloud run deploy --source` makes): about 1.15 GB, most of it the open model the build downloads. Its free tier is 0.5 GB of storage, then about 0.10 USD per GB a month. By the evening of 14 Oct 44 images had grown to 51 GB (about 4.60 EUR a month); Noemi chose to keep only the newest one, so the other 43 were deleted that evening and deploy.sh applies a cleanup policy after each deploy (image_cleanup_policy.json: keep the newest version, delete every other; Google runs it about once a day). One image costs about 0.07 EUR a month. An older site version can't be rolled back to once its image is gone: rebuild it from its commit instead. To bring storage under the free 0.5 GB, the model would have to leave the image (downloaded as the server starts, about 20 s slower starts): not done.

On-demand reading (estimates, 14 Oct 2026; 0 EUR). The reading job is billed like the pre-check, per instance-second
for its whole run, waiting included, on 1 vCPU and 1 GiB. One product takes about 12 minutes: about 6 minutes of
Arctic Shift at its 10 s pace (20 title searches and about 15 reads for a kitchen type with no title words of its own,
fewer for most), about 5 for Gemini (about 9 calls for 6 threads read in parts of 40 comments, each paced 6 s apart),
and half a minute to start. Its runs are capped at 50,000 s a month (about 70 products), so the worst month is 50,000
vCPU-seconds and 50,000 GiB-seconds; with the pre-check's at most 102,300 and 306,900 (15 Oct 2026, at 3 GiB; 83,700
and 125,550 that afternoon, 161,820 and 242,730 before), 152,300 of the free 240,000 vCPU-seconds (63%; 88% before) and
356,900 of the free 450,000 GiB-seconds (79%).
There are no empty runs: nothing is scheduled,
the job runs only when a request waits. Cloud Scheduler: no new job (the site starts the reading job, and the keep-warm
ping starts it again when a start failed), so still 2 of the 3 free jobs. Gemini: free tier only, at most 100 calls a
day by the job (about 10 products), stopping at Gemini's own daily limit. Secret Manager: a third secret (gemini-key,
with hf-token and bright-data-key), inside the free 6 secret versions, and the job reads it once a run (free: 10,000
reads a month). Arctic Shift: free, at its own pace. Starting a job (Cloud Run's Admin API): free. Sending threads to
Gemini is the only traffic out of Google: about 0.25 MB a product, about 17 MB in a capped month, about 0.002 USD.
The on-demand bucket, effectively nothing, like the live checks': Class A (writes), the site's 1 a queued request and
the job's about 20 a product (the queue's lease, usage and states, the bundle after each thread: 11 for 3 threads in
the tests), about 1,500 in a capped month, 0.008 USD; Class B (reads), the job's about 120 a product (it reads the
queue and the bundle afresh before every change: 63 for 3 threads in the tests), the site's hourly question about the
bundle's version (about 720 a month) and its every-5-minutes questions while a request waits (about 18 a product), the
pre-check's few a run, about 10,500 in all, 0.004 USD; storage: only threads not baked in yet (about 35 KB each with
its extraction, at most 300 threads, about 10 MB, 0.0002 USD a month). Under 0.02 USD a month in all.

Bright Data (estimates, 13 Oct 2026; no money: the free tier is 5,000 records a month, and past it jobs simply stop).
Reading a thread costs a record for its post and one for each top-level comment: 22 for the median thread the answers
quote, 63 at the 90th percentile. The pre-check reads at most 30 records a run (PRECHECK_BRIGHT_DATA_RECORDS), so at most
930 a month, under a fifth of the free records, leaving the rest to the library's own reads (3,972 were used in October
by the 13th). That is about one thread a day: at 1 comment in 8, the answers' 1,288 comments hold about 161 the embed
page can't show, in about 105 threads, and the shown ones alone about 89 in 68 threads (about 3,000 records). So the
threads verifying the most shown comments for their records go first, a comment verified that way lasts 48 hours and is
read again only every other run, and covering them all would need far more records than the free tier has: Noemi's
call. (Since the site reads ahead, the job still finds such comments: a read that found no comment is in the bundle for
48 hours.)

The bucket (estimates, 14 Oct 2026, with the site reading ahead), effectively nothing: Cloud Storage's free tier is for US
regions only, so every operation is billed, but there are very few. Class A (writes): the site's bundle at most once an
hour, about 720 a month, and the job's record, plan and Bright Data memory, 3 or 4 a run, about 120: about 840 a month,
0.004 USD at 0.005 USD per 1,000. Class B (reads): the site's hourly question about the plan's version, about 720 a
month, a download a day (31) and its bundle as it gets ready, and the job's bundle, record and memory, about 5 a run
(155): about 930 a month, 0.0004
USD at 0.0004 USD per 1,000 (before: the site asked about the bundle hourly instead; the job wrote it twice a run).
Storage: the bundle about 3 MB, the plan about 0.6 MB (2,260 answers' comments and 3,000 to verify), the record 1 to
4 MB, under 0.0002 USD a month. Reading and
writing from Cloud Run in the same region is free. Under 0.005 USD a month in all; with the image's storage, about 0.10
EUR a month, under the 1 EUR alert.
