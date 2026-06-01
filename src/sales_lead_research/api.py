# agent-notes: { ctx: "FastAPI REST API + static front-end; reuses discovery + matching core", deps: ["fastapi", "sales_lead_research.discovery", "sales_lead_research.matching"], state: active, last: "sato@2026-05-31" }
"""REST API for Sales Lead Research.

A thin HTTP layer over the existing discovery + matching core. Endpoints:

- ``GET /health``        — liveness/readiness probe (used by Kubernetes).
- ``GET /api/search``    — resolve a company name to candidate filers.
- ``GET /api/lookup``    — recursive subsidiary tree + existing-customer
                           account ids, as JSON.
- ``GET /api/web-lookup``— same idea for non-SEC filers, via web fallback.

The static single-page front-end (``static/index.html``) is served at ``/``.
Run it with: ``uvicorn sales_lead_research.api:app --host 0.0.0.0 --port 8000``.
"""

from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from sales_lead_research.discovery import (
    CompanyNotFound,
    EdgarLookupError,
    SubsidiaryNode,
    build_client,
    fetch_subsidiary_tree,
    search_companies,
    web_search_subsidiaries,
)
from sales_lead_research.discovery.edgar import exhibit_21_url, latest_annual_report
from sales_lead_research.matching.store import (
    CustomerStore,
    Matches,
    lookup_with_confidence,
    open_store,
)

USER_AGENT = "Sales Lead Research (mahadevaiah.rashmi@gmail.com)"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Sales Lead Research API",
    version="1.0.0",
    description="Corporate hierarchy + existing-customer matching for sales leads.",
)


# --------------------------------------------------------------------------- #
# Response models
# --------------------------------------------------------------------------- #
class CompanyMatch(BaseModel):
    name: str
    cik: str


class SearchResponse(BaseModel):
    query: str
    matches: list[CompanyMatch]
    message: str


class SubsidiaryNodeOut(BaseModel):
    name: str
    jurisdiction: str
    account_ids: list[str]           # confirmed existing-customer matches
    possible_account_ids: list[str]  # "close — verify" matches
    children: list["SubsidiaryNodeOut"] = []


class FlatRow(BaseModel):
    name: str
    jurisdiction: str
    level: int
    account_ids: list[str]
    possible_account_ids: list[str]


class LookupResponse(BaseModel):
    company: str
    cik: str
    source_url: str
    form: str
    filing_date: str
    subsidiaries_total: int
    customers_matched: int
    tree: SubsidiaryNodeOut
    flat: list[FlatRow]


SubsidiaryNodeOut.model_rebuild()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _client() -> httpx.Client:
    return build_client(USER_AGENT)


def _matches(store: CustomerStore | None, name: str) -> Matches:
    return lookup_with_confidence(store, name) if store is not None else Matches((), ())


def _to_node(node: SubsidiaryNode, store: CustomerStore | None) -> SubsidiaryNodeOut:
    m = _matches(store, node.name)
    return SubsidiaryNodeOut(
        name=node.name,
        jurisdiction=node.jurisdiction,
        account_ids=list(m.exact),
        possible_account_ids=list(m.close),
        children=[_to_node(child, store) for child in node.children],
    )


def _flatten(
    node: SubsidiaryNode, store: CustomerStore | None, depth: int, out: list[FlatRow]
) -> None:
    for child in node.children:
        m = _matches(store, child.name)
        out.append(
            FlatRow(
                name=child.name,
                jurisdiction=child.jurisdiction,
                level=depth,
                account_ids=list(m.exact),
                possible_account_ids=list(m.close),
            )
        )
        _flatten(child, store, depth + 1, out)


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #
@app.get("/health")
def health() -> dict[str, str]:
    """Liveness/readiness probe."""
    return {"status": "ok"}


@app.get("/api/search", response_model=SearchResponse)
def search(q: str = Query(..., min_length=1, description="Company name or ticker")):
    """Resolve a company name to candidate SEC filers (for disambiguation)."""
    client = _client()
    try:
        results = search_companies(q.strip(), client)
    except CompanyNotFound:
        return SearchResponse(
            query=q,
            matches=[],
            message=(
                "No SEC registrant found. Try the legal parent name, or "
                "use /api/web-lookup for non-SEC filers."
            ),
        )
    except EdgarLookupError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return SearchResponse(
        query=q,
        matches=[CompanyMatch(name=name, cik=cik) for name, cik in results],
        message=f"{len(results)} match(es).",
    )


@app.get("/api/lookup", response_model=LookupResponse)
def lookup(
    company: str = Query(..., description="Resolved company title"),
    cik: str = Query(..., description="10-digit CIK from /api/search"),
):
    """Recursive subsidiary tree for a confirmed company, with the account
    ids of any subsidiaries that are already customers."""
    client = _client()
    try:
        accession, form, filing_date = latest_annual_report(cik, client)
        url = exhibit_21_url(cik, accession, client)
        root = fetch_subsidiary_tree(company, client)
    except EdgarLookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    store = open_store()
    tree = _to_node(root, store)
    flat: list[FlatRow] = []
    _flatten(root, store, 1, flat)
    matched = sum(1 for row in flat if row.account_ids or row.possible_account_ids)

    return LookupResponse(
        company=company,
        cik=cik,
        source_url=url,
        form=form,
        filing_date=filing_date,
        subsidiaries_total=len(flat),
        customers_matched=matched,
        tree=tree,
        flat=flat,
    )


@app.get("/api/web-lookup")
def web_lookup(company: str = Query(..., description="Non-SEC company name")):
    """Subsidiary list for a non-SEC filer via web fallback, with matches."""
    client = _client()
    result = web_search_subsidiaries(company, client)
    if not result or (not result.get("parent") and not result.get("subsidiaries")):
        raise HTTPException(
            status_code=404,
            detail=f'No SEC filing or web data found for "{company}".',
        )

    store = open_store()
    rows: list[FlatRow] = []
    for name, jurisdiction in result.get("subsidiaries", []):
        m = _matches(store, name)
        rows.append(
            FlatRow(
                name=name,
                jurisdiction=jurisdiction,
                level=1,
                account_ids=list(m.exact),
                possible_account_ids=list(m.close),
            )
        )
    matched = sum(1 for r in rows if r.account_ids or r.possible_account_ids)
    return {
        "company": company,
        "parent": result.get("parent", ""),
        "source_url": result.get("source", ""),
        "subsidiaries_total": len(rows),
        "customers_matched": matched,
        "flat": [r.model_dump() for r in rows],
    }


# Serve the single-page front-end (declared last so /api and /health win).
if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
