# agent-notes: { ctx: "runnable precision/recall/F1 report for the customer matcher", deps: ["src/sales_lead_research/matching/evaluate.py", "src/sales_lead_research/matching/store.py"], state: active, last: "sato@2026-05-31" }
"""Print a precision / recall / F1 report for the customer matcher.

Builds a small, hand-labelled customer list and a set of labelled leads
(subsidiary name -> the account ids that are genuinely the same company),
runs the matcher over them, and reports both strict (exact matches only)
and lenient (include the "possibly -- verify" close tier) scores, plus the
misses.

    uv run python scripts/eval_matching.py
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

from sales_lead_research.matching.evaluate import evaluate, predicted_account_ids
from sales_lead_research.matching.store import lookup_with_confidence, open_store

# The labelled customer list: (account_id, company_name).
CUSTOMERS: list[tuple[str, str]] = [
    ("ACCT-0102", "FedEx Ground Package System, Inc."),
    ("ACCT-0105", "FedEx Services Inc."),
    ("ACCT-0106", "FedEx Trade Networks Transport & Brokerage, Inc."),
    ("ACCT-0110", "FedEx Corporate Service Inc."),
    ("ACCT-0111", "FedEx Custom Critical, Inc."),
    ("ACCT-0112", "FedEx Custom Critical Inc"),
    ("ACCT-0300", "Apple Inc."),
    ("ACCT-9001", "Acme Corporation"),
]

# Labelled leads: (subsidiary name as it might appear in a filing,
# gold = the set of account ids that are genuinely the same company).
LABELLED_LEADS: list[tuple[str, set[str]]] = [
    ("FedEx Ground Package System Inc.", {"ACCT-0102"}),                 # exact
    ("FedEx Custom Critical Inc", {"ACCT-0111", "ACCT-0112"}),           # exact, duplicate rows
    ("Apple Inc.", {"ACCT-0300"}),                                       # exact
    ("FedEx Trade Networks Transport & Brokerage International, Inc.",
     {"ACCT-0106"}),                                                     # close ("verify") tier
    ("FedEx Corporate Services, Inc.", {"ACCT-0110"}),                   # morphological miss (TD-003)
    ("Globex Worldwide LLC", set()),                                     # true negative
]

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
"""


def _build_db(path: Path) -> None:
    with sqlite3.connect(path) as con:
        con.executescript(_SCHEMA)
        con.executemany(
            "INSERT INTO customers (account_id, company_name) VALUES (?, ?)",
            CUSTOMERS,
        )
        con.commit()


def run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "eval.sqlite"
        _build_db(db)
        store = open_store(db)
        assert store is not None

        strict_cases: list[tuple[set[str], set[str]]] = []
        lenient_cases: list[tuple[set[str], set[str]]] = []
        misses: list[tuple[str, set[str], bool]] = []

        for name, gold in LABELLED_LEADS:
            matches = lookup_with_confidence(store, name)
            strict = predicted_account_ids(matches, include_close=False)
            lenient = predicted_account_ids(matches, include_close=True)
            strict_cases.append((strict, gold))
            lenient_cases.append((lenient, gold))
            if gold - strict:  # a strict false negative
                still_missed = bool(gold - lenient)
                misses.append((name, gold - strict, still_missed))

        strict_m = evaluate(strict_cases)
        lenient_m = evaluate(lenient_cases)

        print(
            f"Matching evaluation — {len(CUSTOMERS)} customer rows, "
            f"{len(LABELLED_LEADS)} labelled leads\n"
        )
        print("Strict (exact matches only):")
        print(
            f"  precision {strict_m.precision:.2f}  recall {strict_m.recall:.2f}  "
            f"F1 {strict_m.f1:.2f}   (TP {strict_m.true_positives}, "
            f"FP {strict_m.false_positives}, FN {strict_m.false_negatives})\n"
        )
        print('Lenient (include "possibly -- verify" close matches):')
        print(
            f"  precision {lenient_m.precision:.2f}  recall {lenient_m.recall:.2f}  "
            f"F1 {lenient_m.f1:.2f}   (TP {lenient_m.true_positives}, "
            f"FP {lenient_m.false_positives}, FN {lenient_m.false_negatives})\n"
        )
        if misses:
            print("Strict misses (false negatives):")
            for name, missed, still_missed in misses:
                tag = (
                    "still missed by close tier"
                    if still_missed
                    else "recovered by the close tier"
                )
                print(f"  - {name!r} -> expected {', '.join(sorted(missed))}  ({tag})")


if __name__ == "__main__":
    run()
