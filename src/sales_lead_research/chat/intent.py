# agent-notes: { ctx: "typed Intent + parse(); consolidates three NL-pattern copies", deps: ["docs/adrs/0003-sales-assistant-chat-architecture.md", "src/sales_lead_research/cli.py"], state: active, last: "sato@2026-04-28" }
"""Natural-language intent parsing for the sales-assistant chat layer.

Public API:

- :class:`Intent` — frozen dataclass with two fields: ``kind`` (one of
  ``"lookup" | "exit" | "empty" | "unknown"``) and ``company_name``
  (the extracted company string for ``lookup``, ``None`` otherwise).
- :func:`parse` — the single entry point. Maps a raw user query to an
  :class:`Intent`.

Per ADR-0003 §2 this is a rules-first, regex-only parser: zero new
dependencies, deterministic, fully offline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


_MAX_QUERY_LEN = 1024


@dataclass(frozen=True)
class Intent:
    """Typed result of parsing a user's chat query.

    ``company_name`` is untrusted user input. Downstream sinks
    (URL builders, terminal renderers, loggers) must escape it
    before use; the parser does not validate or sanitise it.
    """

    kind: Literal["lookup", "exit", "empty", "unknown"]
    company_name: str | None


_LOOKUP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(
        r"(?:show|list|get|find|look\s*up|fetch|pull|display)\s+(?:me\s+)?"
        r"(?:the\s+)?(.+?)(?:'s)?\s+"
        r"(?:subsidiaries|hierarchy|corporate\s+(?:structure|tree)|"
        r"sub\s*companies|child\s+companies)",
        re.I,
    ),
    re.compile(
        r"(?:what|which)\s+(?:are|companies?\s+(?:does|do))\s+"
        r"(?:the\s+)?(.+?)(?:'s)?\s+(?:subsidiaries|own|have)",
        re.I,
    ),
    re.compile(
        r"who\s+(?:does|do|are)\s+(?:the\s+)?(.+?)(?:'s)?\s+"
        r"(?:own|subsidiaries)",
        re.I,
    ),
    re.compile(
        r"(?:subsidiaries|hierarchy|corporate\s+(?:structure|tree)|"
        r"sub\s*companies)\s+(?:of|for|under)\s+(?:the\s+)?(.+)",
        re.I,
    ),
    re.compile(
        r"(?:tell\s+me\s+about|search(?:\s+for)?|look\s*up|"
        r"info\s+(?:on|about|for))\s+(?:the\s+)?(.+)",
        re.I,
    ),
]


_UNKNOWN_TOKENS: frozenset[str] = frozenset(
    {
        "hello",
        "hi",
        "hey",
        "help",
        "what",
        "how",
        "why",
        "when",
        "where",
        "who",
        # exit covers "exit now" / "exit please"; bare "exit" is short-circuited above.
        # tell covers "tell me a joke"; "tell me about X" is matched by pattern 5.
        "exit",
        "tell",
    }
)


def parse(query: str) -> Intent:
    """Map a raw user query to a typed :class:`Intent`.

    Outcomes:

    - **empty** — the query is blank or only whitespace. The chat loop
      uses this to silently skip blank lines.
    - **exit** — the query (after stripping surrounding whitespace and
      lowercasing) is exactly ``"exit"``. The chat loop terminates.
    - **lookup** — the query either matches one of the supported
      phrasing patterns ("show me X's subsidiaries", "search for X",
      etc.) or is a bare company name. ``company_name`` carries the
      extracted name; trailing ``?``/``!`` are stripped, interior
      punctuation (e.g. ``Apple Inc.``) is preserved.
    - **unknown** — chit-chat, off-topic questions, or imperatives the
      parser does not recognise. The chat loop replies in plain
      English asking the user to rephrase.
    """
    # Length cap on raw input — guard against pathological regex
    # backtracking before any work (strip, regex search) is done.
    if len(query) > _MAX_QUERY_LEN:
        return Intent(kind="unknown", company_name=None)

    stripped = query.strip()
    if not stripped:
        return Intent(kind="empty", company_name=None)

    if stripped.lower() == "exit":
        return Intent(kind="exit", company_name=None)

    for pattern in _LOOKUP_PATTERNS:
        match = pattern.search(stripped)
        if match:
            name = match.group(1).strip().rstrip("?!")
            return Intent(kind="lookup", company_name=name)

    first_token = stripped.split()[0].lower().rstrip("?")
    if (
        stripped == "?"
        or first_token in _UNKNOWN_TOKENS
        or re.search(r"[A-Za-z0-9]", stripped) is None
    ):
        return Intent(kind="unknown", company_name=None)

    return Intent(kind="lookup", company_name=stripped.rstrip("?!"))
