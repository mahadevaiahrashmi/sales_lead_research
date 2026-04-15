<!-- agent-notes: { ctx: "quickstart MVP backlog for sales lead research CLI", deps: [CLAUDE.md], state: active, last: "pat@2026-04-15" } -->
# Backlog

**Product:** Sales Lead Research — CLI chat tool that takes a company name and prints its SEC-filed corporate hierarchy (parent + subsidiaries).
**User:** Internal sales team.
**Data source:** SEC EDGAR (10-K filings, Exhibit 21 = "Subsidiaries of the Registrant").

## Sprint 1 (MVP)

- [ ] **#1: CLI chat loop** — Run `sales-lead-research`, get a prompt, type a company name, see a placeholder tree come back, type another, or `exit` to quit. No network yet; proves the interface shape end-to-end.
- [ ] **#2: SEC EDGAR company lookup** — Given a company name, resolve it to a CIK via EDGAR's company tickers file, then fetch the most recent 10-K filing's index. Returns the Exhibit 21 URL (or a clear "not found" / "no 10-K" error). Pure function, tested against a recorded fixture.
- [ ] **#3: Exhibit 21 parse + tree render** — Fetch Exhibit 21, parse subsidiary names (and jurisdictions where present) out of the HTML/text, render as a tree via `rich.tree`. Wire into the CLI from #1 so `Apple` actually prints Apple Inc. with its subsidiaries underneath.

## Later

- Disambiguation when a company name matches multiple CIKs.
- Recursive walk: if a listed subsidiary is itself an SEC filer, pull its Exhibit 21 and nest.
- Parent-company resolution: detect when the queried company is itself a subsidiary and walk up.
- Caching of EDGAR responses (respect SEC fair-use: 10 req/s cap, User-Agent required).
- Fuzzy name matching / ticker fallback.
- Web chat UI (option b from discovery).
- Handling non-US parents that file 20-F instead of 10-K.
- Handling companies that don't file with the SEC at all (graceful fallback message).
