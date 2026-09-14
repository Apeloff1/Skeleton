FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp

WORKDIR /app

# Create the runtime identity before copying application files so ownership is
# explicit and the service never needs root at runtime.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin app

COPY pyproject.toml README.md ./
COPY skeleton ./skeleton

# Install only production dependencies. Tests, linters, audit tools, and the
# editable source mount do not belong in the runtime image.
RUN python -m pip install --no-cache-dir . \
    && rm -rf /root/.cache /tmp/*

USER 10001:10001

EXPOSE 8001

CMD ["uvicorn", "skeleton.api.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001", "--no-access-log"]
