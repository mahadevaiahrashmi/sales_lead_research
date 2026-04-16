# agent-notes: { ctx: "web search fallback for non-SEC filers", deps: ["httpx"], state: active, last: "sato@2026-04-16" }
"""Web search fallback for companies not found in SEC EDGAR.

When a company doesn't file with the SEC (e.g., DHL, Samsung), this
module searches the web for their annual report and extracts corporate
structure information.
"""

from __future__ import annotations

import json
import re

import httpx

# Brave Search API (free tier: 2000 queries/month)
_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


def web_search_subsidiaries(
    company_name: str,
    client: httpx.Client,
) -> dict[str, str | list[str]]:
    """Search the web for a non-SEC company's corporate structure.

    Returns a dict with:
      - ``parent``: parent company name (if found)
      - ``subsidiaries``: list of subsidiary/division names
      - ``source``: URL of the source page
      - ``summary``: brief description of the company structure

    Returns an empty dict if nothing useful is found.
    """
    # Use DuckDuckGo HTML search as a free fallback (no API key needed)
    query = f"{company_name} annual report subsidiaries parent company corporate structure"
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

    # Rank URLs: prefer official company sites, then annual report sites, then Wikipedia
    promising = [u for u in urls if _is_promising_url(u, company_name)]

    def _url_priority(url: str) -> int:
        url_lower = url.lower()
        if "wikipedia" in url_lower:
            return 3
        if "scribd" in url_lower:
            return 3
        if any(kw in url_lower for kw in ["division", "structure", "about", "corporate"]):
            return 0
        if any(kw in url_lower for kw in ["annual", "investor", "reporting"]):
            return 1
        return 2

    promising.sort(key=_url_priority)

    # Try fetching the most promising results
    fetch_client = httpx.Client(
        headers={"User-Agent": "Mozilla/5.0 (compatible)"},
        follow_redirects=True,
        timeout=15,
    )
    for url in promising[:5]:
        try:
            page_resp = fetch_client.get(url)
            page_resp.raise_for_status()
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
    # Skip PDFs (we can't parse them easily)
    if url_lower.endswith(".pdf"):
        return False
    keywords = ["annual-report", "investor", "corporate", "about",
                "structure", "subsidiary", "business-model", "reporting",
                "company-group", "group", "overview", "profile"]
    promising_domains = ["marketscreener.com", "reporting-hub", "companiesmarketcap"]
    if any(d in url_lower for d in promising_domains):
        return True
    return any(kw in url_lower for kw in keywords)


def _extract_structure(html: str, company_name: str) -> dict | None:
    """Try to extract corporate structure from an HTML page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")

    subsidiaries: list[str] = []
    parent: str | None = None

    # Strategy 1: Look for tables with subsidiary/company data
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            texts = [c.get_text(strip=True) for c in cells if c.get_text(strip=True)]
            if len(texts) >= 2:
                name = texts[0]
                # Skip header-like rows
                if name.lower() in ("name", "company", "subsidiary", "entity", "#", "no."):
                    continue
                # Looks like a company name if it has reasonable length
                if 3 < len(name) < 120 and not name.startswith("http"):
                    subsidiaries.append(name)

    # Strategy 2: Look for structured lists (ul/ol) in relevant sections
    if not subsidiaries:
        for heading in soup.find_all(["h1", "h2", "h3", "h4"]):
            heading_text = heading.get_text(strip=True).lower()
            if any(kw in heading_text for kw in ["subsidiar", "division", "segment", "structure", "operating"]):
                # Get the next sibling list or paragraph
                for sibling in heading.find_next_siblings(["ul", "ol", "table", "div"]):
                    for li in sibling.find_all("li"):
                        text = li.get_text(strip=True)
                        if 3 < len(text) < 120:
                            subsidiaries.append(text)
                    if subsidiaries:
                        break
                break

    # Strategy 3: Headings as division/subsidiary names
    # Some corporate pages list divisions as h3/h4 under a relevant h1/h2
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
                    subsidiaries.append(text_val)

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

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_subs: list[str] = []
    for s in subsidiaries:
        if s not in seen:
            seen.add(s)
            unique_subs.append(s)

    return {
        "parent": parent or "",
        "subsidiaries": unique_subs[:50],
        "summary": f"Web search result for {company_name}",
    }
