# agent-notes: { ctx: "Wave 2.1 / issue #15 red-phase tests for matching/names.py (normalise_name, jaccard_similarity, classify_match)", deps: ["src/sales_lead_research/matching/names.py", "docs/adrs/0003-sales-assistant-chat-architecture.md"], state: active, last: "tara@2026-04-28" }
"""Red-phase tests for ``sales_lead_research.matching.names``.

Scope: the three pure string-matching functions specified in
ADR-0003 §4 — ``normalise_name``, ``jaccard_similarity``, and
``classify_match``. No I/O, no mocking; every case is a pure
input -> output assertion.

The module under test does not yet exist. Until Sato writes it,
every case here is expected to error at import time
(``ModuleNotFoundError: No module named 'sales_lead_research.matching'``).
That is the correct red-phase signal.

Canonical cases (per Wave 2.1 brief and ADR-0003 §4):

1. DHL parens-country -> exact after normalisation.
2. FedEx token-superset -> close-match (Jaccard exactly 0.8).
3. Apple Inc. vs Apple -> exact.
4. Acme Corp vs Acme Holdings -> none.
"""

from __future__ import annotations

import pytest

from sales_lead_research.matching.names import (
    classify_match,
    jaccard_similarity,
    normalise_name,
)


# ---------------------------------------------------------------------------
# normalise_name
# ---------------------------------------------------------------------------


class TestNormaliseName:
    """Lowercase, strip trailing legal suffix, collapse whitespace,
    drop trailing/leading punctuation, drop parenthesis characters
    (keeping the content)."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # --- canonical cases ---
            pytest.param(
                "DHL Express (Portugal) Lda.",
                "dhl express portugal",
                id="canonical-dhl-parens-country",
            ),
            pytest.param(
                "Apple Inc.",
                "apple",
                id="canonical-apple-strips-inc-dot",
            ),
            pytest.param(
                "Apple",
                "apple",
                id="canonical-apple-bare",
            ),
            # --- per-suffix coverage from ADR-0003 §4 (one row per suffix) ---
            pytest.param("Foo Inc", "foo", id="suffix-inc"),
            pytest.param("Foo Inc.", "foo", id="suffix-inc-dot"),
            pytest.param("Foo Incorporated", "foo", id="suffix-incorporated"),
            pytest.param("Foo Ltd", "foo", id="suffix-ltd"),
            pytest.param("Foo Ltd.", "foo", id="suffix-ltd-dot"),
            pytest.param("Foo Limited", "foo", id="suffix-limited"),
            pytest.param("Foo GmbH", "foo", id="suffix-gmbh"),
            pytest.param("Foo Lda", "foo", id="suffix-lda"),
            pytest.param("Foo Lda.", "foo", id="suffix-lda-dot"),
            pytest.param("Foo SAS", "foo", id="suffix-sas"),
            pytest.param("Foo S.A.", "foo", id="suffix-s-a-dot"),
            pytest.param("Foo S.A", "foo", id="suffix-s-a"),
            pytest.param("Foo Co", "foo", id="suffix-co"),
            pytest.param("Foo Co.", "foo", id="suffix-co-dot"),
            pytest.param("Foo Corp", "foo", id="suffix-corp"),
            pytest.param("Foo Corp.", "foo", id="suffix-corp-dot"),
            pytest.param("Foo Corporation", "foo", id="suffix-corporation"),
            pytest.param("Foo LLC", "foo", id="suffix-llc"),
            pytest.param("Foo LLC.", "foo", id="suffix-llc-dot"),
            pytest.param("Foo PLC", "foo", id="suffix-plc"),
            pytest.param("Foo AG", "foo", id="suffix-ag"),
            pytest.param("Foo N.V.", "foo", id="suffix-n-v"),
            pytest.param("Foo NV", "foo", id="suffix-nv"),
            pytest.param("Foo B.V.", "foo", id="suffix-b-v"),
            pytest.param("Foo BV", "foo", id="suffix-bv"),
            pytest.param("Foo SARL", "foo", id="suffix-sarl"),
            pytest.param("Foo S.p.A.", "foo", id="suffix-s-p-a"),
            pytest.param("Foo SpA", "foo", id="suffix-spa"),
            pytest.param("Foo S.r.l.", "foo", id="suffix-s-r-l"),
            pytest.param("Foo SRL", "foo", id="suffix-srl"),
            pytest.param("Foo Pty", "foo", id="suffix-pty"),
            pytest.param("Foo Oy", "foo", id="suffix-oy"),
            pytest.param("Foo Oyj", "foo", id="suffix-oyj"),
            # --- whitespace handling ---
            pytest.param(
                "  Apple   Inc.  ",
                "apple",
                id="leading-trailing-whitespace-stripped",
            ),
            pytest.param(
                "DHL\tExpress\nPortugal",
                "dhl express portugal",
                id="internal-tabs-and-newlines-collapsed",
            ),
            pytest.param(
                "DHL    Express    Portugal",
                "dhl express portugal",
                id="multiple-spaces-collapsed",
            ),
            # --- parenthesis handling: bracket chars stripped, content kept ---
            pytest.param(
                "FedEx Express (France) SAS",
                "fedex express france",
                id="parens-around-country-kept-content",
            ),
            # --- punctuation trimming ---
            pytest.param(
                "Apple, Inc.",
                "apple",
                id="comma-before-suffix",
            ),
            pytest.param(
                "...Apple Inc...",
                "apple",
                id="leading-trailing-dots-stripped",
            ),
            # --- embedded suffix-like substring is NOT stripped ---
            # "Incandescent" begins with "Inc" but is a real word; it
            # must survive normalisation. Suffix stripping is a trailing
            # token rule, not a substring rule.
            pytest.param(
                "Incandescent Ltd",
                "incandescent",
                id="embedded-inc-prefix-not-stripped",
            ),
            pytest.param(
                "Incorporated Holdings",
                "incorporated holdings",
                id="incorporated-as-first-word-not-stripped",
            ),
            # A suffix-shaped token at the *start* must survive — the
            # rule only fires on trailing tokens. Without this row, an
            # implementation that filtered suffixes globally would still
            # pass the rest of the suite.
            pytest.param(
                "Inc Magazine Ltd",
                "inc magazine",
                id="suffix-at-position-zero-kept",
            ),
            # --- multiple stacked trailing suffixes ---
            # Real-world Exhibit-21 names occasionally pile descriptors
            # ("Foo Holdings Inc Ltd."). The pop loop must iterate; a
            # single-pop implementation would leave "foo inc" or "foo ltd".
            pytest.param(
                "Foo Inc Ltd",
                "foo",
                id="multi-trailing-suffix-stripped",
            ),
            # --- suffix token with trailing edge punctuation ---
            # Pins down that punctuation glued to the suffix tail itself
            # (not just to a preceding word) is stripped before the
            # set-membership check.
            pytest.param(
                "Foo Inc,",
                "foo",
                id="suffix-with-trailing-comma-stripped",
            ),
            # --- degenerate inputs ---
            pytest.param("", "", id="empty-string"),
            # A name that is *only* a legal suffix normalises to empty.
            # Documented as desired behaviour: the input is degenerate
            # and downstream code (``classify_match``) treats two empty
            # normalised names as a no-match (Jaccard returns 0.0).
            pytest.param("Inc.", "", id="suffix-only-becomes-empty"),
            pytest.param("Ltd", "", id="bare-ltd-becomes-empty"),
        ],
    )
    def test_normalises(self, raw: str, expected: str) -> None:
        assert normalise_name(raw) == expected

    @pytest.mark.parametrize(
        "raw",
        [
            pytest.param("DHL Express (Portugal) Lda.", id="dhl-canonical"),
            pytest.param("Apple Inc.", id="apple-canonical"),
            pytest.param("FedEx Express (France) SAS", id="fedex-france"),
            pytest.param("  Foo   Bar  Inc.  ", id="messy-whitespace"),
            pytest.param("", id="empty"),
            pytest.param("Inc.", id="suffix-only"),
        ],
    )
    def test_idempotent(self, raw: str) -> None:
        """``normalise_name`` is a fixed-point: applying it twice
        returns the same value as applying it once. This guards
        against rules that only fire on the un-normalised shape
        (e.g. case-sensitive suffix lists)."""
        once = normalise_name(raw)
        twice = normalise_name(once)
        assert once == twice


# ---------------------------------------------------------------------------
# jaccard_similarity
# ---------------------------------------------------------------------------


class TestJaccardSimilarity:
    """Token-level Jaccard on whitespace-split *normalised* strings.

    Both inputs pass through ``normalise_name`` before token-set
    comparison. Empty-on-both-sides returns 0.0 (not 1.0). Empty-on-
    one-side returns 0.0. Result is in [0.0, 1.0]."""

    @pytest.mark.parametrize(
        ("a", "b", "expected"),
        [
            # --- identity after normalisation ---
            pytest.param(
                "Apple Inc.",
                "Apple",
                1.0,
                id="apple-inc-vs-apple-identical-after-normalise",
            ),
            pytest.param(
                "DHL Express (Portugal) Lda.",
                "dhl express portugal",
                1.0,
                id="dhl-canonical-identical-after-normalise",
            ),
            # --- canonical close-match shape: 4/5 token superset ---
            # Tokens: {fedex, express, freight, france}
            #     vs  {fedex, express, freight, france, services}
            # |intersection| = 4, |union| = 5, Jaccard = 0.8 exactly.
            # 'services' is not in the ADR-0003 suffix list, so it
            # survives normalisation and contributes a token.
            pytest.param(
                "FedEx Express Freight France",
                "FedEx Express Freight France Services",
                0.8,
                id="canonical-close-fedex-4-of-5",
            ),
            # --- canonical no-match shape ---
            # Tokens: {acme} vs {acme, holdings}
            # |intersection| = 1, |union| = 2, Jaccard = 0.5
            pytest.param(
                "Acme Corp",
                "Acme Holdings",
                0.5,
                id="canonical-acme-corp-vs-holdings",
            ),
            # --- complete disjoint ---
            pytest.param(
                "Apple Inc.",
                "Microsoft Corp.",
                0.0,
                id="completely-different-names",
            ),
            # --- empty handling ---
            pytest.param("", "", 0.0, id="both-empty-returns-zero-not-one"),
            pytest.param("Apple", "", 0.0, id="right-empty-returns-zero"),
            pytest.param("", "Apple", 0.0, id="left-empty-returns-zero"),
            # Both inputs degenerate to empty after suffix stripping
            # (per the "suffix-only -> empty" rule). Treat as the
            # both-empty case: 0.0, not 1.0.
            pytest.param("Inc.", "Ltd", 0.0, id="both-degenerate-to-empty"),
        ],
    )
    def test_score(self, a: str, b: str, expected: float) -> None:
        assert jaccard_similarity(a, b) == pytest.approx(expected)

    @pytest.mark.parametrize(
        ("a", "b"),
        [
            pytest.param("Apple Inc.", "Apple", id="apple-pair"),
            pytest.param(
                "DHL Express (Portugal) Lda.",
                "dhl express portugal",
                id="dhl-pair",
            ),
            pytest.param(
                "FedEx Express Freight France",
                "FedEx Express Freight France Services",
                id="fedex-close-pair",
            ),
            pytest.param("Acme Corp", "Acme Holdings", id="acme-pair"),
            pytest.param("Apple", "Microsoft", id="disjoint-pair"),
        ],
    )
    def test_symmetric(self, a: str, b: str) -> None:
        """Jaccard is symmetric: J(a, b) == J(b, a). Token-set
        operations are commutative; this guards against any future
        change that introduces left/right asymmetry (e.g. weighting
        the first argument)."""
        assert jaccard_similarity(a, b) == pytest.approx(
            jaccard_similarity(b, a)
        )

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("Apple Inc.", id="apple"),
            pytest.param("DHL Express (Portugal) Lda.", id="dhl"),
            pytest.param("FedEx Express Freight France Services", id="fedex"),
        ],
    )
    def test_self_similarity_is_one(self, value: str) -> None:
        """A non-empty name compared with itself is fully similar."""
        assert jaccard_similarity(value, value) == pytest.approx(1.0)

    @pytest.mark.parametrize(
        ("a", "b"),
        [
            pytest.param("Apple", "Microsoft", id="disjoint"),
            pytest.param("Apple Inc.", "Apple", id="identical-after-normalise"),
            pytest.param(
                "FedEx Express Freight France",
                "FedEx Express Freight France Services",
                id="superset-close",
            ),
            pytest.param("Acme Corp", "Acme Holdings", id="partial-overlap"),
            pytest.param("", "", id="both-empty"),
        ],
    )
    def test_within_unit_interval(self, a: str, b: str) -> None:
        """Result is always in [0.0, 1.0]."""
        score = jaccard_similarity(a, b)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# classify_match
# ---------------------------------------------------------------------------


class TestClassifyMatch:
    """``classify_match`` returns one of {"exact", "close", "none"}.

    - "exact": the two normalised strings are byte-for-byte equal.
    - "close": not equal but Jaccard similarity >= 0.8.
    - "none": Jaccard similarity < 0.8.
    """

    @pytest.mark.parametrize(
        ("subsidiary", "customer", "expected"),
        [
            # --- canonical case 1: DHL parens-country -> exact ---
            pytest.param(
                "DHL Express (Portugal) Lda.",
                "dhl express portugal",
                "exact",
                id="canonical-dhl-exact",
            ),
            # --- canonical case 2: FedEx 4/5 token superset -> close ---
            # Tokens after normalise:
            #   subsidiary -> {fedex, express, freight, france}
            #   customer   -> {fedex, express, freight, france, services}
            # |intersection|/|union| = 4/5 = 0.8 exactly.
            # 0.8 >= 0.8 threshold -> "close". This row also covers
            # the threshold edge (the >= comparison, not >).
            pytest.param(
                "FedEx Express Freight France",
                "FedEx Express Freight France Services",
                "close",
                id="canonical-fedex-close-at-0.8-threshold",
            ),
            # --- canonical case 3: Apple Inc. vs Apple -> exact ---
            pytest.param(
                "Apple Inc.",
                "Apple",
                "exact",
                id="canonical-apple-exact",
            ),
            # --- canonical case 4: Acme Corp vs Acme Holdings -> none ---
            # Jaccard = 1/2 = 0.5 < 0.8.
            pytest.param(
                "Acme Corp",
                "Acme Holdings",
                "none",
                id="canonical-acme-none",
            ),
            # --- threshold guard: just below 0.8 is "none" ---
            # Tokens: {dhl, express, portugal}
            #     vs  {dhl, express, portugal, international}
            # |intersection|/|union| = 3/4 = 0.75 < 0.8 -> "none".
            pytest.param(
                "DHL Express Portugal Limited",
                "DHL Express Portugal International Lda.",
                "none",
                id="threshold-just-below-0.8-is-none",
            ),
            # --- both empty after normalisation -> "none" ---
            # Two degenerate inputs are not "exact" (they would be a
            # spurious match between every pair of degenerate names);
            # Jaccard returns 0.0 by spec, so the answer is "none".
            pytest.param("", "", "none", id="both-empty-is-none"),
            pytest.param("Inc.", "Ltd", "none", id="both-degenerate-is-none"),
            # --- one side empty -> "none" ---
            pytest.param("Apple Inc.", "", "none", id="customer-empty-is-none"),
            pytest.param("", "Apple", "none", id="subsidiary-empty-is-none"),
            # --- ordering of inputs does not flip the verdict ---
            pytest.param(
                "dhl express portugal",
                "DHL Express (Portugal) Lda.",
                "exact",
                id="canonical-dhl-exact-args-swapped",
            ),
            pytest.param(
                "FedEx Express Freight France Services",
                "FedEx Express Freight France",
                "close",
                id="canonical-fedex-close-args-swapped",
            ),
        ],
    )
    def test_classification(
        self, subsidiary: str, customer: str, expected: str
    ) -> None:
        assert classify_match(subsidiary, customer) == expected
