# agent-notes: { ctx: "unit tests for web_fallback helpers and PDF/HTML extractors", deps: ["src/sales_lead_research/discovery/web_fallback.py"], state: active, last: "sato@2026-04-28" }
"""Tests for ``sales_lead_research.discovery.web_fallback``.

Covers the deterministic helpers (URL extraction, URL scoring, jurisdiction
and financial-noise filters) and the HTML / PDF structure extractors. The
PDF parser is exercised via a stubbed ``pypdf.PdfReader`` so the test suite
does not need real PDF fixtures.

The test ``test_pdf_parser_keeps_country_in_parens`` is a regression guard
for the right-to-left country scan in ``_extract_structure_from_pdf``. If
anyone changes that loop to pick the first match, the DHL live run will
silently regress.
"""

from __future__ import annotations

from urllib.parse import quote_plus

import pytest

from sales_lead_research.discovery import web_fallback
from sales_lead_research.discovery.web_fallback import (
    _extract_ddg_urls,
    _extract_structure,
    _extract_structure_from_pdf,
    _is_promising_url,
    _looks_like_financial_noise,
    _looks_like_jurisdiction,
)


# ---------- _extract_ddg_urls ----------

class TestExtractDdgUrls:
    def test_extracts_uddg_urls(self):
        target = "https://example.com/annual-report.pdf"
        html = f'<a href="/l/?uddg={quote_plus(target)}&rut=abc">link</a>'
        assert _extract_ddg_urls(html) == [target]

    def test_dedupes_repeated_urls(self):
        target = "https://example.com/page"
        encoded = quote_plus(target)
        html = (
            f'<a href="/l/?uddg={encoded}">one</a>'
            f'<a href="/l/?uddg={encoded}&rut=1">two</a>'
        )
        assert _extract_ddg_urls(html) == [target]

    def test_returns_empty_list_when_no_uddg(self):
        assert _extract_ddg_urls("<html>no results</html>") == []


# ---------- _is_promising_url ----------

class TestIsPromisingUrl:
    def test_pdf_with_annual_keyword_is_promising(self):
        assert _is_promising_url(
            "https://group.dhl.com/.../DHL-Group-List-of-shareholdings-2024.pdf",
            "DHL",
        )

    def test_pdf_without_report_keywords_is_not_promising(self):
        assert not _is_promising_url(
            "https://example.com/random-brochure.pdf", "DHL"
        )

    def test_investor_page_is_promising(self):
        assert _is_promising_url(
            "https://example.com/investor/annual-report-2024", "DHL"
        )

    def test_random_blog_is_not_promising(self):
        assert not _is_promising_url(
            "https://blog.example.com/top-10-logistics-news", "DHL"
        )


# ---------- jurisdiction / financial noise ----------

class TestLooksLikeJurisdiction:
    @pytest.mark.parametrize(
        "text",
        ["Germany", "Portugal, Moreira da Maia", "Hong Kong",
         "United Kingdom", "Delaware", "California"],
    )
    def test_recognises_known_jurisdictions(self, text):
        assert _looks_like_jurisdiction(text)

    def test_rejects_unrelated_text(self):
        assert not _looks_like_jurisdiction("Total operating revenue")

    def test_rejects_empty(self):
        assert not _looks_like_jurisdiction("")

    def test_rejects_overly_long_text(self):
        # Prose that happens to mention a country should not count.
        assert not _looks_like_jurisdiction(
            "A sprawling paragraph mentioning Germany but much too long to "
            "be a jurisdiction column in a structured table."
        )


class TestLooksLikeFinancialNoise:
    @pytest.mark.parametrize(
        "text", ["Revenue", "EBIT", "Net income", "Total"]
    )
    def test_catches_common_financial_lines(self, text):
        assert _looks_like_financial_noise(text)

    def test_ignores_real_company_names(self):
        assert not _looks_like_financial_noise("Apple Inc.")
        assert not _looks_like_financial_noise("DHL Express (Portugal) Lda.")


# ---------- _extract_structure (HTML) ----------

class TestExtractStructureHtml:
    def test_returns_none_for_empty_html(self):
        assert _extract_structure("", "Acme") is None

    def test_parses_basic_subsidiary_table(self):
        html = """
        <table>
          <tr><th>Name</th><th>Country</th></tr>
          <tr><td>Acme Deutschland GmbH</td><td>Germany</td></tr>
          <tr><td>Acme France SAS</td><td>France</td></tr>
        </table>
        """
        result = _extract_structure(html, "Acme")
        assert result is not None
        assert ("Acme Deutschland GmbH", "Germany") in result["subsidiaries"]
        assert ("Acme France SAS", "France") in result["subsidiaries"]

    def test_skips_rows_that_are_financial_noise(self):
        html = """
        <table>
          <tr><td>Revenue</td><td>1234</td></tr>
          <tr><td>Acme France SAS</td><td>France</td></tr>
        </table>
        """
        result = _extract_structure(html, "Acme")
        names = [n for n, _ in result["subsidiaries"]]
        assert "Revenue" not in names
        assert "Acme France SAS" in names

    def test_picks_jurisdiction_from_later_column_when_middle_is_noise(self):
        html = """
        <table>
          <tr><td>Acme Japan K.K.</td><td>--</td><td>Japan</td></tr>
        </table>
        """
        result = _extract_structure(html, "Acme")
        assert ("Acme Japan K.K.", "Japan") in result["subsidiaries"]

    def test_deduplicates_repeated_names(self):
        html = """
        <table>
          <tr><td>Acme UK Ltd</td><td>United Kingdom</td></tr>
          <tr><td>Acme UK Ltd</td><td>United Kingdom</td></tr>
        </table>
        """
        result = _extract_structure(html, "Acme")
        names = [n for n, _ in result["subsidiaries"]]
        assert names.count("Acme UK Ltd") == 1


# ---------- _extract_structure_from_pdf (via stubbed pypdf) ----------

class _FakePage:
    def __init__(self, text: str) -> None:
        self._text = text

    def extract_text(self) -> str:
        return self._text


class _FakeReader:
    """Swapped in for ``pypdf.PdfReader`` in tests."""

    _pages_text: list[str] = []

    def __init__(self, *_args, **_kwargs) -> None:
        self.pages = [_FakePage(t) for t in type(self)._pages_text]


@pytest.fixture
def fake_pdf(monkeypatch):
    """Return a callable that installs fake PDF text for the next call."""

    def _install(*pages: str) -> None:
        _FakeReader._pages_text = list(pages)
        import pypdf
        monkeypatch.setattr(pypdf, "PdfReader", _FakeReader)

    return _install


class TestExtractStructureFromPdf:
    def test_returns_none_when_no_rows_match(self, fake_pdf):
        fake_pdf("Just a cover page. Nothing structured here.")
        assert _extract_structure_from_pdf(b"ignored", "DHL") is None

    def test_parses_a_simple_shareholdings_row(self, fake_pdf):
        fake_pdf(
            "DHL Logistics GmbH Germany, Bonn 100.00 EUR 1,234.5 567.8\n"
        )
        result = _extract_structure_from_pdf(b"ignored", "DHL")
        assert result is not None
        assert result["subsidiaries"] == [
            ("DHL Logistics GmbH", "Germany, Bonn")
        ]

    def test_strips_footnote_markers_from_name(self, fake_pdf):
        fake_pdf(
            "ABIS GmbH 6), 9) Germany, Bonn 100.00 EUR 50.0 10.0\n"
        )
        result = _extract_structure_from_pdf(b"ignored", "DHL")
        assert result["subsidiaries"] == [("ABIS GmbH", "Germany, Bonn")]

    def test_keeps_country_in_parens(self, fake_pdf):
        """Regression guard for the right-to-left country scan.

        If this breaks, the parser is splitting at the first country
        match (inside the parens) instead of the last one. DHL's PDF
        will return rows like ``("DHL Express", "Portugal, Lda. ...")``.
        """
        fake_pdf(
            "DHL Express (Portugal) Lda. Portugal, Moreira da Maia "
            "100.00 EUR 1,234.5 567.8\n"
        )
        result = _extract_structure_from_pdf(b"ignored", "DHL")
        assert result["subsidiaries"] == [
            ("DHL Express (Portugal) Lda.", "Portugal, Moreira da Maia")
        ]

    def test_skips_lines_without_trailing_numeric_columns(self, fake_pdf):
        fake_pdf(
            "Chapter heading with no numbers\n"
            "DHL Logistics GmbH Germany, Bonn 100.00 EUR 50.0 10.0\n"
            "Another prose line.\n"
        )
        result = _extract_structure_from_pdf(b"ignored", "DHL")
        assert [name for name, _ in result["subsidiaries"]] == [
            "DHL Logistics GmbH"
        ]

    def test_deduplicates_repeated_names_across_pages(self, fake_pdf):
        fake_pdf(
            "DHL Logistics GmbH Germany, Bonn 100.00 EUR 50.0 10.0\n",
            "DHL Logistics GmbH Germany, Bonn 100.00 EUR 50.0 10.0\n",
        )
        result = _extract_structure_from_pdf(b"ignored", "DHL")
        names = [n for n, _ in result["subsidiaries"]]
        assert names == ["DHL Logistics GmbH"]

    def test_parent_field_echoes_query(self, fake_pdf):
        fake_pdf("DHL Logistics GmbH Germany, Bonn 100.00 EUR 50.0 10.0\n")
        result = _extract_structure_from_pdf(b"ignored", "Deutsche Post")
        assert result["parent"] == "Deutsche Post"
