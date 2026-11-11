"""Hardcoded state documentation-fee caps and tax calculation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


# States with a statutory (or widely enforced) documentation-fee ceiling.
DOC_FEE_CAPS: Dict[str, float] = {
    "CA": 85.0,
    "WA": 200.0,
    "TX": 150.0,
}

# States without a hard cap — flag anything above this as an excessive target.
UNCAPPED_EXCESSIVE_THRESHOLD: float = 399.0

# Approximate combined sales/use tax rates used when building an OTD counter.
# These are rough planning rates, not a substitute for county-level tables.
STATE_TAX_RATES: Dict[str, float] = {
    "CA": 0.0725,
    "WA": 0.065,
    "TX": 0.0625,
    "FL": 0.06,
    "VA": 0.043,
    "NY": 0.04,
    "OR": 0.0,
    "NH": 0.0,
    "MT": 0.0,
    "DE": 0.0,
    "AK": 0.0,
}

DEFAULT_TAX_RATE: float = 0.06


@dataclass(frozen=True)
class DocFeeRule:
    """Outcome of evaluating a documentation fee against state rules."""

    state: str
    statutory_cap: Optional[float]
    is_uncapped: bool
    excessive_threshold: Optional[float]
    recommended_amount: float
    excess_amount: float
    flag: Optional[str]


def normalize_state(state: str) -> str:
    """Return a two-letter uppercase state code."""
    return (state or "").strip().upper()


def get_doc_fee_cap(state: str) -> Optional[float]:
    """Return the statutory doc-fee cap for *state*, or None if uncapped."""
    return DOC_FEE_CAPS.get(normalize_state(state))


def get_tax_rate(state: str) -> float:
    """Return the planning sales-tax rate for *state*."""
    return STATE_TAX_RATES.get(normalize_state(state), DEFAULT_TAX_RATE)


def evaluate_doc_fee(state: str, amount: float) -> DocFeeRule:
    """
    Evaluate a documentation fee against the state rule matrix.

    - Capped states: clamp recommended amount to the statutory ceiling.
    - Uncapped states: recommend the quoted amount, but flag amounts above
      UNCAPPED_EXCESSIVE_THRESHOLD as an excessive negotiation target.
    """
    code = normalize_state(state)
    amount = float(amount or 0.0)
    cap = get_doc_fee_cap(code)

    if cap is not None:
        recommended = min(amount, cap)
        excess = max(0.0, amount - cap)
        flag = "Exceeds statutory documentation fee maximum" if excess > 0 else None
        return DocFeeRule(
            state=code,
            statutory_cap=cap,
            is_uncapped=False,
            excessive_threshold=None,
            recommended_amount=recommended,
            excess_amount=excess,
            flag=flag,
        )

    excess = max(0.0, amount - UNCAPPED_EXCESSIVE_THRESHOLD)
    flag = None
    if amount > UNCAPPED_EXCESSIVE_THRESHOLD:
        flag = "Excessive / High-Negotiation Target"
    return DocFeeRule(
        state=code,
        statutory_cap=None,
        is_uncapped=True,
        excessive_threshold=UNCAPPED_EXCESSIVE_THRESHOLD,
        recommended_amount=amount,  # no legal clamp; negotiation only
        excess_amount=excess,
        flag=flag,
    )


def estimate_tax(taxable_amount: float, state: str) -> float:
    """Estimate sales/use tax on *taxable_amount* for *state*."""
    return round(max(0.0, taxable_amount) * get_tax_rate(state), 2)
