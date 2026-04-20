---
agent-notes: { ctx: "ADR for chat + DB-match expansion: module split, intent parsing, SQLite access, name matching, front-ends, CSV schema", deps: [docs/product-context.md, src/sales_lead_research/cli.py, src/sales_lead_research/edgar.py, src/sales_lead_research/web_fallback.py, app.py, hf_space/app.py], state: accepted, last: "archie@2026-04-20" }
---

# ADR-0003: Sales Assistant Chat Architecture

## Status

Accepted — 2026-04-20

## Context

The product has grown from a standalone CLI that prints a subsidiary tree into a natural-language chat tool that enriches that tree with account IDs from an internal customer database (see `docs/product-context.md`, updated 2026-04-20).

Today, three front-ends (`src/sales_lead_research/cli.py`, `app.py`, `hf_space/app.py`) each import the subsidiary-discovery code directly and each re-implement their own shallow natural-language pattern set and CSV writer. That duplication was tolerable for a single purpose (lookup + CSV). It is not tolerable now that we're adding a second behaviour (database match) and a richer chat surface.

We need one architectural shape that:

- Keeps the proven discovery engine (SEC EDGAR + web/PDF fallback) untouched — same tests, same right-to-left country scan, same CSV semantics.
- Adds a natural-language chat layer that understands phrases like "search for FedEx", "show me FedEx's subsidiaries", "FedEx tree".
- Adds a read-only customer database lookup (SQLite for v1, per the human's commit) that attaches an `account_id` column.
- Respects the project non-negotiables: plain-English user-facing text, open-source-only dependencies, reuse-don't-rebuild, archive-don't-delete.

This ADR covers six decisions as a single architectural shape, because they only make sense together.

## Decision

### 1. Module / library boundary

Split the codebase into three layers inside the existing `src/sales_lead_research/` package — no new top-level package, no monorepo. Each layer has a single responsibility and imports only from layers below it.

```
sales_lead_research/
  discovery/     # library: pure subsidiary discovery (no UI, no DB)
    edgar.py            (moved from package root)
    web_fallback.py     (moved from package root)
    cache.py            (moved from package root)
    __init__.py         (re-exports the public API listed below)
  matching/      # library: customer-DB lookup and name normalisation
    names.py            (normalisation rules, pure functions)
    store.py            (SQLite read-only access)
  chat/          # library: intent parsing and session orchestration
    intent.py           (the single rules-based parser)
    session.py          (ties discovery + matching + rendering together)
  cli.py         # thin front-end: stdin/stdout REPL, calls chat.session
```

**Public API of `sales_lead_research.discovery`** (the only names front-ends and `chat/` may import):

- `build_client(user_agent) -> httpx.Client`
- `search_companies(name, client) -> list[(name, cik)]`
- `fetch_subsidiary_tree(name, client) -> SubsidiaryNode`
- `web_search_subsidiaries(name, client) -> dict | None`
- Exceptions: `EdgarLookupError`, `CompanyNotFound`, `No10KFiled`, `NoExhibit21`
- Data class: `SubsidiaryNode`

Lower-level helpers (`latest_10k_accession`, `exhibit_21_url`, `parse_exhibit_21`, `_extract_structure_from_pdf`) remain module-private to `discovery/` and are not part of the public surface. This protects the right-to-left country scan regression test from callers taking an accidental dependency on its internals.

**Consequences for the three current front-ends:**

- `cli.py` is rewritten as a thin REPL that calls `chat.session.answer(query)` — all its regex patterns and CSV code move into `chat/` and `discovery/`.
- `app.py` (local Gradio) is rewritten to call `chat.session.answer(query)`. Its bespoke regex list is deleted.
- `hf_space/app.py` currently **inlines** the whole discovery pipeline by copy-paste. It continues to run as a self-contained file for Hugging Face Spaces deployment, but we mark it as a distribution artefact that is regenerated from `discovery/` + `chat/` via a small build script (`scripts/bundle_hf_space.py`, future). For v1 we accept it stays hand-maintained and note the drift risk in Consequences.

The moved modules (`edgar.py`, `web_fallback.py`, `cache.py`) are relocated into `discovery/`; the old paths are kept as one-line shims that re-export from the new location **only for the duration of the migration commit**, then archived to `archive/legacy-module-shims/`.

### 2. Chat / intent parsing

**Decision: rules-first regex parser, no LLM in v1.**

Three options were considered:

1. **Rules only (regex + keyword patterns).** Zero new dependencies, millisecond latency, fully offline, deterministic, trivial to unit-test.
2. **Rules first, LLM fallback for unmatched queries.** Handles the long tail, but adds an API dependency, a key, cost, network latency, and a testing burden.
3. **Full LLM parsing.** Most flexible, but every query now costs money and requires network access, violating "boring tech" and the graceful-offline posture.

The user base is an internal sales team typing a small, predictable phrase set ("search for X", "find subsidiaries of Y", "show me Z's tree", "Z"). The existing three copies of `_NL_PATTERNS` already cover this shape and have been good enough in production. We consolidate those three copies into one module (`chat/intent.py`) with a single `parse(query) -> Intent` function returning a small typed result:

```python
@dataclass(frozen=True)
class Intent:
    kind: Literal["lookup", "exit", "empty", "unknown"]
    company_name: str | None
```

If `parse` returns `kind="unknown"`, the chat replies in plain English: *"I didn't understand that — try 'search for [company name]'."* — no silent failures, no hallucinated intent. LLM fallback is **deferred** to a future ADR if real usage shows the pattern set is too narrow.

### 3. Database layer

**Decision: raw `sqlite3` from the standard library, wrapped in a thin read-only query helper (`matching/store.py`). No ORM.**

The schema has eight columns across one table and the tool only reads one of them (`company_name` → `account_id`). An ORM would add a dependency (SQLAlchemy) and a learning surface for zero payoff. `sqlite3` is stdlib, fully open-source, and already supports parameterised queries as the default idiom.

Concrete shape:

- `matching/store.py` exposes two functions:
  - `open_store(path: Path) -> CustomerStore` — opens the SQLite file in **read-only URI mode** (`file:{path}?mode=ro`). This enforces read-only at the connection level, not by convention, so any accidental INSERT/UPDATE/DELETE from future code raises a hard error. Belt and braces: we do not include any write helpers in the module at all (belt = SQL, braces = Python surface).
  - `lookup_by_name(store, normalised_name) -> list[str]` — returns zero, one, or many `account_id` values. Takes already-normalised input; normalisation lives in `matching/names.py` (see decision 4).
- All SQL uses parameterised queries (`?` placeholders) — no string interpolation of user input. Pierrot will re-verify in review.
- Database path comes from env var `SALES_DB_PATH`. Default: `./data/customers.sqlite` under the project root. If the file does not exist when the chat starts, the tool runs in "discovery-only mode" and says so in plain English on every answer: *"Customer database not found — showing subsidiaries without account IDs."* This matches the product-context "fail gracefully" directive.
- A small CLI command (`sales-lead-research init-db`, future work) will create an empty DB and schema from an idempotent `.sql` file — out of scope for this ADR, flagged for the next sprint.

### 4. Name matching

**Decision: normalise in Python (`matching/names.py`) on both sides before comparing; compare case-insensitively after stripping common legal suffixes. Do not push normalisation into SQL.**

Two options were considered:

- **Normalise in SQL.** SQLite lacks regex by default, so normalisation would require either a custom function registered via `connection.create_function` or a complex LIKE expression per suffix. Hard to test, hard to reuse, ties matching logic to the DB.
- **Normalise in Python.** Pure function, unit-testable in isolation, reusable for both the subsidiary name and the DB row. Slightly more data moves over the `sqlite3` cursor — negligible at the table sizes this tool will see (an internal customer list, tens of thousands of rows at most).

Python wins on testability and portability. The normalisation function:

```python
def normalise_name(raw: str) -> str:
    # lowercase, strip whitespace, drop common legal suffixes
    # (inc, inc., incorporated, ltd, ltd., limited, gmbh, lda, lda., sas, s.a., s.a, co, co.,
    #  corp, corp., corporation, llc, llc., plc, ag, n.v., nv, b.v., bv, sarl, s.p.a., spa, s.r.l., srl, pty, oy, oyj)
    # collapse internal whitespace, strip trailing punctuation
```

The full suffix list is defined in `matching/names.py` as a module constant so Tara can table-drive the tests. Tests must cover at minimum: `DHL Express (Portugal) Lda.` / `dhl express portugal`, `FedEx Express (France) SAS`, `Apple Inc.` / `Apple`, and a case where normalisation should **not** produce a match (to guard against over-normalisation).

**Lookup strategy:** `lookup_by_name` compares the normalised input against a normalised copy of `company_name`. Two implementation options:

- **Schema option (preferred for v1):** Add a generated column or an auxiliary table `customer_name_index(normalised_name, account_id)` populated once by the `init-db` step. Indexed lookup is O(log n), deterministic, portable.
- **In-memory scan:** Load all `(company_name, account_id)` rows into a dict at startup. Fine for <100k rows; not fine long-term. Acceptable v1 fallback if building the auxiliary table is out of scope for the first sprint.

I recommend the auxiliary-table approach; Sam will confirm the migration script shape when the schema work is scheduled.

**Match confidence — two tiers.** `lookup_by_name` returns both the `account_id` and a confidence tag:

- **Exact** — the normalised subsidiary name equals the normalised DB `company_name` byte-for-byte. Rendered as `[Account: ACCT-1234]`.
- **Close** — the two normalised names are not equal but clear one simple similarity bar. Rendered as `[Possibly ACCT-1234 — verify]` so the salesperson knows to double-check.

**Close-match rule (v1):** Jaccard similarity of whitespace-split tokens on the normalised strings `>= 0.8`. Rationale: it is a four-line pure function over Python `set`s, requires no new dependency, is trivially unit-testable, and catches the realistic v1 cases ("FedEx Express France" vs. "FedEx Express (France)" after suffix stripping) without the false-positive noise that substring containment produces on short tokens like "inc" or "group". Levenshtein, phonetic matching, and tuned thresholds remain deferred per the product-context.

**Multiple matches.** When one subsidiary name matches multiple DB rows, `lookup_by_name` returns the full list (each tagged with its confidence tier). The rendering layer joins them with `", "` in both the tree cell (`[Account: ACCT-123, ACCT-456]` or `[Possibly ACCT-123, ACCT-456 — verify]` when all are close) and the CSV `account_id` column. When a subsidiary has a mix of exact and close matches, we render the exact IDs first with `[Account: ...]` and append `(also possibly ACCT-789 — verify)` for the close ones. This is the human's proposed behaviour and it preserves information over any "pick one" heuristic we would later regret.

### 5. Output layer / front-ends

**Decision: the chat layer replaces the existing CLI loop. All three front-ends share the same `chat.session.answer(query)` core.**

`chat/session.py` exposes one orchestration function:

```python
def answer(query: str, *, client: httpx.Client, store: CustomerStore | None, writer: CsvWriter) -> AnswerResult
```

`AnswerResult` is a typed value object containing:
- `message: str` (plain-English status for the user — **must** include the filing-date banner described below when a source is known)
- `tree: SubsidiaryNode | None` (the enriched tree — each node carries `account_ids: list[str]` set by the matching step)
- `csv_path: Path | None` (if a CSV was written)
- `filing_date: date | None` (the filing or retrieval date of the source — SEC: date the 10-K was filed; web-fallback: date the PDF was retrieved)
- `source_description: str` (plain-English source label — e.g. `"FedEx Corporation's 10-K"` or `"DHL Group's 2024 annual report"`)
- `errors: list[str]` (plain-English, never raw exceptions)

**Filing-date banner.** Every `message` that carries a result must name the source and its date. Concrete forms:

- SEC path: `"Subsidiaries from FedEx Corporation's 10-K filed 2025-04-15."`
- Web-fallback path: `"Subsidiaries from DHL Group's 2024 annual report (retrieved 2026-03-12)."`
- No source known (pure DB match with no fresh filing): the banner is omitted and the message says so in plain English.

This requires the discovery layer to carry the filing date outward: `fetch_subsidiary_tree` returns the filing date on its result object, `web_search_subsidiaries` returns the retrieval date on its dict, and `chat/session.py` copies these into `AnswerResult` before rendering. Diego will note the new fields in the code-map when implementation lands.

Each front-end is then responsible only for rendering `AnswerResult` into its native medium:

- **CLI** (`sales_lead_research.cli`): renders `tree` with `rich.Tree`, prints `message` and `errors` through `rich.Console`.
- **Local Gradio** (`app.py`): renders `tree` as an indented markdown tree in a chat-style `gr.Chatbot` component and also surfaces the flat list in a `gr.Dataframe`.
- **Hugging Face Gradio** (`hf_space/app.py`): same as local Gradio, but the file stays self-bundled. It calls the same `answer()` shape; the bundle script (future work) ensures the inlined copy stays in sync.

The **old CLI loop** in `cli.py` — the two-gate confirmation flow (company resolution + filing source confirmation) — does not survive into v1 of the chat product. Rationale: the chat persona demands a single turn per user query; a prompt that replies "Proceed with this filing? [Y/n]" is not chat, it is a wizard. Instead, the new CLI:

- Runs the resolution automatically when the query is unambiguous (single SEC match).
- When ambiguous, replies with a numbered list inline and accepts a follow-up turn `1` / `2` / the name itself. This is chat-native.
- The source URL is shown in the answer message, not gated behind a yes/no prompt.

The old interactive two-gate flow is archived (not deleted) to `archive/pre-chat-cli/` per the project's "archive, don't delete" rule. Its unit tests move with it.

### 6. CSV schema

**Decision: flat list with an `account_id` column. Tree structure lives only in the chat rendering.**

The new CSV header is:

```
Subsidiary Name,Jurisdiction,Level,Account ID
```

- `Subsidiary Name`, `Jurisdiction`, `Level` — unchanged from the current CLI CSV (so existing consumers don't break).
- `Account ID` — new column. Empty string when no DB match. Comma-separated list when multiple matches (see decision 4).

Reasons:

- Flat CSVs import cleanly into CRMs, spreadsheets, and pandas without custom parsers.
- `Level` (depth from the parent) preserves enough hierarchy to reconstruct the tree if ever needed downstream — the product owner can defer the "tree-preserving CSV" conversation until a consumer actually asks for it.
- The CSV is a data artefact, not a rendering. The chat window is where the tree shape matters; the spreadsheet is where the flat list matters.

The existing web-fallback CSV (two columns: `Subsidiary Name`, `Jurisdiction`) gains `Level` and `Account ID` to align with the SEC CSV — no more two-shape output. `Level` for web-fallback results stays `1` for now (the PDF path does not yet build a deep tree); this is correct, not a bug.

## Alternatives Considered

- **Separate package for the discovery library.** Attractive for true reuse (another tool could `pip install` it), but premature. No second consumer exists. A sub-package inside `sales_lead_research/` keeps the import surface one move away from extraction if that consumer ever appears.
- **Full LLM chat layer.** Rejected in decision 2. Revisit if the rules-first parser covers fewer than ~90% of real queries after a month of use.
- **PostgreSQL for v1.** Rejected per human commit. SQLite keeps zero-ops, zero-cost, single-file — perfect for an internal tool with one DB file per environment.
- **Keep the two-gate confirmation CLI alongside the chat.** Rejected — two personalities for the same tool is worse than one good one. The archived flow stays recoverable.
- **One ADR per decision.** Rejected at the human's request. The six decisions interlock; splitting them would fragment the reasoning.

## Consequences

### Positive

- Single source of truth for intent parsing — the three copies of `_NL_PATTERNS` collapse to one tested module.
- Discovery engine is untouched behaviourally; its tests (including the right-to-left country-scan regression in `_extract_structure_from_pdf`) continue to pass.
- Read-only DB access is enforced at the connection level, not by convention — a full defence against accidental writes from future code.
- Normalisation is pure Python, easy to unit-test, portable across SQLite and any future PostgreSQL.
- Plain-English failure modes are a first-class concern of `chat/session.py`, not a thing each front-end reinvents.
- Flat CSV with `Account ID` preserves downstream compatibility and adds the new column cleanly.

### Negative

- The `hf_space/app.py` inlined copy drifts from `discovery/` + `chat/` until the bundle script exists. Until then, changes to discovery or chat logic require a manual touch in two places.
- Consolidating the three front-ends onto one `answer()` entry point is a meaningful refactor that will change test surfaces — existing CLI tests will need to be rewritten against the new shape (Tara's work).
- The old two-gate confirmation flow disappears from the primary CLI. Any sales user who liked the "Proceed? [Y/n]" gate will notice. We believe none exist — this is a fresh-enough product.
- The rules-first intent parser will fail on phrasings it hasn't seen. The "unknown" fallback message is the safety net, but expect some user-education cost.
- Multiple DB matches rendered as comma-separated IDs is cheap but not beautiful in a spreadsheet cell. Acceptable v1; revisit when a user complains. Note that comma-separation also hides a data-quality signal — multiple matches often mean the customer list has duplicate rows for the same entity, and a tighter rendering would surface that. We accept the trade for simpler output in v1; **revisit in v2 if duplicate rows become a real problem**.
- The filing-date banner gives the salesperson a freshness signal, but the subsidiary cache can still serve a list older than the most recent filing (cache asymmetry: the cache refreshes on miss, not on new filing). We accept this residual staleness risk in v1 because the banner makes the date explicit — the user can judge whether to trust it or ask for a refresh. Revisit if a sales user reports being misled by a stale but recently-banner-dated list.

### Security & Data Handling

- **Customer data on the online (Hugging Face) front-end — accepted risk.** All three front-ends (terminal, local Gradio, Hugging Face Gradio) may open the customer database when `SALES_DB_PATH` is set. On the Hugging Face-hosted deployment this means the customer list — including tax numbers, postcodes, and the mapping from company name to internal account ID — lives on a third-party hosting provider's filesystem and passes through their runtime. The human accepted this trade-off on 2026-04-20 as a v1 decision (see `docs/product-context.md` § Decisions, item 9). This entry is the audit trail. Mitigations we are **not** doing in v1 and which should be revisited before any external-facing launch: (a) field-level redaction of `tax_number` and `zip_code` from the hosted front-end, (b) a separate smaller customer file for the hosted deployment, (c) hosted-side authentication, (d) a formal data-processing agreement with the host.
- **Read-only DB access** is enforced at the SQLite connection level (`mode=ro` URI), not by code convention — this survives the hosting change and protects against accidental writes from any front-end.
- **No customer data in logs.** `chat/session.py` logs query text and counts but never logs raw DB rows or account IDs. Pierrot to verify in review.

### Neutral

- `SALES_DB_PATH` env var adds one config knob. Documented in the README and the `init-db` command.
- The auxiliary normalised-name index adds a small build step to `init-db`. One-time cost, indexed-lookup payoff.
- The package gains three new sub-modules (`discovery/`, `matching/`, `chat/`). The code-map (`docs/code-map.md`) will need to be filled in to reflect this — Diego's task once implementation lands.

## Explicitly Deferred

The following decisions are out of scope for this ADR and will each get their own smaller ADR or sprint item when the need is concrete:

- **`init-db` command shape and schema migration.** Sam to own. Blocks actual DB use but not the module refactor.
- **Bundling script for `hf_space/app.py`.** Needed only when discovery logic first drifts meaningfully from the inlined copy.
- **LLM fallback for intent parsing.** Revisit after real usage data.
- **Fuzzy matching beyond suffix stripping + Jaccard >= 0.8** (Levenshtein, phonetics, tuned thresholds). The product-context explicitly marks this as out of scope for v1.
- **Multi-user / write-back / auth.** Out of v1 scope by product decision. Concretely, v1 assumes: `SALES_DB_PATH` points to a local file on a single salesperson's machine; no shared-drive or shared-mount story; no authentication layer; no concurrent-writer coordination (the tool is read-only anyway, but this also means no read-while-someone-else-edits story is promised). Multi-user, shared storage, and auth are v2 concerns.
- **Hosted-deployment data minimisation** — Pierrot to own, Pat for product input. Small follow-up ADR after the v1 shell is running. Covers redacting `tax_number`/`zip_code` from the customer file shipped to the Hugging Face host, or serving a separate minimised file, or adding hosted-side auth. See Security & Data Handling above.

## Revision history

- 2026-04-20 — revised after Wei's challenge and human decisions; match confidence tiered, filing-date banner added, customer-list-on-online-version accepted as v1 risk.
- 2026-04-20 (second pass) — human confirmed Jaccard threshold stays at 0.8 (tune on data), mixed tier rendering stays as `[Account: ACCT-123] (also possibly ACCT-789 — verify)`, and hosted-deployment data minimisation is scheduled as a follow-up ADR owned by Pierrot with Pat's product input.
