"""Pydantic v2 domain schemas for worksheets and negotiation audits."""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class FeeCategory(str, Enum):
    GOV_TAX_REG = "GOV_TAX_REG"
    DOC_FEE = "DOC_FEE"
    DEALER_ADDON = "DEALER_ADDON"
    MARKET_ADJUSTMENT = "MARKET_ADJUSTMENT"


class FeeItem(BaseModel):
    name: str
    amount: float = Field(..., ge=0)
    category: FeeCategory = FeeCategory.DEALER_ADDON
    is_removable: bool = True
    recommended_amount: float = Field(0.0, ge=0)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        cleaned = (value or "").strip()
        if not cleaned:
            raise ValueError("fee name must be non-empty")
        return cleaned


class DealerWorksheet(BaseModel):
    year: int = Field(..., ge=1980, le=2100)
    make: str
    model: str
    trim: str = ""
    msrp: float = Field(..., gt=0)
    dealer_offered_price: float = Field(..., gt=0)
    state: str = Field(..., min_length=2, max_length=2)
    fees: List[FeeItem] = Field(default_factory=list)
    quoted_otd: float = Field(..., gt=0)

    @field_validator("state")
    @classmethod
    def _upper_state(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("make", "model", "trim")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        return (value or "").strip()


class NegotiationAudit(BaseModel):
    total_junk_fees: float
    dealer_invoice_floor: float
    target_counter_otd: float
    projected_customer_savings: float
    dealer_acceptance_probability: float = Field(..., ge=0.0, le=1.0)
    tactical_action_plan: List[str]
    anti_deflection_email: str
    audited_fees: List[FeeItem] = Field(default_factory=list)
    vehicle_label: Optional[str] = None
    notes: List[str] = Field(default_factory=list)


class AuditRequest(BaseModel):
    """Request body for the /audit endpoint."""

    worksheet: DealerWorksheet
    aggression_discount: float = Field(
        0.03,
        ge=0.0,
        le=0.15,
        description="Fraction off dealer-offered price used as the aggressive ceiling.",
    )
    vehicle_segment: str = Field(
        "mainstream",
        description="Segment key for invoice-factor selection (economy/mainstream/luxury/truck).",
    )


class ParseRequest(BaseModel):
    """Optional multimodal parse request (Gemini stub when no API key)."""

    image_base64: Optional[str] = None
    text_blob: Optional[str] = None
    state_hint: Optional[str] = None
