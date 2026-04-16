# agent-notes: { ctx: "issue #10 tests for non-SEC filer graceful fallback", deps: ["src/sales_lead_research/edgar.py", "src/sales_lead_research/cli.py"], state: active, last: "sato@2026-04-16" }
"""Tests for issue #10: graceful fallback for non-SEC filers.

Companies that don't file with the SEC (e.g., DHL, Samsung) should get
a clear message explaining why and suggesting the legal parent name.
"""

import io
from pathlib import Path

import httpx
import pytest

from sales_lead_research.cli import run_repl
from sales_lead_research.edgar import CompanyNotFound, search_companies

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _mock_handler(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    if url == "https://www.sec.gov/files/company_tickers.json":
        return httpx.Response(200, content=_fixture("company_tickers.json"))
    return httpx.Response(404, text="Not found")


@pytest.fixture()
def client() -> httpx.Client:
    transport = httpx.MockTransport(_mock_handler)
    return httpx.Client(
        transport=transport,
        headers={"User-Agent": "Sales Lead Research (test@example.com)"},
    )


class TestNonSecFilerMessage:
    def test_unknown_company_raises_with_helpful_message(self, client):
        with pytest.raises(CompanyNotFound, match="not file with the SEC"):
            search_companies("DHL", client)

    def test_message_suggests_legal_parent(self, client):
        with pytest.raises(CompanyNotFound, match="Try the legal parent name"):
            search_companies("DHL", client)

    def test_message_includes_query(self, client):
        with pytest.raises(CompanyNotFound, match="DHL"):
            search_companies("DHL", client)


class TestNonSecFilerCli:
    def test_cli_prints_fallback_message_and_continues(self, client):
        """Searching for a non-SEC filer should print the fallback message
        and return to the prompt (not crash)."""
        out = io.StringIO()
        run_repl(
            iter(["DHL", "exit"]),
            out,
            client=client,
        )
        output = out.getvalue()
        assert "not file with the SEC" in output
        assert "Try the legal parent name" in output

    def test_cli_continues_after_non_sec_filer(self, client):
        """After a non-SEC filer query, the REPL should accept the next query."""
        out = io.StringIO()
        run_repl(
            iter(["DHL", "exit"]),
            out,
            client=client,
        )
        # The fact that run_repl returns normally (processes "exit")
        # proves it didn't crash on the DHL query.
        output = out.getvalue()
        assert "DHL" in output
