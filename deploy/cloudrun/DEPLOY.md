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
    (its disk starts empty at every restart), by the daily job as it starts, and by deploy.sh (15 Oct 2026: the text
    a comment found edited keeps).
  - `live_check/plan.json`: what the site should read ahead, from the daily job: the links of the comments answers would
    show or hold next in line, likeliest first; the links of the slimmed library's kept comments due to be verified;
    those of the kept comments found edited, read again like answers' comments until a deploy applies them (15 Oct
    2026); and the job's checks through Bright Data. The site asks for its version at most once an hour (a small
    metadata read) and downloads it only when it changed.
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
  computer; the old run's working out took 84 s on Cloud Run for 1,967) and the kept comments due (earliest deadline first, ties by use, at most 4,500 a day since 25 Oct 2026, 3,000 before: config.LIBRARY_VERIFY_READS, the answers'
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
  site reads the plan's comments that are due: an answer's comment (the first two tiers: shown and next in line) once its
  last read is 40 hours old (so its check never runs out at 48 hours), or that has none; since 25 Oct 2026 the last two
  tiers (the products behind the picks and those after them) are listed one day in five each ("fallback" in the plan) and
  read when they have no read in the last 48 hours; a comment to verify not read in the last 48 hours. At most 48 a ping
  (40 until 25 Oct 2026), 8 at once (4 until 15 Oct 2026), none starting 6 seconds after the ping began (5 until 25 Oct),
  never a read that would wait for Reddit's allowance, and none while Reddit says fewer than 100 reads are left in its 10
  minutes (120 until 25 Oct; those are visitors' answers'). Each ping's counts are in the site's logs ("Reading ahead:
  ...").
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

It deploys on-demand reading on unless told off (on again by default since 25 Oct 2026, below), turns it off for that deploy if the Gemini
key's secret isn't there yet (below; the site deploys anyway and never says it has started reading), and the pre-check's
Bright Data verification off if the Bright Data
key's isn't (the job deploys anyway), makes sure both buckets exist with their rules,
brings the threads read on demand into data/library, applies the pre-check's verification record to the
library, bundles the current commit with the library, builds the private
image and deploys the site, releases Firebase Hosting again (since 3 Nov 2026, so its CDN lets go of the home page and
the How page it keeps; below), then points the pre-check job and the reading job at the same image, makes sure the daily
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

1. every day the pre-check job lists in its plan the kept comments with the earliest deadlines (4,500; 3,000 until 25 Oct 2026), the site reads them
   over the day (its reads ahead), and the next run records what each read said in `live_check/verified.json`;
2. `deploy.sh` copies that record to a temporary file (`gcloud storage cp`) and runs
   `python -m engine.library apply-checks --ledger <it>` before bundling: each passing comment gets its date, and a
   comment found deleted or edited, or not verified within 30 days, loses its words and its mentions, in
   data/library on this computer; the image built next holds the result. With no record yet (before the pre-check's
   first run), this computer's checks of the last 48 hours and the 30-day deadline are applied alone.
   Since 15 Oct 2026 (Noemi's decision 3: a comment edited on Reddit keeps Reddit's current text and only the items
   whose quotes are still found in it word for word) it copies the site's reads of the last 48 hours too, the bundle
   (`live_check/bundle.json`), into the same temporary folder, and passes it (`--bundle <it>`): a comment found edited
   keeps the text the read that found it so showed (or a newer read's), with its verification date, and the items
   still found in it; a reply taking its product from it keeps its item only while it still names that product. The
   copy is read into a temporary folder of its own (reads under 48 hours old only) and both are deleted once applied.
   Without a read of the last 48 hours, such a comment loses its words and items as before; so the plan lists the
   comments found edited for the site to read again every 40 hours, like answers' comments, until a deploy applies
   them (`live_check/plan.json`'s "edited").

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

   Then the verification record applied to the library (13 Oct 2026), before it is bundled, with the site's reads of
   the last 48 hours (15 Oct 2026: the text a comment found edited keeps):

       gcloud storage cp gs://credible-picks-live-checks/live_check/verified.json <a temporary folder>/verified.json
       gcloud storage cp gs://credible-picks-live-checks/live_check/bundle.json <a temporary folder>/bundle.json
       .venv/bin/python -m engine.library apply-checks --ledger <folder>/verified.json --bundle <folder>/bundle.json

   (with no record there yet, `apply-checks --bundle <file>` alone; with no bundle, without `--bundle`), then the
   temporary folder deleted. Then the site, as before, with `CREDIBLE_RECS_LIVE_CACHE_BUCKET=credible-picks-live-checks`,
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
           --tasks 1 --max-retries 0 --task-timeout 55m --memory 2Gi --cpu 1 \
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
pings in Reddit's 10 minutes they took at most 80 of its 200, and none while fewer than 120 were left, so three fresh
answers' worth (an answer reads 10 to 40 comments) stayed for visitors. Since 25 Oct 2026 (the review
docs/verify-bfs-2026-10-25.md, option (c)) they take at most 96 (48 a ping) and none while fewer than 100 are left, so two
fresh answers of the biggest size and a margin of 20 stay for visitors. The site's other reads (on-demand reading's
archive, the bucket) aren't Reddit's.

## On-demand reading

**On by default since 25 Oct 2026** (Noemi, "yes to all recommendations"; it was off from 16 Oct 2026, her decision 6, because
Gemini 3.8 Flash's free allowance read about one product a day and "check back in about 20 minutes" wasn't true). The
reader is now Gemini 3.1 Flash-Lite, whose free allowance is 500 requests a day and 15 a minute: on her three labelled
gold threads it found 80% of her products at 85% precision (3.8 Flash: 84% and 93%), and every quote is checked word for
word as for every reader. Every deploy turns it on, with one setting to turn it off for a deploy:

    CREDIBLE_RECS_ON_DEMAND=off sh deploy/cloudrun/deploy.sh

Off, the site gets none of its settings (CREDIBLE_RECS_ON_DEMAND_BUCKET, CREDIBLE_RECS_ON_DEMAND_JOB): a product it
hasn't read about gets the honest no-threads message ("We haven't read any Reddit threads about teapots yet..."),
nothing is queued, the reading job is never started, and the pre-check doesn't look at the queue. Nothing is deleted:
the code, the bucket (whose objects go at 37 days, as always) and the job stay, and the job is moved to the site's image
again by the first deploy without "off". The switch's default is `ON_DEMAND_SWITCH` in deploy/cloudrun/on_demand.sh.

Since 14 Oct 2026 (Noemi: "I want recs regardless of the category"; the plan's part 3). A request module 1 understands,
about a product the library holds fewer than 6 extracted threads about, is queued, and the answer says so in the
page's words, for example "We haven't read Reddit about teapots yet, so we've started: check back in about 25 minutes."
(about 21 minutes more for each request ahead of it while the day's calls last, since a Flash-Lite call is told to take a
minute and a request 15 calls plus 6 minutes of archive reading; "taking longer than usual" after 150 minutes; and when the free allowance is used up,
when it is back, with the place in line). Since 4 Nov 2026 (Noemi: "Keep 25 min") the job keeps a request inside those
numbers: at most 16 archive searches (config ON_DEMAND_SEARCH_CALLS, the round asked for "blush" before; for a common word the advice
searches such as "blush favorite" come before the newest-100 title searches) and threads whose extraction fits 15 Gemini
calls (engine.on_demand.within_calls); a request whose searches were cut short and waits for its next try, an hour
later, is told the wait from that try. That answer isn't remembered: the next ask works it out again. The site starts
the reading job at once, and at every keep-warm ping while a request waits it asks the bundle's version (one small
read, a download only when it changed), takes the new threads into its library folder and answers with them, every
quote shown checked live on Reddit as always. The daily pre-check takes them in too and checks their answers ahead.

To see the queue (on Noemi's computer, through gcloud's sign-in; counts and product types only):

    .venv/bin/python -m engine.on_demand status

To run the job by hand (it does nothing when no request waits): `gcloud run jobs execute credible-recs-reader --region
europe-west1 --project credible-picks`; its report (counts and product types, never a comment's words) is in its logs
(Cloud Run, Jobs, credible-recs-reader, Logs).

The job's limits, all in engine/config.py ("On-demand reading"): it starts no new reading after 15 minutes of a run and
stops at 45; its runs read for at most 92,000 seconds a month since 6 Nov 2026 (50,000 before; then the queue rests until
the 1st), which at 21 minutes a request is 73 requests a month (39 before; about twice that at the 11 minutes a request
actually took on 25 Oct 2026) and is what limits the reading, within the free-tier guard (below); it makes at most 450 Gemini calls a day, at most 10 a minute (18 a day with Gemini 3.8 Flash, whose
free allowance is 20 a day and 5 a minute, as Google's own 429 answer says; 100 until 25 Oct 2026): Flash-Lite's is 500
a day and 15 a minute, and a request takes about 15 calls, so Gemini's calls alone could read 30 requests a day; none more that
day after Gemini's daily 429 (until 8 am UTC, when the allowance is surely back); at most 20 requests wait at once (10 until
14 Oct 2026: with the general category most requests queue; 20 is about two days of the job's reading, and the
sums below don't change, since the job's time and Gemini calls have caps of their own); a request
whose archive search fails is tried again an hour later and set aside for a day after 3 tries; a product read once is
read again only after 30 days, if its library is still thin then.

**What counts and what visitors are told** (25 Oct 2026, from the review of 16 Oct 2026, R1, R2 and R7; wording
PROPOSED). The bar of 6 threads counts only the threads about the type, never those titled as another type, and a
fast-moving type (laptop, headphones, phone...) whose newest thread about it is over 2 years old (config
ON_DEMAND_OLD_YEARS) is queued too, to be read again for newer threads (only threads posted in the last 2 years are
read; the answer keeps its picks and says the threads are a few years old). The sentence the visitor sees now comes from
the queue's length and the day's capacity (engine.on_demand.wait_for): "in about 25 minutes" only while the day's calls
and the month's reading time can still read the request (21 minutes more for each one ahead), else "It's in line: 3
products are ahead of it, and our free reading allowance covers about 30 a day. Check back tomorrow" (or the date; and
once the month's job time is what runs out, "covers about 73 a month. Check back on 1 November" (39 until 6 Nov 2026),
because 30 a day beside the 1st of next month would not be true). The wording of this message was approved by Noemi on
25 Oct 2026. A free-tier guard's no (below) is told like the month's time running out: "our free reading allowance is used
up for now".

**Doubled, with backfill and a free-tier guard** (6 Nov 2026; Noemi, 5 Nov: "You can double (do it with random products
if people don't research any), but make sure my claude usage for this week and in general stays under control", then
"Let's do A"). Google's free allowance for Cloud Run is one pot in dollars shared by the site and both jobs (Costs,
below), so the month's 92,000 seconds were chosen to keep 10% of each part in hand on the measured use (17 Oct to 5 Nov
2026, scaled to a month), and the hard caps alone can't promise it. So:

- Visitors' first 50,000 seconds of reading a month (config ON_DEMAND_GUARD_FREE_SECONDS, the month before the doubling)
  work exactly as before. Before any visitor read past them, the job asks the free-tier guard (engine/free_tier.py).
- The guard reads, with the job's own service account (deploy.sh grants it roles/monitoring.viewer, read only), what
  Cloud Run has used this month and in the last 7 days from Cloud Monitoring (billable instance time and the CPU and
  memory allocated, by service and job), prices it at Tier 1, adds the days left at the last 7 days' pace at today's
  sizes and the read about to start, and says yes only while each part's projection stays under 90%. Anything it can't
  read or can't trust (no token, an HTTP error, a missing series or one without points, a service in some of the three
  metrics only, an unknown unit, a value that isn't a number of 0 or more) is a no. A no, or a reading that failed,
  rests reading past the first 50,000 seconds for 6 hours (never past the month's end) and backfill for a day: each try
  starts the paid job, and a run that asks the guard or does backfill counts at least the minute Google bills a job's
  run. It keeps a reading 10 minutes: twelve small calls, well inside Cloud Monitoring's free million time series a
  month.
- Backfill: when no visitor's request waits, the job reads a product nobody asked for, one whose answer the daily
  pre-check found thin (fewer than 3 picks; it lists them in the queue), in an order seeded by the day, never one read in
  the last 30 days. The keep-warm ping looks at most hourly whether one is due and queues it (the pre-check may queue one
  too): no new Cloud Scheduler job. Visitors always come first: a visitor's request is read before any backfill, a
  visitor asking for the product a backfill waits on makes it theirs, a full queue counts visitors only, and a backfill
  read already begun adds one request's 21 minutes to the wait a visitor is told. Backfill reads for at most 42,000
  seconds a month (half the month, never into visitors' 50,000: its last read starts only while a whole run still fits),
  paced evenly (never more than its share of the days gone), only while the day's Gemini calls leave room for 20
  visitors' requests, never while the bundle holds 150 threads or more not baked in, never a type a visitor waits for or
  had read in the last 30 days, from Arctic Shift only, and only after the guard's yes. The guard is asked about the
  read together with what is left of visitors' first 50,000 seconds this month (they never ask it, so nothing could stop
  them later): backfill only reads in a month with room for both. Its threads go through every
  usual check (each quote word for word, and live on Reddit before it is shown), and the job's report logs each backfill
  read (product type, minutes, Gemini calls) beside the visitors' reads. `python -m engine.on_demand status` shows
  backfill's hours of the month and its list.
The reader's model is config ON_DEMAND_GEMINI_MODEL (a deploy may set CREDIBLE_RECS_ON_DEMAND_MODEL on the job instead).

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

## Firebase Hosting and the domain

Since 2 Nov 2026 the site's address is **crediblepicks.com** (Noemi bought it at Porkbun, with Porkbun's free WHOIS
privacy: the public record names only Porkbun's proxy). Firebase Hosting, free, holds the domain and
credible-picks.web.app and hands every request to the Cloud Run service (deploy/cloudrun/hosting.py; Cloud Run's own
domain mapping is a preview "not recommended for production", and Google's load balancer costs about 18 USD a month).
www.crediblepicks.com is sent on to crediblepicks.com. The service's run.app address keeps working, for the keep-warm
ping and the latency measurements.

    python -m deploy.cloudrun.hosting release    every path on the Hosting addresses to the service, in europe-west1
    python -m deploy.cloudrun.hosting domains    adds the domain and www where missing (done 2 Nov 2026)
    python -m deploy.cloudrun.hosting status     the domains' state, and the DNS records Firebase still wants

The DNS records, at Porkbun (Noemi's account): Porkbun's parking records removed (the ALIAS on the domain and the
CNAME on `*`), then A on the domain to 199.36.158.100, TXT on the domain `hosting-site=credible-picks` (kept for good:
it proves the domain is ours), and CNAME on www to credible-picks.web.app. Firebase's certificate follows within 24
hours.

What Hosting changes for the site:
- **60 seconds a request at most.** Answers took 2 to 21 s through it on 2 Nov 2026 (live_latency.py, 4 fresh
  answers); a server still getting ready (up to 4 minutes, after a deploy) could make a visitor's first answer time
  out, which the keep-warm ping makes rare. Answers are one JSON reply, not a stream, so Hosting's buffering does not
  matter.
- **A busy site (3 Nov 2026, before the Show HN of about 10 Nov).** The service is one instance that lets 8 requests in
  at once (deploy.sh: `--concurrency 8 --max-instances 1`) and works fresh answers out one at a time, so a crowd would
  queue behind one answer, reach Hosting's 60 s and see a generic error, while the server went on working for answers
  nobody waited for any more. The per-visitor rate limit (30 answers in 10 minutes) does nothing against that. So the
  public site (engine/web.py; values in engine/config.py, "A busy site") does this: an answer that isn't remembered and
  would have to queue is refused at once with 503 `busy` and a Retry-After header of 20 s when 4 visitors already wait
  for their turn, or when its turn doesn't come within 20 s; remembered answers are never refused, and warming takes its
  turns as before and is never refused. And no answer waits for Reddit past 45 s after the request arrived (queue time
  included): a live check that can't start by then is not made, what depends on it is left out of the answer (the
  "Also worth a look" items and summaries), and that answer isn't remembered; if the picks' own checks can't be made in
  time the visitor gets `busy` too, since showing the picks unchecked or changed isn't allowed. The checks that were
  made are kept, so the retry finds them. The 4 and the 45 s are tied to `--concurrency 8` (the answer under way and 4
  queued leave 3 places for pages, the keep-warm ping and remembered answers; a test fails if the concurrency is lowered
  below 8) and to Hosting's 60 s; check them again if either changes. What the deadline can't cut: the engine's own work
  before the checks (a fresh answer took 2 to 21 s in all through Hosting on 2 Nov) and a Reddit read already begun
  (about 0.3 s; a hung one stops at its 30 s timeout). Local mode has neither the cap nor the deadline. The page shows "Lots of people are asking right now.
  Please try again in a minute." (wording proposed by Claude on 3 Nov 2026, waiting for Noemi's yes).
- **The addresses the site answers.** Hosting's Host header names the service, as before, but a page's Origin names
  the address the visitor opened, and feedback and the blind test's answers are refused from any other: deploy.sh adds
  SITE_DOMAINS (the domain, www, credible-picks.web.app and credible-picks.firebaseapp.com) to
  CREDIBLE_RECS_ALLOWED_HOSTS.
- **Who a visitor is, for the rate limit.** Hosting replaces whatever X-Forwarded-For a visitor sends with the
  visitor's own address, and Google's front end then adds the address Hosting reached it from, one of Google's own
  (74.125.0.0/16, 66.102.0.0/20 and 192.178.0.0/15 on 2 Nov 2026). engine.web.client_address skips that one hop, so
  each visitor keeps a limit of their own instead of sharing Google's (engine/web.py, GOOGLE_FRONT_ENDS).
- **Cookies.** Hosting passes on only one named `__session`; the site sets none.
- **The home page and the How page are kept by Hosting's CDN (3 Nov 2026, the launch-load fix, for the Show HN).** The
  site is one Cloud Run server, at most one instance, 8 requests at a time, and until then every response said
  `Cache-Control: no-store`, so every visit to the home page woke and used the server that also works out answers. In
  public mode, `GET /` and `GET /how` answered 200 now say `Cache-Control: public, max-age=60, s-maxage=600`
  (engine/web.py, PAGE_CACHE_CONTROL and cache_control): the CDN keeps a copy for 10 minutes and a browser for 1.
  Everything else says `no-store`: the API, `/test`, `/ready`, every error and 404, and local mode. What Firebase's
  documentation says (https://firebase.google.com/docs/hosting/manage-cache, read 3 Nov 2026), and what the site does
  about it:
  - Responses from Cloud Run are not kept by the CDN by default: Hosting treats them as `private` (the visitor's browser
    only). A response is kept only if it says `public` and a lifetime: `s-maxage` for the CDN (it overrides `max-age`
    there), `max-age` for browsers. Once a kept copy is older than `s-maxage`, the CDN asks the server again. Our
    server doesn't answer "unchanged" (no ETag), so it sends the page whole each time, once per CDN location per 10
    minutes.
  - Only GET and HEAD can be kept. The server answers GET and POST only: a HEAD gets Python's own 501, which is never
    marked `public`.
  - The key a copy is kept under is the host name, the path, the query string and the request headers named in `Vary`
    (Hosting adds Cookie, Authorization and, as the live site's responses showed on 3 Nov 2026, the address the visitor
    opened, so crediblepicks.com, www and credible-picks.web.app each have a copy; and the server adds Accept-Encoding,
    so a gzipped and a plain copy are kept apart). So `/?a=1` and `/?a=2` are two copies; a link with `?utm_source=...`
    is kept like any other, and anyone adding random query strings reaches the server each time (the page is cheap to
    make).
  - Cookies are stripped from requests to Cloud Run except one named `__session`, which would join the key. The site
    reads no cookie and sets none, so the key is just the address. (The docs don't say what a response that sets a cookie
    does to caching; ours never does.)
  - Both pages are the same bytes for everyone (engine/tests/test_web_cache.py asks both with different cookies,
    addresses, countries, languages, browsers, origins and query strings and compares them), and change only with a
    deploy: the templates, the example requests, the makers' image hosts (data/product_pages.json) and
    eval/metrics.json, which the How page shows (it is read each time the page is made, but it is in the image like
    every tracked file, `git archive HEAD` in make_context.py), are all baked in. Nothing the site works out at run time
    reaches either page.
  - A 404 Hosting makes itself is kept 10 minutes by default; ours come from the server, say `no-store`, and aren't kept.
  - **A deploy clears the CDN.** The docs say that redeploying a site's content clears all its cached content across
    the CDN until the next request. They say it of the site's content and don't say it separately of a Cloud Run
    service's responses, so it is not proven for ours. deploy.sh therefore runs `python -m deploy.cloudrun.hosting
    release` right after it deploys the site (step 3b), which also changes nothing else (the same rewrite of every
    path to the service; a new Hosting version each time, none deleted, no domain touched), and prints one line if it
    fails without stopping the deploy. If the release does not clear the CDN, a page is at most 11 minutes old after a
    deploy (10 in the CDN, 1 in the browser); if it does, 1 minute. Either is harmless: the old pages call the same
    `/api/answer`; only a deploy that changed the shape of its JSON could make an old page misbehave for those minutes.
  - **Checking it after a deploy** (the live site's responses carry `x-cache` and `x-cache-hits`):
    `curl -s -o /dev/null -D - https://crediblepicks.com/how | grep -i -E 'cache'` twice. The first shows
    `cache-control: public, max-age=60, s-maxage=600` and `x-cache: MISS`, the second `x-cache: HIT` (the edge location
    that answers is in `x-served-by`; another location has its own copy). `x-cache: MISS` every time, or `no-store`,
    means the pages aren't being kept: check that the revision serving is the new one. A page that still shows the old
    wording after 11 minutes means the release did not clear the CDN and the 10 minutes were not enough: lower
    s-maxage.

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
month; since 6 Nov 2026 counted as one pot shared with the jobs, The shared pot below). The image is about 1.5 GB in Artifact Registry, whose free storage is 0.5 GB: about 0.10 EUR a month for the
rest. Cloud Scheduler's first 3 jobs are free; a ping is one short request, and a server between requests costs
nothing. The budget alert emails Noemi at 50% and 100% of 1 EUR.

The pre-check (14 Oct 2026, the free-tier redesign; engine/tests/test_cloudrun.py does these sums from deploy.sh's own
settings). A job is billed per instance-second for its whole run, waiting included, so it runs with the least that
works: 1 vCPU (a job's minimum) and 2 GiB since 5 Nov 2026 (3 GiB before, see The site's memory below), with module 1's
open model off (15 Oct 2026: with ~2,000 threads it ran out of memory at 1.5 and at 2 GiB; working out the 486 requests peaked at 2.97 GB with the model and 2.25 GB without on
Noemi's computer, and the rules place 484 of them; on 13 Oct, with 436 threads, it had peaked at 1.3 GB with the model;
0.2 GB without it, but without the model the open model's product types would not be checked ahead). It no longer
waits for Reddit: a run is working out the answers (the whole plan run took 2.1 minutes on Noemi's computer for 439
requests on 14 Oct 2026's library, slimmed; the old run's working out took 84 s on Cloud Run), the record and the plan, then Bright Data's batch (a few minutes on Bright Data's side
when there is something to read), so a typical run should take 5 to 10 minutes, 9,300 to 18,600 vCPU-seconds a month
(an estimate: the first runs' logs will say; the first, on 14 Oct 2026, took 32 minutes, 29 of them waiting on Bright
Data's two jobs, both cut off at the then 10-minute wait). Its bound is Cloud Run's 55-minute task timeout: 3,300
seconds a day, 102,300 in a 31-day month, 102,300 vCPU-seconds and 306,900 GiB-seconds, 43% and 68% of the free tier for
instance-billed work (240,000 vCPU-seconds and 450,000 GiB-seconds a month), where the old run's 87 minutes a day were
161,820 and 242,730 (67% and 54%). At 2 GiB, since 5 Nov 2026, its bound is 204,600 GiB-seconds a month (45%, where at 3 GiB it
was 306,900, 68%). So 0 EUR. If a run's log says the memory limit was exceeded, `--memory 3Gi` is still inside the free
tier (306,900 GiB-seconds, 68%). The schedule is the second of Cloud Scheduler's 3 free jobs
(the keep-warm ping is the first); the redesign adds none.

The site's reads ahead (14 Oct 2026). The site is billed by request, under its own free tier (180,000 vCPU-seconds and
360,000 GiB-seconds a month): only while it answers, and a read ahead runs inside the keep-warm ping's request, 4 at
once, each mostly waiting on Reddit's answer (about 0.3 s), so about a tenth of a second of the site's time a read. A
ping starts no read 5 seconds after it began, so at most about 6 seconds a ping with the last reads' answers: 288 pings
a day, at most 53,568 vCPU-seconds and 107,136 GiB-seconds in a 31-day month on the site's 1 vCPU and 2 GiB, 30% of
each. From 15 Oct to 5 Nov 2026 the site ran at 4 GiB, a stopgap: at 2 GiB it ran out of memory every 20 to 40 minutes
with ~1,950 threads, the open model and its warmed answers, so reading ahead's GiB-seconds were at most 214,272 (60%).
Its memory is brought down in the next section (The site's memory). The first deploy of that work is at 3 GiB, so
they are at most 187,488 (52%), and 124,992 (35%) once the site steps down to 2 GiB. What is due on 14 Oct 2026's
library, slimmed (17,335 kept comments): the answers' 2,229 comments once every 40
hours (about 1,340 a day) and up to 3,000 kept comments to verify, about 4,340 reads a day, 15 a ping, about 1.5
seconds of each: about 13,400 vCPU-seconds a month, 7%. 12,356 of the kept comments were never verified (read from the
archive on 11 to 14 Oct, so due by 10 to 13 Nov), about 31,000 once the 846 threads still to extract are slimmed: 11
days at 3,000 a day, oldest first. With the whole library extracted (about 36,000 kept comments) the reads stay the
same (the 3,000 a day are the budget; each kept comment is then read every 12 days, well inside the 30-day deadline).
4,340 reads a day are 38% of what the pings may read (40 a ping, 11,520 a day). On 15 Oct 2026, with ~1,950 threads,
about 7,650 were due a day (the plan's ~7,750 answers' comments every 40 hours and 3,000 kept comments), and the pings
read 20 each (4 at once, each batch about a second on Reddit's side), 5,760 a day; now 8 at once (as an answer reads),
so a ping reaches its 40 in its 5 seconds: 11,520 a day, half as much again as is due, with the same reads of Reddit (at
most 80 of each 10 minutes' 200) and the same billed seconds. Finding what is
due takes about a millisecond a ping (each comment's last read is kept in memory, read from the folder in 0.3 s once a
day as the new plan comes in).

Reading ahead's capacity and the free tier, 25 Oct 2026 (the verify2 builder; the review docs/verify-bfs-2026-10-25.md,
options (b), (c), (h) and (i); reported to Noemi). The plan asks for 4,500 kept comments a day (3,000 before): the review
measured 78,102 kept comments, about 2,700 passing their 30 days a day, and a week's outage costing about 2,200 comments,
ten days about 10,400; at 4,500 a ten-day outage loses nothing. The answers' last two tiers (881 behind the picks and 2,266
after those, of the 559 requests' 10,172 comments) are read every 5 days instead of every 40 hours, freeing about 1,260
reads a day; a comment unreadable twice a week apart lapses at once, freeing the reads it held. What falls due a day:
7,025 first-tier comments x 24/40 = 4,215, 3,147 fallback ones / 5 = 629 and 4,500 kept ones, about 9,350 against 9,600
read on 24 Oct 2026 (the cap then 11,520). So a ping reads at most 48 in 6 seconds (40 in 5 before), 13,824 a day, with
visitors keeping 100 of Reddit's 200 reads in each 10 minutes (96 for reading ahead). The ping bills 7 seconds (6
before): at most 62,496 vCPU-seconds a month on the site's 1 vCPU (35% of 180,000; it was 53,568, 30%) and, at 4 GiB,
249,984 GiB-seconds (69% of 360,000; it was 214,272, 60%), still free. At the site's 3 GiB from the first deploy of the
memory work (6 Nov 2026) the ping's GiB-seconds are 187,488 (52%), and 124,992 (35%) at 2 GiB. The pre-check job's
vCPU-seconds are unchanged (102,300, 43%; 152,300 with on-demand reading's, 63%), and so are Bright Data's 930 records a
month.

The site's memory (5 Nov 2026, Noemi: "Let's do A"). From 15 Oct 2026 the site ran at 4 GiB, a stopgap. The work below
was written to bring it back to 2 GiB, and after two independent reviews deploy.sh asks for 3 GiB for the first deploy of this
code (`--memory 3Gi`, 6 Nov 2026, not deployed yet), with 2 GiB to follow once Cloud Monitoring shows room (the paragraph
headed What the live site will tell says when). Google's free allowance for Cloud Run is most likely one pot for the site and the
jobs, and the site at 4 GiB was most of October's use of its memory part (84% of it, from Cloud Monitoring's billable time),
so halving the site's memory at the step down to 2 GiB leaves room to double on-demand reading later at no cost, and 3 GiB
leaves half as much. A review on 5 Nov 2026, in the evening, found that the first version of this work had missed the biggest
part of the memory's growth and a few spikes. What it found and what was done are in here, and the numbers are the second
round's. Two independent reviews of that round found the code correct and the answers unchanged in all 296 sweep requests.

What the live site used (Cloud Monitoring, run.googleapis.com/container/memory/utilizations, read only, the 4 GiB revisions,
15 Oct to 5 Nov 2026, 6,061 five-minute windows). The busiest window of each day rose from 1.28 GiB on 16 Oct to 2.00 GiB on
5 Nov. Two things made that rise. The library grew from about 1,950 to 2,748 threads. And the memory of each instance climbs
through its life and falls at each start, by 0.055 to 0.132 GiB a day with the keep-warm pings alone and 0.16 to 0.38 GiB a
day with the Show HN traffic, over instances that lived 4 to 32 hours and, when a deploy ended them, up to 55 to 73 hours.
The level 3 hours after a start rose from 1.16 to 1.20 GiB on 16 Oct to 1.60 to 1.72 GiB from late October to 3 Nov. Over the
three weeks the median window was 1.64 GiB, 54% of the windows were over 1.6 GiB, 19% over 1.8 GiB and 54 (0.9%) over 2.0
GiB. The first hour at 4 GiB (15 Oct, 2.32 GiB) was the highest, just after the move. At 2 GiB the site would have run out of
memory within hours again. The first version of this section read the whole rise as the library's growth (0.035 GiB a day)
and counted its room from that, which mixed an instance's age with the library's size. It also called the match between a
34-minute soak on Noemi's computer (2,075 MB) and the busiest window of a week (2,048 MB) a calibration, and it was none: the
two measure different things.

How it was measured. The site was run on Noemi's computer the way the image runs it (engine.web --public, the library as the
image holds it with its 2,748 threads, and about 3,050 once the 300 largest are taken in from an on-demand bundle, which is
the worst case measured, with the open model and the keep-warm ping reading ahead against stand-ins for Reddit and for Google
Cloud's bucket) and its memory read as macOS's footprint, the dirty and compressed pages, every half second, with the
lifetime peak the system keeps (the open model's 1.1 GB file is mapped and left out). The scripts are in eval/site_memory
(its README says how to run them). Not measured: Linux and Cloud Run's own count of memory. No container runs here, so what
glibc's arenas do and what Cloud Run counts are left to the first day's reading of Cloud Monitoring. One thing the first
version did not count is now in the figures, the saved checks: on Cloud Run the disk is memory and each file takes a whole 4
KiB page, which no macOS figure showed. One thing is still not in them: an on-demand bundle's threads, which Cloud Run holds as
files too (49.0 MiB for the 300 largest, see the result below).

Where the memory went (the code as it was, 2,748 threads, after the 85 warm answers, each object counted once): the library's
threads 371 MB and its checked extractions 168 MB (213,000 comments and some 94,000 quotes), the tables of every name's words
and features that making the library's name index fills and nothing needs again 290 MB, the brand rules' remembered pairs 75
MB, the credibility tables 85 MB, the writers' profile store 69 MB, the name index 63 MB and the library's ranges 43 MB, the
comments read for every thread an answer touched 56 MB once all have been touched. Remembered answers (20 to 35 KB each)
were never let go of. The review then found three more.
- The compiled expressions made for each product type. The one that finds a type's names inside the names of the other types
  of its category (engine/sources.py, _inside_pattern) is 549 KB each for the 347 types of the general category, and it was
  kept for every type ever asked about: 31 MB after getting ready, 153 MB after a soak that touched 338 types, up to 196 MB
  for all 446, and a visitor's own words for a type the open model names each added one. Two more were the same in kind
  (_covering_pattern with _covering_phrases, 13 and 14 MB for all types, and _community_covers, which is small: only 2 types
  have community names, about 1 KiB each. The up to 0.6 MB each and 268 MB for all types first written for it came from
  building it for types with no community names, which the code never does). A heap dump
  of a server after 11 minutes of the soak showed the compiled expressions grown by 150 MB (from 37 MB to 187 MB) and the
  memory Python keeps for small objects by 59 MB (the structures it knew of by 42 MB of that), of the 240 MB the footprint had
  risen. This was most of the soak's climb. It does not explain the climb through an instance's life that Cloud Monitoring
  shows with pings alone (0.055 to 0.132 GiB a day, live): no new product types are asked then, so these caches do not grow.
  The saved checks below explain about 40 MiB a day of it at most. So 16 to 95 MiB a day of that climb is still unexplained,
  and instances live up to 73 hours.
- The saved checks as files on Cloud Run's memory disk: a page each whatever their size, about 300 bytes of words. 18,400 files
  from the bucket's bundle at a start, 44,838 after the review's soak, 70 to 210 MiB with the files' own bookkeeping. Reading
  ahead adds up to about 9,350 a day, which at a page each is about 40 MiB a day, below the climb Cloud Monitoring shows with
  pings alone (56 to 135 MiB a day) and so only part of it. Kept in memory as they are now, 9,350 checks are about 5 MiB.
- Taking in an on-demand bundle parsed the whole file at once, which holds the file, its text decoded (2 to 4 bytes a letter
  once a curly quote or an emoji is in it) and every string parsed out of it: about 7.8 times the file for a moment, +119 MiB
  for a typical 16.1 MiB bundle and +416 MiB for the 300 largest threads (52.8 MB).

What was bounded (engine/tests/test_site_memory.py holds each one, written before it). Nothing changes an answer. Each only
decides what stays in memory, and what is let go is worked out again, the same.
- Every pydantic object keeps a set of its field names (728 bytes for a comment). Objects of one shape share one set, made as
  each thread and extraction is read (engine/compact.py): about 250 MB, and a library read again never holds two sizes.
- The tables of every name's words and features are emptied once the library's name index of a category is built
  (engine/match_products.py, forget_names): about 190 MB at the end of the warm answers.
- The profile store the site reads is held as pairs and tuples (engine/profiles.py, CompactProfileStore, read only): 69 MB to 41.
- The brand rules' remembered pairs share the sets of names they are keyed by (engine/pipeline.py): 75 MB to 15.
- Remembered answers are kept to 24 MB (config.ANSWERS_KEPT_BYTES, engine.web.RememberedAnswers), about 1,000 answers: the
  answers whose time is up go first and then the oldest.
- A Table of remembered answers holds 40,000 at most (engine/memo.py, 200,000 before), the facts of recent threads 256 (512)
  and the library's names share their words, through a pool of the index's own (sys.intern kept them for ever in Python 3.12).
  About 100 MB together in the soak.
The review's three, and the setting, in the second round:
- The compiled expressions made for each product type are kept for ANSWERS_KEPT_TYPES types at most, the types asked
  most lately (engine/sources.py, a least-recently-used cache of 64 for _inside_pattern, _community_covers,
  _covering_pattern and _covering_phrases). The patterns of the 64 biggest general types are about 47 MiB (37.8 for
  _inside_pattern, 5.6 for _covering_pattern and 4.0 for _covering_phrases), measured. Python's own re cache (512 patterns)
  can also hold a pattern that this cache let go, so that figure is a floor. One let go is made again, the same
  expression, in 3 to 50 ms.
- A bundle is taken in one item at a time (engine/on_demand.py, bundle_items): the file is scanned for where each item
  lies, the whole of it is checked to be readable before anything is written, and one item is parsed at a time, so what
  it needs beside the file is +25 MiB for the typical bundle and +64 MiB for the largest, the file itself being the
  floor.
- The site's saved checks are kept in memory (engine/live_check.py, _MemoryChecks, used by the public site when it has
  the live checks' bucket): 526 bytes each, so 18,400 are 9 MiB and 44,838 are 23 MiB where files took 70 to 215 MiB,
  and any over 48 hours old, which nothing uses, is let go whenever the bundle is made. The daily job and Noemi's
  computer keep files as before.
- The image sets MALLOC_ARENA_MAX=2, so glibc keeps two memory arenas and not one for each of the threads that answer,
  read ahead and run the open model. It is the usual setting for a Python server of this kind and the one change here
  that no Mac can measure.
Not changed: the answers' memory of 64 product types (config.ANSWERS_KEPT_TYPES), what warming warms (the search page's
examples and the demo requests stay warm), the answers, their wording and scores, the 48-hour quote rule, the concurrency of
8, reading ahead's counts, the busy cap and on-demand reading.

Result, on Noemi's computer, the review's runs again on the code as it is now (the library of 2,748 threads, the open model,
the 300 largest library threads as the bundle, reading ahead against the stand-ins, footprint in MiB, the highest of each
phase and the lifetime peak): getting ready (its 90 seconds of warm answers) 1,196 (the lifetime peak), 8 cold answers at
once on the biggest types beside a keep-warm ping 1,193 (6 of the 16 refused by the busy cap, as designed), the open model's
37 requests 1,182, remembered answers 1,174 (four rounds of 56 at once, 0.01 to 0.04 s at the median), the largest bundle
taken in 1,256 with a lifetime peak of 1,257, the 60.6-minute soak (6,789 different answers for 3 visitors, no error and no
503) 1,545 highest and 1,584.3 for the lifetime, then the largest bundle changing again at that level and a typical one
replacing it 1,479 highest and no new peak, and a short idle 1,468. The control run (a typical bundle, pings every 20 s, 2
visitors, 13.5 minutes, the same bundle again) peaked at 1,259. The soak held 67,732 saved checks at its end, 35 MiB in
memory, where as files they would have taken over 300 MiB on Cloud Run. The review measured 1,742.5 MiB (85.1% of 2 GiB) at
the same place on the code of the first round, 2,016.5 with the largest bundle changing again at the soak's level, and about
1.85 GiB or more once Cloud Run's files were added. The ceiling is 1,638 MiB, 80% of 2 GiB, the most the site may reach in
any of these before it needs more memory. The highest of all of them is 1,584.3 MiB, 77.4% of 2 GiB and 54 MiB under the
ceiling, but that figure did not count everything it was first said to. On Cloud Run, write_items puts an on-demand bundle's
threads into data/library/{threads,extracted} on the in-memory disk, and a Mac's footprint never counts files. For the 300
largest threads those files are 49.0 MiB in 4 KiB pages. So the same worst case on Cloud Run is about 1,633 MiB, 79.8% of
2 GiB and 5 MiB under the ceiling of 1,638 MiB. Two more readings bear on it. A second measurement review, with its own soak,
found a lifetime peak of 1,459.3 MiB (71.3%). And Cloud Monitoring put the live old code, once warm, at 88 to 93% of the Mac's
figure for the same code, which makes the Mac a conservative stand-in. What stays unmeasured is Linux itself, glibc with
MALLOC_ARENA_MAX=2 and several days of creep in an instance's memory, and reading ahead and the bundle's sharing ran 60 times
faster here than they do live. With 5 MiB of margin on the worst case and those open, 2 GiB should not be the first
setting, so the first deploy of this code is at 3 GiB, and the paragraph headed What the live site will tell says when to step down.

Speed, measured in-process on the full library with the model on (the review's bench, best of two rounds, paired by request):
warmed answers had a median of 0.249 s on the code before the first round, 0.263 s after it and 0.262 s now (24 requests,
3.7% over the first), first answers of a type 1.203, 1.304 and 1.131 s (20 types, paired by request 1.6% over the first and
0.2% under the first round's), remembered answers take no time, the 8 largest types took 13.8, 13.2 and 12.4 s in all, and
the bench's getting ready 12.4, 11.3 and 11.3 s. The sweep's 296 answers took 268.8 s and the eval 168 s here, the machine's
load moving them as much as the code. So the second round moved no speed, and the first round's few percent on warmed answers
is not noticeable to a visitor. The first answer after an on-demand bundle with new threads arrives still takes 22 to 50 s
(the library is read again and its index built), and the visitors who ask meanwhile are refused by the busy cap after 20 s,
as they were before. All 296 requests of eval/sweep.py gave identical answers (every field except the seconds), and
eval/run_eval.py with live checks off gave identical output and an identical metrics.json.

What the live site will tell, and what to do (6 Nov 2026: the first deploy is at 3 GiB). The memory of each instance should
now start near the footprint after getting ready, 1,196 MiB on the computer (1.17 GiB), and stay flat apart from the saved
checks, which are 526 bytes each and are let go at 48 hours. Whether it does is the open question, since 16 to 95 MiB a day of
the climb with pings alone is unexplained (see the compiled expressions above). After the first deploy, read Cloud
Monitoring's memory for the first day and then the first week (Metrics Explorer, Cloud Run Revision, Container, Memory
utilizations, service credible-recs, the 99th percentile). Step down to 2 GiB (`--memory 2Gi` in deploy.sh, then deploy
again) once the p99 stays under about 1.5 GiB across instances at least 2 days old (a utilisation of about 0.5 at 3 GiB).
Reading ahead then bills 124,992 GiB-seconds a month (35% of the free 360,000) where 3 GiB bills 187,488 (52%) and 4 GiB
249,984 (69%). Go back to 3 GiB if the p99 goes over 0.8 of the limit in any 5-minute window or the warmed level climbs more
than about 0.05 GiB a day. An alert on that metric at 0.8, with an email, is the surest way to hear of it, and creating one
sends mail in Noemi's name, so it is hers to say yes to (none was made). What is still unmeasured is Linux: what the arenas
setting does and what Cloud Run adds to the count. The review's own fallback was to stay at 4 GiB or to try 3 GiB until that
is measured, which is what the first deploy does. Until the p99 has been read for a few days, 2 GiB rests on a Mac's figures
and 5 MiB of margin.

The pre-check job (the same library, the open model off, 559 requests): 913 MB at its worst on Noemi's computer, where it was
1,410 MB before the first round and 1,092 MB after it (the bound on the compiled expressions saves the job too), and the job
on Cloud Run used at most 1.47 GiB of its 3 GiB since 16 Oct (1.47 on 19 Oct and 1.35 on 4 Nov), which is 73.5% of 2 GiB
before the saving this change brings, so it runs at 2 GiB and bills a third fewer GiB-seconds. Moving the job to 2 GiB is
safe on its own.

Container images (14 Oct 2026). Each deploy stores the site's image in Artifact Registry (the repository `cloud-run-source-deploy`, which `gcloud run deploy --source` makes): about 1.15 GB, most of it the open model the build downloads. Its free tier is 0.5 GB of storage, then about 0.10 USD per GB a month. By the evening of 14 Oct 44 images had grown to 51 GB (about 4.60 EUR a month); Noemi chose to keep only the newest one, so the other 43 were deleted that evening and deploy.sh applies a cleanup policy after each deploy (image_cleanup_policy.json: keep the newest version, delete every other; Google runs it about once a day). One image costs about 0.07 EUR a month. An older site version can't be rolled back to once its image is gone: rebuild it from its commit instead. To bring storage under the free 0.5 GB, the model would have to leave the image (downloaded as the server starts, about 20 s slower starts): not done.

The shared pot (6 Nov 2026, Noemi's doubling of on-demand reading, option A; engine/tests/test_cloudrun.py does these
sums from deploy.sh's own settings). Cloud Run's pricing page (https://cloud.google.com/run/pricing, read 6 Nov 2026)
says the free tier "is applied as a spending based discount using Tier 1 pricing", aggregated by billing account, and
it is the same money in every section: a job's free 240,000 vCPU-seconds at $0.000018 and a request-billed service's
180,000 at $0.000024 are both $4.32 of CPU, and 450,000 GiB-seconds at $0.000002 and 360,000 at $0.0000025 both $0.90
of memory. So the site and both jobs share one pot per part, and the sums above, made for separate allowances, no longer
hold on their own. The site is request-billed (no `--no-cpu-throttling`, none when idle), and its startup CPU boost (2
vCPU while it starts and 10 s after) is billed too. In dollars, for a 31-day month:

| | CPU | Memory, site at 3 GiB | Memory, site at 2 GiB |
|---|---|---|---|
| The pre-check at its 55 minutes every day (102,300 vCPU-s, 204,600 GiB-s) | $1.84 | $0.41 | $0.41 |
| Reading ahead at its limit (62,496 s of the site) | $1.50 | $0.47 | $0.31 |
| Both | $3.34 (77%) | $0.88 (98%) | $0.72 (80%) |
| On-demand reading's month, 92,000 s at 1 vCPU and 1 GiB | $1.66 | $0.18 | $0.18 |
| All three | $5.00 (116%) | $1.06 (118%) | $0.91 (101%) |
| Free | $4.32 | $0.90 | $0.90 |

Visitors' answers on the site have no cap at all. So the caps alone can't keep 10% in hand: at 3 GiB the memory part is
past 90% before on-demand reading reads a second, and on the CPU part only 30,372 of its seconds would fit (44,160 on
memory at 2 GiB). What was measured (Cloud Monitoring, read only, 6 Nov 2026, summed by day) is far under the caps. Over
the 20 days from 17 Oct to 5 Nov 2026, scaled to a 31-day month (the site came up on 12 Oct and its first days were its
busiest, with deploys, boosts and the 4 GiB stopgap's restarts), the site billed 52,223 s with 57,916 vCPU-seconds
allocated (its boosts included) and the pre-check 44,028 s (44,425 vCPU-s). At today's sizes that is:

| | CPU | Memory, site at 3 GiB | Memory, site at 2 GiB |
|---|---|---|---|
| The site | $1.39 | $0.39 | $0.26 |
| The pre-check, at 2 GiB | $0.80 | $0.18 | $0.18 |
| On-demand reading's month, 92,000 s | $1.66 | $0.18 | $0.18 |
| All three | $3.85 (89.0%) | $0.75 (83.5%) | $0.62 (69.0%) |

The CPU part binds: on these 20 days the reader's month could be at most 94,353 s at 90%; the last 14 days alone were
busier (90,325 s, so 92,000 is 90.7% there) and the last 7 a little quieter (95,222 s). 92,000 is kept. (Until the fix
round of 6 Nov 2026 this table took October's sums, where the pre-check ran only 19 days: 89.6%, 79.6% and 65.0%.) The
pre-check's daily time is growing (about 1,100 s a day in late October, about 1,700 in early November), and a busier
month (the last 30 days, 7 Oct to 6 Nov, with their deploys, would leave the reader about 65,650 s) is the free-tier
guard's to catch (On-demand reading, above): past visitors' first 50,000 seconds, and for every backfill read, it reads
the month so far and stops reading while the projection is at 90% of either part. Nothing caps the site's own answers,
as before the doubling: a month with the site's traffic tripled for its last 10 days would pass the free tier with or
without on-demand reading. The guard sees this project only; the billing account
also pays for "My First Project", which runs no Cloud Run today. Cloud Monitoring's read API (https://cloud.google.com/stackdriver/pricing,
read 6 Nov 2026): $0.50 per million time series returned, the first million a month free per billing account, each call
counting its series or one, whichever is more; the project may make 6,000 time-series queries a minute. The guard makes
12 calls a reading, about 24 series (the site and a small test service, the two jobs), at most one reading per 10
minutes of a run, and only a run whose time counts in the month's 92,000 seconds asks it, at least a minute each (since
the fix round of 6 Nov 2026): at worst about 1,700 readings, about 41,000 series a month, about 7,000 in a likely month.
0 EUR.

On-demand reading (estimates, 14 Oct 2026; 0 EUR). The reading job is billed like the pre-check, per instance-second
for its whole run, waiting included, on 1 vCPU and 1 GiB. One product takes about 12 minutes: about 6 minutes of
Arctic Shift at its 10 s pace (20 title searches and about 15 reads for a kitchen type with no title words of its own,
fewer for most), about 5 for Gemini (about 9 calls for 6 threads read in parts of 40 comments, each paced 6 s apart),
and half a minute to start. Its runs are capped at 50,000 s a month (about 70 products; 92,000 s since 6 Nov 2026,
about 73 at the 21 minutes a request is told to take, priced in The shared pot above), so the worst month was 50,000
vCPU-seconds and 50,000 GiB-seconds; with the pre-check's at most 102,300 and 306,900 (15 Oct 2026, at 3 GiB; 83,700
and 125,550 that afternoon, 161,820 and 242,730 before), 152,300 of the free 240,000 vCPU-seconds (63%; 88% before) and
356,900 of the free 450,000 GiB-seconds (79%). Since 5 Nov 2026 the pre-check runs at 2 GiB, so its GiB-seconds are at
most 204,600 and the two jobs' 254,600 (57%).
There are no empty runs: nothing is scheduled,
the job runs only when a request waits. Cloud Scheduler: no new job (the site starts the reading job, and the keep-warm
ping starts it again when a start failed), so still 2 of the 3 free jobs. Gemini: free tier only, at most 450 calls a
day by the job (500 are free; 30 requests by calls, but the month's 92,000 job seconds read about 73 requests, 39 at
50,000 before 6 Nov 2026), 10 a minute, stopping at Gemini's own daily limit; backfill starts only while 20 visitors'
requests' calls are left for the day. Secret Manager: a third secret (gemini-key,
with hf-token and bright-data-key), inside the free 6 secret versions, and the job reads it once a run (free: 10,000
reads a month). Arctic Shift: free, at its own pace. Starting a job (Cloud Run's Admin API): free. Sending threads to
Gemini is the only traffic out of Google: about 0.25 MB a product, about 17 MB in a capped month, about 0.002 USD.
The on-demand bucket, effectively nothing, like the live checks': Class A (writes), the site's 1 a queued request and
the job's about 20 a product (the queue's lease, usage and states, the bundle after each thread: 11 for 3 threads in
the tests), about 1,500 in a month capped at 50,000 s, 0.008 USD; Class B (reads), the job's about 120 a product (it
reads the queue and the bundle afresh before every change: 63 for 3 threads in the tests), the site's hourly question
about the bundle's version (about 720 a month) and its every-5-minutes questions while a request waits (about 18 a
product), the pre-check's few a run, about 10,500 in all, 0.004 USD; storage: only threads not baked in yet (about 35
KB each with its extraction, at most 300 threads, about 10 MB, 0.0002 USD a month). Under 0.02 USD a month in all.
Since the doubling (6 Nov 2026) a month capped at 92,000 s reads about 130 products at the 12 minutes one takes: about
2,600 Class A, plus at most about 750 for backfill queued by the hourly ping, about 0.017 USD; about 16,000 Class B,
plus the ping's hourly look at the queue (about 750), about 0.007 USD. Under 0.03 USD a month in all.

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
(155), and each deploy's record and bundle (2 a deploy, since 15 Oct 2026): about 1,000 a month, 0.0004
USD at 0.0004 USD per 1,000 (before: the site asked about the bundle hourly instead; the job wrote it twice a run).
Storage: the bundle about 3 MB, the plan about 0.6 MB (2,260 answers' comments and 3,000 to verify), the record 1 to
4 MB, under 0.0002 USD a month. Reading and
writing from Cloud Run in the same region is free. Under 0.005 USD a month in all; with the image's storage, about 0.10
EUR a month, under the 1 EUR alert.
