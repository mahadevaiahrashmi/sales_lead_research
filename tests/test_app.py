# agent-notes: { ctx: "Gap 3: Gradio app handler tests — recursive tree + Level/Account columns", deps: ["app.py", "tests/fixtures/edgar/"], state: active, last: "tara@2026-05-29" }
"""Tests for the Gradio web handlers in ``app.py``.

``app.lookup`` builds its own httpx client via ``build_client``, so we
monkeypatch that to return an httpx ``MockTransport`` client serving the
recursive PARENT -> CHILD -> GRANDCHILD fixtures. These run fully offline.

The customer store is forced absent (no ``SALES_DB_PATH`` and an empty
working directory) so the Account ID column is present-but-empty and the
tests stay hermetic regardless of any local ``data/customers.sqlite``.
"""

from __future__ import annotations

import csv
from pathlib import Path

import httpx
import pytest

import app as webapp

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _recursive_handler(request: httpx.Request) -> httpx.Response:
    """Serve PARENT CORP -> CHILD INC -> GRANDCHILD CORP (+ LEAF LLC)."""
    url = str(request.url)
    if url == "https://www.sec.gov/files/company_tickers.json":
        return httpx.Response(200, content=_fixture("company_tickers.json"))
    if url == "https://data.sec.gov/submissions/CIK0009999999.json":
        return httpx.Response(200, content=_fixture("CIK0009999999.json"))
    if "000999999924000001/0009999999-24-000001-index.htm" in url:
        return httpx.Response(200, content=_fixture("parent_10k_filing_index.html"))
    if "parent-20240101ex211.htm" in url:
        return httpx.Response(200, content=_fixture("parent_exhibit_21.html"))
    if url == "https://data.sec.gov/submissions/CIK0008888888.json":
        return httpx.Response(200, content=_fixture("CIK0008888888.json"))
    if "000888888824000001/0008888888-24-000001-index.htm" in url:
        return httpx.Response(200, content=_fixture("child_10k_filing_index.html"))
    if "child-20240101ex211.htm" in url:
        return httpx.Response(200, content=_fixture("child_exhibit_21.html"))
    return httpx.Response(404, text=f"no fixture: {url}")


@pytest.fixture()
def mock_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Point ``app.build_client`` at the recursive fixtures and force the
    customer store absent so the Account ID column is blank-but-present."""

    def _build(_user_agent: str) -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(_recursive_handler),
            headers={"User-Agent": "test"},
        )

    monkeypatch.setattr(webapp, "build_client", _build)
    monkeypatch.delenv("SALES_DB_PATH", raising=False)
    monkeypatch.chdir(tmp_path)


class TestRecursiveLookup:
    """Gap 3: the web UI must show the full recursive tree (not one level)
    and use the same four columns as the CLI."""

    def test_includes_nested_grandchild(self, mock_app):
        _info, _url, table, _csv = webapp.lookup("PARENT CORP", "0009999999")
        names = [row[0] for row in table]
        assert "CHILD INC" in names
        # GRANDCHILD only appears if the recursive walk happened.
        assert "GRANDCHILD CORP" in names

    def test_rows_have_four_columns_with_level(self, mock_app):
        _info, _url, table, _csv = webapp.lookup("PARENT CORP", "0009999999")
        assert table and all(len(row) == 4 for row in table)
        levels = {row[2] for row in table}
        assert 1 in levels and 2 in levels  # nested depth is represented

    def test_csv_headers_match_cli(self, mock_app):
        _info, _url, _table, csv_path = webapp.lookup("PARENT CORP", "0009999999")
        assert csv_path is not None
        with open(csv_path) as f:
            headers = next(csv.reader(f))
        assert headers == ["Subsidiary Name", "Jurisdiction", "Level", "Account ID"]

    def test_account_column_present_but_empty_without_store(self, mock_app):
        _info, _url, table, _csv = webapp.lookup("PARENT CORP", "0009999999")
        assert all(row[3] == "" for row in table)

    def test_info_shows_filing_freshness(self, mock_app):
        info, _url, _table, _csv = webapp.lookup("PARENT CORP", "0009999999")
        assert "10-K filed 2024-03-15" in info
