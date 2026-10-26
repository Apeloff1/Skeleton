# ============================================================================
# Tutolage Backend Dockerfile
# ============================================================================
# Build context MUST be the repository root because the image vendors
# skeleton/ alongside backend/.
# ============================================================================

# Stage 1: dependency builder. Alpine keeps the builder/runtime ABI aligned
# so compiled wheels and native extensions do not cross a glibc/musl boundary.
FROM python:3.15-alpine@sha256:d44b1254cb92329418d164b22b20d86bbd3869d48e80e09e476531a409a728bb AS builder

WORKDIR /app

# Copy dependency metadata before installing the build toolchain. Keeping the
# toolchain and dependency transaction in one layer avoids repeatedly copying
# a large intermediate filesystem on Docker daemons that use the vfs driver.
COPY backend/pyproject.toml backend/requirements.txt ./

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PIP_DISABLE_PIP_VERSION_CHECK=1
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca PIP_CERT=/run/secrets/proxy_ca NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    apk add --no-cache --virtual .build-deps \
      build-base cargo libffi-dev openssl-dev linux-headers \
    && pip install --no-cache-dir uv==0.12.4 \
    && uv venv /opt/venv \
    && uv pip install --python /opt/venv/bin/python -r requirements.txt \
    && uv pip install --python /opt/venv/bin/python "msgpack>=1.2.1" "setuptools>=78.1.1" \
    && apk del .build-deps \
    && rm -rf /root/.cache /tmp/*

# Prepare the existing flat backend layout in a source-only stage. The
# Dockerfile-specific context allowlist excludes secrets and runtime data.
FROM python:3.15-alpine@sha256:d44b1254cb92329418d164b22b20d86bbd3869d48e80e09e476531a409a728bb AS runtime-source
WORKDIR /source
COPY . .
RUN mv backend /runtime \
    && mv skeleton machine docs /runtime/ \
    && test ! -e /runtime/scripts/check_jeeves_training_modules.py \
    && test ! -L /runtime/scripts/check_jeeves_training_modules.py \
    && cp scripts/check_jeeves_training_modules.py /runtime/scripts/check_jeeves_training_modules.py

# Stage 2: Production
FROM python:3.15-alpine@sha256:d44b1254cb92329418d164b22b20d86bbd3869d48e80e09e476531a409a728bb AS production

# Apply the current Alpine security repository updates to the runtime layer.
# The pinned base remains reproducible while util-linux and other OS packages
# receive fixes released after the base-image snapshot.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca PIP_CERT=/run/secrets/proxy_ca NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    apk upgrade --no-cache

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

# Release version (from the repo-root VERSION file, passed by the release
# workflow). Exposed as APP_VERSION so /api/metrics codedock_build_info reports it.
ARG APP_VERSION=dev
ARG VCS_REF=unknown
ENV APP_VERSION=$APP_VERSION
LABEL org.opencontainers.image.version=$APP_VERSION \
      org.opencontainers.image.revision=$VCS_REF \
      org.opencontainers.image.source=https://github.com/Apeloff1/Skeleton \
      org.opencontainers.image.title=skeleton-backend

WORKDIR /app

RUN addgroup -S -g 10001 appuser \
    && adduser -S -D -u 10001 -G appuser -s /sbin/nologin appuser \
    && mkdir -p /app/data \
    && chown appuser:appuser /app/data

COPY --from=builder --chown=appuser:appuser /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY --from=runtime-source --chown=appuser:appuser /runtime/ .

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
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca PIP_CERT=/run/secrets/proxy_ca NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    python -m ensurepip --upgrade \
    && python -m pip install --no-cache-dir "pytest>=8,<9" pytest-cov "ruff==0.9.*"
USER appuser

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]
