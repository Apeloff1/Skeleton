FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY skeleton ./skeleton
COPY tests ./tests

RUN pip install --no-cache-dir -e ".[dev]"

EXPOSE 8001

CMD ["uvicorn", "skeleton.api.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]
