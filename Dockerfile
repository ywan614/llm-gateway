FROM ghcr.io/astral-sh/uv:0.11.7 AS uv
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app
COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

RUN useradd --create-home --uid 10001 gateway \
    && mkdir -p /app/logs \
    && chown -R gateway:gateway /app
USER gateway

ENV PATH="/opt/venv/bin:$PATH"
CMD ["uvicorn", "llm_central_gateway.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
