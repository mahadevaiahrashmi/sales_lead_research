<!-- agent-notes: { ctx: "session handoff after v1 product spec + ADR + plan + devcontainer landed", deps: [docs/product-context.md, docs/adrs/0003-sales-assistant-chat-architecture.md, docs/plans/sales-assistant-chat-v1-plan.md, docs/decisions-log.md, .devcontainer/devcontainer.json, data/customers.sqlite], state: active, last: "coordinator@2026-04-20" } -->

# Session Handoff

**Created:** 2026-04-20
**Sprint:** New product expansion — "Sales Assistant Chat (with DB Matching)" v1.
**Wave:** Pre-Wave (spec + architecture + plan landed this session). Wave 1 of 5 starts next session.
**Session summary:** Expanded the product from a standalone subsidiary-lookup tool into a chat tool that enriches the subsidiary tree with account IDs from a read-only customer database. Produced product context, ADR-0003 (Accepted), a 5-wave / 13-item implementation plan, a dummy SQLite customer database, and a devcontainer. Committed in three logical commits; not yet pushed.

## What Was Done

### Board tidy-up
- Pushed prior 5 local commits (origin was behind coming in).
- Moved issues #4, #5, #9, #10 on project board #5 to Done. All 11 board items are now Done. Underlying GitHub issues were already closed.

### Product expansion
- Drafted `docs/product-context.md` from the existing codebase; then replaced it with the human's expanded vision (chat + DB matching). Added a Mermaid flowchart for the lookup pipeline.
- Codified 9 confirmed product decisions in the same file — matching rule, multi-match rendering, filing-date banner on every answer, SQLite commitment, chat window (not a search box), single-user v1 scope, online-version DB access risk accepted in writing.

### Architecture Gate — completed
- **Archie** drafted `docs/adrs/0003-sales-assistant-chat-architecture.md` covering six decisions: module split (`discovery/` + `matching/` + `chat/`), rules-based intent parser (no LLM), stdlib `sqlite3` in read-only URI mode, tiered name matching (Jaccard ≥ 0.8), unified `chat.session.answer()` across all three front-ends, flat CSV schema with `Account ID` column.
- **Wei** challenged independently — 8 objections, 1 veto-level (customer data reaching the Hugging Face host).
- Translated Wei's objections to plain English for the human; human answered six questions.
- Archie revised the ADR — status now **Accepted — 2026-04-20**. Added Security & Data Handling subsection as the audit trail for the accepted risk.
- I made three further judgement calls (Jaccard 0.8 stays, mixed-tier rendering format, tax-number redaction deferred to a Pierrot + Pat follow-up ADR). Recorded in the ADR's revision history.

### Dummy customer database
- `scripts/init_dummy_db.py` → generates `data/customers.sqlite` with 47 rows across FedEx, DHL, Apple, Microsoft, 3M families plus unrelated noise.
- Exercises every matching path: exact, close (e.g. "FedEx Corporate Service" vs real "...Services, Inc."), multi-match duplicates (two "FedEx Custom Critical" rows sharing a tax number), parenthesised-country names (DHL Portugal, Netherlands).
- `data/customers.sqlite` is gitignored; the generator is the source of truth.

### Implementation plan
- `docs/plans/sales-assistant-chat-v1-plan.md` — 5 waves, 13 work items, TDD-ordered, with acceptance criteria.
- Architecture Decision Scan confirmed: **no new gated items** — every work item builds on ADR-0003.
- `docs/tracking/2026-04-20-sales-assistant-chat-plan.md` — phase tracking artifact.

### Decisions log (plain English)
- `docs/decisions-log.md` — layman-English record of every decision made this session, with who decided each.

### Dev environment
- `.devcontainer/devcontainer.json` — Python 3.12 Bookworm base, GitHub CLI feature, `uv` installed via official script in `postCreateCommand`, port 7860 auto-forwarded for Gradio, standard Python VS Code extensions.
- `CLAUDE.md` — added `.devcontainer/` to the project-structure tree.
- `README.md` — new "Development Environment" section.

## Current State

- **Branch:** `main` — **3 commits ahead of origin, needs a push.**
- **Last commit:** `d5c4dd2 chore: add devcontainer for Python 3.12 + uv`
- **Uncommitted changes:** none — working tree clean.
- **Tests:** 163 passing across 10 test files (unchanged; no code touched this session).
- **Board status:** all 11 items Done. **No issues exist yet for the 13 new work items in the Wave 1-5 plan.** They need to be created before Wave 1 starts (Session Entry Protocol Q1).

## Sprint Progress

- **Wave plan:** `docs/plans/sales-assistant-chat-v1-plan.md` (not `docs/sprints/` — that directory doesn't exist; this project runs on ad-hoc queues per the earlier handoff).
- **Current wave:** Pre-Wave — spec/architecture/plan complete.
- **Issues completed this session:** none (this session produced no code changes, only documents and scaffolding).
- **Issues remaining in wave:** n/a.
- **Next wave:** **Wave 1 — Foundation refactor** (3 items, all S/XS):
  - **W1.1 (S):** Move `edgar.py`, `web_fallback.py`, `cache.py` into `src/sales_lead_research/discovery/` with shim re-exports. All 163 existing tests must stay green.
  - **W1.2 (S):** Define `discovery/__init__.py` public API (six names listed in ADR-0003 §1). Update internal callers.
  - **W1.3 (XS):** Remove shims, archive to `archive/legacy-module-shims/`.

## What To Do Next (in order)

1. Read `docs/code-map.md` to orient (it is still a stub — worth filling in during Wave 5 anyway).
2. Read `docs/product-context.md` for the 9 confirmed decisions and the expanded vision.
3. Read `docs/adrs/0003-sales-assistant-chat-architecture.md` — source of truth for the code shape. Do NOT re-litigate the six decisions.
4. Read `docs/plans/sales-assistant-chat-v1-plan.md` for the full wave breakdown and acceptance criteria.
5. **Push `main`** — `git push` (three commits: `2b85cc3`, `8d98e42`, `d5c4dd2`).
6. **Create GitHub issues for the 13 Wave 1-5 work items.** Use the IDs (W1.1 … W5.4), titles, sizes, and owner personas from the plan doc. Add them to project board #5 in "Ready" status. Session Entry Protocol Q1 requires this before implementation.
7. **Start Wave 1.1** — move the three discovery modules into `src/sales_lead_research/discovery/` with shim re-exports. No behaviour change. Run `uv run pytest` after the move — all 163 tests must still pass. Session Entry Protocol Q3 says "no tests needed first" because this is a pure move with existing regression coverage.
8. Commit W1.1 on its own. Move its issue In Progress → In Review → Done on the board. Repeat for W1.2 then W1.3.
9. End the session with `/handoff` — Wave 1 should fit in one session; Wave 2 is a fresh session.

## Tracking Artifacts

- `docs/tracking/2026-04-20-sales-assistant-chat-plan.md` — current phase artifact (plan phase, Active). Prior phase: architecture (ADR-0003). Next phase: implementation (start of Wave 1).
- `docs/product-context.md` — last updated 2026-04-20 with the nine confirmed decisions.

## Proxy Decisions (Review Required)

None. The human was active throughout the session.

Three small calls I made on the human's behalf when they said "you decide", all logged in the ADR revision history and the decisions log:

- Close-match threshold stays at **0.8** (tune later when real data is available).
- Mixed-tier rendering: `[Account: ACCT-123] (also possibly ACCT-789 — verify)`.
- Tax-number redaction on the online version → small follow-up ADR owned by Pierrot with Pat's product input, scheduled after v1 ships.

All reversible; re-open if needed.

## Key Context

- **The architecture is fixed.** ADR-0003 is Accepted. Do not re-open the six decisions (module split, rules-based parser, SQLite read-only, tiered matching, unified `answer()`, flat CSV). If a concrete problem forces a change, raise a new ADR — don't silently deviate.
- **Do not break the right-to-left country scan** in `_extract_structure_from_pdf` when reshuffling into `discovery/`. Its regression test is `tests/test_web_fallback.py::test_keeps_country_in_parens`. It must stay green through Wave 1.
- **`hf_space/app.py` is special.** It's a self-contained copy (inlined, not an import of the package). Wave 1.1 must not break it. A bundling script to keep it in sync is explicitly deferred per the ADR — accept the drift for v1.
- **Customer data reaches the online host** — this is the human's accepted v1 risk, recorded in ADR-0003 §Security & Data Handling and in `docs/decisions-log.md`. A follow-up ADR on data minimisation is on the deferred list.
- **`SALES_DB_PATH` env var** is the runtime contract for database location. Default in the ADR: `./data/customers.sqlite`. When the file is missing, the tool runs in "discovery-only mode" with a plain-English banner.
- **Plain-English rule applies to every user-facing reply.** Codified in `CLAUDE.md` and `memory/feedback_plain_english.md`. Tests should assert that error messages don't leak raw exception class names.
- **User preferences in cross-session memory:**
  - Plain English always.
  - Archive, don't delete.
  - `gh project` owner quirk — use explicit `--owner mahadevaiahrashmi`.
  - `updateProjectV2Field` GraphQL no longer accepts `projectId`.
- **Three commits pending push:**
  - `2b85cc3 docs: product context, ADR-0003, plan, and decisions log for chat + DB matching`
  - `8d98e42 chore: add dummy customer database generator`
  - `d5c4dd2 chore: add devcontainer for Python 3.12 + uv`
