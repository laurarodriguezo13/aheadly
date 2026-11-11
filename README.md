# Aheadly

*Clarity today. A brighter tomorrow.*

Aheadly is an AI financial co-pilot for owners of small, local businesses. It checks the owner's cash every day, warns weeks before cash runs low, explains why in plain words, and lets the owner test a decision ("What if I buy the oven next month instead?") before making it.

Built for **AI-Driven App Development** (Babson, Prof. Matthew Macarty) by Laura Rodriguez, Fernando Siman, Mauricio Hasbun and Miguel Royo. Python 3.11 + Streamlit, SQLite, Prophet, Gemini or Claude.

## Run it in 5 steps (no keys needed)

```bash
cd Aheadly
uv sync                      # or: python3.11 -m venv .venv && pip install -r requirements.txt
cp .env.example .env         # defaults: DEMO_MODE=true, LLM_PROVIDER=stub
uv run streamlit run app.py
# Accounts → upload a bank statement (+ optional upcoming payments),
#            or click "Try the example bakery" to see it with no files of your own
```

Optional, a real language model: set `LLM_PROVIDER=gemini` and `GEMINI_API_KEY=...` in `.env` (or `anthropic` + `ANTHROPIC_API_KEY`). Keys never go anywhere else.

Other commands:

```bash
uv run pytest -q                      # all offline, a few seconds; ends with the test-business scorecard
uv run black .                        # formatting
uv run python -m aheadly.jobs.daily_run   # the daily check from the command line (cron-able)
```

## Demo script (storyboard frames 1 to 6)

1. **Guessing.** Fresh start: every visitor gets an empty app; the Accounts page shows the upload card.
2. **Connect once.** Upload Maria's bank statement and her upcoming payments: 12 months of Panadería La Esquina come in, the balance is read from the statement, "All set".
3. **Always watching.** Dashboard: $8,200 today, 8-week forecast crossing the red low cash line in week 5.
4. **Early warning.** Alerts badge shows 1. The alert explains the week-5 cluster (quarterly flour order $4,000 and inventory restock $1,200 land in the same week, after the new oven $7,500) and lists three actions.
5. **Ask in plain words.** Ask Aheadly: "What if I buy the new oven next month instead?" → the model calls `run_scenario`, and the answer plus the best/base/worst card show cash staying above the $2,000 line even in the worst case ("That looks safe").
6. **Act with confidence.** *Save as my plan*: the oven moves, the forecast reruns, the alert resolves.

Maria's two files are created outside the app, relative to the day they are made: make them again on demo day so the statement ends yesterday. The built-in demo data (`DemoConnector`) is only used by the tests.

## Architecture (matches the Milestone 1 component diagram)

```
Streamlit UI (app.py, aheadly/ui/views, aheadly/ui)   Application layer
   │  Get Insights
App Core (aheadly/core/app_core.py)             orchestrates: sync → forecast → alert rules → alerts
   │  Run Forecast                 │  Explain Results
Forecast Engine (aheadly/ai)      Insight Translator (aheadly/ai)     AI layer
   │  Read/Write Data               │  Generate Text
Data Repository (aheadly/data)    LLM API (Gemini / Claude / stub)   Data + external
   │  Sync Transactions
Connectors (demo, CSV, Plaid*, QuickBooks*)                           * scaffolds, next milestone
```

Rules we keep: the UI only calls `AppCore`; only the Insight Translator talks to the LLM; only connectors talk to banks; only the Repository talks SQL.

| Folder | What lives there |
|---|---|
| `app.py` | Streamlit entry: page config, sidebar logo, `st.navigation` |
| `aheadly/ui/views/` | the six page scripts (Dashboard, Alerts, Ask Aheadly, What-if, Accounts, Settings) |
| `aheadly/ui/` | brand CSS on top of `.streamlit/config.toml`, all copy strings, cards, charts (weekly lows), cached bootstrap |
| `aheadly/core/` | `AppCore` and the deterministic `alert_rules` |
| `aheadly/ai/` | `ForecastEngine` + models, `scenarios`, `InsightTranslator`, `llm_client`, `tools`, `guardrails`, `prompts`, `templates` |
| `aheadly/data/` | `schema.sql`, `Repository`, `seed_demo`, `connectors/` |
| `aheadly/jobs/` | `daily_run` (cron-able) |
| `tests/` | pytest: unit tests per component, the demo script as a functional test, and `test_businesses.py`, which runs the six test businesses in `tests/businesses/` against their answer keys |
| `docs/` | UML diagrams, milestone check-in |

## How the AI works

* **Forecast Engine.** History minus scheduled-type payments is fitted with Prophet (weekly seasonality, Colombian holidays, flat trend). 500 sampled future paths + known scheduled items (bills, payroll, rent, receivables, planned purchases) are cumulated from today's balance; worst / base / best case are the 10th / 50th / 90th percentiles. A seasonal-naive baseline is always available; Settings → *Compare forecast models* runs the backtest (MAE on the last 4 weeks).
* **Alert rules** are deterministic code: shortfall when the base case drops below the low cash line, idle cash when even the worst case stays above three months of outflows. Rules build a *facts* object; the LLM only writes the words.
* **Insight Translator** answers chat questions with function calling over six tools (`get_cash_summary`, `get_forecast`, `get_upcoming_outflows`, `get_transactions`, `run_scenario`, `get_alerts`).
* **Guardrail.** Every number in an answer must appear in the facts or tool outputs of that turn. Otherwise: one retry, then a deterministic template answer. The LLM never invents figures.
* **Providers.** `LLM_PROVIDER=gemini` (course default, via Google's OpenAI-compatible endpoint), `anthropic` (official SDK), or `stub` (offline rules + templates, used for the demo and the tests). All three expose the same `chat()`.

Vendor notes: Gemini free tier has per-minute request limits; Claude is pay-per-token. Prophet is MIT licensed; all other packages are MIT/BSD/Apache.

## Status

See `PROGRESS.md` for what is done and what is next, and `DECISIONS.md` for every deviation from the spec.

## Providers, rate limits and cost

| Provider | How it is called | Free-tier limit seen | Cost |
|---|---|---|---|
| Gemini (`gemini-3.5-flash-lite`, default) | `openai` package against Google's OpenAI-compatible endpoint | free tier is per model and per day (the non-lite 3.x models allowed only 20 requests a day in Nov 2026); one chat question uses 2 to 3 requests | free tier |
| Claude (`claude-sonnet-5-5`) | official `anthropic` SDK | pay as you go | about 1 cent per question |
| Stub | no network | none | free |

If Gemini answers 429 or 503 the client waits as long as Google asks and retries; if it still fails, the chat answers from the offline planner and templates and shows a small note. Switch models with `GEMINI_MODEL` in `.env`.

## Uploading your data

Accounts → upload a bank statement (CSV or Excel). Headers may be the app's (`date, description, amount[, category]`) or a bank's (`Date, Description, Debit, Credit, Balance`, or Spanish: `Fecha, Descripción, Valor, Saldo`, `Fecha Movimiento`, `Monto`, `Saldo Disponible`…). Real bank exports are fine: comma, semicolon or tab separated, UTF-8 or Windows-1252, bank lines above the header, newest line first, dates like `10/11/2026` (day first), `11-nov-2026` or `2026-11-10`, amounts like `1.250,00`, `1,250.00`, `$ 2.000` or `(900,50)`. If the file has a Balance column, the current balance is read from its newest line and checked line by line; otherwise type it in. Lines that can't be read are left out and counted, never turned into $0. If the statement ends before yesterday, the forecast starts the day after it ends, and the app says so.

Optionally upload a second file with upcoming **one-off** payments and expected income (`Date, Description, Amount`, minus = money going out, same formats as above), for example a planned purchase, a big supplier order or a customer order. Regular payments (payroll, rent, suppliers) are learned from the statement, so don't list them again: they would be counted twice.

No files at hand? On Accounts, **Try the example bakery** loads Panadería La Esquina (`aheadly/examples/`): a year of statements from the test businesses plus the one-off payments its owner knows about. It is always shown as of the day after its statement ends (Nov 11, 2026). Settings → Start over goes back to your own upload.

A sample bank export of the demo bakery is still in `data/samples/` for testing the import (regenerate it with `uv run python -m scripts.make_sample_export`). For realistic files, use the statements in `tests/businesses/<business>/statements/`: six test businesses made separately from the code, each with an answer key (DECISIONS #25).
