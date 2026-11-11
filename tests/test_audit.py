"""
Spec verification cases:

1. $1,995 Ceramic Coating + $895 Nitrogen/Etch → both zeroed.
2. Florida $1,195 doc fee → $796 flagged as excessive negotiation target.
3. Counter-offer never breaches the invoice/holdback floor.
"""

from __future__ import annotations

from app.schemas import DealerWorksheet, FeeCategory, FeeItem
from core.elasticity import dealer_invoice_floor
from core.fee_auditor import audit_fees, total_junk_fees
from core.guardrail_clamper import clamp_counter_offer, run_full_audit
from core.statutory_rules import evaluate_doc_fee


def test_ceramic_and_nitrogen_etch_zeroed():
    fees = [
        FeeItem(
            name="Ceramic Coating",
            amount=1995.0,
            category=FeeCategory.DEALER_ADDON,
            is_removable=False,
            recommended_amount=1995.0,
        ),
        FeeItem(
            name="Nitrogen/Etch",
            amount=895.0,
            category=FeeCategory.DEALER_ADDON,
            is_removable=False,
            recommended_amount=895.0,
        ),
    ]
    audited = audit_fees(fees, "CA")
    by_name = {f.name: f for f in audited}
    assert by_name["Ceramic Coating"].recommended_amount == 0.0
    assert by_name["Ceramic Coating"].is_removable is True
    assert by_name["Nitrogen/Etch"].recommended_amount == 0.0
    assert by_name["Nitrogen/Etch"].is_removable is True
    assert total_junk_fees(audited, "CA") == 1995.0 + 895.0


def test_florida_doc_fee_flags_796_excessive():
    """FL uncapped: $1,195 doc fee → $796 above the $399 excessive threshold."""
    rule = evaluate_doc_fee("FL", 1195.0)
    assert rule.excess_amount == 796.0
    assert rule.flag == "Excessive / High-Negotiation Target"

    fees = [
        FeeItem(
            name="Documentation Fee",
            amount=1195.0,
            category=FeeCategory.DOC_FEE,
            is_removable=False,
            recommended_amount=1195.0,
        )
    ]
    audited = audit_fees(fees, "FL")
    assert total_junk_fees(audited, "FL") == 796.0


def test_counter_obeys_invoice_floor_never_loss_leader():
    """Counter-offer price strictly obeys the calculated invoice floor."""
    msrp = 50000.0
    segment = "mainstream"
    floor = dealer_invoice_floor(msrp, segment)

    worksheet = DealerWorksheet(
        year=2025,
        make="Honda",
        model="Accord",
        trim="EX-L",
        msrp=msrp,
        dealer_offered_price=48000.0,
        state="FL",
        fees=[
            FeeItem(
                name="Ceramic Coating",
                amount=1995.0,
                category=FeeCategory.DEALER_ADDON,
                is_removable=True,
                recommended_amount=1995.0,
            ),
            FeeItem(
                name="Nitrogen/Etch",
                amount=895.0,
                category=FeeCategory.DEALER_ADDON,
                is_removable=True,
                recommended_amount=895.0,
            ),
            FeeItem(
                name="Market Adjustment",
                amount=4500.0,
                category=FeeCategory.MARKET_ADJUSTMENT,
                is_removable=True,
                recommended_amount=4500.0,
            ),
            FeeItem(
                name="Documentation Fee",
                amount=1195.0,
                category=FeeCategory.DOC_FEE,
                is_removable=False,
                recommended_amount=1195.0,
            ),
        ],
        quoted_otd=58000.0,
    )

    result = clamp_counter_offer(worksheet, vehicle_segment=segment)
    assert result.floor_price == floor
    assert result.counter_base >= floor
    assert result.counter_base > 0
    assert result.target_counter_otd > 0
    # Must not emit a loss-leader that terminates negotiation.
    assert result.target_counter_otd >= floor

    audit = run_full_audit(worksheet, vehicle_segment=segment)
    assert audit.dealer_invoice_floor == floor
    assert audit.target_counter_otd >= floor
    assert audit.total_junk_fees == 1995.0 + 895.0 + 4500.0 + 796.0
