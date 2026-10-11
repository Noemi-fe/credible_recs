# The credible recs demo as a Hugging Face Docker Space. DEPLOY.md, next to this file, explains every step.
#
# Nothing private is in this image. The code comes from the public GitHub repository, and the saved library (Reddit
# text) is downloaded from Noemi's private dataset only when the Space starts (start.sh), never built in: Hugging Face
# lets anyone run a public Space's image. No secret is used while building.
FROM python:3.12-slim

# git, to fetch the code; libgomp1, the one system library llama.cpp's prebuilt CPU build needs to run.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face runs a Space as the user with id 1000, so everything from here on belongs to that user.
RUN useradd --create-home --uid 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /home/user

# The code: the public repository at CREDIBLE_RECS_REF, a branch, a tag or a commit. main, unless the Space has a
# variable of that name (Hugging Face passes a Space's variables to the build).
ARG CREDIBLE_RECS_REPO=https://github.com/Noemi-fe/credible_recs
ARG CREDIBLE_RECS_REF=main
RUN git init --quiet app \
    && git -C app fetch --quiet --depth 1 "$CREDIBLE_RECS_REPO" "$CREDIBLE_RECS_REF" \
    && git -C app checkout --quiet FETCH_HEAD
WORKDIR /home/user/app

# The engine and the two packages it needs (pydantic, certifi), with huggingface_hub (the [deploy] extra) for the
# downloads and the feedback uploads.
RUN pip install --user -e ".[deploy]"

# Module 1's open model runs through llama-cpp-python, installed from its prebuilt CPU wheels so nothing is compiled.
# 0.3.16, the version on Noemi's computer, has no prebuilt CPU wheel; 0.3.18 is the next release that has one, and
# changes nothing module 1 uses. If it can't be installed, the site still works: module 1 uses its rules alone.
ARG LLAMA_CPP_VERSION=0.3.18
RUN pip install --user --only-binary=llama-cpp-python \
        --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu \
        "llama-cpp-python==${LLAMA_CPP_VERSION}" \
    || echo "WARNING: no prebuilt llama-cpp-python ${LLAMA_CPP_VERSION} here: module 1 will use its rules alone."

# 7860 is the port the Space's README names (app_port).
EXPOSE 7860
CMD ["sh", "deploy/huggingface/start.sh"]
