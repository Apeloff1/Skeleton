ARG PYTHON_IMAGE=python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# The pinned base digest can lag Debian security point releases. Apply
# available vendor fixes at build time, then discard package indexes so the
# runtime does not retain stale apt metadata.
RUN apt-get update \
    && apt-get upgrade -y \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --gid 10001 appuser \
    && useradd --create-home --uid 10001 --gid 10001 --shell /usr/sbin/nologin appuser

COPY --chown=appuser:appuser pyproject.toml README.md ./
COPY --chown=appuser:appuser skeleton ./skeleton

# setuptools is required only to build this project, not to serve it. msgpack
# is also not a declared runtime dependency. Remove vulnerable copies that are
# inherited from the base image after the application has been installed.
RUN pip install --no-cache-dir . \
    && pip uninstall -y msgpack setuptools

USER appuser

EXPOSE 8001

# Probe only the public liveness contract and use Python's standard library so
# the runtime image does not gain curl/apt packages solely for health checks.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/api/v1/health/live', timeout=5).read()" || exit 1

CMD ["uvicorn", "skeleton.api.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]