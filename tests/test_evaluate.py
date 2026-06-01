# agent-notes: { ctx: "tests for matching/evaluate.py precision/recall/F1 helpers", deps: ["src/sales_lead_research/matching/evaluate.py", "src/sales_lead_research/matching/store.py"], state: active, last: "tara@2026-05-31" }
"""Tests for ``sales_lead_research.matching.evaluate``.

The metric maths is pure (no I/O), so these are plain value asserts. They
pin the precision / recall / F1 definitions and the predicted-id helper
that turns a Matches result into a positive-prediction set.
"""

from __future__ import annotations

from sales_lead_research.matching.evaluate import (
    Metrics,
    evaluate,
    predicted_account_ids,
)
from sales_lead_research.matching.store import Matches


class TestPredictedAccountIds:
    def test_exact_only_by_default(self) -> None:
        m = Matches(exact=("ACCT-1",), close=("ACCT-2",))
        assert predicted_account_ids(m, include_close=False) == {"ACCT-1"}

    def test_include_close_adds_close(self) -> None:
        m = Matches(exact=("ACCT-1",), close=("ACCT-2",))
        assert predicted_account_ids(m, include_close=True) == {"ACCT-1", "ACCT-2"}

    def test_no_matches_is_empty(self) -> None:
        assert predicted_account_ids(Matches((), ()), include_close=True) == set()


class TestEvaluate:
    def test_perfect_prediction_scores_one(self) -> None:
        cases = [({"A"}, {"A"}), ({"B", "C"}, {"B", "C"})]
        m = evaluate(cases)
        assert (m.precision, m.recall, m.f1) == (1.0, 1.0, 1.0)
        assert (m.true_positives, m.false_positives, m.false_negatives) == (3, 0, 0)

    def test_false_positive_lowers_precision(self) -> None:
        # Predicted B but B is not a real match -> 1 TP, 1 FP, 0 FN.
        m = evaluate([({"A", "B"}, {"A"})])
        assert m.true_positives == 1
        assert m.false_positives == 1
        assert m.precision == 0.5
        assert m.recall == 1.0

    def test_false_negative_lowers_recall(self) -> None:
        # Missed B -> 1 TP, 0 FP, 1 FN.
        m = evaluate([({"A"}, {"A", "B"})])
        assert m.false_negatives == 1
        assert m.precision == 1.0
        assert m.recall == 0.5

    def test_f1_is_harmonic_mean(self) -> None:
        # precision 0.5, recall 1.0 -> F1 = 2*0.5*1/(1.5) = 0.6667
        m = evaluate([({"A", "B"}, {"A"})])
        assert m.f1 == round(2 * 0.5 * 1.0 / 1.5, 4)

    def test_empty_cases_are_defined(self) -> None:
        # No predictions and no gold: precision/recall default to 1.0, F1 1.0.
        m = evaluate([(set(), set())])
        assert (m.precision, m.recall, m.f1) == (1.0, 1.0, 1.0)

    def test_all_missed_is_zero_recall(self) -> None:
        m = evaluate([(set(), {"A"})])
        assert m.recall == 0.0
        assert m.f1 == 0.0
