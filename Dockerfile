FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11.11 /uv /uvx /bin/

ENV UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 appuser \
    && useradd --uid 10001 --gid 10001 --create-home \
        --shell /usr/sbin/nologin appuser

WORKDIR /app

COPY --from=builder --chown=10001:10001 /app/.venv /app/.venv

USER 10001:10001

ENTRYPOINT ["nyc-taxi"]
CMD ["discover", "--lookback-months", "3"]
