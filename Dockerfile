# REST API + web UI (FastAPI) for Sales Lead Research.
#
#   docker compose up --build      ->  http://localhost:8000
#
# The image installs the package with `uv` (using uv.lock for a
# reproducible build), then serves the FastAPI app with uvicorn. On first
# start the entrypoint seeds a demo customer database so matches show up.

FROM python:3.12-slim-bookworm

# Bring in the `uv` binary — the project's dependency manager — for fast,
# reproducible installs straight from uv.lock.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    SALES_DB_PATH=/app/data/customers.sqlite \
    APP_PORT=8000

# 1) Install third-party dependencies only — cached unless pyproject /
#    uv.lock change (the heavy layer: fastapi, uvicorn, httpx, pypdf, ...).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) Install the project itself (fast; reruns only when src changes).
COPY src ./src
RUN uv sync --frozen --no-dev

# 3) Startup script + demo-data seeder (the app itself ships in the package).
COPY docker-entrypoint.sh ./
COPY scripts ./scripts
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
