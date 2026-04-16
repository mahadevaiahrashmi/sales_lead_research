# agent-notes: { ctx: "REPL chat loop, EDGAR lookup, tree + CSV output", deps: ["rich", "httpx", "csv", "sales_lead_research.edgar"], state: active, last: "sato@2026-04-16" }
"""CLI chat loop.

``run_repl`` iterates input lines as user queries, rendering a placeholder
corporate hierarchy tree for each non-empty company name. Exits on ``"exit"``
or when the input iterator is exhausted. Empty/whitespace lines are skipped.

Issue #3 adds: fuzzy company matching with disambiguation, two confirmation
gates (company resolution + filing source), Exhibit 21 parsing, rich tree
rendering of subsidiaries, and CSV export.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path
from typing import TextIO

import httpx
from rich.console import Console
from rich.tree import Tree

from sales_lead_research.edgar import (
    EdgarLookupError,
    exhibit_21_url,
    latest_10k_accession,
    parse_exhibit_21,
    search_companies,
)

PLACEHOLDER_CHILD = "(subsidiary data unavailable - SEC lookup not yet implemented)"


def _next_line(it: iter) -> str | None:
    """Read the next line from the input iterator, returning None on EOF."""
    val = next(it, None)
    if val is None:
        return None
    return val.strip()


def _confirm(it: iter) -> bool | None:
    """Read a confirmation line. Returns True for y/Y/empty, False for n/N, None for EOF."""
    line = _next_line(it)
    if line is None:
        return None
    if line == "" or line.lower() == "y":
        return True
    if line.lower() == "n":
        return False
    return True


def run_repl(
    input_lines: Iterable[str],
    output: TextIO,
    *,
    client: httpx.Client | None = None,
    output_dir: Path | None = None,
) -> None:
    console = Console(file=output)
    it = iter(input_lines)

    for raw in it:
        line = raw.strip()
        if line == "exit":
            return
        if not line:
            continue

        if client is None:
            # Placeholder mode (original issue #1 behavior)
            tree = Tree(line)
            tree.add(PLACEHOLDER_CHILD)
            console.print(tree)
            continue

        # --- EDGAR integration flow ---
        try:
            matches = search_companies(line, client)
        except EdgarLookupError as exc:
            console.print(str(exc))
            continue

        if len(matches) == 1:
            company_name, cik = matches[0]
            console.print(f"Resolved: {company_name} (CIK: {cik})")
            console.print("Is this the right company? [Y/n]")
            answer = _confirm(it)
            if answer is None:
                return
            if not answer:
                continue
        else:
            # Multiple matches: show numbered list
            for i, (name, cik) in enumerate(matches, 1):
                console.print(f"  {i}. {name} (CIK: {cik})")
            choice_line = _next_line(it)
            if choice_line is None:
                return
            try:
                idx = int(choice_line) - 1
                company_name, cik = matches[idx]
            except (ValueError, IndexError):
                console.print("Invalid choice.")
                continue
            console.print(f"Resolved: {company_name} (CIK: {cik})")
            console.print("Is this the right company? [Y/n]")
            answer = _confirm(it)
            if answer is None:
                return
            if not answer:
                continue

        # Gate 2: filing source confirmation
        try:
            accession = latest_10k_accession(cik, client)
            url = exhibit_21_url(cik, accession, client)
        except EdgarLookupError as exc:
            console.print(str(exc))
            continue

        console.print(f"Source: {url}")
        console.print("Proceed with this filing? [Y/n]")
        answer = _confirm(it)
        if answer is None:
            return
        if not answer:
            continue

        # Fetch and parse Exhibit 21
        resp = client.get(url)
        resp.raise_for_status()
        subsidiaries = parse_exhibit_21(resp.text)

        # Render tree
        console.print(f"{company_name} (CIK: {cik})")
        tree = Tree(company_name)
        for sub_name, jurisdiction in subsidiaries:
            tree.add(f"{sub_name} ({jurisdiction})")
        console.print(tree)

        # CSV export
        filename = company_name.lower().replace(" ", "_") + "_subsidiaries.csv"
        if output_dir is not None:
            csv_path = output_dir / filename
        else:
            csv_path = Path(filename)

        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Subsidiary Name", "Jurisdiction"])
            for sub_name, jurisdiction in subsidiaries:
                writer.writerow([sub_name, jurisdiction])

        console.print(f"Saved to {filename} ({len(subsidiaries)} subsidiaries)")
