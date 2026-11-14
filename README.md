# Aheadly

*Clarity today. A brighter tomorrow.*

Aheadly is an AI financial co-pilot for owners of small, local businesses. It checks the owner's cash every day, warns weeks before cash runs low, explains why in plain words, and lets the owner test a decision ("What if I buy the oven next month instead?") before making it.

Built for **AI-Driven App Development** (Babson, Prof. Matthew Macarty) by Laura Rodriguez, Fernando Siman, Mauricio Hasbun and Miguel Royo. Python 3.11 + Streamlit, SQLite, Prophet, Gemini or Claude.

## Run it in 5 steps (no keys needed)

```bash
cd aheadly
uv sync                      # or: python3.11 -m venv .venv && pip install -r requirements.txt
cp .env.example .env         # defaults: LLM_PROVIDER=stub (offline, no keys)
uv run streamlit run app.py
# Accounts → upload your bank statements (+ any files you keep),
#            or click "Try the example bakery" to see it with no files of your own
```

Optional, a real language model: set `LLM_PROVIDER=gemini` and `GEMINI_API_KEY=...` in `.env` (or `anthropic` + `ANTHROPIC_API_KEY`). Keys never go anywhere else.

Other commands:

```bash
uv run pytest -q                      # all offline, about a minute and a half; ends with the test-business scorecard
uv run black .                        # formatting
uv run python -m aheadly.jobs.daily_run   # the daily check from the command line (cron-able)
```

## Demo script (storyboard frames 1 to 6)

With the example bakery (Panadería La Esquina, statement up to Nov 10, 2026; the numbers below are the example's):

1. **Guessing.** Fresh start: every visitor gets an empty app; Accounts shows the upload card and *Try the example bakery*.
2. **Connect once.** *Try the example bakery*: a year of statements comes in and the app opens **Questions** (what the business does, busy months, whether the weekly transfer to M Gómez is the owner's pay…), pre-filled with the owner's answers.
3. **Always watching.** Dashboard: $8,200 today, the forecast dips below the $2,000 line in mid-December (the $7,500 oven on Nov 14, then the Christmas ingredients, the quarterly flour order and rent), the chance of dipping below the line, safe to spend today, how much to trust the forecast. *How we built it* shows every payment the forecast counts on.
4. **Early warning.** Alerts: why it happens, and fixes the app has already tested on the forecast ("Move New oven to Dec 16": lowest balance from below zero to above the line), each with *Test this*, how to do it and a message to copy. *How could you cover a gap?* says it's a timing gap and compares the owner's own options by cost.
5. **Ask in plain words.** Ask Aheadly: "What if I move the new oven payment to next month?" → the answer plus the best / base / worst card; "How much can I safely spend?" and "How can I cover this?" work too. What-if: *Check four surprises* (sales down 20%, the biggest payment a month late, the main supplier 10% dearer, a surprise bill).
6. **Act with confidence.** *Save as my plan*: the oven moves, the forecast reruns, the alert resolves.

To show the app on a business that isn't a bakery, upload the statements of another test business from `tests/businesses/<business>/statements/` (the café's problem is structural, the hardware store depends on one late-paying customer).

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
| `aheadly/ui/views/` | the eight page scripts (Dashboard, Questions, Alerts, How we built it, Ask Aheadly, What-if, Accounts, Settings) |
| `aheadly/ui/` | brand CSS on top of `.streamlit/config.toml`, all copy strings, cards, charts (weekly lows), cached bootstrap |
| `aheadly/core/` | `AppCore`, and the rules it uses: `alert_rules`, `actions` (tested fixes), `safe` (safe to spend / pay), `stress` (bad surprises), `financing`, `onboarding` (questions), `transfers`, `examples`, `session` |
| `aheadly/ai/` | `ForecastEngine` + models, `scenarios`, `categorizer`, `recurring`, `seasons`, `confidence`, `plan_text`, `InsightTranslator`, `llm_client`, `tools`, `guardrails`, `prompts`, `templates` |
| `aheadly/data/` | `schema.sql` + numbered migrations, `Repository`, `seed_demo`, `connectors/` (bank statements, the owner's own files) |
| `aheadly/jobs/` | `daily_run` (cron-able) |
| `tests/` | pytest: unit tests per component, the demo script as a functional test, and `test_businesses.py`, which runs the six test businesses in `tests/businesses/` against their answer keys |
| `docs/` | `ROADMAP.md` (the plan to the final version, kept current), UML diagrams, milestone check-in |

## How the AI works

* **Forecast Engine.** Regular payments and income found in the statement (rent on the 15th, payroll on Fridays, taxes every two months…) and the one-offs the owner knows go on their real dates; the rest of the history is fitted with Prophet (weekly seasonality, Colombian holidays, flat trend). 500 sampled future paths are cumulated from today's balance; worst / base / best case are the 10th / 50th / 90th percentiles, and the chance of dipping below the line is the share of paths that do. A seasonal-naive baseline is always available; Settings → *Compare forecast models* runs the backtest (MAE on the last 4 weeks).
* **Alert rules** are deterministic code: shortfall when the base case drops below the low cash line, idle cash when even the worst case stays above three months of outflows. Rules build a *facts* object; the LLM only writes the words.
* **Things we noticed** (`aheadly/core/pattern_rules.py`): twelve patterns worth knowing even when cash is fine (thin cushion, a cost creeping up, the owner's pay taking most of what's left, one big customer, a customer paying later, doubled or unusual charges…), found by rules that skip the months the owner calls busy or slow. Each gets a title from code and 1–3 sentences from the LLM; every chart gets a short summary the same way. Both are checked by the guardrail, fall back to templates and are written once per set of numbers.
* **Solving, not just warning.** Every fix the app suggests (move a payment, ask for money earlier, pay yourself less, raise prices, pairs of these) is run as a what-if first and shown with its effect; the same machinery gives safe to spend, the stress tests and the financing comparison (only the owner's own options, with their own rates; not financial advice).
* **Insight Translator** answers chat questions with function calling over nine tools (`get_cash_summary`, `get_forecast`, `get_upcoming_outflows`, `get_transactions`, `run_scenario`, `get_alerts`, `safe_to_spend`, `compare_financing`, `propose_plan_items`).
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

Accounts → upload one or more bank statements (CSV or Excel; several accounts and credit cards are combined, moves between your own accounts don't count). Headers may be the app's (`date, description, amount[, category]`) or a bank's (`Date, Description, Debit, Credit, Balance`, or Spanish: `Fecha, Descripción, Valor, Saldo`, `Fecha Movimiento`, `Monto`, `Saldo Disponible`…). Real bank exports are fine: comma, semicolon or tab separated, UTF-8 or Windows-1252, bank lines above the header, newest line first, dates like `10/11/2026` (day first), `11-nov-2026` or `2026-11-10`, amounts like `1.250,00`, `1,250.00`, `$ 2.000` or `(900,50)`. If the file has a Balance column, the current balance is read from its newest line and checked line by line; otherwise type it in. Lines that can't be read are left out and counted, never turned into $0. If the statement ends before yesterday, the forecast starts the day after it ends, and the app says so. Every line gets a category (sales, payroll, rent, utilities, suppliers, taxes, loan, bank fees...) from the bank's wording (DECISIONS #29); what the app can't tell, the owner answers once and it sticks. Other files you keep (upcoming payments, money customers owe you, an employee list, a ledger or your inventory, any layout) can be added with the statements or later; each is previewed and used only when you confirm (DECISIONS #32). Upcoming one-offs can also be typed in plain words on the "How we built it" page or in the chat ("I'm buying a new oven for $7,500 on Nov 14"): the app shows what it understood and adds nothing until you press Add (DECISIONS #31). Repeating payments and income (payroll, rent, utilities, taxes, a customer's monthly transfer) are found with their calendar rule and put on their real dates in the forecast (DECISIONS #30). The **How we built it** page lists everything the forecast counts on (where it starts, your normal week, regular and one-off payments, what's left out, next month at a glance); change, pause, end or remove any payment and it shows what that does to your lowest balance (DECISIONS #33). After the upload, **Questions** asks only what the statement can't show (what the business does, busy and slow months, whether a regular transfer is your own pay, what a few unplaced payees are, anything big coming up), one at a time and all skippable; the connected AI suggests categories from payee names only, and nothing changes until you save (DECISIONS #34). The dashboard says how much to trust the forecast (high, medium or low, and why) and asks about big one-off payments when none are known (DECISIONS #35).

A list of upcoming **one-off** payments and expected income (`Date, Description, Amount`, minus = money going out) is one of the files you keep: a planned purchase, a big supplier order, a customer order. Regular payments (payroll, rent, suppliers) are learned from the statement; one you list anyway is recognised and counted once.

No files at hand? On Accounts, **Try the example bakery** loads Panadería La Esquina (`aheadly/examples/`): a year of statements from the test businesses plus the one-off payments its owner knows about. It is always shown as of the day after its statement ends (Nov 11, 2026). Settings → Start over goes back to your own upload.

A sample bank export of the demo bakery is still in `data/samples/` for testing the import (regenerate it with `uv run python -m scripts.make_sample_export`). For realistic files, use the statements in `tests/businesses/<business>/statements/`: six test businesses made separately from the code, each with an answer key (DECISIONS #25).
