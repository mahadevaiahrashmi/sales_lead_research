---
agent-notes: { ctx: "technical user manual: run, API reference, config, Docker, EKS", deps: [src/sales_lead_research/api.py, Dockerfile, k8s/], state: active, last: "sato@2026-05-31" }
---

# Sales Lead Research — User Manual (technical)

CLI + REST API that, given a company name, resolves its corporate hierarchy from
SEC EDGAR (10-K Exhibit 21; 20-F fallback; web fallback for non-filers) and
matches each entity against a customer database, flagging existing customers.

- Architecture & scaling design: [`docs/architecture.md`](architecture.md)
- Package layout / public APIs: [`docs/code-map.md`](code-map.md)
- Decisions: [`docs/adrs/`](adrs/) · Known debt: [`docs/tech-debt.md`](tech-debt.md)

## Requirements

- Python 3.12 and [`uv`](https://docs.astral.sh/uv/).
- Optional: a Docker-compatible runtime (Docker Desktop, or Colima on macOS) for
  containers; a Kubernetes cluster (e.g. EKS) for deployment.

## Install

```bash
git clone git@github.com:mahadevaiahrashmi/sales_lead_research.git
cd sales_lead_research
uv sync          # installs deps + the package (dev group includes pytest)
```

## Run

### Tests
```bash
uv run pytest                 # ~453 tests
uv run python scripts/eval_matching.py   # precision/recall/F1 report
```

### CLI (terminal chat)
```bash
uv run python -m sales_lead_research        # interactive lookup REPL
# console script equivalent: sales-lead-research
```

### Customer database (CLI)
```bash
# create an empty DB, or seed it from a CRM export:
uv run python -m sales_lead_research init-db --seed customers.csv
# or generate the 47-row fictional demo DB:
uv run python scripts/init_dummy_db.py
```

### REST API + web UI
```bash
uv run uvicorn sales_lead_research.api:app --host 0.0.0.0 --port 8000
#   UI:   http://localhost:8000
#   docs: http://localhost:8000/docs        (interactive OpenAPI/Swagger)
```

## Customer database

- **Read-only SQLite** opened at `SALES_DB_PATH` (default `data/customers.sqlite`).
- **Schema:** `account_id` (PK), `company_name`, `parent_id`, `ultimate_parent_id`,
  `location`, `country`, `tax_number`, `zip_code`.
- **Sample list:** `src/sales_lead_research/static/sample-customers.csv` (also
  served at `/sample-customers.csv`); 47 fictional companies that match the demo.
- The DB is **gitignored** (regenerable, and sensitive — it can hold tax numbers).

## REST API reference

| Method & path | Purpose | Key params / body | Returns |
|---|---|---|---|
| `GET /health` | Liveness/readiness probe | — | `{"status":"ok"}` |
| `GET /api/search` | Resolve a name to candidate filers | `q=<name or ticker>` | `{query, matches:[{name,cik}], message}` |
| `GET /api/lookup` | Recursive tree + customer matches | `company=<title>&cik=<10-digit>` | `{company, cik, source_url, form, filing_date, subsidiaries_total, customers_matched, tree, flat[]}` |
| `GET /api/web-lookup` | Non-SEC fallback (web search) | `company=<name>` | `{company, parent, source_url, subsidiaries_total, customers_matched, flat[]}` |
| `GET /api/customers` | Is a customer list loaded? | — | `{loaded, rows}` |
| `POST /api/customers` | Load customer list from CSV | body = CSV text (needs `account_id` + `company_name`) | `{loaded, rows}` — **overwrites**, writes to `SALES_DB_PATH` |

Each node in `tree` / row in `flat` carries `account_ids` (confirmed customer
matches) and `possible_account_ids` (close "verify" matches).

```bash
# examples
curl 'http://localhost:8000/health'
curl 'http://localhost:8000/api/search?q=FedEx'
curl 'http://localhost:8000/api/lookup?company=FEDEX%20CORP&cik=0001048911'
curl --data-binary @customers.csv -H 'Content-Type: text/csv' \
     http://localhost:8000/api/customers
```

## Configuration (environment variables)

| Var | Default | Meaning |
|---|---|---|
| `SALES_DB_PATH` | `data/customers.sqlite` | Path to the customer SQLite DB |
| `APP_PORT` | `8000` | Port uvicorn binds in the container |
| `USER_AGENT` | set in code | Sent on SEC requests for fair-use compliance |

## Docker

```bash
docker compose up --build      # -> http://localhost:8000
```
- Compose maps port 8000, persists the DB in a named volume, and the entrypoint
  **seeds the demo DB on first run** if none exists.
- **macOS / Colima:** use the hyphenated `docker-compose`, and if host port 8000
  is already in use, remap it in `docker-compose.yml` (e.g. `"8080:8000"`).
- **Real data:** bind-mount your own SQLite file at `SALES_DB_PATH`, or point it
  at an external database.

## Kubernetes / EKS

Manifests in [`k8s/`](../k8s/): a Deployment (with `/health` liveness + readiness
probes and resource requests/limits), a ClusterIP Service, an ALB Ingress, and a
CPU HorizontalPodAutoscaler.

```bash
# build for the cluster arch, push to ECR, set the image in k8s/deployment.yaml:
kubectl apply -k k8s/
kubectl get pods,svc,ingress,hpa -l app=sales-lead-research
```
- Each pod seeds its own demo DB on start. For **real, shared** customer data use
  a PersistentVolume, an external database, or a direct CRM connection (not the
  per-pod upload).
- The ALB Ingress needs the AWS Load Balancer Controller; the HPA needs
  metrics-server.

## How it works (in brief)

`name → CIK → latest annual report (10-K, else 20-F) → Exhibit 21 → recursive
subsidiary tree`; non-filers fall back to web search + HTML/PDF extraction.
Matching normalises names (strips legal suffixes) and classifies each candidate
as `exact` / `close` (token-set Jaccard ≥ 0.8) / `none`, using an in-memory
**token-index blocking** step so lookups score only candidate rows. The
production-scale design (persistent index, ANN, multilingual, calibrated
scoring) is in [`docs/architecture.md`](architecture.md) §9.

## Conventions

TDD, conventional commits, and a **mandatory plain-English rule for user-facing
text** — see `CLAUDE.md`. To rebuild an equivalent system from the repo's own
artifacts, see [`docs/regeneration-kit.md`](regeneration-kit.md).
