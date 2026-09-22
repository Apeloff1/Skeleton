# ============================================================================
# Tutolage Backend Dockerfile
# ============================================================================
# Build context MUST be the repository root because the image vendors
# skeleton/ alongside backend/.
# ============================================================================

# Stage 1: dependency builder. Alpine keeps the builder/runtime ABI aligned
# so compiled wheels and native extensions do not cross a glibc/musl boundary.
FROM python:3.14-alpine@sha256:016508ba505da24f7139765bc4bb669df4e88eb2f12eeadd571bf2f88d7533df AS builder

WORKDIR /app

# uv is a build-time tool only. Build dependencies are isolated to this stage.
RUN apk add --no-cache --virtual .build-deps \
      build-base \
      cargo \
      libffi-dev \
      openssl-dev \
      linux-headers \
    && pip install --no-cache-dir uv==0.12.4

COPY backend/pyproject.toml ./
COPY backend/requirements.txt ./

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN uv venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN uv pip install -r requirements.txt \
    && uv pip install "msgpack>=1.2.1" "setuptools>=78.1.1"

# Stage 2: Production
FROM python:3.14-alpine@sha256:016508ba505da24f7139765bc4bb669df4e88eb2f12eeadd571bf2f88d7533df AS production

# Apply the current Alpine security repository updates to the runtime layer.
# The pinned base remains reproducible while util-linux and other OS packages
# receive fixes released after the base-image snapshot.
RUN apk upgrade --no-cache

# pip is not required to serve the production application. pip 26.2+ carries
# vendored packages and an embedded CycloneDX SBOM under pip/_vendor, so keep
# that installer-only code out of the production runtime entirely. The
# development stage below can restore pip from Python's bundled ensurepip when
# developer-only tools are explicitly requested.
RUN rm -rf /usr/local/lib/python3.14/site-packages/pip \
           /usr/local/lib/python3.14/site-packages/pip-*.dist-info \
           /usr/local/bin/pip*

# Explicitly identify the application host as production so exec_guard can
# never be re-enabled by ALLOW_UNSAFE_CODE_EXECUTION inside this image. CORS
# also fails closed unless deployment supplies an explicit origin allowlist.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ENVIRONMENT=production \
    CORS_ORIGINS=https://cors.invalid

WORKDIR /app

RUN addgroup -S -g 10001 appuser \
    && adduser -S -D -u 10001 -G appuser -s /sbin/nologin appuser

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY --chown=appuser:appuser backend/ .
COPY --chown=appuser:appuser skeleton/ ./skeleton/
COPY --chown=appuser:appuser machine/manifest.json ./machine/manifest.json
COPY --chown=appuser:appuser machine/architecture.json ./machine/architecture.json
COPY --chown=appuser:appuser machine/ai_app_construction.json ./machine/ai_app_construction.json
COPY --chown=appuser:appuser machine/capability_interfaces.json ./machine/capability_interfaces.json
COPY --chown=appuser:appuser machine/state_topology.json ./machine/state_topology.json
COPY --chown=appuser:appuser machine/ai_capabilities.json ./machine/ai_capabilities.json
COPY --chown=appuser:appuser machine/ai_runtime_schemas.json ./machine/ai_runtime_schemas.json
COPY --chown=appuser:appuser machine/ai_implementation_handoff.json ./machine/ai_implementation_handoff.json
COPY --chown=appuser:appuser machine/ai_closure_evidence.json ./machine/ai_closure_evidence.json
COPY --chown=appuser:appuser docs/AI_APP_CONSTRUCTION_MANUAL.md ./docs/AI_APP_CONSTRUCTION_MANUAL.md

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
# production image fail-closed and permanently disabling host execution there.
ENV ENVIRONMENT=development \
    CORS_ORIGINS=*

USER root
RUN python -m ensurepip --upgrade \
    && python -m pip install --no-cache-dir "pytest>=8,<9" pytest-cov "ruff==0.9.*"
USER appuser

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
