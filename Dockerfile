ARG PYTHON_IMAGE=python:3.14-slim@sha256:83ff1d245a3d57d04152252d3ef9cb361494d0b3395abd65a5ebe91c401c8e83
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

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