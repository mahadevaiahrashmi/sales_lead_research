# agent-notes: { ctx: "issue #1 + #3 acceptance tests for run_repl chat loop", deps: ["src/sales_lead_research/cli.py", "src/sales_lead_research/edgar.py", "tests/fixtures/edgar/"], state: active, last: "tara@2026-04-16" }
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


# ---------------------------------------------------------------------------
# Issue #3: EDGAR integration tests (fuzzy match, gates, tree, CSV)
# ---------------------------------------------------------------------------

import csv
from pathlib import Path

import httpx

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _issue3_mock_handler(request: httpx.Request) -> httpx.Response:
    """Mock transport serving all fixtures needed for the full CLI flow."""
    url = str(request.url)

    if url == "https://www.sec.gov/files/company_tickers.json":
        return httpx.Response(200, content=_fixture("company_tickers.json"))

    if url == "https://data.sec.gov/submissions/CIK0001048911.json":
        return httpx.Response(200, content=_fixture("CIK0001048911.json"))

    if url == "https://data.sec.gov/submissions/CIK0001048912.json":
        # FEDEX GROUND INC - reuse FedEx CIK data for simplicity
        return httpx.Response(200, content=_fixture("CIK0001048911.json"))

    if url == "https://data.sec.gov/submissions/CIK0000320193.json":
        return httpx.Response(200, content=_fixture("CIK0000320193.json"))

    if "000104891124000045/0001048911-24-000045-index.htm" in url:
        return httpx.Response(200, content=_fixture("fedex_10k_filing_index.html"))

    if "fdx-20240531ex211.htm" in url:
        return httpx.Response(200, content=_fixture("fedex_exhibit_21.html"))

    if "000032019324000123/0000320193-24-000123-index.htm" in url:
        return httpx.Response(200, content=_fixture("apple_10k_filing_index.html"))

    if "aapl-20240928ex211.htm" in url:
        return httpx.Response(200, content=_fixture("apple_exhibit_21.html"))

    return httpx.Response(404, text=f"Not found in test fixtures: {url}")


@pytest.fixture()
def edgar_client() -> httpx.Client:
    transport = httpx.MockTransport(_issue3_mock_handler)
    return httpx.Client(
        transport=transport,
        headers={"User-Agent": "Sales Lead Research (test@example.com)"},
    )


def _run_with_client(lines, edgar_client, tmp_path=None):
    out = io.StringIO()
    run_repl(
        iter(lines),
        out,
        client=edgar_client,
        output_dir=tmp_path,
    )
    return out.getvalue()


class TestFuzzyNameResolution:
    def test_substring_match_resolves_fedex(self, edgar_client):
        """Typing 'fedex' should match 'FEDEX CORP' via substring search."""
        output = _run_with_client(["fedex", "y", "y", "exit"], edgar_client)
        assert "FEDEX CORP" in output

    def test_multiple_matches_shows_numbered_list(self, edgar_client):
        """'fedex' matches both FEDEX CORP and FEDEX GROUND INC;
        the CLI should show a numbered list for disambiguation."""
        output = _run_with_client(["fedex", "1", "y", "y", "exit"], edgar_client)
        # The numbered list should contain both companies
        assert "FEDEX CORP" in output
        assert "FEDEX GROUND" in output

    def test_user_picks_from_numbered_list(self, edgar_client):
        """After seeing the numbered list, user picks option 1."""
        output = _run_with_client(["fedex", "1", "y", "y", "exit"], edgar_client)
        # After picking, we should proceed with that company
        assert "FEDEX CORP" in output


class TestConfirmationGates:
    def test_decline_company_confirmation_returns_to_prompt(self, edgar_client):
        """Answering 'n' at 'Is this the right company?' returns to prompt
        without fetching the filing."""
        output = _run_with_client(
            ["Apple Inc.", "n", "exit"], edgar_client
        )
        # The resolution prompt must have appeared (proves gates exist)
        assert "Resolved" in output or "Is this the right company" in output
        # Should NOT contain filing/subsidiary data
        assert "Apple Asia Limited" not in output

    def test_decline_filing_confirmation_returns_to_prompt(self, edgar_client):
        """Answering 'n' at 'Proceed with this filing?' returns to prompt
        without parsing the Exhibit 21."""
        output = _run_with_client(
            ["Apple Inc.", "y", "n", "exit"], edgar_client
        )
        # The filing source prompt must have appeared (proves second gate exists)
        assert "Proceed with this filing" in output or "Source:" in output
        # Should NOT contain subsidiary tree output
        assert "Apple Asia Limited" not in output

    def test_default_confirmation_is_yes(self, edgar_client, tmp_path):
        """Pressing Enter (empty string) at confirmation gates defaults to Y."""
        output = _run_with_client(
            ["Apple Inc.", "", "", "exit"], edgar_client, tmp_path
        )
        # Should proceed through both gates and show subsidiary data
        assert "Apple Asia Limited" in output


class TestFullHappyPathFlow:
    def test_tree_output_contains_company_and_subsidiaries(
        self, edgar_client, tmp_path
    ):
        """Full flow: fedex -> y -> y -> exit produces a tree with
        the company name and subsidiary names from the fixture."""
        # Use exact name to avoid disambiguation for this test
        output = _run_with_client(
            ["FEDEX CORP", "y", "y", "exit"], edgar_client, tmp_path
        )
        assert "FEDEX CORP" in output
        assert "Federal Express Corporation" in output
        assert "Delaware" in output
        # Tree glyphs should be present
        tree_glyphs = ("\u251c", "\u2514", "\u2502")
        assert any(glyph in output for glyph in tree_glyphs), (
            f"expected tree glyphs in output, got: {output!r}"
        )

    def test_output_shows_cik(self, edgar_client, tmp_path):
        output = _run_with_client(
            ["FEDEX CORP", "y", "y", "exit"], edgar_client, tmp_path
        )
        assert "1048911" in output

    def test_output_shows_source_url(self, edgar_client, tmp_path):
        output = _run_with_client(
            ["FEDEX CORP", "y", "y", "exit"], edgar_client, tmp_path
        )
        assert "sec.gov" in output


class TestCsvExport:
    def test_csv_file_created_in_output_dir(self, edgar_client, tmp_path):
        """A CSV file should be auto-saved to output_dir."""
        _run_with_client(
            ["FEDEX CORP", "y", "y", "exit"], edgar_client, tmp_path
        )
        csv_files = list(tmp_path.glob("*.csv"))
        assert len(csv_files) == 1

    def test_csv_filename_uses_underscored_company_name(
        self, edgar_client, tmp_path
    ):
        _run_with_client(
            ["FEDEX CORP", "y", "y", "exit"], edgar_client, tmp_path
        )
        expected = tmp_path / "fedex_corp_subsidiaries.csv"
        assert expected.exists(), (
            f"expected {expected}, found: {list(tmp_path.iterdir())}"
        )

    def test_csv_has_correct_headers(self, edgar_client, tmp_path):
        _run_with_client(
            ["FEDEX CORP", "y", "y", "exit"], edgar_client, tmp_path
        )
        csv_file = tmp_path / "fedex_corp_subsidiaries.csv"
        with open(csv_file) as f:
            reader = csv.reader(f)
            headers = next(reader)
        assert headers == ["Subsidiary Name", "Jurisdiction"]

    def test_csv_contains_all_subsidiaries(self, edgar_client, tmp_path):
        _run_with_client(
            ["FEDEX CORP", "y", "y", "exit"], edgar_client, tmp_path
        )
        csv_file = tmp_path / "fedex_corp_subsidiaries.csv"
        with open(csv_file) as f:
            reader = csv.reader(f)
            next(reader)  # skip header
            rows = list(reader)
        assert len(rows) == 5
        names = [row[0] for row in rows]
        assert "Federal Express Corporation" in names
        assert "TNT Express B.V." in names

    def test_output_confirms_csv_save(self, edgar_client, tmp_path):
        output = _run_with_client(
            ["FEDEX CORP", "y", "y", "exit"], edgar_client, tmp_path
        )
        assert "fedex_corp_subsidiaries.csv" in output
        assert "5 subsidiaries" in output


class TestSearchCompaniesFunction:
    """Tests for the new search_companies function in edgar.py."""

    def test_substring_match_returns_results(self, edgar_client):
        from sales_lead_research.edgar import search_companies

        results = search_companies("fedex", edgar_client)
        assert len(results) >= 1
        names = [name for name, _ in results]
        assert any("FEDEX" in name.upper() for name in names)

    def test_no_match_raises_company_not_found(self, edgar_client):
        from sales_lead_research.edgar import CompanyNotFound, search_companies

        with pytest.raises(CompanyNotFound):
            search_companies("zzz_nonexistent_zzz", edgar_client)

    def test_returns_cik_as_zero_padded_string(self, edgar_client):
        from sales_lead_research.edgar import search_companies

        results = search_companies("apple", edgar_client)
        for _name, cik in results:
            assert len(cik) == 10
            assert cik.isdigit()
