"""Anti-deflection remote-purchase scripts for internet sales managers."""

from __future__ import annotations

from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from app.schemas import DealerWorksheet
    from core.guardrail_clamper import ClampResult


def _fee_strike_lines(result: "ClampResult") -> List[str]:
    lines: List[str] = []
    for fee in result.audited_fees:
        if fee.recommended_amount < fee.amount:
            lines.append(
                f"- {fee.name}: quoted ${fee.amount:,.2f} → ${fee.recommended_amount:,.2f}"
            )
    return lines


def generate_tactical_plan(
    worksheet: "DealerWorksheet",
    result: "ClampResult",
) -> List[str]:
    """Step-by-step counter instructions."""
    strikes = _fee_strike_lines(result)
    plan = [
        f"Open with a firm Out-The-Door target of ${result.target_counter_otd:,.2f} "
        f"for the {worksheet.year} {worksheet.make} {worksheet.model}.",
        "State that the offer is contingent on a signed Buyer's Order matching that OTD — "
        "no showroom visit before figures are locked.",
    ]
    if strikes:
        plan.append("Itemize fee strikes on the worksheet:")
        plan.extend(strikes)
    plan.extend(
        [
            f"Do not accept a vehicle price below the estimated invoice/holdback floor "
            f"of ${result.floor_price:,.2f}; walk away rather than go underwater.",
            "If the desk counters with payment packing or 'manager approval' delays, "
            "restate the OTD number and the remote-close path (e-deposit + remote credit app).",
            "Expire the offer same-business-day to force a clean yes/no.",
        ]
    )
    return plan


def generate_anti_deflection_email(
    worksheet: "DealerWorksheet",
    result: "ClampResult",
) -> str:
    """
    Concise, professional message for the internet sales manager.

    Tone: direct, firm, non-emotional. Explicitly counters the
    "come into the store" trap per the build spec.
    """
    vehicle = f"{worksheet.year} {worksheet.make} {worksheet.model}"
    if worksheet.trim:
        vehicle = f"{vehicle} {worksheet.trim}"

    strike_block = "\n".join(_fee_strike_lines(result)) or "- No discretionary fee adjustments required."
    otd = result.target_counter_otd

    return (
        f"Subject: Firm Out-The-Door Offer — {vehicle}\n\n"
        f"Hello,\n\n"
        f"Thank you for the quote on the {vehicle}. After reviewing the worksheet, "
        f"I am prepared to proceed at the following Out-The-Door figure only:\n\n"
        f"Out-The-Door: ${otd:,.2f}\n\n"
        f"Fee adjustments required on the Buyer's Order:\n"
        f"{strike_block}\n\n"
        f"Vehicle selling price basis (pre-tax/fees): ${result.counter_base:,.2f}\n"
        f"Approved documentation fee: ${result.doc_fee:,.2f}\n\n"
        f"I am prepared to complete this transaction today via electronic deposit and "
        f"remote credit application upon receipt of a signed Buyer's Order reflecting "
        f"the Out-The-Door figure of ${otd:,.2f}. I will not be visiting the showroom "
        f"prior to locking in the agreed figures.\n\n"
        f"Please confirm in writing whether the desk will honor this OTD today. "
        f"If not, I will move on to another inventory unit.\n\n"
        f"Regards"
    )
