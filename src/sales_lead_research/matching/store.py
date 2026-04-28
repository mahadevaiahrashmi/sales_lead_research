# agent-notes: { ctx: "Wave 2.2 / issue #16 read-only customer-store wrapper (open_store, lookup_by_name, lookup_with_confidence) per ADR-0003 §3-4", deps: ["src/sales_lead_research/matching/names.py"], state: active, last: "sato@2026-04-28" }
"""Read-only wrapper around the customer SQLite database.

Three public functions, plus the ``Matches`` value-object:

- ``open_store`` — open the customer DB in read-only URI mode and
  return an opaque handle (or ``None`` if the file is missing).
- ``lookup_by_name`` — exact equality on already-normalised inputs.
- ``lookup_with_confidence`` — raw-name lookup that buckets each row
  into ``exact`` or ``close`` per ``classify_match``.

The connection is opened with ``mode=ro`` so writes raise at the SQL
level (per ADR-0003 §3 — defence in depth). No write helpers are
exposed from this module.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from sales_lead_research.matching.names import classify_match, normalise_name


_DEFAULT_DB_PATH = Path("data/customers.sqlite")


@dataclass(frozen=True)
class Matches:
    """Account-id buckets for a confidence-classified lookup."""

    exact: tuple[str, ...]
    close: tuple[str, ...]


@dataclass(frozen=True)
class CustomerStore:
    """Opaque handle wrapping a read-only SQLite connection."""

    connection: sqlite3.Connection


def open_store(path: Path | str | None = None) -> CustomerStore | None:
    """Open the customer DB in read-only mode; ``None`` if the file is missing."""
    if path is None:
        env_path = os.environ.get("SALES_DB_PATH")
        path = env_path if env_path is not None else _DEFAULT_DB_PATH
    db_path = Path(path)
    if not db_path.exists():
        return None
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return CustomerStore(connection=connection)


def lookup_by_name(store: CustomerStore, normalised_name: str) -> list[str]:
    """Return account ids whose normalised company_name equals the input."""
    if not normalised_name:
        return []
    cursor = store.connection.execute(
        "SELECT account_id, company_name FROM customers ORDER BY account_id"
    )
    return [
        row["account_id"]
        for row in cursor
        if normalise_name(row["company_name"]) == normalised_name
    ]


def lookup_with_confidence(store: CustomerStore, subsidiary_name: str) -> Matches:
    """Bucket each row's account id into ``exact`` or ``close`` per ``classify_match``."""
    if not subsidiary_name:
        return Matches(exact=(), close=())
    if not normalise_name(subsidiary_name):
        return Matches(exact=(), close=())
    cursor = store.connection.execute(
        "SELECT account_id, company_name FROM customers ORDER BY account_id"
    )
    exact: list[str] = []
    close: list[str] = []
    for row in cursor:
        verdict = classify_match(subsidiary_name, row["company_name"])
        if verdict == "exact":
            exact.append(row["account_id"])
        elif verdict == "close":
            close.append(row["account_id"])
    return Matches(exact=tuple(exact), close=tuple(close))
