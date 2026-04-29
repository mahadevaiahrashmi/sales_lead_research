# agent-notes: { ctx: "Wave 3.1 / issue #18 tests for chat/intent.py — parse() + Intent dataclass + regression pins", deps: ["src/sales_lead_research/chat/intent.py", "docs/adrs/0003-sales-assistant-chat-architecture.md"], state: active, last: "tara@2026-04-28" }
"""Red-phase tests for ``sales_lead_research.chat.intent``.

Scope: the natural-language intent parser specified in ADR-0003 §2.
The parser replaces the existing ``cli.extract_company_name`` shim
with a typed ``Intent`` value-object that the chat loop branches on.

Public API the tests pin down:

- ``Intent`` — frozen dataclass with two fields:
  - ``kind``: one of ``{"lookup", "exit", "empty", "unknown"}``.
  - ``company_name``: the extracted company string for ``lookup``,
    ``None`` for every other kind.
- ``parse(query: str) -> Intent`` — the single entry point.

The ``chat`` subpackage does not yet exist; until Sato writes it,
every case here is expected to error at import time
(``ModuleNotFoundError: No module named 'sales_lead_research.chat'``).
That is the correct red-phase signal.

Coverage floor: every shape ``cli.extract_company_name`` already
handles (see ``tests/test_nlq.py`` — 22 cases) is ported here, plus
the four new ``kind`` outcomes the existing parser cannot represent
(``empty``, ``exit``, ``unknown``, and a frozen ``Intent`` value).

The "bare name" vs "unknown chit-chat" boundary is the new
judgement call. The rule locked in by these tests is documented in
``TestParseUnknown.__doc__``: a fixed set of greeting/help/question
tokens (when not part of a phrasing pattern match) lands as
``unknown``; anything else with at least one alphanumeric token
falls through as a bare-name lookup.
"""

from __future__ import annotations

import dataclasses

import pytest

from sales_lead_research.chat.intent import (  # type: ignore[import-not-found]
    Intent,
    parse,
)


# ---------------------------------------------------------------------------
# TestParseEmpty
# ---------------------------------------------------------------------------


class TestParseEmpty:
    """Empty or whitespace-only input parses to ``Intent("empty", None)``.

    The chat loop uses this kind to silently skip blank lines without
    rendering an "I don't understand" banner."""

    @pytest.mark.parametrize(
        "query",
        [
            pytest.param("", id="empty-string"),
            pytest.param(" ", id="single-space"),
            pytest.param("   ", id="multiple-spaces"),
            pytest.param("\n", id="newline-only"),
            pytest.param("\t", id="tab-only"),
            pytest.param("\t  ", id="tab-then-spaces"),
            pytest.param("  \n  ", id="spaces-newline-spaces"),
            pytest.param("\r\n", id="crlf"),
        ],
    )
    def test_empty_or_whitespace(self, query: str) -> None:
        assert parse(query) == Intent(kind="empty", company_name=None)


# ---------------------------------------------------------------------------
# TestParseExit
# ---------------------------------------------------------------------------


class TestParseExit:
    """The literal token ``exit`` (after ``.strip()``, case-insensitive)
    parses to ``Intent("exit", None)``.

    The existing CLI in ``cli.py:95`` matches lowercase ``"exit"`` after
    ``.strip()``. The new parser keeps that behaviour and additionally
    treats any case variant as exit, since ``Intent`` is consumed by a
    chat loop where users type freely. ``"quit"`` is *not* an alias —
    we are consolidating the existing behaviour, not extending it.
    A line like ``"exit now"`` is natural language, not a bare exit."""

    @pytest.mark.parametrize(
        "query",
        [
            pytest.param("exit", id="bare-lowercase"),
            pytest.param("EXIT", id="all-caps"),
            pytest.param("Exit", id="title-case"),
            pytest.param("eXiT", id="mixed-case"),
            pytest.param("  exit  ", id="surrounding-whitespace"),
            pytest.param("\texit\n", id="tab-and-newline-around"),
            pytest.param("  EXIT  ", id="caps-with-whitespace"),
        ],
    )
    def test_exit_variants(self, query: str) -> None:
        assert parse(query) == Intent(kind="exit", company_name=None)

    def test_quit_is_not_exit(self) -> None:
        """``quit`` is not an alias for ``exit``. Existing behaviour is
        ``exit``-only and we are consolidating, not extending."""
        result = parse("quit")
        assert result.kind != "exit"

    def test_exit_now_is_not_exit(self) -> None:
        """``exit now`` begins with the exit token but has trailing
        words; it is natural-language input, not a bare exit. Per the
        unknown-rule documented on ``TestParseUnknown``, it lands as
        ``unknown`` (no phrasing pattern matches it)."""
        result = parse("exit now")
        assert result.kind != "exit"


# ---------------------------------------------------------------------------
# TestParseLookup
# ---------------------------------------------------------------------------


class TestParseLookup:
    """A query that resolves to a company name parses to
    ``Intent("lookup", "<name>")``. The five phrasing patterns from
    the existing ``cli._NL_PATTERNS`` block are all supported, plus
    bare-name pass-through. Trailing ``?``/``!`` are stripped from
    the extracted name; an interior period (``Apple Inc.``) is kept.
    Phrasing keywords match case-insensitively; the *name* is
    returned in the case the user typed it."""

    # --- Bare-name pass-through ----------------------------------------

    @pytest.mark.parametrize(
        ("query", "expected_name"),
        [
            pytest.param("Apple", "Apple", id="bare-apple"),
            pytest.param("AAPL", "AAPL", id="bare-ticker"),
            pytest.param("FedEx Corp", "FedEx Corp", id="bare-multi-word"),
            pytest.param(
                "Apple Inc.",
                "Apple Inc.",
                id="bare-with-trailing-period-kept",
            ),
            pytest.param(
                "  FedEx  ",
                "FedEx",
                id="bare-strips-surrounding-whitespace",
            ),
            pytest.param(
                "Berkshire Hathaway",
                "Berkshire Hathaway",
                id="bare-two-word-name",
            ),
            pytest.param(
                "Apple?",
                "Apple",
                id="bare-strips-trailing-question-mark",
            ),
            pytest.param(
                "Apple!",
                "Apple",
                id="bare-strips-trailing-exclamation",
            ),
        ],
    )
    def test_bare_name(self, query: str, expected_name: str) -> None:
        assert parse(query) == Intent(kind="lookup", company_name=expected_name)

    # --- Pattern 1: show / list / get / find / look up / fetch / pull / display

    @pytest.mark.parametrize(
        ("query", "expected_name"),
        [
            pytest.param(
                "show me Apple's subsidiaries",
                "Apple",
                id="show-me-apples-subsidiaries",
            ),
            pytest.param(
                "show FedEx subsidiaries",
                "FedEx",
                id="show-fedex-subsidiaries",
            ),
            pytest.param(
                "list Microsoft's subsidiaries",
                "Microsoft",
                id="list-microsofts-subsidiaries",
            ),
            pytest.param(
                "find Apple Inc subsidiaries",
                "Apple Inc",
                id="find-apple-inc-subsidiaries",
            ),
            pytest.param(
                "get Apple's corporate structure",
                "Apple",
                id="get-apples-corporate-structure",
            ),
            pytest.param(
                "look up Microsoft Corp",
                "Microsoft Corp",
                id="look-up-microsoft-corp",
            ),
            pytest.param(
                "fetch Apple's hierarchy",
                "Apple",
                id="fetch-apples-hierarchy",
            ),
            pytest.param(
                "pull FedEx corporate tree",
                "FedEx",
                id="pull-fedex-corporate-tree",
            ),
            pytest.param(
                "display Apple's sub companies",
                "Apple",
                id="display-apples-sub-companies",
            ),
            pytest.param(
                "show me the Apple's child companies",
                "Apple",
                id="show-me-the-apple-child-companies",
            ),
        ],
    )
    def test_show_list_get_patterns(
        self, query: str, expected_name: str
    ) -> None:
        assert parse(query) == Intent(kind="lookup", company_name=expected_name)

    # --- Pattern 2: what / which (are | companies do(es)) ... ----------

    @pytest.mark.parametrize(
        ("query", "expected_name"),
        [
            pytest.param(
                "what are Apple's subsidiaries",
                "Apple",
                id="what-are-apples-subsidiaries",
            ),
            pytest.param(
                "what companies does FedEx own",
                "FedEx",
                id="what-companies-does-fedex-own",
            ),
            pytest.param(
                "which companies do Microsoft have",
                "Microsoft",
                id="which-companies-do-microsoft-have",
            ),
            pytest.param(
                "what companies does FedEx own?",
                "FedEx",
                id="what-companies-does-fedex-own-with-question-mark",
            ),
        ],
    )
    def test_what_which_patterns(
        self, query: str, expected_name: str
    ) -> None:
        assert parse(query) == Intent(kind="lookup", company_name=expected_name)

    # --- Pattern 3: who (does | do | are) ... own | subsidiaries -------

    @pytest.mark.parametrize(
        ("query", "expected_name"),
        [
            pytest.param(
                "who does Microsoft own",
                "Microsoft",
                id="who-does-microsoft-own",
            ),
            pytest.param(
                "who are Apple's subsidiaries",
                "Apple",
                id="who-are-apples-subsidiaries",
            ),
        ],
    )
    def test_who_patterns(self, query: str, expected_name: str) -> None:
        assert parse(query) == Intent(kind="lookup", company_name=expected_name)

    # --- Pattern 4: subsidiaries | hierarchy | ... of | for | under X ---

    @pytest.mark.parametrize(
        ("query", "expected_name"),
        [
            pytest.param(
                "subsidiaries of Apple",
                "Apple",
                id="subsidiaries-of-apple",
            ),
            pytest.param(
                "hierarchy of FedEx Corp",
                "FedEx Corp",
                id="hierarchy-of-fedex-corp",
            ),
            pytest.param(
                "corporate structure of Microsoft",
                "Microsoft",
                id="corporate-structure-of-microsoft",
            ),
            pytest.param(
                "corporate tree of Apple",
                "Apple",
                id="corporate-tree-of-apple",
            ),
            pytest.param(
                "sub companies of FedEx",
                "FedEx",
                id="sub-companies-of-fedex",
            ),
            pytest.param(
                "subsidiaries for Apple",
                "Apple",
                id="subsidiaries-for-apple",
            ),
            pytest.param(
                "subsidiaries under Microsoft",
                "Microsoft",
                id="subsidiaries-under-microsoft",
            ),
            pytest.param(
                "subsidiaries of the Apple",
                "Apple",
                id="subsidiaries-of-the-apple",
            ),
        ],
    )
    def test_subsidiaries_of_patterns(
        self, query: str, expected_name: str
    ) -> None:
        assert parse(query) == Intent(kind="lookup", company_name=expected_name)

    # --- Pattern 5: tell me about | search | look up | info on/about/for

    @pytest.mark.parametrize(
        ("query", "expected_name"),
        [
            pytest.param(
                "tell me about Apple",
                "Apple",
                id="tell-me-about-apple",
            ),
            pytest.param(
                "search for FedEx",
                "FedEx",
                id="search-for-fedex",
            ),
            pytest.param(
                "search Microsoft",
                "Microsoft",
                id="search-microsoft-no-for",
            ),
            pytest.param(
                "info on Apple",
                "Apple",
                id="info-on-apple",
            ),
            pytest.param(
                "info about FedEx",
                "FedEx",
                id="info-about-fedex",
            ),
            pytest.param(
                "info for Microsoft",
                "Microsoft",
                id="info-for-microsoft",
            ),
        ],
    )
    def test_tell_me_about_patterns(
        self, query: str, expected_name: str
    ) -> None:
        assert parse(query) == Intent(kind="lookup", company_name=expected_name)

    # --- Pattern 5 widening regression pin (T-I2 / V-I2) ---------------

    @pytest.mark.parametrize(
        ("query", "expected_name"),
        [
            pytest.param("search the database", "database",
                         id="search-the-database-widened"),
            pytest.param("search me", "me", id="search-me-widened"),
        ],
    )
    def test_search_widening_v1(self, query: str, expected_name: str) -> None:
        """v1 deliberately widens pattern 5 to make 'search FedEx' (no 'for')
        work. Side effect: 'search the database' captures 'database', 'search
        me' captures 'me'. Pinning these as v1 behaviour — if a future
        refactor tightens pattern 5 back to require 'for', this test signals
        the widening was load-bearing for these (admittedly nonsense) shapes
        and the chat layer's 'no match found' message is the safety net."""
        assert parse(query) == Intent(kind="lookup", company_name=expected_name)

    # --- Natural-language exit asymmetry (T-I4) ------------------------

    def test_please_exit_is_lookup_not_exit(self) -> None:
        """v1 only treats the bare 'exit' token as the exit command.
        'please exit' falls through to bare-name lookup with the whole
        string. Locked as v1 behaviour — discovery's 'no match' is the
        safety net. v2 may add an exit-phrase set."""
        assert parse("please exit") == Intent(
            kind="lookup", company_name="please exit"
        )

    # --- Pattern-precedence over unknown-token (T-N8) ------------------

    @pytest.mark.parametrize(
        ("query", "expected_name"),
        [
            pytest.param("what are Apple's subsidiaries", "Apple", id="what-pattern-2"),
            pytest.param("who does Microsoft own", "Microsoft", id="who-pattern-3"),
            pytest.param("which companies do FedEx have", "FedEx", id="which-pattern-2"),
        ],
    )
    def test_question_word_in_pattern_is_lookup(
        self, query: str, expected_name: str
    ) -> None:
        """Phrasing patterns must be tried before the unknown-token check.
        Otherwise queries that legitimately start with what/who/which would
        be misclassified as unknown chit-chat."""
        result = parse(query)
        assert result.kind == "lookup"
        assert result.company_name == expected_name

    # --- Punctuation / casing edge cases -------------------------------

    def test_preserves_period_in_name(self) -> None:
        """Interior period (``Apple Inc.``) is part of the company
        name and must survive — only trailing ``?``/``!`` are
        stripped."""
        assert parse("Apple Inc.") == Intent(
            kind="lookup", company_name="Apple Inc."
        )

    def test_strips_question_mark_from_bare_name(self) -> None:
        assert parse("Apple?") == Intent(kind="lookup", company_name="Apple")

    def test_strips_exclamation_from_bare_name(self) -> None:
        assert parse("Apple!") == Intent(kind="lookup", company_name="Apple")

    def test_nl_with_question_mark_strips_from_name(self) -> None:
        """``what companies does FedEx own?`` — the ``?`` is on the
        end of the *extracted name*, not a separate token, and must
        be stripped."""
        assert parse("what companies does FedEx own?") == Intent(
            kind="lookup", company_name="FedEx"
        )

    def test_phrasing_is_case_insensitive_name_preserves_case(self) -> None:
        """The *phrasing* (SHOW / SUBSIDIARIES) matches case-insensitively
        but the *extracted name* keeps the user's casing. This mirrors
        the existing behaviour pinned in ``test_nlq.py:86``."""
        assert parse("SHOW ME apple's SUBSIDIARIES") == Intent(
            kind="lookup", company_name="apple"
        )


# ---------------------------------------------------------------------------
# TestParseUnknown
# ---------------------------------------------------------------------------


class TestParseUnknown:
    """Chat-style queries that don't match any phrasing pattern parse
    to ``Intent("unknown", None)``.

    Per ADR-0003 §2: "no silent failures, no hallucinated intent."
    The existing ``extract_company_name`` falls through to "treat
    anything as a company name", which the ADR explicitly rejects.

    The rule locked in here:

    A query is ``unknown`` when, after stripping whitespace and
    failing every phrasing pattern, its first whitespace-token
    (lowercased, with trailing ``?`` removed) is a known
    greeting/help/question word:

        {hello, hi, hey, help, what, how, why, when, where, who}

    plus the bare token ``?``. Anything else with at least one
    alphanumeric token is a bare-name lookup.

    Greeting/question words that *are* part of a phrasing pattern
    match (e.g. ``what are Apple's subsidiaries``) are still lookups
    — the unknown-token list is only consulted *after* every
    phrasing pattern has failed."""

    @pytest.mark.parametrize(
        "query",
        [
            # --- Greetings / chit-chat ---
            pytest.param("hello", id="hello"),
            pytest.param("hi", id="hi"),
            pytest.param("hey there", id="hey-there"),
            pytest.param("Hello", id="hello-capitalized"),
            pytest.param("HI", id="hi-all-caps"),
            # --- Questions that don't match supported patterns ---
            pytest.param("what time is it", id="what-time-is-it"),
            pytest.param("how are you", id="how-are-you"),
            pytest.param("why is the sky blue", id="why-is-the-sky-blue"),
            pytest.param("when is the meeting", id="when-is-the-meeting"),
            pytest.param("where is the data", id="where-is-the-data"),
            pytest.param("who are you", id="who-are-you"),
            # --- Imperatives that don't match ---
            # The existing pattern requires "tell me about" — "tell me a
            # joke" lacks the "about" anchor and must NOT be misclassified
            # as a lookup for "a joke".
            pytest.param("tell me a joke", id="tell-me-a-joke-not-about"),
            # --- Help / meta ---
            pytest.param("help", id="help"),
            pytest.param("what can you do", id="what-can-you-do"),
            pytest.param("?", id="bare-question-mark"),
            # --- exit-with-trailing-words is unknown, not exit ---
            pytest.param("exit now", id="exit-now"),
        ],
    )
    def test_unknown_inputs(self, query: str) -> None:
        assert parse(query) == Intent(kind="unknown", company_name=None)

    @pytest.mark.parametrize(
        "query",
        [
            pytest.param("hello", id="hello"),
            pytest.param("hey there", id="hey-there"),
            pytest.param("how are you", id="how-are-you"),
            pytest.param("help", id="help"),
        ],
    )
    def test_unknown_company_name_is_none(self, query: str) -> None:
        """``unknown`` carries no extracted name — the chat layer relies
        on ``company_name is None`` as the don't-render-a-tree signal."""
        assert parse(query).company_name is None

    def test_question_word_inside_pattern_is_still_lookup(self) -> None:
        """``what are Apple's subsidiaries`` starts with ``what`` but
        matches phrasing pattern 2; the unknown-token list must not
        short-circuit a successful pattern match. (Sanity case — the
        full overlap matrix is in
        ``TestParseLookup.test_question_word_in_pattern_is_lookup``.)"""
        result = parse("what are Apple's subsidiaries")
        assert result.kind == "lookup"
        assert result.company_name == "Apple"

    @pytest.mark.parametrize(
        "query",
        [
            pytest.param("!!!", id="exclamation-only"),
            pytest.param("...", id="ellipsis-only"),
            pytest.param("?!", id="question-and-bang"),
            pytest.param("---", id="dashes-only"),
            pytest.param("***", id="asterisks-only"),
            pytest.param("@@@", id="at-signs-only"),
        ],
    )
    def test_punctuation_only_is_unknown(self, query: str) -> None:
        """Pure-punctuation input must NOT cascade into discovery as a
        company-name search — a salesperson typo should not cost an
        SEC round-trip."""
        assert parse(query) == Intent(kind="unknown", company_name=None)

    def test_tell_me_x_subsidiaries_is_unknown_v1(self) -> None:
        """'tell me FedEx subsidiaries' lacks the 'about' anchor required
        by pattern 5 and lacks any 'show/list/get' verb required by
        pattern 1, so it falls through to the unknown-token check where
        'tell' is in _UNKNOWN_TOKENS. Locked as unknown for v1; v2 may
        add a sixth pattern. Pat-confirmed scope decision."""
        assert parse("tell me FedEx subsidiaries") == Intent(
            kind="unknown", company_name=None
        )

    def test_exit_please_is_unknown(self) -> None:
        """Mirror of ``test_please_exit_is_lookup_not_exit`` in
        ``TestParseLookup``: 'exit please' hits the 'exit' token in the
        unknown-token set, so it lands as unknown rather than exit. The
        asymmetry vs 'please exit' is deliberate v1 simplicity — both
        behaviours are pinned so neither drifts silently."""
        assert parse("exit please") == Intent(
            kind="unknown", company_name=None
        )


# ---------------------------------------------------------------------------
# TestParseLengthCap
# ---------------------------------------------------------------------------


class TestParseLengthCap:
    """Inputs over 1024 characters short-circuit to ``unknown`` before
    any regex runs. Defends against pathological backtracking and
    pasted-megabyte hostile input (Pierrot, ADR-0003 Security)."""

    def test_at_cap_still_runs_normally(self) -> None:
        """Exactly 1024 chars is allowed. We pad with spaces around a
        bare-name 'Apple' so the parser still recognises it."""
        query = "Apple" + " " * (1024 - 5)
        assert len(query) == 1024
        result = parse(query)
        assert result.kind == "lookup"
        assert result.company_name == "Apple"

    def test_one_over_cap_is_unknown(self) -> None:
        query = "Apple" + " " * (1025 - 5)
        assert len(query) == 1025
        assert parse(query) == Intent(kind="unknown", company_name=None)

    def test_far_over_cap_is_unknown(self) -> None:
        query = "a" * 100_000
        assert parse(query) == Intent(kind="unknown", company_name=None)

    def test_over_cap_phrasing_pattern_does_not_run(self) -> None:
        """A phrasing-pattern query that would otherwise match must
        also short-circuit to unknown when oversize — proves the cap
        runs before the regex loop."""
        query = "search for FedEx" + " " * 1100
        assert parse(query) == Intent(kind="unknown", company_name=None)


# ---------------------------------------------------------------------------
# TestIntent — dataclass invariants
# ---------------------------------------------------------------------------


class TestIntent:
    """``Intent`` is the value-object the chat layer branches on. Pin
    down its observable shape: two named fields, frozen, equal by
    value, and the four ``kind`` literals."""

    def test_construction_with_keyword_args(self) -> None:
        i = Intent(kind="lookup", company_name="Apple")
        assert i.kind == "lookup"
        assert i.company_name == "Apple"

    def test_construction_with_positional_args(self) -> None:
        """Field order is ``(kind, company_name)`` — positional
        construction is what the parser implementation will use."""
        i = Intent("lookup", "Apple")
        assert i.kind == "lookup"
        assert i.company_name == "Apple"

    def test_company_name_can_be_none(self) -> None:
        """``empty``, ``exit``, and ``unknown`` carry ``None``."""
        i = Intent(kind="empty", company_name=None)
        assert i.company_name is None

    def test_equality_by_value(self) -> None:
        """Frozen dataclasses compare structurally; this lets us write
        ``assert parse(q) == Intent("lookup", "Apple")`` instead of
        deep-asserting field by field."""
        a = Intent(kind="lookup", company_name="Apple")
        b = Intent(kind="lookup", company_name="Apple")
        assert a == b

    def test_inequality_by_kind(self) -> None:
        a = Intent(kind="lookup", company_name=None)
        b = Intent(kind="unknown", company_name=None)
        assert a != b

    def test_inequality_by_company_name(self) -> None:
        a = Intent(kind="lookup", company_name="Apple")
        b = Intent(kind="lookup", company_name="Microsoft")
        assert a != b

    def test_is_frozen(self) -> None:
        """``frozen=True`` is required so the value-object is hashable
        and not mutated downstream. Frozen dataclasses raise
        ``dataclasses.FrozenInstanceError`` on attribute assignment."""
        i = Intent(kind="lookup", company_name="Apple")
        with pytest.raises(dataclasses.FrozenInstanceError):
            i.kind = "exit"  # type: ignore[misc]

    def test_is_frozen_company_name(self) -> None:
        i = Intent(kind="lookup", company_name="Apple")
        with pytest.raises(dataclasses.FrozenInstanceError):
            i.company_name = "Microsoft"  # type: ignore[misc]

    @pytest.mark.parametrize(
        "kind",
        [
            pytest.param("lookup", id="lookup"),
            pytest.param("exit", id="exit"),
            pytest.param("empty", id="empty"),
            pytest.param("unknown", id="unknown"),
        ],
    )
    def test_all_four_kind_literals_are_constructible(self, kind: str) -> None:
        """At runtime the ``Literal`` type is just a string; verify
        every documented value is accepted by the constructor."""
        i = Intent(kind=kind, company_name=None)  # type: ignore[arg-type]
        assert i.kind == kind

    def test_is_hashable(self) -> None:
        """Frozen dataclasses are hashable. The chat layer (Wave 3.2)
        may want to dedupe Intents in a set; pin the property explicitly."""
        a = Intent(kind="lookup", company_name="Apple")
        b = Intent(kind="lookup", company_name="Apple")
        assert {a, b} == {a}

    def test_hash_differs_when_kind_differs(self) -> None:
        a = Intent(kind="lookup", company_name=None)
        b = Intent(kind="unknown", company_name=None)
        assert hash(a) != hash(b)
