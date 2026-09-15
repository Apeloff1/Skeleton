# ============================================================================
# Tutolage Backend Dockerfile
# ============================================================================
# Build context MUST be the repository root because the image vendors
# skeleton/ alongside backend/.
# ============================================================================

ARG UV_VERSION=0.12.4

# Official Python multi-platform index pinned for reproducible rebuilds.
# Refresh this digest deliberately alongside dependency/security review.
# Stage 1: Builder with uv
FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS builder
ARG UV_VERSION

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:${UV_VERSION} /uv /usr/local/bin/uv
COPY backend/pyproject.toml ./
COPY backend/requirements.txt ./

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN uv pip install -r requirements.txt

# Stage 2: Production
FROM python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6 AS production

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY backend/ .
COPY skeleton/ ./skeleton/

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8001/api/health || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]

# Stage 3: Development
FROM production AS development

USER root
RUN pip install --no-cache-dir "pytest>=8,<9" pytest-cov "ruff==0.9.*"
USER appuser

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
