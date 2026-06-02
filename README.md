<!-- agent-notes: { ctx: "public README for the Sales Lead Research product", deps: [docs/user-guide.md, docs/run-locally.md, docs/code-map.md], state: active, last: "claude@2026-06-02" } -->

# Sales Lead Research

**Enter a company name and see its whole corporate family — its parent and the smaller companies it owns — with the ones you already sell to flagged by account number.**

When a new lead comes in, this tool pulls the company's parent/subsidiary structure from its latest public annual report, then checks each of those companies against your customer list. Instead of a cold call, you can walk in warm: *"we already work with your parent company — here's the account history."*

It runs two ways: as a **web app** (a chat window with saved history and customer-list upload) or as a **terminal chat** for quick local lookups.

---

## What it does

1. You type a company name (for example, **FedEx**).
2. It finds that company's latest annual report filed with the U.S. securities regulator (SEC EDGAR) and reads the exhibit that lists its subsidiaries.
3. It shows the corporate family as an indented tree — parent on top, the companies it owns underneath.
4. It checks every company in that tree against **your** customer list and tags each one:
   - **customer** (with the account number) — you already sell to them,
   - **possibly a customer — verify** — the name is a near-match, worth a quick check,
   - **not a customer** — a fresh lead.
5. The result also shows **which report it came from and when**, so you can judge how current it is, and it can be exported to a spreadsheet.

If a company doesn't file with the U.S. regulator (common for non-US firms), the tool offers to **search the web** and pull what it can from the company's published reports instead.

There's a friendly, non-technical walkthrough in **[docs/user-guide.md](docs/user-guide.md)**.

---

## Quick start

Prerequisites: Python 3.12 and the [`uv`](https://docs.astral.sh/uv/) package manager. All commands run from the repo root.

```bash
# 1. (first time only) create a small demo customer list so matches show up
uv run python scripts/init_dummy_db.py

# 2a. run the web app
uv run uvicorn sales_lead_research.api:app --host 127.0.0.1 --port 8001
#     then open http://localhost:8001   (interactive API docs at /docs)

# 2b. …or run the terminal chat instead
uv run python -m sales_lead_research
```

In the web app, type a company name in the box at the bottom. Use **"Upload customer list"** in the left panel to load your own customers, or **"download a sample"** to see the expected format. In the terminal chat, type a company name and press Enter; type `exit` to quit.

Other ways to run it (Docker via Colima, freeing port 8000, troubleshooting) are in **[docs/run-locally.md](docs/run-locally.md)**.

---

## Your customer list

The tool can only flag existing customers if it has your customer list. Upload a spreadsheet in the web app, or seed the demo with the command above.

The spreadsheet needs at least two columns — an **account number** and a **company name**. Other columns (country, location, tax id, …) are optional. Each upload **replaces** the previous list.

The list is stored locally on the machine running the tool (`data/customers.sqlite` by default; override with the `SALES_DB_PATH` environment variable). Real customer data can include tax numbers — treat it as sensitive. For company-wide use, IT may prefer to connect the tool to your customer system directly rather than uploading a file.

---

## How it fits together

```
company name
   → latest annual report (10-K, or 20-F) on SEC EDGAR
   → the subsidiary-list exhibit (Exhibit 21)
   → recursive parent/subsidiary tree
   → match each name against your customer list
   → tagged tree + match summary + exportable spreadsheet
```

The customer list is opened read-only, and a lookup index is built once in memory so each match scores only plausible candidates rather than the whole list. For a module-by-module map of the code, see **[docs/code-map.md](docs/code-map.md)**; for the broader design, **[docs/architecture.md](docs/architecture.md)** and the decision records in **[docs/adrs/](docs/adrs/)**.

---

## Development

```bash
uv run pytest        # run the test suite
```

| Doc | What's in it |
|-----|--------------|
| [docs/user-guide.md](docs/user-guide.md) | Plain-English guide for everyday (non-technical) use |
| [docs/run-locally.md](docs/run-locally.md) | Every way to start/stop the app, plus troubleshooting |
| [docs/code-map.md](docs/code-map.md) | Package structure, public functions, data flow — read first |
| [docs/architecture.md](docs/architecture.md) | System design and the path to a production matcher |
| [docs/tech-debt.md](docs/tech-debt.md) | Known limitations and what they'd cost to fix |
| [CLAUDE.md](CLAUDE.md) | How this repo is built and maintained with Claude Code |

---

## License

See [LICENSE](LICENSE).
