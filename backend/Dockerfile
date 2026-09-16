# ============================================================================
# Tutolage Backend Dockerfile
# ============================================================================
# Build context MUST be the repository root because the image vendors
# skeleton/ alongside backend/.
# ============================================================================

# Resolve the versioned uv image by immutable multi-platform digest. Refresh
# the tag+digest pair deliberately alongside dependency/security review.
FROM ghcr.io/astral-sh/uv:0.12.4@sha256:d0a6eca6c669dc7e9c51218707b8438a3d30402733d739dcc00adb3e213e8f5c AS uv

# Official Python multi-platform index pinned for reproducible rebuilds.
# Refresh this digest deliberately alongside dependency/security review.
# Stage 1: Builder with uv
FROM python:3.14-slim@sha256:83ff1d245a3d57d04152252d3ef9cb361494d0b3395abd65a5ebe91c401c8e83 AS builder

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
FROM python:3.14-slim@sha256:83ff1d245a3d57d04152252d3ef9cb361494d0b3395abd65a5ebe91c401c8e83 AS production

# Fail closed for cross-origin browser access when deploy configuration omits
# CORS_ORIGINS. Production deployments that need cross-origin access must set
# the exact allowed origin list explicitly.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CORS_ORIGINS=https://cors.invalid

WORKDIR /app

# msgpack and setuptools are inherited tooling rather than backend runtime
# dependencies. Remove those base-image copies before the application runs;
# the production dependency graph itself lives in /opt/venv.
RUN python -m pip uninstall -y msgpack setuptools

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

# Preserve the historical local-development convenience while keeping the
# production image fail-closed.
ENV CORS_ORIGINS=*

USER root
RUN pip install --no-cache-dir "pytest>=8,<9" pytest-cov "ruff==0.9.*"
USER appuser

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]