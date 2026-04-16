# agent-notes: { ctx: "issue #5 tests for parent-company resolution", deps: ["src/sales_lead_research/edgar.py", "tests/fixtures/edgar/"], state: active, last: "sato@2026-04-16" }
"""Tests for issue #5: parent-company resolution (walk up the tree).

When the queried company is itself a subsidiary of another SEC filer,
the tool should detect this and offer to show the parent's full hierarchy.
"""

from pathlib import Path

import httpx
import pytest

from sales_lead_research.edgar import (
    find_parent_company,
    search_companies,
)

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _mock_handler(request: httpx.Request) -> httpx.Response:
    """Mock transport that knows about PARENT CORP -> CHILD INC hierarchy."""
    url = str(request.url)

    if url == "https://www.sec.gov/files/company_tickers.json":
        return httpx.Response(200, content=_fixture("company_tickers.json"))

    # PARENT CORP
    if url == "https://data.sec.gov/submissions/CIK0009999999.json":
        return httpx.Response(200, content=_fixture("CIK0009999999.json"))

    if "000999999924000001/0009999999-24-000001-index.htm" in url:
        return httpx.Response(200, content=_fixture("parent_10k_filing_index.html"))

    if "parent-20240101ex211.htm" in url:
        return httpx.Response(200, content=_fixture("parent_exhibit_21.html"))

    # CHILD INC
    if url == "https://data.sec.gov/submissions/CIK0008888888.json":
        return httpx.Response(200, content=_fixture("CIK0008888888.json"))

    if "000888888824000001/0008888888-24-000001-index.htm" in url:
        return httpx.Response(200, content=_fixture("child_10k_filing_index.html"))

    if "child-20240101ex211.htm" in url:
        return httpx.Response(200, content=_fixture("child_exhibit_21.html"))

    # FEDEX CORP
    if url == "https://data.sec.gov/submissions/CIK0001048911.json":
        return httpx.Response(200, content=_fixture("CIK0001048911.json"))

    if "000104891124000045/0001048911-24-000045-index.htm" in url:
        return httpx.Response(200, content=_fixture("fedex_10k_filing_index.html"))

    if "fdx-20240531ex211.htm" in url:
        return httpx.Response(200, content=_fixture("fedex_exhibit_21.html"))

    return httpx.Response(404, text=f"Not found: {url}")


@pytest.fixture()
def client() -> httpx.Client:
    transport = httpx.MockTransport(_mock_handler)
    return httpx.Client(
        transport=transport,
        headers={"User-Agent": "Sales Lead Research (test@example.com)"},
    )


class TestFindParentCompany:
    """find_parent_company should search other SEC filers' Exhibit 21s
    to find who lists the queried company as a subsidiary."""

    def test_child_inc_has_parent_corp_as_parent(self, client):
        """CHILD INC is listed in PARENT CORP's Exhibit 21."""
        parent = find_parent_company("CHILD INC", client)
        assert parent is not None
        assert parent[0] == "PARENT CORP"

    def test_returns_parent_name_and_cik(self, client):
        """Should return a (name, cik) tuple."""
        parent = find_parent_company("CHILD INC", client)
        assert parent is not None
        name, cik = parent
        assert name == "PARENT CORP"
        assert cik == "0009999999"

    def test_top_level_company_returns_none(self, client):
        """PARENT CORP has no parent — should return None."""
        parent = find_parent_company("PARENT CORP", client)
        assert parent is None

    def test_case_insensitive_matching(self, client):
        """Parent lookup should be case-insensitive."""
        parent = find_parent_company("child inc", client)
        assert parent is not None
        assert parent[0] == "PARENT CORP"

    def test_fedex_ground_is_subsidiary_of_fedex(self, client):
        """FedEx Ground Package System Inc. is listed in FEDEX CORP's Exhibit 21."""
        parent = find_parent_company("FedEx Ground Package System Inc.", client)
        assert parent is not None
        assert parent[0] == "FEDEX CORP"
