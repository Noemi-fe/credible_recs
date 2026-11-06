#!/bin/sh
# One segment of a run of the site's memory under load: each is meant for one hold of the heavy lock (about 20 minutes at
# most), with the server frozen between them (README.md). usage: segments.sh <label> <A|B|C|D|X> <tree> [start flags]
#   A  start, getting ready, 8 cold answers at once with pings, the open model, remembered answers, the biggest bundle
#   B and C  a soak of 20 minutes each
#   D  a soak, the biggest bundle changing again, a typical bundle replacing it, a short idle, stop
#   X  the control run in one hold: a typical bundle, no compressed reading ahead, 2 visitors, 13.5 minutes, the bundle again
# SITE_MEMORY_WORK (the work folder) and PYTHON (default python3) are read from the environment.
HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${SITE_MEMORY_WORK:-$HERE/../../.cache/site_memory}"
PY="${PYTHON:-python3}"
label=$1; seg=$2; tree=$3; shift 3
cd "$HERE" || exit 1
date
case $seg in
A)
  $PY drive.py start "$label" "$tree" "$@" || exit 1
  $PY drive.py phase "$label" startup || exit 1
  $PY drive.py phase "$label" overlap || exit 1
  $PY drive.py phase "$label" model || exit 1
  $PY drive.py phase "$label" remembered || exit 1
  $PY drive.py phase "$label" bundle || exit 1
  $PY drive.py freeze "$label" ;;
B|C|D)
  $PY drive.py phase "$label" soak minutes=20.2 || exit 1
  if [ "$seg" = D ]; then
    $PY drive.py phase "$label" rebundle
    $PY drive.py phase "$label" rebundle which="$WORK/bundle_typical/on_demand/threads.json"
    $PY drive.py phase "$label" idle minutes=0.5
    $PY drive.py stop "$label"
  else
    $PY drive.py freeze "$label"
  fi ;;
X)
  $PY drive.py start "$label" "$tree" "$@" || exit 1
  $PY drive.py phase "$label" startup || exit 1
  $PY drive.py phase "$label" bundle which="$WORK/bundle_typical/on_demand/threads.json" || exit 1
  $PY drive.py phase "$label" soak minutes=13.5 workers=2 ping_every=20 || exit 1
  $PY drive.py phase "$label" rebundle which="$WORK/bundle_typical/on_demand/threads.json"
  $PY drive.py stop "$label" ;;
esac
date
