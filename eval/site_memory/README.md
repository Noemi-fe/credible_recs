# The site's memory under load

The scripts behind the numbers in `deploy/cloudrun/DEPLOY.md` (The site's memory). They run the site on a Mac the way the
image runs it (`engine.web --public`, the library as the image holds it, the open model) against stand-ins for Reddit and
for the Google Cloud bucket, so nothing leaves the computer, and read the server's macOS memory while it works.

What is measured: `phys_footprint` (the dirty and compressed pages, which is what Linux counts against a container best)
and its lifetime peak, read every 0.5 s with `proc_pid_rusage` (`mem.py`). The open model's 1.1 GB file is mapped and left
out. Not measured: Linux itself (glibc's arenas), and Cloud Run's own count. Since 5 Nov 2026 the site keeps its saved
checks in memory, so the Mac's footprint counts them, where as files on Cloud Run each took a page of memory that no Mac
figure showed.

## What a run needs (one work folder, outside the repository)

Everything a run reads or writes is in the folder `SITE_MEMORY_WORK` names (default `.cache/site_memory`). It holds
commenters' words (the library copy, the fake Reddit's pages, the bundles), so keep it out of the repository and put it in
the Trash when the work is done.

    export SITE_MEMORY_WORK=/somewhere/outside/the/repo
    TREE=$SITE_MEMORY_WORK/tree                       # the code to measure: git archive <commit> | tar -x -C $TREE
    cp -R data/library $SITE_MEMORY_WORK/lib          # a frozen copy: a profile warm may be writing the shared one
    ln -s $SITE_MEMORY_WORK/lib $TREE/data/library    # and the model under $TREE/models, as the repository has it
    cd $TREE
    python eval/site_memory/prep_requests.py $SITE_MEMORY_WORK/requests.json
    python eval/site_memory/prep_cloud.py $SITE_MEMORY_WORK/cloud
    python eval/site_memory/make_bundle.py $TREE $SITE_MEMORY_WORK/lib $SITE_MEMORY_WORK/bundle_biggest 300 biggest
    python eval/site_memory/make_bundle.py $TREE $SITE_MEMORY_WORK/lib $SITE_MEMORY_WORK/bundle_typical 300 random

`prep_cloud.py` makes the fake Reddit's pages, a bundle of about 18,400 saved checks as the live bucket holds at a start,
and the daily plans. `make_bundle.py` makes a bundle of 300 threads under new ids, the largest in the library or a typical
sample, as if the reading job had added them.

Run `prep_cloud.py` again just before each run. It fixes the bundle's check ages at the time it is run (the answers' checks
are 41 hours old and the rest 10), so a run that starts more than about 7 hours later finds the 41-hour checks past the
48-hour rule and the site lets them go, which changes what the run measures.

## Runs

`segments.sh` runs one piece of a run for one hold of the heavy lock (about 20 minutes), freezing the server between
pieces. The review's whole run was A, B, C and D with `--compress` (reading ahead and the bundle's sharing sped up 60
times, so an hour holds days of them), and X was its control.

    segments.sh <label> A <tree> --compress     start, getting ready, 8 cold answers at once, the open model, remembered
                                                answers, the biggest bundle
    segments.sh <label> B <tree>                a soak of 20 minutes: distinct requests over every product type, 3 visitors,
                                                a keep-warm ping every 3 s, a new daily plan every 4 minutes
    segments.sh <label> C <tree>                the same again
    segments.sh <label> D <tree>                a soak, then the biggest bundle changing again at the soak's level, a typical
                                                bundle taking its place, and a short idle
    segments.sh <label> X <tree>                the control in one hold

`drive.py report <label>` gives each phase's highest footprint and the lifetime peak. `--files` on `drive.py start` keeps
the saved checks as files, as the site did before 5 Nov 2026. `spike_probe.py <bundle>` measures what taking in one
bundle needs on its own. `drive.py dump <label>` and `sets_probe.py` say what the memory holds (the dump needs memory of
its own, so never dump a run whose peak is measured). `kill -USR2 <server pid>` writes one line to the server's log with
what it keeps (remembered answers, the bundle's version, the threads taken from it).

Two things to know. The library copy a run uses is made when it starts (hard links), because the site writes the bundle's
threads into its library folder: a run that shared the folder with the next would find the threads already there and take
nothing in. And the figures are for a library of 2,748 threads: with the 300 largest threads taken in from the bundle the
site holds about 3,050, which is the review's worst case.
