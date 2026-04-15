# agent-notes: { ctx: "console_scripts entrypoint, wraps run_repl on stdin/stdout", deps: ["sales_lead_research.cli"], state: active, last: "sato@2026-04-15" }
"""Entry point for the ``sales-lead-research`` console script."""

import sys

from sales_lead_research.cli import run_repl


def main() -> None:
    run_repl(sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
