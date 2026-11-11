# vehicle-negotiator-engine

**Dealer-Counter AI** — analytical core for consumer automotive deal negotiation.

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
app/
  schemas.py             # Pydantic v2 domain models
  api.py                 # FastAPI (/health, /audit, /parse, /parse-and-audit)
web/
  streamlit_app.py       # minimal audit portal
tests/
  test_fee_auditor.py
  test_guardrails.py
  test_audit.py          # spec verification cases
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

## Run Streamlit

```bash
streamlit run web/streamlit_app.py
```

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
