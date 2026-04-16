# agent-notes: { ctx: "SEC EDGAR lookup: name -> Exhibit 21 URL + parse", deps: ["httpx", "beautifulsoup4"], state: active, last: "sato@2026-04-16" }  # noqa: E501
"""SEC EDGAR company lookup — public contract (Sato: implement these).

Pipeline: company name -> CIK -> latest 10-K accession -> Exhibit 21 URL.
This module returns the Exhibit 21 URL; fetching/parsing it is issue #3.

Public contract
---------------
- ``build_client(user_agent: str) -> httpx.Client``
    Construct an ``httpx.Client`` whose default headers include a
    ``User-Agent`` equal to ``user_agent``. Centralizes SEC fair-use
    compliance so every outbound request carries the header.

- ``resolve_cik(name: str, client: httpx.Client) -> str``
    Fetch ``https://www.sec.gov/files/company_tickers.json`` and resolve
    ``name`` to a zero-padded 10-digit CIK string. Case-insensitive; strips
    surrounding whitespace. Raises ``CompanyNotFound`` if no entry's
    ``title`` matches. Raises ``AmbiguousCompanyName`` if more than one
    entry matches.

- ``latest_10k_accession(cik: str, client: httpx.Client) -> str``
    Fetch ``https://data.sec.gov/submissions/CIK{cik}.json`` and return
    the accession number of the most recent filing with ``form == "10-K"``
    (by ``filingDate``, descending). Accession format is the SEC's dashed
    form, e.g. ``"0000320193-24-000123"``. Raises ``No10KFiled`` if the
    filer has no 10-K entries in ``filings.recent``.

- ``exhibit_21_url(cik: str, accession: str, client: httpx.Client) -> str``
    Fetch the filing index page at
    ``https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{accession}-index.htm``
    and return the absolute URL of the document whose type is ``EX-21``
    (or ``EX-21.1`` / ``EX-21.2``). Relative hrefs must be resolved
    against the index URL. Raises ``NoExhibit21`` if no such row exists.

- ``find_exhibit_21(name: str, client: httpx.Client) -> str``
    Compose the three steps above and return the Exhibit 21 URL. This is
    the single entry point issue #3 will call from ``run_repl``.

Exception hierarchy
-------------------
``EdgarLookupError`` is the base; callers catch it to surface a clean
error to users. Specific subclasses let tests and future UX branch on
the exact failure mode.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

import httpx


class EdgarLookupError(Exception):
    """Base class for all EDGAR lookup failures."""


class CompanyNotFound(EdgarLookupError):
    """No company in the tickers file matched the given name."""


class AmbiguousCompanyName(EdgarLookupError):
    """More than one company in the tickers file matched the given name."""


class No10KFiled(EdgarLookupError):
    """The filer has no 10-K in its recent submissions."""


class NoExhibit21(EdgarLookupError):
    """The 10-K filing index has no Exhibit 21 document."""


class _FilingIndexParser(HTMLParser):
    """Minimal HTML parser to extract document rows from EDGAR filing index."""

    def __init__(self) -> None:
        super().__init__()
        self._in_td = False
        self._in_a = False
        self._current_href: str | None = None
        self._cells: list[str] = []
        self._rows: list[tuple[str, str]] = []  # (type, href)

    @property
    def rows(self) -> list[tuple[str, str]]:
        """Parsed document rows as (type, href) pairs."""
        return self._rows
        self._current_text = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "td":
            self._in_td = True
            self._current_text = ""
        elif tag == "a" and self._in_td:
            self._in_a = True
            attr_dict = dict(attrs)
            self._current_href = attr_dict.get("href")

    def handle_endtag(self, tag: str) -> None:
        if tag == "td":
            self._in_td = False
            self._cells.append(self._current_text.strip())
            self._current_text = ""
        elif tag == "a":
            self._in_a = False
        elif tag == "tr":
            # Cells: Seq, Description, Document, Type, Size
            if len(self._cells) >= 4 and self._current_href is not None:
                doc_type = self._cells[3]
                self._rows.append((doc_type, self._current_href))
            self._cells = []
            self._current_href = None

    def handle_data(self, data: str) -> None:
        if self._in_td:
            self._current_text += data


def build_client(user_agent: str) -> httpx.Client:
    return httpx.Client(headers={"User-Agent": user_agent})


def resolve_cik(name: str, client: httpx.Client) -> str:
    resp = client.get("https://www.sec.gov/files/company_tickers.json")
    resp.raise_for_status()
    tickers = resp.json()

    needle = name.strip().lower()
    matches: list[int] = []
    for entry in tickers.values():
        if entry["title"].strip().lower() == needle:
            matches.append(entry["cik_str"])

    if not matches:
        raise CompanyNotFound(name)
    if len(matches) > 1:
        raise AmbiguousCompanyName(name)

    return str(matches[0]).zfill(10)


def latest_10k_accession(cik: str, client: httpx.Client) -> str:
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    resp = client.get(url)
    resp.raise_for_status()
    data = resp.json()

    recent = data["filings"]["recent"]
    for acc, form in zip(recent["accessionNumber"], recent["form"]):
        if form == "10-K":
            return acc

    raise No10KFiled(cik)


def exhibit_21_url(cik: str, accession: str, client: httpx.Client) -> str:
    # int(cik) ensures only digits survive — guards against injection via
    # user-controlled strings flowing into the URL template.
    cik_int = str(int(cik))
    accession_no_dashes = accession.replace("-", "")
    index_url = (
        f"https://www.sec.gov/Archives/edgar/data/"
        f"{cik_int}/{accession_no_dashes}/{accession}-index.htm"
    )

    resp = client.get(index_url)
    resp.raise_for_status()

    parser = _FilingIndexParser()
    parser.feed(resp.text)

    for doc_type, href in parser.rows:
        if doc_type.startswith("EX-21"):
            return urljoin(index_url, href)

    raise NoExhibit21(accession)


def find_exhibit_21(name: str, client: httpx.Client) -> str:
    cik = resolve_cik(name, client)
    accession = latest_10k_accession(cik, client)
    return exhibit_21_url(cik, accession, client)


def search_companies(
    name: str,
    client: httpx.Client,
    *,
    cache_dir: Path | None = None,
) -> list[tuple[str, str]]:
    """Search for companies by title substring or ticker symbol (case-insensitive).

    Returns a list of ``(company_title, cik_str)`` tuples where ``cik_str``
    is a zero-padded 10-digit CIK. Checks both title (substring) and ticker
    (exact match), deduplicating by CIK. Raises ``CompanyNotFound`` if no
    entries match either field.

    When *cache_dir* is provided, ``company_tickers.json`` is cached locally
    to avoid redundant fetches.
    """
    url = "https://www.sec.gov/files/company_tickers.json"
    if cache_dir is not None:
        from sales_lead_research.cache import cached_get

        resp = cached_get(client, url, cache_dir)
    else:
        resp = client.get(url)
        resp.raise_for_status()
    tickers = resp.json()

    needle = name.strip().lower()
    seen_ciks: set[str] = set()
    matches: list[tuple[str, str]] = []

    for entry in tickers.values():
        cik = str(entry["cik_str"]).zfill(10)
        title_match = needle in entry["title"].strip().lower()
        ticker_match = entry.get("ticker", "").strip().lower() == needle
        if (title_match or ticker_match) and cik not in seen_ciks:
            seen_ciks.add(cik)
            matches.append((entry["title"], cik))

    if not matches:
        raise CompanyNotFound(
            f'No SEC registrant found matching "{name}". '
            f"This company may not file with the SEC (non-US parent, private, etc.)."
        )

    return matches


_HEADER_KEYWORDS = frozenset([
    "name of subsidiary", "subsidiary", "nameofsubsidiary",
    "jurisdiction", "state or jurisdiction", "jurisdictionofincorporation",
    "jurisdictionofincorporationororganization",
])


def _is_header_row(name: str, jurisdiction: str) -> bool:
    """Return True if the row looks like a table header, not data."""
    return (
        name.lower().replace(" ", "") in _HEADER_KEYWORDS
        or jurisdiction.lower().replace(" ", "") in _HEADER_KEYWORDS
    )


def parse_exhibit_21(html: str) -> list[tuple[str, str]]:
    """Parse an Exhibit 21 HTML page into ``(subsidiary_name, jurisdiction)`` pairs.

    Handles the common table format found in large filers' Exhibit 21 pages.
    Skips header rows and empty rows. Returns an empty list if no subsidiary
    data is found.
    """
    if not html.strip():
        return []

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    results: list[tuple[str, str]] = []

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) == 2:
                name = cells[0].get_text(strip=True)
                jurisdiction = cells[1].get_text(strip=True)
                if name and jurisdiction and not _is_header_row(name, jurisdiction):
                    results.append((name, jurisdiction))

    return results
