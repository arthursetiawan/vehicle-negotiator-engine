"""Dealer-Counter AI analytical core."""

from core.fee_auditor import audit_fees
from core.guardrail_clamper import clamp_counter_offer
from core.script_generator import generate_anti_deflection_email, generate_tactical_plan

__all__ = [
    "audit_fees",
    "clamp_counter_offer",
    "generate_anti_deflection_email",
    "generate_tactical_plan",
]
