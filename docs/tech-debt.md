---
agent-notes:
  ctx: "technical debt register, persists across sprints"
  deps: []
  state: active
  last: "grace@2026-05-29"
  key: ["Grace tracks, Pat prioritizes against features"]
---
# Technical Debt Register

<!-- Grace maintains this register. Pat prioritizes debt against feature work. -->
<!-- This persists across sprints — board items get closed, but debt lives here until resolved. -->

**Project:** Sales Lead Research
**Last reviewed:** 2026-05-29

## Active Debt

| ID | Description | Incurred | Why (business reason) | Est. cost to fix | Risk if left | Status |
|----|-------------|----------|----------------------|-----------------|-------------|--------|
| TD-001 | `hf_space/app.py` is a standalone vendored copy of the web app: its own NL-pattern parser, EDGAR/web-fallback logic, and (now) it lacks the account_id / recursive / freshness improvements made in the package. | Pre-existing | HF Spaces deploy ran as a single self-contained file. | M (½–1 day) | Drift: the hosted demo diverges from the package; the parser de-dup (Gap 2) and Gap 1/3/4 features are not reflected there. | Open |
| TD-002 | Gradio `_account_cells` calls `open_store()` on every request, rebuilding the in-memory token index each time. | Gap 1/5 | Simplicity; the Gradio handlers are stateless functions. | S (½ day) | None at POC scale (47 rows). With a large customer list the per-request index build dominates latency — cache the store/index per process. | Open |
| TD-003 | `classify_match` uses token-set Jaccard, which treats morphological variants as different tokens ("Service" vs "Services", "Deutschland" vs "Germany"). Some intended near-matches fall below the 0.8 "close" threshold (e.g. seed `FedEx Corporate Service Inc.` is not flagged for `FedEx Corporate Services`). | Wave 2.1 | Boring, dependency-free matching for v1. | M | Recall gap on real, messy names. Consider stemming, character n-grams, or the production matcher in `docs/architecture.md` §9. | Open |
| TD-004 | Matching is exact/close only — no multilingual, phonetic, tax-id, or calibrated-confidence matching. | v1 scope | Out of scope for the SEC-EDGAR POC. | L | Won't meet the multilingual / millions-of-rows production goal. Designed in `docs/architecture.md` §9 (blocking + ANN + Splink). | Open |
| TD-005 | `fetch_subsidiary_tree` re-fetches `company_tickers.json` on each call and is depth-capped at 2; the reverse `find_parent_company` scans many filers. | Issue #4/#? | Correctness-first implementation. | S–M | Latency and SEC rate-limit pressure on deep/large lookups. Cache the ticker index; widen/parameterise depth. | Open |
| TD-006 | No lint / type-check gate (ruff / mypy) is wired into the test run. | Pre-existing | Tests were the priority. | S | Style/type regressions slip through (e.g. unused imports after refactors). | Open |

## Resolved Debt

| ID | Description | Incurred | Resolved | How it was fixed |
|----|-------------|----------|----------|-----------------|
| TD-R01 | Customer-matching engine (`names.py`, `store.py`) was fully built and tested but **never called** by either front-end — no `account_id` in any output. | Wave 2/3 | 2026-05-29 (Gap 1) | Wired `lookup_with_confidence` into `cli.py` and `app.py`; added the Account ID column to the tree, table, and CSV; added `matching/present.py`. |
| TD-R02 | The natural-language parser was duplicated in `cli.py` and `app.py` instead of using `chat/intent.py` (W3.2 was queued, never done). | W3.1 | 2026-05-29 (Gap 2) | Both front-ends now delegate to `chat.intent.parse`; `extract_company_name` kept as a thin shim. (`hf_space/app.py` still pending — TD-001.) |
| TD-R03 | The Gradio UI showed only one level of subsidiaries (`parse_exhibit_21`) while the CLI showed the full recursive tree. | Pre-existing | 2026-05-29 (Gap 3) | `app.lookup` now uses `fetch_subsidiary_tree`; table/CSV gained a Level column; added `tests/test_app.py` (the web UI had no tests). |
| TD-R04 | The source filing's date was never shown, despite being a product non-negotiable. | Pre-existing | 2026-05-29 (Gap 4) | Added `latest_annual_report` (returns form + filing date); CLI and Gradio now show "from {form} filed {date}". |
| TD-R05 | `lookup_with_confidence` did a full table scan (`SELECT *`) and scored every row on every lookup — O(N) per subsidiary. | Wave 2.2 | 2026-05-29 (Gap 5) | Added an in-memory token inverted index built once at `open_store`; `candidate_account_ids` does blocking so only candidates are scored. Results provably identical (a zero-token-overlap row can't match). |

## Debt Categories

| Category | Count | Trend |
|----------|-------|-------|
| Copy-paste duplication | 1 (TD-001) | ↓ (was 3; cli/app de-duped) |
| Performance | 2 (TD-002, TD-005) | → |
| Matching quality | 2 (TD-003, TD-004) | → |
| Tooling | 1 (TD-006) | → |

## Review Cadence

- **Sprint boundary:** Grace reviews the register. New debt discovered during the sprint is added. Pat decides what to pay down next sprint.
- **Every 3 sprints:** Full debt review. Re-estimate costs. Re-assess risks. Anything open for 3+ sprints gets escalated.
