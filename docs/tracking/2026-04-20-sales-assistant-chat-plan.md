---
agent-notes: { ctx: "plan-phase tracking for sales-assistant chat + DB matching v1", deps: [docs/plans/sales-assistant-chat-v1-plan.md, docs/adrs/0003-sales-assistant-chat-architecture.md, docs/product-context.md], state: active, last: "pat@2026-04-20" }
---

# Plan: Sales Assistant Chat v1

**Date:** 2026-04-20
**Lead:** Pat + Archie
**Status:** Active
**Prior Phase:** `docs/adrs/0003-sales-assistant-chat-architecture.md` (architecture, accepted 2026-04-20)

## Key Decisions

- **Five waves, thirteen work items.** Chose a wave-based sequence over a flat backlog so each session boundary lines up with a natural pause point (foundation → matching → chat → front-ends → polish).
- **No new architecture gates in v1.** Every item in the plan implements a decision already captured in ADR-0003. Item-level scan produced an empty "Architecture Gate Items" section.
- **TDD scope.** Tara writes tests first for all M and L items (W2.1, W2.2, W3.1, W3.2, W4.1, W4.2, W4.3, W4.4). S and XS items skip the ceremony unless they introduce new behaviour. W1.1–W1.3 are pure moves — existing 163 tests are the regression net.
- **Front-end strategy.** The three current front-ends (`cli.py`, `app.py`, `hf_space/app.py`) all collapse onto `chat.session.answer()`. The old two-gate confirmation CLI loop archives to `archive/pre-chat-cli/` rather than being deleted, per the project rule.
- **Seed data on first run.** `init-db` will create an empty schema only; seeding requires an explicit `--seed <path>`. Avoids surprising a first-time user with demo data they didn't ask for. (Open question #1 in the plan — defaulting to this unless overturned.)
- **CSV filename unchanged.** Keeps `<company>_subsidiaries.csv` rather than the sample-transcript's `_subsidiaries_enriched.csv`, so anyone automating on the current filename isn't broken by the upgrade.
- **Close-match visual treatment** will use Rich yellow in the terminal, neutral markdown in Gradio, final call by Dani during Wave 4.3.

## Artifacts Produced

- `docs/plans/sales-assistant-chat-v1-plan.md` — the full plan.
- `docs/tracking/2026-04-20-sales-assistant-chat-plan.md` — this artifact.

## Open Questions

- Seed-on-first-run default (plan §Open Questions #1) — proposed empty.
- Close-match visual styling in the terminal (plan §Open Questions #3) — proposed yellow Rich, confirmed by Dani in W4.3.
- CSV filename (plan §Open Questions #2) — proposed unchanged.
- Devcontainer is not yet set up; decision pending (see next phase).

## Next Phase

- Implementation. First session picks up Wave 1 (foundation refactor) under `/tdd`-style flow. Wave-by-wave, a `/handoff` at the end of each session so the next one starts cold with clean context.
- Before Wave 1 starts: confirm devcontainer decision with the human.
