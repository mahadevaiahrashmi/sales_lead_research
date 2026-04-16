# agent-notes: { ctx: "issue #9 tests for 20-F filing support", deps: ["src/sales_lead_research/edgar.py", "tests/fixtures/edgar/"], state: active, last: "sato@2026-04-16" }
"""Tests for issue #9: support 20-F filings for non-US parents.

Foreign private issuers file 20-F instead of 10-K. The lookup pipeline
should fall back to 20-F when no 10-K is found.
"""

from pathlib import Path

import httpx
import pytest

from sales_lead_research.edgar import (
    No10KFiled,
    exhibit_21_url,
    find_exhibit_21,
    latest_10k_accession,
    parse_exhibit_21,
)

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _mock_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)

    if url == "https://www.sec.gov/files/company_tickers.json":
        return httpx.Response(200, content=_fixture("company_tickers.json"))

    # Toyota — 20-F filer, no 10-K
    if url == "https://data.sec.gov/submissions/CIK0007777777.json":
        return httpx.Response(200, content=_fixture("CIK0007777777.json"))

    if "000777777724000010/0007777777-24-000010-index.htm" in url:
        return httpx.Response(200, content=_fixture("toyota_20f_filing_index.html"))

    if "tm-20240331ex211.htm" in url:
        return httpx.Response(200, content=_fixture("toyota_exhibit_21.html"))

    # Apple — 10-K filer (existing fixture)
    if url == "https://data.sec.gov/submissions/CIK0000320193.json":
        return httpx.Response(200, content=_fixture("CIK0000320193.json"))

    if "000032019324000123/0000320193-24-000123-index.htm" in url:
        return httpx.Response(200, content=_fixture("apple_10k_filing_index.html"))

    return httpx.Response(404, text=f"Not found: {url}")


@pytest.fixture()
def client() -> httpx.Client:
    transport = httpx.MockTransport(_mock_handler)
    return httpx.Client(
        transport=transport,
        headers={"User-Agent": "Sales Lead Research (test@example.com)"},
    )


class TestLatestAnnualAccession20F:
    """latest_10k_accession should fall back to 20-F for foreign filers."""

    def test_returns_20f_when_no_10k(self, client):
        """Toyota has no 10-K but has a 20-F; should return the 20-F accession."""
        result = latest_10k_accession("0007777777", client)
        assert result == "0007777777-24-000010"

    def test_prefers_10k_over_20f(self, client):
        """When both 10-K and 20-F exist, 10-K should be preferred."""
        result = latest_10k_accession("0000320193", client)
        assert result == "0000320193-24-000123"

    def test_no_10k_or_20f_raises(self):
        """A filer with neither 10-K nor 20-F should still raise No10KFiled."""
        # CIK 3333333 fixture has only 8-K filings
        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "CIK0003333333" in url:
                return httpx.Response(200, content=_fixture("CIK0003333333.json"))
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        c = httpx.Client(transport=transport, headers={"User-Agent": "test"})
        with pytest.raises(No10KFiled):
            latest_10k_accession("0003333333", c)


class TestFindExhibit21With20F:
    """End-to-end: find_exhibit_21 should work for 20-F filers."""

    def test_toyota_exhibit_21_found(self, client):
        url = find_exhibit_21("TOYOTA MOTOR CORP", client)
        assert "tm-20240331ex211.htm" in url

    def test_toyota_exhibit_21_is_absolute_url(self, client):
        url = find_exhibit_21("TOYOTA MOTOR CORP", client)
        assert url.startswith("https://")


class TestParseExhibit21ForForeignFiler:
    """Exhibit 21 parsing should work identically for 20-F filers."""

    def test_toyota_subsidiaries_parsed(self):
        html = _fixture("toyota_exhibit_21.html").decode()
        subs = parse_exhibit_21(html)
        names = [name for name, _jur in subs]
        assert "Toyota Motor North America Inc." in names
        assert "Lexus International" in names

    def test_toyota_subsidiary_count(self):
        html = _fixture("toyota_exhibit_21.html").decode()
        subs = parse_exhibit_21(html)
        assert len(subs) == 3
