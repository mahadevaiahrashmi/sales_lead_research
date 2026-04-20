<!-- agent-notes: { ctx: "v1 plan for sales-assistant chat + DB matching", deps: [docs/product-context.md, docs/adrs/0003-sales-assistant-chat-architecture.md, data/customers.sqlite], state: active, last: "pat@2026-04-20" } -->

# Plan — Sales Assistant Chat v1

**Date:** 2026-04-20
**Lead:** Pat (backlog) + Archie (architecture follow-through)

## Goal

Turn the current one-shot subsidiary-lookup tool into a chat window that also tells the salesperson which subsidiaries already exist as customers in the local database, so they can focus their prospecting on the genuinely new entities.

The behaviour the user types is captured in `docs/product-context.md`. The architectural shape is captured in `docs/adrs/0003-sales-assistant-chat-architecture.md`. This plan turns those two documents into a sequence of work items that can be executed session-by-session.

## Constraints

- **Architecture is set.** ADR-0003 is Accepted. Do not re-open the six decisions (module split, rules-based intent parsing, stdlib SQLite read-only, tiered name matching, chat-over-REPL, flat CSV with Account ID). If a concrete problem forces a revision, raise a new ADR.
- **Confirmed product decisions.** See the nine decisions in `docs/product-context.md` under "Decisions (confirmed by the human on 2026-04-20)". All work below respects them — in particular: chat (not a search box), filing-date banner on every answer, close-match tier with a "verify" marker, comma-separated multi-match, single-user v1, online version may read the customer list (risk accepted in writing).
- **Keep the discovery engine behaviourally unchanged.** The 163 existing tests must stay green through every work item. Do not simplify the right-to-left country scan in `_extract_structure_from_pdf`.
- **Plain English to the user always.** Codified in `CLAUDE.md` and cross-session memory.
- **TDD for M and L items.** Tara writes the failing test first; Sato makes it pass.
- **Archive, don't delete.** Any code removed from the active tree moves to `archive/` with its tests.

## Architecture Gate Items

**None.** The Architecture Decision Scan was run against every work item below. Each one implements a decision already captured in ADR-0003. No new patterns, no new integrations, no new technology choices, no new package boundaries — the subpackage shape was set by the ADR, not invented here.

Deferred items (already noted in the ADR's "Explicitly Deferred" section, not in v1 scope):

- `init-db` full schema migration story (Sam owns; out of v1)
- Bundling script for `hf_space/app.py` (out of v1)
- Rules-based → LLM fallback for intent parsing (out of v1)
- Tax-number redaction on the online version (Pierrot + Pat follow-up, scheduled after v1 ships)
- Multi-user / shared storage / authentication (v2 concern)

## Approach — Five Waves

Each wave is sized to fit roughly one working session. Waves are ordered by dependency. Within a wave, items are ordered so Tara's tests always land before Sato's implementation for M+ items.

### Wave 1 — Foundation refactor (S, S, XS)

Carve the existing discovery code out of the package root and into a `discovery/` subpackage, as specified in ADR-0003 §1. No new features, no behaviour change.

- **W1.1 (S) — Move discovery files.** Move `src/sales_lead_research/edgar.py`, `web_fallback.py`, `cache.py` into a new `src/sales_lead_research/discovery/` subpackage. Add shim re-exports at the old paths so every import keeps working. Full test suite must stay green. _Owner:_ Sato. _TDD:_ skip (no behaviour change); rely on existing 163 tests.
- **W1.2 (S) — Define the public API.** Populate `discovery/__init__.py` with the six public names listed in ADR-0003 §1. Update internal callers so they import from the subpackage, not the shim. _Owner:_ Sato.
- **W1.3 (XS) — Retire the shims.** Remove the shim files once nothing imports them. Archive to `archive/legacy-module-shims/` per the rule. _Owner:_ Sato.

### Wave 2 — Matching layer (M, M, S)

New subpackage `matching/` containing the name-normalisation rules and the read-only SQLite store. This is the first time we touch the customer database.

- **W2.1 (M) — `matching/names.py`.** Pure functions: `normalise_name(raw)` (lowercase, strip legal suffixes, collapse whitespace) and `jaccard_similarity(a, b)` (token-level Jaccard on normalised strings). Plus a `classify_match(subsidiary, customer)` helper that returns one of `"exact"`, `"close"`, `"none"` using the ≥ 0.8 threshold. _Tara writes:_ table-driven tests covering the canon cases — "DHL Express (Portugal) Lda." vs "dhl express portugal", "FedEx Corporate Services, Inc." vs "FedEx Corporate Service Inc." (close), "Apple Inc." vs "Apple" (exact), "Acme Corp" vs "Acme Holdings" (none). _Owner:_ Tara → Sato.
- **W2.2 (M) — `matching/store.py`.** Thin wrapper around stdlib `sqlite3`. `open_store(path)` uses URI mode `file:{path}?mode=ro`. `lookup_by_name(store, normalised_name)` returns `list[str]` of account IDs. `lookup_with_confidence(store, subsidiary_name)` returns tiered matches (exact IDs + close IDs). Path defaults from env var `SALES_DB_PATH`. Missing file → store is `None` and the caller says so in plain English. _Tara writes:_ store opens against `data/customers.sqlite`, read-only enforcement test (INSERT raises `OperationalError`), exact and close match tests against the seed data, graceful behaviour when the file is absent. _Owner:_ Tara → Sato.
- **W2.3 (S) — `sales-lead-research init-db` subcommand.** Creates an empty schema file if one doesn't exist. Loads a seed CSV when `--seed` is passed. Uses the shape of `scripts/init_dummy_db.py` as the reference. _Owner:_ Sato (with Sam confirming the schema matches product-context). _TDD:_ smoke test that the subcommand creates a readable file with the right shape.

### Wave 3 — Chat layer (M, L)

One source of truth for "what did the user mean" and "what do I do with it." Replaces the three duplicated `_NL_PATTERNS` blocks and the scattered orchestration in the current front-ends.

- **W3.1 (M) — `chat/intent.py`.** Single `parse(query) -> Intent` function. Returns the typed `Intent` dataclass from ADR-0003 §2. Unknown phrasings yield `kind="unknown"` with a plain-English reply, not a silent guess. _Tara writes:_ every supported phrasing shape, several unsupported shapes, the empty-string and whitespace-only cases, the `exit` case. _Owner:_ Tara → Sato.
- **W3.2 (L) — `chat/session.py`.** The `answer(query, *, client, store, writer) -> AnswerResult` orchestrator. Pipeline: `parse` → if lookup, call `discovery` → for each subsidiary, call `matching.lookup_with_confidence` → build an enriched tree → write CSV → return `AnswerResult` with filing-date banner in `message`. Plain-English errors on every failure path. _Tara writes:_ golden-path happy-case (FedEx → enriched tree with at least one exact and one close match from the dummy DB), "unknown intent" path, "DB missing" path (no store → tree has empty account_id cells + banner), "SEC not found → web fallback kicks in" path, "filing date absent → generic wording" path. _Owner:_ Tara → Sato.

### Wave 4 — CSV schema + front-end rewrites (S, M, M, M)

All three front-ends collapse onto `chat.session.answer()`. Old orchestration code moves to `archive/`.

- **W4.1 (S) — Align the CSV writer.** Flat schema: `Subsidiary Name, Jurisdiction, Level, Account ID`. Both SEC and web-fallback paths emit the same four columns. Web-fallback rows get `Level = 1`. _Tara writes:_ writer emits the four columns for both paths; `Account ID` is empty when no match, a single ID when exact, comma-separated when multi-match, `"possibly X — verify"` shape in the chat but plain ID in the CSV (Pat ruling: CSV stays machine-readable; chat carries the uncertainty copy). _Owner:_ Tara → Sato.
- **W4.2 (M) — Rewrite `cli.py`.** Thin REPL. Reads stdin, calls `chat.session.answer()`, renders with `rich.Console`/`rich.Tree`. No more two-gate confirmation prompts. Ambiguous company → numbered inline list, user replies with a number or the name. Archive the current `cli.py` two-gate flow and its tests to `archive/pre-chat-cli/`. _Tara writes:_ REPL golden path, numbered-disambiguation path, unknown-intent reply, `exit` cleanly ends the loop. _Owner:_ Tara → Sato.
- **W4.3 (M) — Rewrite `app.py` (local Gradio).** Calls `chat.session.answer()`. Renders the tree in a chat-style component; renders the flat list in a dataframe component. Exposes a button to download the CSV. _Tara writes:_ unit tests for the adapter layer only (Gradio UI itself is manual-verified). _Dani reviews:_ accessibility + visual rendering of the close-match "verify" marker. _Owner:_ Tara → Sato (Dani for visual review).
- **W4.4 (M) — Rewrite `hf_space/app.py`.** Self-contained copy that calls the same `answer()` shape. Customer database access is allowed per the human's decision; note that the online deploy will read `data/customers.sqlite` when `SALES_DB_PATH` is set in the Space's environment. _Tara writes:_ parity tests against a small fixture showing the Space adapter produces the same `AnswerResult` as `app.py`. _Owner:_ Tara → Sato.

### Wave 5 — Polish, docs, and end-to-end verification (XS, S, XS, S)

- **W5.1 (XS) — Update `docs/code-map.md`.** Fill in the three sub-packages (`discovery/`, `matching/`, `chat/`) and the front-end fan-out. _Owner:_ Diego.
- **W5.2 (S) — Update `README.md`.** New quick-start shows typing a natural-language query and seeing an enriched tree. _Owner:_ Diego.
- **W5.3 (XS) — Append a real example chat transcript** to `docs/product-context.md`, replacing the synthetic one at the bottom with one captured against the dummy database. _Owner:_ Diego.
- **W5.4 (S) — End-to-end demo run.** With `SALES_DB_PATH=data/customers.sqlite`, run: `FedEx`, `find subsidiaries of DHL`, `acme corp` (no match), and a deliberately unclear query. Verify filing-date banner, exact and close-match tiers, CSV export, graceful missing-match rendering. Capture the output as a markdown snippet. _Owner:_ Sato.

## Personas Involved

| Phase | Lead | Others |
|-------|------|--------|
| Implementation | Sato | Tara (tests first for all M+ items) |
| Data / schema check in W2.3 | Sam (Archie's schema persona) | — |
| Accessibility review in W4.3 | Dani | — |
| Docs in W5.1–W5.3 | Diego | — |
| Code review at end of each wave | Vik + Tara + Pierrot | Three parallel lenses |
| Sprint boundary after Wave 5 | Grace | Triggers retro and done-gate |

## Open Questions

1. **Seed data on first run.** Should `sales-lead-research init-db` auto-populate from `data/customers.sqlite` (the generated dummy data) if a salesperson runs the tool for the first time with no file, or should it create an empty schema and leave the seeding to a separate command? _Proposed:_ empty schema on `init-db`; seeding only when `--seed <path>` is passed.
2. **CSV filename for chat context.** Currently the filename is `<company>_subsidiaries.csv`. With enrichment, should it become `<company>_subsidiaries_enriched.csv` (per the product-context sample transcript) or stay the existing name? _Proposed:_ keep existing name (`_subsidiaries.csv`) — the Account ID column is obvious on open, and changing the filename breaks anyone already automating on the current name.
3. **Front-end visual treatment for close matches.** Markdown `[Possibly ACCT-1234 — verify]` inline is readable but visually the same colour as exact matches in a plain console. Do we want Rich to render the "verify" tier in a different colour (yellow / warning style)? _Proposed:_ yes in the terminal (`rich` yellow); neutral text in Gradio markdown; Dani confirms during W4.3.

## Acceptance Criteria

v1 is done when, with `SALES_DB_PATH=data/customers.sqlite` exported:

- Typing `FedEx` into the terminal produces a subsidiary tree where at least three subsidiaries carry `[Account: ACCT-0xxx]` exact markers and at least one carries a `[Possibly ACCT-0xxx — verify]` close marker.
- Typing `DHL` triggers the web-fallback path, surfaces filings, and enriches the subsidiaries whose names match rows like "DHL Express (Portugal) Lda." — including the comma-separated multi-match for the two "FedEx Custom Critical" rows when their subsidiary counterpart is in the tree.
- The answer always carries the filing-date banner — e.g. *"Subsidiaries from FedEx Corporation's 10-K filed 2025-04-15."*
- Every successful run writes `<company>_subsidiaries.csv` with the four-column schema, including the populated `Account ID` column.
- A malformed query ("blargh") returns `I didn't understand that — try 'search for [company name]'.`, not a traceback.
- With `SALES_DB_PATH` unset (or pointing at a missing file), the same queries still run and return a subsidiary tree; every answer prefixes with "Customer database not found — showing subsidiaries without account IDs."
- All 163 existing discovery tests still pass. The new `matching/`, `chat/`, and front-end tests also pass.
- `docs/code-map.md` reflects the three sub-packages.
- The Done Gate (`docs/process/done-gate.md`) is satisfied for every work item before it closes.
