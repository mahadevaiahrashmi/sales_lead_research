# agent-notes: { ctx: "REPL chat loop, placeholder hierarchy renderer", deps: ["rich"], state: active, last: "sato@2026-04-15b" }
"""CLI chat loop.

``run_repl`` iterates input lines as user queries, rendering a placeholder
corporate hierarchy tree for each non-empty company name. Exits on ``"exit"``
or when the input iterator is exhausted. Empty/whitespace lines are skipped.
"""

from collections.abc import Iterable
from typing import TextIO

from rich.console import Console
from rich.tree import Tree

PLACEHOLDER_CHILD = "(subsidiary data unavailable - SEC lookup not yet implemented)"


def run_repl(input_lines: Iterable[str], output: TextIO) -> None:
    console = Console(file=output)
    for raw in input_lines:
        line = raw.strip()
        if line == "exit":
            return
        if not line:
            continue
        tree = Tree(line)
        tree.add(PLACEHOLDER_CHILD)
        console.print(tree)
