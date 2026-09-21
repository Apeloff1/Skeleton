ARG PYTHON_IMAGE=python:3.14-alpine@sha256:c6ead215bfd31f1e433d968853b7a769989117115b728874824e6c0a27cb96fc
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Refresh the pinned Alpine base to the currently fixed security packages.
RUN apk upgrade --no-cache

RUN addgroup -S -g 10001 appuser \
    && adduser -S -D -u 10001 -G appuser -s /sbin/nologin appuser

COPY --chown=appuser:appuser pyproject.toml README.md ./
COPY --chown=appuser:appuser skeleton ./skeleton
COPY --chown=appuser:appuser machine/manifest.json ./machine/manifest.json
COPY --chown=appuser:appuser machine/architecture.json ./machine/architecture.json
COPY --chown=appuser:appuser machine/ai_app_construction.json ./machine/ai_app_construction.json
COPY --chown=appuser:appuser machine/capability_interfaces.json ./machine/capability_interfaces.json
COPY --chown=appuser:appuser machine/ai_runtime_schemas.json ./machine/ai_runtime_schemas.json
COPY --chown=appuser:appuser machine/ai_implementation_handoff.json ./machine/ai_implementation_handoff.json
COPY --chown=appuser:appuser machine/ai_closure_evidence.json ./machine/ai_closure_evidence.json
COPY --chown=appuser:appuser docs/AI_APP_CONSTRUCTION_MANUAL.md ./docs/AI_APP_CONSTRUCTION_MANUAL.md

# The installer toolchain is build-time only. pip 26.2+ also carries vendored
# packages plus an embedded CycloneDX SBOM under pip/_vendor; leaving that
# tree in a production image makes those vendored copies part of the runtime
# attack surface and causes image scanners to report them independently of
# the application's installed packages. Install first, then remove the full
# installer/toolchain surface from the final runtime.
RUN pip install --no-cache-dir . \
    && pip uninstall -y msgpack setuptools \
    && rm -rf /usr/local/lib/python3.14/site-packages/msgpack* \
              /usr/local/lib/python3.14/site-packages/setuptools* \
              /usr/local/lib/python3.14/site-packages/pkg_resources* \
              /usr/local/lib/python3.14/site-packages/pip \
              /usr/local/lib/python3.14/site-packages/pip-*.dist-info \
              /usr/local/bin/pip*

USER appuser

EXPOSE 8001

# Probe only the public liveness contract and use Python's standard library so
# the runtime image does not gain curl/apt packages solely for health checks.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/v1/health/live', timeout=5).read()" || exit 1

CMD ["uvicorn", "skeleton.api.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]
