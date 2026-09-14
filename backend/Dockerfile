# ============================================================================
# Tutolage Backend Dockerfile
# Build context MUST be the repository root because the image vendors
# skeleton/ alongside backend/.
# ============================================================================

ARG UV_VERSION=0.12.4

FROM python:3.11-slim AS builder
ARG UV_VERSION
WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:${UV_VERSION} /uv /usr/local/bin/uv
COPY backend/pyproject.toml ./
COPY backend/requirements.txt ./

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN uv pip install --no-cache -r requirements.txt

FROM python:3.11-slim AS production

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    HOME=/tmp

WORKDIR /app

# No package manager is invoked in the production stage: fewer binaries,
# packages, and transitive CVEs. Python stdlib performs the health check.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=10001:10001 backend/ ./
COPY --chown=10001:10001 skeleton/ ./skeleton/

USER 10001:10001

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/health', timeout=5).read()"]

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--no-access-log"]

FROM production AS development

USER root
RUN pip install --no-cache-dir "pytest>=8,<9" pytest-cov "ruff==0.9.*"
USER 10001:10001

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
