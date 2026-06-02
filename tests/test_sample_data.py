# agent-notes: { ctx: "guard: the committed sample customer CSV stays valid + loadable", deps: ["src/sales_lead_research/static/sample-customers.csv", "src/sales_lead_research/matching/init_db.py"], state: active, last: "tara@2026-05-31" }
"""The downloadable sample customer list must stay valid and loadable.

Users download ``static/sample-customers.csv`` to test the upload flow (and to
model their own CRM export on it), so it must round-trip through the same
loader the upload endpoint uses.
"""

from __future__ import annotations

from pathlib import Path

from sales_lead_research.matching.init_db import rebuild_from_csv_text

SAMPLE = (
    Path(__file__).parent.parent
    / "src"
    / "sales_lead_research"
    / "static"
    / "sample-customers.csv"
)


def test_sample_csv_exists() -> None:
    assert SAMPLE.is_file()


def test_sample_csv_has_required_columns() -> None:
    header = SAMPLE.read_text(encoding="utf-8").splitlines()[0]
    assert "account_id" in header and "company_name" in header


def test_sample_csv_loads(tmp_path: Path) -> None:
    rows = rebuild_from_csv_text(tmp_path / "c.sqlite", SAMPLE.read_text(encoding="utf-8"))
    assert rows >= 40  # ~47 fictional companies
