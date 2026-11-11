"""Invoice / holdback estimation and acceptance-probability helpers."""

from __future__ import annotations

from typing import Dict, Tuple


# Approximate invoice-as-fraction-of-MSRP by vehicle segment.
# Spec: MSRP × 0.92 to 0.95 depending on segment, then subtract 2% holdback.
INVOICE_FACTORS: Dict[str, float] = {
    "economy": 0.95,
    "mainstream": 0.93,
    "luxury": 0.92,
    "truck": 0.94,
    "ev": 0.93,
}

HOLDBACK_RATE: float = 0.02


def normalize_segment(segment: str | None) -> str:
    key = (segment or "mainstream").strip().lower()
    return key if key in INVOICE_FACTORS else "mainstream"


def estimate_invoice(msrp: float, segment: str | None = "mainstream") -> float:
    """Estimate dealer invoice from MSRP and segment."""
    factor = INVOICE_FACTORS[normalize_segment(segment)]
    return round(float(msrp) * factor, 2)


def estimate_holdback(msrp: float) -> float:
    """Estimate factory holdback (typically ~2% of MSRP)."""
    return round(float(msrp) * HOLDBACK_RATE, 2)


def dealer_invoice_floor(msrp: float, segment: str | None = "mainstream") -> float:
    """
    Floor the dealer can typically accept before losing money on the unit.

    Floor = estimated invoice − holdback.
    """
    invoice = estimate_invoice(msrp, segment)
    holdback = estimate_holdback(msrp)
    return round(invoice - holdback, 2)


def acceptance_probability(
    counter_base: float,
    floor_price: float,
    dealer_offered_price: float,
) -> float:
    """
    Calibrate a simple 0–1 acceptance score.

    Near the dealer offer → high probability.
    Near / at the invoice floor → low but non-zero probability.
    Below the floor → clamped to a near-zero floor (should not happen after clamp).
    """
    if dealer_offered_price <= floor_price:
        return 0.55

    span = dealer_offered_price - floor_price
    if span <= 0:
        return 0.5

    # How far above the floor the counter sits (1.0 = at dealer offer).
    relative = (counter_base - floor_price) / span
    relative = max(0.0, min(1.0, relative))

    # Map [0,1] → roughly [0.18, 0.92]
    score = 0.18 + 0.74 * relative
    return round(score, 3)


def classify_segment_from_make(make: str, msrp: float) -> str:
    """Heuristic segment guess when the caller does not supply one."""
    luxury_makes = {
        "bmw",
        "mercedes",
        "mercedes-benz",
        "audi",
        "lexus",
        "porsche",
        "cadillac",
        "genesis",
        "infiniti",
        "acura",
        "jaguar",
        "land rover",
        "volvo",
    }
    truck_tokens = {"ford", "ram", "gmc", "chevrolet", "chevy", "toyota", "nissan"}
    make_l = (make or "").strip().lower()
    if make_l in luxury_makes or msrp >= 70000:
        return "luxury"
    if make_l in truck_tokens and msrp >= 45000:
        return "truck"
    if msrp < 28000:
        return "economy"
    return "mainstream"


def invoice_band(msrp: float, segment: str | None = "mainstream") -> Tuple[float, float]:
    """Return (low, high) invoice estimates bracketing the point estimate."""
    base = estimate_invoice(msrp, segment)
    return round(base * 0.99, 2), round(base * 1.01, 2)
