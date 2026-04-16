# agent-notes: { ctx: "tests for natural language query extraction", deps: ["src/sales_lead_research/cli.py"], state: active, last: "sato@2026-04-16" }
"""Tests for natural language query extraction.

Verifies that extract_company_name correctly pulls company names
from various natural language phrasings, while passing plain
company names through unchanged.
"""

import pytest

from sales_lead_research.cli import extract_company_name


class TestExtractCompanyName:
    # Plain company names pass through unchanged
    def test_plain_name(self):
        assert extract_company_name("Apple") == "Apple"

    def test_ticker_symbol(self):
        assert extract_company_name("AAPL") == "AAPL"

    def test_strips_whitespace(self):
        assert extract_company_name("  FedEx  ") == "FedEx"

    def test_empty_string(self):
        assert extract_company_name("") == ""

    # "show me X's subsidiaries" patterns
    def test_show_me_subsidiaries(self):
        assert extract_company_name("show me Apple's subsidiaries") == "Apple"

    def test_show_subsidiaries(self):
        assert extract_company_name("show FedEx subsidiaries") == "FedEx"

    def test_list_subsidiaries(self):
        assert extract_company_name("list Microsoft's subsidiaries") == "Microsoft"

    def test_find_subsidiaries(self):
        assert extract_company_name("find Apple Inc subsidiaries") == "Apple Inc"

    def test_get_hierarchy(self):
        assert extract_company_name("get Apple's corporate structure") == "Apple"

    # "what/who" question patterns
    def test_what_are_subsidiaries(self):
        assert extract_company_name("what are Apple's subsidiaries") == "Apple"

    def test_what_companies_does_own(self):
        assert extract_company_name("what companies does FedEx own") == "FedEx"

    def test_who_does_own(self):
        assert extract_company_name("who does Microsoft own") == "Microsoft"

    # "subsidiaries of X" patterns
    def test_subsidiaries_of(self):
        assert extract_company_name("subsidiaries of Apple") == "Apple"

    def test_hierarchy_of(self):
        assert extract_company_name("hierarchy of FedEx Corp") == "FedEx Corp"

    def test_corporate_structure_of(self):
        assert extract_company_name("corporate structure of Microsoft") == "Microsoft"

    # "tell me about / search for" patterns
    def test_tell_me_about(self):
        assert extract_company_name("tell me about Apple") == "Apple"

    def test_search_for(self):
        assert extract_company_name("search for FedEx") == "FedEx"

    def test_look_up(self):
        assert extract_company_name("look up Microsoft Corp") == "Microsoft Corp"

    # Trailing punctuation stripped
    def test_strips_question_mark(self):
        assert extract_company_name("Apple?") == "Apple"

    def test_preserves_period_in_name(self):
        assert extract_company_name("Apple Inc.") == "Apple Inc."

    def test_nl_with_question_mark(self):
        assert extract_company_name("what companies does FedEx own?") == "FedEx"

    # Case insensitive matching
    def test_case_insensitive(self):
        assert extract_company_name("SHOW ME apple's SUBSIDIARIES") == "apple"
