"""YourNextCar guided discovery + Dealer-Counter audit portal (Streamlit)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Allow `streamlit run web/streamlit_app.py` from the repo root.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from app.schemas import DealerWorksheet, FeeCategory, FeeItem
from core.discovery import (
    DiscoveryQuery,
    InventoryListing,
    generate_cold_outreach,
    junk_fee_radar_tips,
    otd_request_draft,
    search_inventory,
)
from core.guardrail_clamper import run_full_audit
from core.parser import mock_worksheet_from_fixture, parse_text_blob

st.set_page_config(
    page_title="YourNextCar — Dealer-Counter",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

# Brand atmosphere: ink + steel + brass (not purple SaaS / cream terracotta).
st.markdown(
    """
<style>
  :root {
    --ync-ink: #14212b;
    --ync-steel: #3d5a6c;
    --ync-brass: #b08d57;
    --ync-mist: #e8eef2;
    --ync-paper: #f7f5f1;
  }
  .stApp {
    background:
      radial-gradient(1200px 500px at 10% -10%, #d9e4ec 0%, transparent 55%),
      radial-gradient(900px 420px at 100% 0%, #e6ddd0 0%, transparent 50%),
      linear-gradient(180deg, var(--ync-paper) 0%, #f0ebe3 100%);
  }
  .ync-brand {
    font-family: "Iowan Old Style", "Palatino Linotype", Palatino, "Book Antiqua", Georgia, serif;
    font-size: 2.6rem;
    letter-spacing: 0.02em;
    color: var(--ync-ink);
    margin: 0.2rem 0 0.1rem 0;
    line-height: 1.05;
  }
  .ync-tag {
    color: var(--ync-steel);
    font-size: 1.05rem;
    margin-bottom: 1.25rem;
  }
  .ync-step {
    display: inline-block;
    color: var(--ync-brass);
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-size: 0.75rem;
    margin-bottom: 0.35rem;
  }
  .ync-card-lite {
    border-left: 3px solid var(--ync-brass);
    padding: 0.55rem 0.85rem;
    margin: 0.4rem 0;
    background: rgba(255,255,255,0.55);
  }
  div[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a2833 0%, #243746 100%);
  }
  div[data-testid="stSidebar"] * { color: #e8eef2 !important; }
</style>
""",
    unsafe_allow_html=True,
)

STEPS = ["Where", "What", "Find", "Negotiate"]


def _init_state() -> None:
    defaults = {
        "flow_step": 0,
        "zip_code": "",
        "dealer_name": "",
        "any_franchise": True,
        "state": "CA",
        "year": 2025,
        "make": "Toyota",
        "model": "Camry",
        "trim": "SE",
        "condition": "new",
        "budget_otd": 0.0,
        "must_haves": "",
        "listings": [],
        "selected_idx": None,
        "search_query": "",
        "search_provider": "",
        "competitor_suggestions": [],
        "discovery_notes": [],
        "portal_mode": "Guided discovery",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _selected_listing() -> Optional[InventoryListing]:
    idx = st.session_state.selected_idx
    listings = st.session_state.listings
    if idx is None or not listings:
        return None
    if 0 <= idx < len(listings):
        return listings[idx]
    return None


def _render_brand_header() -> None:
    st.markdown('<p class="ync-brand">YourNextCar</p>', unsafe_allow_html=True)
    st.markdown(
        '<p class="ync-tag">Find the dealer. Lock the car. Counter with a clean Out-The-Door.</p>',
        unsafe_allow_html=True,
    )


def _step_indicator() -> None:
    current = st.session_state.flow_step
    cols = st.columns(len(STEPS))
    for i, (col, label) in enumerate(zip(cols, STEPS)):
        marker = "●" if i == current else ("✓" if i < current else "○")
        weight = "**" if i == current else ""
        col.markdown(f"{marker} {weight}{i + 1}. {label}{weight}")


def _goto(step: int) -> None:
    st.session_state.flow_step = max(0, min(step, len(STEPS) - 1))


def render_where() -> None:
    st.markdown('<div class="ync-step">Step 1 — Where</div>', unsafe_allow_html=True)
    st.subheader("Which dealer world are we shopping?")
    st.caption("ZIP or metro first. Name a store if you already have one — or shop any nearby franchise.")

    c1, c2 = st.columns(2)
    with c1:
        st.session_state.zip_code = st.text_input(
            "ZIP / metro",
            value=st.session_state.zip_code,
            placeholder="94107",
        )
        st.session_state.state = st.selectbox(
            "State (for fee rules)",
            ["CA", "WA", "TX", "FL", "VA", "NY", "OR"],
            index=["CA", "WA", "TX", "FL", "VA", "NY", "OR"].index(st.session_state.state)
            if st.session_state.state in ["CA", "WA", "TX", "FL", "VA", "NY", "OR"]
            else 0,
        )
    with c2:
        st.session_state.any_franchise = st.checkbox(
            "Any nearby franchise for this brand",
            value=st.session_state.any_franchise,
        )
        st.session_state.dealer_name = st.text_input(
            "Dealer name (optional)",
            value=st.session_state.dealer_name,
            placeholder="Toyota of Downtown",
            disabled=st.session_state.any_franchise,
        )

    if st.button("Continue to car interest →", type="primary", disabled=not st.session_state.zip_code.strip()):
        _goto(1)
        st.rerun()


def render_what() -> None:
    st.markdown('<div class="ync-step">Step 2 — What</div>', unsafe_allow_html=True)
    st.subheader("What are you trying to buy?")
    st.caption("Year, make, model, trim. Optional OTD ceiling keeps the search honest.")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.session_state.year = int(st.number_input("Year", value=int(st.session_state.year), min_value=1990, max_value=2100))
        st.session_state.make = st.text_input("Make", value=st.session_state.make)
    with c2:
        st.session_state.model = st.text_input("Model", value=st.session_state.model)
        st.session_state.trim = st.text_input("Trim", value=st.session_state.trim)
    with c3:
        st.session_state.condition = st.selectbox(
            "Condition",
            ["new", "used", "any"],
            index=["new", "used", "any"].index(st.session_state.condition),
        )
        st.session_state.budget_otd = float(
            st.number_input(
                "Budget OTD ceiling (optional)",
                value=float(st.session_state.budget_otd or 0),
                min_value=0.0,
                step=500.0,
            )
        )
    st.session_state.must_haves = st.text_input(
        "Must-haves",
        value=st.session_state.must_haves,
        placeholder="AWD, blind-spot, no market adjustment",
    )

    b1, b2 = st.columns(2)
    with b1:
        if st.button("← Back"):
            _goto(0)
            st.rerun()
    with b2:
        ready = bool(st.session_state.make.strip() and st.session_state.model.strip())
        if st.button("Search live inventory →", type="primary", disabled=not ready):
            _goto(2)
            st.rerun()


def render_find() -> None:
    st.markdown('<div class="ync-step">Step 3 — Find</div>', unsafe_allow_html=True)
    st.subheader("Live inventory near you")
    dealer = "" if st.session_state.any_franchise else st.session_state.dealer_name
    budget = st.session_state.budget_otd if st.session_state.budget_otd and st.session_state.budget_otd > 0 else None

    if st.button("Run web search", type="primary"):
        with st.spinner("Searching the open web for matching inventory…"):
            result = search_inventory(
                DiscoveryQuery(
                    zip_code=st.session_state.zip_code,
                    year=int(st.session_state.year),
                    make=st.session_state.make,
                    model=st.session_state.model,
                    trim=st.session_state.trim,
                    condition=st.session_state.condition,
                    dealer_name=dealer,
                    budget_otd=budget,
                    state=st.session_state.state,
                    max_results=8,
                )
            )
        st.session_state.listings = result.listings
        st.session_state.search_query = result.search_query
        st.session_state.search_provider = result.provider
        st.session_state.competitor_suggestions = result.competitor_suggestions
        st.session_state.discovery_notes = result.notes
        st.session_state.selected_idx = None

    if st.session_state.search_query:
        st.caption(
            f"Query: `{st.session_state.search_query}` · provider: **{st.session_state.search_provider or 'duckduckgo'}**"
        )

    listings: list[InventoryListing] = st.session_state.listings
    if not listings:
        st.info("Click **Run web search** to surface ranked listings (DuckDuckGo — no API key).")
    else:
        for i, item in enumerate(listings):
            price = f"${item.price:,.0f}" if item.price else "Price n/a"
            days = f"{item.days_listed}d on market" if item.days_listed is not None else "Days n/a"
            dealer_label = item.dealer_name or "Dealer n/a"
            st.markdown(
                f'<div class="ync-card-lite"><strong>{item.title}</strong><br/>'
                f"{price} · {dealer_label} · {days} · score {item.score:.1f}<br/>"
                f'<a href="{item.url}" target="_blank">Open listing</a></div>',
                unsafe_allow_html=True,
            )
            if st.button(f"Pick this target #{i + 1}", key=f"pick_{i}"):
                st.session_state.selected_idx = i
                _goto(3)
                st.rerun()

        for note in st.session_state.discovery_notes:
            st.warning(note)
        for tip in st.session_state.competitor_suggestions:
            st.markdown(f"- {tip}")

    b1, b2 = st.columns(2)
    with b1:
        if st.button("← Back to car"):
            _goto(1)
            st.rerun()
    with b2:
        if st.button("Skip to negotiate without pick"):
            _goto(3)
            st.rerun()


def render_negotiate() -> None:
    st.markdown('<div class="ync-step">Step 4 — Negotiate</div>', unsafe_allow_html=True)
    st.subheader("Audit a quote — or open with cold outreach")

    listing = _selected_listing()
    if listing:
        st.markdown(
            f"**Target:** [{listing.title}]({listing.url}) · "
            f"{f'${listing.price:,.0f}' if listing.price else 'price n/a'} · "
            f"{listing.dealer_name or 'dealer n/a'}"
        )
        tips = junk_fee_radar_tips(st.session_state.make, st.session_state.state)
        st.markdown("**Junk fee radar**")
        for tip in tips:
            st.markdown(f'<div class="ync-card-lite">{tip}</div>', unsafe_allow_html=True)

    path = st.radio(
        "Path",
        ["I have a dealer quote — run audit", "No quote yet — cold outreach script"],
        horizontal=True,
    )

    if path.startswith("I have"):
        mode = st.radio("Worksheet source", ["Sample fixture", "Paste worksheet text", "Manual fees"])
        state = st.session_state.state
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
            # Prefer discovered vehicle identity when present.
            worksheet = worksheet.model_copy(
                update={
                    "year": int(st.session_state.year),
                    "make": st.session_state.make or worksheet.make,
                    "model": st.session_state.model or worksheet.model,
                    "trim": st.session_state.trim or worksheet.trim,
                    "dealer_offered_price": float(listing.price)
                    if listing and listing.price
                    else worksheet.dealer_offered_price,
                }
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
                year = st.number_input("Year", value=int(st.session_state.year), step=1)
                make = st.text_input("Make ", st.session_state.make)
                model = st.text_input("Model ", st.session_state.model)
                trim = st.text_input("Trim ", st.session_state.trim)
            with col2:
                default_offer = float(listing.price) if listing and listing.price else 40500.0
                msrp = st.number_input("MSRP", value=max(default_offer * 1.05, 20000.0), step=500.0)
                offer = st.number_input("Dealer offered price", value=default_offer, step=500.0)
                quoted = st.number_input("Quoted OTD", value=default_offer * 1.12, step=500.0)
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
            st.progress(
                audit.dealer_acceptance_probability,
                text=f"Acceptance {audit.dealer_acceptance_probability:.0%}",
            )
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

            drafts = otd_request_draft(
                listing
                or InventoryListing(title=f"{worksheet.year} {worksheet.make} {worksheet.model}", url=""),
                target_otd=audit.target_counter_otd,
                vehicle_label=f"{worksheet.year} {worksheet.make} {worksheet.model}",
            )
            st.subheader("Request OTD Buyer's Order")
            st.code(drafts["email"], language=None)
            st.code(drafts["sms"], language=None)
    else:
        if listing is None:
            st.warning("Pick a listing in Find for a targeted script — or search again.")
        else:
            budget = (
                st.session_state.budget_otd
                if st.session_state.budget_otd and st.session_state.budget_otd > 0
                else None
            )
            script = generate_cold_outreach(
                listing,
                year=int(st.session_state.year),
                make=st.session_state.make,
                model=st.session_state.model,
                trim=st.session_state.trim,
                budget_otd=budget,
                zip_code=st.session_state.zip_code,
            )
            st.subheader("Cold outreach anti-deflection script")
            st.code(script, language=None)
            drafts = otd_request_draft(
                listing,
                target_otd=budget,
                vehicle_label=f"{st.session_state.year} {st.session_state.make} {st.session_state.model}",
            )
            st.subheader("One-click OTD request drafts")
            st.markdown("**Email**")
            st.code(drafts["email"], language=None)
            st.markdown("**SMS**")
            st.code(drafts["sms"], language=None)

    if st.button("← Back to Find"):
        _goto(2)
        st.rerun()


def render_direct_audit() -> None:
    """Legacy single-page audit portal preserved under Direct audit mode."""
    st.subheader("Direct worksheet audit")
    with st.sidebar:
        st.header("Input")
        mode = st.radio("Source", ["Sample fixture", "Paste worksheet text", "Manual fees"], key="direct_mode")
        state = st.selectbox("State", ["CA", "WA", "TX", "FL", "VA", "NY", "OR"], index=0, key="direct_state")
        aggression = st.slider("Aggression discount", 0.0, 0.10, 0.03, 0.01, key="direct_agg")
        segment = st.selectbox(
            "Segment", ["mainstream", "economy", "luxury", "truck", "ev"], key="direct_seg"
        )

    worksheet: DealerWorksheet
    if mode == "Sample fixture":
        ceramic = st.number_input("Ceramic Coating $", value=1995.0, step=50.0, key="d_cer")
        nitrogen = st.number_input("Nitrogen/Etch $", value=895.0, step=50.0, key="d_nit")
        doc = st.number_input("Doc fee $", value=1195.0 if state == "FL" else 85.0, step=25.0, key="d_doc")
        worksheet = mock_worksheet_from_fixture(
            state=state, ceramic=ceramic, nitrogen_etch=nitrogen, doc_fee=doc
        )
    elif mode == "Paste worksheet text":
        blob = st.text_area("Worksheet text", height=220, placeholder="Paste dealer quote…", key="d_blob")
        if blob.strip():
            worksheet = parse_text_blob(blob, state_hint=state)
        else:
            worksheet = mock_worksheet_from_fixture(state=state)
    else:
        col1, col2 = st.columns(2)
        with col1:
            year = st.number_input("Year", value=2025, step=1, key="d_year")
            make = st.text_input("Make", "Toyota", key="d_make")
            model = st.text_input("Model", "Camry", key="d_model")
            trim = st.text_input("Trim", "SE", key="d_trim")
        with col2:
            msrp = st.number_input("MSRP", value=42000.0, step=500.0, key="d_msrp")
            offer = st.number_input("Dealer offered price", value=40500.0, step=500.0, key="d_offer")
            quoted = st.number_input("Quoted OTD", value=46000.0, step=500.0, key="d_otd")
        fee_name = st.text_input("Add fee name", "Ceramic Coating", key="d_fee_name")
        fee_amt = st.number_input("Add fee amount", value=1995.0, step=50.0, key="d_fee_amt")
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
        if st.button("Add fee", key="d_add_fee"):
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

    if st.button("Run audit", type="primary", key="d_run"):
        audit = run_full_audit(worksheet, aggression_discount=aggression, vehicle_segment=segment)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Junk fees", f"${audit.total_junk_fees:,.2f}")
        m2.metric("Invoice floor", f"${audit.dealer_invoice_floor:,.2f}")
        m3.metric("Target OTD", f"${audit.target_counter_otd:,.2f}")
        m4.metric("Projected savings", f"${audit.projected_customer_savings:,.2f}")
        st.progress(
            audit.dealer_acceptance_probability,
            text=f"Acceptance {audit.dealer_acceptance_probability:.0%}",
        )
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


def main() -> None:
    _init_state()
    _render_brand_header()

    with st.sidebar:
        st.markdown("### Portal")
        st.session_state.portal_mode = st.radio(
            "Mode",
            ["Guided discovery", "Direct audit"],
            index=0 if st.session_state.portal_mode == "Guided discovery" else 1,
        )
        st.caption("Discovery remembers ZIP/dealer in this session.")
        if st.session_state.zip_code:
            st.write(f"Last ZIP: `{st.session_state.zip_code}`")
        if st.session_state.dealer_name and not st.session_state.any_franchise:
            st.write(f"Dealer: `{st.session_state.dealer_name}`")

    if st.session_state.portal_mode == "Direct audit":
        render_direct_audit()
        return

    _step_indicator()
    step = st.session_state.flow_step
    if step == 0:
        render_where()
    elif step == 1:
        render_what()
    elif step == 2:
        render_find()
    else:
        render_negotiate()


main()
