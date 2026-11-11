# Café La Tertulia (Cali)

_Cali café whose costs have outrun flat sales since August, so cash slides toward its $1,500 minimum: a structural problem a loan won't fix._

## Story

Julián Muestra Ortiz runs a café in Cali with three staff and, since August 2026, a part-time helper. Sales are flat all year: card sales Monday to Saturday, a weekly cash deposit and a weekly Rappi payout. Coffee, milk and pastry suppliers raised prices about 8% in March and another 24% in August, the lease went up 9% in July, and a new point-of-sale subscription started in August.

Since August more money goes out than comes in. The account has $3,568.29 on 2026-11-10 and keeps sliding; the December bonus pushes it under the $1,500 minimum late in the forecast. Borrowing would lift the line for a few weeks but the monthly loss continues; prices or costs must change.

On 2026-10-20 the milk supplier was paid twice for the same delivery.

## What it tests

- Structural, not timing: there is no single event to move; the gap repeats every month.
- The loan what-if raises the 8-week low, yet the right answer says it only buys time.
- Insights: cost_creeping_up, costs_faster_than_sales, net_flow_shrinking, a duplicate charge and a new recurring charge.
- No balance column, so the app must ask the owner for today's balance.

## Tricky parts

- No Balance column: the balance on 2026-11-10 must be typed in (see the answer key).
- Dates like 05-dic-2026 with Spanish month abbreviations.
- Negative amounts in parentheses, e.g. (1.290,00); decimal comma in a comma-delimited file, so amounts are quoted.
- Closed on Sundays: no card sales those days.
- Two identical lines on 2026-10-20 (PAGO PSE LACTEOS DEL VALLE): a real duplicate charge, not an import duplicate; both must be kept.
- TRANSF 0211 REF 30774 is the building's admin fee (category rent).

## Key numbers (from the ground truth)

- Cash on 2026-11-10: $3,568.29 (low-cash line $1,500.00)
- True lowest in the next 8 weeks: $1,280.00 on 2027-01-05
- First day below the line: 2026-12-18
- Acceptable risk levels: act_now
- Insights that must appear: thin_cushion, cost_creeping_up, costs_faster_than_sales, duplicate_charge, new_recurring_charge, owner_pay_high, net_flow_shrinking
- Insights that must not appear: sales_slowing, few_customers, customers_paying_later, idle_cash

## Solved and automatic values

- Closing balance solved at $3,568.29 so the true lowest balance in the next 8 weeks is $1,280.00.

## Files

- `statements/movimientos_ahorros_2208.csv`: bank_statement, Ahorros 2208, 1173 lines, 2025-11-11 to 2026-11-10
- `files/staff.csv`: owner file (employees), 4 rows

All names of people and companies are invented.
