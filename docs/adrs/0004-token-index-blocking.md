---
agent-notes: { ctx: "ADR: in-memory token-index blocking for customer matching", deps: [docs/adrs/0003-sales-assistant-chat-architecture.md, src/sales_lead_research/matching/store.py], state: active, last: "archie@2026-05-31" }
---

# ADR-0004: In-memory token-index blocking for customer matching

## Status

Accepted

## Context

ADR-0003 §4 specified name matching as: normalise both sides, then classify each
customer row as exact / close (token-set Jaccard ≥ 0.8) / none. The first
implementation did this with a full table scan — `lookup_with_confidence` read
every customer row and scored it on every subsidiary lookup.

That is O(rows) per subsidiary, per lookup. A single recursive company tree can
trigger dozens of lookups, and the stated production goal is a customer list of
millions of rows. Scoring every row every time does not scale, and it is the
question most likely to be raised in review ("how does the match run at scale?").

## Decision

Introduce a **blocking** step (candidate generation) in front of scoring.

- When the store is opened, build an **in-memory token inverted index** once: for
  every customer row, map each normalised name token → the account ids whose name
  contains it (plus an `account_id → name` map).
- `candidate_account_ids(name)` returns the union of the token buckets for the
  input's tokens — i.e. the rows that share at least one normalised token.
- `lookup_with_confidence` and `lookup_by_name` score **only** those candidates.

This is provably equivalent to the full scan: a row sharing no normalised token
with the input has an empty token intersection, so its Jaccard is 0 (never
"close") and its normalised form differs (never "exact"). The existing matching
tests are the equivalence guarantee — they pass unchanged.

The persistent / approximate-nearest-neighbour / multilingual version (for true
millions-scale, cross-language matching) is documented as the production target
in `docs/architecture.md` §9 and is explicitly out of scope here.

## Consequences

### Positive

- Each lookup costs ~O(candidates) instead of O(all rows); the index is built
  once per store-open and amortised across every lookup in a session.
- Identical public API and identical results — no change for callers or tests.
- Gives a concrete, demonstrable answer to "how does matching scale?" and a clean
  stepping-stone to the production design in `architecture.md` §9.

### Negative

- The index is rebuilt each time the store is opened. The web UI opens the store
  per request, so a very large list would pay that build cost repeatedly (tracked
  in `docs/tech-debt.md`, TD-002).
- Holds the customer names in memory; fine at v1 scale, not at millions.

### Neutral

- Matching *quality* is unchanged — this is purely a performance/structure change.
  Stemming, phonetics, and multilingual matching remain future work.
