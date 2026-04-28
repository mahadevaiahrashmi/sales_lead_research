# agent-notes: { ctx: "console_scripts entrypoint: REPL by default, init-db subcommand creates customer DB", deps: ["argparse", "sales_lead_research.cli", "sales_lead_research.discovery", "sales_lead_research.matching.init_db"], state: active, last: "sato@2026-04-28" }
"""Entry point for the ``sales-lead-research`` console script."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

from sales_lead_research.cli import run_repl
from sales_lead_research.discovery import build_client
from sales_lead_research.matching.init_db import init_db

_DEFAULT_DB_PATH = Path("data/customers.sqlite")


def _resolve_db_path() -> Path:
    env_path = os.environ.get("SALES_DB_PATH")
    return Path(env_path) if env_path else _DEFAULT_DB_PATH


def _run_repl() -> int:
    client = build_client("Sales Lead Research (mahadevaiah.rashmi@gmail.com)")
    run_repl(sys.stdin, sys.stdout, client=client)
    return 0


def _run_init_db(seed: Path | None) -> int:
    db_path = _resolve_db_path()
    try:
        init_db(db_path, seed_csv=seed)
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if seed is not None:
        with sqlite3.connect(db_path) as con:
            count = con.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        print(f"Created customer database at {db_path} with {count} seeded rows.")
    else:
        print(f"Created empty customer database at {db_path}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sales-lead-research",
        description="Look up corporate hierarchies for sales prospecting.",
    )
    subparsers = parser.add_subparsers(dest="command")

    init = subparsers.add_parser(
        "init-db",
        help="Create the customer database file (optionally loading a seed CSV).",
    )
    init.add_argument(
        "--seed",
        type=Path,
        default=None,
        help="Optional path to a CSV file used to populate the new database.",
    )

    args = parser.parse_args(argv)

    if args.command == "init-db":
        return _run_init_db(args.seed)
    return _run_repl()


if __name__ == "__main__":
    sys.exit(main())
