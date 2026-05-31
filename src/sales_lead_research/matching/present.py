# agent-notes: { ctx: "Gap 1: render a Matches value-object as CSV cell / tree suffix (pure)", deps: ["src/sales_lead_research/matching/store.py"], state: active, last: "sato@2026-05-29" }
"""Turn a customer-match result into display strings.

Three pure functions (no I/O) shared by the CLI and Gradio layers so the
"which subsidiaries are already customers" rendering lives in one place:

- ``account_cell`` — plain-text value for the spreadsheet / table cell.
- ``tree_account_suffix`` — bracketed label appended to a subsidiary in
  the indented tree view.
- ``is_existing_customer`` — boolean used for the plain-English counts
  ("3 of these are already in your customer list").

Rendering rules follow product-context decisions 1 and 2:
exact matches win and render as their account id(s); close-only matches
render with a "possibly … — verify" marker; no match is blank.
"""

from __future__ import annotations

from sales_lead_research.matching.store import Matches

_VERIFY_PREFIX = "possibly "
_VERIFY_SUFFIX = " — verify"
_NO_MATCH_TREE = "[—]"


def account_cell(matches: Matches) -> str:
    """Return the plain-text account cell for a subsidiary.

    Exact matches take precedence and are returned as comma-separated
    account ids. If there are only close matches, they are returned with
    a ``"possibly … — verify"`` marker. No match returns an empty string.
    """
    if matches.exact:
        return ", ".join(matches.exact)
    if matches.close:
        return _VERIFY_PREFIX + ", ".join(matches.close) + _VERIFY_SUFFIX
    return ""


def tree_account_suffix(matches: Matches) -> str:
    """Return the bracketed suffix appended to a subsidiary in the tree.

    ``"[Account: …]"`` for confirmed matches, ``"[possibly … — verify]"``
    for close-only matches, and ``"[—]"`` when the subsidiary is not a
    customer.
    """
    if matches.exact:
        return f"[Account: {', '.join(matches.exact)}]"
    if matches.close:
        return f"[{_VERIFY_PREFIX}{', '.join(matches.close)}{_VERIFY_SUFFIX}]"
    return _NO_MATCH_TREE


def is_existing_customer(matches: Matches) -> bool:
    """Return ``True`` if the subsidiary matched a customer (exact or close)."""
    return bool(matches.exact or matches.close)
