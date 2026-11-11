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
- Upload-only onboarding (2026-11-10): bank statement + optional upcoming one-off payments file, balance read from the statement, no demo/Plaid/QuickBooks buttons; Maria's demo story verified from uploaded files with Prophet; 58 tests.
- Latin American bank formats (2026-11-11): day/month dates, "1.250,00" amounts, unreadable rows skipped and reported instead of becoming $0; 64 tests.
- "What we're counting on" (2026-11-11): Accounts lists the upcoming payments the forecast uses (`AppCore.planned_items`) and updates when a plan is saved; 65 tests.
- Suggested questions from the business's own payments (2026-11-11): the third suggestion names the biggest payment due before the end of next month and moves on to the next one once a plan is saved; the offline chat finds any scheduled payment by name; 69 tests.
- Bank files, roadmap 1.3 (2026-11-11): the forecast starts where the statement ends (with a notice when it ends before yesterday), newest-first files read correctly, the Balance column is checked, the same bank line keeps the same id across files; 80 tests.
- Live-check fixes, roadmap 1.4 (2026-11-11): cached objects keyed by a code fingerprint so an update can't crash the live site; times stored in UTC, shown in the visitor's time zone; 88 tests. Known: `AppCore.today` still uses the server's date (UTC on Streamlit Cloud), so after about 7 pm in New York "today" is already tomorrow; fix with the business profile's time zone (1.4 groundwork).

## Next (for the final demonstration)
Follow `docs/ROADMAP.md` (one builder, about four weeks; Must / Should / Nice, sizes, dependencies, cut order). In short:
1. Phase 1, foundation and proof: test businesses with answer keys (made separately from the code) + harness; finish bank files (as-of date, reconciliation, stable ids); groundwork (migrations, business profile, settings reload after a deploy, local time); "Try an example business".
2. Phase 2, understand the business: multiple accounts + credit cards; categorizer; recurring detection on real dates (weekly to yearly) without double counting; "just say it"; any Excel file (receivables, bills, employee list, ledger, inventory); "How we built your forecast" page; onboarding questions; forecast confidence.
3. Phase 3, solve, not just warn: chance below the line; actions with computed impact, Test this, how-to steps and drafted messages; suggested fixes; safe to spend / safe owner's pay; stress tests; financing helper.
4. Phase 4, insights: pattern rules, chart summaries, Insights page.
5. Phase 5, finish: Download / Load my data, privacy page, glossary, chatbot eval set, final demo with two test businesses.

Demo day: regenerate Maria's files the same day (`uv run python ../aheadly-test-data/make_maria_files.py`) and rehearse at most twice on the Gemini key. After a merge to `main`, check the live site; reboot it on Streamlit Cloud if it shows `AttributeError` (cached settings, fixed in Phase 1).

## Open decisions
- Whether idle-cash alerts should be shown on the dashboard or only in Alerts.
- When Plaid comes back: encrypt stored tokens with Fernet (spec) or keep sandbox tokens in `.env` only.
