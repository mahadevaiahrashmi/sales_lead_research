# agent-notes: { ctx: "precision/recall/F1 for the customer matcher (pure)", deps: ["src/sales_lead_research/matching/store.py"], state: active, last: "sato@2026-05-31" }
"""Measure how good the customer matcher is.

Pure helpers (no I/O), so the maths is trivially testable:

- ``predicted_account_ids`` — turn a ``Matches`` result into the set of
  account ids the matcher is *claiming* (exact, optionally plus the
  "possibly … — verify" close tier).
- ``evaluate`` — aggregate precision / recall / F1 over a list of
  ``(predicted, gold)`` pairs.

A runnable report against a small labelled dataset lives in
``scripts/eval_matching.py``. Precision answers "when we flag an existing
customer, how often are we right?"; recall answers "of the real existing
customers, how many did we catch?".
"""

from __future__ import annotations

from dataclasses import dataclass

from sales_lead_research.matching.store import Matches


@dataclass(frozen=True)
class Metrics:
    """Aggregate match-quality metrics over a labelled set."""

    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float
    recall: float
    f1: float


def predicted_account_ids(matches: Matches, *, include_close: bool) -> set[str]:
    """Return the account ids the matcher predicts as customers.

    Exact matches are always included. The close ("possibly … — verify")
    tier is included only when *include_close* is true, which lets the
    report show the strict-vs-lenient precision/recall trade-off.
    """
    predicted = set(matches.exact)
    if include_close:
        predicted |= set(matches.close)
    return predicted


def evaluate(cases: list[tuple[set[str], set[str]]]) -> Metrics:
    """Aggregate precision / recall / F1 over ``(predicted, gold)`` pairs.

    Each case is one looked-up subsidiary: *predicted* is the set of
    account ids the matcher returned, *gold* is the hand-labelled set of
    account ids that are genuinely the same company. Conventions for the
    degenerate cases: precision is 1.0 when nothing was predicted, recall
    is 1.0 when there were no real matches to find, and F1 is 0.0 when
    precision and recall are both 0.
    """
    tp = fp = fn = 0
    for predicted, gold in cases:
        tp += len(predicted & gold)
        fp += len(predicted - gold)
        fn += len(gold - predicted)

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return Metrics(
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1=round(f1, 4),
    )
