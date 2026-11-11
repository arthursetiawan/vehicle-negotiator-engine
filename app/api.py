"""FastAPI surface for the Dealer-Counter evaluation engine."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.schemas import AuditRequest, NegotiationAudit, ParseRequest, DealerWorksheet
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
