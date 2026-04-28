# agent-notes: { ctx: "console_scripts entrypoint, wraps run_repl on stdin/stdout", deps: ["sales_lead_research.cli", "sales_lead_research.discovery"], state: active, last: "sato@2026-04-28" }
"""Entry point for the ``sales-lead-research`` console script."""

import sys

from sales_lead_research.cli import run_repl
from sales_lead_research.discovery import build_client


def main() -> None:
    client = build_client("Sales Lead Research (mahadevaiah.rashmi@gmail.com)")
    run_repl(sys.stdin, sys.stdout, client=client)


if __name__ == "__main__":
    main()
