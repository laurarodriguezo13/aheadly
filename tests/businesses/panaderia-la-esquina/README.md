# Panadería La Esquina (Bogotá)

_Bogotá bakery whose new oven drains its cushion, so cash dips below $2,000 in mid-December until two cafés pay their Christmas orders._

## Story

Maria Gómez (45) runs a neighbourhood bakery in Bogotá with six employees paid every Friday. Card sales settle every day (smaller on Sundays and holidays, much bigger in December). Two cafés buy bread on 7-day credit and pay weekly: Café El Tinto Feliz on Mondays, Café La Molienda Azul on Thursdays. Flour, dairy and eggs are paid weekly, a bulk flour order every quarter, rent on the 15th and utilities around the 5th (slowly rising). A cryptic monthly transfer, TRANSF 0045 REF 88213, repays an equipment loan. Every Friday Maria moves her own pay ($690.00) to her personal savings account.

On 2026-11-10 she has $8,200. On Nov 12 a construction company pays $3,883.34 for Christmas hampers, and on Nov 14 she pays $7,500 for a new oven. Cash holds for four weeks; then the Christmas ingredients ($2,640.00, Dec 10), the $4,000 quarterly flour order and the rent (both Dec 15) take it to about $1,350, below her $2,000 minimum. The two cafés pay $5,500 each on Dec 16 and 17 and cash recovers.

This is a timing gap, not a loss. Paying the oven after the Christmas orders fixes it. Paying it exactly one month later (Dec 14) does not, because it then lands in the same week as the flour order.

## What it tests

- A known one-off (the oven) causes a shortfall five weeks later, not on the day it is paid.
- The fix is about timing: 'one month later' (Dec 14) is NOT enough, after Dec 20 is.
- Recurring items on several cadences: daily, weekly (Mon/Tue/Wed/Thu/Fri), monthly, every two months, quarterly and twice a year.
- Owner files announce the oven, the flour order, the Christmas ingredients and both Christmas orders; the receivables file has the corporate order and two overdue invoices.

## Tricky parts

- Two statements of the same account overlap 2026-05-01..2026-05-15; shared lines count once.
- The first statement is Windows-1252 encoded, the second UTF-8.
- Semicolon-separated, decimal comma, thousands dot, newest line first.
- Payroll moves to Thursday when Friday is a holiday (and to Wednesday 2026-04-01 in Holy Week).
- Rent due on the 15th is paid on the next business day (2026-11-17 next time).
- TRANSF 0045 REF 88213 is a loan repayment; nothing in the text says so.
- The same two cafés send small weekly payments and one large December payment each.
- The GMF 4X1000 tax follows almost every payment as a separate tiny line.
- 47 lines appear in two overlapping statements and must be counted once.

## Key numbers (from the ground truth)

- Cash on 2026-11-10: $8,200.00 (low-cash line $2,000.00)
- True lowest in the next 8 weeks: $1,350.00 on 2026-12-15
- First day below the line: 2026-12-15
- Acceptable risk levels: act_now
- Insights that must appear: owner_pay_high
- Insights that must not appear: cost_creeping_up, costs_faster_than_sales, duplicate_charge, sales_slowing, customers_paying_later, net_flow_shrinking, idle_cash

## Solved and automatic values

- Owner pay solved at $690.00 a week so the account a year ago held about $7,800.
- Corporate hamper order solved at $3,883.34 so the week-5 low is $1,350.00.
- Christmas ingredients set at 24% of the Christmas orders ($2,640.00); solving it as well would be redundant, because it shifts the December low by the same amount as the corporate order.

## Files

- `statements/extracto_ahorros_4471_2025-11_2026-05.csv`: bank_statement, Ahorros 4471, 623 lines, 2025-11-11 to 2026-05-15
- `statements/extracto_ahorros_4471_2026-05_2026-11.csv`: bank_statement, Ahorros 4471, 641 lines, 2026-05-01 to 2026-11-10
- `files/proximos_pagos.xlsx`: owner file (upcoming_payments), 5 rows
- `files/cartera.xlsx`: owner file (receivables), 5 rows
- `files/empleados.xlsx`: owner file (employees), 6 rows

All names of people and companies are invented.
