# ============================================================================
# Tutolage Backend Dockerfile
# ============================================================================
# Build context MUST be the repository root because the image vendors
# skeleton/ alongside backend/.
# ============================================================================

ARG UV_VERSION=0.12.4

# Resolve the versioned uv image in a FROM instruction. Docker does not expand
# build arguments in COPY --from image references, so give the image a stage
# name and copy from that stable stage instead.
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# Official Python multi-platform index pinned for reproducible rebuilds.
# Refresh this digest deliberately alongside dependency/security review.
# Stage 1: Builder with uv
FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS builder

WORKDIR /app

COPY --from=uv /uv /usr/local/bin/uv
COPY backend/pyproject.toml ./
COPY backend/requirements.txt ./

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN uv pip install -r requirements.txt

# Stage 2: Production
FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN groupadd --gid 10001 appuser \
    && useradd --create-home --uid 10001 --gid 10001 --shell /usr/sbin/nologin appuser

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY --chown=appuser:appuser backend/ .
COPY --chown=appuser:appuser skeleton/ ./skeleton/

USER appuser

EXPOSE 8001

# Use the Python standard library for health checks so the production image
# does not need curl/apt packages solely for probing the local service.
HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/health', timeout=10).read()" || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]

# Stage 3: Development
FROM production AS development

USER root
RUN pip install --no-cache-dir "pytest>=8,<9" pytest-cov "ruff==0.9.*"
USER appuser

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
