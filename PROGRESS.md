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
- Live-check fixes, roadmap 1.4 (2026-11-11): cached objects keyed by a code fingerprint so an update can't crash the live site; times stored in UTC, shown in the visitor's time zone; 88 tests.
- Groundwork, roadmap 1.4 (2026-11-11): the database upgrades itself (numbered migrations), business profile, planned items remember where they came from and how sure we are, new link fields and tables for Phase 2, "today" in the owner's time zone; 97 tests.
- Test businesses, roadmap 1.1 and 1.2 (2026-11-11): six businesses with answer keys made separately from the code (`tests/businesses/`), checked by `tests/test_businesses.py` with a scorecard; the reading bugs they found are fixed (DECISIONS #26). 126 tests pass, 48 checks wait for roadmap items (PENDING). Next: 2.1 (several accounts, credit cards), then 2.2 and 2.3.
- Check-up (2026-11-11): the upcoming-payments file now reads the same bank formats as statements and reports lines it can't read (it used to drop Latin American dates and amounts silently); README updated; 128 tests.
- Several accounts and credit cards, roadmap 2.1 (2026-11-11): upload several statements at once; overlapping statements of one account merge; credit card statements (debt, not cash); transfers between the owner's own accounts and card payments are left out of income, spending and the forecast's history. Bakery and hardware store go from 2 to 6 and 7 checks passing; 146 tests pass, 38 checks wait (PENDING).
- Try an example business, roadmap 1.5 (2026-11-11): one click on Accounts loads the bakery (Panadería La Esquina) with its statements and known upcoming payments, shown as of Nov 11, 2026 and marked as an example; account names leave out dates and words like "extracto" from the file name ("Ahorros 4471"). Phase 1 is complete. 159 tests pass, 38 checks wait (PENDING).
- Categories, roadmap 2.2 (2026-11-11): every bank line gets a category (sales, payroll, rent, utilities, suppliers, taxes, loan, bank fees...) from keyword rules, and the owner's answer about a payee always wins and applies to later uploads; Accounts shows them; the What-if "change sales" uses the real weekly sales, and the What-if form shows the right boxes as soon as you pick what to test. Categories check passes for 5 of 6 test businesses (the sixth has unreadable lines in the key's totals). 207 tests pass, 33 checks wait (PENDING).

## Next (for the final demonstration)
Follow `docs/ROADMAP.md` (one builder, about four weeks; Must / Should / Nice, sizes, dependencies, cut order). In short:
1. Phase 1, foundation and proof: done (1.1 to 1.5, 2026-11-11).
2. Phase 2, understand the business: multiple accounts + credit cards (done, 2.1); categories (done, 2.2); next recurring payments on their real dates (2.3); recurring detection on real dates (weekly to yearly) without double counting; "just say it"; any Excel file (receivables, bills, employee list, ledger, inventory); "How we built your forecast" page; onboarding questions; forecast confidence.
3. Phase 3, solve, not just warn: chance below the line; actions with computed impact, Test this, how-to steps and drafted messages; suggested fixes; safe to spend / safe owner's pay; stress tests; financing helper.
4. Phase 4, insights: pattern rules, chart summaries, Insights page.
5. Phase 5, finish: Download / Load my data, privacy page, glossary, chatbot eval set, final demo with two test businesses.

Demo day: regenerate Maria's files the same day (`uv run python ../aheadly-test-data/make_maria_files.py`) and rehearse at most twice on the Gemini key. After a merge to `main`, check the live site; reboot it on Streamlit Cloud if it shows `AttributeError` (cached settings, fixed in Phase 1).

## Open decisions
- Whether idle-cash alerts should be shown on the dashboard or only in Alerts.
- When Plaid comes back: encrypt stored tokens with Fernet (spec) or keep sandbox tokens in `.env` only.
