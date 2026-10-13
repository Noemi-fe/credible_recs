# The credible recs site on Google Cloud Run (Noemi, 12 Oct 2026). deploy/cloudrun/DEPLOY.md explains every step.
#
# Built from the private bundle deploy/cloudrun/make_context.py writes (the code at a commit, and the saved library the
# answers read), inside Noemi's own Google Cloud project, so the image is private to it: the library is Reddit text and
# is never public. No secret is used while building; the Hugging Face token for feedback uploads is given at run time
# from Secret Manager. The same image runs the daily pre-check of the quotes answers show (13 Oct 2026): a Cloud Run
# job whose command is `python -m engine.precheck` instead of the CMD below (deploy.sh).
FROM python:3.12-slim

# libgomp1, the one system library llama.cpp's prebuilt CPU build needs; curl, to fetch the open model below.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
# Made by the user itself: a WORKDIR Docker creates belongs to root, and the install below writes into it.
RUN mkdir -p /home/user/app
WORKDIR /home/user/app
COPY --chown=user . .

# The engine and the two packages it needs, with huggingface_hub (the [deploy] extra) for the feedback uploads.
RUN pip install --user -e ".[deploy]"

# Module 1's open model runs through llama-cpp-python, from its prebuilt CPU wheels so nothing is compiled (0.3.18:
# the first release with one; see deploy/huggingface/Dockerfile). Without it, module 1 uses its rules alone.
ARG LLAMA_CPP_VERSION=0.3.18
RUN pip install --user --only-binary=llama-cpp-python \
        --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu \
        "llama-cpp-python==${LLAMA_CPP_VERSION}" \
    || echo "WARNING: no prebuilt llama-cpp-python ${LLAMA_CPP_VERSION} here: module 1 will use its rules alone."

# The open model itself (Qwen2.5 1.5B Instruct, Apache-2.0, public, about 1.1 GB), built in so a cold start doesn't
# download it. Where engine/query_model.py looks for it.
RUN mkdir -p models/qwen2.5-1.5b-instruct \
    && curl -fsSL --retry 3 -o models/qwen2.5-1.5b-instruct/qwen2.5-1.5b-instruct-q4_k_m.gguf \
        https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf \
    || echo "WARNING: the open model wasn't downloaded: module 1 will use its rules alone."

# Cloud Run tells the server its port in PORT (8080). Public mode answers only CREDIBLE_RECS_ALLOWED_HOSTS.
ENV PORT=8080
CMD ["sh", "-c", "exec python -m engine.web --public --port ${PORT}"]
