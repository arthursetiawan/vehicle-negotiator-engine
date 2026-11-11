"""Dealer-Counter AI analytical core."""

from core.discovery import generate_cold_outreach, search_inventory
from core.fee_auditor import audit_fees
from core.guardrail_clamper import clamp_counter_offer
from core.script_generator import generate_anti_deflection_email, generate_tactical_plan

__all__ = [
    "audit_fees",
    "clamp_counter_offer",
    "generate_anti_deflection_email",
    "generate_cold_outreach",
    "generate_tactical_plan",
    "search_inventory",
]
