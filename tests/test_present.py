# agent-notes: { ctx: "Gap 1: tests for matching/present.py display helpers (pure)", deps: ["src/sales_lead_research/matching/present.py", "src/sales_lead_research/matching/store.py"], state: active, last: "tara@2026-05-29" }
"""Tests for ``sales_lead_research.matching.present``.

These pin the plain-text and tree-suffix rendering of a ``Matches``
value-object, per product-context decisions 1 and 2:

- exact matches render as the account id(s), comma-separated;
- close-only matches render with a "possibly ... — verify" marker;
- no match renders as an empty cell (CSV) / an em-dash (tree).

All functions are pure (no I/O), so the tests are plain value asserts.
"""

from __future__ import annotations

from sales_lead_research.matching.present import (
    account_cell,
    is_existing_customer,
    tree_account_suffix,
)
from sales_lead_research.matching.store import Matches


class TestAccountCell:
    """``account_cell`` is the plain-text value for the CSV / table cell."""

    def test_exact_single(self) -> None:
        assert account_cell(Matches(exact=("ACCT-0100",), close=())) == "ACCT-0100"

    def test_exact_multiple_comma_separated(self) -> None:
        # Decision 2: multiple matches are comma-separated in one cell.
        assert (
            account_cell(Matches(exact=("ACCT-0111", "ACCT-0112"), close=()))
            == "ACCT-0111, ACCT-0112"
        )

    def test_close_only_gets_verify_marker(self) -> None:
        # Decision 1: close matches show a "possibly ... — verify" marker.
        assert (
            account_cell(Matches(exact=(), close=("ACCT-0110",)))
            == "possibly ACCT-0110 — verify"
        )

    def test_close_multiple_comma_separated(self) -> None:
        assert (
            account_cell(Matches(exact=(), close=("ACCT-0110", "ACCT-0199")))
            == "possibly ACCT-0110, ACCT-0199 — verify"
        )

    def test_no_match_is_empty_string(self) -> None:
        assert account_cell(Matches(exact=(), close=())) == ""

    def test_exact_takes_precedence_over_close(self) -> None:
        # A confirmed account beats a "possible" one — show the confirmed id.
        assert (
            account_cell(Matches(exact=("ACCT-0100",), close=("ACCT-9999",)))
            == "ACCT-0100"
        )


class TestTreeAccountSuffix:
    """``tree_account_suffix`` is the bracketed label appended in the tree."""

    def test_exact(self) -> None:
        assert (
            tree_account_suffix(Matches(exact=("ACCT-0100",), close=()))
            == "[Account: ACCT-0100]"
        )

    def test_exact_multiple(self) -> None:
        assert (
            tree_account_suffix(Matches(exact=("ACCT-0111", "ACCT-0112"), close=()))
            == "[Account: ACCT-0111, ACCT-0112]"
        )

    def test_close(self) -> None:
        assert (
            tree_account_suffix(Matches(exact=(), close=("ACCT-0110",)))
            == "[possibly ACCT-0110 — verify]"
        )

    def test_no_match_is_em_dash(self) -> None:
        assert tree_account_suffix(Matches(exact=(), close=())) == "[—]"


class TestIsExistingCustomer:
    """``is_existing_customer`` powers the plain-English status counts."""

    def test_exact_is_customer(self) -> None:
        assert is_existing_customer(Matches(exact=("ACCT-0100",), close=())) is True

    def test_close_is_customer(self) -> None:
        assert is_existing_customer(Matches(exact=(), close=("ACCT-0110",))) is True

    def test_no_match_is_not_customer(self) -> None:
        assert is_existing_customer(Matches(exact=(), close=())) is False
