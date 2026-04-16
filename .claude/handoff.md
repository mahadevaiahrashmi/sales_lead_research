# Session Handoff

**Created:** 2026-04-16
**Sprint:** All sprints complete (sprint 1 + sprint 2 + unsprinted items)
**Session summary:** Added web search fallback for non-SEC filers (DHL, Samsung), fixed 3-column Exhibit 21 parsing (Microsoft), added web fallback to both Gradio UIs, performed UAT against live SEC EDGAR, created user flow and architecture diagrams.

## What Was Done

### This session (continuation)
- **Web search fallback for non-SEC filers:** New `src/sales_lead_research/web_fallback.py` — DuckDuckGo HTML search with 3-strategy HTML structure extraction (tables, lists under headings, h3/h4 as division names). No API key required.
- **3-column Exhibit 21 fix:** `parse_exhibit_21()` now handles spacer columns (Microsoft's format) by extracting non-empty cells.
- **Expanded header keywords:** Added "name", "whereincorporated", "stateorcountryofincorporationororganization" to `_HEADER_KEYWORDS`.
- **Improved error messages:** `NoExhibit21` and `No10KFiled` now include descriptive text instead of raw accession numbers.
- **Web fallback in CLI:** `cli.py` offers web search when `CompanyNotFound`, renders tree from web results.
- **Web fallback in Gradio UI:** Both `app.py` and `hf_space/app.py` fall back to web search when no SEC match found. Returns 6-tuple with web result info.
- **UAT completed:** Tested live against Apple, FedEx, Microsoft, Toyota, DHL, Samsung, AAPL ticker — all working.
- **User flow diagram:** `docs/user-flow.png` + `docs/user-flow.html` (interactive Mermaid with Anthropic theme).
- **Architecture diagram:** `docs/architecture.png` — full system architecture rendered via mermaid.ink API.

### Prior in this session
- Recursive subsidiary walk (#4), 20-F support (#9), non-SEC filer fallback (#10), parent-company resolution (#5)
- Anthropic website theme, natural language query support
- All 11 issues closed

## Current State

- **Branch:** `main` (1 commit ahead of origin — needs push)
- **Last commit:** `e2619f0 docs: add user flow and architecture diagrams`
- **Uncommitted changes:** None (stray UAT output files in root: `3m_co_subsidiaries.csv`, `DHL.csv`, `DHL.html`, `DHL.md`, `apple_inc._subsidiaries.csv`, `fedex.csv`, `fedex_corp_subsidiaries.csv`, `microsoft_corp_subsidiaries.csv` — untracked, safe to delete or `.gitignore`)
- **Tests:** 130 passing across 9 test files
- **Board status:** All 11 issues CLOSED on GitHub

## Test Files

| File | Tests | Covers |
|------|-------|--------|
| `test_cli.py` | 28 | CLI REPL, fuzzy match, gates, tree, CSV |
| `test_edgar.py` | 22 | EDGAR lookup pipeline, ticker fallback |
| `test_exhibit21.py` | 11 | Exhibit 21 HTML parsing |
| `test_recursive.py` | 16 | Recursive subsidiary walk |
| `test_cache.py` | 7 | File-based HTTP response cache |
| `test_20f.py` | 7 | 20-F filing support |
| `test_non_sec_filer.py` | 5 | Non-SEC filer fallback message |
| `test_parent_resolution.py` | 5 | Parent company detection |
| `test_nlq.py` | 22 | Natural language query extraction |

## Key Files

| File | Purpose |
|------|---------|
| `src/sales_lead_research/edgar.py` | Full EDGAR pipeline: search, CIK, 10-K/20-F, Exhibit 21, parse, recursive tree, parent resolution |
| `src/sales_lead_research/cli.py` | REPL with EDGAR integration, NLQ extraction, web fallback, tree + CSV |
| `src/sales_lead_research/web_fallback.py` | DuckDuckGo web search fallback for non-SEC filers |
| `src/sales_lead_research/cache.py` | File-based HTTP response cache with TTL |
| `src/sales_lead_research/__main__.py` | CLI entry point |
| `app.py` | Local Gradio web UI (Anthropic theme, web fallback) |
| `hf_space/app.py` | Self-contained HF Spaces app (Anthropic theme, inlined web fallback) |
| `docs/user-flow.html` | Interactive Mermaid user flow diagram |
| `docs/user-flow.png` | Static user flow diagram |
| `docs/architecture.png` | System architecture diagram |

## What To Do Next (in order)

1. Read `docs/code-map.md` to orient
2. **Push latest commit** — `main` is 1 commit ahead of origin
3. **Clean up UAT artifacts** — add `*_subsidiaries.csv` and `DHL.*` to `.gitignore`, or delete them
4. **Add web_fallback tests** — `web_fallback.py` has no unit tests yet; mock DuckDuckGo responses and test all 3 extraction strategies
5. **Wire caching into CLI** — `cache.py` exists but `--cache-dir` flag isn't exposed
6. **Rate limiting** — SEC asks for max 10 req/s; important for large recursive walks
7. **CI pipeline** — GitHub Actions running pytest on push
8. **Update HF Space** — push latest changes (web fallback, diagrams) to HF Space repo

## Proxy Decisions (Review Required)
<!-- None this session -->

## Key Context

- **User preference:** archive, don't delete (move to `archive/` instead of `rm`)
- **`gh project` owner quirk:** always use explicit `--owner mahadevaiahrashmi`, not `@me`
- **User-Agent for SEC:** `Sales Lead Research (mahadevaiah.rashmi@gmail.com)`
- **HF Space:** theme/css must be in `Blocks()` constructor, not `launch()` — HF Spaces auto-launches
- **Gradio 6.0:** local app passes theme/css to `launch()` (deprecation warning if in `Blocks()`)
- **DuckDuckGo HTML search:** uses `html.duckduckgo.com/html/` endpoint, URLs encoded in `uddg=` query parameter
- **Microsoft Exhibit 21:** 3-column table with spacer column — parser extracts non-empty cells
- **`find_parent_company()` is slow:** scans all filers' Exhibit 21s — removed from automatic CLI flow, available for programmatic use only
- **No sprint/tracking docs exist:** `docs/sprints/` and `docs/tracking/` directories are empty; `docs/product-context.md` does not exist
