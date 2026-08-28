# ============================================================================
# Tutolage Backend Dockerfile
# ============================================================================
# Build: docker build -f backend/Dockerfile -t tutolage-backend .   (repo root!)
# Run:   docker run -p 8001:8001 tutolage-backend
#
# NOTE (B5): the build context is the REPO ROOT (see docker-compose.yml), so
# both backend/ and skeleton/ are copied in. skeleton/ lands at /app/skeleton
# and /app is already on sys.path, so the guarded shims in
# services/{cag,mag}.py resolve to the canonical skeleton.memory modules in
# production too. Building with context ./backend still works — the skeleton
# COPY would fail, so root context is now required.
# ============================================================================

# Stage 1: Builder with uv
FROM python:3.11-slim AS builder

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY backend/pyproject.toml ./
COPY backend/requirements.txt ./

# Create venv and install dependencies
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN uv pip install -r requirements.txt

# Stage 2: Production
FROM python:3.11-slim AS production

WORKDIR /app

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application: backend code + the skeleton package (B5 vendoring)
COPY backend/ .
COPY skeleton/ ./skeleton/

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8001/api/health || exit 1

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]

# Stage 3: Development
FROM production AS development

USER root
RUN pip install pytest pytest-cov ruff
USER appuser

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
