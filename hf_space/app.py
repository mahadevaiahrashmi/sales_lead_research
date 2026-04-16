# Sales Lead Research — Gradio Web UI for Hugging Face Spaces
# Self-contained: bundles the EDGAR lookup pipeline inline.

from __future__ import annotations

import csv
import tempfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import gradio as gr
import httpx
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# EDGAR lookup pipeline (inlined from sales_lead_research.edgar)
# ---------------------------------------------------------------------------

USER_AGENT = "Sales Lead Research (mahadevaiah.rashmi@gmail.com)"


class EdgarLookupError(Exception):
    pass


class CompanyNotFound(EdgarLookupError):
    pass


class No10KFiled(EdgarLookupError):
    pass


class NoExhibit21(EdgarLookupError):
    pass


class _FilingIndexParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_td = False
        self._in_a = False
        self._current_href: str | None = None
        self._cells: list[str] = []
        self._rows: list[tuple[str, str]] = []
        self._current_text = ""

    @property
    def rows(self) -> list[tuple[str, str]]:
        return self._rows

    def handle_starttag(self, tag, attrs):
        if tag == "td":
            self._in_td = True
            self._current_text = ""
        elif tag == "a" and self._in_td:
            self._in_a = True
            self._current_href = dict(attrs).get("href")

    def handle_endtag(self, tag):
        if tag == "td":
            self._in_td = False
            self._cells.append(self._current_text.strip())
            self._current_text = ""
        elif tag == "a":
            self._in_a = False
        elif tag == "tr":
            if len(self._cells) >= 4 and self._current_href is not None:
                self._rows.append((self._cells[3], self._current_href))
            self._cells = []
            self._current_href = None

    def handle_data(self, data):
        if self._in_td:
            self._current_text += data


_HEADER_KEYWORDS = frozenset([
    "name of subsidiary", "subsidiary", "nameofsubsidiary",
    "jurisdiction", "state or jurisdiction", "jurisdictionofincorporation",
    "jurisdictionofincorporationororganization",
])


def _is_header_row(name: str, jurisdiction: str) -> bool:
    return (
        name.lower().replace(" ", "") in _HEADER_KEYWORDS
        or jurisdiction.lower().replace(" ", "") in _HEADER_KEYWORDS
    )


def _client() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": USER_AGENT})


def search_companies(name: str) -> list[tuple[str, str]]:
    client = _client()
    resp = client.get("https://www.sec.gov/files/company_tickers.json")
    resp.raise_for_status()
    tickers = resp.json()
    needle = name.strip().lower()
    matches = []
    for entry in tickers.values():
        if needle in entry["title"].strip().lower():
            cik = str(entry["cik_str"]).zfill(10)
            matches.append((entry["title"], cik))
    if not matches:
        raise CompanyNotFound(f'No SEC registrant found matching "{name}".')
    return matches


def latest_10k_accession(cik: str) -> str:
    client = _client()
    resp = client.get(f"https://data.sec.gov/submissions/CIK{cik}.json")
    resp.raise_for_status()
    data = resp.json()
    recent = data["filings"]["recent"]
    for acc, form in zip(recent["accessionNumber"], recent["form"]):
        if form == "10-K":
            return acc
    raise No10KFiled(f"No 10-K filing found for CIK {cik}.")


def exhibit_21_url(cik: str, accession: str) -> str:
    cik_int = str(int(cik))
    acc_nodash = accession.replace("-", "")
    index_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_nodash}/{accession}-index.htm"
    client = _client()
    resp = client.get(index_url)
    resp.raise_for_status()
    parser = _FilingIndexParser()
    parser.feed(resp.text)
    for doc_type, href in parser.rows:
        if doc_type.startswith("EX-21"):
            return urljoin(index_url, href)
    raise NoExhibit21(f"No Exhibit 21 found in filing {accession}.")


def parse_exhibit_21(html: str) -> list[tuple[str, str]]:
    if not html.strip():
        return []
    soup = BeautifulSoup(html, "html.parser")
    results = []
    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) == 2:
                n = cells[0].get_text(strip=True)
                j = cells[1].get_text(strip=True)
                if n and j and not _is_header_row(n, j):
                    results.append((n, j))
    return results


# ---------------------------------------------------------------------------
# Gradio UI
# ---------------------------------------------------------------------------

def on_search(company_name: str):
    if not company_name.strip():
        return "Please enter a company name.", gr.update(choices=[], visible=False), gr.update(visible=False)

    try:
        matches = search_companies(company_name)
    except CompanyNotFound as e:
        return str(e), gr.update(choices=[], visible=False), gr.update(visible=False)
    except Exception as e:
        return f"Error: {e}", gr.update(choices=[], visible=False), gr.update(visible=False)

    choices = [f"{name} | CIK: {cik}" for name, cik in matches]

    if len(matches) == 1:
        return (
            f"Found: **{matches[0][0]}** (CIK: {matches[0][1]})",
            gr.update(choices=choices, value=choices[0], visible=True),
            gr.update(visible=True),
        )

    return (
        f"Found {len(matches)} matches. Select one below.",
        gr.update(choices=choices, value=choices[0], visible=True),
        gr.update(visible=True),
    )


def on_lookup(selection: str):
    if not selection:
        return "", "", [], None

    # Parse "COMPANY NAME | CIK: 0001234567"
    parts = selection.split(" | CIK: ")
    if len(parts) != 2:
        return "Invalid selection.", "", [], None

    company_name = parts[0]
    cik = parts[1]

    try:
        accession = latest_10k_accession(cik)
        url = exhibit_21_url(cik, accession)
    except EdgarLookupError as e:
        return str(e), "", [], None

    try:
        client = _client()
        resp = client.get(url)
        resp.raise_for_status()
        subsidiaries = parse_exhibit_21(resp.text)
    except Exception as e:
        return f"Error fetching Exhibit 21: {e}", url, [], None

    if not subsidiaries:
        return "No subsidiaries found in the filing.", url, [], None

    info = f"**{company_name}** (CIK: {cik}) — **{len(subsidiaries)} subsidiaries**\n\n[View Exhibit 21 Filing]({url})"
    table = [[n, j] for n, j in subsidiaries]

    # CSV download
    safe = company_name.lower().replace(" ", "_").replace("/", "_").replace("..", "_")
    csv_path = Path(tempfile.gettempdir()) / f"{safe}_subsidiaries.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Subsidiary Name", "Jurisdiction"])
        for n, j in subsidiaries:
            writer.writerow([n, j])

    return info, table, str(csv_path)


with gr.Blocks(
    title="Sales Lead Research — SEC EDGAR Subsidiary Lookup",
    theme=gr.themes.Soft(),
) as app:
    gr.Markdown(
        "# 🏢 Sales Lead Research\n"
        "Look up a company's subsidiaries from its **SEC EDGAR 10-K Exhibit 21** filing.\n\n"
        "Type a company name below to get started. Examples: `FedEx`, `Apple`, `Microsoft`, `JPMorgan Chase`"
    )

    with gr.Row():
        company_input = gr.Textbox(
            label="Company Name",
            placeholder="e.g., FedEx, Apple, Microsoft",
            scale=4,
        )
        search_btn = gr.Button("🔍 Search", variant="primary", scale=1)

    status_text = gr.Markdown("")

    company_dropdown = gr.Dropdown(
        label="Select a company",
        choices=[],
        visible=False,
        interactive=True,
    )
    lookup_btn = gr.Button("📋 Look Up Subsidiaries", visible=False, variant="primary")

    info_text = gr.Markdown("")
    results_table = gr.Dataframe(
        headers=["Subsidiary Name", "Jurisdiction"],
        label="Subsidiaries",
        visible=False,
        wrap=True,
    )
    csv_download = gr.File(label="Download CSV", visible=False)

    # Search event
    def do_search(name):
        status, dropdown_update, btn_update = on_search(name)
        return status, dropdown_update, btn_update, "", gr.update(visible=False), gr.update(visible=False)

    search_btn.click(
        fn=do_search,
        inputs=[company_input],
        outputs=[status_text, company_dropdown, lookup_btn, info_text, results_table, csv_download],
    )
    company_input.submit(
        fn=do_search,
        inputs=[company_input],
        outputs=[status_text, company_dropdown, lookup_btn, info_text, results_table, csv_download],
    )

    # Lookup event
    def do_lookup(selection):
        result = on_lookup(selection)
        if len(result) == 4:
            info, table, csv_path = result[0], result[1], result[3]
            return info, gr.update(visible=False), gr.update(visible=False)
        info, table, csv_path = result
        if not table:
            return info, gr.update(visible=False), gr.update(visible=False)
        return info, gr.update(value=table, visible=True), gr.update(value=csv_path, visible=True)

    lookup_btn.click(
        fn=do_lookup,
        inputs=[company_dropdown],
        outputs=[info_text, results_table, csv_download],
    )

if __name__ == "__main__":
    app.launch()
