# agent-notes: { ctx: "Wave 2.2 / issue #16 red-phase tests for matching/store.py (open_store, lookup_by_name, lookup_with_confidence, Matches)", deps: ["src/sales_lead_research/matching/store.py", "src/sales_lead_research/matching/names.py", "docs/adrs/0003-sales-assistant-chat-architecture.md", "docs/plans/sales-assistant-chat-v1-plan.md"], state: active, last: "tara@2026-04-28" }
"""Red-phase tests for ``sales_lead_research.matching.store``.

Scope: the read-only customer-store wrapper specified in ADR-0003 §3
and Wave 2.2 of the sales-assistant-chat-v1 plan. The module under
test does not yet exist; until Sato writes it, every case here is
expected to error at import time
(``ModuleNotFoundError: No module named 'sales_lead_research.matching.store'``).
That is the correct red-phase signal.

Public API the tests pin down:

- ``Matches`` — frozen dataclass with ``exact`` and ``close`` tuples.
- ``open_store(path=None)`` — returns an opaque store handle, or
  ``None`` when the database file is missing. Reads ``SALES_DB_PATH``
  from the environment when ``path`` is ``None``. Opens the
  underlying connection in **read-only URI mode** so writes raise
  ``sqlite3.OperationalError`` — this is the security gate.
- ``lookup_by_name(store, normalised_name)`` — exact equality on the
  *already-normalised* input vs. the normalised form of each row's
  ``company_name``. Returns the matching ``account_id`` strings as a
  list (order is whatever the database yields).
- ``lookup_with_confidence(store, subsidiary_name)`` — takes a *raw*
  subsidiary name and routes each row to ``exact`` or ``close``
  buckets per ``classify_match``. A row is never in both buckets.

Fixture strategy: tests build a tiny SQLite database under
``tmp_path_factory`` once per session, mirroring the schema in
``scripts/init_dummy_db.py``. Tests do **not** depend on
``data/customers.sqlite`` — that file is gitignored and may not exist
in CI.
"""

from __future__ import annotations

import dataclasses
import sqlite3
from pathlib import Path

import pytest

from sales_lead_research.matching.store import (  # type: ignore[import-not-found]
    Matches,
    lookup_by_name,
    lookup_with_confidence,
    open_store,
)


# ---------------------------------------------------------------------------
# Fixture database — built once per test session.
# ---------------------------------------------------------------------------


# A focused subset of the dummy-DB schema. Account IDs are picked from
# ``scripts/init_dummy_db.py`` so failure messages stay readable when
# someone diffs a real-DB lookup against these tests.
_FIXTURE_ROWS: tuple[tuple[str, str], ...] = (
    ("ACCT-0100", "FedEx Corporation"),
    ("ACCT-0109", "FedEx Express (France) SAS"),
    ("ACCT-0106", "FedEx Trade Networks Transport & Brokerage, Inc."),
    ("ACCT-0111", "FedEx Custom Critical, Inc."),
    ("ACCT-0112", "FedEx Custom Critical Inc"),
    ("ACCT-0203", "DHL Express (Portugal) Lda."),
    ("ACCT-0300", "Apple Inc."),
    ("ACCT-9001", "Acme Corporation"),
)


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


@pytest.fixture(scope="session")
def fixture_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build a tiny read-only-friendly SQLite DB once per session.

    The file is populated and then never modified, so every test can
    open it with ``mode=ro`` without trampling sibling tests.
    """
    db_path = tmp_path_factory.mktemp("store") / "customers.sqlite"
    with sqlite3.connect(db_path) as con:
        con.executescript(_SCHEMA)
        con.executemany(
            "INSERT INTO customers (account_id, company_name) VALUES (?, ?)",
            _FIXTURE_ROWS,
        )
        con.commit()
    return db_path


@pytest.fixture()
def store(fixture_db: Path):
    """Open a fresh store handle per test.

    ``open_store`` is just opening a SQLite connection, so the
    per-test cost is negligible and we get clean isolation if a
    future implementation grows per-handle state.
    """
    handle = open_store(fixture_db)
    assert handle is not None, "fixture DB exists; open_store must return a handle"
    return handle


# ---------------------------------------------------------------------------
# open_store
# ---------------------------------------------------------------------------


class TestOpenStore:
    """``open_store`` returns a handle, ``None`` on missing file, and
    opens the underlying connection in read-only mode."""

    def test_returns_handle_for_explicit_path(self, fixture_db: Path) -> None:
        """Happy path: explicit path to an existing DB returns a non-None handle."""
        handle = open_store(fixture_db)
        assert handle is not None

    def test_accepts_string_path(self, fixture_db: Path) -> None:
        """The path argument accepts ``str`` as well as ``Path`` (per signature)."""
        handle = open_store(str(fixture_db))
        assert handle is not None

    def test_returns_none_when_file_missing(self, tmp_path: Path) -> None:
        """Missing file is a soft failure: ``None``, not an exception.

        The chat layer renders a plain-English banner from this; if
        ``open_store`` raised, the banner wouldn't fire and the user
        would see a traceback.
        """
        ghost = tmp_path / "does-not-exist.sqlite"
        assert not ghost.exists()
        assert open_store(ghost) is None

    def test_reads_path_from_env_var(
        self,
        fixture_db: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When ``path`` is ``None``, ``SALES_DB_PATH`` is consulted."""
        monkeypatch.setenv("SALES_DB_PATH", str(fixture_db))
        handle = open_store()
        assert handle is not None

    def test_env_var_unset_falls_back_to_default_path(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """No env var, no arg → default path (``data/customers.sqlite``
        relative to CWD). When that path doesn't exist, ``open_store``
        returns ``None`` instead of raising.

        We chdir into a guaranteed-empty temp dir so the default path
        is provably missing on any machine, then assert ``None``. This
        gives positive coverage of the default-path branch (no env var,
        no argument) without coupling the test to a developer's local
        ``data/`` directory.
        """
        monkeypatch.delenv("SALES_DB_PATH", raising=False)
        monkeypatch.chdir(tmp_path)
        assert open_store() is None

    def test_uri_mode_ro_refuses_writes(self, fixture_db: Path) -> None:
        """The URI string ``file:<path>?mode=ro`` is the SQL belt
        promised by ADR-0003 §3. Verify SQLite itself refuses writes
        on such a connection — independent of the implementation.
        """
        ro_conn = sqlite3.connect(f"file:{fixture_db}?mode=ro", uri=True)
        try:
            with pytest.raises(sqlite3.OperationalError) as exc_info:
                ro_conn.execute(
                    "INSERT INTO customers (account_id, company_name) "
                    "VALUES ('ACCT-9999', 'Hostile Corp')"
                )
            # SQLite says "attempt to write a readonly database". Be
            # forgiving on the exact phrasing but pin "read" + "only".
            message = str(exc_info.value).lower()
            assert (
                "readonly" in message
                or "read-only" in message
                or "read only" in message
            )
        finally:
            ro_conn.close()

    def test_open_store_returns_readonly_connection(self, store) -> None:
        """The implementation gate: ``open_store`` itself must use
        ``mode=ro``, not just any ``sqlite3.connect(path)`` call.

        If a future implementer switched to a writable connection by
        accident, the previous test (which opens its own ``mode=ro``
        connection) would still pass — that test only verifies the
        URI string is the right form, not that the implementation
        uses it. This test reaches into the handle and asserts a
        write fails on the actual connection ``open_store`` returned.
        """
        with pytest.raises(sqlite3.OperationalError) as exc_info:
            store.connection.execute(
                "INSERT INTO customers (account_id, company_name) "
                "VALUES ('ACCT-9998', 'Sneaky Corp')"
            )
        message = str(exc_info.value).lower()
        assert (
            "readonly" in message
            or "read-only" in message
            or "read only" in message
        )


# ---------------------------------------------------------------------------
# lookup_by_name
# ---------------------------------------------------------------------------


class TestLookupByName:
    """``lookup_by_name`` does literal equality on the *normalised*
    form of the DB row's ``company_name``. The caller is responsible
    for normalising the input first."""

    def test_single_exact_match(self, store) -> None:
        """``"fedex express france"`` is the normalised form of
        ``"FedEx Express (France) SAS"``. Exactly one DB row
        normalises to that string."""
        result = lookup_by_name(store, "fedex express france")
        assert result == ["ACCT-0109"]

    def test_multi_match_returns_all_account_ids(self, store) -> None:
        """Two rows in the fixture (``ACCT-0111`` and ``ACCT-0112``)
        both normalise to ``"fedex custom critical"``. Both account
        IDs must come back. Sorted compare keeps the test
        order-independent (the spec leaves DB row order as
        whatever-the-DB-yields)."""
        result = lookup_by_name(store, "fedex custom critical")
        assert sorted(result) == ["ACCT-0111", "ACCT-0112"]

    def test_no_match_returns_empty_list(self, store) -> None:
        result = lookup_by_name(store, "nonexistent company")
        assert result == []

    def test_empty_input_returns_empty_list(self, store) -> None:
        """Empty input must NOT match every-or-any row. The function
        returns ``[]`` for ``""`` — a deliberate shortcut so the
        chat layer can pass through ``normalise_name(raw)`` without
        a separate empty check."""
        result = lookup_by_name(store, "")
        assert result == []

    def test_already_normalised_apple(self, store) -> None:
        """``"apple"`` is the normalised form of ``"Apple Inc."`` —
        the DB row's normalised company_name equals the input."""
        result = lookup_by_name(store, "apple")
        assert result == ["ACCT-0300"]

    def test_does_not_renormalise_input(self, store) -> None:
        """The function expects an already-normalised input. Passing
        a raw name like ``"Apple Inc."`` must NOT match — the DB row
        normalises to ``"apple"`` but the function only re-normalises
        the row, not the argument. Callers who want auto-normalisation
        use ``lookup_with_confidence``."""
        result = lookup_by_name(store, "Apple Inc.")
        assert result == []


# ---------------------------------------------------------------------------
# lookup_with_confidence
# ---------------------------------------------------------------------------


class TestLookupWithConfidence:
    """``lookup_with_confidence`` takes a *raw* subsidiary name and
    routes each DB row through ``classify_match``. ``"exact"`` rows
    go in ``Matches.exact``; ``"close"`` rows go in ``Matches.close``;
    ``"none"`` rows are dropped. A row is never in both tuples."""

    def test_exact_single_match(self, store) -> None:
        """The raw FedEx France subsidiary name matches one DB row
        exactly (after both sides normalise to ``"fedex express france"``)
        and no row close-matches it."""
        result = lookup_with_confidence(store, "FedEx Express (France) SAS")
        assert result == Matches(exact=("ACCT-0109",), close=())

    def test_exact_multi_match(self, store) -> None:
        """Two DB rows normalise to ``"fedex custom critical"``;
        both must come back as exact matches. Sorting the tuple keeps
        the test order-insensitive (spec leaves row order open)."""
        result = lookup_with_confidence(store, "FedEx Custom Critical Inc")
        assert sorted(result.exact) == ["ACCT-0111", "ACCT-0112"]
        assert result.close == ()

    def test_close_match_at_jaccard_six_sevenths(self, store) -> None:
        """Close-match arithmetic, verified manually:

        DB row "FedEx Trade Networks Transport & Brokerage, Inc."
            normalises to tokens
            {fedex, trade, networks, transport, &, brokerage}      (6 tokens)

        Subsidiary input "FedEx Trade Networks Transport & Brokerage
        International, Inc." normalises to tokens
            {fedex, trade, networks, transport, &, brokerage,
             international}                                        (7 tokens)

        |intersection| = 6, |union| = 7 -> Jaccard = 6/7 ~= 0.857.
        0.857 >= 0.8 threshold and the normalised forms are NOT
        equal, so ``classify_match`` returns ``"close"`` for ACCT-0106
        and ``"none"`` for every other row in the fixture (verified
        via a manual probe before this test was written).
        """
        result = lookup_with_confidence(
            store,
            "FedEx Trade Networks Transport & Brokerage International, Inc.",
        )
        assert result.exact == ()
        assert result.close == ("ACCT-0106",)

    def test_no_match_returns_empty_matches(self, store) -> None:
        result = lookup_with_confidence(store, "Random Nonexistent Corp")
        assert result == Matches(exact=(), close=())

    def test_empty_input_returns_empty_matches(self, store) -> None:
        """Per spec, empty input short-circuits to ``Matches((), ())``.
        This protects against a future implementation that would
        otherwise compare every row's normalised form against ``""``
        and accidentally match degenerate rows."""
        result = lookup_with_confidence(store, "")
        assert result == Matches(exact=(), close=())

    def test_suffix_only_input_returns_empty_matches(self, store) -> None:
        """``"Inc."`` normalises to the empty string (suffix-only is
        degenerate by W2.1 spec). The ``classify_match`` rule then
        emits ``"none"`` for every row, so both buckets are empty."""
        result = lookup_with_confidence(store, "Inc.")
        assert result == Matches(exact=(), close=())

    def test_exact_and_close_are_mutually_exclusive(self, store) -> None:
        """A row that exact-matches must NOT also appear in ``close``.
        ``classify_match`` returns one verdict per pair; a future
        implementation that double-counted (e.g. by running an exact
        check and a close check independently) would be caught here."""
        result = lookup_with_confidence(store, "FedEx Express (France) SAS")
        assert set(result.exact).isdisjoint(set(result.close))

    def test_handle_is_reusable_across_calls(self, store) -> None:
        """The Wave 3 chat session opens one store handle and calls
        ``lookup_with_confidence`` once per subsidiary in a loop.
        Each call must be independent — no per-call state pollution,
        no cursor exhaustion. Two sequential calls must each return
        the correct buckets for their input."""
        first = lookup_with_confidence(store, "FedEx Express (France) SAS")
        second = lookup_with_confidence(store, "Apple Inc.")
        third = lookup_with_confidence(store, "FedEx Express (France) SAS")
        assert first == Matches(exact=("ACCT-0109",), close=())
        assert second == Matches(exact=("ACCT-0300",), close=())
        assert third == first


# ---------------------------------------------------------------------------
# Matches dataclass
# ---------------------------------------------------------------------------


class TestMatches:
    """``Matches`` is the value-object the chat layer consumes. Pin
    down its observable shape: two named fields, both tuples, frozen."""

    def test_construction_with_keyword_args(self) -> None:
        """Construction by keyword is the form used in tests and in
        the chat layer; it must work."""
        m = Matches(exact=("ACCT-0001",), close=("ACCT-0002", "ACCT-0003"))
        assert m.exact == ("ACCT-0001",)
        assert m.close == ("ACCT-0002", "ACCT-0003")

    def test_default_or_empty_construction(self) -> None:
        """Empty buckets are the no-match shape used throughout."""
        m = Matches(exact=(), close=())
        assert m.exact == ()
        assert m.close == ()

    def test_equality_by_value(self) -> None:
        """Frozen dataclasses compare structurally, which lets us
        write ``assert result == Matches((...,), ())`` instead of
        deep-asserting field by field."""
        a = Matches(exact=("ACCT-0001",), close=())
        b = Matches(exact=("ACCT-0001",), close=())
        assert a == b

    def test_is_frozen(self) -> None:
        """``frozen=True`` is required so the value-object is hashable
        and not mutated by the chat layer once returned. Frozen
        dataclasses raise ``dataclasses.FrozenInstanceError`` on
        attribute assignment."""
        m = Matches(exact=("ACCT-0001",), close=())
        with pytest.raises(dataclasses.FrozenInstanceError):
            m.exact = ("ACCT-9999",)  # type: ignore[misc]
