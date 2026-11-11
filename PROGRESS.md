# PROGRESS

Short state file so a fresh session (or teammate) can continue.

## Done (Milestone 2 check-in, 2026-11-09)
- Repo skeleton with `uv` (Python 3.11), `.env.example`, `.gitignore`, `requirements.txt`, CI workflow (black, secret scan, pytest).
- Data layer: `schema.sql`, `Repository` (sqlite3), demo seed for Panadería La Esquina, demo connector, CSV/Excel import with bank-style headers plus a sample bank export in `data/samples/`, Plaid/QuickBooks scaffolds.
- Forecast Engine: Prophet + seasonal-naive baseline, 500-path simulation, scheduled items, backtest.
- Scenarios: six adjustment types.
- Alert rules (shortfall, idle cash, de-duplication, resolution) and App Core daily run.
- Insight Translator with function calling (6 tools), number guardrail, template fallback; stub / Gemini / Claude clients.
- Streamlit UI: Dashboard, Alerts, Ask Aheadly (chat + scenario card + save plan), What-if form, Accounts, Settings. Brand theme via native Streamlit theme options; 2x screenshots in `docs/screenshots/`.
- 41 pytest tests incl. the demo script and provider-down fallbacks as functional tests. All offline.
- Gemini verified live (2026-11-10): `gemini-3.5-flash-lite` through the OpenAI-compatible endpoint, tool calling with Gemini 3 thought signatures, guardrail passing on the alert and the four demo questions, about 2 to 5 s per answer.
- Fresh start for every visitor (2026-11-10): each browser session gets its own App Core and in-memory database (`aheadly/core/session.py`, `PER_VISITOR_DATA`), 44 tests.
- Honest verdicts (2026-11-10): three risk levels (act now / keep an eye on it / safe) using the worst case, in the chat, What-if, templates and dashboard; 49 tests.
- Small fixes (2026-11-10): "Lowest projected" counts today's balance, "next month" questions answer up to the end of next month (`get_forecast` `until`), Ask button no longer cut off, no "every day" promise; 53 tests.

## Next (for the final demonstration)
1. Plaid sandbox: public token → access token → `/transactions/sync`, `/accounts/balance/get` (plaid-python).
2. QuickBooks sandbox OAuth: open Bills → scheduled bills, open Invoices → receivables.
3. Gemini verified live on 2026-11-10 (`gemini-3.5-flash-lite`, tool calling, guardrail). Still to do: run the full demo script twice more on a fresh day and tune prompts from what you see; keep the free-tier daily quota in mind (do not rehearse 50 times on one key).
4. Deploy to Streamlit Community Cloud; smoke tests; screenshots in `docs/`.
5. Nice-to-haves: Spanish copy (`copy.py`), transaction categoriser (Hugging Face zero-shot), utilities-trend insight.

## Open decisions
- Whether to encrypt stored Plaid tokens with Fernet (spec) or keep sandbox tokens in `.env` only.
- Whether idle-cash alerts should be shown on the dashboard or only in Alerts.
