# Aheadly: Build Specification for the MVP

> **For the Claude session building this app.** This file is the single source of truth. It describes what Aheadly is, who it is for, exactly what the MVP must do, how it is architected, how it should look, and how to prove it works. Every other file in this kit is a supporting resource and is listed in the *Kit manifest* at the end. Read this whole file before writing code.

---

## 0. Context in one minute

* **Product:** Aheadly, an AI financial co-pilot for owners of small, local businesses in Latin America.
* **Tagline:** *Clarity today. A brighter tomorrow.*
* **Promise:** see a cash problem weeks before it happens, understand why in plain words, and decide with confidence.
* **Origin:** a university team project for the course **AI-Driven App Development** (Professor **Matthew Macarty**), also used as the team's venture in a New Venture Creation course.
* **Team:** Laura Rodriguez, Fernando Siman, Mauricio Hasbun, Miguel Royo.
* **Status:** Milestone I (overview, storyboard, UML) is done and submitted; those documents are in `course/`. **Your job is to build the working MVP that matches them.**
* **Hard constraint:** the app must stay consistent with the submitted deliverables. The component names, the four use cases, the persona and the core flow below are already graded artifacts. Do not rename or restructure them; if you must deviate, document it in `DECISIONS.md` in the repo.

---

## 1. Problem, user and persona

### 1.1 Problem
Owners of small businesses have the numbers but not the answers. They check today's bank balance and look at spreadsheets that describe the past, so payroll, supplier payments and big purchases (like a new oven) are decided with incomplete visibility. Bills often cluster in one week, and the owner only notices when the money is gone. One surprise shortfall means a late supplier, an overdraft fee or a missed payroll.

**How they cope today:** bank balance (shows today, not next month), spreadsheets (show what already happened), gut feel plus an accountant who reports monthly.

### 1.2 Target user
Owners of small, local businesses in Colombia (bakeries, cafés, corner shops) with 1 to 15 employees and no finance staff. Medium tech comfort: smartphone, WhatsApp and online banking daily; will not learn a complex finance tool.

### 1.3 Persona: Maria Gómez (use her in demo data and copy)
* 45, owner of **Panadería La Esquina**, Bogotá, for 12 years.
* 6 employees; walk-in customers plus two cafés she supplies on credit.
* Pays flour and dairy suppliers **weekly**, her team **every two weeks**, rent **monthly**.
* QuickBooks was set up by her accountant.
* **Goals:** never miss payroll or a supplier bill; know if she can afford a new oven; worry less about the numbers.
* **Pain points:** only sees today's balance; accountant's report arrives a month late; bills pile up in one week.
* **Quote:** *"I know how to bake. I just need to know if I'll have enough cash next month."*
* Portrait: `media/photos/persona_maria_portrait_square.jpg`.

**Language and tone for all user-facing text:** plain, warm, short sentences, no finance jargon (say "money coming in / going out", not "accounts receivable / payables" unless explaining). Write UI copy in **English** for the MVP, but keep all strings in one module (`aheadly/ui/copy.py`) so Spanish (`es-CO`) can be added later.

---

## 2. MVP scope

### 2.1 The four core features (these ARE the four use cases; keep the names)

| # | Use case / feature | What it must do |
|---|---|---|
| 1 | **Connect financial accounts** | Link the bank (Plaid **sandbox**) and QuickBooks (Intuit **sandbox**) once; transactions then sync automatically. A **"Use demo data"** option must always work without any API keys. |
| 2 | **Receive early-warning alert** | The forecast runs daily; when a shortfall (or idle cash) is coming, a plain-language alert appears in the app with the cause and 2 to 3 actions. |
| 3 | **Ask about my numbers** | Chat with Aheadly about balances, trends and upcoming bills in everyday words. |
| 4 | **Test a what-if scenario** | Model a purchase or change before deciding (for example "What if I buy the oven next month instead?") and see best, base and worst case. |

### 2.2 Explicitly out of scope (do not build)
* Moving money or paying bills.
* Bookkeeping, invoicing and taxes.
* Loans or credit offers.
* Native mobile app (MVP is a **Streamlit** web app; make it usable at phone width where Streamlit allows).
* Multiple users or accountant access (single demo business, simple local login optional).
* Live Colombian bank feeds (MVP uses Plaid sandbox data; Plaid does not really cover Colombia, a LatAm aggregator such as Belvo is a future option).
* Push/SMS/WhatsApp notifications (alerts are in-app; email is a stretch goal only).

### 2.3 Stack (fixed by the deliverables)
Python 3.11+, **Streamlit** (UI), **SQLite** (storage), **Prophet** (forecasting), **Plaid** sandbox and **QuickBooks Online API** sandbox (data), **Claude or Gemini API** (LLM, switchable by config). Currency: **USD** for the MVP (the deck uses $); keep currency in config.

---

## 3. Architecture (must match the component diagram)

See `design/uml/component_diagram.svg`. Three layers plus external services. Each arrow is a provided interface (ball) and a required interface (socket).

| Component | Layer | Responsibility | Module |
|---|---|---|---|
| **Streamlit UI** | Application | Dashboard and chat that Maria uses | `aheadly/ui/` + `app.py` |
| **App Core** | Application | Orchestrates the daily run, decides when to raise an alert, serves insights to the UI | `aheadly/core/app_core.py` |
| **Forecast Engine** | AI | Prophet time-series model; projects cash 8 weeks ahead; reruns for what-ifs | `aheadly/ai/forecast_engine.py` |
| **Insight Translator** | AI | Builds prompts, explains results, parses questions via function calling | `aheadly/ai/insight_translator.py` |
| **Data Repository** | Data | SQLite store of transactions, scheduled payments, forecasts, alerts, scenarios, chat | `aheadly/data/repository.py` |
| **Bank Feed API** «external» | External | Plaid, QuickBooks | `aheadly/data/connectors/` |
| **LLM API** «external» | External | Claude / Gemini | `aheadly/ai/llm_client.py` |

| Interface | Provider (ball) | Requirer (socket) | Suggested function(s) |
|---|---|---|---|
| Get Insights | App Core | Streamlit UI | `AppCore.get_dashboard()`, `get_alerts()`, `ask()`, `run_what_if()` |
| Run Forecast | Forecast Engine | App Core | `ForecastEngine.forecast(business_id, horizon_days=56, adjustments=None)` |
| Explain Results | Insight Translator | App Core | `InsightTranslator.write_alert(facts)`, `answer(question, history)` |
| Read/Write Data | Data Repository | Forecast Engine (and App Core) | `Repository.*` |
| Generate Text | LLM API | Insight Translator | `LLMClient.chat(messages, tools)` |
| Sync Transactions | Bank Feed API | Data Repository | `PlaidConnector.sync()`, `QuickBooksConnector.sync()` |

**Rule:** only the Insight Translator talks to the LLM; only connectors talk to Plaid/QuickBooks; the UI only talks to App Core.

### 3.1 Suggested repo layout
```
aheadly/
├── app.py                         # Streamlit entry (st.navigation / pages)
├── .streamlit/config.toml         # copy from brand/streamlit/config.toml
├── .env.example                   # all keys, DEMO_MODE=true by default
├── requirements.txt
├── README.md                      # setup + run + demo script
├── DECISIONS.md                   # any deviation from this spec
├── assets/                        # logo, icon, persona photo from this kit
├── aheadly/
│   ├── config.py                  # env loading, constants (horizon, thresholds, currency)
│   ├── ui/
│   │   ├── theme.py               # inject tokens.css + helper card components
│   │   ├── copy.py                # all user-facing strings
│   │   ├── page_dashboard.py
│   │   ├── page_alerts.py
│   │   ├── page_ask.py            # chat (Ask about my numbers + what-ifs)
│   │   ├── page_whatif.py         # form-based what-if (same engine as chat)
│   │   └── page_connect.py        # onboarding / accounts
│   ├── core/
│   │   ├── app_core.py
│   │   └── alert_rules.py
│   ├── ai/
│   │   ├── forecast_engine.py
│   │   ├── scenarios.py           # adjustment types applied to forecasts
│   │   ├── insight_translator.py
│   │   ├── prompts.py
│   │   ├── tools.py               # function-calling tool schemas + dispatch
│   │   ├── guardrails.py          # number check on LLM output
│   │   └── llm_client.py          # Claude / Gemini adapter, plus offline stub
│   ├── data/
│   │   ├── repository.py
│   │   ├── schema.sql
│   │   ├── seed_demo.py           # generates Panadería La Esquina data
│   │   └── connectors/
│   │       ├── plaid_connector.py
│   │       └── quickbooks_connector.py
│   └── jobs/
│       └── daily_run.py           # python -m aheadly.jobs.daily_run (cron-able)
└── tests/
```

---

## 4. Core flow (must match the activity diagram)

See `design/uml/activity_diagram.svg`. Swimlanes: Business Owner, App, AI service.

1. **App:** Sync bank & books → Forecast cash flow.
2. **Decision "Risk or idle cash?"**
   * **[no]** → Update dashboard → end.
   * **[yes]** → **AI service:** Write plain-language alert → **App:** Send alert (in-app).
3. **Business Owner:** Read alert.
4. **Decision "Have a question?"**
   * **[no]** → Act on advice → end.
   * **[yes]** → **AI service:** Answer / run what-if → **App:** Show answer → **Business Owner:** Act on advice → end.

**Daily trigger in a Streamlit MVP:** run the pipeline (a) via `python -m aheadly.jobs.daily_run` (cron-able), (b) automatically on app load if the last run is older than 24 h, and (c) from a "Run today's check" button in Settings for demos. Store each run in `forecast_runs`.

---

## 5. Data model (SQLite)

```sql
CREATE TABLE businesses (
  id INTEGER PRIMARY KEY, name TEXT, owner_name TEXT, city TEXT,
  currency TEXT DEFAULT 'USD', low_cash_line REAL DEFAULT 2000,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);

CREATE TABLE accounts (
  id INTEGER PRIMARY KEY, business_id INTEGER REFERENCES businesses(id),
  source TEXT CHECK (source IN ('plaid','quickbooks','demo','csv')),
  name TEXT, external_id TEXT, access_token_enc TEXT, last_synced_at TEXT);

CREATE TABLE transactions (
  id INTEGER PRIMARY KEY, business_id INTEGER, account_id INTEGER,
  external_id TEXT UNIQUE, date TEXT NOT NULL, amount REAL NOT NULL, -- + inflow, - outflow
  description TEXT, category TEXT, counterparty TEXT, source TEXT);

CREATE TABLE scheduled_items (           -- known future money in/out
  id INTEGER PRIMARY KEY, business_id INTEGER, kind TEXT CHECK (kind IN ('bill','payroll','rent','receivable','planned_purchase','other')),
  label TEXT, amount REAL NOT NULL,       -- signed like transactions
  due_date TEXT, recurrence TEXT,         -- NULL | 'weekly' | 'biweekly' | 'monthly'
  source TEXT, active INTEGER DEFAULT 1);

CREATE TABLE forecast_runs (
  id INTEGER PRIMARY KEY, business_id INTEGER, run_at TEXT, horizon_days INTEGER,
  model TEXT, scenario_id INTEGER NULL, opening_balance REAL,
  min_p50 REAL, min_p50_date TEXT, min_p10 REAL, min_p90 REAL);

CREATE TABLE forecast_points (
  run_id INTEGER REFERENCES forecast_runs(id), date TEXT,
  balance_p10 REAL, balance_p50 REAL, balance_p90 REAL,
  net_flow_p50 REAL, PRIMARY KEY (run_id, date));

CREATE TABLE alerts (
  id INTEGER PRIMARY KEY, business_id INTEGER, run_id INTEGER, type TEXT CHECK (type IN ('shortfall','idle_cash')),
  severity TEXT, weeks_ahead INTEGER, facts_json TEXT,  -- the numbers the LLM was given
  title TEXT, body TEXT, actions_json TEXT, created_at TEXT, read_at TEXT, dismissed INTEGER DEFAULT 0);

CREATE TABLE scenarios (
  id INTEGER PRIMARY KEY, business_id INTEGER, name TEXT, adjustments_json TEXT,
  created_at TEXT, result_run_id INTEGER);

CREATE TABLE chat_messages (
  id INTEGER PRIMARY KEY, business_id INTEGER, role TEXT, content TEXT,
  tool_calls_json TEXT, created_at TEXT);
```

---

## 6. AI design

### 6.1 Forecast Engine (Prophet)
* Aggregate transactions to **daily net cash flow** (exclude known scheduled items so they are not double counted; if a history line matches a scheduled item, model it as scheduled).
* Fit Prophet on the residual daily net flow with weekly and yearly seasonality (yearly only if 12+ months of history) and Colombian holidays (`m.add_country_holidays('CO')`).
* Predict 56 days. Add scheduled items (bills, payroll, rent, receivables, planned purchases) deterministically on their due dates.
* Cumulate from the opening balance (current bank balance) to get daily balance. Use Prophet's `yhat_lower` / `yhat` / `yhat_upper` (interval width 0.8) to produce **worst (p10) / base (p50) / best (p90)** balance paths. Cumulating intervals naively overstates spread; acceptable approximation: simulate 500 paths from Prophet `predictive_samples` and take percentiles of the cumulative balance. Prefer the simulation.
* Output: `ForecastResult` dataclass with daily points, min p50 balance and date, min p10/p90, top outflows in the risk window.
* If Prophet cannot be installed in the environment, fall back to `statsmodels` ExponentialSmoothing behind the same interface and note it in `DECISIONS.md`. The UI and docs still call it the Forecast Engine.

### 6.2 Alert rules (`core/alert_rules.py`, deterministic, no LLM)
* **Shortfall:** any day where `balance_p50 < low_cash_line` within the horizon. Severity: `high` if ≤ 2 weeks away or p50 < 0; `medium` if 3 to 5 weeks; `low` if 6 to 8 weeks. `weeks_ahead = ceil(days/7)`.
* **Idle cash:** `min(balance_p10)` over the horizon stays above `3 × average monthly outflows` for the whole horizon → suggest putting money to work (e.g., pay a supplier early for a discount, buy inventory in bulk). Never suggest specific investment products.
* De-duplicate: do not raise a new alert of the same type if an unread one exists with the same risk date ± 3 days; update it instead.
* Build a **facts** object for every alert (this is all the LLM may use):
```json
{"type":"shortfall","current_balance":8200,"low_cash_line":2000,
 "lowest_balance":-4000,"lowest_date":"2026-12-14","weeks_ahead":5,
 "top_outflows":[{"label":"Supplier payment","amount":4000,"date":"2026-12-14"},
                 {"label":"Inventory","amount":1200,"date":"2026-12-15"},
                 {"label":"Rent","amount":900,"date":"2026-12-15"}],
 "expected_inflows_before":[{"label":"Café Azul invoice","amount":1500,"date":"2026-12-20"}],
 "possible_actions":["collect_receivables_early","adjust_inventory_orders","negotiate_payment_terms","delay_planned_purchase"]}
```

### 6.3 Insight Translator (LLM with function calling)
**Provider adapter** (`llm_client.py`): `LLM_PROVIDER=anthropic|gemini|stub`. Model ids come from env (`ANTHROPIC_MODEL`, `GEMINI_MODEL`); check the providers' docs for current ids rather than hardcoding (a reasonable Anthropic default is `claude-sonnet-5-5`). The `stub` provider returns template text so the app and tests run offline.

**Job A, write alert:** input = facts JSON → output JSON `{title, body, actions:[{label, detail}]}`; body ≤ 60 words, 2 to 3 actions, mention the cause (which bills, which week).

**Job B, answer questions and what-ifs (chat):** tools the model may call:

| Tool | Params | Returns |
|---|---|---|
| `get_cash_summary` | none | current balance, last 30 days in/out, low cash line |
| `get_forecast` | `weeks` (1 to 8) | weekly p10/p50/p90 balances, lowest point |
| `get_upcoming_outflows` | `weeks` | list of scheduled + predicted large outflows |
| `get_transactions` | `category?`, `since?`, `limit?` | recent transactions |
| `run_scenario` | `adjustments[]` (see below), `name` | baseline vs scenario: lowest p10/p50/p90, dates, delta |
| `get_alerts` | `status?` | current alerts with facts |

Scenario adjustment types (`ai/scenarios.py`):
`one_time_expense {amount, date, label}`, `move_item {item_id|label, new_date}`, `remove_item {item_id|label}`, `recurring_change {label, amount_delta, recurrence, start_date}`, `revenue_change {percent, start_date}`, `collect_early {label, new_date}`.

### 6.4 Prompts (start here, iterate)
System prompt for chat (`prompts.py`):
```
You are Aheadly, a friendly financial co-pilot for a small business owner who is not a finance expert.
Rules:
1. Every number you state must come from a tool result in this conversation. Never estimate, round creatively, or invent figures. If you lack a number, call a tool.
2. Use plain, warm, short sentences. No jargon. Money is "coming in" or "going out".
3. For any "what if" question, translate it into run_scenario adjustments, call run_scenario, then explain best, base and worst case and whether the balance stays above the low cash line.
4. End with one clear suggestion, not a list of ten. You inform; the owner decides. Do not give legal, tax or investment advice.
5. Keep answers under 120 words unless the owner asks for detail.
Business: {business_name}, owner {owner_name}. Today is {today}. Currency {currency}. Low cash line {low_cash_line}.
```

### 6.5 Guardrail (`guardrails.py`, required)
After every LLM response, extract all numbers (money, %, weeks) and check each appears in the facts or tool outputs of that turn (allow formatting differences and ±1 rounding). If any number is unverified, regenerate once with a correction message; if it still fails, show a deterministic template answer built from the facts. Log failures. This guardrail is a stated feature in the deliverables ("the LLM never invents figures").

---

## 7. Demo data: Panadería La Esquina (`seed_demo.py`)

The app must run end to end with `DEMO_MODE=true` and no keys. Generate 12 months of history ending today plus scheduled items. Use a fixed random seed.

**Business facts (weekly averages; add realistic noise, keep ordinary weeks netting about +$300):**

| Money in | ≈ per week | Money out | ≈ per week |
|---|---|---|---|
| Walk-in sales (daily, higher Fri to Sun, closed on some Colombian holidays) | $5,500 | Flour and dairy suppliers (weekly, Mondays) | $3,100 |
| Two cafés, invoiced weekly, paid 14 to 21 days later | $1,500 | Payroll, 6 staff (biweekly ~$3,600) | $1,800 |
| | | Owner's draw (weekly) | $1,200 |
| | | Rent ($900 on the 15th) | $225 |
| | | Packaging, utilities (~$250/month, trending up so a "High expense trend: Utilities" low-severity insight is possible), maintenance | $375 |
| **Total** | **≈ $7,000** | **Total** | **≈ $6,700** |

**Canonical demo story (tune the generator so the base case lands within ±10% of these numbers):**
* Today's balance: **$8,200**.
* Maria has a **planned purchase: new oven $7,500 this week** (a `planned_purchase` scheduled item).
* In week 5, a quarterly flour order (**Supplier payment $4,000**), **Inventory $1,200** and **Rent $900** land together.
* Baseline forecast: lowest base-case balance **≈ −$4,000 in 5 weeks** → **shortfall alert, medium severity**.
* Low cash line: **$2,000**.
* What-if "Buy the oven next month instead" (move it to week 7, after the cafés pay): lowest base-case balance **stays above $3,000** the whole time → the AI says it looks safe.
* **Arithmetic that makes this work (check it):** ordinary weeks net only about **+$300** (sales roughly cover suppliers, payroll and rent). So without the oven, week 5 lands near 8,200 + 5 × 300 − 6,100 ≈ **$3,600**; with the oven in week 1 it lands near **−$3,900 ≈ −$4,000**. Weeks 6 and 7 are a **seasonal peak** (+$4,000 to +$5,000 net each: holiday sales plus large café holiday orders paid on time), so paying the $7,500 oven at the end of week 7 still leaves roughly **$5,000**. Generate all dates **relative to the run date** so the story works whenever the demo runs; label the peak "Christmas season" only when it actually falls in December (Colombian bakeries sell heavily during the novena season).
* Mockup numbers in `media/ui_mockups/` (e.g., $12,450, +1,800 / +200 / −4,000) are **illustrative only**; the canonical numbers above win.

---

## 8. Connectors

* **Plaid (sandbox):** use the official `plaid-python` SDK. Plaid Link is a JavaScript widget, which is awkward in Streamlit; for the MVP use the sandbox shortcut `/sandbox/public_token/create` with a sandbox institution (e.g., "First Platypus Bank"; confirm the institution id in Plaid docs) → exchange for an access token → `/transactions/sync` and `/accounts/balance/get`. Map Plaid's sign convention (Plaid: positive = money out) to ours (positive = money in).
* **QuickBooks Online (sandbox):** OAuth 2.0 via Intuit developer sandbox company (`intuit-oauth` + `python-quickbooks`, or REST). Pull open **Bills** (→ `scheduled_items` kind `bill`) and open **Invoices** (→ `receivable`). If OAuth is not configured, the page shows "Connect later" and demo data fills in.
* **CSV import (fallback):** date, description, amount; useful for the demo and testing.
* Secrets only from `.env`; never commit keys; encrypt stored tokens with a key from env (Fernet).

---

## 9. UI specification (Streamlit)

**Visual reference:** `media/ui_mockups/` (dashboard, alert detail, what-if chat), `media/photos/deck_slide_*.png` (overall look), `design/storyboard/` (the user journey). Brand tokens in `brand/tokens.css`; Streamlit theme in `brand/streamlit/config.toml`.

**Look and feel:** white background; navy text; purple primary; purple to blue gradient for the hero accents and the primary button; soft pastel cards (lavender, sky, mint) with 20 px radius, thin `#E6E0FA` border and a soft purple shadow; red only for risk. Font Inter (load from Google Fonts in injected CSS). Lots of white space; big numbers. Logo top left of the sidebar (`assets/logo_full_transparent.png`), app icon as favicon and as the assistant's chat avatar (`assets/logo_mark_transparent.png`).

**Navigation (sidebar):** Dashboard · Alerts (badge with unread count) · Ask Aheadly · What-if · Accounts · Settings.

**Page specs**
1. **Accounts / onboarding (feature 1).** First run shows a welcome card with Maria's business name, then three choices: *Connect bank (Plaid sandbox)*, *Connect QuickBooks*, *Use demo data*. Show connected status with green checks and "All set" (see storyboard frame 2). Last synced time.
2. **Dashboard.** Top row of stat cards: **Current cash** (purple), **Lowest projected** (red if below the low cash line, with "in N weeks"), **Next big payment**. Main chart: 8-week **cash flow forecast** (history solid line, forecast dashed, best/worst band shaded, horizontal dashed red **low cash line**, red dot and label at the lowest point, vertical "Today" line). Use Plotly or Altair styled with the tokens. Below: **Upcoming alerts** list and an **Ask Aheadly** quick box ("Ask a question…") that opens the chat with the text.
3. **Alerts (feature 2).** Alert card like `alert_detail_mockup.png`: title ("Heads up"), body, three blocks: **Why it matters**, **What you can do** (checklist of actions), **Top cash outflows in N weeks** (table). Buttons: *See why* (opens chat seeded with the alert), *Test a what-if*, *Dismiss*. Mark as read on open.
4. **Ask Aheadly (features 3 and 4).** `st.chat_message` chat, assistant avatar = app icon. Suggested prompt chips: "How am I doing this month?", "Will I have enough cash next month?", "What if I buy the new oven next month instead?". When `run_scenario` is used, render a result card under the answer: mini chart baseline vs scenario + **Best / Base / Worst** lowest balance (see `whatif_chat_mockup.png`).
5. **What-if (feature 4, form version).** Simple form: type (buy something, move a payment, change sales), amount, date, label → same `run_scenario` engine → comparison chart and the LLM explanation. Save scenario.
6. **Settings.** Low cash line, currency, LLM provider status, demo reset, "Run today's check".

**Empty and error states:** friendly copy, never a stack trace; if the LLM fails, show the deterministic template answer with a small note.

---

## 10. Demo script = acceptance test (mirrors storyboard frames 1 to 6)

Run with `DEMO_MODE=true`, `LLM_PROVIDER=stub` (and again with a real provider).
1. **Guessing:** fresh start shows onboarding; no data yet.
2. **Connect once:** click *Use demo data* (or Plaid sandbox) → "All set"; transactions visible.
3. **Always watching:** dashboard shows today ≈ $8,200 and an 8-week chart crossing the low cash line in week 5.
4. **Early warning:** Alerts badge = 1; alert says cash may run low in about 5 weeks because supplier bills, inventory and rent land the same week; three actions listed.
5. **Ask in plain words:** in chat, "What if I buy the new oven next month instead?" → tool call `run_scenario(move_item oven → week 7)` → answer says cash stays above $3,000 the whole time, with best/base/worst card.
6. **Act with confidence:** save the scenario as the plan; dashboard updates; the shortfall alert resolves.

### 10.1 Tests (pytest)
* Seed generator is deterministic and hits the canonical numbers within tolerance.
* Forecast returns 56 daily points with p10 ≤ p50 ≤ p90.
* Alert rules: shortfall detected at the right week; no duplicate alerts; idle cash rule.
* Each scenario adjustment type changes the forecast as expected.
* Guardrail rejects an answer containing an invented number.
* Tool dispatch returns valid JSON for every tool.
* Plaid sign convention mapping.

---

## 11. Build order

1. Repo skeleton, config, theme injection, copy module, schema + repository.
2. Demo seed generator; dashboard with a plain chart from history.
3. Forecast Engine + scenarios; dashboard chart with bands and low cash line.
4. Alert rules + App Core daily run + Alerts page (stub translator).
5. LLM client (stub, Anthropic, Gemini), Insight Translator, tools, guardrail; Ask Aheadly chat; what-if result card.
6. What-if form page; Settings.
7. Plaid sandbox connector; QuickBooks sandbox connector; CSV import.
8. Tests, README with setup and the demo script, `DECISIONS.md`, screenshots in `docs/`.

**Definition of done:** `pip install -r requirements.txt && streamlit run app.py` works on a clean machine with no keys; the demo script passes; tests pass; real LLM provider works when keys are set; README explains setup in under 10 steps.

---

## 12. Glossary
* **Low cash line:** the safety buffer the owner sets; below it Aheadly warns.
* **Best / base / worst case:** p90 / p50 / p10 of the simulated balance paths.
* **Idle cash:** money that will sit unused through the whole horizon even in the worst case.
* **Ball / socket:** UML notation; ball = component that provides an interface, socket = component that requires it.

---

## 13. Kit manifest

```
aheadly-build-kit/
├── AHEADLY_APP_SPEC.md                 ← this file
├── brand/
│   ├── logo_full_transparent.png       wordmark + mark, transparent (use in app)
│   ├── logo_full_original_white_bg.png original high-res logo
│   ├── logo_mark_transparent.png       "A" mark only (chat avatar)
│   ├── app_icon_512.png, favicon_64.png
│   ├── tokens.css                      colors, gradient, radius, shadow, font
│   └── streamlit/config.toml           Streamlit theme
├── media/
│   ├── photos/                         persona portrait, deck photos (right halves), all 10 original pitch-deck slides
│   └── ui_mockups/                     dashboard, alert detail, what-if chat (visual targets)
├── design/
│   ├── uml/                            use case, component, activity (.svg + slide .png + original dark versions)
│   └── storyboard/                     6 frames as .svg, full storyboard .png, original dark version
└── course/
    ├── Milestone1_Report.pdf           submitted report (full narrative of the product)
    ├── Milestone1_Deck.pptx / .pdf     presentation
    └── rubric/                         grading rubric screenshots (consistency matters)
```

Photos in `media/photos/` are AI-generated marketing images from the team's pitch deck; they are fine for the demo but are not real customers.
