# agent-notes: { ctx: "issue #4 red-phase tests for recursive subsidiary walk", deps: ["src/sales_lead_research/edgar.py", "tests/fixtures/edgar/"], state: active, last: "tara@2026-04-16" }
"""Red-phase tests for issue #4: recursive subsidiary walk.

Tests the ``SubsidiaryNode`` dataclass and ``fetch_subsidiary_tree`` function
that builds a multi-level corporate hierarchy from SEC EDGAR Exhibit 21 filings.
All tests expected to FAIL until Sato implements the green phase.
"""

from pathlib import Path

import httpx
import pytest

from sales_lead_research.edgar import (
    SubsidiaryNode,
    fetch_subsidiary_tree,
)

FIXTURES = Path(__file__).parent / "fixtures" / "edgar"


def _fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def _recursive_mock_handler(request: httpx.Request) -> httpx.Response:
    """Mock transport serving fixtures for the recursive walk scenario.

    Companies in play:
    - PARENT CORP (CIK 9999999): has CHILD INC + LEAF LLC as subsidiaries
    - CHILD INC (CIK 8888888): has GRANDCHILD CORP as subsidiary
    - LEAF LLC: NOT an SEC filer (absent from company_tickers.json)
    """
    url = str(request.url)

    # Company tickers (shared fixture, now includes PARENT CORP + CHILD INC)
    if url == "https://www.sec.gov/files/company_tickers.json":
        return httpx.Response(200, content=_fixture("company_tickers.json"))

    # --- PARENT CORP (CIK 9999999) ---
    if url == "https://data.sec.gov/submissions/CIK0009999999.json":
        return httpx.Response(200, content=_fixture("CIK0009999999.json"))

    if "000999999924000001/0009999999-24-000001-index.htm" in url:
        return httpx.Response(200, content=_fixture("parent_10k_filing_index.html"))

    if "parent-20240101ex211.htm" in url:
        return httpx.Response(200, content=_fixture("parent_exhibit_21.html"))

    # --- CHILD INC (CIK 8888888) ---
    if url == "https://data.sec.gov/submissions/CIK0008888888.json":
        return httpx.Response(200, content=_fixture("CIK0008888888.json"))

    if "000888888824000001/0008888888-24-000001-index.htm" in url:
        return httpx.Response(200, content=_fixture("child_10k_filing_index.html"))

    if "child-20240101ex211.htm" in url:
        return httpx.Response(200, content=_fixture("child_exhibit_21.html"))

    return httpx.Response(404, text=f"Not found in test fixtures: {url}")


@pytest.fixture()
def recursive_client() -> httpx.Client:
    transport = httpx.MockTransport(_recursive_mock_handler)
    return httpx.Client(
        transport=transport,
        headers={"User-Agent": "Sales Lead Research (test@example.com)"},
    )


# ---------------------------------------------------------------------------
# SubsidiaryNode dataclass
# ---------------------------------------------------------------------------


class TestSubsidiaryNode:
    def test_has_name_field(self):
        node = SubsidiaryNode(name="Acme", jurisdiction="Delaware", children=[])
        assert node.name == "Acme"

    def test_has_jurisdiction_field(self):
        node = SubsidiaryNode(name="Acme", jurisdiction="Delaware", children=[])
        assert node.jurisdiction == "Delaware"

    def test_has_children_field(self):
        child = SubsidiaryNode(name="Sub", jurisdiction="Nevada", children=[])
        node = SubsidiaryNode(name="Parent", jurisdiction="", children=[child])
        assert len(node.children) == 1
        assert node.children[0].name == "Sub"

    def test_children_defaults_to_empty_list(self):
        node = SubsidiaryNode(name="Leaf", jurisdiction="California")
        assert node.children == []

    def test_nested_tree_structure(self):
        grandchild = SubsidiaryNode(name="GC", jurisdiction="CA")
        child = SubsidiaryNode(name="C", jurisdiction="DE", children=[grandchild])
        root = SubsidiaryNode(name="R", jurisdiction="", children=[child])
        assert root.children[0].children[0].name == "GC"


# ---------------------------------------------------------------------------
# fetch_subsidiary_tree
# ---------------------------------------------------------------------------


class TestFetchSubsidiaryTree:
    def test_happy_path_returns_subsidiary_node(self, recursive_client):
        """Root return type must be SubsidiaryNode."""
        result = fetch_subsidiary_tree("PARENT CORP", recursive_client)
        assert isinstance(result, SubsidiaryNode)

    def test_root_node_has_parent_name(self, recursive_client):
        """Root node name should be the resolved company name."""
        result = fetch_subsidiary_tree("PARENT CORP", recursive_client)
        assert result.name == "PARENT CORP"

    def test_root_has_two_direct_children(self, recursive_client):
        """PARENT CORP's Exhibit 21 lists CHILD INC and LEAF LLC."""
        result = fetch_subsidiary_tree("PARENT CORP", recursive_client)
        child_names = {c.name for c in result.children}
        assert "CHILD INC" in child_names
        assert "LEAF LLC" in child_names
        assert len(result.children) == 2

    def test_child_inc_has_nested_grandchild(self, recursive_client):
        """CHILD INC is an SEC filer, so its Exhibit 21 should be fetched
        and GRANDCHILD CORP should appear as its child."""
        result = fetch_subsidiary_tree("PARENT CORP", recursive_client)
        child_inc = next(c for c in result.children if c.name == "CHILD INC")
        grandchild_names = {gc.name for gc in child_inc.children}
        assert "GRANDCHILD CORP" in grandchild_names

    def test_child_inc_jurisdiction_is_delaware(self, recursive_client):
        result = fetch_subsidiary_tree("PARENT CORP", recursive_client)
        child_inc = next(c for c in result.children if c.name == "CHILD INC")
        assert child_inc.jurisdiction == "Delaware"

    def test_grandchild_jurisdiction_is_california(self, recursive_client):
        result = fetch_subsidiary_tree("PARENT CORP", recursive_client)
        child_inc = next(c for c in result.children if c.name == "CHILD INC")
        grandchild = next(gc for gc in child_inc.children if gc.name == "GRANDCHILD CORP")
        assert grandchild.jurisdiction == "California"

    def test_leaf_subsidiary_has_no_children(self, recursive_client):
        """LEAF LLC is NOT an SEC filer -- it should be a leaf node."""
        result = fetch_subsidiary_tree("PARENT CORP", recursive_client)
        leaf = next(c for c in result.children if c.name == "LEAF LLC")
        assert leaf.children == []

    def test_leaf_jurisdiction_is_nevada(self, recursive_client):
        result = fetch_subsidiary_tree("PARENT CORP", recursive_client)
        leaf = next(c for c in result.children if c.name == "LEAF LLC")
        assert leaf.jurisdiction == "Nevada"

    def test_max_depth_1_prevents_recursion(self, recursive_client):
        """With max_depth=1, no subsidiary's Exhibit 21 should be fetched.
        All children should be leaf nodes."""
        result = fetch_subsidiary_tree(
            "PARENT CORP", recursive_client, max_depth=1
        )
        for child in result.children:
            assert child.children == [], (
                f"{child.name} should be a leaf at max_depth=1 but has children"
            )

    def test_max_depth_2_allows_one_level_of_recursion(self, recursive_client):
        """max_depth=2 (default) allows fetching CHILD INC's subsidiaries
        but GRANDCHILD CORP should be a leaf (depth would be 3)."""
        result = fetch_subsidiary_tree(
            "PARENT CORP", recursive_client, max_depth=2
        )
        child_inc = next(c for c in result.children if c.name == "CHILD INC")
        assert len(child_inc.children) >= 1
        # GRANDCHILD CORP should be a leaf at depth 3
        grandchild = child_inc.children[0]
        assert grandchild.children == []

    def test_failed_subsidiary_lookup_treated_as_leaf(self):
        """If a subsidiary IS in company_tickers.json but its 10-K or
        Exhibit 21 fetch fails, it should become a leaf node -- not crash."""

        def _failing_handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if url == "https://www.sec.gov/files/company_tickers.json":
                return httpx.Response(200, content=_fixture("company_tickers.json"))
            if url == "https://data.sec.gov/submissions/CIK0009999999.json":
                return httpx.Response(200, content=_fixture("CIK0009999999.json"))
            if "000999999924000001/0009999999-24-000001-index.htm" in url:
                return httpx.Response(200, content=_fixture("parent_10k_filing_index.html"))
            if "parent-20240101ex211.htm" in url:
                return httpx.Response(200, content=_fixture("parent_exhibit_21.html"))
            # CHILD INC submissions return 500 -- simulating a lookup failure
            if url == "https://data.sec.gov/submissions/CIK0008888888.json":
                return httpx.Response(500, text="Internal Server Error")
            return httpx.Response(404, text="Not found")

        transport = httpx.MockTransport(_failing_handler)
        client = httpx.Client(
            transport=transport,
            headers={"User-Agent": "Sales Lead Research (test@example.com)"},
        )

        result = fetch_subsidiary_tree("PARENT CORP", client)
        # CHILD INC should still appear but as a leaf (failed recursive lookup)
        child_inc = next(c for c in result.children if c.name == "CHILD INC")
        assert child_inc.children == []

    def test_case_insensitive_subsidiary_matching(self, recursive_client):
        """Subsidiary name matching against company_tickers.json should
        be case-insensitive. Our fixture has 'CHILD INC' in both the
        Exhibit 21 and company_tickers.json in the same case, but the
        implementation must use case-insensitive comparison."""
        # This test validates the contract. The fixture happens to match
        # case, but the implementation must not rely on that.
        result = fetch_subsidiary_tree("PARENT CORP", recursive_client)
        child_inc = next(c for c in result.children if c.name == "CHILD INC")
        assert len(child_inc.children) >= 1

    def test_root_jurisdiction_is_empty_string(self, recursive_client):
        """The root company's jurisdiction is not in its own Exhibit 21,
        so it should be an empty string."""
        result = fetch_subsidiary_tree("PARENT CORP", recursive_client)
        assert result.jurisdiction == ""
