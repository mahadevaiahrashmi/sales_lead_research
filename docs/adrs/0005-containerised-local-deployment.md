---
agent-notes: { ctx: "ADR: containerised local deployment of the Gradio web UI", deps: [Dockerfile, docker-compose.yml, app.py], state: active, last: "archie@2026-05-31" }
---

# ADR-0005: Containerised local deployment of the web UI

## Status

Accepted

## Context

The tool already runs three ways: a terminal chat, a local Gradio web UI on port
7860, and a standalone Hugging Face Space copy. Running the local web UI still
required a working Python 3.12 + uv environment on the host. We wanted a
one-command way to run the web UI locally that does not depend on the host's
Python setup, and that works without Docker Desktop (to avoid its licensing and
GUI overhead).

## Decision

Ship a container build for the Gradio web UI:

- `Dockerfile` based on `python:3.12-slim`, installing dependencies from
  `uv.lock` with `uv` for a reproducible image. No BuildKit-only features, so it
  builds on the classic builder too.
- `docker-entrypoint.sh` seeds the demo customer database on first run if none
  exists, then launches the app.
- `docker-compose.yml` maps port 7860 and persists the database in a named volume;
  a commented bind-mount shows how to supply a real customer list.
- `app.py` reads `GRADIO_SERVER_NAME` / `GRADIO_SERVER_PORT` from the environment
  — defaulting to `127.0.0.1` locally, set to `0.0.0.0` in the container so the
  host can reach it.
- The customer database stays **out of the image** (gitignored; seeded or mounted
  at runtime) so no customer data is baked into a shareable artifact.

Colima is the recommended runtime on macOS (lightweight, no Docker Desktop), but
any Docker-compatible runtime works.

## Consequences

### Positive

- `docker compose up --build` → working web UI on http://localhost:7860 with demo
  data seeded automatically; no host Python required.
- Reproducible (pinned via `uv.lock`); the same entry point serves locally and in
  the container via env vars.
- Customer data never ships inside the image.

### Negative

- Adds container files to maintain and an image build step.
- The Homebrew Docker CLI lacks the buildx plugin, so the BuildKit cache-mount
  optimisation was removed for compatibility (slightly slower rebuilds).

### Neutral

- The Hugging Face Space copy (`hf_space/`) remains a separate standalone
  deployment path (tracked in `docs/tech-debt.md`, TD-001).
