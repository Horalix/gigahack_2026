# Image for the local meeting service: the FastAPI app and the job worker share it.
#
# Targets:
#   cpu  (default)  runs anywhere Docker runs; ASR on CPU via the `cpu` profile
#   gpu             adds CUDA 12 / cuDNN 9 user-space libraries for CTranslate2;
#                   needs an NVIDIA GPU, WSL2 and the NVIDIA Container Toolkit
#
# Build while online. Everything below happens at build time, so starting a
# container needs no network: pip, apt and model downloads never run at runtime.

# Python 3.11 is what services/meeting/README.md specifies and what
# requirements.lock was pinned against.
FROM python:3.11-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH

# FFmpeg/FFprobe on PATH are a documented service requirement: uploads are
# probed and decoded by the CLI tools, not just by the bundled PyAV libraries.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv "$VIRTUAL_ENV"

# Dependencies first, so editing service code does not reinstall them.
COPY services/meeting/requirements.lock /tmp/requirements.lock
RUN pip install -r /tmp/requirements.lock

# Non-root runtime user. /data and /models exist in the image with the right
# owner so named volumes created from them inherit it.
RUN useradd --create-home --uid 10001 mom \
 && mkdir -p /data /models \
 && chown mom:mom /data /models

WORKDIR /app

# Only what the service reads at runtime. models.py resolves config/profiles and
# models/manifest.json relative to the repository root, which is /app here.
COPY --chown=mom:mom services/ services/
COPY --chown=mom:mom config/ config/
COPY --chown=mom:mom contracts/ contracts/
COPY --chown=mom:mom models/manifest.json models/manifest.json

# Storage refuses a data root inside the repository, so /data sits outside /app.
# Belt and braces for the offline gate: no Hugging Face hub or transformers
# download can happen even if a code path forgets local_files_only.
ENV MOM_DATA_DIR=/data \
    MOM_MODEL_ROOT=/models \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    HF_DATASETS_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1

USER mom

# The API binds loopback only. It is reached through the web container, which
# shares this network namespace; see docker-compose.yml for why.
CMD ["python", "-m", "uvicorn", "services.meeting.api:app", "--host", "127.0.0.1", "--port", "8000"]


FROM base AS cpu


FROM base AS gpu

USER root

# CTranslate2 4.5.0 on Linux needs CUDA 12 cuBLAS and cuDNN 9 at runtime. This
# is the install route the faster-whisper README documents for Linux, and keeps
# the same Python base instead of a separate multi-GB CUDA image. The driver
# itself (libcuda) is injected by the NVIDIA Container Toolkit at run time.
#
# UNTESTED: built and qualified only on a machine with an NVIDIA GPU. Pinned to
# versions that exist on PyPI; confirm on the 3070 Ti laptop before relying on it.
RUN pip install \
      nvidia-cublas-cu12==12.4.5.8 \
      nvidia-cudnn-cu12==9.1.0.70

ENV LD_LIBRARY_PATH=/opt/venv/lib/python3.11/site-packages/nvidia/cublas/lib:/opt/venv/lib/python3.11/site-packages/nvidia/cudnn/lib \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility

USER mom
