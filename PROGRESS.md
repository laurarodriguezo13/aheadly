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

## Next (for the final demonstration)
Direction (agreed 2026-11-10): the client only has bank statements (CSV/Excel now, PDF later) and maybe their own Excel files. One-time sessions now; saved accounts and a subscription later. No Plaid or QuickBooks for the course (the scaffolds stay).
1. Test businesses with answer keys: fake statements for several different businesses, made outside the code, plus automated tests that check the app against them.
2. Finish reading real bank files: forecast from the statement's last date, check that the balance adds up.
3. Categories and recurring payments from the statement (rules + Hugging Face zero-shot), without double counting.
4. Money plan page + onboarding questions ("detect first, then ask"); one editable list of everything the forecast expects.
5. Actions with "Test this" and suggested fixes for every warning; alert actions should name the payment that causes the alert.
6. Financing helper: compares the owner's existing options (credit line, card, supplier terms) by cost; never offers credit.
7. Insights page ("Things we noticed"), with a short summary under every chart.
8. Download / Load my data, privacy page, glossary, chatbot test set.
9. Demo day: regenerate Maria's files the same day (`uv run python ../aheadly-test-data/make_maria_files.py`) and rehearse at most twice on the Gemini key (free-tier daily quota).

Later (after the course): PDF statements, Plaid / QuickBooks, accounts and a subscription.

## Open decisions
- Whether idle-cash alerts should be shown on the dashboard or only in Alerts.
- When Plaid comes back: encrypt stored tokens with Fernet (spec) or keep sandbox tokens in `.env` only.
