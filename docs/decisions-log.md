<!-- agent-notes: { ctx: "layman-English running log of decisions made with the human", deps: [docs/product-context.md, docs/adrs/0003-sales-assistant-chat-architecture.md], state: active, last: "coordinator@2026-04-20" } -->

# Decisions Log — Plain English

This file is a running record of every meaningful decision made while building this tool, written so anyone (sales, product, a new developer) can follow along without digging through the formal documents. Formal records still live in the architecture decision records and the product context file; this log is the friendly summary.

Each entry says: **what we chose**, **why**, and **who decided**.

---

## Session of 2026-04-20

### What we are actually building

- **Chat tool that looks up a company's subsidiaries and flags which ones are already customers.**
  The salesperson types a company name (or a question like "show me FedEx's tree"), the tool finds all subsidiaries of that company, and for each subsidiary it also shows the account ID if that subsidiary is already a customer.
  *Decided by: you.*

- **Reuse the existing subsidiary-lookup code, don't rebuild it.**
  The current tool already knows how to pull subsidiary lists from public filings. We keep that exactly as it is and bolt on the new parts (chat window + customer-list matching).
  *Decided by: you.*

- **Chat window, not a plain search box.**
  A chat window is more flexible ("show me just the French ones") but also more fragile (it can misunderstand a query). You picked chat anyway, knowing the trade-off.
  *Decided by: you.*

- **Build for one user on one laptop for now.**
  Multi-user, shared storage, and login are all version-2 problems. Version 1 is a single salesperson on a single machine.
  *Decided by: you.*

### How the tool will match subsidiary names against the customer list

- **Ignore capitalisation and legal suffixes when matching names.**
  "Apple Inc." and "apple" are treated as the same company. Suffixes like "Inc", "Ltd", "GmbH", "Lda", "SAS", "S.A.", "Corp" get stripped from both sides before comparing.
  *Decided by: you and the team.*

- **Show "close" matches too, with a visible warning.**
  If "FedEx Corporate Service Inc" in the customer list is almost (but not exactly) the same as "FedEx Corporate Services, Inc." in the subsidiary list, the tool shows it as *"Possibly ACCT-1234 — verify"* so the salesperson knows to double-check. Beats silently missing a real match, and beats silently claiming a wrong match.
  *Decided by: you.*

- **Similarity threshold for "close" is 0.8** on a standard word-overlap score. Educated guess; tune later once we have real data.
  *Decided by: me, subject to your review.*

- **When one subsidiary matches several customer rows, show all the account IDs.**
  Comma-separated in the cell. Keeps all the information visible; if the customer list has duplicates, the salesperson can see them.
  *Decided by: you.*

- **Mixed case — one exact match plus one close match** for the same subsidiary renders as `[Account: ACCT-123] (also possibly ACCT-789 — verify)`. One line, exact shown first, close flagged.
  *Decided by: me.*

### What the user sees

- **Every answer shows when the data was filed.**
  Something like *"Subsidiaries from FedEx Corporation's annual report filed 2025-04-15."* Means a salesperson can tell at a glance whether the data is recent enough to rely on.
  *Decided by: you.*

- **The tree shape stays in the chat; the spreadsheet stays flat.**
  In the chat window the subsidiaries are shown as an indented tree (parent on top, children underneath). The exported spreadsheet is a flat list with an extra "Account ID" column — easier to paste into other tools.
  *Decided by: you.*

- **Spreadsheet export is never optional.**
  Every successful lookup writes a spreadsheet file alongside the chat output, so the salesperson can hand it on or load it into another tool.
  *Decided by: you (carried over from the earlier tool).*

- **All messages are in plain English.**
  No jargon, no error codes, no stack traces. If something breaks, the tool says so in a sentence like *"Couldn't find FedEx on the filings website."*
  *Decided by: you (codified across the whole project).*

- **Archive, don't delete.**
  Any code or file we remove goes into an `archive/` folder rather than being deleted outright. Recoverable history over clean-room repos.
  *Decided by: you (project-wide rule).*

### Security and privacy

- **The online (Hugging Face) version is allowed to read the customer list.**
  This means the customer file — including tax numbers and postcodes — gets uploaded to a public hosting provider. The team's security reviewer flagged this as a top risk; you accepted it as a version-1 trade-off for demo speed. The acceptance is recorded in the architecture decision record so it is on the audit trail.
  *Decided by: you, explicitly, after the risk was surfaced.*

- **We will look at redacting tax numbers from the online version as a follow-up.**
  Not blocking version 1. A small separate decision record will be written after the main feature ships, owned by the security reviewer with product input.
  *Decided by: me.*

- **The customer database is read-only at the connection level.**
  Even if a future change accidentally tried to write to the customer list, the database connection itself would refuse. Belt-and-braces: no write code is shipped AND no writes are allowed by the connection.
  *Decided by: the team (architecture decision record §3).*

### Which database and why

- **SQLite.**
  Open source, free, stores the whole customer list in a single file, needs no server to run. Already included with Python. Fits the "one salesperson on one laptop" shape of version 1. If we outgrow it, PostgreSQL is the next step — also open source and free.
  *Decided by: you (you asked for an open-source free option; I picked SQLite over PostgreSQL based on version-1 scale).*

- **No heavyweight database library.**
  We use Python's built-in SQLite library directly with safe, parameterised queries. Avoids adding a dependency (like SQLAlchemy) for a small job.
  *Decided by: the team.*

- **The path to the customer database comes from an environment variable** (`SALES_DB_PATH`). If the file is missing, the tool still runs and just says so in plain English.
  *Decided by: the team.*

- **A dummy customer database with 47 fake companies is included** (FedEx, DHL, Apple, Microsoft, 3M families plus some unrelated noise). Designed so every matching path can be demoed — exact, close, duplicate, and "parens in the country name" cases.
  *Decided by: you (you asked for dummy data); content chosen by me.*

### How the code is shaped under the hood

- **The code is split into three clear areas.**
  One for finding subsidiaries (the existing code, moved), one for matching names against the customer list (new), one for understanding chat queries and pulling the pieces together (new).
  *Decided by: the team.*

- **All three ways of running the tool (terminal, local web page, online web page) share the same core function.**
  Before, each version had its own pattern-matching and spreadsheet-writing code. Now they all call the same `answer(query)` function and only differ in how they display the result.
  *Decided by: the team.*

- **Chat understanding is rules-based, not a large-language-model.**
  Faster, cheaper, works offline, easier to test. The sales team types a predictable shape of question, and regular-expression patterns cover it. A language-model fallback is a future option if those patterns prove too narrow.
  *Decided by: the team.*

- **The old two-prompt terminal flow ("Proceed? [Y/n]") goes away.**
  Chat is one turn per question. The old flow moves to `archive/pre-chat-cli/` in case we ever want to look at it again.
  *Decided by: the team.*

### Plan for building it

- **Five waves, thirteen work items**, one wave per work session. First wave is a pure move (no behaviour change, all existing tests stay green), last wave is end-to-end verification.
  *Decided by: the team.*

- **Test-first for all medium and large items.**
  The testing specialist writes the failing test before any implementation. Safety net; codified in the project rules.
  *Decided by: you (project-wide rule).*

- **Development container is set up** with Python 3.12, the `uv` dependency manager, and port forwarding for the local web version. Anyone opening the project in Visual Studio Code or GitHub Codespaces gets an identical environment.
  *Decided by: you (you said "yes" when I offered); contents chosen by me.*

### Deferred to later (not blocking version 1)

- Full schema initialisation command for the customer database.
- Automatic bundling of the online version from the shared code.
- Language-model fallback for chat understanding.
- More sophisticated fuzzy matching (beyond suffix stripping).
- Multi-user, shared-drive, authentication.
- Redacting sensitive columns (tax numbers, postcodes) on the online version.
- Tidying the one dodgy DHL row (a PDF layout artefact).
- SEC rate limiting.
- A cache-folder flag on the terminal tool.
- A continuous-integration pipeline that runs the test suite on every push.
