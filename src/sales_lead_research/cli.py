# agent-notes: { ctx: "REPL chat loop, EDGAR lookup, recursive tree + CSV output", deps: ["rich", "httpx", "csv", "sales_lead_research.discovery"], state: active, last: "sato@2026-04-28" }
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

from sales_lead_research.chat.intent import parse
from sales_lead_research.discovery import (
    CompanyNotFound,
    EdgarLookupError,
    SubsidiaryNode,
    fetch_subsidiary_tree,
    search_companies,
    web_search_subsidiaries,
)
from sales_lead_research.discovery.edgar import (
    exhibit_21_url,
    find_parent_company,
    latest_annual_report,
    parse_exhibit_21,
)
from sales_lead_research.matching.present import account_cell, tree_account_suffix
from sales_lead_research.matching.store import (
    CustomerStore,
    Matches,
    lookup_with_confidence,
)

PLACEHOLDER_CHILD = "(subsidiary data unavailable - SEC lookup not yet implemented)"

def extract_company_name(query: str) -> str:
    """Extract a company name from a natural-language query.

    Thin backwards-compatible shim over the shared intent parser
    (``chat.intent.parse``). The natural-language patterns live in one
    place now; this name is kept so existing callers and tests keep
    working. Returns ``""`` for blank / non-lookup input.
    """
    return parse(query).company_name or ""


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


def _match_subsidiaries(
    root: SubsidiaryNode, store: CustomerStore | None
) -> dict[str, Matches]:
    """Map every subsidiary name in the tree to its customer matches.

    Each unique name is looked up once. When no customer store is open,
    every name maps to an empty ``Matches`` so callers can index safely.
    """
    result: dict[str, Matches] = {}

    def _walk(node: SubsidiaryNode) -> None:
        for child in node.children:
            if child.name not in result:
                result[child.name] = (
                    lookup_with_confidence(store, child.name)
                    if store is not None
                    else Matches(exact=(), close=())
                )
            _walk(child)

    _walk(root)
    return result


def _print_match_summary(
    console: Console, matches_by_name: dict[str, Matches]
) -> None:
    """Print a plain-English count of how many subsidiaries are customers."""
    confirmed = sum(1 for m in matches_by_name.values() if m.exact)
    possible = sum(1 for m in matches_by_name.values() if not m.exact and m.close)
    if confirmed:
        console.print(f"{confirmed} of these are already in your customer list.")
    if possible:
        console.print(f"{possible} look like possible matches worth a quick check.")
    if not confirmed and not possible:
        console.print("None of these are in your customer list yet.")


def run_repl(
    input_lines: Iterable[str],
    output: TextIO,
    *,
    client: httpx.Client | None = None,
    output_dir: Path | None = None,
    store: CustomerStore | None = None,
) -> None:
    console = Console(file=output)
    it = iter(input_lines)

    for raw in it:
        intent = parse(raw)
        if intent.kind == "exit":
            return
        if intent.kind == "empty":
            continue
        if intent.kind == "unknown":
            console.print(
                "I look up a company's corporate family tree. Try a company "
                "name like 'FedEx', or ask 'show me Apple's subsidiaries'."
            )
            continue

        line = intent.company_name or ""

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
                    root_name = result.get("parent") or line
                    if result.get("parent"):
                        console.print(f"Parent company: {result['parent']}")
                    subs: list[tuple[str, str]] = result.get("subsidiaries", [])
                    web_matches = {
                        sub_name: (
                            lookup_with_confidence(store, sub_name)
                            if store is not None
                            else Matches(exact=(), close=())
                        )
                        for sub_name, _ in subs
                    }
                    if subs:
                        tree = Tree(root_name)
                        for sub_name, jurisdiction in subs:
                            label = f"{sub_name} ({jurisdiction})" if jurisdiction else sub_name
                            if store is not None:
                                label += " " + tree_account_suffix(web_matches[sub_name])
                            tree.add(label)
                        console.print(tree)
                        console.print(f"({len(subs)} subsidiaries/divisions found)")
                        if store is not None:
                            _print_match_summary(console, web_matches)
                    if result.get("source"):
                        console.print(f"Source: {result['source']}")

                    if subs:
                        safe_name = root_name.lower().replace(" ", "_").replace("/", "_").replace("..", "_")
                        filename = safe_name + "_subsidiaries.csv"
                        csv_path = (output_dir / filename) if output_dir is not None else Path(filename)
                        with open(csv_path, "w", newline="") as f:
                            writer = csv.writer(f)
                            writer.writerow(["Subsidiary Name", "Jurisdiction", "Level", "Account ID"])
                            for sub_name, jurisdiction in subs:
                                cell = account_cell(web_matches[sub_name]) if store is not None else ""
                                writer.writerow([sub_name, jurisdiction, 1, cell])
                        console.print(f"Saved to {filename} ({len(subs)} subsidiaries)")
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
            accession, form, filing_date = latest_annual_report(cik, client)
            url = exhibit_21_url(cik, accession, client)
        except EdgarLookupError as exc:
            console.print(str(exc))
            continue

        console.print(f"Source: {url}")
        if filing_date:
            console.print(
                f"Subsidiaries are from this company's {form} filed {filing_date}."
            )
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

        # Match every subsidiary against the customer list (once per name).
        matches_by_name = _match_subsidiaries(root_node, store)

        # Render tree, annotating each subsidiary with its customer status.
        console.print(f"{company_name} (CIK: {cik})")

        def _add_children(rich_tree: Tree, node: SubsidiaryNode) -> None:
            for child in node.children:
                label = f"{child.name} ({child.jurisdiction})" if child.jurisdiction else child.name
                if store is not None:
                    label += " " + tree_account_suffix(matches_by_name[child.name])
                branch = rich_tree.add(label)
                _add_children(branch, child)

        tree = Tree(root_node.name)
        _add_children(tree, root_node)
        console.print(tree)

        if store is not None:
            _print_match_summary(console, matches_by_name)

        # Flatten tree for CSV export
        flat: list[tuple[str, str, int]] = []

        def _flatten(node: SubsidiaryNode, depth: int) -> None:
            for child in node.children:
                flat.append((child.name, child.jurisdiction, depth))
                _flatten(child, depth + 1)

        _flatten(root_node, 1)

        # CSV export (enriched with the customer Account ID column)
        safe_name = company_name.lower().replace(" ", "_").replace("/", "_").replace("..", "_")
        filename = safe_name + "_subsidiaries.csv"
        if output_dir is not None:
            csv_path = output_dir / filename
        else:
            csv_path = Path(filename)

        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Subsidiary Name", "Jurisdiction", "Level", "Account ID"])
            for sub_name, jurisdiction, level in flat:
                cell = account_cell(matches_by_name[sub_name]) if store is not None else ""
                writer.writerow([sub_name, jurisdiction, level, cell])

        console.print(f"Saved to {filename} ({len(flat)} subsidiaries)")
