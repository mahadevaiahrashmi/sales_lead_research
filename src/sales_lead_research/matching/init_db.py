# agent-notes: { ctx: "Wave 2.3 / issue #17 init-db helper: create customer schema, optional CSV seed", deps: ["csv", "sqlite3"], state: active, last: "sato@2026-04-28" }
"""Create a fresh customer database file with the production schema.

Single public function ``init_db`` — refuses to overwrite an existing
file, optionally loads a seed CSV. The CLI subcommand in ``__main__``
is the user-facing surface; this module just does the work.
"""

from __future__ import annotations

import csv
import io
import sqlite3
from pathlib import Path

# Schema kept in sync with scripts/init_dummy_db.py — copied (not
# imported) so src/ does not depend on scripts/, which is dev-only.
_SCHEMA = """
CREATE TABLE customers (
    account_id          TEXT PRIMARY KEY,
    company_name        TEXT NOT NULL,
    parent_id           TEXT,
    ultimate_parent_id  TEXT,
    location            TEXT,
    country             TEXT,
    tax_number          TEXT,
    zip_code            TEXT
);
CREATE INDEX idx_customers_company_name ON customers(company_name);
"""

_COLUMNS: tuple[str, ...] = (
    "account_id", "company_name", "parent_id", "ultimate_parent_id",
    "location", "country", "tax_number", "zip_code",
)


def init_db(db_path: Path | str, seed_csv: Path | str | None = None) -> None:
    """Create a customer database at ``db_path``; optionally seed from a CSV."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        raise FileExistsError(
            f"Customer database already exists at {db_path} — refusing to "
            "overwrite. Delete the file first if you want to recreate it."
        )

    rows = _load_seed_rows(seed_csv) if seed_csv is not None else []

    with sqlite3.connect(db_path) as connection:
        connection.executescript(_SCHEMA)
        if rows:
            connection.executemany(
                "INSERT INTO customers (" + ", ".join(_COLUMNS) + ") "
                "VALUES (" + ", ".join(["?"] * len(_COLUMNS)) + ")",
                rows,
            )
        connection.commit()


def _load_seed_rows(seed_csv: Path | str) -> list[tuple[str | None, ...]]:
    with Path(seed_csv).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != _COLUMNS:
            raise ValueError(
                "Seed CSV must have these columns in this order: "
                + ", ".join(_COLUMNS)
            )
        return [tuple((row[col] or None) for col in _COLUMNS) for row in reader]


def rebuild_from_csv_text(db_path: Path | str, csv_text: str) -> int:
    """(Re)create the customer database from CSV text; return the row count.

    Requires at least ``account_id`` and ``company_name`` columns; any other
    schema columns are optional (missing ones are stored as NULL), and extra
    columns are ignored. Overwrites any existing database at *db_path*. This is
    the entry point the web upload uses to let a user supply their own list.
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    fields = set(reader.fieldnames or ())
    if "account_id" not in fields or "company_name" not in fields:
        raise ValueError(
            "CSV must include at least 'account_id' and 'company_name' columns."
        )
    rows = [tuple((row.get(col) or None) for col in _COLUMNS) for row in reader]

    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    with sqlite3.connect(db_path) as connection:
        connection.executescript(_SCHEMA)
        if rows:
            connection.executemany(
                "INSERT INTO customers (" + ", ".join(_COLUMNS) + ") "
                "VALUES (" + ", ".join(["?"] * len(_COLUMNS)) + ")",
                rows,
            )
        connection.commit()
    return len(rows)
