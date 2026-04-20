# agent-notes: { ctx: "web search fallback for non-SEC filers", deps: ["httpx", "bs4"], state: active, last: "sato@2026-04-20" }
"""Web search fallback for companies not found in SEC EDGAR.

When a company doesn't file with the SEC (e.g., DHL, Samsung), this
module searches the web for their annual report and extracts corporate
structure information.
"""

from __future__ import annotations

import re

import httpx


def web_search_subsidiaries(
    company_name: str,
    client: httpx.Client,
) -> dict:
    """Search the web for a non-SEC company's corporate structure.

    Returns a dict with:
      - ``parent``: parent company name (if found)
      - ``subsidiaries``: list of ``(name, jurisdiction)`` tuples
      - ``source``: URL of the source page
      - ``summary``: brief description of the company structure

    Returns an empty dict if nothing useful is found.
    """
    # Target the dedicated "list of subsidiaries / shareholdings" document
    # first — that's the structured table our PDF parser understands. If
    # the company doesn't publish one, the URL-priority pass below will
    # fall back to their investor pages, Wikipedia, etc.
    query = f"{company_name} annual report list of subsidiaries shareholdings"
    search_url = f"https://html.duckduckgo.com/html/?q={_url_encode(query)}"

    try:
        # Use a browser-like User-Agent for DDG
        search_client = httpx.Client(
            headers={"User-Agent": "Mozilla/5.0 (compatible)"},
            follow_redirects=True,
            timeout=15,
        )
        resp = search_client.get(search_url)
        resp.raise_for_status()
    except Exception:
        return {}

    # Extract URLs from DuckDuckGo Lite HTML results
    urls = _extract_ddg_urls(resp.text)
    if not urls:
        return {}

    # Rank URLs: official list-of-subsidiaries / annual-report pages first,
    # then Wikipedia and the company's own domain, then generic corporate
    # pages. SEO content farms and scribd are demoted.
    _JUNK_DOMAINS = (
        "firmsworld.com", "coursesidekick.com", "scribd.com",
        "studocu.com", "coursehero.com",
    )
    promising = [
        u for u in urls
        if _is_promising_url(u, company_name)
        and not any(d in u.lower() for d in _JUNK_DOMAINS)
    ]

    company_slug = company_name.lower().replace(" ", "")

    def _url_priority(url: str) -> int:
        url_lower = url.lower()
        # Official PDFs from the company's own investor pages are the
        # gold standard — rank them first.
        if url_lower.endswith(".pdf") and any(
            kw in url_lower for kw in
            ["list-of-shareholding", "list-of-subsidiar", "shareholding",
             "annual-report", "consolidated"]
        ):
            return 0
        if any(kw in url_lower for kw in
               ["list-of-subsidiaries", "group-structure", "consolidated-entities",
                "annual-report", "annualreport"]):
            return 1
        if "wikipedia" in url_lower:
            return 2
        if company_slug and company_slug in url_lower.replace("-", "").replace(".", ""):
            return 2
        if any(kw in url_lower for kw in ["division", "structure", "corporate", "group"]):
            return 3
        if any(kw in url_lower for kw in ["annual", "investor", "reporting", "about"]):
            return 4
        return 5

    promising.sort(key=_url_priority)

    # Try fetching the most promising results
    fetch_client = httpx.Client(
        headers={"User-Agent": "Mozilla/5.0 (compatible)"},
        follow_redirects=True,
        timeout=15,
    )
    for url in promising[:5]:
        try:
            page_resp = fetch_client.get(url, timeout=60)
            page_resp.raise_for_status()
            if url.lower().endswith(".pdf"):
                result = _extract_structure_from_pdf(page_resp.content, company_name)
            else:
                result = _extract_structure(page_resp.text, company_name)
            if result:
                result["source"] = url
                return result
        except Exception:
            continue

    return {}


def _url_encode(query: str) -> str:
    """Simple URL encoding for search queries."""
    from urllib.parse import quote_plus
    return quote_plus(query)


def _extract_ddg_urls(html: str) -> list[str]:
    """Extract result URLs from DuckDuckGo HTML search results."""
    from urllib.parse import unquote

    # DDG HTML results encode destination URLs in the 'uddg' query parameter
    uddg_pattern = re.compile(r'uddg=(https?[^&"]+)', re.I)
    seen: set[str] = set()
    urls: list[str] = []
    for match in uddg_pattern.finditer(html):
        url = unquote(match.group(1))
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def _is_promising_url(url: str, company_name: str) -> bool:
    """Check if a URL is likely to contain corporate structure info."""
    url_lower = url.lower()
    # PDFs from official annual reports / lists of shareholdings are
    # the best source — always promising.
    if url_lower.endswith(".pdf"):
        return any(kw in url_lower for kw in
                   ["annual", "report", "shareholding", "subsidiar",
                    "list-of", "consolidated"])
    keywords = ["annual-report", "investor", "corporate", "about",
                "structure", "subsidiary", "business-model", "reporting",
                "company-group", "group", "overview", "profile"]
    promising_domains = ["marketscreener.com", "reporting-hub", "companiesmarketcap"]
    if any(d in url_lower for d in promising_domains):
        return True
    return any(kw in url_lower for kw in keywords)


# Countries and US/Canadian states that appear as "<Country>, <City>" in
# the structured subsidiary tables we parse from PDFs and HTML.
_COUNTRIES = [
    "Germany", "France", "United States", "USA", "U.S.A.", "United Kingdom",
    "UK", "Japan", "China", "India", "Netherlands", "Switzerland", "Spain",
    "Italy", "Canada", "Mexico", "Brazil", "Australia", "Belgium", "Austria",
    "Sweden", "Denmark", "Norway", "Poland", "Ireland", "Singapore",
    "Hong Kong", "Korea", "South Korea", "Turkey", "Portugal", "Luxembourg",
    "Finland", "Czech Republic", "Czechia", "Hungary", "Greece",
    "South Africa", "UAE", "United Arab Emirates", "Russia", "Ukraine",
    "Bulgaria", "Estonia", "Latvia", "Lithuania", "Slovakia", "Slovenia",
    "Serbia", "Romania", "Macedonia", "Croatia", "Bosnia", "Montenegro",
    "Cayman Islands", "Barbados", "Bermuda", "Jersey", "Guernsey",
    "Colombia", "Venezuela", "Uruguay", "Argentina", "Chile", "Peru",
    "Malaysia", "Indonesia", "Thailand", "Vietnam", "Philippines",
    "Taiwan", "New Zealand", "Pakistan", "Bangladesh", "Israel", "Egypt",
    "Morocco", "Kenya", "Nigeria", "Ghana", "Saudi Arabia", "Qatar",
    "Bahrain", "Oman", "Kuwait", "Yemen", "Jordan", "Lebanon",
    "Puerto Rico", "Cyprus", "Malta", "Iceland",
    # US and Canadian subdivisions common in Exhibit-21-style tables
    "Delaware", "California", "New York", "Texas", "Nevada", "Florida",
    "Tennessee", "Pennsylvania", "Arkansas", "Ohio",
    "Ontario", "Quebec", "Nova Scotia", "British Columbia", "Alberta",
]


def _build_country_alt() -> str:
    # Longer names first so "United Kingdom" matches before "UK".
    ordered = sorted(_COUNTRIES, key=len, reverse=True)
    escaped = [re.escape(c) for c in ordered]
    return "|".join(escaped)


_COUNTRY_ALT = _build_country_alt()
_JURISDICTION_HINTS = re.compile(rf"\b(?:{_COUNTRY_ALT})\b", re.I)


def _looks_like_jurisdiction(text: str) -> bool:
    if not text:
        return False
    if len(text) > 60:
        return False
    return bool(_JURISDICTION_HINTS.search(text))


# Financial-statement line items that tend to show up in tables scraped
# from annual-report pages but are not subsidiaries.
_FINANCIAL_NOISE = {
    "revenue", "total", "net profit", "net income", "ebit", "ebitda",
    "operating income", "operating expenses", "material expense",
    "staff costs", "depreciation", "amortization", "impairment losses",
    "profit from operating activities", "net finance costs",
    "profit before income taxes", "income taxes", "consolidated net profit",
    "basic earnings per share", "diluted earnings per share",
    "intangible assets", "property, plant and equipment",
    "investment property", "noncurrent assets", "inventories",
    "other operating income", "other operating expenses",
    "other noncurrent assets", "deferred tax assets",
    "segment", "product/service", "region", "brand",
    "consolidation/other", "group functions/consolidation",
    "item (€ million)", "item ($ million)",
}


def _looks_like_financial_noise(name: str) -> bool:
    key = name.strip().lower()
    return key in _FINANCIAL_NOISE


def _extract_structure(html: str, company_name: str) -> dict | None:
    """Try to extract corporate structure from an HTML page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    subsidiaries: list[tuple[str, str]] = []
    parent: str | None = None

    # Strategy 1: Look for tables with subsidiary/company data
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            texts = [c.get_text(strip=True) for c in cells if c.get_text(strip=True)]
            if len(texts) >= 2:
                name = texts[0]
                if name.lower() in ("name", "company", "subsidiary", "entity", "#", "no."):
                    continue
                if 3 < len(name) < 120 and not name.startswith("http"):
                    if _looks_like_financial_noise(name):
                        continue
                    jurisdiction = ""
                    for candidate in texts[1:]:
                        if _looks_like_jurisdiction(candidate):
                            jurisdiction = candidate
                            break
                    subsidiaries.append((name, jurisdiction))

    # Strategy 2: Look for structured lists (ul/ol) in relevant sections
    if not subsidiaries:
        for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
            heading_text = heading.get_text(strip=True).lower()
            if any(kw in heading_text for kw in ["subsidiar", "division", "segment", "structure", "operating"]):
                for sibling in heading.find_next_siblings(["ul", "ol", "table", "div"]):
                    for li in sibling.find_all("li"):
                        text = li.get_text(strip=True)
                        if 3 < len(text) < 120:
                            subsidiaries.append((text, ""))
                    if subsidiaries:
                        break
                break

    # Strategy 3: Headings as division/subsidiary names
    if not subsidiaries:
        _skip_headings = {"downloads", "follow us", "contact", "related", "share",
                          "footer", "menu", "navigation", "search", "cookie", "privacy"}
        in_relevant_section = False
        for tag in soup.find_all(["h1", "h2", "h3", "h4"]):
            text_val = tag.get_text(strip=True)
            text_lower = text_val.lower()
            if tag.name in ("h1", "h2"):
                in_relevant_section = any(
                    kw in text_lower
                    for kw in ["division", "subsidiar", "segment", "structure",
                               "business", "companies", "brands", "operations"]
                )
            elif in_relevant_section and tag.name in ("h3", "h4"):
                if text_lower not in _skip_headings and 2 < len(text_val) < 100:
                    subsidiaries.append((text_val, ""))

    # Extract parent company from page text
    text = soup.get_text(separator=" ", strip=True)
    parent_patterns = [
        re.compile(r"(?:parent\s+company)\s*(?:is|:)\s*([A-Z][A-Za-z\s&.,]+?)(?:\.|,|\()", re.I),
        re.compile(rf"{re.escape(company_name)}.*?(?:subsidiary|division|unit|brand)\s+of\s+([A-Z][A-Za-z\s&.,]+?)(?:\.|,|\()", re.I),
        re.compile(r"(?:owned\s+by|part\s+of)\s+([A-Z][A-Za-z\s&.,]+?)(?:\.|,|\()", re.I),
    ]
    for pat in parent_patterns:
        m = pat.search(text)
        if m:
            candidate = m.group(1).strip().rstrip(",. ")
            if 3 < len(candidate) < 80:
                parent = candidate
                break

    if not subsidiaries and not parent:
        return None

    # Deduplicate on (lower-cased name) while preserving first-seen jurisdiction.
    seen: set[str] = set()
    unique_subs: list[tuple[str, str]] = []
    for name, jurisdiction in subsidiaries:
        key = name.strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique_subs.append((name, jurisdiction))

    return {
        "parent": parent or "",
        "subsidiaries": unique_subs[:50],
        "summary": f"Web search result for {company_name}",
    }


# Matches a trailing "<equity%> <CCY> <equity> <net>" block at the end of a
# line of a "List of shareholdings" PDF. Captures let us strip the numeric
# columns so the remaining prefix is "<name> <country>, <city>".
_PDF_TRAILING_NUMBERS_RE = re.compile(
    r"\s+\d+\.\d{1,2}\s+[A-Z]{3}\s+-?[\d,.]+\s+-?[\d,.]+\s*$"
)

# Footnote markers pypdf often attaches to company names, e.g.
# "ABIS GmbH 6), 9)" — strip them to get a clean name.
_PDF_FOOTNOTE_RE = re.compile(r"\s+\d{1,2}\)(?:\s*,\s*\d{1,2}\))*\s*$")

def _extract_structure_from_pdf(
    pdf_bytes: bytes,
    company_name: str,
) -> dict | None:
    """Pull a list of subsidiaries out of an annual-report / shareholdings PDF.

    The common shape of each line in these documents is:

        ``<Company Name> [footnote markers] <Country>, <City>
         <pct> <CCY> <equity> <net-income>``

    We anchor on the trailing numeric columns, then split the remaining
    prefix into ``name`` and ``<Country>, <City>`` using the country
    vocabulary we share with the HTML extractor.
    """
    import io

    try:
        import pypdf
    except ImportError:
        return None

    try:
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    except Exception:
        return None

    subsidiaries: list[tuple[str, str]] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            match = _PDF_TRAILING_NUMBERS_RE.search(line)
            if not match:
                continue
            prefix = line[: match.start()].strip()
            if not prefix:
                continue

            # The real "<Country>, <City>" block sits at the *end* of the
            # prefix. Company names often contain country words inside
            # parens ("DHL Express (Portugal) Lda."), so we scan from the
            # right and pick the last country immediately followed by ", ".
            pos = -1
            for m in _JURISDICTION_HINTS.finditer(prefix):
                tail = prefix[m.end() : m.end() + 2]
                if tail.startswith(","):
                    pos = m.start()
            if pos <= 0:
                continue
            name = prefix[:pos].strip()
            jurisdiction = prefix[pos:].strip()
            name = _PDF_FOOTNOTE_RE.sub("", name).strip()
            if len(name) < 3 or len(name) > 150:
                continue
            if _looks_like_financial_noise(name):
                continue
            subsidiaries.append((name, jurisdiction))

    if not subsidiaries:
        return None

    # Deduplicate on lower-cased name, first-seen jurisdiction wins.
    seen: set[str] = set()
    unique: list[tuple[str, str]] = []
    for name, jurisdiction in subsidiaries:
        key = name.strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append((name, jurisdiction))

    return {
        "parent": company_name,
        "subsidiaries": unique,
        "summary": f"Parsed {len(unique)} subsidiaries from PDF",
    }
