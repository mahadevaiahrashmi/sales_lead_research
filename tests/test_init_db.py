# agent-notes: { ctx: "Wave 2.3 / issue #17 smoke tests for matching/init_db.py (schema, refusal-to-overwrite, CSV seed, store integration)", deps: ["src/sales_lead_research/matching/init_db.py", "src/sales_lead_research/matching/store.py"], state: active, last: "sato@2026-04-28" }
"""Smoke tests for ``sales_lead_research.matching.init_db``.

Wave 2.3 is small enough that the plan calls for one combined pass
(implementation + tests) rather than the usual red/green split. Each
test pins down one promise of the contract.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from sales_lead_research.__main__ import main
from sales_lead_research.matching.init_db import init_db
from sales_lead_research.matching.store import lookup_by_name, open_store


_SEED_CSV = """\
account_id,company_name,parent_id,ultimate_parent_id,location,country,tax_number,zip_code
ACCT-0001,Acme Corp,,ACCT-0001,Phoenix,United States,US-86-1234567,85001
ACCT-0002,Acme Subsidiary Ltd,ACCT-0001,ACCT-0001,Tokyo,Japan,,100-0001
"""


def test_init_db_creates_customers_table(tmp_path: Path) -> None:
    db_path = tmp_path / "customers.sqlite"

    init_db(db_path)

    assert db_path.exists()
    with sqlite3.connect(db_path) as con:
        tables = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    assert ("customers",) in tables


def test_init_db_schema_columns_match_production(tmp_path: Path) -> None:
    db_path = tmp_path / "customers.sqlite"

    init_db(db_path)

    with sqlite3.connect(db_path) as con:
        info = con.execute("PRAGMA table_info(customers)").fetchall()
    column_names = [row[1] for row in info]
    assert column_names == [
        "account_id",
        "company_name",
        "parent_id",
        "ultimate_parent_id",
        "location",
        "country",
        "tax_number",
        "zip_code",
    ]


def test_init_db_refuses_to_overwrite_existing_file(tmp_path: Path) -> None:
    db_path = tmp_path / "customers.sqlite"
    init_db(db_path)

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        init_db(db_path)


def test_init_db_loads_seed_csv(tmp_path: Path) -> None:
    db_path = tmp_path / "customers.sqlite"
    csv_path = tmp_path / "seed.csv"
    csv_path.write_text(_SEED_CSV, encoding="utf-8")

    init_db(db_path, seed_csv=csv_path)

    with sqlite3.connect(db_path) as con:
        rows = con.execute(
            "SELECT account_id, company_name FROM customers ORDER BY account_id"
        ).fetchall()
        empty_tax = con.execute(
            "SELECT tax_number FROM customers WHERE account_id = 'ACCT-0002'"
        ).fetchone()[0]

    assert rows == [
        ("ACCT-0001", "Acme Corp"),
        ("ACCT-0002", "Acme Subsidiary Ltd"),
    ]
    assert empty_tax is None


def test_init_db_rejects_seed_csv_with_wrong_header(tmp_path: Path) -> None:
    db_path = tmp_path / "customers.sqlite"
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text(
        "account_id,company_name\nACCT-0001,Acme Corp\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="Seed CSV must have these columns"):
        init_db(db_path, seed_csv=bad_csv)


def test_init_db_output_is_readable_by_store(tmp_path: Path) -> None:
    db_path = tmp_path / "customers.sqlite"
    csv_path = tmp_path / "seed.csv"
    csv_path.write_text(_SEED_CSV, encoding="utf-8")

    init_db(db_path, seed_csv=csv_path)

    store = open_store(db_path)
    assert store is not None
    # ``lookup_by_name`` takes the *already-normalised* form per the store
    # contract; ``normalise_name("Acme Corp")`` strips the "Corp" suffix.
    assert lookup_by_name(store, "acme") == ["ACCT-0001"]


def test_cli_init_db_creates_file_and_exits_zero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI dispatch smoke: ``sales-lead-research init-db`` reads
    ``SALES_DB_PATH`` from the env, calls ``init_db``, prints a
    plain-English success line, and exits 0."""
    db_path = tmp_path / "customers.sqlite"
    monkeypatch.setenv("SALES_DB_PATH", str(db_path))

    exit_code = main(["init-db"])

    assert exit_code == 0
    assert db_path.exists()
    out = capsys.readouterr().out
    assert "Created empty customer database" in out
    assert str(db_path) in out


def test_cli_init_db_exits_two_on_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A second run against the same path surfaces the refusal-to-
    overwrite message on stderr and exits with code 2 (distinguishable
    from generic failure for shell scripting)."""
    db_path = tmp_path / "customers.sqlite"
    monkeypatch.setenv("SALES_DB_PATH", str(db_path))
    assert main(["init-db"]) == 0
    capsys.readouterr()  # discard the success message

    exit_code = main(["init-db"])

    assert exit_code == 2
    err = capsys.readouterr().err
    assert "refusing to overwrite" in err
