---
agent-notes:
  ctx: "codebase structural overview for humans and agents"
  deps: []
  state: active
  last: "sato@2026-05-29"
  key: ["UPDATE when adding packages, modules, or changing public APIs"]
---
# Code Map

Structural overview of the codebase. Read this before diving into code. **Keep it up to date** — when you add a package/module or change a public API, update this file.

## Architecture at a Glance

```
User query
   │
   ▼
chat/intent.parse(query) ── Intent(kind, company_name)      [single NL parser]
   │  kind == "lookup"
   ▼
discovery/                                                  [find the family tree]
   ├── edgar.py        name → CIK → latest annual report (10-K / 20-F)
   │                   → Exhibit 21 → recursive SubsidiaryNode tree
   └── web_fallback.py non-SEC filers: web search → HTML/PDF subsidiary list
   │
   ▼  list of (subsidiary name, jurisdiction)
matching/                                                   [which are customers?]
   ├── store.py   candidate_account_ids() BLOCKING → classify_match → Matches
   ├── names.py   normalise / jaccard / classify (pure)
   └── present.py Matches → "[Account: …]" / account-cell text
   │
   ▼
Front-ends: cli.py (rich tree) · api.py (FastAPI REST + static JS)  +  enriched CSV
```

The customer database is opened **read-only**; a **token inverted index** is built in memory once at open time so each lookup scores only candidate rows, not the whole table.

## Dependency Graph

```
matching/names.py ───── (pure: stdlib only — foundational)
matching/store.py ───── depends on names           (+ in-memory token index)
matching/present.py ─── depends on store (Matches)
matching/init_db.py ─── stdlib (sqlite3, csv)

chat/intent.py ──────── (pure: re only — single source of NL patterns)

discovery/edgar.py ──── httpx, beautifulsoup4
discovery/web_fallback ─ httpx, beautifulsoup4, pypdf
discovery/cache.py ──── httpx
discovery/__init__.py ─ re-exports the public discovery API

cli.py ──────────────── chat.intent · discovery · matching.store · matching.present
api.py (FastAPI) ────── discovery · matching.store · matching.present
__main__.py ─────────── cli · discovery · matching.init_db · matching.store
```

## Package / Module Summaries

### `chat/` — natural-language intent
**Purpose:** turn a raw query into a typed intent. The **single** home for the NL patterns (the CLI delegates here; the API takes a query string directly).

| Module | Key Exports | Notes |
|--------|------------|-------|
| `chat/intent.py` | `parse(query) -> Intent`, `Intent(kind, company_name)` | `kind` ∈ `lookup`/`exit`/`empty`/`unknown`; regex-only; input length-capped |

### `discovery/` — corporate-hierarchy lookup
**Purpose:** given a company name, return its parent/subsidiary tree from public sources.

| Module | Key Exports | Notes |
|--------|------------|-------|
| `discovery/edgar.py` | `build_client`, `resolve_cik`, `search_companies`, `latest_annual_report`, `latest_10k_accession`, `exhibit_21_url`, `find_exhibit_21`, `parse_exhibit_21`, `fetch_subsidiary_tree`, `find_parent_company`, `SubsidiaryNode`, error classes | 10-K, falling back to 20-F; recursive walk (`max_depth=2`); `latest_annual_report` returns `(accession, form, filing_date)` |
| `discovery/web_fallback.py` | `web_search_subsidiaries` | Non-SEC filers: DuckDuckGo → URL ranking → HTML/PDF extraction; jurisdiction + financial-noise heuristics |
| `discovery/cache.py` | `cached_get` | File-based HTTP cache with TTL; internal (not re-exported) |
| `discovery/__init__.py` | public API re-exports | Only these names are for outside callers; lower-level helpers import from `discovery.edgar` directly |

### `matching/` — customer-database matching
**Purpose:** decide which discovered subsidiaries are existing customers.

| Module | Key Exports | Notes |
|--------|------------|-------|
| `matching/names.py` | `normalise_name`, `jaccard_similarity`, `classify_match` | Pure. `exact` / `close (Jaccard ≥ 0.8)` / `none` |
| `matching/store.py` | `CustomerStore`, `Matches`, `open_store`, `candidate_account_ids`, `lookup_by_name`, `lookup_with_confidence` | Read-only connection + in-memory token index; **blocking** then score |
| `matching/present.py` | `account_cell`, `tree_account_suffix`, `is_existing_customer` | Pure. Renders `Matches` for the table/tree |
| `matching/init_db.py` | `init_db(db_path, seed_csv=None)` | Creates the customer schema; refuses to overwrite |

### Front-ends
| File | Key Exports | Notes |
|------|------------|-------|
| `cli.py` | `run_repl(input_lines, output, *, client, output_dir, store)` | Chat loop: 2 confirmation gates, recursive tree with `[Account: …]` annotations, match summary, enriched CSV, web-fallback path |
| `api.py` | FastAPI `app`; `/health`, `/api/search`, `/api/lookup`, `/api/web-lookup` | REST API over the core; JSON tree + account matches; OpenAPI at `/docs` |
| `__main__.py` | `main(argv)` | `sales-lead-research` console script: REPL default + `init-db`; opens the store, warns in plain English if absent |
| `static/index.html` | — | Static vanilla-JS front-end served by the API at `/` |

## Test Inventory

| Test file | Focus |
|-----------|-------|
| `test_names.py` | normalise / jaccard / classify |
| `test_store.py` | read-only store, lookups, **blocking candidates** |
| `test_present.py` | account-cell / tree-suffix rendering |
| `test_intent.py`, `test_nlq.py` | intent parsing + `extract_company_name` shim |
| `test_edgar.py`, `test_20f.py` | CIK resolve, annual report (10-K + 20-F), Exhibit 21, `latest_annual_report` |
| `test_exhibit21.py` | Exhibit 21 HTML parsing |
| `test_recursive.py`, `test_parent_resolution.py` | recursive tree + reverse parent search |
| `test_web_fallback.py`, `test_non_sec_filer.py` | web-search fallback (HTML/PDF) |
| `test_cache.py` | HTTP cache TTL |
| `test_init_db.py` | DB creation / seeding |
| `test_cli.py` | full chat loop: gates, tree, **account_id wiring**, freshness, chit-chat |
| `test_api.py` | FastAPI endpoints: health, search, recursive lookup (JSON), customer match, web fallback |
| `test_evaluate.py` | precision / recall / F1 metric helpers |

Run: `uv run pytest`.

## Key Type Flow

```
query: str
  → Intent(kind, company_name: str | None)
  → CIK: str
  → (accession, form, filing_date): tuple[str, str, str]
  → Exhibit 21 URL: str
  → SubsidiaryNode(name, jurisdiction, children)        # recursive tree
  → per subsidiary: candidate_account_ids → Matches(exact, close)
  → account_cell / tree_account_suffix → rich tree row / JSON / CSV
```

## Config Structure

| Setting | Where | Purpose |
|---------|-------|---------|
| `SALES_DB_PATH` | env var | Customer DB path (default `data/customers.sqlite`). Build it with `init-db` or `scripts/init_dummy_db.py` |
| `USER_AGENT` | `cli.py` / `api.py` | Sent on SEC requests for fair-use compliance |
| `APP_PORT` | `api.py` (container) | `8000` when serving the REST API + UI |
