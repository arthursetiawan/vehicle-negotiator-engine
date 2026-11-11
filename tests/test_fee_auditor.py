"""Unit tests for rapidfuzz fee classification."""

from __future__ import annotations

from app.schemas import FeeCategory, FeeItem
from core.fee_auditor import audit_fees, classify_fee, total_junk_fees
from core.statutory_rules import evaluate_doc_fee


def test_ceramic_coating_zeroed():
    fee = FeeItem(
        name="Ceramic Coating",
        amount=1995.0,
        category=FeeCategory.DEALER_ADDON,
        is_removable=False,
        recommended_amount=1995.0,
    )
    audited = classify_fee(fee, "CA")
    assert audited.category == FeeCategory.DEALER_ADDON
    assert audited.is_removable is True
    assert audited.recommended_amount == 0.0


def test_nitrogen_etch_zeroed():
    fee = FeeItem(
        name="Nitrogen/Etch",
        amount=895.0,
        category=FeeCategory.DEALER_ADDON,
        is_removable=False,
        recommended_amount=895.0,
    )
    audited = classify_fee(fee, "TX")
    assert audited.recommended_amount == 0.0
    assert audited.is_removable is True


def test_fuzzy_paint_protection():
    fee = FeeItem(
        name="Paint Prot. Pkg",
        amount=1299.0,
        category=FeeCategory.DEALER_ADDON,
        is_removable=False,
        recommended_amount=1299.0,
    )
    audited = classify_fee(fee, "WA")
    assert audited.category == FeeCategory.DEALER_ADDON
    assert audited.recommended_amount == 0.0


def test_ca_doc_fee_clamped_to_85():
    fee = FeeItem(
        name="Documentation Fee",
        amount=499.0,
        category=FeeCategory.DOC_FEE,
        is_removable=False,
        recommended_amount=499.0,
    )
    audited = classify_fee(fee, "CA")
    assert audited.category == FeeCategory.DOC_FEE
    assert audited.recommended_amount == 85.0
    assert audited.is_removable is True


def test_florida_doc_fee_excess_flag():
    rule = evaluate_doc_fee("FL", 1195.0)
    assert rule.is_uncapped is True
    assert rule.excess_amount == 796.0
    assert rule.flag == "Excessive / High-Negotiation Target"


def test_gov_fees_pass_through():
    fee = FeeItem(
        name="Registration",
        amount=365.0,
        category=FeeCategory.GOV_TAX_REG,
        is_removable=True,
        recommended_amount=0.0,
    )
    audited = classify_fee(fee, "CA")
    assert audited.category == FeeCategory.GOV_TAX_REG
    assert audited.is_removable is False
    assert audited.recommended_amount == 365.0


def test_total_junk_includes_addons_and_doc_excess():
    fees = [
        FeeItem(name="Ceramic Coating", amount=1995.0, category=FeeCategory.DEALER_ADDON),
        FeeItem(name="Documentation Fee", amount=1195.0, category=FeeCategory.DOC_FEE),
    ]
    audited = audit_fees(fees, "FL")
    junk = total_junk_fees(audited, "FL")
    assert junk == 1995.0 + 796.0
