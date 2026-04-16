# agent-notes: { ctx: "issue #3 red-phase tests for Exhibit 21 parser", deps: ["src/sales_lead_research/edgar.py", "tests/fixtures/edgar/apple_exhibit_21.html"], state: active, last: "tara@2026-04-16" }
"""Failing tests for ``parse_exhibit_21`` — red phase of TDD.

Tests exercise the HTML table parser against fixture files and edge cases.
All tests should fail with ``NotImplementedError`` until Sato implements
``parse_exhibit_21`` in ``edgar.py``.
"""

from pathlib import Path

import pytest

from sales_lead_research.edgar import parse_exhibit_21

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"


def _fixture_html(name: str) -> str:
    return (FIXTURES / name).read_text()


class TestParseExhibit21HappyPath:
    def test_returns_list_of_tuples(self):
        html = _fixture_html("apple_exhibit_21.html")
        result = parse_exhibit_21(html)
        assert isinstance(result, list)
        assert all(isinstance(item, tuple) and len(item) == 2 for item in result)

    def test_extracts_correct_count(self):
        html = _fixture_html("apple_exhibit_21.html")
        result = parse_exhibit_21(html)
        assert len(result) == 7

    def test_first_subsidiary_name_and_jurisdiction(self):
        html = _fixture_html("apple_exhibit_21.html")
        result = parse_exhibit_21(html)
        assert result[0] == ("Apple Asia Limited", "Hong Kong")

    def test_last_subsidiary(self):
        html = _fixture_html("apple_exhibit_21.html")
        result = parse_exhibit_21(html)
        assert result[-1] == ("Braeburn Capital Inc.", "Nevada")

    def test_all_subsidiaries_have_nonempty_names(self):
        html = _fixture_html("apple_exhibit_21.html")
        result = parse_exhibit_21(html)
        for name, _jurisdiction in result:
            assert name.strip(), f"empty subsidiary name found"

    def test_parses_fedex_fixture(self):
        html = _fixture_html("fedex_exhibit_21.html")
        result = parse_exhibit_21(html)
        assert len(result) == 5
        names = [name for name, _ in result]
        assert "Federal Express Corporation" in names
        assert "TNT Express B.V." in names


class TestParseExhibit21EdgeCases:
    def test_empty_html_returns_empty_list(self):
        result = parse_exhibit_21("")
        assert result == []

    def test_html_with_no_table_returns_empty_list(self):
        html = "<html><body><p>No subsidiary data here.</p></body></html>"
        result = parse_exhibit_21(html)
        assert result == []

    def test_table_with_only_header_returns_empty_list(self):
        html = """<html><body><table>
        <tr><th>Name</th><th>Jurisdiction</th></tr>
        </table></body></html>"""
        result = parse_exhibit_21(html)
        assert result == []

    def test_whitespace_in_cells_is_stripped(self):
        html = """<html><body><table>
        <tr><th>Name</th><th>Jurisdiction</th></tr>
        <tr><td>  Acme Corp  </td><td>  Delaware  </td></tr>
        </table></body></html>"""
        result = parse_exhibit_21(html)
        assert result == [("Acme Corp", "Delaware")]
