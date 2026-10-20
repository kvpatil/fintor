# Fintor, as a container. Built for Cloud Run; nothing in here is GCP-specific.
#
#   docker build -t fintor .
#   docker run -e PORT=8080 -p 8080:8080 -e OPENAI_API_KEY=... fintor
#
# Two stages so the final image carries no build toolchain and no pip cache.

# ---- build ---------------------------------------------------------------
FROM python:3.13-slim AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies before source, so a code edit does not re-resolve the whole
# tree. requirements.txt is runtime only - pytest, ruff and playwright live
# in requirements-dev.txt and never reach an image.
COPY requirements.txt .
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt

# THE EMBEDDING MODEL IS BAKED IN, and this is not an optimisation.
#
# src/rag/embedding.py calls StaticModel.from_pretrained("minishlab/potion-base-8M"),
# and model2vec defaults force_download=True - verified by signature inspection
# and then by a socket spy, which recorded one outbound connection on every
# load even with a warm HuggingFace cache. A container that fetches a model at
# startup cannot boot when HuggingFace is slow or down.
#
# model2vec short-circuits on a path that exists (see its persistence module),
# so pointing config at a local directory skips the network entirely.
# allow_patterns, not a full snapshot: the repo also ships an onnx/ export
# (29 MB) that model2vec never reads - it loads model.safetensors. Fetching
# only what is used halves the model layer.
RUN /opt/venv/bin/python -c "\
from huggingface_hub import snapshot_download; \
snapshot_download('minishlab/potion-base-8M', local_dir='/opt/models/potion-base-8M', \
  allow_patterns=['*.safetensors','config.json','modules.json','tokenizer*','vocab.txt','special_tokens_map.json'])" \
 && rm -rf /opt/models/potion-base-8M/.cache

# Strip what a running container never reads: bundled tests, bytecode caches
# and C headers. These ship inside wheels and are dead weight in an image.
RUN find /opt/venv -type d -name "__pycache__" -prune -exec rm -rf {} + \
 && find /opt/venv -type d -name "tests" -prune -exec rm -rf {} + \
 && find /opt/venv -type f -name "*.pyc" -delete \
 && find /opt/venv -name "*.h" -delete 2>/dev/null || true

# ---- runtime -------------------------------------------------------------
FROM python:3.13-slim

# HF_HUB_OFFLINE makes a regression loud. If anything ever tries to reach
# HuggingFace at runtime it will fail immediately and visibly, rather than
# hanging a cold start on a third party's availability.
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HUB_OFFLINE=1 \
    FINTOR_LOCAL_MODEL=/opt/models/potion-base-8M

COPY --from=build /opt/venv /opt/venv
COPY --from=build /opt/models /opt/models

WORKDIR /app
COPY . .

# Runtime state lives under /app/data: four SQLite files (the LLM, embedding
# and market caches, plus LangGraph's thread checkpoints). On Cloud Run that
# is an in-memory overlay, so it is per-instance and lost on recycle - which
# costs cache hits and conversation history, not correctness. Deliberately NOT
# a GCS FUSE mount: SQLite's WAL mode is unsafe over network filesystems.
RUN mkdir -p /app/data/cache /app/data/checkpoints \
 && useradd --create-home --uid 1000 fintor \
 && chown -R fintor:fintor /app/data
USER fintor

EXPOSE 8080

# $PORT at RUN time, not build time: Cloud Run injects it and fails the
# startup probe if nothing listens there. Streamlit defaults to 8501 and does
# not read $PORT on its own, so the flag is required.
#
# Streamlit serves /_stcore/health, which Cloud Run can use as a probe - note
# it answers before the container is built, so a green probe means the server
# is up, not that the model loaded.
CMD exec streamlit run src/web_app/app.py \
    --server.port="${PORT:-8080}" \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.fileWatcherType=none \
    --browser.gatherUsageStats=false
