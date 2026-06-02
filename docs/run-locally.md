---
agent-notes: { ctx: "steps to start and stop the app locally (uvicorn, Docker/Colima, CLI)", deps: [Dockerfile, docker-compose.yml, src/sales_lead_research/api.py], state: active, last: "sato@2026-05-31" }
---

# Run / Stop the App Locally

Three ways to run it. Pick one. All commands run from the repo root.

> **Port note for this machine:** another app already uses port **8000**. So
> either run on a different port (shown below) or free 8000 first.

---

## Option A — Direct with uv (simplest, no Docker)

**Run**
```bash
# 1. (first time only) create the demo customer list so matches show up
uv run python scripts/init_dummy_db.py

# 2. start the API + web UI  (use 8001 if 8000 is busy; add --reload for dev)
uv run uvicorn sales_lead_research.api:app --host 127.0.0.1 --port 8001
```
Open **http://localhost:8001** · API docs at **/docs**.

**Stop**
- Press **Ctrl+C** in that terminal.
- If you started it in the background:
  ```bash
  pkill -f "uvicorn sales_lead_research"      # or: lsof -nP -iTCP:8001 -sTCP:LISTEN  then  kill <PID>
  ```

---

## Option B — Docker (via Colima)

**Run**
```bash
colima start                    # if the runtime isn't already up
docker-compose up -d --build    # builds the image, starts in the background
```
Open **http://localhost:8000**.
- If host port 8000 is busy, edit `docker-compose.yml` → `ports: ["8080:8000"]`,
  re-run, then use **http://localhost:8080**.
- Watch logs: `docker-compose logs -f web`

**Stop**
```bash
docker-compose down             # stop + remove the container
colima stop                     # optional: shut the VM down to free ~4 GB
```

> On macOS this setup uses **`docker-compose`** (hyphenated). `docker compose`
> (with a space) is not installed here.

---

## Option C — Terminal chat (CLI, no web server)

**Run**
```bash
uv run python -m sales_lead_research
```
**Stop** — type `exit` or press **Ctrl+C**.

---

## Verify it's up
```bash
curl http://localhost:8001/health      # -> {"status":"ok"}   (use your port)
```

## Troubleshooting
- **"Address already in use" / nothing on 8000** — another app holds the port.
  Use a different one (`--port 8001`) or remap in `docker-compose.yml`.
- **Results show no account numbers** — no customer list is loaded. Seed the demo
  (`uv run python scripts/init_dummy_db.py`) or upload a CSV in the web UI.
- **`docker: unknown command: docker compose`** — use the hyphenated
  `docker-compose`.
- **Docker says it can't reach the daemon** — run `colima start` first.
