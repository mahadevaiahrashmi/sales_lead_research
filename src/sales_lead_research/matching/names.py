# agent-notes: { ctx: "Wave 2.1: pure name-matching primitives — normalise, jaccard, classify (per ADR-0003 §4)", deps: [], state: active, last: "sato@2026-04-28" }
"""Pure string-matching primitives for customer-name comparison.

Three public functions, all pure (no I/O, no state):

- ``normalise_name`` — lowercase, drop bracket characters, drop trailing
  legal-suffix tokens, collapse whitespace.
- ``jaccard_similarity`` — token-set Jaccard on the normalised forms.
- ``classify_match`` — ``"exact"`` / ``"close"`` / ``"none"`` verdict.

Behaviour is fully specified by ``tests/test_names.py`` and ADR-0003 §4.
"""

from __future__ import annotations


_LEGAL_SUFFIXES: frozenset[str] = frozenset(
    {
        "inc", "incorporated",
        "ltd", "limited",
        "gmbh",
        "lda",
        "sas",
        "s.a",
        "co",
        "corp", "corporation",
        "llc",
        "plc",
        "ag",
        "n.v", "nv",
        "b.v", "bv",
        "sarl",
        "s.p.a", "spa",
        "s.r.l", "srl",
        "pty",
        "oy", "oyj",
    }
)

_BRACKETS = "()[]{}"
_EDGE_PUNCTUATION = ".,;:"


def normalise_name(raw: str) -> str:
    """Return the canonical lowercase form of *raw* with legal suffixes removed."""
    lowered = raw.lower()
    for bracket in _BRACKETS:
        lowered = lowered.replace(bracket, " ")
    tokens = [t.strip(_EDGE_PUNCTUATION) for t in lowered.split()]
    while tokens and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(t for t in tokens if t)


def jaccard_similarity(a: str, b: str) -> float:
    """Return token-set Jaccard similarity of the normalised forms of *a* and *b*."""
    set_a = set(normalise_name(a).split())
    set_b = set(normalise_name(b).split())
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def classify_match(subsidiary: str, customer: str) -> str:
    """Return ``"exact"``, ``"close"``, or ``"none"`` for the pair."""
    norm_sub = normalise_name(subsidiary)
    norm_cust = normalise_name(customer)
    if norm_sub and norm_cust and norm_sub == norm_cust:
        return "exact"
    if jaccard_similarity(subsidiary, customer) >= 0.8:
        return "close"
    return "none"
