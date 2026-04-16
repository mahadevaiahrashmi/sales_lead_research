# agent-notes: { ctx: "issue #2 acceptance tests for SEC EDGAR lookup pipeline", deps: ["src/sales_lead_research/edgar.py", "tests/fixtures/edgar/"], state: active, last: "tara@2026-04-16" }
"""Acceptance tests for issue #2: SEC EDGAR company lookup.

Drives ``edgar.py`` functions against fixture files via ``httpx.MockTransport``.
No live network calls.
"""

import json
import re
from pathlib import Path

import httpx
import pytest

from sales_lead_research.edgar import (
    AmbiguousCompanyName,
    CompanyNotFound,
    No10KFiled,
    NoExhibit21,
    build_client,
    exhibit_21_url,
    find_exhibit_21,
    latest_10k_accession,
    resolve_cik,
)

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _mock_handler(request: httpx.Request) -> httpx.Response:
    """Route requests to fixture files based on URL path."""
    url = str(request.url)

    if url == "https://www.sec.gov/files/company_tickers.json":
        return httpx.Response(200, content=_fixture("company_tickers.json"))

    if url == "https://data.sec.gov/submissions/CIK0000320193.json":
        return httpx.Response(200, content=_fixture("CIK0000320193.json"))

    if url == "https://data.sec.gov/submissions/CIK0003333333.json":
        return httpx.Response(200, content=_fixture("CIK0003333333.json"))

    if "000032019324000123/0000320193-24-000123-index.htm" in url:
        return httpx.Response(200, content=_fixture("apple_10k_filing_index.html"))

    if "000032019323000106/0000320193-23-000106-index.htm" in url:
        return httpx.Response(200, content=_fixture("no_ex21_filing_index.html"))

    return httpx.Response(404, text="Not found in test fixtures")


@pytest.fixture()
def client() -> httpx.Client:
    transport = httpx.MockTransport(_mock_handler)
    return httpx.Client(
        transport=transport,
        headers={"User-Agent": "Sales Lead Research (test@example.com)"},
    )


class TestResolveCik:
    def test_happy_path_apple(self, client):
        assert resolve_cik("Apple Inc.", client) == "0000320193"

    def test_case_insensitive(self, client):
        assert resolve_cik("apple inc.", client) == "0000320193"

    def test_uppercase_match(self, client):
        assert resolve_cik("microsoft corp", client) == "0000789019"

    def test_strips_whitespace(self, client):
        assert resolve_cik("  Apple Inc.  ", client) == "0000320193"

    def test_not_found_raises(self, client):
        with pytest.raises(CompanyNotFound):
            resolve_cik("Nonexistent Corp", client)

    def test_ambiguous_raises(self, client):
        with pytest.raises(AmbiguousCompanyName):
            resolve_cik("Acme Holdings Inc.", client)


class TestLatest10KAccession:
    def test_happy_path_apple(self, client):
        result = latest_10k_accession("0000320193", client)
        assert result == "0000320193-24-000123"

    def test_skips_non_10k(self, client):
        result = latest_10k_accession("0000320193", client)
        assert result != "0000320193-24-000100"

    def test_no_10k_raises(self, client):
        with pytest.raises(No10KFiled):
            latest_10k_accession("0003333333", client)


class TestExhibit21Url:
    def test_happy_path_returns_absolute_url(self, client):
        url = exhibit_21_url("0000320193", "0000320193-24-000123", client)
        assert url.startswith("https://")
        assert "aapl-20240928ex211.htm" in url

    def test_resolves_relative_href(self, client):
        url = exhibit_21_url("0000320193", "0000320193-24-000123", client)
        assert url.startswith("https://www.sec.gov/Archives/edgar/data/")

    def test_no_exhibit_21_raises(self, client):
        with pytest.raises(NoExhibit21):
            exhibit_21_url("0000320193", "0000320193-23-000106", client)


class TestFindExhibit21:
    def test_end_to_end_apple(self, client):
        url = find_exhibit_21("Apple Inc.", client)
        assert "aapl-20240928ex211.htm" in url
        assert url.startswith("https://")

    def test_end_to_end_not_found(self, client):
        with pytest.raises(CompanyNotFound):
            find_exhibit_21("Nonexistent Corp", client)


class TestUserAgentCompliance:
    def test_build_client_sets_user_agent(self):
        ua = "Sales Lead Research (test@example.com)"
        c = build_client(ua)
        assert c.headers["user-agent"] == ua

    def test_requests_carry_user_agent(self):
        captured_headers = []

        def capturing_handler(request: httpx.Request) -> httpx.Response:
            captured_headers.append(dict(request.headers))
            return httpx.Response(200, content=_fixture("company_tickers.json"))

        ua = "Sales Lead Research (compliance-test@example.com)"
        c = build_client(ua)
        c._transport = httpx.MockTransport(capturing_handler)
        try:
            resolve_cik("Apple Inc.", c)
        except NotImplementedError:
            pytest.skip("resolve_cik not implemented yet")

        assert len(captured_headers) > 0
        for headers in captured_headers:
            assert re.search(r"[\w.+-]+@[\w.-]+", headers.get("user-agent", "")), (
                f"User-Agent missing email: {headers.get('user-agent')}"
            )
