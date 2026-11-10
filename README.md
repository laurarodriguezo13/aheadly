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
# Accounts → "Use demo data"
```

Optional, a real language model: set `LLM_PROVIDER=gemini` and `GEMINI_API_KEY=...` in `.env` (or `anthropic` + `ANTHROPIC_API_KEY`). Keys never go anywhere else.

Other commands:

```bash
uv run pytest -q                      # 34 tests, all offline, < 1 s
uv run black .                        # formatting
uv run python -m aheadly.jobs.daily_run   # the daily check from the command line (cron-able)
```

## Demo script (storyboard frames 1 to 6)

1. **Guessing.** Fresh start: the Accounts page shows the welcome card, no data yet.
2. **Connect once.** Click *Use demo data*: 12 months of Panadería La Esquina sync in, "All set".
3. **Always watching.** Dashboard: $8,200 today, 8-week forecast crossing the red low cash line in week 5.
4. **Early warning.** Alerts badge shows 1. The alert explains the week-5 cluster (quarterly flour order $4,000, inventory $1,200, rent $900 landing with the new oven $7,500) and lists three actions.
5. **Ask in plain words.** Ask Aheadly: "What if I buy the new oven next month instead?" → the model calls `run_scenario`, and the answer plus the best/base/worst card show cash staying above $3,000.
6. **Act with confidence.** *Save as my plan*: the oven moves, the forecast reruns, the alert resolves.

The story is generated relative to the run date; it is tuned for demos between the 1st and the 24th of a month.

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
| `tests/` | pytest: unit tests per component plus the demo script as a functional test |
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

## Importing a bank export

Accounts → *Import a bank export instead*. CSV or Excel; headers may be the app's (`date, description, amount[, category]`) or a bank's (`Date, Description, Debit, Credit, Balance`, Spanish accepted). A ready-made sample bank export of the demo bakery is in `data/samples/` and downloadable from that page; regenerate it with `uv run python -m scripts.make_sample_export`. Scheduled items (oven, payroll, rent) are not part of a bank export, so an imported file gives you the forecast without the planned payments until those connectors land.
