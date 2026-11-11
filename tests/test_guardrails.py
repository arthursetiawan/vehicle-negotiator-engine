"""Tests for invoice-floor clamping and OTD construction."""

from __future__ import annotations

from app.schemas import DealerWorksheet, FeeCategory, FeeItem
from core.elasticity import dealer_invoice_floor
from core.guardrail_clamper import clamp_counter_offer, compute_counter_base, run_full_audit


def _worksheet(**overrides) -> DealerWorksheet:
    base = dict(
        year=2025,
        make="Toyota",
        model="Camry",
        trim="SE",
        msrp=42000.0,
        dealer_offered_price=40500.0,
        state="CA",
        fees=[
            FeeItem(
                name="Documentation Fee",
                amount=85.0,
                category=FeeCategory.DOC_FEE,
                is_removable=False,
                recommended_amount=85.0,
            ),
            FeeItem(
                name="Ceramic Coating",
                amount=1995.0,
                category=FeeCategory.DEALER_ADDON,
                is_removable=True,
                recommended_amount=1995.0,
            ),
        ],
        quoted_otd=45000.0,
    )
    base.update(overrides)
    return DealerWorksheet(**base)


def test_counter_never_below_invoice_floor():
    floor = dealer_invoice_floor(42000.0, "mainstream")
    # Extreme junk fees that would otherwise pull FairMarket far below floor.
    ws = _worksheet(
        fees=[
            FeeItem(
                name="Market Adjustment",
                amount=8000.0,
                category=FeeCategory.MARKET_ADJUSTMENT,
                is_removable=True,
                recommended_amount=8000.0,
            ),
            FeeItem(
                name="Ceramic Coating",
                amount=5000.0,
                category=FeeCategory.DEALER_ADDON,
                is_removable=True,
                recommended_amount=5000.0,
            ),
        ]
    )
    result = clamp_counter_offer(ws, vehicle_segment="mainstream")
    assert result.floor_price == floor
    assert result.counter_base >= result.floor_price
    assert result.counter_base > 0
    assert result.target_counter_otd >= result.floor_price


def test_compute_counter_base_math():
    floor = 10000.0
    offered = 12000.0
    junk = 500.0
    # fair=11500, aggressive=12000*0.97=11640 → min=11500 → max(floor,11500)=11500
    assert compute_counter_base(offered, floor, junk, 0.03) == 11500.0
    # If junk is huge, fair goes below floor → pin to floor.
    assert compute_counter_base(offered, floor, 5000.0, 0.03) == floor


def test_full_audit_savings_and_probability():
    audit = run_full_audit(_worksheet(), vehicle_segment="mainstream")
    assert audit.projected_customer_savings == round(
        45000.0 - audit.target_counter_otd, 2
    )
    assert 0.0 <= audit.dealer_acceptance_probability <= 1.0
    assert audit.dealer_invoice_floor > 0
    assert "Out-The-Door" in audit.anti_deflection_email
    assert "will not be visiting the showroom" in audit.anti_deflection_email.lower()


def test_no_negative_or_loss_leader_otd():
    ws = _worksheet(msrp=30000.0, dealer_offered_price=28000.0, quoted_otd=32000.0)
    result = clamp_counter_offer(ws)
    assert result.target_counter_otd > 0
    assert result.counter_base >= result.floor_price
