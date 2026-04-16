# agent-notes: { ctx: "Gradio web UI for Sales Lead Research, HF Spaces entrypoint", deps: ["gradio", "sales_lead_research.edgar"], state: active, last: "sato@2026-04-16" }
"""Gradio web interface for Sales Lead Research.

Provides a browser-based UI for looking up SEC EDGAR corporate hierarchies.
Designed to run on Hugging Face Spaces.
"""

from __future__ import annotations

import csv
import io
import tempfile
from pathlib import Path

import gradio as gr

from sales_lead_research.edgar import (
    CompanyNotFound,
    EdgarLookupError,
    build_client,
    exhibit_21_url,
    latest_10k_accession,
    parse_exhibit_21,
    search_companies,
)
from sales_lead_research.web_fallback import web_search_subsidiaries

USER_AGENT = "Sales Lead Research (mahadevaiah.rashmi@gmail.com)"


import re

_NL_PATTERNS = [
    # "show me X's subsidiaries", "show X subsidiaries"
    re.compile(r"(?:show|list|get|find|look\s*up|fetch|pull|display)\s+(?:me\s+)?(?:the\s+)?(.+?)(?:'s)?\s+(?:subsidiaries|hierarchy|corporate\s+(?:structure|tree)|sub\s*companies|child\s+companies)", re.I),
    # "what are X's subsidiaries", "what companies does X own"
    re.compile(r"(?:what|which)\s+(?:are|companies?\s+(?:does|do))\s+(?:the\s+)?(.+?)(?:'s)?\s+(?:subsidiaries|own|have)", re.I),
    # "who does X own", "who are X's subsidiaries"
    re.compile(r"who\s+(?:does|do|are)\s+(?:the\s+)?(.+?)(?:'s)?\s+(?:own|subsidiaries)", re.I),
    # "subsidiaries of X", "hierarchy of X", "corporate structure of X"
    re.compile(r"(?:subsidiaries|hierarchy|corporate\s+(?:structure|tree)|sub\s*companies)\s+(?:of|for|under)\s+(?:the\s+)?(.+)", re.I),
    # "tell me about X", "search for X", "look up X"
    re.compile(r"(?:tell\s+me\s+about|search\s+(?:for)?|look\s*up|info\s+(?:on|about|for))\s+(?:the\s+)?(.+)", re.I),
]


def extract_company_name(query: str) -> str:
    """Extract a company name from a natural language query.

    If the query matches a known pattern, returns the extracted company
    name. Otherwise returns the original query unchanged, so plain
    company names still work.
    """
    query = query.strip()
    if not query:
        return query

    for pattern in _NL_PATTERNS:
        m = pattern.search(query)
        if m:
            return m.group(1).strip().rstrip("?!")

    # Strip trailing question marks / punctuation from plain queries
    return query.rstrip("?!")


def search(company_name: str) -> tuple[list[list[str]], str]:
    """Search for a company by name. Returns (matches_table, status_message)."""
    if not company_name.strip():
        return [], "Please enter a company name."

    client = build_client(USER_AGENT)
    try:
        matches = search_companies(company_name.strip(), client)
    except CompanyNotFound:
        return [], f"No SEC registrant found matching \"{company_name}\"."
    except EdgarLookupError as exc:
        return [], f"Error: {exc}"

    table = [[name, cik] for name, cik in matches]
    if len(matches) == 1:
        return table, f"Found: {matches[0][0]} (CIK: {matches[0][1]})"
    return table, f"Found {len(matches)} matches. Select one from the table below."


def lookup(company_name: str, cik: str) -> tuple[str, str, list[list[str]], str | None]:
    """Given a confirmed company, fetch its subsidiary hierarchy.

    Returns (info_text, source_url, subsidiaries_table, csv_file_path).
    """
    if not cik.strip():
        return "No company selected.", "", [], None

    client = build_client(USER_AGENT)
    try:
        accession = latest_10k_accession(cik, client)
        url = exhibit_21_url(cik, accession, client)
    except EdgarLookupError as exc:
        return f"Error: {exc}", "", [], None

    try:
        resp = client.get(url)
        resp.raise_for_status()
        subsidiaries = parse_exhibit_21(resp.text)
    except Exception as exc:
        return f"Error fetching Exhibit 21: {exc}", url, [], None

    if not subsidiaries:
        return "No subsidiaries found in the filing.", url, [], None

    # Build results
    info = f"{company_name} (CIK: {cik}) — {len(subsidiaries)} subsidiaries"
    table = [[name, jurisdiction] for name, jurisdiction in subsidiaries]

    # Generate CSV for download
    safe_name = company_name.lower().replace(" ", "_").replace("/", "_").replace("..", "_")
    csv_path = Path(tempfile.gettempdir()) / f"{safe_name}_subsidiaries.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Subsidiary Name", "Jurisdiction"])
        for name, jurisdiction in subsidiaries:
            writer.writerow([name, jurisdiction])

    return info, url, table, str(csv_path)


def _web_fallback(company_name: str):
    """Run web search fallback and return Gradio outputs."""
    client = build_client(USER_AGENT)
    result = web_search_subsidiaries(company_name, client)

    if not result or (not result.get("parent") and not result.get("subsidiaries")):
        return (
            f'No SEC filing or web data found for "{company_name}".',
            gr.update(choices=[], value=None, visible=False),
            gr.update(visible=False),
            gr.update(value=None, visible=False),
            gr.update(value=None, visible=False),
            gr.update(value=None, visible=False),
        )

    parent = result.get("parent", "")
    subs = result.get("subsidiaries", [])
    source = result.get("source", "")

    heading = parent or company_name
    info_parts = [f"**{heading}** — {len(subs)} divisions/subsidiaries (web search)"]
    if source:
        info_parts.append(f"\n\n[Source]({source})")
    info = "".join(info_parts)

    table = [[s, ""] for s in subs] if subs else []

    return (
        f"Not an SEC filer. Showing web search results for **{company_name}**.",
        gr.update(choices=[], value=None, visible=False),
        gr.update(visible=False),
        gr.update(value=info, visible=True),
        gr.update(value=table, visible=True) if table else gr.update(visible=False),
        gr.update(value=None, visible=False),
    )


def on_search(company_name: str):
    """Handle the search button click."""
    company_name = extract_company_name(company_name)
    matches, status = search(company_name)
    if not matches:
        # Fall back to web search for non-SEC filers
        return _web_fallback(company_name)

    if len(matches) == 1:
        # Auto-select the single match and fetch immediately
        name, cik = matches[0]
        info, url, table, csv_path = lookup(name, cik)
        source_md = f"[View Exhibit 21 Filing]({url})" if url else ""
        return (
            status,
            gr.update(choices=[f"{name} (CIK: {cik})"], value=f"{name} (CIK: {cik})", visible=False),
            gr.update(visible=False),
            gr.update(value=info, visible=True),
            gr.update(value=table, visible=True) if table else gr.update(visible=False),
            gr.update(value=csv_path, visible=True) if csv_path else gr.update(visible=False),
        )

    # Multiple matches — show dropdown
    choices = [f"{name} (CIK: {cik})" for name, cik in matches]
    return (
        status,
        gr.update(choices=choices, value=choices[0], visible=True),
        gr.update(visible=True),
        gr.update(value=None, visible=False),
        gr.update(value=None, visible=False),
        gr.update(value=None, visible=False),
    )


def on_select(selection: str):
    """Handle selection from the disambiguation dropdown."""
    if not selection:
        return (
            gr.update(value=None, visible=False),
            gr.update(value=None, visible=False),
            gr.update(value=None, visible=False),
        )

    # Parse "COMPANY NAME (CIK: 0001234567)" format
    parts = selection.rsplit(" (CIK: ", 1)
    if len(parts) != 2:
        return (
            gr.update(value="Invalid selection.", visible=True),
            gr.update(value=None, visible=False),
            gr.update(value=None, visible=False),
        )

    company_name = parts[0]
    cik = parts[1].rstrip(")")

    info, url, table, csv_path = lookup(company_name, cik)
    source_md = f"[View Exhibit 21 Filing]({url})" if url else ""
    info_with_link = f"{info}\n\n{source_md}" if source_md else info

    return (
        gr.update(value=info_with_link, visible=True),
        gr.update(value=table, visible=True) if table else gr.update(visible=False),
        gr.update(value=csv_path, visible=True) if csv_path else gr.update(visible=False),
    )


def _anthropic_theme() -> gr.themes.Base:
    """Build a Gradio theme matching Anthropic's website aesthetic."""
    return gr.themes.Base(
        primary_hue=gr.themes.Color(
            c50="#FDF4EE",
            c100="#FBEADB",
            c200="#F5D0B4",
            c300="#EFB68D",
            c400="#E49A6A",
            c500="#D97757",
            c600="#C4613F",
            c700="#A34D32",
            c800="#823D28",
            c900="#6B3222",
            c950="#4A2116",
            name="anthropic_terracotta",
        ),
        secondary_hue=gr.themes.Color(
            c50="#FAF7F2",
            c100="#F5F0E8",
            c200="#EBE4D8",
            c300="#DDD4C4",
            c400="#C9BDA8",
            c500="#B0A48C",
            c600="#968870",
            c700="#7A6E59",
            c800="#5E5545",
            c900="#463F33",
            c950="#2D2924",
            name="anthropic_sand",
        ),
        neutral_hue=gr.themes.Color(
            c50="#FAF7F2",
            c100="#F5F0E8",
            c200="#EBE4D8",
            c300="#DDD4C4",
            c400="#C9BDA8",
            c500="#B0A48C",
            c600="#968870",
            c700="#7A6E59",
            c800="#5E5545",
            c900="#463F33",
            c950="#1A1714",
            name="anthropic_neutral",
        ),
        font=[
            gr.themes.GoogleFont("Inter"),
            "ui-sans-serif",
            "system-ui",
            "sans-serif",
        ],
        font_mono=[
            gr.themes.GoogleFont("JetBrains Mono"),
            "ui-monospace",
            "monospace",
        ],
        radius_size=gr.themes.sizes.radius_md,
        spacing_size=gr.themes.sizes.spacing_lg,
    ).set(
        body_background_fill="#FAF7F2",
        body_background_fill_dark="#1A1714",
        body_text_color="#1A1714",
        body_text_color_dark="#F5F0E8",
        body_text_color_subdued="#5E5545",
        background_fill_primary="#FFFFFF",
        background_fill_primary_dark="#2D2924",
        background_fill_secondary="#F5F0E8",
        background_fill_secondary_dark="#463F33",
        border_color_primary="#EBE4D8",
        border_color_primary_dark="#5E5545",
        block_background_fill="#FFFFFF",
        block_background_fill_dark="#2D2924",
        block_border_color="#EBE4D8",
        block_border_width="1px",
        block_label_text_color="#5E5545",
        block_label_text_size="sm",
        block_shadow="0 1px 3px 0 rgba(26, 23, 20, 0.06)",
        block_title_text_color="#1A1714",
        button_primary_background_fill="#D97757",
        button_primary_background_fill_hover="#C4613F",
        button_primary_text_color="#FFFFFF",
        button_primary_border_color="#D97757",
        button_primary_shadow="none",
        button_secondary_background_fill="#F5F0E8",
        button_secondary_background_fill_hover="#EBE4D8",
        button_secondary_text_color="#1A1714",
        button_secondary_border_color="#DDD4C4",
        input_background_fill="#FFFFFF",
        input_background_fill_dark="#2D2924",
        input_border_color="#DDD4C4",
        input_border_color_focus="#D97757",
        input_shadow="none",
        input_shadow_focus="0 0 0 2px rgba(217, 119, 87, 0.2)",
        table_even_background_fill="#FAF7F2",
        table_odd_background_fill="#FFFFFF",
        table_border_color="#EBE4D8",
        panel_background_fill="#FFFFFF",
        panel_border_color="#EBE4D8",
    )


ANTHROPIC_CSS = """
.gradio-container {
    max-width: 960px !important;
    margin: 0 auto !important;
}
.prose h1 {
    color: #1A1714 !important;
    font-weight: 600 !important;
    letter-spacing: -0.02em !important;
}
.prose p, .prose li {
    color: #5E5545 !important;
    line-height: 1.7 !important;
}
.prose a {
    color: #D97757 !important;
    text-decoration: none !important;
}
.prose a:hover {
    text-decoration: underline !important;
}
footer {
    display: none !important;
}
"""


def build_app() -> gr.Blocks:
    """Build the Gradio app."""
    with gr.Blocks(
        title="Sales Lead Research — SEC EDGAR Subsidiary Lookup",
    ) as app:
        gr.Markdown(
            "# Sales Lead Research\n\n"
            "Look up a company's subsidiaries from its **SEC EDGAR** 10-K Exhibit 21 filing.  \n"
            "Type a company name, ticker symbol, or ask in plain English."
        )

        with gr.Row():
            company_input = gr.Textbox(
                label="Search",
                placeholder="e.g., FedEx, AAPL, show me Apple's subsidiaries, who does Microsoft own?",
                scale=4,
            )
            search_btn = gr.Button("Search", variant="primary", scale=1)

        status_text = gr.Markdown(value="", visible=True)

        company_dropdown = gr.Dropdown(
            label="Select a company",
            choices=[],
            visible=False,
            interactive=True,
        )
        select_btn = gr.Button("Look Up Subsidiaries", visible=False, variant="secondary")

        info_text = gr.Markdown(value=None, visible=False)

        results_table = gr.Dataframe(
            headers=["Subsidiary Name", "Jurisdiction"],
            label="Subsidiaries",
            visible=False,
            wrap=True,
        )

        csv_download = gr.File(label="Download CSV", visible=False)

        # Wire events
        search_btn.click(
            fn=on_search,
            inputs=[company_input],
            outputs=[status_text, company_dropdown, select_btn, info_text, results_table, csv_download],
        )
        company_input.submit(
            fn=on_search,
            inputs=[company_input],
            outputs=[status_text, company_dropdown, select_btn, info_text, results_table, csv_download],
        )
        select_btn.click(
            fn=on_select,
            inputs=[company_dropdown],
            outputs=[info_text, results_table, csv_download],
        )

    return app


if __name__ == "__main__":
    app = build_app()
    app.launch(theme=_anthropic_theme(), css=ANTHROPIC_CSS)
