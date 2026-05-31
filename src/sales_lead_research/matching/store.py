# agent-notes: { ctx: "Gap 5: read-only customer store with in-memory token index for blocking (open_store, candidate_account_ids, lookup_by_name, lookup_with_confidence) per ADR-0003 §3-4", deps: ["src/sales_lead_research/matching/names.py"], state: active, last: "sato@2026-05-29" }
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
from dataclasses import dataclass, field
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
    """Opaque handle: a read-only connection plus an in-memory token index.

    The token index is built once, when the store is opened. It maps each
    normalised name token to the account ids whose company name contains
    it, which lets ``lookup_with_confidence`` score only *candidate* rows
    (those sharing a token) instead of scanning the whole customer table on
    every lookup. The index fields are excluded from equality and repr —
    the connection identifies the store.
    """

    connection: sqlite3.Connection
    name_by_account: dict[str, str] = field(
        default_factory=dict, compare=False, repr=False
    )
    accounts_by_token: dict[str, tuple[str, ...]] = field(
        default_factory=dict, compare=False, repr=False
    )


def _build_token_index(
    connection: sqlite3.Connection,
) -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    """Read every customer row once and build the in-memory token index.

    Returns ``(name_by_account, accounts_by_token)``; the second maps each
    normalised token to the account ids whose company name contains it.
    Rows are read in ``account_id`` order so candidate lists — and thus
    lookup results — are deterministic.
    """
    name_by_account: dict[str, str] = {}
    token_lists: dict[str, list[str]] = {}
    cursor = connection.execute(
        "SELECT account_id, company_name FROM customers ORDER BY account_id"
    )
    for row in cursor:
        account_id = row["account_id"]
        company_name = row["company_name"]
        name_by_account[account_id] = company_name
        for token in set(normalise_name(company_name).split()):
            token_lists.setdefault(token, []).append(account_id)
    accounts_by_token = {tok: tuple(ids) for tok, ids in token_lists.items()}
    return name_by_account, accounts_by_token


def open_store(path: Path | str | None = None) -> CustomerStore | None:
    """Open the customer DB in read-only mode; ``None`` if the file is missing.

    Builds the in-memory token index once, up front, so subsequent lookups
    are bounded by the candidate set rather than the size of the table.
    """
    if path is None:
        env_path = os.environ.get("SALES_DB_PATH")
        path = env_path if env_path is not None else _DEFAULT_DB_PATH
    db_path = Path(path)
    if not db_path.exists():
        return None
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    name_by_account, accounts_by_token = _build_token_index(connection)
    return CustomerStore(
        connection=connection,
        name_by_account=name_by_account,
        accounts_by_token=accounts_by_token,
    )


def candidate_account_ids(
    store: CustomerStore, subsidiary_name: str
) -> tuple[str, ...]:
    """Return the account ids worth scoring for *subsidiary_name*.

    This is the **blocking** step. A row can only exact- or close-match if
    it shares at least one normalised token with the input, so the union of
    the input's token buckets is a complete superset of the real matches —
    and far smaller than the whole table. Returned sorted for deterministic
    output (mirroring ``ORDER BY account_id``).
    """
    tokens = set(normalise_name(subsidiary_name).split())
    if not tokens:
        return ()
    ids: set[str] = set()
    for token in tokens:
        ids.update(store.accounts_by_token.get(token, ()))
    return tuple(sorted(ids))


def lookup_by_name(store: CustomerStore, normalised_name: str) -> list[str]:
    """Return account ids whose normalised company_name equals the input.

    Scores only the candidate rows from the token index, then keeps those
    that match exactly. The input is expected to be already normalised —
    callers wanting auto-normalisation use ``lookup_with_confidence``.
    """
    if not normalised_name:
        return []
    return [
        account_id
        for account_id in candidate_account_ids(store, normalised_name)
        if normalise_name(store.name_by_account[account_id]) == normalised_name
    ]


def lookup_with_confidence(store: CustomerStore, subsidiary_name: str) -> Matches:
    """Bucket candidate account ids into ``exact`` or ``close`` per
    ``classify_match``.

    Only the candidates from the token index are scored (blocking), so the
    cost is proportional to the candidate set, not the whole table. The
    result is identical to scoring every row, because a row that shares no
    token with the input can be neither an exact nor a close match.
    """
    if not subsidiary_name:
        return Matches(exact=(), close=())
    if not normalise_name(subsidiary_name):
        return Matches(exact=(), close=())
    exact: list[str] = []
    close: list[str] = []
    for account_id in candidate_account_ids(store, subsidiary_name):
        verdict = classify_match(subsidiary_name, store.name_by_account[account_id])
        if verdict == "exact":
            exact.append(account_id)
        elif verdict == "close":
            close.append(account_id)
    return Matches(exact=tuple(exact), close=tuple(close))
