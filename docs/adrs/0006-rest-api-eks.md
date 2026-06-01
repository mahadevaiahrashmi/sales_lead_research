---
agent-notes: { ctx: "ADR: FastAPI REST API + JS front-end on EKS, replacing Gradio", deps: [src/sales_lead_research/api.py, k8s/, docs/adrs/0005-containerised-local-deployment.md], state: active, last: "archie@2026-05-31" }
---

# ADR-0006: REST API (FastAPI) + JS front-end on Kubernetes (EKS)

## Status

Accepted — supersedes the Gradio specifics of [ADR-0005](./0005-containerised-local-deployment.md).

## Context

The web UI was a Gradio app, with a separate Hugging Face Space copy. Gradio is
quick for demos but couples the UI to the server, doesn't fit standard
Kubernetes ingress / health-check machinery cleanly, and isn't the shape of
interface a production service exposes. We want a conventional REST API any
front-end can consume, and a deployment that fits AWS EKS.

## Decision

Replace Gradio with:

- A **FastAPI** REST API (`sales_lead_research/api.py`) over the existing
  discovery + matching core. Endpoints: `GET /health` (probe), `GET /api/search`
  (disambiguation), `GET /api/lookup` (recursive tree + customer matches as
  JSON), `GET /api/web-lookup` (non-SEC fallback). Pydantic response models;
  auto-generated OpenAPI docs at `/docs`.
- A **static, dependency-free front-end** (`static/index.html`, vanilla JS)
  served by the same app at `/`. Keeps the deployable a single image (no Node
  build step); a React/Next front-end can replace it later without touching the
  API contract.
- **uvicorn** as the server; the container serves on port 8000.
- **EKS manifests** in `k8s/` — a Deployment with `/health` liveness + readiness
  probes and resource requests/limits, a ClusterIP Service, an ALB Ingress, and
  a CPU HorizontalPodAutoscaler — applied with `kubectl apply -k k8s/`.

Gradio, the `huggingface-hub` dependency, the Gradio module, and the `hf_space/`
Space copy are removed. The container entrypoint still seeds the demo database
on first run.

## Consequences

### Positive

- A real REST contract any client can call; Kubernetes-native health probes and
  horizontal scaling; OpenAPI docs for free.
- Still a single image (API + static front-end), trivially deployable to EKS.
- Directly matches the target stack: API design, containers, Kubernetes/EKS.

### Negative

- Two things to evolve (API + front-end) instead of one Gradio script; the
  vanilla-JS front-end is intentionally minimal.
- `/api/lookup` still opens the customer store per request (carried from
  `docs/tech-debt.md` TD-002).

### Neutral

- The CLI is unchanged, and the discovery + matching core is untouched — only the
  presentation / transport layer changed.
