ARG PYTHON_IMAGE=python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6
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

RUN pip install --no-cache-dir .

USER appuser

EXPOSE 8001

CMD ["uvicorn", "skeleton.api.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]
