"""FastAPI surface for the Dealer-Counter evaluation engine."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import (
    AuditRequest,
    DiscoverRequest,
    DiscoverResponse,
    InventoryListingModel,
    NegotiationAudit,
    ParseRequest,
    DealerWorksheet,
)
from core.discovery import DiscoveryQuery, junk_fee_radar_tips, search_inventory
from core.guardrail_clamper import run_full_audit
from core.parser import ParserUnavailableError, parse_worksheet

app = FastAPI(
    title="Dealer-Counter AI Engine",
    description="Audit dealer worksheets, clamp counter-offers to invoice floors, and emit anti-deflection scripts.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/audit", response_model=NegotiationAudit)
def audit(request: AuditRequest) -> NegotiationAudit:
    """Run the full fee audit + clamped counter + script pipeline."""
    return run_full_audit(
        request.worksheet,
        aggression_discount=request.aggression_discount,
        vehicle_segment=request.vehicle_segment,
    )


@app.post("/parse", response_model=DealerWorksheet)
def parse(request: ParseRequest) -> DealerWorksheet:
    """Parse worksheet image/text (Gemini when keyed; stub/heuristic otherwise)."""
    try:
        return parse_worksheet(
            image_base64=request.image_base64,
            text_blob=request.text_blob,
            state_hint=request.state_hint,
            allow_stub=True,
        )
    except ParserUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/parse-and-audit", response_model=NegotiationAudit)
def parse_and_audit(request: ParseRequest) -> NegotiationAudit:
    worksheet = parse(request)
    return run_full_audit(worksheet)


@app.post("/discover", response_model=DiscoverResponse)
def discover(request: DiscoverRequest) -> DiscoverResponse:
    """Live web-search inventory discovery (DuckDuckGo by default; no API key)."""
    result = search_inventory(
        DiscoveryQuery(
            zip_code=request.zip_code,
            year=request.year,
            make=request.make,
            model=request.model,
            trim=request.trim,
            condition=request.condition,
            dealer_name=request.dealer_name,
            budget_otd=request.budget_otd,
            state=request.state,
            max_results=request.max_results,
        )
    )
    tips = junk_fee_radar_tips(request.make, request.state) if result.listings else []
    return DiscoverResponse(
        search_query=result.search_query,
        provider=result.provider,
        listings=[InventoryListingModel.model_validate(item.__dict__) for item in result.listings],
        competitor_suggestions=result.competitor_suggestions,
        junk_fee_tips=tips,
        notes=result.notes,
    )
