---
agent-notes: { ctx: "archived shims that bridged sales_lead_research.{edgar,web_fallback,cache} → discovery/* during the W1.1–W1.3 refactor", deps: [docs/adrs/0003-sales-assistant-chat-architecture.md, docs/plans/sales-assistant-chat-v1-plan.md], state: archived, last: "sato@2026-04-28" }
---

# Legacy Module Shims

These three files lived at `src/sales_lead_research/` and re-exported the discovery modules from their new home (`src/sales_lead_research/discovery/`) during the foundation refactor. They were removed in W1.3 (issue #14) once every internal caller had been redirected at the new public API in W1.2 (issue #13).

Kept here as a reference in case anyone hits an old import path in a fork, an external script, or a stale notebook and needs to see what the path used to mean. The file content is also visible in git history under `5688e57` (W1.1, where the shims were created) and `9fbde5f`..`<W1.3 commit>` (where they were retired).

Do not import from these files. The current public API is:

```python
from sales_lead_research.discovery import (
    build_client,
    search_companies,
    fetch_subsidiary_tree,
    web_search_subsidiaries,
    SubsidiaryNode,
    EdgarLookupError,
    CompanyNotFound,
    No10KFiled,
    NoExhibit21,
)
```
