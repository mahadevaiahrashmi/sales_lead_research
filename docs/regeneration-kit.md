---
agent-notes: { ctx: "how to rebuild an equivalent system from this repo's artifacts + prompts", deps: [docs/product-context.md, docs/code-map.md, docs/architecture.md, CLAUDE.md], state: active, last: "coordinator@2026-05-31" }
---

# Regeneration Kit

How to rebuild an equivalent version of this tool. The reliable recipe is **a
short prompt that points at durable artifacts + the test suite** — not one giant
prompt. The artifacts below carry the intent, the decisions, and the behaviour;
the prompt is just the ignition key.

## What answers what

| Question | Artifact |
|----------|----------|
| **WHY** — who it's for, what success is, what's out of scope | `docs/product-context.md` |
| **WHAT** — exact behaviour (the contract) | the **test suite** in `tests/` (`uv run pytest`) |
| **HOW** — the non-obvious decisions and trade-offs | `docs/adrs/` (0001–0005) |
| **HOW it scales** — millions of rows / multilingual | `docs/architecture.md` §9 |
| **Orientation** — package layout, public APIs, data flow | `docs/code-map.md` |
| **Conventions / guardrails** — plain-English output, security, commits | `CLAUDE.md`, ADR-0001, ADR-0002 |
| **Plain-English decision history** | `docs/decisions-log.md` |
| **Known debt / deferred** | `docs/tech-debt.md` |

The ADRs worth reading before touching code:

- **ADR-0003** — chat + DB-matching architecture (read-only store, rules-first
  intent, name matching rules).
- **ADR-0004** — token-index blocking for matching (don't full-scan).
- **ADR-0005** — containerised local deployment.

## Option A — rebuild from the artifacts (recommended)

Highest fidelity, because the agent can check itself against the tests. Hand it
this thin prompt:

```text
Read docs/product-context.md, every ADR in docs/adrs/, docs/code-map.md, and
CLAUDE.md. Then implement the system so the tests in tests/ pass. Work
test-first, in small conventional commits. Treat the ADRs as binding — ask
before deviating from any of them. Keep every user-facing message plain-English
per CLAUDE.md.
```

## Option B — rebuild from a single self-contained prompt

Use this when you do **not** have the repo (a greenfield rebuild). It is lossier
— you get an *equivalent* system, not a byte-identical one — and it has to spell
out the non-obvious decisions because there are no ADRs or tests to point at.

```text
Build a Python 3.12 tool called "Sales Lead Research".

PRODUCT: Given a company name, a salesperson wants to (1) see that company's full
corporate family tree — parent and subsidiaries — and (2) instantly know which of
those entities are already customers, so they can approach a new lead warm by
referencing an existing relationship. Core flow: type a company name in natural
language -> resolve its corporate hierarchy from public sources -> match every
entity against an internal customer list -> show the tree with an "Account ID"
column marking existing customers (and which are not yet customers).

CORPORATE-HIERARCHY DISCOVERY:
- Primary source: SEC EDGAR. Resolve the name to a CIK (company_tickers.json),
  find the latest annual report (10-K, falling back to 20-F for foreign filers),
  locate its Exhibit 21 ("list of subsidiaries"), and parse the subsidiary +
  jurisdiction table. Walk it recursively (depth 2) for subsidiaries that are
  themselves filers. Surface the filing's form and date so the user can judge
  freshness. Disambiguate when a name matches several filers.
- Fallback for non-SEC companies (DHL, Samsung, etc.): web-search their annual
  report / "list of subsidiaries", rank results (official PDF > annual report >
  Wikipedia > company site; demote content farms), and extract subsidiaries from
  HTML or PDF.
- Cache HTTP responses to disk with a TTL; send a descriptive SEC User-Agent.

CUSTOMER MATCHING:
- Customer data is SQLite (account_id, company_name, parent_id,
  ultimate_parent_id, location, country, tax_number, zip_code), opened READ-ONLY.
- Normalise names (lowercase; strip brackets and legal suffixes Inc/Ltd/GmbH/SAS)
  and classify each subsidiary vs the customer list as exact / close (token-set
  Jaccard >= 0.8) / none. Show all matches comma-separated; mark close ones
  "possibly <id> — verify".
- Do NOT scan the whole table per lookup: build an in-memory token inverted index
  when the store opens and score only candidate rows that share a token — and it
  must be provably equivalent to a full scan.

INTERFACES (all share one discovery + matching core):
1. Terminal chat (REPL): prints the hierarchy as an indented tree with account
   annotations, confirmation gates for company + filing, and writes an enriched CSV.
2. Gradio web UI on port 7860: same recursive tree, an Account ID column, CSV download.
3. A shared natural-language intent parser ("show me X's subsidiaries", "search
   for X", a bare name...); politely handle chit-chat.
4. Console entry point with an "init-db" subcommand; plus a script that seeds a
   realistic demo dataset (FedEx/DHL/Apple families with exact, near, duplicate,
   and unrelated rows).

PACKAGING / RUN ANYWHERE: manage with uv (pyproject + lockfile, hatchling build).
Provide a Dockerfile + docker-compose so `docker compose up` serves the web UI on
localhost:7860 and seeds the demo database on first run.

NON-NEGOTIABLES:
- Test-driven with pytest; mock all SEC/web calls via httpx MockTransport against
  saved fixtures; cover parsing, matching, intent, and both front-ends.
- ALL user-facing text in plain English for a non-technical salesperson: explain
  outcomes not internals, no jargon, graceful plain-English errors (never a stack
  trace).
- The Account ID column is always present (blank when no match); every successful
  lookup also writes a CSV; the customer database is read-only and gitignored
  (sensitive, regenerable data).
- Security-minded: guard URL building against injection, cap input length, keep
  data/credentials out of version control. Commit in small conventional commits.

DOCS: an architecture/system-design doc with diagrams that ALSO explains how the
matcher scales to millions of multilingual records (blocking -> candidate
generation -> calibrated scoring, with multilingual embeddings / ANN); a
code-map; and a tech-debt register.
```

## How a rebuild actually goes

1. Stand up the skeleton (package, uv, `pyproject.toml`, test runner).
2. Build the pure pieces first (name normalise / classify), test-first.
3. Build discovery (EDGAR → Exhibit 21 → recursive tree; web fallback) against
   saved fixtures with mocked HTTP.
4. Build the read-only store + token-index blocking (ADR-0004).
5. Wire matching into the front-ends (CLI + Gradio) — the Account ID column.
6. Add the container build (ADR-0005).
7. Run the full suite; a green suite is the definition of done.

Expect **iteration, not one shot**. The history of this repo shows the seams (the
matcher was built before it was wired into the UIs) — that is normal and fine.

## Fidelity note

- Artifacts + tests → reproducible **behaviour**.
- ADRs → reproducible **structure and decisions**.
- A prose-only prompt → an **equivalent** system, lossier the terser it gets.

Keep the artifacts in version control and the prompt thin. The documents are the
source of truth; the prompt is the ignition key.
