# Disfraces La Fantasía (Barranquilla)

_Barranquilla costume shop just past its Halloween peak: the slow season, a big VAT bill and the Carnaval stock deposit pull cash down, but it stays above the line._

## Story

Rosa Ejemplo Charris sells and rents costumes in Barranquilla with three staff and extra temps in each peak. Sales explode in October (Halloween) and in the weeks before Carnaval (February), and are thin from November to mid-January and in March. Stock for each peak is bought one to two months ahead, financed with a revolving credit line repaid from the season's sales. VAT is paid every two months on the previous two months' sales.

On 2026-11-10 the account holds $13,813.31 after a strong October. Over the next eight weeks a VAT payment of $2,610.43 (Nov 13, on the Halloween sales), the $5,200 Carnaval stock deposit (Dec 9), the December bonus and thin sales take it down to about $3,900.00, still above her $3,000 minimum. Last year's statement shows the same slow months, so a good forecast follows last year's shape rather than October's.

## What it tests

- Extrapolating October (or the yearly average) gives a rising forecast; the truth falls.
- A large tax payment that depends on the previous peak's sales.
- Seasonal cost jumps (stock, temps) must not be called creeping costs or slowing sales with certainty; these are judgement calls in the key.
- Base case safe or watch: only a weaker-than-usual December brings it near the minimum.

## Tricky parts

- The statement is an .xlsx file with real Excel date and number cells, oldest first.
- Sundays have sales only in February and October.
- DESEMBOLSO / PAGO CREDITO ROTATIVO lines are borrowing and repaying, not sales or costs.
- The owner's file is semicolon-separated, Windows-1252, decimal comma, and lists one payment after the 8-week window (2027-01-12).

## Key numbers (from the ground truth)

- Cash on 2026-11-10: $13,813.31 (low-cash line $3,000.00)
- True lowest in the next 8 weeks: $3,900.00 on 2027-01-05
- First day below the line: never
- Acceptable risk levels: safe, watch
- Insights that must appear: none
- Insights that must not appear: thin_cushion, duplicate_charge, sales_slowing, few_customers, customers_paying_later, owner_pay_high, idle_cash

## Solved and automatic values

- History safety net: Ahorros 6610 used a revolving credit line, $6,500.00 drawn 2025-12-26 and repaid with interest on 2026-02-27.
- History safety net: Ahorros 6610 used a revolving credit line, $4,500.00 drawn 2026-08-27 and repaid with interest on 2026-10-30.
- History safety net: Ahorros 6610 used a revolving credit line, $4,000.00 drawn 2026-04-27 and repaid with interest on 2026-06-26.
- History safety net: Ahorros 6610 used a revolving credit line, $3,500.00 drawn 2026-03-26 and repaid with interest on 2026-05-29.
- History safety net: Ahorros 6610 used a revolving credit line, $3,000.00 drawn 2025-11-11 and repaid with interest on 2026-01-15.
- History safety net: Ahorros 6610 used a revolving credit line, $2,500.00 drawn 2026-06-25 and repaid with interest on 2026-08-28.
- History safety net: Ahorros 6610 used a revolving credit line, $2,000.00 drawn 2026-02-23 and repaid with interest on 2026-04-27.
- Closing balance solved at $13,813.31 so the true lowest balance in the next 8 weeks is $3,900.00 (130% of the minimum).

## Files

- `statements/movimientos_6610.xlsx`: bank_statement, Ahorros 6610, 728 lines, 2025-11-11 to 2026-11-10
- `files/compromisos_proveedores.csv`: owner file (upcoming_payments), 3 rows

All names of people and companies are invented.
