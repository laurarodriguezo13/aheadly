# Taller Los Pistones (Pereira)

_Pereira auto-repair shop with ordinary finances but the messiest files: preamble lines, unreadable rows, a missing line and an old account closed in August._

## Story

Óscar Simulado Henao runs a repair shop with three mechanics paid every Saturday. Drivers pay by card or Nequi; an insurance company pays repair claims about twice a month. Until July 2026 the insurer paid into an old account at another bank, from which Óscar swept the money to his main account; in August he changed the account on file and closed the old one, moving its last balance across.

The business itself is steady. Its files are not: the main bank export starts with six lines of bank text, has four rows that cannot be read and is missing one line, so its running balance stops adding up in June. In late October an international online charge of $689.30 appeared that matches nothing else in the history.

## What it tests

- Import robustness: preamble, unreadable rows, missing line, odd amount format, encoding.
- Two accounts but only one open: the old one's statement ends in August with balance 0.
- Money swept from the old account looks like income on the main account but is internal.
- unusual_charge must appear for the October online purchase.

## Tricky parts

- Six preamble lines (bank name, account, holder, period, final balance, blank) above the header.
- Amounts like '$ 7.900' and '-$ 1.234,56': dot for thousands, comma for cents, no decimals when the cents are zero.
- Upper-case Spanish headers in Windows-1252; newest line first; semicolon-separated.
- Unreadable cells show '#¡VALOR!' (amount) or '#########' (date); the rest of each row is fine.
- Nequi transfers have only a random reference number (TRANSF NEQUI REF 12345).
- The old account's statement deliberately ends on 2026-08-31.
- The employee file uses dates like 02.05.2018 and pay like '$ 280'.
- `statements/extracto_4589.csv` has 4 unreadable line(s).
- `statements/extracto_4589.csv`: a line is missing, so the Balance column stops adding up on 2026-06-17.

## Key numbers (from the ground truth)

- Cash on 2026-11-10: $7,900.00 (low-cash line $1,800.00)
- True lowest in the next 8 weeks: $7,339.76 on 2026-12-21
- First day below the line: never
- Acceptable risk levels: safe
- Insights that must appear: unusual_charge, owner_pay_high
- Insights that must not appear: thin_cushion, cost_creeping_up, costs_faster_than_sales, duplicate_charge, sales_slowing, customers_paying_later, net_flow_shrinking, idle_cash

## Solved and automatic values

- Missing line: 2026-06-17 PAGO PSE AUTOPARTES DEL EJE -$824.03. Unreadable lines: 2026-10-14 PAGO PSE AUTOPARTES DEL EJE -$1,039.04 (amount); 2026-04-27 COMISION CONSIGNACION NACIONAL -$2.24 (amount); 2026-01-21 PAGO PSE AUTOPARTES DEL EJE -$808.57 (date); 2026-07-08 PAGO PSE AUTOPARTES DEL EJE -$647.33 (date). monthly_totals include these lines (true totals), so the affected months may differ from what the files alone show.

## Files

- `statements/extracto_4589.csv`: bank_statement, Ahorros 4589, 840 lines, 2025-11-11 to 2026-11-10
- `statements/cuenta_vieja_1180_hasta_agosto.csv`: bank_statement, Ahorros 1180, 46 lines, 2025-11-13 to 2026-08-28
- `files/mecanicos.csv`: owner file (employees), 3 rows
- `files/reclamaciones_pendientes.xlsx`: owner file (receivables), 5 rows

All names of people and companies are invented.
