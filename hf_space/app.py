# agent-notes: { ctx: "Hugging Face Space entry point; thin shim over sales_lead_research.web", deps: ["src/sales_lead_research/web.py"], state: active, last: "sato@2026-05-31" }
"""Hugging Face Spaces entry point.

The web UI lives in the installed package (``sales_lead_research.web``), so
this is a thin shim — no vendored copy of the discovery / matching / UI code
to drift out of sync. The Space installs the package via requirements.txt.
"""

from sales_lead_research.web import build_app

demo = build_app()

if __name__ == "__main__":
    demo.launch()
