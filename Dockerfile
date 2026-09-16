ARG PYTHON_IMAGE=python:3.14-alpine@sha256:05b2b8b732ecd268fee8727a369f936f022d1321b59befd13c30ede22769dcdc
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

# setuptools is required only to build this project, not to serve it. msgpack
# is also not a declared runtime dependency. Remove vulnerable copies that are
# inherited from the base image after the application has been installed.
RUN pip install --no-cache-dir . \
    && pip uninstall -y msgpack setuptools || true \
    && rm -rf /usr/local/lib/python3.14/site-packages/msgpack* \
              /usr/local/lib/python3.14/site-packages/setuptools* \
              /usr/local/lib/python3.14/site-packages/pkg_resources*

USER appuser

EXPOSE 8001

# Probe only the public liveness contract and use Python's standard library so
# the runtime image does not gain curl/apt packages solely for health checks.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/v1/health/live', timeout=5).read()" || exit 1

CMD ["uvicorn", "skeleton.api.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]
