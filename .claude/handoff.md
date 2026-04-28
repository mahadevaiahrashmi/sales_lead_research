<!-- agent-notes: { ctx: "session handoff after Wave 1 finished — discovery refactor fully landed, Wave 2 (matching layer) queued", deps: [docs/plans/sales-assistant-chat-v1-plan.md, docs/adrs/0003-sales-assistant-chat-architecture.md, docs/product-context.md, src/sales_lead_research/discovery/__init__.py], state: active, last: "coordinator@2026-04-28" } -->

# Session Handoff

**Created:** 2026-04-28
**Sprint:** Sales Assistant Chat (with DB Matching) v1
**Wave:** **Wave 1 of 5 — DONE.** Wave 2 of 5 is queued and ready to start.
**Session summary:** Executed Wave 1 (Foundation refactor) end to end — three issues, three commits each through In Progress → In Review → Done with code-reviewer sign-off, plus minor nice-to-have follow-ups. The discovery code now lives in its own subpackage with an explicit public API and the legacy shims are retired and archived. All 163 existing tests stay green throughout.

## What Was Done

### Wave 1.1 — already in place at session start
- W1.1 (#12) had been completed and pushed in the previous session (commit `5688e57`). The three discovery modules (`edgar.py`, `web_fallback.py`, `cache.py`) had been moved into `src/sales_lead_research/discovery/` with one-line shims left at the old paths.

### Wave 1.2 — discovery public API + caller redirection (#13)
- Populated `src/sales_lead_research/discovery/__init__.py` with the nine public names from ADR-0003 §1: `build_client`, `search_companies`, `fetch_subsidiary_tree`, `web_search_subsidiaries`, `SubsidiaryNode`, `EdgarLookupError`, `CompanyNotFound`, `No10KFiled`, `NoExhibit21`. Added explicit `__all__` and a docstring noting that `cache` is intentionally module-private.
- Redirected every internal caller off the shim paths and onto the new subpackage. Established a consistent split: **public names** come from `sales_lead_research.discovery`; **private helpers** (`exhibit_21_url`, `latest_10k_accession`, `parse_exhibit_21`, `find_parent_company`, `find_exhibit_21`, `resolve_cik`, `AmbiguousCompanyName`, `_extract_*`, `cached_get`) come from the specific submodule (`sales_lead_research.discovery.{edgar,web_fallback,cache}`).
- Files touched: `app.py`, `src/sales_lead_research/__main__.py`, `src/sales_lead_research/cli.py`, plus nine test files.
- Code-reviewer (Vik + Tara + Pierrot) approved with three nice-to-haves; the only one that warranted action was Vik's docstring clarification on `cache`'s deliberate omission, which was added in a follow-up commit.
- Commits: `9f0f236` (W1.2 main change), `9fbde5f` (cache docstring nice-to-have).

### Wave 1.3 — retire the shims (#14)
- Confirmed via grep that no live caller in `src/`, `tests/`, `scripts/`, or `app.py` referenced the shim paths after W1.2.
- Archived the three shim files to `archive/legacy-module-shims/` via `git mv` (preserving git history). Added a README in that directory pointing future readers at the current public API and the relevant commits (`5688e57` + `94b3cd2`).
- Confirmed `import sales_lead_research.edgar` now raises `ModuleNotFoundError` — the intended outcome.
- Code-reviewer approved clean (one nice-to-have: pin the W1.3 commit SHA in the README, which was applied as a follow-up).
- Commits: `94b3cd2` (W1.3 main change), `c467ec4` (README SHA pin nice-to-have).

### One declined direction
- The user asked partway through the session about adopting the look of `mckaywrigley/chatbot-ui`. Cam-style probing surfaced that this would re-open ADR-0003 (the Gradio-based front-end decision) and invalidate several Wave 4 work items. The user replied "do no change and continue", so the architecture stands as written and Wave 4 plans are unchanged. Worth knowing if the same idea resurfaces.

## Current State

- **Branch:** `main` — in sync with `origin/main`.
- **Last commit:** `c467ec4 docs(archive): pin W1.3 commit SHA in shim retirement README`.
- **Uncommitted changes:** none — working tree clean.
- **Tests:** 163 passing across 10 test files (unchanged behaviour, just import-path moves).
- **Board status:** **All 11 prior items + #12, #13, #14 in Done (14 total).** All 13 remaining issues (#15–#27, covering Waves 2–5) are still in **Ready**. Session Entry Protocol Q1 satisfied for the next wave.
- **Issue ↔ work-item map (Waves 2–5, all Ready):** #15 W2.1 · #16 W2.2 · #17 W2.3 · #18 W3.1 · #19 W3.2 · #20 W4.1 · #21 W4.2 · #22 W4.3 · #23 W4.4 · #24 W5.1 · #25 W5.2 · #26 W5.3 · #27 W5.4.

## Sprint Progress

- **Wave plan:** `docs/plans/sales-assistant-chat-v1-plan.md` (note: this project has no `docs/sprints/` — plans live in `docs/plans/`).
- **Wave 1 — DONE.** Issues #12, #13, #14 all Closed and on the Done column.
- **Issues completed this session:** #13 (W1.2), #14 (W1.3). #12 (W1.1) was already Done at session start.
- **Issues remaining in this wave:** none — Wave 1 is finished.
- **Next wave: Wave 2 — Matching layer (3 items, all in Ready):**
  - **#15 W2.1 (M):** `src/sales_lead_research/matching/names.py` — `normalise_name`, `jaccard_similarity`, `classify_match` (≥ 0.8 threshold). Tara writes table-driven tests first (DHL parens-country, FedEx close-match, Apple exact, Acme no-match).
  - **#16 W2.2 (M):** `src/sales_lead_research/matching/store.py` — read-only SQLite wrapper. `open_store(path)` uses URI mode `file:{path}?mode=ro`. `lookup_by_name`, `lookup_with_confidence`. Path default from env `SALES_DB_PATH`. Missing file → `None` and plain-English banner. Tara writes tests for read-only enforcement (INSERT raises `OperationalError`), exact/close match, missing-file behaviour.
  - **#17 W2.3 (S):** `sales-lead-research init-db` subcommand. Empty schema file when none exists; loads seed CSV only with `--seed <path>`.

## What To Do Next (in order)

1. Read `docs/code-map.md` to orient (still a stub — Wave 5.1 fills it in).
2. Read `docs/product-context.md` for the nine confirmed product decisions and the matching-tier rules (last updated 2026-04-20).
3. Read `docs/adrs/0003-sales-assistant-chat-architecture.md` §3 (database layer) and §4 (name matching) — source of truth for Wave 2.
4. Read `docs/plans/sales-assistant-chat-v1-plan.md` Wave 2 section for full acceptance criteria.
5. **Start Wave 2.1 (issue #15).** Move #15 to **In Progress** on the board (item ID `PVTI_lAHOATydZs4BUtC2zgqcn7s`, status field `PVTSSF_lAHOATydZs4BUtC2zhCIs6w`, In-Progress option `33e5be0d`, project node `PVT_kwHOATydZs4BUtC2`). This is the first M-sized item — TDD applies. **Tara writes the failing tests first** (table-driven, covering the canonical four cases listed in the plan) before Sato implements `matching/names.py`.
6. Continue through W2.2 (#16) — TDD again — then W2.3 (#17) which is S-sized and only needs a smoke test.
7. End the session with `/handoff`. Wave 2 likely fits one session if you keep tests parallel to implementation; if it stretches, hand off mid-wave is fine.

## Tracking Artifacts

- `docs/tracking/2026-04-20-sales-assistant-chat-plan.md` — plan-phase artifact, still active. Next phase artifact when Wave 2 starts: implementation tracker for the matching layer.
- `docs/product-context.md` — last updated 2026-04-20 with nine confirmed product decisions.
- `docs/adrs/0003-sales-assistant-chat-architecture.md` — Accepted 2026-04-20.

## Proxy Decisions (Review Required)

None this session. The human was active throughout (vision check on the chatbot-ui suggestion, "go"/"start"/"wrap" pacing).

## Key Context

- **Architecture is fixed.** ADR-0003 is Accepted. Do not re-open the six decisions even if the chat-shell idea resurfaces — raise a new ADR if a real constraint forces it.
- **Wave 2 is the first DB-touching wave.** Pierrot will want to see parameterised queries (no string interpolation) and confirmed read-only URI mode in W2.2.
- **`SALES_DB_PATH` env var** is the runtime contract for database location. Default: `./data/customers.sqlite`. Missing file → discovery-only mode with the plain-English banner *"Customer database not found — showing subsidiaries without account IDs."*
- **The discovery import convention is now load-bearing for Waves 2 + 3.** `chat/` and `matching/` should import discovery via `sales_lead_research.discovery` (public API only). Don't drill into `discovery.edgar` etc. from outside the discovery layer — that path is for the discovery layer's own tests.
- **The right-to-left country scan in `_extract_structure_from_pdf` must stay green.** Regression test: `tests/test_web_fallback.py::test_pdf_parser_keeps_country_in_parens`.
- **`hf_space/app.py` is special** — self-contained inlined copy. Wave 4.4 covers its rewrite. Until then, drift is accepted per ADR-0003.
- **Plain-English rule applies to every user-facing reply.** Codified in `CLAUDE.md` and cross-session memory.
- **User preferences in cross-session memory:**
  - Plain English always, to a non-technical reader.
  - Archive, don't delete (followed for the shims this session).
  - `gh project` owner quirk — use explicit `--owner mahadevaiahrashmi`.
  - `updateProjectV2Field` GraphQL no longer accepts `projectId`.
- **Cached board IDs in `CLAUDE.md`:** project-node `PVT_kwHOATydZs4BUtC2`, status-field `PVTSSF_lAHOATydZs4BUtC2zhCIs6w`, options: backlog `b47b9404`, ready `fc2fa384`, in-progress `33e5be0d`, in-review `d79cdd57`, done `e7258da6`. Save the next session a lookup.
- **All commits pushed** (as of 2026-04-28). `main` is in sync with `origin/main`.
