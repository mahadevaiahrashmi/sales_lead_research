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

USER_AGENT = "Sales Lead Research (mahadevaiah.rashmi@gmail.com)"


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


def on_search(company_name: str):
    """Handle the search button click."""
    matches, status = search(company_name)
    if not matches:
        return (
            status,
            gr.update(choices=[], value=None, visible=False),
            gr.update(visible=False),
            gr.update(value=None, visible=False),
            gr.update(value=None, visible=False),
            gr.update(value=None, visible=False),
        )

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


def build_app() -> gr.Blocks:
    """Build the Gradio app."""
    with gr.Blocks(
        title="Sales Lead Research — SEC EDGAR Subsidiary Lookup",
        theme=gr.themes.Soft(),
    ) as app:
        gr.Markdown(
            "# Sales Lead Research\n"
            "Look up a company's subsidiaries from its SEC EDGAR 10-K Exhibit 21 filing.\n"
            "Type a company name below to get started."
        )

        with gr.Row():
            company_input = gr.Textbox(
                label="Company Name",
                placeholder="e.g., FedEx, Apple, Microsoft",
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
        select_btn = gr.Button("Look Up Subsidiaries", visible=False)

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
    app.launch()
