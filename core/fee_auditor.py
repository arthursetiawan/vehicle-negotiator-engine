"""Fuzzy fee classification against known dealer junk-fee patterns."""

from __future__ import annotations

from copy import deepcopy
from typing import Iterable, List, Sequence, Tuple

from rapidfuzz import fuzz

from app.schemas import FeeCategory, FeeItem
from core.statutory_rules import evaluate_doc_fee

# Red-flag dealer add-on / packing terms from the build spec.
RED_FLAG_TERMS: Sequence[str] = (
    "Paint Protection",
    "Ceramic",
    "Ceramic Coating",
    "Window Tint",
    "Desert Protection",
    "PDI",
    "Dealer Prep",
    "LoJack",
    "Etch",
    "Nitrogen",
    "Nitrogen/Etch",
    "Reconditioning",
    "Market Adjustment",
    "Admin Fee",
    "ADM",
    "Appearance Package",
    "Fabric Protection",
    "Rust Proofing",
    "Undercoating",
)

MATCH_THRESHOLD = 65

# Tokens that strongly indicate a documentation / processing fee.
_DOC_FEE_HINTS = (
    "doc fee",
    "documentation",
    "document fee",
    "dealer doc",
    "processing fee",
    "documentary",
)

# Tokens that indicate government tax / registration / title.
_GOV_HINTS = (
    "sales tax",
    "state tax",
    "registration",
    "reg fee",
    "title fee",
    "license",
    "dmv",
    "plate",
    "excise",
)


def _best_red_flag_score(name: str) -> Tuple[int, str | None]:
    best_score = 0
    best_term: str | None = None
    for term in RED_FLAG_TERMS:
        score = int(fuzz.token_sort_ratio(name, term))
        # Also try partial ratio so "Nitrogen/Etch Package" hits "Nitrogen" / "Etch".
        partial = int(fuzz.partial_ratio(name.lower(), term.lower()))
        score = max(score, partial)
        if score > best_score:
            best_score = score
            best_term = term
    return best_score, best_term


def _looks_like_doc_fee(name: str) -> bool:
    lower = name.lower()
    return any(hint in lower for hint in _DOC_FEE_HINTS)


def _looks_like_gov(name: str) -> bool:
    lower = name.lower()
    return any(hint in lower for hint in _GOV_HINTS)


def classify_fee(fee: FeeItem, state: str) -> FeeItem:
    """
    Classify a single fee item.

    Rules (spec):
    - token_sort_ratio > 65 vs a red-flag term → DEALER_ADDON, removable, $0.
    - Doc fee over statutory limit → clamp recommended_amount to the ceiling.
    - Florida (uncapped) doc fee > $399 → flag excess as negotiation target
      (recommended stays quoted; excess tracked via statutory_rules).
    """
    audited = fee.model_copy(deep=True)
    name = audited.name

    if _looks_like_gov(name):
        audited.category = FeeCategory.GOV_TAX_REG
        audited.is_removable = False
        audited.recommended_amount = audited.amount
        return audited

    # Doc / processing fees take priority over fuzzy add-on matches so that
    # names like "Documentation Fee" are not swallowed by "Admin Fee".
    if _looks_like_doc_fee(name) or audited.category == FeeCategory.DOC_FEE:
        rule = evaluate_doc_fee(state, audited.amount)
        audited.category = FeeCategory.DOC_FEE
        # Doc fees are not "removable" entirely, but excess is negotiable.
        audited.is_removable = rule.excess_amount > 0
        audited.recommended_amount = round(rule.recommended_amount, 2)
        return audited

    score, _term = _best_red_flag_score(name)
    if score > MATCH_THRESHOLD:
        # Market Adjustment is its own category but still a removable packing fee.
        if "market adjustment" in name.lower() or name.lower().strip() in {"adm", "adm fee"}:
            audited.category = FeeCategory.MARKET_ADJUSTMENT
        else:
            audited.category = FeeCategory.DEALER_ADDON
        audited.is_removable = True
        audited.recommended_amount = 0.0
        return audited

    # Unknown line: treat conservatively as a removable dealer add-on if
    # the caller already marked it that way; otherwise preserve category.
    if audited.category in (FeeCategory.DEALER_ADDON, FeeCategory.MARKET_ADJUSTMENT):
        audited.is_removable = True
        if audited.recommended_amount == audited.amount:
            # Default recommendation for unclassified add-ons: strike to $0.
            audited.recommended_amount = 0.0
    return audited


def audit_fees(fees: Iterable[FeeItem], state: str) -> List[FeeItem]:
    """Classify every fee on a worksheet."""
    return [classify_fee(fee, state) for fee in fees]


def total_junk_fees(audited: Sequence[FeeItem], state: str) -> float:
    """
    Sum of non-mandatory add-ons and excess doc fees.

    - Removable add-ons / market adjustments contribute their full amount
      (recommended is $0).
    - Doc fees contribute only the excess over the statutory (or uncapped
      negotiation) ceiling.
    """
    total = 0.0
    for fee in audited:
        if fee.category in (FeeCategory.DEALER_ADDON, FeeCategory.MARKET_ADJUSTMENT):
            if fee.is_removable:
                total += max(0.0, fee.amount - fee.recommended_amount)
        elif fee.category == FeeCategory.DOC_FEE:
            rule = evaluate_doc_fee(state, fee.amount)
            total += rule.excess_amount
    return round(total, 2)


def approved_doc_fee(audited: Sequence[FeeItem], state: str) -> float:
    """Return the recommended (clamped) documentation fee, or 0 if none."""
    for fee in audited:
        if fee.category == FeeCategory.DOC_FEE:
            return round(fee.recommended_amount, 2)
    # If no explicit doc fee line, use the state cap (or $0 for uncapped).
    from core.statutory_rules import get_doc_fee_cap

    cap = get_doc_fee_cap(state)
    return float(cap or 0.0)


def gov_fees_total(audited: Sequence[FeeItem]) -> float:
    """Sum of government tax / registration lines (pass-through)."""
    return round(
        sum(f.amount for f in audited if f.category == FeeCategory.GOV_TAX_REG),
        2,
    )
