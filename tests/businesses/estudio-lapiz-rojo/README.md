# Estudio Lápiz Rojo (Medellín)

_Healthy Medellín design studio with steady retainers and far more cash than it needs: no alerts, only idle cash._

## Story

Valentina Ejemplo Ríos runs a two-designer studio in Medellín. Twelve clients pay monthly retainers ($560-$850) by transfer around the 15th, always at about the same point; project work comes in through a card payment link. Salaries are paid in two halves, social security on the 9th, VAT every two months and withholding tax monthly.

Cash grows by roughly $2,000 a month and sits in one savings account: $52,400.00 on 2026-11-10 against a $5,000 minimum. The only planned items are a laptop and the yearly hosting renewal in December.

## What it tests

- A false-alarm test: no shortfall, no cost creep, no late payers, no concentration.
- December has a bonus (prima) and slower project income; this must not cause an alert.
- Lumpy taxes (VAT every two months) must not read as costs jumping or falling.
- The useful insight is idle cash; the term-deposit what-if shows how much is spare.

## Tricky parts

- English headers with separate Debit and Credit columns; an empty cell means zero.
- Comma-delimited file whose amounts contain thousands commas (quoted fields).
- Card subscriptions post on weekends; transfers move to business days.
- TRANSF 0117 REF 40562 is the accountant; nothing in the text says so.
- Payment-link income (ABONO PASARELA WOMPI) has no customer name.

## Key numbers (from the ground truth)

- Cash on 2026-11-10: $52,400.00 (low-cash line $5,000.00)
- True lowest in the next 8 weeks: $50,618.81 on 2026-12-09
- First day below the line: never
- Acceptable risk levels: safe
- Insights that must appear: idle_cash
- Insights that must not appear: thin_cushion, cost_creeping_up, costs_faster_than_sales, unusual_charge, duplicate_charge, new_recurring_charge, sales_slowing, few_customers, customers_paying_later, owner_pay_high, net_flow_shrinking

## Files

- `statements/account_statement_0932.csv`: bank_statement, Ahorros 0932, 594 lines, 2025-11-11 to 2026-11-10
- `files/upcoming_payments.csv`: owner file (upcoming_payments), 2 rows
- `files/open_invoices.csv`: owner file (receivables), 10 rows

All names of people and companies are invented.
