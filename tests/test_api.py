# agent-notes: { ctx: "tests for the FastAPI REST API (health, search, lookup, web-lookup)", deps: ["src/sales_lead_research/api.py", "tests/fixtures/edgar/"], state: active, last: "tara@2026-05-31" }
"""Tests for the FastAPI REST API.

The endpoints build their own httpx client via ``build_client``, so we
monkeypatch ``sales_lead_research.api.build_client`` to serve the recursive
PARENT -> CHILD -> GRANDCHILD fixtures offline. Customer matching is
exercised by pointing ``SALES_DB_PATH`` at a tiny seeded database.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

import sales_lead_research.api as api

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"

_STORE_SCHEMA = """
CREATE TABLE customers (
    account_id TEXT PRIMARY KEY, company_name TEXT NOT NULL,
    parent_id TEXT, ultimate_parent_id TEXT, location TEXT,
    country TEXT, tax_number TEXT, zip_code TEXT
);
"""


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _recursive_handler(request: httpx.Request) -> httpx.Response:
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


def _mock_build(_user_agent: str) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(_recursive_handler),
        headers={"User-Agent": "test"},
    )


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    """API client wired to the EDGAR fixtures, with no customer DB present."""
    monkeypatch.setattr(api, "build_client", _mock_build)
    monkeypatch.delenv("SALES_DB_PATH", raising=False)
    monkeypatch.chdir(tmp_path)  # default DB path is missing -> empty matching
    return TestClient(api.app)


def _names(tree: dict) -> list[str]:
    out = [tree["name"]]
    for child in tree["children"]:
        out.extend(_names(child))
    return out


class TestHealth:
    def test_health_ok(self, client: TestClient) -> None:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json() == {"status": "ok"}


class TestSearch:
    def test_returns_matches(self, client: TestClient) -> None:
        r = client.get("/api/search", params={"q": "PARENT"})
        assert r.status_code == 200
        names = [m["name"] for m in r.json()["matches"]]
        assert any("PARENT" in n.upper() for n in names)

    def test_no_match_is_empty_with_message(self, client: TestClient) -> None:
        r = client.get("/api/search", params={"q": "zzz_nonexistent_zzz"})
        assert r.status_code == 200
        body = r.json()
        assert body["matches"] == []
        assert "web-lookup" in body["message"]


class TestLookup:
    def test_recursive_tree_includes_grandchild(self, client: TestClient) -> None:
        r = client.get(
            "/api/lookup", params={"company": "PARENT CORP", "cik": "0009999999"}
        )
        assert r.status_code == 200
        names = _names(r.json()["tree"])
        assert "CHILD INC" in names
        assert "GRANDCHILD CORP" in names  # only present if recursion worked

    def test_flat_has_levels_and_freshness(self, client: TestClient) -> None:
        d = client.get(
            "/api/lookup", params={"company": "PARENT CORP", "cik": "0009999999"}
        ).json()
        levels = {row["level"] for row in d["flat"]}
        assert 1 in levels and 2 in levels
        assert d["form"] == "10-K"
        assert d["filing_date"] == "2024-03-15"

    def test_no_store_means_no_customers_matched(self, client: TestClient) -> None:
        d = client.get(
            "/api/lookup", params={"company": "PARENT CORP", "cik": "0009999999"}
        ).json()
        assert d["customers_matched"] == 0
        assert all(not row["account_ids"] for row in d["flat"])


class TestLookupWithCustomerMatch:
    def test_existing_customer_flagged(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        db = tmp_path / "customers.sqlite"
        with sqlite3.connect(db) as con:
            con.executescript(_STORE_SCHEMA)
            con.execute(
                "INSERT INTO customers (account_id, company_name) VALUES (?, ?)",
                ("ACCT-CHILD", "CHILD INC"),
            )
            con.commit()
        monkeypatch.setattr(api, "build_client", _mock_build)
        monkeypatch.setenv("SALES_DB_PATH", str(db))
        c = TestClient(api.app)

        d = c.get(
            "/api/lookup", params={"company": "PARENT CORP", "cik": "0009999999"}
        ).json()
        assert d["customers_matched"] == 1
        child = next(r for r in d["flat"] if r["name"] == "CHILD INC")
        assert child["account_ids"] == ["ACCT-CHILD"]


class TestWebLookup:
    def test_web_fallback_subsidiaries(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            api,
            "web_search_subsidiaries",
            lambda name, client: {
                "parent": "DHL",
                "source": "http://example.test/report.pdf",
                "subsidiaries": [
                    ("DHL Express (Portugal) Lda.", "Portugal"),
                    ("DHL Parcel UK Ltd", "United Kingdom"),
                ],
            },
        )
        monkeypatch.setattr(api, "build_client", lambda ua: httpx.Client())
        monkeypatch.delenv("SALES_DB_PATH", raising=False)
        monkeypatch.chdir(tmp_path)
        c = TestClient(api.app)

        d = c.get("/api/web-lookup", params={"company": "DHL"}).json()
        assert d["parent"] == "DHL"
        assert d["subsidiaries_total"] == 2

    def test_web_fallback_not_found_is_404(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(api, "web_search_subsidiaries", lambda name, client: {})
        monkeypatch.setattr(api, "build_client", lambda ua: httpx.Client())
        monkeypatch.chdir(tmp_path)
        c = TestClient(api.app)
        assert c.get("/api/web-lookup", params={"company": "Nope"}).status_code == 404


class TestCustomers:
    """The CRM-data endpoints: report status and load a customer list from an
    uploaded CSV (this is how a user provides their customer data)."""

    def test_status_empty_when_no_db(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("SALES_DB_PATH", str(tmp_path / "missing.sqlite"))
        c = TestClient(api.app)
        assert c.get("/api/customers").json() == {"loaded": False, "rows": 0}

    def test_upload_loads_list_and_drives_matching(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("SALES_DB_PATH", str(tmp_path / "c.sqlite"))
        monkeypatch.setattr(api, "build_client", _mock_build)
        c = TestClient(api.app)

        csv_text = "account_id,company_name\nACCT-CHILD,CHILD INC\nACCT-X,Other Co\n"
        r = c.post("/api/customers", content=csv_text, headers={"Content-Type": "text/csv"})
        assert r.status_code == 200 and r.json() == {"loaded": True, "rows": 2}
        assert c.get("/api/customers").json() == {"loaded": True, "rows": 2}

        # The freshly uploaded list now drives the matcher.
        d = c.get(
            "/api/lookup", params={"company": "PARENT CORP", "cik": "0009999999"}
        ).json()
        assert d["customers_matched"] == 1
        child = next(row for row in d["flat"] if row["name"] == "CHILD INC")
        assert child["account_ids"] == ["ACCT-CHILD"]

    def test_upload_rejects_missing_required_columns(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("SALES_DB_PATH", str(tmp_path / "c.sqlite"))
        c = TestClient(api.app)
        r = c.post(
            "/api/customers", content="name,foo\nA,B\n", headers={"Content-Type": "text/csv"}
        )
        assert r.status_code == 400
