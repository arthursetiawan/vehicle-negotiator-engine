"""Minimal Streamlit portal for worksheet audit + counter script."""

from __future__ import annotations

import sys
from pathlib import Path

# Allow `streamlit run web/streamlit_app.py` from the repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.schemas import DealerWorksheet, FeeCategory, FeeItem
from core.guardrail_clamper import run_full_audit
from core.parser import mock_worksheet_from_fixture, parse_text_blob

st.set_page_config(page_title="Dealer-Counter AI", page_icon=None, layout="wide")
st.title("Dealer-Counter AI")
st.caption("Audit junk fees, clamp to invoice floor, generate a remote-close script.")

with st.sidebar:
    st.header("Input")
    mode = st.radio("Source", ["Sample fixture", "Paste worksheet text", "Manual fees"])
    state = st.selectbox("State", ["CA", "WA", "TX", "FL", "VA", "NY", "OR"], index=0)
    aggression = st.slider("Aggression discount", 0.0, 0.10, 0.03, 0.01)
    segment = st.selectbox("Segment", ["mainstream", "economy", "luxury", "truck", "ev"])

worksheet: DealerWorksheet

if mode == "Sample fixture":
    ceramic = st.number_input("Ceramic Coating $", value=1995.0, step=50.0)
    nitrogen = st.number_input("Nitrogen/Etch $", value=895.0, step=50.0)
    doc = st.number_input("Doc fee $", value=1195.0 if state == "FL" else 85.0, step=25.0)
    worksheet = mock_worksheet_from_fixture(
        state=state, ceramic=ceramic, nitrogen_etch=nitrogen, doc_fee=doc
    )
elif mode == "Paste worksheet text":
    blob = st.text_area("Worksheet text", height=220, placeholder="Paste dealer quote…")
    if blob.strip():
        worksheet = parse_text_blob(blob, state_hint=state)
    else:
        worksheet = mock_worksheet_from_fixture(state=state)
else:
    col1, col2 = st.columns(2)
    with col1:
        year = st.number_input("Year", value=2025, step=1)
        make = st.text_input("Make", "Toyota")
        model = st.text_input("Model", "Camry")
        trim = st.text_input("Trim", "SE")
    with col2:
        msrp = st.number_input("MSRP", value=42000.0, step=500.0)
        offer = st.number_input("Dealer offered price", value=40500.0, step=500.0)
        quoted = st.number_input("Quoted OTD", value=46000.0, step=500.0)
    fee_name = st.text_input("Add fee name", "Ceramic Coating")
    fee_amt = st.number_input("Add fee amount", value=1995.0, step=50.0)
    if "manual_fees" not in st.session_state:
        st.session_state.manual_fees = [
            FeeItem(
                name="Documentation Fee",
                amount=85.0,
                category=FeeCategory.DOC_FEE,
                is_removable=False,
                recommended_amount=85.0,
            )
        ]
    if st.button("Add fee"):
        st.session_state.manual_fees.append(
            FeeItem(
                name=fee_name,
                amount=fee_amt,
                category=FeeCategory.DEALER_ADDON,
                is_removable=True,
                recommended_amount=fee_amt,
            )
        )
    worksheet = DealerWorksheet(
        year=int(year),
        make=make,
        model=model,
        trim=trim,
        msrp=float(msrp),
        dealer_offered_price=float(offer),
        state=state,
        fees=list(st.session_state.manual_fees),
        quoted_otd=float(quoted),
    )

if st.button("Run audit", type="primary"):
    audit = run_full_audit(worksheet, aggression_discount=aggression, vehicle_segment=segment)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Junk fees", f"${audit.total_junk_fees:,.2f}")
    m2.metric("Invoice floor", f"${audit.dealer_invoice_floor:,.2f}")
    m3.metric("Target OTD", f"${audit.target_counter_otd:,.2f}")
    m4.metric("Projected savings", f"${audit.projected_customer_savings:,.2f}")
    st.progress(audit.dealer_acceptance_probability, text=f"Acceptance {audit.dealer_acceptance_probability:.0%}")

    st.subheader("Audited fees")
    st.dataframe(
        [
            {
                "name": f.name,
                "amount": f.amount,
                "category": f.category.value,
                "removable": f.is_removable,
                "recommended": f.recommended_amount,
            }
            for f in audit.audited_fees
        ],
        use_container_width=True,
    )

    st.subheader("Tactical plan")
    for step in audit.tactical_action_plan:
        st.markdown(f"- {step}")

    st.subheader("Anti-deflection email")
    st.code(audit.anti_deflection_email, language=None)
else:
    st.info("Configure the worksheet, then click **Run audit**.")
