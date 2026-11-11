# Aheadly: roadmap to the final version (technical)

> **For whoever builds the final version (and their Claude).** One person builds everything, in the order below. This is the plan from the Milestone 2 check-in to the final demo; `PROGRESS.md` says where the work stands. The team also has a plain-language version of this plan.
>
> Written on 2026-11-11 from `main` after PR #1 (69 tests passing, CI green, live site checked with Gemini `gemini-3.5-flash-lite` and Prophet). Read `aheadly-build-kit/AHEADLY_APP_SPEC.md` and `aheadly-build-kit/COURSE_GUIDE.md` first; re-check file and function names below if the code has moved on.

---

## 0. Product decisions (agreed by the team)

1. **Client = a small business with only bank statements (CSV/Excel; PDF later) plus maybe its own Excel files.** No QuickBooks or live bank connection for the course; the Plaid/QuickBooks scaffolds stay for the long term. Use case 1 *Connect financial accounts* is satisfied by file upload.
2. **Onboarding is upload-only** (`DECISIONS.md` #20). No *Use demo data* in the UI; `DemoConnector` and `seed_demo` stay for tests. A visitor without files gets "Try an example business" (1.5), which loads a test business, not the old seed.
3. **One-time session tool.** Each visit starts empty (`PER_VISITOR_DATA`, #17). "Download / Load my data" (5.1) lets an owner continue. Accounts, logins and automatic updates are long term (section 6).
4. **The app suggests, drafts and tests; the owner decides and sends.** It never sends messages, moves money or offers credit.

## 1. Rules for every item

- **Code computes every number; the LLM only writes words; `aheadly/ai/guardrails.py` checks every number; `aheadly/ai/templates.py` is the fallback.** Applies to every new text: actions, how-to steps, drafted messages, insights, chart summaries, file-type explanations, financing.
- UI calls only `AppCore`; only `repository.py` has SQL; only `llm_client.py` talks to providers; user-facing strings in `aheadly/ui/copy.py`.
- TDD with pytest (failing test first), `black`, CI green. `PROGRESS.md` after each item; `DECISIONS.md` for every deviation (next free number: **#22**).
- Works with `LLM_PROVIDER=stub` and with Gemini. Free-tier quota: cache LLM outputs per facts hash so Streamlit reruns don't call the provider again.
- Every chart gets a 1–3 sentence summary (4.2). Every warning, alert or insight gets 2–3 `Action`s (3.2).
- The owner can always see and correct what the forecast assumes (2.6).
- Data sent to the LLM = data, never instructions (prompt-injection rule). Personal data minimised: an employee list's names and salaries never go to the LLM (only headers / column types / aggregates).
- Keep the four use case names (Connect financial accounts, Receive early-warning alert, Ask about my numbers, Test a what-if scenario).
- The canonical demo tests (`tests/test_seed_demo.py`, `tests/test_demo_script.py`) stay green unless an item says otherwise.

**Priority:** Must = in the final version even if time runs short · Should = if the pace allows · Nice = only with time left. **Size:** S = a few hours · M = about a day · L = 2–3 days. Must ≈ 20 working days, Should ≈ 8 more.

## 2. Current state (what exists, where)

- **Session / config:** `aheadly/core/session.py` (`new_repository`, `new_core`), `aheadly/config.py` (`Settings.per_visitor_data`), `aheadly/ui/bootstrap.py` (`get_settings`, `get_engine`, `get_llm` cached with `st.cache_resource`; `get_core` per session in `st.session_state["core"]`; `reset_core`).
- **Import:** `aheadly/data/connectors/csv_connector.py`: `CsvConnector(content, balance, filename, business_profile, upcoming, upcoming_filename)`; `parse_dates` (ISO, day-first unless the 2nd number > 12), `parse_amounts`/`_parse_amount` (1.250,00 · 1,250.00 · $ 2.000 · (900,50) · B/.), `closing_balance` from a Balance column, `read_upcoming_payments` (Date/Description/Amount → `ScheduledItem` kind `receivable`/`bill`, source `csv`), `skipped_rows`. Every imported row gets `category="other"`.
- **Forecast:** `aheadly/ai/forecast_engine.py` (Prophet with weekly seasonality on residual daily net flow, 500 paths, p10/p50/p90; `SeasonalNaiveModel` fallback; paths cached per history), `aheadly/ai/scenarios.py` (six adjustment types).
- **Core:** `aheadly/core/app_core.py`: `_model_history` (excludes history by category of scheduled kinds: uploaded statements are all "other", so nothing is excluded; this is why the upcoming file must hold one-offs only), `forecast_summary(weeks, until)`, `planned_items()`, `biggest_upcoming_payment()`, `save_plan()` → `run_daily_check(force=True)`. `aheadly/domain.py`: `ForecastResult.risk_level`, `lowest_with_today`, `ScenarioResult.summary()`.
- **AI:** `aheadly/ai/tools.py` (six tools, `ToolDispatcher`, `scheduled_labels`), `llm_client.py` (`StubClient.plan(question, labels)`, `best_label`, Gemini/Anthropic clients), `prompts.py` (rules 1–9), `templates.py` (risk-level verdicts; generic alert actions), `insight_translator.py`.
- **UI:** `aheadly/ui/views/` dashboard, alerts, ask (suggestion chips incl. `MOVE_PAYMENT_QUESTION`), whatif, accounts (upload card; "What we're counting on"; recent transactions), settings (Start over, backtest).
- **Demo data:** Maria's files are generated outside the repo by `../aheadly-test-data/make_maria_files.py` (statement ends yesterday; regenerate on demo day).

**Known issues to fix along the way** (each is assigned below):
1. Forecasts start from `date.today()`, not the statement's last date → 1.3.
2. No balance reconciliation → 1.3.
3. `external_id` is row-index based (`csv-{row}-{date}-{amount}`; verify) → re-import duplicates → 1.3.
4. Cached `Settings` survive a deploy: after the PR #1 merge the live app crashed with `AttributeError: per_visitor_data` until a reboot → 1.4.
5. Settings shows server time (UTC) → 1.4.
6. Weekly-only seasonality smooths monthly/quarterly items across weeks → 2.3.
7. `scenarios._revenue_change_items` hard-codes `weekly_sales=5500.0` → 2.2.
8. Template alert actions are generic ("Delay the planned purchase") → 3.2.
9. `alerts.type` CHECK allows only `shortfall` / `idle_cash` → insights get their own table (1.4, 4.1).

---

## 3. Overview

| ID | Item | Priority | Size | Depends on |
|---|---|---|---|---|
| 1.1 | Test businesses + answer keys (separate session) | Must | M | none |
| 1.2 | Test-business harness | Must | M | 1.1 |
| 1.3 | Finish bank-file reading: as-of date, reconciliation, stable ids | Must | S | none |
| 1.4 | Groundwork: migrations, profile, new columns, settings reload, local time | Must | M | none |
| 1.5 | Try an example business | Must | S | 1.1 |
| 2.1 | Multiple bank accounts (Must) + credit cards (Should) | Must / Should | M + S | 1.3, 1.4 |
| 2.2 | Transaction categorizer (+ fix `revenue_change`) | Must | M | 1.4 |
| 2.3 | Recurring detection on real dates (weekly → yearly), no double counting | Must | L | 2.2 |
| 2.4 | "Just say it": free text → plan item, confirmed | Must | S | 1.4 |
| 2.5 | Any Excel file: receivables + bills (Must), employee list (Should), ledger + inventory (Nice) | Must / Should | M + S | 1.4, 2.2 |
| 2.6 | "How we built your forecast" page (replaces Money plan + "What we're counting on") | Must | L | 2.3, 2.4, 2.5 |
| 2.7 | Onboarding questions (detect first, then ask) | Must | L | 2.2, 2.3, 2.4 |
| 2.8 | Forecast confidence + "no big purchases known" note | Must | S | 1.3, 2.2 |
| 3.1 | Chance of dipping below the line | Must | S | 1.4 |
| 3.2 | Actions framework: computed impact, Test this, how-to steps, drafted message | Must | M | 3.1 |
| 3.3 | Suggested fixes (auto-tested what-ifs) | Must | M | 3.2, 2.3 |
| 3.4 | Safe to spend + safe owner's pay | Must | S | 3.1, 2.3 |
| 3.5 | One-click stress tests | Should | S | 2.2, 3.2 |
| 3.6 | Financing helper | Should | L | 3.3, 2.7 |
| 4.1 | Pattern rules ("things we noticed"): small Must, full Should | Must / Should | M | 2.2, 2.3, 3.2 |
| 4.2 | Insight text + chart summaries | Must (small) | S | 4.1 |
| 4.3 | Insights page + dashboard cards: small Must, full Should | Must / Should | M | 4.2, 3.4 |
| 5.1 | Download / Load my data | Must | M | 1.4, 1.3 |
| 5.2 | Privacy page + delete my data | Must | S | none |
| 5.3 | Glossary tooltips | Should | S | none |
| 5.4 | Chatbot evaluation set in CI | Should | S | 1.1 |
| 5.5 | Final demo with two test businesses | Must | S | all Must |

**Schedule (one person, demo assumed ~Dec 10; shift if the date differs):** week 1 (Nov 12–18) Phase 1 · week 2 (Nov 19–25) 2.1–2.4 · week 3 (Nov 26–Dec 2, Thanksgiving) 2.5–2.8 · week 4 (Dec 3–9) 3.1–3.4, small 4.x, 5.1, 5.2 · then 5.5. Should items slot in where the pace allows.

**Cut order if time runs short:** Nice items and ledger/inventory → 3.6 (or only its timing-vs-structural verdict) → full 4.x → 3.5 → credit cards and employee list → 5.3/5.4 minimal. **Never cut:** 1.1/1.2, 2.6, the numbers-in-code rule.

---

## 4. Items

### Phase 1: foundation and proof (week 1)

#### 1.1 Test businesses + answer keys · Must · M
**Who:** Miguel with his own Claude, in a session separate from the one writing app code. **The builder session never creates, regenerates or edits these files**, and never weakens a feature or a check to make a test pass; if a key looks wrong, stop and ask. Independent test data is the honest check (like an auditor's samples).
**What arrives**, one folder per business:
```
tests/businesses/<slug>/
├── statements/           # 1+ bank statements (CSV/XLSX; English/Spanish headers, dd/mm/yyyy, "1.234,56", cryptic descriptions); some with a credit card statement
├── files/                # the owner's own Excel files: receivables, bills/upcoming, employee list, sometimes ledger/inventory, each in its own layout
├── answer_key.json
└── README.md             # the business's story in plain words
```
4–6 businesses: different industries, sizes and situations (healthy with no alerts; timing gap; structural loss; seasonal; dependent on one customer). Maria's bakery is one of them. At least one has two bank accounts + a card; one has an employee list; one has a ledger.
`answer_key.json` (field names agreed on delivery; tolerances wherever numbers vary): import (transactions per file, as-of date, closing balance, reconciliation result, internal transfers found); categories; recurring items (label, amount, cadence incl. monthly/quarterly, next date); file types detected + rows read; onboarding answers to feed automatically; warnings and insights that must / must not appear; chance below line range; suggested fixes expected among the top 3; safe-to-spend range; what-ifs (adjustment + direction and size of change); backtest max error; chat questions + what the answer must reflect.

#### 1.2 Test-business harness · Must · M
`tests/test_businesses.py`, parametrized over `tests/businesses/*`: upload through the real `CsvConnector` / file readers + `AppCore`, feed the key's onboarding answers, run each feature, compare with the key. Stub LLM, fixed seed. Checks for features not built yet: `pytest.mark.xfail(strict=True, reason="needs 2.3")`, so the xfail list is the to-do list and lands as features do. Print a results table in the CI log. When a check fails: fix the app, not the key. Manual checklist `docs/MANUAL_TEST_CHECKLIST.md` for what can't be automated (charts look right, Gemini answers read well, the app feels finished).

#### 1.3 Finish bank-file reading · Must · S
- **As-of date** = the statement's last transaction date: history and forecast start there; UI "Based on your statement up to Nov 10". Today's behaviour (as-of = today) stays for the built-in seed so canonical tests don't shift. With several statements (2.1): the earliest of the accounts' last dates, and say which.
- **Reconciliation:** with a Balance column, opening balance + sum of transactions = closing balance (tolerance a cent per row); else warn "Some rows may be missing" with the first date where it breaks.
- **Stable ids:** content hash of (account, date, amount, normalized description, running balance if present) instead of the row index; keep the `UNIQUE` constraint; report "N new, M already known". Needed by 2.1 (overlapping statements) and 5.1 (load + newer statement).
**Done when:** unit tests for each; re-importing the same file adds 0 rows.

#### 1.4 Groundwork + two fixes · Must · M
- **Migrations** in `Repository.__init__`: `PRAGMA user_version`, numbered steps, all SQL in `repository.py`. (Per-visitor DBs start fresh, but 5.1 loads older files and the local file DB must upgrade.)
- `business_profile` (one row per business): type, employees, how customers pay + terms, busy/slow months, how the owner pays themselves, comfortable minimum cash, goal, financing options JSON (3.6), supplier terms, onboarding progress, currency, time zone.
- `scheduled_items` new columns: `status` (`detected`/`confirmed`/`user`), `certainty` (`confirmed`/`maybe`), `likelihood` (0–1), `user_edited`, `category`, `match_key`, `cadence` (incl. `quarterly`, `yearly`), `end_date`, `paused`, `source` (`statement`/`file:<name>`/`chat`/`onboarding`/`plan`).
- `transactions` new columns: `account_id` (if missing), `scheduled_item_id`, `category_source` (`bank`/`rule`/`owner`/`model`), `is_internal_transfer`.
- `accounts`: `kind` (`bank`/`card`), `currency`. New tables: `payee_rules` (match_key → category, label), `insights` (alerts' CHECK only allows two types), `uploaded_files` (name, detected type, mapping JSON, confirmed). `forecast_runs.chance_below_line`.
- **Settings reload after a deploy:** stop caching `Settings` with `st.cache_resource` (`load_settings()` is cheap), or key the cached objects on a config/app version so a deploy can't reuse objects built by old code. Same review for `get_engine`/`get_llm` (they must be rebuilt if their class changes). Regression test with `AppTest`.
- **Local time:** store UTC; display in the owner's time zone (browser time zone via `st.context.timezone` if the Streamlit version has it, else the profile's time zone); Settings "Last run", chat timestamps, "last synced".
**Done when:** migration tests (old DB opens and upgrades); `reset()` covers new tables; settings test.

#### 1.5 Try an example business · Must · S
A button on Accounts loads one of the 1.1 businesses (files bundled read-only in the app package or `data/examples/`), runs the same upload path, and pre-fills onboarding answers from its key. Label it clearly ("Example: Panadería La Esquina, a bakery in Bogotá"). `DECISIONS.md` #22: example business replaces the old demo button.

### Phase 2: understand the business (weeks 2–3)

#### 2.1 Multiple bank accounts (Must) + credit cards (Should) · M + S
- Accounts page accepts several statements; one `account` per file (name from file or asked).
- **Internal transfers:** same amount, opposite sign, two of the owner's accounts, within 3 days (or a description pattern + owner confirmation) → `is_internal_transfer=1`, excluded from flows, history and categories. Note: "TRANSF A CTA AHORROS M GOMEZ" in Maria's file is the owner's pay to a personal account, not internal: ask (2.7).
- **Current balance** = sum of bank accounts. **Card:** purchases → spending by category on their dates; the card's statement balance → a scheduled payment on its due date; the bank's card-payment line is an internal transfer (not spending a second time).
**Done when:** a 1.1 business with two accounts + a card reconciles to its key; no double counting test.

#### 2.2 Transaction categorizer · Must · M
`aheadly/ai/categorizer.py`, run by App Core after every import: (1) `payee_rules` from owner answers, (2) keyword rules for common bank wording in Spanish and English (NOMINA/PAYROLL → payroll, ARRIENDO/RENT → rent, ENEL/CODENSA/VANTI/EPM → utilities, DATAFONO/REDEBAN/ABONO VENTAS → sales, PSE/PAGO PROVEEDOR → suppliers…), (3) zero-shot `facebook/bart-large-mnli` via `transformers` (MIT) cached with `st.cache_resource`, only rows with confidence ≥ 0.5; the rest become onboarding questions. `transformers`/`torch` optional (Streamlit Cloud size): without them skip (3), record in `DECISIONS.md`. Store `category_source`; owner's answer always wins. **Fix:** `_revenue_change_items` uses the business's real average weekly sales (category `sales`, last 8 weeks).
**Done when:** rule order tests; categories match 1.1 keys within tolerance; model mocked in CI.

#### 2.3 Recurring payments and income on their real dates · Must · L
`aheadly/ai/recurring.py`: normalize payees → `match_key` (lowercase; strip digits, dates, references, bank prefixes); group by (`match_key`, sign); cadence from the median interval: weekly 6–8 d, biweekly 13–15, monthly 28–31, quarterly 85–95, yearly 355–375 (≥ 3 occurrences for weekly–monthly; ≥ 2 for quarterly/yearly, then `certainty='maybe'` until confirmed); amount fixed if variation < 15% else "varies" (median of last 3); next date; confidence. Output `ScheduledItem(status='detected', source='statement', match_key, cadence, kind)` with kind from the category.
- **No double counting (critical):** replace the category rule in `_model_history` with: a transaction is excluded from model history **iff it is linked** (`scheduled_item_id`) to an active scheduled item. Link at detection time; for the seed, link by category so the canonical story doesn't change. The model then learns only the unexplained rhythm, and recurring items land on their real dates (fixes known issue 6).
- Flags for 2.6/2.7: an expected item didn't arrive (cadence + 5 days); amount changed (> 5% over the last 2).
**Done when:** on Maria's file it finds weekly payroll $1,800, weekly owner transfer $1,500, monthly rent on the 15th, monthly utilities (varies), weekly café income; forecast with detected items ≈ forecast from full history in total, but rent shows as a dip on the 15th; 1.1 recurring checks pass; canonical tests green.

#### 2.4 "Just say it" · Must · S
`AppCore.parse_plan_text(text) -> list[ProposedItem]`: the LLM extracts {label, amount, date or cadence, in/out, certainty} with a JSON schema; code validates (amount > 0, date parseable and ≥ as-of, sign from in/out) and shows a confirmation card; nothing saved without "Add". Stub planner: regex for "$7,500 … Dec 1". New chat tool `add_plan_item` that **proposes** (returns a card), never writes directly. Also a text box on the 2.6 page and in 2.7 answers.
**Done when:** tests for extraction validation (bad dates/amounts rejected), the confirm step, and the stub path.

#### 2.5 Upload any Excel file · receivables + bills Must · employee list Should · ledger + inventory Nice · M + S
- Accounts: the second uploader becomes "Other files you keep (optional)", multiple files.
- **Detect + map:** read headers + column types (+ value patterns, not values, for sensitive columns). Rules first (header keywords per type, Spanish/English); LLM proposes {type, column mapping} from headers only when rules are unsure; code validates (required columns present, types parse). Show a preview: "Looks like money customers owe you: 12 unpaid invoices, $8,400. Due dates Nov 20 to Jan 5. Right?" → confirm / change type / skip. Save in `uploaded_files`.
- **Per type:** receivables → `ScheduledItem(kind='receivable', source='file:<name>')` on due dates (overdue ones: ask, or likelihood < 1); bills/upcoming → `kind='bill'` (today's `read_upcoming_payments` becomes this reader); employee list → monthly payroll total compared with detected payroll (2.3), flag mismatch, enables "what if I hire" (adds a recurring cost); **never send names or salaries to the LLM**; ledger → `payee_rules`/categories by matching to bank transactions (date ± 3 d, amount), never adds flows (no double counting); inventory → suggested one-off restocks the owner confirms.
**Done when:** each type's reader tested on the 1.1 files; detection accuracy checked against keys; a test proves the employee list never reaches the LLM client.

#### 2.6 "How we built your forecast" page · Must · L
New page `aheadly/ui/views/forecast_basis.py` (sidebar between Alerts and Ask), replacing "What we're counting on" on Accounts. `AppCore` methods: `forecast_basis()` (all sections below as data), `update_plan_item`, `add_plan_item`, `pause/end/delete_plan_item`, `confirm_detected`, `plan_impact(change)` (before/after lowest balance, risk level).
1. **Starting point:** balance, as-of date, history span, transaction count, unidentified count (link to review), reconciliation result.
2. **Normal rhythm:** typical week of money in / out from the unexplained history (p25–p75 range), busiest/slowest weekdays and months.
3. **Recurring:** name, amount, cadence, next date, in/out, badge *Found in your statement* / *Confirmed by you* / *From your file* / *Added by you*; edit, pause, end on a date, delete; "amount varies". Automatic updates **suggest, never overwrite** ("Rent was $950 the last 2 months, not $900. Update?"); once `user_edited=1`, detection no longer changes the row.
4. **One-offs:** from files, chat (2.4), onboarding, saved plans; certain / maybe + likelihood; past-due ones ask "Did this happen?".
5. **Not counting on:** maybe items below the threshold, ignored unusual past charges, internal transfers.
6. **Next month at a glance:** money in / out split into rhythm, recurring, one-off.
- **Maybe items in the engine:** apply to a random subset of paths (share = likelihood, seeded RNG), so a maybe expense shows mostly in the worst case.
- **Every change reruns the forecast** and shows the effect ("Change rent to $950 → lowest balance $3,892").
- **Links in:** the dashboard cards, alerts and chat answers link to the items that drive them (top contributors in the risk window).
**Done when:** AppTest: add a one-off → lowest balance changes; edit a detected item → badge changes and survives a re-import; the page's next-month totals equal the forecast's.

#### 2.7 Onboarding questions · Must · L
After upload; resumable; skippable; progress bar; each question says why it matters; **never ask what the data already shows**; at most ~10 at first, the rest later as small cards.
1. Business: type, employees, how customers pay + terms, busy/slow months, comfortable minimum cash (sets the low cash line), how the owner pays themselves, financing options and supplier terms (3.6).
2. Confirm detected items: "We see $900 to ARRIENDO around the 15th every month. Is this rent?"; "Is the weekly $1,500 to M GOMEZ your own pay?"
3. What statements can't show: "Anything big coming up in the next two months?" (answered via 2.4), loans, money owed, unpaid bills (or upload the file, 2.5).
4. Mystery transactions: only the few largest uncategorized → answer becomes a payee rule.
Free-text "Tell us about your business" → LLM extracts into the profile schema → "Here's what I understood" → nothing saved without confirmation. The profile summary goes to prompts as data and to pattern rules (a busy December isn't "unusual").
**Done when:** functional test per 1.1 business: upload → key's answers → items + profile exist → expected warnings.

#### 2.8 Forecast confidence + "nothing big planned" note · Must · S
Score from history length, unidentified share, reconciliation, backtest error on the business's own past (`ForecastEngine.backtest`), detected-vs-confirmed share → high/medium/low + the two biggest reasons. If no one-off items exist: dashboard note "This forecast assumes no big one-off purchases. Planning any?" opening 2.4.

### Phase 3: solve, not just warn (weeks 3–4)

#### 3.1 Chance of dipping below the line · Must · S
`ForecastResult.path_minimums` (per-path minimum, not persisted) and `chance_below(line)`; persist in `forecast_runs.chance_below_line`; add to alert facts and scenario summary so the guardrail accepts it; show with the risk level.

#### 3.2 Actions framework · Must · M
`Action(label, detail, impact, adjustment, how_to, message_draft)` in `domain.py`. `impact` = before/after lowest balance, risk level and chance from actually running `adjustment` (a `run_scenario` dict) through the scenario engine (paths are cached → instant). Actions **name the real item** (from the risk window's top contributors), replacing the generic template actions. UI component: action row with impact line, **Test this** → `AppCore.run_what_if(action.adjustment)` → result card → *Save as my plan*. **How to do it:** 2–3 steps + an optional drafted WhatsApp/email (supplier: move a date; customer: friendly reminder) written by the LLM from facts, guardrail-checked, template fallback, shown with Copy; the app never sends. Applies to alerts, insights (4.1) and tight what-if answers.
**Done when:** every alert action with an adjustment has a computed impact; tests for impact numbers; drafted messages pass the guardrail.

#### 3.3 Suggested fixes · Must · M
When risk is `act_now` or `watch`, generate candidates: move each movable outflow in the risk window by 1–3 weeks (`move_item`), collect each receivable early (`collect_early`), delay planned purchases, lower the owner's pay for N weeks (`recurring_change` on the 2.3 item). Run each; rank by risk level, then worst case, then smallest change; top 3 as `Action`s. If none fixes it, try pairs of the top 5; if still not, hand to 3.6.
**Done when:** on Maria, moving the oven is in the top 3; 1.1 keys' expected fixes appear; ranking tests.

#### 3.4 Safe to spend + safe owner's pay · Must · S
`AppCore.safe_to_spend(window='week'|'month')`: largest one-off outflow on the next day such that the worst case (p10) stays ≥ the low cash line across the horizon (binary search over cached paths). `safe_owner_pay(weeks=4)`: largest weekly owner pay (replacing the detected owner's-pay item) with the same condition. Dashboard cards + chat tool `safe_to_spend`; facts to the guardrail. If already below the line: 0, and say why.

#### 3.5 Stress tests · Should · S
Presets as adjustments: sales −20% for 4 weeks (needs 2.2 sales), biggest customer pays 30 days late (largest receivable / top income source), main supplier +10% (top supplier category), surprise expense = one month of rent. Each: "you'd be fine" or "you'd need about $X" (gap size), with actions.

#### 3.6 Financing helper · Should · L
**Spec note:** spec 2.2 lists "Loans or credit offers" as out of scope. This compares only the options **the owner already has**, offers no credit, names no lenders; `DECISIONS.md` entry + "not financial advice" note in the UI. Runs only when 3.3 finds no free fix, or on request ("How can I cover this?"). `aheadly/ai/financing.py` via `AppCore.compare_financing()`:
1. Gap size (base: `line − lowest p50`; worst: `line − min p10`), start date, recovery date.
2. **Timing vs structural:** 12-week average net flow (excluding one-offs) > 0 and the base case recovers within the horizon → timing; else structural: say so plainly and point to costs/prices (4.1), no options.
3. Options from `business_profile.financing_options`: credit line, business card, longer supplier terms (`move_item`), invoice factoring / early collection (`collect_early` + fee), short-term loan, owner's own money.
4. Per option: feasible (limit ≥ amount, money arrives before the gap), cost in dollars (amount × rate × days / 365 + fees), effective annual rate.
5. New adjustment `financing {amount, start_date, repay_date, cost, label}` in `scenarios.py` (+ `ADJUSTMENT_TYPES`, `parse_adjustment`, `tools.ADJUSTMENT_SCHEMA`); **check the repayment doesn't create a new gap.**
6. Top 2 feasible options by cost as `Action`s. Rates come from the owner or are labelled examples; never hard-code real bank rates. Chat tool `compare_financing`; template fallback.

### Phase 4: insights (week 4)

#### 4.1 Pattern rules · small Must (3 patterns) · full Should · M
`aheadly/core/pattern_rules.py`, deterministic, same style as `alert_rules.py`, returns `InsightFacts(type, severity, facts, actions)` stored in `insights`. Small set: **thin cushion** (cash ÷ average weekly outflow < 2 weeks), **category creeping up** (last 3 months vs previous 3 > +15% and > $50/month), **depends on few customers** (top 1–2 income sources > 20% of money in). Full set adds: costs growing faster than sales, unusual or duplicate charge, new recurring charge, sales slowing, weekday shift, customers paying later (from receivables files), owner's pay vs surplus (> 75%), net flow shrinking, idle cash (existing). Respect the profile. 1.1 keys say what must / must not appear (healthy businesses: no false alarms).

#### 4.2 Insight text + chart summaries · Must (small) · S
`InsightTranslator.write_insight(facts)` and `summarize_chart(chart_facts)`: facts → JSON → guardrail → template fallback; 1–3 sentences; "nothing unusual here" allowed; cached per facts hash.

#### 4.3 Insights page + dashboard · small Must · full Should · M
Dashboard: current cash, lowest point + risk + chance, safe to spend / safe pay (3.4), forecast chart, alerts, top 2–3 "things we noticed" with actions, confidence (2.8). New `aheadly/ui/views/insights.py` (`st.tabs`): small = money in vs out by month (net line), spending by category over time, cash cushion (weeks covered); full adds where income comes from and sales by weekday. Every chart with its 4.2 summary. Chat tool `get_insights`.

### Phase 5: finish (week 4)

#### 5.1 Download / Load my data · Must · M
`AppCore.export_data() -> bytes`: zipped JSON (`aheadly-<business>-<date>.aheadly`) with every table for the business (profile, accounts, transactions with categories/links, scheduled items with status/edits, payee rules, uploaded-file mappings, onboarding answers, scenarios, plans, alerts, insights, forecast runs, chat), `schema_version`, `app_version`. `import_data(content)`: validate (zip/JSON, known keys, types, size limit, `schema_version` ≤ current → migrate older), never execute anything, load into the empty session DB, run the daily check. Then a newer statement adds only new transactions (1.3 ids). Privacy note next to the button; optional password (`cryptography` Fernet). `DECISIONS.md` entry.
**Done when:** round-trip test (export → import → identical dashboard, plan, alerts, chat); corrupted / newer-version file → friendly error.

#### 5.2 Privacy page + delete my data · Must · S
What is stored, where, for how long (this session only unless downloaded), what goes to the LLM provider (numbers and descriptions; never employee names or salaries), a "Delete my data now" button → `AppCore.reset()`.

#### 5.3 Glossary tooltips · Should · S
`help=` text and short definitions: worst case, base case, chance below the line, cash cushion, low cash line, safe to spend.

#### 5.4 Chatbot evaluation set · Should · S
`tests/eval_questions.json`: 20–30 questions (Spanish and English) across the 1.1 businesses: expected tool(s), checks (risk word present, no unverified numbers, < 120 words). Stub in CI; `scripts/eval_live.py` runs it on Gemini manually (quota).

#### 5.5 Final demo · Must · S
Two 1.1 businesses, uploaded like a real client (statements + Excel files) → onboarding (~1 min) → dashboard with risk, chance, safe to spend, things we noticed → alert actions with Test this and a drafted message → suggested fix → save plan → "How we built your forecast" → download my data. The second business shows the app isn't tied to one bakery. Update README and `docs/`; run the manual checklist; rehearse at most twice a day on the Gemini key; after merging to `main`, check the live site (and reboot it if 1.4's fix isn't in yet).

---

## 5. Nice to have (in rough order of value)
Cash calendar (next 8 weeks by day, tight days highlighted) · "Your week in 30 seconds" (2–3 sentences on the dashboard, 4.2 machinery) · What changed since your last visit (needs 5.1: compare the loaded file's last forecast run with the new one, attribute to drivers, real date of the last visit) · Forecast accuracy shown to the owner (backtest on their own past) · Mobile-friendly layout · "Was this helpful?" on answers and alerts (feeds 5.4) · More what-if types (`price_change`, `new_recurring_cost` e.g. a hire from the employee list, `new_recurring_income`) + comparing 2–3 scenarios · Seasonal patterns (12+ months) · Monthly cash summary (call it a cash summary, not accounting; spec 2.2) + one-click PDF report (`reportlab`, BSD) · Savings goals and break-even · Known tax payments as planned items (spec: no tax calculation) and bills paid well before their due date · Unusual-charge detection with `IsolationForest` vs the rules, measured on 1.1 keys (course lecture 18) · Excel templates to download (optional, only for owners with nothing written down) · Spanish (`copy_es.py`) + currencies (COP: no cents, "." thousands; change the seed tests together) · PDF bank statements (LLM extraction + reconciliation + preview; likely moves up for the real product) · Ledger and inventory file types if not done in 2.5.

## 6. Long term (after the class)
Subscription service: logins and saved data per business (hosted Postgres, e.g. Supabase with row-level security; all SQL is already in `Repository`; 5.1 files migrate users in) · automatic updates (monthly upload reminder, then Plaid/QuickBooks scaffolds or a Latin American aggregator such as Belvo) · daily check on a host that doesn't sleep (`python -m aheadly.jobs.daily_run`) · notifications: weekly email summary, alerts, a WhatsApp check-in ("Next week looks tight. Reply 1 to see options") · accountant access, several users per business · security (encryption at rest, privacy terms, access audit) · billing.

## 7. Checklist for each item
- [ ] Failing test first; unit + functional tests; canonical demo tests green.
- [ ] Test-business harness green; this item's `xfail`s removed; no 1.1 file edited.
- [ ] Numbers computed in code; new LLM text through the guardrail with a template fallback; LLM outputs cached per facts hash.
- [ ] New strings in `copy.py`; new SQL only in `repository.py` with a migration.
- [ ] New chat tool (if any) in `TOOL_SCHEMAS`, `ToolDispatcher`, the stub planner and 5.4.
- [ ] No personal data beyond what the item needs reaches the LLM.
- [ ] `PROGRESS.md` updated; `DECISIONS.md` entry for any deviation.
- [ ] Works with `LLM_PROVIDER=stub` and with Gemini; after a merge to `main`, the live site checked.
