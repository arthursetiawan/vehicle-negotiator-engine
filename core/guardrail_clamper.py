"""Clamped counter-offer math: invoice floor, junk-fee strip, OTD build."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence

from app.schemas import DealerWorksheet, FeeItem, NegotiationAudit
from core.elasticity import (
    acceptance_probability,
    classify_segment_from_make,
    dealer_invoice_floor,
)
from core.fee_auditor import (
    approved_doc_fee,
    audit_fees,
    gov_fees_total,
    total_junk_fees,
)
from core.script_generator import generate_anti_deflection_email, generate_tactical_plan
from core.statutory_rules import estimate_tax


@dataclass(frozen=True)
class ClampResult:
    floor_price: float
    fair_market_price: float
    counter_base: float
    target_counter_otd: float
    total_junk_fees: float
    tax_estimate: float
    doc_fee: float
    gov_fees: float
    acceptance: float
    audited_fees: List[FeeItem]


def compute_counter_base(
    dealer_offered_price: float,
    floor_price: float,
    total_junk: float,
    aggression_discount: float = 0.03,
) -> float:
    """
    Spec clamp:

    FairMarketPrice = dealer_offered_price − total_junk_fees
    CounterBase = max(FloorPrice, min(FairMarketPrice, dealer_offered × (1 − Aggression)))
    """
    fair = dealer_offered_price - total_junk
    aggressive_ceiling = dealer_offered_price * (1.0 - aggression_discount)
    counter = max(floor_price, min(fair, aggressive_ceiling))
    # Never emit a non-positive or below-floor figure.
    counter = max(counter, floor_price, 0.0)
    return round(counter, 2)


def build_target_otd(
    counter_base: float,
    state: str,
    doc_fee: float,
    gov_fees: float,
    tax_on_vehicle: Optional[float] = None,
) -> tuple[float, float]:
    """
    OTD = vehicle counter + approved doc fee + gov fees + sales tax on vehicle.

    Returns (target_otd, tax_estimate).
    """
    tax = tax_on_vehicle if tax_on_vehicle is not None else estimate_tax(counter_base, state)
    # If worksheet already itemized sales tax under GOV, avoid double-counting tax.
    # Heuristic: when gov_fees already exceed a plausible registration-only band
    # and look like they include tax, prefer the worksheet gov total and skip
    # synthetic tax. Callers can pass tax_on_vehicle=0 to force that.
    otd = counter_base + doc_fee + gov_fees + tax
    return round(otd, 2), round(tax, 2)


def clamp_counter_offer(
    worksheet: DealerWorksheet,
    aggression_discount: float = 0.03,
    vehicle_segment: Optional[str] = None,
) -> ClampResult:
    """Run fee audit + clamped counter math for a dealer worksheet."""
    segment = vehicle_segment or classify_segment_from_make(worksheet.make, worksheet.msrp)
    audited = audit_fees(worksheet.fees, worksheet.state)
    junk = total_junk_fees(audited, worksheet.state)
    floor = dealer_invoice_floor(worksheet.msrp, segment)
    fair = worksheet.dealer_offered_price - junk
    counter_base = compute_counter_base(
        worksheet.dealer_offered_price,
        floor,
        junk,
        aggression_discount=aggression_discount,
    )

    doc = approved_doc_fee(audited, worksheet.state)
    gov = gov_fees_total(audited)

    # Prefer worksheet sales-tax line if present; else synthesize from rate table.
    has_tax_line = any(
        f.category.value == "GOV_TAX_REG" and "tax" in f.name.lower() for f in audited
    )
    if has_tax_line:
        # Scale tax roughly to the new vehicle price vs original offer.
        original_tax = sum(
            f.amount
            for f in audited
            if f.category.value == "GOV_TAX_REG" and "tax" in f.name.lower()
        )
        # Remove original tax from gov pass-through; recompute on counter_base.
        gov_without_tax = gov - original_tax
        tax = estimate_tax(counter_base, worksheet.state)
        otd, tax = build_target_otd(counter_base, worksheet.state, doc, gov_without_tax, tax)
        gov = gov_without_tax
    else:
        otd, tax = build_target_otd(counter_base, worksheet.state, doc, gov)

    acceptance = acceptance_probability(counter_base, floor, worksheet.dealer_offered_price)

    return ClampResult(
        floor_price=floor,
        fair_market_price=round(fair, 2),
        counter_base=counter_base,
        target_counter_otd=otd,
        total_junk_fees=junk,
        tax_estimate=tax,
        doc_fee=doc,
        gov_fees=gov,
        acceptance=acceptance,
        audited_fees=audited,
    )


def run_full_audit(
    worksheet: DealerWorksheet,
    aggression_discount: float = 0.03,
    vehicle_segment: Optional[str] = None,
) -> NegotiationAudit:
    """Produce a complete NegotiationAudit including scripts."""
    result = clamp_counter_offer(
        worksheet,
        aggression_discount=aggression_discount,
        vehicle_segment=vehicle_segment,
    )
    savings = round(worksheet.quoted_otd - result.target_counter_otd, 2)
    label = f"{worksheet.year} {worksheet.make} {worksheet.model} {worksheet.trim}".strip()
    plan = generate_tactical_plan(worksheet, result)
    email = generate_anti_deflection_email(worksheet, result)

    notes: List[str] = []
    if result.counter_base <= result.floor_price + 0.01:
        notes.append("Counter base is pinned to the estimated invoice/holdback floor.")
    if result.total_junk_fees > 0:
        notes.append(f"Identified ${result.total_junk_fees:,.2f} in junk / excess fees.")

    return NegotiationAudit(
        total_junk_fees=result.total_junk_fees,
        dealer_invoice_floor=result.floor_price,
        target_counter_otd=result.target_counter_otd,
        projected_customer_savings=savings,
        dealer_acceptance_probability=result.acceptance,
        tactical_action_plan=plan,
        anti_deflection_email=email,
        audited_fees=result.audited_fees,
        vehicle_label=label,
        notes=notes,
    )
