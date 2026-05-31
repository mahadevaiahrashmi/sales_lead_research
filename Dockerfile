# Local web UI (Gradio) for Sales Lead Research.
#
#   docker compose up --build      ->  http://localhost:7860
#
# The image installs the package with `uv` (using uv.lock for a
# reproducible build), then runs app.py. On first start the entrypoint
# seeds a demo customer database so the UI shows real account matches.

FROM python:3.12-slim-bookworm

# Bring in the `uv` binary — the project's dependency manager — for fast,
# reproducible installs straight from uv.lock.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    SALES_DB_PATH=/app/data/customers.sqlite \
    GRADIO_SERVER_NAME=0.0.0.0 \
    GRADIO_SERVER_PORT=7860

# 1) Install third-party dependencies only — cached unless pyproject /
#    uv.lock change (the heavy layer: gradio, httpx, pypdf, ...).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 2) Install the project itself (fast; reruns only when src changes).
COPY src ./src
RUN uv sync --frozen --no-dev

# 3) Application entry point, demo-data seeder, and startup script.
COPY app.py docker-entrypoint.sh ./
COPY scripts ./scripts
RUN chmod +x docker-entrypoint.sh

EXPOSE 7860
ENTRYPOINT ["./docker-entrypoint.sh"]
