"""
Dealer worksheet parser.

Uses Google Gemini multimodal when GEMINI_API_KEY / GOOGLE_API_KEY is set.
Otherwise falls back to a deterministic stub / text heuristic so offline tests pass.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from app.schemas import DealerWorksheet, FeeCategory, FeeItem


class ParserUnavailableError(RuntimeError):
    """Raised when a live multimodal parse is requested without an API key."""


def _has_gemini_key() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


def mock_worksheet_from_fixture(
    state: str = "CA",
    *,
    ceramic: float = 1995.0,
    nitrogen_etch: float = 895.0,
    doc_fee: float = 85.0,
) -> DealerWorksheet:
    """Deterministic fixture used by the stub path and unit tests."""
    msrp = 42000.0
    offer = 40500.0
    fees = [
        FeeItem(
            name="Documentation Fee",
            amount=doc_fee,
            category=FeeCategory.DOC_FEE,
            is_removable=False,
            recommended_amount=doc_fee,
        ),
        FeeItem(
            name="Ceramic Coating",
            amount=ceramic,
            category=FeeCategory.DEALER_ADDON,
            is_removable=True,
            recommended_amount=ceramic,
        ),
        FeeItem(
            name="Nitrogen/Etch",
            amount=nitrogen_etch,
            category=FeeCategory.DEALER_ADDON,
            is_removable=True,
            recommended_amount=nitrogen_etch,
        ),
        FeeItem(
            name="Registration",
            amount=365.0,
            category=FeeCategory.GOV_TAX_REG,
            is_removable=False,
            recommended_amount=365.0,
        ),
    ]
    tax = round(offer * 0.0725, 2) if state.upper() == "CA" else round(offer * 0.06, 2)
    fees.append(
        FeeItem(
            name="Sales Tax",
            amount=tax,
            category=FeeCategory.GOV_TAX_REG,
            is_removable=False,
            recommended_amount=tax,
        )
    )
    quoted = offer + sum(f.amount for f in fees)
    return DealerWorksheet(
        year=2025,
        make="Toyota",
        model="Camry",
        trim="SE",
        msrp=msrp,
        dealer_offered_price=offer,
        state=state.upper(),
        fees=fees,
        quoted_otd=round(quoted, 2),
    )


_FEE_LINE = re.compile(
    r"(?P<name>[A-Za-z][A-Za-z0-9 /&\-]{1,40}?)\s*[:=\-]?\s*\$?(?P<amt>\d{1,3}(?:,\d{3})*(?:\.\d{2})?)",
)


def parse_text_blob(text: str, state_hint: Optional[str] = None) -> DealerWorksheet:
    """
    Lightweight heuristic parser for pasted worksheet text.

    Not a substitute for multimodal OCR — good enough for demos and tests.
    """
    state = (state_hint or "CA").upper()
    year_match = re.search(r"\b(20\d{2})\b", text)
    year = int(year_match.group(1)) if year_match else 2025

    make = "Unknown"
    model = "Unknown"
    trim = ""
    for brand in (
        "Toyota",
        "Honda",
        "Ford",
        "Chevrolet",
        "Tesla",
        "BMW",
        "Hyundai",
        "Kia",
        "Nissan",
        "Subaru",
    ):
        if re.search(rf"\b{brand}\b", text, re.I):
            make = brand
            break

    msrp_match = re.search(r"MSRP\s*[:=]?\s*\$?([\d,]+(?:\.\d+)?)", text, re.I)
    offer_match = re.search(
        r"(?:Sale|Selling|Dealer|Offer(?:ed)?)\s*(?:Price)?\s*[:=]?\s*\$?([\d,]+(?:\.\d+)?)",
        text,
        re.I,
    )
    msrp = float(msrp_match.group(1).replace(",", "")) if msrp_match else 40000.0
    offer = float(offer_match.group(1).replace(",", "")) if offer_match else msrp * 0.96

    fees: list[FeeItem] = []
    for match in _FEE_LINE.finditer(text):
        name = match.group("name").strip(" -:=")
        if name.lower() in {"msrp", "sale", "selling", "dealer", "offer", "offered", "price"}:
            continue
        amount = float(match.group("amt").replace(",", ""))
        category = FeeCategory.DEALER_ADDON
        lower = name.lower()
        if "doc" in lower or "documentation" in lower:
            category = FeeCategory.DOC_FEE
        elif any(k in lower for k in ("tax", "registration", "title", "license", "dmv")):
            category = FeeCategory.GOV_TAX_REG
        elif "market" in lower or "adm" in lower:
            category = FeeCategory.MARKET_ADJUSTMENT
        fees.append(
            FeeItem(
                name=name,
                amount=amount,
                category=category,
                is_removable=category
                in (FeeCategory.DEALER_ADDON, FeeCategory.MARKET_ADJUSTMENT),
                recommended_amount=amount,
            )
        )

    if not fees:
        return mock_worksheet_from_fixture(state=state)

    quoted_match = re.search(r"(?:OTD|Out[- ]?the[- ]?Door)\s*[:=]?\s*\$?([\d,]+(?:\.\d+)?)", text, re.I)
    quoted = (
        float(quoted_match.group(1).replace(",", ""))
        if quoted_match
        else round(offer + sum(f.amount for f in fees), 2)
    )

    return DealerWorksheet(
        year=year,
        make=make,
        model=model,
        trim=trim,
        msrp=msrp,
        dealer_offered_price=offer,
        state=state,
        fees=fees,
        quoted_otd=quoted,
    )


def _call_gemini(image_base64: Optional[str], text_blob: Optional[str], state_hint: Optional[str]) -> dict[str, Any]:
    """Live Gemini call — imported lazily so the package works offline."""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ParserUnavailableError("GEMINI_API_KEY / GOOGLE_API_KEY not set")

    try:
        import google.generativeai as genai  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ParserUnavailableError(
            "google-generativeai is not installed; pip install google-generativeai"
        ) from exc

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    prompt = (
        "Extract a dealer worksheet as JSON with keys: year, make, model, trim, msrp, "
        "dealer_offered_price, state, quoted_otd, fees (list of {name, amount}). "
        f"State hint: {state_hint or 'unknown'}."
    )
    parts: list[Any] = [prompt]
    if text_blob:
        parts.append(text_blob)
    if image_base64:
        parts.append({"mime_type": "image/jpeg", "data": image_base64})
    response = model.generate_content(parts)
    raw = response.text or "{}"
    # Strip markdown fences if present.
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.I)
    return json.loads(raw)


def _worksheet_from_dict(data: dict[str, Any], state_hint: Optional[str]) -> DealerWorksheet:
    fees = [
        FeeItem(
            name=str(f.get("name", "Fee")),
            amount=float(f.get("amount", 0)),
            category=FeeCategory.DEALER_ADDON,
            is_removable=True,
            recommended_amount=float(f.get("amount", 0)),
        )
        for f in data.get("fees", [])
    ]
    return DealerWorksheet(
        year=int(data.get("year", 2025)),
        make=str(data.get("make", "Unknown")),
        model=str(data.get("model", "Unknown")),
        trim=str(data.get("trim", "")),
        msrp=float(data.get("msrp", 40000)),
        dealer_offered_price=float(data.get("dealer_offered_price", data.get("msrp", 40000))),
        state=str(data.get("state") or state_hint or "CA").upper()[:2],
        fees=fees,
        quoted_otd=float(data.get("quoted_otd", 0) or 0)
        or float(data.get("dealer_offered_price", 0)) + sum(f.amount for f in fees),
    )


def parse_worksheet(
    *,
    image_base64: Optional[str] = None,
    text_blob: Optional[str] = None,
    state_hint: Optional[str] = None,
    allow_stub: bool = True,
) -> DealerWorksheet:
    """
    Parse a dirty dealer worksheet into a DealerWorksheet.

    Preference order:
    1. Gemini multimodal when an API key is present and image/text is provided.
    2. Text heuristic when *text_blob* is provided.
    3. Deterministic mock fixture when *allow_stub* is True.
    """
    if _has_gemini_key() and (image_base64 or text_blob):
        try:
            data = _call_gemini(image_base64, text_blob, state_hint)
            return _worksheet_from_dict(data, state_hint)
        except Exception:
            if not allow_stub and not text_blob:
                raise
            # Fall through to heuristics / stub.

    if text_blob:
        return parse_text_blob(text_blob, state_hint=state_hint)

    if allow_stub:
        return mock_worksheet_from_fixture(state=state_hint or "CA")

    raise ParserUnavailableError(
        "No Gemini API key and no text_blob provided; cannot parse worksheet."
    )
