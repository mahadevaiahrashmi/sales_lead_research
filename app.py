# agent-notes: { ctx: "local entry point for the Gradio web UI; thin shim over sales_lead_research.web", deps: ["src/sales_lead_research/web.py"], state: active, last: "sato@2026-05-31" }
"""Local entry point for the Sales Lead Research web UI.

The implementation lives in the package (``sales_lead_research.web``) so the
local entry point and the Hugging Face Space are thin shims over one
codebase — no vendored fork. Run it with:

    uv run python app.py        # -> http://localhost:7860 (honours $GRADIO_SERVER_*)
"""

from __future__ import annotations

# Re-export the handlers so existing imports and tests keep working.
from sales_lead_research.web import (  # noqa: F401
    build_app,
    lookup,
    main,
    on_search,
    on_select,
    search,
)

if __name__ == "__main__":
    main()
