# agent-notes: { ctx: "discovery subpackage public API per ADR-0003 §1", deps: [sales_lead_research.discovery.edgar, sales_lead_research.discovery.web_fallback], state: active, last: "sato@2026-04-28" }
"""Public API for the subsidiary-discovery library.

The names re-exported here are the only surface that callers outside
``discovery/`` (front-ends, ``chat/``, ``matching/``) may import. Lower-level
helpers (``latest_10k_accession``, ``exhibit_21_url``, ``parse_exhibit_21``,
``_extract_structure_from_pdf`` and friends) stay module-private — see
ADR-0003 §1 for the rationale.
"""

from sales_lead_research.discovery.edgar import (
    CompanyNotFound,
    EdgarLookupError,
    No10KFiled,
    NoExhibit21,
    SubsidiaryNode,
    build_client,
    fetch_subsidiary_tree,
    search_companies,
)
from sales_lead_research.discovery.web_fallback import web_search_subsidiaries

__all__ = [
    "build_client",
    "search_companies",
    "fetch_subsidiary_tree",
    "web_search_subsidiaries",
    "SubsidiaryNode",
    "EdgarLookupError",
    "CompanyNotFound",
    "No10KFiled",
    "NoExhibit21",
]
