"""Live inventory discovery: web search, ranking, junk-fee tips, cold outreach."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable, Iterable, List, Optional, Sequence

from core.statutory_rules import DOC_FEE_CAPS, UNCAPPED_EXCESSIVE_THRESHOLD, get_doc_fee_cap

# Brands where ADM / "market adjustment" shows up often enough to tip the shopper.
_ADM_PRONE_MAKES = {
    "toyota",
    "honda",
    "lexus",
    "subaru",
    "porsche",
    "bmw",
    "mercedes-benz",
    "mercedes",
    "chevrolet",
    "gmc",
    "ford",
}

_PRICE_RE = re.compile(
    r"(?<!\w)(?:USD\s*)?(?:\$|US\$)\s*([0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]{2})?|[0-9]{4,6}(?:\.[0-9]{2})?)",
    re.IGNORECASE,
)
_DAYS_RE = re.compile(
    r"(\d+)\s*\+?\s*days?\s*(?:on\s*(?:lot|market|site))?",
    re.IGNORECASE,
)
_STOCK_RE = re.compile(r"(?:stock|stk)[#:\s-]*([A-Z0-9-]{4,})", re.IGNORECASE)
_VIN_RE = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b", re.IGNORECASE)

# Domains that usually mean real inventory vs editorial fluff.
_INVENTORY_HOST_BONUS = (
    "cars.com",
    "autotrader.com",
    "cargurus.com",
    "carfax.com",
    "edmunds.com",
    "truecar.com",
    "carsdirect.com",
    "dealer.com",
    "dealeron.com",
)

SearchFn = Callable[[str, int], List[dict]]


@dataclass(frozen=True)
class DiscoveryQuery:
    zip_code: str
    year: Optional[int] = None
    make: str = ""
    model: str = ""
    trim: str = ""
    condition: str = "new"  # new | used | any
    dealer_name: str = ""
    budget_otd: Optional[float] = None
    state: str = ""
    max_results: int = 8


@dataclass
class InventoryListing:
    title: str
    url: str
    snippet: str = ""
    price: Optional[float] = None
    dealer_name: Optional[str] = None
    days_listed: Optional[int] = None
    stock_number: Optional[str] = None
    vin: Optional[str] = None
    score: float = 0.0
    source: str = "duckduckgo"


@dataclass
class DiscoveryResult:
    query: DiscoveryQuery
    listings: List[InventoryListing] = field(default_factory=list)
    search_query: str = ""
    provider: str = "duckduckgo"
    competitor_suggestions: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


def build_search_query(query: DiscoveryQuery) -> str:
    """Compose a practical web-search string for nearby inventory."""
    parts: List[str] = []
    if query.condition and query.condition != "any":
        parts.append(query.condition)
    if query.year:
        parts.append(str(query.year))
    if query.make:
        parts.append(query.make.strip())
    if query.model:
        parts.append(query.model.strip())
    if query.trim:
        parts.append(query.trim.strip())
    parts.append("for sale")
    if query.dealer_name.strip():
        parts.append(query.dealer_name.strip())
    else:
        parts.append("dealer inventory")
    zip_code = (query.zip_code or "").strip()
    if zip_code:
        parts.append(f"near {zip_code}")
    if query.budget_otd and query.budget_otd > 0:
        parts.append(f"under ${int(query.budget_otd):,}")
    return " ".join(p for p in parts if p)


def parse_price(text: str) -> Optional[float]:
    """Extract the most plausible asking price from title/snippet text."""
    if not text:
        return None
    candidates: List[float] = []
    for match in _PRICE_RE.finditer(text):
        raw = match.group(1).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        # Vehicle prices cluster well above accessories / fees.
        if 5_000 <= value <= 250_000:
            candidates.append(value)
    if not candidates:
        return None
    # Prefer the first in-range price (usually the asking figure in listings).
    return candidates[0]


def parse_days_listed(text: str) -> Optional[int]:
    if not text:
        return None
    match = _DAYS_RE.search(text)
    if not match:
        return None
    days = int(match.group(1))
    return days if 0 < days < 1000 else None


def parse_stock_number(text: str) -> Optional[str]:
    if not text:
        return None
    match = _STOCK_RE.search(text)
    return match.group(1).upper() if match else None


def parse_vin(text: str) -> Optional[str]:
    if not text:
        return None
    match = _VIN_RE.search(text)
    return match.group(1).upper() if match else None


def _guess_dealer_name(title: str, snippet: str, preferred: str = "") -> Optional[str]:
    preferred = (preferred or "").strip()
    blob = f"{title} {snippet}"
    if preferred and preferred.lower() in blob.lower():
        return preferred
    # "… at Steve's Toyota of Oakland" / "from Honda of Downtown"
    at_match = re.search(
        r"\b(?:at|from|by)\s+([A-Z][\w'&.\- ]{2,40}?(?:Motors|Auto|Automotive|Cars|Honda|Toyota|Ford|Chevy|Chevrolet|BMW|Dealer|Dealership))",
        blob,
    )
    if at_match:
        return at_match.group(1).strip(" -|,.")
    return preferred or None


def raw_result_to_listing(raw: dict, preferred_dealer: str = "") -> InventoryListing:
    """Normalize a search-provider dict into an InventoryListing."""
    title = str(raw.get("title") or raw.get("Title") or "").strip()
    url = str(raw.get("href") or raw.get("url") or raw.get("link") or "").strip()
    snippet = str(raw.get("body") or raw.get("snippet") or raw.get("description") or "").strip()
    blob = f"{title}\n{snippet}"
    return InventoryListing(
        title=title or url or "Listing",
        url=url,
        snippet=snippet,
        price=parse_price(blob),
        dealer_name=_guess_dealer_name(title, snippet, preferred_dealer),
        days_listed=parse_days_listed(blob),
        stock_number=parse_stock_number(blob),
        vin=parse_vin(blob),
        source=str(raw.get("source") or "duckduckgo"),
    )


def _host_bonus(url: str) -> float:
    host = url.lower()
    return 2.5 if any(domain in host for domain in _INVENTORY_HOST_BONUS) else 0.0


def score_listing(listing: InventoryListing, query: DiscoveryQuery) -> float:
    """Higher is better. Prefer priced inventory hits near the shopper's intent."""
    score = 0.0
    blob = f"{listing.title} {listing.snippet}".lower()
    make = (query.make or "").lower()
    model = (query.model or "").lower()
    trim = (query.trim or "").lower()
    dealer = (query.dealer_name or "").lower()

    if make and make in blob:
        score += 3.0
    if model and model in blob:
        score += 3.0
    if trim and trim in blob:
        score += 1.5
    if query.year and str(query.year) in blob:
        score += 1.5
    if dealer and dealer in blob:
        score += 2.0
    if listing.price is not None:
        score += 2.0
        if query.budget_otd and query.budget_otd > 0:
            if listing.price <= query.budget_otd:
                score += 2.0
            else:
                # Soft penalty for over-budget units.
                overrun = (listing.price - query.budget_otd) / query.budget_otd
                score -= min(3.0, overrun * 4.0)
    if listing.days_listed is not None:
        # Aged inventory is more negotiable.
        if listing.days_listed >= 45:
            score += 1.5
        elif listing.days_listed >= 21:
            score += 0.75
    if listing.vin or listing.stock_number:
        score += 1.0
    score += _host_bonus(listing.url)
    if "for sale" in blob or "inventory" in blob or "priced" in blob:
        score += 0.5
    return round(score, 3)


def rank_listings(
    listings: Sequence[InventoryListing],
    query: DiscoveryQuery,
    *,
    limit: Optional[int] = None,
) -> List[InventoryListing]:
    """Score, sort descending, and optionally trim the list."""
    scored: List[InventoryListing] = []
    for item in listings:
        clone = InventoryListing(**{**item.__dict__})
        clone.score = score_listing(clone, query)
        scored.append(clone)
    scored.sort(key=lambda x: (-x.score, x.price if x.price is not None else 1e12))
    if limit is not None:
        return scored[: max(0, limit)]
    return scored


def default_ddgs_search(search_query: str, max_results: int = 8) -> List[dict]:
    """Live DuckDuckGo text search via the `ddgs` package (no API key)."""
    try:
        from ddgs import DDGS
    except ImportError as exc:  # pragma: no cover - exercised when deps missing
        raise RuntimeError(
            "ddgs is required for live discovery search. Install with: pip install ddgs"
        ) from exc

    results: List[dict] = []
    with DDGS() as client:
        for row in client.text(search_query, max_results=max_results):
            if isinstance(row, dict):
                row = dict(row)
                row.setdefault("source", "duckduckgo")
                results.append(row)
    return results


def resolve_search_fn(override: Optional[SearchFn] = None) -> tuple[SearchFn, str]:
    """Pick a search backend. Override wins; else DuckDuckGo (`ddgs`)."""
    if override is not None:
        return override, "mock"
    provider = (os.environ.get("DISCOVERY_SEARCH_PROVIDER") or "duckduckgo").strip().lower()
    if provider in {"duckduckgo", "ddgs", "ddg"}:
        return default_ddgs_search, "duckduckgo"
    # Unknown provider names still fall back to DuckDuckGo so the UI stays usable.
    return default_ddgs_search, "duckduckgo"


def competitor_suggestions(make: str, zip_code: str, dealer_name: str = "") -> List[str]:
    """Same-brand franchise prompts when preferred inventory is thin."""
    make = (make or "").strip() or "the brand"
    zip_code = (zip_code or "").strip() or "your ZIP"
    dealer = (dealer_name or "").strip()
    tips = [
        f"Search other {make} franchises within ~25 miles of {zip_code} and ask for internet-manager OTD.",
        f"Call 2–3 same-brand stores near {zip_code}; aged units transfer more readily than same-day pulls.",
    ]
    if dealer:
        tips.insert(
            0,
            f"If {dealer} is thin, request a dealer-trade quote from the next-closest {make} franchise.",
        )
    return tips


def junk_fee_radar_tips(make: str, state: str) -> List[str]:
    """Tip cards once a listing is selected — brand ADM + state doc-fee reality."""
    tips: List[str] = []
    make_l = (make or "").strip().lower()
    state_u = (state or "").strip().upper()
    if make_l in _ADM_PRONE_MAKES:
        tips.append(
            f"{make.strip().title() if make else 'This brand'} often carries a Market Adjustment / ADM "
            "on constrained trims — treat it as discretionary and strike it from the Buyer's Order."
        )
    else:
        tips.append(
            "Scan the worksheet for Market Adjustment, ceramic, etch, nitrogen, and protection packages — "
            "these are classic negotiation targets."
        )

    cap = get_doc_fee_cap(state_u) if state_u else None
    if state_u and cap is not None:
        tips.append(
            f"{state_u} documentation fee statutory ceiling is ${cap:,.0f}. "
            "Anything above that is a junk-fee strike, not a government charge."
        )
    elif state_u:
        tips.append(
            f"{state_u} has no hard doc-fee cap in this engine — flag anything above "
            f"${UNCAPPED_EXCESSIVE_THRESHOLD:,.0f} as Excessive / High-Negotiation Target."
        )
    else:
        tips.append(
            "Set your state so we can apply the right doc-fee cap "
            f"(CA ${DOC_FEE_CAPS['CA']:.0f} / WA ${DOC_FEE_CAPS['WA']:.0f} / TX ${DOC_FEE_CAPS['TX']:.0f})."
        )

    tips.append(
        "Ask for a signed Buyer's Order Out-The-Door before any showroom visit — "
        "payment packing usually appears after you sit down."
    )
    return tips


def generate_cold_outreach(
    listing: InventoryListing,
    *,
    year: Optional[int] = None,
    make: str = "",
    model: str = "",
    trim: str = "",
    budget_otd: Optional[float] = None,
    zip_code: str = "",
) -> str:
    """
    Anti-deflection cold email aimed at a searched unit (no worksheet yet).

    Uses the listing asking price as the conversation baseline and optionally
    clamps the ask to the shopper's OTD ceiling.
    """
    vehicle_bits = [
        str(year) if year else "",
        make.strip(),
        model.strip(),
        trim.strip(),
    ]
    vehicle = " ".join(b for b in vehicle_bits if b).strip() or listing.title
    dealer = listing.dealer_name or "Internet Sales Manager"
    ref_parts: List[str] = []
    if listing.stock_number:
        ref_parts.append(f"stock #{listing.stock_number}")
    if listing.vin:
        ref_parts.append(f"VIN {listing.vin}")
    ref = ", ".join(ref_parts) if ref_parts else "the unit linked below"

    asking = listing.price
    target_line: str
    if budget_otd and budget_otd > 0:
        if asking and asking > budget_otd:
            target_line = (
                f"I am prepared to proceed at an Out-The-Door maximum of ${budget_otd:,.2f} "
                f"(below the advertised asking figure of ${asking:,.2f})."
            )
        else:
            target_line = (
                f"I am prepared to proceed at an Out-The-Door maximum of ${budget_otd:,.2f}."
            )
    elif asking:
        # Soft open: ~3% under advertised asking as a remote-close probe.
        probe = round(asking * 0.97, 2)
        target_line = (
            f"Your listing shows approximately ${asking:,.2f}. I am prepared to move today at an "
            f"Out-The-Door figure of ${probe:,.2f}, contingent on a signed Buyer's Order with "
            f"no market adjustment, ceramic, etch, nitrogen, or protection packages."
        )
    else:
        target_line = (
            "Please send a complete Out-The-Door Buyer's Order (vehicle price, approved doc fee, "
            "tax, title, and registration only — no add-ons) so I can respond with a firm number today."
        )

    location = f" near {zip_code}" if zip_code else ""
    return (
        f"Subject: Remote purchase inquiry — {vehicle}{location}\n\n"
        f"Hello {dealer},\n\n"
        f"I am interested in {ref} ({vehicle}) and would like to complete this purchase remotely.\n\n"
        f"{target_line}\n\n"
        f"Please reply with a signed Buyer's Order matching that Out-The-Door figure. "
        f"I can place an electronic deposit and remote credit application once figures are locked. "
        f"I will not visit the showroom before the OTD is confirmed in writing.\n\n"
        f"Listing for reference: {listing.url or 'n/a'}\n\n"
        f"Please confirm yes/no today so I can either proceed or move to another inventory unit.\n\n"
        f"Regards"
    )


def otd_request_draft(
    listing: InventoryListing,
    *,
    target_otd: Optional[float] = None,
    vehicle_label: str = "",
) -> dict[str, str]:
    """One-click email + SMS drafts requesting a locked OTD Buyer's Order."""
    vehicle = vehicle_label or listing.title
    ref = listing.stock_number or listing.vin or "your in-stock unit"
    otd_phrase = (
        f"Out-The-Door ${target_otd:,.2f}"
        if target_otd and target_otd > 0
        else "a complete Out-The-Door Buyer's Order"
    )
    email = (
        f"Subject: Request — signed Buyer's Order for {vehicle}\n\n"
        f"Please send a signed Buyer's Order for {ref} reflecting {otd_phrase}. "
        f"Tax/title/license + approved doc fee only — no ADM or protection products. "
        f"Ready to e-deposit on receipt."
    )
    sms = (
        f"Hi — requesting signed BO for {ref} ({vehicle}) at {otd_phrase}. "
        f"Remote close OK. No ADM/add-ons. Thanks."
    )
    return {"email": email, "sms": sms}


def search_inventory(
    query: DiscoveryQuery,
    *,
    search_fn: Optional[SearchFn] = None,
    raw_results: Optional[Iterable[dict]] = None,
) -> DiscoveryResult:
    """
    Run live (or injected) web search, normalize, and rank inventory hits.

    Pass ``raw_results`` or ``search_fn`` in tests to avoid network I/O.
    """
    search_query = build_search_query(query)
    provider = "duckduckgo"
    rows: List[dict]
    if raw_results is not None:
        rows = list(raw_results)
        provider = "fixture"
    else:
        fn, provider = resolve_search_fn(search_fn)
        rows = list(fn(search_query, query.max_results))

    listings = [raw_result_to_listing(row, preferred_dealer=query.dealer_name) for row in rows]
    ranked = rank_listings(listings, query, limit=query.max_results)

    notes: List[str] = []
    competitors: List[str] = []
    if len(ranked) < 3:
        notes.append("Thin inventory from search — consider same-brand competitors nearby.")
        competitors = competitor_suggestions(query.make, query.zip_code, query.dealer_name)

    return DiscoveryResult(
        query=query,
        listings=ranked,
        search_query=search_query,
        provider=provider,
        competitor_suggestions=competitors,
        notes=notes,
    )
