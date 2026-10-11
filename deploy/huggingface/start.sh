#!/bin/sh
# Starts the demo on Noemi's Hugging Face Space. The Dockerfile runs it from the code it fetched, so it always matches
# that code. DEPLOY.md, next to this file, explains every step.
#   1. deploy/prepare_space.py downloads the saved library from her private dataset into data/library, then module 1's
#      open model into models/. Without the secret HF_TOKEN and the variable CREDIBLE_RECS_LIBRARY_REPO it stops here,
#      and the Space's logs say why. If only the model fails, the site still starts, with module 1's rules alone.
#   2. The web server starts in public mode on port 7860, the port the Space's README names (app_port). It answers
#      only the hosts in CREDIBLE_RECS_ALLOWED_HOSTS: unless that variable is set, the Space's own address, which
#      Hugging Face gives every Space as SPACE_HOST. "exec" hands the process over to the server, so it hears when the
#      Space stops and uploads any feedback still waiting.
set -eu
cd "$(dirname "$0")/../.."

python -m deploy.prepare_space
export CREDIBLE_RECS_ALLOWED_HOSTS="${CREDIBLE_RECS_ALLOWED_HOSTS:-${SPACE_HOST:-}}"
exec python -m engine.web --public --port 7860
