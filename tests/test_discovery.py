"""Mocked discovery search: parsing, ranking, cold outreach, API /discover."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api import app
from core.discovery import (
    DiscoveryQuery,
    InventoryListing,
    build_search_query,
    generate_cold_outreach,
    junk_fee_radar_tips,
    otd_request_draft,
    parse_days_listed,
    parse_price,
    parse_stock_number,
    parse_vin,
    rank_listings,
    raw_result_to_listing,
    search_inventory,
)


FIXTURE_ROWS = [
    {
        "title": "2025 Toyota Camry SE for sale at City Toyota — $35,980",
        "href": "https://www.cars.com/vehicledetail/abc123",
        "body": "New 2025 Toyota Camry SE. Stock #CT-90211. 41 days on market. Priced at $35,980 near 94107.",
    },
    {
        "title": "How to negotiate a Toyota Camry",
        "href": "https://www.example.com/blog/negotiate-camry",
        "body": "Editorial tips only. No inventory.",
    },
    {
        "title": "2025 Honda Accord EX-L — $33,500",
        "href": "https://www.autotrader.com/cars-for-sale/accord",
        "body": "Wrong make for this shopper. 12 days on lot.",
    },
    {
        "title": "2025 Toyota Camry SE FWD inventory",
        "href": "https://www.cargurus.com/Cars/inventory-camry",
        "body": "Asking $37,250 at Maguire Toyota. VIN 4T1G11AK5SU000001. 9 days on market.",
    },
]


def test_build_search_query_includes_zip_and_vehicle():
    q = DiscoveryQuery(
        zip_code="94107",
        year=2025,
        make="Toyota",
        model="Camry",
        trim="SE",
        condition="new",
        budget_otd=38000,
    )
    text = build_search_query(q)
    assert "2025" in text
    assert "Toyota" in text
    assert "Camry" in text
    assert "near 94107" in text
    assert "under $38,000" in text


def test_parse_price_and_days_and_ids():
    blob = "Priced at $35,980. Stock #CT-90211. 41 days on market. VIN 4T1G11AK5SU000001"
    assert parse_price(blob) == 35980.0
    assert parse_days_listed(blob) == 41
    assert parse_stock_number(blob) == "CT-90211"
    assert parse_vin(blob) == "4T1G11AK5SU000001"
    assert parse_price("Accessory $199 only") is None


def test_rank_listings_prefers_matching_priced_inventory():
    query = DiscoveryQuery(
        zip_code="94107",
        year=2025,
        make="Toyota",
        model="Camry",
        trim="SE",
        budget_otd=38000,
        max_results=5,
    )
    listings = [raw_result_to_listing(row) for row in FIXTURE_ROWS]
    ranked = rank_listings(listings, query)
    assert ranked[0].price == 35980.0
    assert "Camry" in ranked[0].title
    assert "cars.com" in ranked[0].url
    # Editorial / wrong-make should not top the list.
    assert "negotiate" not in ranked[0].title.lower()
    assert "Accord" not in ranked[0].title


def test_search_inventory_uses_injected_raw_results_no_network():
    query = DiscoveryQuery(
        zip_code="94107",
        year=2025,
        make="Toyota",
        model="Camry",
        max_results=3,
    )
    result = search_inventory(query, raw_results=FIXTURE_ROWS)
    assert result.provider == "fixture"
    assert result.search_query
    assert len(result.listings) <= 3
    assert result.listings[0].score >= result.listings[-1].score


def test_search_inventory_accepts_mock_search_fn():
    def fake_search(q: str, max_results: int):
        assert "Camry" in q
        return FIXTURE_ROWS[:max_results]

    result = search_inventory(
        DiscoveryQuery(zip_code="94107", make="Toyota", model="Camry", max_results=2),
        search_fn=fake_search,
    )
    assert result.provider == "mock"
    assert len(result.listings) == 2


def test_thin_inventory_suggests_competitors():
    result = search_inventory(
        DiscoveryQuery(zip_code="94107", make="Toyota", model="Camry", dealer_name="City Toyota"),
        raw_results=FIXTURE_ROWS[:1],
    )
    assert result.notes
    assert result.competitor_suggestions
    assert any("Toyota" in tip for tip in result.competitor_suggestions)


def test_junk_fee_radar_and_cold_outreach():
    tips = junk_fee_radar_tips("Toyota", "CA")
    assert any("85" in t for t in tips)
    assert any("Market Adjustment" in t or "ADM" in t for t in tips)

    listing = InventoryListing(
        title="2025 Toyota Camry SE",
        url="https://example.com/camry",
        price=35980.0,
        dealer_name="City Toyota",
        stock_number="CT-90211",
    )
    script = generate_cold_outreach(
        listing,
        year=2025,
        make="Toyota",
        model="Camry",
        trim="SE",
        budget_otd=35000,
        zip_code="94107",
    )
    assert "Out-The-Door" in script
    assert "35,000.00" in script
    assert "CT-90211" in script
    assert "City Toyota" in script

    drafts = otd_request_draft(listing, target_otd=35000.0, vehicle_label="2025 Toyota Camry")
    assert "Buyer's Order" in drafts["email"]
    assert "CT-90211" in drafts["sms"]


def test_discover_api_with_monkeypatched_search(monkeypatch):
    def fake_search(q: str, max_results: int = 8):
        return FIXTURE_ROWS

    monkeypatch.setattr("core.discovery.default_ddgs_search", fake_search)
    client = TestClient(app)
    response = client.post(
        "/discover",
        json={
            "zip_code": "94107",
            "year": 2025,
            "make": "Toyota",
            "model": "Camry",
            "trim": "SE",
            "condition": "new",
            "state": "CA",
            "max_results": 4,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["provider"] == "duckduckgo"
    assert payload["search_query"]
    assert len(payload["listings"]) >= 1
    assert payload["listings"][0]["title"]
    assert payload["junk_fee_tips"]
