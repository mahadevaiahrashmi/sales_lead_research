# agent-notes: { ctx: "issue #1 acceptance tests for run_repl chat loop", deps: ["src/sales_lead_research/cli.py"], state: active, last: "sato@2026-04-15b" }
"""Acceptance tests for issue #1: CLI chat loop with placeholder hierarchy.

Strategy: drive ``run_repl`` with an iterator of input lines and a StringIO
sink, then assert on the rendered text. No subprocess, no stdin patching.
"""

import io

import pytest

from sales_lead_research.cli import run_repl


def _run(lines):
    out = io.StringIO()
    run_repl(iter(lines), out)
    return out.getvalue()


class TestCompanyLookupRendersPlaceholderTree:
    def test_company_name_appears_in_output(self):
        output = _run(["Acme Corp", "exit"])
        assert "Acme Corp" in output

    def test_output_contains_tree_structure(self):
        # rich tree rendering uses box-drawing chars; assert at least one
        # recognizable tree glyph appears so we know *some* tree was rendered
        # without locking in exact formatting.
        output = _run(["Acme Corp", "exit"])
        tree_glyphs = ("├", "└", "│")
        assert any(glyph in output for glyph in tree_glyphs), (
            f"expected tree glyphs in output, got: {output!r}"
        )

    def test_multiple_companies_each_render(self):
        output = _run(["Acme Corp", "Globex", "exit"])
        assert "Acme Corp" in output
        assert "Globex" in output


class TestExitCommand:
    def test_exit_terminates_cleanly(self):
        # Should not raise; should return normally.
        _run(["exit"])

    def test_input_after_exit_is_not_processed(self):
        output = _run(["exit", "ShouldNotAppear"])
        assert "ShouldNotAppear" not in output


class TestEofTerminatesCleanly:
    def test_empty_iterator_returns_without_error(self):
        _run([])

    def test_iterator_exhaustion_after_query_returns_cleanly(self):
        # No explicit "exit" — loop must terminate when input runs out.
        output = _run(["Acme Corp"])
        assert "Acme Corp" in output

    def test_real_textio_eof_terminates_cleanly(self):
        # Exercise real TextIO line-iteration semantics (not a list iterator):
        # a StringIO reaching EOF must end the loop without an explicit "exit".
        out = io.StringIO()
        run_repl(io.StringIO("Acme Corp\n"), out)
        assert "Acme Corp" in out.getvalue()


class TestEmptyInputHandledGracefully:
    def test_blank_line_does_not_crash(self):
        _run(["", "exit"])

    def test_blank_line_produces_no_tree(self):
        # A blank line followed by exit: no company was named, so no tree
        # glyphs should appear in the output.
        output = _run(["", "exit"])
        tree_glyphs = ("├", "└", "│")
        assert not any(glyph in output for glyph in tree_glyphs), (
            f"blank input should not render a tree, got: {output!r}"
        )

    def test_whitespace_only_input_treated_as_empty(self):
        output = _run(["   ", "exit"])
        tree_glyphs = ("├", "└", "│")
        assert not any(glyph in output for glyph in tree_glyphs)

    def test_blank_then_real_query_still_works(self):
        output = _run(["", "Acme Corp", "exit"])
        assert "Acme Corp" in output
