# vehicle-negotiator-engine

**Dealer-Counter AI** / **YourNextCar** — analytical core for consumer automotive deal negotiation.

Ingest dirty dealer worksheets, fuzzy-classify junk fees vs mandatory government fees, clamp counter-offers to an estimated invoice/holdback floor, and emit an anti-deflection remote-purchase script.

## Layout

```text
core/
  parser.py              # Gemini multimodal (or offline stub / text heuristic)
  fee_auditor.py         # rapidfuzz junk-fee classifier
  statutory_rules.py     # state doc-fee caps + tax helpers
  elasticity.py          # invoice / holdback / acceptance score
  guardrail_clamper.py   # clamped OTD counter math
  script_generator.py    # anti-deflection email + tactical plan
  discovery.py           # live web search inventory + ranking + cold outreach
app/
  schemas.py             # Pydantic v2 domain models
  api.py                 # FastAPI (/health, /audit, /parse, /parse-and-audit, /discover)
web/
  streamlit_app.py       # guided discovery + audit portal
  static_mock/           # self-contained HTML mock for github.io mirroring
tests/
  test_fee_auditor.py
  test_guardrails.py
  test_audit.py          # spec verification cases
  test_discovery.py      # mocked search ranking / parsing
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional Gemini parser:

```bash
pip install google-generativeai
export GEMINI_API_KEY=...
```

Without a key, `/parse` and the Streamlit fixture path use a deterministic stub.

## Guided discovery UI

The Streamlit portal opens on a **YourNextCar** multi-step flow:

1. **Where** — ZIP / metro + optional dealer (or any nearby franchise)
2. **What** — year / make / model / trim, new vs used, optional OTD ceiling
3. **Find** — live web search for inventory; ranked list with price / dealer / days / link
4. **Negotiate** — upload/paste a quote → existing audit, **or** generate a cold outreach script for the picked unit

Session remembers last ZIP / dealer. Thin inventory surfaces same-brand competitor tips. Selecting a listing shows junk-fee radar tips (brand ADM + state doc-fee cap).

### Search provider

Default live provider: **DuckDuckGo** via the [`ddgs`](https://pypi.org/project/ddgs/) package — **no API key required**.

| Env var | Purpose |
|---------|---------|
| `DISCOVERY_SEARCH_PROVIDER` | Optional override name (`duckduckgo` default). Other keyed backends (Tavily / Brave / SerpAPI) are reserved for a later drop-in. |
| `GEMINI_API_KEY` | Optional worksheet image parse (unchanged). |

Tests inject fixtures / mock search functions so CI never hits the network.

### Run Streamlit

```bash
streamlit run web/streamlit_app.py
```

Sidebar toggle: **Guided discovery** (default) or **Direct audit** (legacy single-page worksheet portal).

### Static mock (github.io)

Self-contained preview of the guided flow (no Python):

```text
web/static_mock/index.html
web/static_mock/styles.css
web/static_mock/app.js
```

Open `web/static_mock/index.html` in a browser, or serve the folder:

```bash
python3 -m http.server 8080 --directory web/static_mock
```

Another worker may mirror this folder onto `arthursetiawan.github.io`.

## Run tests

```bash
pytest -q
```

## Run API

```bash
uvicorn app.api:app --reload --port 8000
```

- `GET /health`
- `POST /audit` — body: `{ "worksheet": { ... }, "aggression_discount": 0.03, "vehicle_segment": "mainstream" }`
- `POST /parse` — body: `{ "text_blob": "...", "state_hint": "CA" }` (or `image_base64` with Gemini key)
- `POST /parse-and-audit`
- `POST /discover` — body: `{ "zip_code": "94107", "year": 2025, "make": "Toyota", "model": "Camry", "condition": "new", "state": "CA" }`

## Statutory notes (v0)

| State | Doc fee rule |
|-------|----------------|
| CA | Cap **$85** |
| WA | Cap **$200** |
| TX | Cap **$150** |
| Uncapped (e.g. FL, VA) | Flag any doc fee **>$399** as *Excessive / High-Negotiation Target* |

Tax rates in `statutory_rules.py` are planning approximations (state-level only). County/city tables are a follow-up.

## License

Proprietary — all rights reserved unless otherwise noted by the owner.
