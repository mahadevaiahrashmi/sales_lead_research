# agent-notes: { ctx: "generate SQLite dummy customer database for chat+DB-match demos", deps: [docs/product-context.md], state: active, last: "sato@2026-04-20" }
"""Create a SQLite customer database populated with fake companies.

The database shape matches the product-context schema:
    company_name, account_id, parent_id, ultimate_parent_id,
    location, country, tax_number, zip_code

The data is a realistic mix designed to exercise every matching path
the chat tool will have:
  - Exact matches against likely SEC Exhibit 21 entries (FedEx, Apple, ...).
  - Near-matches for the fuzzy-match "possibly ACCT-1234 -- verify" tier
    (e.g. "FedEx Corporate Service Inc." vs the real "...Services, Inc.").
  - Duplicate rows for the multi-match case (two "FedEx Custom Critical"
    variants sharing the same tax number).
  - Parenthesised-country names ("DHL Express (Portugal) Lda.") to verify
    the right-to-left country scan in the web-fallback path.
  - Unrelated noise so non-matches produce empty account_id cells.

Run: `uv run python scripts/init_dummy_db.py`

The output file is regenerable and is gitignored.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DB_PATH = Path(
    os.environ.get(
        "SALES_DB_PATH",
        Path(__file__).resolve().parent.parent / "data" / "customers.sqlite",
    )
)

SCHEMA = """
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

ROWS: list[tuple[str, str, str | None, str, str, str, str, str]] = [
    # ---- Top-level parents ----
    ("ACCT-0100", "FedEx Corporation", None, "ACCT-0100",
     "Memphis", "United States", "US-71-0427007", "38125"),
    ("ACCT-0200", "Deutsche Post AG", None, "ACCT-0200",
     "Bonn", "Germany", "DE-205690497", "53113"),
    ("ACCT-0300", "Apple Inc.", None, "ACCT-0300",
     "Cupertino", "United States", "US-94-2404110", "95014"),
    ("ACCT-0400", "Microsoft Corporation", None, "ACCT-0400",
     "Redmond", "United States", "US-91-1144442", "98052"),
    ("ACCT-0500", "3M Company", None, "ACCT-0500",
     "Saint Paul", "United States", "US-41-0417775", "55144"),

    # ---- FedEx family (exact + near + duplicate + parens-country) ----
    ("ACCT-0101", "FedEx Express Corporation", "ACCT-0100", "ACCT-0100",
     "Memphis", "United States", "US-62-1482161", "38125"),
    ("ACCT-0102", "FedEx Ground Package System, Inc.", "ACCT-0100", "ACCT-0100",
     "Pittsburgh", "United States", "US-25-1721234", "15205"),
    ("ACCT-0103", "FedEx Freight Inc.", "ACCT-0100", "ACCT-0100",
     "Harrison", "United States", "US-43-1897146", "72601"),
    ("ACCT-0104", "FedEx Office and Print Services, Inc.", "ACCT-0100", "ACCT-0100",
     "Plano", "United States", "US-75-2568750", "75074"),
    ("ACCT-0105", "FedEx Services Inc.", "ACCT-0100", "ACCT-0100",
     "Collierville", "United States", "US-27-4513972", "38017"),
    ("ACCT-0106", "FedEx Trade Networks Transport & Brokerage, Inc.", "ACCT-0100", "ACCT-0100",
     "Buffalo", "United States", "US-16-0869541", "14202"),
    ("ACCT-0107", "FedEx Supply Chain Distribution System, Inc.", "ACCT-0100", "ACCT-0100",
     "Memphis", "United States", "US-57-8123443", "38108"),
    ("ACCT-0108", "FedEx Express Canada Ltd.", "ACCT-0100", "ACCT-0100",
     "Toronto", "Canada", "CA-889287113", "M9L 2P9"),
    ("ACCT-0109", "FedEx Express (France) SAS", "ACCT-0100", "ACCT-0100",
     "Roissy", "France", "FR-43821394719", "95701"),
    # Near-match: "Service" vs "Services" exercises fuzzy tier
    ("ACCT-0110", "FedEx Corporate Service Inc.", "ACCT-0100", "ACCT-0100",
     "Memphis", "United States", "US-27-1234567", "38125"),
    # Multi-match pair: two representations of "FedEx Custom Critical"
    ("ACCT-0111", "FedEx Custom Critical, Inc.", "ACCT-0100", "ACCT-0100",
     "Uniontown", "United States", "US-34-1745923", "44685"),
    ("ACCT-0112", "FedEx Custom Critical Inc", "ACCT-0100", "ACCT-0100",
     "Akron", "United States", "US-34-1745923", "44333"),
    ("ACCT-0113", "FedEx Express (Netherlands) B.V.", "ACCT-0100", "ACCT-0100",
     "Schiphol", "Netherlands", "NL-810123456B01", "1118 BH"),

    # ---- DHL family (includes the regression case for right-to-left country scan) ----
    ("ACCT-0201", "DHL Express (Germany) GmbH", "ACCT-0200", "ACCT-0200",
     "Bonn", "Germany", "DE-205123456", "53113"),
    ("ACCT-0202", "DHL Express (UK) Limited", "ACCT-0200", "ACCT-0200",
     "Hounslow", "United Kingdom", "GB-432178923", "TW6 2QE"),
    ("ACCT-0203", "DHL Express (Portugal) Lda.", "ACCT-0200", "ACCT-0200",
     "Lisbon", "Portugal", "PT-502234567", "1990-095"),
    ("ACCT-0204", "DHL Express (Netherlands) B.V.", "ACCT-0200", "ACCT-0200",
     "Utrecht", "Netherlands", "NL-813456789B01", "3542 AA"),
    ("ACCT-0205", "DHL Express (France) SA", "ACCT-0200", "ACCT-0200",
     "Roissy", "France", "FR-67345678901", "95700"),
    ("ACCT-0206", "DHL Global Forwarding GmbH", "ACCT-0200", "ACCT-0200",
     "Bonn", "Germany", "DE-312456789", "53113"),
    ("ACCT-0207", "DHL Logistics Services", "ACCT-0200", "ACCT-0200",
     "Brussels", "Belgium", "BE-0401123456", "1130"),
    ("ACCT-0208", "DHL Parcel UK Ltd", "ACCT-0200", "ACCT-0200",
     "Birmingham", "United Kingdom", "GB-543234567", "B7 5DP"),
    ("ACCT-0209", "DHL Freight Portugal", "ACCT-0200", "ACCT-0200",
     "Maia", "Portugal", "PT-503456789", "4470-177"),

    # ---- Apple family ----
    ("ACCT-0301", "Apple Operations International", "ACCT-0300", "ACCT-0300",
     "Cork", "Ireland", "IE-8923456H", "T12 V9ER"),
    ("ACCT-0302", "Apple Sales International", "ACCT-0300", "ACCT-0300",
     "Cork", "Ireland", "IE-8912345L", "T12 V9ER"),
    ("ACCT-0303", "Apple Operations Europe", "ACCT-0300", "ACCT-0300",
     "Cork", "Ireland", "IE-6578910C", "T12 V9ER"),
    ("ACCT-0304", "Apple Distribution International Limited", "ACCT-0300", "ACCT-0300",
     "Cork", "Ireland", "IE-9651234P", "T12 V9ER"),
    ("ACCT-0305", "Apple Retail Germany GmbH", "ACCT-0300", "ACCT-0300",
     "Munich", "Germany", "DE-812567890", "80333"),
    ("ACCT-0306", "Apple (UK) Limited", "ACCT-0300", "ACCT-0300",
     "London", "United Kingdom", "GB-678901234", "WC2B 4AN"),
    ("ACCT-0307", "Braeburn Capital Inc.", "ACCT-0300", "ACCT-0300",
     "Reno", "United States", "US-26-1234567", "89509"),

    # ---- Microsoft family ----
    ("ACCT-0401", "Microsoft Ireland Operations Limited", "ACCT-0400", "ACCT-0400",
     "Dublin", "Ireland", "IE-8278122H", "D18 P521"),
    ("ACCT-0402", "LinkedIn Corporation", "ACCT-0400", "ACCT-0400",
     "Sunnyvale", "United States", "US-47-1984876", "94085"),
    ("ACCT-0403", "GitHub, Inc.", "ACCT-0400", "ACCT-0400",
     "San Francisco", "United States", "US-20-5528557", "94107"),
    ("ACCT-0404", "Microsoft Mobile Oy", "ACCT-0400", "ACCT-0400",
     "Espoo", "Finland", "FI-24468821", "02610"),

    # ---- 3M family ----
    ("ACCT-0501", "3M Innovative Properties Company", "ACCT-0500", "ACCT-0500",
     "Saint Paul", "United States", "US-41-1967776", "55144"),
    ("ACCT-0502", "3M Canada Company", "ACCT-0500", "ACCT-0500",
     "London, Ontario", "Canada", "CA-100456789", "N5V 3R6"),
    ("ACCT-0503", "3M Deutschland GmbH", "ACCT-0500", "ACCT-0500",
     "Neuss", "Germany", "DE-123456789", "41453"),
    ("ACCT-0504", "3M Brasil Ltda.", "ACCT-0500", "ACCT-0500",
     "Sumare", "Brazil", "BR-123456000189", "13181-900"),

    # ---- Unrelated noise (should never match any subsidiary) ----
    ("ACCT-9001", "Acme Corporation", None, "ACCT-9001",
     "Phoenix", "United States", "US-86-1234567", "85001"),
    ("ACCT-9002", "Widget Industries LLC", None, "ACCT-9002",
     "Chicago", "United States", "US-36-7654321", "60601"),
    ("ACCT-9003", "Global Parts International", None, "ACCT-9003",
     "Osaka", "Japan", "JP-1234567890123", "530-0001"),
    ("ACCT-9004", "Northern Lights Ltd.", None, "ACCT-9004",
     "Oslo", "Norway", "NO-923456789MVA", "0250"),
    ("ACCT-9005", "Sunset Holdings SA", None, "ACCT-9005",
     "Madrid", "Spain", "ES-B12345678", "28001"),
]


def build(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    with sqlite3.connect(db_path) as con:
        con.executescript(SCHEMA)
        con.executemany(
            """
            INSERT INTO customers (
                account_id, company_name, parent_id, ultimate_parent_id,
                location, country, tax_number, zip_code
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ROWS,
        )
        con.commit()


def summarise(db_path: Path) -> None:
    with sqlite3.connect(db_path) as con:
        total = con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        fedex = con.execute(
            "SELECT COUNT(*) FROM customers WHERE company_name LIKE 'FedEx%'"
        ).fetchone()[0]
        dhl = con.execute(
            "SELECT COUNT(*) FROM customers WHERE company_name LIKE 'DHL%'"
        ).fetchone()[0]
        apple = con.execute(
            "SELECT COUNT(*) FROM customers WHERE company_name LIKE 'Apple%'"
        ).fetchone()[0]

    print(f"Database created at {db_path}")
    print(f"  total rows:   {total}")
    print(f"  FedEx-family: {fedex}")
    print(f"  DHL-family:   {dhl}")
    print(f"  Apple-family: {apple}")


if __name__ == "__main__":
    build(DB_PATH)
    summarise(DB_PATH)
