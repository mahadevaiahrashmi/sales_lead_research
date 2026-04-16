# agent-notes: { ctx: "REPL chat loop, EDGAR lookup, recursive tree + CSV output", deps: ["rich", "httpx", "csv", "sales_lead_research.edgar"], state: active, last: "sato@2026-04-16" }
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
import re
from collections.abc import Iterable
from pathlib import Path
from typing import TextIO

import httpx
from rich.console import Console
from rich.tree import Tree

from sales_lead_research.edgar import (
    CompanyNotFound,
    EdgarLookupError,
    SubsidiaryNode,
    exhibit_21_url,
    fetch_subsidiary_tree,
    find_parent_company,
    latest_10k_accession,
    parse_exhibit_21,
    search_companies,
)
from sales_lead_research.web_fallback import web_search_subsidiaries

PLACEHOLDER_CHILD = "(subsidiary data unavailable - SEC lookup not yet implemented)"

_NL_PATTERNS = [
    re.compile(r"(?:show|list|get|find|look\s*up|fetch|pull|display)\s+(?:me\s+)?(?:the\s+)?(.+?)(?:'s)?\s+(?:subsidiaries|hierarchy|corporate\s+(?:structure|tree)|sub\s*companies|child\s+companies)", re.I),
    re.compile(r"(?:what|which)\s+(?:are|companies?\s+(?:does|do))\s+(?:the\s+)?(.+?)(?:'s)?\s+(?:subsidiaries|own|have)", re.I),
    re.compile(r"who\s+(?:does|do|are)\s+(?:the\s+)?(.+?)(?:'s)?\s+(?:own|subsidiaries)", re.I),
    re.compile(r"(?:subsidiaries|hierarchy|corporate\s+(?:structure|tree)|sub\s*companies)\s+(?:of|for|under)\s+(?:the\s+)?(.+)", re.I),
    re.compile(r"(?:tell\s+me\s+about|search\s+(?:for)?|look\s*up|info\s+(?:on|about|for))\s+(?:the\s+)?(.+)", re.I),
]


def extract_company_name(query: str) -> str:
    """Extract a company name from a natural language query."""
    query = query.strip()
    if not query:
        return query
    for pattern in _NL_PATTERNS:
        m = pattern.search(query)
        if m:
            return m.group(1).strip().rstrip("?!")
    return query.rstrip("?!")


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

        line = extract_company_name(line)

        if client is None:
            # Placeholder mode (original issue #1 behavior)
            tree = Tree(line)
            tree.add(PLACEHOLDER_CHILD)
            console.print(tree)
            continue

        # --- EDGAR integration flow ---
        try:
            matches = search_companies(line, client)
        except CompanyNotFound as exc:
            console.print(str(exc))
            console.print("Search the web for this company's annual report? [Y/n]")
            answer = _confirm(it)
            if answer is None:
                return
            if answer:
                console.print(f"Searching the web for {line}...")
                result = web_search_subsidiaries(line, client)
                if result and (result.get("parent") or result.get("subsidiaries")):
                    if result.get("parent"):
                        console.print(f"Parent company: {result['parent']}")
                    subs = result.get("subsidiaries", [])
                    if subs:
                        tree = Tree(result.get("parent") or line)
                        for sub in subs:
                            tree.add(sub)
                        console.print(tree)
                        console.print(f"({len(subs)} subsidiaries/divisions found)")
                    if result.get("source"):
                        console.print(f"Source: {result['source']}")
                else:
                    console.print(
                        "No corporate structure data found via web search. "
                        "Try searching for the company's legal parent name directly."
                    )
            continue
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

        # Build recursive subsidiary tree
        try:
            root_node = fetch_subsidiary_tree(company_name, client)
        except EdgarLookupError as exc:
            console.print(str(exc))
            continue

        # Render tree
        console.print(f"{company_name} (CIK: {cik})")

        def _add_children(rich_tree: Tree, node: SubsidiaryNode) -> None:
            for child in node.children:
                label = f"{child.name} ({child.jurisdiction})" if child.jurisdiction else child.name
                branch = rich_tree.add(label)
                _add_children(branch, child)

        tree = Tree(root_node.name)
        _add_children(tree, root_node)
        console.print(tree)

        # Flatten tree for CSV export
        flat: list[tuple[str, str, int]] = []

        def _flatten(node: SubsidiaryNode, depth: int) -> None:
            for child in node.children:
                flat.append((child.name, child.jurisdiction, depth))
                _flatten(child, depth + 1)

        _flatten(root_node, 1)

        # CSV export
        safe_name = company_name.lower().replace(" ", "_").replace("/", "_").replace("..", "_")
        filename = safe_name + "_subsidiaries.csv"
        if output_dir is not None:
            csv_path = output_dir / filename
        else:
            csv_path = Path(filename)

        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Subsidiary Name", "Jurisdiction", "Level"])
            for sub_name, jurisdiction, level in flat:
                writer.writerow([sub_name, jurisdiction, level])

        console.print(f"Saved to {filename} ({len(flat)} subsidiaries)")
